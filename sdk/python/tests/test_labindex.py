"""A7: Projekt-Index – Alternativen bestehen nebeneinander, nichts wird überschrieben."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import labindex as IX  # noqa: E402
import labproject as LP  # noqa: E402
import labshare as SH  # noqa: E402

PROV = {"module": "tga", "env": "standard", "item": "r1"}


class Index(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.suite = LP.Suite(self.tmp.name)
        self.ix = IX.ProjectIndex(self.suite)

    def tearDown(self):
        self.tmp.cleanup()

    def test_alternatives_coexist(self):
        a = self.ix.add("Massenverlust CaCO3", "TGA Stufe 3", {"value": 43.6, "unit": "%"}, "measured", PROV,
                        {"rate": 10})
        b = self.ix.add("Massenverlust  CaCO3", "Theorie", {"value": 43.97, "unit": "%"}, "calculated",
                        {"module": "elementrechner"}, source={"type": "web", "title": "CIAAW"})
        self.assertNotEqual(a["id"], b["id"])
        self.assertEqual(b["alternative_to"], [a["id"]])
        g = self.ix.groups()
        self.assertEqual(len(g), 1)
        self.assertEqual([e["quantity"]["value"] for e in g[0]["entries"]], [43.6, 43.97])
        self.assertEqual(self.ix.get(a["id"])["quantity"]["value"], 43.6)       # unverändert

    def test_validation_and_no_share_leak(self):
        with self.assertRaises(LP.EnvError):
            self.ix.add("x", "", {"value": "a"}, "measured", PROV)
        with self.assertRaises(LP.EnvError):
            self.ix.add("x", "", {"value": 1}, "guessed", PROV)
        with self.assertRaises(LP.EnvError):
            self.ix.add("", "", {"value": 1}, "measured", PROV)
        with self.assertRaises(LP.EnvError):
            self.ix.get("../x")
        SH.Sharebox(self.suite).publish(PROV, "tga.steps", "x", [{"key": "a", "quantity": {"value": 1}}], ["rechner"])
        self.assertEqual(self.ix.list(), [])                                   # Teilen legt nichts im Index ab

    def test_route_from_any_environment(self):
        envs = LP.ModuleEnvs(self.tmp.name + "/out", "elementrechner")
        e = IX.route(envs, "elementrechner", "1.0", "add",
                     {"key": "M(H2O)", "quantity": {"value": 18.015, "unit": "g/mol"}, "type": "tabulated"})
        self.assertEqual(e["provenance"]["module"], "elementrechner")
        envs.create("zweite") if hasattr(envs, "create") else None
        other = LP.ModuleEnvs(self.tmp.name + "/out", "rechner")
        self.assertEqual(IX.route(other, "rechner", "1.0", "list", {})["groups"][0]["key"], "M(H2O)")


if __name__ == "__main__":
    unittest.main()
