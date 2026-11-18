"""Input for tests that need a whole measurement but not its particular values.

By default the tests run on the synthetic curve of test_dataset.py (E = 70 GPa, yield 105 MPa, Rm ≈ 140 MPa), turned
into a measurement by flps.dataset.make_raw exactly as a dataset import would be. To run them on a real .flps file
instead, set FOLIO_ZV_REFERENCE to its path (real measurements are never part of the repository).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REAL = Path(os.environ["FOLIO_ZV_REFERENCE"]) if os.environ.get("FOLIO_ZV_REFERENCE") else None
for p in (str(ROOT), str(ROOT.parents[1] / "sdk" / "python"), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)


def measurement() -> tuple[bytes, str, bool]:
    """(raw bytes, file name, real?)"""
    if REAL is not None and REAL.exists():
        return REAL.read_bytes(), REAL.name, True
    import labdataset as DSET
    from flps import dataset as ZD
    from test_dataset import A0, L0, V, curve
    eps, sig = curve()
    ds = DSET.from_columns("Synthetische Kurve", [
        {"key": "e", "name": "Dehnung", "unit": "%", "values": eps * 100},
        {"key": "s", "name": "Spannung", "unit": "MPa", "values": sig}])
    raw, name, _c = ZD.make_raw(ds, {"load": "s", "ext": "e"}, {"a0_mm2": A0, "l0_mm": L0, "speed_mm_min": V},
                                {"share": "s-5e7a0001", "title": "Synthetische Kurve", "version": 1,
                                 "created": "2026-11-18T10:00:00"})
    return raw, name, False
