"""Every report piece of the Elementrechner declares what it needs.

The module writes no methods text (no add_methods): each text piece carries its own explanation and citations, so
every figure, table and text declares ``steps=[]``. An undeclared piece would count as needing a whole methods text.
"""
import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "sdk" / "python"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")

from elementrechner import bundle as B  # noqa: E402
from laboptional import skip_unless  # noqa: E402

U = {"parts": [{"kind": "limits", "a": 0.01, "dist": "rect"}]}
STATE = {"equation": "Zn + CuSO4 -> ZnSO4 + Cu", "amounts": {"0": {"mass_g": 6.5}}, "actual": {"3": {"mass_g": 6.0}},
         "unc": {"method": "gum", "specs": {"st.0": U, "st.3": U}},
         "ph": {"mixture": "0,1 M CH3COOH"},
         "titration": {"analyte": "0,1 M CH3COOH", "V0": 25, "titrant": "NaOH", "c": 0.1, "Vmax": 50},
         "species": ["NaCl"]}


def undeclared(d):
    return [f"{it['kind']}:{it['id']}" for it in d["items"] if it["kind"] in ("figure", "table", "text")
            and not it.get("methods") and "steps" not in (it.get("needs") or {})]


class Declared(unittest.TestCase):
    def test_every_call_declares_its_steps(self):
        """Covers the branches a single state does not reach (nuclear, kinetics, preparation, chain, ...)."""
        tree = ast.parse((ROOT / "elementrechner" / "bundle.py").read_text(encoding="utf-8"))
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                 and n.func.attr in ("add_figure", "add_table", "add_text")]
        self.assertGreater(len(calls), 40)
        self.assertEqual([n.lineno for n in calls if not any(k.arg == "steps" for k in n.keywords)], [])

    def test_no_methods_text(self):
        """If the module gets a methods text, its pieces must name real steps instead of []."""
        src = (ROOT / "elementrechner" / "bundle.py").read_text(encoding="utf-8")
        self.assertNotIn(".add_methods(", src)


@skip_unless('pka', 'srd46', 'asd', 'burcat')
class Bundles(unittest.TestCase):
    def test_real_bundle_has_no_undeclared_piece(self):
        for lang in ("de", "en"):
            d = B.build({"state": dict(STATE)}, lang)
            self.assertEqual(undeclared(d), [])
            ids = {it["id"] for it in d["items"] if "id" in it}
            self.assertTrue({"gleichung", "bilanz", "stoechiometrie", "thermochemie", "ph", "titration"} <= ids, ids)
            self.assertTrue(any(i.endswith("-budget") for i in ids), ids)     # budgets come from labcalc.uncertainty


if __name__ == "__main__":
    unittest.main()
