"""Systematische Namen einfacher organischer Strukturen nach den IUPAC-Empfehlungen 2013.

Favre, H. A.; Powell, W. H.: Nomenclature of Organic Chemistry. IUPAC Recommendations and Preferred Names 2013.
RSC 2014, doi:10.1039/9781849733069.

Umfang (Substitutionsnomenklatur):
  * Ketten und isolierte Carbocyclen (Cycloalkane, -alkene, Benzol); Ringe und Ketten auch als Substituenten
  * Hauptgruppen in der Rangfolge Carbonsäure > Ester (einer) > Amid > Nitril > Aldehyd > Keton > Alkohol/
    Phenol > Amin; Halogen, Nitro, Ether (Alkoxy) nur als Präfix
  * sekundäre/tertiäre Amine und N-substituierte Amide (P-62.2.1.1, P-66.1.1.4): Stammamin bzw. -amid aus der
    ranghöchsten Gruppe am N, die übrigen als N-Präfixe (N-methylmethanamine, N,N-dimethylaniline,
    N-methylbenzamide); als Präfix nur (methylamino), (dimethylamino) u. ä. mit gleichen einfachen Resten
  * Heteromonocyclen mit festgelegter Bezifferung (P-22.2, P-31.1.4.2.4): Furan, Thiophen, 1H-Pyrrol, 1H-Imidazol,
    1H-Pyrazol, 1,2-/1,3-Oxazol, 1,2-/1,3-Thiazol, Pyridin, Pyrimidin, Pyrazin, Pyridazin; gesättigt Oxiran,
    Thiiran, Aziridin, Oxetan, Thietan, Azetidin, Oxolan, Thiolan, Pyrrolidin, 1,3-Dioxolan, Oxan, Thian, Piperidin,
    Piperazin, Morpholin, 1,3- und 1,4-Dioxan; Indikator-Wasserstoff am Pyrrol-N (1H); auch als Substituent
    (pyridin-2-yl)
  * Stammverbindung (P-44): meiste Hauptgruppen, Ring vor Kette, Heterocyclus vor Carbocyclus (P-44.2.1.2: N-haltig,
    mehr Ringatome, mehr Heteroatome, Vielfalt, O > S > N), längste Kette, meiste Mehrfachbindungen, meiste
    Doppelbindungen; Bezifferung (P-31.1.4): Heteroatome und Indikator-Wasserstoff (fest), Hauptgruppen, dann
    Mehrfachbindungen, Doppelbindungen, Präfixe, alphanumerisch erstgenanntes Präfix
  * Substituentenpräfixe mit längster Kette durch die freie Valenz (propan-2-yl, 2-methylpropyl); tert-Butyl, Benzyl,
    Phenyl, Acetyl, Benzoyl als beibehaltene Namen
  * beibehaltene Stammnamen: Ameisen-, Essig-, Benzoesäure, Phenol, Anilin, Benzaldehyd, Benzonitril, Benzamid,
    Formaldehyd, Formamid, Acetamid, Acetonitril (P-66.1.1.1.1, P-66.5.1.1.1; substituiert wie Essigsäure ohne
    Lokanten); Lokanten weggelassen nach P-14.3.4
Abgelehnt (statt eines möglicherweise falschen Namens): andere Heterocyclen (Triazole, Triazine, teilhydrierte
Ringe, Lactame/Pyridone), kondensierte, verbrückte und Spiro-Ringe, Ringverbände, Ylidene, Amine mit mehreren
Amino-N (N,N′-Lokanten), quartäre Ammoniumsalze, Harnstoffe, Imide, Amide am Ring-N, Anhydride, Lactone, mehrere
Ester, Ester neben Säure, Salze und Ionen, Isotope, Elemente ausser C H N O S F Cl Br I (S nur im Ring), mehrere
gleichrangige Ringe als Stammverbindung.
Stereodeskriptoren (E/Z, R/S) werden nicht vergeben; das wird vermerkt.
"""
from __future__ import annotations

import re

from .molgraph import HALOGENS, Mol, parse, terminal_O
from .smiles import SmilesError

STEM = {1: "meth", 2: "eth", 3: "prop", 4: "but", 5: "pent", 6: "hex", 7: "hept", 8: "oct", 9: "non", 10: "dec",
        11: "undec", 12: "dodec", 13: "tridec", 14: "tetradec", 15: "pentadec", 16: "hexadec", 17: "heptadec",
        18: "octadec", 19: "nonadec", 20: "icos", 21: "henicos", 22: "docos", 23: "tricos", 24: "tetracos",
        25: "pentacos", 26: "hexacos", 27: "heptacos", 28: "octacos", 29: "nonacos", 30: "triacont"}
MULT = {1: "", 2: "di", 3: "tri", 4: "tetra", 5: "penta", 6: "hexa", 7: "hepta", 8: "octa", 9: "nona", 10: "deca"}
MULTK = {1: "", 2: "bis", 3: "tris", 4: "tetrakis", 5: "pentakis", 6: "hexakis", 7: "heptakis", 8: "octakis"}
SENIORITY = ["acid", "ester", "amide", "nitrile", "aldehyde", "ketone", "alcohol", "amine"]
CINC = {"acid", "ester", "amide", "nitrile", "aldehyde"}          # Suffixe, deren C-Atom zur Kette zählt
SUF_CHAIN = {"acid": "oic acid", "ester": "oate", "amide": "amide", "nitrile": "nitrile", "aldehyde": "al",
             "ketone": "one", "alcohol": "ol", "amine": "amine"}
SUF_RING = {"acid": "carboxylic acid", "ester": "carboxylate", "amide": "carboxamide", "nitrile": "carbonitrile",
            "aldehyde": "carbaldehyde", "ketone": "one", "alcohol": "ol", "amine": "amine"}
BENZ_RETAINED = {"acid": "benzoic acid", "ester": "benzoate", "amide": "benzamide", "nitrile": "benzonitrile",
                 "aldehyde": "benzaldehyde", "alcohol": "phenol", "amine": "aniline"}
HALO = {"F": "fluoro", "Cl": "chloro", "Br": "bromo", "I": "iodo"}
VOWELS = "aeiouy"
RULE = "IUPAC-Empfehlungen 2013 (Favre & Powell 2014), Substitutionsnomenklatur"

# Heteromonocyclen: Name und Elementfolge in der festgelegten Bezifferung (Position 1 zuerst). Fünfringe: Position 1
# ist das „Pyrrol-Atom“ (O, S, NH oder NR); beim Pyrrol-N wird der Indikator-Wasserstoff 1H genannt.
HET_ARO = [("furan", "OCCCC"), ("thiophene", "SCCCC"), ("1H-pyrrole", "NCCCC"), ("1H-imidazole", "NCNCC"),
           ("1H-pyrazole", "NNCCC"), ("1,3-oxazole", "OCNCC"), ("1,2-oxazole", "ONCCC"), ("1,3-thiazole", "SCNCC"),
           ("1,2-thiazole", "SNCCC"), ("pyridine", "NCCCCC"), ("pyrimidine", "NCNCCC"), ("pyrazine", "NCCNCC"),
           ("pyridazine", "NNCCCC")]
HET_SAT = [("oxirane", "OCC"), ("thiirane", "SCC"), ("aziridine", "NCC"), ("oxetane", "OCCC"), ("thietane", "SCCC"),
           ("azetidine", "NCCC"), ("oxolane", "OCCCC"), ("thiolane", "SCCCC"), ("pyrrolidine", "NCCCC"),
           ("1,3-dioxolane", "OCOCC"), ("oxane", "OCCCCC"), ("thiane", "SCCCCC"), ("piperidine", "NCCCCC"),
           ("piperazine", "NCCNCC"), ("morpholine", "OCCNCC"), ("1,4-dioxane", "OCCOCC"), ("1,3-dioxane", "OCOCCC")]
SYNONYMS = {"oxolane": "Tetrahydrofuran (THF)", "oxane": "Tetrahydropyran", "1,4-dioxane": "Dioxan",
            "N,N-dimethylformamide": "DMF", "N-phenylacetamide": "Acetanilid"}


class Refuse(Exception):
    """Struktur liegt ausserhalb der umgesetzten Regeln."""


def _locs(ls) -> str:
    """Lokanten aufsteigend; Buchstabenlokanten (N) vor Ziffern: N,N,4-trimethylaniline."""
    return ",".join(str(x) for x in sorted(ls, key=lambda x: (0, x, 0) if isinstance(x, str) else (1, "", x)))


def _elide(base: str, nxt: str) -> str:
    return base[:-1] if base.endswith("e") and nxt[:1] in VOWELS else base


def _wrap(s: str) -> str:
    if "[" in s:
        return "{" + s + "}"
    if "(" in s:
        return "[" + s + "]"
    return "(" + s + ")"


def _hydro(stem: str, enes, ynes, show: bool) -> str:
    """'propane', 'but-2-ene', 'buta-1,3-diene', 'pent-1-en-4-yne'."""
    if not enes and not ynes:
        return stem + "ane"
    s = stem + ("a" if len(enes or ynes) > 1 else "")
    if enes:
        s += ("-" + _locs(enes) + "-" if show else "") + MULT[len(enes)] + "ene"
    if ynes:
        if enes:
            s = s[:-1]
        s += ("-" + _locs(ynes) + "-" if show else "") + MULT[len(ynes)] + "yne"
    return s


def _alpha_key(info: dict) -> str:
    n = info["name"]
    if not info.get("compound"):
        n = re.sub(r"^tert-", "", n)
    return re.sub(r"[^a-z]", "", n.lower())


class _Namer:
    def __init__(self, m: Mol):
        self.m = m
        self.func: dict[int, str] = {}       # C-Atom -> acid/ester/amide/nitrile/aldehyde/ketone
        self.owner: dict[int, int] = {}      # Heteroatom -> C-Atom der Gruppe
        self.att: dict[int, str] = {}        # Heteroatom-Wurzel -> ol/amine/halo/nitro/ether
        self.cut: set = set()
        self.esters = []
        self.hetring: dict[frozenset, dict] = {}   # Heteroring (Atommenge) -> {name, orders, aro}
        self.ringhet: set = set()            # Heteroatome in erkannten Heteroringen
        self.secN: set = set()               # sekundäre/tertiäre Amin-N
        self._check()
        self._classify()
        present = set(self.func.values())
        if any(v == "ol" for v in self.att.values()):
            present.add("alcohol")
        if any(v == "amine" for v in self.att.values()):
            present.add("amine")
        self.P = next((t for t in SENIORITY if t in present), None)
        if self.esters and (len(self.esters) > 1 or "acid" in present):
            raise Refuse("mehrere Estergruppen oder Ester neben Carbonsäure (Präfix-Schreibweise nicht umgesetzt)")
        if self.P == "amine" and self.secN and sum(1 for v in self.att.values() if v == "amine") > 1:
            raise Refuse("mehrere Amino-Stickstoffe mit N-Substitution (Lokanten N, N′) werden nicht benannt")

    # ------------------------------------------------------------------ Prüfung und Gruppen
    def _check(self):
        m = self.m
        if m.n() > 80:
            raise Refuse("Struktur zu gross für die Regelbenennung")
        if len(m.fragments()) != 1:
            raise Refuse("mehrere Fragmente (Salz, Gemisch)")
        if "C" not in m.el:
            raise Refuse("keine Kohlenstoffverbindung")
        for i, e in enumerate(m.el):
            if e not in ("C", "N", "O", "S") + HALOGENS:
                raise Refuse(f"Element {e} wird nicht benannt")
            if m.iso[i]:
                raise Refuse("Isotopenmarkierung wird nicht benannt")
        for sy in m.ring_systems:
            if sy["cyclo"] != 1:
                raise Refuse("kondensierte, verbrückte oder Spiro-Ringsysteme werden nicht benannt")
        for r in m.rings:
            if any(m.el[a] != "C" for a in r["atoms"]):
                self._hetring(r["atoms"])
                continue
            if any(m.aro[a] for a in r["atoms"]) and not r["benzene"]:
                raise Refuse("aromatische Ringe ausser Benzol werden nicht benannt")
            if len(r["atoms"]) > 30:
                raise Refuse("Ring zu gross")
        for i, e in enumerate(m.el):
            if e == "S" and i not in self.ringhet:
                raise Refuse("Schwefel ausserhalb der umgesetzten Heterocyclen (Thiol, Sulfid …) wird nicht benannt")

    def _hetring(self, atoms: list[int]):
        """Heteromonocyclus erkennen (Tabellen HET_ARO/HET_SAT) und die zulässigen Bezifferungen festhalten."""
        m = self.m
        n, S = len(atoms), set(atoms)
        if any(m.q[a] for a in atoms):
            raise Refuse("geladene Atome (Ionen, Salze) werden nicht benannt")
        for a in atoms:
            if any(j not in S and o != 1 for j, o in m.nbrs(a)):
                raise Refuse("Heterocyclen mit exocyclischer Doppelbindung (Lactame, Lactone, Pyridone …) werden "
                             "nicht benannt")
        orders = [m.order(atoms[i], atoms[(i + 1) % n]) for i in range(n)]
        aro = [m.aro[a] for a in atoms]
        if all(aro):
            if any(o != 1.5 for o in orders):
                raise Refuse("gemischt aromatische/kekulé Schreibweise im Heterocyclus wird nicht benannt")
            kind = "aro"
        elif any(aro):
            raise Refuse("gemischt aromatische/kekulé Schreibweise im Heterocyclus wird nicht benannt")
        elif all(o == 1 for o in orders):
            kind = "sat"
        else:
            dbl = [sum(1 for j, o in m.nbrs(a) if j in S and o == 2) for a in atoms]
            if all(o in (1, 2) for o in orders) and ((n == 6 and all(c == 1 for c in dbl)) or
                                                      (n == 5 and sorted(dbl) == [0, 1, 1, 1, 1])):
                kind = "aro"
            else:
                raise Refuse("teilhydrierte Heterocyclen (Dihydro-, Tetrahydro-…, 2H-Pyran) werden nicht benannt")
        pyrrole_like = lambda a: (m.el[a] in ("O", "S") and m.deg(a) == 2 and m.h[a] == 0) or \
            (m.el[a] == "N" and m.deg(a) + m.h[a] == 3)                     # noqa: E731
        X = None
        for a in atoms:
            e = m.el[a]
            if e == "C":
                if m.deg(a) + m.h[a] != (3 if kind == "aro" else 4):
                    raise Refuse("Radikal oder ungewöhnliche Valenz im Heterocyclus wird nicht benannt")
                continue
            if kind == "sat":
                if not pyrrole_like(a):
                    raise Refuse("Heteroatom im Ring in dieser Bindungsform wird nicht benannt")
            elif e == "N" and m.deg(a) == 2 and m.h[a] == 0:
                continue                                                    # Pyridin-N (=N- bzw. n)
            elif n == 5 and pyrrole_like(a) and X is None:
                X = a                                                       # O, S, NH, NR im Fünfring
            else:
                raise Refuse("Heteroatom im aromatischen Ring in dieser Form (Tautomer, Kation …) wird nicht benannt")
        if kind == "aro" and n == 5 and X is None:
            raise Refuse("aromatischer Fünfring ohne eindeutiges Pyrrol-Heteroatom (Tautomer) wird nicht benannt")
        table = HET_ARO if kind == "aro" else HET_SAT
        for nm, seq in table:
            if len(seq) != n:
                continue
            ok = [o for o in self._numberings(atoms, True) if "".join(m.el[a] for a in o) == seq and
                  (X is None or o[0] == X)]
            if ok:
                self.hetring[frozenset(atoms)] = {"name": nm, "orders": ok, "aro": kind == "aro"}
                self.ringhet.update(a for a in atoms if m.el[a] != "C")
                return
        raise Refuse("dieser Heterocyclus wird nicht benannt (umgesetzt: Pyridin, Pyrimidin, Pyrazin, Pyridazin, "
                     "Furan, Thiophen, Pyrrol, Imidazol, Pyrazol, Oxazol, Thiazol und gesättigte Grundringe)")

    def _classify(self):
        m = self.m
        for a in range(m.n()):                                   # Nitrogruppen zuerst (O-Atome gehören dazu)
            if m.el[a] != "N":
                continue
            oo = [j for j, _ in m.nbrs(a) if m.el[j] == "O" and m.deg(j) == 1]
            cc = [j for j, _ in m.nbrs(a) if m.el[j] == "C"]
            if len(oo) == 2 and len(cc) == 1 and m.deg(a) == 3:
                ok = (m.q[a] == 0 and all(m.order(a, o) == 2 for o in oo)) or \
                     (m.q[a] == 1 and sorted(m.q[o] for o in oo) == [-1, 0])
                if ok:
                    self.att[a] = "nitro"
                    for o in oo:
                        self.owner[o] = a
                    continue
            if m.q[a]:
                raise Refuse("geladene Atome (Ionen, Salze) werden nicht benannt")
        for a in range(m.n()):
            if m.q[a] and a not in self.owner and self.att.get(a) != "nitro":
                raise Refuse("geladene Atome (Ionen, Salze) werden nicht benannt")
        for c in range(m.n()):
            if m.el[c] != "C":
                continue
            dO = terminal_O(m, c, 2)
            nit = [j for j, o in m.nbrs(c) if m.el[j] == "N" and o == 3]
            if dO:
                if len(dO) > 1:
                    raise Refuse("C mit zwei =O (z. B. CO₂) wird nicht benannt")
                o2 = dO[0]
                others = [(j, o) for j, o in m.nbrs(c) if j != o2]
                het = [(j, o) for j, o in others if m.el[j] != "C"]
                if any(o != 1 for _, o in others):
                    raise Refuse("Carbonyl-C mit weiterer Mehrfachbindung (Keten, Chinon) wird nicht benannt")
                if m.benzene_atom[c]:
                    raise Refuse("Carbonylgruppe im Benzolring")
                if not het:
                    self.func[c] = "aldehyde" if m.h[c] >= 1 else "ketone"
                    self.owner[o2] = c
                elif len(het) == 1:
                    j = het[0][0]
                    if m.el[j] == "O" and m.h[j] == 1 and m.deg(j) == 1:
                        self.func[c] = "acid"
                    elif m.el[j] == "O" and m.deg(j) == 2:
                        k = next(x for x, _ in m.nbrs(j) if x != c)
                        if m.el[k] != "C" or terminal_O(m, k, 2) or m.ring_atom[j]:
                            raise Refuse("Anhydride, Lactone und ähnliche Gruppen werden nicht benannt")
                        self.func[c] = "ester"
                        self.esters.append((c, j, k))
                        self.cut.add(frozenset((j, k)))
                    elif m.el[j] == "N" and m.h[j] == 2 and m.deg(j) == 1:
                        self.func[c] = "amide"
                    elif m.el[j] == "N" and self._n_amide(j, c):
                        self.func[c] = "amide"                    # N-substituiertes Amid (P-66.1.1.4)
                    else:
                        raise Refuse("diese Carbonylverbindung (Amid am Ring-N, Imid, Säurehalogenid …) wird "
                                     "nicht benannt")
                    self.owner[o2] = c
                    self.owner[j] = c
                else:
                    raise Refuse("Carbonyl-C mit mehreren Heteroatomen (Carbonat, Harnstoff …) wird nicht benannt")
            elif nit:
                j = nit[0]
                if m.deg(j) != 1:
                    raise Refuse("C≡N mit substituiertem N")
                self.func[c] = "nitrile"
                self.owner[j] = c
            else:
                for j, o in m.nbrs(c):
                    if m.el[j] != "C" and o > 1 and j not in self.ringhet:     # Ringbindung im Heteroaromaten
                        raise Refuse("Imine, Oxime u. ä. werden nicht benannt")
        for a in range(m.n()):
            if m.el[a] == "C" or a in self.owner or a in self.att or a in self.ringhet:
                continue
            e, nb = m.el[a], m.nbrs(a)
            if e == "O":
                if len(nb) == 1 and nb[0][1] == 1 and m.h[a] == 1 and m.el[nb[0][0]] == "C":
                    self.att[a] = "ol"
                elif len(nb) == 2 and all(m.el[j] == "C" and o == 1 for j, o in nb) and not m.ring_atom[a]:
                    self.att[a] = "ether"
                else:
                    raise Refuse("Sauerstoff in dieser Bindungsform (Peroxid, Wasser …) wird nicht benannt")
            elif e == "N":
                if len(nb) == 1 and nb[0][1] == 1 and m.h[a] == 2 and m.el[nb[0][0]] == "C":
                    self.att[a] = "amine"
                elif len(nb) in (2, 3) and m.h[a] == 3 - len(nb) and \
                        all(m.el[j] == "C" and o == 1 and j not in self.func for j, o in nb):
                    self.att[a] = "amine"                     # sekundäres/tertiäres Amin (P-62.2.1.1)
                    self.secN.add(a)
                else:
                    raise Refuse("dieser Stickstoff (Hydrazin, Hydroxylamin, Cyanamid …) wird nicht benannt")
            elif e in HALOGENS:
                if len(nb) == 1 and m.el[nb[0][0]] == "C":
                    self.att[a] = "halo"
                else:
                    raise Refuse("Halogen nicht an Kohlenstoff gebunden")
            else:
                raise Refuse(f"{e} in dieser Bindungsform wird nicht benannt")

    def _n_amide(self, j: int, c: int) -> bool:
        """N eines N-substituierten Amids: nicht im Ring, sonst nur einfach gebundene C ohne eigene C=O (kein Imid)."""
        m = self.m
        if m.ring_atom[j] or m.q[j]:
            return False
        rest = [(y, o) for y, o in m.nbrs(j) if y != c]
        return m.deg(j) + m.h[j] == 3 and bool(rest) and \
            all(m.el[y] == "C" and o == 1 and not terminal_O(m, y, 2) and
                not any(m.el[z] == "N" and oz == 3 for z, oz in m.nbrs(y)) for y, o in rest)

    # ------------------------------------------------------------------ Hilfen
    def nb(self, a: int) -> list[int]:
        return [j for j, _ in self.m.adj[a] if frozenset((a, j)) not in self.cut]

    def skel_main(self, a: int) -> bool:
        if self.m.el[a] != "C":
            return False
        f = self.func.get(a)
        return not (f in ("acid", "amide", "nitrile") and f != self.P)

    def skel_sub(self, a: int) -> bool:
        return self.m.el[a] == "C" and self.func.get(a) not in ("acid", "amide", "nitrile", "ester")

    def component(self, start: int, block: int | None = None) -> set:
        seen, st = {start}, [start]
        while st:
            i = st.pop()
            for j in self.nb(i):
                if j != block and j not in seen:
                    seen.add(j)
                    st.append(j)
        return seen

    def _paths(self, forest: set, must: int | None = None, start: int | None = None) -> list[list[int]]:
        """Maximale Ketten (Blatt zu Blatt) im Wald; must: muss enthalten sein; start: Kette beginnt dort."""
        adj = {a: [j for j in self.nb(a) if j in forest] for a in forest}
        leaves = sorted(a for a in forest if len(adj[a]) <= 1)
        out = []
        for u in leaves:
            if start is not None and u != start:
                continue
            if not adj[u]:
                out.append([u])
                continue
            par, st = {u: None}, [u]
            while st:
                i = st.pop()
                for j in adj[i]:
                    if j not in par:
                        par[j] = i
                        st.append(j)
            for v in leaves:
                if v == u or v not in par or (start is None and v < u):
                    continue
                path, x = [], v
                while x is not None:
                    path.append(x)
                    x = par[x]
                path.reverse()
                if must is not None and must not in path:
                    continue
                out.append(path)
        return out

    def _het(self, atoms) -> dict | None:
        return self.hetring.get(frozenset(atoms))

    def _orders(self, atoms: list[int], ring: bool):
        het = self._het(atoms) if ring else None
        return het["orders"] if het else self._numberings(atoms, ring)

    def _multiple(self, order: list[int], ring: bool, benzene: bool):
        if benzene or (ring and self._het(order)):        # Heteroaromat: Name ohne -en; gesättigt: keine
            return [], []
        m = self.m
        n = len(order)
        loc = {a: i + 1 for i, a in enumerate(order)}
        pairs = list(zip(order, order[1:])) + ([(order[-1], order[0])] if ring and n > 2 else [])
        enes, ynes = [], []
        for a, b in pairs:
            o = m.order(a, b)
            la, lb = loc[a], loc[b]
            lo = n if ring and {la, lb} == {1, n} else min(la, lb)
            if o == 2:
                enes.append(lo)
            elif o == 3:
                ynes.append(lo)
        return sorted(enes), sorted(ynes)

    @staticmethod
    def _numberings(atoms: list[int], ring: bool):
        if not ring:
            yield list(atoms)
            if len(atoms) > 1:
                yield list(reversed(atoms))
            return
        n = len(atoms)
        rev = atoms[::-1]
        for s in range(n):
            yield atoms[s:] + atoms[:s]
            k = n - 1 - s
            yield rev[k:] + rev[:k]

    # ------------------------------------------------------------------ Merkmale an einer Stammstruktur
    def _features(self, atoms: list[int], ring: bool, P: str | None, frm: int | None = None, acyl_root: int | None = None):
        """Suffix-Atome, Präfixe [(Atom, info)], an der Kette hängende C-Suffixe (nicht eingeschlossen)."""
        m = self.m
        S = set(atoms)
        suf, pre, attached = [], [], 0
        for p in atoms:
            f = self.func.get(p)
            if f and p != acyl_root:
                if f == P and P in CINC | {"ketone"}:
                    suf.append(p)
                elif f in ("aldehyde", "ketone"):
                    pre.append((p, {"name": "oxo"}))
            for x in self.nb(p):
                if x in S or x == frm or self.owner.get(x) == p:
                    continue
                if m.el[x] == "C" and m.order(p, x) > 1:
                    raise Refuse("exocyclische bzw. Ylidendoppelbindung (…ylidene) wird nicht benannt")
                fx = self.func.get(x)
                if P in CINC and fx == P and frm is None:
                    suf.append(p)
                    if not ring:
                        attached += 1
                elif P == "alcohol" and self.att.get(x) == "ol" and frm is None:
                    suf.append(p)
                elif P == "amine" and self.att.get(x) == "amine" and frm is None:
                    suf.append(p)
                else:
                    pre.append((p, self.sub_name(x, p)))
        return suf, pre, attached

    @staticmethod
    def _groups(pre, loc):
        g = {}
        for p, info in pre:
            d = g.setdefault(info["name"], {"info": info, "locs": []})
            d["locs"].append(loc[p])
        return sorted(g.values(), key=lambda d: (_alpha_key(d["info"]), d["info"]["name"]))

    def _numkey(self, order, ring, benzene, suf, pre):
        loc = {a: i + 1 for i, a in enumerate(order)}
        enes, ynes = self._multiple(order, ring, benzene)
        groups = self._groups(pre, loc)
        return (sorted(loc[p] for p in suf), sorted(enes + ynes), enes, sorted(loc[p] for p, _ in pre),
                [sorted(d["locs"]) for d in groups])

    @staticmethod
    def _prefix_str(groups, show: bool) -> str:
        parts = []
        for d in groups:
            info, n = d["info"], len(d["locs"])
            name = info["name"]
            needs = info.get("compound") or bool(re.search(r"\d", name))
            mult = (MULTK if info.get("compound") else MULT)[n] if n > 1 else ""
            body = _wrap(name) if needs else name
            shown = show or any(isinstance(x, str) for x in d["locs"])      # N-Lokanten stehen immer
            parts.append(((_locs(d["locs"]) + "-") if shown else "", mult, body))
        s = ""
        for loc, mult, body in parts:
            if not loc and s and s[-1] in ")]}" and body[0] not in "([{":
                body = _wrap(body)                        # (4-bromophenyl)(phenyl)methanone
            if mult and body.startswith("tert-"):
                mult += "-"                               # tri-tert-butyl
            p = loc + mult + body
            s += ("-" if s and (loc or p[:1].isdigit()) else "") + p
        return s

    @staticmethod
    def _join(prefixes: str, parent: str) -> str:
        """2-methyl + 1H-pyrrole -> 2-methyl-1H-pyrrole."""
        return prefixes + ("-" if prefixes and parent[:1].isdigit() else "") + parent

    # ------------------------------------------------------------------ Substituenten
    def sub_name(self, x: int, frm: int) -> dict:
        m = self.m
        e = m.el[x]
        if e in HALOGENS:
            return {"name": HALO[e], "base": HALO[e]}
        kind = self.att.get(x)
        if kind == "nitro":
            return {"name": "nitro", "base": "nitro"}
        if kind == "amine":
            others = [j for j in self.nb(x) if j != frm]
            if not others:
                return {"name": "amino", "base": "amino"}
            infos = [self.sub_name(j, x) for j in others]               # (methylamino), (dimethylamino)
            if len({i["name"] for i in infos}) > 1 or any(
                    i.get("compound") or re.search(r"[\d(]", i["name"]) or i["name"].startswith("tert-") for i in infos):
                raise Refuse("Aminopräfix mit verschiedenen oder zusammengesetzten N-Resten wird nicht benannt")
            nm = MULT[len(infos)] + infos[0]["name"] + "amino"
            return {"name": nm, "base": nm, "compound": True}
        if x in self.ringhet:
            return self._ring_sub(x, frm)                                # piperidin-1-yl
        if kind == "ol":
            return {"name": "hydroxy", "base": "hydroxy"}
        if kind == "ether":
            r = next(j for j in self.nb(x) if j != frm)
            ri = self.sub_name(r, x)
            if ri["base"] in ("methyl", "ethyl", "propyl", "butyl", "phenyl", "tert-butyl"):
                name = ri["name"][:-2] + "oxy"
                return {"name": name, "base": ri["base"][:-2] + "oxy", "compound": ri.get("compound")}
            inner = _wrap(ri["name"]) if (ri.get("compound") or re.search(r"\d", ri["name"])) else ri["name"]
            return {"name": inner + "oxy", "base": inner + "oxy", "compound": True}      # (pentyloxy)benzene
        if e != "C":
            raise Refuse("Substituent dieser Art wird nicht benannt")
        if m.order(frm, x) > 1:
            raise Refuse("Ylidensubstituent (Doppelbindung zur Stammstruktur) wird nicht benannt")
        f = self.func.get(x)
        if f == "acid":
            return {"name": "carboxy", "base": "carboxy"}
        if f == "amide":
            if self._amide_n_subs(x):
                raise Refuse("N-substituiertes Amid als Präfix (…carbamoyl) wird nicht benannt")
            return {"name": "carbamoyl", "base": "carbamoyl"}
        if f == "nitrile":
            return {"name": "cyano", "base": "cyano"}
        if f == "ester":
            raise Refuse("Ester als Substituent wird nicht benannt")
        if f == "aldehyde":
            return {"name": "formyl", "base": "formyl"}
        if f == "ketone":
            return self._acyl(x, frm)
        if m.ring_atom[x]:
            return self._ring_sub(x, frm)
        return self._chain_sub(x, frm)

    def _finish_sub(self, base: str, groups, show: bool) -> dict:
        ps = self._prefix_str(groups, show)
        return {"name": self._join(ps, base), "base": base, "compound": bool(groups)}

    def _persub(self, atoms, pre) -> bool:
        return bool(pre) and len({i["name"] for _, i in pre}) == 1 and all(self.m.h[a] == 0 for a in atoms)

    def _chain_sub(self, x: int, frm: int) -> dict:
        comp = self.component(x, frm)
        forest = {a for a in comp if self.skel_sub(a) and not self.m.ring_atom[a]}
        best = None
        for path in self._paths(forest, must=x):
            for order in self._numberings(path, False):
                suf, pre, _ = self._features(order, False, None, frm=frm)
                enes, ynes = self._multiple(order, False, False)
                loc = {a: i + 1 for i, a in enumerate(order)}
                nk = self._numkey(order, False, False, [], pre)
                key = (-len(order), -len(enes) - len(ynes), -len(enes), [loc[x]], nk[1], nk[2], -len(pre), nk[3], nk[4])
                if best is None or key < best[0]:
                    best = (key, order, pre, enes, ynes)
        _, order, pre, enes, ynes = best
        n = len(order)
        loc = {a: i + 1 for i, a in enumerate(order)}
        fv = loc[x]
        groups = self._groups(pre, loc)
        if n == 3 and fv == 2 and not enes and not ynes and len(pre) == 1 and pre[0][1]["name"] == "methyl" \
                and loc[pre[0][0]] == 2:
            return {"name": "tert-butyl", "base": "tert-butyl"}
        if n == 1 and len(pre) == 1 and pre[0][1]["name"] == "phenyl":
            return {"name": "benzyl", "base": "benzyl"}
        if not enes and not ynes and fv == 1:
            base = STEM[n] + "yl" if n in STEM else None
        elif n == 2:
            base = _elide(_hydro("eth", enes, ynes, False), "y") + "yl"
        else:
            base = _elide(_hydro(STEM[n], enes, ynes, True), "y") + f"-{fv}-yl" if n in STEM else None
        if base is None:
            raise Refuse("Kette zu lang")
        show = n > 1 and not self._persub(order, pre)
        return self._finish_sub(base, groups, show)

    def _ring_sub(self, x: int, frm: int) -> dict:
        r = next(r for r in self.m.rings if x in r["atoms"])
        atoms, benz = r["atoms"], r["benzene"]
        het = self._het(atoms)
        if het:                                   # feste Bezifferung; freie Valenz dann möglichst niedrig
            best = None
            for order in het["orders"]:
                suf, pre, _ = self._features(order, True, None, frm=frm)
                nk = self._numkey(order, True, benz, [], pre)
                key = (order.index(x), nk[3], nk[4])
                if best is None or key < best[0]:
                    best = (key, order, pre)
            _, order, pre = best
            loc = {a: i + 1 for i, a in enumerate(order)}
            base = _elide(het["name"], "y") + f"-{loc[x]}-yl"          # pyridin-2-yl, 1H-pyrrol-1-yl
            return self._finish_sub(base, self._groups(pre, loc), not self._persub(order, pre))
        best = None
        for order in self._numberings(atoms, True):
            if order[0] != x:
                continue
            suf, pre, _ = self._features(order, True, None, frm=frm)
            nk = self._numkey(order, True, benz, [], pre)
            key = (nk[1], nk[2], nk[3], nk[4])
            if best is None or key < best[0]:
                best = (key, order, pre)
        _, order, pre = best
        loc = {a: i + 1 for i, a in enumerate(order)}
        groups = self._groups(pre, loc)
        n = len(order)
        if benz:
            base = "phenyl"
        else:
            enes, ynes = self._multiple(order, True, False)
            if n not in STEM:
                raise Refuse("Ring zu gross")
            base = "cyclo" + STEM[n] + "yl" if not enes and not ynes else \
                _elide("cyclo" + _hydro(STEM[n], enes, ynes, True), "y") + "-1-yl"
        return self._finish_sub(base, groups, not self._persub(order, pre))

    def _acyl(self, x: int, frm: int) -> dict:
        m = self.m
        y = next(j for j in self.nb(x) if j != frm and self.owner.get(j) != x)
        if m.ring_atom[y]:
            ri = self._ring_sub(y, x)
            if ri["base"] == "phenyl":
                return {"name": ri["name"][:-len("phenyl")] + "benzoyl", "base": "benzoyl", "compound": ri.get("compound")}
            if ri.get("compound") or "-" in ri["base"]:
                raise Refuse("Acylgruppe an substituiertem oder ungesättigtem Ring wird nicht benannt")
            return {"name": ri["base"][:-2] + "anecarbonyl", "base": ri["base"][:-2] + "anecarbonyl"}
        comp = self.component(x, frm)
        forest = {a for a in comp if self.skel_sub(a) and not m.ring_atom[a]}
        best = None
        for path in self._paths(forest, start=x):
            order = path
            suf, pre, _ = self._features(order, False, None, frm=frm, acyl_root=x)
            nk = self._numkey(order, False, False, [], pre)
            enes, ynes = self._multiple(order, False, False)
            key = (-len(order), -len(enes) - len(ynes), -len(enes), nk[1], nk[2], -len(pre), nk[3], nk[4])
            if best is None or key < best[0]:
                best = (key, order, pre, enes, ynes)
        _, order, pre, enes, ynes = best
        n = len(order)
        loc = {a: i + 1 for i, a in enumerate(order)}
        groups = self._groups(pre, loc)
        if n == 2 and not enes and not ynes:
            return self._finish_sub("acetyl", groups, False)
        if n not in STEM:
            raise Refuse("Kette zu lang")
        base = _elide(_hydro(STEM[n], enes, ynes, True), "o") + "oyl"
        return self._finish_sub(base, groups, not self._persub(order, pre))

    # ------------------------------------------------------------------ Hauptverbindung
    def _parent(self, A: set, P: str | None):
        m = self.m
        cands = [(r["atoms"], True, r["benzene"]) for r in m.rings if set(r["atoms"]) <= A]
        forest = {a for a in A if self.skel_main(a) and not m.ring_atom[a]}
        cands += [(p, False, False) for p in self._paths(forest)]
        if not cands:
            raise Refuse("keine Stammstruktur gefunden")

        def cheap(c):
            atoms, ring, benz = c
            S = set(atoms)
            nP = 0
            for p in atoms:
                if self.func.get(p) == P and P in CINC | {"ketone"}:
                    nP += 1
                for x in self.nb(p):
                    if x in S or self.owner.get(x) == p:
                        continue
                    if (P in CINC and self.func.get(x) == P) or (P == "alcohol" and self.att.get(x) == "ol") or \
                            (P == "amine" and self.att.get(x) == "amine"):
                        nP += 1
            het = self._het(atoms) if ring else None
            if benz:
                nm, nd = 3, 3
            elif het and het["aro"]:
                nm = nd = len(atoms) // 2
            else:
                enes, ynes = self._multiple(atoms, ring, False)
                nm, nd = len(enes) + len(ynes), len(enes)
            els = [m.el[a] for a in atoms] if ring else []
            nh = sum(1 for e in els if e != "C")
            # P-44.2.1.2: Heterocyclus, N-haltig, mehr Ringatome, mehr Heteroatome, Vielfalt, O > S > N
            rk = (0 if nh else 1, 0 if "N" in els else 1) if ring else (0, 0)
            return (-nP, 0 if ring else 1) + rk + (-len(atoms), -nh, -len(set(els) - {"C"}), -els.count("O"),
                                                    -els.count("S"), -els.count("N"), -nm, -nd)
        keyed = [(cheap(c), c) for c in cands]
        top = min(k for k, _ in keyed)
        best = []
        for k, (atoms, ring, benz) in keyed:
            if k != top:
                continue
            suf, pre, attached = self._features(atoms, ring, P)
            for order in self._orders(atoms, ring):
                nk = self._numkey(order, ring, benz, suf, pre)
                full = k + (nk[0], nk[1], nk[2], -len(pre), nk[3], nk[4])
                best.append((full, order, ring, benz, suf, pre, attached))
        best.sort(key=lambda b: b[0])
        win = best[0]
        alts, seen = [], {frozenset(win[1])}
        for b in best:
            if b[0] == win[0] and frozenset(b[1]) not in seen:
                seen.add(frozenset(b[1]))
                alts.append(b)
        if win[6]:
            raise Refuse("Kette mit zusätzlich angehängten -carbonsäure/-carbaldehyd-Gruppen wird nicht benannt")
        return win, alts

    def _amide_n_subs(self, c: int) -> list[int]:
        return [y for x in self.nb(c) if self.m.el[x] == "N" and self.owner.get(x) == c for y in self.nb(x) if y != c]

    def _n_prefixes(self, suf, P) -> list[dict]:
        """N-Präfixe der Hauptgruppe (sekundäres/tertiäres Amin, N-substituiertes Amid)."""
        if P not in ("amine", "amide"):
            return []
        out = []
        for p in suf:
            if P == "amine":
                c, subs = p, [(N, y) for N in self.nb(p) if N in self.secN for y in self.nb(N) if y != p]
            else:
                c = p if self.func.get(p) == "amide" else next(x for x in self.nb(p) if self.func.get(x) == "amide")
                subs = [(next(x for x in self.nb(c) if self.m.el[x] == "N" and self.owner.get(x) == c), y)
                        for y in self._amide_n_subs(c)]
            for N, y in subs:
                if any(self.func.get(a) == P or (P == "amine" and self.att.get(a) == "amine")
                       for a in self.component(y, N)):
                    raise Refuse("Hauptgruppe auch im N-Substituenten (multiplikative Namen) wird nicht benannt")
                out.append(self.sub_name(y, N))
        if out and len(suf) > 1:
            raise Refuse("mehrere Hauptgruppen mit N-Substituenten (Lokanten N, N′) werden nicht benannt")
        return out

    @staticmethod
    def _merge_n(groups, nsubs):
        g = {d["info"]["name"]: {"info": d["info"], "locs": list(d["locs"])} for d in groups}
        for info in nsubs:
            g.setdefault(info["name"], {"info": info, "locs": []})["locs"].append("N")
        return sorted(g.values(), key=lambda d: (_alpha_key(d["info"]), d["info"]["name"]))

    def _compose(self, A: set, P: str | None) -> str:
        win, alts = self._parent(A, P)
        name = self._build(win, P)
        if alts:
            nsub = bool(self._n_prefixes(win[4], P))
            if (win[2] or nsub) and not (nsub and all(self._build(b, P) == name for b in alts)):
                if win[2]:
                    raise Refuse("mehrere gleichrangige Ringe (multiplikative Nomenklatur, z. B. Diphenylmethan-Typ) "
                                 "werden nicht benannt")
                raise Refuse("Wahl der Stammverbindung unter den N-Substituenten nicht eindeutig")
        return name

    def _build(self, win, P: str | None) -> str:
        (k, order, ring, benz, suf, pre, _) = win
        n = len(order)
        loc = {a: i + 1 for i, a in enumerate(order)}
        groups = self._groups(pre, loc)
        nsubs = self._n_prefixes(suf, P)
        if nsubs:
            if not ring and n == 1 and pre:
                raise Refuse("Methan-Stamm mit C- und N-Präfixen (Lokant 1 neben N) wird nicht benannt")
            groups = self._merge_n(groups, nsubs)
        het = self._het(order) if ring else None
        nsuf = len(suf)
        items = nsuf + len(pre)
        enes, ynes = self._multiple(order, ring, benz)
        persub = nsuf == 0 and self._persub(order, pre)
        # beibehaltene Stammnamen
        if not ring and n == 1 and P in ("acid", "ester") and nsuf == 1:
            return self._prefix_str(groups, False) + ("formic acid" if P == "acid" else "formate")
        if not ring and n == 1 and P == "aldehyde" and nsuf == 1 and not pre:
            return "formaldehyde"
        if not ring and n == 2 and P in ("acid", "ester") and nsuf == 1 and not enes and not ynes and \
                self.func.get(order[0]) == P:
            return self._prefix_str(groups, False) + ("acetic acid" if P == "acid" else "acetate")
        # P-66.1.1.1.1 / P-66.5.1.1.1: formamide, acetamide, acetonitrile als beibehaltene PINs
        if not ring and n == 1 and P == "amide" and nsuf == 1:
            return self._prefix_str(groups, False) + "formamide"
        if not ring and n == 2 and P in ("amide", "nitrile") and nsuf == 1 and not enes and not ynes and \
                self.func.get(order[0]) == P:
            if nsubs and pre:
                raise Refuse("Acetamid mit C- und N-Präfixen (Lokant 2 neben N) wird nicht benannt")
            return self._prefix_str(groups, False) + ("acetamide" if P == "amide" else "acetonitrile")
        if benz and nsuf == 1 and P in BENZ_RETAINED:
            return self._prefix_str(groups, items > 1) + BENZ_RETAINED[P]
        # Lokanten weglassen (P-14.3.4); Heteroringe haben ungleichwertige Positionen: Lokanten stets
        single_kind = (not ring and n <= 2) or (ring and not het and (benz or (not enes and not ynes)))
        omit_all = (not ring and n == 1) or (single_kind and items <= 1) or persub
        show_pre = not omit_all and not (not ring and n == 1)
        if ring:
            if het:
                base = het["name"]
            elif benz:
                base = "benzene"
            else:
                show_unsat = not (items == 0 and len(enes) + len(ynes) == 1) and not omit_all
                base = "cyclo" + _hydro(STEM[n], enes, ynes, show_unsat)
        else:
            if n not in STEM:
                raise Refuse("Kette zu lang")
            base = _hydro(STEM[n], enes, ynes, n > 2 and not omit_all)
        if nsuf:
            table = SUF_RING if ring else SUF_CHAIN
            sfx = MULT[nsuf] + table[P]
            cinc_chain = not ring and P in CINC
            show_suf = not omit_all and not cinc_chain
            if show_suf:
                parent = _elide(base, sfx) + "-" + _locs(loc[p] for p in suf) + "-" + sfx
            else:
                parent = _elide(base, sfx) + sfx
        else:
            parent = base
        return self._join(self._prefix_str(groups, show_pre), parent)

    def run(self) -> str:
        if self.P == "ester":
            c, o, k = self.esters[0]
            A = self.component(c)
            acid = self._compose(A, "ester")
            alkyl = self.sub_name(k, o)
            return alkyl["name"] + " " + acid
        return self._compose(set(range(self.m.n())), self.P)


# ----------------------------------------------------------------------------- Deutsch
_DE_WORDS = [
    (r"formic acid", "ameisensäure"), (r"acetic acid", "essigsäure"), (r"benzoic acid", "benzoesäure"),
    (r"\bformate\b", "formiat"), (r"carboxylic acid", "carbonsäure"), (r"oic acid", "säure"),
    (r"benzene", "benzol"), (r"aniline", "anilin"), (r"aldehyde", "aldehyd"), (r"nitrile", "nitril"),
    (r"amide\b", "amid"), (r"amine\b", "amin"), (r"ine\b", "in"), (r"ole\b", "ol"),      # Pyridin, Pyrrol
    (r"ate\b", "at"), (r"fluoro", "fluor"), (r"chloro", "chlor"),
    (r"bromo", "brom"), (r"iodo", "iod"), (r"yne", "in"), (r"yn", "in"), (r"one\b", "on"), (r"ane", "an"),
    (r"ene", "en"),
]


def german(en: str) -> str:
    """Deutsche Schreibweise des englischen IUPAC-Namens (Duden/IUPAC-Übersetzung: -an, -en, -in, Benzol, -säure)."""
    if " " in en and not en.endswith("acid"):                    # Ester: „ethyl acetate“ -> „Ethylacetat“
        alk, acid = en.split(" ", 1)
        s = alk + ("-" if acid[:1].isdigit() else "") + acid
    else:
        s = en
    for pat, rep in _DE_WORDS:
        s = re.sub(pat, rep, s)
    s = s.replace(" ", "")
    m = re.search(r"[a-z]", s)
    if m:
        i = m.start()
        if s[i:i + 5] == "tert-":
            i += 5
        s = s[:i] + s[i].upper() + s[i + 1:]
    return s


def name(smiles: str) -> dict:
    """{'en', 'de', 'rule', 'notes'} oder {'refused': Grund}."""
    try:
        m = parse(smiles)
    except SmilesError as e:
        return {"refused": f"Struktur nicht lesbar: {e}"}
    try:
        en = _Namer(m).run()
    except Refuse as e:
        return {"refused": str(e)}
    except (KeyError, StopIteration, IndexError) as e:     # Lücke in den Regeln: lieber kein Name als ein falscher
        return {"refused": f"Struktur ausserhalb der umgesetzten Regeln ({type(e).__name__})"}
    notes = []
    if m.stereo:
        notes.append("ohne Stereodeskriptor (E/Z, R/S werden nicht vergeben)")
    if en in SYNONYMS:
        notes.append("gebräuchlich: " + SYNONYMS[en])
    return {"en": en, "de": german(en), "rule": RULE, "refs": ["favre2014"], "notes": notes}
