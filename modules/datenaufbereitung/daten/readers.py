"""Readers (DP-03): every format becomes a list of `Sheet`s with the same cell model.

xlsx/xlsm  openpyxl (read-only, stored values); merged ranges, formulas without stored value and hidden sheets
           are taken from the sheet XML and reported
xls        xlrd (DP-Q1)
ods        standard library (zip + XML, streamed)
csv/txt/tsv/dat/asc  labtable sniffing (delimiter, decimal comma, header and units rows as first guess)
json       records, columns, rows or pandas "split"
parquet    pyarrow
paste      text copied from a spreadsheet (tabs) or any delimited text
"""
from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from pathlib import PurePath
from xml.etree import ElementTree as ET

import labtable as LT

from .sheet import MAX_COLS, Builder, Err, Formula, ReadError, Sheet, parse_ref

PARQUET_MISSING = "Parquet braucht das Python-Paket pyarrow (pip install pyarrow)."
MAX_ODS_REPEAT = 100_000           # a filled ODS row repeated more often is read this many times (noted, see read_ods)

TEXT_EXT = {".csv", ".txt", ".tsv", ".dat", ".asc", ".prn"}
EXCEL_EXT = {".xlsx", ".xlsm"}
ACCEPT = sorted(TEXT_EXT | EXCEL_EXT | {".xls", ".ods", ".json", ".parquet"})
MAX_NOTES = 40


def _ext(name: str) -> str:
    return PurePath(name or "").suffix.lower()


def load_bytes(data: bytes, name: str) -> list[Sheet]:
    if not data:
        raise ReadError("Datei ist leer")
    ext = _ext(name)
    if ext in EXCEL_EXT or (data[:2] == b"PK" and ext not in (".ods",) and b"xl/" in data[:4000]):
        return read_xlsx(data, name)
    if ext == ".xls" or data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return read_xls(data, name)
    if ext == ".ods":
        return read_ods(data, name)
    if ext == ".parquet" or data[:4] == b"PAR1":
        return read_parquet(data, name)
    if ext == ".json":
        from .manual import Manual, is_manual
        if is_manual(name):                     # DP-M1: a manual sheet stored in the environment
            return Manual.from_bytes(data).sheets_view()
        return read_json(data, name)
    if ext in TEXT_EXT or not ext:
        return read_text(LT.decode(data), name)
    raise ReadError(f"Format {ext} wird nicht gelesen (möglich: {', '.join(ACCEPT)})")


def _stem(name: str) -> str:
    return (PurePath(name or "Tabelle").stem or "Tabelle")[:60]


# ----------------------------------------------------------------------------- text
def read_text(text: str, name: str) -> list[Sheet]:
    text = text.lstrip("﻿")
    if not text.strip():
        raise ReadError("Datei ist leer")
    lines = text.splitlines()
    g = LT.sniff(text)
    sep = g["sep"]
    if sep == " " and not g["ncol"]:
        sep = "\t" if "\t" in text else ";" if text.count(";") > text.count(",") else ","
    b = Builder(_stem(name), dec_comma=g["dec_comma"], text_numbers=True)
    if sep == " ":
        for ln in lines:
            b.row(ln.split())
    else:
        for row in csv.reader(lines, delimiter=sep):
            b.row([c.strip() for c in row])
    b.meta = {"sep": {"\t": "tab", " ": "space"}.get(sep, sep), "dec_comma": g["dec_comma"],
              "header": g["header"], "units": g["units"], "start": g["start"], "end": g["end"], "ncol": g["ncol"]}
    return [b.sheet()]


def read_paste(text: str, name: str = "Eingefügt") -> list[Sheet]:
    return read_text(text, name)


# ----------------------------------------------------------------------------- xlsx
_NS_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_NS_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_CELL = re.compile(rb'<c r="([A-Z]{1,3}\d{1,7})"(?:[^>/]|/(?!>))*>(.*?)</c>', re.S)
_MERGE = re.compile(rb'<mergeCell ref="([A-Z]{1,3}\d{1,7})(?::([A-Z]{1,3}\d{1,7}))?"')


def _xlsx_parts(z: zipfile.ZipFile) -> dict:
    """Sheet name → (zip part, state) from workbook.xml and its relations."""
    try:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    except (KeyError, ET.ParseError):
        return {}
    target = {r.get("Id"): r.get("Target") for r in rels}
    out = {}
    for s in wb.iter(_NS_MAIN + "sheet"):
        t = target.get(s.get(_NS_REL + "id")) or ""
        t = t.lstrip("/")
        part = t if t.startswith("xl/") else "xl/" + t
        out[s.get("name")] = (part, s.get("state") or "visible")
    return out


def _xml_extras(xml: bytes):
    """Merged ranges and formulas without a stored value, read straight from the sheet XML."""
    merged = []
    for m in _MERGE.finditer(xml):
        r0, c0 = parse_ref(m.group(1).decode())
        r1, c1 = parse_ref((m.group(2) or m.group(1)).decode())
        merged.append([r0, c0, r1, c1])
    formulas = {}
    if b"<f" in xml:
        for m in _CELL.finditer(xml):
            inner = m.group(2)
            if b"<f" in inner and (b"<v>" not in inner or b"<v></v>" in inner):
                f = re.search(rb"<f[^>]*>(.*?)</f>", inner, re.S)
                formulas[parse_ref(m.group(1).decode())] = "=" + (f.group(1).decode("utf-8", "replace") if f else "…")
    return merged, formulas


def read_xlsx(data: bytes, name: str) -> list[Sheet]:
    try:
        import openpyxl
    except ImportError as e:                              # pragma: no cover
        raise ReadError("openpyxl fehlt (pip install openpyxl)") from e
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        parts = _xlsx_parts(z)
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except (zipfile.BadZipFile, KeyError, OSError, ValueError) as e:
        raise ReadError(f"Excel-Datei unlesbar: {e}") from e
    out = []
    try:
        for ws in wb.worksheets:
            b = Builder(ws.title[:60])
            part, state = parts.get(ws.title, (None, "visible"))
            merged, formulas = [], {}
            if part:
                try:
                    merged, formulas = _xml_extras(z.read(part))
                except KeyError:
                    pass
            if state != "visible":
                b.notes.append("Blatt ist in Excel ausgeblendet")
            for r, row in enumerate(ws.iter_rows(values_only=True)):
                vals = list(row)
                for j, v in enumerate(vals):
                    if isinstance(v, str) and v.startswith("#") and v.strip() in _ERRS:
                        vals[j] = Err(v.strip())
                b.row(vals)
            b.merged = merged
            sh = b.sheet()
            if formulas:
                sh = _mark_formulas(sh, formulas)
            out.append(sh)
    finally:
        wb.close()
    if not out:
        raise ReadError("Arbeitsmappe ohne Blätter")
    return out


_ERRS = {"#DIV/0!", "#N/A", "#NAME?", "#NULL!", "#NUM!", "#REF!", "#VALUE!", "#SPILL!", "#CALC!", "#GETTING_DATA"}


def _mark_formulas(sh: Sheet, formulas: dict) -> Sheet:
    """Formulas without a stored value: mark the cells and say so (values must be recalculated in Excel first)."""
    import numpy as np
    from .sheet import FORMULA, ref
    rows = max(sh.rows, 1 + max(r for r, _ in formulas))
    cols = max(sh.cols, 1 + max(c for _, c in formulas))
    if (rows, cols) != (sh.rows, sh.cols):
        num = np.full((rows, cols), np.nan)
        typ = np.zeros((rows, cols), np.uint8)
        num[:sh.rows, :sh.cols], typ[:sh.rows, :sh.cols] = sh.num, sh.typ
        sh.num, sh.typ = num, typ
    for (r, c), f in formulas.items():
        sh.typ[r, c] = FORMULA
        sh.text[(r, c)] = f[:500]
    cells = sorted(formulas)
    sh.notes.append(f"{len(cells)} Formel(n) ohne gespeicherten Wert, z. B. "
                    + ", ".join(ref(r, c) for r, c in cells[:8])
                    + " – in Excel neu berechnen und speichern")
    return sh


# ----------------------------------------------------------------------------- xls
def read_xls(data: bytes, name: str) -> list[Sheet]:
    try:
        import xlrd
    except ImportError as e:                              # pragma: no cover
        raise ReadError("xlrd fehlt (pip install xlrd)") from e
    try:
        book = xlrd.open_workbook(file_contents=data, formatting_info=True, on_demand=True)
    except Exception:  # noqa: BLE001 - formatting_info fails for some files; retry without
        try:
            book = xlrd.open_workbook(file_contents=data, on_demand=True)
        except Exception as e:  # noqa: BLE001
            raise ReadError(f"xls-Datei unlesbar: {e}") from e
    out = []
    for i in range(book.nsheets):
        sh = book.sheet_by_index(i)
        b = Builder(sh.name[:60])
        for r in range(sh.nrows):
            vals = []
            for c in range(sh.ncols):
                t, v = sh.cell_type(r, c), sh.cell_value(r, c)
                if t in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
                    vals.append(None)
                elif t == xlrd.XL_CELL_DATE:
                    try:
                        vals.append(xlrd.xldate.xldate_as_datetime(v, book.datemode))
                    except (ValueError, OverflowError):
                        vals.append(v)
                elif t == xlrd.XL_CELL_BOOLEAN:
                    vals.append(bool(v))
                elif t == xlrd.XL_CELL_ERROR:
                    vals.append(Err(xlrd.error_text_from_code.get(v, "#?")))
                else:
                    vals.append(v)
            b.row(vals)
        b.merged = [[r0, c0, r1 - 1, c1 - 1] for r0, r1, c0, c1 in getattr(sh, "merged_cells", [])]
        if getattr(sh, "visibility", 0):
            b.notes.append("Blatt ist in Excel ausgeblendet")
        out.append(b.sheet())
        book.unload_sheet(i)
    return out


# ----------------------------------------------------------------------------- ods
_T = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
_O = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
_X = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
_DUR = re.compile(r"^-?P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:([\d.]+)S)?$")


def _ods_value(cell):
    vt = cell.get(_O + "value-type")
    if vt in ("float", "percentage", "currency"):
        try:
            return float(cell.get(_O + "value"))
        except (TypeError, ValueError):
            return None
    if vt == "date":
        import datetime as dt
        s = cell.get(_O + "date-value") or ""
        try:
            return dt.datetime.fromisoformat(s) if "T" in s else dt.date.fromisoformat(s)
        except ValueError:
            return s
    if vt == "time":
        m = _DUR.match(cell.get(_O + "time-value") or "")
        if m:
            d, h, mi, s = (float(x or 0) for x in m.groups())
            import datetime as dt
            return dt.timedelta(days=d, hours=h, minutes=mi, seconds=s)
    if vt == "boolean":
        return (cell.get(_O + "boolean-value") or "").lower() == "true"
    txt = "\n".join("".join(p.itertext()) for p in cell.iter(_X + "p"))
    if not vt and cell.get(_T + "formula"):
        return Formula(cell.get(_T + "formula"))
    if txt.startswith("#") and txt.strip() in _ERRS | {"Err:502", "#NAME?"}:
        return Err(txt.strip())
    return txt or None


def read_ods(data: bytes, name: str) -> list[Sheet]:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        f = z.open("content.xml")
    except (zipfile.BadZipFile, KeyError) as e:
        raise ReadError(f"ODS-Datei unlesbar: {e}") from e
    out, b, pending, r = [], None, 0, 0
    try:
        for ev, el in ET.iterparse(f, events=("start", "end")):
            tag = el.tag
            if ev == "start" and tag == _T + "table":
                b, pending, r = Builder((el.get(_T + "name") or f"Tabelle{len(out) + 1}")[:60]), 0, 0
                continue
            if ev != "end" or b is None:
                continue
            if tag == _T + "table-row":
                rep = int(el.get(_T + "number-rows-repeated") or 1)
                vals, c, gap = [], 0, 0
                for cell in el:
                    if cell.tag not in (_T + "table-cell", _T + "covered-table-cell"):
                        continue
                    crep = int(cell.get(_T + "number-columns-repeated") or 1)
                    v = _ods_value(cell) if cell.tag == _T + "table-cell" else None
                    cs, rs = int(cell.get(_T + "number-columns-spanned") or 1), int(cell.get(_T + "number-rows-spanned") or 1)
                    if cs > 1 or rs > 1:
                        b.merged.append([r, c, r + rs - 1, c + cs - 1])
                    if v is None:
                        gap += crep                     # empty cells: only written when a value follows (keeps positions)
                    else:
                        if gap:
                            vals.extend([None] * gap)
                            gap = 0
                        if len(vals) + crep > MAX_COLS:
                            raise ReadError(f"{b.name}: mehr als {MAX_COLS} Spalten (wiederholte Zelle in Zeile {r + 1})")
                        vals.extend([v] * crep)
                    c += crep
                if not vals:
                    pending += rep
                else:
                    if pending:
                        b.empty_rows(pending)
                        pending = 0
                    if rep > MAX_ODS_REPEAT:            # a filled row repeated very often (e.g. to the sheet end)
                        b.notes.append(f"Zeile {r + 1} wiederholt sich {rep}-mal – nur {MAX_ODS_REPEAT}-mal gelesen")
                        b.meta.setdefault("truncated", []).append(
                            {"what": f"Blatt {b.name}, Zeile {r + 1}: wiederholte Zeile", "kept": MAX_ODS_REPEAT, "total": rep})
                    for _ in range(min(rep, MAX_ODS_REPEAT)):
                        b.row(vals)
                r += rep
                el.clear()
            elif tag == _T + "table":
                out.append(b.sheet())
                b = None
                el.clear()
    except ET.ParseError as e:
        raise ReadError(f"ODS-Datei unlesbar: {e}") from e
    if not out:
        raise ReadError("ODS-Datei ohne Tabellen")
    return out


# ----------------------------------------------------------------------------- json
def read_json(data: bytes, name: str) -> list[Sheet]:
    try:
        d = json.loads(LT.decode(data))
    except json.JSONDecodeError as e:
        raise ReadError(f"JSON unlesbar: {e}") from e
    b = Builder(_stem(name))

    def cell(v):
        return json.dumps(v, ensure_ascii=False)[:2000] if isinstance(v, (dict, list)) else v

    if isinstance(d, dict) and d.get("schema") == "suite.dataset/1" and isinstance(d.get("header"), dict) \
            and isinstance(d.get("data"), dict):                                                       # own export
        cols = [c for c in d["header"].get("columns") or [] if isinstance(c, dict) and c.get("key") in d["data"]]
        b.row([str(c.get("name") or c["key"]) for c in cols])
        b.row([str(c.get("unit") or "") for c in cols])
        n = max((len(d["data"][c["key"]]) for c in cols), default=0)
        for i in range(n):
            b.row([d["data"][c["key"]][i] if i < len(d["data"][c["key"]]) else None for c in cols])
    elif isinstance(d, dict) and isinstance(d.get("columns"), list) and isinstance(d.get("data"), list):  # pandas split
        b.row([str(c) for c in d["columns"]])
        for row in d["data"]:
            b.row([cell(v) for v in (row if isinstance(row, list) else [row])])
    elif isinstance(d, dict) and d and all(isinstance(v, list) for v in d.values()):            # columns
        keys = list(d)
        b.row(keys)
        for i in range(max(len(v) for v in d.values())):
            b.row([cell(d[k][i]) if i < len(d[k]) else None for k in keys])
    elif isinstance(d, list) and d and all(isinstance(x, dict) for x in d):                      # records
        keys = []
        for x in d:
            keys.extend(k for k in x if k not in keys)
        b.row(keys)
        for x in d:
            b.row([cell(x.get(k)) for k in keys])
    elif isinstance(d, list) and d and all(isinstance(x, list) for x in d):                      # rows
        for x in d:
            b.row([cell(v) for v in x])
    else:
        raise ReadError("JSON: erwartet werden Datensätze [{…}], Spalten {name: […]}, Zeilen [[…]] "
                        "oder {columns, data}")
    return [b.sheet()]


# ----------------------------------------------------------------------------- parquet
def read_parquet(data: bytes, name: str) -> list[Sheet]:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as e:                              # optional dependency (README, methods page)
        raise ReadError(PARQUET_MISSING) from e
    try:
        t = pq.read_table(pa.BufferReader(data))
    except Exception as e:  # noqa: BLE001
        raise ReadError(f"Parquet unlesbar: {e}") from e
    b = Builder(_stem(name))
    b.row(t.column_names)
    cols = [t.column(i).to_pylist() for i in range(t.num_columns)]
    for i in range(t.num_rows):
        b.row([c[i] for c in cols])
    return [b.sheet()]
