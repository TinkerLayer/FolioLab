"""Known-answer tests for the scientific fixes of module 0.13.0 (kinetics, Student t, onset, ASTM D7582, readers,
replicate statistics, report citations).

Reference values are analytic or come from independent code (scipy, used in tests only, never at run time):
- Student t: scipy.stats.t.ppf(0.975, df).
- Kinetics: conversion curves generated outside the module, by the exact temperature integral of a first-order
  reaction (T·E₂(E/RT), scipy.special.expn) and by numerical integration of dα/dT = (A/β)·exp(−E/RT)·f(α) with
  scipy.integrate.solve_ivp for F2 and A2; none of the module's approximations (Senum–Yang, Doyle) is used to
  generate the data.
- Onset: a step with compact support m(T) = 100 − L·S((T − T0)/h), S'(u) = 15/16·(1 − u²)², whose inflection
  tangent meets the flat baselines exactly at T0 ∓ 8h/15.

    python -m unittest discover -s tests      (in modules/tga)
"""
from __future__ import annotations

import base64
import io
import math
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "sdk" / "python"))

from tga import composition as CO  # noqa: E402
from tga import kinetics as KI  # noqa: E402
from tga import process as PR  # noqa: E402
from tga import readers as RD  # noqa: E402
from tga import refs as RF  # noqa: E402
from tga import steps as ST  # noqa: E402
from tga import synth as SY  # noqa: E402
from tga import tdist  # noqa: E402
from tga.readers import Run  # noqa: E402

try:
    import scipy  # noqa: F401
    from scipy import stats
    from scipy.integrate import solve_ivp
    from scipy.special import expn
    HAVE_SCIPY = True
except ImportError:  # pragma: no cover
    HAVE_SCIPY = False

R = 8.314462618
E_TRUE = 150e3          # J/mol
A_TRUE = 1e10           # 1/s
RATES = (2.0, 5.0, 10.0, 20.0)


def bfile(b, name):
    return base64.b64decode(b["files"].get(name, "")).decode("utf-8")


def kinetic_runs(model: str):
    """Runs at 2/5/10/20 K/min, m = 10·(1 − 0.9 α), α from the exact solution (independent of the module)."""
    out = []
    for b in RATES:
        T = np.arange(150.0, 650.0, 0.05)
        Tk = T + 273.15
        k = A_TRUE * 60.0 / b                                   # 1/K: A [1/s]·60 / β [K/min]
        if model == "F1":
            a = 1 - np.exp(-k * Tk * expn(2, E_TRUE / (R * Tk)))   # ∫₀ᵀ e^(−E/RT') dT' = T·E₂(E/RT)
        else:
            f = {"F2": lambda x: (1 - x) ** 2,
                 "A2": lambda x: 2 * (1 - x) * math.sqrt(max(-math.log(max(1 - x, 1e-300)), 0.0)) + 1e-12}[model]
            s = solve_ivp(lambda TT, y: [k * math.exp(-E_TRUE / (R * TT)) * f(min(y[0], 1 - 1e-15))],
                          (Tk[0], Tk[-1]), [1e-9], t_eval=Tk, rtol=1e-10, atol=1e-13, method="LSODA")
            a = s.y[0]
        out.append(Run(f"{model} {b:g} K/min", T, 10.0 * (1 - 0.9 * a), "mg", (T - T[0]) / b, 10.0, {"rate": b}))
    return out


@unittest.skipUnless(HAVE_SCIPY, "scipy needed for the independent reference values")
class StudentT(unittest.TestCase):
    def test_table_matches_scipy(self):
        # Expected: scipy.stats.t.ppf(0.975, df); table rounded to 6 decimals.
        for df, v in tdist.T975.items():
            self.assertAlmostEqual(v, stats.t.ppf(0.975, df), delta=1e-6, msg=df)
        self.assertAlmostEqual(tdist.T975_INF, stats.norm.ppf(0.975), delta=1e-6)

    def test_interpolation_in_inverse_df(self):
        # Linear interpolation in 1/df between 30, 40, 60, 120, inf: within 1e-4 of scipy.
        for df in (35, 45, 50, 80, 100, 200, 1000, 10 ** 6):
            self.assertAlmostEqual(tdist.t95(df), stats.t.ppf(0.975, df), delta=1e-4, msg=df)
        self.assertTrue(math.isnan(tdist.t95(0)))

    def test_kinetics_uses_exact_t(self):
        # 4 runs -> 2 degrees of freedom -> t = 4.302653 (scipy), not an approximation; 13 runs -> 11 df -> 2.200985
        # (the old code used 2.0 for 11-30 df).
        convs = [KI.conversion(r, 150, 640) for r in kinetic_runs("F1")]
        iso = KI.isoconversional(convs)
        self.assertAlmostEqual(iso["t95"], stats.t.ppf(0.975, 2), delta=1e-6)
        self.assertAlmostEqual(tdist.t95(11), stats.t.ppf(0.975, 11), delta=1e-6)
        row = next(r for r in iso["methods"]["kas"] if abs(r["alpha"] - 0.5) < 1e-9)
        x = 1 / np.array(row["T"])
        y = np.log(np.array(RATES) / np.array(row["T"]) ** 2)
        slope, icpt = np.polyfit(x, y, 1)
        se = math.sqrt(np.sum((y - (slope * x + icpt)) ** 2) / 2 / np.sum((x - x.mean()) ** 2))
        exp_ci = stats.t.ppf(0.975, 2) * se * R / 1000
        self.assertAlmostEqual(row["ci"], exp_ci, delta=1e-6 * exp_ci)       # table t has 6 decimals


@unittest.skipUnless(HAVE_SCIPY, "scipy needed for the independent reference values")
class KineticsKnownAnswer(unittest.TestCase):
    """Eₐ = 150 kJ/mol, A = 1e10 1/s, β = 2/5/10/20 K/min, noise-free; window 150–640 °C."""

    TOL = 0.005 * 150          # 0.5 % of the true Eₐ

    @classmethod
    def setUpClass(cls):
        cls.res = {m: KI.run_all(kinetic_runs(m), 150, 640) for m in ("F1", "F2", "A2")}

    def test_isoconversional_methods_recover_ea(self):
        # Expected 150 kJ/mol (generating value) for every model; mean over alpha = 0.1-0.9, tolerance 0.5 %.
        for model, res in self.res.items():
            for m in ("friedman", "ofw", "kas", "starink", "vyazovkin"):
                self.assertAlmostEqual(res["iso"]["summary"][m]["mean"], 150.0, delta=self.TOL, msg=f"{model} {m}")

    def test_kissinger_first_order(self):
        # Kissinger's equation is derived for first order: 150 kJ/mol within 0.5 %.
        self.assertAlmostEqual(self.res["F1"]["kissinger"]["E"], 150.0, delta=self.TOL)

    def test_master_plot_finds_model(self):
        for model, res in self.res.items():
            self.assertEqual(res["model"], model)

    def test_ofw_iteration_removes_doyle_bias(self):
        # E1641 iteration: within 0.5 %; constant 1.052 (option "doyle"): biased by more than +1 % here
        # (x = E/RT ≈ 28-31, where the exact factor b(x) ≈ 1.065 > 1.052).
        convs = sorted([KI.conversion(r, 150, 640) for r in kinetic_runs("F1")], key=lambda c: c["beta"])
        it = KI.isoconversional(convs)["summary"]["ofw"]["mean"]
        doyle = KI.isoconversional(convs, ofw="doyle")["summary"]["ofw"]["mean"]
        self.assertAlmostEqual(it, 150.0, delta=self.TOL)
        self.assertGreater(doyle - 150.0, 1.5)

    def test_senum_yang_against_exact_temperature_integral(self):
        # p(x) = E₂(x)/x exactly (scipy); Senum–Yang 4th degree: relative error < 1e-6 for x ≥ 10, < 5e-5 at x = 5.
        for x in (10.0, 15.0, 20.0, 30.0, 45.0, 60.0):
            self.assertAlmostEqual(float(KI.senum_yang(x)) / (expn(2, x) / x), 1.0, delta=1e-6, msg=x)
        self.assertAlmostEqual(float(KI.senum_yang(5.0)) / (expn(2, 5.0) / 5.0), 1.0, delta=5e-5)

    def test_ofw_factor_equals_exact_derivative(self):
        # b(x) = −d ln p/dx with the exact p(x) = E₂(x)/x (scipy), central difference; within 2e-5 for x = 10…60.
        for x in (10.0, 20.0, 30.0, 45.0, 60.0):
            h = 1e-4
            lp = lambda z: math.log(expn(2, z) / z)  # noqa: E731
            exact = -(lp(x + h) - lp(x - h)) / (2 * h)
            self.assertAlmostEqual(KI.ofw_b(x), exact, delta=2e-5, msg=x)
        self.assertAlmostEqual(KI.ofw_b(37.0), 1.052, delta=0.002)     # Doyle's constant corresponds to x ≈ 37

    def test_toop_lifetime_first_order(self):
        # Exact first-order life: t_f = −ln(1 − α_f) / (A·exp(−E/RT)). At 300 °C (inside the measured range) the
        # Toop estimate must agree within 5 % (an Eₐ error of 0.5 % alone gives ≈ 2.5 % here).
        res = KI.run_all(kinetic_runs("F1"), 150, 640, {"alpha_f": 0.1, "T_use": [300.0]})
        lt = res["lifetime"]
        self.assertEqual(lt["method"], "toop")
        exact_h = -math.log(1 - 0.1) / (A_TRUE * math.exp(-E_TRUE / (R * 573.15))) / 3600.0
        self.assertAlmostEqual(lt["rows"][0]["t_h"] / exact_h, 1.0, delta=0.05)
        # Temperature index is the inverse of the lifetime relation.
        res2 = KI.run_all(kinetic_runs("F1"), 150, 640, {"alpha_f": 0.1, "T_use": [300.0], "t_target_h": lt["rows"][0]["t_h"]})
        self.assertAlmostEqual(res2["lifetime"]["T_index"], 300.0, delta=1e-6)
        # The model-based option still exists.
        res3 = KI.run_all(kinetic_runs("F1"), 150, 640, {"alpha_f": 0.1, "T_use": [300.0], "lifetime": "model"})
        self.assertEqual(res3["lifetime"]["method"], "model")
        self.assertAlmostEqual(res3["lifetime"]["rows"][0]["t_h"] / exact_h, 1.0, delta=0.1)


class OnsetKnownAnswer(unittest.TestCase):
    T0, H, L = 400.0, 30.0, 40.0

    def run_with(self, rate_fn):
        T = np.arange(200.0, 600.0, 0.05)
        u = np.clip((T - self.T0) / self.H, -1, 1)
        m = 100 - self.L * (0.5 + 15 / 16 * (u - 2 * u ** 3 / 3 + u ** 5 / 5))
        r = rate_fn(T)
        t = np.concatenate([[0.0], np.cumsum(np.diff(T) / ((r[1:] + r[:-1]) / 2))])
        return Run("step", T, m, "%", t, None, {"rate": 10.0})

    def check(self, run, tol):
        # Expected: tangent at u = 0 with slope −15L/(16h) meets m = 100 and m = 100 − L at T0 ∓ 8h/15 = 384 / 416 °C.
        T = run.T
        a = int(np.searchsorted(T, self.T0 - 1.2 * self.H))
        b = int(np.searchsorted(T, self.T0 + 1.2 * self.H))
        s = ST.characterise(run, a, b)
        self.assertAlmostEqual(s["T_onset"], self.T0 - 8 * self.H / 15, delta=tol)
        self.assertAlmostEqual(s["T_endset"], self.T0 + 8 * self.H / 15, delta=tol)
        self.assertAlmostEqual(s["T_inflection"], self.T0, delta=0.1)
        return s

    def test_constant_heating_rate(self):
        self.check(self.run_with(lambda T: np.full_like(T, 10.0)), 0.1)

    def test_variable_heating_rate_uses_local_slope(self):
        # Heating rate rises from 5 to 20 K/min across the step: the step-average rate (old method) gave
        # 389.3 / 413.5 °C; the local slope dm/dT gives the true values.
        s = self.check(self.run_with(lambda T: 5 + 15 / (1 + np.exp(-(T - self.T0) / 10))), 0.1)
        self.assertGreater(s["T_peak"], self.T0 + 2)          # the dm/dt peak is shifted; the tangent does not use it


class D7582Basis(unittest.TestCase):
    """Synthetic proximate analysis: moisture 5 %, volatiles 30 % (N₂ to 950 °C), fixed carbon 50 % (burns after the
    switch to air at 950 °C), ash 15 %, all of the sample as weighed (as-determined)."""

    @classmethod
    def setUpClass(cls):
        t1, T1 = SY.program([("ramp", 950, 20.0)])
        u1 = np.clip((T1 - 70) / 30, -1, 1)
        u2 = np.clip((T1 - 500) / 200, -1, 1)
        S = lambda u: 0.5 + 15 / 16 * (u - 2 * u ** 3 / 3 + u ** 5 / 5)  # noqa: E731
        m1 = 100 - 5 * S(u1) - 30 * S(u2)
        t2 = np.arange(0.05, 30.0, 0.05)
        m2 = 15 + 50 * np.exp(-np.maximum(t2 - 1.0, 0.0) / 2.0)   # burning starts 1 min after the switch
        t = np.concatenate([t1, t1[-1] + t2])
        T = np.concatenate([T1, np.full(len(t2), 950.0)])
        m = np.concatenate([m1, m2]) / 10.0               # mg, m0 = 10 mg
        gas = ["N₂"] * len(t1) + ["Luft"] * len(t2)
        cls.raw = SY.csv_text("Kohle (synthetisch)", t, T, m, 10.0, 20, gas).encode("utf-8")

    def test_as_determined_and_dry(self):
        run = RD.load_bytes(self.raw, "kohle.csv")[0]
        c = CO.compose(run, "d7582")
        got = {r["name"]: r for r in c["rows"]}
        # Expected as-determined: M 5, VM 30, FC = 100 − (5 + 30 + 15) = 50, A 15 (ash: last points, 15 + 50·e^(−14.5)).
        self.assertAlmostEqual(got["Feuchte"]["pct"], 5.0, delta=0.01)
        self.assertAlmostEqual(got["Flüchtige Bestandteile"]["pct"], 30.0, delta=0.01)
        self.assertAlmostEqual(got["Asche"]["pct"], 15.0, delta=0.01)
        self.assertAlmostEqual(got["Fixer Kohlenstoff (Differenz)"]["pct"], 50.0, delta=0.02)
        # Dry basis: X·100/(100 − M) -> VM 31.579, FC 52.632, A 15.789.
        self.assertAlmostEqual(got["Flüchtige Bestandteile"]["dry"], 3000 / 95, delta=0.02)
        self.assertAlmostEqual(got["Fixer Kohlenstoff (Differenz)"]["dry"], 5000 / 95, delta=0.03)
        self.assertAlmostEqual(got["Asche"]["dry"], 1500 / 95, delta=0.02)
        self.assertIsNotNone(c["basis"])

    def test_reference_mass_not_at_start_is_rescaled(self):
        # Reference mass at 120 °C (= 95 % of the sample): without rescaling moisture would be 5.26 and FC
        # 100 − (5.26 + 31.58 + 15.79) = 47.4 (bases mixed). Expected: the same as-determined values as above.
        run = RD.load_bytes(self.raw, "kohle.csv")[0]
        p = PR.apply(run, [{"op": "ref_mass", "mode": "at_T", "T": 120}])
        c = CO.compose(p.run, "d7582")
        got = {r["name"]: r["pct"] for r in c["rows"]}
        self.assertAlmostEqual(got["Feuchte"], 5.0, delta=0.02)
        self.assertAlmostEqual(got["Fixer Kohlenstoff (Differenz)"], 50.0, delta=0.05)
        self.assertAlmostEqual(sum(got.values()), 100.0, delta=1e-9)
        self.assertTrue(any("umgerechnet" in w for w in c["warnings"]))


class ReaderFixes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        t, T, m = SY.oxalate()
        cls.t, cls.T, cls.m = t[::4], T[::4], m[::4]

    def test_perkinelmer_prefers_corrected_weight(self):
        # Corrected weight = unsubtracted − 0.2 mg; the corrected column must be read and named.
        head = ["Sample ID: Oxalat", "Sample Weight: 10.000 mg",
                "Time (min)\tUnsubtracted Weight (mg)\tBaseline Weight (mg)\tWeight (mg)\tProgram Temp. (°C)\tSample Temp. (°C)"]
        body = [f"{a:.4f}\t{c + 0.2:.5f}\t0.2\t{c:.5f}\t{b + 0.7:.3f}\t{b:.3f}" for a, b, c in zip(self.t, self.T, self.m)]
        run = RD.load_bytes("\n".join(head + body).encode("utf-8"), "pyris.txt")[0]
        np.testing.assert_allclose(run.mg(), self.m, atol=1e-4)
        self.assertEqual(run.meta["m_column"], "Weight [mg]")
        self.assertTrue(any("korrigierten" in n for n in run.meta["read_notes"]))

    def test_perkinelmer_unsubtracted_only_is_flagged(self):
        head = ["Sample Weight: 10.000 mg", "Time (min)\tUnsubtracted Weight (mg)\tBaseline Weight (mg)\tSample Temp. (°C)"]
        body = [f"{a:.4f}\t{c:.5f}\t0\t{b:.3f}" for a, b, c in zip(self.t, self.T, self.m)]
        run = RD.load_bytes("\n".join(head + body).encode("utf-8"), "pyris.txt")[0]
        self.assertTrue(any("ohne Leerkurvenkorrektur" in n for n in run.meta["read_notes"]))

    def test_kelvin_without_unit(self):
        # Column without unit starting at 298 -> Kelvin (expected T = values − 273.15) with a note.
        txt = "Zeit;Temp;Masse\n" + "\n".join(f"{a:.4f};{b + 273.15:.3f};{c:.5f}" for a, b, c in zip(self.t, self.T, self.m)) + "\n"
        run = RD.load_bytes(txt.encode(), "k.csv", {"t": 0, "T": 1, "m": 2, "m_unit": "mg", "t_unit": "min"})[0]
        np.testing.assert_allclose(run.T, self.T, atol=0.01)
        self.assertTrue(any("Kelvin" in n for n in run.meta["read_notes"]))
        # Name says K -> Kelvin as well.
        txt2 = "Time;Temperature K;Mass\n" + "\n".join(f"{a:.4f};{b + 273.15:.3f};{c:.5f}" for a, b, c in zip(self.t, self.T, self.m)) + "\n"
        run2 = RD.load_bytes(txt2.encode(), "k2.csv", {"t": 0, "T": 1, "m": 2, "m_unit": "mg", "t_unit": "min"})[0]
        np.testing.assert_allclose(run2.T, self.T, atol=0.01)
        # An explicit °C in the mapping overrides the guess.
        run3 = RD.load_bytes(txt.encode(), "k.csv", {"t": 0, "T": 1, "m": 2, "m_unit": "mg", "T_unit": "°C"})[0]
        np.testing.assert_allclose(run3.T, self.T + 273.15, atol=0.01)

    def test_trios_sheets_time_offset(self):
        try:
            import openpyxl
        except ImportError:
            self.skipTest("openpyxl fehlt")
        wb = openpyxl.Workbook()
        ws = wb.active
        half = len(self.t) // 2
        for k, sl in enumerate((slice(0, half), slice(half, None))):
            if k:
                ws = wb.create_sheet(f"Step {k + 1}")
            ws.append(["Time (min)", "Temperature (°C)", "Weight (mg)"])
            t0 = self.t[sl][0]
            for a, b, c in zip(self.t[sl], self.T[sl], self.m[sl]):
                ws.append([float(a - t0), float(b), float(c)])      # every sheet restarts at t = 0
        buf = io.BytesIO()
        wb.save(buf)
        run = RD.load_bytes(buf.getvalue(), "trios.xlsx")[0]
        self.assertEqual(run.meta["sheets"], 2)
        self.assertTrue(np.all(np.diff(run.t) > 0))                 # continuous and monotonic
        # Expected: second sheet starts one median step after the end of the first.
        dt = float(np.median(np.diff(self.t[:half])))
        self.assertAlmostEqual(run.t[half], (self.t[half - 1] - self.t[0]) + dt, delta=1e-6)


class ReportFixes(unittest.TestCase):
    def test_replicate_mean_from_full_precision(self):
        from labbundle import num

        from tga import bundle as B
        from tga.analysis import run as analyse
        items = []
        vals = []
        for b, seed_noise in ((10.0, 0.0005), (20.0, 0.0007)):
            t, T, m = SY.oxalate(beta=b, noise=seed_noise)
            raw = SY.csv_text(f"Ox {b:g}", t, T, m, 10.0, b).encode("utf-8")
            items.append((raw, f"ox{b:g}.csv", None, {}))
            a = analyse(RD.load_bytes(raw, f"ox{b:g}.csv")[0], {})
            vals.append(a.st["residue"]["end"])
        bd = B.build(items, {"items": [{"name": x[1]} for x in items]}, lang="en")
        tab = bfile(bd, "vergleich.tex")
        # Expected: mean and s of the unrounded residues.
        self.assertIn(f"{num(np.mean(vals), 2, 'en')} ± {num(np.std(vals, ddof=1), 2, 'en')}".replace("±", ""), tab.replace(r"$\pm$", "").replace("±", ""))

    def test_e1582_cited_where_calibration_is_used(self):
        from tga import bundle as B
        raw, name = SY.make("oxalat")[0]
        bd = B.build([(raw, name, None, {"pipeline": [{"op": "tcal", "a": 0.5, "b": 1.0}]})], {"items": [{"name": name}]}, lang="de")
        self.assertIn("tga-astm-e1582", bfile(bd, "text-methodik.tex"))
        self.assertIn("E1582", bfile(bd, "refs.bib"))

    def test_standards_without_year_are_marked(self):
        for k in ("astm-e1582", "astm-e2040", "astm-d7582", "astm-e967", "astm-e793"):
            self.assertNotIn("year", RF.REFS[k])
            self.assertIn("current edition", RF.REFS[k]["note"])

    def test_kinetics_report_cites_matching_methods(self):
        from tga import bundle as B
        items = [(d, n, None, {}) for d, n in SY.make("kinetik")]
        bd = B.build(items, {"items": [{"name": n} for _, n, _, _ in items], "kinetics": {"T_lo": 300, "T_hi": 600}}, lang="de")
        bib = bfile(bd, "refs.bib")
        txt = bfile(bd, "text-methodik.tex")
        self.assertIn("1997", bib)
        self.assertIn("arbitrary variation of temperature", bib)
        self.assertNotIn("Modification of the integral isoconversional method", bib)
        self.assertIn("Toop", bib)
        self.assertIn("nicht gegen den Text der Norm", txt)
        self.assertIn("E1641 iterativ", txt.replace("~", " "))


if __name__ == "__main__":
    unittest.main()
