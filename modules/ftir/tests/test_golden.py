"""Golden test (A0): the report bundle of the synthetic PET sample compared with a stored reference.

Fixed input: samples.make("pet") (seed 11) with peaks, groups, two band areas, one ratio and a correlation search
against the built-in model library, as in test_ftir.py (BundleTest._state).
References: tests/golden/ftir_<lang>.json. Regenerate with FOLIO_GOLDEN_UPDATE=1 (see sdk/python/labgolden.py).
"""
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "sdk" / "python"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import labgolden  # noqa: E402
from ftir import bundle, process, samples, search  # noqa: E402
from ftir import library as LB  # noqa: E402
from ftir.readers import load_bytes  # noqa: E402

GOLDEN = Path(__file__).resolve().parent / "golden"


def pet_state(raw, name):
    sp = load_bytes(raw, name)[0]
    pipe = [{"op": "to_abs"}] if sp.yunit == "T" else []
    s = process.apply(sp, pipe).spectrum
    q = LB.prep(s.x, s.y, s.yunit)
    r = search.search(q, [LB.model_library()], "corr", exclude=search.DEFAULT_EXCLUDE, n=5)
    hits = [{k: h[k] for k in ("rank", "name", "lib_name", "hqi", "category", "cas")} | ({"y": h["y"].tolist()} if i < 3 else {})
            for i, h in enumerate(r["hits"])]
    return {"pipeline": pipe, "peaks": {"params": {}}, "groups": True,
            "bands": [{"name": "C=O", "lo": 1650, "hi": 1780}, {"name": "Ring", "lo": 700, "hi": 745}],
            "ratios": [{"name": "C=O/Ring", "num": "C=O", "den": "Ring"}],
            "search": {"algo": "corr", "hits": hits, "query": [None if not np.isfinite(v) else float(v) for v in q]}}


class GoldenBundle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw, cls.name = samples.make("pet")

    def _check(self, lang):
        st = pet_state(self.raw, self.name)
        b = bundle.build([(self.raw, self.name, 0, st)], {"items": [{"name": self.name, "idx": 0, "state": st}]}, lang)
        labgolden.check(b, GOLDEN / f"ftir_{lang}.json")

    def test_bundle_de(self):
        self._check("de")

    def test_bundle_en(self):
        self._check("en")


if __name__ == "__main__":
    unittest.main()
