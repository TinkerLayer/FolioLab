"""Ermüdung: Wöhlerlinie (Basquin) mit Durchläufern, Mittelspannungseinfluss und Haigh-Diagramm, Marin-Faktoren,
Rainflow-Zählung (ASTM E1049) und lineare Schadensakkumulation (Miner).

Wöhlerlinie: lg N = A + B lg σa (N abhängige Grösse, ASTM E739); Basquin σa = σf′ (2N)^b mit b = 1/B,
lg σf′ = −A/B − b lg 2. Mit Durchläufern (zensiert) Maximum-Likelihood mit normalverteiltem lg N (Nelson 1990).

Mittelspannung (σar = gleichwertige Wechselspannungsamplitude):
    Goodman σar = σa / (1 − σm/Rm), Gerber σar = σa / (1 − (σm/Rm)²), Soderberg σar = σa / (1 − σm/Re),
    Morrow σar = σa / (1 − σm/σf′), SWT σar = √(σmax σa) (σmax > 0)                       (Dowling, Kap. 9–10)
"""
from __future__ import annotations

import math

import numpy as np

from .fit import FitError, linreg, nelder_mead, predict_band

REFS = {"sn": ["basquin1910", "astme739"], "mle": ["nelson1990"], "mean": ["dowling"], "swt": ["swt1970"],
        "marin": ["shigley"], "rainflow": ["astme1049"], "miner": ["miner1945"]}
MEAN_MODELS = ("none", "goodman", "gerber", "soderberg", "morrow", "swt")

# Marin-Faktoren nach Shigley (10. Aufl.), Rm in MPa: ka = a·Rm^b
SURFACE = {"geschliffen": (1.58, -0.085), "bearbeitet": (4.51, -0.265), "warmgewalzt": (57.7, -0.718),
           "geschmiedet": (272.0, -0.995)}
SURFACE_EN = {"geschliffen": "ground", "bearbeitet": "machined or cold-drawn", "warmgewalzt": "hot-rolled",
              "geschmiedet": "as-forged"}
LOADING = {"biegung": 1.0, "zug": 0.85, "torsion": 0.59}
RELIABILITY = {50: 1.000, 90: 0.897, 95: 0.868, 99: 0.814, 99.9: 0.753, 99.99: 0.702, 99.999: 0.659}


class FatigueError(ValueError):
    pass


def _norm_cdf(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def basquin_fit(sa, N, runout=None) -> dict:
    """Ausgleich lg N = A + B lg σa. Ohne Durchläufer kleinste Quadrate (E739) mit Vertrauensband; mit Durchläufern
    zusätzlich Maximum-Likelihood (zensiert)."""
    sa = np.asarray(sa, float)
    N = np.asarray(N, float)
    ro = np.zeros(len(sa), bool) if runout is None else np.asarray(runout, bool)
    ok = np.isfinite(sa) & np.isfinite(N) & (sa > 0) & (N > 0)
    sa, N, ro = sa[ok], N[ok], ro[ok]
    fail = ~ro
    if fail.sum() < 3:
        raise FatigueError("Für eine Wöhlerlinie braucht es mindestens drei Brüche")
    x, y = np.log10(sa), np.log10(N)
    ls = linreg(x[fail], y[fail])
    out = {"n_fail": int(fail.sum()), "n_runout": int(ro.sum()), "lsq": _basq(ls["a"], ls["b"]), "lsq_fit": ls}
    if ls["b"] >= 0:
        out["warn"] = "Steigung ≥ 0: mehr Last ergibt längere Lebensdauer; Daten prüfen"
    if ro.any():
        s0 = ls["s"] or 0.2

        def nll(p):
            A, B, ls_ = p
            s = math.exp(ls_)
            mu = A + B * x
            z = (y - mu) / s
            v = -np.sum(-0.5 * z[fail] ** 2 - math.log(s)) - sum(math.log(max(1 - _norm_cdf(zz), 1e-300)) for zz in z[ro])
            return float(v)
        p, val = nelder_mead(nll, [ls["a"], ls["b"], math.log(max(s0, 1e-3))])
        out["mle"] = _basq(p[0], p[1])
        out["mle"]["s"] = math.exp(p[2])
        out["mle"]["nll"] = val
    return out


def _basq(A, B) -> dict:
    b = 1 / B if B != 0 else float("nan")
    sf = 10 ** (-A / B - b * math.log10(2)) if B != 0 else float("nan")
    return {"A": A, "B": B, "b": b, "sigma_f": sf}


def life(sar, fit: dict) -> float:
    """Lastwechsel bis Bruch N aus der Wöhlerlinie lg N = A + B lg σar."""
    return 10 ** (fit["A"] + fit["B"] * math.log10(sar)) if sar > 0 else float("inf")


def band(fit_lsq: dict, sa_grid) -> dict:
    """95-%-Vertrauensband der mittleren lg N (E739) entlang sa_grid."""
    x = np.log10(np.asarray(sa_grid, float))
    yhat, hw = predict_band(fit_lsq, x)
    return {"sa": list(map(float, sa_grid)), "N": (10 ** yhat).tolist(), "N_lo": (10 ** (yhat - hw)).tolist(),
            "N_hi": (10 ** (yhat + hw)).tolist()}


def equivalent(sa: float, sm: float, model: str, Rm: float | None = None, Re: float | None = None,
               sigma_f: float | None = None) -> float | None:
    """Gleichwertige Wechselspannungsamplitude σar; None, wenn das Modell hier nicht gilt."""
    sa, sm = float(sa), float(sm)
    if model in (None, "", "none"):
        return sa
    if model == "swt":
        smax = sm + sa
        return math.sqrt(smax * sa) if smax > 0 else None
    lim = {"goodman": Rm, "gerber": Rm, "soderberg": Re, "morrow": sigma_f}.get(model)
    if not lim:
        raise FatigueError({"goodman": "Goodman braucht Rm", "gerber": "Gerber braucht Rm",
                            "soderberg": "Soderberg braucht Re", "morrow": "Morrow braucht σf′"}.get(model, "Modell unbekannt"))
    if model == "gerber":
        d = 1 - (sm / lim) ** 2
    else:
        d = 1 - sm / lim
    if model == "gerber" and sm < 0:
        return sa                       # Gerber gilt nur für Zugmittelspannung; Druck: konservativ σar = σa
    return sa / d if d > 0 else None


def haigh(Se: float, Rm: float | None, Re: float | None = None, n: int = 101) -> dict:
    """Grenzlinien im Haigh-Diagramm (σm, σa) für Dauerfestigkeit Se."""
    out = {}
    if Rm:
        sm = np.linspace(0, Rm, n)
        out["goodman"] = {"sm": sm.tolist(), "sa": (Se * (1 - sm / Rm)).tolist()}
        out["gerber"] = {"sm": sm.tolist(), "sa": (Se * (1 - (sm / Rm) ** 2)).tolist()}
    if Re:
        sm = np.linspace(0, Re, n)
        out["soderberg"] = {"sm": sm.tolist(), "sa": (Se * (1 - sm / Re)).tolist()}
        out["yield"] = {"sm": [-Re, 0, Re], "sa": [0, Re, 0]}
    smax = Rm or Re or 3 * Se
    sm = np.linspace(-0.0, smax, n)
    sa_swt = (-sm + np.sqrt(sm ** 2 + 4 * Se ** 2)) / 2           # σa (σa + σm) = Se²
    out["swt"] = {"sm": sm.tolist(), "sa": sa_swt.tolist()}
    return out


def marin(Rm: float, surface: str = "bearbeitet", d_mm: float | None = None, loading: str = "biegung",
          rotating: bool = True, kd: float = 1.0, reliability: float = 50, Se_prime: float | None = None) -> dict:
    """Dauerfestigkeit des Bauteils Se = ka kb kc kd ke Se′ (Stahl: Se′ = 0,5 Rm bis Rm = 1400 MPa, sonst 700 MPa)."""
    Rm = float(Rm)
    notes = []
    if Se_prime is None:
        Se_prime = 0.5 * Rm if Rm <= 1400 else 700.0
        notes.append("Se′ nach der Stahl-Näherung (0,5 Rm, höchstens 700 MPa)")
    a, b = SURFACE[surface]
    ka = a * Rm ** b
    if loading == "zug":
        kb = 1.0
    elif d_mm is None:
        kb = 1.0
        notes.append("kb = 1 (kein Durchmesser angegeben)")
    else:
        d = float(d_mm)
        if 2.79 <= d <= 51:
            kb = 1.24 * d ** -0.107
        elif 51 < d <= 254:
            kb = 1.51 * d ** -0.157
        else:
            kb = 1.0
            notes.append("Durchmesser ausserhalb 2,79–254 mm: kb = 1")
        if not rotating:
            notes.append("nicht umlaufende Biegung: Ersatzdurchmesser nach Shigley Gl. 6-24 ff. selbst bestimmen")
    kc = LOADING[loading]
    rel = min(RELIABILITY, key=lambda r: abs(r - float(reliability)))
    ke = RELIABILITY[rel]
    Se = ka * kb * kc * float(kd) * ke * Se_prime
    return {"ka": ka, "kb": kb, "kc": kc, "kd": float(kd), "ke": ke, "reliability": rel, "Se_prime": Se_prime,
            "Se": Se, "notes": notes}


# ----------------------------------------------------------------------------- Rainflow (ASTM E1049, Abschn. 5.4.4)
def reversals(series, hysteresis: float = 0.0) -> list[float]:
    """Umkehrpunkte einer Lastfolge (gleiche Nachbarn und Zwischenwerte entfernt; optional Hysteresefilter)."""
    x = [float(v) for v in series if v is not None and math.isfinite(float(v))]
    if len(x) < 2:
        return x
    out = [x[0]]
    for v in x[1:]:
        if v == out[-1]:
            continue
        if len(out) >= 2 and (out[-1] - out[-2]) * (v - out[-1]) > 0:
            out[-1] = v
        else:
            out.append(v)
    if hysteresis > 0:
        filt = [out[0]]
        for v in out[1:]:
            if abs(v - filt[-1]) < hysteresis:
                continue
            if len(filt) >= 2 and (filt[-1] - filt[-2]) * (v - filt[-1]) > 0:
                filt[-1] = v
            else:
                filt.append(v)
        out = filt
    return out


def rainflow(series, hysteresis: float = 0.0) -> list[dict]:
    """Rainflow-Zählung nach ASTM E1049-85, 5.4.4: [{range, mean, count (0,5 oder 1), i0, i1}]."""
    rev = reversals(series, hysteresis)
    stack: list[tuple[float, int]] = []
    cycles = []
    for i, v in enumerate(rev):
        stack.append((v, i))
        while len(stack) >= 3:
            X = abs(stack[-1][0] - stack[-2][0])
            Y = abs(stack[-2][0] - stack[-3][0])
            if X < Y:
                break
            if len(stack) == 3:
                a, b = stack[0], stack[1]
                cycles.append({"range": Y, "mean": (a[0] + b[0]) / 2, "count": 0.5, "i0": a[1], "i1": b[1]})
                stack.pop(0)
            else:
                a, b = stack[-3], stack[-2]
                cycles.append({"range": Y, "mean": (a[0] + b[0]) / 2, "count": 1.0, "i0": a[1], "i1": b[1]})
                last = stack.pop()
                stack.pop()
                stack.pop()
                stack.append(last)
    for a, b in zip(stack[:-1], stack[1:]):
        cycles.append({"range": abs(b[0] - a[0]), "mean": (a[0] + b[0]) / 2, "count": 0.5, "i0": a[1], "i1": b[1]})
    return cycles


def miner(cycles: list[dict], fit: dict, model: str = "goodman", Rm=None, Re=None, Se: float | None = None,
          repeats: float = 1.0) -> dict:
    """Schadenssumme D = Σ n_i / N_i; Zyklen unterhalb Se (wenn angegeben) zählen nicht (Miner elementar: ohne Se)."""
    D = 0.0
    rows = []
    skipped = 0
    for c in cycles:
        sa, sm = c["range"] / 2, c["mean"]
        if sa <= 0:
            continue
        sar = equivalent(sa, sm, model, Rm, Re, fit.get("sigma_f"))
        if sar is None:
            rows.append({**c, "sar": None, "N": 0.0, "d": float("inf")})
            D = float("inf")
            continue
        if Se and sar < Se:
            skipped += 1
            rows.append({**c, "sar": sar, "N": None, "d": 0.0})
            continue
        Nf = life(sar, fit)
        d = c["count"] * repeats / Nf
        D += d
        rows.append({**c, "sar": sar, "N": Nf, "d": d})
    return {"D": D, "blocks_to_failure": (1 / D) * repeats if D > 0 and math.isfinite(D) else None,
            "rows": rows, "below_Se": skipped}
