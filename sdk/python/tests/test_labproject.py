"""A2: Projekt- und Umgebungsablage."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import labproject as LP  # noqa: E402


class Store(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.suite = LP.Suite(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_defaults_created(self):
        envs = LP.Environments(self.suite, "ftir")
        lst = envs.list()
        self.assertEqual([e["id"] for e in lst], ["standard"])
        self.assertEqual(self.suite.active(), "standard")
        self.assertTrue((self.root / "suite.json").exists())
        self.assertTrue((self.root / "projects" / "standard" / "project.json").exists())

    def test_state_survives_new_instance(self):
        envs = LP.Environments(self.suite, "tga")
        e = envs.create("Probe A")
        rid = envs.add_raw(e["id"], "lauf 1.txt", b"1;2\n3;4\n")
        self.assertEqual(rid, envs.add_raw(e["id"], "lauf 1.txt", b"1;2\n3;4\n"))
        envs.save_state(e["id"], {"items": [{"raw": rid, "protocol": [{"op": "dtg"}]}]})
        again = LP.Environments(LP.Suite(self.root), "tga")                  # wie nach einem Neustart
        self.assertEqual([x["name"] for x in again.list()], ["Standard", "Probe A"])
        st = again.load_state(e["id"])
        self.assertEqual(again.raw(e["id"], st["items"][0]["raw"]), b"1;2\n3;4\n")
        self.assertEqual(again.manifest(e["id"])["raw"][rid]["bytes"], 8)

    def test_results_are_versioned_never_overwritten(self):
        envs = LP.Environments(self.suite, "tga")
        self.assertEqual(envs.add_result("standard", {"loss": 43.9}), 1)
        self.assertEqual(envs.add_result("standard", {"loss": 44.0}), 2)
        self.assertEqual([r["payload"]["loss"] for r in envs.results("standard")], [43.9, 44.0])

    def test_delete_moves_to_trash_and_default_is_kept(self):
        envs = LP.Environments(self.suite, "rechner")
        e = envs.create("weg")
        envs.delete(e["id"])
        self.assertEqual([x["id"] for x in envs.list()], ["standard"])
        self.assertEqual(len(list((envs.base / "_papierkorb").iterdir())), 1)
        with self.assertRaises(LP.EnvError):
            envs.delete("standard")

    def test_ids_and_paths_checked(self):
        envs = LP.Environments(self.suite, "ftir")
        envs.list()
        for bad in ("../x", "A", "", "x/y"):
            with self.assertRaises(LP.EnvError):
                envs.load_state(bad)
        with self.assertRaises(LP.EnvError):
            envs.raw("standard", "../../suite.json")
        with self.assertRaises(LP.EnvError):
            LP.Environments(self.suite, "../ftir")

    def test_active_project_from_hub_registry(self):
        (self.root).mkdir(exist_ok=True)
        (self.root / "suite.json").write_text(json.dumps({"version": 1, "active": "p2", "projects": [
            {"id": "standard", "name": "Standardprojekt", "reports": []},
            {"id": "p2", "name": "Polymere", "reports": ["b92bd25261c1"]}]}), "utf-8")
        envs = LP.Environments(LP.Suite(self.root), "ftir")
        envs.list()
        self.assertTrue((self.root / "projects" / "p2" / "env" / "ftir" / "standard" / "manifest.json").exists())

    def test_drop_raw_keeps_files_used_by_results(self):
        envs = LP.Environments(self.suite, "ftir")
        envs.list()
        a = envs.add_raw("standard", "a.jdx", b"A")
        b = envs.add_raw("standard", "b.jdx", b"B")
        envs.add_result("standard", {"x": 1}, raw=[a])
        envs.drop_raw("standard", keep=set())
        d = envs.base / "standard" / "raw"
        self.assertTrue((d / a).exists())
        self.assertFalse((d / b).exists())

    def test_module_envs_restart_and_switch(self):
        os.environ["FOLIO_SUITE_DIR"] = str(self.root)
        try:
            me = LP.ModuleEnvs("ignored", "ftir")
            me.remember("a1", b"RAW-A", "a.jdx", 0, "Probe A")
            me.set_client({"sel": 0, "sps": {"a1": {"pipeline": [{"op": "smooth"}]}}})
            me2 = LP.ModuleEnvs("ignored", "ftir")                         # Neustart
            got = me2.route("open", {}, lambda: [i for i, *_ in me2.stored()])
            self.assertEqual(got["items"], ["a1"])
            self.assertEqual(got["client"]["sps"]["a1"]["pipeline"][0]["op"], "smooth")
            self.assertEqual(me2.stored()[0][1], b"RAW-A")
            self.assertEqual(me2.route("open", {"check": 1}, list), {"changed": False})
            r = me2.route("create", {"name": "Zweite"}, lambda: me2.stored())
            self.assertEqual(r["items"], [])
            self.assertEqual(len(r["envs"]), 2)
            me3 = LP.ModuleEnvs("ignored", "ftir")                         # merkt sich die zuletzt aktive Umgebung
            me3.ensure()
            self.assertEqual(me3.eid, r["active"])
            me3.route("switch", {"id": "standard"}, list)
            self.assertEqual([x[0] for x in me3.stored()], ["a1"])
            me3.forget("a1")
            self.assertEqual(me3.stored(), [])
            with self.assertRaises(LP.EnvError):
                me3.set_client({"x": "y" * (LP.MAX_CLIENT + 1)})
        finally:
            os.environ.pop("FOLIO_SUITE_DIR", None)

    def test_summary_and_board(self):
        """UI-10: Zusammenfassung je Umgebung im Manifest; Lage und Verbindungen der Übersicht je Modul und Projekt."""
        os.environ["FOLIO_SUITE_DIR"] = str(self.root)
        try:
            me = LP.ModuleEnvs("ignored", "elementrechner")
            me.set_client({"equation": "H2 + O2 -> H2O", "summary": {"title": "2 H2 + O2 -> 2 H2O", "tools": ["thermo"]}})
            me.route("create", {"name": "Zweite"}, list)
            me.set_client({"summary": {"title": "NaCl"}})
            envs = me.route("info", {}, list)["envs"]
            self.assertEqual({e["name"]: e.get("summary", {}).get("title") for e in envs}, {"Standard": "2 H2 + O2 -> 2 H2O", "Zweite": "NaCl"})
            me.set_client({"summary": {"title": "x" * (LP.MAX_SUMMARY + 10)}})          # zu gross: alte bleibt
            self.assertEqual(me.route("info", {}, list)["envs"][1]["summary"]["title"], "NaCl")
            self.assertEqual(me.route("board", {}, list), {"pos": {}, "links": []})
            b = me.route("board", {"board": {"pos": {"env:standard": [10, 20.04], "bad": ["x", 1]},
                                              "links": [{"from": "s-1a2b3c4d", "to": "env:standard", "mode": "live", "kind": "tga.steps"},
                                                        {"from": "env:a", "to": "env:b", "mode": "copy", "version": 2, "kind": "env.values",
                                                         "share": "s-0f0f0f0f", "keys": ["n_O2", 5, "", "m_CO2"]},
                                                        {"from": "", "to": "x"}, "junk"]}}, list)
            self.assertEqual(b["pos"], {"env:standard": [10.0, 20.0]})
            self.assertEqual(b["links"], [{"from": "s-1a2b3c4d", "to": "env:standard", "mode": "live", "kind": "tga.steps"},
                                          {"from": "env:a", "to": "env:b", "mode": "copy", "version": 2, "kind": "env.values",
                                           "share": "s-0f0f0f0f", "keys": ["n_O2", "m_CO2"]}])
            me2 = LP.ModuleEnvs("ignored", "elementrechner")                 # Neustart: Übersicht bleibt
            self.assertEqual(me2.route("board", {}, list)["links"][0]["mode"], "live")
            self.assertNotIn("_board", [e["id"] for e in me2.route("info", {}, list)["envs"]])
        finally:
            os.environ.pop("FOLIO_SUITE_DIR", None)

    def test_board_shares_any_module(self):
        """UI-04…09: /api/env/shares – an das Modul gerichtete Freigaben (nur lesen) und eigene, nur Kopfdaten."""
        import labshare as LS
        os.environ["FOLIO_SUITE_DIR"] = str(self.root)
        try:
            me = LP.ModuleEnvs("ignored", "rechner")
            me.ensure()
            box = LS.Sharebox(me.suite, me.project)
            out = [{"key": "M", "label": "M", "quantity": {"value": 1.0, "unit": "g/mol"}}]
            a = box.publish({"module": "elementrechner", "env": "standard"}, "chem.values", "an Rechner", out, ["rechner"])
            other = box.publish({"module": "tga", "env": "standard"}, "tga.steps", "nur ER", out, ["elementrechner"])
            b = box.publish({"module": "rechner", "env": "standard"}, "calc.values", "eigen", out, ["elementrechner"])
            r = me.route("shares", {}, list)
            self.assertEqual([s["id"] for s in r["incoming"]], [a["id"]])
            self.assertEqual([s["id"] for s in r["own"]], [b["id"]])
            self.assertNotIn("outputs", r["incoming"][0])
            self.assertEqual(me.route("share", {"id": a["id"]}, list)["outputs"][0]["key"], "M")
            self.assertEqual(me.route("share", {"id": b["id"]}, list)["version"], 1)
            with self.assertRaises(LP.EnvError):                            # an ein anderes Modul gerichtet
                me.route("share", {"id": other["id"]}, list)
        finally:
            os.environ.pop("FOLIO_SUITE_DIR", None)

    def test_env_values_between_environments(self):
        """Verbindung Umgebung → Umgebung in jedem Modul: eine Freigabe je Quellumgebung, neue Version nur bei Änderung."""
        os.environ["FOLIO_SUITE_DIR"] = str(self.root)
        try:
            me = LP.ModuleEnvs("ignored", "rechner")
            me.ensure()
            me.route("create", {"name": "Zweite"}, list)
            items = [{"sym": "u", "label": "u = 50/3", "value": "16,666666666666668", "unit": ""},
                     {"sym": "F", "value": 1200, "unit": "N", "kind": "force"}, {"sym": "x", "value": "abc"}, {"value": 3}]
            a = me.route("envvalues", {"env": "standard", "items": items, "module_version": "9.9"}, list)
            self.assertEqual((a["kind"], a["version"]), ("lab.envvalues", 1))
            self.assertEqual([o["key"] for o in a["outputs"]], ["u", "F"])          # Text und namenlose Werte fallen weg
            self.assertAlmostEqual(a["outputs"][0]["quantity"]["value"], 50 / 3)
            b = me.route("envvalues", {"env": "standard", "items": items}, list)
            self.assertTrue(b.get("unchanged"))
            self.assertEqual((b["id"], b["version"]), (a["id"], 1))
            items[0]["value"] = "17"
            c = me.route("envvalues", {"env": "standard", "items": items}, list)
            self.assertEqual((c["id"], c["version"]), (a["id"], 2))
            r = me.route("shares", {}, list)                                       # nicht unter den eigenen Freigaben
            self.assertEqual([s["id"] for s in r["envvalues"]], [a["id"]])
            self.assertEqual(r["envvalues"][0]["recipients"], ["rechner"])
            self.assertEqual(r["own"], [])
            self.assertEqual(me.route("share", {"id": a["id"], "version": 1}, list)["outputs"][0]["quantity"]["value"], 50 / 3)
            with self.assertRaises(LP.EnvError):
                me.route("envvalues", {"env": "gibtsnicht", "items": items}, list)
            with self.assertRaises(LP.EnvError):
                me.route("envvalues", {"env": "standard", "items": [{"sym": "x", "value": "abc"}]}, list)
        finally:
            os.environ.pop("FOLIO_SUITE_DIR", None)

    def test_suite_root_env(self):
        old = os.environ.pop("FOLIO_SUITE_DIR", None)
        try:
            self.assertEqual(LP.suite_root("out"), Path("out") / "suite")
            os.environ["FOLIO_SUITE_DIR"] = str(self.root)
            self.assertEqual(LP.suite_root("out"), self.root)
        finally:
            os.environ.pop("FOLIO_SUITE_DIR", None)
            if old is not None:
                os.environ["FOLIO_SUITE_DIR"] = old


if __name__ == "__main__":
    unittest.main()
