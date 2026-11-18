"""I-04: Vergleichsverteilung aus einem Datensatz (`data.table`) über der Partikelgrössenverteilung.

Längenspalten werden erkannt und in Meter umgerechnet (µm und mm ergeben dieselben Werte), D10/D50/D90 entsprechen
numpy.percentile, ausgeschlossene Zeilen fehlen. Der Bericht bekommt Abbildung, Tabelle, Kennwerte, Daten, Quelle und Satz;
die Herkunftskette hält die Version fest; ohne Massstab entfällt der Vergleich. Alles in einem temporären Suite-Ordner.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "sdk" / "python"))

import labdataset as DSET  # noqa: E402
import labprov  # noqa: E402
from labshare import Sharebox  # noqa: E402

from mikro import bundle  # noqa: E402
from mikro import compare as CMP  # noqa: E402
from mikro.imageio import load_bytes, sample_image  # noqa: E402

PIPE = [{"op": "background", "radius": 30}, {"op": "gauss", "sigma": 1.5},
        {"op": "threshold", "method": "otsu", "dark": True}, {"op": "fill"}]
STATE = {"pipeline": PIPE, "particles": {"size_min": 2}}
SIZES_UM = np.random.default_rng(7).lognormal(np.log(3.0), 0.4, 300)
PRODUCER = {"module": "datenaufbereitung", "env": "e1", "env_name": "Prüfung", "item_name": "LD-1"}


def dataset(title="Laserbeugung"):
    return DSET.from_columns(title, [
        {"key": "d", "name": "Durchmesser", "unit": "µm", "values": SIZES_UM},
        {"key": "dmm", "name": "Durchmesser mm", "unit": "mm", "values": SIZES_UM / 1000},
        {"key": "t", "name": "Zeit", "unit": "s", "values": np.arange(300.0)},
        {"key": "q", "name": "Anteil", "unit": "", "values": np.ones(300)}],
        flags=[{"row": 0, "code": "outlier", "excluded": True}])


class Unit(unittest.TestCase):
    def test_columns_values_stats(self):
        ds = dataset()
        cols = CMP.length_columns(ds)
        self.assertEqual([c["key"] for c in cols], ["d", "dmm"])
        self.assertEqual(cols[0]["n"], 299)                           # ausgeschlossene Zeile zählt nicht
        v, w = CMP.values_m(ds, "d"), CMP.values_m(ds, "dmm")
        np.testing.assert_allclose(v, w, rtol=1e-12)
        self.assertAlmostEqual(v[0], SIZES_UM[1] * 1e-6)
        with self.assertRaisesRegex(CMP.CompareError, "keine Länge"):
            CMP.values_m(ds, "t")
        with self.assertRaisesRegex(CMP.CompareError, "keine Länge"):
            CMP.values_m(ds, "q")
        s = CMP.stats(v / CMP.metres_per("µm"))
        for k, q in (("D10", 10), ("D50", 50), ("D90", 90)):
            self.assertAlmostEqual(s[k], float(np.percentile(SIZES_UM[1:], q)), places=9)
        self.assertEqual(s["n"], 299)
        self.assertAlmostEqual(CMP.metres_per("nm"), 1e-9)
        self.assertAlmostEqual(CMP.metres_per("um"), 1e-6)
        with self.assertRaisesRegex(CMP.CompareError, "Massstab"):
            CMP.metres_per("px")
        rec = CMP.record(ds, {"version": 2, "title": "Laserbeugung", "producer": PRODUCER}, "s-0000abcd", "pin", "dmm")
        self.assertEqual((rec["name"], rec["unit"], rec["version"], len(rec["values_m"])), ("Durchmesser mm", "mm", 2, 299))
        np.testing.assert_allclose(CMP.in_unit(rec, "nm"), SIZES_UM[1:] * 1000, rtol=1e-5)
        self.assertNotIn("env", rec["producer"])
        short = DSET.from_columns("kurz", [{"key": "d", "name": "d", "unit": "µm", "values": [1.0, -2.0, 3.0]}])
        with self.assertRaisesRegex(CMP.CompareError, "mindestens 3"):
            CMP.values_m(short, "d")


class Report(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw, cls.name = sample_image()                           # kalibriert: 0,25 µm/px
        cls.st = load_bytes(cls.raw, cls.name)
        env = {"version": 3, "title": "Laserbeugung", "created": "2026-11-18T09:00:00", "producer": PRODUCER}
        cls.rec = CMP.record(dataset(), env, "s-0000abcd", "pin", "d")
        cls.state = {**STATE, "compare": cls.rec}
        cls.b = bundle.build([(cls.st, cls.raw, cls.state)], {"items": [{"name": cls.name, "state": cls.state}]}, "de")

    def test_items_and_citation(self):
        b = self.b
        items = {(i["kind"], i.get("id")) for i in b["items"]}
        for k in (("figure", "vergleichsverteilung"), ("table", "vergleichsverteilung"), ("data", "vergleichsverteilung")):
            self.assertIn(k, items)
        fig = next(i for i in b["items"] if i["kind"] == "figure" and i["id"] == "vergleichsverteilung")
        self.assertIn("ds-s-0000abcd", fig["caption"])
        bib = base64.b64decode(b["files"]["refs.bib"]).decode("utf-8")
        self.assertIn("Datensatz Laserbeugung", bib)
        self.assertIn("s-0000abcd, Version 3", bib)
        self.assertIn("Folio Lab, Prüfung, LD-1", bib)
        vals = base64.b64decode(b["files"]["values.tex"]).decode("utf-8")
        for k in ("cmpN", "cmpD10", "cmpD50", "cmpD90", "cmpRatio"):
            self.assertIn(k, vals)
        txt = base64.b64decode(b["files"]["text-ergebnisse.tex"]).decode("utf-8")
        self.assertIn("Zum Vergleich wurde die Spalte", txt)
        self.assertIn(r"\cite{ds-s-0000abcd}", txt)
        self.assertNotIn("„", txt)
        txt.encode("latin-1")
        self.assertIn(("s-0000abcd", 3), labprov.refs_in_request(b["source"]["request"])["shares"])

    def test_rebuild_english_and_without_scale(self):
        src = self.b["source"]
        files = {k: base64.b64decode(v) for k, v in src["files"].items()}
        items = [(load_bytes(files[i["name"]], i["name"]), files[i["name"]], i["state"]) for i in src["request"]["items"]]
        en = bundle.build(items, {**src["request"]}, "en")
        txt = base64.b64decode(en["files"]["text-ergebnisse.tex"]).decode("utf-8")
        self.assertIn("For comparison, the column", txt)
        # gleiche Kennwerte wie direkt gerechnet (µm, wie die Kalibrierung)
        s = CMP.stats(SIZES_UM[1:])
        vals = base64.b64decode(en["files"]["values.tex"]).decode("utf-8")
        self.assertIn(f"{s['D50']:.{bundle._nd(s['D50'])}f}", vals)
        # ohne Massstab kein Vergleich
        b = bundle.build([(self.st, self.raw, {**self.state, "calib": {"pw": 1, "ph": 1, "unit": "px"}})], {"items": []}, "de")
        self.assertFalse(any(i.get("id") == "vergleichsverteilung" for i in b["items"]))

    def test_chart(self):
        from mikro import charts as C
        e = C.overlay_bins(np.array([1.0, 2.0, 3.0]), np.array([2.0, 5.0]))
        self.assertEqual((e[0], e[-1], len(e)), (1.0, 5.0, 7))
        f = C.fig_sizes_overlay([1, 2, 3, 4], [2, 3, 5], "µm", "de", ("Partikel", "LD"))
        labels = [t.get_text() for t in f.axes[0].get_legend().get_texts()]
        self.assertEqual(len(labels), 4)                              # zwei Verteilungen, zwei D50
        self.assertTrue(any(lb.startswith("LD (n = 3)") for lb in labels))
        C.plt.close(f)


class Server(unittest.TestCase):
    def setUp(self):
        from mikro import server as S
        self.S = S
        self.env = mock.patch.dict(os.environ)
        self.env.start()
        os.environ.pop("FOLIO_SUITE_DIR", None)                   # nie den echten Suite-Ordner
        self.tmp = TemporaryDirectory()
        self.old = S.STATE
        S.STATE = S.State(Path(self.tmp.name))
        S.STATE.envs.ensure()
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.S.STATE = self.old
        self.tmp.cleanup()
        self.env.stop()

    def post(self, path, obj):
        r = urllib.request.Request(f"http://127.0.0.1:{self.srv.server_address[1]}{path}", data=json.dumps(obj).encode(), method="POST")
        try:
            with urllib.request.urlopen(r, timeout=120) as f:
                return f.status, json.loads(f.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def publish(self, share=None, title="Laserbeugung"):
        e = self.S.STATE.envs
        return Sharebox(e.suite, e.project).publish_dataset(PRODUCER, title, dataset(title), ["rechner"], share_id=share)["id"]

    def test_flow(self):
        sid = self.publish()                                          # an ein anderes Modul adressiert – lesbar (I-01)
        c, info = self.post("/api/dataset/columns", {"id": sid})
        self.assertEqual(c, 200, info)
        self.assertEqual(([x["key"] for x in info["columns"]], info["version"], info["latest"]), (["d", "dmm"], 1, 1))
        c, j = self.post("/api/dataset/compare", {"id": sid, "key": "dmm", "unit": "µm"})
        self.assertEqual(c, 200, j)
        self.assertAlmostEqual(j["stats"]["D50"], float(np.percentile(SIZES_UM[1:], 50)), places=4)
        self.assertEqual((j["cmp"]["share"], j["cmp"]["mode"], j["cmp"]["version"]), (sid, "live", 1))
        c, e = self.post("/api/dataset/compare", {"id": sid, "key": "t", "unit": "µm"})
        self.assertEqual(c, 400)
        self.assertIn("keine Länge", e["error"])
        c, e = self.post("/api/dataset/compare", {"id": sid, "key": "fehlt"})
        self.assertEqual(c, 400)
        c, e = self.post("/api/dataset/columns", {"id": "s-00000000"})
        self.assertEqual(c, 400)
        self.publish(share=sid)
        c, lt = self.post("/api/dataset/latest", {"ids": [sid, "s-00000000"]})
        self.assertEqual(lt["latest"], {sid: 2, "s-00000000": None})
        c, j1 = self.post("/api/dataset/compare", {"id": sid, "mode": "pin", "version": 1, "key": "d"})
        self.assertEqual((j1["cmp"]["version"], j1["latest"]), (1, 2))
        # Export und Bericht mit der Vergleichsverteilung
        c, img = self.post("/api/sample", {})
        state = {**STATE, "compare": j1["cmp"]}
        c, ex = self.post("/api/export", {"id": img["id"], **state})
        self.assertEqual(c, 200, ex)
        self.assertIn("vergleichsverteilung.csv", ex["files"])
        self.assertIn("vergleichsverteilung.png", ex["files"])
        c, b = self.post("/api/bundle", {"items": [{"id": img["id"], "state": state}], "lang": "de"})
        self.assertEqual(c, 200, b)
        self.assertIn((sid, 1), labprov.refs_in_request(b["source"]["request"])["shares"])


if __name__ == "__main__":
    unittest.main()
