"""Lastspitzen (fortschreitendes Versagen) mit bekannten Antworten (Version 1.4.0).

Alle Kurven sind stückweise linear mit Stützstellen auf dem Abtastraster (dt = 0,1 s): Spitzen, Täler, Steigungen
und Flächen sind dann von Hand exakt bekannt (Trapezregel ist auf Geraden exakt). Jede Prüfung nennt den erwarteten
Wert und woher er kommt.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT), str(ROOT.parents[1] / "sdk" / "python"), str(Path(__file__).resolve().parent)):
    if p not in sys.path:
        sys.path.insert(0, p)

import labdataset as DSET  # noqa: E402

from flps import analyse  # noqa: E402
from flps import dataset as ZD  # noqa: E402
from flps import peaks  # noqa: E402
from flps.parser import parse_bytes  # noqa: E402

DT = 0.1
RES = 0.01   # Anzeigeauflösung in N; 3 × RES = 0,03 N liegt weit unter allen Schwellen dieser Tests


def polyline(knots):
    """Kurve durch Stützstellen (Index, Wert); Index ganzzahlig, t = Index · DT."""
    idx = np.array([k[0] for k in knots], dtype=float)
    val = np.array([k[1] for k in knots], dtype=float)
    i = np.arange(int(idx[-1]) + 1, dtype=float)
    return i * DT, np.interp(i, idx, val)


def sawtooth(t_peaks, y_peaks, valley_frac=0.4, drop_pts=10):
    """Anstieg von 0 zur ersten Spitze, nach jeder Spitze linearer Abfall auf valley_frac · Spitze in drop_pts Punkten,
    dann Anstieg zur nächsten Spitze; nach der letzten Spitze Abfall auf 0."""
    knots = [(0, 0.0)]
    for k, (tp, yp) in enumerate(zip(t_peaks, y_peaks)):
        ip = int(round(tp / DT))
        knots.append((ip, yp))
        last = k == len(t_peaks) - 1
        knots.append((ip + (2 * drop_pts if last else drop_pts), 0.0 if last else valley_frac * yp))
    return polyline(knots)


# Treppenkurve mit Abfällen von 3 %, 7,5 %, 12,6 % und 100 % (Stützstellen als Index, Wert in N):
STAIR = [(0, 0.0), (100, 100.0), (110, 97.0), (135, 99.5), (145, 92.0), (175, 95.0), (185, 83.0), (220, 90.0), (300, 0.0)]


def run(t, y, frac=0.05, **kw):
    return peaks.evaluate(t, y, y, ymax=float(np.max(y)), resolution=RES, frac=frac, dt=DT, **kw)


class Envelope(unittest.TestCase):
    T = [10.0, 30.0, 50.0, 70.0, 90.0]

    def test_exp_envelope_recovered(self):
        # Spitzen y = 100 · exp(−0,02 · t) bei t = 10..90 s (Bauart); die Exponentialfunktion trifft sie exakt
        a, b = 100.0, -0.02
        t, y = sawtooth(self.T, [a * np.exp(b * x) for x in self.T])
        pk = run(t, y)
        self.assertEqual(pk["n"], 5)                                   # erwartet 5 Spitzen (Bauart)
        self.assertEqual(pk["x_kind"], "time")                         # ohne v: x = Zeit
        self.assertEqual([e["t"] for e in pk["list"]], self.T)         # Spitzen genau an den Stützstellen
        fit = pk["fit"]
        self.assertEqual(fit["best"], "exp")
        self.assertAlmostEqual(fit["exp"]["a"], a, delta=a * 1e-6)    # erwartet a = 100 N
        self.assertAlmostEqual(fit["exp"]["b"], b, delta=1e-8)        # erwartet b = −0,02 1/s
        self.assertAlmostEqual(fit["exp"]["r2"], 1.0, places=9)
        self.assertLess(fit["line"]["r2"], fit["exp"]["r2"])          # Gerade passt schlechter (Krümmung)
        self.assertEqual((fit["n"], fit["exp"]["dof"]), (5, 3))        # n − 2 Freiheitsgrade

    def test_line_envelope_exact(self):
        # Spitzen y = 80 − 0,5 · t: 75, 65, 55, 45, 35 N (Bauart); die Gerade trifft sie exakt
        t, y = sawtooth(self.T, [80.0 - 0.5 * x for x in self.T])
        fit = run(t, y)["fit"]
        self.assertEqual(fit["best"], "line")
        self.assertAlmostEqual(fit["line"]["a"], 80.0, places=9)      # erwartet a = 80 N
        self.assertAlmostEqual(fit["line"]["b"], -0.5, places=9)      # erwartet b = −0,5 N/s
        self.assertAlmostEqual(fit["line"]["r2"], 1.0, places=12)
        self.assertAlmostEqual(fit["line"]["sse"], 0.0, places=18)
        self.assertLess(fit["exp"]["r2"], 1.0)

    def test_excluded_peaks_leave_the_fit(self):
        # Spitze 1 auf 40 N verfälscht (statt 75 N); ausgeschlossen ist die Gerade wieder exakt (Spitzen 2..5 wie oben)
        y_pk = [80.0 - 0.5 * x for x in self.T]
        y_pk[0] = 40.0
        t, y = sawtooth(self.T, y_pk)
        pk = run(t, y, exclude=[1])
        self.assertEqual(pk["fit"]["excluded"], [1])
        self.assertEqual(pk["fit"]["n"], 4)
        self.assertTrue(pk["list"][0]["excluded"])
        self.assertAlmostEqual(pk["fit"]["line"]["b"], -0.5, places=9)

    def test_strain_axis(self):
        # mit v = 0,5 mm/s und L0 = 50 mm: x = 100 · v · (t − t0) / L0 = t (in %), t0 = 0 (Bauart)
        t, y = sawtooth(self.T, [80.0 - 0.5 * x for x in self.T])
        pk = run(t, y, t0=0.0, v_mm_s=0.5, l0=50.0)
        self.assertEqual((pk["x_kind"], pk["x_unit"]), ("strain", "%"))
        for e in pk["list"]:
            self.assertAlmostEqual(e["x"], 100 * 0.5 * e["t"] / 50.0, places=12)
        self.assertAlmostEqual(pk["fit"]["line"]["b"], -0.5, places=9)   # x = t: gleiche Steigung je %


class Threshold(unittest.TestCase):
    def test_counts_at_2_5_10_percent(self):
        # Treppe STAIR, Fmax = 100 N. Von Hand nach der Regel „Abfall ≥ Δ, dann Wiederanstieg ≥ Δ“:
        # 2 % (Δ = 2 N): alle 4 Spitzen (Abfälle 3, 7,5, 12, 90 N; Anstiege 2,5, 3, 7 N)
        # 5 % (Δ = 5 N): 100 N (Abfall bis 83 N) und 90 N; 99,5 und 95 N steigen nicht um 5 N über ihr Tal
        # 10 % (Δ = 10 N): nur 100 N (83 → 90 N ist kein Wiederanstieg um 10 N)
        t, y = polyline(STAIR)
        self.assertEqual([e["y"] for e in run(t, y, 0.02)["list"]], [100.0, 99.5, 95.0, 90.0])
        pk5 = run(t, y, 0.05)
        self.assertEqual([e["y"] for e in pk5["list"]], [100.0, 90.0])
        self.assertEqual(pk5["list"][0]["valley_y"], 83.0)
        self.assertEqual(pk5["delta"], 5.0)
        self.assertEqual(pk5["delta_basis"], "anteil")
        pk10 = run(t, y, 0.10)
        self.assertEqual([e["y"] for e in pk10["list"]], [100.0])
        self.assertIsNone(pk10["fit"])                                 # 1 Spitze: kein Ausgleich
        self.assertFalse(pk10["progressive"])

    def test_resolution_floor(self):
        # Δ = max(frac · ymax, 3 · Auflösung): mit Auflösung 1 N und 2 % von 100 N gilt 3 N
        self.assertEqual(peaks.threshold(100.0, 1.0, 0.02), (3.0, "aufloesung"))
        self.assertEqual(peaks.threshold(100.0, 0.01, 0.05), (5.0, "anteil"))

    def test_at_least_rule_and_ties(self):
        # Abfall genau Δ zählt („mindestens“); gleiche Höchstwerte: die erste Stelle gilt
        y = np.array([0.0, 10.0, 10.0, 9.0, 8.0, 10.0, 0.0])
        self.assertEqual(peaks.detect(y, 2.0), [(1, 4), (5, 6)])       # 10 → 8 = Δ, 8 → 10 = Δ
        self.assertEqual(peaks.detect(y, 2.0 + 1e-9), [(1, 6)])        # knapp darüber: eine Spitze

    def test_noise_below_threshold(self):
        # eine Spitze 100 N, Abfall auf 50 N, dann Bruch; Rauschen ±0,5 N (Spitze-Spitze 1 N < Δ = 5 N)
        t, y = polyline([(0, 0.0), (100, 100.0), (400, 50.0), (420, 0.0)])
        rng = np.random.default_rng(7)
        y = y + rng.uniform(-0.5, 0.5, y.size)
        self.assertEqual(run(t, y, 0.05)["n"], 1)                      # erwartet 1 Spitze

    def test_single_maximum_gradual_decline(self):
        # ein Maximum, langsamer Abfall bis zum Ende: 1 Spitze, kein fortschreitendes Versagen, kein Ausgleich
        t, y = polyline([(0, 0.0), (100, 100.0), (600, 10.0)])
        pk = run(t, y)
        self.assertEqual(pk["n"], 1)
        self.assertEqual(pk["list"][0]["valley_idx"], 600)            # Tal = Minimum bis zum Ende
        self.assertIsNone(pk["fit"])

    def test_two_peaks_no_fit_with_reason(self):
        t, y = sawtooth([10.0, 30.0], [100.0, 80.0])
        pk = run(t, y)
        self.assertEqual(pk["n"], 2)
        self.assertTrue(pk["progressive"])
        self.assertIsNone(pk["fit"]["best"])
        self.assertIn("weniger als 3", pk["fit"]["reason"])           # mit 2 Parametern kein Freiheitsgrad


class PerPeak(unittest.TestCase):
    """Treppe STAIR bei 2 %: Spitzen 100 / 99,5 / 95 / 90 N an Index 100 / 135 / 175 / 220,
    Täler 97 / 92 / 83 / 0 N an Index 110 / 145 / 185 / 300."""

    @classmethod
    def setUpClass(cls):
        cls.t, cls.y = polyline(STAIR)
        cls.v = 0.5                                                  # mm/s, Weg = v · t (Traverse, t0 = 0)
        cls.pk = run(cls.t, cls.y, 0.02, t0=0.0, v_mm_s=cls.v, path_mm=cls.v * cls.t, work_basis="Traversenweg")
        cls.L = cls.pk["list"]

    def test_drop_duration_ratio(self):
        exp_drop = [3.0, (99.5 - 92) / 99.5 * 100, (95 - 83) / 95 * 100, 100.0]   # (Spitze − Tal) / Spitze
        for e, d in zip(self.L, exp_drop):
            self.assertAlmostEqual(e["drop_pct"], d, places=9)
        self.assertEqual([e["valley_idx"] for e in self.L], [110, 145, 185, 300])
        for e, d in zip(self.L, [1.0, 1.0, 1.0, 8.0]):                # (Index Tal − Index Spitze) · 0,1 s
            self.assertAlmostEqual(e["dauer"], d, places=9)
            self.assertEqual(e["dauer_u"], DT)                         # ± 1 Abtastintervall
        self.assertIsNone(self.L[0]["ratio"])
        for e, q in zip(self.L[1:], [99.5 / 100, 95 / 99.5, 90 / 95]):  # F / F der vorherigen Spitze
            self.assertAlmostEqual(e["ratio"], q, places=12)

    def test_stiffness_known_slopes(self):
        # Anstiege: 0 → 100 N in 10 s, 97 → 99,5 in 2,5 s, 92 → 95 in 3 s, 83 → 90 in 3,5 s (Stützstellen)
        for e, k in zip(self.L, [10.0, 1.0, 1.0, 2.0]):
            self.assertAlmostEqual(e["k_N_s"], k, places=9)              # N/s
            self.assertAlmostEqual(e["k_N_mm"], k / self.v, places=9)    # N/mm = (N/s) / v
        self.assertEqual(self.L[1]["rise_from_idx"], 110)                # Anstieg ab dem vorherigen Tal

    def test_segment_work_closed_form(self):
        # ∫F dx = v · ∫F dt, Flächen der Geradenstücke von Hand (N·s), · 0,5 mm/s, / 1000 → J
        seg_ns = [0.5 * 100 * 10 + (100 + 97) / 2 * 1,                 # 0..110:   500 + 98,5
                  (97 + 99.5) / 2 * 2.5 + (99.5 + 92) / 2 * 1,         # 110..145: 245,625 + 95,75
                  (92 + 95) / 2 * 3 + (95 + 83) / 2 * 1,               # 145..185: 280,5 + 89
                  (83 + 90) / 2 * 3.5 + 90 / 2 * 8]                    # 185..300: 302,75 + 360
        cum = 0.0
        for e, w in zip(self.L, seg_ns):
            cum += w * self.v / 1000
            self.assertAlmostEqual(e["W_J"], w * self.v / 1000, places=12)
            self.assertAlmostEqual(e["W_cum_J"], cum, places=12)
        self.assertAlmostEqual(cum, 0.9860625, places=12)              # Summe 1972,125 N·s · 0,5 mm/s / 1000
        self.assertAlmostEqual(cum, float(np.trapz(self.y, self.v * self.t)) / 1000 if not hasattr(np, "trapezoid")
                               else float(np.trapezoid(self.y, self.v * self.t)) / 1000, places=12)  # = ganze Kurve

    def test_travel_axis(self):
        self.assertEqual((self.pk["x_kind"], self.pk["x_unit"]), ("travel", "mm"))
        self.assertAlmostEqual(self.L[0]["x"], 5.0, places=12)          # v · t = 0,5 mm/s · 10 s


class _Stair:
    """Treppe STAIR als Kraft + Weg aus einem Datensatz (v = 6 mm/min = 0,1 mm/s, Weg 0,01 mm je Punkt → dt = 0,1 s)."""

    @classmethod
    def setUpClass(cls):
        _t, y = polyline(STAIR)
        dl = np.arange(y.size) * 0.01
        ds = DSET.from_columns("Treppe", [{"key": "dl", "name": "Verlängerung", "unit": "mm", "values": dl},
                                          {"key": "F", "name": "Kraft", "unit": "N", "values": y}])
        raw, name, c = ZD.make_raw(ds, {"load": "F", "ext": "dl"}, {"l0_mm": 10.0, "speed_mm_min": 6.0},
                                   {"share": "s-5e7a0003", "title": "Treppe", "version": 1, "created": "2026-11-18T10:00:00"})
        cls.f = parse_bytes(raw, name)
        cls.c = {**c, "displacement_source": "probe"}

    def result(self, **cfg):
        return analyse.run(self.f, analyse.Config.from_dict({**self.c, **cfg}))


class InAnalysis(_Stair, unittest.TestCase):
    """Ganzer Ablauf über analyse.run: Kennwerte, Hinweis 4.9, Variablen."""

    def test_default_threshold(self):
        r = self.result()
        pk = r.kv["peaks"]
        self.assertEqual([round(e["F"], 6) for e in pk["list"]], [100.0, 90.0])   # wie Threshold bei 5 %
        self.assertEqual(pk["x_kind"], "strain")
        self.assertTrue(any(w["code"] == "4.9" for w in r.warnings))             # Hinweis bei ≥ 2 Spitzen
        v = analyse.equation_variables(r)
        self.assertEqual(v["npk"]["value"], 2)
        self.assertAlmostEqual(v["Fpk2"]["value"], 90.0, places=6)
        self.assertAlmostEqual(r.kv["max"]["F"], 100.0, places=6)                # Fmax bleibt das globale Maximum

    def test_config_threshold_and_exclusion(self):
        r = self.result(peak_drop_frac=0.02, peak_fit_exclude="2, 9")
        pk = r.kv["peaks"]
        self.assertEqual(pk["n"], 4)
        self.assertEqual(pk["fit"]["excluded"], [2])                 # Nr. 9 gibt es nicht
        self.assertEqual(r.config.peak_fit_exclude, [2, 9])
        r10 = self.result(peak_drop_frac=0.10)
        self.assertEqual(r10.kv["peaks"]["n"], 1)
        self.assertFalse(any(w["code"] == "4.9" for w in r10.warnings))
        self.assertNotIn("Fpk1", analyse.equation_variables(r10))       # Spitzenvariablen erst ab 2 Spitzen


class FirstLoading(_Stair, unittest.TestCase):
    """Fitgerade aus der Erstbelastung (Methoden 3.2, Schritt 3): Anstieg 0 → 100 N in 100 Punkten (1 N je Punkt,
    dt = 0,1 s → 10 N/s), Abfall auf 40 N, Wiederanstieg auf 90 N mit 5 N je Punkt (50 N/s, steiler), Abfall auf 0."""
    KNOTS = [(0, 0.0), (100, 100.0), (110, 40.0), (120, 90.0), (130, 10.0), (200, 0.0)]

    @classmethod
    def setUpClass(cls):
        global STAIR
        keep, STAIR = STAIR, cls.KNOTS
        try:
            super().setUpClass()
        finally:
            STAIR = keep

    def test_fit_before_first_peak(self):
        r = self.result()
        first = r.kv["peaks"]["list"][0]
        self.assertEqual(r.kv["peaks"]["n"], 2)
        self.assertLessEqual(r.t[r.fit.hi], first["t"] + 1e-9)    # Fenster endet spätestens bei der ersten Spitze
        self.assertAlmostEqual(r.fit.k, 10.0, places=6)              # Steigung der Erstbelastung, nicht 50 N/s
        self.assertGreater(first["x"], 0.0)                          # erste Spitze mit positiver Dehnung


class ElasticPlastic(_Stair, unittest.TestCase):
    """Einteilung elastisch/plastisch (Methoden 3.2, Schritt 4): Treppe STAIR bei 5 % hat 2 Spitzen (Index 100 und 220).
    Bis zur ersten Spitze ist die Kurve eine Gerade, danach fällt sie: ein Fliessbeginn läge nur nach der Spitze."""

    def names(self, r):
        return [b["phase"] for b in r.kv["phases"] if b["phase"] not in ("Bruch", "nach Bruch")]

    def test_auto_progressive_not_divided(self):
        r = self.result()
        self.assertEqual(r.kv["ep"], {"setting": "auto", "on": False, "progressive": True, "rise_end": 100,
                                      "last_peak": 220})
        self.assertIsNone(r.kv["yield"])
        self.assertTrue(all(row["idx"] is None for row in r.yield_table))
        self.assertEqual(self.names(r), ["Setzen", "Anstieg", "Lastspitzen", "Abfall"][-len(self.names(r)):])
        lsp = next(b for b in r.kv["phases"] if b["phase"] == "Lastspitzen")
        self.assertEqual((lsp["von"], lsp["bis"]), (100, 219))                # erste bis vor die letzte Spitze
        self.assertIsNone(r.kv["Ag_pct"])
        self.assertIsNone(r.kv["A_pct"] if "A_pct" in r.kv else None)
        self.assertIsNotNone(r.kv["Agt_pct"])                                 # Gesamtdehnung bleibt
        self.assertIsNotNone(r.kv["E_fit"])                                   # Steigung bleibt
        w = [x["text"] for x in r.warnings if x["code"] == "7.4"]
        self.assertEqual(len(w), 1)
        self.assertIn("2 Lastspitzen", w[0])
        self.assertFalse(any(x["code"] == "4.4" for x in r.warnings))         # kein "kein Fliessbeginn"

    def test_forced_on_yield_never_after_first_peak(self):
        r = self.result(elastic_plastic="ein")
        self.assertTrue(r.kv["ep"]["on"])
        # die Gerade läuft bis zur Spitze exakt mit; ohne Grenze läge der Fliessbeginn auf der fallenden Flanke
        self.assertIsNone(r.kv["yield"])
        self.assertIsNotNone(analyse.find_yield(r.t, r.y, r.fit, 0.02 * 100.0))      # ungebremst: nach der Spitze
        self.assertGreater(analyse.find_yield(r.t, r.y, r.fit, 0.02 * 100.0), 100)
        self.assertIn("elastisch", self.names(r))
        self.assertIn("Lastspitzen", self.names(r))
        self.assertTrue(any(x["code"] == "4.4" and "vor der ersten Lastspitze" in x["text"] for x in r.warnings))

    def test_off_and_single_peak(self):
        r = self.result(peak_drop_frac=0.10)                                   # 1 Spitze: auto teilt ein
        self.assertTrue(r.kv["ep"]["on"])
        self.assertFalse(r.kv["ep"]["progressive"])
        self.assertIn("elastisch", self.names(r))
        r = self.result(peak_drop_frac=0.10, elastic_plastic="aus")
        self.assertFalse(r.kv["ep"]["on"])
        self.assertEqual(self.names(r)[-2:], ["Anstieg", "Abfall"])
        self.assertTrue(any(x["code"] == "7.4" and "ausgeschaltet" in x["text"] for x in r.warnings))

    def test_config_values(self):
        self.assertEqual(analyse.Config.from_dict({"elastic_plastic": "AUS "}).elastic_plastic, "aus")
        self.assertEqual(analyse.Config.from_dict({"elastic_plastic": "vielleicht"}).elastic_plastic, "auto")
        self.assertEqual(analyse.Config.from_dict({"elastic_plastic": None}).elastic_plastic, "auto")
        self.assertEqual(analyse.Config().elastic_plastic, "auto")

    def test_outputs_without_division(self):
        import base64
        import tempfile

        from flps import bundle
        from flps.export import write_all
        r = self.result()
        with tempfile.TemporaryDirectory() as d:                               # Mappe mit Selbstprüfung
            names = {p.name for p in write_all(r, Path(d), overwrite=False)}
            self.assertTrue(any(n.endswith("_Bericht.pdf") for n in names))
        for lang, text in (("de", "nicht in elastisch und plastisch eingeteilt"), ("en", "not divided into elastic")):
            b = bundle.build([r], {}, {"items": []}, lang=lang)
            meth = base64.b64decode(b["files"]["text-methodik.tex"]).decode("utf-8")
            self.assertIn(text, meth)
            self.assertTrue(all(ord(ch) < 256 for ch in meth), lang)


class YieldBeforeMaximum(_Stair, unittest.TestCase):
    """Eine Spitze: Gerade bis zum Maximum (Index 100), danach Abfall. Der Fliessbeginn wird nur vor dem Maximum
    gesucht; früher lag er auf der fallenden Flanke (Index > 100)."""
    KNOTS = [(0, 0.0), (100, 100.0), (200, 0.0)]

    @classmethod
    def setUpClass(cls):
        global STAIR
        keep, STAIR = STAIR, cls.KNOTS
        try:
            super().setUpClass()
        finally:
            STAIR = keep

    def test_no_yield_on_falling_flank(self):
        r = self.result()
        self.assertTrue(r.kv["ep"]["on"])
        self.assertIsNone(r.kv["yield"])
        self.assertNotIn("plastisch", [b["phase"] for b in r.kv["phases"]])
        self.assertTrue(any(x["code"] == "4.4" and "vor dem Maximum" in x["text"] for x in r.warnings))


class Outputs(_Stair, unittest.TestCase):
    """Ausgaben mit 4 Spitzen (Treppe bei 2 %): Mappe mit Selbstprüfung, Bilder, Bericht, Bündel DE/EN."""

    def test_workbook_report_pngs(self):
        import tempfile

        from flps.export import write_all
        r = self.result(peak_drop_frac=0.02)
        with tempfile.TemporaryDirectory() as d:
            names = {p.name for p in write_all(r, Path(d), overwrite=False)}   # Mappe: Selbstprüfung würde abbrechen
            self.assertTrue(any(n.endswith("_Diagramm_5.png") for n in names))  # Lastspitzen-Bild
            self.assertTrue(any(n.endswith("_Bericht.pdf") for n in names))
            import openpyxl
            wb = openpyxl.load_workbook(next(Path(d).rglob("*.xlsx")))
            self.assertIn("Lastspitzen", wb.sheetnames)

    def test_bundle_latin1_and_items(self):
        import base64

        from flps import bundle
        r = self.result(peak_drop_frac=0.02)
        for lang in ("de", "en"):
            b = bundle.build([r], {}, {"items": []}, lang=lang)
            ids = {(i["kind"], i.get("id")) for i in b["items"]}
            for need in (("figure", "lastspitzen"), ("figure", "lastspitzen-ausgleich"), ("table", "lastspitzen"),
                         ("table", "lastspitzen-ausgleich")):
                self.assertIn(need, ids, lang)
            vals = base64.b64decode(b["files"]["values.tex"]).decode("utf-8")
            self.assertRegex(vals, r"\{npk\}\{4\}")
            for fn, data in b["files"].items():
                if fn.endswith(".tex"):
                    txt = base64.b64decode(data).decode("utf-8")
                    self.assertTrue(all(ord(ch) < 256 for ch in txt), (lang, fn))   # nur Latin-1
                    for bad in ("\\text{", "\\ce{", "\\tfrac", "\\boldsymbol"):
                        self.assertNotIn(bad, txt, (lang, fn))
        # ohne Spitzen (10 %): keine Lastspitzen-Teile im Bündel
        b = bundle.build([self.result(peak_drop_frac=0.10)], {}, {"items": []}, lang="de")
        self.assertFalse(any("lastspitzen" in (i.get("id") or "") for i in b["items"]))


if __name__ == "__main__":
    unittest.main()
