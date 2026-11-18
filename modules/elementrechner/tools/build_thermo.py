"""Thermochemische Standarddaten bei 298,15 K und 1 bar -> labcalc/data/thermo.json.

Quellen (Rohdateien im Download-Ordner, nicht im Projekt):
  codata/key1.html                         CODATA Key Values (Cox, Wagman & Medvedev 1989): ΔfH°, S° mit Unsicherheit
  nbs/NBS_Tables_with_ErratumValues.csv    NBS-Tabellen (Wagman u. a. 1982, Erratum 1989), digitalisiert von NIST (2020)
  burcat/BURCAT.THR.txt                    Burcat/Ruscic-Datenbank (NASA-7-Polynome; ΔfH° z. T. aus ATcT)

Jeder Eintrag: Formel wie in der Quelle, Hill-Formel, Ladung, Phase (cr, l, g, aq, am, vit), ΔfH° [kJ/mol],
ΔfG° [kJ/mol], S° [J/(mol K)], Cp° [J/(mol K)], Quelle. Fehlt ΔfG°, wird es aus ΔfH° und S° berechnet
(ΔfG° = ΔfH° − T·ΔfS° mit den Entropien der Elemente im Referenzzustand, CODATA) und als berechnet markiert.
"""
from __future__ import annotations

import csv
import html
import json
import math
import re
from pathlib import Path

T0 = 298.15
R = 8.314462618e-3            # kJ/(mol K), CODATA 2022


def _chem():
    from labcalc import chem as C  # noqa: E402  (Pfad setzt build_data)
    return C


# Referenzzustand der Elemente bei 298,15 K, 1 bar (Formel, Phase in den Quellen, Atome je Formeleinheit)
REF_STATE = {"H": ("H2", "g", 2), "N": ("N2", "g", 2), "O": ("O2", "g", 2), "F": ("F2", "g", 2), "Cl": ("Cl2", "g", 2),
             "Br": ("Br2", "l", 2), "I": ("I2", "cr", 2), "He": ("He", "g", 1), "Ne": ("Ne", "g", 1), "Ar": ("Ar", "g", 1),
             "Kr": ("Kr", "g", 1), "Xe": ("Xe", "g", 1), "Rn": ("Rn", "g", 1), "Hg": ("Hg", "l", 1), "C": ("C", "cr", 1),
             "S": ("S", "cr", 1), "P": ("P", "cr", 1)}     # P: weisser Phosphor (NBS-Referenz), sonst Metalle/Feststoffe cr


def _num(s: str):
    s = (s or "").strip().replace("−", "-")
    if s in ("", "-", "–"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _hill(counts: dict) -> str:
    return _chem()._hill({k: int(v) if float(v).is_integer() else float(v) for k, v in counts.items()})


def _parse(formula: str):
    """'SO4^2-' -> (counts, charge, hill) oder None."""
    C = _chem()
    try:
        sp = C.parse_species(formula)
    except C.ChemError:
        return None
    if sp.kind != "chem" or not sp.counts:
        return None
    try:
        return sp.counts, sp.charge, _hill(sp.counts)             # Hill ohne Ladung; Ladung getrennt in q
    except (C.ChemError, ValueError):
        return None


# ----------------------------------------------------------------------------- CODATA Key Values
def read_codata(path: Path) -> list[dict]:
    h = path.read_text(encoding="latin-1")
    out = []
    for row in re.findall(r"<TR>(.*?)</TR>", h, re.S | re.I):
        cells = re.findall(r"<TD[^>]*>(.*?)</TD>", row, re.S | re.I)
        if len(cells) < 4:
            continue
        f = cells[0]
        f = re.sub(r"<SUP>\s*([^<]*?)\s*</SUP>", lambda m: "^" + m.group(1).strip(), f, flags=re.I)
        f = re.sub(r"<SUB>\s*([^<]*?)\s*</SUB>", lambda m: m.group(1).strip(), f, flags=re.I)
        f = re.sub(r"<[^>]+>", "", html.unescape(f)).strip().replace(" ", "")
        if not f or f.lower().startswith("substance"):
            continue
        m = re.fullmatch(r"(.+?)\^([+-])(\d*)", f)              # Al^+3 -> Al^3+
        if m:
            f = f"{m.group(1)}^{m.group(3)}{m.group(2)}" if m.group(3) not in ("", "1") else f"{m.group(1)}^{m.group(2)}"
        state = re.sub(r"<[^>]+>", "", html.unescape(cells[1])).strip()

        def vu(c):
            t = re.sub(r"<[^>]+>", "", html.unescape(c)).replace("±", " ± ").strip()
            p = [x.strip() for x in t.split("±")]
            return _num(p[0]), (_num(p[1]) if len(p) > 1 else None)
        H, uH = vu(cells[2])
        S, uS = vu(cells[3])
        ph, poly = (state.split(",", 1) + [""])[:2]
        out.append({"f": f, "ph": ph.strip(), "poly": poly.strip(), "H": H, "uH": uH if H else (0.0 if H == 0 else None),
                    "S": S, "uS": uS, "src": "codata"})
    return out


# ----------------------------------------------------------------------------- NBS-Tabellen
_NBS_STATE = {"cr": "cr", "l": "l", "g": "g", "ai": "aq", "ao": "aq", "aq": "aq", "am": "am", "vit": "vit"}


def read_nbs(path: Path) -> list[dict]:
    rows = list(csv.reader(open(path, encoding="utf-8-sig")))
    out = []
    table = ""
    for r in rows[2:]:
        if len(r) >= 1 and r[0].startswith("Table"):
            table = r[0].split(":")[-1].strip()
            continue
        if len(r) < 12 or not r[4].strip():
            continue                                             # Lösungen „in n H2O“ und Überschriften
        st = r[4].strip()
        base = re.sub(r"\d+$|\*$", "", st)
        if base not in _NBS_STATE:
            continue
        f = re.sub(r"<sup>([^<]*)</sup>", lambda m: "^" + m.group(1), r[0].strip())
        f = re.sub(r"<sub>([^<]*)</sub>", r"\1", f).replace(" ", "")
        fixed = ""
        # Digitalisierung: Elementsymbol der Tabelle in Grossbuchstaben (CO(IO3)2 = Co(IO3)2, CS2O = Cs2O)
        if len(table) == 2 and table.upper() in f and table not in f:
            f, fixed = f.replace(table.upper(), table), f"Formel korrigiert ({table.upper()} → {table})"
        name = (r[1] if not r[1].startswith("in ") else "") or r[2]
        desc = r[3].strip()
        out.append({"f": f, "ph": _NBS_STATE[base], "aqs": base if base in ("ai", "ao") else None,
                    "poly": " ".join(x for x in (name.strip() if st != base else "", desc) if x) or (st if st != base else ""),
                    "name": name.strip(), "H": _num(r[7]), "G": _num(r[8]), "S": _num(r[10]), "Cp": _num(r[11]),
                    "src": "nbs", "alt": st != base, "fix": fixed or None})
    return out


# ----------------------------------------------------------------------------- Burcat (NASA-7)
def read_burcat(path: Path) -> list[dict]:
    lines = path.read_text(encoding="latin-1").splitlines()
    out = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        if len(ln) >= 80 and ln[79] == "1" and i + 3 < len(lines) and lines[i + 1][79:80] == "2" \
                and lines[i + 2][79:80] == "3" and lines[i + 3][79:80] == "4":
            # Kommentarblock rückwärts bis zur Leerzeile: CAS, Name, HF298, ATcT-Wert
            j = i - 1
            com = []
            while j >= 0 and lines[j].strip() and not (len(lines[j]) >= 80 and lines[j][79:80] == "4"):
                com.insert(0, lines[j])
                j -= 1
            rec = _burcat_record(ln, lines[i + 1:i + 4], com)
            if rec:
                out.append(rec)
            i += 4
            continue
        i += 1
    return out


def _coefs(block):
    vals = []
    for ln, n in zip(block, (5, 5, 4)):
        vals += [float(ln[k * 15:(k + 1) * 15].replace("D", "E")) for k in range(n)]
    return vals                                                   # 14: hoch a1..a7, tief a1..a7


def _nasa(head: str, tlow: float, thigh: float, lo, hi, single: bool) -> dict:
    """{"T": [Tlow, Tmid, Thigh], "lo": a1..a7, "hi": a1..a7} bzw. ein Bereich {"T": [Tlow, Thigh], "lo": …}."""
    if single:
        return {"T": [tlow, thigh], "lo": list(lo if any(lo[:5]) else hi)}
    try:
        tmid = float(head[65:73])
    except ValueError:
        tmid = 1000.0
    return {"T": [tlow, tmid or 1000.0, thigh], "lo": list(lo), "hi": list(hi)}


def _burcat_record(head: str, block, com):
    name = head[:18].strip()
    els = {}
    for k in range(4):
        e, c = head[24 + 5 * k:26 + 5 * k].strip(), head[26 + 5 * k:29 + 5 * k].strip().rstrip(".")
        if e and c:
            try:
                n = float(c)
            except ValueError:
                return None
            if n:
                els[e.capitalize() if len(e) == 2 else e] = n
    phase = head[44].upper()
    try:
        tlow, thigh = float(head[45:55]), float(head[55:65])
        a = _coefs(block)
    except ValueError:
        return None
    hi, lo = a[:7], a[7:]
    use = lo if any(lo[:5]) else hi
    # Gültigkeit bei 298,15 K: ein Bereich (kondensierte Phasen) tlow..thigh, zwei Bereiche tlow..1000 K (Tmid)
    single = not any(hi[:5]) or not any(lo[:5])
    top = thigh if single else min(1000.0, thigh)
    if not (tlow - 1 <= T0 <= top + 1):
        return None
    q = -int(els.pop("E", 0))                                     # Elektronen: E -1 = Kation
    if any(e not in _chem()._SYMSET for e in els) or not els:
        return None
    t = T0
    cp = (use[0] + use[1] * t + use[2] * t ** 2 + use[3] * t ** 3 + use[4] * t ** 4) * R * 1000
    h = (use[0] + use[1] * t / 2 + use[2] * t ** 2 / 3 + use[3] * t ** 3 / 4 + use[4] * t ** 4 / 5 + use[5] / t) * R * t
    s = (use[0] * math.log(t) + use[1] * t + use[2] * t ** 2 / 2 + use[3] * t ** 3 / 3 + use[4] * t ** 4 / 4 + use[6]) * R * 1000
    text = " ".join(com)
    cas = [c for c in re.findall(r"\b\d{2,7}-\d\d-\d\b", com[0] if com else "")]
    atct = re.search(r"\{\s*HF298\s*=\s*(-?\d+(?:\.\d+)?)\.?\s*\+/-\s*(\d+(?:\.\d+)?)\.?\s*kJ\s*REF=ATcT\s*([A-Z]?)", text)
    hf = re.search(r"HF298\s*=\s*(-?\d+(?:\.\d+)?)\.?\s*(kJ|KJ|kcal)", text)
    tok = name.split()[0].split(",")[0]
    if phase == "G":
        ph = "g"
    elif re.search(r"\(L\)", name.split()[0], re.I):
        ph = "l"
    else:
        ph = "cr"
    rec = {"f": re.sub(r"\([A-Za-z]{1,3}\)$", "", tok), "name": name, "ph": ph, "H": round(h, 3),
           "S": round(s, 3), "Cp": round(cp, 3), "src": "burcat", "cas": cas, "counts": els, "q": q,
           # NASA-7 mit voller Stellenzahl (a5 ~ 1e-12 darf nicht gerundet werden) und beiden Bereichen (ER-701)
           "nasa": _nasa(head, tlow, thigh, lo, hi, single)}
    rec["poly"] = name[len(name.split()[0]):].strip() if " " in name else ""
    if atct:
        rec["H_atct"], rec["uH_atct"] = float(atct.group(1)), float(atct.group(2))
    elif hf and hf.group(2).lower() == "kj":
        rec["H_tab"] = float(hf.group(1))
    return rec


# ----------------------------------------------------------------------------- Zusammenführen
def build_thermo(raw: Path, sdk_data: Path, write) -> dict:
    C = _chem()
    cod = read_codata(raw / "codata" / "key1.html")
    nbs = read_nbs(raw / "nbs" / "NBS_Tables_with_ErratumValues.csv")
    bur = read_burcat(raw / "burcat" / "BURCAT.THR.txt")
    mols = json.loads((sdk_data / "molecules.json").read_text(encoding="utf-8")).get("molecules", {})
    by_cas, by_name, by_hill = {}, {}, {}
    for key, m in mols.items():
        if m.get("cas"):
            by_cas.setdefault(m["cas"], key)
        for n in [m.get("en"), m.get("de"), m.get("iupac")] + m.get("syn", [])[:5]:
            if n:
                by_name.setdefault(n.lower().strip(), key)
        f = m.get("formula")
        if f:
            p = _parse(f)
            if p and p[1] == 0:
                by_hill.setdefault(p[2], set()).add(key)

    # Entropie der Elemente im Referenzzustand (CODATA, sonst NBS) für ΔfG° = ΔfH° − T·ΔfS°
    refS = {}
    for src in (nbs, cod):                                       # CODATA zuletzt: überschreibt
        for e in src:
            if e["H"] == 0 and e.get("S") is not None and not e.get("alt"):
                p = _parse(e["f"])
                if not p or p[1] != 0 or len(p[0]) != 1:
                    continue
                el, n = next(iter(p[0].items()))
                rs = REF_STATE.get(el)
                if rs and (rs[0] != e["f"] or rs[1] != e["ph"]):
                    continue
                if not rs and e["ph"] != "cr":
                    continue
                refS[el] = e["S"] / float(n)
    s_h2 = refS["H"] * 2

    def dfG(counts, q, H, S):
        if H is None or S is None:
            return None
        try:
            dS = S - sum(refS[e] * float(n) for e, n in counts.items()) + q / 2 * s_h2   # Ionen: H+(aq)-Konvention
        except KeyError:
            return None
        return round(H - T0 * dS / 1000, 3)

    out, skipped, nfix = [], 0, [0]
    for e in cod + nbs + bur:
        if e["src"] == "burcat":
            counts, q = e.pop("counts"), e.pop("q")
            hill = _hill(counts)
            qs = ("^" + (str(abs(q)) if abs(q) > 1 else "") + ("+" if q > 0 else "-")) if q else ""
            f = e["f"].rstrip("+-") + qs
            p = _parse(f)
            # Burcat schreibt Elemente teils gross (CL, AL) oder mit Zusätzen: dann die Hill-Formel
            e["f"] = f if p and p[2] == hill and p[1] == q else hill + qs
        else:
            p = _parse(e["f"])
            if not p:
                skipped += 1
                continue
            counts, q, hill = p
        if e["H"] is None and e.get("G") is None:
            skipped += 1
            continue
        rec = {k: v for k, v in e.items() if v not in (None, "", []) and k != "alt"}
        rec["hill"], rec["q"] = hill, q
        if e["src"] == "burcat" and e.get("H_atct") is not None:
            rec["H_poly"], rec["H"], rec["uH"] = rec["H"], e["H_atct"], e["uH_atct"]
            rec.pop("H_atct"), rec.pop("uH_atct")
            rec["Hsrc"] = "atct"
        if rec.get("G") is not None and rec.get("H") is not None and rec.get("S") is not None and not rec.get("Gcalc"):
            # Prüfung ΔfG° = ΔfH° − T·ΔfS°; verschobenes Komma in H oder S (Digitalisierung) wird korrigiert,
            # wenn die Korrektur die Beziehung auf 0,5 kJ/mol erfüllt; sonst bleibt der Wert mit Hinweis.
            g0 = dfG(counts, q, rec["H"], rec["S"])
            if g0 is not None and abs(g0 - rec["G"]) > 2.0:
                fixed = None
                for k, fct in (("H", 10), ("H", 0.1), ("S", 10), ("S", 0.1)):
                    trial = dict(rec, **{k: rec[k] * fct})
                    g1 = dfG(counts, q, trial["H"], trial["S"])
                    if g1 is not None and abs(g1 - rec["G"]) < 0.5:
                        fixed = (k, rec[k], round(rec[k] * fct, 4))
                        break
                if fixed:
                    rec[fixed[0]] = fixed[2]
                    rec["fix"] = ((rec.get("fix") + "; ") if rec.get("fix") else "") + \
                        f"{'ΔfH°' if fixed[0] == 'H' else 'S°'} korrigiert ({fixed[1]} → {fixed[2]}, Komma verschoben; geprüft mit ΔfG° = ΔfH° − TΔfS°)"
                    nfix[0] += 1
                else:
                    rec["ghs"] = round(g0 - rec["G"], 1)
        if rec.get("G") is None:
            g = dfG(counts, q, rec.get("H"), rec.get("S"))
            if g is not None:
                rec["G"], rec["Gcalc"] = g, True
        # Verknüpfung mit der Sammlung: CAS (Burcat), Name, eindeutige Summenformel
        key = None
        for c in e.get("cas") or []:
            key = key or by_cas.get(c)
        if not key and e.get("name"):
            nm = re.sub(r"\s*\(.*$", "", e["name"]).lower().strip()
            key = by_name.get(nm)
        if not key and q == 0 and len(by_hill.get(hill, ())) == 1 and not re.search(r"[a-z]{3,}", e.get("name", "")):
            key = next(iter(by_hill[hill]))
        if key:
            rec["key"] = key
        rec.pop("cas", None)
        out.append(rec)

    # NBS-Formeln mit Isomeren: Schlüssel nur, wenn innerhalb der Quelle eindeutig
    seen = {}
    for r in out:
        if r.get("key") and r["src"] != "burcat":
            seen.setdefault((r["src"], r["hill"], r["q"]), set()).add(r["f"])
    for r in out:
        if r.get("key") and r["src"] != "burcat" and len(seen.get((r["src"], r["hill"], r["q"]), ())) > 1 \
                and not r.get("name"):
            r.pop("key")

    data = {"_source": "CODATA Key Values (Cox u. a. 1989); NBS-Tabellen (Wagman u. a. 1982, Erratum 1989; "
                       "digitalisiert NIST 2020); Burcat/Ruscic-Datenbank (Goos, Burcat & Ruscic, Stand 2018; ATcT-Werte)",
            "_note": "kJ/mol (ΔfH°, ΔfG°), J/(mol K) (S°, Cp°); 298,15 K, 1 bar. G mit Gcalc=true aus ΔfH° und S° berechnet. "
                     "aq-Ionen: Konvention ΔfH°, ΔfG°, S° von H⁺(aq) = 0.",
            "refS": refS, "species": out}
    write(sdk_data / "thermo.json", data)
    n = {s: sum(1 for r in out if r["src"] == s) for s in ("codata", "nbs", "burcat")}
    print(f"Thermo: {len(out)} Einträge (CODATA {n['codata']}, NBS {n['nbs']}, Burcat {n['burcat']}), "
          f"{sum(1 for r in out if r.get('key'))} mit der Sammlung verknüpft, {skipped} übersprungen, "
          f"{sum(1 for r in out if r.get('Gcalc'))} dfG berechnet, {nfix[0]} Kommafehler korrigiert, "
          f"{sum(1 for r in out if 'ghs' in r)} mit Abweichung G-H-S > 2 kJ/mol")
    return data
