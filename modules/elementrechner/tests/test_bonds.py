"""ER-X01: mittlere Bindungsenthalpien und die ΔrH-Schätzung (immer als Schätzung neben dem Tabellenwert)."""
import base64
import unittest

from labcalc import bonds as BD
from labcalc import chem as C

from elementrechner import analysis as AN
from elementrechner import bundle as B


def _est(text):
    eq = C.parse_equation(text)
    return BD.estimate(eq, C.balance(eq)["coefs"])


class Bonds(unittest.TestCase):
    def test_lookup_symmetric(self):
        self.assertEqual(BD.lookup("H", "N")["D"], BD.lookup("N", "H")["D"])
        self.assertEqual(BD.lookup("C", "C", 2)["length_pm"], 134)
        with self.assertRaises(C.ChemError):
            BD.lookup("Xe", "F")

    def test_counts(self):
        self.assertEqual(BD.bond_counts("CCO"), {("C", "C", 1): 1, ("C", "O", 1): 1, ("C", "H", 1): 5, ("H", "O", 1): 1})

    def test_estimates_hand_checked(self):
        self.assertAlmostEqual(_est("H2 + Cl2 -> HCl")["dH_est"], 436 + 242 - 2 * 431)
        self.assertAlmostEqual(_est("CH4 + O2 -> CO2 + H2O")["dH_est"], 4 * 412 + 2 * 497 - 2 * 743 - 4 * 463)
        self.assertAlmostEqual(_est("N2 + H2 -> NH3")["dH_est"], 945 + 3 * 436 - 6 * 388)

    def test_in_thermo_and_report(self):
        r = AN.equation_result("H2 + Cl2 -> HCl")
        self.assertTrue(r["thermo"]["bond_estimate"]["estimate"])
        d = B.build({"state": {"equation": "H2 + Cl2 -> HCl"}}, "de")
        tex = {k: base64.b64decode(v).decode("utf-8") for k, v in d["files"].items() if k.endswith(".tex")}
        self.assertIn("mittleren Bindungsenthalpien", tex["text-thermochemie.tex"])
        self.assertIn(r"\approx -184", tex["text-thermochemie.tex"])


if __name__ == "__main__":
    unittest.main()
