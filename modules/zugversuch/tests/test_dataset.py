"""I-03: ganzer Zugversuch aus einem Datensatz (`data.table`) der Datenaufbereitung.

Dieselbe synthetische Kurve einmal als Spannung + Dehnung, einmal als Kraft + Verlängerung muss dieselben Kennwerte
ergeben (Rm, scheinbarer Modul, Dehnung bei Rm). Die Masse, mit denen übersetzt wurde, bleiben fest; gleiche Wege ergeben
keine gleichen Zeitstempel; der Server legt die Messung an, aktualisiert sie auf eine neue Version, liest sie nach dem
Neustart wieder und der Bericht zitiert den Datensatz mit Version. Alles in einem temporären Suite-Ordner.
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

from flps import analyse  # noqa: E402
from flps import dataset as ZD  # noqa: E402
from flps.parser import parse_bytes  # noqa: E402

A0, L0, V = 0.2, 10.0, 1.0          # mm², mm, mm/min
E_MPA = 70_000.0


def curve():
    """(ε [1], σ [MPa]): linear bis 105 MPa, Verfestigung bis Rm ≈ 140 MPa, Einschnürung, Bruch."""
    eps = np.concatenate([np.linspace(0, 0.002, 81), np.linspace(0.002, 0.12, 400)[1:]])
    ey = 105.0 / E_MPA
    sig = np.where(eps <= ey, E_MPA * eps, 105.0 + 35.0 * (1 - np.exp(-(eps - ey) / 0.02)))
    neck = eps > 0.09
    sig = np.where(neck, sig[np.searchsorted(eps, 0.09)] - (eps - 0.09) / 0.03 * 20.0, sig)
    return np.append(eps, [0.12005, 0.1201]), np.append(sig, [0.3, 0.1])    # Lastabfall unter 1 % von Fmax


def cfg_from(c: dict, **kw) -> analyse.Config:
    return analyse.Config.from_dict({**c, "displacement_source": "probe", **kw})


class Translate(unittest.TestCase):
    """Übersetzung ohne Server: Datensatz → JSON → FlpsFile → Auswertung."""

    def ds(self, kind="stress", extra=None, **head):
        eps, sig = curve()
        if kind == "stress":
            cols = [{"key": "e", "name": "Dehnung", "unit": "%", "values": eps * 100},
                    {"key": "s", "name": "Spannung", "unit": "MPa", "values": sig}]
        else:
            cols = [{"key": "dl", "name": "Verlängerung", "unit": "mm", "values": eps * L0},
                    {"key": "F", "name": "Kraft", "unit": "N", "values": sig * A0}]
        return DSET.from_columns(f"Kurve {kind}", cols + (extra or []), **head)

    def evaluate(self, ds, roles, geo=None, **kw):
        raw, name, c = ZD.make_raw(ds, roles, geo or {"a0_mm2": A0, "l0_mm": L0, "speed_mm_min": V},
                                   {"share": "s-0000abcd", "title": ds.header.get("title"), "version": 1,
                                    "created": "2026-11-18T10:00:00"})
        f = parse_bytes(raw, name)
        return analyse.run(f, cfg_from(c, **kw)), f, raw, c

    def test_guess_and_columns(self):
        info = ZD.columns_info(self.ds())
        self.assertEqual(info["guess"], {"load": "s", "ext": "e", "t": None})
        self.assertEqual([c["q"] for c in info["columns"]], ["strain", "stress"])
        t = {"key": "t", "name": "Zeit", "unit": "s", "values": np.arange(len(curve()[0])) * 0.1}
        info = ZD.columns_info(self.ds("force", [t], conditions={"Querschnitt": {"value": 0.2, "unit": "mm2"},
                                                                  "L0 Messlänge": {"value": 1.0, "unit": "cm"},
                                                                  "v": {"value": 1.0, "unit": "mm/min"}}))
        self.assertEqual(info["guess"], {"load": "F", "ext": "dl", "t": "t"})
        g = info["geometry"]
        self.assertAlmostEqual(g["a0_mm2"], 0.2)
        self.assertAlmostEqual(g["l0_mm"], 10.0)
        self.assertAlmostEqual(g["speed_mm_min"], 1.0)
        # Dimensionslose Spalte ohne Einheit und ohne Namenshinweis ist keine Dehnung
        self.assertIsNone(ZD.kind_of({"key": "q", "name": "Anteil", "unit": ""}))
        self.assertEqual(ZD.kind_of({"key": "q", "name": "eps", "unit": ""}), "strain")

    def test_same_result_both_ways(self):
        rs, f, _raw, _c = self.evaluate(self.ds(), {"load": "s", "ext": "e"})
        rf, _f, _r, _c = self.evaluate(self.ds("force"), {"load": "F", "ext": "dl"})
        eps, sig = curve()
        self.assertEqual(rs.mode, "Spannung")
        self.assertAlmostEqual(rs.kv["Rm"], float(sig.max()), delta=0.01)
        self.assertAlmostEqual(rs.kv["Rm"], rf.kv["Rm"], delta=1e-3)
        self.assertAlmostEqual(rs.e_schein_gpa, E_MPA / 1000, delta=E_MPA / 1000 * 0.03)
        self.assertAlmostEqual(rs.e_schein_gpa, rf.e_schein_gpa, delta=1e-3)
        self.assertAlmostEqual(rs.kv["strain_max_pct"], float(eps[np.argmax(sig)] * 100), delta=0.05)
        self.assertAlmostEqual(rs.kv["strain_max_pct"], rf.kv["strain_max_pct"], delta=1e-3)
        self.assertIsNotNone(rs.kv["break"])
        self.assertEqual(rs.kv["test_type"], "Zug")
        self.assertEqual(f.displacement_unit, "µm")
        self.assertEqual(f.origin["roles"]["load"]["q"], "stress")
        self.assertTrue(any(w["code"] == "I-03" for w in rs.warnings))
        self.assertTrue(rs.device["origin"])

    def test_geometry_locked(self):
        r, *_ = self.evaluate(self.ds(), {"load": "s", "ext": "e"}, a0_mm2=0.5, l0_mm=50, speed_mm_min=5)
        self.assertEqual((r.config.a0_mm2, r.config.l0_mm, r.config.speed_mm_min), (A0, L0, V))
        texts = " ".join(w["text"] for w in r.warnings if w["code"] == "I-03")
        self.assertIn("A0 bleibt", texts)
        self.assertIn("L0 bleibt", texts)
        self.assertIn("v bleibt", texts)
        _eps, sig = curve()
        self.assertAlmostEqual(r.kv["Rm"], float(sig.max()), delta=0.01)
        # Kraft + Verlängerung: A0 ist frei (Spannung = F / A0), L0 und v hängen am Weg
        r2, *_ = self.evaluate(self.ds("force"), {"load": "F", "ext": "dl"}, a0_mm2=0.4)
        self.assertAlmostEqual(r2.kv["Rm"], float(sig.max()) / 2, delta=0.01)

    def test_errors(self):
        ds = self.ds()
        for roles, geo, word in (({"ext": "e"}, {}, "Kraft oder Spannung wählen"),
                                 ({"load": "e", "ext": "e"}, {}, "weder eine Kraft"),
                                 ({"load": "s", "ext": "s"}, {"a0_mm2": 1}, "weder eine Verlängerung"),
                                 ({"load": "s", "ext": "e"}, {"l0_mm": 10}, "A0 fehlt"),
                                 ({"load": "s", "ext": "e"}, {"a0_mm2": 1}, "L0 fehlt"),
                                 ({"load": "s"}, {"a0_mm2": 1}, "Weg"),
                                 ({"load": "s", "ext": "e"}, {"a0_mm2": -1, "l0_mm": 10}, "grösser als 0"),
                                 ({"load": "s", "ext": "e"}, {"a0_mm2": "x", "l0_mm": 10}, "keine Zahl")):
            with self.assertRaises(ZD.DatasetTestError, msg=roles) as cm:
                ZD.make_raw(ds, roles, geo, {})
            self.assertIn(word, str(cm.exception), roles)
        short = DSET.from_columns("kurz", [{"key": "F", "name": "Kraft", "unit": "N", "values": [1, 2, 3]},
                                           {"key": "dl", "name": "Weg", "unit": "mm", "values": [0, 1, 2]}])
        with self.assertRaisesRegex(ZD.DatasetTestError, "Zu wenige"):
            ZD.make_raw(short, {"load": "F", "ext": "dl"}, {}, {})

    def test_time_axis_speed_and_duplicates(self):
        # Zeitspalte ohne v: v aus der Zeit gemittelt; doppelte Wege ergeben streng steigende Zeitstempel
        eps, sig = curve()
        n = len(eps)
        dl = eps * L0
        dl[5] = dl[4]
        t = dl / (2.0 / 60)                                       # 2 mm/min
        ds = DSET.from_columns("mit Zeit", [{"key": "dl", "name": "Weg", "unit": "mm", "values": dl},
                                            {"key": "F", "name": "Kraft", "unit": "N", "values": sig * A0},
                                            {"key": "t", "name": "Zeit", "unit": "s", "values": t}])
        raw, _n, c = ZD.make_raw(ds, {"load": "F", "ext": "dl", "t": "t"}, {"a0_mm2": A0, "l0_mm": L0}, {})
        self.assertAlmostEqual(c["speed_mm_min"], 2.0, places=6)
        d = json.loads(raw)
        self.assertEqual(d["time_from"], "elongation")
        self.assertIn("gemittelt", d["notes"][0])
        self.assertEqual(len(d["t"]), n)
        f = parse_bytes(raw, "x.json")
        ts = [p.timestamp for p in f.points]
        self.assertTrue(all(b > a for a, b in zip(ts, ts[1:])))
        # ohne v und ohne Zeit: 1 mm/min mit Hinweis; ohne Weg: Zeitspalte, F negativ (Zug) oder positiv (Druck)
        raw, _n, c = ZD.make_raw(ds, {"load": "F", "ext": "dl"}, {"a0_mm2": A0, "l0_mm": L0}, {})
        self.assertEqual(c["speed_mm_min"], 1.0)
        self.assertIn("1 mm/min", json.loads(raw)["notes"][0])
        d = json.loads(ZD.make_raw(ds, {"load": "F", "t": "t"}, {"compression": True}, {})[0])
        self.assertEqual((d["time_from"], d["dL"]), ("column", None))
        self.assertGreater(max(d["F"]), 0)
        self.assertTrue(ZD.is_dataset(ZD.make_raw(ds, {"load": "F", "t": "t"}, {}, {})[0]))


class ServerFlow(unittest.TestCase):
    """Über den Modulserver: Spalten, Messung anlegen, neue Version, Neustart, Bericht."""

    def setUp(self):
        from flps.ui import server as S
        self.S = S
        self.env = mock.patch.dict(os.environ)
        self.env.start()
        os.environ.pop("FOLIO_SUITE_DIR", None)                   # nie den echten Suite-Ordner
        self.tmp = TemporaryDirectory()
        self.old = S.STATE
        S.STATE = S.State(Path(self.tmp.name), None)
        S.STATE.envs.ensure()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.S.STATE = self.old
        self.tmp.cleanup()
        self.env.stop()

    def call(self, path, body):
        req = urllib.request.Request(f"http://127.0.0.1:{self.httpd.server_address[1]}{path}", method="POST",
                                     data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def publish(self, scale=1.0, share=None, recipients=("datenaufbereitung",)):
        eps, sig = curve()
        e = self.S.STATE.envs
        ds = DSET.from_columns("Probe 7", [{"key": "e", "name": "Dehnung", "unit": "%", "values": eps * 100},
                                           {"key": "s", "name": "Spannung", "unit": "MPa", "values": sig * scale}],
                               conditions={"A0": {"value": A0, "unit": "mm2"}, "L0": {"value": L0, "unit": "mm"}})
        return Sharebox(e.suite, e.project).publish_dataset({"module": "datenaufbereitung", "env": "e1", "env_name": "Prüfung",
                                                             "item_name": "Probe 7"}, "Probe 7", ds, list(recipients),
                                                            share_id=share)["id"]

    def test_flow(self):
        sid = self.publish()                                          # nicht an den Zugversuch adressiert – lesbar (I-01)
        code, info = self.call("/api/dataset/columns", {"id": sid})
        self.assertEqual(code, 200, info)
        self.assertEqual((info["guess"]["load"], info["guess"]["ext"], info["version"]), ("s", "e", 1))
        self.assertAlmostEqual(info["geometry"]["l0_mm"], L0)
        code, err = self.call("/api/dataset/test", {"id": sid, "roles": {"load": "s", "ext": "e"}, "geometry": {"l0_mm": L0}})
        self.assertEqual(code, 400)
        self.assertIn("A0 fehlt", err["error"])
        self.assertEqual(self.S.STATE.files, {})
        code, j = self.call("/api/dataset/test", {"id": sid, "roles": {"load": "s", "ext": "e"},
                                                  "geometry": {"a0_mm2": A0, "l0_mm": L0, "speed_mm_min": V,
                                                               "displacement_source": "probe"}})
        self.assertEqual(code, 200, j)
        fid = j["id"]
        self.assertEqual((j["name"], j["dataset"]["version"], j["dataset"]["mode"]), ("Probe 7", 1, "live"))
        cfg = {**j["config"], "shape": "ISO 527-2 Typ 5B"}
        code, d = self.call("/api/analyse", {"id": fid, "config": cfg})
        self.assertEqual(code, 200, d)
        _eps, sig = curve()
        self.assertAlmostEqual(d["kv"]["Rm"], float(sig.max()), delta=0.01)
        self.assertEqual(d["device"]["origin"]["share"], sid)
        # Bericht: Datensatz zitiert, Version festgehalten, Text Latin-1
        code, b = self.call("/api/bundle", {"items": [{"id": fid, "config": cfg}], "lang": "de"})
        self.assertEqual(code, 200, b)
        bib = base64.b64decode(b["files"]["refs.bib"]).decode("utf-8")
        self.assertIn("Datensatz Probe 7", bib)
        self.assertIn(f"{sid}, Version 1", bib)
        txt = base64.b64decode(b["files"]["text-methodik.tex"]).decode("utf-8")
        self.assertIn("Ausgewertet wurde der Datensatz", txt)
        self.assertIn("Spannung [MPa]", txt)
        txt.encode("latin-1")
        import labprov
        self.assertIn((sid, 1), labprov.refs_in_request(b["source"]["request"])["shares"])
        code, b2 = self.call("/api/bundle/rebuild", {"source": b["source"], "lang": "en"})
        self.assertEqual(code, 200, b2)
        en = base64.b64decode(b2["files"]["text-methodik.tex"]).decode("utf-8")
        self.assertIn("The dataset", en)
        # neue Version: "latest" meldet sie, refresh übernimmt sie (ID bleibt), zweimal ändert nichts
        self.publish(scale=1.1, share=sid)
        code, lt = self.call("/api/dataset/latest", {})
        self.assertEqual(lt["files"][fid]["latest"], 2)
        code, rf = self.call("/api/dataset/refresh", {"file": fid})
        self.assertEqual((code, rf["changed"], rf["version"]), (200, True, 2))
        self.assertFalse(self.call("/api/dataset/refresh", {"file": fid})[1]["changed"])
        self.assertEqual(self.S.STATE.files[fid].origin["version"], 2)
        # Neustart: die Messung kommt aus der Umgebung zurück, mit Herkunft und neuer Version
        out = self.S.reload_env()
        self.assertEqual([x["id"] for x in out], [fid])
        f = self.S.STATE.files[fid]
        self.assertEqual((f.origin["share"], f.origin["version"]), (sid, 2))
        code, d2 = self.call("/api/analyse", {"id": fid, "config": cfg})
        self.assertAlmostEqual(d2["kv"]["Rm"], float(sig.max()) * 1.1, delta=0.02)
        # gepinnte Version 1 neu anlegen; unbekannte Freigabe -> 400
        code, j1 = self.call("/api/dataset/test", {"id": sid, "mode": "pin", "version": 1, "roles": {"load": "s", "ext": "e"},
                                                   "geometry": {"a0_mm2": A0, "l0_mm": L0}})
        self.assertEqual((code, j1["dataset"]["version"], j1["dataset"]["latest"]), (200, 1, 2))
        code, _e = self.call("/api/dataset/columns", {"id": "s-00000000"})
        self.assertEqual(code, 400)


if __name__ == "__main__":
    unittest.main()
