"""ER-S02: Metall–Ligand-Speziation mit den mitgelieferten Konstanten (NIST SRD 46).

Bezugswert: erste Hydrolysekonstante von Fe³⁺ bei I = 0, lg *β₁ = −2,19 (Baes & Mesmer 1976): der Schnittpunkt
Fe³⁺/FeOH²⁺ liegt bei pH 2,19.
"""
import base64
import math
import unittest

from labcalc import speciation as SP

from elementrechner import analysis as AN
from elementrechner import bundle as B
from laboptional import skip_unless  # noqa: E402


def _cross(r, i, j):
    pts = r["points"]
    for a, b in zip(pts, pts[1:]):
        da = a["rows"][i]["frac"] - a["rows"][j]["frac"]
        db = b["rows"][i]["frac"] - b["rows"][j]["frac"]
        if da * db <= 0 and da != db:
            return a["pH"] + (b["pH"] - a["pH"]) * da / (da - db)
    return None


@skip_unless('srd46')
class Speciation(unittest.TestCase):
    def test_charge_parser(self):
        self.assertEqual(SP._charge("Cu2+"), 2)
        self.assertEqual(SP._charge("Fe^3+"), 3)
        self.assertEqual(SP._charge("Fe³⁺"), 3)
        self.assertEqual(SP._charge("OH-"), -1)

    def test_fe_hydrolysis_baes_mesmer(self):
        r = SP.distribution("Fe3+", "OH-", 1e-6, None, 1.0, 4.0, 301)
        self.assertAlmostEqual(_cross(r, 0, 1), 2.19, delta=0.03)
        self.assertTrue(any("einkernige" in n for n in r["notes"]))

    def test_cu_nh3_balances_and_steps(self):
        r = SP.distribution("Cu2+", "NH3", 0.001, 0.1, 4, 12, 81)
        self.assertLess(r["max_residual"], 1e-9)
        b = r["betas"]
        for p in r["points"]:
            self.assertAlmostEqual(sum(x["frac"] for x in p["rows"]), 1.0, places=10)
            # Gleichgewichtsbeziehung: [MLn]/[MLn-1] = Kn·[L]
            rows = {x["n"]: x["c"] for x in p["rows"]}
            if rows[0] > 1e-12 and rows[1] > 1e-12:
                self.assertAlmostEqual(math.log10(rows[1] / rows[0]), b[1] + math.log10(p["L_free"]), places=8)
        hi = r["points"][-1]["rows"]
        self.assertGreater(hi[4]["frac"], 0.8)                       # Tetraammin im Ammoniaküberschuss
        self.assertAlmostEqual(r["points"][0]["charge_rest"], 2 * 0.001, places=6)

    def test_ca_edta_conditional(self):
        r = SP.distribution("Ca2+", "EDTA", 0.001, 0.0011, 4, 12, 81)
        p10 = min(r["points"], key=lambda p: abs(p["pH"] - 10))
        pk = r["lig_steps"]
        H = 10 ** -p10["pH"]
        den = 1 + sum(10 ** (sum(pk[k] for k in range(1, j + 1)) - j * p10["pH"]) for j in range(1, 5))
        self.assertAlmostEqual(p10["alpha_L"], 1 / den, places=10)
        self.assertAlmostEqual(p10["conditional"][1], r["betas"][1] + math.log10(1 / den), places=8)
        self.assertGreater(p10["rows"][1]["frac"], 0.99)
        self.assertIsNotNone(r["K_MHL"])
        del H

    def test_errors(self):
        with self.assertRaises(SP.SpeciationError):
            SP.distribution("Cu2+", "NH3", 0.001, None)
        with self.assertRaises(SP.SpeciationError):
            SP.distribution("Cl-", "NH3", 0.001, 0.1)

    def test_report(self):
        d = B.build({"state": {"speciation": {"metal": "Cu2+", "ligand": "NH3", "c_M": "0,001", "c_L": "0,1"}}}, "de")
        tex = {k: base64.b64decode(v).decode("utf-8") for k, v in d["files"].items() if k.endswith(".tex")}
        t = tex["text-speziation.tex"]
        t.encode("latin-1")
        self.assertIn(r"\lg\beta_{4}", t)
        self.assertIn("fig/speziation.pdf", d["files"])
        keys = {i["key"] for i in d["items"] if i["kind"] == "citation"}
        self.assertIn("er-srd46", keys)
        self.assertIn("baes1976", AN.speciation_call({"metal": "Fe3+", "ligand": "OH-", "c_M": "1e-5"})["refs"])


class Saturation(unittest.TestCase):
    # Vergleichswerte lg Ksp (25 °C, I = 0) aus der Tabelle der Löslichkeitsprodukte bei Harris (Calcit −8,47;
    # BaSO4 −9,96), aus dem Gedächtnis übertragen – siehe DECISIONS.
    def test_ksp_close_to_harris(self):
        from labcalc import substances as S
        self.assertAlmostEqual(S.ksp("CaCO3")["value"], -8.47, delta=0.15)
        self.assertAlmostEqual(S.ksp("BaSO4")["value"], -9.96, delta=0.15)

    def test_caco3(self):
        r = SP.saturation("CaCO3", "Ca2+", 1e-3, "CO3^2-", 1e-5, model=None)
        self.assertAlmostEqual(r["SI"], -8.0 - r["lgKsp"], places=10)
        self.assertEqual(r["nu"], [1, 1])
        self.assertIn("Fällung möglich", r["state"])
        a = SP.saturation("CaCO3", "Ca2+", 1e-3, "CO3^2-", 1e-5, model="davies")
        self.assertLess(a["SI"], r["SI"])                              # Aktivitäten < Konzentrationen
        self.assertTrue(any("keine Mengenvorhersage" in n for n in a["notes"]))

    def test_baso4_undersaturated(self):
        r = SP.saturation("BaSO4", "Ba2+", 1e-6, "SO4^2-", 1e-6)
        self.assertLess(r["SI"], -0.05)
        self.assertIn("untersättigt", r["state"])

    def test_stoichiometry_and_errors(self):
        r = SP.saturation("CaF2", "Ca2+", 1e-3, "F-", 1e-3, model=None)
        self.assertEqual(r["nu"], [1, 2])
        self.assertAlmostEqual(r["lg_IAP"], -9.0, places=10)
        with self.assertRaises(SP.SpeciationError):
            SP.saturation("CaCO3", "Ca2+", 0, "CO3^2-", 1e-5)

    def test_report(self):
        d = B.build({"state": {"saturation": {"salt": "CaCO3", "cation": "Ca2+", "c_cat": "1e-3", "anion": "CO3^2-",
                                              "c_an": "1e-5", "model": "davies"}}}, "de")
        tex = {k: base64.b64decode(v).decode("utf-8") for k, v in d["files"].items() if k.endswith(".tex")}
        t = tex["text-saettigung.tex"]
        t.encode("latin-1")
        self.assertIn(r"\mathrm{CO_{3}}^{2-}", t)
        self.assertIn("{SI}", tex["values.tex"])


if __name__ == "__main__":
    unittest.main()
