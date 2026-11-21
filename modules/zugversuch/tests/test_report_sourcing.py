"""Every report piece of the tensile test declares which methods steps it needs.

Single test: own equations (table, budgets, values) need the equations block. Several tests: the bundle has no methods
text, so the overlays, the comparison table and the series uncertainty declare ``steps=[]``.
"""
import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "sdk" / "python"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import matplotlib  # noqa: E402

matplotlib.use("Agg")

from flps import bundle  # noqa: E402
from test_uncertainty import UNC_ALL, measure  # noqa: E402


def undeclared(d):
    return [f"{it['kind']}:{it['id']}" for it in d["items"] if it["kind"] in ("figure", "table", "text")
            and not it.get("methods") and "steps" not in (it.get("needs") or {})]


def build(runs, lang="de"):
    return bundle.build([x[0] for x in runs], {x[2]: x[1] for x in runs},
                        {"items": [{"name": x[2], "config": x[3].to_dict()} for x in runs]}, lang=lang)


class Declared(unittest.TestCase):
    def test_every_call_declares_its_steps(self):
        tree = ast.parse((ROOT / "flps" / "bundle.py").read_text(encoding="utf-8"))
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                 and n.func.attr in ("add_figure", "add_table", "add_text")]
        self.assertEqual([n.lineno for n in calls if not any(k.arg == "steps" for k in n.keywords)], [])

    def test_single_with_equation(self):
        run = measure(unc=UNC_ALL, equations=[{"sym": "q", "expr": "Rm/E", "unit": ""}])
        d = build([run])
        self.assertEqual(undeclared(d), [])
        items = {it["id"]: it for it in d["items"] if it["kind"] == "table"}
        self.assertEqual(items["gleichungen"]["needs"]["steps"], ["gleichungen"])
        self.assertEqual(items["eq-q-budget"]["needs"]["steps"], ["gleichungen"])
        self.assertEqual(items["Rm-budget"]["needs"]["steps"], ["unsicherheit"])
        meth = next(it for it in d["items"] if it.get("methods"))
        self.assertIn("gleichungen", [s["id"] for s in meth["steps"]])

    def test_series(self):
        runs = [measure(scale=s, unc=UNC_ALL, name=f"U{i}") for i, s in enumerate((1.0, 1.02, 0.98))]
        for lang in ("de", "en"):
            d = build(runs, lang)
            self.assertEqual(undeclared(d), [])
            self.assertFalse(any(it.get("methods") for it in d["items"]))
            ids = {it["id"] for it in d["items"] if "id" in it}
            self.assertTrue({"verlauf", "kennwerte", "vergleich", "serie-Rm-budget", "unsicherheit"} <= ids, ids)


if __name__ == "__main__":
    unittest.main()
