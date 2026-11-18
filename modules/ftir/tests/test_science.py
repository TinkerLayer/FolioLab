"""FTIR 1.5: Prüfungen mit bekannten Ergebnissen zu den wissenschaftlichen Korrekturen (CO₂-Bereiche, Normieren,
ATR, ALS-λ, Flächen auf Absorbanz, Bandenzuordnung, Peaksuche, Mischung, S/N, Einheiten beim Einlesen, Open Specy).

Start:  python -m unittest discover -s tests   (im Ordner modules/ftir)
scipy wird nur hier als unabhängige Vergleichsrechnung benutzt (nie zur Laufzeit) und ist optional.
"""
import struct
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "sdk" / "python"))

from ftir import groups, peaks, process, quality, refdata, search  # noqa: E402
from ftir import library as LB  # noqa: E402
from ftir.readers import ReadError, Spectrum, load_bytes  # noqa: E402

X = np.arange(600.0, 4000.0 + 1e-9, 1.0)
MATS = {m[0]: m for m in refdata.MATERIALS}


def model(mid, x=X, shift=1.0, widen=1.1):
    return refdata.band_model([(c + shift, h, w * widen) for c, h, w in MATS[mid][4]], x)


def gauss(x, x0, h, fwhm):
    s = fwhm / (2 * np.sqrt(2 * np.log(2)))
    return h * np.exp(-0.5 * ((x - x0) / s) ** 2)


def spc(x0, x1, y, fxtype=1, fytype=2):
    """Minimale SPC-Datei (neues Format, ein Spektrum, float32) mit wählbarem fxtype/fytype (Kopf-Byte 28/29)."""
    n = len(y)
    head = bytearray(512)
    struct.pack_into("<BBBbiddiBBBBi", head, 0, 0, 0x4B, 0, -128, n, x0, x1, 1, fxtype, fytype, 0, 0, 0)
    head[88:92] = b"Test"
    sub = struct.pack("<Bbhfffi", 0, 0, 0, 0.0, 0.0, 0.0, 0) + b"\0" * 12
    return bytes(head) + sub + np.asarray(y, "<f4").tobytes()


# ----------------------------------------------------------------------------- 1 CO₂-Bereiche
class Co2Test(unittest.TestCase):
    def test_narrow_keeps_neighbouring_sample_bands(self):
        # PS 698 cm⁻¹ und Calcit 712 cm⁻¹ liegen ausserhalb von 680–655 (eng); der weite Bereich 720–630 schneidet sie ab
        y = model("ps") + 0.6 * model("calcite") + 0.02
        sp = Spectrum("ps+cc", X, y, "A")
        nar = process.apply(sp, [{"op": "co2"}]).spectrum.y
        wid = process.apply(sp, [{"op": "co2", "ranges": "wide"}]).spectrum.y
        for band in (698, 712):
            i = int(np.argmin(np.abs(X - band)))
            self.assertEqual(nar[i], y[i], f"{band} cm⁻¹ bleibt unverändert (ausserhalb 680–655)")
            self.assertNotAlmostEqual(wid[i], y[i], places=3, msg=f"{band} cm⁻¹ liegt in 720–630 (weit)")
        # Isocyanat-Bande bei 2270 cm⁻¹ liegt ausserhalb 2390–2280
        i = int(np.argmin(np.abs(X - 2270)))
        self.assertEqual(nar[i], y[i])

    def test_overlap_warning(self):
        base = 0.05 + 0.0 * X
        co2 = gauss(X, 2360, 0.05, 12) + gauss(X, 2340, 0.04, 12) + gauss(X, 668, 0.03, 4)
        rng = np.random.default_rng(1)
        noise = rng.normal(0, 5e-4, len(X))
        p = process.apply(Spectrum("co2", X, base + co2 + noise, "A"), [{"op": "co2"}])
        self.assertEqual(p.warnings, [], "nur CO₂ im Bereich: kein Hinweis")
        # Probenbande bei 2285 cm⁻¹ (FWHM 30) reicht über die Grenze 2280 -> Hinweis
        p2 = process.apply(Spectrum("nco", X, base + co2 + gauss(X, 2285, 0.4, 30) + noise, "A"), [{"op": "co2"}])
        self.assertTrue(any(w["kind"] == "co2_overlap" and w["range"] == [2390.0, 2280.0] for w in p2.warnings), p2.warnings)

    def test_unknown_ranges_refused(self):
        with self.assertRaises(process.OpError):
            process.apply(Spectrum("a", X, model("pet"), "A"), [{"op": "co2", "ranges": "x"}])


# ----------------------------------------------------------------------------- 2 Normieren auf eine Bande
class NormalizeTest(unittest.TestCase):
    def test_peak_normalisation_refused_for_transmission(self):
        t = 100 * 10 ** (-model("pet"))
        with self.assertRaises(process.OpError) as cm:
            process.apply(Spectrum("t", X, t, "T"), [{"op": "normalize", "mode": "peak", "at": 1714}])
        self.assertIn("Absorbanz", str(cm.exception))
        # nach Umrechnung: Bande bei 1714 cm⁻¹ = 1 (erwartet exakt 1, Definition)
        out = process.apply(Spectrum("t", X, t, "T"), [{"op": "to_abs"}, {"op": "normalize", "mode": "peak", "at": 1714}])
        m = np.abs(out.spectrum.x - 1714) <= 5
        self.assertAlmostEqual(float(np.max(out.spectrum.y[m])), 1.0, places=12)

    def test_peak_normalisation_needs_positive_band(self):
        with self.assertRaises(process.OpError):
            process.apply(Spectrum("a", X, -model("pet"), "A"), [{"op": "normalize", "mode": "peak", "at": 1714}])


# ----------------------------------------------------------------------------- 3 ATR
class AtrTest(unittest.TestCase):
    def test_atr_factor_is_wavenumber_over_reference(self):
        # d_p ∝ λ ∝ 1/ν̃ (Harrick 1967) -> Korrektur y · ν̃/ν̃_ref; für y = 1 erwartet ν̃/1000 exakt
        out = process.apply(Spectrum("a", X, np.ones(len(X)), "A"), [{"op": "atr", "ref": 1000}]).spectrum.y
        np.testing.assert_allclose(out, X / 1000.0, rtol=0, atol=1e-15)
        # Verhältnis zweier gleich hoher Banden bei 3000 und 1000 cm⁻¹ nach Korrektur: 3 (= 3000/1000)
        y = gauss(X, 3000, 0.1, 20) + gauss(X, 1000, 0.1, 20)
        c = process.apply(Spectrum("a", X, y, "A"), [{"op": "atr", "ref": 1000}]).spectrum.y
        self.assertAlmostEqual(c[X == 3000][0] / c[X == 1000][0], 3.0, places=6)
        with self.assertRaises(process.OpError):
            process.apply(Spectrum("a", X, y, "A"), [{"op": "atr", "ref": 0}])


# ----------------------------------------------------------------------------- 4 ALS
class AlsTest(unittest.TestCase):
    @staticmethod
    def curve(x):
        return model("pet", x) + 0.3 + 0.2 * np.sin((x - 600) / 900)

    def test_lambda_scaling(self):
        # λ_Punkt = 10^lam · (1 cm⁻¹/h)⁴ (Diskretisierung von λ∫z''² dν̃, Eilers & Boelens 2005): h = 2 -> 10⁶/16
        x2 = np.arange(600.0, 4000.0, 2.0)
        self.assertAlmostEqual(process.als_lambda(x2, 6, "cm1"), 1e6 / 16, places=6)
        self.assertEqual(process.als_lambda(x2, 6, "point"), 1e6)
        self.assertAlmostEqual(process.als_lambda(X, 6, "cm1"), 1e6, places=6)

    def test_same_baseline_on_any_grid(self):
        # gleiche Kurve auf 1 und 2 cm⁻¹ Raster: mit Bezug 1 cm⁻¹ gleiche Basislinie (gemessen: 7e-6), je Punkt nicht
        b = {}
        for ref in ("cm1", "point"):
            for h in (1.0, 2.0):
                x = np.arange(600.0, 4000.0 + 1e-9, h)
                b[ref, h] = (x, process.baseline_of(x, self.curve(x), {"method": "als", "lam": 6, "p": 0.01, "lam_ref": ref}))
        x1, b1 = b["cm1", 1.0]
        x2, b2 = b["cm1", 2.0]
        self.assertLess(float(np.max(np.abs(np.interp(x2, x1, b1) - b2))), 1e-4)
        x2p, b2p = b["point", 2.0]
        self.assertGreater(float(np.max(np.abs(np.interp(x2p, x1, b["point", 1.0][1]) - b2p))), 5e-3)

    def test_banded_solver_against_scipy(self):
        try:
            from scipy import sparse
            from scipy.sparse.linalg import spsolve
        except ImportError:
            self.skipTest("scipy nicht installiert (nur für diese Vergleichsrechnung)")
        rng = np.random.default_rng(0)
        n, lam = 300, 1e4
        y = rng.normal(0, 1, n)
        w = rng.uniform(0.01, 1, n)
        D = sparse.diags([1.0, -2.0, 1.0], [0, 1, 2], shape=(n - 2, n))
        z_ref = spsolve((sparse.diags(w) + lam * D.T @ D).tocsc(), w * y)
        d0 = np.full(n, 6.0)
        d0[[0, -1]] = 1.0
        d0[[1, -2]] = 5.0
        d1 = np.full(n - 1, -4.0)
        d1[[0, -1]] = -2.0
        z = process._penta_solve(w + lam * d0, lam * d1, lam * np.ones(n - 2), w * y)
        np.testing.assert_allclose(z, z_ref, rtol=1e-8, atol=1e-10)

    def test_old_behaviour_selectable(self):
        p = process.apply(Spectrum("a", X, self.curve(X), "A"), [{"op": "baseline", "method": "als", "lam_ref": "point"}])
        self.assertIn("je Punkt", p.steps[0])
        with self.assertRaises(process.OpError):
            process.apply(Spectrum("a", X, self.curve(X), "A"), [{"op": "baseline", "method": "als", "lam_ref": "x"}])


# ----------------------------------------------------------------------------- 5 Flächen und Breiten auf Absorbanz
class AreaBasisTest(unittest.TestCase):
    def test_integrate_transmission_on_absorbance(self):
        # Gauss in A: Höhe 0,8, σ = 10 cm⁻¹ -> Fläche 0,8 · 10 · √(2π) = 20,0530 (analytisch; Grenzen ±10σ)
        a = 0.8 * np.exp(-0.5 * ((X - 1700) / 10) ** 2)
        t = 100 * 10 ** (-a)
        rt = peaks.integrate(X, t, 1600, 1800, "T", "linear")
        ra = peaks.integrate(X, a, 1600, 1800, "A", "linear")
        self.assertEqual(rt["basis"], "A")
        self.assertAlmostEqual(rt["area"], 0.8 * 10 * np.sqrt(2 * np.pi), places=3)
        self.assertAlmostEqual(rt["area"], ra["area"], places=9)
        self.assertAlmostEqual(rt["height"], 0.8, places=9)

    def test_peak_width_and_area_of_transmission_band(self):
        # FWHM eines Gauss = 2√(2 ln 2) σ = 23,548 cm⁻¹ (σ = 10); auf −%T wäre die Bande breiter
        a = 0.8 * np.exp(-0.5 * ((X - 1700) / 10) ** 2)
        pk = peaks.find(X, 100 * 10 ** (-a), "T", {"prominence": 3})
        self.assertEqual(len(pk), 1)
        self.assertAlmostEqual(pk[0]["fwhm"], 23.548, delta=0.05)
        self.assertAlmostEqual(pk[0]["area"], 20.053, delta=0.01)
        self.assertLess(pk[0]["y"], 20, "Lage und Höhe bleiben in %T (Minimum bei 100·10^-0,8 = 15,8 %)")

    def test_reflectance_basis(self):
        r = 100 * 10 ** (-gauss(X, 1500, 0.5, 30))
        self.assertEqual(peaks.integrate(X, r, 1400, 1600, "R")["basis"], "LR")


# ----------------------------------------------------------------------------- 6 Zuordnung
class AssignTest(unittest.TestCase):
    def test_pet_bands_assigned_to_ester_and_ring(self):
        g = groups.analyse(X, model("pet"), "A")
        ctx = groups.context_of(g)
        self.assertEqual(ctx.get("Ester"), 0, ctx)
        # Erwartung: Lehrbuchzuordnung von PET (Silverstein et al. 2014, Kap. 2: Ester C=O, C–O–C, aromatischer Ring)
        cases = {1715: ("vs", 20, "Ester"), 1242: ("vs", 25, "Ester"), 1095: ("s", 20, "Ester"), 1579: ("w", 8, "aromat")}
        for x0, (st, fw, want) in cases.items():
            first = groups.assign(x0, st, "de", 3, fw, ctx)[0]
            self.assertIn(want, first, (x0, first))

    def test_sharp_band_not_assigned_to_broad_group(self):
        # 1095 cm⁻¹ mit 20 cm⁻¹ Breite ist keine Sulfatbande (breit, Tabelle "br"); ohne Breite kommt Sulfat zuerst
        self.assertIn("Sulfat", groups.assign(1095, "s", "de", 3)[0])
        self.assertNotIn("Sulfat", groups.assign(1095, "s", "de", 3, fwhm=20)[0])


# ----------------------------------------------------------------------------- 7 Suche und Mischung
class SearchMixTest(unittest.TestCase):
    def test_peak_tolerance(self):
        # 6 cm⁻¹ + 0,4 %: 10 bei 1000, 18 bei 3000 cm⁻¹ (Definition, search.PEAK_TOL/PEAK_TOL_REL)
        np.testing.assert_allclose(search.peak_tolerance([1000.0, 3000.0]), [10.0, 18.0])

    def test_same_peak_criteria_for_sample_and_library(self):
        # verrauschtes Spektrum als Probe und als Referenz: gleiche Bandensuche (auch S/N ≥ 10) auf beiden Seiten,
        # also gleiche Bandenlisten und HQI 100 (Definition: alle Banden entsprechen sich)
        from tempfile import TemporaryDirectory
        y = model("pet") + 0.05 + np.random.default_rng(9).normal(0, 0.004, len(X))
        with TemporaryDirectory() as tmp:
            lib = LB.Libraries(Path(tmp)).create("Rauschen")
            lib.add(Spectrum("PET verrauscht", X, y, "A"))
            q = LB.prep(X, y, "A")
            v = np.isfinite(q)
            mine = [p["x"] for p in peaks.find(LB.GRID[v], q[v].astype(float), "A", search.PEAK_PARAMS)]
            np.testing.assert_allclose(lib.peaklists()[0][0], mine, atol=0.05)     # Bibliothek speichert float32
            r = search.search(q, [lib], "peaks", n=1)
            self.assertAlmostEqual(r["hits"][0]["hqi"], 100.0, places=6)

    def test_mixture_fractions_are_area_shares(self):
        lib = LB.model_library()
        y = 0.7 * model("pe") + 0.5 * model("calcite") + 0.02 + np.random.default_rng(3).normal(0, 0.003, len(X))
        q = LB.prep(X, y, "A")
        best = search.mixture(q, [lib], exclude=search.DEFAULT_EXCLUDE, max_components=2)["combos"][0]
        mask = search.region_mask(None, search.DEFAULT_EXCLUDE) & np.isfinite(q)
        # Flächenanteil_j = w_j · ΣL_j⁺ / Σ_k w_k · ΣL_k⁺ (über den gemeinsamen Bereich), unabhängig nachgerechnet
        areas = []
        for c in best["components"]:
            i = lib.index(c["id"])
            L = lib.G[i].astype(float)
            m = mask & np.isfinite(L)
            areas.append(c["weight"] * float(np.sum(np.clip(L[m], 0, None))))
        for c, a in zip(best["components"], areas):
            self.assertEqual(c["frac_kind"], "area")
            self.assertAlmostEqual(c["frac"], a / sum(areas), places=5)

    def test_nnls_small_matches_scipy(self):
        try:
            from scipy.optimize import nnls
        except ImportError:
            self.skipTest("scipy nicht installiert (nur für diese Vergleichsrechnung)")
        rng = np.random.default_rng(4)
        for _ in range(20):
            A = rng.normal(0, 1, (60, 4))
            b = A @ np.array([1.0, -0.5, 0.3, 0.0]) + rng.normal(0, 0.1, 60)
            w, _gain = search._nnls_small(A.T @ A, A.T @ b)
            w_ref, _ = nnls(A, b)
            np.testing.assert_allclose(w, w_ref, atol=1e-8)


# ----------------------------------------------------------------------------- 9 S/N
class SnrTest(unittest.TestCase):
    def test_sigma_is_standard_deviation_of_white_noise(self):
        # weisses Rauschen σ = 0,01: Schätzung im Mittel über 8 Zufallsfolgen innerhalb ±5 % (gemessen 0,975–0,998)
        for h in (0.5, 1.0, 2.0, 4.0):
            x = np.arange(600.0, 4000.0 + 1e-9, h)
            r = [quality.assess(x, 0.05 + np.random.default_rng(s).normal(0, 0.01, len(x)), "A")["sigma"] / 0.01
                 for s in range(8)]
            self.assertAlmostEqual(float(np.mean(r)), 1.0, delta=0.05, msg=h)

    def test_snr_is_band_height_over_sigma(self):
        # eine Bande, Höhe 1, FWHM 40 cm⁻¹, Rauschen σ = 0,01: S/N = 1/0,01 = 100; der 12-cm⁻¹-Mittelwert senkt die
        # Höhe um ≈ 2 % (Varianz des Gauss 17,0² + Rechteck 13²/12) -> erwartet 98 ± 8
        y = gauss(X, 1700, 1.0, 40) + 0.05 + np.random.default_rng(7).normal(0, 0.01, len(X))
        q = quality.assess(X, y, "A")
        self.assertAlmostEqual(q["snr"], 98.0, delta=8)
        self.assertAlmostEqual(q["signal"], 0.98, delta=0.02)


# ----------------------------------------------------------------------------- 10 Einheiten beim Einlesen
class UnitsTest(unittest.TestCase):
    def test_table_without_units_guessed_with_warning_and_override(self):
        x = np.arange(400.0, 4000.0, 4.0)
        rows = "\n".join(f"{a:.1f},{b:.5f}" for a, b in zip(x, 0.1 + gauss(x, 1700, 0.5, 20)))
        sp = load_bytes(rows.encode(), "ohne.csv")[0]
        kinds = {w["kind"] for w in sp.meta.get("warnings", [])}
        self.assertEqual(kinds, {"guess_x", "guess_y"})
        self.assertEqual((sp.yunit, sp.meta["x_unit"]), ("A", "cm-1 (geraten)"))
        sp2 = load_bytes(rows.encode(), "ohne.csv", {"xunit": "cm-1", "yunit": "A"})[0]
        self.assertFalse(sp2.meta.get("warnings"))
        self.assertEqual(sp2.meta["read_opts"], {"xunit": "cm-1", "yunit": "A"})
        with self.assertRaises(ReadError):
            load_bytes(rows.encode(), "ohne.csv", {"xunit": "parsec"})

    def test_micrometre_rule_and_declared_header(self):
        um = np.linspace(2.5, 25.0, 400)                    # 4000–400 cm⁻¹ als Wellenlänge
        rows = "\n".join(f"{a:.5f},{b:.4f}" for a, b in zip(um, 0.2 + 0.0 * um))
        sp = load_bytes(rows.encode(), "um.csv")[0]
        self.assertAlmostEqual(sp.x.max(), 4000.0, places=1)          # 10⁴/2,5
        self.assertTrue(any(w["kind"] == "guess_x" and w["unit"] == "um" for w in sp.meta["warnings"]))
        sp2 = load_bytes(("Wellenzahl [cm-1],Absorbanz\n" + rows).encode(), "decl.csv")[0]
        self.assertFalse(sp2.meta.get("warnings"), "deklarierte Einheiten: kein Hinweis")
        self.assertAlmostEqual(sp2.x.max(), 25.0, places=3)

    def test_spc_fxtype(self):
        y = 0.1 + gauss(np.linspace(600, 4000, 500), 1700, 0.5, 20)
        nm = load_bytes(spc(2500.0, 25000.0, y, fxtype=3), "nm.spc")[0]       # nm -> cm⁻¹ = 10⁷/nm
        self.assertAlmostEqual(nm.x.max(), 4000.0, places=3)
        self.assertAlmostEqual(nm.x.min(), 400.0, places=3)
        um = load_bytes(spc(2.5, 25.0, y, fxtype=2), "um.spc")[0]
        self.assertAlmostEqual(um.x.max(), 4000.0, places=3)
        with self.assertRaises(ReadError):
            load_bytes(spc(0.0, 10.0, y, fxtype=4), "zeit.spc")             # 4 = Sekunden: kein IR-Spektrum
        anyx = load_bytes(spc(600.0, 4000.0, y, fxtype=0), "beliebig.spc")[0]
        self.assertTrue(any(w["kind"] == "guess_x" for w in anyx.meta["warnings"]))
        t = load_bytes(spc(600.0, 4000.0, 0.5 + 0.0 * y, fytype=128), "t.spc")[0]
        self.assertEqual(t.yunit, "T")
        self.assertAlmostEqual(float(t.y[0]), 50.0, places=4)              # Bruchteil -> %


# ----------------------------------------------------------------------------- 11 Open Specy: gespeicherte Einheit
class OpenSpecyUnitTest(unittest.TestCase):
    def test_stored_unit(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import build_openspecy as B
        self.assertEqual(B.unit_column({"spectrum_type": 0, "intensity_units": 0}), "intensity_units")
        self.assertIsNone(B.unit_column({"spectrum_type": 0}))
        self.assertEqual([B.stored_unit(t) for t in ("absorbance", "Transmittance", "reflectance", "", None)],
                         ["A", "T", "R", None, None])


if __name__ == "__main__":
    unittest.main()
