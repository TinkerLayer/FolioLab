"""Lösungen ansetzen (ER-L01 bis ER-L03)."""
import unittest

from labcalc import prep as P
from laboptional import skip_unless  # noqa: E402

HCL37 = {"value": 37, "unit": "%(w/w)",
         "density": {"value": 1.184, "unit": "g/mL", "T_C": 20, "source": "Datenblatt Salzsäure 37 %"}}


class Core(unittest.TestCase):
    def test_form_and_per_unit(self):
        f = P.form("CuSO4·5H2O")
        self.assertAlmostEqual(f["M"], 249.68, delta=0.01)
        self.assertEqual(f["water"], 5)
        self.assertEqual(P.form("CuSO4*5H2O")["formula"], f["formula"])
        self.assertEqual(P.per_unit(f, P.form("Cu^2+")), 1)
        self.assertEqual(P.per_unit(P.form("CaCl2·2H2O"), P.form("Cl^-")), 2)
        self.assertEqual(P.per_unit(P.form("(NH4)2SO4"), P.form("NH4^+")), 2)
        with self.assertRaises(P.PrepError):
            P.per_unit(P.form("NaCl"), P.form("K^+"))

    def test_bases(self):
        for unit, kind in (("mol/L", "molar"), ("mmol/L", "molar"), ("g/L", "mass"), ("mg/L", "mass"),
                           ("%(w/v)", "wv"), ("%(w/w)", "w"), ("mol/kg", "b")):
            self.assertEqual(P.target(1, unit)["kind"], kind)
        self.assertAlmostEqual(P.target(5, "mmol/L")["x"], 0.005)
        for bad in ((0, "mol/L"), (1, "furlong"), (100, "%(w/w)"), ("x", "mol/L")):
            with self.assertRaises(P.PrepError):
                P.target(*bad)

    def test_density_needs_source_and_temperature(self):
        self.assertAlmostEqual(P.density({"value": 1184, "unit": "kg/m3", "T_C": 20, "source": "x"})["g_mL"], 1.184)
        for bad in ({"value": 1.1, "T_C": 20}, {"value": 1.1, "source": "x"}, {"value": -1, "T_C": 20, "source": "x"},
                    1.18):
            with self.assertRaises(P.PrepError):
                P.density(bad)

    def test_volume(self):
        self.assertAlmostEqual(P.volume_L(250), 0.25)
        self.assertAlmostEqual(P.volume_L(1, "L"), 1)
        for bad in ((0,), (-5,), (1, "gal")):
            with self.assertRaises(P.PrepError):
                P.volume_L(*bad)


class Solid(unittest.TestCase):
    def test_copper_sulfate(self):
        # 250 mL 0,100 mol/L CuSO4: Pentahydrat 6,242 g, wasserfrei 3,990 g
        r = P.from_solid("CuSO4·5H2O", 0.1, "mol/L", 250, basis="CuSO4")
        self.assertAlmostEqual(r["mass_g"], 6.242, delta=0.0005)
        self.assertTrue(any("Hydrat" in n for n in r["notes"]))
        self.assertAlmostEqual(P.from_solid("CuSO4", 0.1, "mol/L", 250)["mass_g"], 3.990, delta=0.0005)
        self.assertAlmostEqual(P.from_solid("CuSO4·5H2O", 0.1, "mol/L", 250, basis="Cu^2+")["mass_g"], 6.242,
                               delta=0.0005)
        self.assertTrue(r["steps"])
        self.assertTrue(all("text" in s for s in r["steps"]))

    def test_purity_and_rounding(self):
        a = P.from_solid("NaCl", 0.1, "mol/L", 1000)["mass_g"]
        self.assertAlmostEqual(a, 5.844, delta=0.001)
        self.assertAlmostEqual(P.from_solid("NaCl", 0.1, "mol/L", 1000, purity=98)["mass_g"], a / 0.98, places=9)
        self.assertAlmostEqual(P.from_solid("NaCl", 0.1, "mol/L", 1000, purity=0.98)["mass_g"], a / 0.98, places=9)
        r = P.from_solid("NaCl", 0.1, "mol/L", 240, flask=True, balance_d=0.01)
        self.assertEqual(r["V_L"], 0.25)
        self.assertAlmostEqual(r["mass_rounded_g"], 1.46, places=9)
        self.assertAlmostEqual(r["actual_value"], 0.1 * 1.46 / r["mass_g"], places=9)

    def test_other_bases(self):
        self.assertAlmostEqual(P.from_solid("NaCl", 9, "g/L", 500)["mass_g"], 4.5, places=9)
        self.assertAlmostEqual(P.from_solid("NaCl", 0.9, "%(w/v)", 500)["mass_g"], 4.5, places=9)
        rho = {"value": 1.005, "unit": "g/mL", "T_C": 20, "source": "eigene Messung"}
        self.assertAlmostEqual(P.from_solid("NaCl", 1, "%(w/w)", 100, rho_solution=rho)["mass_g"], 1.005, places=9)
        # Molalität: m(LM) = m(Lsg)/(1 + b·M)
        r = P.from_solid("NaCl", 0.1, "mol/kg", 1000, rho_solution=rho)
        m_solv = 1005 / (1 + 0.1 * 58.443 / 1000)
        self.assertAlmostEqual(r["n_basis"], 0.1 * m_solv / 1000, places=6)

    def test_refusals(self):
        for call in (lambda: P.from_solid("NaCl", 1, "%(w/w)", 100),                  # Dichte fehlt
                     lambda: P.from_solid("NaCl", 0.1, "mol/kg", 100),                 # Dichte fehlt
                     lambda: P.from_solid("NaCl", 0.1, "mol/L", -5),
                     lambda: P.from_solid("NaCl", 0.1, "mol/L", 0),
                     lambda: P.from_solid("Unobtainium", 0.1, "mol/L", 100),
                     lambda: P.from_solid("NaCl", 0.1, "mol/L", 100, purity=120),
                     lambda: P.from_solid("NaCl", 0.1, "mol/L", 100, basis="Cu^2+")):
            with self.assertRaises(P.PrepError):
                call()

    def test_mixture(self):
        r = P.mixture([{"substance": "NaCl", "value": 0.1, "unit": "mol/L"},
                       {"substance": "KCl", "value": 2.7, "unit": "mmol/L"}], 1, "L")
        self.assertEqual(len(r["components"]), 2)
        self.assertAlmostEqual(r["components"][1]["mass_g"], 0.0027 * 74.551, delta=0.0001)


class Stock(unittest.TestCase):
    def test_hcl_from_37_percent(self):
        # c = w·ρ/M = 0,37·1184 g/L / 36,458 g/mol = 12,02 mol/L -> 83,2 mL für 1 L 1 mol/L
        r = P.from_stock("HCl", HCL37, 1, "mol/L", 1, "L")
        self.assertAlmostEqual(r["c_stock"], 0.37 * 1184 / 36.458, delta=0.005)
        self.assertAlmostEqual(r["V_stock_mL"], 83.2, delta=0.1)
        self.assertAlmostEqual(r["m_stock_g"], r["V_stock_mL"] * 1.184, places=6)
        self.assertTrue(any("nicht additiv" in n for n in r["notes"]))

    def test_missing_density_is_asked_for(self):
        with self.assertRaises(P.PrepError) as cm:
            P.from_stock("HCl", {"value": 37, "unit": "%(w/w)"}, 1, "mol/L", 1, "L")
        self.assertIn("Dichte", str(cm.exception))

    def test_certified_standard_and_c1v1(self):
        std = {"value": 1000, "unit": "mg/L", "basis": "basis", "source": "Zertifikat"}
        r = P.from_stock("Cu(NO3)2", std, 10, "mg/L", 100, basis="Cu")
        self.assertAlmostEqual(r["V_stock_mL"], 1.0, places=9)                      # 1000 -> 10 mg/L: 1:100
        r = P.from_stock("NaCl", {"value": 1, "unit": "mol/L"}, 50, "mmol/L", 200)
        self.assertAlmostEqual(r["V_stock_mL"], 10.0, places=9)
        with self.assertRaises(P.PrepError):
            P.from_stock("NaCl", {"value": 0.01, "unit": "mol/L"}, 0.1, "mol/L", 100)  # Stamm zu verdünnt


class Dilution(unittest.TestCase):
    def test_series_1_to_10(self):
        r = P.series(1, "mol/L", 10, 5, 10)
        self.assertEqual(len(r["rows"]), 5)
        for i, row in enumerate(r["rows"]):
            self.assertAlmostEqual(row["c"], 10 ** -(i + 1), places=12)
            self.assertAlmostEqual(row["transfer_mL"], row["total_mL"] / 10, places=12)
            nxt = r["rows"][i + 1]["transfer_mL"] if i < 4 else 0
            self.assertAlmostEqual(row["total_mL"] - nxt, 10, places=9)          # jede Stufe behält 10 mL
        self.assertAlmostEqual(r["rows"][-1]["total_mL"], 10, places=12)
        self.assertAlmostEqual(r["stock_needed_mL"], 1.1111, places=9)          # 10 → 11 → 11,1 → 11,11 → 11,111 mL
        r = P.series(1, "mol/L", 10, 3, 1, replicates=3, min_pipette_uL=500)
        self.assertAlmostEqual(r["rows"][-1]["total_mL"], 3, places=12)
        self.assertTrue(any("µL" in n for n in r["notes"]))
        for bad in (lambda: P.series(1, "%(w/w)", 10, 3, 10), lambda: P.series(1, "mol/L", 1, 3, 10),
                    lambda: P.series(1, "mol/L", 10, 0, 10)):
            with self.assertRaises(P.PrepError):
                bad()

    def test_mix_three_stocks_balances(self):
        r = P.mix([{"V": 10, "species": {"Na+": 1.0, "Cl-": 1.0}}, {"V": 5, "species": {"K+": 0.5, "Cl-": 0.5}},
                   {"V": 20, "species": {"Na+": 0.1}}], 100)
        self.assertAlmostEqual(r["species"]["Na+"], (10 * 1 + 20 * 0.1) / 100, places=12)
        self.assertAlmostEqual(r["species"]["Cl-"], (10 + 2.5) / 100, places=12)
        self.assertAlmostEqual(r["fill_mL"], 65, places=12)
        with self.assertRaises(P.PrepError):
            P.mix([{"V": 80, "species": {"A": 1}}, {"V": 30, "species": {"A": 1}}], 100)

    def test_mix_solve_any_unknown(self):
        parts = [{"c": 1.0, "V": 10}, {"c": 0.5, "V": 20}, {"c": 0.2, "V": None}]
        r = P.mix_solve(parts, 0.3, 100)                                           # gesuchtes V₃
        self.assertAlmostEqual(r["parts"][2]["V"], (30 - 10 - 10) / 0.2, places=9)
        self.assertAlmostEqual(r["balance"]["n_parts"], r["balance"]["n_final"], places=9)
        r = P.mix_solve([{"c": 1.0, "V": 10}, {"c": 0.5, "V": 20}], None, 100)     # gesuchtes c
        self.assertAlmostEqual(r["c_final"], 0.2, places=12)
        r = P.mix_solve([{"c": 1.0, "V": 10}, {"c": None, "V": 20}], 0.3, 100)     # gesuchtes c₂
        self.assertAlmostEqual(r["parts"][1]["c"], 1.0, places=12)
        r = P.mix_solve([{"c": 1.0, "V": 10}], 0.05, None)                         # gesuchtes Endvolumen
        self.assertAlmostEqual(r["V_final"], 200, places=9)
        for bad in (lambda: P.mix_solve([{"c": None, "V": None}], 0.5, 100),       # zwei Werte offen
                    lambda: P.mix_solve([{"c": 1, "V": 10}], 2, 100),             # nichts offen
                    lambda: P.mix_solve([{"c": 1.0, "V": None}], 0.0, 100),        # gesuchtes V wäre 0 -> ok?
                    lambda: P.mix_solve([{"c": 1.0, "V": 10}, {"c": None, "V": 20}], 0.01, 100)):  # c₂ negativ
            with self.assertRaises(P.PrepError):
                bad()


class BufferRecipe(unittest.TestCase):
    @skip_unless('srd46')
    def test_phosphate_pair(self):
        r = P.buffer_recipe(7.4, 0.1, 1, "L", acid="NaH2PO4·H2O", base="Na2HPO4·2H2O")
        self.assertAlmostEqual(r["check"]["pH"], 7.40, delta=0.005)
        a, b = r["parts"]
        self.assertAlmostEqual(a["c"] + b["c"], 0.1, places=9)
        self.assertGreater(b["c"], a["c"])                                         # pH > pKa2
        self.assertAlmostEqual(a["mass_g"], a["c"] * 137.99, delta=0.01)
        self.assertAlmostEqual(b["mass_g"], b["c"] * 177.99, delta=0.01)
        self.assertGreater(r["check"]["I"], 0.1)
        self.assertTrue(any("Aktivitäten" in n for n in r["notes"]))

    def test_tris_with_hcl(self):
        stock = {"value": 1, "unit": "mol/L"}
        r = P.buffer_recipe(7.4, 0.05, 500, "mL", form_="Tris", titrant="HCl", titrant_stock=stock)
        self.assertAlmostEqual(r["check"]["pH"], 7.40, delta=0.005)
        self.assertAlmostEqual(r["parts"][0]["mass_g"], 0.05 * 0.5 * 121.135, delta=0.01)
        self.assertLess(r["titrant"]["c_in_buffer"], 0.05)
        self.assertAlmostEqual(r["titrant"]["V_mL"], r["titrant"]["n_mol"] / 1 * 1000, places=9)

    @skip_unless('srd46')
    def test_unreachable(self):
        with self.assertRaises(P.PrepError):
            P.buffer_recipe(11, 0.1, 1, "L", acid="NaH2PO4", base="Na2HPO4")
        with self.assertRaises(P.PrepError):
            P.buffer_recipe(7, 0.1, 1, "L", acid="NaH2PO4")


if __name__ == "__main__":
    unittest.main()
