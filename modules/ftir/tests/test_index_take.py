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

from ftir import bundle as B  # noqa: E402
from ftir import samples as SM  # noqa: E402
from ftir.analysis import run  # noqa: E402
from test_uncert import manual, spectrum  # noqa: E402

EXT = [{"key": "Pref", "label": "Referenzlage", "value": 0.1715, "unit": "µm⁻¹", "u": 0.001, "from_name": "Projektindex g-1 · rechner"},
       {"key": "Pok", "label": "Passend", "value": 1700.0, "unit": "cm⁻¹", "u": 4.0, "from_name": "Projektindex g-2 · rechner"},
       {"key": "k", "label": "Faktor", "value": 2.0, "unit": "", "u": 0.1, "from_name": "Projektindex g-3 · rechner"}]
DEFS = [{"sym": "mix", "expr": "P1/Pref"}, {"sym": "good", "expr": "P1/Pok"}, {"sym": "sc", "expr": "k*area(1660, 1770)"},
        {"sym": "bad", "expr": "Pok + k"},
        {"sym": "Pok_idx", "label": "Passend · Projektindex g-2", "expr": "Pok", "unit": "cm⁻¹", "digits": 4}]


class TakenValues(unittest.TestCase):
    def check(self, a):
        by = {x["sym"]: x for x in a.equations}
        self.assertEqual((a.variables["Pok"]["unit"], a.variables["Pok"]["u"]), ("cm⁻¹", 4.0))
        self.assertIn("Projektindex g-2", a.variables["Pok"]["label"])
        self.assertIsNone(by["mix"]["value"])
        self.assertIn("convert(Pref", by["mix"]["error"])
        self.assertIsNone(by["bad"]["value"])
        self.assertIsNone(by["good"]["error"])
        self.assertGreater(by["good"]["unc"]["u"], 0)
        self.assertGreater(by["sc"]["unc"]["u"], 0)                 # module function next to a taken value
        self.assertAlmostEqual(by["Pok_idx"]["unc"]["u"], 4.0)

    def test_without_measurement_uncertainty(self):
        a = run(spectrum(), {"bands": [{"name": "CO", "lo": 1660, "hi": 1770}], "equations": DEFS, "ext_values": EXT})
        self.assertIsNone(a.unc)
        self.check(a)

    def test_with_measurement_uncertainty(self):
        a = run(spectrum(), manual(0.001, {"equations": DEFS, "ext_values": EXT}))
        self.assertIsNotNone(a.unc)
        self.check(a)

    def test_report_row(self):
        d, n = SM.make("pet")
        st = {"bands": [{"name": "CO", "lo": 1680, "hi": 1780}], "equations": DEFS, "ext_values": EXT}
        b = B.build([(d, n, 0, st)], {"items": [{"name": n}]}, lang="de")
        t = base64.b64decode(b["files"]["gleichungen.tex"]).decode("utf-8")
        self.assertIn("Projektindex g-2", t)
        t.encode("latin-1")


if __name__ == "__main__":
    unittest.main()
