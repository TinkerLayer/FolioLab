"""Weibull-Statistik von Festigkeitswerten und linear-elastische Bruchmechanik.

Weibull (zweiparametrig): P_f(σ) = 1 − exp(−(σ/σ₀)^m).
- Rangregression: F_i = (i − 0,3)/(n + 0,4) (Bernard), Gerade ln ln(1/(1−F)) = m ln σ − m ln σ₀ (kleinste Quadrate in
  y, wie in ISO 20501 als Alternative beschrieben)
- Maximum Likelihood (ASTM C1239): Σ σ_i^m ln σ_i / Σ σ_i^m − 1/m − (1/n) Σ ln σ_i = 0, σ₀ = (Σ σ_i^m / n)^(1/m);
  m wird ohne Korrekturfaktor angegeben (für kleine n systematisch zu gross; C1239 gibt Faktoren)
- Vertrauensbereiche: parametrischer Bootstrap (Efron & Tibshirani) mit festem Startwert
- Grösseneffekt: σ₂/σ₁ = (V_eff1/V_eff2)^(1/m); effektive Volumina für Biegung (Quinn 2003):
  3-Punkt V_eff = V/(2(m+1)²), 4-Punkt V_eff = V (m L_i/L + 1)/(2(m+1)²)

Bruchmechanik (ASTM E399):
- SENB (S = 4W): K = P S/(B W^1,5) · f(a/W), f = 3√α [1,99 − α(1−α)(2,15 − 3,93α + 2,7α²)] / [2(1+2α)(1−α)^1,5]
- C(T): K = P/(B √W) · f(a/W), f = (2+α)(0,886 + 4,64α − 13,32α² + 14,72α³ − 5,6α⁴)/(1−α)^1,5
- Gültigkeit: a, B, W − a ≥ 2,5 (K/Rp0,2)²; 0,45 ≤ a/W ≤ 0,55; P_max/P_Q ≤ 1,10
- kritische Risslänge a_c = (1/π) (K_Ic/(Y σ))² (Anderson)
"""
from __future__ import annotations

import math

import numpy as np

from .fit import linreg

REFS = {"weibull": ["weibull1951"], "ranks": ["bernard1953"], "mle": ["astmc1239"], "boot": ["efron1993"],
        "size": ["weibull1951", "quinn2003"], "e399": ["astme399", "anderson"], "crack": ["anderson"]}


class RelError(ValueError):
    pass


def _clean(x):
    x = np.asarray([float(v) for v in x if v is not None and np.isfinite(float(v))], float)
    if len(x) < 3:
        raise RelError("Mindestens drei Festigkeitswerte nötig")
    if np.any(x <= 0):
        raise RelError("Festigkeiten müssen positiv sein")
    return np.sort(x)


def weibull_lsq(x) -> dict:
    x = _clean(x)
    n = len(x)
    F = (np.arange(1, n + 1) - 0.3) / (n + 0.4)
    X = np.log(x)
    Y = np.log(-np.log(1 - F))
    f = linreg(X, Y)
    m = f["b"]
    s0 = math.exp(-f["a"] / m)
    return {"m": m, "sigma0": s0, "r2": f["r2"], "n": n, "x": x.tolist(), "F": F.tolist(), "X": X.tolist(),
            "Y": Y.tolist()}


def weibull_mle(x) -> dict:
    x = _clean(x)
    n = len(x)
    lx = np.log(x)
    xs = x / x.max()                                     # Überlauf vermeiden

    def g(m):
        w = xs ** m
        return float((w * lx).sum() / w.sum() - 1 / m - lx.mean())
    lo, hi = 0.05, 1.0
    while g(hi) < 0 and hi < 1e4:
        hi *= 2
    if g(hi) < 0:
        raise RelError("Maximum-Likelihood ohne Lösung (alle Werte gleich?)")
    for _ in range(64):
        mid = 0.5 * (lo + hi)
        if g(mid) < 0:
            lo = mid
        else:
            hi = mid
    m = 0.5 * (lo + hi)
    s0 = x.max() * float(((xs ** m).sum() / n) ** (1 / m))
    return {"m": m, "sigma0": s0, "n": n}


def bootstrap(x, method: str = "mle", B: int = 1000, seed: int = 20261118, level: float = 0.90) -> dict:
    """Parametrischer Bootstrap: B Stichproben aus der angepassten Verteilung, gleiches Verfahren; Perzentilbereich."""
    x = _clean(x)
    fit = weibull_mle(x) if method == "mle" else weibull_lsq(x)
    rng = np.random.default_rng(seed)
    ms, ss = [], []
    for _ in range(int(B)):
        smp = fit["sigma0"] * rng.weibull(fit["m"], len(x))
        try:
            f = weibull_mle(smp) if method == "mle" else weibull_lsq(smp)
        except RelError:
            continue
        ms.append(f["m"])
        ss.append(f["sigma0"])
    q = [(1 - level) / 2 * 100, (1 + level) / 2 * 100]
    return {"m": fit["m"], "sigma0": fit["sigma0"], "m_ci": np.percentile(ms, q).tolist(),
            "sigma0_ci": np.percentile(ss, q).tolist(), "B": len(ms), "level": level, "seed": seed}


def quantile(m: float, s0: float, P: float) -> float:
    """Festigkeit bei Ausfallwahrscheinlichkeit P."""
    return s0 * (-math.log(1 - P)) ** (1 / m)


def v_eff(kind: str, V: float, m: float, Li: float | None = None, L: float | None = None) -> float:
    if kind == "zug":
        return V
    if kind == "3pb":
        return V / (2 * (m + 1) ** 2)
    if kind == "4pb":
        if not (Li and L):
            raise RelError("4-Punkt-Biegung braucht innere und äussere Stützweite")
        return V * (m * Li / L + 1) / (2 * (m + 1) ** 2)
    raise RelError(f"Belastungsart {kind} unbekannt")


def size_scale(sigma1: float, m: float, Veff1: float, Veff2: float) -> float:
    return sigma1 * (Veff1 / Veff2) ** (1 / m)


# ----------------------------------------------------------------------------- E399
def f_senb(a_W: float) -> float:
    a = a_W
    return 3 * math.sqrt(a) * (1.99 - a * (1 - a) * (2.15 - 3.93 * a + 2.7 * a * a)) / (2 * (1 + 2 * a) * (1 - a) ** 1.5)


def f_ct(a_W: float) -> float:
    a = a_W
    return (2 + a) * (0.886 + 4.64 * a - 13.32 * a ** 2 + 14.72 * a ** 3 - 5.6 * a ** 4) / (1 - a) ** 1.5


def k_q(geom: str, P_kN: float, B_mm: float, W_mm: float, a_mm: float, S_mm: float | None = None,
        Rp: float | None = None, Pmax_kN: float | None = None) -> dict:
    """K_Q in MPa·√m mit den Gültigkeitsprüfungen von E399 (soweit aus den Eingaben prüfbar)."""
    B, W, a = B_mm / 1e3, W_mm / 1e3, a_mm / 1e3
    P = P_kN * 1e3
    aw = a / W
    if not 0 < aw < 1:
        raise RelError("a/W muss zwischen 0 und 1 liegen")
    if geom == "senb":
        S = (S_mm or 4 * W_mm) / 1e3
        f = f_senb(aw)
        K = P * S / (B * W ** 1.5) * f / 1e6
    elif geom == "ct":
        f = f_ct(aw)
        K = P / (B * math.sqrt(W)) * f / 1e6
    else:
        raise RelError(f"Probenform {geom} unbekannt")
    checks = [{"name": "0,45 ≤ a/W ≤ 0,55", "ok": 0.45 <= aw <= 0.55, "value": aw}]
    if Rp:
        need = 2.5 * (K / float(Rp)) ** 2 * 1e3                   # mm
        checks += [{"name": "a ≥ 2,5 (K_Q/Rp)²", "ok": a_mm >= need, "value": a_mm, "limit": need},
                   {"name": "B ≥ 2,5 (K_Q/Rp)²", "ok": B_mm >= need, "value": B_mm, "limit": need},
                   {"name": "W − a ≥ 2,5 (K_Q/Rp)²", "ok": W_mm - a_mm >= need, "value": W_mm - a_mm, "limit": need}]
    if Pmax_kN:
        checks.append({"name": "P_max/P_Q ≤ 1,10", "ok": Pmax_kN / P_kN <= 1.10, "value": Pmax_kN / P_kN})
    valid = all(c["ok"] for c in checks) and bool(Rp) and bool(Pmax_kN)
    return {"K": K, "f": f, "a_W": aw, "checks": checks, "valid_KIc": valid,
            "complete": bool(Rp) and bool(Pmax_kN)}


def critical_crack(KIc: float, sigma: float, Y: float = 1.0) -> dict:
    """a_c in mm aus K_Ic [MPa√m], σ [MPa] und Geometriefaktor Y."""
    if sigma <= 0 or KIc <= 0 or Y <= 0:
        raise RelError("K_Ic, σ und Y müssen positiv sein")
    a = (KIc / (Y * sigma)) ** 2 / math.pi
    return {"a_c_mm": a * 1e3, "KIc": KIc, "sigma": sigma, "Y": Y}


def critical_stress(KIc: float, a_mm: float, Y: float = 1.0) -> float:
    return KIc / (Y * math.sqrt(math.pi * a_mm / 1e3))
