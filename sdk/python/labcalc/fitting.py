"""G-02: Ausgleichsrechnung für Messreihen y(x), linearisiert oder direkt, mit Unsicherheiten und Einheiten.

Modelle:
  lin    y = m·x + b
  prop   y = m·x
  poly2  y = a·x² + b·x + c
  poly3  y = a·x³ + b·x² + c·x + d
  log    y = a + b·ln x
  exp    y = a·e^(b·x)            linearisiert: ln y = ln a + b·x
  pow    y = a·x^b                linearisiert: ln y = ln a + b·ln x
  arrh   k = A·e^(−Ea/(R·T))      linearisiert: ln k = ln A − (Ea/R)·(1/T)   (T in K; °C, °F werden umgerechnet)
  mm     v = Vmax·S/(Km + S)      linearisiert (Lineweaver–Burk): 1/v = 1/Vmax + (Km/Vmax)·(1/S)

Linearisiert: Ausgleichsgerade durch die umgerechneten Punkte (ungewichtet, wie im Praktikum); die Parameter werden
zurückgerechnet, ihre Unsicherheit mit der Kovarianz nach Gauss (erste Ordnung, symmetrisch). Lineweaver–Burk (mm)
ist bekannt verzerrt (die Kehrwerte geben kleinen S und v grosses Gewicht); es bleibt als Option, die direkte
Anpassung wird empfohlen. Direkt: kleinste Quadrate in y (Levenberg–Marquardt mit numerischer Ableitung, Start bei
den linearisierten Werten) an allen Punkten, an denen das Modell selbst definiert ist (auch y ≤ 0), Unsicherheit aus
s²·(JᵀJ)⁻¹ am Optimum, mit Konvergenzprüfung. Vertrauensbereich 95 % mit dem Student-t-Quantil (n − p
Freiheitsgrade). Für lin, prop, poly und log sind beide Wege gleich (das Modell ist in den Parametern schon linear).
R² = 1 − SSE/SST; SST um den Mittelwert, beim Modell ohne Achsenabschnitt (prop) unzentriert, SST = Σy².

Werte kommen in den Einheiten der Spalten (nicht SI); die Einheiten der Parameter werden daraus gebildet.
"""
from __future__ import annotations

import math
import re

import numpy as np

from . import stats
from . import units as U

R_GAS = U.R_GAS                        # J/(mol·K), exakt R = N_A·k (SI 2019), volle Doppelgenauigkeit
GTOL = 1e-4                            # Konvergenz: max. Kosinus zwischen Residuum und Spalten der Jacobi-Matrix

# key: (de, en, Formel, Parameter, linearisierbar)
MODELS = {
    "lin": ("Gerade", "Straight line", "y = m·x + b", ["m", "b"], False),
    "prop": ("Ursprungsgerade", "Through origin", "y = m·x", ["m"], False),
    "poly2": ("Parabel", "Quadratic", "y = a·x² + b·x + c", ["a", "b", "c"], False),
    "poly3": ("Polynom 3. Grades", "Cubic", "y = a·x³ + b·x² + c·x + d", ["a", "b", "c", "d"], False),
    "log": ("Logarithmus", "Logarithmic", "y = a + b·ln x", ["a", "b"], False),
    "exp": ("Exponentialfunktion", "Exponential", "y = a·e^(b·x)", ["a", "b"], True),
    "pow": ("Potenzfunktion", "Power law", "y = a·x^b", ["a", "b"], True),
    "arrh": ("Arrhenius", "Arrhenius", "k = A·e^(−Ea/(R·T))", ["A", "Ea"], True),
    "mm": ("Michaelis–Menten", "Michaelis–Menten", "v = Vmax·S/(Km + S)", ["Vmax", "Km"], True),
}
# Achsen der linearisierten Darstellung: (x, y) als Text
LIN_AXES = {
    "lin": ("x", "y"), "prop": ("x", "y"), "poly2": ("x", "y"), "poly3": ("x", "y"), "log": ("ln x", "y"),
    "exp": ("x", "ln y"), "pow": ("ln x", "ln y"), "arrh": ("1/T", "ln k"), "mm": ("1/S", "1/v"),
}


class FitError(ValueError):
    pass


# ----------------------------------------------------------------------------- Einheiten
def _wrap(u: str) -> str:
    return u if re.fullmatch(r"[^/*·\s()^]+(\^-?\d+)?", u) else f"({u})"


def _div(a: str, b: str) -> str:
    if not b or b == "1":
        return a
    if not a or a == "1":
        return "1/" + _wrap(b)
    if a == b:
        return ""
    return f"{_wrap(a)}/{_wrap(b)}"


def _pow(u: str, k: int) -> str:
    return "" if not u else (u if k == 1 else f"{_wrap(u)}^{k}")


def param_units(model: str, ux: str, uy: str) -> list[str]:
    ux, uy = (ux or "").strip(), (uy or "").strip()
    return {
        "lin": lambda: [_div(uy, ux), uy],
        "prop": lambda: [_div(uy, ux)],
        "poly2": lambda: [_div(uy, _pow(ux, 2)), _div(uy, ux), uy],
        "poly3": lambda: [_div(uy, _pow(ux, 3)), _div(uy, _pow(ux, 2)), _div(uy, ux), uy],
        "log": lambda: [uy, uy],
        "exp": lambda: [uy, _div("", ux) if ux else ""],
        "pow": lambda: ["", ""],
        "arrh": lambda: [uy, "kJ/mol"],
        "mm": lambda: [uy, ux],
    }[model]()


def _temperature_K(x: np.ndarray, ux: str):
    """x als absolute Temperatur in K; (Werte, Hinweis)."""
    u = (ux or "").strip()
    if not u:
        return x, "x ohne Einheit: als T in K gelesen"
    try:
        f, d, off = U.parse_unit(u)
    except Exception as e:  # noqa: BLE001 - jede Einheitenfehlermeldung reicht hier
        raise FitError(f"Einheit {u} unbekannt") from e
    if not U.deq(d, U.parse_unit("K")[1]):
        raise FitError(f"Arrhenius braucht die Temperatur als x (K oder °C), nicht {u}")
    return x * f + off, (f"T aus {u} in K umgerechnet" if u != "K" else "")


# ----------------------------------------------------------------------------- Modelle
def _design(model, x):
    """Lineare Modelle: Spalten der Planmatrix (Reihenfolge = Parameter)."""
    one = np.ones_like(x)
    return {
        "lin": lambda: [x, one], "prop": lambda: [x], "poly2": lambda: [x * x, x, one],
        "poly3": lambda: [x ** 3, x * x, x, one], "log": lambda: [one, np.log(x)],
    }[model]()


def predict(model: str, p, x, xunit: str = ""):
    """Modellwerte für x mit den berichteten Parametern p (Liste wie MODELS[model][3])."""
    x = np.asarray(x, dtype=float)
    with np.errstate(all="ignore"):
        if model in ("lin", "prop", "poly2", "poly3", "log"):
            if model == "log":
                x = np.where(x > 0, x, np.nan)
            return sum(c * col for c, col in zip(p, _design(model, x)))
        if model == "exp":
            return p[0] * np.exp(p[1] * x)
        if model == "pow":
            return p[0] * np.where(x > 0, x, np.nan) ** p[1]
        if model == "arrh":
            T, _ = _temperature_K(x, xunit)
            return p[0] * np.exp(-p[1] * 1000.0 / (R_GAS * np.where(T > 0, T, np.nan)))
        if model == "mm":
            return p[0] * x / (p[1] + x)
    raise FitError("Unbekanntes Modell")


def _linear_ls(cols, y):
    A = np.column_stack(cols)
    q, *_ = np.linalg.lstsq(A, y, rcond=None)
    res = y - A @ q
    n, k = A.shape
    sse = float(res @ res)
    dof = n - k
    s2 = sse / dof if dof > 0 else 0.0
    cov = s2 * np.linalg.pinv(A.T @ A) if dof > 0 else None
    return q, cov, sse, dof


def _r2(y, yh, centred=True):
    """Bestimmtheitsmass 1 − SSE/SST. centred=False (Modell ohne Achsenabschnitt): SST = Σy² statt Σ(y − ȳ)²."""
    sst = float(np.sum((y - y.mean()) ** 2)) if centred else float(np.sum(y ** 2))
    sse = float(np.sum((y - yh) ** 2))
    return 1 - sse / sst if sst > 0 else 1.0


def converged(J, r, y) -> bool:
    """Optimum erreicht? Residuum (fast) null oder senkrecht zu allen Spalten von J (Kosinus ≤ GTOL, wie das
    Gradientenkriterium von MINPACK)."""
    rr = float(r @ r)
    if rr <= 1e-24 * max(float(y @ y), 1e-300):
        return True
    if not np.all(np.isfinite(J)):
        return False
    nr = math.sqrt(rr)
    cols = np.sqrt(np.sum(J * J, axis=0))
    g = np.abs(J.T @ r)
    with np.errstate(all="ignore"):
        cos = np.where(cols > 0, g / (cols * nr), 0.0)
    return bool(np.all(cos <= GTOL))


# Linearisierte Form der nichtlinearen Modelle: Punkte (X, Y) und Rückrechnung der Geradenparameter (c, s)
def _lin_points(model, x, y, xunit):
    note = ""
    with np.errstate(all="ignore"):
        if model == "exp":
            ok = y > 0
            return x[ok], np.log(y[ok]), ok, "" if ok.all() else "Punkte mit y ≤ 0 weggelassen"
        if model == "pow":
            ok = (x > 0) & (y > 0)
            return np.log(x[ok]), np.log(y[ok]), ok, "" if ok.all() else "Punkte mit x ≤ 0 oder y ≤ 0 weggelassen"
        if model == "arrh":
            T, note = _temperature_K(x, xunit)
            ok = (T > 0) & (y > 0)
            msg = "; ".join(m for m in (note, "" if ok.all() else "Punkte mit k ≤ 0 weggelassen") if m)
            return 1.0 / T[ok], np.log(y[ok]), ok, msg
        if model == "mm":
            ok = (x > 0) & (y > 0)
            return 1.0 / x[ok], 1.0 / y[ok], ok, "" if ok.all() else "Punkte mit S ≤ 0 oder v ≤ 0 weggelassen"
        if model == "log":
            ok = x > 0
            return np.log(x[ok]), y[ok], ok, "" if ok.all() else "Punkte mit x ≤ 0 weggelassen"
    ok = np.ones_like(x, dtype=bool)
    return x, y, ok, note


def _from_line(model, c, s):
    """Gerade Y = c + s·X -> berichtete Parameter und Ableitungsmatrix d(p)/d(c, s)."""
    if model in ("exp", "pow"):
        a = math.exp(c)
        return [a, s], np.array([[a, 0.0], [0.0, 1.0]])
    if model == "arrh":
        A = math.exp(c)
        return [A, -s * R_GAS / 1000.0], np.array([[A, 0.0], [0.0, -R_GAS / 1000.0]])
    if model == "mm":
        if c == 0:
            raise FitError("Achsenabschnitt 1/Vmax ist null – Vmax nicht bestimmbar")
        return [1.0 / c, s / c], np.array([[-1.0 / c ** 2, 0.0], [-s / c ** 2, 1.0 / c]])
    raise FitError("Unbekanntes Modell")


def _lm(f, q0, x, y, iters=200):
    """Levenberg–Marquardt für y ≈ f(x, q); gibt (q, Kovarianz, SSE, Freiheitsgrade, konvergiert?)."""
    q = np.asarray(q0, dtype=float)
    n, k = len(y), len(q)

    def sse(qq):
        with np.errstate(all="ignore"):
            r = f(x, qq) - y
        return float(r @ r) if np.all(np.isfinite(r)) else math.inf

    def jac(qq):
        J = np.empty((n, k))
        f0 = f(x, qq)
        for i in range(k):
            h = 1e-7 * max(1.0, abs(qq[i]))
            d = qq.copy()
            d[i] += h
            J[:, i] = (f(x, d) - f0) / h
        return J, f0

    s, lam = sse(q), 1e-3
    if not math.isfinite(s):
        raise FitError("Startwerte unbrauchbar – erst linearisiert anpassen")
    for _ in range(iters):
        with np.errstate(all="ignore"):
            J, f0 = jac(q)
        if not np.all(np.isfinite(J)):
            break
        r = f0 - y
        A, g = J.T @ J, J.T @ r
        better = False
        for _ in range(16):
            try:
                dq = np.linalg.solve(A + lam * np.diag(np.diag(A) + 1e-300), -g)
            except np.linalg.LinAlgError:
                lam *= 10
                continue
            s2 = sse(q + dq)
            if s2 < s:
                done = s - s2 <= 1e-15 * max(1.0, s)
                q, s, lam, better = q + dq, s2, max(lam / 10, 1e-15), True
                break
            lam *= 10
        if not better or done:
            break
    with np.errstate(all="ignore"):
        J, f0 = jac(q)
    dof = n - k
    cov = (s / dof) * np.linalg.pinv(J.T @ J) if dof > 0 and np.all(np.isfinite(J)) else None
    return q, cov, s, dof, converged(J, f0 - y, y)


def _direct_fn(model, xunit):
    """Modell in inneren Parametern q für die direkte Anpassung (gut skaliert) und Rückrechnung q -> p."""
    if model == "exp":
        return (lambda x, q: np.exp(q[0] + q[1] * x)), (lambda q: ([math.exp(q[0]), q[1]], np.diag([math.exp(q[0]), 1.0])))
    if model == "pow":
        return (lambda x, q: np.exp(q[0] + q[1] * np.log(x))), (lambda q: ([math.exp(q[0]), q[1]], np.diag([math.exp(q[0]), 1.0])))
    if model == "arrh":
        def f(x, q):
            T, _ = _temperature_K(x, xunit)
            return np.exp(q[0] + q[1] / T)
        return f, (lambda q: ([math.exp(q[0]), -q[1] * R_GAS / 1000.0], np.diag([math.exp(q[0]), -R_GAS / 1000.0])))
    if model == "mm":
        return (lambda x, q: q[0] * x / (q[1] + x)), (lambda q: ([q[0], q[1]], np.eye(2)))
    raise FitError("Unbekanntes Modell")


def _direct_points(model, x, xunit):
    """Punkte, an denen das Modell selbst (nicht seine Linearisierung) definiert ist: exp, mm alle; pow x > 0;
    arrh T > 0 (in K)."""
    if model == "pow":
        return x > 0
    if model == "arrh":
        T, _ = _temperature_K(x, xunit)
        return T > 0
    return np.ones_like(x, dtype=bool)


def _direct_note(model, x, dm, xunit):
    msgs = []
    if model == "arrh":
        msgs.append(_temperature_K(x, xunit)[1])
        if not dm.all():
            msgs.append("Punkte mit T ≤ 0 K weggelassen")
    elif model == "pow" and not dm.all():
        msgs.append("Punkte mit x ≤ 0 weggelassen")
    return "; ".join(m for m in msgs if m)


def _thin(a, b, n=500):
    if len(a) <= n:
        return a, b
    k = math.ceil(len(a) / n)
    return a[::k], b[::k]


def _num(v):
    v = float(v)
    return v if math.isfinite(v) else None


def fit(x, y, model: str, mode: str = "lin", xunit: str = "", yunit: str = "", lang: str = "de") -> dict:
    """Anpassung an die endlichen Wertepaare. mode: "lin" (linearisiert) oder "direct"."""
    if model not in MODELS:
        raise FitError("Unbekanntes Modell")
    de, en, formula, pnames, has_lin = MODELS[model]
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    k = len(pnames)
    if len(x) < k:
        raise FitError(f"{de}: mindestens {k} Wertepaare nötig ({len(x)} vorhanden)")
    notes = []
    mode = "direct" if (mode == "direct" and has_lin) else "lin"
    X, Y, keep, note = _lin_points(model, x, y, xunit)
    if note and mode != "direct":
        notes.append(note)
    if len(X) < k:
        raise FitError(f"{de}: zu wenige brauchbare Wertepaare ({len(X)})")
    r2_lin = None
    conv = None
    u_method = "linear"                  # Kovarianz s²·(AᵀA)⁻¹ eines in den Parametern linearen Modells
    if not has_lin:
        cols = _design(model, x) if model != "log" else _design(model, x[keep])
        yy = y if model != "log" else y[keep]
        q, cov, sse, dof = _linear_ls(cols, yy)
        p, cov_p = [float(v) for v in q], cov
        xs_used, ys_used = (x, y) if model != "log" else (x[keep], y[keep])
    else:
        (c, s), cov_l, _sse, dof = _linear_ls([np.ones_like(X), X], Y)
        r2_lin = _r2(Y, c + s * X)
        p, G = _from_line(model, float(c), float(s))
        cov_p = G @ cov_l @ G.T if cov_l is not None else None
        xs_used, ys_used = x[keep], y[keep]
        u_method = "first_order_back_transform"
        if mode == "direct":
            dm = _direct_points(model, x, xunit)
            xs_used, ys_used = x[dm], y[dm]
            dn = _direct_note(model, x, dm, xunit)
            if dn:
                notes.append(dn)
            if len(xs_used) < k:
                raise FitError(f"{de}: zu wenige brauchbare Wertepaare ({len(xs_used)})")
            if int(dm.sum()) > int(keep.sum()):
                notes.append(f"Startwerte aus den {int(keep.sum())} linearisierbaren Punkten; angepasst an alle "
                             f"{int(dm.sum())} Punkte")
            f, back = _direct_fn(model, xunit)
            q0 = [float(c), float(s)] if model != "mm" else p
            q, cov_q, _sse, dof, conv = _lm(f, q0, xs_used, ys_used)
            p, G = back(q)
            cov_p = G @ cov_q @ G.T if cov_q is not None else None
            u_method = "jacobian" if model == "mm" else "jacobian_first_order"
            if not conv:
                notes.append("Levenberg–Marquardt nicht konvergiert (kein Optimum nach dem Gradientenkriterium) – "
                             "Ergebnis und Unsicherheiten unzuverlässig; Daten, Bereich oder Modell prüfen")
        elif model == "mm":
            notes.append("Lineweaver–Burk (doppelt reziproke Gerade): bekannt verzerrt, da kleine S und v durch die "
                         "Kehrwerte grosses Gewicht erhalten – für Ergebnisse die direkte Anpassung verwenden")
        if mode != "direct":
            which = {"exp": "a", "pow": "a", "arrh": "A", "mm": "Vmax und Km"}[model]
            notes.append(f"Unsicherheit von {which} aus der Geraden zurückgerechnet (erste Ordnung, symmetrisch)")
    with np.errstate(all="ignore"):
        yh = predict(model, p, xs_used, xunit)
    resid = ys_used - yh
    n = len(ys_used)
    dof = n - k
    if dof <= 0:
        notes.append("so viele Parameter wie Wertepaare – keine Unsicherheit")
    t = stats.t_ppf(0.975, dof) if dof > 0 else None
    units = param_units(model, xunit, yunit)
    params = []
    for i, (sym, val) in enumerate(zip(pnames, p)):
        u = math.sqrt(cov_p[i, i]) if cov_p is not None and cov_p[i, i] >= 0 else None
        params.append({"sym": sym, "value": _num(val), "u": _num(u) if u is not None else None,
                       "ci": _num(t * u) if (t is not None and u is not None) else None, "unit": units[i]})
    if model == "pow" and (xunit or yunit):
        notes.append(f"a gilt für x in {xunit or '1'} und y in {yunit or '1'}")
    if model == "log":
        notes.append(f"a = y bei x = 1 {xunit}: a hängt von der Einheit von x ab (x in {xunit})" if xunit else
                     "a = y bei x = 1: a hängt von der Einheit von x ab")
    if model == "prop":
        notes.append("R² ohne Achsenabschnitt: SST = Σy² (unzentriert)")
    s_res = math.sqrt(float(resid @ resid) / dof) if dof > 0 else None
    out = {
        "model": model, "mode": mode, "name": en if lang == "en" else de, "formula": formula, "n": n, "dof": dof,
        "params": params, "r2": _num(_r2(ys_used, yh, centred=model != "prop")),
        "r2_centred": model != "prop", "s": _num(s_res) if s_res is not None else None, "t": t,
        "notes": notes, "xunit": xunit, "yunit": yunit, "u_method": u_method,
    }
    if model == "mm" and mode != "direct":
        out["method"] = "Lineweaver–Burk"
    if conv is not None:
        out["converged"] = bool(conv)
    if model == "log":
        out["a_xunit"] = xunit or ""
    if r2_lin is not None:
        out["r2_lin"] = _num(r2_lin)
    out["plots"] = _plots(model, mode, p, x, y, X, Y, keep, xs_used, resid, xunit, yunit, lang)
    return out


def _plots(model, mode, p, x, y, X, Y, keep, xs_used, resid, xunit, yunit, lang):
    """Zwei kleine Grafiken (LabBoard-Format): linearisierte Darstellung mit Gerade, Residuen über x."""
    en = lang == "en"
    ax, ay = LIN_AXES[model]
    ux = (f" [{xunit}]" if xunit else "")
    uy = (f" [{yunit}]" if yunit else "")
    if model in ("lin", "prop", "poly2", "poly3"):
        lx, ly = "x" + ux, "y" + uy
        X1, Y1 = x, y
        xl = np.linspace(float(np.min(x)), float(np.max(x)), 60)
        yl = predict(model, p, xl, xunit)
    else:
        lx = {"ln x": "ln x", "x": "x" + ux, "1/T": "1/T [1/K]", "1/S": "1/S" + (f" [1/{xunit}]" if xunit else "")}[ax]
        ly = {"ln y": "ln y", "y": "y" + uy, "ln k": "ln k", "1/v": "1/v" + (f" [1/{yunit}]" if yunit else "")}[ay]
        X1, Y1 = X, Y
        if model == "log":
            xl = np.linspace(float(np.min(X)), float(np.max(X)), 2)
            yl = p[0] + p[1] * xl
        else:                                  # die (bei „direkt“ zurückgerechnete) Gerade in linearen Koordinaten
            c, s = {"exp": lambda: (math.log(p[0]) if p[0] > 0 else math.nan, p[1]),
                    "pow": lambda: (math.log(p[0]) if p[0] > 0 else math.nan, p[1]),
                    "arrh": lambda: (math.log(p[0]) if p[0] > 0 else math.nan, -p[1] * 1000.0 / R_GAS),
                    "mm": lambda: (1.0 / p[0] if p[0] else math.nan, p[1] / p[0] if p[0] else math.nan)}[model]()
            xl = np.linspace(float(np.min(X)), float(np.max(X)), 2)
            yl = c + s * xl
    tx, ty = _thin(np.asarray(X1, float), np.asarray(Y1, float))
    rx, ry = _thin(np.asarray(xs_used, float), np.asarray(resid, float))
    meas, line = ("Measured", "Fit") if en else ("Messwerte", "Ausgleich")
    if model in ("lin", "prop", "poly2", "poly3"):
        lin_t = "Data and fit" if en else "Messwerte und Ausgleich"
    else:
        lin_t = f"Linearised: {ay} over {ax}" if en else f"Linearisiert: {ay} über {ax}"
        if model == "mm":
            lin_t += " (Lineweaver–Burk)"
    return [
        {"title": lin_t, "xlab": lx, "ylab": ly,
         "series": [{"name": meas, "x": [_num(v) for v in tx], "y": [_num(v) for v in ty], "pts": True},
                    {"name": line, "x": [_num(v) for v in xl], "y": [_num(v) for v in yl]}]},
        {"title": "Residuals y − ŷ" if en else "Residuen y − ŷ", "xlab": "x" + ux, "ylab": ("y − ŷ") + uy,
         "series": [{"name": "Residuals" if en else "Residuen", "x": [_num(v) for v in rx], "y": [_num(v) for v in ry], "pts": True}]},
    ]
