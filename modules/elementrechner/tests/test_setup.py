"""Reaktionsansatz und Skalierung (ER-L05)."""
import unittest

from labcalc import reaction_setup as R

ETOH = {"value": 0.789, "unit": "g/mL", "T_C": 20, "source": "Datenblatt Ethanol"}
INP = {"equation": "CH3COOH + C2H5OH -> CH3COOC2H5 + H2O",
       "reference": {"i": 0, "value": 50, "unit": "mmol"},
       "reagents": {1: {"equiv": 3, "density": ETOH}},
       "extras": [{"name": "Toluol", "role": "solvent", "value": 20, "unit": "mL"},
                  {"name": "H2SO4", "formula": "H2SO4", "role": "catalyst", "value": 5, "unit": "mol%"}],
       "conditions": {"T": "Rückfluss", "t": "3 h"}}


class Setup(unittest.TestCase):
    def test_table(self):
        p = R.plan(**INP)
        ac, et = p["reactants"]
        self.assertAlmostEqual(ac["n_mol"], 0.05)
        self.assertAlmostEqual(ac["m_g"], 0.05 * 60.052, delta=0.001)
        self.assertAlmostEqual(et["n_mol"], 0.15)
        self.assertAlmostEqual(et["V_mL"], 0.15 * 46.069 / 0.789, delta=0.01)
        self.assertEqual(p["limiting"], 0)
        self.assertAlmostEqual(et["excess_mol"], 0.10)
        self.assertAlmostEqual(p["products"][0]["m_theor_g"], 0.05 * 88.106, delta=0.001)
        tol, cat = p["extras"]
        self.assertFalse(tol["in_stoichiometry"])
        self.assertAlmostEqual(cat["n_mol"], 0.0025)
        self.assertAlmostEqual(cat["m_g"], 0.0025 * 98.07, delta=0.001)
        self.assertEqual(p["conditions"]["t"], "3 h")

    def test_solvent_does_not_change_stoichiometry(self):
        a = R.plan(**INP)
        b = R.plan(**{**INP, "extras": [{"name": "Toluol", "role": "solvent", "value": 500, "unit": "mL"}]})
        self.assertEqual([r["n_mol"] for r in a["reactants"]], [r["n_mol"] for r in b["reactants"]])
        self.assertEqual(a["products"][0]["n_theor_mol"], b["products"][0]["n_theor_mol"])

    def test_scale_keeps_equivalents(self):
        s = R.scale(INP, 2.5)
        a, b = R.plan(**INP), R.plan(**s)
        for ra, rb in zip(a["reactants"], b["reactants"]):
            self.assertEqual(ra["equiv"], rb["equiv"])
            self.assertAlmostEqual(rb["n_mol"], 2.5 * ra["n_mol"])
        self.assertAlmostEqual(b["extras"][0]["V_mL"], 50)                         # absolutes Volumen skaliert
        self.assertAlmostEqual(b["extras"][1]["n_mol"], 2.5 * a["extras"][1]["n_mol"])   # mol% bleibt mol%
        self.assertEqual(INP["reference"]["value"], 50)                           # Eingabe unverändert

    def test_observed_does_not_change_plan(self):
        a = R.plan(**INP)
        b = R.plan(**INP, observed={"masses": {2: 3.1, 0: 3.05}})
        self.assertEqual(a["reactants"], b["reactants"])
        self.assertEqual(a["products"], b["products"])
        self.assertAlmostEqual(b["observed"][2]["yield"], 3.1 / (0.05 * 88.106), delta=0.001)
        self.assertEqual(b["observed"][0]["kind"], "reactant")

    def test_target_and_refusals(self):
        p = R.plan(INP["equation"], {"i": 0}, target={"i": 2, "value": 4.406, "unit": "g", "yield_pct": 80})
        self.assertAlmostEqual(p["reactants"][0]["n_mol"], 4.406 / 88.106 / 0.8, delta=1e-4)
        for bad in (lambda: R.plan(INP["equation"], {"i": 2, "value": 1, "unit": "mmol"}),       # Produkt als Bezug
                    lambda: R.plan(INP["equation"], {"i": 0, "value": -1, "unit": "mmol"}),
                    lambda: R.plan(INP["equation"], {"i": 0, "value": 1, "unit": "mmol"},
                                   extras=[{"name": "x", "role": "magic", "value": 1, "unit": "mL"}]),
                    lambda: R.plan(INP["equation"], {"i": 0, "value": 1, "unit": "mmol"},
                                   reagents={1: {"equiv": 2, "density": {"value": 0.79}}}),          # Dichte ohne Quelle
                    lambda: R.scale(INP, 0)):
            with self.assertRaises((R.SetupError, R.P.PrepError)):
                bad()


class Green(unittest.TestCase):
    TOL = {"value": 0.867, "unit": "g/mL", "T_C": 20, "source": "Datenblatt Toluol"}

    def _plan(self, **kw):
        ex = [{"name": "Toluol", "role": "solvent", "value": 20, "unit": "mL", "density": self.TOL},
              {"name": "H2SO4", "formula": "H2SO4", "role": "catalyst", "value": 5, "unit": "mol%"}]
        return R.plan(**{**INP, "extras": ex, **kw})

    def test_definitions(self):
        p = self._plan(observed={"masses": {2: 3.5}})
        m = R.metrics(p, workup=[{"name": "Wasser (Waschen)", "m_g": 30}])
        m_in = sum(r["m_g"] for r in p["reactants"]) + 20 * 0.867 + p["extras"][1]["m_g"] + 30
        self.assertAlmostEqual(m["m_in_g"], m_in, places=9)
        self.assertAlmostEqual(m["E_factor"], (m_in - 3.5) / 3.5, places=9)
        self.assertAlmostEqual(m["PMI"], m["E_factor"] + 1, places=9)               # PMI = E + 1
        self.assertAlmostEqual(m["RME"], 3.5 / sum(r["m_g"] for r in p["reactants"]), places=9)
        self.assertAlmostEqual(m["solvent_share"], 20 * 0.867 / m_in, places=9)
        self.assertAlmostEqual(m["atom_economy"], 88.106 / (60.052 + 46.069), delta=1e-4)
        self.assertEqual(m["product_basis"], "isoliert")
        self.assertIn("Lösungsmittel", m["boundary_text"])

    def test_boundary_changes_and_is_printed(self):
        p = self._plan()
        full = R.metrics(p)
        noslv = R.metrics(p, boundary={"solvents": False})
        self.assertLess(noslv["E_factor"], full["E_factor"])
        self.assertIn("nicht eingerechnet: Lösungsmittel", noslv["boundary_text"])
        self.assertEqual(full["product_basis"], "theoretisch (100 % Ausbeute)")
        with self.assertRaises(R.SetupError):                                      # Volumen ohne Dichte
            R.metrics(R.plan(**INP))
        self.assertEqual(len(R.compare([p, R.plan(**R.scale(INP, 2))], boundary={"solvents": False})), 2)


if __name__ == "__main__":
    unittest.main()
