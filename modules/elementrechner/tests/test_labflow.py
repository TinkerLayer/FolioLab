"""Laborrechnungen im Rechner und im Bericht (ER-L09)."""
import base64
import unittest

from labcalc import expr as E

from elementrechner import analysis as A
from elementrechner import bundle as B
from laboptional import skip_unless  # noqa: E402

TOL = {"value": 0.867, "unit": "g/mL", "T_C": 20, "source": "Datenblatt Toluol"}
ETOH = {"value": 0.789, "unit": "g/mL", "T_C": 20, "source": "Datenblatt Ethanol"}
RX = {"equation": "CH3COOH + C2H5OH -> CH3COOC2H5 + H2O", "reference": {"i": 0, "value": 50, "unit": "mmol"},
      "reagents": {"1": {"equiv": 3, "density": ETOH}},
      "extras": [{"name": "Toluol", "role": "solvent", "value": 20, "unit": "mL", "density": TOL}],
      "conditions": {"T": "Rückfluss", "t": "3 h"}, "observed": {"masses": {"2": 3.5}}, "metrics": True}
PREP = [
    {"kind": "solid", "req": {"components": [{"substance": "CuSO4·5H2O", "basis": "Cu", "value": 0.1, "unit": "mol/L"}],
                              "V": 250, "V_unit": "mL"}},
    {"kind": "solid", "req": {"components": [{"substance": "NaCl", "value": 0.15, "unit": "mol/L"},
                                             {"substance": "KCl", "value": 5, "unit": "mmol/L"}], "V": 1000}},
    {"kind": "stock", "req": {"substance": "HCl", "stock": {"value": 37, "unit": "%(w/w)", "basis": "form",
                                                            "density": {"value": 1.18, "unit": "g/mL", "T_C": 20,
                                                                        "source": "Datenblatt"}},
                              "value": 1, "unit": "mol/L", "V": 1000}},
    {"kind": "series", "req": {"c0": 1, "unit": "mol/L", "factor": 10, "steps": 3, "V": 10}},
    {"kind": "mixsolve", "req": {"parts": [{"c": 1, "V": None}, {"c": 0, "V": 50}], "c_final": 0.1, "V_final": 100}},
    {"kind": "buffer", "req": {"pH": 7.4, "c": 0.1, "V": 1000, "acid": "NaH2PO4·H2O", "base": "Na2HPO4·2H2O"}},
    {"kind": "buffer", "req": {"pH": 8, "c": 0.05, "V": 500, "form": "Tris", "titrant": "HCl",
                               "stock": {"value": 1, "unit": "mol/L"}}},
    {"kind": "gas", "req": {"p": 101.325, "V": "", "n": 1, "T": 0, "formula": "N2", "mix": {"N2": 78.08, "O2": 20.95}}},
    {"kind": "reaction", "req": RX},
]


class CalculatorFunctions(unittest.TestCase):
    def setUp(self):
        E._register_chem()
        self.f = lambda n, *a: E.STRFUNCS[n][0](None, *a)   # noqa: E731

    @skip_unless('srd46')
    def test_si_in_si_out(self):
        # 0,1 mol/L = 100 mol/m³, 250 mL = 2,5e-4 m³ -> kg
        self.assertAlmostEqual(self.f("m_prep", "CuSO4·5H2O", 100, 2.5e-4), 6.242e-3, delta=2e-6)
        self.assertAlmostEqual(self.f("m_prep", "CuSO4·5H2O", 100, 2.5e-4, "Cu"), 6.242e-3, delta=2e-6)
        # 37 % HCl, 1,18 g/mL, 1 mol/L, 1 L -> 83,5 mL (M = 36,46 g/mol)
        v = self.f("V_reag", "HCl", 0.37, 1180, 1000, 1e-3)
        self.assertAlmostEqual(v * 1e6, 36.46 / 0.37 / 1.18, delta=0.05)
        a = self.f("m_buf", "NaH2PO4·H2O", "Na2HPO4·2H2O", 7.4, 100, 1e-3, 1)
        b = self.f("m_buf", "NaH2PO4·H2O", "Na2HPO4·2H2O", 7.4, 100, 1e-3, 2)
        self.assertAlmostEqual(a * 1000, 5.323, delta=0.002)
        self.assertAlmostEqual(b * 1000, 10.93, delta=0.01)
        self.assertAlmostEqual(self.f("rho_gas", "N2", 273.15, 101325), 1.2498, delta=0.001)
        self.assertAlmostEqual(self.f("AE", "CH3COOH + C2H5OH -> CH3COOC2H5 + H2O", "CH3COOC2H5"),
                               88.106 / (60.052 + 46.069), delta=1e-3)

    def test_refusals(self):
        from labcalc import chem as C
        with self.assertRaises(C.ChemError):
            self.f("V_reag", "HCl", 37, 1180, 1000, 1e-3)          # 37 statt 0,37
        with self.assertRaises(C.ChemError):
            self.f("AE", "CH4 + O2 -> CO2 + H2O", "CH4")           # kein Produkt
        with self.assertRaises(C.ChemError):
            self.f("m_buf", "NaH2PO4", "Na2HPO4", 7.4, 100, 1e-3, 3)

    def test_rechner_library(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "rechner"))
        from rechner import library as L
        eq = {e.id: e for e in L.EQUATIONS}
        for k, src in (("lab_E_factor", "sheldon2007"), ("lab_PMI", "jimenez2011"), ("lab_RME", "constable2002"),
                       ("lab_mix", "harris")):
            self.assertIn(k, eq)
            self.assertEqual(eq[k].source_key, src)


class ReportSections(unittest.TestCase):
    def _tex(self, d):
        return {k: base64.b64decode(v).decode("utf-8") for k, v in d["files"].items() if k.endswith(".tex")}

    @skip_unless('srd46')
    def test_run_matches_api(self):
        out = A.run({"prep": PREP})
        self.assertFalse(out["errors"], out["errors"])
        self.assertEqual([p["kind"] for p in out["prep"]], [p["kind"] for p in PREP])
        self.assertAlmostEqual(out["prep"][0]["result"]["mass_g"], 6.242, delta=0.002)
        self.assertEqual(out["prep"][0]["result"], A.prep_call("solid", PREP[0]["req"]))

    @skip_unless('srd46')
    def test_every_section(self):
        plans = [{"label": "Toluol 20 mL", "req": RX},
                 {"label": "ohne Lösungsmittel", "req": {**RX, "extras": []}}]
        for lang in ("de", "en"):
            d = B.build({"state": {"prep": PREP, "plans": plans}}, lang)
            ids = {i.get("id") for i in d["items"]}
            self.assertTrue({"ansetzen", "verduennungsreihe-4", "reaktionsansatz-9", "ansatzvergleich"} <= ids, ids)
            if lang == "de":
                self.assertTrue({"arbeitsblatt-1-1", "arbeitsblatt-2-1", "arbeitsblatt-2-2", "arbeitsblatt-3",
                                 "arbeitsblatt-6", "arbeitsblatt-7"} <= ids, ids)
            vals = {v["key"] for i in d["items"] if i.get("kind") == "values" for v in i["values"]}
            self.assertTrue({"e-faktor", "pmi", "rme"} <= vals, vals)
            tex = self._tex(d)
            for name, t in tex.items():
                self.assertFalse([c for c in t if ord(c) > 255], f"{lang} {name}: Zeichen ausserhalb Latin-1")
                for bad in ("\\ce{", "\\tfrac", "\\boldsymbol", "\\text{"):
                    self.assertNotIn(bad, t, f"{lang} {name}")
                self.assertEqual(t.count("$") % 2, 0, f"{lang} {name}: ungerade Zahl $")
                self.assertNotIn("$\\cdot$}", t, f"{lang} {name}: $ im Mathemodus")
            body = tex["text-ansetzen.tex"]
            self.assertIn("er-sheldon2007", body)
            self.assertIn("er-harris", body)
            self.assertIn("6{,}242" if lang == "de" else "6.242", body)
            self.assertIn(r"\mathrm{C_{4}H_{11}NO_{3}}", body)                       # Tris
            self.assertIn(r"$79{,}89$\,kPa" if lang == "de" else r"$79.89$\,kPa", body)
            if lang == "de":
                self.assertIn("0,038576", tex["arbeitsblatt-6.tex"])                 # Dezimalkomma im Rechenweg
            cmp_ = tex["ansatzvergleich.tex"]
            self.assertIn("Toluol 20 mL", cmp_)

    def test_bad_item_reported_not_fatal(self):
        out = A.run({"prep": [{"kind": "buffer", "req": {"pH": 13, "c": 0.05, "V": 500, "form": "Tris",
                                                          "titrant": "HCl"}}, PREP[0]]})
        self.assertEqual(len(out["prep"]), 1)
        self.assertEqual(out["errors"][0]["where"], "prep:buffer")


if __name__ == "__main__":
    unittest.main()
