"""Measurement uncertainty of the TGA results (tga/uncert.py): hand calculations, replicates, kinetics, report."""
from __future__ import annotations

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

from tga import bundle as B  # noqa: E402
from tga import kinetics as KI  # noqa: E402
from tga import readers as RD  # noqa: E402
from tga import synth as SY  # noqa: E402
from tga import uncert as UC  # noqa: E402
from tga.analysis import run as analyse  # noqa: E402

U_M0 = 0.05      # mg, standard uncertainty of the sample mass
U_BAL = 0.002    # mg, per TGA balance reading
U_DRIFT = 0.01   # mg
UNC = {"m0": {"parts": [{"kind": "u", "u": U_M0}]}, "bal": {"parts": [{"kind": "u", "u": U_BAL}]},
       "drift": {"parts": [{"kind": "u", "u": U_DRIFT}]}}


def oxalate():
    data, name = SY.make("oxalat")[0]
    return RD.load_bytes(data, name)[0]


def by_id(a):
    return {r["id"]: r for r in a.unc["results"]}


class OffByDefault(unittest.TestCase):
    def test_no_entries_no_budgets(self):
        a = analyse(oxalate(), {})
        self.assertIsNone(a.unc)
        self.assertNotIn("u", a.variables["L1"])


class MassLoss(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = oxalate()
        cls.a = analyse(cls.raw, {"unc": copy.deepcopy(UNC)})

    def test_loss_against_hand_calculation(self):
        # L = 100 (m_a - m_b + d) / m0: c_m0 = -L/m0, c_ma = -c_mb = c_d = 100/m0
        st = self.a.steps[0]
        m0 = self.raw.m0
        L = st["loss"]
        u = math.sqrt((L / m0 * U_M0) ** 2 + 2 * (100 / m0 * U_BAL) ** 2 + (100 / m0 * U_DRIFT) ** 2)
        r = by_id(self.a)["step1-loss"]
        self.assertAlmostEqual(r["value"], L, places=6)
        self.assertAlmostEqual(r["u"], u, delta=1e-6 * u + 1e-9)
        self.assertAlmostEqual(r["res"]["U"], r["res"]["k"] * u, delta=1e-6)

    def test_residue_and_variables(self):
        res = by_id(self.a)["residue"]
        R = self.a.st["residue"]["end"]
        m0 = self.raw.m0
        u = math.sqrt((R / m0 * U_M0) ** 2 + (100 / m0 * U_BAL) ** 2 + (100 / m0 * U_DRIFT) ** 2)
        self.assertAlmostEqual(res["u"], u, delta=1e-6 * u)
        self.assertAlmostEqual(self.a.variables["L1"]["u"], by_id(self.a)["step1-loss"]["u"])
        self.assertAlmostEqual(self.a.variables["m0"]["u"], U_M0)

    def test_equation_carries_u(self):
        eq = [{"sym": "n", "label": "n(H2O)", "expr": "L1/100*146.11/18.015"}]
        a = analyse(self.raw, {"unc": copy.deepcopy(UNC), "equations": eq})
        row = a.equations[0]
        uL = by_id(a)["step1-loss"]["u"]
        self.assertAlmostEqual(row["unc"]["u"], uL / 100 * 146.11 / 18.015, delta=1e-6)
        self.assertIn("±", row["text_pm"])

    def test_content_from_stoichiometry(self):
        a = analyse(self.raw, {"unc": copy.deepcopy(UNC), "reactions": [{"step": 1, "key": "oxalat1"}]})
        c = by_id(a)["content1"]
        L = by_id(a)["step1-loss"]
        th = a.reactions[0]["theory"]
        self.assertAlmostEqual(c["u"], L["u"] * 100 / th, delta=1e-6)


class Temperatures(unittest.TestCase):
    def test_calibration_and_interpolation_labelled(self):
        unc = {"T_cal": {"parts": [{"kind": "u", "u": 0.5}]}, "T_tc": {"parts": [{"kind": "u", "u": 1.0}]}}
        a = analyse(oxalate(), {"unc": unc})
        r = by_id(a)
        on = r["step1-onset"]
        self.assertGreater(on["u"], math.sqrt(0.5 ** 2 + 1.0 ** 2) - 1e-9)
        names = [b.get("name") for b in on["res"]["budget"]]
        self.assertIn("dT_eval", names)                      # tangent construction as its own, labelled input
        t5 = r["t5"]
        self.assertGreaterEqual(t5["u"], math.sqrt(1.25) - 1e-9)
        pk = r["step1-peak"]
        self.assertGreater(pk["u"], math.sqrt(1.25))         # sampling contribution on top

    def test_composition_d7582_basis_start(self):
        a = analyse(oxalate(), {"unc": copy.deepcopy(UNC), "composition": {"preset": "d7582"}})
        rows = [r for r in a.unc["results"] if r["group"] == "comp"]
        if not a.comp or a.comp.get("error"):
            self.skipTest("D7582 preset not applicable to the synthetic run")
        self.assertTrue(rows)
        for r in rows:
            self.assertGreater(r["u"], 0)


class Replicates(unittest.TestCase):
    def test_type_a_from_repeats(self):
        run = oxalate()
        base = analyse(run, {})
        L = base.steps[0]["loss"]
        # three "repeats": same run, scaled step via the sample mass -> known spread of L1
        xs = [L, L * 1.01, L * 0.99]

        class Fake:
            def __init__(self, x):
                self.steps = [dict(base.steps[0], loss=x)]
                self.st = {"loss_T": {}, "residue": {}}
                self.comp = None
                self.unc = None
        out = UC.replicates([Fake(x) for x in xs], {}, "de")
        r = {x["id"]: x for x in out["results"]}["rep-step1-loss"]
        m = sum(xs) / 3
        s = math.sqrt(sum((x - m) ** 2 for x in xs) / 2)
        self.assertAlmostEqual(r["value"], m, places=9)
        self.assertAlmostEqual(r["u"], s / math.sqrt(3), delta=1e-9)
        self.assertFalse(r["typeB"])

    def test_type_a_combined_with_type_b(self):
        run = oxalate()
        a = [analyse(run, {"unc": copy.deepcopy(UNC)}) for _ in range(2)]
        out = UC.replicates(a, {}, "de")
        r = {x["id"]: x for x in out["results"]}["rep-step1-loss"]
        self.assertTrue(r["typeB"])                          # identical runs: only the type B part remains
        self.assertAlmostEqual(r["u"], by_id(a[0])["step1-loss"]["u"], delta=1e-9)


class Kinetics(unittest.TestCase):
    def test_confidence_interval_reproduced(self):
        runs = [RD.load_bytes(d, n)[0] for d, n in SY.make("kinetik")]
        res = KI.run_all(runs, 300, 600)
        out = {x["id"]: x for x in UC.kinetics(res, {}, "de")}
        k = res["kissinger"]
        self.assertIn("ea-kissinger", out)
        self.assertAlmostEqual(out["ea-kissinger"]["res"]["U"], k["ci"], delta=1e-6 * abs(k["ci"]) + 1e-9)
        self.assertEqual(len(out["ea-kissinger"]["res"]["budget"]), 1)   # nothing added on top


class Report(unittest.TestCase):
    def test_bundle_values_and_tables(self):
        data, name = SY.make("oxalat")[0]
        b = B.build([(data, name, None, {"unc": copy.deepcopy(UNC)})], {"items": [{"name": name}]}, lang="de")
        d = b if isinstance(b, dict) else b.to_dict() if hasattr(b, "to_dict") else None
        text = repr(d if d is not None else b.__dict__)
        self.assertIn("step1-loss-pm", text)
        self.assertIn("unsicherheit", text)


if __name__ == "__main__":
    unittest.main()
