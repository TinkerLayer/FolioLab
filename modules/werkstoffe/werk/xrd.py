"""Auswertung von Pulverdiffraktogrammen.

Schritte (jeder abschaltbar, Reihenfolge fest): Glätten (Savitzky–Golay) → Untergrund (SNIP) → Kα2-Abzug (Rachinger)
→ Reflexe (lokale Maxima, dann Profilanpassung pseudo-Voigt) → Indizierung / Gitterparameter (kubisch automatisch
oder über eine Vergleichsphase) → Kristallitgrösse (Scherrer, Williamson–Hall) → Phasenvergleich mit berechneten
Diagrammen → halbquantitative Anteile aus berechneten Intensitäten.
"""
from __future__ import annotations

import math

import numpy as np

from . import cryst as C
from .fit import FitError, linreg, lm, mlinreg

REFS = {"smooth": ["savitzky1964"], "background": ["ryan1988", "morhac1997"], "kalpha2": ["rachinger1948"],
        "peaks": ["thompson1987"], "nelson": ["nelson1945"], "scherrer": ["scherrer1918", "langford1978"],
        "wh": ["williamson1953"], "match": ["cullity"], "quant": ["chung1974", "hubbard1988"]}
DEFAULTS = {"smooth": 0, "bg": True, "bg_width": 2.0, "strip_ka2": False, "min_rel": 2.0, "min_sep": 0.15,
            "fit": True, "doublet": True, "K": 0.9, "inst_fwhm": 0.0, "breadth": "fwhm", "correction": "quadratic",
            "tol": 0.2, "shift": True}


class XrdCalcError(ValueError):
    pass


# ----------------------------------------------------------------------------- Vorverarbeitung
def savgol(y: np.ndarray, window: int, order: int = 2) -> np.ndarray:
    """Savitzky–Golay-Glättung (Fenster ungerade, Ränder mit kürzeren Fenstern)."""
    n = len(y)
    window = int(window) | 1
    if window < order + 2 or n < window:
        return y.copy()
    h = window // 2
    k = np.arange(-h, h + 1)
    A = np.vander(k, order + 1, increasing=True)
    coef = np.linalg.pinv(A)[0]
    out = np.convolve(y, coef[::-1], mode="same")
    for i in list(range(h)) + list(range(n - h, n)):
        lo, hi = max(0, i - h), min(n, i + h + 1)
        kk = np.arange(lo, hi) - i
        Ai = np.vander(kk, min(order + 1, len(kk)), increasing=True)
        out[i] = (np.linalg.pinv(Ai)[0] @ y[lo:hi])
    return out


def snip(y: np.ndarray, m: int) -> np.ndarray:
    """SNIP-Untergrund (Ryan 1988) mit LLS-Transformation und abnehmendem Fenster (Morháč 1997)."""
    y = np.asarray(y, float)
    v = np.log(np.log(np.sqrt(np.maximum(y, 0) + 1) + 1) + 1)
    n = len(v)
    m = int(max(1, min(m, n // 2 - 1)))
    for p in range(m, 0, -1):
        a = v[p:n - p]
        b = 0.5 * (v[:n - 2 * p] + v[2 * p:])
        v[p:n - p] = np.minimum(a, b)
    return (np.exp(np.exp(v) - 1) - 1) ** 2 - 1


def strip_ka2(tth: np.ndarray, y: np.ndarray, lam1: float, lam2: float, ratio: float) -> np.ndarray:
    """Kα2-Anteil abziehen (Rachinger 1948): I₁(2θ) = I(2θ) − R·I₁(2θ′), 2θ′ = Lage der α1-Linie, deren α2 bei 2θ liegt."""
    out = y.astype(float).copy()
    th = np.radians(tth / 2)
    src = np.sin(th) * lam1 / lam2
    tth1 = np.where(src < 1, np.degrees(2 * np.arcsin(np.clip(src, -1, 1))), np.nan)
    for i in range(len(tth)):
        t1 = tth1[i]
        if not np.isfinite(t1) or t1 < tth[0]:
            continue
        j = np.searchsorted(tth, t1)
        if j <= 0 or j >= len(tth):
            continue
        f = (t1 - tth[j - 1]) / (tth[j] - tth[j - 1])
        out[i] = y[i] - ratio * (out[j - 1] * (1 - f) + out[j] * f)
    return out


# ----------------------------------------------------------------------------- Reflexe
def pv(x, x0, h, fwhm, eta):
    dx = (x - x0) / (fwhm / 2)
    return h * (eta / (1 + dx ** 2) + (1 - eta) * np.exp(-math.log(2) * dx ** 2))


def pv_area(h, fwhm, eta):
    return h * fwhm / 2 * (eta * math.pi + (1 - eta) * math.sqrt(math.pi / math.log(2)))


def ka2_pos(tth, lam1, lam2):
    x = lam2 / lam1 * np.sin(np.radians(np.asarray(tth, float) / 2))
    return np.degrees(2 * np.arcsin(np.clip(x, -1, 1)))


def find_peaks(tth, y, min_rel: float = 2.0, min_sep: float = 0.15) -> list[int]:
    """Lokale Maxima mit Prominenz ≥ min_rel % des grössten Werts und Abstand ≥ min_sep Grad."""
    y = np.asarray(y, float)
    n = len(y)
    if n < 5:
        return []
    step = float(np.median(np.diff(tth)))
    ys = savgol(y, max(5, int(round(min_sep / step / 2)) | 1), 2)      # Rauschen nicht als Maxima zählen
    top = float(np.max(ys))
    if top <= 0:
        return []
    cand = np.flatnonzero((ys[1:-1] > ys[:-2]) & (ys[1:-1] >= ys[2:])) + 1
    # topographische Prominenz: Abstand zum höheren der beiden Sattel bis zum nächsten höheren Punkt
    left = np.full(n, -1)
    stack: list[int] = []
    for i in range(n):
        while stack and ys[stack[-1]] <= ys[i]:
            stack.pop()
        left[i] = stack[-1] if stack else -1
        stack.append(i)
    right = np.full(n, n)
    stack = []
    for i in range(n - 1, -1, -1):
        while stack and ys[stack[-1]] < ys[i]:
            stack.pop()
        right[i] = stack[-1] if stack else n
        stack.append(i)
    out = []
    for i in cand:
        lmin = float(ys[left[i] + 1:i + 1].min()) if left[i] >= 0 else float(ys[:i + 1].min())
        rmin = float(ys[i:right[i]].min()) if right[i] < n else float(ys[i:].min())
        prom = ys[i] - max(lmin, rmin)
        if prom >= min_rel / 100 * top:
            j = int(max(0, i - 2) + np.argmax(y[max(0, i - 2):i + 3]))
            out.append((float(ys[i]), j))
    out.sort(reverse=True)
    keep: list[int] = []
    for _, i in out:
        if all(abs(tth[i] - tth[j]) >= min_sep for j in keep):
            keep.append(i)
    return sorted(keep)


def fit_peaks(tth, y, idx, lam1=None, lam2=None, ratio=0.5, doublet=False) -> list[dict]:
    """Je Gruppe überlappender Reflexe eine gemeinsame Anpassung: pseudo-Voigt je Reflex (+ Kα2-Linie, falls doublet)
    auf linearem Restuntergrund. Gibt je Reflex 2θ, Höhe, FWHM, η, Fläche, Integralbreite zurück."""
    tth = np.asarray(tth, float)
    y = np.asarray(y, float)
    step = float(np.median(np.diff(tth)))
    est = []
    for i in idx:
        half = y[i] / 2
        lo = i
        while lo > 0 and y[lo] > half:
            lo -= 1
        hi = i
        while hi < len(y) - 1 and y[hi] > half:
            hi += 1
        w = max((tth[hi] - tth[lo]), 3 * step)
        est.append([float(tth[i]), float(y[i]), float(w), 0.5])
    groups: list[list[int]] = []
    for k in range(len(idx)):
        if groups and est[k][0] - est[groups[-1][-1]][0] < 2.5 * (est[k][2] + est[groups[-1][-1]][2]):
            groups[-1].append(k)
        else:
            groups.append([k])
    use2 = bool(doublet and lam1 and lam2)
    out: list[dict | None] = [None] * len(idx)
    for g in groups:
        x_lo = est[g[0]][0] - 3 * est[g[0]][2]
        x_hi = est[g[-1]][0] + 3 * est[g[-1]][2] + (abs(float(ka2_pos(est[g[-1]][0], lam1, lam2)) - est[g[-1]][0]) if use2 else 0)
        sel = (tth >= x_lo) & (tth <= x_hi)
        xs, ys = tth[sel], y[sel]
        if len(xs) < 4 * len(g) + 2:
            for k in g:
                x0, h, w, e = est[k]
                out[k] = {"tth": x0, "height": h, "fwhm": w, "eta": e, "area": pv_area(h, w, e), "fitted": False}
            continue
        p0 = [float(np.min(ys)), 0.0]
        lo_b, hi_b = [-np.inf, -np.inf], [np.inf, np.inf]
        for k in g:
            x0, h, w, e = est[k]
            p0 += [x0, h, w, e]
            lo_b += [x0 - w, 0, step / 2, 0]
            hi_b += [x0 + w, np.inf, 10 * w + 1, 1]
        xc = float(xs.mean())

        def model(x, p, g=g):
            out_ = p[0] + p[1] * (x - xc)
            for j in range(len(g)):
                x0, h, w, e = p[2 + 4 * j: 6 + 4 * j]
                out_ = out_ + pv(x, x0, h, w, e)
                if use2:
                    out_ = out_ + pv(x, ka2_pos(x0, lam1, lam2), h * ratio, w, e)
            return out_
        try:
            r = lm(model, p0, xs, ys, lo=lo_b, hi=hi_b, maxit=100)
            p, se = r["p"], r["se"]
            for j, k in enumerate(g):
                x0, h, w, e = p[2 + 4 * j: 6 + 4 * j]
                out[k] = {"tth": float(x0), "height": float(h), "fwhm": float(w), "eta": float(e),
                          "area": pv_area(h, w, e), "fitted": True,
                          "s_tth": float(se[2 + 4 * j]) if np.isfinite(se[2 + 4 * j]) else None,
                          "s_fwhm": float(se[4 + 4 * j]) if np.isfinite(se[4 + 4 * j]) else None}
        except (FitError, np.linalg.LinAlgError, ValueError):
            for k in g:
                x0, h, w, e = est[k]
                out[k] = {"tth": x0, "height": h, "fwhm": w, "eta": e, "area": pv_area(h, w, e), "fitted": False}
    for o in out:
        if o:
            o["beta"] = o["area"] / o["height"] if o["height"] > 0 else None
    return [o for o in out if o]


# ----------------------------------------------------------------------------- Gitterparameter
def index_cubic(d: list[float], kinds=("sc", "bcc", "fcc", "diamond")) -> list[dict]:
    """Kubische Indizierung: je Gittertyp und Startzuordnung a_i = d_i·√N_i; Rangfolge nach relativer Streuung von a
    und der Zahl der fehlenden erlaubten Linien. Gibt die Kandidaten (beste zuerst) zurück."""
    d = sorted([float(x) for x in d if x and x > 0], reverse=True)
    if len(d) < 3:
        raise XrdCalcError("Für eine Indizierung braucht es mindestens drei Reflexe")
    inv = np.array([1 / x ** 2 for x in d])
    out = []
    for kind in kinds:
        seq = C.cubic_sequence(kind, 60)
        Ns = [N for N, _ in seq]
        rep = dict(seq)
        for start in range(min(4, len(Ns))):
            a2 = Ns[start] / inv[0]                         # a² aus der ersten Linie
            assign = []
            for q in inv:
                Nq = q * a2
                best = min(Ns, key=lambda N: abs(N - Nq))
                assign.append(best)
            if len(set(assign)) < len(assign):
                continue
            a = np.array([dd * math.sqrt(N) for dd, N in zip(d, assign)])
            rel = float(np.std(a) / np.mean(a))
            missing = sum(1 for N in Ns if N < max(assign) and N not in assign)
            out.append({"kind": kind, "label": C.CUBIC_TYPES[kind], "label_en": C.CUBIC_TYPES_EN[kind],
                        "a": float(np.mean(a)), "rel_sd": rel,
                        "missing": missing, "N": assign, "hkl": ["".join(str(v) for v in rep[N]) for N in assign],
                        "score": rel * 1e3 + 0.5 * missing + 0.2 * start})
    out.sort(key=lambda r: r["score"])
    return out


def nelson_riley(tth) -> np.ndarray:
    th = np.radians(np.asarray(tth, float) / 2)
    return 0.5 * (np.cos(th) ** 2 / np.sin(th) + np.cos(th) ** 2 / th)


def refine_cell(system: str, hkl: list, d: list[float], tth: list[float] | None = None) -> dict:
    """Gitterparameter aus zugeordneten Reflexen: lineare kleinste Quadrate in 1/d²; kubisch zusätzlich Nelson–Riley."""
    H = np.array(hkl, float)
    q = 1 / np.asarray(d, float) ** 2
    s = (system or "").lower()
    if s == "cubic":
        X = (H ** 2).sum(1)[:, None]
        names = ["A"]
    elif s == "tetragonal":
        X = np.c_[H[:, 0] ** 2 + H[:, 1] ** 2, H[:, 2] ** 2]
        names = ["A", "C"]
    elif s in ("hexagonal", "trigonal"):
        X = np.c_[4 / 3 * (H[:, 0] ** 2 + H[:, 0] * H[:, 1] + H[:, 1] ** 2), H[:, 2] ** 2]
        names = ["A", "C"]
    elif s == "orthorhombic":
        X = H ** 2
        names = ["A", "B", "C"]
    else:
        raise XrdCalcError(f"Verfeinerung für das System „{system}“ nicht eingebaut (kubisch bis orthorhombisch)")
    if len(q) < X.shape[1] + 1:
        raise XrdCalcError(f"Zu wenige zugeordnete Reflexe ({len(q)}) für {X.shape[1]} Parameter")
    beta, *_ = np.linalg.lstsq(X, q, rcond=None)
    res = q - X @ beta
    dof = len(q) - X.shape[1]
    cov = (res @ res / dof) * np.linalg.inv(X.T @ X) if dof > 0 else np.zeros((X.shape[1],) * 2)
    out = {"system": s, "n": len(q)}
    for i, nm in enumerate(names):
        v = beta[i]
        if v <= 0:
            raise XrdCalcError("Verfeinerung ergibt keinen positiven Gitterparameter; Zuordnung prüfen")
        L = 1 / math.sqrt(v)
        sL = 0.5 * L / v * math.sqrt(max(cov[i, i], 0)) if dof > 0 else None
        out[{"A": "a", "B": "b", "C": "c"}[nm]] = L
        out["s_" + {"A": "a", "B": "b", "C": "c"}[nm]] = sL
    if s == "cubic" and tth is not None and len(tth) >= 3:
        a_i = np.asarray(d, float) * np.sqrt((H ** 2).sum(1))
        f = linreg(nelson_riley(tth), a_i)
        out["nr"] = {"a0": f["a"], "s_a0": f.get("sa"), "slope": f["b"], "r2": f["r2"],
                     "x": nelson_riley(tth).tolist(), "y": a_i.tolist()}
    return out


# ----------------------------------------------------------------------------- Kristallitgrösse
def inst_fwhm(tth, inst) -> np.ndarray:
    """Instrumentelle FWHM [Grad]: Zahl (konstant) oder {"U","V","W"} nach Caglioti (FWHM² = U tan²θ + V tanθ + W)."""
    tth = np.asarray(tth, float)
    if isinstance(inst, dict):
        t = np.tan(np.radians(tth / 2))
        return np.sqrt(np.maximum(float(inst.get("U", 0)) * t ** 2 + float(inst.get("V", 0)) * t + float(inst.get("W", 0)), 0))
    return np.full_like(tth, float(inst or 0))


def sample_breadth(b_obs, b_inst, correction: str = "quadratic") -> np.ndarray:
    b_obs, b_inst = np.asarray(b_obs, float), np.asarray(b_inst, float)
    if correction == "linear":
        return b_obs - b_inst
    return np.sqrt(np.maximum(b_obs ** 2 - b_inst ** 2, 0))


def scherrer(tth, breadth_deg, lam, K: float = 0.9) -> np.ndarray:
    """D = K λ / (β cos θ) in nm (λ in Å, β in Grad 2θ)."""
    th = np.radians(np.asarray(tth, float) / 2)
    b = np.radians(np.asarray(breadth_deg, float))
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(b > 0, K * lam / (b * np.cos(th)) / 10, np.nan)


def williamson_hall(tth, breadth_deg, lam, K: float = 0.9) -> dict:
    """β cos θ = K λ / D + 4 ε sin θ; Gerade in (4 sin θ, β cos θ), β in rad."""
    th = np.radians(np.asarray(tth, float) / 2)
    b = np.radians(np.asarray(breadth_deg, float))
    x, y = 4 * np.sin(th), b * np.cos(th)
    f = linreg(x, y)
    D = K * lam / f["a"] / 10 if f["a"] > 0 else None
    sD = (K * lam / f["a"] ** 2 / 10 * f["sa"]) if (f["a"] > 0 and f.get("sa")) else None
    return {"D_nm": D, "s_D": sD, "strain": f["b"], "s_strain": f.get("sb"), "r2": f["r2"], "n": f["n"],
            "x": x.tolist(), "y": y.tolist(), "intercept": f["a"]}


# ----------------------------------------------------------------------------- Phasenvergleich
def match_phase(peaks: list[dict], lines: list[dict], tth_range: tuple, tol: float = 0.2, shift: bool = True,
                min_ref: float = 3.0) -> dict:
    """Vergleich gemessener Reflexe mit einem berechneten Diagramm.

    Gütezahl (eigene, ähnlich den Figure-of-Merit-Werten der Suchprogramme):
        Abdeckung = Σ I_ref der gefundenen Linien / Σ I_ref aller Linien im Messbereich (I_ref ≥ min_ref %),
        Lage = 1 − mittlere |Δ2θ| / tol,  Güte = 100 · Abdeckung · (0,5 + 0,5 · Lage).
    Mit shift wird eine gemeinsame Verschiebung im Bereich ±2·tol gesucht (Nullpunkt, Probenhöhe, Gitterdehnung)."""
    lo, hi = tth_range
    ref = [L for L in lines if lo <= L["tth"] <= hi and L["Irel"] >= min_ref]
    if not ref or not peaks:
        return {"score": 0.0, "coverage": 0.0, "explained": 0.0, "shift": 0.0, "pairs": []}
    obs = np.array([p["tth"] for p in peaks])
    oI = np.array([p.get("area") or p.get("height") or 1.0 for p in peaks], float)
    best = None
    shifts = np.arange(-2 * tol, 2 * tol + 1e-9, tol / 10) if shift else [0.0]
    for s in shifts:
        pairs, used = [], set()
        for L in sorted(ref, key=lambda r: -r["Irel"]):
            dif = np.abs(obs - (L["tth"] + s))
            j = int(np.argmin(dif))
            if dif[j] <= tol and j not in used:
                used.add(j)
                pairs.append((L, j, float(obs[j] - L["tth"] - s)))
        cov = sum(L["Irel"] for L, _, _ in pairs) / sum(L["Irel"] for L in ref)
        pos = 1 - (np.mean([abs(e) for _, _, e in pairs]) / tol if pairs else 1)
        score = 100 * cov * (0.5 + 0.5 * pos)
        if best is None or score > best[0] + 1e-9 or (abs(score - best[0]) < 1e-9 and abs(s) < abs(best[1])):
            best = (score, float(s), pairs, cov)
    score, s, pairs, cov = best
    expl = float(sum(oI[j] for _, j, _ in pairs) / oI.sum()) if oI.sum() > 0 else 0.0
    return {"score": float(score), "coverage": float(cov), "explained": expl, "shift": s,
            "pairs": [{"hkl": L["hkl"], "tth_ref": L["tth"], "I_ref": L["Irel"], "peak": j, "dtth": e}
                      for L, j, e in pairs], "n_ref": len(ref)}


def search(peaks: list[dict], phases: list[dict], lam: float, tth_range: tuple, tol: float = 0.2,
           shift: bool = True) -> list[dict]:
    """Alle Phasen bewerten; danach gierig mehrphasig: die beste Phase nimmt ihre Reflexe, die nächste wird an den
    übrigen gemessen."""
    out = []
    for p in phases:
        try:
            lines = C.reflections(p, lam, max(tth_range[0] - 1, 1), min(tth_range[1] + 1, 175))
        except (C.CrystError, ValueError):
            continue
        m = match_phase(peaks, lines, tth_range, tol, shift)
        out.append({"id": p["id"], "name": p.get("name"), "formula": p.get("formula", ""), **m})
    out.sort(key=lambda r: -r["score"])
    return out


def quantify(peaks: list[dict], chosen: list[dict], lam: float, tth_range: tuple, tol: float = 0.2) -> dict:
    """Halbquantitativ: je Phase Skalenfaktor S = Σ A_obs / Σ I_abs der zugeordneten Linien, mit
    I_abs = m |F|² LP / V² (Intensität je Volumenanteil); Volumenanteil ∝ S, Massenanteil ∝ S · ρ.
    Gleichwertig mit RIR-Werten, die aus der Struktur berechnet werden (Chung 1974). Ohne Absorptionsunterschiede,
    Textur, Mikroabsorption und amorphe Anteile."""
    rows = []
    used: set[int] = set()
    for p in chosen:
        cell = C.Cell.of(p["cell"], p.get("system"))
        atoms = C.expand(p)
        lines = C.reflections(p, lam, max(tth_range[0] - 1, 1), min(tth_range[1] + 1, 175), cell=cell, atoms=atoms)
        m = match_phase([pk for i, pk in enumerate(peaks)], lines, tth_range, tol, True)
        pairs = [q for q in m["pairs"] if q["peak"] not in used]
        if not pairs:
            rows.append({"id": p["id"], "name": p.get("name"), "S": 0.0, "rho": C.density(p, atoms, cell), "n": 0})
            continue
        by_t = {round(L["tth"], 6): L for L in lines}
        I_abs = sum(by_t[round(q["tth_ref"], 6)]["I"] * by_t[round(q["tth_ref"], 6)]["m"] / cell.V ** 2
                    for q in pairs if round(q["tth_ref"], 6) in by_t)
        A_obs = sum(peaks[q["peak"]].get("area") or 0 for q in pairs)
        for q in pairs:
            used.add(q["peak"])
        rows.append({"id": p["id"], "name": p.get("name"), "S": A_obs / I_abs if I_abs > 0 else 0.0,
                     "rho": C.density(p, atoms, cell), "n": len(pairs)})
    v = np.array([r["S"] for r in rows])
    w = v * np.array([r["rho"] for r in rows])
    if v.sum() <= 0:
        raise XrdCalcError("Keine zugeordneten Reflexe für eine Mengenabschätzung")
    for r, vi, wi in zip(rows, v / v.sum(), w / w.sum()):
        r["vol"] = float(vi)
        r["mass"] = float(wi)
    return {"rows": rows}


# ----------------------------------------------------------------------------- Gesamtablauf
def analyse(pat, opt: dict, phases_all: list[dict] | None = None) -> dict:
    """Ein Diagramm mit Einstellungen opt auswerten (siehe DEFAULTS). Ergebnis JSON-tauglich."""
    o = {**DEFAULTS, **(opt or {})}
    tth = pat.tth.astype(float)
    y0 = pat.counts.astype(float)
    notes = []
    if o.get("lam1"):
        lam1, lam2, ratio, lam_src = float(o["lam1"]), o.get("lam2"), o.get("ratio"), "Einstellung"
    elif pat.meta.get("lam1"):
        lam1, lam2, ratio, lam_src = float(pat.meta["lam1"]), pat.meta.get("lam2"), pat.meta.get("ratio"), "Datei"
    else:
        lam1, lam2, ratio = C.TUBES["Cu"]
        lam_src = "angenommen: Cu Kα1/Kα2"
        notes.append("Wellenlänge nicht in der Datei: Cu Kα1/Kα2 angenommen (unter Röhre änderbar)")
    lam2 = float(lam2) if lam2 else None
    ratio = float(ratio or 0.5)
    step = float(np.median(np.diff(tth)))
    y = y0.copy()
    if int(o["smooth"] or 0) >= 5:
        y = savgol(y, int(o["smooth"]), 2)
    bg = np.zeros_like(y)
    if o["bg"]:
        bg = snip(y, int(round(float(o["bg_width"]) / step)))
    net = y - bg
    if o["strip_ka2"]:
        if lam2:
            net = strip_ka2(tth, net, lam1, lam2, ratio)
        else:
            notes.append("Kα2-Abzug übersprungen: λ(Kα2) unbekannt")
    idx = find_peaks(tth, net, float(o["min_rel"]), float(o["min_sep"]))
    doublet = bool(o["doublet"] and not o["strip_ka2"] and lam2)
    if o["fit"]:
        peaks = fit_peaks(tth, net, idx, lam1, lam2, ratio, doublet)
        spikes = [p for p in peaks if p["fitted"] and p["fwhm"] < 2 * step]
        if spikes:
            peaks = [p for p in peaks if p not in spikes]
            notes.append(f"{len(spikes)} Spitze(n) schmaler als zwei Messschritte verworfen (Rauschen, Ausreisser)")
        hmax = max([p["height"] for p in peaks] or [0])
        weak = [p for p in peaks if p["fitted"] and p["height"] < 0.5 * float(o["min_rel"]) / 100 * hmax]
        if weak:
            peaks = [p for p in peaks if p not in weak]
            notes.append(f"{len(weak)} Reflex(e) nach der Anpassung unter der halben Mindesthöhe verworfen "
                         "(meist Kα2-Schultern oder Untergrund)")
    else:
        peaks = [{"tth": float(tth[i]), "height": float(net[i]), "fwhm": None, "eta": None, "area": None,
                  "fitted": False, "beta": None} for i in idx]
    top = max([p["height"] for p in peaks] or [1])
    topA = max([p["area"] or 0 for p in peaks] or [1]) or 1
    binst = inst_fwhm([p["tth"] for p in peaks], o.get("inst_U") and {"U": o.get("inst_U"), "V": o.get("inst_V"), "W": o.get("inst_W")} or o["inst_fwhm"])
    for p, bi in zip(peaks, binst):
        p["d"] = float(C.d_from_2theta(p["tth"], lam1))
        p["Irel"] = 100 * p["height"] / top
        p["Arel"] = 100 * (p["area"] or 0) / topA
        if p.get("fwhm"):
            b = p["fwhm"] if o["breadth"] == "fwhm" else p["beta"]
            bs = float(sample_breadth(b, bi, o["correction"]))
            p["b_sample"] = bs
            p["D_nm"] = float(scherrer(p["tth"], bs, lam1, float(o["K"]))) if bs > 0 else None
    res = {"lam1": lam1, "lam2": lam2, "ratio": ratio, "lam_src": lam_src, "doublet": doublet, "notes": notes,
           "peaks": peaks, "step": step, "tth_range": [float(tth[0]), float(tth[-1])]}
    good = [p for p in peaks if p.get("b_sample")]
    if len(good) >= 3:
        try:
            res["wh"] = williamson_hall([p["tth"] for p in good], [p["b_sample"] for p in good], lam1, float(o["K"]))
        except FitError:
            pass
    sel = [p for p in peaks if p["Irel"] >= float(o.get("index_min", 3))]
    if len(sel) >= 3:
        try:
            cand = index_cubic([p["d"] for p in sel])
            if not cand:
                raise XrdCalcError("keine kubische Indizierung")
            res["cubic"] = cand[:4]
            best = cand[0]
            ds = sorted([p["d"] for p in sel], reverse=True)
            tt = [float(C.bragg_2theta(dd, lam1)) for dd in ds]
            rep = dict(C.cubic_sequence(best["kind"], 60))
            hk = [rep[N] for N in best["N"]]
            res["cubic_refined"] = refine_cell("cubic", hk, ds, tt)
        except (XrdCalcError, FitError, ValueError):
            pass
    if o.get("phase_ref") and phases_all is not None:
        ph = next((p for p in phases_all if p["id"] == o["phase_ref"]), None)
        if ph:
            lines = C.reflections(ph, lam1, max(tth[0] - 1, 1), min(tth[-1] + 1, 175))
            m = match_phase(peaks, lines, (tth[0], tth[-1]), float(o["tol"]), bool(o["shift"]))
            res["ref_match"] = {"id": ph["id"], **m}
            byt = {round(L["tth"], 6): L for L in lines}
            hk, ds, tt = [], [], []
            for q in m["pairs"]:
                L = byt.get(round(q["tth_ref"], 6))
                if L:
                    hk.append(L["hkl_list"][0])
                    ds.append(peaks[q["peak"]]["d"])
                    tt.append(peaks[q["peak"]]["tth"])
            try:
                res["ref_refined"] = refine_cell(ph.get("system", ""), hk, ds, tt)
            except (XrdCalcError, np.linalg.LinAlgError) as e:
                res["ref_refined"] = {"error": str(e)}
    if o.get("search") and phases_all:
        ids = set(o.get("search_ids") or [])
        cands = [p for p in phases_all if not ids or p["id"] in ids]
        res["search"] = search(peaks, cands, lam1, (tth[0], tth[-1]), float(o["tol"]), bool(o["shift"]))[:12]
    if o.get("quant_ids") and phases_all:
        chosen = [p for p in phases_all if p["id"] in set(o["quant_ids"])]
        try:
            res["quant"] = quantify(peaks, chosen, lam1, (tth[0], tth[-1]), float(o["tol"]))
        except XrdCalcError as e:
            res["quant"] = {"error": str(e)}
    res["bg"] = bg
    res["net"] = net
    res["y"] = y
    return res
