"""Gleichungen und Gleichungssysteme lösen (S-01, S-02).

Eine Gleichung mit einer Unbekannten:

* Polynome (bis Grad 24) aus dem Ausdrucksbaum: Grad 1 und 2 exakt, bei rationalen Koeffizienten als Bruch bzw.
  Wurzelform (x = (−1 ± √13)/2); höhere Grade mit den Eigenwerten der Begleitmatrix (numpy.roots), rationale
  Nullstellen werden exakt erkannt und abgespalten (Rest vom Grad 2 wieder exakt).
* alles andere numerisch: Vorzeichenwechsel und Berührstellen auf wachsenden Rastern (±10, ±10³ und logarithmisch
  1e-6…1e3, ±1e-15…1e15), Bisektion bzw. Minimum von |f|; höchstens MAX_SOL Lösungen, bei periodischen Gleichungen
  die im kleinsten Bereich.
* Bedingungen (x > 0) filtern die Lösungen.
* Einheit der Unbekannten: die Exponenten der SI-Basiseinheiten sind in jedem Term linear in denen der Unbekannten;
  Summen und Funktionsargumente (exp, ln, sin …) liefern lineare Gleichungen dafür.

Gleichungssysteme: linear (numerisch geprüft) mit Rang, reduzierter Stufenform, Parameterform oder Ausgleichslösung,
exakt in Brüchen, wenn alle Koeffizienten rational sind; nichtlinear mit gedämpftem Newton-Verfahren von mehreren
Startpunkten.
"""
from __future__ import annotations

import ast
import math
from fractions import Fraction

import numpy as np

from . import expr as E
from . import units as U

MAX_SOL = 12
MAX_DEG = 24
_FIXED = {"inf", "nan", "i", "j"}
_ERRS = (E.CalcError, ValueError, TypeError, ZeroDivisionError, OverflowError, FloatingPointError, IndexError,
         ArithmeticError, np.linalg.LinAlgError)


class SolveError(E.CalcError):
    pass


# ----------------------------------------------------------------------------- Namen
def free_names(node, ctx) -> list:
    """Namen ohne Wert (in Reihenfolge des Auftretens); Laufvariablen von integral, sum … zählen nicht."""
    out = []

    def walk(n, bound):
        if isinstance(n, ast.Name):
            k = n.id
            if (k not in bound and k not in ctx.names and k not in U.CONSTANTS and k not in _FIXED
                    and k not in E.BUILTINS and k not in E.SPECIAL and k not in ctx.funcs and k not in out):
                out.append(k)
            return
        if isinstance(n, ast.Call):
            fn = n.func.id if isinstance(n.func, ast.Name) else None
            if fn in E.SPECIAL and fn not in ("if", "if_") and len(n.args) >= 2 and isinstance(n.args[1], ast.Name):
                walk(n.args[0], bound | {n.args[1].id})
                for a in n.args[2:]:
                    walk(a, bound)
                return
            for a in n.args:
                walk(a, bound)
            return
        for c in ast.iter_child_nodes(n):
            walk(c, bound)

    walk(node, frozenset())
    return out


def _has(node, names) -> bool:
    names = {names} if isinstance(names, str) else set(names)
    return any(isinstance(m, ast.Name) and m.id in names for m in ast.walk(node))


def residual(lhs, rhs):
    return ast.BinOp(left=lhs, op=ast.Sub(), right=rhs)


# ----------------------------------------------------------------------------- Einheiten der Unbekannten
def _lz():
    return (np.zeros(7), {})


def _ladd(a, b, s=1.0):
    k = dict(a[1])
    for u, v in b[1].items():
        k[u] = k.get(u, 0.0) + s * v
    return (a[0] + s * b[0], k)


def _lscale(a, f):
    return (a[0] * f, {u: v * f for u, v in a[1].items()})


def _num_const(node, ctx):
    v = np.asarray(E.evaluate(node, ctx))
    if v.ndim:
        raise SolveError("Exponent muss eine Zahl sein")
    return float(np.real(v))


def _dlin(node, ctx, unk, cons, dd):
    """Dimension als (c, k) mit d = c + Σ k[u]·d(u); None = unbekannt. Summen hängen Bedingungen an cons."""
    t = type(node)
    if t is ast.Constant:
        return _lz()
    if t is ast.Name:
        n = node.id
        if n in unk:
            return (np.zeros(7), {n: 1.0})
        if n in dd:
            return (np.array(dd[n], dtype=float), {})
        if n in U.CONSTANTS:
            return (np.array(U.constant_dims(n), dtype=float), {})
        if n in _FIXED:
            return _lz()
        return None
    if t is ast.UnaryOp:
        return _dlin(node.operand, ctx, unk, cons, dd)
    if t is ast.BinOp:
        op = type(node.op)
        a = _dlin(node.left, ctx, unk, cons, dd)
        if op is ast.Pow:
            if a is None:
                return None
            if _has(node.right, unk):
                cons.append(a)                                   # Basis ohne Einheit
                return _lz()
            try:
                return _lscale(a, _num_const(node.right, ctx))
            except _ERRS:
                return None
        b = _dlin(node.right, ctx, unk, cons, dd)
        if a is None or b is None:
            return None
        if op in (ast.Add, ast.Sub, ast.Mod):
            cons.append(_ladd(a, b, -1.0))
            return a if len(a[1]) <= len(b[1]) else b
        if op in (ast.Mult, ast.MatMult):
            return _ladd(a, b)
        if op is ast.Div:
            return _ladd(a, b, -1.0)
        return None
    if t is ast.Call and isinstance(node.func, ast.Name):
        fn, args = node.func.id, node.args
        if not _has(node, unk):
            d = E.dims_of(node, dd)
            return (np.array(d, dtype=float), {}) if d is not None else None
        ds = lambda k: _dlin(args[k], ctx, unk, cons, dd)       # noqa: E731
        if fn == "sqrt" and len(args) == 1:
            a = ds(0)
            return _lscale(a, 0.5) if a else None
        if fn == "cbrt" and len(args) == 1:
            a = ds(0)
            return _lscale(a, 1 / 3) if a else None
        if fn == "root" and len(args) == 2 and not _has(args[1], unk):
            a = ds(0)
            try:
                return _lscale(a, 1.0 / _num_const(args[1], ctx)) if a else None
            except _ERRS:
                return None
        if fn in ("abs", "round", "floor", "ceil", "re", "im", "conj", "mean", "median") and args:
            return ds(0)
        if fn in ("min", "max", "hypot") and args:
            parts = [ds(k) for k in range(len(args))]
            if any(p is None for p in parts):
                return None
            for p in parts[1:]:
                cons.append(_ladd(parts[0], p, -1.0))
            return parts[0]
        if fn == "sign":
            return _lz()
        if fn == "atan2" and len(args) == 2:
            a, b = ds(0), ds(1)
            if a is not None and b is not None:
                cons.append(_ladd(a, b, -1.0))
            return _lz()
        if fn in E._DIMLESS_FUNCS or fn == "log":
            a = ds(0)
            if a is not None:
                cons.append(a)
            return _lz()
        return None
    if t in (ast.Compare, ast.BoolOp):
        return _lz()
    if not _has(node, unk):
        d = E.dims_of(node, dd)
        return (np.array(d, dtype=float), {}) if d is not None else None
    return None


def infer_dims(pairs, ctx, unknowns):
    """Einheit (Dimension) jeder Unbekannten aus den Gleichungen [(links, rechts)].

    -> ({u: Dimension oder None}, widersprüchlich). Ohne Grössen mit Einheit: alle None."""
    names = {m.id for lhs, rhs in pairs for side in (lhs, rhs) for m in ast.walk(side) if isinstance(m, ast.Name)}
    if not names & set(ctx.dims):
        return {u: None for u in unknowns}, False
    dd = {n: U.D0 for n in ctx.names}
    dd.update(ctx.dims)
    unk = set(unknowns)
    cons = []
    for lhs, rhs in pairs:
        a, b = _dlin(lhs, ctx, unk, cons, dd), _dlin(rhs, ctx, unk, cons, dd)
        if a is not None and b is not None:
            cons.append(_ladd(a, b, -1.0))
    res = {}
    progress = True
    while progress:
        progress = False
        for c, k in cons:
            open_ = [u for u, v in k.items() if abs(v) > 1e-12 and u not in res]
            if len(open_) != 1:
                continue
            u = open_[0]
            rest = c + sum((k[w] * np.array(res[w]) for w in k if w in res and abs(k[w]) > 1e-12), np.zeros(7))
            res[u] = tuple(float(x) for x in -rest / k[u])
            progress = True
    bad = False
    for c, k in cons:
        if all(u in res or abs(v) <= 1e-12 for u, v in k.items()):
            tot = c + sum((v * np.array(res[u]) for u, v in k.items() if u in res and abs(v) > 1e-12), np.zeros(7))
            if np.any(np.abs(tot) > 1e-9):
                bad = True
    return {u: res.get(u) for u in unknowns}, bad


# ----------------------------------------------------------------------------- Polynome
class _NotPoly(Exception):
    pass


def _exact(node):
    """Reine Zahlenausdrücke (Ziffern, + − · /, ganzzahlige Potenzen) als Bruch, sonst None."""
    t = type(node)
    if t is ast.Constant and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return Fraction(str(node.value)) if isinstance(node.value, float) else Fraction(node.value)
    if t is ast.UnaryOp and isinstance(node.op, (ast.USub, ast.UAdd)):
        v = _exact(node.operand)
        return None if v is None else (-v if isinstance(node.op, ast.USub) else v)
    if t is ast.BinOp:
        a, b = _exact(node.left), _exact(node.right)
        if a is None or b is None:
            return None
        op = type(node.op)
        if op is ast.Add:
            return a + b
        if op is ast.Sub:
            return a - b
        if op is ast.Mult:
            return a * b
        if op is ast.Div:
            return a / b if b != 0 else None
        if op is ast.Pow and b.denominator == 1 and abs(b) <= 64 and (a != 0 or b >= 0):
            return a ** int(b)
    return None


def _leaf(node, ctx):
    ex = _exact(node)
    if ex is not None:
        return ex
    try:
        v = np.asarray(E.evaluate(node, ctx))
    except _ERRS as e:
        raise _NotPoly from e
    if v.ndim:
        raise _NotPoly
    z = complex(v)
    if not (math.isfinite(z.real) and math.isfinite(z.imag)):
        raise _NotPoly
    return z if abs(z.imag) > 1e-14 * max(1.0, abs(z.real)) else z.real


def _padd(a, b, s=1):
    n = max(len(a), len(b))
    return [(a[i] if i < len(a) else 0) + s * (b[i] if i < len(b) else 0) for i in range(n)]


def _pmul(a, b):
    out = [Fraction(0)] * (len(a) + len(b) - 1)
    for i, x in enumerate(a):
        if x == 0:
            continue
        for j, y in enumerate(b):
            out[i + j] += x * y
    if len(out) > MAX_DEG + 1 and any(c != 0 for c in out[MAX_DEG + 1:]):
        raise _NotPoly
    return out


def poly_of(node, x, ctx):
    """Koeffizienten (niedrigster Grad zuerst; Bruch, float oder complex) oder None, wenn kein Polynom in x."""
    def go(n):
        if not _has(n, x):
            return [_leaf(n, ctx)]
        if isinstance(n, ast.Name):
            return [Fraction(0), Fraction(1)]
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            p = go(n.operand)
            return [-c for c in p] if isinstance(n.op, ast.USub) else p
        if isinstance(n, ast.BinOp):
            op = type(n.op)
            if op in (ast.Add, ast.Sub):
                return _padd(go(n.left), go(n.right), -1 if op is ast.Sub else 1)
            if op is ast.Mult:
                return _pmul(go(n.left), go(n.right))
            if op is ast.Div and not _has(n.right, x):
                c = _leaf(n.right, ctx)
                if c == 0:
                    raise _NotPoly
                return [k / c for k in go(n.left)]
            if op is ast.Pow and not _has(n.right, x):
                e = _leaf(n.right, ctx)
                if isinstance(e, complex) or float(e) != int(float(e)) or not 0 <= float(e) <= MAX_DEG:
                    raise _NotPoly
                base, r = go(n.left), [Fraction(1)]
                for _ in range(int(float(e))):
                    r = _pmul(r, base)
                return r
        raise _NotPoly

    try:
        c = go(node)
    except _NotPoly:
        return None
    return _trim([Fraction(k) if isinstance(k, int) else k for k in c])


def _trim(c):
    mags = [abs(complex(k)) for k in c]
    top = max(mags) if mags else 0.0
    tol = 0.0 if all(isinstance(k, Fraction) for k in c) else 1e-13 * top
    while len(c) > 1 and abs(complex(c[-1])) <= tol:
        c = c[:-1]
    return c


def _pval_exact(c, r):
    s = Fraction(0)
    for k in reversed(c):
        s = s * r + k
    return s


def _deflate(c, r):
    """c (niedrigster Grad zuerst) durch (x − r) teilen."""
    hi = list(reversed(c))
    out, acc = [], Fraction(0)
    for k in hi[:-1]:
        acc = acc * r + k
        out.append(acc)
    return list(reversed(out))


def _squarefree(n: int):
    """n = k²·m mit quadratfreiem m; None, wenn n zu gross ist."""
    if n > 10 ** 12:
        return None
    k, m, f = 1, n, 2
    while f * f <= m:
        while m % (f * f) == 0:
            m //= f * f
            k *= f
        f += 1
    return k, m


def _sqrt_parts(D: Fraction):
    """√D = q·√m mit Bruch q und quadratfreiem m (D > 0)."""
    n, d = D.numerator, D.denominator
    sf = _squarefree(n * d)
    if sf is None:
        return None
    k, m = sf
    return Fraction(k, d), m


def _quad_exact(c):
    """Exakte Lösungen von c0 + c1·x + c2·x² (Brüche). -> (Lösungen, Wurzelform oder None, komplex)."""
    a, b, cc = c[2], c[1], c[0]
    D = b * b - 4 * a * cc
    p = -b / (2 * a)
    if D == 0:
        return [{"value": float(p), "exact": p, "mult": 2}], None, False
    sp = _sqrt_parts(abs(D))
    if sp is None:
        return None
    q, m = sp
    q = abs(q / (2 * a))
    if D > 0:
        if m == 1:
            rs = sorted([p - q, p + q])
            return [{"value": float(r), "exact": r} for r in rs], None, False
        s = float(q) * math.sqrt(m)
        form = {"p": p, "q": q, "m": m, "i": False}
        return ([{"value": float(p) - s, "surd": {**form, "sign": -1}}, {"value": float(p) + s, "surd": {**form, "sign": 1}}],
                form, False)
    s = float(q) * math.sqrt(m)
    form = {"p": p, "q": q, "m": m, "i": True}
    return ([{"value": complex(float(p), -s), "surd": {**form, "sign": -1}},
             {"value": complex(float(p), s), "surd": {**form, "sign": 1}}], form, True)


def _polish(c_hi, r):
    d = np.polyder(c_hi)
    for _ in range(6):
        f, fp = np.polyval(c_hi, r), np.polyval(d, r)
        if fp == 0 or not np.isfinite(f):
            break
        nr = r - f / fp
        if not np.isfinite(nr):
            break
        if abs(nr - r) <= 1e-15 * max(1.0, abs(nr)):
            r = nr
            break
        r = nr
    return r


def _numeric_poly_roots(c):
    c_hi = np.array([complex(k) for k in reversed(c)])
    if not np.any(c_hi.imag):
        c_hi = c_hi.real
    rts = [_polish(c_hi, r) for r in np.roots(c_hi)]
    groups = []
    for r in sorted(rts, key=lambda z: (round(z.real, 6), z.imag)):
        for g in groups:
            if abs(np.mean(g) - r) <= 1e-4 * max(1.0, abs(r)):
                g.append(r)
                break
        else:
            groups.append([r])
    out = []
    for g in groups:
        z = complex(np.mean(g))
        if abs(z.imag) <= 1e-7 * max(1.0, abs(z)):
            z = complex(z.real, 0.0)
        out.append({"value": z if z.imag else z.real, "mult": len(g)})
    return out


def solve_poly(c, complex_ok=False):
    """Nullstellen eines Polynoms c (niedrigster Grad zuerst, Grad ≥ 1). -> (Lösungen, Wurzelform, Hinweise)."""
    notes, form = [], None
    exact = all(isinstance(k, Fraction) for k in c)
    sols = []
    if exact:
        c = list(c)
        while len(c) > 3:                                      # rationale Nullstellen abspalten
            found = None
            # Satz über rationale Nullstellen: bei ganzzahligen Koeffizienten teilt der Nenner p/q (gekürzt) den
            # Leitkoeffizienten; gesucht wird also bis zu diesem Nenner (mindestens 1000, höchstens 10¹²). Jeder
            # Kandidat wird exakt in Brüchen eingesetzt und nur bei P(p/q) = 0 als exakte Lösung gezeigt.
            den = math.lcm(*[k.denominator for k in c])
            lead = abs(int(c[-1] * den))
            qmax = min(max(1000, lead), 10 ** 12)
            for s in _numeric_poly_roots(c):
                v = s["value"]
                if isinstance(v, complex):
                    continue
                fr = Fraction(v).limit_denominator(qmax)
                if _pval_exact(c, fr) == 0:
                    found = fr
                    break
            if found is None:
                break
            sols.append({"value": float(found), "exact": found})
            c = _deflate(c, found)
        if len(c) == 2:
            r = -c[0] / c[1]
            sols.append({"value": float(r), "exact": r})
            c = [c[0]]
        elif len(c) == 3:
            q = _quad_exact(c)
            if q is not None:
                qs, form, _ = q
                sols.extend(qs)
                c = [c[0]]
    if len(c) > 1:
        sols.extend(_numeric_poly_roots(c))
    # gleiche Lösungen zusammenfassen (Vielfachheit)
    merged = []
    for s in sols:
        for m in merged:
            if abs(complex(m["value"]) - complex(s["value"])) <= 1e-9 * max(1.0, abs(complex(s["value"]))):
                m["mult"] = m.get("mult", 1) + s.get("mult", 1)
                break
        else:
            merged.append(dict(s))
    real = [s for s in merged if not isinstance(s["value"], complex)]
    cplx = [s for s in merged if isinstance(s["value"], complex)]
    if cplx and not complex_ok:
        notes.append(f"dazu {len(cplx)} komplexe Lösung{'en' if len(cplx) > 1 else ''} (Einstellung „komplex“ zeigt sie)")
        if form and form.get("i"):
            form = None
        merged = real
    merged.sort(key=lambda s: (complex(s["value"]).real, complex(s["value"]).imag))
    return merged, form, notes, cplx


# ----------------------------------------------------------------------------- numerisch
def _real(v):
    a = np.asarray(v)
    if a.ndim:
        raise SolveError("Die Gleichung ergibt eine Liste oder Matrix – lösen lassen sich nur Zahlen")
    z = complex(a)
    if abs(z.imag) > 1e-12 * max(1.0, abs(z.real)):
        return math.nan
    return z.real


def _safe1(f, x):
    try:
        with np.errstate(all="ignore"):
            return _real(f(float(x)))
    except _ERRS:
        return math.nan


def _vals(f, X):
    Y = None
    with np.errstate(all="ignore"):
        try:
            Y = np.asarray(f(X))
            if Y.ndim == 0:
                Y = np.full(X.shape, Y)
            if Y.shape != X.shape:
                Y = None
        except _ERRS:
            Y = None
    if Y is None:
        Y = np.array([_safe1(f, x) for x in X])
    if np.iscomplexobj(Y):
        bad = np.abs(Y.imag) > 1e-12 * np.maximum(1.0, np.abs(Y.real))
        Y = np.where(bad, np.nan, Y.real)
    return np.asarray(Y, dtype=float)


def _grids():
    lin = np.linspace(-10.0, 10.0, 4001)
    l2 = np.logspace(-6, 3, 3000)
    l3 = np.logspace(-15, 15, 6000)
    return [(10.0, lin),
            (1e3, np.unique(np.concatenate([-l2[::-1], [0.0], l2, np.linspace(-1e3, 1e3, 4001)]))),
            (1e15, np.unique(np.concatenate([-l3[::-1], [0.0], l3])))]


def _golden_min(g, a, b, it=80):
    phi = (math.sqrt(5) - 1) / 2
    c, d = b - phi * (b - a), a + phi * (b - a)
    gc, gd = g(c), g(d)
    for _ in range(it):
        if gc < gd:
            b, d, gd = d, c, gc
            c = b - phi * (b - a)
            gc = g(c)
        else:
            a, c, gc = c, d, gd
            d = a + phi * (b - a)
            gd = g(d)
    return (a + b) / 2


def _touch_polish(f, r):
    """Berührstelle genauer: Newton auf f' (|f| allein ist nur auf √ε genau)."""
    g = lambda t: np.real(f(t))                                # noqa: E731
    for _ in range(5):
        try:
            d1 = float(E.deriv_at(g, r, 1))
            d2 = float(E.deriv_at(g, r, 2))
        except _ERRS:
            break
        if not (math.isfinite(d1) and math.isfinite(d2)) or d2 == 0:
            break
        nr = r - d1 / d2
        if not math.isfinite(nr) or abs(nr - r) > 1e-4 * max(1.0, abs(r)):
            break
        r = nr
    return r


def _scan(f, X):
    Y = _vals(f, X)
    roots = []
    fin = np.isfinite(Y)
    for i in np.nonzero(fin & (Y == 0))[0]:
        roots.append(float(X[i]))
    s = np.nonzero(fin[:-1] & fin[1:] & (np.sign(Y[:-1]) * np.sign(Y[1:]) < 0))[0]
    for i in s:
        a, b = float(X[i]), float(X[i + 1])
        r = E.bisect(lambda t: _safe1(f, t), a, b, float(Y[i]), float(Y[i + 1]))
        fr = _safe1(f, r)
        if math.isfinite(fr) and abs(fr) <= 1e-6 * max(abs(Y[i]), abs(Y[i + 1])):
            roots.append(r)
    A = np.abs(Y)
    for i in range(1, len(X) - 1):                                   # Berührstellen: kleines Minimum von |f|
        if not (fin[i - 1] and fin[i] and fin[i + 1]) or Y[i] == 0:
            continue
        if A[i] < A[i - 1] and A[i] <= A[i + 1] and np.sign(Y[i - 1]) == np.sign(Y[i]) == np.sign(Y[i + 1]):
            scale = max(A[i - 1], A[i + 1])
            if A[i] > 0.2 * scale:
                continue
            r = _golden_min(lambda t: abs(_safe1(f, t)) if math.isfinite(_safe1(f, t)) else math.inf,
                            float(X[i - 1]), float(X[i + 1]))
            r = _touch_polish(f, r)
            fr = _safe1(f, r)
            if math.isfinite(fr) and abs(fr) <= 1e-12 * max(1.0, scale):
                roots.append(r)
    roots.sort()
    out = []
    for r in roots:
        if not out or abs(r - out[-1]) > 1e-9 * max(1.0, abs(r)):
            out.append(r)
    return out


def _polish_num(f, r):
    for _ in range(4):
        fx = _safe1(f, r)
        if not math.isfinite(fx) or fx == 0:
            break
        try:
            d = float(np.real(E.deriv_at(lambda t: np.real(f(t)), r)))
        except _ERRS:
            break
        if not math.isfinite(d) or d == 0:
            break
        nr = r - fx / d
        if not math.isfinite(nr) or abs(_safe1(f, nr)) > abs(fx):
            break
        r = nr
    return r


def solve_numeric(f, conds_ok=None):
    """Reelle Nullstellen von f. -> (Lösungen, Hinweise)."""
    notes = []
    grids = _grids()
    found, rng = [], None
    for k, (R, X) in enumerate(grids):
        rs = _scan(f, X)
        if conds_ok:
            rs = [r for r in rs if conds_ok(r)]
        if rs:
            found, rng = rs, R
            if k + 1 < len(grids):
                more = _scan(f, grids[k + 1][1])
                if conds_ok:
                    more = [r for r in more if conds_ok(r)]
                if len(more) <= MAX_SOL:
                    allr = sorted(set(found) | set(more))
                    found = []
                    for r in allr:
                        if not found or abs(r - found[-1]) > 1e-8 * max(1.0, abs(r)):
                            found.append(r)
                    rng = grids[k + 1][0]
                else:
                    notes.append(f"viele Lösungen (periodisch?) – gezeigt die zwischen −{_fmt_r(R)} und {_fmt_r(R)}")
            break
    if len(found) > MAX_SOL:
        found = sorted(sorted(found, key=abs)[:MAX_SOL])
        notes.append(f"mehr als {MAX_SOL} Lösungen – gezeigt die {MAX_SOL} nächsten bei 0")
    found = [_polish_num(f, r) for r in found]
    if not found:
        notes.append("numerisch gesucht zwischen −10¹⁵ und 10¹⁵")
    return [{"value": r} for r in found], notes, rng


def _fmt_r(R):
    return {10.0: "10", 1e3: "1000"}.get(R, "10¹⁵")


# ----------------------------------------------------------------------------- eine Gleichung
def solve_equation(lhs, rhs, x, ctx, conds=()):
    """Gleichung lhs = rhs nach x lösen.

    -> {"status": "ok" | "none" | "identity", "solutions": [{value, exact?, mult?}], "form": Wurzelform oder None,
        "method": "linear" | "quadratic" | "polynomial" | "numeric", "notes": [...], "dims": Dimension oder None}"""
    node = residual(lhs, rhs)
    dims, bad = infer_dims([(lhs, rhs)], ctx, [x])
    notes = ["die Einheiten der beiden Seiten passen nicht zusammen"] if bad else []

    def f(v):
        return E.evaluate(node, ctx, {x: v})

    def ok(v):
        if not conds:
            return True
        try:
            return all(bool(np.all(E.evaluate(c, ctx, {x: v}))) for c in conds)
        except _ERRS:
            return False

    try:
        probe = np.asarray(E.evaluate(node, ctx, {x: 1.2345}))
        if probe.ndim:
            raise SolveError("Die Gleichung ergibt eine Liste oder Matrix – lösen lassen sich nur Zahlen")
    except SolveError:
        raise
    except _ERRS:
        pass
    out = {"status": "ok", "solutions": [], "form": None, "method": "numeric", "notes": notes,
           "dims": None if bad else dims.get(x), "complex": []}
    c = poly_of(node, x, ctx)
    if c is not None:
        if len(c) == 1:
            out["status"] = "identity" if abs(complex(c[0])) <= 1e-12 else "none"
            out["method"] = "polynomial"
            return out
        deg = len(c) - 1
        sols, form, pn, cplx = solve_poly(c, bool(ctx.complex_ok))
        out.update(method="linear" if deg == 1 else "quadratic" if deg == 2 else "polynomial", form=form, degree=deg,
                   complex=[s["value"] for s in cplx])
        out["notes"] += pn
        if conds:
            kept = [s for s in sols if not isinstance(s["value"], complex) and ok(s["value"])]
            if len(kept) != len(sols):
                out["form"] = None
            sols = kept
        out["solutions"] = sols
    else:
        sols, nn, _rng = solve_numeric(f, ok if conds else None)
        out["solutions"] = sols
        out["notes"] += nn
    if not out["solutions"]:
        out["status"] = "none"
    return out


# ----------------------------------------------------------------------------- Gleichungssysteme
def _frac(v):
    if not math.isfinite(v):
        return None
    fr = Fraction(v).limit_denominator(10000)
    return fr if abs(float(fr) - v) <= 1e-12 * max(1.0, abs(v)) else None


def rref(M, exact=False):
    """Reduzierte Stufenform der erweiterten Matrix [A | b] (letzte Spalte rechts). -> (Matrix, Pivotspalten)."""
    M = [list(r) for r in M]
    rows, cols = len(M), len(M[0]) if M else 0
    top = max((abs(float(v)) for r in M for v in r), default=1.0) or 1.0
    tol = 0 if exact else 1e-11 * top
    piv, r = [], 0
    for c in range(cols - 1):
        if r >= rows:
            break
        if exact:
            p = next((i for i in range(r, rows) if M[i][c] != 0), None)
        else:
            p = max(range(r, rows), key=lambda i: abs(M[i][c]))
            if abs(M[p][c]) <= tol:
                p = None
        if p is None:
            continue
        M[r], M[p] = M[p], M[r]
        pv = M[r][c]
        M[r] = [v / pv for v in M[r]]
        for i in range(rows):
            if i != r and M[i][c] != 0:
                fct = M[i][c]
                M[i] = [a - fct * b for a, b in zip(M[i], M[r])]
        if not exact:
            M = [[0.0 if abs(v) <= tol else v for v in row] for row in M]
        piv.append(c)
        r += 1
    return M, piv


def _lin_system(F, n):
    """Lineares System erkennen: F(u) = A·u − b für alle u. -> (A, b) oder None."""
    try:
        f0 = F(np.zeros(n))
        A = np.column_stack([F(np.eye(n)[j]) - f0 for j in range(n)]) if n else np.zeros((len(f0), 0))
        rng = np.random.default_rng(3)
        for _ in range(2):
            u = rng.normal(0, 3, n)
            lhs = F(u)
            if not np.all(np.isfinite(lhs)) or not np.allclose(lhs, f0 + A @ u, rtol=1e-9,
                                                                 atol=1e-9 * (1 + np.abs(lhs).max())):
                return None
    except _ERRS:
        return None
    if not (np.all(np.isfinite(A)) and np.all(np.isfinite(f0))):
        return None
    return A, -f0


def _newton(F, x0, check):
    x = np.array(x0, dtype=float)
    n = x.size
    extra = 0
    for _ in range(80):
        try:
            fx = F(x)
        except _ERRS:
            return x if check(x) else None
        if not np.all(np.isfinite(fx)):
            return None
        if check(x):                                     # gefunden: noch zwei Schritte für volle Genauigkeit
            extra += 1
            if extra > 2 or not np.any(fx):
                return x
        J = np.empty((fx.size, n))
        for j in range(n):
            h = 1e-7 * max(1.0, abs(x[j]))
            d = x.copy()
            d[j] += h
            try:
                J[:, j] = (F(d) - fx) / h
            except _ERRS:
                return None
        if not np.all(np.isfinite(J)):
            return None
        dx = np.linalg.lstsq(J, -fx, rcond=None)[0]
        nf, lam = float(fx @ fx), 1.0
        while lam > 1e-6:
            xn = x + lam * dx
            try:
                fn = F(xn)
            except _ERRS:
                fn = None
            if fn is not None and np.all(np.isfinite(fn)) and float(fn @ fn) < nf:
                break
            lam /= 2
        else:
            return x if check(x) else None
        x = xn
        if np.linalg.norm(lam * dx) <= 1e-15 * (1 + np.linalg.norm(x)):
            break
    return x if check(x) else None


def solve_system(pairs, ctx, unknowns=None):
    """Gleichungssystem [(links, rechts)] lösen.

    -> {"type": "linear" | "nonlinear", "unknowns": [...], "status": "unique" | "infinite" | "none" | "ok",
        "solutions": [[Wert je Unbekannte], …], "exact": [[Bruch oder None]] , "A", "b", "rref", "rank",
        "param": {Unbekannte: (Konstante, {freie: Faktor})}, "free": [...], "lsq": [...], "dims": {...}, "notes"}"""
    nodes = [residual(lhs, rhs) for lhs, rhs in pairs]
    unk = list(unknowns) if unknowns else []
    if not unk:
        for nd in nodes:
            for u in free_names(nd, ctx):
                if u not in unk:
                    unk.append(u)
    if not unk:
        raise SolveError("Das System hat keine Unbekannten")
    n, m = len(unk), len(nodes)
    dims, bad = infer_dims(pairs, ctx, unk)
    notes = ["die Einheiten passen nicht zusammen"] if bad else []

    def F(u):
        loc = dict(zip(unk, (float(v) for v in u)))
        return np.array([_real(E.evaluate(nd, ctx, loc)) for nd in nodes], dtype=float)

    out = {"unknowns": unk, "notes": notes, "dims": {u: (None if bad else dims.get(u)) for u in unk}}
    lin = _lin_system(F, n)
    if lin is not None:
        A, b = lin
        A, b = A + 0.0, b + 0.0                                    # −0 (aus −F(0)) als 0 anzeigen
        fa = [[_frac(float(v)) for v in row] + [_frac(float(bv))] for row, bv in zip(A.tolist(), b.tolist())]
        exact = all(v is not None for row in fa for v in row)
        M = fa if exact else [list(row) + [bv] for row, bv in zip(A.tolist(), b.tolist())]
        R, piv = rref(M, exact)
        rank = len(piv)
        incons = any(all(v == 0 for v in row[:-1]) and row[-1] != 0 for row in R)
        out.update(type="linear", A=A.tolist(), b=b.tolist(), rank=rank, exact_coeffs=exact,
                   rref=[[float(v) + 0.0 for v in row] for row in R])
        if incons:
            ls = np.linalg.lstsq(A, b, rcond=None)[0]
            out.update(status="none", solutions=[], lsq=ls.tolist(), lsq_res=float(np.linalg.norm(A @ ls - b)))
            return out
        if rank == n:
            sol = [None] * n
            for r, c in enumerate(piv):
                sol[c] = R[r][-1]
            out.update(status="unique", solutions=[[float(v) for v in sol]],
                       exact=[[v if exact else None for v in sol]])
            return out
        free = [unk[c] for c in range(n) if c not in piv]
        param = {}
        for r, c in enumerate(piv):
            param[unk[c]] = (R[r][-1], {unk[f]: -R[r][f] for f in range(n) if f not in piv and R[r][f] != 0})
        out.update(status="infinite", solutions=[], free=free, param=param)
        return out
    if m != n:
        raise SolveError(f"Nichtlineares System: so viele Gleichungen wie Unbekannte nötig ({m} Gleichungen, "
                         f"{n} Unbekannte: {', '.join(unk)})")

    def check(u):
        loc = dict(zip(unk, (float(v) for v in u)))
        try:
            for lhs, rhs in pairs:
                a, bb = _real(E.evaluate(lhs, ctx, loc)), _real(E.evaluate(rhs, ctx, loc))
                if not (math.isfinite(a) and math.isfinite(bb)) or abs(a - bb) > 1e-9 * max(1.0, abs(a), abs(bb)):
                    return False
            return True
        except _ERRS:
            return False

    rng = np.random.default_rng(1)
    starts = [np.full(n, v) for v in (0.5, 1.0, -1.0, 2.0, 0.1)]
    for s in (1.0, 10.0, 100.0):
        starts += [rng.normal(0, s, n) for _ in range(10)]
    sols = []
    for x0 in starts:
        x = _newton(F, x0, check)
        if x is None:
            continue
        if not any(np.allclose(x, y, rtol=1e-6, atol=1e-9) for y in sols):
            sols.append(x)
        if len(sols) >= 8:
            break
    sols.sort(key=lambda v: tuple(np.round(v, 9)))
    out.update(type="nonlinear", status="ok" if sols else "none", solutions=[s.tolist() for s in sols],
               exact=[[None] * n for _ in sols])
    out["notes"].append("numerisch (Newton-Verfahren von mehreren Startpunkten) – weitere Lösungen sind möglich"
                        if sols else "keine Lösung gefunden (Newton-Verfahren von mehreren Startpunkten)")
    return out
