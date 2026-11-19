"""Formeln darstellen (LaTeX fuer den Bericht, HTML fuer die Seite) und nach einer Variablen umstellen."""
from __future__ import annotations

import ast
import html as _html
import math
import re

from . import expr as E

GREEK_TEX = {"alpha": r"\alpha", "beta": r"\beta", "gamma": r"\gamma", "delta": r"\delta", "epsilon": r"\varepsilon",
             "eps": r"\varepsilon", "zeta": r"\zeta", "eta": r"\eta", "theta": r"\theta", "iota": r"\iota",
             "kappa": r"\kappa", "lambda": r"\lambda", "mu": r"\mu", "nu": r"\nu", "xi": r"\xi", "pi": r"\pi",
             "rho": r"\rho", "sigma": r"\sigma", "tau": r"\tau", "phi": r"\varphi", "chi": r"\chi", "psi": r"\psi",
             "omega": r"\omega", "Delta": r"\Delta", "Gamma": r"\Gamma", "Omega": r"\Omega", "Phi": r"\Phi",
             "Sigma": r"\Sigma", "Theta": r"\Theta", "Lambda": r"\Lambda", "Psi": r"\Psi", "Pi": r"\Pi"}
GREEK_HTML = {"alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "eps": "ε", "zeta": "ζ",
              "eta": "η", "theta": "θ", "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ",
              "pi": "π", "rho": "ρ", "sigma": "σ", "tau": "τ", "phi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",
              "Delta": "Δ", "Gamma": "Γ", "Omega": "Ω", "Phi": "Φ", "Sigma": "Σ", "Theta": "Θ", "Lambda": "Λ",
              "Psi": "Ψ", "Pi": "Π"}

# Konstanten und Sondernamen: (LaTeX, HTML)
SPECIAL_SYM = {
    "pi": (r"\pi", "π"), "e": (r"\mathrm{e}", "e"), "g0": ("g", "<i>g</i>"), "c0": ("c_0", "<i>c</i><sub>0</sub>"),
    "hP": ("h", "<i>h</i>"), "hbar": (r"\hbar", "ħ"), "kB": (r"k_\mathrm{B}", "<i>k</i><sub>B</sub>"),
    "NA": (r"N_\mathrm{A}", "<i>N</i><sub>A</sub>"), "Rgas": ("R", "<i>R</i>"), "G_grav": ("G", "<i>G</i>"),
    "eps0": (r"\varepsilon_0", "ε<sub>0</sub>"), "mu0": (r"\mu_0", "μ<sub>0</sub>"), "q_e": (r"\mathrm{e}", "e"),
    "m_e": (r"m_\mathrm{e}", "<i>m</i><sub>e</sub>"), "m_p": (r"m_\mathrm{p}", "<i>m</i><sub>p</sub>"),
    "sigma_SB": (r"\sigma_\mathrm{SB}", "σ<sub>SB</sub>"), "F_c": (r"F", "<i>F</i>"),
    "T0": ("T_0", "<i>T</i><sub>0</sub>"), "p_n": (r"p_\mathrm{n}", "<i>p</i><sub>n</sub>"),
    "c_std": (r"c^\circ", "<i>c</i>°"), "MPa1": (r"\mathrm{MPa}", "MPa"), "inf": (r"\infty", "∞"),
    "NA_o": (r"\mathrm{NA}", "NA"), "b_wien": (r"b", "<i>b</i>"),
    "t_half": (r"t_{1/2}", "<i>t</i><sub>1/2</sub>"), "m_dot": (r"\dot{m}", "ṁ"),
    "Q_dot": (r"\dot{Q}", "Q̇"), "V_dot": (r"\dot{V}", "V̇"), "W_dot": (r"\dot{W}", "Ẇ"),
}
UPRIGHT_BASE = {"HV", "HB", "pH", "pOH", "pKa", "Re", "Pr", "Nu", "Ma", "Fr", "NA_opt", "KV", "COP", "Bi", "Gr", "Ra",
                "FWHM", "SNR", "DOF", "OD", "MTF"}


def _split_name(name: str):
    n = name.rstrip("_") if name.endswith("_") and name[:-1] else name
    if "_" in n:
        base, sub = n.split("_", 1)
    else:
        m = re.fullmatch(r"([^\W\d_]+?)(\d+)", n)
        base, sub = (m.group(1), m.group(2)) if m else (n, "")
    delta = False
    if base not in GREEK_TEX and base not in UPRIGHT_BASE and len(base) > 1 and base[0] == "d" and \
            (base[1:] in GREEK_TEX or (base[1].isupper() and len(base) <= 3) or base[1:] in ("x", "y", "z", "t", "s", "l", "p", "v", "h", "r")):
        delta, base = True, base[1:]
    return base, sub, delta


def _base_tex(b):
    if b in GREEK_TEX:
        return GREEK_TEX[b]
    if len(b) == 1 and b.isascii():
        return b
    return r"\mathrm{%s}" % b if b.isascii() else r"\mbox{%s}" % b      # Umlaute nicht im Mathemodus


def _base_html(b):
    if b in GREEK_HTML:
        return GREEK_HTML[b]
    if len(b) == 1:
        return f"<i>{b}</i>"
    return b


def _sub_tex(s):
    parts = []
    for p in s.split("_"):
        if p in GREEK_TEX:
            parts.append(GREEK_TEX[p])
        elif (len(p) == 1 and p.isascii()) or p.isdigit():
            parts.append(p)
        elif not p.isascii():
            parts.append(r"\mbox{\scriptsize %s}" % p)
        else:
            parts.append(r"\mathrm{%s}" % p)
    return ",".join(parts)


def _sub_html(s):
    return ",".join(GREEK_HTML.get(p, p) for p in s.split("_"))


def sym_tex(name: str) -> str:
    if name in SPECIAL_SYM:
        return SPECIAL_SYM[name][0]
    base, sub, delta = _split_name(name)
    t = _base_tex(base)
    if sub:
        t += "_{%s}" % _sub_tex(sub)
    return (r"\Delta " if delta else "") + t


def sym_html(name: str) -> str:
    if name in SPECIAL_SYM:
        return SPECIAL_SYM[name][1]
    base, sub, delta = _split_name(name)
    h = _base_html(base)
    if sub:
        h += f"<sub>{_sub_html(sub)}</sub>"
    return ("Δ" if delta else "") + h


# ----------------------------------------------------------------------------- Zahlen und Einheiten
def _nonfinite(v):
    """Text für NaN/±∞ (oder None, wenn v endlich ist); fmt_num liefert dafür Wörter, die ein „e“ enthalten."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "nan"
    if math.isnan(f):
        return "nan"
    if math.isinf(f):
        return "inf" if f > 0 else "-inf"
    return None


def num_tex(v: float, lang="de", digits=4) -> str:
    bad = _nonfinite(v)
    if bad:
        return {"nan": r"\mbox{%s}" % ("nicht definiert" if lang == "de" else "not defined"), "inf": r"\infty",
                "-inf": r"-\infty"}[bad]
    s = E.fmt_num(v, digits)
    if "e" in s:
        mant, ex = s.split("e")
        s = (mant + r"\cdot " if mant not in ("1", "-1") else ("-" if mant == "-1" else "")) + "10^{%d}" % int(ex)
    if lang == "de":
        s = s.replace(".", "{,}")
    return s.replace("∞", r"\infty").replace("nicht definiert", r"\mathrm{n.\,d.}")


def num_html(v: float, lang="de", digits=4) -> str:
    bad = _nonfinite(v)
    if bad:
        return {"nan": "nicht definiert" if lang == "de" else "not defined", "inf": "∞", "-inf": "−∞"}[bad]
    s = E.fmt_num(v, digits)
    if "e" in s:
        mant, ex = s.split("e")
        s = (mant + "·" if mant not in ("1", "-1") else ("−" if mant == "-1" else "")) + f"10<sup>{int(ex)}</sup>"
    if lang == "de":
        s = s.replace(".", ",")
    return s.replace("-", "−")


_UTOK = re.compile(r"\^\(?-?[\d.]+(?:/\d+)?\)?|[*/()·]|[^*/()^·\s]+|\s+")


def _uexp(e: str) -> str:
    e = e.strip("()")
    return {"0.5": "1/2", "-0.5": "-1/2", "0.25": "1/4", "1.5": "3/2", "0.333333": "1/3"}.get(e, e)


def unit_tex(u: str) -> str:
    """Einheitentext -> LaTeX (ohne amsmath, im Mathematikmodus)."""
    if not u or u == "1":
        return ""
    s = str(u).replace("μ", "µ").replace("²", "^2").replace("³", "^3").replace("⁻¹", "^-1")
    s = re.sub(r"√\(([^)]*)\)", r"(\1)^0.5", s)
    s = re.sub(r"√([A-Za-zµ]+)", r"\1^0.5", s)
    out = []
    for tok in _UTOK.findall(s):
        if tok.isspace():
            out.append(r"\,")
        elif tok.startswith("^"):
            out.append("^{%s}" % _uexp(tok[1:]))
        elif tok in ("*", "·"):
            out.append(r"\cdot ")
        elif tok in ("/", "(", ")"):
            out.append(tok)
        else:
            out.append(_atom_tex(tok))
    return "".join(out)


def _atom_tex(a: str) -> str:
    rep = {"°C": r"{}^{\circ}\mathrm{C}", "°F": r"{}^{\circ}\mathrm{F}", "°": r"{}^{\circ}", "%": r"\%",
           "‰": r"\mbox{\textperthousand}", "Ohm": r"\Omega", "Å": r"\mbox{\AA}", "Ω": r"\Omega"}
    if a in rep:
        return rep[a]
    m = re.fullmatch(r"([kMGTmunpµ]?)(Ohm|Ω)", a)
    if m:
        return (r"\mathrm{%s}" % m.group(1) if m.group(1) and m.group(1) not in "µu" else (r"\mu " if m.group(1) else "")) + r"\Omega"
    if a.startswith(("µ", "u")) and len(a) > 1 and a not in ("u",):
        if a[0] == "µ":
            return r"\mu\mathrm{%s}" % a[1:]
    if re.fullmatch(r"\d+(\.\d+)?", a):
        return a
    return r"\mathrm{%s}" % a.replace("%", r"\%")


def unit_html(u: str) -> str:
    if not u or u == "1":
        return ""
    s = _html.escape(str(u)).replace("Ohm", "Ω").replace("*", "·")
    s = re.sub(r"\^\(?(-?[\d.]+(?:/\d+)?)\)?", lambda m: f"<sup>{_uexp(m.group(1)).replace('-', '−')}</sup>", s)
    return s


def qty_tex(v, unit, lang="de", digits=4):
    u = unit_tex(unit)
    return num_tex(v, lang, digits) + (r"\," + u if u else "")


def qty_html(v, unit, lang="de", digits=4):
    u = unit_html(unit)
    return num_html(v, lang, digits) + ("&#8239;" + u if u else "")


# ----------------------------------------------------------------------------- AST -> LaTeX/HTML
P_ADD, P_MUL, P_NEG, P_POW, P_ATOM = 1, 2, 3, 4, 5
FUNC_TEX = {"sin": r"\sin", "cos": r"\cos", "tan": r"\tan", "cot": r"\cot", "sinh": r"\sinh", "cosh": r"\cosh",
            "tanh": r"\tanh", "asin": r"\arcsin", "acos": r"\arccos", "atan": r"\arctan", "ln": r"\ln",
            "log10": r"\log_{10}", "log2": r"\log_{2}", "exp": r"\exp", "min": r"\min", "max": r"\max", "det": r"\det",
            "erf": r"\operatorname{erf}", "erfc": r"\operatorname{erfc}"}
FUNC_HTML = {"asin": "arcsin", "acos": "arccos", "atan": "arctan", "log10": "log<sub>10</sub>", "log2": "log<sub>2</sub>"}


class Renderer:
    """subs: Name -> (latex, html, prec) fuer eingesetzte Werte."""

    def __init__(self, subs=None, lang="de"):
        self.subs = subs or {}
        self.lang = lang

    def go(self, node):
        return self._r(node)[:2]

    def _paren(self, part, need):
        t, h, p = part
        if p < need:
            return r"\left(" + t + r"\right)", "(" + h + ")", P_ATOM
        return part

    def _r(self, node):
        t = type(node)
        if t is ast.Constant:
            v = node.value
            if isinstance(v, str):
                return r"\mbox{%s}" % v, _html.escape(v), P_ATOM
            if isinstance(v, complex):
                return num_tex(v.imag, self.lang) + r"\,\mathrm{i}", num_html(v.imag, self.lang) + "i", P_MUL
            return num_tex(v, self.lang, 6), num_html(v, self.lang, 6), (P_ATOM if v >= 0 else P_NEG)
        if t is ast.Name:
            if node.id in self.subs:
                return self.subs[node.id]
            return sym_tex(node.id), sym_html(node.id), P_ATOM
        if t is ast.UnaryOp:
            a = self._r(node.operand)
            if isinstance(node.op, ast.USub):
                a = self._paren(a, P_NEG + (1 if a[2] == P_NEG else 0))
                return "-" + a[0], "−" + a[1], P_NEG
            if isinstance(node.op, ast.Not):
                return r"\neg " + a[0], "¬" + a[1], P_NEG
            return a
        if t is ast.BinOp:
            op = type(node.op)
            if op in (ast.Add, ast.Sub):
                a = self._r(node.left)
                b = self._r(node.right)
                sign = "+"
                if op is ast.Sub:
                    sign = "-"
                    b = self._paren(b, P_MUL)
                elif b[2] == P_NEG and b[0].startswith("-"):
                    sign, b = "-", (b[0][1:], b[1][1:], P_MUL)
                b = self._paren(b, P_NEG + 1 if b[2] == P_NEG else P_MUL)
                return f"{a[0]} {sign} {b[0]}", f"{a[1]} {'+' if sign == '+' else '−'} {b[1]}", P_ADD
            if op in (ast.Mult, ast.MatMult):
                a = self._paren(self._r(node.left), P_MUL)
                b = self._r(node.right)
                b = self._paren(b, P_NEG + 1 if b[2] == P_NEG else P_MUL)
                r = node.right
                implicit = isinstance(node.left, ast.Constant) and not self._is_subs(r) and (
                    (isinstance(r, ast.Name) and r.id != "e") or isinstance(r, ast.Call)
                    or (isinstance(r, ast.BinOp) and isinstance(r.op, ast.Pow) and isinstance(r.left, ast.Name)
                        and not self._is_subs(r.left)))
                if implicit:
                    return f"{a[0]}\\,{b[0]}", f"{a[1]}{b[1]}", P_MUL
                return f"{a[0]} \\cdot {b[0]}", f"{a[1]} · {b[1]}", P_MUL
            if op is ast.Div:
                a, b = self._r(node.left), self._r(node.right)
                return r"\frac{%s}{%s}" % (a[0], b[0]), \
                    f'<span class="frac"><span>{a[1]}</span><span>{b[1]}</span></span>', P_ATOM
            if op is ast.Pow:
                ex = node.right
                exv = _const_value(ex)
                base = self._r(node.left)
                if exv is not None and abs(exv - 0.5) < 1e-12:
                    return r"\sqrt{%s}" % base[0], f'√<span class="rad">{base[1]}</span>', P_ATOM
                if exv is not None and abs(exv - 1 / 3) < 1e-12:
                    return r"\sqrt[3]{%s}" % base[0], f'∛<span class="rad">{base[1]}</span>', P_ATOM
                base = self._paren(base, P_ATOM)
                if isinstance(node.left, ast.BinOp) and isinstance(node.left.op, ast.Div):     # (a/b)^n, nicht a/b mit Hochzahl
                    base = (r"\left(" + base[0] + r"\right)", "(" + base[1] + ")", P_ATOM)
                elif isinstance(node.left, ast.Call) and node.left.func.id in FUNC_TEX and base[0].startswith(FUNC_TEX[node.left.func.id]):
                    base = (r"\left(" + base[0] + r"\right)", "(" + base[1] + ")", P_ATOM)
                e = self._r(ex)
                et = e[0]
                if isinstance(ex, ast.BinOp) and isinstance(ex.op, ast.Div):     # Bruch im Exponent: a/b
                    l, r = self._r(ex.left), self._r(ex.right)
                    et = "%s/%s" % (self._paren(l, P_ATOM)[0], self._paren(r, P_ATOM)[0])
                return "{%s}^{%s}" % (base[0], et), f"{base[1]}<sup>{e[1]}</sup>", P_POW
            if op is ast.Mod:
                a, b = self._r(node.left), self._r(node.right)
                return rf"{a[0]} \bmod {b[0]}", f"{a[1]} mod {b[1]}", P_MUL
        if t is ast.Compare:
            parts = [self._r(node.left)]
            syms = {ast.Eq: ("=", "="), ast.NotEq: (r"\neq", "≠"), ast.Lt: ("<", "&lt;"), ast.LtE: (r"\leq", "≤"),
                    ast.Gt: (">", "&gt;"), ast.GtE: (r"\geq", "≥")}
            tx, hx = parts[0][0], parts[0][1]
            for o, c in zip(node.ops, node.comparators):
                s = syms[type(o)]
                r = self._r(c)
                tx += f" {s[0]} {r[0]}"
                hx += f" {s[1]} {r[1]}"
            return tx, hx, 0
        if t is ast.Call and isinstance(node.func, ast.Name):
            return self._call(node)
        if t in (ast.List, ast.Tuple):
            if node.elts and all(isinstance(e, (ast.List, ast.Tuple)) for e in node.elts):
                rows = [[self._r(c) for c in r.elts] for r in node.elts]
                ncol = max(len(r) for r in rows)
                tx = r"\left(\begin{array}{%s}" % ("c" * ncol) + r" \\ ".join(" & ".join(c[0] for c in r) for r in rows) + r"\end{array}\right)"
                hx = '<span class="mat">' + "".join("<span>" + "".join(f"<span>{c[1]}</span>" for c in r) + "</span>" for r in rows) + "</span>"
                return tx, hx, P_ATOM
            items = [self._r(c) for c in node.elts]
            return r"\left(" + ";\\ ".join(i[0] for i in items) + r"\right)", "(" + "; ".join(i[1] for i in items) + ")", P_ATOM
        if t is ast.Subscript:
            b = self._paren(self._r(node.value), P_ATOM)
            idx = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
            ii = [self._r(i) for i in idx]
            return "{%s}_{%s}" % (b[0], ",".join(i[0] for i in ii)), b[1] + "<sub>" + ",".join(i[1] for i in ii) + "</sub>", P_ATOM
        src = ast.unparse(node)
        return r"\mbox{%s}" % src, _html.escape(src), P_ATOM

    def _is_subs(self, node):
        return isinstance(node, ast.Name) and node.id in self.subs

    def _call(self, node):
        n = node.func.id
        args = [self._r(a) for a in node.args]
        if n == "sqrt" and len(args) == 1:
            return r"\sqrt{%s}" % args[0][0], f'√<span class="rad">{args[0][1]}</span>', P_ATOM
        if n == "cbrt" and len(args) == 1:
            return r"\sqrt[3]{%s}" % args[0][0], f'∛<span class="rad">{args[0][1]}</span>', P_ATOM
        if n == "root" and len(args) == 2:
            return r"\sqrt[%s]{%s}" % (args[1][0], args[0][0]), f'<sup>{args[1][1]}</sup>√<span class="rad">{args[0][1]}</span>', P_ATOM
        if n == "exp" and len(args) == 1:
            return r"\mathrm{e}^{%s}" % args[0][0], f"e<sup>{args[0][1]}</sup>", P_POW
        if n == "abs" and len(args) == 1:
            return r"\left|%s\right|" % args[0][0], f"|{args[0][1]}|", P_ATOM
        if n in ("fact", "factorial") and len(args) == 1:
            a = self._paren(args[0], P_ATOM)
            return a[0] + "!", a[1] + "!", P_POW
        if n == "transpose" and len(args) == 1:
            a = self._paren(args[0], P_ATOM)
            return "{%s}^{T}" % a[0], a[1] + "<sup>T</sup>", P_POW
        if n == "log" and len(args) == 2:
            return r"\log_{%s}\left(%s\right)" % (args[1][0], args[0][0]), f"log<sub>{args[1][1]}</sub>({args[0][1]})", P_ATOM
        if n == "integral" and len(args) == 4:
            return r"\int_{%s}^{%s} %s \,\mathrm{d}%s" % (args[2][0], args[3][0], args[0][0], args[1][0]), \
                f"∫<sub>{args[2][1]}</sub><sup>{args[3][1]}</sup> {args[0][1]} d{args[1][1]}", P_MUL
        if n in ("sum", "prod") and len(args) == 4:
            big = r"\sum" if n == "sum" else r"\prod"
            return r"%s_{%s=%s}^{%s} %s" % (big, args[1][0], args[2][0], args[3][0], self._paren(args[0], P_MUL)[0]), \
                f"{'Σ' if n == 'sum' else 'Π'}<sub>{args[1][1]}={args[2][1]}</sub><sup>{args[3][1]}</sup> {args[0][1]}", P_MUL
        if n == "binom" and len(args) == 2:
            return r"{%s \choose %s}" % (args[0][0], args[1][0]), f"C({args[0][1]}, {args[1][1]})", P_ATOM
        ft = FUNC_TEX.get(n, r"\mathrm{%s}" % n.rstrip("_").replace("_", r"\_"))
        fh = FUNC_HTML.get(n, n.rstrip("_"))
        if len(args) == 1 and args[0][2] == P_ATOM and n in FUNC_TEX and isinstance(node.args[0], ast.Name) \
                and not self._is_subs(node.args[0]):
            return f"{ft} {args[0][0]}", f"{fh} {args[0][1]}", P_MUL
        return ft + r"\left(" + ", ".join(a[0] for a in args) + r"\right)", fh + "(" + ", ".join(a[1] for a in args) + ")", P_ATOM


def _const_value(node):
    try:
        if not any(isinstance(n, ast.Name) for n in ast.walk(node)):
            return float(E.evaluate(node, E.Ctx()))
    except (E.CalcError, TypeError, ValueError):
        pass
    return None


def to_tex(node, subs=None, lang="de"):
    return Renderer(subs, lang).go(node)[0]


def to_html(node, subs=None, lang="de"):
    return Renderer(subs, lang).go(node)[1]


def render(node, subs=None, lang="de"):
    return Renderer(subs, lang).go(node)


def plain(node) -> str:
    return ast.unparse(node).replace("**", "^").replace("if_(", "if(")


# ----------------------------------------------------------------------------- Umstellen
def _var_nodes(node):
    funcs = {id(n.func) for n in ast.walk(node) if isinstance(n, ast.Call)}
    return [n for n in ast.walk(node) if isinstance(n, ast.Name) and id(n) not in funcs]


def names_in(node) -> list[str]:
    seen = []
    for n in sorted(_var_nodes(node), key=lambda n: (getattr(n, "lineno", 0), getattr(n, "col_offset", 0))):
        if n.id not in seen:
            seen.append(n.id)
    return seen


def count(node, var) -> int:
    return sum(1 for n in _var_nodes(node) if n.id == var)


def _num(v):
    v = float(v)
    return ast.Constant(value=int(v) if v.is_integer() else v)


def _bin(a, op, b):
    return ast.BinOp(left=a, op=op, right=b)


def _call(name, *args):
    return ast.Call(func=ast.Name(id=name, ctx=ast.Load()), args=list(args), keywords=[])


_INV = {"sqrt": lambda o: _bin(o, ast.Pow(), _num(2)), "cbrt": lambda o: _bin(o, ast.Pow(), _num(3)),
        "exp": lambda o: _call("ln", o), "ln": lambda o: _call("exp", o),
        "log10": lambda o: _bin(_num(10), ast.Pow(), o), "log2": lambda o: _bin(_num(2), ast.Pow(), o),
        "sin": lambda o: _call("asin", o), "cos": lambda o: _call("acos", o), "tan": lambda o: _call("atan", o),
        "asin": lambda o: _call("sin", o), "acos": lambda o: _call("cos", o), "atan": lambda o: _call("tan", o),
        "sinh": lambda o: _call("asinh", o), "cosh": lambda o: _call("acosh", o), "tanh": lambda o: _call("atanh", o)}


def _neg(n):
    if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.USub):
        return n.operand
    return ast.UnaryOp(op=ast.USub(), operand=n)


def _iso(node, other, var):
    if isinstance(node, ast.Name) and node.id == var:
        return other
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return _iso(node.operand, _neg(other), var)
    if isinstance(node, ast.BinOp):
        L, R = count(node.left, var), count(node.right, var)
        op = type(node.op)
        if op is ast.Add:
            return _iso(node.left, _bin(other, ast.Sub(), node.right), var) if L else _iso(node.right, _bin(other, ast.Sub(), node.left), var)
        if op is ast.Sub:
            return _iso(node.left, _bin(other, ast.Add(), node.right), var) if L else _iso(node.right, _bin(node.left, ast.Sub(), other), var)
        if op is ast.Mult:
            return _iso(node.left, _bin(other, ast.Div(), node.right), var) if L else _iso(node.right, _bin(other, ast.Div(), node.left), var)
        if op is ast.Div:
            return _iso(node.left, _bin(other, ast.Mult(), node.right), var) if L else _iso(node.right, _bin(node.left, ast.Div(), other), var)
        if op is ast.Pow:
            if L:
                ev = _const_value(node.right)
                if ev is not None:
                    if abs(ev - 2) < 1e-12:
                        return _iso(node.left, _call("sqrt", other), var)
                    if abs(ev - 0.5) < 1e-12:
                        return _iso(node.left, _bin(other, ast.Pow(), _num(2)), var)
                    if abs(ev - 1) < 1e-12:
                        return _iso(node.left, other, var)
                    if abs(ev + 1) < 1e-12:
                        return _iso(node.left, _bin(_num(1), ast.Div(), other), var)
                    if abs(ev - 3) < 1e-12:
                        return _iso(node.left, _call("cbrt", other), var)
                inv = _bin(_num(1), ast.Div(), node.right) if _const_value(node.right) is None else _num(1 / _const_value(node.right))
                return _iso(node.left, _bin(other, ast.Pow(), inv), var)
            base = node.left
            if isinstance(base, ast.Name) and base.id == "e":
                return _iso(node.right, _call("ln", other), var)
            return _iso(node.right, _bin(_call("ln", other), ast.Div(), _call("ln", base)), var)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and len(node.args) == 1 and node.func.id in _INV:
        return _iso(node.args[0], _INV[node.func.id](other), var)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "log" and len(node.args) == 2 \
            and count(node.args[1], var) == 0:
        return _iso(node.args[0], _bin(node.args[1], ast.Pow(), other), var)
    raise ValueError("nicht umstellbar")


def isolate(lhs, rhs, var):
    """lhs = rhs nach var umstellen (var darf nur einmal vorkommen). -> AST oder None."""
    cl, cr = count(lhs, var), count(rhs, var)
    if cl + cr != 1:
        return None
    try:
        return _simplify(_iso(lhs, rhs, var) if cl else _iso(rhs, lhs, var))
    except ValueError:
        return None


def _simplify(n):
    """Kleine Aufraeumarbeiten: a/(b/c) -> a*c/b, -(-a) -> a, 1*a -> a."""
    if isinstance(n, ast.BinOp):
        n.left, n.right = _simplify(n.left), _simplify(n.right)
        if isinstance(n.op, ast.Div) and isinstance(n.right, ast.BinOp) and isinstance(n.right.op, ast.Div):
            return _simplify(_bin(_bin(n.left, ast.Mult(), n.right.right), ast.Div(), n.right.left))
        if isinstance(n.op, ast.Div) and isinstance(n.left, ast.BinOp) and isinstance(n.left.op, ast.Div):
            return _bin(n.left.left, ast.Div(), _bin(n.left.right, ast.Mult(), n.right))
        if isinstance(n.op, ast.Mult) and _const_value(n.left) == 1.0:
            return n.right
        if isinstance(n.op, (ast.Mult, ast.Div)) and _const_value(n.right) == 1.0:
            return n.left
        if isinstance(n.op, ast.Sub) and isinstance(n.right, ast.UnaryOp) and isinstance(n.right.op, ast.USub):
            return _bin(n.left, ast.Add(), n.right.operand)
        if isinstance(n.op, ast.Add) and isinstance(n.right, ast.UnaryOp) and isinstance(n.right.op, ast.USub):
            return _bin(n.left, ast.Sub(), n.right.operand)
        return n
    if isinstance(n, ast.UnaryOp):
        n.operand = _simplify(n.operand)
        if isinstance(n.op, ast.USub) and isinstance(n.operand, ast.UnaryOp) and isinstance(n.operand.op, ast.USub):
            return n.operand.operand
        if isinstance(n.op, ast.USub) and isinstance(n.operand, ast.BinOp) and isinstance(n.operand.op, ast.Sub):
            return _bin(n.operand.right, ast.Sub(), n.operand.left)
        return n
    if isinstance(n, ast.Call):
        n.args = [_simplify(a) for a in n.args]
    return n


def fix_locations(node):
    return ast.fix_missing_locations(ast.Expression(body=node)).body
