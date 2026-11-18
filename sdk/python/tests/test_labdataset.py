"""DP-02: typed datasets (suite.dataset/1), data.table shares and provenance back to file and cells."""
from __future__ import annotations

import hashlib
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import labdataset as DS  # noqa: E402
import labprov as PV  # noqa: E402
import labproject as LP  # noqa: E402
import labshare as SH  # noqa: E402

RAW = b"Zeit;Konz\nmin;mmol/L\n0;10\n5;8,1\n10;6,6\n"


def kinetics(**kw):
    return DS.from_columns("Kinetik 25 °C", [
        {"key": "t", "name": "Zeit", "unit": "min", "role": "x", "values": [0, 5, 10, 15]},
        {"key": "c", "name": "Konzentration", "unit": "mmol/L", "role": "y", "u": "uc", "values": [10, 8.1, None, 5.4]},
        {"key": "uc", "name": "u(c)", "unit": "mmol/L", "role": "uncertainty", "values": [0.1, 0.1, 0.1, 0.1]},
        {"key": "probe", "name": "Probe", "dtype": "text", "role": "label", "values": ["A", "A", "B", None]},
    ], conditions={"T": {"value": 25, "unit": "°C"}},
        flags=[{"row": 3, "col": "c", "code": "outlier", "excluded": True, "reason": "Grubbs", "alpha": 0.05}], **kw)


class DatasetTest(unittest.TestCase):
    def test_kinds_si_and_mask(self):
        d = kinetics()
        self.assertEqual(d.rows, 4)
        self.assertEqual(d.col("t")["kind"], "time")
        self.assertEqual(d.col("c")["kind"], "concentration")
        self.assertTrue(np.allclose(d.si("t"), [0, 300, 600, 900]))
        self.assertTrue(np.allclose(d.in_unit("c", "mol/L")[:2], [0.01, 0.0081]))
        self.assertTrue(math.isnan(d.values("c")[2]))
        self.assertEqual(d.values("t", used_only=True).tolist(), [0, 5, 10])
        self.assertEqual(d.values("probe").tolist(), ["A", "A", "B", ""])
        p = d.page(1, 3, ["c"])
        self.assertEqual(p["values"]["c"], [8.1, None])
        json.dumps(p)                                   # JSON-safe

    def test_temperature_offset_and_difference(self):
        d = DS.from_columns("T", [{"key": "T", "name": "T", "unit": "°C", "values": [0, 100]},
                                  {"key": "dT", "name": "dT", "unit": "K", "kind": "temp_diff", "values": [1, 2]}])
        self.assertTrue(np.allclose(d.si("T"), [273.15, 373.15]))
        self.assertTrue(np.allclose(d.in_unit("T", "K"), [273.15, 373.15]))
        self.assertTrue(np.allclose(d.si("dT"), [1, 2]))
        self.assertEqual(DS.from_columns("x", [{"key": "n", "name": "n", "unit": "", "values": [1]}]).col("n")["kind"], "number")

    def test_round_trip(self):
        d = kinetics(provenance={"files": [{"name": "a.xlsx", "sha256": "0" * 64, "sheet": "Tabelle1", "ranges": ["A3:B6"]}]})
        with tempfile.TemporaryDirectory() as t:
            d.save(Path(t) / "ds")
            e = DS.Dataset.load(Path(t) / "ds")
            self.assertEqual(e.header, d.header)
            for c in d.columns:
                self.assertTrue(np.array_equal(e.data[c["key"]], d.data[c["key"]], equal_nan=c["dtype"] == "number"))
            # tampered values are noticed
            h = json.loads((Path(t) / "ds.json").read_text(encoding="utf-8"))
            np.savez(Path(t) / "ds.npz", **{**{k: e.data[k] for k in e.data}, "t": np.array([0, 5, 10, 16.0])})
            with self.assertRaises(DS.DatasetError):
                DS.Dataset.load(Path(t) / "ds")
            self.assertEqual(h["schema"], DS.SCHEMA)

    def test_refusals(self):
        bad = [
            ({"key": "1x", "name": "a", "unit": "s", "values": [1]}, "ungültig"),
            ({"key": "a", "name": "a", "unit": "furlong", "values": [1]}, "a"),
            ({"key": "a", "name": "a", "unit": "s", "kind": "mass", "values": [1]}, "passt nicht"),
            ({"key": "a", "name": "a", "unit": "s", "kind": "nonsense", "values": [1]}, "unbekannt"),
            ({"key": "a", "name": "a", "unit": "s", "role": "boss", "values": [1]}, "Rolle"),
            ({"key": "a", "name": "a", "unit": "s", "values": [1, math.inf]}, "unendlich"),
        ]
        for col, msg in bad:
            with self.assertRaises(DS.DatasetError, msg=col) as cm:
                DS.from_columns("x", [col])
            self.assertIn(msg, str(cm.exception))
        with self.assertRaisesRegex(DS.DatasetError, "Zeilen"):
            DS.from_columns("x", [{"key": "a", "name": "a", "unit": "s", "values": [1, 2]},
                                  {"key": "b", "name": "b", "unit": "s", "values": [1]}])
        with self.assertRaisesRegex(DS.DatasetError, "Unsicherheit"):
            DS.from_columns("x", [{"key": "a", "name": "a", "unit": "s", "u": "zz", "values": [1]}])
        with self.assertRaisesRegex(DS.DatasetError, "Zeile"):
            DS.from_columns("x", [{"key": "a", "name": "a", "unit": "s", "values": [1]}], flags=[{"row": 5, "code": "note"}])
        with self.assertRaisesRegex(DS.DatasetError, "gross"):
            DS.from_columns("x", [{"key": f"c{i}", "name": "c", "unit": "s", "values": np.zeros(DS.MAX_CELLS // 10 + 1)}
                                  for i in range(10)])

    def test_safe_key(self):
        self.assertEqual(DS.safe_key("Temperatur (°C)"), "Temperatur_oC")
        self.assertEqual(DS.safe_key("1. Messung"), "c_1_Messung")
        self.assertEqual(DS.safe_key("x", {"x", "x_2"}), "x_3")


class ShareTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.suite = LP.Suite(t / "projects" / "_suite")
        self.suite.root.mkdir(parents=True)
        (self.suite.root / "suite.json").write_text(json.dumps(
            {"version": 1, "active": "p1", "projects": [{"id": "p1", "name": "P", "reports": [], "created": ""}]}))
        self.me = LP.ModuleEnvs(t / "out", "datenaufbereitung")
        self.me.suite = self.suite
        self.eid = self.me.create("Kinetik")
        self.me.remember("i1", RAW, "kinetik.csv")
        self.raw = self.me.items["i1"]["raw"]
        self.box = SH.Sharebox(self.suite, "p1")
        self.prod = {"module": "datenaufbereitung", "env": self.eid, "env_name": "Kinetik", "item": "i1",
                     "item_name": "kinetik.csv"}
        self.ds = kinetics(provenance={"files": [{"name": "kinetik.csv", "raw": self.raw,
                                                  "sha256": hashlib.sha256(RAW).hexdigest(), "ranges": ["A3:B5"]}]})

    def tearDown(self):
        self.tmp.cleanup()

    def test_publish_pin_live_copy_delete(self):
        e1 = self.box.publish_dataset(self.prod, "Kinetik", self.ds, ["elementrechner", "rechner"])
        self.assertEqual(e1["kind"], "data.table")
        self.assertEqual([o["quantity"]["value"] for o in e1["outputs"]], [4.0, 4.0])
        d = self.box.base / e1["id"]
        self.assertTrue((d / "v1.npz").is_file() and not (d / "v1.json.json").exists())
        got = self.box.dataset(e1["id"], 1, "elementrechner")
        self.assertEqual(got.header["data_hash"], self.ds.header["data_hash"])
        # I-01: every module may read a dataset; the recipients only mark who it is meant for
        self.assertEqual(self.box.dataset(e1["id"], 1, "ftir").rows, 4)
        self.assertEqual([m["id"] for m in self.box.list("ftir", "data.table")], [e1["id"]])
        self.assertEqual((SH.for_me(self.box.list()[0], "rechner"), SH.for_me(self.box.list()[0], "ftir")), (True, False))
        # scalar publish may not pretend to be a dataset, nor switch kind
        with self.assertRaises(LP.EnvError):
            self.box.publish(self.prod, "data.table", "x", [{"key": "a", "quantity": {"value": 1}}], ["rechner"])
        with self.assertRaises(LP.EnvError):
            self.box.publish(self.prod, "x", "x", [{"key": "a", "quantity": {"value": 1}}], ["rechner"], share_id=e1["id"])
        # v2: pin stays on v1 with an update notice, live follows
        ds2 = DS.from_columns("Kinetik 2", [{"key": "t", "name": "Zeit", "unit": "min", "values": [0, 1]}])
        self.box.publish_dataset(self.prod, "Kinetik", ds2, ["rechner"], share_id=e1["id"])
        r = self.box.resolve({"id": e1["id"], "mode": "pin", "version": 1}, "rechner")
        self.assertEqual((r["status"], r["used"]), ("update", 1))
        self.assertEqual(self.box.dataset(e1["id"], r["used"], "rechner").rows, 4)
        r = self.box.resolve({"id": e1["id"], "mode": "live", "used": 1}, "rechner")
        self.assertEqual((r["status"], r["envelope"]["version"]), ("stale", 2))
        # copy: values live with the recipient and survive deleting the share
        dest = Path(self.tmp.name) / "rechner" / "kopie"
        env = self.box.copy_dataset(e1["id"], 1, "rechner", dest)
        self.box.delete(e1["id"], 1)
        self.assertFalse((d / "v1.npz").exists())
        self.assertEqual(DS.Dataset.load(dest).rows, 4)
        self.assertEqual(self.box.resolve({"id": e1["id"], "mode": "copy", "copy": env}, "rechner")["status"], "update")
        # tampered sidecar is refused
        np.savez(d / "v2.npz", t=np.array([0, 2.0]))
        with self.assertRaisesRegex(LP.EnvError, "Prüfsumme"):
            self.box.dataset(e1["id"], 2)

    def test_import_window_routes(self):
        """I-02: every module lists every dataset (its own first) and previews one with versions, ranges, picture."""
        e1 = self.box.publish_dataset(self.prod, "Kinetik", self.ds, ["rechner"])
        e2 = self.box.publish_dataset(self.prod, "Für TGA", self.ds, ["tga"])
        self.box.publish_dataset(self.prod, "Kinetik", kinetics(), ["rechner"], share_id=e1["id"])
        tga = LP.ModuleEnvs(Path(self.tmp.name) / "tga", "tga")
        tga.suite = self.suite
        L = tga.route("datasets", {}, list)["datasets"]
        self.assertEqual([(d["id"], d["for_me"]) for d in L], [(e2["id"], True), (e1["id"], False)])
        self.assertEqual([c["key"] for c in L[1]["columns"]], ["t", "c", "uc", "probe"])
        p = tga.route("dataset", {"id": e1["id"]}, list)
        self.assertEqual((p["version"], p["latest"], [v["version"] for v in p["versions"]]), (2, 2, [2, 1]))
        self.assertEqual((p["excluded"], p["ext"]["t"], p["ext"]["probe"] if "probe" in p["ext"] else None), (1, [0.0, 10.0, 3], None))
        self.assertEqual(p["first"]["values"]["c"][:3], [10.0, 8.1, None])
        self.assertEqual(p["thumb"]["xlab"], "Zeit [min]")
        self.assertEqual(tga.route("dataset", {"id": e1["id"], "version": 1}, list)["version"], 1)
        json.dumps(p, allow_nan=False)                               # strict JSON for the page

    def test_chain_to_file_and_cells(self):
        e1 = self.box.publish_dataset(self.prod, "Kinetik", self.ds, ["rechner"])
        steps = PV.chain(self.suite, "p1", {"share": e1["id"], "version": 1})
        self.assertEqual([s["level"] for s in steps], ["share", "dataset", "env", "raw"])
        self.assertIn("4 Zeilen", steps[1]["title"])
        self.assertIn("A3:B5", steps[-1]["detail"])
        self.assertTrue(steps[-1]["ok"] and steps[-1]["sha_matches"])
