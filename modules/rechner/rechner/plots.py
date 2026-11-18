"""Diagramme: Funktionen abtasten, Kurven untersuchen, Messdaten anpassen, Bild fuer den Bericht."""
from __future__ import annotations

import math

import numpy as np

from . import expr as E

FIT_MODELS = {
    "lin": ("Gerade", "Line"), "poly2": ("Polynom 2. Grades", "Quadratic"), "poly3": ("Polynom 3. Grades", "Cubic"),
    "exp": ("Exponentialfunktion", "Exponential"), "pow": ("Potenzfunktion", "Power law"),
    "log": ("Logarithmus", "Logarithmic"), "prop": ("Ursprungsgerade", "Proportional"),
}
COLORS = ["#00796b", "#c62828", "#1565c0", "#ef6c00", "#6a1b9a", "#2e7d32", "#ad1457", "#4e342e"]


# ----------------------------------------------------------------------------- Kontext
def make_ctx(req: dict) -> E.Ctx:
    """Rechenkontext aus einer Anfrage: Variablen und Funktionen der Konsole, Groessen des Arbeitsblatts."""
    names, dims = {}, {}
    from . import units as U
    for sym, q in (req.get("quantities") or {}).items():
        try:
            names[sym] = float(q["si"]) if isinstance(q, dict) else float(q)
            if isinstance(q, dict) and q.get("kind") in U.KINDS:
                dims[sym] = U.ensure_kind(q["kind"]).dims
        except (TypeError, ValueError, KeyError):
            pass
    for k, v in (req.get("vars") or {}).items():
        try:
            names[k] = E.from_json(v)
            dims.pop(k, None)
        except (TypeError, ValueError):
            pass
    for k, d in (req.get("vdims") or {}).items():          # Einheit von Zeilenvariablen (u = F/A → Pa)
        try:
            if k in names and d and len(d) == 7:
                dims[k] = tuple(float(x) for x in d)
        except (TypeError, ValueError):
            pass
    ctx = E.Ctx(names=names, angle=req.get("angle", "rad"), complex_ok=bool(req.get("complex")), dims=dims)
    # DP-11: Teile mit eigener Einheit (fit = linreg(eps, sigma) -> fit[1] in Pa, fit[2] in Pa)
    ctx.pdims = {}
    for k, ps in (req.get("vpdims") or {}).items():
        try:
            if k in names and isinstance(ps, list) and ps and all(len(d) == 7 for d in ps):
                ctx.pdims[k] = [tuple(float(x) for x in d) for d in ps]
        except (TypeError, ValueError):
            pass
    funcs = req.get("funcs") or {}
    callables = ctx.callables() | frozenset(funcs)
    for k, f in funcs.items():
        try:
            ctx.funcs[k] = (list(f["args"]), E.parse(f["body"], callables))
        except (E.CalcError, KeyError, TypeError):
            pass
    return ctx


def fn_of(spec_expr: str, var: str, ctx: E.Ctx):
    node = E.parse(spec_expr, ctx.callables())

    def f(x):
        with np.errstate(all="ignore"):
            return E.evaluate(node, ctx, {var: x})
    return f


def eval_vec(f, X):
    try:
        Y = np.asarray(f(X))
        if np.iscomplexobj(Y):
            Y = np.where(np.abs(Y.imag) < 1e-12 * np.maximum(1, np.abs(Y.real)), Y.real, np.nan)
        Y = np.asarray(Y, dtype=float)
        if Y.shape == X.shape:
            return Y
        if Y.ndim == 0:
            return np.full(X.shape, float(Y))
    except (E.CalcError, TypeError, ValueError, ZeroDivisionError, OverflowError):
        pass
    out = np.empty(X.shape)
    for i, x in enumerate(X):
        try:
            y = complex(np.asarray(f(float(x))))
            out[i] = y.real if abs(y.imag) < 1e-12 * max(1, abs(y.real)) else np.nan
        except (E.CalcError, TypeError, ValueError, ZeroDivisionError, OverflowError):
            out[i] = np.nan
    return out


def _breaks(X, Y, yspan):
    """Spruenge an Polstellen auftrennen (None in der Liste = Linie absetzen)."""
    Y = Y.copy()
    if yspan and len(Y) > 2:
        d = np.abs(np.diff(Y))
        jump = (d > 2.5 * yspan) & (np.sign(Y[:-1]) != np.sign(Y[1:]))
        Y[1:][jump] = np.nan
    return [E._jnum(x) for x in X], [E._jnum(y) for y in Y]


# ----------------------------------------------------------------------------- Abtasten
def sample(spec: dict, ctx: E.Ctx, view: dict, n=900) -> dict:
    kind = spec.get("kind", "fx")
    x0, x1 = float(view.get("xmin", -10)), float(view.get("xmax", 10))
    yspan = abs(float(view.get("ymax", 10)) - float(view.get("ymin", -10)))
    if kind == "fx":
        f = fn_of(spec["expr"], "x", ctx)
        X = np.linspace(x0, x1, n)
        Y = eval_vec(f, X)
        xs, ys = _breaks(X, Y, yspan)
        return {"x": xs, "y": ys}
    if kind in ("param", "polar"):
        t0 = float(_num(spec.get("tmin", 0), ctx))
        t1 = float(_num(spec.get("tmax", 2 * math.pi), ctx))
        T = np.linspace(t0, t1, max(n, 1200))
        if kind == "param":
            X = eval_vec(fn_of(spec["x"], "t", ctx), T)
            Y = eval_vec(fn_of(spec["y"], "t", ctx), T)
        else:
            Rr = eval_vec(fn_of(spec["r"], "theta", ctx), T)
            th = T * ctx.aconv
            X, Y = Rr * np.cos(th), Rr * np.sin(th)
        return {"x": [E._jnum(v) for v in X], "y": [E._jnum(v) for v in Y]}
    if kind == "data":
        d = spec.get("data") or {}
        xs = [_f(v) for v in d.get("x", [])]
        ys = [_f(v) for v in d.get("y", [])]
        out = {"x": xs, "y": ys, "points": True}
        if spec.get("fit") and spec["fit"] != "none":
            try:
                fr = fit(xs, ys, spec["fit"])
                X = np.linspace(x0, x1, n)
                Y = eval_vec(fn_of(fr["expr"], "x", ctx), X)
                out["fit"] = fr
                out["fx"], out["fy"] = _breaks(X, Y, yspan)
            except E.CalcError as e:
                out["fit_error"] = str(e)
        return out
    raise E.CalcError(f"Unbekannte Kurvenart {kind}")


def _f(v):
    try:
        f = float(str(v).replace(",", "."))
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _num(v, ctx):
    if isinstance(v, (int, float)):
        return float(v)
    return float(np.real(E.evaluate(E.parse(str(v), ctx.callables()), ctx)))


# ----------------------------------------------------------------------------- Untersuchen
def _scan(f, a, b, n=4000):
    X = np.linspace(a, b, n)
    return X, eval_vec(f, X)


def roots_in(f, a, b):
    X, Y = _scan(f, a, b)
    out = []
    for i in range(len(X) - 1):
        ya, yb = Y[i], Y[i + 1]
        if not (np.isfinite(ya) and np.isfinite(yb)):
            continue
        if ya == 0:
            out.append(X[i])
        elif ya * yb < 0:
            r = E.bisect(lambda t: float(eval_vec(f, np.array([t]))[0]), X[i], X[i + 1], ya, yb)
            fr = abs(float(eval_vec(f, np.array([r]))[0]))
            local = max(abs(ya), abs(yb))
            if fr <= 1e-6 * max(1.0, local) or fr < local * 1e-3:
                out.append(r)
    res = []
    for r in out:
        if not res or abs(r - res[-1]) > 1e-9 * max(1, abs(r)):
            res.append(float(r))
    return res


def extrema_in(f, a, b):
    X, Y = _scan(f, a, b)
    out = []
    for i in range(1, len(X) - 1):
        y0, y1, y2 = Y[i - 1], Y[i], Y[i + 1]
        if not (np.isfinite(y0) and np.isfinite(y1) and np.isfinite(y2)):
            continue
        if (y1 > y0 and y1 >= y2) or (y1 < y0 and y1 <= y2):
            kind = "max" if y1 > y0 else "min"
            lo, hi = X[i - 1], X[i + 1]
            g = (lambda t: -float(eval_vec(f, np.array([t]))[0])) if kind == "max" else (lambda t: float(eval_vec(f, np.array([t]))[0]))
            gr = (math.sqrt(5) - 1) / 2
            c, d = hi - gr * (hi - lo), lo + gr * (hi - lo)
            for _ in range(80):
                if g(c) < g(d):
                    hi = d
                else:
                    lo = c
                c, d = hi - gr * (hi - lo), lo + gr * (hi - lo)
            xm = (lo + hi) / 2
            out.append({"x": float(xm), "y": float(eval_vec(f, np.array([xm]))[0]), "type": kind})
    return out


def analyze(req: dict, ctx: E.Ctx) -> dict:
    what = req.get("what")
    spec = req.get("fn") or {}
    if spec.get("kind", "fx") != "fx":
        raise E.CalcError("Untersuchen geht nur mit Funktionen y = f(x)")
    f = fn_of(spec["expr"], "x", ctx)
    a, b = float(req.get("a", -10)), float(req.get("b", 10))
    if a > b:
        a, b = b, a
    if what == "roots":
        return {"points": [{"x": r, "y": 0.0} for r in roots_in(f, a, b)]}
    if what == "extrema":
        return {"points": extrema_in(f, a, b)}
    if what == "intersect":
        s2 = req.get("fn2") or {}
        if s2.get("kind", "fx") != "fx":
            raise E.CalcError("Schnittpunkte nur zwischen zwei Funktionen y = f(x)")
        g = fn_of(s2["expr"], "x", ctx)
        h = lambda x: np.asarray(f(x), dtype=float) - np.asarray(g(x), dtype=float)   # noqa: E731
        return {"points": [{"x": r, "y": float(eval_vec(f, np.array([r]))[0])} for r in roots_in(h, a, b)]}
    if what == "integral":
        v = E.quad(lambda x: eval_vec(f, np.atleast_1d(np.asarray(x, dtype=float))).reshape(np.shape(x)), a, b)
        return {"value": v, "a": a, "b": b}
    if what == "value":
        x = float(req.get("x", 0))
        y = float(eval_vec(f, np.array([x]))[0])
        d = float(E.deriv_at(lambda t: eval_vec(f, np.atleast_1d(np.asarray(t, dtype=float)))[0], x))
        return {"x": x, "y": y, "dy": d}
    raise E.CalcError("Unbekannte Untersuchung")


# ----------------------------------------------------------------------------- Anpassen
def fit(xs, ys, model: str) -> dict:
    pts = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pts) < 2:
        raise E.CalcError("Mindestens zwei Wertepaare nötig")
    x = np.array([p[0] for p in pts], dtype=float)
    y = np.array([p[1] for p in pts], dtype=float)
    if model == "lin":
        k, d = np.polyfit(x, y, 1)
        yh, params = k * x + d, {"k": k, "d": d}
        ex, tex = f"{_g(k)}*x + ({_g(d)})", f"y = {_t(k)}\\,x {_sgn(d)}"
    elif model == "prop":
        k = float(np.sum(x * y) / np.sum(x * x))
        yh, params = k * x, {"k": k}
        ex, tex = f"{_g(k)}*x", f"y = {_t(k)}\\,x"
    elif model in ("poly2", "poly3"):
        n = 2 if model == "poly2" else 3
        if len(pts) <= n:
            raise E.CalcError(f"Für Grad {n} mindestens {n + 1} Wertepaare")
        p = np.polyfit(x, y, n)
        yh = np.polyval(p, x)
        params = {f"a{n - i}": c for i, c in enumerate(p)}
        ex = " + ".join(f"({_g(c)})*x^{n - i}" if n - i > 1 else (f"({_g(c)})*x" if n - i == 1 else f"({_g(c)})") for i, c in enumerate(p))
        tex = "y = " + " ".join((_t(c) if i == 0 else _sgn(c)) + (f"\\,x^{{{n - i}}}" if n - i > 1 else ("\\,x" if n - i == 1 else ""))
                                for i, c in enumerate(p))
    elif model == "exp":
        if np.any(y <= 0):
            raise E.CalcError("Exponentialanpassung braucht y > 0")
        b, lna = np.polyfit(x, np.log(y), 1)
        a = math.exp(lna)
        yh, params = a * np.exp(b * x), {"a": a, "b": b}
        ex, tex = f"{_g(a)}*exp({_g(b)}*x)", f"y = {_t(a)}\\,\\mathrm{{e}}^{{{_t(b)}\\,x}}"
    elif model == "pow":
        if np.any(y <= 0) or np.any(x <= 0):
            raise E.CalcError("Potenzanpassung braucht x > 0 und y > 0")
        b, lna = np.polyfit(np.log(x), np.log(y), 1)
        a = math.exp(lna)
        yh, params = a * x ** b, {"a": a, "b": b}
        ex, tex = f"{_g(a)}*x^({_g(b)})", f"y = {_t(a)}\\,x^{{{_t(b)}}}"
    elif model == "log":
        if np.any(x <= 0):
            raise E.CalcError("Logarithmische Anpassung braucht x > 0")
        b, a = np.polyfit(np.log(x), y, 1)
        yh, params = a + b * np.log(x), {"a": a, "b": b}
        ex, tex = f"({_g(a)}) + ({_g(b)})*ln(x)", f"y = {_t(a)} {_sgn(b)}\\,\\ln x"
    else:
        raise E.CalcError("Unbekanntes Modell")
    ss = float(np.sum((y - y.mean()) ** 2))
    r2 = 1 - float(np.sum((y - yh) ** 2)) / ss if ss > 0 else 1.0
    return {"model": model, "name": FIT_MODELS[model][0], "params": {k: float(v) for k, v in params.items()},
            "r2": r2, "expr": ex, "tex": tex, "n": len(pts)}


def _g(v):
    return f"{float(v):.10g}"


def _t(v):
    from . import render as R
    return R.num_tex(float(v), "de", 5)


def _sgn(v):
    from . import render as R
    v = float(v)
    return ("+ " if v >= 0 else "- ") + R.num_tex(abs(v), "de", 5)


# ----------------------------------------------------------------------------- Bild fuer den Bericht
def figure(plot: dict, ctx: E.Ctx, lang="de", curves=None):
    """Matplotlib-Bild eines Diagramms (gleiche Angaben wie in der Oberflaeche)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    view = plot.get("view") or {}
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    x0, x1 = float(view.get("xmin", -10)), float(view.get("xmax", 10))
    y0, y1 = float(view.get("ymin", -10)), float(view.get("ymax", 10))
    dec = "," if lang == "de" else "."
    for i, spec in enumerate(plot.get("functions", [])):
        if spec.get("visible") is False or spec.get("kind") == "curve":     # Formelkurven kommen über curves
            continue
        col = spec.get("color") or COLORS[i % len(COLORS)]
        label = spec.get("label") or _label(spec)
        try:
            s = sample(spec, ctx, view, 1200)
        except E.CalcError:
            continue
        if s.get("points"):
            ax.plot([v for v in s["x"]], [v for v in s["y"]], "o", ms=4, color=col, label=label)
            if s.get("fx"):
                fr = s["fit"]
                ax.plot(_nan(s["fx"]), _nan(s["fy"]), "-", lw=1.4, color=col, alpha=0.8,
                        label=f"{fr['name'] if lang == 'de' else FIT_MODELS[fr['model']][1]} (R² = {fr['r2']:.4f})".replace(".", dec))
        else:
            ax.plot(_nan(s["x"]), _nan(s["y"]), "-", lw=1.6, color=col, label=label)
    for c in curves or []:
        ax.plot(_nan(c["x"]), _nan(c["y"]), "-", lw=1.6, color=c.get("color") or "#37474f", label=c.get("label"))
    has_fn = any(spec.get("visible") is not False and spec.get("kind") != "curve" for spec in plot.get("functions", []))
    if has_fn or not curves:          # gleiche Ansicht wie im Rechner; nur reine Formelkurven skalieren selbst
        ax.set_xlim(x0, x1)
        ax.set_ylim(y0, y1)
        ax.axhline(0, color="#90a4ae", lw=0.8, zorder=0)
        ax.axvline(0, color="#90a4ae", lw=0.8, zorder=0)
    ax.grid(True, color="#e0e0e0", lw=0.6)
    ax.set_xlabel(plot.get("xlabel") or "x")
    ax.set_ylabel(plot.get("ylabel") or "y")
    if lang == "de":
        from matplotlib.ticker import FuncFormatter
        fmt = FuncFormatter(lambda v, _p: f"{v:g}".replace(".", ","))
        ax.xaxis.set_major_formatter(fmt)
        ax.yaxis.set_major_formatter(fmt)
    if ax.get_legend_handles_labels()[0]:
        ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    return fig


def _nan(v):
    return [math.nan if x is None else x for x in v]


def _label(spec):
    k = spec.get("kind", "fx")
    if k == "fx":
        return f"y = {spec.get('expr', '')}"
    if k == "param":
        return f"({spec.get('x', '')}, {spec.get('y', '')})"
    if k == "polar":
        return f"r = {spec.get('r', '')}"
    return spec.get("name") or "Messdaten"
