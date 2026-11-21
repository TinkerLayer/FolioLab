"""Measurement uncertainty of the tensile key values (flps/uncertainty.py on labcalc.uncertainty).

Synthetic curve of test_dataset.py as force + elongation (no private data). Checks the budgets against hand
calculations (Rm = Fmax/S0 with a class-1 force-measuring system and a diameter with limits), the strain and modulus
models, the series of several specimens (mean ± type A), the propagation into own equations, the report bundle
(values, budget tables, citations, settings in source.request) and the workbook sheet.
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "sdk" / "python"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import labdataset as DSET  # noqa: E402
from flps import analyse, bundle  # noqa: E402
from flps import dataset as ZD  # noqa: E402
from flps import uncertainty as UNC  # noqa: E402
from flps.parser import parse_bytes  # noqa: E402
from test_dataset import A0, L0, V, curve  # noqa: E402

D = math.sqrt(4 * A0 / math.pi)        # Durchmesser mit derselben Fläche
SQ3 = math.sqrt(3)


def measure(scale=1.0, unc=None, name="U", **kw):
    """Kraft + Verlängerung der synthetischen Kurve, rund mit d, Kraftklasse 1 usw. aus ``unc``."""
    eps, sig = curve()
    ds = DSET.from_columns(name, [{"key": "dl", "name": "Verlängerung", "unit": "mm", "values": eps * L0},
                                  {"key": "F", "name": "Kraft", "unit": "N", "values": sig * A0 * scale}])
    raw, fname, c = ZD.make_raw(ds, {"load": "F", "ext": "dl"}, {"l0_mm": L0, "speed_mm_min": V},
                                {"share": "s-0000u" + name.lower(), "title": name, "version": 1,
                                 "created": "2026-11-19T10:00:00"})
    cfg = analyse.Config.from_dict({**c, "displacement_source": "probe", "specimen_mode": "manuell", "section": "rund",
                                    "diameter_mm": D, "a0_mm2": None, "unc": unc, **kw})
    return analyse.run(parse_bytes(raw, fname), cfg), raw, fname, cfg


UNC_ALL = {"method": "gum", "force_class": "kraft-iso7500-1", "ext_class": "extenso-iso9513-1",
           "specs": {"diameter_mm": {"parts": [{"kind": "limits", "a": 0.01, "dist": "rect"}]},
                     "l0_mm": {"parts": [{"kind": "limits", "a": 0.1}]}}}


class Budgets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r, cls.raw, cls.name, cls.cfg = measure(unc=UNC_ALL)
        cls.res = cls.r.unc["results"]

    def test_without_settings_nothing_changes(self):
        r, *_ = measure()
        self.assertIsNone(r.unc)
        self.assertNotIn("unc", r.config.to_dict())           # Berichtsquelle und Goldens wie bisher
        self.assertNotIn("unc", analyse.result_to_dict(r, False))
        self.assertTrue(all("u" not in v for v in r.variables.values()))

    def test_fmax_class_1(self):
        """Kraftklasse 1 (ISO 7500-1): a = 1 % vom Wert, rechteckig → u_rel = 1 %/√3; dazu die Anzeigeauflösung."""
        F = self.r.kv["max"]["F"]
        res = self.r.prep.resolution
        u_hand = math.sqrt((0.01 * F / SQ3) ** 2 + (res / 2 / SQ3) ** 2 if res and math.isfinite(res) else (0.01 * F / SQ3) ** 2)
        x = self.res["Fmax"]
        self.assertAlmostEqual(x["u"], u_hand, delta=u_hand * 1e-6)
        self.assertGreater(x["u"] / F, 0.01 / SQ3 * 0.999)

    def test_rm_hand_calculation(self):
        """Rm = F/(π d²/4): u_rel(Rm)² = u_rel(F)² + (2 u(d)/d)², u(d) = 0,01 mm/√3 (Grenzen, rechteckig)."""
        F = self.r.kv["max"]["F"]
        uF = self.res["Fmax"]["u"]
        ud = 0.01 / SQ3
        rm = F / (math.pi * D ** 2 / 4)
        u_hand = rm * math.sqrt((uF / F) ** 2 + (2 * ud / D) ** 2)
        x = self.res["Rm"]
        self.assertAlmostEqual(x["value"], self.r.kv["Rm"], places=9)
        self.assertAlmostEqual(x["u"], u_hand, delta=u_hand * 1e-4)
        self.assertAlmostEqual(x["U"], x["k"] * x["u"], places=9)
        names = {row["name"] for row in x["budget"]}
        self.assertEqual(names, {"F", "d"})
        # S0 selbst: u(S0)/S0 = 2 u(d)/d
        self.assertAlmostEqual(self.res["S0"]["u"] / self.res["S0"]["value"], 2 * ud / D, delta=1e-6)

    def test_strain_models(self):
        """Agt = 100·ΔL/L0 mit Extensometerklasse 1 (max(1 %·ΔL, 3 µm)) und Zeitauflösung; A und Ag kleiner als At, Agt."""
        for n in ("Agt", "At", "Ag", "A"):
            self.assertIn(n, self.res)
            self.assertAlmostEqual(self.res[n]["value"], self.r.kv[n + "_pct"], places=6)
            self.assertGreater(self.res[n]["u"], 0)
        x = self.res["Agt"]
        dl = (self.r.t[self.r.imax] - self.r.t0) * self.r.v_mm_s
        u_ext = max(0.01 * dl, 0.003) / SQ3
        u_t = self.r.prep.dt * self.r.v_mm_s / 2 / SQ3
        u_l0 = 0.1 / SQ3
        u_hand = x["value"] * math.sqrt((math.hypot(u_ext, u_t) / dl) ** 2 + (u_l0 / L0) ** 2)
        self.assertAlmostEqual(x["u"], u_hand, delta=u_hand * 1e-4)
        # v wurde aus dem Weg berechnet (Datensatz): v kürzt sich heraus und steht nicht im Budget
        self.assertNotIn("v", {row["name"] for row in x["budget"]})

    def test_modulus(self):
        x = self.res["E"]
        self.assertAlmostEqual(x["value"], self.r.e_schein_gpa, delta=1e-6 * self.r.e_schein_gpa)
        self.assertEqual({row["name"] for row in x["budget"]} >= {"dF", "dLE", "L0", "d"}, True)
        self.assertTrue(any("Steigung" in n or "slope" in n for n in x["note_texts"]))

    def test_sources_cited(self):
        refs = " ".join(self.res["Rm"]["refs_full"])
        self.assertIn("Annex J", refs)
        self.assertIn("Code of Practice 07", refs)
        for rec in UNC.SOURCES.values():
            self.assertIn("Angaben nicht am Original geprüft", rec["note"])

    def test_yield_not_rp(self):
        x = self.res.get("sy")
        self.assertIsNotNone(x)
        self.assertTrue(any("Rp0,2" in n for n in x["note_texts"]))

    def test_variables_carry_u(self):
        v = self.r.variables
        for n in ("Fmax", "Rm", "E", "A0", "L0", "Agt"):
            self.assertIn("u", v[n], n)
        self.assertAlmostEqual(v["Rm"]["u"], self.res["Rm"]["u"])
        self.assertAlmostEqual(v["L0"]["u"], 0.1 / SQ3)

    def test_own_equation_propagates(self):
        r, *_ = measure(unc=UNC_ALL, equations=[{"sym": "q", "expr": "Rm/E", "unit": ""}])
        eq = r.equations[0]
        self.assertIsNone(eq["error"])
        self.assertIn("unc", eq)
        rm, e = r.variables["Rm"], r.variables["E"]
        u_hand = eq["value"] * math.hypot(rm["u"] / rm["value"], e["u"] / e["value"])
        self.assertAlmostEqual(eq["unc"]["u"], u_hand, delta=u_hand * 1e-3)

    def test_methods(self):
        for m in ("mc", "gauss", "worst"):
            r, *_ = measure(unc={**UNC_ALL, "method": m})
            x = r.unc["results"]["Rm"]
            self.assertEqual(x["method"], m)
            self.assertLessEqual(x["lo"], self.r.kv["Rm"])
            self.assertGreaterEqual(x["hi"], self.r.kv["Rm"])
        cmp = UNC.compare(self.r, "Rm")
        self.assertEqual(set(cmp), {"gum", "mc", "gauss", "worst"})

    def test_settings_cleaned(self):
        st = UNC.settings(analyse.Config.from_dict({"unc": {"method": "x", "p": "7", "specs": {"bogus": {"parts": [1]},
                                                                                              "l0_mm": {"parts": []}}}}))
        self.assertEqual(st["method"], "gum")
        self.assertLess(st["p"], 1)
        self.assertEqual(st["specs"], {})


class Series(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runs = [measure(scale=s, unc=UNC_ALL, name=f"P{i}") for i, s in enumerate((1.0, 1.02, 0.97))]
        cls.rs = [x[0] for x in cls.runs]

    def test_mean_type_a(self):
        ser = UNC.series(self.rs, "de")
        x = ser["Rm"]
        vals = [r.kv["Rm"] for r in self.rs]
        s = float(np.std(vals, ddof=1))
        ub = float(np.mean([r.unc["results"]["Rm"]["u"] for r in self.rs]))
        self.assertEqual(x["n"], 3)
        self.assertAlmostEqual(x["value"], float(np.mean(vals)), places=9)
        self.assertAlmostEqual(x["u"], math.hypot(s / math.sqrt(3), ub), delta=1e-9 * x["value"])
        self.assertEqual(UNC.series(self.rs[:1]), {})

    def test_bundle_single_and_series(self):
        r, raw, name, cfg = self.runs[0]
        b = bundle.build([r], {name: raw}, {"items": [{"name": name, "config": cfg.to_dict()}]}, lang="de")
        files = b["files"]
        self.assertIn("Rm-budget.tex", files)
        self.assertIn("methods/unsicherheit.tex", files)
        keys = [c["key"] for c in b["items"] if c["kind"] == "citation"]
        self.assertIn("iso6892-1-anhj", keys)
        self.assertIn("uncert-cop07", keys)
        self.assertEqual(b["source"]["request"]["items"][0]["config"]["unc"]["force_class"], "kraft-iso7500-1")
        bm = bundle.build(self.rs, {x[2]: x[1] for x in self.runs},
                          {"items": [{"name": x[2], "config": x[3].to_dict()} for x in self.runs]}, lang="en")
        self.assertIn("serie-Rm-budget.tex", bm["files"])
        self.assertIn("text-unsicherheit.tex", bm["files"])

    def test_pdf_lines_and_workbook(self):
        from flps.export import report
        from flps.export.xlsx_export import write_xlsx
        k, v = report._unc_line(self.rs[0])
        self.assertIn("Rm", v)
        self.assertIn("±", v)
        self.assertIn("Serie (n = 3", report._series_line(self.rs))
        from openpyxl import load_workbook
        with TemporaryDirectory() as td:
            p = write_xlsx(self.rs[0], Path(td))
            wb = load_workbook(p)
            self.assertIn("Messunsicherheit", wb.sheetnames)
            wb.close()


if __name__ == "__main__":
    unittest.main()
