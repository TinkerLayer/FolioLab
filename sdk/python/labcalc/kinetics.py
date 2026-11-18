"""Kinetik aus eigenen Daten (ER-703) und Simulation einfacher Geschwindigkeitsgesetze (ER-704).

Konvention: k ist über −d[A]/dt = k·[A]^n definiert (nicht über die Reaktionsgeschwindigkeit je Formelumsatz);
das steht in jedem Ergebnis.

- arrhenius(T, k): ln k = ln A − Eₐ/(R T), lineare Regression in 1/T (Arrhenius 1889).
- eyring(T, k):    ln(k/T) = ln(k_B/h) + ΔS‡/R − ΔH‡/(R T) (Eyring 1935), Transmissionskoeffizient 1.
- order_fit(t, c): Ordnung 0, 1, 2 über die linearisierten Formen; Auswahl nach der Restabweichung in c.
- simulate(model, …): analytische Lösungen; eine RK4-Integration läuft zur Kontrolle mit.
Unsicherheiten: Standardfehler der Regression (1 σ), Kovarianz von Steigung und Achsenabschnitt angegeben.
"""
from __future__ import annotations

import math

R = 8.314462618          # J/(mol K), CODATA 2022 (exakt aus N_A·k_B)
KB = 1.380649e-23        # J/K, exakt (SI 2019)
H = 6.62607015e-34       # J s, exakt (SI 2019)
REFS_FIT = ["arrhenius1889", "atkins"]
REFS_EYRING = ["eyring1935", "atkins", "codata2022"]
CONV = "k über −d[A]/dt = k·[A]^n definiert"


class KineticsError(ValueError):
    pass


def _nums(xs, name, positive=True):
    out = []
    for x in xs:
        try:
            v = float(str(x).replace(",", "."))
        except (TypeError, ValueError):
            raise KineticsError(f"{name}: keine Zahl ({x!r})") from None
        if not math.isfinite(v) or (positive and v <= 0):
            raise KineticsError(f"{name} muss positiv sein ({x})")
        out.append(v)
    return out


def linfit(x: list[float], y: list[float]) -> dict:
    """Gewöhnliche kleinste Quadrate y = a + b·x mit Standardfehlern."""
    n = len(x)
    if n < 3:
        raise KineticsError("Mindestens drei Messpunkte nötig")
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((xi - mx) ** 2 for xi in x)
    if sxx == 0:
        raise KineticsError("Alle x-Werte gleich: keine Steigung bestimmbar")
    b = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y)) / sxx
    a = my - b * mx
    res = [yi - (a + b * xi) for xi, yi in zip(x, y)]
    ssr = sum(r * r for r in res)
    syy = sum((yi - my) ** 2 for yi in y)
    dof = n - 2
    s2 = ssr / dof if dof > 0 else 0.0
    se_b = math.sqrt(s2 / sxx)
    se_a = math.sqrt(s2 * (1 / n + mx * mx / sxx))
    return {"slope": b, "intercept": a, "se_slope": se_b, "se_intercept": se_a, "cov": -mx * s2 / sxx,
            "r2": 1 - ssr / syy if syy > 0 else 1.0, "residuals": res, "s": math.sqrt(s2), "n": n, "dof": dof}


def arrhenius(T, k) -> dict:
    T, k = _nums(T, "T"), _nums(k, "k")
    if len(T) != len(k):
        raise KineticsError("Gleich viele T- und k-Werte angeben")
    f = linfit([1 / t for t in T], [math.log(v) for v in k])
    Ea = -f["slope"] * R / 1000
    lnA = f["intercept"]
    return {"model": "arrhenius", "Ea_kJ": Ea, "u_Ea_kJ": f["se_slope"] * R / 1000, "lnA": lnA,
            "u_lnA": f["se_intercept"], "A": math.exp(lnA), "u_A": math.exp(lnA) * f["se_intercept"],
            "cov_lnA_Ea": -f["cov"] * R / 1000, "r2": f["r2"], "s": f["s"], "n": f["n"],
            "T_range": [min(T), max(T)], "points": [{"T": t, "k": v, "x": 1 / t, "y": math.log(v), "res": r}
                                                   for t, v, r in zip(T, k, f["residuals"])],
            "notes": ["Unsicherheiten: Standardfehler der linearen Regression von ln k gegen 1/T (1 σ); u(A) "
                      "linearisiert, die Verteilung von A ist asymmetrisch.",
                      "Gültig im gemessenen Bereich " + f"{min(T):g}–{max(T):g} K; Extrapolation unsicher."],
            "refs": REFS_FIT}


def eyring(T, k) -> dict:
    T, k = _nums(T, "T"), _nums(k, "k")
    if len(T) != len(k):
        raise KineticsError("Gleich viele T- und k-Werte angeben")
    f = linfit([1 / t for t in T], [math.log(v / t) for t, v in zip(T, k)])
    dH = -f["slope"] * R / 1000
    dS = (f["intercept"] - math.log(KB / H)) * R
    return {"model": "eyring", "dH_kJ": dH, "u_dH_kJ": f["se_slope"] * R / 1000, "dS_J": dS,
            "u_dS_J": f["se_intercept"] * R, "r2": f["r2"], "s": f["s"], "n": f["n"], "T_range": [min(T), max(T)],
            "points": [{"T": t, "k": v, "x": 1 / t, "y": math.log(v / t), "res": r}
                       for t, v, r in zip(T, k, f["residuals"])],
            "notes": ["Transmissionskoeffizient κ = 1; k in s⁻¹ (erste Ordnung) bzw. mit Standardkonzentration "
                      "1 mol/L für höhere Ordnung.", "Unsicherheiten: Standardfehler der Regression (1 σ)."],
            "refs": REFS_EYRING}


_FORMS = {0: ("c", lambda c: c), 1: ("ln c", math.log), 2: ("1/c", lambda c: 1 / c)}


def _c_pred(order, k, c0, t):
    if order == 0:
        return max(c0 - k * t, 0.0)
    if order == 1:
        return c0 * math.exp(-k * t)
    return c0 / (1 + k * c0 * t)


def half_life(order: int, k: float, c0: float | None = None) -> float | None:
    if k <= 0:
        return None
    if order == 1:
        return math.log(2) / k
    if not c0 or c0 <= 0:
        return None
    return c0 / (2 * k) if order == 0 else 1 / (k * c0)


def order_fit(t, c, kind: str = "c", c0: float | None = None) -> dict:
    """Reaktionsordnung aus Konzentration–Zeit (kind 'c') oder Umsatz–Zeit (kind 'X', Umsatz 0…1 mit c0)."""
    t = _nums(t, "t", positive=False)
    if kind == "X":
        if not c0 or c0 <= 0:
            raise KineticsError("Für Umsatzdaten die Anfangskonzentration c0 angeben")
        X = _nums(c, "Umsatz", positive=False)
        if any(not 0 <= x < 1 for x in X):
            raise KineticsError("Umsatz zwischen 0 und < 1 angeben")
        c = [c0 * (1 - x) for x in X]
    else:
        c = _nums(c, "c")
    if len(t) != len(c):
        raise KineticsError("Gleich viele t- und c-Werte angeben")
    fits = []
    for order, (lab, fn) in _FORMS.items():
        f = linfit(t, [fn(v) for v in c])
        k = -f["slope"] if order < 2 else f["slope"]
        c0f = f["intercept"] if order == 0 else math.exp(f["intercept"]) if order == 1 else 1 / f["intercept"] \
            if f["intercept"] > 0 else None
        if k <= 0 or not c0f:
            fits.append({"order": order, "form": lab, "r2": f["r2"], "valid": False})
            continue
        u_k = f["se_slope"]
        res_c = [ci - _c_pred(order, k, c0f, ti) for ti, ci in zip(t, c)]
        rms = math.sqrt(sum(r * r for r in res_c) / len(res_c))
        fits.append({"order": order, "form": lab, "k": k, "u_k": u_k, "c0": c0f, "r2": f["r2"], "rms_c": rms,
                     "residuals_c": res_c, "t_half": half_life(order, k, c0f), "valid": True})
    ok = [f for f in fits if f["valid"]]
    if not ok:
        raise KineticsError("Keine Ordnung 0–2 passt (Konzentration steigt?)")
    best = min(ok, key=lambda f: f["rms_c"])
    notes = [CONV + ".", "Auswahl nach der kleinsten Restabweichung in c (nicht nach R² der linearisierten Formen, "
             "die nicht vergleichbar sind)."]
    second = sorted(ok, key=lambda f: f["rms_c"])[1:2]
    if second and second[0]["rms_c"] < 1.5 * best["rms_c"]:
        notes.append(f"Ordnung {second[0]['order']} passt fast ebenso gut: Umsatzbereich für eine sichere Unterscheidung "
                     "zu klein.")
    return {"model": "order", "kind": kind, "t": t, "c": c, "fits": fits, "best": best["order"],
            "t_range": [min(t), max(t)], "notes": notes, "refs": ["atkins"]}


def k_at(T: float, Ea_kJ: float, A: float | None = None, k_ref: float | None = None,
         T_ref: float | None = None) -> float:
    """k(T) aus Eₐ mit A oder aus einem Bezugswert k(T_ref)."""
    if T <= 0:
        raise KineticsError("T > 0 K angeben")
    if A is not None:
        return A * math.exp(-Ea_kJ * 1000 / (R * T))
    if k_ref is None or not T_ref:
        raise KineticsError("A oder k(T_ref) mit T_ref angeben")
    return k_ref * math.exp(-Ea_kJ * 1000 / R * (1 / T - 1 / T_ref))


# ----------------------------------------------------------------------------- ER-704 Simulation
MODELS = {
    "0": ("A → P, nullte Ordnung", ["k", "a0"]),
    "1": ("A → P, erste Ordnung", ["k", "a0"]),
    "2": ("A → P, zweite Ordnung (−d[A]/dt = k[A]²)", ["k", "a0"]),
    "2AB": ("A + B → P, zweite Ordnung (−d[A]/dt = k[A][B])", ["k", "a0", "b0"]),
    "consec": ("A → B → C, Folgereaktion erster Ordnung", ["k1", "k2", "a0"]),
    "rev": ("A ⇌ B, erste Ordnung hin und zurück", ["kf", "kr", "a0", "b0"]),
}


def _analytic(model, p, t):
    k = p.get("k")
    a0 = p["a0"]
    if model in ("0", "1", "2"):
        return {"A": _c_pred(int(model), k, a0, t)}
    if model == "2AB":
        b0 = p["b0"]
        d = b0 - a0
        if abs(d) < 1e-12 * max(a0, b0):
            a = a0 / (1 + k * a0 * t)
        else:
            e = d * k * t
            a = d * a0 / (b0 * math.exp(e) - a0) if e < 700 else (0.0 if d > 0 else -d)
        return {"A": a, "B": a + d, "P": a0 - a}
    if model == "consec":
        k1, k2 = p["k1"], p["k2"]
        A = a0 * math.exp(-k1 * t)
        if abs(k1 - k2) < 1e-12 * max(k1, k2):
            B = a0 * k1 * t * math.exp(-k1 * t)
        else:
            B = a0 * k1 / (k2 - k1) * (math.exp(-k1 * t) - math.exp(-k2 * t))
        return {"A": A, "B": B, "C": a0 - A - B}
    if model == "rev":
        kf, kr, b0 = p["kf"], p["kr"], p.get("b0", 0.0)
        tot = a0 + b0
        aeq = kr * tot / (kf + kr)
        a = aeq + (a0 - aeq) * math.exp(-(kf + kr) * t)
        return {"A": a, "B": tot - a}
    raise KineticsError("Unbekanntes Modell")


def _rhs(model, p, y):
    if model == "0":
        return {"A": -p["k"] if y["A"] > 0 else 0.0}
    if model == "1":
        return {"A": -p["k"] * y["A"]}
    if model == "2":
        return {"A": -p["k"] * y["A"] ** 2}
    if model == "2AB":
        r = p["k"] * y["A"] * y["B"]
        return {"A": -r, "B": -r, "P": r}
    if model == "consec":
        r1, r2 = p["k1"] * y["A"], p["k2"] * y["B"]
        return {"A": -r1, "B": r1 - r2, "C": r2}
    r = p["kf"] * y["A"] - p["kr"] * y["B"]
    return {"A": -r, "B": r}


def rk4(model, p, y0: dict, t_end: float, n: int) -> list[dict]:
    """Klassisches Runge-Kutta-Verfahren 4. Ordnung mit n Schritten (Kontrolle der analytischen Lösung)."""
    h = t_end / n
    y = dict(y0)
    out = [dict(y)]
    for _ in range(n):
        k1 = _rhs(model, p, y)
        k2 = _rhs(model, p, {s: y[s] + h / 2 * k1[s] for s in y})
        k3 = _rhs(model, p, {s: y[s] + h / 2 * k2[s] for s in y})
        k4 = _rhs(model, p, {s: y[s] + h * k3[s] for s in y})
        y = {s: y[s] + h / 6 * (k1[s] + 2 * k2[s] + 2 * k3[s] + k4[s]) for s in y}
        out.append(dict(y))
    return out


def simulate(model: str, params: dict, t_end: float | None = None, n: int = 200) -> dict:
    if model not in MODELS:
        raise KineticsError("Modell wählen: " + ", ".join(MODELS))
    need = MODELS[model][1]
    p = {}
    for key in need:
        v = params.get(key)
        if v in (None, ""):
            if key == "b0" and model == "rev":
                v = 0
            else:
                raise KineticsError(f"Parameter {key} fehlt")
        p[key] = float(str(v).replace(",", "."))
        if p[key] < 0 or (key.startswith("k") and p[key] == 0 and key != "kr"):
            raise KineticsError(f"{key} muss positiv sein")
    if t_end in (None, "") or float(t_end) <= 0:
        rate = p.get("k") or p.get("k1") or (p.get("kf", 0) + p.get("kr", 0))
        if model == "consec":
            rate = min(p["k1"], p["k2"])
        if model in ("2", "2AB"):
            rate *= p["a0"]
        t_end = (5 / rate) if model != "0" else p["a0"] / p["k"] * 1.2
    t_end = float(t_end)
    ts = [t_end * i / n for i in range(n + 1)]
    rows = [{"t": t, **_analytic(model, p, t)} for t in ts]
    y0 = {s: v for s, v in rows[0].items() if s != "t"}
    num = rk4(model, p, y0, t_end, n * 5)[::5]
    dev = max(abs(num[i][s] - rows[i][s]) for i in range(len(rows)) for s in y0)
    scale = max(max(abs(r[s]) for r in rows) for s in y0) or 1.0
    out = {"model": model, "label": MODELS[model][0], "params": p, "t_end": t_end, "rows": rows,
           "check": {"method": "RK4", "steps": n * 5, "max_dev": dev, "rel_dev": dev / scale},
           "notes": [CONV + "."], "refs": ["atkins"]}
    if model in ("0", "1", "2"):
        out["t_half"] = half_life(int(model), p["k"], p["a0"])
    if model == "consec":
        k1, k2 = p["k1"], p["k2"]
        out["t_Bmax"] = math.log(k2 / k1) / (k2 - k1) if abs(k1 - k2) > 1e-12 * max(k1, k2) else 1 / k1
    if model == "rev":
        out["K"] = p["kf"] / p["kr"] if p["kr"] > 0 else math.inf
    return out
