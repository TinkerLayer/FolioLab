"""Werte aus dem Projektindex in eigenen Gleichungen: Einheiten prüfen, statt still falsch zu rechnen.

Eigene Gleichungen rechnen mit Zahlenwerten in den Einheiten der Anzeige. Eine Zeile, die einen übernommenen Indexwert
verwendet (direkt oder über eine frühere Gleichung), wird abgelehnt, wenn sie
  * ihn mit einer Grösse derselben Dimension in anderer Einheit mischt (GPa neben MPa), oder
  * Grössen verschiedener Dimension addiert oder vergleicht (MPa + mm²), oder
  * den Namen des Indexwerts benutzt, der hier etwas anderes bedeutet (Messwert, Konstante).
``convert(x, "GPa", "MPa")`` ist die ausdrückliche Umrechnung und zählt als Grösse in der Zieleinheit.
Gleichungen ohne Indexwert bleiben unberührt. Gleiche Datei in Zugversuch, FTIR, TGA und Mikroskopie.
"""
from __future__ import annotations

import ast
import copy

MARK = "Projektindex "                                 # Anfang von ``from`` eines übernommenen Indexwerts


class _Convert(ast.NodeTransformer):
    """Ersetzt convert(x, "von", "nach") durch einen Namen mit der Einheit „nach“."""

    def __init__(self, units):
        self.U, self.info = units, {}

    def visit_Call(self, n):
        if isinstance(n.func, ast.Name) and n.func.id == "convert" and len(n.args) == 3 \
                and isinstance(n.args[2], ast.Constant) and isinstance(n.args[2].value, str):
            name, to = f"_cv{len(self.info)}", n.args[2].value
            try:
                self.info[name] = (to, *self.U.parse_unit(to))
            except self.U.UnitError:
                self.info[name] = None
            return ast.Name(id=name, ctx=ast.Load())
        return self.generic_visit(n)


def is_taken(v) -> bool:
    return isinstance(v, dict) and bool(v.get("ext")) and str(v.get("from") or "").startswith(MARK)


def guard(rows: list, variables: dict, functions=(), lang: str = "de") -> list:
    """Zeilen mit unpassenden Einheiten bekommen ``error`` statt eines Werts (auch alle, die auf ihnen aufbauen)."""
    taken = {k for k, v in (variables or {}).items() if is_taken(v)}
    if not taken or not rows:
        return rows
    from labcalc import expr as E
    from labcalc import units as U
    de = lang != "en"

    def unit_info(unit):
        try:
            return (unit or "", *U.parse_unit(unit or ""))
        except U.UnitError:
            return None

    info = {k: unit_info(v.get("unit") if isinstance(v, dict) else "") for k, v in variables.items()}
    callables = E.Ctx().callables() | frozenset(functions or ())
    tainted, refused = set(taken), set()
    renamed = {variables[k]["key"]: k for k in taken if variables[k].get("key") and variables[k]["key"] != k}

    def refuse(r, msg):
        r.update(value=None, text="", tex_value="", error=msg)
        r.pop("unc", None)
        r.pop("text_pm", None)
        refused.add(r["sym"])

    for r in rows:
        sym = r.get("sym")
        if r.get("error") or r.get("value") is None:
            refused.add(sym)
            continue
        try:
            node = E.parse(r["expr"], callables)
        except (E.CalcError, SyntaxError, ValueError):
            continue
        before = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
        clash = sorted(before & set(renamed))
        if clash:                                       # der Name meint hier etwas anderes als den Indexwert
            k = clash[0]
            refuse(r, f"„{k}“ ist hier schon vergeben (Messwert oder reservierter Name); der Indexwert heisst {renamed[k]}" if de
                   else f"“{k}” is already taken here (measured value or reserved name); the index value is called {renamed[k]}")
            continue
        bad = sorted(before & refused)
        if bad:
            refuse(r, f"Baut auf {bad[0]} auf, das abgelehnt wurde" if de else f"Depends on {bad[0]}, which was refused")
            continue
        if before & tainted:
            tainted.add(sym)
            conv = _Convert(U)
            tree = conv.visit(copy.deepcopy(node))
            names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
            known = {**info, **conv.info}
            msg = _mixed(names & taken, names, known, U, de)
            if msg is None:
                dims = {k: (known[k][2] if known.get(k) else None) for k in names if k in known or k not in U.CONSTANTS}
                try:
                    E.dims_of(tree, dims, strict=True)
                except E.DimError as e:
                    msg = (f"Einheiten passen nicht zusammen: {e}" if de else f"Units do not fit together: {e}")
            if msg:
                refuse(r, msg)
                continue
        if r.get("unit"):
            info[sym] = unit_info(r["unit"])
    return rows


def _mixed(mine, names, known, U, de):
    for t in sorted(mine):
        a = known.get(t)
        if not a or U.deq(a[2], U.D0):
            continue
        for o in sorted(names - {t}):
            b = known.get(o)
            if b and U.deq(a[2], b[2]) and (a[1] != b[1] or a[3] != b[3]):
                c = f'convert({t}, "{a[0]}", "{b[0]}")'
                return (f"{t} steht in {a[0]}, {o} in {b[0]}: Gleichungen rechnen mit Zahlenwerten. Umrechnen mit {c}" if de
                        else f"{t} is in {a[0]}, {o} in {b[0]}: equations use plain numbers. Convert with {c}")
    return None
