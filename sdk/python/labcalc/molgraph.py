"""Molekülgraph aus SMILES (ohne RDKit) für den Moleküldesigner: Atome, Bindungen, Wasserstoffe, Ringe, Gruppen.

Gelesen wird OpenSMILES (organic subset, Klammeratome mit Isotop, Wasserstoffzahl, Ladung, Chiralität; Ringschlüsse
auch %nn; Verzweigungen; '.' trennt Fragmente). Aromatische Bindungen zählen 1,5. Implizite Wasserstoffe wie in
smiles.py nach den Standardvalenzen. Stereoangaben (@, /, \\) werden gelesen und nur als „vorhanden“ vermerkt.

Ringe: Bindungen in Zyklen (Brücken-Test nach Tarjan), Ringsysteme als Zusammenhangskomponenten der Ringbindungen;
ein System mit zyklomatischer Zahl 1 ist ein einfacher Ring. Benzolringe werden aromatisch (Kleinbuchstaben) wie
kekulé (alternierende Doppelbindungen) erkannt.
"""
from __future__ import annotations

import math
import re

from .smiles import VALENCE, SmilesError

_ORG = re.compile(r"Cl|Br|[BCNOPSFI]|[bcnops]")
_BRACKET = re.compile(r"\[(\d*)(se|as|[A-Z][a-z]?|[bcnops]|\*)(@@?(?:TH|AL|SP|TB|OH)?\d*)?(?:(H)(\d*))?"
                      r"([+-]\d+|[+-]*)(?::\d+)?\]")
_BOND = {"-": 1, "=": 2, "#": 3, "$": 4, ":": 1.5, "/": 1, "\\": 1}
HALOGENS = ("F", "Cl", "Br", "I")


def _charge(s: str) -> int:
    if not s:
        return 0
    if re.fullmatch(r"[+-]\d+", s):
        return int(s)
    return s.count("+") - s.count("-")


class Mol:
    """Atome (el, aro, q, iso, h) und Bindungen (a, b, Ordnung 1/2/3/1,5)."""

    def __init__(self):
        self.el: list[str] = []
        self.aro: list[bool] = []
        self.q: list[int] = []
        self.iso: list[int | None] = []
        self.hx: list[int | None] = []
        self.h: list[int] = []
        self.bonds: list[tuple[int, int, float]] = []
        self.adj: list[list[tuple[int, int]]] = []          # je Atom: (Nachbar, Bindungsindex)
        self.stereo = False
        self.smiles = ""

    # ------------------------------------------------------------------ Aufbau
    def _add_atom(self, el, aro, q=0, iso=None, hx=None):
        self.el.append(el)
        self.aro.append(aro)
        self.q.append(q)
        self.iso.append(iso)
        self.hx.append(hx)
        self.adj.append([])
        return len(self.el) - 1

    def _add_bond(self, a, b, order):
        if a == b or any(n == b for n, _ in self.adj[a]):
            raise SmilesError("doppelte Bindung zwischen denselben Atomen")
        self.bonds.append((a, b, order))
        k = len(self.bonds) - 1
        self.adj[a].append((b, k))
        self.adj[b].append((a, k))

    # ------------------------------------------------------------------ Abfragen
    def n(self) -> int:
        return len(self.el)

    def nbrs(self, i: int) -> list[tuple[int, float]]:
        return [(j, self.bonds[k][2]) for j, k in self.adj[i]]

    def order(self, i: int, j: int) -> float:
        for n, k in self.adj[i]:
            if n == j:
                return self.bonds[k][2]
        return 0

    def bond_index(self, i: int, j: int) -> int | None:
        for n, k in self.adj[i]:
            if n == j:
                return k
        return None

    def deg(self, i: int) -> int:
        return len(self.adj[i])

    def counts(self) -> dict:
        c = {}
        for i, e in enumerate(self.el):
            lab = e if not self.iso[i] else {("H", 2): "D", ("H", 3): "T"}.get((e, self.iso[i]), f"^{self.iso[i]}{e}")
            c[lab] = c.get(lab, 0) + 1
            if self.h[i]:
                c["H"] = c.get("H", 0) + self.h[i]
        return c

    def element_counts(self) -> dict:
        c = {}
        for i, e in enumerate(self.el):
            c[e] = c.get(e, 0) + 1
            if self.h[i]:
                c["H"] = c.get("H", 0) + self.h[i]
        return c

    def charge(self) -> int:
        return sum(self.q)

    def fragments(self) -> list[list[int]]:
        seen, out = set(), []
        for s in range(self.n()):
            if s in seen:
                continue
            comp, stack = [], [s]
            seen.add(s)
            while stack:
                i = stack.pop()
                comp.append(i)
                for j, _ in self.adj[i]:
                    if j not in seen:
                        seen.add(j)
                        stack.append(j)
            out.append(sorted(comp))
        return out


def parse(smi: str) -> Mol:
    smi = (smi or "").strip().split()[0] if (smi or "").strip() else ""
    if not smi:
        raise SmilesError("leere Struktur")
    m = Mol()
    m.smiles = smi
    i, prev, stack, ring, pend = 0, None, [], {}, None
    while i < len(smi):
        ch = smi[i]
        if ch == "[":
            g = _BRACKET.match(smi, i)
            if not g:
                raise SmilesError("Klammeratom " + smi[i:i + 12])
            el = g.group(2)
            if el == "*":
                raise SmilesError("Platzhalteratom * wird nicht unterstützt")
            hx = (int(g.group(5)) if g.group(5) else 1) if g.group(4) else 0
            if g.group(3):
                m.stereo = True
            cur = m._add_atom(el.capitalize() if el[0].islower() else el, el[0].islower(), _charge(g.group(6)),
                              int(g.group(1)) if g.group(1) else None, hx)
            i = g.end()
        elif _ORG.match(smi, i):
            el = _ORG.match(smi, i).group(0)
            cur = m._add_atom(el.capitalize(), el.islower())
            i += len(el)
        elif ch in _BOND:
            if ch in "/\\":
                m.stereo = True
            pend = _BOND[ch]
            i += 1
            continue
        elif ch == "(":
            stack.append(prev)
            i += 1
            continue
        elif ch == ")":
            if not stack:
                raise SmilesError("Klammer ) ohne (")
            prev = stack.pop()
            i += 1
            continue
        elif ch == ".":
            prev, pend = None, None
            i += 1
            continue
        elif ch.isdigit() or ch == "%":
            num, i = (smi[i + 1:i + 3], i + 3) if ch == "%" else (ch, i + 1)
            if prev is None:
                raise SmilesError("Ringschluss ohne Atom")
            if num in ring:
                j, o = ring.pop(num)
                order = pend or o or (1.5 if m.aro[j] and m.aro[prev] else 1)
                m._add_bond(j, prev, order)
            else:
                ring[num] = (prev, pend)
            pend = None
            continue
        else:
            raise SmilesError("Zeichen " + ch)
        if prev is not None:
            order = pend or (1.5 if m.aro[prev] and m.aro[cur] else 1)
            m._add_bond(prev, cur, order)
        prev, pend = cur, None
    if ring:
        raise SmilesError("offene Ringbindung")
    if stack:
        raise SmilesError("Klammer ( nicht geschlossen")
    for a in range(m.n()):
        if m.hx[a] is not None:
            m.h.append(m.hx[a])
            continue
        b = sum(o for _, o in m.nbrs(a))
        used = math.floor(b + 0.5 + 1e-9) if m.aro[a] else math.ceil(b - 1e-9)
        h = 0
        if m.aro[a]:                                    # aromatisch: nur die niedrigste Valenz (s, n-R ohne H)
            h = max(0, VALENCE.get(m.el[a], (0,))[0] - used)
        else:
            for v in VALENCE.get(m.el[a], (0,)):
                if v >= used:
                    h = v - used
                    break
        m.h.append(h)
    _rings(m)
    return m


# ----------------------------------------------------------------------------- Ringe
def _rings(m: Mol):
    n = m.n()
    disc, low, t = [-1] * n, [0] * n, [0]
    bridge = [False] * len(m.bonds)

    def dfs(root):                                      # iterativ (keine Rekursionsgrenze)
        stack = [(root, -1, iter(m.adj[root]))]
        disc[root] = low[root] = t[0]
        t[0] += 1
        while stack:
            v, pk, it = stack[-1]
            adv = False
            for w, k in it:
                if k == pk:
                    continue
                if disc[w] == -1:
                    disc[w] = low[w] = t[0]
                    t[0] += 1
                    stack.append((w, k, iter(m.adj[w])))
                    adv = True
                    break
                low[v] = min(low[v], disc[w])
            if not adv:
                stack.pop()
                if stack:
                    u = stack[-1][0]
                    low[u] = min(low[u], low[v])
                    if low[v] > disc[u]:
                        bridge[pk] = True
    for s in range(n):
        if disc[s] == -1:
            dfs(s)
    m.ring_bond = [not b for b in bridge]
    m.ring_atom = [any(m.ring_bond[k] for _, k in m.adj[i]) for i in range(n)]
    # Ringsysteme
    seen, systems = set(), []
    for s in range(n):
        if not m.ring_atom[s] or s in seen:
            continue
        atoms, bnds, stack = set(), set(), [s]
        seen.add(s)
        while stack:
            i = stack.pop()
            atoms.add(i)
            for j, k in m.adj[i]:
                if m.ring_bond[k]:
                    bnds.add(k)
                    if j not in seen:
                        seen.add(j)
                        stack.append(j)
        systems.append({"atoms": sorted(atoms), "bonds": sorted(bnds), "cyclo": len(bnds) - len(atoms) + 1})
    m.ring_systems = systems
    m.rings = []                                        # einfache Ringe als geordnete Atomfolge
    for sy in systems:
        if sy["cyclo"] != 1:
            continue
        atoms = set(sy["atoms"])
        cyc, prev, cur = [sy["atoms"][0]], None, sy["atoms"][0]
        while True:
            nxt = next(j for j, k in m.adj[cur] if j in atoms and m.ring_bond[k] and j != prev and (len(cyc) < 2 or j != cyc[-2]))
            if nxt == cyc[0]:
                break
            cyc.append(nxt)
            prev, cur = cur, nxt
        m.rings.append({"atoms": cyc, "benzene": _is_benzene(m, cyc)})
    m.benzene_atom = [False] * n
    for r in m.rings:
        if r["benzene"]:
            for a in r["atoms"]:
                m.benzene_atom[a] = True


def _is_benzene(m: Mol, cyc: list[int]) -> bool:
    if len(cyc) != 6 or any(m.el[a] != "C" or m.q[a] for a in cyc):
        return False
    orders = [m.order(cyc[i], cyc[(i + 1) % 6]) for i in range(6)]
    if all(o == 1.5 for o in orders):
        return True
    return sorted(orders) == [1, 1, 1, 2, 2, 2] and all(orders[i] != orders[(i + 1) % 6] for i in range(6))


def aromatic_atom(m: Mol, i: int) -> bool:
    """Atom in einem aromatischen Ring (Kleinbuchstabe in SMILES oder kekulé-Benzol)."""
    return m.aro[i] or m.benzene_atom[i]


# ----------------------------------------------------------------------------- Kennzahlen
def hill(counts: dict) -> str:
    keys = list(counts)
    if "C" in counts:
        order = ["C"] + (["H"] if "H" in counts else []) + sorted(k for k in keys if k not in ("C", "H"))
    else:
        order = sorted(keys)
    return "".join(k + (str(counts[k]) if counts[k] != 1 else "") for k in order if counts[k])


def dbe(counts: dict) -> float | None:
    """Doppelbindungsäquivalente C − H/2 + N/2 + 1 (Halogene wie H; nur C, H, N, O, S, Halogene, Si, P)."""
    if "C" not in counts or any(k not in ("C", "H", "N", "O", "S", "F", "Cl", "Br", "I", "Si", "P") for k in counts):
        return None
    c = counts.get("C", 0) + counts.get("Si", 0)
    h = counts.get("H", 0) + sum(counts.get(x, 0) for x in HALOGENS)
    nn = counts.get("N", 0) + counts.get("P", 0)
    return c - h / 2 + nn / 2 + 1


def terminal_O(m: Mol, c: int, order: float = 2) -> list[int]:
    """Endständige O-Atome mit gegebener Bindungsordnung an Atom c."""
    return [j for j, o in m.nbrs(c) if m.el[j] == "O" and o == order and m.deg(j) == 1 and m.q[j] == 0]


# ----------------------------------------------------------------------------- funktionelle Gruppen (Anzeige)
GROUP_NAMES = {
    "acid": ("Carbonsäure", "carboxylic acid"), "ester": ("Ester", "ester"), "lactone": ("Lacton", "lactone"),
    "anhydride": ("Carbonsäureanhydrid", "anhydride"), "acyl_halide": ("Carbonsäurehalogenid", "acyl halide"),
    "amide": ("Amid", "amide"), "nitrile": ("Nitril", "nitrile"), "aldehyde": ("Aldehyd", "aldehyde"),
    "ketone": ("Keton", "ketone"), "alcohol": ("Alkohol", "alcohol"), "phenol": ("Phenol", "phenol"),
    "enol": ("Enol", "enol"), "amine1": ("primäres Amin", "primary amine"), "amine2": ("sekundäres Amin", "secondary amine"),
    "amine3": ("tertiäres Amin", "tertiary amine"), "arylamine": ("aromatisches Amin", "aromatic amine"),
    "imine": ("Imin", "imine"), "nitro": ("Nitrogruppe", "nitro group"), "ether": ("Ether", "ether"),
    "epoxide": ("Epoxid", "epoxide"), "peroxide": ("Peroxid", "peroxide"), "halide": ("Halogenalkan", "alkyl halide"),
    "arylhalide": ("Halogenaren", "aryl halide"), "alkene": ("Alken (C=C)", "alkene (C=C)"),
    "alkyne": ("Alkin (C≡C)", "alkyne (C≡C)"), "arene": ("Benzolring", "benzene ring"),
    "heteroarene": ("aromatischer Heterocyclus", "aromatic heterocycle"), "thiol": ("Thiol", "thiol"),
    "sulfide": ("Sulfid (Thioether)", "sulfide"), "disulfide": ("Disulfid", "disulfide"),
    "sulfonic": ("Sulfonsäure", "sulfonic acid"), "carbonate": ("Carbonat (Ester)", "carbonate ester"),
    "urea": ("Harnstoff-Gruppe", "urea"), "carbamate": ("Carbamat", "carbamate"), "azo": ("Azogruppe", "azo group"),
    "phosphate": ("Phosphorsäureester", "phosphate ester"),
}


def functional_groups(m: Mol) -> list[dict]:
    """Funktionelle Gruppen mit Anzahl (Anzeige und Reaktionshinweise)."""
    found = {}

    def add(t, n=1):
        found[t] = found.get(t, 0) + n
    used_O, used_N = set(), set()
    for c in range(m.n()):
        if m.el[c] != "C":
            continue
        dO = terminal_O(m, c, 2)
        if not dO:
            if any(m.el[j] == "N" and o == 3 and m.deg(j) == 1 for j, o in m.nbrs(c)):
                add("nitrile")
                used_N.update(j for j, o in m.nbrs(c) if m.el[j] == "N" and o == 3)
            continue
        used_O.add(dO[0])
        others = [(j, o) for j, o in m.nbrs(c) if j != dO[0]]
        os_ = [j for j, o in others if m.el[j] == "O" and o == 1]
        ns_ = [j for j, o in others if m.el[j] == "N" and o == 1]
        hal = [j for j, o in others if m.el[j] in HALOGENS]
        if len(os_) == 2:
            add("carbonate")
            used_O.update(os_)
        elif os_ and ns_:
            add("carbamate")
            used_O.update(os_)
            used_N.update(ns_)
        elif len(ns_) == 2:
            add("urea")
            used_N.update(ns_)
        elif os_:
            o = os_[0]
            used_O.add(o)
            if m.h[o] == 1 or m.q[o] == -1:
                add("acid")
            else:
                other = next(j for j, _ in m.nbrs(o) if j != c)
                if m.el[other] == "C" and terminal_O(m, other, 2):
                    add("anhydride")
                elif m.ring_bond[m.bond_index(c, o)]:
                    add("lactone")
                else:
                    add("ester")
        elif ns_:
            add("amide")
            used_N.update(ns_)
        elif hal:
            add("acyl_halide")
        else:
            nc = sum(1 for j, _ in others if m.el[j] == "C")
            add("aldehyde" if m.h[c] >= 1 and nc <= 1 else "ketone")
    for a in range(m.n()):
        e = m.el[a]
        if e == "O" and a not in used_O:
            nb = m.nbrs(a)
            if len(nb) == 1 and nb[0][1] == 1 and m.el[nb[0][0]] == "C" and (m.h[a] == 1):
                c = nb[0][0]
                if aromatic_atom(m, c):
                    add("phenol")
                elif any(o == 2 for _, o in m.nbrs(c)):
                    add("enol")
                else:
                    add("alcohol")
            elif len(nb) == 2 and all(o == 1 for _, o in nb):
                els = [m.el[j] for j, _ in nb]
                if "O" in els:
                    add("peroxide")
                elif els == ["C", "C"]:
                    if m.ring_atom[a] and any(len(r["atoms"]) == 3 and a in r["atoms"] for r in m.rings):
                        add("epoxide")
                    elif not m.aro[a]:
                        add("ether")
        elif e == "N" and a not in used_N:
            nb = m.nbrs(a)
            oO = [j for j, o in nb if m.el[j] == "O"]
            if len(oO) >= 2:
                add("nitro")
                continue
            if m.aro[a]:
                continue
            if any(o == 2 and m.el[j] == "N" for j, o in nb):
                add("azo")
            elif any(o == 2 and m.el[j] == "C" for j, o in nb):
                add("imine")
            elif all(o == 1 for _, o in nb) and m.q[a] == 0 and all(m.el[j] in ("C", "H") for j, _ in nb):
                nc = len(nb)
                if any(aromatic_atom(m, j) for j, _ in nb):
                    add("arylamine")
                elif nc in (1, 2, 3):
                    add("amine" + str(nc))
        elif e in HALOGENS:
            nb = m.nbrs(a)
            if nb and m.el[nb[0][0]] == "C":
                add("arylhalide" if aromatic_atom(m, nb[0][0]) else "halide")
        elif e == "S":
            nb = m.nbrs(a)
            dO = [j for j, o in nb if m.el[j] == "O"]
            if len(dO) >= 3:
                add("sulfonic")
            elif m.h[a] == 1 and len(nb) == 1:
                add("thiol")
            elif len(nb) == 2 and all(o == 1 for _, o in nb):
                add("disulfide" if any(m.el[j] == "S" for j, _ in nb) else "sulfide")
        elif e == "P" and sum(1 for j, _ in m.nbrs(a) if m.el[j] == "O") == 4:
            add("phosphate")
    seen = set()
    for i, j, o in m.bonds:
        if m.el[i] == "C" and m.el[j] == "C" and not (aromatic_atom(m, i) and aromatic_atom(m, j) and m.ring_bond[m.bond_index(i, j)]):
            if o == 2:
                add("alkene")
            elif o == 3:
                add("alkyne")
    for r in m.rings:
        if r["benzene"]:
            add("arene")
        elif any(m.aro[a] for a in r["atoms"]) and any(m.el[a] != "C" for a in r["atoms"]):
            add("heteroarene")
    for sy in m.ring_systems:
        if sy["cyclo"] > 1 and any(m.aro[a] for a in sy["atoms"]):
            key = "heteroarene" if any(m.el[a] != "C" for a in sy["atoms"]) else "arene"
            if key not in seen:
                add(key)
                seen.add(key)
    order = list(GROUP_NAMES)
    return [{"key": k, "n": n, "de": GROUP_NAMES[k][0], "en": GROUP_NAMES[k][1]}
            for k, n in sorted(found.items(), key=lambda x: order.index(x[0]))]
