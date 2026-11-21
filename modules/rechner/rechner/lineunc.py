"""Messunsicherheit in Rechenzeilen.

Eingaben
    ``x = 5,0 ± 0,1 mm``        Standardunsicherheit u (in der Einheit der Zeile)
    ``x = 5,0 ± 0,2 (k=2) mm``  erweiterte Unsicherheit U mit Erweiterungsfaktor k
    ``x = 5,0 ± 0,1 rect mm``   Grenzen ±a, Rechteck- (``rect``) oder Dreieckverteilung (``tri``)
    ±-Knopf einer Wertzeile     weitere Beiträge (Messmittel, Wiederholmessung …) in ``item["unc"] = {"parts": [...]}``
    Variablen mit ``u`` (Standardunsicherheit in ihrer Einheit) oder ``unc = {"parts": [...]}``
    weitergegebene Zeilenvariablen anderer Blätter mit ``u`` (SI)

Jede Zeile, deren Ergebnis von unsicheren Eingaben abhängt, bekommt ``unc`` (Ergebnis von
``labcalc.uncertainty.evaluate`` nach dem Verfahren des Blatts, ``env["unc"] = {method, p, k, corr}``). Das Modell
rechnet die ganze Abhängigkeitskette der Zeile in SI neu (wie ``labcalc.formulas._propagate``), damit eine Eingabe,
die über mehrere Zeilen in ein Ergebnis eingeht, richtig (korreliert) zählt. Formelkarten und abgeleitete Werte
gehen als exakte Werte ein (Hinweis an der Zeile).
"""
from __future__ import annotations

import copy
import math
import re

import numpy as np
from labcalc import uncertainty as UN

from . import expr as E
from . import plots as P
from . import render as R
from . import units as U

NUM = r"[-+−]?(?:\d+(?:[.,]\d*)?|[.,]\d+)(?:[eE][-+−]?\d+)?"
_PM = re.compile(rf"^\s*([^\W\d]\w*)\s*=\s*({NUM})\s*(?:±|\+/-)\s*({NUM})\s*(.*?)\s*$")
_K = re.compile(rf"\(\s*k\s*=\s*({NUM})\s*\)|(?<![\w])k\s*=\s*({NUM})", re.I)
_DIST = re.compile(r"(?<![\w°])(rect|rechteck|tri|dreieck)(?!\w)", re.I)
VALUE_LINE = re.compile(rf"^(\s*[^\W\d]\w*\s*=\s*)({NUM})(\s*)$")
SUPPORTED = ("assign", "expr")
METHODS = UN.METHODS + ("off",)

TX = {"de": {"pm_kd": "entweder (k = …) oder rect/tri angeben", "unit": "Einheit „{u}“ unbekannt",
             "cards": "Ergebnisse von Formelkarten und abgeleitete Werte gehen ohne Unsicherheit ein",
             "from": "von Blatt {b}", "u": "Standardunsicherheit", "var": "Variable"},
      "en": {"pm_kd": "give either (k = …) or rect/tri", "unit": "unknown unit “{u}”",
             "cards": "results of formula cards and derived values enter without uncertainty",
             "from": "from sheet {b}", "u": "standard uncertainty", "var": "variable"}}


def _f(s: str) -> float:
    return float(str(s).replace(",", ".").replace("−", "-"))


def _loc(s: str, lang: str) -> str:
    return s.replace(".", ",") if lang == "de" else s


def parse_pm(src: str, lang: str = "de") -> dict | None:
    """``x = 5,0 ± 0,1 mm`` -> {name, value, amount, unit, part, k, dist, …}; None, wenn die Zeile kein ± trägt.

    Der Beitrag (``part``) hat die Form von ``labcalc.uncertainty``: ``u`` (ohne Zusatz), ``U`` mit k, ``limits``
    mit Rechteck- oder Dreieckverteilung. Eine unbekannte Einheit gibt ``E.CalcError``."""
    m = _PM.match(str(src or ""))
    if not m:
        return None
    name, val, amt, tail = m.groups()
    T = TX.get(lang, TX["de"])
    k = dist = None
    mk = _K.search(tail)
    if mk:
        k = abs(_f(mk.group(1) or mk.group(2)))
        tail = tail[:mk.start()] + tail[mk.end():]
    md = _DIST.search(tail)
    if md:
        dist = "rect" if md.group(1).lower() in ("rect", "rechteck") else "tri"
        tail = tail[:md.start()] + tail[md.end():]
    if k and dist:
        raise E.CalcError(T["pm_kd"])
    unit = tail.strip().strip("[]").strip()
    try:
        U.parse_unit(U.split_delta(unit)[0])
    except U.UnitError:
        raise E.CalcError(T["unit"].format(u=unit)) from None
    amount = abs(_f(amt))
    if k:
        part = {"kind": "U", "U": amount, "k": k}
    elif dist:
        part = {"kind": "limits", "a": amount, "dist": dist}
    else:
        part = {"kind": "u", "u": amount}
    return {"name": E.norm_name(name), "raw_name": name, "value": _f(val), "amount": amount, "unit": unit, "k": k,
            "dist": dist, "part": part, "value_text": val.replace("−", "-"), "amount_text": amt.replace("−", "-")}


def affine(unit: str) -> tuple[float, float]:
    """SI = a + b·x für einen Wert x in ``unit`` (°C mit Nullpunkt, Δ°C ohne)."""
    target, delta = U.split_delta(unit or "")
    a = float(U.to_si(0.0, target, diff=delta))
    return a, float(U.to_si(1.0, target, diff=delta)) - a


def pm_line(pm: dict, lang: str) -> dict:
    """Darstellung einer ±-Zeile (HTML, LaTeX) und die Einheit in SI für die folgenden Zeilen."""
    target, delta = U.split_delta(pm["unit"])
    dims = U.parse_unit(target)[1] if target else U.D0
    opt_h = opt_t = ""
    if pm["k"]:
        kt = _loc(f"{pm['k']:g}", lang)
        opt_h, opt_t = f" <span class=\"small\">(k = {kt})</span>", r"\ (k = %s)" % kt.replace(",", "{,}")
    elif pm["dist"]:
        word = {"rect": ("Rechteck", "rectangular"), "tri": ("Dreieck", "triangular")}[pm["dist"]][0 if lang == "de" else 1]
        opt_h, opt_t = f" <span class=\"small\">({word})</span>", r"\ (\mbox{%s})" % word
    v_t, a_t = (_loc(x.replace(",", "."), lang) for x in (pm["value_text"], pm["amount_text"]))
    uh = f" {R.unit_html(pm['unit'])}" if pm["unit"] else ""
    ut = R.unit_tex(target) if target else ""
    if ut and delta:
        ut = r"\Delta " + ut
    tex_pm = f"{v_t} \\pm {a_t}".replace(",", "{,}")
    return {"html": f"{R.sym_html(pm['name'])} = {v_t} ± {a_t}{uh}{opt_h}",
            "tex": f"{R.sym_tex(pm['name'])} = " + (f"({tex_pm})\\,{ut}" if ut else tex_pm) + opt_t,
            "dims": None if U.deq(dims, U.D0) else list(dims), "unit": U.dims_text(dims) if not U.deq(dims, U.D0) else None,
            "tdiff": bool(delta)}


def is_value_line(p: dict | None, r: dict) -> bool:
    """Zeile, die einen Wert festlegt (keine Namen rechts), z. B. ``x = 5.0`` oder ``x = 5,0 ± 0,1 mm``."""
    if not p or r.get("kind") != "assign" or r.get("error"):
        return False
    v = (r.get("result") or {}).get("value")
    return (p.get("kind") in ("pm", "qty") or (p.get("kind") is None and not (p.get("uses") or set()))) \
        and _scalar(v) is not None


def _scalar(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v) if math.isfinite(v) else None


def _fmt_u(u: float, unit: str, lang: str) -> str:
    s = f"{u:.2g}"
    if "e" in s:
        m, e = s.split("e")
        s = f"{m}·10^{int(e)}"
    return f"u = {_loc(s, lang)}" + (f" {unit}" if unit else "")


# ----------------------------------------------------------------------------- Eingaben eines Blatts
def collect_inputs(req, env, sh, q, calc, preps, lines, base_vars, imports, lang, errors=None):
    """Unsichere Eingaben eines Blatts: Wertzeilen mit ± oder ±-Knopf, Variablen mit u, weitergegebene Zeilen mit u.

    Rückgabe: Liste {key, spec (für make_input, in der Einheit der Eingabe), a, b (SI = a + b·x), names, line (Index)
    oder None}. Fehler einer Eingabe stehen an ihrer Zeile (``unc_error``)."""
    T = TX.get(lang, TX["de"])
    out, keys = [], set()

    def key_for(name):
        k, i = name, 2
        while k in keys:
            k, i = f"{name}_{i}", i + 1
        keys.add(k)
        return k

    # 1. Wertzeilen
    for i, it in enumerate(calc):
        p = preps[i]
        r = lines.get(str(it.get("id"))) or {}
        if not is_value_line(p, r):
            continue
        extra = [x for x in ((it.get("unc") or {}).get("parts") or []) if isinstance(x, dict)][:20] \
            if isinstance(it.get("unc"), dict) else []
        if p.get("kind") == "pm":
            pm = p["pm"]
            parts, value, unit = [pm["part"]] + extra, pm["value"], pm["unit"]
        elif p.get("kind") == "qty":                       # m = 2 kg mit ±-Knopf: Beiträge in der Einheit der Zeile
            if not extra:
                continue
            parts, value, unit = extra, p["qty"]["value"], p["qty"]["unit"]
        elif extra:
            parts, value, unit = extra, float(r["result"]["value"]), ""
        else:
            continue
        name = r.get("name") or p.get("name")
        spec = {"name": key_for(name), "value": value, "unit": unit, "label": str(it.get("src") or name)[:120],
                "parts": parts}
        if isinstance(it.get("unc"), dict) and it["unc"].get("note"):
            spec["note"] = str(it["unc"]["note"])[:300]
        try:
            inp = UN.make_input(spec, lang)
        except UN.UncError as e:
            r["unc_error"] = str(e)
            continue
        a, b = affine(unit)
        r["unc_in"] = {"u": inp["u"], "u_si": abs(inp["u"] * b), "unit": unit, "dof": UN._jsonable(inp["dof"]),
                       "type": inp["type"], "text": _fmt_u(inp["u"], unit, lang),
                       "parts": [{"label": x["label"], "u": x["u"], "dist": x["dist"]} for x in inp["parts"]]}
        out.append({"key": spec["name"], "spec": inp, "a": a, "b": b, "names": [name], "line": i})

    # 2. Variablen des Blatts mit Unsicherheit (± in der Variablenleiste, übernommene Werte mit u)
    by_id = {str(v.get("id")): v for v in req.get("values") or [] if isinstance(v, dict)}
    from . import solver as S
    for vid, kn in sh.user_by_id.items():
        v = by_id.get(vid) or {}
        parts = (v.get("unc") or {}).get("parts") if isinstance(v.get("unc"), dict) else None
        if not parts:
            try:
                u = float(str(v.get("u")).replace(",", "."))
            except (TypeError, ValueError):
                u = 0.0
            if not (u > 0 and math.isfinite(u)):
                continue
            parts = [{"kind": "u", "u": u}]
        names = [n for n in dict.fromkeys([kn.name, kn.sym]) if n not in (base_vars or {})]
        if not names:
            continue
        try:
            k = U.ensure_kind(kn.kind)
            a = float(S.to_si(0.0, kn.unit, k))
            b = float(S.to_si(1.0, kn.unit, k)) - a
        except (U.UnitError, E.CalcError, ValueError, TypeError):
            continue
        if not b:
            continue
        spec = {"name": key_for(kn.name), "value": (kn.si - a) / b, "unit": kn.unit,
                "label": f"{T['var']} {v.get('sym') or kn.name}", "parts": list(parts)[:20]}
        try:
            inp = UN.make_input(spec, lang)
        except UN.UncError as e:
            if errors is not None:
                errors[vid] = str(e)
            continue
        out.append({"key": spec["name"], "spec": inp, "a": a, "b": b, "names": names, "line": None, "var": vid})

    # 3. Zeilenvariablen anderer Blätter mit u (SI)
    for name, x in (imports or {}).items():
        try:
            u = float(x.get("u") or 0)
        except (TypeError, ValueError):
            continue
        val = _scalar(x.get("store"))
        if not (u > 0 and math.isfinite(u)) or val is None:
            continue
        spec = {"name": key_for(name), "value": val, "unit": x.get("unit") or "",
                "label": f"{name} ({T['from'].format(b=x.get('env_name') or x.get('env') or '?')})",
                "parts": [{"kind": "u", "u": u}]}
        try:
            out.append({"key": spec["name"], "spec": UN.make_input(spec, lang), "a": 0.0, "b": 1.0, "names": [name],
                        "line": None, "import": True})
        except UN.UncError:
            continue
    return out


# ----------------------------------------------------------------------------- Fortpflanzung
def _closure(j: int, deps: list) -> set:
    seen, todo = {j}, [j]
    while todo:
        for d in deps[todo.pop()]:
            if d not in seen:
                seen.add(d)
                todo.append(d)
    return seen


def _body(src: str):
    st = E.split_statement(src)
    if st[0] == "assign":
        return st[2], E.norm_name(st[1]), None
    if st[0] == "convert":
        return st[1], None, st[2]
    if st[0] in ("func", "equation", "system"):
        return None, None, None
    return st[1], None, None


def propagate(req, env, sh, q, calc, preps, order, deps, lines, base_vars, funcs, imports, lang):
    """Unsicherheit für jede Zeile, die von unsicheren Eingaben abhängt (``unc``, ``unc_error``, ``unc_notes``).

    Rückgabe: Übersicht {inputs: [{key, label, unit, u}], method, n} oder None ohne unsichere Eingaben."""
    opts = env.get("unc") if isinstance(env.get("unc"), dict) else {}
    method = opts.get("method") if opts.get("method") in METHODS else "gum"
    if req.get("unc_lang") in ("de", "en"):                   # Sprache der Seite (die Rechnung selbst bleibt deutsch)
        lang = req["unc_lang"]
    errors: dict = {}
    inputs = collect_inputs(req, env, sh, q, calc, preps, lines, base_vars, imports, lang, errors)
    if not inputs:
        return {"var_errors": errors} if errors else None
    T = TX.get(lang, TX["de"])
    summary = {"inputs": [{"key": x["key"], "label": x["spec"]["label"], "unit": x["spec"]["unit"], "u": x["spec"]["u"],
                           **({"line": str(calc[x["line"]].get("id"))} if x["line"] is not None else {}),
                           **({"var": x["var"]} if x.get("var") else {})} for x in inputs],
               "method": method, "n": 0, **({"var_errors": errors} if errors else {})}
    if method == "off":
        return summary
    ctx = P.make_ctx({"quantities": q, "vars": base_vars, "funcs": funcs, "angle": req.get("angle", "rad"),
                      "complex": req.get("complex")})
    callables = ctx.callables()
    def_at: dict = {}
    for i, p in enumerate(preps):
        for d in (p or {}).get("defs") or ():
            def_at.setdefault(d, []).append(i)
    line_in = {x["line"]: x for x in inputs if x["line"] is not None}
    base_in = {n: x for x in inputs if x["line"] is None for n in x["names"]}
    card_names = ({kn.sym for kn in sh.card_known.values()} | {kn.sym for kn in sh.derived.values()}) - \
        {n for kn in sh.user.values() for n in (kn.sym, kn.name)}
    rank = {i: k for k, i in enumerate(order)}
    want = (req.get("unc_compare") or {}) if str((req.get("unc_compare") or {}).get("env")) == str(env.get("id")) else {}
    nodes: dict = {}

    def step_of(i):
        if i in nodes:
            return nodes[i]
        r = lines.get(str(calc[i].get("id"))) or {}
        st = None
        if i in line_in:
            st = {"input": line_in[i]}
        elif r.get("kind") == "func":
            st = {"skip": True}
        elif preps[i] and preps[i].get("kind") == "qty" and _scalar((r.get("result") or {}).get("value")) is not None:
            st = {"node": E.parse(repr(float(r["result"]["value"]))), "name": preps[i]["name"]}   # fester Wert in SI
        elif r.get("kind") in SUPPORTED and _scalar((r.get("result") or {}).get("value")) is not None and preps[i] \
                and preps[i].get("kind") is None:
            try:
                body, name, conv = _body(preps[i]["src"])
                if body is not None:
                    node = E.parse(body, callables)
                    st = {"node": node, "name": name}
                    if conv:                                  # -> Einheit: wert = (SI − Nullpunkt)/Faktor
                        tgt, delta = U.split_delta(conv)
                        diff = delta or str(r.get("unit") or "").startswith("Δ")
                        off = float(U.from_si(0.0, tgt, diff))
                        st["conv"] = (float(U.from_si(1.0, tgt, diff)) - off, off)
            except (E.CalcError, U.UnitError, SyntaxError, ValueError, TypeError):
                st = None
        nodes[i] = st
        return st

    for j in order:
        it = calc[j]
        r = lines.get(str(it.get("id"))) or {}
        if j in line_in or r.get("kind") not in SUPPORTED or r.get("error") or not preps[j]:
            continue
        if _scalar((r.get("result") or {}).get("value")) is None:
            continue
        chain = sorted(_closure(j, deps), key=lambda i: rank.get(i, i))
        steps = [step_of(i) for i in chain]
        used_base = {u for i in chain for u in ((preps[i] or {}).get("uses") or ()) if not any(d != i for d in def_at.get(u, []))}
        ids = {id(base_in[u]) for u in used_base if u in base_in}
        var_ins = [x for x in inputs if id(x) in ids]
        line_ins = [line_in[i] for i in chain if i in line_in]
        ins = line_ins + var_ins
        if not ins:
            continue
        if any(s is None for s in steps):
            continue
        notes = [T["cards"]] if used_base & card_names else []

        def run(vals, steps=steps, var_ins=var_ins):
            loc = {}
            for x in var_ins:
                v = x["a"] + x["b"] * vals[x["key"]]
                for n in x["names"]:
                    loc[n] = v
            y = None
            for st in steps:
                if st.get("skip"):
                    continue
                if "input" in st:
                    x = st["input"]
                    y = x["a"] + x["b"] * vals[x["key"]]
                    loc[x["names"][0]] = y
                else:
                    c = copy.copy(ctx)
                    c.names = {**ctx.names, **loc}
                    y = E.evaluate(st["node"], c)
                    if st.get("conv"):
                        y = np.asarray(y) * st["conv"][0] + st["conv"][1]
                    if st.get("name"):
                        loc[st["name"]] = y
                loc["ans"] = y
            return y

        def model(vals, run=run):
            n = max([np.size(v) for v in vals.values()] + [1])
            y = run(vals)
            if n > 1:                                         # vektorisiert: Form und zwei Stichproben prüfen
                ya = np.asarray(y, dtype=float)
                if ya.shape != (n,):
                    raise ValueError("Modell nicht elementweise")
                for i in (0, n - 1):
                    yi = float(np.real(run({k: (v[i] if np.ndim(v) else v) for k, v in vals.items()})))
                    if not (np.isclose(yi, ya[i], rtol=1e-9, atol=1e-300) or (math.isnan(yi) and math.isnan(ya[i]))):
                        raise ValueError("Modell nicht elementweise")
                return ya
            return y

        unit = r.get("unit") if r.get("unit") not in (None, "?") else ""
        kw = dict(corr=opts.get("corr") or None, p=opts.get("p") or UN.P_DEFAULT, k=opts.get("k") or None, lang=lang,
                  unit=unit, label=str(it.get("src") or r.get("name") or "")[:120],
                  name=r.get("name") or f"l{j + 1}")
        specs = [x["spec"] for x in ins]
        try:
            res = UN.evaluate(model, specs, method, **kw)
        except (UN.UncError, E.CalcError, U.UnitError, ValueError, TypeError, ZeroDivisionError, OverflowError) as e:
            r["unc_error"] = str(e)
            continue
        r["unc"] = res
        r["text_pm"] = res.get("text")
        if notes:
            r["unc_notes"] = notes
        summary["n"] += 1
        if want and str(want.get("line")) == str(it.get("id")):
            r["unc_compare"] = UN.compare(model, specs, **kw)
    return summary


def std_u(r: dict) -> float | None:
    """Standardunsicherheit einer Zeile in SI (für Weitergabe und Wertekatalog)."""
    if isinstance(r.get("unc"), dict) and isinstance(r["unc"].get("u"), (int, float)) and not r.get("kind") == "expr":
        return float(r["unc"]["u"])
    if isinstance(r.get("unc_in"), dict):
        return float(r["unc_in"]["u_si"])
    return None
