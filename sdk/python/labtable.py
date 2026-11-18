"""Text tables: decoding, delimiter and decimal-comma detection, numeric blocks, header names and units, numbers.

Shared by every module that reads CSV/TXT exports (TGA, FTIR, Elementrechner own tables, Datenaufbereitung).
The sniffing functions came from `tga/readers.py` (DP-01) and keep their behaviour; `number()` is the general cell
parser (German and English formats, Unicode minus, thin spaces, `E`, `·10^`).

Rules for ambiguous numbers (documented, tested):
- one comma and no dot (`12,5`) is a decimal comma (German first, as everywhere in Folio Lab);
- `1.234,5` and `1 234,5` are German with thousands separators; `1,234.5` and `1,234,567` are English;
- several dots and no comma (`1.234.567`) are thousands dots.
"""
from __future__ import annotations

import math
import re

__all__ = ["decode", "split", "isnum", "tofloat", "number", "sniff_sep", "comma_decimal", "data_block",
           "name_unit", "is_unit_row", "norm_unit", "sniff", "UNIT_ROW_GENERAL"]


# ----------------------------------------------------------------------------- decoding
def decode(data: bytes) -> str:
    """Bytes to text: BOM / UTF-16 (also without BOM), then UTF-8, cp1252, latin-1."""
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16")
    if len(data) > 4 and data[1:4:2] == b"\x00\x00" and data[0] != 0:
        return data.decode("utf-16-le", errors="replace")
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


# ----------------------------------------------------------------------------- fields and numbers
_NUM = re.compile(r"^[+-−]?(\d+([.,]\d*)?|[.,]\d+)([eE][+-−]?\d+)?$")


def split(line: str, sep: str) -> list[str]:
    if sep == " ":
        return line.split()
    return [c.strip().strip('"') for c in line.split(sep)]


def isnum(s: str) -> bool:
    return bool(_NUM.match(s.strip().strip('"')))


def tofloat(s: str, dec_comma: bool) -> float:
    """Field to float when the file's decimal sign is known (NaN when not a number)."""
    s = s.strip().strip('"').replace("−", "-")
    if not s:
        return math.nan
    if dec_comma:
        s = s.replace(".", "").replace(",", ".") if s.count(",") == 1 and s.count(".") >= 1 and s.index(".") < s.index(",") \
            else s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return math.nan


_SPACES = dict.fromkeys(map(ord, "     '’"), None)   # thousands spaces and apostrophes
_POW10 = re.compile(r"^(.*?)\s*[·x×*]\s*10\s*\^?\s*\(?([+-−]?\d+)\)?$")
_SUP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺", "0123456789-+")


def number(s) -> float | None:
    """Cell text to float, or None when it is not a plain number.

    Understands `12,5`, `12.5`, `1.234,5`, `1 234,5`, `1,234.5`, `1'234.5`, `−3`, `+4`, `1,2E-3`, `1.2e3`,
    `1,2·10^-3`, `1.2×10⁻³`. Anything else (units, text, `<0,01`, `n.d.`) gives None; such markers are handled by the
    caller (Datenaufbereitung parsing rules)."""
    if isinstance(s, bool):
        return None
    if isinstance(s, (int, float)):
        return float(s) if math.isfinite(float(s)) else None
    t = str(s).strip().strip('"').translate(_SUP).replace("−", "-").replace("–", "-")
    if not t:
        return None
    m = _POW10.match(t)
    if m:
        mant = number(m.group(1)) if m.group(1).strip() else 1.0
        if mant is None:
            return None
        try:
            return mant * 10.0 ** int(m.group(2).replace("−", "-"))
        except (ValueError, OverflowError):
            return None
    exp = ""
    me = re.search(r"[eE]([+-]?\d+)$", t)
    if me:
        exp, t = "e" + me.group(1), t[:me.start()]
    t = t.translate(_SPACES)
    if not re.fullmatch(r"[+-]?[\d.,]*\d[\d.,]*|[+-]?[\d.,]*[.,]", t):
        return None
    nc, nd = t.count(","), t.count(".")
    if nc and nd:
        if t.rfind(",") > t.rfind("."):          # 1.234,5
            t = t.replace(".", "").replace(",", ".")
        else:                                     # 1,234.5
            t = t.replace(",", "")
    elif nc == 1:
        t = t.replace(",", ".")                   # decimal comma
    elif nc > 1:
        t = t.replace(",", "")                    # 1,234,567
    elif nd > 1:
        t = t.replace(".", "")                    # 1.234.567
    try:
        v = float(t + exp)
    except ValueError:
        return None
    return v if math.isfinite(v) else None


# ----------------------------------------------------------------------------- sniffing
def comma_decimal(lines, sep) -> bool:
    """Decimal comma? Only when comma is not the delimiter and numbers like 12,34 outnumber 12.34."""
    n = k = 0
    for ln in lines[:400]:
        for p in (ln.split() if sep == " " else ln.split(sep)):
            p = p.strip().strip('"')
            if re.fullmatch(r"[+-]?\d+,\d+([eE][+-]?\d+)?", p):
                k += 1
            elif re.fullmatch(r"[+-]?\d+\.\d+([eE][+-]?\d+)?", p):
                n += 1
    return k > n


def sniff_sep(lines: list[str]) -> str:
    """Delimiter among tab, `;`, `,` and space: the one giving the most rows with the same number of numeric fields."""
    sample = [ln for ln in lines if ln.strip()][:400]
    best, score = " ", -1
    for sep in ("\t", ";", ",", " "):
        counts = {}
        for ln in sample:
            parts = split(ln, sep)
            if len(parts) >= 2 and sum(isnum(p) for p in parts) >= 2:
                counts[len(parts)] = counts.get(len(parts), 0) + 1
        if not counts:
            continue
        n, c = max(counts.items(), key=lambda kv: kv[1])
        sc = c * (1.2 if sep != " " else 1.0) + 0.01 * n
        if sep == "," and any(comma_decimal(sample, s) for s in (";", "\t", " ")):
            sc *= 0.3                     # decimal comma with another delimiter: comma is not the delimiter
        if sc > score:
            best, score = sep, sc
    return best


def data_block(lines: list[str], sep: str) -> tuple[int, int, int]:
    """Longest run of consecutive lines with the same number of mostly numeric fields: (start, end, ncol)."""
    best = (0, 0, 0)
    i, N = 0, len(lines)
    while i < N:
        parts = split(lines[i], sep)
        nnum = sum(isnum(p) for p in parts)
        if len(parts) >= 2 and nnum >= 2 and nnum >= len(parts) - 2:
            j = i + 1
            ncol = len(parts)
            while j < N:
                pj = split(lines[j], sep)
                if not lines[j].strip():
                    break
                if abs(len(pj) - ncol) > 1 or sum(isnum(p) for p in pj) < 2:
                    break
                j += 1
            if j - i > best[1] - best[0]:
                best = (i, j, ncol)
            i = j
        else:
            i += 1
    return best


# ----------------------------------------------------------------------------- headers and units
_UNIT_IN = re.compile(r"\s*(?:\(([^()]*)\)|\[([^\[\]]*)\]|/\s*([^/;,\t]+)$|\bin\s+(\S+)$)\s*$")


def name_unit(h: str) -> tuple[str, str]:
    """`T (°C)`, `m [mg]`, `t / min`, `Masse in mg` -> (name, unit)."""
    h = h.strip().strip('"')
    m = _UNIT_IN.search(h)
    if m:
        unit = next(g for g in m.groups() if g is not None).strip()
        return h[:m.start()].strip(), unit
    return h, ""


# A unit row has mostly unit-like tokens. Single letters that are also common column names (m, t, T, c, x, y, A)
# are left out on purpose, so a header row "t T m" is not taken for units.
UNIT_ROW_GENERAL = re.compile(
    r"^\[?\(?("
    r"s|sec|min|h|d|ms|µs|us|°c|°f|k|mk|"
    r"mg|g|kg|µg|ug|ng|%|‰|ppm|ppb|"
    r"mol|mmol|µmol|umol|mol/l|mmol/l|µmol/l|umol/l|mol/kg|mol/m3|mol/m³|g/l|mg/l|µg/l|ug/l|g/ml|g/cm3|g/cm³|kg/m3|kg/m³|"
    r"l|ml|µl|ul|m3|m³|cm3|cm³|mm|cm|nm|µm|um|"
    r"pa|kpa|mpa|gpa|hpa|bar|mbar|atm|torr|mmhg|psi|"
    r"v|mv|µv|uv|ma|µa|ua|ω|ohm|s/m|ms/cm|µs/cm|us/cm|"
    r"j|kj|j/mol|kj/mol|j/g|j/\(mol\*?k\)|w|mw|w/g|mw/mg|"
    r"n|kn|mn|n/mm2|n/mm²|"
    r"1/s|s-1|s⁻¹|1/min|min-1|1/cm|cm-1|cm⁻¹|"
    r"%/min|mg/min|ml/min|°c/min|k/min|l/min|"
    r"au|a\.u\.|abs|-|–|1"
    r")\)?\]?$", re.I)


def is_unit_row(parts: list[str], pattern: re.Pattern | None = None) -> bool:
    """True when at least half (and at least two) of the non-empty tokens look like units."""
    pat = pattern or UNIT_ROW_GENERAL
    toks = [p.strip() for p in parts if p.strip()]
    if not toks:
        return False
    return sum(bool(pat.match(t)) for t in toks) >= max(2, len(toks) // 2)


def norm_unit(u: str) -> str:
    """Lower case, no spaces, deg/º → °, µ/μ → u (for comparing unit spellings)."""
    u = (u or "").strip().lower().replace(" ", "").replace("deg", "°").replace("º", "°")
    u = u.replace("°°", "°").replace("µ", "u").replace("μ", "u")
    return u


# ----------------------------------------------------------------------------- one call
def sniff(text: str) -> dict:
    """First guess for a text table: delimiter, decimal comma, data block, header row and unit row.

    Returns {"sep", "dec_comma", "start", "end", "ncol", "header": index | None, "units": index | None}
    (indices into `text.splitlines()`)."""
    lines = text.splitlines()
    sep = sniff_sep(lines)
    dec = comma_decimal(lines, sep) if sep != "," else False
    i, j, ncol = data_block(lines, sep)
    header = units = None
    k = i - 1
    while k >= 0 and not lines[k].strip():
        k -= 1
    if k >= 0 and is_unit_row(split(lines[k], sep)):
        units, k = k, k - 1
        while k >= 0 and not lines[k].strip():
            k -= 1
    if k >= 0:
        parts = split(lines[k], sep)
        if len(parts) >= max(2, ncol - 1) and sum(isnum(p) for p in parts) < 2:
            header = k
    return {"sep": sep, "dec_comma": dec, "start": i, "end": j, "ncol": ncol, "header": header, "units": units}
