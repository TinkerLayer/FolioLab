"""Kleine Formel-Neuberechnung fuer die Arbeitsmappe (Spezifikation 6.2).

Rechnet alle Formeln einer openpyxl-Mappe nach, damit die App vor dem Ausliefern pruefen kann,
dass keine Formel einen Fehlerwert liefert. Beherrscht genau den Funktionsumfang, den der
Export verwendet. Unbekannte Funktionen gelten als Fehler (#NAME?).
"""
from __future__ import annotations

import math
import re

from openpyxl.utils import column_index_from_string, get_column_letter


class XlError(Exception):
    def __init__(self, code: str, where: str = ""):
        super().__init__(f"{code} {where}")
        self.code = code


_TOKEN = re.compile(r"""
    (?P<ws>\s+)
  | (?P<str>"(?:[^"]|"")*")
  | (?P<ref>(?:(?:'(?:[^']|'')+'|[A-Za-z_][\w.]*)!)?\$?[A-Z]{1,3}\$?\d+(?::\$?[A-Z]{1,3}\$?\d+)?)
  | (?P<num>\d+(?:\.\d*)?(?:[eE][+-]?\d+)?|\.\d+)
  | (?P<func>[A-Z][A-Z0-9._]*(?=\())
  | (?P<bool>TRUE|FALSE)
  | (?P<op><=|>=|<>|[-+*/^&=<>%])
  | (?P<lp>\()
  | (?P<rp>\))
  | (?P<sep>[,;])
""", re.VERBOSE)


def tokenize(s: str):
    pos, out = 0, []
    while pos < len(s):
        m = _TOKEN.match(s, pos)
        if not m:
            raise XlError("#PARSE!", s[pos:pos + 20])
        kind = m.lastgroup
        if kind != "ws":
            out.append((kind, m.group()))
        pos = m.end()
    return out


class Range:
    def __init__(self, values: list):
        self.values = values


class Book:
    def __init__(self, wb):
        self.wb = wb
        self.cache: dict = {}
        self.stack: set = set()

    # -- Zellen ---------------------------------------------------------------
    def cell(self, sheet: str, col: int, row: int):
        key = (sheet, col, row)
        if key in self.cache:
            return self.cache[key]
        if key in self.stack:
            raise XlError("#ZIRKEL!", f"{sheet}!{get_column_letter(col)}{row}")
        ws = self.wb[sheet]
        v = ws.cell(row=row, column=col).value
        if isinstance(v, str) and v.startswith("="):
            self.stack.add(key)
            try:
                v = Evaluator(self, sheet).run(v[1:])
            finally:
                self.stack.discard(key)
            if isinstance(v, Range):
                v = v.values[0] if v.values else None
        self.cache[key] = v
        return v

    def ref(self, sheet_default: str, text: str):
        if "!" in text:
            sh, addr = text.rsplit("!", 1)
            sh = sh[1:-1].replace("''", "'") if sh.startswith("'") else sh
        else:
            sh, addr = sheet_default, text
        if sh not in self.wb.sheetnames:
            raise XlError("#REF!", text)
        parts = addr.replace("$", "").split(":")
        c1, r1 = _split(parts[0])
        if len(parts) == 1:
            return self.cell(sh, c1, r1)
        c2, r2 = _split(parts[1])
        vals = [self.cell(sh, c, r) for r in range(min(r1, r2), max(r1, r2) + 1)
                for c in range(min(c1, c2), max(c1, c2) + 1)]
        return Range(vals)

    def check_all(self) -> list[tuple[str, str, str]]:
        """Alle Formeln neu berechnen. Rueckgabe: Liste (Blatt, Zelle, Fehler)."""
        errors = []
        for ws in self.wb.worksheets:
            for row in ws.iter_rows():
                for c in row:
                    if isinstance(c.value, str) and c.value.startswith("="):
                        try:
                            v = self.cell(ws.title, c.column, c.row)
                            if isinstance(v, float) and not math.isfinite(v):
                                raise XlError("#NUM!")
                        except XlError as e:
                            errors.append((ws.title, c.coordinate, e.code))
        return errors


def _split(a: str):
    m = re.match(r"([A-Z]{1,3})(\d+)", a)
    return column_index_from_string(m.group(1)), int(m.group(2))


def _num(v):
    if isinstance(v, Range):
        if len(v.values) != 1:
            raise XlError("#VALUE!")
        v = v.values[0]
    if v is None or v == "":
        return 0.0
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", "."))
    except ValueError:
        raise XlError("#VALUE!")


def _text(v) -> str:
    if isinstance(v, Range):
        v = v.values[0] if v.values else None
    if v is None:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, float):
        return f"{v:.15g}"
    return str(v)


def _nums(args):
    out = []
    for a in args:
        if isinstance(a, Range):
            out.extend(float(x) for x in a.values if isinstance(x, (int, float)) and not isinstance(x, bool))
        else:
            out.append(_num(a))
    return out


def _crit(spec):
    s = _text(spec)
    m = re.match(r"(<=|>=|<>|<|>|=)?(.*)", s)
    op, val = m.group(1) or "=", m.group(2)
    try:
        val = float(val)
    except ValueError:
        pass

    def test(x):
        if isinstance(val, float):
            if not isinstance(x, (int, float)) or isinstance(x, bool):
                return op == "<>"
            x = float(x)
        return {"=": x == val, "<>": x != val, "<": x < val, ">": x > val, "<=": x <= val, ">=": x >= val}[op]
    return test


def _cmp(a, b, op):
    if isinstance(a, Range):
        a = a.values[0]
    if isinstance(b, Range):
        b = b.values[0]
    a = "" if a is None else a
    b = "" if b is None else b
    if isinstance(a, str) != isinstance(b, str):
        # Excel: Zahlen < Text
        ka, kb = (1 if isinstance(a, str) else 0), (1 if isinstance(b, str) else 0)
        a, b = ka, kb
    return {"=": a == b, "<>": a != b, "<": a < b, ">": a > b, "<=": a <= b, ">=": a >= b}[op]


def _linreg(ys, xs):
    pairs = [(float(x), float(y)) for x, y in zip(xs.values, ys.values)
             if isinstance(x, (int, float)) and isinstance(y, (int, float))]
    n = len(pairs)
    if n < 2:
        raise XlError("#DIV/0!")
    mx = sum(p[0] for p in pairs) / n
    my = sum(p[1] for p in pairs) / n
    sxx = sum((p[0] - mx) ** 2 for p in pairs)
    syy = sum((p[1] - my) ** 2 for p in pairs)
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pairs)
    if sxx == 0:
        raise XlError("#DIV/0!")
    return mx, my, sxx, syy, sxy


def _fixed(x, nd=2, no_commas=False):
    x, nd = _num(x), int(_num(nd))
    s = f"{abs(x):,.{max(nd, 0)}f}"
    if no_commas:
        s = s.replace(",", "")
    s = s.replace(",", "'").replace(".", ",")  # Darstellung mit Dezimalkomma
    return ("-" if x < 0 else "") + s


def _index(rng, r, c=None):
    r = int(_num(r))
    if not isinstance(rng, Range) or r < 1 or r > len(rng.values):
        raise XlError("#REF!")
    return rng.values[r - 1]


def _match(v, rng, mode=1):
    mode = int(_num(mode))
    if mode != 0:
        raise XlError("#N/A")
    for i, x in enumerate(rng.values, 1):
        if isinstance(v, (int, float)) and isinstance(x, (int, float)) and float(x) == float(v):
            return float(i)
        if isinstance(v, str) and isinstance(x, str) and x.lower() == v.lower():
            return float(i)
    raise XlError("#N/A")


def _avgifs(avg, *crit):
    if len(crit) % 2:
        raise XlError("#VALUE!")
    tests = [(crit[i], _crit(crit[i + 1])) for i in range(0, len(crit), 2)]
    vals = []
    for k, v in enumerate(avg.values):
        if all(t(rng.values[k]) for rng, t in tests) and isinstance(v, (int, float)):
            vals.append(float(v))
    if not vals:
        raise XlError("#DIV/0!")
    return sum(vals) / len(vals)


def _if(c, a, b=False):
    return a if (_num(c) != 0 if not isinstance(c, bool) else c) else b


def _rsq(ys, xs):
    _, _, sxx, syy, sxy = _linreg(ys, xs)
    if syy == 0:
        raise XlError("#DIV/0!")
    return sxy * sxy / (sxx * syy)


FUNCS = {
    "ABS": lambda x: abs(_num(x)),
    "SQRT": lambda x: math.sqrt(_num(x)) if _num(x) >= 0 else (_ for _ in ()).throw(XlError("#NUM!")),
    "PI": lambda: math.pi,
    "ROUND": lambda x, n=0: round(_num(x), int(_num(n))),
    "MAX": lambda *a: max(_nums(a)) if _nums(a) else 0.0,
    "MIN": lambda *a: min(_nums(a)) if _nums(a) else 0.0,
    "SUM": lambda *a: sum(_nums(a)),
    "COUNT": lambda *a: float(len(_nums(a))),
    "AVERAGE": lambda *a: (sum(_nums(a)) / len(_nums(a))) if _nums(a) else (_ for _ in ()).throw(XlError("#DIV/0!")),
    "AND": lambda *a: all(_num(x) != 0 for x in a),
    "OR": lambda *a: any(_num(x) != 0 for x in a),
    "IF": _if,
    "INDEX": _index,
    "MATCH": _match,
    "SLOPE": lambda ys, xs: (lambda m: m[4] / m[2])(_linreg(ys, xs)),
    "INTERCEPT": lambda ys, xs: (lambda m: m[1] - m[4] / m[2] * m[0])(_linreg(ys, xs)),
    "RSQ": _rsq,
    "AVERAGEIFS": _avgifs,
    "FIXED": _fixed,
    "ISNUMBER": lambda x: isinstance(x, (int, float)) and not isinstance(x, bool),
}


_AST_CACHE: dict = {}


class Evaluator:
    """Zerlegt die Formel in einen Baum und wertet ihn aus (IF wertet nur den gewaehlten Zweig aus)."""

    def __init__(self, book: Book, sheet: str):
        self.book, self.sheet = book, sheet

    def run(self, formula: str):
        ast = _AST_CACHE.get(formula)
        if ast is None:
            self.toks = tokenize(formula)
            self.i = 0
            ast = self.comparison()
            if self.i != len(self.toks):
                raise XlError("#PARSE!", formula)
            _AST_CACHE[formula] = ast
        return self.ev(ast)

    # -- Parser ----------------------------------------------------------------
    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else (None, None)

    def take(self):
        if self.i >= len(self.toks):
            raise XlError("#PARSE!")
        t = self.toks[self.i]
        self.i += 1
        return t

    def _binary(self, ops, sub):
        a = sub()
        while self.peek()[0] == "op" and self.peek()[1] in ops:
            op = self.take()[1]
            a = ("bin", op, a, sub())
        return a

    def comparison(self):
        return self._binary(("=", "<>", "<", ">", "<=", ">="), self.concat)

    def concat(self):
        return self._binary(("&",), self.additive)

    def additive(self):
        return self._binary(("+", "-"), self.term)

    def term(self):
        return self._binary(("*", "/"), self.power)

    def power(self):
        return self._binary(("^",), self.unary)

    def unary(self):
        if self.peek() == ("op", "-"):
            self.take()
            return ("neg", self.unary())
        if self.peek() == ("op", "+"):
            self.take()
            return self.unary()
        return self.primary()

    def primary(self):
        kind, val = self.take()
        if kind == "num":
            return ("lit", float(val))
        if kind == "str":
            return ("lit", val[1:-1].replace('""', '"'))
        if kind == "bool":
            return ("lit", val == "TRUE")
        if kind == "ref":
            return ("ref", val)
        if kind == "lp":
            v = self.comparison()
            self.take()
            return v
        if kind == "func":
            name = val.upper().replace("_XLFN.", "")
            self.take()  # (
            args = []
            if self.peek()[0] != "rp":
                while True:
                    args.append(self.comparison())
                    if self.peek()[0] == "sep":
                        self.take()
                        continue
                    break
            self.take()  # )
            return ("fn", name, args)
        raise XlError("#PARSE!", val)

    # -- Auswertung ------------------------------------------------------------
    def ev(self, n):
        kind = n[0]
        if kind == "lit":
            return n[1]
        if kind == "ref":
            return self.book.ref(self.sheet, n[1])
        if kind == "neg":
            return -_num(self.ev(n[1]))
        if kind == "bin":
            op, a, b = n[1], self.ev(n[2]), self.ev(n[3])
            if op == "&":
                return _text(a) + _text(b)
            if op in ("=", "<>", "<", ">", "<=", ">="):
                return _cmp(a, b, op)
            a, b = _num(a), _num(b)
            if op == "+":
                return a + b
            if op == "-":
                return a - b
            if op == "*":
                return a * b
            if op == "/":
                if b == 0:
                    raise XlError("#DIV/0!")
                return a / b
            if op == "^":
                return a ** b
        if kind == "fn":
            name, args = n[1], n[2]
            if name == "IF":
                c = self.ev(args[0])
                cond = c if isinstance(c, bool) else _num(c) != 0
                if cond:
                    return self.ev(args[1]) if len(args) > 1 else True
                return self.ev(args[2]) if len(args) > 2 else False
            if name == "IFERROR":
                raise XlError("#NAME?", "IFERROR verdeckt Fehler und ist nicht erlaubt")
            fn = FUNCS.get(name)
            if fn is None:
                raise XlError("#NAME?", name)
            vals = [self.ev(a) for a in args]
            try:
                return fn(*vals)
            except XlError:
                raise
            except (TypeError, ValueError, ZeroDivisionError, AttributeError, IndexError) as e:
                raise XlError("#VALUE!", f"{name}: {e}")
        raise XlError("#PARSE!", str(n))
