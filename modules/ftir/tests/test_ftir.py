"""FTIR-Modul: Dateien, Bearbeitung, Banden, Gruppen, Suche, Mischung, Bibliotheken, Bericht, Server.

Start:  python -m unittest discover -s tests   (im Ordner modules/ftir)
"""
import base64
import json
import struct
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "sdk" / "python"))

from ftir import bundle, groups, peaks, process, quality, refdata, samples, search  # noqa: E402
from ftir import library as LB  # noqa: E402
from ftir.analysis import run  # noqa: E402
from ftir.readers import ReadError, Spectrum, load_bytes, to_csv, to_jcamp  # noqa: E402
from laboptional import available, skip_unless  # noqa: E402

X = np.arange(600.0, 4000.0 + 1e-9, 1.0)
MATS = {m[0]: m for m in refdata.MATERIALS}


def model(mid, x=X, shift=1.0, widen=1.1):
    return refdata.band_model([(c + shift, h, w * widen) for c, h, w in MATS[mid][4]], x)


def pet_abs(noise=0.003, seed=1):
    rng = np.random.default_rng(seed)
    return model("pet") * (1000 / X) ** 0.6 + 0.05 + 0.04 * (X / 4000) ** 2 + rng.normal(0, noise, len(X))


# ----------------------------------------------------------------------------- Testdateien
SQZ_POS, SQZ_NEG = "@ABCDEFGHI", "@abcdefghi"
DIF_POS, DIF_NEG = "%JKLMNOPQR", "%jklmnopqr"
DUP = "STUVWXYZs"


def _sqz(v):
    s = str(abs(v))
    return (SQZ_NEG if v < 0 else SQZ_POS)[int(s[0])] + s[1:]


def _dif(v):
    s = str(abs(v))
    return (DIF_NEG if v < 0 else DIF_POS)[int(s[0])] + s[1:]


def jcamp_difdup(x0, dx, yint, yfactor, per_line=10, title="komprimiert"):
    """JCAMP-DX mit X++(Y..Y) in DIF/DUP-Form samt Y-Prüfwert am Zeilenanfang."""
    lines = [f"##TITLE={title}", "##JCAMP-DX=5.01", "##DATA TYPE=INFRARED SPECTRUM", "##XUNITS=1/CM",
             "##YUNITS=ABSORBANCE", "##XFACTOR=1", f"##YFACTOR={yfactor}", f"##FIRSTX={x0}",
             f"##LASTX={x0 + dx * (len(yint) - 1)}", f"##DELTAX={dx}", f"##NPOINTS={len(yint)}", "##XYDATA=(X++(Y..Y))"]
    i = 0
    while i < len(yint) - 1:
        start = i
        toks = [_sqz(yint[i])]
        j = i + 1
        while j < len(yint) and j - start <= per_line:
            toks.append(_dif(yint[j] - yint[j - 1]))
            j += 1
        # gleiche DIF-Zeichen hintereinander mit DUP zusammenfassen
        out, k = [], 0
        while k < len(toks):
            n = 1
            while k + n < len(toks) and k > 0 and toks[k + n] == toks[k] and n < 9:
                n += 1
            out.append(toks[k] + (DUP[n - 1] if n > 1 else ""))
            k += n
        lines.append(f"{x0 + dx * start:g}" + "".join(out))
        i = j - 1                                                     # nächste Zeile beginnt mit dem Prüfwert
    lines.append("##END=")
    return "\n".join(lines) + "\n"


def spa_bytes(x0, x1, y, ykey=17, title="OMNIC Probe"):
    n = len(y)
    buf = bytearray(1024 + 4 * n)
    t = title.encode("latin-1")
    buf[30:30 + len(t)] = t
    hdr, dat = 700, 1024
    # Verzeichnis: Eintrag 0 = Kopf (Schlüssel 2), Eintrag 1 = Daten (Schlüssel 3)
    buf[304] = 2
    struct.pack_into("<II", buf, 306, hdr, 64)
    buf[320] = 3
    struct.pack_into("<II", buf, 322, dat, 4 * n)
    struct.pack_into("<I", buf, hdr + 4, n)
    buf[hdr + 12] = ykey
    struct.pack_into("<ff", buf, hdr + 16, x0, x1)
    buf[dat:dat + 4 * n] = np.asarray(y, "<f4").tobytes()
    return bytes(buf)


def spc_bytes(x0, x1, y, ytype=2, comment="SPC Probe", ints=False):
    n = len(y)
    flags = 0
    fexp = -128
    head = bytearray(512)
    if ints:
        fexp = 0
        while np.max(np.abs(y)) * 2.0 ** (32 - fexp) >= 2 ** 31:
            fexp += 1
    struct.pack_into("<BBBbiddiBBBBi", head, 0, flags, 0x4B, 0, fexp, n, x0, x1, 1, 1, ytype, 0, 0, 0)
    c = comment.encode("latin-1")
    head[88:88 + len(c)] = c
    sub = struct.pack("<Bbhfffi", 0, 0, 0, 0.0, 0.0, 0.0, 0) + b"\0" * 12          # Unterkopf: 32 Byte
    if ints:
        data = np.round(np.asarray(y) * 2.0 ** (32 - fexp)).astype("<i4").tobytes()
    else:
        data = np.asarray(y, "<f4").tobytes()
    return bytes(head) + sub + data


# ----------------------------------------------------------------------------- Dateien
class ReaderTest(unittest.TestCase):
    def test_csv_semicolon_decimal_comma_transmission(self):
        t = 100 * 10 ** (-pet_abs())
        text = "Wellenzahl;%T\n" + "\n".join(f"{x:.1f};{v:.3f}".replace(".", ",") for x, v in zip(X[::-1], t[::-1]))
        sp = load_bytes(text.encode("utf-8"), "probe.csv")[0]
        self.assertEqual(sp.yunit, "T")
        self.assertEqual(len(sp.x), len(X))
        self.assertTrue(np.all(np.diff(sp.x) > 0), "Wellenzahl aufsteigend sortiert")
        self.assertAlmostEqual(float(sp.y[np.argmin(np.abs(sp.x - 2000))]), float(t[1400]), places=2)

    def test_csv_multiple_columns(self):
        rows = ["wn,a,b,c"] + [f"{x},{0.1 * x / 4000},{0.2},{0.3 + 0.001 * (x % 7)}" for x in X[::4]]
        sps = load_bytes("\n".join(rows).encode(), "drei.csv")
        self.assertEqual(len(sps), 3)

    def test_jcamp_roundtrip(self):
        sp = Spectrum("PET", X, pet_abs(), "A", {})
        back = load_bytes(to_jcamp(sp).encode(), "pet.jdx")[0]
        self.assertEqual(back.yunit, "A")
        np.testing.assert_allclose(back.y, sp.y, rtol=1e-5, atol=1e-6)

    def test_jcamp_compressed_difdup(self):
        y = pet_abs(noise=0)
        yint = [int(round(v * 10000)) for v in y]
        yint[100:130] = [yint[100]] * 30                                 # Plateau -> DUP mit DIF null
        text = jcamp_difdup(600, 1.0, yint, 0.0001)
        self.assertRegex(text, r"[STUVWXYZs]", "Testdatei soll DUP enthalten")
        sp = load_bytes(text.encode(), "dif.jdx")[0]
        self.assertEqual(len(sp.x), len(yint))
        np.testing.assert_allclose(sp.y, np.array(yint) * 0.0001, atol=1e-9)
        self.assertAlmostEqual(sp.x[-1], 600 + len(yint) - 1)

    def test_jcamp_multiblock_and_transmission_fraction(self):
        a = Spectrum("eins", X, pet_abs(), "A", {})
        b = Spectrum("zwei", X, 10 ** (-pet_abs(seed=2)), "T", {})
        txt = "##TITLE=Sammlung\n##JCAMP-DX=5.01\n##DATA TYPE=LINK\n##BLOCKS=2\n" + to_jcamp(a) + \
            to_jcamp(b).replace("##YUNITS=TRANSMITTANCE", "##YUNITS=TRANSMITTANCE") + "##END=\n"
        sps = load_bytes(txt.encode(), "zwei.jdx")
        self.assertEqual([s.name for s in sps], ["eins", "zwei"])
        self.assertEqual(sps[1].yunit, "T")
        self.assertGreater(float(np.max(sps[1].y)), 50, "Transmission 0..1 wird in Prozent umgerechnet")

    def test_spa(self):
        y = pet_abs()
        sp = load_bytes(spa_bytes(4000.0, 600.0, y[::-1]), "probe.spa")[0]
        self.assertEqual(sp.name, "OMNIC Probe")
        self.assertEqual(sp.yunit, "A")
        np.testing.assert_allclose(sp.y, y, atol=1e-5)
        spT = load_bytes(spa_bytes(4000.0, 600.0, 10 ** (-y[::-1]), ykey=16), "t.spa")[0]
        self.assertEqual(spT.yunit, "T")
        self.assertGreater(spT.y.max(), 50)

    def test_spc_float_and_int(self):
        y = pet_abs()
        sp = load_bytes(spc_bytes(600.0, 4000.0, y), "probe.spc")[0]
        self.assertEqual((sp.name, sp.yunit), ("SPC Probe", "A"))
        np.testing.assert_allclose(sp.y, y, atol=1e-5)
        sp2 = load_bytes(spc_bytes(600.0, 4000.0, y, ints=True), "probe2.spc")[0]
        np.testing.assert_allclose(sp2.y, y, atol=1e-6)

    def test_agilent_fir(self):
        # Agilent MicroLab: SPC mit Endung .fir, Auflösung im Kopf, SampleID und Quelldatei im Log-Block
        y = pet_abs()
        raw = bytearray(spc_bytes(650.0, 4000.0, y, comment=""))
        raw[36:42] = b"4 cm-1"
        txt = b"SampleID=dose_innen\r\nSpectrum=Exported from C:\\Users\\Public\\Documents\\Agilent\\MicroLab\\Results\\\\dose_innen.a2r\r\n\0"
        struct.pack_into("<I", raw, 248, len(raw))
        raw += struct.pack("<IIII", 64 + len(txt), 4096, 64, 0) + b"\0" * 48 + txt
        sp = load_bytes(bytes(raw), "dose_innen_2026-11-11T15-43-22.fir")[0]
        self.assertEqual(sp.name, "dose_innen_2026-11-11T15-43-22")
        self.assertEqual(sp.yunit, "A")
        np.testing.assert_allclose(sp.y, y, atol=1e-5)
        self.assertEqual(sp.meta["resolution"], "4")
        self.assertEqual(sp.meta["sample"], "dose_innen")
        self.assertEqual(sp.meta["instrument"], "Agilent MicroLab")
        self.assertTrue(sp.meta["source"].endswith("Results\\dose_innen.a2r"))

    def test_rejects_garbage(self):
        with self.assertRaises(ReadError):
            load_bytes(b"\0\1\2" * 300, "x.bin")
        with self.assertRaises(ValueError):
            load_bytes(b"a,b\n1,2\n3,4\n", "kurz.csv")

    def test_samples_load(self):
        for k in samples.SAMPLES:
            data, name = samples.make(k)
            self.assertTrue(load_bytes(data, name))


# ----------------------------------------------------------------------------- Bearbeitung
class ProcessTest(unittest.TestCase):
    def test_absorbance_transmission_roundtrip(self):
        a = pet_abs()
        sp = Spectrum("t", X, 100 * 10 ** (-a), "T")
        p = process.apply(sp, [{"op": "to_abs"}])
        self.assertEqual(p.spectrum.yunit, "A")
        np.testing.assert_allclose(p.spectrum.y, a, atol=1e-9)
        back = process.apply(p.spectrum, [{"op": "to_trans"}]).spectrum
        np.testing.assert_allclose(back.y, sp.y, rtol=1e-9)

    def test_baselines_remove_offset_and_slope(self):
        clean = model("pet")
        y = clean + 0.2 + 0.1 * (X - 600) / 3400
        sp = Spectrum("b", X, y, "A")
        for method in ("rubber", "als", "poly"):
            out = process.apply(sp, [{"op": "baseline", "method": method, "lam": 6, "p": 0.01, "deg": 2}]).spectrum.y
            far = (X > 1900) & (X < 2600)                                # bandenfrei im Modell
            self.assertLess(float(np.max(np.abs(out[far]))), 0.03, method)
            self.assertAlmostEqual(float(out[np.argmin(np.abs(X - 1714))]), float(clean[np.argmin(np.abs(X - 1714))]), delta=0.05)
        pts = process.apply(sp, [{"op": "baseline", "method": "points", "pts": [3900, 2500, 2000, 800], "interp": "linear"}]).spectrum.y
        self.assertLess(abs(float(pts[np.argmin(np.abs(X - 2200))])), 0.01)

    def test_savgol_preserves_polynomial(self):
        x = np.linspace(0, 1, 101)
        y = 3 * x ** 2 - x + 0.5
        # exakt für Polynome bis zum Grad der Glättung (am Rand nur angenähert, dort wird gespiegelt)
        np.testing.assert_allclose(process.savgol(y, 11, 2)[5:-5], y[5:-5], atol=1e-10)
        self.assertLess(float(np.max(np.abs(process.savgol(y, 11, 2) - y))), 1e-3)
        d = process.savgol(y, 11, 2, deriv=1, dx=x[1] - x[0])
        np.testing.assert_allclose(d[10:-10], (6 * x - 1)[10:-10], atol=1e-8)

    def test_pipeline_steps_described_and_cut(self):
        sp = Spectrum("x", X, pet_abs(), "A")
        p = process.apply(sp, [{"op": "cut", "lo": 700, "hi": 3800}, {"op": "smooth", "method": "sg", "points": 9, "order": 2},
                               {"op": "normalize", "mode": "max"}, {"op": "co2"}])
        self.assertEqual(len(p.steps), 4)
        self.assertGreaterEqual(p.spectrum.x[0], 700)
        self.assertLessEqual(p.spectrum.x[-1], 3800)
        self.assertAlmostEqual(float(np.max(p.spectrum.y)), 1.0, places=6)

    def test_op_requires_unit(self):
        with self.assertRaises(process.OpError):
            process.apply(Spectrum("a", X, pet_abs(), "A"), [{"op": "km"}])


# ----------------------------------------------------------------------------- Banden und Gruppen
class PeaksGroupsTest(unittest.TestCase):
    def test_pet_peaks_and_manual_edit(self):
        y = model("pet", shift=0)
        pk = peaks.find(X, y, "A", {"prominence": 3})
        xs = [round(p["x"]) for p in pk]
        for ref in (1713, 1240, 1094, 723):
            self.assertTrue(any(abs(v - ref) <= 2 for v in xs), ref)
        top = max(pk, key=lambda p: p["prom"])
        self.assertEqual(top["strength"], "vs")
        pk2 = peaks.find(X, y, "A", {"prominence": 3}, add=[1600], remove=[1713])
        self.assertFalse(any(abs(p["x"] - 1713) < 3 for p in pk2))
        self.assertTrue(any(p.get("manual") for p in pk2))

    def test_valleys_in_transmission(self):
        t = 100 * 10 ** (-0.8 * model("pet", shift=0))
        pk = peaks.find(X, t, "T", {"prominence": 3})
        self.assertTrue(any(abs(p["x"] - 1713) < 2 for p in pk))
        self.assertLess(min(p["y"] for p in pk), 30)

    def test_integrate_triangle(self):
        x = np.linspace(0, 10, 1001)
        y = np.where(x < 5, x, 10 - x)
        r = peaks.integrate(x, y, 0, 10, "A", "zero")
        self.assertAlmostEqual(r["area"], 25, places=3)
        self.assertAlmostEqual(r["pos"], 5, places=2)

    def test_assignments(self):
        self.assertTrue(any("C=O" in a or "Carbonyl" in a or "Ester" in a for a in groups.assign(1735, "s")))
        self.assertTrue(groups.assign(2918, "s"))

    def test_groups_pet_and_mixture(self):
        g = groups.analyse(X, pet_abs(), "A")
        likely = {c["id"] for c in g["classes"] if c["verdict"] == "wahrscheinlich"}
        self.assertTrue({"aromatic", "ester"} <= likely, likely)
        for no in ("acid", "amide", "nitrile", "silicate", "alcohol"):
            self.assertNotIn(no, {c["id"] for c in g["classes"] if c["verdict"] != "unwahrscheinlich"}, no)
        self.assertFalse(any("aliphatische" in a["text"] for a in g["absent"]), "PET hat schwache C–H-Banden")
        self.assertTrue(any("O–H" in a["text"] for a in g["absent"]))
        mix = 0.7 * model("pe") + 0.5 * model("calcite") + 0.02
        likely = {c["id"] for c in groups.analyse(X, mix, "A")["classes"] if c["verdict"] == "wahrscheinlich"}
        self.assertTrue({"alkyl", "carbonate"} <= likely, likely)


# ----------------------------------------------------------------------------- Signalqualität (Diamant-ATR, schwaches Signal)
def diamond_atr(scale=0.1, base_noise=4e-4, diamond_noise=4e-3, seed=3):
    """Schwaches ATR-Spektrum (PS, Maximum ~scale) mit stark verrauschtem Diamantfenster 2300–1900 cm⁻¹."""
    rng = np.random.default_rng(seed)
    y = scale * model("ps") / model("ps").max() + 0.002
    noise = np.full(len(X), base_noise)
    noise[(X >= 1900) & (X <= 2300)] = diamond_noise
    return y + rng.normal(0, 1, len(X)) * noise


class QualityTest(unittest.TestCase):
    def test_diamond_window_detected_and_ignored(self):
        y = diamond_atr()
        q = quality.assess(X, y, "A")
        self.assertEqual(len(q["noisy"]), 1, q["noisy"])
        hi, lo = q["noisy"][0]
        self.assertTrue(2250 <= hi <= 2340 and 1860 <= lo <= 1950, q["noisy"])
        self.assertTrue(any(w["kind"] == "noisy" and "Diamant" in w["de"] for w in q["warnings"]))
        pk = peaks.find(X, y, "A")
        self.assertFalse([p["x"] for p in pk if 1900 <= p["x"] <= 2300], "keine Rauschpeaks im Diamantfenster")
        self.assertTrue(any(abs(p["x"] - 698) < 4 for p in pk) and any(abs(p["x"] - 1493) < 4 for p in pk))
        g = groups.analyse(X, y, "A")
        bad = {c["id"] for c in g["classes"] if c["verdict"] != "unwahrscheinlich"} & {"nitrile", "isocyanate", "alkyne"}
        self.assertFalse(bad, bad)
        self.assertIn("aromatic", {c["id"] for c in g["classes"] if c["verdict"] == "wahrscheinlich"})
        self.assertTrue(g["masked"])
        # Suche: Fenster leer, PS bleibt vorne
        qv = LB.prep(X, y, "A", blank=q["noisy"])
        self.assertTrue(np.isnan(qv[(LB.GRID > 2000) & (LB.GRID < 2200)]).all())
        r = search.search(qv, [LB.model_library()], "dcorr", exclude=search.DEFAULT_EXCLUDE, n=2)
        self.assertIn("PS", r["hits"][0]["name"])

    def test_clean_and_weak_spectra(self):
        q = quality.assess(X, pet_abs(), "A")
        self.assertEqual(q["noisy"], [])
        self.assertGreater(q["snr"], 50)
        self.assertFalse([w for w in q["warnings"] if w["kind"] == "snr"])
        weak = diamond_atr(scale=0.004, base_noise=4e-4)
        qw = quality.assess(X, weak, "A")
        self.assertLess(qw["snr"], quality.POOR_SNR)
        self.assertTrue(any(w["kind"] == "snr" for w in qw["warnings"]))
        g = groups.analyse(X, weak, "A")
        self.assertEqual(g["absent"], [], "bei so viel Rauschen keine Aussagen über fehlende Banden")
        self.assertTrue(g["absent_note"])
        self.assertLessEqual(len([c for c in g["classes"] if c["verdict"] == "wahrscheinlich"]), 2)


# ----------------------------------------------------------------------------- Suche, Mischung, Bibliotheken
class SearchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib = LB.model_library()

    def test_every_algorithm_finds_pet(self):
        q = LB.prep(X, pet_abs(), "A")
        for algo in search.ALGOS:
            r = search.search(q, [self.lib], algo, exclude=search.DEFAULT_EXCLUDE, n=3)
            self.assertIn("PET", r["hits"][0]["name"], algo)
            self.assertGreater(r["hits"][0]["hqi"], 85, algo)
            self.assertGreater(r["hits"][0]["hqi"] - r["hits"][1]["hqi"], 20, algo)

    def test_identical_reference_scores_100(self):
        q = LB.prep(LB.GRID, model("ps", LB.GRID, 0, 1.0), "A")
        r = search.search(q, [self.lib], "corr", n=1)
        self.assertAlmostEqual(r["hits"][0]["hqi"], 100, delta=0.05)

    def test_coating_resins_distinct(self):
        # Lackbindemittel gegen ihre nächsten Verwandten (PS/PMMA, PET, Epoxid) unterscheidbar
        rng = np.random.default_rng(5)
        for mid in ("styacr", "pesmf", "epphen"):
            self.assertEqual(MATS[mid][3], "Lack/Beschichtung")
            y = model(mid) + 0.03 + rng.normal(0, 0.003, len(X))
            r = search.search(LB.prep(X, y, "A"), [self.lib], "corr", exclude=search.DEFAULT_EXCLUDE, n=2)
            self.assertEqual(r["hits"][0]["name"], MATS[mid][1], mid)
            self.assertGreater(r["hits"][0]["hqi"] - r["hits"][1]["hqi"], 3, mid)

    def test_mixture_pe_calcite(self):
        y = 0.7 * model("pe") + 0.5 * model("calcite") + 0.02 + np.random.default_rng(3).normal(0, 0.003, len(X))
        m = search.mixture(LB.prep(X, y, "A"), [self.lib], exclude=search.DEFAULT_EXCLUDE, max_components=3)
        best = m["combos"][0]
        names = {c["name"] for c in best["components"]}
        self.assertTrue(any("Polyethylen" in n for n in names) and any("Calcit" in n for n in names), names)
        self.assertEqual(best["n"], 2, "Sparsamkeit: keine dritte Komponente ohne Not")
        self.assertGreater(best["hqi"], 97)
        self.assertAlmostEqual(sum(c["frac"] for c in best["components"]), 1.0, places=6)

    def test_user_library_persist_search_export(self):
        with TemporaryDirectory() as tmp:
            libs = LB.Libraries(Path(tmp))
            lib = libs.create("Eigene Proben")
            with self.assertRaises(PermissionError):
                libs.get(LB.MODEL_ID).add(Spectrum("x", X, pet_abs(), "A"))
            e = lib.add(Spectrum("Meine PET-Folie", X, pet_abs(seed=5), "A"), {"category": "Kunststoff", "cas": "25038-59-9"})
            lib.add(Spectrum("Mein PS", X, model("ps"), "A"))
            lib.save()
            again = LB.Libraries(Path(tmp))
            lib2 = again.get(lib.id)
            self.assertEqual([x["name"] for x in lib2.entries], ["Meine PET-Folie", "Mein PS"])
            r = search.search(LB.prep(X, pet_abs(), "A"), [lib2, again.get(LB.MODEL_ID)], "corr", n=3)
            self.assertEqual(r["hits"][0]["name"], "Meine PET-Folie")
            sps = load_bytes(lib2.to_jcamp().encode(), "bib.jdx")
            self.assertEqual([s.name for s in sps], ["Meine PET-Folie", "Mein PS"])
            lib2.update(e["id"], {"comment": "geprüft"})
            lib2.remove(lib2.entries[1]["id"])
            self.assertEqual(len(lib2.G), 1)
            again.delete(lib.id)
            self.assertFalse((Path(tmp) / lib.id).exists())


# ----------------------------------------------------------------------------- mitgelieferte gemessene Referenzen
def open_specy():
    """The Open Specy library as one: public part plus, if fetched, the part with restricted licences."""
    libs = {lib.id: lib for lib in LB.bundled_libraries()}
    pub, rest = libs.get("openspecy"), libs.get("openspecy-restricted")
    if pub is None or rest is None:
        return pub
    m = LB.Library("openspecy", pub.name, pub.description, readonly=True)
    # same order as the maintainers' single library: both parts come from one build, ids "os<n>" and "ros<n>"
    entries, G = pub.entries + rest.entries, np.vstack([pub.G, rest.G])
    order = sorted(range(len(entries)), key=lambda i: int("".join(ch for ch in entries[i]["id"] if ch.isdigit())))
    m.source, m.entries, m.G = pub.source, [entries[i] for i in order], G[order]
    return m


class BundledLibraryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.os = open_specy()

    def test_loaded_readonly_and_attributed(self):
        lib = self.os
        self.assertIsNotNone(lib, "ftir/data/openspecy fehlt")
        self.assertTrue(lib.readonly)
        full = available("openspecy")
        self.assertGreater(len(lib.entries), 1000 if full else 150)
        self.assertEqual(lib.G.shape, (len(lib.entries), len(LB.GRID)))
        cats = set(lib.info()["categories"])
        for c in (("Kunststoff", "Füllstoff/Mineral", "Faser", "Naturstoff", "Elastomer") if full else ("Kunststoff",)):
            self.assertIn(c, cats)
        for e in lib.entries:
            self.assertTrue(e["source"] and e["group"] and e["name"], e)
        if full:
            self.assertTrue(any(e.get("license") == "CC BY-NC" for e in lib.entries))
        with self.assertRaises(PermissionError):
            lib.add(Spectrum("x", X, pet_abs(), "A"))
        with TemporaryDirectory() as tmp:
            L = LB.Libraries(Path(tmp))
            self.assertIn("openspecy", L.libs)
            with self.assertRaises(PermissionError):
                L.delete("openspecy")

    def _ref(self, group):
        """Erstes gemessenes Spektrum eines Stoffs (Gruppe) auf dem Suchraster."""
        i = next(k for k, e in enumerate(self.os.entries) if e["group"] == group)
        g = self.os.G[i].astype(float)
        return np.nan_to_num(g), self.os.entries[i]

    @skip_unless("openspecy")
    def test_measured_references_found_and_collapsed(self):
        rng = np.random.default_rng(2)
        for gid in ("pp", "pet", "pa6", "x:calcite", "x:quartz", "cotton", "x:caffeine"):
            g, e = self._ref(gid)
            q = LB.prep(LB.GRID, g + rng.normal(0, 0.004, len(g)) + 0.03, "A")
            r = search.search(q, [self.os], "corr", exclude=search.DEFAULT_EXCLUDE, n=8, collapse=True)
            ok = {"pet": {"pet", "pest"}}.get(gid, {gid})      # Polyesterfaser ist praktisch immer PET
            self.assertIn(self.os.entries[self.os.index(r["hits"][0]["id"])]["group"], ok, (gid, r["hits"][0]["name"]))
            self.assertGreater(r["hits"][0]["hqi"], 95, gid)
            groups = [self.os.entries[self.os.index(h["id"])]["group"] for h in r["hits"]]
            self.assertEqual(len(groups), len(set(groups)), "zusammengefasst: je Stoff ein Treffer")
            full = search.search(q, [self.os], "corr", exclude=search.DEFAULT_EXCLUDE, n=8, collapse=False)
            self.assertAlmostEqual(full["hits"][0]["hqi"], r["hits"][0]["hqi"], places=2)
        # berechnete Modellspektren finden die gemessenen Gegenstücke (robuste Fälle)
        for mid, want in (("ps", "Polystyrol"), ("pp", "Polypropylen"), ("pa6", "Polyamid"), ("kaolin", "Kaolinit")):
            r = search.search(LB.prep(X, model(mid) + 0.02, "A"), [self.os], "corr", exclude=search.DEFAULT_EXCLUDE,
                              n=5, collapse=True)
            self.assertTrue(any(want.lower() in h["name"].lower() for h in r["hits"][:3]), (mid, [h["name"] for h in r["hits"][:3]]))

    @skip_unless("openspecy")
    def test_mixture_candidates_distinct(self):
        a, _ = self._ref("pp")
        b, _ = self._ref("x:calcite")
        y = 0.6 * a + 0.5 * b + 0.02 + np.random.default_rng(4).normal(0, 0.003, len(a))
        m = search.mixture(LB.prep(LB.GRID, y, "A"), [self.os], exclude=search.DEFAULT_EXCLUDE, max_components=3)
        names = " | ".join(c["name"] for c in m["combos"][0]["components"])
        self.assertIn("Polypropylen", names)
        self.assertIn("Calcite", names)
        self.assertGreater(m["combos"][0]["hqi"], 97)
        for c in m["combos"]:
            gs = [self.os.entries[self.os.index(k["id"])]["group"] for k in c["components"] if k["lib"] == "openspecy"]
            self.assertEqual(len(gs), len(set(gs)), "keine Mischung aus zwei Spektren desselben Stoffs")

    def test_rds_reader(self):
        sys.path.insert(0, str(ROOT / "tools"))
        from rds import read_rds
        import gzip
        import struct

        def i(v):
            return struct.pack(">i", v)

        def chars(s):
            b = s.encode()
            return i(9 | (1 << 15)) + i(len(b)) + b

        def strs(*ss):
            return i(16) + i(len(ss)) + b"".join(chars(s) for s in ss)

        def reals(v, attrs=b""):
            return i(14 | ((1 << 9) if attrs else 0)) + i(len(v)) + b"".join(struct.pack(">d", x) for x in v) + attrs

        def attr(pairs):           # Paarliste (tag, wert)
            out = b""
            for k, (tag, val) in enumerate(pairs):
                out += i(2 | (1 << 10)) + i(1) + chars(tag) + val
            return out + i(254)

        def vec(items, names, cls=None):
            pl = [("names", strs(*names))] + ([("class", strs(*cls))] if cls else [])
            return i(19 | (1 << 9)) + i(len(items)) + b"".join(items) + attr(pl)

        md = vec([strs("ftir", "raman"), strs("pe", "pp")], ["spectrum_type", "spectrum_identity"], ["data.table", "data.frame"])
        sp = vec([reals([0.1, 0.2]), reals([0.3, float("nan")])], ["a", "b"])
        obj = vec([reals([600.0, 606.0]), sp, md], ["wavenumber", "spectra", "metadata"], ["OpenSpecy", "list"])
        raw = b"X\n" + i(3) + i(0x040300) + i(0x030500) + i(5) + b"UTF-8" + obj
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "t.rds"
            p.write_bytes(gzip.compress(raw))
            o = read_rds(p)
        self.assertEqual(o.attrs["class"], ["OpenSpecy", "list"])
        self.assertEqual(list(o.get("wavenumber")), [600.0, 606.0])
        self.assertEqual(o.get("metadata").get("spectrum_identity"), ["pe", "pp"])
        self.assertTrue(np.isnan(o.get("spectra")[1][1]))


# ----------------------------------------------------------------------------- Bericht
def charts_tag(e, lib):
    from ftir import charts
    return charts.ref_tag(lib.ref_of(e))


class BundleTest(unittest.TestCase):
    def _state(self, raw, name):
        sp = load_bytes(raw, name)[0]
        s = process.apply(sp, [{"op": "to_abs"}] if sp.yunit == "T" else []).spectrum
        q = LB.prep(s.x, s.y, s.yunit)
        r = search.search(q, [LB.model_library()], "corr", exclude=search.DEFAULT_EXCLUDE, n=5)
        hits = [{k: h[k] for k in ("rank", "name", "lib_name", "hqi", "category", "cas")} | ({"y": h["y"].tolist()} if i < 3 else {})
                for i, h in enumerate(r["hits"])]
        return {"pipeline": [{"op": "to_abs"}] if sp.yunit == "T" else [], "peaks": {"params": {}}, "groups": True,
                "bands": [{"name": "C=O", "lo": 1650, "hi": 1780}, {"name": "Ring", "lo": 700, "hi": 745}],
                "ratios": [{"name": "C=O/Ring", "num": "C=O", "den": "Ring"}],
                "search": {"algo": "corr", "hits": hits, "query": [None if not np.isfinite(v) else float(v) for v in q]}}

    def test_single_and_comparison(self):
        raw, name = samples.make("pet")
        st = self._state(raw, name)
        b = bundle.build([(raw, name, 0, st)], {"items": [{"name": name, "idx": 0, "state": st}]}, "de")
        kinds = [(i["kind"], i.get("id")) for i in b["items"]]
        for want in (("figure", "spektrum"), ("figure", "suche"), ("table", "peaks"), ("table", "gruppen"),
                     ("table", "treffer"), ("table", "flaechen"), ("data", "spektrum"), ("text", "methodik"), ("text", "ergebnisse")):
            self.assertIn(want, kinds)
        vals = next(i for i in b["items"] if i["kind"] == "values")["values"]
        keys = {v["key"] for v in vals}
        self.assertTrue({"npeaks", "peak1", "hit1", "hqi1", "band1", "ratio1"} <= keys, keys)
        self.assertIn("PET", next(v["text"] for v in vals if v["key"] == "hit1"))
        methods = base64.b64decode(b["files"]["text-methodik.tex"]).decode()
        self.assertIn("Modellbibliothek", methods)
        self.assertIn("keine gemessenen", methods)
        self.assertIn(name, b["source"]["files"])
        raw2, name2 = samples.make("mix")
        b2 = bundle.build([(raw, name, 0, st), (raw2, name2, 0, {"peaks": {"params": {}}})], {"items": []}, "en", include={"data": False})
        ids = [i.get("id") for i in b2["items"]]
        self.assertIn("vergleich", ids)
        self.assertNotIn("spektrump1", [i.get("id") for i in b2["items"] if i["kind"] == "data"])
        self.assertTrue(all(i.get("id") != "suche" for i in b2["items"]), "Vergleich: Kennungen mit Präfix")

    @skip_unless("openspecy")
    def test_reference_sources_cited_automatically(self):
        """Figuren und Tabellen mit Referenzspektren tragen die Quellen in der Bildunterschrift; geöffnete Referenzen
        behalten ihre Herkunft über JCAMP und werden als solche zitiert."""
        os_, mod = open_specy(), LB.model_library()
        i = next(k for k, e in enumerate(os_.entries) if e["group"] == "x:calcite" and e["source"].startswith("RRUFF"))
        e = os_.entries[i]
        g = np.nan_to_num(os_.G[i].astype(float))
        q = LB.prep(LB.GRID, g + 0.02, "A")
        r = search.search(q, [os_], "corr", exclude=search.DEFAULT_EXCLUDE, n=6, collapse=True)
        rm = search.search(q, [mod], "corr", exclude=search.DEFAULT_EXCLUDE, n=2)
        hits = [dict(h, y=h["y"].tolist()) if k < 3 else {kk: v for kk, v in h.items() if kk != "y"}
                for k, h in enumerate(r["hits"] + rm["hits"])]
        self.assertTrue(any(h["lib"] == "modell" for h in hits) and hits[0]["lib"] == "openspecy")
        mixc = [{"name": hits[0]["name"], "lib": "openspecy", "lib_name": os_.name, "source": hits[0]["source"], "frac": 1.0,
                 "y": hits[0]["y"]}]
        qq = [None if not np.isfinite(v) else float(v) for v in q]
        st = {"search": {"algo": "corr", "hits": hits, "query": qq},
              "mixture": {"components": mixc, "fit": hits[0]["y"], "residual": [0.0] * len(q), "query": qq, "hqi": 99.0}}
        sp = Spectrum("Probe", LB.GRID.copy(), g + 0.02, "A")
        raw, name = to_jcamp(sp).encode(), "probe.jdx"
        b = bundle.build([(raw, name, 0, st)], {"items": []}, "de")
        items = {(i["kind"], i.get("id")): i for i in b["items"]}
        bib = base64.b64decode(b["files"]["refs.bib"]).decode()
        fig = items[("figure", "suche")]
        self.assertIn(r"\cite{", fig["caption"])
        self.assertIn("openspecy2025", fig["cites"])
        self.assertIn("ref-rruff", fig["cites"])
        tab = items[("table", "treffer")]
        self.assertIn(bundle.MODEL_KEY, tab["cites"], "Modelltreffer unter den ersten 10: Modellbibliothek zitiert")
        self.assertGreaterEqual(base64.b64decode(b["files"][tab["file"]]).decode().count(r"\cite{"), len(hits[:10]))
        self.assertIn("openspecy2025", items[("table", "mischung")]["cites"])
        for k in set(fig["cites"]) | set(tab["cites"]):
            self.assertIn("{" + k + ",", bib)
        self.assertNotIn("\\cite", items[("figure", "spektrum")]["caption"], "eigene Messung: keine Fremdquelle")
        # geöffnete Referenz: Herkunft über JCAMP, Bericht zitiert sie am Spektrum selbst
        ref = os_.spectrum(e["id"])
        ref.meta["refs"] = [os_.ref_of(e)]
        raw2 = to_jcamp(ref, ref.name).encode()
        back = load_bytes(raw2, "ref.jdx")[0]
        self.assertEqual(back.meta["refs"][0]["source"], e["source"])
        b2 = bundle.build([(raw2, "ref.jdx", 0, {})], {"items": []}, "en")
        cap = next(i for i in b2["items"] if i.get("id") == "spektrum")["caption"]
        self.assertIn("openspecy2025", cap)
        self.assertIn("ref-rruff", cap)
        self.assertIn("reference spectrum from Open Specy/RRUFF", base64.b64decode(b2["files"]["text-methodik.tex"]).decode())
        self.assertEqual(charts_tag(e, os_), "Open Specy/RRUFF")

    def test_tex_escaping_of_formulas(self):
        self.assertEqual(bundle.tx("CO₃²⁻"), r"CO$_{3}$$^{2-}$")
        self.assertIn(r"\equiv", bundle.tx("C≡N"))
        self.assertIn(r"\%", bundle.tx("50 %"))


# ----------------------------------------------------------------------------- Server
class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from ftir import server as S
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

    def post(self, path, body=None, raw=None, origin=None):
        data = raw if raw is not None else json.dumps(body or {}).encode()
        req = urllib.request.Request(self.base + path, data=data, method="POST")
        req.add_header("Content-Type", "application/octet-stream" if raw is not None else "application/json")
        if origin:
            req.add_header("Origin", origin)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_share_peaks(self):
        """A6: Peaktabelle + Gruppenhypothesen teilen; erneut teilen = neue Version; kein Spektrum im Umschlag."""
        code, j = self.post("/api/sample", {"which": "pet"})
        sid = j["spectra"][0]["id"]
        code, e1 = self.post("/api/share/peaks", {"id": sid, "pipeline": [{"op": "to_abs"}, {"op": "baseline", "method": "als"}]})
        self.assertEqual(code, 200, e1)
        self.assertEqual((e1["kind"], e1["version"]), ("ftir.peaks", 1))
        peaks = [o["quantity"]["value"] for o in e1["outputs"] if o["key"].startswith("peak")]
        self.assertTrue(any(1700 <= x <= 1730 for x in peaks), peaks)              # C=O Ester
        ester = next(o for o in e1["outputs"] if o["key"] == "class-ester")
        self.assertIn(ester["conditions"]["verdict"], ("wahrscheinlich", "möglich"))
        code, e2 = self.post("/api/share/peaks", {"id": sid, "pipeline": [{"op": "to_abs"}]})
        self.assertEqual((e2["id"], e2["version"]), (e1["id"], 2))

    def test_flow(self):
        with urllib.request.urlopen(self.base + "/api/meta", timeout=60) as r:   # libraries warm up in the background
            meta = json.loads(r.read())
        self.assertIn("baseline", meta["ops"])
        self.assertEqual(meta["libs"][0]["id"], "modell")
        code, j = self.post("/api/sample", {"which": "pet"})
        self.assertEqual(code, 200)
        sid = j["spectra"][0]["id"]
        code, j = self.post("/api/spectrum", {"id": sid, "pipeline": [{"op": "to_abs"}, {"op": "baseline", "method": "als"}], "preview": True})
        self.assertEqual((code, j["yunit"]), (200, "A"))
        self.assertEqual(len(j["baseline"]), len(j["x"]))
        code, j = self.post("/api/analyse", {"id": sid, "pipeline": [{"op": "to_abs"}], "peaks": {"params": {}}, "groups": True,
                                             "bands": [{"name": "C=O", "lo": 1650, "hi": 1780}]})
        self.assertTrue(j["peaks"] and j["groups"]["classes"] and j["bands"][0]["area"] > 0)
        code, j = self.post("/api/search", {"id": sid, "pipeline": [{"op": "to_abs"}], "libs": ["modell"], "algo": "corr"})
        self.assertIn("PET", j["hits"][0]["name"])
        self.assertEqual(len(j["query"]), meta["grid"]["n"])
        code, j = self.post("/api/library/create", {"name": "Server Test"})
        lid = j["lib"]["id"]
        code, j = self.post("/api/library/add", {"lib": lid, "id": sid, "pipeline": [], "meta": {"name": "Folie"}})
        self.assertEqual(j["entry"]["name"], "Folie")
        code, j = self.post("/api/library/add", {"lib": "modell", "id": sid, "pipeline": []})
        self.assertEqual(code, 403)
        raw = jcamp_difdup(600, 2.0, [int(1000 * v) for v in model("ps", np.arange(600, 4000, 2.0))], 0.001, title="PS komprimiert")
        code, j = self.post(f"/api/library/import?lib={lid}&name=ps.jdx&category=Kunststoff", raw=raw.encode())
        self.assertEqual((code, len(j["added"])), (200, 1))
        code, j = self.post("/api/library/open", {"lib": lid, "eid": j["added"][0]["id"]})
        self.assertEqual(j["spectra"][0]["name"], "PS komprimiert")
        rid = j["spectra"][0]["id"]
        self.assertEqual(self.S.item(rid).sp.meta["refs"][0]["lib"], lid, "geöffnete Referenz kennt ihre Bibliothek")
        code, j = self.post("/api/derive", {"op": "diff", "ids": [sid, rid], "pipelines": {}})
        self.assertEqual(code, 200, j)
        self.assertEqual(self.S.item(j["spectra"][0]["id"]).sp.meta["refs"][0]["lib"], lid,
                         "Differenzspektrum behält die Herkunft der Referenz")
        code, j = self.post("/api/bundle", {"items": [{"id": sid, "state": {"peaks": {"params": {}}}}], "lang": "en", "include": {}})
        self.assertEqual(code, 200, j)
        code, j2 = self.post("/api/bundle/rebuild", {"source": j["source"], "lang": "de"})
        self.assertEqual((code, j2["lang"]), (200, "de"))
        code, j = self.post("/api/export", {"id": sid, "pipeline": [], "peaks": {"params": {}}})
        self.assertIn("spektrum.png", j["files"])
        code, _ = self.post("/api/sample", {"which": "pet"}, origin="http://evil.example")
        self.assertEqual(code, 403)
        code, j = self.post("/api/load?name=leer.csv", raw=b"nichts")
        self.assertEqual(code, 400)

    def test_reference_from_file_with_source_and_equations(self):
        from urllib.parse import quote
        cite = {"type": "article", "authors": "Muster, A.; Beispiel, B.", "title": "IR-Spektren von Polystyrol",
                "container": "Vibrational Spectroscopy", "year": "2023", "doi": "10.1234/ps.77"}
        raw = jcamp_difdup(600, 2.0, [int(1000 * v) for v in model("ps", np.arange(600, 4000, 2.0))], 0.001, title="PS Paper")
        bad = quote(json.dumps({"type": "article", "title": "ohne Zeitschrift"}))
        code, j = self.post(f"/api/library/import?lib=eigene-referenzen&name=ps.jdx&open=1&cite={bad}", raw=raw.encode())
        self.assertEqual(code, 400, "unvollständige Quelle wird abgelehnt, nichts gespeichert")
        q = quote(json.dumps(cite))
        code, j = self.post(f"/api/library/import?lib=eigene-referenzen&name=ps.jdx&open=1&label=PS%20(Paper)&cite={q}", raw=raw.encode())
        self.assertEqual(code, 200, j)
        self.assertEqual(j["lib"]["id"], "eigene-referenzen")
        self.assertEqual(j["added"][0]["cite"]["doi"], "10.1234/ps.77")
        self.assertIn("Muster", j["added"][0]["source"])
        rid = j["spectra"][0]["id"]
        self.assertEqual(j["spectra"][0]["name"], "PS (Paper)")
        self.assertEqual(self.S.item(rid).sp.meta["refs"][0]["cite"]["doi"], "10.1234/ps.77", "Quelle reist mit dem Spektrum")
        # Suche: der Treffer trägt die Quelle, der Bericht zitiert sie als @article mit DOI
        code, j = self.post("/api/sample", {"which": "pet"})
        sid = j["spectra"][0]["id"]
        code, s = self.post("/api/search", {"id": rid, "pipeline": [], "libs": ["eigene-referenzen"], "algo": "corr"})
        self.assertEqual(s["hits"][0]["cite"]["doi"], "10.1234/ps.77")
        eq = [{"sym": "CI", "label": "Carbonylindex", "expr": "area(1650, 1850)/area(1420, 1500)", "digits": 3,
               "source": {"type": "article", "authors": "Almond, J.; Sugumaar, P.; Wenzel, M. N.; Hill, G.; Wallis, C.",
                          "title": "Determination of the carbonyl index of polyethylene and polypropylene using specified area under band methodology with ATR-FTIR spectroscopy",
                          "container": "e-Polymers", "year": "2020", "volume": "20", "pages": "369-381", "doi": "10.1515/epoly-2020-0041"}},
              {"sym": "a1715", "expr": "A(1715)", "digits": 3},
              {"sym": "CI2", "expr": "B1/B2"},
              {"sym": "aus", "expr": "A(5000)"}]
        code, j = self.post("/api/equations/save", {"item": eq[0]})
        self.assertEqual(code, 200, j)
        code, j = self.post("/api/equations/save", {"item": {"sym": "area", "expr": "1"}})
        self.assertEqual(code, 400)
        st = {"pipeline": [{"op": "to_abs"}], "bands": [{"name": "C=O", "lo": 1650, "hi": 1850}, {"name": "CH2", "lo": 1420, "hi": 1500}],
              "equations": eq}
        code, a = self.post("/api/analyse", {"id": sid, **st})
        res = {e["sym"]: e for e in a["equations"]}
        self.assertAlmostEqual(res["CI"]["value"], res["CI2"]["value"], places=6)
        self.assertGreater(res["a1715"]["value"], 0)
        self.assertIn("ausserhalb", res["aus"]["error"])
        self.assertIn("B1", [v["name"] for v in a["variables"]])
        code, b = self.post("/api/bundle", {"items": [{"id": sid, "state": {**st, "search": {"hits": s["hits"][:3], "query": s["query"]}}}],
                                            "lang": "de", "include": {}})
        self.assertEqual(code, 200, b)
        bib = base64.b64decode(b["files"]["refs.bib"]).decode("utf-8")
        self.assertIn("10.1234/ps.77", bib)
        self.assertIn("10.1515/epoly-2020-0041", bib)
        self.assertRegex(bib, r"@article\{src-")
        meth = base64.b64decode(b["files"]["text-methodik.tex"]).decode("utf-8")
        self.assertIn(r"\mathrm{CI}", meth)
        vals = base64.b64decode(b["files"]["values.tex"]).decode("utf-8")
        self.assertIn("eq-CI", vals)
        self.assertNotIn("eq-aus", vals)
        # Neuaufbau aus dem Bundle allein (Bibliothek und Gleichung später gelöscht)
        self.post("/api/library/delete", {"lib": "eigene-referenzen"})
        code, b2 = self.post("/api/bundle/rebuild", {"source": b["source"], "lang": "de"})
        self.assertEqual(code, 200, b2)
        self.assertIn("10.1234/ps.77", base64.b64decode(b2["files"]["refs.bib"]).decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
