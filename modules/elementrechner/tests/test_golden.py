"""Golden test (A0): the report bundle of a fixed calculator state compared with a stored reference.

Fixed input: equation Zn + CuSO4 -> ZnSO4 + Cu with 6.5 g Zn, pH of 0.1 M acetic acid, titration of 25 mL 0.1 M acetic
acid with 0.1 M NaOH, and the species NaCl (real data files of labcalc; no designer/molecule and no prep input).
References: tests/golden/elementrechner_<lang>.json. Regenerate with FOLIO_GOLDEN_UPDATE=1 (see sdk/python/labgolden.py).
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
from elementrechner import bundle as B  # noqa: E402
from laboptional import skip_unless  # noqa: E402

GOLDEN = Path(__file__).resolve().parent / "golden"
STATE = {"equation": "Zn + CuSO4 -> ZnSO4 + Cu", "amounts": {"0": {"mass_g": 6.5}},
         "ph": {"mixture": "0,1 M CH3COOH"},
         "titration": {"analyte": "0,1 M CH3COOH", "V0": 25, "titrant": "NaOH", "c": 0.1, "Vmax": 50},
         "species": ["NaCl"]}


@skip_unless('pka', 'srd46', 'asd', 'burcat')
class GoldenBundle(unittest.TestCase):
    def _check(self, lang):
        b = B.build({"state": copy.deepcopy(STATE)}, lang)
        labgolden.check(b, GOLDEN / f"elementrechner_{lang}.json")

    def test_bundle_de(self):
        self._check("de")

    def test_bundle_en(self):
        self._check("en")


if __name__ == "__main__":
    unittest.main()
