"""Project index values in own equations: named variable with unit, u and origin; wrong units are refused."""
from __future__ import annotations

import base64
import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "sdk" / "python"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mikro import bundle  # noqa: E402
from mikro import server as SV  # noqa: E402
from mikro import uncertainty as UNC  # noqa: E402
from mikro.analysis import run  # noqa: E402
from mikro.imageio import load_bytes, sample_image  # noqa: E402
from test_uncertainty import state  # noqa: E402

EXT = [{"key": "Dref", "label": "Referenz", "value": 2.0, "unit": "mm", "u": 0.1, "from_name": "Projektindex g-1 · rechner"},
       {"key": "Dok", "label": "Passend", "value": 4.0, "unit": "µm", "u": 0.2, "from_name": "Projektindex g-2 · rechner"}]
DEFS = [{"sym": "mix", "expr": "D50/Dref"}, {"sym": "good", "expr": "D50/Dok"},
        {"sym": "Dok_idx", "label": "Passend · Projektindex g-2", "expr": "Dok", "unit": "µm", "digits": 4}]


class TakenValues(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw, cls.name = sample_image()
        cls.st = load_bytes(cls.raw, cls.name)
        cls.s = state(equations=DEFS, ext_values=EXT)
        cls.a = run(cls.st, copy.deepcopy(cls.s), "de")
        cls.u = UNC.evaluate_all(cls.a)
        cls.v, eqs = UNC.evaluate_equations(cls.a, cls.u, DEFS)
        cls.by = {x["sym"]: x for x in eqs}

    def test_variable_keeps_unit_u_origin(self):
        x = self.v["Dok"]
        self.assertEqual((x["value"], x["unit"], x["u"]), (4.0, "µm", 0.2))
        self.assertIn("Projektindex g-2", x["label"])

    def test_refused_and_computed(self):
        self.assertIsNone(self.by["mix"]["value"])
        self.assertIn("convert(Dref", self.by["mix"]["error"])
        self.assertIsNone(self.by["good"]["error"])
        self.assertGreater(self.by["good"]["unc"]["u"], 0)

    def test_state_keeps_values(self):
        self.assertEqual(SV.state_of({"ext_values": EXT})["ext_values"], EXT)
        self.assertNotIn("ext_values", SV.state_of({}))

    def test_report_row(self):
        b = bundle.build([(self.st, self.raw, copy.deepcopy(self.s))], {"items": [{"name": self.name, "state": copy.deepcopy(self.s)}]}, "de")
        t = base64.b64decode(b["files"]["gleichungen.tex"]).decode("utf-8")
        self.assertIn("Projektindex g-2", t)
        t.encode("latin-1")


if __name__ == "__main__":
    unittest.main()
