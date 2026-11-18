"""DP-12: Messreihen aus Datensätzen (data.table) für Arrhenius/Eyring, Reaktionsordnung und die Rb–Sr-Isochrone.

Fertig, wenn: ein Datensatz in °C und min liefert dieselbe Aktivierungsenergie und Reaktionsordnung wie dieselben
Daten, in K und s eingetippt. Die Datensätze werden wie in der Datenaufbereitung geteilt (temporäre Suite).
"""
from __future__ import annotations

import base64
import json
import math
import tempfile
import threading
import types
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import labdataset as DS
from labcalc import kinetics as K
from labcalc import nuclear as N
from labproject import EnvError, ModuleEnvs
from labshare import Sharebox

from elementrechner import analysis as AN
from elementrechner import bundle as B
from elementrechner import datasets as DSET
from elementrechner import server as SV

EA, A = 75.0, 2.0e10                       # kJ/mol, 1/s (erste Ordnung)
T_K = [290.0, 300.0, 310.0, 320.0, 330.0, 340.0]
K2, C0 = 0.05, 0.1                         # zweite Ordnung: k in L/(mol·s), c0 in mol/L
T_S = [0.0, 60.0, 120.0, 240.0, 360.0, 480.0, 600.0, 900.0]
PRODUCER = {"module": "datenaufbereitung", "env": "e1", "env_name": "Messung"}


def k_s(T):
    return A * math.exp(-EA * 1000 / (K.R * T))


def c_mol(t):
    return C0 / (1 + K2 * C0 * t)


def series(si: bool, bad_T_unit: str | None = None):
    """Eine Messreihe, 9 Zeilen: k(T) in den ersten 6 (Rest leer), c(t) in den ersten 8, Zeile 9 ausgeschlossen."""
    T = [x if si else x - 273.15 for x in T_K] + [None, None, 999.0]
    k = [k_s(x) * (1 if si else 60) for x in T_K] + [None, None, 1.0]
    t = [x if si else x / 60 for x in T_S] + [5000.0]
    c = [c_mol(x) * (1 if si else 1000) for x in T_S] + [99.0]
    return DS.from_columns("Kinetik SI" if si else "Kinetik °C/min", [
        {"key": "T", "name": "Temperatur", "unit": bad_T_unit or ("K" if si else "°C"), "values": T},
        {"key": "k", "name": "k", "unit": "1/s" if si else "1/min", "values": k},
        {"key": "t", "name": "Zeit", "unit": "s" if si else "min", "values": t},
        {"key": "c", "name": "c(A)", "unit": "mol/L" if si else "mmol/L", "values": c},
        {"key": "note", "name": "Notiz", "dtype": "text", "values": [""] * 8 + ["Ausreisser"]}],
        flags=[{"row": 8, "code": "outlier", "excluded": True, "reason": "Pipette"}])


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.envs = ModuleEnvs(Path(self.tmp.name), "elementrechner")
        self.envs.ensure()
        self.box = Sharebox(self.envs.suite, self.envs.project)

    def tearDown(self):
        self.tmp.cleanup()

    def publish(self, ds, title=None, recipients=("elementrechner",), share=None):
        return self.box.publish_dataset(PRODUCER, title or ds.header["title"], ds, list(recipients), share_id=share)

    def read(self, sid, tool, cols, **kw):
        return DSET.route(self.envs, {"id": sid, "tool": tool, "cols": cols, **kw})


class DoneWhen(Base):
    """°C und min aus dem Datensatz ergeben dieselbe Eₐ und Ordnung wie K und s von Hand."""

    def test_same_activation_energy_and_order(self):
        cmin, si = self.publish(series(False))["id"], self.publish(series(True))["id"]
        lst = {d["id"]: d for d in DSET.route(self.envs, {"list": True})["datasets"]}
        self.assertEqual(set(lst), {cmin, si})
        self.assertEqual([c["dim"] for c in lst[cmin]["columns"]], ["T", "k", "t", "c", ""])
        self.assertEqual(lst[cmin]["columns"][0]["unit"], "°C")

        typed = {"arrhenius": AN.kinetics_call("arrhenius", {"T": " ".join(map(str, T_K)),
                                                             "k": " ".join(repr(k_s(x)) for x in T_K)}),
                 "eyring": AN.kinetics_call("eyring", {"T": " ".join(map(str, T_K)), "k": " ".join(repr(k_s(x)) for x in T_K)}),
                 "order": AN.kinetics_call("order", {"t": " ".join(map(str, T_S)), "c": " ".join(repr(c_mol(x)) for x in T_S)})}
        self.assertAlmostEqual(typed["arrhenius"]["Ea_kJ"], EA, places=6)
        self.assertEqual(typed["order"]["best"], 2)

        for sid in (cmin, si):
            r = self.read(sid, "arrhenius", {"T": "T", "k": "k"})
            self.assertEqual((r["n"], r["dropped"]), (6, {"excluded": 1, "missing": 2}))     # Zeile 9 und leere k(T)
            self.assertEqual(r["unit_k"], "s⁻¹")
            for a, b in zip(r["values"]["T"], T_K):
                self.assertAlmostEqual(a, b, places=9)                                       # °C → K
            for a, x in zip(r["values"]["k"], T_K):
                self.assertAlmostEqual(a / k_s(x), 1.0, places=10)                          # 1/min → 1/s
            body = {"T": " ".join(map(str, r["values"]["T"])), "k": " ".join(map(str, r["values"]["k"])),
                    "T_unit": "K", "unit_k": r["unit_k"], "dataset": r["origin"]}
            arr, ey = AN.kinetics_call("arrhenius", body), AN.kinetics_call("eyring", body)
            self.assertAlmostEqual(arr["Ea_kJ"], typed["arrhenius"]["Ea_kJ"], places=6)
            self.assertAlmostEqual(arr["A"] / typed["arrhenius"]["A"], 1.0, places=6)
            self.assertAlmostEqual(ey["dH_kJ"], typed["eyring"]["dH_kJ"], places=6)
            self.assertAlmostEqual(ey["dS_J"], typed["eyring"]["dS_J"], places=5)
            self.assertEqual((arr["dataset"]["id"], arr["dataset"]["version"], arr["dataset"]["mode"]), (sid, 1, "live"))

            o = self.read(sid, "order", {"t": "t", "c": "c"})
            self.assertEqual((o["n"], o["data"], o["to"]), (8, "c", {"t": "s", "c": "mol/L"}))
            fit = AN.kinetics_call("order", {"t": " ".join(map(str, o["values"]["t"])), "c": " ".join(map(str, o["values"]["c"])),
                                             "data": o["data"], "dataset": o["origin"]})
            self.assertEqual(fit["best"], typed["order"]["best"])
            kb = next(f for f in fit["fits"] if f["order"] == 2)["k"]
            self.assertAlmostEqual(kb / K2, 1.0, places=8)
            self.assertEqual(fit["unit_k"], "L mol⁻¹ s⁻¹")                                  # aus t in s, c in mol/L

    def test_conversion_series_and_x(self):
        ds = DS.from_columns("Umsatz", [{"key": "t", "name": "t", "unit": "h", "values": [0, 1, 2, 4]},
                                        {"key": "X", "name": "Umsatz", "unit": "%", "values": [0, 10, 19, 34.39]}])
        sid = self.publish(ds)["id"]
        r = self.read(sid, "order", {"t": "t", "c": "X"})
        self.assertEqual(r["data"], "X")
        self.assertEqual(r["values"]["t"], [0.0, 3600.0, 7200.0, 14400.0])
        self.assertAlmostEqual(r["values"]["c"][3], 0.3439, places=12)                      # % → Anteil
        self.assertEqual(DSET._k_target(-1.0), ("(mol/L)^-1/s", "L mol⁻¹ s⁻¹"))
        self.assertEqual(DSET._k_target(1.0)[1], "mol L⁻¹ s⁻¹")
        self.assertEqual(DSET._k_target(-2.0)[1], "L² mol⁻² s⁻¹")
        k2 = DS.from_columns("k2", [{"key": "T", "name": "T", "unit": "K", "values": [300, 310, 320]},
                                    {"key": "k", "name": "k", "unit": "L/(mol*min)", "values": [6.0, 12.0, 24.0]}])
        r = self.read(self.publish(k2)["id"], "eyring", {"T": "T", "k": "k"})
        self.assertEqual(r["unit_k"], "L mol⁻¹ s⁻¹")
        self.assertEqual(r["values"]["k"], [0.1, 0.2, 0.4])


class Refused(Base):
    def test_unit_mismatch_refused_with_message(self):
        sid = self.publish(series(True, bad_T_unit="mm"))["id"]
        with self.assertRaises(ValueError) as cm:
            self.read(sid, "arrhenius", {"T": "T", "k": "k"})
        self.assertIn("lässt sich nicht in K umrechnen", str(cm.exception))
        self.assertIn("Temperatur", str(cm.exception))
        km = DS.from_columns("k in mm", [{"key": "T", "name": "T", "unit": "°C", "values": [20, 30, 40]},
                                         {"key": "k", "name": "k", "unit": "mm", "values": [1, 2, 4]}])
        with self.assertRaises(ValueError) as cm:                                          # k in mm
            self.read(self.publish(km)["id"], "arrhenius", {"T": "T", "k": "k"})
        self.assertIn("keine Geschwindigkeitskonstante", str(cm.exception))
        with self.assertRaises(ValueError) as cm:                                          # Konzentration als Umsatz
            self.read(sid, "order", {"t": "t", "c": "c"}, data="X")
        self.assertIn("nicht dimensionslos", str(cm.exception))
        with self.assertRaises(ValueError) as cm:                                          # Textspalte
            self.read(sid, "order", {"t": "t", "c": "note"})
        self.assertIn("Text", str(cm.exception))
        with self.assertRaises(ValueError):                                                # Spalte fehlt
            self.read(sid, "order", {"t": "t", "c": "nope"})
        with self.assertRaises(ValueError):
            self.read(sid, "unbekannt", {})

    def test_not_addressed_and_missing(self):
        sid = self.publish(series(True), recipients=("rechner",))["id"]
        self.assertEqual([d["id"] for d in DSET.route(self.envs, {"list": True})["datasets"]], [sid])   # I-01: lesbar
        self.assertEqual(self.read(sid, "arrhenius", {"T": "T", "k": "k"})["n"], 6)
        with self.assertRaises(EnvError):
            self.read("s-00000000", "arrhenius", {"T": "T", "k": "k"})

    def test_http_route_refuses_with_german_message(self):
        sid = self.publish(series(True, bad_T_unit="mm"))["id"]
        old, SV.STATE = SV.STATE, types.SimpleNamespace(envs=self.envs)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), SV.Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            def post(body):
                req = urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}/api/dataset",
                                             data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
                try:
                    with urllib.request.urlopen(req) as r:
                        return r.status, json.loads(r.read())
                except urllib.error.HTTPError as e:
                    return e.code, json.loads(e.read())
            code, out = post({"list": True})
            self.assertEqual((code, len(out["datasets"])), (200, 1))
            code, out = post({"id": sid, "tool": "arrhenius", "cols": {"T": "T", "k": "k"}})
            self.assertEqual(code, 400)
            self.assertIn("lässt sich nicht in K umrechnen", out["error"])
            code, out = post({"id": sid, "tool": "order", "cols": {"t": "t", "c": "c"}})
            self.assertEqual((code, out["n"], out["version"]), (200, 8, 1))
        finally:
            srv.shutdown()
            srv.server_close()
            SV.STATE = old


class LivePin(Base):
    def test_live_follows_pin_stays(self):
        sid = self.publish(series(True))["id"]
        ds2 = series(True)
        ds2.data["k"][0] *= 2
        self.publish(DS.Dataset(ds2.header, ds2.data), share=sid)
        live = self.read(sid, "arrhenius", {"T": "T", "k": "k"}, mode="live")
        pin = self.read(sid, "arrhenius", {"T": "T", "k": "k"}, mode="pin", version=1)
        self.assertEqual((live["version"], live["status"], live["origin"]["mode"]), (2, "current", "live"))
        self.assertEqual((pin["version"], pin["latest"], pin["status"], pin["origin"]["mode"]), (1, 2, "update", "pin"))
        self.assertAlmostEqual(live["values"]["k"][0] / pin["values"]["k"][0], 2.0, places=10)


class Isochron(Base):
    def test_rbsr_from_dataset(self):
        lam = N.LAMBDA["Rb87"][0]
        m = math.exp(lam * 500e6) - 1
        xs = [0.5, 1.0, 2.0, 4.0, 6.0]
        ys = [0.7040 + m * x + d for x, d in zip(xs, (1e-5, -2e-5, 1.5e-5, 0, -1e-5))]
        ds = DS.from_columns("Granit", [{"key": "rb", "name": "⁸⁷Rb/⁸⁶Sr", "unit": "", "values": xs + [9.0]},
                                        {"key": "sr", "name": "⁸⁷Sr/⁸⁶Sr", "unit": "1", "values": ys + [None]},
                                        {"key": "d", "name": "Tiefe", "unit": "m", "values": [1, 2, 3, 4, 5, 6]}])
        sid = self.publish(ds)["id"]
        r = self.read(sid, "rbsr", {"x": "rb", "y": "sr"})
        self.assertEqual((r["n"], r["dropped"]["missing"]), (5, 1))
        pts = "\n".join(f"{x} {y}" for x, y in zip(r["values"]["x"], r["values"]["y"]))
        got = AN.nuclear_call("dating", {"method": "rbsr", "points": pts, "dataset": r["origin"]})
        want = AN.nuclear_call("dating", {"method": "rbsr", "points": "\n".join(f"{x} {y}" for x, y in zip(xs, ys))})
        self.assertAlmostEqual(got["age_a"] / want["age_a"], 1.0, places=9)
        self.assertEqual(got["dataset"]["id"], sid)
        with self.assertRaises(ValueError) as cm:
            self.read(sid, "rbsr", {"x": "d", "y": "sr"})
        self.assertIn("nicht dimensionslos", str(cm.exception))


class Report(Base):
    def test_bundle_names_dataset_and_version(self):
        sid = self.publish(series(False))["id"]
        r = self.read(sid, "arrhenius", {"T": "T", "k": "k"}, mode="pin", version=1)
        o = self.read(sid, "order", {"t": "t", "c": "c"})
        iso = DS.from_columns("Granit", [{"key": "rb", "name": "⁸⁷Rb/⁸⁶Sr", "values": [0.5, 1, 2, 4]},
                                         {"key": "sr", "name": "⁸⁷Sr/⁸⁶Sr", "values": [0.7076, 0.7112, 0.7184, 0.7328]}])
        ir = self.read(self.publish(iso)["id"], "rbsr", {"x": "rb", "y": "sr"})
        line = lambda a: " ".join(map(str, a))  # noqa: E731
        state = {"kinetics": [
            {"kind": "arrhenius", "req": {"T": line(r["values"]["T"]), "k": line(r["values"]["k"]), "unit_k": r["unit_k"],
                                         "dataset": r["origin"]}},
            {"kind": "order", "req": {"t": line(o["values"]["t"]), "c": line(o["values"]["c"]), "data": "c", "dataset": o["origin"]}}],
            "nuclear": [{"kind": "dating", "req": {"method": "rbsr", "points": "\n".join(f"{x} {y}" for x, y in zip(
                ir["values"]["x"], ir["values"]["y"])), "dataset": ir["origin"]}}]}
        for lang, ver, pin in (("de", "Version 1", "gepinnt"), ("en", "version 1", "pinned")):
            d = B.build({"state": state}, lang)
            tex = {k: base64.b64decode(v).decode("utf-8") for k, v in d["files"].items() if k.endswith(".tex")}
            kin, nuc = tex["text-kinetik.tex"], tex["text-kernchemie.tex"]
            kin.encode("latin-1")
            nuc.encode("latin-1")
            self.assertEqual(kin.count(sid), 2)
            self.assertIn(f"{sid}, {ver}, {pin})", kin)                                    # Arrhenius gepinnt
            self.assertIn(f"{sid}, {ver}, live)", kin)                                     # Ordnung live
            self.assertIn(r"\textdegree{}C", kin)                                           # Spalteneinheit genannt
            self.assertIn(ir["id"], nuc)
            for bad in (r"\text{", r"\ce{", r"\tfrac", r"\boldsymbol", "$$"):
                self.assertNotIn(bad, kin + nuc)
        self.assertIsNone(DSET.clean_origin({"title": "ohne id"}))
        c = DSET.clean_origin({"id": "s-1", "version": "x", "mode": "?", "cols": {"T": "T" * 500}, "n": -5})
        self.assertEqual((c["version"], c["mode"], len(c["cols"]["T"]), c["n"]), (0, "live", 80, 0))


if __name__ == "__main__":
    unittest.main()
