"""Thermochemie bei 298,15 K aus Standardbildungsdaten (Hess): ΔrH°, ΔrS°, ΔrG°, K, Freiwilligkeit, T*, Wärme.

Daten: labcalc/data/thermo.json (CODATA Key Values, NBS-Tabellen, Burcat/ATcT; siehe tools/build_thermo.py) und
eigene Werte aus der Stoffdatenbank (Grössen dfH, dfG, S0, Cp mit Phase).

Auswahl je Stoff:
  1. Stoff bestimmen: aufgelöster Name bzw. Sammlungseintrag (InChIKey), sonst gleiche Schreibweise der Formel,
     sonst Summenformel (bei Isomeren wird das genannt).
  2. Phase: wie angegeben ((s) = cr); sonst Ionen (aq), Neutralstoffe in der bei 298,15 K und 1 bar stabilen Phase
     (kleinstes ΔfG° unter cr, l, g). Gelöste Neutralstoffe (aq): undissoziiert (NBS „ao“) vor vollständig
     dissoziiert („ai“).
  3. Quelle: eigener Wert > CODATA Key Values > NBS > Burcat; innerhalb einer Quelle die stabilste Modifikation
     (kleinstes ΔfG°, z. B. Graphit vor Diamant, Calcit vor Aragonit).

Bei anderer Temperatur gilt hier die Näherung ΔrH°, ΔrS° unabhängig von T (Ellingham); Cp(T) folgt später.
"""
from __future__ import annotations

import math
import re
from functools import lru_cache

from . import chem as C

T0 = 298.15
R = C.R_GAS                       # J/(mol K), CODATA 2022
P0 = 1e5                          # Pa, Standarddruck (IUPAC seit 1982)
C0 = 1000.0                       # mol/m³ = 1 mol/L
# Schätzwerte aus dem Moleküldesigner – nur, wenn keine Tabelle Daten hat: "estb" Benson (Domalski & Hearing 1993,
# ±4 kJ/mol) vor "est" Joback & Reid 1987
PRIO = {"own": 0, "codata": 1, "nbs": 2, "burcat": 3, "estb": 4, "est": 5}
SRC_NAME = {"own": "eigener Wert", "codata": "CODATA Key Values", "nbs": "NBS-Tabellen", "burcat": "Burcat/ATcT",
            "estb": "Schätzung (Benson)", "est": "Schätzung (Joback)"}
# Quellenschlüssel in labcalc.sources (Bericht, Tooltips)
SRC_REF = {"own": "", "codata": "cox1989", "nbs": "wagman1982", "burcat": "burcat2018", "estb": "domalski1993",
           "est": "joback1987"}
SRC_REFS = {"own": [], "codata": ["cox1989"], "nbs": ["wagman1982", "reed2020"], "burcat": ["burcat2018", "burcat2005"],
            "estb": ["domalski1993", "benson1969"], "est": ["joback1987", "joback_wiki"]}
PHASE_ALIAS = {"s": "cr", "cr": "cr", "l": "l", "g": "g", "aq": "aq", "am": "am"}


class ThermoError(C.ChemError):
    pass


@lru_cache(maxsize=1)
def data() -> dict:
    d = C._json("thermo.json") or {"species": [], "refS": {}}
    # Burcat/ATcT-Teil: nicht frei weiterverbreitbar, im öffentlichen Repository fehlend; tools/fetch_optional_data.py
    # legt ihn als optional/thermo_burcat.json ab (gleiches Format, nur "species").
    extra = C._json("optional/thermo_burcat.json")
    if extra and extra.get("species"):
        have = {entry_id(e) for e in d["species"]}
        d = {**d, "species": d["species"] + [e for e in extra["species"] if entry_id(e) not in have]}
    return d


@lru_cache(maxsize=1)
def _index() -> dict:
    idx = {}
    for i, e in enumerate(data()["species"]):
        idx.setdefault((e["hill"], e["q"]), []).append(i)
    return idx


def _hill(sp: C.Species) -> str:
    return C._hill({k: int(v) if v.denominator == 1 else float(v) for k, v in sp.counts.items()})


def _written(f: str) -> str:
    """Schreibweise ohne Ladung, Leerzeichen, Phase: 'C2H5OH', 'CH3COOH'."""
    f = C.Species.text_formula(f).replace(" ", "")
    return re.sub(r"\^?\d*[+-]+$", "", f)


def entry_id(e: dict) -> str:
    return "|".join(str(e.get(k) or "") for k in ("src", "f", "ph", "aqs", "poly"))


def _own_entries(sp: C.Species) -> list[dict]:
    """Eigene Werte (Stoffdatenbank, Grössen dfH/dfG/S0/Cp) zu Stoffen mit gleicher Summenformel und Ladung."""
    try:
        from . import substances as S
    except ImportError:
        return []
    out = []
    hill, q = _hill(sp), sp.charge
    for key, m in S._user().items():
        f = m.get("formula")
        if not f:
            continue
        try:
            osp = C.parse_species(f)
        except C.ChemError:
            continue
        if _hill(osp) != hill or osp.charge != q:
            continue
        vals = m.get("values") or {}
        by_ph = {}                                     # (Quelle, Phase) -> Werte; Schätzwerte getrennt von Messwerten
        for k, field in (("dfH", "H"), ("dfG", "G"), ("S0", "S"), ("Cp", "Cp")):
            for v in vals.get(k) or []:
                if v.get("v") is None:
                    continue
                ph = PHASE_ALIAS.get((v.get("phase") or "").strip(), "") or (osp.phase and PHASE_ALIAS.get(osp.phase)) or ""
                src = ("estb" if "Benson" in str(v.get("method") or "") else "est") if v.get("est") else "own"
                by_ph.setdefault((src, ph), {})[field] = float(v["v"])
        for (src, ph), vv in by_ph.items():
            e = {"src": src, "f": f, "ph": ph or "?", "hill": hill, "q": q, "key": key, "name": m.get("name") or m.get("de"),
                 "source": m.get("source")}
            e.update(vv)
            if "G" not in e and "H" in e and "S" in e:
                g = dfG_from(osp.counts, q, e["H"], e["S"])
                if g is not None:
                    e["G"], e["Gcalc"] = g, True
            if "S" not in e and "H" in e and "G" in e:
                s = S_from(osp.counts, q, e["H"], e["G"])
                if s is not None:
                    e["S"], e["Scalc"] = s, True
            out.append(e)
    return out


def S_from(counts, q, H, G) -> float | None:
    """S° = (ΔfH° − ΔfG°)/T + Σ S°(Elemente im Referenzzustand) (Umkehrung von dfG_from)."""
    refS = data().get("refS", {})
    try:
        return (H - G) * 1000 / T0 + sum(refS[e] * float(n) for e, n in counts.items()) - q * refS["H"]
    except KeyError:
        return None


def dfG_from(counts, q, H, S) -> float | None:
    """ΔfG° = ΔfH° − T·ΔfS°, ΔfS° = S° − Σ S°(Elemente im Referenzzustand) (+ z/2·S°(H₂) für Ionen, H⁺(aq)-Konvention)."""
    refS = data().get("refS", {})
    try:
        dS = S - sum(refS[e] * float(n) for e, n in counts.items()) + q / 2 * 2 * refS["H"]
    except KeyError:
        return None
    return H - T0 * dS / 1000


_EXCITED = re.compile(r"tripl|singl|excit|\bA\d?\b|\bB\d?\b", re.I)


def _plain_burcat(e: dict) -> bool:
    return e["src"] == "burcat" and (not e.get("poly") or e["poly"].upper() == "REF ELEMENT")


def candidates(sp: C.Species) -> list[dict]:
    """Einträge zur Summenformel und Ladung. Burcat führt auch angeregte Zustände (Singulett, Triplett, „*“) und
    Isomere unter derselben CAS-Nummer; die werden nicht als Daten des Grundzustands genommen."""
    d = data()["species"]
    raw = [d[i] for i in _index().get((_hill(sp), sp.charge), [])]
    plain = {(e.get("key"), e["ph"]) for e in raw if _plain_burcat(e) and e.get("key")}
    out = []
    for e in raw:
        if e["src"] == "burcat":
            if "*" in e["f"] or (e.get("poly") and _EXCITED.search(e["poly"]) and e.get("key")
                                and (e["key"], e["ph"]) in plain):
                continue
            if e.get("poly") and not _plain_burcat(e) and (e.get("key"), e["ph"]) in plain:
                continue                              # zweiter Burcat-Eintrag zur selben CAS-Nummer (Isomer, Zustand)
        out.append(e)
    return _own_entries(sp) + out


def _identity(sp: C.Species, cands: list[dict], key_hint: str | None) -> tuple[list[dict], list[str]]:
    """Einträge desselben Stoffs (Isomere trennen). Rückgabe: Einträge, Hinweise."""
    notes = []
    hill = _hill(sp)
    w2key = {}
    for e in cands:
        if e.get("key"):
            w2key.setdefault(_written(e["f"]), e["key"])

    def ident(e):
        if e.get("key"):
            return e["key"]
        w = _written(e["f"])
        if w in w2key:
            return w2key[w]
        if e["src"] == "burcat":
            return "b:" + (e.get("name") or w)        # Burcat-Eintrag ohne Bezug zur Sammlung (Isomer, Radikal)
        return "f:" + w
    groups = {}
    for e in cands:
        groups.setdefault(ident(e), []).append(e)
    if len(groups) <= 1:
        return cands, notes

    def rank(g):                                      # Sammlungseintrag vor Formel vor Burcat-Einzelnamen; beste Quelle
        return (g.startswith("b:"), g.startswith("f:"), min(PRIO.get(e["src"], 9) for e in groups[g]), -len(groups[g]))
    target = None
    if key_hint and key_hint in groups:
        target = key_hint
    w = _written(sp.text)
    if not target and w != hill:                      # Schreibweise wie C2H5OH oder (CH3)2O; reine Summenformel nicht
        hit = [g for g, es in groups.items() if any(_written(e["f"]) == w for e in es)]
        if hit:
            target = sorted(hit, key=rank)[0]
    if not target and key_hint is None:
        try:
            from . import substances as S
            k = S.resolve(sp.formula)
            if k in groups:
                target = k
        except Exception:
            pass
    if not target:
        target = sorted(groups, key=rank)[0]
    # Hinweis nur auf echte Isomere (Stoffe der Sammlung oder benannte Einträge der Tabellen), nicht auf angeregte Zustände
    others = [g for g in groups if g != target and not g.startswith("b:")]
    if others:
        def nm(g):
            try:
                from . import substances as S
                m = S.molecules().get(g)
                if m:
                    return m.get("de") or m.get("en") or g
            except Exception:
                pass
            es = groups[g]
            for e in es:
                if e.get("name") and not re.fullmatch(r"[A-Z][A-Za-z0-9()]*", e["name"]):
                    return e["name"]
            return es[0]["f"]
        notes.append(f"{sp.unicode()}: weitere Isomere mit Daten ({', '.join(nm(g) for g in others[:4])}); "
                     f"verwendet: {nm(target)}. Mit Name oder eindeutiger Schreibweise (z. B. C2H5OH) wählbar.")
    return groups[target], notes


def _best(entries: list[dict]) -> dict | None:
    """Beste Quelle, darin die stabilste Modifikation (kleinstes ΔfG°); Einträge mit ΔfH° und S° bevorzugt."""
    if not entries:
        return None
    return sorted(entries, key=lambda e: (PRIO.get(e["src"], 9), e.get("H") is None or e.get("S") is None,
                                          e.get("G") if e.get("G") is not None else 1e9, bool(e.get("ghs"))))[0]


def species_data(sp: C.Species, key_hint: str | None = None, choice: str | None = None) -> dict:
    """Daten eines Stoffs: gewählter Eintrag, Alternativen, Hinweise."""
    if sp.kind == "electron":
        raise ThermoError("Elektronen: Halbreaktionen werden über Standardpotenziale behandelt (folgt mit Redox)")
    if sp.kind != "chem":
        raise ThermoError(f"{sp.unicode()}: keine thermochemischen Bildungsdaten (Kernreaktion)")
    cands = candidates(sp)
    if not cands:
        raise ThermoError(f"keine Bildungsdaten für {sp.unicode()} in den mitgelieferten Tabellen")
    if key_hint is None and sp.name:                 # Name aufgelöst („Ethanol“): Stoff der Sammlung
        try:
            from . import substances as S
            key_hint = S.resolve(sp.name)
        except Exception:
            pass
    ents, notes = _identity(sp, cands, key_hint)
    want = PHASE_ALIAS.get(sp.phase, "") if sp.phase else ""
    phase_note = ""
    chosen = None
    if choice:
        chosen = next((e for e in ents if entry_id(e) == choice), None) or next((e for e in cands if entry_id(e) == choice), None)
    if chosen is None:
        if want:
            pool = [e for e in ents if e["ph"] == want or (e["src"] == "own" and e["ph"] == "?")]
            if want == "aq" and sp.charge == 0:
                ao = [e for e in pool if e.get("aqs") != "ai"]
                if ao:
                    pool = ao
            if not pool:
                have = sorted({e["ph"] for e in ents})
                raise ThermoError(f"keine Daten für {sp.unicode()} in der Phase ({sp.phase}); vorhanden: {', '.join(have)}")
            chosen = _best(pool)
        elif sp.charge:
            pool = [e for e in ents if e["ph"] in ("aq", "?")] or [e for e in ents if e["ph"] == "g"]
            chosen = _best(pool)
            phase_note = f"Ion ohne Phasenangabe: {chosen['ph']} angenommen" if chosen else ""
        else:
            per_phase = {}
            for ph in ("cr", "l", "g"):
                b = _best([e for e in ents if e["ph"] == ph])
                if b and b.get("G") is not None:
                    per_phase[ph] = b
            own = [e for e in ents if e["src"] == "own"]
            if own and not per_phase:
                chosen = own[0]
            elif per_phase:
                ph = min(per_phase, key=lambda p: per_phase[p]["G"])
                chosen = per_phase[ph]
                if len(per_phase) > 1:
                    phase_note = (f"Phase nicht angegeben: ({ph}) angenommen, die bei 298,15 K und 1 bar stabile Phase "
                                  f"(kleinstes ΔfG° unter {', '.join('(' + p + ')' for p in per_phase)})")
            else:
                chosen = _best(ents)
    if chosen is None:
        raise ThermoError(f"keine passenden Bildungsdaten für {sp.unicode()}")
    alts = sorted((e for e in ents if e is not chosen), key=lambda e: (e["ph"] != chosen["ph"], PRIO.get(e["src"], 9)))
    return {"entry": chosen, "id": entry_id(chosen), "alternatives": alts[:12], "notes": notes, "phase_note": phase_note}


def _pub(e: dict) -> dict:
    keep = ("src", "f", "ph", "aqs", "poly", "name", "H", "uH", "G", "Gcalc", "S", "Scalc", "uS", "Cp", "fix", "ghs", "Hsrc",
            "key", "source")
    d = {k: e.get(k) for k in keep if e.get(k) not in (None, "")}
    d["id"] = entry_id(e)
    d["refs"] = refs_of(e)
    return d


def refs_of(e: dict) -> list[str]:
    """Quellenschlüssel (labcalc.sources) eines Eintrags; ATcT-Enthalpien in Burcat zusätzlich mit Ruscic 2004."""
    r = list(SRC_REFS.get(e["src"], []))
    if e["src"] == "burcat" and e.get("Hsrc") == "atct":
        r.append("atct2004")
    return r


def reaction(eq: C.Equation, coefs, T: float = T0, choices: dict | None = None, key_hints: dict | None = None) -> dict:
    """Reaktionsgrössen aus den Bildungsdaten. coefs: ausgeglichene Koeffizienten (Edukte positiv angegeben)."""
    from fractions import Fraction
    choices, key_hints = choices or {}, key_hints or {}
    rows, missing, notes = [], [], []
    for i, t in enumerate(eq.terms):
        nu = float(Fraction(str(coefs[i]))) * t.side
        sp = t.species
        try:
            d = species_data(sp, key_hints.get(str(i)) or key_hints.get(i), choices.get(str(i)) or choices.get(i))
        except C.ChemError as err:
            missing.append({"i": i, "species": sp.unicode(), "error": str(err)})
            rows.append({"i": i, "species": sp.unicode(), "nu": nu, "error": str(err)})
            continue
        e = d["entry"]
        r = {"i": i, "species": sp.unicode(), "text": sp.text, "nu": nu, **_pub(e), "phase_note": d["phase_note"],
             "notes": d["notes"], "alternatives": [_pub(a) for a in d["alternatives"]]}
        if e.get("Cp") is None:                       # CODATA ohne Cp: Wert derselben Phase aus der nächsten Quelle
            a = next((a for a in sorted(d["alternatives"], key=lambda a: PRIO.get(a["src"], 9))
                      if a["ph"] == e["ph"] and a.get("aqs") == e.get("aqs") and a.get("Cp") is not None), None)
            if a:
                r["Cp"], r["Cp_src"] = a["Cp"], a["src"]
                r["refs"] = r["refs"] + [k for k in refs_of(a) if k not in r["refs"]]
        rows.append(r)
        notes += d["notes"]
    out = {"T": T, "rows": rows, "missing": missing, "notes": list(dict.fromkeys(notes))}
    if missing:
        out["error"] = "Für " + ", ".join(m["species"] for m in missing) + " fehlen Bildungsdaten"
        return out
    ok = [r for r in rows if "error" not in r]

    def total(k):
        vals = [(r["nu"], r.get(k)) for r in ok]
        if any(v is None for _, v in vals):
            return None
        return sum(n * v for n, v in vals)

    def unc(k, uk):
        terms = [(r["nu"] * r[uk]) ** 2 for r in ok if r.get(uk) is not None]
        complete = all(r.get(uk) is not None or (r.get(k) == 0) for r in ok)
        return (math.sqrt(sum(terms)) if terms else None), complete
    dH, dS, dGf = total("H"), total("S"), total("G")
    out.update({"dH": dH, "dS": dS, "dG_f": dGf, "dCp": total("Cp")})
    uH, cH = unc("H", "uH")
    uS, cS = unc("S", "uS")
    out["uH"], out["uS"], out["u_complete"] = uH, uS, cH and cS
    if dH is not None and dS is not None:
        out["dG_HS"] = dH - T0 * dS / 1000
        out["dG_T"] = dH - T * dS / 1000
    dG298 = out.get("dG_HS") if out.get("dG_HS") is not None else dGf
    if dGf is not None and out.get("dG_HS") is not None:
        out["dG_diff"] = out["dG_HS"] - dGf
    out["dG"] = dG298
    if dG298 is not None:
        x = -dG298 * 1000 / (R * T0)
        out["lnK"], out["lgK"] = x, x / math.log(10)
        out["K"] = math.exp(x) if x < 700 else math.inf
    if abs(T - T0) > 0.01 and out.get("dG_T") is not None:
        x = -out["dG_T"] * 1000 / (R * T)
        out["lgK_T"] = x / math.log(10)
        out["approx_T"] = True
    if dH is not None and dS is not None:
        out.update(spontaneity(dH, dS))
    # Gase: Δn und Kc
    dn = sum(r["nu"] for r in ok if r.get("ph") == "g")
    out["dn_gas"] = dn
    if out.get("lgK") is not None and dn and not any(r.get("ph") == "aq" for r in ok):
        f = P0 / (R * T0 * C0)
        out["lgKc"] = out["lgK"] + dn * math.log10(f)
    out["sources"] = sorted({r["src"] for r in ok}, key=lambda s: PRIO.get(s, 9))
    out["refs"] = list(dict.fromkeys(k for r in ok for k in r["refs"]))
    est = [r["species"] for r in ok if r["src"] in ("est", "estb")]
    if est:
        out["estimated"] = est
        meth = " bzw. ".join(m for s, m in (("estb", "Benson-Gruppenadditivität, Domalski & Hearing 1993"),
                                           ("est", "Joback & Reid 1987")) if any(r["src"] == s for r in ok))
        out["notes"].append(f"Ergebnis beruht teilweise auf Schätzwerten ({meth}, Gasphase) für "
                            + ", ".join(est) + "; Schätzwerte sind deutlich unsicherer als Tabellenwerte.")
    return out


def spontaneity(dH: float, dS: float) -> dict:
    """Vier Fälle nach den Vorzeichen von ΔH und ΔS (Näherung: beide unabhängig von T)."""
    out = {}
    if dS != 0 and (dH < 0) == (dS < 0):
        out["T_star"] = dH * 1000 / dS
    if dH < 0 and dS >= 0:
        out["case"] = "exergonisch bei jeder Temperatur (ΔH < 0, ΔS > 0)"
        out["case_en"] = "spontaneous at every temperature (ΔH < 0, ΔS > 0)"
    elif dH < 0 and dS < 0:
        out["case"] = "freiwillig unterhalb T* (ΔH < 0, ΔS < 0: enthalpiegetrieben)"
        out["case_en"] = "spontaneous below T* (ΔH < 0, ΔS < 0: enthalpy-driven)"
    elif dH > 0 and dS > 0:
        out["case"] = "freiwillig oberhalb T* (ΔH > 0, ΔS > 0: entropiegetrieben)"
        out["case_en"] = "spontaneous above T* (ΔH > 0, ΔS > 0: entropy-driven)"
    else:
        out["case"] = "bei keiner Temperatur freiwillig; die Rückreaktion ist freiwillig (ΔH > 0, ΔS < 0)"
        out["case_en"] = "not spontaneous at any temperature; the reverse reaction is (ΔH > 0, ΔS < 0)"
    return out


def heat(res: dict, stoich: dict | None, eq: C.Equation, coefs) -> dict:
    """Wärme für den berechneten Umsatz ξ und Reaktionsenthalpie je Masse der Edukte (z. B. Brennwert)."""
    from fractions import Fraction
    out = {}
    if res.get("dH") is None:
        return out
    if stoich and stoich.get("extent") is not None:
        out["Q_kJ"] = stoich["extent"] * res["dH"]
    per = []
    for i, t in enumerate(eq.terms):
        if t.side < 0 and t.species.kind == "chem":
            try:
                M = C.molar_mass(t.species)["M"]
            except C.ChemError:
                continue
            nu = float(Fraction(str(coefs[i])))
            per.append({"i": i, "species": t.species.unicode(), "per_mol": res["dH"] / nu, "per_kg": res["dH"] / nu / M * 1000})
    out["per_reactant"] = per
    # Verbrennung: O2 als Edukt, CO2 und/oder H2O als Produkt
    names = {(_hill(t.species), t.side) for t in eq.terms if t.species.kind == "chem"}
    if ("O2", -1) in names and (("CO2", 1) in names or ("H2O", 1) in names):
        water = [r for r in res["rows"] if r.get("f", "").replace(" ", "") == "H2O" and r["nu"] > 0]
        out["combustion"] = True
        out["water_phase"] = water[0]["ph"] if water else None
    return out


def dG_curve(dH: float, dS: float, T1: float = 200, T2: float = 2000, n: int = 91) -> list[tuple[float, float]]:
    return [(T, dH - T * dS / 1000) for T in (T1 + (T2 - T1) * k / (n - 1) for k in range(n))]


# ----------------------------------------------------------------------------- Ksp aus ΔfG°
def _binary_halide(formula: str):
    """AgCl, PbI2, CaF2: PubChem schreibt manche Halogenide kovalent (Cl[Ag]). Metallion mit Ladung aus der Formel."""
    try:
        sp = C.parse_species(formula)
    except C.ChemError:
        return None
    c = {k: int(v) for k, v in sp.counts.items() if v == int(v)}
    if len(c) != 2 or sp.charge:
        return None
    hal = [k for k in c if k in ("F", "Cl", "Br", "I")]
    if len(hal) != 1:
        return None
    x = hal[0]
    m = next(k for k in c if k != x)
    if m in ("H", "C", "N", "O", "S", "P", "Si", "B") or c[x] % c[m]:
        return None
    z = c[x] // c[m]
    from math import gcd
    g = gcd(c[m], c[x])
    return [(m + "^" + (str(z) if z > 1 else "") + "+", z, c[m] // g), (x + "^-", -1, c[x] // g)], 0


def ksp_from_dG(formula: str, smiles: str | None = None) -> dict | None:
    """Löslichkeitsprodukt aus ΔrG° der Auflösung MₐXᵦ·nH₂O(cr) → a M^z+(aq) + b X^z−(aq) + n H₂O(l).
    Die Ionen kommen aus der Struktur (SMILES der Sammlung)."""
    from .smiles import SmilesError, ions
    if not smiles:
        return None
    try:
        res = ions(smiles)
    except SmilesError:
        return None
    if not res:
        res = _binary_halide(formula)
    if not res:
        return None
    ion_list, water = res
    try:
        solid = species_data(C.parse_species(formula + "(cr)"))
        parts = [(n, species_data(C.parse_species(f + "(aq)"))) for f, q, n in ion_list]
        w = species_data(C.parse_species("H2O(l)")) if water else None
    except C.ChemError:
        return None
    gs = solid["entry"].get("G")
    if gs is None or any(p["entry"].get("G") is None for _, p in parts):
        return None
    dG = sum(n * p["entry"]["G"] for n, p in parts) + (water * w["entry"]["G"] if w else 0) - gs
    lgK = -dG * 1000 / (R * T0 * math.log(10))
    srcs = sorted({solid["entry"]["src"]} | {p["entry"]["src"] for _, p in parts}, key=lambda s: PRIO.get(s, 9))
    return {"value": lgK, "dG": dG, "ions": [f for f, _, _ in ion_list], "water": water, "sources": srcs,
            "reaction": f"{formula}(cr) → " + " + ".join((f"{n} " if n > 1 else "") + f + "(aq)" for f, _, n in ion_list)
                        + (f" + {water} H2O(l)" if water else "")}


# ----------------------------------------------------------------------------- Rechner-Funktionen
def _sp(q: str) -> C.Species:
    if not isinstance(q, str):
        raise C.ChemError('in Anführungszeichen angeben, z. B. dfH("H2O(l)")')
    return C.parse_species(q)


def _rx(q: str):
    if not isinstance(q, str):
        raise C.ChemError('Gleichung in Anführungszeichen, z. B. dHr("CH4 + O2 -> CO2 + H2O(l)")')
    eq = C.parse_equation(q)
    b = C.balance(eq)
    if b.get("status") not in ("ok", "given_ok"):
        raise C.ChemError(b.get("reason") or "Gleichung lässt sich nicht ausgleichen")
    res = reaction(eq, b["coefs"])
    if res.get("error"):
        raise C.ChemError(res["error"])
    return res


def _rxv(q: str, k: str) -> float:
    v = _rx(q).get(k)
    if v is None:
        raise C.ChemError({"dH": "ΔrH°", "dS": "ΔrS°", "dG": "ΔrG°", "lgK": "lg K"}.get(k, k)
                          + " nicht berechenbar: Bildungsdaten unvollständig")
    return v


def register_calc_functions():
    from . import expr as E
    from . import units as U
    Hd, Sd = U.kind_dims("molar_energy"), U.kind_dims("molar_entropy")

    def val(q, k):
        d = species_data(_sp(q))
        v = d["entry"].get(k)
        if v is None:                                 # z. B. Cp fehlt bei CODATA: nächste Quelle derselben Phase
            v = next((a.get(k) for a in sorted(d["alternatives"], key=lambda a: PRIO.get(a["src"], 9))
                      if a["ph"] == d["entry"]["ph"] and a.get("aqs") == d["entry"].get("aqs") and a.get(k) is not None), None)
        if v is None:
            raise C.ChemError(f"kein Wert {k} für {q}")
        return v
    E.register_string_function("dfH", lambda ctx, q: val(q, "H") * 1000, 1, 1, Hd,
                               'dfH("H2O(l)") – Standardbildungsenthalpie ΔfH° bei 298,15 K (CODATA/NBS/Burcat)')
    E.register_string_function("dfG", lambda ctx, q: val(q, "G") * 1000, 1, 1, Hd,
                               'dfG("H2O(l)") – freie Standardbildungsenthalpie ΔfG° bei 298,15 K')
    E.register_string_function("Sm0", lambda ctx, q: val(q, "S"), 1, 1, Sd,
                               'Sm0("H2O(l)") – molare Standardentropie S° bei 298,15 K')
    E.register_string_function("Cpm0", lambda ctx, q: val(q, "Cp"), 1, 1, Sd,
                               'Cpm0("H2O(l)") – molare Wärmekapazität Cp° bei 298,15 K')
    E.register_string_function("dHr", lambda ctx, q: _rxv(q, "dH") * 1000, 1, 1, Hd,
                               'dHr("CH4 + O2 -> CO2 + H2O(l)") – Reaktionsenthalpie ΔrH° (Gleichung wird ausgeglichen)')
    E.register_string_function("dSr", lambda ctx, q: _rxv(q, "dS"), 1, 1, Sd,
                               'dSr("N2 + H2 -> NH3") – Reaktionsentropie ΔrS°')
    E.register_string_function("dGr", lambda ctx, q: _rxv(q, "dG") * 1000, 1, 1, Hd,
                               'dGr("N2 + H2 -> NH3") – freie Reaktionsenthalpie ΔrG° bei 298,15 K')
    E.register_string_function("lgKr", lambda ctx, q: _rxv(q, "lgK"), 1, 1, U.D0,
                               'lgKr("N2 + H2 -> NH3") – lg K bei 298,15 K aus ΔrG° = −RT ln K')
