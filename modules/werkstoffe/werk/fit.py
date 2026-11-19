"""Gemeinsame Ausgleichsrechnung: Gerade mit Standardfehlern, multiple lineare Regression, Levenberg–Marquardt."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

_SDK = Path(__file__).resolve().parents[3] / "sdk" / "python"
if _SDK.is_dir() and str(_SDK) not in sys.path:
    sys.path.insert(0, str(_SDK))

from labcalc.stats import t_ppf  # noqa: E402


class FitError(ValueError):
    pass


def linreg(x, y) -> dict:
    """y = a + b·x, kleinste Quadrate. Standardfehler, R², 95-%-Vertrauensbereiche (Student t, n − 2)."""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    n = len(x)
    if n < 2 or np.ptp(x) == 0:
        raise FitError("Für eine Gerade braucht es mindestens zwei verschiedene x-Werte")
    xm, ym = x.mean(), y.mean()
    sxx = float(((x - xm) ** 2).sum())
    b = float(((x - xm) * (y - ym)).sum() / sxx)
    a = float(ym - b * xm)
    res = y - (a + b * x)
    sst = float(((y - ym) ** 2).sum())
    r2 = 1 - float((res ** 2).sum()) / sst if sst > 0 else 1.0
    out = {"a": a, "b": b, "n": n, "r2": r2, "xm": float(xm), "sxx": sxx}
    if n > 2:
        s = math.sqrt(float((res ** 2).sum()) / (n - 2))
        sb = s / math.sqrt(sxx)
        sa = s * math.sqrt(1 / n + xm ** 2 / sxx)
        t = t_ppf(0.975, n - 2)
        out.update(s=s, sa=sa, sb=sb, t=t, cov=-xm * s ** 2 / sxx)
    else:
        out.update(s=None, sa=None, sb=None, t=None, cov=None)
    return out


def predict_band(fit: dict, x0) -> tuple[np.ndarray, np.ndarray]:
    """95-%-Vertrauensband der Geraden an x0 (± t·s·√(1/n + (x0 − x̄)²/Sxx))."""
    x0 = np.asarray(x0, float)
    yhat = fit["a"] + fit["b"] * x0
    if fit.get("s") is None:
        return yhat, np.full_like(yhat, np.nan)
    hw = fit["t"] * fit["s"] * np.sqrt(1 / fit["n"] + (x0 - fit["xm"]) ** 2 / fit["sxx"])
    return yhat, hw


def mlinreg(X, y) -> dict:
    """y = X·β (X mit Spalte 1 für den Achsenabschnitt): β, Standardfehler, R²."""
    X = np.asarray(X, float)
    y = np.asarray(y, float)
    n, p = X.shape
    if n < p:
        raise FitError(f"Zu wenige Punkte ({n}) für {p} Parameter")
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    res = y - X @ beta
    sst = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - float(res @ res) / sst if sst > 0 else 1.0
    se = [None] * p
    if n > p:
        s2 = float(res @ res) / (n - p)
        try:
            cov = s2 * np.linalg.inv(X.T @ X)
            se = [float(math.sqrt(max(cov[i, i], 0))) for i in range(p)]
        except np.linalg.LinAlgError:
            pass
    return {"beta": [float(b) for b in beta], "se": se, "r2": r2, "n": n, "p": p,
            "t": t_ppf(0.975, n - p) if n > p else None}


def nelder_mead(f, x0, step=None, maxit: int = 4000, tol: float = 1e-10) -> tuple[np.ndarray, float]:
    """Minimum von f (Simplex-Verfahren nach Nelder und Mead, Standardkoeffizienten)."""
    x0 = np.asarray(x0, float)
    n = len(x0)
    step = np.asarray(step if step is not None else np.maximum(np.abs(x0) * 0.1, 0.1), float)
    pts = [x0] + [x0 + np.eye(n)[i] * step[i] for i in range(n)]
    vals = [f(p) for p in pts]
    for _ in range(maxit):
        o = np.argsort(vals)
        pts = [pts[i] for i in o]
        vals = [vals[i] for i in o]
        if abs(vals[-1] - vals[0]) <= tol * (abs(vals[0]) + tol) and np.max(np.abs(np.array(pts) - pts[0])) < 1e-9:
            break
        c = np.mean(pts[:-1], axis=0)
        xr = c + (c - pts[-1])
        fr = f(xr)
        if fr < vals[0]:
            xe = c + 2 * (c - pts[-1])
            fe = f(xe)
            pts[-1], vals[-1] = (xe, fe) if fe < fr else (xr, fr)
        elif fr < vals[-2]:
            pts[-1], vals[-1] = xr, fr
        else:
            xc = c + 0.5 * (pts[-1] - c)
            fc = f(xc)
            if fc < vals[-1]:
                pts[-1], vals[-1] = xc, fc
            else:
                pts = [pts[0]] + [pts[0] + 0.5 * (p - pts[0]) for p in pts[1:]]
                vals = [vals[0]] + [f(p) for p in pts[1:]]
    i = int(np.argmin(vals))
    return pts[i], float(vals[i])


def lm(model, p0, x, y, w=None, fixed=None, lo=None, hi=None, maxit: int = 200, tol: float = 1e-10) -> dict:
    """Levenberg–Marquardt mit numerischer Jacobi-Matrix. model(x, p) -> y. Gibt p, Standardfehler, χ² zurück."""
    p = np.asarray(p0, float).copy()
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    w = np.ones_like(y) if w is None else np.asarray(w, float)
    free = np.ones(len(p), bool)
    if fixed is not None:
        free[np.asarray(fixed, int)] = False
    lo = np.full(len(p), -np.inf) if lo is None else np.asarray(lo, float)
    hi = np.full(len(p), np.inf) if hi is None else np.asarray(hi, float)

    def clip(q):
        return np.minimum(np.maximum(q, lo), hi)

    def resid(q):
        return (model(x, q) - y) * np.sqrt(w)
    r = resid(p)
    chi = float(r @ r)
    lam = 1e-3
    for _ in range(maxit):
        J = np.zeros((len(y), int(free.sum())))
        k = 0
        for i in np.flatnonzero(free):
            h = 1e-6 * max(abs(p[i]), 1e-6)
            q = p.copy()
            q[i] += h
            J[:, k] = (resid(q) - r) / h
            k += 1
        A = J.T @ J
        g = J.T @ r
        improved = False
        for _ in range(12):
            try:
                step = np.linalg.solve(A + lam * np.diag(np.diag(A) + 1e-12), -g)
            except np.linalg.LinAlgError:
                lam *= 10
                continue
            q = p.copy()
            q[free] += step
            q = clip(q)
            rq = resid(q)
            cq = float(rq @ rq)
            if cq < chi:
                done = chi - cq < tol * max(chi, 1e-300)
                p, r, chi = q, rq, cq
                lam = max(lam / 10, 1e-12)
                improved = True
                break
            lam *= 10
        if not improved or done:
            break
    dof = max(len(y) - int(free.sum()), 1)
    se = np.full(len(p), np.nan)
    try:
        J = np.zeros((len(y), int(free.sum())))
        k = 0
        for i in np.flatnonzero(free):
            h = 1e-6 * max(abs(p[i]), 1e-6)
            q = p.copy()
            q[i] += h
            J[:, k] = (resid(q) - r) / h
            k += 1
        cov = np.linalg.inv(J.T @ J) * chi / dof
        se[free] = np.sqrt(np.maximum(np.diag(cov), 0))
    except np.linalg.LinAlgError:
        pass
    return {"p": p, "se": se, "chi2": chi, "dof": dof}
