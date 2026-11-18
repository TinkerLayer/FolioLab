"""MI-01: Wasserscheide trennt sich berührende Scheiben; Zählung stimmt."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "sdk" / "python"))

from mikro import watershed as WS  # noqa: E402
from mikro.label import label  # noqa: E402


def discs(centres, r, shape=(120, 200)):
    yy, xx = np.mgrid[: shape[0], : shape[1]]
    m = np.zeros(shape, bool)
    for cy, cx in centres:
        m |= (yy - cy) ** 2 + (xx - cx) ** 2 <= r * r
    return m


class Watershed(unittest.TestCase):
    def test_edt_exact(self):
        m = np.zeros((41, 41), bool)
        m[5:36, 5:36] = True
        d = WS.edt(m)
        self.assertAlmostEqual(d[20, 20], 16.0)                     # Mitte: 16 Pixel bis zum ersten Hintergrundpixel
        yy, xx = np.mgrid[:41, :41]
        c = discs([(20, 20)], 15, (41, 41))
        dc = WS.edt(c)
        self.assertAlmostEqual(dc[20, 20], np.sqrt(226), places=9)   # nächstes Hintergrundpixel bei (15, 1)
        self.assertTrue(np.all(dc[~c] == 0))

    def test_two_touching_discs(self):
        m = discs([(60, 70), (60, 104)], 20)                        # Abstand 34 < 2r: überlappen
        self.assertEqual(label(m)[1], 1)
        out, info = WS.watershed(m, h=1.0)
        L, n = label(out)
        self.assertEqual(n, 2)
        self.assertEqual(info["markers"], 2)
        areas = sorted(np.bincount(L.ravel())[1:])
        self.assertAlmostEqual(areas[0] / areas[1], 1.0, delta=0.05)
        cut = np.nonzero(m & ~out)[1]                               # Trennlinie in der Mitte
        self.assertAlmostEqual(float(np.median(cut)), 87.0, delta=1.5)
        self.assertLess(info["lines"], 40)

    def test_counts_and_single_objects_kept(self):
        m = discs([(30, 30), (30, 62), (30, 94), (90, 150)], 18)    # drei in einer Kette + ein einzelnes
        out, _ = WS.watershed(m, h=1.0)
        self.assertEqual(label(out)[1], 4)
        single = discs([(60, 100)], 25)
        out1, info1 = WS.watershed(single, h=1.0)
        self.assertEqual(label(out1)[1], 1)
        self.assertEqual(info1["lines"], 0)

    def test_h_controls_merging(self):
        m = discs([(60, 80), (60, 104)], 20)                         # starke Überlappung, flacher Sattel
        self.assertEqual(label(WS.watershed(m, h=0.5)[0])[1], 2)
        self.assertEqual(label(WS.watershed(m, h=15)[0])[1], 1)

    def test_protocol_step_and_report(self):
        import base64
        import io
        import matplotlib
        matplotlib.use("Agg")
        from PIL import Image
        from mikro import bundle, ops as OP
        from mikro.imageio import load_bytes
        self.assertEqual(OP.OPS["watershed"]["needs"], "binary")
        img = (discs([(60, 70), (60, 104)], 20) * 200 + 20).astype(np.uint8)
        buf = io.BytesIO()
        Image.fromarray(img).save(buf, format="PNG")
        raw = buf.getvalue()
        st = load_bytes(raw, "zwei.png")
        pipe = [{"op": "threshold", "method": "otsu", "dark": True}, {"op": "watershed", "h": 1.0}]
        p = OP.apply(st, pipe)
        self.assertEqual(label(p.stack.data[0] > 0)[1], 2)
        self.assertIn("h = 1,0 px", "; ".join(p.steps))
        state = {"pipeline": pipe, "particles": {"size_min": 0, "size_in_pixels": True}}
        b = bundle.build([(st, raw, state)], {"items": [{"name": "zwei.png", "state": state}]}, "de")
        tex = "".join(base64.b64decode(v).decode("utf-8") for k, v in b["files"].items() if k.endswith(".tex"))
        bib = base64.b64decode(b["files"]["refs.bib"]).decode("utf-8")
        self.assertIn("Wasserscheide", tex)
        self.assertIn("vincent1991", bib)
        tex.encode("latin-1")


if __name__ == "__main__":
    unittest.main()
