"""TGA-04: Gasspektren-Serien, Gram-Schmidt-Kurve und Übergabe an das FTIR-Modul."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "sdk" / "python"))

from tga import egs as EG  # noqa: E402


class EGS(unittest.TestCase):
    def test_gram_schmidt_maximum(self):
        raw, truth = EG.synth(gas_peaks=((18.0, 2.5),))
        s = EG.load_bytes(raw, "serie.csv")
        self.assertEqual(s.Y.shape, (60, len(s.x)))
        gs = EG.gram_schmidt(s, k=5)
        self.assertAlmostEqual(float(s.t[np.argmax(gs)]), truth["t_max"], delta=0.7)
        self.assertLess(gs[:5].max(), 1e-9)                         # Hintergrund liegt im Basisraum
        two = EG.load_bytes(EG.synth(gas_peaks=((10.0, 1.5), (28.0, 1.5)))[0], "zwei.csv")
        g2 = EG.gram_schmidt(two)
        i1, i2 = int(np.argmax(g2[: len(g2) // 2])), len(g2) // 2 + int(np.argmax(g2[len(g2) // 2:]))
        self.assertAlmostEqual(float(two.t[i1]), 10.0, delta=0.8)
        self.assertAlmostEqual(float(two.t[i2]), 28.0, delta=0.8)

    def test_spectrum_and_chemigram(self):
        s = EG.load_bytes(EG.synth(gas_peaks=((18.0, 2.5),))[0], "serie.csv")
        sp = EG.spectrum_at(s, 18.0)
        self.assertAlmostEqual(float(s.x[np.argmax(sp["y"])]), 2348.0, delta=8)   # CO2-Bande
        self.assertLess(abs(sp["y"][s.x < 1000][:5]).max(), 1e-6)                  # Hintergrund abgezogen
        c = EG.chemigram(s, 2250, 2450)
        self.assertAlmostEqual(float(s.t[np.argmax(c)]), 18.0, delta=0.7)

    def test_transposed_and_jcamp(self):
        s = EG.load_bytes(EG.synth()[0], "a.csv")
        # transponiert
        rows = ["Wellenzahl;" + ";".join(f"{v:.3f}" for v in s.t)]
        rows += [f"{x:g};" + ";".join(f"{v:.6f}" for v in s.Y[:, j]) for j, x in enumerate(s.x)]
        s2 = EG.load_bytes("\n".join(rows).encode(), "b.txt")
        np.testing.assert_allclose(s2.Y, s.Y, atol=1e-6)
        # mehrere JCAMP-Blöcke
        jdx = "".join(EG.to_jcamp(s.x, s.Y[i], f"Gas {s.t[i]:.3f} min", {"$RETENTION TIME": f"{s.t[i]:.4f}"})
                      for i in range(len(s.t)))
        s3 = EG.load_bytes(jdx.encode(), "serie.jdx")
        np.testing.assert_allclose(s3.t, s.t, atol=1e-4)
        np.testing.assert_allclose(s3.Y, s.Y, atol=1e-5)

    def test_compressed_jcamp_reported(self):
        jdx = ""
        for i in range(3):
            jdx += (f"##TITLE=b{i}\n##$RETENTION TIME={i}\n##FIRSTX=4000\n##LASTX=3996\n##NPOINTS=3\n"
                    "##XYDATA=(X++(Y..Y))\n4000@A1j2\n##END=\n")
        with self.assertRaises(EG.EGSError) as cm:
            EG.load_bytes(jdx.encode(), "k.jdx")
        self.assertIn("komprimiert", str(cm.exception))

    def test_jcamp_opens_in_ftir(self):
        """Das übergebene Einzelspektrum liest der FTIR-Leser (gleiche Wellenzahlen und Werte)."""
        s = EG.load_bytes(EG.synth()[0], "a.csv")
        sp = EG.spectrum_at(s, 20.0)
        txt = EG.to_jcamp(sp["x"], sp["y"], "Gasspektrum 20 min")
        ftir_root = ROOT.parents[0] / "ftir"
        sys.path.insert(0, str(ftir_root))
        try:
            from ftir import readers as FR
        finally:
            sys.path.remove(str(ftir_root))
        out = FR.load_bytes(txt.encode("utf-8"), "gas.jdx")
        self.assertEqual(len(out), 1)
        f = out[0]
        o = np.argsort(f.x)
        np.testing.assert_allclose(f.x[o], sp["x"], atol=1e-3)
        np.testing.assert_allclose(f.y[o], sp["y"], atol=1e-5)
        self.assertEqual(f.yunit, "A")

    def test_errors(self):
        with self.assertRaises(EG.EGSError):
            EG.load_bytes(b"a;b\n1;2\n", "x.csv")
        with self.assertRaises(EG.EGSError):
            EG.load_bytes(b"", "x.csv")


if __name__ == "__main__":
    unittest.main()
