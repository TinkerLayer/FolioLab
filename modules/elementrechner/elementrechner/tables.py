"""Import eigener Datentabellen (ER-X04): CSV oder JSON -> eigene Stoffe mit eigenen Werten.

Jede Zeile ist ein Wert: Stoff (name, optional formula/cas), Grösse (property), Zahl (value), Einheit, Temperatur,
Phase und Quelle. Eine Quelle ist Pflicht – je Tabelle (JSON "source" oder CSV-Kopfzeilen "# Quelle: …",
"# DOI: …", "# URL: …", "# Autoren: …", "# Jahr: …") oder je Zeile (Spalten source, source_doi, source_url,
source_authors, source_year). Zeilen ohne Quelle werden abgelehnt. Importierte Werte sind eigene Werte und gehen
den mitgelieferten vor (substances.prop).
"""
from __future__ import annotations

import csv
import io
import json
import re

import labcite as LC
import labtable as LT

from labcalc import substances as S

THERMO = {"dfH": "kJ/mol", "dfG": "kJ/mol", "S0": "J/(mol*K)", "Cp": "J/(mol*K)"}
# Bezeichnungen, die in Kopfzeilen und Grössenspalten verstanden werden
ALIASES = {
    "name": ("name", "stoff", "substance", "bezeichnung"), "name_en": ("name_en", "english name", "englischer name"),
    "formula": ("formula", "formel", "summenformel"), "cas": ("cas", "cas-nr", "cas number", "casrn"),
    "property": ("property", "grösse", "groesse", "größe", "eigenschaft", "quantity"),
    "value": ("value", "wert", "zahl"), "unit": ("unit", "einheit"), "T": ("t", "t_c", "temperatur", "temperature", "t/°c"),
    "phase": ("phase",), "note": ("note", "bemerkung", "anmerkung", "txt"),
    "source": ("source", "quelle", "source_title", "titel"), "source_doi": ("source_doi", "doi"),
    "source_url": ("source_url", "url"), "source_authors": ("source_authors", "autoren", "authors"),
    "source_year": ("source_year", "jahr", "year"),
}
PROP_ALIASES = {**{k: k for k in list(S.PROPS) + ["pka"] + list(THERMO)},
                **{S.norm(v[0]): k for k, v in S.PROPS.items()}, **{S.norm(v[1]): k for k, v in S.PROPS.items()},
                "pka": "pka", "pks": "pka", "schmp": "mp", "sdp": "bp", "smp": "mp", "kp": "bp", "rho": "density",
                "dfh": "dfH", "δfh°": "dfH", "dfg": "dfG", "s°": "S0", "s0": "S0", "cp": "Cp"}
TEXT_PROPS = {"descr", "color", "odor", "decomp", "stability"}


def _col(h: str) -> str | None:
    h = S.norm(h).strip("# ")
    for k, al in ALIASES.items():
        if h in al:
            return k
    return None


def _num(s) -> float:
    """Number from a cell (shared rules in `labtable.number`); ValueError when it is not one."""
    v = LT.number(s)
    if v is None:
        raise ValueError(f"keine Zahl: {s!r}")
    return v


def _source(d: dict) -> dict | None:
    rec = {}
    if d.get("source"):
        rec = LC.from_legacy(str(d["source"]), url=str(d.get("source_url") or ""), year=str(d.get("source_year") or ""))
    if d.get("source_doi"):
        rec["doi"] = LC.norm_doi(str(d["source_doi"]))
    if d.get("source_url") and LC.safe_url(str(d["source_url"])):
        rec["url"] = str(d["source_url"]).strip()
    if d.get("source_authors"):
        rec["authors"] = str(d["source_authors"]).strip()
    if d.get("source_year"):
        rec["year"] = str(d["source_year"]).strip()
    if rec and not rec.get("type"):
        rec["type"] = "article" if rec.get("doi") else "web" if rec.get("url") else "misc"
    return LC.clean(rec) if LC.is_record(rec) else None


def parse(text: str, fmt: str = "") -> tuple[list[dict], dict | None]:
    """Zeilen (als dict mit Standardspalten) und die Tabellenquelle."""
    text = (text or "").lstrip("﻿")
    if not text.strip():
        raise ValueError("Tabelle ist leer")
    if fmt == "json" or text.lstrip().startswith(("{", "[")):
        d = json.loads(text)
        rows = d.get("rows") if isinstance(d, dict) else d
        if not isinstance(rows, list):
            raise ValueError("JSON: Liste „rows“ erwartet")
        src = d.get("source") if isinstance(d, dict) else None
        if isinstance(src, str):
            src = LC.from_legacy(src)
        out = []
        for r in rows:
            if isinstance(r, dict):
                out.append({c: v for k, v in r.items() if (c := _col(str(k)))})
        return out, (LC.clean(src) if LC.is_record(src) else None)
    head, body = {}, []
    for line in text.splitlines():
        m = re.match(r"^\s*#\s*([^:]+):\s*(.+)$", line)
        if m and not body:
            c = _col(m.group(1)) or {"quelle": "source", "source": "source"}.get(S.norm(m.group(1)))
            if c and c.startswith("source"):
                head[c] = m.group(2).strip()
            continue
        if line.strip() and not line.lstrip().startswith("#"):
            body.append(line)
    if not body:
        raise ValueError("keine Datenzeilen")
    sample = body[0]
    delim = max(";\t,", key=sample.count) if any(c in sample for c in ";\t,") else ","
    rd = csv.reader(io.StringIO("\n".join(body)), delimiter=delim)
    hdr = next(rd)
    cols = [_col(h) for h in hdr]
    if "name" not in cols or "value" not in cols or "property" not in cols:
        raise ValueError("Spalten „name“, „property“ und „value“ werden gebraucht (Kopfzeile)")
    rows = [{c: v.strip() for c, v in zip(cols, r) if c and v.strip()} for r in rd if any(x.strip() for x in r)]
    return rows, _source(head)


def to_items(rows: list[dict], table_src: dict | None, existing: list[dict]) -> tuple[list[dict], list[dict]]:
    """Zeilen zu Einträgen für den Stoffspeicher. Vorhandene eigene Stoffe (gleicher Name) werden ergänzt."""
    by_name = {S.norm(it.get("name") or ""): dict(it, values={k: list(v) for k, v in (it.get("values") or {}).items()})
               for it in existing}
    touched, errors = {}, []
    for i, r in enumerate(rows, start=1):
        name = (r.get("name") or "").strip()
        if not name:
            errors.append({"row": i, "error": "Name fehlt"})
            continue
        prop = PROP_ALIASES.get(S.norm(r.get("property") or "")) or PROP_ALIASES.get(str(r.get("property") or "").strip())
        if not prop:
            errors.append({"row": i, "error": f"unbekannte Grösse „{r.get('property')}“"})
            continue
        src = _source(r) or table_src
        if not src:
            errors.append({"row": i, "error": "keine Quelle (weder in der Zeile noch für die Tabelle)"})
            continue
        if LC.errors(src):
            errors.append({"row": i, "error": "Quelle: " + ", ".join(LC.errors(src))})
            continue
        val = {"u": r.get("unit") or THERMO.get(prop, ""), "source": src, "txt": (r.get("note") or "")[:200]}
        if prop in TEXT_PROPS:
            errors.append({"row": i, "error": f"„{prop}“ ist eine Textangabe; nur Zahlenwerte werden importiert"})
            continue
        try:
            val["v"] = _num(r.get("value"))
        except (TypeError, ValueError):
            errors.append({"row": i, "error": f"Wert „{r.get('value')}“ ist keine Zahl"})
            continue
        if r.get("T") not in (None, ""):
            try:
                val["T"] = _num(r["T"])
            except ValueError:
                errors.append({"row": i, "error": f"Temperatur „{r.get('T')}“ ist keine Zahl"})
                continue
        if prop in THERMO:
            val["phase"] = (r.get("phase") or "").strip()
        k = S.norm(name)
        it = by_name.get(k)
        if it is None:
            it = {"name": name, "values": {}, "kind": "mixture", "classes": ["Importierte Tabelle"]}
            try:                                               # Stoff der Sammlung? Dann gelten die Werte für ihn (Vorrang)
                ref = S.resolve(r.get("cas") or name)
            except Exception:  # noqa: BLE001
                ref = None
            if ref and not str(ref).startswith("own:"):
                it["ref"] = ref
        for f in ("name_en", "formula", "cas"):
            if r.get(f) and not it.get(f):
                it[f] = r[f].strip()
        if it.get("formula") and it.get("kind") == "mixture":
            it["kind"] = "molecule"
        if not it.get("source"):
            it["source"] = table_src or src
        it["values"].setdefault(prop, [])
        it["values"][prop] = [v for v in it["values"][prop] if not (v.get("T") == val.get("T") and LC.clean(v.get("source") or {}) == src)]
        it["values"][prop].insert(0, val)
        by_name[k] = it
        touched[k] = it
    return list(touched.values()), errors


def export_csv(items: list[dict]) -> str:
    """Alle eigenen Werte als CSV im Importformat (Quelle je Zeile), Semikolon, Punkt als Dezimaltrennzeichen."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\n")
    w.writerow(["name", "formula", "cas", "property", "value", "unit", "T", "phase", "note",
                "source", "source_authors", "source_year", "source_doi", "source_url"])
    for it in items:
        for prop, vals in (it.get("values") or {}).items():
            for v in vals:
                if v.get("est"):
                    continue
                s = LC.clean(v.get("source") or it.get("source") or {})
                w.writerow([it.get("name", ""), it.get("formula", ""), it.get("cas", ""), prop, repr(float(v["v"])),
                            v.get("u", ""), "" if v.get("T") is None else repr(float(v["T"])), v.get("phase", ""),
                            v.get("txt", ""), s.get("title", ""), s.get("authors", ""), s.get("year", ""),
                            s.get("doi", ""), s.get("url", "")])
    return buf.getvalue()
