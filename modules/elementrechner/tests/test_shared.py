"""A3: Theoretischer Massenverlust und Vergleich mit geteilten TGA-Stufen."""
from __future__ import annotations

import tempfile
import unittest

import labproject as LP
import labshare as LS
from elementrechner import shared as SH


class TheoryTest(unittest.TestCase):
    def test_oxalate_chain(self):
        # Calciumoxalat-Monohydrat: 12,33 / 19,17 / 30,12 % (ASTM E1582 / Lehrbuchwerte)
        b = "CaC2O4·H2O"
        self.assertAlmostEqual(SH.theoretical_loss("CaC2O4·H2O -> CaC2O4 + H2O(g)")["loss"], 12.33, delta=0.02)
        self.assertAlmostEqual(SH.theoretical_loss("CaC2O4 -> CaCO3 + CO(g)", b)["loss"], 19.17, delta=0.02)
        self.assertAlmostEqual(SH.theoretical_loss("CaCO3 -> CaO + CO2(g)", b)["loss"], 30.12, delta=0.02)
        self.assertAlmostEqual(SH.theoretical_loss("CaCO3 -> CaO + CO2(g)")["loss"], 43.97, delta=0.02)

    def test_unbalanced_input_is_balanced_and_gas_required(self):
        r = SH.theoretical_loss("Mg(OH)2 -> MgO + H2O(g)")
        self.assertAlmostEqual(r["loss"], 30.89, delta=0.05)
        self.assertAlmostEqual(SH.theoretical_loss("Al(OH)3 -> Al2O3 + H2O(g)")["loss"], 34.64, delta=0.05)
        with self.assertRaises(ValueError):
            SH.theoretical_loss("CaCO3 -> CaO + CO2")

    def test_compare_with_share(self):
        with tempfile.TemporaryDirectory() as d:
            box = LS.Sharebox(LP.Suite(d))
            prod = {"module": "tga", "env": "standard", "item": "r1"}
            outs = [{"key": "step1-loss", "label": "Stufe 1", "quantity": {"value": 12.5, "unit": "%"}},
                    {"key": "step2-loss", "label": "Stufe 2", "quantity": {"value": 19.0, "unit": "%"}}]
            e = box.publish(prod, SH.KIND, "Oxalat", outs, [SH.ME])
            rows = SH.compare(box.get(e["id"], recipient=SH.ME),
                              [{"key": "step1-loss", "equation": "CaC2O4·H2O -> CaC2O4 + H2O(g)"},
                               {"key": "step2-loss", "equation": "CaC2O4 -> CaCO3 + CO2(g)", "basis": "CaC2O4·H2O"},
                               {"key": "fehlt", "equation": "x"}])
            self.assertEqual(len(rows), 2)
            self.assertAlmostEqual(rows[0]["delta"], 12.5 - 12.33, delta=0.02)
            self.assertIn("error", rows[1])          # CaC2O4 -> CaCO3 + CO2 lässt sich nicht ausgleichen


class ReportTest(unittest.TestCase):
    def test_shared_comparison_in_report(self):
        """A5: Bericht nennt Freigabe und Version; der Umschlag liegt im Request (gepinnt)."""
        import base64

        from elementrechner import bundle as B
        env = {"schema": LS.SCHEMA, "id": "s-0a1b2c3d", "version": 2, "kind": SH.KIND, "title": "Oxalat",
               "producer": {"module": "tga", "env": "standard", "env_name": "Standard", "item": "r1", "item_name": "Oxalat"},
               "outputs": [{"key": "step3-loss", "label": "Stufe 3: Massenverlust", "quantity": {"value": 29.84, "unit": "%"}}]}
        rows = [{"key": "step3-loss", "equation": "CaCO3 -> CaO + CO2(g)", "basis": "CaC2O4·H2O"}]
        d = B.build({"state": {"shared": {"envelope": env, "rows": rows}}}, lang="de")
        tex = base64.b64decode(d["files"]["tga-vergleich.tex"]).decode("utf-8")
        cap = next(i for i in d["items"] if i.get("id") == "tga-vergleich")
        self.assertIn("s-0a1b2c3d v2", str(cap))
        str(cap.get("caption", "")).encode("latin-1")
        self.assertIn("30,12", tex)
        self.assertIn("$-$0,28", tex)
        tex.encode("latin-1")                                   # LaTeX-Regel: nur Latin-1
        self.assertEqual(d["source"]["request"]["state"]["shared"]["envelope"]["version"], 2)


class IrTest(unittest.TestCase):
    ENV = {"schema": LS.SCHEMA, "id": "s-00ff00ff", "version": 4, "kind": "ftir.peaks",
           "producer": {"module": "ftir", "env": "standard", "env_name": "Standard", "item": "a1", "item_name": "Folie"},
           "outputs": [{"key": f"peak{i}", "label": "", "quantity": {"value": x, "unit": "cm-1"}, "conditions": {"rel": 0.5}}
                       for i, x in enumerate([2960, 1715, 1505, 1410, 1240, 1100, 870, 725], 1)] +
                      [{"key": "class-ester", "label": "Ester", "quantity": {"value": 1.0, "unit": ""},
                        "conditions": {"verdict": "wahrscheinlich"}},
                       {"key": "class-nitrile", "label": "Nitril", "quantity": {"value": 1.0, "unit": ""},
                        "conditions": {"verdict": "wahrscheinlich"}}]}

    def test_structure_against_bands(self):
        r = SH.compare_ir(self.ENV, "COC(=O)c1ccc(cc1)C(=O)OC")          # Dimethylterephthalat
        by = {x["group"]: x for x in r["rows"]}
        self.assertEqual(by["ester"]["status"], "bestätigt")
        self.assertEqual(by["ester"]["ftir_verdict"], "wahrscheinlich")
        self.assertEqual(by["arene"]["status"], "teilweise")             # 1505 ja, =C–H über 3000 nein
        self.assertEqual([e["class"] for e in r["extra"]], ["nitrile"])  # im Spektrum, nicht in der Struktur
        self.assertEqual((r["share"], r["version"]), ("s-00ff00ff", 4))
        r2 = SH.compare_ir(self.ENV, "CCO")
        self.assertEqual(r2["rows"][0]["status"], "fehlt")              # keine O–H-Bande

    def test_report_names_version(self):
        import base64

        from elementrechner import bundle as B
        d = B.build({"state": {"ir_shared": {"envelope": self.ENV, "smiles": "COC(=O)c1ccc(cc1)C(=O)OC"}}}, lang="de")
        it = next(i for i in d["items"] if i.get("id") == "ftir-vergleich")
        self.assertIn("s-00ff00ff v4", str(it))
        tex = base64.b64decode(d["files"]["ftir-vergleich.tex"]).decode("utf-8")
        self.assertIn("bestätigt", tex)
        tex.encode("latin-1")
        self.assertIn("Socrates", base64.b64decode(d["files"]["refs.bib"]).decode("utf-8"))


class ValuesTest(unittest.TestCase):
    def test_send_to_rechner_is_versioned(self):
        """A5: jede Übergabe ist eine neue Version derselben Freigabe; nur für den Rechner lesbar."""
        with tempfile.TemporaryDirectory() as d:
            envs = LP.ModuleEnvs(d, "elementrechner")
            items = [{"sym": "M_CaCO3", "kind": "molar_mass", "value": "100.0869", "unit": "g/mol", "label": "Molare Masse"},
                     {"sym": "x", "value": "abc"}]
            e1 = SH.publish_values(envs, items, "1.0")
            self.assertEqual((e1["kind"], e1["version"], len(e1["outputs"])), ("chem.values", 1, 1))
            self.assertEqual(e1["outputs"][0]["quantity"], {"value": 100.0869, "unit": "g/mol"})
            e2 = SH.publish_values(envs, items[:1], "1.0")
            self.assertEqual((e2["id"], e2["version"]), (e1["id"], 2))
            box = LS.Sharebox(envs.suite, envs.project)
            self.assertEqual(box.get(e1["id"], 1, recipient="rechner")["version"], 1)
            with self.assertRaises(LP.EnvError):
                box.get(e1["id"], recipient="ftir")

    def test_board_shares(self):
        """UI-11: Übersicht trennt Freigaben an den Elementrechner (nur lesen) von eigenen Freigaben."""
        with tempfile.TemporaryDirectory() as d:
            envs = LP.ModuleEnvs(d, "elementrechner")
            own = SH.publish_values(envs, [{"sym": "M_X", "value": "1", "unit": "g/mol"}], "1.0")
            box = LS.Sharebox(envs.suite, envs.project)
            tga = box.publish({"module": "tga", "env": "standard", "env_name": "Standard", "item": "r1"}, SH.KIND, "Oxalat",
                              [{"key": "step1-loss", "label": "Stufe 1", "quantity": {"value": 12.3, "unit": "%"}}], [SH.ME])
            box.publish({"module": "tga", "env": "standard", "item": "r2"}, SH.KIND, "nur FTIR",
                        [{"key": "step1-loss", "label": "Stufe 1", "quantity": {"value": 5.0, "unit": "%"}}], ["ftir"])
            b = SH.board_shares(envs)
            self.assertEqual([s["id"] for s in b["incoming"]], [tga["id"]])
            self.assertEqual([s["id"] for s in b["own"]], [own["id"]])
            self.assertEqual(b["own"][0]["producer"]["env"], envs.eid)
            self.assertNotIn("outputs", b["incoming"][0])               # nur Kopfdaten, keine Messwerte

    def test_env_values_version_only_on_change(self):
        """UI-15: eine Freigabe je Quellumgebung; neue Version nur bei geänderten Werten; eigene Liste der Übersicht."""
        with tempfile.TemporaryDirectory() as d:
            envs = LP.ModuleEnvs(d, "elementrechner")
            envs.ensure()
            eid = envs.eid
            it = [{"sym": "n_O2", "value": "150", "unit": "mol", "label": "n(O₂) umgesetzt"}, {"sym": "x", "value": "abc"}]
            a = SH.publish_env_values(envs, eid, it, "1.0")
            self.assertEqual(a["version"], 1)
            self.assertEqual([o["key"] for o in a["outputs"]], ["n_O2"])          # nicht-numerisch fällt weg
            self.assertTrue(SH.publish_env_values(envs, eid, it, "1.0").get("unchanged"))
            c = SH.publish_env_values(envs, eid, [{**it[0], "value": "180"}], "1.0")
            self.assertEqual((c["id"], c["version"]), (a["id"], 2))
            b = SH.board_shares(envs)
            self.assertEqual([s["id"] for s in b["envvalues"]], [a["id"]])
            self.assertEqual(b["own"], [])
            self.assertEqual(SH.get_share(envs, a["id"], 1)["outputs"][0]["quantity"]["value"], 150.0)   # Momentaufnahme
            with self.assertRaises(ValueError):
                SH.publish_env_values(envs, "gibtsnicht", it)
            with self.assertRaises(ValueError):
                SH.publish_env_values(envs, eid, [{"sym": "x", "value": ""}])


if __name__ == "__main__":
    unittest.main()
