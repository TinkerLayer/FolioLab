"""Lokale Oberfläche des FTIR-Moduls.

Läuft nur auf 127.0.0.1 und ruft nichts aus dem Netz ab. Spektren bleiben im Speicher; geschrieben wird nur bei
"Exportieren" und in eigene Bibliotheken (<ausgaben>/bibliotheken).

Start:  python -m ftir.server  [--port 8767] [--out Ausgaben] [--no-browser]
"""
from __future__ import annotations

import argparse
import base64
import csv
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

_SDK = Path(__file__).resolve().parents[3] / "sdk" / "python"
if _SDK.is_dir() and str(_SDK) not in sys.path:
    sys.path.insert(0, str(_SDK))

import labcite  # noqa: E402
from labproject import EnvError, ModuleEnvs  # noqa: E402
from labuser import JsonStore  # noqa: E402

from . import __version__  # noqa: E402
from . import charts as C
from . import groups as GR
from . import peaks as PK
from . import process as PR
from . import quality as QA
from . import samples as SM
from . import search as SR
from .analysis import FUNCTIONS_DOC, arr, run
from .library import GRID, MODEL_ID, Libraries, prep
from .readers import YUNITS, ReadError, Spectrum, load_bytes, to_csv, to_jcamp

STATIC = Path(__file__).resolve().parent / "static"
ROOT = Path(__file__).resolve().parents[1]
ORIGIN_OK = re.compile(r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$")
MAX_FILE = 200 * 1024 * 1024


class Item:
    def __init__(self, sp: Spectrum, raw: bytes, fname: str, idx: int):
        self.sp, self.raw, self.fname, self.idx = sp, raw, fname, idx


class State:
    def __init__(self, out_root: Path):
        self.items: dict[str, Item] = {}
        self.cache: OrderedDict = OrderedDict()
        self.lock = threading.Lock()
        self.out_root = out_root
        self.libs = Libraries(out_root / "bibliotheken")
        self.eqs = JsonStore(out_root / "eigene_gleichungen.json", kind="folio-gleichungen/1")
        self.envs = ModuleEnvs(out_root, "ftir")                         # A2: Umgebungen im aktiven Projekt


STATE: State | None = None


def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, np.ndarray):
        if o.dtype.kind == "f":
            o = np.round(o.astype(float), 6)
        return clean(o.tolist())
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, (float, np.floating)):
        f = float(o)
        return f if math.isfinite(f) else None
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def item(iid) -> Item:
    it = STATE.items.get(iid)
    if it is None:
        raise LookupError("Spektrum nicht geladen")
    return it


def processed(iid, pipeline) -> PR.Proc:
    key = (iid, json.dumps(pipeline or [], sort_keys=True))
    with STATE.lock:
        if key in STATE.cache:
            STATE.cache.move_to_end(key)
            return STATE.cache[key]
    proc = PR.apply(item(iid).sp, pipeline or [])
    with STATE.lock:
        STATE.cache[key] = proc
        while len(STATE.cache) > 24:
            STATE.cache.popitem(last=False)
    return proc


def add_item(sp: Spectrum, raw: bytes, fname: str, idx: int, iid: str | None = None) -> dict:
    keep = iid is None
    iid = iid or uuid.uuid4().hex[:10]
    with STATE.lock:
        STATE.items[iid] = Item(sp, raw, fname, idx)
    if keep:
        STATE.envs.remember(iid, raw, fname, idx, sp.name)
    return describe(iid)


def describe(iid) -> dict:
    it = item(iid)
    d = it.sp.describe()
    d.update(id=iid, file=it.fname, idx=it.idx)
    src = (it.sp.meta or {}).get("dataset") or {}
    if src.get("share"):                               # DP-13: neueste Version des Datensatzes (für „aktualisieren“)
        d["ds_latest"] = ds_latest(src["share"])
    return d


# ----------------------------------------------------------------------------- DP-13: Spektren aus Datensatz
def _box():
    from labshare import Sharebox
    STATE.envs.ensure()
    return Sharebox(STATE.envs.suite, STATE.envs.project)


def ds_latest(sid: str) -> int | None:
    try:
        return _box().resolve({"id": sid, "mode": "live"}, "ftir").get("latest")
    except (EnvError, OSError, ValueError):
        return None


def ds_list() -> dict:
    """Datensätze (`data.table`), die an das FTIR adressiert sind, mit Spalten und Vorschlag x/y je Spalte."""
    from labshare import DATA_KIND
    from . import dataset as DS
    box = _box()
    out = []
    for m in box.list("ftir", DATA_KIND):
        try:
            env = box.get(m["id"], None, "ftir")
        except EnvError:
            continue
        h, p = env.get("dataset") or {}, m.get("producer") or {}
        out.append({"id": m["id"], "title": m.get("title"), "latest": m.get("latest"), "modified": m.get("modified"),
                    "rows": h.get("rows"), "producer": {k: p.get(k) for k in ("module", "env_name", "item_name")},
                    "columns": [dict({k: c.get(k) for k in ("key", "name", "unit", "dtype", "kind")}, guess=DS.guess(c))
                                for c in h.get("columns") or []]})
    return {"datasets": out}


def ds_open(sid: str, mode: str, version=None):
    from labshare import dataset_of
    box = _box()
    res = box.resolve({"id": sid, "mode": mode, "version": version}, "ftir")
    if res["status"] == "failed":
        raise EnvError(res.get("error") or "Datensatz nicht verfügbar")
    env = res["envelope"]
    return dataset_of(env, box.base / sid), env


def _ds_source(sid: str, env: dict, mode: str) -> dict:
    p = env.get("producer") or {}
    return {"share": sid, "title": env.get("title"), "version": env["version"], "mode": mode,
            "producer": {k: p.get(k) for k in ("module", "env_name", "item_name")}}


def ds_spectra(req) -> list[dict]:
    """Je gewählter y-Spalte ein Spektrum; gespeichert wie eine geladene Datei (JCAMP-DX mit Herkunft)."""
    from . import dataset as DS
    sid = str(req.get("id") or "")
    mode = "pin" if req.get("mode") == "pin" else "live"
    ds, env = ds_open(sid, mode, req.get("version"))
    raws = DS.make_raws(ds, str(req.get("x") or ""), req.get("y") or [], str(req.get("yunit") or "auto"),
                        _ds_source(sid, env, mode))
    out = []
    for raw, fname in raws:                            # erst alle prüfen (make_raws), dann anlegen
        for d in load_file(raw, fname):
            STATE.envs.set_extra(d["id"], dataset={"share": sid, "version": env["version"], "mode": mode})
            out.append(d)
    return out


def ds_refresh(req) -> dict:
    """Spektrum aus einem Datensatz auf die neueste (oder genannte) Version bringen; Name und ID bleiben."""
    from . import dataset as DS
    iid = str(req.get("id") or "")
    it = item(iid)
    src = (it.sp.meta or {}).get("dataset") or {}
    if not src.get("share"):
        raise ValueError("Dieses Spektrum stammt nicht aus einem Datensatz.")
    ds, env = ds_open(src["share"], "pin" if req.get("version") else "live", req.get("version"))
    if env["version"] == src.get("version"):
        return {"spectrum": describe(iid), "changed": False}
    cols = src.get("columns") or {}
    (raw, fname), = DS.make_raws(ds, (cols.get("x") or {}).get("key"), [(cols.get("y") or {}).get("key")],
                                 src.get("choice") or "auto", _ds_source(src["share"], env, src.get("mode") or "live"))
    sp = load_bytes(raw, fname)[0]
    sp.name = it.sp.name
    with STATE.lock:
        STATE.items[iid] = Item(sp, raw, fname, 0)
        for k in [k for k in STATE.cache if k[0] == iid]:
            STATE.cache.pop(k, None)
    STATE.envs.replace_raw(iid, raw, fname)
    STATE.envs.set_extra(iid, dataset={"share": src["share"], "version": env["version"], "mode": src.get("mode") or "live"})
    return {"spectrum": describe(iid), "changed": True}


def reload_env() -> list[dict]:
    """Spektren der aktiven Umgebung neu einlesen (nach Neustart oder Wechsel); IDs bleiben gleich."""
    with STATE.lock:
        STATE.items.clear()
        STATE.cache.clear()
    out = []
    for iid, raw, fname, idx, name, _extra in STATE.envs.stored():
        try:
            sp = load_bytes(raw, fname)[idx]
        except (ReadError, IndexError, ValueError):
            continue
        if name:
            sp.name = name
        out.append(add_item(sp, raw, fname, idx, iid))
    return out


def load_file(data: bytes, name: str) -> list[dict]:
    sps = load_bytes(data, name)
    return [add_item(sp, data, name, i) for i, sp in enumerate(sps)]


def state_of(req) -> dict:
    return {k: req.get(k) for k in ("pipeline", "peaks", "bands", "ratios", "groups", "search", "mixture", "equations",
                                    "ext_values")}


def share_peaks(req) -> dict:
    """A6: Peaktabelle und Gruppenhypothesen eines Spektrums für den Elementrechner teilen – nur Zahlen, nie das Spektrum.
    Dasselbe Spektrum in derselben Umgebung erneut geteilt = neue Version derselben Freigabe."""
    from labshare import Sharebox
    iid = req.get("id")
    it = item(iid)
    st = state_of(req)
    st["peaks"] = st.get("peaks") or {}
    st["groups"] = True
    st["mixture"] = None
    st["search"] = None
    a = run(it.sp, st, "de")
    outs = []
    for i, p in enumerate(sorted(a.peaks or [], key=lambda p: -p["x"]), 1):
        outs.append({"key": f"peak{i}", "label": f"Bande {i}: " + ", ".join((p.get("assign") or [])[:2]),
                     "quantity": {"value": round(float(p["x"]), 1), "unit": "cm-1"},
                     "conditions": {"strength": p.get("strength") or "", "rel": round(float(p.get("prom_rel") or 0), 3),
                                    "fwhm": round(float(p.get("fwhm") or 0), 1)}})
    for c in (a.groups or {}).get("classes", []):
        outs.append({"key": f"class-{c['id']}", "label": c["name"], "quantity": {"value": float(c["score"]), "unit": ""},
                     "conditions": {"verdict": c["verdict"], "found": c["found"], "needed": c["needed"]}})
    for j, ab in enumerate((a.groups or {}).get("absent", []), 1):
        outs.append({"key": f"absent{j}", "label": ab["text"], "quantity": {"value": float(ab["range"][0]), "unit": "cm-1"},
                     "conditions": {"lo": float(ab["range"][1])}})
    if not any(o["key"].startswith("peak") for o in outs):
        raise ValueError("Keine Banden gefunden – nichts zu teilen.")
    envs = STATE.envs
    envs.ensure()
    box = Sharebox(envs.suite, envs.project)
    prev = next((m for m in box.list(kind="ftir.peaks") if (m.get("producer") or {}).get("item") == iid
                 and (m.get("producer") or {}).get("env") == envs.eid), None)
    env_name = next((e["name"] for e in envs.envs.list() if e["id"] == envs.eid), envs.eid)
    prod = {"module": "ftir", "env": envs.eid, "env_name": env_name, "item": iid, "item_name": it.sp.name,
            "raw": (envs.items.get(iid) or {}).get("raw"),  # A8: Rohdatei der Kette, auch wenn der Eintrag später geschlossen wird
            "module_version": __version__}
    return box.publish(prod, "ftir.peaks", it.sp.name, outs, req.get("recipients") or ["elementrechner"],
                       sources=[{"protocol": a.proc.steps}], share_id=prev["id"] if prev else None)


def libs_of(ids) -> list:
    ids = ids or [MODEL_ID]
    out = []
    for lid in ids:
        try:
            out.append(STATE.libs.get(lid))
        except LookupError:
            continue
    if not out:
        raise LookupError("Keine Bibliothek gewählt.")
    return out


def query_of(req):
    """Suchvektor aus dem bearbeiteten Spektrum; Ableitungen werden nicht durchsucht (dann das Original)."""
    it = item(req.get("id"))
    sp = processed(req.get("id"), req.get("pipeline")).spectrum
    if sp.yunit in ("D1", "D2", "au"):
        sp = it.sp
    blank = QA.assess(sp.x, sp.y, sp.yunit)["noisy"] if req.get("noise_mask", True) else []
    try:
        return prep(sp.x, sp.y, sp.yunit, blank=blank), sp, blank
    except ValueError as e:
        raise PR.OpError(str(e)) from e


def meta_payload() -> dict:
    return {
        "version": __version__,
        "ops": PR.OPS,
        "algos": {k: v[0] for k, v in SR.ALGOS.items()},
        "exclude": SR.DEFAULT_EXCLUDE,
        "peak_defaults": PK.DEFAULT,
        "yunits": {k: v[0] for k, v in YUNITS.items()},
        "grid": {"x0": float(GRID[0]), "dx": float(GRID[1] - GRID[0]), "n": len(GRID)},
        "libs": STATE.libs.list(),
        "lib_errors": STATE.libs.errors,
        "model_id": MODEL_ID,
        "samples": {k: v[0] for k, v in SM.SAMPLES.items()},
        "out_root": str(STATE.out_root),
        "own_refs": STATE.libs.OWN_REFS,
        "eq_functions": FUNCTIONS_DOC,
    }


def spectrum_payload(iid, pipeline, preview=False) -> dict:
    it = item(iid)
    proc = processed(iid, pipeline)
    sp = proc.spectrum
    out = {"id": iid, "name": it.sp.name, "x": sp.x.astype(np.float32), "y": sp.y.astype(np.float32), "yunit": sp.yunit,
           "steps": proc.steps, "orig": it.sp.describe(), "n": len(sp.x), "quality": QA.assess(sp.x, sp.y, sp.yunit)}
    if preview and pipeline:
        before = processed(iid, pipeline[:-1]).spectrum
        out["before"] = {"x": before.x.astype(np.float32), "y": before.y.astype(np.float32), "yunit": before.yunit}
        if proc.baseline is not None and pipeline[-1].get("op") == "baseline":
            out["baseline"] = proc.baseline.astype(np.float32)
    return out


def hits_payload(res, keep_y=10):
    for k, h in enumerate(res["hits"]):
        if "y" in h and k >= keep_y:
            h.pop("y")
    return {"algo": res["algo"], "hits": res["hits"], "query": res["query"]}


# ----------------------------------------------------------------------------- Ableiten (Differenz, Mittel)
def derive(req) -> list[dict]:
    op = req.get("op")
    ids = req.get("ids") or []
    pipes = req.get("pipelines") or {}
    if op not in ("diff", "avg", "sum") or len(ids) < (2 if op != "avg" else 2):
        raise PR.OpError("Bitte mindestens zwei Spektren wählen.")
    sps = []
    for iid in ids:
        sp = processed(iid, pipes.get(iid) or []).spectrum
        if sp.yunit in ("T", "R"):
            sp = sp.copy(y=PR.to_absorbance(sp.y, sp.yunit), yunit="A")
        sps.append(sp)
    base = sps[0]
    lo = max(s.x[0] for s in sps)
    hi = min(s.x[-1] for s in sps)
    m = (base.x >= lo) & (base.x <= hi)
    if m.sum() < 10:
        raise PR.OpError("Die Spektren überlappen nicht.")
    x = base.x[m]
    ys = [np.interp(x, s.x, s.y) for s in sps]
    if op == "diff":
        b = ys[1]
        f = req.get("factor")
        if f in (None, "", "auto"):
            # Faktor so, dass die Differenz im gewählten Bereich möglichst klein wird (kleinste Quadrate)
            r = req.get("region") or [x[0], x[-1]]
            mm = (x >= min(r)) & (x <= max(r))
            bb = b[mm] - b[mm].mean()
            f = float(np.dot(ys[0][mm] - ys[0][mm].mean(), bb) / (np.dot(bb, bb) or 1.0))
        f = float(f)
        y = ys[0] - f * b
        name = f"{sps[0].name} − {f:.3g}·{sps[1].name}"
        info = {"factor": f}
    elif op == "avg":
        y = np.mean(ys, axis=0)
        name = "Mittel aus " + ", ".join(s.name for s in sps)
        info = {}
    else:
        y = np.sum(ys, axis=0)
        name = "Summe aus " + ", ".join(s.name for s in sps)
        info = {}
    unit = sps[0].yunit if all(s.yunit == sps[0].yunit for s in sps) else "au"
    refs = []                                  # Herkunft enthaltener Bibliotheksreferenzen weitergeben
    for s in sps:
        for ref in s.meta.get("refs") or []:
            if ref not in refs:
                refs.append(ref)
    meta = {"format": "berechnet", "origin": name}
    if refs:
        meta["refs"] = refs
    sp = Spectrum(name[:120], x, y, unit, meta)
    fname = re.sub(r"[^\w\-]+", "_", name)[:60].strip("_") + ".jdx"
    raw = to_jcamp(sp, name).encode("utf-8")
    d = load_file(raw, fname)
    for x_ in d:
        x_.update(info)
    return d


# ----------------------------------------------------------------------------- Export
def _csv(path: Path, header, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(header)
        for r in rows:
            w.writerow(["" if v is None else (f"{v:.6g}".replace(".", ",") if isinstance(v, float) else v) for v in r])


def export(req) -> dict:
    import matplotlib.pyplot as plt
    it = item(req.get("id"))
    state = state_of(req)
    a = run(it.sp, state, "de")
    sp = a.sp
    stem = re.sub(r"[^\w\-]+", "_", it.sp.name).strip("_") or "Spektrum"
    folder = STATE.out_root / stem
    if folder.exists() and any(folder.iterdir()) and not req.get("overwrite"):
        return {"exists": True, "folder": str(folder)}
    folder.mkdir(parents=True, exist_ok=True)
    files = []

    def fig(f, name):
        f.savefig(folder / name, dpi=200, bbox_inches="tight")
        plt.close(f)
        files.append(name)

    regions = [(r["lo"], r["hi"], r["name"]) for r in a.bands]
    fig(C.fig_spectra([{"name": a.name, "x": sp.x, "y": sp.y}], sp.yunit, "de", peaks=a.peaks, regions=regions), "spektrum.png")
    (folder / "spektrum.jdx").write_text(to_jcamp(sp, a.name, {"$PROCESSING": "; ".join(a.proc.steps)}), encoding="utf-8")
    (folder / "spektrum.csv").write_text(to_csv(sp), encoding="utf-8")
    files += ["spektrum.jdx", "spektrum.csv"]
    if a.peaks:
        _csv(folder / "banden.csv", ["Wellenzahl_cm-1", "y", "rel_Intensitaet", "Staerke", "FWHM_cm-1", "Flaeche", "Zuordnung"],
             [[p["x"], p["y"], p["rel"], p["strength"], p["fwhm"], p["area"], " | ".join(p.get("assign") or [])] for p in a.peaks])
        files.append("banden.csv")
    if a.groups:
        _csv(folder / "gruppen.csv", ["Stoffklasse", "Bewertung", "Punkte", "Belege"],
             [[c["name"], c["verdict"], c["score"],
               " | ".join(f"{e['band']} ({e['status']}{'' if e.get('at') is None else ', %.0f' % e['at']})"
                          for e in c.get("evidence") or [])] for c in a.groups["classes"]])
        files.append("gruppen.csv")
    if a.bands:
        _csv(folder / "flaechen.csv", ["Bande", "von", "bis", "Flaeche", "Hoehe", "Lage", "Schwerpunkt"],
             [[r["name"], r["lo"], r["hi"], r["area"], r["height"], r["pos"], r.get("centroid")] for r in a.bands] +
             [[f"Verhältnis {r['name']}", None, None, r["value"], None, None, None] for r in a.ratios])
        files.append("flaechen.csv")
    s = state.get("search") or {}
    if s.get("hits"):
        _csv(folder / "treffer.csv", ["Rang", "Referenz", "Bibliothek", "Kategorie", "CAS", "HQI", "Quelle", "Messart/Lizenz"],
             [[h.get("rank"), h["name"], h.get("lib_name"), h.get("category"), h.get("cas"), h["hqi"], h.get("source"),
               h.get("comment")] for h in s["hits"]])
        files.append("treffer.csv")
        q = arr(s.get("query"))
        hits = [dict(h, y=arr(h["y"])) for h in s["hits"] if h.get("y") is not None]
        if q is not None and hits:
            fig(C.fig_search(GRID, q, hits, "de", a.name), "suche.png")
    m = state.get("mixture") or {}
    if m.get("components"):
        _csv(folder / "mischung.csv", ["Komponente", "Bibliothek", "Anteil_Prozent", "Quelle"],
             [[c["name"], c.get("lib_name"), 100 * c["frac"], c.get("source")] for c in m["components"]] + [["HQI", "", m["hqi"], ""]])
        files.append("mischung.csv")
        if m.get("query") is not None:
            combo = dict(m, fit=arr(m["fit"]), residual=arr(m["residual"]),
                         components=[dict(c, y=arr(c["y"])) for c in m["components"]])
            fig(C.fig_mixture(GRID, arr(m["query"]), combo, "de", a.name), "mischung.png")
    o = it.sp
    lines = [f"Spektrum: {o.name}  (Datei {it.fname}, {o.x[0]:.0f}–{o.x[-1]:.0f} cm⁻¹, {len(o.x)} Punkte, {YUNITS.get(o.yunit, ('?',))[0]})",
             "", "Bearbeitung:"]
    lines += [f"  {i}. {t}" for i, t in enumerate(a.proc.steps, 1)] or ["  (keine)"]
    lines += ["", "Protokoll als JSON (in der Oberfläche unter Bearbeiten ▸ Protokoll laden wieder einlesbar):",
              json.dumps(state.get("pipeline") or [], ensure_ascii=False)]
    if s.get("hits"):
        lines += ["", f"Suche ({SR.ALGOS.get(s.get('algo', 'corr'), ('?',))[0]}): " +
                  ", ".join(f"{h['name']} {h['hqi']:.1f}" for h in s["hits"][:5])]
    if any("Modell" in (h.get("lib_name") or "") for h in s.get("hits") or []):
        lines.append("Hinweis: Die Modellbibliothek enthält berechnete, keine gemessenen Referenzspektren.")
    # Quellen aller Referenzen, die in Treffern, Mischung oder im Spektrum selbst vorkommen
    used = list(o.meta.get("refs") or []) + list((s.get("hits") or [])[:10]) + list(m.get("components") or [])
    srcs = []
    for h in used:
        line = f"{h.get('name', '')}: {h.get('lib_name', '')}" + (f" – {h['source']}" if h.get("source") else "")
        if line not in srcs:
            srcs.append(line)
    if any(str(h.get("lib")).startswith("openspecy") for h in used):
        srcs.insert(0, "Open Specy: Cowger W. et al. (2025), Analytical Chemistry, doi:10.1021/acs.analchem.5c00962")
    if srcs:
        lines += ["", "Quellen der Referenzspektren:"] + [f"  {x}" for x in srcs]
    (folder / "protokoll.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    files.append("protokoll.txt")
    return {"folder": str(folder), "files": files}


# ----------------------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "FolioFTIR/1.0"

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
        self._send(code, json.dumps(clean(obj), ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_FILE:
            raise PR.OpError("Datei zu gross.")
        return self.rfile.read(n) if n else b""

    def _req(self) -> dict:
        return json.loads(self._body() or b"{}")

    def do_GET(self):
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        if url.path in ("/labref.js", "/labindex.js", "/labenv.js", "/labui.js", "/labboard.js", "/laboverview.js", "/labimport.js"):   # UI-05, I-02
            return self._send(200, labcite.web_asset(url.path[1:]), "text/javascript; charset=utf-8")
        if url.path == "/api/meta":
            return self._json(meta_payload())
        self._send(404, b"nicht gefunden", "text/plain")

    def do_POST(self):
        url = urlparse(self.path)
        origin = self.headers.get("Origin")
        if origin and not ORIGIN_OK.match(origin):
            return self._json({"error": "Fremde Herkunft abgelehnt"}, 403)
        try:
            return self._route(url)
        except (PR.OpError, ReadError, EnvError, ValueError) as e:
            return self._json({"error": str(e)}, 400)
        except PermissionError as e:
            return self._json({"error": str(e)}, 403)
        except LookupError as e:
            return self._json({"error": str(e).strip("'\"")}, 404)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    def _route(self, url):
        p = url.path
        qs = parse_qs(url.query)
        if p == "/api/load":
            name = unquote(qs.get("name", ["Spektrum.csv"])[0])
            return self._json({"spectra": load_file(self._body(), name)})
        if p == "/api/sample":
            which = self._req().get("which") or "pet"
            data, name = SM.make(which)
            return self._json({"spectra": load_file(data, name)})
        if p == "/api/remove":
            iid = self._req().get("id")
            with STATE.lock:
                STATE.items.pop(iid, None)
                for k in [k for k in STATE.cache if k[0] == iid]:
                    STATE.cache.pop(k, None)
            STATE.envs.forget(str(iid))
            return self._json({"ok": True})
        if p.startswith("/api/env/"):
            return self._json(STATE.envs.route(p.rsplit("/", 1)[1], self._req(), reload_env))
        if p.startswith("/api/index/"):                # A7: Projektindex
            import labindex
            return self._json(labindex.route(STATE.envs, "ftir", __version__, p.rsplit("/", 1)[1], self._req()))
        if p.startswith("/api/prov/"):                 # A8: Herkunftskette, Abhängigkeiten
            import labprov
            return self._json(labprov.route(STATE.envs, p.rsplit("/", 1)[1], self._req()))
        if p == "/api/share/peaks":
            return self._json(share_peaks(self._req()))
        if p == "/api/dataset":                        # DP-13: Spektren aus einem Datensatz der Datenaufbereitung
            return self._json(ds_list())
        if p == "/api/dataset/spectra":
            return self._json({"spectra": ds_spectra(self._req())})
        if p == "/api/dataset/refresh":
            return self._json(ds_refresh(self._req()))
        if p == "/api/rename":
            req = self._req()
            it = item(req.get("id"))
            it.sp.name = (req.get("name") or it.sp.name).strip()[:120]
            STATE.envs.set_name(str(req.get("id")), it.sp.name)
            with STATE.lock:
                for k in [k for k in STATE.cache if k[0] == req.get("id")]:
                    STATE.cache.pop(k, None)
            return self._json({"ok": True, "name": it.sp.name})
        if p == "/api/spectrum":
            req = self._req()
            return self._json(spectrum_payload(req.get("id"), req.get("pipeline") or [], bool(req.get("preview"))))
        if p == "/api/analyse":
            # Peaks, Gruppen, Flächen (alles, was im Arbeitsstand angefordert ist)
            req = self._req()
            it = item(req.get("id"))
            st = state_of(req)
            st["mixture"] = None
            st["search"] = {"hits": ((req.get("search") or {}).get("hits") or [])[:1]}   # nur für hqi1
            a = run(it.sp, st, "de")
            return self._json({"peaks": a.peaks, "groups": a.groups, "bands": a.bands, "ratios": a.ratios,
                               "yunit": a.sp.yunit, "equations": a.equations,
                               "variables": [{"name": k, **v} for k, v in a.variables.items()]})
        if p == "/api/assign":
            req = self._req()
            return self._json({"assign": GR.assign(float(req.get("x")), req.get("strength") or "m", "de", n=6)})
        if p == "/api/grouptable":
            return self._json({"table": GR.table("de")})
        if p == "/api/integrate":
            req = self._req()
            sp = processed(req.get("id"), req.get("pipeline")).spectrum
            return self._json(PK.integrate(sp.x, sp.y, req.get("lo"), req.get("hi"), sp.yunit, req.get("base", "linear")))
        if p == "/api/search":
            req = self._req()
            q, _, blank = query_of(req)
            res = SR.search(q, libs_of(req.get("libs")), req.get("algo") or "corr", req.get("include"),
                            req.get("exclude", SR.DEFAULT_EXCLUDE), int(req.get("n") or 25), req.get("category") or None,
                            collapse=bool(req.get("collapse", True)))
            return self._json({**hits_payload(res), "masked": blank})
        if p == "/api/mixture":
            req = self._req()
            q, _, blank = query_of(req)
            res = SR.mixture(q, libs_of(req.get("libs")), req.get("include"), req.get("exclude", SR.DEFAULT_EXCLUDE),
                             int(req.get("max") or 3))
            return self._json({"combos": res["combos"], "query": res.get("query"), "note": res.get("note", ""),
                               "masked": blank})
        if p == "/api/derive":
            return self._json({"spectra": derive(self._req())})
        if p == "/api/save":
            req = self._req()
            it = item(req.get("id"))
            sp = processed(req.get("id"), req.get("pipeline")).spectrum
            stem = re.sub(r"[^\w\-]+", "_", it.sp.name).strip("_") or "Spektrum"
            if req.get("format") == "csv":
                return self._json({"text": to_csv(sp), "filename": stem + ".csv", "mime": "text/csv"})
            return self._json({"text": to_jcamp(sp, it.sp.name), "filename": stem + ".jdx", "mime": "chemical/x-jcamp-dx"})
        if p.startswith("/api/library/"):
            return self._library(p.rsplit("/", 1)[1], qs)
        if p.startswith("/api/equations/"):
            return self._equations(p.rsplit("/", 1)[1])
        if p == "/api/export":
            return self._json(export(self._req()))
        if p == "/api/open":
            folder = Path(self._req().get("folder", ""))
            if folder.exists() and STATE.out_root.resolve() in folder.resolve().parents and hasattr(os, "startfile"):
                os.startfile(str(folder))  # noqa: S606 - nur Ordner unterhalb des Ausgabeordners
            return self._json({"ok": True})
        if p in ("/api/bundle", "/api/bundle/rebuild"):
            return self._bundle(p)
        return self._send(404, b"nicht gefunden", "text/plain")

    # ------------------------------------------------------------------- Bibliotheken
    def _library(self, action, qs):
        L = STATE.libs
        if action == "list":
            return self._json({"libs": L.list(), "errors": L.errors})
        if action == "import":
            lid = qs.get("lib", [""])[0]
            name = unquote(qs.get("name", ["Referenz.jdx"])[0])
            category = unquote(qs.get("category", [""])[0])
            label = unquote(qs.get("label", [""])[0]).strip()
            cite = None
            if qs.get("cite"):
                try:
                    cite = json.loads(unquote(qs["cite"][0]))
                except ValueError:
                    raise ValueError("Quelle: unlesbar") from None
            from .library import clean_cite
            cite = clean_cite(cite)            # prüfen, bevor etwas gespeichert wird
            lib = L.own_refs() if lid == L.OWN_REFS else L.get(lid)
            sps = load_bytes(self._body(), name)
            added, failed = [], []
            with L.lock:
                for sp in sps:
                    try:
                        nm = label if (label and len(sps) == 1) else sp.name
                        meta = {"name": nm, "category": category, "source": "" if cite else name}
                        if cite:
                            meta["cite"] = cite
                            meta["comment"] = f"Datei: {name}"
                        added.append(lib.add(sp, meta))
                    except ValueError as e:
                        failed.append(f"{sp.name}: {e}")
                lib.save()
            out = {"added": added, "failed": failed, "lib": lib.info(), "libs": L.list()}
            if qs.get("open", ["0"])[0] == "1":     # „Referenz aus Datei einblenden“: gleich als Spektrum öffnen
                out["spectra"] = [d for e in added for d in self._open_entry(lib, e["id"])]
            return self._json(out)
        req = self._req()
        if action == "create":
            lib = L.create(req.get("name", ""), req.get("description", ""), req.get("cite"))
            return self._json({"lib": lib.info(), "libs": L.list()})
        if action == "delete":
            L.delete(req.get("lib"))
            return self._json({"libs": L.list()})
        lib = L.get(req.get("lib"))
        if action == "entries":
            return self._json({"lib": lib.info(), "entries": lib.entries})
        if action == "add":
            sp = processed(req.get("id"), req.get("pipeline")).spectrum
            if sp.yunit in ("D1", "D2"):
                raise PR.OpError("Ableitungen lassen sich nicht als Referenz speichern.")
            with L.lock:
                e = lib.add(sp, req.get("meta") or {})
                lib.save()
            return self._json({"entry": e, "lib": lib.info()})
        if action == "remove":
            with L.lock:
                lib.remove(req.get("eid"))
                lib.save()
            return self._json({"lib": lib.info()})
        if action == "update":
            with L.lock:
                e = lib.update(req.get("eid"), req.get("meta") or {})
                lib.save()
            return self._json({"entry": e})
        if action == "spectrum":
            sp = lib.spectrum(req.get("eid"))
            return self._json({"name": sp.name, "x": sp.x.astype(np.float32), "y": sp.y.astype(np.float32), "yunit": sp.yunit,
                               "grid": lib.G[lib.index(req.get("eid"))]})
        if action == "open":
            return self._json({"spectra": self._open_entry(lib, req.get("eid"))})
        if action == "export":
            stem = re.sub(r"[^\w\-]+", "_", lib.name).strip("_") or "Bibliothek"
            return self._json({"text": lib.to_jcamp(), "filename": stem + ".jdx", "mime": "chemical/x-jcamp-dx"})
        return self._send(404, b"nicht gefunden", "text/plain")

    @staticmethod
    def _open_entry(lib, eid) -> list[dict]:
        sp = lib.spectrum(eid)
        fname = re.sub(r"[^\w\-]+", "_", sp.name).strip("_")[:60] + ".jdx"
        e = lib.entries[lib.index(eid)]
        sp.meta["refs"] = [lib.ref_of(e)]      # Herkunft geht mit (Bericht zitiert Bibliothek und Quelle)
        raw = to_jcamp(sp, sp.name, {"ORIGIN": f"{lib.name}: {e.get('source') or ''}", "CAS REGISTRY NO": e.get("cas")}).encode("utf-8")
        return load_file(raw, fname)

    # ------------------------------------------------------------------- Eigene Gleichungen
    def _equations(self, action):
        from labcalc import formulas as F
        S = STATE.eqs
        if action == "list":
            return self._json({"items": S.items()})
        req = self._req()
        if action == "save":
            d = F.clean_defs([req.get("item") or {}])
            if not d:
                raise ValueError("Gleichung leer")
            x = d[0]
            err = F.check_name(x["sym"], reserved=("A", "y", "area", "area0", "height"))
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
            return self._json({"text": json.dumps(S.export(), ensure_ascii=False, indent=1), "filename": "eigene_gleichungen.json",
                               "mime": "application/json"})
        if action == "import":
            n = S.import_(req.get("data") or {}, bool(req.get("replace")))
            return self._json({"added": n, "items": S.items()})
        return self._send(404, b"nicht gefunden", "text/plain")

    # ------------------------------------------------------------------- Bericht
    def _bundle(self, p):
        from . import bundle as B
        req = self._req()
        items, req_items = [], []
        if p == "/api/bundle":
            for x in req.get("items", []):
                it = item(x.get("id"))
                state = x.get("state") or {}
                items.append((it.raw, it.fname, it.idx, state))
                rx = {"name": it.fname, "idx": it.idx, "label": it.sp.name, "state": state}
                src = (it.sp.meta or {}).get("dataset") or {}
                if src.get("share"):                   # DP-13: Datensatz-Version für Herkunft und Aufbewahrung (labprov)
                    rx["dataset"] = {"share": src["share"], "version": src.get("version"), "title": src.get("title")}
                req_items.append(rx)
        else:
            src = req.get("source") or {}
            files = {k: base64.b64decode(v) for k, v in (src.get("files") or {}).items()}
            for x in (src.get("request") or {}).get("items", []):
                data = files.get(x["name"])
                if data is None:
                    return self._json({"error": f"Quelldatei {x['name']} fehlt im Bundle"}, 400)
                items.append((data, x["name"], int(x.get("idx") or 0), x.get("state") or {}))
                req_items.append(x)
            old = src.get("request") or {}
            req = {**old, **{k: v for k, v in req.items() if k != "source"}}
        if not items:
            return self._json({"error": "Kein Spektrum gewählt."}, 400)
        # umbenannte Spektren: Name aus der Anfrage
        labelled = []
        for (raw, fname, idx, state), x in zip(items, req_items):
            st = dict(state)
            if x.get("label"):
                st["_label"] = x["label"]
            labelled.append((raw, fname, idx, st))
        request = {"items": req_items, "lang": req.get("lang", "de"), "include": req.get("include") or {},
                   "title": req.get("title") or None, "slug": req.get("slug") or None}
        b = B.build(labelled, request, lang=request["lang"], include=request["include"], title=request["title"])
        return self._json(b)


def main(argv=None):
    global STATE
    ap = argparse.ArgumentParser(description="FTIR, lokale Oberfläche")
    ap.add_argument("--port", type=int, default=8767)
    ap.add_argument("--out", default=str(ROOT / "Ausgaben"), help="Wurzelordner der Exporte und Bibliotheken")
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args(argv)
    STATE = State(Path(a.out).resolve())
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = f"http://127.0.0.1:{a.port}/"
    print(f"FTIR läuft auf {url}  (Beenden mit Strg+C)")
    print(f"Exporte und Bibliotheken unter {STATE.out_root}")
    if STATE.libs.errors:
        print("Bibliotheken mit Fehlern:", "; ".join(STATE.libs.errors))
    if not a.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
