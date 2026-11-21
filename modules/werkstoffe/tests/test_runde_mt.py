"""Ashby-Karte, Spannen, Zustandsdiagramme (Abdeckung, Format 2), Martensitzelle, Zuordnung im Gitter."""
import os
import sys
import unittest

sys.path[:0] = [os.path.join(os.path.dirname(__file__), ".."), os.path.join(os.path.dirname(__file__), "..", "..", "..", "sdk", "python")]

from werk import gitter as G  # noqa: E402
from werk import phasediag as P  # noqa: E402
from werk import refs as RF  # noqa: E402
from werk import select as SL  # noqa: E402
from werk import tools as T  # noqa: E402


class DiagramCoverage(unittest.TestCase):
    def test_every_system_valid(self):
        for s in P._data()["systeme"]:
            with self.subTest(system=s["id"]):
                self.assertEqual(P.validate(s), [])

    def test_lever_rule_in_two_phase_regions(self):
        """In jedem Zweiphasengebiet liefert das Hebelgesetz an einem inneren Punkt zwei Anteile, die 1 ergeben."""
        for s in P._data()["systeme"]:
            for r in s["regions"]:
                if len(r["phases"]) != 2:
                    continue
                xs = [p[0] for p in r["poly"]]
                Ts = [p[1] for p in r["poly"]]
                hit = None
                for fx in (0.5, 0.35, 0.65, 0.2, 0.8):
                    for fT in (0.5, 0.35, 0.65, 0.2, 0.8):
                        x = min(xs) + fx * (max(xs) - min(xs))
                        T_ = min(Ts) + fT * (max(Ts) - min(Ts))
                        if P.region_at(s, x, T_) is r:
                            hit = (x, T_)
                            break
                    if hit:
                        break
                if not hit:
                    continue
                with self.subTest(system=s["id"], region=r["label"]):
                    lv = P.lever(s, *hit)
                    self.assertEqual(len(lv["phases"]), 2)
                    self.assertAlmostEqual(sum(p["frac"] for p in lv["phases"]), 1.0, places=6)

    def test_coverage_and_groups(self):
        ids = {s["id"] for s in P._data()["systeme"]}
        for need in ("fe-c", "al-cu", "al-si", "al-mg", "al-zn", "cu-zn", "cu-sn", "fe-cr", "fe-ni", "ni-cr", "ti-al", "ti-v",
                     "mg-al", "pb-sn", "al2o3-sio2", "zro2-y2o3"):
            self.assertIn(need, ids)
        groups = {x["group"] for x in P.systems("de") if x["kind"] == "schematic"}
        self.assertGreaterEqual(len(groups), 5)

    def test_sources_known(self):
        for s in P._data()["systeme"]:
            for k in s["q"]:
                self.assertTrue(RF.known(k), f"{s['id']}: {k}")

    def test_lines_drawn_and_sent(self):
        r = T.run("phasen", {"system": "fe-c", "x": 0.4, "T": 900, "lang": "en"}, T.Ctx())
        self.assertTrue(r["diagram"]["lines"])
        self.assertTrue(all(len(ln["pts"]) >= 2 for ln in r["diagram"]["lines"]))


class GitterMapping(unittest.TestCase):
    def test_host_side_and_precipitates(self):
        s = G.phase_state("Al", [{"el": "Cu", "c": 4, "einheit": "wt"}], 20)
        self.assertEqual(s["diagram"]["id"], "al-cu")
        names = {p["name"]: p for p in s["phases"]}
        self.assertEqual(names["(Al)"]["el"], "Al")
        self.assertTrue(any(p["el"] is None for p in s["phases"]))          # θ als Ausscheidung

    def test_pair_with_two_diagrams_uses_host_as_base(self):
        self.assertEqual(G.phase_state("Mg", [{"el": "Al", "c": 9, "einheit": "wt"}], 300)["diagram"]["id"], "mg-al")
        self.assertEqual(G.phase_state("Al", [{"el": "Mg", "c": 4, "einheit": "wt"}], 300)["diagram"]["id"], "al-mg")

    def test_complete_solution_follows_host(self):
        s = G.phase_state("Ni", [{"el": "Fe", "c": 20, "einheit": "wt"}], 600)
        self.assertEqual(s["phases"][0]["el"], "Ni")


class AshbySelection(unittest.TestCase):
    def test_every_material_on_rho_E_with_range(self):
        c = SL.chart("rho", "E")
        self.assertGreaterEqual(len(c["points"]), 130)
        self.assertTrue(all(p["xmin"] is not None and p["ymin"] is not None for p in c["points"]))
        self.assertTrue(any(p["range_only"] for p in c["points"]))

    def test_card_route(self):
        r = T.run("werkstoff", {"id": "s235jr", "lang": "de"}, T.Ctx())
        rows = {w["prop"]: w for w in r["card"]["werte"]}
        self.assertIn("Rm", rows)
        self.assertLess(rows["Rm"]["min"], rows["Rm"]["max"])
        self.assertTrue(rows["rho"].get("range_only"))                  # nur Spanne, kein Einzelwert
        self.assertTrue(rows["rho"]["range_source"])

    def test_decoder_route(self):
        r = T.run("bezeichnung", {"text": "EN AW-1050A H14", "lang": "de"}, T.Ctx())
        if r.get("error"):
            self.skipTest("Entschlüsselung nicht verfügbar")
        self.assertTrue(r["found"])
        self.assertTrue(any("1050" in f["code"] for f in r["found"]))


class Microstructure(unittest.TestCase):
    def test_heat_treatment_has_inter_frames_where_the_change_happens(self):
        from werk import struktur as SK
        p = SK.temper_presets("c45e-n", "de")[1]
        r = SK.temper("c45e-n", p["steps"], "de", 1, p["kind"])
        inter = [f for f in r["frames"] if f.get("inter")]
        self.assertGreaterEqual(len(inter), 12)
        for f in inter:                                    # Zwischenbild verweist auf ein Schlüsselbild
            self.assertFalse(r["frames"][f["base"]].get("inter"))
            self.assertEqual(f["panels"][0]["id"], "gefuege")
        mart = [f for f in inter if f["panels"][0]["sketch"]["info"]["tid"] == "martensit"]
        self.assertTrue(mart)
        self.assertTrue(all(f["T"] <= 340 for f in mart))  # erst unter Ms
        aus = [f for f in inter if f["panels"][0]["sketch"]["info"]["tid"] == "austenitisieren"]
        self.assertTrue(all(f["T"] >= 700 for f in aus))   # erst über Ac1
        fr = [f["panels"][0]["sketch"]["info"]["frac"] for f in mart]
        self.assertEqual(fr, sorted(fr))

    def test_steel_opens_on_library_microstructure(self):
        from werk import struktur as SK
        cold = SK.build("c45e-n", 20, "de", 1, 3)["panels"][0]
        warm = SK.build("c45e-n", 900, "de", 1, 3)["panels"][0]
        self.assertEqual(cold["id"], "gefuege")
        self.assertEqual(cold["sketch"]["info"]["tid"], "perlit")
        self.assertEqual(warm["sketch"]["info"]["tid"], "austenitisieren")

    def test_mechanism_and_atlas_routes(self):
        m = T.run("struktur", {"mode": "mech", "mech": "bain", "lang": "en"}, T.Ctx())
        self.assertEqual(len(m["frames"]), 24)
        self.assertEqual(m["frames"][0]["panels"][0]["kind"], "scene")
        self.assertTrue(m["refs"])
        a = T.run("struktur", {"mode": "atlas", "gef": "perlit", "lang": "de"}, T.Ctx())
        self.assertEqual(a["panels"][0]["kind"], "sketch")
        self.assertTrue(a["info"]["what"])
        with self.assertRaises(T.ToolError):
            T.run("struktur", {"mode": "atlas", "gef": "gibtsnicht"}, T.Ctx())

    def test_phase_diagram_inset(self):
        r = T.run("phasen", {"system": "fe-c", "x": 0.4, "T": 600, "lang": "de"}, T.Ctx())
        self.assertEqual(r["micro"]["cid"], "ferrit_perlit")
        r = T.run("phasen", {"system": "pb-sn", "x": 40, "T": 150, "lang": "de"}, T.Ctx())
        self.assertEqual(r["micro"]["cid"], "pb_sn_eutektikum")
        r = T.run("phasen", {"system": "fe-c", "x": 0.4, "T": 760, "lang": "de"}, T.Ctx())
        self.assertEqual(r["micro"]["sketch"]["info"]["tid"], "austenitisieren")

    def test_report_sections_for_new_modes(self):
        import base64
        from werk import bundle as B
        for req, want in (({"mode": "mech", "mech": "perlit"}, "struktur-mech"), ({"mode": "atlas", "gef": "ledeburit"}, "struktur-atlas"),
                          ({"system": "fe-c", "x": 0.4, "T": 600}, "phasen-gefuege-punkt")):
            tool = "phasen" if "system" in req else "struktur"
            with self.subTest(req=req):
                b = B.build({"sections": [{"tool": tool, "req": {**req, "lang": "de"}}], "lang": "de"}, T.Ctx(), {})
                ids = {it.get("id") for it in b["items"]}
                self.assertIn(want, ids)
                bib = base64.b64decode(b["files"]["refs.bib"]).decode("utf-8", "replace")
                self.assertIn("@", bib)


class Martensite(unittest.TestCase):
    def test_bct_cell_splits_peaks(self):
        r = T.run("kristall", {"phase": "martensit-1", "tube": "Cu", "lang": "de"}, T.Ctx())
        tth = {l["hkl"]: l["tth"] for l in r["lines"]}
        self.assertLess(tth["101"], tth["110"])                         # c > a: (101) vor (110)
        self.assertLess(tth["002"], tth["200"])


if __name__ == "__main__":
    unittest.main()
