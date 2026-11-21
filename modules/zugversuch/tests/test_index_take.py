"""Project index values in own equations: named variable with unit, u and origin; wrong units are refused."""
from __future__ import annotations

import base64
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "sdk" / "python"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from flps import bundle  # noqa: E402
from test_uncertainty import measure  # noqa: E402

EXT = [{"key": "Rref", "label": "Referenz", "value": 0.5, "unit": "GPa", "u": 0.01, "from_name": "Projektindex g-1 · rechner"},
       {"key": "Rok", "label": "Passend", "value": 500.0, "unit": "MPa", "u": 5.0, "from_name": "Projektindex g-2 · rechner"}]
DEFS = [{"sym": "mix", "expr": "Rm/Rref"}, {"sym": "after", "expr": "mix*2"},
        {"sym": "conv", "expr": 'Rm/convert(Rref, "GPa", "MPa")'}, {"sym": "ratio2", "expr": "Rm/Rok*100", "unit": "%"},
        {"sym": "tot", "expr": "Rok + A0"}, {"sym": "plain", "expr": "Rm + A0"},
        {"sym": "Rok_idx", "label": "Passend · Projektindex g-2 · rechner", "expr": "Rok", "unit": "MPa", "digits": 4}]


class TakenValues(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r, cls.raw, cls.name, cls.cfg = measure(equations=DEFS, ext_values=EXT)
        cls.by = {x["sym"]: x for x in cls.r.equations}

    def test_keeps_unit_u_origin(self):
        v = self.r.variables["Rok"]
        self.assertEqual((v["value"], v["unit"], v["u"]), (500.0, "MPa", 5.0))
        self.assertIn("Projektindex g-2", v["label"])
        self.assertAlmostEqual(self.by["Rok_idx"]["unc"]["u"], 5.0)

    def test_same_dimension_other_unit_is_refused(self):
        self.assertIsNone(self.by["mix"]["value"])
        self.assertIn("convert(Rref", self.by["mix"]["error"])
        self.assertIsNone(self.by["after"]["value"])                 # builds on the refused line
        self.assertNotIn("unc", self.by["mix"])

    def test_explicit_convert_and_same_unit_compute(self):
        Rm = self.r.variables["Rm"]["value"]
        self.assertAlmostEqual(self.by["conv"]["value"], Rm / 500.0)
        self.assertAlmostEqual(self.by["ratio2"]["value"], Rm / 500.0 * 100)
        self.assertGreater(self.by["ratio2"]["unc"]["u"], 0)

    def test_wrong_dimension_refused_others_untouched(self):
        self.assertIn("Summe", self.by["tot"]["error"])
        self.assertIsNone(self.by["plain"]["error"])                 # no index value: behaviour unchanged

    def test_reserved_name_does_not_mean_the_constant(self):
        ext = [{"key": "pi", "label": "x", "value": 3.0, "unit": "", "from_name": "Projektindex g-3"}]
        r, *_ = measure(equations=[{"sym": "y", "expr": "pi*2"}], ext_values=ext)
        self.assertIsNone(r.equations[0]["value"])
        self.assertIn("pi_ext", r.equations[0]["error"])

    def test_report_row(self):
        b = bundle.build([self.r], {self.name: self.raw}, {"items": [{"name": self.name, "config": self.cfg.to_dict()}]}, lang="de")
        t = base64.b64decode(b["files"]["gleichungen.tex"]).decode("utf-8")
        self.assertIn("Projektindex g-2", t)
        self.assertIn(r"\pm", t)
        t.encode("latin-1")

    def test_guard_is_the_same_file_in_all_modules(self):
        base = ROOT.parent
        me = (ROOT / "flps" / "taken.py").read_bytes()
        for p in ("ftir/ftir", "tga/tga", "mikroskopie/mikro"):
            f = base / p / "taken.py"
            if f.exists():
                self.assertEqual(f.read_bytes(), me, p)


if __name__ == "__main__":
    unittest.main()
