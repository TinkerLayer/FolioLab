"""Messunsicherheit im Elementrechner: molare Masse nach Possolo et al. 2018, Ansetzen (QUAM A1), Verdünnungsreihe,
Gasgesetz, Ausbeute, pH, Bericht."""
import math
import unittest

from labcalc import acidbase as AB
from labcalc import uncertainty as UN
from elementrechner import analysis as AN
from elementrechner import uncert as UC

R3 = math.sqrt(3)


def _u(parts_u):
    return {"parts": [{"kind": "u", "u": parts_u}]}


class MolarMass(unittest.TestCase):
    def test_h2o_by_hand(self):
        # CIAAW-Intervalle: H [1,00784; 1,00811], O [15,99903; 15,99977]; Rechteck (Possolo et al. 2018), H zweimal als 2·A_r(H)
        hH, hO = (1.00811 - 1.00784) / 2, (15.99977 - 15.99903) / 2
        value = 2 * (1.00784 + 1.00811) / 2 + (15.99903 + 15.99977) / 2
        u = math.sqrt((2 * hH / R3) ** 2 + (hO / R3) ** 2)
        r = UC.molar_mass("H2O", {"method": "gum"})
        self.assertAlmostEqual(r["value"], value, places=9)
        self.assertAlmostEqual(r["u"], u, delta=1e-9)
        self.assertAlmostEqual(UC.possolo_u("H2O")["u"], u, delta=1e-12)
        # Budget: zwei Eingangsgrössen (Elemente unabhängig), H mit Empfindlichkeit 2
        names = {b["name"]: b for b in r["budget"]}
        self.assertEqual(set(names), {"A_H", "A_O"})
        self.assertAlmostEqual(names["A_H"]["c"], 2.0, places=6)
        self.assertIn("Possolo", repr(UC.aw_input("H")["parts"][0]["source"]))

    def test_methods_agree_roughly(self):
        g = UC.molar_mass("CuSO4", {"method": "gum"})
        for m in ("mc", "gauss", "worst"):
            r = UC.molar_mass("CuSO4", {"method": m})
            self.assertNotIn("error", r, m)
            self.assertAlmostEqual(r["value"], g["value"], delta=10 * g["u"])

    def test_isotope_uses_ame(self):
        j = UC.molar_mass_job("^13CH4")
        src = {x["name"]: x.get("source") for x in j["inputs"]}
        self.assertEqual(src["A_13C"], UC.AME2020)
        self.assertNotIn("error", UC.molar_mass("^13CH4", {"method": "gum"}))


class QuamA1(unittest.TestCase):
    """EURACHEM/CITAC QUAM (2012), Beispiel A1: Cd-Kalibrierstandard, c = 1002,7 mg/L, u_c = 0,9 mg/L, U = 1,8 mg/L (k = 2)."""

    REQ = {"components": [{"substance": "Cd", "value": 1000, "unit": "mg/L", "purity": 0.9999, "mw": 0.10028}],
           "V": 100, "V_unit": "mL",
           "unc": {"method": "gum", "k": 2, "specs": {"s.m.0": _u(0.00005), "s.purity.0": _u(0.000058), "s.V": _u(0.066)}}}

    def test_quam_a1(self):
        out = AN.prep_call("solid", dict(self.REQ))
        r = out["unc"]["results"][0]
        self.assertNotIn("error", r)
        self.assertEqual(r["unit"], "mg/L")
        self.assertAlmostEqual(r["value"], 1002.7, delta=0.05)
        rel = math.sqrt((0.05 / 100.28) ** 2 + (0.000058 / 0.9999) ** 2 + (0.066 / 100) ** 2)
        self.assertAlmostEqual(r["u"], 1002.6997 * rel, delta=2e-3)        # 0,831 (QUAM rundet auf 0,9)
        self.assertLessEqual(abs(r["u"] - 0.9), 0.1)
        self.assertAlmostEqual(r["k"], 2.0)
        self.assertLessEqual(abs(r["U"] - 1.8), 0.2)
        # A_r(Cd) kürzt sich heraus (Form = Bezug): Empfindlichkeit 0
        b = {x["name"]: x for x in r["budget"]}
        self.assertAlmostEqual(b["A_Cd"].get("c") or 0.0, 0.0, delta=1e-9)
        self.assertIn("specs", r)

    def test_without_unc_no_block(self):
        req = dict(self.REQ)
        req.pop("unc")
        self.assertNotIn("unc", AN.prep_call("solid", req))

    def test_compare(self):
        cmp = UC.compare("prep:solid", dict(self.REQ), "prep-c-Cd")
        self.assertEqual(set(cmp) >= {"gum", "mc", "gauss", "worst"}, True)


class Series(unittest.TestCase):
    def test_correlation_by_hand(self):
        r0, pt, pf = 0.002, 0.5, 0.2
        req = {"c0": 1, "unit": "mol/L", "factor": 10, "steps": 3, "V": 10, "V_unit": "mL",
               "unc": {"method": "gum", "specs": {"v.c0": _u(r0), "v.pip": {"parts": [{"kind": "rel", "pct": pt}]},
                                                  "v.flask": {"parts": [{"kind": "rel", "pct": pf}]}}}}
        out = AN.prep_call("series", req)
        res, corr = out["unc"]["results"], out["unc"]["corr"]
        self.assertEqual([x["name"] for x in res], ["series-c1", "series-c2", "series-c3"])
        q = (pt / 100 / R3) ** 2 + (pf / 100 / R3) ** 2          # je Stufe: Pipette und Kolben, relativ
        rel = lambda i: math.sqrt(r0 ** 2 + i * q)               # noqa: E731
        for i, x in enumerate(res, start=1):
            self.assertAlmostEqual(x["u"] / x["value"], rel(i), delta=1e-6)
        for i in range(1, 4):
            for k in range(1, 4):
                hand = (r0 ** 2 + min(i, k) * q) / (rel(i) * rel(k))
                self.assertAlmostEqual(corr["r"][i - 1][k - 1], hand, delta=1e-6)
        self.assertGreater(corr["r"][0][1], 0.5)                  # über die Stammlösung stark korreliert


class GasYieldPH(unittest.TestCase):
    def test_gas_unknown_gets_u(self):
        req = {"p": "101.325", "V": None, "n": "1", "T": "0", "p_unit": "kPa", "V_unit": "L", "T_unit": "°C",
               "unc": {"method": "gum", "specs": {"g.p": _u(0.1), "g.T": _u(0.2)}}}
        out = AN.prep_call("gas", req)
        r = out["unc"]["results"][0]
        self.assertEqual(r["name"], "gas-V")
        self.assertAlmostEqual(r["value"], out["ideal"]["value"], places=9)
        V = r["value"]
        hand = V * math.sqrt((0.1 / 101.325) ** 2 + (0.2 / 273.15) ** 2)
        self.assertAlmostEqual(r["u"], hand, delta=1e-6)

    def test_stoich_yield(self):
        st = {"equation": "Zn + CuSO4 -> ZnSO4 + Cu", "amounts": {"0": {"mass_g": 6.5}}, "actual": {"3": {"mass_g": 6.0}},
              "unc": {"method": "gum", "specs": {"st.0": _u(0.01), "st.3": _u(0.01)}}}
        res = AN.run(st)
        y = [x for x in res["unc"]["results"] if x["name"] == "yield-Cu"][0]
        row = [x for x in res["equation"]["stoich"]["rows"] if x["species"] == "Cu"][0]
        self.assertAlmostEqual(y["value"], row["yield_pct"], delta=0.01)
        self.assertGreater(y["u"], 0.1)
        self.assertLess(y["u"], 1.0)

    def test_plan_yield(self):
        req = {"equation": "Zn + CuSO4 -> ZnSO4 + Cu", "reference": {"i": 0, "value": 6.5, "unit": "g"}, "reagents": {},
               "extras": [], "observed": {"masses": {"3": 6.0}}, "unc": {"method": "gum", "specs": {"r.amt": _u(0.01), "r.obs.3": _u(0.01)}}}
        out = AN.prep_call("reaction", req)
        r = out["unc"]["results"][0]
        self.assertNotIn("error", r)
        self.assertAlmostEqual(r["value"], 100 * out["plan"]["observed"][3]["yield"], delta=0.01)

    def test_ph_model_matches_acidbase(self):
        for mix in ("0,1 M CH3COOH", "0,1 M CH3COOH; 0,05 M CH3COONa", "0,01 M H3PO4", "0,01 M HCl"):
            j, listing = UC.ph_job(mix, 25.0, {}, "de")
            v = {x["name"]: x["value"] for x in j["inputs"]}
            self.assertAlmostEqual(j["model"](v), AB.ph(mix, 25.0)["pH"], delta=1e-6, msg=mix)
            self.assertTrue(all(x["key"].startswith("ph.") for x in listing))

    def test_ph_u_by_propagation(self):
        r = UC.ph("0,1 M CH3COOH", 25, {"method": "gum", "specs": {"ph.c.0": {"parts": [{"kind": "rel", "pct": 1}]},
                                                                   "ph.pka.0.0.1": _u(0.02)}})["result"]
        # schwache Säure: pH ≈ (pKa − lg c)/2, also u ≈ ½·√(u(pKa)² + (u_rel(c)/ln 10)²)
        hand = 0.5 * math.sqrt(0.02 ** 2 + (0.01 / R3 / math.log(10)) ** 2)
        self.assertAlmostEqual(r["u"], hand, delta=0.1 * hand)
        self.assertTrue(r.get("note_texts"))
        none = UC.ph("0,1 M CH3COOH", 25, {"method": "gum"})["result"]
        self.assertTrue(none.get("none"))


class Report(unittest.TestCase):
    def test_bundle_section(self):
        import matplotlib
        matplotlib.use("Agg")
        from elementrechner import bundle as B
        state = {"equation": "Zn + CuSO4 -> ZnSO4 + Cu", "amounts": {"0": {"mass_g": 6.5}}, "actual": {"3": {"mass_g": 6.0}},
                 "unc": {"method": "gum", "specs": {"st.0": _u(0.01), "st.3": _u(0.01)}},
                 "prep": [{"kind": "solid", "req": QuamA1.REQ}]}
        for lang in ("de", "en"):
            b = B.build({"state": state}, lang)
            txt = repr(b)
            self.assertIn("unc-yield-Cu-pm", txt)
            self.assertIn("unc-prep-c-Cd-pm", txt)
            self.assertIn("messunsicherheit", txt)
            cites = [i.get("key") or "" for i in b["items"] if i["kind"] == "citation"]
            self.assertTrue(any("possolo" in k for k in cites), cites)
            self.assertTrue(any("jcgm100" in k for k in cites), cites)
            self.assertEqual(b["source"]["request"]["state"]["unc"]["specs"]["st.0"], _u(0.01))

    def test_no_unc_no_section(self):
        import matplotlib
        matplotlib.use("Agg")
        from elementrechner import bundle as B
        b = B.build({"state": {"equation": "Zn + CuSO4 -> ZnSO4 + Cu", "amounts": {"0": {"mass_g": 6.5}}}}, "de")
        self.assertNotIn("messunsicherheit", repr(b))

    def test_methods_listed(self):
        self.assertEqual(set(UN.METHODS), {"gum", "mc", "gauss", "worst"})


if __name__ == "__main__":
    unittest.main()
