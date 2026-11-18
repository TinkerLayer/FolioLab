"""TGA-03: DSC-Auswertung an synthetischen Kurven mit bekannter Fläche, Spitze und Glasübergang."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "sdk" / "python"))

from tga import analysis as AN  # noqa: E402
from tga import dsc as DS  # noqa: E402
from tga.readers import Run  # noqa: E402

BETA = 10.0     # K/min
M0 = 10.0       # mg


def synth(area_mJ=50.0, Tp=160.0, sig=3.0, endo=True, tg=None, exo_up=True, noise=0.0):
    T = np.arange(30.0, 300.0, 0.05)
    t = (T - T[0]) / BETA                                    # min
    hf = 0.2 + 0.002 * (T - 30)                              # schräge Basislinie (mW)
    g = np.exp(-0.5 * ((T - Tp) / sig) ** 2)
    g_area_s = np.trapezoid(g, t * 60.0) if hasattr(np, "trapezoid") else np.trapz(g, t * 60.0)
    s = (-1.0 if exo_up else 1.0) * (1.0 if endo else -1.0)
    hf = hf + s * area_mJ / g_area_s * g
    if tg:
        Tg, step = tg
        hf = hf + s * step / 2 * (1 + np.tanh((T - Tg) / 2.0))
    if noise:
        hf = hf + np.random.default_rng(1).normal(0, noise, len(T))
    return Run("dsc", T, np.linspace(M0, M0 * 0.99, len(T)), "mg", t, M0, {"rate": BETA}, {"hf": hf})


class DSC(unittest.TestCase):
    def test_peak_area_and_temperatures(self):
        r = synth()
        p = DS.peak(r.T, r.time(), r.extra["hf"], 135, 185, "mW", "exo_up", M0)
        self.assertEqual(p["kind"], "endo")
        self.assertAlmostEqual(p["area"], 50.0, delta=0.5)                 # mJ
        self.assertAlmostEqual(p["dH"], 5.0, delta=0.05)                   # J/g
        self.assertAlmostEqual(p["T_peak"], 160.0, delta=0.1)
        # Gauss: Wendepunkt bei Tp − σ, Tangente schneidet die Basislinie bei Tp − 2σ
        self.assertAlmostEqual(p["T_onset"], 154.0, delta=0.3)
        self.assertAlmostEqual(p["T_endset"], 166.0, delta=0.3)

    def test_exo_and_sign_convention(self):
        r = synth(endo=False, exo_up=False, area_mJ=30.0)
        p = DS.peak(r.T, r.time(), r.extra["hf"], 135, 185, "mW", "endo_up", M0)
        self.assertEqual(p["kind"], "exo")
        self.assertAlmostEqual(p["dH_signed"], -3.0, delta=0.05)

    def test_noise_and_units(self):
        r = synth(noise=0.002)
        p = DS.peak(r.T, r.time(), r.extra["hf"], 135, 185, "mW", "exo_up", M0)
        self.assertAlmostEqual(p["dH"], 5.0, delta=0.1)
        u = DS.peak(r.T, r.time(), r.extra["hf"], 135, 185, "uV", "exo_up", M0)
        self.assertNotIn("dH", u)
        self.assertIn("µV", u["note"])

    def test_glass_transition(self):
        r = synth(area_mJ=1e-9, tg=(100.0, 0.15))
        g = DS.glass(r.T, r.time(), r.extra["hf"], 70, 130, "mW", M0, BETA)
        self.assertAlmostEqual(g["Tg_mid"], 100.0, delta=0.3)
        self.assertAlmostEqual(g["step"], 0.15, delta=0.01)
        self.assertAlmostEqual(g["dcp"], 0.15 / M0 / (BETA / 60), delta=0.01)   # 0,09 J/(g·K)
        self.assertLess(g["T_onset"], 100.0)
        self.assertGreater(g["T_endset"], 100.0)

    def test_analysis_and_errors(self):
        r = synth(tg=(100.0, 0.15))
        a = AN.run(r, {"dsc": {"unit": "mW", "peaks": [{"lo": 135, "hi": 185}, {"lo": 400, "hi": 450}],
                               "tg": [{"lo": 70, "hi": 130}]}})
        self.assertAlmostEqual(a.dsc["peaks"][0]["dH"], 5.0, delta=0.1)
        self.assertIn("error", a.dsc["peaks"][1])
        self.assertIn("H1", a.variables)
        self.assertIn("Tg1", a.variables)
        no_hf = Run("x", r.T, r.m, "mg", r.t, M0, {}, {})
        self.assertIsNone(AN.run(no_hf, {"dsc": {"peaks": [{"lo": 135, "hi": 185}]}}).dsc)


class DSCReport(unittest.TestCase):
    def test_csv_with_heat_flow_and_bundle(self):
        import base64
        import json
        from tga import bundle as B
        from tga import readers as RD
        r = synth(tg=(100.0, 0.15))
        lines = ["# Probe: STA-Test", f"# Einwaage: {M0} mg", f"# Heizrate: {BETA} K/min",
                 "Zeit/min;Temperatur/°C;Masse/mg;Wärmestrom/mW"]
        lines += [f"{a:.5f};{b:.3f};{c:.6f};{d:.6f}" for a, b, c, d in zip(r.time(), r.T, r.m, r.extra["hf"])]
        raw = ("\n".join(lines) + "\n").encode("utf-8")
        run = RD.load_bytes(raw, "sta.csv")[0]
        self.assertIn("hf", run.extra)
        self.assertEqual(run.meta.get("hf_unit"), "mW")
        st = {"dsc": {"peaks": [{"lo": 135, "hi": 185}], "tg": [{"lo": 70, "hi": 130}]}}
        for lang in ("de", "en"):
            b = B.build([(raw, "sta.csv", None, st)], {"items": [{"name": "sta.csv"}]}, lang=lang)
            files = b["files"]
            self.assertTrue(any(k.startswith("fig/dsc") for k in files), list(files))
            tex = "".join(base64.b64decode(v).decode("utf-8") for k, v in files.items() if k.endswith(".tex"))
            tex.encode("latin-1")
            self.assertIn("11357", tex + base64.b64decode(files["refs.bib"]).decode("utf-8"))
            vals = json.dumps(b["items"], ensure_ascii=False)
            self.assertIn("dsc1-dh", vals)
            self.assertIn("tg1", vals)


if __name__ == "__main__":
    unittest.main()
