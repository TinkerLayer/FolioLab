"""DP-13: TGA-Lauf aus einem Datensatz (`data.table`) der Datenaufbereitung.

Ein Datensatz aus den Spalten der synthetischen Oxalat-CSV muss dieselben Stufen ergeben wie die CSV selbst; Einheiten
werden umgerechnet, unpassende abgelehnt; der Lauf übersteht das Neuladen der Umgebung und nennt im Bericht ID und
Version des Datensatzes. Alles in einem temporären Suite-Ordner.
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

from tga import readers as RD  # noqa: E402
from tga import steps as ST  # noqa: E402
from tga import synth as SY  # noqa: E402


def oxalate():
    """(Rohdatei, Name, Spalten t/T/m) der synthetischen Oxalat-Probe."""
    data, name = SY.make("oxalat")[0]
    rows = [ln.split(";") for ln in data.decode("utf-8").splitlines() if ln.strip() and not ln.startswith("#")][1:]
    return data, name, np.array(rows, dtype=float)


class DatasetRun(unittest.TestCase):
    def setUp(self):
        from tga import server as S
        self.S = S
        self.env = mock.patch.dict(os.environ)
        self.env.start()
        os.environ.pop("FOLIO_SUITE_DIR", None)                   # nie den echten Suite-Ordner
        self.tmp = TemporaryDirectory()
        self.old = S.STATE
        S.STATE = S.State(Path(self.tmp.name))
        S.STATE.envs.ensure()
        self.raw, self.name, self.a = oxalate()

    def tearDown(self):
        self.S.STATE = self.old
        self.tmp.cleanup()
        self.env.stop()

    def publish(self, cols, share=None, recipients=("tga",), title="Oxalat aus CSV", **head):
        e = self.S.STATE.envs
        ds = DSET.from_columns(title, cols, **head)
        return Sharebox(e.suite, e.project).publish_dataset({"module": "datenaufbereitung", "env": "e1", "env_name": "Prüfung"},
                                                            title, ds, list(recipients), share_id=share)

    def cols(self, units=("min", "°C", "mg"), f=(1.0, 0.0, 1.0)):
        t, T, m = self.a[:, 0], self.a[:, 1], self.a[:, 2]
        return [{"key": "t", "name": "Zeit", "unit": units[0], "values": t * f[0]},
                {"key": "T", "name": "Temperatur", "unit": units[1], "values": T + f[1]},
                {"key": "m", "name": "Masse", "unit": units[2], "values": m * f[2]}]

    COND = {"Einwaage": {"value": 10.0, "unit": "mg"}, "Heizrate": {"value": 10, "unit": "K/min"}}

    def run_of(self, d):
        return self.S.item(d["id"]).run

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

    def assertSameSteps(self, r, loss=1e-6, temp=1e-6):
        a0, a1 = ST.analyse(RD.load_bytes(self.raw, self.name)[0]), ST.analyse(r)
        self.assertEqual(len(a1["steps"]), 3)
        self.assertEqual(len(a0["steps"]), len(a1["steps"]))
        for s0, s1 in zip(a0["steps"], a1["steps"]):
            self.assertAlmostEqual(s0["loss"], s1["loss"], delta=loss)
            for k in ("T_onset", "T_peak", "T_endset"):
                self.assertAlmostEqual(s0[k], s1[k], delta=temp, msg=k)
        self.assertAlmostEqual(a0["residue"]["end"], a1["residue"]["end"], delta=loss)

    def test_oxalate_dataset_same_steps_as_csv(self):
        env = self.publish(self.cols(), conditions=self.COND)
        sid = env["id"]
        other = self.publish(self.cols(), recipients=("rechner",))["id"]   # nicht an die TGA adressiert – lesbar (I-01)
        lst = self.S.ds_list()["datasets"]
        self.assertEqual(sorted(d["id"] for d in lst), sorted([sid, other]))
        lst = [d for d in lst if d["id"] == sid]
        self.assertEqual([c["guess"] for c in lst[0]["columns"]], ["t", "T", "m"])
        runs = self.S.ds_run({"id": sid, "mode": "live", "roles": {"t": "t", "T": "T", "m": "m"}})
        self.assertEqual(len(runs), 1)
        r = self.run_of(runs[0])
        self.assertEqual((r.m0, r.meta.get("rate"), r.unit), (10.0, 10.0, "mg"))
        self.assertSameSteps(r)
        src = r.meta["dataset"]
        self.assertEqual((src["share"], src["version"], src["mode"], src["title"]), (sid, 1, "live", "Oxalat aus CSV"))
        self.assertEqual(src["columns"]["T"], {"key": "T", "name": "Temperatur", "unit": "°C"})
        self.assertEqual(runs[0]["ds_latest"], 1)

    def test_units_converted(self):
        """Zeit in s, Temperatur in K, Masse in g: gleiche Stufen (Einwaage dann aus dem ersten Messwert)."""
        sid = self.publish(self.cols(("s", "K", "g"), (60.0, 273.15, 1e-3)))["id"]
        r = self.run_of(self.S.ds_run({"id": sid, "roles": {"t": "t", "T": "T", "m": "m"}})[0])
        self.assertAlmostEqual(float(r.t[-1]), float(self.a[-1, 0]), places=6)
        self.assertAlmostEqual(float(r.T[0]), float(self.a[0, 1]), places=6)
        self.assertSameSteps(r, loss=5e-3, temp=0.05)
        # Masse in % (dimensionslos) ergibt einen Lauf in %
        pct = self.cols(("min", "°C", "%"), (1.0, 0.0, 10.0))
        sid2 = self.publish(pct, title="Oxalat in Prozent")["id"]
        r2 = self.run_of(self.S.ds_run({"id": sid2, "roles": {"t": "t", "T": "T", "m": "m"}})[0])
        self.assertEqual(r2.unit, "%")
        self.assertSameSteps(r2, loss=5e-3, temp=0.05)

    def test_unit_mismatch_refused(self):
        cols = self.cols()
        cols.append({"key": "q", "name": "Anteil", "unit": "", "values": self.a[:, 2]})
        sid = self.publish(cols)["id"]
        for roles, word in (({"t": "t", "T": "m", "m": "m"}, "zugleich"),            # eine Spalte, zwei Rollen
                            ({"t": "t", "T": "t", "m": "m"}, "zugleich"),
                            ({"t": "T", "T": "t", "m": "m"}, "passt nicht zur Rolle"),
                            ({"t": "t", "T": "T", "m": "T"}, "zugleich"),
                            ({"t": "t", "m": "T"}, "passt nicht zur Rolle Masse"),
                            ({"t": "t", "T": "T", "m": "q"}, "keine Einheit"),
                            ({"t": "t", "T": "T"}, "Massenspalte")):
            with self.assertRaises(ValueError, msg=roles) as cm:
                self.S.ds_run({"id": sid, "roles": roles})
            self.assertIn(word, str(cm.exception), roles)
        self.assertEqual(self.S.STATE.items, {})                     # nichts angelegt
        # über HTTP: 400 mit deutscher Meldung
        code, r = self.http("/api/dataset/run", {"id": sid, "roles": {"t": "T", "T": "t", "m": "m"}})
        self.assertEqual(code, 400)
        self.assertIn("passt nicht zur Rolle Zeit", r["error"])
        code, r = self.http("/api/dataset/run", {"id": "s-00000000", "roles": {"t": "t", "T": "T", "m": "m"}})
        self.assertEqual(code, 400)                                   # Freigabe fehlt

    def test_excluded_rows_restore_refresh_and_report(self):
        from tga import bundle as B
        env = self.publish(self.cols(), conditions=self.COND, flags=[{"row": 10, "code": "outlier", "excluded": True}])
        sid = env["id"]
        d = self.S.ds_run({"id": sid, "mode": "pin", "version": 1, "roles": {"t": "t", "T": "T", "m": "m"}})[0]
        iid = d["id"]
        r = self.run_of(d)
        self.assertEqual(len(r.m), len(self.a) - 1)                   # ausgeschlossene Zeile fehlt
        self.assertNotIn(float(self.a[10, 0]), r.t.tolist())
        self.assertEqual((r.meta["dataset"]["excluded"], r.meta["dataset"]["mode"]), (1, "pin"))
        self.S.item(iid).run.name = "Oxalat DS"                       # wie /api/rename
        self.S.STATE.envs.set_name(iid, "Oxalat DS")
        # Neuladen der Umgebung (Neustart): gleicher Lauf, gleiche Herkunft
        out = self.S.reload_env()
        self.assertEqual([x["id"] for x in out], [iid])
        r2 = self.run_of(out[0])
        self.assertEqual((r2.name, len(r2.m), r2.meta["dataset"]["share"]), ("Oxalat DS", len(r.m), sid))
        self.assertEqual(self.S.STATE.envs.items[iid]["extra"]["dataset"], {"share": sid, "version": 1, "mode": "pin"})
        # Bericht nennt ID und Version; Anfrage trägt die Freigabe für die Herkunftskette
        it = self.S.item(iid)
        b = B.build([(it.raw, it.fname, it.mapping, {})], {"items": [{"name": it.fname}]}, lang="de")
        txt = base64.b64decode(b["files"]["text-methodik.tex"]).decode("utf-8")
        self.assertIn(f"ID {sid}, Version 1", txt)
        self.assertIn("1 als ausgeschlossen markierte Zeile blieb unberücksichtigt", txt)
        self.assertNotIn("„", txt)
        txt.encode("latin-1")
        en = base64.b64decode(B.build([(it.raw, it.fname, it.mapping, {})], {"items": [{"name": it.fname}]}, lang="en")
                              ["files"]["text-methodik.tex"]).decode("utf-8")
        self.assertIn(f"ID {sid}, version 1", en)
        import labprov
        code, bb = self.http("/api/bundle", {"items": [{"id": iid, "state": {}}]})
        self.assertEqual(code, 200, bb)
        self.assertIn((sid, 1), labprov.refs_in_request(bb["source"]["request"])["shares"])   # Bericht hält v1 fest
        # neue Version: Hinweis, dann auf Wunsch aktualisieren (ID, Name bleiben)
        cols = self.cols()
        cols[2]["values"] = cols[2]["values"] * 0.5
        self.publish(cols, share=sid, conditions={"Einwaage": {"value": 5.0, "unit": "mg"}})
        self.assertEqual(self.S.describe(iid)["ds_latest"], 2)
        res = self.S.ds_refresh({"id": iid})
        self.assertTrue(res["changed"])
        r3 = self.run_of(res["run"])
        self.assertEqual((r3.name, r3.meta["dataset"]["version"], r3.m0), ("Oxalat DS", 2, 5.0))
        self.assertEqual(len(r3.m), len(self.a))                      # v2 ohne Ausschluss
        self.assertFalse(self.S.ds_refresh({"id": iid})["changed"])
        self.assertEqual(self.run_of(self.S.reload_env()[0]).meta["dataset"]["version"], 2)

    def test_gas_text_column_and_extra_roles(self):
        n = len(self.a)
        cols = self.cols() + [{"key": "gas", "name": "Gas", "dtype": "text", "values": ["N2"] * (n // 2) + ["Luft"] * (n - n // 2)},
                              {"key": "Tp", "name": "Ofen", "unit": "K", "values": self.a[:, 1] + 274.15}]
        sid = self.publish(cols)["id"]
        r = self.run_of(self.S.ds_run({"id": sid, "roles": {"t": "t", "T": "T", "m": "m", "gas": "gas", "Tprog": "Tp"}})[0])
        self.assertEqual(r.meta["gas_names"], ["N₂", "Luft"])
        self.assertAlmostEqual(float(r.extra["Tprog"][0] - r.T[0]), 1.0, places=6)
        with self.assertRaises(ValueError):
            self.S.ds_run({"id": sid, "roles": {"t": "t", "T": "T", "m": "m", "gas": "T"}})


if __name__ == "__main__":
    unittest.main()
