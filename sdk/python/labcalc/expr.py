"""Ausdruecke lesen und auswerten.

Schreibweise wie auf einem Taschenrechner: ``2x``, ``3(a+b)``, ``x^2``, ``5!``, ``A'`` (transponiert),
``[[1,2],[3,4]]`` (Matrix), ``f(x) = x^2``, ``v -> km/h``. Ausgewertet wird ein eingeschraenkter Python-AST mit
numpy, nie mit eval(). Alles laesst sich auch mit Arrays auswerten (Diagramme).
"""
from __future__ import annotations

import ast
import keyword
import math
import re

import numpy as np

from . import units as U


class CalcError(ValueError):
    pass


GREEK = {"α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "ε": "epsilon", "ζ": "zeta", "η": "eta",
         "θ": "theta", "ι": "iota", "κ": "kappa", "λ": "lambda", "μ": "mu", "ν": "nu", "ξ": "xi", "π": "pi",
         "ρ": "rho", "σ": "sigma", "τ": "tau", "φ": "phi", "χ": "chi", "ψ": "psi", "ω": "omega", "Δ": "Delta",
         "Ω": "Omega", "Φ": "Phi", "Σ": "Sigma", "Γ": "Gamma", "Λ": "Lambda", "Θ": "Theta", "Ψ": "Psi"}
_REPL = [("×", "*"), ("·", "*"), ("⋅", "*"), ("÷", "/"), ("−", "-"), ("√", "sqrt"), ("²", "^2"), ("³", "^3"),
         ("≤", "<="), ("≥", ">="), ("≠", "!="), ("∞", "inf")]

_TOK = re.compile(r"""
  (?P<num>(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)
 |(?P<name>[^\W\d]\w*)
 |(?P<str>"[^"]*")
 |(?P<op>\*\*|==|!=|<=|>=|[-+*/%^(),\[\]<>!'@:])
 |(?P<ws>\s+)
""", re.X)


def _tokens(src: str):
    out, pos = [], 0
    while pos < len(src):
        m = _TOK.match(src, pos)
        if not m:
            raise CalcError(f"Zeichen „{src[pos]}“ an Stelle {pos + 1} nicht erlaubt")
        pos = m.end()
        kind = m.lastgroup
        if kind != "ws":
            out.append((kind, m.group(kind)))
    return out


def _operand_start(out):
    """Index des Operanden, der vor einem nachgestellten Operator (!, ') steht."""
    if not out:
        raise CalcError("Operator ohne Operand")
    k, v = out[-1]
    if v in (")", "]"):
        opener = "(" if v == ")" else "["
        depth, i = 0, len(out) - 1
        while i >= 0:
            if out[i][1] == v:
                depth += 1
            elif out[i][1] == opener:
                depth -= 1
                if depth == 0:
                    break
            i -= 1
        if i < 0:
            raise CalcError("Klammern passen nicht")
        if i > 0 and out[i - 1][0] == "name":
            i -= 1
        return i
    if k in ("num", "name"):
        return len(out) - 1
    raise CalcError("Operator ohne Operand")


def preprocess(src: str, callables=frozenset()) -> str:
    """Rechnerschreibweise -> Python-Ausdruck (implizite Multiplikation, ^, !, ')."""
    s = str(src)
    for a, b in _REPL:
        s = s.replace(a, b)
    for g, n in GREEK.items():
        s = s.replace(g, f" {n} ")
    toks = _tokens(s)
    out = []
    skip = -1
    for ti, (kind, v) in enumerate(toks):
        if ti <= skip:
            continue
        prime = 0                                          # f'(x), f''(x): Ableitung einer Funktion (labcalc.deriv)
        if kind == "name" and v in callables and v not in SPECIAL and v not in STRFUNCS:
            j = ti + 1
            while j < len(toks) and toks[j] == ("op", "'"):
                j += 1
            if j > ti + 1 and j < len(toks) and toks[j] == ("op", "("):
                prime, fname, skip = j - ti - 1, v, j
                v = "fprime_"
        if kind == "name":
            if v in ("and", "or", "not"):
                kind = "op"
            elif keyword.iskeyword(v):
                v = v + "_"                                # lambda -> lambda_, if -> if_
        if v in ("!", "'"):
            i = _operand_start(out)
            out[i:i] = [("name", "fact" if v == "!" else "transpose"), ("op", "(")]
            out.append(("op", ")"))
            continue
        if out:
            pk, pv = out[-1]
            prev_operand = pk in ("num", "str", "name") or pv in (")", "]")
            starts_operand = kind in ("num", "name", "str") or v == "("
            if prev_operand and starts_operand:
                if pk == "name" and v == "(" and pv in callables:
                    pass                                   # Funktionsaufruf
                elif pk == "name" and v == "(" and pv in STRFUNCS and ti + 1 < len(toks) and toks[ti + 1][0] == "str":
                    pass                                   # M("H2O"): nur mit Formel in Anführungszeichen
                elif pk == "num" and kind == "num":
                    raise CalcError("Zwei Zahlen ohne Operator")
                else:
                    out.append(("op", "*"))
        out.append((kind, "**" if v == "^" else v))
        if prime:
            out += [("op", "("), ("name", fname), ("op", ","), ("num", str(prime)), ("op", ",")]
    return " ".join(v for _, v in out)


def norm_name(s: str) -> str:
    """Vom Benutzer eingegebenes Symbol -> interner Name (λ -> lambda_, Python-Schluesselwoerter mit _)."""
    s = re.sub(r"[\s\-]+", "_", str(s).strip())                # "Masse Auto" -> Masse_Auto
    s = GREEK.get(s, s) if len(s) == 1 else "".join(GREEK.get(ch, ch) for ch in s)
    if not re.fullmatch(r"[^\W\d]\w*", s):
        raise CalcError(f"„{s}“ ist kein gültiger Name (beginnt mit einem Buchstaben, dann Buchstaben, Ziffern, _)")
    return s + "_" if keyword.iskeyword(s) else s


def plain_name(s: str) -> str:
    """Interner Name -> Anzeigename ohne angehaengtes _ (lambda_ -> lambda)."""
    return s[:-1] if s.endswith("_") and keyword.iskeyword(s[:-1]) else s


def parse(src: str, callables=None) -> ast.AST:
    if callables is None:
        callables = frozenset(BUILTINS) | frozenset(SPECIAL)
    py = preprocess(src, callables)
    if not py.strip():
        raise CalcError("Leerer Ausdruck")
    try:
        return ast.parse(py, mode="eval").body
    except SyntaxError as e:
        raise CalcError(f"Ausdruck nicht lesbar: {src}") from e


_DVAR = "|".join(sorted(GREEK.values(), key=len, reverse=True)) + r"|[^\W\d_](?:_?\d+)?"
_DDX = re.compile(rf"(?<![\w.])d(?:\^?(?P<n>[2-9²³]))?\s*/\s*d(?P<v>{_DVAR})(?:\^?(?P<m>[2-9²³]))?(?=\s*\S)(?=\s|\()")


def _ddx_operand(s: str, i: int):
    """Operand ohne Klammer hinter d/dx: bis zum nächsten + oder − (nicht im Exponenten), Komma, = oder zur Klammer zu."""
    depth, k = 0, i
    while k < len(s):
        c = s[k]
        if c in "([":
            depth += 1
        elif c in ")]":
            if not depth:
                break
            depth -= 1
        elif not depth and c in ",;=<>":
            break
        elif not depth and c in "+-−":
            before = s[i:k].rstrip()
            if before and before[-1] not in "^*/·" and not re.search(r"\d[eE]$", before):
                break
        k += 1
    return k


def rewrite_ddx(src: str, known=()) -> str:
    """Handschriftliche Ableitung ``d/dx(x^3)``, ``d²/dx²(…)``, ``d/dx x^3`` -> ``diff(…, x[, n])``.

    Bleibt unverändert, wenn die Seite ``d`` oder ``dx`` selbst definiert (dann ist es ein Quotient)."""
    s, out, pos = str(src), [], 0
    while True:
        m = _DDX.search(s, pos)
        if not m:
            out.append(s[pos:])
            return "".join(out)
        var = m.group("v")
        same = (m.group("n") or "") == (m.group("m") or "")
        start = m.end() + len(s[m.end():]) - len(s[m.end():].lstrip())
        end = None
        if same and "d" not in known and "d" + var not in known and start < len(s):
            if s[start] == "(":
                depth = 0
                for k in range(start, len(s)):
                    depth += s[k] in "(["
                    depth -= s[k] in ")]"
                    if not depth:
                        body, end = s[start + 1:k], k + 1
                        break
            else:
                k = _ddx_operand(s, start)
                body = s[start:k].rstrip()
                end = start + len(body)
        if end is None or not body.strip():
            out.append(s[pos:m.end()])
            pos = m.end()
            continue
        order = {"²": "2", "³": "3"}.get(m.group("n"), m.group("n"))
        out.append(s[pos:m.start()] + f"diff({rewrite_ddx(body, known)}, {var}{', ' + order if order else ''})")
        pos = end


ASSIGN = re.compile(r"^\s*([^\W\d]\w*)\s*(\(([^()]*)\))?\s*(?<![<>=!])=(?!=)(.*)$", re.S)
# Zuweisung nach rechts, wie man rechnet: 50/3 = u  (der Name steht allein rechts vom einzigen =)
RASSIGN = re.compile(r"^\s*([^=]*[^\s<>=!])\s*=(?!=)\s*([^\W\d]\w*)\s*$", re.S)


def _top_split(s: str, sep: str):
    """s an sep teilen, aber nicht innerhalb von Klammern oder Anführungszeichen."""
    parts, cur, depth, quote = [], [], 0, False
    for ch in s:
        if ch == '"':
            quote = not quote
        elif not quote:
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth -= 1
            elif ch == sep and depth == 0:
                parts.append("".join(cur))
                cur = []
                continue
        cur.append(ch)
    parts.append("".join(cur))
    return parts


def eq_positions(s: str):
    """Stellen eines einzelnen = (nicht ==, <=, >=, !=) ausserhalb von Klammern."""
    out, depth, quote = [], 0, False
    for i, ch in enumerate(s):
        if ch == '"':
            quote = not quote
        elif quote:
            continue
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "=" and depth == 0:
            prev, nxt = s[i - 1] if i else "", s[i + 1] if i + 1 < len(s) else ""
            if prev not in "<>=!" and nxt != "=":
                out.append(i)
    return out


def split_statement(src: str):
    """-> ("assign", name, expr) | ("func", name, [args], body) | ("convert", expr, unit) | ("expr", expr)
    | ("equation", links, rechts, [Zusätze], Zieleinheit oder None) | ("system", [(links, rechts), …]).

    Zuweisung: ``u = 50/3`` oder nach rechts ``50/3 = u``. Gleichung (S-01): ``x^2 - 3 + x = 0``, mit Zusätzen nach
    Kommas: Bedingungen (``x > 0``) oder die gesuchte Grösse (``x``). System (S-02): Gleichungen mit ``;`` getrennt."""
    s = str(src).strip()
    for g, n in GREEK.items():
        s = s.replace(g, n)
    if ";" in s:
        parts = [p.strip() for p in _top_split(s, ";") if p.strip()]
        if len(parts) > 1:
            eqs = []
            for p in parts:
                pos = eq_positions(p)
                if len(pos) != 1:
                    raise CalcError("Gleichungssystem: jede Gleichung mit genau einem =, getrennt durch ;")
                eqs.append((p[:pos[0]].strip(), p[pos[0] + 1:].strip()))
            return ("system", eqs)
        s = parts[0] if parts else s
    unit = None
    if "->" in s:
        e, u = s.rsplit("->", 1)
        if eq_positions(e):
            s, unit = e.strip(), u.strip()
    parts = _top_split(s, ",")
    if len(parts) > 1 and len(eq_positions(parts[0])) == 1:
        p0 = parts[0]
        i = eq_positions(p0)[0]
        return ("equation", p0[:i].strip(), p0[i + 1:].strip(), [x.strip() for x in parts[1:] if x.strip()], unit)
    if unit is not None:
        pos = eq_positions(s)
        if len(pos) == 1:
            return ("equation", s[:pos[0]].strip(), s[pos[0] + 1:].strip(), [], unit)
    m = ASSIGN.match(s)
    if m:
        name, args, body = m.group(1), m.group(3), m.group(4).strip()
        if not body:
            raise CalcError("Nach dem = fehlt ein Ausdruck")
        if m.group(2) is not None:
            names = [a.strip() for a in args.split(",") if a.strip()]
            ok = all(re.fullmatch(r"[^\W\d]\w*", a) for a in names)
            if name in BUILTINS or name in SPECIAL or name in STRFUNCS or not ok:     # sin(x) = 0.5: Gleichung
                pos = eq_positions(s)
                if len(pos) == 1:
                    return ("equation", s[:pos[0]].strip(), s[pos[0] + 1:].strip(), [], None)
            if not ok:
                raise CalcError("Funktionsargumente müssen Namen sein")
            return ("func", name, names, body)
        return ("assign", name, body)
    m = RASSIGN.match(s)
    if m and "->" not in m.group(1):
        return ("assign", m.group(2), m.group(1).strip())
    if "->" in s:
        e, unit = s.rsplit("->", 1)
        return ("convert", e.strip(), unit.strip())
    pos = eq_positions(s)
    if len(pos) > 1:
        raise CalcError("Nur ein = je Gleichung – für ein Gleichungssystem die Gleichungen mit ; trennen")
    if pos:
        if not s[:pos[0]].strip() or not s[pos[0] + 1:].strip():
            raise CalcError("Auf beiden Seiten des = muss etwas stehen")
        return ("equation", s[:pos[0]].strip(), s[pos[0] + 1:].strip(), [], None)
    return ("expr", s)


# ----------------------------------------------------------------------------- Kontext
class Ctx:
    def __init__(self, names=None, funcs=None, angle="rad", complex_ok=False, dims=None):
        self.names = dict(names or {})
        self.funcs = dict(funcs or {})        # name -> (args, ast)
        self.angle = angle
        self.complex_ok = complex_ok
        self.dims = dict(dims or {})
        self.depth = 0
        self.notes = []                       # Hinweise der Analysis-Funktionen (Integral-/Ableitungsgenauigkeit)

    def note(self, text):
        if text not in self.notes:
            self.notes.append(text)

    @property
    def aconv(self):
        return math.pi / 180 if self.angle == "deg" else 1.0

    def callables(self):
        return frozenset(BUILTINS) | frozenset(SPECIAL) | frozenset(self.funcs)


def _arr(v):
    return np.asarray(v)


def _num(v):
    a = np.asarray(v)
    if a.dtype == object or a.dtype.kind in "US":
        raise CalcError("Zahl erwartet")
    return a


def _mul(a, b):
    A, B = np.asarray(a), np.asarray(b)
    if A.ndim == 2 or B.ndim == 2:
        if A.ndim >= 1 and B.ndim >= 1:
            try:
                return A @ B
            except ValueError as e:
                raise CalcError(f"Matrixprodukt: Grössen {A.shape} und {B.shape} passen nicht") from e
    return a * b


def _div(a, b):
    B = np.asarray(b)
    if B.ndim == 2:
        return _mul(a, np.linalg.inv(B))
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.true_divide(a, b)


def _pow(a, b, ctx):
    A = np.asarray(a)
    if A.ndim == 2:
        if np.ndim(b) == 0 and float(b) == int(b):
            return np.linalg.matrix_power(A, int(b))
        raise CalcError("Matrixpotenz nur mit ganzzahligem Exponenten")
    if ctx.complex_ok and np.ndim(a) == 0 and np.ndim(b) == 0 and np.isreal(a) and np.real(a) < 0 \
            and float(np.real(b)) != int(np.real(b)):
        return complex(a) ** complex(b)
    with np.errstate(all="ignore"):
        return np.power(np.asarray(a, dtype=complex if np.iscomplexobj(a) or np.iscomplexobj(b) else float), b)


_BIN = {ast.Add: lambda a, b, c: np.add(a, b), ast.Sub: lambda a, b, c: np.subtract(a, b),
        ast.Mult: lambda a, b, c: _mul(a, b), ast.Div: lambda a, b, c: _div(a, b),
        ast.Pow: _pow, ast.Mod: lambda a, b, c: np.mod(a, b), ast.MatMult: lambda a, b, c: np.asarray(a) @ np.asarray(b),
        ast.FloorDiv: lambda a, b, c: np.floor_divide(a, b)}
_CMP = {ast.Eq: np.equal, ast.NotEq: np.not_equal, ast.Lt: np.less, ast.LtE: np.less_equal, ast.Gt: np.greater,
        ast.GtE: np.greater_equal}


def evaluate(node, ctx: Ctx, local=None):
    local = local or {}
    t = type(node)
    if t is ast.Constant:
        if isinstance(node.value, (int, float, complex)) and not isinstance(node.value, bool):
            return float(node.value) if isinstance(node.value, int) else node.value
        if isinstance(node.value, str):
            return node.value
        raise CalcError("Wert nicht erlaubt")
    if t is ast.Name:
        n = node.id
        if n in local:
            return local[n]
        if n in ctx.names:
            return ctx.names[n]
        if n in U.CONSTANTS:
            return U.CONSTANTS[n][0]
        if n == "inf":
            return math.inf
        if n == "nan":
            return math.nan
        if n in ("i", "j"):
            return 1j
        if n in BUILTINS or n in SPECIAL or n in ctx.funcs:
            raise CalcError(f"„{n}“ ist eine Funktion und braucht Klammern: {n}(…)")
        raise CalcError(f"Unbekannter Name „{n}“")
    if t is ast.BinOp:
        f = _BIN.get(type(node.op))
        if not f:
            raise CalcError("Operator nicht erlaubt")
        return f(evaluate(node.left, ctx, local), evaluate(node.right, ctx, local), ctx)
    if t is ast.UnaryOp:
        v = evaluate(node.operand, ctx, local)
        if isinstance(node.op, ast.USub):
            return np.negative(v)
        if isinstance(node.op, ast.UAdd):
            return v
        if isinstance(node.op, ast.Not):
            return np.logical_not(v)
        raise CalcError("Operator nicht erlaubt")
    if t is ast.Compare:
        left = evaluate(node.left, ctx, local)
        res = None
        for op, comp in zip(node.ops, node.comparators):
            right = evaluate(comp, ctx, local)
            f = _CMP.get(type(op))
            if not f:
                raise CalcError("Vergleich nicht erlaubt")
            if not isinstance(op, (ast.Eq, ast.NotEq)) and (np.iscomplexobj(left) or np.iscomplexobj(right)):
                left, right = real_values(left, "Vergleich"), real_values(right, "Vergleich")     # z > 1 hat keine Ordnung
            r = f(left, right)
            res = r if res is None else np.logical_and(res, r)
            left = right
        return res
    if t is ast.BoolOp:
        vals = [evaluate(v, ctx, local) for v in node.values]
        f = np.logical_and if isinstance(node.op, ast.And) else np.logical_or
        r = vals[0]
        for v in vals[1:]:
            r = f(r, v)
        return r
    if t in (ast.List, ast.Tuple):
        items = [evaluate(e, ctx, local) for e in node.elts]
        try:
            a = np.array(items, dtype=complex if any(np.iscomplexobj(x) for x in items) else float)
        except (ValueError, TypeError) as e:
            raise CalcError("Zeilen einer Matrix müssen gleich lang sein") from e
        return a
    if t is ast.Subscript:
        base = np.asarray(evaluate(node.value, ctx, local))
        sl = node.slice
        idx = [evaluate(e, ctx, local) for e in sl.elts] if isinstance(sl, ast.Tuple) else [evaluate(sl, ctx, local)]
        try:
            ii = tuple(int(round(float(k))) - 1 for k in idx)
            if any(k < 0 for k in ii):
                raise IndexError
            return base[ii]
        except (IndexError, TypeError) as e:
            raise CalcError(f"Index {', '.join(str(int(float(k))) for k in idx)} ausserhalb von {base.shape} (Zählung ab 1)") from e
    if t is ast.Call:
        if not isinstance(node.func, ast.Name):
            raise CalcError("Nur benannte Funktionen erlaubt")
        name = node.func.id
        if node.keywords:
            raise CalcError("Benannte Argumente sind nicht erlaubt")
        if name in local and callable(local[name]):
            return local[name](*[evaluate(a, ctx, local) for a in node.args])
        if name in ctx.funcs:
            args, body = ctx.funcs[name]
            if len(node.args) != len(args):
                raise CalcError(f"{name} erwartet {len(args)} Argument(e)")
            vals = [evaluate(a, ctx, local) for a in node.args]
            ctx.depth += 1
            if ctx.depth > 60:
                raise CalcError(f"{name}: zu tiefe Verschachtelung (Rekursion?)")
            try:
                return evaluate(body, ctx, {**local, **dict(zip(args, vals))})
            finally:
                ctx.depth -= 1
        if name in SPECIAL:
            return SPECIAL[name](node.args, ctx, local)
        if name in STRFUNCS and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            fn, nmin, nmax = STRFUNCS[name][:3]
            if not (nmin <= len(node.args) <= nmax):
                raise CalcError(f"{name} erwartet {nmin if nmin == nmax else f'{nmin} bis {nmax}'} Argument(e)")
            args = [evaluate(a, ctx, local) for a in node.args]
            try:
                return fn(ctx, *args)
            except ValueError as e:
                raise CalcError(str(e)) from e
        if name in BUILTINS:
            fn, nmin, nmax = BUILTINS[name]
            if not (nmin <= len(node.args) <= nmax):
                need = str(nmin) if nmin == nmax else f"{nmin} bis {nmax}" if nmax < 99 else f"mindestens {nmin}"
                raise CalcError(f"{name} erwartet {need} Argument(e)")
            args = [evaluate(a, ctx, local) for a in node.args]
            if name in _REAL_ONLY:                            # komplexe Werte: klare Meldung statt abgeschnittenem Imaginärteil
                args = [real_values(a, name) if np.iscomplexobj(a) else a for a in args]
            with np.errstate(all="ignore"):
                try:
                    return fn(ctx, *args)
                except np.linalg.LinAlgError as e:
                    raise CalcError(f"{name}: {_linalg_msg(e)}") from e
        raise CalcError(f"Unbekannte Funktion „{name}“")
    if t is ast.IfExp:
        c = evaluate(node.test, ctx, local)
        return np.where(c, evaluate(node.body, ctx, local), evaluate(node.orelse, ctx, local))
    raise CalcError(f"Ausdruck nicht erlaubt ({t.__name__})")


def _linalg_msg(e):
    s = str(e)
    return "Matrix ist singulär (nicht invertierbar)" if "ingular" in s else s


# ----------------------------------------------------------------------------- Funktionen
def _trig(f):
    return lambda c, x: f(np.asarray(x) * c.aconv)


def _atrig(f, cplx=None):
    def g(c, x):
        if c.complex_ok and cplx is not None and np.ndim(x) == 0 and np.isreal(x) and abs(float(np.real(x))) > 1:
            return cplx(x) / c.aconv
        return f(x) / c.aconv
    return g


def _maybe_c(f, cplx):
    def g(c, x):
        if c.complex_ok and np.ndim(x) == 0 and np.isreal(x) and float(np.real(x)) < 0:
            return cplx(x)
        return f(x)
    return g


def real_values(x, what="Diese Funktion"):
    """Werte als reelles Feld; ein echter Imaginärteil ist ein Fehler (numpy würde ihn sonst stillschweigend abschneiden)."""
    a = np.asarray(x)
    if np.iscomplexobj(a):
        if np.any(np.abs(a.imag) > 1e-12 * np.maximum(1, np.abs(a.real))):
            raise CalcError(f"{what}: nur für reelle Werte, hier sind sie komplex")
        a = a.real
    return np.asarray(a, dtype=float)


_REAL_ONLY = {"atan2", "cbrt", "ceil", "floor", "deg", "rad", "hypot", "mod", "gcd", "lcm", "nPr", "min", "max", "median",
              "eye", "identity", "zeros", "ones", "rand", "seq", "range", "linspace", "interp"}


def _number(z):
    """Zahl aus det, trace: reell, wenn der Imaginärteil nur Rundungsrauschen ist, sonst komplex."""
    z = np.real_if_close(z)
    return complex(z) if np.iscomplexobj(z) else float(z)


def _root(c, x, n):
    n = real_values(n, "root")
    if np.iscomplexobj(x):
        return np.power(x, 1 / n)                         # Hauptwert
    return np.sign(x) * np.abs(x) ** (1 / n) if np.all(np.mod(n, 2) == 1) else np.power(x, 1 / n)


def _gamma(x):
    a = real_values(x, "gamma")
    if a.ndim == 0:
        v = float(a)
        if v < 0 and v == int(v):
            return math.nan
        try:
            return math.gamma(v)
        except OverflowError:
            return math.inf
    return np.vectorize(lambda v: math.nan if (v < 0 and v == int(v)) else math.gamma(v) if v < 171 else math.inf)(a)


def _erf(x):
    v = np.vectorize(math.erf, otypes=[float])(real_values(x, "erf"))
    return float(v) if v.ndim == 0 else v


def _fact(c, n):
    a = real_values(n, "Fakultät")
    if np.any(a < 0):
        raise CalcError("Fakultät nur für n ≥ 0")
    return _gamma(a + 1)


def _binom(c, n, k):
    n, k = real_values(n, "binom"), real_values(k, "binom")
    return np.round(_gamma(n + 1) / (_gamma(k + 1) * _gamma(n - k + 1)))


def _agg(fn):
    def g(c, *args):
        if len(args) == 1:
            return fn(np.asarray(args[0]))
        return fn(np.asarray([np.asarray(a) for a in args]), axis=0) if fn in (np.min, np.max) else fn(np.asarray(args))
    return g


def _vec(x):
    return real_values(x).ravel()


def _rref(c, A):
    M = np.array(real_values(A, "rref"), dtype=float)
    if M.ndim != 2:
        raise CalcError("rref braucht eine Matrix")
    r = 0
    rows, cols = M.shape
    for col in range(cols):
        if r >= rows:
            break
        p = r + int(np.argmax(np.abs(M[r:, col])))
        if abs(M[p, col]) < 1e-12:
            continue
        M[[r, p]] = M[[p, r]]
        M[r] = M[r] / M[r, col]
        for i in range(rows):
            if i != r:
                M[i] -= M[i, col] * M[r]
        r += 1
    M[np.abs(M) < 1e-12] = 0.0
    return M


def _linreg(c, x, y):
    x, y = _vec(x), _vec(y)
    if x.size != y.size or x.size < 2:
        raise CalcError("linreg: x und y gleich lang, mindestens 2 Werte")
    k, d = np.polyfit(x, y, 1)
    yhat = k * x + d
    ss = np.sum((y - y.mean()) ** 2)
    r2 = 1 - np.sum((y - yhat) ** 2) / ss if ss > 0 else 1.0
    return np.array([k, d, r2])


def _seq(c, a, b, step=1.0):
    if step == 0 or (b - a) / step > 1e6:
        raise CalcError("seq: Schrittweite ungültig oder zu viele Werte")
    return np.arange(a, b + step * 1e-9, step, dtype=float)


def _convert(c, v, a, b):
    if not isinstance(a, str) or not isinstance(b, str):
        raise CalcError('convert(Wert, "von", "nach") – Einheiten in Anführungszeichen')
    (a, da), (b, db) = U.split_delta(a), U.split_delta(b)
    diff = da or db                                # "Δ°C": Temperaturdifferenz, ohne Nullpunktverschiebung
    U.parse_unit(a)
    U.parse_unit(b)
    if not U.compatible(a, b):                     # auch: Skalen wie pH, dB, NTU nur in sich selbst
        raise CalcError(f"{a} und {b} passen nicht zusammen")
    return U.from_si(U.to_si(real_values(v, "convert"), a, diff), b, diff)


def _size(c, A):
    s = np.shape(A)
    return np.array(s if s else (1,), dtype=float)


def _idx(c, A, k, axis):
    A = np.asarray(A)
    if A.ndim != 2:
        raise CalcError("braucht eine Matrix")
    i = int(round(float(k))) - 1
    if not 0 <= i < A.shape[axis]:
        raise CalcError("Index ausserhalb der Matrix (Zählung ab 1)")
    return A[i] if axis == 0 else A[:, i]


def _sq(A):
    A = np.asarray(A)
    if A.ndim != 2 or A.shape[0] != A.shape[1]:
        raise CalcError("braucht eine quadratische Matrix")
    return A


def _cofactors(A):
    """Kofaktormatrix C_ij = (−1)^(i+j)·det(A ohne Zeile i und Spalte j); adj(A) = Cᵀ, auch für singuläre A.
    Ganzzahlige Matrizen geben ganzzahlige Kofaktoren (Rundung der Determinanten der Minoren)."""
    M = np.asarray(_sq(A))
    n = M.shape[0]
    if n == 1:
        return np.array([[1.0]])
    Cm = np.empty(M.shape, dtype=complex if np.iscomplexobj(M) else float)
    for i in range(n):
        for j in range(n):
            minor = np.delete(np.delete(M, i, axis=0), j, axis=1)
            Cm[i, j] = (-1) ** (i + j) * np.linalg.det(minor)
    if not np.iscomplexobj(M) and np.all(np.isfinite(M)) and np.all(M == np.round(M)):
        Cm = np.round(Cm)
    return Cm


def _real_if_close(v):
    a = np.asarray(v)
    if np.iscomplexobj(a) and np.all(np.abs(a.imag) <= 1e-12 * np.maximum(1, np.abs(a.real))):
        return a.real
    return a


BUILTINS = {
    "sin": (_trig(np.sin), 1, 1), "cos": (_trig(np.cos), 1, 1), "tan": (_trig(np.tan), 1, 1),
    "cot": (lambda c, x: 1 / np.tan(np.asarray(x) * c.aconv), 1, 1),
    "asin": (_atrig(np.arcsin, lambda x: np.emath.arcsin(x)), 1, 1),
    "acos": (_atrig(np.arccos, lambda x: np.emath.arccos(x)), 1, 1),
    "atan": (_atrig(np.arctan), 1, 1), "atan2": (lambda c, y, x: np.arctan2(y, x) / c.aconv, 2, 2),
    "sinh": (lambda c, x: np.sinh(x), 1, 1), "cosh": (lambda c, x: np.cosh(x), 1, 1), "tanh": (lambda c, x: np.tanh(x), 1, 1),
    "asinh": (lambda c, x: np.arcsinh(x), 1, 1), "acosh": (lambda c, x: np.arccosh(x), 1, 1), "atanh": (lambda c, x: np.arctanh(x), 1, 1),
    "sqrt": (_maybe_c(np.sqrt, lambda x: np.emath.sqrt(x)), 1, 1), "cbrt": (lambda c, x: np.cbrt(x), 1, 1),
    "root": (_root, 2, 2),
    "exp": (lambda c, x: np.exp(x), 1, 1), "ln": (_maybe_c(np.log, lambda x: np.emath.log(x)), 1, 1),
    "log": (lambda c, x, b=10.0: np.log(x) / np.log(b), 1, 2), "log10": (lambda c, x: np.log10(x), 1, 1),
    "log2": (lambda c, x: np.log2(x), 1, 1), "abs": (lambda c, x: np.abs(x), 1, 1), "sign": (lambda c, x: np.sign(x), 1, 1),
    "floor": (lambda c, x: np.floor(x), 1, 1), "ceil": (lambda c, x: np.ceil(x), 1, 1),
    "round": (lambda c, x, n=0: np.round(x, int(n)), 1, 2), "mod": (lambda c, a, b: np.mod(a, b), 2, 2),
    "gcd": (lambda c, a, b: np.gcd(np.asarray(a, int), np.asarray(b, int)).astype(float), 2, 2),
    "lcm": (lambda c, a, b: np.lcm(np.asarray(a, int), np.asarray(b, int)).astype(float), 2, 2),
    "fact": (_fact, 1, 1), "factorial": (_fact, 1, 1), "gamma": (lambda c, x: _gamma(x), 1, 1),
    "erf": (lambda c, x: _erf(x), 1, 1), "erfc": (lambda c, x: 1.0 - _erf(x), 1, 1),          # Fick 2 (Diffusion)
    "binom": (_binom, 2, 2), "nCr": (_binom, 2, 2), "nPr": (lambda c, n, k: np.round(_gamma(np.asarray(n, float) + 1) / _gamma(np.asarray(n, float) - k + 1)), 2, 2),
    "deg": (lambda c, x: np.degrees(x), 1, 1), "rad": (lambda c, x: np.radians(x), 1, 1),
    "hypot": (lambda c, a, b: np.hypot(a, b), 2, 2),
    "re": (lambda c, z: np.real(z), 1, 1), "im": (lambda c, z: np.imag(z), 1, 1), "conj": (lambda c, z: np.conj(z), 1, 1),
    "arg": (lambda c, z: np.angle(z) / c.aconv, 1, 1),
    # Statistik und Listen
    "mean": (_agg(np.mean), 1, 99), "median": (_agg(np.median), 1, 99),
    "std": (lambda c, *a: np.std(_vec(a[0] if len(a) == 1 else a), ddof=1), 1, 99),
    "var": (lambda c, *a: np.var(_vec(a[0] if len(a) == 1 else a), ddof=1), 1, 99),
    "min": (_agg(np.min), 1, 99), "max": (_agg(np.max), 1, 99), "sort": (lambda c, x: np.sort(_vec(x)), 1, 1),
    "len": (lambda c, x: float(np.size(x)), 1, 1), "cumsum": (lambda c, x: np.cumsum(x), 1, 1),
    "trapz": (lambda c, y, x=None: np.trapezoid(_vec(y), None if x is None else _vec(x)) if hasattr(np, "trapezoid") else np.trapz(_vec(y), None if x is None else _vec(x)), 1, 2),
    "linreg": (_linreg, 2, 2), "polyfit": (lambda c, x, y, n: np.polyfit(_vec(x), _vec(y), int(n)), 3, 3),
    "polyval": (lambda c, p, x: np.polyval(_vec(p), x), 2, 2), "roots": (lambda c, p: _real_if_close(np.roots(_vec(p))), 1, 1),
    "interp": (lambda c, x, xs, ys: np.interp(x, _vec(xs), _vec(ys)), 3, 3),
    "seq": (_seq, 2, 3), "range": (_seq, 2, 3), "linspace": (lambda c, a, b, n=50: np.linspace(a, b, int(n)), 2, 3),
    "rand": (lambda c, n=1: np.random.default_rng().random(int(n)) if int(n) > 1 else float(np.random.default_rng().random()), 0, 1),
    # Matrizen
    "det": (lambda c, A: _number(np.linalg.det(_sq(A))), 1, 1), "inv": (lambda c, A: np.linalg.inv(_sq(A)), 1, 1),
    "adj": (lambda c, A: _cofactors(A).T, 1, 1), "adjugate": (lambda c, A: _cofactors(A).T, 1, 1),
    "cof": (lambda c, A: _cofactors(A), 1, 1),
    "transpose": (lambda c, A: np.asarray(A).T if np.ndim(A) == 2 else np.asarray(A).reshape(-1, 1) if np.ndim(A) == 1 else A, 1, 1),
    "trace": (lambda c, A: _number(np.trace(_sq(A))), 1, 1), "rank": (lambda c, A: float(np.linalg.matrix_rank(np.asarray(A))), 1, 1),
    "eig": (lambda c, A: _real_if_close(np.linalg.eigvals(_sq(A))), 1, 1),
    "eigvec": (lambda c, A: _real_if_close(np.linalg.eig(_sq(A))[1]), 1, 1),
    "svd": (lambda c, A: np.linalg.svd(real_values(A, "svd"), compute_uv=False), 1, 1),
    "norm": (lambda c, A, p=2.0: float(np.linalg.norm(np.asarray(A), ord=None if p == 2 and np.ndim(A) == 1 else ("fro" if p == 2 else p))), 1, 2),
    "dot": (lambda c, a, b: np.dot(_vec(a), _vec(b)), 2, 2), "cross": (lambda c, a, b: np.cross(_vec(a), _vec(b)), 2, 2),
    "eye": (lambda c, n: np.eye(int(n)), 1, 1), "identity": (lambda c, n: np.eye(int(n)), 1, 1),
    "zeros": (lambda c, m, n=None: np.zeros((int(m), int(n if n is not None else m))), 1, 2),
    "ones": (lambda c, m, n=None: np.ones((int(m), int(n if n is not None else m))), 1, 2),
    "diag": (lambda c, v: np.diag(np.asarray(v)), 1, 1), "rref": (_rref, 1, 1),
    "linsolve": (lambda c, A, b: np.linalg.solve(_sq(A), np.asarray(b)), 2, 2),
    "pinv": (lambda c, A: np.linalg.pinv(real_values(A, "pinv")), 1, 1),
    "cond": (lambda c, A: float(np.linalg.cond(real_values(A, "cond"))), 1, 1),
    "size": (_size, 1, 1), "row": (lambda c, A, i: _idx(c, A, i, 0), 2, 2), "col": (lambda c, A, j: _idx(c, A, j, 1), 2, 2),
    "kron": (lambda c, A, B: np.kron(A, B), 2, 2),
    # Einheiten
    "convert": (_convert, 3, 3),
}


# ----------------------------------------------------------------------------- Sonderformen (Variable bleibt symbolisch)
def _var_name(node, fn):
    if not isinstance(node, ast.Name):
        raise CalcError(f"{fn}: das zweite Argument ist die Variable, z. B. {fn}(x^2, x, …)")
    return node.id


def _fn_of(node, var, ctx, local):
    def f(x):
        v = evaluate(node, ctx, {**local, var: x})
        return real_values(v, "Integral, Reihe, Ableitung und nsolve") if np.iscomplexobj(v) else v    # rechnen reell
    return f


def _refuse_complex(f, *points):
    """Integral und Ableitung fangen Fehler im Verfahren ab: ein komplexer Integrand wird vorher klar gemeldet."""
    for x in points:
        try:
            f(np.ravel(x)[0] if np.ndim(x) else x)
        except CalcError as e:
            if "komplex" in str(e):
                raise
        except Exception:                                 # alles andere meldet das Verfahren selbst
            pass


def _vectorized(f, X):
    try:
        Y = np.asarray(f(X), dtype=float)
        if Y.shape == np.shape(X):
            return Y
        if Y.ndim == 0:
            return np.full(np.shape(X), float(Y))
    except (CalcError, TypeError, ValueError):
        pass
    return np.array([float(np.real(f(float(x)))) for x in np.ravel(X)]).reshape(np.shape(X))


# Gauss–Kronrod 7/15 (Knoten und Gewichte wie QUADPACK qk15; Piessens et al. 1983). Geprüft im Test: K15 exakt
# für Polynome bis Grad 22, G7 sind die Gauss-Legendre-Knoten n = 7.
_XK = [0.991455371120812639206854697526329, 0.949107912342758524526189684047851, 0.864864423359769072789712788640926,
       0.741531185599394439863864773280788, 0.586087235467691130294144845693013, 0.405845151377397166906606412076961,
       0.207784955007898467600689403773245]
_WK = [0.022935322010529224963732008058970, 0.063092092629978553290700663189204, 0.104790010322250183839876322541518,
       0.140653259715525918745189590510238, 0.169004726639267902826583426598550, 0.190350578064785409913256402421014,
       0.204432940075298892414161999234649]
_WK0 = 0.209482141084727828012999174891714
_WG = [0.129484966168869693270611432679082, 0.279705391489276667901467771423780, 0.381830050505118944950369775488975]
_WG0 = 0.417959183673469387755102040816327
GK_X = np.array([-x for x in _XK] + [0.0] + _XK[::-1])
GK_W = np.array(_WK + [_WK0] + _WK[::-1])
G7_W = np.array([0.0, _WG[0], 0.0, _WG[1], 0.0, _WG[2], 0.0, _WG0, 0.0, _WG[2], 0.0, _WG[1], 0.0, _WG[0], 0.0])

QUAD_RTOL = 1e-10            # Ziel: geschätzter Fehler ≤ 1e-10·|I| (bzw. 50·eps·∫|f|)
QUAD_ACCEPT = 1e-6           # darüber wird kein Wert ausgegeben, sondern ein Fehler gemeldet
QUAD_LIMIT = 2000            # höchstens so viele Teilintervalle
QUAD_START = 16              # gleich breite Startintervalle


class QuadResult(float):
    """Integralwert mit Fehlerschätzung (.err) und Konvergenzangabe (.converged)."""
    err = 0.0
    converged = True


def _eval_points(f, X):
    """f an den Stellen X (beliebige Form); nicht berechenbare Stellen werden NaN."""
    X = np.asarray(X, dtype=float)
    try:
        with np.errstate(all="ignore"):
            Y = np.asarray(f(X.ravel()))                  # eindimensional: kein Matrixprodukt in _mul
        if Y.shape == (X.size,) and not np.iscomplexobj(Y) and Y.dtype.kind in "fiub":
            return Y.astype(float).reshape(X.shape)
        if Y.ndim == 0 and not np.iscomplexobj(Y) and Y.dtype.kind in "fiub":
            return np.full(X.shape, float(Y))
    except (CalcError, TypeError, ValueError, ZeroDivisionError, OverflowError, IndexError):
        pass
    out = np.empty(X.size)
    for i, x in enumerate(X.ravel()):
        try:
            with np.errstate(all="ignore"):
                z = complex(np.asarray(f(float(x))))
            out[i] = z.real if abs(z.imag) <= 1e-12 * max(1.0, abs(z.real)) else math.nan
        except (CalcError, TypeError, ValueError, ZeroDivisionError, OverflowError, IndexError):
            out[i] = math.nan
    return out.reshape(X.shape)


def _gk15(f, lo, hi):
    """Gauss–Kronrod auf den Intervallen [lo_i, hi_i]: (K15-Werte, |K15 − G7|, ∫|f| nach K15)."""
    c, h = (lo + hi) / 2, (hi - lo) / 2
    X = c[:, None] + h[:, None] * GK_X[None, :]
    Y = _eval_points(f, X)
    if not np.all(np.isfinite(Y)):
        raise CalcError("Integral: der Integrand ist im Intervall nicht endlich (oder nicht definiert)")
    k = h * (Y @ GK_W)
    g = h * (Y @ G7_W)
    return k, np.abs(k - g), np.abs(h) * (np.abs(Y) @ GK_W)


def _adapt(f, a, b):
    """Global adaptive Unterteilung (Halbierung der Intervalle mit dem grössten Fehler, wie QUADPACK QAG, ohne
    Extrapolation). -> (Wert, Fehlerschätzung, konvergiert?)."""
    edges = np.linspace(a, b, QUAD_START + 1)
    lo, hi = edges[:-1], edges[1:]
    val, err, absv = _gk15(f, lo, hi)
    while True:
        tot, etot, rabs = float(np.sum(val)), float(np.sum(err)), float(np.sum(absv))
        goal = max(QUAD_RTOL * abs(tot), 50 * np.finfo(float).eps * rabs)
        if etot <= goal:
            return tot, etot, True
        if lo.size >= QUAD_LIMIT:
            return tot, etot, False
        width = hi - lo
        can = width > 64 * np.finfo(float).eps * np.maximum(np.abs(lo), np.abs(hi))
        order = np.argsort(-np.where(can, err, -1.0))
        pick = [i for i in order[:min(64, QUAD_LIMIT - lo.size)] if can[i] and err[i] > goal / lo.size]
        if not pick:
            pick = [i for i in order[:1] if can[i]]
        if not pick:                                       # nichts mehr teilbar (Intervalle auf Rundungsbreite)
            return tot, etot, False
        pick = np.array(pick)
        mid = (lo[pick] + hi[pick]) / 2
        nlo = np.concatenate([lo[pick], mid])
        nhi = np.concatenate([mid, hi[pick]])
        nv, ne, na = _gk15(f, nlo, nhi)
        keep = np.ones(lo.size, dtype=bool)
        keep[pick] = False
        lo, hi = np.concatenate([lo[keep], nlo]), np.concatenate([hi[keep], nhi])
        val, err, absv = np.concatenate([val[keep], nv]), np.concatenate([err[keep], ne]), np.concatenate([absv[keep], na])


def quad_est(f, a, b):
    """Integral von f über [a, b] (auch unendliche Grenzen): adaptives Gauss–Kronrod 7/15 mit Fehlerschätzung.
    -> (Wert, Fehlerschätzung, konvergiert?). Unendliche Grenzen: x = a + t/(1 − t), dx = dt/(1 − t)², t in [0, 1]."""
    a, b = float(a), float(b)
    if a == b:
        return 0.0, 0.0, True
    if a > b:
        v, e, ok = quad_est(f, b, a)
        return -v, e, ok
    if math.isinf(a) and math.isinf(b):
        v1, e1, ok1 = quad_est(f, -math.inf, 0.0)
        v2, e2, ok2 = quad_est(f, 0.0, math.inf)
        return v1 + v2, e1 + e2, ok1 and ok2
    with np.errstate(all="ignore"):
        if math.isinf(b):
            return _adapt(lambda t: f(a + t / (1 - t)) / (1 - t) ** 2, 0.0, 1.0)
        if math.isinf(a):
            return _adapt(lambda t: f(b - t / (1 - t)) / (1 - t) ** 2, 0.0, 1.0)
        return _adapt(f, a, b)


def quad(f, a, b, ctx=None):
    """Integralwert (QuadResult mit .err). Ist der geschätzte Fehler grösser als QUAD_ACCEPT·|I| (bzw.
    QUAD_ACCEPT·∫|f| bei I ≈ 0), wird kein Wert ausgegeben (CalcError); liegt er zwischen dem Ziel und dieser Grenze,
    gibt es einen Hinweis in ctx.notes."""
    v, e, ok = quad_est(f, a, b)
    if not math.isfinite(v):
        raise CalcError("Integral: der Integrand ist im Intervall nicht endlich")
    scale = max(abs(v), 1e-300)
    if not ok and not e <= QUAD_ACCEPT * scale:
        raise CalcError(f"Integral konvergiert numerisch nicht (Schätzwert {fmt_num(v, 6)}, geschätzter Fehler "
                        f"{fmt_num(e, 2)}): der Integrand oszilliert oder ist singulär. Bei unendlichen Grenzen eine "
                        "endliche Grenze wählen, bei Singularitäten das Intervall teilen.")
    if not ok and ctx is not None:
        ctx.note(f"Integral: geschätzter relativer Fehler {fmt_num(e / scale, 2)} (Ziel {fmt_num(QUAD_RTOL, 1)} "
                 "nicht erreicht)")
    r = QuadResult(v)
    r.err, r.converged = e, ok
    return r


def _sp_integral(args, ctx, local):
    if len(args) != 4:
        raise CalcError("integral(Ausdruck, x, a, b)")
    var = _var_name(args[1], "integral")
    f = _fn_of(args[0], var, ctx, local)
    a, b = evaluate(args[2], ctx, local), evaluate(args[3], ctx, local)
    _refuse_complex(f, a, np.add(a, b) / 2)               # die Mitte: z*x ist bei x = 0 noch reell
    if np.ndim(a) or np.ndim(b):
        A, B = np.broadcast_arrays(np.asarray(a, float), np.asarray(b, float))
        return np.vectorize(lambda x, y: float(quad(f, x, y, ctx)))(A, B)
    return float(quad(f, a, b, ctx))


# Numerische Ableitung: Stufenleiter h_k = h_max·10^(−k/2) von h_max = 0,1·max(|x0|, 1) bis 1e-9·min(|x0|, 1)
# (relativer Schritt, auch für kleine |x0|). Je Stufe zentraler Differenzenquotient mit einem Richardson-Schritt,
# (4·D(h/2) − D(h))/3. Gewählt wird die Stufe, an der zwei benachbarte Schätzwerte am besten übereinstimmen (die
# Differenz ist die Fehlerschätzung; Prinzip wie Ridders' Verfahren, Press et al. 2007, Abschn. 5.7). Liegt eine Stelle
# des zentralen Schemas ausserhalb des Definitionsbereichs (NaN), wird für diese Stufe die einseitige Formel zweiter
# Ordnung (vorwärts, sonst rückwärts) genommen, ebenfalls mit Richardson-Schritt.
_DOFF = np.array([-3.0, -2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0, 3.0])


def deriv_est(f, x0, n=1):
    """Ableitung n-ter Ordnung (1 oder 2) an x0 (Zahl oder Feld). -> (Wert, Fehlerschätzung)."""
    if n not in (1, 2):
        raise CalcError("deriv: nur 1. oder 2. Ableitung")
    x0 = np.asarray(x0, dtype=float)
    shape = x0.shape
    xv = x0.ravel()
    ax = np.abs(xv)
    hmax = 0.1 * np.maximum(ax, 1.0)
    hmin = 1e-9 * np.where(ax > 0, np.minimum(ax, 1.0), 1.0)
    hmin = np.maximum(hmin, 1e-300)
    K = int(min(80, np.ceil(2 * np.max(np.log10(hmax / hmin))) + 1))
    H = hmax[None, :] * 10.0 ** (-np.arange(K) / 2.0)[:, None]                  # (K, N)
    H = np.maximum(H, hmin[None, :])
    X = xv[None, None, :] + _DOFF[None, :, None] * H[:, None, :]               # (K, 11, N)
    Y = _eval_points(f, X)
    F = {o: Y[:, i, :] for i, o in enumerate(_DOFF)}
    f0 = F[0.0]
    with np.errstate(all="ignore"):
        if n == 1:
            def cen(a):
                return (F[a] - F[-a]) / (2 * a * H)

            def one(s, a):                       # s = +1 vorwärts, −1 rückwärts; Schritt a·h
                return s * (-3 * f0 + 4 * F[s * a] - F[s * 2 * a]) / (2 * a * H)
        else:
            def cen(a):
                return (F[a] - 2 * f0 + F[-a]) / (a * H) ** 2

            def one(s, a):
                return (2 * f0 - 5 * F[s * a] + 4 * F[s * 2 * a] - F[s * 3 * a]) / (a * H) ** 2
        cands = []
        if n == 1:
            cands.append((4 * cen(0.5) - cen(1.0)) / 3)
            for s in (1.0, -1.0):
                cands.append((4 * one(s, 0.5) - one(s, 1.0)) / 3)
        else:
            cands.append((4 * cen(0.5) - cen(1.0)) / 3)
            for s in (1.0, -1.0):                # einseitig: halber Schritt (0,5 h; 1 h; 1,5 h) und ganzer (1; 2; 3 h)
                cands.append((4 * one(s, 0.5) - one(s, 1.0)) / 3)
    C = np.full(H.shape, np.nan)
    kind = np.full(H.shape, -1)
    for t, c in enumerate(cands):
        use = (kind < 0) & np.isfinite(c)
        C = np.where(use, c, C)
        kind = np.where(use, t, kind)
    # Rundungsfehler je Stufe (Auslöschung in f(x+h) − f(x−h)): etwa 10·ε·max|f|/h bzw. 60·ε·max|f|/h²; er ist eine
    # untere Grenze der Fehlerschätzung, sonst sähen gleiche (ausgelöschte) Werte bei winzigem h wie Übereinstimmung aus.
    with np.errstate(all="ignore"):
        fmax = np.max(np.where(np.isfinite(Y), np.abs(Y), 0.0), axis=1)
        rnd = (10.0 if n == 1 else 60.0) * np.finfo(float).eps * fmax / H ** n
    if K > 1:
        same = (kind[:-1] == kind[1:]) & (kind[:-1] >= 0)
        diff = np.where(same, np.maximum(np.abs(C[:-1] - C[1:]), np.maximum(rnd[:-1], rnd[1:])), np.inf)
        k = np.argmin(diff, axis=0)
        cols = np.arange(xv.size)
        best, err = C[k, cols], diff[k, cols]
        # Knick: das zentrale Schema mittelt links- und rechtsseitige Steigung (|x| bei 0 ergäbe 0 ohne Warnung).
        # Weichen die einseitigen Schätzwerte an der gewählten Stufe deutlich voneinander ab, gilt ihr Abstand als
        # Fehlerschätzung.
        with np.errstate(all="ignore"):
            fw, bw = cands[1][k, cols], cands[2][k, cols]
            jump = np.abs(fw - bw)
            kink = (kind[k, cols] == 0) & np.isfinite(jump) \
                & (jump > 1e-3 * np.maximum(np.maximum(np.abs(fw), np.abs(bw)), np.abs(best))) & (jump > 100 * err)
        err = np.where(kink, jump, err)
    else:
        best, err = C[0], np.full(xv.size, np.inf)
    lone = ~np.isfinite(err)                          # keine zwei vergleichbaren Stufen: kleinster brauchbarer Schritt
    if np.any(lone):
        for j in np.nonzero(lone)[0]:
            ok = np.nonzero(np.isfinite(C[:, j]))[0]
            best[j] = C[ok[-1], j] if ok.size else math.nan
            err[j] = math.inf if ok.size else math.nan
    best, err = best.reshape(shape), err.reshape(shape)
    if not shape:
        return float(best), float(err)
    return best, err


def deriv_at(f, x0, n=1):
    return deriv_est(f, x0, n)[0]


def _sp_deriv(args, ctx, local):
    if len(args) not in (3, 4):
        raise CalcError("deriv(Ausdruck, x, Stelle[, Ordnung])")
    var = _var_name(args[1], "deriv")
    f = _fn_of(args[0], var, ctx, local)
    n = int(evaluate(args[3], ctx, local)) if len(args) == 4 else 1
    _refuse_complex(f, evaluate(args[2], ctx, local))
    v, e = deriv_est(f, evaluate(args[2], ctx, local), n)
    va, ea = np.abs(np.atleast_1d(np.asarray(v, float))), np.abs(np.atleast_1d(np.asarray(e, float)))
    fin = np.isfinite(va)
    with np.errstate(all="ignore"):
        rel = np.where(va > 0, ea / va, np.where(ea <= 1e-12, 0.0, np.inf))[fin]
    if rel.size and not np.all(np.isfinite(rel)):
        ctx.note("Ableitung: keine verlässliche Fehlerschätzung (Funktion an der Stelle nicht glatt?)")
    elif rel.size and float(np.max(rel)) > 1e-6:
        ctx.note(f"Ableitung: geschätzter relativer Fehler {fmt_num(float(np.max(rel)), 2)}")
    return v


def find_root(f, x0, x1=None, tol=1e-12):
    """Nullstelle von f nahe x0 (bzw. im Intervall [x0, x1])."""
    f0 = float(np.real(f(x0)))
    if x1 is not None:
        f1 = float(np.real(f(x1)))
        if f0 == 0:
            return x0
        if f1 == 0:
            return x1
        if f0 * f1 > 0:
            raise CalcError("nsolve: f hat an beiden Grenzen dasselbe Vorzeichen")
        return bisect(f, x0, x1, f0, f1, tol)
    x = float(x0)
    for _ in range(100):
        fx = float(np.real(f(x)))
        if fx == 0:
            return x
        d = float(deriv_at(lambda t: np.real(f(t)), x))
        if not math.isfinite(d) or d == 0:
            break
        nx = x - fx / d
        if not math.isfinite(nx):
            break
        if abs(nx - x) <= tol * max(1.0, abs(nx)):
            return nx
        x = nx
    # Vorzeichenwechsel in der Umgebung suchen
    for span in (1, 10, 100, 1e3, 1e4, 1e6):
        xs = np.linspace(x0 - span, x0 + span, 401)
        ys = np.array([float(np.real(f(v))) for v in xs])
        s = np.where(np.sign(ys[:-1]) * np.sign(ys[1:]) < 0)[0]
        if s.size:
            k = s[np.argmin(np.abs(xs[s] - x0))]
            return bisect(f, xs[k], xs[k + 1], ys[k], ys[k + 1], tol)
    raise CalcError("nsolve: keine Nullstelle gefunden – anderen Startwert versuchen")


def bisect(f, a, b, fa=None, fb=None, tol=1e-13):
    fa = float(np.real(f(a))) if fa is None else fa
    for _ in range(200):
        m = (a + b) / 2
        fm = float(np.real(f(m)))
        if fm == 0 or abs(b - a) <= tol * max(1.0, abs(m)):
            return m
        if (fa < 0) == (fm < 0):
            a, fa = m, fm
        else:
            b = m
    return (a + b) / 2


def _sp_nsolve(args, ctx, local):
    if len(args) not in (3, 4):
        raise CalcError("nsolve(Gleichung, x, Startwert[, zweiter Wert])")
    var = _var_name(args[1], "nsolve")
    e = args[0]
    if isinstance(e, ast.Compare) and len(e.ops) == 1 and isinstance(e.ops[0], ast.Eq):
        e = ast.BinOp(left=e.left, op=ast.Sub(), right=e.comparators[0])
    f = _fn_of(e, var, ctx, local)
    x0 = float(evaluate(args[2], ctx, local))
    x1 = float(evaluate(args[3], ctx, local)) if len(args) == 4 else None
    return find_root(f, x0, x1)


def _sp_series(kind):
    def g(args, ctx, local):
        if len(args) == 1:
            v = np.asarray(evaluate(args[0], ctx, local))
            return _number(np.sum(v)) if kind == "sum" else _number(np.prod(v))
        if len(args) != 4:
            raise CalcError(f"{kind}(Liste) oder {kind}(Ausdruck, k, von, bis)")
        var = _var_name(args[1], kind)
        a, b = int(round(float(evaluate(args[2], ctx, local)))), int(round(float(evaluate(args[3], ctx, local))))
        if b - a > 1_000_000:
            raise CalcError(f"{kind}: höchstens eine Million Glieder")
        if b < a:
            return 0.0 if kind == "sum" else 1.0
        k = np.arange(a, b + 1, dtype=float)
        v = _vectorized(_fn_of(args[0], var, ctx, local), k)
        return float(np.sum(v)) if kind == "sum" else float(np.prod(v))
    return g


def _sp_if(args, ctx, local):
    if len(args) != 3:
        raise CalcError("if(Bedingung, dann, sonst)")
    c = evaluate(args[0], ctx, local)
    return np.where(c, evaluate(args[1], ctx, local), evaluate(args[2], ctx, local))


def _deriv_notes(ctx, numeric):
    from . import deriv as D
    if numeric:
        ctx.note(D.NUMERIC_NOTE["de"].format(t=", ".join(numeric)))


def _sp_diff(args, ctx, local):
    """diff(Liste): Differenzen aufeinanderfolgender Werte; diff(Ausdruck, x[, n]): symbolische Ableitung nach x,
    ausgewertet am Wert von x (labcalc.deriv)."""
    if len(args) == 1:
        return np.diff(_vec(evaluate(args[0], ctx, local)))
    if len(args) not in (2, 3) or not isinstance(args[1], ast.Name):
        raise CalcError("diff(Ausdruck, x) oder diff(Ausdruck, x, n) – bzw. diff(Liste)")
    from . import deriv as D
    call = ast.Call(func=ast.Name(id="diff", ctx=ast.Load()), args=list(args), keywords=[])
    node, numeric = D.cached("diff", call, ctx.funcs, ctx.angle, lambda: D.expand(call, ctx.funcs, ctx.angle))
    _deriv_notes(ctx, numeric)
    return evaluate(node, ctx, local)


def _sp_prime(args, ctx, local):
    """fprime_(f, n, u): n-te Ableitung der Funktion f an der Stelle u (Schreibweise f'(u), f''(u))."""
    from . import deriv as D
    call = ast.Call(func=ast.Name(id="fprime_", ctx=ast.Load()), args=list(args), keywords=[])
    node, numeric = D.cached("prime", call, ctx.funcs, ctx.angle, lambda: D.expand(call, ctx.funcs, ctx.angle))
    _deriv_notes(ctx, numeric)
    return evaluate(node, ctx, local)


def _sp_dnum(args, ctx, local):
    """dnum_(g, x, n): numerische Ableitung von g nach x am Wert von x (Rückfall ohne Ableitungsregel)."""
    if len(args) != 3 or not isinstance(args[1], ast.Name):
        raise CalcError("dnum_(Ausdruck, x, n)")
    var = args[1].id
    n = int(evaluate(args[2], ctx, local))
    x0 = evaluate(args[1], ctx, local)
    v, _e = deriv_est(_fn_of(args[0], var, ctx, local), x0, min(max(n, 1), 2))
    return v


SPECIAL = {"integral": _sp_integral, "deriv": _sp_deriv, "nsolve": _sp_nsolve, "sum": _sp_series("sum"),
           "prod": _sp_series("prod"), "if_": _sp_if, "if": _sp_if, "diff": _sp_diff, "fprime_": _sp_prime,
           "dnum_": _sp_dnum}

FUNC_DOC = [
    ("Grundfunktionen", ["sqrt(x)", "cbrt(x)", "root(x, n)", "exp(x)", "ln(x)", "log(x, b)", "log10(x)", "abs(x)",
                         "round(x, n)", "floor(x)", "ceil(x)", "mod(a, b)", "n!", "binom(n, k)", "gcd(a, b)", "lcm(a, b)",
                         "erf(x)", "erfc(x)"]),
    ("Trigonometrie", ["sin(x)", "cos(x)", "tan(x)", "asin(x)", "acos(x)", "atan(x)", "atan2(y, x)", "sinh(x)",
                       "cosh(x)", "tanh(x)", "deg(x)", "rad(x)", "hypot(a, b)"]),
    ("Analysis", ["integral(f, x, a, b)", "diff(f, x)", "diff(f, x, 2)", "f'(x)", "f''(x)", "deriv(f, x, x0)",
                  "deriv(f, x, x0, 2)", "nsolve(f == g, x, x0)", "sum(f, k, a, b)", "prod(f, k, a, b)",
                  "if(Bedingung, a, b)"]),
    ("Matrizen", ["[[1, 2], [3, 4]]", "A*B", "A*B = C", "A'", "inv(A)", "det(A)", "adj(A)", "cof(A)", "rank(A)",
                  "trace(A)", "eig(A)",
                  "eigvec(A)", "rref(A)", "linsolve(A, b)", "eye(n)", "zeros(m, n)", "dot(a, b)", "cross(a, b)",
                  "norm(v)", "A[i, j]", "row(A, i)", "col(A, j)", "svd(A)", "pinv(A)"]),
    ("Statistik", ["[1, 2, 3]", "mean(L)", "median(L)", "std(L)", "var(L)", "min(L)", "max(L)", "sum(L)",
                   "linreg(x, y)", "polyfit(x, y, n)", "polyval(p, x)", "roots(p)", "interp(x, xs, ys)",
                   "seq(a, b, s)", "linspace(a, b, n)", "trapz(y, x)"]),
    ("Einheiten und Komplex", ["v -> km/h", 'convert(x, "bar", "psi")', "re(z)", "im(z)", "abs(z)", "arg(z)",
                               "conj(z)", "2 + 3i"]),
]

# Funktionen mit Formel bzw. Name als erstem Argument (M("H2O"), pKa("…")). Sie gelten nur als Aufruf, wenn das
# erste Argument in Anführungszeichen steht; so bleiben n, M usw. als Variablennamen frei (n(T-1) = n·(T-1)).
STRFUNCS: dict = {}          # Name -> (fn(ctx, *args), nmin, nmax, Dimension, Beschreibung)


def register_string_function(name, fn, nmin, nmax, dims, doc="", group="Chemie"):
    """``dims``: Dimension des Ergebnisses, oder eine Funktion der Argumente in Anführungszeichen, die sie liefert
    (mat("Cu", "E") -> Elastizitätsmodul); ``group``: Abschnitt in der Funktionsübersicht."""
    STRFUNCS[name] = (fn, nmin, nmax, dims, doc)
    gname = group
    group = next((g for g in FUNC_DOC if g[0] == gname), None)
    if group is None:
        group = (gname, [])
        FUNC_DOC.append(group)
    entry = doc.split(" – ")[0] if doc else f'{name}("…")'
    if entry not in group[1]:
        group[1].append(entry)


def strfunc_dims(node):
    """Dimension eines Aufrufs wie M("H2O") oder mat("Cu", "E"); None, wenn sie sich nicht bestimmen lässt."""
    d = STRFUNCS[node.func.id][3]
    if callable(d):                                           # Einheit hängt von den Textargumenten ab
        return d(*[a.value if isinstance(a, ast.Constant) and isinstance(a.value, str) else None for a in node.args])
    return d


# ----------------------------------------------------------------------------- Dimensionen
class DimError(ValueError):
    pass


_DIMLESS_FUNCS = {"sin", "cos", "tan", "cot", "asin", "acos", "atan", "atan2", "sinh", "cosh", "tanh", "exp", "ln", "erf", "erfc",
                  "log", "log10", "log2", "asinh", "acosh", "atanh", "fact", "gamma", "eigvec"}
# Ergebnis hat die Einheit des ersten Arguments
_SAME_DIMS = {"std", "sort", "cumsum", "diff", "transpose", "trace", "eig", "svd", "norm", "diag", "row", "col",
              "re", "im", "conj"}


def _bare(node) -> bool:
    """Zahl ohne Namen (0, 2.5, −1, inf, pi): als Grenze oder Startwert passt sie zu jeder Einheit."""
    calls = [c for c in ast.walk(node) if isinstance(c, ast.Call)]
    if any(isinstance(c.func, ast.Name) and c.func.id in STRFUNCS for c in calls):
        return False
    fn = {id(c.func) for c in calls}
    return all(not isinstance(n, ast.Name) or id(n) in fn or n.id in ("inf", "nan", "pi") for n in ast.walk(node))


def _special_dims(node, dims, strict, consts):
    """Einheit von integral, deriv, nsolve, sum, prod, if: ∫f dx -> [f]·[x], df/dx -> [f]/[x]ⁿ, nsolve -> [x]
    (aus dem Startwert, sonst dimensionslos, wenn die Gleichung nur dimensionslose Grössen enthält), Summe -> [Glied].
    None = unbekannt."""
    n, args = node.func.id, node.args

    def dd(a, extra=None):
        return dims_of(a, {**dims, **(extra or {})}, strict, consts)

    def same(ds, what):
        if any(d is None for d in ds):
            return None
        if ds and not all(U.deq(d, ds[0]) for d in ds[1:]):
            if strict:
                raise DimError(f"{what}: Grenzen mit verschiedenen Einheiten")
            return None
        return ds[0] if ds else U.D0

    if n == "integral" and len(args) == 4 and isinstance(args[1], ast.Name):
        dx = same([dd(a) for a in args[2:] if not _bare(a)], "integral")
        if dx is None:
            return None
        inner = dd(args[0], {args[1].id: dx})
        return U.dmul(inner, dx) if inner is not None else None
    if n == "deriv" and len(args) in (3, 4) and isinstance(args[1], ast.Name):
        dx = U.D0 if _bare(args[2]) else dd(args[2])
        if dx is None:
            return None
        try:
            order = int(float(evaluate(args[3], Ctx()))) if len(args) == 4 else 1
        except (CalcError, TypeError, ValueError):
            return None
        inner = dd(args[0], {args[1].id: dx})
        return U.ddiv(inner, U.dpow(dx, order)) if inner is not None else None
    if n == "nsolve" and len(args) in (3, 4) and isinstance(args[1], ast.Name):
        given = [a for a in args[2:] if not _bare(a)]
        if given:
            return same([dd(a) for a in given], "nsolve")
        var = args[1].id
        e = args[0]
        pair = (e.left, e.comparators[0]) if isinstance(e, ast.Compare) and len(e.ops) == 1 else (e, e)
        from . import solve as SV                         # Einheit der Unbekannten wie beim Lösen von Gleichungen
        try:
            got, bad = SV.infer_dims([pair], Ctx(names={}, dims={k: v for k, v in dims.items() if k != var}), [var])
        except (CalcError, ValueError, TypeError):
            return None
        if got.get(var) is not None and not bad:
            return got[var]
        fnames = {c.func.id for c in ast.walk(e) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
        others = {m.id for m in ast.walk(e) if isinstance(m, ast.Name) and m.id != var and m.id not in fnames}
        ds = [dd(ast.Name(id=m, ctx=ast.Load())) for m in others if m not in ("inf", "nan", "pi")]
        return U.D0 if not bad and all(d is not None and U.deq(d, U.D0) for d in ds) else None
    if n in ("sum", "prod"):
        if len(args) == 1:
            d = dd(args[0])
            if n == "sum" or d is None:
                return d
            return U.D0 if U.deq(d, U.D0) else None
        if len(args) == 4 and isinstance(args[1], ast.Name):
            inner = dd(args[0], {args[1].id: U.D0})
            if inner is None or n == "sum":
                return inner
            if U.deq(inner, U.D0):
                return U.D0
            try:
                cnt = int(round(float(evaluate(args[3], Ctx())))) - int(round(float(evaluate(args[2], Ctx())))) + 1
            except (CalcError, TypeError, ValueError):
                return None
            return U.dpow(inner, max(cnt, 0))
        return None
    if n in ("if", "if_") and len(args) == 3:
        a, b = dd(args[1]), dd(args[2])
        return a if a is not None and b is not None and U.deq(a, b) else None
    if n == "diff" and len(args) == 1:
        return dd(args[0])
    if n in ("diff", "dnum_") and len(args) in (2, 3) and isinstance(args[1], ast.Name):
        dx = dd(args[1])                                   # d f/d x: Einheit von f durch Einheit von x hoch n
        if dx is None:
            return None
        try:
            order = int(float(evaluate(args[2], Ctx()))) if len(args) == 3 else 1
        except (CalcError, TypeError, ValueError):
            return None
        inner = dd(args[0])
        return U.ddiv(inner, U.dpow(dx, order)) if inner is not None else None
    return None


def dims_of(node, dims: dict, strict=False, consts=True):
    """Dimension eines Ausdrucks; None = unbekannt. strict: Fehler bei unpassenden Summen."""
    t = type(node)
    if t is ast.Constant:
        return U.D0
    if t is ast.Name:
        n = node.id
        if n in dims:
            return dims[n]
        if consts and n in U.CONSTANTS:
            return U.constant_dims(n)
        if n in ("inf", "nan", "i", "j"):
            return U.D0
        if strict:
            raise DimError(f"Dimension von „{n}“ unbekannt")
        return None
    if t is ast.UnaryOp:
        return dims_of(node.operand, dims, strict, consts)
    if t is ast.BinOp:
        a = dims_of(node.left, dims, strict, consts)
        op = type(node.op)
        if op is ast.Pow:
            if a is None:
                return None
            try:
                n = float(evaluate(node.right, Ctx()))
            except CalcError:
                if U.deq(a, U.D0):
                    return U.D0
                if strict:
                    raise DimError("Exponent einer Grösse mit Einheit muss eine Zahl sein")
                return None
            return U.dpow(a, n)
        b = dims_of(node.right, dims, strict, consts)
        if a is None or b is None:
            return None
        if op in (ast.Add, ast.Sub, ast.Mod):
            if not U.deq(a, b):
                if strict:
                    raise DimError(f"Summe aus {U.dims_text(a) or '1'} und {U.dims_text(b) or '1'}")
                return None
            return a
        if op in (ast.Mult, ast.MatMult):
            return U.dmul(a, b)
        if op is ast.Div:
            return U.ddiv(a, b)
        return None
    if t in (ast.List, ast.Tuple):                    # Liste/Matrix: Einheit, wenn alle Einträge dieselbe haben
        ds = [dims_of(e, dims, strict, consts) for e in node.elts]
        if not ds:
            return U.D0
        if any(d is None for d in ds):
            return None
        return ds[0] if all(U.deq(d, ds[0]) for d in ds[1:]) else None
    if t is ast.Subscript:
        return dims_of(node.value, dims, strict, consts)
    if t is ast.IfExp:
        a, b = dims_of(node.body, dims, strict, consts), dims_of(node.orelse, dims, strict, consts)
        return a if a is not None and b is not None and U.deq(a, b) else None
    if t is ast.Call and isinstance(node.func, ast.Name) and node.func.id in SPECIAL:
        return _special_dims(node, dims, strict, consts)
    if t is ast.Call and isinstance(node.func, ast.Name):
        n = node.func.id
        ds = [dims_of(a, dims, strict, consts) for a in node.args]
        if n in _SAME_DIMS and ds:
            return ds[0]
        if n == "inv" and ds and ds[0] is not None:
            return U.dpow(ds[0], -1)
        if n in ("len", "size", "rank", "cond", "eye", "identity", "zeros", "ones", "binom", "nCr", "nPr",
                 "rand", "gcd", "lcm"):
            return U.D0
        if n in ("det", "adj", "adjugate", "cof") and ds and ds[0] is not None:
            return U.D0 if U.deq(ds[0], U.D0) else None          # Einheit^n, n = Grösse der Matrix: unbekannt
        if n == "var" and ds and ds[0] is not None:
            return U.dpow(ds[0], 2)
        if n in ("dot", "kron", "cross") and len(ds) == 2 and ds[0] is not None and ds[1] is not None:
            return U.dmul(ds[0], ds[1])
        if n == "linsolve" and len(ds) == 2 and ds[0] is not None and ds[1] is not None:
            return U.ddiv(ds[1], ds[0])
        if n == "trapz" and ds and ds[0] is not None:
            dx = ds[1] if len(ds) == 2 else U.D0
            return U.dmul(ds[0], dx) if dx is not None else None
        if n == "interp" and len(ds) == 3:
            return ds[2]
        if n == "convert" and len(node.args) == 3 and isinstance(node.args[2], ast.Constant) \
                and isinstance(node.args[2].value, str):
            return U.D0                                   # Zahlenwert in der Zieleinheit
        if n in ("polyfit", "polyval", "roots", "linreg"):
            if all(d is not None and U.deq(d, U.D0) for d in ds):
                return U.D0
            return None                                   # Koeffizienten mit verschiedenen Einheiten
        if n == "sqrt":
            return U.dpow(ds[0], 0.5) if ds[0] is not None else None
        if n == "cbrt":
            return U.dpow(ds[0], 1 / 3) if ds[0] is not None else None
        if n in ("abs", "min", "max", "mean", "median", "round", "floor", "ceil", "sign"):
            return U.D0 if n == "sign" else ds[0]
        if n == "hypot":
            if strict and ds[0] is not None and ds[1] is not None and not U.deq(ds[0], ds[1]):
                raise DimError("hypot aus unterschiedlichen Einheiten")
            return ds[0]
        if n in STRFUNCS and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            return strfunc_dims(node)
        if n in _DIMLESS_FUNCS:
            if strict and any(d is not None and not U.deq(d, U.D0) for d in ds[:1]) and n != "atan2":
                raise DimError(f"{n}() braucht ein dimensionsloses Argument")
            return U.D0
        return None
    if t is ast.Compare:
        return U.D0
    return None


# ----------------------------------------------------------------------------- Ausgabe
def fmt_num(v: float, digits=10) -> str:
    if v is None:
        return "–"
    v = float(v)
    if math.isnan(v):
        return "nicht definiert"
    if math.isinf(v):
        return "∞" if v > 0 else "−∞"
    if v == 0:
        return "0"
    a = abs(v)
    if 1e-4 <= a < 10 ** digits:
        s = f"{v:.{digits}g}"
        if "e" in s:
            s = f"{v:.{max(0, digits - int(math.floor(math.log10(a))) - 1)}f}"
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        return s
    s = f"{v:.{max(1, digits - 1)}e}"
    mant, ex = s.split("e")
    if "." in mant:
        mant = mant.rstrip("0").rstrip(".")
    return f"{mant}e{int(ex)}"


def fmt_complex(z: complex, digits=10) -> str:
    re_, im_ = z.real, z.imag
    if abs(im_) <= 1e-14 * max(1, abs(re_)):
        return fmt_num(re_, digits)
    if abs(re_) <= 1e-14 * max(1, abs(im_)):
        return fmt_num(im_, digits) + "i"
    return f"{fmt_num(re_, digits)} {'+' if im_ >= 0 else '−'} {fmt_num(abs(im_), digits)}i"


def describe(v, digits=10) -> dict:
    """Ergebnis fuer die Oberflaeche: Typ, Text und JSON-Wert."""
    if isinstance(v, str):
        return {"type": "text", "text": v, "value": v}
    a = np.asarray(v)
    if a.dtype == bool:
        a = a.astype(float)
        if a.ndim == 0:
            return {"type": "bool", "text": "wahr" if a else "falsch", "value": float(a)}
    if a.ndim == 0:
        z = complex(a)
        if z.imag != 0 and abs(z.imag) > 1e-14 * max(1, abs(z.real)):
            return {"type": "complex", "text": fmt_complex(z, digits), "value": [z.real, z.imag]}
        return {"type": "scalar", "text": fmt_num(z.real, digits), "value": _jnum(z.real)}
    if a.ndim > 2:
        raise CalcError("Mehr als zweidimensionale Felder werden nicht unterstützt")
    cells = a.tolist()
    f = (lambda x: fmt_complex(complex(x), digits)) if np.iscomplexobj(a) else (lambda x: fmt_num(x, digits))
    if a.ndim == 1:
        txt = [f(x) for x in cells]
        return {"type": "vector", "text": "[" + ", ".join(txt) + "]", "cells": txt,
                "value": [_jnum(x) for x in np.real(a).tolist()] if not np.iscomplexobj(a) else None, "shape": [a.size]}
    txt = [[f(x) for x in r] for r in cells]
    return {"type": "matrix", "text": "[" + ", ".join("[" + ", ".join(r) + "]" for r in txt) + "]", "cells": txt,
            "value": [[_jnum(x) for x in r] for r in np.real(a).tolist()] if not np.iscomplexobj(a) else None,
            "shape": list(a.shape)}


def _jnum(x):
    x = float(x)
    return x if math.isfinite(x) else None


def _from_cell(c):
    if c is None:
        return math.nan
    if isinstance(c, dict):
        re_, im_ = c.get("re"), c.get("im", 0)
        return complex(math.nan if re_ is None else re_, math.nan if im_ is None else im_)
    return c


def from_json(v):
    """Gespeicherter Wert (Zahl, Liste, Matrix; komplexe Zahlen als {re, im}, auch als Zellen) -> numpy."""
    if isinstance(v, dict) and "re" in v:
        return _from_cell(v)
    if isinstance(v, list):
        rows = [[_from_cell(c) for c in r] if isinstance(r, list) else _from_cell(r) for r in v]
        cplx = any(isinstance(c, complex) for r in rows for c in (r if isinstance(r, list) else [r]))
        return np.array(rows, dtype=complex if cplx else float)
    if v is None:
        return math.nan
    return float(v)


def _to_cell(x):
    z = complex(x)
    return {"re": _jnum(z.real), "im": _jnum(z.imag)} if z.imag else _jnum(z.real)


def to_json(v):
    """Wert für JSON; komplexe Einträge bleiben als {re, im} erhalten."""
    a = np.asarray(v)
    if a.ndim == 0:
        z = complex(a)
        return {"re": z.real, "im": z.imag} if z.imag else _jnum(z.real)
    cell = _to_cell if np.iscomplexobj(a) else _jnum
    return [[cell(x) for x in r] for r in a.tolist()] if a.ndim == 2 else [cell(x) for x in a.tolist()]


# ----------------------------------------------------------------------------- Chemie-Funktionen
def _register_chem():
    from . import acidbase, chem, ionization, materials, nuclear, prep, redox, substances, thermo, vapor
    ionization.register_calc_functions()
    vapor.register_calc_functions()
    nuclear.register_calc_functions()
    chem.register_calc_functions()
    substances.register_calc_functions()
    thermo.register_calc_functions()
    redox.register_calc_functions()
    acidbase.register_calc_functions()
    prep.register_calc_functions()
    materials.register_calc_functions()
    substances.install()        # Stoffnamen (DE/EN) aus der Sammlung in Formeln: M("Essigsäure")


_register_chem()
