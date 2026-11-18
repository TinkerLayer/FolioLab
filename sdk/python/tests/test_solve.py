"""S-01/S-02: labcalc.solve (Gleichungen, Einheiten der Unbekannten, Gleichungssysteme)."""
import math
import sys
import unittest
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from labcalc import expr as E  # noqa: E402
from labcalc import solve as SV  # noqa: E402

KG, MS, J = (0, 1, 0, 0, 0, 0, 0), (1, 0, -1, 0, 0, 0, 0), (2, 1, -2, 0, 0, 0, 0)


def eq(src, **ctx):
    l, r = src.split("=")
    c = E.Ctx(**ctx)
    L, R = E.parse(l), E.parse(r)
    return SV.solve_equation(L, R, SV.free_names(SV.residual(L, R), c)[0], c)


class Equations(unittest.TestCase):
    def test_quadratic_surd(self):
        r = eq("x^2 - 3 + x = 0")
        self.assertEqual(r["method"], "quadratic")
        self.assertEqual(r["form"], {"p": Fraction(-1, 2), "q": Fraction(1, 2), "m": 13, "i": False})
        self.assertAlmostEqual(r["solutions"][1]["value"], (-1 + math.sqrt(13)) / 2, places=14)

    def test_rational_roots_split_off(self):
        r = eq("x^3 - 2x = 0")
        self.assertEqual([s.get("exact") for s in r["solutions"]], [None, Fraction(0), None])
        self.assertEqual(r["solutions"][2]["surd"]["m"], 2)

    def test_numeric_and_touching(self):
        self.assertAlmostEqual(eq("x*exp(x) = 1")["solutions"][0]["value"], 0.5671432904097838, places=12)
        r = eq("cos(x) = 1")
        self.assertTrue(any(abs(s["value"] - 2 * math.pi) < 1e-8 for s in r["solutions"]))
        self.assertTrue(any("periodisch" in n for n in r["notes"]))

    def test_identity_and_none(self):
        self.assertEqual(eq("x - x = 0")["status"], "identity")
        self.assertEqual(eq("x - x = 1")["status"], "none")
        self.assertEqual(eq("x^2 + 1 = 0")["status"], "none")
        self.assertEqual(len(eq("x^2 + 1 = 0", complex_ok=True)["solutions"]), 2)

    def test_dims(self):
        r = eq("0.5*m*v^2 = Ek", names={"m": 2.0, "Ek": 100.0}, dims={"m": KG, "Ek": J})
        self.assertEqual(r["dims"], MS)
        self.assertEqual(sorted(s["value"] for s in r["solutions"]), [-10.0, 10.0])
        bad = eq("m + x = Ek", names={"m": 2.0, "Ek": 100.0}, dims={"m": KG, "Ek": J})
        self.assertIsNone(bad["dims"])
        self.assertTrue(bad["notes"])

    def test_bound_names_are_not_unknown(self):
        c = E.Ctx()
        n = E.parse("integral(t^2, t, 0, x) - 9")
        self.assertEqual(SV.free_names(n, c), ["x"])


class Systems(unittest.TestCase):
    def sys(self, src):
        pairs = [tuple(E.parse(p) for p in q.split("=")) for q in src.split(";")]
        return SV.solve_system(pairs, E.Ctx())

    def test_linear_exact(self):
        r = self.sys("2x + 3y = 1; x - y = 2")
        self.assertEqual((r["type"], r["status"], r["rank"]), ("linear", "unique", 2))
        self.assertEqual(r["exact"][0], [Fraction(7, 5), Fraction(-3, 5)])
        self.assertEqual(r["A"], [[2.0, 3.0], [1.0, -1.0]])
        r = self.sys("x + y + z = 6; x - y = 0; 2z = 4")              # rechte Seite 0 ohne Vorzeichen
        self.assertEqual([str(v) for v in r["b"]], ["6.0", "0.0", "4.0"])
        self.assertEqual(r["solutions"], [[2.0, 2.0, 2.0]])

    def test_infinite_and_none(self):
        r = self.sys("x + y = 3; 2x + 2y = 6")
        self.assertEqual((r["status"], r["free"]), ("infinite", ["y"]))
        self.assertEqual(r["param"]["x"], (Fraction(3), {"y": Fraction(-1)}))
        r = self.sys("x + y = 3; x + y = 4")
        self.assertEqual(r["status"], "none")
        self.assertAlmostEqual(r["lsq"][0], 1.75)

    def test_nonlinear(self):
        r = self.sys("x^2 + y^2 = 25; x - y = 1")
        self.assertEqual(r["type"], "nonlinear")
        got = sorted(tuple(round(v, 10) for v in s) for s in r["solutions"])
        self.assertEqual(got, [(-3.0, -4.0), (4.0, 3.0)])


if __name__ == "__main__":
    unittest.main()
