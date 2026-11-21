"""Infotafel: Inhalte des Kompendiums anheften, auf einer Fläche ordnen und mit ihren Quellen in einen Bericht geben.

Ein **Pin** hält fest, woher sein Inhalt stammt (``entry``, ``ref``, ``spec``), welche Quellen er trägt (``sources`` mit
Prüfstatus) und was er beim Anheften zeigte (``content`` je Sprache). Ändert sich das Kompendium später, bleibt der Pin
wie er war und ``state`` meldet „geändert seit dem Anheften“; übernommen wird die neue Fassung nur auf Wunsch (``renew``).

Eine **Tafel** ist ``{id, name, view, frames: [{id, name, x, y, w, h}], cards: [Pin + x, y, w, h, frame]}``; die Reihenfolge
der Rahmen ist die Reihenfolge der Abschnitte im Bericht, innerhalb eines Rahmens gilt die Leserichtung. Die Tafeln liegen
je Projekt in ``projects/<projekt>/env/werkstoffe/_infotafeln.json``, neben der Lage der Übersicht (``_board.json``).

Im Bericht trägt jede Aussage genau ihre eigenen Quellen. Aussagen ohne Quelle oder auf ungeprüften Quellen werden vor dem
Export aufgelistet (``plan``) und erscheinen, wenn sie bleiben, mit †. Das Programm behauptet für keine Quelle eine Prüfung.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import threading
import zlib
from datetime import datetime, timezone
from functools import lru_cache

import labcite
from labbundle import Bundle, booktabs, slugify
from labproject import EnvError, Environments, _read, _write

from . import bundle as B
from . import charts as CH
from . import kompendium as KP
from . import tools as T

FILE = "_infotafeln.json"
LANGS = ("de", "en")
MAX_DOC = 24 * 1024 * 1024
MAX_BOARDS = 40
MAX_CARDS = 600
MAX_FRAMES = 80
MAX_NOTE = 6000
MECH_FRAMES = 24
KINDS = ("entry", "section", "statement", "value", "figure", "compare")
_LOCK = threading.RLock()
_STMT = ("id", "text", "keys", "basis", "unsourced", "check", "label", "prop", "value", "unit", "shown", "range", "art",
         "value_keys", "range_keys", "value_status", "range_status", "T", "step", "code", "system", "parts")
FLAG_CHECK = ("unchecked", "mixed")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canon(o) -> str:
    return json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def flag_of(s: dict) -> str:
    """Warum eine Aussage vor dem Export gemeldet wird: ``open`` (keine Quelle), ``unchecked`` oder leer."""
    if s.get("unsourced") == "open":
        return "open"
    return "unchecked" if s.get("check") in FLAG_CHECK else ""


# ----------------------------------------------------------------------------- Inhalt eines Pins
def _stmt(s: dict) -> dict:
    return {k: s[k] for k in _STMT if k in s and s[k] not in (None, "", [])}


def _pack(o) -> str:
    return base64.b64encode(zlib.compress(_canon(o).encode("utf-8"), 6)).decode("ascii")


def _unpack(z: str):
    return json.loads(zlib.decompress(base64.b64decode(z)).decode("utf-8"))


def _sources(keys, eid: str = "") -> dict:
    """Quellen mit Datensatz, Prüfstatus und ausgeschriebener Angabe, damit ein Pin ohne das Register auskommt."""
    local = {}
    if eid:
        try:
            local = KP._find(eid, "de").get("local") or {}
        except LookupError:
            local = {}
    out = {}
    for k in dict.fromkeys(keys):
        rec = KP._rec(k) or local.get(k)
        if not rec:
            continue
        out[k] = {"rec": labcite.clean(rec), "status": KP.status_of(rec),
                  "text": {lg: KP.ref_text(rec, lg) for lg in LANGS}, "short": {lg: labcite.short(rec, lg) for lg in LANGS}}
    return out


def _blocks_of(e: dict) -> list[dict]:
    own = list(e.get("facts") or []) + list(e.get("statements") or [])
    out = [{"id": e["id"], "title": "", "statements": [_stmt(s) for s in own]}] if own else []
    for sec in e.get("sections") or []:
        st = [_stmt(s) for s in sec.get("statements") or []]
        if st:
            out.append({"id": sec["id"], "title": "" if sec.get("view") == "_" else sec["title"], "statements": st})
    return out


def _keys_of(blocks: list[dict]) -> list[str]:
    return list(dict.fromkeys(k for b in blocks for s in b["statements"] for k in s.get("keys") or []))


def _pin_entry(eid: str) -> tuple[dict, list[str]]:
    content = {}
    for lg in LANGS:
        e = KP.entry(eid, lg)
        content[lg] = {"title": e["title"], "sub": e.get("short", ""), "blocks": _blocks_of(e)}
    return content, _keys_of(content["de"]["blocks"])


def _pin_section(sid: str) -> tuple[dict, list[str]]:
    content = {}
    base = sid.split("#", 1)[0]
    for lg in LANGS:
        e = KP.entry(base, lg)
        sec = next((s for s in e.get("sections") or [] if s["id"] == sid), None)
        if sec is None:
            raise LookupError(f"Abschnitt „{sid}“ unbekannt")
        st = [_stmt(s) for s in sec.get("statements") or []]
        if not st:
            raise T.ToolError("Dieser Abschnitt enthält keine Aussagen")
        title = e["title"] if sec.get("view") == "_" else f"{e['title']} · {sec['title']}"
        content[lg] = {"title": title, "sub": "", "blocks": [{"id": sid, "title": "", "statements": st}]}
    return content, _keys_of(content["de"]["blocks"])


def _pin_statement(sid: str) -> tuple[dict, list[str]]:
    content = {}
    for lg in LANGS:
        s = KP.statement(sid, lg)
        content[lg] = {"title": s["entry_title"], "sub": s.get("label", ""),
                       "blocks": [{"id": sid, "title": "", "statements": [_stmt(s)]}]}
    return content, _keys_of(content["de"]["blocks"])


def _pin_compare(mids: list[str]) -> tuple[dict, list[str]]:
    """Kennwerte mehrerer Werkstoffe nebeneinander; jede Zelle ist eine Aussage mit eigener Quelle."""
    from labcalc import materials as M
    mids = list(dict.fromkeys(str(m) for m in mids))
    if len(mids) < 2:
        raise T.ToolError("Für einen Vergleich mindestens zwei Werkstoffe wählen")
    content, keys = {}, []
    for lg in LANGS:
        ents = [KP.entry("material:" + m, lg) for m in mids]
        vals = [{s["prop"]: s for s in e["statements"] if s.get("prop")} for e in ents]
        order = [p for p in M.PROPS if sum(p in v for v in vals) >= 2] or [p for p in M.PROPS if any(p in v for v in vals)]
        rows = []
        for p in order:
            cells = [_stmt(v[p]) if p in v else None for v in vals]
            first = next(c for c in cells if c)
            rows.append({"prop": p, "label": first.get("label", p), "cells": cells})
        content[lg] = {"title": ("Vergleich: " if lg == "de" else "Comparison: ") + ", ".join(e["title"] for e in ents), "sub": "",
                       "blocks": [], "table": {"columns": [{"id": e["material"], "name": e["title"]} for e in ents], "rows": rows}}
        if lg == "de":
            keys = list(dict.fromkeys(k for r in rows for c in r["cells"] if c for k in c.get("keys") or []))
    return content, keys


@lru_cache(maxsize=128)
def _figure_cached(spec_json: str, lang: str) -> str:
    return _canon(_figure(json.loads(spec_json), lang))


def _mech_keys(e: dict, caption: str) -> list[str]:
    """Quellen genau des Schritts, dessen Bildunterschrift das Bild zeigt; sonst die des Eintrags."""
    steps: dict[int, list[dict]] = {}
    for s in e.get("statements") or []:
        steps.setdefault(s.get("step"), []).append(s)
    for st in steps.values():
        if " ".join(x["text"] for x in st).strip() == str(caption or "").strip():
            return list(dict.fromkeys(k for x in st for k in x["keys"]))
    return list(e.get("keys") or [])


def _figure(spec: dict, lang: str) -> dict:
    de = lang != "en"
    ctx = T.Ctx()
    fig = spec.get("fig")
    if fig == "atlas":
        cid = str(spec.get("gef") or "")
        r = T.run("struktur", {"mode": "atlas", "gef": cid, "seed": 1, "lang": lang}, ctx)
        e = KP.entry("atlas:" + cid, lang)
        inf = r.get("info") or {}
        cap = (f"Gefüge {r['name']} (Skizze, schematisch und nicht massstäblich; typischer Bildausschnitt {inf.get('scale', '')})." if de else
               f"Microstructure {r['name']} (sketch, schematic and not to scale; typical field of view {inf.get('scale', '')}).")
        return {"fig": fig, "title": r["name"], "caption": cap, "keys": list(e["keys"]), "draw": _pack(r["panels"][0]), "check": _stat(e["keys"])}
    if fig == "mech":
        mid = str(spec.get("mech") or "")
        r = T.run("struktur", {"mode": "mech", "mech": mid, "seed": 1, "frames": MECH_FRAMES, "lang": lang}, ctx)
        k = max(0, min(int(spec.get("frame") or 0), len(r["frames"]) - 1))
        f = r["frames"][k]
        e = KP.entry("mech:" + mid, lang)
        keys = _mech_keys(e, f.get("caption"))
        cap = (f"{r['name']}, Bild {k + 1} von {len(r['frames'])} ({f.get('label', '')}): {f.get('caption', '')} Schematisch, nach den angegebenen Quellen." if de else
               f"{r['name']}, frame {k + 1} of {len(r['frames'])} ({f.get('label', '')}): {f.get('caption', '')} Schematic, after the sources given.")
        return {"fig": fig, "title": f"{r['name']} · {k + 1}/{len(r['frames'])}", "caption": cap, "keys": keys, "draw": _pack(f["panels"][0]),
                "frame": k, "check": _stat(keys)}
    if fig == "chart":
        req = dict(spec.get("req") or {})
        res = T.run("auswahl", {**req, "lang": lang}, ctx)
        res.pop("refs", None)
        view = {k: v for k, v in (spec.get("view") or {}).items() if k in ("sel", "fam", "groups")}
        lim = spec.get("limits")
        shown = _chart_shown(res, view, lim)
        keys = list(dict.fromkeys(q for p in shown for q in p.get("q") or []))
        if res.get("rank"):
            keys = ["ashby"] + keys
        states = [KP.status_of(KP._rec(k)) for k in keys if KP._rec(k)]
        if any(p.get("unchecked") for p in shown):
            states.append("unchecked")
        x, y = res["x"], res["y"]
        n_fam = len({p.get("familie") for p in shown})
        whom = (f"Umrisse von {n_fam} Familien aus {len(shown)} Werkstoffen" if de else f"outlines of {n_fam} families from {len(shown)} materials") if view.get("groups") \
            else (f"{len(shown)} Werkstoffe" if de else f"{len(shown)} materials")
        what = (f"{y['label']} über {x['label']}, {whom} im gezeigten Bereich, Werte aus der Werkstoffdatenbank" if de else
                f"{y['label']} versus {x['label']}, {whom} in the range shown, values from the materials database")
        return {"fig": fig, "title": f"{y['label']} / {x['label']}", "caption": ("Kennwertdiagramm: " if de else "Property chart: ") + what + ".",
                "keys": keys, "draw": _pack({"res": res, "view": view, "limits": lim}), "check": KP._check(states)}
    raise T.ToolError("Unbekannte Abbildung")


def _stat(keys) -> str:
    return KP._check([KP.status_of(KP._rec(k)) for k in keys if KP._rec(k)])


def _chart_shown(res: dict, view: dict, lim) -> list[dict]:
    """Die Werkstoffe, deren Werte das Bild zeigt: in der Familienansicht als Punkt oder als Teil eines Umrisses."""
    pts = [p for p in res["points"] if p.get("x") and p.get("y") and p["x"] > 0 and p["y"] > 0]
    if view.get("groups"):
        pts = [p for p in pts if not p.get("mp") and p.get("familie")]
    if isinstance(lim, (list, tuple)) and len(lim) == 4 and all(isinstance(v, (int, float)) for v in lim):
        x0, x1, y0, y1 = lim
        pts = [p for p in pts if x0 <= p["x"] <= x1 and y0 <= p["y"] <= y1]
    return pts


def _draw_figure(c: dict, lang: str):
    """Zeichnet eine Abbildung aus den beim Anheften gespeicherten Daten."""
    d = _unpack(c["draw"])
    if c["fig"] == "chart":
        f = CH.fig_ashby(d["res"], lang, view=d.get("view") or {})
        lim = d.get("limits")
        if isinstance(lim, list) and len(lim) == 4 and f.axes:
            f.axes[0].set_xlim(lim[0], lim[1])
            f.axes[0].set_ylim(lim[2], lim[3])
        return f
    return CH.fig_panel(d, lang)


def _thumb(c: dict, lang: str) -> str:
    import io
    import matplotlib.pyplot as plt
    f = _draw_figure(c, lang)
    try:
        buf = io.BytesIO()
        f.savefig(buf, format="png", dpi=46)
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    finally:
        plt.close(f)


def _clean_spec(spec) -> dict:
    if not isinstance(spec, dict) or spec.get("kind") not in KINDS:
        raise T.ToolError("Unbekannte Art von Pin")
    k = spec["kind"]
    if k in ("entry", "section", "statement", "value"):
        return {"kind": k, "id": str(spec.get("id") or "")}
    if k == "compare":
        return {"kind": k, "materials": [str(m) for m in spec.get("materials") or []][:12]}
    fig = spec.get("fig")
    if fig == "atlas":
        return {"kind": k, "fig": fig, "gef": str(spec.get("gef") or "")}
    if fig == "mech":
        return {"kind": k, "fig": fig, "mech": str(spec.get("mech") or ""), "frame": int(spec.get("frame") or 0)}
    if fig == "chart":
        lim = spec.get("limits")
        ok = isinstance(lim, (list, tuple)) and len(lim) == 4 and all(isinstance(v, (int, float)) for v in lim)
        return {"kind": k, "fig": fig, "req": dict(spec.get("req") or {}), "view": dict(spec.get("view") or {}), "limits": list(lim) if ok else None}
    raise T.ToolError("Unbekannte Abbildung")


def _fingerprint(pin: dict) -> str:
    body = {"content": pin["content"], "sources": {k: {"rec": v["rec"], "status": v["status"]} for k, v in pin["sources"].items()}}
    return hashlib.sha256(_canon(body).encode("utf-8")).hexdigest()[:24]


def make_pin(spec, pid: str | None = None, lang: str = "de", thumb: bool = True) -> dict:
    """Pin aus einer Angabe ``{kind, id | fig … | materials}``: Inhalt in beiden Sprachen, Quellen, Prüfstatus, Fingerabdruck."""
    spec = _clean_spec(spec)
    k = spec["kind"]
    eid, ref = "", spec.get("id", "")
    local_eids: list[str] = []
    if k == "entry":
        KP._find(ref, "de")
        eid = ref
        content, keys = _pin_entry(ref)
    elif k == "section":
        eid = ref.split("#", 1)[0]
        content, keys = _pin_section(ref)
    elif k in ("statement", "value"):
        eid = KP.entry_of_statement(ref)
        content, keys = _pin_statement(ref)
        if k == "value" and "prop" not in content["de"]["blocks"][0]["statements"][0]:
            raise T.ToolError("Diese Aussage ist kein Kennwert")
    elif k == "compare":
        content, keys = _pin_compare(spec["materials"])
        local_eids = ["material:" + m for m in spec["materials"]]
        ref = "compare:" + ",".join(spec["materials"])
    else:
        fs = {lg: json.loads(_figure_cached(_canon(spec), lg)) for lg in LANGS}
        content = {lg: {"title": f["title"], "sub": "", "blocks": [], "figure": f} for lg, f in fs.items()}
        keys = list(fs["de"]["keys"])
        eid = {"atlas": "atlas:" + spec.get("gef", ""), "mech": "mech:" + spec.get("mech", ""), "chart": "tool:auswahl"}[spec["fig"]]
        ref = {"atlas": eid, "mech": f"{eid}@{fs['de'].get('frame', 0)}", "chart": "chart:" + str((spec.get("req") or {}).get("x")) + "/" + str((spec.get("req") or {}).get("y"))}[spec["fig"]]
    sources = _sources(keys, eid)
    for e in local_eids:                                   # Vergleich: Quellen aus den Datensätzen aller Werkstoffe
        missing = [x for x in keys if x not in sources]
        if not missing:
            break
        sources.update(_sources(missing, e))
    pin = {"id": pid or "p" + secrets.token_hex(5), "kind": k, "entry": eid, "ref": ref, "spec": spec, "content": content,
           "sources": sources, "pinned": _now()}
    pin["hash"] = _fingerprint(pin)
    pin["flag"] = _pin_flag(pin)
    if thumb and k == "figure":
        pin["thumb"] = _thumb(content[lang if lang in LANGS else "de"]["figure"], lang)
    return pin


def _pin_statements(pin: dict, lang: str = "de") -> list[dict]:
    """Alle Aussagen eines Pins (auch die Zellen eines Vergleichs)."""
    c = (pin.get("content") or {}).get(lang) or {}
    out = [s for b in c.get("blocks") or [] for s in b.get("statements") or []]
    for r in (c.get("table") or {}).get("rows") or []:
        out += [x for x in r.get("cells") or [] if x]
    return out


def _pin_flag(pin: dict, lang: str = "de") -> dict:
    c = (pin.get("content") or {}).get(lang) or {}
    st = [s for s in _pin_statements(pin, lang) if s.get("unsourced") != "software"]
    n_open = sum(1 for s in st if flag_of(s) == "open")
    n_un = sum(1 for s in st if flag_of(s) == "unchecked")
    if c.get("figure"):
        n_un += 1 if c["figure"].get("check") in FLAG_CHECK else 0
        n_open += 1 if not c["figure"].get("keys") else 0
    return {"n": len(st) + (1 if c.get("figure") else 0), "open": n_open, "unchecked": n_un}


def _diff(old: dict, new: dict) -> list[str]:
    """Was sich seit dem Anheften geändert hat: ``text``, ``sources`` und/oder ``check``."""
    def view(p, field):
        st = _pin_statements(p)
        if field == "text":
            return [(s.get("id"), s.get("text")) for s in st] + [((p["content"]["de"].get("figure") or {}).get("caption"))]
        if field == "sources":
            return [sorted(s.get("keys") or []) for s in st] + [sorted((p["content"]["de"].get("figure") or {}).get("keys") or []),
                                                               {k: v["rec"] for k, v in (p.get("sources") or {}).items()}]
        return [s.get("check") for s in st] + [(p["content"]["de"].get("figure") or {}).get("check"),
                                               {k: v["status"] for k, v in (p.get("sources") or {}).items()}]
    return [f for f in ("text", "sources", "check") if view(old, f) != view(new, f)]


def state(pins: list[dict]) -> dict:
    """Stand jedes Pins gegen das aktuelle Kompendium: ``ok``, ``changed`` (mit ``what``) oder ``missing``."""
    out = {}
    for p in pins or []:
        if not isinstance(p, dict) or p.get("kind") == "note" or not p.get("spec"):
            continue
        try:
            now = make_pin(p["spec"], p.get("id"), thumb=False)
        except (LookupError, T.ToolError, KeyError, ValueError):
            out[p.get("id")] = {"state": "missing"}
            continue
        if now["hash"] == p.get("hash"):
            out[p.get("id")] = {"state": "ok"}
        else:
            out[p.get("id")] = {"state": "changed", "what": _diff(p, now) if p.get("content") else []}
    return {"states": out}


def renew(pin: dict, lang: str = "de") -> dict:
    """Neue Fassung eines Pins (auf Wunsch): gleiche Kennung und Lage, Inhalt und Quellen wie heute im Kompendium."""
    new = make_pin(pin.get("spec"), pin.get("id"), lang)
    for k in ("x", "y", "w", "h", "frame"):
        if k in pin:
            new[k] = pin[k]
    return new


def walk(ids, lang: str = "de") -> list[dict]:
    """Der Weg durch das Kompendium für eine Auswahl: je Werkstoff sein Eintrag und die wirklich verknüpften Einträge."""
    out, seen = [], set()
    for mid in ids or []:
        eid = "material:" + str(mid)
        try:
            e = KP.entry(eid, lang)
        except LookupError:
            continue
        if eid not in seen:
            seen.add(eid)
            out.append({"id": eid, "title": e["title"], "kind": "material", "via": ""})
        for kind in ("atlas", "mech"):
            for x in e["links"][kind]:
                if x["id"] not in seen:
                    seen.add(x["id"])
                    out.append({"id": x["id"], "title": x["title"], "kind": kind, "via": e["title"]})
    return out


# ----------------------------------------------------------------------------- Ablage je Projekt
def _path(envs, project: str):
    return Environments(envs.suite, envs.module, project).base / FILE


def _num(v, default=0.0, lo=-1e6, hi=1e6) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    return default if x != x or x < lo or x > hi else round(x, 1)


def _id(v, prefix: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_-]", "", str(v or ""))[:40]
    return s or prefix + secrets.token_hex(4)


def new_board(name: str = "Tafel 1") -> dict:
    return {"id": "b" + secrets.token_hex(4), "name": name, "view": {"x": 40, "y": 40, "z": 1}, "frames": [], "cards": []}


def normalize(doc) -> dict:
    """Prüft ein Tafel-Dokument der Seite: Kennungen, Zahlen, Längen. Der Inhalt der Pins bleibt unverändert."""
    if not isinstance(doc, dict):
        raise EnvError("Tafel-Dokument ungültig")
    boards = []
    for b in (doc.get("boards") or [])[:MAX_BOARDS]:
        if not isinstance(b, dict):
            continue
        frames = []
        for f in (b.get("frames") or [])[:MAX_FRAMES]:
            if isinstance(f, dict):
                frames.append({"id": _id(f.get("id"), "f"), "name": str(f.get("name") or "")[:120], "x": _num(f.get("x")), "y": _num(f.get("y")),
                               "w": _num(f.get("w"), 420, 120, 8000), "h": _num(f.get("h"), 320, 100, 8000)})
        ids = {f["id"] for f in frames}
        cards = []
        for c in (b.get("cards") or [])[:MAX_CARDS]:
            if not isinstance(c, dict) or (c.get("kind") != "note" and c.get("kind") not in KINDS):
                continue
            c = dict(c)
            c.update(id=_id(c.get("id"), "p"), x=_num(c.get("x")), y=_num(c.get("y")), w=_num(c.get("w"), 260, 120, 1600), h=_num(c.get("h"), 80, 20, 4000))
            if c.get("frame") not in ids:
                c.pop("frame", None)
            if c["kind"] == "note":
                c["text"] = str(c.get("text") or "")[:MAX_NOTE]
            cards.append(c)
        v = b.get("view") if isinstance(b.get("view"), dict) else {}
        boards.append({"id": _id(b.get("id"), "b"), "name": str(b.get("name") or "Tafel")[:120],
                       "view": {"x": _num(v.get("x"), 40), "y": _num(v.get("y"), 40), "z": _num(v.get("z"), 1, 0.2, 3)}, "frames": frames, "cards": cards})
    if not boards:
        boards = [new_board()]
    active = doc.get("active") if any(b["id"] == doc.get("active") for b in boards) else boards[0]["id"]
    return {"version": 1, "rev": int(doc.get("rev") or 0), "active": active, "boards": boards,
            "selection": [str(x) for x in (doc.get("selection") or [])][:200]}


def load(envs, project: str | None = None) -> dict:
    with _LOCK:
        envs.ensure()
        pid = project or envs.project
        doc = _read(_path(envs, pid), None)
        return {"project": pid, "doc": normalize(doc if isinstance(doc, dict) else {})}


def save(envs, req: dict) -> dict:
    """Speichert in das Projekt, aus dem die Seite geladen hat, auch wenn der Hub inzwischen ein anderes gewählt hat."""
    project = str(req.get("project") or "")
    if not project:
        raise EnvError("Projekt fehlt")
    doc = normalize(req.get("doc"))
    if len(_canon(doc)) > MAX_DOC:
        raise EnvError("Die Tafeln sind zu gross zum Speichern")
    with _LOCK:
        p = _path(envs, project)
        cur = _read(p, None)
        rev = int((cur or {}).get("rev") or 0)
        if req.get("rev") is not None and int(req["rev"]) != rev:
            return {"conflict": True, "project": project, "doc": normalize(cur or {})}
        doc["rev"] = rev + 1
        _write(p, doc)
    return {"ok": True, "project": project, "rev": doc["rev"]}


def route(envs, action: str, req: dict) -> dict:
    lang = req.get("lang") if req.get("lang") in LANGS else "de"
    if action == "load":
        return load(envs, req.get("project") or None)
    if action == "save":
        return save(envs, req)
    if action == "pin":
        return {"pin": make_pin(req.get("spec"), lang=lang)}
    if action == "state":
        return state(req.get("pins") or [])
    if action == "renew":
        return {"pin": renew(req.get("pin") or {}, lang)}
    if action == "walk":
        return {"items": walk(req.get("ids") or [], lang)}
    if action == "plan":
        return plan(req.get("board") or {}, req.get("frame") or None, lang)
    raise LookupError("Unbekannte Aktion")


# ----------------------------------------------------------------------------- Export: Reihenfolge und Warnliste
def _reading(c: dict):
    return (round(float(c.get("y") or 0) / 60), float(c.get("x") or 0))


def ordered(board: dict, frame: str | None = None, lang: str = "de") -> list[tuple[dict, list[dict]]]:
    """[(Rahmen, Karten in Leserichtung)] in der Reihenfolge der Rahmen; lose Karten kommen beim Export der ganzen Tafel zuletzt."""
    cards = [c for c in board.get("cards") or [] if isinstance(c, dict)]
    frames = [f for f in board.get("frames") or [] if isinstance(f, dict)]
    ids = {f.get("id") for f in frames}
    out = [(f, sorted((c for c in cards if c.get("frame") == f.get("id")), key=_reading)) for f in frames if not frame or f.get("id") == frame]
    if not frame:
        loose = sorted((c for c in cards if c.get("frame") not in ids), key=_reading)
        if loose:
            out.append(({"id": "_lose", "name": "Ohne Rahmen" if lang != "en" else "Not in a frame"}, loose))
    return out


def _is_multi(pin: dict) -> bool:
    return pin.get("kind") in ("entry", "section", "compare")


def plan(board: dict, frame: str | None = None, lang: str = "de") -> dict:
    """Was vor dem Export zu sagen ist: Pins mit Aussagen ohne Quelle oder auf ungeprüften Quellen, und geänderte Pins."""
    flagged, frames, pins = [], [], []
    for f, cards in ordered(board, frame, lang):
        frames.append({"id": f.get("id"), "name": f.get("name") or "", "n": len(cards)})
        pins += [c for c in cards if c.get("kind") != "note"]
    for p in pins:
        c = (p.get("content") or {}).get(lang) or {}
        st = [{"id": s.get("id"), "text": s.get("text", ""), "reason": flag_of(s)} for s in _pin_statements(p, lang) if s.get("unsourced") != "software" and flag_of(s)]
        fig = c.get("figure")
        if fig and fig.get("check") in FLAG_CHECK:
            st.append({"id": p.get("ref"), "text": fig.get("title", ""), "reason": "unchecked"})
        elif fig and not fig.get("keys"):
            st.append({"id": p.get("ref"), "text": fig.get("title", ""), "reason": "open"})
        if st:
            flagged.append({"pin": p.get("id"), "title": c.get("title", ""), "kind": p.get("kind"), "partial": _is_multi(p),
                            "n": len(st), "n_open": sum(1 for x in st if x["reason"] == "open"), "statements": st[:12]})
    states = state(pins)["states"]
    changed = [{"pin": p.get("id"), "title": ((p.get("content") or {}).get(lang) or {}).get("title", ""), **states[p["id"]]}
               for p in pins if states.get(p.get("id"), {}).get("state") in ("changed", "missing")]
    return {"frames": frames, "flagged": flagged, "changed": changed, "n_pins": len(pins)}


# ----------------------------------------------------------------------------- Export: Bericht
DAG = r"$^{\dagger}$"
DAG_OPEN = DAG + "{}"                  # † wegen fehlender Quelle: die Tabellenlegende unterscheidet so beide Gründe
STAR = r"$^{*}$"


def _bibkey(k: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "-", str(k))


class _Out:
    """Schreibt die Quellen genau der gezeigten Aussagen in das Bündel und merkt sich, welche Zeichen zu erklären sind."""

    def __init__(self, b: Bundle, lang: str, inc: dict):
        self.b, self.lang, self.inc = b, lang, inc
        self.dag = self.star = self.open = False

    def L(self, de, en):
        return de if self.lang == "de" else en

    def reset(self):
        self.dag = self.star = self.open = False

    def keys(self, keys, sources: dict) -> list[str]:
        if not self.inc.get("citations", True):
            return []
        out = []
        for k in keys or []:
            src = (sources or {}).get(k)
            if not src:
                continue
            bk = _bibkey(k)
            n0 = len(self.b.bib)
            rec = src["rec"]
            if self.L("de", "en") == "en" and KP.RF.NG in str(rec.get("note") or ""):   # der Vermerk folgt der Berichtssprache
                rec = {**rec, "note": rec["note"].replace(KP.RF.NG, KP.NG_EN)}
            labcite.to_bib(self.b, bk, rec)
            if not src["rec"].get("authors"):
                B._sortkey(self.b, n0, str(src["rec"].get("title") or bk)[:40])
            out.append(bk)
        return list(dict.fromkeys(out))

    def cite(self, keys, sources) -> str:
        k = self.keys(keys, sources)
        return f"~\\cite{{{','.join(k)}}}" if k else ""

    def mark(self, s: dict) -> str:
        f = flag_of(s)
        if f:
            self.dag = True
            self.open = self.open or f == "open"
        return DAG if f else ""

    def sentence(self, s: dict, sources: dict) -> str:
        t = str(s.get("text") or "").strip()
        if s.get("label") and "prop" not in s:
            t = f"{s['label']}: {t}"
        core = t[:-1] if t.endswith(".") else t
        tail = "" if core.endswith(("!", "?")) else "."
        mid = self.cite(s.get("keys"), sources)
        if mid and s.get("basis") == "entry":
            mid += STAR
            self.star = True
        no_src = self.L(" (ohne Quelle)", " (no source)") if s.get("unsourced") == "open" else ""
        return B.tx(core) + no_src + mid + self.mark(s) + tail

    def note(self) -> str:
        """Erklärung der Zeichen, die dieser Abschnitt benutzt. Sie sagt nichts über eine erfolgte Prüfung."""
        out = []
        if self.dag:
            out.append(self.L("† Stützt sich auf Quellen, deren Angaben nicht am Original geprüft sind"
                              + (", oder hat keine nachvollziehbare Quelle" if self.open else "") + ".",
                              "† Rests on sources whose details were not checked against the original"
                              + (", or has no traceable source" if self.open else "") + "."))
        if self.star:
            out.append(self.L("* Quelle des Eintrags; die Zuordnung zum einzelnen Satz steht noch aus.",
                              "* Source of the entry; the assignment to the individual sentence is still open."))
        return " ".join(out).replace("†", DAG).replace("* ", STAR + " ", 1) if out else ""


def _rng(s: dict, lang: str) -> str:
    r = s.get("range")
    return f"{KP._num(r[0], lang)}–{KP._num(r[1], lang)}" if isinstance(r, list) and len(r) == 2 else ""


def _value_row(o: _Out, s: dict, sources: dict, name: str | None = None) -> list[str]:
    """Zeile Kennwert | Wert | Spanne | Quelle mit † genau an dem Teil, der auf einer ungeprüften Quelle ruht."""
    val = B.tx(s.get("shown") or "")
    if s.get("value_keys") and s.get("value_status") in FLAG_CHECK:
        val += DAG
    rng = B.tx(_rng(s, o.lang))
    if rng and s.get("range_status") in FLAG_CHECK:
        rng += DAG
    src = o.cite(list(dict.fromkeys((s.get("value_keys") or []) + (s.get("range_keys") or []))), sources).lstrip("~")
    if s.get("unsourced") == "open":
        src = B.tx(o.L("ohne Quelle", "no source"))
        val += DAG_OPEN
    lab = B.tx(s.get("label") or s.get("prop") or "") + (f" ({B.tx(s['art'])})" if s.get("art") else "")
    return ([B.tx(name)] if name is not None else []) + [lab, val, rng or "--", src or "--"]


def _value_head(o: _Out, with_name: bool) -> list[str]:
    return ([o.L("Werkstoff", "Material")] if with_name else []) + [o.L("Kennwert", "Property"), o.L("Wert", "Value"), o.L("Spanne", "Range"), o.L("Quelle", "Source")]


def _keep(pin: dict, leave: set) -> tuple[list[dict], bool]:
    """Blöcke des Pins ohne die Aussagen, die der Nutzer weglässt. Programmbeschreibungen gehören nicht in den Bericht."""
    c = pin["_c"]
    drop = pin.get("id") in leave
    multi = pin.get("kind") in ("entry", "section")
    out = []
    for b in c.get("blocks") or []:
        st = [s for s in b.get("statements") or [] if not (multi and s.get("unsourced") == "software") and not (drop and flag_of(s))]
        if st:
            out.append({**b, "statements": st})
    return out, drop


def build_bundle(request: dict) -> dict:
    """Bericht aus den gespeicherten Pin-Datensätzen: je Rahmen ein Abschnitt, in der Reihenfolge der Rahmen."""
    lang = request.get("lang") if request.get("lang") in LANGS else "de"
    inc = {"figures": True, "tables": True, "citations": True, "text": True, **(request.get("include") or {})}
    sec = next((x for x in request.get("sections") or [] if x.get("tool") == "infotafel"), None)
    req = (sec or {}).get("req") or {}
    board = req.get("board") or {}
    leave = {str(x) for x in req.get("leave_out") or []}
    frames = ordered(board, req.get("frame") or None, lang)
    name = str(board.get("name") or ("Infotafel" if lang == "de" else "Info board"))
    title = request.get("title") or (("Infotafel: " if lang == "de" else "Info board: ") + name)
    b = Bundle(module="werkstoffe", module_name="Werkstoffe" if lang == "de" else "Materials", title=title, lang=lang,
               slug=request.get("slug") or None, summary=" · ".join(str(f.get("name") or "") for f, _ in frames))
    o = _Out(b, lang, inc)
    from_compendium, n_sec = False, 0
    for f, cards in frames:
        n_sec += 1
        from_compendium = _write_frame(o, f, cards, f"rahmen{n_sec}", leave, n_sec) or from_compendium
    if not any(it["kind"] in ("text", "figure", "table") for it in b.items):
        raise T.ToolError(o.L("Für den Bericht bleibt nichts übrig.", "Nothing is left for the report."))
    if inc.get("text", True) and from_compendium:                 # ein Satz für alle Rahmen; er gilt für jede Teilauswahl
        b.add_methods([o.L("Dieser Teil stellt Aussagen, Kennwerte und Abbildungen aus dem Kompendium des Moduls Werkstoffe zusammen; jede Aussage nennt ihre eigene Quelle.",
                           "This part compiles statements, properties and figures from the compendium of the Materials module; each statement names its own source.")],
                      o.L("Methodik", "Methods"))
    b.set_source({**request, "slug": b.slug}, {})
    out = b.to_dict()
    out["items"] = [i for i in out["items"] if i.get("methods")] + [i for i in out["items"] if not i.get("methods")]
    for it in out["items"]:                        # the hub's results section keeps this order instead of text, figures, tables
        if it["kind"] in ("text", "figure", "table"):
            it["flow"] = True
    return out


def _write_frame(o: _Out, frame: dict, cards: list[dict], pid: str, leave: set, n: int) -> bool:
    """Ein Rahmen: ein Textbaustein mit Überschrift, danach seine Abbildungen und Tabellen. True, wenn Inhalt aus dem Kompendium kam."""
    lang, inc, b = o.lang, o.inc, o.b
    o.reset()
    head = B.tx(frame.get("name") or o.L("Abschnitt", "Section"))
    parts: list[str] = []
    val_rows: list[list[str]] = []
    val_keys: list[str] = []
    figs: list[tuple] = []
    tables: list[tuple] = []
    any_kp = False
    for c in cards:
        if c.get("kind") == "note":
            text = str(c.get("text") or "").strip()
            if text:
                body = "\n\n".join(B.tx(x) for x in re.split(r"\n\s*\n", text))
                parts.append("\\par\\medskip\\noindent\\textit{" + o.L("Eigene Notiz", "Own note") + ":} " + body + "\\par\\medskip")
            continue
        cont = (c.get("content") or {}).get(lang)
        if not cont:
            continue
        pin = {**c, "_c": cont}
        src = c.get("sources") or {}
        if c.get("kind") == "figure":
            fig = cont["figure"]
            flag = fig.get("check") in FLAG_CHECK or not fig.get("keys")
            if flag and c.get("id") in leave:
                continue
            figs.append((c, fig, flag))
            any_kp = True
            continue
        if c.get("kind") == "compare":
            t = _compare_table(o, c, cont, c.get("id") in leave)
            if t:
                tables.append(t)
                any_kp = True
            continue
        blocks, _ = _keep(pin, leave)
        if not blocks:
            continue
        any_kp = True
        if c.get("kind") == "value":
            for bl in blocks:
                for s in bl["statements"]:
                    val_rows.append(_value_row(o, s, src, cont.get("title", "")))
                    val_keys += list(s.get("keys") or [])
            continue
        lines, entry_rows, entry_keys = [], [], []
        for bl in blocks:
            sub = []
            for s in bl["statements"]:
                if s.get("prop"):
                    entry_rows.append(_value_row(o, s, src))
                    entry_keys += list(s.get("keys") or [])
                else:
                    sub.append(o.sentence(s, src))
            if sub:
                lines.append((f"\\textit{{{B.tx(bl['title'])}.}} " if bl.get("title") else "") + " ".join(sub))
        if lines:
            parts.append(f"\\paragraph{{{B.tx(cont.get('title') or '')}}} " + "\n\n".join(lines))
        if entry_rows:
            tables.append(("werte", _value_head(o, False), entry_rows, "lrrl",
                           B.tx(o.L(f"Kennwerte: {cont.get('title', '')}.", f"Properties: {cont.get('title', '')}.")),
                           o.keys(list(dict.fromkeys(entry_keys)), src)))
    if val_rows:
        tables.insert(0, ("kennwerte", _value_head(o, True), val_rows, "llrrl",
                          B.tx(o.L("Angeheftete Kennwerte mit Spanne und Quelle.", "Pinned properties with range and source.")),
                          o.keys(list(dict.fromkeys(val_keys)), _merged_sources(cards))))
    if not any_kp and not parts:
        return False
    legend = o.note()
    if inc.get("text", True):
        body = f"\\subsubsection{{{head}}}\n" + "\n\n".join(parts) + (f"\n\n\\par\\noindent\\footnotesize {legend}\\normalsize\n" if legend and parts else "\n")
        b.add_text(f"r{n}", body, f"{frame.get('name') or head}", steps=[pid] if any_kp else [])
    if inc.get("figures", True):
        for k, (c, fig, flag) in enumerate(figs, 1):
            cap = B.tx(fig.get("caption") or "")
            if flag:
                why = (o.L("Stützt sich auf Quellen, deren Angaben nicht am Original geprüft sind.", "Rests on sources whose details were not checked against the original.")
                       if fig.get("check") in FLAG_CHECK else o.L("Hat keine nachvollziehbare Quelle.", "Has no traceable source."))
                cap = cap.rstrip(".") + DAG + ". " + DAG + " " + why
            b.add_figure((lambda fg=fig: _draw_figure(fg, lang)), f"r{n}-abb{k}", cap, width="0.8", dpi=150, cites=o.keys(fig.get("keys"), c.get("sources") or {}), steps=[pid])
    if inc.get("tables", True):
        for k, (tid, thead, rows, align, cap, keys) in enumerate(tables, 1):
            nt = _table_note(o, rows)
            b.add_table(f"r{n}-{tid}{k}", booktabs([B.tx(h) for h in thead], rows, align, small=True, escape_header=False), cap, notes=nt, cites=keys, steps=[pid])
    return any_kp


def _merged_sources(cards: list[dict]) -> dict:
    out: dict = {}
    for c in cards:
        out.update(c.get("sources") or {})
    return out


def _table_note(o: _Out, rows: list[list[str]]) -> str:
    cells = [x for r in rows for x in r]
    opn = any(DAG_OPEN in x for x in cells)
    unch = any(DAG in x.replace(DAG_OPEN, "") for x in cells)
    if opn and unch:
        return o.L(f"{DAG} Nicht am Original geprüft oder ohne nachvollziehbare Quelle.", f"{DAG} Not checked against the original, or no traceable source.")
    if unch:
        return o.L(f"{DAG} Nicht am Original geprüft.", f"{DAG} Not checked against the original.")
    if opn:
        return o.L(f"{DAG} Ohne nachvollziehbare Quelle.", f"{DAG} No traceable source.")
    return ""


def _compare_table(o: _Out, pin: dict, cont: dict, drop: bool):
    t = cont.get("table") or {}
    cols = t.get("columns") or []
    src = pin.get("sources") or {}
    rows, keys = [], []
    for r in t.get("rows") or []:
        cells, seen = [B.tx(r.get("label") or r.get("prop") or "")], False
        for x in r.get("cells") or []:
            if not x or (drop and flag_of(x)):
                cells.append("--")
                continue
            seen = True
            v = B.tx(x.get("shown") or "")
            if x.get("value_keys") and x.get("value_status") in FLAG_CHECK:
                v += DAG
            if x.get("unsourced") == "open":
                v += DAG_OPEN
            rg = B.tx(_rng(x, o.lang))
            if rg:
                v += f" ({rg}" + (DAG if x.get("range_status") in FLAG_CHECK else "") + ")"
            ks = list(dict.fromkeys((x.get("value_keys") or []) + (x.get("range_keys") or [])))
            keys += ks
            cells.append(v + o.cite(ks, src))
        if seen:
            rows.append(cells)
    if not rows:
        return None
    head = [o.L("Kennwert", "Property")] + [c["name"] for c in cols]
    cap = B.tx(o.L("Kennwerte im Vergleich, Wert (Spanne) mit Quelle je Zelle: ", "Properties compared, value (range) with a source per cell: ") + ", ".join(c["name"] for c in cols) + ".")
    return ("vergleich", head, rows, "l" + "r" * len(cols), cap, o.keys(list(dict.fromkeys(keys)), src))
