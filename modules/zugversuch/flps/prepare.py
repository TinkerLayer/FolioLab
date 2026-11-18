"""Datenaufbereitung (Spezifikation Abschnitt 2)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np

from .parser import FlpsFile


@dataclass
class Prepared:
    """Alle Messpunkte, inklusive der Leerwerte nach dem Bruch."""
    timestamps: list[datetime]
    t_coarse: np.ndarray      # Sekunden seit Start, sekundengenau (Beleg)
    t_fine: np.ndarray        # verteilte Zeit (fuer jede Rechnung)
    force_raw: np.ndarray     # mit Vorzeichen, wie gespeichert
    force_abs: np.ndarray     # Betrag
    displacement: np.ndarray
    resolution: float         # Anzeigeaufloesung der Kraft (aus ForceDecimalPoint)
    test_type: str            # "Zug" oder "Druck"
    break_index: int | None   # erster Messpunkt des Lastabfalls (0-basiert), None = kein Bruch
    active_end: int           # letzter Index des aktiven Abschnitts (inklusive)
    rate_hz: float
    criteria_ref: float       # Fmax ueber alle Punkte, Bezug der Bruchkriterien

    @property
    def n_total(self) -> int:
        return len(self.force_abs)

    @property
    def n_active(self) -> int:
        return self.active_end + 1

    @property
    def n_cut(self) -> int:
        return self.n_total - self.n_active

    @property
    def dt(self) -> float:
        return 1.0 / self.rate_hz if self.rate_hz > 0 else float("nan")


def fine_time(timestamps: list[datetime]) -> tuple[np.ndarray, np.ndarray]:
    """Abschnitt 2.2: Gruppen gleicher Zeitstempel, gleichmaessig verteilt."""
    t_start = timestamps[0]
    coarse = np.array([(ts - t_start).total_seconds() for ts in timestamps], dtype=float)
    fine = coarse.copy()
    n = len(coarse)
    i = 0
    while i < n:
        j = i
        while j + 1 < n and timestamps[j + 1] == timestamps[i]:
            j += 1
        size = j - i + 1
        for k in range(size):
            fine[i + k] = coarse[i] + k / size
        i = j + 1
    return coarse, fine


def find_break(force_abs: np.ndarray, ref: float, upper: float, lower: float) -> int | None:
    """Abschnitt 4.6: erster Punkt, dessen Vorgaenger ueber dem oberen und der selbst
    unter dem unteren Kriterium liegt. Rueckgabe: Index dieses Punktes (Lastabfall)."""
    hi, lo = upper * ref, lower * ref
    for i in range(1, len(force_abs)):
        if force_abs[i - 1] > hi and force_abs[i] < lo:
            return i
    return None


def prepare(f: FlpsFile, break_upper: float = 0.10, break_lower: float = 0.01) -> Prepared:
    if not f.points:
        raise ValueError("Datei enthaelt keine Messpunkte")
    ts = [p.timestamp for p in f.points]
    coarse, fine = fine_time(ts)
    raw = np.array([p.force for p in f.points], dtype=float)
    absf = np.abs(raw)
    disp = np.array([p.displacement for p in f.points], dtype=float)

    imax = int(np.argmax(absf))
    test_type = "Zug" if raw[imax] < 0 else "Druck"

    dp = f.points[0].force_decimal_point
    resolution = 10.0 ** (-dp) if isinstance(dp, int) and 0 <= dp < 6 else 0.1

    ref = float(absf.max())
    b = find_break(absf, ref, break_upper, break_lower)
    active_end = b if b is not None else len(absf) - 1

    # Abschnitt 2.3: Messpunkte bis zum Lastabfall / zugehoerige feine Zeit
    t_end = fine[active_end] - fine[0]
    rate = active_end / t_end if t_end > 0 else float("nan")

    return Prepared(
        timestamps=ts, t_coarse=coarse, t_fine=fine, force_raw=raw, force_abs=absf,
        displacement=disp, resolution=resolution, test_type=test_type,
        break_index=b, active_end=active_end, rate_hz=rate, criteria_ref=ref,
    )
