"""Redoxchemie: Oxidationszahlen, Elektronenbilanz, Halbreaktionen, Ausgleich in saurer bzw. basischer Lösung,
Standardpotenziale aus Bildungsdaten, Nernst-Gleichung und Faraday-Gesetz.

Quellen
- Oxidationszahl nach der IUPAC-Definition (Karen et al. 2016): in der Ionenzerlegung gehen die Bindungselektronen an
  den elektronegativeren Partner; Elektronegativität nach Pauling aus dem PubChem-Periodensystem (Kim et al. 2021).
  Mit Struktur (SMILES der Sammlung) je Atom; ohne Struktur aus der Formel mit den üblichen Regeln (IUPAC Red Book
  2005: F −1, Alkali- und Erdalkalimetalle, H, O, dann nach Elektronegativität) – das ergibt die mittlere
  Oxidationszahl je Element.
- Standardpotenzial E° = −ΔrG°/(nF) und Nernst-Gleichung E = E° − RT/(nF)·ln Q (Bard & Faulkner 2001, Atkins 2018).
  ΔfG° kommt aus labcalc.thermo (CODATA Key Values, NBS-Tabellen, Burcat); Konvention der Tabellen: ΔfG°(H⁺, aq) = 0,
  dazu ΔfG°(e⁻) = 0, d. h. Potenziale gegen die Standardwasserstoffelektrode.
- F (exakt, N_A·e) und R: CODATA 2022.
"""
from __future__ import annotations

import math
import re
from fractions import Fraction

from . import chem as C

F = C.FARADAY                         # C/mol, exakt: F = N_A·e (SI 2019)
R = C.R_GAS
T0 = 298.15
REFS_OX = ["karen2016", "redbook2005", "pubchem_pt"]
REFS_E = ["bard", "atkins", "codata2022"]

G1 = {"Li", "Na", "K", "Rb", "Cs", "Fr"}
G2 = {"Be", "Mg", "Ca", "Sr", "Ba", "Ra"}
_METAL_BLOCKS = {"Alkali metal", "Alkaline earth metal", "Transition metal", "Post-transition metal", "Lanthanide",
                 "Actinide"}


class RedoxError(C.ChemError):
    pass


# ----------------------------------------------------------------------------- Elementdaten
def _elements() -> dict:
    return (C._json("elements.json") or {}).get("elements", {})


def en(sym: str) -> float | None:
    return (_elements().get(sym) or {}).get("electronegativity")


def common_states(sym: str) -> list[int]:
    return list((_elements().get(sym) or {}).get("oxidation_states") or [])


def is_metal(sym: str) -> bool:
    return (_elements().get(sym) or {}).get("group_block") in _METAL_BLOCKS


def _base(k: str) -> str:
    k = re.sub(r"^\d+", "", k)
    return "H" if k in ("D", "T") else k


def fstr(v) -> str:
    """Oxidationszahl als Text: +7, −2, 0, +8/3."""
    v = Fraction(v)
    if v == 0:
        return "0"
    s = "+" if v > 0 else "−"
    a = abs(v)
    return s + (str(a.numerator) if a.denominator == 1 else f"{a.numerator}/{a.denominator}")


def _merge(pairs) -> list[tuple[Fraction, Fraction]]:
    d = {}
    for v, n in pairs:
        d[Fraction(v)] = d.get(Fraction(v), Fraction(0)) + Fraction(n)
    return sorted(d.items())


# ----------------------------------------------------------------------------- Oxidationszahlen
def formula_ox(sp: C.Species) -> dict:
    """Mittlere Oxidationszahlen aus der Formel (Regeln nach dem IUPAC Red Book; Rest über die Ladungsbilanz)."""
    counts: dict[str, Fraction] = {}
    for k, v in sp.counts.items():
        b = _base(k)
        counts[b] = counts.get(b, Fraction(0)) + Fraction(v)
    q = Fraction(sp.charge)
    els = list(counts)
    if not els:
        return {"ok": False, "reason": "keine Atome"}
    if len(els) == 1:
        e = els[0]
        return {"ok": True, "method": "formula", "atoms": {e: [(q / counts[e], counts[e])]}, "rules": ["Element bzw. einatomiges Ion"]}
    assigned: dict[str, Fraction] = {}
    rules: list[str] = []

    def rem():
        return [e for e in els if e not in assigned]

    def fix(e, v, why):
        if e in counts and e not in assigned and len(rem()) > 1:
            assigned[e] = Fraction(v)
            rules.append(f"{e} {fstr(v)} ({why})")
    fix("F", -1, "Fluor")
    for e in els:
        if e in G1:
            fix(e, 1, "Alkalimetall")
        elif e in G2:
            fix(e, 2, "Erdalkalimetall")
    fix("Al", 3, "Aluminium")
    fix("Zn", 2, "Zink")
    if "H" in counts:
        others = [e for e in els if e != "H"]
        if others and all(is_metal(e) for e in others):
            fix("H", -1, "Hydrid, nur mit Metallen")
        else:
            fix("H", 1, "Wasserstoff mit Nichtmetall")
    fix("O", -2, "Sauerstoff")
    while len(rem()) > 1:
        cand = [e for e in rem() if en(e) is not None]
        if not cand:
            break
        e = max(cand, key=en)
        neg = [s for s in common_states(e) if s < 0]
        if not neg:
            break
        fix(e, min(neg), "elektronegativstes übriges Element, häufigste negative Stufe")
    r = rem()
    if len(r) != 1:
        return {"ok": False, "reason": "aus der Formel allein nicht bestimmbar (Struktur nötig)"}
    last = r[0]
    v = (q - sum(assigned[e] * counts[e] for e in assigned)) / counts[last]
    assigned[last] = v
    rules.append(f"{last} {fstr(v)} aus der Ladungsbilanz")
    st = common_states(last)
    lo, hi = (min(st + [0]), max(st + [0])) if st else (-4, 8)
    if not -5 <= v <= 9:
        return {"ok": False, "reason": f"Formelregeln ergeben für {last} {fstr(v)} – unmöglich; die Struktur wird gebraucht "
                                       "(z. B. Cyanid, Peroxid oder Metall-Metall-Bindung)"}
    out = {"ok": True, "method": "formula", "atoms": {e: [(assigned[e], counts[e])] for e in els}, "rules": rules}
    if not lo <= v <= hi:
        out["unusual"] = f"{last} {fstr(v)} liegt ausserhalb der üblichen Stufen ({', '.join(fstr(s) for s in sorted(st))})"
    return out


def structure_ox(smiles: str) -> dict:
    """Oxidationszahl je Atom aus der Struktur: Formalladung + Bindungselektronen an den elektronegativeren Partner."""
    from . import molgraph as G
    m = G.parse(smiles)
    ox = [Fraction(int(q)) for q in m.q]
    for a, b, o in m.bonds:
        ea, eb = en(m.el[a]), en(m.el[b])
        if ea is None or eb is None:
            return {"ok": False, "reason": f"keine Elektronegativität für {m.el[a] if ea is None else m.el[b]}"}
        o = Fraction(o).limit_denominator(2)
        if ea > eb:
            ox[a] -= o
            ox[b] += o
        elif eb > ea:
            ox[a] += o
            ox[b] -= o
    enh = en("H")
    hpairs = []
    for i, nh in enumerate(m.h):
        if not nh:
            continue
        e = en(m.el[i])
        if e is None:
            return {"ok": False, "reason": f"keine Elektronegativität für {m.el[i]}"}
        if e > enh:
            ox[i] -= nh
            hpairs.append((Fraction(1), nh))
        elif e < enh:
            ox[i] += nh
            hpairs.append((Fraction(-1), nh))
        else:
            hpairs.append((Fraction(0), nh))
    atoms: dict[str, list] = {}
    for i, e in enumerate(m.el):
        atoms.setdefault("H" if e in ("D", "T") else e, []).append((ox[i], 1))
    for p in hpairs:
        atoms.setdefault("H", []).append(p)
    return {"ok": True, "method": "structure", "atoms": {e: _merge(v) for e, v in atoms.items()}, "charge": m.charge(),
            "aromatic": any(o == 1.5 for _, _, o in m.bonds)}


def species_ox(sp: C.Species, smiles: str | None = None) -> dict:
    """Oxidationszahlen eines Stoffs; mit Struktur je Atom, sonst mittlere Werte aus der Formel."""
    if sp.kind != "chem":
        return {"ok": False, "reason": "kein chemischer Stoff"}
    if smiles:
        try:
            r = structure_ox(smiles)
        except Exception:  # noqa: BLE001 - unlesbare Struktur: Formelregeln
            r = {"ok": False}
        if r.get("ok"):
            want = {}
            for k, v in sp.counts.items():
                want[_base(k)] = want.get(_base(k), Fraction(0)) + Fraction(v)
            have = {e: sum(n for _, n in l) for e, l in r["atoms"].items()}
            if have == want and r["charge"] == sp.charge:
                if any(v.denominator != 1 for l in r["atoms"].values() for v, _ in l):
                    r["note"] = "gebrochene Werte: Mittel über die Grenzstrukturen (aromatische Bindungen)"
                return r
    return formula_ox(sp)


# ----------------------------------------------------------------------------- Elektronenbilanz
def _transfer(left, right):
    """Kleinste Elektronenverschiebung zwischen zwei Mengen von (Oxidationszahl, Anzahl): Paarung nach Grösse."""
    L = sorted([[Fraction(v), Fraction(n)] for v, n in left if n])
    Rr = sorted([[Fraction(v), Fraction(n)] for v, n in right if n])
    up = down = Fraction(0)
    i = j = 0
    while i < len(L) and j < len(Rr):
        a = min(L[i][1], Rr[j][1])
        d = Rr[j][0] - L[i][0]
        if d > 0:
            up += d * a
        else:
            down += -d * a
        L[i][1] -= a
        Rr[j][1] -= a
        if L[i][1] == 0:
            i += 1
        if Rr[j][1] == 0:
            j += 1
    return up, down


def _is_medium(sp: C.Species) -> bool:
    if sp.kind != "chem":
        return False
    return _plain(sp) in (("H2O", 0), ("H", 1), ("H3O", 1), ("HO", -1))


def _plain(sp: C.Species) -> tuple[str, int]:
    """(Hill-Formel ohne Ladung, Ladung) – z. B. ("HO", -1) für OH⁻."""
    c = {}
    for k, v in sp.counts.items():
        c[_base(k)] = c.get(_base(k), 0) + int(v) if Fraction(v).denominator == 1 else c.get(_base(k), 0)
    return C._hill(c), sp.charge


def analyse(eq: C.Equation, coefs, smiles: dict | None = None) -> dict:
    """Oxidationszahlen aller Stoffe, Elektronenbilanz je Element, Oxidations- und Reduktionsmittel."""
    smiles = smiles or {}
    if eq.nuclear:
        return {"redox": False, "skip": "Kerngleichung"}
    cf = [Fraction(str(c)) for c in coefs]
    species, left, right, e_coef, missing, contrib = [], {}, {}, Fraction(0), [], []
    for i, t in enumerate(eq.terms):
        sp = t.species
        if sp.kind == "electron":
            e_coef += cf[i] * t.side
            continue
        r = species_ox(sp, smiles.get(i) or smiles.get(str(i)))
        row = {"i": i, "species": sp.unicode(), "side": t.side}
        if not r.get("ok"):
            row["error"] = r.get("reason")
            missing.append(sp.unicode())
            species.append(row)
            continue
        row.update(method=r["method"], atoms=[{"el": e, "ox": fstr(v), "v": float(v), "n": float(n)}
                                              for e in sorted(r["atoms"], key=lambda x: C.Z_OF.get(x, 999))
                                              for v, n in r["atoms"][e]])
        for k in ("note", "unusual", "rules"):
            if r.get(k):
                row[k] = r[k]
        species.append(row)
        for e, pairs in r["atoms"].items():
            contrib.append((t.side, e, pairs, r["method"], cf[i]))
    out = {"species": species, "refs": REFS_OX}
    if missing:
        out.update(redox=None, error="Oxidationszahlen fehlen für " + ", ".join(missing))
        return out
    # Struktur (je Atom) und Formel (Mittelwert) nicht mischen: kommt ein Element in einem Stoff nur als Mittelwert vor,
    # wird es überall gemittelt – sonst erschiene CH₃COOH (Formel, C 0) → CH₃COO⁻ (Struktur, C −3/+3) als Redox.
    avg_el = {e for _, e, _, m, _ in contrib if m != "structure"}
    for side_s, e, pairs, m, c in contrib:
        side = left if side_s < 0 else right
        if e in avg_el and len(pairs) > 1:
            tot = sum(Fraction(n) for _, n in pairs)
            pairs = [(sum(Fraction(v) * Fraction(n) for v, n in pairs) / tot, tot)]
        for v, n in pairs:
            side.setdefault(e, []).append((v, n * c))
    changes, up_t, down_t = [], Fraction(0), Fraction(0)
    for e in sorted(set(left) | set(right), key=lambda x: C.Z_OF.get(x, 999)):
        up, down = _transfer(left.get(e, []), right.get(e, []))
        if up or down:
            changes.append({"el": e, "from": [fstr(v) for v, _ in _merge(left.get(e, []))],
                            "to": [fstr(v) for v, _ in _merge(right.get(e, []))], "up": float(up), "down": float(down)})
        up_t += up
        down_t += down
    out["changes"] = changes
    half = e_coef != 0
    if half:                                           # Halbreaktion mit Elektronen
        n = abs(e_coef)
        out.update(redox=True, half=True, n=float(n), n_frac=str(n),
                   kind="Oxidation" if e_coef > 0 else "Reduktion",       # e⁻ rechts: abgegeben
                   balanced=(down_t - up_t == -e_coef))
        return out
    if up_t != down_t:
        out.update(redox=None, error=f"Elektronenbilanz geht nicht auf (abgegeben {float(up_t):g}, aufgenommen "
                                     f"{float(down_t):g}); Gleichung oder Formeln prüfen")
        return out
    out["n"] = float(up_t)
    out["n_frac"] = str(up_t)
    out["redox"] = up_t > 0
    if not out["redox"]:
        return out
    ox_el = [c["el"] for c in changes if c["up"] > 0]
    red_el = [c["el"] for c in changes if c["down"] > 0]
    out["oxidized"], out["reduced"] = ox_el, red_el
    out["disproportionation"] = [c["el"] for c in changes if c["up"] and c["down"] and len(c["from"]) == 1]
    out["comproportionation"] = [c["el"] for c in changes if c["up"] and c["down"] and len(c["to"]) == 1]

    def agents(els, lower):
        res = []
        for s in species:
            if s["side"] > 0 or "atoms" not in s:
                continue
            for a in s["atoms"]:
                if a["el"] in els:
                    vals = [Fraction(v) for v, _ in _merge(right.get(a["el"], []))]
                    if vals and ((lower and Fraction(a["v"]).limit_denominator(12) > min(vals))
                                 or (not lower and Fraction(a["v"]).limit_denominator(12) < max(vals))):
                        res.append(s["i"])
                        break
        return res
    out["oxidant"] = agents(red_el, True)
    out["reductant"] = agents(ox_el, False)
    return out


# ----------------------------------------------------------------------------- freier Ausgleich
def _free_balance(fixed: list, free: list):
    """fixed: [(Species, Seite)], free: [Species] (Seite frei). Ergebnis [(Species, ganzzahliger Koeffizient mit
    Vorzeichen: < 0 Edukt, > 0 Produkt)] oder None, wenn nicht eindeutig bzw. Seiten widersprüchlich.
    Nicht eindeutig (z. B. H₂O₂ mit H₂O und H⁺): erneut mit weniger freien Stoffen, das letzte zuerst weg."""
    r = _free_balance1(fixed, free)
    if r is None and len(free) > 1:
        for k in range(len(free) - 1, 0, -1):
            r = _free_balance1(fixed, free[:k] + free[k + 1:])
            if r:
                return r
    return r


def _free_balance1(fixed: list, free: list):
    sps = [s for s, _ in fixed] + list(free)
    eq = C.Equation([C.Term(None, s, 1) for s in sps])
    _, M = C.conserved(eq)
    N = C.nullspace(M)
    if len(N) != 1:
        return None
    v = C._integerise(N[0])
    s0 = fixed[0][1]
    if (v[0] > 0) != (s0 > 0):
        v = [-x for x in v]
    for (s, side), x in zip(fixed, v):
        if x == 0 or (x > 0) != (side > 0):
            return None
    return [(sps[i], v[i]) for i in range(len(sps)) if v[i] != 0]


def _text(terms) -> str:
    def side(sign):
        parts = []
        for s, c in terms:
            if (c > 0) == (sign > 0):
                parts.append((f"{abs(c)} " if abs(c) != 1 else "") + s.text)
        return " + ".join(parts)
    return f"{side(-1)} -> {side(1)}"


def _uni(terms) -> str:
    def side(sign):
        return " + ".join((f"{abs(c)} " if abs(c) != 1 else "") + s.unicode() for s, c in terms if (c > 0) == (sign > 0))
    return f"{side(-1)} → {side(1)}"


def medium_species(medium: str) -> list:
    return [C.parse_species("H^+"), C.parse_species("H2O")] if medium == "acid" else \
        [C.parse_species("OH^-"), C.parse_species("H2O")]


def balance_in_medium(eq: C.Equation, medium: str) -> dict | None:
    """Ausgleich mit H⁺/H₂O (sauer) bzw. OH⁻/H₂O (basisch); vorhandene H⁺, OH⁻, H₂O werden neu verteilt."""
    if eq.nuclear:
        return None
    fixed = [(t.species, t.side) for t in eq.terms if not _is_medium(t.species)]
    if not fixed or any(s.kind not in ("chem", "electron") for s, _ in fixed):
        return None
    res = _free_balance(fixed, medium_species(medium))
    if not res:
        return None
    return {"medium": medium, "text": _text(res), "unicode": _uni(res)}


# ----------------------------------------------------------------------------- Ionenschreibweise
def _ion_text(counts: dict, q: int) -> str:
    """Formel eines Ions in üblicher Schreibweise: mit C nach Hill; sonst bei Anionen H zuerst (HSO₄⁻), dann nach
    steigender Elektronegativität (MnO₄⁻, Cr₂O₇²⁻); OH⁻; Kationen mit H zuletzt (NH₄⁺)."""
    if "C" in counts:
        body = C._hill(counts)
    elif set(counts) == {"O", "H"} and counts["O"] == 1:
        body = "OH" if counts["H"] == 1 else "H" + (str(counts["H"]) if counts["H"] > 1 else "") + "O"
    else:
        els = sorted((e for e in counts if e != "H"), key=lambda e: (en(e) or 9, e))
        if "H" in counts:
            els = els + ["H"] if q > 0 else ["H"] + els
        body = "".join(e + (str(counts[e]) if counts[e] > 1 else "") for e in els)
    if not q:
        return body
    return f"{body}^{abs(q) if abs(q) > 1 else ''}{'+' if q > 0 else '-'}"


def _dissolved_ions(sp: C.Species, smiles: str | None) -> list[tuple[C.Species, int]] | None:
    """Gelöster Stoff -> [(Ion, Anzahl)]; None, wenn er nicht in Ionen zerfällt (Moleküle, schwache Säuren, Metalle,
    Feststoffe/Gase mit Phasenangabe, schwer lösliche Salze mit Löslichkeitsprodukt)."""
    from . import acidbase as AB
    if sp.kind != "chem" or sp.charge or sp.phase in ("s", "cr", "l", "g"):
        return None
    plain = AB._plain_counts(sp.counts)
    hill = C._hill(plain)
    if hill in AB.STRONG_ACIDS or hill == "H2O4S":            # starke Säuren; H₂SO₄ wie üblich als 2 H⁺ + SO₄²⁻
        nH = 2 if hill == "H2O4S" else 1
        rest = dict(plain)
        rest["H"] -= nH
        if not rest["H"]:
            del rest["H"]
        return [(C.parse_species("H^+"), nH), (C.parse_species(_ion_text(rest, -nH)), 1)]
    frs = []
    if smiles:
        from . import molgraph as G
        try:
            g = G.parse(smiles)
            for fr in g.fragments():
                cnt = {}
                for i in fr:
                    cnt[g.el[i]] = cnt.get(g.el[i], 0) + 1
                    if g.h[i]:
                        cnt["H"] = cnt.get("H", 0) + g.h[i]
                frs.append((cnt, sum(g.q[i] for i in fr)))
        except Exception:  # noqa: BLE001 – unlesbare Struktur: nicht zerlegen
            frs = []
    if len(frs) < 2 or not all(q for _, q in frs):
        # Metallhalogenide (MnCl₂, FeCl₃; in der Sammlung oft kovalent als Cl[Fe]Cl): Mⁿ⁺ + n X⁻, wenn n eine übliche
        # Oxidationsstufe des Metalls ist
        frs = []
        hal = [e for e in plain if e in ("F", "Cl", "Br", "I")]
        met = [e for e in plain if e not in hal]
        if len(hal) == 1 and len(met) == 1 and is_metal(met[0]) and plain[hal[0]] % plain[met[0]] == 0:
            q = plain[hal[0]] // plain[met[0]]
            if q in common_states(met[0]):
                frs = [({met[0]: 1}, q)] * plain[met[0]] + [({hal[0]: 1}, -1)] * plain[hal[0]]
        if not frs:
            return None
    from . import substances as S
    sig = {}
    for cnt, q in frs:
        k = (tuple(sorted(cnt.items())), q)
        sig[k] = sig.get(k, 0) + 1
    if S.sparingly_soluble(sp.text, list(sig.values())):
        return None                                           # schwer löslich: bleibt als Feststoff stehen
    agg = {}
    cations = {next(iter(c)) for c, q in frs if q > 0 and len(c) == 1}
    for cnt, q in frs:
        t = _ion_text(cnt, q)
        if "C" in cnt and len(cations) == 1:
            # organisches Anion in der Schreibweise der Eingabe: CH3COONa -> CH3COO⁻ (statt C₂H₃O₂⁻)
            m = next(iter(cations))
            raw = re.sub(r"\((aq|s|l|g|cr)\)$", "", sp.text)
            body = re.sub(rf"^{m}\d*(?![a-z])|{m}\d*$", "", raw)
            try:
                if body and body != sp.text and AB._plain_counts(C.parse_species(body).counts) == cnt:
                    t = f"{body}^{abs(q) if abs(q) > 1 else ''}{'+' if q > 0 else '-'}"
            except C.ChemError:
                pass
        agg[t] = agg.get(t, 0) + 1
    out = []
    for t, n in agg.items():
        out.append((C.parse_species(t), n))
    # Plausibilität: Zerlegung muss die Formel ergeben (Hydrate u. Ä. nicht zerlegen)
    tot = {}
    for s, n in out:
        for e, k in AB._plain_counts(s.counts).items():
            tot[e] = tot.get(e, 0) + k * n
    return out if tot == plain else None


def ionic_form(eq: C.Equation, coefs, smiles: dict | None = None) -> dict | None:
    """Ionengleichung: gelöste Salze, starke Säuren und Basen in Ionen zerlegt, Zuschauerionen gekürzt
    (Atkins 2018, Kap. Reaktionen in Lösung). None, wenn sich nichts ändert."""
    smiles = smiles or {}
    net, rep, sides, split = {}, {}, {}, False
    for i, (t, c) in enumerate(zip(eq.terms, coefs)):
        sp = t.species
        if sp.kind != "chem":
            return None
        parts = _dissolved_ions(sp, smiles.get(i))
        if parts:
            split = True
        for s, n in parts or [(sp, 1)]:
            k = _plain(s)
            rep.setdefault(k, s)
            net[k] = net.get(k, Fraction(0)) + Fraction(str(c)) * n * t.side
            sides.setdefault(k, set()).add(t.side)
    if not split:
        return None
    spect = [rep[k].unicode() for k, ss in sides.items() if len(ss) == 2]
    terms = [(rep[k], v) for k, v in net.items() if v != 0]
    if not terms or all(v > 0 for _, v in terms) or all(v < 0 for _, v in terms):
        return {"empty": True, "spectators": spect,
                "note": "Nach dem Kürzen der Zuschauerionen bleibt keine Reaktion übrig."}
    den = math.lcm(*(v.denominator for _, v in terms))
    ints = [(s, int(v * den)) for s, v in terms]
    g = math.gcd(*(abs(v) for _, v in ints))
    ints = [(s, v // g) for s, v in ints]
    return {"text": _text(ints), "unicode": _uni(ints), "spectators": spect, "refs": ["atkins"]}


# ----------------------------------------------------------------------------- Potenziale
def _dG(terms) -> tuple[float | None, list, list]:
    """Σ ν ΔfG° (kJ/mol) über [(Species, ν mit Vorzeichen)]; Elektronen 0 (SHE-Konvention)."""
    from . import thermo as TH
    tot, rows, refs = 0.0, [], []
    for s, c in terms:
        if s.kind == "electron":
            rows.append({"species": "e⁻", "nu": c, "G": 0.0, "src": "SHE-Konvention"})
            continue
        try:
            d = TH.species_data(s)
        except C.ChemError as e:
            return None, rows + [{"species": s.unicode(), "error": str(e)}], refs
        g = d["entry"].get("G")
        if g is None:
            return None, rows + [{"species": s.unicode(), "error": "kein ΔfG°"}], refs
        tot += c * g
        rows.append({"species": s.unicode(), "nu": c, "G": g, "ph": d["entry"].get("ph"), "src": d["entry"]["src"]})
        refs += [k for k in TH.refs_of(d["entry"]) if k not in refs]
    return tot, rows, refs


def E_of_half(terms) -> dict:
    """E° des Redoxpaars (als Reduktion geschrieben) aus einer Halbreaktion [(Species, ν)]."""
    ne = sum(c for s, c in terms if s.kind == "electron")          # > 0: Elektronen rechts (Oxidation)
    if ne == 0:
        return {"error": "keine Elektronen in der Halbreaktion"}
    dG, rows, refs = _dG(terms)
    if dG is None:
        bad = next((r for r in rows if r.get("error")), None)
        return {"error": f"{bad['species']}: {bad['error']}" if bad else "Daten fehlen", "rows": rows}
    n = abs(ne)
    dG_red = -dG if ne > 0 else dG                                 # als Reduktion geschrieben
    E = -dG_red * 1000 / (n * F)
    return {"E0": E, "n": n, "dG_red": dG_red, "rows": rows, "refs": refs, "written": "Oxidation" if ne > 0 else "Reduktion"}


def couple_label(terms) -> str:
    """„MnO₄⁻/Mn²⁺“: oxidierte Form / reduzierte Form (ohne H⁺, OH⁻, H₂O, e⁻)."""
    ne = sum(c for s, c in terms if s.kind == "electron")
    main = [(s, c) for s, c in terms if s.kind == "chem" and not _is_medium(s)]
    lhs = [s.unicode() for s, c in main if c < 0]
    rhs = [s.unicode() for s, c in main if c > 0]
    for side, sign in ((lhs, -1), (rhs, 1)):           # O₂/H₂O: fehlt eine Form, steht Wasser bzw. OH⁻ dafür
        if not side:
            side += [s.unicode() for s, c in terms if s.kind == "chem" and (c > 0) == (sign > 0)
                     and _plain(s) in (("H2O", 0), ("HO", -1))] or \
                [s.unicode() for s, c in terms if s.kind == "chem" and (c > 0) == (sign > 0) and _plain(s) == ("H", 1)]
    ox, red = (rhs, lhs) if ne > 0 else (lhs, rhs)
    return f"{', '.join(ox) or '?'}/{', '.join(red) or '?'}"


def half_reactions(eq: C.Equation, coefs, res: dict) -> dict:
    """Oxidations- und Reduktionshalbreaktion aus der ausgeglichenen Gleichung (Ausgleich mit e⁻, H⁺/OH⁻, H₂O)."""
    if not res.get("redox") or res.get("half"):
        return {}
    medium = "base" if any(t.species.kind == "chem" and _plain(t.species) == ("HO", -1) for t in eq.terms) else "acid"
    out = {"medium": medium}
    ox_el, red_el = set(res["oxidized"]), set(res["reduced"])
    both = ox_el & red_el
    if both:
        out["note"] = ("Disproportionierung bzw. Komproportionierung von " + ", ".join(sorted(both))
                       + ": die Halbreaktionen sind nach Oxidationsstufe getrennt")
    sp_atoms = {s["i"]: s for s in res["species"]}
    vfr = lambda a: Fraction(a["v"]).limit_denominator(12)          # noqa: E731
    lo = {-1: {}, 1: {}}
    hi = {-1: {}, 1: {}}
    for s in res["species"]:
        for a in s.get("atoms", []):
            v = vfr(a)
            lo[s["side"]][a["el"]] = min(lo[s["side"]].get(a["el"], v), v)
            hi[s["side"]][a["el"]] = max(hi[s["side"]].get(a["el"], v), v)

    def terms_for(els, oxidation):
        """Stoffe einer Halbreaktion: das Element ändert von diesem Stoff aus in die passende Richtung.
        O(−2) und H(+1) zählen nicht – die liefert das Medium (H₂O, H⁺, OH⁻)."""
        fixed = []
        for i, t in enumerate(eq.terms):
            if t.species.kind != "chem" or _is_medium(t.species):
                continue
            rel = [(a["el"], vfr(a)) for a in (sp_atoms.get(i) or {}).get("atoms", [])
                   if a["el"] in els and not ((a["el"] == "O" and vfr(a) == -2) or (a["el"] == "H" and vfr(a) == 1))]
            other = -t.side
            ok = any((v < hi[other].get(e, v)) if oxidation == (t.side < 0) else (v > lo[other].get(e, v))
                     for e, v in rel)
            if ok:
                fixed.append((t.species, t.side))
        return fixed
    for key, els, oxid in (("oxidation", ox_el, True), ("reduction", red_el, False)):
        fixed = terms_for(els, oxid)
        if not fixed:
            continue
        r = _free_balance(fixed, [C.parse_species("e-")] + medium_species(medium))
        if not r:
            out[key] = {"error": "lässt sich nicht getrennt ausgleichen – meist hilft die Ionenschreibweise "
                                 "(z. B. MnO₄⁻ statt KMnO₄, Gegenionen weglassen)"}
            continue
        h = {"text": _text(r), "unicode": _uni(r), "couple": couple_label(r)}
        h.update({k: v for k, v in E_of_half(r).items() if k in ("E0", "n", "dG_red", "rows", "refs", "error")})
        out[key] = h
    o, rd = out.get("oxidation") or {}, out.get("reduction") or {}
    if o.get("E0") is not None and rd.get("E0") is not None:
        out["E0_cell_halves"] = rd["E0"] - o["E0"]
    return out


def potentials(res: dict, thermo: dict | None, T: float = T0) -> dict:
    """E° der Gesamtreaktion aus ΔrG° (E° = −ΔrG°/(nF)); bei anderer Temperatur genähert mit ΔrH°, ΔrS° konstant."""
    n = res.get("n")
    if not n or not thermo or thermo.get("dG") is None:
        return {}
    out = {"E0": -thermo["dG"] * 1000 / (n * F), "n": n, "refs": REFS_E}
    if abs(T - T0) > 0.01 and thermo.get("dH") is not None and thermo.get("dS") is not None:
        out["E_T"] = -(thermo["dH"] * 1000 - T * thermo["dS"]) / (n * F)
        out["T"] = T
    return out


def nernst(eq: C.Equation, coefs, E0: float, n: float, activities: dict | None = None, T: float = T0,
           pH: float | None = None) -> dict:
    """E = E° − RT/(nF)·ln Q. Aktivitäten je Stoff (Index); reine Flüssigkeiten/Feststoffe 1, H⁺/OH⁻ aus dem pH."""
    from .substances import PKW_25
    activities = activities or {}
    lnQ, used = 0.0, []
    for i, t in enumerate(eq.terms):
        sp = t.species
        if sp.kind != "chem":
            continue
        nu = float(Fraction(str(coefs[i]))) * t.side
        a, how = activities.get(str(i), activities.get(i)), "eingegeben"
        pl = _plain(sp)
        if sp.phase in ("s", "cr", "l") and a is None:
            a, how = 1.0, "rein (Feststoff/Flüssigkeit)"
        elif pl == ("H2O", 0) and a is None:
            a, how = 1.0, "Lösungsmittel Wasser"
        elif pH is not None and a is None and pl in (("H", 1), ("H3O", 1)):
            a, how = 10 ** -pH, f"aus pH {pH:g}"
        elif pH is not None and a is None and pl == ("HO", -1):
            a, how = 10 ** (pH - PKW_25), f"aus pH {pH:g} und pKw {PKW_25}"
        elif a is None:
            a, how = 1.0, "Standardzustand (1 mol/L bzw. 1 bar)"
        a = float(a)
        if a <= 0:
            raise RedoxError(f"Aktivität von {sp.unicode()} muss > 0 sein")
        lnQ += nu * math.log(a)
        used.append({"i": i, "species": sp.unicode(), "a": a, "how": how, "nu": nu})
    E = E0 - R * T / (n * F) * lnQ
    return {"E": E, "lnQ": lnQ, "lgQ": lnQ / math.log(10), "T": T, "used": used, "refs": REFS_E}


def _bal(q: str):
    eq = C.parse_equation(q)
    b = C.balance(eq)
    if b.get("status") not in ("ok", "given_ok"):
        raise RedoxError(b.get("reason") or "Gleichung nicht ausgleichbar")
    return eq, b["coefs"]


def calc_E0r(ctx, q):
    from . import thermo as TH
    eq, cf = _bal(C._str_arg(q, "E0r"))
    res = analyse(eq, cf)
    if res.get("half"):
        terms = [(t.species, Fraction(str(c)) * t.side) for t, c in zip(eq.terms, cf)]
        r = E_of_half([(s, float(c)) for s, c in terms])
        if r.get("E0") is None:
            raise RedoxError(r.get("error") or "E° nicht berechenbar")
        return r["E0"]
    if not res.get("redox"):
        raise RedoxError(res.get("error") or "keine Redoxreaktion (keine Elektronenübertragung)")
    th = TH.reaction(eq, cf)
    if th.get("dG") is None:
        raise RedoxError(th.get("error") or "ΔrG° nicht berechenbar")
    return -th["dG"] * 1000 / (res["n"] * F)


def calc_nred(ctx, q):
    eq, cf = _bal(C._str_arg(q, "ne"))
    res = analyse(eq, cf)
    if res.get("n") is None:
        raise RedoxError(res.get("error") or "Elektronenzahl nicht bestimmbar")
    return res["n"]


def calc_oxn(ctx, f, el):
    sp = C.parse_species(C._str_arg(f, "oxn"))
    r = species_ox(sp)
    if not r.get("ok"):
        raise RedoxError(r.get("reason"))
    pairs = r["atoms"].get(C._str_arg(el, "oxn"))
    if not pairs:
        raise RedoxError(f"{el} kommt in {f} nicht vor")
    return float(sum(v * n for v, n in pairs) / sum(n for _, n in pairs))


def register_calc_functions():
    from . import expr as E
    from . import units as U
    E.register_string_function("E0r", calc_E0r, 1, 1, U.kind_dims("voltage"),
                               'E0r("Zn + Cu^2+ -> Zn^2+ + Cu") – Standardpotenzial E° = −ΔrG°/(nF); Halbreaktion mit e⁻: '
                               'E° des Redoxpaars')
    E.register_string_function("ne", calc_nred, 1, 1, U.D0,
                               'ne("Zn + Cu^2+ -> Zn^2+ + Cu") – übertragene Elektronen n (ausgeglichene Gleichung)')
    E.register_string_function("oxn", calc_oxn, 2, 2, U.D0,
                               'oxn("MnO4^-", "Mn") – (mittlere) Oxidationszahl eines Elements')


def faraday(eq: C.Equation, coefs, n: float, Q: float | None = None, I: float | None = None,
            t: float | None = None, eta: float | None = None, actual: dict | None = None,
            analysis: dict | None = None) -> dict:
    """Faraday-Gesetz: Ladung Q (oder I·t) → Umsatz ξ = η·Q/(nF) und Stoffmengen bzw. Massen je Stoff.

    eta: Stromausbeute (Anteil 0 < η ≤ 1, Vorgabe 1). actual: {Index: tatsächliche Masse in g} → Ausbeute der
    Elektrolyse = m(tatsächlich)/m(theoretisch bei η = 1). analysis: Ergebnis von analyse() für Warnhinweise
    (mehrere oxidierte oder reduzierte Elemente: die Ladung muss nicht vollständig über diese Reaktion fliessen).
    """
    if Q is None:
        if I is None or t is None:
            raise RedoxError("Ladung Q oder Stromstärke I und Zeit t angeben")
        Q = float(I) * float(t)
    Q = float(Q)
    if Q <= 0:
        raise RedoxError("Ladung Q muss positiv sein")
    eta = 1.0 if eta is None else float(eta)
    if not 0 < eta <= 1:
        raise RedoxError("Stromausbeute muss zwischen 0 und 100 % liegen")
    xi0 = Q / (n * F)                                    # theoretisch (η = 1)
    xi = eta * xi0
    rows = []
    for i, term in enumerate(eq.terms):
        sp = term.species
        if sp.kind != "chem":
            continue
        nu = float(Fraction(str(coefs[i])))
        r = {"i": i, "species": sp.unicode(), "side": term.side, "n_mol": nu * xi}
        try:
            M = C.molar_mass(sp)["M"]
            r["m_g"] = nu * xi * M
            r["m0_g"] = nu * xi0 * M
            if actual and actual.get(i) not in (None, "") and float(actual[i]) >= 0:
                r["m_actual_g"] = float(actual[i])
                r["yield"] = float(actual[i]) / r["m0_g"]
        except C.ChemError:
            pass
        rows.append(r)
    warnings = []
    if analysis:
        ox, red = set(analysis.get("oxidized") or []), set(analysis.get("reduced") or [])
        if len(ox) > 1 or len(red) > 1:
            warnings.append("Mehrere Elemente werden oxidiert oder reduziert; an einer Elektrode können mehrere "
                            "Paare umgesetzt werden. Faraday gilt hier nur, wenn die gesamte Ladung über diese "
                            "Gleichung fliesst.")
        if analysis.get("disproportionation") or analysis.get("comproportionation"):
            warnings.append("Dis- oder Komproportionierung: die Elektronenzahl hängt von der gewählten "
                            "Halbreaktion ab; n bezieht sich auf die Gleichung wie geschrieben.")
    return {"Q": Q, "n_e": Q / F, "eta": eta, "xi": xi, "xi0": xi0, "rows": rows, "warnings": warnings,
            "refs": ["codata2022", "bard"]}
