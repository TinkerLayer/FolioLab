"""Lokale Oberfläche des TGA-Moduls.

Läuft nur auf 127.0.0.1 und ruft nichts aus dem Netz ab. Läufe bleiben im Speicher; geschrieben wird nur bei
„Exportieren“, in eigene Bibliotheken (<ausgaben>/bibliotheken) und in eigene Gleichungen (<ausgaben>/eigene_gleichungen.json).

Start:  python -m tga.server  [--port 8768] [--out Ausgaben] [--no-browser]
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
from . import composition as CO  # noqa: E402
from . import deconv as DC  # noqa: E402
from . import kinetics as KI  # noqa: E402
from . import process as PR  # noqa: E402
from . import search as SR  # noqa: E402
from . import steps as ST  # noqa: E402
from . import synth as SY  # noqa: E402
from . import uncert as UC  # noqa: E402
from .analysis import run as analyse  # noqa: E402
from .library import GRID, MODEL_ID, Libraries  # noqa: E402
from .readers import ROLE_LABEL, ReadError, Run, load_bytes, to_csv  # noqa: E402
from .refs import REFS  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
ROOT = Path(__file__).resolve().parents[1]
ORIGIN_OK = re.compile(r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$")
MAX_FILE = 100 * 1024 * 1024


class Item:
    def __init__(self, run: Run, raw: bytes, fname: str, mapping: dict | None):
        self.run, self.raw, self.fname, self.mapping = run, raw, fname, mapping


class State:
    def __init__(self, out_root: Path):
        self.items: dict[str, Item] = {}
        self.cache: OrderedDict = OrderedDict()
        self.lock = threading.Lock()
        self.out_root = out_root
        self.libs = Libraries(out_root / "bibliotheken")
        self.eqs = JsonStore(out_root / "eigene_gleichungen.json", kind="folio-gleichungen/1")
        self.egs: dict = {}                     # TGA-04: Gasspektren-Serien (nur im Speicher)
        self.envs = ModuleEnvs(out_root, "tga")  # A2: Umgebungen im aktiven Projekt


STATE: State | None = None


def egs_payload(sid: str, s, k: int = 5) -> dict:
    from . import egs as EG
    gs = EG.gram_schmidt(s, k)
    return {"id": sid, "name": s.name, "n": int(len(s.t)), "t": s.t.astype(np.float32), "gs": gs.astype(np.float32),
            "x": [float(s.x.min()), float(s.x.max())], "meta": s.meta, "k": k, "refs": EG.REFS}


def egs_route(p: str, req: dict, body: bytes | None, name: str | None) -> dict:
    """/api/egs/load|sample|gs|spectrum|chemigram (TGA-04)."""
    import uuid
    from . import egs as EG
    if p == "load":
        s = EG.load_bytes(body or b"", name or "serie.csv")
        sid = uuid.uuid4().hex[:8]
        with STATE.lock:
            STATE.egs = dict(list(STATE.egs.items())[-3:])          # höchstens vier Serien im Speicher
            STATE.egs[sid] = s
        return egs_payload(sid, s)
    if p == "sample":
        raw, _ = EG.synth(gas_peaks=((12.0, 2.0), (26.0, 3.0)))
        return egs_route("load", {}, raw, "Beispiel Gasanalyse.csv")
    s = STATE.egs.get(str(req.get("id")))
    if s is None:
        raise LookupError("Gasspektren-Serie nicht geladen")
    k = int(req.get("k") or 5)
    if p == "gs":
        return egs_payload(str(req.get("id")), s, k)
    if p == "spectrum":
        sp = EG.spectrum_at(s, float(req.get("t") or 0), k, bool(req.get("subtract", True)))
        title = f"{s.name} – Gasspektrum bei {sp['t']:.2f} min".replace(f"{sp['t']:.2f}", f"{sp['t']:.2f}".replace(".", ",")) + (" (Hintergrund abgezogen)" if sp["subtracted"] else "")
        return {"t": sp["t"], "i": sp["i"], "x": sp["x"].astype(np.float32), "y": sp["y"].astype(np.float32),
                "title": title, "jcamp": EG.to_jcamp(sp["x"], sp["y"], title, {"$FOLIO ORIGIN": "TGA-FTIR " + s.name})}
    if p == "chemigram":
        c = EG.chemigram(s, float(req["lo"]), float(req["hi"]))
        return {"t": s.t.astype(np.float32), "y": c.astype(np.float32), "lo": float(req["lo"]), "hi": float(req["hi"])}
    raise LookupError("unbekannt")


def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items() if not str(k).startswith("_")}
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
    if isinstance(o, Path):
        return str(o)
    return o


def item(iid) -> Item:
    it = STATE.items.get(iid)
    if it is None:
        raise LookupError("Lauf nicht geladen")
    return it


def processed(iid, pipeline) -> Run:
    key = (iid, json.dumps(pipeline or [], sort_keys=True))
    with STATE.lock:
        if key in STATE.cache:
            STATE.cache.move_to_end(key)
            return STATE.cache[key]
    r = PR.apply(item(iid).run, pipeline or []).run
    with STATE.lock:
        STATE.cache[key] = r
        while len(STATE.cache) > 24:
            STATE.cache.popitem(last=False)
    return r


def _drop_cache(iid):
    with STATE.lock:
        for k in [k for k in STATE.cache if k[0] == iid]:
            STATE.cache.pop(k, None)


def describe(iid) -> dict:
    it = item(iid)
    d = it.run.describe()
    d.update(id=iid, file=it.fname, mapping=it.mapping)
    src = (it.run.meta or {}).get("dataset") or {}
    if src.get("share"):                               # DP-13: neueste Version des Datensatzes (für „aktualisieren“)
        d["ds_latest"] = ds_latest(src["share"])
    return d


def add_item(run: Run, raw: bytes, fname: str, mapping=None, idx: int = 0, iid: str | None = None) -> dict:
    keep = iid is None
    iid = iid or uuid.uuid4().hex[:10]
    with STATE.lock:
        STATE.items[iid] = Item(run, raw, fname, mapping)
        STATE.items[iid].idx = int(idx)
    if keep:
        STATE.envs.remember(iid, raw, fname, idx, run.name, mapping=mapping)
    return describe(iid)


def env_bundle(stored, report: dict, lang: str) -> dict:
    """Bündel einer gespeicherten Umgebung (nicht der aktiven) aus ihren Läufen und dem Berichtsauftrag der
    Seite (Körper von /api/bundle: items[{id, state}], kinetics)."""
    from . import bundle as B
    by_id = {iid: (raw, fname, idx, name, extra) for iid, raw, fname, idx, name, extra in stored}
    labelled, req_items = [], []
    for x in report.get("items") or []:
        got = by_id.get(x.get("id"))
        if got is None:
            continue
        raw, fname, idx, name, extra = got
        mapping = (extra or {}).get("mapping")
        if not name:
            try:
                name = load_bytes(raw, fname, mapping)[idx].name
            except (ReadError, IndexError, ValueError):
                continue
        state = x.get("state") or {}
        rx = {"name": fname, "mapping": mapping, "label": name, "state": state}
        if idx:
            rx["idx"] = int(idx)
        labelled.append((raw, fname, mapping, dict(state, _label=name, _idx=int(idx or 0))))
        req_items.append(rx)
    if not labelled:
        raise EnvError("Kein Lauf dieser Umgebung im Berichtsstand")
    request = {"items": req_items, "lang": lang, "include": report.get("include") or {},
               "title": report.get("title") or None, "slug": None, "kinetics": report.get("kinetics")}
    if report.get("unc_replicates"):
        request["unc_replicates"] = True
    if any(UC.active(x[3]) for x in labelled):
        own_instruments()
    return B.build(labelled, request, lang=lang, include=request["include"], title=request["title"])


def load_file(data: bytes, name: str, mapping=None) -> list[dict]:
    return [add_item(r, data, name, mapping, i) for i, r in enumerate(load_bytes(data, name, mapping))]


def reload_env() -> list[dict]:
    """Läufe der aktiven Umgebung neu einlesen (A2); IDs, Namen und Spaltenzuordnung bleiben."""
    with STATE.lock:
        STATE.items.clear()
        STATE.cache.clear()
    out = []
    for iid, raw, fname, idx, name, extra in STATE.envs.stored():
        try:
            run = load_bytes(raw, fname, extra.get("mapping"))[idx]
        except (ReadError, IndexError, ValueError):
            continue
        if name:
            run.name = name
        out.append(add_item(run, raw, fname, extra.get("mapping"), idx, iid))
    return out


def _dec(a, n=4000):
    step = max(1, len(a) // n)
    return a[::step]


def share_steps(req) -> dict:
    """A3: Stufentabelle eines Laufs teilen – nur Zahlen (Verlust, Temperaturen, Rückstand), nie die Kurve.
    Dieselbe Messung erneut geteilt ergibt eine neue Version derselben Freigabe."""
    from labshare import Sharebox
    iid = req.get("id")
    it = item(iid)
    if UC.active(req.get("state") or {}):
        own_instruments()
    a = analyse(it.run, req.get("state") or {}, "de")
    if not a.steps:
        raise ValueError("Keine Stufen gefunden – nichts zu teilen.")
    meta = it.run.meta or {}
    cond0 = {k: meta[k] for k in ("rate", "atmosphere", "gas") if isinstance(meta.get(k), (int, float, str))}
    uq = UC.plain(a.unc)                               # Messunsicherheit reist mit (quantity.u, Standardunsicherheit)

    def q(value, key):
        out = {"value": round(float(value), 3), "unit": "%"}
        x = uq.get(key)
        if x and x.get("u"):
            out["u"] = float(f"{x['u']:.3g}")
            out["unc"] = {"method": x.get("method"), "U": x.get("U")}
        return out
    outs = []
    for i, s in enumerate(a.steps, 1):
        c = dict(cond0, **{k: round(float(s[k]), 2) for k in ("T_onset", "T_peak", "T_endset") if s.get(k) is not None})
        outs.append({"key": f"step{i}-loss", "label": f"Stufe {i}: Massenverlust", "quantity": q(s["loss"], f"step{s['no']}-loss"),
                     "conditions": c})
    res = (a.st.get("residue") or {}).get("end")
    if isinstance(res, (int, float)):
        outs.append({"key": "residue", "label": "Rückstand am Ende", "quantity": q(res, "residue"), "conditions": cond0})
    envs = STATE.envs
    envs.ensure()
    box = Sharebox(envs.suite, envs.project)
    prev = next((m for m in box.list(kind="tga.steps") if (m.get("producer") or {}).get("item") == iid
                 and (m.get("producer") or {}).get("env") == envs.eid), None)
    env_name = next((e["name"] for e in envs.envs.list() if e["id"] == envs.eid), envs.eid)
    prod = {"module": "tga", "env": envs.eid, "env_name": env_name, "item": iid, "item_name": it.run.name,
            "raw": (envs.items.get(iid) or {}).get("raw"),  # A8: Rohdatei der Kette, auch wenn der Eintrag später geschlossen wird
            "module_version": __version__}
    return box.publish(prod, "tga.steps", it.run.name, outs, req.get("recipients") or ["elementrechner"],
                       sources=[{"protocol": a.proc.steps}], share_id=prev["id"] if prev else None)


# ----------------------------------------------------------------------------- DP-13: Lauf aus Datensatz
def _box():
    from labshare import Sharebox
    STATE.envs.ensure()
    return Sharebox(STATE.envs.suite, STATE.envs.project)


def ds_latest(sid: str) -> int | None:
    try:
        return _box().resolve({"id": sid, "mode": "live"}, "tga").get("latest")
    except (EnvError, OSError, ValueError):
        return None


def ds_list() -> dict:
    """Datensätze (`data.table`), die an die TGA adressiert sind, mit Spalten und einem Rollenvorschlag je Spalte."""
    from labshare import DATA_KIND
    from . import dataset as DS
    box = _box()
    out = []
    for m in box.list("tga", DATA_KIND):
        try:
            env = box.get(m["id"], None, "tga")
        except EnvError:
            continue
        h, p = env.get("dataset") or {}, m.get("producer") or {}
        out.append({"id": m["id"], "title": m.get("title"), "latest": m.get("latest"), "modified": m.get("modified"),
                    "rows": h.get("rows"), "producer": {k: p.get(k) for k in ("module", "env_name", "item_name")},
                    "columns": [dict({k: c.get(k) for k in ("key", "name", "unit", "dtype", "kind")}, guess=DS.guess(c))
                                for c in h.get("columns") or []]})
    return {"datasets": out}


def ds_open(sid: str, mode: str, version=None):
    """(Datensatz, Umschlag) einer Freigabe; live = neueste Version, pin = die genannte (sonst die neueste)."""
    from labshare import dataset_of
    box = _box()
    res = box.resolve({"id": sid, "mode": mode, "version": version}, "tga")
    if res["status"] == "failed":
        raise EnvError(res.get("error") or "Datensatz nicht verfügbar")
    env = res["envelope"]
    return dataset_of(env, box.base / sid), env


def _ds_source(sid: str, env: dict, mode: str) -> dict:
    p = env.get("producer") or {}
    return {"share": sid, "title": env.get("title"), "version": env["version"], "mode": mode,
            "producer": {k: p.get(k) for k in ("module", "env_name", "item_name")}}


def ds_run(req) -> list[dict]:
    """Lauf aus gewählten Spalten eines Datensatzes; wird wie eine geladene Datei in der Umgebung gespeichert."""
    from . import dataset as DS
    sid = str(req.get("id") or "")
    mode = "pin" if req.get("mode") == "pin" else "live"
    ds, env = ds_open(sid, mode, req.get("version"))
    raw, fname = DS.make_raw(ds, req.get("roles") or {}, _ds_source(sid, env, mode))
    out = load_file(raw, fname)
    for d in out:
        STATE.envs.set_extra(d["id"], dataset={"share": sid, "version": env["version"], "mode": mode})
    return out


def ds_refresh(req) -> dict:
    """Lauf aus einem Datensatz auf die neueste (oder genannte) Version bringen; Name, Zuordnung und ID bleiben."""
    from . import dataset as DS
    iid = str(req.get("id") or "")
    it = item(iid)
    src = (it.run.meta or {}).get("dataset") or {}
    if not src.get("share"):
        raise ValueError("Dieser Lauf stammt nicht aus einem Datensatz.")
    ds, env = ds_open(src["share"], "pin" if req.get("version") else "live", req.get("version"))
    if env["version"] == src.get("version"):
        return {"run": describe(iid), "changed": False}
    roles = {r: c.get("key") for r, c in (src.get("columns") or {}).items()}
    raw, fname = DS.make_raw(ds, roles, _ds_source(src["share"], env, src.get("mode") or "live"))
    run = load_bytes(raw, fname, it.mapping)[0]
    run.name = it.run.name
    with STATE.lock:
        STATE.items[iid] = Item(run, raw, fname, it.mapping)
    STATE.envs.replace_raw(iid, raw, fname)
    STATE.envs.set_extra(iid, dataset={"share": src["share"], "version": env["version"], "mode": src.get("mode") or "live"})
    _drop_cache(iid)
    return {"run": describe(iid), "changed": True}


def own_instruments():
    """Eigene Messmittel der Suite für labcalc.uncertainty bekannt machen (vor jeder Auswertung mit Unsicherheit)."""
    try:
        import labunc
        labunc.load_own(STATE.envs)
    except Exception:  # noqa: BLE001 – ohne Projekt nur die eingebauten Messmittel
        pass


def replicates_payload(req) -> dict:
    """Mittelwert ± U aus Läufen derselben Probe (Typ A aus der Streuung, Typ B aus den Einzelbudgets)."""
    own_instruments()
    lang = req.get("lang") if req.get("lang") in ("de", "en") else "de"
    analyses = [analyse(item(x.get("id")).run, x.get("state") or {}, lang) for x in req.get("items") or []]
    st = (req.get("items") or [{}])[0].get("state") or {}
    return UC.replicates(analyses, st, lang)


def run_payload(iid, state, lang="de") -> dict:
    it = item(iid)
    if UC.active(state or {}):
        own_instruments()
    a = analyse(it.run, state or {}, lang if lang in ("de", "en") else "de")
    r = a.run
    d = a.st["dtg"]
    step = max(1, len(r.m) // 4000)
    sl = slice(None, None, step)
    steps = a.steps
    return {
        "id": iid, "name": it.run.name, "orig": it.run.describe(), "proc": a.proc.steps, "unit": r.unit, "m0": r.m0,
        "ref": r.meta.get("ref"),
        "x": {"T": r.T[sl].astype(np.float32), "t": r.time()[sl].astype(np.float32)},
        "m": r.pct()[sl].astype(np.float32),
        "dtg": {"dT": (-d["dT"][sl]).astype(np.float32), "dt": (-d["dt"][sl]).astype(np.float32)},
        "extra": {k: v[sl].astype(np.float32) for k, v in r.extra.items() if k in ("hf", "Tprog")},
        "steps": steps, "loss_T": a.st["loss_T"], "residue": a.st["residue"], "segments": a.st["segments"], "iso": a.st["iso"],
        "dtg_points": d["points"], "comp": a.comp, "reactions": a.reactions, "calib": a.calib, "deconv": a.deconv, "dsc": a.dsc,
        "equations": a.equations, "variables": [{"name": k, **v} for k, v in a.variables.items()],
        "decim": step, "unc": a.unc,
    }


def meta_payload() -> dict:
    return {
        "version": __version__, "ops": PR.OPS, "roles": ROLE_LABEL, "libs": STATE.libs.list(), "lib_errors": STATE.libs.errors,
        "model_id": MODEL_ID, "samples": {k: v[0] for k, v in SY.SAMPLES.items()}, "reactions": CO.reactions(),
        "presets": {k: {"label": v["de"], "params": v["params"]} for k, v in CO.PRESETS.items()},
        "deconv_presets": DC.PRESETS, "its90": CO.ITS90, "models": {k: v[0] for k, v in KI.MODELS.items()},
        "refs": {k: {"short": labcite.short(v), "text": labcite.text(v)} for k, v in REFS.items()},
        "grid": {"x0": float(GRID[0]), "dx": 1.0, "n": len(GRID)}, "out_root": str(STATE.out_root),
        "step_defaults": ST.DEFAULT,
    }


def libs_of(ids):
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
    a = analyse(item(req.get("id")).run, req.get("state") or {}, "de")
    return SR.query(a.run, a.steps, (a.st.get("residue") or {}).get("end"))


# ----------------------------------------------------------------------------- Ableiten (Leerkurve, Mittel)
def derive(req) -> list[dict]:
    op = req.get("op")
    ids = req.get("ids") or []
    pipes = req.get("pipelines") or {}
    if op not in ("blank", "avg") or len(ids) < 2:
        raise PR.OpError("Bitte mindestens zwei Läufe wählen.")
    runs = [processed(i, pipes.get(i) or []) for i in ids]
    base = runs[0]
    axis = req.get("axis", "T")
    if op == "blank":
        blank = runs[1]
        if base.unit != blank.unit:
            raise PR.OpError("Probe und Leerkurve müssen dieselbe Masseneinheit haben (beide mg oder beide %).")
        bx = blank.T if axis == "T" else blank.time()
        x = base.T if axis == "T" else base.time()
        if axis == "T":
            keep = bx >= np.maximum.accumulate(bx) - 1e-9
            bx, by = bx[keep], blank.m[keep]
            bx, k = np.unique(bx, return_index=True)
            by = by[k]
        else:
            by = blank.m
        corr = np.interp(x, bx, by - by[0])
        m = base.m - corr
        name = f"{base.name} − Leerkurve"
        meta = dict(base.meta, origin=f"{base.name} minus Leerkurve {blank.name} (über {'Temperatur' if axis == 'T' else 'Zeit'})")
        r = base.copy(m=m, meta=meta, name=name)
    else:
        x = base.T
        ms = []
        for r_ in runs:
            T = r_.T
            keep = T >= np.maximum.accumulate(np.nan_to_num(T, nan=-1e9)) - 1e-9
            T, m = T[keep], r_.pct()[keep]
            T, k = np.unique(T, return_index=True)
            ms.append(np.interp(x, T, m[k], left=np.nan, right=np.nan))
        m = np.nanmean(np.array(ms), axis=0)
        ok = np.isfinite(m)
        name = "Mittel aus " + ", ".join(r_.name for r_ in runs)
        r = base.copy(T=base.T[ok], m=m[ok], t=base.time()[ok], unit="%", name=name[:120], extra={},
                      meta=dict(base.meta, origin=name))
    fname = re.sub(r"[^\w\-]+", "_", r.name)[:60].strip("_") + ".csv"
    raw = to_csv(r).encode("utf-8")
    return load_file(raw, fname)


def export(req) -> dict:
    import matplotlib.pyplot as plt

    from . import charts as C
    it = item(req.get("id"))
    a = analyse(it.run, req.get("state") or {}, "de")
    stem = re.sub(r"[^\w\-]+", "_", it.run.name).strip("_") or "TGA"
    folder = STATE.out_root / stem
    if folder.exists() and any(folder.iterdir()) and not req.get("overwrite"):
        return {"exists": True, "folder": str(folder)}
    folder.mkdir(parents=True, exist_ok=True)
    files = []
    f = C.fig_tg_dtg(a, "de")
    f.savefig(folder / "tg_dtg.png", dpi=200, bbox_inches="tight")
    plt.close(f)
    files.append("tg_dtg.png")
    (folder / "lauf.csv").write_text(to_csv(a.run), encoding="utf-8")
    files.append("lauf.csv")
    if a.steps:
        with (folder / "stufen.csv").open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(["Nr", "T_onset_C", "T_peak_C", "T_endset_C", "T_mid_C", "Verlust_%", "Verlust_mg"])
            for s in a.steps:
                w.writerow([s["no"]] + [("" if s.get(k) is None else f"{s[k]:.4g}".replace(".", ",")) for k in
                                        ("T_onset", "T_peak", "T_endset", "T_mid", "loss", "loss_mg")])
        files.append("stufen.csv")
    lines = [f"Lauf: {it.run.name} (Datei {it.fname}, {it.run.meta.get('format')})", "", "Bearbeitung:"]
    lines += [f"  {i}. {t}" for i, t in enumerate(a.proc.steps, 1)] or ["  (keine)"]
    lines += ["", "Arbeitsstand als JSON:", json.dumps(clean({k: v for k, v in (req.get("state") or {}).items()
                                                               if k not in ("search", "mixture")}), ensure_ascii=False)]
    (folder / "protokoll.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    files.append("protokoll.txt")
    return {"folder": str(folder), "files": files}


# ----------------------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "FolioTGA/1.0"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200):
        self._send(code, json.dumps(clean(obj), ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8"),
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
        if url.path in ("/labref.js", "/labenv.js", "/labindex.js", "/labui.js", "/labboard.js", "/laboverview.js", "/labimport.js", "/labunc.js"):   # gemeinsame Seitenskripte
            return self._send(200, labcite.web_asset(url.path[1:]), "text/javascript; charset=utf-8")
        if url.path == "/api/meta":
            return self._json(meta_payload())
        self._send(404, b"nicht gefunden", "text/plain")

    def do_POST(self):
        url = urlparse(self.path)
        origin = self.headers.get("Origin")
        if origin and not ORIGIN_OK.match(origin):
            n = int(self.headers.get("Content-Length") or 0)
            if 0 < n <= 1 << 20:
                self.rfile.read(n)                       # read the small body so the answer arrives cleanly
            return self._json({"error": "Fremde Herkunft abgelehnt"}, 403)
        try:
            return self._route(url)
        except (PR.OpError, ReadError, KI.KinError, EnvError, ValueError, np.linalg.LinAlgError) as e:
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
            name = unquote(qs.get("name", ["Lauf.csv"])[0])
            mapping = json.loads(unquote(qs.get("mapping", ["null"])[0]) or "null")
            return self._json({"runs": load_file(self._body(), name, mapping)})
        if p.startswith("/api/egs/"):
            sub = p[len("/api/egs/"):]
            if sub == "load":
                return self._json(egs_route("load", {}, self._body(), unquote(qs.get("name", ["serie.csv"])[0])))
            return self._json(egs_route(sub, self._req(), None, None))
        if p == "/api/remap":
            req = self._req()
            it = item(req.get("id"))
            r = load_bytes(it.raw, it.fname, req.get("mapping"))[0]
            it.run, it.mapping = r, req.get("mapping")
            STATE.envs.set_extra(str(req.get("id")), mapping=it.mapping)
            _drop_cache(req.get("id"))
            return self._json({"run": describe(req.get("id"))})
        if p == "/api/sample":
            out = []
            for data, name in SY.make(self._req().get("which") or "oxalat"):
                out += load_file(data, name)
            return self._json({"runs": out})
        if p == "/api/remove":
            iid = self._req().get("id")
            with STATE.lock:
                STATE.items.pop(iid, None)
            _drop_cache(iid)
            STATE.envs.forget(str(iid))
            return self._json({"ok": True})
        if p.startswith("/api/env/"):
            return self._json(STATE.envs.route(p.rsplit("/", 1)[1], self._req(), reload_env))
        if p.startswith("/api/index/"):                # A7: Projektindex
            import labindex
            return self._json(labindex.route(STATE.envs, "tga", __version__, p.rsplit("/", 1)[1], self._req()))
        if p.startswith("/api/prov/"):                 # A8: Herkunftskette, Abhängigkeiten
            import labprov
            return self._json(labprov.route(STATE.envs, p.rsplit("/", 1)[1], self._req()))
        if p.startswith("/api/unc/"):                  # Messunsicherheit: Messmittel, Vorschau, Verfahren (labunc)
            import labunc
            return self._json(labunc.route(STATE.envs, p.rsplit("/", 1)[1], self._req()))
        if p == "/api/uncert/replicates":              # Wiederholungen derselben Probe: Typ A (+ Typ B)
            return self._json(replicates_payload(self._req()))
        if p == "/api/share/steps":
            return self._json(share_steps(self._req()))
        if p == "/api/dataset":                        # DP-13: Lauf aus einem Datensatz der Datenaufbereitung
            return self._json(ds_list())
        if p == "/api/dataset/run":
            return self._json({"runs": ds_run(self._req())})
        if p == "/api/dataset/refresh":
            return self._json(ds_refresh(self._req()))
        if p == "/api/rename":
            req = self._req()
            it = item(req.get("id"))
            it.run.name = (req.get("name") or it.run.name).strip()[:120]
            STATE.envs.set_name(str(req.get("id")), it.run.name)
            _drop_cache(req.get("id"))
            return self._json({"ok": True, "name": it.run.name})
        if p == "/api/run":
            req = self._req()
            return self._json(run_payload(req.get("id"), req.get("state") or {}, req.get("lang") or "de"))
        if p == "/api/derive":
            return self._json({"runs": derive(self._req())})
        if p == "/api/search":
            req = self._req()
            Q = query_of(req)
            try:
                w_raw = req.get("w_curve")
                w = 0.6 if w_raw in (None, "") else float(w_raw)
            except (TypeError, ValueError):
                return self._json({"error": "Ungültige Gewichtung der DTG-Kurve (0 bis 1)."}, 400)
            if not (0.0 <= w <= 1.0):
                return self._json({"error": "Die Gewichtung der DTG-Kurve muss zwischen 0 und 1 liegen."}, 400)
            res = SR.search(Q, libs_of(req.get("libs")), req.get("mode") or "both", int(req.get("shift", 20)),
                            int(req.get("n") or 25), req.get("category") or None, bool(req.get("same_atm")), w_curve=w)
            return self._json(res)
        if p == "/api/mixture":
            req = self._req()
            Q = query_of(req)
            return self._json(SR.mixture(Q, libs_of(req.get("libs")), int(req.get("max") or 3), int(req.get("shift", 20))))
        if p == "/api/kinetics":
            req = self._req()
            runs = [processed(i, (req.get("pipelines") or {}).get(i) or []) for i in req.get("ids") or []]
            res = KI.run_all(runs, float(req.get("T_lo")), float(req.get("T_hi")), req.get("opts"))
            res["unc"] = UC.kinetics(res, {"unc_method": req.get("unc_method")}, req.get("lang") or "de")
            return self._json(res)
        if p == "/api/deconv_guess":
            req = self._req()
            a = analyse(item(req.get("id")).run, req.get("state") or {}, "de")
            d = a.st["dtg"]
            lo, hi = float(req.get("lo")), float(req.get("hi"))
            m = np.isfinite(d["dT"]) & (a.run.T >= lo) & (a.run.T <= hi)
            return self._json({"peaks": DC.guess(a.run.T[m], -d["dT"][m], req.get("n"))})
        if p == "/api/calib":
            req = self._req()
            return self._json(CO.two_point([(x[0], x[1]) for x in req.get("points") or []]))
        if p.startswith("/api/library/"):
            return self._library(p.rsplit("/", 1)[1], qs)
        if p.startswith("/api/equations/"):
            return self._equations(p.rsplit("/", 1)[1])
        if p == "/api/save":
            req = self._req()
            it = item(req.get("id"))
            r = processed(req.get("id"), req.get("pipeline"))
            stem = re.sub(r"[^\w\-]+", "_", it.run.name).strip("_") or "Lauf"
            return self._json({"text": to_csv(r), "filename": stem + ".csv", "mime": "text/csv"})
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
        req = self._req()
        if action == "create":
            lib = L.create(req.get("name", ""), req.get("description", ""), req.get("source"))
            return self._json({"lib": lib.info(), "libs": L.list()})
        if action == "delete":
            L.delete(req.get("lib"))
            return self._json({"libs": L.list()})
        if action == "add_run":
            # gemessener Lauf als Referenz; ohne Bibliothek -> „Eigene Referenzen“
            lib = L.get(req["lib"]) if req.get("lib") else L.own()
            r = processed(req.get("id"), req.get("pipeline"))
            meta = dict(req.get("meta") or {})
            meta.setdefault("name", r.name)
            meta.setdefault("atmosphere", r.meta.get("gas", ""))
            if r.meta.get("rate"):
                meta.setdefault("rate", r.meta["rate"])
            if r.m0:
                meta.setdefault("m0", r.m0)
            with L.lock:
                e = lib.add_curve(r.T, r.pct(), meta)
                lib.save()
            return self._json({"entry": e, "lib": lib.info(), "libs": L.list()})
        lib = L.get(req["lib"]) if req.get("lib") else L.own()
        if action == "entries":
            return self._json({"lib": lib.info(), "entries": [{k: v for k, v in e.items() if not k.startswith("_")} for e in lib.entries]})
        if action == "add_steps":
            with L.lock:
                e = lib.add_steps(req.get("meta") or {})
                lib.save()
            return self._json({"entry": e, "lib": lib.info(), "libs": L.list()})
        if action == "update":
            with L.lock:
                e = lib.update(req.get("eid"), req.get("meta") or {})
                lib.save()
            return self._json({"entry": e})
        if action == "remove":
            with L.lock:
                lib.remove(req.get("eid"))
                lib.save()
            return self._json({"lib": lib.info()})
        if action == "curve":
            e = lib.entry(req.get("eid"))
            return self._json({"name": e["name"], "dtg": lib.dtg(e).astype(np.float32), "tg": lib.tg(e).astype(np.float32),
                               "ref": lib.ref_of(e), "entry": {k: v for k, v in e.items() if not k.startswith("_")}})
        if action == "export":
            stem = re.sub(r"[^\w\-]+", "_", lib.name).strip("_") or "Bibliothek"
            return self._json({"text": json.dumps(clean(lib.export()), ensure_ascii=False, indent=1), "filename": stem + ".json",
                               "mime": "application/json"})
        if action == "import":
            with L.lock:
                n = lib.import_(req.get("data") or {})
                lib.save()
            return self._json({"added": n, "lib": lib.info(), "libs": L.list()})
        return self._send(404, b"nicht gefunden", "text/plain")

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
                items.append((it.raw, it.fname, it.mapping, state))
                rx = {"name": it.fname, "mapping": it.mapping, "label": it.run.name, "state": state}
                if getattr(it, "idx", 0):
                    rx["idx"] = int(it.idx)
                src = (it.run.meta or {}).get("dataset") or {}
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
                items.append((data, x["name"], x.get("mapping"), x.get("state") or {}))
                req_items.append(x)
            old = src.get("request") or {}
            req = {**old, **{k: v for k, v in req.items() if k != "source"}}
        if not items:
            return self._json({"error": "Kein Lauf gewählt."}, 400)
        labelled = []
        for (raw, fname, mp, state), x in zip(items, req_items):
            st = dict(state)
            if x.get("label"):
                st["_label"] = x["label"]
            if x.get("idx"):
                st["_idx"] = int(x["idx"])
            labelled.append((raw, fname, mp, st))
        request = {"items": req_items, "lang": req.get("lang", "de"), "include": req.get("include") or {},
                   "title": req.get("title") or None, "slug": req.get("slug") or None, "kinetics": req.get("kinetics")}
        if req.get("unc_replicates"):                  # Läufe sind Wiederholungen derselben Probe (Typ A)
            request["unc_replicates"] = True
        if any(UC.active(st) for (_r, _f, _m, st) in items):
            own_instruments()
        # the hub's figure styles and the describe request for its editing window pass through (labbundle)
        for k in ("styles", "describe_figures", "preview"):
            if k in req:
                request[k] = req[k]
        return self._json(B.build(labelled, request, lang=request["lang"], include=request["include"], title=request["title"]))


def main(argv=None):
    global STATE
    ap = argparse.ArgumentParser(description="TGA, lokale Oberfläche")
    ap.add_argument("--port", type=int, default=8768)
    ap.add_argument("--out", default=str(ROOT / "Ausgaben"), help="Wurzelordner der Exporte und Bibliotheken")
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args(argv)
    STATE = State(Path(a.out).resolve())
    STATE.envs.env_bundle = env_bundle
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = f"http://127.0.0.1:{a.port}/"
    print(f"TGA läuft auf {url}  (Beenden mit Strg+C)")
    if not a.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
