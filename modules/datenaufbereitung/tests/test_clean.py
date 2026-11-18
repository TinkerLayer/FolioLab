"""DP-06 cell formats, DP-07 cleaning steps, DP-08 outlier flags and check chips."""
from __future__ import annotations

import datetime as dt
import io
import math
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "sdk" / "python"))

import labdataset as DS  # noqa: E402

from daten import clean as C  # noqa: E402
from daten import datasets as D  # noqa: E402
from daten import parse as P  # noqa: E402
from daten import readers as R  # noqa: E402
from daten import recipe as RC  # noqa: E402


def every_format(ws):
    ws.append(["Probe", "c [mg/L]", "Zeit", "Uhrzeit", "Bemerkung"])
    cells = ["12,5", "1.234,5", "1,2E-1", "1,2·10^-1", "<0,01", "<NWG", ">1000", "n.d.", "—", "#DIV/0!",
             "12,3 ± 0,4", "0,02 g/L", "15 mg/L", "0,5 g"]
    t0 = dt.datetime(2024, 3, 1, 23, 40, 0)
    for i, x in enumerate(cells):
        t = t0 + dt.timedelta(minutes=10 * i)
        ws.append([f"P{i + 1}", x, t, t.strftime("%H:%M:%S"), "ok"])        # clock text runs past midnight


def wb(build):
    import openpyxl
    w = openpyxl.Workbook()
    build(w.active)
    b = io.BytesIO()
    w.save(b)
    return R.load_bytes(b.getvalue(), "t.xlsx")[0]


def col(tbl, name):
    return next(c for c in tbl["columns"] if c["name"] == name)


class FormatTest(unittest.TestCase):
    """DP-06: a sheet with every format parses with the expected values and flags."""

    def test_markers(self):
        self.assertEqual(P.marker("<0,01")["code"], "below_lod")
        self.assertAlmostEqual(P.marker("<0,01")["value"], 0.01)
        self.assertTrue(math.isnan(P.marker("<NWG")["value"]))
        self.assertEqual(P.marker("< LOD")["code"], "below_lod")
        self.assertEqual(P.marker(">1000")["code"], "above_range")
        for t in ("n.d.", "—", "-", "k.A.", "#DIV/0!", "#NV", "#WERT!"):
            self.assertEqual(P.marker(t)["code"], "missing", t)
        r = P.marker("12,3 ± 0,4")
        self.assertEqual((r["value"], r["u"], r["code"]), (12.3, 0.4, None))
        r = P.marker("1,5 ± 0,1 g", "mg")                          # value and u converted to the column unit
        self.assertAlmostEqual(r["value"], 1500.0)
        self.assertAlmostEqual(r["u"], 100.0)
        self.assertAlmostEqual(P.marker("0,02 g/L", "mg/L")["value"], 20.0)
        self.assertEqual(P.marker("0,02 g/L", "mg/L")["code"], "note")
        self.assertIsNone(P.marker("0,5 g", "mg/L"))                 # other dimension → stays a parse error
        self.assertIsNone(P.marker("trüb"))
        self.assertFalse(P.resolvable("1. Messung"))
        self.assertTrue(P.resolvable("12,5 mg"))

    def test_times(self):
        self.assertEqual(P.time_of("2024-03-01 12:00:05"), ((dt.datetime(2024, 3, 1, 12, 0, 5) - dt.datetime(1970, 1, 1)).total_seconds(), False))
        self.assertEqual(P.time_of("01.03.2024 12:00")[1], False)
        self.assertEqual(P.time_of("12:00:05"), (43205.0, True))
        rel, unit, start = P.elapsed(np.array([23 * 3600 + 50 * 60, 0.0, 600.0]), True)
        np.testing.assert_allclose(rel, [0, 10, 20])                 # past midnight, in min
        self.assertEqual((unit, start), ("min", "23:50:00"))

    def test_sheet_with_every_format(self):
        sh = wb(every_format)
        steps = RC.guess(sh)
        t = RC.extract(sh, steps)
        c = col(t, "c")
        self.assertEqual(c["unit"], "mg/L")
        v = c["values"]
        expect = [12.5, 1234.5, 0.12, 0.12, 0.01, math.nan, 1000.0, math.nan, math.nan, math.nan, 12.3, 20.0, 15.0, math.nan]
        np.testing.assert_allclose(v, expect, equal_nan=True)
        self.assertEqual(c["raw"], {13: "0,5 g"})                    # not readable in mg/L → parse error, empty
        codes = {i: m[0] for i, m in c["mk"].items()}
        self.assertEqual(codes, {4: "below_lod", 5: "below_lod", 6: "above_range", 7: "missing", 8: "missing",
                                 9: "missing", 11: "note"})
        u = col(t, "u(c)")                                          # ± → uncertainty column linked to c
        self.assertEqual((u["role"], u["of"], u["unit"]), ("uncertainty", "c", "mg/L"))
        self.assertAlmostEqual(u["values"][10], 0.4)
        self.assertTrue(np.isnan(u["values"][0]))
        z = col(t, "Zeit")                                          # Excel dates → elapsed time (130 min span → h)
        self.assertEqual((z["unit"], z["kind"]), ("h", "time"))
        np.testing.assert_allclose(z["values"], np.arange(14) * 10.0 / 60)
        self.assertEqual(t["conditions"]["Zeit Start"]["value"], "2024-03-01 23:40:00")
        h = col(t, "Uhrzeit")                                       # clock texts across midnight
        self.assertEqual(h["unit"], "h")
        np.testing.assert_allclose(h["values"], np.arange(14) * 10.0 / 60)
        ds = RC.to_dataset(t, "Formate", [], steps, "x")
        fl = {(f["row"], f["code"]) for f in ds.header["flags"]}
        self.assertIn((4, "below_lod"), fl)
        self.assertIn((13, "parse_error"), fl)
        self.assertEqual(ds.col("c")["u"], "u_c")
        self.assertEqual(ds.rows, 14)                               # flags never delete rows

    def test_colprop_symbol_kind_and_raw_time(self):
        sh = wb(every_format)
        steps = RC.guess(sh) + [{"op": "colprop", "series": 1, "symbol": "c", "kind": "mass_conc"},
                                {"op": "colprop", "series": 2, "time": "elapsed", "time_unit": "h"}]
        t = RC.extract(sh, steps)
        self.assertEqual((col(t, "c")["symbol"], col(t, "c")["kind"]), ("c", "mass_conc"))
        self.assertEqual(col(t, "Zeit")["unit"], "h")
        ds = RC.to_dataset(t, "x", [], steps, "x")
        self.assertEqual(ds.col("c")["kind"], "mass_conc")
        bad = RC.extract(sh, RC.guess(sh) + [{"op": "colprop", "series": 1, "kind": "length"}])
        with self.assertRaises(DS.DatasetError):                     # mg/L is no length
            RC.to_dataset(bad, "x", [], [], "x")
        with self.assertRaises(RC.RecipeError):
            RC.extract(sh, RC.guess(sh) + [{"op": "colprop", "series": 1, "kind": "unsinn"}])


def base():
    return DS.from_columns("Messung", [
        {"key": "t", "name": "t", "unit": "min", "role": "x", "values": [0, 1, 2, 3, 4, 5, 6, 7]},
        {"key": "c", "name": "c", "unit": "mmol/L", "role": "y", "values": [10, 8, 6.5, None, 4.4, 3.6, 2.9, 2.4]},
        {"key": "probe", "name": "Probe", "dtype": "text", "role": "group", "values": list("AABBAABB")}])


class CleanTest(unittest.TestCase):
    """DP-07: one test per step; replaying the recipe gives the same dataset."""

    def run_ops(self, ops, ds=None, loader=None):
        return D.derive(ds or base(), ops, "x", loader=loader)

    def test_trim_filter_sort_drop(self):
        ds = self.run_ops([{"op": "trim", "first": 2, "last": 6}])
        np.testing.assert_array_equal(ds.data["t"], [1, 2, 3, 4, 5])
        ds = self.run_ops([{"op": "filter", "col": "c", "cmp": ">=", "value": "4,4"}])
        np.testing.assert_array_equal(ds.data["t"], [0, 1, 2, 4])
        ds = self.run_ops([{"op": "filter", "col": "t", "cmp": "between", "value": 2, "value2": 5}])
        np.testing.assert_array_equal(ds.data["t"], [2, 3, 4, 5])
        ds = self.run_ops([{"op": "filter", "col": "probe", "cmp": "==", "value": "B"}])
        np.testing.assert_array_equal(ds.data["t"], [2, 3, 6, 7])
        ds = self.run_ops([{"op": "sort", "col": "c", "desc": False}])
        np.testing.assert_array_equal(ds.data["t"], [7, 6, 5, 4, 2, 1, 0, 3])     # missing last
        ds = self.run_ops([{"op": "drop_empty", "cols": ["c"]}])
        self.assertEqual(ds.rows, 7)
        st = ds.header["provenance"]["steps"][0]
        self.assertEqual((st["rows_before"], st["rows_after"]), (8, 7))

    def test_flags_follow_rows(self):
        d0 = base()
        d0.header["flags"] = [{"row": 5, "col": "c", "code": "note", "reason": "x"}]
        ds = self.run_ops([{"op": "sort", "col": "t", "desc": True}], d0)
        self.assertEqual(ds.header["flags"][0]["row"], 2)
        ds = self.run_ops([{"op": "trim", "first": 1, "last": 3}], d0)
        self.assertEqual(ds.header["flags"], [])

    def test_duplicates_flagged_not_removed(self):
        d0 = DS.from_columns("d", [{"key": "x", "name": "x", "unit": "s", "values": [1, 2, 2, 3, 1]},
                                   {"key": "y", "name": "y", "unit": "m", "values": [5, 6, 6, 7, 9]}])
        ds = self.run_ops([{"op": "duplicates", "cols": []}], d0)
        self.assertEqual(ds.rows, 5)
        self.assertEqual([(f["row"], f["code"], f["reason"]) for f in ds.header["flags"]], [(2, "duplicate", "wie Zeile 2")])
        ds = self.run_ops([{"op": "duplicates", "cols": ["x"]}], d0)
        self.assertEqual([f["row"] for f in ds.header["flags"]], [2, 4])

    def test_replicates(self):
        d0 = DS.from_columns("r", [{"key": "T", "name": "T", "unit": "°C", "kind": "temperature", "role": "x",
                                    "values": [25, 25, 25, 35, 35, 45]},
                                   {"key": "k", "name": "k", "unit": "1/s", "role": "y", "values": [1.0, 1.2, 1.4, 2.0, 2.2, 3.0]}])
        d0.header["flags"] = [{"row": 2, "code": "excluded", "excluded": True, "reason": "Fehlmessung"}]
        ds = self.run_ops([{"op": "replicates", "by": ["T"], "cols": ["k"]}], d0)
        np.testing.assert_array_equal(ds.data["T"], [25, 35, 45])
        np.testing.assert_allclose(ds.data["k"], [1.1, 2.1, 3.0])                      # row 3 excluded → not averaged
        np.testing.assert_allclose(ds.data["k_s"], [math.sqrt(0.02), math.sqrt(0.02), math.nan])
        np.testing.assert_array_equal(ds.data["k_n"], [2, 2, 1])
        np.testing.assert_allclose(ds.data["k_se"], [0.1, 0.1, math.nan])
        self.assertEqual(ds.col("k")["u"], "k_se")
        self.assertIn("1 ausgeschlossene", ds.header["provenance"]["steps"][0]["text"])

    def test_replicates_default_leaves_uncertainty_out(self):
        """Without chosen columns every number column is averaged except the uncertainties (the mean gets SE)."""
        d0 = DS.from_columns("r", [{"key": "g", "name": "Probe", "dtype": "text", "role": "group", "values": ["A", "A", "B", "B"]},
                                   {"key": "c", "name": "c", "unit": "mg/L", "role": "y", "u": "u_c", "values": [1.0, 1.2, 2.0, 2.4]},
                                   {"key": "u_c", "name": "u(c)", "unit": "mg/L", "role": "uncertainty", "values": [0.05, None, None, None]}])
        ds = self.run_ops([{"op": "replicates", "by": ["g"]}], d0)
        self.assertEqual([c["key"] for c in ds.columns], ["g", "c", "c_s", "c_n", "c_se"])
        self.assertEqual(ds.col("c")["u"], "c_se")
        texts = " | ".join(x["text"] for x in C.checks(ds))
        self.assertNotIn("ohne Einheit", texts)                                         # n(c) is a count
        self.assertIn("keine fehlenden Werte", texts)

    def test_join_interpolates_and_labels(self):
        other = DS.from_columns("Temperatur", [{"key": "time", "name": "Zeit", "unit": "s", "values": [0, 120, 240, 360]},
                                               {"key": "T", "name": "T", "unit": "K", "values": [300, 310, 320, 330]}])
        ds = self.run_ops([{"op": "join", "share": "S2", "mode": "pin", "version": 1, "x": "t", "x2": "time", "cols": ["T"]}],
                          loader=lambda sid, v=None: (other, {"version": 3}))
        np.testing.assert_allclose(ds.data["T"], [300, 305, 310, 315, 320, 325, 330, math.nan])   # t in min, x2 in s
        c = ds.col("T")
        self.assertIn("interpoliert", c["note"])
        interp = sorted(f["row"] for f in ds.header["flags"] if f["code"] == "interpolated")
        self.assertEqual(interp, [1, 3, 5])                                            # 0, 2, 4, 6 min are exact
        with self.assertRaises(D.DeriveError):
            self.run_ops([{"op": "join", "share": "S2", "x": "t", "x2": "T", "cols": ["T"]}],
                         loader=lambda sid, v=None: (other, {"version": 3}))           # K is not a time

    def test_smooth_savgol(self):
        x = np.linspace(0, 6, 61)
        y = np.sin(x) + 0.05 * np.cos(17 * x)
        d0 = DS.from_columns("s", [{"key": "x", "name": "x", "unit": "s", "role": "x", "values": x},
                                   {"key": "y", "name": "y", "unit": "V", "role": "y", "values": y}])
        ds = self.run_ops([{"op": "smooth", "col": "y", "window": 11, "order": 3}], d0)
        self.assertIn("Savitzky", ds.col("y_sg")["note"])
        try:
            from scipy.signal import savgol_filter
        except ImportError:                                       # reference only when scipy happens to be there
            savgol_filter = None
        if savgol_filter is not None:
            np.testing.assert_allclose(ds.data["y_sg"], savgol_filter(y, 11, 3, mode="interp"), atol=1e-10)
        self.assertLess(np.abs(ds.data["y_sg"] - np.sin(x)).max(), 0.05)
        with self.assertRaises(D.DeriveError):
            self.run_ops([{"op": "smooth", "col": "y", "window": 4}], d0)

    def test_replay_gives_same_dataset(self):
        ops = [{"op": "convert", "col": "c", "unit": "mol/L"}, {"op": "drop_empty", "cols": ["c"]},
               {"op": "sort", "col": "t", "desc": True}, {"op": "outliers", "method": "iqr", "col": "c"},
               {"op": "formula", "name": "lnc", "expr": "ln(c / c0)", "unit": "",
                "consts": [{"sym": "c0", "value": "1", "unit": "mol/L"}]}]
        a, b = self.run_ops(ops), self.run_ops(ops)
        self.assertEqual(a.header["data_hash"], b.header["data_hash"])
        self.assertEqual(a.header["flags"], b.header["flags"])
        self.assertEqual(len(a.header["provenance"]["steps"]), 5)


class OutlierTest(unittest.TestCase):
    """DP-08: Grubbs and Dixon against published examples; flags never remove rows."""

    def test_grubbs_nist_example(self):
        # NIST/SEMATECH e-Handbook, Grubbs' test example (Tietjen–Moore data): G = 2.4687, one-sided 5 %: 2.032
        x = [199.31, 199.53, 200.19, 200.82, 201.92, 201.95, 202.18, 245.57]
        r = C.grubbs(x, 0.05, "max", iterate=False)
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["i"], 7)
        self.assertAlmostEqual(r[0]["G"], 2.4687, places=3)
        self.assertAlmostEqual(r[0]["crit"], 2.032, places=3)
        self.assertEqual(C.grubbs(x[:7], 0.05), [])

    def test_t_quantile(self):
        self.assertAlmostEqual(C.t_ppf(0.975, 10), 2.228139, places=5)
        self.assertAlmostEqual(C.t_ppf(0.995, 3), 5.840909, places=5)

    def test_dixon_example(self):
        # Rorabacher (1991) critical values: n = 10, Q = 0.455 > 0.412 (90 %), < 0.466 (95 %)
        x = [0.189, 0.167, 0.187, 0.183, 0.186, 0.182, 0.181, 0.184, 0.181, 0.177]
        r = C.dixon(x, 0.10)
        self.assertEqual([d["i"] for d in r], [1])
        self.assertAlmostEqual(r[0]["Q"], 0.4545, places=4)
        self.assertEqual(C.dixon(x, 0.05), [])
        with self.assertRaises(C.CleanError):
            C.dixon(x + [0.18], 0.05)

    def test_iqr_hampel_residual(self):
        x = [10.0, 10.2, 9.9, 10.1, 10.0, 14.0, 9.8, 10.1]
        self.assertEqual([d["i"] for d in C.iqr(x)[0]], [5])
        self.assertEqual([d["i"] for d in C.hampel(x)], [5])
        t = np.arange(10.0)
        y = 2 * t + 1
        y[4] += 6
        y = y + np.array([0.1, -0.1, 0.05, -0.05, 0, 0.1, -0.1, 0.05, -0.05, 0])
        self.assertEqual([d["i"] for d in C.residual(t, y, 2.5)], [4])
        # masking: one large outlier on a curve inflates the plain residual scatter; the deleted residual finds it
        tt = np.arange(0.0, 75.0, 5.0)
        clean = 12.0 * np.exp(-0.035 * tt) + np.random.default_rng(7).normal(0, 0.05, tt.size)
        yy = clean.copy()
        yy[10] = 9.9
        e = yy - np.polyval(np.polyfit(tt, yy, 3), tt)
        plain = np.abs(e) / math.sqrt(float(e @ e) / (tt.size - 4))
        self.assertLess(plain.max(), 3.0)                                               # the old rule misses it
        self.assertEqual([d["i"] for d in C.residual(tt, yy, 3.0, 3)], [10])
        self.assertEqual(C.residual(tt, clean, 3.0, 3), [])                             # noisy curve only: nothing

    def test_flags_never_remove_rows_and_exclusion_is_separate(self):
        d0 = DS.from_columns("g", [{"key": "x", "name": "x", "unit": "mg",
                                    "values": [199.31, 199.53, 200.19, 200.82, 201.92, 201.95, 202.18, 245.57]}])
        ds = D.derive(d0, [{"op": "outliers", "method": "grubbs", "col": "x", "sided": "max"}], "g")
        self.assertEqual(ds.rows, 8)
        f = ds.header["flags"][0]
        self.assertEqual((f["row"], f["code"], f.get("excluded")), (7, "outlier", None))
        self.assertIn("Grubbs", f["rule"])
        self.assertTrue(ds.used_mask().all())
        ds2 = D.derive(d0, [{"op": "outliers", "method": "grubbs", "col": "x", "sided": "max"},
                            {"op": "exclude", "codes": ["outlier"], "reason": "Wägefehler"}], "g")
        self.assertEqual(ds2.rows, 8)
        self.assertEqual(int((~ds2.used_mask()).sum()), 1)
        self.assertIn("Wägefehler", ds2.header["flags"][0]["reason"])
        st = ds2.header["provenance"]["steps"]
        self.assertEqual((st[1]["excluded_before"], st[1]["excluded_after"]), (0, 1))
        with self.assertRaises(D.DeriveError):
            D.derive(d0, [{"op": "exclude", "rows": [1]}], "g")                      # a reason is required

    def test_by_group(self):
        d0 = DS.from_columns("g", [{"key": "y", "name": "y", "unit": "m", "values": [1, 1.1, 0.9, 1, 5, 20, 21, 19, 20, 20]},
                                   {"key": "g", "name": "g", "dtype": "text", "role": "group", "values": list("AAAAABBBBB")}])
        ds = D.derive(d0, [{"op": "outliers", "method": "dixon", "col": "y", "by": "g", "alpha": 0.05}], "g")
        self.assertEqual([f["row"] for f in ds.header["flags"]], [4])

    def test_checks(self):
        d0 = DS.from_columns("c", [{"key": "t", "name": "t", "unit": "s", "role": "x", "values": [0, 1, 2, 10, 11, 9]},
                                   {"key": "m", "name": "m", "unit": "mg", "kind": "mass", "values": [5, 4, -1, 3, None, 2]},
                                   {"key": "a", "name": "A", "unit": "", "values": [1, 2, 3, 4, 5, 6]},
                                   {"key": "g", "name": "g", "dtype": "text", "role": "group", "values": list("aaabbc")}])
        ch = {c["key"]: c for c in C.checks(d0)}
        self.assertEqual(ch["missing"]["level"], "warn")
        self.assertEqual(ch["monotonic"]["level"], "warn")
        self.assertIn("Lücke", ch["gaps"]["text"])
        self.assertEqual(ch["impossible:m"]["level"], "bad")
        self.assertIn("A", ch["units"]["text"])
        self.assertEqual(ch["groups:g"]["level"], "warn")


if __name__ == "__main__":
    unittest.main()
