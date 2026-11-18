"""ER-S01: Aktivitätskoeffizienten (Davies, erweiterte Debye–Hückel) und korrigierter pH.

Referenzwerte γ: Kielland (1937), Tabelle der Einzelionen-Aktivitätskoeffizienten bei 25 °C (auch bei Harris,
Quantitative Chemical Analysis), Ionengrösse a in pm.
"""
import base64
import unittest

from labcalc import acidbase as AB
from labcalc import activity as A

from elementrechner import bundle as B

# (z, a in pm): γ bei I = 0,001 / 0,01 / 0,1 mol/L
KIELLAND = {(1, 900): (0.967, 0.914, 0.83), (1, 450): (0.964, 0.902, 0.775), (1, 300): (0.964, 0.899, 0.755),
            (2, 600): (0.870, 0.675, 0.405), (2, 800): (0.872, 0.69, 0.45), (3, 900): (0.738, 0.445, 0.18)}


class Gamma(unittest.TestCase):
    def test_constants_25(self):
        Aa, Bb = A.dh_constants(25)
        self.assertAlmostEqual(Aa, 0.511, delta=0.002)
        self.assertAlmostEqual(Bb, 0.329, delta=0.002)
        self.assertGreater(A.dh_constants(80)[0], Aa)               # A steigt mit T

    def test_kielland_table(self):
        for (z, a), ref in KIELLAND.items():
            for I, g in zip((0.001, 0.01, 0.1), ref):
                self.assertAlmostEqual(A.gamma(z, I, "edh", a), g, delta=0.01, msg=f"z={z} a={a} I={I}")

    def test_davies(self):
        self.assertAlmostEqual(A.gamma(1, 0.1, "davies"), 0.78, delta=0.01)
        self.assertEqual(A.gamma(0, 0.1, "davies"), 1.0)
        with self.assertRaises(A.ActivityError):
            A.gamma(1, 0.1, "pitzer")


class CorrectedPH(unittest.TestCase):
    def test_hcl(self):
        r = A.ph_corrected("0,01 M HCl", 25, "edh")
        self.assertAlmostEqual(r["pH_ideal"], 2.00, places=2)
        self.assertAlmostEqual(r["pH"], 2.04, delta=0.01)             # Harris: a(H⁺) = 0,914·0,01

    def test_acetate_buffer_at_I_01(self):
        r = A.ph_corrected("0,1 M CH3COOH; 0,1 M CH3COONa", 25, "davies")
        self.assertAlmostEqual(r["I"], 0.1, delta=0.002)
        self.assertLess(r["pH"], r["pH_ideal"])
        self.assertAlmostEqual(r["dpH"], -0.11, delta=0.02)          # lg γ(A⁻) bei I = 0,1
        self.assertEqual(r["model"], "davies")

    def test_limit_note(self):
        r = A.ph_corrected("1 M NaCl; 0,001 M HCl", 25, "edh")
        self.assertTrue(any("Gültigkeitsbereich" in n for n in r["notes"]))

    def test_buffer(self):
        b = AB.buffer("Essigsäure", 4.76, 0.2)
        c = A.buffer_corrected(b, "davies")
        self.assertGreater(c["ratio_base_acid"], b["ratio_base_acid"])
        self.assertAlmostEqual(c["acid_form_c"] + c["base_form_c"], 0.2)

    def test_report(self):
        d = B.build({"state": {"ph": {"mixture": "0,1 M CH3COOH; 0,1 M CH3COONa", "activity": "davies"}}}, "de")
        tex = {k: base64.b64decode(v).decode("utf-8") for k, v in d["files"].items() if k.endswith(".tex")}
        t = tex["text-ph.tex"]
        t.encode("latin-1")
        self.assertIn("Davies-Gleichung", t)
        self.assertIn("{pH-akt}", tex["values.tex"].replace("pH-akt", "pH-akt"))
        keys = {i["key"] for i in d["items"] if i["kind"] == "citation"}
        self.assertIn("er-davies1962", keys)


if __name__ == "__main__":
    unittest.main()
