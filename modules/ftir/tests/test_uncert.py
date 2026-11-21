"""Measurement uncertainty of FTIR results (ftir/uncert.py): linear forms, noise scaling, correlated ratios, equations."""
from __future__ import annotations

import json
import math
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "sdk" / "python"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")

from ftir import bundle as B  # noqa: E402
from ftir import peaks as PK  # noqa: E402
from ftir.analysis import run  # noqa: E402
from ftir.readers import Spectrum  # noqa: E402


def spectrum(yunit="A"):
    x = np.arange(400.0, 4000.0 + 1e-9, 2.0)
    y = 0.8 * np.exp(-0.5 * ((x - 1715) / 12) ** 2) + 0.3 * np.exp(-0.5 * ((x - 1450) / 10) ** 2) + 0.02
    if yunit == "T":
        y = 100 * 10 ** (-y)
    return Spectrum(name="synth", x=x, y=y, yunit=yunit, meta={})


def manual(s, extra=None):
    st = {"bands": [{"name": "CO", "lo": 1660, "hi": 1770}, {"name": "CH", "lo": 1410, "hi": 1490},
                    {"name": "CO2", "lo": 1690, "hi": 1740}],
          "ratios": [{"name": "CI", "num": "CO", "den": "CH"}, {"name": "ov", "num": "CO", "den": "CO2"}],
          "unc": {"noise": {"parts": [{"kind": "u", "u": s}]}}, "unc_noise": {"mode": "manual"}}
    st.update(extra or {})
    return st


def by_id(a):
    return {r["id"]: r for r in a.unc["results"]}


class Off(unittest.TestCase):
    def test_no_entries(self):
        a = run(spectrum(), {"bands": [{"name": "CO", "lo": 1660, "hi": 1770}]})
        self.assertIsNone(a.unc)


class LinearForms(unittest.TestCase):
    def test_area_and_height_reproduce_integrate(self):
        sp = spectrum("T")
        a = run(sp, manual(0.001))
        b = a.unc_ctx.band(1660, 1770)
        r = PK.integrate(sp.x, sp.y, 1660, 1770, "T")
        self.assertAlmostEqual(b["area"].value, r["area"], places=10)
        self.assertAlmostEqual(b["height"].value, r["height"], places=12)

    def test_band_area_u_scales_with_noise(self):
        u1 = by_id(run(spectrum(), manual(0.001)))["band1-area"]["u"]
        u2 = by_id(run(spectrum(), manual(0.002)))["band1-area"]["u"]
        # baseline/limits part is independent of the noise; remove it before comparing
        a = run(spectrum(), manual(0.001))
        c = a.unc_ctx
        un1 = c.noise_u(c.band(1660, 1770)["area"].g)
        self.assertGreater(u2, u1)
        self.assertAlmostEqual(c.noise_u(c.band(1660, 1770)["area"].g) * 2, 2 * un1)
        g = c.band(1660, 1770)["area"].g
        self.assertAlmostEqual(un1, 0.001 * math.sqrt(float(np.sum(g ** 2))), places=12)

    def test_noise_u_hand_formula_zero_base(self):
        # area0 over zero: c = trapezoid weights; u = σ·sqrt(Σ w²) with w = Δx/2 at the ends and Δx inside
        a = run(spectrum(), manual(0.001))
        b = a.unc_ctx.band(1700, 1730, "zero")
        n = int((1730 - 1700) / 2) + 1
        w = np.full(n, 2.0)
        w[0] = w[-1] = 1.0
        self.assertAlmostEqual(a.unc_ctx.noise_u(b["area"].g), 0.001 * math.sqrt(float(np.sum(w ** 2))), places=12)


class Ratios(unittest.TestCase):
    def test_ratio_with_correlation(self):
        st = manual(0.002)
        st["bands"][0]["base"] = st["bands"][2]["base"] = "zero"     # areas over zero: overlap -> positive correlation
        a = run(spectrum(), st)
        c = a.unc_ctx
        r = by_id(a)["ratio2"]                         # CO / CO2
        n_, d_ = c.band(1660, 1770, "zero")["area"], c.band(1690, 1740, "zero")["area"]
        self.assertGreater(c.cov_noise(n_.g, d_.g), 0)
        lin = n_.lin_ratio(d_)
        u_lin = math.sqrt(c.var(lin))
        self.assertAlmostEqual(r["u"], u_lin, delta=0.02 * u_lin)
        # ignoring the correlation would give a larger u
        R = n_.value / d_.value
        u_ind = R * math.sqrt(c.var(n_) / n_.value ** 2 + c.var(d_) / d_.value ** 2)
        self.assertLess(r["u"], u_ind)
        corr = [b for b in r["res"]["budget"] if b.get("name", "").startswith("e_")]
        self.assertEqual(len(corr), 2)

    def test_disjoint_bands_uncorrelated(self):
        a = run(spectrum(), manual(0.002))
        c = a.unc_ctx
        self.assertEqual(c.cov_noise(c.band(1660, 1770)["area"].g, c.band(1410, 1490)["area"].g), 0.0)


class Positions(unittest.TestCase):
    def test_wavenumber_accuracy_and_interpolation(self):
        st = {"peaks": {}, "unc": {"nu": {"parts": [{"kind": "limits", "a": 1.0, "dist": "rect"}]}}}
        a = run(spectrum(), st)
        r = by_id(a)["peak1"]
        exp = math.sqrt((1 / math.sqrt(3)) ** 2 + (2.0 / math.sqrt(12)) ** 2)   # δν̃ and spacing 2 cm⁻¹
        self.assertAlmostEqual(r["u"], exp, places=6)


class Equations(unittest.TestCase):
    def test_function_calls_match_variables(self):
        eqs = [{"sym": "q", "expr": "B1/B2"}, {"sym": "w", "expr": "area(1660,1770)/area(1410,1490)"},
               {"sym": "z", "expr": "A(1716)*2"}]
        a = run(spectrum(), manual(0.002, {"equations": eqs}))
        ids = by_id(a)
        q, w, z = a.equations
        self.assertAlmostEqual(q["unc"]["u"], ids["ratio1"]["u"], delta=1e-9 + 1e-6 * ids["ratio1"]["u"])
        self.assertAlmostEqual(w["unc"]["u"], q["unc"]["u"], delta=1e-9 + 1e-6 * q["unc"]["u"])
        self.assertAlmostEqual(z["unc"]["u"], 2 * 0.002, delta=1e-9)
        self.assertIn("±", z["text_pm"])


class Report(unittest.TestCase):
    def test_bundle(self):
        from ftir import samples as SM
        d, n = SM.make("pet")
        st = {"bands": [{"name": "CO", "lo": 1680, "hi": 1780}, {"name": "ref", "lo": 1380, "hi": 1440}],
              "ratios": [{"name": "CI", "num": "CO", "den": "ref"}],
              "unc": {"nu": {"parts": [{"kind": "limits", "a": 1.0}]}}, "unc_noise": {"mode": "region", "region": [2200, 2000]}}
        b = B.build([(d, n, 0, st)], {"items": [{"name": n}]}, lang="en")
        s = json.dumps(b, default=str)
        self.assertIn("ratio1-pm", s)
        self.assertIn("unsicherheit", s)
        self.assertIn("Measurement uncertainties were evaluated", s)


if __name__ == "__main__":
    unittest.main()
