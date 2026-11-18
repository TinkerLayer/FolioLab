"""Beispieldateien zum Ausprobieren, berechnet aus der Modellbibliothek (mit Rauschen, Basislinie, ATR-Gewichtung
und CO₂). Sie liegen in den Formaten vor, die das Modul liest, und durchlaufen beim Laden denselben Weg wie echte
Dateien. Keine Messdaten."""
from __future__ import annotations

import numpy as np

from .readers import Spectrum, to_jcamp
from .refdata import MATERIALS, band_model

SAMPLES = {
    "pet": ("Unbekannte Folie (ATR, %T, CSV mit Semikolon)", "Probe_Folie_ATR.csv"),
    "mix": ("Gefüllter Kunststoff (Absorbanz, JCAMP-DX)", "Probe_gefuellt.jdx"),
    "ps": ("Becherdeckel (Transmission, Absorbanz, CSV)", "Probe_Deckel.csv"),
}


def _bands(mid):
    for m in MATERIALS:
        if m[0] == mid:
            return m[4]
    raise KeyError(mid)


def _model(mid, x, shift=1.5, widen=1.1):
    return band_model([(c + shift, h, w * widen) for c, h, w in _bands(mid)], x)


def _co2(x, amp):
    return amp * (np.exp(-((x - 2360) / 9) ** 2) - 0.8 * np.exp(-((x - 2338) / 8) ** 2)) + \
        0.3 * amp * np.exp(-((x - 668) / 3) ** 2)


def make(which: str) -> tuple[bytes, str]:
    rng = np.random.default_rng({"pet": 11, "mix": 12, "ps": 13}.get(which, 1))
    if which == "pet":
        x = np.arange(600.0, 4000.0 + 1e-9, 0.964)          # typisches 4-cm⁻¹-Gerät mit Nullfüllung
        a = 0.55 * _model("pet", x) * (1000 / x) ** 0.7 + 0.015 + 0.01 * (x / 4000) + _co2(x, 0.01)
        a += rng.normal(0, 0.0012, len(x))
        t = 100 * 10 ** (-a)
        lines = ["Wellenzahl [cm-1];%T"] + [f"{xx:.3f};{yy:.4f}".replace(".", ",") for xx, yy in zip(x[::-1], t[::-1])]
        return ("\n".join(lines) + "\n").encode("utf-8"), SAMPLES[which][1]
    if which == "mix":
        x = np.arange(450.0, 4000.0 + 1e-9, 1.929)
        a = 0.62 * _model("pe", x) + 0.45 * _model("calcite", x) + 0.04 + 0.03 * (x / 4000) ** 2 + _co2(x, 0.006)
        a += rng.normal(0, 0.0015, len(x))
        sp = Spectrum("Gefuellter Kunststoff", x, a, "A")
        txt = to_jcamp(sp, "Gefuellter Kunststoff", {"SAMPLING PROCEDURE": "ATR, Diamant", "RESOLUTION": 4,
                                                     "$NOTE": "Beispiel aus Folio Lab, berechnet, keine Messung"})
        return txt.encode("utf-8"), SAMPLES[which][1]
    if which == "ps":
        x = np.arange(500.0, 4000.0 + 1e-9, 1.0)
        a = 0.8 * _model("ps", x, shift=0.5, widen=1.0) + 0.05 + 0.06 * ((4000 - x) / 3500) ** 2 + _co2(x, 0.02)
        a += rng.normal(0, 0.002, len(x))
        lines = ["wavenumber,absorbance"] + [f"{xx:.1f},{yy:.5f}" for xx, yy in zip(x, a)]
        return ("\n".join(lines) + "\n").encode("utf-8"), SAMPLES[which][1]
    raise KeyError(which)
