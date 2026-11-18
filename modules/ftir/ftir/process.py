"""Bearbeitungsschritte für Spektren. Jeder Schritt ist ein dict {"op": ..., Parameter}; die Liste (das Protokoll)
wird immer auf das Originalspektrum angewendet, in der Oberfläche, im Export und im Bericht gleich.

Numerik ohne SciPy: Savitzky-Golay über Kleinste-Quadrate-Koeffizienten, ALS-Basislinie (Eilers & Boelens 2005) mit
eigenem Löser für das fünfbandige Gleichungssystem und λ bezogen auf 1 cm⁻¹ Punktabstand, Gummiband als untere
konvexe Hülle, einfache ATR-Korrektur über die Eindringtiefe d_p ∝ λ (Harrick 1967).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .readers import Spectrum


class OpError(ValueError):
    pass


def P(key, label, type="number", default=None, **kw):
    return {"key": key, "label": label, "type": type, "default": default, **kw}


# needs: welche y-Einheiten der Schritt verlangt ("" = alle)
OPS = {
    "to_abs": {"de": "In Absorbanz umrechnen", "en": "Convert to absorbance", "needs": "T R", "params": []},
    "to_trans": {"de": "In Transmission umrechnen", "en": "Convert to transmittance", "needs": "A", "params": []},
    "km": {"de": "Kubelka-Munk (aus Reflexion)", "en": "Kubelka-Munk (from reflectance)", "needs": "R", "params": []},
    "cut": {"de": "Bereich ausschneiden", "en": "Cut range", "needs": "", "params": [
        P("lo", "von [cm⁻¹]", default=650, min=0), P("hi", "bis [cm⁻¹]", default=4000, min=0)]},
    "interp": {"de": "Auf festes Raster interpolieren", "en": "Interpolate to fixed spacing", "needs": "", "params": [
        P("step", "Abstand [cm⁻¹]", "select", "2", options=[["0.5", "0,5"], ["1", "1"], ["2", "2"], ["4", "4"], ["8", "8"]])]},
    "smooth": {"de": "Glätten", "en": "Smooth", "needs": "", "params": [
        P("method", "Verfahren", "select", "sg", options=[["sg", "Savitzky-Golay"], ["mean", "Gleitender Mittelwert"]]),
        P("points", "Fensterbreite [Punkte, ungerade]", default=9, min=3, max=101, step=2),
        P("order", "Polynomgrad (Savitzky-Golay)", default=2, min=1, max=5, step=1)]},
    "baseline": {"de": "Basislinie korrigieren", "en": "Baseline correction", "needs": "", "params": [
        P("method", "Verfahren", "select", "rubber", options=[["rubber", "Gummiband (konvexe Hülle)"],
                                                              ["als", "Asymmetrische kleinste Quadrate (ALS)"],
                                                              ["poly", "Polynom, iterativ"],
                                                              ["points", "Stützpunkte von Hand"]]),
        P("lam", "ALS: Steifigkeit log₁₀ λ", default=6, min=2, max=10, step=0.5),
        P("lam_ref", "ALS: λ bezogen auf", "select", "cm1",
          options=[["cm1", "1 cm⁻¹ Punktabstand (unabhängig vom Raster)"], ["point", "je Datenpunkt (wie bis Version 1.4)"]]),
        P("p", "ALS: Asymmetrie p", default=0.01, min=0.0005, max=0.2, step=0.005),
        P("deg", "Polynom: Grad", default=3, min=1, max=8, step=1),
        P("interp", "Stützpunkte: Verbindung", "select", "spline", options=[["linear", "linear"], ["spline", "Spline"]]),
        P("pts", "Stützpunkte [cm⁻¹]", "points", [])]},
    "co2": {"de": "CO₂-Banden überbrücken", "en": "Bridge CO₂ bands", "needs": "", "params": [
        P("ranges", "Bereiche", "select", "narrow",
          options=[["narrow", "eng: 2390–2280 und 680–655 cm⁻¹"], ["wide", "weit: 2400–2250 und 720–630 cm⁻¹ (wie bis 1.4)"]])]},
    "atr": {"de": "ATR-Korrektur (Eindringtiefe)", "en": "ATR correction (penetration depth)", "needs": "A", "params": [
        P("ref", "Bezugswellenzahl [cm⁻¹]", default=1000, min=100, max=5000)]},
    "normalize": {"de": "Normieren", "en": "Normalise", "needs": "", "params": [
        P("mode", "Art", "select", "max", options=[["max", "Maximum = 1"], ["minmax", "Minimum 0, Maximum 1"],
                                                   ["vector", "Vektornorm = 1"], ["area", "Fläche = 1"],
                                                   ["peak", "Bande bei … = 1"]]),
        P("at", "Bande bei [cm⁻¹] (für „Bande bei …“)", default=1720, min=0)]},
    "offset": {"de": "Nullpunkt verschieben", "en": "Offset", "needs": "", "params": [
        P("mode", "Art", "select", "min", options=[["min", "Minimum auf 0"], ["value", "Wert addieren"]]),
        P("value", "Wert", default=0)]},
    "scale": {"de": "Mit Faktor multiplizieren", "en": "Multiply by factor", "needs": "", "params": [
        P("factor", "Faktor", default=1)]},
    "deriv": {"de": "Ableitung (Savitzky-Golay)", "en": "Derivative (Savitzky-Golay)", "needs": "", "params": [
        P("order", "Ordnung", "select", "1", options=[["1", "1. Ableitung"], ["2", "2. Ableitung"]]),
        P("points", "Fensterbreite [Punkte, ungerade]", default=11, min=5, max=101, step=2)]},
}

# Atmosphärisches CO₂: asymmetrische Streckschwingung ν₃ (Bandenzentrum ≈ 2349 cm⁻¹, P- und R-Zweig) und
# Deformationsschwingung ν₂ (Q-Zweig ≈ 667 cm⁻¹). "narrow" (Standard) umfasst nur diese Banden, damit Probenbanden
# daneben (Isocyanat ≈ 2270, Polystyrol 698, Calcit 712 cm⁻¹) erhalten bleiben; "wide" sind die Bereiche bis 1.4.
CO2_SETS = {"narrow": [(2390.0, 2280.0), (680.0, 655.0)], "wide": [(2400.0, 2250.0), (720.0, 630.0)]}
CO2_RANGES = CO2_SETS["narrow"]
# Erwartete Lage des grössten CO₂-Ausschlags je Bereich (ν₃: P/R-Zweige 2330–2370; ν₂: Q-Zweig 662–672 cm⁻¹)
CO2_PEAK = {0: (2330.0, 2370.0), 1: (662.0, 672.0)}
CO2_FLANK = 15.0          # cm⁻¹ ausserhalb des Bereichs, in denen eine Probenbande die Brücke stören würde
ALS_REF_STEP = 1.0        # cm⁻¹: λ gilt für diesen Punktabstand und wird mit (1 cm⁻¹/Δν̃)⁴ umgerechnet


@dataclass
class Proc:
    spectrum: Spectrum
    steps: list = field(default_factory=list)       # lesbare Beschreibung je Schritt
    baseline: np.ndarray | None = None              # zuletzt abgezogene Basislinie (auf spectrum.x)
    warnings: list = field(default_factory=list)    # Hinweise der Schritte [{"kind", "de", "en"}]


# ----------------------------------------------------------------------------- Numerik
def sg_coeffs(window: int, order: int, deriv: int = 0) -> np.ndarray:
    window = max(3, int(window) | 1)
    order = min(int(order), window - 1)
    k = window // 2
    A = np.vander(np.arange(-k, k + 1, dtype=float), order + 1, increasing=True)
    c = np.linalg.pinv(A)[deriv] * math.factorial(deriv)
    return c[::-1]


def savgol(y: np.ndarray, window: int, order: int, deriv: int = 0, dx: float = 1.0) -> np.ndarray:
    window = max(3, int(window) | 1)
    if window > len(y):
        window = len(y) if len(y) % 2 else len(y) - 1
    order = min(int(order), window - 1)
    k = window // 2
    c = sg_coeffs(window, order, deriv)
    yp = np.concatenate([2 * y[0] - y[k:0:-1], y, 2 * y[-1] - y[-2:-k - 2:-1]])   # Punktspiegelung am Rand
    out = np.convolve(yp, c, mode="valid")
    return out / (dx ** deriv) if deriv else out


def moving_mean(y: np.ndarray, window: int) -> np.ndarray:
    window = max(1, int(window) | 1)
    k = window // 2
    yp = np.concatenate([np.full(k, y[0]), y, np.full(k, y[-1])])
    return np.convolve(yp, np.ones(window) / window, mode="valid")


def rubberband(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Untere konvexe Hülle (Andrew's monotone chain), linear verbunden."""
    pts = []
    for i in range(len(x)):
        while len(pts) >= 2:
            (x1, y1), (x2, y2) = (x[pts[-2]], y[pts[-2]]), (x[pts[-1]], y[pts[-1]])
            if (x2 - x1) * (y[i] - y1) - (y2 - y1) * (x[i] - x1) <= 0:
                pts.pop()
            else:
                break
        pts.append(i)
    return np.interp(x, x[pts], y[pts])


def _penta_solve(a0, a1, a2, b):
    """Löst A z = b für symmetrisches, positiv definites fünfbandiges A (LDLᵀ)."""
    n = len(a0)
    d = np.empty(n)
    e = np.zeros(n)
    f = np.zeros(n)
    for i in range(n):
        di = a0[i]
        if i >= 1:
            di -= e[i - 1] * e[i - 1] * d[i - 1]
        if i >= 2:
            di -= f[i - 2] * f[i - 2] * d[i - 2]
        d[i] = di
        if i < n - 1:
            ei = a1[i]
            if i >= 1:
                ei -= f[i - 1] * e[i - 1] * d[i - 1]
            e[i] = ei / di
        if i < n - 2:
            f[i] = a2[i] / di
    z = np.empty(n)
    for i in range(n):
        v = b[i]
        if i >= 1:
            v -= e[i - 1] * z[i - 1]
        if i >= 2:
            v -= f[i - 2] * z[i - 2]
        z[i] = v
    z /= d
    xs = np.empty(n)
    for i in range(n - 1, -1, -1):
        v = z[i]
        if i + 1 < n:
            v -= e[i] * xs[i + 1]
        if i + 2 < n:
            v -= f[i] * xs[i + 2]
        xs[i] = v
    return xs


def als_lambda(x: np.ndarray, log_lam: float, ref: str = "cm1") -> float:
    """λ für als_baseline. ref "cm1": log_lam gilt für 1 cm⁻¹ Punktabstand; bei Abstand h wird λ = 10^log_lam · (1/h)⁴
    verwendet. Begründung: Σ wᵢ(yᵢ − zᵢ)² + λ Σ(Δ²zᵢ)² ≈ (1/h)·[∫w(y − z)² dν̃ + λh⁴ ∫(z'')² dν̃]; die Glättung hängt
    also von λh⁴ ab, und dieselbe Kurve wird bei jedem Raster gleich steif. ref "point": λ = 10^log_lam je Datenpunkt
    (Verhalten bis Version 1.4; dieselbe Zahl glättet bei feinerem Raster weniger)."""
    lam = 10 ** float(log_lam)
    if ref == "point":
        return lam
    h = float(np.median(np.diff(x))) if len(x) > 1 else ALS_REF_STEP
    return lam * (ALS_REF_STEP / h) ** 4 if h > 0 else lam


def als_baseline(y: np.ndarray, lam: float = 1e6, p: float = 0.01, niter: int = 10) -> np.ndarray:
    """Asymmetrische Glättung nach Eilers & Boelens (2005): minimiert Σ wᵢ(yᵢ − zᵢ)² + λ Σ(Δ²zᵢ)² mit wᵢ = p über der
    Kurve (yᵢ > zᵢ) und 1 − p darunter; λ wirkt je Datenpunkt (Umrechnung auf cm⁻¹: als_lambda)."""
    n = len(y)
    if n < 5:
        return np.full(n, float(np.min(y)))
    d0 = np.full(n, 6.0)
    d0[[0, -1]] = 1.0
    d0[[1, -2]] = 5.0
    d1 = np.full(n - 1, -4.0)
    d1[[0, -1]] = -2.0
    d2 = np.ones(n - 2)
    w = np.ones(n)
    z = y.copy()
    for _ in range(niter):
        z = _penta_solve(w + lam * d0, lam * d1, lam * d2, w * y)
        w_new = np.where(y > z, p, 1 - p)
        if np.array_equal(w_new, w):
            break
        w = w_new
    return z


def poly_baseline(x: np.ndarray, y: np.ndarray, deg: int = 3, niter: int = 100) -> np.ndarray:
    """Iterativ angepasstes Polynom ("modified polyfit", Lieber & Mahadevan-Jansen 2003, Applied Spectroscopy 57,
    1363–1367): Punkte über der Kurve werden auf die Kurve gesetzt und neu angepasst."""
    t = (x - x.mean()) / ((x.max() - x.min()) / 2 or 1)
    yy = y.copy()
    fit = yy
    for _ in range(niter):
        c = np.polynomial.polynomial.polyfit(t, yy, int(deg))
        fit = np.polynomial.polynomial.polyval(t, c)
        nyy = np.minimum(yy, fit)
        if np.allclose(nyy, yy, atol=1e-9 * (np.ptp(y) or 1)):
            break
        yy = nyy
    return fit


def _natural_spline(xk, yk, x):
    n = len(xk)
    if n < 3:
        return np.interp(x, xk, yk)
    h = np.diff(xk)
    A = np.zeros((n, n))
    r = np.zeros(n)
    A[0, 0] = A[-1, -1] = 1
    for i in range(1, n - 1):
        A[i, i - 1], A[i, i], A[i, i + 1] = h[i - 1], 2 * (h[i - 1] + h[i]), h[i]
        r[i] = 6 * ((yk[i + 1] - yk[i]) / h[i] - (yk[i] - yk[i - 1]) / h[i - 1])
    m = np.linalg.solve(A, r)
    j = np.clip(np.searchsorted(xk, x) - 1, 0, n - 2)
    t = x - xk[j]
    hj = h[j]
    a = yk[j]
    b = (yk[j + 1] - yk[j]) / hj - hj * (2 * m[j] + m[j + 1]) / 6
    return a + b * t + m[j] / 2 * t ** 2 + (m[j + 1] - m[j]) / (6 * hj) * t ** 3


def points_baseline(x: np.ndarray, y: np.ndarray, pts, mode: str = "spline") -> np.ndarray:
    pts = sorted({float(p) for p in pts or [] if x[0] <= float(p) <= x[-1]})
    if len(pts) < 2:
        raise OpError("Für die Basislinie von Hand mindestens zwei Stützpunkte setzen (Werkzeug „Basislinienpunkte“).")
    xk = np.array(pts)
    yk = []
    for p in xk:
        i = int(np.clip(np.searchsorted(x, p), 0, len(x) - 1))
        lo, hi = max(0, i - 2), min(len(x), i + 3)
        yk.append(float(np.mean(y[lo:hi])))
    yk = np.array(yk)
    base = _natural_spline(xk, yk, x) if mode == "spline" and len(xk) >= 3 else np.interp(x, xk, yk)
    return base


def to_absorbance(y: np.ndarray, unit: str) -> np.ndarray:
    if unit in ("T", "R"):
        return -np.log10(np.clip(y / 100.0, 1e-4, None))
    return y


def baseline_of(x, y, st) -> np.ndarray:
    m = st.get("method", "rubber")
    if m == "rubber":
        return rubberband(x, y)
    if m == "als":
        ref = st.get("lam_ref", "cm1")
        if ref not in ("cm1", "point"):
            raise OpError(f"ALS: unbekannter Bezug für λ „{ref}“")
        return als_baseline(y, als_lambda(x, float(st.get("lam", 6)), ref), float(st.get("p", 0.01)))
    if m == "poly":
        return poly_baseline(x, y, int(st.get("deg", 3)))
    if m == "points":
        return points_baseline(x, y, st.get("pts"), st.get("interp", "spline"))
    raise OpError(f"Unbekanntes Basislinienverfahren: {m}")


# ----------------------------------------------------------------------------- Schritte
def describe_step(st: dict, lang: str = "de") -> str:
    op = st.get("op")
    d = OPS.get(op, {})
    name = d.get("de" if lang == "de" else "en", op)
    if op == "cut":
        return f"{name}: {st.get('lo')}–{st.get('hi')} cm⁻¹"
    if op == "interp":
        return f"{name}: {st.get('step')} cm⁻¹"
    if op == "smooth":
        return f"{name}: {'Savitzky-Golay' if st.get('method', 'sg') == 'sg' else 'Mittelwert'}, {st.get('points', 9)} Punkte" + \
            (f", Grad {st.get('order', 2)}" if st.get("method", "sg") == "sg" else "")
    if op == "baseline":
        m = st.get("method", "rubber")
        lref = "je Punkt" if st.get("lam_ref", "cm1") == "point" else "für 1 cm⁻¹ Punktabstand"
        extra = {"rubber": "Gummiband", "als": f"ALS, log λ = {st.get('lam', 6)} ({lref}), p = {st.get('p', 0.01)}",
                 "poly": f"Polynom Grad {st.get('deg', 3)}", "points": f"{len(st.get('pts') or [])} Stützpunkte"}.get(m, m)
        return f"{name}: {extra}"
    if op == "co2":
        rs = CO2_SETS.get(st.get("ranges", "narrow"), CO2_RANGES)
        return f"{name}: " + ", ".join(f"{hi:.0f}–{lo:.0f}" for hi, lo in rs) + " cm⁻¹"
    if op == "atr":
        return f"{name}: Bezug {st.get('ref', 1000)} cm⁻¹"
    if op == "normalize":
        mode = st.get("mode", "max")
        return f"{name}: " + {"max": "Maximum", "minmax": "Min/Max", "vector": "Vektornorm", "area": "Fläche",
                              "peak": f"Bande bei {st.get('at')} cm⁻¹"}.get(mode, mode)
    if op == "offset":
        return f"{name}: " + ("Minimum auf 0" if st.get("mode", "min") == "min" else f"+{st.get('value')}")
    if op == "scale":
        return f"{name}: × {st.get('factor')}"
    if op == "deriv":
        return f"{name}: {st.get('order', 1)}. Ordnung, {st.get('points', 11)} Punkte"
    return name


def _num(st, key, dflt):
    try:
        v = float(st.get(key, dflt))
    except (TypeError, ValueError):
        raise OpError(f"Ungültiger Wert für {key}")
    if not math.isfinite(v):
        raise OpError(f"Ungültiger Wert für {key}")
    return v


ABS_LIKE = ("A", "LR", "KM", "au")       # Banden zeigen nach oben, Werte proportional zur Absorption (oder unbekannt)
_UNIT_DE = {"T": "Transmission", "R": "Reflexion", "D1": "Ableitungen", "D2": "Ableitungen"}


def co2_overlap(x, y, yunit, lo, hi, k) -> dict | None:
    """Prüft, ob im überbrückten CO₂-Bereich mehr als CO₂ liegt; gibt dann einen Hinweis zurück.

    Kriterien (in Richtung der Banden, d. h. −y bei T/R): (1) In den 15 cm⁻¹ breiten Flanken direkt ausserhalb des
    Bereichs weicht die Kurve um mehr als max(5σ, 20 % des Ausschlags im Bereich) von der Geraden durch die Flanken
    ab – eine Probenbande reicht über die Grenze. (2) Der grösste Ausschlag im Bereich liegt nicht dort, wo CO₂
    absorbiert (ν₃: 2330–2370, ν₂: 662–672 cm⁻¹). σ: Rauschen (quality.py) der ganzen Kurve."""
    s = -np.asarray(y, float) if yunit in ("T", "R") else np.asarray(y, float)
    fl = ((x >= lo - CO2_FLANK) & (x < lo)) | ((x > hi) & (x <= hi + CO2_FLANK))
    inside = (x >= lo) & (x <= hi)
    if fl.sum() < 4 or inside.sum() < 3:
        return None
    c = np.polyfit(x[fl], s[fl], 1)
    d_in = s[inside] - np.polyval(c, x[inside])
    d_fl = s[fl] - np.polyval(c, x[fl])
    amp = float(np.max(np.abs(d_in)))
    from . import quality as Q
    sigma = float(Q.assess(x, s, "A")["sigma"]) if len(x) >= 30 else 0.0
    reasons = []
    if float(np.max(d_fl)) > max(5 * sigma, 0.2 * amp) and float(np.max(d_fl)) > 0:
        reasons.append(("eine Bande reicht über die Bereichsgrenze", "a band extends across the range limit"))
    pk_lo, pk_hi = CO2_PEAK.get(k, (lo, hi))
    if amp > 5 * sigma:
        xp = float(x[inside][np.argmax(np.abs(d_in))])
        if not pk_lo <= xp <= pk_hi:
            reasons.append((f"der grösste Ausschlag liegt bei {xp:.0f} cm⁻¹, nicht bei CO₂ ({pk_hi:.0f}–{pk_lo:.0f})",
                            f"the largest feature is at {xp:.0f} cm⁻¹, not at CO₂ ({pk_hi:.0f}–{pk_lo:.0f})"))
    if not reasons:
        return None
    return {"kind": "co2_overlap", "range": [hi, lo],
            "de": f"CO₂-Überbrückung {hi:.0f}–{lo:.0f} cm⁻¹: womöglich wird eine Probenbande entfernt ("
                  + "; ".join(r[0] for r in reasons) + "). Spektrum vor und nach dem Schritt vergleichen.",
            "en": f"CO₂ bridge {hi:.0f}–{lo:.0f} cm⁻¹: a sample band may be removed ("
                  + "; ".join(r[1] for r in reasons) + "). Compare the spectrum before and after this step."}


def apply_step(sp: Spectrum, st: dict, i: int = 0, warn: list | None = None) -> tuple[Spectrum, np.ndarray | None]:
    op = st.get("op")
    if op not in OPS:
        raise OpError(f"Schritt {i + 1}: unbekannter Bearbeitungsschritt „{op}“")
    need = OPS[op]["needs"]
    if need and sp.yunit not in need.split():
        want = {"T R": "Transmission oder Reflexion", "A": "Absorbanz", "R": "Reflexion"}.get(need, need)
        raise OpError(f"Schritt {i + 1} ({OPS[op]['de']}): braucht ein Spektrum in {want}.")
    x, y = sp.x, sp.y
    base = None
    if op == "to_abs":
        lab = "LR" if sp.yunit == "R" else "A"
        return sp.copy(y=to_absorbance(y, sp.yunit), yunit=lab), None
    if op == "to_trans":
        return sp.copy(y=100 * 10 ** (-y), yunit="T"), None
    if op == "km":
        r = np.clip(y / 100, 1e-4, 1.0)
        return sp.copy(y=(1 - r) ** 2 / (2 * r), yunit="KM"), None
    if op == "cut":
        lo, hi = sorted((_num(st, "lo", 650), _num(st, "hi", 4000)))
        m = (x >= lo) & (x <= hi)
        if m.sum() < 10:
            raise OpError(f"Schritt {i + 1}: im Bereich {lo:g}–{hi:g} cm⁻¹ liegen kaum Messpunkte.")
        return sp.copy(x=x[m], y=y[m]), None
    if op == "interp":
        s = _num(st, "step", 2)
        if s <= 0:
            raise OpError("Abstand muss grösser als 0 sein")
        xs = np.arange(math.ceil(x[0] / s) * s, x[-1] + 1e-9, s)
        return sp.copy(x=xs, y=np.interp(xs, x, y)), None
    if op == "smooth":
        n = int(_num(st, "points", 9))
        if st.get("method", "sg") == "mean":
            return sp.copy(y=moving_mean(y, n)), None
        return sp.copy(y=savgol(y, n, int(_num(st, "order", 2)))), None
    if op == "baseline":
        valley = sp.yunit in ("T", "R")
        yy = -y if valley else y
        base = baseline_of(x, yy, st)
        if valley:
            base = -base
            return sp.copy(y=y - base + 100.0), base               # Basislinie auf 100 %
        return sp.copy(y=y - base), base
    if op == "co2":
        sel = st.get("ranges", "narrow")
        if sel not in CO2_SETS:
            raise OpError(f"Schritt {i + 1}: unbekannte CO₂-Bereiche „{sel}“")
        yy = y.copy()
        for k, (hi, lo) in enumerate(CO2_SETS[sel]):
            m = (x >= lo) & (x <= hi)
            if m.sum() < 2:
                continue
            idx = np.where(m)[0]
            a, b = max(0, idx[0] - 3), min(len(x), idx[-1] + 4)
            ya, yb = float(np.mean(y[a:idx[0] + 1])), float(np.mean(y[idx[-1]:b]))
            yy[m] = np.interp(x[m], [x[idx[0]], x[idx[-1]]], [ya, yb])
            if warn is not None:
                w = co2_overlap(x, y, sp.yunit, lo, hi, k)
                if w:
                    warn.append(w)
        return sp.copy(y=yy), None
    if op == "atr":
        # Einfache ATR-Korrektur: Eindringtiefe d_p = λ / (2π n₁ √(sin²θ − (n₂/n₁)²)) (Harrick 1967) ist bei festem
        # Einfallswinkel und konstanten Brechzahlen proportional zur Wellenlänge, also zu 1/ν̃; bei schwacher Absorption
        # ist die Absorbanz proportional zu d_p. Korrektur auf die Eindringtiefe bei ν̃_ref: y · ν̃/ν̃_ref.
        ref = _num(st, "ref", 1000)
        if ref <= 0:
            raise OpError(f"Schritt {i + 1}: Bezugswellenzahl muss grösser als 0 sein")
        return sp.copy(y=y * x / ref), None
    if op == "normalize":
        mode = st.get("mode", "max")
        if mode == "max":
            d = float(np.max(np.abs(y)))
            out = y / d if d else y
        elif mode == "minmax":
            d = float(np.ptp(y))
            out = (y - y.min()) / d if d else y
        elif mode == "vector":
            d = float(np.linalg.norm(y))
            out = y / d if d else y
        elif mode == "area":
            d = float(abs(np.trapezoid(y, x)) if hasattr(np, "trapezoid") else abs(np.trapz(y, x)))
            out = y / d if d else y
        else:
            if sp.yunit not in ABS_LIKE:
                raise OpError(f"Schritt {i + 1} (Normieren auf eine Bande): nur für absorbanzartige Spektren (Absorbanz, "
                              f"log(1/R), Kubelka-Munk, Intensität), nicht für {_UNIT_DE.get(sp.yunit, sp.yunit)}. "
                              "Vorher „In Absorbanz umrechnen“ anwenden.")
            at = _num(st, "at", 1720)
            m = np.abs(x - at) <= 5
            if not m.any():
                raise OpError(f"Schritt {i + 1}: {at:g} cm⁻¹ liegt ausserhalb des Spektrums.")
            v = float(np.max(y[m]))
            if not v > 0:
                raise OpError(f"Schritt {i + 1}: bei {at:g} cm⁻¹ ist keine positive Bande (Maximum {v:.3g}); "
                              "Normieren darauf nicht möglich.")
            out = y / v
        return sp.copy(y=out), None
    if op == "offset":
        if st.get("mode", "min") == "min":
            return sp.copy(y=y - y.min()), None
        return sp.copy(y=y + _num(st, "value", 0)), None
    if op == "scale":
        return sp.copy(y=y * _num(st, "factor", 1)), None
    if op == "deriv":
        o = int(_num(st, "order", 1))
        n = int(_num(st, "points", 11))
        return sp.copy(y=savgol(y, n, max(2, o + 1) if o == 1 else 3, o, sp.step), yunit="D1" if o == 1 else "D2"), None
    raise OpError(f"Schritt {i + 1}: nicht umgesetzt")


def apply(sp: Spectrum, pipeline: list | None, lang: str = "de") -> Proc:
    cur = sp
    steps, base, warns = [], None, []
    for i, st in enumerate(pipeline or []):
        if not isinstance(st, dict):
            raise OpError(f"Schritt {i + 1}: ungültig")
        cur, b = apply_step(cur, st, i, warns)
        if b is not None:
            base = (cur.x.copy(), b)
        elif base is not None and (len(base[0]) != len(cur.x) or not np.array_equal(base[0], cur.x)):
            base = None
        steps.append(describe_step(st, lang))
    return Proc(cur, steps, base[1] if base is not None else None, warns)
