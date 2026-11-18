"""Known-answer tests for the scientific fixes of version 1.3.0 (non-square pixels, TIFF ResolutionUnit, edge
correction, outer perimeter, Q0/Q3 D values, threshold methods, references).

Each assertion names its expected value and where it comes from (analytic result, TIFF 6.0 rule or an independent
reference such as numpy's Hazen percentile)."""
from __future__ import annotations

import base64
import io
import math
import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image
from PIL.TiffImagePlugin import ImageFileDirectory_v2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "sdk" / "python"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")

from mikro import bundle, measure as M, ops, threshold as TH, watershed as WS  # noqa: E402
from mikro import compare as CMP  # noqa: E402
from mikro.imageio import Calib, load_bytes  # noqa: E402


def contour_length(m, pw, ph):
    """Length of the level-½ contour of a padded mask (pixel centres at ((i + ½)·pw, (j + ½)·ph)) via contourpy."""
    import contourpy
    p = np.pad(m.astype(float), 1)
    H, W = p.shape
    x = (np.arange(W) - 0.5) * pw
    y = (np.arange(H) - 0.5) * ph
    L = 0.0
    for line in contourpy.contour_generator(x, y, p).lines(0.5):
        d = np.diff(line, axis=0)
        L += float(np.hypot(d[:, 0], d[:, 1]).sum())
    return L


def tiff(tags: dict, desc: str | None = None) -> bytes:
    ifd = ImageFileDirectory_v2()
    if desc is not None:
        ifd[270] = desc
    for k, v in tags.items():
        ifd[k] = v
    buf = io.BytesIO()
    Image.fromarray(np.zeros((6, 8), np.uint8)).save(buf, format="TIFF", tiffinfo=ifd)
    return buf.getvalue()


class TiffResolution(unittest.TestCase):
    """TIFF 6.0 tag 296 ResolutionUnit: 1 none, 2 inch (default when absent), 3 centimetre."""

    def test_inch_and_separate_x_y(self):
        st = load_bytes(tiff({282: 2540.0, 283: 1270.0, 296: 2}), "inch.tif")
        # 2540 px/inch -> 25400 µm / 2540 = 10 µm; 1270 px/inch -> 20 µm
        self.assertEqual(st.calib.unit, "µm")
        self.assertAlmostEqual(st.calib.pw, 10.0, places=9)
        self.assertAlmostEqual(st.calib.ph, 20.0, places=9)
        self.assertFalse(st.calib.square_assumed)
        self.assertIn("Zoll", st.info["calib_source"])

    def test_centimetre(self):
        st = load_bytes(tiff({282: 1000.0, 283: 1000.0, 296: 3}), "cm.tif")
        # 1000 px/cm -> 10000 µm / 1000 = 10 µm
        self.assertEqual((st.calib.unit, round(st.calib.pw, 9), round(st.calib.ph, 9)), ("µm", 10.0, 10.0))
        self.assertIn("px/cm", st.info["calib_source"])

    def test_no_absolute_unit_is_no_scale(self):
        st = load_bytes(tiff({282: 72.0, 283: 72.0, 296: 1}), "none.tif")
        self.assertFalse(st.calib.calibrated)                  # ResolutionUnit 1: no absolute unit
        self.assertEqual(st.info["calib_source"], "")

    def test_print_dpi_is_no_scale(self):
        # 72/96/300 dpi are what cameras and image programs write as a print setting; 72 dpi would mean 352.8 µm/px
        for dpi in (72.0, 96.0, 300.0):
            for tags in ({282: dpi, 283: dpi, 296: 2}, {282: dpi, 283: dpi}):
                st = load_bytes(tiff(tags), "print.tif")
                self.assertFalse(st.calib.calibrated, (dpi, tags))

    def test_imagej_description_wins(self):
        # ImageJ writes px per description unit and ResolutionUnit 1
        st = load_bytes(tiff({282: 4.0, 283: 2.0, 296: 1}, "ImageJ=1.54\nunit=micron\n"), "ij.tif")
        self.assertEqual((st.calib.unit, st.calib.pw, st.calib.ph), ("µm", 0.25, 0.5))

    def test_only_x_resolution_assumes_square_and_says_so(self):
        st = load_bytes(tiff({282: 1000.0, 296: 3}), "x.tif")
        if 283 in Image.open(io.BytesIO(tiff({282: 1000.0, 296: 3}))).tag_v2:
            self.skipTest("Pillow writes YResolution on its own")
        self.assertAlmostEqual(st.calib.ph, st.calib.pw)
        self.assertTrue(st.calib.square_assumed)
        self.assertIn("quadratische Pixel angenommen", st.info["calib_source"])

    def test_calib_from_dict_without_ph_is_square_assumed(self):
        c = Calib.from_dict({"pw": 0.3, "unit": "µm"})
        self.assertEqual((c.ph, c.square_assumed), (0.3, True))
        self.assertFalse(Calib.from_dict({"pw": 0.3, "ph": 0.6, "unit": "µm"}).square_assumed)


class NonSquarePixels(unittest.TestCase):
    """pw = 0.5 µm, ph = 2 µm: a 40 × 20 px block is 20 µm wide and 40 µm high."""

    def setUp(self):
        self.cal = Calib(0.5, 2.0, "µm")
        self.m = np.zeros((100, 120), bool)
        self.m[30:50, 30:70] = True

    def test_rectangle_exact(self):
        r = M.particles(self.m, None, self.cal)["rows"][0]
        self.assertAlmostEqual(r["Area"], 800.0, places=9)                  # 20 µm × 40 µm
        self.assertAlmostEqual(r["ECD"], 2 * math.sqrt(800 / math.pi), places=9)
        self.assertAlmostEqual(r["Feret"], math.hypot(20, 40), places=9)    # diagonal of the outer pixel edges
        self.assertAlmostEqual(r["MinFeret"], 20.0, places=9)
        # estimator: 2(w−1)·pw + 2(h−1)·ph + 4·½·|(pw, ph)| (straight steps, corners cut by half pixel diagonals)
        exp = 2 * 39 * 0.5 + 2 * 19 * 2.0 + 2 * math.hypot(0.5, 2.0)
        self.assertAlmostEqual(r["Perim."], exp, places=9)
        self.assertAlmostEqual(r["AR"], 2.0, places=6)                       # 40 µm / 20 µm
        self.assertAlmostEqual(r["Angle"], 90.0, places=6)                   # long axis along y
        self.assertAlmostEqual(r["Width"], 20.0)
        self.assertAlmostEqual(r["Height"], 40.0)

    def test_rotation_with_swapped_pixel_size_gives_same_values(self):
        a = M.particles(self.m, None, self.cal)["rows"][0]
        b = M.particles(np.rot90(self.m).copy(), None, Calib(2.0, 0.5, "µm"))["rows"][0]
        for k in ("Area", "Perim.", "ECD", "Feret", "MinFeret", "Major", "Minor", "Solidity", "Circ."):
            self.assertAlmostEqual(a[k], b[k], places=9, msg=k)

    def test_physical_disc_on_rectangular_pixels(self):
        # disc of radius R = 30 µm sampled with pw = 0.5, ph = 1.5 µm: an ellipse of 60 × 20 px semi-axes
        pw, ph, R = 0.5, 1.5, 30.0
        H, W = 80, 160
        yy, xx = np.mgrid[0:H, 0:W]
        m = ((xx + 0.5 - 80) * pw) ** 2 + ((yy + 0.5 - 40) * ph) ** 2 <= R * R
        r = M.particles(m, None, Calib(pw, ph, "µm"))["rows"][0]
        self.assertAlmostEqual(r["Area"], math.pi * R * R, delta=0.01 * math.pi * R * R)   # π R², 1 %
        self.assertAlmostEqual(r["ECD"], 2 * R, delta=0.01 * 2 * R)
        self.assertAlmostEqual(r["Major"], 2 * R, delta=0.02 * 2 * R)       # a circle: both axes 2R
        self.assertAlmostEqual(r["Minor"], 2 * R, delta=0.02 * 2 * R)
        self.assertAlmostEqual(r["Feret"], 2 * R, delta=0.04 * 2 * R)       # outer pixel edges: up to ~1 px more
        self.assertAlmostEqual(r["MinFeret"], 2 * R, delta=0.04 * 2 * R)
        # the perimeter estimator is the marching-squares contour at level ½ in calibrated coordinates; independent
        # reference: contourpy (matplotlib's contouring library) on the same mask with x·pw, y·ph
        self.assertAlmostEqual(r["Perim."], contour_length(m, pw, ph), places=6)
        # its digitisation bias grows with the pixel aspect ratio: +12.7 % here (3:1), +5.6 % for square pixels
        self.assertAlmostEqual(r["Perim."], 2 * math.pi * R, delta=0.15 * 2 * math.pi * R)

    def test_line_length_and_profile_scale(self):
        self.assertAlmostEqual(M.line_scale(self.cal, 10, 0), 0.5)          # along x: pw
        self.assertAlmostEqual(M.line_scale(self.cal, 0, 7), 2.0)           # along y: ph
        self.assertAlmostEqual(M.line_scale(self.cal, 3, 4), math.hypot(1.5, 8) / 5)
        img = np.zeros((50, 50), np.float32)
        ln = M.measure(img, {"type": "line", "x1": 0, "y1": 0, "x2": 30, "y2": 40}, self.cal)
        self.assertAlmostEqual(ln["Length"], math.hypot(15, 80))            # |(30·0.5, 40·2)|
        d, _ = M.sample_line(img, 0, 0, 30, 40)
        self.assertAlmostEqual(d[-1] * M.line_scale(self.cal, 30, 40), ln["Length"])

    def test_report_states_pixel_geometry(self):
        img = np.zeros((60, 80), np.uint8)
        img[20:40, 20:50] = 200
        buf = io.BytesIO()
        Image.fromarray(img).save(buf, format="PNG")
        raw = buf.getvalue()
        st = load_bytes(raw, "r.png")
        pipe = [{"op": "threshold", "method": "otsu", "dark": True}]
        for cal, de_txt in (({"pw": 0.5, "ph": 2.0, "unit": "µm"}, "nicht quadratisch"),
                            ({"pw": 0.5, "unit": "µm"}, "Pixelhöhe gleich Pixelbreite angenommen")):
            state = {"pipeline": pipe, "particles": {}, "calib": cal}
            b = bundle.build([(st, raw, state)], {"items": [{"name": "r.png", "state": state}]}, "de")
            txt = base64.b64decode(b["files"]["text-methodik.tex"]).decode("utf-8")
            self.assertIn(de_txt, txt)
            txt.encode("latin-1")


class OuterPerimeter(unittest.TestCase):
    def test_square_ring(self):
        # 30 × 30 px square with a 10 × 10 px hole, pixel size 1
        m = np.zeros((50, 50), bool)
        m[10:40, 10:40] = True
        m[20:30, 20:30] = False
        outer = 4 * 29 + 4 * math.sqrt(0.5)          # estimator on a 30 px square: 4(a−1) + 4·√½ = 118.83
        hole = 4 * 9 + 4 * math.sqrt(0.5)            # contour around the 10 px hole, same rule = 38.83
        r = M.particles(m, None, Calib())["rows"][0]
        self.assertAlmostEqual(r["Perim."], outer, places=9)                  # default: outer only
        self.assertAlmostEqual(r["Circ."], 4 * math.pi * 800 / outer ** 2, places=9)   # area without the hole
        t = M.particles(m, None, Calib(), {"perimeter": "total"})["rows"][0]
        self.assertAlmostEqual(t["Perim."], outer + hole, places=9)

    def test_disc_ring_equals_disc(self):
        yy, xx = np.mgrid[0:100, 0:100]
        r2 = (xx + 0.5 - 50) ** 2 + (yy + 0.5 - 50) ** 2
        ring = (r2 <= 400) & (r2 > 100)
        disc = r2 <= 400
        pr = M.particles(ring, None, Calib(0.5, 0.5, "µm"))["rows"][0]["Perim."]
        pd = M.particles(disc, None, Calib(0.5, 0.5, "µm"))["rows"][0]["Perim."]
        self.assertAlmostEqual(pr, pd, places=9)                            # outer contour of a ring = its disc

    def test_particle_inside_hole_keeps_its_own_perimeter(self):
        m = np.zeros((60, 60), bool)
        m[10:50, 10:50] = True
        m[15:45, 15:45] = False                                             # frame
        m[25:35, 25:35] = True                                              # island in the hole
        rows = sorted(M.particles(m, None, Calib())["rows"], key=lambda r: r["Area"])
        self.assertAlmostEqual(rows[0]["Perim."], 4 * 9 + 4 * math.sqrt(0.5), places=9)    # 10 px island
        self.assertAlmostEqual(rows[1]["Perim."], 4 * 39 + 4 * math.sqrt(0.5), places=9)   # 40 px frame, outer


def periodic_field(P=24):
    """One large 9 × 7 px and one small 3 × 3 px particle per P × P cell (no contact across cell borders)."""
    cell = np.zeros((P, P), bool)
    cell[3:10, 2:11] = True          # large: w = 9, h = 7, 63 px
    cell[15:18, 15:18] = True        # small: 9 px
    return np.tile(cell, (5, 5)), P


class EdgeCorrection(unittest.TestCase):
    """Averaged over all P² translations of a periodic field, the Miles–Lantuéjoul estimate is exact (Horvitz–Thompson):
    each particle copy is kept in exactly N(w, h) of the translations and then carries the weight |R|/N(w, h).
    Expected corrected count per type = |R| / P² (one particle of each type per cell); expected area fraction =
    (63 + 9)/P² (every foreground pixel counted)."""

    def _run(self, region=None, H=36, W=40):
        big, P = periodic_field()
        sums = {63: 0.0, 9: 0.0}
        raw = {63: 0, 9: 0}
        frac = 0.0
        reg_px = None
        for oy in range(P):
            for ox in range(P):
                win = big[oy:oy + H, ox:ox + W]
                res = M.particles(win, None, Calib(), {}, region)
                for r in res["rows"]:
                    sums[r["Pixels"]] += r["Weight"]
                    raw[r["Pixels"]] += 1
                frac += res["summary"]["AreaFraction"]
                reg_px = res["summary"]["RegionArea"]
        n = P * P
        return {k: v / n for k, v in sums.items()}, {k: v / n for k, v in raw.items()}, frac / n, reg_px, P

    def test_whole_image(self):
        corr, raw, frac, reg_px, P = self._run()
        exp = reg_px / P ** 2                                               # 1440 / 576 = 2.5 per type
        self.assertAlmostEqual(exp, 2.5)
        self.assertAlmostEqual(corr[63], exp, places=9)
        self.assertAlmostEqual(corr[9], exp, places=9)
        self.assertAlmostEqual(frac, 100 * 72 / 576, places=9)              # 12.5 %, edge particles included
        # without weights large particles are under-represented: (W−w−1)(H−h−1)/P² = 30·28/576 vs 36·32/576
        self.assertAlmostEqual(raw[63], 30 * 28 / 576, places=9)
        self.assertAlmostEqual(raw[9], 36 * 32 / 576, places=9)

    def test_oval_region(self):
        region = {"type": "oval", "x": 1.5, "y": 2.5, "w": 37, "h": 31}
        corr, raw, frac, reg_px, P = self._run(region)
        exp = reg_px / P ** 2
        self.assertAlmostEqual(corr[63], exp, places=9)
        self.assertAlmostEqual(corr[9], exp, places=9)
        self.assertAlmostEqual(frac, 100 * 72 / 576, places=9)
        self.assertLess(raw[63] / raw[9], 0.8)                              # bias of plain exclusion

    def test_weights_and_summary(self):
        m = np.zeros((100, 100), bool)
        m[30:50, 20:60] = True                                              # w = 40, h = 20
        m[0:10, 0:10] = True                                                # touches the corner
        res = M.particles(m, None, Calib())
        self.assertEqual(res["summary"]["Count"], 1)
        self.assertAlmostEqual(res["rows"][0]["Weight"], 10000 / (59 * 79), places=12)   # WH/((W−w−1)(H−h−1))
        self.assertAlmostEqual(res["summary"]["AreaFraction"], 100 * (800 + 100) / 10000, places=12)
        off = M.particles(m, None, Calib(), {"exclude_edges": False})
        self.assertEqual(off["summary"]["Count"], 2)
        self.assertTrue(all(r["Weight"] == 1.0 for r in off["rows"]))
        self.assertEqual(off["summary"]["EdgeCorrection"], "none")


class Quantiles(unittest.TestCase):
    def test_equal_weights_are_hazen(self):
        v = np.random.default_rng(5).lognormal(1, 0.5, 57)
        got = M.wquantile(v, np.ones_like(v), (0.1, 0.5, 0.9))
        ref = np.percentile(v, [10, 50, 90], method="hazen")                # Hyndman & Fan definition 5
        np.testing.assert_allclose(got, ref, rtol=0, atol=1e-12)

    def test_volume_weighting(self):
        # d = 1, 2, 10 with weights d³ = 1, 8, 1000: P = 0.5/1009, 5/1009, 509/1009 -> D50 = 2 + (504.5 − 5)/504·8
        self.assertAlmostEqual(M.wquantile([1, 2, 10], [1, 8, 1000], (0.5,))[0], 2 + 499.5 / 504 * 8, places=12)
        # scale invariance of the weights
        self.assertAlmostEqual(M.wquantile([1, 2, 10], [1e-9, 8e-9, 1e-6], (0.5,))[0], 2 + 499.5 / 504 * 8, places=9)

    def test_summary_q0_q3_and_comparison_alike(self):
        yy, xx = np.mgrid[0:200, 0:200]
        m = np.zeros((200, 200), bool)
        rs = [3, 4, 5, 6, 8, 10, 12]
        for i, r in enumerate(rs):
            cx, cy = 25 + (i % 4) * 50, 40 + (i // 4) * 80
            m |= (xx + 0.5 - cx) ** 2 + (yy + 0.5 - cy) ** 2 <= r * r
        s = M.particles(m, None, Calib(), {"exclude_edges": False})
        ecd = np.array([r["ECD"] for r in s["rows"]])
        sm = s["summary"]
        np.testing.assert_allclose([sm["D10"], sm["D50"], sm["D90"]], np.percentile(ecd, [10, 50, 90], method="hazen"), atol=1e-12)
        self.assertGreater(sm["Dv50"], sm["D50"])                          # volume weighting shifts to large sizes
        c = CMP.stats(ecd)                                                  # dataset path: same definition
        for k in ("D10", "D50", "D90", "Dv10", "Dv50", "Dv90"):
            self.assertAlmostEqual(c[k], sm[k], places=12, msg=k)


class ThresholdMethods(unittest.TestCase):
    def test_moments_two_level_image(self):
        # Tsai: a two-level image is reproduced exactly (z0 = 50, z1 = 200, p0 = 0.7) -> lower class = {50}
        h = np.zeros(256)
        h[50], h[200] = 700, 300
        self.assertEqual(TH.auto_level(h, "moments"), 50)

    def test_minimum_ignores_falling_start(self):
        # histogram falling from bin 0, then two equal Gaussian modes at 60 and 180: valley at 120
        i = np.arange(256, dtype=float)
        h = 4000 * np.exp(-i / 4) + 1000 * np.exp(-0.5 * ((i - 60) / 10) ** 2) + 1000 * np.exp(-0.5 * ((i - 180) / 10) ** 2)
        self.assertLessEqual(abs(TH.auto_level(h, "minimum") - 120), 3)
        self.assertLessEqual(abs(TH.auto_level(h, "intermodes") - 120), 3)

    def test_references_consistent(self):
        self.assertEqual(TH.UNVERIFIED, set())
        for refs in (TH.REFERENCES, WS.REFERENCES):
            for key, ref in refs.items():
                self.assertEqual(key[-4:], ref["year"], key)                # key year = cited year
        self.assertIn("soille2004", WS.REFS)
        self.assertEqual(TH.REFERENCES["tsai1985"]["pages"], "377--393")
        self.assertEqual(TH.REFERENCES["prewitt1966"]["volume"], "128")


class BackgroundName(unittest.TestCase):
    def test_named_for_what_it_is(self):
        for lang, word in (("de", "Graustufen-Öffnung"), ("en", "grey-scale opening")):
            d = ops.describe({"op": "background", "radius": 40}, lang)
            self.assertIn(word, d)
            self.assertNotIn("olling", d)
            self.assertIn(word, ops.OPS["background"][lang])


if __name__ == "__main__":
    unittest.main()
