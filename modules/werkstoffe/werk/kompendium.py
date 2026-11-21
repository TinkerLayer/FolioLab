"""Kompendium des Werkstoffe-Moduls: ein Nachschlagewerk, in dem jede Aussage ihre eigene Quelle trägt.

Einträge (``id``):

* ``tool:<werkzeug>`` mit Abschnitten ``tool:<werkzeug>#<ansicht>``: Verfahren je Ansicht und Verhalten des Werkzeugs;
* ``mech:<id>``: Bildfolge eines Mechanismus (``gefuege.MECHANISMS``);
* ``atlas:<id>``: Gefügebestandteil mit Steckbrief und Skizze (``gefuege.CONSTITUENTS``);
* ``topic:<id>``: Themen wie Cellulose beim Erwärmen oder Werkstoffbezeichnungen;
* ``material:<id>``: je Werkstoff der Datenbank Kennwerte mit Spanne, Quelle und Prüfstatus, die Bezeichnung nach ihrer
  Norm und die Phasen, Mechanismen und Gefüge, die wirklich zu ihm gehören.

Eine Aussage (``statements``) ist ``{id, text, keys, basis, software, unsourced, check}``. Die ``id`` ist stabil und das
Verweisziel für Pins (``statement(sid)``):

* ``basis``: ``statement`` (Quelle dieser Aussage zugeordnet), ``entry`` (Quellenliste des Eintrags, die Zuordnung zum
  einzelnen Satz steht noch aus), ``data`` (Quelle des Datensatzes) oder ``none``;
* ``unsourced``: ``None``, ``software`` (beschreibt das Programm, keine Literaturstelle nötig) oder ``open`` (Sachaussage
  ohne nachvollziehbare Quelle, offen für die Quellenprüfung);
* ``check``: ``unchecked`` (nur ungeprüfte Quellen), ``mixed``, ``partial``, ``no_record`` (kein Prüfvermerk) oder
  ``none``. „Kein Prüfvermerk“ heisst nicht „geprüft“: das Programm behauptet für keine Quelle eine vollständige Prüfung.

Der Text steht in ``data/kompendium_text.json``; Atlas, Mechanismen und Werkstoffe werden aus ihren Daten aufgebaut.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from . import refs as RF
from . import views as VW

DATA = Path(__file__).resolve().parent / "data" / "kompendium.json"
TEXT = Path(__file__).resolve().parent / "data" / "kompendium_text.json"
BEZ = "bezeichnung"


@lru_cache(maxsize=1)
def data() -> dict:
    return json.loads(DATA.read_text("utf-8"))


@lru_cache(maxsize=1)
def text() -> dict:
    return json.loads(TEXT.read_text("utf-8"))


def _i(lang: str) -> int:
    return 1 if lang == "en" else 0


def tool_name(tool: str, lang: str = "de") -> str:
    return data()["tools"][tool][_i(lang)]


def tool_desc(tool: str, lang: str = "de") -> str:
    return data()["tools"][tool][2 + _i(lang)]


def groups(lang: str = "de") -> list[dict]:
    """Werkzeuge nach Aufgabe gruppiert (für die Werkzeugleiste und die Suche)."""
    return [{"id": g["id"], "label": g["en" if lang == "en" else "de"], "tools": list(g["tools"]), "main": list(g.get("main") or g["tools"])}
            for g in data()["groups"]]


def group_of(tool: str) -> dict | None:
    return next((g for g in data()["groups"] if tool in g["tools"]), None)


def view_title(tool: str, vid: str, lang: str = "de") -> str:
    v = (data()["views"].get(tool) or {}).get(vid)
    return v[_i(lang)] if v else tool_name(tool, lang)


def _known(keys) -> list[str]:
    return [k for k in dict.fromkeys(keys or []) if k and RF.known(k)]


def link(tool: str, view: str | None = None, req: dict | None = None) -> str:
    """Eintrag zum Werkzeug bzw. zur Ansicht (der eine Verweis „im Kompendium“ je Ansicht)."""
    req = req or {}
    if tool == "struktur" and req.get("mode") == "mech":
        return "mech:" + str(req.get("mech") or "bain")
    if tool == "struktur" and req.get("mode") == "atlas":
        return "atlas:" + str(req.get("gef") or "perlit")
    if view and view != "_":
        return f"tool:{tool}#{view}"
    return "tool:" + tool


# ----------------------------------------------------------------------------- Prüfstatus
def status_of(rec: dict | None) -> str:
    """Prüfstatus einer Quelle aus ihrem Vermerk: ``unchecked``, ``partial`` (Teil geprüft) oder ``no_record``."""
    note = str((rec or {}).get("note") or "")
    if RF.NG in note:
        return "unchecked"
    rest = re.sub(r"nicht[^;.]*geprüft", "", note)
    return "partial" if "geprüft" in rest else "no_record"


def _rec(key: str) -> dict | None:
    """Quellendatensatz über alle Register, auch die Normen der Spannen (``ranges.json``)."""
    if RF.known(key):
        return RF.rec(key)
    from labcalc import materials as M
    q = (M._ranges().get("quellen") or {}).get(key)
    return dict(q) if isinstance(q, dict) else None


def _check(states: list[str]) -> str:
    if not states:
        return "none"
    if all(s == "unchecked" for s in states):
        return "unchecked"
    if any(s == "unchecked" for s in states):
        return "mixed"
    return "partial" if any(s == "partial" for s in states) else "no_record"


def _st(sid: str, txt: str, keys, basis: str, software: bool = False, **extra) -> dict:
    keys = list(dict.fromkeys(k for k in keys or [] if k))
    states = [status_of(_rec(k)) for k in keys]
    unsourced = None if keys else ("software" if software else "open")
    return {"id": sid, "text": txt, "keys": keys, "basis": basis if keys else "none", "software": bool(software),
            "unsourced": unsourced, "check": _check(states), **extra}


def _row(prefix: str, row: list, lang: str) -> dict:
    """Zeile aus ``kompendium_text.json``: [Kennung, DE, EN, Schlüssel, Kennzeichen]."""
    flag = row[4] if len(row) > 4 else None
    return _st(f"{prefix}.{row[0]}", row[1 + _i(lang)], _known(row[3]), "statement", software=flag == "sw")


_ABBR = (("z. B.", "z. B․"), ("e.g.", "e․g․"), ("i.e.", "i․e․"), ("bzw.", "bzw․"), ("ca.", "ca․"))
_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-ZÄÖÜΑ-Ωα-ωθεδγ0-9„“])")
_SHOUT = {"ZWISCHEN": "zwischen", "IN": "in", "BETWEEN": "between", "INSIDE": "inside"}


def _sentences(t: str) -> list[str]:
    t = re.sub(r"\b(ZWISCHEN|IN|BETWEEN|INSIDE)\b", lambda m: _SHOUT[m.group(1)], str(t or "").strip())
    for a, b in _ABBR:
        t = t.replace(a, b)
    out = [x.strip() for x in _SPLIT.split(t) if x.strip()]
    for a, b in _ABBR:
        out = [x.replace(b, a) for x in out]
    return out


def _paired(de: str, en: str, lang: str) -> list[str]:
    """Sätze in der gewählten Sprache; zerfallen DE und EN verschieden, bleibt der Text ein Block (gleiche Kennungen)."""
    a, b = _sentences(de), _sentences(en)
    if len(a) != len(b):
        return [" ".join(a if lang != "en" else b)]
    return a if lang != "en" else b


# Sätze, die ein Verfahren oder einen Befund beim Namen nennen, tragen die zugehörige Quelle selbst
_NAMED = (("Hall-Petch", ("hall1951", "petch1953")), ("Zener", ("zener1946",)), ("Roberts", ("roberts1953",)),
          ("Koistinen", ("koistinen1959",)), ("Jackson-Hunt", ("jackson1966",)), ("Ostwald", ("lifshitz1961",)),
          (r"Bain(?!it)", ("bain1924",)), ("Guinier", ("guinier1938", "preston1938")), ("ISO 945", ("iso945",)))   # Bain, nicht Bainit


def _cited(sid: str, sentence: str, entry_keys: list[str], **extra) -> dict:
    named = _known([k for w, ks in _NAMED if re.search(w, sentence) for k in ks])
    if named:
        return _st(sid, sentence, named, "statement", **extra)
    return _st(sid, sentence, entry_keys, "entry", **extra)


def _all_keys(statements) -> list[str]:
    return list(dict.fromkeys(k for s in statements for k in s["keys"]))


def statements_of(e: dict) -> list[dict]:
    """Alle Aussagen eines Eintrags, auch aus Steckbrief und Abschnitten."""
    out = list(e.get("facts") or []) + list(e.get("statements") or [])
    for s in e.get("sections") or []:
        out += s.get("statements") or []
    return out


def _stats(e: dict, refs: list[dict] | None = None) -> dict:
    st = statements_of(e)
    out = {"n": len(st), "cited": sum(1 for s in st if s["keys"]),
           "only_unchecked": sum(1 for s in st if s["check"] == "unchecked"),
           "open": sum(1 for s in st if s["unsourced"] == "open"),
           "software": sum(1 for s in st if s["unsourced"] == "software")}
    if refs is not None:
        out["sources"] = len(refs)
        out["sources_unchecked"] = sum(1 for q in refs if q["status"] == "unchecked")
        out["sources_partial"] = sum(1 for q in refs if q["status"] == "partial")
    return out


# ----------------------------------------------------------------------------- Einträge: Werkzeuge
def _sections(tool: str, lang: str) -> list[dict]:
    tx = text()["sections"].get(tool) or {}
    spec = VW.S_CAT if tool == "struktur" else (VW.V.get(tool) or {})
    out = []
    for vid in spec:
        st = [_row(f"tool:{tool}#{vid}", r, lang) for r in tx.get(vid) or []]
        out.append({"id": f"tool:{tool}#{vid}", "view": vid, "statements": st, "keys": _all_keys(st),
                    "title": view_title(tool, vid, lang) if vid != "_" else tool_name(tool, lang)})
    return out


def _tool_entry(tool: str, lang: str) -> dict:
    de = lang != "en"
    secs = _sections(tool, lang)
    st = [_row("tool:" + tool, r, lang) for r in text()["notes"].get(tool) or []]
    if tool == "gitter":
        from . import gitter as GT
        st.append(_st("tool:gitter.solute-list", ("Hinterlegte Fremdatome: " if de else "Available solutes: ") + ", ".join(GT.solute_list()) + ".",
                      [], "none", software=True))
    keys = _all_keys(st + [x for s in secs for x in s["statements"]])
    acts = [{"id": "ex:" + x["id"], "label": x["de" if de else "en"]} for x in (data()["examples"].get(tool) or [])]
    g = group_of(tool)
    return {"id": "tool:" + tool, "kind": "tool", "tool": tool, "title": tool_name(tool, lang), "short": tool_desc(tool, lang),
            "group": (g["de"] if de else g["en"]) if g else "", "statements": st, "sections": secs, "keys": keys,
            "actions": [{"id": "open:" + tool, "label": ("Werkzeug öffnen" if de else "Open the tool")}] + acts}


# ----------------------------------------------------------------------------- Einträge: Mechanismen, Atlas, Themen
@lru_cache(maxsize=4)
def _mech_entries(lang: str) -> tuple:
    from . import gefuege as GF
    de = lang != "en"
    out = []
    for mid, m in GF.MECHANISMS.items():
        caps = {lg: list(dict.fromkeys(f["caption"] for f in GF.mechanism(mid, lg, 1, 12)["frames"] if f.get("caption"))) for lg in ("de", "en")}
        keys = _known(m["refs"])
        st = []
        if len(caps["de"]) == len(caps["en"]):
            for n, (a, b) in enumerate(zip(caps["de"], caps["en"]), 1):
                st += [_cited(f"mech:{mid}.{n}.{k}", x, keys, step=n) for k, x in enumerate(_paired(a, b, lang), 1)]
        else:
            st = [_cited(f"mech:{mid}.{n}.1", x, keys, step=n) for n, x in enumerate(caps[lang if lang == "en" else "de"], 1)]
        out.append({"id": "mech:" + mid, "kind": "mech", "tool": "struktur", "mech": mid, "title": m["name"][0 if de else 1],
                    "short": st[0]["text"] if st else "", "statements": st, "sections": [], "keys": _all_keys(st) or keys,
                    "group": "Mechanismen" if de else "Mechanisms", "media": "mech",
                    "note": ("Schematische Bildfolge: Geometrie und Abläufe nach den Quellen angedeutet, nicht berechnet." if de else
                             "Schematic sequence: geometry and course indicated after the sources, not computed.")})
    return tuple(out)


FAMILY = {"stahl": ("Stahl", "Steel"), "gusseisen": ("Gusseisen", "Cast iron"), "aluminium": ("Aluminium", "Aluminium"),
          "kupfer": ("Kupfer", "Copper"), "titan": ("Titan", "Titanium"), "eutektisch": ("Eutektika", "Eutectics"),
          "allgemein": ("Allgemein", "General")}


def _atlas_entries(lang: str) -> list[dict]:
    from . import gefuege as GF
    de = lang != "en"
    i = _i(lang)
    out = []
    for cid, c in GF.CONSTITUENTS.items():
        keys = _known(c["refs"])
        pid = "atlas:" + cid
        facts = [_st(pid + ".formed", c["conditions"][i], keys, "entry", label="Entsteht durch" if de else "Formed by"),
                 _st(pid + ".etchant", c["etch"][i], keys, "entry", label="Ätzung" if de else "Etchant")]
        if c.get("hv") and len(c["hv"]) == 2:
            facts.append(_st(pid + ".hardness", f"{c['hv'][0]:g}–{c['hv'][1]:g} HV", keys, "entry", label="Härte (typisch)" if de else "Hardness (typical)"))
        if c.get("scale"):
            facts.append(_st(pid + ".field", str(c["scale"]), [], "none", software=True, label="Bildausschnitt" if de else "Field of view"))
        st = [_cited(f"{pid}.{n}", x, keys) for n, x in enumerate(_paired(c["what"][0], c["what"][1], lang), 1)]
        fam = FAMILY.get(c["family"], (c["family"], c["family"]))[i]
        out.append({"id": pid, "kind": "atlas", "tool": "struktur", "gef": cid, "title": c["name"][i], "short": c["conditions"][i],
                    "statements": st, "facts": facts, "sections": [], "keys": _all_keys(st + facts),
                    "group": ("Gefügeatlas · " if de else "Atlas · ") + fam, "media": "atlas",
                    "note": ("Skizze nach Lehrbüchern und Atlanten, schematisch und nicht massstäblich." if de else
                             "Sketch after textbooks and atlases, schematic and not to scale.")})
    return out


def _topic_entries(lang: str) -> list[dict]:
    i = _i(lang)
    out = []
    for tid, m in text()["topic_meta"].items():
        st = [_row("topic:" + tid, r, lang) for r in text()["topics"][tid]]
        out.append({"id": "topic:" + tid, "kind": "topic", "tool": m.get("tool") or "", "title": m["title"][i], "short": m["short"][i],
                    "statements": st, "sections": [], "keys": _all_keys(st), "terms": m.get("terms", ""),
                    "group": "Themen" if i == 0 else "Topics"})
    return out


# ----------------------------------------------------------------------------- Einträge: Werkstoffe
_UNIT = {"g/cm^3": "g/cm³", "µm/(m*K)": "10⁻⁶/K", "W/(m*K)": "W/(m·K)", "J/(kg*K)": "J/(kg·K)", "µOhm*cm": "µΩ·cm",
         "MPa*m^0.5": "MPa·√m", "1": ""}


def _num(x, lang: str) -> str:
    s = f"{x:.4g}".replace("e+0", "e").replace("e-0", "e-")
    return s if lang == "en" else s.replace(".", ",")


_SAME: dict[str, str] | None = None


def _same_source(key: str) -> str:
    """Die Normen stehen in ``ranges.json`` und im Quellenregister unter zwei Schlüsseln; beide zählen als eine Quelle."""
    global _SAME
    if _SAME is None:
        from labcalc import materials as M
        from labcalc import sources as LS
        known = {(str(r.get("title")), str(r.get("year"))): k for reg in (LS.REFS, RF.REFS) for k, r in reg.items()}
        _SAME = {}
        for k, r in (M._ranges().get("quellen") or {}).items():
            twin = known.get((str(r.get("title")), str(r.get("year")))) if isinstance(r, dict) else None
            if twin and twin != k:
                _SAME[k] = twin
    return _SAME.get(key, key)


def _source_key(key, rec: dict | None) -> str:
    """Registerschlüssel oder, bei einer frei formulierten Quellenangabe, ein stabiler Schlüssel aus ihrem Text."""
    if key and _rec(key) is not None:
        return _same_source(key)
    return "q:" + hashlib.sha1(str((rec or {}).get("title") or key or "").encode("utf-8")).hexdigest()[:10]


def _value_row(r: dict, prop: str, lang: str, local: dict) -> dict | None:
    """Ein Kennwert als Aussage: Wert, Einheit, Wertart, Spanne, je eigene Quelle und Prüfstatus."""
    from labcalc import materials as M
    from . import select as SL
    de = lang != "en"
    kind, unit, lde, len_ = M.PROPS.get(prop, ("", "", prop, prop))
    label = lde if de else len_
    shown = _UNIT.get(unit, unit)
    sid = f"material:{r['id']}.{prop}"
    try:
        v = M.value(r, prop)
    except M.MatError:
        v = None
    if v is None:
        rg = M.range_of(r, prop) if kind != "text" else None
        if not rg:
            return None
        lo, hi = SL.disp(rg["min_si"], prop), SL.disp(rg["max_si"], prop)
        rk = _source_key(rg.get("range_key"), rg.get("range_source"))
        local[rk] = rg.get("range_source") or {}
        rng = f"{_num(lo, lang)}–{_num(hi, lang)}" + (f" {shown}" if shown else "")
        st = _st(sid, f"{label}: {rng}", [rk], "data", prop=prop, label=label, value=None, unit=shown, shown=("nur Spanne" if de else "range only"),
                 range=[lo, hi], art="", value_keys=[], range_keys=[rk], value_status="none", range_status="unchecked", range_note=rg.get("note") or "")
        st["check"] = "unchecked"
        return st
    title = (v.get("source") or {}).get("title")
    no_src = not v.get("key") and (not title or title == "ohne Quellenangabe")
    vk = [] if no_src else [_source_key(v.get("key"), v.get("source"))]
    for k in vk:
        local[k] = v.get("source") or {}
    vstat = "unchecked" if v.get("nicht_geprueft") else (status_of(v.get("source")) if vk else "none")
    art = (M.ART.get(v.get("art") or "") or ("", ""))[_i(lang)]
    if v.get("si") is None:                              # Text, z. B. Kristallstruktur
        st = _st(sid, f"{label}: {v.get('text', '')}", vk, "data", prop=prop, label=label, value=None, unit="", shown=v.get("text", ""),
                 range=None, art=art, value_keys=vk, range_keys=[], value_status=vstat, range_status="none", range_note="")
        if vk:
            st["check"] = "unchecked" if vstat == "unchecked" else st["check"]
        return st
    val = SL.disp(v["si"], prop)
    lo, hi = SL.disp(v.get("min_si"), prop), SL.disp(v.get("max_si"), prop)
    rkeys, rstat = [], "none"
    if lo is not None and hi is not None:
        if v.get("range_own"):
            rkeys, rstat = list(vk), vstat
        elif v.get("range_key"):
            rk = _source_key(v.get("range_key"), v.get("range_source"))
            local[rk] = v.get("range_source") or {}
            rkeys, rstat = [rk], "unchecked"             # ranges.json: alle Spannen sind nicht am Original geprüft
    has_range = lo is not None and hi is not None
    body = _num(val, lang) + (f" {shown}" if shown else "")
    txt = f"{label}: {body}" + (f" ({'Spanne' if de else 'range'} {_num(lo, lang)}–{_num(hi, lang)})" if has_range else "")
    st = _st(sid, txt, list(dict.fromkeys(vk + rkeys)), "data", prop=prop, label=label, value=val, unit=shown, shown=body,
             range=[lo, hi] if has_range else None, art=art, value_keys=vk, range_keys=rkeys, value_status=vstat, range_status=rstat,
             range_note=v.get("range_note") or "", T=v.get("T") or "")
    if vk or rkeys:
        states = ([vstat] if vk else []) + ([rstat] if rkeys and not v.get("range_own") else [])
        st["check"] = _check(states)
    return st


def _material_group(r: dict, lang: str) -> tuple[str, str]:
    from labcalc import materials as M
    from . import select as SL
    de = lang != "en"
    cls = (M.CLASSES.get(r.get("klasse")) or ("", ""))[_i(lang)]
    return ("Werkstoffe · " if de else "Materials · ") + cls, SL.family_name(r.get("familie") or "", "de" if de else "en")


@lru_cache(maxsize=4)
def _material_entries(lang: str) -> tuple:
    from labcalc import materials as M
    de = lang != "en"
    out = []
    for r in M.materials():
        if r.get("_teil") == "materials_mp":
            continue
        local: dict = {}
        props = list(M.props_of(r))
        props += [p for p, x in M.PROPS.items() if p not in props and x[0] != "text" and M.range_of(r, p)]
        st = [x for x in (_value_row(r, p, lang, local) for p in props) if x]
        s = M.summary(r, lang)
        group, sub = _material_group(r, lang)
        cls = (M.CLASSES.get(r.get("klasse")) or ("", ""))[_i(lang)]
        ng = (r.get("nicht_geprueft_en") if not de else None) or r.get("nicht_geprueft") or r.get("werte_hinweis") or ""
        aliases = list(r.get("aliase") or [])
        out.append({"id": "material:" + r["id"], "kind": "material", "material": r["id"], "tool": "auswahl", "title": s["name"],
                    "short": " · ".join(x for x in (sub, cls) if x), "group": group, "sub": sub, "aliases": aliases,
                    "statements": st, "sections": [], "keys": _all_keys(st), "local": local, "data_note": ng,
                    "hint": r.get("hinweis") or "",
                    "terms": " ".join([r.get("name") or "", r.get("name_en") or "", r["id"], r.get("familie") or "", r.get("kategorie") or ""] + aliases)})
    return tuple(out)


def _struct_links(mid: str) -> tuple[list[str], list[str]]:
    """Atlas- und Mechanismus-Einträge aus Lieferzustand und Regel des Strukturdatensatzes. Bewusst eng: es steht nur,
    was zum Zustand gehört (die Ausscheidungsfolge im Kompendium ist die von Al–Cu, sie gilt nicht für 6xxx und 7xxx)."""
    from . import struktur as SK
    try:
        r = SK.record(mid)
    except SK.StructError:
        return [], []
    rule = r.get("regel")
    z = str(r.get("zustand") or "").upper()
    c = float((r.get("zus") or {}).get("C", 0) or 0)
    atlas: list[str] = []
    mech: list[str] = []
    if rule == "stahl":
        if z.startswith("QT"):
            atlas, mech = ["martensit_angelassen"], ["austenitisieren", "martensit", "bain", "anlassen"]
        elif 0.02 <= c <= 0.77:
            atlas, mech = ["ferrit_perlit"], ["perlit"]
    elif rule == "edelstahl-austenit":
        atlas = ["austenit"]
    elif rule == "gusseisen":
        atlas = [{"lamellen": "gjl", "kugel": "gjs"}.get(r.get("graphit"), "")]
        mech = ["erstarrung"]
    elif rule == "al-2xxx":
        atlas = ["al_gp"] if z.startswith(("T3", "T4")) else ["al_theta_strich"] if z.startswith("T6") else []
        mech = ["ausscheidung"]
    elif rule in SK.RX_RULES:
        cold = r.get("kaltverformt") if "kaltverformt" in r else z.startswith("H")
        if cold:
            atlas, mech = ["kaltverformt"], ["rekristallisation"]
        elif "kaltverformt" in r or z == "O":
            atlas, mech = ["rekristallisiert"], ["rekristallisation"]
    return [a for a in atlas if a], mech


def _phase_links(mid: str, lang: str) -> list[dict]:
    """Phasen, deren Zelle die Struktur-Ansicht für diesen Werkstoff zeigt; reine Vergleichszellen zählen nicht."""
    from . import cryst as C
    from . import struktur as SK
    try:
        out = SK.build(mid, 20.0, lang, 1, 3)
    except (SK.StructError, KeyError, ValueError):
        return []
    builtin = {p["id"] for p in C.builtin_phases()}
    seen, res = set(), []
    for p in out.get("panels") or []:
        ph = p.get("phase")
        if not ph or ph["id"] in seen or re.search("vergleich|comparison", str(p.get("caption") or ""), re.I):
            continue
        seen.add(ph["id"])
        res.append({"id": ph["id"], "name": ph.get("name") or ph["id"], "formula": ph.get("formula") or "",
                    "keys": _known(p.get("q") or []), "builtin": ph["id"] in builtin})
    return res


def _links(mid: str, lang: str) -> dict:
    from . import gefuege as GF
    atlas, mech = _struct_links(mid)
    i = _i(lang)
    return {"phases": _phase_links(mid, lang),
            "atlas": [{"id": "atlas:" + a, "title": GF.CONSTITUENTS[a]["name"][i]} for a in atlas if a in GF.CONSTITUENTS],
            "mech": [{"id": "mech:" + m, "title": GF.MECHANISMS[m]["name"][i]} for m in mech if m in GF.MECHANISMS]}


@lru_cache(maxsize=512)
def _designation(mid: str, lang: str) -> dict | None:
    """Abschnitt „Bezeichnung“: die Teile der Bezeichnung nach ihrer Norm, je Bezeichnung eine Aussage mit Quellen."""
    try:
        from labcalc import designation as DG
        d = DG.decode_material(mid, lang)
        found, quals = _decoded(mid, lang)
    except Exception:  # noqa: BLE001 – der Eintrag funktioniert auch ohne Entschlüsselung
        return None
    if not found:
        return None
    de = lang != "en"
    pid = f"material:{mid}#{BEZ}"
    st = []
    for slug, f in found.items():
        keys = _known(f.get("refs"))
        sid = f"{pid}.{slug}"
        st.append(_st(sid, f.get("summary") or f.get("code") or "", keys, "data", code=f.get("code") or "", system=f.get("system") or "",
                      parts=[{"code": p.get("code", ""), "meaning": p.get("meaning", "")} for p in f.get("parts") or []]))
        comp = f.get("composition") or {}
        if comp:
            cv = lambda v: "–".join(str(x) for x in v) if isinstance(v, (list, tuple)) else str(v)
            txt = ("Zusammensetzung nach Norm [Gew.-%]: " if de else "Composition per standard [wt%]: ") + " · ".join(f"{k} {cv(v)}" for k, v in comp.items())
            st.append(_st(f"{sid}.composition", txt, keys, "data"))
    for slug, q in quals.items():
        st.append(_st(f"{pid}.q-{slug}", f"{q.get('code', '')}: {q.get('meaning', '')}", [], "none"))
    return {"id": pid, "view": BEZ, "title": "Bezeichnung" if de else "Designation", "statements": st, "keys": _all_keys(st),
            "summary": d.get("summary") or ""}


def _code_slug(code: str) -> str:
    s = unicodedata.normalize("NFKD", str(code or "")).lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or hashlib.sha1(str(code).encode("utf-8")).hexdigest()[:8]


def _decoded_one(r: dict, lang: str) -> tuple[dict, dict]:
    from labcalc import designation as DG
    found, quals = {}, {}
    for tx in [r.get("name"), r.get("name_en"), *(r.get("aliase") or [])]:
        if not tx:
            continue
        d = DG.decode(tx, lang, hint=r.get("familie"))
        for f in d.get("found") or []:
            found.setdefault(_code_slug(f.get("code")), f)
        for q in d.get("qualifiers") or []:
            quals.setdefault(_code_slug(q.get("code")), q)
    return found, quals


def _decoded(mid: str, lang: str) -> tuple[dict, dict]:
    """Bezeichnungen aus Name, englischem Name und Aliasen, nach Code gekennzeichnet. Es bleibt, was in beiden Sprachen
    erkannt wird: eine Aussage hat in DE und EN dieselbe Kennung, damit ein Verweis darauf in beiden Sprachen gilt."""
    from labcalc import materials as M
    r = M.find(mid)
    other = "de" if lang == "en" else "en"
    fa, qa = _decoded_one(r, lang)
    fb, qb = _decoded_one(r, other)
    return {k: v for k, v in fa.items() if k in fb}, {k: v for k, v in qa.items() if k in qb}


# ----------------------------------------------------------------------------- Zugriff
@lru_cache(maxsize=4)
def _entries(lang: str) -> tuple:
    from . import tools as T
    out = [_tool_entry(t, lang) for t in T.TOOLS] + _topic_entries(lang) + list(_mech_entries(lang)) + _atlas_entries(lang) + list(_material_entries(lang))
    return tuple(out)


def entries(lang: str = "de") -> list[dict]:
    return [dict(e) for e in _entries(lang)]


def _find(eid: str, lang: str) -> dict:
    base = eid.split("#", 1)[0]
    for e in _entries(lang):
        if e["id"] == base:
            return e
    raise LookupError(f"Kompendiumseintrag „{eid}“ unbekannt")


NG_EN = "Details not checked against the original"


def ref_text(rec: dict, lang: str) -> str:
    """Quelle als Text; der Prüfvermerk folgt der Sprache."""
    import labcite
    text = labcite.text(rec, lang)
    return text.replace(RF.NG, NG_EN) if lang == "en" else text


def _ref_item(key: str, rec: dict, lang: str) -> dict:
    import labcite
    st = status_of(rec)
    return {"key": key, "short": labcite.short(rec, lang), "text": ref_text(rec, lang), "status": st, "unchecked": st == "unchecked"}


def _listing(keys, local: dict, lang: str) -> list[dict]:
    out = []
    for k in dict.fromkeys(keys):
        rec = _rec(k) or local.get(k)
        if rec:
            out.append(_ref_item(k, rec, lang))
    return out


def entry(eid: str, lang: str = "de") -> dict:
    """Ein Eintrag mit ausgeschriebenen Quellen, Prüfstatus je Quelle und Bilanz der Aussagen."""
    e = dict(_find(str(eid or ""), lang))
    local = e.pop("local", None) or {}
    if e["kind"] == "material":
        mid = e["material"]
        dec = _designation(mid, lang)
        e["sections"] = [dec] if dec else []
        e["links"] = _links(mid, lang)
        e["struktur"] = bool(e["links"]["phases"] or e["links"]["atlas"] or e["links"]["mech"])
        try:
            from . import struktur as SK
            SK.record(mid)
            e["struktur"] = True
        except SK.StructError:
            pass
    keys = _all_keys(statements_of(e)) + list(e.get("keys") or [])
    if e["kind"] == "material":
        keys += [k for p in e["links"]["phases"] for k in p["keys"]]
    e["refs"] = _listing(keys, local, lang)
    e["keys"] = [q["key"] for q in e["refs"]]
    e["stats"] = _stats(e, e["refs"])
    e["anchor"] = str(eid) if "#" in str(eid) else ""
    return e


def entry_of_statement(sid: str) -> str:
    """Eintrags-Kennung einer Aussagen-Kennung."""
    s = str(sid or "")
    return s.split("#", 1)[0] if "#" in s else s.split(".", 1)[0]


def statement(sid: str, lang: str = "de") -> dict:
    """Eine Aussage über ihre stabile Kennung, mit Eintrag und ausgeschriebenen Quellen (Verweisziel für Pins)."""
    e = entry(entry_of_statement(sid), lang)
    for s in statements_of(e):
        if s["id"] == sid:
            have = {q["key"]: q for q in e["refs"]}
            return {**s, "entry": e["id"], "entry_title": e["title"], "refs": [have[k] for k in s["keys"] if k in have]}
    raise LookupError(f"Aussage „{sid}“ unbekannt")


def text_of(e: dict) -> str:
    """Aller Text eines Eintrags (Suche, Tests). Die Zahlenwerte der Werkstoffe gehören nicht in den Suchtext."""
    parts = [e.get("title", ""), e.get("short", ""), e.get("note", ""), e.get("terms", "")]
    for s in e.get("facts") or []:
        parts += [s.get("label", ""), s["text"]]
    parts += [s["text"] for s in e.get("statements") or [] if "prop" not in s]
    for sec in e.get("sections") or []:
        parts.append(sec["title"])
        parts += [s["text"] for s in sec.get("statements") or []]
    return " ".join(p for p in parts if p)


@lru_cache(maxsize=4)
def _index(lang: str) -> tuple:
    def n_open(e: dict) -> int:                     # die Bezeichnung eines Werkstoffs kommt erst mit ``entry`` dazu
        sec = _designation(e["material"], lang) if e["kind"] == "material" else None
        return _stats(e)["open"] + sum(1 for s in (sec or {}).get("statements") or [] if s["unsourced"] == "open")
    return tuple({"id": e["id"], "kind": e["kind"], "title": e["title"], "short": e.get("short", ""), "group": e.get("group", ""),
                  "sub": e.get("sub", ""), "open": n_open(e),
                  "sections": [{"id": s["id"], "title": s["title"]} for s in e.get("sections") or []]} for e in _entries(lang))


def index(lang: str = "de") -> list[dict]:
    """Liste für das Kompendiumsfenster: Einträge ohne Text, nach Gruppen."""
    return [dict(x) for x in _index(lang)]


def balance(lang: str = "de") -> dict:
    """Bilanz über alle Aussagen und Quellen (Prüfungen, Bericht an die Quellenprüfung)."""
    out = {"entries": 0, "statements": 0, "cited": 0, "open": 0, "software": 0, "only_unchecked": 0, "entry_level": 0, "sources": {}}
    for x in _entries(lang):
        e = entry(x["id"], lang)
        out["entries"] += 1
        for s in statements_of(e):
            out["statements"] += 1
            out["cited"] += bool(s["keys"])
            out["open"] += s["unsourced"] == "open"
            out["software"] += s["unsourced"] == "software"
            out["only_unchecked"] += s["check"] == "unchecked"
            out["entry_level"] += s["basis"] == "entry"
        for q in e["refs"]:
            out["sources"][q["key"]] = q["status"]
    src = out.pop("sources")
    out["sources"] = len(src)
    out["sources_unchecked"] = sum(1 for v in src.values() if v == "unchecked")
    out["sources_partial"] = sum(1 for v in src.values() if v == "partial")
    out["sources_no_record"] = sum(1 for v in src.values() if v == "no_record")
    return out
