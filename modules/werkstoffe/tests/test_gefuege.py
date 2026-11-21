"""Gefügeskizzen (werk/gefuege.py): Bestandteile, stetige Umwandlungen, Mechanismus-Bildfolgen, Zustände, Quellen.

Start:  python -m unittest discover -s tests   (im Ordner modules/werkstoffe)
"""
import json
import math
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT.parents[1] / "sdk" / "python"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from werk import gefuege as GF  # noqa: E402
from werk import refs as RF  # noqa: E402

ALLOWED = set(GF.ITEM_TYPES)
LO, HI = -0.3, 1.3
MAX_PRIMS = 2500
MAX_KB = 150
MAX_MS = 600          # großzügig (langsame Testrechner); Zielwert 150 ms, gemessen < 70 ms
SEEDS = (1, 4)


def _walk(items):
    for it in items:
        yield it
        if it.get("t") == "clip":
            yield from _walk(it.get("items") or [])


def _points(it):
    t = it["t"]
    if t in ("poly", "line", "pline", "dots", "clip"):
        for q in it.get("p", it.get("poly", [])):
            yield q[0], q[1]
    elif t == "dashes":
        for q in it["p"]:
            yield q[0], q[1]
    elif t == "hatch":
        for q in it["poly"]:
            yield q[0], q[1]
    elif t == "circle":
        yield it["c"][0], it["c"][1]
    elif t == "text":
        yield it["p"][0], it["p"][1]


def _decimals_ok(v):
    return abs(v * 1e4 - round(v * 1e4)) < 1e-6


class Pruefer:
    def check_sketch(self, sk, ctx):
        self.assertIsInstance(sk, dict, ctx)
        self.assertTrue(sk.get("items"), ctx)
        for it in _walk(sk["items"]):
            self.assertIn(it["t"], ALLOWED, ctx)
            for x, y in _points(it):
                self.assertTrue(LO <= x <= HI and LO <= y <= HI, f"{ctx}: Punkt ({x}, {y}) außerhalb")
                self.assertTrue(_decimals_ok(x) and _decimals_ok(y), f"{ctx}: mehr als 4 Nachkommastellen ({x}, {y})")
        self.assertLessEqual(GF.count_primitives(sk), MAX_PRIMS, ctx)
        kb = len(json.dumps(sk, ensure_ascii=False)) / 1024
        self.assertLessEqual(kb, MAX_KB, f"{ctx}: {kb:.1f} KB")
        for e in sk.get("legend", []):
            self.assertTrue(str(e.get("label", "")).strip(), f"{ctx}: leere Legende")
            self.assertTrue(e.get("color"), ctx)


class TestBestandteile(unittest.TestCase, Pruefer):
    def test_anzahl_und_felder(self):
        self.assertGreaterEqual(len(GF.CONSTITUENTS), 29)
        for cid, c in GF.CONSTITUENTS.items():
            for k in ("name", "what", "conditions", "etch"):
                self.assertEqual(len(c[k]), 2, f"{cid}.{k}")
                self.assertTrue(all(str(s).strip() for s in c[k]), f"{cid}.{k}")
            self.assertTrue(c["family"], cid)
            self.assertTrue(c["refs"], cid)

    def test_alle_skizzen_de_en(self):
        for cid in GF.CONSTITUENTS:
            for de in (True, False):
                for s in SEEDS:
                    t0 = time.perf_counter()
                    sk = GF.sketch(cid, s, de)
                    ms = (time.perf_counter() - t0) * 1000
                    ctx = f"{cid} de={de} seed={s}"
                    self.check_sketch(sk, ctx)
                    self.assertLess(ms, MAX_MS, f"{ctx}: {ms:.0f} ms")

    def test_generator_als_rng(self):
        import numpy as np
        a = GF.sketch("perlit", np.random.default_rng(7))
        self.check_sketch(a, "perlit/Generator")

    def test_sprache_unterscheidet_legende(self):
        de = GF.sketch("martensit_platte", 2, True)["legend"]
        en = GF.sketch("martensit_platte", 2, False)["legend"]
        self.assertNotEqual([e["label"] for e in de], [e["label"] for e in en])

    def test_unbekannt(self):
        with self.assertRaises(Exception):
            GF.sketch("gibtsnicht", 1)


class TestUmwandlungen(unittest.TestCase, Pruefer):
    PFLICHT = ("austenitisieren", "perlit", "martensit", "anlassen", "bainit_oben", "bainit_unten", "ausscheidung",
               "rekristallisation", "erstarrung", "sphaeroidisieren")
    FS = [k / 10 for k in range(11)]

    def test_pflicht_vorhanden(self):
        for tid in self.PFLICHT:
            self.assertIn(tid, GF.TRANSITIONS)
            tr = GF.TRANSITIONS[tid]
            self.assertTrue(tr["name"] and tr["refs"] and tr["steps"], tid)
            for lo, hi, cde, cen in tr["steps"]:
                self.assertTrue(0 <= lo <= hi <= 1 and cde.strip() and cen.strip(), tid)

    def test_deterministisch(self):
        for tid in GF.TRANSITIONS:
            for f in (0.0, 0.35, 0.8):
                a = json.dumps(GF.transition(tid, f, 3, True), sort_keys=True)
                GF._fp_geom.cache_clear()
                GF._mart_geom.cache_clear()
                b = json.dumps(GF.transition(tid, f, 3, True), sort_keys=True)
                self.assertEqual(a, b, f"{tid} f={f}")

    def test_anteil_monoton(self):
        for tid in GF.TRANSITIONS:
            for s in SEEDS:
                fr = [GF.transition(tid, f, s, True)["info"]["frac"] for f in self.FS]
                for a, b in zip(fr, fr[1:]):
                    self.assertGreaterEqual(b + 1e-9, a, f"{tid} seed={s}: {fr}")
                self.assertLessEqual(fr[0], 0.05, f"{tid}: Start {fr[0]}")
                self.assertGreater(fr[-1], fr[0], tid)

    def test_skizzen_gueltig(self):
        for tid in GF.TRANSITIONS:
            for f in (0.0, 0.5, 1.0):
                for de in (True, False):
                    sk = GF.transition(tid, f, 2, de)
                    self.check_sketch(sk, f"{tid} f={f} de={de}")
                    self.assertTrue(sk["info"]["caption"].strip(), tid)

    def test_stahl_parameter(self):
        for C in (0.2, 0.45, 0.77, 1.2):
            fr = [GF.transition("perlit", f, 1, True, C=C)["info"]["frac"] for f in self.FS]
            self.assertTrue(all(b + 1e-9 >= a for a, b in zip(fr, fr[1:])), f"C={C}: {fr}")
        for C in (0.2, 1.4):
            self.check_sketch(GF.transition("martensit", 1.0, 1, True, C=C), f"martensit C={C}")

    def test_unbekannt(self):
        with self.assertRaises(Exception):
            GF.transition("gibtsnicht", 0.5)


class TestMechanismen(unittest.TestCase):
    def test_bildfolgen(self):
        for mid in GF.MECHANISMS:
            for n in (12, 24):
                m = GF.mechanism(mid, "de", 1, n)
                self.assertEqual(m["id"], mid)
                self.assertTrue(m["name"].strip())
                self.assertEqual(len(m["frames"]), n, mid)
                fs = [fr["f"] for fr in m["frames"]]
                self.assertAlmostEqual(fs[0], 0.0)
                self.assertAlmostEqual(fs[-1], 1.0)
                self.assertTrue(all(b > a for a, b in zip(fs, fs[1:])), mid)
                for fr in m["frames"]:
                    self.assertTrue(fr["caption"].strip(), mid)
                    self.assertTrue(fr["label"].strip(), mid)
                    self.assertIn(fr["panel"]["kind"], ("sketch", "scene"))
                for k in m["refs_keys"]:
                    self.assertTrue(RF.known(k), f"{mid}: {k}")

    def test_englisch(self):
        de = GF.mechanism("perlit", "de", 1, 12)
        en = GF.mechanism("perlit", "en", 1, 12)
        self.assertNotEqual(de["frames"][5]["caption"], en["frames"][5]["caption"])

    def test_n_begrenzt(self):
        self.assertEqual(len(GF.mechanism("ausscheidung", n=3)["frames"]), 12)
        self.assertEqual(len(GF.mechanism("ausscheidung", n=500)["frames"]), 60)

    def test_ease_in_out(self):
        fs = GF.frame_positions(24)
        d = [b - a for a, b in zip(fs, fs[1:])]
        self.assertLess(d[0], d[len(d) // 2])
        self.assertLess(d[-1], d[len(d) // 2])

    def test_bain(self):
        m = GF.mechanism("bain", "de", n=24)
        ca = [fr["panel"]["scene"]["c_a"] for fr in m["frames"]]
        self.assertAlmostEqual(ca[0], math.sqrt(2), places=3)
        self.assertTrue(1.0 < ca[-1] < 1.06, ca[-1])
        self.assertTrue(all(b <= a + 1e-12 for a, b in zip(ca, ca[1:])), ca)
        self.assertIn("c/a", m["frames"][0]["label"])


class TestZustaende(unittest.TestCase, Pruefer):
    def test_stahl(self):
        for st in ("normal", "austenit", "ab", "gehaertet", "angelassen", "bainit_oben", "bainit_unten",
                   "sphaeroidit"):
            for C in (0.35, 0.77, 1.1):
                self.check_sketch(GF.steel_state(C, st, 0.6, 1, True), f"{st} C={C}")

    def test_ab_trifft_gamma_anteil(self):
        for target in (0.25, 0.6):
            sk = GF.steel_state(0.45, "ab", target, 1, True)
            self.assertAlmostEqual(sk["info"]["frac"], target, delta=0.03)

    def test_aluminium(self):
        fr = []
        for key in ("ss", "gp", "peak", "over", "eq"):
            sk = GF.al_state(key, 1, False)
            self.check_sketch(sk, key)
            fr.append(sk["info"]["frac"])
        self.assertEqual(fr, sorted(fr))

    def test_unbekannt(self):
        with self.assertRaises(Exception):
            GF.steel_state(0.4, "gibtsnicht")
        with self.assertRaises(Exception):
            GF.al_state("gibtsnicht")


class TestQuellen(unittest.TestCase):
    def test_eigene_quellen(self):
        q = GF.sources()
        self.assertGreaterEqual(len(q), 10)
        for k, r in q.items():
            for f in ("type", "authors", "title", "year"):
                self.assertTrue(str(r.get(f, "")).strip(), f"{k}.{f}")
            if "doi" in r:
                self.assertTrue(r["doi"].startswith("10."), k)

    def test_alle_aufloesbar(self):
        for k in GF.all_refs():
            self.assertTrue(k in GF.sources() or RF.known(k), f"Quelle {k} unbekannt")


if __name__ == "__main__":
    unittest.main()
