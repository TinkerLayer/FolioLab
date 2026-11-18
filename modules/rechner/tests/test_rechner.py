"""Tests des Rechners:  python -m unittest discover -s tests   (im Ordner modules/rechner)."""
import ast
import base64
import json
import math
import sys
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "sdk" / "python"))

import numpy as np  # noqa: E402

from rechner import bundle as B  # noqa: E402
from rechner import console as C  # noqa: E402
from rechner import expr as E  # noqa: E402
from rechner import library as L  # noqa: E402
from rechner import plots as P  # noqa: E402
from rechner import render as R  # noqa: E402
from rechner import solver as S  # noqa: E402
from rechner import units as U  # noqa: E402


def ev(s, **kw):
    ctx = E.Ctx(**kw)
    return E.evaluate(E.parse(s, ctx.callables()), ctx)


class Units(unittest.TestCase):
    def test_parse(self):
        self.assertAlmostEqual(U.to_si(72, "km/h"), 20)
        self.assertAlmostEqual(U.to_si(1, "N/mm^2"), 1e6)
        self.assertAlmostEqual(U.to_si(1, "N/mm²"), 1e6)
        self.assertAlmostEqual(U.to_si(20, "°C"), 293.15)
        self.assertAlmostEqual(U.to_si(10, "°C", diff=True), 10)
        self.assertAlmostEqual(U.to_si(1, "MPa√m"), 1e6)
        self.assertAlmostEqual(U.to_si(1, "L/(mol*cm)"), 0.1)
        self.assertAlmostEqual(U.to_si(1, "µm"), 1e-6)
        self.assertAlmostEqual(U.to_si(1, "kWh"), 3.6e6)
        self.assertTrue(U.deq(U.parse_unit("kg m/s^2")[1], U.parse_unit("N")[1]))

    def test_kinds(self):
        self.assertIsNone(U.check_unit("velocity", "km/h"))
        self.assertIsNotNone(U.check_unit("velocity", "m/s^2"))
        self.assertEqual(U.auto_unit("pressure", 2.5e8), "MPa")
        self.assertEqual(U.dims_text(U.parse_unit("kg*m/s^2")[1]), "N")


class Expressions(unittest.TestCase):
    def test_calculator_notation(self):
        self.assertEqual(float(ev("2(3+4)^2")), 98)
        self.assertEqual(float(ev("5!")), 120)
        self.assertAlmostEqual(float(ev("2pi")), 2 * math.pi)
        self.assertAlmostEqual(float(ev("sin(30)", angle="deg")), 0.5)
        self.assertAlmostEqual(float(ev("sin(pi/2)")), 1)
        self.assertEqual(float(ev("a b", names={"a": 2, "b": 3})), 6)
        self.assertEqual(float(ev("(a+1)(b+1)", names={"a": 2, "b": 3})), 12)
        self.assertEqual(float(ev("1e3")), 1000)
        self.assertEqual(float(ev("if(3 > 2, 1, 0)")), 1)

    def test_matrices(self):
        A = "[[1,2],[3,4]]"
        np.testing.assert_allclose(ev(f"{A}*{A}"), [[7, 10], [15, 22]])
        np.testing.assert_allclose(ev(f"{A}'"), [[1, 3], [2, 4]])
        np.testing.assert_allclose(ev(f"inv({A})"), [[-2, 1], [1.5, -0.5]])
        self.assertAlmostEqual(float(ev(f"det({A})")), -2)
        np.testing.assert_allclose(ev("linsolve([[2,1],[1,3]], [3,5])"), [0.8, 1.4])
        np.testing.assert_allclose(ev("rref([[1,2,3],[4,5,6]])"), [[1, 0, -1], [0, 1, 2]])
        self.assertEqual(float(ev(f"{A}[2,1]")), 3)
        with self.assertRaises(E.CalcError):
            ev("inv([[1,2],[2,4]])")

    def test_calculus(self):
        self.assertAlmostEqual(float(ev("integral(x^2, x, 0, 3)")), 9, places=9)
        self.assertAlmostEqual(float(ev("integral(exp(-x^2), x, -inf, inf)")), math.sqrt(math.pi), places=7)
        self.assertAlmostEqual(float(ev("deriv(x^3, x, 2)")), 12, places=6)
        self.assertAlmostEqual(float(ev("nsolve(x^2 == 2, x, 1)")), math.sqrt(2), places=10)
        self.assertEqual(float(ev("sum(k^2, k, 1, 10)")), 385)

    def test_complex(self):
        self.assertTrue(math.isnan(float(ev("sqrt(-4)"))))
        self.assertEqual(complex(ev("sqrt(-4)", complex_ok=True)), 2j)

    def test_safety(self):
        for bad in ["__import__('os')", "open('x')", "().__class__", "lambda: 1"]:
            with self.assertRaises((E.CalcError, ValueError)):
                ev(bad)

    def test_statements(self):
        self.assertEqual(E.split_statement("f(x) = x^2"), ("func", "f", ["x"], "x^2"))
        self.assertEqual(E.split_statement("v -> km/h"), ("convert", "v", "km/h"))
        self.assertEqual(E.split_statement("a == b"), ("expr", "a == b"))


class Library(unittest.TestCase):
    def test_size(self):
        self.assertGreaterEqual(len(L.EQUATIONS), 200)
        self.assertEqual(len({e.id for e in L.EQUATIONS}), len(L.EQUATIONS))

    def test_dimensions(self):
        for eq in L.EQUATIONS:
            dims = {v["sym"]: U.KINDS[v["kind"]].dims for v in eq.vars}
            a = E.dims_of(eq.lhs, dims, strict=True)
            b = E.dims_of(eq.rhs, dims, strict=True)
            self.assertTrue(U.deq(a, b), f"{eq.id}: {U.dims_text(a)} ≠ {U.dims_text(b)}")

    def test_every_variable_solvable(self):
        """Mit Werten aus einem gueltigen Zustand laesst sich jede Variable zurueckrechnen."""
        import zlib
        for eq in L.EQUATIONS:
            rng = np.random.default_rng(zlib.crc32(eq.id.encode()))   # je Formel: unabhängig von der Reihenfolge
            for attempt in range(200):
                vals = {}
                for v in eq.vars[1:]:
                    k = U.KINDS[v["kind"]]
                    vals[v["sym"]] = float(rng.uniform(0.2, 0.9) if k.key in ("angle", "number", "strain") else rng.uniform(0.5, 3))
                first = eq.vars[0]
                roots = S.solve_for(eq, first["sym"], vals)
                r = S.pick_root(roots, U.KINDS[first["kind"]])
                if r is not None and math.isfinite(r) and r != 0:
                    break
            else:
                self.fail(f"{eq.id}: kein gültiger Zustand gefunden")
            full = {**vals, first["sym"]: r}
            for v in eq.vars:
                others = {k: x for k, x in full.items() if k != v["sym"]}
                roots = S.solve_for(eq, v["sym"], others)
                self.assertTrue(any(math.isclose(x, full[v["sym"]], rel_tol=1e-5, abs_tol=1e-9) for x in roots),
                                f"{eq.id}: {v['sym']} = {full[v['sym']]} nicht unter {roots}")

    def test_rendering(self):
        for eq in L.EQUATIONS:
            d = eq.to_dict()
            self.assertTrue(d["tex"] and d["html"], eq.id)
            self.assertNotRegex(d["tex"], r"lambda_(?!\{)")

    def test_isolate(self):
        eq = L.BY_ID["kin_v_t"]
        self.assertEqual(R.plain(eq.isolated("a")), "(v - v0) / t")
        eq = L.BY_ID["frac_KI"]
        self.assertIsNotNone(eq.isolated("a"))
        self.assertIsNone(L.BY_ID["kin_s_t"].isolated("t"))


def card(eq, target, **vars):
    """Eine Formelkarte rechnen; vars: sym=(Wert, Einheit) oder sym=Wert."""
    vs = {k: ({"value": str(v[0]), "unit": v[1]} if isinstance(v, tuple) else {"value": str(v)}) for k, v in vars.items()}
    out = S.eval_sheet({"values": [], "cards": [{"id": "c", "eq": eq, "target": target, "vars": vs}]})["cards"][0]
    assert out["status"] == "ok", out
    return out["result"]["si"]


class Chemistry(unittest.TestCase):
    def test_weak_acid(self):
        # 0,1 mol/L Essigsäure, pKs 4,76: exakt 2,883, Näherung 0,5·(4,76 + 1) = 2,88
        exact = card("ch_weak_acid_exact", "pH", pKa=4.76, c_a=(0.1, "mol/L"))
        ka = 10 ** -4.76
        self.assertAlmostEqual(exact, -math.log10((-ka + math.sqrt(ka * ka + 4 * ka * 0.1)) / 2), places=9)
        self.assertAlmostEqual(exact, 2.883, places=3)
        self.assertAlmostEqual(card("ch_weak_acid", "pH", pKa=4.76, c_a=(0.1, "mol/L")), 2.88, places=9)
        # Rückwärts: aus dem gemessenen pH die Konzentration
        self.assertAlmostEqual(card("ch_weak_acid_exact", "c_a", pKa=4.76, pH=exact) / 1000, 0.1, places=9)

    def test_weak_base_and_strong(self):
        # 0,1 mol/L Ammoniak, pKb 4,75: pH = 14 − 0,5·(4,75 + 1) = 11,125
        self.assertAlmostEqual(card("ch_weak_base", "pH", pKb=4.75, pKw=14, c_b=(0.1, "mol/L")), 11.125, places=9)
        self.assertAlmostEqual(card("ch_strong_acid", "pH", c_a=(0.01, "mol/L")), 2.0, places=9)
        self.assertAlmostEqual(card("ch_strong_base", "pH", pKw=14, c_b=(0.01, "mol/L")), 12.0, places=9)

    def test_buffer_and_dissociation(self):
        self.assertAlmostEqual(card("ch_hh", "pH", pKa=4.76, c_A=(0.1, "mol/L"), c_HA=(0.1, "mol/L")), 4.76, places=9)
        self.assertAlmostEqual(card("ch_alpha", "alpha_d", pKa=4.76, pH=4.76), 0.5, places=9)
        # Pufferkapazität bei pH = pKs: ln10 · c / 4
        self.assertAlmostEqual(card("ch_buffer_cap", "beta_p", c_t=(0.1, "mol/L"), pKa=4.76, pH=4.76) / 1000,
                               math.log(10) * 0.1 / 4, places=9)

    def test_nernst_and_thermo(self):
        # Cu²⁺/Cu, E° = 0,34 V, z = 2, Q = 1/[Cu²⁺] = 100, 25 °C: E = 0,34 − 0,05916 V
        u = card("ch_nernst", "U", U_0=(0.34, "V"), z_e=2, T=(298.15, "K"), Q_r=100)
        self.assertAlmostEqual(u, 0.34 - 8.314462618 * 298.15 / (2 * 96485.33212) * math.log(100), places=9)
        self.assertAlmostEqual(u, 0.2808, places=4)
        dg = card("ch_gibbs", "dG", dH=(-92.2, "kJ/mol"), T=(298.15, "K"), dS=(-198.7, "J/(mol*K)"))
        self.assertAlmostEqual(dg, -92200 + 298.15 * 198.7, places=6)
        k = card("ch_dG_K", "K_eq", dG_0=(-32.96, "kJ/mol"), T=(298.15, "K"))
        self.assertAlmostEqual(math.log(k), 32960 / (8.314462618 * 298.15), places=6)

    def test_radioactivity_and_colligative(self):
        # C-14, Halbwertszeit 5730 a: nach 5730 a ist die Aktivität halb so gross
        a = card("nuc_activity_t", "A_act", A_0=(100, "Bq"), t=(5730, "a"), T_half=(5730, "a"))
        self.assertAlmostEqual(a, 50, places=9)
        self.assertAlmostEqual(card("nuc_halflife", "lambda_d", T_half=(1, "s")), math.log(2), places=12)
        # 1 mol/kg NaCl (i = 2) in Wasser, K_f = 1,86 K·kg/mol: ΔT = 3,72 K
        self.assertAlmostEqual(card("ch_fp", "dT_f", i_vh=2, K_f=(1.86, "K*kg/mol"), b_m=(1, "mol/kg")), 3.72, places=9)

    def test_every_equation_and_constant_sourced(self):
        import labcite
        for eq in L.EQUATIONS:
            d = eq.to_dict()
            self.assertTrue(d["source"] and d["source"].get("title"), eq.id)
            self.assertFalse(labcite.errors(d["source"]), eq.id)
            self.assertTrue(d["source_short"], eq.id)
        names = {c["name"] for c in U.constants_list()}
        self.assertEqual(names, set(U.CONSTANTS))
        for c in U.constants_list():
            self.assertTrue(c["source"].get("title"), c["name"])
            self.assertFalse(labcite.errors(c["source"]), c["name"])

    def test_codata_2022(self):
        self.assertEqual(U.CONSTANTS["eps0"][0], 8.8541878188e-12)
        self.assertEqual(U.CONSTANTS["m_e"][0], 9.1093837139e-31)
        self.assertAlmostEqual(U.CONSTANTS["Rgas"][0], 6.02214076e23 * 1.380649e-23, places=8)
        self.assertAlmostEqual(U.CONSTANTS["F_c"][0], 6.02214076e23 * 1.602176634e-19, places=4)


class Sheet(unittest.TestCase):
    STATE = {"values": [{"id": "1", "sym": "v", "kind": "velocity", "value": "72", "unit": "km/h"},
                        {"id": "2", "sym": "t", "kind": "time", "value": "8", "unit": "s"},
                        {"id": "3", "sym": "m", "kind": "mass", "value": "1.2", "unit": "t"}],
             "cards": []}

    def test_derive_v_t_gives_a(self):
        out = S.eval_sheet(self.STATE)
        der = {(d["sym"], d["kind"]): d for d in out["derived"]}
        self.assertAlmostEqual(der[("a", "acceleration")]["si"], 2.5)
        self.assertAlmostEqual(der[("F", "force")]["si"], 3000)          # weiter: F = m a
        self.assertEqual(der[("a", "acceleration")]["prov"]["eq"], "kin_a_mean")

    def test_card_auto_and_target(self):
        st = {**self.STATE, "cards": [{"id": "c", "eq": "dyn_newton", "target": "m", "vars": {}},
                                      {"id": "k", "eq": "frac_KI", "vars": {"Y": {"value": "1.12"},
                                       "sigma": {"value": "200", "unit": "MPa"}, "K_I": {"value": "50", "unit": "MPa*m^0.5"}}}]}
        out = S.eval_sheet(st)
        c, k = out["cards"]
        self.assertEqual(c["status"], "ok")
        self.assertAlmostEqual(c["result"]["si"], 1200)
        self.assertEqual(k["result"]["sym"], "a")
        self.assertAlmostEqual(k["result"]["si"], (50 / (1.12 * 200)) ** 2 / math.pi, places=9)
        self.assertIn("MPa", k["sub_tex"])

    def test_card_cycle_marked(self):
        """A4: Karte A rechnet F aus a, Karte B rechnet a aus F → Zirkelbezug wird gemeldet; Einzelkarte nicht."""
        st = {**self.STATE, "cards": [{"id": "A", "eq": "dyn_newton", "target": "F", "vars": {}},
                                      {"id": "B", "eq": "dyn_newton", "target": "a", "vars": {}}]}
        sh = S.Sheet(st).run()
        a, b = sh.cards_out
        self.assertEqual(sh.card_graph(), {"A": {"B"}, "B": {"A"}})
        self.assertEqual((a.get("cycle"), b.get("cycle")), (["B"], ["A"]))
        self.assertIn("Zirkelbezug", a["notes"][0])
        one = S.Sheet({**self.STATE, "cards": st["cards"][:1]}).run()
        self.assertNotIn("cycle", one.cards_out[0])

    def test_missing(self):
        out = S.eval_sheet({"values": [], "cards": [{"id": "x", "eq": "en_kin", "vars": {"m": {"value": "2", "unit": "kg"}}}]})
        self.assertEqual(out["cards"][0]["status"], "missing")
        self.assertEqual([m["sym"] for m in out["cards"][0]["missing"]], ["v"])

    def test_numeric_and_units(self):
        st = {"values": [], "cards": [{"id": "x", "eq": "kin_s_t", "target": "t", "vars": {"s": {"value": "100", "unit": "m"},
              "v0": {"value": "5", "unit": "m/s"}, "a": {"value": "2", "unit": "m/s^2"}}}]}
        o = S.eval_sheet(st)["cards"][0]
        self.assertAlmostEqual(o["result"]["si"], (-5 + math.sqrt(25 + 400)) / 2, places=8)
        self.assertTrue(o["numeric"])

    def test_bad_unit_reported(self):
        out = S.eval_sheet({"values": [{"id": "9", "sym": "v", "kind": "velocity", "value": "3", "unit": "kg"}], "cards": []})
        self.assertIn("9", out["errors"])

    def test_goal(self):
        g = S.goal(self.STATE, "P", "power")
        self.assertTrue(g["rows"])
        self.assertEqual(g["rows"][0]["missing"], [])            # P = W/t mit W = F s ... oder P = F v
        g = S.goal({"values": [], "cards": []}, "K_I", None)
        self.assertEqual(g["kind"], "stress_int")
        self.assertIn("frac_KI", [r["eq"] for r in g["rows"]])

    def test_curve(self):
        st = {"values": [], "cards": [{"id": "k", "eq": "frac_KI", "vars": {"Y": {"value": "1"}, "sigma": {"value": "100", "unit": "MPa"},
                                                                           "K_I": {"value": "30", "unit": "MPa*m^0.5"}}}]}
        cv = S.card_curve(st, "k", "sigma", 100, 400, 5)
        self.assertEqual(len(cv["y"]), 5)
        self.assertGreater(cv["y"][0], cv["y"][-1])


class ConsoleAndPlots(unittest.TestCase):
    def test_console(self):
        ctx = {"vars": {"A": [[1, 2], [3, 4]]}, "funcs": {"f": {"args": ["x"], "body": "x^2 - 2"}},
               "quantities": {"v": {"si": 20, "kind": "velocity"}, "t": {"si": 8, "kind": "time"}}}
        r = C.evaluate_line({**ctx, "line": "v/t"})
        self.assertEqual(r["unit"], "m/s²")
        self.assertEqual(r["result"]["text"], "2.5")
        r = C.evaluate_line({**ctx, "line": "v -> km/h"})
        self.assertEqual(r["result"]["text"], "72")
        r = C.evaluate_line({**ctx, "line": "b = inv(A)"})
        self.assertEqual(r["kind"], "assign")
        np.testing.assert_allclose(r["store"], [[-2, 1], [1.5, -0.5]])
        r = C.evaluate_line({**ctx, "line": "g(x) = f(x) + 1"})
        self.assertEqual(r["kind"], "func")
        with self.assertRaises(E.CalcError):
            C.evaluate_line({**ctx, "line": "v -> kg"})

    def test_analysis_and_fit(self):
        ctx = P.make_ctx({})
        r = P.analyze({"fn": {"expr": "x^2 - 2"}, "what": "roots", "a": -5, "b": 5}, ctx)
        np.testing.assert_allclose([p["x"] for p in r["points"]], [-math.sqrt(2), math.sqrt(2)], rtol=1e-8)
        r = P.analyze({"fn": {"expr": "tan(x)"}, "what": "roots", "a": -2, "b": 2}, ctx)
        self.assertEqual(len(r["points"]), 1)                     # Polstellen sind keine Nullstellen
        r = P.analyze({"fn": {"expr": "x^3 - 3x"}, "what": "extrema", "a": -5, "b": 5}, ctx)
        self.assertEqual([p["type"] for p in r["points"]], ["max", "min"])
        f = P.fit([1, 2, 3, 4], [2, 4, 6, 8], "lin")
        self.assertAlmostEqual(f["params"]["k"], 2)
        self.assertAlmostEqual(f["r2"], 1)
        f = P.fit([1, 2, 3], [2.7183, 7.389, 20.09], "exp")
        self.assertAlmostEqual(f["params"]["b"], 1, places=3)


class Bundle(unittest.TestCase):
    REQ = {"sheet": {"values": [{"id": "1", "sym": "v", "kind": "velocity", "value": "72", "unit": "km/h"},
                                {"id": "2", "sym": "t", "kind": "time", "value": "8", "unit": "s"}],
                     "cards": [{"id": "c1", "eq": "kin_a_mean", "vars": {}}]},
           "plots": [{"functions": [{"kind": "fx", "expr": "x^2"}], "view": {"xmin": -2, "xmax": 2, "ymin": -1, "ymax": 4}}],
           "console": [{"tex": "1 + 1", "result_tex": "2"}], "matrices": {"A": [[1, 2], [3, 4]]}, "ctx": {}}

    def test_build_and_rebuild(self):
        d = B.build(self.REQ, lang="de")
        kinds = [(i["kind"], i.get("id")) for i in d["items"]]
        for want in [("text", "rechenweg"), ("table", "groessen"), ("figure", "diagramm1"), ("text", "nebenrechnungen"),
                     ("text", "matrizen"), ("values", None)]:
            self.assertIn(want, kinds)
        work = base64.b64decode(d["files"]["text-rechenweg.tex"]).decode()
        self.assertIn(r"\frac{72\,\mathrm{km}/\mathrm{h}}{8\,\mathrm{s}} = 2{,}5", work)
        self.assertNotIn("amsmath", work)
        en = B.build({**d["source"]["request"], "lang": "en"}, lang="en")
        self.assertIn("2.5", base64.b64decode(en["files"]["text-rechenweg.tex"]).decode())

    def test_sources_cited(self):
        req = {"envs": [{"id": "e1", "name": "U1", "items": [
            {"id": "l1", "type": "calc", "src": "RT = Rgas*298.15", "report": True},
            {"id": "c1", "type": "card", "eq": "ch_nernst", "target": "U",
             "vars": {"U_0": {"value": "0.34", "unit": "V"}, "z_e": {"value": "2"}, "T": {"value": "298.15", "unit": "K"},
                      "Q_r": {"value": "100"}}}]}], "values": []}
        d = B.build(req, lang="de", include={"plots": False})
        bib = base64.b64decode(d["files"]["refs.bib"]).decode()
        self.assertIn("@book{rf-bard", bib)                    # Nernst-Gleichung
        self.assertIn("@article{rf-codata2022", bib)           # R und F aus CODATA 2022
        self.assertIn("RevModPhys.97.025002", bib)
        work = base64.b64decode(d["files"]["text-rechenweg.tex"]).decode()
        self.assertRegex(work, r"\\cite\{rf-bard,rf-codata2022\}")
        side = base64.b64decode(d["files"]["text-nebenrechnungen.tex"]).decode()
        self.assertIn(r"\mbox{\cite{rf-codata2022}}", side)

    def test_nothing(self):
        with self.assertRaises(ValueError):
            B.build({"sheet": {"values": [], "cards": []}}, include={"plots": False})


class Server(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from rechner import server
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def call(self, path, body=None, origin=None):
        url = f"http://127.0.0.1:{self.port}{path}"
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **({"Origin": origin} if origin else {})})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read() or b"{}") if path.startswith("/api") else r.read()
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_meta_and_page(self):
        code, m = self.call("/api/meta")
        self.assertEqual(code, 200)
        self.assertGreaterEqual(len(m["equations"]), 200)
        code, page = self.call("/")
        self.assertIn(b"Rechner", page)

    def test_eval_and_errors(self):
        code, r = self.call("/api/eval", {"line": "2+2"})
        self.assertEqual((code, r["result"]["text"]), (200, "4"))
        code, r = self.call("/api/eval", {"line": "2+"})
        self.assertEqual(code, 400)
        code, r = self.call("/api/eval", {"line": "1"}, origin="http://evil.example")
        self.assertEqual(code, 403)

    def test_bundle_endpoints(self):
        code, b = self.call("/api/bundle", {**Bundle.REQ, "lang": "de"})
        self.assertEqual(code, 200, b)
        code, b2 = self.call("/api/bundle/rebuild", {"source": b["source"], "lang": "en"})
        self.assertEqual(code, 200, b2)
        self.assertEqual(b2["lang"], "en")


class DatasetRoute(unittest.TestCase):
    """DP-M6: a dataset of the Datenaufbereitung as table in the graph (live / pinned)."""

    def setUp(self):
        import tempfile
        from labproject import ModuleEnvs
        from rechner import server
        self.server, self.tmp = server, tempfile.TemporaryDirectory()
        self.old = server.ENVS
        server.ENVS = ModuleEnvs(Path(self.tmp.name), "rechner")
        server.ENVS.ensure()

    def tearDown(self):
        self.server.ENVS = self.old
        self.tmp.cleanup()

    def publish(self, F, share=None, recipients=("rechner",)):
        import labdataset as DS
        from labshare import Sharebox
        e = self.server.ENVS
        ds = DS.from_columns("Zugprobe", [{"key": "eps", "name": "ε", "unit": "%", "role": "x", "values": [0, 0.1, 0.2]},
                                          {"key": "sigma", "name": "σ", "unit": "MPa", "role": "y", "values": F},
                                          {"key": "note", "name": "Notiz", "dtype": "text", "values": ["a", "b", "c"]}],
                             flags=[{"row": 2, "code": "outlier", "excluded": True}])
        return Sharebox(e.suite, e.project).publish_dataset({"module": "datenaufbereitung", "env": "e1", "env_name": "Prüfung"},
                                                            "Zugprobe", ds, list(recipients), share_id=share)

    def test_list_live_pin(self):
        env = self.publish([0.0, 100.0, 200.0])
        other = self.publish([0.0, 1.0, 2.0], recipients=("tga",))         # not addressed to the Rechner – readable (I-01)
        sid = env["id"]
        out = self.server.dataset_route({"list": True})
        self.assertEqual(sorted(d["id"] for d in out["datasets"]), sorted([sid, other["id"]]))
        out["datasets"] = [d for d in out["datasets"] if d["id"] == sid]
        imp = self.server.ENVS.route("datasets", {}, list)["datasets"]        # I-02: import window, own first
        self.assertEqual([(d["id"], d["for_me"]) for d in imp], [(sid, True), (other["id"], False)])
        self.assertEqual(out["datasets"][0]["columns"][1]["unit"], "MPa")
        r = self.server.dataset_route({"id": sid, "mode": "live", "keys": ["eps", "sigma"]})
        self.assertEqual((r["version"], r["status"]), (1, "current"))
        self.assertEqual(r["cols"][1]["values"], [0.0, 100.0, None])         # excluded row stays out
        self.publish([0.0, 110.0, 220.0], share=sid)
        live = self.server.dataset_route({"id": sid, "mode": "live", "keys": ["sigma"]})
        pin = self.server.dataset_route({"id": sid, "mode": "pin", "version": 1, "keys": ["sigma"]})
        self.assertEqual((live["version"], live["cols"][0]["values"][1]), (2, 110.0))
        self.assertEqual((pin["version"], pin["latest"], pin["status"], pin["cols"][0]["values"][1]), (1, 2, "update", 100.0))
        from labproject import EnvError
        with self.assertRaises(EnvError):
            self.server.dataset_route({"id": sid, "keys": ["nope"]})
        with self.assertRaises(EnvError):
            self.server.dataset_route({"id": "s-00000000"})
        # the graph draws the converted table like any table
        g = G.compute({"rows": [{"id": "d", "kind": "table", "table": {"cols": [{"name": "eps", "values": ["0", "0.1", ""]},
                                                                                  {"name": "sigma", "values": ["0", "110", ""]}]}}]})
        self.assertEqual(g["rows"]["d"]["series"][0]["y"], [0.0, 110.0])


from rechner import graph as G  # noqa: E402
from rechner import workspace as W  # noqa: E402


class Workspace(unittest.TestCase):
    REQ = {"values": [{"id": "v", "sym": "v", "kind": "velocity", "value": "72", "unit": "km/h", "scope": "all"},
                      {"id": "t", "sym": "t", "kind": "time", "value": "8", "unit": "s", "scope": ["e1"]},
                      {"id": "m", "sym": "m", "kind": "mass", "value": "1.2", "unit": "t", "scope": ["e2"]}],
           "envs": [{"id": "e1", "name": "Bremsen", "items": [
                         {"id": "c1", "type": "calc", "src": "v/t"},
                         {"id": "c2", "type": "calc", "src": "k = 2*v"},
                         {"id": "c3", "type": "calc", "src": "k/2 -> km/h"}]},
                    {"id": "e2", "name": "Energie", "items": [
                         {"id": "k1", "type": "card", "eq": "en_kin", "vars": {}},
                         {"id": "c4", "type": "calc", "src": "v/t"}]}],
           "angle": "rad", "lang": "de"}

    def test_scope(self):
        o = W.evaluate(self.REQ)
        e1, e2 = o["envs"]["e1"], o["envs"]["e2"]
        self.assertAlmostEqual(e1["lines"]["c1"]["result"]["value"], 2.5)
        self.assertEqual(e1["lines"]["c3"]["result"]["text"], "72")
        self.assertIn("error", e2["lines"]["c4"])                   # t gilt nur in e1
        card = e2["cards"][0]
        self.assertEqual(card["status"], "ok")
        self.assertAlmostEqual(card["result"]["si"], 0.5 * 1200 * 20 ** 2)
        self.assertEqual({k["sym"] for k in o["global"]}, {"v"})
        self.assertNotIn("m", {k["sym"] for k in e1["known"]})

    def test_origin_in_report(self):
        """A5: übernommene Grösse nennt im Bericht Modul, Umgebung, Freigabe und Version (gepinnt)."""
        og = {"module": "elementrechner", "module_name": "Elementrechner", "env_name": "Standard", "share": "s-1234abcd",
              "version": 3}
        req = {**self.REQ, "values": [dict(self.REQ["values"][0], origin=og)] + self.REQ["values"][1:]}
        d = B.build(req, lang="de", include={"plots": False})
        tab = base64.b64decode(d["files"]["groessen.tex"]).decode("utf-8")
        self.assertIn("aus Elementrechner, Standard, s-1234abcd v3", tab)
        req["values"][0]["origin"] = dict(og, edited=True)
        tab = base64.b64decode(B.build(req, lang="de", include={"plots": False})["files"]["groessen.tex"]).decode("utf-8")
        self.assertIn("hier geändert", tab)
        req["values"][0]["origin"] = {"index": "g-1a2b3c4d", "from": "tga · Standard"}       # A7
        tab = base64.b64decode(B.build(req, lang="de", include={"plots": False})["files"]["groessen.tex"]).decode("utf-8")
        self.assertIn("Projektindex g-1a2b3c4d (tga", tab)

    def test_line_variables_right_assign_units_and_export(self):
        """50/3 = u legt u an; u behält die Einheit; mit export: true gilt u auch auf den anderen Blättern."""
        from labcalc import expr as LE
        self.assertEqual(LE.split_statement("50/3 = u"), ("assign", "u", "50/3"))
        self.assertEqual(LE.split_statement("v*t = s_1"), ("assign", "s_1", "v*t"))
        self.assertEqual(LE.split_statement("u = 50/3"), ("assign", "u", "50/3"))
        self.assertEqual(LE.split_statement("a == b")[0], "expr")
        self.assertEqual(LE.split_statement("f(x) = x^2")[0], "func")
        req = {"values": [{"id": "v", "sym": "v", "kind": "velocity", "value": "72", "unit": "km/h", "scope": "all"},
                          {"id": "t", "sym": "t", "kind": "time", "value": "10", "unit": "s", "scope": ["e1"]}],
               "envs": [{"id": "e1", "name": "A", "items": [
                             {"id": "a1", "type": "calc", "src": "50/3 = u"},
                             {"id": "a2", "type": "calc", "src": "u*3"},
                             {"id": "a3", "type": "calc", "src": "v*t = s_w", "export": True},
                             {"id": "a4", "type": "calc", "src": "s_w / (t/2.5)"}]},
                        {"id": "e2", "name": "B", "items": [
                             {"id": "b1", "type": "calc", "src": "s_w * 2"},
                             {"id": "b2", "type": "calc", "src": "u"}]}],
               "angle": "rad", "lang": "de"}
        o = W.evaluate(req)
        e1, e2 = o["envs"]["e1"], o["envs"]["e2"]
        self.assertEqual(e1["lines"]["a1"]["kind"], "assign")
        self.assertAlmostEqual(e1["lines"]["a2"]["result"]["value"], 50.0)
        self.assertEqual(e1["lines"]["a3"]["unit"], "m")                    # 20 m/s · 10 s
        self.assertEqual(e1["lines"]["a4"]["unit"], "m/s")                  # Einheit bleibt an s_w
        self.assertAlmostEqual(e1["lines"]["a4"]["result"]["value"], 50.0)
        self.assertAlmostEqual(e2["lines"]["b1"]["result"]["value"], 400.0)  # s_w von Blatt A, mit Einheit
        self.assertEqual(e2["lines"]["b1"]["unit"], "m")
        self.assertIn("error", e2["lines"]["b2"])                           # u ist nicht weitergegeben
        self.assertEqual(e2["imported"], {"s_w": "e1"})
        self.assertEqual(o["exports"], {"s_w": {"env": "e1", "line": "a3", "unit": "m"}})
        d = B.build(req, lang="de", include={"plots": False})                # Bericht rechnet ebenso
        self.assertTrue(d["files"])

    def test_legacy(self):
        r = W.from_legacy({"sheet": {"values": [{"id": "a", "sym": "v", "kind": "velocity", "value": "1", "unit": "m/s"}],
                                     "cards": [{"id": "k", "eq": "en_kin"}]}})
        self.assertEqual(r["values"][0]["scope"], "all")
        self.assertEqual(r["envs"][0]["items"][0]["type"], "card")


class Solve(unittest.TestCase):
    """S-01/S-02: Gleichungen und Gleichungssysteme in Rechenzeilen."""

    def run_lines(self, lines, values=(), picks=None, cplx=False):
        items = [{"id": f"l{i}", "type": "calc", "src": s, **({"pick": picks[i]} if picks and i in picks else {})}
                 for i, s in enumerate(lines)]
        o = W.evaluate({"values": list(values), "envs": [{"id": "e1", "name": "A", "items": items}], "angle": "rad",
                        "lang": "de", "complex": cplx})
        return [o["envs"]["e1"]["lines"][f"l{i}"] for i in range(len(lines))]

    def test_split(self):
        self.assertEqual(LE_split("x^2 - 3 + x = 0"), ("equation", "x^2 - 3 + x", "0", [], None))
        self.assertEqual(LE_split("t^2 = 9, t > 0")[3], ["t > 0"])
        self.assertEqual(LE_split("x + y = 3; x - y = 1"), ("system", [("x + y", "3"), ("x - y", "1")]))
        self.assertEqual(LE_split("sin(x) = 0.5")[0], "equation")
        self.assertEqual(LE_split("f(x) = x^2")[0], "func")
        self.assertEqual(LE_split("u = 50/3")[0], "assign")
        self.assertEqual(LE_split("2x = 4 -> cm")[4], "cm")

    def test_quadratic_exact_and_pick(self):
        r = self.run_lines(["x^2 -3 +x =0", "x_1 + x_2", "x"], picks={0: 2})
        self.assertEqual(r[0]["kind"], "solve")
        self.assertEqual([s["name"] for s in r[0]["solutions"]], ["x_1", "x_2"])
        self.assertEqual(r[0]["solutions"][1]["exact"], "(−1 + √13)/2")
        self.assertIn(r"\frac{-1 + \sqrt{13}}{2}", r[0]["result_tex"])
        self.assertAlmostEqual(r[1]["result"]["value"], -1.0)                 # x_1 + x_2 = −b/a
        self.assertAlmostEqual(r[2]["result"]["value"], (-1 + math.sqrt(13)) / 2)
        r = self.run_lines(["x^2 -3 +x =0", "x"])                              # ohne Wahl bleibt x offen
        self.assertIn("error", r[1])

    def test_kinds_of_equations(self):
        r = self.run_lines(["y = 2y - 3", "z^2 = z", "t^2 = 9, t > 0", "x^3 - 6x^2 + 11x - 6 = 0", "exp(s) = 1e6",
                            "2 + 2 = 5", "q^2 + 1 = 0", "w - w = 1", "2x + 3 = 4"])
        self.assertAlmostEqual(r[0]["result"]["value"], 3.0)                  # x = … mit x rechts: Gleichung
        self.assertEqual([s["text"] for s in r[1]["solutions"]], ["0", "1"])
        self.assertEqual([s["text"] for s in r[2]["solutions"]], ["3"])
        self.assertEqual([s["text"] for s in r[3]["solutions"]], ["1", "2", "3"])
        self.assertAlmostEqual(r[4]["solutions"][0]["value"], math.log(1e6), places=9)
        self.assertEqual((r[5]["kind"], r[5]["truth"]), ("check", False))
        self.assertEqual(r[6]["status"], "none")
        self.assertTrue(any("komplex" in n for n in r[6]["notes"]))
        self.assertEqual(r[7]["status"], "none")
        self.assertEqual(r[8]["solutions"][0]["exact"], "1/2")
        c = self.run_lines(["q^2 + 1 = 0"], cplx=True)[0]
        self.assertEqual(len(c["solutions"]), 2)

    def test_units_of_the_unknown(self):
        vals = [{"id": "m", "sym": "m_a", "kind": "mass", "value": "2", "unit": "kg", "scope": "all"},
                {"id": "E", "sym": "E_k", "kind": "energy", "value": "100", "unit": "J", "scope": "all"}]
        r = self.run_lines(["0.5*m_a*v^2 = E_k, v > 0", "v -> km/h", "1/2*m_a*u^2 = E_k -> km/h"], values=vals)
        self.assertEqual(r[0]["unit"], "m/s")
        self.assertAlmostEqual(r[0]["solutions"][0]["value"], 10.0)
        self.assertAlmostEqual(r[1]["result"]["value"], 36.0)
        self.assertEqual(r[2]["unit"], "km/h")
        self.assertEqual(sorted(s["value"] for s in r[2]["solutions"]), [-36.0, 36.0])

    def test_solve_for_a_defined_name(self):
        r = self.run_lines(["w = 5", "w^2 = 16", "w^2 = 16, w"])
        self.assertEqual(r[1]["kind"], "check")
        self.assertTrue(any(", w" in n for n in r[1]["notes"]))
        self.assertEqual([s["value"] for s in r[2]["solutions"]], [-4.0, 4.0])

    def test_systems(self):
        r = self.run_lines(["a + b = 3; a - b = 1", "a*b", "2c + 3d = 1; c - d = 2", "u + v = 3; 2u + 2v = 6",
                            "u + v = 3; u + v = 4", "p^2 + q^2 = 25; p - q = 1"], picks={5: 2})
        self.assertEqual(r[0]["kind"], "system")
        self.assertEqual([v["text"] for v in r[0]["solutions"][0]["vals"]], ["2", "1"])
        self.assertAlmostEqual(r[1]["result"]["value"], 2.0)
        self.assertEqual([v["exact"] for v in r[2]["solutions"][0]["vals"]], ["7/5", "−3/5"])
        self.assertEqual(r[2]["system"]["rank"], 2)
        self.assertEqual(r[3]["status"], "infinite")
        self.assertIn("u = 3 − v", r[3]["result"]["text"])
        self.assertEqual(r[4]["status"], "none")
        self.assertEqual(len(r[5]["solutions"]), 2)
        self.assertEqual({s["name"] for s in r[5]["sets"]}, {"p_1", "q_1", "p_2", "q_2", "p", "q"})

    def test_report_shows_solutions(self):
        req = {"values": [], "envs": [{"id": "e1", "name": "A", "items": [
            {"id": "a", "type": "calc", "src": "x^2 - 3 + x = 0"}, {"id": "b", "type": "calc", "src": "x + y = 3; x - y = 1"}]}],
            "angle": "rad", "lang": "de"}
        d = B.build(req, lang="de", include={"plots": False})
        side = base64.b64decode(d["files"]["text-nebenrechnungen.tex"]).decode("latin-1")
        self.assertIn(r"\Rightarrow", side)
        self.assertIn(r"\sqrt{13}", side)
        self.assertIn(r"\begin{array}{l}", side)


def LE_split(s):
    from labcalc import expr as LE
    return LE.split_statement(s)


class Graph(unittest.TestCase):
    VIEW = {"xmin": -10, "xmax": 10, "ymin": -6, "ymax": 6, "w": 800, "h": 500}

    def run_rows(self, rows, focus=None, ctx=None):
        return G.compute({"rows": rows, "view": self.VIEW, "ctx": ctx or {"angle": "rad"}, "focus": focus})

    def test_classify(self):
        self.assertEqual(G.classify("y = x^2")[0], "y")
        self.assertEqual(G.classify("f(x) = x^2")[0], "func")
        self.assertEqual(G.classify("a = 2")[0], "def")
        self.assertEqual(G.classify("x^2 + y^2 = 9")[0], "eq")
        self.assertEqual(G.classify("(cos t, sin t)")[0], "pair")
        self.assertEqual(G.classify("y1 ~ m x1 + b")[0], "reg")
        self.assertEqual(G.classify("r = 2")[0], "r")

    def test_slider_implicit_value(self):
        r = self.run_rows([{"id": "1", "src": "y = a x^2"}, {"id": "2", "src": "a = 0.5"},
                           {"id": "3", "src": "x^2 + y^2 = 9"}, {"id": "4", "src": "integral(sin(x), x, 0, pi)"},
                           {"id": "5", "src": "y = b x"}])["rows"]
        self.assertEqual(r["2"]["type"], "slider")
        self.assertEqual(r["1"]["type"], "curve")
        self.assertEqual(r["3"]["type"], "implicit")
        self.assertGreater(len(r["3"]["segs"]), 20)
        self.assertEqual(r["4"]["type"], "value")
        self.assertAlmostEqual(r["4"]["value"], 2, places=6)
        self.assertEqual(r["5"]["type"], "error")
        self.assertIn("b", r["5"]["free"])

    def test_regression_and_poi(self):
        rows = [{"id": "t", "kind": "table", "table": {"cols": [{"name": "x1", "values": ["0", "1", "2", "3"]},
                                                                {"name": "y1", "values": ["1", "3", "5", "7"]}]}},
                {"id": "r", "src": "y1 ~ m x1 + b"}, {"id": "f", "src": "y = x^2 - 4"}]
        o = self.run_rows(rows, focus="f")
        reg = o["rows"]["r"]
        self.assertEqual(reg["type"], "regression")
        self.assertAlmostEqual(reg["params"]["m"], 2, places=6)
        self.assertAlmostEqual(reg["params"]["b"], 1, places=6)
        self.assertAlmostEqual(reg["r2"], 1, places=9)
        roots = sorted(p["x"] for p in o["poi"]["points"] if p["kind"] == "root")
        self.assertEqual(len(roots), 2)
        self.assertAlmostEqual(roots[1], 2, places=5)

    def test_large_dataset_thinned_and_fitted(self):
        """G-01/G-02: 200 000 Messpunkte; gezeigt wird ausgedünnt, angepasst mit allen Werten."""
        n = 200_000
        X = np.linspace(0, 10, n)
        Y = 3.0 * X + 1.0 + np.sin(X * 50) * 0.01
        Y[5] = np.nan                                                      # ausgeschlossene Zeile
        cols = [{"key": "t", "name": "t", "unit": "s"}, {"key": "F", "name": "F", "unit": "N"}]

        def resolve(spec):
            return {"rows": n, "columns": cols, "cols": {"t": X, "F": Y}, "title": "Zug", "version": 2, "latest": 2,
                    "status": "current", "producer": {}}

        rows = [{"id": "d", "kind": "dataset", "ds": {"id": "s-1", "mode": "live", "x": "t", "y": ["F"]}},
                {"id": "f", "kind": "fit", "of": "d", "y": "F", "model": "lin", "mode": "lin", "range": None},
                {"id": "g", "kind": "fit", "of": "d", "y": "F", "model": "lin", "mode": "lin", "range": [2, 4]}]
        o = G.compute({"rows": rows, "view": {"xmin": 0, "xmax": 10, "ymin": 0, "ymax": 32, "w": 800, "h": 500},
                       "ctx": {"angle": "rad"}}, resolve=resolve)["rows"]
        s = o["d"]["series"][0]
        self.assertTrue(s["line"])                                        # viele fortlaufende Werte -> Linie
        self.assertEqual(s["n"], n - 1)
        self.assertLess(s["sent"], 5000)
        self.assertEqual(o["d"]["ds"]["units"], {"t": "s", "F": "N"})
        f = o["f"]
        self.assertEqual(f["type"], "fit")
        self.assertEqual(f["n"], n - 1)                                   # alle Werte, nicht die gezeigten
        m = next(p for p in f["params"] if p["sym"] == "m")
        self.assertAlmostEqual(m["value"], 3.0, places=3)
        self.assertEqual(m["unit"], "N/s")
        g = o["g"]
        self.assertEqual(g["range"], [2.0, 4.0])
        self.assertLess(g["n"], n // 4)
        pts = G.compute({"rows": [dict(rows[0], style="pts")], "view": {"xmin": 0, "xmax": 10, "ymin": 0, "ymax": 32,
                                                                          "w": 800, "h": 500}}, resolve=resolve)["rows"]
        self.assertFalse(pts["d"]["series"][0]["line"])
        self.assertLessEqual(pts["d"]["series"][0]["sent"], G.MAX_CELLS)
        bad = G.compute({"rows": [{"id": "x", "kind": "fit", "of": "nope", "model": "lin"}]})["rows"]
        self.assertEqual(bad["x"]["type"], "error")

    def test_fit_on_table_into_bundle(self):
        rows = [{"id": "t", "kind": "table", "table": {"cols": [{"name": "T", "values": ["300", "320", "340", "360"]},
                                                                {"name": "k", "values": ["0.0012", "0.0050", "0.0178", "0.0553"]}]}},
                {"id": "f", "kind": "fit", "of": "t", "y": "k", "model": "arrh", "mode": "lin"}]
        o = self.run_rows(rows)["rows"]["f"]
        self.assertEqual(o["type"], "fit")
        ea = next(p for p in o["params"] if p["sym"] == "Ea")
        self.assertGreater(ea["value"], 50)
        req = {"envs": [], "values": [], "plots": [{"rows": rows, "view": {"xmin": 290, "xmax": 370, "ymin": 0, "ymax": 0.06}}]}
        d = B.build(req, lang="de")
        tex = "".join(base64.b64decode(v).decode("utf-8", "replace") for k, v in d["files"].items() if k.endswith(".tex"))
        self.assertIn("Arrhenius", tex)

    def test_quantities_in_ctx(self):
        o = self.run_rows([{"id": "1", "src": "y = v x"}], ctx={"angle": "rad", "quantities": {"v": {"si": 3, "kind": "velocity"}}})
        self.assertEqual(o["rows"]["1"]["type"], "curve")
        ys = [y for x, y in zip(o["rows"]["1"]["x"], o["rows"]["1"]["y"]) if x is not None and abs(x - 1) < 0.05]
        self.assertTrue(ys and abs(ys[0] - 3) < 0.2)


class Recognize(unittest.TestCase):
    def best(self, name, unit=""):
        from rechner import recognize as RC
        r = RC.recognize(name, unit)
        return r, (r["best"]["sym"], r["best"]["kind"]) if r["best"] else None

    def test_names_typos_synonyms(self):
        for name, unit, want in [("Geschwindigkeit", "m/s", ("v", "velocity")), ("Geschweindigkeit", "m/s", ("v", "velocity")),
                                 ("Tempo", "km/h", ("v", "velocity")), ("Gewicht", "kg", ("m", "mass")),
                                 ("Spannung", "MPa", ("sigma", "stress")), ("Spannung", "V", ("U", "voltage")),
                                 ("Masse Auto", "t", ("m", "mass")), ("v", "", ("v", "velocity"))]:
            r, got = self.best(name, unit)
            self.assertEqual(got, want, name)
            self.assertTrue(r["confident"], name)

    def test_unit_only(self):
        r, got = self.best("x1", "mm")
        self.assertFalse(r["confident"])
        self.assertEqual(r["kind_guess"], "length")
        r, _ = self.best("Linienlast", "kN/m^2")
        self.assertIn(r["kind_guess"], r["unit_kinds"] or [r["kind_guess"]])
        r, _ = self.best("Massenbelag", "kg/m")
        self.assertTrue(r["kind_guess"].startswith("dim:"))
        # U-01: Leitfähigkeit und pH über die Einheit
        r, _ = self.best("Probe 3", "µS/cm")
        self.assertEqual(r["kind_guess"], "el_conductivity")
        r, _ = self.best("x2", "pH")
        self.assertEqual(r["unit_kinds"], ["ph", "number"])

    def test_ph_value_feeds_equations(self):
        """U-01: Ein pH-Wert (Art ph, Einheit pH) speist die pH-Formeln der Bibliothek wie eine Zahl."""
        r, got = self.best("pH", "pH")
        self.assertEqual(got[0], "pH")
        ws = {"values": [{"id": "1", "sym": "pH", "kind": "ph", "value": "3", "unit": "pH"},
                         {"id": "2", "sym": "c_std", "kind": "concentration", "value": "1", "unit": "mol/L"}],
              "envs": [{"id": "e", "items": []}]}
        o = W.evaluate(ws)
        self.assertEqual(o["errors"], {})
        der = {d["sym"]: d for d in o["envs"]["e"]["derived"]}
        self.assertAlmostEqual(der["c_H"]["si"], 1.0)                 # 10⁻³ mol/L = 1 mol/m³
        self.assertEqual(der["c_H"]["prov"]["eq"], "ch_pH")

    def test_named_variables(self):
        ws = {"values": [{"id": "1", "sym": "Geschweindigkeit", "as": "v", "kind": "velocity", "value": "20", "unit": "m/s"},
                         {"id": "2", "sym": "Fahrzeit", "as": "t", "kind": "time", "value": "8", "unit": "s"},
                         {"id": "3", "sym": "Länge Probe", "kind": "length", "value": "50", "unit": "mm"},
                         {"id": "4", "sym": "Massenbelag", "kind": "dim:kg/m", "value": "2", "unit": "g/mm"}],
              "envs": [{"id": "e", "items": [{"id": "l1", "type": "calc", "src": "Geschweindigkeit/Fahrzeit"},
                                             {"id": "l2", "type": "calc", "src": "v*t"},
                                             {"id": "l3", "type": "calc", "src": "Massenbelag * Länge_Probe"},
                                             {"id": "k", "type": "card", "eq": "en_kin", "vars": {"m": {"value": "2", "unit": "kg"}}}]}]}
        o = W.evaluate(ws)
        self.assertEqual(o["errors"], {})
        e = o["envs"]["e"]
        self.assertAlmostEqual(e["lines"]["l1"]["result"]["value"], 2.5)
        self.assertAlmostEqual(e["lines"]["l2"]["result"]["value"], 160)
        self.assertAlmostEqual(e["lines"]["l3"]["result"]["value"], 0.1)
        self.assertEqual(e["lines"]["l3"]["unit"], "kg")
        self.assertAlmostEqual(e["cards"][0]["result"]["si"], 400)
        self.assertIn("a", [d["sym"] for d in e["derived"]])
        self.assertEqual(S.goal({"values": ws["values"]}, "Geschweindigkeit")["kind"], "velocity")
        dup = W.evaluate({"values": [{"id": "1", "sym": "Tempo", "as": "v", "kind": "velocity", "value": "1", "unit": "m/s"},
                                     {"id": "2", "sym": "v", "kind": "velocity", "value": "2", "unit": "m/s"}],
                          "envs": [{"id": "e", "items": []}]})
        self.assertIn("Tempo", dup["errors"]["2"])
        tex = R.sym_tex("Länge_Probe")
        self.assertIn(r"\mbox{Länge}", tex)
        d = B.build({"values": ws["values"], "envs": ws["envs"]}, lang="de", include={"plots": False})
        table = base64.b64decode(d["files"]["groessen.tex"]).decode()
        self.assertIn("Geschweindigkeit (Geschwindigkeit)", table)
        self.assertIn("Massenbelag", table)


class BundleEnvs(unittest.TestCase):
    def test_two_envs(self):
        req = {**Workspace.REQ, "envs": [
            {**Workspace.REQ["envs"][0], "items": Workspace.REQ["envs"][0]["items"] + [
                {"id": "k0", "type": "card", "eq": "en_kin", "vars": {"m": {"value": "2", "unit": "kg"}}}]},
            Workspace.REQ["envs"][1]],
            "plots": [{"title": "Parabel", "view": {"xmin": -3, "xmax": 3, "ymin": -1, "ymax": 9}, "env": "",
                       "rows": [{"id": "1", "src": "y = x^2"},
                                {"id": "t", "kind": "table", "table": {"cols": [{"name": "x1", "values": ["0", "1", "2"]},
                                                                                {"name": "y1", "values": ["0", "1.1", "3.9"]}]}},
                                {"id": "r", "src": "y1 ~ a x1^2"}],
                       "curves": [{"env": "e2", "card": "k1", "xvar": "v", "x0": 1, "x1": 30}]}]}
        d = B.build(req, lang="de")
        kinds = [(i["kind"], i.get("id")) for i in d["items"]]
        for want in [("text", "rechenweg"), ("table", "groessen"), ("figure", "diagramm1"), ("text", "nebenrechnungen"),
                     ("text", "diagramm1-anpassung"), ("values", None)]:
            self.assertIn(want, kinds)
        f = lambda n: base64.b64decode(d["files"][n]).decode()  # noqa: E731
        work = f("text-rechenweg.tex")
        self.assertIn(r"\subsubsection*{Bremsen}", work)
        self.assertIn(r"\subsubsection*{Energie}", work)
        side = f("text-nebenrechnungen.tex")
        self.assertIn(r"\textit{Bremsen}", side)
        self.assertEqual(side.count(r"\["), 3)                       # Zeile c4 (v/t in Energie) ist ein Fehler
        self.assertIn("Regression", f("text-diagramm1-anpassung.tex"))
        self.assertIn("u1-k1-m", json.dumps(d["items"]))
        self.assertTrue(any(k.startswith("data/diagramm1-kurve1") for k in d["files"]), list(d["files"]))
        again = B.build({**d["source"]["request"], "lang": "en"}, lang="en")
        self.assertIn(("figure", "diagramm1"), [(i["kind"], i.get("id")) for i in again["items"]])


class DatasetVariables(unittest.TestCase):
    """DP-11: columns of a dataset as list variables with units in the calculation lines (live / pinned)."""

    LINES = [{"id": "m", "type": "calc", "src": "mean(sigma)"}, {"id": "x", "type": "calc", "src": "max(sigma)"},
             {"id": "q", "type": "calc", "src": "sigma/eps"}, {"id": "s", "type": "calc", "src": "std(sigma)"},
             {"id": "r", "type": "calc", "src": "linreg(eps, sigma)"},
             {"id": "k", "type": "calc", "src": "E_mod = linreg(eps, sigma)[1]"},
             {"id": "f", "type": "calc", "src": "fit = linreg(eps, σ)"}, {"id": "d", "type": "calc", "src": "fit[2]"},
             {"id": "n", "type": "calc", "src": "len(sigma)"}, {"id": "c", "type": "calc", "src": "mean(sigma) -> MPa"}]

    def setUp(self):
        import tempfile
        from labproject import ModuleEnvs
        from rechner import dsvars as DV
        from rechner import server
        self.server, self.DV, self.tmp = server, DV, tempfile.TemporaryDirectory()
        self.old = server.ENVS
        server.ENVS = ModuleEnvs(Path(self.tmp.name), "rechner")
        server.ENVS.ensure()

    def tearDown(self):
        self.server.ENVS = self.old
        self.tmp.cleanup()

    def publish(self, sigma, share=None):
        """eps in %, sigma in MPa; row 3 excluded (outlier), row 4 has a gap in sigma -> rows 0..2 are used."""
        import labdataset as DS
        from labshare import Sharebox
        e = self.server.ENVS
        ds = DS.from_columns("Zugprobe", [{"key": "eps", "name": "ε", "unit": "%", "role": "x", "values": [0.1, 0.2, 0.3, 0.4, 0.5]},
                                          {"key": "sigma", "name": "σ", "unit": "MPa", "role": "y", "values": sigma},
                                          {"key": "note", "name": "Notiz", "dtype": "text", "values": list("abcde")}],
                             flags=[{"row": 3, "code": "outlier", "excluded": True}])
        return Sharebox(e.suite, e.project).publish_dataset({"module": "datenaufbereitung", "env": "e1", "env_name": "Prüfung"},
                                                            "Zugprobe", ds, ["rechner"], share_id=share)

    def req(self, binding, values=()):
        return {"values": list(values), "envs": [{"id": "e1", "name": "Zug", "items": self.LINES}], "angle": "rad",
                "lang": "de", "dsvars": [binding]}

    def run_ws(self, binding, values=()):
        return W.evaluate(self.DV.attach(self.req(binding, values), self.server.ENVS))

    def test_live_follows_pinned_stays(self):
        sid = self.publish([21.0, 41.0, 61.0, 999.0, None])["id"]
        live = {"share": sid, "mode": "live", "keys": ["eps", "sigma", "note"]}
        pin = {"share": sid, "mode": "pin", "version": 1, "keys": ["eps", "sigma"]}
        o = self.run_ws(live)
        ln = o["envs"]["e1"]["lines"]
        self.assertAlmostEqual(ln["m"]["result"]["value"], 41e6)              # MPa -> Pa, excluded row and gap dropped
        self.assertEqual(ln["m"]["unit"], "Pa")
        self.assertEqual((ln["x"]["result"]["value"], ln["x"]["unit"]), (61e6, "Pa"))
        self.assertEqual((ln["q"]["result"]["type"], ln["q"]["unit"]), ("vector", "Pa"))   # sigma/eps keeps the unit
        self.assertEqual(ln["s"]["unit"], "Pa")
        self.assertEqual(ln["n"]["result"]["value"], 3)
        self.assertAlmostEqual(ln["c"]["result"]["value"], 41)
        info = o["datasets"][0]
        self.assertEqual((info["version"], info["status"], info["rows"], info["used"], info["excluded"]), (1, "current", 5, 3, 1))
        self.assertEqual([v["name"] for v in info["vars"]], ["eps", "sigma"])
        self.assertEqual(info["missing"], ["note"])                            # text column is no list variable
        self.assertEqual(o["envs"]["e1"]["ds_used"], ["eps", "sigma"])
        self.assertNotIn("sigma", o["envs"]["e1"]["locals"])
        self.publish([31.0, 61.0, 91.0, 999.0, None], share=sid)             # version 2
        lv, pn = self.run_ws(live), self.run_ws(pin)
        self.assertAlmostEqual(lv["envs"]["e1"]["lines"]["m"]["result"]["value"], 61e6)
        self.assertAlmostEqual(pn["envs"]["e1"]["lines"]["m"]["result"]["value"], 41e6)
        self.assertEqual((lv["datasets"][0]["version"], lv["datasets"][0]["status"]), (2, "current"))
        self.assertEqual((pn["datasets"][0]["version"], pn["datasets"][0]["latest"], pn["datasets"][0]["status"]), (1, 2, "update"))
        # an own variable of the same name wins; the dataset column is reported as hidden
        own = [{"id": "s1", "sym": "sigma", "kind": "stress", "value": "5", "unit": "MPa", "scope": "all"}]
        import warnings
        with warnings.catch_warnings():                                      # std of one value: numpy warns
            warnings.simplefilter("ignore", RuntimeWarning)
            o = self.run_ws(live, own)
        self.assertAlmostEqual(o["envs"]["e1"]["lines"]["m"]["result"]["value"], 5e6)
        self.assertEqual(o["ds_shadowed"], {"sigma": ["e1"]})
        # through the HTTP route as the page calls it
        srv = ThreadingHTTPServer(("127.0.0.1", 0), self.server.Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            rq = urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}/api/workspace", data=json.dumps(self.req(pin)).encode(),
                                        headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(rq) as r:
                j = json.loads(r.read())
            self.assertAlmostEqual(j["envs"]["e1"]["lines"]["m"]["result"]["value"], 41e6)
        finally:
            srv.shutdown()
            srv.server_close()
        # gone share: error in the origin info, the lines report the unknown name
        o = self.run_ws({"share": "s-00000000", "mode": "live", "keys": ["sigma"]})
        self.assertIn("error", o["datasets"][0])
        self.assertIn("error", o["envs"]["e1"]["lines"]["m"])

    def test_linreg_units(self):
        sid = self.publish([21.0, 41.0, 61.0, 999.0, None])["id"]
        ln = self.run_ws({"share": sid, "mode": "live", "keys": ["eps", "sigma"]})["envs"]["e1"]["lines"]
        # exact line: sigma = 2e10 Pa * eps + 1e6 Pa (eps in 1, from %)
        parts = {p["name"]: p for p in ln["r"]["parts"]}
        self.assertAlmostEqual(parts["k"]["value"] / 2e10, 1, places=9)
        self.assertAlmostEqual(parts["d"]["value"] / 1e6, 1, places=6)
        self.assertAlmostEqual(parts["R2"]["value"], 1, places=12)
        self.assertEqual((parts["k"]["unit"], parts["d"]["unit"], parts["R2"]["unit"]), ("Pa", "Pa", ""))
        self.assertIn(r"\left(k,\ d,\ R^2\right)", ln["r"]["result_tex"])
        self.assertEqual((ln["k"]["unit"], ln["d"]["unit"]), ("Pa", "Pa"))     # E_mod = linreg(…)[1]; fit[2]
        self.assertAlmostEqual(ln["k"]["result"]["value"] / 2e10, 1, places=9)
        self.assertAlmostEqual(ln["d"]["result"]["value"] / 1e6, 1, places=6)
        # force over length: slope in N/m; plain lists without units stay as before
        ctx = {"vars": {"x": [0.01, 0.02, 0.03], "F": [5.0, 7.0, 9.0]}, "vdims": {"x": list(U.parse_unit("m")[1]),
                                                                          "F": list(U.parse_unit("N")[1])}}
        r = C.evaluate_line({**ctx, "line": "linreg(x, F)"})
        self.assertEqual([(p["name"], p["unit"]) for p in r["parts"]], [("k", "kg/s²"), ("d", "N"), ("R2", "")])   # N/m in SI
        self.assertAlmostEqual(r["parts"][0]["value"], 200)
        r = C.evaluate_line({"line": "linreg([1, 2, 3], [2, 4, 6])"})
        self.assertNotIn("parts", r)
        np.testing.assert_allclose(r["store"], [2, 0, 1], atol=1e-12)
        # column keys -> names: reserved names get _ds, duplicates a number
        self.assertEqual([self.DV.var_name(k, {"sigma"}) for k in ("e", "mean", "M", "sigma", "lambda")],
                         ["e_ds", "mean_ds", "M", "sigma_2", "lambda_"])

    def test_report_names_dataset_version(self):
        sid = self.publish([21.0, 41.0, 61.0, 999.0, None])["id"]
        self.publish([31.0, 61.0, 91.0, 999.0, None], share=sid)
        req = self.DV.attach(self.req({"share": sid, "mode": "live", "keys": ["eps", "sigma"]}), self.server.ENVS)
        d = B.build(req, lang="de", include={"plots": False})
        self.assertEqual(d["items"][0]["id"], "methodik")
        text = base64.b64decode(d["files"]["text-methodik.tex"]).decode("utf-8")
        self.assertIn(f"Freigabe {sid}, Version 2", text)
        self.assertIn("3 von 5 Zeilen", text)
        text.encode("latin-1")                                                 # LaTeX text: Latin-1 only
        for bad in (r"\text{", r"\ce{", r"\tfrac", r"\boldsymbol"):
            self.assertNotIn(bad, text)
        src = d["source"]["request"]
        self.assertNotIn("dsvals", src)
        self.assertEqual(src["dsvars"][0]["version"], 2)                       # A8: this report used version 2
        import labprov
        self.assertIn((sid, 2), labprov.refs_in_request(src)["shares"])
        en = B.build(self.DV.attach({**src, "lang": "en"}, self.server.ENVS), lang="en", include={"plots": False})
        self.assertIn(f"share {sid}, version 2", base64.b64decode(en["files"]["text-methodik.tex"]).decode("utf-8"))
        side = base64.b64decode(d["files"]["text-nebenrechnungen.tex"]).decode("utf-8")
        self.assertIn(r"\mathrm{Pa}", side)
        # without dataset columns in the lines: no methods text
        plain = self.DV.attach({**self.req({"share": sid, "mode": "live", "keys": ["eps"]}),
                                "envs": [{"id": "e1", "items": [{"id": "a", "type": "calc", "src": "1+1"}]}]}, self.server.ENVS)
        self.assertNotIn("text-methodik.tex", B.build(plain, lang="de", include={"plots": False})["files"])


if __name__ == "__main__":
    unittest.main()
