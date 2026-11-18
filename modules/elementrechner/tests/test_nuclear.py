"""Kernchemie (ER-601…606): Q-Werte, Zerfall, Ketten, Datierung, Isotopenmuster, Rechner und Bericht."""
import base64
import math
import unittest

from labcalc import expr as E
from labcalc import nuclear as N

from elementrechner import analysis as A
from elementrechner import bundle as B

NUC = [
    {"kind": "q", "req": {"nuclide": "U-238", "mode": "A"}},
    {"kind": "binding", "req": {"nuclide": "Fe-56"}},
    {"kind": "chain", "req": {"nuclide": "Sr-90", "members": 3, "tmax": 20, "t_unit": "d", "N0": 1e6}},
    {"kind": "decay", "req": {"nuclide": "C-14", "A0": 1, "A_unit": "kBq", "t": 5700, "t_unit": "a"}},
    {"kind": "dating", "req": {"method": "c14", "F": 0.5}},
    {"kind": "dating", "req": {"method": "upb", "r206": 0.1677, "r207": 1.6774}},
    {"kind": "dating", "req": {"method": "rbsr", "points": "0.5 0.7071\n1.0 0.7142\n2.0 0.7284"}},
    {"kind": "pattern", "req": {"formula": "Cl2"}},
    {"kind": "enriched", "req": {"composition": "6Li 95; 7Li 5"}},
    {"kind": "equation", "req": {"equation": "n + U-235 -> Ba-141 + Kr-92 + 3 n"}},
    {"kind": "equation", "req": {"equation": "Tc-99m -> Tc-99 + γ"}},
]


class QAndBinding(unittest.TestCase):
    def test_q_values(self):
        q = N.q_value("U-238", "A")
        self.assertEqual(q["daughter"], "234Th")
        self.assertAlmostEqual(q["Q_MeV"], 4.26986, delta=0.0005)      # AME2020: 4269,86 ± 2,99 keV
        self.assertAlmostEqual(q["u_MeV"] * 1000, 2.99, delta=0.05)
        self.assertAlmostEqual(N.q_value("C-14", "B-")["Q_MeV"] * 1000, 156.476, delta=0.01)
        self.assertAlmostEqual(N.q_value("F-18", "B+")["Q_MeV"] * 1000, 633.9, delta=0.2)

    def test_refusals(self):
        with self.assertRaises(N.NuclearError):
            N.q_value("Tc-99", "IT")
        with self.assertRaises(N.NuclearError):
            N.half_life_s("C-12")                                       # stabil

    def test_classify_equations(self):
        cases = {"U-238 -> Th-234 + α": ("A", 4.26986), "C-14 -> N-14 + β- + ν̄": ("B-", 0.156476),
                 "F-18 -> O-18 + e+ + ν": ("B+", 0.6339), "K-40 + e- -> Ar-40 + ν": ("EC", 1.5044),
                 "Am-241 -> Np-237 + He-4": ("A", 5.6378), "Ca-48 -> Ti-48 + 2 e-": ("2B-", 4.2681),
                 "Cf-252 -> Ba-144 + Mo-104 + 4 n": ("SF", None), "n + U-235 -> Ba-141 + Kr-92 + 3 n": ("reaction", 173.28),
                 "N-14 + α -> O-17 + p": ("reaction", -1.1919), "Tc-99m -> Tc-99 + γ": ("IT", None)}
        for eq, (mode, Q) in cases.items():
            r = N.classify(eq)
            self.assertEqual(r["mode"], mode, eq)
            if Q is not None:
                self.assertAlmostEqual(r["Q_MeV"], Q, delta=abs(Q) * 2e-4 + 1e-4, msg=eq)
        self.assertNotIn("Q_MeV", N.classify("Tc-99m -> Tc-99 + γ"))
        self.assertEqual(N.classify("Am-241 -> Np-237 + α")["daughter"], "237Np")    # 241Am ist kein Isomer
        with self.assertRaises(N.NuclearError):
            N.classify("U-238 -> Th-233 + α")                                         # A nicht erhalten
        with self.assertRaises(N.NuclearError):
            N.classify("U-238 + α")

    def test_binding(self):
        self.assertAlmostEqual(N.binding("Fe-56")["B_per_A_MeV"], 8.7904, delta=0.0005)


class Decay(unittest.TestCase):
    def test_specific_activity(self):
        self.assertAlmostEqual(N.specific_activity("Ra-226")["a_Bq_g"] / 3.658e10, 1, delta=0.002)

    def test_activity_units(self):
        self.assertAlmostEqual(N.activity_convert(1, "mCi", "MBq"), 37.0, places=9)
        self.assertAlmostEqual(N.activity_convert(1, "µCi", "kBq"), 37.0, places=9)

    def test_decay_one_half_life(self):
        T = N.half_life_s("C-14")
        r = N.decay("C-14", A0_Bq=1000, t_s=T)
        self.assertAlmostEqual(r["fraction"], 0.5, places=12)
        self.assertAlmostEqual(r["A_Bq"], 500, places=6)

    def test_bateman_two_members_analytic(self):
        m = [{"key": "P", "T_half_s": 10.0}, {"key": "D", "T_half_s": 2.0}]
        l1, l2 = math.log(2) / 10, math.log(2) / 2
        ts = [0, 1, 5, 20, 60]
        got = N.bateman(m, 1e6, ts)
        for t, row in zip(ts, got):
            self.assertAlmostEqual(row[0], 1e6 * math.exp(-l1 * t), delta=1e-6)
            self.assertAlmostEqual(row[1], 1e6 * l1 / (l2 - l1) * (math.exp(-l1 * t) - math.exp(-l2 * t)), delta=1e-6)

    def test_bateman_stable_end_conserves(self):
        mem = N.chain("Sr-90", 3)
        self.assertEqual([x["key"] for x in mem], ["90Sr", "90Y", "90Zr"])
        tot = [sum(r) for r in N.bateman(mem, 1e6, [0, 1e8, 1e9, 1e10])]
        for s in tot:
            self.assertAlmostEqual(s, 1e6, delta=1e-3)

    def test_equilibrium_classes(self):
        self.assertEqual(N.equilibrium("Sr-90")["kind"], "secular")
        self.assertEqual(N.equilibrium("Ra-226")["kind"], "secular")
        tr = N.equilibrium("Ba-140", "La-140")
        self.assertEqual(tr["kind"], "transient")
        self.assertGreater(tr["A_ratio"], 1)
        self.assertEqual(N.equilibrium("Bi-210")["kind"], "none")


class Dating(unittest.TestCase):
    def test_radiocarbon(self):
        r = N.radiocarbon(0.5)
        self.assertAlmostEqual(r["age_BP"], 5568.0, delta=0.5)
        self.assertAlmostEqual(r["age_cambridge_a"], 5730.0, delta=0.5)

    def test_k_ar_formula(self):
        lt, le = N.LAMBDA["K40_total"][0], N.LAMBDA["K40_e"][0]
        R = 0.01
        self.assertAlmostEqual(N.k_ar(R)["age_a"], math.log(1 + lt / le * R) / lt, delta=1)

    def test_u_pb_round_trip(self):
        t = 1.0e9
        r206 = math.exp(N.LAMBDA["U238"][0] * t) - 1
        r207 = math.exp(N.LAMBDA["U235"][0] * t) - 1
        out = N.u_pb(r206, r207)
        self.assertAlmostEqual(out["age_206_a"], t, delta=1)
        self.assertTrue(out["concordant"])
        self.assertFalse(N.u_pb(r206, r207 * 1.2)["concordant"])

    def test_rb_sr_isochron(self):
        lam = N.LAMBDA["Rb87"][0]
        m = math.exp(lam * 1.0e9) - 1
        pts = [(x, 0.7 + m * x) for x in (0.2, 1.0, 3.0, 5.0)]
        out = N.rb_sr(pts)
        self.assertAlmostEqual(out["age_a"] / 1e9, 1.0, places=6)
        self.assertAlmostEqual(out["intercept"], 0.7, places=9)
        with self.assertRaises(N.NuclearError):
            N.rb_sr(pts[:2])


class Isotopes(unittest.TestCase):
    def _rel(self, f):
        return {p["A"]: p["rel"] for p in N.isotope_pattern(f)["peaks"]}

    def test_cl2_br2(self):
        cl = self._rel("Cl2")
        self.assertAlmostEqual(cl[70], 100, places=6)
        self.assertAlmostEqual(cl[72], 63.9, delta=0.2)
        self.assertAlmostEqual(cl[74], 10.2, delta=0.1)
        br = self._rel("Br2")
        self.assertAlmostEqual(br[160], 100, places=6)
        self.assertAlmostEqual(br[158], 51.3, delta=0.2)
        self.assertAlmostEqual(br[162], 48.7, delta=0.2)

    def test_enriched(self):
        self.assertAlmostEqual(N.enriched_mass({"6Li": 95, "7Li": 5})["M"], 6.06517, delta=2e-5)
        with self.assertRaises(N.NuclearError):
            N.enriched_mass({"6Li": 50, "12C": 50})


class CalculatorFunctions(unittest.TestCase):
    def setUp(self):
        E._register_chem()
        self.f = lambda n, *a: E.STRFUNCS[n][0](None, *a)   # noqa: E731

    def test_functions_si(self):
        self.assertAlmostEqual(self.f("Qval", "U-238", "A") / N.MEV_J, 4.26986, delta=0.0005)
        self.assertAlmostEqual(self.f("Bnuc", "Fe-56") / N.MEV_J, 8.7904, delta=0.0005)
        self.assertAlmostEqual(self.f("Thalf", "C-14") / N.YEAR_S, 5700, delta=40)
        self.assertAlmostEqual(self.f("Aspec", "Ra-226") / 3.658e13, 1, delta=0.002)
        self.assertAlmostEqual(self.f("Ma", "U-235"), 0.235043930, delta=1e-8)


class ReportSection(unittest.TestCase):
    def test_run_matches_api(self):
        out = A.run({"nuclear": NUC})
        self.assertFalse(out["errors"], out["errors"])
        self.assertEqual([x["kind"] for x in out["nuclear"]], [x["kind"] for x in NUC])
        self.assertEqual(out["nuclear"][0]["result"], A.nuclear_call("q", NUC[0]["req"]))

    def test_report_de_en(self):
        for lang in ("de", "en"):
            d = B.build({"state": {"nuclear": NUC}}, lang)
            ids = {i.get("id") for i in d["items"]}
            self.assertTrue({"kernchemie", "kette-3", "isotopenmuster-8"} <= ids, ids)
            vals = {v["key"] for i in d["items"] if i.get("kind") == "values" for v in i["values"]}
            self.assertTrue({"q-238u-a", "ba-56fe", "a-14c", "alter-c14", "alter-rbsr"} <= vals, vals)
            tex = {k: base64.b64decode(v).decode("utf-8") for k, v in d["files"].items() if k.endswith(".tex")}
            for name, t in tex.items():
                self.assertFalse([c for c in t if ord(c) > 255], f"{lang} {name}: Zeichen ausserhalb Latin-1")
                self.assertNotIn("?", t.replace("\\?", ""), f"{lang} {name}: ersetztes Zeichen")
                for bad in ("\\ce{", "\\tfrac", "\\boldsymbol", "\\text{"):
                    self.assertNotIn(bad, t, f"{lang} {name}")
                self.assertEqual(t.count("$") % 2, 0, f"{lang} {name}: ungerade Zahl $")
            body = tex["text-kernchemie.tex"]
            for k in ("er-ame2020", "er-nubase2020", "er-bateman1910", "er-villa2015", "er-jaffey1971"):
                self.assertIn(k, body, f"{lang}: {k}")
            self.assertIn("4{,}26986" if lang == "de" else "4.26986", body)
            self.assertIn("Säkulares" if lang == "de" else "Secular", body)
            self.assertIn(r"$^{99\mathrm{m}}\mathrm{Tc}$", body)
            self.assertIn("Kernreaktion" if lang == "de" else "nuclear reaction", body)
            self.assertTrue(any(k.startswith("fig/kette-3") for k in d["files"]), d["files"].keys())


if __name__ == "__main__":
    unittest.main()
