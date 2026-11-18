"""Herkunft und Aufbewahrung (A8).

* `chain(suite, project, ref)` – vom Wert zurück bis zur Rohdatei: Projektindex-Eintrag → geteilte Version →
  Umgebung und Eintrag des erzeugenden Moduls → Rohdatei (Pfad, SHA-256). Ein abgeleiteter Datensatz zeigt seine
  Schritte und die ganze Kette seiner Eltern. Wird nur auf Anfrage gebaut.
* `report_refs(suite, project)` – welche Freigabe-Versionen und Index-Einträge in Berichten des Projekts stecken
  (gelesen aus `projects/<bericht>/files/lab/*/bundle.json`, deren `history/*/bundle.json` und aus entfernten, aber
  ausgegebenen Ergebnissen unter `lab/_removed/`), samt den Elternversionen benutzter abgeleiteter Datensätze.
* `guard_*` – Versionen (auch Elternversionen) und Umgebungen, die ein Bericht benutzt, lassen sich nicht löschen.
* `dependencies(suite, project)` – Liste für den Projekt-Export.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from labproject import EnvError, Environments, Suite, _read

SHARE_RE = re.compile(r"^s-[0-9a-f]{8}$")
INDEX_RE = re.compile(r"^g-[0-9a-f]{8}$")


# ---------------------------------------------------------------------------- Berichte durchsuchen
def _walk_refs(o, out):
    """Verweise in einem gespeicherten Request finden (Umschläge, Herkunftsangaben, Bindungen, Index-IDs).
    Gleiche Regel wie `refsIn` in server/lab.js."""
    if isinstance(o, dict):
        if o.get("schema") == "suite.shared-result/1" and SHARE_RE.match(str(o.get("id", ""))):
            out["shares"].add((o["id"], int(o.get("version") or 0)))
        if SHARE_RE.match(str(o.get("share", ""))) and o.get("version") is not None:
            try:
                out["shares"].add((o["share"], int(o["version"])))
            except (TypeError, ValueError):
                pass
        # Bindung {id, mode: pin|live|copy, version?, used?}: die benutzte Version zählt
        if o.get("mode") in ("pin", "live", "copy") and SHARE_RE.match(str(o.get("id", ""))) and o.get("schema") is None:
            v = o.get("used") if o.get("used") is not None else o.get("version")
            try:
                if v is not None:
                    out["shares"].add((o["id"], int(v)))
            except (TypeError, ValueError):
                pass
        if INDEX_RE.match(str(o.get("index", ""))):
            out["index"].add(o["index"])
        for v in o.values():
            _walk_refs(v, out)
    elif isinstance(o, list):
        for v in o:
            _walk_refs(v, out)


def _report_dirs(suite: Suite, project: str | None):
    reg = suite.registry
    pid = project or suite.active()
    p = next((x for x in reg["projects"] if x["id"] == pid), None)
    projects_dir = suite.root.parent
    for rid in (p or {}).get("reports", []):
        lab = projects_dir / str(rid) / "files" / "lab"
        if lab.is_dir():
            yield str(rid), lab


def report_refs(suite: Suite, project: str | None = None, parents: bool = True) -> dict:
    """{"shares": {(id, v): [Bericht/Ergebnis#Revision]}, "index": {g-id: [...]}}

    Gelesen werden die aktuellen Ergebnisse, ihre alten Revisionen (`history/`) und entfernte, aber ausgegebene
    Ergebnisse (`lab/_removed/`, siehe server/lab.js). Mit `parents` kommen die Versionen dazu, aus denen ein
    benutzter Datensatz abgeleitet oder mit denen er verbunden wurde (rekursiv)."""
    shares: dict = {}
    index: dict = {}
    for rid, lab in _report_dirs(suite, project):
        mans = (list(lab.glob("*/bundle.json")) + list(lab.glob("*/history/*/bundle.json"))
                + list(lab.glob("_removed/*/bundle.json")) + list(lab.glob("_removed/*/history/*/bundle.json")))
        for man in mans:
            m = _read(man)
            if not isinstance(m, dict):
                continue
            out = {"shares": set(), "index": set()}
            _walk_refs((m.get("source") or {}).get("request"), out)
            where = f"{rid}/{m.get('slug', man.parent.name)}#{m.get('revision', 1)}"
            if "_removed" in man.parts:
                where += " (entfernt, aufbewahrt)"
            for s in out["shares"]:
                shares.setdefault(s, []).append(where)
            for g in out["index"]:
                index.setdefault(g, []).append(where)
    if parents and shares:
        shares = _with_parents(suite, project, shares)
    return {"shares": shares, "index": index}


def _with_parents(suite: Suite, project, shares: dict) -> dict:
    """Benutzte Datensatz-Versionen um ihre Eltern (derived_from) und verbundenen Datensätze (inputs, gepinnte
    Verbindungen) ergänzen – sonst liesse sich die Elternversion eines benutzten abgeleiteten Datensatzes löschen."""
    from labshare import Sharebox
    box = Sharebox(suite, project)
    out = {k: list(v) for k, v in shares.items()}
    todo, seen = list(shares), set(shares)
    while todo:
        sid, v = todo.pop()
        try:
            env = box.get(sid, v or None)
        except EnvError:
            continue
        head = env.get("dataset")
        if not isinstance(head, dict):
            continue
        refs = {"shares": set(), "index": set()}
        _walk_refs(head.get("provenance"), refs)
        for k in refs["shares"]:
            if k == (sid, v):
                continue
            lst = out.setdefault(k, [])
            for w in out.get((sid, v), []):
                w2 = w if " über " in w else f"{w} über {sid} v{v}"
                if w2 not in lst:
                    lst.append(w2)
            if k not in seen:
                seen.add(k)
                todo.append(k)
    return out


def refs_in_request(request) -> dict:
    out = {"shares": set(), "index": set()}
    _walk_refs(request, out)
    return {"shares": sorted(out["shares"]), "index": sorted(out["index"])}


# ---------------------------------------------------------------------------- Aufbewahrung
def guard_share_delete(suite: Suite, project, share_id: str, version: int | None = None) -> None:
    used = report_refs(suite, project)["shares"]
    hits = [(k, v) for k, v in used.items() if k[0] == share_id and (version is None or k[1] == int(version))]
    if hits:
        raise EnvError("Wird in einem Bericht benutzt und kann nicht gelöscht werden: "
                       + "; ".join(f"{k[0]} v{k[1]} in {', '.join(v)}" for k, v in hits))


def guard_env_delete(suite: Suite, project, module: str, eid: str) -> None:
    """Eine Umgebung, aus der eine in einem Bericht benutzte Version stammt, bleibt bestehen."""
    from labshare import Sharebox
    used = report_refs(suite, project)["shares"]
    if not used:
        return
    box = Sharebox(suite, project)
    for (sid, v), where in used.items():
        try:
            env = box.get(sid, v)
        except EnvError:
            continue
        p = env.get("producer") or {}
        if p.get("module") == module and p.get("env") == eid:
            raise EnvError(f"Die Umgebung liefert {sid} v{v}, die in {', '.join(where)} benutzt wird – Löschen nicht möglich")


# ---------------------------------------------------------------------------- Kette
def _raw_step(suite, project, prod: dict) -> dict:
    mod, eid, item = prod.get("module"), prod.get("env"), prod.get("item")
    if not (mod and eid):
        return {"level": "raw", "title": "Rohdatei unbekannt", "detail": "Erzeuger ohne Umgebung", "ok": False}
    envs = Environments(suite, mod, project)
    try:
        st = envs.load_state(eid, {}) or {}
    except EnvError:
        st = {}
    it = (st.get("items") or {}).get(item) or {}
    rid = prod.get("raw") or it.get("raw")
    if not rid:
        return {"level": "raw", "title": "Rohdatei nicht mehr in der Umgebung", "ok": False,
                "detail": f"{mod} · {eid} · Eintrag {item}: keine Rohdatei gespeichert (z. B. Beispieldaten)"}
    p = envs.base / eid / "raw" / rid
    ok = p.exists()
    sha = hashlib.sha256(p.read_bytes()).hexdigest() if ok else None
    return {"level": "raw", "title": f"Rohdatei {it.get('file') or rid.split('-', 1)[-1]}", "ok": ok,
            "path": str(p), "sha256": sha, "sha_matches_id": bool(sha and sha.startswith(rid.split("-", 1)[0])),
            "detail": f"{mod} · Umgebung {eid} · Eintrag {item}"}


MAX_CHAIN_DEPTH = 8                     # abgeleitet aus abgeleitet aus … (die Datenaufbereitung erlaubt 6)


def _file_steps(suite, project, files: list, prod: dict | None, checked: bool = True) -> list[dict]:
    """Je Quelldatei Blatt und Zellbereiche; liegt die Rohdatei noch in der Umgebung, wird ihr SHA-256 verglichen."""
    prod = prod or {}
    if not files:
        return [{"level": "raw", "title": "Keine Quelldatei angegeben", "ok": False,
                 "detail": "z. B. eingefügte Werte ohne Datei"}]
    envs = Environments(suite, prod["module"], project) if checked and prod.get("module") and prod.get("env") else None
    steps = []
    for f in files[:20]:
        where = ", ".join(x for x in (f"Blatt {f['sheet']}" if f.get("sheet") else "",
                                      "Bereiche " + ", ".join(map(str, f.get("ranges") or [])) if f.get("ranges") else "") if x)
        st = {"level": "raw", "title": f"Quelldatei {f.get('name') or '?'}", "detail": where or "ganze Datei",
              "sha256": f.get("sha256"), "ok": bool(f.get("sha256"))}
        if not checked:
            st["detail"] += " · gespeicherter SHA-256, Rohdatei nicht geprüft"
        elif envs and f.get("raw"):
            p = envs.base / prod["env"] / "raw" / str(f["raw"])
            if p.exists() and re.match(r"^[0-9A-Za-z._-]{1,120}$", str(f["raw"])):
                sha = hashlib.sha256(p.read_bytes()).hexdigest()
                st.update(path=str(p), ok=sha == f.get("sha256"), sha_matches=sha == f.get("sha256"))
            else:
                st.update(ok=False, detail=st["detail"] + " · Rohdatei nicht mehr in der Umgebung")
        steps.append(st)
    return steps


def _share_step(env: dict) -> dict:
    p = env.get("producer") or {}
    return {"level": "share", "title": f"Freigabe {env['id']} v{env['version']} ({env.get('kind')})",
            "detail": f"von {p.get('module')} · {p.get('env_name') or p.get('env')} · {p.get('item_name') or p.get('item')}, "
                      f"Modulversion {p.get('module_version') or '?'}, {env['created']}", "ok": True,
            "protocol": next((s.get("protocol") for s in env.get("sources") or [] if isinstance(s, dict) and s.get("protocol")), None)}


def _dataset_steps(suite, project, head: dict, prod: dict, depth: int = 0) -> list[dict]:
    """DP-02: Datensatz → Umgebung → je Quelldatei Blatt und Zellbereiche, Rohdatei mit SHA-256-Vergleich.
    Ein abgeleiteter Datensatz zeigt seine Schritte und dann die ganze Kette seines Elterndatensatzes (rekursiv bis
    zur Rohdatei); fehlt die Elternversion, wird die im Datensatz gespeicherte Herkunft des Elters gezeigt."""
    from labshare import Sharebox
    prov = head.get("provenance") or {}
    cols = head.get("columns") or []
    steps = [{"level": "dataset", "title": f"Datensatz „{head.get('title')}“: {head.get('rows')} Zeilen × {len(cols)} Spalten",
              "detail": "; ".join(f"{c.get('name')}" + (f" [{c['unit']}]" if c.get("unit") else "")
                                  + (f" ← {c['cells']}" if c.get("cells") else "") for c in cols[:12])
                        + (" …" if len(cols) > 12 else ""),
              "recipe": len(prov.get("recipe") or []), "ok": True}]
    if prod.get("module"):
        steps.append({"level": "env", "title": f"Umgebung {prod.get('env_name') or prod.get('env')} in {prod['module']}",
                      "detail": f"Eintrag {prod.get('item_name') or prod.get('item')}", "ok": True})
    d = prov.get("derived_from")
    if not (isinstance(d, dict) and d.get("share")):
        return steps + _file_steps(suite, project, prov.get("files") or [], prod)
    texts = [str(s.get("text") or s.get("op") or "") for s in prov.get("steps") or []]
    steps.append({"level": "derived", "ok": True, "steps": len(texts),
                  "title": f"Abgeleitet aus „{d.get('title') or d['share']}“ ({d['share']} v{d.get('version')})",
                  "detail": "; ".join(texts[:12]) + (" …" if len(texts) > 12 else "") if texts else "ohne Schritte"})
    for i in prov.get("inputs") or []:
        if isinstance(i, dict) and i.get("share"):
            steps.append({"level": "input", "ok": True, "title": f"Verbunden mit „{i.get('title') or i['share']}“ "
                                                                  f"({i['share']} v{i.get('version')})",
                          "detail": "zweiter Datensatz eines Schritts (Verbinden)"})
    if depth >= MAX_CHAIN_DEPTH:
        steps.append({"level": "end", "title": "Kette hier abgebrochen", "ok": False,
                      "detail": f"mehr als {MAX_CHAIN_DEPTH} abgeleitete Stufen"})
        return steps
    try:
        penv = Sharebox(suite, project).get(d["share"], d.get("version"))
        if not isinstance(penv.get("dataset"), dict):
            raise EnvError("Elternfreigabe ist kein Datensatz")
    except EnvError as e:
        steps.append({"level": "share", "title": f"Freigabe {d['share']} v{d.get('version')} nicht lesbar", "ok": False,
                      "detail": f"{e} – gespeicherte Herkunft des Elterndatensatzes"})
        p = prov.get("parent_provenance") or {}
        while isinstance(p.get("parent_provenance"), dict) and p.get("parent_provenance") and not p.get("files"):
            p = p["parent_provenance"]
        return steps + _file_steps(suite, project, p.get("files") or [], None, checked=False)
    steps.append(_share_step(penv))
    return steps + _dataset_steps(suite, project, penv["dataset"], penv.get("producer") or {}, depth + 1)


def chain(suite: Suite, project, ref: dict) -> list[dict]:
    """ref = {"index": g-id} | {"share": s-id, "version": n} | {"module", "env", "item"} → Schritte bis zur Rohdatei."""
    from labindex import ProjectIndex
    from labshare import Sharebox
    steps = []
    if ref.get("index"):
        e = ProjectIndex(suite, project).get(ref["index"])
        q = e["quantity"]
        steps.append({"level": "index", "title": f"Projektindex {e['id']}: {e['key']}",
                      "detail": f"{q['value']} {q.get('unit', '')} ({e['type']}), angelegt {e['created']}", "ok": True})
        p = e.get("provenance") or {}
        if p.get("share"):
            ref = {"share": p["share"], "version": p.get("version")}
        elif p.get("module") and p.get("item"):
            ref = {"module": p["module"], "env": p.get("env"), "item": p["item"]}
        else:
            steps.append({"level": "end", "title": f"Erfasst in {p.get('module') or '?'} · {p.get('env_name') or p.get('env') or '?'}",
                          "detail": "ohne Rohdatei (berechnet oder Tabellenwert)", "ok": True})
            return steps
    if ref.get("share"):
        env = Sharebox(suite, project).get(ref["share"], ref.get("version"))
        p = env.get("producer") or {}
        steps.append(_share_step(env))
        if isinstance(env.get("dataset"), dict):
            steps.extend(_dataset_steps(suite, project, env["dataset"], p))
            return steps
        ref = p
    if ref.get("module"):
        steps.append({"level": "env", "title": f"Umgebung {ref.get('env_name') or ref.get('env')} in {ref['module']}",
                      "detail": f"Eintrag {ref.get('item_name') or ref.get('item')}", "ok": True})
        steps.append(_raw_step(suite, project, ref))
    return steps


def chain_for_report(suite: Suite, project, report_id: str, slug: str) -> dict:
    """Alle Ketten für die Verweise eines Berichtsergebnisses (aktuelle Revision)."""
    if not re.match(r"^[A-Za-z0-9_-]{1,80}$", report_id or "") or not re.match(r"^[A-Za-z0-9_.-]{1,80}$", slug or ""):
        raise EnvError("ungültiger Bericht oder Ergebnisname")
    man = _read(suite.root.parent / report_id / "files" / "lab" / slug / "bundle.json")
    if not isinstance(man, dict):
        raise EnvError("Ergebnis nicht gefunden")
    refs = refs_in_request((man.get("source") or {}).get("request"))
    out = []
    for sid, v in refs["shares"]:
        out.append({"ref": f"{sid} v{v}", "steps": chain(suite, project, {"share": sid, "version": v})})
    for g in refs["index"]:
        out.append({"ref": g, "steps": chain(suite, project, {"index": g})})
    return {"result": f"{report_id}/{slug}", "revision": man.get("revision", 1), "chains": out}


def dependencies(suite: Suite, project=None) -> dict:
    """Für den Export: benutzte Freigabe-Versionen, Index-Einträge und die Rohdateien dahinter."""
    used = report_refs(suite, project)
    raws = {}
    for (sid, v) in used["shares"]:
        try:
            for st in chain(suite, project, {"share": sid, "version": v}):
                if st["level"] == "raw" and st.get("path"):
                    raws[st["path"]] = st.get("sha256")
        except EnvError:
            pass
    return {"project": project or suite.active(),
            "shares": [{"id": k[0], "version": k[1], "used_in": w} for k, w in sorted(used["shares"].items())],
            "index": [{"id": k, "used_in": w} for k, w in sorted(used["index"].items())],
            "raw_files": [{"path": p, "sha256": s} for p, s in sorted(raws.items())]}


def route(envs, action: str, req: dict):
    """Gemeinsame Endpunkte /api/prov/{chain,report,deps} für jeden Modulserver."""
    envs.ensure()
    if action == "chain":
        return {"steps": chain(envs.suite, envs.project, req.get("ref") or {})}
    if action == "report":
        return chain_for_report(envs.suite, envs.project, req.get("report") or "", req.get("slug") or "")
    if action == "deps":
        return dependencies(envs.suite, envs.project)
    raise EnvError("unbekannte Aktion")


def _dump(o) -> str:          # für Fehlersuche
    return json.dumps(o, ensure_ascii=False, indent=1, default=str)
