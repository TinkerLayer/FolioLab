"""DP-01: shared text-table sniffing and number parsing (labtable)."""
import math
import unittest

import labtable as LT


class NumberTest(unittest.TestCase):
    def test_formats(self):
        cases = {"12,5": 12.5, "12.5": 12.5, "1.234,5": 1234.5, "1 234,5": 1234.5, "1 234,5": 1234.5,
                 "1,234.5": 1234.5, "1,234,567": 1234567.0, "1.234.567": 1234567.0, "1'234.5": 1234.5,
                 "−3": -3.0, "+4": 4.0, "1,2E-3": 1.2e-3, "1.2e3": 1200.0, "1,2·10^-3": 1.2e-3,
                 "1.2×10⁻³": 1.2e-3, "2*10^5": 2e5, ".5": 0.5, "12,": 12.0, 7: 7.0, 2.5: 2.5}
        for s, v in cases.items():
            self.assertAlmostEqual(LT.number(s), v, msg=repr(s))

    def test_not_numbers(self):
        for s in ("", "abc", "<0,01", "n.d.", "12 mg", "#DIV/0!", "—", ".", "1-2", True, float("nan")):
            self.assertIsNone(LT.number(s), msg=repr(s))


class SniffTest(unittest.TestCase):
    def test_german_semicolon_with_units_row(self):
        text = "Probe: A1\nEinwaage: 12,3 mg\n\nZeit;Temperatur;Masse\nmin;°C;mg\n" + \
               "\n".join(f"{i};{25 + 10 * i},5;{12.3 - 0.01 * i:.3f}".replace(".", ",") for i in range(30))
        s = LT.sniff(text)
        lines = text.splitlines()
        self.assertEqual((s["sep"], s["dec_comma"], s["ncol"]), (";", True, 3))
        self.assertEqual(lines[s["header"]], "Zeit;Temperatur;Masse")
        self.assertEqual(lines[s["units"]], "min;°C;mg")
        self.assertEqual(s["end"] - s["start"], 30)

    def test_english_comma_tab_space(self):
        rows = "\n".join(f"{i},{i * 0.5:.2f},{i ** 2}" for i in range(20))
        s = LT.sniff("t (s),c (mol/L),n\n" + rows)
        self.assertEqual((s["sep"], s["dec_comma"], s["header"], s["units"]), (",", False, 0, None))
        s = LT.sniff("x\ty\n" + rows.replace(",", "\t"))
        self.assertEqual(s["sep"], "\t")
        s = LT.sniff("  1  2.5  3\n  2  3.5  4\n  3  4.5  5\n")
        self.assertEqual(s["sep"], " ")

    def test_header_row_t_T_m_is_not_units(self):
        self.assertFalse(LT.is_unit_row(["t", "T", "m"]))
        self.assertTrue(LT.is_unit_row(["[s]", "[°C]", "[mg]"]))
        self.assertTrue(LT.is_unit_row(["mol/L", "K", "s-1"]))

    def test_name_unit_and_norm(self):
        self.assertEqual(LT.name_unit("T (°C)"), ("T", "°C"))
        self.assertEqual(LT.name_unit("m [mg]"), ("m", "mg"))
        self.assertEqual(LT.name_unit("t / min"), ("t", "min"))
        self.assertEqual(LT.name_unit("Masse in mg"), ("Masse", "mg"))
        self.assertEqual(LT.norm_unit(" deg C"), "°c")
        self.assertEqual(LT.norm_unit("µV"), "uv")

    def test_decode(self):
        txt = "Zeit;Masse\n1;2,5\n"
        self.assertEqual(LT.decode(txt.encode("utf-16")), txt)
        self.assertEqual(LT.decode(txt.encode("utf-16-le")), txt)
        self.assertEqual(LT.decode("Größe".encode("cp1252")), "Größe")
        self.assertEqual(LT.decode("﻿Größe".encode("utf-8")), "Größe")

    def test_tofloat_thousands(self):
        self.assertEqual(LT.tofloat("1.234,5", True), 1234.5)
        self.assertTrue(math.isnan(LT.tofloat("x", False)))


if __name__ == "__main__":
    unittest.main()
