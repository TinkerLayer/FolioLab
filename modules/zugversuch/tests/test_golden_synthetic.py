"""Golden test on a synthetic curve: the whole report bundle (figures, tables, values, methods text, citations) of a
test whose answer is known, compared with a stored reference.

Unlike test_golden.py this needs no measured file, so it also runs in the public repository. The curve is the one of
test_dataset.py: E = 70 GPa up to 105 MPa, hardening to Rm ≈ 140 MPa, necking, break. Input path: dataset → make_raw
→ parser → analysis → bundle, with the reference material EN AW-5052-H38 for the comparison.
References: tests/golden/zugversuch_synth_<lang>.json. Regenerate with FOLIO_GOLDEN_UPDATE=1 (sdk/python/labgolden.py).
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "sdk" / "python"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import labdataset as DSET  # noqa: E402
import labgolden  # noqa: E402
from flps import analyse, bundle  # noqa: E402
from flps import dataset as ZD  # noqa: E402
from flps.parser import parse_bytes  # noqa: E402
from test_dataset import A0, E_MPA, L0, V, curve  # noqa: E402

GOLDEN = Path(__file__).resolve().parent / "golden"
SOURCE = {"share": "s-5e7a0001", "title": "Synthetische Kurve", "version": 1, "created": "2026-11-18T10:00:00"}


class GoldenSynthetic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        eps, sig = curve()
        ds = DSET.from_columns("Synthetische Kurve", [
            {"key": "e", "name": "Dehnung", "unit": "%", "values": eps * 100},
            {"key": "s", "name": "Spannung", "unit": "MPa", "values": sig}])
        cls.raw, cls.name, c = ZD.make_raw(ds, {"load": "s", "ext": "e"},
                                           {"a0_mm2": A0, "l0_mm": L0, "speed_mm_min": V}, SOURCE)
        cls.cfg = analyse.Config.from_dict({**c, "displacement_source": "probe", "material_ref": "EN AW-5052-H38"})
        cls.r = analyse.run(parse_bytes(cls.raw, cls.name), cls.cfg)
        cls.req = {"items": [{"name": cls.name, "config": cls.cfg.to_dict()}]}

    def test_known_values(self):
        eps, sig = curve()
        self.assertAlmostEqual(self.r.kv["Rm"], float(sig.max()), delta=0.01)
        self.assertAlmostEqual(self.r.e_schein_gpa, E_MPA / 1000, delta=E_MPA / 1000 * 0.03)

    def _check(self, lang):
        b = bundle.build([self.r], {self.name: self.raw}, self.req, lang=lang)
        labgolden.check(b, GOLDEN / f"zugversuch_synth_{lang}.json")

    def test_bundle_de(self):
        self._check("de")

    def test_bundle_en(self):
        self._check("en")


if __name__ == "__main__":
    unittest.main()
