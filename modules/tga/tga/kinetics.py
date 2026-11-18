"""Zersetzungskinetik aus mehreren Heizraten (Empfehlungen des ICTAC Kinetics Committee 2011/2014/2023).

Umsatz α einer gewählten Stufe aus der Masse: α(T) = (m(T₀) − m(T)) / (m(T₀) − m(T₁)), nur Heizabschnitt.

Isokonversionsverfahren (Eₐ in Abhängigkeit von α, mit Vertrauensbereich aus der Regression):
- Friedman (1964): ln(dα/dt)_α = ln[A f(α)] − Eₐ/(R T_α)
- Ozawa-Flynn-Wall (Ozawa 1965; Flynn & Wall 1966; ASTM E1641): ln β = konst − 1,052 Eₐ/(R T_α) (Doyle-Näherung)
- Kissinger-Akahira-Sunose (1971): ln(β/T_α²) = konst − Eₐ/(R T_α)
- Starink (2003): ln(β/T_α^1,92) = konst − 1,0008 Eₐ/(R T_α)
- Vyazovkin (2001), integral, ohne Näherung im Verfahren: Minimum von Σᵢ Σⱼ≠ᵢ I(E,Tᵢ)βⱼ / (I(E,Tⱼ)βᵢ), Temperatur-
  integral nach Senum & Yang (1977)
Dazu Kissinger (1957) aus den DTG-Spitzen, Coats-Redfern (1964) je Reaktionsmodell für einen Lauf, Master-Plot
y(α)/y(0,5) gegen f(α)/f(0,5), Kompensationseffekt und Lebensdauer nach der Arrhenius-Extrapolation (ASTM E1877).
"""
from __future__ import annotations

import math

import numpy as np

R = 8.314462618  # J/(mol K), CODATA 2022

# Reaktionsmodelle: f(α), g(α) (ICTAC 2011, Tabelle 1)
MODELS = {
    "F1": ("Reaktion 1. Ordnung", lambda a: 1 - a, lambda a: -np.log(1 - a)),
    "F2": ("Reaktion 2. Ordnung", lambda a: (1 - a) ** 2, lambda a: 1 / (1 - a) - 1),
    "F3": ("Reaktion 3. Ordnung", lambda a: (1 - a) ** 3, lambda a: ((1 - a) ** -2 - 1) / 2),
    "R2": ("Kontrahierende Fläche", lambda a: 2 * (1 - a) ** 0.5, lambda a: 1 - (1 - a) ** 0.5),
    "R3": ("Kontrahierendes Volumen", lambda a: 3 * (1 - a) ** (2 / 3), lambda a: 1 - (1 - a) ** (1 / 3)),
    "A2": ("Avrami-Erofeev n = 2", lambda a: 2 * (1 - a) * (-np.log(1 - a)) ** 0.5, lambda a: (-np.log(1 - a)) ** 0.5),
    "A3": ("Avrami-Erofeev n = 3", lambda a: 3 * (1 - a) * (-np.log(1 - a)) ** (2 / 3), lambda a: (-np.log(1 - a)) ** (1 / 3)),
    "A4": ("Avrami-Erofeev n = 4", lambda a: 4 * (1 - a) * (-np.log(1 - a)) ** 0.75, lambda a: (-np.log(1 - a)) ** 0.25),
    "D1": ("Eindimensionale Diffusion", lambda a: 1 / (2 * a), lambda a: a ** 2),
    "D2": ("Zweidimensionale Diffusion", lambda a: 1 / (-np.log(1 - a)), lambda a: (1 - a) * np.log(1 - a) + a),
    "D3": ("Dreidimensionale Diffusion (Jander)", lambda a: 3 * (1 - a) ** (2 / 3) / (2 * (1 - (1 - a) ** (1 / 3))),
           lambda a: (1 - (1 - a) ** (1 / 3)) ** 2),
    "D4": ("Ginstling-Brounshtein", lambda a: 3 / (2 * ((1 - a) ** (-1 / 3) - 1)), lambda a: 1 - 2 * a / 3 - (1 - a) ** (2 / 3)),
    "P2": ("Potenzgesetz n = 1/2", lambda a: 2 * a ** 0.5, lambda a: a ** 0.5),
    "P3": ("Potenzgesetz n = 1/3", lambda a: 3 * a ** (2 / 3), lambda a: a ** (1 / 3)),
}
ALPHAS = np.round(np.arange(0.05, 0.951, 0.05), 3)
T_CRIT = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228}


def _t95(dof: int) -> float:
    return T_CRIT.get(dof, 1.96 if dof > 30 else 2.0)


class KinError(ValueError):
    pass


def conversion(run, T_lo: float, T_hi: float) -> dict:
    """α(T), α(t), dα/dt eines Laufs zwischen T_lo und T_hi (erster Heizabschnitt)."""
    from .process import savgol
    T = np.asarray(run.T, float)
    t = run.time()
    m = run.pct()
    keep = T >= np.maximum.accumulate(np.nan_to_num(T, nan=-1e9)) - 1e-9
    T, t, m = T[keep], t[keep], m[keep]
    sel = (T >= T_lo) & (T <= T_hi)
    if sel.sum() < 20:
        raise KinError(f"{run.name}: Bereich {T_lo:g}–{T_hi:g} °C enthält kaum Messpunkte")
    T, t, m = T[sel], t[sel], m[sel]
    m0, m1 = float(np.median(m[:3])), float(np.median(m[-3:]))
    if m0 - m1 < 0.5:
        raise KinError(f"{run.name}: im Bereich kaum Massenverlust ({m0 - m1:.2f} %)")
    a = np.clip((m0 - m) / (m0 - m1), 0, 1)
    a = np.maximum.accumulate(savgol(a, max(5, (len(a) // 60) | 1), 2))   # leicht glätten, monoton
    w = max(5, (len(a) // 40) | 1)
    dadi = savgol(a, w, 2, 1)
    dti = savgol(t, w, 1, 1)
    dadt = dadi / np.where(np.abs(dti) < 1e-12, np.nan, dti)
    beta = run.meta.get("rate") or float(np.median(np.diff(T) / np.diff(t)))
    return {"T": T + 273.15, "t": t, "a": a, "dadt": dadt / 60.0, "beta": float(beta), "loss": m0 - m1,
            "name": run.name, "m0": run.m0}


def at_alpha(c: dict, alphas=ALPHAS) -> dict:
    a = c["a"]
    idx = np.searchsorted(a, alphas)
    ok = (idx > 0) & (idx < len(a))
    T = np.full(len(alphas), np.nan)
    r = np.full(len(alphas), np.nan)
    for k in np.nonzero(ok)[0]:
        j = idx[k]
        f = (alphas[k] - a[j - 1]) / ((a[j] - a[j - 1]) or 1e-12)
        T[k] = c["T"][j - 1] + f * (c["T"][j] - c["T"][j - 1])
        r[k] = c["dadt"][j - 1] + f * (c["dadt"][j] - c["dadt"][j - 1])
    return {"T": T, "dadt": r}


def _reg(x, y):
    """Lineare Regression mit Standardfehler der Steigung."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    n = len(x)
    if n < 2:
        return None
    A = np.vstack([x, np.ones(n)]).T
    (k, d), *_ = np.linalg.lstsq(A, y, rcond=None)
    res = y - (k * x + d)
    sxx = float(np.sum((x - x.mean()) ** 2)) or 1e-30
    ss_tot = float(np.sum((y - y.mean()) ** 2)) or 1e-30
    r2 = 1 - float(res @ res) / ss_tot
    se = math.sqrt(float(res @ res) / (n - 2) / sxx) if n > 2 else float("nan")
    return {"k": float(k), "d": float(d), "se": se, "r2": r2, "n": n}


def senum_yang(x):
    x = np.asarray(x, float)
    return np.exp(-x) / x * (x ** 3 + 18 * x ** 2 + 88 * x + 96) / (x ** 4 + 20 * x ** 3 + 120 * x ** 2 + 240 * x + 120)


def _I(E, T):
    """Temperaturintegral ∫₀ᵀ exp(−E/RT') dT' ≈ (E/R)·p(x), x = E/RT."""
    x = E / (R * T)
    return E / R * senum_yang(x)


def _vyazovkin(Ts: np.ndarray, betas: np.ndarray, E0: float) -> float | None:
    ok = np.isfinite(Ts)
    if ok.sum() < 3:
        return None
    Ts, b = Ts[ok], betas[ok]

    def phi(E):
        I = _I(E, Ts)
        M = np.outer(I, b) / np.outer(b, I)
        return float(np.sum(M) - len(Ts))

    lo, hi = max(5e3, 0.3 * E0), min(1.5e6, 2.5 * E0)
    g = (math.sqrt(5) - 1) / 2
    a, c = lo, hi
    x1, x2 = c - g * (c - a), a + g * (c - a)
    f1, f2 = phi(x1), phi(x2)
    for _ in range(80):
        if f1 < f2:
            c, x2, f2 = x2, x1, f1
            x1 = c - g * (c - a)
            f1 = phi(x1)
        else:
            a, x1, f1 = x1, x2, f2
            x2 = a + g * (c - a)
            f2 = phi(x2)
        if c - a < 1.0:
            break
    return (a + c) / 2


def isoconversional(convs: list[dict], alphas=ALPHAS) -> dict:
    if len(convs) < 3:
        raise KinError("Für Isokonversionsverfahren mindestens drei Läufe mit verschiedenen Heizraten laden (ICTAC 2011).")
    betas = np.array([c["beta"] for c in convs])
    if len(set(np.round(betas, 2))) < len(betas):
        raise KinError("Zwei Läufe haben dieselbe Heizrate; für die Kinetik verschiedene Heizraten verwenden.")
    pts = [at_alpha(c, alphas) for c in convs]
    TT = np.array([p["T"] for p in pts])          # Läufe × α
    RR = np.array([p["dadt"] for p in pts])
    out = {m: [] for m in ("friedman", "ofw", "kas", "starink", "vyazovkin")}
    dof = len(convs) - 2
    t95 = _t95(dof)
    for k, al in enumerate(alphas):
        T = TT[:, k]
        x = 1 / T
        rows = {}
        f = _reg(x, np.log(RR[:, k]))
        if f:
            rows["friedman"] = (-f["k"] * R, f["se"] * R, f["r2"], f["d"])
        o = _reg(x, np.log(betas))
        if o:
            rows["ofw"] = (-o["k"] * R / 1.052, o["se"] * R / 1.052, o["r2"], o["d"])
        ka = _reg(x, np.log(betas / T ** 2))
        if ka:
            rows["kas"] = (-ka["k"] * R, ka["se"] * R, ka["r2"], ka["d"])
        st = _reg(x, np.log(betas / T ** 1.92))
        if st:
            rows["starink"] = (-st["k"] * R / 1.0008, st["se"] * R / 1.0008, st["r2"], st["d"])
        for mname, v in rows.items():
            out[mname].append({"alpha": float(al), "E": v[0] / 1000, "ci": t95 * v[1] / 1000 if math.isfinite(v[1]) else None,
                               "r2": v[2], "intercept": v[3], "T": [float(x_) for x_ in T]})
        E0 = rows.get("kas", (150e3,))[0]
        Ev = _vyazovkin(T, betas, max(10e3, E0))
        if Ev:
            out["vyazovkin"].append({"alpha": float(al), "E": Ev / 1000, "ci": None, "r2": None, "T": [float(x_) for x_ in T]})
    summary = {}
    for mname, rows in out.items():
        Es = np.array([r["E"] for r in rows if 0.1 <= r["alpha"] <= 0.9 and math.isfinite(r["E"])])
        if len(Es):
            summary[mname] = {"mean": float(Es.mean()), "sd": float(Es.std(ddof=1)) if len(Es) > 1 else 0.0,
                              "min": float(Es.min()), "max": float(Es.max())}
    return {"alphas": [float(a) for a in alphas], "methods": out, "summary": summary, "betas": betas.tolist(),
            "warnings": checks(convs, summary)}


def checks(convs: list[dict], summary: dict) -> list[str]:
    w = []
    b = sorted(c["beta"] for c in convs)
    if len(b) < 3:
        w.append("Weniger als drei Heizraten (ICTAC 2011 empfiehlt drei bis fünf).")
    if b and b[-1] / max(b[0], 1e-9) < 3:
        w.append(f"Heizraten liegen eng beieinander ({b[0]:g}–{b[-1]:g} K/min); ein breiterer Bereich macht Eₐ belastbarer (ICTAC 2014).")
    ms = [c.get("m0") for c in convs if c.get("m0")]
    if len(ms) >= 2 and max(ms) / min(ms) > 2:
        w.append("Probenmassen unterscheiden sich um mehr als den Faktor 2; ICTAC 2014 empfiehlt gleiche, kleine Massen.")
    losses = [c["loss"] for c in convs]
    if max(losses) - min(losses) > 0.1 * max(losses):
        w.append("Der Massenverlust der Stufe unterscheidet sich zwischen den Läufen um mehr als 10 %; Stufengrenzen prüfen.")
    s = summary.get("friedman") or summary.get("kas")
    if s and s["mean"] > 0 and (s["max"] - s["min"]) > 0.2 * s["mean"]:
        w.append("Eₐ ändert sich mit dem Umsatz um mehr als 20 % des Mittels: wahrscheinlich mehrstufiger Vorgang; ein einzelnes Eₐ "
                 "(Kissinger, Coats-Redfern) ist dann nicht aussagekräftig (ICTAC 2011, 2020).")
    return w


def kissinger(convs: list[dict]) -> dict:
    """Kissinger aus der Temperatur der grössten Umsatzrate; A für eine Reaktion 1. Ordnung."""
    if len(convs) < 3:
        raise KinError("Kissinger braucht mindestens drei Heizraten.")
    b = np.array([c["beta"] for c in convs])
    Tp = np.array([c["T"][int(np.nanargmax(c["dadt"]))] for c in convs])
    r = _reg(1 / Tp, np.log(b / Tp ** 2))
    E = -r["k"] * R
    A = E / R * math.exp(r["d"])            # ln(β/Tp²) = ln(A R/E) − E/(R Tp), β in K/min -> A in 1/min
    return {"E": E / 1000, "ci": _t95(len(b) - 2) * r["se"] * R / 1000 if math.isfinite(r["se"]) else None,
            "A": A / 60.0, "lnA": math.log(A / 60.0), "r2": r["r2"], "Tp": (Tp - 273.15).tolist(), "betas": b.tolist()}


def coats_redfern(c: dict, a_lo: float = 0.1, a_hi: float = 0.9) -> list[dict]:
    a = c["a"]
    sel = (a >= a_lo) & (a <= a_hi)
    T = c["T"][sel]
    al = a[sel]
    out = []
    for key, (label, _f, g) in MODELS.items():
        with np.errstate(all="ignore"):
            y = np.log(g(al) / T ** 2)
        r = _reg(1 / T, y)
        if not r or not math.isfinite(r["k"]):
            continue
        E = -r["k"] * R
        if E <= 0:
            continue
        A = c["beta"] * E / R * math.exp(r["d"])          # 1/min
        out.append({"model": key, "label": label, "E": E / 1000, "lnA": math.log(A / 60.0), "r2": r["r2"]})
    out.sort(key=lambda x: -x["r2"])
    return out


def master_plot(convs: list[dict], E_kJ: float, alphas=np.round(np.arange(0.1, 0.91, 0.05), 3)) -> dict:
    """y(α) = (dα/dt)·exp(E/RT), normiert bei α = 0,5, gegen f(α)/f(0,5) der Modelle (ICTAC 2011)."""
    E = E_kJ * 1000
    exp_curves = []
    for c in convs:
        p = at_alpha(c, alphas)
        y = p["dadt"] * np.exp(E / (R * p["T"]))
        i5 = int(np.argmin(np.abs(alphas - 0.5)))
        exp_curves.append((y / y[i5]).tolist())
    mean = np.nanmean(np.array(exp_curves, float), axis=0)
    ranks = []
    theo = {}
    for key, (label, f, _g) in MODELS.items():
        with np.errstate(all="ignore"):
            th = f(alphas) / f(np.array([0.5]))[0]
        theo[key] = th.tolist()
        rms = float(np.sqrt(np.nanmean((th - mean) ** 2)))
        ranks.append({"model": key, "label": label, "rms": rms})
    ranks.sort(key=lambda r: r["rms"])
    return {"alphas": alphas.tolist(), "experimental": exp_curves, "mean": mean.tolist(), "models": theo, "ranking": ranks}


def preexp(iso: dict, convs: list[dict], model: str = "F1", method: str = "friedman") -> list[dict]:
    """A(α) aus dem Achsenabschnitt der Friedman-Geraden: ln[A f(α)] = Achsenabschnitt."""
    f = MODELS[model][1]
    out = []
    for r in iso["methods"].get(method, []):
        if r.get("intercept") is None:
            continue
        with np.errstate(all="ignore"):
            fa = float(f(np.array([r["alpha"]]))[0])
        if fa > 0 and math.isfinite(fa):
            out.append({"alpha": r["alpha"], "lnA": r["intercept"] - math.log(fa)})
    return out


def compensation(cr: list[dict]) -> dict | None:
    """Kompensationseffekt ln A = a·E + b über die Coats-Redfern-Modelle (ICTAC 2011)."""
    pts = [(r["E"], r["lnA"]) for r in cr if math.isfinite(r["lnA"])]
    if len(pts) < 3:
        return None
    r = _reg([p[0] for p in pts], [p[1] for p in pts])
    return {"a": r["k"], "b": r["d"], "r2": r["r2"]}


def lifetime(E_kJ: float, lnA: float, alpha_f: float = 0.05, model: str = "F1", T_use=None, t_target_h: float | None = None) -> dict:
    """Arrhenius-Extrapolation (ASTM E1877): t_f = g(α_f)/k(T); Temperaturindex für eine Ziel-Lebensdauer."""
    g = MODELS[model][2]
    ga = float(g(np.array([alpha_f]))[0])
    E = E_kJ * 1000
    A = math.exp(lnA)                    # 1/s
    rows = []
    for Tc in T_use or [50, 100, 150, 200]:
        k = A * math.exp(-E / (R * (Tc + 273.15)))
        rows.append({"T": float(Tc), "t_h": ga / k / 3600.0})
    out = {"alpha_f": alpha_f, "model": model, "rows": rows}
    if t_target_h:
        k = ga / (t_target_h * 3600.0)
        out["T_index"] = E / (R * (math.log(A) - math.log(k))) - 273.15
        out["t_target_h"] = t_target_h
    return out


def run_all(runs, T_lo: float, T_hi: float, opts: dict | None = None) -> dict:
    o = opts or {}
    convs = [conversion(r, T_lo, T_hi) for r in runs]
    convs.sort(key=lambda c: c["beta"])
    res = {"range": [T_lo, T_hi], "runs": [{"name": c["name"], "beta": c["beta"], "loss": c["loss"]} for c in convs],
           "curves": [{"name": c["name"], "beta": c["beta"], "T": (c["T"] - 273.15)[::max(1, len(c["T"]) // 400)].tolist(),
                       "a": c["a"][::max(1, len(c["a"]) // 400)].tolist()} for c in convs]}
    iso = isoconversional(convs)
    res["iso"] = iso
    try:
        res["kissinger"] = kissinger(convs)
    except (KinError, ValueError, ZeroDivisionError) as e:
        res["kissinger"] = {"error": str(e)}
    mid = convs[len(convs) // 2]
    res["coats_redfern"] = {"run": mid["name"], "beta": mid["beta"], "models": coats_redfern(mid)}
    res["compensation"] = compensation(res["coats_redfern"]["models"])
    Eref = iso["summary"].get("friedman", iso["summary"].get("kas", {})).get("mean")
    if Eref:
        res["master"] = master_plot(convs, Eref)
        best = res["master"]["ranking"][0]["model"]
        res["model"] = o.get("model") or best
        A = preexp(iso, convs, res["model"])
        res["lnA"] = A
        lnA_mid = float(np.median([x["lnA"] for x in A])) if A else None
        if lnA_mid is not None:
            res["lifetime"] = lifetime(Eref, lnA_mid, float(o.get("alpha_f", 0.05)), res["model"],
                                       o.get("T_use"), o.get("t_target_h"))
            res["lifetime"]["E"] = Eref
            res["lifetime"]["lnA"] = lnA_mid
    return res
