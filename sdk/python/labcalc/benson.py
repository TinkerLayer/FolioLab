"""Benson-Gruppenadditivität (Gasphase, 298,15 K) mit den Gruppenwerten von Domalski & Hearing 1993.

Domalski, E. S.; Hearing, E. D.: Estimation of the Thermodynamic Properties of C-H-N-O-S-Halogen Compounds at
298.15 K. J. Phys. Chem. Ref. Data 22 (1993) 805-1159, doi:10.1063/1.555927 (Table 2, S. 816-819). Verfahren nach
Benson et al., Chem. Rev. 69 (1969) 279. Gruppenwerte und Belege je Gruppe in data/benson_groups.json.

  ΔfH°(g) = Σ nᵢ ΔfH°ᵢ + Korrekturen          Cp°(g) = Σ nᵢ Cp°ᵢ + Korrekturen
  S°(g)   = Σ nᵢ S°ᵢ + Korrekturen − R ln σ + R ln η   (σ Symmetriezahl gesamt, η Zahl der optischen Isomere)

Umfang: C/H- und C/H/O-Verbindungen ohne nicht-aromatische Ringe; Benzolringe (nicht kondensiert). Fehlt eine
Gruppe in der übernommenen Tabelle, wird mit BensonError abgelehnt (Joback bleibt dann die Schätzung).
σ wird aus dem Molekülgraphen bestimmt: Zahl der Graph-Automorphismen, die eigentlichen Drehungen entsprechen
(Parität an sp³-Zentren, cis/trans-Lage an C=C erhalten); das schliesst CH₃-Rotoren (3), C(CH₃)₃-Rotoren (3) und
den Phenyl-Flip (2) ein, wie in den Zusammensetzungen bei D&H (z. B. Toluol σ = 6, 2,2-Dimethylbutan σ = 243).
Alle Ergebnisse sind Schätzwerte; tabellierte Messwerte (Thermochemie) haben Vorrang.
"""
from __future__ import annotations

import math
import re
from functools import lru_cache

from . import chem as C
from .molgraph import Mol, terminal_O

REFS = ["domalski1993", "benson1969"]
METHOD = "Benson-Gruppenadditivität (Werte: Domalski & Hearing 1993)"
LIG_ORDER = ("H", "C", "Cd", "Ct", "CB", "CO", "O")
SRC_TXT = "Domalski & Hearing 1993, Table 2, S. {page}"


class BensonError(ValueError):
    pass


@lru_cache(maxsize=1)
def table() -> dict:
    d = C._json("benson_groups.json")
    if not d:
        raise BensonError("Benson nicht anwendbar: Gruppentabelle benson_groups.json fehlt")
    idx = {}
    for g in d["groups"]:
        idx[_key(g["center"], g["ligands"], g.get("variant"))] = g
    return {"meta": d["_meta"], "groups": idx, "corr": d["corrections"]}


def _key(center: str, ligands, variant=None) -> str:
    lig = sorted(ligands, key=LIG_ORDER.index)
    return center + "|" + ",".join(lig) + ("|" + variant if variant else "")


def _label(center: str, ligands) -> str:
    """D&H-ähnliche Schreibweise für eine (fehlende) Gruppe, z. B. C-(H)2(O)(CB)."""
    lig = sorted(ligands, key=LIG_ORDER.index)
    out, i = center + "-", 0
    while i < len(lig):
        j = i
        while j < len(lig) and lig[j] == lig[i]:
            j += 1
        out += f"({lig[i]})" + (str(j - i) if j - i > 1 else "")
        i = j
    return out


# ----------------------------------------------------------------------------- Atomtypen
def _benzene(m: Mol, a: int) -> bool:
    return m.benzene_atom[a]


def _ctype(m: Mol, j: int) -> str | None:
    """Ligandentyp eines Nachbaratoms nach Benson: C, Cd, Ct, CB, CO, O."""
    e = m.el[j]
    if e == "O":
        return "O"
    if e != "C":
        return None
    if terminal_O(m, j, 2):
        return "CO"
    if _benzene(m, j):
        return "CB"
    orders = [o for k, o in m.nbrs(j) if m.el[k] == "C"]
    if 3 in orders:
        return "Ct"
    if 2 in orders:
        return "Cd"
    return "C"


def _assign(m: Mol) -> tuple[list[tuple[str, dict]], list[str]]:
    """Gruppe je Zentralatom: Liste (Atom-Rolle, Gruppeneintrag). BensonError bei fehlender Gruppe."""
    T = table()["groups"]
    if any(m.q):
        raise BensonError("Benson nicht anwendbar: geladene Teilchen sind nicht vorgesehen")
    bad = sorted({e for e in m.el if e not in ("C", "O")})
    if bad:
        raise BensonError(f"Benson nicht anwendbar: Gruppen mit {', '.join(bad)} wurden nicht übernommen "
                          "(nur C/H- und C/H/O-Gruppen aus Domalski & Hearing 1993)")
    if not any(e == "C" for e in m.el):
        raise BensonError("Benson nicht anwendbar: keine Kohlenstoffgruppe")
    for sy in m.ring_systems:
        if sy["cyclo"] > 1:
            raise BensonError("Benson nicht anwendbar: kondensierte oder verbrückte Ringe – Gruppen CBF und "
                              "Ringkorrekturen wurden nicht übernommen")
    for a in range(m.n()):
        if m.ring_atom[a] and not m.benzene_atom[a]:
            raise BensonError("Benson nicht anwendbar: nicht-aromatischer Ring – Ringspannungskorrekturen (rsc) "
                              "wurden nicht übernommen")
    heavy_c = [a for a in range(m.n()) if m.el[a] == "C"]
    if len(heavy_c) == 1 and m.n() == 1:
        raise BensonError("Benson nicht anwendbar: Methan besteht aus nur einer Gruppe; D&H schliessen solche "
                          "Einzelgruppen-Moleküle von der Additivität aus")
    out, notes = [], []
    for a in range(m.n()):
        e, h = m.el[a], m.h[a]
        nb = m.nbrs(a)
        variant = None
        if e == "O":
            if any(o != 1 for _, o in nb):
                if len(nb) == 1 and nb[0][1] == 2 and m.el[nb[0][0]] == "C":
                    continue                                   # Carbonyl-O gehört zur CO-Gruppe
                raise BensonError("Benson nicht anwendbar: Sauerstoff in dieser Bindungsform nicht vorgesehen")
            center, lig = "O", [_ctype(m, j) for j, _ in nb] + ["H"] * h
        elif _benzene(m, a):
            ring = [j for j, o in nb if _benzene(m, j) and m.ring_bond[m.bond_index(a, j)]]
            other = [j for j, _ in nb if j not in ring]
            if len(ring) != 2 or len(other) + h != 1:
                raise BensonError("Benson nicht anwendbar: Aromat-Kohlenstoff ohne passende CB-Gruppe")
            center, lig = "CB", ["CB", "CB"] + ([_ctype(m, other[0])] if other else ["H"])
            if other and m.el[other[0]] == "C" and _ctype(m, other[0]) == "CB":
                raise BensonError("Benson nicht anwendbar: Gruppe CB-(CB)3 (Biphenyl-Typ) fehlt")
        elif terminal_O(m, a, 2):
            dO = terminal_O(m, a, 2)[0]
            rest = [j for j, _ in nb if j != dO]
            if any(o != 1 for j, o in nb if j != dO) or len(rest) + h != 2:
                raise BensonError("Benson nicht anwendbar: Carbonylgruppe dieser Art nicht vorgesehen")
            center, lig = "CO", [_ctype(m, j) for j in rest] + ["H"] * h
            if center == "CO" and h == 2:
                raise BensonError("Benson nicht anwendbar: Methanal ist bei D&H ein Einzelgruppen-Molekül")
        else:
            multi = [(j, o) for j, o in nb if o > 1]
            if any(o == 3 for _, o in multi):
                if len(multi) != 1 or m.el[multi[0][0]] != "C":
                    raise BensonError("Benson nicht anwendbar: Dreifachbindung dieser Art nicht vorgesehen")
                center, lig = "Ct", [_ctype(m, j) for j, o in nb if o == 1] + ["H"] * h
            elif multi:
                if len(multi) != 1 or m.el[multi[0][0]] != "C" or multi[0][1] != 2:
                    raise BensonError("Benson nicht anwendbar: kumulierte oder Hetero-Doppelbindung (z. B. Allen, "
                                      "Keten) nicht vorgesehen")
                center, lig = "Cd", [_ctype(m, j) for j, o in nb if o == 1] + ["H"] * h
            else:
                if h == 3 and len(nb) == 1:
                    out.append((a, T[_key("C", ["H", "H", "H", "C"])]))   # C-(H)3(X) = C-(H)3(C), D&H S. 807
                    continue
                center, lig = "C", [_ctype(m, j) for j, _ in nb] + ["H"] * h
                if "O" in lig and h <= 1:
                    o = next(j for j, _ in nb if m.el[j] == "O")
                    variant = "alc" if m.h[o] == 1 else "eth"
        if None in lig:
            raise BensonError("Benson nicht anwendbar: Nachbaratom ohne Benson-Typ")
        g = T.get(_key(center, lig, variant))
        if g is None:
            lab = _label(center, lig) + {"alc": " (Alkohol)", "eth": " (Ether/Ester)"}.get(variant, "")
            raise BensonError(f"Benson nicht anwendbar: Gruppe {lab} fehlt (nicht aus Domalski & Hearing 1993 "
                              "übernommen)")
        out.append((a, g))
    return out, notes


# ----------------------------------------------------------------------------- Korrekturen
def _methyl_corr(m: Mol) -> dict:
    """Methyl-Abstossungskorrekturen nach D&H Table 3 (S. 827)."""
    methyl = [a for a in range(m.n()) if m.el[a] == "C" and m.h[a] == 3 and m.deg(a) == 1]
    on = {}
    for a in methyl:
        x = m.nbrs(a)[0][0]
        on.setdefault(x, []).append(a)

    def sp3(x):
        return m.el[x] == "C" and all(o == 1 for _, o in m.nbrs(x)) and not m.benzene_atom[x]
    T = [x for x in on if sp3(x) and m.deg(x) == 3]
    Q = [x for x in on if sp3(x) and m.deg(x) == 4]
    out = {}

    def add(k, n):
        if n:
            out[k] = out.get(k, 0) + n
    for x, ms in on.items():
        n = len(ms)
        if sp3(x) and m.deg(x) in (3, 4):
            if len(Q) >= 2:
                add("CH3_quat_quat", n)
            elif Q and T:
                add("CH3_tert_quat", n)
            else:
                add("CH3_tertiary" if m.deg(x) == 3 else "CH3_quaternary", n)
        elif (m.el[x] == "C" and not m.benzene_atom[x] and not terminal_O(m, x, 2) and m.deg(x) == 3
              and any(o == 2 for _, o in m.nbrs(x))):
            add("CH3_tertiary", n)                        # Cd mit drei schweren Nachbarn (D&H: 2-Methylpropen)
    return out


def _bond_dirs(smi: str) -> dict:
    """Richtungsbindungen / und \\ zwischen Atomen in Schreibreihenfolge {(p, q): Zeichen}, p vor q."""
    org = re.compile(r"Cl|Br|[BCNOPSFI]|[bcnops]")
    res, i, idx, prev, stack, pend = {}, 0, -1, None, [], None
    while i < len(smi):
        ch = smi[i]
        if ch == "[":
            i = smi.index("]", i) + 1
        elif org.match(smi, i):
            i += len(org.match(smi, i).group(0))
        else:
            if ch in "/\\":
                pend = ch
            elif ch in "-=#$:":
                pend = None
            elif ch == "(":
                stack.append(prev)
            elif ch == ")":
                prev = stack.pop() if stack else prev
            elif ch == ".":
                prev, pend = None, None
            elif ch.isdigit():
                pend = None
            elif ch == "%":
                pend = None
                i += 2
            i += 1
            continue
        idx += 1
        if prev is not None and pend:
            res[(prev, idx)] = pend
        prev, pend = idx, None
    return res


def _cis_corr(m: Mol, notes: list) -> int:
    """Zahl der cis-Korrekturen; nur 1,2-disubstituierte C=C (D&H), E/Z aus / und \\ der SMILES."""
    dirs = None
    flip = {"/": "\\", "\\": "/"}
    n = 0
    for i, j, o in m.bonds:
        if o != 2 or m.el[i] != "C" or m.el[j] != "C" or m.benzene_atom[i] or m.benzene_atom[j]:
            continue
        a, b = min(i, j), max(i, j)
        sa = [k for k, _ in m.nbrs(a) if k != b]
        sb = [k for k, _ in m.nbrs(b) if k != a]
        if not sa or not sb:
            continue
        if len(sa) == 1 and len(sb) == 1:
            if any(_tbutyl(m, s) for s in (sa[0], sb[0])):
                raise BensonError("Benson nicht anwendbar: tert-Butyl an C=C (eigene cis-Korrektur bei D&H, nicht "
                                  "übernommen)")
            if dirs is None:
                dirs = _bond_dirs(m.smiles)
            x, y = sa[0], sb[0]
            da = dirs.get((x, a)) or (flip[dirs[(a, x)]] if (a, x) in dirs else None)
            db = dirs.get((b, y)) or (flip[dirs[(y, b)]] if (y, b) in dirs else None)
            if da is None or db is None:
                notes.append("E/Z einer 1,2-disubstituierten C=C-Bindung nicht angegeben: als E (trans) gerechnet; "
                             "das Z-Isomer liegt um die cis-Korrektur höher (ΔfH° +4,85 kJ/mol, D&H)")
            elif da != db:
                n += 1
            continue
        two = [s for s in (sa, sb) if len(s) == 2]
        if any(all(m.el[k] == "C" and m.h[k] == 3 and m.deg(k) == 1 for k in s) for s in two):
            continue                                       # =C(CH3)2: bei D&H ohne cis-Korrektur (2-Methyl-2-buten)
        raise BensonError("Benson nicht anwendbar: cis-Korrektur für diese drei- oder vierfach substituierte "
                          "C=C-Bindung bei D&H nicht eindeutig")
    return n


def _tbutyl(m: Mol, a: int) -> bool:
    return (m.el[a] == "C" and m.h[a] == 0 and all(o == 1 for _, o in m.nbrs(a))
            and sum(1 for k, _ in m.nbrs(a) if m.el[k] == "C" and m.h[k] == 3 and m.deg(k) == 1) == 3)


def _ring_corr(m: Mol) -> dict:
    """ortho/meta-Korrekturen je Substituentenpaar am Benzolring (D&H: o-/m-Xylol, Kresole, Methylanisole)."""
    out = {}
    for r in m.rings:
        if not r["benzene"]:
            continue
        cyc = r["atoms"]
        subs = {}
        for p, a in enumerate(cyc):
            ext = [j for j, _ in m.nbrs(a) if j not in cyc]
            if ext:
                j = ext[0]
                t = _ctype(m, j)
                if t in ("C", "Cd", "Ct"):
                    kind = "hc"
                elif t == "O":
                    kind = "OH" if m.h[j] == 1 else "OR"
                else:
                    kind = t
                subs[p] = kind
        ps = sorted(subs)
        for x in range(len(ps)):
            for y in range(x + 1, len(ps)):
                d = abs(ps[x] - ps[y])
                d = min(d, 6 - d)
                if d not in (1, 2):
                    continue
                pair = {subs[ps[x]], subs[ps[y]]}
                if not pair <= {"hc", "OH", "OR"} or pair == {"OH"} or pair == {"OH", "OR"}:
                    raise BensonError("Benson nicht anwendbar: ortho/meta-Korrektur für das Substituentenpaar "
                                      f"{'/'.join(sorted(pair))} nicht übernommen")
                k = "ortho" if d == 1 else "meta"
                out[k] = out.get(k, 0) + 1
    return out


# ----------------------------------------------------------------------------- Symmetrie
def _classes(m: Mol) -> list:
    lab = [(m.el[a], m.h[a], m.benzene_atom[a], tuple(sorted(o for _, o in m.nbrs(a)))) for a in range(m.n())]
    cls = {v: i for i, v in enumerate(sorted(set(lab)))}
    c = [cls[v] for v in lab]
    for _ in range(m.n()):
        sig = [(c[a], tuple(sorted((c[j], o) for j, o in m.nbrs(a)))) for a in range(m.n())]
        new = {v: i for i, v in enumerate(sorted(set(sig)))}
        c2 = [new[s] for s in sig]
        if len(set(c2)) == len(set(c)):
            return c2
        c = c2
    return c


def _automorphisms(m: Mol, limit: int = 200000) -> list[list[int]] | None:
    n = m.n()
    cls = _classes(m)
    order = sorted(range(n), key=lambda a: (sum(1 for x in cls if x == cls[a]), a))
    # BFS-ähnliche Reihenfolge: bevorzugt Atome mit bereits gesetzten Nachbarn
    seq, seen = [], set()
    for s in order:
        if s in seen:
            continue
        q = [s]
        seen.add(s)
        while q:
            a = q.pop(0)
            seq.append(a)
            for j, _ in sorted(m.nbrs(a), key=lambda t: order.index(t[0])):
                if j not in seen:
                    seen.add(j)
                    q.append(j)
    res, phi, used, budget = [], [-1] * n, [False] * n, [limit]

    def ok(a, b):
        for j, o in m.nbrs(a):
            if phi[j] >= 0 and m.order(b, phi[j]) != o:
                return False
        mapped = sum(1 for j, _ in m.nbrs(a) if phi[j] >= 0)
        return sum(1 for j, _ in m.nbrs(b) if used[j]) == mapped

    def rec(i):
        budget[0] -= 1
        if budget[0] < 0:
            raise OverflowError
        if i == n:
            res.append(phi[:])
            return
        a = seq[i]
        for b in range(n):
            if not used[b] and cls[b] == cls[a] and ok(a, b):
                phi[a], used[b] = b, True
                rec(i + 1)
                phi[a], used[b] = -1, False
    try:
        rec(0)
    except (OverflowError, RecursionError):
        return None
    return res


def _parity(perm: list[int]) -> int:
    p, seen = 0, [False] * len(perm)
    for i in range(len(perm)):
        if seen[i]:
            continue
        j, ln = i, 0
        while not seen[j]:
            seen[j] = True
            j = perm[j]
            ln += 1
        p += ln - 1
    return p % 2


def symmetry(m: Mol) -> dict:
    """Symmetriezahl σ (eigentliche Drehungen inkl. interner Rotoren) und Stereozentren aus dem Graphen."""
    auts = _automorphisms(m)
    if auts is None:
        return {"sigma": None, "stereocentres": None}
    sp3 = {a for a in range(m.n()) if m.el[a] == "C" and not m.benzene_atom[a] and all(o == 1 for _, o in m.nbrs(a))
           and m.deg(a) + m.h[a] == 4}
    dbl = [(min(i, j), max(i, j)) for i, j, o in m.bonds if o == 2 and m.el[i] == "C" and m.el[j] == "C"
           and not (m.benzene_atom[i] and m.benzene_atom[j])]
    in_dbl = {x for b in dbl for x in b}
    hvy = {a: sorted(j for j, _ in m.nbrs(a)) for a in range(m.n())}
    total = 0
    for phi in auts:
        w = 1
        for a in range(m.n()):
            h = m.h[a]
            if a in sp3:
                if h >= 2:
                    w *= math.factorial(h) // 2
                else:
                    tgt = hvy[phi[a]]
                    perm = [tgt.index(phi[j]) for j in hvy[a]]
                    if _parity(perm):
                        w = 0
                        break
            elif a not in in_dbl:
                w *= math.factorial(h)
        if not w:
            continue
        for a, b in dbl:
            free, sig = 0, []
            for end, other in ((a, b), (b, a)):
                slots = [j for j in hvy[end] if j != other]
                tgt_other = phi[other]
                tslots = [j for j in hvy[phi[end]] if j != tgt_other]
                if m.h[end] == 2:
                    free += 1
                    sig.append(None)
                elif len(slots) == 2:
                    sig.append(0 if phi[slots[0]] == tslots[0] else 1)
                else:
                    sig.append(0)
            if free == 2:
                w *= 2
            elif free == 0 and sig[0] != sig[1]:
                w = 0
                break
        total += w
    stereo = 0
    for a in sp3:
        if m.h[a] > 1:
            continue
        nb = hvy[a]
        if any(phi[a] == a and any(phi[j] != j for j in nb) for phi in auts):
            continue
        stereo += 1
    return {"sigma": total or None, "stereocentres": stereo}


# ----------------------------------------------------------------------------- Schätzung
def estimate(m: Mol) -> dict:
    """ΔfH°(g), S°(g), Cp°(g) bei 298,15 K nach Benson (D&H 1993). BensonError, wenn eine Gruppe fehlt."""
    tb = table()
    R = tb["meta"]["R"]
    assigned, notes = _assign(m)
    counts, order = {}, []
    for _, g in assigned:
        if g["label"] not in counts:
            order.append(g)
        counts[g["label"]] = counts.get(g["label"], 0) + 1
    corr = _methyl_corr(m)
    ncis = _cis_corr(m, notes)
    if ncis:
        corr["cis"] = ncis
    corr.update(_ring_corr(m))
    rows = [(g, counts[g["label"]]) for g in order] + [(tb["corr"][k], n) for k, n in corr.items()]
    out = {"method": "Benson", "method_long": METHOD, "refs": REFS, "values": {}, "notes": notes,
           "groups": [{"group": g["label"], "n": n, "source": SRC_TXT.format(page=g["page"]),
                       "values": {k: g.get(k) for k in ("dfH", "Cp", "S")}} for g, n in rows]}

    def total(k):
        miss = sorted({g["label"] for g, _ in rows if g.get(k) is None})
        if miss:
            return None, miss
        return sum(n * g[k] for g, n in rows), []
    H, mH = total("dfH")
    Cp, mC = total("Cp")
    S0, mS = total("S")
    sym = symmetry(m)
    sigma, k = sym["sigma"], sym["stereocentres"]
    eta = None
    s_note = ""
    if S0 is not None:
        if sigma is None or k is None:
            S0, s_note = None, "Symmetriezahl σ nicht bestimmbar (Molekül zu gross/symmetrisch)"
        elif k > 1:
            S0, s_note = None, "mehrere Stereozentren: σ und Zahl der optischen Isomere hängen vom Isomer ab"
        else:
            eta = 1 if (k == 0 or "@" in m.smiles) else 2
            S0 = S0 - R * math.log(sigma) + R * math.log(eta)
            s_note = f"σ = {sigma}, η = {eta}: S° = ΣS − R ln σ + R ln η"
            if k == 1 and eta == 1:
                s_note += " (Enantiomer angegeben, kein Mischungsterm)"
    out["sigma"], out["eta"] = sigma, eta
    lab = "Benson (D&H 1993)"

    def put(key, v, unit, label, miss, extra=""):
        note = extra
        if miss:
            note = "Gruppenwert fehlt in der Quelle bzw. im Scan nicht eindeutig: " + ", ".join(miss)
        out["values"][key] = {"v": None if miss else v, "u": unit, "label": f"{label} – {lab}", "note": note,
                              "method": "Benson"}
    put("dfH_g", H, "kJ/mol", "ΔfH°(g, 298 K)", mH, "Schätzwert, Gruppenadditivität")
    put("S_g", S0, "J/(mol·K)", "S°(g, 298 K)", mS, s_note)
    put("Cp_g", Cp, "J/(mol·K)", "Cp°(g, 298 K)", mC, "nur 298,15 K – die Quelle gibt keine Cp(T)-Werte")
    out["cp_poly"] = None
    out["notes"].append("Benson-Schätzung (Gruppenwerte Domalski & Hearing 1993); tabellierte Messwerte haben Vorrang. "
                        "Genauigkeit laut Quelle typisch ±4 kJ/mol (ΔfH°) bzw. ±4 J/(mol·K) (Cp°, S°), "
                        "Grenze des Annehmbaren ±8")
    return out
