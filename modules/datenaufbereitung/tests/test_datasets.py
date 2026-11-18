"""DP-M4/M5: datasets from manual sheets – new version only on change, open, derived datasets (N → MPa)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "sdk" / "python"))

import labdataset as DS  # noqa: E402

from daten import datasets as D  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_readers import ServerTest  # noqa: E402

AREA = [{"sym": "A0", "value": "12,57", "unit": "mm²"}]
STEPS = [{"op": "unit", "range": "A1", "unit": "N"}, {"op": "unit", "range": "B1", "unit": "mm"}]


def parent():
    return DS.from_columns("Zug", [
        {"key": "F", "name": "F", "unit": "N", "role": "x", "values": [0.0, 1257.0, 2514.0]},
        {"key": "dL", "name": "ΔL", "unit": "mm", "role": "y", "values": [0.0, 0.1, 0.2]},
        {"key": "T", "name": "T", "unit": "°C", "kind": "temperature", "values": [20.0, 21.0, 22.0]}])


class DeriveTest(unittest.TestCase):
    def test_formula_n_to_mpa_replaces_column(self):
        ds = D.derive(parent(), [{"op": "formula", "name": "σ", "key": "sigma", "expr": "F / A0", "unit": "MPa",
                                  "consts": AREA, "replaces": "F"}], "Spannung")
        self.assertEqual([c["key"] for c in ds.columns], ["sigma", "dL", "T"])
        self.assertEqual(ds.col("sigma")["role"], "x")                     # takes the place of F
        np.testing.assert_allclose(ds.data["sigma"], [0.0, 100.0, 200.0])
        self.assertEqual(ds.col("sigma")["kind"], "pressure")
        keep = D.derive(parent(), [{"op": "formula", "name": "σ", "expr": "F / A0", "unit": "MPa", "consts": AREA,
                                    "replaces": "F", "keep": True}], "Spannung")
        self.assertEqual([c["key"] for c in keep.columns], ["F", "sigma", "dL", "T"])     # σ → sigma

    def test_convert_and_refusals(self):
        ds = D.derive(parent(), [{"op": "convert", "col": "F", "unit": "kN"}, {"op": "convert", "col": "T", "unit": "K"},
                                 {"op": "convert", "col": "dL", "unit": "µm", "keep": True}], "x")
        np.testing.assert_allclose(ds.data["F"], [0.0, 1.257, 2.514])
        np.testing.assert_allclose(ds.data["T"], [293.15, 294.15, 295.15])
        self.assertEqual([c["unit"] for c in ds.columns], ["kN", "mm", "µm", "K"])
        with self.assertRaisesRegex(D.DeriveError, "Formel"):
            D.derive(parent(), [{"op": "convert", "col": "F", "unit": "MPa"}], "x")
        with self.assertRaisesRegex(D.DeriveError, "nicht MPa"):                # F / A0 in mm is no pressure
            D.derive(parent(), [{"op": "formula", "name": "s", "expr": "F / A0", "unit": "MPa",
                                 "consts": [{"sym": "A0", "value": "12", "unit": "mm"}]}], "x")
        with self.assertRaises(D.DeriveError):
            D.derive(parent(), [{"op": "formula", "name": "s", "expr": "__import__('os')", "unit": ""}], "x")
        with self.assertRaisesRegex(D.DeriveError, "Spalte"):
            D.derive(parent(), [{"op": "formula", "name": "x", "expr": "F", "unit": "N", "consts": [{"sym": "F", "value": 1}]}], "x")


class DatasetServerTest(ServerTest):
    test_load_cells_restart = test_page_and_assets = None          # run once, in test_readers

    def sheet(self):
        st, j = self.post("/api/manual/new", {"name": "Zugprobe"})
        iid = j["files"][0]["id"]
        w = [{"r": 0, "c": 0, "v": "F"}, {"r": 0, "c": 1, "v": "dL"}]
        for i, (f, d) in enumerate([("0", "0"), ("1257", "0,1"), ("2514", "0,2")]):
            w += [{"r": 1 + i, "c": 0, "v": f}, {"r": 1 + i, "c": 1, "v": d}]
        self.post("/api/manual/write", {"id": iid, "sheet": 0, "writes": w})
        st, g = self.post("/api/recipe/guess", {"id": iid, "sheet": 0})
        return iid, g["steps"] + STEPS

    def test_publish_versions_open_and_live_child(self):
        iid, steps = self.sheet()
        st, p = self.post("/api/ds/publish", {"id": iid, "sheet": 0, "steps": steps, "title": "Zugprobe 1"})
        self.assertEqual(st, 200, p)
        sid = p["share"]
        self.assertEqual((p["version"], p["unchanged"]), (1, False))
        st, p2 = self.post("/api/ds/publish", {"id": iid, "sheet": 0, "steps": steps, "title": "Zugprobe 1", "share": sid})
        self.assertEqual((p2["share"], p2["version"], p2["unchanged"]), (sid, 1, True))      # nothing changed
        # derived: σ = F / A0, live
        ops = [{"op": "formula", "name": "σ", "key": "sigma", "expr": "F / A0", "unit": "MPa", "consts": AREA, "replaces": "F"}]
        st, pv = self.post("/api/ds/preview", {"share": sid, "ops": ops})
        self.assertEqual(st, 200, pv)
        self.assertAlmostEqual(pv["page"]["values"]["sigma"][2], 200.0)
        st, dv = self.post("/api/ds/derive", {"share": sid, "ops": ops, "title": "Spannung", "mode": "live"})
        self.assertEqual(st, 200, dv)
        child = dv["share"]
        # a new value in the sheet → new parent version → the live child follows
        self.post("/api/manual/write", {"id": iid, "sheet": 0, "writes": [{"r": 4, "c": 0, "v": "3771"}, {"r": 4, "c": 1, "v": "0,3"}]})
        st, g = self.post("/api/recipe/guess", {"id": iid, "sheet": 0})
        st, p3 = self.post("/api/ds/publish", {"id": iid, "sheet": 0, "steps": g["steps"] + STEPS, "title": "Zugprobe 1", "share": sid})
        self.assertEqual((p3["version"], p3["unchanged"]), (2, False))
        self.assertEqual(p3["children"], [{"share": child, "version": 2}])
        st, ls = self.post("/api/ds/list", {})
        rec = {d["id"]: d for d in ls["datasets"]}
        self.assertEqual(rec[child]["derive"]["version"], 2)
        self.assertEqual(rec[child]["columns"][0]["unit"], "MPa")
        self.assertEqual(rec[sid]["origin"]["item"], iid)
        # open as a read-only table
        st, o = self.post("/api/ds/open", {"share": child})
        self.assertEqual(st, 200, o)
        f = o["files"][0]
        self.assertEqual(f["dataset"], {"share": child, "version": 2})
        self.assertFalse(f["manual"])
        st, w = self.post("/api/cells", {"id": f["id"], "sheet": 0, "r0": 0, "r1": 6, "c0": 0, "c1": 2})
        self.assertEqual(w["v"][0], ["σ", "dL"])
        self.assertEqual(w["v"][1], ["MPa", "mm"])
        self.assertEqual(w["v"][5][0], "300")
        # a pinned child does not follow; refresh brings it up to date
        st, pin = self.post("/api/ds/derive", {"share": sid, "ops": [{"op": "convert", "col": "F", "unit": "kN"}],
                                               "title": "kN", "mode": "pin"})
        self.post("/api/manual/write", {"id": iid, "sheet": 0, "writes": [{"r": 5, "c": 0, "v": "5028"}, {"r": 5, "c": 1, "v": "0,4"}]})
        st, g = self.post("/api/recipe/guess", {"id": iid, "sheet": 0})
        st, p4 = self.post("/api/ds/publish", {"id": iid, "sheet": 0, "steps": g["steps"] + STEPS, "title": "Zugprobe 1", "share": sid})
        self.assertNotIn(pin["share"], [c["share"] for c in p4["children"]])
        st, r = self.post("/api/ds/refresh", {"share": pin["share"]})
        self.assertEqual((r["version"], r["unchanged"]), (2, False))
        # a live child whose formula no longer fits (column renamed) keeps its last version and shows the error
        st, bad = self.post("/api/ds/derive", {"share": sid, "ops": [{"op": "formula", "name": "x", "expr": "F * 2", "unit": "N"}], "title": "2F"})
        self.post("/api/manual/write", {"id": iid, "sheet": 0, "writes": [{"r": 0, "c": 0, "v": "Kraft"}]})
        st, g = self.post("/api/recipe/guess", {"id": iid, "sheet": 0})
        st, p5 = self.post("/api/ds/publish", {"id": iid, "sheet": 0, "steps": g["steps"] + STEPS, "title": "Zugprobe 1", "share": sid})
        self.assertIn("F", next(c for c in p5["children"] if c["share"] == bad["share"])["error"])
        st, ls = self.post("/api/ds/list", {})
        rec = {d["id"]: d for d in ls["datasets"]}
        self.assertTrue(rec[bad["share"]]["error"])
        self.assertEqual(rec[bad["share"]]["latest"], 1)
        # only own datasets can be deleted; errors come back as 400
        st, e = self.post("/api/ds/derive", {"share": sid, "ops": [{"op": "convert", "col": "F", "unit": "m"}], "title": "x"})
        self.assertEqual(st, 400)
        st, e = self.post("/api/ds/delete", {"share": pin["share"]})
        self.assertEqual(st, 200, e)

    def test_flag_only_change_is_a_new_version_and_live_child_follows(self):
        """A changed flag or exclusion (same values) gives a new version; the live child is computed again by the
        running module, whose version is recorded (not the version of the first computation)."""
        envs = self.S.STATE.envs
        p1 = D.publish(envs, D.producer(envs, "0.3.0", None, "Test"), parent())
        sid = p1["share"]
        ch = D.make_derived(envs, "0.3.0", sid, [{"op": "convert", "col": "F", "unit": "kN"}], "kN", "live")
        flagged = DS.from_columns("Zug", [{**c, "values": parent().data[c["key"]].tolist()} for c in parent().columns],
                                  flags=[{"row": 2, "col": "dL", "code": "outlier", "excluded": True, "reason": "Riss"}])
        self.assertEqual(flagged.header["data_hash"], parent().header["data_hash"])
        p2 = D.publish(envs, D.producer(envs, "9.9.9", None, "Test"), flagged, sid)
        self.assertEqual((p2["version"], p2["unchanged"]), (2, False))
        self.assertEqual(p2["children"], [{"share": ch["share"], "version": 2}])
        self.assertEqual(D.publish(envs, D.producer(envs, "9.9.9", None, "Test"), flagged, sid)["unchanged"], True)
        cds, cenv = D.load(envs, ch["share"], 2)
        self.assertEqual(cds.header["flags"][0]["reason"], "Riss")
        self.assertEqual(int((~cds.used_mask()).sum()), 1)
        self.assertEqual((cenv["producer"]["module_version"], cds.header["provenance"]["module_version"]), ("9.9.9", "9.9.9"))
        self.assertEqual(D.load(envs, ch["share"], 1)[1]["producer"]["module_version"], "0.3.0")

    def test_connected_table_follows_in_place(self):
        """A dataset opened through a connection from another collection is replaced in place by the next version."""
        iid, steps = self.sheet()
        st, p = self.post("/api/ds/publish", {"id": iid, "sheet": 0, "steps": steps, "title": "Zug"})
        sid = p["share"]
        st, o = self.post("/api/ds/open", {"share": sid, "link": "andere"})
        f = o["files"][0]
        self.assertEqual(f["dataset"], {"share": sid, "version": 1, "link": "andere"})
        self.post("/api/manual/write", {"id": iid, "sheet": 0, "writes": [{"r": 4, "c": 0, "v": "3771"}, {"r": 4, "c": 1, "v": "0,3"}]})
        st, g = self.post("/api/recipe/guess", {"id": iid, "sheet": 0})
        st, p2 = self.post("/api/ds/publish", {"id": iid, "sheet": 0, "steps": g["steps"] + STEPS, "title": "Zug", "share": sid})
        self.assertEqual(p2["version"], 2)
        st, o2 = self.post("/api/ds/open", {"share": sid, "item": f["id"], "link": "andere"})
        self.assertEqual(st, 200, o2)
        self.assertEqual(o2["replaced"], f["id"])
        g2 = o2["files"][0]
        self.assertEqual((g2["id"], g2["name"], g2["dataset"]["version"]), (f["id"], "Zug (v2)", 2))
        st, w = self.post("/api/cells", {"id": f["id"], "sheet": 0, "r0": 0, "r1": 6, "c0": 0, "c1": 2})
        self.assertEqual(w["v"][5][0], "3771")
        st, o3 = self.post("/api/ds/open", {"share": sid, "item": iid})      # not a table of this dataset: a new one
        self.assertNotIn("replaced", o3)
        self.assertNotEqual(o3["files"][0]["id"], iid)


if __name__ == "__main__":
    unittest.main()
