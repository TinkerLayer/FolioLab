"""Lokale Oberflaeche des Mikroskopie-Moduls.

Laeuft nur auf 127.0.0.1 und ruft nichts aus dem Netz ab. Die Bilder bleiben im Speicher; geschrieben wird erst
bei "Exportieren".

Start:  python -m mikro.server  [--port 8766] [--aus Ausgaben] [--kein-browser]
"""
from __future__ import annotations

import argparse
import base64
import csv
import io
import json
import math
import os
import re
import sys
import threading
import traceback
import uuid
import webbrowser
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import numpy as np
from PIL import Image

_SDK = Path(__file__).resolve().parents[3] / "sdk" / "python"
if _SDK.is_dir() and str(_SDK) not in sys.path:
    sys.path.insert(0, str(_SDK))

import labcite  # noqa: E402
from labproject import EnvError, ModuleEnvs  # noqa: E402

from . import charts as C
from . import measure as M
from . import ops
from . import threshold as TH
from .analysis import display_for_pre, run
from .imageio import Calib, load_bytes, sample_image

STATIC = Path(__file__).resolve().parent / "static"
ROOT = Path(__file__).resolve().parents[1]
ORIGIN_OK = re.compile(r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$")
MAX_ROWS = 5000


class State:
    def __init__(self, out_root: Path):
        self.images: dict = {}       # id -> Stack (Original)
        self.raw: dict = {}          # id -> Rohdaten der Datei
        self.cache: OrderedDict = OrderedDict()   # (id, Protokoll) -> Proc
        self.lock = threading.Lock()
        self.out_root = out_root
        self.envs = ModuleEnvs(out_root, "mikroskopie")   # A2: Umgebungen im aktiven Projekt


STATE: State | None = None


def add_image(st, data: bytes, name: str, iid: str | None = None) -> dict:
    keep = iid is None
    iid = iid or uuid.uuid4().hex[:10]
    with STATE.lock:
        STATE.images[iid] = st
        STATE.raw[iid] = data
    if keep:
        STATE.envs.remember(iid, data, name, 0, name)
    d = st.describe()
    d["id"] = iid
    return d


def reload_env() -> list[dict]:
    """Bilder der aktiven Umgebung neu einlesen (A2); IDs bleiben gleich."""
    with STATE.lock:
        STATE.images.clear()
        STATE.raw.clear()
        STATE.cache.clear()
    out = []
    for iid, raw, fname, _idx, _name, _extra in STATE.envs.stored():
        try:
            out.append(add_image(load_bytes(raw, fname), raw, fname, iid))
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
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        f = float(o)
        return f if math.isfinite(f) else None
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def get_image(iid):
    st = STATE.images.get(iid)
    if st is None:
        raise LookupError("Bild nicht geladen")
    return st


def processed(iid, pipeline) -> ops.Proc:
    """Protokoll anwenden, Ergebnis zwischenspeichern (die Oberflaeche fragt oft nach demselben Stand)."""
    key = (iid, json.dumps(pipeline or [], sort_keys=True))
    with STATE.lock:
        if key in STATE.cache:
            STATE.cache.move_to_end(key)
            return STATE.cache[key]
    proc = ops.apply(get_image(iid), pipeline or [])
    with STATE.lock:
        STATE.cache[key] = proc
        while len(STATE.cache) > 8:
            STATE.cache.popitem(last=False)
    return proc


def proc_info(iid, proc: ops.Proc) -> dict:
    d = proc.stack.describe()
    d["id"] = iid
    d["steps"] = proc.steps
    d["thr"] = proc.thr
    d["has_pre"] = proc.pre is not None
    return d


def calib_of(req, stack) -> Calib:
    return Calib.from_dict(req["calib"]) if req.get("calib") else stack.calib


def state_of(req) -> dict:
    """Arbeitsstand aus einer Anfrage (gleiche Form wie im Bericht gespeichert)."""
    return {k: req.get(k) for k in ("pipeline", "slice", "display", "calib", "rois", "particles", "region", "scalebar", "compare")}


def png_bytes(rgb_or_rgba: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(rgb_or_rgba).save(buf, format="PNG")
    return buf.getvalue()


def meta_payload() -> dict:
    return {
        "ops": ops.OPS,
        "methods": {k: v[0] for k, v in TH.METHODS.items()},
        "luts": C.all_luts(),
        "particle_defaults": M.DEFAULT_PARTICLE,
        "out_root": str(STATE.out_root),
        "version": __import__("mikro").__version__,
    }


def particle_payload(a) -> dict:
    p = a.part
    rows = p["rows"]
    return {"count": len(rows), "rows": rows[:MAX_ROWS], "truncated": len(rows) > MAX_ROWS,
            "summary": p["summary"], "overlay": base64.b64encode(png_bytes(M.outline_rgba(p["labels"]))).decode("ascii")}


# ----------------------------------------------------------------------------- Datensatz (I-04)
def _ds_open(sid: str, mode: str, version=None):
    """(Datensatz, Umschlag, neueste Version) einer Freigabe; live = neueste Version, pin = die genannte."""
    from labshare import Sharebox, dataset_of
    STATE.envs.ensure()
    box = Sharebox(STATE.envs.suite, STATE.envs.project)
    res = box.resolve({"id": sid, "mode": mode, "version": version}, "mikroskopie")
    if res["status"] == "failed":
        raise EnvError(res.get("error") or "Datensatz nicht verfügbar")
    env = res["envelope"]
    return dataset_of(env, box.base / sid), env, res.get("latest")


def dataset_route(action: str, req: dict) -> dict:
    """columns = Längenspalten des Datensatzes; compare = Vergleichsverteilung (Werte in m, Kennwerte in `unit`);
    latest = neueste Version je Freigabe (für „live“ verbundene Vergleiche)."""
    from labdataset import DatasetError

    from . import compare as CMP
    sid = str(req.get("id") or "")
    mode = "pin" if req.get("mode") == "pin" else "live"
    try:
        if action == "columns":
            ds, env, latest = _ds_open(sid, mode, req.get("version"))
            return {"columns": CMP.length_columns(ds), "title": env.get("title"), "version": env["version"],
                    "latest": latest, "rows": ds.rows}
        if action == "compare":
            ds, env, latest = _ds_open(sid, mode, req.get("version"))
            rec = CMP.record(ds, env, sid, mode, str(req.get("key") or ""))
            out = {"cmp": rec, "latest": latest}
            if req.get("unit"):
                out["stats"] = CMP.stats(CMP.in_unit(rec, str(req["unit"])))
            return out
        if action == "latest":
            from labshare import Sharebox
            STATE.envs.ensure()
            box = Sharebox(STATE.envs.suite, STATE.envs.project)
            out = {}
            for s in {str(x) for x in (req.get("ids") or [])}:
                try:
                    out[s] = box.resolve({"id": s, "mode": "live"}).get("latest")
                except (EnvError, OSError, ValueError):
                    out[s] = None
            return {"latest": out}
    except CMP.CompareError as e:
        raise ops.OpError(str(e)) from None
    except DatasetError as e:
        raise ops.OpError(str(e)) from None
    raise LookupError("Unbekannte Aktion")


# ----------------------------------------------------------------------------- Export
def _write_csv(path: Path, rows: list[dict], cols: list[str] | None = None):
    cols = cols or [k for k in rows[0] if not k.startswith("_")]
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(cols)
        for r in rows:
            w.writerow(["" if r.get(c) is None else (f"{r[c]:.6g}".replace(".", ",") if isinstance(r.get(c), float) else r.get(c))
                        for c in cols])


def export(iid, req) -> dict:
    import matplotlib.pyplot as plt
    st = get_image(iid)
    state = state_of(req)
    a = run(st, state, "de")
    stem = re.sub(r"[^\w\-]+", "_", Path(st.name).stem).strip("_") or "Bild"
    folder = STATE.out_root / stem
    if folder.exists() and any(folder.iterdir()) and not req.get("overwrite"):
        return {"exists": True, "folder": str(folder)}
    folder.mkdir(parents=True, exist_ok=True)
    files = []

    def fig(f, name):
        f.savefig(folder / name, dpi=200, bbox_inches="tight")
        plt.close(f)
        files.append(name)

    disp = display_for_pre(a) if a.kind == "binary" else (state.get("display") or {})
    base = a.intensity if a.kind == "binary" else a.img
    rgb = C.render(base, "rgb" if base.ndim == 3 else "gray", disp)
    sb = state.get("scalebar")
    fig(C.fig_image(rgb, a.calib, "de", rois=state.get("rois"), scalebar=sb), "bild.png")
    if a.kind == "binary":
        Image.fromarray((a.img > 0).astype(np.uint8) * 255).save(folder / "maske.png")
        files.append("maske.png")
    if a.measurements:
        _write_csv(folder / "messungen.csv", a.measurements,
                   ["Label", "Type", "Area", "Mean", "StdDev", "Min", "Max", "Median", "X", "Y", "Perim.", "Length", "Angle"])
        files.append("messungen.csv")
    if a.part:
        rows = a.part["rows"]
        if rows:
            _write_csv(folder / "partikel.csv", rows)
            files.append("partikel.csv")
        _write_csv(folder / "zusammenfassung.csv", [a.part["summary"]])
        files.append("zusammenfassung.csv")
        fig(C.fig_image(rgb, a.calib, "de", overlay=M.outline_rgba(a.part["labels"]), scalebar=sb,
                        labels=[r["_px"] for r in rows] if len(rows) <= 300 else None), "partikel.png")
        if len(rows) >= 3:
            unit = a.calib.unit if a.calib.calibrated else "px"
            fig(C.fig_sizes(rows, unit, "de"), "groessenverteilung.png")
        from .bundle import _overlay
        ov = _overlay(a)
        if ov:                                          # I-04: Vergleichsverteilung aus einem Datensatz
            fig(C.fig_sizes_overlay(ov["ecd"], ov["vals"], a.calib.unit, "de", ("Partikel", ov["cmp"].get("name") or "Datensatz"),
                                    weights=ov["w"]),
                "vergleichsverteilung.png")
            names = {"D10": "D10 (Q0)", "D50": "D50 (Q0)", "D90": "D90 (Q0)", "Dv10": "Dv10 (Q3)", "Dv50": "Dv50 (Q3)",
                     "Dv90": "Dv90 (Q3)", "mean": "Mittelwert (Q0)", "sd": "Std.-Abw. (Q0)"}
            _write_csv(folder / "vergleichsverteilung.csv",
                       [{"Grösse": names.get(k, k), "Partikel": ov["s_img"][k], "Datensatz": ov["s_ds"][k]}
                        for k in ("n", "D10", "D50", "D90", "Dv10", "Dv50", "Dv90", "mean", "sd")])
            files.append("vergleichsverteilung.csv")
    if a.intensity.ndim == 2:
        fig(C.fig_hist(a.intensity, "de", a.proc.thr), "histogramm.png")
    lines = [f"Bild: {st.name}  ({st.width}×{st.height} px, {st.type_label()}, {st.slices} Ebene(n))",
             ("Kalibrierung: " + (f"{a.calib.pw:g} {a.calib.unit}/px (quadratische Pixel"
                                  + (", angenommen" if a.calib.square_assumed else "") + ")" if a.calib.square
                                  else f"Pixelbreite {a.calib.pw:g} {a.calib.unit}, Pixelhöhe {a.calib.ph:g} {a.calib.unit}")
              if a.calib.calibrated else "Kalibrierung: keine"),
             "", "Protokoll:"]
    lines += [f"  {i}. {s}" for i, s in enumerate(a.proc.steps, 1)] or ["  (keine Bearbeitung)"]
    lines += ["", "Protokoll als JSON (in der Oberfläche unter Protokoll ▸ Laden wieder einlesbar):",
              json.dumps(state.get("pipeline") or [], ensure_ascii=False)]
    if a.part:
        lines += ["", "Partikelanalyse: " + json.dumps(clean(state.get("particles")), ensure_ascii=False)]
    (folder / "protokoll.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    files.append("protokoll.txt")
    return {"folder": str(folder), "files": files}


# ----------------------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "FolioMikro/1.0"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code: int, body: bytes, ctype: str, headers: dict | None = None):
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
        return self.rfile.read(n) if n else b""

    def _req(self) -> dict:
        return json.loads(self._body() or b"{}")

    def do_GET(self):
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        if url.path == "/api/meta":
            return self._json(meta_payload())
        if url.path in ("/labenv.js", "/labindex.js", "/labui.js", "/labboard.js", "/laboverview.js", "/labimport.js"):   # UI-07, I-02
            return self._send(200, labcite.web_asset(url.path[1:]), "text/javascript; charset=utf-8")
        self._send(404, b"nicht gefunden", "text/plain")

    def do_POST(self):
        url = urlparse(self.path)
        origin = self.headers.get("Origin")
        if origin and not ORIGIN_OK.match(origin):
            return self._json({"error": "Fremde Herkunft abgelehnt"}, 403)
        try:
            return self._route(url)
        except (ops.OpError, EnvError) as e:
            return self._json({"error": str(e)}, 400)
        except LookupError as e:
            return self._json({"error": str(e)}, 404)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    def _route(self, url):
        p = url.path
        if p in ("/api/load", "/api/sample"):
            if p == "/api/sample":
                data, name = sample_image()
            else:
                name = unquote(parse_qs(url.query).get("name", ["Bild.tif"])[0])
                data = self._body()
            try:
                st = load_bytes(data, name)
            except ValueError as e:
                return self._json({"error": str(e)}, 400)
            return self._json(add_image(st, data, name))
        if p == "/api/remove":
            iid = self._req().get("id")
            with STATE.lock:
                STATE.images.pop(iid, None)
                STATE.raw.pop(iid, None)
                for k in [k for k in STATE.cache if k[0] == iid]:
                    STATE.cache.pop(k, None)
            STATE.envs.forget(str(iid))
            return self._json({"ok": True})
        if p.startswith("/api/env/"):
            return self._json(STATE.envs.route(p.rsplit("/", 1)[1], self._req(), reload_env))
        if p.startswith("/api/index/"):                # A7: Projektindex
            import labindex
            return self._json(labindex.route(STATE.envs, "mikroskopie", __import__("mikro").__version__, p.rsplit("/", 1)[1], self._req()))
        if p.startswith("/api/prov/"):                 # A8: Herkunftskette, Abhängigkeiten
            import labprov
            return self._json(labprov.route(STATE.envs, p.rsplit("/", 1)[1], self._req()))
        if p == "/api/process":
            req = self._req()
            return self._json(proc_info(req.get("id"), processed(req.get("id"), req.get("pipeline"))))
        if p == "/api/pixels":
            # Rohwerte einer Ebene: Graustufen als float32 (little endian), RGB als uint8 RGBRGB...
            req = self._req()
            proc = processed(req.get("id"), req.get("pipeline"))
            st = proc.stack
            s = min(max(int(req.get("slice") or 0), 0), st.slices - 1)
            which = req.get("which")
            if which == "pre" and proc.pre is not None:
                arr, kind = proc.pre[min(s, proc.pre.shape[0] - 1)], "gray"
            else:
                arr, kind = st.data[s], st.kind
            body = np.ascontiguousarray(arr, dtype=np.uint8 if kind == "rgb" else "<f4").tobytes()
            return self._send(200, body, "application/octet-stream",
                              {"X-Kind": kind, "X-W": arr.shape[1], "X-H": arr.shape[0], "X-Slices": st.slices})
        if p == "/api/threshold":
            req = self._req()
            proc = processed(req.get("id"), req.get("pipeline"))
            st = proc.stack
            if st.kind != "gray":
                raise ops.OpError("Schwellen gehen nur mit Graustufenbildern.")
            s = min(max(int(req.get("slice") or 0), 0), st.slices - 1)
            src = st.data if req.get("stack") else st.data[s]
            method = req.get("method") or "default"
            if method == "all":
                out = {}
                for k in TH.METHODS:
                    out[k] = TH.auto_range(src, st.bitdepth, k, bool(req.get("dark", True)))
                return self._json({"all": out})
            return self._json(TH.auto_range(src, st.bitdepth, method, bool(req.get("dark", True))))
        if p == "/api/measure":
            req = self._req()
            st = get_image(req.get("id"))
            a = run(st, {**state_of(req), "particles": None}, "de", with_particles=False)
            return self._json({"rows": a.measurements, "unit": a.calib.unit if a.calib.calibrated else "px",
                               "on_pre": a.pre is not None})
        if p == "/api/profile":
            req = self._req()
            st = get_image(req.get("id"))
            a = run(st, {**state_of(req), "rois": [], "particles": None}, "de", with_particles=False)
            r = req.get("roi") or {}
            d, v = M.sample_line(a.intensity, r["x1"], r["y1"], r["x2"], r["y2"], int(r.get("width") or 1))
            k = M.line_scale(a.calib, r["x2"] - r["x1"], r["y2"] - r["y1"])     # pw und ph je nach Richtung
            return self._json({"d": d * k, "v": v, "unit": a.calib.unit if a.calib.calibrated else "px"})
        if p == "/api/particles":
            req = self._req()
            st = get_image(req.get("id"))
            state = state_of(req)
            state["particles"] = req.get("params") or {}
            state["rois"] = []
            a = run(st, state, "de")
            out = particle_payload(a)
            out["unit"] = a.calib.unit if a.calib.calibrated else "px"
            return self._json(out)
        if p == "/api/export":
            req = self._req()
            return self._json(export(req.get("id"), req))
        if p == "/api/open":
            folder = Path(self._req().get("folder", ""))
            if folder.exists() and STATE.out_root.resolve() in folder.resolve().parents and hasattr(os, "startfile"):
                os.startfile(str(folder))  # noqa: S606 - nur Ordner unterhalb des Ausgabeordners
            return self._json({"ok": True})
        if p in ("/api/bundle", "/api/bundle/rebuild"):
            return self._bundle(p)
        if p.startswith("/api/dataset/"):              # I-04: Vergleichsverteilung aus einem Datensatz
            return self._json(dataset_route(p.rsplit("/", 1)[1], self._req()))
        return self._send(404, b"nicht gefunden", "text/plain")

    def _bundle(self, p):
        from . import bundle as B
        req = self._req()
        items, req_items = [], []
        if p == "/api/bundle":
            for it in req.get("items", []):
                st = get_image(it.get("id"))
                state = it.get("state") or {}
                items.append((st, STATE.raw[it["id"]], state))
                req_items.append({"name": st.name, "state": state})
        else:
            src = req.get("source") or {}
            files = {k: base64.b64decode(v) for k, v in (src.get("files") or {}).items()}
            for it in (src.get("request") or {}).get("items", []):
                data = files.get(it["name"])
                if data is None:
                    return self._json({"error": f"Quelldatei {it['name']} fehlt im Bundle"}, 400)
                items.append((load_bytes(data, it["name"]), data, it.get("state") or {}))
                req_items.append(it)
            old = src.get("request") or {}
            req = {**old, **{k: v for k, v in req.items() if k != "source"}}
        if not items:
            return self._json({"error": "Kein Bild gewählt."}, 400)
        request = {"items": req_items, "lang": req.get("lang", "de"), "include": req.get("include") or {},
                   "title": req.get("title") or None, "slug": req.get("slug") or None}
        try:
            b = B.build(items, request, lang=request["lang"], include=request["include"], title=request["title"])
        except ValueError as e:
            return self._json({"error": str(e)}, 400)
        return self._json(b)


def main(argv=None):
    global STATE
    ap = argparse.ArgumentParser(description="Mikroskopie, lokale Oberfläche")
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--aus", default=str(ROOT / "Ausgaben"), help="Wurzelordner der Exporte")
    ap.add_argument("--kein-browser", action="store_true")
    a = ap.parse_args(argv)
    STATE = State(Path(a.aus).resolve())
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = f"http://127.0.0.1:{a.port}/"
    print(f"Mikroskopie läuft auf {url}  (Beenden mit Strg+C)")
    print(f"Exporte gehen nach {STATE.out_root}")
    if not a.kein_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
