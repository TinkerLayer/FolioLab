"""DP-13: FTIR-Spektren aus einem Datensatz (`data.table`) der Datenaufbereitung.

x = Wellenzahl (oder Wellenlänge, umgerechnet), jede y-Spalte ein Spektrum mit dem Spaltennamen; unpassende Einheiten
werden abgelehnt; Spektren überstehen das Neuladen der Umgebung und nennen im Bericht ID und Version des Datensatzes.
Alles in einem temporären Suite-Ordner.
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
from labshare import Sharebox  # noqa: E402

NU = np.arange(4000.0, 399.0, -2.0)                       # absteigend wie in vielen Exporten


def band(x0, w, h):
    return h * np.exp(-0.5 * ((NU - x0) / w) ** 2)


PE = 0.02 + band(2917, 12, 0.9) + band(2849, 10, 0.7) + band(1470, 8, 0.3) + band(720, 6, 0.2)
PS = 0.03 + band(3026, 10, 0.25) + band(1601, 6, 0.2) + band(1493, 6, 0.5) + band(698, 8, 0.95)


class DatasetSpectra(unittest.TestCase):
    def setUp(self):
        from ftir import server as S
        self.S = S
        self.env = mock.patch.dict(os.environ)
        self.env.start()
        os.environ.pop("FOLIO_SUITE_DIR", None)                   # nie den echten Suite-Ordner
        self.tmp = TemporaryDirectory()
        self.old = S.STATE
        S.STATE = S.State(Path(self.tmp.name))
        S.STATE.envs.ensure()

    def tearDown(self):
        self.S.STATE = self.old
        self.tmp.cleanup()
        self.env.stop()

    def publish(self, cols, share=None, recipients=("ftir",), title="Folien", **head):
        e = self.S.STATE.envs
        ds = DSET.from_columns(title, cols, **head)
        return Sharebox(e.suite, e.project).publish_dataset({"module": "datenaufbereitung", "env": "e1", "env_name": "Prüfung"},
                                                            title, ds, list(recipients), share_id=share)

    def cols(self, xunit="1/cm", x=None):
        return [{"key": "nu", "name": "Wellenzahl", "unit": xunit, "values": NU if x is None else x},
                {"key": "pe", "name": "PE-Folie", "unit": "", "values": PE},
                {"key": "ps", "name": "PS-Becher", "unit": "1", "values": PS},
                {"key": "note", "name": "Notiz", "dtype": "text", "values": ["a"] * len(NU)}]

    def sp(self, d):
        return self.S.item(d["id"]).sp

    def http(self, path, obj):
        """POST an einen eigenen Modulserver (freier Port) für die Dauer eines Aufrufs."""
        srv = ThreadingHTTPServer(("127.0.0.1", 0), self.S.Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}{path}", method="POST",
                                         data=json.dumps(obj).encode(), headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read() or b"{}")
        finally:
            srv.shutdown()
            srv.server_close()

    def test_two_columns_two_spectra(self):
        sid = self.publish(self.cols())["id"]
        other = self.publish(self.cols(), recipients=("tga",))["id"]  # nicht an das FTIR adressiert – lesbar (I-01)
        lst = self.S.ds_list()["datasets"]
        self.assertEqual(sorted(d["id"] for d in lst), sorted([sid, other]))
        lst = [d for d in lst if d["id"] == sid]
        self.assertEqual([c["guess"] for c in lst[0]["columns"]], ["x", "y", "y", ""])
        out = self.S.ds_spectra({"id": sid, "x": "nu", "y": ["pe", "ps"]})
        self.assertEqual([d["name"] for d in out], ["PE-Folie", "PS-Becher"])
        for d, y in zip(out, (PE, PS)):
            sp = self.sp(d)
            self.assertEqual((sp.yunit, len(sp.x)), ("A", len(NU)))
            np.testing.assert_allclose(sp.x, NU[::-1], atol=1e-4)            # intern aufsteigend
            np.testing.assert_allclose(sp.y, y[::-1], rtol=1e-5, atol=1e-7)
            self.assertEqual((sp.meta["dataset"]["share"], sp.meta["dataset"]["version"]), (sid, 1))
            self.assertEqual(d["ds_latest"], 1)
        self.assertEqual(self.sp(out[1]).meta["dataset"]["columns"]["y"], {"key": "ps", "name": "PS-Becher", "unit": "1"})
        # Neuladen der Umgebung: beide Spektren mit Herkunft
        back = self.S.reload_env()
        self.assertEqual(sorted(x["id"] for x in back), sorted(x["id"] for x in out))
        self.assertTrue(all(self.sp(x).meta["dataset"]["share"] == sid for x in back))

    def test_transmittance_and_wavelength(self):
        T = 100 * 10 ** (-PE)
        cols = [{"key": "lam", "name": "Wellenlänge", "unit": "µm", "values": 1e4 / NU},
                {"key": "t", "name": "Probe", "unit": "%", "values": T},
                {"key": "tf", "name": "Probe Transmission", "unit": "1", "values": T / 100}]
        sid = self.publish(cols)["id"]
        self.assertEqual([c["guess"] for c in self.S.ds_list()["datasets"][0]["columns"]], ["x", "y", "y"])
        a, b = self.S.ds_spectra({"id": sid, "x": "lam", "y": ["t", "tf"]})
        for d in (a, b):
            sp = self.sp(d)
            self.assertEqual(sp.yunit, "T")                              # % -> T; Name „Transmission“ -> T
            self.assertAlmostEqual(float(sp.x[0]), 400.0, places=3)
            self.assertAlmostEqual(float(sp.x[-1]), 4000.0, places=3)
            self.assertAlmostEqual(float(np.interp(1000.0, sp.x, sp.y)), float(np.interp(1000.0, NU[::-1], T[::-1])), places=3)
            self.assertIn("Wellenlänge", sp.meta["dataset"]["x_note"])
        # gewählte Einheit geht vor: Reflexion
        c = self.sp(self.S.ds_spectra({"id": sid, "x": "lam", "y": ["t"], "yunit": "R"})[0])
        self.assertEqual(c.yunit, "R")

    def test_unit_mismatch_refused(self):
        cols = self.cols() + [{"key": "m", "name": "Masse", "unit": "mg", "values": PE},
                              {"key": "raw", "name": "Index", "unit": "", "values": np.arange(len(NU), dtype=float)},
                              {"key": "pct", "name": "Anteil", "unit": "%", "values": PE * 100}]
        sid = self.publish(cols)["id"]
        for req, word in (({"x": "m", "y": ["pe"]}, "passt nicht zur x-Achse"),
                          ({"x": "raw", "y": ["pe"]}, "keine Einheit"),
                          ({"x": "nu", "y": ["m"]}, "keine Absorbanz oder Transmission"),
                          ({"x": "nu", "y": ["pct"], "yunit": "A"}, "dimensionslos"),
                          ({"x": "nu", "y": ["note"]}, "Text"),
                          ({"x": "nu", "y": []}, "y-Spalte"),
                          ({"x": "nu", "y": ["nu"]}, "zugleich")):
            with self.assertRaises(ValueError, msg=req) as cm:
                self.S.ds_spectra({"id": sid, **req})
            self.assertIn(word, str(cm.exception), req)
        self.assertEqual(self.S.STATE.items, {})                     # nichts angelegt
        code, r = self.http("/api/dataset/spectra", {"id": sid, "x": "m", "y": ["pe"]})
        self.assertEqual(code, 400)
        self.assertIn("passt nicht zur x-Achse", r["error"])

    def test_excluded_refresh_and_report(self):
        from ftir import bundle as B
        cols = self.cols()
        cols[1]["values"] = PE.copy()
        cols[1]["values"][5] = 50.0                                   # Ausreisser, im Datensatz ausgeschlossen
        sid = self.publish(cols, flags=[{"row": 5, "code": "outlier", "excluded": True}])["id"]
        out = self.S.ds_spectra({"id": sid, "mode": "pin", "version": 1, "x": "nu", "y": ["pe", "ps"]})
        sp = self.sp(out[0])
        self.assertLess(float(sp.y.max()), 1.0)                       # Zeile fehlt; die Lücke wird wie beim Einlesen
        self.assertIn("resampled", sp.meta)                           # auf das gleichmässige Raster interpoliert
        self.assertEqual((sp.meta["dataset"]["excluded"], sp.meta["dataset"]["mode"]), (1, "pin"))
        items = [(self.S.item(d["id"]).raw, self.S.item(d["id"]).fname, 0, {}) for d in out]
        b = B.build(items[:1], {"items": [{"name": items[0][1]}]}, lang="de")
        txt = base64.b64decode(b["files"]["text-methodik.tex"]).decode("utf-8")
        self.assertIn(f"ID {sid}, Version 1, Spalte PE-Folie", txt)
        self.assertIn("1 als ausgeschlossen markierte Zeile blieb unberücksichtigt", txt)
        txt.encode("latin-1")
        b2 = B.build(items, {"items": [{"name": x[1]} for x in items]}, lang="en")
        en = base64.b64decode(b2["files"]["text-methodik.tex"]).decode("utf-8")
        self.assertIn(f"ID {sid}, version 1, column PE-Folie", en)
        self.assertIn("The spectrum PS-Becher comes from dataset", en)
        # neue Version: Hinweis, dann auf Wunsch aktualisieren
        cols = self.cols()
        cols[1]["values"] = PE * 2
        self.publish(cols, share=sid)
        iid = out[0]["id"]
        self.assertEqual(self.S.describe(iid)["ds_latest"], 2)
        res = self.S.ds_refresh({"id": iid})
        self.assertTrue(res["changed"])
        sp2 = self.sp(res["spectrum"])
        self.assertEqual((sp2.name, sp2.meta["dataset"]["version"], len(sp2.x)), ("PE-Folie", 2, len(NU)))
        np.testing.assert_allclose(sp2.y, 2 * PE[::-1], rtol=1e-5, atol=1e-7)
        self.assertFalse(self.S.ds_refresh({"id": iid})["changed"])
        back = {x["id"]: x for x in self.S.reload_env()}
        self.assertEqual(self.sp(back[iid]).meta["dataset"]["version"], 2)
        self.assertEqual(self.sp(back[out[1]["id"]]).meta["dataset"]["version"], 1)   # das andere bleibt gepinnt
        import labprov
        code, bb = self.http("/api/bundle", {"items": [{"id": d["id"], "state": {}} for d in out]})
        self.assertEqual(code, 200, bb)
        self.assertEqual(labprov.refs_in_request(bb["source"]["request"])["shares"], [(sid, 1), (sid, 2)])


if __name__ == "__main__":
    unittest.main()
