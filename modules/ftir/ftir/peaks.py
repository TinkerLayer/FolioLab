"""Peaksuche (Prominenz, Mindestabstand), Peakeigenschaften (Lage, Höhe, Halbwertsbreite, Fläche) und Bandenintegration.

Bei Transmission und Reflexion zeigen Banden nach unten; gesucht wird dann in -y.
"""
from __future__ import annotations

import numpy as np

# Prominenz/Schwelle in % des Bereichs; snr: Prominenz mindestens snr x Rauschen (0 = aus; 10 entspricht der üblichen
# Bestimmungsgrenze). Das Rauschen ist sigma0 bzw. dort, wo es das Signal überwiegt, das lokale Rauschen (quality.py).
# Die Prominenz reicht bis zum nächsten höheren Punkt und nimmt so auch Basislinienwellen mit; daher 10 und nicht 3–4.
DEFAULT = {"prominence": 2.0, "distance": 8.0, "threshold": 0.0, "max": 60, "snr": 10.0}

STRENGTH = [(0.75, "vs"), (0.4, "s"), (0.15, "m"), (0.0, "w")]


def _trap(y, x):
    return float(np.trapezoid(y, x)) if hasattr(np, "trapezoid") else float(np.trapz(y, x))


def _local_maxima(y: np.ndarray) -> np.ndarray:
    """Indizes lokaler Maxima, Plateaus in der Mitte."""
    n = len(y)
    out = []
    i = 1
    while i < n - 1:
        if y[i] > y[i - 1]:
            j = i
            while j + 1 < n and y[j + 1] == y[i]:
                j += 1
            if j + 1 < n and y[j + 1] < y[i]:
                out.append((i + j) // 2)
            i = j + 1
        else:
            i += 1
    return np.array(out, dtype=int)


def _bases(y: np.ndarray, idx: np.ndarray):
    """Prominenz je Maximum: links/rechts bis zum nächsten höheren Punkt (oder Rand), dort das Minimum."""
    n = len(y)
    # nächster höherer Punkt links/rechts über einen Stapel (O(n))
    left_hi = np.full(n, -1)
    stack = []
    for i in range(n):
        while stack and y[stack[-1]] <= y[i]:
            stack.pop()
        left_hi[i] = stack[-1] if stack else -1
        stack.append(i)
    right_hi = np.full(n, n)
    stack = []
    for i in range(n - 1, -1, -1):
        while stack and y[stack[-1]] < y[i]:
            stack.pop()
        right_hi[i] = stack[-1] if stack else n
        stack.append(i)
    prom, lb, rb = [], [], []
    for i in idx:
        a, b = left_hi[i] + 1, right_hi[i]
        li = a + int(np.argmin(y[a:i + 1])) if i >= a else i
        ri = i + int(np.argmin(y[i:b])) if b > i else i
        prom.append(y[i] - max(y[li], y[ri]))
        lb.append(li)
        rb.append(ri)
    return np.array(prom), np.array(lb, dtype=int), np.array(rb, dtype=int)


def _props(x, ys, i, li, ri, prom, rng):
    """Eigenschaften eines Peaks in ys (Banden nach oben)."""
    # Lage: Parabel durch drei Punkte
    xp, yp = x[i], ys[i]
    if 0 < i < len(x) - 1:
        y0, y1, y2 = ys[i - 1], ys[i], ys[i + 1]
        den = y0 - 2 * y1 + y2
        if den < 0:
            d = 0.5 * (y0 - y2) / den
            if abs(d) <= 1:
                step = (x[i + 1] - x[i - 1]) / 2
                xp = x[i] + d * step
                yp = y1 - 0.25 * (y0 - y2) * d
    # Halbwertsbreite auf halber Prominenz
    level = ys[i] - prom / 2
    a = i
    while a > li and ys[a] > level:
        a -= 1
    b = i
    while b < ri and ys[b] > level:
        b += 1
    xl = np.interp(level, [ys[a], ys[a + 1]], [x[a], x[a + 1]]) if ys[a] <= level < ys[a + 1] else x[a]
    xr = np.interp(level, [ys[b], ys[b - 1]], [x[b], x[b - 1]]) if ys[b] <= level < ys[b - 1] else x[b]
    fwhm = float(xr - xl)
    # Fläche über der Verbindungslinie der Fusspunkte, höchstens ±3 Halbwertsbreiten
    lo = max(li, int(np.searchsorted(x, xp - 3 * max(fwhm, 2))))
    hi = min(ri, int(np.searchsorted(x, xp + 3 * max(fwhm, 2))))
    area = 0.0
    if hi - lo >= 2:
        seg = ys[lo:hi + 1]
        base = np.interp(x[lo:hi + 1], [x[lo], x[hi]], [ys[lo], ys[hi]])
        area = _trap(np.clip(seg - base, 0, None), x[lo:hi + 1])
    return {"x": float(xp), "y": float(yp), "prom": float(prom), "prom_rel": float(prom / rng) if rng else 0.0,
            "fwhm": fwhm, "area": area}


def find(x: np.ndarray, y: np.ndarray, yunit: str = "A", params: dict | None = None,
         add=None, remove=None) -> list[dict]:
    """Peaks eines Spektrums. params wie DEFAULT; add/remove: Lagen in cm⁻¹ von Hand gesetzter/gelöschter Peaks."""
    p = {**DEFAULT, **(params or {})}
    valley = yunit in ("T", "R")
    ys = -y if valley else y
    snr = float(p.get("snr") or 0)
    noise = None
    calm = np.ones(len(ys), bool)
    if snr > 0 and len(ys) >= 30 and yunit not in ("D1", "D2"):
        from . import quality as Q
        q = Q.assess(x, ys, "A")
        noise = Q.effective_noise(x, ys, q)
        if q["noisy"]:
            calm = ~Q.mask_of(x, q["noisy"])
            if calm.sum() < 10:
                calm[:] = True
    rng = float(np.ptp(ys[calm])) or 1.0
    idx = _local_maxima(ys)
    peaks = []
    if len(idx):
        prom, lb, rb = _bases(ys, idx)
        thr = ys[calm].min() + float(p["threshold"]) / 100 * rng
        ok = (prom >= float(p["prominence"]) / 100 * rng) & (ys[idx] >= thr)
        if noise is not None:
            # in verrauschten Bereichen keine automatischen Peaks (die grössten Rauschspitzen erreichen dort leicht
            # 6–8 sigma); von Hand gesetzte Peaks bleiben möglich
            ok &= (prom >= snr * noise[idx]) & calm[idx]
        cand = sorted(np.where(ok)[0], key=lambda k: -prom[k])
        kept = []
        dist = float(p["distance"])
        for k in cand:
            if all(abs(x[idx[k]] - x[idx[j]]) >= dist for j in kept):
                kept.append(k)
            if len(kept) >= int(p["max"]):
                break
        for k in kept:
            peaks.append(_props(x, ys, idx[k], lb[k], rb[k], prom[k], rng))
    removed = [float(r) for r in remove or []]
    peaks = [pk for pk in peaks if not any(abs(pk["x"] - r) <= max(3.0, 1.5 * _step(x)) for r in removed)]
    for a in add or []:
        a = float(a)
        if not (x[0] <= a <= x[-1]) or any(abs(pk["x"] - a) <= max(3.0, 1.5 * _step(x)) for pk in peaks):
            continue
        pk = _manual(x, ys, a, rng)
        if pk:
            pk["manual"] = True
            peaks.append(pk)
    peaks.sort(key=lambda d: -d["x"])
    if peaks:
        top = max(pk["prom"] for pk in peaks) or 1.0
        for pk in peaks:
            pk["rel"] = pk["prom"] / top
            pk["strength"] = next(s for t, s in STRENGTH if pk["rel"] >= t)
            pk["shape"] = "br" if pk["fwhm"] > 60 else ""
            if valley:
                pk["y"] = -pk["y"]
    return peaks


def _step(x):
    return float(np.median(np.diff(x))) if len(x) > 1 else 1.0


def _manual(x, ys, a, rng):
    """Peak von Hand: höchster Punkt im Umkreis von ±6 cm⁻¹, Fusspunkte bis ±60 cm⁻¹."""
    m = np.where(np.abs(x - a) <= max(6.0, 2 * _step(x)))[0]
    if not len(m):
        return None
    i = int(m[np.argmax(ys[m])])
    w = np.where(np.abs(x - x[i]) <= 60)[0]
    li = int(w[0] + np.argmin(ys[w[0]:i + 1]))
    ri = int(i + np.argmin(ys[i:w[-1] + 1]))
    prom = ys[i] - max(ys[li], ys[ri])
    return _props(x, ys, i, li, ri, max(prom, 1e-12), rng)


def integrate(x: np.ndarray, y: np.ndarray, lo: float, hi: float, yunit: str = "A", base: str = "linear") -> dict:
    """Bandenfläche zwischen lo und hi; base: "linear" (Gerade zwischen den Grenzen) oder "zero"."""
    lo, hi = sorted((float(lo), float(hi)))
    m = (x >= lo) & (x <= hi)
    if m.sum() < 3:
        return {"lo": lo, "hi": hi, "area": None, "height": None, "pos": None}
    valley = yunit in ("T", "R")
    ys = -y[m] if valley else y[m]
    xs = x[m]
    b = np.interp(xs, [xs[0], xs[-1]], [ys[0], ys[-1]]) if base == "linear" else np.zeros_like(xs)
    d = ys - b
    i = int(np.argmax(d))
    area = _trap(d, xs)
    cen = float(_trap(d * xs, xs) / area) if area else None
    return {"lo": lo, "hi": hi, "area": area, "height": float(d[i]), "pos": float(xs[i]), "centroid": cen}
