"""Korrosion (Tafel-Auswertung von Polarisationskurven) und Kriechen (Larson–Miller, Norton).

Korrosion:
- Tafel-Geraden: je Ast lineare Regression E gegen lg|i| im Bereich η = E − E_corr von η_min bis η_max (Vorgabe
  50–150 mV); Schnittpunkt der Geraden → E_corr, i_corr; Steigungen β_a, β_c in mV/Dekade
- Butler–Volmer (wahlweise): i = i_corr [10^(η/β_a) − 10^(−η/β_c)], Ausgleich nach Levenberg–Marquardt in ±η_fit
- Polarisationswiderstand R_p = dE/di bei η = 0 (Gerade in ±10 mV, ASTM G59); Stern–Geary: i_corr = B/R_p mit
  B = β_a β_c / (2,303 (β_a + β_c))
- Abtragsrate (ASTM G102): CR = K₁ i_corr EW / ρ, K₁ = 3,27·10⁻³ mm·g/(µA·cm·a); EW = M/n

Kriechen:
- Larson–Miller: P = T (C + lg t_r) mit T in K, t_r in h; C fest (Vorgabe 20) oder angepasst; lg σ als Polynom in P
- Norton (mit Arrhenius): ε̇ = A σ^n exp(−Q/(R T)); lg ε̇ = lg A + n lg σ − Q/(R T ln 10), multiple Regression
"""
from __future__ import annotations

import math

import numpy as np

from .fit import FitError, linreg, lm, mlinreg

R = 8.314462618
REFS = {"tafel": ["stern1957", "bard"], "rp": ["astmg59", "stern1957"], "rate": ["astmg102"],
        "lmp": ["larsonmiller1952"], "norton": ["norton1929", "dowling"]}
K1 = 3.27e-3                                    # mm·g/(µA·cm·a)
VALENCE = {"Fe": 2, "Al": 3, "Cu": 2, "Zn": 2, "Ni": 2, "Mg": 2, "Ti": 4, "Cr": 3, "Sn": 2, "Pb": 2, "Ag": 1, "Co": 2}


class CorrError(ValueError):
    pass


def equivalent_weight(el: str) -> dict:
    """EW = M/n für ein reines Metall; Dichte aus der Werkstoffdatenbank (Element)."""
    from labcalc import chem
    from labcalc import materials as Mt
    if el not in VALENCE:
        raise CorrError(f"Für {el} ist keine Wertigkeit hinterlegt")
    M = chem.element_weight(el)[0]
    try:
        rho = Mt.get(el, "rho") / 1000
    except Mt.MatError:
        rho = None
    return {"el": el, "M": M, "n": VALENCE[el], "EW": M / VALENCE[el], "rho": rho}


def _units_i(i, unit: str, area_cm2: float) -> np.ndarray:
    """Strom in µA/cm²."""
    f = {"A": 1e6, "mA": 1e3, "uA": 1.0, "µA": 1.0, "nA": 1e-3, "A/cm2": 1e6, "mA/cm2": 1e3, "uA/cm2": 1.0,
         "µA/cm2": 1.0, "A/m2": 100.0}.get(unit)
    if f is None:
        raise CorrError(f"Stromeinheit {unit} unbekannt")
    i = np.asarray(i, float) * f
    if "/" not in unit:
        if not area_cm2 or area_cm2 <= 0:
            raise CorrError("Für einen Strom (nicht Stromdichte) wird die Probenfläche gebraucht")
        i = i / area_cm2
    return i


def tafel(E_V, i, unit: str = "A", area_cm2: float = 1.0, eta_min: float = 0.05, eta_max: float = 0.15,
          E_corr: float | None = None, bv: bool = False, eta_fit: float = 0.02) -> dict:
    E = np.asarray(E_V, float)
    j = _units_i(i, unit, area_cm2)                                   # µA/cm²
    ok = np.isfinite(E) & np.isfinite(j)
    E, j = E[ok], j[ok]
    if len(E) < 10:
        raise CorrError("Zu wenige Messpunkte")
    o = np.argsort(E)
    E, j = E[o], j[o]
    if E_corr is None:
        k = int(np.argmin(np.abs(j)))
        if 0 < k < len(E) - 1 and np.sign(j[k - 1]) != np.sign(j[k + 1]):
            E_corr0 = float(np.interp(0, [j[k - 1], j[k + 1]], [E[k - 1], E[k + 1]]) if j[k + 1] > j[k - 1] else E[k])
        else:
            E_corr0 = float(E[k])
    else:
        E_corr0 = float(E_corr)
    eta = E - E_corr0
    an = (eta >= eta_min) & (eta <= eta_max) & (j > 0)
    ca = (eta <= -eta_min) & (eta >= -eta_max) & (j < 0)
    if an.sum() < 3 and ca.sum() < 3:
        # manche Geräte geben |i|: dann Vorzeichen aus η
        j = np.where(eta >= 0, np.abs(j), -np.abs(j))
        an = (eta >= eta_min) & (eta <= eta_max)
        ca = (eta <= -eta_min) & (eta >= -eta_max)
    if an.sum() < 3 or ca.sum() < 3:
        raise CorrError("Im Tafel-Bereich liegen zu wenige Punkte je Ast (mindestens 3); Bereich anpassen")
    fa = linreg(np.log10(j[an]), E[an])                                # E = a + b lg i
    fc = linreg(np.log10(-j[ca]), E[ca])
    if fa["b"] <= 0 or fc["b"] >= 0:
        raise CorrError("Tafel-Geraden haben die falsche Steigung; Bereich oder E_corr prüfen")
    lgi = (fc["a"] - fa["a"]) / (fa["b"] - fc["b"])
    icorr = 10 ** lgi
    Ecorr = fa["a"] + fa["b"] * lgi
    ba, bc = fa["b"] * 1e3, -fc["b"] * 1e3                            # mV/Dekade
    out = {"E_corr_input": E_corr0, "Ecorr": Ecorr, "icorr": icorr, "ba": ba, "bc": bc, "r2_a": fa["r2"],
           "r2_c": fc["r2"], "n_a": int(an.sum()), "n_c": int(ca.sum()),
           "fit_a": {"a": fa["a"], "b": fa["b"]}, "fit_c": {"a": fc["a"], "b": fc["b"]},
           "E": E.tolist(), "j": j.tolist()}
    near = np.abs(eta) <= 0.010
    if near.sum() >= 3:
        f = linreg(j[near] * 1e-6, E[near])                            # Ω·cm²
        Rp = f["b"]
        B = ba * bc / (2.303 * (ba + bc)) / 1e3                        # V
        out.update(Rp=Rp, B=B, icorr_sg=B / Rp * 1e6 if Rp > 0 else None)
    if bv:
        sel = np.abs(eta) <= eta_fit
        if sel.sum() >= 6:
            def model(x, p):
                ic, a_, c_, e0 = p
                return ic * (10 ** ((x - e0) / (a_ / 1e3)) - 10 ** (-(x - e0) / (c_ / 1e3)))
            try:
                r = lm(model, [icorr, ba, bc, Ecorr], E[sel], j[sel], lo=[1e-9, 5, 5, E[0]], hi=[1e9, 2000, 2000, E[-1]])
                out["bv"] = {"icorr": float(r["p"][0]), "ba": float(r["p"][1]), "bc": float(r["p"][2]),
                             "Ecorr": float(r["p"][3]), "se": [float(s) if np.isfinite(s) else None for s in r["se"]],
                             "n": int(sel.sum())}
            except (FitError, np.linalg.LinAlgError, ValueError):
                out["bv"] = {"error": "Butler–Volmer-Anpassung nicht konvergiert"}
    return out


def corrosion_rate(icorr_uA_cm2: float, EW: float, rho: float) -> dict:
    """mm/a und mpy nach ASTM G102."""
    cr = K1 * icorr_uA_cm2 * EW / rho
    return {"mm_a": cr, "mpy": cr / 0.0254, "um_a": cr * 1e3}


# ----------------------------------------------------------------------------- Kriechen
def lmp_fit(sigma, T_C, t_h, C: float | None = 20.0, deg: int = 2) -> dict:
    """lg σ = Polynom(P), P = T(C + lg t). C=None: C mit angepasst (eindimensionale Suche nach kleinster Streuung)."""
    s = np.asarray(sigma, float)
    T = np.asarray(T_C, float) + 273.15
    t = np.asarray(t_h, float)
    if len(s) < deg + 2:
        raise CorrError(f"Zu wenige Versuche ({len(s)}) für ein Polynom vom Grad {deg}")
    if np.any(t <= 0) or np.any(s <= 0):
        raise CorrError("Zeiten und Spannungen müssen positiv sein")
    ls = np.log10(s)

    def resid(Cv):
        P = T * (Cv + np.log10(t))
        c = np.polyfit(P / 1e3, ls, deg)
        return float(((np.polyval(c, P / 1e3) - ls) ** 2).sum()), c, P
    fitted = C is None
    if fitted:
        grid = np.arange(5, 40.01, 0.25)
        vals = [resid(c)[0] for c in grid]
        Cv = float(grid[int(np.argmin(vals))])
        lo, hi = Cv - 0.25, Cv + 0.25
        for _ in range(40):
            m1, m2 = lo + (hi - lo) / 3, hi - (hi - lo) / 3
            if resid(m1)[0] < resid(m2)[0]:
                hi = m2
            else:
                lo = m1
        Cv = 0.5 * (lo + hi)
    else:
        Cv = float(C)
    sse, coef, P = resid(Cv)
    sst = float(((ls - ls.mean()) ** 2).sum())
    return {"C": Cv, "C_fitted": fitted, "coef": coef.tolist(), "deg": deg, "r2": 1 - sse / sst if sst > 0 else 1.0,
            "P": P.tolist(), "lg_sigma": ls.tolist(), "n": len(s)}


def lmp_predict(fit: dict, sigma: float, T_C: float) -> dict:
    """Bruchzeit bei σ und T aus der Kurve (P aus lg σ durch Bisektion im Datenbereich)."""
    c = np.array(fit["coef"])
    P = np.array(fit["P"]) / 1e3
    lo, hi = float(P.min()), float(P.max())
    target = math.log10(sigma)
    f = lambda p: float(np.polyval(c, p)) - target  # noqa: E731
    if f(lo) * f(hi) > 0:
        return {"t_h": None, "note": "Spannung ausserhalb des Datenbereichs; nicht extrapoliert"}
    for _ in range(80):
        m = 0.5 * (lo + hi)
        if f(lo) * f(m) <= 0:
            hi = m
        else:
            lo = m
    Pv = 0.5 * (lo + hi) * 1e3
    T = T_C + 273.15
    return {"P": Pv, "t_h": 10 ** (Pv / T - fit["C"])}


def norton_fit(rate, sigma, T_C=None) -> dict:
    """ε̇ = A σ^n exp(−Q/RT): mit einer Temperatur nur A und n; mit mehreren auch Q (kJ/mol)."""
    e = np.asarray(rate, float)
    s = np.asarray(sigma, float)
    if np.any(e <= 0) or np.any(s <= 0):
        raise CorrError("Kriechraten und Spannungen müssen positiv sein")
    if T_C is None or len(set(np.round(np.asarray(T_C, float), 6))) < 2:
        f = linreg(np.log10(s), np.log10(e))
        return {"n": f["b"], "s_n": f.get("sb"), "lgA": f["a"], "Q_kJ": None, "r2": f["r2"], "N": f["n"]}
    T = np.asarray(T_C, float) + 273.15
    X = np.c_[np.ones(len(e)), np.log10(s), -1 / (R * T * math.log(10))]
    f = mlinreg(X, np.log10(e))
    b = f["beta"]
    return {"lgA": b[0], "n": b[1], "s_n": f["se"][1], "Q_kJ": b[2] / 1e3,
            "s_Q": f["se"][2] / 1e3 if f["se"][2] is not None else None, "r2": f["r2"], "N": f["n"]}
