"""Bibliothekssuche und Mischungsanalyse.

Trefferqualität (HQI, 0–100, 100 = deckungsgleich), berechnet nur im gemeinsamen, gewählten Bereich:
  corr     Korrelation:            HQI = 100 · r²   (r: Pearson-Korrelation, negative r zählen als 0)
  euclid   Euklidischer Abstand:   HQI = 100 · (1 − d²/2) der auf Länge 1 normierten Spektren (= Kosinus)
  dcorr    1. Ableitung, Korrelation;  deuclid  1. Ableitung, euklidisch (betonen Bandenlagen, unempfindlich
           gegen Basislinien)
  peaks    Peaksuche: Anteil der Banden, die sich innerhalb der Toleranz entsprechen (beidseitig gewichtet)
Deckt eine Referenz den gewählten Bereich nur teilweise ab, sinkt der HQI anteilig (unter 90 % Abdeckung).

Mischungen: Kombinationen aus 2–3 (bis 4) Referenzen werden mit nicht-negativen Gewichten und freiem
Achsenabschnitt an das Spektrum angepasst; HQI = 100 · R² der Anpassung. Gewichte sind Anteile an der Absorbanz,
keine Massenanteile.
"""
from __future__ import annotations

from itertools import combinations

import numpy as np

from .library import GRID, Library, deriv

ALGOS = {
    "corr": ("Korrelation", "Correlation"),
    "euclid": ("Euklidischer Abstand", "Euclidean distance"),
    "dcorr": ("1. Ableitung, Korrelation", "First derivative, correlation"),
    "deuclid": ("1. Ableitung, euklidisch", "First derivative, Euclidean"),
    "peaks": ("Peaksuche", "Peak search"),
}
DEFAULT_EXCLUDE = [[2400.0, 2280.0]]          # CO₂


def region_mask(include=None, exclude=None) -> np.ndarray:
    inc = [r for r in (include or []) if r and len(r) == 2]
    m = np.zeros(len(GRID), bool) if inc else np.ones(len(GRID), bool)
    for a, b in inc:
        lo, hi = sorted((float(a), float(b)))
        m |= (GRID >= lo) & (GRID <= hi)
    for r in exclude or []:
        if r and len(r) == 2:
            lo, hi = sorted((float(r[0]), float(r[1])))
            m &= ~((GRID >= lo) & (GRID <= hi))
    return m


def _scores(q: np.ndarray, L: np.ndarray, mask: np.ndarray, kind: str, mats=None):
    """HQI und Abdeckung für alle Zeilen von L, je Zeile im gemeinsamen belegten Bereich.

    mats: (L0, W, L0²) aus Library.mats(); dann nur Matrix-Vektor-Produkte, ohne Kopien der ganzen Bibliothek."""
    wq = np.isfinite(q) & mask
    nq = int(wq.sum())
    if nq < 10 or not len(L):
        return np.zeros(len(L)), np.zeros(len(L))
    if mats is None:
        W = np.isfinite(L)
        L0 = np.where(W, L, 0).astype(np.float32)
        mats = (L0, W.astype(np.float32), L0 * L0)
    L0, Wf, L2 = mats
    m = wq.astype(np.float32)
    q0 = np.where(wq, q, 0.0).astype(np.float32)
    n = (Wf @ m).astype(np.float64)
    sql = (L0 @ q0).astype(np.float64)
    sqq = (Wf @ (q0 * q0)).astype(np.float64)
    sll = (L2 @ m).astype(np.float64)
    with np.errstate(invalid="ignore", divide="ignore"):
        if kind == "corr":
            sq = (Wf @ q0).astype(np.float64)
            sl = (L0 @ m).astype(np.float64)
            cov = sql - sq * sl / n
            vq = sqq - sq * sq / n
            vl = sll - sl * sl / n
            r = cov / np.sqrt(vq * vl)
            hqi = 100 * np.clip(np.nan_to_num(r), 0, 1) ** 2
        else:
            cos = sql / np.sqrt(sqq * sll)
            hqi = 100 * np.clip(np.nan_to_num(cos), 0, 1)
    cov_frac = n / nq
    hqi = hqi * np.minimum(1.0, cov_frac / 0.9)
    hqi[n < 10] = 0
    return hqi, cov_frac


def _peak_scores(q: np.ndarray, lib: Library, mask: np.ndarray, tol: float = 6.0):
    from . import peaks as PK
    v = np.isfinite(q) & mask
    p = PK.find(GRID[v], np.nan_to_num(q[v]).astype(float), "A", {"prominence": 1.5, "distance": 6, "max": 40})
    qx = np.array([a["x"] for a in p])
    qw = np.array([a["rel"] for a in p])
    lo, hi = GRID[v].min(), GRID[v].max()
    out = np.zeros(len(lib.entries))
    cover = np.ones(len(lib.entries))
    if not len(qx):
        return out, cover
    for i, (lx, lw) in enumerate(lib.peaklists()):
        lx, lw = np.asarray(lx), np.asarray(lw)
        sel = (lx >= lo) & (lx <= hi) & mask[np.clip(np.searchsorted(GRID, lx), 0, len(GRID) - 1)] if len(lx) else []
        lx, lw = (lx[sel], lw[sel]) if len(lx) else (lx, lw)
        if not len(lx):
            continue
        dq = np.abs(qx[:, None] - lx[None, :])
        tq = tol + 0.004 * qx[:, None]
        mq = (dq <= tq).any(1)
        ml = (dq <= tq).any(0)
        a = float((qw * mq).sum() / qw.sum())
        b = float((lw * ml).sum() / lw.sum())
        out[i] = 100 * np.sqrt(a * b)
    return out, cover


def lib_scores(q: np.ndarray, lib: Library, mask: np.ndarray, algo: str):
    if algo == "peaks":
        return _peak_scores(q, lib, mask)
    if algo in ("dcorr", "deuclid"):
        return _scores(deriv(q), lib.D, mask, "corr" if algo == "dcorr" else "euclid", lib.mats("D"))
    return _scores(q, lib.G, mask, algo, lib.mats("G"))


def search(q: np.ndarray, libs: list[Library], algo: str = "corr", include=None, exclude=None, n: int = 25,
           category: str | None = None, n_overlay: int = 10, collapse: bool = False) -> dict:
    """collapse: je Stoff (Eintragsfeld "group", sonst je Eintrag) nur den besten Treffer zeigen; "similar" zählt
    die weiteren Spektren desselben Stoffs unter den Treffern."""
    mask = region_mask(include, exclude)
    hits = []
    for lib in libs:
        if not lib.entries:
            continue
        hqi, cov = lib_scores(q, lib, mask, algo)
        for i, e in enumerate(lib.entries):
            if category and e.get("category") != category:
                continue
            hits.append({"lib": lib.id, "lib_name": lib.name, "id": e["id"], "name": e["name"],
                         "category": e.get("category", ""), "cas": e.get("cas", ""), "source": e.get("source", ""),
                         "comment": e.get("comment", ""), **lib.cite_fields(e),
                         "hqi": round(float(hqi[i]), 2), "coverage": round(float(min(1.0, cov[i])), 3), "_i": i, "_lib": lib,
                         "_g": (lib.id, e.get("group") or e["id"])})
    hits.sort(key=lambda h: -h["hqi"])
    if collapse:
        best, out = {}, []
        for h in hits:
            g = h["_g"]
            if g in best:
                best[g]["similar"] += 1
                continue
            h["similar"] = 0
            best[g] = h
            out.append(h)
        hits = out
    hits = hits[:n]
    for h in hits:
        h.pop("_g", None)
    wq = np.isfinite(q) & mask
    for k, h in enumerate(hits):
        lib, i = h.pop("_lib"), h.pop("_i")
        if k < n_overlay:
            h["y"] = scaled_overlay(q, lib.G[i], wq)
    for k, h in enumerate(hits):
        h["rank"] = k + 1
    return {"algo": algo, "hits": hits, "mask": mask, "query": q}


def scaled_overlay(q: np.ndarray, l: np.ndarray, wq: np.ndarray) -> np.ndarray:
    """Referenz auf die Höhe des Suchspektrums gebracht (kleinste Quadrate im gemeinsamen Bereich)."""
    m = wq & np.isfinite(l)
    if m.sum() < 5:
        return l
    a = float(np.dot(q[m], l[m]) / (np.dot(l[m], l[m]) or 1.0))
    return (l * a).astype(np.float32)


# ----------------------------------------------------------------------------- Mischungen
def _nnls_small(G: np.ndarray, b: np.ndarray):
    """min |y - Xw|² mit w ≥ 0 für kleine k über alle Teilmengen (G = XᵀX, b = Xᵀy). Gibt (w, Abnahme der SSQ)."""
    k = len(b)
    best_w, best_gain = np.zeros(k), 0.0
    for r in range(1, k + 1):
        for S in combinations(range(k), r):
            S = list(S)
            try:
                w = np.linalg.solve(G[np.ix_(S, S)], b[S])
            except np.linalg.LinAlgError:
                continue
            if np.any(w <= 0):
                continue
            gain = float(2 * w @ b[S] - w @ G[np.ix_(S, S)] @ w)
            if gain > best_gain:
                best_gain = gain
                best_w = np.zeros(k)
                best_w[S] = w
    return best_w, best_gain


def _gkey(c):
    lib, i = c[1], c[2]
    return lib.id, lib.entries[i].get("group") or lib.entries[i]["id"]


def _distinct(cands, k):
    """Die besten k Kandidaten, je Stoff nur einer (sonst füllen zehn PE-Spektren die ganze Auswahl)."""
    out, seen = [], set()
    for c in cands:
        g = _gkey(c)
        if g in seen:
            continue
        seen.add(g)
        out.append(c)
        if len(out) >= k:
            break
    return out


def mixture(q: np.ndarray, libs: list[Library], include=None, exclude=None, max_components: int = 3,
            pool: int = 24, top: int = 8) -> dict:
    mask = region_mask(include, exclude)
    wq = np.isfinite(q) & mask
    # Kandidaten: beste Einzeltreffer plus beste Treffer für den Rest nach Abzug des besten Einzeltreffers
    cands = []
    for lib in libs:
        if not lib.entries:
            continue
        hqi, cov = _scores(q, lib.G, mask, "corr", lib.mats("G"))
        for i, e in enumerate(lib.entries):
            if cov[i] >= 0.9:
                cands.append((float(hqi[i]), lib, i))
    if not cands:
        return {"combos": [], "note": "Keine Referenz deckt den Bereich des Spektrums ab."}
    cands.sort(key=lambda c: -c[0])
    chosen = _distinct(cands, pool)
    best = chosen[0]
    l0 = best[1].G[best[2]]
    m0 = wq & np.isfinite(l0)
    a = float(np.dot(q[m0], l0[m0]) / (np.dot(l0[m0], l0[m0]) or 1))
    resid = np.where(np.isfinite(l0), q - a * l0, q)
    resid = np.clip(resid, 0, None).astype(np.float32)
    seen = {_gkey(c) for c in chosen}
    rc = []
    for lib in libs:
        if not lib.entries:
            continue
        hqi, cov = _scores(resid, lib.G, mask, "corr", lib.mats("G"))
        for i in range(len(lib.entries)):
            if cov[i] >= 0.9 and _gkey((0, lib, i)) not in seen:
                rc.append((float(hqi[i]), lib, i))
    rc.sort(key=lambda c: -c[0])
    chosen += _distinct(rc, max(4, pool // 3))
    X = np.array([c[1].G[c[2]] for c in chosen], dtype=np.float64)
    m = wq & np.all(np.isfinite(X), axis=0)
    if m.sum() < 20:
        return {"combos": [], "note": "Zu wenig gemeinsamer Bereich."}
    y = q[m].astype(np.float64)
    Xm = X[:, m]
    yc = y - y.mean()
    Xc = Xm - Xm.mean(1, keepdims=True)
    Gm = Xc @ Xc.T
    bm = Xc @ yc
    sst = float(yc @ yc) or 1.0
    k_max = max(1, min(int(max_components), 4))
    P = len(chosen)
    if k_max == 4:
        P = min(P, 16)
    results = []
    for k in range(1, k_max + 1):
        for S in combinations(range(P), k):
            S = list(S)
            w, gain = _nnls_small(Gm[np.ix_(S, S)], bm[S])
            if np.count_nonzero(w) != k:
                continue
            r2 = gain / sst
            results.append((100 * r2, S, w))
    # nach Wertung mit Sparsamkeitsabzug sortieren, bevor gekürzt wird; sonst verdrängen viele "beste Paare + x"
    # mit minimal höherem HQI die eigentliche Lösung aus der Liste
    results.sort(key=lambda t: -(t[0] - 2.0 * (len(t[1]) - 1)))
    combos, seen_sets = [], set()
    for hqi, S, w in results:
        key = frozenset(S)
        if key in seen_sets:
            continue
        seen_sets.add(key)
        comps = []
        for j, wj in zip(S, w):
            lib, i = chosen[j][1], chosen[j][2]
            comps.append({"lib": lib.id, "lib_name": lib.name, "id": lib.entries[i]["id"], "name": lib.entries[i]["name"],
                          "source": lib.entries[i].get("source", ""), **lib.cite_fields(lib.entries[i]),
                          "weight": float(wj), "_j": j})
        tot = sum(c["weight"] * float(np.sum(np.clip(Xm[c["_j"]], 0, None))) for c in comps) or 1.0
        for c in comps:
            c["frac"] = c["weight"] * float(np.sum(np.clip(Xm[c.pop("_j")], 0, None))) / tot
        combos.append({"hqi": round(hqi, 2), "n": len(S), "components": comps, "_S": S, "_w": w})
        if len(combos) >= top * 3:
            break
    # Mehr Komponenten nur, wenn sie spürbar besser passen (Sparsamkeit)
    for c in combos:
        c["score"] = c["hqi"] - 2.0 * (c["n"] - 1)
    combos.sort(key=lambda c: -c["score"])
    combos = combos[:top]
    for c in combos:
        S, w = c.pop("_S"), c.pop("_w")
        comp_full = []
        for j, wj in zip(S, w):
            comp_full.append((X[j] * wj).astype(np.float32))
        fit = np.sum(comp_full, axis=0)
        off = float(np.mean(y) - np.mean(fit[m]))
        c["fit"] = (fit + off).astype(np.float32)
        c["offset"] = off
        for comp, yy in zip(c["components"], comp_full):
            comp["y"] = yy
        res = np.full(len(GRID), np.nan, dtype=np.float32)
        res[m] = (y - (fit[m] + off)).astype(np.float32)
        c["residual"] = res
    return {"combos": combos, "mask": mask, "query": q, "note": ""}
