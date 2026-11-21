"""Eine Suche über das ganze Modul (Runde V): Werkzeuge, Ansichten und Betriebsarten, Werkstoffe (Namen, Aliase,
Bezeichnungen), Zustandsdiagramme, Phasen und Kompendiumseinträge. ``search(q, lang)`` liefert die Treffer nach Art
gruppiert; jeder Treffer trägt ``act`` (was die Seite beim Öffnen einstellt)."""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

from . import kompendium as KP

KINDS = ("tool", "material", "entry", "system", "phase")
LABEL = {"tool": ("Werkzeuge und Ansichten", "Tools and views"), "material": ("Werkstoffe", "Materials"),
         "entry": ("Kompendium", "Compendium"), "system": ("Zustandsdiagramme", "Phase diagrams"),
         "phase": ("Kristallphasen", "Crystal phases")}


def norm(s: str) -> str:
    s = str(s or "").lower().replace("ß", "ss").replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")  # „Härte“ = „haerte“
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9.]+", " ", s).strip()


def _item(kind: str, iid: str, title: str, sub: str, terms, act: dict) -> dict:
    words = norm(" ".join([title, sub] + [t for t in terms if t]))
    return {"kind": kind, "id": iid, "title": title, "sub": sub, "act": act, "_t": norm(title), "_w": words,
            "_c": words.replace(" ", "").replace(".", "")}


@lru_cache(maxsize=4)
def _index(lang: str) -> tuple:
    from labcalc import materials as M
    from . import cryst as C
    from . import phasediag as PD
    from . import select as SL
    from . import struktur as SK
    de = lang != "en"
    out = []
    other = "en" if de else "de"
    for g in KP.groups(lang):
        for t in g["tools"]:
            out.append(_item("tool", "tool:" + t, KP.tool_name(t, lang), f"{g['label']} · {KP.tool_desc(t, lang)}",
                             [KP.tool_name(t, other), KP.tool_desc(t, other), t], {"tool": t}))
            spec = KP.data()["views"].get(t) or {}
            if t != "struktur":
                for vid, names in spec.items():
                    out.append(_item("tool", f"view:{t}:{vid}", f"{KP.tool_name(t, lang)} · {names[0 if de else 1]}", g["label"],
                                     [names[1 if de else 0]], {"tool": t, "view": vid}))
    for mode, de_, en_ in (("T", "Temperatur", "Temperature"), ("temper", "Wärmebehandlung", "Heat treatment")):
        out.append(_item("tool", "mode:struktur:" + mode, f"{KP.tool_name('struktur', lang)} · {de_ if de else en_}", KP.groups(lang)[1]["label"],
                         [en_ if de else de_, "Anlassen Härten Auslagern tempering quench ageing" if mode == "temper" else "Heizen heating"],
                         {"tool": "struktur", "mode": mode}))
    smat = {m["id"] for m in SK.materials(lang)}
    for r in M.materials():
        if r.get("_teil") == "materials_mp":
            continue
        s = M.summary(r, lang)
        terms = [r.get("name") or "", r.get("name_en") or "", r.get("id") or "", r.get("familie") or "", r.get("kategorie") or ""] + list(r.get("aliase") or [])
        out.append(_item("material", "mat:" + r["id"], s["name"], " · ".join(x for x in (SL.family_name(r.get("familie") or "", "de" if de else "en"), (M.CLASSES.get(r.get("klasse")) or ("", ""))[0 if de else 1]) if x),
                         terms, {"material": r["id"], "name": s["name"], "struktur": r["id"] in smat, "kp": "material:" + r["id"]}))
    for e in KP.entries(lang):
        out.append(_item("entry", e["id"], e["title"], e.get("group") or "", [KP.text_of(e)], {"entry": e["id"]}))
        for s in e.get("sections") or []:
            out.append(_item("entry", s["id"], f"{e['title']} · {s['title']}", e.get("group") or "", [x["text"] for x in s.get("statements") or []], {"entry": s["id"]}))
    for s in PD.systems(lang):
        out.append(_item("system", "sys:" + s["id"], s["name"], s.get("group") or "", [s["id"].replace("-", " ")], {"tool": "phasen", "system": s["id"]}))
    for p in C.builtin_phases():
        nm = (p.get("name_en") if not de and p.get("name_en") else p.get("name")) or p["id"]
        out.append(_item("phase", "phase:" + p["id"], nm, p.get("formula", ""), [p.get("name", ""), p.get("name_en", ""), p["id"]],
                         {"tool": "kristall", "phase": p["id"]}))
    return tuple(out)


def _score(it: dict, q: str, toks: list[str], qc: str) -> int:
    t, w = it["_t"], it["_w"]
    if t == q:
        return 100
    words = w.split()
    if not all(any(x.startswith(k) for x in words) or (len(k) >= 3 and k in w) for k in toks):
        return 20 if len(qc) >= 3 and qc in it["_c"] else 0
    s = 40
    if t.startswith(q):
        s = 80
    elif all(any(x.startswith(k) for x in t.split()) for k in toks):
        s = 60
    return s


def search(q: str, lang: str = "de", limit: int = 8, kinds=None) -> dict:
    qn = norm(q)
    toks = qn.split()
    if not toks:
        return {"q": q, "groups": [], "n": 0}
    qc = qn.replace(" ", "").replace(".", "")
    hits = []
    for it in _index(lang):
        if kinds and it["kind"] not in kinds:
            continue
        s = _score(it, qn, toks, qc)
        if s:
            hits.append((s, it))
    hits.sort(key=lambda h: (-h[0], len(h[1]["title"])))
    de = lang != "en"
    groups = []
    for k in KINDS:
        items = [{x: v for x, v in it.items() if not x.startswith("_")} | {"score": s} for s, it in hits if it["kind"] == k]
        if items:
            groups.append({"kind": k, "label": LABEL[k][0 if de else 1], "items": items[:limit], "more": max(0, len(items) - limit)})
    groups.sort(key=lambda g: -g["items"][0]["score"])
    return {"q": q, "groups": groups, "n": len(hits)}


def all_items(lang: str = "de") -> list[dict]:
    """Der ganze Suchindex ohne interne Felder (Tests)."""
    return [{x: v for x, v in it.items() if not x.startswith("_")} for it in _index(lang)]
