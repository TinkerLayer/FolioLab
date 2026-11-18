"""U-01: Messgrössen aus Labor, Wasser- und Umweltanalytik (pH, Leitfähigkeit, Feuchte, Trübung …)."""
import itertools
import unittest

import numpy as np

import labdataset as DS
from labcalc import expr as E
from labcalc import units as U


class UnitsU01Test(unittest.TestCase):
    def test_ph_is_a_scale(self):
        f, d, off = U.parse_unit("pH")
        self.assertEqual((f, U.dims_text(d), off), (1, "", 0.0))           # nicht mehr Pikohenry
        self.assertEqual(U.kind_for_unit("pH"), "ph")
        self.assertFalse(U.compatible("pH", "%"))
        self.assertFalse(U.compatible("pH", ""))
        self.assertTrue(U.compatible("pH", "pH"))
        with self.assertRaises(E.CalcError):
            E.evaluate(E.parse('convert(7, "pH", "%")'), E.Ctx(names={}))
        self.assertEqual(U.auto_unit("ph", 7.0), "pH")

    def test_conversions(self):
        cases = [("1 mS/cm", "µS/cm", 1000), ("1 S/m", "mS/cm", 10), ("1 °dH", "mmol/L", 10 / 56.077),        # 10 mg CaO/L, M(CaO) = 40.078 + 15.999 g/mol (IUPAC Standardatomgewichte)
                 ("1 °fH", "mmol/L", 10 / 100.086),                                         # 10 mg CaCO3/L, M(CaCO3) = 100.086 g/mol
                 ("1 cP", "mPa*s", 1), ("1 cSt", "mm^2/s", 1), ("760 Torr", "atm", 1), ("1 mTorr", "Pa", 0.133322),
                 ("45 %RH", "%", 45), ("1 sccm", "mL/min", 1), ("1 slm", "L/min", 1), ("1000 ppb", "ppm", 1),
                 ("1 klx", "lx", 1000), ("1 mSv/h", "µSv/h", 1000), ("1 µkat", "nkat", 1000), ("1 CFU/mL", "1/L", 1000),
                 ("5 mAU", "AU", 0.005), ("2 Bq/L", "Bq/m^3", 2000)]
        for src, to, want in cases:
            with self.subTest(src=src):
                v, u = src.split(" ", 1)
                self.assertTrue(U.compatible(u, to))
                self.assertAlmostEqual(U.from_si(U.to_si(float(v), u), to) / want, 1, places=5)

    def test_kinds_for_new_units(self):
        for unit, kind in [("µS/cm", "el_conductivity"), ("mV", "voltage"), ("%RH", "rel_humidity"), ("NTU", "turbidity"),
                           ("FNU", "turbidity"), ("mAU", "absorbance"), ("dB", "sound_level"), ("lx", "illuminance"),
                           ("°dH", "hardness"), ("CFU/mL", "number_conc"), ("µSv/h", "dose_rate"), ("mSv", "equiv_dose"), ("mGy", "dose"),
                           ("ppm", "fraction"), ("g/kg", "fraction"), ("%", "number"), ("", "number"), ("mg/L", "mass_conc"),
                           ("Bq/L", "activity_conc"), ("sccm", "vol_flow"), ("cP", "dyn_visc")]:
            with self.subTest(unit=unit):
                self.assertEqual(U.kind_for_unit(unit), kind)
        self.assertIn("redox", [k.key for k in U.kinds_for_unit("mV")])
        self.assertIn("dissolved_o2", [k.key for k in U.kinds_for_unit("mg/L")])
        self.assertNotIn("ph", [k.key for k in U.kinds_for_unit("%")])           # % ist kein pH
        self.assertNotIn("turbidity", [k.key for k in U.kinds_for_unit("1")])

    def test_every_kind_converts_within_itself(self):
        for k in U.KINDS.values():
            if k.key.startswith("dim:"):
                continue
            for a, b in itertools.combinations(k.units, 2):
                if U.scale_of(a) and U.scale_of(b) and U.scale_of(a) != U.scale_of(b):
                    continue                    # Trübung: NTU, FNU, FAU sind verschiedene Verfahren, keine Umrechnung
                with self.subTest(kind=k.key, a=a, b=b):
                    self.assertTrue(U.compatible(a, b))

    def test_dataset_ph_column(self):
        head, data = DS.check({"title": "pH-Verlauf", "columns": [
            {"key": "t", "name": "Zeit", "dtype": "number", "unit": "h"},
            {"key": "ph", "name": "pH", "dtype": "number", "unit": "pH"},
            {"key": "k", "name": "Leitfähigkeit", "dtype": "number", "unit": "mS/cm"}]},
            {"t": [0, 1, 2], "ph": [7.1, 6.9, 6.4], "k": [1.2, 1.3, 1.5]})
        kinds = {c["key"]: c["kind"] for c in head["columns"]}
        self.assertEqual((kinds["ph"], kinds["k"]), ("ph", "el_conductivity"))
        ds = DS.Dataset(head, data, checked=True)
        self.assertTrue(np.allclose(ds.in_unit("k", "µS/cm"), [1200, 1300, 1500]))
        with self.assertRaises(DS.DatasetError):
            ds.in_unit("ph", "%")


if __name__ == "__main__":
    unittest.main()
