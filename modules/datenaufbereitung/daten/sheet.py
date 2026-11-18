"""Sheet model shared by every reader (DP-03): one grid of cells per sheet, stored compactly.

    num   float64 (rows × cols)  number of the cell (NaN when none); text cells that read as numbers carry it too
    typ   uint8   (rows × cols)  EMPTY, NUM, TEXT, BOOL, DATE, ERROR, FORMULA (formula without stored value)
    text  {(r, c): str}          text of TEXT, DATE (ISO), ERROR, FORMULA cells
    merged [[r0, c0, r1, c1]]    merged ranges, inclusive, 0-based
    notes  [str]                 what the reader noticed (hidden sheet, formulas without values, …)
    meta   {}                    first guess of text readers (delimiter, decimal comma, header and units rows)

A sheet of DP-Q3 size (100 000 rows × 20 columns) takes about 18 MB.
"""
from __future__ import annotations

import datetime as _dt
import math
import re

import numpy as np

import labtable as LT

EMPTY, NUM, TEXT, BOOL, DATE, ERROR, FORMULA = range(7)
TYPE_NAMES = ["empty", "number", "text", "bool", "date", "error", "formula"]
MAX_CELLS = 10_000_000
MAX_COLS = 16_384
_CHUNK = 4096
_EPOCH = _dt.datetime(1970, 1, 1)
ERRORS = re.compile(r"^#(DIV/0!|N/A|NAME\?|NULL!|NUM!|REF!|VALUE!|SPILL!|CALC!|GETTING_DATA|FIELD!|BLOCKED!|UNKNOWN!|BUSY!)$")


class ReadError(ValueError):
    pass


class Err(str):
    """Spreadsheet error value (#DIV/0! …)."""


class Formula(str):
    """Formula without a stored result."""


# ----------------------------------------------------------------------------- references
def col_name(c: int) -> str:
    s = ""
    c += 1
    while c:
        c, r = divmod(c - 1, 26)
        s = chr(65 + r) + s
    return s


def ref(r: int, c: int) -> str:
    return f"{col_name(c)}{r + 1}"


def range_ref(r0, c0, r1, c1) -> str:
    return ref(r0, c0) if (r0, c0) == (r1, c1) else f"{ref(r0, c0)}:{ref(r1, c1)}"


def parse_ref(s: str) -> tuple[int, int]:
    m = re.fullmatch(r"\$?([A-Za-z]{1,3})\$?(\d{1,7})", s.strip())
    if not m:
        raise ValueError(f"Zellbezug {s!r} ungültig")
    c = 0
    for ch in m.group(1).upper():
        c = c * 26 + ord(ch) - 64
    return int(m.group(2)) - 1, c - 1


# ----------------------------------------------------------------------------- values
def cell_number(s: str, dec_comma: bool | None = None) -> float | None:
    """Number in a text cell. In files known to use a decimal point, `1,234` is a thousands group."""
    t = s.strip()
    if dec_comma is False and re.fullmatch(r"[+\-−]?\d{1,3}(,\d{3})+(\.\d+)?", t):
        return float(t.replace(",", "").replace("−", "-"))
    return LT.number(t)


def classify(v, dec_comma: bool | None = None, text_numbers: bool = False):
    """Python value → (type, number, text). `text_numbers`: plain strings that read as numbers are numbers (CSV)."""
    if v is None:
        return EMPTY, math.nan, None
    if isinstance(v, Err):
        return ERROR, math.nan, str(v)
    if isinstance(v, Formula):
        return FORMULA, math.nan, str(v)
    if isinstance(v, (bool, np.bool_)):
        return BOOL, float(v), "TRUE" if v else "FALSE"
    if isinstance(v, (int, float, np.integer, np.floating)):
        f = float(v)
        return (NUM, f, None) if math.isfinite(f) else (EMPTY, math.nan, None)
    if isinstance(v, _dt.datetime):
        naive = v.replace(tzinfo=None) if v.tzinfo else v
        return DATE, (naive - _EPOCH).total_seconds(), v.isoformat(sep=" ")
    if isinstance(v, _dt.date):
        return DATE, (_dt.datetime(v.year, v.month, v.day) - _EPOCH).total_seconds(), v.isoformat()
    if isinstance(v, _dt.time):
        return DATE, v.hour * 3600 + v.minute * 60 + v.second + v.microsecond / 1e6, v.isoformat()
    if isinstance(v, _dt.timedelta):
        return NUM, v.total_seconds(), None
    s = str(v)
    if not s.strip():
        return EMPTY, math.nan, None
    if ERRORS.match(s.strip()):
        return ERROR, math.nan, s.strip()
    x = cell_number(s, dec_comma)
    if x is not None and text_numbers:
        return NUM, x, None
    return TEXT, (math.nan if x is None else x), s[:2000]


def fmt(x: float) -> str:
    if x == int(x) and abs(x) < 1e15:
        return str(int(x))
    return format(x, ".12g")


# ----------------------------------------------------------------------------- sheet
class Sheet:
    def __init__(self, name: str, num: np.ndarray, typ: np.ndarray, text: dict, merged=None, notes=None, meta=None):
        self.name, self.num, self.typ, self.text = name, num, typ, text
        self.merged = merged or []
        self.notes = notes or []
        self.meta = meta or {}

    @property
    def rows(self) -> int:
        return self.typ.shape[0]

    @property
    def cols(self) -> int:
        return self.typ.shape[1]

    def display(self, r: int, c: int):
        t = int(self.typ[r, c])
        if t == EMPTY:
            return None
        if t in (NUM,):
            s = self.text.get((r, c))                   # manual sheets keep a number as it was typed ("12,5")
            return s if s is not None else fmt(float(self.num[r, c]))
        if t == BOOL:
            return "TRUE" if self.num[r, c] else "FALSE"
        return self.text.get((r, c), "")

    def value(self, r: int, c: int):
        """Cell as Python value: float for numbers and booleans, str otherwise, None when empty."""
        t = int(self.typ[r, c])
        if t == EMPTY:
            return None
        if t in (NUM, BOOL):
            return float(self.num[r, c])
        return self.text.get((r, c), "")

    def window(self, r0: int, r1: int, c0: int, c1: int) -> dict:
        """Cells of a block for the grid: types and display texts (row-major)."""
        r0, c0 = max(0, r0), max(0, c0)
        r1, c1 = min(self.rows, max(r0, r1)), min(self.cols, max(c0, c1))
        typ = self.typ[r0:r1, c0:c1]
        out_v, out_t = [], typ.tolist()
        for i in range(r1 - r0):
            row = []
            for j in range(c1 - c0):
                row.append(self.display(r0 + i, c0 + j) if out_t[i][j] else None)
            out_v.append(row)
        return {"r0": r0, "r1": r1, "c0": c0, "c1": c1, "t": out_t, "v": out_v}

    def describe(self) -> dict:
        counts = np.bincount(self.typ.ravel(), minlength=7) if self.typ.size else np.zeros(7, int)
        return {"name": self.name, "rows": self.rows, "cols": self.cols, "merged": self.merged[:500],
                "notes": self.notes[:40], "meta": self.meta,
                "types": {TYPE_NAMES[i]: int(counts[i]) for i in range(1, 7) if counts[i]}}


class Builder:
    """Collects rows one at a time (streaming readers) and makes a compact Sheet."""

    def __init__(self, name: str, dec_comma: bool | None = None, text_numbers: bool = False):
        self.name = name
        self.dec, self.tn = dec_comma, text_numbers
        self.n = 0
        self.width = 8
        self.used_cols = 0
        self.last_row = -1
        self.num_chunks: list[np.ndarray] = []
        self.typ_chunks: list[np.ndarray] = []
        self.text: dict = {}
        self.merged: list = []
        self.notes: list = []
        self.meta: dict = {}

    def _widen(self, w: int):
        if w > MAX_COLS:
            raise ReadError(f"{self.name}: mehr als {MAX_COLS} Spalten")
        nw = max(w, self.width * 2)
        for k, a in enumerate(self.num_chunks):
            b = np.full((a.shape[0], nw), np.nan)
            b[:, :a.shape[1]] = a
            self.num_chunks[k] = b
        for k, a in enumerate(self.typ_chunks):
            b = np.zeros((a.shape[0], nw), np.uint8)
            b[:, :a.shape[1]] = a
            self.typ_chunks[k] = b
        self.width = nw

    def empty_rows(self, k: int):
        for _ in range(k):
            self.row(())

    def row(self, cells, start_col: int = 0):
        """Append one row; `cells` are Python values (see `classify`)."""
        r = self.n
        if r % _CHUNK == 0:
            self.num_chunks.append(np.full((_CHUNK, self.width), np.nan))
            self.typ_chunks.append(np.zeros((_CHUNK, self.width), np.uint8))
        n = len(cells)
        if start_col + n > self.width:
            self._widen(start_col + n)
        if (r + 1) * max(self.used_cols, start_col + n) > MAX_CELLS:
            raise ReadError(f"{self.name}: zu viele Zellen (höchstens {MAX_CELLS:,})".replace(",", "'"))
        numc, typc = self.num_chunks[-1], self.typ_chunks[-1]
        i = r % _CHUNK
        any_val = False
        for j, v in enumerate(cells):
            if v is None or (isinstance(v, str) and not v.strip()):
                continue
            t, x, s = classify(v, self.dec, self.tn)
            if t == EMPTY:
                continue
            c = start_col + j
            typc[i, c] = t
            numc[i, c] = x
            if s is not None:
                self.text[(r, c)] = s
            if c + 1 > self.used_cols:
                self.used_cols = c + 1
            any_val = True
        if any_val:
            self.last_row = r
        self.n += 1

    def sheet(self) -> Sheet:
        rows, cols = self.last_row + 1, self.used_cols
        if self.num_chunks:
            num = np.concatenate(self.num_chunks)[:rows, :cols].copy()
            typ = np.concatenate(self.typ_chunks)[:rows, :cols].copy()
        else:
            num, typ = np.full((0, 0), np.nan), np.zeros((0, 0), np.uint8)
        merged = [m for m in self.merged if m[0] < max(rows, 1) and m[1] < max(cols, 1)]
        return Sheet(self.name, num, typ, self.text, merged, self.notes, self.meta)
