"""FT-01: Bruker-OPUS-Leser mit erzeugten Dateien (keine echte OPUS-Datei vorhanden)."""
from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "sdk" / "python"))

from ftir import opus as OP  # noqa: E402
from ftir.readers import ReadError, load_bytes  # noqa: E402


def spectrum(n=1801):
    x = np.linspace(4000.0, 400.0, n)                                   # OPUS: absteigend gespeichert
    y = 0.05 + 0.8 * np.exp(-((x - 1720) / 12) ** 2) + 0.4 * np.exp(-((x - 2920) / 30) ** 2)
    return x, y


class Opus(unittest.TestCase):
    def test_round_trip_absorbance(self):
        x, y = spectrum()
        raw = OP.write_spectrum(x, y, sample={"SNM": "PE-Folie", "SFM": "Folie"}, csf=0.5)
        sps = load_bytes(raw, "probe.0")
        self.assertEqual(len(sps), 1)
        sp = sps[0]
        self.assertEqual(sp.name, "PE-Folie")
        self.assertEqual(sp.yunit, "A")
        self.assertAlmostEqual(sp.x[0], 400.0)
        self.assertAlmostEqual(sp.x[-1], 4000.0)
        np.testing.assert_allclose(sp.y, y[::-1], atol=1e-6)            # float32, Faktor CSF wieder angewandt
        self.assertIn("nicht mit echten OPUS-Dateien geprüft", sp.meta["format"])
        self.assertEqual(sp.meta["sample_form"], "Folie")
        self.assertEqual(sp.x[int(np.argmax(sp.y))].round(), 1720)

    def test_micrometre_axis_and_single_channel(self):
        x, y = spectrum(500)
        um = 1e4 / x
        raw = OP.write_spectrum(um, 50 + 40 * y, kind="ScSm", xunit="MI")
        sp = load_bytes(raw, "probe.1")[0]
        self.assertEqual(sp.yunit, "au")
        self.assertIn("Einkanalspektrum", sp.name)
        self.assertAlmostEqual(sp.x[0], 400.0, places=3)

    def test_unknown_blocks_reported_not_guessed(self):
        x, y = spectrum()
        ig = ((7, 8, 0), np.zeros(64, "<f4").tobytes())                 # Interferogramm: gemeldet, nicht geöffnet
        odd = ((99, 3, 0), b"\x01\x02\x03\x04" * 8)
        sp = load_bytes(OP.write_spectrum(x, y, extra=[ig, odd]), "probe.2")[0]
        self.assertEqual(sp.meta["opus_unbekannt"], [{"datentyp": 99, "kanal": 3, "text": 0, "bytes": 32}])
        self.assertEqual(sp.meta["opus_nicht_geoeffnet"], ["Interferogramm Probe"])

    def test_broken_files_rejected(self):
        x, y = spectrum()
        raw = bytearray(OP.write_spectrum(x, y))
        with self.assertRaises(ReadError):
            load_bytes(bytes(raw[:30]), "kurz.0")                       # Verzeichnis abgeschnitten
        bad = bytearray(raw)
        struct.pack_into("<i", bad, 24 + 8, len(raw) + 100)             # Offset des ersten Blocks ausserhalb
        with self.assertRaises(ReadError):
            load_bytes(bytes(bad), "kaputt.0")
        only_ig = OP.write([((7, 8, 0), np.zeros(64, "<f4").tobytes())])
        with self.assertRaisesRegex(ReadError, "Interferogramm"):
            load_bytes(only_ig, "ig.0")

    def test_param_block_corruption_detected(self):
        blk = bytearray(OP._param_block({"NPT": 10}))
        blk[0:4] = b"n?\x01\0"
        with self.assertRaisesRegex(ReadError, "beschädigt"):
            OP.params(bytes(blk), 0, len(blk) // 4, "x.0")


if __name__ == "__main__":
    unittest.main()
