"""ER-X02: Ionisierungsenergien aus der NIST ASD (gebündelt). Bezugswerte aus derselben Quelle (Export 17.11.2026)."""
import unittest

from labcalc import chem as C
from labcalc import ionization as IO
from laboptional import skip_unless  # noqa: E402


class Ionization(unittest.TestCase):
    @skip_unless('asd')
    def test_values(self):
        self.assertAlmostEqual(IO.ie(1, 1)["eV"], 13.598434599702, places=9)       # H, NIST ASD
        self.assertAlmostEqual(IO.ie(2, 2)["eV"], 54.4177655282, places=8)         # He II
        self.assertAlmostEqual(IO.ie(3, 1)["eV"], 5.391714996, places=8)           # Li
        self.assertEqual(len(IO.series(26)), 26)                                    # Fe: 26 Stufen
        self.assertAlmostEqual(IO.ie(1, 1)["kJmol"], 1312.05, delta=0.05)

    @skip_unless('asd')
    def test_trend_and_flags(self):
        na = IO.series(11)
        self.assertTrue(all(a["eV"] < b["eV"] for a, b in zip(na, na[1:])))
        self.assertGreater(na[1]["eV"] / na[0]["eV"], 9)                           # Sprung nach dem 3s-Elektron
        self.assertEqual(IO.ie(1, 1)["flag"], "theo")                             # ASD setzt den H-Wert in ( )

    @skip_unless('asd')
    def test_lookup_and_licence(self):
        self.assertEqual(IO.z_of("Na"), 11)
        with self.assertRaises(C.ChemError):
            IO.ie(11, 12)
        d = C._json("ionization.json")
        self.assertIn("Standard Reference Data", d["_licence"])
        self.assertEqual(d["_doi"], "10.18434/T4W30F")

    def test_radii(self):
        from labcalc import radii as RA
        self.assertAlmostEqual(RA.radius("Na", 1), 1.02)
        self.assertAlmostEqual(RA.radius("O", -2), 1.40)                            # Bezug der Skala
        fe = {r["ion"]: r for r in RA.for_element("Fe")}
        self.assertEqual(set(fe), {"Fe2+", "Fe3+"})
        self.assertAlmostEqual(fe["Fe3+"]["r_cryst"], 0.785)
        self.assertIn("prüfen", fe["Fe3+"]["check"])
        with self.assertRaises(C.ChemError):
            RA.radius("Na", 1, 8)

    @skip_unless('asd')
    def test_rechner_function(self):
        from labcalc import expr as E
        E._register_chem()
        # Rechner 1.4.0: IE() is an energy in J (shown with -> eV); IE_eV() keeps the plain number in eV
        r = E.STRFUNCS["IE"][0](None, "Na", 1)
        self.assertAlmostEqual(float(getattr(r, "value", r)) / 1.602176634e-19, IO.ie(11, 1)["eV"], places=9)
        r = E.STRFUNCS["IE_eV"][0](None, "Na", 1)
        self.assertAlmostEqual(float(getattr(r, "value", r)), IO.ie(11, 1)["eV"], places=9)


if __name__ == "__main__":
    unittest.main()
