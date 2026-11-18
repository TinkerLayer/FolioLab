"""ER-701/702: ΔrG(T), K(T) mit Cp(T) und Gleichgewichtslage – gegen Literaturwerte geprüft.

Referenzen:
- NIST-JANAF Thermochemical Tables (Chase 1998), Tabelle H-083 NH3(g): log Kf bei 500/700/1000 K = −0,501/−2,029/−3,234
  für 1/2 N2 + 3/2 H2 -> NH3.
- Atkins, Physical Chemistry: N2O4(g) ⇌ 2 NO2(g) bei 298 K und 1 bar, Dissoziationsgrad α ≈ 0,19.
"""
import base64
import math
import unittest

from labcalc import chem as C
from labcalc import equilibrium as EQ
from labcalc import thermo as TH
from labcalc import thermo_t as TT

from elementrechner import analysis as AN
from elementrechner import bundle as B
from laboptional import skip_unless  # noqa: E402

JANAF_NH3 = {500.0: -0.501, 700.0: -2.029, 1000.0: -3.234}


def _nh3(T):
    eq = C.parse_equation("N2 + 3 H2 -> 2 NH3")
    return TT.reaction_T(eq, [1, 3, 2], T)


class CpModel(unittest.TestCase):
    @skip_unless('burcat')
    def test_nh3_log_kf_against_janaf(self):
        for T, ref in JANAF_NH3.items():
            r = _nh3(T)
            self.assertEqual(r["model"], "cp")
            self.assertAlmostEqual(r["lgK_T"] / 2, ref, delta=0.01, msg=f"T={T}")   # je mol NH3
            self.assertIn("burcat2018", r["refs"])
            self.assertIn("mcbride2002", r["refs"])

    def test_constant_approximation_differs(self):
        r = _nh3(1000.0)
        self.assertGreater(abs(r["const"]["lgK_T"] / 2 - JANAF_NH3[1000.0]), 0.1)

    def test_298_matches_table(self):
        eq = C.parse_equation("N2 + 3 H2 -> 2 NH3")
        r = TT.reaction_T(eq, [1, 3, 2], 298.15)
        base = TH.reaction(eq, [1, 3, 2], 298.15)
        self.assertAlmostEqual(r["dG_T"], base["dG"], delta=0.05)

    def test_t_eq(self):
        r = _nh3(500.0)
        self.assertIn("T_eq", r)
        self.assertTrue(400 < r["T_eq"] < 500, r["T_eq"])           # ΔrG = 0 bei rund 460 K
        f = TT.reaction_T(C.parse_equation("N2 + 3 H2 -> 2 NH3"), [1, 3, 2], r["T_eq"])
        self.assertAlmostEqual(f["dG_T"], 0.0, delta=0.01)

    @skip_unless('burcat')
    def test_out_of_range_warning(self):
        # Burcat-Polynom für H2O(l) gilt nur 273,15–600 K
        r = TT.reaction_T(C.parse_equation("2 H2 + O2 -> 2 H2O(l)"), [2, 1, 2], 800.0)
        self.assertTrue(r["outside"])
        self.assertTrue(any("Gültigkeitsbereich" in n for n in r["notes"]))

    def test_bad_temperature(self):
        with self.assertRaises(TH.ThermoError):
            _nh3(10.0)

    def test_vant_hoff(self):
        self.assertAlmostEqual(TT.vant_hoff(0.0, 300.0, 300.0, -50.0), 0.0)
        self.assertGreater(TT.vant_hoff(0.0, 300.0, 400.0, 50.0), 0.0)   # endotherm: K steigt mit T


class Equilibrium(unittest.TestCase):
    def test_n2o4_dissociation_atkins(self):
        eq = C.parse_equation("N2O4(g) -> 2 NO2(g)")
        r = TT.reaction_T(eq, [1, 2], 298.15)
        s = EQ.solve([{"name": "N2O4", "nu": -1, "phase": "g", "n0": 1},
                      {"name": "NO2", "nu": 2, "phase": "g", "n0": 0}], r["lnK_T"], 1.0)
        self.assertTrue(s["diagnostics"]["converged"])
        self.assertAlmostEqual(s["xi"], 0.19, delta=0.01)
        # Probe: α aus K direkt, K = 4α²/(1−α²)
        K = math.exp(r["lnK_T"])
        self.assertAlmostEqual(s["xi"], math.sqrt(K / (K + 4)), delta=1e-6)

    def test_ammonia_composition_satisfies_k(self):
        r = _nh3(723.15)
        last = 0.0
        for p in (1.0, 100.0, 300.0):
            s = EQ.solve([{"name": "N2", "nu": -1, "phase": "g", "n0": 1},
                          {"name": "H2", "nu": -3, "phase": "g", "n0": 3},
                          {"name": "NH3", "nu": 2, "phase": "g", "n0": 0}], r["lnK_T"], p)
            x = {row["name"]: row["x"] for row in s["rows"]}
            lnQ = 2 * math.log(x["NH3"]) - math.log(x["N2"]) - 3 * math.log(x["H2"]) - 2 * math.log(p)
            self.assertAlmostEqual(lnQ, r["lnK_T"], delta=1e-6)
            self.assertGreater(x["NH3"], last)                       # Le Chatelier: mehr NH3 bei höherem p
            last = x["NH3"]

    def test_direction(self):
        self.assertTrue(EQ.direction(-1.0, 0.0).startswith("Hinreaktion"))
        self.assertTrue(EQ.direction(1.0, 0.0).startswith("Rückreaktion"))
        self.assertEqual(EQ.direction(0.5, 0.5), "Gleichgewicht")

    def test_gas_complete_conversion(self):
        # sehr grosses K: Umsatz bis an den begrenzenden Stoff (O2)
        s = EQ.solve([{"name": "H2", "nu": -2, "phase": "g", "n0": 2},
                      {"name": "O2", "nu": -1, "phase": "g", "n0": 0.5},
                      {"name": "H2O", "nu": 2, "phase": "g", "n0": 0}], 200.0, 1.0)
        self.assertAlmostEqual(s["xi"], 0.5, delta=1e-6)

    def test_limit_reported(self):
        # Kalkzersetzung mit K > p: der Feststoff wird ganz verbraucht, das Gleichgewicht wird nicht erreicht
        s = EQ.solve([{"name": "CaCO3", "nu": -1, "phase": "cr", "n0": 1},
                      {"name": "CaO", "nu": 1, "phase": "cr", "n0": 0},
                      {"name": "CO2", "nu": 1, "phase": "g", "n0": 0}], 10.0, 1.0)
        self.assertAlmostEqual(s["xi"], 1.0, delta=1e-9)
        self.assertIn("vollständig", s["diagnostics"]["limit"])

    def test_no_reaction_possible(self):
        with self.assertRaises(EQ.EquilibriumError):
            EQ.solve([{"name": "A", "nu": -1, "phase": "g", "n0": 0},
                      {"name": "B", "nu": 1, "phase": "g", "n0": 0}], 0.0, 1.0)

    @skip_unless('burcat')
    def test_api(self):
        out = AN.equilibrium_call({"equation": "N2O4(g) -> 2 NO2(g)", "T": 298.15, "p": 1})
        self.assertTrue(out["diagnostics"]["converged"])
        self.assertAlmostEqual(out["xi"], 0.19, delta=0.01)
        self.assertIn("direction", out)
        self.assertEqual(out["model"], "cp")


class Report(unittest.TestCase):
    @skip_unless('burcat')
    def test_bundle_uses_cp_model(self):
        for lang, word in (("de", "NASA-7-Polynomen"), ("en", "NASA-7 polynomials")):
            d = B.build({"state": {"equation": "N2 + H2 -> NH3", "thermo": {"T": 700}}}, lang)
            tex = {k: base64.b64decode(v).decode("utf-8") for k, v in d["files"].items() if k.endswith(".tex")}
            body = tex["text-thermochemie.tex"]
            self.assertIn(word, body)
            self.assertIn(r"\lg K(T) = ", body)
            body.encode("latin-1")
            keys = {i["key"] for i in d["items"] if i["kind"] == "citation"}
            self.assertIn("er-burcat2018", keys)
            self.assertIn("er-mcbride2002", keys)
            self.assertIn("fig/dg-t.pdf", d["files"])
            self.assertIn("{dG-T}", tex["values.tex"])
            self.assertIn("{lgK-T}", tex["values.tex"])


if __name__ == "__main__":
    unittest.main()
