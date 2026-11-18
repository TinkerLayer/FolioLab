"""DP-09 templates and batches, DP-10 exports (re-import gives the same dataset) and the report bundle."""
from __future__ import annotations

import base64
import importlib.util
import io
import json
import math
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "sdk" / "python"))

import labdataset as DS  # noqa: E402

from daten import bundle as B  # noqa: E402
from daten import datasets as D  # noqa: E402
from daten import export as X  # noqa: E402
from daten import readers as R  # noqa: E402
from daten import recipe as RC  # noqa: E402
from daten import templates as T  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_readers import ServerTest  # noqa: E402

HAS_PYARROW = importlib.util.find_spec("pyarrow") is not None      # Parquet is optional


def device_file(n_rows: int, T_set: float, header=("Zeit", "Temperatur", "Masse"), header_row: int = 4) -> bytes:
    """An instrument export: metadata above, header and units lines, numbers until the end."""
    import openpyxl
    w = openpyxl.Workbook()
    ws = w.active
    ws["A1"] = "Gerät: TG 209"
    ws["A2"] = "Ofentemperatur:"
    ws["B2"] = T_set
    ws["C2"] = "°C"
    for c, h in enumerate(header, start=1):
        ws.cell(header_row, c, h)
        ws.cell(header_row + 1, c, ["min", "°C", "mg"][c - 1])
    for i in range(n_rows):
        ws.cell(header_row + 2 + i, 1, i * 0.5)
        ws.cell(header_row + 2 + i, 2, 25 + 10 * i)
        ws.cell(header_row + 2 + i, 3, round(12.0 - 0.01 * i, 4))
    b = io.BytesIO()
    w.save(b)
    return b.getvalue()


def sheet(raw: bytes):
    return R.load_bytes(raw, "x.xlsx")[0]


class TemplateTest(unittest.TestCase):
    """Done when: a template from file A reads B and C and refuses a file with a moved header."""

    def test_template_reads_b_and_c_refuses_moved_header(self):
        a = sheet(device_file(10, 600))
        steps = RC.guess(a)
        tpl = {"name": "TG 209", "steps": steps, "anchors": T.anchors(a, steps)}
        self.assertIn({"cell": "A4", "text": "Zeit", "what": "header"}, tpl["anchors"])
        self.assertTrue(any(x["what"] == "meta" for x in tpl["anchors"]))
        for n, Tset in ((25, 650), (4, 700)):                          # B longer, C shorter than A
            s = sheet(device_file(n, Tset))
            st = T.apply(s, tpl)
            t = RC.extract(s, st)
            self.assertEqual(t["rows"], n)
            self.assertEqual([(c["name"], c["unit"]) for c in t["columns"]], [("Zeit", "min"), ("Temperatur", "°C"), ("Masse", "mg")])
            self.assertEqual(t["conditions"]["Ofentemperatur"]["value"], float(Tset))
        moved = sheet(device_file(10, 600, header_row=6))
        with self.assertRaises(T.TemplateError) as cm:
            T.apply(moved, tpl)
        self.assertIn("A4", str(cm.exception))
        self.assertTrue(cm.exception.problems)
        renamed = sheet(device_file(10, 600, header=("Zeit", "T", "Masse")))
        probs = T.check(renamed, tpl)
        self.assertEqual([(p["cell"], p["expected"], p["found"]) for p in probs], [("B4", "Temperatur", "T")])

    def test_combine_with_file_column(self):
        parts = []
        for n, Tset in ((5, 600), (3, 650)):
            s = sheet(device_file(n, Tset))
            parts.append((f"Lauf {Tset}", RC.extract(s, RC.guess(s))))
        t = T.combine(parts, "alle")
        self.assertEqual(t["rows"], 8)
        self.assertEqual(t["columns"][0]["name"], "Datei")
        self.assertEqual(list(t["columns"][0]["values"]), ["Lauf 600"] * 5 + ["Lauf 650"] * 3)
        oven = next(c for c in t["columns"] if c["name"] == "Ofentemperatur")    # differs → a column
        np.testing.assert_array_equal(oven["values"], [600] * 5 + [650] * 3)
        ds = RC.to_dataset(t, "alle", [], [], "x")
        self.assertEqual(ds.rows, 8)

    def test_combine_converts_same_quantity(self):
        """Clock times give a different automatic unit per file (min / h): combined in the unit of the first file."""
        def clock(times):
            text = "t;T;c\r\n;°C;mg/L\r\n" + "".join(f"{x};25;{1 + i},5\r\n" for i, x in enumerate(times))
            return R.load_bytes(text.encode("utf-8"), "x.csv")[0]
        a, b = clock(["08:00", "09:00", "10:00", "11:00"]), clock(["12:00", "12:10", "12:20"])
        parts = [("A", RC.extract(a, RC.guess(a))), ("B", RC.extract(b, RC.guess(b)))]
        self.assertNotEqual(parts[0][1]["columns"][0]["unit"], parts[1][1]["columns"][0]["unit"])
        t = T.combine(parts, "beide")
        tc = next(c for c in t["columns"] if c["name"] == "t")
        self.assertEqual(tc["unit"], parts[0][1]["columns"][0]["unit"])
        np.testing.assert_allclose(tc["values"][4:], [0, 10 / 60, 20 / 60], atol=1e-12)
        self.assertTrue(any("umgerechnet" in n for n in t["notes"]))
        bad = clock(["08:00", "09:00"])
        bad_t = RC.extract(bad, RC.guess(bad))
        bad_t["columns"][2]["unit"] = "s"
        with self.assertRaises(T.TemplateError):
            T.combine([parts[0], ("C", bad_t)], "x")
        # a column only one file has (here u(c) from "1,5 ± 0,1") is kept; the other file leaves it empty
        pm = R.load_bytes("t;T;c\r\n;°C;mg/L\r\n08:00;25;1,5 ± 0,1\r\n08:30;25;2,5\r\n".encode("utf-8"), "y.csv")[0]
        t2 = T.combine([("PM", RC.extract(pm, RC.guess(pm))), parts[1]], "u")
        uc = next(c for c in t2["columns"] if c["name"] == "u(c)")
        np.testing.assert_allclose(uc["values"], [0.1, np.nan, np.nan, np.nan, np.nan], equal_nan=True)
        self.assertEqual(uc["of"], next(c for c in t2["columns"] if c["name"] == "c")["key"])
        self.assertTrue(any("fehlt in" in n for n in t2["notes"]))
        self.assertEqual(RC.to_dataset(t2, "u", [], [], "x").col("c")["u"], uc["key"])


def sample_ds():
    return DS.from_columns("Kinetik A", [
        {"key": "t", "name": "t", "unit": "min", "role": "x", "values": [0, 5, 10, 15, 20]},
        {"key": "c", "name": "c", "unit": "mmol/L", "role": "y", "u": "u_c", "values": [10.0, 7.8, None, 4.7, 3.65]},
        {"key": "u_c", "name": "u(c)", "unit": "mmol/L", "role": "uncertainty", "values": [0.1, 0.1, 0.1, 0.12, 0.1]},
        {"key": "T", "name": "T", "unit": "°C", "kind": "temperature", "values": [25.0, 25.1, 24.9, 25.0, 25.2]},
        {"key": "probe", "name": "Probe", "dtype": "text", "role": "label", "values": ["a", "b", "c", "d", "e"]}],
        flags=[{"row": 3, "col": "c", "code": "outlier", "rule": "Grubbs", "excluded": True, "reason": "Luftblase"}],
        provenance={"files": [{"name": "kin.xlsx", "sha256": "ab" * 32, "sheet": "M"}],
                    "recipe": [{"op": "block", "range": "A3:E7"}], "module_version": "0.2.0"})


class ExportTest(unittest.TestCase):
    """Done when: exports re-import to the same dataset."""

    def test_round_trips(self):
        ds = sample_ds()
        for fmt, ext in (("csv", ".csv"), ("xlsx", ".xlsx"), ("json", ".json")) + ((("parquet", ".parquet"),) if HAS_PYARROW else ()):
            raw, mime = X.export(ds, fmt)
            back = X.reimport(raw, "export" + ext)
            self.assertEqual(X.same(ds, back), [], fmt)
        back = X.reimport(X.to_json(ds), "x.json")                         # JSON keeps flags and provenance
        self.assertEqual(back.header["flags"], ds.header["flags"])
        self.assertEqual(back.header["data_hash"], ds.header["data_hash"])
        sh = R.load_bytes(X.to_json(ds), "x.json")[0]                       # opened in the page: names + units lines
        self.assertEqual(sh.display(1, 1), "mmol/L")

    def test_csv_keeps_cleaning_state(self):
        ds = sample_ds()
        lines = X.to_csv(ds).decode("utf-8").splitlines()
        self.assertEqual(lines[0].split(",")[-2:], [X.CSV_USED, X.CSV_FLAGS])
        self.assertTrue(lines[4].endswith(",0,Ausreisser in c (ausgeschlossen: Luftblase)"), lines[4])
        self.assertTrue(lines[1].endswith(",1,"))
        self.assertNotIn(X.CSV_USED, X.to_csv(ds, flags=False).decode("utf-8").splitlines()[0])
        back = X.reimport(X.to_csv(ds), "e.csv")                            # the two columns are not data
        self.assertEqual(X.same(ds, back), [])

    @unittest.skipUnless(HAS_PYARROW, "Parquet: pyarrow nicht installiert")
    def test_parquet_round_trip(self):
        ds = sample_ds()
        back = X.reimport(X.export(ds, "parquet")[0], "e.parquet")
        self.assertEqual(X.same(ds, back), [])

    def test_parquet_without_pyarrow(self):
        with mock.patch.dict(sys.modules, {"pyarrow": None, "pyarrow.parquet": None}):
            with self.assertRaises(ValueError) as cm:
                X.export(sample_ds(), "parquet")
        self.assertEqual(str(cm.exception), "Parquet braucht das Python-Paket pyarrow (pip install pyarrow).")

    def test_xlsx_protocol_sheet(self):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(X.to_xlsx(sample_ds())))
        self.assertEqual(wb.sheetnames, ["Daten", "Protokoll"])
        text = "\n".join(" | ".join(str(c) for c in r if c is not None) for r in wb["Protokoll"].iter_rows(values_only=True))
        self.assertIn("kin.xlsx", text)
        self.assertIn("Luftblase", text)
        self.assertIn("Ausreisser", text)
        self.assertEqual(wb["Daten"]["B2"].value, "mmol/L")


class BundleTest(unittest.TestCase):
    def test_bundle_pieces_and_pdflatex_safety(self):
        d0 = sample_ds()
        ds = D.derive(d0, [{"op": "outliers", "method": "grubbs", "col": "T"},
                           {"op": "smooth", "col": "c", "window": 3, "order": 1}], "Kinetik A bereinigt")
        b = B.build(ds, {"share": "abc123", "version": 4}, {"lang": "de"}, lambda s: str(s.get("op")))
        kinds = {i["kind"] for i in b["items"]}
        self.assertTrue({"figure", "table", "data", "values", "text", "citation"} <= kinds)
        files = {k: base64.b64decode(v) for k, v in b["files"].items()}
        txt = files["text-methodik.tex"].decode("utf-8")
        self.assertIn("Version 4", txt)
        self.assertIn("abc123", txt)
        self.assertIn("kin.xlsx", txt)
        self.assertIn("SHA-256", txt)
        self.assertIn("Luftblase", txt)
        self.assertIn(r"\cite{grubbs1969", txt)
        for name, data in files.items():
            if name.endswith((".tex", ".bib")):
                s = data.decode("utf-8")
                s.encode("latin-1")                                       # pdfLaTeX-safe
                for bad in (r"\text{", r"\ce{", r"\tfrac", r"\boldsymbol"):
                    self.assertNotIn(bad, s, name)
        csv = files["data/daten.csv"].decode()                            # pgfplots: comma, point decimals
        head = csv.splitlines()[0].split(",")
        self.assertEqual(head[:2], ["t", "c"])
        self.assertIn("used", head)
        self.assertEqual(csv.splitlines()[2].split(",")[:2], ["5", "7.8"])
        data_item = next(i for i in b["items"] if i["kind"] == "data")
        self.assertEqual(data_item["plot"]["x"], "t")
        bib = files["refs.bib"].decode()
        self.assertIn("10.1021/ac60214a047", bib)                       # Savitzky–Golay
        # Refresh rebuilds from the dataset kept in the bundle (same version even if the share changed)
        again = B.rebuild_dataset(b["source"])
        self.assertEqual(again.header["data_hash"], ds.header["data_hash"])
        b_en = B.build(ds, {"share": "abc123", "version": 4}, {"lang": "en", "include": {"figures": False}}, None)
        self.assertNotIn("figure", {i["kind"] for i in b_en["items"]})
        # provenance for the hub: version of this process, what the source files are, Refresh mode (default pin)
        from daten import __version__
        self.assertEqual((b["module_version"], b["source"]["kind"], b["source"]["request"]["mode"]),
                         (__version__, "dataset", "pin"))
        self.assertIn("nist", bib)                                       # Grubbs: NIST/SEMATECH e-Handbook
        self.assertIn("10.18434/M32189", bib)
        self.assertIn("Art der angegebenen Unsicherheit: c: nicht angegeben", txt)

    def test_bundle_states_uncertainty_type_and_refresh_note(self):
        d0 = sample_ds()
        d0 = DS.from_columns(d0.header["title"], [{**c, **({"u_type": "U", "u_k": 2} if c["key"] == "u_c" else {}),
                                                   "values": d0.data[c["key"]].tolist()} for c in d0.columns],
                             flags=d0.header["flags"], provenance=d0.header["provenance"])
        b = B.build(d0, {"share": "s-00000001", "version": 3}, {"lang": "de", "mode": "live"}, None,
                    note="Aktualisiert: Datensatz s-00000001 von Version 2 auf die neueste Version 3")
        txt = base64.b64decode(b["files"]["text-methodik.tex"]).decode("utf-8")
        self.assertIn("erweiterte Unsicherheit U (k = 2)", txt)
        self.assertIn("von Version 2 auf die neueste Version 3", txt)
        self.assertIn("folgt der neuesten Version", b["summary"])
        self.assertEqual(b["source"]["request"]["mode"], "live")


class ShareServerTest(ServerTest):
    test_load_cells_restart = test_page_and_assets = None

    def load(self, raw, name):
        st, j = self.post(f"/api/load?name={name}", raw=raw)
        self.assertEqual(st, 200, j)
        return j["files"][0]["id"]

    def test_template_batch_export_bundle(self):
        a, b_, c, moved = (self.load(device_file(10, 600), "a.xlsx"), self.load(device_file(20, 650), "b.xlsx"),
                           self.load(device_file(6, 700), "c.xlsx"), self.load(device_file(8, 600, header_row=6), "d.xlsx"))
        st, g = self.post("/api/recipe/guess", {"id": a, "sheet": 0})
        st, t = self.post("/api/tpl/save", {"id": a, "sheet": 0, "steps": g["steps"], "name": "TG 209"})
        self.assertEqual(st, 200, t)
        tid = t["template"]["id"]
        st, lst = self.post("/api/tpl/list", {})
        self.assertEqual([x["name"] for x in lst["templates"]], ["TG 209"])
        st, dup = self.post("/api/tpl/save", {"id": a, "sheet": 0, "steps": g["steps"], "name": "tg 209"})
        self.assertEqual(st, 400)
        st, ap = self.post("/api/tpl/apply", {"template": tid, "id": moved, "sheet": 0})
        self.assertIn("A4", ap["error"])
        st, bt = self.post("/api/tpl/batch", {"template": tid, "items": [{"id": b_}, {"id": c}, {"id": moved}], "mode": "each"})
        self.assertEqual(st, 200, bt)
        ok = [r for r in bt["results"] if r["ok"]]
        self.assertEqual([r["rows"] for r in ok], [20, 6])
        self.assertFalse(bt["results"][2]["ok"])
        st, bt2 = self.post("/api/tpl/batch", {"template": tid, "items": [{"id": b_}, {"id": c}], "mode": "each"})
        self.assertEqual([r["unchanged"] for r in bt2["results"]], [True, True])          # same share, no new version
        st, cb = self.post("/api/tpl/batch", {"template": tid, "items": [{"id": a}, {"id": b_}, {"id": c}], "mode": "combined"})
        self.assertEqual(cb["combined"]["rows"], 36)
        sid = cb["combined"]["share"]
        st, ck = self.post("/api/ds/checks", {"share": sid})
        self.assertEqual(st, 200, ck)
        self.assertEqual(ck["checks"][0]["key"], "rows")
        for fmt in ("csv", "xlsx", "json") + (("parquet",) if HAS_PYARROW else ()):
            st, ex = self.post("/api/ds/export", {"share": sid, "format": fmt})
            self.assertEqual(st, 200, ex)
            self.assertTrue(ex["filename"].endswith("." + fmt))
            self.assertGreater(len(base64.b64decode(ex["data"])), 50)
        # pyarrow is optional: without it a Parquet export is a clean 400 with the German message, not a 500
        with mock.patch.dict(sys.modules, {"pyarrow": None, "pyarrow.parquet": None}):
            st, ex = self.post("/api/ds/export", {"share": sid, "format": "parquet"})
        self.assertEqual(st, 400, ex)
        self.assertEqual(ex["error"], X.PARQUET_MISSING)
        self.assertNotIn("ModuleNotFoundError", str(ex))
        st, ex = self.post("/api/ds/export", {"share": sid, "format": "pdf"})
        self.assertEqual(st, 400, ex)
        st, ex = self.post("/api/ds/export", {"share": sid, "format": "csv", "flags": False})
        self.assertEqual(st, 200, ex)
        self.assertNotIn(X.CSV_FLAGS, base64.b64decode(ex["data"]).decode("utf-8").splitlines()[0])
        st, bu = self.post("/api/bundle", {"share": sid, "lang": "de"})
        self.assertEqual(st, 200, bu)
        self.assertEqual(bu["module"], "datenaufbereitung")
        st, rb = self.post("/api/bundle/rebuild", {"source": bu["source"], "lang": "en"})
        self.assertEqual(st, 200, rb)
        self.assertEqual(rb["lang"], "en")
        # Refresh: a pinned bundle keeps its version, a live one moves to the newest version and says so
        st, live = self.post("/api/bundle", {"share": sid, "lang": "de", "mode": "live"})
        self.assertEqual(st, 200, live)
        v1 = bu["source"]["request"]["version"]
        st, cb2 = self.post("/api/tpl/batch", {"template": tid, "items": [{"id": a}, {"id": b_}], "mode": "combined",
                                               "share": sid})
        self.assertEqual(st, 200, cb2)
        newest = cb2["combined"]["version"]
        self.assertEqual(cb2["combined"]["share"], sid)
        self.assertGreater(newest, v1)
        st, rp = self.post("/api/bundle/rebuild", {"source": bu["source"]})
        self.assertEqual(rp["source"]["request"]["version"], v1)
        st, rl = self.post("/api/bundle/rebuild", {"source": live["source"]})
        self.assertEqual(st, 200, rl)
        self.assertEqual(rl["source"]["request"]["version"], newest)
        self.assertIn(f"von Version {v1} auf die neueste Version {newest}", rl["summary"])
        self.assertIn(f"Version {newest}", base64.b64decode(rl["files"]["text-methodik.tex"]).decode("utf-8"))
        st, dl = self.post("/api/tpl/delete", {"template": tid})
        st, lst = self.post("/api/tpl/list", {})
        self.assertEqual(lst["templates"], [])


if __name__ == "__main__":
    unittest.main()
