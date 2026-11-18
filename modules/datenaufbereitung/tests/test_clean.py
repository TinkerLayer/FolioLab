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


class ScientificFixesTest(unittest.TestCase):
    """Module 0.3.0: known answers for the corrected outlier rules, flags of means, signed quantities, ± type."""

    def test_dixon_untabulated_alpha_refused_and_sides(self):
        x = [0.189, 0.167, 0.187, 0.183, 0.186, 0.182, 0.181, 0.184, 0.181, 0.177]
        for a in (0.02, 0.2, 0.001):                                   # was: silently the 0.05 column
            with self.assertRaisesRegex(C.CleanError, "nicht tabelliert"):
                C.dixon(x, a)
        with self.assertRaisesRegex(C.CleanError, "nicht tabelliert"):
            C.dixon(x, 0.01, "max")                                    # one-sided: 0.05, 0.025, 0.005 only
        # two-sided: only the end with the larger ratio (low end, Q = 0.455); high end Q = 0.002/0.022 = 0.091
        self.assertEqual([d["i"] for d in C.dixon(x, 0.10)], [1])
        self.assertEqual(C.dixon(x, 0.05, "max"), [])
        # one-sided min at α = 0.05 uses the two-sided 0.10 column: Q = 0.4545 > 0.412
        r = C.dixon(x, 0.05, "min")
        self.assertEqual(([d["i"] for d in r], r[0]["crit"]), ([1], 0.412))
        self.assertEqual(C.dixon(x, 0.025, "min"), [])                 # 0.05 column: 0.466
        # both ends beyond Q_crit (n = 10, α = 0.10: 0.412): Q_low = 4.5/10 = 0.45, Q_high = 4.6/10 = 0.46. Before 0.3.0
        # both ends were tested at the two-sided α and both flagged; now only the end with the larger ratio
        y = [0.0, 4.5, 4.7, 4.9, 5.0, 5.1, 5.2, 5.3, 5.4, 10.0]
        r = C.dixon(y, 0.10)
        self.assertEqual([d["i"] for d in r], [9])
        self.assertAlmostEqual(r[0]["Q"], 0.46)
        with self.assertRaises(C.CleanError):
            C.dixon(x, 0.05, "beide")

    def test_dixon_table_matches_null_distribution(self):
        """Independent check of DIXON_Q (not of the publication): for normal data
        P(Q_high > c) = n(n−1) ∫∫_{a<b} φ(a) φ(b) [Φ(b − c(b − a)) − Φ(a)]^(n−2) da db, two-sided α ≈ 2 P (the overlap
        of both ends is below 1e-4 here). The true critical value lies within ±0.003 of every table value, except
        n = 4, α = 0.01 where it is ≈ 0.921 (table 0.926; noted in clean.py and on the methods page)."""
        try:
            from scipy.special import ndtr
        except ImportError:
            self.skipTest("scipy nicht installiert")
        g = np.linspace(-7, 7, 1001)
        h = g[1] - g[0]
        A, B = np.meshgrid(g, g, indexing="ij")
        phi = np.exp(-g * g / 2) / math.sqrt(2 * math.pi)
        W = np.outer(phi, phi) * (B > A) * h * h
        PA = ndtr(A)

        def alpha2(c, n):
            return 2 * n * (n - 1) * float((W * np.clip(ndtr(B - c * (B - A)) - PA, 0, None) ** (n - 2)).sum())
        for a, col in C.DIXON_Q.items():
            for n, crit in zip(range(3, 11), col):
                if (n, a) == (4, 0.01):
                    self.assertGreater(alpha2(0.918, n), a)                # true value between 0.918 and 0.924
                    self.assertLess(alpha2(0.924, n), a)
                    continue
                self.assertGreater(alpha2(crit - 0.003, n), a, (n, a))
                self.assertLess(alpha2(crit + 0.003, n), a, (n, a))

    def test_grubbs_sequential_and_single_pass(self):
        x = [199.31, 199.53, 200.19, 200.82, 201.92, 201.95, 202.18, 245.57]       # NIST example (see above)
        self.assertEqual([d["i"] for d in C.grubbs(x, 0.05, "max", iterate=False)], [7])
        self.assertEqual([d["i"] for d in C.grubbs(x, 0.05, "max")], [7])          # 2nd step not significant
        d0 = DS.from_columns("g", [{"key": "x", "name": "x", "unit": "mg", "values": x}])
        ds = D.derive(d0, [{"op": "outliers", "method": "grubbs", "col": "x", "sided": "max"}], "g")
        self.assertIn("je Schritt", ds.header["flags"][0]["rule"])
        self.assertIn("sequenziell", ds.header["flags"][0]["rule"])
        ds = D.derive(d0, [{"op": "outliers", "method": "grubbs", "col": "x", "sided": "max", "iterate": False}], "g")
        self.assertIn("ein Durchgang", ds.header["flags"][0]["rule"])
        self.assertEqual(len(ds.header["flags"]), 1)

    def test_iqr_quartiles_are_hyndman_fan_type_7(self):
        # x = 1 … 8 and 30: type 7 quartiles Q1 = 3, Q3 = 7 (h = (n − 1) p + 1 → positions 3 and 7);
        # fences 3 − 1.5·4 = −3 and 7 + 6 = 13 → only 30 flagged. Tukey's hinges would give 3 and 7 here too, but for
        # n = 8 (1 … 8) type 7 gives 2.75 / 6.25 while the hinges are 2.5 / 6.5.
        x = [1, 2, 3, 4, 5, 6, 7, 8, 30]
        res, lo, hi = C.iqr(x)
        self.assertEqual(([d["i"] for d in res], lo, hi), ([8], -3.0, 13.0))
        _, lo8, hi8 = C.iqr(list(range(1, 9)), 1.0)
        self.assertAlmostEqual(lo8, 2.75 - 3.5)
        self.assertAlmostEqual(hi8, 6.25 + 3.5)
        d0 = DS.from_columns("i", [{"key": "x", "name": "x", "unit": "mg", "values": x}])
        ds = D.derive(d0, [{"op": "outliers", "method": "iqr", "col": "x"}], "i")
        self.assertIn("Hyndman", ds.header["flags"][0]["rule"])

    def test_hampel_window_in_x_units(self):
        """Uneven spacing: a window of ±1.5 x-units holds other neighbours than ±1 position."""
        xs = np.array([0, 1, 2, 3, 10, 11, 12, 13, 14.0])
        y = np.array([1.0, 1.1, 0.9, 1.0, 5.0, 5.1, 4.9, 5.0, 9.0])
        # by x (±2): the last point (x = 14) sees x = 12, 13, 14 → y 4.9, 5.0, 9.0: median 5.0,
        # MAD = 1.4826 · median(0.1, 0, 4.0) = 0.148; |9.0 − 5.0| = 4.0 > 3 · 0.148 → flagged; no other point is
        r = C.hampel(y, 3.0, 2.0, xs)
        self.assertEqual([d["i"] for d in r], [8])
        self.assertAlmostEqual(r[0]["med"], 5.0)
        self.assertAlmostEqual(r[0]["mad"], 1.4826 * 0.1)
        self.assertEqual(r[0]["n"], 3)
        # by x (±1.5): the last point sees only x = 13, 14 → median 7.0, MAD 2.97 → not flagged
        self.assertEqual(C.hampel(y, 3.0, 1.5, xs), [])
        d0 = DS.from_columns("h", [{"key": "t", "name": "t", "unit": "s", "role": "x", "values": xs},
                                   {"key": "y", "name": "y", "unit": "V", "values": y}])
        ds = D.derive(d0, [{"op": "outliers", "method": "hampel", "col": "y", "k": 3, "window": 2.0, "x": "t"}], "h")
        self.assertEqual([f["row"] for f in ds.header["flags"]], [8])
        self.assertIn("in „t“", ds.header["flags"][0]["rule"])
        ds = D.derive(d0, [{"op": "outliers", "method": "hampel", "col": "y", "window": 1}], "h")
        self.assertIn("x-Abstand nicht berücksichtigt", ds.header["provenance"]["steps"][0]["text"])

    def test_residual_rule_text(self):
        t = np.arange(10.0)
        y = 2 * t + 1 + np.array([0.1, -0.1, 0.05, -0.05, 6, 0.1, -0.1, 0.05, -0.05, 0])
        d0 = DS.from_columns("r", [{"key": "t", "name": "t", "unit": "s", "role": "x", "values": t},
                                   {"key": "y", "name": "y", "unit": "V", "values": y}])
        ds = D.derive(d0, [{"op": "outliers", "method": "residual", "col": "y", "x": "t", "k": 2.5}], "r")
        rule = ds.header["flags"][0]["rule"]
        self.assertIn("extern studentisiertes Residuum", rule)
        self.assertIn("Faustregel", rule)
        with self.assertRaises(D.DeriveError):
            D.derive(d0, [{"op": "outliers", "method": "iqr", "col": "y", "k": -1}], "r")

    def test_replicate_means_keep_flags(self):
        d0 = DS.from_columns("r", [{"key": "T", "name": "T", "unit": "°C", "kind": "temperature", "role": "x",
                                    "values": [25, 25, 25, 35, 35, 45]},
                                   {"key": "k", "name": "k", "unit": "1/s", "role": "y", "values": [1.0, 1.2, 1.4, 2.0, None, 3.0]}],
                             flags=[{"row": 1, "col": "k", "code": "outlier", "rule": "Grubbs (α = 0,05)"},
                                    {"row": 2, "code": "excluded", "excluded": True, "reason": "Fehlmessung"},
                                    {"row": 4, "col": "k", "code": "missing"},
                                    {"row": 5, "col": "k", "code": "below_lod"}])
        ds = D.derive(d0, [{"op": "replicates", "by": ["T"], "cols": ["k"]}], "r")
        np.testing.assert_allclose(ds.data["k"], [1.1, 2.0, 3.0])
        fl = [(f["row"], f.get("col"), f["code"], f["reason"]) for f in ds.header["flags"]]
        self.assertEqual(fl, [(0, "k", "outlier", "aus Zeile(n) 2"), (2, "k", "below_lod", "aus Zeile(n) 6")])
        self.assertIn("Grubbs", ds.header["flags"][0]["rule"])
        self.assertEqual(ds.col("k_se")["u_type"], "se")
        self.assertIn("2 Markierung(en) auf die Mittelwerte übertragen", ds.header["provenance"]["steps"][0]["text"])

    def test_signed_quantities_not_impossible(self):
        d0 = DS.from_columns("s", [
            {"key": "dL", "name": "ΔL", "unit": "mm", "values": [0.1, -0.2]},
            {"key": "x", "name": "Position", "unit": "mm", "values": [-5, 3]},
            {"key": "dm", "name": "Massenänderung", "unit": "mg", "kind": "mass", "values": [-0.5, 0.2]},
            {"key": "m", "name": "Masse", "unit": "mg", "kind": "mass", "values": [-1, 2]},
            {"key": "rho", "name": "Dichte", "unit": "g/cm³", "kind": "density", "values": [-1, 2]}])
        ch = {c["key"] for c in C.checks(d0)}
        self.assertNotIn("impossible:dL", ch)                          # length: signed (positions, ΔL)
        self.assertNotIn("impossible:x", ch)
        self.assertNotIn("impossible:dm", ch)                          # a change of a mass
        self.assertIn("impossible:m", ch)
        self.assertIn("impossible:rho", ch)                            # "Dichte" is not a "d…" difference
        self.assertTrue(C.signed_name({"name": "dT"}) and C.signed_name({"name": "Delta T"}))
        self.assertFalse(C.signed_name({"name": "dichte"}) or C.signed_name({"name": "Druck"}))

    def test_uncertainty_type_chip(self):
        d0 = DS.from_columns("u", [{"key": "m", "name": "m", "unit": "g", "u": "um", "values": [1.0]},
                                   {"key": "um", "name": "U(m)", "unit": "g", "role": "uncertainty", "values": [0.1],
                                    "u_type": "U", "u_k": 2}])
        ch = {c["key"]: c for c in C.checks(d0)}
        self.assertEqual(ch["utype:um"]["level"], "info")
        self.assertIn("k = 2", ch["utype:um"]["text"])
        d1 = DS.from_columns("u", [{"key": "m", "name": "m", "unit": "g", "u": "um", "values": [1.0]},
                                   {"key": "um", "name": "u(m)", "unit": "g", "role": "uncertainty", "values": [0.1]}])
        ch = {c["key"]: c for c in C.checks(d1)}
        self.assertEqual((ch["utype:um"]["level"], ch["utype:um"]["text"]), ("warn", "„u(m)“: nicht angegeben"))


def csv_sheet(text):
    return R.load_bytes(text.encode("utf-8"), "t.csv")[0]


class TimesAndReadingTest(unittest.TestCase):
    """Time zones and daylight saving, truncations reported, ± type from the recipe."""

    def test_offsets_are_converted_to_utc(self):
        utc = (dt.datetime(2024, 3, 30, 23, 30) - dt.datetime(1970, 1, 1)).total_seconds()
        self.assertEqual(P.time_of("2024-03-31T00:30+01:00"), (utc, False))
        self.assertEqual(P.time_of("2024-03-30T23:30Z"), (utc, False))
        self.assertEqual(P.time_of("2024-03-30 23:30:00 +0000")[0], utc)
        self.assertEqual(P.time_of("2024-03-31 00:30")[0], utc + 3600)          # no zone: wall-clock time as written
        vals, only, tz = P.time_column(["2024-03-31T01:30+01:00", "2024-03-31T03:00+02:00", "2024-03-31T03:30+02:00"])
        self.assertEqual(tz, "utc")
        np.testing.assert_allclose(np.diff(vals), [1800, 1800])                 # across the change: 30 min steps
        self.assertEqual(P.time_column(["2024-03-31T01:30+01:00", "2024-03-31 03:00"])[2], "mixed")
        self.assertEqual(P.dst_dates(2024)[0][0], dt.date(2024, 3, 31))          # EU: last Sunday of March

    def test_dst_jump_in_local_times_is_warned(self):
        text = "Zeit;c\n2024-03-31 01:00;1\n2024-03-31 01:30;2\n2024-03-31 03:00;3\n2024-03-31 03:30;4\n2024-03-31 04:00;5\n"
        sh = csv_sheet(text)
        steps = RC.guess(sh)
        t = RC.extract(sh, steps)
        z = col(t, "Zeit")
        self.assertTrue(any("1 h" in w for w in z["tz_warn"]), z["tz_warn"])
        self.assertTrue(any("31.03.2024" in w for w in z["tz_warn"]))
        self.assertTrue(any("ACHTUNG" in n for n in t["notes"]))
        ds = RC.to_dataset(t, "DST", [], steps, "x")
        self.assertTrue(ds.header["provenance"]["warnings"])
        self.assertIn("Ortszeit", ds.col("Zeit")["note"] if ds.col("Zeit").get("note") else " ".join(t["notes"]))
        # the same instants with offsets: UTC, steps of 30 min, no warning
        text2 = ("Zeit;c\n2024-03-31T01:00+01:00;1\n2024-03-31T01:30+01:00;2\n2024-03-31T03:00+02:00;3\n"
                 "2024-03-31T03:30+02:00;4\n")
        sh2 = csv_sheet(text2)
        t2 = RC.extract(sh2, RC.guess(sh2))
        z2 = col(t2, "Zeit")
        self.assertEqual(z2["tz_warn"], [])
        np.testing.assert_allclose(z2["values"], [0, 30, 60, 90])
        self.assertTrue(z2["elapsed"].endswith("UTC"))

    def test_flag_truncation_is_reported(self):
        text = "x;y\n" + "".join(f"{i};n.d.\n" if i % 2 else f"{i};{i},5\n" for i in range(12))   # 6 × n.d.
        sh = csv_sheet(text)
        steps = RC.guess(sh)
        old = RC.MAX_CELL_FLAGS
        RC.MAX_CELL_FLAGS = 3
        try:
            t = RC.extract(sh, steps)
            ds = RC.to_dataset(t, "kurz", [], steps, "x")
        finally:
            RC.MAX_CELL_FLAGS = old
        cut = ds.header["provenance"]["truncations"]
        self.assertEqual((cut[0]["kept"], cut[0]["total"], cut[0]["from_row"]), (3, 6, 8))
        self.assertTrue(any("GEKÜRZT" in n for n in t["notes"]))
        self.assertEqual(sum(1 for f in ds.header["flags"] if f["code"] == "missing"), 3)
        self.assertEqual(ds.rows, 12)                                         # the values themselves stay

    def test_uncertainty_type_from_recipe(self):
        sh = csv_sheet("t;T;m\r\n;°C;g\r\n08:00;25;1,5 ± 0,2\r\n08:30;25;2,5 ± 0,2\r\n09:00;26;3,5\r\n09:30;26;4,0 ± 0,3\r\n")
        steps = RC.guess(sh) + [{"op": "colprop", "series": 2, "u_type": "U", "u_k": 2}]
        t = RC.extract(sh, steps)
        ds = RC.to_dataset(t, "U", [], steps, "x")
        u = ds.col(ds.col("m")["u"])
        self.assertEqual((u["u_type"], u["u_k"]), ("U", 2.0))
        self.assertIn("k = 2", " ".join(x["text"] for x in C.checks(ds)))
        with self.assertRaises(RC.RecipeError):
            RC.extract(sh, RC.guess(sh) + [{"op": "colprop", "series": 2, "u_type": "U"}])          # k missing
        with self.assertRaises(RC.RecipeError):
            RC.extract(sh, RC.guess(sh) + [{"op": "colprop", "series": 2, "u_type": "2s"}])


if __name__ == "__main__":
    unittest.main()
