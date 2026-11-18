"""Typed datasets (`suite.dataset/1`, DP-02): equal-length columns, each with name, quantity kind and unit.

Made by the Datenaufbereitung module, read by the Rechner, Elementrechner, TGA and FTIR. A dataset is one table:

    header = {"schema": "suite.dataset/1", "title", "rows",
              "columns": [{"key", "name", "symbol"?, "kind"?, "unit", "dtype": "number"|"text", "role"?, "u"?,
                           "cells"?, "note"?, "u_type"?, "u_k"?, "u_level"?}],
              "conditions"?: {name: {"value", "unit"?, "from"?}},
              "flags"?: [{"row", "col"?, "code", "excluded"?, "reason"?, "rule"?, "raw"?}],
              "provenance"?: {"files": [{"name", "sha256", "sheet"?, "ranges"?}], "recipe"?: [...], "module_version"?}}
    data   = {key: numpy array (float, NaN = missing) | numpy str array}

Rules (OUTLINE §7): flags never delete rows; `excluded` is a recorded decision; units must be readable by
`labcalc.units` and fit the quantity kind; missing values stay NaN (no imputation here).
Storage: `<stem>.json` (header) + `<stem>.npz` (columns, no pickles).

Hashes: `data_hash` covers column keys, units, types and values (checked on load and by shares);
`flags_hash` covers the flags including exclusions. Both are recomputed whenever a dataset is built.

Uncertainty type (`u_type`, on a column of role "uncertainty" or one that other columns point to with "u"):
"" not stated (default), "u" standard uncertainty, "U" expanded uncertainty (coverage factor `u_k`),
"sd" standard deviation, "se" standard error of the mean, "ci" half-width of a confidence interval (`u_level` in %).
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

import numpy as np

from labcalc import units as U

SCHEMA = "suite.dataset/1"
MAX_ROWS = 1_000_000
MAX_COLS = 200
MAX_CELLS = 5_000_000            # ~100 000 rows × 50 columns with room (DP-Q3)
ROLES = ("", "x", "y", "uncertainty", "group", "label", "condition")
FLAG_CODES = ("outlier", "missing", "below_lod", "above_range", "duplicate", "excluded", "interpolated",
              "parse_error", "note")
U_TYPES = {"": ("nicht angegeben", "not stated"), "u": ("Standardunsicherheit u", "standard uncertainty u"),
           "U": ("erweiterte Unsicherheit U", "expanded uncertainty U"), "sd": ("Standardabweichung s", "standard deviation s"),
           "se": ("Standardfehler des Mittelwerts", "standard error of the mean"),
           "ci": ("Konfidenzintervall (halbe Breite)", "confidence interval (half-width)")}


def u_type_text(c: dict, lang: str = "de") -> str:
    """What a ± / uncertainty column holds, e.g. "erweiterte Unsicherheit U (k = 2)"; "nicht angegeben" by default."""
    t = c.get("u_type") or ""
    s = U_TYPES.get(t, U_TYPES[""])[0 if lang == "de" else 1]
    if t == "U" and c.get("u_k"):
        s += f" (k = {c['u_k']:g})".replace(".", "," if lang == "de" else ".")
    if t == "ci" and c.get("u_level"):
        s += f" ({c['u_level']:g} %)".replace(".", "," if lang == "de" else ".")
    return s
_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,39}$")


class DatasetError(ValueError):
    pass


_TRANS = str.maketrans({**{a: b for a, b in zip("äöüÄÖÜßµ°", "aouAOUsuo")},
                        "σ": "sigma", "ε": "eps", "τ": "tau", "Δ": "d", "δ": "d", "α": "alpha", "β": "beta", "γ": "gamma",
                        "λ": "lambda", "ρ": "rho", "η": "eta", "θ": "theta", "φ": "phi", "ω": "omega", "ν": "nu",
                        "κ": "kappa", "Σ": "Sum", "μ": "u"})


def safe_key(name: str, taken=()) -> str:
    """Column key from a header text: letters, digits, underscore; unique against `taken` (ΔL → dL, σ → sigma)."""
    k = re.sub(r"[^A-Za-z0-9_]+", "_", str(name or "").translate(_TRANS)).strip("_")
    k = k or "col"
    if not re.match(r"[A-Za-z_]", k):
        k = "c_" + k
    k = k[:36]
    base, i = k, 2
    while k in taken:
        k = f"{base}_{i}"
        i += 1
    return k


def _num_array(v) -> np.ndarray:
    a = np.asarray([math.nan if x is None else x for x in v] if isinstance(v, list) else v, dtype=float)
    return a.ravel()


def _txt_array(v) -> np.ndarray:
    return np.asarray(["" if x is None else str(x)[:500] for x in (v.tolist() if isinstance(v, np.ndarray) else v)],
                      dtype=str)


def check(header: dict, data: dict) -> tuple[dict, dict]:
    """Validate and normalise; returns (header, data). Raises DatasetError with a message for the user."""
    if not isinstance(header, dict):
        raise DatasetError("Datensatz: Kopf fehlt")
    cols = header.get("columns")
    if not isinstance(cols, list) or not cols:
        raise DatasetError("Datensatz ohne Spalten")
    if len(cols) > MAX_COLS:
        raise DatasetError(f"Zu viele Spalten ({len(cols)} > {MAX_COLS})")
    out_cols, out_data, n = [], {}, None
    for c in cols:
        key = str((c or {}).get("key") or "")
        if not _KEY.match(key):
            raise DatasetError(f"Spaltenschlüssel „{key}“ ungültig (Buchstaben, Ziffern, _; max. 40)")
        if key in out_data:
            raise DatasetError(f"Spalte „{key}“ doppelt")
        if key not in data:
            raise DatasetError(f"Spalte „{key}“: Werte fehlen")
        dtype = c.get("dtype") or "number"
        if dtype not in ("number", "text"):
            raise DatasetError(f"Spalte „{key}“: Typ {dtype} unbekannt")
        role = c.get("role") or ""
        if role not in ROLES:
            raise DatasetError(f"Spalte „{key}“: Rolle {role} unbekannt")
        rec = {"key": key, "name": str(c.get("name") or key)[:120], "dtype": dtype, "role": role,
               "unit": str(c.get("unit") or "")[:30]}
        for f in ("symbol", "note", "cells", "u"):
            if c.get(f):
                rec[f] = str(c[f])[:200]
        ut = c.get("u_type") or ""
        if ut:
            if ut not in U_TYPES:
                raise DatasetError(f"Spalte „{rec['name']}“: Art der Unsicherheit „{ut}“ unbekannt "
                                   f"(u, U, sd, se, ci oder leer)")
            rec["u_type"] = ut
            for f, lo, hi, what in (("u_k", 0.0, 100.0, "Erweiterungsfaktor k"), ("u_level", 0.0, 100.0, "Niveau in %")):
                if c.get(f) is None or c.get(f) == "":
                    continue
                try:
                    x = float(str(c[f]).replace(",", "."))
                except ValueError:
                    raise DatasetError(f"Spalte „{rec['name']}“: {what} ist keine Zahl") from None
                if not lo < x < hi:
                    raise DatasetError(f"Spalte „{rec['name']}“: {what} ausserhalb ({lo:g}, {hi:g})")
                if (f == "u_k" and ut == "U") or (f == "u_level" and ut == "ci"):
                    rec[f] = x
        if dtype == "number":
            arr = _num_array(data[key])
            unit, kind = rec["unit"], str(c.get("kind") or "")
            try:
                _, dims, _ = U.parse_unit(unit)
            except U.UnitError as e:
                raise DatasetError(f"Spalte „{rec['name']}“: {e}") from e
            if kind:
                try:
                    msg = U.check_unit(kind, unit)
                except U.UnitError as e:
                    msg = str(e)
                if msg:
                    raise DatasetError(f"Spalte „{rec['name']}“: {msg}")
            else:
                kind = U.kind_for_unit(unit or "1")      # U-01: pH -> pH-Wert, µS/cm -> Leitfähigkeit, sonst Zahl …
            rec["kind"] = kind
            if np.isinf(arr).any():
                raise DatasetError(f"Spalte „{rec['name']}“: unendliche Werte")
        else:
            arr = _txt_array(data[key])
            rec["unit"] = ""
        if n is None:
            n = len(arr)
        elif len(arr) != n:
            raise DatasetError(f"Spalte „{rec['name']}“ hat {len(arr)} Zeilen, die anderen {n}")
        out_cols.append(rec)
        out_data[key] = arr
    if n > MAX_ROWS or n * len(out_cols) > MAX_CELLS:
        raise DatasetError(f"Datensatz zu gross ({n} Zeilen × {len(out_cols)} Spalten; höchstens {MAX_ROWS} Zeilen "
                           f"und {MAX_CELLS} Zellen)")
    keys = {c["key"] for c in out_cols}
    for c in out_cols:
        if c.get("u") and (c["u"] not in keys or c["u"] == c["key"]):
            raise DatasetError(f"Spalte „{c['name']}“: Unsicherheitsspalte „{c['u']}“ fehlt")
    flags = []
    for f in header.get("flags") or []:
        r = f.get("row")
        if not isinstance(r, int) or isinstance(r, bool) or not 0 <= r < n:
            raise DatasetError(f"Markierung mit ungültiger Zeile {r!r}")
        if f.get("col") and f["col"] not in keys:
            raise DatasetError(f"Markierung für unbekannte Spalte {f['col']}")
        code = f.get("code")
        if code not in FLAG_CODES:
            raise DatasetError(f"Markierung {code!r} unbekannt")
        flags.append({k: (f[k] if k in ("row", "excluded", "alpha") else str(f[k])[:300])
                      for k in ("row", "col", "code", "excluded", "reason", "rule", "raw", "alpha") if k in f and f[k] is not None})
    cond = {}
    for k, v in list((header.get("conditions") or {}).items())[:40]:
        if isinstance(v, dict) and isinstance(v.get("value"), (int, float, str)) and not isinstance(v.get("value"), bool):
            unit = str(v.get("unit") or "")[:30]
            if unit and isinstance(v["value"], (int, float)):
                try:
                    U.parse_unit(unit)
                except U.UnitError as e:
                    raise DatasetError(f"Bedingung {k}: {e}") from e
            cond[str(k)[:60]] = {"value": v["value"], "unit": unit, **({"from": str(v["from"])[:80]} if v.get("from") else {})}
    head = {"schema": SCHEMA, "title": str(header.get("title") or "Datensatz")[:160], "rows": int(n),
            "columns": out_cols, "conditions": cond, "flags": flags,
            "provenance": header.get("provenance") if isinstance(header.get("provenance"), dict) else {}}
    head["data_hash"] = data_hash(head, out_data)
    head["flags_hash"] = flags_hash(flags)
    return head, out_data


def flags_hash(flags) -> str:
    """SHA-256 over the flags in their stored order (row, column, code, exclusion, reason, rule, cell text, α), so a
    change that only alters flags or exclusions is visible (the data hash covers the values only)."""
    keys = ("row", "col", "code", "excluded", "reason", "rule", "raw", "alpha")
    rows = [[f.get(k) for k in keys] for f in flags or []]
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def data_hash(header: dict, data: dict) -> str:
    """SHA-256 over the column keys, units and types and the values (stable across saves). Flags and exclusions are
    in `flags_hash`; names, roles, kinds, conditions and provenance are in neither."""
    h = hashlib.sha256()
    h.update(json.dumps([{k: c.get(k) for k in ("key", "unit", "dtype")} for c in header["columns"]],
                        sort_keys=True).encode("utf-8"))
    for c in header["columns"]:
        a = data[c["key"]]
        h.update(np.ascontiguousarray(a, dtype=float).tobytes() if c["dtype"] == "number"
                 else "\x1f".join(a.tolist()).encode("utf-8"))
    return h.hexdigest()


class Dataset:
    """A checked dataset in memory."""

    def __init__(self, header: dict, data: dict, checked: bool = False):
        self.header, self.data = (header, data) if checked else check(header, data)

    # ------------------------------------------------------------------ access
    @property
    def rows(self) -> int:
        return self.header["rows"]

    @property
    def columns(self) -> list[dict]:
        return self.header["columns"]

    def col(self, key: str) -> dict:
        for c in self.columns:
            if c["key"] == key:
                return c
        raise DatasetError(f"Spalte „{key}“ nicht im Datensatz")

    def values(self, key: str, used_only: bool = False) -> np.ndarray:
        a = self.data[self.col(key)["key"]]
        return a[self.used_mask()] if used_only else a

    def used_mask(self) -> np.ndarray:
        """True for rows that consumers should use (not excluded by a recorded decision)."""
        m = np.ones(self.rows, dtype=bool)
        for f in self.header.get("flags") or []:
            if f.get("excluded"):
                m[f["row"]] = False
        return m

    def si(self, key: str, used_only: bool = False) -> np.ndarray:
        """Numbers of a column in SI (°C → K etc.; temperature differences without offset)."""
        c = self.col(key)
        if c["dtype"] != "number":
            raise DatasetError(f"Spalte „{c['name']}“ ist Text")
        f, _, off = U.parse_unit(c["unit"])
        k = U.KINDS.get(c.get("kind") or "")
        return self.values(key, used_only) * f + (0.0 if (k and k.diff) else off)

    def in_unit(self, key: str, unit: str, used_only: bool = False) -> np.ndarray:
        """Column converted to `unit` (must have the same dimension)."""
        c = self.col(key)
        f2, d2, off2 = U.parse_unit(unit)
        if not U.compatible(c["unit"], unit):            # gleiche Dimension und Skala (pH nicht in %)
            raise DatasetError(f"Spalte „{c['name']}“ ({c['unit'] or '1'}) lässt sich nicht in {unit} umrechnen")
        k = U.KINDS.get(c.get("kind") or "")
        diff = bool(k and k.diff)
        return (self.si(key, used_only) - (0.0 if diff else off2)) / f2

    # ------------------------------------------------------------------ page payload
    def page(self, r0: int = 0, r1: int | None = None, keys=None) -> dict:
        """Header plus a row range of chosen columns as JSON-safe lists (NaN → None)."""
        r1 = self.rows if r1 is None else max(0, min(int(r1), self.rows))
        r0 = max(0, min(int(r0), r1))
        keys = keys or [c["key"] for c in self.columns]
        cols = {}
        for k in keys:
            a = self.values(k)[r0:r1]
            cols[k] = [None if (isinstance(x, float) and math.isnan(x)) else x for x in a.tolist()]
        return {"header": self.header, "r0": r0, "r1": r1, "values": cols}

    # ------------------------------------------------------------------ files
    def save(self, stem: Path) -> Path:
        stem = Path(stem)
        stem.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(stem.with_suffix(".npz"), **{c["key"]: self.data[c["key"]] for c in self.columns})
        stem.with_suffix(".json").write_text(json.dumps(self.header, ensure_ascii=False, indent=1), encoding="utf-8")
        return stem.with_suffix(".json")

    @classmethod
    def load(cls, stem: Path) -> "Dataset":
        stem = Path(stem)
        head = json.loads(stem.with_suffix(".json").read_text(encoding="utf-8"))
        with np.load(stem.with_suffix(".npz"), allow_pickle=False) as z:
            data = {k: z[k] for k in z.files}
        ds = cls(head, data)
        if head.get("data_hash") and ds.header["data_hash"] != head["data_hash"]:
            raise DatasetError(f"{stem.name}: Daten passen nicht zur Prüfsumme (Datei verändert?)")
        if head.get("flags_hash") and ds.header["flags_hash"] != head["flags_hash"]:
            raise DatasetError(f"{stem.name}: Markierungen passen nicht zur Prüfsumme (Datei verändert?)")
        return ds


def thumb(ds: Dataset, n: int = 150) -> dict | None:
    """UI-18 / I-02: small picture of a dataset (overview box, import window): x column (or row number) against up to
    three number columns, rows excluded by a recorded decision left out, every k-th row (the page thins it further)."""
    unc = {c.get("u") for c in ds.columns if c.get("u")}
    cols = [c for c in ds.columns if c.get("dtype") == "number" and c.get("role") != "uncertainty" and c["key"] not in unc]
    xc = next((c for c in cols if c.get("role") == "x"), None)
    ys = [c for c in cols if c is not xc][:3]
    if not ys or not ds.rows:
        return None
    m = ds.used_mask()
    x = (ds.values(xc["key"]) if xc else np.arange(1, ds.rows + 1, dtype=float))[m]
    step = max(1, math.ceil(len(x) / n))

    def arr(a):
        return [float(f"{v:.4g}") if math.isfinite(v) else None for v in np.asarray(a, float)[::step]]

    def lab(c):
        return c["name"] + (f" [{c['unit']}]" if c.get("unit") else "")

    return {"title": str(ds.header.get("title") or "")[:80], "xlab": lab(xc)[:50] if xc else "#",
            "ylab": (lab(ys[0]) if len(ys) == 1 else ", ".join(c["name"] for c in ys))[:50],
            "series": [{"name": c["name"][:60], "x": arr(x), "y": arr(ds.values(c["key"])[m])} for c in ys]}


def from_columns(title: str, columns: list[dict], **header) -> Dataset:
    """Convenience: columns as [{key, name, unit, kind?, dtype?, role?, values}]."""
    data = {c["key"]: c["values"] for c in columns}
    head = {"title": title, "columns": [{k: v for k, v in c.items() if k != "values"} for c in columns], **header}
    return Dataset(head, data)
