"""Golden test (A0): the report bundle of the synthetic sample image compared with a stored reference.

Fixed input: imageio.sample_image() (seed 7, 16-bit TIFF, 0.25 um/px) with the pipeline, particle filter, scale bar
and the two ROIs of test_mikro.py. References: tests/golden/mikroskopie_<lang>.json.
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
from mikro import bundle  # noqa: E402
from mikro.imageio import load_bytes, sample_image  # noqa: E402

GOLDEN = Path(__file__).resolve().parent / "golden"
PIPE = [{"op": "background", "radius": 30}, {"op": "gauss", "sigma": 1.5},
        {"op": "threshold", "method": "otsu", "dark": True}, {"op": "fill"}]
STATE = {"pipeline": PIPE, "particles": {"size_min": 2}, "scalebar": {"pos": "bl", "len": 20, "box": True},
         "rois": [{"type": "rect", "x": 50, "y": 60, "w": 200, "h": 150, "name": "Feld A"},
                  {"type": "line", "x1": 100, "y1": 300, "x2": 600, "y2": 320, "name": "L1"}]}


class GoldenBundle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw, cls.name = sample_image()

    def _check(self, lang):
        st = load_bytes(self.raw, self.name)
        state = copy.deepcopy(STATE)
        b = bundle.build([(st, self.raw, state)], {"items": [{"name": self.name, "state": copy.deepcopy(STATE)}]}, lang)
        labgolden.check(b, GOLDEN / f"mikroskopie_{lang}.json")

    def test_bundle_de(self):
        self._check("de")

    def test_bundle_en(self):
        self._check("en")


if __name__ == "__main__":
    unittest.main()
