"""Periodensystem: Lage (Periode, Gruppe), Block und Anzeigezeile für die 118 Elemente.

Darstellung mit 18 Gruppen (IUPAC); Lanthanoide (57–71) und Actinoide (89–103) in eigenen Zeilen darunter.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SDK = Path(__file__).resolve().parents[3] / "sdk" / "python"
if _SDK.is_dir() and str(_SDK) not in sys.path:
    sys.path.insert(0, str(_SDK))

from labcalc.chem import NAMES_DE, NAMES_EN, SYMBOLS  # noqa: E402

PERIOD_STARTS = [1, 3, 11, 19, 37, 55, 87, 119]


def position(Z: int) -> dict:
    """{"period", "group" (None bei f-Block), "row", "col", "block"} für die Rasterdarstellung (row/col ab 1)."""
    period = next(p for p in range(1, 8) if PERIOD_STARTS[p - 1] <= Z < PERIOD_STARTS[p])
    k = Z - PERIOD_STARTS[period - 1]                  # 0-basiert in der Periode
    if period == 1:
        group = 1 if Z == 1 else 18
    elif period in (2, 3):
        group = k + 1 if k < 2 else k + 11
    elif period in (4, 5):
        group = k + 1
    else:
        if k < 2:
            group = k + 1
        elif k < 17:                                   # La–Lu bzw. Ac–Lr (15 Elemente)
            group = None
        else:
            group = k - 13
    if group is None:
        row = 9 if period == 6 else 10
        col = 3 + (k - 2)
        block = "f"
    else:
        row, col = period, group
        block = "s" if group in (1, 2) or Z == 2 else "p" if group >= 13 else "d"
    return {"period": period, "group": group, "row": row, "col": col, "block": block}


def table() -> list[dict]:
    return [{"Z": z, "symbol": s, "name_de": NAMES_DE[z - 1], "name_en": NAMES_EN[z - 1], **position(z)}
            for z, s in enumerate(SYMBOLS, start=1)]
