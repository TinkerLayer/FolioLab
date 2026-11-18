"""Optional reference data: which parts are present on this computer.

The public repository contains only data whose licence allows redistribution (see THIRD_PARTY_NOTICES.md). Five
further parts are free to use but may not be redistributed, or their terms are unclear. They are not in the
repository; `python tools/fetch_optional_data.py` downloads them from the original source and builds them on the
user's computer:

  pka        IUPAC Digitized pKa Dataset (CC BY-NC 4.0)               -> labcalc/data/pka.json
  srd46      NIST SRD 46, critically selected stability constants     -> labcalc/data/stability.json
  asd        NIST Atomic Spectra Database, ionisation energies        -> labcalc/data/ionization.json
  burcat     Burcat/Goos/Ruscic thermochemical database (NASA-7)      -> labcalc/data/optional/thermo_burcat.json
  openspecy  Open Specy spectra whose source licence is non-commercial or unstated
                                                                       -> modules/ftir/ftir/data/openspecy-restricted/

Every module works without them; functions that need a missing part say so. Tests that need a part are skipped with
`skip_unless(...)` and name the command that adds it.
"""
from __future__ import annotations

import json
import unittest
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SDK_DATA = Path(__file__).resolve().parent / "labcalc" / "data"
FTIR_DATA = ROOT / "modules" / "ftir" / "ftir" / "data"

PARTS = ("pka", "srd46", "asd", "burcat", "openspecy")
OPENSPECY_OPEN = ("Microplastix", "Davidson 2023", "Primpke 2018")


@lru_cache(maxsize=None)
def available(part: str) -> bool:
    if part == "pka":
        return (SDK_DATA / "pka.json").exists()
    if part == "srd46":
        return (SDK_DATA / "stability.json").exists()
    if part == "asd":
        return (SDK_DATA / "ionization.json").exists()
    if part == "burcat":
        if (SDK_DATA / "optional" / "thermo_burcat.json").exists():
            return True
        p = SDK_DATA / "thermo.json"            # maintainers' working copy: one file with all sources
        return p.exists() and b'"src":"burcat"' in p.read_bytes()
    if part == "openspecy":
        if (FTIR_DATA / "openspecy-restricted" / "meta.json").exists():
            return True
        p = FTIR_DATA / "openspecy" / "meta.json"
        if not p.exists():
            return False
        meta = json.loads(p.read_text(encoding="utf-8"))
        return any(e.get("origin") not in OPENSPECY_OPEN for e in meta.get("entries", []))
    raise ValueError(f"unknown optional part {part!r}; known: {', '.join(PARTS)}")


def missing(*parts: str) -> list[str]:
    return [p for p in parts if not available(p)]


def skip_unless(*parts: str):
    """unittest decorator: skip when an optional data part is not installed."""
    miss = missing(*parts)
    return unittest.skipIf(bool(miss), f"needs optional data {', '.join(miss)} "
                                       f"(python tools/fetch_optional_data.py {' '.join(miss)})")
