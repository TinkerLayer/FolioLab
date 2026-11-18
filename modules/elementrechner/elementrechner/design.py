"""Moleküldesigner, Server-Seite: alles, was aus der gezeichneten Struktur folgt.

Exakt aus der Struktur: Summenformel, molare Masse (CIAAW), monoisotopische Masse (AME2020, häufigstes Isotop nach
CIAAW), Doppelbindungsäquivalente, funktionelle Gruppen.
Name: Regelbenennung nach IUPAC 2013 (labcalc.naming); Wiedererkennung in Sammlung und eigenen Stoffen geschieht im
Browser (OpenChemLib-idcode), hier werden nur die Kandidaten gleicher Summenformel geliefert.
Schätzungen: Joback & Reid 1987 (labcalc.joback); Benson-Gruppenadditivität mit den Werten von Domalski & Hearing
1993 (labcalc.benson, ΔfH°/S°/Cp° der Gasphase, als „Benson“ gekennzeichnet; Joback bleibt Rückfall, tabellierte
Messwerte der Thermochemie haben Vorrang); log P, log S, TPSA rechnet der Browser mit OpenChemLib.
pKa: keine Vorhersage – nur ein Anhaltspunkt über eine verwandte Verbindung der Sammlung mit gemessenem Wert.
PubChem: nur auf Knopfdruck; gesendet wird ausschliesslich die Struktur (SMILES).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from labcalc import benson as B
from labcalc import chem as C
from labcalc import joback as J
from labcalc import molgraph as G
from labcalc import naming as NM
from labcalc import smiles as SM
from labcalc import sources as SRC
from labcalc import substances as S
from labcalc import thermo as TH
from labcalc.smiles import SmilesError

M_E = 5.485799090441e-4          # Elektronenmasse in u, CODATA 2022

# Gruppe -> verwandte Verbindungen der Sammlung (erste auflösbare mit pKa-Wert wird genannt)
PKA_REP = {
    "acid": ["acetic acid", "Essigsäure"], "acid_ar": ["benzoic acid", "Benzoesäure"], "phenol": ["phenol", "Phenol"],
    "amine1": ["ethylamine", "methylamine", "Ethylamin"], "amine2": ["diethylamine", "dimethylamine"],
    "amine3": ["triethylamine", "trimethylamine"], "arylamine": ["aniline", "Anilin"], "pyridine": ["pyridine", "Pyridin"],
    "thiol": ["ethanethiol", "methanethiol"], "alcohol": ["ethanol", "methanol"], "sulfonic": ["methanesulfonic acid"],
    "imidazole": ["imidazole"],
}
PKA_LABEL = {"acid": "Carbonsäure", "acid_ar": "aromatische Carbonsäure", "phenol": "Phenol", "amine1": "primäres Amin",
             "amine2": "sekundäres Amin", "amine3": "tertiäres Amin", "arylamine": "aromatisches Amin",
             "pyridine": "Pyridin-Stickstoff", "thiol": "Thiol", "alcohol": "Alkohol", "sulfonic": "Sulfonsäure",
             "imidazole": "Imidazol"}

# Typische Reaktionen je Gruppe (Lehrbuchwissen; Clayden, Greeves, Warren: Organic Chemistry, 2. Aufl. 2012)
HINTS = {
    "acid": "Salzbildung mit Basen; Veresterung mit Alkoholen (säurekatalysiert); Amide über aktivierte Derivate; "
            "Reduktion zum primären Alkohol (LiAlH₄)",
    "ester": "Verseifung (basisch) bzw. saure Hydrolyse zu Säure und Alkohol; Umesterung; Aminolyse zum Amid; "
             "Reduktion zum Alkohol",
    "lactone": "Ringöffnung durch Hydrolyse (Hydroxysäure) oder Aminolyse",
    "anhydride": "Acylierung von Alkoholen und Aminen; Hydrolyse zur Säure",
    "acyl_halide": "sehr reaktives Acylierungsmittel: mit Wasser Säure, mit Alkoholen Ester, mit Aminen Amide",
    "amide": "Hydrolyse (sauer/basisch, langsam) zu Säure und Amin; Reduktion zum Amin; primäre Amide: "
             "Dehydratisierung zum Nitril",
    "nitrile": "Hydrolyse über das Amid zur Carbonsäure; Reduktion zum primären Amin",
    "aldehyde": "Oxidation zur Säure; Reduktion zum primären Alkohol; nucleophile Addition (Halbacetal, Cyanhydrin, "
                "Imin); Aldolreaktion",
    "ketone": "Reduktion zum sekundären Alkohol; nucleophile Addition (Grignard, Imin, Enamin); α-Reaktionen über das "
              "Enolat",
    "alcohol": "Oxidation (primär → Aldehyd/Säure, sekundär → Keton); Veresterung; säurekatalysierte Eliminierung "
               "zum Alken; Substitution nach Aktivierung",
    "phenol": "schwache Säure (Phenolat mit Basen); elektrophile Substitution am Ring (o/p, aktivierend); "
              "Veretherung und Veresterung",
    "enol": "steht im Gleichgewicht mit der Carbonylform (Keto-Enol-Tautomerie)",
    "amine1": "Base (Ammoniumsalz mit Säuren); Nucleophil: Alkylierung, Acylierung zum Amid, Imin mit Carbonylen",
    "amine2": "Base; Nucleophil: Alkylierung, Acylierung zum Amid, Enamin mit Ketonen",
    "amine3": "Base; Alkylierung zum quartären Ammoniumsalz",
    "arylamine": "schwache Base; Diazotierung (primär); Acylierung; elektrophile Substitution (o/p, stark aktivierend)",
    "ether": "weitgehend reaktionsträge; Spaltung mit HI/HBr; Peroxidbildung an Luft möglich",
    "epoxide": "Ringöffnung durch Nucleophile (sauer oder basisch katalysiert)",
    "halide": "nucleophile Substitution (SN1/SN2); Eliminierung zum Alken (E1/E2); Grignard-Reagenz mit Mg",
    "arylhalide": "kaum nucleophile Substitution; Kreuzkupplung (Pd-katalysiert); Grignard-Reagenz",
    "alkene": "elektrophile Addition (HX, X₂, H₂O); Hydrierung; Epoxidierung; Polymerisation",
    "alkyne": "Addition (H₂, HX, X₂); Hydratisierung zum Keton; terminale Alkine sind C–H-acide",
    "arene": "elektrophile aromatische Substitution (Nitrierung, Halogenierung, Friedel-Crafts)",
    "nitro": "Reduktion zum Amin; am Aromaten stark desaktivierend und m-dirigierend",
    "thiol": "Oxidation zum Disulfid; saurer als Alkohole; gutes Nucleophil",
    "sulfide": "Oxidation zum Sulfoxid und Sulfon",
    "imine": "Hydrolyse zu Carbonylverbindung und Amin; Reduktion zum Amin",
}


def mono_mass(counts: dict, charge: int = 0) -> float | None:
    """Monoisotopische Masse: je Element das häufigste Isotop (CIAAW), Massen aus AME2020; Ionen minus z·mₑ."""
    data = C._json("isotopes.json") or {}
    nuc, by = data.get("nuclides", {}), data.get("by_element", {})
    total = 0.0
    for el, n in counts.items():
        if el in ("D", "T"):
            key = "2H" if el == "D" else "3H"
        elif el.startswith("^"):
            key = el[1:]
        else:
            best, bf = None, -1.0
            for k in by.get(el, []):
                ab = (nuc.get(k) or {}).get("abundance_ciaaw") or {}
                f = ab.get("fraction")
                if f is None and ab.get("interval"):
                    lo, hi = ab["interval"]
                    f = (lo + hi) / 2
                if f is not None and f > bf:
                    best, bf = k, f
            key = best
        m = (nuc.get(key) or {}).get("mass_u") if key else None
        if m is None:
            return None
        total += n * m
    return total - charge * M_E


def _acid_aromatic(m: G.Mol) -> bool:
    for c in range(m.n()):
        if m.el[c] == "C" and G.terminal_O(m, c, 2) and any(m.el[j] == "O" and o == 1 and m.h[j] == 1 for j, o in m.nbrs(c)):
            if any(G.aromatic_atom(m, j) for j, _ in m.nbrs(c) if m.el[j] == "C"):
                return True
    return False


def pka_hints(m: G.Mol, groups: list[dict]) -> list[dict]:
    keys = {g["key"] for g in groups}
    want = []
    if "acid" in keys:
        want.append("acid_ar" if _acid_aromatic(m) else "acid")
    for k in ("phenol", "amine1", "amine2", "amine3", "arylamine", "thiol", "sulfonic", "alcohol"):
        if k in keys:
            want.append(k)
    if any(m.el[a] == "N" and m.aro[a] and m.h[a] == 0 and m.deg(a) == 2 for a in range(m.n())):
        want.append("pyridine")
    out = []
    for w in want:
        for nm in PKA_REP.get(w, []):
            key = S.resolve(nm)
            if not key:
                continue
            try:
                ch = S.pka(key, 1, 25.0)
            except C.ChemError:
                continue
            mm = S.molecules().get(key) or {}
            out.append({"group": PKA_LABEL[w], "key": key, "name": mm.get("de") or mm.get("en") or nm,
                        "smiles": mm.get("smiles"), "pka": ch.get("value"), "T_C": ch.get("T_C"),
                        "source": ch.get("source"), "label": ch.get("label")})
            break
    return out


def candidates(hill: str) -> list[dict]:
    """Stoffe der Sammlung und eigene Stoffe mit derselben Summenformel (für den Strukturvergleich im Browser)."""
    keys = S._index()[1].get(hill, [])
    mols = S.molecules()
    out = []
    for k in keys[:60]:
        mm = mols.get(k) or {}
        if mm.get("smiles"):
            out.append({"key": k, "de": mm.get("de") or mm.get("name"), "en": mm.get("en"), "smiles": mm["smiles"],
                        "formula": mm.get("formula"), "cas": mm.get("cas"), "own": bool(mm.get("own"))})
    return out


def analyze(smiles: str) -> dict:
    smiles = (smiles or "").strip()
    if not smiles:
        raise ValueError("keine Struktur")
    if len(smiles) > 4000:
        raise ValueError("Struktur zu gross")
    try:
        m = G.parse(smiles)
    except SmilesError as e:
        raise ValueError(f"Struktur nicht lesbar: {e}") from e
    counts = m.element_counts()
    q = m.charge()
    hill = C._hill(counts) + (f"^{abs(q) if abs(q) > 1 else ''}{'+' if q > 0 else '-'}" if q else "")
    out = {"smiles": smiles, "hill": hill, "charge": q, "fragments": len(m.fragments()), "stereo": m.stereo,
           "atoms": m.n(), "notes": []}
    try:
        eqf = SM.equation_formula(smiles)[0]
        out["formula"] = eqf
        mm = C.molar_mass(eqf)
        out["M"], out["uM"] = mm["M"], mm.get("u")
    except (SmilesError, C.ChemError) as e:
        out["formula"] = None
        out["notes"].append(f"Formel für Gleichungen nicht bildbar: {e}")
        try:
            mm = C.molar_mass(C._hill(counts))
            out["M"], out["uM"] = mm["M"], mm.get("u")
        except C.ChemError:
            out["M"] = None
    out["mono"] = mono_mass(m.counts(), q)
    out["dbe"] = G.dbe(counts) if not q else None
    groups = G.functional_groups(m)
    out["groups"] = groups
    out["hints"] = [{"group": g["de"], "text": HINTS[g["key"]]} for g in groups if g["key"] in HINTS]
    out["name"] = NM.name(smiles)
    try:
        if len(m.fragments()) != 1:
            raise J.JobackError("mehrere Fragmente (Salz, Gemisch)")
        jb = J.estimate(m, out.get("M"))
        H, Gf = jb["values"]["dfH_g"]["v"], jb["values"]["dfG_g"]["v"]
        s = TH.S_from(counts, 0, H, Gf) if H is not None and Gf is not None else None
        jb["values"]["S_g"] = {"v": s, "u": "J/(mol·K)", "label": "S°(g, 298 K)",
                               "note": "abgeleitet: (ΔfH° − ΔfG°)/T + Σ S°(Elemente), Elemente nach CODATA Key Values"}
        out["joback"] = jb
    except J.JobackError as e:
        out["joback"] = {"error": str(e)}
    try:
        if len(m.fragments()) != 1:
            raise B.BensonError("Benson nicht anwendbar: mehrere Fragmente (Salz, Gemisch)")
        out["benson"] = B.estimate(m)
    except B.BensonError as e:
        out["benson"] = {"error": str(e), "method": "Benson", "refs": B.REFS}
    out["pka_hints"] = pka_hints(m, groups)
    out["candidates"] = candidates(hill)
    out["refs"] = {k: SRC.REFS[k] for k in ("favre2014", "joback1987", "joback_wiki", "domalski1993", "benson1969",
                                             "ertl2000", "sander2015", "clayden2012", "pubchem2025")}
    return out


UA = "FolioLab-Elementrechner/0.4"
PUG = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/property/IUPACName,Title,MolecularFormula,InChIKey/JSON"


def pubchem(smiles: str, timeout: float = 15) -> dict:
    """Name bei PubChem (PUG REST, POST). Gesendet wird nur die Struktur."""
    smiles = (smiles or "").strip()
    if not smiles or len(smiles) > 4000:
        raise ValueError("keine oder zu grosse Struktur")
    body = urllib.parse.urlencode({"smiles": smiles}).encode()
    req = urllib.request.Request(PUG, data=body, headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"found": False, "note": "PubChem kennt diese Struktur nicht"}
        if e.code in (429, 503):
            return {"found": False, "note": "PubChem ist ausgelastet (Anfragebegrenzung); später erneut versuchen"}
        raise ValueError(f"PubChem antwortet mit HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise ValueError(f"PubChem nicht erreichbar: {getattr(e, 'reason', e)}") from e
    props = (data.get("PropertyTable") or {}).get("Properties") or []
    p = props[0] if props else {}
    if not p.get("CID"):
        return {"found": False, "note": "PubChem kennt diese Struktur nicht"}
    return {"found": True, "cid": p["CID"], "iupac": p.get("IUPACName"), "title": p.get("Title"),
            "formula": p.get("MolecularFormula"), "inchikey": p.get("InChIKey"),
            "note": "IUPAC-Name von PubChem berechnet (OpenEye Lexichem TK)", "source": SRC.REFS["pubchem2025"]}
