"""DP-05: marking → recipe steps → long datasets, on three workbooks (tidy; header + units + metadata; blocks side by
side), plus wide → long, transpose and skipped lines."""
from __future__ import annotations

import io
import math
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "sdk" / "python"))

from daten import readers as R  # noqa: E402
from daten import recipe as RC  # noqa: E402


def wb(build):
    import openpyxl
    w = openpyxl.Workbook()
    build(w.active)
    b = io.BytesIO()
    w.save(b)
    return R.load_bytes(b.getvalue(), "t.xlsx")[0]


def col(tbl, name):
    return next(c for c in tbl["columns"] if c["name"] == name)


def tidy(ws):
    ws.append(["t (min)", "c [mol/L]", "u(c)", "Probe"])
    for i in range(10):
        ws.append([i * 5, round(0.1 * math.exp(-0.05 * i * 5), 6), 0.001, "A" if i < 5 else "B"])


def header_units_meta(ws):
    ws["A1"] = "Kinetik Kristallviolett"
    ws["A2"] = "Temperatur:"
    ws["B2"] = 25
    ws["C2"] = "°C"
    ws["A3"] = "Ansatz: 2,5 mL"
    ws.append([])
    ws.append(["Zeit", "Extinktion", "Bemerkung"])
    ws.append(["s", "1", None])
    for i in range(8):
        ws.append([i * 30, round(1.2 * math.exp(-0.002 * i * 30), 4), "trüb" if i == 3 else None])
    ws.cell(8 + 4, 2, "<0,01")                      # one cell that is not a number


def side_by_side(ws):
    ws["A1"] = "Esterhydrolyse"
    ws.merge_cells("A1:E1")
    for k, c0 in enumerate((1, 4)):
        ws.cell(3, c0, f"Lauf {k + 1} – {25 + 10 * k} °C")
        ws.merge_cells(start_row=3, start_column=c0, end_row=3, end_column=c0 + 1)
        ws.cell(4, c0, "t")
        ws.cell(4, c0 + 1, "c")
        ws.cell(5, c0, "min")
        ws.cell(5, c0 + 1, "mol/L")
        for i in range(6):
            ws.cell(6 + i, c0, i * 10)
            ws.cell(6 + i, c0 + 1, round(0.1 * math.exp(-0.01 * (k + 1) * i * 10), 6))


class GuessExtractTest(unittest.TestCase):
    def test_tidy(self):
        sh = wb(tidy)
        steps = RC.guess(sh)
        self.assertIn({"op": "block", "range": "A2:D11"}, steps)
        self.assertIn({"op": "header", "lines": [0]}, steps)
        self.assertIn({"op": "role", "series": 2, "role": "uncertainty", "of": 1}, steps)
        t = RC.extract(sh, steps)
        self.assertEqual(t["rows"], 10)
        self.assertEqual([(c["name"], c["unit"], c["role"]) for c in t["columns"]],
                         [("t", "min", "x"), ("c", "mol/L", "y"), ("u(c)", "", "uncertainty"), ("Probe", "", "label")])
        self.assertEqual(col(t, "u(c)")["of"], "c")
        ds = RC.to_dataset(t, "Tidy", [{"name": "t.xlsx", "sha256": "0" * 64}], steps, "0.1.0")
        self.assertEqual(ds.col("t")["kind"], "time")
        self.assertEqual(ds.col("c")["u"], "u_c")
        self.assertTrue(np.allclose(ds.si("t")[:3], [0, 300, 600]))
        self.assertEqual(ds.col("t")["cells"], "Sheet!A2:A11")

    def test_units_line_with_one_unit(self):
        """x/y tables where only x has a unit: the line with the single unit is the units line, not the header."""
        def ir(ws):
            ws.append(["Messung IR"])
            ws.append(["lambda", "A"])
            ws.append(["µm", None])
            for i in range(10):
                ws.append([2.5 + i * 0.1, 0.1 + 0.01 * i])
        for sh in (wb(ir), R.load_bytes("t;c\r\n;mg/L\r\n0;1,5\r\n5;1,4\r\n10;1,3\r\n".encode("utf-8"), "x.csv")[0]):
            t = RC.extract(sh, RC.guess(sh))
            got = [(c["name"], c["unit"]) for c in t["columns"]]
            self.assertIn(got, ([("lambda", "µm"), ("A", "")], [("t", ""), ("c", "mg/L")]))
        def titled(ws):                                     # a title or "Name:" line above is no header → no change
            ws.append(["Gerät:", "TG 209"])
            ws.append(["Zeit", "m"])
            for i in range(6):
                ws.append([i, 10 - i * 0.1])
        t = RC.extract(wb(titled), RC.guess(wb(titled)))
        self.assertEqual([c["name"] for c in t["columns"]], ["Zeit", "m"])

    def test_header_units_meta(self):
        sh = wb(header_units_meta)
        steps = RC.guess(sh)
        self.assertIn({"op": "header", "lines": [4]}, steps)
        self.assertIn({"op": "units", "line": 5}, steps)
        metas = [s for s in steps if s["op"] == "meta"]
        self.assertEqual(metas[0], {"op": "meta", "cell": "B2", "name": "Temperatur", "unit": "°C", "as": "condition"})
        self.assertEqual(metas[1]["cell"], "A3")
        t = RC.extract(sh, steps)
        self.assertEqual(t["conditions"]["Temperatur"], {"value": 25.0, "unit": "°C", "from": "Sheet!B2"})
        self.assertEqual(t["conditions"]["Ansatz"], {"value": 2.5, "unit": "mL", "from": "Sheet!A3"})
        ext = col(t, "Extinktion")
        self.assertEqual((ext["unit"], t["rows"]), ("", 8))
        self.assertEqual(ext["raw"], {})                  # DP-06: "<0,01" is a value at the detection limit
        self.assertAlmostEqual(ext["values"][5], 0.01)
        self.assertEqual(col(t, "Bemerkung")["values"][3], "trüb")
        self.assertTrue(any("Nachweisgrenze" in n for n in t["notes"]))
        ds = RC.to_dataset(t, "Meta", [], steps, "0.1.0")
        self.assertEqual(ds.header["flags"], [{"row": 5, "col": "Extinktion", "code": "below_lod", "raw": "<0,01",
                                               "reason": "Wert = Grenze (<0,01)"}])
        self.assertEqual(ds.header["conditions"]["Temperatur"]["unit"], "°C")

    def test_side_by_side_blocks(self):
        sh = wb(side_by_side)
        steps = RC.guess(sh)
        self.assertIn({"op": "block", "range": "A6:B11"}, steps)
        self.assertIn({"op": "repeat", "dir": "right", "step": 3, "count": 2, "label": "A3"}, steps)
        t = RC.extract(sh, steps)
        self.assertEqual(t["blocks"], 2)
        self.assertEqual(t["rows"], 12)
        self.assertEqual([(c["name"], c["unit"], c["role"]) for c in t["columns"]],
                         [("Block", "", "group"), ("t", "min", "x"), ("c", "mol/L", "y")])
        self.assertEqual(list(col(t, "Block")["values"][[0, 6]]), ["Lauf 1 – 25 °C", "Lauf 2 – 35 °C"])
        self.assertEqual(col(t, "t")["values"][6], 0)
        self.assertEqual(col(t, "t")["cells"], "Sheet!A6:A11; Sheet!D6:D11")
        kinds = {m["kind"] for m in t["marks"]}
        self.assertTrue({"data", "header", "units", "label"} <= kinds)
        ds = RC.to_dataset(t, "Läufe", [], steps, "0.1.0")
        self.assertEqual(ds.rows, 12)
        self.assertEqual(ds.col("Block")["role"], "group")

    def test_wide_to_long(self):
        def build(ws):
            ws.append(["t (min)", "c bei 25 °C", "c bei 35 °C", "c bei 45 °C"])
            for i in range(4):
                ws.append([i * 5] + [round(0.1 * math.exp(-0.01 * k * i * 5), 5) for k in (1, 2, 3)])
        sh = wb(build)
        steps = RC.guess(sh) + [{"op": "wide", "series": [1, 2, 3], "name": "c", "cond": "T"}]
        t = RC.extract(sh, steps)
        self.assertEqual(t["rows"], 12)
        self.assertEqual([(c["name"], c["unit"], c["role"]) for c in t["columns"]],
                         [("t", "min", "x"), ("T", "°C", "condition"), ("c", "", "y")])
        self.assertEqual(list(col(t, "T")["values"][[0, 4, 8]]), [25, 35, 45])
        self.assertEqual(list(col(t, "t")["values"][[0, 4]]), [0, 0])
        # stacking columns with different units keeps no unit and says so
        mixed = RC.extract(sh, RC.guess(sh) + [{"op": "wide", "series": [0, 1], "name": "v", "cond": "Spalte"}])
        self.assertEqual((col(mixed, "v")["unit"], col(mixed, "v")["role"]), ("", "y"))
        self.assertTrue(any("Einheiten" in n for n in mixed["notes"]))

    def test_transpose_and_skip(self):
        def build(ws):
            ws.append(["t", "s", 0, 10, 20, 30, 40])
            ws.append(["m", "mg", 10.0, 9.5, "Pause", 9.0, 8.7])
        sh = wb(build)
        steps = [{"op": "transpose", "on": True}, {"op": "block", "range": "C1:G2"}, {"op": "header", "lines": [0]},
                 {"op": "units", "line": 1}, {"op": "role", "series": 0, "role": "x"}, {"op": "role", "series": 1, "role": "y"},
                 {"op": "skip", "lines": [4]}]
        t = RC.extract(sh, steps)
        self.assertEqual([(c["name"], c["unit"]) for c in t["columns"]], [("t", "s"), ("m", "mg")])
        self.assertEqual(list(col(t, "t")["values"]), [0, 10, 30, 40])
        self.assertEqual(list(col(t, "m")["values"]), [10.0, 9.5, 9.0, 8.7])
        self.assertEqual(col(t, "m")["cells"], "Sheet!C2:G2")
        # toggling the skip again brings the line back (as a non-number cell)
        t2 = RC.extract(sh, steps + [{"op": "skip", "lines": [4]}])
        self.assertEqual(col(t2, "m")["raw"], {2: "Pause"})

    def test_csv_first_guess_uses_reader_guess(self):
        text = "Messung: A1\nEinwaage: 12,3 mg\n\nZeit;Temperatur;Masse\nmin;°C;mg\n" + \
               "\n".join(f"{i};{25 + 10 * i},5;{12.3 - 0.01 * i:.3f}".replace(".", ",") for i in range(30))
        sh = R.read_text(text, "tga.csv")[0]
        steps = RC.guess(sh)
        t = RC.extract(sh, steps)
        self.assertEqual([(c["name"], c["unit"]) for c in t["columns"]], [("Zeit", "min"), ("Temperatur", "°C"), ("Masse", "mg")])
        self.assertEqual(t["conditions"], {"Einwaage": {"value": 12.3, "unit": "mg", "from": "tga!A2"}})
        self.assertEqual(t["rows"], 30)

    def test_refusals(self):
        sh = wb(tidy)
        with self.assertRaises(RC.RecipeError):
            RC.extract(sh, [])
        with self.assertRaises(RC.RecipeError):
            RC.extract(sh, [{"op": "explode"}])
        with self.assertRaises(RC.RecipeError):
            RC.extract(sh, [{"op": "block", "range": "A2:D11"}, {"op": "role", "series": 0, "role": "boss"}])
        with self.assertRaises(RC.RecipeError):
            RC.extract(sh, [{"op": "block", "range": "A2:D11"}, {"op": "wide", "series": [1]}])
        bad = RC.extract(sh, [{"op": "block", "range": "A2:B11"}, {"op": "header", "lines": [0]}])
        bad["columns"][0]["unit"] = "Furlong"
        import labdataset as DS
        with self.assertRaises(DS.DatasetError):
            RC.to_dataset(bad, "x", [], [], "0.1.0")
        self.assertIsNotNone(RC.unit_problem("Furlong"))
        self.assertIsNone(RC.unit_problem("mol/L"))


if __name__ == "__main__":
    unittest.main()
