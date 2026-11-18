"""Strukturierte Quellenangaben für eigene Referenzen, Werkstoffwerte, Gleichungen und Konstanten.

Ein Quelleneintrag ist ein dict:

    {"type": "article", "authors": "Müller, A.; Meier, B.", "title": "…", "container": "Polymer Testing",
     "year": "2021", "volume": "93", "issue": "", "pages": "106-115", "doi": "10.1016/j.x.2020.1", "url": "",
     "accessed": "2026-11-16", "publisher": "", "edition": "", "note": "", "licence": ""}

``type``: article, book, chapter, standard, datasheet, web, thesis, report, dataset, misc. ``container`` ist je nach Typ
die Zeitschrift, der Verlag, das Buch (chapter), die Organisation (standard, datasheet, web) oder die Hochschule.

Funktionen:
- ``clean(rec)``: Felder prüfen und kürzen, unbekannte Felder verwerfen.
- ``errors(rec)``: was für eine brauchbare Angabe fehlt (leere Liste = in Ordnung).
- ``to_bib(bundle, key, rec)``: als biblatex-Eintrag in ein ``labbundle.Bundle`` (passender Eintragstyp).
- ``key_for(prefix, rec, name)``: stabiler, kollisionsarmer Schlüssel.
- ``short(rec, lang)``: Kurzform „Müller u. a. 2021“ für Beschriftungen in Abbildungen.
- ``text(rec, lang)``: ausgeschriebene Angabe für PDF-Berichte und Oberflächen (ohne LaTeX).
- ``from_legacy(text)``: alter Freitext („Quelle“) als Eintrag, damit vorhandene Daten weiter gelten.
"""
from __future__ import annotations

import hashlib
import re

TYPES = ("article", "book", "chapter", "standard", "datasheet", "web", "thesis", "report", "dataset", "misc")
FIELDS = ("type", "authors", "title", "container", "year", "volume", "issue", "pages", "doi", "url", "accessed",
          "publisher", "edition", "note", "licence")
TYPE_LABEL = {
    "de": {"article": "Zeitschriftenartikel", "book": "Buch", "chapter": "Buchkapitel", "standard": "Norm",
           "datasheet": "Datenblatt", "web": "Webseite", "thesis": "Abschlussarbeit", "report": "Bericht",
           "dataset": "Datensatz", "misc": "Sonstiges"},
    "en": {"article": "Journal article", "book": "Book", "chapter": "Book chapter", "standard": "Standard",
           "datasheet": "Data sheet", "web": "Web page", "thesis": "Thesis", "report": "Report",
           "dataset": "Dataset", "misc": "Other"},
}
_BIBTYPE = {"article": "article", "book": "book", "chapter": "incollection", "standard": "manual",
            "datasheet": "manual", "web": "online", "thesis": "thesis", "report": "report", "dataset": "dataset",
            "misc": "misc"}
_CONTAINER = {"article": "journal", "book": "publisher", "chapter": "booktitle", "standard": "organization",
              "datasheet": "organization", "web": "organization", "thesis": "institution", "report": "institution",
              "dataset": "publisher", "misc": "howpublished"}
DOI_RE = re.compile(r"^10\.\d{4,9}/[^\s{}\\]+$")
DATE_RE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")


def safe_url(u: str) -> bool:
    """URL-Felder landen unverändert in der .bib: nur http(s) ohne Klammern, Backslash oder Leerzeichen."""
    return bool(u) and u.startswith(("http://", "https://")) and not any(c in u for c in "{}\\ \n\t")


def norm_doi(d: str) -> str:
    d = (d or "").strip()
    d = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", "", d, flags=re.I)
    return d


def clean(rec) -> dict:
    if not isinstance(rec, dict):
        return {}
    out = {}
    for k in FIELDS:
        v = rec.get(k)
        if v is None:
            continue
        if isinstance(v, (list, tuple)) and k == "authors":
            v = "; ".join(str(x) for x in v)
        v = str(v).strip()[:600 if k in ("title", "note") else 300]
        if v:
            out[k] = v
    t = out.get("type", "misc")
    out["type"] = t if t in TYPES else "misc"
    if "doi" in out:
        out["doi"] = norm_doi(out["doi"])
    return out


def errors(rec, lang: str = "de") -> list[str]:
    r = clean(rec)
    de = lang == "de"
    e = []
    if not (r.get("title") or r.get("doi") or r.get("url")):
        e.append("Titel, DOI oder URL fehlt" if de else "title, DOI or URL missing")
    if r.get("doi") and not DOI_RE.match(r["doi"]):
        e.append("DOI sieht nicht wie 10.xxxx/… aus" if de else "DOI does not look like 10.xxxx/…")
    if r.get("url") and not safe_url(r["url"]):
        e.append("URL muss mit http(s):// beginnen und darf keine Leerzeichen enthalten" if de
                 else "URL must start with http(s):// and contain no spaces")
    if r.get("accessed") and not DATE_RE.match(r["accessed"]):
        e.append("Abrufdatum als JJJJ-MM-TT" if de else "access date as YYYY-MM-DD")
    if r["type"] == "article" and not r.get("container") and not r.get("doi"):
        e.append("Zeitschrift oder DOI fehlt" if de else "journal or DOI missing")
    return e


def authors_list(s: str) -> list[str]:
    """'Müller, A.; Meier, B.' oder 'Müller, A. and Meier, B.' oder 'A. Müller, B. Meier' -> Liste."""
    s = (s or "").strip()
    if not s:
        return []
    if ";" in s:
        parts = s.split(";")
    elif " and " in s:
        parts = s.split(" and ")
    elif s.count(",") >= 2 and not re.search(r",\s*[A-ZÄÖÜ]\.", s):
        parts = s.split(",")
    else:
        parts = [s] if s.count(",") <= 1 else s.split(",")
    return [p.strip() for p in parts if p.strip()]


def surname(a: str) -> str:
    a = a.strip()
    if a.startswith("{") and a.endswith("}"):          # Körperschaft in BibTeX-Klammern: ganz
        return a[1:-1].strip()
    if "," not in a and _ORG_WORDS.search(a):           # Organisation ohne Klammern: ganz
        return a
    if "," in a:
        return a.split(",")[0].strip()
    bits = a.split()
    return bits[-1] if bits else a


def short(rec, lang: str = "de") -> str:
    r = clean(rec)
    au = authors_list(r.get("authors", ""))
    who = surname(au[0]) + (" u. a." if lang == "de" else " et al.") if len(au) > 2 or "others" in au[1:] else \
        " & ".join(surname(a) for a in au) if au else (r.get("container") or r.get("title", "")[:30])
    return f"{who} {r.get('year', '')}".strip()


def key_for(prefix: str, rec, name: str = "") -> str:
    """Schlüssel aus Präfix, Erstautor/Name, Jahr und einem kurzen Hash des Inhalts (gleiche Quelle -> gleicher Schlüssel)."""
    from labbundle import slugify
    r = clean(rec)
    au = authors_list(r.get("authors", ""))
    base = slugify(surname(au[0]) if au else (name or r.get("container") or r.get("title") or "quelle"), 20)
    h = hashlib.sha1("|".join(f"{k}={r.get(k, '')}" for k in FIELDS if k != "accessed").encode("utf-8")).hexdigest()[:5]
    return "-".join(x for x in (prefix, base, r.get("year", ""), h) if x)


_ORG_WORDS = re.compile(r"\b(GmbH|AG|Inc|Ltd|LLC|SE|e\.\s?V|Institut\w*|Institute|University|Universität|Hochschule|"
                        r"Association|Society|Verband|Verein|Committee|Council|Organi[sz]ation|Technologies|Company|"
                        r"Corporation|Group|Pharmaceuticals|Laborator\w*|Agency|Bundesamt|Bureau|ISO|ASTM|DIN|NIST|IUPAC)\b", re.I)


def _is_org(a: str) -> bool:
    """Organisation statt Person? Dann in BibTeX als ein Name in Klammern (sonst zerlegt biblatex ihn in Vor-/Nachname)."""
    if "," in a or a == "others":           # „others“ = biblatex „und weitere“
        return False
    words = a.split()
    if any(re.fullmatch(r"[A-ZÄÖÜ]\.(-?[A-ZÄÖÜ]\.)*", w) for w in words):
        return False
    return bool(_ORG_WORDS.search(a)) or len(words) >= 3 or (len(words) == 1 and len(a) > 1)


def to_bib(b, key: str, rec, extra: dict | None = None) -> str:
    """Eintrag in die Literatur des Bundles schreiben; gibt den Schlüssel zurück."""
    from labbundle import tex_escape
    r = clean(rec)
    t = r["type"]
    f = {}
    au = authors_list(r.get("authors", ""))
    if au:
        f["author"] = " and ".join("{" + tex_escape(a) + "}" if _is_org(a) else tex_escape(a) for a in au)
    f["title"] = tex_escape(r.get("title", "")) or (tex_escape(r.get("doi", "")) if r.get("doi") else "")
    if r.get("container"):
        f[_CONTAINER[t]] = tex_escape(r["container"])
    if r.get("publisher") and t not in ("book", "dataset"):
        f["publisher"] = tex_escape(r["publisher"])
    for k in ("year", "volume", "pages", "edition"):
        if r.get(k):
            f[k] = tex_escape(r[k]).replace("-", "--") if k == "pages" else tex_escape(r[k])
    if r.get("issue"):
        f["number"] = tex_escape(r["issue"])
    if t == "standard":
        f["type"] = "Norm"
    if t == "datasheet":
        f["type"] = "Datenblatt"
    if r.get("doi") and DOI_RE.match(r["doi"]):
        f["doi"] = r["doi"]
    if r.get("url") and safe_url(r["url"]):
        f["url"] = r["url"]
        if r.get("accessed") and DATE_RE.match(r["accessed"]):
            f["urldate"] = r["accessed"]
    note = [tex_escape(r[k]) for k in ("note",) if r.get(k)]
    if r.get("licence"):
        note.append("Lizenz: " + tex_escape(r["licence"]))
    if note:
        f["note"] = ". ".join(note)
    f.update(extra or {})
    b.add_citation(key, _BIBTYPE[t], **f)
    return key


def text(rec, lang: str = "de") -> str:
    """Ausgeschriebene Angabe ohne LaTeX, z. B. für PDF-Berichte und Tooltips."""
    r = clean(rec)
    au = authors_list(r.get("authors", ""))
    parts = []
    if au:
        parts.append("; ".join(au) + (f" ({r['year']})" if r.get("year") else "") + ":")
    elif r.get("year"):
        parts.append(f"({r['year']})")
    if r.get("title"):
        parts.append(r["title"] + ".")
    cont = r.get("container", "")
    if cont:
        vol = (f" {r['volume']}" if r.get("volume") else "") + (f" ({r['issue']})" if r.get("issue") else "")
        parts.append(cont + vol + (f", {r['pages']}" if r.get("pages") else "") + ".")
    elif r.get("pages"):
        parts.append(f"S. {r['pages']}." if lang == "de" else f"pp. {r['pages']}.")
    if r.get("publisher") and r.get("publisher") != cont:
        parts.append(r["publisher"] + ".")
    if r.get("doi"):
        parts.append("doi:" + r["doi"])
    if r.get("url"):
        parts.append(r["url"] + (f" ({'abgerufen' if lang == 'de' else 'accessed'} {r['accessed']})" if r.get("accessed") else ""))
    if r.get("note"):
        parts.append(r["note"])
    return " ".join(parts).strip() or ("Quelle nicht angegeben" if lang == "de" else "source not given")


def from_legacy(s: str, url: str = "", year: str = "", accessed: str = "") -> dict:
    """Freitext-Quelle (bisheriges Feld „Quelle“) als Eintrag."""
    r = {"type": "web" if url else "misc", "title": (s or "").strip()}
    if url:
        r["url"] = url
    if year:
        r["year"] = str(year)
    if accessed:
        r["accessed"] = accessed
    return clean(r)


def web_asset(name: str = "labref.js") -> bytes:
    """Gemeinsame Browserdatei aus sdk/web (z. B. das Quellenformular), damit jedes Modul sie selbst ausliefern kann."""
    from pathlib import Path
    p = Path(__file__).resolve().parents[1] / "web" / name
    if p.parent.name != "web" or "/" in name or "\\" in name or ".." in name:
        raise FileNotFoundError(name)
    return p.read_bytes()


def is_record(v) -> bool:
    return isinstance(v, dict) and any(v.get(k) for k in ("title", "doi", "url", "authors"))
