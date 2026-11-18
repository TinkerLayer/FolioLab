"""Tests des TGA-Moduls. Alle Messdaten sind synthetisch (tga/synth.py) mit bekannten Sollwerten.

    python -m unittest discover -s tests      (im Ordner modules/tga)
"""
from __future__ import annotations

import io
import json
import sys
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "sdk" / "python"))

from tga import composition as CO  # noqa: E402
from tga import deconv as DC  # noqa: E402
from tga import kinetics as KI  # noqa: E402
from tga import library as LB  # noqa: E402
from tga import process as PR  # noqa: E402
from tga import readers as RD  # noqa: E402
from tga import search as SR  # noqa: E402
from tga import steps as ST  # noqa: E402
from tga import synth as SY  # noqa: E402
from tga.analysis import run as analyse  # noqa: E402


def oxalate_arrays(step=4):
    t, T, m = SY.oxalate()
    return t[::step], T[::step], m[::step]


def bundle_values(b):
    return {v["key"] for it in b["items"] if it["kind"] == "values" for v in it["values"]}


def bundle_file(b, name):
    import base64
    return base64.b64decode(b["files"].get(name, "")).decode("utf-8")


def bundle_kinds(b, kind):
    return [it for it in b["items"] if it["kind"] == kind]


def oxalate_run():
    data, name = SY.make("oxalat")[0]
    return RD.load_bytes(data, name)[0]


class ReaderTest(unittest.TestCase):
    """Ein synthetischer Lauf in den dokumentierten Exportformaten; jedes muss dieselben Werte ergeben."""

    @classmethod
    def setUpClass(cls):
        cls.t, cls.T, cls.m = oxalate_arrays()
        cls.pct = 100 * cls.m / 10.0

    def check(self, run, unit="mg", fmt=None, tcol=True):
        self.assertEqual(len(run.T), len(self.T))
        np.testing.assert_allclose(run.T, self.T, atol=0.01)
        if unit == "mg":
            np.testing.assert_allclose(run.mg(), self.m, atol=1e-3)
        np.testing.assert_allclose(run.pct(), self.pct, atol=0.02)
        if tcol:
            np.testing.assert_allclose(run.time(), self.t, atol=1e-3)
        if fmt:
            self.assertEqual(run.meta["format"], fmt)

    def rows(self, fmt, cols="tTm", scale_t=1.0, mass="mg"):
        out = []
        for a, b, c in zip(self.t, self.T, self.m):
            v = {"t": a * scale_t, "T": b, "m": c if mass == "mg" else 100 * c / 10.0}
            out.append(fmt.format(*[v[k] for k in cols]))
        return out

    def test_generic_csv_with_header_metadata(self):
        run = RD.load_bytes(SY.make("oxalat")[0][0], "x.csv")[0]
        self.assertEqual(run.meta["format"], "Text/CSV")
        self.assertAlmostEqual(run.m0, 10.0)
        self.assertEqual(run.meta.get("rate"), 10.0)
        self.assertEqual(run.meta.get("gas"), "N₂")
        self.assertIn("Al", run.meta.get("crucible", ""))

    def test_decimal_comma_semicolon(self):
        txt = "Probe: Oxalat\nEinwaage: 10,000 mg\nZeit [min];Temperatur [°C];Masse [mg]\n" + "\n".join(
            r.replace(".", ",") for r in self.rows("{:.4f};{:.3f};{:.5f}")) + "\n"
        self.check(RD.load_bytes(txt.encode("cp1252"), "komma.txt")[0])

    def test_netzsch_ascii(self):
        head = ["#EXPORTTYPE:\tDATA ALL", "#INSTRUMENT:\tNETZSCH TG 209F1 Libra", "#SAMPLE:\tOxalat",
                "#SAMPLE MASS /mg:\t10.000", "#ATMOSPHERE:\tN2", "#RANGE:\t30°C/10.0(K/min)/1000°C",
                "##Temp./°C;Time/min;Mass/%"]
        txt = "\n".join(head + self.rows("{:.3f};{:.4f};{:.4f}", "Ttm", mass="%")) + "\n"
        run = RD.load_bytes(txt.encode("latin-1"), "netzsch.txt")[0]
        self.check(run, unit="%", fmt="NETZSCH Proteus ASCII")
        self.assertAlmostEqual(run.m0, 10.0)
        self.assertEqual(run.meta.get("rate"), 10.0)

    def test_ta_universal_analysis(self):
        head = ["OrgFile\tC:\\TA\\Data\\TGA\\oxalat.001", "Instrument\tTGA Q500 V20.13", "Sample\tOxalat", "Size\t10.0000 mg",
                "Sig1\tTime (min)", "Sig2\tTemperature (°C)", "Sig3\tWeight (mg)", "StartOfData"]
        txt = "\n".join(head + self.rows("{:.4f}\t{:.3f}\t{:.5f}")) + "\n"
        self.check(RD.load_bytes(txt.encode("utf-16"), "ta.txt")[0], fmt="TA Universal Analysis")

    def test_mettler_stare(self):
        head = ["Oxalat 10 K/min", "Index\tt\tTs\tTr\tValue", "\t[s]\t[°C]\t[°C]\t[mg]"]
        body = [f"{i}\t{a * 60:.2f}\t{b:.3f}\t{b + 0.5:.3f}\t{c:.5f}" for i, (a, b, c) in enumerate(zip(self.t, self.T, self.m))]
        self.check(RD.load_bytes("\n".join(head + body).encode("utf-8"), "stare.txt")[0], fmt="METTLER STARe")

    def test_perkinelmer_pyris(self):
        head = ["Sample ID: Oxalat", "Sample Weight: 10.000 mg",
                "Time (min)\tUnsubtracted Weight (mg)\tBaseline Weight (mg)\tProgram Temp. (°C)\tSample Temp. (°C)"]
        body = [f"{a:.4f}\t{c:.5f}\t0\t{b + 0.7:.3f}\t{b:.3f}" for a, b, c in zip(self.t, self.T, self.m)]
        self.check(RD.load_bytes("\n".join(head + body).encode("utf-8"), "pyris.txt")[0], fmt="PerkinElmer Pyris")

    def test_shimadzu(self):
        head = ["[File Information]", "Sample Name\tOxalat", "Sample Weight\t10.000[mg]", "[Data]", "Time\tTemp\tTGA",
                "[min]\t[C]\t[mg]"]
        txt = "\n".join(head + self.rows("{:.4f}\t{:.3f}\t{:.5f}")) + "\n"
        self.check(RD.load_bytes(txt.encode("shift_jis"), "shimadzu.txt")[0], fmt="Shimadzu ASCII")

    def test_kelvin_and_seconds_converted(self):
        txt = "time [s];T [K];mass [mg]\n" + "\n".join(
            f"{a * 60:.3f};{b + 273.15:.3f};{c:.5f}" for a, b, c in zip(self.t, self.T, self.m)) + "\n"
        self.check(RD.load_bytes(txt.encode(), "kelvin.csv")[0])

    def test_mapping_dialog_overrides_guess(self):
        txt = "a;b;c\n" + "\n".join(self.rows("{:.3f};{:.4f};{:.5f}", "Ttm")) + "\n"
        run = RD.load_bytes(txt.encode(), "unbekannt.csv", {"t": 1, "T": 0, "m": 2, "m_unit": "mg"})[0]
        self.check(run)

    def test_xlsx(self):
        try:
            import openpyxl
        except ImportError:
            self.skipTest("openpyxl fehlt")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Time (min)", "Temperature (°C)", "Weight (mg)"])
        for a, b, c in zip(self.t, self.T, self.m):
            ws.append([float(a), float(b), float(c)])
        buf = io.BytesIO()
        wb.save(buf)
        self.check(RD.load_bytes(buf.getvalue(), "trios.xlsx")[0])

    def test_binary_native_rejected_with_hint(self):
        with self.assertRaises(RD.ReadError) as cm:
            RD.load_bytes(b"\x00\x01PK\x03\x04" + bytes(200), "lauf.tri")
        self.assertIn("export", str(cm.exception).lower())

    @unittest.skipIf(RD.ngb_available(), "pyngb installiert: Hinweistext entfällt")
    def test_ngb_without_package_hint(self):
        with self.assertRaises(RD.ReadError) as cm:
            RD.load_bytes(b"PK\x03\x04" + bytes(200), "lauf.ngb-ss3")
        self.assertIn("pyngb", str(cm.exception))

    def test_ngb_mapping_with_fake_pyngb(self):
        """TGA-02: Abbildung der pyngb-Spalten (Zeit s, Temperatur °C, Masse mg) auf einen Lauf – ohne das Paket,
        mit einem Ersatzmodul, das die von pyngb dokumentierte Rückgabe (Metadaten, Tabelle) nachbildet."""
        import types
        r = oxalate_run()

        class Col:
            def __init__(self, a):
                self.a = a

            def to_numpy(self, zero_copy_only=False):
                return self.a

        class Table:
            column_names = ["time", "sample_temperature", "mass", "dsc_signal", "purge_flow_1"]

            def __init__(self):
                n = len(r.m)
                self.d = {"time": r.time() * 60.0, "sample_temperature": r.T, "mass": r.mg(),
                          "dsc_signal": np.zeros(n), "purge_flow_1": np.full(n, 50.0)}

            def column(self, k):
                return Col(self.d[k])

        fake = types.ModuleType("pyngb")
        fake.read_ngb = lambda path, return_metadata=False: (
            {"sample_mass": r.m0, "sample_name": "CaOx synthetisch", "instrument": "STA 449 F3"}, Table())
        old = sys.modules.get("pyngb")
        sys.modules["pyngb"] = fake
        try:
            run = RD.load_bytes(b"PK\x03\x04" + bytes(64), "lauf.ngb-ss3")[0]
        finally:
            if old is None:
                sys.modules.pop("pyngb", None)
            else:
                sys.modules["pyngb"] = old
        self.assertEqual(run.meta["format"], "NETZSCH NGB (pyngb)")
        self.assertEqual(run.name, "CaOx synthetisch")
        self.assertEqual(run.unit, "mg")
        self.assertAlmostEqual(run.m0, r.m0)
        np.testing.assert_allclose(run.t, r.time(), rtol=1e-9)              # s -> min
        np.testing.assert_allclose(run.T, r.T)
        self.assertIn("hf", run.extra)
        self.assertIn("flow", run.extra)

    @unittest.skipUnless(RD.ngb_available(), "pyngb nicht installiert (optional)")
    def test_ngb_real_package_present(self):
        import pyngb
        self.assertTrue(hasattr(pyngb, "read_ngb"))

    @unittest.skipUnless(RD.ngb_available(), "pyngb nicht installiert (optional)")
    def test_ngb_real_pyarrow_table_units_and_ds3(self):
        """Mit dem echten pyngb: pyarrow-Tabelle mit Einheiten aus pyngb.set_column_units; nur das Lesen der Datei
        (read_ngb) wird ersetzt, da keine echte .ngb-Datei vorliegt. .ngb-ds3 wird korrigiert angefordert."""
        import pyarrow as pa
        import pyngb
        r = oxalate_run()
        tab = pa.table({"time": r.time() * 60.0, "sample_temperature": r.T, "mass": r.mg(),
                        "dtg": np.gradient(r.mg(), r.time())})
        for c, u in (("time", "s"), ("sample_temperature", "°C"), ("mass", "mg"), ("dtg", "mg/min")):
            tab = pyngb.set_column_units(tab, c, u)
        calls = []

        def fake_read(path, return_metadata=False, run="sample", **kw):
            calls.append((Path(path).suffix, run))
            return ({"sample_mass": r.m0, "sample_name": "CaOx"}, tab)
        old = pyngb.read_ngb
        pyngb.read_ngb = fake_read
        try:
            a = RD.load_bytes(b"PK\x03\x04" + bytes(64), "lauf.ngb-ss3")[0]
            b = RD.load_bytes(b"PK\x03\x04" + bytes(64), "lauf.ngb-ds3")[0]
        finally:
            pyngb.read_ngb = old
        self.assertEqual(calls, [(".ngb-ss3", "sample"), (".ngb-ds3", "corrected")])
        self.assertEqual(RD._ngb_units(tab)["dtg"], "mg/min")
        np.testing.assert_allclose(a.t, r.time(), rtol=1e-9)
        self.assertAlmostEqual(a.m0, r.m0)
        self.assertNotIn("ngb_run", a.meta)
        self.assertIn("korrigiert", b.meta["ngb_run"])

    def test_csv_roundtrip(self):
        r = oxalate_run()
        r2 = RD.load_bytes(RD.to_csv(r).encode("utf-8"), "rt.csv")[0]
        np.testing.assert_allclose(r2.pct(), r.pct(), atol=1e-3)


class StepTest(unittest.TestCase):
    def test_oxalate_three_steps_match_stoichiometry(self):
        a = ST.analyse(oxalate_run())
        self.assertEqual(len(a["steps"]), 3)
        for s, th in zip(a["steps"], (12.33, 19.17, 30.12)):
            self.assertAlmostEqual(s["loss"], th, delta=0.5)
            self.assertLess(s["T_onset"], s["T_peak"])
            self.assertLess(s["T_peak"], s["T_endset"])
        self.assertTrue(CO.check_oxalate(a["steps"])["ok"])
        self.assertAlmostEqual(a["residue"]["end"], 100 - 12.33 - 19.17 - 30.12, delta=1.0)

    def test_loss_temperatures_increase(self):
        lt = ST.analyse(oxalate_run())["loss_T"]
        Ts = [lt[k]["T"] for k in ("1", "2", "5", "10", "50")]
        self.assertEqual(Ts, sorted(Ts))

    def test_manual_limits(self):
        a = ST.analyse(oxalate_run(), manual=[{"lo": 300, "hi": 560}])
        self.assertEqual(len(a["steps"]), 1)
        self.assertAlmostEqual(a["steps"][0]["loss"], 19.17, delta=0.6)

    def test_reaction_content_from_loss(self):
        self.assertAlmostEqual(CO.content_from_loss(43.97 / 2, "caco3")["content"], 50.0, delta=0.05)
        self.assertAlmostEqual(CO.formula_mass("CaCO3"), 100.086, delta=0.01)

    def test_e1131_composition(self):
        data, name = SY.make("elastomer")[0]
        r = RD.load_bytes(data, name)[0]
        c = CO.compose(r, "e1131")
        got = {row["name"]: row["pct"] for row in c["rows"]}
        self.assertEqual(len(c["rows"]), 4)
        self.assertAlmostEqual(sum(got.values()), 100.0, delta=0.5)
        vals = list(got.values())
        self.assertAlmostEqual(vals[2], 30.0, delta=1.5)      # Russ: Verlust nach dem Gaswechsel

    def test_segments_and_gas_switch(self):
        data, name = SY.make("elastomer")[0]
        r = RD.load_bytes(data, name)[0]
        segs = PR.segments(r)
        self.assertGreaterEqual(len(segs), 2)
        self.assertIsNotNone(PR.gas_switch(r))

    def test_pipeline_ops(self):
        r = oxalate_run()
        p = PR.apply(r, [{"op": "ref_mass", "mode": "at_T", "T": 120}, {"op": "cut", "axis": "T", "lo": 50, "hi": 900},
                         {"op": "tcal", "a": 1.0, "b": 1.0}, {"op": "smooth", "kind": "sg", "width": 9}])
        self.assertEqual(len(p.steps), 4)
        self.assertGreaterEqual(p.run.T.min(), 50)
        self.assertAlmostEqual(float(p.run.pct()[np.argmin(abs(p.run.T - 121))]), 100.0, delta=0.2)


class LibraryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib = LB.model_library()

    def test_every_model_entry_is_sourced(self):
        self.assertGreater(len(self.lib.entries), 50)
        for e in self.lib.entries:
            self.assertTrue(e["source"].get("title") or e["source"].get("authors"), e["name"])
            self.assertTrue(self.lib.ref_of(e).get("modelled"))
            self.assertLessEqual(sum(s["loss"] for s in e["steps"]), 101)

    def test_model_curves_have_the_published_losses(self):
        e = next(x for x in self.lib.entries if x["id"].startswith("calciumoxalat"))
        tg = self.lib.tg(e)
        self.assertAlmostEqual(100 - tg[-1], sum(s["loss"] for s in e["steps"]), delta=0.6)

    def test_search_ranks_oxalate_first(self):
        a = analyse(oxalate_run(), {})
        Q = SR.query(a.run, a.steps, a.st["residue"]["end"])
        res = SR.search(Q, [self.lib])
        self.assertIn("Calciumoxalat", res["hits"][0]["name"])
        self.assertGreater(res["hits"][0]["hqi"], 80)
        self.assertTrue(res["hits"][0]["modelled"])

    def test_own_library_measured_curve_wins(self):
        with TemporaryDirectory() as d:
            libs = LB.Libraries(Path(d))
            own = libs.own()
            r = oxalate_run()
            own.add_curve(r.T, r.pct(), {"name": "Mein Oxalat", "source": {"type": "misc", "title": "Eigene Messung", "year": "2026"}})
            own.save()
            a = analyse(r, {})
            Q = SR.query(a.run, a.steps, a.st["residue"]["end"])
            res = SR.search(Q, [libs.get(own.id)])
            self.assertEqual(res["hits"][0]["name"], "Mein Oxalat")
            self.assertGreater(res["hits"][0]["hqi"], 95)
            # Neu laden, exportieren, importieren
            libs2 = LB.Libraries(Path(d))
            lib = libs2.get(own.id)
            self.assertEqual(len(lib.entries), 1)
            ex = lib.export()
            n = libs2.create("Kopie", "", None).import_(ex)
            self.assertEqual(n, 1)

    def test_step_table_reference(self):
        with TemporaryDirectory() as d:
            own = LB.Libraries(Path(d)).own()
            e = own.add_steps({"name": "PVC aus Paper", "atmosphere": "N₂", "steps": [{"T_peak": 300, "loss": 58}, {"T_peak": 460, "loss": 30}],
                               "residue": 12, "source": {"type": "article", "authors": "Muster, A.", "title": "PVC", "year": "2020"}})
            self.assertEqual(len(e["steps"]), 2)
            self.assertAlmostEqual(float(100 - own.tg(own.entries[0])[-1]), 88.0, delta=0.5)

    def test_mixture_recovers_two_components(self):
        lib = self.lib
        ia = next(i for i, e in enumerate(lib.entries) if e["id"].startswith("pe-hd"))
        ib = next(i for i, e in enumerate(lib.entries) if e["id"].startswith("calciumcarbonat"))
        q = 0.7 * np.nan_to_num(lib.G[ia]) + 0.3 * np.nan_to_num(lib.G[ib])
        res = SR.mixture({"dtg": q, "steps": [], "residue": None, "atm": ""}, [lib], 2)
        best = res["combos"][0]
        fr = {c["id"]: c["frac"] for c in best["components"]}
        self.assertEqual(len(fr), 2, fr)
        self.assertAlmostEqual(sum(fr.values()), 1.0, delta=0.1)


class KineticsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runs = [RD.load_bytes(d, n)[0] for d, n in SY.make("kinetik")]
        cls.res = KI.run_all(cls.runs, 300, 600)

    def test_isoconversional_recovers_ea(self):
        for m in ("friedman", "ofw", "kas", "starink", "vyazovkin"):
            self.assertAlmostEqual(self.res["iso"]["summary"][m]["mean"], 180.0, delta=6.0, msg=m)

    def test_kissinger_and_model(self):
        self.assertAlmostEqual(self.res["kissinger"]["E"], 180.0, delta=6.0)
        self.assertEqual(self.res["model"], "F1")
        best = min(self.res["coats_redfern"]["models"], key=lambda x: -x["r2"])
        self.assertEqual(best["model"], "F1")

    def test_too_few_rates(self):
        with self.assertRaises((KI.KinError, ValueError)):
            KI.run_all(self.runs[:2], 300, 600)


class DeconvTest(unittest.TestCase):
    def test_three_overlapping_peaks(self):
        x = np.arange(200, 500, 1.0)
        truth = [(300, 30, 25, 30), (350, 40, 15, 20), (380, 20, 60, 70)]
        y = sum(LB.fs_peak(x, p, a, hl, hr) for p, a, hl, hr in truth)
        res = DC.fit(x, y, [{"x0": 295, "area": 25, "hwl": 20, "hwr": 20}, {"x0": 355, "area": 35, "hwl": 20, "hwr": 20},
                            {"x0": 390, "area": 25, "hwl": 50, "hwr": 50}])
        self.assertGreater(res["r2"], 0.999)
        got = sorted((p["x0"], p["area"]) for p in res["peaks"])
        for (p, a, _, _), (gp, ga) in zip(truth, got):
            self.assertAlmostEqual(gp, p, delta=2)
            self.assertAlmostEqual(ga, a, delta=1.5)


class AnalysisTest(unittest.TestCase):
    def test_own_equations_use_measured_values(self):
        a = analyse(oxalate_run(), {"equations": [
            {"sym": "Lw", "label": "Kristallwasser", "expr": "L1", "unit": "%"},
            {"sym": "n", "label": "Wasser je Formeleinheit", "expr": "Lw/100*146.11/18.015"},
            {"sym": "d", "label": "Massenabnahme 150-250", "expr": "loss(150, 250)", "unit": "%"}]})
        ev = {e["sym"]: e for e in a.equations}
        self.assertAlmostEqual(ev["n"]["value"], 1.0, delta=0.05)
        self.assertGreater(ev["d"]["value"], 10)

    def test_equation_error_is_reported_not_raised(self):
        a = analyse(oxalate_run(), {"equations": [{"sym": "x", "expr": "L9 * 2"}]})
        self.assertTrue(a.equations[0].get("error"))


class BundleTest(unittest.TestCase):
    def test_single_and_comparison_bundle(self):
        from tga import bundle as B
        raw, name = SY.make("oxalat")[0]
        st = {"calib": True, "reactions": [{"step": 1, "key": "oxalat1"}],
              "equations": [{"sym": "n", "label": "n(H2O)", "expr": "L1/100*146.11/18.015",
                             "source": {"type": "book", "authors": "Brown, M.E.", "title": "Introduction to Thermal Analysis", "year": "2001"}}]}
        b = B.build([(raw, name, None, st)], {"items": [{"name": name}]}, lang="de")
        self.assertEqual(b["format"], "folio-lab-bundle/1")
        keys = bundle_values(b)
        self.assertTrue({"step1-loss", "step1-onset", "residue", "t5"} <= keys, keys)
        bib = bundle_file(b, "refs.bib")
        self.assertIn("11358", bib)
        self.assertIn("Brown", bib)
        self.assertTrue(bundle_kinds(b, "figure"))
        # Vergleich zweier Läufe
        b2 = B.build([(raw, name, None, {}), (raw, "b.csv", None, {})], {"items": [{"name": name}, {"name": "b.csv"}]}, lang="en")
        self.assertGreaterEqual(len(bundle_kinds(b2, "figure")), 2)

    def test_overlaid_own_reference_is_drawn_and_cited(self):
        from tga import bundle as B
        raw, name = SY.make("oxalat")[0]
        lib = LB.model_library()
        e = lib.entries[0]
        ov = {"name": "Eigene Ref", "lib": "eigene", "lib_name": "Eigene Referenzen", "modelled": False,
              "source": {"type": "article", "authors": "Muster, A.; Beispiel, B.", "title": "TGA von Oxalat", "container": "J. Test",
                         "year": "2024", "doi": "10.1234/abcd.5678"},
              "tg": lib.tg(e).tolist(), "dtg": lib.dtg(e).tolist()}
        b = B.build([(raw, name, None, {"overlays": [ov]})], {"items": [{"name": name}]}, lang="de")
        bib = bundle_file(b, "refs.bib")
        self.assertIn("10.1234/abcd.5678", bib)
        fig = next(it for it in b["items"] if it["kind"] == "figure" and it["id"].startswith("tg"))
        self.assertIn("Eigene Ref", fig["caption"])

    def test_search_hits_cited(self):
        from tga import bundle as B
        raw, name = SY.make("oxalat")[0]
        r = RD.load_bytes(raw, name)[0]
        a = analyse(r, {})
        res = SR.search(SR.query(a.run, a.steps, a.st["residue"]["end"]), [LB.model_library()], n=5)
        st = {"search": {"hits": json.loads(json.dumps(res["hits"], default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))}}
        b = B.build([(raw, name, None, st)], {"items": [{"name": name}]}, lang="de")
        txt = bundle_file(b, "refs.bib") + json.dumps(b["items"], ensure_ascii=False)
        self.assertIn("modell", txt.lower())
        self.assertIn("hit1", bundle_values(b))


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tga import server as S
        cls.S = S
        cls.tmp = TemporaryDirectory()
        S.STATE = S.State(Path(cls.tmp.name))
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.tmp.cleanup()

    def post(self, path, obj=None, raw=None, origin=None):
        data = raw if raw is not None else json.dumps(obj or {}).encode()
        req = urllib.request.Request(self.base + path, data=data, method="POST",
                                     headers={"Content-Type": "application/json", "X-Folio": "1", **({"Origin": origin} if origin else {})})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=30) as r:
            return r.read()

    def test_share_steps(self):
        """A3: Stufentabelle teilen – neue Version bei erneutem Teilen, keine Kurve im Umschlag."""
        code, r = self.post("/api/sample", {"which": "oxalat"})
        iid = r["runs"][0]["id"]
        code, e1 = self.post("/api/share/steps", {"id": iid, "state": {}})
        self.assertEqual(code, 200, e1)
        self.assertEqual((e1["schema"], e1["version"], e1["kind"]), ("suite.shared-result/1", 1, "tga.steps"))
        keys = [o["key"] for o in e1["outputs"]]
        self.assertEqual(keys[:3], ["step1-loss", "step2-loss", "step3-loss"])
        self.assertAlmostEqual(e1["outputs"][0]["quantity"]["value"], 12.33, delta=0.6)
        self.assertIn("T_peak", e1["outputs"][0]["conditions"])
        self.assertTrue(all(isinstance(o["quantity"]["value"], float) for o in e1["outputs"]))
        code, e2 = self.post("/api/share/steps", {"id": iid, "state": {}})
        self.assertEqual((e2["id"], e2["version"]), (e1["id"], 2))

    def test_flow(self):
        meta = json.loads(self.get("/api/meta"))
        self.assertIn("modell", [x["id"] for x in meta["libs"]])
        self.assertIn(b"<html", self.get("/").lower()[:200])
        self.assertIn(b"LabRef", self.get("/labref.js"))
        code, r = self.post("/api/sample", {"which": "oxalat"})
        self.assertEqual(code, 200)
        iid = r["runs"][0]["id"]
        code, p = self.post("/api/run", {"id": iid, "state": {"calib": True}})
        self.assertEqual(code, 200)
        self.assertEqual(len(p["steps"]), 3)
        self.assertTrue(p["calib"]["ok"])
        code, s = self.post("/api/search", {"id": iid, "state": {}})
        self.assertIn("Calciumoxalat", s["hits"][0]["name"])
        # eigene Referenz aus dem Lauf, dann Suche in „Eigene Referenzen“
        code, e = self.post("/api/library/add_run", {"id": iid, "meta": {"name": "Ref-Oxalat",
                                                                          "source": {"type": "misc", "title": "Messung Labor", "year": "2026"}}})
        self.assertEqual(code, 200, e)
        own = e["lib"]["id"]
        code, s = self.post("/api/search", {"id": iid, "state": {}, "libs": [own, "modell"]})
        self.assertEqual(s["hits"][0]["name"], "Ref-Oxalat")
        self.assertFalse(s["hits"][0]["modelled"])
        # eigene Gleichung speichern
        code, q = self.post("/api/equations/save", {"item": {"sym": "n", "label": "Wasser", "expr": "L1/100*146.11/18.015"}})
        self.assertEqual(code, 200, q)
        self.assertEqual(len(q["items"]), 1)
        code, q = self.post("/api/equations/save", {"item": {"sym": "1x", "expr": "2"}})
        self.assertEqual(code, 400)
        # Bericht
        code, b = self.post("/api/bundle", {"items": [{"id": iid, "state": {"calib": True}}]})
        self.assertEqual(code, 200, b)
        self.assertEqual(b["format"], "folio-lab-bundle/1")
        code, b2 = self.post("/api/bundle/rebuild", {"source": b["source"], "lang": "en"})
        self.assertEqual(code, 200, b2)
        self.assertEqual(b2["lang"], "en")
        # Fremde Herkunft
        code, _ = self.post("/api/remove", {"id": iid}, origin="http://evil.example")
        self.assertEqual(code, 403)

    def test_kinetics_endpoint(self):
        code, r = self.post("/api/sample", {"which": "kinetik"})
        ids = [x["id"] for x in r["runs"]]
        code, k = self.post("/api/kinetics", {"ids": ids, "T_lo": 300, "T_hi": 600})
        self.assertEqual(code, 200, k)
        self.assertAlmostEqual(k["iso"]["summary"]["friedman"]["mean"], 180, delta=6)
        code, k = self.post("/api/kinetics", {"ids": ids[:2], "T_lo": 300, "T_hi": 600})
        self.assertEqual(code, 400)

    def test_bad_file(self):
        code, r = self.post("/api/load?name=leer.csv", raw=b"nur text\nohne zahlen\n")
        self.assertEqual(code, 400)
        self.assertIn("error", r)


if __name__ == "__main__":
    unittest.main()
