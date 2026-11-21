"""Quellen je Ansicht; die Texte stehen Aussage für Aussage im Kompendium (werk/kompendium.py).

``V`` und ``S_CAT`` halten je Ansicht die Quellenschlüssel.
``annotate(tool, out, req, lang)`` hängt an jedes Werkzeugergebnis ``views_info`` an: Ansicht → {keys, entry}, ohne
Erklärtext; ``entry`` ist der Kompendiumseintrag, auf den der eine Verweis der Ansicht zeigt.
``keys`` sind die Quellen genau dieser Ansicht (statisch je Ansicht plus die Quellen, die das Ergebnis selbst nennt,
z. B. das gewählte Phasendiagramm oder die Kristallstruktur). Struktur-Panels bekommen zusätzlich ``cat`` (Art der
Ansicht) und ``refs_keys`` (Quellen des Panels); Zwischenbilder einer Wärmebehandlung behalten ihre eigenen Quellen.
Fehlt eine Quelle in ``out["refs"]``, wird sie ergänzt, damit die Seite jede genannte Quelle ausschreiben kann.
"""
from __future__ import annotations

from . import refs as RF

# Quellen je Ansicht (Abbildung im Bericht, Quellenliste des Werkzeugs); der Text steht je Aussage in data/kompendium_text.json.
V = {
    "auswahl": {"_": (["ashby"],)},
    "karten": {"_": ([],)},
    "kristall": {"lines": (["cullity", "itc_c"],), "cell": (["itc_c"],)},
    "gitter": {"3d": (["kittel", "callister"],), "cell": (["itc_c", "kittel"],), "slice": (["kittel"],)},
    "xrd": {"pattern": (["cullity"],), "wh": (["williamson1953", "scherrer1918"],), "nr": (["nelson1945"],)},
    "phasen": {"diagram": ([],), "cooling": (["porter"],)},
    "stahl": {"_": (["en1011_2", "andrews1965"],)},
    "laminat": {"s1": (["daniel2006", "jones1999"],), "s2": (["daniel2006", "jones1999"],), "t12": (["daniel2006", "jones1999"],)},
    "ermuedung": {"sn": (["basquin1910", "astme739"],), "haigh": (["dowling"],), "rf": (["astme1049", "miner1945"],)},
    "weibull": {"_": (["weibull1951", "astmc1239"],)},
    "bruch": {"_": (["astme399", "anderson"],)},
    "haerte": {"ind": (["iso6507", "iso6506"],), "hp": (["hall1951", "petch1953", "astme112"],)},
    "korrosion": {"_": (["stern1957", "astmg102"],)},
    "kriechen": {"lmp": (["larsonmiller1952"],), "norton": (["norton1929", "dowling"],)},
}

# Struktur: Art der Ansicht nach Panel-ID
S_CAT = {
    "gefuege": ([],),
    "gitter": ([],),
    "zelle": (["cordero2008"],),
    "polymer": (["strobl2007"],),
    "zustand": ([],),
    "weg": (["hollomonjaffe1945"],),
    "mech": ([],),
    "atlas": ([],),
}
POLY = ("kette", "knaeuel", "morphologie", "netzwerk", "schichten", "verbund")


def panel_cat(pid: str) -> str:
    pid = str(pid or "")
    if pid.startswith("zelle:"):
        return "zelle"
    if pid in ("gefuege", "gitter", "weg", "mech", "atlas"):
        return pid
    if pid in POLY:
        return "polymer"
    return "zustand"


def _known(keys) -> list[str]:
    return [k for k in dict.fromkeys(keys or []) if k and RF.known(k)]


def _ent(tool: str, vid: str, keys, req: dict | None = None) -> dict:
    """Ansicht im Ergebnis: nur ihre Quellen und der Verweis in den Kompendiumseintrag (Runde V: der Erklärtext steht
    im Kompendium, nicht mehr im Werkzeug)."""
    from . import kompendium as KP
    return {"keys": _known(keys), "entry": KP.link(tool, vid, req if vid in ("mech", "atlas") else None)}


def _panel_keys(p: dict, out: dict) -> list[str]:
    cat = panel_cat(p.get("id"))
    keys = list(p.get("refs") or p.get("refs_keys") or [])
    q = list(p.get("q") or [])
    if q:
        keys += q + (["grazulis2012"] if any(str(k).startswith("cod") for k in q) else [])
    if not keys:                                   # Panel ohne eigene Quellen: Quellen des Werkstoffs
        keys = list(out.get("refs_keys") or [])
    return _known(list(S_CAT[cat][0]) + keys)


def annotate(tool: str, out, req: dict, lang: str = "de"):
    """``views_info`` (und bei Struktur ``cat``/``refs_keys`` je Panel) an ein Ergebnis hängen."""
    if not isinstance(out, dict) or out.get("error"):
        return out
    all_keys = [r.get("key") for r in out.get("refs") or [] if isinstance(r, dict)]
    info = {}
    if tool == "struktur":
        panels = list(out.get("panels") or [])
        for f in out.get("frames") or []:
            panels += f.get("panels") or []
            f["refs_keys"] = _known(f.get("refs_keys") or [])
        for p in panels:
            p["cat"] = panel_cat(p.get("id"))
            p["refs_keys"] = _panel_keys(p, out)
        cats = {p["cat"] for p in panels}
        if out.get("frames") and out.get("profile"):
            cats.add("weg")
        mode = (req or {}).get("mode")
        if mode in ("mech", "atlas"):
            cats.add(mode)
        for c in cats:
            ks = list(S_CAT[c][0])
            if c in ("weg", "mech", "atlas"):
                ks += out.get("refs_keys") or []
            info[c] = _ent(tool, c, ks, req)
        extra = [k for p in panels for k in p["refs_keys"]]
    else:
        spec = V.get(tool) or {}
        ent = {}
        for vid, sp in spec.items():
            ks = list(sp[0])
            if tool == "phasen" and vid == "diagram":
                ks += [k for k in all_keys if k not in ("porter",)]
            if tool in ("kristall", "gitter"):
                ks += [k for k in all_keys if k not in ks]         # Strukturquelle der Phase gehört zu jeder Ansicht
            ent[vid] = _ent(tool, vid, ks)
        info = ent
        extra = [k for e in ent.values() for k in e["keys"]]
    missing = [k for k in dict.fromkeys(extra) if k not in all_keys]
    if missing:
        out["refs"] = list(out.get("refs") or []) + RF.listing(missing, lang)
    out["views_info"] = info
    return out


def figure_keys(tool: str, view: str, res: dict | None = None) -> list[str]:
    """Quellen einer Ansicht für die Abbildung im Bericht (ohne Ergebnis: nur die festen)."""
    if tool == "struktur":
        return _known(S_CAT.get(panel_cat(view), ([],))[0])
    sp = (V.get(tool) or {}).get(view) or (V.get(tool) or {}).get("_")
    return _known(sp[0]) if sp else []
