"""DP-13: TGA-Lauf aus einem Datensatz (`data.table`) der Datenaufbereitung.

Gewählte Spalten werden den Rollen eines Laufs zugeordnet (Zeit, Probentemperatur, Programmtemperatur, Masse, DTG,
Wärmestrom, Gasfluss, Segment, Gas) und in die internen Einheiten umgerechnet: Zeit → min, Temperaturen → °C,
Masse → mg (Massenspalte) oder % (dimensionslose Spalte in %, ‰ …). Passt eine Einheit nicht zur Rolle, wird der Lauf
abgelehnt; ohne Einheit auch (die Einheit gehört in den Datensatz). Ausgeschlossene Zeilen bleiben weg.

Der Lauf wird als eigene kleine JSON-Datei (`folio-tga-dataset/1`) gespeichert, die `readers.load_bytes` wieder
einliest – so übersteht er Neustart, Umgebungswechsel und Bericht-Neuaufbau wie eine geladene Datei. Die Datei trägt
die Herkunft (Freigabe-ID, Titel, Version, live/fest, Spalten) als `meta["dataset"]`.
"""
from __future__ import annotations

import json
import math
import re

import numpy as np

from .readers import ROLE_LABEL, ReadError, role_of

FORMAT = "folio-tga-dataset/1"
ORDER = ("t", "T", "Tprog", "m", "dtg", "hf", "flow", "seg", "gas")
HEAD = {"t": "Zeit", "T": "Temperatur", "Tprog": "Programmtemperatur", "m": "Masse", "dtg": "DTG", "hf": "Wärmestrom",
        "flow": "Gasfluss", "seg": "Segment", "gas": "Gas"}
_EXPECT = {"t": "eine Zeit (s, min, h)", "T": "eine Temperatur (°C, K)", "Tprog": "eine Temperatur (°C, K)",
           "m": "eine Masse (mg, g) oder einen Anteil in %", "flow": "einen Volumenstrom (ml/min)"}


def _units():
    from labcalc import units as U
    return U


def _dims(unit: str):
    return _units().parse_unit(unit)[1]


def _same(unit: str, ref: str) -> bool:
    U = _units()
    try:
        return U.deq(_dims(unit), _dims(ref))
    except U.UnitError:
        return False


def _no_unit(unit: str) -> bool:
    return (unit or "").strip() in ("", "-")


def _refuse(c: dict, role: str, why: str = "") -> ReadError:
    u = c.get("unit") or ""
    lab = ROLE_LABEL.get(role, role)
    if _no_unit(u):
        return ReadError(f"Spalte „{c['name']}“ hat keine Einheit; für {lab} wird {_EXPECT.get(role, 'eine Einheit')} gebraucht "
                         "(Einheit in der Datenaufbereitung setzen)")
    return ReadError(f"Spalte „{c['name']}“ ({u}) passt nicht zur Rolle {lab}: erwartet {_EXPECT.get(role, 'eine andere Einheit')}"
                     + (f" – {why}" if why else ""))


def column(ds, key: str, role: str):
    """(Werte in der internen Einheit, Einheit) einer Spalte für eine Rolle; ReadError mit Grund, wenn sie nicht passt."""
    c = ds.col(key)
    unit = (c.get("unit") or "").strip()
    lab = ROLE_LABEL.get(role, role)
    if role == "gas":
        if c["dtype"] != "text":
            raise ReadError(f"Spalte „{c['name']}“: für {lab} wird eine Textspalte erwartet (z. B. N2, Luft)")
        return np.array([re.sub(r"[\r\n]+", " ", str(x)) for x in ds.values(key)], dtype=object), ""
    if c["dtype"] != "number":
        raise ReadError(f"Spalte „{c['name']}“ ist Text; für {lab} werden Zahlen gebraucht")
    if role in ("dtg", "hf", "seg"):                     # werden nur angezeigt bzw. mit ihrer Einheit ausgewertet
        return ds.values(key).astype(float), unit
    if _no_unit(unit):
        raise _refuse(c, role)
    if role == "t":
        if not _same(unit, "s"):
            raise _refuse(c, role)
        return ds.in_unit(key, "min"), "min"
    if role in ("T", "Tprog"):
        if not _same(unit, "K"):
            raise _refuse(c, role)
        if c.get("kind") == "temp_diff":
            raise _refuse(c, role, "die Spalte ist als Temperaturdifferenz angelegt")
        return ds.in_unit(key, "°C"), "°C"
    if role == "m":
        if _same(unit, "g"):
            return ds.in_unit(key, "mg"), "mg"
        if _same(unit, "1") and unit != "1":            # %, ‰, ppm: Anteil -> %
            return ds.in_unit(key, "%"), "%"
        raise _refuse(c, role)
    if role == "flow":
        if not _same(unit, "ml/min"):
            raise _refuse(c, role)
        return ds.in_unit(key, "ml/min"), "ml/min"
    raise ReadError(f"Rolle {role} unbekannt")


def guess(c: dict) -> str:
    """Vorschlag einer Rolle für eine Datensatzspalte (für die Auswahl in der Oberfläche)."""
    if c.get("dtype") == "text":
        return "gas" if re.search(r"gas|atmos|spül|purge", str(c.get("name") or ""), re.I) else ""
    unit = c.get("unit") or ""
    r = role_of(str(c.get("name") or ""), unit)
    if r and not _no_unit(unit) and r in _EXPECT:
        want = {"t": "s", "T": "K", "Tprog": "K", "m": "g", "flow": "ml/min"}[r]
        if not (_same(unit, want) or (r == "m" and _same(unit, "1"))):
            r = ""
    return r


def conditions(ds) -> tuple[list[str], dict]:
    """Kopfzeilen aus den Bedingungen des Datensatzes (Einwaage, Heizrate, Gas), wie sie der Leser versteht."""
    U = _units()
    head, used = [], {}
    for name, c in (ds.header.get("conditions") or {}).items():
        low, v, u = str(name).lower(), c.get("value"), str(c.get("unit") or "")
        try:
            if isinstance(v, (int, float)) and u:
                if "m0" not in used and _same(u, "g") and re.search(
                        r"einwaage|probenmasse|sample\s*(mass|weight)|initial\s*(mass|weight)|^\W*m_?0\W*$", low):
                    used["m0"] = U.to_si(float(v), u) * 1e6
                    head.append(f"# Einwaage: {used['m0']:.6g} mg")
                elif "rate" not in used and _same(u, "K/s") and re.search(r"heiz|rate|ramp|beta", low):
                    used["rate"] = U.to_si(float(v), u, diff=True) * 60.0
                    head.append(f"# Heizrate: {used['rate']:.6g} K/min")
            elif isinstance(v, str) and v.strip() and "gas" not in used and re.search(r"gas|atmos|spül|purge", low):
                used["gas"] = re.sub(r"[\r\n]+", " ", v.strip())[:80]
                head.append(f"# Gas: {used['gas']}")
        except U.UnitError:
            continue
    return head, used


def _f(v) -> float | None:
    return float(f"{v:.10g}") if v is not None and math.isfinite(v) else None


def make_raw(ds, roles: dict, source: dict) -> tuple[bytes, str]:
    """Datensatz + Rollen -> (Dateiinhalt, Dateiname) im Format folio-tga-dataset/1."""
    roles = {r: str(k) for r, k in (roles or {}).items() if r in ORDER and k}
    if "m" not in roles:
        raise ReadError("Bitte eine Massenspalte wählen.")
    if not ({"t", "T", "Tprog"} & set(roles)):
        raise ReadError("Bitte eine Temperatur- oder Zeitspalte wählen.")
    core = [roles[r] for r in ("t", "T", "Tprog", "m") if r in roles]
    if len(set(core)) < len(core):
        raise ReadError("Eine Spalte kann nicht zugleich Zeit, Temperatur und Masse sein.")
    used = ds.used_mask()
    vals, units = {}, {}
    for r in ORDER:
        if r in roles:
            vals[r], units[r] = column(ds, roles[r], r)
    keep = used & np.isfinite(vals["m"])
    keep &= np.isfinite(vals["t"]) if "t" in vals else np.isfinite(vals.get("T", vals.get("Tprog")))
    if keep.sum() < 5:
        raise ReadError(f"Datensatz „{ds.header.get('title')}“: zu wenige gültige Zeilen ({int(keep.sum())}) für einen Lauf")
    head, cond = conditions(ds)
    cols = []
    for r in ORDER:
        if r not in vals:
            continue
        a = vals[r][keep]
        c = ds.col(roles[r])
        cols.append({"name": HEAD[r], "unit": units[r], "role": r, "from": {"key": c["key"], "name": c["name"], "unit": c.get("unit") or ""},
                     "values": [str(x)[:80] for x in a] if r == "gas" else [_f(float(x)) for x in a]})
    src = dict(source or {})
    src["columns"] = {c["role"]: c["from"] for c in cols}
    src["excluded"] = int((~used).sum())
    src["rows"] = int(keep.sum())
    title = str(ds.header.get("title") or "Datensatz")
    doc = {"format": FORMAT, "title": title, "header": head, "dataset": src, "meta": cond, "columns": cols}
    stem = re.sub(r"[^\w\-]+", "_", title).strip("_")[:50] or "Datensatz"
    return json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), f"{stem}_v{src.get('version', 1)}.json"


def read_raw(data: bytes, name: str, mapping: dict | None = None):
    """Gespeicherten Datensatz-Lauf wieder einlesen (gleicher Weg wie jede Datei: build_run)."""
    from .readers import build_run, parse_meta
    try:
        doc = json.loads(data.decode("utf-8"))
        cols = doc["columns"]
        n = len(cols[0]["values"])
    except (ValueError, KeyError, IndexError, TypeError) as e:
        raise ReadError(f"{name}: Datensatz-Lauf unlesbar ({e})") from None
    data_ = np.full((n, len(cols)), np.nan)
    texts = {}
    for j, c in enumerate(cols):
        if c.get("role") == "gas":
            texts[j] = [str(x) for x in c["values"]]
        else:
            data_[:, j] = [np.nan if x is None else float(x) for x in c["values"]]
    names = [(str(c.get("name") or ""), str(c.get("unit") or "")) for c in cols]
    mp = {k: v for k, v in (mapping or {}).items() if k in ROLE_LABEL and k and v not in (None, "")}
    roles = mp or {c["role"]: j for j, c in enumerate(cols) if c.get("role")}
    unit_over = {k[:-5]: str(v) for k, v in (mapping or {}).items() if k.endswith("_unit") and v}
    meta = parse_meta(list(doc.get("header") or []))
    meta.update(format="Datensatz (Folio Lab)", file=name, header=list(doc.get("header") or []),
                dataset=doc.get("dataset") or {},
                columns=[{"name": n_, "unit": u_, "role": next((r for r, i in roles.items() if i == k_), "")}
                         for k_, (n_, u_) in enumerate(names)])
    run = build_run(data_, names, roles, meta, str(doc.get("title") or name), texts, unit_over)
    run.name = str(doc.get("title") or run.name)[:120]
    return [run]
