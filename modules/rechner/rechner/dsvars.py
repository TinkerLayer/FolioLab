"""DP-11: Spalten eines Datensatzes (Freigabe `data.table`) als Listenvariablen der Rechenzeilen.

Die Seite merkt sich je Umgebung (Projekt-Umgebung, also für alle Blätter) Bindungen
``{"share": s-…, "title", "mode": "live"|"pin", "version": n, "keys": [Spaltenschlüssel, …]}``.
Bei jeder Rechnung löst der Server sie auf: live = neueste Version, pin = die gemerkte Version. Jede gewählte
Zahlenspalte wird eine Variable (Name = Spaltenschlüssel) mit den Werten in SI-Einheiten; die Einheit der Spalte
geht als Dimension mit (``mean(sigma)`` hat Pa, ``sigma/eps`` auch). Ausgeschlossene Zeilen und Zeilen mit einer
Lücke in einer der gewählten Spalten fallen in allen Spalten weg, damit die Listen paarweise zusammenpassen.
"""
from __future__ import annotations

import re
import threading

import numpy as np

from . import console as CON
from . import expr as E
from . import units as U

MAX_BINDINGS = 8
MAX_COLS = 20
_CACHE: dict = {}            # (Ordner, Freigabe, Version, Prüfsumme) -> Datensatz; Versionen ändern sich nie
_CACHE_MAX = 6
_LOCK = threading.Lock()


def _dataset(box, sid: str, env: dict):
    """Datensatz einer Version, zwischengespeichert (/api/workspace läuft bei jeder Eingabe)."""
    from labshare import dataset_of
    key = (str(box.base), sid, env.get("version"), env.get("hash"))
    with _LOCK:
        ds = _CACHE.pop(key, None)
    if ds is None:
        ds = dataset_of(env, box.base / sid)
    with _LOCK:
        _CACHE[key] = ds
        while len(_CACHE) > _CACHE_MAX:
            _CACHE.pop(next(iter(_CACHE)))
    return ds


def bindings_of(req: dict) -> list[dict]:
    """Gültige Bindungen aus der Anfrage (Reihenfolge bleibt; dient auch der Zuordnung von Info und Bindung)."""
    out = []
    for b in req.get("dsvars") or []:
        if isinstance(b, dict) and isinstance(b.get("share"), str) and b["share"]:
            out.append(b)
    return out[:MAX_BINDINGS]


def var_name(key: str, taken) -> str:
    """Spaltenschlüssel -> Variablenname; reservierte Namen (mean, e, pi, …) bekommen _ds angehängt."""
    try:
        n = E.norm_name(key)
    except E.CalcError:
        n = re.sub(r"\W+", "_", str(key)).strip("_") or "spalte"
        if not re.match(r"[^\W\d]", n):
            n = "c_" + n
    if n in CON.RESERVED or n in U.CONSTANTS:          # lambda -> lambda_ wie beim Tippen; M, n bleiben frei
        n = n + "_ds"
    base, i = n, 2
    while n in taken:
        n = f"{base}_{i}"
        i += 1
    return n


def _info(b: dict) -> dict:
    mode = "pin" if b.get("mode") == "pin" else "live"
    return {"share": b["share"], "mode": mode, "title": b.get("title") or "", "version": b.get("version"),
            "latest": None, "status": None, "rows": 0, "used": 0, "excluded": 0, "vars": []}


def resolve(bindings: list[dict], box) -> tuple[dict, list[dict]]:
    """Bindungen mit einer Sharebox auflösen -> (Variablen {name: {store, dims, …}}, Info je Bindung)."""
    from labproject import EnvError
    vals, infos = {}, []
    for b in bindings:
        rec = _info(b)
        infos.append(rec)
        try:
            res = box.resolve({"id": b["share"], "mode": rec["mode"], "version": b.get("version")}, "rechner")
            if res["status"] == "failed":
                raise EnvError(res.get("error") or "Datensatz nicht verfügbar")
            env = res["envelope"]
            ds = _dataset(box, b["share"], env)
        except EnvError as e:
            rec["error"] = str(e)
            continue
        p = env.get("producer") or {}
        rec.update(version=env["version"], latest=res["latest"], status=res["status"], title=env.get("title") or rec["title"],
                   rows=ds.rows, producer={k: p.get(k) for k in ("module", "env_name", "item_name")})
        cols, missing = [], []
        for k in [k for k in b.get("keys") or [] if isinstance(k, str)][:MAX_COLS]:
            try:
                c = ds.col(k)
            except ValueError:                        # Spalte fehlt in dieser Version
                missing.append(k)
                continue
            if c["dtype"] == "number":
                cols.append(c)
            else:
                missing.append(k)
        used = ds.used_mask()
        mask = used.copy()
        arrays = {}
        for c in cols:
            a = np.asarray(ds.si(c["key"]), dtype=float)
            mask &= np.isfinite(a)
            arrays[c["key"]] = a
        rec["excluded"] = int((~used).sum())
        rec["used"] = int(mask.sum()) if cols else 0
        if missing:
            rec["missing"] = missing
        for c in cols:
            name = var_name(c["key"], vals)
            _, d, _ = U.parse_unit(c["unit"])
            vals[name] = {"store": [float(x) for x in arrays[c["key"]][mask]], "dims": [float(x) for x in d],
                          "unit": c["unit"], "si": U.dims_text(d), "share": b["share"], "version": env["version"]}
            rec["vars"].append({"name": name, "key": c["key"], "label": c.get("name") or c["key"], "unit": c["unit"],
                                "si": U.dims_text(d), "kind": c.get("kind") or ""})
    return vals, infos


def attach(req: dict, envs) -> dict:
    """Anfrage um die aufgelösten Datensatz-Variablen ergänzen (``dsvals``, ``dsinfo``); ohne Bindung unverändert."""
    bindings = bindings_of(req)
    if not bindings:
        return req
    if envs is None:
        infos = [{**_info(b), "error": "Keine Projektumgebung – Datensätze sind hier nicht lesbar"} for b in bindings]
        return {**req, "dsvars": bindings, "dsvals": {}, "dsinfo": infos}
    from labshare import Sharebox
    envs.ensure()
    vals, infos = resolve(bindings, Sharebox(envs.suite, envs.project))
    return {**req, "dsvars": bindings, "dsvals": vals, "dsinfo": infos}
