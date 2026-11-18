"""Lastspitzen bei fortschreitendem Versagen (z. B. Seile, Faserbündel, Verbunde).

Die Last steigt auf ein Maximum, fällt ab, wenn ein Teil reisst, steigt wieder, fällt wieder … (Sägezahn). Erkannt
werden die Spitzen mit einer Schwellenregel mit Hysterese (Zickzack-Regel) auf den Lastabfällen:

- Δ = max(Anteil · y_max, 3 · Anzeigeauflösung), Anteil voreingestellt 0,05 (5 % von Fmax bzw. Rm).
- Steigend: das laufende Maximum mitführen (nur ein echt grösserer Wert ersetzt es, bei einem flachen Maximum gilt
  also der erste Punkt). Liegt ein Punkt um mindestens Δ unter dem laufenden Maximum, ist dieses Maximum eine
  Lastspitze.
- Fallend: das laufende Minimum mitführen (ebenfalls der erste Punkt eines flachen Minimums). Liegt ein Punkt um
  mindestens Δ über dem Minimum, ist dieses Minimum das Tal nach der Spitze, und die Suche nach der nächsten Spitze
  beginnt bei diesem Punkt.
- Am Ende des aktiven Abschnitts: fällt die Kurve gerade, ist das bisherige Minimum das letzte Tal; steigt sie gerade,
  ist das laufende Maximum keine Spitze (kein Abfall um Δ danach).

Je Spitze: Lage, Last, Tal danach, Abfall, Dauer des Abfalls, Verhältnis zur vorigen Spitze, Steifigkeit des
Wiederanstiegs, Arbeit im Abschnitt. Die Spitzenlasten werden gegen die Verlängerung bei der Spitze ausgeglichen,
mit einer Geraden y = a + b·x und einer Exponentialfunktion y = a·exp(b·x) (labcalc.fitting, direkt in y).
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

DEFAULT_DROP_FRAC = 0.05      # Lastabfall, ab dem eine Spitze zählt, als Anteil von y_max
RESOLUTION_FACTOR = 3.0       # Δ mindestens 3 Anzeigeauflösungen: Rauschen zählt nie
STIFF_BAND = (0.20, 0.80)     # Steifigkeit des Wiederanstiegs zwischen 20 % und 80 % des Anstiegs
MIN_FIT = 3                   # Ausgleich erst ab 3 Spitzen (2 Parameter, mindestens 1 Freiheitsgrad)
MAX_VARS = 20                 # höchstens so viele Spitzen als Variablen Fpk1 … für eigene Gleichungen
FIT_POINTS = 80               # Stützpunkte der Ausgleichskurven für die Diagramme

X_LABELS = {   # (de, en, Einheit)
    "strain": ("Dehnung ε bei der Spitze", "Strain ε at the peak", "%"),
    "travel": ("Traversenweg v·(t − t₀) bei der Spitze", "Crosshead travel v·(t − t₀) at the peak", "mm"),
    "time": ("Zeit t bei der Spitze", "Time t at the peak", "s"),
}


def detect(y, delta: float) -> list[tuple[int, int]]:
    """Spitzen nach der Hysterese-Regel: Liste (Index der Spitze, Index des Tals danach)."""
    y = np.asarray(y, dtype=float)
    n = len(y)
    out: list[tuple[int, int]] = []
    if n == 0 or not (delta > 0):
        return out
    rising, imax, imin = True, 0, 0
    for i in range(1, n):
        v = y[i]
        if rising:
            if v > y[imax]:
                imax = i
            elif v <= y[imax] - delta:
                rising, imin = False, i
        else:
            if v < y[imin]:
                imin = i
            elif v >= y[imin] + delta:
                out.append((imax, imin))
                rising, imax = True, i
    if not rising:
        out.append((imax, imin))
    return out


def threshold(ymax: float, resolution: float, frac: float) -> tuple[float, str]:
    """(Δ, Grundlage): Δ = max(Anteil · y_max, 3 · Auflösung); Grundlage "anteil" oder "aufloesung"."""
    a, b = frac * ymax, RESOLUTION_FACTOR * resolution
    return (a, "anteil") if a >= b else (b, "aufloesung")


def x_axis(v_mm_s: float | None, l0: float | None) -> tuple[str, float]:
    """(Art, Faktor) der Verlängerung bei der Spitze: Dehnung in % mit v und L₀ (x = 100·v·(t − t₀)/L₀, wie die
    Dehnung der Auswertung), Traversenweg in mm nur mit v (x = v·(t − t₀)), sonst die Zeit t in s (x = t, ab dem
    ersten Messpunkt; ohne v gibt es keine Verlängerung, und t₀ aus dem linearen Abschnitt wird nicht gebraucht)."""
    if v_mm_s and l0:
        return "strain", v_mm_s / l0 * 100.0
    if v_mm_s:
        return "travel", v_mm_s
    return "time", 1.0


def _fitting():
    try:
        from labcalc import fitting
    except ImportError:  # ausserhalb des Hubs gestartet: SDK aus dem Suite-Ordner holen
        import sys
        p = Path(__file__).resolve().parents[3] / "sdk" / "python"
        if not p.is_dir():
            return None
        sys.path.insert(0, str(p))
        try:
            from labcalc import fitting
        except ImportError:
            return None
    return fitting


def _trapz(y, x) -> float:
    return float(np.trapezoid(y, x)) if hasattr(np, "trapezoid") else float(np.trapz(y, x))


def _stiffness(t, force, s: int, p: int) -> tuple[float | None, int]:
    """Steigung dF/dt [N/s] (kleinste Quadrate) über die Punkte von s bis p, deren Last zwischen 20 % und 80 % des
    Anstiegs von F[s] auf F[p] liegt; (None, n) bei weniger als 2 Punkten oder ohne Zeitspanne."""
    f0, f1 = float(force[s]), float(force[p])
    rise = f1 - f0
    if rise <= 0:
        return None, 0
    lo, hi = f0 + STIFF_BAND[0] * rise, f0 + STIFF_BAND[1] * rise
    seg_t, seg_f = np.asarray(t[s:p + 1], float), np.asarray(force[s:p + 1], float)
    m = (seg_f >= lo) & (seg_f <= hi)
    if m.sum() < 2 or np.ptp(seg_t[m]) <= 0:
        return None, int(m.sum())
    k, _q = np.polyfit(seg_t[m], seg_f[m], 1)
    return float(k), int(m.sum())


def _model(fitting, x, y, model: str, xunit: str, yunit: str) -> dict:
    """Eine Anpassung über labcalc.fitting (direkt in y); Parameter umbenannt auf y = a + b·x bzw. y = a·exp(b·x)."""
    try:
        res = fitting.fit(x, y, "lin" if model == "line" else "exp", mode="direct", xunit=xunit, yunit=yunit)
    except fitting.FitError as e:
        return {"ok": False, "error": str(e)}
    p = {q["sym"]: q for q in res["params"]}
    a, b = (p["b"], p["m"]) if model == "line" else (p["a"], p["b"])
    pv = [a["value"], b["value"]]
    pred = fitting.predict("lin", [b["value"], a["value"]], x) if model == "line" else fitting.predict("exp", pv, x)
    sse = float(np.sum((np.asarray(y, float) - pred) ** 2))
    return {"ok": True, "formula": "y = a + b·x" if model == "line" else "y = a·exp(b·x)",
            "a": a["value"], "a_u": a["u"], "a_ci": a["ci"], "a_unit": a["unit"],
            "b": b["value"], "b_u": b["u"], "b_ci": b["ci"], "b_unit": b["unit"],
            "r2": res["r2"], "sse": sse, "s": res["s"], "dof": res["dof"], "t95": res["t"], "n": res["n"],
            "converged": res.get("converged", True), "notes": list(res.get("notes") or []),
            "u_method": res.get("u_method")}


def predict(model: str, fit: dict, x):
    x = np.asarray(x, dtype=float)
    if model == "line":
        return fit["a"] + fit["b"] * x
    with np.errstate(all="ignore"):
        return fit["a"] * np.exp(fit["b"] * x)


def fit_peaks(x, y, unit: str, xunit: str, exclude=None) -> dict:
    """Gerade und Exponentialfunktion durch die Spitzen (x_i, y_i); die bessere (kleinere Summe der Fehlerquadrate in y,
    gleichbedeutend mit grösserem R², beide Modelle haben 2 Parameter und dieselben y) ist "best". Bei Gleichstand gilt
    die Gerade. Weniger als 3 Spitzen: kein Ausgleich, "reason" sagt warum."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    excl = sorted({int(e) for e in (exclude or []) if 1 <= int(e) <= len(x)})
    keep = np.array([i + 1 not in excl for i in range(len(x))], dtype=bool)
    out = {"n": int(keep.sum()), "n_peaks": int(len(x)), "excluded": excl, "x_unit": xunit, "y_unit": unit,
           "line": None, "exp": None, "best": None, "reason": None}
    if keep.sum() < MIN_FIT:
        out["reason"] = (f"weniger als {MIN_FIT} Lastspitzen im Ausgleich (n = {int(keep.sum())}): mit 2 Parametern "
                         "bliebe kein Freiheitsgrad für Streuung und Unsicherheit")
        return out
    F = _fitting()
    if F is None:
        out["reason"] = "labcalc (SDK) nicht gefunden: kein Ausgleich"
        return out
    xs, ys = x[keep], y[keep]
    out["line"] = _model(F, xs, ys, "line", xunit, unit)
    out["exp"] = _model(F, xs, ys, "exp", xunit, unit)
    ok = [m for m in ("line", "exp") if out[m]["ok"] and math.isfinite(out[m]["sse"])]
    if ok:
        out["best"] = min(ok, key=lambda m: (out[m]["sse"], 0 if m == "line" else 1))
        if len(ok) == 2 and abs(out["line"]["sse"] - out["exp"]["sse"]) <= 1e-12 * max(1.0, out["line"]["sse"]):
            out["best"] = "line"
    xl = np.linspace(float(xs.min()), float(xs.max()), FIT_POINTS)
    out["curve"] = {"x": xl.tolist(),
                    **{m: predict(m, out[m], xl).tolist() for m in ("line", "exp") if out[m]["ok"]}}
    return out


def evaluate(t, y, force, *, ymax: float, resolution: float, frac: float = DEFAULT_DROP_FRAC, t0: float = 0.0,
             v_mm_s: float | None = None, l0: float | None = None, a0: float | None = None, path_mm=None,
             work_basis: str | None = None, dt: float | None = None, exclude=None, unit: str = "N") -> dict:
    """Lastspitzen einer Kurve.

    t, y, force: aktiver Abschnitt (Zeit in s, Auswertegrösse σ oder |F|, Kraft |F| in N). resolution in Einheiten
    von y. path_mm: Verlängerung in mm für die Arbeit (gemessen oder Traversenweg) oder None; work_basis beschreibt sie.
    dt: Abtastintervall in s (Unsicherheit der Zeiten). exclude: Nummern (ab 1) der Spitzen, die nicht in den
    Ausgleich gehen."""
    t = np.asarray(t, dtype=float)
    y = np.asarray(y, dtype=float)
    force = np.asarray(force, dtype=float)
    frac = float(frac) if frac is not None and frac > 0 else DEFAULT_DROP_FRAC
    delta, basis = threshold(ymax, resolution, frac)
    kind, fac = x_axis(v_mm_s, l0)
    origin = 0.0 if kind == "time" else float(t0)
    de, en, xunit = X_LABELS[kind]
    pairs = detect(y, delta)
    i_t0 = int(np.searchsorted(t, t0, side="left")) if len(t) else 0
    peaks = []
    w_cum = 0.0
    for k, (p, v) in enumerate(pairs):
        prev_v = pairs[k - 1][1] if k else None
        # Anstieg zur ersten Spitze ab dem Fusspunkt t0 (liegt er nicht vor der Spitze: ab dem ersten Punkt)
        s = prev_v if prev_v is not None else (i_t0 if 0 <= i_t0 < p else 0)
        k_n_s, k_pts = _stiffness(t, force, s, p)
        seg_from = prev_v if prev_v is not None else 0
        w = None
        if path_mm is not None:
            w = _trapz(force[seg_from:v + 1], path_mm[seg_from:v + 1]) / 1000.0
            w_cum += w
        fp, fv = float(force[p]), float(force[v])
        e = {
            "nr": k + 1, "idx": int(p), "t": float(t[p]), "x": float(fac * (t[p] - origin)), "y": float(y[p]), "F": fp,
            "valley_idx": int(v), "valley_t": float(t[v]), "valley_y": float(y[v]), "valley_F": fv,
            "drop_y": float(y[p] - y[v]), "drop_F": fp - fv, "drop_pct": (fp - fv) / fp * 100.0 if fp > 0 else None,
            "dauer": float(t[v] - t[p]), "dauer_u": dt,
            "ratio": (fp / peaks[-1]["F"]) if peaks and peaks[-1]["F"] > 0 else None,
            "rise_from_idx": int(s), "k_N_s": k_n_s, "k_points": k_pts,
            "k_N_mm": (k_n_s / v_mm_s) if (k_n_s is not None and v_mm_s) else None,
            "k_MPa_pct": (k_n_s / a0 / (v_mm_s / l0 * 100.0)) if (k_n_s is not None and v_mm_s and l0 and a0) else None,
            "W_J": w, "W_cum_J": w_cum if w is not None else None,
        }
        peaks.append(e)
    excl = sorted({int(e) for e in (exclude or []) if 1 <= int(e) <= len(peaks)})
    for e in peaks:
        e["excluded"] = e["nr"] in excl
    out = {
        "n": len(peaks), "progressive": len(peaks) >= 2, "frac": frac, "delta": delta,
        "delta_F": delta * a0 if a0 else delta, "delta_basis": basis, "ymax": float(ymax), "resolution": resolution,
        "unit": unit, "x_kind": kind, "x_unit": xunit, "x_label": de, "x_label_en": en, "x_factor": fac,
        "x_origin": origin, "t0": float(t0), "dt": dt, "work_basis": work_basis if path_mm is not None else None, "list": peaks,
        "fit": None,
    }
    if len(peaks) >= 2:
        out["fit"] = fit_peaks([e["x"] for e in peaks], [e["y"] for e in peaks], unit, xunit, excl)
        cv = out["fit"].get("curve")
        if cv:
            cv["t"] = [origin + xx / fac for xx in cv["x"]]   # Zeitachse der Ausgleichskurven für das Diagramm
    return out


def warning_text(pk: dict, a0: bool, fmt) -> str:
    """Hinweis 4.9 (Deutsch) bei mindestens 2 Spitzen."""
    u = pk["unit"]
    ref = "Rm" if a0 else "Fmax"
    nd = 2 if pk["delta"] < 1 else 1
    return (f"Fortschreitendes Versagen: {pk['n']} Lastspitzen, jede mit einem Lastabfall von mindestens "
            f"{fmt(pk['delta'], nd, u)} danach ({fmt(pk['frac'] * 100, 1)} % von {ref}"
            + (", hier begrenzt durch 3 × Anzeigeauflösung" if pk["delta_basis"] == "aufloesung" else "")
            + f"). {ref} ist die höchste Last (das globale Maximum); Haltezeit, Plateau, Abfall und Bruch beziehen "
            "sich auf dieses globale Maximum, nicht auf die einzelnen Spitzen. Die Spitzen, ihre Abfälle und der "
            "Ausgleich der Spitzenlasten stehen unter „Lastspitzen“.")
