"""Gemeinsame Werkstoffdatenbank: Kennwerte von Metallen, Polymeren, Keramiken, Gläsern, Fasern und Verbunden.

Eine Datei (``data/materials.json``) für Rechner und Zugversuch. Jede Zahl nennt ihre Quelle: einen Schlüssel aus
``sources.REFS`` oder einen Quellentext (Datenblatt, Norm). Die Vergleichswerkstoffe des Zugversuchs stehen mit ihren
bisherigen Feldern in derselben Liste (``"zugversuch": true``); ``load_alloys`` im Zugversuch liest genau diese Zeilen.

Werte sind in der Datei in einer lesbaren Einheit eingetragen (GPa, g/cm³, °C …); ``value`` rechnet sie in SI um.
Optional nachgeladene Teile (``data/optional/materials_*.json``) werden angehängt, ohne gleichnamige Einträge zu
überschreiben.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from . import units as U

DATA = Path(__file__).resolve().parent / "data"
PATH = DATA / "materials.json"

# Schlüssel -> (Grössenart in units.KINDS, Anzeigeeinheit, Name DE, Name EN)
PROPS: dict[str, tuple[str, str, str, str]] = {
    "rho": ("density", "g/cm^3", "Dichte", "Density"),
    "E": ("modulus", "GPa", "Elastizitätsmodul", "Young's modulus"),
    "G": ("modulus", "GPa", "Schubmodul", "Shear modulus"),
    "K": ("modulus", "GPa", "Kompressionsmodul", "Bulk modulus"),
    "nu": ("number", "1", "Querkontraktionszahl", "Poisson's ratio"),
    "Rp": ("stress", "MPa", "Dehngrenze Rp0,2 bzw. Streckgrenze", "Yield strength (0.2 % offset)"),
    "Rm": ("stress", "MPa", "Zugfestigkeit", "Tensile strength"),
    "A": ("strain", "%", "Bruchdehnung", "Elongation at break"),
    "sigma_c": ("stress", "MPa", "Druckfestigkeit", "Compressive strength"),
    "sigma_f": ("stress", "MPa", "Biegefestigkeit", "Flexural strength"),
    "HV": ("number", "1", "Vickershärte", "Vickers hardness"),
    "KIc": ("stress_int", "MPa*m^0.5", "Bruchzähigkeit K_Ic", "Fracture toughness K_Ic"),
    "m_W": ("number", "1", "Weibull-Modul", "Weibull modulus"),
    "Tm": ("temperature", "°C", "Schmelztemperatur", "Melting temperature"),
    "Tg": ("temperature", "°C", "Glasübergangstemperatur", "Glass transition temperature"),
    "alpha": ("expansion", "µm/(m*K)", "Längenausdehnungskoeffizient", "Coefficient of thermal expansion"),
    "lambda": ("conductivity_th", "W/(m*K)", "Wärmeleitfähigkeit", "Thermal conductivity"),
    "cp": ("spec_heat", "J/(kg*K)", "Spez. Wärmekapazität", "Specific heat capacity"),
    "rho_el": ("resistivity", "µOhm*cm", "Spez. elektrischer Widerstand", "Electrical resistivity"),
    "Eg": ("energy", "eV", "Bandlücke", "Band gap"),
    "a": ("length", "nm", "Gitterkonstante a", "Lattice parameter a"),
    "c": ("length", "nm", "Gitterkonstante c", "Lattice parameter c"),
    "struktur": ("text", "", "Kristallstruktur", "Crystal structure"),
    # unidirektionale Schicht (1 = Faserrichtung)
    "E1": ("modulus", "GPa", "E-Modul längs (E₁)", "Longitudinal modulus E1"),
    "E2": ("modulus", "GPa", "E-Modul quer (E₂)", "Transverse modulus E2"),
    "G12": ("modulus", "GPa", "Schubmodul (G₁₂)", "In-plane shear modulus G12"),
    "nu12": ("number", "1", "Querkontraktionszahl (ν₁₂)", "Major Poisson's ratio nu12"),
    "Xt": ("stress", "MPa", "Zugfestigkeit längs (X_t)", "Longitudinal tensile strength Xt"),
    "Xc": ("stress", "MPa", "Druckfestigkeit längs (X_c)", "Longitudinal compressive strength Xc"),
    "Yt": ("stress", "MPa", "Zugfestigkeit quer (Y_t)", "Transverse tensile strength Yt"),
    "Yc": ("stress", "MPa", "Druckfestigkeit quer (Y_c)", "Transverse compressive strength Yc"),
    "S12": ("stress", "MPa", "Schubfestigkeit (S₁₂)", "In-plane shear strength S12"),
    "phi_f": ("number", "1", "Faservolumengehalt", "Fibre volume fraction"),
}
# Felder der Zugversuch-Zeilen -> (Eigenschaft, Einheit, Schlüssel in wertart)
LEGACY = {"E": ("E_GPa", "GPa", None), "Rp": ("Rp02_MPa", "MPa", "Rp"), "Rm": ("Rm_MPa", "MPa", "Rm"),
          "A": ("A_pct", "%", None)}
CLASSES = {"metall": ("Metalle und Legierungen", "Metals and alloys"), "polymer": ("Polymere", "Polymers"),
           "keramik": ("Keramik", "Ceramics"), "glas": ("Gläser", "Glasses"), "verbund": ("Verbundwerkstoffe", "Composites"),
           "faser": ("Fasern", "Fibres"), "halbleiter": ("Halbleiter", "Semiconductors"),
           "naturstoff": ("Naturstoffe (Holz, Papier)", "Natural materials (wood, paper)")}
ART = {"typ": ("Typwert", "typical"), "min": ("Mindestwert", "minimum"), "max": ("Höchstwert", "maximum"),
       "mitte": ("Mitte der Spanne", "middle of range"), "unklar": ("Art unklar", "kind unclear")}


class MatError(ValueError):
    pass


# ----------------------------------------------------------------------------- Laden
def _key(s: str) -> str:
    """Vergleichsschlüssel: Gross/klein, Umlaute, Leerzeichen und Bindestriche egal ("en aw 6061 t6" = "EN AW-6061-T6")."""
    s = unicodedata.normalize("NFKC", str(s)).casefold().replace("ß", "ss")
    s = s.replace("gamma", "γ").replace("alpha", "α")
    return re.sub(r"[\s\-_.,/()]+", "", s)


@lru_cache(maxsize=None)
def _db() -> dict:
    if not PATH.exists():
        raise MatError("Werkstoffdatenbank fehlt (labcalc/data/materials.json)")
    db = json.loads(PATH.read_text(encoding="utf-8"))
    rows = list(db.get("werkstoffe") or [])
    ids = {r["id"] for r in rows}
    for p in sorted((DATA / "optional").glob("materials_*.json")) if (DATA / "optional").is_dir() else []:
        try:
            extra = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for r in extra.get("werkstoffe") or []:
            if r.get("id") and r["id"] not in ids:
                rows.append({**r, "_teil": p.stem})
                ids.add(r["id"])
    index: dict[str, list[dict]] = {}
    for r in rows:
        for n in [r["id"], r["name"], r.get("name_en"), *(r.get("aliase") or [])]:
            if n:
                lst = index.setdefault(_key(n), [])
                if r not in lst:
                    lst.append(r)
    return {"rows": rows, "index": index, "diffusion": db.get("diffusion") or [], "hinweis": db.get("_hinweis", "")}


@lru_cache(maxsize=None)
def _ranges() -> dict:
    """Spannen je Werkstoff und Eigenschaft (``data/ranges.json``); fehlende oder kaputte Datei -> leer."""
    p = DATA / "ranges.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (OSError, ValueError):
        d = {}
    return d if isinstance(d, dict) else {}


def reload() -> None:
    _db.cache_clear()
    _ranges.cache_clear()


def materials(klasse: str | None = None) -> list[dict]:
    rows = _db()["rows"]
    return [r for r in rows if not klasse or r.get("klasse") == klasse]


def zugversuch_rows() -> list[dict]:
    """Die Vergleichswerkstoffe des Zugversuchs in ihrer Reihenfolge (Felder wie bisher in alloys.json)."""
    return [r for r in _db()["rows"] if r.get("zugversuch")]


def find(name) -> dict:
    """Werkstoff nach id, Name, englischem Namen oder Alias; sonst eindeutiger Teiltreffer."""
    if isinstance(name, dict):
        return name
    k = _key(name)
    if not k:
        raise MatError("Werkstoffname fehlt")
    hit = _db()["index"].get(k)
    if hit and len(hit) == 1:
        return hit[0]
    if hit:
        raise MatError(f"„{name}“ ist mehrdeutig: " + ", ".join(r["name"] for r in hit[:8]))
    part = [r for key, lst in _db()["index"].items() if k in key for r in lst]
    part = list({id(r): r for r in part}.values())
    if len(part) == 1:
        return part[0]
    if part:
        raise MatError(f"„{name}“ ist mehrdeutig: " + ", ".join(r["name"] for r in part[:8])
                       + (" …" if len(part) > 8 else ""))
    raise MatError(f"Werkstoff „{name}“ nicht in der Werkstoffdatenbank")


# ----------------------------------------------------------------------------- Werte
def _element(sym: str) -> dict:
    from . import chem
    return ((chem._json("elements.json") or {}).get("elements") or {}).get(sym) or {}


def _legacy_source(r: dict) -> dict:
    return {"type": "misc", "title": r.get("quelle") or "", "url": r.get("url") or "", "year": str(r.get("jahr") or ""),
            "accessed": r.get("abgerufen") or "", "note": r.get("basis") or ""}


def _source(r: dict, q) -> tuple[str | None, dict]:
    """(Quellenschlüssel oder None, Quellendatensatz)."""
    from . import sources as S
    if isinstance(q, dict):
        return None, q
    if q and q in S.REFS:
        return q, S.ref(q)
    if q:
        return None, {"type": "misc", "title": str(q)}
    return None, {"type": "misc", "title": "ohne Quellenangabe"}


def props_of(name) -> list[str]:
    """Eigenschaften, für die ein Wert hinterlegt ist (Reihenfolge wie PROPS)."""
    r = find(name)
    have = set((r.get("werte") or {}).keys())
    for p, (f, _, _) in LEGACY.items():
        if r.get(f) is not None:
            have.add(p)
    if r.get("element"):
        el = _element(r["element"])
        if el.get("density_g_cm3") is not None:
            have.add("rho")
        if el.get("melting_point_K") is not None:
            have.add("Tm")
    return [p for p in PROPS if p in have] + sorted(have - set(PROPS))


def ranges_meta() -> dict:
    """Erläuterung der Spannen in ``data/ranges.json``: {"format", "de", "en"}."""
    d = _ranges()
    return {"format": d.get("_format", ""), "de": d.get("_hinweis", ""), "en": d.get("_hinweis_en", "")}


def _range_source(q) -> tuple[str | None, dict | None]:
    """(Schlüssel, Quellendatensatz) einer Spanne: Eintrag in ranges.json "quellen" oder labcalc-Quellenschlüssel."""
    from . import sources as S
    if not q:
        return None, None
    rec = (_ranges().get("quellen") or {}).get(q)
    if isinstance(rec, dict):
        return q, dict(rec)
    if q in S.REFS:
        return q, S.ref(q)
    return q, {"type": "misc", "title": str(q)}


def range_of(name, prop: str) -> dict | None:
    """Spanne aus ``data/ranges.json`` (auch ohne gespeicherten Einzelwert) oder None:
    {"material", "prop", "min_si", "max_si", "min", "max", "u", "range_key", "range_source", "range_art", "note"}."""
    r = find(name)
    b = ((_ranges().get("bereiche") or {}).get(r["id"]) or {}).get(prop)
    if not isinstance(b, dict) or b.get("min") is None or b.get("max") is None or prop not in PROPS:
        return None
    u = b.get("u") or PROPS[prop][1]
    key, rec = _range_source(b.get("q"))
    return {"material": r, "prop": prop, "min_si": float(U.to_si(float(b["min"]), u)),
            "max_si": float(U.to_si(float(b["max"]), u)), "min": b["min"], "max": b["max"], "u": u,
            "range_key": key, "range_source": rec, "range_art": b.get("art", ""), "note": b.get("note", "")}


def value(name, prop: str) -> dict:
    """Kennwert mit Herkunft: {"material", "prop", "si", "min_si", "max_si", "v", "u", "art", "key", "source",
    "nicht_geprueft", "kind", "range_key", "range_source", "range_art", "range_note", "range_own"}. Bei Text
    (Kristallstruktur) steht der Text in "text" und "si" ist None.

    Trägt der Wert selbst keine vollständige Spanne (min und max), kommt sie aus ``data/ranges.json`` mit deren
    eigener Quelle ("range_own" False); sonst bleibt die eigene Spanne mit der Quelle des Werts ("range_own" True)."""
    v = _value(name, prop)
    if v.get("si") is None:
        return v
    if v.get("min_si") is not None and v.get("max_si") is not None:
        v.update(range_key=v.get("key"), range_source=v.get("source"), range_art=v.get("art", ""), range_note="",
                 range_own=True)
        return v
    rg = range_of(v["material"], v["prop"])
    if rg is None:
        v.update(range_key=None, range_source=None, range_art="", range_note="", range_own=False)
    else:
        v.update(min_si=rg["min_si"], max_si=rg["max_si"], range_key=rg["range_key"], range_source=rg["range_source"],
                 range_art=rg["range_art"], range_note=rg["note"], range_own=False)
    return v


def _value(name, prop: str) -> dict:
    r = find(name)
    if prop not in PROPS:
        alias = {"density": "rho", "E_mod": "E", "poisson": "nu", "Re": "Rp", "Rp02": "Rp", "Tg_": "Tg", "k": "lambda",
                 "lambda_w": "lambda", "c_p": "cp", "alpha_T": "alpha", "K_Ic": "KIc", "KIC": "KIc"}
        if prop in alias:
            prop = alias[prop]
        else:
            raise MatError(f"Unbekannte Eigenschaft „{prop}“; bekannt: " + ", ".join(PROPS))
    kind, unit, _, _ = PROPS[prop]
    w = (r.get("werte") or {}).get(prop)
    ng = r.get("nicht_geprueft") or (r.get("werte_hinweis") if w is not None else "") or ""
    if w is not None:
        key, rec = _source(r, w.get("q") or r.get("q"))
        if kind == "text":
            return {"material": r, "prop": prop, "text": str(w["v"]), "si": None, "key": key, "source": rec,
                    "nicht_geprueft": ng, "kind": kind, "art": w.get("art", "")}
        u = w.get("u") or unit
        conv = lambda x: None if x is None else float(U.to_si(float(x), u))
        return {"material": r, "prop": prop, "si": conv(w["v"]), "min_si": conv(w.get("min")), "max_si": conv(w.get("max")),
                "v": w["v"], "u": u, "art": w.get("art", "typ"), "key": key, "source": rec, "nicht_geprueft": ng,
                "kind": kind, "T": w.get("T", "")}
    if prop in LEGACY and r.get(LEGACY[prop][0]) is not None:
        field, u, wa = LEGACY[prop]
        art = ((r.get("wertart") or {}).get(wa) if wa else "") or ""
        lo, hi = (r.get("Rm_min"), r.get("Rm_max")) if prop == "Rm" else (None, None)
        conv = lambda x: None if x is None else float(U.to_si(float(x), u))
        return {"material": r, "prop": prop, "si": conv(r[field]), "min_si": conv(lo), "max_si": conv(hi), "v": r[field],
                "u": u, "art": art, "key": None, "source": _legacy_source(r), "nicht_geprueft": r.get("nicht_geprueft") or "",
                "kind": kind, "T": ""}
    if r.get("element") and prop in ("rho", "Tm"):
        el = _element(r["element"])
        f, u = ("density_g_cm3", "g/cm^3") if prop == "rho" else ("melting_point_K", "K")
        if el.get(f) is not None:
            key, rec = _source(r, "pubchem_pt")
            return {"material": r, "prop": prop, "si": float(U.to_si(float(el[f]), u)), "min_si": None, "max_si": None,
                    "v": el[f], "u": u, "art": "typ", "key": key, "source": rec, "nicht_geprueft": "", "kind": kind, "T": ""}
    have = ", ".join(props_of(r)) or "keine"
    raise MatError(f"Für {r['name']} ist kein Wert „{prop}“ hinterlegt (vorhanden: {have})")


def get(name, prop: str) -> float:
    """Kennwert in SI-Einheiten (z. B. E in Pa, Tm in K, alpha in 1/K)."""
    v = value(name, prop)
    if v["si"] is None:
        raise MatError(f"„{prop}“ von {v['material']['name']} ist ein Text: {v.get('text', '')}")
    return v["si"]


def text(name, prop: str = "struktur") -> str:
    v = value(name, prop)
    return v.get("text") or ""


# ----------------------------------------------------------------------------- Suche, Zusammenfassung
def summary(r: dict, lang: str = "de") -> dict:
    """Kurzform für Auswahllisten (Rechner): id, Name, Klasse, Familie, Aliase, vorhandene Eigenschaften."""
    return {"id": r["id"], "name": r["name"] if lang == "de" else (r.get("name_en") or r["name"]),
            "klasse": r.get("klasse", ""), "familie": r.get("familie", ""), "aliase": r.get("aliase") or [],
            "props": props_of(r), "zugversuch": bool(r.get("zugversuch")), "teil": r.get("_teil", "")}


def search(q: str = "", klasse: str | None = None, prop: str | None = None, limit: int = 60, lang: str = "de") -> list[dict]:
    """Teiltreffer in Name, englischem Namen, Aliasen, Familie; optional nur Werkstoffe mit Eigenschaft ``prop``."""
    k = _key(q) if q else ""
    out = []
    for r in materials(klasse):
        if k:
            hay = [r["id"], r["name"], r.get("name_en") or "", r.get("familie") or "", *(r.get("aliase") or [])]
            if not any(k in _key(h) for h in hay if h):
                continue
        if prop and prop not in props_of(r):
            continue
        out.append(summary(r, lang))
        if len(out) >= limit:
            break
    return out


def card(name, lang: str = "de") -> dict:
    """Alle Werte eines Werkstoffs mit Anzeigeeinheit und Quelle (für die Detailansicht im Rechner)."""
    import labcite
    r = find(name)
    rows = []
    for p in props_of(r):
        try:
            v = value(r, p)
        except MatError:
            continue
        kind, unit, de, en = PROPS.get(p, ("", "", p, p))
        if v.get("si") is None:
            shown = v.get("text", "")
        else:
            shown = _fmt(v, unit)
        rows.append({"prop": p, "label": de if lang == "de" else en, "text": shown, "art": v.get("art", ""),
                     "source": labcite.short(v["source"], lang), "key": v["key"], "unit": unit,
                     "si": v.get("si"), "nicht_geprueft": bool(v.get("nicht_geprueft"))})
    ng = (r.get("nicht_geprueft_en") if lang == "en" else None) or r.get("nicht_geprueft") or r.get("werte_hinweis") or ""
    return {**summary(r, lang), "werte": rows, "hinweis": r.get("hinweis", ""), "nicht_geprueft": ng}


def _fmt(v: dict, unit: str) -> str:
    def f(x):
        y = U.from_si(x, unit) if unit != "°C" else x - 273.15
        return f"{y:.4g}".replace("e+0", "e").replace("e-0", "e-")
    shown_u = {"g/cm^3": "g/cm³", "µm/(m*K)": "10⁻⁶/K", "W/(m*K)": "W/(m·K)", "J/(kg*K)": "J/(kg·K)",
               "µOhm*cm": "µΩ·cm", "MPa*m^0.5": "MPa·√m", "1": ""}.get(unit, unit)
    if v.get("min_si") is not None and v.get("max_si") is not None and v.get("range_own", True):
        s = f"{f(v['min_si'])} … {f(v['max_si'])}"
    else:
        s = f(v["si"])
    return (s + (" " + shown_u if shown_u else "")).strip()


# ----------------------------------------------------------------------------- optionaler Teil: Materials Project
# Formel -> Klasse; abgefragt wird je Formel die stabile Phase (auf der konvexen Hülle). tools/fetch_optional_data.py mp
MP_FORMULAS = {
    "Fe": "metall", "Cu": "metall", "Al": "metall", "Ni": "metall", "Ti": "metall", "Mg": "metall", "Zn": "metall",
    "Cr": "metall", "Co": "metall", "Mo": "metall", "W": "metall", "Ag": "metall", "Au": "metall", "Pt": "metall",
    "Pb": "metall", "Sn": "metall", "V": "metall", "Nb": "metall", "Ta": "metall", "Zr": "metall",
    "Si": "halbleiter", "Ge": "halbleiter", "GaAs": "halbleiter", "GaN": "halbleiter", "InP": "halbleiter",
    "Al2O3": "keramik", "SiC": "keramik", "Si3N4": "keramik", "ZrO2": "keramik", "MgO": "keramik", "TiO2": "keramik",
    "AlN": "keramik", "BN": "keramik", "WC": "keramik", "TiC": "keramik", "TiN": "keramik", "SiO2": "keramik",
    "C": "keramik",
}
MP_FIELDS = ("material_id", "formula_pretty", "density", "band_gap", "bulk_modulus", "shear_modulus", "symmetry",
             "energy_above_hull", "is_stable", "theoretical")
MP_NOTE_DE = ("berechnet (DFT, Materials Project), nicht gemessen: Bandlücken aus GGA sind meist deutlich zu klein, "
              "Dichten und Moduln weichen typischerweise einige Prozent vom Experiment ab; stabile Phase bei 0 K")
MP_NOTE_EN = ("computed (DFT, Materials Project), not measured: GGA band gaps are usually much too small, densities and "
              "moduli typically differ by a few per cent from experiment; phase stable at 0 K")


def _modulus(m) -> float | None:
    if isinstance(m, dict):
        for k in ("vrh", "VRH", "k_vrh", "g_vrh"):
            if isinstance(m.get(k), (int, float)):
                return float(m[k])
    return float(m) if isinstance(m, (int, float)) else None


def mp_rows(docs_by_formula: dict, accessed: str) -> list[dict]:
    """Einträge für data/optional/materials_mp.json aus den Antworten der Materials Project API (je Formel die Liste
    ``data`` des Endpunkts /materials/summary/). Je Formel die stabile Phase mit der niedrigsten Energie über der Hülle."""
    rows = []
    for formula, docs in docs_by_formula.items():
        docs = [d for d in (docs or []) if isinstance(d, dict) and d.get("material_id")]
        if not docs:
            continue
        stable = [d for d in docs if d.get("is_stable")] or docs
        d = min(stable, key=lambda x: x.get("energy_above_hull") if isinstance(x.get("energy_above_hull"), (int, float)) else 9e9)
        mid = str(d["material_id"])
        sym = d.get("symmetry") or {}
        phase = " ".join(str(x) for x in (sym.get("symbol"), sym.get("crystal_system")) if x)
        werte = {}
        if isinstance(d.get("density"), (int, float)):
            werte["rho"] = {"v": round(float(d["density"]), 4), "u": "g/cm^3", "q": "jain2013"}
        k, g = _modulus(d.get("bulk_modulus")), _modulus(d.get("shear_modulus"))
        if k is not None and k > 0:
            werte["K"] = {"v": round(k, 1), "u": "GPa", "q": "dejong2015"}
        if g is not None and g > 0:
            werte["G"] = {"v": round(g, 1), "u": "GPa", "q": "dejong2015"}
        if k and g and k > 0 and g > 0:       # isotrope Näherung aus K und G (Voigt-Reuss-Hill)
            werte["E"] = {"v": round(9 * k * g / (3 * k + g), 1), "u": "GPa", "q": "dejong2015", "art": "typ"}
            werte["nu"] = {"v": round((3 * k - 2 * g) / (2 * (3 * k + g)), 3), "u": "1", "q": "dejong2015"}
        if isinstance(d.get("band_gap"), (int, float)) and MP_FORMULAS.get(formula) != "metall":
            werte["Eg"] = {"v": round(float(d["band_gap"]), 3), "u": "eV", "q": "jain2013"}
        if phase:
            werte["struktur"] = {"v": phase, "q": "jain2013"}
        if not werte:
            continue
        pretty = d.get("formula_pretty") or formula
        rows.append({"id": mid, "name": f"{pretty} (berechnet, {mid})", "name_en": f"{pretty} (computed, {mid})",
                     "klasse": MP_FORMULAS.get(formula, "keramik"), "familie": "Materials Project (DFT)",
                     "aliase": [mid, f"{pretty} MP", f"{pretty} DFT"], "werte": werte,
                     "nicht_geprueft": MP_NOTE_DE, "nicht_geprueft_en": MP_NOTE_EN,
                     "hinweis": f"https://next-gen.materialsproject.org/materials/{mid}, abgerufen {accessed}; "
                                f"Lizenz CC BY 4.0" + ("; E und ν isotrop aus K und G" if "E" in werte else "")
                                + ("; theoretisch, nicht synthetisiert" if d.get("theoretical") else "")})
    return rows


# ----------------------------------------------------------------------------- Diffusion
def diffusion(species: str, host: str) -> dict:
    """Diffusionsdaten D0 (m²/s) und Q (J/mol) für Teilchen in Wirtsgitter, z. B. ("C", "γ-Fe")."""
    ks, kh = _key(species), _key(host)
    for d in _db()["diffusion"]:
        w = d["wirt"]
        if _key(d["teilchen"]) == ks and kh in (_key(w), _key("-".join(reversed(w.split("-"))))):   # γ-Fe = Fe-gamma
            return {**d, "D0": float(d["D0_m2_s"]), "Q": float(d["Q_kJ_mol"]) * 1000.0}
    pairs = ", ".join(f"{d['teilchen']} in {d['wirt']}" for d in _db()["diffusion"])
    raise MatError(f"Keine Diffusionsdaten für {species} in {host}; vorhanden: {pairs}")


def D_diff(species: str, host: str, T: float) -> float:
    """Diffusionskoeffizient D = D0·exp(−Q/(R·T)) in m²/s; T in K."""
    from .units import CONSTANTS
    d = diffusion(species, host)
    R = CONSTANTS["Rgas"][0]
    if T <= 0:
        raise MatError("Temperatur muss positiv sein (K)")
    return d["D0"] * math.exp(-d["Q"] / (float(R) * T))


# ----------------------------------------------------------------------------- Prüfung
def validate() -> list[str]:
    """Formale Prüfung der Datenbank: Pflichtfelder, eindeutige ids, Einheit passt zur Grössenart, Quelle vorhanden,
    min ≤ v ≤ max."""
    from . import sources as S
    bad: list[str] = []
    seen: set[str] = set()
    for r in _db()["rows"]:
        rid = r.get("id") or "?"
        for f in ("id", "name", "klasse"):
            if not r.get(f):
                bad.append(f"{rid}: Feld {f} fehlt")
        if rid in seen:
            bad.append(f"{rid}: id doppelt")
        seen.add(rid)
        if r.get("klasse") and r["klasse"] not in CLASSES:
            bad.append(f"{rid}: unbekannte Klasse {r['klasse']}")
        for p, w in (r.get("werte") or {}).items():
            if p not in PROPS:
                bad.append(f"{rid}: unbekannte Eigenschaft {p}")
                continue
            q = w.get("q") or r.get("q")
            if not q:
                bad.append(f"{rid}.{p}: Quelle fehlt")
            elif isinstance(q, str) and re.fullmatch(r"[a-z0-9_]+", q) and q not in S.REFS:
                bad.append(f"{rid}.{p}: Quellenschlüssel {q} unbekannt")
            kind = PROPS[p][0]
            if kind == "text":
                continue
            u = w.get("u") or PROPS[p][1]
            try:
                _, dims, _ = U.parse_unit(u)
                if not U.deq(dims, U.kind_dims(kind)):
                    bad.append(f"{rid}.{p}: Einheit {u} passt nicht zu {kind}")
            except Exception as e:                              # noqa: BLE001 – jede Einheitenfehlermeldung zählt
                bad.append(f"{rid}.{p}: Einheit {u}: {e}")
            if w.get("art") == "mitte" and not (w.get("min") is not None and w.get("max") is not None):
                bad.append(f"{rid}.{p}: art mitte ohne min/max")
            if w.get("min") is not None and w.get("max") is not None and not (w["min"] <= w["v"] <= w["max"]):
                bad.append(f"{rid}.{p}: v ausserhalb min..max")
        if r.get("zugversuch"):
            for f in ("Rm_MPa", "A_pct", "E_GPa", "quelle"):
                if r.get(f) in (None, ""):
                    bad.append(f"{rid}: Zugversuch-Feld {f} fehlt")
    for d in _db()["diffusion"]:
        if not (d.get("D0_m2_s", 0) > 0 and d.get("Q_kJ_mol", 0) > 0 and d.get("q")):
            bad.append(f"Diffusion {d.get('teilchen')} in {d.get('wirt')}: unvollständig")
    return bad


# ----------------------------------------------------------------------------- Rechner-Funktionen
# Kurzformen: E_mat("Cu") = mat("Cu", "E")
SHORTCUTS = {"rho_mat": "rho", "E_mat": "E", "G_mat": "G", "nu_mat": "nu", "Rp_mat": "Rp", "Rm_mat": "Rm",
             "A_mat": "A", "KIc_mat": "KIc", "Tm_mat": "Tm", "Tg_mat": "Tg", "alpha_mat": "alpha", "lambda_mat": "lambda",
             "cp_mat": "cp", "rhoel_mat": "rho_el", "Eg_mat": "Eg", "a_lat": "a", "c_lat": "c"}


def _dims_of(prop) -> tuple | None:
    if not isinstance(prop, str) or prop not in PROPS or PROPS[prop][0] == "text":
        return None
    return U.kind_dims(PROPS[prop][0])


def calc_names(src: str) -> list[tuple[str, str | None]]:
    """(Werkstoff, Eigenschaft) aller Werkstoff-Aufrufe in einer Rechenzeile – für die Quellenangabe im Bericht."""
    out = []
    for fn, a, b in re.findall(r"\b(mat|\w+_mat|a_lat|c_lat)\(\s*\"([^\"]+)\"(?:\s*,\s*\"([^\"]+)\")?", src or ""):
        if fn == "mat":
            out.append((a, b or None))
        elif fn in SHORTCUTS:
            out.append((a, SHORTCUTS[fn]))
    return out


def cite_records(src: str) -> list[dict]:
    """Quellendatensätze der in einer Rechenzeile benutzten Werkstoffwerte (doppelte entfernt)."""
    recs, seen = [], set()
    for name, prop in calc_names(src):
        try:
            v = value(name, prop) if prop else None
        except MatError:
            continue
        if v is None:
            continue
        k = v["key"] or json.dumps(v["source"], sort_keys=True, ensure_ascii=False)
        if k not in seen:
            seen.add(k)
            recs.append({"key": v["key"], "source": v["source"]})
    for sp, host in re.findall(r"\bD_diff\(\s*\"([^\"]+)\"\s*,\s*\"([^\"]+)\"", src or ""):
        if "callister" not in seen:
            seen.add("callister")
            from . import sources as S
            recs.append({"key": "callister", "source": S.ref("callister")})
    return recs


def register_calc_functions():
    from . import expr as E

    def _s(x, what):
        if not isinstance(x, str):
            raise MatError(f"{what}: Name in Anführungszeichen erwartet")
        return x

    def mat(ctx, name, prop):
        return get(_s(name, "mat"), _s(prop, "mat"))

    E.register_string_function("mat", mat, 2, 2, lambda name=None, prop=None: _dims_of(prop),
                               'mat("Cu", "E") – Werkstoffkennwert in SI aus der Werkstoffdatenbank '
                               '(Eigenschaften: ' + ", ".join(p for p in PROPS if PROPS[p][0] != "text") + ")",
                               group="Werkstoffe")
    example = {"Rp": "S235JR", "Rm": "S235JR", "A": "S235JR", "KIc": "Al2O3", "Tg": "PC", "Eg": "Si", "c": "Ti",
               "rho_el": "Cu", "K": "Cu"}
    for fn, prop in SHORTCUTS.items():
        _, unit, de, _ = PROPS[prop]
        E.register_string_function(fn, (lambda p, f: lambda ctx, name: get(_s(name, f), p))(prop, fn), 1, 1,
                                   U.kind_dims(PROPS[prop][0]),
                                   f'{fn}("{example.get(prop, "Cu")}") – {de} (Werkstoffdatenbank)', group="Werkstoffe")
    E.register_string_function("D_diff", lambda ctx, sp, host, T: D_diff(_s(sp, "D_diff"), _s(host, "D_diff"), float(T)),
                               3, 3, U.kind_dims("diffusivity"),
                               'D_diff("C", "γ-Fe", T) – Diffusionskoeffizient D0·exp(−Q/RT) (Callister Tab. 5.2)',
                               group="Werkstoffe")
    E.register_string_function("Q_diff", lambda ctx, sp, host: diffusion(_s(sp, "Q_diff"), _s(host, "Q_diff"))["Q"], 2, 2,
                               U.kind_dims("molar_energy"), 'Q_diff("C", "γ-Fe") – Aktivierungsenergie der Diffusion',
                               group="Werkstoffe")
    E.register_string_function("D0_diff", lambda ctx, sp, host: diffusion(_s(sp, "D0_diff"), _s(host, "D0_diff"))["D0"], 2, 2,
                               U.kind_dims("diffusivity"), 'D0_diff("C", "γ-Fe") – Vorfaktor D0 der Diffusion',
                               group="Werkstoffe")
