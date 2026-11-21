"""Local page of the Datenaufbereitung module (DP-03).

Runs on 127.0.0.1 only and fetches nothing from the network. Loaded files are kept as raw files in the active
environment (labproject), so they come back after a restart; the sheets themselves stay in memory.

Start:  python -m daten.server  [--port 8774] [--out Ausgaben] [--no-browser]
"""
from __future__ import annotations

import argparse
import hashlib
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
from .readers import ACCEPT, ReadError, load_bytes  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
ROOT = Path(__file__).resolve().parents[1]
ORIGIN_OK = re.compile(r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$")
MAX_FILE = 200 * 1024 * 1024
MAX_WINDOW = (1000, 200)                 # rows × columns per /api/cells request
WEB = ("/labref.js", "/labenv.js", "/labindex.js", "/labui.js", "/labboard.js", "/laboverview.js", "/labunc.js")


class Item:
    def __init__(self, sheets, raw: bytes, fname: str, name: str, manual=None):
        self.sheets, self.raw, self.fname, self.name = sheets, raw, fname, name
        self.manual = manual                    # DP-M1: Manual workbook when the entry is typed in the page
        self.sha256 = hashlib.sha256(raw).hexdigest()
        self.lock = threading.Lock()


class State:
    def __init__(self, out_root: Path):
        self.items: dict[str, Item] = {}
        self.lock = threading.Lock()
        self.out_root = out_root
        self.envs = ModuleEnvs(out_root, "datenaufbereitung")


STATE: State | None = None


def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items() if not str(k).startswith("_")}
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


def item(iid) -> Item:
    it = STATE.items.get(iid)
    if it is None:
        raise LookupError("Datei nicht geladen")
    return it


def sheet_of(iid, k):
    it = item(iid)
    try:
        return it.sheets[int(k or 0)]
    except (IndexError, ValueError, TypeError):
        raise LookupError("Blatt nicht gefunden") from None


def describe(iid) -> dict:
    it = item(iid)
    return {"id": iid, "name": it.name, "file": it.fname, "bytes": len(it.raw), "sha256": it.sha256,
            "manual": it.manual is not None, **({"rev": it.manual.rev} if it.manual else {}),
            "dataset": ((STATE.envs.items.get(iid) or {}).get("extra") or {}).get("dataset"),
            "sheets": [s.describe() for s in it.sheets]}


def add_item(data: bytes, fname: str, name: str | None = None, iid: str | None = None) -> dict:
    from .manual import Manual, is_manual
    man = Manual.from_bytes(data) if is_manual(fname) else None
    sheets = man.sheets_view() if man else load_bytes(data, fname)
    keep = iid is None
    iid = iid or uuid.uuid4().hex[:10]
    stem = Path(fname).name[:-len(".messung.json")] if man else Path(fname).stem
    name = (name or stem or "Tabelle")[:120]
    with STATE.lock:
        STATE.items[iid] = Item(sheets, data, fname, name, man)
    if keep:
        STATE.envs.remember(iid, data, fname, 0, name)
    return describe(iid)


def reload_env() -> list[dict]:
    """Files of the active environment, read again after a restart or a switch."""
    with STATE.lock:
        STATE.items.clear()
    out = []
    for iid, raw, fname, _idx, name, _extra in STATE.envs.stored():
        try:
            out.append(add_item(raw, fname, name, iid))
        except (ReadError, ValueError):
            continue
    return out


def _persist_manual(iid: str, it: Item) -> None:
    """Store the edited manual workbook as the entry's new raw file (new SHA-256)."""
    it.raw = it.manual.to_bytes()
    it.sha256 = hashlib.sha256(it.raw).hexdigest()
    STATE.envs.replace_raw(iid, it.raw)


def manual_route(action: str, req: dict) -> dict:
    """DP-M1: create and edit manual sheets ("Einzelmessergebnisse")."""
    from .manual import SUFFIX, Manual, ManualError, clean_name
    if action == "new":
        name = clean_name(req.get("name"), "Einzelmessergebnisse")
        m = Manual([{"name": clean_name(req.get("sheet"), "Messung 1"), "cells": {}}])
        return {"files": [add_item(m.to_bytes(), name + SUFFIX, name)]}
    if action == "parse":                                # DP-M2: values of the sequential entry, unit kept per column
        from .manual import parse_entry
        texts = req.get("texts") or []
        if not isinstance(texts, list) or len(texts) > 20_000:
            raise ValueError("Werte ungültig")
        unit = str(req.get("unit") or "").strip()
        items = []
        for t in texts:
            x, u, cell = parse_entry(str(t)[:2000])
            rec = {"cell": cell, "value": x, "unit": u}
            if u and unit and u != unit:
                rec["error"] = (f"„{t}“: Einheit {u} passt nicht zur Spalte ({unit}) – den Wert ohne Einheit eingeben "
                                f"oder die Einheit der Spalte ändern")
                rec["mismatch"] = {"text": str(t)[:80], "unit": u, "col": unit}
                items.append(rec)
                break
            if u and not unit:
                unit = u
            items.append(rec)
        return {"items": items, "unit": unit}
    iid = str(req.get("id") or "")
    it = item(iid)
    if action == "probe" and it.manual is not None:    # DP-M2: where the sequential entry continues
        k, idx = int(req.get("sheet") or 0), int(req.get("idx") or 0)
        cells = it.manual._sheet(k)["cells"]
        down = req.get("dir") != "right"
        line = [(r if down else c) for (r, c) in cells if (c if down else r) == idx]
        hdr = cells.get((0, idx) if down else (idx, 0), "")
        import labtable as LT
        hnum = bool(hdr) and LT.number(hdr) is not None
        return {"next": max(line, default=0) + 1, "header": "" if hnum else hdr,
                "header_num": hnum}
    if it.manual is None:
        raise ValueError("Diese Tabelle ist eine Datei und lässt sich nicht bearbeiten – „Neue Messtabelle“ anlegen")
    try:
        with it.lock:
            if action == "write":
                k = int(req.get("sheet") or 0)
                before = it.manual.write(k, req.get("writes"))
                it.sheets[k] = it.manual.sheet(k)
                _persist_manual(iid, it)
                sh = it.sheets[k]
                cells = []
                for w in before:
                    r, c = w["r"], w["c"]
                    t = int(sh.typ[r, c]) if r < sh.rows and c < sh.cols else 0
                    cells.append({"r": r, "c": c, "t": t, "v": sh.display(r, c) if t else None})
                return {"rev": it.manual.rev, "sha256": it.sha256, "before": before, "cells": cells,
                        "sheet": sh.describe()}
            if action == "sheet":
                op = req.get("op")
                if op == "add":
                    k = it.manual.add_sheet(req.get("name"))
                elif op == "rename":
                    it.manual.rename_sheet(req.get("sheet"), str(req.get("name") or ""))
                    k = int(req.get("sheet") or 0)
                elif op == "remove":
                    it.manual.remove_sheet(req.get("sheet"))
                    k = 0
                else:
                    raise ValueError("unbekannte Blattaktion")
                it.sheets = it.manual.sheets_view()
                _persist_manual(iid, it)
                return {**describe(iid), "sheet": k}
    except ManualError as e:
        raise ValueError(str(e)) from None
    raise LookupError("unbekannte Aktion")


def unit_info(unit: str) -> dict:
    """DP-M3: is a unit readable, and which quantity kinds fit it (for the unit dialog)."""
    from labcalc import units as U
    from .recipe import _clean_unit, unit_problem
    u = _clean_unit(unit)[:30]
    msg = unit_problem(u) if u else None
    if msg:
        return {"unit": u, "ok": False, "msg": msg}
    _, dims, _ = U.parse_unit(u)
    ks = U.kinds_for_unit(u)                                              # U-01: most likely kind first (pH → pH-Wert)
    kinds = [{"key": k.key, "de": k.de, "en": k.en} for k in ks][:8]
    # same dimension and scale: the units to convert into (pH, dB, NTU … only into themselves)
    units = list(dict.fromkeys(x for k in ks for x in k.units if U.compatible(u, x)))[:40]
    return {"unit": u, "ok": True, "dims": U.dims_text(dims) or "1", "kinds": kinds, "units": units}


def ds_thumb(ds, n: int = 150) -> dict | None:
    """UI-18: small picture of a dataset for the box on the overview (shared with the import window, I-02)."""
    import labdataset
    return labdataset.thumb(ds, n)


def ds_route(action: str, req: dict) -> dict:
    """DP-M4/M5: save a prepared table as dataset (new version only on change), list, open, derive."""
    from . import datasets as D
    from . import recipe as RC
    import labdataset as DS
    envs = STATE.envs
    try:
        if action == "publish":
            iid, k = str(req.get("id") or ""), int(req.get("sheet") or 0)
            it, sh = item(iid), sheet_of(iid, k)
            steps = req.get("steps") or []
            if not isinstance(steps, list) or len(steps) > 500:
                raise ValueError("Rezept ungültig")
            tbl = RC.extract(sh, steps)
            rid = (envs.items.get(iid) or {}).get("raw")
            files = [{"name": it.fname, "sha256": it.sha256, "sheet": sh.name, "raw": rid,
                      "ranges": sorted({m["range"] for m in tbl["marks"] if m["kind"] == "data"})[:50]}]
            title = str(req.get("title") or it.name).strip()[:160] or it.name
            ds = RC.to_dataset(tbl, title, files, steps, __version__)
            res = D.publish(envs, D.producer(envs, __version__, iid, it.name, rid), ds, req.get("share") or None,
                            origin={"env": envs.eid, "item": iid, "sheet": k, "sheet_name": sh.name})
            try:
                th = ds_thumb(ds)
            except Exception:                                     # the picture is optional, the dataset is not
                th = None
            return {**res, "thumb": th} if isinstance(res, dict) and th else res
        if action == "list":
            return {"datasets": D.listing(envs), "env": envs.eid}
        sid = str(req.get("share") or "")
        if action == "open":
            ds, env = D.load(envs, sid, req.get("version"))
            name = f"{ds.header['title']} (v{env['version']})"[:120]
            data, fname = D.table_text(ds).encode("utf-8"), re.sub(r"[\\/:*?\"<>|]+", "_", name) + ".tsv"
            ref = {"share": sid, "version": env["version"]}
            if req.get("link"):                                   # opened through a connection from another environment
                ref["link"] = str(req["link"])[:80]
            old = str(req.get("item") or "")
            prev = ((envs.items.get(old) or {}).get("extra") or {}).get("dataset") or {} if old else {}
            if old and old in STATE.items and prev.get("share") == sid:     # the same table follows the new version
                with STATE.lock:
                    STATE.items[old] = Item(load_bytes(data, fname), data, fname, name, None)
                envs.replace_raw(old, data, fname, name)
                envs.set_extra(old, dataset=ref)
                return {"files": [describe(old)], "replaced": old}
            d = add_item(data, fname, name)
            envs.set_extra(d["id"], dataset=ref)
            return {"files": [describe(d["id"])]}
        if action == "preview":
            pds, penv = D.load(envs, sid, req.get("version"))
            ds = D.derive(pds, req.get("ops"), str(req.get("title") or penv.get("title") or ""),
                          {"share": sid, "version": penv["version"]}, loader=lambda s2, v=None: D.load(envs, s2, v))
            from . import clean as C
            return {"header": ds.header, "page": ds.page(0, 12), "steps": ds.header["provenance"].get("steps") or [],
                    "checks": C.checks(ds)}
        if action == "derive":
            return D.make_derived(envs, __version__, sid, req.get("ops"), str(req.get("title") or "").strip()[:160],
                                  str(req.get("mode") or "live"), req.get("target") or None, req.get("version"))
        if action == "refresh":                                   # pinned derived dataset → latest parent
            h = D.head(D.box(envs), sid) or {}
            d = h.get("derive")
            if not d:
                raise ValueError("Kein abgeleiteter Datensatz")
            return D.make_derived(envs, __version__, d["parent"], d.get("ops") or [], h.get("title") or "",
                                  str(req.get("mode") or d.get("mode") or "pin"), sid)
        if action == "delete":
            b = D.box(envs)
            h = D.head(b, sid)
            if not h or (h.get("producer") or {}).get("module") != D.MODULE:
                raise ValueError("Nur eigene Datensätze lassen sich löschen")
            b.delete(sid)
            return {"ok": True}
        if action == "checks":                                    # DP-08: check chips of a dataset
            from . import clean as C
            ds, env = D.load(envs, sid, req.get("version"))
            steps = [s for p in _prov_chain(ds.header.get("provenance") or {}) for s in (p.get("steps") or [])]
            return {"checks": C.checks(ds), "version": env["version"], "steps": steps,
                    "flags": len(ds.header.get("flags") or [])}
        if action == "export":                                    # DP-10: CSV, XLSX (+ Protokoll), JSON, Parquet
            import base64
            from . import export as X
            ds, env = D.load(envs, sid, req.get("version"))
            fmt = str(req.get("format") or "csv")
            if fmt not in X.FORMATS:
                raise ValueError(f"Format „{fmt}“ unbekannt (csv, xlsx, json, parquet)")
            data, mime = X.export(ds, fmt, describe_step, flags=req.get("flags", True) is not False)
            stem = re.sub(r"[\\/:*?\"<>|]+", "_", f"{ds.header['title']}_v{env['version']}")[:100]
            return {"data": base64.b64encode(data).decode("ascii"), "mime": mime, "filename": stem + X.FORMATS[fmt][1],
                    "bytes": len(data)}
    except (D.DeriveError, DS.DatasetError, RC.RecipeError) as e:
        raise ValueError(str(e)) from None
    raise LookupError("unbekannte Aktion")


def _prov_chain(prov: dict) -> list[dict]:
    out, p = [], prov
    while isinstance(p, dict) and p:
        out.append(p)
        p = p.get("parent_provenance")
    return list(reversed(out))


def tpl_route(action: str, req: dict) -> dict:
    """DP-09: reading templates (recipe + anchors) and batches over several loaded files."""
    from . import datasets as D
    from . import recipe as RC
    from . import templates as T
    import labdataset as DS
    store = T.Store(STATE.out_root)
    try:
        if action == "list":
            return {"templates": [{k: t.get(k) for k in ("id", "name", "source", "saved", "anchors")} | {"steps": len(t["steps"])}
                                  for t in store.list()]}
        if action == "delete":
            store.delete(str(req.get("template") or ""))
            return {"ok": True}
        if action == "save":
            iid, k = str(req.get("id") or ""), int(req.get("sheet") or 0)
            it, sh = item(iid), sheet_of(iid, k)
            rec = store.save(sh, req.get("steps") or [], req.get("name"), {"file": it.name, "sheet": sh.name},
                             req.get("template") or None)
            return {"template": rec}
        tpl = store.get(str(req.get("template") or ""))
        if action in ("check", "apply"):
            iid, k = str(req.get("id") or ""), int(req.get("sheet") or 0)
            sh = sheet_of(iid, k)
            if action == "check":
                return {"problems": T.check(sh, tpl)}
            try:
                steps = T.apply(sh, tpl)
                RC.extract(sh, steps)
            except T.TemplateError as e:
                return {"error": str(e), "problems": e.problems}
            return {"steps": steps}
        if action == "batch":
            mode = "combined" if req.get("mode") == "combined" else "each"
            items = req.get("items") or []
            if not isinstance(items, list) or not items or len(items) > 200:
                raise ValueError("Dateien wählen (höchstens 200)")
            results, parts, files = [], [], []
            for x in items:
                iid, k = str((x or {}).get("id") or ""), int((x or {}).get("sheet") or 0)
                it, sh = item(iid), sheet_of(iid, k)
                rec = {"id": iid, "name": it.name, "sheet": k}
                try:
                    steps = T.apply(sh, tpl)
                    tbl = RC.extract(sh, steps)
                except (T.TemplateError, RC.RecipeError) as e:
                    results.append({**rec, "ok": False, "error": str(e), "problems": getattr(e, "problems", [])})
                    continue
                rid = (STATE.envs.items.get(iid) or {}).get("raw")
                fi = {"name": it.fname, "sha256": it.sha256, "sheet": sh.name, "raw": rid,
                      "ranges": sorted({m["range"] for m in tbl["marks"] if m["kind"] == "data"})[:50]}
                rec.update(ok=True, steps=steps, rows=tbl["rows"])
                if mode == "each":
                    title = f"{tpl['name']} – {it.name}"[:160]
                    prev = (((STATE.envs.items.get(iid) or {}).get("extra") or {}).get("batch") or {}).get(tpl["id"])
                    try:
                        ds = RC.to_dataset(tbl, title, [fi], steps, __version__)
                        p = D.publish(STATE.envs, D.producer(STATE.envs, __version__, iid, it.name, rid), ds, prev,
                                      origin={"env": STATE.envs.eid, "item": iid, "sheet": k, "sheet_name": sh.name,
                                              "template": tpl["id"]})
                    except DS.DatasetError as e:
                        rec.update(ok=False, error=str(e))
                    else:
                        STATE.envs.set_extra(iid, batch={**((((STATE.envs.items.get(iid) or {}).get("extra") or {})
                                                              .get("batch")) or {}), tpl["id"]: p["share"]})
                        rec.update(share=p["share"], version=p["version"], unchanged=p["unchanged"], title=title)
                else:
                    parts.append((it.name, tbl))
                    files.append(fi)
                results.append(rec)
            out = {"results": results, "mode": mode}
            if mode == "combined" and parts:
                tbl = T.combine(parts, str(req.get("title") or tpl["name"]))
                title = str(req.get("title") or f"{tpl['name']} ({len(parts)} Dateien)").strip()[:160]
                ds = RC.to_dataset(tbl, title, files, tpl["steps"], __version__)
                p = D.publish(STATE.envs, D.producer(STATE.envs, __version__, None, title), ds, req.get("share") or None,
                              origin={"env": STATE.envs.eid, "template": tpl["id"], "combined": True})
                out["combined"] = {"share": p["share"], "version": p["version"], "unchanged": p["unchanged"],
                                   "rows": ds.rows, "title": title, "notes": tbl["notes"][:10]}
            return out
    except T.TemplateError as e:
        raise ValueError(str(e)) from None
    except (DS.DatasetError, RC.RecipeError) as e:
        raise ValueError(str(e)) from None
    raise LookupError("unbekannte Aktion")


def env_default_report(_stored, _client, eid: str) -> dict | None:
    """Bericht einer Umgebung = ihr neuester veröffentlichter Datensatz (neueste Version, folgt der Quelle)."""
    mine = [d for d in STATE.envs.datasets()["datasets"]
            if (d.get("producer") or {}).get("module") == "datenaufbereitung" and (d.get("producer") or {}).get("env") == eid]
    if not mine:
        return None
    d = max(mine, key=lambda x: str(x.get("modified") or ""))
    return {"share": d["id"], "version": d.get("latest"), "mode": "live", "include": {}, "title": d.get("title")}


def bundle_route(action: str, req: dict) -> dict:
    """DP-10: report bundle of a dataset (share + version).

    Refresh (rebuild) follows the mode stored in the request: "pin" (default, also for bundles made before the mode
    existed) rebuilds the same version – the dataset kept in the bundle, else that version from the active project;
    "live" loads the newest version of the share from the active project and says in the summary and the methods
    text when it moved (if the share cannot be read there, the kept version is used and that is said instead)."""
    from . import bundle as B
    from . import datasets as D
    import labdataset as DS
    if action == "rebuild":
        src = req.get("source") or {}
        old = src.get("request") or {}
        request = {**old, **{k: v for k, v in req.items() if k != "source"}}
        mode = "live" if old.get("mode") == "live" else "pin"
        sid = str(old.get("share") or "")
        ds, meta, note = None, None, ""
        if mode == "live" and sid:
            try:
                ds, env = D.load(STATE.envs, sid, None)
                meta = {"share": sid, "version": env["version"]}
                if old.get("version") is not None and env["version"] != old.get("version"):
                    note = (f"Aktualisiert: Datensatz {sid} von Version {old.get('version')} auf die neueste Version "
                            f"{env['version']} (Bericht folgt der neuesten Version)")
            except (EnvError, DS.DatasetError, ValueError, KeyError, OSError) as e:
                ds, note = None, (f"Neueste Version von {sid} nicht lesbar ({e}); Version {old.get('version')} "
                                  f"beibehalten")
        if ds is None:
            ds = B.rebuild_dataset(src)
            if ds is None:
                ds, env = D.load(STATE.envs, sid, old.get("version"))
                meta = {"share": old.get("share"), "version": env["version"]}
            else:
                meta = {"share": old.get("share"), "version": old.get("version")}
        request["mode"] = mode
        return B.build(ds, meta, request, describe_step, note=note)
    sid = str(req.get("share") or "")
    if not sid:
        raise ValueError("Kein Datensatz gewählt")
    ds, env = D.load(STATE.envs, sid, req.get("version"))
    request = {k: req.get(k) for k in ("lang", "include", "title", "slug") if req.get(k) is not None}
    request["mode"] = "live" if req.get("mode") == "live" else "pin"
    return B.build(ds, {"share": sid, "version": env["version"]}, request, describe_step)


def stats(sh, ranges) -> dict:
    """Counts and sums of a selection (status bar): cells, numbers, texts that read as numbers, empty, errors."""
    from .sheet import EMPTY, ERROR, FORMULA, NUM, TEXT
    mask = np.zeros(sh.typ.shape, bool)
    for g in list(ranges)[:50]:
        try:
            r0, c0, r1, c1 = (int(g[k]) for k in ("r0", "c0", "r1", "c1"))
        except (KeyError, TypeError, ValueError):
            raise ValueError("Bereich ungültig") from None
        r0, r1 = sorted((r0, r1))
        c0, c1 = sorted((c0, c1))
        mask[max(r0, 0):r1 + 1, max(c0, 0):c1 + 1] = True
    t = sh.typ[mask]
    x = sh.num[mask][t == NUM]
    return {"cells": int(mask.sum()), "numbers": int(x.size), "empty": int((t == EMPTY).sum()),
            "text": int((t == TEXT).sum()), "text_numbers": int(((t == TEXT) & np.isfinite(sh.num[mask])).sum()),
            "errors": int((t == ERROR).sum()), "formulas": int((t == FORMULA).sum()),
            **({"sum": float(x.sum()), "mean": float(x.mean()), "min": float(x.min()), "max": float(x.max())} if x.size else {})}


def repeat_values(sh, ranges) -> list[float]:
    """Numbers of a selection, row by row (a column or a range of repeated readings)."""
    from .sheet import NUM
    out = []
    for g in list(ranges)[:50]:
        try:
            r0, c0, r1, c1 = (int(g[k]) for k in ("r0", "c0", "r1", "c1"))
        except (KeyError, TypeError, ValueError):
            raise ValueError("Bereich ungültig") from None
        r0, r1 = sorted((max(r0, 0), max(r1, 0)))
        c0, c1 = sorted((max(c0, 0), max(c1, 0)))
        typ, num = sh.typ[r0:r1 + 1, c0:c1 + 1], sh.num[r0:r1 + 1, c0:c1 + 1]
        out += [float(x) for x in num[(typ == NUM) & np.isfinite(num)].ravel().tolist()]
        if len(out) > 10000:
            raise ValueError("Wiederholmessung: höchstens 10 000 Werte")
    return out


def repeat_route(req: dict) -> dict:
    """Wiederholmessung: mean, s, u = s/√n, ν = n − 1 of the numbers in a selection (type A)."""
    from . import uncert as UC
    sh = sheet_of(req.get("id"), req.get("sheet"))
    try:
        r = UC.repeats(repeat_values(sh, req.get("ranges") or []))
    except UC.UncColError as e:
        raise ValueError(str(e)) from None
    r.pop("values")
    return r


def recipe_route(action: str, req: dict) -> dict:
    """DP-05: first guess, preview of the extracted long table, check as a dataset."""
    from . import recipe as RC
    iid, k = req.get("id"), int(req.get("sheet") or 0)
    sh = sheet_of(iid, k)
    if action == "guess":
        steps = RC.guess(sh, loose=bool(sh.meta.get("manual")))
        return {"steps": steps, "describe": [describe_step(s) for s in steps]}
    steps = req.get("steps") or []
    if not isinstance(steps, list) or len(steps) > 500:
        raise ValueError("Rezept ungültig")
    try:
        tbl = RC.extract(sh, steps)
    except RC.RecipeError as e:
        return {"error": str(e), "describe": [describe_step(s) for s in steps]}
    if action == "extract":
        out = RC.preview(tbl, int(req.get("n") or 50))
        out["describe"] = [describe_step(s) for s in steps]
        return out
    if action == "dataset":
        import labdataset as DS
        it = item(iid)
        files = [{"name": it.fname, "sha256": it.sha256, "sheet": sh.name,
                  "ranges": sorted({m["range"] for m in tbl["marks"] if m["kind"] == "data"})[:50],
                  "raw": (STATE.envs.items.get(iid) or {}).get("raw")}]
        try:
            ds = RC.to_dataset(tbl, str(req.get("title") or it.name), files, steps, __version__)
        except DS.DatasetError as e:
            return {"error": str(e)}
        return {"header": ds.header, "page": ds.page(0, 20)}
    raise LookupError("unbekannte Aktion")


def describe_step(s: dict) -> str:
    """One line per recipe step for the page and the methods text."""
    op = (s or {}).get("op")
    lines = lambda xs: ", ".join(str(int(x) + 1) for x in xs)  # noqa: E731
    if op == "block":
        return f"Datenblock {s.get('range')}"
    if op == "header":
        return f"Kopfzeile(n) {lines(s.get('lines') or [])}" if s.get("lines") else "Keine Kopfzeile"
    if op == "units":
        return f"Einheitenzeile {int(s['line']) + 1}" if s.get("line") is not None else "Keine Einheitenzeile"
    if op == "skip":
        return f"Zeile(n) {lines(s.get('lines') or [])} überspringen (umschalten)"
    if op == "role":
        names = {"x": "x", "y": "y", "uncertainty": "Unsicherheit", "group": "Gruppe", "label": "Beschriftung",
                 "condition": "Bedingung", "ignore": "ignorieren", "": "ohne Rolle"}
        of = f" von Spalte {int(s['of']) + 1}" if s.get("of") is not None else ""
        return f"Spalte {int(s.get('series', 0)) + 1} im Block: {names.get(s.get('role'), s.get('role'))}{of}"
    if op == "meta":
        return (f"Metadatenzelle {s.get('cell')}" + (f" als „{s['name']}“" if s.get("name") else "")
                + (f" [{s['unit']}]" if s.get("unit") else "") + (" (Spalte)" if s.get("as") == "column" else " (Bedingung)"))
    if op == "meta_remove":
        return f"Metadatenzelle {s.get('cell')} entfernt"
    if op == "repeat":
        d = "nach rechts" if s.get("dir") != "down" else "nach unten"
        n = f"{s['count']}×" if s.get("count") else "bis leer"
        return f"Block wiederholt sich {d} alle {s.get('step')} ({n})" + (f", Beschriftung {s['label']}" if s.get("label") else "")
    if op == "repeat_off":
        return "Keine Wiederholung"
    if op == "wide":
        return f"Breit → lang: Spalten {lines(s.get('series') or [])} → „{s.get('name')}“ mit „{s.get('cond')}“"
    if op == "wide_off":
        return "Breit → lang aus"
    if op == "transpose":
        return "Zeilen und Spalten getauscht" if s.get("on", True) else "Nicht getauscht"
    if op == "unit":
        return f"Einheit {s.get('unit')} für {s.get('range')}" if s.get("unit") else f"Einheit für {s.get('range')} entfernt"
    if op == "name":
        return f"Name „{s.get('name')}“ für {s.get('range')}"
    if op == "colprop":
        parts = []
        if s.get("symbol") is not None:
            parts.append(f"Symbol {s['symbol']}" if s.get("symbol") else "ohne Symbol")
        if s.get("kind") is not None:
            parts.append(f"Grösse {s['kind']}" if s.get("kind") else "Grösse automatisch")
        if s.get("time"):
            parts.append("Datum/Zeit als Zeitspanne" + (f" in {s['time_unit']}" if s.get("time_unit") else "")
                         if s["time"] == "elapsed" else "Datum/Zeit als Rohwert")
        return f"Spalte {int(s.get('series', 0)) + 1} im Block: " + ", ".join(parts or ["Eigenschaften"])
    return str(op)


def unit_kinds() -> list[dict]:
    """Quantity kinds with their units (labcalc, as in the Rechner) – suggestions for every unit field."""
    from labcalc import units as U
    return [{"key": k.key, "de": k.de, "en": k.en, "si": k.si, "dims": U.dims_text(k.dims) or "1", "units": list(k.units)}
            for k in U.KINDS.values() if not k.key.startswith("dim:") and k.units]


def meta_payload() -> dict:
    return {"version": __version__, "accept": ACCEPT, "out_root": str(STATE.out_root),
            "window": {"rows": MAX_WINDOW[0], "cols": MAX_WINDOW[1]}, "kinds": unit_kinds()}


class Handler(BaseHTTPRequestHandler):
    server_version = "FolioDaten/0.1"

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
            raise ValueError(f"Datei zu gross (höchstens {MAX_FILE // 1048576} MB)")
        return self.rfile.read(n) if n else b""

    def _req(self) -> dict:
        return json.loads(self._body() or b"{}")

    def do_GET(self):
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        if url.path in WEB:
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
        except (ReadError, EnvError, ValueError) as e:
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
            name = unquote(qs.get("name", ["Tabelle.csv"])[0])[:200]
            return self._json({"files": [add_item(self._body(), name)]})
        if p == "/api/paste":
            req = self._req()
            text = str(req.get("text") or "")
            if not text.strip():
                raise ValueError("Nichts eingefügt")
            name = re.sub(r"[\\/:*?\"<>|]+", "_", str(req.get("name") or "Eingefügt").strip())[:80] or "Eingefügt"
            return self._json({"files": [add_item(text.encode("utf-8"), name + ".tsv", name)]})
        if p == "/api/remove":
            iid = str(self._req().get("id"))
            with STATE.lock:
                STATE.items.pop(iid, None)
            STATE.envs.forget(iid)
            return self._json({"ok": True})
        if p == "/api/rename":
            req = self._req()
            it = item(req.get("id"))
            it.name = (str(req.get("name") or "") or it.name).strip()[:120]
            STATE.envs.set_name(str(req.get("id")), it.name)
            return self._json({"ok": True, "name": it.name})
        if p == "/api/file":
            return self._json(describe(self._req().get("id")))
        if p == "/api/cells":
            req = self._req()
            sh = sheet_of(req.get("id"), req.get("sheet"))
            r0, c0 = int(req.get("r0") or 0), int(req.get("c0") or 0)
            r1 = min(int(req.get("r1") if req.get("r1") is not None else r0 + 100), r0 + MAX_WINDOW[0])
            c1 = min(int(req.get("c1") if req.get("c1") is not None else c0 + 30), c0 + MAX_WINDOW[1])
            return self._json(sh.window(r0, r1, c0, c1))
        if p == "/api/unit":
            return self._json(unit_info(str(self._req().get("unit") or "")))
        if p.startswith("/api/manual/"):
            return self._json(manual_route(p.rsplit("/", 1)[1], self._req()))
        if p.startswith("/api/ds/"):
            action = p.rsplit("/", 1)[1]
            if action in ("preview", "derive", "refresh", "publish"):    # own instruments of the suite for "unc" steps
                import labunc
                labunc.load_own(STATE.envs)
            return self._json(ds_route(action, self._req()))
        if p == "/api/repeat":
            return self._json(repeat_route(self._req()))
        if p.startswith("/api/unc/"):                       # measurement uncertainty: instruments, preview, methods
            import labunc
            return self._json(labunc.route(STATE.envs, p.rsplit("/", 1)[1], self._req()))
        if p.startswith("/api/recipe/"):
            return self._json(recipe_route(p.rsplit("/", 1)[1], self._req()))
        if p.startswith("/api/tpl/"):
            return self._json(tpl_route(p.rsplit("/", 1)[1], self._req()))
        if p in ("/api/bundle", "/api/bundle/rebuild"):
            import labunc
            labunc.load_own(STATE.envs)
            return self._json(bundle_route("rebuild" if p.endswith("rebuild") else "build", self._req()))
        if p == "/api/stats":
            req = self._req()
            return self._json(stats(sheet_of(req.get("id"), req.get("sheet")), req.get("ranges") or []))
        if p.startswith("/api/env/"):
            return self._json(STATE.envs.route(p.rsplit("/", 1)[1], self._req(), reload_env))
        if p.startswith("/api/index/"):
            import labindex
            return self._json(labindex.route(STATE.envs, "datenaufbereitung", __version__, p.rsplit("/", 1)[1], self._req()))
        if p.startswith("/api/prov/"):
            import labprov
            return self._json(labprov.route(STATE.envs, p.rsplit("/", 1)[1], self._req()))
        return self._send(404, b"nicht gefunden", "text/plain")


def main(argv=None):
    global STATE
    ap = argparse.ArgumentParser(description="Datenaufbereitung, lokale Oberfläche")
    ap.add_argument("--port", type=int, default=8774)
    ap.add_argument("--out", default=str(ROOT / "Ausgaben"), help="Wurzelordner der Ausgaben")
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args(argv)
    STATE = State(Path(a.out).resolve())
    # Der Bericht eines Datensatzes hängt nur an Freigabe und Version (projektweit), nicht an Dateien der Umgebung
    STATE.envs.env_bundle = lambda _stored, report, lang: bundle_route("bundle", {**report, "lang": lang})
    STATE.envs.env_default_report = env_default_report
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = f"http://127.0.0.1:{a.port}/"
    print(f"Datenaufbereitung läuft auf {url}  (Beenden mit Strg+C)")
    if not a.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
