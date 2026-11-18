"""Umgebungen: Kästen mit Formelkarten und Rechenzeilen, je mit eigenen Grössen.

Eine Grösse gilt in allen Umgebungen (``scope: "all"``) oder nur in ausgewählten (``scope: [id, …]``). Jede
Umgebung ist ein eigenes Arbeitsblatt: Grössen nach Geltungsbereich, Ableiten, Formelkarten; danach laufen ihre
Rechenzeilen der Reihe nach, mit allen dort bekannten Werten (Grössen, Kartenergebnisse, abgeleitete Werte) und den
Zuweisungen der Zeilen davor. Der Server bleibt zustandslos.

DP-11: ``req["dsvals"]`` (von ``dsvars.attach`` aufgelöst) bringt Spalten von Datensätzen als Listenvariablen mit
Einheit; sie gelten auf allen Blättern, eine Grösse oder Matrix gleichen Namens geht vor.
"""
from __future__ import annotations

import re

from . import console as CON
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
    funcs = {}
    lines = {}
    ds_used, ds_set, assigned = set(), set(dsnames), set()
    for it in env.get("items") or []:
        if it.get("type") != "calc":
            continue
        iid = str(it.get("id"))
        src = str(it.get("src") or "").strip()
        if not src:
            lines[iid] = {"empty": True}
            continue
        if ds_set:
            ds_used.update((set(_NAME.findall(_body(src))) & ds_set) - assigned)
        try:
            r = CON.evaluate_line({"line": src, "quantities": q, "vars": vars_, "vdims": vdims, "vpdims": vpdims,
                                   "vtdiff": sorted(vtdiff),
                                   "funcs": funcs, "angle": req.get("angle", "rad"), "complex": req.get("complex"),
                                   "digits": req.get("digits", 10), "lang": lang, "pick": it.get("pick")})
        except (E.CalcError, U.UnitError, E.DimError, ValueError, TypeError, ZeroDivisionError, OverflowError) as e:
            lines[iid] = {"error": str(e)}
            continue
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
        lines[iid] = r
    out["lines"] = lines
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
    for it in env.get("items") or []:
        if it.get("type") == "calc" and it.get("export"):
            r = (out.get("lines") or {}).get(str(it.get("id"))) or {}
            if r.get("kind") == "assign" and r.get("store") is not None:
                res[r["name"]] = {"store": r["store"], "dims": r.get("dims"), "unit": r.get("unit") or "",
                                  "env": str(env.get("id")), "line": str(it.get("id"))}
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
    out["exports"] = {k: {"env": v["env"], "line": v["line"], "unit": v["unit"]} for k, v in exports.items()}
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


def from_legacy(req: dict) -> dict:
    """Älterer Arbeitsstand (ein Arbeitsblatt, Grössen ohne Geltungsbereich) -> eine Umgebung."""
    if req.get("envs") is not None:
        return req
    sheet = req.get("sheet") or {}
    env = {"id": "u1", "name": "", "derive": sheet.get("derive", True),
           "items": [{**c, "type": "card"} for c in sheet.get("cards") or []]}
    return {**req, "values": [{**v, "scope": "all"} for v in sheet.get("values") or []], "envs": [env]}
