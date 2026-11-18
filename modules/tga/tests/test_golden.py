"""Golden test (A0): the report bundle of the synthetic calcium oxalate run compared with a stored reference.

Fixed input: synth.make("oxalat") with calibration, one assigned reaction and one own equation with a source, as in
test_tga.py (BundleTest). References: tests/golden/tga_<lang>.json.
Regenerate with FOLIO_GOLDEN_UPDATE=1 (see sdk/python/labgolden.py).
"""
import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "sdk" / "python"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import labgolden  # noqa: E402
from tga import bundle as B  # noqa: E402
from tga import synth as SY  # noqa: E402

GOLDEN = Path(__file__).resolve().parent / "golden"
STATE = {"calib": True, "reactions": [{"step": 1, "key": "oxalat1"}],
         "equations": [{"sym": "n", "label": "n(H2O)", "expr": "L1/100*146.11/18.015",
                        "source": {"type": "book", "authors": "Brown, M.E.", "title": "Introduction to Thermal Analysis",
                                   "year": "2001"}}]}


class GoldenBundle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw, cls.name = SY.make("oxalat")[0]

    def _check(self, lang):
        b = B.build([(self.raw, self.name, None, copy.deepcopy(STATE))], {"items": [{"name": self.name}]}, lang=lang)
        labgolden.check(b, GOLDEN / f"tga_{lang}.json")

    def test_bundle_de(self):
        self._check("de")

    def test_bundle_en(self):
        self._check("en")


if __name__ == "__main__":
    unittest.main()
