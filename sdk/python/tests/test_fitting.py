"""G-02: Ausgleichsrechnung (labcalc.fitting) und t-Verteilung (labcalc.stats)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from labcalc import fitting as F  # noqa: E402
from labcalc import stats as ST  # noqa: E402


def par(res, sym):
    return next(p for p in res["params"] if p["sym"] == sym)


class Stats(unittest.TestCase):
    def test_t_quantiles(self):
        self.assertAlmostEqual(ST.t_ppf(0.975, 10), 2.2281, places=3)
        self.assertAlmostEqual(ST.t_ppf(0.975, 1), 12.706, places=2)
        self.assertAlmostEqual(ST.t_cdf(0.0, 5), 0.5, places=9)


class Fitting(unittest.TestCase):
    def setUp(self):
        self.rng = np.random.default_rng(7)

    def test_line_with_units_and_ci(self):
        x = np.linspace(0, 2, 50)
        y = 2.5 * x + 0.3 + self.rng.normal(0, 0.01, x.size)
        r = F.fit(x, y, "lin", xunit="%", yunit="MPa")
        m, b = par(r, "m"), par(r, "b")
        self.assertAlmostEqual(m["value"], 2.5, places=2)
        self.assertAlmostEqual(b["value"], 0.3, places=2)
        self.assertEqual(m["unit"], "MPa/%")
        self.assertEqual(b["unit"], "MPa")
        self.assertGreater(m["u"], 0)
        self.assertAlmostEqual(m["ci"], m["u"] * ST.t_ppf(0.975, 48), places=9)
        self.assertGreater(r["r2"], 0.999)
        self.assertEqual((r["n"], r["dof"]), (50, 48))
        self.assertEqual(len(r["plots"]), 2)                      # linearisierte Ansicht und Residuen

    def test_exponential_linearised_and_direct(self):
        x = np.linspace(0, 3, 40)
        y = 4.0 * np.exp(-0.8 * x) * (1 + self.rng.normal(0, 0.005, x.size))
        lin = F.fit(x, y, "exp", "lin")
        direct = F.fit(x, y, "exp", "direct")
        for r in (lin, direct):
            self.assertAlmostEqual(par(r, "a")["value"], 4.0, places=1)
            self.assertAlmostEqual(par(r, "b")["value"], -0.8, places=2)
        self.assertIsNotNone(lin["r2_lin"])
        self.assertEqual(direct["mode"], "direct")

    def test_non_positive_values_for_log_forms(self):
        r = F.fit(np.array([1.0, 2, 3, 4]), np.array([1.0, -2, 3, 4]), "exp", "lin")
        self.assertEqual(r["n"], 3)                                 # y ≤ 0 fällt weg, mit Hinweis
        self.assertTrue(any("y ≤ 0" in n for n in r["notes"]))
        with self.assertRaises(F.FitError):
            F.fit(np.array([1.0, 2, 3]), np.array([-1.0, -2, 3]), "exp", "lin")

    def test_arrhenius_in_celsius_gives_kj_per_mol(self):
        T_C = np.linspace(20, 120, 12)
        k = 1e7 * np.exp(-50_000 / (F.R_GAS * (T_C + 273.15)))
        r = F.fit(T_C, k, "arrh", "lin", xunit="°C", yunit="1/s")
        ea = par(r, "Ea")
        self.assertEqual(ea["unit"], "kJ/mol")
        self.assertAlmostEqual(ea["value"], 50.0, places=3)
        self.assertAlmostEqual(par(r, "A")["value"] / 1e7, 1.0, places=3)

    def test_michaelis_menten(self):
        S = np.array([0.5, 1, 2, 4, 8, 16])
        v = 10 * S / (2 + S)
        r = F.fit(S, v, "mm", "direct")
        self.assertAlmostEqual(par(r, "Vmax")["value"], 10, places=4)
        self.assertAlmostEqual(par(r, "Km")["value"], 2, places=4)

    def test_polynomial_and_predict(self):
        x = np.linspace(-2, 2, 21)
        y = 0.5 * x ** 2 - x + 1
        r = F.fit(x, y, "poly2")
        p = [q["value"] for q in r["params"]]
        np.testing.assert_allclose(p, [0.5, -1, 1], atol=1e-9)
        np.testing.assert_allclose(F.predict("poly2", p, np.array([3.0])), [2.5], atol=1e-9)

    def test_too_few_points(self):
        with self.assertRaises(F.FitError):
            F.fit(np.array([1.0]), np.array([2.0]), "lin")

    def test_every_model_described(self):
        for key, (de, en, formula, params, lin) in F.MODELS.items():
            self.assertTrue(de and en and formula and params, key)
            self.assertIn(key, F.LIN_AXES)


if __name__ == "__main__":
    unittest.main()
