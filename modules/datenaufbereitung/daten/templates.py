"""Reading templates and batches (DP-09).

A template is the marking recipe of one sheet plus "anchors": the texts the recipe relies on (names in the header
line(s), the units line, labels of metadata cells). Applied to another file, the anchors are compared first; a file
whose header moved or changed is refused with the cells that do not fit. The data block grows or shrinks with the
file (rows until the numbers end), everything else is taken as it is.

Batch: one template over several loaded files → one dataset per file, or one combined dataset with a file column
(conditions that differ between the files become columns).
"""
from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path

import numpy as np

import labdataset as DS

from . import recipe as RC
from .sheet import EMPTY, TEXT, Sheet, parse_ref, range_ref, ref

FILE = "datenaufbereitung_vorlagen.json"
MAX_TEMPLATES = 200
MAX_ANCHORS = 80


class TemplateError(ValueError):
    def __init__(self, msg: str, problems=None):
        super().__init__(msg)
        self.problems = problems or []


def _norm(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().casefold()


def anchors(sh: Sheet, steps) -> list[dict]:
    """Texts the recipe depends on: header and units lines over the block, labels next to metadata cells."""
    L = RC.layout_of(steps)
    if not L["block"]:
        raise TemplateError("Kein Datenblock markiert – erst die Tabelle lesen, dann als Vorlage speichern")
    v = RC.View(sh, L["transpose"])
    r0, c0, r1, c1 = L["block"]
    (l0, s0), (l1, s1) = v.ls(r0, c0), v.ls(r1, c1)
    s0, s1 = sorted((s0, s1))
    out = []
    for line, what in [(h, "header") for h in L["header"]] + ([(L["units"], "units")] if L["units"] is not None else []):
        for s in range(s0, s1 + 1):
            t = v.text(line, s)
            if t:
                out.append({"cell": v.ref(line, s), "text": t[:120], "what": what})
    for (r, c) in L["meta"]:
        for rr, cc in ((r, c - 1), (r, c)):                    # "Temperatur:" left of the value, or "T: 25 °C"
            if 0 <= rr < sh.rows and 0 <= cc < sh.cols and sh.typ[rr, cc] == TEXT:
                t = (sh.display(rr, cc) or "").strip()
                m = re.match(r"^\s*([^:=]{1,40}?)\s*[:=]", t)
                lab = m.group(1) if m else (t if cc != c else "")
                if lab:
                    out.append({"cell": ref(rr, cc), "text": lab[:120], "what": "meta", "prefix": bool(m)})
                    break
    return out[:MAX_ANCHORS]


def check(sh: Sheet, tpl: dict) -> list[dict]:
    """Anchors that do not fit: [{"cell", "expected", "found", "what"}]."""
    probs = []
    for a in tpl.get("anchors") or []:
        r, c = parse_ref(a["cell"])
        found = sh.display(r, c) if 0 <= r < sh.rows and 0 <= c < sh.cols and sh.typ[r, c] != EMPTY else ""
        found = str(found or "").strip()
        if a.get("prefix"):
            m = re.match(r"^\s*([^:=]{1,40}?)\s*[:=]", found)
            got = m.group(1) if m else found
        else:
            got = found
        if _norm(got) != _norm(a["text"]):
            probs.append({"cell": a["cell"], "expected": a["text"], "found": found[:120], "what": a.get("what", "")})
    return probs


def fit_block(sh: Sheet, steps) -> list[dict]:
    """The data block of the template, extended or shortened to where the numbers of this file end."""
    out = [dict(s) for s in steps]
    L = RC.layout_of(out)
    b = next((s for s in out if s.get("op") == "block"), None)
    if not b or (L["repeat"] and (L["repeat"]["dir"] == "right") == L["transpose"]):
        return out                                    # blocks repeat along the lines: their length stays fixed
    v = RC.View(sh, L["transpose"])
    r0, c0, r1, c1 = L["block"]
    l0, s0 = v.ls(r0, c0)
    l1, s1 = v.ls(r1, c1)
    l0 = min(l0, l1)
    s_lo, s_hi = sorted((s0, s1))
    num = RC._is_numeric(sh.typ, sh.num) | RC._marker_mask(sh)
    typ = sh.typ
    if L["transpose"]:
        num, typ = num.T, typ.T
    end, weak = l0 - 1, 0
    for line in range(l0, v.nl):                          # numbers until an empty line or a third text-only line
        if num[line, s_lo:s_hi + 1].any():
            end, weak = line, 0
        elif not (typ[line, s_lo:s_hi + 1] != EMPTY).any():
            break
        else:
            weak += 1
            if weak > 2:
                break
    if end < l0:
        raise TemplateError(f"Keine Zahlen ab {v.ref(l0, s_lo)} – der Datenblock beginnt in dieser Datei woanders",
                            [{"cell": v.ref(l0, s_lo), "expected": "Zahlen", "found": v.text(l0, s_lo), "what": "block"}])
    a, z = v.rc(l0, s_lo), v.rc(end, s_hi)
    b["range"] = range_ref(min(a[0], z[0]), min(a[1], z[1]), max(a[0], z[0]), max(a[1], z[1]))
    return out


def apply(sh: Sheet, tpl: dict) -> list[dict]:
    """Recipe steps of the template for this sheet, or TemplateError with the cells that do not fit."""
    probs = check(sh, tpl)
    if probs:
        p = probs[0]
        more = f" (und {len(probs) - 1} weitere)" if len(probs) > 1 else ""
        raise TemplateError(f"Vorlage „{tpl.get('name')}“ passt nicht: {p['cell']} sollte „{p['expected']}“ sein, "
                            f"steht „{p['found'] or 'leer'}“{more}", probs)
    return fit_block(sh, tpl.get("steps") or [])


# ----------------------------------------------------------------------------- storage
class Store:
    def __init__(self, root: Path):
        self.path = Path(root) / FILE

    def _read(self) -> list[dict]:
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
            return d.get("templates") or [] if isinstance(d, dict) else []
        except (OSError, ValueError):
            return []

    def _write(self, items: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"format": "datenaufbereitung-vorlagen/1", "templates": items}, ensure_ascii=False,
                                  indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def list(self) -> list[dict]:
        return self._read()

    def get(self, tid: str) -> dict:
        for t in self._read():
            if t["id"] == tid:
                return t
        raise LookupError("Vorlage nicht gefunden")

    def save(self, sh: Sheet, steps, name: str, source: dict, tid: str | None = None) -> dict:
        name = str(name or "").strip()[:80]
        if not name:
            raise TemplateError("Name der Vorlage fehlt")
        if not isinstance(steps, list) or not steps or len(steps) > 500:
            raise TemplateError("Rezept leer oder ungültig")
        RC.extract(sh, steps)                                  # only a recipe that reads this sheet is saved
        items = self._read()
        if any(t["name"].casefold() == name.casefold() and t["id"] != tid for t in items):
            raise TemplateError(f"Eine Vorlage „{name}“ gibt es schon")
        rec = {"id": tid or uuid.uuid4().hex[:10], "name": name, "steps": steps, "anchors": anchors(sh, steps),
               "source": {k: str(v)[:160] for k, v in (source or {}).items()}, "saved": time.strftime("%Y-%m-%d %H:%M")}
        items = [t for t in items if t["id"] != rec["id"]] + [rec]
        if len(items) > MAX_TEMPLATES:
            raise TemplateError(f"Höchstens {MAX_TEMPLATES} Vorlagen")
        self._write(items)
        return rec

    def delete(self, tid: str) -> None:
        self._write([t for t in self._read() if t["id"] != tid])


# ----------------------------------------------------------------------------- combined dataset
def combine(parts: list[tuple[str, dict]], title: str) -> dict:
    """[(file name, extracted table)] → one table with a file column. Columns are matched by name (all columns of
    all files; a column a file lacks stays empty there); the same quantity in another unit is converted into the unit
    of the first file that has it. Conditions that differ between the files become columns."""
    if not parts:
        raise TemplateError("Keine Datei gelesen")
    from labcalc import units as U
    base = parts[0][1]
    protos, first = [], {}                                      # union of the columns, in order of appearance
    for name, t in parts:
        for c in t["columns"]:
            p = next((x for x in protos if x["name"] == c["name"]), None)
            if p is None:
                of = next((x["name"] for x in t["columns"] if c.get("of") and x.get("key") == c["of"]), None)
                protos.append({**c, "_of": of})
                first[c["name"]] = name
            elif p["dtype"] != c["dtype"]:
                raise TemplateError(f"„{name}“: Spalte „{c['name']}“ ist {'Text' if c['dtype'] == 'text' else 'Zahl'}, "
                                    f"in „{first[c['name']]}“ {'Text' if p['dtype'] == 'text' else 'Zahl'}")
    conv_notes, cols = [], []
    for p in protos:
        vals, raw, mk, off, missing = [], {}, {}, 0, []
        for name, t in parts:
            c = next((x for x in t["columns"] if x["name"] == p["name"]), None)
            if c is None:
                vals.append(np.full(t["rows"], np.nan) if p["dtype"] == "number" else np.array([""] * t["rows"], dtype=object))
                missing.append(name)
                off += t["rows"]
                continue
            v = np.asarray(c["values"], float) if p["dtype"] == "number" else np.asarray(c["values"], dtype=object)
            u0, u1 = p.get("unit") or "", c.get("unit") or ""
            if p["dtype"] == "number" and u1 != u0:              # same quantity, other unit (e.g. min/h) → convert
                try:
                    f1, d1, o1 = U.parse_unit(u1)
                    f0, d0, o0 = U.parse_unit(u0)
                except U.UnitError:
                    d1, d0 = 1, 0
                if d1 != d0 or not U.compatible(u1, u0):         # U-01: pH nicht in % usw.
                    raise TemplateError(f"„{name}“: Spalte „{c['name']}“ in {u1 or '1'} passt nicht zu {u0 or '1'} "
                                        f"in „{first[p['name']]}“")
                diff = c.get("role") == "uncertainty" or (c.get("kind") or p.get("kind")) == "temp_diff"
                v = (v * f1 + (0.0 if diff else o1 - o0)) / f0
                conv_notes.append(f"„{name}“: Spalte „{c['name']}“ von {u1 or '1'} in {u0 or '1'} umgerechnet")
            vals.append(v)
            raw.update({off + i: x for i, x in c["raw"].items()})
            mk.update({off + i: x for i, x in (c.get("mk") or {}).items()})
            off += t["rows"]
        if missing:
            conv_notes.append(f"Spalte „{p['name']}“ fehlt in " + ", ".join(f"„{m}“" for m in missing[:6]) + " (leer gelassen)")
        cols.append({**{kk: vv for kk, vv in p.items() if kk not in ("values", "raw", "mk", "key")},
                     "values": np.concatenate(vals), "raw": raw, "mk": mk})
    n = sum(t["rows"] for _, t in parts)
    names = []
    for i, (name, t) in enumerate(parts):
        names += [name] * t["rows"]
    cols.insert(0, {"name": "Datei", "unit": "", "dtype": "text", "values": np.array(names, dtype=object), "raw": {},
                    "mk": {}, "date": False, "cells": "Dateiname", "errors": 0, "j": None, "role": "group", "of_j": None})
    conds, notes = {}, []
    allk = list(dict.fromkeys(k for _, t in parts for k in t["conditions"]))
    for k in allk:
        vs = [t["conditions"].get(k) for _, t in parts]
        if all(v is not None and v.get("value") == vs[0].get("value") and v.get("unit") == vs[0].get("unit") for v in vs):
            conds[k] = vs[0]
            continue
        num = all(v is not None and isinstance(v.get("value"), float) for v in vs) and len({v.get("unit") for v in vs}) == 1
        if num:
            arr = np.concatenate([np.full(t["rows"], v["value"]) for (_, t), v in zip(parts, vs)])
            cols.append({"name": k, "unit": vs[0].get("unit") or "", "dtype": "number", "values": arr, "raw": {}, "mk": {},
                         "date": False, "cells": "Bedingung je Datei", "errors": 0, "j": None, "role": "condition", "of_j": None})
        else:
            arr = np.concatenate([np.array([("" if v is None else str(v.get("value"))) + (" " + v["unit"] if v and v.get("unit") else "")]
                                           * t["rows"], dtype=object) for (_, t), v in zip(parts, vs)])
            cols.append({"name": k, "unit": "", "dtype": "text", "values": arr, "raw": {}, "mk": {}, "date": False,
                         "cells": "Bedingung je Datei", "errors": 0, "j": None, "role": "condition", "of_j": None})
        notes.append(f"Bedingung „{k}“ unterscheidet sich zwischen den Dateien – als Spalte geführt")
    taken = set()
    for c in cols:
        c["key"] = DS.safe_key(c["name"], taken)
        taken.add(c["key"])
    by_name = {c["name"]: c for c in cols}
    for c in cols:
        of_name = c.pop("_of", None)
        if c.get("role") == "uncertainty" and c.get("of"):
            ref_c = by_name.get(of_name) if of_name else None
            c["of"] = ref_c["key"] if ref_c else None
    return {"columns": cols, "rows": n, "conditions": conds, "notes": (conv_notes + notes + [n for _, t in parts for n in t["notes"]])[:50],
            "marks": [], "blocks": len(parts), "layout": base["layout"]}
