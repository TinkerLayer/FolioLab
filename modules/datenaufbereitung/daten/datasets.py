"""Datasets made in this module (DP-M4, DP-M5).

DP-M4  A prepared table is shared as `data.table` (labshare) for the Rechner, Elementrechner, TGA, FTIR and this
       module. Saving again gives a new version only when the table changed (values, names, units, roles or title).
       The share remembers where it came from (`origin` = entry and sheet), so the page can keep it up to date.
DP-M5  A derived dataset is computed from another dataset: unit conversions of columns and formula columns
       (`σ = F / A0` with constants typed in). It is a dataset of its own with the recipe in `derive`
       ({parent, mode live|pin, version, ops}). Live children are computed again when the parent gets a new version.
       Formulas are evaluated in SI with `labcalc.expr`; the result unit must fit the dimension of the formula.
"""
from __future__ import annotations

import math

import numpy as np

import labdataset as DS
from labcalc import expr as E
from labcalc import units as U
from labproject import EnvError, _read, _write
from labshare import DATA_KIND, Sharebox

MODULE = "datenaufbereitung"
RECIPIENTS = ["rechner", "elementrechner", "tga", "ftir", MODULE]
MAX_OPS = 40
MAX_DEPTH = 6                       # derived from derived from … (live chain)


class DeriveError(ValueError):
    pass


def col_key(name: str, taken) -> str:
    """Column key (formula name) from a column name: σ → sigma, ΔL → dL (see labdataset.safe_key)."""
    return DS.safe_key(str(name or ""), taken)


# ----------------------------------------------------------------------------- shares
def box(envs) -> Sharebox:
    envs.ensure()
    return Sharebox(envs.suite, envs.project)


def env_name(envs) -> str:
    try:
        return envs.envs.manifest(envs.eid).get("name") or envs.eid
    except EnvError:
        return envs.eid


def producer(envs, version: str, item=None, item_name=None, raw=None) -> dict:
    return {"module": MODULE, "env": envs.eid, "env_name": env_name(envs), "item": item, "item_name": item_name,
            "module_version": version, "raw": raw}


def _sig(h: dict):
    return [h.get("data_hash"), h.get("title"),
            [(c.get("key"), c.get("name"), c.get("unit"), c.get("role"), c.get("kind")) for c in h.get("columns") or []]]


def head(b: Sharebox, sid: str) -> dict | None:
    try:
        return _read(b.base / sid / "share.json") or None
    except EnvError:
        return None


def set_meta(b: Sharebox, sid: str, **extra) -> None:
    p = b.base / sid / "share.json"
    m = _read(p) or {}
    m.update(extra)
    _write(p, m)


def publish(envs, prod: dict, ds: DS.Dataset, share_id: str | None = None, **meta) -> dict:
    """New version of `share_id` (or a new share) unless the latest version holds the same table."""
    b = box(envs)
    if share_id:
        h = head(b, share_id)
        if not h or (h.get("producer") or {}).get("module") != MODULE:
            share_id = None                                    # share was deleted → start a new one
        else:
            try:
                last = b.get(share_id)
            except EnvError:
                last = None
            same_meta = all(h.get(k) == v for k, v in meta.items())
            if last and isinstance(last.get("dataset"), dict) and _sig(last["dataset"]) == _sig(ds.header) and same_meta:
                return {"share": share_id, "version": last["version"], "unchanged": True, "children": []}
    env = b.publish_dataset(prod, ds.header["title"], ds, RECIPIENTS, share_id=share_id)
    if meta:
        set_meta(b, env["id"], **meta)
    children = refresh_children(envs, env["id"], prod.get("module_version") or "")
    return {"share": env["id"], "version": env["version"], "unchanged": False, "children": children}


def load(envs, sid: str, version=None) -> tuple[DS.Dataset, dict]:
    """Dataset of a share this module may read (own, or addressed to it)."""
    from labshare import dataset_of
    b = box(envs)
    h = head(b, sid)
    if not h or h.get("kind") != DATA_KIND:
        raise EnvError("Datensatz nicht gefunden")
    own = (h.get("producer") or {}).get("module") == MODULE
    env = b.get(sid, int(version) if version else None, None if own else MODULE)
    return dataset_of(env, b.base / sid), env


def listing(envs) -> list[dict]:
    """Datasets of the project this module can open: own ones (all environments) and those addressed to it."""
    b = box(envs)
    out = []
    for m in b.list(kind=DATA_KIND):
        own = (m.get("producer") or {}).get("module") == MODULE
        if not own and MODULE not in (m.get("recipients") or []):
            continue
        try:
            env = b.get(m["id"], None, None if own else MODULE)
        except EnvError:
            continue
        h = env.get("dataset") or {}
        p = m.get("producer") or {}
        d = m.get("derive")
        rec = {"id": m["id"], "title": m.get("title"), "latest": m.get("latest"), "modified": m.get("modified"),
               "own": own, "rows": h.get("rows"),
               "producer": {k: p.get(k) for k in ("module", "env", "env_name", "item", "item_name")},
               "columns": [{k: c.get(k) for k in ("key", "name", "unit", "kind", "dtype", "role")} for c in h.get("columns") or []],
               "origin": m.get("origin"), "derive": d, "error": m.get("error")}
        if d:
            ph = head(b, d.get("parent") or "")
            rec["parent_latest"] = (ph or {}).get("latest")
            rec["parent_title"] = (ph or {}).get("title")
        out.append(rec)
    return out


def table_text(ds: DS.Dataset) -> str:
    """Dataset as tab-separated text (names, units, values) – opened as a read-only table in the page."""
    clean = lambda s: str(s).replace("\t", " ").replace("\r", " ").replace("\n", " ")  # noqa: E731
    cols = ds.columns
    lines = ["\t".join(clean(c["name"]) for c in cols), "\t".join(clean(c.get("unit") or "") for c in cols)]
    arrs = [ds.data[c["key"]] for c in cols]
    for r in range(ds.rows):
        row = []
        for c, a in zip(cols, arrs):
            v = a[r]
            if c["dtype"] == "number":
                row.append("" if not math.isfinite(float(v)) else repr(float(v)))
            else:
                row.append(clean(v))
        lines.append("\t".join(row))
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------- derived datasets (DP-M5)
def _si(unit: str):
    try:
        return U.parse_unit(unit or "")
    except U.UnitError as e:
        raise DeriveError(str(e)) from None


def _is_diff(kind: str) -> bool:
    k = U.KINDS.get(kind or "")
    return bool(k and k.diff)


def _const(c: dict) -> tuple[str, float, tuple]:
    sym = str(c.get("sym") or "").strip()
    if not sym or not sym.isidentifier():
        raise DeriveError(f"Konstante „{sym}“: Name aus Buchstaben, Ziffern, _")
    try:
        v = float(str(c.get("value")).replace(",", ".").replace("−", "-"))
    except (TypeError, ValueError):
        raise DeriveError(f"Konstante {sym}: Zahl fehlt") from None
    if not math.isfinite(v):
        raise DeriveError(f"Konstante {sym}: Zahl ungültig")
    f, d, off = _si(str(c.get("unit") or ""))
    return sym, v * f + off, d


class _Ctx:
    """What a step may read besides its parent (DP-07 join: a second dataset of the project)."""

    def __init__(self, loader=None):
        self._loader = loader

    def load(self, sid, version=None):
        if self._loader is None:
            raise DeriveError("Zweiter Datensatz nicht erreichbar")
        return self._loader(sid, version)


def derive(parent: DS.Dataset, ops: list, title: str, origin: dict | None = None, loader=None) -> DS.Dataset:
    """Apply conversions, formula columns and cleaning steps (DP-07/08) to a copy of `parent`, in order.
    The provenance records each step with rows and flags before/after."""
    from . import clean as C
    if not isinstance(ops, list) or not ops:
        raise DeriveError("Keine Umrechnung gewählt")
    if len(ops) > MAX_OPS:
        raise DeriveError(f"Höchstens {MAX_OPS} Schritte")
    t = C.Table(parent)
    ctx = _Ctx(loader)
    log = []
    def n_ex():                                          # excluded rows (a row may carry several excluded flags)
        return len({f["row"] for f in t.flags if f.get("excluded")})
    for op in ops:
        kind = (op or {}).get("op")
        before = (t.n, len(t.flags), n_ex())
        try:
            if kind in ("convert", "formula"):
                text = _derive_col(t, op)
            elif kind in C.OPS:
                text = C.OPS[kind](t, op, ctx)
            else:
                raise DeriveError(f"Schritt „{kind}“ unbekannt")
        except C.CleanError as e:
            raise DeriveError(f"{C.describe(op)}: {e}") from None
        except EnvError as e:
            raise DeriveError(f"{C.describe(op)}: {e}") from None
        log.append({"op": kind, "text": text, "rows_before": before[0], "rows_after": t.n, "flags_before": before[1],
                    "flags_after": len(t.flags), "excluded_before": before[2],
                    "excluded_after": n_ex()})
    prov = {"derived_from": origin or {}, "ops": ops, "steps": log, "parent_provenance": parent.header.get("provenance") or {}}
    try:
        return t.dataset(title or parent.header["title"], prov)
    except C.CleanError as e:
        raise DeriveError(str(e)) from None


def _derive_col(t, op: dict) -> str:
    """DP-M5 column steps on the working table: unit conversion and formula column."""
    cols, data, n = t.cols, t.data, t.n

    def find(key):
        for i, c in enumerate(cols):
            if c["key"] == key:
                return i, c
        raise DeriveError(f"Spalte „{key}“ nicht im Datensatz")

    def numeric(c):
        if c["dtype"] != "number":
            raise DeriveError(f"Spalte „{c['name']}“ ist Text")

    for op in [op]:
        kind = (op or {}).get("op")
        if kind == "convert":
            i, c = find(str(op.get("col") or ""))
            numeric(c)
            unit = str(op.get("unit") or "").strip()
            f1, d1, o1 = _si(c.get("unit"))
            f2, d2, o2 = _si(unit)
            if not U.deq(d1, d2) or not U.compatible(c.get("unit") or "", unit):
                raise DeriveError(f"„{c['name']}“ ({c.get('unit') or '1'}) lässt sich nicht in {unit or '1'} umrechnen – "
                                  f"dafür eine Formel verwenden")
            diff = _is_diff(c.get("kind"))
            old = c.get("unit") or "1"
            vals = (data[c["key"]] * f1 + (0.0 if diff else o1) - (0.0 if diff else o2)) / f2
            if op.get("keep"):
                key = col_key(f"{c['key']}_{unit}", [x["key"] for x in cols])
                nc = {**c, "key": key, "name": str(op.get("name") or c["name"])[:120], "unit": unit, "role": "y"
                      if c.get("role") == "x" else c.get("role", "")}
                nc.pop("u", None)
                cols.insert(i + 1, nc)
                data[key] = vals
            else:
                c["unit"] = unit
                if op.get("name"):
                    c["name"] = str(op["name"])[:120]
                data[c["key"]] = vals
            return f"„{c['name']}“ von {old} in {unit or '1'} umgerechnet" + (" (neue Spalte)" if op.get("keep") else "")
        elif kind == "formula":
            src = str(op.get("expr") or "").strip()
            name = str(op.get("name") or "").strip()[:120]
            if not src or not name:
                raise DeriveError("Formel: Name und Ausdruck angeben")
            names, dims = {}, {}
            for c in cols:
                if c["dtype"] == "number":
                    f, d, off = _si(c.get("unit"))
                    names[c["key"]] = data[c["key"]] * f + (0.0 if _is_diff(c.get("kind")) else off)
                    dims[c["key"]] = d
            for k in op.get("consts") or []:
                sym, v, d = _const(k)
                if sym in names:
                    raise DeriveError(f"Konstante {sym}: so heisst schon eine Spalte")
                names[sym], dims[sym] = v, d
            try:
                node = E.parse(src)
                d = E.dims_of(node, dims, strict=True)
                val = E.evaluate(node, E.Ctx(names=names))
            except (E.CalcError, E.DimError, SyntaxError, ZeroDivisionError) as e:
                raise DeriveError(f"Formel „{src}“: {e}") from None
            unit = str(op.get("unit") or "").strip()
            fu, du, ou = _si(unit)
            if d is not None and not U.deq(d, du):
                raise DeriveError(f"Formel „{src}“ ergibt {U.dims_text(d) or 'eine Zahl ohne Einheit'}, nicht {unit or '1'}")
            a = np.asarray(val)
            if np.iscomplexobj(a):
                raise DeriveError(f"Formel „{src}“ ergibt komplexe Zahlen")
            try:
                a = np.broadcast_to(a.astype(float), (n,)).copy()
            except ValueError:
                raise DeriveError(f"Formel „{src}“ ergibt {a.size} Werte, der Datensatz hat {n} Zeilen") from None
            a[~np.isfinite(a)] = np.nan
            vals = (a - ou) / fu
            rep = op.get("replaces")
            key = col_key(str(op.get("key") or name), [x["key"] for x in cols if x["key"] != rep or op.get("keep")])
            nc = {"key": key, "name": name, "unit": unit, "dtype": "number", "role": str(op.get("role") or "y"),
                  "note": f"= {src}"[:200]}
            if op.get("symbol"):
                nc["symbol"] = str(op["symbol"])[:40]
            if rep and not op.get("keep"):
                i, c = find(str(rep))
                nc["role"] = str(op.get("role") or c.get("role") or "y")
                cols[i] = nc
                del data[c["key"]]
            else:
                at = len(cols)
                if rep:
                    at = find(str(rep))[0] + 1
                cols.insert(at, nc)
            data[key] = vals
            return f"Formelspalte „{name}“ = {src}" + (f" [{unit}]" if unit else "")
        else:
            raise DeriveError(f"Umrechnung „{kind}“ unbekannt")
    return ""


def make_derived(envs, version: str, parent: str, ops: list, title: str, mode: str = "live", share_id=None,
                 parent_version=None) -> dict:
    """Create (or give a new version of) a derived dataset."""
    if mode not in ("live", "pin"):
        raise DeriveError("Modus live oder pin")
    pds, penv = load(envs, parent, parent_version)
    ds = derive(pds, ops, title, {"share": parent, "version": penv["version"], "title": penv.get("title")},
                loader=lambda sid, v=None: load(envs, sid, v))
    meta = {"derive": {"parent": parent, "mode": mode, "version": penv["version"], "ops": ops}}
    return publish(envs, producer(envs, version, None, penv.get("title")), ds, share_id, **meta)


def refresh_children(envs, parent: str, version: str, depth: int = 0) -> list[dict]:
    """After a new version of `parent`: compute live derived datasets again (errors are reported, not raised)."""
    if depth >= MAX_DEPTH:
        return []
    b = box(envs)
    out = []
    for m in b.list(kind=DATA_KIND):
        d = m.get("derive") or {}
        if d.get("parent") != parent or d.get("mode") != "live" or (m.get("producer") or {}).get("module") != MODULE:
            continue
        try:
            pds, penv = load(envs, parent)
            ds = derive(pds, d.get("ops") or [], m.get("title") or "", {"share": parent, "version": penv["version"],
                                                                        "title": penv.get("title")},
                        loader=lambda sid, v=None: load(envs, sid, v))
            last = b.get(m["id"])
            if _sig(last.get("dataset") or {}) == _sig(ds.header):
                set_meta(b, m["id"], derive={**d, "version": penv["version"]}, error=None)
                continue
            env = b.publish_dataset(m.get("producer") or producer(envs, version), ds.header["title"], ds, RECIPIENTS,
                                    share_id=m["id"])
            set_meta(b, m["id"], derive={**d, "version": penv["version"]}, error=None)
            out.append({"share": m["id"], "version": env["version"]})
            out += refresh_children(envs, m["id"], version, depth + 1)
        except (DeriveError, EnvError, DS.DatasetError) as e:
            set_meta(b, m["id"], error=str(e)[:300])
            out.append({"share": m["id"], "error": str(e)})
    return out
