"""Umgebungen: Kästen mit Formelkarten und Rechenzeilen, je mit eigenen Grössen.

Eine Grösse gilt in allen Umgebungen (``scope: "all"``) oder nur in ausgewählten (``scope: [id, …]``). Jede
Umgebung ist ein eigenes Arbeitsblatt: Grössen nach Geltungsbereich, Ableiten, Formelkarten; danach laufen ihre
Rechenzeilen der Reihe nach, mit allen dort bekannten Werten (Grössen, Kartenergebnisse, abgeleitete Werte) und den
Zuweisungen der Zeilen davor. Der Server bleibt zustandslos.

DP-11: ``req["dsvals"]`` (von ``dsvars.attach`` aufgelöst) bringt Spalten von Datensätzen als Listenvariablen mit
Einheit; sie gelten auf allen Blättern, eine Grösse oder Matrix gleichen Namens geht vor.
"""
from __future__ import annotations

import heapq
import re

import numpy as np

from . import console as CON
from . import lineunc as LU
from . import render as R
from . import expr as E
from . import solver as S
from . import units as U

_NAME = re.compile(r"[^\W\d]\w*")


def _body(src: str) -> str:
    """Rechter Teil einer Zeile (ohne den zugewiesenen Namen bzw. die Zieleinheit), Griechisch als Namen."""
    try:
        st = E.split_statement(src)
    except E.CalcError:
        return src
    return {"assign": lambda: st[2], "func": lambda: st[3], "convert": lambda: st[1], "equation": lambda: src,
            "system": lambda: src}.get(st[0], lambda: st[1])()


# ----------------------------------------------------------------------------- RC-02/RC-03: Zeilen vorbereiten
_CHAIN = re.compile(r"^\s*([^\W\d]\w*)\s*=\s*([^\W\d]\w*)\s*\(([^()=]*)\)\s*=\s*(.+)$")
_RANGE = re.compile(r"^\s*([^\W\d]\w*)\s*=\s*(.+?)\s*\.\.\s*(.+?)(?:\s+(step|schritt|count|anzahl)\s+(.+?))?(\s+(?:slider|schieber))?\s*$",
                    re.I)
_LISTSEMI = re.compile(r"^\s*([^\W\d]\w*)\s*=\s*\[([^\[\]]*;[^\[\]]*)\]\s*$")
SWEEP_N = 61                                               # Punkte des Verlaufs über die Grenzen eines Schiebers
MAX_RANGE = 5001


def _names(text: str) -> set:
    t = re.sub(r'"[^"]*"', " ", str(text))
    for g, n in E.GREEK.items():
        t = t.replace(g, f" {n} ")
    return set(_NAME.findall(t))


_QTY = re.compile(rf"^\s*([^\W\d]\w*)\s*=\s*({LU.NUM})\s*([^\d\s=(),;\[\]±][^=(),;\[\]±]*?)\s*$")
_QTY_UNIT = re.compile(rf"^\s*([^\W\d]\w*)\s*=\s*({LU.NUM})\s*\[([^\[\]=,;±]+)\]\s*$")     # L = 3 [m]: ausdrücklich Einheit
_ALGEBRA_UNITS = {"a", "d", "t", "u"}                      # Jahr, Tag, Tonne, u: als Buchstaben meist Variablen


def parse_qty(src: str) -> dict | None:
    """``m = 2 kg``, ``a = 9,81 m/s^2``, ``L = 3 [m]``: Zahl mit Einheit -> {name, value, unit, unit_names}; sonst None."""
    s = str(src or "")
    br = _QTY_UNIT.match(s)
    m = br or _QTY.match(s)
    if not m:
        return None
    name, val, unit = m.groups()
    unit = unit.strip().strip("[]").strip()
    if not unit or not re.search(r"[^\W\d]|°", unit):
        return None
    if not br and (unit in ("a", "u") or (len(unit) == 1 and unit.isalpha()
                                          and not re.search(r"\s", m.group(0)[m.end(2):m.start(3)]))):
        return None                                        # 2a, 2t, 2 a: Algebra, kein Jahr und keine Tonne
    try:
        dims = U.parse_unit(U.split_delta(unit)[0])[1]
    except (U.UnitError, ValueError, KeyError, TypeError):
        return None
    return {"name": E.norm_name(name), "value": float(val.replace(",", ".").replace("−", "-")), "value_text": val,
            "unit": unit, "dims": dims, "unit_names": set(_NAME.findall(unit)), "explicit": bool(br)}


def unit_stands(q: dict, clash: set) -> bool:
    """Bleibt die Einheit, obwohl Namen in ihr auf der Seite stehen? Eine ausdrücklich geklammerte immer, eine
    zusammengesetzte (m/s^2), solange mindestens ein Teil kein Seitenname und kein typischer Variablenbuchstabe ist;
    sonst ist es Algebra (s = 0.5 a t^2)."""
    if q.get("explicit"):
        return True
    return len(q["unit_names"]) >= 2 and bool(q["unit_names"] - clash - _ALGEBRA_UNITS)


def unit_note(q: dict, clash: set, lang: str) -> str:
    names = ", ".join(sorted(clash))
    hint = f"{q['name']} = {q['value_text']} [{q['unit']}]"
    if lang == "de":
        return f"{names} steht auf dieser Seite und gilt hier als Variable, nicht als Einheit. Für die Einheit: {hint}"
    return f"{names} is a name on this page and is read as the variable, not as a unit. For the unit write: {hint}"


def prepare(src: str, lang: str = "de", qty: bool = True) -> dict:
    """Eine Zeile für Reihenfolge und Auswertung: {kind, src, name, defs, uses, …}.

    kind: None (gewöhnliche Zeile), "chain" (x = f(t) = t^5 − 3: Funktion und Wert), "range" (t = 0..10 step 0.5 /
    count 21), "list" (t = [1; 2; 5]), "slider" (t = 0..10 slider: ein Wert, mit dem Schieber gewählt), "pm"
    (x = 5,0 ± 0,1 mm: Wert mit Messunsicherheit, siehe lineunc), "qty" (m = 2 kg: Zahl mit Einheit; ein Name, den die
    Seite definiert, geht der Einheit vor)."""
    s = str(src).strip()
    try:
        pm = LU.parse_pm(s, lang)
    except E.CalcError as e:
        m = LU._PM.match(s)
        return {"kind": "pm", "name": E.norm_name(m.group(1)), "src": s, "pm": None, "pm_error": str(e),
                "defs": {E.norm_name(m.group(1))}, "uses": set()}
    if pm:
        return {"kind": "pm", "name": pm["name"], "src": s, "pm": pm, "defs": {pm["name"]}, "uses": set()}
    q = parse_qty(s) if qty else None
    if q:
        return {"kind": "qty", "name": q["name"], "src": s, "qty": q, "defs": {q["name"]}, "uses": set(),
                "unit_names": q["unit_names"]}
    m = _CHAIN.match(s)
    if m and m.group(2) not in E.BUILTINS and m.group(2) not in E.SPECIAL:
        name, fn, args, body = m.groups()
        argl = [a.strip() for a in args.split(",") if a.strip()]
        if argl and all(re.fullmatch(r"[^\W\d]\w*", a) for a in argl):
            call = f"{fn}({', '.join(argl)})"
            return {"kind": "chain", "name": E.norm_name(name), "fn": E.norm_name(fn), "src": f"{name} = {call}",
                    "func_src": f"{call} = {body.strip()}", "defs": {E.norm_name(name), E.norm_name(fn)},
                    "uses": (_names(body) - set(argl)) | _names(" ".join(argl))}
    m = _RANGE.match(s)
    if m and "=" not in (m.group(2) + m.group(3)) and "[" not in m.group(2):
        name, lo, hi, how, amount, sl = m.groups()
        return {"kind": "slider" if sl else "range", "name": E.norm_name(name), "lo": lo.strip(), "hi": hi.strip(),
                "how": (how or "").lower(), "amount": (amount or "").strip(), "src": s,
                "defs": {E.norm_name(name)}, "uses": _names(f"{lo} {hi} {amount or ''}")}
    m = _LISTSEMI.match(s)
    if m:
        items = [x.strip() for x in m.group(2).split(";") if x.strip()]
        return {"kind": "list", "name": E.norm_name(m.group(1)), "src": f"{m.group(1)} = [{', '.join(items)}]",
                "defs": {E.norm_name(m.group(1))}, "uses": _names(m.group(2))}
    try:
        st = E.split_statement(s)
    except E.CalcError:
        return {"kind": None, "stmt": None, "src": s, "defs": set(), "uses": _names(s)}
    k = st[0]
    if k == "assign":
        defs, uses = {E.norm_name(st[1])}, _names(st[2])
    elif k == "func":
        defs, uses = {E.norm_name(st[1])}, _names(st[3]) - set(st[2])
    elif k in ("equation", "system"):
        defs, uses = set(), _names(s)
    else:
        defs, uses = set(), _names(_body(s))
    return {"kind": None, "stmt": k, "src": s, "defs": defs, "uses": uses}


def line_order(preps: list, known=frozenset(), lang="de", deps_out: list | None = None):
    """Auswertungsreihenfolge einer Seite (RC-02): -> (Indizes, Fehler je Index, Hinweise je Index).

    ``deps_out`` (Liste) bekommt je Zeile die Indizes der Zeilen, von denen sie direkt abhängt (Messunsicherheit).

    Die Zeilen dürfen in beliebiger Reihenfolge stehen. Ein Name gilt aus der nächsten Zeile darüber, die ihn
    definiert, sonst aus der ersten darunter (so bleiben x = 1 … x = 2x wie bisher der Reihe nach). Zeilen, die
    denselben Namen definieren, bleiben in Seitenreihenfolge; „ans“ ist das Ergebnis der Zeile davor. Eine Gleichung
    definiert ihre Unbekannten (Namen, die sonst niemand definiert). Zirkelbezüge werden je Zeile gemeldet; was
    davon abhängt, rechnet danach (mit offenen Namen symbolisch)."""
    n = len(preps)
    def_at = {}
    for i, p in enumerate(preps):
        if p.get("stmt") in ("equation", "system"):       # wird unten bestimmt (die Reihenfolge kann zweimal laufen)
            p["defs"] = set()
        for d in p["defs"]:
            def_at.setdefault(d, []).append(i)
    for i, p in enumerate(preps):
        if p.get("stmt") in ("equation", "system"):
            p["defs"] = {u for u in p["uses"] if u not in def_at and u not in known
                         and u not in E.BUILTINS and u not in E.SPECIAL}
    for i, p in enumerate(preps):
        if p.get("stmt") in ("equation", "system"):
            for d in p["defs"]:
                def_at.setdefault(d, []).append(i)
    deps = [set() for _ in range(n)]
    notes = {}
    for i, p in enumerate(preps):
        for u in sorted(p["uses"]):
            if p.get("stmt") in ("equation", "system") and u in p["defs"]:
                continue
            ds = [j for j in def_at.get(u, []) if j != i]
            if not ds:
                continue
            above = [j for j in ds if j < i]
            deps[i].add(above[-1] if above else ds[0])
            if not above and len(ds) > 1:
                notes[i] = (f"{u} ist mehrfach definiert; verwendet wird Zeile {ds[0] + 1}" if lang == "de"
                            else f"{u} is defined more than once; line {ds[0] + 1} is used")
        if "ans" in p["uses"] and i > 0:
            deps[i].add(i - 1)
    if deps_out is not None:                                  # Datenabhängigkeiten (ohne reine Reihenfolge)
        deps_out[:] = [set(d) for d in deps]
    for js in def_at.values():
        js = sorted(set(js))
        for a, b in zip(js, js[1:]):
            deps[b].add(a)
    users = [[] for _ in range(n)]
    indeg = [len(d) for d in deps]
    for i, d in enumerate(deps):
        for j in d:
            users[j].append(i)
    heap = [i for i in range(n) if indeg[i] == 0]
    heapq.heapify(heap)
    order = []
    while heap:
        i = heapq.heappop(heap)
        order.append(i)
        for k in users[i]:
            indeg[k] -= 1
            if indeg[k] == 0:
                heapq.heappush(heap, k)
    rest = [i for i in range(n) if i not in set(order)]
    errors = {}

    def reach(a, b):                                          # führt eine Abhängigkeit von a zurück zu b?
        seen, todo = set(), [a]
        while todo:
            x = todo.pop()
            for y in deps[x]:
                if y == b:
                    return True
                if y not in seen:
                    seen.add(y)
                    todo.append(y)
        return False
    cyc = [i for i in rest if reach(i, i)]
    if cyc:
        twice = _solved_twice(preps, cyc, def_at, reach)
        for i, (names, lines) in twice.items():
            errors[i] = _twice_text(names, lines, lang)
        loop = [i for i in cyc if i not in twice]
        names = sorted(set().union(*(preps[i]["defs"] for i in loop))) if loop else []
        for i in loop:
            errors[i] = (f"Zirkelbezug: {', '.join(names)} hängen voneinander ab (Zeilen "
                         f"{', '.join(str(j + 1) for j in loop)})" if lang == "de" else
                         f"Circular reference: {', '.join(names)} depend on each other (lines "
                         f"{', '.join(str(j + 1) for j in loop)})")
    return order + rest, errors, notes


def _solved_twice(preps, cyc, def_at, reach) -> dict:
    """Zeilen eines Kreises, in dem zwei Gleichungen denselben Namen bestimmen: {Zeile: (Namen, Zeilen)}.

    ``x^2 = k`` zählt als Gleichung, wenn k schon anderswo definiert ist; sonst legt die Zeile k an."""
    out = {}
    for i in cyc:
        group = [j for j in cyc if j == i or (reach(i, j) and reach(j, i))]

        def unknowns(j):
            p = preps[j]
            if p.get("stmt") in ("equation", "system"):
                return set(p["defs"])
            if p.get("stmt") == "assign" and not E.ASSIGN.match(p["src"]) \
                    and any(k != j for d in p["defs"] for k in def_at.get(d, [])):
                return {u for u in p["uses"] if u in def_at and set(def_at[u]) <= set(group)}
            return set()
        solved = {j: unknowns(j) for j in group}
        names = sorted(u for u in set().union(*solved.values()) if sum(u in s for s in solved.values()) > 1)
        if names:
            out[i] = (names, [j for j in group if solved[j] & set(names)])
    return out


def _twice_text(names, lines, lang) -> str:
    nums = [str(j + 1) for j in sorted(lines)]
    who = ", ".join(names)
    if lang == "de":
        count = "zwei" if len(nums) == 2 else str(len(nums))
        return (f"{who} {'werden' if len(names) > 1 else 'wird'} von {count} Zeilen bestimmt (Zeilen "
                f"{', '.join(nums[:-1])} und {nums[-1]}); eine davon entfernen oder einen anderen Namen verwenden")
    count = "two" if len(nums) == 2 else str(len(nums))
    return (f"{who} {'are' if len(names) > 1 else 'is'} determined by {count} lines (lines "
            f"{', '.join(nums[:-1])} and {nums[-1]}); remove one or use a different name")


_ERRS = (E.CalcError, U.UnitError, E.DimError, ValueError, TypeError, ZeroDivisionError, OverflowError, IndexError,
         np.linalg.LinAlgError)


def _flat(v) -> bool:
    return isinstance(v, list) and len(v) > 0 and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v)


def _fmt(v) -> str:
    return format(float(v), ".12g")


def _run_lines(req, q, calc, preps, order, cyc_err, order_notes, base, ds_set, lang, override=None):
    """Rechenzeilen in der Auswertungsreihenfolge rechnen. `override`: Name eines Schiebers, der statt seines Werts
    über seine Grenzen läuft (Verlauf, RC-04)."""
    vars_, vdims, vpdims = dict(base[0]), dict(base[1]), dict(base[2])
    vtdiff, imported = set(base[3]), dict(base[4])
    funcs, lines, symbolic = {}, {}, {}
    ds_used, assigned = set(), set()
    rdep, sdep, ranges, sliders = {}, {}, {}, {}          # Name -> Bereichsvariable / Schieber, von der er abhängt
    line_sdep = {}

    def ev(src, it=None):
        return CON.evaluate_line({"line": src, "quantities": q, "vars": vars_, "vdims": vdims, "vpdims": vpdims,
                                  "vtdiff": sorted(vtdiff), "funcs": funcs, "angle": req.get("angle", "rad"),
                                  "complex": req.get("complex"), "digits": req.get("digits", 10), "lang": lang,
                                  "pick": (it or {}).get("pick"), "symbolic": symbolic, "partial": True,
                                  "products": False})     # AB = C entscheidet run_env mit Blick auf die ganze Seite

    def num(src):
        r = ev(src)
        v = (r.get("result") or {}).get("value")
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise E.CalcError(f"„{src}“: Zahl erwartet" if lang == "de" else f"“{src}”: number expected")
        return float(v), r

    def store(r):
        if r.get("kind") in ("solve", "system"):           # S-01/S-02: Lösungen als Zeilenvariablen
            for s in r.get("sets") or []:
                vars_[s["name"]] = s["store"]
                imported.pop(s["name"], None)
                assigned.add(s["name"])
                vpdims.pop(s["name"], None)
                if s.get("dims"):
                    vdims[s["name"]] = s["dims"]
                else:
                    vdims.pop(s["name"], None)
            if r.get("store") is not None:
                vars_["ans"] = r["store"]
            vdims.pop("ans", None)
            vpdims.pop("ans", None)
        elif r.get("kind") == "assign":
            vars_[r["name"]] = r["store"]
            vars_["ans"] = r["store"]
            imported.pop(r["name"], None)
            assigned.add(r["name"])
            for k in (r["name"], "ans"):
                if r.get("dims"):
                    vdims[k] = r["dims"]
                else:
                    vdims.pop(k, None)
                if r.get("tdiff"):
                    vtdiff.add(k)
                else:
                    vtdiff.discard(k)
                if r.get("pdims"):
                    vpdims[k] = r["pdims"]
                else:
                    vpdims.pop(k, None)
        elif r.get("kind") == "func":
            funcs[r["name"]] = {"args": r["args"], "body": r["body"]}
        elif r.get("store") is not None:
            vars_["ans"] = r["store"]
            if r.get("dims") and not r.get("pdims"):
                vdims["ans"] = r["dims"]
            else:
                vdims.pop("ans", None)
            vtdiff.discard("ans")
            if r.get("pdims"):
                vpdims["ans"] = r["pdims"]
            else:
                vpdims.pop("ans", None)

    def evaluate(p, it):
        k = p.get("kind")
        if k == "pm":                                     # x = 5,0 ± 0,1 mm: Wert in SI, Einheit für spätere Zeilen
            if not p.get("pm"):
                raise E.CalcError(p.get("pm_error") or "±")
            pm = p["pm"]
            a, b = LU.affine(pm["unit"])
            si = a + b * pm["value"]
            r = ev(f"{p['name']} = {si!r}", it)
            show = LU.pm_line(pm, lang)
            r.update(html=show["html"], tex=show["tex"], pm={"value": pm["value"], "amount": pm["amount"],
                                                             "unit": pm["unit"], "k": pm["k"], "dist": pm["dist"]})
            for f in ("dims", "unit", "tdiff"):
                r.pop(f, None)
            if show["dims"]:
                r["dims"], r["unit"] = show["dims"], show["unit"]
                r["result_tex"] = R.num_tex(si, lang, 8) + r"\," + R.unit_tex(CON.unit_plain(show["unit"]))
                if U.deq(show["dims"], U.parse_unit("K")[1]):
                    r["tdiff"] = show["tdiff"]
            return r
        if k == "qty":                                    # m = 2 kg: Wert in SI, Einheit für spätere Zeilen
            qt = p["qty"]
            a, b = LU.affine(qt["unit"])
            si = a + b * qt["value"]
            r = ev(f"{p['name']} = {si!r}", it)
            for f in ("dims", "unit", "tdiff"):
                r.pop(f, None)
            vt = qt["value_text"].replace(",", ".").replace("−", "-")
            vt = vt.replace(".", ",") if lang == "de" else vt
            r["html"] = f"{R.sym_html(p['name'])} = {vt} {R.unit_html(qt['unit'])}"
            r["tex"] = f"{R.sym_tex(p['name'])} = {vt.replace(',', '{,}')}\\," + R.unit_tex(U.split_delta(qt["unit"])[0])
            if not U.deq(qt["dims"], U.D0):
                r["dims"], r["unit"] = list(qt["dims"]), U.dims_text(qt["dims"])
                r["result_tex"] = R.num_tex(si, lang, 8) + r"\," + R.unit_tex(CON.unit_plain(r["unit"]))
                if U.deq(qt["dims"], U.parse_unit("K")[1]):
                    r["tdiff"] = U.split_delta(qt["unit"])[1]
            r["qty"] = {"value": qt["value"], "unit": qt["unit"]}
            return r
        if k == "chain":                                  # x = f(t) = t^5 − 3
            rf = ev(p["func_src"])
            store(rf)
            r = ev(p["src"], it)
            if rf.get("html") and " = " in rf["html"]:
                r["html"] = f"{r.get('html', '')} = {rf['html'].split(' = ', 1)[1]}"
            if rf.get("tex") and " = " in rf["tex"]:
                r["tex"] = f"{r.get('tex', '')} = {rf['tex'].split(' = ', 1)[1]}"
            r["func"] = rf.get("name")
            return r
        if k == "list":
            r = ev(p["src"], it)
            r["range_var"] = p["name"]
            return r
        if k in ("range", "slider"):
            name = p["name"]
            lo, rlo = num(p["lo"])
            hi, rhi = num(p["hi"])
            if hi == lo:
                raise E.CalcError("Bereich: Anfang und Ende sind gleich" if lang == "de" else "Range: start equals end")
            sym_h, sym_t = R.sym_html(name), R.sym_tex(name)
            lo_h, hi_h = (rlo.get("result") or {}).get("text", _fmt(lo)), (rhi.get("result") or {}).get("text", _fmt(hi))
            if k == "slider":
                step = abs(num(p["amount"])[0]) if p["how"] in ("step", "schritt") and p["amount"] else abs(hi - lo) / 100
                cur = it.get("cur")
                cur = float(cur) if isinstance(cur, (int, float)) and not isinstance(cur, bool) else lo
                cur = min(max(cur, min(lo, hi)), max(lo, hi))
                src = f"{name} = linspace({_fmt(lo)}, {_fmt(hi)}, {SWEEP_N})" if override == name else f"{name} = {_fmt(cur)}"
                r = ev(src, it)
                sliders[name] = {"lo": lo, "hi": hi, "step": step, "cur": cur, "unit": r.get("unit") or ""}
                r["slider"] = dict(sliders[name])
                r["html"] = f"{sym_h} = {r.get('result', {}).get('text', _fmt(cur))}"
                r["tex"] = f"{sym_t}"
                r["slider"]["text"] = f"{lo_h} … {hi_h}"
                return r
            if p["how"] in ("count", "anzahl"):
                n = int(round(num(p["amount"])[0]))
                if not 2 <= n <= MAX_RANGE:
                    raise E.CalcError(f"Bereich: 2 bis {MAX_RANGE} Werte" if lang == "de" else f"Range: 2 to {MAX_RANGE} values")
                src, how = f"{name} = linspace({_fmt(lo)}, {_fmt(hi)}, {n})", (f"{n} Werte" if lang == "de" else f"{n} values")
            else:
                if p["how"] in ("step", "schritt"):
                    step = abs(num(p["amount"])[0])
                elif float(lo).is_integer() and float(hi).is_integer() and abs(hi - lo) <= 1000:
                    step = 1.0
                else:
                    step = abs(hi - lo) / 50
                if step == 0 or abs(hi - lo) / step + 1 > MAX_RANGE:
                    raise E.CalcError(f"Bereich: höchstens {MAX_RANGE} Werte" if lang == "de" else f"Range: at most {MAX_RANGE} values")
                step = step if hi > lo else -step
                src = f"{name} = seq({_fmt(lo)}, {_fmt(hi)}, {_fmt(step)})"
                how = (f"Schritt {_fmt(abs(step)).replace('.', ',')}" if lang == "de" else f"step {_fmt(abs(step))}")
            r = ev(src, it)
            r["range_var"] = name
            r["html"] = f"{sym_h} = {lo_h} … {hi_h} <span class=\"small\">({how})</span>"
            r["tex"] = r"%s = %s \ldots %s\ (\mbox{%s})" % (sym_t, R.num_tex(lo, lang, 6), R.num_tex(hi, lang, 6), how)
            return r
        return ev(p["src"], it)

    for i in order:
        it = calc[i]
        iid = str(it.get("id"))
        p = preps[i]
        if p is None:
            lines[iid] = {"empty": True}
            continue
        if i in cyc_err:
            lines[iid] = {"error": cyc_err[i]}
            continue
        if ds_set:
            ds_used.update((p["uses"] & ds_set) - assigned)
        try:
            r = evaluate(p, it)
        except _ERRS as e:
            lines[iid] = {"error": str(e)}
            continue
        node = r.pop("_node", None)
        if r.get("kind") == "symbolic" and r.get("name") and node is not None:
            symbolic[r["name"]] = node
        store(r)
        own = p["name"] if p.get("kind") in ("range", "list") else None
        rv = own or next((rdep[u] for u in sorted(p["uses"]) if u in rdep), None)
        val0 = (r.get("result") or {}).get("value")
        if not rv and r.get("kind") == "assign" and r.get("name") and _flat(val0) and len(val0) >= 2:
            own = rv = r["name"]                          # t = eps (Datensatzspalte), t = linspace(…): auch ein Bereich
        sv = p["name"] if p.get("kind") == "slider" else next((sdep[u] for u in sorted(p["uses"]) if u in sdep), None)
        for d in p["defs"] | ({r["name"]} if r.get("kind") == "assign" else set()):
            if rv:
                rdep[d] = rv
            if sv:
                sdep[d] = sv
        if sv and p.get("kind") != "slider":
            line_sdep[i] = {sv}
        val = (r.get("result") or {}).get("value")
        if own and _flat(val):
            mono = len(val) >= 8 and (all(a < b for a, b in zip(val, val[1:])) or all(a > b for a, b in zip(val, val[1:])))
            ranges[own] = {"x": val, "unit": r.get("unit") or "",
                           "list": p.get("kind") == "list" or (p.get("kind") != "range" and not mono)}
        elif rv and rv in ranges and _flat(val) and len(val) == len(ranges[rv]["x"]) and r.get("kind") in ("assign", "expr"):
            r["range"] = {"var": rv, "x": ranges[rv]["x"], "xunit": ranges[rv]["unit"], "list": ranges[rv]["list"]}
        for extra in (p.get("note"), order_notes.get(i)):
            if extra:
                r["notes"] = [*(r.get("notes") or []), extra]
        lines[iid] = r
    return {"lines": lines, "vars": vars_, "imported": imported, "ds_used": ds_used, "assigned": assigned,
            "sliders": sliders, "sdep": line_sdep, "funcs": funcs}


def applies(value: dict, env_id: str) -> bool:
    sc = value.get("scope", "all")
    if sc in (None, "all", ""):
        return True
    return isinstance(sc, (list, tuple)) and str(env_id) in [str(x) for x in sc]


def env_values(values, env_id):
    return [v for v in values or [] if applies(v, env_id)]


def env_cards(env: dict):
    return [it for it in env.get("items") or [] if it.get("type", "card") == "card"]


def env_sheet_state(req: dict, env: dict) -> dict:
    """Arbeitsblatt einer Umgebung im Format von solver.Sheet."""
    return {"values": env_values(req.get("values"), env.get("id")), "cards": env_cards(env),
            "derive": env.get("derive", req.get("derive", True)) is not False, "lang": req.get("lang", "de")}


def quantities_of(sh: S.Sheet) -> dict:
    """Name -> {si, kind} für Rechenzeilen; Vorrang: eigene Grösse > Kartenergebnis > abgeleitet."""
    q = {}
    for group in (sh.derived.values(), sh.card_known.values(), sh.user.values()):
        for kn in group:
            q[kn.sym] = {"si": kn.si, "kind": kn.kind}
    for kn in sh.user.values():                       # eigener Name gilt in Rechenzeilen zusätzlich zur Rolle
        if kn.name and kn.name != kn.sym:
            q[kn.name] = {"si": kn.si, "kind": kn.kind}
    return q


def _scalar_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and np.isfinite(v)


def page_values(calc: list, lines: dict) -> dict:
    """Zahlenwerte der Rechenzeilen einer Seite für die Formelkarten: {Name: {si, dims, line}}."""
    page = {}
    for it in calc:
        r = lines.get(str(it.get("id"))) or {}
        if r.get("error"):
            continue
        if r.get("kind") == "assign" and r.get("name") and _scalar_num(r.get("store")):
            page[r["name"]] = {"si": float(r["store"]), "dims": r.get("dims"), "line": str(it.get("id"))}
        elif r.get("kind") in ("solve", "system"):
            for s in r.get("sets") or []:
                if _scalar_num(s.get("store")):
                    page[s["name"]] = {"si": float(s["store"]), "dims": s.get("dims"), "line": str(it.get("id"))}
    page.pop("ans", None)
    return page


def eval_env(req: dict, env: dict, imports=None) -> dict:
    return run_env(req, env, imports)[1]


def run_env(req: dict, env: dict, imports=None):
    """(Arbeitsblatt, Ergebnis) einer Umgebung; das Arbeitsblatt braucht der Bericht für die Grössentabelle.

    `imports`: Zeilenvariablen anderer Blätter, die dort zum Weitergeben markiert sind ({name: {store, dims, env}}).
    Eine Zeile ``50/3 = u`` oder ``u = 50/3`` legt u auf diesem Blatt an; spätere Zeilen rechnen damit (mit Einheit)."""
    lang = req.get("lang", "de")
    sh = S.Sheet(env_sheet_state(req, env)).run()
    out = sh.to_dict()
    q = quantities_of(sh)
    out["known"] = [{"sym": k, **v} for k, v in q.items()]
    vars_ = dict(req.get("vars") or {})
    vdims, vpdims = {}, {}
    vtdiff = set()                                        # Zeilenvariablen, die Temperaturdifferenzen sind (T2 − T1)
    imported = {}
    # DP-11: Spalten eines Datensatzes als Listen mit Einheit (vom Server aufgelöst, gelten auf allen Blättern);
    # eine eigene Matrix oder Grösse gleichen Namens geht vor
    dsnames, shadowed = [], []
    for name, x in (req.get("dsvals") or {}).items():
        if name in vars_ or name in q:
            shadowed.append(name)
            continue
        vars_[name] = x["store"]
        if x.get("dims"):
            vdims[name] = x["dims"]
        dsnames.append(name)
    for name, x in (imports or {}).items():
        if name in vars_ or name in q:                    # eigene Matrix bzw. Grösse geht vor
            continue
        vars_[name] = x["store"]
        if x.get("dims"):
            vdims[name] = x["dims"]
        imported[name] = x.get("env")
    ds_set = set(dsnames)
    calc = [it for it in env.get("items") or [] if it.get("type") == "calc"]
    preps = [prepare(str(it.get("src") or ""), lang) if str(it.get("src") or "").strip() else None for it in calc]
    known = set(q) | set(vars_) | set(U.CONSTANTS)
    page_defs = set().union(*(p["defs"] for p in preps if p)) if any(preps) else set()
    for i, p in enumerate(preps):                         # d/dx(x^3) wie diff(x^3, x), solange d und dx keine Namen sind
        if p and p.get("kind") is None and "/" in p["src"]:
            s2 = E.rewrite_ddx(p["src"], known | page_defs)
            if s2 != p["src"]:
                preps[i] = prepare(s2, lang)
    page_defs = set().union(*(p["defs"] for p in preps if p)) if any(preps) else set()
    def elsewhere(i):                                     # Namen, die eine andere Zeile der Seite definiert
        return set().union(*(x["defs"] for j, x in enumerate(preps) if x and j != i))
    for i, p in enumerate(preps):                         # m = 2 kg; aber F = 2 m, wenn m auf der Seite steht
        if p and p.get("kind") == "qty":
            clash = p["unit_names"] & (known | elsewhere(i))
            if clash and not unit_stands(p["qty"], clash):
                note = unit_note(p["qty"], clash, lang)
                preps[i] = prepare(p["src"], lang, qty=False)
                preps[i]["note"] = note
    blank = {"kind": None, "defs": set(), "uses": set()}
    deps = []
    order, cyc_err, order_notes = line_order([p or dict(blank) for p in preps], known, lang, deps_out=deps)
    base = (vars_, vdims, vpdims, vtdiff, imported)
    base_vars = dict(vars_)
    run = _run_lines(req, q, calc, preps, order, cyc_err, order_notes, base, ds_set, lang)
    # AB = C: A und B sind Matrizen der Seite, AB gibt es nicht -> A*B = C (C = AB ebenso)
    products = {}
    for i, p in enumerate(preps):
        if p and p.get("kind") is None and p.get("stmt") == "assign":
            try:
                hit = CON.split_product(E.split_statement(p["src"]), set(q) | set(vars_) | elsewhere(i))
            except E.CalcError:
                hit = None
            if hit and all(f in run["vars"] or f in q for f in hit[0]) \
                    and any(isinstance(run["vars"].get(f), list) for f in hit[0]):
                products[i] = hit
    if products:
        for i, (parts, target) in products.items():
            preps[i] = prepare(f"{target} = {'*'.join(parts)}", lang, qty=False)
            if len(parts) > 1:
                preps[i]["note"] = CON.product_note(parts, lang)
        deps = []
        order, cyc_err, order_notes = line_order([p or dict(blank) for p in preps], known, lang, deps_out=deps)
        run = _run_lines(req, q, calc, preps, order, cyc_err, order_notes, base, ds_set, lang)
    # Formelkarten mit den Werten der Rechenzeilen dieser Seite (m = 2 kg speist F = m·a); ändern sich dadurch
    # Kartenergebnisse, rechnen die Zeilen ein zweites Mal
    page = {}
    if env_cards(env):
        page = {n: {"si": float(x["store"]), "dims": x.get("dims"), "line": None, "from": x.get("env")}
                for n, x in (imports or {}).items() if n in imported and _scalar_num(x.get("store"))}
        page.update(page_values(calc, run["lines"]))
    if page:
        st = env_sheet_state(req, env)
        st["page"] = page
        sh2 = S.Sheet(st).run()
        q2 = quantities_of(sh2)
        sh, out = sh2, sh2.to_dict()
        out["known"] = [{"sym": k, **v} for k, v in q2.items()]
        if q2 != q:
            q = q2
            known = set(q) | set(base_vars) | set(U.CONSTANTS)
            deps = []
            order, cyc_err, order_notes = line_order([p or {"kind": None, "defs": set(), "uses": set()} for p in preps],
                                                     known, lang, deps_out=deps)
            run = _run_lines(req, q, calc, preps, order, cyc_err, order_notes, base, ds_set, lang)
    # Messunsicherheit: Eingaben mit ± und alles, was davon abhängt (Kette im Modell nachgerechnet)
    for i, it in enumerate(calc):                         # Wertzeilen bekommen in der Seite den ±-Knopf
        r = run["lines"].get(str(it.get("id")))
        if r and LU.is_value_line(preps[i], r):
            r["value_line"] = True
    if req.get("unc") != "off":
        used_imp = {n: (imports or {})[n] for n in imported if n in (imports or {})}
        try:
            us = LU.propagate(req, env, sh, q, calc, preps, order, deps, run["lines"], base_vars, run["funcs"], used_imp, lang)
        except Exception as e:  # noqa: BLE001 – die Unsicherheit darf die Rechnung nie verhindern
            us = {"error": f"{type(e).__name__}: {e}"}
        if us:
            out["errors"].update(us.pop("var_errors", None) or {})
            if us.get("inputs") or us.get("error"):
                out["unc"] = us
    vars_, imported = run["vars"], run["imported"]
    lines, ds_used, assigned = run["lines"], run["ds_used"], run["assigned"]
    # RC-04: Verlauf über die Grenzen eines Schiebers für die Zeilen, die von ihm abhängen
    for s, info in run["sliders"].items():
        dep = [i for i in order if s in run["sdep"].get(i, ())]
        if not dep:
            continue
        sweep = _run_lines(req, q, calc, preps, order, cyc_err, {}, base, ds_set, lang, override=s)["lines"]
        xs = np.linspace(info["lo"], info["hi"], SWEEP_N).tolist()
        for i in dep:
            iid = str(calc[i].get("id"))
            r, r2 = lines.get(iid) or {}, sweep.get(iid) or {}
            ys = (r2.get("result") or {}).get("value")
            if r.get("kind") in ("assign", "expr") and _flat(ys) and len(ys) == SWEEP_N:
                r["sweep"] = {"var": s, "x": xs, "y": ys, "cur": info["cur"], "unit": r2.get("unit") or "",
                              "xunit": info.get("unit") or ""}
    out["lines"] = lines
    out["order"] = [str(calc[i].get("id")) for i in order]
    out["imported"] = imported
    out["dsvars"] = dsnames                               # DP-11: Datensatz-Variablen auf diesem Blatt
    out["ds_used"] = sorted(ds_used)                      # … und die davon in Rechenzeilen benutzten
    if shadowed:
        out["ds_shadowed"] = shadowed
    out["locals"] = sorted(k for k in vars_ if k != "ans" and k not in (req.get("vars") or {}) and k not in imported
                           and (k not in ds_set or k in assigned))
    return sh, out


def exports_of(env: dict, out: dict) -> dict:
    """Zeilenvariablen eines Blatts, die an die anderen Blätter gehen (Zeile mit export: true)."""
    res = {}
    cards = {str(c.get("id")): c for c in out.get("cards") or []}
    for it in env.get("items") or []:
        if it.get("type", "card") == "card" and it.get("export"):    # Ergebnis einer Formelkarte
            c = cards.get(str(it.get("id"))) or {}
            rs = c.get("result") or {}
            if c.get("status") == "ok" and rs.get("sym") and _scalar_num(rs.get("si")):
                dims = U.KINDS[rs["kind"]].dims if rs.get("kind") in U.KINDS else None
                dims = None if dims is None or U.deq(dims, U.D0) else list(dims)
                res.setdefault(rs["sym"], {"store": float(rs["si"]), "dims": dims,
                                           "unit": U.dims_text(dims) if dims else "", "env": str(env.get("id")),
                                           "line": str(it.get("id")), "card": True, "kind": rs.get("kind")})
            continue
        if it.get("type") == "calc" and it.get("export"):
            r = (out.get("lines") or {}).get(str(it.get("id"))) or {}
            if r.get("kind") == "assign" and r.get("store") is not None:
                res[r["name"]] = {"store": r["store"], "dims": r.get("dims"), "unit": r.get("unit") or "",
                                  "env": str(env.get("id")), "line": str(it.get("id"))}
                u = LU.std_u(r)                         # Messunsicherheit reist mit (Standardunsicherheit in SI)
                if u:
                    res[r["name"]].update(u=u, env_name=str(env.get("name") or ""))
            elif r.get("kind") in ("solve", "system"):     # gelöste Gleichung: ihre Lösungsvariablen
                for s in r.get("sets") or []:
                    res[s["name"]] = {"store": s["store"], "dims": s.get("dims"),
                                      "unit": U.dims_text(s["dims"]) if s.get("dims") else "",
                                      "env": str(env.get("id")), "line": str(it.get("id"))}
    return res


def run_all(req: dict, envs: list):
    """Alle Blätter rechnen, mit den weitergegebenen Zeilenvariablen der anderen Blätter.

    Höchstens drei Durchgänge: Blatt B kann eine Variable von A brauchen, die A erst im ersten Durchgang anlegt.
    Gibt [(env, Arbeitsblatt, Ergebnis)] und die Weitergaben {name: {store, dims, unit, env, line}} zurück; derselbe
    Name auf zwei Blättern: das erste Blatt gilt."""
    exports, runs = {}, []
    for _ in range(3):
        runs, new = [], {}
        for env in envs:
            eid = str(env.get("id"))
            sh, o = run_env(req, env, {k: v for k, v in exports.items() if v["env"] != eid})
            runs.append((env, sh, o))
            for k, v in exports_of(env, o).items():
                new.setdefault(k, v)
        if new == exports:
            break
        exports = new
    return runs, exports


def evaluate(req: dict) -> dict:
    """Alle Umgebungen rechnen. Fehler der Grössen werden je Grösse gesammelt, auch für Grössen ohne Umgebung."""
    envs = req.get("envs") or []
    out = {"envs": {}, "errors": {}}
    used = set()
    runs, exports = run_all(req, envs)
    out["exports"] = {k: {"env": v["env"], "line": v["line"], "unit": v["unit"], **({"card": True} if v.get("card") else {})}
                      for k, v in exports.items()}
    out["datasets"] = req.get("dsinfo") or []              # DP-11: Herkunft der Datensatz-Variablen je Bindung
    for env, _sh, o in runs:
        out["envs"][str(env.get("id"))] = o
        out["errors"].update(o["errors"])
        used.update(str(v.get("id")) for v in env_values(req.get("values"), env.get("id")))
        for n in o.get("ds_shadowed") or []:
            out.setdefault("ds_shadowed", {}).setdefault(n, []).append(str(env.get("id")))
    glob = S.Sheet({"values": [v for v in req.get("values") or [] if v.get("scope", "all") in (None, "all", "")],
                    "lang": req.get("lang", "de")})
    glob.load_values()
    out["global"] = [{"sym": s, "kind": kn.kind, "si": kn.si} for kn in glob.user.values()
                     for s in dict.fromkeys([kn.sym, kn.name])]
    for v in req.get("values") or []:
        if str(v.get("id")) in used:
            continue
        sh = S.Sheet({"values": [v], "lang": req.get("lang", "de")})
        sh.load_values()
        out["errors"].update(sh.errors)
    return out


def compare_line(req: dict) -> dict:
    """Messunsicherheit einer Rechenzeile nach allen vier Verfahren („Verfahren vergleichen“).

    ``req["unc_compare"] = {"env": Blatt, "line": Zeile}``; Rückgabe {gum, mc, gauss, worst} oder {"error"}."""
    want = req.get("unc_compare") or {}
    runs, _ = run_all(req, req.get("envs") or [])
    for env, _sh, o in runs:
        if str(env.get("id")) == str(want.get("env")):
            r = (o.get("lines") or {}).get(str(want.get("line"))) or {}
            if r.get("unc_compare"):
                return r["unc_compare"]
            return {"error": r.get("unc_error") or ("Zeile ohne Messunsicherheit" if req.get("lang", "de") == "de"
                                                    else "line without measurement uncertainty")}
    return {"error": "Blatt nicht gefunden" if req.get("lang", "de") == "de" else "sheet not found"}


def from_legacy(req: dict) -> dict:
    """Älterer Arbeitsstand (ein Arbeitsblatt, Grössen ohne Geltungsbereich) -> eine Umgebung."""
    if req.get("envs") is not None:
        return req
    sheet = req.get("sheet") or {}
    env = {"id": "u1", "name": "", "derive": sheet.get("derive", True),
           "items": [{**c, "type": "card"} for c in sheet.get("cards") or []]}
    return {**req, "values": [{**v, "scope": "all"} for v in sheet.get("values") or []], "envs": [env]}
