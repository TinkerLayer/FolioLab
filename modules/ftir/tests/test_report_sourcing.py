"""Every report piece of the FTIR module declares which methods steps it needs.

The comparison table of several spectra needs the band evaluation (and the search if it shows hits). Own equations need
their block in the methods text for one spectrum; for several spectra the formulas stand in the results instead.
"""
import ast
import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "sdk" / "python"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import matplotlib  # noqa: E402

matplotlib.use("Agg")

from ftir import bundle, samples  # noqa: E402
from test_golden import pet_state  # noqa: E402

EQ = [{"sym": "a1715", "expr": "A(1715)", "digits": 3}]


def undeclared(d):
    return [f"{it['kind']}:{it['id']}" for it in d["items"] if it["kind"] in ("figure", "table", "text")
            and not it.get("methods") and "steps" not in (it.get("needs") or {})]


class Declared(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw, cls.name = samples.make("pet")
        cls.st = pet_state(cls.raw, cls.name)

    def test_every_call_declares_its_steps(self):
        tree = ast.parse((ROOT / "ftir" / "bundle.py").read_text(encoding="utf-8"))
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                 and n.func.attr in ("add_figure", "add_table", "add_text")]
        self.assertEqual([n.lineno for n in calls if not any(k.arg == "steps" for k in n.keywords)], [])

    def test_single_with_equation(self):
        st = {**copy.deepcopy(self.st), "equations": copy.deepcopy(EQ)}
        d = bundle.build([(self.raw, self.name, 0, st)], {"items": []}, "de")
        self.assertEqual(undeclared(d), [])
        tab = next(it for it in d["items"] if it.get("id") == "gleichungen")
        self.assertEqual(tab["needs"]["steps"], ["gleichungen"])
        meth = next(it for it in d["items"] if it.get("methods"))
        self.assertIn("gleichungen", [s["id"] for s in meth["steps"]])

    def test_comparison(self):
        raw2, name2 = samples.make("mix")
        st = {**copy.deepcopy(self.st), "equations": copy.deepcopy(EQ)}
        for lang in ("de", "en"):
            d = bundle.build([(self.raw, self.name, 0, copy.deepcopy(st)), (raw2, name2, 0, {"peaks": {"params": {}}})],
                             {"items": []}, lang)
            self.assertEqual(undeclared(d), [])
            items = {(it["kind"], it["id"]): it for it in d["items"] if "id" in it}
            self.assertEqual(items["table", "vergleich"]["needs"]["steps"], ["banden", "rauschen", "suche"])
            self.assertEqual(items["table", "p1-gleichungen"]["needs"]["steps"], [])

    def test_comparison_without_search(self):
        raw2, name2 = samples.make("mix")
        d = bundle.build([(self.raw, self.name, 0, {"peaks": {"params": {}}}), (raw2, name2, 0, {"peaks": {"params": {}}})],
                         {"items": []}, "de")
        tab = next(it for it in d["items"] if it["kind"] == "table" and it.get("id") == "vergleich")
        self.assertEqual(tab["needs"]["steps"], ["banden", "rauschen"])


if __name__ == "__main__":
    unittest.main()
