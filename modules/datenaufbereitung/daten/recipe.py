"""Marking a sheet (DP-05): every assignment is a recipe step; the steps fold into a layout, the layout extracts a
long table from the sheet.

Steps (cell references are A1 in the original sheet; "lines" are rows, or columns when the sheet is transposed;
"series" are the other direction, counted from the first column/row of the data block):

    {"op": "block", "range": "A5:C200"}                 data block (the numbers) of the first block
    {"op": "header", "lines": [3]}                       line(s) with names above the block (0-based)
    {"op": "units", "line": 4}                           line with units (or null)
    {"op": "skip", "lines": [17, 18]}                    lines inside the block that are not data (toggle)
    {"op": "role", "series": 1, "role": "y", "of": 0}    x | y | uncertainty (of series) | group | label | ignore
    {"op": "meta", "cell": "B2", "name": "T", "unit": "°C", "as": "condition"|"column"}   (unit/name optional)
    {"op": "meta_remove", "cell": "B2"}
    {"op": "repeat", "dir": "right"|"down", "step": 3, "count": 0, "label": "A4"}   count 0 = until empty
    {"op": "repeat_off"}
    {"op": "wide", "series": [1, 2, 3], "name": "c", "cond": "T"}   columns → one value column + condition column
    {"op": "wide_off"}
    {"op": "transpose", "on": true}
    {"op": "colprop", "series": 1, "symbol": "σ", "kind": "stress", "time": "elapsed"|"raw", "time_unit": "min"}  (DP-06)

Cell texts in number columns (`<0,01`, `n.d.`, `12,3 ± 0,4`, `#DIV/0!`, …) are resolved by `parse.marker` with a flag;
date and time columns become elapsed time (`parse.elapsed`), the start time is kept as a condition.

`guess(sheet)` proposes the steps; `extract(sheet, steps)` gives the table; `to_dataset` checks it with labdataset.
"""
from __future__ import annotations

import re

import numpy as np

import labdataset as DS
import labtable as LT

from . import parse as P
from .sheet import DATE, EMPTY, ERROR, FORMULA, NUM, TEXT, Sheet, col_name, parse_ref, range_ref, ref

ROLES = ("x", "y", "uncertainty", "group", "label", "condition", "ignore", "")
OPS = ("block", "header", "units", "skip", "role", "meta", "meta_remove", "repeat", "repeat_off", "wide", "wide_off",
       "transpose", "unit", "name", "colprop")
MARK_TEXT = {"below_lod": "unter der Nachweisgrenze (Wert = Grenze)", "above_range": "über dem Messbereich (Wert = Grenze)",
             "missing": "fehlend (n.d., —, Fehlerwert)", "note": "mit Einheit in der Zelle, umgerechnet"}
MAX_BLOCKS = 1000
_U_HINT = re.compile(r"^(u|s|sd|std|stdev|σ|sigma|err|error|fehler|unsicherheit|uncertainty|±|\+/-)\b|^(u|s|σ)\s*\(|±",
                     re.I)


class RecipeError(ValueError):
    pass


# ----------------------------------------------------------------------------- layout
def layout_of(steps) -> dict:
    L = {"block": None, "header": [], "units": None, "skip": set(), "roles": {}, "meta": {}, "repeat": None,
         "wide": None, "transpose": False, "unit_ranges": [], "name_ranges": [], "colprops": {}}
    for s in steps or []:
        op = (s or {}).get("op")
        if op not in OPS:
            raise RecipeError(f"Schritt {op!r} unbekannt")
        if op == "block":
            p = str(s.get("range") or "").split(":")
            (r0, c0), (r1, c1) = parse_ref(p[0]), parse_ref(p[-1])
            L["block"] = (min(r0, r1), min(c0, c1), max(r0, r1), max(c0, c1))
        elif op == "header":
            L["header"] = sorted({int(x) for x in s.get("lines") or []})
        elif op == "units":
            L["units"] = None if s.get("line") is None else int(s["line"])
        elif op == "skip":
            for x in s.get("lines") or []:
                L["skip"] ^= {int(x)}
        elif op == "role":
            role = s.get("role") or ""
            if role not in ROLES:
                raise RecipeError(f"Rolle {role!r} unbekannt")
            j = int(s["series"])
            L["roles"][j] = {"role": role, **({"of": int(s["of"])} if s.get("of") is not None else {})}
        elif op == "meta":
            r, c = parse_ref(str(s["cell"]))
            L["meta"][(r, c)] = {"name": str(s.get("name") or "")[:60], "unit": str(s.get("unit") or "")[:30],
                                 "as": "column" if s.get("as") == "column" else "condition"}
        elif op == "meta_remove":
            L["meta"].pop(parse_ref(str(s["cell"])), None)
        elif op == "repeat":
            L["repeat"] = {"dir": "down" if s.get("dir") == "down" else "right", "step": int(s.get("step") or 0),
                           "count": int(s.get("count") or 0),
                           "label": parse_ref(s["label"]) if s.get("label") else None}
            if L["repeat"]["step"] <= 0:
                raise RecipeError("Wiederholung: Abstand muss grösser als 0 sein")
        elif op == "repeat_off":
            L["repeat"] = None
        elif op == "wide":
            ser = sorted({int(x) for x in s.get("series") or []})
            if len(ser) < 2:
                raise RecipeError("Breit → lang braucht mindestens zwei Spalten")
            L["wide"] = {"series": ser, "name": str(s.get("name") or "Wert")[:60], "cond": str(s.get("cond") or "Bedingung")[:60]}
        elif op == "wide_off":
            L["wide"] = None
        elif op == "transpose":
            L["transpose"] = bool(s.get("on", True))
        elif op == "colprop":                            # DP-06: symbol, quantity kind, date/time handling
            from labcalc import units as U
            j = int(s["series"])
            cp = dict(L["colprops"].get(j) or {})
            if "symbol" in s:
                cp["symbol"] = str(s.get("symbol") or "").strip()[:40]
            if "kind" in s:
                kind = str(s.get("kind") or "").strip()
                if kind and kind not in U.KINDS:
                    raise RecipeError(f"Grössenart „{kind}“ unbekannt")
                cp["kind"] = kind
            if "time" in s:
                if s.get("time") not in ("elapsed", "raw"):
                    raise RecipeError("Datum/Zeit: „elapsed“ oder „raw“")
                cp["time"] = s["time"]
            if "time_unit" in s:
                tu = _clean_unit(str(s.get("time_unit") or ""))
                if tu and unit_problem(tu):
                    raise RecipeError(f"Zeiteinheit „{tu}“: {unit_problem(tu)}")
                cp["time_unit"] = tu
            L["colprops"][j] = cp
        elif op in ("unit", "name"):                     # DP-M3: unit or name for the columns of a range
            p = str(s.get("range") or "").split(":")
            (r0, c0), (r1, c1) = parse_ref(p[0]), parse_ref(p[-1])
            box = (min(r0, r1), min(c0, c1), max(r0, r1), max(c0, c1))
            if op == "unit":
                u = _clean_unit(str(s.get("unit") or ""))[:30]
                if u and unit_problem(u):
                    raise RecipeError(f"Einheit „{u}“: {unit_problem(u)}")
                L["unit_ranges"].append((box, u))
            else:
                L["name_ranges"].append((box, str(s.get("name") or "").strip()[:120]))
    return L


def _range_value(ranges, T: bool, s: int):
    """Last unit/name assignment whose range covers series s (columns, or rows when transposed); None if none."""
    out = None
    for (r0, c0, r1, c1), val in ranges:
        lo, hi = (r0, r1) if T else (c0, c1)
        if lo <= s <= hi:
            out = val
    return out


class View:
    """The sheet as lines × series (transposed when series run along rows)."""

    def __init__(self, sh: Sheet, T: bool):
        self.sh, self.T = sh, T
        self.nl, self.ns = (sh.cols, sh.rows) if T else (sh.rows, sh.cols)
        self.merged = {}
        for r0, c0, r1, c1 in sh.merged:
            for r in range(r0, min(r1, r0 + 200) + 1):
                for c in range(c0, min(c1, c0 + 200) + 1):
                    self.merged[(r, c)] = (r0, c0)

    def rc(self, l, s):
        return (s, l) if self.T else (l, s)

    def ls(self, r, c):
        return (c, r) if self.T else (r, c)

    def ok(self, l, s):
        return 0 <= l < self.nl and 0 <= s < self.ns

    def typ(self, l, s) -> int:
        return int(self.sh.typ[self.rc(l, s)]) if self.ok(l, s) else EMPTY

    def text(self, l, s, fill_merged=True) -> str:
        if not self.ok(l, s):
            return ""
        r, c = self.rc(l, s)
        if fill_merged and self.sh.typ[r, c] == EMPTY and (r, c) in self.merged:
            r, c = self.merged[(r, c)]
        v = self.sh.display(r, c)
        return "" if v is None else str(v).strip()

    def series(self, s, l0, l1):
        """typ, num for series s over lines l0..l1 (inclusive)."""
        if not 0 <= s < self.ns:
            n = l1 - l0 + 1
            return np.zeros(n, np.uint8), np.full(n, np.nan)
        if self.T:
            return self.sh.typ[s, l0:l1 + 1], self.sh.num[s, l0:l1 + 1]
        return self.sh.typ[l0:l1 + 1, s], self.sh.num[l0:l1 + 1, s]

    def ref(self, l, s) -> str:
        return ref(*self.rc(l, s))

    def range(self, l0, s0, l1, s1) -> str:
        a, b = self.rc(l0, s0), self.rc(l1, s1)
        return range_ref(min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))


# ----------------------------------------------------------------------------- helpers
_NUM_UNIT = re.compile(r"^\s*([-+−]?(?:\d[\d.,' ]*|[.,]\d+)(?:[eE][-+−]?\d+)?)\s*(.*?)\s*$")


def value_unit(text: str):
    """'25 °C' → (25.0, '°C'); 'c bei 35 °C' → (35.0, '°C'); '1,2 mol/L' → (1.2, 'mol/L'); else (None, text)."""
    t = str(text or "").strip()
    m = _NUM_UNIT.match(t)
    if m and LT.number(m.group(1)) is not None:
        return LT.number(m.group(1)), m.group(2)
    m = re.search(r"(?:^|\s)([-+−]?\d[\d.,]*)\s*([^\d\s]\S*)?\s*$", t)        # "c bei 35 °C"; not "A1"
    if m and LT.number(m.group(1)) is not None:
        return LT.number(m.group(1)), (m.group(2) or "")
    return None, t


def _clean_unit(u: str) -> str:
    u = (u or "").strip().strip("[]()").strip()
    return {"-": "", "–": "", "1": "", "°c": "°C", "degc": "°C", "deg c": "°C", "grad": "°", "l": "L", "ml": "mL",
            "µl": "µL", "ul": "µL", "mol/l": "mol/L", "mmol/l": "mmol/L", "µmol/l": "µmol/L", "g/l": "g/L",
            "mg/l": "mg/L", "sec": "s", "std": "h"}.get(u.lower(), u)


def _lone_units(v, h: int, c0: int, c1: int) -> bool:
    """A units line in which only some columns have a unit (labtable.is_unit_row needs two): every filled cell is a
    readable unit, the line above names more columns (a header, not a title or a `Name:` cell) and stands over
    each unit."""
    toks = [v.text(h, c) for c in range(c0, c1 + 1)]
    above = [v.text(h - 1, c) for c in range(c0, c1 + 1)]
    filled = [i for i, x in enumerate(toks) if x]
    named = [a for a in above if a]
    if not filled or len(named) < 2 or len(filled) >= len(named):
        return False
    if any(LT.number(a) is not None or a.rstrip().endswith((":", "=")) for a in named):
        return False
    for i in filled:
        u = _clean_unit(toks[i])
        if not above[i] or LT.number(toks[i]) is not None or not u or unit_problem(u):
            return False
    return True


def _is_numeric(t: np.ndarray, x: np.ndarray) -> np.ndarray:
    return (t == NUM) | (t == DATE) | ((t == TEXT) & np.isfinite(x))


def _marker_mask(sh: Sheet, cap: int = 200_000) -> np.ndarray:
    """DP-06 for the first guess: error values, markers ("<0,01", "n.d.", "12 ± 1") and clock/date texts count as
    data cells – but only in columns that also hold real numbers, so remark columns stay text."""
    m = sh.typ == ERROR
    numcols = _is_numeric(sh.typ, sh.num).any(axis=0)
    rr, cc = np.where((sh.typ == TEXT) & ~np.isfinite(sh.num))
    for r, c in list(zip(rr.tolist(), cc.tolist()))[:cap]:
        t = sh.display(r, c) or ""
        if (numcols[c] and P.resolvable(t)) or P.time_of(t) is not None:
            m[r, c] = True
    return m & (numcols[None, :] | (sh.typ == TEXT))


# ----------------------------------------------------------------------------- first guess
def guess(sh: Sheet, loose: bool = False) -> list[dict]:
    """Largest numeric block, header and units lines above it, metadata cells (`Name: value`), side-by-side blocks.
    `loose` (manual sheets, DP-M3): one number per row is enough, so columns of different length stay one block."""
    if sh.rows == 0 or sh.cols == 0:
        return []
    numeric = _is_numeric(sh.typ, sh.num) | _marker_mask(sh)
    per_row = numeric.sum(axis=1)
    # longest run of rows with ≥ 2 numeric cells (or ≥ 1 when only one column holds numbers)
    need = 2 if int(numeric.any(axis=0).sum()) > 1 and not loose else 1
    filled_row = (sh.typ != EMPTY).sum(axis=1)
    best, i = (0, -1), 0
    while i < sh.rows:
        if per_row[i] >= need:
            j = i
            while True:
                if j + 1 < sh.rows and per_row[j + 1] >= need:
                    j += 1
                    continue
                # up to two weak rows (e.g. "<0,01" in one cell) inside a run do not end it
                k = next((k for k in (j + 2, j + 3) if k < sh.rows and per_row[k] >= need
                          and all(filled_row[m] > 0 for m in range(j + 1, k))), None)
                if k is None:
                    break
                j = k
            if j - i > best[1] - best[0]:
                best = (i, j)
            i = j + 1
        else:
            i += 1
    if best[1] < 0:
        return []
    r0, r1 = best
    istext = (sh.typ[r0:r1 + 1] == TEXT) & ~numeric[r0:r1 + 1]
    if loose:       # manual sheets: columns may be of any length – more numbers than texts makes a number column
        nn, nt = numeric[r0:r1 + 1].sum(axis=0), istext.sum(axis=0)
        cols, textcols = np.where((nn > 0) & (nn >= nt))[0], np.where((nt > 0) & (nt > nn))[0]
    else:
        cols = np.where(numeric[r0:r1 + 1].mean(axis=0) >= 0.5)[0]
        textcols = np.where(istext.mean(axis=0) >= 0.5)[0]
    allc = np.union1d(cols, textcols)
    c0, c1 = int(allc.min()), int(allc.max())
    # contiguous groups of used columns (side-by-side blocks)
    used = np.zeros(c1 - c0 + 1, bool)
    used[allc - c0] = True
    groups, k = [], 0
    while k < len(used):
        if used[k]:
            m = k
            while m + 1 < len(used) and used[m + 1]:
                m += 1
            groups.append((c0 + k, c0 + m))
            k = m + 1
        else:
            k += 1
    # header and units above the block
    v = View(sh, False)
    units = header = None
    h = r0 - 1
    while h >= 0 and not any(v.text(h, c) for c in range(c0, c1 + 1)):
        h -= 1
    if h >= 0 and LT.is_unit_row([v.text(h, c) for c in range(c0, c1 + 1)]):
        units, h = h, h - 1
        while h >= 0 and not any(v.text(h, c) for c in range(c0, c1 + 1)):
            h -= 1
    if h >= 0:
        cells = [v.text(h, c) for c in range(c0, c1 + 1)]
        filled = [x for x in cells if x]
        if filled and sum(LT.number(x) is None for x in filled) >= max(1, len(filled) * 0.6):
            header = h
    if sh.meta.get("header") is not None and sh.meta.get("start") == r0:   # text reader saw the same table
        header = sh.meta["header"]
        units = sh.meta.get("units")
    if units is None and header is not None and header >= 1 and _lone_units(v, header, c0, c1):
        units, header = header, header - 1              # e.g. "µm" over x and nothing over a dimensionless y
    if header is not None and len(groups) == 1:
        # neighbouring columns with a header name and some content (e.g. a sparse remarks column) belong to the table
        filled = sh.typ[r0:r1 + 1] != EMPTY
        while c1 + 1 < sh.cols and v.text(header, c1 + 1) and filled[:, c1 + 1].any():
            c1 += 1
        while c0 - 1 >= 0 and v.text(header, c0 - 1) and filled[:, c0 - 1].any():
            c0 -= 1
        groups = [(c0, c1)]
    steps = []
    g0 = groups[0]
    if len(groups) >= 2:
        w = g0[1] - g0[0]
        same = [g for g in groups if g[1] - g[0] == w]
        if len(same) == len(groups):
            hdr = lambda g: [v.text(header, c) for c in range(g[0], g[1] + 1)] if header is not None else []  # noqa: E731
            if all(hdr(g) == hdr(g0) for g in groups[1:]):
                step = groups[1][0] - g0[0]
                lab = None
                top = (header if header is not None else r0) - 1
                while top >= 0 and not v.text(top, g0[0]):
                    top -= 1
                if top >= 0 and LT.number(v.text(top, g0[0])) is None and (units is None or top != units):
                    lab = ref(top, g0[0])
                steps.append({"op": "block", "range": range_ref(r0, g0[0], r1, g0[1])})
                steps.append({"op": "repeat", "dir": "right", "step": step, "count": len(groups),
                              **({"label": lab} if lab else {})})
                c0, c1 = g0
    if not steps:
        steps.append({"op": "block", "range": range_ref(r0, c0, r1, c1)})
    if header is not None:
        steps.append({"op": "header", "lines": [header]})
    if units is not None:
        steps.append({"op": "units", "line": units})
    # roles: first numeric series x, then y; texts label; "u(…)", "s", "±" → uncertainty of the series before
    # empty columns without a name inside the block are left out; on manual sheets a bare "s" or "u" is more
    # likely seconds or a voltage than an uncertainty
    first_x = None
    for j, c in enumerate(range(c0, c1 + 1)):
        name = v.text(header, c) if header is not None else ""
        if c not in cols and not name and not (sh.typ[r0:r1 + 1, c] != EMPTY).any():
            steps.append({"op": "role", "series": j, "role": "ignore"})
        elif c not in cols:
            steps.append({"op": "role", "series": j, "role": "label"})
        elif first_x is None:
            first_x = j
            steps.append({"op": "role", "series": j, "role": "x"})
        elif (name and _U_HINT.search(name) and j > 0 and (c - 1) in cols
              and not (loose and name.strip().lower() in ("s", "u"))):
            steps.append({"op": "role", "series": j, "role": "uncertainty", "of": j - 1})
        else:
            steps.append({"op": "role", "series": j, "role": "y"})
    # metadata above: "Name:" followed by a value, or "Name: value unit" in one cell
    top = min(x for x in (header, units, r0) if x is not None)
    for r in range(0, top):
        for c in range(0, min(sh.cols, 30)):
            t = v.text(r, c, False)
            if not t:
                continue
            m = re.match(r"^\s*([^:=]{1,40}?)\s*[:=]\s*(.+)$", t)
            if m and value_unit(m.group(2))[0] is not None:
                steps.append({"op": "meta", "cell": ref(r, c), "name": m.group(1).strip(), "as": "condition"})
            elif t.endswith((":", "=")) and c + 1 < sh.cols and sh.typ[r, c + 1] in (NUM, TEXT) and \
                    value_unit(v.text(r, c + 1, False))[0] is not None:
                unit = v.text(r, c + 2, False) if c + 2 < sh.cols and sh.typ[r, c + 2] == TEXT else ""
                steps.append({"op": "meta", "cell": ref(r, c + 1), "name": t.rstrip(":= ").strip(),
                              **({"unit": unit} if unit and LT.number(unit) is None and len(unit) <= 12 else {}),
                              "as": "condition"})
    return steps


# ----------------------------------------------------------------------------- extraction
def _blocks(v: View, L: dict):
    """[(l0, s0, l1, s1, label)] in view coordinates."""
    r0, c0, r1, c1 = L["block"]
    (l0, s0), (l1, s1) = v.ls(r0, c0), v.ls(r1, c1)
    l0, l1 = sorted((l0, l1))
    s0, s1 = sorted((s0, s1))
    rep = L["repeat"]
    out = [(l0, s0, l1, s1, None)]
    if not rep:
        return out
    # "right" = along the series direction, "down" = along the lines (in the original orientation of the sheet)
    along_series = (rep["dir"] == "right") != v.T
    lab = v.ls(*rep["label"]) if rep["label"] else None
    out = []
    n = rep["count"] or MAX_BLOCKS
    for i in range(min(n, MAX_BLOCKS)):
        dl, ds = (0, i * rep["step"]) if along_series else (i * rep["step"], 0)
        b = (l0 + dl, s0 + ds, l1 + dl, s1 + ds)
        if not v.ok(b[0], b[1]):
            break
        if not rep["count"] and i > 0:
            t, x = v.series(b[1], b[0], min(b[2], v.nl - 1))
            if not (_is_numeric(t, x)).any():
                break
        label = v.text(lab[0] + dl, lab[1] + ds) if lab else None
        out.append((*b, label or f"Block {i + 1}"))
    return out


def extract(sh: Sheet, steps, sheet_name: str | None = None) -> dict:
    """Long table from the marked sheet: {"columns": [...], "rows", "conditions", "notes", "marks"}."""
    L = layout_of(steps)
    if not L["block"]:
        raise RecipeError("Kein Datenblock markiert")
    v = View(sh, L["transpose"])
    name = sheet_name or sh.name
    blocks = _blocks(v, L)
    notes, marks = [], []
    w = blocks[0][3] - blocks[0][1] + 1
    roles = {j: L["roles"].get(j, {"role": ""}) for j in range(w)}
    keep = [j for j in range(w) if roles[j]["role"] != "ignore"]
    per_block = []
    skipped_empty = 0
    for bi, (l0, s0, l1, s1, label) in enumerate(blocks):
        shift_l = l0 - blocks[0][0]                      # header, units and skipped lines move with the block
        lines = [l for l in range(l0, l1 + 1) if (l - shift_l) not in L["skip"] and l < v.nl]
        if not lines:
            continue
        idx = np.array(lines) - l0
        cols = []
        for j in keep:
            s = s0 + j
            t, x = v.series(s, l0, min(l1, v.nl - 1))
            t, x = t[idx[idx < len(t)]], x[idx[idx < len(x)]]
            hdr_parts = []
            for h in L["header"]:
                txt = v.text(h + shift_l, s)
                if txt and (not hdr_parts or hdr_parts[-1] != txt):
                    hdr_parts.append(txt)
            nm = " ".join(hdr_parts) or (f"Zeile {s + 1}" if v.T else f"Spalte {col_name(s)}")
            unit = ""
            if L["units"] is not None:
                unit = _clean_unit(v.text(L["units"] + shift_l, s))
            if not unit:
                nm2, u2 = LT.name_unit(nm)
                if u2 and nm2 and unit_problem(_clean_unit(u2)) is None:      # "u(c)" is a name, not unit "c"
                    nm, unit = nm2, _clean_unit(u2)
            nm_set, u_set = _range_value(L["name_ranges"], v.T, s), _range_value(L["unit_ranges"], v.T, s)
            if nm_set:
                nm = nm_set
            if u_set is not None:
                unit = u_set
            num_mask = _is_numeric(t, x)
            filled = t != EMPTY
            bad = np.where(filled & ~num_mask)[0]
            n_mark = 0                                   # DP-06: "<0,01", "n.d.", "12 ± 1" count as numbers
            if bad.size and num_mask.any():
                probe = bad[:2000]
                n_mark = sum(1 for i in probe if P.resolvable(v.text(lines[i], s, False))) * bad.size / probe.size
            dtype = "number" if filled.sum() == 0 or num_mask.sum() + n_mark >= 0.5 * filled.sum() else "text"
            raw = {}
            if dtype == "number":
                vals = np.where(num_mask, x, np.nan).astype(float)
                for i in bad[:5000]:
                    raw[int(i)] = v.text(lines[i], s, False)
                is_date = bool((t == DATE).sum() > 0.5 * max(1, num_mask.sum()))
            else:
                vals = np.array([v.text(lines[i], s, False) for i in range(len(t))], dtype=object)
                is_date = False
                tc = P.time_column(vals)                 # "2024-03-01 12:00:05", "12:00:05" → seconds
                if tc is not None:
                    dtype, vals, is_date = "number", tc[0], True
            cols.append({"j": j, "name": nm[:120], "unit": unit[:30], "dtype": dtype, "values": vals, "raw": raw,
                         "date": is_date, "cells": f"{name}!{v.range(lines[0], s, lines[-1], s)}",
                         "errors": int(((t == ERROR) | (t == FORMULA)).sum())})
        if not cols:
            continue
        # empty data lines (nothing in any kept series) are not data
        n = len(cols[0]["values"])
        empty = np.ones(n, bool)
        for c in cols:
            if c["dtype"] == "number":
                empty &= ~np.isfinite(c["values"]) & np.array([i not in c["raw"] for i in range(n)])
            else:
                empty &= np.array([not str(x) for x in c["values"]])
        if empty.any():
            skipped_empty += int(empty.sum())
            keep_i = np.where(~empty)[0]
            remap = {int(o): k for k, o in enumerate(keep_i)}
            for c in cols:
                c["values"] = c["values"][keep_i]
                c["raw"] = {remap[i]: t for i, t in c["raw"].items() if i in remap}
        per_block.append((label, cols))
        marks.append({"kind": "data", "range": v.range(l0, s0, l1, s1)})
        for h in L["header"]:
            marks.append({"kind": "header", "range": v.range(h + shift_l, s0, h + shift_l, s1)})
        if L["units"] is not None:
            marks.append({"kind": "units", "range": v.range(L["units"] + shift_l, s0, L["units"] + shift_l, s1)})
        for j in range(w):
            if roles[j]["role"] == "ignore":
                marks.append({"kind": "ignore", "range": v.range(l0, s0 + j, l1, s0 + j)})
        for sk in L["skip"]:
            if l0 <= sk + shift_l <= l1:
                marks.append({"kind": "skip", "range": v.range(sk + shift_l, s0, sk + shift_l, s1)})
        if L["repeat"] and L["repeat"]["label"]:
            lab = v.ls(*L["repeat"]["label"])
            marks.append({"kind": "label", "range": v.ref(lab[0] + (l0 - blocks[0][0]), lab[1] + (s0 - blocks[0][1]))})
    if not per_block:
        raise RecipeError("Der markierte Bereich enthält keine Daten")
    # stack blocks (columns matched by position)
    base = per_block[0][1]
    for bi, (label, cols) in enumerate(per_block[1:], start=2):
        for c0, c in zip(base, cols):
            if c["name"] != c0["name"] and c["name"] and not c["name"].startswith("Spalte "):
                notes.append(f"Block {bi}: Spalte {c['j'] + 1} heisst „{c['name']}“, im ersten Block „{c0['name']}“")
            if c["unit"] != c0["unit"]:
                notes.append(f"Block {bi}: Einheit „{c['unit']}“ statt „{c0['unit']}“ in „{c0['name']}“ – nicht umgerechnet")
    out_cols = []
    for k, c0 in enumerate(base):
        parts = [cols[k] for _, cols in per_block]
        dtype = "number" if all(p["dtype"] == "number" for p in parts) else "text"
        vals, raw, off = [], {}, 0
        for p in parts:
            vv = p["values"] if dtype == p["dtype"] else np.array([("" if (isinstance(x, float) and np.isnan(x)) else
                                                                     (str(x) if p["dtype"] == "text" else _fmt(x)))
                                                                    for x in p["values"]], dtype=object)
            vals.append(vv)
            raw.update({off + i: t for i, t in p["raw"].items()})
            off += len(vv)
        out_cols.append({"name": c0["name"], "unit": c0["unit"] if dtype == "number" else "", "dtype": dtype,
                         "values": np.concatenate(vals) if vals else np.array([]), "raw": raw, "date": c0["date"],
                         "cells": "; ".join(p["cells"] for p in parts[:4]) + (" …" if len(parts) > 4 else ""),
                         "errors": sum(p["errors"] for p in parts), "j": c0["j"],
                         "role": roles[c0["j"]]["role"], "of_j": roles[c0["j"]].get("of")})
    nrows = len(out_cols[0]["values"])
    if len(per_block) > 1:
        labels = np.concatenate([np.array([lab] * len(cols[0]["values"]), dtype=object) for lab, cols in per_block])
        out_cols.insert(0, {"name": "Block", "unit": "", "dtype": "text", "values": labels, "raw": {}, "date": False,
                            "cells": "Beschriftung je Block" if L["repeat"]["label"] else "Blocknummer", "errors": 0,
                            "j": None, "role": "group", "of_j": None})
    # metadata cells
    conditions = {}
    for (r, c), m in L["meta"].items():
        val, unit = _meta_value(sh, r, c)
        nm = m["name"]
        if not nm and c > 0 and sh.typ[r, c - 1] == TEXT:
            nm = (sh.display(r, c - 1) or "").rstrip(":= ").strip()
        if not nm and sh.typ[r, c] == TEXT:
            mm = re.match(r"^\s*([^:=]{1,40}?)\s*[:=]", sh.display(r, c) or "")
            nm = mm.group(1) if mm else ""
        nm = (nm or ref(r, c))[:60]
        unit = m["unit"] or unit
        marks.append({"kind": "meta", "range": ref(r, c)})
        if val is None:
            notes.append(f"Metadatenzelle {ref(r, c)}: kein Wert")
            continue
        if m["as"] == "column":
            isnum = isinstance(val, float)
            out_cols.append({"name": nm, "unit": _clean_unit(unit) if isnum else "", "dtype": "number" if isnum else "text",
                             "values": np.full(nrows, val) if isnum else np.array([val] * nrows, dtype=object),
                             "raw": {}, "date": False, "cells": f"{name}!{ref(r, c)}", "errors": 0, "j": None,
                             "role": "condition", "of_j": None})
        else:
            conditions[nm] = {"value": val, "unit": _clean_unit(unit) if isinstance(val, float) else "",
                              "from": f"{name}!{ref(r, c)}"}
    # wide → long
    if L["wide"]:
        out_cols, nrows = _wide(out_cols, L["wide"], v, L, blocks, notes)
    out_cols = _resolve(out_cols, L, conditions, notes)
    # keys and uncertainty links
    taken: set = set()
    by_j = {}
    for c in out_cols:
        c["key"] = DS.safe_key(c["name"], taken)
        taken.add(c["key"])
        if c.get("j") is not None:
            by_j[c["j"]] = c["key"]
    for c in out_cols:
        if c.get("role") == "uncertainty" and c.get("of_j") is not None:
            c["of"] = by_j.get(c["of_j"])
        if c.get("of_col") is not None:
            c["of"] = c.pop("of_col")["key"]
    nraw = sum(len(c["raw"]) for c in out_cols)
    if nraw:
        notes.append(f"{nraw} Zelle(n) in Zahlenspalten sind nicht lesbar – sie bleiben leer und als Lesefehler markiert "
                     "(Text in der Zelle korrigieren oder die Spalte als Beschriftung führen)")
    if skipped_empty:
        notes.append(f"{skipped_empty} leere Zeile(n) im Block übergangen")
    errs = sum(c["errors"] for c in out_cols)
    if errs:
        notes.append(f"{errs} Fehlerwert(e) oder Formel(n) ohne Wert im Block – als leer gelesen")
    return {"columns": out_cols, "rows": nrows, "conditions": conditions, "notes": notes, "marks": marks,
            "blocks": len(per_block), "layout": _layout_json(L)}


def _fmt(x) -> str:
    return "" if x is None or (isinstance(x, float) and not np.isfinite(x)) else format(float(x), ".12g")


def _resolve(cols, L, conditions, notes):
    """DP-06: column properties, cell markers (flagged, never guessed), ± → uncertainty column, dates → elapsed."""
    out = []
    for c in cols:
        out.append(c)
        c.setdefault("mk", {})
        cp = L["colprops"].get(c.get("j")) if c.get("j") is not None else None
        for k in ("symbol", "kind"):
            if cp and cp.get(k):
                c[k] = cp[k]
        if c["dtype"] != "number":
            continue
        c["values"] = np.array(c["values"], dtype=float)
        if c["raw"]:
            unc = {}
            for i, txt in list(c["raw"].items()):
                r = P.marker(txt, c["unit"])
                if r is None:
                    continue
                c["values"][i] = r["value"]
                del c["raw"][i]
                if r.get("code"):
                    c["mk"][i] = (r["code"], txt, r.get("reason") or "")
                if r.get("u") is not None:
                    unc[i] = r["u"]
            counts = {}
            for code, _, _ in c["mk"].values():
                counts[code] = counts.get(code, 0) + 1
            parts = [f"{n} × {MARK_TEXT.get(k, k)}" for k, n in counts.items()]
            if unc:
                uv = np.full(len(c["values"]), np.nan)
                for i, u in unc.items():
                    uv[i] = u
                have = next((x for x in cols if x is not c and x.get("role") == "uncertainty" and x.get("of_j") is not None
                             and x.get("of_j") == c.get("j") and x["dtype"] == "number"), None)
                if have is not None:
                    have["values"] = np.where(np.isfinite(np.asarray(have["values"], float)), have["values"], uv)
                    parts.append(f"{len(unc)} × Wert ± Unsicherheit (in „{have['name']}“)")
                else:
                    nm = f"u({c['name']})"[:120]
                    out.append({"name": nm, "unit": c["unit"], "dtype": "number", "values": uv, "raw": {}, "mk": {},
                                "date": False, "cells": c["cells"], "errors": 0, "j": None, "role": "uncertainty",
                                "of_j": None, "of_col": c})
                    parts.append(f"{len(unc)} × Wert ± Unsicherheit (Spalte „{nm}“)")
            if parts:
                notes.append(f"Spalte „{c['name']}“: " + "; ".join(parts))
        if c.get("date") and (cp or {}).get("time") != "raw":
            vals = c["values"]
            fin = vals[np.isfinite(vals)]
            only = bool(fin.size and (fin < 2 * 86400).all())
            try:
                rel, unit, start = P.elapsed(vals, only, (cp or {}).get("time_unit") or None)
            except ValueError as e:
                notes.append(f"Spalte „{c['name']}“: {e}")
                continue
            c.update(values=rel, unit=unit, kind=c.get("kind") or "time", elapsed=start)
            if start:
                conditions[f"{c['name']} Start"[:60]] = {"value": start, "unit": "", "from": str(c["cells"])[:80]}
                notes.append(f"Spalte „{c['name']}“: Datum/Uhrzeit → Zeit seit {start} in {unit}")
    return out


def _meta_value(sh: Sheet, r: int, c: int):
    if not (0 <= r < sh.rows and 0 <= c < sh.cols):
        return None, ""
    t = int(sh.typ[r, c])
    if t in (NUM, DATE):
        unit = ""
        if c + 1 < sh.cols and sh.typ[r, c + 1] == TEXT:
            u = (sh.display(r, c + 1) or "").strip()
            if len(u) <= 12 and LT.number(u) is None:
                unit = u
        return float(sh.num[r, c]), unit
    if t == TEXT:
        s = sh.display(r, c) or ""
        m = re.match(r"^\s*[^:=]{1,40}?\s*[:=]\s*(.+)$", s)
        val, unit = value_unit(m.group(1) if m else s)
        return (val, unit) if val is not None else (s.strip(), "")
    return None, ""


def _wide(cols, W, v, L, blocks, notes):
    """Selected series → one value column + a condition column from their header text."""
    wset = set(W["series"])
    wcols = [c for c in cols if c.get("j") in wset]
    other = [c for c in cols if c.get("j") not in wset]
    if len(wcols) < 2:
        raise RecipeError("Breit → lang: die gewählten Spalten sind nicht im Block")
    n = len(wcols[0]["values"])
    k = len(wcols)
    conds = [value_unit(c["name"]) for c in wcols]
    numeric = all(x[0] is not None for x in conds) and len({x[1] for x in conds}) == 1
    units = {c["unit"] for c in wcols}
    if len(units) > 1:
        notes.append("Breit → lang: Spalten mit verschiedenen Einheiten (" + ", ".join(sorted(units)) + ") – nicht umgerechnet")
    dtype = "number" if all(c["dtype"] == "number" for c in wcols) else "text"
    vals = np.concatenate([c["values"] if dtype == c["dtype"] else np.array([_fmt(x) if c["dtype"] == "number" else str(x)
                                                                           for x in c["values"]], dtype=object)
                           for c in wcols])
    raw = {}
    for i, c in enumerate(wcols):
        raw.update({i * n + r: t for r, t in c["raw"].items()})
    out = []
    for c in other:
        out.append({**c, "values": np.concatenate([c["values"]] * k),
                    "raw": {i * n + r: t for i in range(k) for r, t in c["raw"].items()}})
    if numeric:
        cond = {"name": W["cond"], "unit": _clean_unit(conds[0][1]), "dtype": "number",
                "values": np.repeat(np.array([x[0] for x in conds], float), n)}
    else:
        cond = {"name": W["cond"], "unit": "", "dtype": "text",
                "values": np.repeat(np.array([c["name"] for c in wcols], dtype=object), n)}
    out.append({**cond, "raw": {}, "date": False, "cells": "Kopfzeile der Spalten " + ", ".join(c["name"] for c in wcols)[:200],
                "errors": 0, "j": None, "role": "condition", "of_j": None})
    roles = {c.get("role") or "y" for c in wcols}
    out.append({"name": W["name"], "unit": wcols[0]["unit"] if dtype == "number" and len(units) == 1 else "", "dtype": dtype,
                "values": vals, "raw": raw, "date": False, "cells": "; ".join(c["cells"] for c in wcols[:4]),
                "errors": sum(c["errors"] for c in wcols), "j": wcols[0]["j"],
                "role": roles.pop() if len(roles) == 1 else "y", "of_j": None})
    return out, n * k


def _layout_json(L: dict) -> dict:
    return {"block": range_ref(*L["block"]) if L["block"] else None, "header": L["header"], "units": L["units"],
            "skip": sorted(L["skip"]), "roles": {str(k): v for k, v in L["roles"].items()},
            "meta": [{"cell": ref(*k), **v} for k, v in L["meta"].items()],
            "repeat": ({**L["repeat"], "label": ref(*L["repeat"]["label"]) if L["repeat"]["label"] else None}
                       if L["repeat"] else None), "wide": L["wide"], "transpose": L["transpose"],
            "colprops": {str(k): v for k, v in L["colprops"].items()}}


# ----------------------------------------------------------------------------- output
def preview(tbl: dict, n: int = 50) -> dict:
    """JSON for the page: columns with unit check and the first n rows."""
    cols = []
    for c in tbl["columns"]:
        info = {k: c.get(k) for k in ("key", "name", "unit", "dtype", "role", "of", "cells", "date", "symbol", "kind",
                                      "elapsed", "j")}
        info["raw"] = len(c["raw"])
        info["raw_examples"] = sorted({t for t in list(c["raw"].values())[:200]})[:6]
        fl = {}
        for code, txt, _ in (c.get("mk") or {}).values():
            e = fl.setdefault(code, {"n": 0, "examples": []})
            e["n"] += 1
            if len(e["examples"]) < 4 and txt not in e["examples"]:
                e["examples"].append(txt)
        info["flags"] = fl
        info["mk_head"] = {str(i): m[0] for i, m in (c.get("mk") or {}).items() if i < n}
        if c["dtype"] == "number":
            a = c["values"]
            fin = a[np.isfinite(a)]
            info.update(n=int(fin.size), min=float(fin.min()) if fin.size else None,
                        max=float(fin.max()) if fin.size else None)
            info["unit_msg"] = unit_problem(c["unit"])
        else:
            info["n"] = int(sum(1 for x in c["values"] if str(x)))
        cols.append(info)
    rows = []
    for i in range(min(n, tbl["rows"])):
        row = []
        for c in tbl["columns"]:
            x = c["values"][i]
            if c["dtype"] == "number":
                row.append(None if not np.isfinite(x) else float(x)) if i not in c["raw"] else row.append(c["raw"][i])
            else:
                row.append(str(x))
        rows.append(row)
    return {"columns": cols, "rows": tbl["rows"], "head": rows, "conditions": tbl["conditions"], "notes": tbl["notes"],
            "marks": tbl["marks"][:2000], "blocks": tbl["blocks"], "layout": tbl["layout"]}


def unit_problem(unit: str) -> str | None:
    from labcalc import units as U
    try:
        U.parse_unit(unit or "")
    except U.UnitError as e:
        return str(e)
    return None


def to_dataset(tbl: dict, title: str, files: list[dict], steps, module_version: str):
    """Table → checked dataset. Unknown units are refused (labdataset), never guessed."""
    cols = []
    for c in tbl["columns"]:
        rec = {"key": c["key"], "name": c["name"], "unit": c["unit"] if c["dtype"] == "number" else "",
               "dtype": c["dtype"], "role": c["role"] if c["role"] in DS.ROLES else "", "cells": c["cells"][:200],
               "values": c["values"] if c["dtype"] == "number" else [str(x) for x in c["values"]]}
        if c.get("symbol"):
            rec["symbol"] = c["symbol"]
        if c.get("kind") and c["dtype"] == "number":
            rec["kind"] = c["kind"]
        if c.get("elapsed"):
            rec["note"] = f"Zeit seit {c['elapsed']}"
        cols.append(rec)
    for c in tbl["columns"]:                        # uncertainty column: the measured column points to it ("u")
        if c.get("role") == "uncertainty" and c.get("of"):
            for r2 in cols:
                if r2["key"] == c["of"]:
                    r2["u"] = c["key"]
    flags = []
    for c in tbl["columns"]:
        for i, t in sorted(c["raw"].items())[:20000]:
            flags.append({"row": int(i), "col": c["key"], "code": "parse_error", "raw": t[:200]})
        for i, (code, t, reason) in sorted((c.get("mk") or {}).items())[:20000]:
            flags.append({"row": int(i), "col": c["key"], "code": code, "raw": t[:200], **({"reason": reason} if reason else {})})
    flags.sort(key=lambda f: (f["row"], f["col"]))
    prov = {"files": files, "recipe": list(steps or []), "module_version": module_version}
    return DS.from_columns(title, cols, conditions=tbl["conditions"], flags=flags, provenance=prov)
