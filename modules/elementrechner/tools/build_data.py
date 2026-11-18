"""Baut die Datendateien des Elementrechners aus den Originaldateien der Quellen.

Die Originale werden nicht im Projekt abgelegt (sie sind jederzeit neu herunterladbar, URLs unten). Aufruf:

    python -I tools/build_data.py <Ordner mit den Originalen> [teil ...]

Der Ordner enthält je Quelle einen Unterordner (ciaaw/, ame/, nbs/, burcat/, pka/, srd46/, codata/, pubchem/).
Ergebnis: sdk/python/labcalc/data/*.json bzw. modules/elementrechner/elementrechner/data/*.json.
Jede Datei trägt "_source" (Zitierschlüssel), "_built" (Datum) und "_from" (Originaldatei mit URL).
"""
from __future__ import annotations

import html
import json
import re
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[3]
SDK_DATA = ROOT / "sdk" / "python" / "labcalc" / "data"
MOD_DATA = HERE.parents[1] / "elementrechner" / "data"

URLS = {
    "ciaaw_abridged": "https://www.ciaaw.org/abridged-atomic-weights.htm",
    "ciaaw_full": "https://www.ciaaw.org/atomic-weights.htm",
    "ciaaw_iso": "https://www.ciaaw.org/isotopic-abundances.htm",
    "ame": "https://amdc.impcas.ac.cn/masstables/Ame2020/mass_1.mas20",
    "nubase": "https://amdc.impcas.ac.cn/masstables/Ame2020/nubase_4.mas20",
}

SYMBOLS = ("H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr "
           "Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir "
           "Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl "
           "Mc Lv Ts Og").split()


def _write(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=False), encoding="utf-8")
    print(f"  {path.relative_to(ROOT)}  ({path.stat().st_size // 1024} KB)")


def _meta(source: str, files: dict) -> dict:
    return {"_source": source, "_built": date.today().isoformat(), "_from": files}


# ----------------------------------------------------------------------------- CIAAW
def _cells(row_html: str) -> list[str]:
    cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.S)
    return [html.unescape(re.sub(r"<[^>]+>", "", c)).replace("\xa0", " ").strip() for c in cells]


def _rows(page: str) -> list[str]:
    """Zeilen der Tabelle; an </tr> getrennt, weil der CIAAW-Seite vor manchen Zeilen das <tr> fehlt."""
    body = page[page.index("<tbody"):page.index("</tbody>")]
    body = body[body.index(">") + 1:]
    return [c for c in body.split("</tr>") if "<td" in c]


def _notes(row_html: str) -> list[str]:
    return re.findall(r'href="#([a-z])"', row_html)


def _num_unc(s: str) -> tuple[float, float, int]:
    """'4.002 602(2)' -> (4.002602, 0.000002, Nachkommastellen); '1.0080 ± 0.0002' -> (1.008, 0.0002, 4)."""
    s = s.replace(" ", "").replace(" ", "")
    m = re.fullmatch(r"([\d.]+)±([\d.]+)", s)
    if m:
        return float(m.group(1)), float(m.group(2)), len(m.group(1).split(".")[1]) if "." in m.group(1) else 0
    m = re.fullmatch(r"([\d.]+)\((\d+)\)", s)
    if m:
        v = m.group(1)
        nd = len(v.split(".")[1]) if "." in v else 0
        return float(v), int(m.group(2)) * 10 ** -nd, nd
    if re.fullmatch(r"[\d.]+", s):
        return float(s), 0.0, len(s.split(".")[1]) if "." in s else 0
    raise ValueError(s)


def build_ciaaw(raw: Path):
    d = raw / "ciaaw"
    ab = (d / "abridged-atomic-weights.htm").read_text(encoding="utf-8")
    full = (d / "atomic-weights.htm").read_text(encoding="utf-8")
    iso = (d / "isotopic-abundances.htm").read_text(encoding="utf-8")
    out: dict = {}
    for r in _rows(ab):
        c = _cells(r)
        if len(c) < 4 or not c[0].isdigit():
            continue
        Z, sym = int(c[0]), c[1]
        assert SYMBOLS[Z - 1] == sym, (Z, sym)
        e = {"Z": Z, "notes": _notes(r)}
        if c[3] in ("—", "-", ""):
            e["value"] = None
        else:
            v, u, nd = _num_unc(c[3])
            e.update(value=v, u=u, digits=nd, abridged=c[3])
        out[sym] = e
    for r in _rows(full):
        c = _cells(r)
        if len(c) < 4 or not c[0].isdigit():
            continue
        sym = c[1]
        t = re.sub(r"\s+", " ", c[3]).strip()
        if t in ("—", "-", ""):
            continue
        out[sym]["text"] = t
        m = re.fullmatch(r"\[([\d. ]+),\s*([\d. ]+)\]", t)
        if m:
            out[sym]["interval"] = [float(m.group(1).replace(" ", "")), float(m.group(2).replace(" ", ""))]
        else:
            v, u, _ = _num_unc(t)
            out[sym]["standard"] = v
            out[sym]["standard_u"] = u
    # Isotopenzusammensetzung; Massenzahl in [ ] = Element ohne Standard-Atomgewicht
    by_el: dict = {}
    cur = None
    for r in _rows(iso):
        c = _cells(r)
        if not c:
            continue
        if len(c) >= 5 and c[0].isdigit():
            cur = c[1]
            A, comp = c[3], c[4]
        elif len(c) >= 2 and cur:
            A, comp = c[0], c[1]
        else:
            continue
        m = re.fullmatch(r"\[(\d+)\]", A)
        if m:
            out[cur]["mass_number"] = int(m.group(1))
            continue
        if not A.isdigit():
            continue
        t = re.sub(r"\s+", " ", comp).strip()
        ent = {"A": int(A), "text": t}
        mi = re.fullmatch(r"\[([\d. ]+),\s*([\d. ]+)\]", t)
        if mi:
            lo, hi = float(mi.group(1).replace(" ", "")), float(mi.group(2).replace(" ", ""))
            ent.update(interval=[lo, hi])
        elif t not in ("-", "—"):
            v, u, _ = _num_unc(t)
            ent.update(fraction=v, u=u)
        by_el.setdefault(cur, []).append(ent)
    missing = [s for s in SYMBOLS if s not in out]
    assert not missing, missing
    nostd = [s for s, e in out.items() if e.get("value") is None and "mass_number" not in e]
    aw = {**out, **_meta("ciaaw2024", {"abridged": URLS["ciaaw_abridged"], "full": URLS["ciaaw_full"],
                                       "isotopic": URLS["ciaaw_iso"]}),
          "_note": "value/u: gekürzte Standard-Atomgewichte (CIAAW 2024); text/interval: ungekürzte Werte; "
                   "mass_number: Massenzahl in [ ] aus der CIAAW-Isotopentabelle (Element ohne Standard-Atomgewicht); "
                   "notes: Fussnoten g, m, r der CIAAW-Tabelle."}
    print(f"CIAAW: {len(out)} Elemente, {sum(1 for e in out.values() if e.get('value') is not None)} mit Standard-Atomgewicht, "
          f"ohne Massenzahl aus CIAAW: {len(nostd)}")
    return aw, by_el


def fill_mass_numbers(aw: dict, nuc: dict):
    """Elemente ohne Standard-Atomgewicht und ohne CIAAW-Massenzahl: langlebigstes Isotop nach NUBASE2020."""
    filled = []
    for sym in SYMBOLS:
        e = aw[sym]
        if e.get("value") is not None or "mass_number" in e:
            continue
        Z = SYMBOLS.index(sym) + 1
        cands = [(v.get("half_life_s") or 0.0, v["A"]) for v in nuc.values()
                 if v.get("Z") == Z and not v.get("isomer") and v.get("half_life_s")]
        if not cands:
            continue
        t, A = max(cands)
        e["mass_number"] = A
        e["mass_number_source"] = "nubase2020"
        filled.append(f"{sym}-{A}")
    print(f"  Massenzahl nach NUBASE2020 (langlebigstes Isotop): {', '.join(filled)}")


# ----------------------------------------------------------------------------- AME2020 / NUBASE2020
_T_UNIT = {"ys": 1e-24, "zs": 1e-21, "as": 1e-18, "fs": 1e-15, "ps": 1e-12, "ns": 1e-9, "us": 1e-6, "ms": 1e-3,
           "s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0}
_YEAR = 365.2422 * 86400.0       # NUBASE2020: 1 a = 365,2422 d
for _p, _f in (("y", 1), ("ky", 1e3), ("My", 1e6), ("Gy", 1e9), ("Ty", 1e12), ("Py", 1e15), ("Ey", 1e18), ("Zy", 1e21),
               ("Yy", 1e24)):
    _T_UNIT[_p] = _f * _YEAR


def _f(s: str):
    """Zahl aus AME/NUBASE; '#' statt Dezimalpunkt = Schätzwert aus der Systematik."""
    s = s.strip()
    if not s or s == "*":
        return None, False
    est = "#" in s
    try:
        return float(s.replace("#", ".") if s.count("#") == 1 and "." not in s else s.replace("#", "")), est
    except ValueError:
        return None, est


def build_nuclides(raw: Path, by_el: dict):
    d = raw / "ame"
    nuc: dict = {}
    started = False
    for line in (d / "mass_1.mas20").read_text(encoding="utf-8").splitlines():
        if not started:
            started = "micro-u" in line
            continue
        if len(line) < 130:
            continue
        try:
            Z, A = int(line[9:14]), int(line[14:19])
        except ValueError:
            continue
        el = line[20:23].strip()
        if Z == 0:
            el = "n"
        hi = int(line[106:109])
        lo, est = _f(line[110:123])
        u, est2 = _f(line[123:135])
        if lo is None:
            continue
        mass = hi + lo * 1e-6
        key = f"{A}{el}" if Z else "1n"
        nuc[key] = {"Z": Z, "A": A, "mass_u": round(mass, 12), "u_u": (u or 0) * 1e-6}
        if est or est2:
            nuc[key]["estimated"] = True
    n_half = 0
    for line in (d / "nubase_4.mas20").read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or len(line) < 80:
            continue
        A = int(line[0:3])
        zi = line[4:8]
        Z, iso = int(zi[:3]), zi[3]
        name = line[11:16].strip()
        state = line[16].strip()
        el = re.sub(r"^\d+", "", name) or "n"
        if iso not in "0" and state not in ("m", "n"):
            continue                                        # Niveaus, Resonanzen, IAS: nicht gebraucht
        key = f"{A}{state if iso != '0' else ''}{el}"            # Isomere wie üblich: 99mTc, 235nU
        t_raw, unit, dt = line[69:78].strip(), line[78:80].strip(), line[81:88].strip()
        e = nuc.setdefault(key, {"Z": Z, "A": A})
        if iso != "0":
            ex, _ = _f(line[42:54])
            e["isomer"] = True
            e["excitation_keV"] = ex
        if t_raw == "stbl":
            e["stable"] = True
        elif t_raw == "p-unst":
            e["particle_unstable"] = True
        elif t_raw:
            v, est = _f(t_raw.replace("<", "").replace(">", "").replace("~", ""))
            if v is not None and unit in _T_UNIT:
                e["half_life_s"] = v * _T_UNIT[unit]
                e["half_life"] = f"{t_raw} {unit}" + (f" ({dt})" if dt else "")
                if est or t_raw[0] in "<>~":
                    e["half_life_estimated"] = True
                n_half += 1
            elif unit in ("eV", "ke", "Me"):                    # Breite statt Halbwertszeit
                e["width"] = f"{t_raw} {unit}"
        jp = line[88:102].strip()
        if jp:
            e["spin_parity"] = jp
        br = line[119:209].strip() if len(line) > 119 else ""
        if br:
            e["decay_text"] = br
            modes = []
            for part in br.split(";"):
                part = part.strip()
                m = re.match(r"^([A-Za-z0-9+\-]+)\s*([=~<>?]+)?\s*([\d.#]+(?:e[-+]?\d+)?)?", part)
                if not m:
                    continue
                mode = m.group(1)
                if mode == "IS":
                    v, _ = _f(m.group(3) or "")
                    if v is not None:
                        e["abundance_nubase_pct"] = v
                    continue
                v, _ = _f(m.group(3) or "")
                modes.append({"mode": mode, "rel": m.group(2) or "", "pct": v})
            if modes:
                e["decay"] = modes
    # Häufigkeiten aus CIAAW 2024 (bevorzugt), sonst NUBASE
    for sym, rows in by_el.items():
        for r in rows:
            k = f"{r['A']}{sym}"
            if k in nuc:
                nuc[k]["abundance_ciaaw"] = {x: r[x] for x in ("text", "fraction", "u", "interval") if x in r}
    by_element: dict = {}
    for k, e in nuc.items():
        if e.get("isomer") or not e.get("Z"):
            continue
        sym = SYMBOLS[e["Z"] - 1]
        by_element.setdefault(sym, []).append(k)
    for sym in by_element:
        by_element[sym].sort(key=lambda k: nuc[k]["A"])
    obj = {"nuclides": nuc, "by_element": by_element,
           **_meta("ame2020", {"ame": URLS["ame"], "nubase": URLS["nubase"], "abundance": URLS["ciaaw_iso"]}),
           "_sources": {"mass": "ame2020", "half_life": "nubase2020", "abundance": "ciaaw_iso2024"},
           "_note": "mass_u/u_u: Atommasse in u (AME2020); estimated: Wert aus der Systematik (#). half_life_s mit "
                    "1 a = 365,2422 d (NUBASE2020). decay: Zerfallsarten mit Anteil in %. abundance_ciaaw: "
                    "repräsentative Isotopenzusammensetzung (Stoffmengenanteil) CIAAW 2024."}
    print(f"AME/NUBASE: {len(nuc)} Nuklide, {n_half} mit Halbwertszeit")
    _write(SDK_DATA / "isotopes.json", obj)
    return nuc


# ----------------------------------------------------------------------------- PubChem-Sammlung
_SKIP_SYN = re.compile(r"^(UNII|EINECS|EC |DTXSID|DTXCID|CHEBI|CHEMBL|NSC|HSDB|CCRIS|BRN|AI3-|SCHEMBL|MFCD|AKOS|ZINC|"
                       r"WLN|InChI|Q\d|D0|NCGC|BDBM|STL|CAS-|RCRA|UN\d|FEMA|E\d{3}|Caswell|EPA|AC-|CS-|HY-|FT-|SY|"
                       r"[A-Z]{2,}\d{3,}|\d+-\d+-\d$)", re.I)


def _cas_ok(s: str) -> bool:
    m = re.fullmatch(r"(\d{2,7})-(\d\d)-(\d)", s)
    if not m:
        return False
    digits = (m.group(1) + m.group(2))[::-1]
    return sum((i + 1) * int(d) for i, d in enumerate(digits)) % 10 == int(m.group(3))


# Quellen der PUG-View-Eigenschaften, deren Bedingungen eine Übernahme erlauben (Behörden-Werke bzw. CC BY 4.0).
# Nicht übernommen: CAMEO, Haz-Map, DrugBank, ChEMBL, HMDB u. a. mit eigenen Nutzungsbedingungen.
OPEN_SOURCES = {
    "Hazardous Substances Data Bank (HSDB)": ("hsdb", "U.S. National Library of Medicine, gemeinfrei (U.S. Government Work)"),
    "ILO-WHO International Chemical Safety Cards (ICSCs)": ("icsc", "CC BY 4.0"),
    "Occupational Safety and Health Administration (OSHA)": ("osha", "U.S. Government Work"),
    "The National Institute for Occupational Safety and Health (NIOSH)": ("niosh", "U.S. Government Work"),
    "PAC Chemical Database, U.S. Department of Energy": ("doepac", "U.S. Government Work"),
}

PROP_HEADINGS = {
    # Überschrift -> (Schlüssel, Zielgröße)
    "Melting Point": ("mp", "T"), "Boiling Point": ("bp", "T"), "Flash Point": ("flash", "T"),
    "Autoignition Temperature": ("autoign", "T"), "Density": ("density", "rho"), "Vapor Pressure": ("vp", "p"),
    "Vapor Density": ("vapdens", "rel"), "Solubility": ("solubility", "text"), "Dissociation Constants": ("pka", "pK"),
    "LogP": ("logp", "num"), "Henry's Law Constant": ("henry", "kH"), "Refractive Index": ("nD", "num"),
    "Viscosity": ("viscosity", "eta"), "Surface Tension": ("surftens", "gamma"), "Ionization Potential": ("ip", "eV"),
    "Heat of Vaporization": ("dHvap", "E"), "Heat of Combustion": ("dHc", "E"), "Physical Description": ("descr", "text"),
    "Color/Form": ("color", "text"), "Odor": ("odor", "text"), "Decomposition": ("decomp", "text"),
    "Stability/Shelf Life": ("stability", "text"),
}
_NUM = r"(-?\d+(?:[.,]\d+)?(?:\s*[xX×]\s*10\s*\^?\s*\(?(-?\d+)\)?|[eE]-?\d+)?)"


def _f(s: str) -> float:
    s = s.replace(",", ".")
    m = re.match(r"(-?\d+(?:\.\d+)?)\s*[xX×]\s*10\s*\^?\s*\(?(-?\d+)\)?", s)
    return float(m.group(1)) * 10 ** int(m.group(2)) if m else float(s)


def _temp_c(val: float, unit: str) -> float:
    u = unit.replace(" ", "").replace("deg", "°").upper()
    if u.endswith("F"):
        return round((val - 32) * 5 / 9, 2)
    if u == "K":
        return round(val - 273.15, 2)
    return val


def _cond_T(text: str) -> float | None:
    m = re.search(r"(?:at|@)\s*" + _NUM + r"\s*(°\s*[CF]|deg\s*[CF]|K\b)", text)
    return _temp_c(_f(m.group(1)), m.group(3)) if m else None


def _parse_prop(kind: str, text: str) -> dict | None:
    """Originaltext -> {"v": Zahl in der Zieleinheit, "u": Einheit, "T": °C?}; None, wenn nicht eindeutig lesbar."""
    t = text.replace("°", "°").replace("deg ", "°").replace("degrees", "°")
    if kind == "T":
        m = re.search(_NUM + r"(?:\s*(?:-|to|–)\s*" + _NUM + r")?\s*(°\s*[CF]|K\b)", t)
        if not m:
            return None
        u = m.group(5)
        lo = _temp_c(_f(m.group(1)), u)
        o = {"v": lo, "u": "°C"}
        if m.group(3):
            o["hi"] = _temp_c(_f(m.group(3)), u)
        pm = re.search(r"(?:at|@)\s*" + _NUM + r"\s*(mm\s*Hg|mmHg|kPa|atm|Pa|bar)", t[m.end():])
        if pm:
            o["p_Pa"] = _to_pa(_f(pm.group(1)), pm.group(3))
        return o
    if kind == "rho":
        m = re.search(r"Relative density.*?:\s*" + _NUM, t, re.I)
        if m:
            return {"v": _f(m.group(1)), "u": "1", "rel": "water=1"}
        m = re.search(_NUM + r"\s*(g/cu\s*cm|g/cm\s*3|g/cm³|g/cm\^3|g/mL|g/ml|kg/m3|kg/m³|g/L)", t)
        if not m:
            m2 = re.match(r"^\s*" + _NUM + r"(?:\s|$)", t)
            if m2 and 0.05 < _f(m2.group(1)) < 25:
                return {"v": _f(m2.group(1)), "u": "g/cm³", "assumed_unit": True, "T": _cond_T(t)}
            return None
        v, u = _f(m.group(1)), m.group(3).replace(" ", "").lower()
        v = v / 1000 if u.startswith("kg") or u == "g/l" else v
        return {"v": v, "u": "g/cm³", "T": _cond_T(t)}
    if kind == "p":
        m = re.search(_NUM + r"\s*(mm\s*Hg|mmHg|kPa|atm|Pa|bar|torr)", t, re.I)
        return {"v": _to_pa(_f(m.group(1)), m.group(3)), "u": "Pa", "T": _cond_T(t)} if m else None
    if kind == "pK":
        m = re.search(r"pKa\d?\s*(?:=|:|of)?\s*" + _NUM, t) or re.match(r"^\s*" + _NUM + r"\s*(?:\(|at|$)", t)
        return {"v": _f(m.group(1)), "u": "1", "T": _cond_T(t)} if m else None
    if kind in ("num", "rel"):
        m = re.search(r"(?:=|:)\s*" + _NUM, t) or re.match(r"^\s*" + _NUM, t)
        return {"v": _f(m.group(1)), "u": "1", "T": _cond_T(t)} if m else None
    if kind == "kH":
        m = re.search(_NUM + r"\s*atm[- ]?(?:cu\s*m|m3|m³)/mol", t)
        return {"v": _f(m.group(1)) * 101325, "u": "Pa·m³/mol", "T": _cond_T(t)} if m else None
    if kind == "eta":
        m = re.search(_NUM + r"\s*(cP|mPa[.·]?s|centipoise|Pa[.·]?s)", t, re.I)
        if not m:
            return None
        v = _f(m.group(1)) * (1000 if m.group(3).lower().startswith("pa") else 1)
        return {"v": v, "u": "mPa·s", "T": _cond_T(t)}
    if kind == "gamma":
        m = re.search(_NUM + r"\s*(dynes?/cm|mN/m)", t)
        return {"v": _f(m.group(1)), "u": "mN/m", "T": _cond_T(t)} if m else None
    if kind == "eV":
        m = re.search(_NUM + r"\s*eV", t)
        return {"v": _f(m.group(1)), "u": "eV"} if m else None
    if kind == "E":
        m = re.search(_NUM + r"\s*(kJ/mol|kcal/mol|J/mol|J/g|kJ/kg|cal/g|BTU/lb)", t)
        if not m:
            return None
        v, u = _f(m.group(1)), m.group(3)
        conv = {"kJ/mol": (1, "kJ/mol"), "kcal/mol": (4.184, "kJ/mol"), "J/mol": (0.001, "kJ/mol"),
                "J/g": (1, "kJ/kg"), "kJ/kg": (1, "kJ/kg"), "cal/g": (4.184, "kJ/kg"), "BTU/lb": (2.326, "kJ/kg")}[u]
        return {"v": round(v * conv[0], 6), "u": conv[1], "T": _cond_T(t)}
    return None


def _to_pa(v: float, unit: str) -> float:
    u = unit.replace(" ", "").lower()
    return round(v * {"mmhg": 133.322, "torr": 133.322, "kpa": 1000, "atm": 101325, "pa": 1, "bar": 1e5}[u], 6)


def _walk_info(sec: dict, out: dict):
    h = sec.get("TOCHeading")
    if h in PROP_HEADINGS and sec.get("Information"):
        out.setdefault(h, []).extend(sec["Information"])
    for s in sec.get("Section", []):
        _walk_info(s, out)


def build_pubchem(raw: Path) -> dict:
    """PubChem-Abruf (Namen -> CID -> Eigenschaften, Synonyme, PUG View) + Wikidata-Bezeichnungen -> molecules.json,
    physprops.json. Schlüssel ist der InChIKey."""
    sys.path.insert(0, str(HERE.parent))
    from smilesformula import SmilesError, equation_formula  # noqa: E402
    sys.path.insert(0, str(ROOT / "sdk" / "python"))
    from labcalc import chem as C  # noqa: E402
    d = raw / "pubchem"
    names = json.loads((d / "classes.json").read_text(encoding="utf-8"))
    cids = json.loads((d / "cids.json").read_text(encoding="utf-8"))
    props = json.loads((d / "props.json").read_text(encoding="utf-8"))
    syns = json.loads((d / "synonyms.json").read_text(encoding="utf-8"))
    wd = {}
    wp = raw / "wikidata" / "labels.json"
    if wp.exists():
        w = json.loads(wp.read_text(encoding="utf-8"))
        wd = {k: v[0] for k, v in w.get("by_inchikey", {}).items()}
        for cas, ik in w.get("cas_to_inchikey", {}).items():
            if ik and ik not in wd and w.get("by_cas", {}).get(cas):
                wd[ik] = w["by_cas"][cas][0]
    classes, cls_idx = [], {}
    mols, unresolved, fallback = {}, [], []
    for cls, name in names:
        if cls not in cls_idx:
            cls_idx[cls] = len(classes); classes.append(cls)
        cl = cids.get(name) or []
        name = name.split(" = ")[0].strip()          # „Anzeigename = PubChem-Suchname“
        if not cl:
            unresolved.append(name); continue
        p = props.get(str(cl[0]))
        if not p or not p.get("InChIKey"):
            unresolved.append(name); continue
        ik = p["InChIKey"]
        if ik in mols:
            if cls_idx[cls] not in mols[ik]["cls"]:
                mols[ik]["cls"].append(cls_idx[cls])
            if name.lower() != mols[ik]["en"].lower():
                mols[ik].setdefault("alias_en", []).append(name)
            continue
        smi = p.get("SMILES") or p.get("ConnectivitySMILES") or ""
        rec = {"cid": p["CID"], "en": name, "title": p.get("Title"), "iupac": p.get("IUPACName"),
               "hill": p.get("MolecularFormula"), "smiles": smi, "inchi": p.get("InChI"),
               "M_pubchem": float(p["MolecularWeight"]) if p.get("MolecularWeight") else None,
               "charge": p.get("Charge", 0), "cls": [cls_idx[cls]]}
        try:
            f, tot, q = equation_formula(smi)
            pc = C._formula_counts(re.sub(r"[+-]\d*$", "", p.get("MolecularFormula") or ""))
            if {k: int(v) for k, v in pc.items()} != tot:
                raise SmilesError("Abweichung zu PubChem")
            C.parse_species(f)
            rec["formula"] = f
        except (SmilesError, C.ChemError, ValueError, KeyError, IndexError) as e:
            mf = p.get("MolecularFormula") or ""
            try:
                C.parse_species(mf)
                rec["formula"] = mf
                fallback.append(f"{name}: {e}")
            except C.ChemError:
                rec["formula"] = None
                rec["kind"] = "polymer" if re.search(r"poly|nylon", name, re.I) else "mixture"
        cas = [s for s in syns.get(str(p["CID"]), []) if _cas_ok(s)]
        if cas:
            rec["cas"] = cas[0]
        clean = []
        for s in syns.get(str(p["CID"]), []):
            if len(s) > 60 or _SKIP_SYN.match(s) or s.lower() in (x.lower() for x in clean) or s.lower() == name.lower():
                continue
            clean.append(s)
            if len(clean) >= 15:
                break
        rec["syn"] = clean
        w = wd.get(ik)
        if w:
            rec["qid"] = w["qid"]
            if w.get("de"):
                rec["de"] = w["de"]
            if w.get("alt_de"):
                rec["syn_de"] = [a for a in w["alt_de"] if len(a) <= 60][:12]
        mols[ik] = rec
    # Polymere: Wiederholeinheit aus polymers.json, Formel gegen die SMILES geprüft ('*' = Verknüpfung, als H gezählt)
    from smilesformula import fragment_counts  # noqa: E402
    poly = json.loads((HERE.parent / "polymers.json").read_text(encoding="utf-8"))
    pcls = "Polymere | Polymers"
    if pcls not in cls_idx:
        cls_idx[pcls] = len(classes); classes.append(pcls)
    for p in poly["polymers"]:
        c, _ = fragment_counts(p["smiles"].replace("*", "[H]"))
        c["H"] = c.get("H", 0) - p["smiles"].count("*")
        want = {k: int(v) for k, v in C._formula_counts(p["ru"]).items()}
        if {k: v for k, v in c.items() if v} != want:
            raise SystemExit(f"Polymer {p['abbr']}: Wiederholeinheit {p['ru']} passt nicht zu SMILES ({c})")
        key = "poly:" + re.sub(r"[^A-Za-z0-9]+", "", p["abbr"]).lower()
        mols[key] = {"en": p["en"], "de": p["de"], "syn": [p["abbr"]], "smiles": p["smiles"], "formula": None,
                     "repeat_unit": p["ru"], "kind": "polymer", "cls": [cls_idx[pcls]], "source": poly["_source"]}
    # Physikalische Eigenschaften (PUG View, nur offene Quellen)
    phys, src_used, n_vals = {}, {}, 0
    by_cid = {m["cid"]: k for k, m in mols.items() if m.get("cid")}
    vp = d / "pugview.jsonl"
    for line in (vp.open(encoding="utf-8") if vp.exists() else []):
        row = json.loads(line)
        ik = by_cid.get(row["cid"])
        if not ik:
            continue
        refs = {r["ReferenceNumber"]: r for r in row["refs"]}
        info = {}
        for s in row["sections"]:
            _walk_info(s, info)
        rec = {}
        for h, items in info.items():
            key, kind = PROP_HEADINGS[h]
            vals, seen = [], set()
            for it in items:
                ref = refs.get(it.get("ReferenceNumber")) or {}
                src = OPEN_SOURCES.get(ref.get("SourceName"))
                if not src:
                    continue
                v = it.get("Value") or {}
                txt = " ".join(s.get("String", "") for s in v.get("StringWithMarkup", [])).strip()
                if not txt and v.get("Number"):
                    txt = f"{v['Number'][0]} {v.get('Unit', '')}".strip()
                if not txt or len(txt) > 300:
                    continue
                o = {"txt": txt[:200], "src": src[0]}
                if kind != "text":
                    pv = _parse_prop(kind, txt)
                    if pv:
                        o.update({k: x for k, x in pv.items() if x is not None})
                if it.get("Reference"):
                    o["ref"] = it["Reference"][0][:220]
                sig = (o.get("v"), o.get("u"), o["src"]) if "v" in o else (txt.lower(), o["src"])
                if sig in seen:
                    continue
                seen.add(sig)
                src_used[src[0]] = {"name": ref.get("SourceName"), "licence": src[1], "url": ref.get("LicenseURL")}
                vals.append(o)
            if vals:
                rec[key] = vals[:6 if kind != "text" else 3]
                n_vals += len(rec[key])
        if rec:
            phys[ik] = rec
    obj = _meta("pubchem", {"PUG REST": "https://pubchem.ncbi.nlm.nih.gov/rest/pug/",
                            "Auswahl": "modules/elementrechner/tools/compounds.txt",
                            **({"Wikidata": "https://query.wikidata.org/"} if wd else {})})
    obj.update({"_note": "Schlüssel InChIKey. formula: Gleichungsschreibweise aus den SMILES-Fragmenten (gegen die "
                         "PubChem-Summenformel geprüft); hill: PubChem-Summenformel; M_pubchem nur zur Kontrolle "
                         "(Rechnungen nutzen CIAAW). de/syn_de/qid: Wikidata (CC0).",
                "classes": classes, "molecules": mols})
    print(f"PubChem: {len(mols)} Stoffe, {len(unresolved)} Namen nicht aufgelöst, {len(fallback)} mit PubChem-Formel, "
          f"{sum(1 for m in mols.values() if m.get('de'))} mit deutschem Namen, "
          f"{sum(1 for m in mols.values() if not m.get('formula'))} ohne Formel")
    if unresolved:
        print("  nicht aufgelöst: " + "; ".join(unresolved))
    if fallback:
        print("  PubChem-Formel: " + "; ".join(fallback[:40]))
    _write(SDK_DATA / "molecules.json", obj)
    pobj = _meta("pubchem_view", {"PUG View": "https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/"})
    pobj.update({"_note": "Experimentelle Eigenschaften aus PubChem (PUG View), nur Quellen mit offenen Bedingungen. "
                          "v in der Zieleinheit u, T in °C, txt Originaltext, ref Primärquelle laut Datensammlung.",
                 "sources": src_used, "props": phys})
    print(f"Eigenschaften: {len(phys)} Stoffe, {n_vals} Werte")
    _write(SDK_DATA / "physprops.json", pobj)
    return obj


# ----------------------------------------------------------------------------- Verknüpfung mit der Sammlung
def _mol_index() -> dict:
    """InChI -> InChIKey und Name (klein) -> InChIKey aus der bereits gebauten Sammlung."""
    p = SDK_DATA / "molecules.json"
    if not p.exists():
        return {"inchi": {}, "name": {}}
    mols = json.loads(p.read_text(encoding="utf-8")).get("molecules", {})
    by_inchi, by_name = {}, {}
    for key, m in mols.items():
        if m.get("inchi"):
            by_inchi[m["inchi"]] = key
        for n in [m.get("en"), m.get("de"), m.get("iupac")] + m.get("syn", []) + m.get("syn_de", []):
            if n:
                by_name.setdefault(_norm_name(n), key)
    return {"inchi": by_inchi, "name": by_name}


def _norm_name(s: str) -> str:
    s = s.lower().replace("’", "'").replace("–", "-")
    return re.sub(r"\s+", " ", s).strip()


# ----------------------------------------------------------------------------- IUPAC pKa
def build_pka(raw: Path) -> dict:
    """IUPAC Digitized pKa Dataset (CC BY-NC 4.0) -> pka.json: Verbindungen (InChI, SMILES) und Messwerte."""
    import csv
    d = raw / "pka"
    idx = _mol_index()
    methods, refs = {}, {}
    for row in csv.DictReader(open(d / "method_translation.csv", encoding="utf-8")):
        methods[row["code"]] = {k: row[k + "_value"] for k in ("perrin", "perrin-supplement", "serjeant") if row.get(k + "_value")}
    for row in csv.DictReader(open(d / "reference_code_translation.csv", encoding="utf-8")):
        refs[row["code"]] = {k: row[c] for k, c in (("perrin", "perrin_source"), ("perrin_supp", "perrin_supp_source"),
                                                     ("serjeant", "serjeant_source")) if row.get(c)}
    comp, rows, used_m, used_r = {}, [], set(), set()
    src_key = {"perrin": "perrin", "perrin_supp": "perrin_supp", "serjeant": "serjeant"}
    for r in csv.DictReader(open(d / "iupac_high-confidence_v2_4.csv", encoding="utf-8")):
        try:
            val = float(r["pka_value"])
        except ValueError:
            continue
        cid = r["unique_ID"]
        if cid not in comp:
            names = [n.strip() for n in re.split(r";\s*", r.get("original_IUPAC_names") or "") if n.strip()]
            c = {"inchi": r["InChI"], "smiles": r["SMILES"], "names": names[:3]}
            key = idx["inchi"].get(r["InChI"])
            if key:
                c["key"] = key
            comp[cid] = c
        try:
            T = float(r["T"]) if r["T"] else None
        except ValueError:
            T = None
        src = src_key.get(r["source"], r["source"])
        rows.append([cid, r["pka_type"], val, T, r["assessment"] or None, r["method"] or None, r["ref"] or None, src,
                     r["cosolvent"] or None, (r["remarks"] or "")[:160] or None, r["acidity_label"] or None,
                     r["pressure"] or None])
        used_m.add(r["method"]); used_r.add(r["ref"])
    by_key = {}
    for cid, c in comp.items():
        if c.get("key"):
            by_key.setdefault(c["key"], []).append(cid)
    obj = _meta("iupac_pka", {"iupac_high-confidence_v2_4.csv": "https://doi.org/10.5281/zenodo.7236452"})
    obj.update({"_licence": "CC BY-NC 4.0", "_attribution": "Reproduced by permission of International Union of Pure and "
                "Applied Chemistry (IUPAC Digitized pKa Dataset)",
                "_note": "Zeilen: [Verbindung, pKa-Typ, Wert, T/°C, Bewertung, Methode, Literatur, Sammlung, Cosolvens, "
                         "Bemerkung, Säure-Label, Druck]. Sammlung: perrin = Perrin 1965/1972, perrin_supp = Perrin 1972 "
                         "Supplement, serjeant = Serjeant & Dempsey 1979.",
                "compounds": comp, "rows": rows, "by_key": by_key,
                "methods": {k: v for k, v in methods.items() if k in used_m},
                "refs": {k: v for k, v in refs.items() if k in used_r}})
    print(f"pKa: {len(comp)} Verbindungen, {len(rows)} Werte, {len(by_key)} mit der Sammlung verknüpft")
    _write(SDK_DATA / "pka.json", obj)
    return obj


# ----------------------------------------------------------------------------- NIST SRD 46
_TOSUB = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
_TOSUP = str.maketrans("0123456789+-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻")


def _html_chem(s: str) -> str:
    s = re.sub(r"<sub>(.*?)</sub>", lambda m: m.group(1).translate(_TOSUB), s or "")
    s = re.sub(r"<sup>(.*?)</sup>", lambda m: m.group(1).translate(_TOSUP), s)
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def _tsv(path: Path) -> list[list[str]]:
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip():
            out.append([None if c == r"\N" else c for c in line.split("\t")])
    return out


def _species_formula(name_html: str) -> tuple[str, int]:
    """'Fe<sup>2+</sup>' -> ('Fe', 2); 'UO<sub>2</sub><sup>2+</sup>' -> ('UO2', 2)."""
    m = re.search(r"<sup>(\d*)([+-])</sup>", name_html or "")
    q = (int(m.group(1) or 1) * (1 if m.group(2) == "+" else -1)) if m else 0
    f = re.sub(r"<sup>.*?</sup>", "", name_html or "")
    f = re.sub(r"</?sub>", "", f)
    return html.unescape(re.sub(r"<[^>]+>", "", f)).strip(), q


def _ligand_L(formula: str | None, figdef: str | None) -> tuple[str | None, int | None]:
    """SRD-Formel 'C2H4O2' mit Figur 'HL' -> Formel und Ladung der vollständig deprotonierten Form L."""
    if not formula or "*" in formula:
        return None, None
    f, _, qs = formula.partition("/")
    q = 0
    if qs:
        m = re.match(r"(\d*)([+-])", qs)
        q = int(m.group(1) or 1) * (1 if m.group(2) == "+" else -1) if m else 0
    fm = re.match(r"^(?:H(\d*))?L", figdef or "L")
    hn = int(fm.group(1) or 1) if fm and figdef and figdef.startswith("H") else 0
    counts = {}
    for el, n in re.findall(r"([A-Z][a-z]?)(\d*)", f):
        counts[el] = counts.get(el, 0) + int(n or 1)
    if hn:
        if counts.get("H", 0) < hn:
            return None, None
        counts["H"] -= hn
        if not counts["H"]:
            del counts["H"]
    return counts and "".join(f"{e}{n if n > 1 else ''}" for e, n in counts.items()), q - hn


_KSP_SOLID = re.compile(r"/(?:\[H\](?:<sup>\d+</sup>)?)?\[M(?:<sub>(\d+)</sub>)?L(?:<sub>(\d+)</sub>)?"
                        r"(?:\(H<sub>2</sub>O\)(?:<sub>(\d+)</sub>)?)?\(s\)\]$")
_KSP_PLAIN = re.compile(r"^\[M\](?:<sup>(\d+)</sup>)?\[L\](?:<sup>(\d+)</sup>)?/")


def build_srd46(raw: Path) -> dict:
    """NIST SRD 46 (Critically Selected Stability Constants of Metal Complexes, Version 8.0) -> stability.json."""
    sys.path.insert(0, str(ROOT / "sdk" / "python"))
    from labcalc import chem as C  # noqa: E402
    x = raw / "srd46" / "x"
    idx = _mol_index()
    ligs = {r[0]: r for r in _tsv(x / "liganden.txt")}
    metals = {r[0]: r for r in _tsv(x / "metal.txt")}
    defs = {r[0]: r[1] for r in _tsv(x / "beta_definition.txt")}
    foot = {r[0]: _html_chem(r[1]) for r in _tsv(x / "footnote.txt")}
    lit = {r[0]: r[1] for r in _tsv(x / "literature_alt.txt")}
    ctype = {"2": "H", "3": "K", "4": "S"}
    rows, used_l, used_m, used_d, used_f = [], set(), set(), set(), set()
    for r in _tsv(x / "verkn_ligand_metal.txt"):
        lid, mid, did, ct = r[1], r[2], r[3], r[4]
        lg = ligs.get(lid)
        if not lg or lg[6] == "59" or ct not in ctype:  # nicht ausgewählte Liganden, Typ "*"
            continue
        try:
            val = float(r[7])
        except (TypeError, ValueError):
            continue
        T = r[5]; I = r[6]
        # Unsicherheit "+/-3" bezieht sich auf die letzte Stelle des Werts (9.57 +/-5 -> ±0.05)
        em = re.match(r"^\+/-\s*(\d+)$", (r[9] or "").strip())
        dec = len(r[7].split(".")[1]) if "." in r[7] else 0
        err = round(int(em.group(1)) * 10 ** -dec, dec + 1) if em else None
        rows.append([lid, mid, did, ctype[ct], T, I, val, err,
                     r[10] if r[10] not in (None, "0") else None, (r[12] or "").strip() or None])
        used_l.add(lid); used_m.add(mid); used_d.add(did)
        if r[10] not in (None, "0"):
            used_f.add(r[10])
    pair_lit = {}
    for r in _tsv(x / "verkn_ligand_metal_literature.txt"):
        if r[1] in used_l and r[4] not in (None, "0") and r[4] in lit:
            pair_lit.setdefault(f"{r[1]}:{r[2]}", []).append(r[4])
    used_lit = {i for v in pair_lit.values() for i in v}
    L = {}
    for lid in used_l:
        lg = ligs[lid]
        lf, lq = _ligand_L(lg[2], lg[5])
        names = [n.strip() for n in re.split(r"\s*\(([^)]*)\)\s*$", lg[1] or "") if n and n.strip()]
        key = None
        for n in names + [re.sub(r"\s+ion$", "", names[0]) if names else ""]:
            key = key or idx["name"].get(_norm_name(n))
        L[lid] = {"name": lg[1], "formula": lg[2] if lg[2] and "*" not in lg[2] else None, "fig": lg[5],
                  "L": lf, "Lq": lq, "class": lg[6], **({"key": key} if key else {})}
    M = {}
    for mid in used_m:
        f, q = _species_formula(metals[mid][1])
        M[mid] = {"name": _html_chem(metals[mid][1]), "formula": f, "charge": q}
    # Löslichkeitsprodukte: Feststoff MaLb(H2O)n im Nenner -> Hill-Formel des wasserfreien Feststoffs.
    # Eintrag [Zeile, n(H2O), Standardform?]; Standardform = [M]^a[L]^b/[MaLb(s)], sonst gilt die Definition (z. B. Sulfide).
    ksp = {}
    for i, r in enumerate(rows):
        lid, mid, did, typ = r[0], r[1], r[2], r[3]
        dh = defs.get(did, "") or ""
        m = _KSP_SOLID.search(dh)
        if typ != "K" or not m or not L[lid]["L"] or M[mid]["formula"] == "H":
            continue
        a, b, nw = int(m.group(1) or 1), int(m.group(2) or 1), int(m.group(3) or (1 if "(H<sub>2</sub>O)" in dh else 0))
        if M[mid]["charge"] * a + (L[lid]["Lq"] or 0) * b != 0:
            continue
        p = _KSP_PLAIN.match(dh)
        plain = bool(p) and int(p.group(1) or 1) == a and int(p.group(2) or 1) == b and dh.count("[") == 3
        try:
            cm = C._formula_counts(M[mid]["formula"]); cl = C._formula_counts(L[lid]["L"])
        except C.ChemError:
            continue
        tot = {}
        for e, n in cm.items():
            tot[e] = tot.get(e, 0) + n * a
        for e, n in cl.items():
            tot[e] = tot.get(e, 0) + n * b
        ksp.setdefault(C._hill(tot), []).append([i, nw, plain])
    obj = _meta("srd46", {"SRD 46 SQL.zip": "https://data.nist.gov/od/id/mds2-2154"})
    obj.update({"_note": "Zeilen: [Ligand, Metall, Definition, Typ (K = lg K, H = ΔH/kJ mol⁻¹, S = ΔS/J K⁻¹ mol⁻¹), "
                         "T/°C, I/mol L⁻¹, Wert, Unsicherheit (absolut, aus '+/-n' der letzten Stelle), Fußnote, "
                         "Elektrolyt]. Nur ausgewählte Liganden (ohne Klasse 59 'not selected'). ksp: Hill-Formel des "
                         "wasserfreien Feststoffs -> [Zeile, Kristallwasser, Standardform [M]^a[L]^b/[MaLb(s)]?].",
                "ligands": L, "metals": M,
                "defs": {k: _html_chem(v) for k, v in defs.items() if k in used_d},
                "footnotes": {k: v for k, v in foot.items() if k in used_f},
                "rows": rows, "ksp": ksp, "pair_lit": pair_lit,
                "literature": {k: v for k, v in lit.items() if k in used_lit}})
    print(f"SRD 46: {len(rows)} Werte, {len(L)} Liganden ({sum(1 for v in L.values() if v.get('key'))} verknüpft), "
          f"{len(M)} Metalle, {len(ksp)} Feststoffe mit Ksp")
    _write(SDK_DATA / "stability.json", obj)
    return obj


def main(argv=None):
    argv = argv or sys.argv[1:]
    if not argv:
        print(__doc__)
        return 2
    raw = Path(argv[0])
    parts = set(argv[1:]) or {"ciaaw", "nuclides"}
    if parts & {"ciaaw", "nuclides"}:
        aw, by_el = build_ciaaw(raw)
        nuc = build_nuclides(raw, by_el)
        fill_mass_numbers(aw, nuc)
        _write(SDK_DATA / "atomic_weights.json", aw)
    if "pubchem" in parts:
        build_pubchem(raw)
    if "pka" in parts:
        build_pka(raw)
    if "srd46" in parts:
        build_srd46(raw)
    if "thermo" in parts:
        sys.path.insert(0, str(ROOT / "sdk" / "python"))
        sys.path.insert(0, str(HERE.parent))
        from build_thermo import build_thermo  # noqa: E402
        build_thermo(raw, SDK_DATA, _write)
    return 0


if __name__ == "__main__":
    sys.exit(main())
