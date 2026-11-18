"""Zweiseitige 95-%-Quantile der Student-t-Verteilung (t₀,₉₇₅; ν Freiheitsgrade), ohne scipy zur Laufzeit.

Tabelle für ν = 1–30, 40, 60, 120 und ∞ (keine scipy-Abhängigkeit zur Laufzeit); Werte auf 6 Nachkommastellen, geprüft in
tests/test_tdist.py gegen scipy.stats.t.ppf(0,975, ν). Zwischen den Tabellenwerten (ν > 30) wird linear in 1/ν
interpoliert; für ν > 120 zwischen 120 und ∞ (1/ν → 0).
"""
from __future__ import annotations

import math

T975 = {
    1: 12.706205, 2: 4.302653, 3: 3.182446, 4: 2.776445, 5: 2.570582, 6: 2.446912, 7: 2.364624, 8: 2.306004,
    9: 2.262157, 10: 2.228139, 11: 2.200985, 12: 2.178813, 13: 2.160369, 14: 2.144787, 15: 2.131450, 16: 2.119905,
    17: 2.109816, 18: 2.100922, 19: 2.093024, 20: 2.085963, 21: 2.079614, 22: 2.073873, 23: 2.068658, 24: 2.063899,
    25: 2.059539, 26: 2.055529, 27: 2.051831, 28: 2.048407, 29: 2.045230, 30: 2.042272, 40: 2.021075, 60: 2.000298,
    120: 1.979930,
}
T975_INF = 1.959964


def t95(dof: float) -> float:
    """t₀,₉₇₅ für ν Freiheitsgrade (zweiseitiges 95-%-Intervall); NaN für ν < 1."""
    if dof is None or not math.isfinite(dof):
        return T975_INF if dof == math.inf else float("nan")
    if dof < 1:
        return float("nan")
    if float(dof).is_integer() and int(dof) in T975:
        return T975[int(dof)]
    nodes = sorted(T975)
    lo = max(k for k in nodes if k <= dof)
    hi = min((k for k in nodes if k > dof), default=None)
    t_lo = T975[lo]
    if hi is None:                                     # ν > 120: zwischen 120 und ∞
        x, x0, x1, t_hi = 1.0 / dof, 1.0 / lo, 0.0, T975_INF
    else:
        x, x0, x1, t_hi = 1.0 / dof, 1.0 / lo, 1.0 / hi, T975[hi]
    return t_lo + (t_hi - t_lo) * (x - x0) / (x1 - x0)
