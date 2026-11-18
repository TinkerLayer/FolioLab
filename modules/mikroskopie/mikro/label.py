"""Zusammenhaengende Komponenten in einer Binaermaske (4er- oder 8er-Nachbarschaft), nur numpy.

Arbeitet auf Laeufen (Runs) je Zeile: die Laeufe benachbarter Zeilen werden mit Union-Find verbunden.
Das ist auch bei grossen Bildern schnell genug, weil nur Laeufe, nicht Pixel, in Python verarbeitet werden.
"""
from __future__ import annotations

import numpy as np


def label(mask: np.ndarray, conn: int = 8) -> tuple[np.ndarray, int]:
    """Liefert (Labelbild int32 mit 0 = Hintergrund, Anzahl Komponenten)."""
    m = np.asarray(mask, dtype=bool)
    H, W = m.shape
    out = np.zeros((H, W), dtype=np.int32)
    if not m.any():
        return out, 0
    p = np.zeros((H, W + 2), dtype=np.int8)
    p[:, 1:-1] = m
    d = np.diff(p, axis=1)
    rs, cs = np.nonzero(d == 1)          # Laufbeginn (Spalte inkl.)
    _, ce = np.nonzero(d == -1)          # Laufende (Spalte exkl.)
    n = len(rs)
    parent = list(range(n))

    def find(i):
        root = i
        while parent[root] != root:
            root = parent[root]
        while parent[i] != root:
            parent[i], i = root, parent[i]
        return root

    ptr = np.searchsorted(rs, np.arange(H + 1))
    csl, cel = cs.tolist(), ce.tolist()
    slack = 1 if conn == 8 else 0       # 8er: diagonal beruehrende Laeufe gehoeren zusammen
    for y in range(1, H):
        a0, a1, b0, b1 = int(ptr[y - 1]), int(ptr[y]), int(ptr[y]), int(ptr[y + 1])
        if a0 == a1 or b0 == b1:
            continue
        i, j = a0, b0
        while i < a1 and j < b1:
            if csl[i] < cel[j] + slack and csl[j] < cel[i] + slack:
                ri, rj = find(i), find(j)
                if ri != rj:
                    if ri < rj:
                        parent[rj] = ri
                    else:
                        parent[ri] = rj
            if cel[i] < cel[j]:
                i += 1
            else:
                j += 1
    roots = np.array([find(i) for i in range(n)], dtype=np.int64)
    uniq, lab = np.unique(roots, return_inverse=True)
    lab = (lab + 1).astype(np.int32)
    lengths = ce - cs
    total = int(lengths.sum())
    rows = np.repeat(rs, lengths)
    starts = np.repeat(cs, lengths)
    offs = np.arange(total) - np.repeat(np.cumsum(lengths) - lengths, lengths)
    out[rows, starts + offs] = np.repeat(lab, lengths)
    return out, int(len(uniq))


def fill_holes(mask: np.ndarray) -> np.ndarray:
    """Loecher (Hintergrund ohne Verbindung zum Bildrand, 4er-Nachbarschaft) fuellen."""
    m = np.asarray(mask, dtype=bool)
    bg, n = label(~m, conn=4)
    if n == 0:
        return m.copy()
    border = np.unique(np.concatenate([bg[0], bg[-1], bg[:, 0], bg[:, -1]]))
    keep = np.zeros(n + 1, dtype=bool)
    keep[border] = True
    keep[0] = True
    return m | ~keep[bg]
