"""Tests der gemeinsamen SDK-Teile:  python -m unittest discover -s sdk/python/tests   (im Folio-Lab-Ordner)."""
import base64
import sys
import tempfile
import unittest
from pathlib import Path

SDK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SDK))

import labcite as C  # noqa: E402
from labbundle import Bundle  # noqa: E402
from labcalc import formulas as F  # noqa: E402
from labuser import JsonStore  # noqa: E402

ART = {"type": "article", "authors": "Schindler, A.; Neumann, M.; Rodriguez Vazquez, E.", "year": "2017",
       "title": "Thermal analysis of polymers: identification", "container": "Journal of Thermal Analysis and Calorimetry",
       "volume": "129", "pages": "833-842", "doi": "https://doi.org/10.1007/s10973-017-6208-5", "licence": "CC BY 4.0"}


def bib(b):
    return base64.b64decode(b.to_dict()["files"]["refs.bib"]).decode("utf-8")


class CiteTest(unittest.TestCase):
    def test_clean_and_errors(self):
        r = C.clean(ART)
        self.assertEqual(r["doi"], "10.1007/s10973-017-6208-5")
        self.assertEqual(C.errors(r), [])
        self.assertTrue(C.errors({"type": "article"}))
        self.assertIn("DOI", " ".join(C.errors({"title": "x", "doi": "abc"})))
        self.assertTrue(C.errors({"title": "x", "url": "ftp://x"}))
        self.assertEqual(C.clean({"type": "nonsense", "title": "t", "evil": "x"}), {"type": "misc", "title": "t"})

    def test_bib_types_and_fields(self):
        b = Bundle(module="t", module_name="T", title="t")
        k = C.to_bib(b, C.key_for("ref", ART), ART)
        self.assertTrue(k.startswith("ref-schindler-2017-"))
        s = bib(b)
        self.assertIn("@article{" + k, s)
        self.assertIn("journal = {Journal of Thermal Analysis and Calorimetry}", s)
        self.assertIn("doi = {10.1007/s10973-017-6208-5}", s)
        self.assertIn("pages = {833--842}", s)
        self.assertIn("Lizenz: CC BY 4.0", s)
        ds = {"type": "datasheet", "authors": "Freudenberg Sealing Technologies", "title": "Material 70 NBR NB704816",
              "url": "https://products.fst.com/x%20y.pdf", "accessed": "2026-11-16", "year": "2025"}
        b2 = Bundle(module="t", module_name="T", title="t")
        C.to_bib(b2, "x", ds)
        s2 = bib(b2)
        self.assertIn("@manual{x", s2)
        self.assertIn("author = {{Freudenberg Sealing Technologies}}", s2)   # Organisation als ein Name
        self.assertIn("urldate = {2026-11-16}", s2)

    def test_keys_short_text(self):
        self.assertEqual(C.key_for("ref", ART), C.key_for("ref", dict(ART, accessed="2020-01-01")))
        self.assertNotEqual(C.key_for("ref", ART), C.key_for("ref", dict(ART, pages="1-2")))
        self.assertEqual(C.short(ART), "Schindler u. a. 2017")
        self.assertEqual(C.short(ART, "en"), "Schindler et al. 2017")
        t = C.text(ART)
        self.assertIn("doi:10.1007/s10973-017-6208-5", t)
        self.assertIn("(2017):", t)
        self.assertEqual(C.from_legacy("EN 485-2")["title"], "EN 485-2")

    def test_web_asset(self):
        self.assertIn(b"window.LabRef", C.web_asset("labref.js"))
        with self.assertRaises(FileNotFoundError):
            C.web_asset("../python/labcite.py")


class FormulaTest(unittest.TestCase):
    def test_evaluate_chain_units_errors(self):
        defs = [{"sym": "ratio", "label": "Streckgrenzenverhältnis", "expr": "Rm/Rp", "digits": 3},
                {"sym": "W", "expr": "ratio*2 + pi", "unit": "J"},
                {"sym": "bad", "expr": "Rm/0"},
                {"sym": "Rm", "expr": "1"},
                {"sym": "imp", "expr": "__import__('os')"},
                {"sym": "fx", "expr": "A(1715)*2"}]
        res = F.evaluate(defs, {"Rm": {"value": 300, "unit": "MPa"}, "Rp": 200}, {"A": lambda x: x / 1000})
        by = {r["sym"]: r for r in res}
        self.assertAlmostEqual(by["ratio"]["value"], 1.5)
        self.assertEqual(by["ratio"]["text"], "1,5")
        self.assertAlmostEqual(by["W"]["value"], 3 + 3.141592653589793)
        self.assertIsNone(by["bad"]["value"])
        self.assertIn("endlich", by["bad"]["error"])
        self.assertIn("Messwert", by["Rm"]["error"])
        self.assertIsNotNone(by["imp"]["error"])
        self.assertAlmostEqual(by["fx"]["value"], 3.43)
        self.assertIn(r"\frac", by["ratio"]["tex"])

    def test_report(self):
        b = Bundle(module="t", module_name="T", title="t")
        res = F.evaluate([{"sym": "CI", "label": "Carbonylindex", "expr": "a/b", "digits": 3, "source": ART}],
                         {"a": 2, "b": 4})
        out = F.to_report(b, res, "de")
        self.assertEqual(out["values"], ["eq-CI"])
        self.assertEqual(len(out["cites"]), 1)
        self.assertIn(r"\[", out["latex"])
        d = b.to_dict()
        self.assertIn("gleichungen.tex", d["files"])
        self.assertIn(out["cites"][0], bib(b))


class StoreTest(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            s = JsonStore(Path(td) / "x.json", kind="t/1")
            a = s.put({"name": "A"})
            s.put({"name": "B"})
            s.put(dict(a, name="A2"))
            self.assertEqual([x["name"] for x in s.items()], ["A2", "B"])
            exp = s.export()
            self.assertTrue(s.delete(a["id"]))
            self.assertFalse(s.delete("nope"))
            self.assertEqual(s.import_(exp), 2)
            self.assertEqual(len(s.items()), 3)
            s.import_(exp, replace=True)
            self.assertEqual(len(s.items()), 2)


if __name__ == "__main__":
    unittest.main()
