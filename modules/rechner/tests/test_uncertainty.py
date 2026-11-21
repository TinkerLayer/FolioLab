"""Messunsicherheit in Rechenzeilen: ±-Eingaben, Fortpflanzung durch Zeilenketten, Weitergabe, Bericht."""
import math
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "sdk" / "python"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")

from rechner import bundle as B  # noqa: E402
from rechner import lineunc as LU  # noqa: E402
from rechner import workspace as W  # noqa: E402


def run(*srcs, values=(), unc=None, extra=None, req_extra=None):
    items = [{"id": f"l{i}", "type": "calc", "src": s, **((extra or {}).get(f"l{i}") or {})} for i, s in enumerate(srcs)]
    env = {"id": "e", "name": "A", "items": items, **({"unc": unc} if unc else {})}
    o = W.evaluate({"values": list(values), "envs": [env], "lang": "de", **(req_extra or {})})
    return o["envs"]["e"]


class Parse(unittest.TestCase):
    def test_forms(self):
        p = LU.parse_pm("x = 5,0 ± 0,1 mm")
        self.assertEqual((p["name"], p["value"], p["unit"], p["part"]), ("x", 5.0, "mm", {"kind": "u", "u": 0.1}))
        p = LU.parse_pm("x = 5.0 +/- 0.2 (k=2) mm")
        self.assertEqual((p["unit"], p["part"]), ("mm", {"kind": "U", "U": 0.2, "k": 2.0}))
        p = LU.parse_pm("T = 20 ± 0,5 rect °C")
        self.assertEqual((p["unit"], p["part"]), ("°C", {"kind": "limits", "a": 0.5, "dist": "rect"}))
        self.assertEqual(LU.parse_pm("a = 1 ± 0,3 tri")["part"]["dist"], "tri")
        self.assertIsNone(LU.parse_pm("x = 3 +-2"))            # ohne ± bleibt alles beim Alten
        self.assertIsNone(LU.parse_pm("v/t"))

    def test_lines_without_pm_unchanged(self):
        o = run("x = 5", "y = 2*x", "y -> 1")
        self.assertEqual(o["lines"]["l1"]["result"]["value"], 10.0)
        self.assertNotIn("unc", o["lines"]["l1"])
        self.assertNotIn("unc", o)


class Propagation(unittest.TestCase):
    def test_pm_line_gives_gum_u(self):
        o = run("x = 5,0 ± 0,1 mm", "y = 2,0 ± 0,2 (k=2) s", "v = x/y", "v -> mm/s")
        x, y, v, vmm = (o["lines"][f"l{i}"] for i in range(4))
        self.assertAlmostEqual(x["result"]["value"], 0.005)          # Wert in SI, Einheit für die nächsten Zeilen
        self.assertEqual(x["unit"], "m")
        self.assertAlmostEqual(x["unc_in"]["u"], 0.1)
        self.assertAlmostEqual(y["unc_in"]["u"], 0.1)                # U/k
        hand = math.hypot(0.1e-3 / 2.0, 5e-3 * 0.1 / 2.0 ** 2)        # u(v)² = (u_x/y)² + (x·u_y/y²)²
        self.assertAlmostEqual(v["unc"]["u"], hand, delta=hand * 1e-6)
        self.assertEqual(v["unc"]["method"], "gum")
        self.assertAlmostEqual(vmm["unc"]["u"], hand * 1e3, delta=hand * 1e-3)   # -> mm/s rechnet die Unsicherheit mit um
        self.assertIn("±", v["text_pm"])
        self.assertEqual({b["name"] for b in v["unc"]["budget"]}, {"x", "y"})

    def test_rect_limits_and_temperature(self):
        o = run("T = 20 ± 0,5 rect °C", "T -> °C", "dT = 2*T")
        self.assertAlmostEqual(o["lines"]["l0"]["unc_in"]["u"], 0.5 / math.sqrt(3))
        self.assertAlmostEqual(o["lines"]["l1"]["unc"]["u"], 0.5 / math.sqrt(3), places=9)
        self.assertAlmostEqual(o["lines"]["l2"]["unc"]["u"], 1.0 / math.sqrt(3), places=9)

    def test_chain_keeps_correlation(self):
        # w = v·y − x mit v = x/y ist exakt 0: korreliert gerechnet bleibt u(w) = 0 (unabhängig wäre u > 0)
        o = run("x = 5 ± 0,1", "y = 2 ± 0,1", "v = x/y", "w = v*y - x", "s = x + x")
        self.assertLess(o["lines"]["l3"]["unc"]["u"], 1e-9)
        self.assertAlmostEqual(o["lines"]["l4"]["unc"]["u"], 0.2, places=9)     # nicht 0,1·√2

    def test_any_order_and_redefinition(self):
        o = run("z = y + x", "y = 5 ± 0,3", "x = 1 ± 0,4")
        self.assertAlmostEqual(o["lines"]["l0"]["unc"]["u"], 0.5, places=9)

    def test_methods_and_correlation(self):
        for m in ("mc", "gauss", "worst"):
            o = run("x = 5 ± 0,1", "y = 3*x", unc={"method": m})
            self.assertEqual(o["lines"]["l1"]["unc"]["method"], m)
        o = run("x = 5 ± 0,1 rect", "y = 3*x", unc={"method": "worst"})
        self.assertAlmostEqual(o["lines"]["l1"]["unc"]["U"], 0.3, places=9)
        o = run("a = 1 ± 0,1", "b = 1 ± 0,1", "c = a - b", unc={"method": "gum", "corr": [{"a": "a", "b": "b", "r": 1}]})
        self.assertLess(o["lines"]["l2"]["unc"]["u"], 1e-9)
        o = run("x = 5 ± 0,1", "y = 3*x", unc={"method": "off"})
        self.assertNotIn("unc", o["lines"]["l1"])
        self.assertIn("unc_in", o["lines"]["l0"])

    def test_button_parts_and_variables(self):
        reps = [2.9, 3.0, 3.1, 3.0]
        o = run("z = 3.0", "q = z*m", values=[{"id": "1", "sym": "m", "kind": "mass", "value": "2", "unit": "kg", "u": "0.01"}],
                extra={"l0": {"unc": {"parts": [{"kind": "repeats", "values": reps}]}}})
        s = (sum((r - 3.0) ** 2 for r in reps) / 3) ** 0.5
        self.assertAlmostEqual(o["lines"]["l0"]["unc_in"]["u"], s / 2)
        hand = math.hypot(2 * s / 2, 3 * 0.01)
        self.assertAlmostEqual(o["lines"]["l1"]["unc"]["u"], hand, delta=hand * 1e-6)
        self.assertEqual(o["lines"]["l1"]["unc"]["dof"] is not None, True)
        # Variable mit ± (Angabe in ihrer Einheit, hier g)
        o = run("2*m", values=[{"id": "1", "sym": "m", "kind": "mass", "value": "500", "unit": "g",
                                "unc": {"parts": [{"kind": "U", "U": 2, "k": 2}]}}])
        self.assertAlmostEqual(o["lines"]["l0"]["unc"]["u"], 2e-3, places=12)

    def test_unit_error_and_compare(self):
        o = run("q = 1 ± 0,1 kk")
        self.assertIn("kk", o["lines"]["l0"]["error"])
        items = [{"id": "a", "type": "calc", "src": "x = 4 ± 0,2"}, {"id": "b", "type": "calc", "src": "x^2"}]
        cmp = W.compare_line({"values": [], "envs": [{"id": "e", "items": items}], "lang": "de",
                              "unc_compare": {"env": "e", "line": "b"}})
        self.assertEqual(set(cmp), {"gum", "mc", "gauss", "worst"})
        self.assertAlmostEqual(cmp["gum"]["u"], 2 * 4 * 0.2, places=6)

    def test_share_to_other_sheet(self):
        e1 = {"id": "e1", "name": "A", "items": [{"id": "a", "type": "calc", "src": "x = 5 ± 0,1", "export": True}]}
        e2 = {"id": "e2", "name": "B", "items": [{"id": "b", "type": "calc", "src": "3*x"}]}
        o = W.evaluate({"values": [], "envs": [e1, e2], "lang": "de"})
        self.assertAlmostEqual(o["envs"]["e2"]["lines"]["b"]["unc"]["u"], 0.3, places=9)


class Report(unittest.TestCase):
    def test_bundle_values_budget_and_methods(self):
        req = {"values": [{"id": "1", "sym": "m", "kind": "mass", "value": "2", "unit": "kg", "u": "0.01", "scope": "all"}],
               "envs": [{"id": "e", "name": "A", "unc": {"method": "gum"}, "items": [
                   {"id": "a", "type": "calc", "src": "x = 5,0 ± 0,1 mm"}, {"id": "b", "type": "calc", "src": "F = m*x"}]}]}
        import base64
        d = B.build(req, lang="de")
        vals = next(i for i in d["items"] if i["kind"] == "values")["values"]
        keys = [v["key"] for v in vals]
        self.assertIn("unc-F-pm", keys)
        self.assertIn("unc-F-u", keys)
        self.assertIn("\\pm", next(v["latex"] for v in vals if v["key"] == "m"))   # Variable mit u in der Tabelle
        self.assertTrue(any(i.get("id") == "unc-F-budget" for i in d["items"]))
        text = lambda name: base64.b64decode(d["files"][name]).decode("utf-8")      # noqa: E731
        self.assertIn("F = m \\cdot x = (0{,}01000 \\pm 0{,}00040)", text("text-nebenrechnungen.tex"))
        self.assertIn("x = (5{,}0 \\pm 0{,}1)\\,\\mathrm{mm}", text("text-nebenrechnungen.tex"))
        self.assertIn("GUM", text("text-methodik.tex"))
        self.assertIn("unc-jcgm100", text("text-methodik.tex"))
        self.assertEqual(d["source"]["request"]["envs"][0]["unc"], {"method": "gum"})   # Angaben für Aktualisieren
        self.assertIn("±", d["source"]["request"]["envs"][0]["items"][0]["src"])
        en = B.build(req, lang="en")
        self.assertIn("Measurement uncertainties", base64.b64decode(en["files"]["text-methodik.tex"]).decode("utf-8"))


    def test_a_plot_alone_does_not_need_the_uncertainty_text(self):
        req = {"envs": [{"id": "e", "name": "A", "unc": {"method": "gum"}, "items": [
                   {"id": "a", "type": "calc", "src": "x = 5,0 ± 0,1 mm"}, {"id": "b", "type": "calc", "src": "F = 2*x"}]}],
               "plots": [{"title": "G", "view": {"xmin": 0, "xmax": 2, "ymin": 0, "ymax": 4},
                          "rows": [{"id": "r", "kind": "expr", "src": "x^2"}]}]}
        d = B.build(req, lang="de")
        by = {i.get("id"): i for i in d["items"]}
        self.assertEqual(by["diagramm1"]["needs"]["steps"], [])
        self.assertIn("unsicherheit", by["nebenrechnungen"]["needs"]["steps"])
        self.assertEqual(by["unc-F-budget"]["needs"]["steps"], ["unsicherheit"])
        steps = next(i for i in d["items"] if i["kind"] == "text" and i.get("methods"))["steps"]
        self.assertTrue(any(s.get("of") == "unsicherheit" for s in steps))
        self.assertTrue(any(s["id"] == "software" for s in steps))


class ServerRoutes(unittest.TestCase):
    def test_labunc_and_routes(self):
        import json
        import threading
        import urllib.request
        from http.server import ThreadingHTTPServer

        from rechner import server
        srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_address[1]}"

        def post(path, body):
            rq = urllib.request.Request(base + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(rq) as r:
                return json.loads(r.read())
        try:
            with urllib.request.urlopen(base + "/labunc.js") as r:
                self.assertIn(b"LabUnc", r.read())
            self.assertTrue(post("/api/unc/instruments", {})["items"])
            self.assertAlmostEqual(post("/api/unc/preview", {"value": 5, "parts": [{"kind": "U", "U": 0.2, "k": 2}]})["u"], 0.1)
            st = {"values": [], "lang": "de", "envs": [{"id": "e", "items": [{"id": "a", "type": "calc", "src": "x = 4 ± 0,2"},
                                                                            {"id": "b", "type": "calc", "src": "y = x^2"}]}]}
            self.assertAlmostEqual(post("/api/workspace", st)["envs"]["e"]["lines"]["b"]["unc"]["u"], 1.6, places=6)
            cmp = post("/api/workspace/compare", {**st, "unc_compare": {"env": "e", "line": "b"}})
            self.assertEqual(set(cmp), {"gum", "mc", "gauss", "worst"})
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
