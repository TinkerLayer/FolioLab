"""Measurement uncertainty in datasets: ± columns → standard u, repeats, formula columns (GUM row by row), type-B
columns from an instrument spec, report and server routes."""
from __future__ import annotations

import base64
import math
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "sdk" / "python"))

import labdataset as DS  # noqa: E402

from daten import bundle as B  # noqa: E402
from daten import clean as C  # noqa: E402
from daten import datasets as D  # noqa: E402
from daten import readers as R  # noqa: E402
from daten import recipe as RC  # noqa: E402
from daten import uncert as UC  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_readers import ServerTest  # noqa: E402


def ds_FL(u_type="U", u_k=2):
    return DS.from_columns("p", [
        {"key": "F", "name": "F", "unit": "N", "role": "y", "u": "uF", "values": [100.0, 200.0, 300.0]},
        {"key": "uF", "name": "U(F)", "unit": "N", "role": "uncertainty", "values": [2.0, 4.0, None],
         "u_type": u_type, **({"u_k": u_k} if u_type == "U" else {})},
        {"key": "L", "name": "L", "unit": "mm", "role": "x", "u": "uL", "values": [10.0, 20.0, 30.0]},
        {"key": "uL", "name": "u(L)", "unit": "µm", "role": "uncertainty", "values": [50.0, 50.0, 50.0], "u_type": "u"}])


class Conversion(unittest.TestCase):
    def test_factors(self):
        self.assertEqual(UC.factor({"u_type": "U", "u_k": 2})[0], 0.5)
        self.assertIn("U/k", UC.factor({"u_type": "U", "u_k": 2})[1])
        self.assertAlmostEqual(1 / UC.factor({"u_type": "ci", "u_level": 95})[0], 1.959964, places=5)
        self.assertEqual(UC.factor({"u_type": "sd"})[0], 1.0)
        self.assertEqual(UC.factor({"u_type": "se"})[0], 1.0)
        self.assertIsNone(UC.factor({"u_type": ""})[0])
        self.assertIn("nicht angegeben", UC.factor({})[1])

    def test_pm_column_converts(self):
        sh = R.load_bytes("t;m\r\n;g\r\n1;1,5 ± 0,2\r\n2;2,5 ± 0,4\r\n3;3,5\r\n".encode("utf-8"), "t.csv")[0]
        steps = RC.guess(sh) + [{"op": "colprop", "series": 1, "u_type": "U", "u_k": 2}]
        ds = RC.to_dataset(RC.extract(sh, steps), "U", [], steps, "x")
        u, how = UC.std_u(ds.columns, ds.data, "m")
        np.testing.assert_allclose(u, [0.1, 0.2, np.nan])
        self.assertIn("k = 2", how)
        self.assertIn("→ u = U/k", " ".join(c["text"] for c in C.checks(ds)))
        u, _ = UC.std_u(ds_FL().columns, ds_FL().data, "L")         # u column in µm, values in mm
        np.testing.assert_allclose(u, [0.05] * 3)
        self.assertIsNone(UC.std_u(ds_FL("").columns, ds_FL("").data, "F")[0])   # type not stated: not used

    def test_repeats(self):
        vals = [10.1, 10.3, 9.9, 10.0, 10.2]
        r = UC.repeats(vals)
        s = float(np.std(vals, ddof=1))
        self.assertAlmostEqual(r["mean"], 10.1)
        self.assertAlmostEqual(r["s"], s)
        self.assertAlmostEqual(r["u"], s / math.sqrt(5))
        self.assertEqual((r["n"], r["dof"]), (5, 4))
        with self.assertRaises(UC.UncColError):
            UC.repeats([1.0])


class Derived(unittest.TestCase):
    def test_formula_column_u_matches_hand(self):
        d0 = ds_FL()
        ds = D.derive(d0, [{"op": "formula", "name": "W", "expr": "F*L", "unit": "J"}], "w")
        w = ds.col("W")
        uc = ds.col(w["u"])
        self.assertEqual((uc["u_type"], uc["role"], uc["unit"]), ("u", "uncertainty", "J"))
        F, L = np.array([100.0, 200.0]), np.array([0.010, 0.020])
        hand = np.hypot(L * np.array([1.0, 2.0]), F * 50e-6)          # u(F) = U/2; u(L) = 50 µm
        np.testing.assert_allclose(ds.data[w["u"]][:2], hand, rtol=1e-6)
        self.assertTrue(np.isnan(ds.data[w["u"]][2]))                   # no stated u(F) in row 3
        self.assertIn("GUM", ds.header["provenance"]["steps"][0]["text"])
        # a constant without u and a column without u: only the column with u counts
        ds2 = D.derive(d0, [{"op": "formula", "name": "s", "expr": "F/A0", "unit": "MPa",
                             "consts": [{"sym": "A0", "value": "10", "unit": "mm²"}]}], "s")
        np.testing.assert_allclose(ds2.data[ds2.col("s")["u"]][:2], [0.1, 0.2], rtol=1e-6)
        ds3 = D.derive(d0, [{"op": "formula", "name": "W", "expr": "F*L", "unit": "J", "unc": False}], "w")
        self.assertNotIn("u", ds3.col("W"))

    def test_constant_from_project_index(self):
        c = {"sym": "A0", "value": "10", "unit": "mm²", "u": "0.5", "index": "g-1", "from": "Projektindex g-1 · rechner"}
        d0 = DS.from_columns("p", [{"key": "F", "name": "F", "unit": "N", "role": "y", "values": [100.0, 200.0]}])
        ds = D.derive(d0, [{"op": "formula", "name": "s", "expr": "F/A0", "unit": "MPa", "consts": [c]}], "s")
        s = ds.col("s")
        np.testing.assert_allclose(ds.data["s"], [10.0, 20.0])
        np.testing.assert_allclose(ds.data[s["u"]], [0.5, 1.0], rtol=1e-6)          # u(s)/s = u(A0)/A0 = 5 %
        text = ds.header["provenance"]["steps"][0]["text"]
        self.assertIn("Projektindex g-1", text)
        self.assertIn("± 0.5", text)
        self.assertIn("u(A0)", text)
        self.assertEqual(ds.header["provenance"]["ops"][0]["consts"][0]["index"], "g-1")
        with self.assertRaisesRegex(D.DeriveError, "ergibt"):                       # wrong dimension: refused
            D.derive(d0, [{"op": "formula", "name": "s", "expr": "F/A0", "unit": "MPa",
                           "consts": [{**c, "unit": "mm"}]}], "s")
        with self.assertRaisesRegex(D.DeriveError, "Summe|Formel"):
            D.derive(d0, [{"op": "formula", "name": "s", "expr": "F + A0", "unit": "N", "consts": [c]}], "s")

    def test_type_b_column(self):
        d0 = DS.from_columns("d", [{"key": "d", "name": "d", "unit": "mm", "values": [5.0, 6.0, None]}])
        ds = D.derive(d0, [{"op": "unc", "col": "d", "parts": [{"kind": "limits", "a": 0.03, "dist": "rect"}]}], "b")
        ub = ds.col(ds.col("d")["u"])
        self.assertEqual((ub["name"], ub["u_type"]), ("u_B(d)", "u"))
        np.testing.assert_allclose(ds.data[ub["key"]][:2], [0.03 / math.sqrt(3)] * 2)
        # instrument class from the shared library (calliper, MPE 0,02 mm + reading 0,005 mm, rectangular)
        ds = D.derive(d0, [{"op": "unc", "col": "d", "parts": [{"kind": "instrument", "id": "messschieber-001"}]}], "b")
        np.testing.assert_allclose(ds.data[ds.col("d")["u"]][0], math.hypot(0.02, 0.005) / math.sqrt(3), rtol=1e-9)
        # with a stated ± already: u_B plus a combined column, linked
        d1 = ds_FL("u")
        ds = D.derive(d1, [{"op": "unc", "col": "F", "parts": [{"kind": "rel", "pct": 1, "dist": "rect"}]}], "c")
        tot = ds.col(ds.col("F")["u"])
        self.assertIn("gesamt", tot["name"])
        np.testing.assert_allclose(ds.data[tot["key"]][:2], [math.hypot(2, 1 / math.sqrt(3)), math.hypot(4, 2 / math.sqrt(3))])


class Report(unittest.TestCase):
    def test_bundle_shows_u_columns_and_method(self):
        ds = D.derive(ds_FL(), [{"op": "formula", "name": "W", "expr": "F*L", "unit": "J"}], "w")
        b = B.build(ds, {"share": "s1", "version": 1}, {"lang": "de"}, None)
        self.assertTrue(any(i.get("id") == "unsicherheiten" for i in b["items"]))
        txt = base64.b64decode(b["files"]["text-methodik.tex"]).decode("utf-8")
        self.assertIn("Standardunsicherheiten", txt)
        self.assertIn("unc-jcgm100", txt)
        self.assertIn("Fortpflanzungsgesetz", txt)
        self.assertIn("4.3.3", txt)                                   # which conversion
        en = B.build(ds, {"share": "s1", "version": 1}, {"lang": "en"}, None)
        self.assertIn("standard uncertainties", base64.b64decode(en["files"]["text-methodik.tex"]).decode("utf-8"))


class Routes(ServerTest):
    test_load_cells_restart = test_page_and_assets = None

    def test_labunc_and_repeat(self):
        import urllib.request
        with urllib.request.urlopen(self.base + "/labunc.js") as r:
            self.assertIn(b"LabUnc", r.read())
        st, j = self.post("/api/unc/instruments", {})
        self.assertEqual(st, 200, j)
        self.assertTrue(j["items"])
        st, j = self.post("/api/load?name=r.csv", raw="x;y\n10,1;1\n10,3;1\n9,9;1\n10,0;1\n10,2;1\n".encode("utf-8"))
        fid = j["files"][0]["id"]
        st, r = self.post("/api/repeat", {"id": fid, "sheet": 0, "ranges": [{"r0": 0, "c0": 0, "r1": 5, "c1": 0}]})
        self.assertEqual(st, 200, r)
        self.assertEqual((r["n"], r["dof"]), (5, 4))
        self.assertAlmostEqual(r["u"], float(np.std([10.1, 10.3, 9.9, 10.0, 10.2], ddof=1)) / math.sqrt(5))


if __name__ == "__main__":
    unittest.main()
