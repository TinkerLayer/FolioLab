"""Stoffsammlung und Nachschlagewerte (geteilt von Elementrechner und Rechner).

Daten (labcalc/data, gebaut mit modules/elementrechner/tools/build_data.py):
  molecules.json   Sammlung aus PubChem (Strukturen, Namen, CAS) mit deutschen Namen aus Wikidata; Schlüssel InChIKey
  physprops.json   experimentelle Eigenschaften (PubChem PUG View, nur Quellen mit offenen Bedingungen)
  pka.json         IUPAC Digitized pKa Dataset (CC BY-NC 4.0)
  stability.json   NIST SRD 46 (Protonierungs-, Komplexbildungs- und Löslichkeitskonstanten)

Jeder Wert kommt mit Quelle, Temperatur und Medium. Widersprechen sich Werte, werden alle geliefert; ``choose`` wählt
nach einer festen, dokumentierten Regel einen Vorschlag, den die Oberfläche durch die Wahl des Nutzers ersetzen kann.
Eigene Stoffe werden über ``set_user_store`` eingehängt (Elementrechner: eigene_stoffe.json).
"""
from __future__ import annotations

import math
import re
import threading
import unicodedata
from functools import lru_cache

from . import chem as C

PKW_25 = 13.995          # Bandura & Lvov 2006, 25 °C, 0,1 MPa
PKW_SOURCE = "bandura2006"

_USER = [None]           # fn() -> {key: record}


def set_user_store(fn):
    _USER[0] = fn
    _index_build.cache_clear()


def _user() -> dict:
    try:
        return (_USER[0] or (lambda: {}))() or {}
    except Exception:  # noqa: BLE001 - eigene Daten dürfen die Sammlung nie blockieren
        return {}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower().replace("’", "'").replace("–", "-")
    return re.sub(r"\s+", " ", s).strip()


def collection() -> dict:
    return (C._json("molecules.json") or {"molecules": {}, "classes": []})


def molecules() -> dict:
    return {**collection().get("molecules", {}), **_user()}


_TL = threading.local()            # Rekursionssperre je Thread
_LOCK = threading.RLock()          # Server sind mehrfädig: andere Threads warten, bis der Index fertig ist


def _index():
    # Während des Aufbaus darf parse_species den Namens-Hook nicht erneut auslösen (Rekursion). Die Sperre gilt nur
    # im bauenden Thread; andere Threads warten am Lock, statt einen leeren Index zu sehen.
    if getattr(_TL, "building", False):
        return {}, {}, {}
    with _LOCK:
        _TL.building = True
        try:
            return _index_build()
        finally:
            _TL.building = False


@lru_cache(maxsize=1)
def _index_build():
    by_name, by_formula, by_cas = {}, {}, {}
    for key, m in molecules().items():
        for n in _names(m):
            by_name.setdefault(norm(n), key)
        if m.get("cas"):
            by_cas.setdefault(m["cas"], key)
        # Gleichungsformel ergibt die Hill-Formel selbst; PubChems Hill-Formel nur ohne eigene Formel
        # (PubChem lässt Isotope weg: D2O stünde sonst unter H2O)
        f = m.get("formula") or m.get("hill")
        if f:
            lst = by_formula.setdefault(_fkey(f), [])
            if key not in lst:
                lst.append(key)
    return by_name, by_formula, by_cas


def _names(m: dict) -> list[str]:
    return [n for n in [m.get("en"), m.get("de"), m.get("title"), m.get("iupac"), m.get("name")] +
            m.get("alias_en", []) + m.get("syn_de", []) + m.get("syn", []) if n]


def _fkey(f: str) -> str:
    try:
        return C.hill_formula(f)
    except C.ChemError:
        return norm(f)


def summary(key: str, m: dict | None = None) -> dict:
    m = m or molecules().get(key) or {}
    cls = collection().get("classes", [])
    return {"key": key, "en": m.get("en") or m.get("name"), "de": m.get("de"), "formula": m.get("formula"),
            "cas": m.get("cas"), "smiles": m.get("smiles"), "cid": m.get("cid"), "kind": m.get("kind"),
            "own": bool(m.get("own")), "classes": [cls[i] for i in m.get("cls", []) if i < len(cls)] + m.get("classes", [])}


def get(key: str) -> dict | None:
    m = molecules().get(key)
    if m is None:
        return None
    out = dict(m, key=key, **{"classes": summary(key, m)["classes"]})
    for f, k in ((m.get("formula"), "M"), (m.get("repeat_unit"), "M_repeat_unit")):
        if f:
            try:
                out[k] = C.molar_mass(f)["M"]
            except C.ChemError:
                pass
    return out


def resolve(query: str) -> str | None:
    """Name, CAS, InChIKey oder eindeutige Formel -> Schlüssel."""
    q = (query or "").strip()
    if not q:
        return None
    mols = molecules()
    if q in mols:
        return q
    by_name, by_formula, by_cas = _index()
    if q in by_cas:
        return by_cas[q]
    k = by_name.get(norm(q))
    if k:
        return k
    try:
        hits = by_formula.get(C.hill_formula(q)) or []
    except C.ChemError:
        hits = []
    if hits:
        # Formel mehrdeutig (Isomere): erster Eintrag der Sammlung in Gleichungsschreibweise bevorzugt
        exact = [h for h in hits if (mols[h].get("formula") or "").replace(" ", "") == q.replace(" ", "")]
        return (exact or hits)[0]
    return None


def find(query: str, limit: int = 60, cls: str | None = None) -> list[dict]:
    """Suche nach Name (Anfang/Teil), Formel, CAS oder Stoffklasse; beste Treffer zuerst."""
    q = norm(query)
    mols = molecules()
    by_name, by_formula, by_cas = _index()
    scored = {}

    def add(k, s):
        if k in mols and s > scored.get(k, -1):
            scored[k] = s
    if q:
        if query.strip() in by_cas:
            add(by_cas[query.strip()], 100)
        if q in by_name:
            add(by_name[q], 95)
        try:
            for k in by_formula.get(C.hill_formula(query.strip()), []):
                add(k, 90)
        except C.ChemError:
            pass
    cl = collection().get("classes", [])
    for k, m in mols.items():
        mcls = [cl[i] for i in m.get("cls", []) if i < len(cl)] + m.get("classes", [])
        if cls and cls not in mcls:
            continue
        if not q:
            add(k, 1)
            continue
        best = 0
        for i, n in enumerate(_names(m)):
            nn = norm(n)
            if nn.startswith(q):
                best = max(best, 80 - min(i, 10) - min(len(nn) - len(q), 20) / 4)
            elif q in nn:
                best = max(best, 50 - min(i, 10))
        if any(q in norm(c) for c in mcls):
            best = max(best, 20)
        if best:
            add(k, best)
    keys = sorted(scored, key=lambda k: (-scored[k], (mols[k].get("en") or mols[k].get("name") or "").lower()))
    return [summary(k, mols[k]) for k in keys[:limit]]


def name_resolver(text: str) -> dict | None:
    """Hook für chem.parse_species: nur exakte Namen (DE/EN), nie Teiltreffer."""
    by_name = _index()[0]
    k = by_name.get(norm(text))
    if not k:
        return None
    m = molecules()[k]
    if not m.get("formula"):
        return None
    return {"formula": m["formula"], "name": m.get("de") or m.get("en") or m.get("name"), "key": k}


def install():
    C.set_name_resolver(name_resolver)


# ----------------------------------------------------------------------------- Werte
def _val(value, *, kind, source, T=None, I=None, medium="Wasser", label="", note="", ref="", quality="", unit="",
         extra=None) -> dict:
    d = {"value": value, "kind": kind, "source": source, "T_C": T, "I": I, "medium": medium, "label": label,
         "note": note, "ref": ref, "quality": quality, "unit": unit}
    if extra:
        d.update(extra)
    return d


def _fT(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


# Protonierungsschritt [HjL]/[H][Hj-1L]; SRD 46 schreibt beide Reihenfolgen ([HL]/[L][H] und [H₂L]/[H][HL])
_ACID_RE = re.compile(r"^\[(H(?:[₀-₉]+)?)?L\]/(?:\[H\]\[(H(?:[₀-₉]+)?)?L\]|\[(H(?:[₀-₉]+)?)?L\]\[H\])$")
_SUBD = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")


def _hcount(s: str | None) -> int:
    if not s:
        return 0
    return int(s[1:].translate(_SUBD) or 1)


def _fig_h(fig: str | None) -> int:
    m = re.match(r"^H(\d*)L", fig or "")
    return int(m.group(1) or 1) if m else 0


def _srd() -> dict:
    return C._json("stability.json") or {}


@lru_cache(maxsize=1)
def _srd_by_ligand() -> dict:
    out = {}
    for r in _srd().get("rows", []):
        out.setdefault(r[0], []).append(r)
    return out


@lru_cache(maxsize=1)
def _pka_by_cid() -> dict:
    out = {}
    for r in (C._json("pka.json") or {}).get("rows", []):
        out.setdefault(r[0], []).append(r)
    return out


def _ligands_for(key: str) -> list[str]:
    return [lid for lid, l in _srd().get("ligands", {}).items() if l.get("key") == key]


def _srd_ref(lid: str, mid: str) -> str:
    d = _srd()
    lits = d.get("pair_lit", {}).get(f"{lid}:{mid}", [])
    return "; ".join(d["literature"][i] for i in lits[:3] if i in d.get("literature", {}))


def pka_values(query: str) -> dict:
    """Alle pKa-Werte eines Stoffs: NIST SRD 46 (Protonierungskonstanten), IUPAC-Datensatz, PubChem (offene Quellen).
    label „pKa1“ = erste Dissoziation der vollständig protonierten Form (für Basen: pKa der konjugierten Säure)."""
    key = resolve(query)
    out = []
    if not key:
        return {"key": None, "query": query, "values": []}
    d = _srd()
    for lid in _ligands_for(key):
        lig = d["ligands"][lid]
        n = _fig_h(lig.get("fig"))
        for r in _srd_by_ligand().get(lid, []):
            if r[3] != "K" or d["metals"].get(r[1], {}).get("formula") != "H":
                continue
            m = _ACID_RE.match(d["defs"].get(r[2], ""))
            if not m:
                continue
            j = _hcount(m.group(1))
            if j != _hcount(m.group(2) if m.group(2) is not None else m.group(3)) + 1:
                continue
            # Protonierungsschritt j: [HjL]/[H][Hj-1L]; pKa-Index von der protonierten Seite aus gezählt
            idx = n - j + 1 if n >= j else None
            acid = (f"H{j if j > 1 else ''}L").translate(str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉"))
            lab = f"pKa{idx}" if idx else f"pKa ({acid}⁺)"
            out.append(_val(r[6], kind="pKa", source="srd46", T=_fT(r[4]), I=_fT(r[5]), label=lab,
                            note=f"lg K für {d['defs'][r[2]]}" + (f"; {r[9]}" if r[9] else ""),
                            ref=_srd_ref(lid, r[1]), quality="kritisch ausgewählt",
                            extra={"u": r[7], "step": idx, "acid": acid}))
    pk = C._json("pka.json") or {}
    for cid in pk.get("by_key", {}).get(key, []):
        for r in _pka_by_cid().get(cid, []):
            typ = r[1]
            m = re.match(r"pKa(H)?(\d*)$", typ)
            idx = int(m.group(2) or 1) if m and not m.group(1) else None
            lab = typ if not m else (f"pKa{idx}" if idx else f"pKa (konj. Säure, {typ})")
            refs = pk.get("refs", {}).get(r[6] or "", {})
            out.append(_val(r[2], kind="pKa" if typ.startswith("pK") and not typ.startswith("pKb") else typ,
                            source="iupac_pka", T=r[3], label=lab, medium=("Wasser + " + r[8]) if r[8] else "Wasser",
                            note="; ".join(x for x in (r[9], f"Methode {r[5]}" if r[5] else "") if x),
                            ref=refs.get(r[7]) or "", quality=r[4] or "",
                            extra={"step": idx, "collection": r[7], "type": typ}))
    for v in (_user().get(key) or {}).get("values", {}).get("pka", []):
        out.append(_val(v["v"], kind="pKa", source="own", T=v.get("T"), label="pKa", note=v.get("txt", ""),
                        quality="eigener Wert", extra={"step": 1, "own_source": v.get("source")}))
    for v in (C._json("physprops.json") or {}).get("props", {}).get(key, {}).get("pka", []):
        if "v" in v:
            out.append(_val(v["v"], kind="pKa", source=v["src"], T=v.get("T"), label="pKa", note=v["txt"],
                            ref=v.get("ref", ""), extra={"step": None}))
    return {"key": key, "query": query, "values": out}


_Q_ORDER = {"eigener Wert": -1, "kritisch ausgewählt": 0, "Reliable": 1, "Approximate": 2, "": 3, "berechnet": 3.5,
            "Uncertain": 4, "Very uncertain": 5}


def choose(values: list[dict], T: float = 25.0) -> dict | None:
    """Vorschlag aus mehreren Werten: nahe der gewünschten Temperatur, Ionenstärke 0 bevorzugt, dann die Bewertung
    (SRD 46 kritisch ausgewählt vor IUPAC „Reliable“ vor „Approximate“ …), reines Wasser vor Cosolvens."""
    if not values:
        return None

    def rank(v):
        dT = abs((v.get("T_C") if v.get("T_C") is not None else T) - T) + (0.5 if v.get("T_C") is None else 0)
        I = v.get("I")
        return (dT > 2.5, v.get("medium") != "Wasser", 0 if not I else 1, _Q_ORDER.get(v.get("quality", ""), 3),
                dT, I or 0)
    return sorted(values, key=rank)[0]


def pka(query: str, step: int = 1, T: float = 25.0) -> dict:
    vals = [v for v in pka_values(query)["values"] if v.get("step") == step and v["kind"] == "pKa"]
    if not vals and step == 1:
        vals = [v for v in pka_values(query)["values"] if v["kind"] == "pKa" and v.get("step") is None]
    best = choose(vals, T)
    if not best:
        raise C.ChemError(f"kein pKa{step} für „{query}“ in den mitgelieferten Quellen")
    return best


def pkb(query: str, step: int = 1, T: float = 25.0) -> dict:
    """pKb = pKw − pKa der konjugierten Säure (25 °C, pKw nach Bandura & Lvov 2006); direkte pKb-Werte, falls vorhanden."""
    allv = pka_values(query)["values"]
    direct = [v for v in allv if v["kind"].startswith("pKb") and (v.get("type") in (f"pKb{step}", "pKb"))]
    if direct:
        return choose(direct, T)
    # Protonierungsschritt `step` der Base = höchster pKa-Index zuerst
    conj = [v for v in allv if v["kind"] == "pKa" and v.get("label", "").startswith("pKa (")]
    if not conj:
        steps = sorted({v["step"] for v in allv if v.get("step")}, reverse=True)
        if len(steps) >= step:
            conj = [v for v in allv if v.get("step") == steps[step - 1]]
    best = choose(conj, T)
    if not best:
        raise C.ChemError(f"kein pKb für „{query}“ (keine pKa-Werte der konjugierten Säure)")
    return dict(best, value=round(PKW_25 - best["value"], 4), kind="pKb", label=f"pKb{step}",
                note=f"pKw − pKa(konj. Säure) = {PKW_25} − {best['value']}; " + best.get("note", ""),
                derived_from=best, extra_source=PKW_SOURCE)


def ksp_values(query: str) -> dict:
    """Löslichkeitsprodukte (NIST SRD 46). query: Formel (AgCl, Ca(OH)2, CaC2O4·H2O) oder Name aus der Sammlung."""
    d = _srd()
    f = query
    key = None
    try:
        sp = C.parse_species(query)
    except C.ChemError:
        sp = None
    if sp is None or sp.name:
        key = resolve(query)
        f = (molecules().get(key) or {}).get("formula") if key else None
        if not f:
            return {"query": query, "values": []}
        sp = C.parse_species(f)
    water = 0
    counts = dict(sp.counts)
    if sp.parts:
        for fac, part in sp.parts:
            if part.replace(" ", "") == "H2O":
                water = int(fac)
        if water:
            counts["H"] = counts.get("H", 0) - 2 * water
            counts["O"] = counts.get("O", 0) - water
    hill = C._hill({k: int(v) for k, v in counts.items() if v})
    out = []
    for i, nw, plain in d.get("ksp", {}).get(hill, []):
        r = d["rows"][i]
        lig, met = d["ligands"][r[0]], d["metals"][r[1]]
        out.append(_val(r[6], kind="lgKsp", source="srd46", T=_fT(r[4]), I=_fT(r[5]),
                        label="lg Ksp" if plain else "lg K (s. Definition)",
                        note=f"{d['defs'][r[2]]}; {met['name']} + {lig['name']}" + (f"; {r[9]}" if r[9] else ""),
                        ref=_srd_ref(r[0], r[1]), quality="kritisch ausgewählt",
                        extra={"u": r[7], "water": nw, "plain": plain, "Ksp": 10 ** r[6] if plain else None,
                               "match_hydrate": nw == water}))
    calc = _ksp_calc(query, key, f)
    if calc:
        out.append(calc)
    return {"query": query, "key": key, "hill": hill, "water": water, "values": out}


INSOLUBLE_MOL_L = 0.01          # Lehrbuchgrenze „schwer löslich“: Löslichkeit unter etwa 0,01 mol/L (Harris 2016)


def molar_solubility(query: str, ions: list[int] | None = None) -> float | None:
    """Molare Löslichkeit s (mol/L, ideal, ohne Nebenreaktionen) aus dem bevorzugten Ksp: Ksp = Π (νᵢ s)^νᵢ.
    ions: Anzahl je Ionensorte (z. B. [1, 2] für CaF₂); ohne Angabe aus der Struktur, sonst 1:1. None ohne Ksp."""
    try:
        vals = [v for v in ksp_values(query)["values"] if v.get("plain") and v.get("match_hydrate", True)]
    except C.ChemError:
        return None
    if not vals:
        return None
    lg = vals[0]["value"]
    if ions is None:
        ions = [1, 1]
        k = resolve(query)
        smi = (molecules().get(k) or {}).get("smiles") if k else None
        if smi:
            from . import molgraph as G
            try:
                g = G.parse(smi)
                cnt = {}
                for fr in g.fragments():
                    sig = (tuple(sorted(g.el[i] for i in fr)), sum(g.q[i] for i in fr))
                    cnt[sig] = cnt.get(sig, 0) + 1
                if len(cnt) >= 2:
                    ions = list(cnt.values())
            except Exception:  # noqa: BLE001
                pass
    nu = sum(ions)
    lg_den = sum(n * math.log10(n) for n in ions)
    return 10 ** ((lg - lg_den) / nu)


def sparingly_soluble(query: str, ions: list[int] | None = None) -> bool:
    s = molar_solubility(query, ions)
    return s is not None and s < INSOLUBLE_MOL_L


def _ksp_calc(query: str, key: str | None, formula: str | None) -> dict | None:
    """lg Ksp aus den Freien Bildungsenthalpien (thermo), als „berechnet“ gekennzeichnet; schwächer als SRD 46."""
    from . import thermo as TH
    k = key or resolve(query)
    m = molecules().get(k) or {} if k else {}
    f = m.get("formula") or formula or query
    try:
        r = TH.ksp_from_dG(f, m.get("smiles"))
    except C.ChemError:
        return None
    if not r:
        return None
    src = TH.SRC_REF.get(r["sources"][0], "")
    return _val(round(r["value"], 2), kind="lgKsp", source=src, T=25.0, I=0.0,
                label="lg Ksp (berechnet aus ΔfG°)",
                note=f"{r['reaction']}; ΔrG° = {r['dG']:.2f}".replace(".", ",") + " kJ/mol, lg Ksp = −ΔrG°/(RT ln 10); Daten: "
                     + ", ".join(TH.SRC_NAME[s] for s in r["sources"]),
                quality="berechnet", extra={"u": None, "water": r["water"], "plain": True, "Ksp": 10 ** r["value"],
                                            "match_hydrate": True, "calc": True, "sources": [TH.SRC_REF[s] for s in r["sources"]]})


def ksp(query: str, T: float = 25.0) -> dict:
    res = ksp_values(query)
    vals = [v for v in res["values"] if v["plain"]]
    exact = [v for v in vals if v["match_hydrate"]]
    best = choose(exact or vals, T)
    if not best:
        raise C.ChemError(f"kein Löslichkeitsprodukt für „{query}“ in NIST SRD 46")
    return best


_ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8}


def _metal_ids(metal: str) -> list[str]:
    """Metallion als 'Cu2+', 'Cu^2+', 'Cu²⁺', 'Cu(II)' oder Formel mit Ladung ('UO2^2+')."""
    s = metal.strip().translate(str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻", "0123456789+-"))
    m = re.fullmatch(r"([A-Z][a-z]?)\^?(\d*)([+-])", s)          # einatomig: Ziffer vor dem Vorzeichen = Ladung
    r = re.fullmatch(r"([A-Z][a-z]?)\s*\(([IVX]+)\)", s)
    if m:
        f, q = m.group(1), int(m.group(2) or 1) * (1 if m.group(3) == "+" else -1)
    elif r and r.group(2) in _ROMAN:
        f, q = r.group(1), _ROMAN[r.group(2)]
    else:
        sp = C.parse_species(metal)
        f, q = "".join(k + (str(int(v)) if v != 1 else "") for k, v in sp.counts.items()), sp.charge
    return [mid for mid, x in _srd().get("metals", {}).items() if x["formula"] == f and x["charge"] == q]


def _ligand_ids(ligand: str) -> list[str]:
    d = _srd()
    key = resolve(ligand)
    ids = _ligands_for(key) if key else []
    if ids:
        return ids
    q = norm(ligand)
    ids = [lid for lid, l in d.get("ligands", {}).items() if norm(l["name"]).startswith(q)]
    if ids:
        return ids
    try:
        sp = C.parse_species(ligand)
        h = C._hill({k: int(v) for k, v in sp.counts.items()})
    except C.ChemError:
        return []
    out = []
    for lid, l in d.get("ligands", {}).items():
        if l.get("L") and l.get("Lq") == sp.charge:
            try:
                if C._hill({k: int(v) for k, v in C._formula_counts(l["L"]).items()}) == h:
                    out.append(lid)
            except C.ChemError:
                pass
    return out


def logk_values(metal: str, ligand: str) -> dict:
    """Stabilitätskonstanten (lg K, lg β) Metallion–Ligand aus NIST SRD 46, alle Definitionen."""
    d = _srd()
    mids, lids = set(_metal_ids(metal)), set(_ligand_ids(ligand))
    out = []
    for r in (x for lid in lids for x in _srd_by_ligand().get(lid, [])):
        if r[1] in mids and r[3] == "K":
            df = d["defs"].get(r[2], "")
            m = re.fullmatch(r"\[ML(?:([₀-₉]+))?\]/\[M\]\[L\](?:([⁰¹²³⁴⁵⁶⁷⁸⁹]+))?", df)
            n = int(m.group(1).translate(_SUBD)) if m and m.group(1) else (1 if m else None)
            out.append(_val(r[6], kind="lgK", source="srd46", T=_fT(r[4]), I=_fT(r[5]),
                            label=(f"lg β{n}" if n and n > 1 else "lg K1") if m else "lg K", note=df,
                            ref=_srd_ref(r[0], r[1]), quality="kritisch ausgewählt",
                            extra={"u": r[7], "n": n, "def": df, "ligand": d["ligands"][r[0]]["name"],
                                   "metal": d["metals"][r[1]]["name"]}))
    return {"metal": metal, "ligand": ligand, "values": out}


def logk(metal: str, ligand: str, n: int = 1, T: float = 25.0) -> dict:
    vals = [v for v in logk_values(metal, ligand)["values"] if v.get("n") == n]
    best = choose(vals, T)
    if not best:
        raise C.ChemError(f"keine Stabilitätskonstante lg β{n} für {metal} / {ligand} in NIST SRD 46")
    return best


PROPS = {"mp": ("Schmelzpunkt", "Melting point"), "bp": ("Siedepunkt", "Boiling point"),
         "density": ("Dichte", "Density"), "vp": ("Dampfdruck", "Vapour pressure"),
         "flash": ("Flammpunkt", "Flash point"), "autoign": ("Zündtemperatur", "Autoignition temperature"),
         "solubility": ("Löslichkeit", "Solubility"), "logp": ("lg Kow", "log Kow"), "nD": ("Brechzahl", "Refractive index"),
         "viscosity": ("Viskosität", "Viscosity"), "surftens": ("Oberflächenspannung", "Surface tension"),
         "henry": ("Henry-Konstante", "Henry constant"), "ip": ("Ionisierungsenergie", "Ionisation energy"),
         "dHvap": ("Verdampfungsenthalpie", "Enthalpy of vaporisation"), "dHc": ("Verbrennungsenthalpie", "Enthalpy of combustion"),
         "vapdens": ("Dampfdichte (Luft = 1)", "Vapour density (air = 1)"), "descr": ("Beschreibung", "Description"),
         "color": ("Farbe/Form", "Colour/form"), "odor": ("Geruch", "Odour"), "decomp": ("Zersetzung", "Decomposition"),
         "stability": ("Stabilität", "Stability")}


def properties(query: str) -> dict:
    key = resolve(query)
    if not key:
        return {"key": None, "props": {}}
    users = _user()
    own = (users.get(key) or {}).get("values", {})
    base = (C._json("physprops.json") or {}).get("props", {}).get(key, {})
    props = {k: list(v) for k, v in base.items()}
    for k, vals in own.items():
        props.setdefault(k, [])
        props[k] = [dict(v, own=True) for v in vals] + props[k]
    for rec in users.values():                     # ER-X04: importierte Werte, die einem Sammlungsstoff zugeordnet sind
        if rec.get("ref") == key and rec.get("ref") is not None:
            for k, vals in (rec.get("values") or {}).items():
                props[k] = [dict(v, own=True) for v in vals] + props.get(k, [])
    return {"key": key, "props": props, "sources": (C._json("physprops.json") or {}).get("sources", {})}


def prop(query: str, name: str, T: float = 25.0) -> dict:
    vals = [dict(v, T_C=v.get("T"), quality="eigener Wert" if v.get("own") else "", medium="Wasser")
            for v in properties(query)["props"].get(name, []) if "v" in v and not v.get("rel")]
    if not vals:
        raise C.ChemError(f"kein Wert „{PROPS.get(name, (name,))[0]}“ für „{query}“ in den mitgelieferten Quellen")
    own = [v for v in vals if v.get("own") and not v.get("est")]
    if own:
        return own[0]
    if any(not v.get("est") for v in vals):            # Schätzwerte (Moleküldesigner) nur ohne gemessenen Wert
        vals = [v for v in vals if not v.get("est")]
    else:
        return dict(vals[0], quality="Schätzwert")
    # Temperaturabhängige Größen: Werte nahe T zuerst; Dampfdruck ohne Temperaturangabe ist nicht verwendbar.
    # Danach HSDB (mit Primärquelle) vor ICSC und den Behördenlisten.
    order = {"hsdb": 0, "icsc": 1, "doepac": 2, "niosh": 3, "osha": 4}
    if name in T_DEPENDENT:
        if name == "vp":
            vals = [v for v in vals if v.get("T") is not None]
            if not vals:
                raise C.ChemError(f"kein Dampfdruck mit Temperaturangabe für „{query}“")
        def tkey(v):
            t = v.get("T")
            return 2 if t is None else (0 if abs(t - T) <= 5 else 1)
        vals.sort(key=lambda v: (tkey(v), order.get(v.get("src"), 9), not v.get("ref"),
                                 abs((v.get("T") if v.get("T") is not None else T) - T)))
    else:
        vals.sort(key=lambda v: (order.get(v.get("src"), 9), not v.get("ref")))
    return vals[0]


T_DEPENDENT = {"density", "vp", "viscosity", "surftens", "henry", "pka", "nD"}


# ----------------------------------------------------------------------------- Rechner-Funktionen
def _arg(x, fn):
    if not isinstance(x, str):
        raise C.ChemError(f'{fn}("Name oder Formel") – in Anführungszeichen')
    return x


def register_calc_functions():
    from . import expr as E
    from . import units as U
    D0 = U.D0
    E.register_string_function("pKa", lambda ctx, q, i=1: pka(_arg(q, "pKa"), int(i))["value"], 1, 2, D0,
                               'pKa("CH3COOH") – pKa (NIST SRD 46 / IUPAC-Datensatz); pKa("H3PO4", 2) zweite Stufe')
    E.register_string_function("pKb", lambda ctx, q, i=1: pkb(_arg(q, "pKb"), int(i))["value"], 1, 2, D0,
                               'pKb("NH3") – pKw − pKa der konjugierten Säure (25 °C)')
    E.register_string_function("Ksp", lambda ctx, q: 10 ** ksp(_arg(q, "Ksp"))["value"], 1, 1, D0,
                               'Ksp("AgCl") – Löslichkeitsprodukt (NIST SRD 46, Konzentrationen in mol/L)')
    E.register_string_function("pKsp", lambda ctx, q: -ksp(_arg(q, "pKsp"))["value"], 1, 1, D0,
                               'pKsp("AgCl") – −lg Ksp')
    E.register_string_function("lgK", lambda ctx, m, l, n=1: logk(_arg(m, "lgK"), _arg(l, "lgK"), int(n))["value"],
                               2, 3, D0, 'lgK("Cu2+", "NH3", 4) – lg β (NIST SRD 46)')
    tdim = U.kind_dims("temperature")
    E.register_string_function("Tm", lambda ctx, q: prop(_arg(q, "Tm"), "mp")["v"] + 273.15, 1, 1, tdim,
                               'Tm("Ethanol") – Schmelzpunkt in K (PubChem: HSDB/ICSC)')
    E.register_string_function("Tb", lambda ctx, q: prop(_arg(q, "Tb"), "bp")["v"] + 273.15, 1, 1, tdim,
                               'Tb("Ethanol") – Siedepunkt in K (PubChem: HSDB/ICSC)')
    E.register_string_function("rho", lambda ctx, q: prop(_arg(q, "rho"), "density")["v"] * 1000.0, 1, 1,
                               U.kind_dims("density"), 'rho("Ethanol") – Dichte in kg/m³ (PubChem: HSDB/ICSC)')
