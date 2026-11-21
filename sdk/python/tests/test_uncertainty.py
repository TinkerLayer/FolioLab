"""Messunsicherheit (labcalc.uncertainty): Eingangsgrössen, vier Verfahren, Messmittel, Bericht.

Bekannte Ergebnisse aus JCGM 101:2008 (GUM S1), Abschnitt 9.2 (additives Modell) und 9.3 (Massekalibrierung).
"""
import base64
import math
import sys
import unittest
from pathlib import Path

SDK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SDK))

from labbundle import Bundle  # noqa: E402
from labcalc import uncertainty as UN  # noqa: E402
from labcalc.sources import REFS  # noqa: E402


def additive(dist):
    """Y = X1 + X2 + X3 + X4, jede Grösse mit Standardunsicherheit 1 (S1 9.2)."""
    if dist == "normal":
        parts = [{"kind": "u", "u": 1}]
    else:
        parts = [{"kind": "limits", "a": math.sqrt(3), "dist": "rect"}]
    return [{"name": f"X{i}", "value": 0, "parts": parts} for i in range(1, 5)]


def mass_inputs():
    """S1 9.3: Kalibrierung eines Massestücks (mg, kg/m³)."""
    return [
        {"name": "mRc", "value": 100000.000, "parts": [{"kind": "u", "u": 0.050}]},
        {"name": "dmRc", "value": 1.234, "parts": [{"kind": "u", "u": 0.020}]},
        {"name": "rhoa", "value": 1.20, "parts": [{"kind": "limits", "a": 0.10, "dist": "rect"}]},
        {"name": "rhoW", "value": 8e3, "parts": [{"kind": "limits", "a": 1e3, "dist": "rect"}]},
        {"name": "rhoR", "value": 8.00e3, "parts": [{"kind": "limits", "a": 50, "dist": "rect"}]},
    ]


def mass_model(v):
    return (v["mRc"] + v["dmRc"]) * (1 + (v["rhoa"] - 1.2) * (1 / v["rhoW"] - 1 / v["rhoR"])) - 100000.0


class InputTest(unittest.TestCase):
    def test_kinds(self):
        x = UN.make_input({"name": "a", "value": 5, "parts": [{"kind": "limits", "a": 0.3, "dist": "rect"}]})
        self.assertAlmostEqual(x["u"], 0.3 / math.sqrt(3))
        x = UN.make_input({"name": "a", "value": 5, "parts": [{"kind": "limits", "a": 0.3, "dist": "tri"}]})
        self.assertAlmostEqual(x["u"], 0.3 / math.sqrt(6))
        x = UN.make_input({"name": "a", "value": 5, "parts": [{"kind": "U", "U": 0.4, "k": 2}]})
        self.assertAlmostEqual(x["u"], 0.2)
        x = UN.make_input({"name": "a", "value": 5, "parts": [{"kind": "resolution", "d": 0.01}]})
        self.assertAlmostEqual(x["u"], 0.005 / math.sqrt(3))
        x = UN.make_input({"name": "a", "value": 200, "parts": [{"kind": "rel", "pct": 1}]})
        self.assertAlmostEqual(x["u"], 2 / math.sqrt(3))
        x = UN.make_input({"name": "a", "value": 12.00, "parts": [{"kind": "spec", "pct": 0.5, "digits": 2, "d": 0.01}]})
        self.assertAlmostEqual(x["u"], (0.06 + 0.02) / math.sqrt(3))
        x = UN.make_input({"name": "a", "value": 5, "parts": [{"kind": "sd", "sd": 0.2, "n": 4}]})
        self.assertAlmostEqual(x["u"], 0.1)
        self.assertEqual(x["dof"], 3)

    def test_repeats_and_combination(self):
        x = UN.make_input({"name": "d", "value": None, "parts": [{"kind": "repeats", "values": [10.01, 10.03, 10.02, 10.02]},
                                                                  {"kind": "resolution", "d": 0.01}]})
        self.assertAlmostEqual(x["value"], 10.02)
        s = 0.008164965809277263
        uA, uB = s / 2, 0.005 / math.sqrt(3)
        self.assertAlmostEqual(x["u"], math.hypot(uA, uB))
        self.assertEqual(x["type"], "A+B")
        # Welch–Satterthwaite über die Beiträge: ν = u⁴ / (uA⁴/3)
        self.assertAlmostEqual(x["dof"], x["u"] ** 4 / (uA ** 4 / 3))

    def test_errors(self):
        with self.assertRaises(UN.UncError):
            UN.make_input({"name": "a", "value": 1, "parts": [{"kind": "repeats", "values": [1]}]})
        with self.assertRaises(UN.UncError):
            UN.make_input({"name": "a", "value": 1, "parts": [{"kind": "limits", "a": -1}]})
        with self.assertRaises(UN.UncError):
            UN.make_input({"name": "a", "value": "x", "parts": []})
        with self.assertRaises(UN.UncError):
            UN.evaluate("a+b", [{"name": "a", "value": 1}, {"name": "b", "value": 1}], corr=[{"a": "a", "b": "b", "r": 2}])

    def test_instruments(self):
        p = UN.instrument_parts("pt100-a", 100.0, "°C")
        self.assertAlmostEqual(p[0]["a"], 0.35)
        p = UN.instrument_parts("pt100-a", 373.15, "K")              # Einheit wird umgerechnet
        self.assertAlmostEqual(p[0]["a"], 0.35)
        p = UN.instrument_parts("thermoelement-k1", 800.0, "°C")
        self.assertAlmostEqual(p[0]["a"], 3.2)
        p = UN.instrument_parts("vollpipette-a-10", 10.0, "mL")
        self.assertAlmostEqual(p[0]["u"], 0.02 / math.sqrt(6))
        p = UN.instrument_parts("messkolben-a-100", 0.1, "L")         # Grenze in der Einheit der Grösse
        self.assertAlmostEqual(p[0]["a"], 0.0001)
        p = UN.instrument_parts("extenso-iso9513-1", 0.1, "mm")
        self.assertAlmostEqual(p[0]["a"], 0.003)
        p = UN.instrument_parts("messschieber-001", 10, "mm", {"mpe": 0.03})
        self.assertAlmostEqual(p[0]["a"], 0.03)
        with self.assertRaises(UN.UncError):
            UN.instrument_parts("pt100-a", 1.0, "mm")
        for it in UN.instruments():                                  # jede Klasse hat eine Quelle
            self.assertIn(it["source"], REFS, it["id"])
            for prt in UN.instrument_parts(it["id"], 10.0, it["unit"]):
                self.assertGreater(prt["u"], 0, it["id"])

    def test_own_instrument(self):
        it = UN.check_own_instrument({"name": "Mein Messschieber", "unit": "mm", "parts": [{"a": "0.01 + x/1000"}],
                                      "source": {"type": "misc", "title": "Kalibrierschein 42"}})
        it["id"] = "own-1"
        UN.set_own_instruments([it])
        try:
            self.assertAlmostEqual(UN.instrument_parts("own-1", 20, "mm")[0]["a"], 0.03)
        finally:
            UN.set_own_instruments([])
        with self.assertRaises(UN.UncError):
            UN.check_own_instrument({"name": "x", "parts": [{"a": "__import__('os')"}]})


class MethodTest(unittest.TestCase):
    def test_additive_normal(self):
        r = UN.evaluate(lambda v: v["X1"] + v["X2"] + v["X3"] + v["X4"], additive("normal"), "gum")
        self.assertAlmostEqual(r["u"], 2.0, places=6)
        self.assertAlmostEqual(r["U"], 3.92, places=2)
        m = UN.evaluate(lambda v: v["X1"] + v["X2"] + v["X3"] + v["X4"], additive("normal"), "mc")
        self.assertAlmostEqual(m["u"], 2.0, delta=0.02)
        self.assertAlmostEqual(m["lo"], -3.92, delta=0.05)
        self.assertAlmostEqual(m["hi"], 3.92, delta=0.05)
        self.assertTrue(m["stable"])

    def test_additive_rect(self):
        """S1 9.2.3: Rechteckverteilungen, MC-Intervall ±3,88 statt ±3,92."""
        m = UN.evaluate(lambda v: v["X1"] + v["X2"] + v["X3"] + v["X4"], additive("rect"), "mc")
        self.assertAlmostEqual(m["hi"], 3.88, delta=0.04)
        self.assertAlmostEqual(m["lo"], -3.88, delta=0.04)

    def test_mass_calibration(self):
        """S1 9.3: GUM u = 0,0539 mg, Monte Carlo u = 0,0750 mg, Intervall [1,0870; 1,3828] mg."""
        g = UN.evaluate(mass_model, mass_inputs(), "gum")
        self.assertAlmostEqual(g["value"], 1.2340, places=4)
        self.assertAlmostEqual(g["u"], 0.0539, delta=0.0002)
        m = UN.evaluate(mass_model, mass_inputs(), "mc")
        self.assertAlmostEqual(m["u"], 0.0750, delta=0.0015)
        self.assertAlmostEqual(m["lo"], 1.0870, delta=0.004)
        self.assertAlmostEqual(m["hi"], 1.3828, delta=0.004)
        # fester Startwert: gleiche Zahlen bei gleicher Eingabe
        self.assertEqual(m["u"], UN.evaluate(mass_model, mass_inputs(), "mc")["u"])

    def test_expr_model_and_budget(self):
        ins = [{"name": "F", "value": 10000, "unit": "N", "parts": [{"kind": "rel", "pct": 1}]},
               {"name": "d", "value": 10, "unit": "mm", "parts": [{"kind": "limits", "a": 0.02}]}]
        r = UN.evaluate({"expr": "F/(pi*d^2/4)"}, ins, "gum", unit="MPa", label="Rm", name="Rm")
        y = 10000 / (math.pi * 25)
        self.assertAlmostEqual(r["value"], y)
        ur = math.hypot(0.01 / math.sqrt(3), 2 * 0.002 / math.sqrt(3))
        self.assertAlmostEqual(r["u"] / y, ur, places=6)
        shares = {b["name"]: b["share"] for b in r["budget"]}
        self.assertAlmostEqual(sum(shares.values()), 100, places=6)
        self.assertGreater(shares["F"], shares["d"])
        self.assertIn("MPa", r["text"])
        self.assertIn("k = 1,96", r["text"])

    def test_welch_satterthwaite(self):
        ins = [{"name": "a", "value": 1, "parts": [{"kind": "u", "u": 1, "dof": 4}]},
               {"name": "b", "value": 1, "parts": [{"kind": "u", "u": 1}]}]
        r = UN.evaluate("a+b", ins, "gum")
        self.assertAlmostEqual(r["dof"], 16)
        self.assertAlmostEqual(r["k"], 2.120, places=3)
        r = UN.evaluate("a+b", ins, "gum", k=2)
        self.assertEqual(r["k"], 2)

    def test_correlation(self):
        ins = [{"name": "a", "value": 1, "parts": [{"kind": "u", "u": 1}]},
               {"name": "b", "value": 1, "parts": [{"kind": "u", "u": 1}]}]
        r = UN.evaluate("a-b", ins, "gum", corr=[{"a": "a", "b": "b", "r": 1}])
        self.assertAlmostEqual(r["u"], 0, places=6)
        r = UN.evaluate("a+b", ins, "gum", corr={"a|b": 0.5})
        self.assertAlmostEqual(r["u"], math.sqrt(3))
        m = UN.evaluate("a+b", ins, "mc", corr={"a|b": 0.5})
        self.assertAlmostEqual(m["u"], math.sqrt(3), delta=0.03)

    def test_gauss_and_worst(self):
        ins = [{"name": "a", "value": 2, "parts": [{"kind": "limits", "a": 0.1}]},
               {"name": "b", "value": 3, "parts": [{"kind": "limits", "a": 0.2}]}]
        g = UN.evaluate("a*b", ins, "gauss")
        self.assertAlmostEqual(g["u"], math.hypot(3 * 0.1, 2 * 0.2) / math.sqrt(3))
        self.assertEqual(g["k"], 1)
        w = UN.evaluate("a*b", ins, "worst")
        self.assertAlmostEqual(w["lo"], 1.9 * 2.8)
        self.assertAlmostEqual(w["hi"], 2.1 * 3.2)
        self.assertAlmostEqual(w["linear"], 3 * 0.1 + 2 * 0.2)
        # nicht monoton: Extremwert im Inneren
        w = UN.evaluate("(a-2)^2", [{"name": "a", "value": 2.05, "parts": [{"kind": "limits", "a": 0.1}]}], "worst")
        self.assertAlmostEqual(w["lo"], 0, places=4)
        self.assertIn("interior", w["notes"])

    def test_nonlinear_note_and_compare(self):
        ins = [{"name": "x", "value": 0.1, "parts": [{"kind": "u", "u": 0.1}]}]
        r = UN.evaluate("x^2", ins, "gum")
        self.assertTrue(any("nichtlinear" in t for t in r["note_texts"]))
        c = UN.compare("x^2", ins)
        self.assertEqual(set(c), set(UN.METHODS))
        self.assertGreater(c["mc"]["u"], c["gum"]["u"])

    def test_scalar_only_model(self):
        def f(v):                                   # nicht vektorisierbar
            return float(v["a"]) * 2
        r = UN.evaluate(f, [{"name": "a", "value": 1, "parts": [{"kind": "u", "u": 0.1}]}], "mc")
        self.assertFalse(r["vectorised"])            # Einzelauswertungen, adaptiv bis stabil (oder Zeitbudget)
        self.assertTrue(r["stable"] or "mc_loop" in r["notes"])
        self.assertAlmostEqual(r["u"], 0.2, delta=0.02)
        old = UN.MC_LOOP_SECONDS
        try:                                         # Zeitbudget erschöpft: Abbruch mit Hinweis
            UN.MC_LOOP_SECONDS = 0.0
            r = UN.evaluate(lambda v: float(v["a"]) * 2 + 1e-9 * float(v["a"]) ** 3,
                            [{"name": "a", "value": 1, "parts": [{"kind": "u", "u": 0.1}]}], "mc")
            self.assertIn("mc_loop", r["notes"])
        finally:
            UN.MC_LOOP_SECONDS = old

    def test_zero_uncertainty_rounding(self):
        self.assertEqual(UN.round_pm(716.75, 0.0)[:2], ("716.75", "0"))

    def test_rounding(self):
        self.assertEqual(UN.round_pm(12.3456, 0.0234)[:2], ("12.346", "0.023"))
        self.assertEqual(UN.round_pm(1234.5, 56)[:2], ("1234", "56"))
        self.assertEqual(UN.round_pm(98765, 1234)[:2], ("98800", "1200"))

    def test_gum_rows(self):
        import numpy as np
        r = UN.gum_rows("a*b", {"a": np.array([1.0, 2.0, 3.0]), "b": 4.0}, {"a": np.array([0.1, 0.0, 0.2]), "b": 0.5})
        np.testing.assert_allclose(r["value"], [4, 8, 12])
        np.testing.assert_allclose(r["u"], [math.hypot(0.4, 0.5), 1.0, math.hypot(0.8, 1.5)])

    def test_exact_inputs(self):
        r = UN.evaluate("a*b", [{"name": "a", "value": 2}, {"name": "b", "value": 3, "parts": [{"kind": "u", "u": 0.1}]}])
        self.assertTrue(r["budget"][0]["exact"])
        self.assertAlmostEqual(r["u"], 0.2)


class FormulaUncTest(unittest.TestCase):
    def test_chain_keeps_correlation(self):
        from labcalc import formulas as F
        defs = [{"sym": "p", "expr": "a*b"}, {"sym": "q", "expr": "p/a"}, {"sym": "c", "expr": "2*k"}]
        res = F.evaluate(defs, {"a": {"value": 2, "u": 0.1}, "b": {"value": 3, "u": 0.2, "unit": "mm"}, "k": 4})
        by = {r["sym"]: r for r in res}
        self.assertAlmostEqual(by["p"]["unc"]["u"], math.hypot(3 * 0.1, 2 * 0.2))
        self.assertAlmostEqual(by["q"]["unc"]["u"], 0.2, places=6)       # q = b: a kürzt sich heraus
        self.assertNotIn("unc", by["c"])                                    # nur exakte Grössen
        self.assertIn("±", by["p"]["text_pm"])
        res = F.evaluate(defs, {"a": {"value": 2, "u": 0.1}, "b": 3}, unc={"method": "worst"})
        self.assertEqual(res[0]["unc"]["method"], "worst")
        self.assertNotIn("unc", F.evaluate(defs, {"a": {"value": 2, "u": 0.1}, "b": 3}, unc={"method": "off"})[0])

    def test_ext_values_carry_u(self):
        from labcalc import formulas as F
        v = F.merge_ext({}, [{"key": "Rm", "value": 400, "unit": "MPa", "u": 4.5, "from_name": "Probe 1"}])
        self.assertEqual(v["Rm"]["u"], 4.5)
        res = F.evaluate([{"sym": "h", "expr": "Rm/2"}], v)
        self.assertAlmostEqual(res[0]["unc"]["u"], 2.25)

    def test_report_with_unc(self):
        from labcalc import formulas as F
        b = Bundle(module="t", module_name="T", title="t")
        res = F.evaluate([{"sym": "p", "expr": "a*b", "unit": "N"}], {"a": {"value": 2, "u": 0.1}, "b": 3})
        out = F.to_report(b, res, "de")
        self.assertIn("eq-p-pm", out["values"])
        self.assertIn("eq-p-budget", out["tables"])
        self.assertIn(r"\pm", base64.b64decode(b.to_dict()["files"]["gleichungen.tex"]).decode("utf-8"))


class RouteTest(unittest.TestCase):
    def test_route(self):
        import os
        import tempfile

        import labproject as LP
        import labunc
        with tempfile.TemporaryDirectory() as td:
            os.environ["FOLIO_SUITE_DIR"] = td
            try:
                me = LP.ModuleEnvs("ignored", "werkstoffe")
                L = labunc.route(me, "instruments", {})
                self.assertTrue(any(i["id"] == "pt100-a" and i["ref"]["title"].startswith("IEC 60751") for i in L["items"]))
                it = labunc.route(me, "own_save", {"item": {"name": "Schieblehre 3", "unit": "mm", "parts": [{"a": "0.03"}]}})
                self.assertTrue(Path(td, "messmittel.json").exists())       # eine Datei für die ganze Suite
                me2 = LP.ModuleEnvs("ignored", "tga")                       # anderes Modul sieht dasselbe Messmittel
                self.assertTrue(any(i["id"] == it["id"] for i in labunc.route(me2, "instruments", {})["items"]))
                pv = labunc.route(me2, "preview", {"value": 12, "unit": "mm", "parts": [{"kind": "instrument", "id": it["id"]}]})
                self.assertAlmostEqual(pv["u"], 0.03 / math.sqrt(3))
                ev = labunc.route(me, "evaluate", {"expr": "a*2", "inputs": [{"name": "a", "value": 1, "parts": [{"kind": "u", "u": 0.1}]}],
                                                   "method": "all"})
                self.assertEqual(set(ev), set(UN.METHODS))
                with self.assertRaises(LP.EnvError):
                    labunc.route(me, "own_save", {"item": {"name": "x", "parts": [{"a": "1/0*"}]}})
                self.assertTrue(labunc.route(me, "own_delete", {"id": it["id"]})["ok"])
            finally:
                os.environ.pop("FOLIO_SUITE_DIR", None)
                UN.set_own_instruments([])


class ReportTest(unittest.TestCase):
    def test_bundle(self):
        b = Bundle(module="t", module_name="T", title="t")
        ins = [{"name": "F", "value": 10000, "unit": "N", "parts": [{"kind": "instrument", "id": "kraft-iso7500-1"}]},
               {"name": "d", "value": 10, "unit": "mm", "parts": [{"kind": "limits", "a": 0.02}]}]
        res = [UN.evaluate({"expr": "F/(pi*d^2/4)"}, ins, m, unit="MPa", label="Zugfestigkeit", name="Rm")
               for m in ("gum", "mc")]
        res[1]["name"] = "Rm-mc"
        out = UN.to_report(b, res, "de")
        self.assertIn("Rm-pm", out["values"])
        self.assertIn("Rm-budget", out["tables"])
        self.assertIn("GUM", out["latex"])
        d = b.to_dict()
        bib = base64.b64decode(d["files"]["refs.bib"]).decode("utf-8")
        self.assertIn("JCGM 100:2008", bib)
        self.assertIn("ISO 7500-1", bib)                 # Quelle des Messmittels zitiert
        self.assertIn("Rm-budget.tex", " ".join(d["files"]))


if __name__ == "__main__":
    unittest.main()
