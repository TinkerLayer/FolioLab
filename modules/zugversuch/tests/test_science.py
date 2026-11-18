"""Fachliche Prüfungen mit bekannten Antworten (Version 1.3.0).

Jede Prüfung nennt den erwarteten Wert und woher er kommt. Grundlage ist die synthetische Kurve aus test_dataset.py
(E = 70 GPa, linear bis 105 MPa, Verfestigung bis Rm ≈ 139,6 MPa, Einschnürung ab ε = 9 %, Bruch bei ε = 12 %),
A0 = 0,2 mm², L0 = 10 mm, v = 1 mm/min. Die Zeitachse eines Datensatzes ist t = Σ|ΔL| / v.
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT), str(ROOT.parents[1] / "sdk" / "python"), str(Path(__file__).resolve().parent)):
    if p not in sys.path:
        sys.path.insert(0, p)

import labdataset as DSET  # noqa: E402

from flps import alloys, analyse  # noqa: E402
from flps import dataset as ZD  # noqa: E402
from flps.parser import parse_bytes  # noqa: E402
from test_dataset import A0, E_MPA, L0, V, curve  # noqa: E402


def run_curve(eps, sig):
    ds = DSET.from_columns("Kurve", [{"key": "e", "name": "Dehnung", "unit": "%", "values": eps * 100},
                                     {"key": "s", "name": "Spannung", "unit": "MPa", "values": sig}])
    raw, name, c = ZD.make_raw(ds, {"load": "s", "ext": "e"}, {"a0_mm2": A0, "l0_mm": L0, "speed_mm_min": V},
                               {"share": "s-5e7a0002", "title": "Kurve", "version": 1, "created": "2026-11-18T10:00:00"})
    return analyse.run(parse_bytes(raw, name), analyse.Config.from_dict({**c, "displacement_source": "probe"}))


class HoldTime(unittest.TestCase):
    def test_dip_splits_the_run(self):
        # y über der Grenze 0,9 bei t = 1..3 und t = 5..8, Einbruch bei t = 4, Maximum bei t = 6.
        t = np.arange(10.0)
        y = np.array([0.0, 0.95, 0.97, 0.96, 0.5, 0.95, 1.0, 0.98, 0.92, 0.1])
        h = analyse.hold_run(t, y, imax=6, limit=0.9)
        self.assertEqual(h["dauer"], 3.0)          # erwartet: zusammenhängend t = 5..8 -> 3 s (von Hand)
        self.assertEqual((h["von"], h["bis"]), (5.0, 8.0))
        self.assertEqual(h["spanne"], 7.0)         # frühere Definition: erster bis letzter Punkt, t = 1..8 -> 7 s
        self.assertEqual(h["summe"], 5.0)          # 2 s + 3 s
        self.assertEqual(h["abschnitte"], 2)

    def test_no_dip_unchanged(self):
        t = np.arange(5.0)
        y = np.array([0.0, 0.95, 1.0, 0.95, 0.0])
        h = analyse.hold_run(t, y, imax=2, limit=0.9)
        self.assertEqual((h["dauer"], h["spanne"]), (2.0, 2.0))   # ohne Einbruch: alte = neue Definition


class Plateau(unittest.TestCase):
    def test_measured_from_force_rise(self):
        # Vorlauf ohne Kraft: 0,1 mm Weg bei 1 mm/min = 6 s (von Hand). Das Plateau (letzte 20 % der Zeit vom
        # Kraftanstieg bis Fmax) darf sich dadurch nicht verschieben; gezählt ab t = 0 würde es früher beginnen.
        eps, sig = curve()
        slack = np.linspace(0, 0.01, 41)[:-1]
        r0 = run_curve(eps, sig)
        r1 = run_curve(np.concatenate([slack, eps + 0.01]), np.concatenate([np.zeros_like(slack), sig]))
        p0, p1 = r0.kv["plateau"], r1.kv["plateau"]
        self.assertAlmostEqual(p1["t_ref"], 6.0, delta=0.2)                  # erwartet 6 s (0,1 mm / 1 mm/min)
        tm = r1.kv["max"]["t"]
        self.assertAlmostEqual(p1["t_von"], p1["t_ref"] + 0.8 * (tm - p1["t_ref"]), places=9)
        self.assertAlmostEqual(p1["t_von"] - p1["t_ref"], p0["t_von"] - p0["t_ref"], delta=0.2)
        self.assertAlmostEqual(p1["mittel"], p0["mittel"], places=6)         # Vorlauf ändert den Mittelwert nicht


class StrainAtFracture(unittest.TestCase):
    """ISO 6892-1: At = Gesamtdehnung beim Bruch, A = At − σ_Bruch/E; Agt bei Fmax, Ag = Agt − Rm/E."""

    @classmethod
    def setUpClass(cls):
        cls.eps, cls.sig = curve()
        cls.r = run_curve(cls.eps, cls.sig)

    def test_at_and_a(self):
        kv = self.r.kv
        ib = int(np.searchsorted(self.eps, 0.12))            # letzter Punkt vor dem Lastabfall unter 1 % Fmax
        s_b = float(self.sig[ib])                            # = σ(9 %) − 20 MPa nach der Bauart von curve()
        self.assertAlmostEqual(kv["At_pct"], 12.0, places=6)                     # erwartet 12,0 % (Kurve)
        self.assertAlmostEqual(kv["A_pct"], 12.0 - 100 * s_b / E_MPA, places=3)  # 12,0 − 0,171 = 11,829 %
        self.assertAlmostEqual(kv["E_fit"], E_MPA, delta=E_MPA * 1e-6)           # Steigung = E der Kurve
        self.assertEqual(kv["strain_break_pct"], kv["At_pct"])                    # alter Schlüssel = At

    def test_agt_and_ag(self):
        kv = self.r.kv
        im = int(np.argmax(self.sig))
        self.assertAlmostEqual(kv["Agt_pct"], 100 * self.eps[im], places=6)
        self.assertAlmostEqual(kv["Ag_pct"], 100 * self.eps[im] - 100 * self.sig[im] / E_MPA, places=3)

    def test_variables(self):
        v = self.r.variables
        self.assertAlmostEqual(v["A"]["value"], self.r.kv["A_pct"])
        self.assertAlmostEqual(v["At"]["value"], self.r.kv["At_pct"])

    def test_work_from_measured_elongation(self):
        # W = A0·L0·∫σ dε bis zum Bruch, geschlossen integriert: elastisch 105²/(2E), Verfestigung
        # 105·Δε + 35·(Δε − 0,02·(1 − e^(−Δε/0,02))) mit Δε = 0,09 − 105/E, Einschnürung (σ(9 %) − 10 MPa)·0,03.
        ey = 105 / E_MPA
        de = 0.09 - ey
        s09 = float(self.sig[np.searchsorted(self.eps, 0.09)])
        w = 105 * ey / 2 + 105 * de + 35 * (de - 0.02 * (1 - math.exp(-de / 0.02))) + (s09 - 10) * 0.03
        expect_j = w * A0 * L0 / 1000                          # ≈ 0,03132 J
        v = self.r.variables["Wbreak"]
        self.assertIn("gemessenen Verlängerung", v["label"])
        self.assertAlmostEqual(v["value"], expect_j, delta=expect_j * 1e-3)   # Trapezregel: < 0,1 % daneben


class RambergOsgood(unittest.TestCase):
    """Idealisierte Kurve (Ramberg & Osgood 1943, NACA TN 902, Form mit 0,2 % Dehngrenze)."""

    def setUp(self):
        self.a = alloys.find(alloys.load_alloys(), "EN AW-5052-H38")   # Rp 220, Rm 285, A 7 %, E 70 GPa
        self.p = alloys.curve_model(self.a)

    def test_initial_slope_is_e(self):
        e = np.array([1e-5])
        s = alloys.ideal_curve(self.a, e)[0]
        self.assertAlmostEqual(s / 1e-5, self.a.e_gpa * 1000, delta=self.a.e_gpa * 1000 * 0.01)
        # früher Rp/ε_y = 220/(220/70000 + 0,002) ≈ 42,8 GPa; jetzt E = 70 GPa

    def test_passes_rp_and_rm(self):
        self.assertEqual(self.p["kind"], "ramberg-osgood")
        e_rp = self.a.rp / (self.a.e_gpa * 1000) + 0.002                  # Definition der 0,2-%-Dehngrenze
        s = alloys.ideal_curve(self.a, np.array([e_rp, self.p["ag"]]))
        self.assertAlmostEqual(s[0], self.a.rp, delta=0.5)                # σ = Rp bei σ/E + 0,2 %
        self.assertAlmostEqual(s[1], self.a.rm, delta=0.5)                # σ = Rm bei ε_u = 0,55·A
        self.assertAlmostEqual(self.p["ag"], 0.55 * self.a.a_pct / 100, places=12)
        n = math.log((self.p["ag"] - self.a.rm / 70000) / 0.002) / math.log(self.a.rm / self.a.rp)
        self.assertAlmostEqual(self.p["n"], n, places=9)                  # n aus der Bedingung σ(ε_u) = Rm

    def test_after_uniform_strain(self):
        A = self.a.a_pct / 100
        s = alloys.ideal_curve(self.a, np.array([A, A * 1.01]))
        self.assertAlmostEqual(s[0], 0.93 * self.a.rm, places=6)         # 7 % Abfall bis A
        self.assertTrue(math.isnan(s[1]))


class Ranking(unittest.TestCase):
    def mk(self, name, rm, rp):
        return alloys.Alloy(name=name, rp=rp, rm=rm, a_pct=10, e_gpa=70, rm_min=None, rm_max=None, source="Test")

    def test_relative_to_material_and_status_first(self):
        # Messung Rm = 100, Fliessbeginn 80 -> Verhältnis 1,25.
        al = [self.mk("nah, falsches Verhältnis", 102, 51),   # ΔRm −1,96 %, Verh. 2,0 -> zurückgestuft
              self.mk("weiter, passt", 110, 88),               # ΔRm −9,09 %, Verh. 1,25 -> Kandidat
              self.mk("weit", 200, 160)]                       # |ΔRm| 50 % -> ausgeschlossen
        c = alloys.compare(100.0, 80.0, None, al)
        rows = {r["name"]: r for r in c["rows"]}
        self.assertAlmostEqual(rows["weiter, passt"]["d_rm_pct"], 100 * (100 - 110) / 110, places=9)
        self.assertAlmostEqual(rows["nah, falsches Verhältnis"]["d_rm_pct"], 100 * (100 - 102) / 102, places=9)
        self.assertAlmostEqual(rows["weiter, passt"]["score"], 10 / 110, places=12)   # Abstand = |ΔRm|/Rm_W
        self.assertEqual([r["name"] for r in c["rows"]], ["weiter, passt", "nah, falsches Verhältnis", "weit"])
        self.assertEqual(rows["nah, falsches Verhältnis"]["status"], "zurückgestuft (Verfestigungsverhältnis)")
        self.assertEqual(rows["nah, falsches Verhältnis"]["rank_rm"], 1)   # nach Rm allein wäre es vorn
        self.assertIn("nach Status", c["criterion"])

    def test_reference_same_basis(self):
        a = self.mk("R", 200, 150)
        rc = alloys.reference_comparison(180.0, 120.0, None, a)
        self.assertAlmostEqual(rc["d_rm_pct"], -10.0, places=9)           # (180 − 200)/200
        self.assertAlmostEqual(rc["d_rp_pct"], -20.0, places=9)           # (120 − 150)/150
        self.assertIn("nicht gleichartig", rc["d_rp_basis"])


class MaterialData(unittest.TestCase):
    def setUp(self):
        self.al = {a.name: a for a in alloys.load_alloys()}

    def test_titan_grade1_minimum(self):
        self.assertEqual(self.al["Titan Grade 1"].rp, 138.0)   # ASTM B265 Grade 1: Rp0,2 min 138 MPa (20 ksi)
        self.assertEqual(self.al["Titan Grade 1"].rm, 240.0)   # Rm min 240 MPa (35 ksi)

    def test_every_row_has_value_type(self):
        for a in self.al.values():
            self.assertTrue(a.value_type.startswith("Rm "), a.name)

    def test_unverified_rows_marked(self):
        for n in ("PC", "PA6-GF30 trocken", "PA66-GF30 trocken", "PET-Folie (BOPET), längs",
                  "Buche, Zug parallel zur Faser", "Eiche, Zug parallel zur Faser"):
            self.assertTrue(self.al[n].check_note, n)

    def test_wood_modulus_is_bending(self):
        for a in self.al.values():
            if a.category == "Holz":
                self.assertIn("Biege", a.basis, a.name)

    def test_specimen_iso527_1a(self):
        self.assertEqual(analyse.SHAPES["ISO 527-2 Typ 1A"]["L0"], 75.0)   # ISO 527-2:2012, Typ 1A: L0 = 75 mm


class OwnImport(unittest.TestCase):
    def test_import_without_source_is_marked(self):
        from flps.ui import server
        x, flagged = server._import_source({"name": "ohne", "rm": 100, "a_pct": 5, "e_gpa": 70})
        self.assertTrue(flagged)
        self.assertEqual(x["source"], server.NO_SOURCE)
        self.assertIn("keine Quelle", alloys.own_from_dict(x).check_note)
        x, flagged = server._import_source({"name": "mit", "rm": 100, "a_pct": 5, "e_gpa": 70, "source": "Datenblatt X"})
        self.assertFalse(flagged)

    def test_import_rejects_bad_fields(self):
        from flps.ui import server
        with self.assertRaises(ValueError):
            server._import_source({"name": "x", "cite": "kein Objekt"})
        with self.assertRaises(ValueError):
            server._import_source({"name": "x", "source": 12})
        for bad in ({"rm": "abc"}, {"rm": -5}, {"rm": float("nan")}, {"e_gpa": 0}, {"curve": [[0, 0], ["a", 1], [2, 3]]},
                    {"curve": [[0, 0], [1], [2, 3]]}):
            with self.assertRaises(ValueError, msg=bad):
                alloys.own_from_dict({"name": "x", "rm": 100, "a_pct": 5, "e_gpa": 70, **bad})


if __name__ == "__main__":
    unittest.main()
