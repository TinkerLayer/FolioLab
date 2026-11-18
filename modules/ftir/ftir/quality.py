"""Signalqualität eines Spektrums: Rauschen, verrauschte Bereiche, Signal/Rausch-Verhältnis und Hinweise.

Rauschen: Rest nach einer Savitzky-Golay-Glättung (7 Punkte, kubisch), lokal als gleitender Median der Beträge
(robust gegen einzelne scharfe Banden). sigma0 ist das 25. Perzentil der lokalen Werte, also das Rauschen der
ruhigen Abschnitte.

Verrauscht heisst: lokal mehr als 3,5 x sigma0 und dort mehr Rauschen als Signal. Typisch ist der Bereich
um 2300–1900 cm⁻¹ bei Diamant-ATR (der Kristall absorbiert dort selbst, es kommt wenig Licht an); ebenso die
Ränder des Detektorbereichs. Die zweite Bedingung verhindert, dass dichte Bandenbereiche sehr guter Spektren
(wo die Glättung etwas Signal mitnimmt) als Rauschen gelten.
"""
from __future__ import annotations

import numpy as np

from .process import moving_mean, savgol

H0 = 7 / 21                      # Mittelkoeffizient der 7-Punkt-Glättung (quadratisch = kubisch)
WINDOW = 80.0                    # cm⁻¹, Fenster für das lokale Rauschen
NOISY_FACTOR = 3.5
MIN_NOISY = 40.0                 # cm⁻¹, kürzere Abschnitte zählen nicht
WEAK_SNR, POOR_SNR = 50.0, 15.0


def _rolling(v: np.ndarray, w: int, fn) -> np.ndarray:
    n = len(v)
    w = max(3, min(int(w) | 1, n if n % 2 else n - 1))
    k = w // 2
    vp = np.concatenate([v[k:0:-1], v, v[-2:-k - 2:-1]]) if n > k + 1 else np.pad(v, k, mode="edge")
    view = np.lib.stride_tricks.sliding_window_view(vp, w)
    return fn(view, axis=1)[:n]


def _step(x) -> float:
    return float(abs(np.median(np.diff(x)))) if len(x) > 1 else 1.0


def local_noise(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Lokale Standardabweichung des Rauschens je Punkt (gleiche Einheit wie y)."""
    y = np.asarray(y, float)
    if len(y) < 15:
        return np.zeros(len(y))
    r = y - savgol(y, 7, 3)
    w = min(101, max(9, int(WINDOW / max(_step(x), 1e-6))))
    return 1.4826 * _rolling(np.abs(r), w, np.median) / np.sqrt(1 - H0)


def _ranges(x: np.ndarray, m: np.ndarray, min_width: float, gap: float) -> list[list[float]]:
    """Zusammenhängende True-Abschnitte von m als [[hoch, tief], ...] (cm⁻¹), Lücken < gap geschlossen."""
    out = []
    idx = np.where(m)[0]
    if not len(idx):
        return out
    start = prev = idx[0]
    for i in idx[1:]:
        if abs(x[i] - x[prev]) > gap:
            out.append((start, prev))
            start = i
        prev = i
    out.append((start, prev))
    res = []
    for a, b in out:
        lo, hi = sorted((float(x[a]), float(x[b])))
        if hi - lo >= min_width:
            res.append([round(hi, 1), round(lo, 1)])
    return sorted(res, key=lambda r: -r[0])


def mask_of(x: np.ndarray, ranges) -> np.ndarray:
    m = np.zeros(len(x), bool)
    for r in ranges or []:
        lo, hi = sorted((float(r[0]), float(r[1])))
        m |= (x >= lo) & (x <= hi)
    return m


def assess(x: np.ndarray, y: np.ndarray, yunit: str = "A") -> dict:
    """Rauschen und Hinweise. Für Ableitungen nur das Rauschen, ohne Bereiche und Hinweise."""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    ok = np.isfinite(y)
    if ok.sum() < 30:
        return {"sigma": 0.0, "noisy": [], "snr": None, "warnings": []}
    x, y = x[ok], y[ok]
    loc = local_noise(x, y)
    s0 = float(np.percentile(loc, 25))
    if s0 <= 0:
        s0 = float(np.median(loc[loc > 0])) if (loc > 0).any() else 0.0
    out = {"sigma": s0, "noisy": [], "snr": None, "warnings": []}
    if s0 <= 0 or yunit in ("D1", "D2"):
        return out
    step = _step(x)
    w = min(101, max(9, int(WINDOW / max(step, 1e-6))))
    sm = moving_mean(y, max(3, int(round(12 / max(step, 1e-6))) | 1))
    span = _rolling(sm, w, np.max) - _rolling(sm, w, np.min)
    noise_dom = span < 8 * loc
    core = (loc > NOISY_FACTOR * s0) & noise_dom
    # Hysterese: Kernbereiche nach aussen erweitern, solange das Rauschen noch deutlich erhöht ist
    ext = (loc > 2.0 * s0) & noise_dom
    noisy = np.zeros(len(x), bool)
    i, n = 0, len(x)
    while i < n:
        if ext[i]:
            j = i
            while j < n and ext[j]:
                j += 1
            if core[i:j].any():
                noisy[i:j] = True
            i = j
        else:
            i += 1
    out["noisy"] = _ranges(x, noisy, MIN_NOISY, max(60.0, 3 * step))
    quiet = ~mask_of(x, out["noisy"])
    if quiet.sum() < 30:
        quiet = np.ones(len(x), bool)
    # Signal: stärkste Bande über einer Hüllkurven-Basislinie, ausserhalb der verrauschten Bereiche
    from .process import rubberband
    ys = -sm if yunit in ("T", "R") else sm
    xb, yb = x[quiet], ys[quiet]
    order = np.argsort(xb)
    xb, yb = xb[order], yb[order]
    sig = float(np.percentile(yb - rubberband(xb, yb), 99.5))
    snr = sig / s0
    out["snr"] = round(snr, 1)
    W = out["warnings"]
    for hi, lo in out["noisy"]:
        diamond = lo < 2250 and hi > 1950
        W.append({"kind": "noisy", "range": [hi, lo],
                  "de": f"Verrauschter Bereich {hi:.0f}–{lo:.0f} cm⁻¹"
                        + (" (typisch für Diamant-ATR)" if diamond else "")
                        + ": bei Peaks, Gruppen und Suche nicht berücksichtigt.",
                  "en": f"Noisy region {hi:.0f}–{lo:.0f} cm⁻¹" + (" (typical of diamond ATR)" if diamond else "")
                        + ": ignored for peaks, groups and search."})
    if snr < POOR_SNR:
        W.append({"kind": "snr", "de": f"Kaum Signal (S/N ≈ {snr:.0f}). Probenkontakt und Anpressdruck prüfen oder neu messen; "
                                      "Banden, Gruppen und Suchtreffer sind nicht belastbar.",
                  "en": f"Hardly any signal (S/N ≈ {snr:.0f}). Check sample contact and pressure or measure again; "
                        "bands, groups and search hits are not reliable."})
    elif snr < WEAK_SNR:
        W.append({"kind": "snr", "de": f"Schwaches Signal (S/N ≈ {snr:.0f}). Schwache Banden können im Rauschen untergehen.",
                  "en": f"Weak signal (S/N ≈ {snr:.0f}). Weak bands may be lost in the noise."})
    if yunit == "A":
        top = float(np.percentile(y[quiet], 99.9))
        if top > 1.5:
            W.append({"kind": "sat", "de": f"Absorbanz bis {top:.1f}: stärkste Banden womöglich gesättigt (nicht linear).",
                      "en": f"Absorbance up to {top:.1f}: strongest bands may be saturated (non-linear)."})
    elif yunit in ("T", "R"):
        if float(np.percentile(y[quiet], 0.1)) < 1.0:
            W.append({"kind": "sat", "de": "Transmission nahe 0 %: stärkste Banden womöglich gesättigt.",
                      "en": "Transmittance near 0 %: strongest bands may be saturated."})
    return out


def effective_noise(x: np.ndarray, y: np.ndarray, q: dict | None = None) -> np.ndarray:
    """Rauschschwelle je Punkt: wo das Rauschen das Signal überwiegt, das lokale Rauschen (mindestens sigma0), sonst
    sigma0. In dichten Bandenbereichen enthält der Glättungsrest etwas Signal; dort gilt deshalb sigma0."""
    q = q or assess(x, y)
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    s0 = float(q["sigma"])
    sig = np.full(len(x), s0)
    if len(y) < 30 or s0 <= 0:
        return sig
    loc = local_noise(x, y)
    step = _step(x)
    w = min(101, max(9, int(WINDOW / max(step, 1e-6))))
    sm = moving_mean(y, max(3, int(round(12 / max(step, 1e-6))) | 1))
    span = _rolling(sm, w, np.max) - _rolling(sm, w, np.min)
    dom = span < 8 * loc
    if q["noisy"]:
        dom |= mask_of(x, q["noisy"])
    sig[dom] = np.maximum(s0, loc[dom])
    return sig
