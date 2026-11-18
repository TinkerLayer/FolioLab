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


def evaluate(defs, variables: dict, functions: dict | None = None, lang: str = "de") -> list[dict]:
    """Gleichungen der Reihe nach auswerten.

    variables: Name -> Zahl oder {"value", "unit", "label"}; functions: Name -> Python-Funktion (Zahlen rein, Zahl raus).
    Ergebnis je Gleichung: sym, label, expr, unit, digits, source, value (float|None), text, error, tex (Gleichung),
    tex_value (eingesetztes Ergebnis), html.
    """
    names = {}
    for k, v in (variables or {}).items():
        val = v.get("value") if isinstance(v, dict) else v
        if val is None:
            continue
        try:
            names[k] = float(val)
        except (TypeError, ValueError):
            continue
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
            except (E.CalcError, U.UnitError, ValueError, TypeError, ZeroDivisionError, OverflowError,
                    np.linalg.LinAlgError) as e:
                err = str(e)
        row["error"] = err
        out.append(row)
    return out


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
        taken.add(name)
    return variables


def variables_doc(variables: dict) -> list[dict]:
    """Variablenliste für die Oberfläche: Name, Wert, Einheit, Bezeichnung."""
    out = []
    for k, v in (variables or {}).items():
        if isinstance(v, dict):
            out.append({"name": k, "value": v.get("value"), "unit": v.get("unit", ""), "label": v.get("label", "")})
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
        vals.append((key, tex_escape(label), latex, r["text"] + (" " + r["unit"] if r["unit"] else "")))
        ck = []
        if r.get("source"):
            ck = [C.to_bib(b, C.key_for(cite_prefix, r["source"], r["sym"]), r["source"])]
            cites += ck
        rows.append([f"${R.sym_tex(r['sym'])}$" + (" " + tex_escape(r["label"]) if r.get("label") else ""),
                     f"${r['tex']}$" + (cite(ck) if ck else ""), f"${latex}$"])
        maths.append(r"\[ " + r["tex"] + " = " + latex + r" \]" + (cite(ck, sep=" ") if ck else ""))
    b.add_values(vals)
    b.add_table(f"{prefix}gleichungen", booktabs(L["h"], rows, escape_header=True), caption=L["tab"] + ".")
    text = L["intro"] + ":\n" + "\n".join(maths) + "\n"
    return {"values": [v[0] for v in vals], "cites": cites, "latex": text}


def _key(sym: str) -> str:
    return re.sub(r"[^A-Za-z0-9-]", "-", sym).strip("-") or "x"
