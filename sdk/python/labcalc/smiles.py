"""Summenformel je Fragment aus SMILES (ohne RDKit), für die Gleichungsschreibweise der Sammlung.

Implizite Wasserstoffe nach den Standardvalenzen der SMILES-Spezifikation (OpenSMILES, „organic subset“):
B 3, C 4, N 3/5, O 2, P 3/5, S 2/4/6, F Cl Br I 1. Aromatische Bindungen zählen 1,5.
Das Ergebnis wird beim Bau gegen die Summenformel von PubChem geprüft; bei Abweichung gilt PubChem.
"""
from __future__ import annotations

import math
import re

VALENCE = {"B": (3,), "C": (4,), "N": (3, 5), "O": (2,), "P": (3, 5), "S": (2, 4, 6),
           "F": (1,), "Cl": (1,), "Br": (1,), "I": (1,)}
_ORG = re.compile(r"Cl|Br|[BCNOPSFI]|[bcnops]")
_BRACKET = re.compile(r"\[(\d*)(se|as|[A-Z][a-z]?|[bcnops])(@*)(?:(H)(\d*))?([+-]\d+|[+-]*)(?::\d+)?\]")
_BOND = {"-": 1, "=": 2, "#": 3, ":": 1.5, "$": 4, "/": 1, "\\": 1}


class SmilesError(ValueError):
    pass


def _charge(s: str) -> int:
    if not s:
        return 0
    if re.fullmatch(r"[+-]\d+", s):
        return int(s)
    return s.count("+") - s.count("-")


def fragment_counts(smi: str) -> tuple[dict, int]:
    """Elementzählung und Ladung eines Fragments (ohne '.')."""
    atoms, bonds = [], []          # atoms: [elem, aromatic, explicit H or None, charge]
    i, prev, stack, ring, pend = 0, None, [], {}, None
    while i < len(smi):
        ch = smi[i]
        if ch == "[":
            m = _BRACKET.match(smi, i)
            if not m:
                raise SmilesError("Klammeratom " + smi[i:i + 12])
            el = m.group(2)
            aro = el[0].islower()
            h = (int(m.group(5)) if m.group(5) else 1) if m.group(4) else 0
            lab = el.capitalize()
            if m.group(1):                                   # Isotop: [2H] -> D, [3H] -> T, [13C] -> ^13C
                lab = {("H", "2"): "D", ("H", "3"): "T"}.get((lab, m.group(1)), f"^{m.group(1)}{lab}")
            atoms.append([lab, aro, h, _charge(m.group(6))])
            i = m.end()
        elif _ORG.match(smi, i):
            el = _ORG.match(smi, i).group(0)
            atoms.append([el.capitalize(), el.islower(), None, 0])
            i += len(el)
        elif ch in _BOND:
            pend = _BOND[ch]; i += 1
            continue
        elif ch == "(":
            stack.append(prev); i += 1
            continue
        elif ch == ")":
            prev = stack.pop(); i += 1
            continue
        elif ch.isdigit() or ch == "%":
            num, i = (smi[i + 1:i + 3], i + 3) if ch == "%" else (ch, i + 1)
            if num in ring:
                j, o = ring.pop(num)
                order = pend or o or (1.5 if atoms[j][1] and atoms[prev][1] else 1)
                bonds[j] += order; bonds[prev] += order
            else:
                ring[num] = (prev, pend)
            pend = None
            continue
        else:
            raise SmilesError("Zeichen " + ch)
        bonds.append(0.0)
        cur = len(atoms) - 1
        if prev is not None:
            order = pend or (1.5 if atoms[prev][1] and atoms[cur][1] else 1)
            bonds[prev] += order; bonds[cur] += order
        prev, pend = cur, None
    if ring:
        raise SmilesError("offene Ringbindung")
    counts, q = {}, 0
    for (el, aro, h, c), b in zip(atoms, bonds):
        if h is None:
            used = math.floor(b + 0.5 + 1e-9) if aro else math.ceil(b - 1e-9)
            h = 0
            if aro:                                     # aromatisch: nur die niedrigste Valenz (s, n-R ohne H)
                h = max(0, VALENCE.get(el, (0,))[0] - used)
            else:
                for v in VALENCE.get(el, (0,)):
                    if v >= used:
                        h = v - used
                        break
        counts[el] = counts.get(el, 0) + 1
        if h:
            counts["H"] = counts.get("H", 0) + h
        q += c
    return counts, q


# Elektronegativität (Pauling) für die Reihenfolge anorganischer Formeln: elektropositiv zuerst (IUPAC Red Book IR-4.4.2.1)
EN = {"H": 2.20, "D": 2.20, "T": 2.20, "Li": 0.98, "Be": 1.57, "B": 2.04, "C": 2.55, "N": 3.04, "O": 3.44, "F": 3.98, "Na": 0.93, "Mg": 1.31,
      "Al": 1.61, "Si": 1.90, "P": 2.19, "S": 2.58, "Cl": 3.16, "K": 0.82, "Ca": 1.00, "Sc": 1.36, "Ti": 1.54, "V": 1.63,
      "Cr": 1.66, "Mn": 1.55, "Fe": 1.83, "Co": 1.88, "Ni": 1.91, "Cu": 1.90, "Zn": 1.65, "Ga": 1.81, "Ge": 2.01,
      "As": 2.18, "Se": 2.55, "Br": 2.96, "Rb": 0.82, "Sr": 0.95, "Y": 1.22, "Zr": 1.33, "Mo": 2.16, "Ru": 2.2,
      "Pd": 2.20, "Ag": 1.93, "Cd": 1.69, "Sn": 1.96, "Sb": 2.05, "Te": 2.1, "I": 2.66, "Xe": 2.6, "Cs": 0.79,
      "Ba": 0.89, "La": 1.10, "Ce": 1.12, "Hf": 1.3, "W": 2.36, "Os": 2.2, "Pt": 2.28, "Au": 2.54, "Hg": 2.00,
      "Tl": 1.62, "Pb": 2.33, "Bi": 2.02, "U": 1.38}
_H_FIRST = {"O", "F", "Cl", "Br", "I", "S", "Se", "Te"}


def base_element(lab: str) -> str:
    return {"D": "H", "T": "H"}.get(lab) or re.sub(r"^\^\d+", "", lab)


def ion_formula(counts: dict) -> str:
    """Organisch (C und H) nach Hill, sonst elektropositiv zuerst; NH4, OH, H2O als übliche Schreibweise.
    H steht vorn bei Säuren und Säureresten (HCl, H2SO4, HSO4), hinten bei Hydriden (NH3, NaH, SiH4).
    Isotope (D, T, ^13C) stehen an der Stelle ihres Elements: CDCl3, C2D6OS, D2O."""
    ks = set(counts)
    if ks == {"N", "H"} and counts["N"] == 1 and counts["H"] == 4:
        return "NH4"
    if ks == {"O", "H"} and counts["O"] == 1 and counts["H"] in (1, 2):
        return "OH" if counts["H"] == 1 else "H2O"
    hyd = [k for k in ("H", "D", "T") if k in ks]
    carb = [k for k in ks if base_element(k) == "C"]
    if carb and hyd:
        order = sorted(carb, key=len) + hyd + sorted(k for k in ks if k not in carb and k not in hyd)
    else:
        rest = sorted((k for k in ks if k != "H"), key=lambda k: (EN.get(k, 1.5), k))
        order = rest if "H" not in ks else (["H"] + rest if ks & _H_FIRST else rest + ["H"])
    return "".join(k + (str(counts[k]) if counts[k] != 1 else "") for k in order)


def _group(f: str, n: int) -> str:
    if n == 1:
        return f
    poly = len(re.findall(r"[A-Z]", f)) > 1 or bool(re.search(r"\d", f))
    return f"({f}){n}" if poly else f"{f}{n}"


def ions(smiles: str) -> tuple[list, int] | None:
    """Ionen eines Salzes je Formeleinheit: 'O.O.[O-]S(=O)(=O)[O-].[Ca+2]' -> ([('Ca^2+', 2, 1), ('SO4^2-', -2, 1)], 2).
    None, wenn die Verbindung nicht aus Ionen besteht (neutrale Fragmente ausser Wasser)."""
    frags, water = {}, 0
    for f in smiles.split("."):
        c, q = fragment_counts(f)
        fm = ion_formula(c)
        if q == 0:
            if fm == "H2O":
                water += 1
                continue
            return None
        frags[(fm, q)] = frags.get((fm, q), 0) + 1
    if not frags or sum(q * n for (_, q), n in frags.items()) != 0:
        return None
    g = 0
    for n in frags.values():
        g = math.gcd(g, n)
    out = [(f + "^" + (str(abs(q)) if abs(q) > 1 else "") + ("+" if q > 0 else "-"), q, n // g)
           for (f, q), n in sorted(frags.items(), key=lambda x: -x[0][1])]
    return out, (water // g if water % g == 0 else water / g)


def equation_formula(smiles: str) -> tuple[str, dict, int]:
    """'O.O.[O-]S(=O)(=O)[O-].[Cu+2]' -> ('CuSO4·2H2O', Gesamtzählung, Gesamtladung).
    Ionen werden zum neutralen Salz zusammengefasst, Wasser als Kristallwasser angehängt."""
    frags, total, qtot = {}, {}, 0
    for f in smiles.split("."):
        c, q = fragment_counts(f)
        key = (ion_formula(c), q)
        frags[key] = frags.get(key, 0) + 1
        for e, n in c.items():                              # Gesamtzählung ohne Isotope (wie PubChems Summenformel)
            e = base_element(e)
            total[e] = total.get(e, 0) + n
        qtot += q
    water = frags.pop(("H2O", 0), 0)
    cations = sorted(((k, n) for k, n in frags.items() if k[1] > 0), key=lambda x: x[0][0])
    anions = sorted(((k, n) for k, n in frags.items() if k[1] < 0), key=lambda x: x[0][0])
    neutral = [(k, n) for k, n in frags.items() if k[1] == 0]
    parts = []
    g = 1
    if cations or anions:
        if cations and anions and qtot == 0:
            g = 0
            for _, n in cations + anions:
                g = math.gcd(g, n)
            parts.append("".join(_group(f, n // g) for (f, _), n in cations) +
                         "".join(_group(f, n // g) for (f, _), n in anions))
        elif len(cations) + len(anions) == 1 and not neutral and not water:
            (f, q), n = (cations + anions)[0]
            if n > 1:
                raise SmilesError("mehrere gleiche Ionen")
            return f + f"^{abs(q) if abs(q) > 1 else ''}{'+' if q > 0 else '-'}", total, qtot
        else:
            raise SmilesError("geladenes Gemisch")
    def per_unit(n):
        # je Formeleinheit des Salzes: 2 CaSO4 · 1 H2O -> CaSO4·0.5H2O
        x = n / g
        return "" if x == 1 else (str(int(x)) if x == int(x) else f"{x:g}")
    for (f, _), n in neutral:
        parts.append((per_unit(n) if parts else (str(n) if n > 1 else "")) + f)
    s = "·".join(parts)
    if water:
        s = (s + "·" if s else "") + per_unit(water) + "H2O"
    return s, total, qtot
