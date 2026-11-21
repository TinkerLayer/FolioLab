"""Eigene Gleichungen eines Moduls: ``Name = Ausdruck`` über die Ergebnisse einer Messung.

Ein Modul stellt Variablen bereit (Name -> Wert, Einheit, Bezeichnung) und optional Funktionen (z. B. FTIR ``A(1715)``).
Die Nutzerin legt Gleichungen an: ``{"sym": "CI", "label": "Carbonylindex", "expr": "area(1650,1850)/area(1420,1500)",
"unit": "", "digits": 3, "source": {...}}``. Spätere Gleichungen dürfen frühere verwenden. Ausgewertet wird mit
``labcalc.expr`` (eingeschränkter AST, kein ``eval``); Fehler bleiben bei der jeweiligen Zeile.

Für den Bericht: ``to_report`` schreibt Werte (``\\labval{slug}{eq-<sym>}``), eine Tabelle und die Gleichungen als
abgesetzte Formeln; eine Gleichung mit Quelle wird zitiert (``labcite``).
"""
from __future__ import annotations

import keyword
import math
import re

import numpy as np

from . import expr as E
from . import render as R
from . import units as U

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,23}$")
MAX_DEFS = 60


class FormulaError(ValueError):
    pass


def clean_defs(defs) -> list[dict]:
    """Gleichungsliste prüfen und vereinheitlichen (für Speichern und Bericht)."""
    out, seen = [], set()
    for d in list(defs or [])[:MAX_DEFS]:
        if not isinstance(d, dict):
            continue
        sym = str(d.get("sym") or "").strip()
        ex = str(d.get("expr") or "").strip()
        if not sym and not ex:
            continue
        row = {"sym": sym, "label": str(d.get("label") or "").strip()[:120], "expr": ex[:400],
               "unit": str(d.get("unit") or "").strip()[:30], "digits": _digits(d.get("digits")),
               "source": d.get("source") if isinstance(d.get("source"), dict) else None}
        if d.get("id"):
            row["id"] = str(d["id"])[:40]
        out.append(row)
        seen.add(sym)
    return out


def _digits(v):
    try:
        return max(1, min(10, int(v)))
    except (TypeError, ValueError):
        return 4


def check_name(sym: str, reserved=()) -> str | None:
    """Fehlermeldung für einen unzulässigen Namen, sonst None."""
    if not NAME_RE.match(sym or ""):
        return "Name: Buchstabe am Anfang, dann Buchstaben, Ziffern oder _ (höchstens 24 Zeichen)"
    if keyword.iskeyword(sym) or sym in E.BUILTINS or sym in E.SPECIAL:
        return f"„{sym}“ ist ein reservierter Name"
    if sym in U.CONSTANTS:
        return f"„{sym}“ ist eine Konstante"
    if sym in reserved:
        return f"„{sym}“ ist bereits ein Messwert dieses Moduls"
    return None


def evaluate(defs, variables: dict, functions: dict | None = None, lang: str = "de", unc: dict | None = None) -> list[dict]:
    """Gleichungen der Reihe nach auswerten.

    variables: Name -> Zahl oder {"value", "unit", "label", "u"?, "unc"?}; functions: Name -> Python-Funktion (Zahlen
    rein, Zahl raus). Ergebnis je Gleichung: sym, label, expr, unit, digits, source, value (float|None), text, error,
    tex (Gleichung), tex_value (eingesetztes Ergebnis), html.

    Messunsicherheit: trägt eine verwendete Variable ``u`` (Standardunsicherheit) oder ``unc`` ({"parts": [...]} wie in
    ``labcalc.uncertainty``), bekommt die Zeile ``unc`` (Ergebnis des Verfahrens, Standard GUM) und ``text_pm``.
    ``unc``: {"method": "gum"|"mc"|"gauss"|"worst"|"off", "p", "k", "corr"}. Frühere Gleichungen werden im Modell
    nachgerechnet, damit gemeinsame Eingangsgrössen richtig korreliert bleiben.
    """
    names = {}
    uspec = {}
    for k, v in (variables or {}).items():
        val = v.get("value") if isinstance(v, dict) else v
        if val is None:
            continue
        try:
            names[k] = float(val)
        except (TypeError, ValueError):
            continue
        sp = _unc_spec(k, names[k], v)
        if sp:
            uspec[k] = sp
    umeth = (unc or {}).get("method") or "gum"
    chain = []                                     # (sym, node) der bisher gültigen Gleichungen
    base_names = dict(names)
    funcs = dict(functions or {})
    callables = E.Ctx().callables() | frozenset(funcs)
    reserved = set(variables or {}) | set(funcs)
    out = []
    for d in clean_defs(defs):
        row = {**d, "value": None, "text": "", "error": None, "tex": "", "html": "", "tex_value": ""}
        err = check_name(d["sym"], reserved)
        if err is None and d["sym"] in [r["sym"] for r in out]:
            err = f"„{d['sym']}“ ist doppelt"
        if err is None and not d["expr"]:
            err = "Ausdruck fehlt"
        node = None
        if err is None:
            try:
                node = E.parse(d["expr"], callables)
                row["tex"], row["html"] = R.render(node, lang=lang)
                row["tex"] = R.sym_tex(d["sym"]) + " = " + row["tex"]
            except (E.CalcError, SyntaxError, ValueError) as e:
                err = f"Ausdruck: {e}"
        if err is None:
            try:
                v = E.evaluate(node, E.Ctx(names=names), dict(funcs))
                a = np.asarray(v)
                if a.ndim != 0 or a.dtype.kind not in "fiub":
                    raise E.CalcError("Ergebnis ist keine Zahl")
                f = float(a)
                if not math.isfinite(f):
                    raise E.CalcError("Ergebnis ist nicht endlich (Division durch null?)")
                row["value"] = f
                row["text"] = fmt(f, d["digits"], lang)
                row["tex_value"] = R.num_tex(f, lang, d["digits"]) + (r"\," + R.unit_tex(d["unit"]) if d["unit"] else "")
                names[d["sym"]] = f
                chain.append((d["sym"], node, d["expr"]))
                if uspec and umeth != "off":
                    _propagate(row, chain, base_names, uspec, funcs, umeth, unc or {}, lang)
            except (E.CalcError, U.UnitError, ValueError, TypeError, ZeroDivisionError, OverflowError,
                    np.linalg.LinAlgError) as e:
                err = str(e)
        row["error"] = err
        out.append(row)
    return out


_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _unc_spec(name: str, value: float, v) -> dict | None:
    """Unsicherheitsangabe einer Variablen als Eingangsgrösse für labcalc.uncertainty (oder None)."""
    if not isinstance(v, dict):
        return None
    sp = v.get("unc")
    parts = sp.get("parts") if isinstance(sp, dict) else None
    if not parts:
        try:
            u = float(v.get("u"))
        except (TypeError, ValueError):
            return None
        if not (u > 0 and math.isfinite(u)):
            return None
        parts = [{"kind": "u", "u": u, **({"dof": v["dof"]} if v.get("dof") not in (None, "", "inf") else {})}]
    return {"name": name, "value": value, "unit": str(v.get("unit") or ""), "label": str(v.get("label") or name),
            "parts": parts, "source": v.get("source") if isinstance(v.get("source"), dict) else None}


def _propagate(row, chain, base_names, uspec, funcs, method, opts, lang):
    from . import uncertainty as UN
    # verwendete Eingangsgrössen: Namen im Ausdruck, über frühere Gleichungen aufgelöst
    exprs = {s: ex for s, _n, ex in chain}
    used, todo = set(), [chain[-1][0]]
    while todo:
        s = todo.pop()
        for t in _TOKEN.findall(exprs.get(s, "")):
            if t in exprs and t not in used and t != s:
                todo.append(t)
            used.add(t)
    ins = [uspec[k] for k in uspec if k in used]
    if not ins:
        return
    nodes = list(chain)

    def model(vals):
        loc = {**base_names, **vals}
        y = None
        for sym, node, _ex in nodes:
            y = E.evaluate(node, E.Ctx(names=dict(loc)), dict(funcs))
            loc[sym] = y
        return y
    try:
        r = UN.evaluate(model, ins, method, corr=opts.get("corr"), p=opts.get("p") or UN.P_DEFAULT, k=opts.get("k"),
                        lang=lang, unit=row.get("unit") or "", label=row.get("label") or row["sym"], name=f"eq-{_key(row['sym'])}")
    except (UN.UncError, E.CalcError, U.UnitError, ValueError, TypeError, ZeroDivisionError) as e:
        row["unc_error"] = str(e)
        return
    row["unc"] = r
    row["text_pm"] = r["text"]


def fmt(v: float, digits: int = 4, lang: str = "de") -> str:
    s = f"{v:.{digits}g}"
    if "e" in s:
        m, ex = s.split("e")
        s = f"{m}·10^{int(ex)}"
    return s.replace(".", ",") if lang == "de" else s


def merge_ext(variables: dict, ext, reserved=()) -> dict:
    """Werte anderer Umgebungen (Verbindung in der Übersicht) als zusätzliche Variablen.

    ext: Liste ``{key, value, unit, label, from_name}``. Eigene Messwerte haben Vorrang: ist der Name schon vergeben,
    heisst der übernommene Wert ``<key>_ext`` (``_ext2`` …). Ungültige Namen und Nicht-Zahlen werden übergangen.
    Rückgabe: ``variables`` (ergänzt, mit ``ext: True`` und ``from`` je übernommenem Wert).
    """
    taken = set(variables) | set(reserved)
    for x in list(ext or [])[:200]:
        if not isinstance(x, dict):
            continue
        try:
            val = float(str(x.get("value")).replace(",", "."))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(val):
            continue
        key = str(x.get("key") or "").strip()
        if not NAME_RE.match(key):
            continue
        name, i = key, 1
        while name in taken or keyword.iskeyword(name) or name in E.BUILTINS or name in E.SPECIAL or name in U.CONSTANTS:
            name = (key[:18] + "_ext" + (str(i) if i > 1 else ""))
            i += 1
            if i > 50:
                break
        if name in taken:
            continue
        src = str(x.get("from_name") or "").strip()[:60]
        label = str(x.get("label") or key).strip()[:100]
        variables[name] = {"value": val, "unit": str(x.get("unit") or "")[:30],
                           "label": f"{label} (aus {src})" if src else label, "ext": True, "from": src, "key": key}
        try:                                              # Unsicherheit reist mit (Standardunsicherheit u)
            u = float(str(x.get("u")).replace(",", "."))
            if u > 0 and math.isfinite(u):
                variables[name]["u"] = u
                if isinstance(x.get("unc"), dict):
                    variables[name]["unc_info"] = {k: x["unc"].get(k) for k in ("method", "U", "k", "p", "dof")}
        except (TypeError, ValueError):
            pass
        taken.add(name)
    return variables


def variables_doc(variables: dict) -> list[dict]:
    """Variablenliste für die Oberfläche: Name, Wert, Einheit, Bezeichnung."""
    out = []
    for k, v in (variables or {}).items():
        if isinstance(v, dict):
            out.append({"name": k, "value": v.get("value"), "unit": v.get("unit", ""), "label": v.get("label", ""),
                        **({"u": v["u"]} if v.get("u") is not None else {})})
        else:
            out.append({"name": k, "value": v, "unit": "", "label": ""})
    return out


# ----------------------------------------------------------------------------- Bericht
T = {"de": {"tab": "Eigene Gleichungen", "h": ["Grösse", "Gleichung", "Wert"], "text": "Eigene Gleichungen",
            "intro": "Zusätzlich wurden folgende eigene Gleichungen ausgewertet"},
     "en": {"tab": "Own equations", "h": ["Quantity", "Equation", "Value"], "text": "Own equations",
            "intro": "The following own equations were also evaluated"}}


def to_report(b, results: list[dict], lang: str = "de", prefix: str = "", cite_prefix: str = "eq") -> dict:
    """Werte, Tabelle und Text eines Gleichungssatzes in ein labbundle.Bundle schreiben.

    Gibt {"values": [...keys], "cites": [...keys], "latex": Textblock} zurück; der Textblock wird vom Modul in seinen
    Methodentext übernommen oder als eigener Block abgelegt.
    """
    from labbundle import booktabs, cite, tex_escape

    import labcite as C

    ok = [r for r in results if r.get("value") is not None]
    if not ok:
        return {"values": [], "cites": [], "latex": ""}
    L = T.get(lang, T["de"])
    vals, rows, cites, maths = [], [], [], []
    for r in ok:
        key = f"{prefix}eq-{_key(r['sym'])}"
        label = r.get("label") or r["sym"]
        latex = R.num_tex(r["value"], lang, r["digits"]) + (r"\," + R.unit_tex(r["unit"]) if r["unit"] else "")
        vals.append((key, tex_escape(label), f"${latex}$", r["text"] + (" " + r["unit"] if r["unit"] else "")))  # \labval steht im Text
        ck = []
        if r.get("source"):
            ck = [C.to_bib(b, C.key_for(cite_prefix, r["source"], r["sym"]), r["source"])]
            cites += ck
        if isinstance(r.get("unc"), dict) and r["unc"].get("method") in ("gum", "gauss"):
            from . import uncertainty as UN
            ys, us, _ = UN.round_pm(r["unc"]["value"], r["unc"]["U"])
            loc = (lambda t: t.replace(".", "{,}")) if lang == "de" else (lambda t: t)
            latex = f"({loc(ys)} \\pm {loc(us)})" + (r"\," + R.unit_tex(r["unit"]) if r["unit"] else "")
        rows.append([f"${R.sym_tex(r['sym'])}$" + (" " + tex_escape(r["label"]) if r.get("label") else ""),
                     f"${r['tex']}$" + (cite(ck) if ck else ""), f"${latex}$"])
        maths.append(r"\[ " + r["tex"] + " = " + latex + r" \]" + (cite(ck, sep=" ") if ck else ""))
    b.add_values(vals)
    b.add_table(f"{prefix}gleichungen", booktabs(L["h"], rows, escape_header=True), caption=L["tab"] + ".", steps=[])
    text = L["intro"] + ":\n" + "\n".join(maths) + "\n"
    ur = [dict(r["unc"], name=f"{prefix}eq-{_key(r['sym'])}") for r in ok if isinstance(r.get("unc"), dict)]
    if ur:                                              # Messunsicherheit: Wert ± U, Budget, Methodentext
        from . import uncertainty as UN
        uo = UN.to_report(b, ur, lang)
        cites += uo["cites"]
        text += uo["latex"] + "\n"
        return {"values": [v[0] for v in vals] + uo["values"], "cites": list(dict.fromkeys(cites)), "latex": text,
                "tables": uo["tables"]}
    return {"values": [v[0] for v in vals], "cites": cites, "latex": text}


def _key(sym: str) -> str:
    return re.sub(r"[^A-Za-z0-9-]", "-", sym).strip("-") or "x"
