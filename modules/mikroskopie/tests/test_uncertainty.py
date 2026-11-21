"""Measurement uncertainty of the particle parameters (mikro/uncertainty.py on labcalc.uncertainty).

Synthetic sample image (imageio.sample_image, seed 7). Checks: the scale u (stage micrometer certificate U/k and
±1 px edge reading) propagates relatively into D50 and squared into the mean area; the count carries √N; a number
fraction the binomial u; the area fraction is scale-free; the bootstrap is reproducible (fixed seed); own equations
receive the u of the variables; series of fields (ASTM E562 style mean ± s/√n); the report bundle.
"""
import copy
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "sdk" / "python"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import numpy as np  # noqa: E402

from mikro import bundle  # noqa: E402
from mikro import uncertainty as UNC  # noqa: E402
from mikro.analysis import run  # noqa: E402
from mikro.imageio import load_bytes, sample_image  # noqa: E402

PIPE = [{"op": "background", "radius": 30}, {"op": "gauss", "sigma": 1.5},
        {"op": "threshold", "method": "otsu", "dark": True}, {"op": "fill"}]
L, N = 50.0, 200.0                       # Linie: 200 px entsprechen 50 µm → 0,25 µm/px
UNC_LINE = {"method": "gum", "cal": {"mode": "line", "L": L, "N": N},
            "specs": {"cal_len": {"parts": [{"kind": "U", "U": 0.5, "k": 2}]},          # Zertifikat: U = 0,5 µm, k = 2
                      "cal_px": {"parts": [{"kind": "limits", "a": 1, "dist": "rect"}]}}}   # Kantenablesung ±1 px


def state(unc=UNC_LINE, size_min=2, **kw):
    return {"pipeline": PIPE, "particles": {"size_min": size_min}, "calib": {"pw": L / N, "ph": L / N, "unit": "µm"},
            **({"unc": copy.deepcopy(unc)} if unc else {}), **kw}


class Particles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw, cls.name = sample_image()
        cls.st = load_bytes(cls.raw, cls.name)
        cls.a = run(cls.st, state(), "de")
        cls.u = UNC.evaluate_all(cls.a)
        cls.res = cls.u["results"]

    def test_scale(self):
        uL, uN = 0.5 / 2, 1 / math.sqrt(3)
        rel = math.hypot(uL / L, uN / N)
        self.assertAlmostEqual(self.u["rel_scale"], rel, delta=rel * 1e-4)
        self.assertAlmostEqual(self.res["px"]["value"], L / N, places=12)

    def test_scale_propagates_relatively_to_d50(self):
        """Y = Q·(s/s0): Beitrag von L zu u(D50) ist D50·u(L)/L, von N ist D50·u(N)/N; dazu die Stichprobe (Typ A)."""
        x = self.res["D50"]
        rows = {r["name"]: r for r in x["budget"]}
        d50 = self.a.part["summary"]["D50"]
        self.assertAlmostEqual(x["value"], d50, places=9)
        self.assertAlmostEqual(rows["L"]["cu"] / d50, 0.25 / L, delta=1e-6)
        self.assertAlmostEqual(rows["N"]["cu"] / d50, (1 / math.sqrt(3)) / N, delta=1e-6)
        boot = rows["Q"]["u"]
        self.assertGreater(boot, 0)
        self.assertAlmostEqual(x["u"], math.hypot(boot, d50 * self.u["rel_scale"]), delta=x["u"] * 1e-4)
        # Fläche: doppelte relative Unsicherheit des Massstabs
        y = self.res["meanArea"]
        ra = {r["name"]: r for r in y["budget"]}
        self.assertAlmostEqual(ra["L"]["cu"] / y["value"], 2 * 0.25 / L, delta=1e-6)

    def test_scale_only(self):
        """Ohne Stichprobenbeitrag ist u(D50)/D50 genau die relative Unsicherheit des Massstabs."""
        st = UNC.settings(self.a.state)
        m = UNC.models(self.a, st)["D50"]
        ins = [dict(i, parts=[]) if i["name"] == "Q" else i for i in m["inputs"]]
        from labcalc import uncertainty as UN
        r = UN.evaluate(m["f"], ins, "gum")
        self.assertAlmostEqual(r["u"] / r["value"], self.u["rel_scale"], delta=1e-6)

    def test_count_and_fractions(self):
        n = self.a.part["summary"]["Count"]
        self.assertAlmostEqual(self.res["n"]["u"], math.sqrt(n), places=9)
        self.assertAlmostEqual(UNC.binomial_u(20, 100), 0.04, places=12)
        self.assertEqual(UNC.binomial_u(0, 10), 0.0)
        self.assertAlmostEqual(UNC.poisson_u(144), 12.0)
        af = self.res["areaFrac"]
        self.assertEqual({r["name"] for r in af["budget"]}, {"AA"})       # Massstab kürzt sich heraus
        self.assertGreater(af["u"], 0)

    def test_bootstrap_reproducible(self):
        b1 = UNC.bootstrap(self.a.part, 300)
        b2 = UNC.bootstrap(self.a.part, 300)
        self.assertEqual(b1, b2)
        self.assertTrue(any("Bootstrap" in p["label"] for r in self.res["D50"]["budget"] for p in r.get("parts") or []))

    def test_methods_and_compare(self):
        for m in ("mc", "gauss", "worst"):
            a = run(self.st, state({**UNC_LINE, "method": m}), "de")
            x = UNC.evaluate_all(a)["results"]["D50"]
            self.assertEqual(x["method"], m)
            self.assertLessEqual(x["lo"], x["hi"])
        self.assertEqual(set(UNC.compare(self.a, "D50")), {"gum", "mc", "gauss", "worst"})

    def test_equations_get_u(self):
        v, eqs = UNC.evaluate_equations(self.a, self.u, [{"sym": "q", "expr": "D90/D10", "unit": ""}])
        self.assertIn("u", v["D50"])
        self.assertAlmostEqual(v["n"]["u"], math.sqrt(v["n"]["value"]))
        self.assertIsNone(eqs[0]["error"])
        self.assertIn("unc", eqs[0])
        self.assertGreater(eqs[0]["unc"]["u"], 0)

    def test_no_settings(self):
        a = run(self.st, state(unc=None), "de")
        self.assertIsNone(UNC.evaluate_all(a))

    def test_bundle(self):
        s = state(equations=[{"sym": "q", "expr": "D90/D10", "unit": ""}])
        b = bundle.build([(self.st, self.raw, s)], {"items": [{"name": self.name, "state": copy.deepcopy(s)}]}, "de")
        self.assertIn("unc-D50-budget.tex", b["files"])
        self.assertIn("methods/unsicherheit.tex", b["files"])
        keys = [c["key"] for c in b["items"] if c["kind"] == "citation"]
        self.assertIn("efron1993", keys)
        self.assertIn("taylor1997-11", keys)
        self.assertIn("unc", b["source"]["request"]["items"][0]["state"])
        self.assertIn("gleichungen.tex", b["files"])

    def test_series(self):
        a2 = run(self.st, state(size_min=6), "de")
        ser = UNC.series([self.a, a2], "en")
        x = ser["areaFrac"]
        vals = [self.a.part["summary"]["AreaFraction"], a2.part["summary"]["AreaFraction"]]
        self.assertEqual(x["n"], 2)
        self.assertAlmostEqual(x["value"], float(np.mean(vals)), places=9)
        self.assertAlmostEqual(x["u"], float(np.std(vals, ddof=1)) / math.sqrt(2), delta=1e-9)
        self.assertTrue(any("E562" in t for t in x["refs_full"]))
        s1, s2 = state(), state(size_min=6)
        b = bundle.build([(self.st, self.raw, s1), (self.st, self.raw, s2)],
                         {"items": [{"name": self.name, "state": s1}, {"name": self.name, "state": s2}]}, "en")
        self.assertIn("text-unsicherheit.tex", b["files"])
        self.assertIn("serie-areaFrac-budget.tex", b["files"])


if __name__ == "__main__":
    unittest.main()
