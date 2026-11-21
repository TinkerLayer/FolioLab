"""Symbolische Ableitung auf dem Ausdrucksbaum des Rechners (``labcalc.expr``), ohne CAS-Paket.

Regeln wie in jedem Analysis-Lehrbuch (z. B. J. Stewart, *Calculus*, 8. Aufl., Cengage 2016, Kap. 3 „Differentiation
Rules“ und Kap. 6.2–6.7 für exp, ln, Arkus- und Hyperbelfunktionen): Summe, konstanter Faktor, Produkt, Quotient,
Kette, Potenz x^n, allgemeine Potenz u^v = e^(v·ln u), dazu die Ableitungen der elementaren Funktionen des Rechners.
Eigene Funktionen (``f(x) = x^2``) werden mit der Kettenregel über ihre Argumente abgeleitet.

Schreibweisen: ``diff(Ausdruck, x)``, ``diff(Ausdruck, x, n)`` und ``f'(x)``, ``f''(x)`` (``expr.preprocess`` macht
daraus ``fprime_(f, n, x)``). Wo keine Regel existiert (gamma, Fakultät, min/max, mod, Produkte über k …), steht im
Ergebnis ``dnum_(Teilausdruck, x, n)``: eine numerische Ableitung (zentrale Differenz mit Richardson-Schritt,
``expr.deriv_est``) an der jeweiligen Stelle; die Zeile bekommt dazu einen Hinweis.

Das Ergebnis wird vereinfacht: Zahlen zusammengefasst, Faktoren 0 und 1 und Summanden 0 entfernt, gleiche Faktoren zu
Potenzen und gleiche Summanden zusammengefasst, x/x gekürzt. Ganze Zahlen und Brüche bleiben exakt; Dezimalzahlen der
Eingabe bleiben Dezimalzahlen. Im Gradmodus tragen sin, cos, tan, cot den Faktor π/180 (und die Arkusfunktionen
180/π), weil sin(x°) = sin(π·x/180).
"""
from __future__ import annotations

import ast
import copy
import math
from fractions import Fraction

from . import expr as E

PRIME = "fprime_"            # f'(x) -> fprime_(f, 1, x)
NUMERIC = "dnum_"            # numerische Ableitung an der Stelle: dnum_(g, x, n)
MAX_ORDER = 10
_BOUND = {"integral", "sum", "prod", "nsolve", "deriv"}      # zweites Argument ist eine gebundene Laufvariable


class NoRule(E.CalcError):
    pass


# ----------------------------------------------------------------------------- Bausteine
def _c(v):
    return ast.Constant(value=v)


def _nm(n):
    return ast.Name(id=n, ctx=ast.Load())


def _call(f, *args):
    return ast.Call(func=_nm(f), args=list(args), keywords=[])


def _b(a, op, b):
    return ast.BinOp(left=a, op=op, right=b)


def _mul(a, b):
    return _b(a, ast.Mult(), b)


def _div(a, b):
    return _b(a, ast.Div(), b)


def _add(a, b):
    return _b(a, ast.Add(), b)


def _sub(a, b):
    return _b(a, ast.Sub(), b)


def _pow(a, b):
    return _b(a, ast.Pow(), b)


def _neg(a):
    return ast.UnaryOp(op=ast.USub(), operand=a)


ZERO, ONE = 0, 1


def _num(v):
    """Zahl (int, Fraction, float) -> Knoten; negative Zahlen als −(Zahl), Brüche als p/q."""
    if isinstance(v, Fraction):
        if v < 0:
            return _neg(_num(-v))
        if v.denominator == 1:
            return _c(int(v.numerator))
        return _div(_c(int(v.numerator)), _c(int(v.denominator)))
    if isinstance(v, float):
        if v < 0:
            return _neg(_num(-v))
        if v.is_integer() and abs(v) < 1e15:
            return _c(int(v))
        return _c(v)
    if v < 0:
        return _neg(_c(-int(v)))
    return _c(int(v))


def _numval(n):
    """Wert eines reinen Zahlausdrucks (Fraction, wenn exakt, sonst float) oder None."""
    t = type(n)
    if t is ast.Constant:
        v = n.value
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return None
        if isinstance(v, int):
            return Fraction(v)
        if math.isfinite(v) and v.is_integer() and abs(v) < 1e15:
            return Fraction(int(v))
        return v if math.isfinite(v) else None
    if t is ast.UnaryOp and isinstance(n.op, (ast.USub, ast.UAdd)):
        v = _numval(n.operand)
        if v is None:
            return None
        return -v if isinstance(n.op, ast.USub) else v
    if t is ast.BinOp and isinstance(n.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
        a, b = _numval(n.left), _numval(n.right)
        if a is None or b is None:
            return None
        try:
            if isinstance(n.op, ast.Add):
                return a + b
            if isinstance(n.op, ast.Sub):
                return a - b
            if isinstance(n.op, ast.Mult):
                return a * b
            if isinstance(n.op, ast.Div):
                return None if b == 0 else a / b
            return _numpow(a, b)
        except (OverflowError, ZeroDivisionError, ValueError):
            return None
    return None


def _numpow(a, b):
    if isinstance(b, Fraction) and b.denominator == 1 and abs(b) <= 64:
        if a == 0 and b < 0:
            return None
        return a ** int(b) if isinstance(a, Fraction) else float(a) ** int(b)
    fa, fb = float(a), float(b)
    if fa < 0:
        return None
    r = fa ** fb
    if not math.isfinite(r):
        return None
    if isinstance(a, Fraction) and isinstance(b, Fraction) and abs(r - round(r)) < 1e-12 * max(1.0, abs(r)):
        return Fraction(int(round(r)))
    return None if isinstance(a, Fraction) and isinstance(b, Fraction) else r


def text(node) -> str:
    """Kompakte Schreibweise des Rechners (2*x, 3*x^2, cos(x))."""
    s = ast.unparse(node).replace("**", "^").replace(" ", "")
    return s.replace("if_(", "if(")


def has(node, x) -> bool:
    """Hängt der Ausdruck von x ab (als Variable, nicht als gebundene Laufvariable)?"""
    if isinstance(node, ast.Name):
        return node.id == x
    if isinstance(node, ast.Call):
        fn = node.func.id if isinstance(node.func, ast.Name) else None
        a = node.args
        if fn == PRIME:
            return any(has(v, x) for v in a[2:])
        if fn in ("diff", NUMERIC) and len(a) >= 2 and isinstance(a[1], ast.Name):
            return a[1].id == x or has(a[0], x) or any(has(v, x) for v in a[2:])
        if fn in _BOUND and len(a) >= 2 and isinstance(a[1], ast.Name):
            if a[1].id == x:
                return any(has(v, x) for v in a[2:])
            return has(a[0], x) or any(has(v, x) for v in a[2:])
        return any(has(v, x) for v in a)
    return any(has(c, x) for c in ast.iter_child_nodes(node))


def subst(node, mapping: dict):
    """Namen (nicht Funktionsnamen) gleichzeitig durch Ausdrücke ersetzen."""
    class _S(ast.NodeTransformer):
        def visit_Call(self, n):
            n.args = [self.visit(a) for a in n.args]
            return n

        def visit_Name(self, n):
            return copy.deepcopy(mapping[n.id]) if n.id in mapping else n
    return _S().visit(copy.deepcopy(node))


def has_deriv(node) -> bool:
    """Enthält der Ausdruck diff(…, x) oder f'(x)?"""
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
            if n.func.id == PRIME or (n.func.id == "diff" and len(n.args) >= 2):
                return True
    return False


# ----------------------------------------------------------------------------- Vereinfachen
def simplify(node):
    return _s(copy.deepcopy(node))


def _key(n) -> str:
    return ast.dump(n)


def _is_prod(n):
    return (isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Mult, ast.Div))) or \
        (isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)))


def _is_sum(n):
    return isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Add, ast.Sub))


def _collect(n, num, den, coef, inv, done=False):
    """Faktoren eines Produkts sammeln: coef (Liste mit einer Zahl), Zähler- und Nennerfaktoren."""
    v = _numval(n)
    if v is not None:
        if inv:
            if v == 0:
                raise ZeroDivisionError
            coef[0] = coef[0] / v
        else:
            coef[0] = coef[0] * v
        return
    if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
        if isinstance(n.op, ast.USub):
            coef[0] = -coef[0]
        _collect(n.operand, num, den, coef, inv, done)
        return
    if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Mult):
        _collect(n.left, num, den, coef, inv, done)
        _collect(n.right, num, den, coef, inv, done)
        return
    if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div):
        _collect(n.left, num, den, coef, inv, done)
        _collect(n.right, num, den, coef, not inv, done)
        return
    if not done:
        s = _s(n)
        if _is_prod(s) or _numval(s) is not None:
            _collect(s, num, den, coef, inv, True)
            return
        n = s
    if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Pow):
        ev = _numval(n.right)
        if isinstance(ev, Fraction) and ev.denominator == 1 and ev != 0 and _is_prod(n.left):
            c2, nn, dd = _product_parts(n.left)              # (a·b)^n -> a^n·b^n (ganze n)
            cp = _numpow(c2, abs(ev))
            if cp is not None and cp != 0:
                up = inv != (ev < 0)
                coef[0] = coef[0] / cp if up else coef[0] * cp
                m = abs(ev)
                for b, e in nn:
                    (den if up else num).append((b, e * m if not isinstance(e, ast.AST) else _mul(e, _num(m))))
                for b, e in dd:
                    (num if up else den).append((b, e * m if not isinstance(e, ast.AST) else _mul(e, _num(m))))
                return
        if ev is not None and ev < 0:
            (num if inv else den).append((n.left, -ev))
            return
        (den if inv else num).append((n.left, ev if ev is not None else n.right))
        return
    (den if inv else num).append((n, Fraction(1)))


def _merge(fs):
    out, idx = [], {}
    for base, e in fs:
        k = _key(base)
        if k in idx and not isinstance(e, ast.AST) and not isinstance(out[idx[k]][1], ast.AST):
            j = idx[k]
            out[j] = (out[j][0], out[j][1] + e)
        else:
            if not isinstance(e, ast.AST):
                idx[k] = len(out)
            out.append((base, e))
    return out


def _cancel(num, den):
    dk = {}
    for j, (b, e) in enumerate(den):
        if not isinstance(e, ast.AST):
            dk.setdefault(_key(b), j)
    keep_num = []
    den = list(den)
    for b, e in num:
        k = _key(b)
        if not isinstance(e, ast.AST) and k in dk and den[dk[k]] is not None:
            j = dk[k]
            d = e - den[j][1]
            den[j] = None
            if d > 0:
                keep_num.append((b, d))
            elif d < 0:
                den[j] = (b, -d)
            continue
        keep_num.append((b, e))
    return keep_num, [x for x in den if x is not None]


def _rank(base, e):
    if isinstance(base, ast.Name):
        return 0
    if isinstance(base, ast.Call):
        return 2
    if _is_sum(base):
        return 3
    return 1


def _factor_node(base, e):
    if isinstance(e, ast.AST):
        return _pow(base, e)
    if e == 1:
        return base
    return _pow(base, _num(e))


def _chain(nodes):
    out = nodes[0]
    for n in nodes[1:]:
        out = _mul(out, n)
    return out


def _product_parts(n):
    """-> (Zahl, Zählerfaktoren, Nennerfaktoren) eines (beliebigen) Ausdrucks."""
    coef, num, den = [Fraction(1)], [], []
    _collect(n, num, den, coef, False)
    num, den = _cancel(_merge(num), _merge(den))
    num.sort(key=lambda f: _rank(*f))
    den.sort(key=lambda f: _rank(*f))
    return coef[0], num, den


def _build(coef, num, den):
    if coef == 0:
        return _c(0)
    neg = coef < 0
    c = -coef if neg else coef
    if isinstance(c, Fraction):
        cn, cd = c.numerator, c.denominator
    else:
        cn, cd = c, 1
    fn = [_factor_node(b, e) for b, e in num]
    fd = [_factor_node(b, e) for b, e in den]
    top = ([_num(cn)] if cn != 1 or not fn else []) + fn
    bot = ([_num(Fraction(cd))] if cd != 1 else []) + fd
    if neg and not bot:                                    # Vorzeichen an den ersten Faktor: −2x·sin x statt −(2x·sin x)
        top[0] = _num(-cn) if (cn != 1 or not fn) else _neg(top[0])
        return _chain(top)
    node = _chain(top)
    if bot:
        node = _div(node, _chain(bot))
    return _neg(node) if neg else node


def _terms(n, out, sign):
    if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add):
        _terms(n.left, out, sign)
        _terms(n.right, out, sign)
    elif isinstance(n, ast.BinOp) and isinstance(n.op, ast.Sub):
        _terms(n.left, out, sign)
        _terms(n.right, out, -sign)
    elif isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.USub) and _is_sum(n.operand):
        _terms(n.operand, out, -sign)
    else:
        out.append((sign, n))


def _sum(n):
    raw = []
    _terms(n, raw, 1)
    combined, order = {}, []
    const = Fraction(0)

    def add(coef, key_node):
        nonlocal const
        if key_node is None:
            const = const + coef
            if "#const" not in order:                         # Zahl dort, wo sie zuerst steht (1 − x², 6x + 2)
                order.append("#const")
            return
        k = _key(key_node)
        if k not in combined:
            combined[k] = [coef, key_node]
            order.append(k)
        else:
            combined[k][0] = combined[k][0] + coef

    todo = [(sg, t, False) for sg, t in raw]
    while todo:
        sg, t, done = todo.pop(0)
        s = t if done else _s(t)
        if _is_sum(s):                                    # vereinfacht zu einer Summe: einreihen
            sub = []
            _terms(s, sub, sg)
            todo[0:0] = [(a, b, True) for a, b in sub]
            continue
        coef, num, den = _product_parts(s)
        if len(num) == 1 and not den and _is_sum(num[0][0]) and num[0][1] == 1 and coef != 1:
            sub = []                                      # 2·(a + b) -> 2a + 2b
            _terms(num[0][0], sub, 1)
            todo[0:0] = [(sg, _mul(_num(coef), b) if a > 0 else _neg(_mul(_num(coef), b)), False) for a, b in sub]
            continue
        coef = coef * sg
        if not num and not den:
            add(coef, None)
        else:
            add(coef, _build(Fraction(1), num, den))
    terms = [(const, None) if k == "#const" else (combined[k][0], combined[k][1]) for k in order]
    terms = [(c, k) for c, k in terms if c != 0]
    if not terms:
        return _c(0)

    def node_of(c, key):
        if key is None:
            return _num(c)
        cf, num, den = _product_parts(key)
        return _build(c * cf, num, den)
    first_c, first_k = terms[0]
    out = node_of(first_c, first_k)
    for c, key in terms[1:]:
        out = _sub(out, node_of(-c, key)) if c < 0 else _add(out, node_of(c, key))
    return out


def _s(n):
    v = _numval(n)
    if v is not None:
        return _num(v)
    t = type(n)
    if t in (ast.Name, ast.Constant):
        return n
    if t is ast.UnaryOp:
        if isinstance(n.op, ast.UAdd):
            return _s(n.operand)
        if isinstance(n.op, ast.USub):
            o = _s(n.operand)
            if _is_sum(o):
                return _sum(_neg(o))
            coef, num, den = _product_parts(o)
            return _build(-coef, num, den)
        n.operand = _s(n.operand)
        return n
    if t is ast.BinOp:
        op = type(n.op)
        if op in (ast.Add, ast.Sub):
            return _sum(n)
        if op in (ast.Mult, ast.Div):
            try:
                coef, num, den = _product_parts(n)
            except ZeroDivisionError:
                return n
            return _build(coef, num, den)
        if op is ast.Pow:
            return _spow(_s(n.left), _s(n.right))
        n.left, n.right = _s(n.left), _s(n.right)
        return n
    if t is ast.Call:
        n.args = [_s(a) for a in n.args]
        fn = n.func.id if isinstance(n.func, ast.Name) else ""
        if len(n.args) == 1:
            a = n.args[0]
            if fn == "ln" and isinstance(a, ast.Call) and isinstance(a.func, ast.Name) and a.func.id == "exp":
                return a.args[0]
            if fn == "exp" and isinstance(a, ast.Call) and isinstance(a.func, ast.Name) and a.func.id == "ln":
                return a.args[0]
            if fn == "ln" and isinstance(a, ast.Name) and a.id == "e":
                return _c(1)
            if fn == "exp" and _numval(a) == 0:
                return _c(1)
            if fn == "ln" and _numval(a) == 1:
                return _c(0)
        return n
    if t is ast.IfExp:
        n.test, n.body, n.orelse = _s(n.test), _s(n.body), _s(n.orelse)
        return n
    for field, old in ast.iter_fields(n):
        if isinstance(old, list):
            setattr(n, field, [_s(x) if isinstance(x, ast.expr) else x for x in old])
        elif isinstance(old, ast.expr):
            setattr(n, field, _s(old))
    return n


def _spow(b, e):
    ev, bv = _numval(e), _numval(b)
    if ev is not None and bv is not None:
        r = _numpow(bv, ev)
        if r is not None:
            return _num(r)
    if ev is not None:
        if ev == 0:
            return _c(1)
        if ev == 1:
            return b
        if isinstance(b, ast.BinOp) and isinstance(b.op, ast.Pow) and _numval(b.right) is not None:
            ev, b = ev * _numval(b.right), b.left              # (x^a)^b -> x^(a·b)
            if ev == 1:
                return b
        if isinstance(b, ast.Call) and isinstance(b.func, ast.Name) and b.func.id == "sqrt" and len(b.args) == 1 \
                and isinstance(ev, Fraction) and ev.denominator == 1 and ev % 2 == 0:
            return _spow(b.args[0], ev / 2)                     # sqrt(u)^2 -> u
        if ev < 0:
            return _build(Fraction(1), [], [(b, -ev)])
        return _pow(b, _num(ev))
    if bv is not None and bv == 1:
        return _c(1)
    return _pow(b, e)


# ----------------------------------------------------------------------------- Ableiten
class _Ctx:
    def __init__(self, funcs=None, angle="rad"):
        self.funcs = dict(funcs or {})
        self.angle = angle
        self.numeric = []
        self.depth = 0

    @property
    def deg(self):
        return self.angle == "deg"


def _to_rad():
    return _div(_nm("pi"), _c(180))


def _to_deg():
    return _div(_c(180), _nm("pi"))


def _outer(fn, u, C):
    """Äussere Ableitung f'(u) einer eingebauten Funktion mit einem Argument; None = keine Regel."""
    one = _c(1)
    sq = lambda a: _pow(a, _c(2))                       # noqa: E731
    trig = {"sin": lambda: _call("cos", u), "cos": lambda: _neg(_call("sin", u)),
            "tan": lambda: _div(one, sq(_call("cos", u))), "cot": lambda: _neg(_div(one, sq(_call("sin", u))))}
    if fn in trig:
        r = trig[fn]()
        return _mul(r, _to_rad()) if C.deg else r
    atrig = {"asin": lambda: _div(one, _call("sqrt", _sub(one, sq(u)))),
             "acos": lambda: _neg(_div(one, _call("sqrt", _sub(one, sq(u))))),
             "atan": lambda: _div(one, _add(one, sq(u)))}
    if fn in atrig:
        r = atrig[fn]()
        return _mul(r, _to_deg()) if C.deg else r
    table = {
        "sinh": lambda: _call("cosh", u), "cosh": lambda: _call("sinh", u),
        "tanh": lambda: _div(one, sq(_call("cosh", u))),
        "asinh": lambda: _div(one, _call("sqrt", _add(sq(u), one))),
        "acosh": lambda: _div(one, _call("sqrt", _sub(sq(u), one))),
        "atanh": lambda: _div(one, _sub(one, sq(u))),
        "exp": lambda: _call("exp", u), "ln": lambda: _div(one, u),
        "log10": lambda: _div(one, _mul(u, _call("ln", _c(10)))),
        "log": lambda: _div(one, _mul(u, _call("ln", _c(10)))),
        "log2": lambda: _div(one, _mul(u, _call("ln", _c(2)))),
        "sqrt": lambda: _div(one, _mul(_c(2), _call("sqrt", u))),
        "cbrt": lambda: _div(one, _mul(_c(3), sq(_call("cbrt", u)))),
        "abs": lambda: _call("sign", u),
        "erf": lambda: _mul(_div(_c(2), _call("sqrt", _nm("pi"))), _call("exp", _neg(sq(u)))),
        "erfc": lambda: _neg(_mul(_div(_c(2), _call("sqrt", _nm("pi"))), _call("exp", _neg(sq(u))))),
        "sign": lambda: _c(0), "floor": lambda: _c(0), "ceil": lambda: _c(0), "round": lambda: _c(0),
        "deg": lambda: _to_deg(), "rad": lambda: _to_rad(),
    }
    f = table.get(fn)
    return f() if f else None


def _dd(n, x, C):
    """Ableitung mit Rückfall: ohne Regel die numerische Ableitung dieses Teilausdrucks."""
    try:
        return _d(n, x, C)
    except NoRule:
        t = text(n)
        if t not in C.numeric:
            C.numeric.append(t)
        return _call(NUMERIC, copy.deepcopy(n), _nm(x), _c(1))


def _d(n, x, C):
    if not has(n, x):
        return _c(0)
    t = type(n)
    if t is ast.Name:
        return _c(1)
    if t is ast.UnaryOp:
        if isinstance(n.op, ast.USub):
            return _neg(_dd(n.operand, x, C))
        if isinstance(n.op, ast.UAdd):
            return _dd(n.operand, x, C)
        raise NoRule
    if t is ast.BinOp:
        u, v = n.left, n.right
        op = type(n.op)
        if op in (ast.Add, ast.Sub):
            return _b(_dd(u, x, C), ast.Add() if op is ast.Add else ast.Sub(), _dd(v, x, C))
        if op in (ast.Mult, ast.MatMult):
            if not has(u, x):
                return _mul(u, _dd(v, x, C))
            if not has(v, x):
                return _mul(_dd(u, x, C), v)
            return _add(_mul(_dd(u, x, C), v), _mul(u, _dd(v, x, C)))
        if op is ast.Div:
            if not has(v, x):
                return _div(_dd(u, x, C), v)
            if not has(u, x):
                return _neg(_div(_mul(u, _dd(v, x, C)), _pow(v, _c(2))))
            return _div(_sub(_mul(_dd(u, x, C), v), _mul(u, _dd(v, x, C))), _pow(v, _c(2)))
        if op is ast.Pow:
            if not has(v, x):                              # Potenzregel: n·u^(n−1)·u'
                return _mul(_mul(v, _pow(u, _sub(v, _c(1)))), _dd(u, x, C))
            if not has(u, x):                              # a^v: a^v·ln(a)·v'
                if isinstance(u, ast.Name) and u.id == "e":
                    return _mul(_pow(u, v), _dd(v, x, C))
                return _mul(_mul(_pow(u, v), _call("ln", u)), _dd(v, x, C))
            return _mul(_pow(u, v), _add(_mul(_dd(v, x, C), _call("ln", u)), _div(_mul(v, _dd(u, x, C)), u)))
        raise NoRule
    if t is ast.IfExp:
        return ast.IfExp(test=n.test, body=_dd(n.body, x, C), orelse=_dd(n.orelse, x, C))
    if t is ast.Call and isinstance(n.func, ast.Name):
        return _dcall(n, x, C)
    raise NoRule


def _dcall(n, x, C):
    fn, a = n.func.id, n.args
    if fn == PRIME:
        return _dd(_prime(n, C), x, C)
    if fn == "diff" and len(a) in (2, 3) and isinstance(a[1], ast.Name):
        return _dd(_nth(a[0], a[1].id, _order(a[2]) if len(a) == 3 else 1, C), x, C)
    if fn == NUMERIC and len(a) == 3 and isinstance(a[1], ast.Name) and a[1].id == x:
        k = _order(a[2])
        if k < 2:                                          # numerisch bis zur 2. Ableitung (expr.deriv_est)
            return _call(NUMERIC, a[0], a[1], _c(k + 1))
        raise NoRule
    if fn in C.funcs:
        args, body = C.funcs[fn]
        if len(args) != len(a):
            raise E.CalcError(f"{fn} erwartet {len(args)} Argument(e)")
        C.depth += 1
        if C.depth > 30:
            raise E.CalcError(f"{fn}: zu tiefe Verschachtelung beim Ableiten")
        try:
            out = None
            for name, arg in zip(args, a):
                if not has(arg, x):
                    continue
                part = subst(_dd(body, name, C), dict(zip(args, a)))
                term = _mul(part, _dd(arg, x, C))
                out = term if out is None else _add(out, term)
            return out if out is not None else _c(0)
        finally:
            C.depth -= 1
    if fn in ("if", "if_") and len(a) == 3:
        return _call(fn, a[0], _dd(a[1], x, C), _dd(a[2], x, C))
    if fn == "integral" and len(a) == 4 and isinstance(a[1], ast.Name):
        tv = a[1].id
        if tv != x and has(a[0], x):
            raise NoRule                                   # Integrand hängt vom Parameter ab
        out = _c(0)                                        # Leibniz: f(b)·b' − f(a)·a'
        if has(a[3], x):
            out = _add(out, _mul(subst(a[0], {tv: a[3]}), _dd(a[3], x, C)))
        if has(a[2], x):
            out = _sub(out, _mul(subst(a[0], {tv: a[2]}), _dd(a[2], x, C)))
        return out
    if fn == "sum" and len(a) == 4 and isinstance(a[1], ast.Name) and a[1].id != x:
        if has(a[2], x) or has(a[3], x):
            raise NoRule
        return _call("sum", _dd(a[0], x, C), a[1], a[2], a[3])
    if fn == "log" and len(a) == 2:                        # log(u, b) = ln(u)/ln(b)
        return _dd(_div(_call("ln", a[0]), _call("ln", a[1])), x, C)
    if fn == "root" and len(a) == 2 and not has(a[1], x):
        return _dd(_pow(a[0], _div(_c(1), a[1])), x, C)
    if fn == "atan2" and len(a) == 2:                      # ∂/∂y = x/(x²+y²), ∂/∂x = −y/(x²+y²)
        y_, x_ = a
        r2 = _add(_pow(x_, _c(2)), _pow(y_, _c(2)))
        out = _div(_sub(_mul(x_, _dd(y_, x, C)), _mul(y_, _dd(x_, x, C))), r2)
        return _mul(out, _to_deg()) if C.deg else out
    if fn == "hypot" and len(a) == 2:
        return _div(_add(_mul(a[0], _dd(a[0], x, C)), _mul(a[1], _dd(a[1], x, C))), _call("hypot", a[0], a[1]))
    if len(a) == 1:
        outer = _outer(fn, a[0], C)
        if outer is not None:
            return _mul(outer, _dd(a[0], x, C))
    raise NoRule


def _order(node) -> int:
    v = _numval(node) if node is not None else Fraction(1)
    if v is None or float(v) != int(v) or not 1 <= int(v) <= MAX_ORDER:
        raise E.CalcError(f"Ordnung der Ableitung: ganze Zahl von 1 bis {MAX_ORDER}")
    return int(v)


def _nth(expr_node, x, k, C):
    d = expr_node
    for _ in range(k):
        d = simplify(_dd(d, x, C))
    return d


def _prime(n, C):
    """fprime_(f, k, u) -> k-te Ableitung von f, an der Stelle u (vereinfacht)."""
    a = n.args
    if len(a) < 3 or not isinstance(a[0], ast.Name):
        raise E.CalcError("f′(x): Funktionsname, dann das Argument in Klammern")
    f, k = a[0].id, _order(a[1])
    if f in C.funcs:
        args, body = C.funcs[f]
    elif f in E.BUILTINS:
        args, body = ["t_"], _call(f, _nm("t_"))
    else:
        raise E.CalcError(f"„{f}“ ist keine Funktion: zuerst {f}(x) = … definieren")
    if len(args) != 1 or len(a) != 3:
        raise E.CalcError(f"{f}′ gibt es nur für Funktionen einer Variablen; sonst diff({f}(…), x)")
    C.depth += 1
    if C.depth > 30:
        raise E.CalcError(f"{f}: zu tiefe Verschachtelung beim Ableiten")
    try:
        d = _nth(body, args[0], k, C)
    finally:
        C.depth -= 1
    return simplify(subst(d, {args[0]: a[2]}))


# ----------------------------------------------------------------------------- Öffentliche Aufrufe
def derivative(node, x, n=1, funcs=None, angle="rad"):
    """n-te Ableitung von node nach x -> (vereinfachter Ausdruck, Teilausdrücke ohne Regel (numerisch))."""
    C = _Ctx(funcs, angle)
    return _nth(node, x, _order(_c(n)), C), C.numeric


def expand(node, funcs=None, angle="rad"):
    """diff(…, x[, n]) und f'(x) im Ausdruck durch ihre symbolische Ableitung ersetzen.
    -> (neuer Ausdruck, Teilausdrücke, die numerisch abgeleitet werden)."""
    C = _Ctx(funcs, angle)

    def walk(n):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
            fn = n.func.id
            if fn == PRIME:
                args = list(n.args[:2]) + [walk(v) for v in n.args[2:]]
                return _prime(ast.Call(func=n.func, args=args, keywords=[]), C)
            args = [walk(v) for v in n.args]
            if fn == "diff" and len(args) in (2, 3) and isinstance(args[1], ast.Name):
                return _nth(args[0], args[1].id, _order(args[2]) if len(args) == 3 else 1, C)
            return ast.Call(func=n.func, args=args, keywords=[])
        for field, old in ast.iter_fields(n):
            if isinstance(old, list):
                setattr(n, field, [walk(v) if isinstance(v, ast.expr) else v for v in old])
            elif isinstance(old, ast.expr):
                setattr(n, field, walk(old))
        return n
    out = walk(copy.deepcopy(node))
    return out, C.numeric


_CACHE: dict = {}


def _funcs_key(funcs):
    return tuple(sorted((k, tuple(a), ast.dump(b)) for k, (a, b) in (funcs or {}).items()))


def cached(kind, node, funcs, angle, build):
    """Zwischenspeicher für die Auswertung (Grafik, Integrale rufen dieselbe Ableitung oft auf)."""
    key = (kind, ast.dump(node), angle, _funcs_key(funcs))
    hit = _CACHE.get(key)
    if hit is None:
        if len(_CACHE) > 512:
            _CACHE.clear()
        hit = build()
        _CACHE[key] = hit
    return hit


NUMERIC_NOTE = {"de": "Ableitung numerisch (zentrale Differenz), keine Regel für: {t}",
                "en": "derivative computed numerically (central difference), no rule for: {t}"}
