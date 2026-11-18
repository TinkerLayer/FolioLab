"""DP-M1…M3: manual sheets ("Einzelmessergebnisse"), sequential entry values, units on ranges."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "sdk" / "python"))

from daten import manual as M  # noqa: E402
from daten import recipe as RC  # noqa: E402
from daten import sheet as SH  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_readers import ServerTest  # noqa: E402


def col(tbl, name):
    return next(c for c in tbl["columns"] if c["name"] == name)


class ManualModelTest(unittest.TestCase):
    def test_write_undo_padding_roundtrip(self):
        m = M.Manual()
        before = m.write(0, [{"r": 0, "c": 0, "v": "F"}, {"r": 0, "c": 1, "v": "t"}, {"r": 1, "c": 0, "v": "12,5"},
                             {"r": 1, "c": 1, "v": "0.5"}, {"r": 2, "c": 0, "v": "n.d."}])
        self.assertEqual(before[0], {"r": 0, "c": 0, "v": ""})
        self.assertEqual(m.rev, 1)
        sh = m.sheet(0)
        self.assertEqual((sh.rows, sh.cols), (M.MIN_ROWS, M.MIN_COLS))       # looks like an empty spreadsheet
        self.assertEqual(sh.meta["used"], [3, 2])
        self.assertEqual((int(sh.typ[1, 0]), float(sh.num[1, 0])), (SH.NUM, 12.5))
        self.assertEqual(int(sh.typ[2, 0]), SH.TEXT)
        # undo = writing the previous values back
        b2 = m.write(0, [{"r": 1, "c": 0, "v": "13"}])
        m.write(0, b2)
        self.assertEqual(m.sheets[0]["cells"][(1, 0)], "12,5")
        m.write(0, [{"r": 2, "c": 0, "v": ""}])
        self.assertNotIn((2, 0), m.sheets[0]["cells"])
        k = m.add_sheet()
        self.assertEqual(m.sheets[k]["name"], "Messung 2")
        m.rename_sheet(k, "Probe/2")
        back = M.Manual.from_bytes(m.to_bytes())
        self.assertEqual(back.sheets[0]["cells"], m.sheets[0]["cells"])
        self.assertEqual([s["name"] for s in back.sheets], ["Messung 1", "Probe_2"])
        self.assertEqual(back.rev, m.rev)
        big = m.write(0, [{"r": 300, "c": 30, "v": "1"}])
        self.assertEqual(big[0]["v"], "")
        self.assertEqual((m.sheet(0).rows, m.sheet(0).cols), (301 + M.PAD_ROWS, 31 + M.PAD_COLS))

    def test_refusals(self):
        m = M.Manual()
        for bad in ([], [{"r": -1, "c": 0, "v": "1"}], [{"r": 0, "c": M.MAX_COLS, "v": "1"}], [{"x": 1}]):
            with self.assertRaises(M.ManualError):
                m.write(0, bad)
        with self.assertRaises(M.ManualError):
            m.remove_sheet(0)
        with self.assertRaises(SH.ReadError):
            M.Manual.from_bytes(b'{"format": "andere"}')

    def test_parse_entry(self):
        self.assertEqual(M.parse_entry("12,5"), (12.5, "", "12,5"))
        self.assertEqual(M.parse_entry("12.5 N"), (12.5, "N", "12.5"))
        self.assertEqual(M.parse_entry("1,2E-3 mm²"), (0.0012, "mm²", "1,2E-3"))
        self.assertEqual(M.parse_entry("3 kN"), (3.0, "kN", "3"))
        self.assertEqual(M.parse_entry("n.d."), (None, "", "n.d."))
        self.assertEqual(M.parse_entry("12 Äpfel")[0], None)                 # not a unit → kept as text
        self.assertEqual(M.parse_entry(""), (None, "", ""))


class ManualRecipeTest(unittest.TestCase):
    def sheet(self):
        m = M.Manual()
        w = [{"r": 0, "c": 0, "v": "F"}, {"r": 0, "c": 1, "v": "t"}]
        for i in range(10):
            w.append({"r": 1 + i, "c": 0, "v": f"{100 + 10 * i},5"})
        for i in range(8):                                                  # second column shorter
            w.append({"r": 1 + i, "c": 1, "v": str(i * 2)})
        m.write(0, w)
        return m.sheet(0)

    def test_columns_of_different_length_and_units(self):
        sh = self.sheet()
        steps = RC.guess(sh, loose=True)
        self.assertIn({"op": "block", "range": "A2:B11"}, steps)
        steps += [{"op": "unit", "range": "A2:A11", "unit": "N"}, {"op": "unit", "range": "B1:B9", "unit": "s"}]
        t = RC.extract(sh, steps)
        self.assertEqual(t["rows"], 10)
        self.assertEqual([(c["name"], c["unit"], c["role"]) for c in t["columns"]], [("F", "N", "x"), ("t", "s", "y")])
        self.assertTrue(np.isnan(col(t, "t")["values"][9]))
        # later assignment wins; empty unit removes; name range renames
        t2 = RC.extract(sh, steps + [{"op": "unit", "range": "A5", "unit": "kN"}, {"op": "name", "range": "B1", "name": "Zeit"},
                                     {"op": "unit", "range": "B2", "unit": ""}])
        self.assertEqual([(c["name"], c["unit"]) for c in t2["columns"]], [("F", "kN"), ("Zeit", "")])
        ds = RC.to_dataset(t, "Einzelmessergebnisse", [], steps, "0.2.0")
        self.assertEqual((ds.col("F")["kind"], ds.col("t")["kind"]), ("force", "time"))
        with self.assertRaises(RC.RecipeError):
            RC.extract(sh, steps + [{"op": "unit", "range": "A2", "unit": "Furlong"}])

    def test_empty_gap_column_and_bare_s(self):
        m = M.Manual()
        w = [{"r": 0, "c": 0, "v": "F"}, {"r": 0, "c": 2, "v": "s"}]
        for i in range(4):
            w += [{"r": 1 + i, "c": 0, "v": str(10 * i)}, {"r": 1 + i, "c": 2, "v": str(i)}]
        m.write(0, w)
        t = RC.extract(m.sheet(0), RC.guess(m.sheet(0), loose=True))
        self.assertEqual([(c["name"], c["role"]) for c in t["columns"]], [("F", "x"), ("s", "y")])
        # a short column next to a long one is still a number column
        m.write(0, [{"r": 0, "c": 3, "v": "T"}, {"r": 1, "c": 3, "v": "20"}] + [{"r": 5 + i, "c": 0, "v": str(i)} for i in range(6)])
        t = RC.extract(m.sheet(0), RC.guess(m.sheet(0), loose=True))
        self.assertEqual([(c["name"], c["role"], c["dtype"]) for c in t["columns"]],
                         [("F", "x", "number"), ("s", "y", "number"), ("T", "y", "number")])


class ManualServerTest(ServerTest):
    test_load_cells_restart = test_page_and_assets = None          # run once, in test_readers

    def test_new_write_restart(self):
        st, j = self.post("/api/manual/new", {"name": "Zugprobe 1"})
        self.assertEqual(st, 200, j)
        f = j["files"][0]
        iid = f["id"]
        self.assertTrue(f["manual"])
        self.assertEqual((f["name"], f["sheets"][0]["rows"], f["sheets"][0]["cols"]), ("Zugprobe 1", M.MIN_ROWS, M.MIN_COLS))
        st, j = self.post("/api/manual/write", {"id": iid, "sheet": 0, "writes": [{"r": 0, "c": 0, "v": "F"}, {"r": 1, "c": 0, "v": "12,5"}]})
        self.assertEqual(st, 200, j)
        self.assertEqual(j["cells"], [{"r": 0, "c": 0, "t": SH.TEXT, "v": "F"}, {"r": 1, "c": 0, "t": SH.NUM, "v": "12,5"}])
        self.assertEqual(j["before"][1], {"r": 1, "c": 0, "v": ""})
        sha1 = j["sha256"]
        st, j = self.post("/api/manual/write", {"id": iid, "sheet": 0, "writes": [{"r": 2, "c": 0, "v": "13"}]})
        self.assertNotEqual(j["sha256"], sha1)
        st, w = self.post("/api/cells", {"id": iid, "sheet": 0, "r0": 0, "r1": 3, "c0": 0, "c1": 1})
        self.assertEqual(w["v"], [["F"], ["12,5"], ["13"]])
        st, j = self.post("/api/manual/sheet", {"id": iid, "op": "add"})
        self.assertEqual([s["name"] for s in j["sheets"]], ["Messung 1", "Messung 2"])
        st, j = self.post("/api/manual/sheet", {"id": iid, "op": "rename", "sheet": 1, "name": "Probe B"})
        self.assertEqual(j["sheets"][1]["name"], "Probe B")
        # a loaded file is not editable
        st, j = self.post("/api/paste", {"text": "a\tb\n1\t2\n", "name": "Datei"})
        st, e = self.post("/api/manual/write", {"id": j["files"][0]["id"], "sheet": 0, "writes": [{"r": 0, "c": 0, "v": "x"}]})
        self.assertEqual(st, 400)
        st, e = self.post("/api/manual/write", {"id": iid, "sheet": 0, "writes": [{"r": -3, "c": 0, "v": "x"}]})
        self.assertEqual(st, 400)
        # only the newest state of the manual sheet is kept as raw file
        envs = self.S.STATE.envs
        man = json.loads((envs.envs._dir(envs.eid) / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(sum(1 for r in man["raw"].values() if r["name"].endswith(".messung.json")), 1)
        # restart: content and sheets come back
        self.stop()
        self.start()
        st, j = self.post("/api/env/open", {})
        back = next(x for x in j["items"] if x["id"] == iid)
        self.assertTrue(back["manual"])
        self.assertEqual([s["name"] for s in back["sheets"]], ["Messung 1", "Probe B"])
        st, w = self.post("/api/cells", {"id": iid, "sheet": 0, "r0": 0, "r1": 3, "c0": 0, "c1": 1})
        self.assertEqual(w["v"], [["F"], ["12,5"], ["13"]])

    def test_sequential_entry_routes(self):
        st, j = self.post("/api/manual/parse", {"texts": ["12,5 N", "13", "0,014 kN", "15"], "unit": ""})
        self.assertEqual(st, 200, j)
        self.assertEqual(j["unit"], "N")                                  # first unit typed is taken for the column
        self.assertEqual([x["cell"] for x in j["items"]], ["12,5", "13", "0,014"])
        self.assertIn("kN", j["items"][2]["error"])                       # stops at a value in another unit
        st, j = self.post("/api/manual/parse", {"texts": ["1,5", "n.d."], "unit": "s"})
        self.assertEqual([(x["cell"], x["value"]) for x in j["items"]], [("1,5", 1.5), ("n.d.", None)])
        st, j = self.post("/api/manual/new", {"name": "Probe"})
        iid = j["files"][0]["id"]
        st, j = self.post("/api/manual/probe", {"id": iid, "sheet": 0, "dir": "down", "idx": 1})
        self.assertEqual((j["next"], j["header"]), (1, ""))
        self.post("/api/manual/write", {"id": iid, "sheet": 0, "writes": [{"r": 0, "c": 1, "v": "F"}, {"r": 1, "c": 1, "v": "1"},
                                                                          {"r": 2, "c": 1, "v": "2"}, {"r": 4, "c": 0, "v": "x"}]})
        st, j = self.post("/api/manual/probe", {"id": iid, "sheet": 0, "dir": "down", "idx": 1})
        self.assertEqual((j["next"], j["header"], j["header_num"]), (3, "F", False))
        st, j = self.post("/api/manual/probe", {"id": iid, "sheet": 0, "dir": "right", "idx": 4})
        self.assertEqual((j["next"], j["header"]), (1, "x"))

    def test_unit_info(self):
        st, j = self.post("/api/unit", {"unit": "MPa"})
        self.assertTrue(j["ok"])
        self.assertIn("pressure", [k["key"] for k in j["kinds"]])
        st, j = self.post("/api/unit", {"unit": "Furlong"})
        self.assertFalse(j["ok"])
        self.assertTrue(j["msg"])
        # U-01: pH is its own quantity kind and converts into nothing else; % does not offer pH
        st, j = self.post("/api/unit", {"unit": "pH"})
        self.assertTrue(j["ok"])
        self.assertEqual(j["kinds"][0]["key"], "ph")
        self.assertEqual(j["units"], ["pH"])
        st, j = self.post("/api/unit", {"unit": "%"})
        self.assertNotIn("pH", j["units"])
        self.assertNotIn("ph", [k["key"] for k in j["kinds"]])
        st, j = self.post("/api/unit", {"unit": "µS/cm"})
        self.assertEqual(j["kinds"][0]["key"], "el_conductivity")
        self.assertIn("mS/cm", j["units"])
        from daten import server as SV
        self.assertIn("ph", [k["key"] for k in SV.unit_kinds()])          # unit suggestions on every unit field

    def test_ds_thumb(self):
        """UI-18: a saved dataset brings a small x/y picture for the overview (excluded rows left out)."""
        import labdataset as DS
        from daten import server as SV
        n = 400
        ds = DS.from_columns("pH-Verlauf", [
            {"key": "t", "name": "Zeit", "unit": "h", "dtype": "number", "role": "x", "values": [i * 0.5 for i in range(n)]},
            {"key": "ph", "name": "pH", "unit": "pH", "dtype": "number", "role": "y", "values": [7 - i / n for i in range(n)]},
            {"key": "u", "name": "u(pH)", "unit": "pH", "dtype": "number", "role": "uncertainty", "values": [0.02] * n}],
            flags=[{"row": 3, "col": "ph", "code": "outlier", "excluded": True, "reason": "Test"}])
        th = SV.ds_thumb(ds)
        self.assertEqual((th["xlab"], th["ylab"]), ("Zeit [h]", "pH [pH]"))
        self.assertEqual([s["name"] for s in th["series"]], ["pH"])                 # no uncertainty column
        s = th["series"][0]
        self.assertLessEqual(len(s["x"]), 150)
        self.assertEqual(len(s["x"]), len(s["y"]))
        self.assertNotIn(1.5, s["x"])                                               # row 3 (t = 1.5 h) excluded


if __name__ == "__main__":
    unittest.main()
