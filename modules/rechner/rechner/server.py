"""Lokale Oberflaeche des Rechners.

Laeuft nur auf 127.0.0.1, ruft nichts aus dem Netz ab und speichert nichts: den Arbeitsstand haelt die Seite
(Browser-Speicher oder JSON-Datei) und schickt ihn bei jeder Anfrage mit.

Start:  python -m rechner.server  [--port 8767] [--aus Ausgaben] [--kein-browser]
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import numpy as np

_SDK = Path(__file__).resolve().parents[3] / "sdk" / "python"
if _SDK.is_dir() and str(_SDK) not in sys.path:
    sys.path.insert(0, str(_SDK))

import labcite  # noqa: E402
from labcalc import fitting as FIT  # noqa: E402
from labproject import EnvError, ModuleEnvs  # noqa: E402

from . import __version__
from . import console as CON
from . import expr as E
from . import library as L
from . import plots as P
from . import solver as S
from . import units as U

STATIC = Path(__file__).resolve().parent / "static"
ROOT = Path(__file__).resolve().parents[1]
ORIGIN_OK = re.compile(r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$")
_META = None


def clean(o):
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


def materials_payload(lang: str = "de") -> dict:
    """Alle Werkstoffe (Kurzform), Klassen, Eigenschaften und Diffusionspaare für die Auswahl in der Bibliothek."""
    from labcalc import materials as MAT
    i = 0 if lang == "de" else 1
    return {"items": [MAT.summary(r, lang) for r in MAT.materials()],
            "classes": [{"key": k, "label": v[i]} for k, v in MAT.CLASSES.items()],
            "props": [{"key": k, "kind": v[0], "unit": v[1], "label": v[2 + i]} for k, v in MAT.PROPS.items()],
            "diffusion": [{"species": d["teilchen"], "host": d["wirt"]} for d in MAT._db()["diffusion"]],
            "shortcuts": MAT.SHORTCUTS}


def meta_payload() -> dict:
    global _META
    if _META is None:
        cats = []
        for e in L.EQUATIONS:
            c = next((c for c in cats if c["name"] == e.cat), None)
            if c is None:
                c = {"name": e.cat, "en": L.CATEGORY_EN.get(e.cat, e.cat), "subs": []}
                cats.append(c)
            s = next((s for s in c["subs"] if s["name"] == e.sub), None)
            if s is None:
                s = {"name": e.sub, "eqs": []}
                c["subs"].append(s)
            s["eqs"].append(e.id)
        _META = {
            "version": __version__,
            "kinds": [k.to_dict() for k in U.KINDS.values() if not k.key.startswith("dim:")],
            "constants": U.constants_list(),
            "functions": E.FUNC_DOC,
            "equations": L.library_dict(),
            "categories": cats,
            "symbols": L.symbols_list(),
            "fits": {k: v[0] for k, v in P.FIT_MODELS.items()},
            "fitmodels": [{"key": k, "de": v[0], "en": v[1], "formula": v[2], "params": v[3], "lin": v[4]}   # G-02
                          for k, v in FIT.MODELS.items()],
        }
    return _META


ENVS: ModuleEnvs | None = None
MAX_DS_COLS = 20
_DS_ARR: dict = {}                    # (Freigabe, Version, Prüfsumme) -> Zahlenspalten; Versionen ändern sich nie
_DS_LOCK = threading.Lock()


def ds_resolve(spec: dict) -> dict:
    """G-01: Datensatz für die Grafik lesen (Zahlenspalten, ausgeschlossene Zeilen als NaN), zwischengespeichert."""
    from labshare import Sharebox

    from . import dsvars as DV
    if ENVS is None:
        raise EnvError("Keine Projektumgebung – Datensätze sind hier nicht lesbar")
    ENVS.ensure()
    box = Sharebox(ENVS.suite, ENVS.project)
    sid = str(spec.get("id") or "")
    mode = "pin" if spec.get("mode") == "pin" else "live"
    res = box.resolve({"id": sid, "mode": mode, "version": spec.get("version")}, "rechner")
    if res["status"] == "failed":
        raise EnvError(res.get("error") or "Datensatz nicht verfügbar")
    env = res["envelope"]
    key = (str(box.base), sid, env.get("version"), env.get("hash"))
    with _DS_LOCK:
        hit = _DS_ARR.pop(key, None)
    if hit is None:
        ds = DV._dataset(box, sid, env)
        used = ds.used_mask()
        cols = {}
        for c in ds.columns:
            if c["dtype"] != "number":
                continue
            a = np.array(ds.values(c["key"]), dtype=float)
            a[~used] = np.nan
            cols[c["key"]] = a
        hit = {"rows": ds.rows, "columns": [{f: c.get(f) for f in ("key", "name", "unit", "dtype", "role", "kind")} for c in ds.columns],
               "cols": cols}
    with _DS_LOCK:
        _DS_ARR[key] = hit
        while len(_DS_ARR) > 4:
            _DS_ARR.pop(next(iter(_DS_ARR)))
    p = env.get("producer") or {}
    return {**hit, "title": env.get("title"), "version": env["version"], "latest": res["latest"], "status": res["status"],
            "producer": {k: p.get(k) for k in ("module", "env_name", "item_name")}}


from . import graph as _G  # noqa: E402

_G.DATASETS = ds_resolve


class _NoEnvs:
    """Ohne Projektumgebung (Einzelstart ohne --aus, Tests): eingebaute Messmittel ja, eigene nicht."""

    def ensure(self):
        raise EnvError("Keine Projektumgebung – eigene Messmittel sind hier nicht verfügbar")


def unc_envs():
    return ENVS if ENVS is not None else _NoEnvs()


def load_own_instruments():
    """Eigene Messmittel der Suite für die Auswertung bekannt machen (Eingaben dürfen sie nennen)."""
    import labunc
    labunc.load_own(unc_envs())


def dataset_route(req: dict) -> dict:
    """DP-M6: datasets (`data.table`) addressed to the Rechner – list them, or read chosen columns of one version.
    mode live = newest version, pin = the version given (an update is offered when a newer one exists)."""
    import math
    from labshare import DATA_KIND, Sharebox, dataset_of
    ENVS.ensure()
    box = Sharebox(ENVS.suite, ENVS.project)
    if req.get("list"):
        out = []
        for m in box.list("rechner", DATA_KIND):
            try:
                env = box.get(m["id"], None, "rechner")
            except EnvError:
                continue
            h, p = env.get("dataset") or {}, m.get("producer") or {}
            out.append({"id": m["id"], "title": m.get("title"), "latest": m.get("latest"), "modified": m.get("modified"),
                        "rows": h.get("rows"), "derived": bool(m.get("derive")),
                        "producer": {k: p.get(k) for k in ("module", "env_name", "item_name")},
                        "columns": [{k: c.get(k) for k in ("key", "name", "unit", "dtype", "role", "kind")} for c in h.get("columns") or []]})
        return {"datasets": out}
    sid = str(req.get("id") or "")
    mode = "pin" if req.get("mode") == "pin" else "live"
    res = box.resolve({"id": sid, "mode": mode, "version": req.get("version")}, "rechner")
    if res["status"] == "failed":
        raise EnvError(res.get("error") or "Datensatz nicht verfügbar")
    env = res["envelope"]
    if req.get("meta"):                                # G-01: nur Spalten und Wertebereiche, die Werte liest die Grafik selbst
        d = ds_resolve({"id": sid, "mode": mode, "version": req.get("version")})
        ext = {}
        for k, a in d["cols"].items():
            f = a[np.isfinite(a)]
            ext[k] = [float(f.min()), float(f.max()), int(f.size)] if f.size else None
        return {"id": sid, "title": d["title"], "version": d["version"], "latest": d["latest"], "status": d["status"],
                "rows": d["rows"], "columns": [{f: c.get(f) for f in ("key", "name", "unit", "dtype", "role")} for c in d["columns"]],
                "ext": ext, "producer": d["producer"]}
    ds = dataset_of(env, box.base / sid)
    used = ds.used_mask()
    keys =[k for k in (req.get("keys") or []) if isinstance(k, str)][:MAX_DS_COLS] or [c["key"] for c in ds.columns][:MAX_DS_COLS]
    cols = []
    for k in keys:
        try:
            c = ds.col(k)
        except ValueError as e:                        # column gone in a newer version
            raise EnvError(str(e)) from None
        vals = ds.values(k)
        if c["dtype"] == "number":
            v = [None if not (u and math.isfinite(x)) else x for x, u in zip(vals.tolist(), used.tolist())]
        else:
            v = [str(x) if u else None for x, u in zip(vals.tolist(), used.tolist())]
        cols.append({**{f: c.get(f) for f in ("key", "name", "unit", "kind", "dtype", "role")}, "values": v})
    return {"id": sid, "title": env.get("title"), "version": env["version"], "latest": res["latest"], "status": res["status"],
            "rows": ds.rows, "columns": [{f: c.get(f) for f in ("key", "name", "unit", "dtype", "role")} for c in ds.columns],
            "cols": cols, "producer": {k: (env.get("producer") or {}).get(k) for k in ("module", "env_name", "item_name")}}


class Handler(BaseHTTPRequestHandler):
    server_version = "FolioRechner/1.0"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body: bytes, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(clean(obj), ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _req(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def do_GET(self):
        p = urlparse(self.path).path
        if p in ("/", "/index.html"):
            return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        if p == "/api/meta":
            return self._json(meta_payload())
        if p in ("/labenv.js", "/labindex.js", "/labui.js", "/labboard.js", "/laboverview.js", "/labimport.js",
                 "/labunc.js"):                         # gemeinsame Seitenskripte
            return self._send(200, labcite.web_asset(p[1:]), "text/javascript; charset=utf-8")
        self._send(404, b"nicht gefunden", "text/plain")

    def do_POST(self):
        origin = self.headers.get("Origin")
        if origin and not ORIGIN_OK.match(origin):
            n = int(self.headers.get("Content-Length") or 0)
            if 0 < n <= 1 << 20:
                self.rfile.read(n)                       # read the small body so the answer arrives cleanly
            return self._json({"error": "Fremde Herkunft abgelehnt"}, 403)
        try:
            return self._route(urlparse(self.path).path)
        except (E.CalcError, U.UnitError, E.DimError, EnvError) as e:
            return self._json({"error": str(e)}, 400)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    def _route(self, p):
        req = self._req()
        if p.startswith("/api/env/"):
            # A2: der ganze Arbeitsstand (Blätter, Variablen, Grafik) ist der Seitenzustand der Umgebung; keine Dateien
            return self._json(ENVS.route(p.rsplit("/", 1)[1], req, list))
        if p.startswith("/api/index/"):                # A7: Projektindex
            import labindex
            return self._json(labindex.route(ENVS, "rechner", __version__, p.rsplit("/", 1)[1], req))
        if p.startswith("/api/prov/"):                 # A8: Herkunftskette, Abhängigkeiten
            import labprov
            return self._json(labprov.route(ENVS, p.rsplit("/", 1)[1], req))
        if p.startswith("/api/unc/"):                  # Messunsicherheit: Messmittel, Vorschau im ±-Fenster, Verfahren
            import labunc
            return self._json(labunc.route(unc_envs(), p.rsplit("/", 1)[1], req))
        if p == "/api/materials":                      # Werkstoffdatenbank für die Auswahl in der Bibliothek
            return self._json(materials_payload(req.get("lang") or "de"))
        if p == "/api/material":
            from labcalc import materials as MAT
            try:
                return self._json(MAT.card(req.get("id") or "", req.get("lang") or "de"))
            except MAT.MatError as e:
                return self._json({"error": str(e)}, 400)
        if p == "/api/eval":
            out = CON.evaluate_safe(req)
            return self._json(out, 400 if out.get("error") else 200)
        if p == "/api/sheet":
            return self._json(S.eval_sheet(req))
        if p == "/api/workspace":
            from . import dsvars as DV
            from . import workspace as W
            load_own_instruments()
            return self._json(W.evaluate(DV.attach(req, ENVS)))    # DP-11: Datensatz-Spalten als Listenvariablen
        if p == "/api/workspace/compare":              # Messunsicherheit einer Zeile nach allen vier Verfahren
            from . import dsvars as DV
            from . import workspace as W
            load_own_instruments()
            return self._json(W.compare_line(DV.attach(req, ENVS)))
        if p == "/api/dataset":                        # DP-M6: Tabelle aus einem Datensatz der Datenaufbereitung
            return self._json(dataset_route(req))
        if p == "/api/graph":
            from . import graph as G
            return self._json(G.compute(req))
        if p == "/api/recognize":
            from . import recognize as RC
            return self._json(RC.recognize(req.get("name") or "", req.get("unit") or "", req.get("kind"), req.get("lang", "de")))
        if p == "/api/goal":
            return self._json(S.goal(req.get("sheet") or {}, req.get("sym"), req.get("kind")))
        if p == "/api/plot":
            ctx = P.make_ctx(req.get("ctx") or {})
            view = req.get("view") or {}
            out = []
            for f in req.get("functions") or []:
                try:
                    out.append({"id": f.get("id"), **P.sample(f, ctx, view)})
                except (E.CalcError, KeyError, ValueError, TypeError) as e:
                    out.append({"id": f.get("id"), "error": str(e)})
            return self._json({"series": out})
        if p == "/api/curve":
            return self._json(S.card_curve(req.get("sheet") or {}, req.get("card"), req.get("xvar"),
                                           float(req.get("x0")), float(req.get("x1")), int(req.get("n") or 200),
                                           bool(req.get("log"))))
        if p == "/api/analyze":
            return self._json(P.analyze(req, P.make_ctx(req.get("ctx") or {})))
        if p == "/api/fit":
            return self._json(P.fit(req.get("x") or [], req.get("y") or [], req.get("model") or "lin"))
        if p in ("/api/bundle", "/api/bundle/rebuild"):
            return self._bundle(p, req)
        return self._send(404, b"nicht gefunden", "text/plain")

    def _bundle(self, p, req):
        from . import bundle as B
        from . import dsvars as DV
        if p == "/api/bundle/rebuild":
            src = req.get("source") or {}
            old = src.get("request") or {}
            req = {**old, **{k: v for k, v in req.items() if k != "source"}}
        req = DV.attach(req, ENVS)                     # DP-11: live = neueste Version, gepinnt bleibt
        load_own_instruments()
        lang = req.get("lang", "de")
        try:
            return self._json(B.build(req, lang=lang, include=req.get("include"), title=req.get("title")))
        except ValueError as e:
            return self._json({"error": str(e)}, 400)


def env_bundle(_stored, report: dict, lang: str) -> dict:
    """Bündel einer gespeicherten Umgebung aus dem Berichtsauftrag ihrer Seite (keine Dateien)."""
    from . import bundle as B
    from . import dsvars as DV
    req = DV.attach({**report, "lang": lang}, ENVS)
    load_own_instruments()
    return B.build(req, lang=lang, include=req.get("include"), title=req.get("title"))


def env_default_report(_stored, client: dict, _eid: str = "") -> dict | None:
    """Umgebungen, die vor dem Import aus Folio gespeichert wurden: Blätter, Werte und Variablen aus dem Seitenzustand; Diagramme
    brauchen die Seite (Kurvendaten) und fehlen, bis die Umgebung einmal geöffnet war."""
    ex = (client or {}).get("extra") or {}
    if not isinstance(ex, dict) or not ex.get("envs"):
        return None
    vars_ = ex.get("vars") or {}
    mats: dict = {}                                     # Matrizen erst mit dem Berichtsauftrag der Seite
    return {"values": ex.get("values") or [], "vars": vars_, "dsvars": ex.get("dsvars") or [], "plots": [],
            "envs": [{"id": e.get("id"), "name": e.get("name"), "items": e.get("items") or [], "derive": e.get("derive") is not False,
                      **({"unc": e["unc"]} if isinstance(e.get("unc"), dict) else {})}
                     for e in ex["envs"] if isinstance(e, dict)],
            "matrices": mats, "angle": ex.get("angle"), "complex": ex.get("complex"), "digits": ex.get("digits"),
            "include": {}, "title": "Berechnung"}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Rechner, lokale Oberfläche")
    ap.add_argument("--port", type=int, default=8767)
    ap.add_argument("--aus", default=str(ROOT / "Ausgaben"), help="Ausgabeordner (Umgebungen im Einzelbetrieb)")
    ap.add_argument("--kein-browser", action="store_true")
    a = ap.parse_args(argv)
    global ENVS
    ENVS = ModuleEnvs(Path(a.aus).resolve(), "rechner")
    ENVS.env_bundle = env_bundle
    ENVS.env_default_report = env_default_report
    srv =ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = f"http://127.0.0.1:{a.port}/"
    print(f"Rechner läuft auf {url}  (Beenden mit Strg+C)")
    if not a.kein_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
