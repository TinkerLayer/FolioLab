"""A8: vom Berichtswert zurück zur Rohdatei; benutzte Versionen und Umgebungen lassen sich nicht löschen."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import labindex as IX  # noqa: E402
import labprov as PV  # noqa: E402
import labproject as LP  # noqa: E402
import labshare as SH  # noqa: E402

OUTS = [{"key": "step1-loss", "label": "Stufe 1", "quantity": {"value": 12.3, "unit": "%"}}]
RAW = b"Temperatur;Masse\n25;10.0\n900;5.6\n"


class Provenance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.suite = LP.Suite(t / "projects" / "_suite")
        (self.suite.root).mkdir(parents=True)
        (self.suite.root / "suite.json").write_text(json.dumps(
            {"version": 1, "active": "p1", "projects": [{"id": "p1", "name": "P", "reports": ["r1"], "created": ""}]}))
        self.me = LP.ModuleEnvs(t / "out", "tga")
        self.me.suite = self.suite
        self.eid = self.me.create("Messreihe B")
        self.me.remember("i1", RAW, "lauf.txt")
        self.box = SH.Sharebox(self.suite, "p1")
        prod = {"module": "tga", "env": self.eid, "env_name": "Messreihe B", "item": "i1", "item_name": "Lauf",
                "raw": self.me.items["i1"]["raw"]}
        self.e1 = self.box.publish(prod, "tga.steps", "Lauf", OUTS, ["elementrechner"])
        self.g = IX.ProjectIndex(self.suite, "p1").add("Verlust 1", "Stufe 1", {"value": 12.3, "unit": "%"}, "measured",
                                                      {"module": "tga", "share": self.e1["id"], "version": 1})
        lab = t / "projects" / "r1" / "files" / "lab" / "vergleich"
        lab.mkdir(parents=True)
        req = {"state": {"shared": {"envelope": self.e1, "rows": []}},
               "values": [{"id": "v", "sym": "x", "origin": {"index": self.g["id"]}}]}
        (lab / "bundle.json").write_text(json.dumps({"slug": "vergleich", "revision": 2, "source": {"request": req}}))

    def tearDown(self):
        self.tmp.cleanup()

    def test_report_value_to_raw_file(self):
        r = PV.chain_for_report(self.suite, "p1", "r1", "vergleich")
        self.assertEqual(r["revision"], 2)
        refs = {c["ref"]: c["steps"] for c in r["chains"]}
        share_chain = refs[f"{self.e1['id']} v1"]
        self.assertEqual([s["level"] for s in share_chain], ["share", "env", "raw"])
        raw = share_chain[-1]
        self.assertTrue(raw["ok"] and raw["sha_matches_id"])
        self.assertEqual(raw["sha256"], hashlib.sha256(RAW).hexdigest())
        self.assertTrue(Path(raw["path"]).is_file())
        self.assertEqual([s["level"] for s in refs[self.g["id"]]], ["index", "share", "env", "raw"])
        # Eintrag später geschlossen: die Kette findet die Rohdatei über die Freigabe trotzdem
        self.me.forget("i1")
        self.assertTrue(PV.chain(self.suite, "p1", {"share": self.e1["id"], "version": 1})[-1]["ok"])

    def test_used_version_and_environment_cannot_be_deleted(self):
        with self.assertRaises(LP.EnvError) as cm:
            self.box.delete(self.e1["id"], 1)
        self.assertIn("r1/vergleich#2", str(cm.exception))
        with self.assertRaises(LP.EnvError):
            self.me.delete(self.eid)
        e2 = self.box.publish(self.e1["producer"], "tga.steps", "Lauf", OUTS, ["elementrechner"], share_id=self.e1["id"])
        self.box.delete(self.e1["id"], e2["version"])                 # unbenutzte Version: erlaubt
        self.assertEqual(self.box.list()[0]["latest"], 1)

    def test_dependencies_for_export(self):
        d = PV.dependencies(self.suite, "p1")
        self.assertEqual([(s["id"], s["version"]) for s in d["shares"]], [(self.e1["id"], 1)])
        self.assertEqual([i["id"] for i in d["index"]], [self.g["id"]])
        self.assertEqual(len(d["raw_files"]), 1)
        self.assertEqual(d["raw_files"][0]["sha256"], hashlib.sha256(RAW).hexdigest())


if __name__ == "__main__":
    unittest.main()
