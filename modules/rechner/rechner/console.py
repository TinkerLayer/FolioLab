"""Eine Zeile der Rechner-Konsole auswerten (zustandslos: Variablen und Funktionen schickt die Seite mit)."""
from __future__ import annotations

import ast
import copy
import math
import re

from fractions import Fraction

import numpy as np
from labcalc import deriv as D
from labcalc import solve as SV

from . import expr as E
from . import plots as P
from . import render as R
from . import units as U

RESERVED = set(E.BUILTINS) | set(E.SPECIAL) | {"i", "j", "inf", "nan", "ans"}


def _input_render(node, lang):
    try:
        return R.render(node, lang=lang)
    except Exception:  # noqa: BLE001 - Darstellung darf nie die Rechnung verhindern
        src = ast.unparse(node)
        return src, src


def _result_tex(v, lang):
    a = np.asarray(v)
    if isinstance(v, str):
        return r"\mbox{%s}" % v
    if a.ndim == 0:
        z = complex(a)
        if abs(z.imag) > 1e-14 * max(1, abs(z.real)):
            sign = "+" if z.imag >= 0 else "-"
            return f"{R.num_tex(z.real, lang, 8)} {sign} {R.num_tex(abs(z.imag), lang, 8)}\\,\\mathrm{{i}}"
        return R.num_tex(z.real, lang, 8)
    if a.ndim == 1:
        a = a.reshape(1, -1)

    def cell(x):
        z = complex(x)
        if abs(z.imag) <= 1e-14 * max(1, abs(z.real)):
            return R.num_tex(z.real, lang, 6)
        im = R.num_tex(abs(z.imag), lang, 6) + r"\,\mathrm{i}"
        if abs(z.real) <= 1e-14 * max(1, abs(z.imag)):
            return ("-" if z.imag < 0 else "") + im
        return f"{R.num_tex(z.real, lang, 6)} {'+' if z.imag >= 0 else '-'} {im}"
    rows = [" & ".join(cell(x) for x in r) for r in a.tolist()]
    return r"\left(\begin{array}{%s}" % ("c" * a.shape[1]) + r" \\ ".join(rows) + r"\end{array}\right)"


def expand_derivs(node, ctx, out, lang="de"):
    """f'(x), f''(x) und diff(…, x[, n]) durch ihre symbolische Ableitung ersetzen (labcalc.deriv); ohne Regel bleibt
    eine numerische Ableitung stehen, die Zeile bekommt dann einen Hinweis."""
    if not D.has_deriv(node):
        return node
    new, numeric = D.expand(node, ctx.funcs, ctx.angle)
    out["deriv"] = True
    if numeric:
        _note(out, ctx, D.NUMERIC_NOTE.get(lang, D.NUMERIC_NOTE["de"]).format(t=", ".join(numeric)))
    return D.simplify(new)


def evaluate_safe(req: dict) -> dict:
    """evaluate_line für die Schnittstelle: jeder Fehler kommt als {"error": …} zurück, nie als Ausnahme."""
    try:
        out = evaluate_line(req)
    except Exception as e:  # noqa: BLE001 - die Seite zeigt die Meldung an der Zeile
        return {"input": str(req.get("line", "")), "error": str(e) or type(e).__name__}
    out.pop("_node", None)                                   # Syntaxbaum: nur für Folgezeilen im Prozess
    return out


def _split_names(name, known):
    """AB -> [A, B], wenn der Name ganz aus bekannten Namen besteht (mindestens zwei); sonst None."""
    def go(s):
        if s in known:
            return [s]
        for k in range(len(s) - 1, 0, -1):
            if s[:k] in known:
                rest = go(s[k:])
                if rest:
                    return [s[:k], *rest]
        return None
    if name in known:
        return None
    parts = go(name)
    return parts if parts and len(parts) >= 2 else None


def split_product(st, defined):
    """``AB = C`` (AB und C frei) oder ``C = AB`` (AB frei) mit lauter definierten Faktoren -> (Faktoren, Ziel)."""
    if st[0] != "assign" or not re.fullmatch(r"[^\W\d]\w*", st[2].strip()):
        return None
    name, body = E.norm_name(st[1]), E.norm_name(st[2].strip())
    if body in RESERVED or body in U.CONSTANTS or body in E.BUILTINS:
        return None
    if name in defined and body not in defined:              # AB gibt es schon: AB = C legt nur C an
        return [name], body
    left, right = _split_names(name, defined), _split_names(body, defined)
    if left and not right and body not in defined:
        return left, body
    if right and not left:
        return right, name
    return None


def product_note(parts, lang):
    shown = "·".join(E.plain_name(p) for p in parts)
    joined = "".join(E.plain_name(p) for p in parts)
    return f"{joined} als Produkt {shown} gelesen" if lang == "de" else f"{joined} read as the product {shown}"


def _product_statement(st, ctx, out, lang):
    """AB = C mit definierten Matrizen A, B und ohne Namen AB: wie A*B = C."""
    try:
        hit = split_product(st, set(ctx.names))
    except E.CalcError:
        return st
    if not hit or not any(np.ndim(ctx.names[p]) > 0 for p in hit[0]):
        return st
    if len(hit[0]) > 1:
        out["notes"] = [product_note(hit[0], lang)]
    return ("assign", hit[1], "*".join(hit[0]))


_EVAL_ERRS = (E.CalcError, U.UnitError, E.DimError, ValueError, TypeError, ArithmeticError, IndexError, np.linalg.LinAlgError)


def _assigns_right(L, Rn, ctx) -> bool:
    """inv(A) = Q, det(A) = d: links steht ein fertiger Wert, rechts ein Name. Ein freier Name wird zugewiesen, ein
    vorhandener nur bei Matrix oder Liste (wie A*B = C); eine Zahl = vorhandener Name bleibt eine Prüfung."""
    if not isinstance(Rn, ast.Name) or Rn.id in RESERVED or Rn.id in U.CONSTANTS or SV.free_names(L, ctx):
        return False
    try:
        v = E.evaluate(L, ctx)
    except _EVAL_ERRS:
        return False
    if isinstance(v, str):
        return False
    return Rn.id not in ctx.names or np.ndim(v) > 0


def solve_matrix(A, B, where, lang="de"):
    """A·X = B (where="left") oder X·A = B (where="right") nach X; singuläre und widersprüchliche Fälle als Meldung."""
    de = lang == "de"
    A, B = np.asarray(A), np.asarray(B)
    row = B.ndim == 1
    Bm = B.reshape(-1, 1) if row and where == "left" else B.reshape(1, -1) if row else B
    Am, Bm = (A, Bm) if where == "left" else (A.T, Bm.T)
    if Am.shape[0] != Bm.shape[0]:
        raise E.CalcError(f"Grössen passen nicht: {A.shape} und {B.shape}" if de else f"sizes do not fit: {A.shape} and {B.shape}")
    ra, rb = int(np.linalg.matrix_rank(Am)), int(np.linalg.matrix_rank(np.hstack([Am, Bm])))
    if rb > ra:
        raise E.CalcError(f"Keine Lösung: das System ist widersprüchlich (Rang der Matrix {ra}, mit rechter Seite {rb})" if de
                          else f"No solution: the system is inconsistent (rank {ra}, with right-hand side {rb})")
    if ra < Am.shape[1]:
        raise E.CalcError(f"Keine eindeutige Lösung: die Matrix ist singulär (Rang {ra} bei {Am.shape[1]} Spalten), "
                          "es gibt unendlich viele Lösungen" if de else
                          f"No unique solution: the matrix is singular (rank {ra} with {Am.shape[1]} columns), "
                          "there are infinitely many solutions")
    X = np.linalg.solve(Am, Bm) if Am.shape[0] == Am.shape[1] else np.linalg.lstsq(Am, Bm, rcond=None)[0]
    size = float(np.max(np.abs(X))) if X.size else 0.0
    X = np.where(np.abs(X) <= 1e-12 * size, 0.0, X)
    if where == "right":
        X = X.T
    return X.ravel() if row else X


def _matrix_unknown(L, Rn, ctx, lang, out, digits):
    """A*X = B oder X*A = B mit freiem X: Ergebnis wie eine Zuweisung an X, sonst None."""
    free = SV.free_names(SV.residual(L, Rn), ctx)
    if len(free) != 1:
        return None
    x = free[0]
    for side, other in ((L, Rn), (Rn, L)):
        if not (isinstance(side, ast.BinOp) and isinstance(side.op, ast.Mult)) or SV._has(other, x):
            continue
        if isinstance(side.right, ast.Name) and side.right.id == x and not SV._has(side.left, x):
            coef, where = side.left, "left"
        elif isinstance(side.left, ast.Name) and side.left.id == x and not SV._has(side.right, x):
            coef, where = side.right, "right"
        else:
            continue
        try:
            A, B = E.evaluate(coef, ctx), E.evaluate(other, ctx)
        except _EVAL_ERRS:
            return None
        if isinstance(A, str) or isinstance(B, str) or np.ndim(A) != 2 or np.ndim(B) == 0:
            return None
        X = solve_matrix(A, B, where, lang)
        (tl, hl), (tr_, hr) = _input_render(L, lang), _input_render(Rn, lang)
        out.update(kind="assign", name=x, result=E.describe(X, digits), store=E.to_json(X),
                   html=f"{hl} = {hr} ⇒ {R.sym_html(x)}", tex=rf"{tl} = {tr_} \;\Rightarrow\; {R.sym_tex(x)}",
                   result_tex=_result_tex(X, lang))
        if _has_dims(coef, ctx) or _has_dims(other, ctx):
            da, db = node_dims(coef, ctx), node_dims(other, ctx)
            d = U.ddiv(db, da) if da is not None and db is not None else None
            if d is None:
                out["unit"] = UNKNOWN_UNIT
                _note(out, ctx, UNKNOWN_NOTE)
            elif not U.deq(d, U.D0):
                out["unit"], out["dims"] = _si_text(d), list(d)
                out["result_tex"] += r"\," + R.unit_tex(unit_plain(out["unit"]))
        _note(out, ctx)
        return out
    return None


def evaluate_line(req: dict) -> dict:
    typed = str(req.get("line", "")).strip()
    lang = req.get("lang", "de")
    if not typed:
        raise E.CalcError("Leere Eingabe")
    ctx = P.make_ctx(req)
    if "ans" in (req.get("vars") or {}):
        ctx.names["ans"] = E.from_json(req["vars"]["ans"])
    line = E.rewrite_ddx(typed, set(ctx.names) | set(ctx.funcs))     # d/dx(x^3) -> diff(x^3, x)
    st = E.split_statement(line)
    out = {"input": typed}
    callables = ctx.callables()
    symb = {k: v for k, v in (req.get("symbolic") or {}).items() if k not in ctx.names}   # RC-01 (nur im Prozess)
    if req.get("products", True):                            # die Blätter entscheiden das vorab für die ganze Seite
        st = _product_statement(st, ctx, out, lang)
    if st[0] == "system":                                    # S-02: x + y = 3; x − y = 1
        pairs = [(E.parse(a, callables), E.parse(b, callables)) for a, b in st[1]]
        return solve_system_line(pairs, ctx, req, lang, out)
    if st[0] == "equation":                                  # S-01: x^2 − 3 + x = 0
        _, ls, rs, extras, unit = st
        L, Rn = E.parse(ls, callables), E.parse(rs, callables)
        if not extras and unit is None and _assigns_right(L, Rn, ctx):
            st = ("assign", Rn.id, ls)                       # inv(A) = Q: Zuweisung nach rechts
        else:
            if not extras and unit is None:
                done = _matrix_unknown(L, Rn, ctx, lang, out, int(req.get("digits", 10)))
                if done is not None:
                    return done
            return solve_line(L, Rn, extras, unit, ctx, req, lang, out, callables)
    if st[0] == "assign":                                    # x = 2x − 3, x^2 = x: Gleichung, wenn sonst nichts ginge
        _, name, body = st
        try:
            nm, bnode = E.norm_name(name), inline_symbolic(E.parse(body, callables), symb)
        except E.CalcError:
            nm = bnode = None
        if bnode is not None and SV.free_names(bnode, ctx):
            nn = ast.Name(id=nm, ctx=ast.Load())
            if len(SV.free_names(SV.residual(nn, bnode), ctx)) == 1:
                s = line
                for g, n in E.GREEK.items():
                    s = s.replace(g, n)
                L, Rn = (nn, bnode) if E.ASSIGN.match(s) else (bnode, nn)
                done = _matrix_unknown(L, Rn, ctx, lang, out, int(req.get("digits", 10)))      # A*X = B
                if done is not None:
                    return done
                return solve_line(L, Rn, [], None, ctx, req, lang, out, callables)
    if st[0] == "func":
        _, name, args, body = st
        name = E.norm_name(name)
        if name in E.BUILTINS or name in E.SPECIAL:
            raise E.CalcError(f"„{name}“ ist eine eingebaute Funktion")
        node = E.parse(body, callables | {name})
        tex, html = _input_render(node, lang)
        if D.has_deriv(node):                                # g(x) = f'(x): die Ableitung gleich dahinter zeigen
            try:
                dn = expand_derivs(node, ctx, out, lang)
                dt, dh = _input_render(dn, lang)
                tex, html = f"{tex} = {dt}", f"{html} = {dh}"
            except E.CalcError:
                pass
        arg_html = ", ".join(R.sym_html(a) for a in args)
        out.update(kind="func", name=name, args=args, body=body,
                   html=f"{R.sym_html(name).replace('<i>', '').replace('</i>', '')}({arg_html}) = {html}",
                   tex=f"\\mathrm{{{name}}}({', '.join(R.sym_tex(a) for a in args)}) = {tex}",
                   text=f"Funktion {name}({', '.join(args)}) definiert")
        return out
    if st[0] == "assign":
        _, name, body = st
        name = E.norm_name(name)
        if name in RESERVED or name in U.CONSTANTS:
            raise E.CalcError(f"„{name}“ ist reserviert")
        shown = E.parse(body, callables)
        node = expand_derivs(inline_symbolic(shown, symb), ctx, out, lang)
        free = SV.free_names(node, ctx)
        if free:                                                 # RC-01: noch nicht definierte Namen bleiben stehen
            return _symbolic(out, name, node, free, ctx, lang, shown)
        val = E.evaluate(node, ctx)
        d = E.describe(val, int(req.get("digits", 10)))
        tex, html = _input_render(shown if out.get("deriv") else node, lang)
        out.update(kind="assign", name=name, result=d, store=E.to_json(val),
                   html=f"{R.sym_html(name)} = {html}", tex=f"{R.sym_tex(name)} = {tex}",
                   result_tex=_result_tex(val, lang))
        unit = _dims_unit(node, ctx)
        if unit == UNKNOWN_UNIT:
            out["unit"] = unit
            _note(out, ctx, UNKNOWN_NOTE)
        elif unit:
            out["unit"] = unit
            out["dims"] = list(node_dims(node, ctx))            # die Variable behält ihre Einheit in späteren Zeilen
            out["result_tex"] += r"\," + R.unit_tex(unit_plain(unit))
            if U.deq(out["dims"], U.parse_unit("K")[1]):
                out["tdiff"] = temp_weight(node, ctx) == 0     # Temperaturdifferenz (T2 − T1): später ohne Nullpunkt
        _add_parts(out, node, ctx, val, lang)
        _parts_known(out)
        _note(out, ctx)
        return out
    if st[0] == "convert":
        _, body, unit = st
        node = E.parse(body, callables)
        val = E.evaluate(node, ctx)
        target, delta = U.split_delta(unit)
        f, d, off = U.parse_unit(target)
        dn = node_dims(node, ctx)
        if dn is not None and not U.deq(dn, d):
            raise E.CalcError(f"Ergebnis hat die Einheit {U.dims_text(dn) or '1'}, nicht {target}")
        diff = delta
        if off and not delta:                                  # °C, °F: Temperatur oder Temperaturdifferenz?
            w = temp_weight(node, ctx)
            if w == 0:
                diff = True
                _note(out, ctx, f"als Temperaturdifferenz umgerechnet (ohne Nullpunkt): 1 K = 1 {target}"
                      if target == "°C" else f"als Temperaturdifferenz umgerechnet (ohne Nullpunkt, Faktor {E.fmt_num(1 / f, 6)})")
            elif w is None or abs(w - 1) > 1e-12:
                _note(out, ctx, f"als Temperatur umgerechnet (mit Nullpunkt); für eine Differenz „-> Δ{target}“ schreiben")
        conv = U.from_si(E.real_values(val, "Umrechnung"), target, diff)
        dd = E.describe(conv, int(req.get("digits", 10)))
        tex, html = _input_render(node, lang)
        shown = ("Δ" + target) if diff and off else target
        out.update(kind="expr", result=dd, store=E.to_json(conv), unit=shown, html=html + " → " + R.unit_html(shown),
                   tex=tex, result_tex=_result_tex(conv, lang) + r"\," + (r"\Delta " if diff and off else "") + R.unit_tex(target))
        _note(out, ctx)
        return out
    shown = E.parse(st[1], callables)
    node = expand_derivs(inline_symbolic(shown, symb), ctx, out, lang)
    free = SV.free_names(node, ctx) if symb or req.get("partial") or out.get("deriv") else []
    if free and _symbolic(out, None, node, free, ctx, lang, shown) is not None:
        return out
    val = E.evaluate(node, ctx)
    d = E.describe(val, int(req.get("digits", 10)))
    tex, html = _input_render(shown if out.get("deriv") else node, lang)
    out.update(kind="expr", result=d, store=E.to_json(val) if not isinstance(val, str) else None, html=html, tex=tex,
               result_tex=_result_tex(val, lang))
    unit = _dims_unit(node, ctx)
    if unit == UNKNOWN_UNIT:
        out["unit"] = unit
        _note(out, ctx, UNKNOWN_NOTE)
    elif unit:
        out["unit"] = unit
        out["dims"] = list(node_dims(node, ctx))                # für ans in der nächsten Zeile
        out["result_tex"] += r"\," + R.unit_tex(unit_plain(unit))
    _add_parts(out, node, ctx, val, lang)
    _parts_known(out)
    _note(out, ctx)
    return out


# ----------------------------------------------------------------------------- RC-01: Teilauswertung
_KEEP_SYM = {"pi", "e"}


def inline_symbolic(node, symbolic):
    """Namen, die eine Zeile davor nur symbolisch bestimmt hat (z = y + x, x offen), durch ihren Ausdruck ersetzen."""
    if not symbolic:
        return node

    class _In(ast.NodeTransformer):
        def visit_Call(self, n):
            n.args = [self.visit(a) for a in n.args]             # Funktionsnamen nie ersetzen
            return n

        def visit_Name(self, n):
            if n.id in symbolic:
                return copy.deepcopy(symbolic[n.id])
            return n
    return _In().visit(copy.deepcopy(node))


def partial(node, ctx, lang="de", digits=5, free=None, subs=None):
    """(tex, html) des Ausdrucks mit allen bekannten Teilen ausgerechnet (Zahl mit SI-Einheit); Namen ohne Wert
    bleiben stehen: z = y + x mit y = 5 -> 5 + x. `subs`: Namen, die mit eigener Darstellung eingesetzt werden
    (Formelkarte: Wert in der eingegebenen Einheit)."""
    free = set(free if free is not None else SV.free_names(node, ctx))
    subs = dict(subs or {})
    count = [0]

    def names(n):
        funcs = {id(c.func) for c in ast.walk(n) if isinstance(c, ast.Call)}
        return [m.id for m in ast.walk(n) if isinstance(m, ast.Name) and id(m) not in funcs]

    def fold(n):
        if isinstance(n, ast.Constant):
            return n
        if isinstance(n, ast.Name) and n.id in subs:
            return n
        ns = names(n)
        if not (set(ns) & free) and not set(ns) <= _KEEP_SYM:
            try:
                v = E.evaluate(n, ctx)
            except (E.CalcError, TypeError, ValueError, ZeroDivisionError, OverflowError):
                v = None
            if v is not None and not isinstance(v, str) and np.ndim(v) == 0 and abs(np.imag(complex(v))) < 1e-14 * max(1.0, abs(complex(v))):
                v = float(np.real(complex(v)))
                unit = _dims_unit(n, ctx)
                u = "" if unit in (None, UNKNOWN_UNIT) else unit_plain(unit)
                count[0] += 1
                key = f"_k{count[0]}"
                subs[key] = (R.qty_tex(v, u, lang, digits) if u else R.num_tex(v, lang, digits),
                             R.qty_html(v, u, lang, digits) if u else R.num_html(v, lang, digits),
                             R.P_NEG if v < 0 else (R.P_MUL if u else R.P_ATOM))
                return ast.Name(id=key, ctx=ast.Load())
            return n                                            # Liste oder nicht auswertbar: so stehen lassen
        if isinstance(n, ast.Call):
            n.args = [fold(a) for a in n.args]
            return n
        for field, old in ast.iter_fields(n):
            if isinstance(old, list):
                setattr(n, field, [fold(x) if isinstance(x, ast.expr) else x for x in old])
            elif isinstance(old, ast.expr):
                setattr(n, field, fold(old))
        return n
    return R.render(fold(copy.deepcopy(node)), subs, lang)


def _symbolic(out, name, node, free, ctx, lang, shown=None):
    """Ergebnis einer Zeile mit noch nicht definierten Namen: der Ausdruck mit allem Bekannten eingesetzt."""
    tex, html = _input_render(shown if shown is not None else node, lang)
    pt, ph = partial(node, ctx, lang, free=free)
    if not name and pt == tex:
        return None                                           # nichts eingesetzt: Ausdruckszeile bleibt ein Fehler
    lt, lh = (R.sym_tex(name) + " = ", R.sym_html(name) + " = ") if name else ("", "")
    names = ", ".join(free)
    if out.get("deriv"):                                      # f'(x) mit offenem x: die Ableitung als Term
        text = f"symbolische Ableitung, {names} ohne Wert" if lang == "de" else f"symbolic derivative, {names} without a value"
    else:
        text = (f"{names} noch nicht definiert: Ergebnis mit {names}" if lang == "de"
                else f"{names} not defined yet: result in terms of {names}")
    out.update(kind="symbolic", name=name, free=list(free), html=lh + html, tex=lt + tex,
               partial_html=ph, partial_tex=pt, result_tex=pt, same=pt == tex, text=text)
    out["_node"] = node                                       # für spätere Zeilen (nur im Prozess, nicht als JSON)
    return out


UNKNOWN_UNIT = "?"
UNKNOWN_NOTE = ("Einheit unbekannt: der Ausdruck enthält Grössen mit Einheit, deren Einheit hier nicht weitergegeben "
                "wird (z. B. Liste mit verschiedenen Einheiten, Matrixfunktion, eigene Funktion, Summe ungleicher "
                "Einheiten); der Wert ist in SI")


def _parts_known(out):
    """linreg mit Einheiten: die Teile k, d, R² tragen je ihre Einheit, also keine „unbekannte“ Gesamteinheit."""
    if out.get("parts") and out.get("unit") == UNKNOWN_UNIT:
        out.pop("unit", None)
        if UNKNOWN_NOTE in (out.get("notes") or []):
            out["notes"].remove(UNKNOWN_NOTE)
            if not out["notes"]:
                out.pop("notes")


def _note(out, ctx, text=None):
    """Hinweis an die Zeile hängen (ohne Doppelte); ohne text: Hinweise der Analysis-Funktionen übernehmen."""
    notes = out.setdefault("notes", [])
    for t in ([text] if text else list(getattr(ctx, "notes", []) or [])):
        if t and t not in notes:
            notes.append(t)
    if not notes:
        out.pop("notes", None)


_K_DIMS = U.parse_unit("K")[1]


def temp_weight(node, ctx):
    """Affines Gewicht eines Ausdrucks in K: 1 = Temperatur (Punkt der Skala), 0 = Temperaturdifferenz, None = unklar.

    Regeln: eine Grösse der Art „Temperatur“, die Konstante T0 und Zeilenvariablen in K ohne weitere Angabe zählen 1,
    eine „Temperaturdifferenz“ (Grössenart oder Zeilenvariable aus einer Differenz) und alles ohne K zählt 0;
    a ± b addiert bzw. subtrahiert die Gewichte, Zahl·a und a/Zahl skalieren sie, mean/min/max/median übernehmen das
    gemeinsame Gewicht. T2 − T1 hat damit 0 (Differenz), (T1 + T2)/2 hat 1 (Temperatur)."""
    kinds = getattr(ctx, "kinds", None) or {}
    tdiff = getattr(ctx, "tdiff", None) or set()

    def num(n):
        if not E._bare(n):
            return None
        try:
            v = E.evaluate(n, E.Ctx())
            return float(v) if np.ndim(v) == 0 and np.isreal(v) else None
        except (E.CalcError, TypeError, ValueError):
            return None

    def w(n):
        t = type(n)
        if t is ast.Constant:
            return 0.0
        if t is ast.Name:
            if n.id in tdiff or kinds.get(n.id) == "temp_diff":
                return 0.0
            if kinds.get(n.id) == "temperature" or n.id == "T0":
                return 1.0
            dn = ctx.dims.get(n.id)
            return 1.0 if dn is not None and U.deq(dn, _K_DIMS) else 0.0
        if t is ast.UnaryOp:
            v = w(n.operand)
            return None if v is None else (-v if isinstance(n.op, ast.USub) else v)
        if t is ast.BinOp:
            a, b = w(n.left), w(n.right)
            if a is None or b is None:
                return None
            if isinstance(n.op, ast.Add):
                return a + b
            if isinstance(n.op, ast.Sub):
                return a - b
            if a == 0 and b == 0:
                return 0.0
            if isinstance(n.op, ast.Mult):
                if a == 0:
                    c = num(n.left)
                    return None if c is None else c * b
                if b == 0:
                    c = num(n.right)
                    return None if c is None else c * a
                return None
            if isinstance(n.op, ast.Div) and b == 0:
                c = num(n.right)
                return None if not c else a / c
            return None
        if t is ast.Subscript:
            return w(n.value)
        if t in (ast.List, ast.Tuple):
            ws = [w(e) for e in n.elts]
            return ws[0] if ws and all(x is not None and x == ws[0] for x in ws) else (0.0 if not ws else None)
        if t is ast.Call and isinstance(n.func, ast.Name):
            ws = [w(a) for a in n.args]
            if n.func.id in ("mean", "median", "min", "max", "sort") and ws:
                return ws[0] if all(x is not None and x == ws[0] for x in ws) else None
            if n.func.id == "abs" and ws:
                return ws[0] if ws[0] in (0.0, 1.0) else None
            return 0.0 if all(x == 0 for x in ws) else None
        return None

    return w(node)


# ----------------------------------------------------------------------------- Gleichungen lösen (S-01, S-02)
def _fr_text(fr: Fraction) -> str:
    s = str(abs(fr.numerator)) if fr.denominator == 1 else f"{abs(fr.numerator)}/{fr.denominator}"
    return ("−" if fr < 0 else "") + s


def _fr_tex(fr: Fraction) -> str:
    s = str(abs(fr.numerator)) if fr.denominator == 1 else r"\frac{%d}{%d}" % (abs(fr.numerator), fr.denominator)
    return ("-" if fr < 0 else "") + s


def _surd(sd: dict, tex: bool, sign=None) -> str:
    """p ± q·√m (·i) als gemeinsamer Bruch: (A ± B√m)/n. sign: −1, +1 oder None für ±."""
    p, q, m, im = sd["p"], sd["q"], sd["m"], sd.get("i")
    sign = sd.get("sign") if sign is None and "sign" in sd else sign
    den = p.denominator * q.denominator // math.gcd(p.denominator, q.denominator)
    A, B = int(p * den), int(q * den)
    root = "" if m == 1 else (r"\sqrt{%d}" % m if tex else f"√{m}")
    imag = (r"\mathrm{i}" if tex else "i") if im else ""
    term = ("" if B == 1 and (root or imag) else str(B)) + root + imag
    op = (r"\pm" if tex else "±") if sign is None else ("-" if tex else "−") if sign < 0 else "+"
    if A == 0:
        num = ("" if op == "+" else op) + term
    else:
        num = f"{'-' if tex and A < 0 else '−' if A < 0 else ''}{abs(A)} {op} {term}"
    if den == 1:
        return num
    if tex:
        return r"\frac{%s}{%d}" % (num, den)
    return f"{num}/{den}" if A == 0 else f"({num})/{den}"


def _exact_of(s: dict):
    """(Text, TeX) der exakten Form einer Lösung oder (None, None), wenn sie nichts Neues zeigt."""
    if s.get("surd"):
        return _surd(s["surd"], False), _surd(s["surd"], True)
    fr = s.get("exact")
    if isinstance(fr, Fraction) and fr.denominator != 1:
        return _fr_text(fr), _fr_tex(fr)
    return None, None


def _check(L, Rn, ctx, lang, out, digits):
    """Gleichung ohne Unbekannte: stimmt sie?"""
    a, b = E.evaluate(L, ctx), E.evaluate(Rn, ctx)
    try:
        A, B = np.asarray(a, dtype=complex), np.asarray(b, dtype=complex)
        same = A.shape == B.shape and bool(np.allclose(A, B, rtol=1e-10, atol=1e-12))
    except (TypeError, ValueError):
        same = a == b
    word = "wahr" if same else "falsch"
    out.update(kind="check", truth=same, result={"type": "bool", "text": word, "value": float(same)}, store=None,
               result_tex=r"\mbox{%s}" % word, notes=[])
    if not same and np.ndim(a) == 0 and np.ndim(b) == 0:
        out["notes"].append(f"links {E.describe(a, digits)['text']}, rechts {E.describe(b, digits)['text']}")
        used = [n.id for side in (L, Rn) for n in ast.walk(side) if isinstance(n, ast.Name) and n.id in ctx.names]
        if used:
            out["notes"].append(f"{used[0]} hat schon einen Wert – zum Lösen nach {used[0]} „, {used[0]}“ anhängen")
    return out


def _sets_for(groups, unk, dims, pick):
    """Zeilenvariablen: eine Lösung -> x (und y …); mehrere -> x_1, x_2 … und, wenn gewählt, x."""
    sets = []
    dl = {u: (list(dims[u]) if dims.get(u) is not None and not U.deq(dims[u], U.D0) else None) for u in unk}
    if len(groups) == 1:
        for u, v in zip(unk, groups[0]):
            sets.append({"name": u, "store": E.to_json(v), "dims": dl[u], "unit": U.dims_text(dl[u]) if dl[u] else ""})
        return sets, None
    for k, g in enumerate(groups, 1):
        for u, v in zip(unk, g):
            sets.append({"name": f"{u}_{k}", "store": E.to_json(v), "dims": dl[u], "unit": U.dims_text(dl[u]) if dl[u] else ""})
    try:
        p = int(pick) if pick is not None else None
    except (TypeError, ValueError):
        p = None
    if p is not None and 1 <= p <= len(groups):
        for u, v in zip(unk, groups[p - 1]):
            sets.append({"name": u, "store": E.to_json(v), "dims": dl[u], "unit": U.dims_text(dl[u]) if dl[u] else ""})
        return sets, p
    return sets, None


def solve_line(L, Rn, extras, unit, ctx, req, lang, out, callables):
    """S-01: Gleichung mit einer Unbekannten lösen; Zusätze nach Kommas: Bedingungen oder die gesuchte Grösse."""
    conds, want = [], []
    for x in extras:
        n = E.parse(x, callables)
        if isinstance(n, ast.Name):
            want.append(n.id)
        elif isinstance(n, (ast.Compare, ast.BoolOp)):
            conds.append(n)
        else:
            raise E.CalcError("Nach dem Komma steht eine Bedingung (x > 0) oder die gesuchte Grösse (x)")
    for w in want:                                           # „…, x“: nach x lösen, auch wenn x schon einen Wert hat
        ctx.names.pop(w, None)
        ctx.dims.pop(w, None)
    L0, R0 = L, Rn                                           # f'(x) = 3: mit der Ableitung rechnen, so zeigen
    L, Rn = expand_derivs(L, ctx, out, lang), expand_derivs(Rn, ctx, out, lang)
    free = SV.free_names(SV.residual(L, Rn), ctx)
    if want:
        rest = [f for f in free if f not in want]
        if rest:
            raise E.CalcError(f"Unbekannter Name „{rest[0]}“")
        free = [w for w in want if w in free] or want
    for c in conds:
        bad = [f for f in SV.free_names(c, ctx) if f not in free]
        if bad:
            raise E.CalcError(f"Unbekannter Name „{bad[0]}“ in der Bedingung")
    (tl, hl), (tr_, hr) = _input_render(L0, lang), _input_render(R0, lang)
    cr = [_input_render(c, lang) for c in conds]
    out["html"] = f"{hl} = {hr}" + "".join(f", {h}" for _, h in cr)
    out["tex"] = f"{tl} = {tr_}" + "".join(r",\quad " + t for t, _ in cr)
    digits = int(req.get("digits", 10))
    if not free:
        return _check(L, Rn, ctx, lang, out, digits)
    if len(free) > 1:
        raise E.CalcError(f"{len(free)} Unbekannte ({', '.join(free)}) in einer Gleichung – für ein Gleichungssystem "
                          "die Gleichungen mit ; trennen, z. B. x + y = 3; x − y = 1")
    x = free[0]
    res = SV.solve_equation(L, Rn, x, ctx, conds)
    dims = res.get("dims")
    si_unit = U.dims_text(dims) if dims is not None and not U.deq(dims, U.D0) else ""
    show = si_unit
    conv = None
    if unit:
        _f, d, _off = U.parse_unit(unit)
        if dims is not None and not U.deq(dims, d):
            raise E.CalcError(f"Die Lösung hat die Einheit {si_unit or '1'}, nicht {unit}")
        show = unit
        conv = lambda v: float(U.from_si(np.asarray(v, dtype=float), unit))       # noqa: E731
    sols = res["solutions"]
    n = len(sols)
    names = [x] if n == 1 else [f"{x}_{k}" for k in range(1, n + 1)]
    items, vals = [], []
    for nm, s in zip(names, sols):
        v = s["value"]
        vv = conv(v) if conv and not isinstance(v, complex) else v
        d = E.describe(vv, digits)
        ex_text, ex_tex = (None, None) if conv else _exact_of(s)
        items.append({"name": nm, "text": d["text"], "value": E._jnum(vv) if not isinstance(vv, complex) else None,
                      "exact": ex_text, "mult": s.get("mult", 1)})
        num = (R.num_tex(vv, lang, 8) if not isinstance(vv, complex) else _result_tex(vv, lang)) + \
            (r"\," + R.unit_tex(unit_plain(show)) if show else "")
        items[-1]["tex"] = f"{R.sym_tex(nm)} = " + (f"{ex_tex} \\approx {num}" if ex_tex else num)
        vals.append(v)
    sets, picked = _sets_for([[v] for v in vals], [x], {x: dims}, req.get("pick"))
    notes = list(out.get("notes") or []) + list(res.get("notes") or [])
    if any(it["mult"] > 1 for it in items):
        notes.append("doppelte Lösung" if all(it["mult"] <= 2 for it in items) else "mehrfache Lösung")
    if res["method"] == "numeric" and n:
        notes.append("numerisch bestimmt")
    if res["status"] == "identity":
        result, rtex = {"type": "text", "text": "jede Zahl ist Lösung"}, r"\mbox{jede Zahl ist L\"osung}"
    elif not n:
        result, rtex = {"type": "text", "text": "keine Lösung"}, r"\mbox{keine L\"osung}"
        if res.get("complex"):
            cs = "; ".join(E.fmt_complex(complex(z), 6) for z in res["complex"][:6])
            notes = [f"keine reelle Lösung; komplex: {cs} (Einstellung „komplex“)"] + \
                [m for m in notes if "komplexe Lösung" not in m]
    else:
        conv_vals = [conv(v) if conv and not isinstance(v, complex) else v for v in vals]
        result = E.describe(conv_vals[0] if n == 1 else np.array(conv_vals), digits)
        rtex = r",\quad ".join(it["tex"] for it in items)
    out.update(kind="solve", name=x, status=res["status"], method=res["method"], solutions=items, sets=sets,
               picked=picked, result=result, result_tex=rtex, notes=notes,
               store=(E.to_json(vals[0]) if n == 1 else E.to_json(np.array(vals))) if n else None)
    if show:
        out["unit"] = show
    return out


def _lin_text(const, terms, tex):
    """const + Σ Faktor·Name als Text bzw. TeX (Brüche exakt)."""
    def num(v):
        if isinstance(v, Fraction):
            return _fr_tex(v) if tex else _fr_text(v)
        return E.fmt_num(float(v), 8).replace("-", "−") if not tex else R.num_tex(float(v), "de", 8)
    parts = []
    if const != 0 or not terms:
        parts.append(num(const))
    for name, k in terms.items():
        neg = k < 0
        a = abs(k)
        coef = "" if a == 1 else num(a) + (r"\cdot " if tex else "·")
        sym = R.sym_tex(name) if tex else name
        if parts:
            parts.append(("-" if tex else "−") if neg else "+")
            parts.append(coef + sym)
        else:
            parts.append(("-" if tex else "−") * neg + coef + sym)
    return " ".join(parts)


def solve_system_line(pairs, ctx, req, lang, out):
    """S-02: Gleichungssystem (Gleichungen mit ; getrennt)."""
    digits = int(req.get("digits", 10))
    res = SV.solve_system(pairs, ctx)
    unk, dims = res["unknowns"], res["dims"]
    rend = [(_input_render(a, lang), _input_render(b, lang)) for a, b in pairs]
    out["html"] = ";&nbsp; ".join(f"{hl} = {hr}" for (tl, hl), (tr_, hr) in rend)
    out["tex"] = r"\left\{\begin{array}{l}" + r" \\ ".join(f"{tl} = {tr_}" for (tl, hl), (tr_, hr) in rend) + \
        r"\end{array}\right."
    units = {u: (U.dims_text(dims[u]) if dims.get(u) is not None and not U.deq(dims[u], U.D0) else "") for u in unk}
    notes = list(res.get("notes") or [])
    groups, items = [], []
    st = res["status"]
    if st in ("unique", "ok") and res["solutions"]:
        for k, (sol, ex) in enumerate(zip(res["solutions"], res.get("exact") or [[None] * len(unk)] * len(res["solutions"])), 1):
            g = []
            for u, v, fr in zip(unk, sol, ex):
                exs = _fr_text(fr) if isinstance(fr, Fraction) and fr.denominator != 1 else None
                ext = _fr_tex(fr) if exs else None
                num = R.num_tex(v, lang, 8) + (r"\," + R.unit_tex(unit_plain(units[u])) if units[u] else "")
                g.append({"name": u, "text": E.describe(v, digits)["text"], "value": E._jnum(v), "exact": exs,
                          "unit": units[u], "tex": f"{R.sym_tex(u)} = " + (f"{ext} \\approx {num}" if ext else num)})
            items.append({"k": k, "vals": g})
            groups.append(sol)
        if len(groups) == 1:
            rtex = r",\quad ".join(v["tex"] for v in items[0]["vals"])
        else:
            rtex = r"\quad ".join(r"(%d)\ " % it["k"] + r",\ ".join(v["tex"] for v in it["vals"]) for it in items)
        result = E.describe(np.array(groups[0]) if len(groups) == 1 else np.array(groups), digits)
        store = E.to_json(np.array(groups[0])) if len(groups) == 1 else E.to_json(np.array(groups))
    elif st == "infinite":
        free = res["free"]
        lines_t, lines_x = [], []
        for u, (c, terms) in res["param"].items():
            lines_t.append(f"{u} = {_lin_text(c, terms, False)}")
            lines_x.append(f"{R.sym_tex(u)} = {_lin_text(c, terms, True)}")
        lines_t.append(", ".join(free) + (" frei" if len(free) > 1 else " frei wählbar"))
        lines_x.append(r",\ ".join(R.sym_tex(f) for f in free) + r"\ \mbox{frei}")
        result = {"type": "text", "text": "unendlich viele Lösungen: " + "; ".join(lines_t)}
        rtex, store = r",\quad ".join(lines_x), None
        notes.append(f"Rang {res['rank']} bei {len(unk)} Unbekannten")
    else:
        result, rtex, store = {"type": "text", "text": "keine Lösung"}, r"\mbox{keine L\"osung}", None
        if res.get("lsq"):
            ls = ", ".join(f"{u} = {E.fmt_num(v, 6)}" for u, v in zip(unk, res["lsq"]))
            notes.append(f"widersprüchlich (Rang {res.get('rank')}); Ausgleichslösung (kleinste Quadrate): {ls}")
        used = [n.id for a, b in pairs for side in (a, b) for n in ast.walk(side)
                if isinstance(n, ast.Name) and n.id in ctx.names and n.id != "ans"]
        if used:
            notes.append(f"{used[0]} hat schon einen Wert und zählt nicht als Unbekannte")
    sets, picked = _sets_for(groups, unk, dims, req.get("pick")) if groups else ([], None)
    out.update(kind="system", unknowns=unk, status=st, solutions=items, sets=sets, picked=picked, result=result,
               result_tex=rtex, notes=notes, store=store,
               system={k: res.get(k) for k in ("type", "A", "b", "rref", "rank", "free") if res.get(k) is not None})
    return out


def _has_dims(node, ctx) -> bool:
    """Kommt eine Grösse mit Einheit vor (Variable mit Einheit, Konstante mit Einheit, Chemiefunktion mit Einheit)?"""
    pd = getattr(ctx, "pdims", None) or {}
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            if n.id in ctx.dims and not U.deq(ctx.dims[n.id], U.D0) or n.id in pd:
                return True
            if n.id not in ctx.names and n.id in U.CONSTANTS and not U.deq(U.constant_dims(n.id), U.D0):
                return True
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in E.STRFUNCS and n.args \
                and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str) \
                and (E.strfunc_dims(n) is None or not U.deq(E.strfunc_dims(n), U.D0)):
            return True
    return False


def _dims_unit(node, ctx):
    """SI-Einheit des Ergebnisses, wenn Grössen mit Einheit vorkommen; UNKNOWN_UNIT, wenn sie dann nicht bestimmbar
    ist (statt stillschweigend dimensionslos)."""
    if not _has_dims(node, ctx):
        return None
    d = node_dims(node, ctx)
    if d is None:
        return UNKNOWN_UNIT
    if U.deq(d, U.D0):
        return None
    return _si_text(d)


def _si_text(d) -> str:
    """SI-Einheit; gibt es eine Grössenart mit dieser Dimension, deren kohärente Einheit (J/(mol·K) statt
    m²·kg/(s²·K·mol))."""
    t = U.dims_text(d)
    if "·" not in t and "/" not in t:
        return t
    for k in U.kinds_for_dims(d):
        si = k.si.replace("*", "·")
        if "^" not in si and U.compatible(si, t):
            return si
    return t


# ----------------------------------------------------------------------------- Einheiten von Listen (DP-11)
# E.dims_of kennt mean, min, max …; hier dazu die Listenfunktionen, Elemente einer Liste (sigma[2]) und linreg:
# linreg(x, y) = [k, d, R²] mit k in y/x, d in y. Teilausdrücke mit bekannter Einheit werden vorab durch einen
# Platzhalter-Namen ersetzt, damit E.dims_of den Rest wie gewohnt rechnet (2*linreg(eps, sigma)[1] hat Pa).
_SAME = {"std", "sort", "cumsum", "diff", "sum"}
LINREG_PARTS = ("k", "d", "R2")


def _index_of(sl):
    try:
        v = sl.value if isinstance(sl, ast.Constant) else None
        return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and float(v) == int(v) else None
    except (TypeError, ValueError):
        return None


def linreg_dims(dx, dy):
    """[k, d, R²]-Dimensionen von linreg(x, y) aus den Dimensionen von x und y, oder None, wenn eine fehlt."""
    if dx is None or dy is None:
        return None
    return [U.ddiv(dy, dx), dy, U.D0]


class _DimRewrite(ast.NodeTransformer):
    def __init__(self, dims, pdims):
        self.dims, self.pdims, self.n = dims, pdims, 0

    def _syn(self, d, node):
        if d is None:
            return node
        self.n += 1
        name = f"#d{self.n}"                     # kein gültiger Name einer Rechenzeile, also ohne Konflikt
        self.dims[name] = tuple(d)
        return ast.copy_location(ast.Name(id=name, ctx=ast.Load()), node)

    def visit_Subscript(self, node):
        base, idx = node.value, _index_of(node.slice)
        if isinstance(base, ast.Call) and isinstance(base.func, ast.Name) and base.func.id == "linreg" and len(base.args) == 2:
            base.args = [self.visit(a) for a in base.args]
            pd = linreg_dims(E.dims_of(base.args[0], self.dims), E.dims_of(base.args[1], self.dims))
            return self._syn(pd[idx - 1], node) if pd and idx in (1, 2, 3) else node
        self.generic_visit(node)
        if isinstance(node.value, ast.Name):
            nm = node.value.id
            if nm in self.pdims:                     # fit = linreg(…); fit[1]
                ps = self.pdims[nm]
                return self._syn(ps[idx - 1], node) if idx and 1 <= idx <= len(ps) else node
            if nm in self.dims:                      # Element einer Liste behält deren Einheit
                return self._syn(self.dims[nm], node)
        return node

    def visit_Call(self, node):
        self.generic_visit(node)
        if not isinstance(node.func, ast.Name):
            return node
        n, a = node.func.id, node.args
        d = lambda k: E.dims_of(a[k], self.dims)        # noqa: E731
        if n in _SAME and len(a) == 1:
            return self._syn(d(0), node)
        if n == "var" and len(a) == 1:
            return self._syn(U.dpow(d(0), 2) if d(0) is not None else None, node)
        if n in ("len", "size"):
            return self._syn(U.D0, node)
        if n == "trapz" and len(a) in (1, 2):
            dy = d(0)
            dx = d(1) if len(a) == 2 else U.D0
            return self._syn(U.dmul(dy, dx) if dy is not None and dx is not None else None, node)
        if n == "interp" and len(a) == 3:
            return self._syn(d(2), node)
        if n == "dot" and len(a) == 2:
            return self._syn(U.dmul(d(0), d(1)) if d(0) is not None and d(1) is not None else None, node)
        return node


def node_dims(node, ctx):
    """Dimension eines Ausdrucks wie E.dims_of, ergänzt um Listenfunktionen, Listenelemente und linreg (DP-11)."""
    dims = {n: U.D0 for n in ctx.names}          # Zeilenvariablen und Matrizen ohne Einheitenangabe sind Zahlen
    dims.update(ctx.dims)
    tree = _DimRewrite(dims, getattr(ctx, "pdims", None) or {}).visit(copy.deepcopy(node))
    return E.dims_of(tree, dims)


def _add_parts(out, node, ctx, val, lang):
    """linreg(x, y) mit Einheiten: Teile k, d, R² je mit eigener Einheit (eine Liste hat sonst nur eine Einheit)."""
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "linreg" and len(node.args) == 2):
        return
    if not ({n.id for n in ast.walk(node) if isinstance(n, ast.Name)} & set(ctx.dims)):
        return
    pd = linreg_dims(node_dims(node.args[0], ctx), node_dims(node.args[1], ctx))
    if pd is None or all(U.deq(d, U.D0) for d in pd):
        return
    vals = np.real(np.asarray(val, dtype=complex)).ravel().tolist()
    if len(vals) != 3:
        return
    units = [U.dims_text(d) for d in pd]
    out["parts"] = [{"name": n, "unit": u, "value": E._jnum(v), "text": E.fmt_num(v, 6)}
                    for n, u, v in zip(LINREG_PARTS, units, vals)]
    out["pdims"] = [list(d) for d in pd]
    cells = [R.num_tex(v, lang, 6) + (r"\," + R.unit_tex(unit_plain(u)) if u else "") for v, u in zip(vals, units)]
    out["result_tex"] = r"\left(k,\ d,\ R^2\right) = \left(%s\right)" % r";\ ".join(cells)


_SUP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻", "0123456789-")


def unit_plain(u: str) -> str:
    # vor ")" den Exponenten klammern: R.unit_tex nähme sonst die schliessende Klammer mit (kg²/(m²·s⁴))
    return re.sub(r"([⁰¹²³⁴⁵⁶⁷⁸⁹⁻]+)(\)?)", lambda m: ("^(%s)" if m.group(2) else "^%s") % m.group(1).translate(_SUP) + m.group(2),
                  u).replace("·", "*")
