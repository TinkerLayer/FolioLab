"""A3: Umschlag und Sharebox."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import labproject as LP  # noqa: E402
import labshare as SH  # noqa: E402

PROD = {"module": "tga", "env": "standard", "env_name": "Standard", "item": "r1", "item_name": "Oxalat", "module_version": "1.0"}
OUTS = [{"key": "step1-loss", "label": "Stufe 1 Massenverlust", "quantity": {"value": 12.3, "unit": "%"},
         "conditions": {"T_peak": 180.5, "atm": "N2"}}]


class Share(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.box = SH.Sharebox(LP.Suite(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_publish_versions_and_list(self):
        e1 = self.box.publish(PROD, "tga.steps", "Oxalat", OUTS, ["elementrechner"])
        self.assertEqual((e1["schema"], e1["version"]), (SH.SCHEMA, 1))
        outs2 = [dict(OUTS[0], quantity={"value": 12.4, "unit": "%"})]
        e2 = self.box.publish(PROD, "tga.steps", "Oxalat", outs2, ["elementrechner"], share_id=e1["id"])
        self.assertEqual(e2["version"], 2)
        self.assertEqual(self.box.get(e1["id"], 1)["outputs"][0]["quantity"]["value"], 12.3)   # alte Version bleibt
        self.assertEqual(self.box.get(e1["id"])["version"], 2)
        self.assertEqual([m["id"] for m in self.box.list("elementrechner", "tga.steps")], [e1["id"]])
        self.assertEqual(self.box.list("rechner"), [])
        self.assertNotEqual(e1["hash"], e2["hash"])

    def test_only_selected_numbers_no_raw_data(self):
        with self.assertRaises(LP.EnvError):
            self.box.publish(PROD, "tga.steps", "x", [{"key": "curve", "quantity": {"value": [1, 2, 3]}}], ["elementrechner"])
        with self.assertRaises(LP.EnvError):
            self.box.publish(PROD, "tga.steps", "x", [], ["elementrechner"])
        with self.assertRaises(LP.EnvError):
            self.box.publish(PROD, "tga.steps", "x", OUTS, [])
        e = self.box.publish(PROD, "tga.steps", "x", [dict(OUTS[0], conditions={"T": 1, "raw": [1, 2]})], ["elementrechner"])
        self.assertEqual(e["outputs"][0]["conditions"], {"T": 1})

    def test_live_pin_copy_states(self):
        """A4: Korrektur beim Erzeuger → live wird „stale“ und rechnet mit der neuen Version; gepinnt bleibt."""
        e1 = self.box.publish(PROD, "tga.steps", "x", OUTS, ["elementrechner"])
        pin = {"id": e1["id"], "mode": "pin", "version": 1}
        live = {"id": e1["id"], "mode": "live", "used": 1}
        copy = {"id": e1["id"], "mode": "copy", "copy": e1}
        for b in (pin, live, copy):
            self.assertEqual(self.box.resolve(b)["status"], "current")
        fixed = [dict(OUTS[0], quantity={"value": 12.6, "unit": "%"})]
        self.box.publish(PROD, "tga.steps", "x", fixed, ["elementrechner"], share_id=e1["id"])
        r = self.box.resolve(pin)
        self.assertEqual((r["status"], r["envelope"]["version"]), ("update", 1))
        r = self.box.resolve(live)
        self.assertEqual((r["status"], r["envelope"]["version"], r["envelope"]["outputs"][0]["quantity"]["value"]),
                         ("stale", 2, 12.6))
        self.assertEqual(self.box.resolve(dict(live, used=2))["status"], "current")
        self.assertEqual(self.box.resolve(copy)["status"], "update")
        # ungültige Korrektur wird nicht veröffentlicht – live bleibt auf der letzten gültigen Version
        with self.assertRaises(LP.EnvError):
            self.box.publish(PROD, "tga.steps", "x", [dict(OUTS[0], quantity={"value": float("nan")})], ["elementrechner"],
                             share_id=e1["id"])
        self.assertEqual(self.box.resolve(dict(live, used=2))["envelope"]["version"], 2)
        self.assertEqual(self.box.resolve({"id": "s-00000000", "mode": "live"})["status"], "failed")
        self.assertEqual(self.box.resolve(dict(copy, id="s-00000000"))["status"], "current")

    def test_recipient_and_producer_checked(self):
        e = self.box.publish(PROD, "tga.steps", "x", OUTS, ["elementrechner"])
        with self.assertRaises(LP.EnvError):
            self.box.get(e["id"], recipient="ftir")             # Zahlen bleiben bei den genannten Empfängern
        self.assertEqual(self.box.list("ftir"), [])
        self.assertTrue(SH.readable({"kind": SH.DATA_KIND, "recipients": ["rechner"]}, "ftir"))   # I-01: Datensätze alle
        with self.assertRaises(LP.EnvError):
            self.box.publish(dict(PROD, module="ftir"), "tga.steps", "x", OUTS, ["elementrechner"], share_id=e["id"])
        with self.assertRaises(LP.EnvError):
            self.box.get("../x")


if __name__ == "__main__":
    unittest.main()
