import sys
import unittest
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from labcalc import chem as C  # noqa: E402
from labcalc import expr as E  # noqa: E402


def bal(s):
    return C.balance(C.parse_equation(s))


class Parse(unittest.TestCase):
    def test_formula_counts(self):
        sp = C.parse_species("Ca3(PO4)2")
        self.assertEqual(sp.counts, {"Ca": 3, "P": 2, "O": 8})
        sp = C.parse_species("[Fe(CN)6]^4-")
        self.assertEqual((sp.counts, sp.charge), ({"Fe": 1, "C": 6, "N": 6}, -4))
        self.assertEqual(C.parse_species("CuSO4·5H2O").counts, {"Cu": 1, "S": 1, "O": 9, "H": 10})
        self.assertEqual(C.parse_species("CuSO4.5H2O").counts, {"Cu": 1, "S": 1, "O": 9, "H": 10})
        self.assertEqual(C.parse_species("Fe0.95O").counts, {"Fe": Fraction(19, 20), "O": 1})
        self.assertEqual(C.parse_species("D2O").counts, {"2H": 2, "O": 1})
        self.assertEqual(C.parse_species("^13CH4").counts, {"13C": 1, "H": 4})

    def test_charges_and_phases(self):
        self.assertEqual(C.parse_species("SO4^2-").charge, -2)
        self.assertEqual(C.parse_species("Fe+3").charge, 3)
        self.assertEqual(C.parse_species("NH4+").charge, 1)
        sp = C.parse_species("NO3-")
        self.assertEqual((sp.counts, sp.charge), ({"N": 1, "O": 3}, -1))
        sp = C.parse_species("Fe3+")
        self.assertEqual((sp.counts["Fe"], sp.charge), (3, 1))        # wie mhchem, mit Hinweis
        self.assertTrue(sp.hints)
        sp = C.parse_species("NaCl(s)")
        self.assertEqual((sp.phase, sp.unicode()), ("s", "NaCl(s)"))
        self.assertEqual(C.parse_species("SO4^2-").mhchem(), "SO4^{2-}")
        self.assertEqual(C.parse_species("CuSO4.5H2O").unicode(), "CuSO₄·5H₂O")

    def test_errors(self):
        with self.assertRaises(C.ChemError):
            C.parse_species("Xx2")
        with self.assertRaises(C.ChemError):
            C.parse_species("Ca(OH")
        with self.assertRaises(C.ChemError):
            C.parse_equation("H2O -> ?")


class Balance(unittest.TestCase):
    def test_textbook(self):
        self.assertEqual(bal("C3H8 + O2 -> CO2 + H2O")["coefs"], ["1", "5", "3", "4"])
        self.assertEqual(bal("KMnO4 + HCl -> KCl + MnCl2 + H2O + Cl2")["coefs"], ["2", "16", "2", "2", "8", "5"])
        self.assertEqual(bal("MnO4^- + Fe^2+ + H^+ -> Mn^2+ + Fe^3+ + H2O")["coefs"], ["1", "5", "8", "1", "5", "4"])
        self.assertEqual(bal("Ca(OH)2 + H3PO4 -> Ca3(PO4)2 + H2O")["coefs"], ["3", "2", "1", "6"])
        self.assertEqual(bal("H++OH- -> H2O")["coefs"], ["1", "1", "1"])
        r = bal("N2 + H2 <=> NH3")
        self.assertEqual(r["text"], "N₂ + 3 H₂ ⇌ 2 NH₃")
        self.assertEqual(r["mhchem"], "N2 + 3 H2 <=> 2 NH3")

    def test_fixed_coefficients(self):
        self.assertEqual(bal("1/2 N2 + H2 -> NH3")["coefs"], ["1/2", "3/2", "1"])
        self.assertEqual(bal("2 H2 + O2 -> 2 H2O")["status"], "ok")
        r = bal("2 H2 + 1 O2 -> 3 H2O")
        self.assertEqual(r["status"], "given_wrong")
        self.assertEqual(r["suggestion"], ["2", "1", "2"])
        r = bal("2 H2 + O2 -> 3 H2O")
        self.assertIn("H: links 4, rechts 6", r["reason"])

    def test_problems_are_explained(self):
        self.assertEqual(bal("H2O -> H2O2")["status"], "impossible")
        r = bal("H2 + O2 -> H2O2 + H2O")
        self.assertEqual((r["status"], r["dim"]), ("ambiguous", 2))
        r = bal("NaCl -> Na + Cl2 + K")
        self.assertEqual(r["status"], "impossible")
        self.assertIn("K kommt nur rechts vor", r["reason"])

    def test_nuclear(self):
        self.assertEqual(bal("^235U + n -> ^141Ba + ^92Kr + n")["text"], "²³⁵U + n → ¹⁴¹Ba + ⁹²Kr + 3 n")
        r = bal("^238U -> ^234Th + ?")
        self.assertEqual(r["text"], "²³⁸U → ²³⁴Th + α")
        self.assertIn("A = 4, Z = 2", r["identified"])
        self.assertEqual(bal("^27Al + alpha -> ^30P + ?")["text"], "²⁷Al + α → ³⁰P + n")
        self.assertEqual(bal("^14C -> ^14N + beta- + antinu")["status"], "ok")
        self.assertEqual(bal("U-238 -> Th-234 + alpha")["status"], "ok")
        r = bal("^238U -> ^235Th + alpha")
        self.assertIn("A: links 238, rechts 239", r["reason"])


class CalcFunctions(unittest.TestCase):
    def test_string_functions_keep_names_free(self):
        self.assertEqual(E.preprocess("n(T-1)"), "n * ( T - 1 )")
        self.assertEqual(E.preprocess('n("CaCO3", m)'), 'n ( "CaCO3" , m )')
        self.assertIn("M", E.STRFUNCS)
        self.assertTrue(any(g[0] == "Chemie" for g in E.FUNC_DOC))


if __name__ == "__main__":
    unittest.main()
