"""Exports of a dataset (DP-10): CSV, XLSX (data + "Protokoll"), JSON (lossless), Parquet.

All exports keep every row (flags never delete rows); exclusions and flags are in the XLSX "Protokoll" sheet and in
JSON. Each export reads back to the same columns, units and values (`reimport`).
"""
from __future__ import annotations

import csv
import io
import json
import math

import numpy as np

import labdataset as DS

FORMATS = {"csv": ("text/csv", ".csv"), "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
           "json": ("application/json", ".json"), "parquet": ("application/vnd.apache.parquet", ".parquet")}
FLAG_NAMES = {"outlier": "Ausreisser", "below_lod": "unter Nachweisgrenze", "above_range": "über Messbereich",
              "missing": "fehlend", "duplicate": "doppelt", "excluded": "ausgeschlossen", "interpolated": "interpoliert",
              "parse_error": "Lesefehler", "note": "Hinweis"}


def head_text(c: dict) -> str:
    return c["name"] + (f" [{c['unit']}]" if c.get("unit") else "")


def _cell(c, v):
    if c["dtype"] == "number":
        f = float(v)
        return None if not math.isfinite(f) else f
    return str(v)


CSV_USED, CSV_FLAGS = "verwendet", "Markierungen"         # the two cleaning-state columns at the end of a CSV


def row_flags(ds: DS.Dataset) -> list[str]:
    """Per row: its flags as text, e.g. "Ausreisser in c (ausgeschlossen: Luftblase); unter Nachweisgrenze in d"."""
    names = {c["key"]: c["name"] for c in ds.columns}
    out = [[] for _ in range(ds.rows)]
    for f in ds.header.get("flags") or []:
        s = FLAG_NAMES.get(f["code"], f["code"]) + (f" in {names.get(f['col'], f['col'])}" if f.get("col") else "")
        if f.get("excluded"):
            s += " (ausgeschlossen" + (f": {f['reason']}" if f.get("reason") else "") + ")"
        elif f.get("reason"):
            s += f" ({f['reason']})"
        out[f["row"]].append(s)
    return ["; ".join(x) for x in out]


def to_csv(ds: DS.Dataset, flags: bool = True) -> bytes:
    """One header line "name [unit]", point decimals, comma separator (what pgfplots and Excel import read).
    With `flags` (default) two columns follow the data: "verwendet" (1 = used, 0 = excluded by a recorded decision)
    and "Markierungen" (every flag of the row with column, exclusion and reason), so the file keeps its cleaning
    state. `reimport` recognises and drops them."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow([head_text(c) for c in ds.columns] + ([CSV_USED, CSV_FLAGS] if flags else []))
    arrs = [ds.data[c["key"]] for c in ds.columns]
    used = ds.used_mask()
    texts = row_flags(ds) if flags else None
    for r in range(ds.rows):
        w.writerow(["" if (x := _cell(c, a[r])) is None else (repr(x) if isinstance(x, float) else x)
                    for c, a in zip(ds.columns, arrs)] + ([1 if used[r] else 0, texts[r]] if flags else []))
    return buf.getvalue().encode("utf-8")


def to_json(ds: DS.Dataset) -> bytes:
    """Lossless: the dataset header (columns, conditions, flags, provenance, hash) and the values."""
    data = {c["key"]: [_cell(c, x) for x in ds.data[c["key"]].tolist()] for c in ds.columns}
    return json.dumps({"schema": DS.SCHEMA, "header": ds.header, "data": data}, ensure_ascii=False).encode("utf-8")


def from_json(raw: bytes) -> DS.Dataset:
    d = json.loads(raw.decode("utf-8"))
    if not isinstance(d, dict) or d.get("schema") != DS.SCHEMA:
        raise DS.DatasetError("Keine Datensatz-Datei (suite.dataset/1)")
    head = d["header"]
    ds = DS.Dataset(head, d["data"])
    if head.get("data_hash") and ds.header["data_hash"] != head["data_hash"]:
        raise DS.DatasetError("Datensatz-Datei: Werte passen nicht zur Prüfsumme")
    return ds


def protocol_rows(ds: DS.Dataset, describe=None) -> list[list]:
    """Lines of the "Protokoll" sheet: title, hash, files, recipe, cleaning steps with counts, conditions, flags."""
    h = ds.header
    rows = [["Datensatz", h["title"]], ["Zeilen", ds.rows], ["Spalten", len(ds.columns)], ["SHA-256 der Daten", h["data_hash"]], []]
    prov = h.get("provenance") or {}
    chain, p = [], prov
    while isinstance(p, dict) and p:
        chain.append(p)
        p = p.get("parent_provenance")
    files = next((x.get("files") for x in chain if x.get("files")), []) or []
    if files:
        rows.append(["Quelldateien", "SHA-256", "Blatt", "Bereiche"])
        rows += [[f.get("name", ""), f.get("sha256", ""), f.get("sheet", ""), ", ".join(f.get("ranges") or [])] for f in files]
        rows.append([])
    recipe = next((x.get("recipe") for x in chain if x.get("recipe")), []) or []
    if recipe:
        rows.append(["Lesen (Rezept)"])
        rows += [[i + 1, describe(s) if describe else json.dumps(s, ensure_ascii=False)] for i, s in enumerate(recipe)]
        rows.append([])
    steps = [s for x in reversed(chain) for s in (x.get("steps") or [])]
    if steps:
        rows.append(["Bereinigen und Umrechnen", "Zeilen vorher", "Zeilen nachher", "Markierungen nachher", "ausgeschlossen nachher"])
        rows += [[s.get("text", s.get("op")), s.get("rows_before"), s.get("rows_after"), s.get("flags_after"),
                  s.get("excluded_after")] for s in steps]
        rows.append([])
    if h.get("conditions"):
        rows.append(["Bedingung", "Wert", "Einheit", "aus"])
        rows += [[k, v.get("value"), v.get("unit", ""), v.get("from", "")] for k, v in h["conditions"].items()]
        rows.append([])
    cut = [t for x in chain for t in (x.get("truncations") or [])]
    if cut:
        rows.append(["GEKÜRZT", "behalten", "insgesamt"])
        rows += [[t.get("what", ""), t.get("kept"), t.get("total")] for t in cut]
        rows.append([])
    ukeys = {c.get("u") for c in ds.columns if c.get("u")}
    rows.append(["Spalte", "Schlüssel", "Einheit", "Grösse", "Rolle", "Symbol", "Hinweis", "Art der Unsicherheit"])
    rows += [[c["name"], c["key"], c.get("unit", ""), c.get("kind", ""), c.get("role", ""), c.get("symbol", ""),
              c.get("note", ""), DS.u_type_text(c) if c.get("role") == "uncertainty" or c["key"] in ukeys else ""]
             for c in ds.columns]
    rows.append([])
    if h.get("flags"):
        names = {c["key"]: c["name"] for c in ds.columns}
        rows.append(["Zeile", "Spalte", "Markierung", "ausgeschlossen", "Grund", "Regel", "Zelltext"])
        rows += [[f["row"] + 1, names.get(f.get("col"), f.get("col", "")), FLAG_NAMES.get(f["code"], f["code"]),
                  "ja" if f.get("excluded") else "", f.get("reason", ""), f.get("rule", ""), f.get("raw", "")]
                 for f in h["flags"][:100_000]]
        if len(h["flags"]) > 100_000:
            rows.append([f"GEKÜRZT: nur die ersten 100000 von {len(h['flags'])} Markierungen gelistet (alle in JSON)"])
    return rows


def to_xlsx(ds: DS.Dataset, describe=None) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    ws = wb.active
    ws.title = "Daten"
    ws.append([c["name"] for c in ds.columns])
    ws.append([c.get("unit", "") for c in ds.columns])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    arrs = [ds.data[c["key"]] for c in ds.columns]
    for r in range(ds.rows):
        ws.append([_cell(c, a[r]) for c, a in zip(ds.columns, arrs)])
    ws.freeze_panes = "A3"
    pr = wb.create_sheet("Protokoll")
    for row in protocol_rows(ds, describe):
        pr.append([("" if x is None else x) for x in row])
    pr.column_dimensions["A"].width = 48
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


PARQUET_MISSING = "Parquet braucht das Python-Paket pyarrow (pip install pyarrow)."


def to_parquet(ds: DS.Dataset) -> bytes:
    """Optional: needs pyarrow (not a requirement of the module); without it a ValueError with a German message."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        raise ValueError(PARQUET_MISSING) from None
    arrays, names = [], []
    for c in ds.columns:
        a = ds.data[c["key"]]
        arrays.append(pa.array(a.astype(float), type=pa.float64(), from_pandas=True) if c["dtype"] == "number"
                      else pa.array([str(x) for x in a.tolist()], type=pa.string()))
        names.append(head_text(c))
    t = pa.Table.from_arrays(arrays, names=names)
    t = t.replace_schema_metadata({b"suite.dataset": json.dumps(ds.header, ensure_ascii=False).encode("utf-8")})
    b = io.BytesIO()
    pq.write_table(t, b)
    return b.getvalue()


def export(ds: DS.Dataset, fmt: str, describe=None, flags: bool = True) -> tuple[bytes, str]:
    if fmt == "csv":
        return to_csv(ds, flags), FORMATS["csv"][0]
    if fmt == "xlsx":
        return to_xlsx(ds, describe), FORMATS["xlsx"][0]
    if fmt == "json":
        return to_json(ds), FORMATS["json"][0]
    if fmt == "parquet":
        return to_parquet(ds), FORMATS["parquet"][0]
    raise ValueError(f"Format „{fmt}“ unbekannt (csv, xlsx, json, parquet)")


def reimport(raw: bytes, fname: str) -> DS.Dataset:
    """Read an export back through the module's own readers and first guess (JSON: directly)."""
    if fname.lower().endswith(".json"):
        try:
            return from_json(raw)
        except (ValueError, KeyError):
            pass
    from . import readers as R
    from . import recipe as RC
    sh = R.load_bytes(raw, fname)[0]
    steps = RC.guess(sh)
    tbl = RC.extract(sh, steps)
    if fname.lower().endswith(".csv"):              # the cleaning-state columns of to_csv are not data
        tbl["columns"] = [c for c in tbl["columns"] if c["name"] not in (CSV_USED, CSV_FLAGS)]
    return RC.to_dataset(tbl, "Import", [], steps, "")


def same(a: DS.Dataset, b: DS.Dataset) -> list[str]:
    """Differences in names, units, types and values (keys may differ: they come from the names)."""
    out = []
    if a.rows != b.rows:
        out.append(f"Zeilen {a.rows} ≠ {b.rows}")
    ca, cb = a.columns, b.columns
    if [(c["name"], c.get("unit", ""), c["dtype"]) for c in ca] != [(c["name"], c.get("unit", ""), c["dtype"]) for c in cb]:
        out.append("Spalten: " + str([(c["name"], c.get("unit", "")) for c in cb]))
        return out
    for x, y in zip(ca, cb):
        va, vb = a.data[x["key"]], b.data[y["key"]]
        if x["dtype"] == "number":
            if not np.array_equal(np.isnan(va), np.isnan(vb)) or not np.allclose(va[~np.isnan(va)], vb[~np.isnan(vb)],
                                                                                    rtol=1e-12, atol=0):
                out.append(f"Werte in {x['name']}")
        elif list(va) != list(vb):
            out.append(f"Texte in {x['name']}")
    return out
