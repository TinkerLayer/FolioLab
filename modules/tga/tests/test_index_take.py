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

import matplotlib  # noqa: E402

matplotlib.use("Agg")

from tga import bundle as B  # noqa: E402
from tga import synth as SY  # noqa: E402
from tga.analysis import run as analyse  # noqa: E402
from test_uncert import oxalate  # noqa: E402

EXT = [{"key": "Ltheo", "label": "Theorie", "value": 12.33, "unit": "%", "u": 0.02, "from_name": "Projektindex g-1 · elementrechner"},
       {"key": "Tref", "label": "Referenz", "value": 473.15, "unit": "K", "u": 1.0, "from_name": "Projektindex g-2 · rechner"},
       {"key": "Tok", "label": "Passend", "value": 200.0, "unit": "°C", "u": 1.0, "from_name": "Projektindex g-3 · rechner"}]


class TakenValues(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = oxalate()
        v = analyse(cls.raw, {}).variables
        cls.tname = next(k for k, x in v.items() if x.get("unit") == "°C")     # a characteristic temperature of this run
        cls.defs = [{"sym": "rel", "expr": "L1/Ltheo*100", "unit": "%"}, {"sym": "mixT", "expr": f"{cls.tname} - Tref"},
                    {"sym": "okT", "expr": f"{cls.tname} - Tok", "unit": "°C"}, {"sym": "bad", "expr": "Tok + Ltheo"},
                    {"sym": "Ltheo_idx", "label": "Theorie · Projektindex g-1", "expr": "Ltheo", "unit": "%", "digits": 4}]
        cls.a = analyse(cls.raw, {"equations": cls.defs, "ext_values": EXT})
        cls.by = {x["sym"]: x for x in cls.a.equations}

    def test_keeps_unit_u_origin(self):
        x = self.a.variables["Ltheo"]
        self.assertEqual((x["value"], x["unit"], x["u"]), (12.33, "%", 0.02))
        self.assertIn("Projektindex g-1", x["label"])
        self.assertAlmostEqual(self.by["Ltheo_idx"]["unc"]["u"], 0.02)

    def test_kelvin_next_to_celsius_is_refused(self):
        self.assertIsNone(self.by["mixT"]["value"])                    # same factor, other zero point
        self.assertIn("convert(Tref", self.by["mixT"]["error"])
        self.assertIsNone(self.by["okT"]["error"])

    def test_wrong_dimension_refused(self):
        self.assertIsNone(self.by["bad"]["value"])
        self.assertIsNone(self.by["rel"]["error"])
        self.assertGreater(self.by["rel"]["unc"]["u"], 0)

    def test_report_row(self):
        data, name = SY.make("oxalat")[0]
        b = B.build([(data, name, None, {"equations": self.defs, "ext_values": EXT})], {"items": [{"name": name}]}, lang="de")
        files = [k for k in b["files"] if k.endswith("gleichungen.tex")]
        self.assertTrue(files)
        t = base64.b64decode(b["files"][files[0]]).decode("utf-8")
        self.assertIn("Projektindex g-1", t)
        t.encode("latin-1")


if __name__ == "__main__":
    unittest.main()
