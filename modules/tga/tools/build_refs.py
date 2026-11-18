"""Modellbibliothek TGA aus recherchierten Literaturwerten bauen.

    python tools/build_refs.py recherche1.json [recherche2.json ...]   (im Ordner modules/tga)

Eingabe: Listen von Einträgen {material, variant, atmosphere, heating_rate_K_min, steps: [{onset_C, peak_C, end_C,
loss_pct, reaction, onset_definition, loss_theoretical_pct}], residue_pct, residue_at_C, source: {authors, title,
journal_or_publisher, year, volume_pages, doi, url, licence_if_known}, where_in_source, notes, confidence}.

Ausgabe: tga/data/referenzen.json. Fehlende Werte werden nicht erfunden; wo das Modell trotzdem eine Zahl braucht
(DTG-Spitze ohne Angabe, Stufenverlust ohne Angabe), wird sie aus den vorhandenen Werten abgeleitet und im Eintrag als
„abgeleitet“ vermerkt.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE.parents[1] / "sdk" / "python"))
import labcite  # noqa: E402

ACCESSED = "2026-11-16"
FOLDVARI = {"authors": "Földvári, M.", "title": "Handbook of thermogravimetric system of minerals and its use in geological practice",
            "journal_or_publisher": "Occasional Papers of the Geological Institute of Hungary, vol. 213, Budapest", "year": 2011,
            "volume_pages": "vol. 213, 180 pp.", "doi": None, "url": "https://www.mek.oszk.hu/18000/18031/18031.pdf",
            "licence_if_known": "frei lesbar (MEK), urheberrechtlich geschützt"}

CATS = [
    ("Kalibrierstandard", r"calcium oxalate|whewellite|cuso4|chalcanthite"),
    ("Biomasse", r"cellulose|xylan|hemicellulose|lignin|starch|wood|stärke"),
    ("Elastomer", r"^(nr|sbr|nbr|epdm)\b|silicone|pdms|rubber"),
    ("Kohlenstoff", r"carbon black|graphite|russ"),
    ("Mineral / Füllstoff", r"caco3|calcite|ca\(oh\)2|portlandite|mg\(oh\)2|mdh|al\(oh\)3|ath|gibbsite|magnes|huntite|dolomite|gypsum|"
                            r"kaolin|talc|montmorillonite|bentonite|nahco3|bicarbonate|zinc borate|glass fibre|tio2|silica"),
    ("Kunststoff", r"."),
]
NAME_DE = {"cellulose (microcrystalline)": "Cellulose (mikrokristallin)", "hemicellulose/xylan": "Hemicellulose / Xylan",
           "lignin": "Lignin", "starch": "Stärke", "wood": "Holz", "cured epoxy": "Epoxidharz (gehärtet)",
           "PDMS/silicone rubber": "Silikonkautschuk (PDMS)", "carbon black": "Russ (Carbon Black)", "graphite": "Graphit",
           "glass fibre": "Glasfaser", "talc": "Talk", "kaolinite": "Kaolinit", "montmorillonite": "Montmorillonit",
           "sodium bicarbonate NaHCO3": "Natriumhydrogencarbonat NaHCO₃"}
# Muster -> einheitlicher deutscher Name (gilt nach NAME_DE, erster Treffer gewinnt)
NAME_RX = [
    (r"^calcium oxalate", "Calciumoxalat-Monohydrat CaC₂O₄·H₂O"),
    (r"^caco3", "Calciumcarbonat CaCO₃ (Calcit)"),
    (r"^ca\(oh\)2", "Calciumhydroxid Ca(OH)₂ (Portlandit)"),
    (r"^mg\(oh\)2", "Magnesiumhydroxid Mg(OH)₂ (MDH)"),
    (r"^al\(oh\)3 \(ath\)", "Aluminiumhydroxid Al(OH)₃ (ATH)"),
    (r"^al\(oh\)3 \(gibbsite\)", "Aluminiumhydroxid Al(OH)₃ (Gibbsit)"),
    (r"^hydromagnesite", "Hydromagnesit Mg₅(CO₃)₄(OH)₂·4H₂O"),
    (r"^mgco3", "Magnesiumcarbonat MgCO₃ (Magnesit)"),
    (r"^huntite", "Huntit Mg₃Ca(CO₃)₄"),
    (r"^dolomite", "Dolomit CaMg(CO₃)₂"),
    (r"^gypsum", "Gips CaSO₄·2H₂O"),
    (r"^montmorillonite", "Montmorillonit (Bentonit)"),
    (r"^cuso4", "Kupfersulfat-Pentahydrat CuSO₄·5H₂O"),
    (r"^zinc borate", "Zinkborat 2ZnO·3B₂O₃·3,5H₂O"),
    (r"^silica \(amorphous\)", "Kieselsäure (amorph)"),
    (r"^silica \(fumed\)", "Kieselsäure (pyrogen)"),
    (r"^tio2", "Titandioxid TiO₂"),
]


def de_name(mat: str) -> str:
    if mat in NAME_DE:
        return NAME_DE[mat]
    low = mat.lower()
    for pat, nm in NAME_RX:
        if re.search(pat, low):
            return nm
    return mat


def plausible(steps, res) -> bool:
    """Massenbilanz prüfen: jede Stufe 0..100 %, Summe (+ Rückstand) physikalisch möglich."""
    if any(not 0 < s["loss"] <= 100 for s in steps):
        return False
    tot = sum(s["loss"] for s in steps)
    if res is not None:
        return 85.0 <= tot + res <= 106.0
    return tot <= 101.0


def atm(s: str) -> tuple[str, str]:
    s0 = (s or "").strip()
    low = s0.lower()
    if "then air" in low or "then oxidation" in low:
        return "N₂ → Luft" if "n2" in low or "inert" in low else "Ar → Luft", s0
    if "10 % o2" in low:
        return "O₂ 10 %", s0
    if "static air implied" in low:
        return "Luft", s0 + " (Atmosphäre in der Quelle nicht angegeben)"
    if re.search(r"synthetic air|\bair\b|oxygen", low):
        return "Luft", s0
    if re.search(r"\bn2\b|nitrogen", low):
        return "N₂", s0
    if re.search(r"\bar\b|argon", low):
        return "Ar", s0
    if re.search(r"\bhe\b|helium", low):
        return "He", s0
    if "inert" in low:
        return "inert", s0
    return "", s0


def authors(s: str) -> str:
    s = (s or "").strip()
    others = bool(re.search(r"\bet al\.?", s))
    s = re.sub(r",?\s*\bet al\.?", "", s).strip(" ,")
    parts = [p.strip() for p in re.split(r";|,(?![^()]*\))", s) if p.strip()] if s else []
    # „Müller, A.“ bereits im Format Nachname, Initialen? Dann Paare wieder zusammensetzen
    out = []
    i = 0
    while i < len(parts):
        p = parts[i]
        if i + 1 < len(parts) and re.fullmatch(r"([A-ZÄÖÜŁŚ]\.\s?-?)+", parts[i + 1]) and " " not in p.strip():
            out.append(f"{p}, {parts[i + 1]}")
            i += 2
            continue
        toks = p.split()
        if len(toks) >= 2 and re.fullmatch(r"([A-ZÄÖÜŁŚ]\.?-?)+\.?", toks[-1]):          # „Suzanne M.“
            out.append(f"{' '.join(toks[:-1])}, {toks[-1]}")
        elif len(toks) >= 2 and re.fullmatch(r"([A-ZÄÖÜŁŚ][a-z]?\.-?)+", toks[0]):          # „P.T. Williams“, „O.Yu. Fetisova“
            # alles nach den Initialen ist Nachname („A.F. Al Naim“, „N.R. de Carvalho“, „E. Apaydın Varol“)
            out.append(f"{' '.join(toks[1:])}, {toks[0]}")
        else:
            out.append(p)
        i += 1
    if others:
        out.append("others")
    return "; ".join(out)


def vol_pages(s):
    s = (s or "").strip()
    if not s:
        return {}
    m = re.match(r"^(?:vol\.\s*)?(\d+)\s*(?:\(([\w\-–]+)\))?\s*,?\s*(?:article\s*)?(.*)$", s)
    if not m:
        return {"note": s}
    out = {"volume": m.group(1)}
    if m.group(2):
        out["issue"] = m.group(2)
    rest = (m.group(3) or "").strip()
    if rest:
        out["pages"] = rest.replace("–", "-")
    return out


def source(src, where: str) -> dict:
    if src == "FOLDVARI" or not isinstance(src, dict):
        src = FOLDVARI
    cont = (src.get("journal_or_publisher") or "").strip()
    title = (src.get("title") or "").strip()
    low = (cont + " " + title).lower()
    if src.get("doi"):
        t = "article"
    elif re.search(r"netzsch|application note|data ?sheet|technical|borax|product", low):
        t = "datasheet"
    elif re.search(r"handbook|textbook|libretexts|book", low) and not src.get("doi"):
        t = "book" if "libretexts" not in low else "web"
    elif src.get("doi") or re.search(r"journal|chem|polym|fuel|materials|letters|acta|science|energ|sci", low):
        t = "article"
    else:
        t = "web" if src.get("url") else "misc"
    rec = {"type": t, "authors": authors(src.get("authors") or ""), "title": title, "container": cont,
           "year": str(src.get("year") or ""), "doi": src.get("doi") or "", "url": src.get("url") or "",
           "accessed": ACCESSED if src.get("url") else "", "licence": src.get("licence_if_known") or "",
           "note": ("Werte: " + where) if where else ""}
    vp = vol_pages(src.get("volume_pages"))
    if t == "article":
        rec.update({k: v for k, v in vp.items() if k != "note"})
    elif src.get("volume_pages"):
        rec["note"] = (rec["note"] + "; " if rec["note"] else "") + str(src["volume_pages"])
    r = labcite.clean(rec)
    if r.get("url") and not labcite.safe_url(r["url"]):
        r["url"] = r["url"].replace(" ", "%20")
    return r


def category(material: str) -> str:
    low = material.lower()
    for cat, pat in CATS:
        if re.search(pat, low):
            return cat
    return "Kunststoff"


def num(v):
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        m = re.search(r"-?\d+(?:\.\d+)?", str(v))
        return float(m.group()) if m else None


def convert(x: dict) -> dict | None:
    flags = []
    steps = []
    for s in x.get("steps") or []:
        on, pk, en, lo = num(s.get("onset_C")), num(s.get("peak_C")), num(s.get("end_C")), num(s.get("loss_pct"))
        if pk is None and on is not None and en is not None:
            pk = on + 0.6 * (en - on)
            flags.append("DTG-Spitze aus Onset/Ende abgeleitet")
        if pk is None:
            continue
        st = {"T_peak": round(pk, 1)}
        if on is not None and on < pk:
            st["T_onset"] = on
        if en is not None and en > pk:
            st["T_end"] = en
        if lo is not None:
            st["loss"] = lo
        elif num(s.get("loss_theoretical_pct")) is not None:
            st["loss"] = num(s["loss_theoretical_pct"])
            flags.append("Stufenverlust = theoretischer Wert (Stöchiometrie), nicht gemessen")
        if s.get("reaction"):
            st["label"] = str(s["reaction"])[:80]
        steps.append(st)
    if not steps:
        return None
    res = num(x.get("residue_pct"))
    missing = [s for s in steps if "loss" not in s]
    organic = category(x["material"]) in ("Kunststoff", "Elastomer", "Biomasse")
    if missing:
        # nur ableiten, wenn genau eine Stufe fehlt und die Gesamtbilanz bekannt ist (Rückstand oder organischer Stoff
        # mit einer Stufe); sonst würde das Modell Zahlen erfinden -> Eintrag verwerfen
        if len(missing) > 1:
            return None
        known = sum(s["loss"] for s in steps if "loss" in s)
        if res is not None:
            total, how = 100.0 - res, "Stufenverlust aus Rückstand abgeleitet"
        elif organic and len(steps) == 1:
            total, how = 100.0, "Stufenverlust nicht angegeben, vollständige Zersetzung angenommen"
        else:
            return None
        rest = total - known
        if rest <= 0.5:
            steps = [s for s in steps if "loss" in s]
        else:
            missing[0]["loss"] = round(rest, 2)
            flags.append(how)
    steps = [s for s in steps if s.get("loss", 0) > 0]
    if not steps or not plausible(steps, res):
        return None
    a, a_note = atm(x.get("atmosphere"))
    mat = x["material"].strip()
    src = source(x.get("source"), (x.get("where_in_source") or "").strip())
    name = de_name(mat)
    var = (x.get("variant") or "").strip()
    defs = sorted({str(s.get("onset_definition")) for s in x.get("steps") or [] if s.get("onset_definition")})
    note = "; ".join(p for p in [var, ("Atmosphäre: " + a_note) if a_note else "", x.get("notes") or "",
                                 ("Onset: " + " / ".join(defs)) if defs else "", ", ".join(dict.fromkeys(flags))] if p)
    e = {"name": name, "variant": var[:160], "category": category(mat), "atmosphere": a,
         "rate": num(x.get("heating_rate_K_min")) if isinstance(x.get("heating_rate_K_min"), (int, float)) else None,
         "steps": steps, "source": src, "note": note[:900], "derived": list(dict.fromkeys(flags))}
    if not isinstance(x.get("heating_rate_K_min"), (int, float)) and x.get("heating_rate_K_min"):
        e["note"] = (f"Heizprogramm: {x['heating_rate_K_min']}; " + e["note"])[:900]
    if res is not None:
        e["residue"] = res
        if x.get("residue_at_C") is not None:
            e["residue_at"] = num(x["residue_at_C"])
    return e


def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:30]


def main(paths):
    raw = []
    for p in paths:
        raw += json.loads(Path(p).read_text(encoding="utf-8"))
    entries, skipped = [], []
    for x in raw:
        e = convert(x)
        if e is None:
            skipped.append(x.get("material"))
            continue
        entries.append(e)
    # gleiche Namen unterscheiden: Kurzquelle anhängen
    count = {}
    for e in entries:
        count[e["name"]] = count.get(e["name"], 0) + 1
    seen = {}
    for e in entries:
        base = slug(e["name"]) or "eintrag"
        seen[base] = seen.get(base, 0) + 1
        e["id"] = f"{base}-{seen[base]}"
        e["group"] = base
        if count[e["name"]] > 1:
            e["name"] = f"{e['name']} ({labcite.short(e['source'])}, {e['atmosphere'] or '?'})"
    # immer noch gleich (gleiche Quelle, andere Probe): Variante anhängen
    count = {}
    for e in entries:
        count[e["name"]] = count.get(e["name"], 0) + 1
    for e in entries:
        if count[e["name"]] > 1 and e.get("variant"):
            e["name"] = f"{e['name']} – {e['variant'][:40].rstrip(' ,;')}"
    out ={"format": "folio-tga-bibliothek/1", "name": "Modellbibliothek TGA",
           "hinweis": "DTG-Kurven werden aus diesen veröffentlichten Stufenwerten berechnet (Fraser-Suzuki-Spitzen); keine "
                      "gemessenen Kurven. Werte aus Text und Tabellen der genannten Quellen (Abruf 16.11.2026), nicht aus "
                      "Abbildungen. Vor Gebrauch für belastbare Aussagen gegen die Quelle prüfen.",
           "source": {"type": "misc", "title": "Modellbibliothek TGA (Folio Lab): Stufenwerte aus der Literatur", "year": "2026",
                      "note": "Zusammenstellung; Quelle je Eintrag"},
           "entries": entries}
    dst = HERE / "tga" / "data" / "referenzen.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(entries)} Einträge nach {dst}; übersprungen (keine verwertbare Stufe): {skipped}")


if __name__ == "__main__":
    main(sys.argv[1:])
