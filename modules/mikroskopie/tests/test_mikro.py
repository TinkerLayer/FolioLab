"""Mikroskopie-Modul: Markierung, Schwellen, Bearbeitung, Messung, Partikel, Dateien, Bericht, Server.

Start:  python -m unittest discover -s tests   (im Ordner modules/mikroskopie)
"""
import base64
import io
import json
import math
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "sdk" / "python"))

from mikro import bundle, measure, ops, threshold  # noqa: E402
from mikro.imageio import Calib, Stack, load_bytes, sample_image  # noqa: E402
from mikro.label import fill_holes, label  # noqa: E402


def flood_count(mask, conn):
    """Langsame Referenz: Anzahl Komponenten per Flutfuellung."""
    H, W = mask.shape
    seen = np.zeros_like(mask, bool)
    nb = [(-1, 0), (1, 0), (0, -1), (0, 1)] + ([(-1, -1), (-1, 1), (1, -1), (1, 1)] if conn == 8 else [])
    n = 0
    for y in range(H):
        for x in range(W):
            if mask[y, x] and not seen[y, x]:
                n += 1
                st = [(y, x)]
                seen[y, x] = True
                while st:
                    cy, cx = st.pop()
                    for dy, dx in nb:
                        ny, nx = cy + dy, cx + dx
                        if 0 <= ny < H and 0 <= nx < W and mask[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True
                            st.append((ny, nx))
    return n


def disk(H, W, cx, cy, r):
    yy, xx = np.mgrid[0:H, 0:W]
    return (xx + 0.5 - cx) ** 2 + (yy + 0.5 - cy) ** 2 <= r * r


def gray_stack(img, bitdepth=8, calib=None, name="t.tif"):
    return Stack(name=name, data=np.asarray(img, np.float32)[None], kind="gray", bitdepth=bitdepth, calib=calib or Calib())


class LabelTest(unittest.TestCase):
    def test_against_flood_fill(self):
        rng = np.random.default_rng(3)
        for conn in (4, 8):
            for _ in range(6):
                m = rng.random((40, 50)) < 0.45
                lab, n = label(m, conn)
                self.assertEqual(n, flood_count(m, conn))
                self.assertEqual(set(np.unique(lab[m])), set(range(1, n + 1)))
                self.assertTrue((lab[~m] == 0).all())

    def test_fill_holes(self):
        m = np.zeros((20, 20), bool)
        m[4:16, 4:16] = True
        m[8:12, 8:12] = False          # Loch
        m[0:3, 0:3] = False
        f = fill_holes(m)
        self.assertTrue(f[8:12, 8:12].all())
        self.assertFalse(f[0, 0])      # Hintergrund am Rand bleibt


class ThresholdTest(unittest.TestCase):
    def test_bimodal(self):
        rng = np.random.default_rng(1)
        v = np.concatenate([rng.normal(60, 8, 20000), rng.normal(180, 8, 8000)]).clip(0, 255).round()
        for m in ("default", "isodata", "otsu", "li", "huang", "intermodes", "minimum", "mean", "moments"):
            r = threshold.auto_range(v, 8, m, dark=True)
            self.assertTrue(80 <= r["value"] <= 170, f"{m}: {r['value']}")
            self.assertEqual(r["hi"], 255)
        light = threshold.auto_range(v, 8, "otsu", dark=False)
        self.assertEqual(light["lo"], 0)
        self.assertLess(light["hi"], 180)

    def test_all_methods_run_on_16bit(self):
        raw, name = sample_image()
        st = load_bytes(raw, name)
        for m in threshold.METHODS:
            r = threshold.auto_range(st.data[0], 16, m, dark=True)
            self.assertTrue(st.data.min() <= r["value"] <= st.data.max(), m)


class OpsTest(unittest.TestCase):
    def test_every_op_keeps_shape(self):
        img = (np.arange(30 * 40).reshape(30, 40) % 251).astype(np.float32)
        st = gray_stack(img)
        for op, d in ops.OPS.items():
            step = {"op": op, **{p["key"]: p["default"] for p in d["params"]}}
            if d["needs"] == "rgb":
                continue
            if op == "crop":
                step.update(x=5, y=6, w=10, h=8)
            pl = [{"op": "threshold", "method": "otsu", "dark": True}, step] if d["needs"] == "binary" else [step]
            p = ops.apply(st, pl)
            exp = (8, 10) if op == "crop" else (40, 30) if op == "rotate" else (30, 40)
            self.assertEqual(p.stack.data.shape[1:], exp, op)
            self.assertTrue(np.isfinite(p.stack.data).all(), op)
            self.assertTrue(p.steps and isinstance(p.steps[-1], str))

    def test_rgb_ops(self):
        rgb = np.zeros((1, 10, 12, 3), np.uint8)
        rgb[..., 0] = 200
        st = Stack(name="c.png", data=rgb, kind="rgb", bitdepth=24)
        self.assertEqual(ops.apply(st, [{"op": "channel", "c": "r"}]).stack.data[0, 0, 0], 200)
        self.assertEqual(ops.apply(st, [{"op": "gray"}]).stack.kind, "gray")

    def test_errors_are_german_and_name_the_step(self):
        st = gray_stack(np.zeros((5, 5)))
        with self.assertRaises(ops.OpError) as cm:
            ops.apply(st, [{"op": "fill"}])
        self.assertIn("Schritt 1", str(cm.exception))
        self.assertIn("Binär", str(cm.exception))

    def test_background_flattens(self):
        yy, xx = np.mgrid[0:120, 0:160]
        img = 50 + 0.5 * xx + 200 * disk(120, 160, 80, 60, 6)
        p = ops.apply(gray_stack(img, 16), [{"op": "background", "radius": 20}])
        out = p.stack.data[0]
        bg = out[~disk(120, 160, 80, 60, 12)]
        self.assertLess(bg.std(), 3)
        self.assertGreater(out[60, 80], 150)


class MeasureTest(unittest.TestCase):
    def test_disk_and_rect(self):
        cal = Calib(0.5, 0.5, "µm")
        m = disk(200, 200, 60, 60, 20)
        m[120:160, 100:180] = True
        res = measure.particles(m, None, cal, {"exclude_edges": True})
        rows = sorted(res["rows"], key=lambda r: r["Area"])
        self.assertEqual(len(rows), 2)
        d, r = rows[0], rows[1]
        self.assertAlmostEqual(d["Area"], math.pi * 100, delta=6)          # r = 10 µm
        self.assertAlmostEqual(d["ECD"], 20, delta=0.3)
        self.assertGreater(d["Circ."], 0.85)
        self.assertAlmostEqual(r["Area"], 800, delta=0.01)                 # 40 µm x 20 µm
        self.assertAlmostEqual(r["Feret"], math.hypot(39.5, 19.5), delta=1.0)
        self.assertAlmostEqual(r["AR"], 2.0, delta=0.1)

    def test_edges_size_and_circularity_filters(self):
        m = disk(100, 100, 50, 50, 10) | disk(100, 100, 2, 50, 8)
        m[80:84, 10:60] = True                                             # duenner Balken
        self.assertEqual(measure.particles(m, None, Calib(), {"exclude_edges": True})["summary"]["Count"], 2)
        self.assertEqual(measure.particles(m, None, Calib(), {"exclude_edges": False})["summary"]["Count"], 3)
        self.assertEqual(measure.particles(m, None, Calib(), {"circ_min": 0.6})["summary"]["Count"], 1)
        self.assertEqual(measure.particles(m, None, Calib(), {"size_min": 250})["summary"]["Count"], 1)

    def test_roi_measure(self):
        img = np.zeros((50, 60), np.float32)
        img[10:20, 10:30] = 100
        cal = Calib(2, 2, "µm")
        r = measure.measure(img, {"type": "rect", "x": 10, "y": 10, "w": 20, "h": 10}, cal)
        self.assertEqual(r["Pixels"], 200)
        self.assertAlmostEqual(r["Area"], 800)
        self.assertAlmostEqual(r["Mean"], 100)
        ln = measure.measure(img, {"type": "line", "x1": 0, "y1": 5, "x2": 30, "y2": 5}, cal)
        self.assertAlmostEqual(ln["Length"], 60)
        self.assertEqual(ln["Angle"], 0.0)
        self.assertFalse(math.copysign(1, ln["Angle"]) < 0)
        ov = measure.measure(img, {"type": "oval", "x": 0, "y": 0, "w": 40, "h": 40}, Calib())
        self.assertAlmostEqual(ov["Pixels"], math.pi * 400, delta=20)


class FileTest(unittest.TestCase):
    def test_sample_calibration_roundtrip(self):
        raw, name = sample_image()
        st = load_bytes(raw, name)
        self.assertEqual((st.width, st.height, st.bitdepth, st.kind), (768, 576, 16, "gray"))
        self.assertAlmostEqual(st.calib.pw, 0.25)
        self.assertEqual(st.calib.unit, "µm")

    def test_png_and_rgb_and_garbage(self):
        buf = io.BytesIO()
        Image.fromarray(np.full((8, 9, 3), (10, 20, 30), np.uint8)).save(buf, "PNG")
        st = load_bytes(buf.getvalue(), "f.png")
        self.assertEqual((st.kind, st.width, st.height), ("rgb", 9, 8))
        buf = io.BytesIO()
        Image.fromarray(np.full((8, 9), 7, np.uint8)).save(buf, "PNG")
        self.assertEqual(load_bytes(buf.getvalue(), "g.png").kind, "gray")
        with self.assertRaises(ValueError):
            load_bytes(b"kein Bild", "x.tif")

    def test_stack(self):
        frames = [Image.fromarray(np.full((6, 7), v, np.uint16)) for v in (100, 200, 300)]
        buf = io.BytesIO()
        frames[0].save(buf, "TIFF", save_all=True, append_images=frames[1:])
        st = load_bytes(buf.getvalue(), "s.tif")
        self.assertEqual(st.slices, 3)
        p = ops.apply(st, [{"op": "zproject", "mode": "max"}])
        self.assertEqual(p.stack.slices, 1)
        self.assertEqual(p.stack.data.max(), 300)


PIPE = [{"op": "background", "radius": 30}, {"op": "gauss", "sigma": 1.5},
        {"op": "threshold", "method": "otsu", "dark": True}, {"op": "fill"}]
STATE = {"pipeline": PIPE, "particles": {"size_min": 2}, "scalebar": {"pos": "bl", "len": 20, "box": True},
         "rois": [{"type": "rect", "x": 50, "y": 60, "w": 200, "h": 150, "name": "Feld A"},
                  {"type": "line", "x1": 100, "y1": 300, "x2": 600, "y2": 320, "name": "L1"}]}


class ScaleBarTest(unittest.TestCase):
    def test_options(self):
        from mikro import charts as C
        self.assertIsNone(C.scalebar_opts(False))
        self.assertIsNone(C.scalebar_opts({"show": False, "pos": "tl"}))
        self.assertEqual(C.scalebar_opts(True), C.SCALEBAR_DEFAULT)
        self.assertEqual(C.scalebar_opts(None), C.SCALEBAR_DEFAULT)
        o = C.scalebar_opts({"pos": "xx", "len": "0", "thick": 99, "font": "abc", "color": "black", "box": 1})
        self.assertEqual((o["pos"], o["len"], o["thick"], o["font"], o["color"], o["box"]),
                         ("br", None, 10, C.SCALEBAR_DEFAULT["font"], "black", True))
        self.assertEqual(C.scalebar_opts({"len": 50})["len"], 50)

    def test_geometry(self):
        from mikro import charts as C
        cal = Calib(0.25, 0.25, "µm")
        g = C.scalebar_geom(800, 600, cal, C.scalebar_opts(True))
        self.assertEqual(g["L"], 20)                                  # ein Fünftel von 200 µm, gerundet
        x, y, w, h = g["bar"]
        self.assertAlmostEqual(w, 80)
        self.assertAlmostEqual(x + w, 800 - 0.04 * 600)               # rechts bündig mit Rand
        self.assertAlmostEqual(y + h, 600 - 0.04 * 600)               # unten bündig
        self.assertEqual(g["text"], "20 µm")
        g = C.scalebar_geom(800, 600, cal, C.scalebar_opts({"pos": "tl", "len": 50, "label": False}))
        x, y, w, h = g["bar"]
        self.assertAlmostEqual((x, y, w), (24, 24, 200))
        g = C.scalebar_geom(800, 600, cal, C.scalebar_opts({"len": 2.5}), lang="de")
        self.assertEqual(g["text"], "2,5 µm")

    def test_figure_draws_bar_where_asked(self):
        from mikro import charts as C
        rgb = np.full((300, 400, 3), 128, np.uint8)
        cal = Calib(0.5, 0.5, "µm")

        def pix(sb):
            f = C.fig_image(rgb, cal, "de", scalebar=sb, width_in=4)
            f.canvas.draw()
            a = np.asarray(f.canvas.buffer_rgba())[..., :3].astype(int)
            C.plt.close(f)
            return a
        off = pix(False)
        H, W = off.shape[:2]
        corner = lambda a, q: a[H // 2:, W // 2:] if q == "br" else a[:H // 2, :W // 2]  # noqa: E731
        br = pix({"color": "white"})
        self.assertGreater(np.abs(corner(br, "br") - corner(off, "br")).max(), 100)
        self.assertEqual(np.abs(corner(br, "tl") - corner(off, "tl")).max(), 0)
        tl = pix({"pos": "tl", "color": "black", "box": True})
        self.assertGreater(np.abs(corner(tl, "tl") - corner(off, "tl")).max(), 100)
        self.assertEqual(np.abs(corner(tl, "br") - corner(off, "br")).max(), 0)
        self.assertEqual(np.abs(pix({"show": False}) - off).max(), 0)
        f = C.fig_image(rgb, Calib(), "de")                         # ohne Kalibrierung kein Balken
        self.assertEqual(len(f.axes[0].patches), 0)
        C.plt.close(f)


class BundleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw, cls.name = sample_image()
        cls.st = load_bytes(cls.raw, cls.name)
        cls.b = bundle.build([(cls.st, cls.raw, STATE)], {"items": [{"name": cls.name, "state": STATE}]}, "de")

    def test_content(self):
        b = self.b
        kinds = [i["kind"] for i in b["items"]]
        for k in ("figure", "table", "data", "citation", "text", "values"):
            self.assertIn(k, kinds)
        figs = {i["id"] for i in b["items"] if i["kind"] == "figure"}
        self.assertTrue({"bild", "partikel", "histogramm", "groessen", "form", "profil1"} <= figs)
        vals = b["files"]["values.tex"] if "values.tex" in b["files"] else None
        self.assertIsNotNone(vals)
        txt = base64.b64decode(b["files"]["text-methodik.tex"]).decode() if isinstance(b["files"]["text-methodik.tex"], str) else b["files"]["text-methodik.tex"]
        self.assertIn("\\cite{otsu1979}", txt)
        self.assertNotIn("×", txt)                                         # pdfLaTeX-sicher

    def test_rebuild_keeps_slug_and_switches_language(self):
        src = self.b["source"]
        files = {k: base64.b64decode(v) for k, v in src["files"].items()}
        items = [(load_bytes(files[i["name"]], i["name"]), files[i["name"]], i["state"]) for i in src["request"]["items"]]
        b2 = bundle.build(items, {**src["request"]}, "en")
        self.assertEqual(b2["slug"], self.b["slug"])
        caps = [i["caption"] for i in b2["items"] if i["kind"] == "figure"]
        self.assertTrue(any("particles" in c for c in caps))

    def test_comparison(self):
        b = bundle.build([(self.st, self.raw, STATE), (self.st, self.raw, {**STATE, "rois": []})], {"items": []}, "de",
                         include={"figures": False, "text": False})
        ids = {i.get("id") for i in b["items"]}
        self.assertIn("vergleich", ids)


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mikro import server as S
        cls.tmp = TemporaryDirectory()
        S.STATE = S.State(Path(cls.tmp.name))
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.tmp.cleanup()

    def post(self, path, obj=None, raw=None, origin=None):
        r = urllib.request.Request(self.base + path, data=raw if raw is not None else json.dumps(obj or {}).encode(), method="POST")
        if origin:
            r.add_header("Origin", origin)
        try:
            with urllib.request.urlopen(r) as f:
                return f.status, f.headers, f.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def test_flow(self):
        meta = json.loads(urllib.request.urlopen(self.base + "/api/meta").read())
        self.assertEqual(len(meta["methods"]), 13)
        c, _, b = self.post("/api/sample")
        iid = json.loads(b)["id"]
        c, h, b = self.post("/api/pixels", {"id": iid, "pipeline": PIPE[:2]})
        self.assertEqual((c, h["X-Kind"], len(b)), (200, "gray", 768 * 576 * 4))
        c, _, b = self.post("/api/particles", {"id": iid, "pipeline": PIPE, "params": {"size_min": 2}})
        self.assertEqual(c, 200)
        self.assertGreater(json.loads(b)["count"], 30)
        c, _, b = self.post("/api/particles", {"id": iid, "pipeline": PIPE[:2], "params": {}})
        self.assertEqual(c, 400)
        c, _, b = self.post("/api/measure", {"id": iid, "pipeline": [], "rois": [{"type": "image"}]})
        self.assertEqual(json.loads(b)["rows"][0]["Label"], "Ganzes Bild")
        self.assertEqual(self.post("/api/process", {"id": iid, "pipeline": []}, origin="http://example.com")[0], 403)
        self.assertEqual(self.post("/api/load?name=x.tif", raw=b"xx")[0], 400)
        c, _, b = self.post("/api/export", {"id": iid, **STATE})
        self.assertIn("partikel.csv", json.loads(b)["files"])


if __name__ == "__main__":
    unittest.main()
