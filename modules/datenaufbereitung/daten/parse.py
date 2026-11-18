"""Cell texts in number columns (DP-06): markers, uncertainties, units in the cell, dates and times.

Plain numbers (decimal comma, thousands separators, `1,2E-3`, `1,2·10^-3`) are read by `labtable.number` already.
What is left in a number column is resolved here, never guessed:

    "<0,01"  "< 0.5 mg/L"     below detection limit: value = the limit, flag `below_lod`
    "<NWG" "<LOD" "BDL"        below detection limit without a number: missing, flag `below_lod`
    ">1000"                     above the range: value = the limit, flag `above_range`
    "n.d." "—" "k.A." "NA"      missing, flag `missing`
    "#DIV/0!" "#NV" …           Excel error value: missing, flag `missing`
    "12,3 ± 0,4"  "12.3 +/- 0.4"   value and uncertainty (→ uncertainty column)
    "12,5 mg"                   value with unit: kept when the unit is the column unit, converted when it has the
                                same dimension (flag `note`), otherwise left as a parse error

Dates and times (Excel date cells, or text like `2024-03-01 12:00:05`, `01.03.2024 12:00`, `12:00:05`) become
elapsed time from the first value; the start is kept as a condition of the dataset.
"""
from __future__ import annotations

import datetime as _dt
import math
import re

import numpy as np

import labtable as LT

_LOD_WORDS = r"(?:lod|loq|nwg|bg|ng|dl|ql|nachweisgrenze|bestimmungsgrenze|detection\s+limit|quantification\s+limit)"
_BELOW = re.compile(rf"^\s*(?:<|≤|<=|&lt;|kleiner\s+als|unter|below|less\s+than)\s*(.*?)\s*$", re.I)
_ABOVE = re.compile(r"^\s*(?:>|≥|>=|&gt;|grösser\s+als|größer\s+als|über|ueber|above|greater\s+than)\s*(.*?)\s*$", re.I)
# bare "dL", "BG", "NG" are column names (decilitre, …), so a bare word only counts when it cannot be one
_BDL = re.compile(rf"^\s*(?:bdl|u\.\s*{_LOD_WORDS}|unter\s+{_LOD_WORDS}|below\s+{_LOD_WORDS}|<\s*{_LOD_WORDS}|"
                  r"nachweisgrenze|bestimmungsgrenze|below\s+detection\s+limit|not\s+detectable)\s*$", re.I)
_MISSING = {"n.d.", "n. d.", "nd", "n.d", "n.a.", "n. a.", "na", "n/a", "n.a", "k.a.", "k. a.", "ka", "k.a", "n.v.", "nv",
            "n.b.", "nb", "-", "–", "—", "--", "---", "?", "??", "nan", "null", "none", "leer", "fehlt", "missing",
            "/", "x", "*", "n.m.", "nm", "kein wert", "keine angabe", "not detected", "not determined"}
_EXCEL_ERR = re.compile(r"^#(?:DIV/0!|N/?A|NV|WERT!|VALUE!|REF!|BEZUG!|NAME\?|NUM!|ZAHL!|NULL!|LEER!|SPILL!|ÜBERLAUF!|CALC!|GETTING_DATA)$", re.I)
_PM = re.compile(r"^\s*(.+?)\s*(?:±|\+/-|\+-|\+ /\s*-)\s*(.+?)\s*$")
_NUM_UNIT = re.compile(r"^\s*([-+−]?(?:\d[\d.,' ]*|[.,]\d+)(?:[eE][-+−]?\d+)?(?:\s*[·x×*]\s*10\s*\^?\s*\(?[-+−]?\d+\)?)?)\s*(.*?)\s*$")


def _clean_u(u: str) -> str:
    from .recipe import _clean_unit
    return _clean_unit(u)


def _convert(x: float, unit: str, col_unit: str):
    """(value in the column unit, converted?) or None when the unit does not fit the column."""
    unit = _clean_u(unit)
    if not unit or unit == (col_unit or ""):
        return x, False
    from labcalc import units as U
    try:
        f1, d1, o1 = U.parse_unit(unit)
        f2, d2, o2 = U.parse_unit(col_unit or "")
    except U.UnitError:
        return None
    if not col_unit or not U.deq(d1, d2) or not U.compatible(unit, col_unit):
        return None
    return (x * f1 + o1 - o2) / f2, True


def number_unit(text: str, col_unit: str = ""):
    """'12,5 mg' → (12.5, converted?) in the column unit, or None."""
    m = _NUM_UNIT.match(str(text or ""))
    if not m:
        return None
    x = LT.number(m.group(1))
    if x is None:
        return None
    return _convert(x, m.group(2), col_unit)


def resolvable(text: str) -> bool:
    """Would `marker` resolve this text (any unit)? Used to decide whether a column holds numbers."""
    t = str(text or "").strip()
    if not t:
        return False
    if _EXCEL_ERR.match(t) or t.lower() in _MISSING or _BDL.match(t) or _PM.match(t):
        return True
    for rx in (_BELOW, _ABOVE):
        m = rx.match(t)
        if m:
            return True
    m = _NUM_UNIT.match(t)
    if not (m and LT.number(m.group(1)) is not None and 0 < len(m.group(2)) <= 12):
        return False
    from labcalc import units as U
    try:                                                # "1. Messung" is a label, "12,5 mg" a value
        U.parse_unit(_clean_u(m.group(2)))
        return True
    except U.UnitError:
        return False


def marker(text: str, col_unit: str = "") -> dict | None:
    """Resolve one cell text of a number column: {"value", "code", "u"?, "reason"?} or None (parse error)."""
    t = str(text or "").strip()
    if not t:
        return None
    low = t.lower()
    if _EXCEL_ERR.match(t):
        return {"value": math.nan, "code": "missing", "reason": "Excel-Fehlerwert"}
    if low in _MISSING:
        return {"value": math.nan, "code": "missing", "reason": "kein Wert"}
    if _BDL.match(t):
        return {"value": math.nan, "code": "below_lod", "reason": "unter der Nachweisgrenze (ohne Zahl)"}
    for rx, code, word in ((_BELOW, "below_lod", "unter"), (_ABOVE, "above_range", "über")):
        m = rx.match(t)
        if m:
            rest = m.group(1)
            if not rest or _BDL.match(rest) or re.fullmatch(_LOD_WORDS, rest, re.I):
                return {"value": math.nan, "code": code, "reason": f"{word} der Grenze (ohne Zahl)"}
            r = number_unit(rest, col_unit)
            if r is None:
                return None
            return {"value": r[0], "code": code, "reason": f"Wert = Grenze ({t[:40]})"}
    m = _PM.match(t)
    if m:                                               # "12,3 ± 0,4", "12,3 mg ± 0,4 mg", "12,3 ± 0,4 mg"
        m1, m2 = _NUM_UNIT.match(m.group(1)), _NUM_UNIT.match(m.group(2))
        if not (m1 and m2):
            return None
        x, u = LT.number(m1.group(1)), LT.number(m2.group(1))
        if x is None or u is None:
            return None
        unit = m1.group(2) or m2.group(2)
        a = _convert(x, unit, col_unit)
        if a is None:
            return None
        uu = abs(u) if not a[1] else abs(_convert(abs(u), unit, col_unit)[0] - _convert(0.0, unit, col_unit)[0])
        return {"value": a[0], "code": "note" if a[1] else None, "u": uu,
                "reason": "Wert ± Unsicherheit" + (f", umgerechnet aus {unit}" if a[1] else "")}
    r = number_unit(t, col_unit)
    if r is not None:
        return {"value": r[0], "code": "note" if r[1] else None, "reason": f"umgerechnet aus „{t[:40]}“" if r[1] else ""}
    return None


# ----------------------------------------------------------------------------- dates and times
_ISO = re.compile(r"^\s*(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2})(?:[.,](\d+))?)?)?\s*(Z|[+-]\d{2}:?\d{2})?\s*$")
_DE = re.compile(r"^\s*(\d{1,2})\.(\d{1,2})\.(\d{2}|\d{4})(?:,?\s+(\d{1,2}):(\d{2})(?::(\d{2})(?:[.,](\d+))?)?)?\s*$")
_TIME = re.compile(r"^\s*(\d{1,2}):(\d{2})(?::(\d{2})(?:[.,](\d+))?)?\s*$")
_EPOCH = _dt.datetime(1970, 1, 1)


def _frac(s) -> float:
    return float("0." + s) if s else 0.0


def _offset_s(tz: str) -> int:
    """'Z', '+01:00', '-0530' → seconds east of UTC."""
    if tz.upper() == "Z":
        return 0
    sign = -1 if tz[0] == "-" else 1
    hh, mm = int(tz[1:3]), int(tz[-2:])
    if hh > 23 or mm > 59:
        raise ValueError("Zeitzone ungültig")
    return sign * (hh * 3600 + mm * 60)


def time_info(text: str):
    """Text → (seconds since 1970, time_only, has_offset) or None. A date-time with a time-zone suffix (Z, +01:00)
    is converted to UTC; without one it is read as local wall-clock time as written (no daylight-saving correction)."""
    t = str(text or "")
    try:
        m = _ISO.match(t)
        if m:
            y, mo, d, h, mi, s, f, tz = m.groups()
            dt = _dt.datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0), int(s or 0))
            sec = (dt - _EPOCH).total_seconds() + _frac(f)
            if tz:
                return sec - _offset_s(tz), False, True
            return sec, False, False
        m = _DE.match(t)
        if m:
            d, mo, y, h, mi, s, f = m.groups()
            y = int(y) + (2000 if len(y) == 2 else 0)
            dt = _dt.datetime(y, int(mo), int(d), int(h or 0), int(mi or 0), int(s or 0))
            return (dt - _EPOCH).total_seconds() + _frac(f), False, False
        m = _TIME.match(t)
        if m:
            h, mi, s, f = m.groups()
            if int(h) > 47 or int(mi) > 59 or int(s or 0) > 59:
                return None
            return int(h) * 3600 + int(mi) * 60 + int(s or 0) + _frac(f), True, False
    except ValueError:
        return None
    return None


def time_of(text: str):
    """Text → (seconds since 1970 (UTC when the text has a time-zone offset), time_only) or None."""
    r = time_info(text)
    return None if r is None else (r[0], r[1])


def time_column(texts) -> tuple[np.ndarray, bool, str] | None:
    """A text column that holds dates/times (≥ 80 % of the filled cells) → (seconds, time_only, tz), else None.
    tz: "utc" (every value had an offset, converted to UTC), "local" (none had one) or "mixed"."""
    vals, filled, ok, only, aware, naive = [], 0, 0, True, 0, 0
    for x in texts:
        s = str(x or "").strip()
        if not s:
            vals.append(math.nan)
            continue
        filled += 1
        r = time_info(s)
        if r is None:
            vals.append(math.nan)
            continue
        ok += 1
        only &= r[1]
        aware += r[2]
        naive += not r[2]
        vals.append(r[0])
    if filled < 2 or ok < 0.8 * filled:
        return None
    return np.array(vals, float), bool(only), "utc" if aware and not naive else "mixed" if aware else "local"


def _last_sunday(y: int, mo: int) -> _dt.date:
    d = _dt.date(y + (mo == 12), mo % 12 + 1, 1) - _dt.timedelta(days=1)
    return d - _dt.timedelta(days=(d.weekday() - 6) % 7)


def _nth_sunday(y: int, mo: int, n: int) -> _dt.date:
    d = _dt.date(y, mo, 1)
    return d + _dt.timedelta(days=(6 - d.weekday()) % 7 + 7 * (n - 1))


def dst_dates(y: int) -> list[tuple[_dt.date, str]]:
    """Daylight-saving changes in common use: EU (last Sunday of March / October, since 1996) and USA/Canada
    (second Sunday of March / first Sunday of November, since 2007)."""
    out = []
    if y >= 1996:
        out += [(_last_sunday(y, 3), "EU Beginn"), (_last_sunday(y, 10), "EU Ende")]
    if y >= 2007:
        out += [(_nth_sunday(y, 3, 2), "USA Beginn"), (_nth_sunday(y, 11, 1), "USA Ende")]
    return out


def dst_check(abs_s, rel_s, tz: str) -> list[str]:
    """Warnings for date/time columns read as local time without a zone (`tz` = "local" or "mixed"):
    a step back in time, a step that differs from the typical step by about one hour, or a range that covers a
    daylight-saving change (EU or USA rule, 00:00–05:00 local on that Sunday). Elapsed times across such a change
    can be off by one hour. `abs_s`: seconds since 1970 (None for times of day only), `rel_s`: elapsed seconds."""
    out = []
    if tz == "mixed":
        out.append("Zeitangaben teils mit, teils ohne Zeitzone – die Werte mit Zeitzone sind in UTC, die anderen "
                   "Ortszeit; Zeitspannen zwischen beiden sind falsch")
    if tz == "utc":
        return out
    r = np.asarray(rel_s, float)
    r = r[np.isfinite(r)]
    if r.size > 2:
        d = np.diff(r)
        back = int((d < 0).sum())
        med = float(np.median(np.abs(d))) if d.size else 0.0
        tol = max(60.0, 0.1 * med)
        hour = int(((np.abs(d - med - 3600) < tol) | (np.abs(d - med + 3600) < tol)).sum()) if 0 < med < 3000 else 0
        if back:
            out.append(f"Zeit läuft {back}-mal rückwärts – Zeitumstellung (Sommerzeit-Ende) oder falsche Reihenfolge?")
        if hour:
            out.append(f"{hour} Schritt(e) weichen um etwa 1 h vom üblichen Abstand ab – vermutlich eine "
                       f"Sommerzeit-Umstellung; die Zeitspannen danach sind um 1 h verschoben")
    if abs_s is not None:
        a = np.asarray(abs_s, float)
        a = a[np.isfinite(a)]
        if a.size > 1:
            t0, t1 = (_EPOCH + _dt.timedelta(seconds=float(a.min()))), (_EPOCH + _dt.timedelta(seconds=float(a.max())))
            for y in range(t0.year, min(t1.year, t0.year + 50) + 1):
                for day, what in dst_dates(y):
                    w0 = _dt.datetime(day.year, day.month, day.day, 0, 0)
                    if t0 <= w0 + _dt.timedelta(hours=5) and t1 >= w0:
                        out.append(f"Zeitraum überspannt eine mögliche Sommerzeit-Umstellung ({what} {day:%d.%m.%Y}) – "
                                   f"die Zeiten sind Ortszeit ohne Zeitzone, Zeitspannen darüber können um 1 h falsch sein")
                        break
                else:
                    continue
                break
    return out


def auto_unit(span_s: float) -> str:
    if span_s < 120:
        return "s"
    if span_s < 7200:
        return "min"
    if span_s < 3 * 86400:
        return "h"
    return "d"


_FACT = {"s": 1.0, "min": 60.0, "h": 3600.0, "d": 86400.0, "ms": 1e-3}


def unit_seconds(unit: str) -> float:
    """Seconds per `unit` (a time unit readable by labcalc)."""
    if unit in _FACT:
        return _FACT[unit]
    from labcalc import units as U
    f, d, _ = U.parse_unit(unit)
    return f


def elapsed(seconds: np.ndarray, time_only: bool, unit: str | None = None):
    """Seconds (since 1970, or of the day) → (elapsed in `unit`, unit, start text). Times of day that run past
    midnight are unwrapped (a step back of more than 12 h counts as the next day)."""
    a = np.array(seconds, float)
    fin = np.isfinite(a)
    if not fin.any():
        return a, unit or "s", ""
    if time_only:
        idx = np.where(fin)[0]
        add, prev = 0.0, a[idx[0]]
        for i in idx[1:]:
            if a[i] + add < prev - 43200:
                add += 86400.0
            a[i] += add
            prev = a[i]
    t0 = a[fin][0]
    rel = a - t0
    if unit is None:
        unit = auto_unit(float(np.nanmax(rel) - np.nanmin(rel)) if fin.sum() > 1 else 0.0)
    if unit not in _FACT:
        from labcalc import units as U
        f, d, _ = U.parse_unit(unit)
        fs, ds, _ = U.parse_unit("s")
        if not U.deq(d, ds):
            raise ValueError(f"{unit} ist keine Zeiteinheit")
        fac = f
    else:
        fac = _FACT[unit]
    if time_only:
        h, r = divmod(int(round(t0)), 3600)
        start = f"{h % 24:02d}:{r // 60:02d}:{r % 60:02d}"
    else:
        start = (_EPOCH + _dt.timedelta(seconds=float(t0))).isoformat(sep=" ", timespec="seconds")
    return rel / fac, unit, start
