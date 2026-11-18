"""DP-03: every format opens into the same sheet model; files survive a restart in the environment."""
from __future__ import annotations

import datetime as dt
import importlib.util
import io
import json
import sys
import threading
import unittest
from unittest import mock
import urllib.error
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "sdk" / "python"))

from daten import readers as R  # noqa: E402
from daten import sheet as SH  # noqa: E402

HAS_PYARROW = importlib.util.find_spec("pyarrow") is not None      # Parquet is optional
HEAD = ["Zeit", "Temperatur", "Probe"]
UNITS = ["min", "°C", ""]
ROWS = [[0, 25.5, "A"], [5, 30.25, "A"], [10, 1234.5, "B"]]
EXPECT = [["Zeit", "Temperatur", "Probe"], ["min", "°C", None], ["0", "25.5", "A"], ["5", "30.25", "A"],
          ["10", "1234.5", "B"]]


def grid(sh):
    w = sh.window(0, sh.rows, 0, sh.cols)
    return w["v"]


def xlsx_bytes():
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Messung"
    for r in [HEAD, UNITS] + ROWS:
        ws.append([v if v != "" else None for v in r])
    ws2 = wb.create_sheet("Extras")
    ws2["A1"] = "Titel über zwei Spalten"
    ws2.merge_cells("A1:B1")
    ws2["A2"] = 2
    ws2["B2"] = "=A2*2"                      # openpyxl stores no value: formula without stored result
    ws2["A3"] = dt.datetime(2026, 11, 17, 8, 30)
    ws2["B3"] = "#DIV/0!"
    ws2["A4"] = "12,5"                       # number stored as text
    ws2["B4"] = True
    ws3 = wb.create_sheet("Versteckt")
    ws3["A1"] = 1
    ws3.sheet_state = "hidden"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def ods_bytes():
    def cell(v):
        if v in ("", None):
            return "<table:table-cell/>"
        if isinstance(v, (int, float)):
            return f'<table:table-cell office:value-type="float" office:value="{v}"><text:p>{v}</text:p></table:table-cell>'
        return f'<table:table-cell office:value-type="string"><text:p>{v}</text:p></table:table-cell>'
    rows = "".join(f"<table:table-row>{''.join(cell(v) for v in r)}</table:table-row>" for r in [HEAD, UNITS] + ROWS)
    rows += '<table:table-row table:number-rows-repeated="1048000"><table:table-cell table:number-columns-repeated="1024"/></table:table-row>'
    merged = ('<table:table table:name="Zwei"><table:table-row><table:table-cell table:number-columns-spanned="2" '
              'office:value-type="string"><text:p>Kopf</text:p></table:table-cell><table:covered-table-cell/></table:table-row>'
              '<table:table-row><table:table-cell table:number-columns-repeated="2" office:value-type="float" office:value="7"/>'
              '</table:table-row></table:table>')
    content = ('<?xml version="1.0" encoding="UTF-8"?><office:document-content '
               'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
               'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
               'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><office:spreadsheet>'
               f'<table:table table:name="Messung">{rows}</table:table>{merged}</office:spreadsheet></office:body>'
               '</office:document-content>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mimetype", "application/vnd.oasis.opendocument.spreadsheet")
        z.writestr("content.xml", content)
    return buf.getvalue()


def ods_doc(tables: str) -> bytes:
    content = ('<?xml version="1.0" encoding="UTF-8"?><office:document-content '
               'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
               'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
               'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><office:spreadsheet>'
               f'{tables}</office:spreadsheet></office:body></office:document-content>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mimetype", "application/vnd.oasis.opendocument.spreadsheet")
        z.writestr("content.xml", content)
    return buf.getvalue()


def parquet_bytes():
    import pyarrow as pa
    import pyarrow.parquet as pq
    t = pa.table({"Zeit": [0, 5, 10], "Temperatur": [25.5, 30.25, 1234.5], "Probe": ["A", "A", "B"]})
    buf = pa.BufferOutputStream()
    pq.write_table(t, buf)
    return buf.getvalue().to_pybytes()


class FormatsTest(unittest.TestCase):
    def test_same_grid_from_every_format(self):
        de = "Zeit;Temperatur;Probe\nmin;°C;\n0;25,5;A\n5;30,25;A\n10;1.234,5;B\n"
        en = "Zeit,Temperatur,Probe\nmin,°C,\n0,25.5,A\n5,30.25,A\n10,\"1,234.5\",B\n"
        tsv = de.replace(";", "\t")
        cases = {
            "csv de": R.load_bytes(de.encode("cp1252"), "lauf.csv")[0],
            "csv en": R.load_bytes(en.encode("utf-8"), "lauf.csv")[0],
            "tsv utf16": R.load_bytes(tsv.encode("utf-16"), "lauf.txt")[0],
            "paste": R.read_paste(tsv)[0],
            "xlsx": R.load_bytes(xlsx_bytes(), "mappe.xlsx")[0],
            "ods": R.load_bytes(ods_bytes(), "mappe.ods")[0],
        }
        for k, sh in cases.items():
            self.assertEqual(grid(sh), EXPECT, k)
            self.assertEqual(sh.typ[2, 1], SH.NUM, k)
            self.assertEqual(sh.num[4, 1], 1234.5, k)
        self.assertEqual(cases["csv de"].meta["sep"], ";")
        self.assertTrue(cases["csv de"].meta["dec_comma"])
        self.assertEqual((cases["csv de"].meta["header"], cases["csv de"].meta["units"]), (0, 1))
        no_units = [EXPECT[0]] + EXPECT[2:]
        records = [dict(zip(HEAD, r)) for r in ROWS]
        for d in (records, {k: [r[i] for r in ROWS] for i, k in enumerate(HEAD)},
                  {"columns": HEAD, "data": ROWS}):
            self.assertEqual(grid(R.load_bytes(json.dumps(d).encode(), "t.json")[0]), no_units)
        self.assertEqual(grid(R.load_bytes(json.dumps([HEAD] + ROWS).encode(), "t.json")[0]), no_units)

    @unittest.skipUnless(HAS_PYARROW, "Parquet: pyarrow nicht installiert")
    def test_same_grid_from_parquet(self):
        no_units = [EXPECT[0]] + EXPECT[2:]
        self.assertEqual(grid(R.load_bytes(parquet_bytes(), "t.parquet")[0]), no_units)

    def test_parquet_without_pyarrow_is_a_clean_error(self):
        """pyarrow is optional: without it reading Parquet gives a German ReadError, not ModuleNotFoundError."""
        with mock.patch.dict(sys.modules, {"pyarrow": None, "pyarrow.parquet": None}):
            with self.assertRaises(R.ReadError) as cm:
                R.load_bytes(b"PAR1\x00\x00PAR1", "t.parquet")
        self.assertEqual(str(cm.exception), R.PARQUET_MISSING)
        self.assertIn("pip install pyarrow", R.PARQUET_MISSING)

    def test_ods_long_empty_runs_keep_positions(self):
        """A value after more than 1024 repeated empty cells stays in its column (was moved left before 0.3.0)."""
        row = ('<table:table-row><table:table-cell office:value-type="float" office:value="1"><text:p>1</text:p>'
               '</table:table-cell><table:table-cell table:number-columns-repeated="1500"/>'
               '<table:table-cell office:value-type="float" office:value="2"><text:p>2</text:p></table:table-cell>'
               '</table:table-row>')
        sh = R.load_bytes(ods_doc(f'<table:table table:name="Breit">{row}</table:table>'), "breit.ods")[0]
        self.assertEqual(sh.cols, 1502)
        self.assertEqual((sh.num[0, 0], sh.num[0, 1501]), (1.0, 2.0))
        many = ('<table:table-row table:number-rows-repeated="200000"><table:table-cell office:value-type="float" '
                'office:value="3"><text:p>3</text:p></table:table-cell></table:table-row>')
        sh = R.load_bytes(ods_doc(f'<table:table table:name="Lang">{many}</table:table>'), "lang.ods")[0]
        self.assertEqual(sh.rows, R.MAX_ODS_REPEAT)
        self.assertTrue(sh.meta.get("truncated"))
        self.assertTrue(any("200000" in n.replace("'", "").replace(" ", "") for n in sh.notes), sh.notes)

    def test_time_zones(self):
        """Datetimes with a time zone are stored as UTC seconds; naive ones as wall-clock time."""
        utc = dt.datetime(2024, 3, 31, 0, 30, tzinfo=dt.timezone(dt.timedelta(hours=1)))
        t, x, _ = SH.classify(utc)
        self.assertEqual(t, SH.DATE)
        self.assertEqual(x, (dt.datetime(2024, 3, 30, 23, 30) - dt.datetime(1970, 1, 1)).total_seconds())
        t, x, _ = SH.classify(dt.datetime(2024, 3, 31, 0, 30))
        self.assertEqual(x, (dt.datetime(2024, 3, 31, 0, 30) - dt.datetime(1970, 1, 1)).total_seconds())

    def test_xlsx_details(self):
        sheets = R.load_bytes(xlsx_bytes(), "mappe.xlsx")
        self.assertEqual([s.name for s in sheets], ["Messung", "Extras", "Versteckt"])
        ex = sheets[1]
        self.assertEqual(ex.merged, [[0, 0, 0, 1]])
        self.assertEqual(ex.typ[1, 1], SH.FORMULA)
        self.assertEqual(ex.text[(1, 1)], "=A2*2")
        self.assertTrue(any("B2" in n and "Formel" in n for n in ex.notes))
        self.assertEqual(ex.typ[2, 0], SH.DATE)
        self.assertEqual(ex.display(2, 0), "2026-11-17 08:30:00")
        self.assertEqual(ex.num[2, 0], (dt.datetime(2026, 11, 17, 8, 30) - dt.datetime(1970, 1, 1)).total_seconds())
        self.assertEqual(ex.typ[2, 1], SH.ERROR)
        self.assertEqual((ex.typ[3, 0], ex.num[3, 0]), (SH.TEXT, 12.5))       # text that reads as a number
        self.assertEqual((ex.typ[3, 1], ex.display(3, 1)), (SH.BOOL, "TRUE"))
        self.assertIn("ausgeblendet", " ".join(sheets[2].notes))

    def test_ods_repeats_and_spans(self):
        sheets = R.load_bytes(ods_bytes(), "mappe.ods")
        self.assertEqual(sheets[0].rows, 5)                 # trailing repeated empty rows are not materialised
        self.assertEqual(sheets[1].merged, [[0, 0, 0, 1]])
        self.assertEqual(grid(sheets[1]), [["Kopf", None], ["7", "7"]])

    def test_xls_if_writer_available(self):
        try:
            import xlwt  # noqa: F401
        except ImportError:
            self.skipTest("kein xls-Schreiber installiert; xlrd-Pfad wird mit echten .xls-Dateien geprüft")

    def test_refusals_and_refs(self):
        with self.assertRaises(R.ReadError):
            R.load_bytes(b"", "x.csv")
        with self.assertRaises(R.ReadError):
            R.load_bytes(b"{\"a\": 1}", "x.json")
        with self.assertRaises(R.ReadError):
            R.load_bytes(b"PK\x03\x04garbage", "x.xlsx")
        self.assertEqual(SH.ref(0, 0), "A1")
        self.assertEqual(SH.ref(9, 27), "AB10")
        self.assertEqual(SH.parse_ref("$AB$10"), (9, 27))
        self.assertEqual(SH.range_ref(2, 0, 5, 1), "A3:B6")

    def test_large_sheet(self):
        n = 100_000
        text = "t;c\n" + "\n".join(f"{i};{i * 0.5}".replace(".", ",") for i in range(n))
        sh = R.read_text(text, "gross.csv")[0]
        self.assertEqual((sh.rows, sh.cols), (n + 1, 2))
        self.assertEqual(sh.num[n, 1], (n - 1) * 0.5)
        w = sh.window(50_000, 50_010, 0, 2)
        self.assertEqual(w["v"][0], ["49999", "24999.5"])


class ServerTest(unittest.TestCase):
    def setUp(self):
        from daten import server as S
        self.S = S
        self.tmp = TemporaryDirectory()
        self.start()

    def start(self):
        S = self.S
        S.STATE = S.State(Path(self.tmp.name))
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def stop(self):
        self.srv.shutdown()
        self.srv.server_close()

    def tearDown(self):
        self.stop()
        self.tmp.cleanup()

    def post(self, path, obj=None, raw=None, origin=None):
        data = raw if raw is not None else json.dumps(obj or {}).encode()
        req = urllib.request.Request(self.base + path, data=data, method="POST",
                                     headers={"Content-Type": "application/json", **({"Origin": origin} if origin else {})})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_load_cells_restart(self):
        st, j = self.post("/api/load?name=mappe.xlsx", raw=xlsx_bytes())
        self.assertEqual(st, 200, j)
        f = j["files"][0]
        self.assertEqual([s["name"] for s in f["sheets"]], ["Messung", "Extras", "Versteckt"])
        st, j = self.post("/api/paste", {"text": "a\tb\n1\t2,5\n", "name": "Aus Excel"})
        self.assertEqual(st, 200, j)
        pid = j["files"][0]["id"]
        st, w = self.post("/api/cells", {"id": f["id"], "sheet": 0, "r0": 2, "r1": 4, "c0": 0, "c1": 3})
        self.assertEqual(w["v"], [["0", "25.5", "A"], ["5", "30.25", "A"]])
        self.assertEqual(w["t"][0], [SH.NUM, SH.NUM, SH.TEXT])
        st, j = self.post("/api/cells", {"id": f["id"], "sheet": 7})
        self.assertEqual(st, 404)
        st, j = self.post("/api/cells", {"id": "nix"})
        self.assertEqual(st, 404)
        st, j = self.post("/api/load?name=x.json", raw=b"{\"a\": 1}")
        self.assertEqual(st, 400)
        st, j = self.post("/api/meta", origin="https://evil.example")
        self.assertEqual(st, 403)
        self.post("/api/rename", {"id": pid, "name": "Kinetik"})
        # restart: files come back from the environment, with their names
        self.stop()
        self.start()
        st, j = self.post("/api/env/open", {})
        self.assertEqual(st, 200, j)
        names = sorted(x["name"] for x in j["items"])
        self.assertEqual(names, ["Kinetik", "mappe"])
        back = next(x for x in j["items"] if x["name"] == "Kinetik")
        st, w = self.post("/api/cells", {"id": back["id"], "sheet": 0, "r0": 0, "r1": 2, "c0": 0, "c1": 2})
        self.assertEqual(w["v"], [["a", "b"], ["1", "2.5"]])
        self.assertEqual(back["id"], pid)
        st, _ = self.post("/api/remove", {"id": pid})
        self.stop()
        self.start()
        st, j = self.post("/api/env/open", {})
        self.assertEqual([x["name"] for x in j["items"]], ["mappe"])

    def test_page_and_assets(self):
        for p in ("/", "/labui.js", "/laboverview.js", "/api/meta"):
            with urllib.request.urlopen(self.base + p, timeout=30) as r:
                self.assertEqual(r.status, 200)
        meta = json.loads(urllib.request.urlopen(self.base + "/api/meta", timeout=30).read())
        self.assertIn(".xlsx", meta["accept"])


if __name__ == "__main__":
    unittest.main()
