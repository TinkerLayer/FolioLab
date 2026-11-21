"""Every report piece of the microscopy module declares which methods steps it needs.

One image: own equations (table, budget, values) need the equations block. Several images: the bundle has no methods
text, so its figures, table and series uncertainty declare ``steps=[]``.
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

from mikro import bundle  # noqa: E402
from mikro.imageio import load_bytes, sample_image  # noqa: E402
from test_uncertainty import state  # noqa: E402


def undeclared(d):
    return [f"{it['kind']}:{it['id']}" for it in d["items"] if it["kind"] in ("figure", "table", "text")
            and not it.get("methods") and "steps" not in (it.get("needs") or {})]


class Declared(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw, cls.name = sample_image()
        cls.st = load_bytes(cls.raw, cls.name)

    def test_every_call_declares_its_steps(self):
        tree = ast.parse((ROOT / "mikro" / "bundle.py").read_text(encoding="utf-8"))
        missing = []
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            name = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
            direct = isinstance(n.func, ast.Attribute) and name in ("add_figure", "add_table", "add_text")
            if (direct or name == "_fig") and not any(k.arg == "steps" or k.arg is None for k in n.keywords):
                missing.append(n.lineno)
        self.assertEqual(missing, [])

    def test_single_with_equation(self):
        s = state(equations=[{"sym": "q", "expr": "D90/D10", "unit": ""}])
        d = bundle.build([(self.st, self.raw, s)], {"items": [{"name": self.name}]}, "de")
        self.assertEqual(undeclared(d), [])
        items = {it["id"]: it for it in d["items"] if it["kind"] == "table"}
        self.assertEqual(items["eq-q-budget"]["needs"]["steps"], ["gleichungen"])
        self.assertEqual(items["gleichungen"]["needs"]["steps"], ["gleichungen"])

    def test_several_images(self):
        for lang in ("de", "en"):
            d = bundle.build([(self.st, self.raw, state()), (self.st, self.raw, state(size_min=6))],
                             {"items": [{"name": self.name}, {"name": self.name}]}, lang)
            self.assertEqual(undeclared(d), [])
            self.assertFalse(any(it.get("methods") for it in d["items"]))
            ids = {it["id"] for it in d["items"] if "id" in it}
            self.assertTrue({"vergleich", "bild1", "bild2", "unsicherheit"} <= ids, ids)


if __name__ == "__main__":
    unittest.main()
