"""Golden tests for report bundles (folio-lab-bundle/1): reduce a bundle to a stable, readable snapshot and compare
it with a stored reference.

Snapshot content:
- top-level fields (module, title, slug, lang, summary, ...), without the build time ("created");
- the item list (kind, id, caption/title, label, cites, ...); for the values item only key and plain value;
- every text file (.tex, .bib, ...) as lines with trailing whitespace stripped;
- CSV data: header, row count, first and last row; numbers in those rows are compared to 6 significant digits, and
  |x| < 1e-12 counts as 0 (floating-point noise such as 3.7e-17 instead of 1.2e-17 differs between numpy builds);
- figures and other binary files: type and size only, compared within a factor of 2 (BINARY_RATIO). Matplotlib
  output is not byte-stable, and the same figure differs by about 30 % in size between matplotlib releases (font
  subsetting); a factor of 2 still catches an empty or missing plot;
- the source: request (long number lists shortened) and the names and sizes of the source files.
Volatile strings (date-time stamps, absolute paths, random hex ids) are replaced by placeholders; the build time
("created") is dropped.

Use in a module test::

    import labgolden
    labgolden.check(bundle.build(...), Path(__file__).parent / "golden" / "x_de.json")

With the environment variable FOLIO_GOLDEN_UPDATE=1 the reference is (re)written instead of compared.
"""
from __future__ import annotations

import base64
import copy
import difflib
import json
import os
import re
import sys
from pathlib import Path

UPDATE_ENV = "FOLIO_GOLDEN_UPDATE"
TEXT_EXT = {".tex", ".bib", ".txt", ".md", ".json"}
BINARY_RATIO = 2.0
CSV_DIGITS = 6
CSV_ZERO = 1e-12
MAX_DIFF_LINES = 80

# Plain dates are kept: the data carry fixed dates (urldate/accessed of sources, measurement dates) that must not be
# confused with "today". Builders put the build time only into "created", which the snapshot drops.
_VOLATILE = [
    (re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?([+-]\d{2}:?\d{2}|Z)?"), "<timestamp>"),
    (re.compile(r"(?<![A-Za-z0-9\\])[A-Za-z]:[\\/](?:[^\\/\s\"'{}]+[\\/])+[^\s\"'{}]*"), "<path>"),   # C:\x\y, D:/x/y
    (re.compile(r"(?<![\w.])/(?:Users|home|tmp|var|private)/[^\s\"'{}]*"), "<path>"),
    (re.compile(r"\b[0-9a-f]{32}\b|\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"), "<id>"),
]


def scrub(s: str) -> str:
    for rx, rep in _VOLATILE:
        s = rx.sub(rep, s)
    return s


def _scrub_all(o, shorten: bool = False):
    """Scrub every string in a JSON-like structure; with shorten, long number lists become '<n numbers>'."""
    if hasattr(o, "tolist") and not isinstance(o, (str, bytes)):          # numpy arrays and scalars
        o = o.tolist()
    if isinstance(o, str):
        return scrub(o)
    if isinstance(o, dict):
        return {str(k): _scrub_all(v, shorten) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        if shorten and len(o) > 12 and all(v is None or isinstance(v, (int, float)) for v in o):
            return f"<{len(o)} numbers>"
        return [_scrub_all(v, shorten) for v in o]
    if isinstance(o, float) and o != o:
        return "NaN"
    return o


def _lines(text: str) -> list[str]:
    out = [scrub(l.rstrip()) for l in text.replace("\r\n", "\n").split("\n")]
    while out and not out[-1]:
        out.pop()
    return out


def _file_entry(name: str, data: bytes) -> dict:
    ext = os.path.splitext(name)[1].lower()
    if ext in TEXT_EXT:
        return {"type": ext[1:], "lines": _lines(data.decode("utf-8"))}
    if ext == ".csv":
        rows = [r for r in data.decode("utf-8").replace("\r\n", "\n").split("\n") if r.strip()]
        return {"type": "csv", "header": rows[0] if rows else "", "rows": max(0, len(rows) - 1),
                "first": scrub(rows[1]) if len(rows) > 1 else None, "last": scrub(rows[-1]) if len(rows) > 2 else None}
    return {"type": ext[1:] or "bin", "size": len(data)}


def _item(it: dict) -> dict:
    it = dict(it)
    if it.get("kind") == "values":
        it["values"] = [[v.get("key"), v.get("text")] for v in it.get("values") or []]
    return _scrub_all(it)


def snapshot(bundle: dict) -> dict:
    """Stable, readable reduction of a bundle dict (see module docstring)."""
    top = {k: _scrub_all(v) for k, v in bundle.items() if k not in ("created", "items", "files", "source")}
    files = {name: _file_entry(name, base64.b64decode(b64)) for name, b64 in sorted((bundle.get("files") or {}).items())}
    src = bundle.get("source") or {}
    source = {"request": _scrub_all(src.get("request") or {}, shorten=True),
              "files": {n: {"size": len(base64.b64decode(v))} for n, v in sorted((src.get("files") or {}).items())}}
    return {"bundle": top, "items": [_item(i) for i in bundle.get("items") or []], "files": files, "source": source}


def dumps(snap: dict) -> str:
    return json.dumps(snap, ensure_ascii=False, sort_keys=True, indent=1) + "\n"


def _num_cell(c: str) -> str:
    try:
        v = float(c)
    except ValueError:
        return c
    if v != v or v in (float("inf"), float("-inf")):
        return c
    if abs(v) < CSV_ZERO:
        return "0"
    return f"{v:.{CSV_DIGITS}g}"


def _norm_row(row):
    """CSV row with every number rounded to CSV_DIGITS significant digits (compare only; the stored text is kept)."""
    if not isinstance(row, str):
        return row
    return ",".join(_num_cell(c) for c in row.split(","))


def compare(snap: dict, ref: dict, ratio: float = BINARY_RATIO) -> str:
    """Empty string if equal; otherwise a short report with a unified diff of the differing part."""
    a, b = copy.deepcopy(snap), copy.deepcopy(ref)
    problems = []
    fa, fb = a.get("files") or {}, b.get("files") or {}
    for name in sorted(set(fa) & set(fb)):
        x, y = fa[name], fb[name]
        if x.get("type") == "csv" and y.get("type") == "csv":
            for k in ("first", "last"):
                x[k], y[k] = _norm_row(x.get(k)), _norm_row(y.get(k))
        if "size" in x and "size" in y and "lines" not in x:
            lo, hi = sorted((max(x["size"], 1), max(y["size"], 1)))
            if hi > ratio * lo:
                problems.append(f"{name}: size {x['size']} B, reference {y['size']} B (more than a factor {ratio:g})")
            x["size"] = y["size"] = "<within tolerance>"
    ta, tb = dumps(a), dumps(b)
    if ta != tb:
        diff = list(difflib.unified_diff(tb.splitlines(), ta.splitlines(), "reference", "current", n=2, lineterm=""))
        if len(diff) > MAX_DIFF_LINES:
            diff = diff[:MAX_DIFF_LINES] + [f"... ({len(diff) - MAX_DIFF_LINES} more diff lines)"]
        problems.append("\n".join(diff))
    return "\n".join(problems)


def check(bundle: dict, ref_path, ratio: float = BINARY_RATIO) -> None:
    """Compare the bundle with the reference file; with FOLIO_GOLDEN_UPDATE=1 write the reference instead.

    Raises AssertionError (with a unified diff) on a mismatch or a missing reference."""
    ref_path = Path(ref_path)
    snap = snapshot(bundle)
    if os.environ.get(UPDATE_ENV) == "1":
        ref_path.parent.mkdir(parents=True, exist_ok=True)
        ref_path.write_text(dumps(snap), encoding="utf-8", newline="\n")
        print(f"[labgolden] reference written: {ref_path.name}", file=sys.stderr)
        return
    if not ref_path.exists():
        raise AssertionError(f"reference {ref_path} missing; create it with {UPDATE_ENV}=1")
    ref = json.loads(ref_path.read_text(encoding="utf-8"))
    msg = compare(json.loads(dumps(snap)), ref, ratio)
    if msg:
        raise AssertionError(f"bundle differs from {ref_path.name} (regenerate with {UPDATE_ENV}=1 if intended):\n{msg}")
