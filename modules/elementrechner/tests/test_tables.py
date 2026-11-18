"""ER-X04: Import eigener Datentabellen (CSV/JSON) mit Quellenpflicht, Vorrang und Export."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from labcalc import substances as S
from elementrechner import server as SV
from elementrechner import tables as TB

CSV = """# Quelle: Laborhandbuch Messreihe A
# Jahr: 2026
name;formula;property;value;unit;T
Ethanol;C2H6O;density;0,7801;g/cm3;20
Ethanol;C2H6O;Siedepunkt;78,2;°C;
Testgemisch X;;mp;-12,5;°C;
"""

CSV_ROWSRC = """name,property,value,unit,source,source_doi
Wasser,density,0.99705,g/cm3,Kell 1975,10.1021/je60064a005
Wasser,bp,100.0,°C,,
"""


class Tables(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="er_tbl_"))
        self.state = SV.State(self.tmp)
        SV.STATE = self.state

    def tearDown(self):
        S.set_user_store(lambda: {})
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _import(self, text, dry=False):
        rows, src = TB.parse(text)
        items, errors = TB.to_items(rows, src, self.state.own.items())
        items = [SV.own_clean(it) for it in items]
        if not dry:
            for it in items:
                self.state.own.put(it)
            S.set_user_store(self.state.own_records)
        return rows, src, items, errors

    def test_table_source_and_decimal_comma(self):
        rows, src, items, errors = self._import(CSV)
        self.assertEqual(errors, [])
        self.assertEqual(src["title"], "Laborhandbuch Messreihe A")
        self.assertEqual(src["year"], "2026")
        eth = next(it for it in items if it["name"] == "Ethanol")
        self.assertAlmostEqual(eth["values"]["density"][0]["v"], 0.7801)
        self.assertEqual(eth["values"]["density"][0]["T"], 20.0)
        self.assertIn("bp", eth["values"])                                 # deutsche Bezeichnung erkannt
        self.assertEqual(eth["values"]["density"][0]["source"]["title"], "Laborhandbuch Messreihe A")
        self.assertTrue(eth.get("ref") and not eth["ref"].startswith("own:"))   # an den Sammlungsstoff gebunden
        self.assertNotIn("ref", next(it for it in items if it["name"] == "Testgemisch X"))

    def test_rows_without_source_rejected(self):
        rows, src, items, errors = self._import(CSV_ROWSRC)
        self.assertIsNone(src)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["row"], 2)
        self.assertIn("Quelle", errors[0]["error"])
        w = items[0]["values"]["density"][0]
        self.assertEqual(w["source"]["doi"], "10.1021/je60064a005")
        self.assertNotIn("bp", items[0]["values"])

    def test_bad_values(self):
        _r, _s, _i, errors = self._import("# Quelle: Test\nname;property;value\nA;mp;abc\nB;farbe;rot\n;mp;1\nC;descr;3\n", dry=True)
        self.assertEqual([e["row"] for e in errors], [1, 2, 3, 4])

    def test_precedence(self):
        bundled = S.prop("Ethanol", "density")
        self._import(CSV)
        own = S.prop("Ethanol", "density")
        self.assertAlmostEqual(own["v"], 0.7801)
        self.assertEqual(own["quality"], "eigener Wert")
        self.assertNotAlmostEqual(bundled["v"], 0.7801, places=4)

    def test_json_and_merge(self):
        self._import(CSV)
        j = json.dumps({"source": {"title": "Datenblatt Hersteller Y", "url": "https://example.org/db.pdf", "type": "web"},
                        "rows": [{"Stoff": "Testgemisch X", "Grösse": "flash", "Wert": 23, "Einheit": "°C"}]})
        _r, src, items, errors = self._import(j)
        self.assertEqual(errors, [])
        x = [it for it in self.state.own.items() if it["name"] == "Testgemisch X"]
        self.assertEqual(len(x), 1)                                         # ergänzt, nicht verdoppelt
        self.assertEqual(set(x[0]["values"]), {"mp", "flash"})

    def test_export_roundtrip(self):
        self._import(CSV)
        csv_text = TB.export_csv(self.state.own.items())
        self.assertIn("Laborhandbuch Messreihe A", csv_text)
        rows, src, = TB.parse(csv_text)
        self.assertIsNone(src)
        items, errors = TB.to_items(rows, None, [])
        self.assertEqual(errors, [])
        self.assertEqual(sum(len(v) for it in items for v in it["values"].values()), 3)

    def test_missing_columns(self):
        with self.assertRaises(ValueError):
            TB.parse("name;value\nA;1\n")
        with self.assertRaises(ValueError):
            TB.parse("   ")


if __name__ == "__main__":
    unittest.main()
