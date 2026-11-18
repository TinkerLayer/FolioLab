"""Rechner 1.4.0 (wissenschaftliche Prüfung): Integral, Ableitung, Einheiten durch Funktionen, exakte Konstanten,
Härteeinheiten, Ausgleichsrechnung, rationale Nullstellen, Ionisierungsenergie, Quellen.

Bezugswerte: analytisch (im Kommentar hergeleitet) oder SciPy (nur in Tests, nie zur Laufzeit).
"""
import math
import sys
import unittest
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from labcalc import expr as E  # noqa: E402
from labcalc import fitting as F  # noqa: E402
from labcalc import render as R  # noqa: E402
from labcalc import solve as SV  # noqa: E402
from labcalc import sources as SRC  # noqa: E402
from labcalc import stats as ST  # noqa: E402
from labcalc import units as U  # noqa: E402
from laboptional import skip_unless  # noqa: E402

try:
    import scipy.integrate as SI
    import scipy.optimize as SO
    import scipy.special as SS
    import scipy.stats as SST
except ImportError:                                      # pragma: no cover
    SI = SO = SS = SST = None
needs_scipy = unittest.skipIf(SI is None, "SciPy fehlt (nur Testabhängigkeit)")


def ev(src, **dims):
    ctx = E.Ctx()
    v = E.evaluate(E.parse(src), ctx)
    return float(np.real(v)), ctx.notes


def dims(src, **kw):
    return E.dims_of(E.parse(src), {k: U.parse_unit(u)[1] for k, u in kw.items()})


class Integral(unittest.TestCase):
    def test_gauss_kronrod_constants(self):
        # K15 integriert Polynome bis Grad 3·7+1 = 22 exakt, G7 bis Grad 13: ∫_{-1}^{1} x^k dx = 2/(k+1) für gerades k.
        for k in (0, 2, 10, 22):
            self.assertAlmostEqual(float(np.dot(E.GK_W, E.GK_X ** k)), 2 / (k + 1), places=14)
        for k in (0, 6, 12):                                         # G7_W: Gewichte auf den Kronrod-Stützstellen, 0 ausser bei G7
            self.assertAlmostEqual(float(np.dot(E.G7_W, E.GK_X ** k)), 2 / (k + 1), places=14)
        self.assertAlmostEqual(float(sum(E.GK_W)), 2.0, places=15)

    def test_known_integrals(self):
        cases = [("integral(x^2, x, 0, 3)", 9.0),                      # x³/3 von 0 bis 3
                 ("integral(exp(-x^2), x, -inf, inf)", math.sqrt(math.pi)),   # Gauss-Integral
                 ("integral(exp(-x)*sin(x), x, 0, inf)", 0.5),          # 1/(1+1²)
                 ("integral(1/x^2, x, 1, inf)", 1.0),                    # [−1/x] von 1 bis ∞
                 ("integral(1/sqrt(x), x, 0, 1)", 2.0),                  # 2√x, Singularität am Rand
                 ("integral(abs(x-0.3), x, 0, 1)", 0.29)]                # 0,3²/2 + 0,7²/2, Knick
        for src, want in cases:
            with self.subTest(src=src):
                v, _ = ev(src)
                self.assertLess(abs(v - want), 1e-8 * max(1, abs(want)))

    @needs_scipy
    def test_against_scipy(self):
        for src, f, a, b in [("integral(ln(x)*x, x, 0, 2)", lambda x: math.log(x) * x, 0, 2),
                             ("integral(1/(1+x^2), x, 0, inf)", lambda x: 1 / (1 + x * x), 0, np.inf),
                             ("integral(cos(x)^2, x, 0, 10)", lambda x: math.cos(x) ** 2, 0, 10)]:
            with self.subTest(src=src):
                want = SI.quad(f, a, b, epsabs=1e-13, epsrel=1e-13)[0]    # SciPy QUADPACK
                self.assertAlmostEqual(ev(src)[0], want, places=9)

    @needs_scipy
    def test_oscillating_improper_integral_refused(self):
        # ∫₁^∞ sin x/x dx = π/2 − Si(1) = 0,624713… (SciPy sici); früher stillschweigend 2,293.
        want = math.pi / 2 - SS.sici(1.0)[0]
        self.assertAlmostEqual(want, 0.6247132564277136, places=12)
        with self.assertRaises(E.CalcError) as cm:
            ev("integral(sin(x)/x, x, 1, inf)")
        self.assertIn("konvergiert", str(cm.exception))

    def test_error_estimate(self):
        r = E.quad(lambda x: np.exp(x), 0.0, 1.0)
        self.assertTrue(r.converged)
        self.assertLess(r.err, 1e-12)
        self.assertAlmostEqual(float(r), math.e - 1, places=13)       # e¹ − e⁰


class Derivative(unittest.TestCase):
    def test_known_derivatives(self):
        cases = [("deriv(sqrt(x), x, 1e-4)", 50.0, 1e-7),                 # 1/(2√x) bei x = 10⁻⁴, Schritt bleibt in x > 0
                 ("deriv(sin(1000x), x, 0.001)", 1000 * math.cos(1), 1e-7),   # 1000·cos(1)
                 ("deriv(x+1, x, 1e-10)", 1.0, 1e-9),                       # relativer Schritt bei kleinem x
                 ("deriv(x^3, x, 2)", 12.0, 1e-9),
                 ("deriv(x^3, x, 2, 2)", 12.0, 1e-6),                        # 6x
                 ("deriv(exp(x), x, 0, 2)", 1.0, 1e-6),
                 ("deriv(sin(x), x, 1e6)", math.cos(1e6), 1e-6)]             # grosses x: Schritt relativ
        for src, want, tol in cases:
            with self.subTest(src=src):
                v, _ = ev(src)
                self.assertLess(abs(v - want), tol * max(1, abs(want)))

    def test_one_sided_at_domain_boundary(self):
        v, _ = ev("deriv(x^1.5, x, 0)")                     # 1,5·√x = 0 bei x = 0; zentral läge x < 0 ausserhalb
        self.assertLess(abs(v), 1e-4)

    def test_kink_gets_note(self):
        _, notes = ev("deriv(abs(x), x, 0)")
        self.assertTrue(any("Ableitung" in n for n in notes))

    def test_render_not_defined(self):
        for v in (float("nan"), float("inf"), -float("inf")):
            self.assertTrue(R.num_tex(v, "de", 6))
            self.assertTrue(R.num_html(v, "en", 6))
        self.assertIn("nicht definiert", R.num_tex(float("nan"), "de", 6))


class UnitsThroughFunctions(unittest.TestCase):
    def test_calculus_keeps_units(self):
        m, s = U.parse_unit("m")[1], U.parse_unit("s")[1]
        self.assertTrue(U.deq(dims("integral(v, x, 0, t)", v="m/s", t="s"), m))         # (m/s)·s
        self.assertTrue(U.deq(dims("deriv(v*x, x, t)", v="m/s", t="s"), U.parse_unit("m/s")[1]))
        self.assertTrue(U.deq(dims("sum(v, k, 1, 3)", v="m/s"), U.parse_unit("m/s")[1]))
        self.assertTrue(U.deq(dims("inv([[t]])", t="s"), U.parse_unit("1/s")[1]))
        self.assertIsNone(dims("[v, t]", v="m/s", t="s"))                                   # gemischt: unbekannt
        self.assertTrue(U.deq(dims("var(x)", x="m"), U.parse_unit("m^2")[1]))
        self.assertTrue(U.deq(dims("nsolve(x*v == 6*s0, x, t)", v="m/s", t="s", s0="m"), s))

    def test_delta_syntax(self):
        self.assertEqual(U.split_delta("Δ°C"), ("°C", True))
        self.assertEqual(U.split_delta("Delta °F"), ("°F", True))
        self.assertEqual(U.split_delta("°C"), ("°C", False))
        self.assertAlmostEqual(U.from_si(10.0, "°F", diff=True), 18.0, places=12)     # 10 K = 18 °F (Differenz)


class ExactConstants(unittest.TestCase):
    """SI 2019 (BIPM-Broschüre, 9. Aufl.): h, c, k, N_A, e exakt; abgeleitete Konstanten daraus berechnet."""

    def test_derived_constants(self):
        h, c, k, NA, e = 6.62607015e-34, 299792458.0, 1.380649e-23, 6.02214076e23, 1.602176634e-19
        self.assertAlmostEqual(U.HBAR / (h / (2 * math.pi)), 1, places=15)
        self.assertAlmostEqual(U.R_GAS / (NA * k), 1, places=15)
        self.assertAlmostEqual(U.FARADAY / (NA * e), 1, places=15)
        self.assertAlmostEqual(U.SIGMA_SB / (2 * math.pi ** 5 * k ** 4 / (15 * h ** 3 * c ** 2)), 1, places=14)
        x = h * c / (k * U.WIEN_B)                                   # b = hc/(k·x), x = 5(1 − e^−x) (Wiensches Verschiebungsgesetz)
        self.assertAlmostEqual(x, 5 * (1 - math.exp(-x)), places=14)
        # CODATA 2022 (auf 10 Stellen veröffentlicht, exakt): Übereinstimmung bis zur letzten Stelle
        for got, pub in [(U.HBAR, 1.054571817e-34), (U.R_GAS, 8.314462618), (U.FARADAY, 96485.33212),
                         (U.SIGMA_SB, 5.670374419e-8), (U.WIEN_B, 2.897771955e-3)]:
            self.assertLess(abs(got / pub - 1), 1e-9)

    def test_hardness_units(self):
        # 1 °dH = 10 mg CaO/L; 1 °fH = 10 mg CaCO3/L (Molmassen aus IUPAC-Standardatomgewichten, gekürzt)
        self.assertAlmostEqual(U.to_si(1, "°dH"), 10 / (40.078 + 15.999), places=10)
        self.assertAlmostEqual(U.to_si(1, "°fH"), 10 / (40.078 + 12.011 + 3 * 15.999), places=10)


class Fitting(unittest.TestCase):
    def test_r2_through_origin_uncentred(self):
        x = np.array([1.0, 2, 3, 4])
        y = np.array([2.1, 3.9, 6.2, 7.8])
        r = F.fit(x, y, "prop")
        m = float(np.dot(x, y) / np.dot(x, x))                       # m = Σxy/Σx²
        sse = float(np.sum((y - m * x) ** 2))
        self.assertAlmostEqual(r["params"][0]["value"], m, places=12)
        self.assertAlmostEqual(r["r2"], 1 - sse / float(np.dot(y, y)), places=12)   # SST = Σy² ohne Achsenabschnitt
        self.assertFalse(r["r2_centred"])

    def test_line_uncertainty_analytic(self):
        x = np.array([0.0, 1, 2, 3, 4, 5])
        y = np.array([0.1, 2.2, 3.9, 6.1, 8.0, 9.8])
        r = F.fit(x, y, "lin")
        n = x.size
        sxx = float(np.sum((x - x.mean()) ** 2))
        m = float(np.sum((x - x.mean()) * (y - y.mean())) / sxx)
        b = float(y.mean() - m * x.mean())
        s = math.sqrt(float(np.sum((y - m * x - b) ** 2)) / (n - 2))
        um, ub = s / math.sqrt(sxx), s * math.sqrt(1 / n + x.mean() ** 2 / sxx)   # Lehrbuchformeln Gerade
        pm = next(p for p in r["params"] if p["sym"] == "m")
        pb = next(p for p in r["params"] if p["sym"] == "b")
        self.assertAlmostEqual(pm["u"], um, places=12)
        self.assertAlmostEqual(pb["u"], ub, places=12)

    @needs_scipy
    def test_direct_uses_all_points_and_matches_curve_fit(self):
        x = np.array([0.0, 0.5, 1, 1.5, 2, 3, 4, 5])
        y = np.array([5.02, 3.01, 1.86, 1.10, 0.70, 0.22, 0.05, -0.03])   # letzter Wert ≤ 0 (Rauschen)
        r = F.fit(x, y, "exp", "direct")
        self.assertEqual(r["n"], 8)                                      # alle Punkte, auch y ≤ 0
        self.assertTrue(r["converged"])
        p, cov = SO.curve_fit(lambda t, a, b: a * np.exp(b * t), x, y, p0=[5, -1])   # SciPy, absolute_sigma=False
        got = [q["value"] for q in r["params"]]
        np.testing.assert_allclose(got, p, rtol=1e-6)
        np.testing.assert_allclose([q["u"] for q in r["params"]], np.sqrt(np.diag(cov)), rtol=1e-4)

    def test_convergence_criterion(self):
        J = np.array([[1.0, 0], [0, 1], [0, 0]])
        y = np.array([1.0, 1, 1])
        self.assertTrue(F.converged(J, np.array([0.0, 0, 1]), y))          # Residuum ⟂ Spalten: Optimum
        self.assertFalse(F.converged(J, np.array([1.0, 0, 0]), y))         # Residuum in Spaltenrichtung

    def test_lineweaver_burk_labelled(self):
        S = np.array([0.5, 1, 2, 4, 8, 16])
        v = 10 * S / (2 + S) * np.array([1.02, 0.98, 1.01, 0.99, 1.0, 1.01])
        r = F.fit(S, v, "mm", "lin")
        self.assertEqual(r["method"], "Lineweaver–Burk")
        self.assertEqual(r["u_method"], "first_order_back_transform")
        self.assertTrue(any("verzerrt" in n for n in r["notes"]))

    def test_log_model_states_unit_of_x(self):
        x = np.array([1.0, 2, 4, 8])
        r = F.fit(x, 1 + 2 * np.log(x), "log", xunit="mm")
        self.assertEqual(r["a_xunit"], "mm")
        self.assertTrue(any("x = 1 mm" in n for n in r["notes"]))

    @needs_scipy
    def test_t_quantiles_against_scipy(self):
        for dof in (1, 2, 3, 5, 10, 30, 100):
            self.assertAlmostEqual(ST.t_ppf(0.975, dof), float(SST.t.ppf(0.975, dof)), places=9)


class RationalRoots(unittest.TestCase):
    def test_denominator_above_1000(self):
        # (1001x − 1)(x² − 2)(x − 3) = 1001x⁴ − 3004x³ − 1999x² + 6008x − 6 (ausmultipliziert)
        c = [Fraction(v) for v in (-6, 6008, -1999, -3004, 1001)]
        sols = SV.solve_poly(c)[0]
        exact = {s["exact"] for s in sols if isinstance(s.get("exact"), Fraction)}
        self.assertIn(Fraction(1, 1001), exact)                         # früher als Gleitkommazahl (Grenze 1000)
        self.assertIn(Fraction(3), exact)
        self.assertEqual(sum(1 for s in sols if abs(abs(s["value"]) - math.sqrt(2)) < 1e-12), 2)


class Ionization(unittest.TestCase):
    def test_kj_per_mol_factor(self):
        from labcalc import ionization as IO
        self.assertAlmostEqual(IO.EV_KJMOL, 96.48533212, places=8)          # CODATA 2022 F/1000
        self.assertEqual(IO.EV_J, 1.602176634e-19)                          # e, exakt

    @skip_unless('asd')
    def test_ie_is_an_energy(self):
        from labcalc import ionization as IO
        E._register_chem()
        fn, _, _, d, _ = E.STRFUNCS["IE"]
        self.assertTrue(U.deq(d, U.kind_dims("energy")))
        self.assertAlmostEqual(fn(None, "Na", 1) / 1.602176634e-19, IO.ie(11, 1)["eV"], places=12)
        self.assertAlmostEqual(E.STRFUNCS["IE_eV"][0](None, "Na", 1), IO.ie(11, 1)["eV"], places=12)


class Sources(unittest.TestCase):
    def test_new_and_english_entries(self):
        self.assertEqual(SRC.REFS["trost1991"]["doi"], "10.1126/science.1962206")
        self.assertIn("Flannery", SRC.REFS["press2007"]["authors"])
        for key in ("iso6892", "iso178", "iso6507", "iso6506", "iso18265"):
            self.assertIn("deutsch:", SRC.REFS[key]["note"])
            self.assertNotIn("Metallische", SRC.REFS[key]["title"])


if __name__ == "__main__":
    unittest.main()
