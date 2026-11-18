"""Golden test (A0): report bundles of two fixed calculator states compared with stored references.

Fixed inputs (from test_rechner.py): "sheet" = legacy sheet with one formula card, a function plot, a console line
and a matrix (Bundle.REQ); "envs" = two environments with calc lines, cards, a regression and a formula curve
(BundleEnvs). References: tests/golden/rechner_<case>_<lang>.json.
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
from rechner import bundle as B  # noqa: E402

GOLDEN = Path(__file__).resolve().parent / "golden"

SHEET = {"sheet": {"values": [{"id": "1", "sym": "v", "kind": "velocity", "value": "72", "unit": "km/h"},
                              {"id": "2", "sym": "t", "kind": "time", "value": "8", "unit": "s"}],
                   "cards": [{"id": "c1", "eq": "kin_a_mean", "vars": {}}]},
         "plots": [{"functions": [{"kind": "fx", "expr": "x^2"}], "view": {"xmin": -2, "xmax": 2, "ymin": -1, "ymax": 4}}],
         "console": [{"tex": "1 + 1", "result_tex": "2"}], "matrices": {"A": [[1, 2], [3, 4]]}, "ctx": {}}

ENVS = {"values": [{"id": "v", "sym": "v", "kind": "velocity", "value": "72", "unit": "km/h", "scope": "all"},
                   {"id": "t", "sym": "t", "kind": "time", "value": "8", "unit": "s", "scope": ["e1"]},
                   {"id": "m", "sym": "m", "kind": "mass", "value": "1.2", "unit": "t", "scope": ["e2"]}],
        "envs": [{"id": "e1", "name": "Bremsen", "items": [
                     {"id": "c1", "type": "calc", "src": "v/t"},
                     {"id": "c2", "type": "calc", "src": "k = 2*v"},
                     {"id": "c3", "type": "calc", "src": "k/2 -> km/h"},
                     {"id": "l1", "type": "calc", "src": "RT = Rgas*298.15", "report": True}]},
                 {"id": "e2", "name": "Energie", "items": [
                     {"id": "k1", "type": "card", "eq": "en_kin", "vars": {}},
                     {"id": "c4", "type": "calc", "src": "v/t"},
                     {"id": "k0", "type": "card", "eq": "en_kin", "vars": {"m": {"value": "2", "unit": "kg"}}}]}],
        "angle": "rad", "lang": "de",
        "plots": [{"title": "Parabel", "view": {"xmin": -3, "xmax": 3, "ymin": -1, "ymax": 9}, "env": "",
                   "rows": [{"id": "1", "src": "y = x^2"},
                            {"id": "t", "kind": "table", "table": {"cols": [{"name": "x1", "values": ["0", "1", "2"]},
                                                                            {"name": "y1", "values": ["0", "1.1", "3.9"]}]}},
                            {"id": "r", "src": "y1 ~ a x1^2"}],
                   "curves": [{"env": "e2", "card": "k1", "xvar": "v", "x0": 1, "x1": 30}]}]}


class GoldenBundle(unittest.TestCase):
    def _check(self, case, req, lang):
        labgolden.check(B.build(copy.deepcopy(req), lang=lang), GOLDEN / f"rechner_{case}_{lang}.json")

    def test_sheet_de(self):
        self._check("sheet", SHEET, "de")

    def test_sheet_en(self):
        self._check("sheet", SHEET, "en")

    def test_envs_de(self):
        self._check("envs", ENVS, "de")

    def test_envs_en(self):
        self._check("envs", ENVS, "en")


if __name__ == "__main__":
    unittest.main()
