"""Trennung sich berührender Teilchen: Distanztransformation + Wasserscheide (MI-01), nur numpy.

1. Euklidische Distanztransformation (exakt, separierbar: Zeilenabstand, dann Minimum über Spaltenversätze;
   Verfahren nach Saito & Toriwaki 1994).
2. Marker = h-Maxima der Distanzkarte (morphologische Rekonstruktion durch Dilatation von f − h unter f;
   Soille 2004): Maxima, die weniger als h Pixel über ihrem Sattel liegen, verschmelzen – das verhindert
   Übersegmentierung an rauen Rändern.
3. Flutung der invertierten Distanzkarte von den Markern aus, Stufe für Stufe (Immersion nach Vincent & Soille 1991);
   Pixel, die zwei Becken zugleich erreichen, werden Trennlinie. Die Linien trennen auch in 8er-Nachbarschaft.

Ergebnis ist wieder eine Binärmaske (Teilchen mit 1 Pixel breiten Trennlinien), wie in ImageJ „Watershed“.
"""
from __future__ import annotations

import numpy as np

from .label import label

REFS = ["vincent1991", "soille2004", "saito1994"]
# Format wie threshold.REFERENCES. DOIs am 17.11.2026 gegen Crossref geprüft (MI-02).
# Soille: 2. Auflage (Springer 2003), zitiert wird der korrigierte 2. Druck von 2004, zu dem die DOI gehört; Schlüssel
# und Jahr daher 2004 (bis Version 1.2.0 hiess der Schlüssel soille2003).
REFERENCES = {
    "vincent1991": dict(entry_type="article", author="Vincent, Luc and Soille, Pierre",
                        title="Watersheds in digital spaces: an efficient algorithm based on immersion simulations",
                        journal="IEEE Transactions on Pattern Analysis and Machine Intelligence", year="1991",
                        volume="13", number="6", pages="583--598", doi="10.1109/34.87344"),
    "soille2004": dict(entry_type="book", author="Soille, Pierre",
                       title="Morphological Image Analysis: Principles and Applications", edition="2",
                       publisher="Springer", address="Berlin", year="2004", doi="10.1007/978-3-662-05088-0"),
    "saito1994": dict(entry_type="article", author="Saito, Toyofumi and Toriwaki, Jun-Ichiro",
                      title="New algorithms for euclidean distance transformation of an n-dimensional digitized picture with applications",
                      journal="Pattern Recognition", year="1994", volume="27", number="11", pages="1551--1565",
                      doi="10.1016/0031-3203(94)90133-3"),
}


def edt(mask: np.ndarray) -> np.ndarray:
    """Euklidischer Abstand jedes Vordergrundpixels zum nächsten Hintergrundpixel (Bildrand zählt als Hintergrund)."""
    m = np.pad(np.asarray(mask, bool), 1, constant_values=False)
    H, W = m.shape
    idx = np.arange(W, dtype=np.float64)[None, :].repeat(H, 0)
    big = 1e9
    left = np.where(~m, idx, -big)
    left = np.maximum.accumulate(left, axis=1)
    right = np.where(~m, idx, big)
    right = np.minimum.accumulate(right[:, ::-1], axis=1)[:, ::-1]
    g = np.minimum(idx - left, right - idx)                        # Abstand in der Zeile
    g2 = g * g
    d2 = g2.copy()
    R = int(min(H, np.sqrt(np.max(g2[m])) + 1)) if m.any() else 0
    for dy in range(1, H):
        if dy * dy >= d2.max():
            break
        up = np.full_like(g2, big * big)
        up[dy:] = g2[:-dy]
        dn = np.full_like(g2, big * big)
        dn[:-dy] = g2[dy:]
        d2 = np.minimum(d2, np.minimum(up, dn) + dy * dy)
        if dy > R and dy * dy > d2[m].max():
            break
    d = np.sqrt(d2)
    d[~m] = 0.0
    return d[1:-1, 1:-1]


def _dil8(a: np.ndarray, fill) -> np.ndarray:
    p = np.pad(a, 1, constant_values=fill)
    H, W = a.shape
    out = a.copy()
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            if dy == 1 and dx == 1:
                continue
            np.maximum(out, p[dy:dy + H, dx:dx + W], out=out)
    return out


def _reconstruct(seed: np.ndarray, lim: np.ndarray) -> np.ndarray:
    """Morphologische Rekonstruktion durch Dilatation (8er-Nachbarschaft) von seed unter lim."""
    g = np.minimum(seed, lim)
    for _ in range(int(g.shape[0] * g.shape[1])):
        n = np.minimum(_dil8(g, -np.inf), lim)
        if np.array_equal(n, g):
            break
        g = n
    return g


def hmax_markers(f: np.ndarray, mask: np.ndarray, h: float) -> np.ndarray:
    """Marker = regionale Maxima der h-Maxima-Transformation HMAX_h(f) = R_f(f − h): Gipfel, die weniger als h über
    ihrem Sattel liegen, bilden mit dem Nachbargipfel einen gemeinsamen Marker."""
    lim = np.where(mask, f, -np.inf)
    rec = _reconstruct(np.where(mask, f - h, -np.inf), lim)
    eps = 1e-3
    rec2 = _reconstruct(np.where(mask, rec - eps, -np.inf), np.where(mask, rec, -np.inf))
    with np.errstate(invalid="ignore"):
        return mask & (np.where(mask, rec - rec2, 0.0) > eps / 2)


def _nb8(L: np.ndarray):
    p = np.pad(L, 1)
    H, W = L.shape
    return [p[dy:dy + H, dx:dx + W] for dy in (0, 1, 2) for dx in (0, 1, 2) if not (dy == 1 and dx == 1)]


def watershed(mask: np.ndarray, h: float = 1.0, step: float = 0.5) -> tuple[np.ndarray, dict]:
    """Binärmaske -> getrennte Binärmaske und Kennzahlen (Anzahl Marker, Becken, Trennpixel)."""
    m = np.asarray(mask, bool)
    if not m.any():
        return m.copy(), {"markers": 0, "lines": 0}
    D = edt(m)
    mk = hmax_markers(D, m, float(h))
    L, n = label(mk, conn=8)
    L = L.astype(np.int32)
    BOUND = -1
    levels = np.arange(np.floor(D.max() / step) * step, 0, -step)
    for v in levels:
        allowed = m & (D >= v - 1e-9)
        for _ in range(10 * (D.shape[0] + D.shape[1])):
            free = allowed & (L == 0)
            if not free.any():
                break
            nbs = _nb8(L)
            mx = np.max(np.stack(nbs), axis=0)
            pos = [np.where(x > 0, x, np.iinfo(np.int32).max) for x in nbs]
            mn = np.min(np.stack(pos), axis=0)
            cand = free & (mx > 0)
            if not cand.any():
                break
            L = np.where(cand & (mn == mx), mx, np.where(cand & (mn != mx), BOUND, L)).astype(np.int32)
    # 8er-Nachbarn mit verschiedenen Becken (gleichzeitig geflutet) – eines der beiden wird Trennlinie
    H, W = L.shape
    p = np.pad(L, 1)
    for dy, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
        nb = p[1 + dy:1 + dy + H, 1 + dx:1 + dx + W]
        clash = (L > 0) & (nb > 0) & (nb != L)
        L = np.where(clash & (L > nb), BOUND, L)
        p = np.pad(L, 1)
    out = m & (L != BOUND)
    return out, {"markers": int(n), "lines": int((m & (L == BOUND)).sum())}
