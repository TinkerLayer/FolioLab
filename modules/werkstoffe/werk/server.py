"""Lokale Oberfläche des Werkstoffe-Moduls.

Läuft nur auf 127.0.0.1 und ruft nichts aus dem Netz ab. Geladene Dateien (Diffraktogramme, CIF, Tabellen) bleiben
im Speicher und in der aktiven Umgebung des Projekts.

Start:  python -m werk.server  [--port 8775] [--aus Ausgaben] [--kein-browser]
"""
from __future__ import annotations

import argparse
import base64
import json
import math
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

_SDK = Path(__file__).resolve().parents[3] / "sdk" / "python"
if _SDK.is_dir() and str(_SDK) not in sys.path:
    sys.path.insert(0, str(_SDK))

import labcite  # noqa: E402
from labproject import EnvError, ModuleEnvs  # noqa: E402

from . import __version__  # noqa: E402
from . import cryst as C  # noqa: E402
from . import tools as T  # noqa: E402
from . import xrdio as IO  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
ROOT = Path(__file__).resolve().parents[1]
ORIGIN_OK = re.compile(r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$")
KINDS = ("xrd", "cif", "table", "hardtable")
MAX_FILE = 60 * 1024 * 1024


class State:
    def __init__(self, out_root: Path):
        self.items: dict = {}          # iid -> {"kind", "name", "obj"}
        self.raw: dict = {}            # iid -> Rohdaten
        self.lock = threading.Lock()
        self.out_root = out_root
        self.envs = ModuleEnvs(out_root, "werkstoffe")

    def ctx(self) -> T.Ctx:
        with self.lock:
            return T.Ctx(dict(self.items))


STATE: State | None = None


def guess_kind(name: str) -> str:
    n = name.lower()
    if n.endswith(".cif"):
        return "cif"
    if n.endswith(IO.EXT) and not n.endswith((".csv", ".txt")):
        return "xrd"
    return "table"


def decode_text(data: bytes) -> str:
    import labtable
    return labtable.decode(data)


def parse_item(data: bytes, name: str, kind: str):
    """Datei -> Objekt des Werkzeugs; ValueError mit verständlicher Meldung."""
    if kind == "xrd":
        return IO.load(data, name)
    if kind == "cif":
        return C.parse_cif(decode_text(data))
    if kind in ("table", "hardtable"):
        text = decode_text(data)
        if kind == "hardtable":
            from .hardness import parse_table
            parse_table(text)                               # prüft das Format
        else:
            T.parse_table_text(text)
        return text
    raise ValueError(f"Dateiart {kind} unbekannt")


def describe(iid: str, it: dict) -> dict:
    d = {"id": iid, "kind": it["kind"], "name": it["name"]}
    o = it["obj"]
    if it["kind"] == "xrd":
        d.update(o.describe())
    elif it["kind"] == "cif":
        d.update({"phase": o.get("name"), "formula": o.get("formula", ""), "system": o.get("system"),
                  "cell": o.get("cell"), "phase_id": "cif:" + iid})
    else:
        d["lines"] = o.count("\n") + 1
    return d


def add_item(data: bytes, name: str, kind: str, iid: str | None = None) -> dict:
    keep = iid is None
    obj = parse_item(data, name, kind)
    iid = iid or uuid.uuid4().hex[:10]
    with STATE.lock:
        STATE.items[iid] = {"kind": kind, "name": name, "obj": obj}
        STATE.raw[iid] = data
    if keep:
        STATE.envs.remember(iid, data, name, 0, name, kind=kind)
    return describe(iid, STATE.items[iid])


def build_from(req: dict, items: dict, raws: dict) -> dict:
    """Bündel aus dem Berichtsauftrag der Seite und geladenen Einträgen {iid: {kind, name, obj}} mit Rohdaten."""
    from . import bundle as B
    used = B.used_items(req.get("sections") or [])
    files, finfo = {}, []
    for iid in used:
        it = items.get(iid)
        if it is None:
            raise T.ToolError("Eine verwendete Datei ist nicht mehr geladen")
        # flacher Name: der Hub nimmt in source.files keine Ordner an (lab.js: ohne \ / : * ? " < > |, ≤ 120)
        key = re.sub(r'[\\/:*?"<>|]', "_", f"{iid}-{it['name']}")[:120]
        files[key] = raws[iid]
        finfo.append({"id": iid, "name": it["name"], "kind": it["kind"], "file": key})
    request = {"sections": req.get("sections") or [], "files": finfo, "lang": req.get("lang", "de"),
               "include": req.get("include") or {}, "title": req.get("title") or None,
               "slug": req.get("slug") or None}
    if not request["sections"]:
        raise T.ToolError("Nichts für den Bericht gewählt.")
    return B.build(request, T.Ctx(items), files)


def env_bundle(stored, report: dict, lang: str) -> dict:
    """Bündel einer gespeicherten Umgebung (nicht der aktiven) aus ihren Dateien und dem Berichtsauftrag."""
    items, raws = {}, {}
    for iid, raw, fname, _idx, _name, extra in stored:
        kind = (extra or {}).get("kind") or guess_kind(fname)
        try:
            items[iid] = {"kind": kind, "name": fname, "obj": parse_item(raw, fname, kind)}
            raws[iid] = raw
        except ValueError:
            continue
    return build_from({**report, "lang": lang}, items, raws)


def reload_env() -> list[dict]:
    with STATE.lock:
        STATE.items.clear()
        STATE.raw.clear()
    out = []
    for iid, raw, fname, _idx, _name, extra in STATE.envs.stored():
        kind = (extra or {}).get("kind") or guess_kind(fname)
        try:
            out.append(add_item(raw, fname, kind, iid))
        except ValueError:
            continue
    return out


def clean(o):
    """JSON-tauglich: NaN/inf -> None, numpy -> Python."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return clean(o.tolist())
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, (float, np.floating)):
        f = float(o)
        return f if math.isfinite(f) else None
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def meta_payload(lang: str = "de") -> dict:
    from . import select as SL
    from . import phasediag as PD
    from . import fatigue as FT
    from . import gitter as GT
    from . import struktur as SK
    from . import gefuege as GF
    from . import kompendium as KP
    from labcalc import materials as M

    from . import corrcreep as CC
    plies = []
    for r in M.materials():
        if r.get("_teil") == "materials_mp":
            continue
        try:
            if M.value(r, "E1").get("si"):
                plies.append(M.summary(r, lang)["name"])
        except M.MatError:
            continue
    return {
        "plies": plies,
        "metals": sorted(CC.VALENCE),
        "version": __version__,
        "infoboard": True,
        "out_root": str(STATE.out_root),
        "tools": list(T.DISPATCH),
        "groups": KP.data()["groups"],
        "names": KP.data()["tools"],
        "tubes": {k: list(v) for k, v in C.TUBES.items()},
        "props": SL.props(lang),
        "props_en": SL.props("en"),
        "indices": {k: {"de": v[0], "en": v[1], "expo": v[2]} for k, v in SL.INDICES.items()},
        "classes": {k: {"de": v[0], "en": v[1]} for k, v in M.CLASSES.items()},
        "families": {k: {"de": v[0], "en": v[1]} for k, v in SL.FAMILY_NAMES.items()},
        "gitter": {"hosts": GT.hosts(lang), "solutes": GT.solute_list(), "examples": GT.examples("de"),
                   "examples_en": GT.examples("en")},
        "struktur": {"de": SK.materials("de"), "en": SK.materials("en")},
        "gefuege": {lg: {"atlas": [{"id": c["id"], "name": c["name"], "family": c["family"]} for c in GF.catalog(lg == "de")],
                         "mech": [{"id": k, "name": m["name"][0 if lg == "de" else 1], "kind": m["kind"]} for k, m in GF.MECHANISMS.items()]}
                    for lg in ("de", "en")},
        "systems": PD.systems("de"),
        "systems_en": PD.systems("en"),
        "mean_models": list(FT.MEAN_MODELS),
        "surfaces": list(FT.SURFACE),
        "kinds": list(KINDS),
        "accepts": list(IO.EXT) + [".cif"],
        "has_mp": any(r.get("_teil") == "materials_mp" for r in M.materials()),
        "items": [describe(k, v) for k, v in STATE.items.items()],
    }


# ----------------------------------------------------------------------------- Datensatz
def _ds_open(sid: str, mode: str, version=None):
    from labshare import Sharebox, dataset_of
    STATE.envs.ensure()
    box = Sharebox(STATE.envs.suite, STATE.envs.project)
    res = box.resolve({"id": sid, "mode": mode, "version": version}, "werkstoffe")
    if res["status"] == "failed":
        raise EnvError(res.get("error") or "Datensatz nicht verfügbar")
    env = res["envelope"]
    return dataset_of(env, box.base / sid), env, res.get("latest")


def dataset_route(action: str, req: dict) -> dict:
    """columns = Spalten eines freigegebenen Datensatzes; table = Werte (in SI oder Originaleinheit) als Zeilen."""
    from labdataset import DatasetError
    sid = str(req.get("id") or "")
    mode = "pin" if req.get("mode") == "pin" else "live"
    try:
        ds, env, latest = _ds_open(sid, mode, req.get("version"))
        cols = [{"key": c.key, "name": c.name, "unit": c.unit, "dtype": c.dtype} for c in ds.columns]
        if action == "columns":
            return {"columns": cols, "title": env.get("title"), "version": env["version"], "latest": latest,
                    "rows": ds.rows}
        if action == "table":
            keys = [k for k in (req.get("keys") or [c["key"] for c in cols]) if any(c["key"] == k for c in cols)]
            out = {}
            for k in keys:
                try:
                    out[k] = [None if v is None else float(v) for v in ds.values(k, True)]
                except (TypeError, ValueError):
                    out[k] = [None if v is None else str(v) for v in ds.values(k, True)]
            return {"columns": [c for c in cols if c["key"] in keys], "values": out, "title": env.get("title"),
                    "version": env["version"], "latest": latest}
    except DatasetError as e:
        raise T.ToolError(str(e)) from None
    raise LookupError("Unbekannte Aktion")


# ----------------------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "FolioWerkstoffe/1.0"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code: int, body: bytes, ctype: str, headers: dict | None = None):
        if self.command == "POST" and not getattr(self, "_read", False):
            # Read an unread request body before answering (403/400 before the upload was read): otherwise Windows
            # resets the connection and the client sees an error instead of the answer.
            n = int(self.headers.get("Content-Length") or 0)
            if 0 < n <= MAX_FILE:
                self.rfile.read(n)
            self._read = True
            if n > MAX_FILE:
                self.close_connection = True
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, str(v))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200):
        self._send(code, json.dumps(clean(obj), ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_FILE:
            raise T.ToolError("Datei ist zu gross")
        self._read = True
        return self.rfile.read(n) if n else b""

    def _req(self) -> dict:
        return json.loads(self._body() or b"{}")

    def do_GET(self):
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        if url.path == "/api/meta":
            return self._json(meta_payload())
        if url.path in ("/labenv.js", "/labindex.js", "/labui.js", "/labboard.js", "/laboverview.js", "/labimport.js", "/labunc.js"):
            return self._send(200, labcite.web_asset(url.path[1:]), "text/javascript; charset=utf-8")
        if url.path == "/infoboard.js":
            return self._send(200, (STATIC / "infoboard.js").read_bytes(), "text/javascript; charset=utf-8")
        self._send(404, b"nicht gefunden", "text/plain")

    def do_POST(self):
        self._read = False
        url = urlparse(self.path)
        origin = self.headers.get("Origin")
        if origin and not ORIGIN_OK.match(origin):
            return self._json({"error": "Fremde Herkunft abgelehnt"}, 403)   # _send reads the unread body first
        try:
            return self._route(url)
        except T.ERRORS + (EnvError,) as e:
            return self._json({"error": str(e)}, 400)
        except LookupError as e:
            return self._json({"error": str(e)}, 404)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    def _route(self, url):
        p = url.path
        if p == "/api/load":
            q = parse_qs(url.query)
            name = unquote(q.get("name", ["Datei.txt"])[0])
            kind = q.get("kind", [""])[0] or guess_kind(name)
            if kind not in KINDS:
                return self._json({"error": f"Dateiart {kind} unbekannt"}, 400)
            data = self._body()
            try:
                return self._json(add_item(data, name, kind))
            except ValueError as e:
                return self._json({"error": str(e)}, 400)
        if p == "/api/remove":
            iid = str(self._req().get("id"))
            with STATE.lock:
                STATE.items.pop(iid, None)
                STATE.raw.pop(iid, None)
            STATE.envs.forget(iid)
            return self._json({"ok": True})
        if p == "/api/items":
            return self._json({"items": [describe(k, v) for k, v in STATE.ctx().items.items()]})
        if p.startswith("/api/tool/"):
            name = p.rsplit("/", 1)[1]
            req = self._req()
            if req.get("unc"):                              # eigene Messmittel der Suite für die Unsicherheit
                import labunc
                labunc.load_own(STATE.envs)
            return self._json(T.run(name, req, STATE.ctx()))
        if p.startswith("/api/env/"):
            return self._json(STATE.envs.route(p.rsplit("/", 1)[1], self._req(), reload_env))
        if p.startswith("/api/index/"):
            import labindex
            return self._json(labindex.route(STATE.envs, "werkstoffe", __version__, p.rsplit("/", 1)[1], self._req()))
        if p.startswith("/api/prov/"):
            import labprov
            return self._json(labprov.route(STATE.envs, p.rsplit("/", 1)[1], self._req()))
        if p.startswith("/api/unc/"):                       # Messunsicherheit (Runde U)
            import labunc
            return self._json(labunc.route(STATE.envs, p.rsplit("/", 1)[1], self._req()))
        if p.startswith("/api/dataset/"):
            return self._json(dataset_route(p.rsplit("/", 1)[1], self._req()))
        if p.startswith("/api/infoboard/"):                 # Infotafel: je Projekt gespeichert
            from . import infoboard as IB
            return self._json(IB.route(STATE.envs, p.rsplit("/", 1)[1], self._req()))
        if p in ("/api/bundle", "/api/bundle/rebuild"):
            return self._bundle(p)
        return self._send(404, b"nicht gefunden", "text/plain")

    def _bundle(self, p):
        from . import bundle as B
        req = self._req()
        if p == "/api/bundle":
            ctx = STATE.ctx()
            try:
                b = build_from(req, ctx.items, STATE.raw)
            except T.ERRORS as e:
                return self._json({"error": str(e)}, 400)
            return self._json(b)
        else:
            src = req.get("source") or {}
            raw = {k: base64.b64decode(v) for k, v in (src.get("files") or {}).items()}
            old = src.get("request") or {}
            items = {}
            for f in old.get("files") or []:
                data = raw.get(f["file"])
                if data is None:
                    return self._json({"error": f"Quelldatei {f['name']} fehlt im Bundle"}, 400)
                try:
                    items[f["id"]] = {"kind": f["kind"], "name": f["name"], "obj": parse_item(data, f["name"], f["kind"])}
                except ValueError as e:
                    return self._json({"error": f"{f['name']}: {e}"}, 400)
            ctx = T.Ctx(items)
            files = raw
            request = {**old, **{k: v for k, v in req.items() if k != "source"}}
        if not request.get("sections"):
            return self._json({"error": "Nichts für den Bericht gewählt."}, 400)
        try:
            b = B.build(request, ctx, files)
        except T.ERRORS as e:
            return self._json({"error": str(e)}, 400)
        return self._json(b)


def main(argv=None):
    global STATE
    ap = argparse.ArgumentParser(description="Werkstoffe, lokale Oberfläche")
    ap.add_argument("--port", type=int, default=8775)
    ap.add_argument("--aus", default=str(ROOT / "Ausgaben"), help="Wurzelordner der Ausgaben")
    ap.add_argument("--kein-browser", action="store_true")
    a = ap.parse_args(argv)
    STATE = State(Path(a.aus).resolve())
    STATE.envs.env_bundle = env_bundle
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = f"http://127.0.0.1:{a.port}/"
    print(f"Werkstoffe läuft auf {url}  (Beenden mit Strg+C)")
    if not a.kein_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
