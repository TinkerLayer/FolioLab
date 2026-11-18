"""Prüft die eingespielten Daten (sdk/python/labcalc/data) gegen Werte aus den Quellen.

CIAAW 2024 (gekürzt), AME2020, NUBASE2020, CIAAW-Isotopenzusammensetzung 2024.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "sdk" / "python"))

from labcalc import chem as C  # noqa: E402
from laboptional import skip_unless  # noqa: E402


class AtomicWeights(unittest.TestCase):
    def setUp(self):
        C._json.cache_clear()
        self.aw = C.atomic_weights()

    def test_all_elements(self):
        self.assertEqual(self.aw["_source"], "ciaaw2024")
        for s in C.SYMBOLS:
            e = self.aw[s]
            self.assertTrue(e.get("value") is not None or e.get("mass_number"), s)
        self.assertEqual(sum(1 for s in C.SYMBOLS if self.aw[s].get("value") is not None), 84)

    def test_values(self):
        self.assertEqual((self.aw["H"]["value"], self.aw["H"]["u"]), (1.0080, 0.0002))
        self.assertEqual(self.aw["H"]["interval"], [1.00784, 1.00811])
        self.assertEqual(self.aw["Fe"]["value"], 55.845)
        self.assertEqual(self.aw["Gd"]["standard"], 157.249)          # Änderung 2024
        self.assertEqual(self.aw["Zr"]["value"], 91.222)              # Änderung 2024
        self.assertEqual(self.aw["Tc"]["mass_number"], 97)
        self.assertEqual(self.aw["Pu"]["mass_number"], 244)

    def test_molar_masses(self):
        self.assertAlmostEqual(C.molar_mass("H2O")["M"], 18.015, places=3)
        self.assertAlmostEqual(C.molar_mass("NaCl")["M"], 58.44, places=2)
        self.assertAlmostEqual(C.molar_mass("C6H12O6")["M"], 180.156, places=3)
        self.assertAlmostEqual(C.molar_mass("CuSO4·5H2O")["M"], 249.68, places=2)
        self.assertEqual(C.molar_mass("TcO4^-")["notes"][0][:2], "Tc")   # ohne Standard-Atomgewicht: Hinweis


class Nuclides(unittest.TestCase):
    def setUp(self):
        C._json.cache_clear()
        self.n = C.isotope_masses()

    def test_masses(self):
        self.assertEqual(self.n["12C"]["mass_u"], 12.0)
        self.assertAlmostEqual(self.n["1H"]["mass_u"], 1.007825031898, places=12)
        self.assertAlmostEqual(self.n["235U"]["mass_u"], 235.043928117, places=9)
        self.assertAlmostEqual(C.molar_mass("^13CO2")["M"], 13.00335 + 2 * 15.999, places=4)

    def test_half_lives_and_decay(self):
        year = 365.2422 * 86400
        self.assertAlmostEqual(self.n["14C"]["half_life_s"] / year, 5700, delta=1)
        self.assertAlmostEqual(self.n["3H"]["half_life_s"] / year, 12.32, places=2)
        self.assertAlmostEqual(self.n["99mTc"]["half_life_s"] / 3600, 6.0066, places=4)
        self.assertEqual(self.n["1n"]["half_life_s"], 609.8)
        modes = {d["mode"]: d["pct"] for d in self.n["40K"]["decay"]}
        self.assertAlmostEqual(modes["B-"], 89.28)
        self.assertTrue(self.n["208Pb"].get("stable"))

    def test_abundances_are_on_the_right_element(self):
        self.assertAlmostEqual(self.n["235U"]["abundance_ciaaw"]["fraction"], 0.007204)
        self.assertAlmostEqual(self.n["60Ni"]["abundance_ciaaw"]["fraction"], 0.262231)
        self.assertIsNone(self.n["60Co"].get("abundance_ciaaw"))
        self.assertEqual(self.n["59Co"]["abundance_ciaaw"]["fraction"], 1.0)


class Collection(unittest.TestCase):
    """Sammlung (PubChem/Wikidata) und Nachschlagewerte (NIST SRD 46, IUPAC-pKa-Datensatz, PubChem PUG View)."""

    @classmethod
    def setUpClass(cls):
        from labcalc import substances as S
        C._json.cache_clear()
        for f in (S._index_build, S._srd_by_ligand, S._pka_by_cid):
            f.cache_clear()
        cls.S = S

    def test_size_and_records(self):
        mols = self.S.collection()["molecules"]
        self.assertGreater(len(mols), 1500)
        m = mols["QTBSBXVTEAMEQO-UHFFFAOYSA-N"]                     # Essigsäure
        self.assertEqual((m["formula"], m["cas"], m["cid"]), ("C2H4O2", "64-19-7", 176))
        cu = self.S.get(self.S.resolve("copper(II) sulfate pentahydrate"))
        self.assertEqual(cu["formula"], "CuSO4·5H2O")
        self.assertAlmostEqual(cu["M"], 249.68, places=1)
        self.assertEqual(self.S.get(self.S.resolve("calcium phosphate"))["formula"], "Ca3(PO4)2")
        for k, v in mols.items():                                    # jede Formel ist für Gleichungen lesbar
            if v.get("formula"):
                C.parse_species(v["formula"])
        # Isotope bleiben erhalten; Formeltreffer ohne Doppelte
        self.assertEqual(mols["XLYOFNOQVPJJNP-ZSJDYOACSA-N"]["formula"], "D2O")
        self.assertEqual(self.S.resolve("H2O"), "XLYOFNOQVPJJNP-UHFFFAOYSA-N")
        self.assertEqual(self.S.resolve("D2O"), "XLYOFNOQVPJJNP-ZSJDYOACSA-N")
        hits = self.S._index()[1][C.hill_formula("H2O")]
        self.assertEqual(hits, ["XLYOFNOQVPJJNP-UHFFFAOYSA-N"])

    def test_german_names(self):
        self.assertEqual(self.S.resolve("Essigsäure"), "QTBSBXVTEAMEQO-UHFFFAOYSA-N")
        self.assertEqual(self.S.resolve("Natriumchlorid"), self.S.resolve("sodium chloride"))
        self.S.install()                                             # Namens-Hook für parse_species (sonst vom Server)
        self.assertEqual(C.parse_species("Natriumchlorid").unicode(), "NaCl")
        self.assertEqual(self.S.find("Schwefelsäure")[0]["formula"], "H2SO4")

    @skip_unless('srd46')
    def test_pka_values(self):
        v = self.S.pka("acetic acid")
        self.assertAlmostEqual(v["value"], 4.76, delta=0.01)
        self.assertEqual(v["source"], "srd46")
        p = {i: self.S.pka("phosphoric acid", i)["value"] for i in (1, 2, 3)}
        self.assertAlmostEqual(p[1], 2.15, delta=0.1)
        self.assertAlmostEqual(p[2], 7.20, delta=0.1)
        self.assertAlmostEqual(p[3], 12.35, delta=0.2)
        self.assertAlmostEqual(self.S.pkb("ammonia")["value"], 4.75, delta=0.05)
        srcs = {x["source"] for x in self.S.pka_values("acetic acid")["values"]}
        # Der IUPAC-pKa-Datensatz (CC BY-NC) fehlt im öffentlichen Repository; tools/fetch_optional_data.py holt ihn.
        want = {"srd46", "iupac_pka"} if (ROOT.parents[1] / "sdk" / "python" / "labcalc" / "data" / "pka.json").exists() else {"srd46"}
        self.assertTrue(want <= srcs)

    @skip_unless('srd46')
    def test_ksp_and_complexes(self):
        self.assertAlmostEqual(self.S.ksp("AgCl")["value"], -9.75, delta=0.01)
        self.assertAlmostEqual(self.S.ksp("Fe(OH)3")["value"], -38.8, delta=0.1)
        b4 = self.S.logk("Cu2+", "NH3", 4)["value"]
        self.assertGreater(b4, 11.5)
        self.assertLess(b4, 13.5)

    def test_physical_properties(self):
        self.assertAlmostEqual(self.S.prop("water", "bp")["v"], 100.0, delta=0.5)
        self.assertAlmostEqual(self.S.prop("ethanol", "density")["v"], 0.789, delta=0.01)
        for vals in self.S.properties("ethanol")["props"].values():
            for v in vals:
                self.assertIn(v["src"], ("hsdb", "icsc", "osha", "niosh", "doepac"))   # nur offene Quellen


class Thermo(unittest.TestCase):
    """Bildungsdaten (CODATA Key Values, NBS-Tabellen, Burcat/ATcT) und Reaktionsgrössen bei 298,15 K.
    Sollwerte: CODATA Key Values 1989 und NBS-Tabellen 1982 (Hess-Summen von Hand nachgerechnet)."""

    @classmethod
    def setUpClass(cls):
        from labcalc import substances as S
        from labcalc import thermo as TH
        C._json.cache_clear()
        TH.data.cache_clear()
        TH._index.cache_clear()
        S._index_build.cache_clear()
        S.install()
        cls.TH, cls.S = TH, S

    def rx(self, text, T=None):
        eq = C.parse_equation(text)
        b = C.balance(eq)
        return self.TH.reaction(eq, b["coefs"], T or self.TH.T0)

    def test_species_choice(self):
        sd = lambda q: self.TH.species_data(C.parse_species(q))["entry"]     # noqa: E731
        self.assertEqual(sd("H2O")["ph"], "l")                              # stabile Phase: kleinstes ΔfG°
        self.assertEqual(sd("C")["ph"], "cr")
        self.assertEqual(sd("Br2")["ph"], "l")
        self.assertEqual(sd("Na+")["ph"], "aq")                             # Ion ohne Phase: aq
        self.assertEqual(sd("CH3COOH(aq)")["aqs"], "ao")                    # neutral gelöst: undissoziiert
        self.assertAlmostEqual(sd("H2O(l)")["H"], -285.83, places=2)        # CODATA vor NBS
        self.assertEqual(sd("H2O(l)")["src"], "codata")
        # Isomere: Name bzw. Schreibweise entscheidet, reine Summenformel nimmt den Stoff der Sammlung
        self.assertEqual(sd("Ethanol")["f"], "C2H5OH")
        self.assertEqual(sd("(CH3)2O")["f"], "(CH3)2O")
        # angeregte Zustände aus Burcat sind keine Alternative zum Grundzustand
        d = self.TH.species_data(C.parse_species("CO2"))
        self.assertFalse(d["notes"])
        self.assertFalse(any("triplet" in (a.get("poly") or "") for a in d["alternatives"]))

    def test_methane_combustion(self):
        r = self.rx("CH4 + O2 -> CO2 + H2O(l)")
        self.assertAlmostEqual(r["dH"], -890.36, delta=0.05)
        self.assertAlmostEqual(r["dG"], -817.9, delta=0.2)
        self.assertLess(abs(r["dG_diff"]), 0.05)                            # ΔH − TΔS und Σ ν ΔfG° stimmen überein

    @skip_unless('burcat')
    def test_propane_combustion(self):
        eq = C.parse_equation("C3H8 + O2 -> CO2 + H2O(l)")
        b = C.balance(eq)
        r = self.TH.reaction(eq, b["coefs"])
        self.assertAlmostEqual(r["dH"], -2219.2, delta=1.0)
        st = C.stoichiometry(eq, b["coefs"], {"0": {"mass_g": 44.097}})
        h = self.TH.heat(r, st, eq, b["coefs"])
        self.assertAlmostEqual(h["Q_kJ"], -2219.2, delta=1.5)
        self.assertTrue(h["combustion"])
        self.assertEqual(h["water_phase"], "l")
        self.assertAlmostEqual(-h["per_reactant"][0]["per_kg"] / 1000, 50.3, delta=0.1)   # Brennwert MJ/kg
        r = self.rx("C3H8 + O2 -> CO2 + H2O(g)")
        self.assertIsNone(r.get("T_star"))                                  # ΔH < 0, ΔS > 0: immer freiwillig
        self.assertIn("jeder Temperatur", r["case"])

    def test_haber_bosch(self):
        r = self.rx("N2 + H2 <=> NH3")
        self.assertAlmostEqual(r["dH"], -91.88, delta=0.1)
        self.assertAlmostEqual(r["dS"], -198.1, delta=0.3)
        self.assertAlmostEqual(r["T_star"], 463.8, delta=1.5)
        self.assertAlmostEqual(r["lgK"], 5.75, delta=0.03)
        self.assertEqual(r["dn_gas"], -2)
        r7 = self.rx("N2 + H2 <=> NH3", 700)
        self.assertTrue(r7["approx_T"])
        self.assertAlmostEqual(r7["dG_T"], -91.88 + 700 * 0.19811, delta=0.3)
        self.assertLess(r7["lgK_T"], 0)                                      # bei 700 K liegt das Gleichgewicht links

    def test_decomposition_and_ions(self):
        r = self.rx("CaCO3 -> CaO + CO2")
        self.assertAlmostEqual(r["T_star"], 1123, delta=5)
        self.assertIn("oberhalb", r["case"])
        r = self.rx("Ag+ + Cl- -> AgCl(s)")
        self.assertAlmostEqual(r["lgK"], 9.75, delta=0.05)                  # = −lg Ksp(AgCl)

    def test_ksp_from_formation_data(self):
        self.assertAlmostEqual(self.TH.ksp_from_dG("BaSO4", "[O-]S(=O)(=O)[O-].[Ba+2]")["value"], -10.06, delta=0.05)
        self.assertAlmostEqual(self.TH.ksp_from_dG("AgCl", "Cl[Ag]")["value"], -9.75, delta=0.05)   # kovalent geschrieben
        vals = self.S.ksp_values("BaSO4")["values"]
        calc = [v for v in vals if v.get("calc")]
        self.assertEqual(calc[0]["quality"], "berechnet")

    def test_digitisation_fixes(self):
        """NBS-Digitalisierung: verschobene Kommastelle (BaSO4 ai) wird über ΔG = ΔH − TΔS erkannt und korrigiert."""
        es = [e for e in self.TH.candidates(C.parse_species("BaSO4(aq)")) if e["src"] == "nbs" and e.get("aqs") == "ai"]
        self.assertTrue(es)
        self.assertAlmostEqual(es[0]["H"], -1446.91, delta=0.01)
        self.assertTrue(es[0].get("fix"))

    def test_calc_functions(self):
        from labcalc import expr as E
        f = E.STRFUNCS
        self.assertAlmostEqual(f["dHr"][0](None, "CH4 + O2 -> CO2 + H2O(l)") / 1000, -890.36, delta=0.05)
        self.assertAlmostEqual(f["dfH"][0](None, "H2O(l)"), -285830.0)
        self.assertAlmostEqual(f["lgKr"][0](None, "N2 + H2 -> NH3"), 5.75, delta=0.03)
        self.assertAlmostEqual(f["Cpm0"][0](None, "H2O(l)"), 75.29, delta=0.05)    # CODATA ohne Cp: NBS


if __name__ == "__main__":
    unittest.main()
