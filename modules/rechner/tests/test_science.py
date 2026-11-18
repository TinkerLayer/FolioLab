"""Rechner 1.4.0, wissenschaftliche Prüfung: Temperaturdifferenzen, Einheiten durch Funktionen, Toleranz der Probe,
Berührnullstellen, Unsicherheit der Graph-Regression, Ziffern im Bericht, Formelzahl.

Bezugswerte analytisch (im Kommentar) oder aus SciPy (nur im Test).
"""
import json
import math
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[2] / "sdk" / "python"))

import numpy as np  # noqa: E402

from rechner import bundle as B  # noqa: E402
from rechner import console as C  # noqa: E402
from rechner import graph as G  # noqa: E402
from rechner import library as L  # noqa: E402
from rechner import solver as S  # noqa: E402
from rechner import units as U  # noqa: E402

try:
    import scipy.stats as SST
except ImportError:                                  # pragma: no cover
    SST = None

Q = {"T1": {"si": 293.15, "kind": "temperature"}, "T2": {"si": 303.15, "kind": "temperature"},
     "v": {"si": 2.0, "kind": "velocity"}, "t": {"si": 3.0, "kind": "time"}}


def line(src):
    return C.evaluate_line({"line": src, "quantities": Q})


class TemperatureDifference(unittest.TestCase):
    def test_difference_converted_without_offset(self):
        r = line("T2 - T1 -> °F")                        # 10 K Differenz = 18 °F Differenz (nicht −441,67 °F)
        self.assertAlmostEqual(float(r["result"]["value"]), 18.0, places=9)
        self.assertIn("Δ", r["unit"])
        r = line("T2 - T1 -> °C")
        self.assertAlmostEqual(float(r["result"]["value"]), 10.0, places=9)

    def test_absolute_temperature_keeps_offset(self):
        r = line("(T1 + T2)/2 -> °C")                    # Mittelwert ist eine Temperatur: 298,15 K = 25 °C
        self.assertAlmostEqual(float(r["result"]["value"]), 25.0, places=9)
        self.assertNotIn("Δ", r["unit"])

    def test_explicit_delta_syntax(self):
        r = line("T1 -> Δ°F")                            # ausdrücklich als Differenz: 293,15 K · 9/5
        self.assertAlmostEqual(float(r["result"]["value"]), 293.15 * 9 / 5, places=9)


class UnitsThroughFunctions(unittest.TestCase):
    def test_integral_and_derivative_have_units(self):
        self.assertEqual(line("integral(v, x, 0, t)")["unit"], "m")          # (m/s)·s
        self.assertEqual(line("deriv(v*x^2, x, t)")["unit"], "m")            # (m/s)·2x mit x in s
        self.assertEqual(line("sum(v*k, k, 1, 3)")["unit"], "m/s")

    def test_unknown_unit_shown(self):
        r = line("[v, t]")                                                   # gemischte Liste: Einheit unbestimmt
        self.assertEqual(r["unit"], "?")
        self.assertTrue(r.get("notes"))

    def test_coherent_unit_name(self):
        self.assertEqual(line("Rgas*298.15")["unit"], "J/(mol·K)")


class CardCheck(unittest.TestCase):
    def card(self, F, m, a):
        st = {"values": [], "cards": [{"id": "c", "eq": "dyn_newton", "vars": {"F": {"value": F, "unit": "N"},
                                       "m": {"value": m, "unit": "kg"}, "a": {"value": a, "unit": "m/s^2"}}}]}
        return S.eval_sheet(st)["cards"][0]

    def test_rounding_of(self):
        self.assertAlmostEqual(S.rounding_of("2.50"), 0.005 / 2.5)            # halbe letzte Stelle / Betrag
        self.assertAlmostEqual(S.rounding_of("1.5e3"), 50 / 1500)
        self.assertEqual(S.rounding_of("7"), 0.0)                             # ganze Zahl: exakt

    def test_tolerance_from_input_rounding(self):
        c = self.card("10", "2.0", "5.01")               # F − m·a = 10 − 10,02: 0,2 % Abweichung
        self.assertEqual(c["status"], "check")
        # Toleranz Σ|∂r/∂x|·|x|·δ/|r|: m: 5,01·2·0,025 = 0,2505; a: 2·5,01·(0,005/5,01) = 0,01; /10,02 → 0,026, Obergrenze 0,01
        self.assertAlmostEqual(c["check"]["tol"], S.CHECK_RTOL_MAX)
        self.assertTrue(c["check"]["ok"])
        c = self.card("10", "2", "6")                    # exakte ganze Zahlen: 20 % Abweichung, Toleranz 1e-9
        self.assertFalse(c["check"]["ok"])
        self.assertAlmostEqual(c["check"]["tol"], S.CHECK_RTOL_MIN)
        c = self.card("10", "2", "5")
        self.assertTrue(c["check"]["ok"])

    def test_tolerance_scales_with_digits(self):
        c = self.card("10.000", "2.0000", "5.0010")      # 0,02 % Abweichung, Eingaben auf 5 Stellen
        # δm = 0,00005/2 = 2,5e-5, δa = 0,00005/5,001 ≈ 1e-5, δF = 0,0005/10 = 5e-5 → Toleranz ≈ 8,5e-5 < 2e-4
        self.assertLess(c["check"]["tol"], 1e-4)
        self.assertFalse(c["check"]["ok"])


class TouchingRoots(unittest.TestCase):
    def test_double_root_found(self):
        # s = v0·t + a·t²/2 mit v0 = −4 m/s, a = 2 m/s², s = −4 m: t² − 4t + 4 = 0, doppelte Nullstelle t = 2 s
        st = {"values": [], "cards": [{"id": "x", "eq": "kin_s_t", "target": "t", "vars": {"s": {"value": "-4", "unit": "m"},
              "v0": {"value": "-4", "unit": "m/s"}, "a": {"value": "2", "unit": "m/s^2"}}}]}
        o = S.eval_sheet(st)["cards"][0]
        self.assertEqual(o["status"], "ok")
        self.assertAlmostEqual(o["result"]["si"], 2.0, places=6)

    def test_numeric_roots_direct(self):
        eq = L.BY_ID["kin_s_t"]
        roots = S.numeric_roots(eq, "t", {"s": -4.0, "v0": -4.0, "a": 2.0}, U.KINDS["time"])
        self.assertEqual(len(roots), 1)
        self.assertAlmostEqual(roots[0], 2.0, places=6)


class GraphRegression(unittest.TestCase):
    @unittest.skipIf(SST is None, "SciPy fehlt (nur Testabhängigkeit)")
    def test_line_uncertainty(self):
        x = np.array([0.0, 1, 2, 3, 4, 5])
        y = np.array([0.1, 2.2, 3.9, 6.1, 8.0, 9.8])
        rows = [{"id": "t", "kind": "table", "table": {"cols": [{"name": "x1", "values": [str(v) for v in x]},
                                                                {"name": "y1", "values": [str(v) for v in y]}]}},
                {"id": "r", "src": "y1 ~ m x1 + b"}]
        reg = G.compute({"rows": rows, "view": {"xmin": -1, "xmax": 6, "ymin": -1, "ymax": 11, "w": 800, "h": 500},
                         "ctx": {"angle": "rad"}})["rows"]["r"]
        n, sxx = x.size, float(np.sum((x - x.mean()) ** 2))
        m = float(np.sum((x - x.mean()) * (y - y.mean())) / sxx)
        b = float(y.mean() - m * x.mean())
        s = math.sqrt(float(np.sum((y - m * x - b) ** 2)) / (n - 2))
        self.assertAlmostEqual(reg["u"]["m"], s / math.sqrt(sxx), places=7)                 # Lehrbuchformel Gerade
        self.assertAlmostEqual(reg["u"]["b"], s * math.sqrt(1 / n + x.mean() ** 2 / sxx), places=7)
        t = float(SST.t.ppf(0.975, n - 2))                                                   # SciPy
        self.assertAlmostEqual(reg["t"], t, places=9)
        self.assertAlmostEqual(reg["ci"]["m"], t * reg["u"]["m"], places=9)
        self.assertTrue(reg["converged"])


class ReportDigits(unittest.TestCase):
    def test_value_with_uncertainty(self):
        # u auf 2 gültige Ziffern, Wert auf dieselbe Stelle (GUM-Praxis)
        self.assertEqual(B._pm_tex(9.81234, 0.0123, "", "en"), r"9.812 \pm 0.012")
        self.assertTrue(B._pm_tex(9.81234, 0.0123, "m/s^2", "en").startswith(r"(9.812 \pm 0.012)\,"))
        self.assertEqual(B._pm_tex(12345678.0, 2345.0, "", "en"), r"(1.23457 \pm 0.00023)\cdot 10^{7}")
        self.assertEqual(B._pm_tex(0.98235, 0.0213, "", "de"), r"0{,}982 \pm 0{,}021")

    def test_six_digits_without_uncertainty(self):
        self.assertEqual(B.VALUE_DIGITS, 6)
        self.assertIn("1.23457", B._pm_tex(1.234567, None, "", "en"))


class ModuleMeta(unittest.TestCase):
    def test_equation_count_in_description(self):
        meta = json.loads((HERE.parent / "module.json").read_text(encoding="utf-8"))
        n = len(L.EQUATIONS)
        self.assertIn(f"{n} Formeln", meta["description"])
        self.assertIn(f"{n} clickable", meta["description_en"])

    def test_version_matches(self):
        import rechner
        meta = json.loads((HERE.parent / "module.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["version"], rechner.__version__)

    def test_poh_states_25_degrees(self):
        self.assertIn("25 °C", L.BY_ID["ch_pOH"].de)
        self.assertIn("pKw", L.BY_ID["ch_pOH_pKw"].text)
        self.assertIn("nicht", L.BY_ID["hard_Rm"].note)                 # Faustformel, nicht gegen ISO 18265 geprüft


if __name__ == "__main__":
    unittest.main()
