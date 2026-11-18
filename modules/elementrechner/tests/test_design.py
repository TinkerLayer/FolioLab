"""Tests des Moleküldesigners (Phase 4): SMILES-Graph, Regelnamen (IUPAC 2013), Joback-Schätzung, Analyse und
Schätzwerte in Thermochemie und Stoffwerten.

Sollwerte:
- Namen nach Favre & Powell 2014 (IUPAC-Empfehlungen 2013), von Hand geprüft.
- Joback: Rechenbeispiel Aceton aus der Joback-Tabelle (Wikipedia, CC BY-SA 4.0), die die Gruppenwerte von
  Joback & Reid 1987 wiedergibt: Tb 322,11 K, Tc 500,56 K, Pc 48,03 bar, ΔfH° −217,83 kJ/mol, ΔfG° −154,54 kJ/mol.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "sdk" / "python"))

from labcalc import chem as C  # noqa: E402
from labcalc import joback as J  # noqa: E402
from labcalc import molgraph as G  # noqa: E402
from labcalc import naming as N  # noqa: E402


class Graph(unittest.TestCase):
    def test_parse_and_counts(self):
        cnt = lambda s: G.parse(s).element_counts()   # noqa: E731
        self.assertEqual(G.hill(cnt("CC(=O)O")), "C2H4O2")
        self.assertEqual(G.hill(cnt("c1ccccc1O")), "C6H6O")
        self.assertEqual(G.dbe(cnt("c1ccccc1O")), 4)
        self.assertEqual(G.hill(cnt("[NH4+].[Cl-]")), "ClH4N")
        self.assertEqual(G.parse("[NH4+].[Cl-]").charge(), 0)

    def test_rings(self):
        m = G.parse("C1CCC2CCCCC2C1")                 # Decalin: ein Ringsystem, zwei Ringe
        self.assertEqual(len(m.ring_systems), 1)
        self.assertEqual(m.ring_systems[0]["cyclo"], 2)
        self.assertTrue(all(G.parse("c1ccccc1").benzene_atom))
        self.assertTrue(any(r["benzene"] for r in G.parse("C1=CC=CC=C1").rings))   # Kekulé zählt als Benzolring

    def test_functional_groups(self):
        keys = lambda s: {g["key"] for g in G.functional_groups(G.parse(s))}   # noqa: E731
        self.assertEqual(keys("CC(=O)O"), {"acid"})
        self.assertIn("ester", keys("CC(=O)OCC"))
        self.assertIn("amide", keys("CC(N)=O"))
        self.assertIn("phenol", keys("Oc1ccccc1"))
        self.assertIn("ketone", keys("CC(C)=O"))
        self.assertIn("aldehyde", keys("CC=O"))
        self.assertIn("nitrile", keys("CC#N"))
        self.assertIn("amine1", keys("CCN"))
        self.assertNotIn("alcohol", keys("CC(=O)O"))   # OH der Säure ist kein Alkohol


class Naming(unittest.TestCase):
    CASES = {
        "CCO": "ethanol",
        "CC(C)O": "propan-2-ol",
        "CC(C)=O": "propan-2-one",
        "CC(=O)O": "acetic acid",
        "OC(=O)c1ccccc1": "benzoic acid",
        "CC(=O)OCC": "ethyl acetate",
        "CC(Cl)CCC(=O)OC": "methyl 4-chloropentanoate",
        "CCC(C)CC": "3-methylpentane",
        "CC(C)(C)C": "2,2-dimethylpropane",
        "C=CC=C": "buta-1,3-diene",
        "CC#CC": "but-2-yne",
        "OCCO": "ethane-1,2-diol",
        "NCCO": "2-aminoethan-1-ol",
        "Clc1ccc(Cl)cc1": "1,4-dichlorobenzene",
        "CC(C)(C)c1cc(C(C)(C)C)c(O)c(C(C)(C)C)c1": "2,4,6-tri-tert-butylphenol",
        "CCCCCOc1ccccc1": "(pentyloxy)benzene",
        "O=C(c1ccccc1)c1ccc(Br)cc1": "(4-bromophenyl)(phenyl)methanone",
        "ClCC(=O)O": "chloroacetic acid",
        "C1CCCCC1": "cyclohexane",
        "OC1CCCCC1": "cyclohexanol",
        "CCOCC": "ethoxyethane",
        "N#Cc1ccccc1": "benzonitrile",
    }

    def test_english(self):
        for smi, want in self.CASES.items():
            with self.subTest(smi=smi):
                self.assertEqual(N.name(smi).get("en"), want)

    def test_german(self):
        self.assertEqual(N.name("ClCC(=O)O")["de"], "Chloressigsäure")
        self.assertEqual(N.name("COC(=O)c1ccc(Cl)cc1")["de"], "Methyl-4-chlorbenzoat")
        self.assertEqual(N.name("CCO")["de"], "Ethanol")
        self.assertEqual(N.name("CC(C)O")["de"], "Propan-2-ol")

    def test_refusals(self):
        """Ausserhalb der umgesetzten Regeln wird kein Name geraten (kondensierte Heterocyclen und Ringe, Salze …).

        Pyridin wird seit ER-403 benannt (tests/test_naming_er403.py); hier steht dafür Chinolin."""
        for smi in ("c1ccc2ncccc2c1", "c1ccc2ccccc2c1", "[Na+].[Cl-]"):
            with self.subTest(smi=smi):
                r = N.name(smi)
                self.assertNotIn("en", r)
                self.assertTrue(r.get("refused"))

    def test_source(self):
        self.assertEqual(N.name("CCO")["refs"], ["favre2014"])


class Joback(unittest.TestCase):
    def test_acetone(self):
        m = G.parse("CC(C)=O")
        r = J.estimate(m, C.molar_mass("C3H6O")["M"])
        v = {k: x["v"] for k, x in r["values"].items()}
        self.assertAlmostEqual(v["Tb"], 322.11, delta=0.01)
        self.assertAlmostEqual(v["Tc"], 500.56, delta=0.01)
        self.assertAlmostEqual(v["Pc"], 48.03, delta=0.01)
        self.assertAlmostEqual(v["dfH_g"], -217.83, delta=0.01)
        self.assertAlmostEqual(v["dfG_g"], -154.54, delta=0.01)
        self.assertEqual(r["refs"], ["joback1987", "joback_wiki"])
        self.assertTrue(all(x.get("label") for x in r["values"].values()))

    def test_groups_and_limits(self):
        groups, _ = J.assign(G.parse("CCO"))
        self.assertEqual(dict(groups), {"-CH3": 1, "-CH2-": 1, "-OH (Alkohol)": 1})
        for smi in ("C", "[Na+].[Cl-]", "C[Si](C)(C)C"):           # Methan, Ionen, Si: nicht im Verfahren
            with self.subTest(smi=smi), self.assertRaises(J.JobackError):
                J.assign(G.parse(smi))


class Analyze(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from labcalc import substances as S
        from elementrechner import design as D
        S.install()
        cls.S, cls.D = S, D

    def test_known_and_new(self):
        r = self.D.analyze("CCO")
        self.assertEqual(r["hill"], "C2H6O")
        self.assertAlmostEqual(r["M"], 46.069, places=2)
        self.assertAlmostEqual(r["mono"], 46.04186, places=4)
        self.assertEqual(r["dbe"], 0)
        self.assertTrue(any(c["smiles"] for c in r["candidates"]))    # Isomere mit Struktur für die Wiedererkennung
        self.assertTrue(r["pka_hints"])                                # Ethanol als verwandte Verbindung
        r = self.D.analyze("CC(Cl)CCC(=O)OC")
        self.assertEqual(r["name"]["en"], "methyl 4-chloropentanoate")
        self.assertIn("S_g", r["joback"]["values"])                    # S° aus ΔfH°, ΔfG° und S°(Elemente)
        keys = {x["key"] if isinstance(x, dict) and "key" in x else x for x in r["refs"]}
        self.assertTrue({"favre2014", "joback1987"} <= set(keys) or any("Joback" in str(x) for x in r["refs"]))

    def test_salt_without_joback(self):
        r = self.D.analyze("[Na+].[Cl-]")
        self.assertEqual(r["hill"], "ClNa")
        self.assertTrue(r["joback"].get("error"))

    def test_bad_input(self):
        with self.assertRaises(Exception):
            self.D.analyze("C1CC(")


class Estimates(unittest.TestCase):
    """Gespeicherte Schätzwerte: niedrigste Priorität, gekennzeichnet, S° abgeleitet."""

    @classmethod
    def setUpClass(cls):
        from labcalc import substances as S
        from labcalc import thermo as TH
        S.install()
        cls.S, cls.TH = S, TH
        src = {"type": "article", "authors": "Joback, K. G.; Reid, R. C.", "year": "1987"}
        est = lambda v, u, ph=None: {"v": v, "u": u, "phase": ph, "est": True, "method": "Joback & Reid 1987",   # noqa: E731
                                     "source": src}
        cls.rec = {"own:t1": {"own": True, "id": "t1", "name": "Methyl-4-chlorpentanoat", "en": "methyl 4-chloropentanoate",
                              "formula": "C6H11ClO2", "smiles": "CC(Cl)CCC(=O)OC", "kind": "molecule", "classes": [],
                              "values": {"dfH": [est(-505.47, "kJ/mol", "g")], "dfG": [est(-325.10, "kJ/mol", "g")],
                                         "bp": [est(158.94, "°C")]}}}
        S.set_user_store(lambda: cls.rec)

    @classmethod
    def tearDownClass(cls):
        cls.S.set_user_store(None)

    def test_thermo_uses_estimate_with_warning(self):
        eq = C.parse_equation("C6H11ClO2(g) + O2(g) -> CO2(g) + H2O(g) + HCl(g)")
        b = C.balance(eq)
        r = self.TH.reaction(eq, b["coefs"])
        self.assertTrue(r.get("estimated"))
        self.assertTrue(any("Schätzwerte" in n for n in r.get("notes", [])))
        e = self.TH.species_data(C.parse_species("C6H11ClO2(g)"))["entry"]
        self.assertEqual(e["src"], "est")
        counts = {"C": 6, "H": 11, "Cl": 1, "O": 2}
        self.assertAlmostEqual(e["S"], self.TH.S_from(counts, 0, -505.47, -325.10), places=6)

    def test_report_marks_estimates(self):
        import base64
        from elementrechner import bundle as B
        d = B.build({"state": {"equation": "C6H11ClO2(g) + O2(g) -> CO2(g) + H2O(g) + HCl(g)"}})
        t = base64.b64decode(d["files"]["text-thermochemie.tex"]).decode("utf-8")
        self.assertIn("Schätzwerte", t)
        keys = {i["key"] for i in d["items"] if i["kind"] == "citation"}
        self.assertIn("er-joback1987", keys)

    def test_estimate_priority(self):
        self.assertGreater(self.TH.PRIO["est"], self.TH.PRIO["own"])
        p = self.S.prop("own:t1", "bp")
        self.assertAlmostEqual(p["v"], 158.94)
        self.assertEqual(p.get("quality"), "Schätzwert")


if __name__ == "__main__":
    unittest.main()
