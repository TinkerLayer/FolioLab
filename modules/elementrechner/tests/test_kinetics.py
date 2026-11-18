"""ER-703/704: Kinetik-Fits (synthetische Daten mit bekannten Parametern) und Simulation gegen analytische Lösungen."""
import base64
import math
import random
import unittest

from labcalc import kinetics as K

from elementrechner import analysis as AN
from elementrechner import bundle as B
from laboptional import skip_unless  # noqa: E402

EA, A = 75.0, 2.0e10            # kJ/mol, s⁻¹
TS = [290.0, 300.0, 310.0, 320.0, 330.0, 340.0]


def _k(T):
    return A * math.exp(-EA * 1000 / (K.R * T))


class Fits(unittest.TestCase):
    def test_arrhenius_exact(self):
        r = K.arrhenius(TS, [_k(T) for T in TS])
        self.assertAlmostEqual(r["Ea_kJ"], EA, places=8)
        self.assertAlmostEqual(r["A"] / A, 1.0, places=8)
        self.assertLess(r["u_Ea_kJ"], 1e-6)
        self.assertAlmostEqual(r["r2"], 1.0, places=12)

    def test_arrhenius_noise_within_uncertainty(self):
        rnd = random.Random(7)
        hits = 0
        for _ in range(40):
            k = [_k(T) * math.exp(rnd.gauss(0, 0.05)) for T in TS]
            r = K.arrhenius(TS, k)
            hits += abs(r["Ea_kJ"] - EA) <= 2 * r["u_Ea_kJ"]
        self.assertGreaterEqual(hits, 34)                 # ~95 % Abdeckung bei 2σ

    def test_eyring_consistent_with_arrhenius(self):
        r = K.eyring(TS, [_k(T) for T in TS])
        Tm = sum(TS) / len(TS)
        self.assertAlmostEqual(r["dH_kJ"], EA - K.R * Tm / 1000, delta=0.05)   # ΔH‡ ≈ Eₐ − RT
        # exakte Daten aus Eyring-Parametern zurückgewinnen
        dH, dS = 60.0, -40.0
        k = [K.KB * T / K.H * math.exp(dS / K.R) * math.exp(-dH * 1000 / (K.R * T)) for T in TS]
        e = K.eyring(TS, k)
        self.assertAlmostEqual(e["dH_kJ"], dH, places=8)
        self.assertAlmostEqual(e["dS_J"], dS, places=6)

    def test_order_recovered(self):
        t = [0, 60, 120, 240, 360, 480, 600, 900]
        for order, k, c0 in ((0, 1e-4, 0.1), (1, 2e-3, 0.1), (2, 0.05, 0.1)):
            c = [K._c_pred(order, k, c0, x) for x in t]
            if order == 0:
                c = [max(v, 1e-6) for v in c]
            r = K.order_fit(t, c)
            self.assertEqual(r["best"], order, r["fits"])
            best = next(f for f in r["fits"] if f["order"] == order)
            self.assertAlmostEqual(best["k"] / k, 1.0, places=6)
            self.assertAlmostEqual(best["c0"], c0, places=8)

    def test_order_from_conversion(self):
        t = [0, 100, 200, 400, 800]
        X = [1 - math.exp(-1e-3 * x) for x in t]
        r = K.order_fit(t, X, "X", 0.5)
        self.assertEqual(r["best"], 1)

    def test_errors(self):
        with self.assertRaises(K.KineticsError):
            K.arrhenius([300, 310], [1, 2])
        with self.assertRaises(K.KineticsError):
            K.arrhenius([300, 310, 320], [1, -2, 3])
        with self.assertRaises(K.KineticsError):
            K.order_fit([0, 1, 2], [0.1, 0.2], "c")

    def test_k_at(self):
        self.assertAlmostEqual(K.k_at(320.0, EA, A=A), _k(320.0))
        self.assertAlmostEqual(K.k_at(320.0, EA, k_ref=_k(300.0), T_ref=300.0) / _k(320.0), 1.0, places=10)


class Simulation(unittest.TestCase):
    def test_models_match_rk4(self):
        cases = {"0": {"k": 0.01, "a0": 1}, "1": {"k": 0.1, "a0": 1}, "2": {"k": 0.5, "a0": 2},
                 "2AB": {"k": 0.3, "a0": 1, "b0": 1.5}, "consec": {"k1": 0.5, "k2": 0.2, "a0": 1},
                 "rev": {"kf": 0.3, "kr": 0.1, "a0": 1, "b0": 0}}
        for m, p in cases.items():
            r = K.simulate(m, p)
            # nullte Ordnung: Knick bei c = 0, RK4 trifft ihn nur auf eine Schrittweite genau
            self.assertLess(r["check"]["rel_dev"], 1e-3 if m == "0" else 1e-5, m)
            last = r["rows"][-1]
            tot = sum(v for s, v in last.items() if s != "t")
            if m in ("consec", "rev"):
                self.assertAlmostEqual(tot, p["a0"] + p.get("b0", 0), places=10)

    def test_half_life_and_special_points(self):
        self.assertAlmostEqual(K.simulate("1", {"k": 0.1, "a0": 1})["t_half"], math.log(2) / 0.1)
        self.assertAlmostEqual(K.simulate("2", {"k": 0.5, "a0": 2})["t_half"], 1.0)
        self.assertAlmostEqual(K.simulate("0", {"k": 0.01, "a0": 1})["t_half"], 50.0)
        r = K.simulate("consec", {"k1": 0.5, "k2": 0.2, "a0": 1})
        self.assertAlmostEqual(r["t_Bmax"], math.log(0.2 / 0.5) / (0.2 - 0.5))
        self.assertAlmostEqual(K.simulate("rev", {"kf": 0.3, "kr": 0.1, "a0": 1})["K"], 3.0)

    def test_equal_rates(self):
        r = K.simulate("consec", {"k1": 0.4, "k2": 0.4, "a0": 1})
        self.assertLess(r["check"]["rel_dev"], 1e-5)
        r = K.simulate("2AB", {"k": 0.3, "a0": 1, "b0": 1})
        self.assertLess(r["check"]["rel_dev"], 1e-5)

    def test_api_and_source_required(self):
        with self.assertRaises(K.KineticsError):
            AN.kinetics_call("sim", {"model": "1", "params": {"a0": 1}, "Ea": 50, "T": 310, "k_ref": 0.01, "T_ref": 300})
        r = AN.kinetics_call("sim", {"model": "1", "params": {"a0": 1}, "Ea": 50, "T": 310, "k_ref": 0.01, "T_ref": 300,
                                     "source": "Test"})
        self.assertAlmostEqual(r["params"]["k"], K.k_at(310, 50, k_ref=0.01, T_ref=300))
        r = AN.kinetics_call("arrhenius", {"T": "17 27 37", "T_unit": "C", "k": "1,0e-3; 2,5e-3; 6e-3"})
        self.assertGreater(r["Ea_kJ"], 0)


@skip_unless('burcat')
class Flame(unittest.TestCase):
    # Gegenprobe: dieselbe Energiebilanz mit den NIST-JANAF-Tabellen C-095 (CO2), H-064 (H2O), N-023 (N2) und
    # ΔfH°(CH4) = −74,87 kJ/mol (Chase 1998), linear interpoliert: T_ad = 2326,6 K (ohne Dissoziation).
    JANAF_CH4_AIR = 2326.6

    def test_methane_air_against_janaf(self):
        from labcalc import flame as FL
        r = FL.adiabatic("CH4", 1.0, "air")
        self.assertAlmostEqual(r["T_ad"], self.JANAF_CH4_AIR, delta=5.0)
        # Gleichgewichtswert mit Dissoziation (Turns 2012): 2226 K; ohne Dissoziation 50–150 K darüber
        self.assertTrue(2226 + 50 < r["T_ad"] < 2226 + 150)
        self.assertIn("turns2012", r["refs"])
        self.assertTrue(any("Dissoziation" in n for n in r["notes"]))

    def test_trends_and_errors(self):
        from labcalc import flame as FL
        self.assertLess(FL.adiabatic("CH4", 0.8)["T_ad"], FL.adiabatic("CH4", 1.0)["T_ad"])
        self.assertGreater(FL.adiabatic("CH4", 1.0, "air", 400.0)["T_ad"], FL.adiabatic("CH4", 1.0)["T_ad"])
        with self.assertRaises(FL.FlameError):
            FL.adiabatic("CH4", 1.3)
        with self.assertRaises(FL.FlameError):
            FL.adiabatic("NaCl", 1.0)
        r = AN.kinetics_call("flame", {"fuel": "C3H8", "phi": "1"})
        self.assertAlmostEqual(sum(p["x"] for p in r["products"]), 1.0)


class Report(unittest.TestCase):
    @skip_unless('burcat')
    def test_bundle(self):
        state = {"kinetics": [
            {"kind": "arrhenius", "req": {"T": " ".join(map(str, TS)), "k": " ".join(f"{_k(T):.6e}" for T in TS),
                                         "unit_k": "s⁻¹"}},
            {"kind": "eyring", "req": {"T": " ".join(map(str, TS)), "k": " ".join(f"{_k(T):.6e}" for T in TS)}},
            {"kind": "order", "req": {"t": "0 60 120 240 480", "c": " ".join(str(0.1 * math.exp(-2e-3 * x))
                                                                            for x in (0, 60, 120, 240, 480))}},
            {"kind": "sim", "req": {"model": "rev", "params": {"kf": 0.3, "kr": 0.1, "a0": 1}}},
            {"kind": "flame", "req": {"fuel": "CH4"}}]}
        for lang in ("de", "en"):
            d = B.build({"state": state}, lang)
            tex = {k: base64.b64decode(v).decode("utf-8") for k, v in d["files"].items() if k.endswith(".tex")}
            t = tex["text-kinetik.tex"]
            t.encode("latin-1")
            self.assertIn("75{,}00" if lang == "de" else "75.00", t)
            for j in range(1, 5):
                self.assertIn(f"fig/kinetik-{j}.pdf", d["files"])
            keys = {i["key"] for i in d["items"] if i["kind"] == "citation"}
            self.assertTrue({"er-arrhenius1889", "er-eyring1935", "er-atkins"} <= keys, keys)
            self.assertIn("{ea-1}", tex["values.tex"])
            self.assertIn("{tad-5}", tex["values.tex"])
            fl = tex["text-flammentemperatur-5.tex"]
            fl.encode("latin-1")
            self.assertIn("2325", fl.replace(".", "").replace("{,}", ""))
            self.assertIn("er-turns2012", keys)
            self.assertIn(r"\,s$^{-1}$", t)


if __name__ == "__main__":
    unittest.main()
