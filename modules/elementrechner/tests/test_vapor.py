"""ER-X03: Antoine-Dampfdruck und kolligative Konstanten.

Vergleichswerte: Wasser 25 °C 3,1699 kPa, 60 °C 19,946 kPa (IAPWS-95/Wagner–Pruss, CRC), Ethanol 25 °C 7,87 kPa
(CRC Handbook), Normalsiedepunkte Wasser 373,12 K, Ethanol 351,44 K.
"""
import unittest

from labcalc import chem as C
from labcalc import vapor as VP
from elementrechner import analysis as AN
from elementrechner import bundle as BU


class Antoine(unittest.TestCase):
    def test_water(self):
        self.assertAlmostEqual(VP.vapour_pressure("Wasser", 298.15)["p_kPa"], 3.1699, delta=0.01)
        self.assertAlmostEqual(VP.vapour_pressure("water", 333.15)["p_kPa"], 19.946, delta=0.05)
        self.assertAlmostEqual(VP.boiling_point("Wasser")["T"], 373.12, delta=0.2)
        self.assertFalse(VP.vapour_pressure("H2O", 298.15)["out_of_range"])

    def test_ethanol(self):
        self.assertAlmostEqual(VP.vapour_pressure("Ethanol", 298.15)["p_kPa"], 7.87, delta=0.05)
        self.assertAlmostEqual(VP.boiling_point("ethanol", 1.01325)["T"], 351.44, delta=0.3)

    def test_out_of_range(self):
        r = VP.vapour_pressure("Ethanol", 250.0)
        self.assertTrue(r["out_of_range"])
        self.assertIn("ausserhalb", r["notes"][0])
        with self.assertRaises(C.ChemError):
            VP.vapour_pressure("Quecksilber", 300)

    def test_colligative(self):
        r = VP.colligative("Wasser", 0.1, 2)
        self.assertAlmostEqual(r["dTf"], 0.372, places=6)
        self.assertAlmostEqual(r["dTb"], 0.102, places=6)
        self.assertNotIn("dTb", VP.colligative("Campher", 0.05))
        with self.assertRaises(C.ChemError):
            VP.constant("Campher", "b")

    def test_rechner(self):
        from labcalc import expr as E
        E._register_chem()
        self.assertAlmostEqual(E.STRFUNCS["pvap"][0](None, "Wasser", 298.15), 3169.9, delta=10)
        self.assertEqual(E.STRFUNCS["Kf"][0](None, "Benzol"), 5.12)

    def test_api_and_report(self):
        r = AN.vapor_call({"solvent": "Wasser", "T_C": "25", "p_bar": "1,01325", "b": "0,1", "i": "2"})
        self.assertEqual(set(r) >= {"pvap", "bp", "collig"}, True)
        self.assertIn("nistwebbook", r["refs"])
        with self.assertRaises(ValueError):
            AN.vapor_call({"solvent": "Wasser"})
        res = AN.run({"vapor": {"solvent": "Wasser", "T_C": "25", "b": "0,1"}})
        self.assertIn("vapor", res)
        import base64
        for lang in ("de", "en"):
            d = BU.build({"state": {"vapor": {"solvent": "Wasser", "T_C": "25", "p_bar": "1,01325", "b": "0,1", "i": "2"}}}, lang)
            t = base64.b64decode(d["files"]["text-dampfdruck.tex"]).decode("utf-8")
            t.encode("latin-1")
            self.assertIn("Antoine", t)
            self.assertIn("3{,}167" if lang == "de" else "3.167", t)
            self.assertIn("Bridgeman \\& Aldrich", t)
            keys = {i["key"] for i in d["items"] if i["kind"] == "citation"}
            self.assertTrue({"er-nistwebbook", "er-atkins"} <= keys, keys)


if __name__ == "__main__":
    unittest.main()
