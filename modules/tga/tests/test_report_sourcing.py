"""Every report piece of the TGA declares which methods steps it needs.

The comparison table of several runs needs the DTG and the step evaluation; own equations (table, values) need their
block in the methods text, which holds the equations of the first run only.
"""
import ast
import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "sdk" / "python"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")

from tga import bundle as B  # noqa: E402
from tga import synth as SY  # noqa: E402

EQ = [{"sym": "n", "label": "n(H2O)", "expr": "L1/100*146.11/18.015"}]


def undeclared(d):
    return [f"{it['kind']}:{it['id']}" for it in d["items"] if it["kind"] in ("figure", "table", "text")
            and not it.get("methods") and "steps" not in (it.get("needs") or {})]


class Declared(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw, cls.name = SY.make("oxalat")[0]

    def test_every_call_declares_its_steps(self):
        tree = ast.parse((ROOT / "tga" / "bundle.py").read_text(encoding="utf-8"))
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                 and n.func.attr in ("add_figure", "add_table", "add_text")]
        self.assertEqual([n.lineno for n in calls if not any(k.arg == "steps" for k in n.keywords)], [])

    def test_single_equation_block_is_a_step(self):
        for lang in ("de", "en"):
            d = B.build([(self.raw, self.name, None, {"equations": copy.deepcopy(EQ)})], {"items": [{"name": self.name}]}, lang=lang)
            self.assertEqual(undeclared(d), [])
            tab = next(it for it in d["items"] if it.get("id") == "gleichungen")
            self.assertEqual(tab["needs"]["steps"], ["gleichungen"])
            meth = next(it for it in d["items"] if it.get("methods"))
            self.assertTrue(any(s.get("of") == "gleichungen" for s in meth["steps"]))
            others = [it for it in d["items"] if it["kind"] in ("figure", "table") and it["id"] != "gleichungen"]
            self.assertFalse([it["id"] for it in others if "gleichungen" in (it.get("needs") or {}).get("steps", [])])

    def test_comparison(self):
        st = {"equations": copy.deepcopy(EQ)}
        d = B.build([(self.raw, self.name, None, copy.deepcopy(st)), (self.raw, "b.csv", None, copy.deepcopy(st))],
                    {"items": [{"name": self.name}, {"name": "b.csv"}]}, lang="de")
        self.assertEqual(undeclared(d), [])
        items = {(it["kind"], it["id"]): it for it in d["items"] if "id" in it}
        self.assertEqual(items["table", "vergleich"]["needs"]["steps"], ["dtg", "stufen"])
        self.assertEqual(items["table", "p1-gleichungen"]["needs"]["steps"], ["gleichungen"])
        self.assertEqual(items["table", "p2-gleichungen"]["needs"]["steps"], [])    # not in the methods text


if __name__ == "__main__":
    unittest.main()
