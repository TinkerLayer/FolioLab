"""Lokale Weboberflaeche (Spezifikation 9.2/9.3).

Laeuft nur auf 127.0.0.1, ruft nichts aus dem Netz ab. Alles bleibt im Speicher, bis
"Ausgaben schreiben" gedrueckt wird.

Start:  python -m flps.ui.server  [--port 8765] [--aus Ausgaben] [--kein-browser]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import traceback
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import numpy as np

_SDK = Path(__file__).resolve().parents[4] / "sdk" / "python"
if _SDK.is_dir() and str(_SDK) not in sys.path:
    sys.path.insert(0, str(_SDK))

import labcite  # noqa: E402
from labproject import EnvError, ModuleEnvs  # noqa: E402
from labuser import JsonStore  # noqa: E402

from .. import alloys as alloys_mod  # noqa: E402
from ..analyse import MANUAL_SHAPE, SHAPES, YIELD_DETENTS, Config, _clean, result_to_dict, run  # noqa: E402
from ..parser import FlpsError, parse_bytes  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
ROOT = Path(__file__).resolve().parents[2]


class State:
    def __init__(self, out_root: Path, alloy_path: str | None):
        self.files: dict = {}
        self.raw: dict = {}      # id -> (Dateiname, Bytes), fuer Bundles mit Quelldaten
        self.lock = threading.Lock()
        self.out_root = out_root
        self.builtin = alloys_mod.load_alloys(alloy_path)
        # Eigene Werkstoffe und Gleichungen: lesbare JSON-Dateien im Ausgabeordner (teilbar, von Hand editierbar)
        self.own = JsonStore(out_root / "eigene_werkstoffe.json", kind="folio-werkstoffe/1")
        self.eqs = JsonStore(out_root / "eigene_gleichungen.json", kind="folio-gleichungen/1")
        self.own_errors: list[str] = []
        self.alloys: list = []
        self.rebuild()
        self.envs = ModuleEnvs(out_root, "zugversuch")   # A2: Umgebungen im aktiven Projekt

    def rebuild(self):
        try:
            rows = self.own.items()
        except ValueError as e:
            rows, self.own_errors = [], [str(e)]
        else:
            self.own_errors = []
        self.alloys, errs = alloys_mod.merge_own(self.builtin, rows)
        self.own_errors += errs
        _ENV_CACHE.clear()

    def alloys_with(self, stored: list[dict] | None) -> list:
        """Werkstoffliste für den Neuaufbau eines Berichts: die im Bundle gespeicherten eigenen Werkstoffe haben
        Vorrang vor dem heutigen Stand (gelöscht oder geändert -> der Bericht bleibt wie erstellt)."""
        if not stored:
            return self.alloys
        names = {d.get("name") for d in stored}
        base = [a for a in self.alloys if a.name not in names]
        builtin_names = {a.name for a in self.builtin}
        return alloys_mod.merge_own(base, [d for d in stored if d.get("name") not in builtin_names])[0]


STATE: State | None = None


def _unc_ready():
    """Eigene Messmittel der Suite für die Unsicherheitsrechnung bekannt machen (vor jeder Auswertung)."""
    try:
        import labunc
        labunc.load_own(STATE.envs)
    except ImportError:
        pass


def add_file(f, data: bytes, name: str, fid: str | None = None) -> dict:
    keep = fid is None
    fid = fid or uuid.uuid4().hex[:10]
    with STATE.lock:
        STATE.files[fid] = f
        STATE.raw[fid] = (name, data)
    if keep:
        STATE.envs.remember(fid, data, name, 0, name)
    return {"id": fid, "name": name, "points": len(f.points)}


def reload_env() -> list[dict]:
    """Messdateien der aktiven Umgebung neu einlesen (A2); IDs bleiben gleich."""
    with STATE.lock:
        STATE.files.clear()
        STATE.raw.clear()
    out = []
    for fid, raw, name, _idx, _n, _x in STATE.envs.stored():
        try:
            out.append(add_file(parse_bytes(raw, name), raw, name, fid))
        except Exception:  # noqa: BLE001 - unlesbare Datei überspringen
            continue
    return out


def env_bundle(stored, report: dict, lang: str) -> dict:
    """Bündel einer gespeicherten Umgebung aus ihren Messdateien und dem Berichtsauftrag der Seite
    (Körper von /api/bundle: items[{id, config}]); die aktive Umgebung bleibt unverändert."""
    from .. import bundle as bundle_mod
    by_id = {fid: (raw, name) for fid, raw, name, _i, _n, _x in stored}
    results, raw, items = [], {}, []
    _unc_ready()
    for item in report.get("items") or []:
        got = by_id.get(item.get("id"))
        if got is None:
            continue
        data, name = got
        cfg = Config.from_dict(item.get("config"))
        results.append(run(parse_bytes(data, name), cfg, STATE.alloys))
        raw[name] = data
        items.append({"name": name, "config": cfg.to_dict()})
    if not results:
        raise EnvError("Keine Messung dieser Umgebung im Berichtsstand")
    request = {"items": items, "lang": lang, "include": report.get("include") or {},
               "title": report.get("title") or None, "slug": None, "own_materials": own_used(results)}
    return bundle_mod.build(results, raw, request, lang=lang, include=request["include"], title=request["title"])


def env_default_report(stored, client: dict, _eid: str = "") -> dict | None:
    """Umgebungen, die vor dem Import aus Folio gespeichert wurden: Einstellungen je Messung stehen in client.items[id].cfg."""
    saved = (client or {}).get("items") or {}
    items = [{"id": fid, "config": (saved.get(fid) or {}).get("cfg")} for fid, *_ in stored]
    return {"items": items, "include": {}} if items else None


def _ds_open(sid: str, mode: str, version=None):
    """(Datensatz, Umschlag) einer Freigabe; live = neueste Version, pin = die genannte."""
    from labshare import Sharebox, dataset_of
    STATE.envs.ensure()
    box = Sharebox(STATE.envs.suite, STATE.envs.project)
    res = box.resolve({"id": sid, "mode": mode, "version": version}, "zugversuch")
    if res["status"] == "failed":
        raise EnvError(res.get("error") or "Datensatz nicht verfügbar")
    env = res["envelope"]
    return dataset_of(env, box.base / sid), env, res.get("latest")


def _ds_source(sid: str, env: dict, mode: str) -> dict:
    p = env.get("producer") or {}
    return {"share": sid, "title": env.get("title"), "version": env["version"], "mode": mode, "created": env.get("created"),
            "producer": {k: p.get(k) for k in ("module", "env_name", "item_name")}}


def dataset_route(action: str, req: dict) -> dict:
    """I-03: columns = Spalten mit erkannter Grösse und Vorschlag; test = Zugversuch anlegen (wie eine geladene Datei);
    refresh = einen Zugversuch aus einem Datensatz auf die neueste Version bringen (Zuordnung und Masse bleiben)."""
    from .. import dataset as ZD
    sid = str(req.get("id") or "")
    mode = "pin" if req.get("mode") == "pin" else "live"
    try:
        if action == "columns":
            ds, env, latest = _ds_open(sid, mode, req.get("version"))
            return {**ZD.columns_info(ds), "title": env.get("title"), "version": env["version"], "latest": latest}
        if action == "test":
            ds, env, latest = _ds_open(sid, mode, req.get("version"))
            raw, name, cfg = ZD.make_raw(ds, req.get("roles") or {}, req.get("geometry") or {}, _ds_source(sid, env, mode))
            f = parse_bytes(raw, name)
            out = add_file(f, raw, name)
            STATE.envs.set_extra(out["id"], dataset={"share": sid, "version": env["version"], "mode": mode})
            return {**out, "name": name[:-5], "config": cfg, "dataset": {"share": sid, "version": env["version"], "mode": mode,
                                                                        "latest": latest, "title": env.get("title")}}
        if action == "refresh":
            fid = str(req.get("file") or "")
            with STATE.lock:
                old = STATE.raw.get(fid)
            if not old:
                raise ValueError("Messung nicht geladen")
            o = getattr(STATE.files.get(fid), "origin", None)
            if not o or not o.get("share"):
                raise ValueError("Diese Messung stammt nicht aus einem Datensatz")
            d = json.loads(old[1].decode("utf-8"))
            want = req.get("version")
            ds, env, latest = _ds_open(o["share"], "pin" if want else "live", want)
            if env["version"] == o.get("version"):
                return {"changed": False, "version": env["version"], "latest": latest}
            roles = {r: (c or {}).get("key") for r, c in (d.get("roles") or {}).items()}
            raw, name, _cfg = ZD.make_raw(ds, roles, d.get("geometry") or {}, _ds_source(o["share"], env, o.get("mode") or "live"))
            f = parse_bytes(raw, old[0])
            with STATE.lock:
                STATE.files[fid] = f
                STATE.raw[fid] = (old[0], raw)
            STATE.envs.replace_raw(fid, raw, old[0])
            STATE.envs.set_extra(fid, dataset={"share": o["share"], "version": env["version"], "mode": o.get("mode") or "live"})
            return {"changed": True, "version": env["version"], "latest": latest}
        if action == "latest":                     # neueste Versionen der Datensätze der geladenen Messungen
            from labshare import Sharebox
            STATE.envs.ensure()
            box = Sharebox(STATE.envs.suite, STATE.envs.project)
            out = {}
            for fid, f in list(STATE.files.items()):
                o = getattr(f, "origin", None)
                if o and o.get("share"):
                    try:
                        out[fid] = {"version": o.get("version"), "latest": box.resolve({"id": o["share"], "mode": "live"}).get("latest"),
                                    "mode": o.get("mode"), "title": o.get("title")}
                    except (EnvError, OSError, ValueError):
                        continue
            return {"files": out}
    except ZD.DatasetTestError as e:
        raise ValueError(str(e)) from None
    raise ValueError("unbekannte Datensatzaktion")


_ENV_CACHE: dict = {}


def own_used(results) -> list[dict]:
    """Vollständige Einträge der eigenen Werkstoffe, die in Ergebnissen vorkommen (für source.request im Bundle)."""
    from ..export import charts
    rows = {x.get("name"): x for x in STATE.own.items()}
    out, seen = [], set()
    for r in results:
        used = list(charts.field_members(r)) + ([r.reference] if r.reference is not None else [])
        if r.comparison:
            by = {a.name: a for a in r.alloys}
            used += [by[row["name"]] for row in r.comparison["rows"][:6] if row["name"] in by]
        for a in used:
            if getattr(a, "own", False) and a.name not in seen and a.name in rows:
                seen.add(a.name)
                out.append(rows[a.name])
    return out


def field_extra(r) -> list[dict]:
    """Kurven für die Oberfläche, die nicht in der Hüllkurve der Gruppe stecken: zusätzlich eingeblendete Werkstoffe
    (mit Kurvennummer) und der Referenzwerkstoff, wenn er nicht zur Gruppe gehört."""
    from ..export import charts
    if r.mode != "Spannung" or r.strain is None:
        return []
    members = charts.field_members(r)
    out = []
    todo = [(len(members) - len(r.extras) + i + 1, a, "extra") for i, a in enumerate(r.extras)]
    if r.reference is not None and all(a.name != r.reference.name for a in members):
        todo.append((None, r.reference, "ref"))
    for nr, a, kind in todo:
        end = max(a.a_pct, a.curve[-1][0]) if a.curve else a.a_pct
        eps = np.linspace(0, end / 100.0, 300)
        out.append({"nr": nr, "name": a.name, "kind": kind, "own": a.own, "curve": bool(a.curve),
                    "x": eps * 100, "y": alloys_mod.ideal_curve(a, eps)})
    return _clean(out)


def envelope_payload(group: str | None = None):
    group = group or alloys_mod.DEFAULT_GROUP
    if group not in _ENV_CACHE:
        al = alloys_mod.select_group(STATE.alloys, group)
        eps, up, lo, curves = alloys_mod.envelope(al, n=600)
        _ENV_CACHE[group] = _clean({
            "group": group, "eps": eps * 100, "upper": up, "lower": lo,
            "curves": [{"name": a.name, "y": c, "own": a.own, "curve": bool(a.curve)} for a, c in zip(al, curves)],
        })
    return _ENV_CACHE[group]


def sketch_svg(r) -> str:
    """Probenskizze wie im grafischen Bericht, als SVG-Text."""
    import io

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from ..export import charts
    fig = plt.figure(figsize=(4.6, 2.0))
    ax = fig.add_axes([0.02, 0.02, 0.96, 0.96])
    try:
        charts.specimen_sketch(r, ax)
        buf = io.StringIO()
        fig.savefig(buf, format="svg", transparent=True)
    finally:
        plt.close(fig)
    svg = buf.getvalue()
    return svg[svg.find("<svg"):]


NO_SOURCE = "keine Quelle angegeben (importiert)"


def _import_source(x: dict) -> tuple[dict, bool]:
    """Quelle eines importierten eigenen Werkstoffs prüfen. Eine strukturierte Quelle muss gültig sein (sonst Fehler);
    fehlt jede Quelle, wird der Eintrag als "ohne Quelle" gekennzeichnet statt stillschweigend übernommen.
    Rückgabe: (Eintrag, gekennzeichnet)."""
    if x.get("cite"):
        if not isinstance(x["cite"], dict):
            raise ValueError("Quelle: strukturierte Angabe erwartet")
        e = labcite.errors(x["cite"])
        if e:
            raise ValueError("Quelle: " + "; ".join(e))
        x["cite"] = labcite.clean(x["cite"])
    else:
        x["cite"] = None
    src = x.get("source")
    if src is not None and not isinstance(src, str):
        raise ValueError("Quelle: Text erwartet")
    if labcite.is_record(x.get("cite")) or str(src or "").strip():
        x["no_source"] = False
        return x, False
    x["source"], x["no_source"] = NO_SOURCE, True
    return x, True


def _own_row(d: dict, a) -> dict:
    """Gespeicherte Form eines eigenen Werkstoffs: geprüfte Zahlen statt Eingabetext; aus der Kurve abgeleitete Werte
    (Rm, A, E ohne Eingabe) werden nicht gespeichert."""
    given = lambda k: d.get(k) not in (None, "")  # noqa: E731
    return {"name": a.name, "category": a.category, "rp": a.rp,
            "rm": a.rm if given("rm") else None, "a_pct": a.a_pct if given("a_pct") else None,
            "e_gpa": a.e_gpa if given("e_gpa") else None, "rm_min": a.rm_min,
            "rm_max": a.rm_max, "basis": a.basis, "cite": d.get("cite") or None,
            "source": str(d.get("source") or "").strip()[:300], "curve": a.curve, "no_source": bool(d.get("no_source"))}


def _decoded(al) -> dict:
    """Entschlüsselte Normbezeichnung je Werkstoff (labcalc.designation; fehlt das Modul, bleibt es leer)."""
    try:
        from labcalc import designation as DG
    except ImportError:
        return {}
    out = {}
    for a in al:
        if getattr(a, "own", False):
            continue
        try:
            d = DG.decode_material(a.name, "de")
        except Exception:  # noqa: BLE001 – nur ein Hinweis
            continue
        if d and d.get("found"):
            out[a.name] = d.get("summary") or d["found"][0].get("summary") or ""
    return out


def meta_payload() -> dict:
    al = STATE.alloys
    return {
        "decoded": _decoded(al),
        "shapes": SHAPES, "detents": YIELD_DETENTS, "defaults": Config().to_dict(),
        "alloys": [a.to_dict() for a in al], "categories": alloys_mod.categories(al),
        "groups": alloys_mod.groups(al), "default_group": alloys_mod.DEFAULT_GROUP,
        "manual_shape": MANUAL_SHAPE, "out_root": str(STATE.out_root),
        "own": STATE.own.items(), "own_errors": STATE.own_errors, "own_category": alloys_mod.OWN_CATEGORY,
        "equations": STATE.eqs.items(),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "FLPS/1.0"

    def log_message(self, fmt, *args):  # ruhig bleiben
        pass

    # -- Hilfen -------------------------------------------------------------------
    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    # -- GET -----------------------------------------------------------------------
    def do_GET(self):
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        if url.path in ("/labref.js", "/labenv.js", "/labindex.js", "/labui.js", "/labboard.js", "/laboverview.js", "/labimport.js",
                        "/labunc.js"):
            return self._send(200, labcite.web_asset(url.path[1:]), "text/javascript; charset=utf-8")
        if url.path == "/api/meta":
            return self._json(meta_payload())
        if url.path == "/api/envelope":
            q = parse_qs(url.query)
            return self._json(envelope_payload(q.get("group", [None])[0]))
        self._send(404, b"nicht gefunden", "text/plain")

    # -- POST ----------------------------------------------------------------------
    def do_POST(self):
        url = urlparse(self.path)
        origin = self.headers.get("Origin")
        if origin and not re.match(r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$", origin):
            n = int(self.headers.get("Content-Length") or 0)
            if 0 < n <= 1 << 20:
                self.rfile.read(n)                       # read the small body so the answer arrives cleanly
            return self._json({"error": "Fremde Herkunft abgelehnt"}, 403)
        try:
            if url.path == "/api/load":
                q = parse_qs(url.query)
                name = unquote(q.get("name", ["Messung.flps"])[0])
                data = self._body()
                try:
                    f = parse_bytes(data, name)
                except (FlpsError, Exception) as e:  # noqa: BLE001
                    return self._json({"error": f"{name}: keine lesbare .flps Datei ({e})"}, 400)
                return self._json(add_file(f, data, name))
            if url.path == "/api/remove":
                req = json.loads(self._body() or b"{}")
                with STATE.lock:
                    STATE.files.pop(req.get("id"), None)
                    STATE.raw.pop(req.get("id"), None)
                STATE.envs.forget(str(req.get("id")))
                return self._json({"ok": True})
            if url.path.startswith("/api/env/"):
                req = json.loads(self._body() or b"{}")
                try:
                    return self._json(STATE.envs.route(url.path.rsplit("/", 1)[1], req, reload_env))
                except EnvError as e:
                    return self._json({"error": str(e)}, 400)
            if url.path.startswith("/api/index/") or url.path.startswith("/api/prov/"):   # A7/A8: Projektindex, Herkunft
                import labindex
                import labprov
                from .. import __version__ as flps_version
                req = json.loads(self._body() or b"{}")
                act = url.path.rsplit("/", 1)[1]
                if url.path.startswith("/api/index/"):
                    return self._json(labindex.route(STATE.envs, "zugversuch", flps_version, act, req))
                return self._json(labprov.route(STATE.envs, act, req))
            if url.path.startswith("/api/unc/"):          # Messunsicherheit: Messmittel, Vorschau, Verfahren (labunc)
                import labunc
                req = json.loads(self._body() or b"{}")
                try:
                    return self._json(labunc.route(STATE.envs, url.path.rsplit("/", 1)[1], req))
                except EnvError as e:
                    return self._json({"error": str(e)}, 400)
            if url.path == "/api/unccompare":              # alle vier Verfahren für einen Kennwert
                from .. import uncertainty as unc_mod
                req = json.loads(self._body() or b"{}")
                f = STATE.files.get(req.get("id"))
                if f is None:
                    return self._json({"error": "Datei nicht geladen"}, 404)
                _unc_ready()
                r = run(f, Config.from_dict(req.get("config")), STATE.alloys)
                return self._json(_clean(unc_mod.compare(r, str(req.get("name") or "Rm"), req.get("lang"))))
            if url.path == "/api/analyse":
                req = json.loads(self._body() or b"{}")
                f = STATE.files.get(req.get("id"))
                if f is None:
                    return self._json({"error": "Datei nicht geladen"}, 404)
                _unc_ready()
                cfg = Config.from_dict(req.get("config"))
                r = run(f, cfg, STATE.alloys)
                d = result_to_dict(r)
                d["id"] = req.get("id")
                d["series"]["dev"] = _clean(r.fit.k * r.t + r.fit.q - r.y)
                d["field_extra"] = field_extra(r)
                try:
                    d["sketch_svg"] = sketch_svg(r)
                except Exception:  # noqa: BLE001 - Skizze ist Beiwerk
                    traceback.print_exc()
                    d["sketch_svg"] = ""
                return self._json(d)
            if url.path in ("/api/bundle", "/api/bundle/rebuild"):
                # Ergebnisse fuer den Berichtseditor (Folio Lab). /rebuild bekommt die Quelldateien mitgeliefert.
                import base64

                from .. import bundle as bundle_mod
                req = json.loads(self._body() or b"{}")
                results, raw, items = [], {}, []
                stored = None
                _unc_ready()
                if url.path == "/api/bundle":
                    for item in req.get("items", []):
                        f = STATE.files.get(item.get("id"))
                        if f is None:
                            return self._json({"error": "Datei nicht geladen"}, 404)
                        name, data = STATE.raw[item["id"]]
                        cfg = Config.from_dict(item.get("config"))
                        results.append(run(f, cfg, STATE.alloys))
                        raw[name] = data
                        items.append({"name": name, "config": cfg.to_dict()})
                        o = getattr(f, "origin", None)
                        if o and o.get("share"):           # I-03: Herkunftskette hält die benutzte Version fest
                            items[-1]["dataset"] = {"share": o["share"], "version": o.get("version"), "mode": o.get("mode")}
                else:
                    src = req.get("source") or {}
                    files = {k: base64.b64decode(v) for k, v in (src.get("files") or {}).items()}
                    stored = (src.get("request") or {}).get("own_materials") or None
                    al = STATE.alloys_with(stored)
                    for item in (src.get("request") or {}).get("items", []):
                        data = files.get(item["name"])
                        if data is None:
                            return self._json({"error": f"Quelldatei {item['name']} fehlt im Bundle"}, 400)
                        results.append(run(parse_bytes(data, item["name"]), Config.from_dict(item.get("config")), al))
                        raw[item["name"]] = data
                        items.append(item)
                    old = src.get("request") or {}
                    req = {**old, **{k: v for k, v in req.items() if k != "source"}}
                if not results:
                    return self._json({"error": "Keine Messung gewählt."}, 400)
                request = {"items": items, "lang": req.get("lang", "de"), "include": req.get("include") or {},
                           "title": req.get("title") or None, "slug": req.get("slug") or None,
                           "own_materials": stored if stored is not None else own_used(results)}
                # the hub's figure styles and the describe request for its editing window pass through (labbundle)
                for k in ("styles", "describe_figures", "preview"):
                    if k in req:
                        request[k] = req[k]
                try:
                    b = bundle_mod.build(results, raw, request, lang=request["lang"], include=request["include"],
                                         title=request["title"])
                except ValueError as e:
                    return self._json({"error": str(e)}, 400)
                return self._json(b)
            if url.path == "/api/compare_report":
                from ..export import write_comparison
                req = json.loads(self._body() or b"{}")
                results = []
                _unc_ready()
                for item in req.get("items", []):
                    f = STATE.files.get(item.get("id"))
                    if f is None:
                        return self._json({"error": "Datei nicht geladen"}, 404)
                    results.append(run(f, Config.from_dict(item.get("config")), STATE.alloys))
                if len(results) < 2:
                    return self._json({"error": "Für einen Vergleichsbericht mindestens zwei Messungen laden."}, 400)
                try:
                    path = write_comparison(results, STATE.out_root, overwrite=bool(req.get("overwrite")))
                except FileExistsError as e:
                    return self._json({"exists": True, "file": str(e)}, 409)
                except ValueError as e:
                    return self._json({"error": str(e)}, 400)
                return self._json({"file": str(path), "folder": str(path.parent)})
            if url.path == "/api/export":
                from ..export import output_folder, write_all
                req = json.loads(self._body() or b"{}")
                f = STATE.files.get(req.get("id"))
                if f is None:
                    return self._json({"error": "Datei nicht geladen"}, 404)
                cfg = Config.from_dict(req.get("config"))
                _unc_ready()
                r = run(f, cfg, STATE.alloys)
                folder = output_folder(r, STATE.out_root)
                try:
                    files = write_all(r, STATE.out_root, overwrite=bool(req.get("overwrite")))
                except FileExistsError:
                    return self._json({"exists": True, "folder": str(folder)}, 409)
                return self._json({"folder": str(folder), "files": [p.name for p in files]})
            if url.path.startswith("/api/dataset/"):   # I-03: ganzer Zugversuch aus einem Datensatz
                req = json.loads(self._body() or b"{}")
                try:
                    return self._json(_clean(dataset_route(url.path.rsplit("/", 1)[1], req)))
                except EnvError as e:
                    return self._json({"error": str(e)}, 400)
            if url.path.startswith("/api/own/"):
                return self._own(url.path.rsplit("/", 1)[1])
            if url.path.startswith("/api/equations/"):
                return self._equations(url.path.rsplit("/", 1)[1])
            if url.path == "/api/open":
                req = json.loads(self._body() or b"{}")
                p = Path(req.get("folder", ""))
                if p.exists() and STATE.out_root.resolve() in p.resolve().parents and hasattr(os, "startfile"):
                    os.startfile(str(p))  # noqa: S606 - nur Ordner unterhalb des Ausgabeordners
                return self._json({"ok": True})
        except ValueError as e:
            return self._json({"error": str(e)}, 400)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)
        self._send(404, b"nicht gefunden", "text/plain")

    # -- Eigene Werkstoffe -------------------------------------------------------------
    def _own(self, action):
        S = STATE.own
        if action == "list":
            return self._json({"items": S.items(), "errors": STATE.own_errors})
        req = json.loads(self._body() or b"{}")
        if action == "save":
            d = dict(req.get("item") or {})
            if d.get("cite"):
                e = labcite.errors(d["cite"])
                if e:
                    raise ValueError("Quelle: " + "; ".join(e))
                d["cite"] = labcite.clean(d["cite"])
            if not labcite.is_record(d.get("cite")) and str(d.get("source") or "").strip() in ("", NO_SOURCE):
                raise ValueError("Quelle fehlt: bitte angeben, woher die Kennwerte stammen (DOI, Datenblatt, Norm …)")
            d["no_source"] = False
            a = alloys_mod.own_from_dict(d)          # prüft die Werte
            taken = {x.name for x in STATE.builtin} | {x.get("name") for x in S.items() if x.get("id") != d.get("id")}
            if a.name in taken:
                raise ValueError(f"„{a.name}“ gibt es schon. Bitte einen eindeutigen Namen wählen.")
            item = S.put({"id": d.get("id"), **_own_row(d, a)})
            STATE.rebuild()
            return self._json({"item": item, "items": S.items(), "meta": meta_payload()})
        if action == "delete":
            S.delete(req.get("id"))
            STATE.rebuild()
            return self._json({"items": S.items(), "meta": meta_payload()})
        if action == "export":
            return self._json({"text": json.dumps(S.export(), ensure_ascii=False, indent=1),
                               "filename": "eigene_werkstoffe.json", "mime": "application/json"})
        if action == "import":
            data = req.get("data") or {}
            rows = data.get("items") if isinstance(data, dict) else data
            if not isinstance(rows, list):
                raise ValueError("Import: Liste von Werkstoffen erwartet")
            have = {x.name for x in STATE.builtin} | ({x.get("name") for x in S.items()} if not req.get("replace") else set())
            ok, skipped, no_source = [], [], []
            for x in rows:
                if not isinstance(x, dict):
                    skipped.append("Eintrag ohne Felder übersprungen")
                    continue
                try:
                    x, flagged = _import_source(dict(x))      # Quelle prüfen, fehlende kennzeichnen
                    a = alloys_mod.own_from_dict(x)            # prüft die Zahlenwerte
                except ValueError as e:
                    skipped.append(f"{x.get('name') or '?'}: {e}")
                    continue
                if a.name in have:
                    skipped.append(f"{a.name}: Name schon vorhanden")
                    continue
                have.add(a.name)
                if flagged:
                    no_source.append(a.name)
                ok.append(_own_row(x, a))
            n = S.import_(ok, bool(req.get("replace")))
            STATE.rebuild()
            return self._json({"added": n, "skipped": skipped, "no_source": no_source, "items": S.items(),
                               "meta": meta_payload()})
        return self._send(404, b"nicht gefunden", "text/plain")

    # -- Eigene Gleichungen ------------------------------------------------------------
    def _equations(self, action):
        from labcalc import formulas as F
        S = STATE.eqs
        if action == "list":
            return self._json({"items": S.items()})
        req = json.loads(self._body() or b"{}")
        if action == "save":
            d = F.clean_defs([req.get("item") or {}])
            if not d:
                raise ValueError("Gleichung leer")
            x = d[0]
            err = F.check_name(x["sym"])
            if err:
                raise ValueError(err)
            if x.get("source"):
                e = labcite.errors(x["source"])
                if e:
                    raise ValueError("Quelle: " + "; ".join(e))
                x["source"] = labcite.clean(x["source"])
            x["id"] = (req.get("item") or {}).get("id")
            return self._json({"item": S.put(x), "items": S.items()})
        if action == "delete":
            S.delete(req.get("id"))
            return self._json({"items": S.items()})
        if action == "export":
            return self._json({"text": json.dumps(S.export(), ensure_ascii=False, indent=1),
                               "filename": "eigene_gleichungen.json", "mime": "application/json"})
        if action == "import":
            n = S.import_(req.get("data") or {}, bool(req.get("replace")))
            return self._json({"added": n, "items": S.items()})
        return self._send(404, b"nicht gefunden", "text/plain")


def main(argv=None):
    global STATE
    ap = argparse.ArgumentParser(description="FLPS Auswerte-App, lokale Oberfläche")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--aus", default=str(ROOT / "Ausgaben"), help="Wurzelordner der Ausgaben")
    ap.add_argument("--legierungen", help="eigene Werkstoffdatei (Format des früheren alloys.json) statt der gemeinsamen Werkstoffdatenbank")
    ap.add_argument("--kein-browser", action="store_true")
    a = ap.parse_args(argv)
    STATE = State(Path(a.aus).resolve(), a.legierungen)
    STATE.envs.env_bundle = env_bundle
    STATE.envs.env_default_report = env_default_report
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = f"http://127.0.0.1:{a.port}/"
    print(f"FLPS Auswerte-App läuft auf {url}  (Beenden mit Strg+C)")
    print(f"Ausgaben gehen nach {STATE.out_root}")
    if not a.kein_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
