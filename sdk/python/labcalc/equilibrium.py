"""Reaktionsquotient und Gleichgewichtszusammensetzung einer Reaktion (ER-702).

Ideale Gase (Aktivität = x·p/p°, p° = 1 bar) und ideale Lösung (Aktivität = c/c°, c° = 1 mol/L); reine feste und
flüssige Stoffe Aktivität 1. Eine Reaktion, Umsatzvariable ξ: n_i = n_i,0 + ν_i ξ. Gelöst wird
Σ ν_i ln a_i(ξ) = ln K (monoton in ξ) mit Bisektion auf dem zulässigen ξ-Intervall; Iterationen, Restfehler und
Intervall stehen im Ergebnis. Keine Fugazitäts- oder Aktivitätskoeffizienten (Hinweis im Ergebnis).
"""
from __future__ import annotations

import math

P0_BAR = 1.0
C0 = 1.0          # mol/L


class EquilibriumError(ValueError):
    pass


def _act_ln(kind: str, n: float, n_gas: float, p_bar: float, V_L: float | None) -> float:
    if kind == "g":
        return math.log(n / n_gas * p_bar / P0_BAR)
    if kind == "aq":
        return math.log(n / V_L / C0)
    return 0.0


def quotient(species: list[dict], p_bar: float = 1.0, V_L: float | None = None) -> dict:
    """Q aus aktuellen Stoffmengen. species: [{name, nu, phase ('g','aq','cr','l'), n}]."""
    gas = sum(s["n"] for s in species if s["phase"] == "g")
    lnQ, missing = 0.0, []
    for s in species:
        if s["phase"] in ("cr", "l", "s"):
            continue
        if s["n"] <= 0:
            missing.append(s["name"])
            continue
        lnQ += s["nu"] * _act_ln(s["phase"], s["n"], gas, p_bar, V_L)
    if missing:
        prod = [m for m in missing if next(x for x in species if x["name"] == m)["nu"] > 0]
        return {"lnQ": -math.inf if prod else math.inf, "zero": missing}
    return {"lnQ": lnQ, "lgQ": lnQ / math.log(10)}


def direction(lnQ: float, lnK: float) -> str:
    if abs(lnQ - lnK) < 1e-9:
        return "Gleichgewicht"
    return "Hinreaktion (Q < K)" if lnQ < lnK else "Rückreaktion (Q > K)"


def solve(species: list[dict], lnK: float, p_bar: float = 1.0, V_L: float | None = None, tol: float = 1e-12,
          max_iter: int = 200) -> dict:
    """Gleichgewicht ab den Anfangsstoffmengen. Rückgabe: ξ, Stoffmengen, Anteile, Diagnose."""
    if any(s["phase"] == "aq" for s in species) and not V_L:
        raise EquilibriumError("Gelöste Stoffe: Volumen der Lösung angeben")
    if any(s["phase"] == "g" for s in species) and not p_bar > 0:
        raise EquilibriumError("Gesamtdruck > 0 angeben")
    # zulässiges Intervall: alle n_i ≥ 0
    lo, hi = -math.inf, math.inf
    for s in species:
        if s["nu"] > 0:
            lo = max(lo, -s["n0"] / s["nu"])
        elif s["nu"] < 0:
            hi = min(hi, s["n0"] / -s["nu"])
    if not (math.isfinite(lo) and math.isfinite(hi)) or hi <= lo:
        raise EquilibriumError("Kein zulässiger Umsatz: Anfangsstoffmengen prüfen (jede Seite braucht einen Stoff)")
    # kondensierte Stoffe, die aufgebraucht werden könnten, begrenzen nur das Intervall

    def g(xi):
        n = [s["n0"] + s["nu"] * xi for s in species]
        gas = sum(v for v, s in zip(n, species) if s["phase"] == "g")
        val = 0.0
        for v, s in zip(n, species):
            if s["phase"] in ("cr", "l", "s"):
                continue
            if v <= 0:
                return -math.inf if s["nu"] > 0 else math.inf
            val += s["nu"] * _act_ln(s["phase"], v, gas, p_bar, V_L)
        return val - lnK
    span = hi - lo
    a, b = lo + span * 1e-15, hi - span * 1e-15
    ga, gb = g(a), g(b)
    diag = {"interval": [lo, hi], "iterations": 0, "method": "Bisektion in ξ"}
    if ga > 0 and gb > 0:
        xi, diag["limit"] = a, "Rückreaktion vollständig (K sehr klein gegenüber Q am Rand)"
    elif ga < 0 and gb < 0:
        xi, diag["limit"] = b, "Hinreaktion vollständig bis zum begrenzenden Stoff"
    else:
        it = 0
        while it < max_iter and (b - a) > tol * max(1.0, abs(a) + abs(b)):
            m = (a + b) / 2
            gm = g(m)
            if gm == 0:
                a = b = m
                break
            if (gm > 0) == (ga > 0):
                a, ga = m, gm
            else:
                b = m
            it += 1
        xi = (a + b) / 2
        diag["iterations"] = it
        diag["converged"] = it < max_iter
        if not diag["converged"]:
            raise EquilibriumError(f"Gleichgewicht nicht gefunden nach {max_iter} Iterationen (Intervall {a:g}…{b:g})")
    res = g(xi)
    diag["residual_lnK"] = res if math.isfinite(res) else None
    n = [s["n0"] + s["nu"] * xi for s in species]
    gas = sum(v for v, s in zip(n, species) if s["phase"] == "g")
    rows = []
    for v, s in zip(n, species):
        r = {"name": s["name"], "phase": s["phase"], "n0": s["n0"], "n": v}
        if s["phase"] == "g" and gas > 0:
            r["x"] = v / gas
            r["p_bar"] = v / gas * p_bar
        if s["phase"] == "aq":
            r["c"] = v / V_L
        rows.append(r)
    # Umsatz bezogen auf den begrenzenden Edukt
    conv = None
    lim = [(s["n0"] / -s["nu"]) for s in species if s["nu"] < 0 and s["n0"] > 0]
    if lim and xi > 0:
        conv = xi / min(lim)
    return {"xi": xi, "rows": rows, "conversion": conv, "diagnostics": diag, "p_bar": p_bar, "V_L": V_L,
            "notes": ["Ideales Verhalten angenommen (keine Fugazitäts- oder Aktivitätskoeffizienten); bei hohem "
                      "Druck oder konzentrierten Lösungen weicht die reale Lage ab."]}
