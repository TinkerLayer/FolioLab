"""Cleaning steps and outlier flags on datasets (DP-07, DP-08).

Every step works on a working copy (`Table`) of a dataset and is recorded in the recipe of a derived dataset, so
replaying the recipe gives the same dataset. Each step reports rows before/after and flags before/after.

DP-07  trim, filter, sort, drop_empty, duplicates (flags), replicates (mean, s, n, SE), join (align a second dataset
       on x, linear interpolation labelled), smooth (Savitzky–Golay, labelled). Unit conversions and formula columns
       are in `datasets.derive`.
DP-08  outliers (Grubbs, Dixon Q, Tukey/IQR, Hampel/MAD, fit residual) → `outlier` flags with rule and source; no flag
       removes a row. `exclude` is the separate, recorded decision (flag `excluded` with a reason).
       `checks(ds)` gives the check chips (rows read/used/excluded, missing, monotonic x, gaps, n per group,
       impossible values, units).
"""
from __future__ import annotations

import math
import re

import numpy as np

import labdataset as DS
from labcalc import units as U

MAX_FLAGS = 50_000
MAX_INTERP_FLAGS = 20_000          # "interpolated" flags per joined column; more are reported in the step text


class CleanError(ValueError):
    pass


# ----------------------------------------------------------------------------- sources
SOURCES = {
    "grubbs": {"key": "grubbs1969", "type": "article", "authors": "Grubbs, Frank E.", "year": "1969",
               "title": "Procedures for Detecting Outlying Observations in Samples", "container": "Technometrics",
               "volume": "11", "pages": "1-21", "doi": "10.1080/00401706.1969.10490657"},
    "dixon": {"key": "rorabacher1991", "type": "article", "authors": "Rorabacher, David B.", "year": "1991",
              "title": "Statistical Treatment for Rejection of Deviant Values: Critical Values of Dixon's Q Parameter "
                       "and Related Subrange Ratios at the 95% Confidence Level",
              "container": "Analytical Chemistry", "volume": "63", "pages": "139-146", "doi": "10.1021/ac00002a010"},
    "dixon0": {"key": "dean1951", "type": "article", "authors": "Dean, R. B.; Dixon, W. J.", "year": "1951",
               "title": "Simplified Statistics for Small Numbers of Observations", "container": "Analytical Chemistry",
               "volume": "23", "pages": "636-638", "doi": "10.1021/ac60052a025"},
    "iqr": {"key": "tukey1977", "type": "book", "authors": "Tukey, John W.", "year": "1977",
            "title": "Exploratory Data Analysis", "container": "Addison-Wesley"},
    # the quartiles are numpy's linear interpolation = definition 7 in this paper (not Tukey's hinges)
    "quantile7": {"key": "hyndman1996", "type": "article", "authors": "Hyndman, Rob J.; Fan, Yanan", "year": "1996",
                  "title": "Sample Quantiles in Statistical Packages", "container": "The American Statistician",
                  "volume": "50", "pages": "361-365"},
    "hampel": {"key": "hampel1974", "type": "article", "authors": "Hampel, Frank R.", "year": "1974",
               "title": "The Influence Curve and Its Role in Robust Estimation",
               "container": "Journal of the American Statistical Association", "volume": "69", "pages": "383-393",
               "doi": "10.1080/01621459.1974.10482962"},
    "nist": {"key": "nist-esh", "type": "web", "authors": "NIST/SEMATECH", "accessed": "2026-11-17",
             "title": "e-Handbook of Statistical Methods", "url": "https://www.itl.nist.gov/div898/handbook/",
             "doi": "10.18434/M32189"},
    "savgol": {"key": "savitzky1964", "type": "article", "authors": "Savitzky, Abraham; Golay, Marcel J. E.",
               "year": "1964", "title": "Smoothing and Differentiation of Data by Simplified Least Squares Procedures",
               "container": "Analytical Chemistry", "volume": "36", "pages": "1627-1639", "doi": "10.1021/ac60214a047"},
}
# The fit-residual test has no cited source: the externally studentised residual is a standard regression diagnostic
# and its threshold k is a rule of thumb (methods page, "Fit residual").
METHOD_SOURCES = {"grubbs": ["grubbs", "nist"], "dixon": ["dixon0", "dixon"], "iqr": ["iqr", "quantile7"],
                  "hampel": ["hampel"], "residual": [], "smooth": ["savgol"]}


def _de(x, nd=3) -> str:
    return f"{x:.{nd}g}".replace(".", ",") if isinstance(x, float) and math.isfinite(x) else str(x)


# ----------------------------------------------------------------------------- working copy
class Table:
    def __init__(self, ds: DS.Dataset):
        self.cols = [dict(c) for c in ds.columns]
        self.data = {c["key"]: np.array(ds.data[c["key"]], copy=True) for c in self.cols}
        self.flags = [dict(f) for f in ds.header.get("flags") or []]
        self.conditions = dict(ds.header.get("conditions") or {})
        self.n = ds.rows

    def find(self, key) -> tuple[int, dict]:
        for i, c in enumerate(self.cols):
            if c["key"] == key:
                return i, c
        raise CleanError(f"Spalte „{key}“ nicht im Datensatz")

    def num(self, key) -> np.ndarray:
        _, c = self.find(key)
        if c["dtype"] != "number":
            raise CleanError(f"Spalte „{c['name']}“ ist Text")
        return self.data[key]

    def used(self) -> np.ndarray:
        m = np.ones(self.n, bool)
        for f in self.flags:
            if f.get("excluded"):
                m[f["row"]] = False
        return m

    def take(self, idx) -> None:
        """Keep rows `idx` (in this order); flags follow their rows, flags of dropped rows go."""
        idx = np.asarray(idx, int)
        pos = {int(o): i for i, o in enumerate(idx)}
        for k in self.data:
            self.data[k] = self.data[k][idx]
        self.flags = [{**f, "row": pos[f["row"]]} for f in self.flags if f["row"] in pos]
        self.n = len(idx)

    def add_flag(self, f: dict) -> None:
        if len(self.flags) >= MAX_FLAGS:
            raise CleanError(f"Mehr als {MAX_FLAGS} Markierungen – Regel enger fassen")
        self.flags.append(f)

    def taken(self) -> list[str]:
        return [c["key"] for c in self.cols]

    def dataset(self, title: str, prov: dict) -> DS.Dataset:
        keys = set(self.taken())
        for c in self.cols:
            if c.get("u") and c["u"] not in keys:
                c.pop("u")
        flags = [f for f in self.flags if not f.get("col") or f["col"] in keys]
        flags.sort(key=lambda f: (f["row"], f.get("col") or ""))
        try:
            return DS.Dataset({"title": title, "columns": self.cols, "conditions": self.conditions, "flags": flags,
                               "provenance": prov}, {c["key"]: self.data[c["key"]] for c in self.cols})
        except DS.DatasetError as e:
            raise CleanError(str(e)) from None


def _keys(t: Table, keys, what: str) -> list[str]:
    out = []
    for k in keys or []:
        t.find(str(k))
        out.append(str(k))
    if not out and what:
        raise CleanError(f"{what}: keine Spalte gewählt")
    return out


def _value(t: Table, key: str, v):
    """A number typed in the column unit (decimal comma allowed)."""
    try:
        return float(str(v).replace(",", ".").replace("−", "-").strip())
    except (TypeError, ValueError):
        raise CleanError(f"„{v}“ ist keine Zahl ({t.find(key)[1]['name']})") from None


# ----------------------------------------------------------------------------- DP-07 rows
def op_trim(t: Table, op: dict, ctx=None) -> str:
    first = int(op.get("first") or 1)
    last = int(op.get("last") or t.n)
    if first < 1 or last < first:
        raise CleanError("Zeilenbereich ungültig (von ≥ 1, bis ≥ von)")
    t.take(np.arange(first - 1, min(last, t.n)))
    return f"Zeilen {first}–{min(last, first - 1 + t.n)} behalten"


_CMP = {"<": np.less, "<=": np.less_equal, ">": np.greater, ">=": np.greater_equal, "==": np.equal, "!=": np.not_equal}


def op_filter(t: Table, op: dict, ctx=None) -> str:
    key, cmp = str(op.get("col") or ""), str(op.get("cmp") or "")
    _, c = t.find(key)
    if c["dtype"] == "text":
        a = t.data[key].astype(str)
        val = str(op.get("value") or "")
        if cmp == "==":
            m = a == val
        elif cmp == "!=":
            m = a != val
        elif cmp == "contains":
            m = np.char.find(np.char.lower(a), val.lower()) >= 0
        elif cmp == "notempty":
            m = a != ""
        else:
            raise CleanError(f"Vergleich {cmp} für Text nicht möglich")
        txt = f"„{c['name']}“ {cmp} „{val}“"
    else:
        a = t.data[key]
        if cmp == "notnan":
            m, txt = np.isfinite(a), f"„{c['name']}“ hat einen Wert"
        elif cmp == "between":
            lo, hi = sorted((_value(t, key, op.get("value")), _value(t, key, op.get("value2"))))
            m = np.isfinite(a) & (a >= lo) & (a <= hi)
            txt = f"{_de(lo)} ≤ „{c['name']}“ ≤ {_de(hi)} {c.get('unit') or ''}".rstrip()
        elif cmp in _CMP:
            val = _value(t, key, op.get("value"))
            with np.errstate(invalid="ignore"):
                m = np.isfinite(a) & _CMP[cmp](a, val)
            txt = f"„{c['name']}“ {cmp} {_de(val)} {c.get('unit') or ''}".rstrip()
        else:
            raise CleanError(f"Vergleich „{cmp}“ unbekannt")
    t.take(np.where(m)[0])
    return "Zeilen mit " + txt + " behalten"


def op_sort(t: Table, op: dict, ctx=None) -> str:
    key = str(op.get("col") or "")
    _, c = t.find(key)
    a = t.data[key]
    if c["dtype"] == "number":
        nan = ~np.isfinite(a)
        k = np.where(nan, 0.0, -a if op.get("desc") else a)
        idx = np.lexsort((k, nan))                       # stable; missing values last
    else:
        idx = np.argsort(a.astype(str), kind="stable")
        if op.get("desc"):
            idx = idx[::-1]
    t.take(idx)
    return f"Nach „{c['name']}“ {'absteigend' if op.get('desc') else 'aufsteigend'} sortiert"


def _empty(t: Table, key) -> np.ndarray:
    _, c = t.find(key)
    a = t.data[key]
    return ~np.isfinite(a) if c["dtype"] == "number" else (a.astype(str) == "")


def op_drop_empty(t: Table, op: dict, ctx=None) -> str:
    keys = _keys(t, op.get("cols"), "") or [c["key"] for c in t.cols if c["dtype"] == "number"]
    m = np.ones(t.n, bool)
    for k in keys:
        m &= _empty(t, k)
    t.take(np.where(~m)[0])
    return "Leere Zeilen entfernt (" + ", ".join(t.find(k)[1]["name"] for k in keys[:6]) + ")"


def op_duplicates(t: Table, op: dict, ctx=None) -> str:
    keys = _keys(t, op.get("cols"), "") or t.taken()
    seen, n = {}, 0
    cols = [t.data[k] for k in keys]
    for i in range(t.n):
        sig = tuple(("nan" if isinstance(x, float) and math.isnan(x) else x)
                    for x in (a[i].item() if hasattr(a[i], "item") else a[i] for a in cols))
        if sig in seen:
            t.add_flag({"row": i, "code": "duplicate", "rule": "gleiche Werte in " + ", ".join(keys)[:200],
                        "reason": f"wie Zeile {seen[sig] + 1}"})
            n += 1
        else:
            seen[sig] = i
    return f"Doppelte Zeilen markiert ({n})"


def op_replicates(t: Table, op: dict, ctx=None) -> str:
    """Rows with equal values in `by` → one row: mean, standard deviation s (n − 1), n and standard error s/√n."""
    by = _keys(t, op.get("by"), "Mitteln: Gruppenspalte")
    # default: every number column except the uncertainties (the mean gets its standard error as uncertainty)
    vals = _keys(t, op.get("cols"), "") or [c["key"] for c in t.cols if c["dtype"] == "number" and c["key"] not in by
                                             and c.get("role") != "uncertainty"]
    for k in vals:
        t.num(k)
        if k in by:
            raise CleanError(f"„{k}“ ist Gruppen- und Wertspalte")
    used = t.used()
    groups, order = {}, []
    for i in range(t.n):
        sig = tuple(t.data[k][i].item() if hasattr(t.data[k][i], "item") else t.data[k][i] for k in by)
        sig = tuple("nan" if isinstance(x, float) and math.isnan(x) else x for x in sig)
        if sig not in groups:
            groups[sig] = []
            order.append(sig)
        if used[i]:
            groups[sig].append(i)
    first = [next(iter(groups[g]), None) for g in order]
    keep = [(g, f) for g, f in zip(order, first) if f is not None]
    cols, data = [], {}
    for k in by:
        _, c = t.find(k)
        cols.append(dict(c))
        data[k] = t.data[k][[f for _, f in keep]]
    taken = set(by)
    for k in vals:
        _, c = t.find(k)
        a = t.data[k]
        mean, s, n = [], [], []
        for g, _ in keep:
            v = a[groups[g]]
            v = v[np.isfinite(v)]
            n.append(v.size)
            mean.append(v.mean() if v.size else math.nan)
            s.append(v.std(ddof=1) if v.size > 1 else math.nan)
        mean, s, n = np.array(mean), np.array(s), np.array(n, float)
        with np.errstate(invalid="ignore", divide="ignore"):
            se = s / np.sqrt(n)
        ks, kn, kse = (DS.safe_key(f"{k}_{x}", taken | {k}) for x in ("s", "n", "se"))
        taken |= {k, ks, kn, kse}
        mc = {kk: vv for kk, vv in c.items() if kk not in ("u", "note")}
        mc.update(note=f"Mittelwert je Gruppe ({', '.join(by)})"[:200], u=kse)
        cols += [mc,
                 {"key": ks, "name": f"s({c['name']})"[:120], "unit": c.get("unit", ""), "kind": c.get("kind", ""),
                  "dtype": "number", "role": "", "note": "Standardabweichung (n − 1)"},
                 {"key": kn, "name": f"n({c['name']})"[:120], "unit": "", "dtype": "number", "role": "",
                  "note": "Anzahl Werte je Gruppe"},
                 {"key": kse, "name": f"SE({c['name']})"[:120], "unit": c.get("unit", ""), "kind": c.get("kind", ""),
                  "dtype": "number", "role": "uncertainty", "note": "Standardfehler s/√n", "u_type": "se"}]
        if (c.get("kind") or "") in ("temperature",):              # a spread of temperatures is a difference
            cols[-3]["kind"] = cols[-1]["kind"] = "temp_diff"
        data.update({k: mean, ks: s, kn: n, kse: se})
    rows_in, nex = t.n, int((~used).sum())
    # Flags of the averaged rows go to the mean (excluded rows were left out above): a mean that contains a flagged
    # value (outlier not excluded, value = detection limit, interpolated, converted …) carries a flag of the same code
    # on the same column, naming the source rows. Flags of cells that held no value (missing, unreadable) only show in
    # n; flags of columns that are not kept are dropped and counted.
    vset, bset = set(vals), set(by)
    new_flags, dropped = {}, 0
    for gi, (g, _) in enumerate(keep):
        members = set(groups[g])
        for f in t.flags:
            if f["row"] not in members or f.get("excluded"):
                continue
            c = f.get("col")
            if c and c not in vset and c not in bset:
                dropped += 1
                continue
            if f["code"] in ("missing", "parse_error") or (c in vset and not np.isfinite(t.data[c][f["row"]])):
                continue
            rec = new_flags.setdefault((gi, c or "", f["code"]), {"rows": [], "rules": []})
            rec["rows"].append(f["row"] + 1)
            if f.get("rule") and f["rule"] not in rec["rules"]:
                rec["rules"].append(f["rule"])
    flags = []
    for (gi, c, code), rec in sorted(new_flags.items()):
        rows = sorted(set(rec["rows"]))
        flags.append({"row": gi, **({"col": c} if c else {}), "code": code,
                      "rule": ("Mittelwert enthält markierte Werte" + (f" ({rec['rules'][0]})" if rec["rules"] else ""))[:300],
                      "reason": (f"aus Zeile(n) {', '.join(map(str, rows[:20]))}" + (" …" if len(rows) > 20 else ""))[:300]})
    t.cols, t.data, t.n, t.flags = cols, data, len(keep), flags
    return (f"Wiederholungen gemittelt: {len(keep)} Gruppen aus {rows_in} Zeilen" +
            (f"; {nex} ausgeschlossene Zeile(n) vor dem Mitteln weggelassen" if nex else "") +
            (f"; {len(flags)} Markierung(en) auf die Mittelwerte übertragen" if flags else "") +
            (f"; {dropped} Markierung(en) nicht gemittelter Spalten entfallen" if dropped else ""))


# ----------------------------------------------------------------------------- DP-07 join, smooth
def op_join(t: Table, op: dict, ctx=None) -> str:
    """Columns of a second dataset at the x values of this one (linear interpolation, labelled; no extrapolation)."""
    if ctx is None or not getattr(ctx, "load", None):
        raise CleanError("Verbinden: zweiter Datensatz nicht erreichbar")
    sid = str(op.get("share") or "")
    if not sid:
        raise CleanError("Verbinden: Datensatz wählen")
    other, env = ctx.load(sid, op.get("version") if op.get("mode") == "pin" else None)
    xk, xk2 = str(op.get("x") or ""), str(op.get("x2") or "")
    _, cx = t.find(xk)
    x = t.num(xk)
    try:
        x2 = other.in_unit(xk2, cx.get("unit") or "", used_only=True)
    except (DS.DatasetError, U.UnitError) as e:
        raise CleanError(f"Verbinden: {e}") from None
    keys = [str(k) for k in op.get("cols") or []]
    if not keys:
        raise CleanError("Verbinden: Spalten des zweiten Datensatzes wählen")
    title = other.header.get("title") or sid
    ver = env.get("version")
    if isinstance(getattr(ctx, "inputs", None), list):            # the version actually used (also for live joins)
        ctx.inputs.append({"share": sid, "version": ver, "title": str(title)[:160]})
    order = np.argsort(x2, kind="stable")
    x2s = x2[order]
    exact = np.isin(x, x2s)
    lo, hi = (np.nanmin(x2s), np.nanmax(x2s)) if np.isfinite(x2s).any() else (math.nan, math.nan)
    added, cut = [], []
    for k in keys:
        try:
            c2 = other.col(k)
        except DS.DatasetError as e:
            raise CleanError(str(e)) from None
        if c2["dtype"] != "number":
            raise CleanError(f"Verbinden: „{c2['name']}“ ist Text")
        y2 = other.values(k, used_only=True)[order]
        ok = np.isfinite(x2s) & np.isfinite(y2)
        if ok.sum() < 2:
            raise CleanError(f"Verbinden: „{c2['name']}“ hat zu wenige Werte")
        xs, ys = x2s[ok], y2[ok]
        xs, first = np.unique(xs, return_index=True)          # equal x: the first value
        ys = ys[first]
        y = np.interp(x, xs, ys, left=math.nan, right=math.nan)
        y[~np.isfinite(x)] = math.nan
        key = DS.safe_key(str(op.get("prefix") or "") + k, t.taken())
        t.cols.append({"key": key, "name": f"{c2['name']} ({title})"[:120], "unit": c2.get("unit", ""),
                       "kind": c2.get("kind", ""), "dtype": "number", "role": "y",
                       "note": f"linear interpoliert aus „{title}“ v{ver} auf {cx['name']}"[:200]})
        t.data[key] = y
        rows = np.where(np.isfinite(y) & ~exact)[0]
        for i in rows[:MAX_INTERP_FLAGS]:
            t.add_flag({"row": int(i), "col": key, "code": "interpolated", "rule": f"linear aus „{title}“ v{ver}"[:200]})
        if rows.size > MAX_INTERP_FLAGS:
            cut.append(f"„{key}“: {rows.size} interpolierte Werte, nur die ersten {MAX_INTERP_FLAGS} markiert")
        added.append(key)
    outside = int((np.isfinite(x) & ((x < lo) | (x > hi))).sum())
    return (f"Verbunden mit „{title}“ v{ver} über {cx['name']}: " + ", ".join(added) +
            (f"; {outside} Zeile(n) ausserhalb des Bereichs leer" if outside else "") +
            ("; GEKÜRZT: " + "; ".join(cut) if cut else ""))


def sg_coeffs(w: int, p: int) -> np.ndarray:
    h = w // 2
    return np.linalg.pinv(np.vander(np.arange(-h, h + 1, dtype=float), p + 1, increasing=True))[0]


def savgol(y: np.ndarray, w: int, p: int) -> np.ndarray:
    """Savitzky–Golay smoothing; the edges use the polynomial fitted to the first/last window ("interp")."""
    n, h = len(y), w // 2
    out = np.empty(n)
    out[h:n - h] = np.correlate(y, sg_coeffs(w, p), mode="valid")
    xs = np.arange(w, dtype=float)
    out[:h] = np.polyval(np.polyfit(xs, y[:w], p), xs[:h])
    out[n - h:] = np.polyval(np.polyfit(xs, y[n - w:], p), xs[w - h:])
    return out


def op_smooth(t: Table, op: dict, ctx=None) -> str:
    key = str(op.get("col") or "")
    i, c = t.find(key)
    a = t.num(key)
    w, p = int(op.get("window") or 11), int(op.get("order") or 2)
    if w % 2 == 0 or w < 3:
        raise CleanError("Glätten: Fenster ungerade und mindestens 3")
    if not 0 <= p < w - 1:
        raise CleanError("Glätten: Ordnung kleiner als Fenster − 1")
    out = a.astype(float).copy()
    fin = np.isfinite(a)
    short = 0
    k = 0
    while k < t.n:                                   # finite runs; runs shorter than the window stay as they are
        if not fin[k]:
            k += 1
            continue
        e = k
        while e + 1 < t.n and fin[e + 1]:
            e += 1
        if e - k + 1 >= w:
            out[k:e + 1] = savgol(a[k:e + 1].astype(float), w, p)
        else:
            short += e - k + 1
        k = e + 1
    label = f"Savitzky–Golay (Fenster {w}, Ordnung {p})"
    if op.get("keep", True):
        nk = DS.safe_key(f"{key}_sg", t.taken())
        nc = {kk: vv for kk, vv in c.items() if kk not in ("u",)}
        nc.update(key=nk, name=f"{c['name']} geglättet"[:120], role="y", note=label)
        t.cols.insert(i + 1, nc)
        t.data[nk] = out
    else:
        c["note"] = label
        t.data[key] = out
    warn = ""
    xs = [cc for cc in t.cols if cc.get("role") == "x" and cc["dtype"] == "number"]
    if xs:
        xv = t.data[xs[0]["key"]]
        d = np.diff(xv[np.isfinite(xv)])
        if d.size > 2 and np.median(np.abs(d)) > 0 and np.max(np.abs(d - np.median(d))) > 0.01 * np.median(np.abs(d)):
            warn = f"; Achtung: „{xs[0]['name']}“ nicht gleichabständig"
    return f"„{c['name']}“ geglättet, {label}" + (f"; {short} Werte in kurzen Abschnitten ungeglättet" if short else "") + warn


# ----------------------------------------------------------------------------- DP-08 statistics
def _betacf(a, b, x):
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > 1e-300 else 1e-300)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > 1e-300 else 1e-300)
        c = 1.0 + aa / c if abs(c) > 1e-300 else 1e300
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > 1e-300 else 1e-300)
        c = 1.0 + aa / c if abs(c) > 1e-300 else 1e300
        de = d * c
        h *= de
        if abs(de - 1.0) < 1e-15:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    """Regularised incomplete beta function I_x(a, b) (continued fraction)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbt = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)
    if x < (a + 1) / (a + b + 2):
        return math.exp(lbt) * _betacf(a, b, x) / a
    return 1.0 - math.exp(lbt) * _betacf(b, a, 1 - x) / b


def t_cdf(t: float, df: float) -> float:
    ib = betainc(df / 2, 0.5, df / (df + t * t))
    return 1 - 0.5 * ib if t > 0 else 0.5 * ib


def t_ppf(p: float, df: float) -> float:
    """Quantile of Student's t (bisection on the cdf, |error| < 1e-12)."""
    lo, hi = -1e3, 1e3
    for _ in range(200):
        mid = (lo + hi) / 2
        if t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-12:
            break
    return (lo + hi) / 2


def grubbs_crit(n: int, alpha: float, sided: str = "two") -> float:
    a = alpha / (2 * n) if sided == "two" else alpha / n
    t = t_ppf(1 - a, n - 2)
    return (n - 1) / math.sqrt(n) * math.sqrt(t * t / (n - 2 + t * t))


def grubbs(x, alpha: float = 0.05, sided: str = "two", iterate: bool = True) -> list[dict]:
    """Grubbs' test (Grubbs 1969; NIST/SEMATECH e-Handbook, Grubbs' test): G = max |x − mean| / s against the critical
    value from Student's t. `sided`: two | max | min.
    `iterate` (default): the sequential procedure – the flagged value is set aside and the rest tested again with
    the same α in every step (α per step, until a step is not significant). The error rate of the whole procedure is
    not controlled at α: once a real outlier has been set aside, each further step can flag a good value with
    probability α, and masking/swamping are not controlled (ASTM E178 discusses repeated application).
    `iterate=False`: a single test of the most extreme value."""
    x = np.asarray(x, float)
    idx = np.where(np.isfinite(x))[0]
    out = []
    while idx.size >= 3:
        v = x[idx]
        m, s = v.mean(), v.std(ddof=1)
        if not s > 0:
            break
        d = v - m if sided == "max" else m - v if sided == "min" else np.abs(v - m)
        j = int(np.argmax(d))
        G, n = float(d[j] / s), idx.size
        crit = grubbs_crit(n, alpha, sided)
        if G <= crit:
            break
        out.append({"i": int(idx[j]), "G": G, "crit": crit, "n": n})
        idx = np.delete(idx, j)
        if not iterate:
            break
    return out


# Critical values of r10 for n = 3 … 10 as tabulated by Rorabacher (1991) (values as reproduced in the code since
# DP-08; the publication was not available offline, so the transcription is NOT checked against it). α is the
# TWO-SIDED level: the larger of the two end ratios is compared, P(max(Q_low, Q_high) > Q_crit) = α. An independent
# numerical computation for a normal parent (methods page, section Dixon Q; test_dixon_table_matches_null_distribution)
# reproduces the table within 0.003, except n = 4, α = 0.01 (0.926 here, ≈ 0.921 computed) – kept, not replaced.
DIXON_Q = {0.10: [0.941, 0.765, 0.642, 0.560, 0.507, 0.468, 0.437, 0.412],
           0.05: [0.970, 0.829, 0.710, 0.625, 0.568, 0.526, 0.493, 0.466],
           0.01: [0.994, 0.926, 0.821, 0.740, 0.680, 0.634, 0.598, 0.568]}
# One-sided test of a named end at level α uses the two-sided column 2α (P of both ends exceeding is 0 for Q > 0.5
# and below 10⁻⁴ otherwise for these n), so only α = 0.05, 0.025, 0.005 are tabulated one-sided.
DIXON_ONE = {0.05: 0.10, 0.025: 0.05, 0.005: 0.01}


def _alpha_key(alpha: float, table) -> float | None:
    return next((a for a in table if abs(a - alpha) < 1e-12), None)


def dixon(x, alpha: float = 0.05, sided: str = "two") -> list[dict]:
    """Dixon's Q test (r10 = gap/range; Dean & Dixon 1951, critical values Rorabacher 1991) for 3 … 10 values.
    sided="two" (default): the end with the larger ratio is tested at the two-sided α (0.10, 0.05, 0.01);
    "max" / "min": only the highest / lowest value, one-sided α (0.05, 0.025, 0.005). Other α are refused, never replaced."""
    x = np.asarray(x, float)
    idx = np.where(np.isfinite(x))[0]
    n = idx.size
    if sided not in ("two", "max", "min"):
        raise CleanError(f"Dixon: Seite „{sided}“ unbekannt (zweiseitig, nur Maximum, nur Minimum)")
    if sided == "two":
        a2 = _alpha_key(alpha, DIXON_Q)
        if a2 is None:
            raise CleanError(f"Dixon: α = {_de(float(alpha))} ist für den zweiseitigen Test nicht tabelliert "
                             f"(nur 0,10, 0,05 oder 0,01) – kein Ersatzwert")
    else:
        a1 = _alpha_key(alpha, DIXON_ONE)
        if a1 is None:
            raise CleanError(f"Dixon: α = {_de(float(alpha))} ist für den einseitigen Test nicht tabelliert "
                             f"(nur 0,05, 0,025 oder 0,005) – kein Ersatzwert")
        a2 = DIXON_ONE[a1]
    if not 3 <= n <= 10:
        raise CleanError(f"Dixon-Q-Test nur für 3 bis 10 Werte (hier {n}) – Grubbs verwenden")
    o = idx[np.argsort(x[idx], kind="stable")]
    v = x[o]
    rng = v[-1] - v[0]
    if rng <= 0:
        return []
    crit = DIXON_Q[a2][n - 3]
    lo, hi = (0, float((v[1] - v[0]) / rng)), (n - 1, float((v[-1] - v[-2]) / rng))
    if sided == "max":
        j, q = hi
    elif sided == "min":
        j, q = lo
    else:
        j, q = hi if hi[1] >= lo[1] else lo
    return [{"i": int(o[j]), "Q": q, "crit": crit, "n": n}] if q > crit else []


def iqr(x, k: float = 1.5) -> tuple[list[dict], float, float]:
    """Tukey's fences (Tukey 1977): outside [Q1 − k·IQR, Q3 + k·IQR]. The quartiles are numpy.percentile with linear
    interpolation, i.e. sample quantile definition 7 of Hyndman & Fan (1996) – NOT Tukey's hinges, so the fences can
    differ slightly from a textbook box plot."""
    x = np.asarray(x, float)
    v = x[np.isfinite(x)]
    if v.size < 4:
        return [], math.nan, math.nan
    q1, q3 = np.percentile(v, [25, 75])
    lo, hi = q1 - k * (q3 - q1), q3 + k * (q3 - q1)
    return [{"i": int(i), "v": float(x[i])} for i in np.where(np.isfinite(x) & ((x < lo) | (x > hi)))[0]], float(lo), float(hi)


def hampel(x, k: float = 3.0, window: float = 0, xs=None) -> list[dict]:
    """Hampel identifier: |x − median| > k · 1,4826 · MAD (MAD scaled to estimate σ of a normal distribution).
    `window` > 0 without `xs`: moving median over the ±window neighbouring finite values (by position, the spacing of
    x is ignored). With `xs` (same length): the window holds all finite values with |xs_j − xs_i| ≤ window, in the
    unit of xs (unequal spacing respected); values without a finite xs are not tested."""
    x = np.asarray(x, float)
    fin = np.where(np.isfinite(x))[0]
    out = []
    if fin.size < 3:
        return out
    if window <= 0:
        v = x[fin]
        med = np.median(v)
        mad = 1.4826 * np.median(np.abs(v - med))
        if mad > 0:
            out = [{"i": int(i), "med": float(med), "mad": float(mad)} for i in fin if abs(x[i] - med) > k * mad]
        return out
    if xs is not None:
        xs = np.asarray(xs, float)
        fin = fin[np.isfinite(xs[fin])]
        for i in fin:
            w = x[fin[np.abs(xs[fin] - xs[i]) <= window]]
            med = np.median(w)
            mad = 1.4826 * np.median(np.abs(w - med))
            if mad > 0 and abs(x[i] - med) > k * mad:
                out.append({"i": int(i), "med": float(med), "mad": float(mad), "n": int(w.size)})
        return out
    window = int(window)
    for p, i in enumerate(fin):
        w = x[fin[max(0, p - window):p + window + 1]]
        med = np.median(w)
        mad = 1.4826 * np.median(np.abs(w - med))
        if mad > 0 and abs(x[i] - med) > k * mad:
            out.append({"i": int(i), "med": float(med), "mad": float(mad)})
    return out


def residual(x, y, k: float = 3.0, degree: int = 1) -> list[dict]:
    """Points far from a polynomial fit: externally studentized (deleted) residual
    t_i = e_i / (s_(i) √(1 − h_ii)) with s_(i) the scatter of the fit without point i (a standard regression
    diagnostic; no source is cited for it here). `k` is the threshold on |t_i| – default 3, a rule of thumb, not a
    significance level and without a correction for testing n points. The worst point above k is flagged, the fit
    repeated without it, until none is left (at most a quarter of the points) – so a large outlier cannot hide itself
    by inflating the scatter."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = list(np.where(np.isfinite(x) & np.isfinite(y))[0])
    p = degree + 1
    if len(ok) < degree + 3:
        raise CleanError(f"Residuen: zu wenige Punkte für Grad {degree}")
    out, most = [], max(1, len(ok) // 4)
    while len(ok) - p - 1 >= 1 and len(out) < most:
        xi, yi = x[ok], y[ok]
        sc = float(np.ptp(xi)) or 1.0
        V = np.vander((xi - xi.mean()) / sc, p)                  # centred and scaled: well conditioned
        q, _ = np.linalg.qr(V)
        h = np.clip((q * q).sum(axis=1), 0.0, 1.0)
        coef, *_ = np.linalg.lstsq(V, yi, rcond=None)
        e = yi - V @ coef
        n = len(ok)
        sse = float(e @ e)
        with np.errstate(divide="ignore", invalid="ignore"):
            s2 = (sse - e * e / (1.0 - h)) / (n - p - 1)
            t = np.where((h < 1 - 1e-9) & (s2 > 0), e / np.sqrt(s2 * (1.0 - h)), 0.0)
        j = int(np.argmax(np.abs(t)))
        if not abs(t[j]) > k:
            break
        out.append({"i": int(ok[j]), "r": float(t[j])})
        del ok[j]
    return sorted(out, key=lambda d: d["i"])


def _groups(t: Table, by: str | None, rows: np.ndarray) -> list[np.ndarray]:
    if not by:
        return [rows]
    a = t.data[t.find(by)[1]["key"]]
    out = {}
    for i in rows:
        x = a[i].item() if hasattr(a[i], "item") else a[i]
        out.setdefault("nan" if isinstance(x, float) and math.isnan(x) else x, []).append(i)
    return [np.array(v, int) for v in out.values()]


METHODS = {"grubbs": "Grubbs", "dixon": "Dixon-Q", "iqr": "Tukey/IQR", "hampel": "Hampel/MAD", "residual": "Fit-Residuum"}


def op_outliers(t: Table, op: dict, ctx=None) -> str:
    method = str(op.get("method") or "")
    if method not in METHODS:
        raise CleanError(f"Ausreissertest „{method}“ unbekannt")
    key = str(op.get("col") or "")
    _, c = t.find(key)
    y = t.num(key)
    used = np.where(t.used())[0]
    by = op.get("by") or None
    alpha = float(op.get("alpha") or 0.05)
    k = float(op.get("k") or (1.5 if method == "iqr" else 3.0))
    if not (math.isfinite(k) and k > 0):
        raise CleanError("Ausreisser: k muss grösser als 0 sein")
    sides = dict(two="zweiseitig", max="nur Maximum", min="nur Minimum")
    sided = str(op.get("sided") or "two")
    iterate = op.get("iterate", True) is not False
    found, extra = [], ""
    if method == "residual":
        xk = str(op.get("x") or "")
        deg = int(op.get("degree") or 1)
        x = t.num(xk)
        rule = (f"Fit-Residuum (Polynom Grad {deg} über {t.find(xk)[1]['name']}; extern studentisiertes Residuum "
                f"|t| > k = {_de(k)}, Faustregel, kein Signifikanzniveau)")
    elif method == "grubbs":
        rule = (f"Grubbs (α = {_de(alpha)}" + (" je Schritt" if iterate else "") + f", {sides.get(sided, sided)}, "
                + ("sequenziell: Wert beiseitelegen und erneut prüfen" if iterate else "ein Durchgang") + ")")
    elif method == "dixon":
        rule = f"Dixon-Q (r10, α = {_de(alpha)}, {sides.get(sided, sided)}" + (", Ende mit grösserem Q" if sided == "two" else "") + ")"
    elif method == "iqr":
        rule = f"Tukey-Zäune (k = {_de(k)}; Quartile nach Hyndman–Fan Typ 7, lineare Interpolation)"
    else:
        w = float(op.get("window") or 0)
        xk = str(op.get("x") or "") if w > 0 else ""
        x = t.num(xk) if xk else None
        if xk:
            cx = t.find(xk)[1]
            rule = f"Hampel/MAD (k = {_de(k)}, Fenster ±{_de(w, 6)} {cx.get('unit') or ''} in „{cx['name']}“)".replace("  ", " ")
        else:
            rule = f"Hampel/MAD (k = {_de(k)}" + (f", Fenster ±{int(w)} Werte nach Position, x-Abstand nicht berücksichtigt)" if w else ", gesamt)")
    for g in _groups(t, by, used):
        if method == "grubbs":
            res = grubbs(y[g], alpha, sided, iterate)
            for step, r in enumerate(res, 1):
                found.append((g[r["i"]], f"G = {_de(r['G'], 4)} > G_krit = {_de(r['crit'], 4)} (n = {r['n']}"
                                         + (f", Schritt {step}" if iterate else "") + ")"))
            if iterate and len(res) > 1:
                extra = "; sequenziell mit α je Schritt – die Fehlerrate des ganzen Verfahrens ist nicht α"
        elif method == "dixon":
            for r in dixon(y[g], alpha, sided):
                found.append((g[r["i"]], f"Q = {_de(r['Q'], 3)} > Q_krit = {_de(r['crit'], 3)} (n = {r['n']})"))
        elif method == "iqr":
            res, lo, hi = iqr(y[g], k)
            for r in res:
                found.append((g[r["i"]], f"ausserhalb [{_de(lo, 4)}; {_de(hi, 4)}]"))
        elif method == "hampel":
            w = float(op.get("window") or 0)
            for r in hampel(y[g], k, w, x[g] if x is not None else None):
                found.append((g[r["i"]], f"|x − Median| > {_de(k)} · {_de(r['mad'], 3)} (Median {_de(r['med'], 4)})"))
            if x is not None:
                nox = int((np.isfinite(y[g]) & ~np.isfinite(x[g])).sum())
                if nox:
                    extra += f"; {nox} Wert(e) ohne x nicht geprüft"
        else:
            for r in residual(x[g], y[g], k, int(op.get("degree") or 1)):
                found.append((g[r["i"]], f"studentisiertes Residuum {_de(r['r'], 3)}"))
    for i, why in found:
        t.add_flag({"row": int(i), "col": key, "code": "outlier", "rule": rule[:300], "reason": why[:300],
                    **({"alpha": alpha} if method in ("grubbs", "dixon") else {})})
    return (f"Ausreisser in „{c['name']}“ nach {rule}" + (f" je {t.find(by)[1]['name']}" if by else "")
            + f": {len(found)} markiert" + extra)


def op_exclude(t: Table, op: dict, ctx=None) -> str:
    """The recorded decision: rows (1-based in the page, 0-based here) or all flags of a code/rule are excluded."""
    reason = str(op.get("reason") or "").strip()[:300]
    if not reason:
        raise CleanError("Ausschliessen: Grund angeben")
    n = 0
    rows = sorted({int(r) for r in op.get("rows") or []})
    codes = [str(x) for x in op.get("codes") or []]
    col = op.get("col") or None
    if rows:
        for r in rows:
            if not 0 <= r < t.n:
                raise CleanError(f"Zeile {r + 1} gibt es nicht (1 … {t.n})")
            hit = [f for f in t.flags if f["row"] == r and (not col or f.get("col") == col) and f["code"] != "excluded"]
            if hit:
                for f in hit:
                    f.update(excluded=True, reason=(f.get("reason", "") + "; " if f.get("reason") else "") + reason)
            else:
                t.add_flag({"row": r, **({"col": col} if col else {}), "code": "excluded", "excluded": True, "reason": reason})
            n += 1
    if codes:
        rule = str(op.get("rule") or "")
        rs = set()
        for f in t.flags:
            if f["code"] in codes and (not col or f.get("col") == col) and (not rule or rule in (f.get("rule") or "")):
                f.update(excluded=True, reason=(f.get("reason", "") + "; " if f.get("reason") else "") + reason)
                rs.add(f["row"])
        n += len(rs)
    if not rows and not codes:
        raise CleanError("Ausschliessen: Zeilen oder Markierungen wählen")
    return f"{n} Zeile(n) ausgeschlossen: {reason}"


OPS = {"trim": op_trim, "filter": op_filter, "sort": op_sort, "drop_empty": op_drop_empty, "duplicates": op_duplicates,
       "replicates": op_replicates, "join": op_join, "smooth": op_smooth, "outliers": op_outliers, "exclude": op_exclude}


# ----------------------------------------------------------------------------- check chips (DP-08)
# Kinds that cannot be negative. "length" is not here: a length unit also measures positions, displacements and
# elongation changes (ΔL), which are signed. Columns whose name or symbol marks a difference or change (Δ…, δ…,
# "Änderung", "Differenz", "change", …) are skipped for every kind, e.g. a mass change Δm or ΔT in K.
NONNEG = {"mass": "Masse", "area": "Fläche", "volume": "Volumen", "amount": "Stoffmenge",
          "concentration": "Konzentration", "mass_conc": "Massenkonzentration", "density": "Dichte",
          "molar_mass": "molare Masse", "frequency": "Frequenz", "temperature": "absolute Temperatur",
          "rate_const": "Geschwindigkeitskonstante", "activity": "Aktivität", "resistance": "Widerstand"}
_SIGNED_PREFIX = re.compile(r"^\s*(?:Δ|δ|∆|d(?=[A-Z]))")                 # ΔL, δm, dL (case-sensitive: not "Dichte")
_SIGNED_WORD = re.compile(r"^\s*delta(?![a-z])|änderung|aenderung|differenz|verschiebung|verlust|zunahme|abnahme|"
                          r"change|difference|displacement|shift|loss|gain|drift", re.I)


def signed_name(c: dict) -> bool:
    """Name or symbol says the column is a difference or change, so negative values are possible."""
    return any(_SIGNED_PREFIX.search(s) or _SIGNED_WORD.search(s)
               for s in (str(c.get(f) or "") for f in ("name", "symbol", "key")))


def checks(ds: DS.Dataset) -> list[dict]:
    """Chips: {"key", "level": ok|info|warn|bad, "text"}."""
    out = []
    used = ds.used_mask()
    nex = int((~used).sum())
    out.append({"key": "rows", "level": "ok", "text": f"{ds.rows} Zeilen gelesen, {int(used.sum())} verwendet"
                + (f", {nex} ausgeschlossen" if nex else "")})
    nums = [c for c in ds.columns if c["dtype"] == "number"]
    miss = [(c["name"], int((~np.isfinite(ds.data[c["key"]][used])).sum())) for c in nums
            if c.get("role") != "uncertainty"]            # an uncertainty column is often only partly filled
    miss = [m for m in miss if m[1]]
    out.append({"key": "missing", "level": "warn" if miss else "ok",
                "text": "fehlend: " + ", ".join(f"{n} {k}" for n, k in miss[:6]) if miss else "keine fehlenden Werte"})
    fl = {}
    for f in ds.header.get("flags") or []:
        fl[f["code"]] = fl.get(f["code"], 0) + 1
    if fl:
        names = {"outlier": "Ausreisser", "below_lod": "< Nachweisgrenze", "above_range": "> Messbereich", "missing": "fehlt",
                 "duplicate": "doppelt", "excluded": "ausgeschlossen", "interpolated": "interpoliert",
                 "parse_error": "Lesefehler", "note": "Hinweis"}
        open_out = sum(1 for f in ds.header["flags"] if f["code"] == "outlier" and not f.get("excluded"))
        out.append({"key": "flags", "level": "warn" if fl.get("parse_error") or open_out else "info",
                    "text": "Markierungen: " + ", ".join(f"{n} {names.get(k, k)}" for k, n in fl.items())
                    + (f" ({open_out} Ausreisser ohne Entscheidung)" if open_out else "")})
    xs = [c for c in nums if c.get("role") == "x"] or nums[:1]
    if xs:
        x = ds.data[xs[0]["key"]][used]
        x = x[np.isfinite(x)]
        if x.size > 2:
            d = np.diff(x)
            if (d > 0).all() or (d < 0).all():
                out.append({"key": "monotonic", "level": "ok", "text": f"„{xs[0]['name']}“ streng monoton"})
            else:
                back = int((d < 0).sum()) if (d > 0).sum() >= (d < 0).sum() else int((d > 0).sum())
                same = int((d == 0).sum())
                out.append({"key": "monotonic", "level": "warn" if back else "info",
                            "text": f"„{xs[0]['name']}“ nicht monoton ({back} Rücksprünge" + (f", {same} gleiche Werte)" if same else ")")})
            ad = np.abs(d[d != 0])
            if ad.size > 2:
                med = float(np.median(ad))
                gaps = int((ad > 3 * med).sum())
                if gaps:
                    out.append({"key": "gaps", "level": "warn",
                                "text": f"„{xs[0]['name']}“: {gaps} Lücke(n) grösser als 3 × typischer Abstand"})
    for c in ds.columns:
        if c.get("role") in ("group", "label") or (c["dtype"] == "text" and c.get("role") == "condition"):
            a = ds.data[c["key"]][used]
            vals, cnt = np.unique(a.astype(str), return_counts=True)
            if 1 < vals.size <= 60:
                small = int((cnt < 3).sum())
                out.append({"key": "groups:" + c["key"], "level": "warn" if small else "info",
                            "text": f"n je „{c['name']}“: " + ", ".join(f"{v or '–'} {n}" for v, n in list(zip(vals, cnt))[:8])
                            + (" …" if vals.size > 8 else "")})
    for c in nums:
        k = c.get("kind") or ""
        if k in NONNEG and c.get("role") != "uncertainty" and not signed_name(c):
            try:
                si = ds.si(c["key"])[used]
            except (DS.DatasetError, U.UnitError):
                continue
            bad = int((np.isfinite(si) & (si < 0)).sum())
            if bad:
                out.append({"key": "impossible:" + c["key"], "level": "bad",
                            "text": f"„{c['name']}“: {bad} Wert(e) unter null ({NONNEG[k]} kann nicht negativ sein)"})
    ukeys = {c.get("u") for c in ds.columns if c.get("u")}
    from .uncert import factor
    for c in nums:                                          # what a ± / uncertainty column holds (default: not stated)
        if c.get("role") == "uncertainty" or c["key"] in ukeys:
            f, how = factor(c) if c.get("u_type") not in (None, "", "u") else (None, "")
            out.append({"key": "utype:" + c["key"], "level": "info" if c.get("u_type") else "warn",
                        "text": f"„{c['name']}“: {DS.u_type_text(c)}" + (f" → {how}" if f is not None else "")})
    nounit = [c["name"] for c in nums if not c.get("unit") and (c.get("kind") or "number") == "number"
              and c.get("role") not in ("group", "label") and not str(c.get("note") or "").startswith("Anzahl")]
    if nounit:
        out.append({"key": "units", "level": "info", "text": "ohne Einheit: " + ", ".join(nounit[:6])})
    else:
        out.append({"key": "units", "level": "ok", "text": "alle Zahlenspalten mit Einheit"})
    return out


def describe(op: dict) -> str:
    """One line per cleaning step (before it ran)."""
    k = (op or {}).get("op")
    return {"trim": "Zeilenbereich", "filter": "Zeilen filtern", "sort": "Sortieren", "drop_empty": "Leere Zeilen entfernen",
            "duplicates": "Doppelte markieren", "replicates": "Wiederholungen mitteln", "join": "Mit Datensatz verbinden",
            "smooth": "Glätten (Savitzky–Golay)", "outliers": "Ausreisser markieren", "exclude": "Ausschliessen",
            "convert": "Einheit umrechnen", "formula": "Formelspalte",
            "unc": "Messunsicherheit (Typ B)"}.get(k, str(k))
