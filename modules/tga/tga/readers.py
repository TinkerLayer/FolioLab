"""TGA-Läufe einlesen.

Unterstützt (aus den dokumentierten Textexporten; echte Gerätedateien folgen ab 18.11.2026 als Tests):
- allgemeines CSV/TXT: Trennzeichen ; , Tab oder Leerzeichen, Dezimalkomma, Kopfzeilen mit Metadaten, Spaltennamen mit
  Einheit in Klammern, eckigen Klammern, nach "/" oder in einer eigenen Einheitenzeile;
- NETZSCH Proteus ASCII-Export (Kopf "#SCHLÜSSEL: Wert", Tabellenkopf "##Temp./°C;Time/min;Mass/%");
- TA Instruments Universal Analysis "Export data" (Signalliste "Sig1 Time (min)" …, Daten nach "StartOfData") und
  TRIOS CSV/XLSX (ein Blatt je Schritt);
- METTLER TOLEDO STARe TXT (Spalten "Index t Ts Tr Value" mit Einheitenzeile "[s] [°C] [°C] [mg]");
- PerkinElmer Pyris TXT ("Unsubtracted Weight", "Sample Temp."), Shimadzu TA-60 ASCII ("[Data]", Spalte "TGA").

Intern: Zeit in min, Temperatur in °C, Masse in mg (oder in %, wenn die Datei nur Prozent enthält und keine Einwaage
nennt). Erkennt die Datei die Spalten nicht sicher, liefert ``columns`` die Spaltenliste; die Oberfläche fragt dann
nach der Zuordnung (``mapping``).
"""
from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass, field

import numpy as np


class ReadError(ValueError):
    pass


ROLE_LABEL = {"t": "Zeit", "T": "Probentemperatur", "Tprog": "Programmtemperatur", "m": "Masse", "dtg": "DTG (Gerät)",
              "hf": "Wärmestrom / DTA", "gas": "Gas", "flow": "Gasfluss", "seg": "Segment", "": "nicht verwenden"}


@dataclass
class Run:
    name: str
    T: np.ndarray                 # °C (Probentemperatur; sonst Programmtemperatur)
    m: np.ndarray                 # mg oder %
    unit: str = "mg"              # "mg" | "%"
    t: np.ndarray | None = None   # min
    m0: float | None = None       # Einwaage in mg
    meta: dict = field(default_factory=dict)
    extra: dict = field(default_factory=dict)   # Rolle -> np.ndarray (Tprog, dtg, hf, flow, seg, gas als Codes)

    def __post_init__(self):
        T = np.asarray(self.T, dtype=float).ravel()
        m = np.asarray(self.m, dtype=float).ravel()
        n = min(len(T), len(m))
        t = None if self.t is None else np.asarray(self.t, dtype=float).ravel()[:n]
        ok = np.isfinite(m[:n]) & (np.isfinite(T[:n]) | (t is not None and np.isfinite(t).all()))
        if t is not None:
            ok &= np.isfinite(t)
        self.T, self.m = T[:n][ok], m[:n][ok]
        self.t = None if t is None else t[ok]
        self.extra = {k: np.asarray(v)[:n][ok] for k, v in (self.extra or {}).items() if len(np.asarray(v)) >= n}

    def copy(self, **kw) -> "Run":
        d = dict(name=self.name, T=self.T.copy(), m=self.m.copy(), unit=self.unit,
                 t=None if self.t is None else self.t.copy(), m0=self.m0, meta=dict(self.meta),
                 extra={k: v.copy() for k, v in self.extra.items()})
        d.update(kw)
        return Run(**d)

    @property
    def has_T(self) -> bool:
        return bool(np.isfinite(self.T).sum() > 2)

    def time(self) -> np.ndarray:
        if self.t is not None:
            return self.t
        rate = self.meta.get("rate")
        if rate and self.has_T:
            return (self.T - self.T[0]) / float(rate)
        return np.arange(len(self.m), dtype=float)

    def pct(self, ref: float | None = None) -> np.ndarray:
        """Masse in % bezogen auf ref (mg bzw. %), sonst auf die Einwaage bzw. den ersten Wert."""
        if self.unit == "%":
            return self.m * (100.0 / ref if ref else 1.0)
        r = ref or self.m0 or float(np.median(self.m[:5]))
        return self.m / r * 100.0

    def mg(self) -> np.ndarray | None:
        if self.unit == "mg":
            return self.m
        ref = self.meta.get("ref_mg") or self.m0
        return self.m * ref / 100.0 if ref else None

    def describe(self) -> dict:
        T = self.T[np.isfinite(self.T)] if self.has_T else np.array([np.nan])
        tt = self.time()
        return {"name": self.name, "n": int(len(self.m)), "unit": self.unit, "m0": self.m0,
                "Tmin": float(np.min(T)), "Tmax": float(np.max(T)), "tmax": float(tt[-1] - tt[0]) if len(tt) else 0.0,
                "has_t": self.t is not None, "has_T": self.has_T, "extra": sorted(self.extra), "meta": self.meta}


# ----------------------------------------------------------------------------- Text zerlegen
# Seit DP-01 gemeinsam im SDK (`labtable`); die alten Namen bleiben für den Rest dieser Datei.
from labtable import comma_decimal as _comma_decimal  # noqa: E402
from labtable import data_block as _data_block  # noqa: E402
from labtable import decode  # noqa: E402,F401
from labtable import isnum as _isnum  # noqa: E402
from labtable import name_unit as _name_unit  # noqa: E402
from labtable import norm_unit as _norm_unit  # noqa: E402
from labtable import sniff_sep as _sep_of  # noqa: E402
from labtable import split as _split  # noqa: E402
from labtable import tofloat as _tofloat  # noqa: E402
import labtable as _LT  # noqa: E402

# TGA-eigene Einheitenliste für die Einheitenzeile (unverändert aus der Zeit vor DP-01).
_UNIT_ROW_TGA = re.compile(r"^\[?\(?(s|sec|min|h|°c|°f|k|c|mg|g|µg|ug|%|%/min|%/°c|mg/min|mw|w/g|µv|uv|ml/min|1/min|"
                           r"\-|deg\s*c|degc|°c/min|k/min)\)?\]?$", re.I)


def _is_unit_row(parts: list[str]) -> bool:
    return _LT.is_unit_row(parts, _UNIT_ROW_TGA)


# ----------------------------------------------------------------------------- Spaltenrollen
def role_of(name: str, unit: str) -> str:
    n = name.lower().strip()
    u = _norm_unit(unit)
    if re.search(r"deriv|dtg|d\s*\(?\s*(m|mass|weight)\)?\s*/\s*d|rate\s*of", n) or re.fullmatch(r"(%|mg)/(min|°c|c|k|s)", u):
        return "dtg"
    if re.search(r"heat\s*flow|wärmestrom|waermestrom|\bdsc\b|\bdta\b|\bhf\b", n) or u in ("mw", "w/g", "mw/mg", "uv"):
        return "hf"
    if re.search(r"flow|fluss|durchfluss", n) or u in ("ml/min", "sccm"):
        return "flow"
    if re.search(r"\bseg|segment|\bstep\b|schritt", n):
        return "seg"
    if re.search(r"\bgas\b|purge|atmos", n) and not u:
        return "gas"
    if re.search(r"prog|furnace|ofen|reference|\bref\b|^tr$|^t_?r\b|set\s*point|soll", n) and \
            (re.search(r"temp|^t", n) or u in ("°c", "c", "k", "°f")):
        return "Tprog"
    if re.search(r"temp|^ts$|^t_?s\b|^t\s*$", n) and u in ("°c", "c", "k", "°f", "") and not re.search(r"time|zeit", n):
        if n in ("t",) and u == "":
            return ""
        return "T"
    if u in ("°c", "c", "k", "°f"):
        return "T"
    if re.search(r"time|zeit|^t$|^tempo|^sec|^min$", n) or u in ("s", "sec", "min", "h"):
        return "t"
    if re.search(r"mass|masse|weight|gewicht|^tg\b|^tga\b|^value$|^m$", n) or u in ("mg", "g", "ug", "%"):
        if re.search(r"baseline|blank|leer|corr.*base", n):
            return ""
        return "m"
    return ""


def guess_roles(cols: list[tuple[str, str]], data: np.ndarray) -> dict:
    """Spaltenindex je Rolle; bei mehreren Kandidaten die passendste (Probentemp. vor Programmtemp., mg vor %)."""
    roles: dict[str, list[int]] = {}
    for i, (n, u) in enumerate(cols):
        r = role_of(n, u)
        if r:
            roles.setdefault(r, []).append(i)
    out = {}
    for r, idx in roles.items():
        if r == "m" and len(idx) > 1:
            def mscore(i):
                n, u = cols[i][0].lower(), _norm_unit(cols[i][1])
                return (("unsubtracted" in n) * 3 + (u == "mg") * 2 + (u == "g") + ("%" == u) * 0.5
                        - ("change" in n or "loss" in n or "verlust" in n) * 2)
            idx = sorted(idx, key=mscore, reverse=True)
        if r == "T" and len(idx) > 1:
            idx = sorted(idx, key=lambda i: ("sample" in cols[i][0].lower() or "probe" in cols[i][0].lower()
                                             or cols[i][0].lower() in ("ts", "t_s")), reverse=True)
        out[r] = idx[0]
        if r == "T" and len(idx) > 1 and "Tprog" not in roles:
            out["Tprog"] = idx[1]
    if "m" not in out or ("T" not in out and "t" not in out):
        # Spalten ohne Namen: Reihenfolge Zeit, Temperatur, Masse (häufig) bzw. Temperatur, Masse
        nc = data.shape[1]
        if nc == 2:
            out = {"T": 0, "m": 1}
        elif nc >= 3:
            out = {"t": 0, "T": 1, "m": 2}
        out["_guessed"] = True
    return out


# ----------------------------------------------------------------------------- Metadaten
_GAS = [(r"synth[a-z.]*\s*air|synthetische\s*luft|\bair\b|\bluft\b", "Luft"), (r"\bo2\b|oxygen|sauerstoff", "O₂"),
        (r"\bn2\b|nitrogen|stickstoff", "N₂"), (r"\bar\b|argon", "Ar"), (r"\bhe\b|helium", "He"),
        (r"\bco2\b", "CO₂")]


def gases_in(s: str) -> list[str]:
    """Alle genannten Gase in der Reihenfolge ihres Auftretens."""
    s = (s or "").lower()
    found = []
    for pat, g in _GAS:
        for m in re.finditer(pat, s):
            found.append((m.start(), g))
    out = []
    for _, g in sorted(found):
        if g not in out:
            out.append(g)
    return out


def gas_of(s: str) -> str:
    g = gases_in(s)
    return g[0] if g else ""


def _mass_mg(s: str) -> float | None:
    m = re.search(r"([+-]?\d+(?:[.,]\d+)?)\s*(mg|g|µg|ug)\b", s, re.I)
    if not m:
        return None
    v = float(m.group(1).replace(",", "."))
    u = m.group(2).lower()
    return v * 1000 if u == "g" else v / 1000 if u in ("µg", "ug") else v


def parse_meta(lines: list[str]) -> dict:
    meta: dict = {}
    gases = []
    for raw in lines:
        ln = raw.strip().lstrip("#").strip()
        if not ln:
            continue
        low = ln.lower()
        kv = re.split(r"\s*[:=\t]\s*|\s{2,}", ln, maxsplit=1)
        key = kv[0].lower() if len(kv) == 2 else ""
        val = kv[1].strip() if len(kv) == 2 else ln
        if re.search(r"sample\s*(mass|weight|wt)|^size$|einwaage|probenmasse|initial\s*(mass|weight)|^mass$|^weight$", key) \
                or re.match(r"(sample\s*mass|sample\s*weight|einwaage)\s*/\s*mg", key):
            v = _mass_mg(val + (" mg" if "/mg" in key.replace(" ", "") and not re.search(r"m?g\b", val) else ""))
            if v and "m0" not in meta and 0 < v < 1e5:
                meta["m0"] = v
        if "rate" not in meta:
            m = re.search(r"(\d+(?:[.,]\d+)?)\s*\(?\s*(?:k|°c|°|c|deg\.?\s*c)\s*/\s*min", low)
            if m and ("rate" in low or "heiz" in low or "range" in low or "ramp" in low or "segment" in low or "method" in low
                      or re.search(r"\bto\b|bis|→|/\d", low)):
                v = float(m.group(1).replace(",", "."))
                if 0 < v <= 1000:
                    meta["rate"] = v
        if re.search(r"gas|purge|atmos|spül", key or low):
            for g in gases_in(val):
                if g not in gases:
                    gases.append(g)
        if re.search(r"crucible|tiegel|^pan\b|pan\s*type", key):
            meta.setdefault("crucible", val[:80])
        if re.search(r"^instrument|gerät|^device|^apparatus", key):
            meta.setdefault("instrument", val[:80])
        if re.search(r"^(sample|probe|sample\s*name|probenname|identity|name)$", key) and not _mass_mg(val):
            meta.setdefault("sample", val[:120])
        if re.search(r"^(date|datum|run\s*date|date/time)", key):
            meta.setdefault("date", val[:40])
        if re.search(r"^(operator|bediener|user)", key):
            meta.setdefault("operator", val[:60])
        if re.search(r"flow|fluss", key):
            m = re.search(r"(\d+(?:[.,]\d+)?)\s*ml/min", val, re.I)
            if m:
                meta.setdefault("flow", float(m.group(1).replace(",", ".")))
    if gases:
        meta["gas"] = gases[0]
        if len(gases) > 1:
            meta["gases"] = gases
    return meta


# ----------------------------------------------------------------------------- Formate
def _ta_ua(lines: list[str]):
    """TA Universal Analysis: Signalliste im Kopf, Daten nach StartOfData ohne eigene Kopfzeile."""
    k = next(i for i, ln in enumerate(lines) if ln.strip().lower().startswith("startofdata"))
    cols = []
    for ln in lines[:k]:
        m = re.match(r"\s*sig\d+\s+(.*)$", ln, re.I)
        if m:
            cols.append(_name_unit(m.group(1)))
    return lines[:k], cols, lines[k + 1:]


def _netzsch(lines: list[str]):
    k = next(i for i, ln in enumerate(lines) if ln.startswith("##"))
    head = lines[k][2:]
    sep = ";" if ";" in head else "\t" if "\t" in head else ","
    cols = [_name_unit(h) for h in head.split(sep)]
    return lines[:k], cols, lines[k + 1:], sep


def _section(lines: list[str], tag: str):
    k = next(i for i, ln in enumerate(lines) if ln.strip().lower() == tag)
    return lines[:k], lines[k + 1:]


def parse_table(text: str, name: str, mapping: dict | None = None) -> list[Run]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    fmt = "Text/CSV"
    header_lines, cols, body, sep = [], None, lines, None
    low = [ln.strip().lower() for ln in lines[:400]]
    if any(x.startswith("startofdata") for x in low) and any(re.match(r"sig\d+\s", x) for x in low):
        header_lines, cols, body = _ta_ua(lines)
        fmt = "TA Universal Analysis"
    elif any(ln.startswith("##") for ln in lines[:400]) and any(ln.startswith("#") and not ln.startswith("##") for ln in lines[:200]):
        header_lines, cols, body, sep = _netzsch(lines)
        fmt = "NETZSCH Proteus ASCII"
    elif "[data]" in low:
        header_lines, body = _section(lines, "[data]")
        fmt = "Shimadzu ASCII"
    if sep is None:
        sep = _sep_of(body)
    i0, i1, ncol = _data_block(body, sep)
    if i1 - i0 < 5:
        raise ReadError(f"{name}: keine Messwerttabelle gefunden (Trennzeichen, Kopfzeilen prüfen)")
    dec_comma = _comma_decimal(body[i0:i1], sep)
    pre = body[:i0]
    if cols is None:
        # Kopfzeile(n) direkt über den Daten: Namen, evtl. Einheitenzeile
        cand = [ln for ln in pre if ln.strip()][-3:]
        cols = [("", "")] * ncol
        names, units = None, None
        for ln in reversed(cand):
            parts = _split(ln, sep)
            if units is None and _is_unit_row(parts) and len(parts) >= ncol - 1:
                units = parts
                continue
            if len(parts) >= ncol - 1 and sum(_isnum(p) for p in parts) <= 1:
                names = parts
                break
        if names:
            cols = []
            for k_ in range(ncol):
                n_, u_ = _name_unit(names[k_]) if k_ < len(names) else ("", "")
                if units and k_ < len(units) and not u_:
                    u_ = units[k_].strip("[]() ")
                cols.append((n_, u_))
            if re.search(r"\bts\b", " ".join(n for n, _ in cols).lower()) and "index" in cols[0][0].lower():
                fmt = "METTLER STARe"
            if any("unsubtracted" in n.lower() for n, _ in cols):
                fmt = "PerkinElmer Pyris"
        header_lines = header_lines + pre
    rows = []
    for ln in body[i0:i1]:
        parts = _split(ln, sep)
        rows.append([_tofloat(p, dec_comma) for p in parts[:ncol]] + [math.nan] * (ncol - len(parts)))
    data = np.array(rows, dtype=float)
    if len(cols) < data.shape[1]:
        cols = list(cols) + [("", "")] * (data.shape[1] - len(cols))
    cols = cols[:data.shape[1]]
    # Textspalten (z. B. Gas) aus den Rohzeilen
    texts = {}
    for k_, (n_, _) in enumerate(cols):
        if np.isnan(data[:, k_]).all():
            texts[k_] = [(_split(ln, sep) + [""] * ncol)[k_] for ln in body[i0:i1]]
    mp = {k: v for k, v in (mapping or {}).items() if k in ROLE_LABEL and k and v not in (None, "")}
    unit_over = {k[:-5]: str(v) for k, v in (mapping or {}).items() if k.endswith("_unit") and v}
    roles = mp or guess_roles(cols, data)
    guessed = bool(roles.pop("_guessed", False)) and not mp
    meta = parse_meta(header_lines)
    meta["format"] = fmt
    meta["file"] = name
    meta["header"] = [ln.strip() for ln in header_lines if ln.strip()][:80]
    meta["columns"] = [{"name": n_, "unit": u_, "role": next((r for r, i in roles.items() if i == k_), "")}
                       for k_, (n_, u_) in enumerate(cols)]
    if guessed:
        meta["guessed"] = True
    return [build_run(data, cols, roles, meta, name, texts, unit_over)]


def _col(data, roles, r):
    i = roles.get(r)
    if i is None or i == "" or int(i) < 0 or int(i) >= data.shape[1]:
        return None
    return data[:, int(i)].astype(float)


def build_run(data, cols, roles, meta, name, texts=None, unit_over=None) -> Run:
    roles = {k: int(v) for k, v in roles.items() if v not in (None, "") and str(v).lstrip("-").isdigit() and int(v) >= 0}
    units = {r: _norm_unit(cols[i][1]) if i < len(cols) else "" for r, i in roles.items()}
    for k, v in (unit_over or {}).items():
        units[k] = _norm_unit(v)
    m = _col(data, roles, "m")
    if m is None:
        raise ReadError(f"{name}: keine Massenspalte erkannt; bitte Spalten zuordnen")
    T = _col(data, roles, "T")
    T_role = "T"
    if T is None:
        T = _col(data, roles, "Tprog")
        T_role = "Tprog"
    t = _col(data, roles, "t")
    if T is None and t is None:
        raise ReadError(f"{name}: weder Temperatur- noch Zeitspalte erkannt; bitte Spalten zuordnen")
    # Einheiten
    tu = units.get("t", "")
    if t is not None:
        if tu in ("s", "sec") or (not tu and np.nanmax(t) > 600 and meta.get("format") == "METTLER STARe"):
            t = t / 60.0
        elif tu == "h":
            t = t * 60.0
        elif tu == "ms":
            t = t / 60000.0
    def temp(a, u):
        if a is None:
            return None
        if u == "k":
            return a - 273.15
        if u == "°f":
            return (a - 32) / 1.8
        return a
    T = temp(T, units.get(T_role, ""))
    mu = units.get("m", "")
    unit = "mg"
    if mu == "%" or (not mu and 50 <= np.nanmax(m) <= 120 and np.nanmin(m) >= -5 and not meta.get("m0")):
        unit = "%"
    elif mu == "g":
        m = m * 1000
    elif mu == "ug":
        m = m / 1000
    mname = cols[roles["m"]][0].lower() if roles.get("m", -1) < len(cols) else ""
    m0 = meta.get("m0")
    if unit == "mg" and re.search(r"change|loss|verlust|delta|änderung", mname) and abs(np.nanmedian(m[:5])) < 0.05 * abs(np.nanmax(np.abs(m)) or 1):
        if not m0:
            raise ReadError(f"{name}: Spalte enthält Massenänderung; Einwaage fehlt im Kopf")
        m = m0 + m
    if unit == "%" and m0:
        m = m * m0 / 100.0
        unit = "mg"
    if unit == "mg" and not m0:
        m0 = float(np.nanmedian(m[: max(1, min(5, len(m)))]))
        meta["m0_from"] = "erster Messwert"
    extra = {}
    for r in ("Tprog", "dtg", "hf", "flow", "seg"):
        a = _col(data, roles, r)
        if a is not None and r != T_role:
            extra[r] = temp(a, units.get(r, "")) if r == "Tprog" else a
    if "hf" in extra:                                   # Einheit des Wärmestroms für die DSC-Auswertung (TGA-03)
        hu = {"mw": "mW", "w/g": "W/g", "mw/mg": "W/g", "uv": "uV", "µv": "uV"}.get(units.get("hf", "").lower())
        if hu:
            meta["hf_unit"] = hu
    gi = roles.get("gas")
    if texts and gi in texts:
        g = [gas_of(s) or s.strip() for s in texts[gi]]
        names = list(dict.fromkeys(g))
        extra["gas"] = np.array([names.index(x) for x in g], dtype=float)
        meta["gas_names"] = names
    if T is None:
        T = np.full(len(m), np.nan)
    sample = meta.get("sample") or re.sub(r"\.[^.]+$", "", name)
    run = Run(sample[:120], T, m, unit, t, m0, meta, extra)
    if len(run.m) < 5:
        raise ReadError(f"{name}: zu wenige gültige Messpunkte")
    if run.has_T and (np.nanmin(run.T) < -200 or np.nanmax(run.T) > 2500):
        raise ReadError(f"{name}: Temperaturwerte unplausibel ({np.nanmin(run.T):.0f} … {np.nanmax(run.T):.0f} °C); "
                        "Spalten prüfen")
    if run.has_T and "rate" not in run.meta and run.t is not None and len(run.t) > 10:
        r = heating_rate(run)
        if r:
            run.meta["rate"] = r
    return run


def heating_rate(run: Run) -> float | None:
    """Median der Heizrate im dynamischen Teil, gerundet auf 0,1 K/min."""
    if run.t is None or not run.has_T:
        return None
    dt = np.diff(run.t)
    dT = np.diff(run.T)
    ok = dt > 0
    if ok.sum() < 5:
        return None
    r = dT[ok] / dt[ok]
    r = r[np.abs(r) > 0.3]
    if len(r) < 5:
        return None
    v = float(np.median(r))
    return round(v, 1) if v > 0 else None


def _xlsx(data: bytes, name: str) -> list[Run]:
    try:
        import openpyxl
    except ImportError as e:  # pragma: no cover
        raise ReadError("Für .xlsx wird openpyxl gebraucht") from e
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    runs = []
    for ws in wb.worksheets:
        lines = []
        for row in ws.iter_rows(values_only=True):
            if row is None:
                continue
            lines.append("\t".join("" if v is None else (repr(v) if isinstance(v, float) else str(v)) for v in row))
        try:
            runs += parse_table("\n".join(lines), f"{name} [{ws.title}]")
        except ReadError:
            continue
    if not runs:
        raise ReadError(f"{name}: in keinem Tabellenblatt eine Messwerttabelle gefunden")
    if len(runs) > 1 and all(r.t is not None for r in runs) and len({r.unit for r in runs}) == 1:
        # TRIOS: ein Blatt je Methodenschritt -> zu einem Lauf zusammensetzen
        first = runs[0]
        T = np.concatenate([r.T for r in runs])
        m = np.concatenate([r.m for r in runs])
        t = np.concatenate([r.t for r in runs])
        seg = np.concatenate([np.full(len(r.m), k + 1.0) for k, r in enumerate(runs)])
        meta = dict(first.meta, format="TA TRIOS (XLSX)", sheets=len(runs))
        return [Run(first.name, T, m, first.unit, t, first.m0, meta, {"seg": seg})]
    return runs


# ----------------------------------------------------------------------------- NETZSCH .ngb (TGA-02, optional)
NGB_EXT = (".ngb", ".ngb-ss3", ".ngb-bs3", ".ngb-ds3")
# pyngb-Spaltenname -> (Rolle, Vorgabe-Einheit). Vorgaben aus pyngb 0.6.1 `constants.DEFAULT_COLUMN_METADATA`
# (Zeit s, Temperaturen °C, Masse mg, DSC µV, DTG mg/min, Fluss ml/min); die in der Datei stehende Einheit hat Vorrang.
NGB_COLS = {"time": ("t", "s"), "sample_temperature": ("T", "°C"), "program_temperature": ("Tprog", "°C"),
            "furnace_temperature": ("", "°C"), "mass": ("m", "mg"), "dsc_signal": ("hf", "µV"),
            "dtg": ("dtg", "mg/min"), "purge_flow_1": ("flow", "ml/min"), "purge_flow": ("flow", "ml/min"),
            "segment": ("seg", "")}


def ngb_available() -> bool:
    try:
        import pyngb  # noqa: F401
        return True
    except ImportError:
        return False


def _ngb_columns(table) -> dict[str, np.ndarray]:
    """pyarrow-Tabelle oder polars-DataFrame -> {Spaltenname: Array}."""
    out = {}
    names = list(getattr(table, "column_names", None) or getattr(table, "columns", []) or [])
    for n in names:
        col = table.column(n) if hasattr(table, "column") else table[n]
        try:
            a = col.to_numpy(zero_copy_only=False)          # pyarrow
        except TypeError:
            a = col.to_numpy()                              # polars, numpy-artige Spalten
        try:
            out[str(n)] = np.asarray(a, dtype=float)
        except (TypeError, ValueError):
            continue                       # Textspalten (z. B. Gasname) werden nicht gebraucht
    return out


def _ngb_meta(md) -> dict:
    if isinstance(md, (bytes, str)):
        import json
        try:
            md = json.loads(md)
        except ValueError:
            md = {}
    return md if isinstance(md, dict) else {}


def _ngb_units(table) -> dict[str, str]:
    """Einheiten je Spalte: über `pyngb.get_column_units` (öffentliche API), sonst aus den Feld-Metadaten."""
    out = {}
    schema = getattr(table, "schema", None)
    try:
        import pyngb
        for n in (getattr(table, "column_names", None) or []):
            u = pyngb.get_column_units(table, n)
            if isinstance(u, str) and u.strip():
                out[str(n)] = u.strip()
        if out:
            return out
    except Exception:  # noqa: BLE001 - Ersatzmodul in Tests oder ältere pyngb-Version: Feld-Metadaten lesen
        out = {}
    for f in (schema if schema is not None and hasattr(schema, "__iter__") else []):
        md = getattr(f, "metadata", None) or {}
        raw = md.get(b"units") or md.get("units")
        if raw is None:
            blob = md.get(b"column_metadata") or md.get("column_metadata")
            if blob:
                import json
                try:
                    raw = json.loads(blob).get("units")
                except (ValueError, AttributeError):
                    raw = None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")
        if isinstance(raw, str) and raw.strip().strip('"'):
            out[str(f.name)] = raw.strip().strip('"')
    return out


def ngb_run(cols: dict[str, np.ndarray], md: dict, name: str, units: dict | None = None) -> Run:
    """Lauf aus den von pyngb gelieferten Spalten und Metadaten."""
    md = _ngb_meta(md)
    units = units or {}
    keys = [k for k in cols if k.lower() in NGB_COLS and NGB_COLS[k.lower()][0]]
    if not any(NGB_COLS[k.lower()][0] == "m" for k in keys):
        raise ReadError(f"{name}: .ngb enthält keine Massenspalte (nur {', '.join(cols) or 'nichts'})")
    n = min(len(cols[k]) for k in keys)
    data = np.column_stack([cols[k][:n] for k in keys])
    coldef = [(k, units.get(k) or NGB_COLS[k.lower()][1]) for k in keys]
    roles = {}
    for i, k in enumerate(keys):
        roles.setdefault(NGB_COLS[k.lower()][0], i)
    meta = {"format": "NETZSCH NGB (pyngb)"}
    m0 = md.get("sample_mass")
    try:
        if m0 not in (None, "") and float(m0) > 0:
            meta["m0"] = float(m0)
    except (TypeError, ValueError):
        pass
    for src, dst in (("sample_name", "sample"), ("instrument", "instrument"), ("crucible_type", "crucible"),
                     ("operator", "operator"), ("date_performed", "date")):
        if md.get(src):
            meta[dst] = str(md[src])[:120]
    run = build_run(data, coldef, roles, meta, name)
    run.m0 = run.m0 or meta.get("m0")
    return run


def _ngb(data: bytes, name: str) -> list[Run]:
    try:
        import pyngb
    except ImportError as e:
        raise ReadError(f"{name}: NETZSCH-Binärformat (.ngb). Direkt lesbar mit dem optionalen Paket pyngb "
                        "(„pip install pyngb“); sonst in Proteus als ASCII/CSV exportieren.") from e
    import tempfile
    from pathlib import Path
    suffix = Path(name).suffix.lower() or ".ngb-ss3"
    corrected = suffix == ".ngb-ds3"       # Probe + Korrektur in einer Datei: wie Proteus korrigiert anzeigen
    with tempfile.TemporaryDirectory(prefix="tga_ngb_") as d:
        p = Path(d) / ("lauf" + suffix)
        p.write_bytes(data)
        try:
            try:
                res = (pyngb.read_ngb(str(p), return_metadata=True, run="corrected") if corrected
                       else pyngb.read_ngb(str(p), return_metadata=True))
            except TypeError:
                res = pyngb.read_ngb(str(p))
        except Exception as e:  # noqa: BLE001 - Fremdpaket: jede Ausnahme als Lesefehler melden
            raise ReadError(f"{name}: pyngb konnte die Datei nicht lesen ({type(e).__name__}: {e})") from e
    if isinstance(res, tuple):
        md, table = res
    else:
        table = res
        sm = getattr(getattr(table, "schema", None), "metadata", None) or {}
        md = sm.get(b"file_metadata") or sm.get("file_metadata") or {}
    run = ngb_run(_ngb_columns(table), md, name, _ngb_units(table))
    if corrected:
        run.meta["ngb_run"] = "korrigiert (Probe − eingebettete Korrektur, wie in Proteus)"
    return [run]


def load_bytes(data: bytes, name: str, mapping: dict | None = None) -> list[Run]:
    if not data:
        raise ReadError(f"{name}: Datei ist leer")
    if data[:1] == b"{" and b"folio-tga-dataset/1" in data[:200]:      # DP-13: Lauf aus einem Datensatz
        from .dataset import read_raw
        return read_raw(data, name, mapping)
    low = name.lower()
    if low.endswith((".xlsx", ".xlsm")):
        return _xlsx(data, name)
    if low.endswith(NGB_EXT):
        return _ngb(data, name)
    if low.endswith((".001", ".tri")) or data[:2] == b"PK" and not low.endswith(".xlsx"):
        raise ReadError(f"{name}: Binärformat des Geräts. Bitte in der Gerätesoftware als Text (ASCII/CSV) exportieren.")
    return parse_table(decode(data), name, mapping)


# ----------------------------------------------------------------------------- Schreiben
def to_csv(run: Run, extra_meta: dict | None = None) -> str:
    """Eigenes Textformat (liest dieses Modul wieder ein): Kopf mit '#', dann Zeit;Temperatur;Masse."""
    lines = [f"# Probe: {run.name}"]
    if run.m0:
        lines.append(f"# Einwaage: {run.m0:.5g} mg")
    for k in ("rate", "gas", "crucible", "instrument", "origin"):
        v = run.meta.get(k)
        if v not in (None, ""):
            lab = {"rate": "Heizrate", "gas": "Gas", "crucible": "Tiegel", "instrument": "Gerät", "origin": "Herkunft"}[k]
            lines.append(f"# {lab}: {v}{' K/min' if k == 'rate' else ''}")
    for k, v in (extra_meta or {}).items():
        lines.append(f"# {k}: {v}")
    t = run.time()
    unit = run.unit
    lines.append(f"Zeit/min;Temperatur/°C;Masse/{unit}")
    for a, b, c in zip(t, run.T, run.m):
        lines.append(f"{a:.5f};{'' if not math.isfinite(b) else f'{b:.4f}'};{c:.6g}")
    return "\n".join(lines) + "\n"
