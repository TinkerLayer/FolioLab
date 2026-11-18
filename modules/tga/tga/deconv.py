"""Trennung überlappender DTG-Stufen durch Anpassung von Fraser-Suzuki-Spitzen (Fraser & Suzuki 1969; Verfahren nach
Perejón u. a. 2011). Jede Spitze: Lage, Fläche (= Massenverlust in %), linke und rechte Halbwertsbreite.

Anpassung nach Levenberg-Marquardt mit numerischer Jacobi-Matrix und Grenzen (Projektion), ohne SciPy.
Vorlage „Biomasse“: drei Komponenten Hemicellulose, Cellulose, Lignin als Startwerte (Konzept nach Yang u. a. 2007);
die Startwerte sind Vorschläge und werden angepasst.
"""
from __future__ import annotations

import numpy as np

from .library import fs_peak

PRESETS = {
    "biomass": {"label": "Biomasse: Hemicellulose, Cellulose, Lignin (Startwerte)", "ref": "yang2007",
                "peaks": [{"name": "Hemicellulose", "x0": 290, "hwl": 35, "hwr": 25},
                          {"name": "Cellulose", "x0": 350, "hwl": 22, "hwr": 15},
                          {"name": "Lignin", "x0": 380, "hwl": 120, "hwr": 120}]},
}


def _model(x, p):
    y = np.zeros(len(x))
    for k in range(0, len(p), 4):
        y += fs_peak(x, p[k], p[k + 1], p[k + 2], p[k + 3])
    return y


def fit(x: np.ndarray, y: np.ndarray, peaks: list[dict], fix_pos: bool = False, iters: int = 200) -> dict:
    """peaks: [{name, x0, area?, hwl, hwr}]; gibt angepasste Spitzen, Summe, Residuum und R²."""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    if len(x) < 20 or not peaks:
        raise ValueError("Für die Trennung einen Bereich mit DTG-Daten und mindestens eine Spitze angeben.")
    tot = float(np.trapezoid(y, x) if hasattr(np, "trapezoid") else np.trapz(y, x))
    p = []
    for pk in peaks:
        area = pk.get("area")
        if area in (None, ""):
            area = max(0.1, tot / len(peaks))
        p += [float(pk["x0"]), float(area), float(pk.get("hwl", 20)), float(pk.get("hwr", 20))]
    p = np.array(p)
    lo = np.tile([x.min(), 0.0, 1.0, 1.0], len(peaks))
    hi = np.tile([x.max(), 100.0, 0.5 * np.ptp(x), 0.5 * np.ptp(x)], len(peaks))
    free = np.ones(len(p), bool)
    if fix_pos:
        free[0::4] = False
    lam = 1e-2

    def resid(q):
        return _model(x, q) - y

    r = resid(p)
    cost = float(r @ r)
    for _ in range(iters):
        J = np.zeros((len(x), len(p)))
        for j in np.nonzero(free)[0]:
            h = 1e-4 * max(1.0, abs(p[j]))
            q = p.copy()
            q[j] += h
            J[:, j] = (resid(q) - r) / h
        A = J.T @ J
        g = J.T @ r
        improved = False
        for _ in range(10):
            step = np.linalg.lstsq(A + lam * np.diag(np.diag(A) + 1e-12), -g, rcond=None)[0]
            q = np.clip(p + step, lo, hi)
            rq = resid(q)
            cq = float(rq @ rq)
            if cq < cost:
                p, r, cost = q, rq, cq
                lam = max(lam / 3, 1e-9)
                improved = True
                break
            lam *= 4
        if not improved or abs(cost) < 1e-18:
            break
    fitted = _model(x, p)
    sst = float(np.sum((y - y.mean()) ** 2)) or 1e-30
    out = []
    for k, pk in enumerate(peaks):
        x0, area, hwl, hwr = p[4 * k:4 * k + 4]
        out.append({"name": pk.get("name") or f"Spitze {k + 1}", "x0": float(x0), "area": float(area), "hwl": float(hwl),
                    "hwr": float(hwr), "y": fs_peak(x, x0, area, hwl, hwr).astype(np.float32)})
    return {"x": x.astype(np.float32), "y": y.astype(np.float32), "fit": fitted.astype(np.float32),
            "residual": (y - fitted).astype(np.float32), "peaks": out, "r2": 1 - cost / sst, "total": tot}


def guess(x: np.ndarray, y: np.ndarray, n: int | None = None) -> list[dict]:
    """Startwerte aus Spitzen und Schultern (Minima der 2. Ableitung)."""
    from .process import savgol
    from .steps import _peaks
    y = np.nan_to_num(np.asarray(y, float))
    d2 = -savgol(y, 15, 3, 2)
    cand = sorted(_peaks(d2), key=lambda t: -t[1])
    xs = sorted({int(i) for i, p in cand[: (n or 4)] if y[i] > 0.05 * y.max()})
    return [{"name": f"Spitze {k + 1}", "x0": float(x[i]), "hwl": 20.0, "hwr": 15.0} for k, i in enumerate(xs)]
