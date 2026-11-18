"""Chemische Formeln und Gleichungen: lesen, Elementbilanz, ausgleichen, molare Masse, Stöchiometrie.

Gemeinsam für Elementrechner und Rechner (Funktionen M("…"), Ar("…"), n("…", m) in Rechenzeilen).

Schreibweise wie auf Papier bzw. wie mhchem:
- Formeln mit Klammern ( ) [ ] { }, Hydrate mit · • * (auch „.“ vor einer kleinen Zahl: CuSO4.5H2O),
  Bruchzahlen als Index (Fe0.95O).
- Ladung: SO4^2-, Fe^3+, Fe+3, NH4+, Cl-, e-. Ziffern direkt vor + oder - sind Indizes (NO3- = NO₃⁻); wer Fe³⁺ meint,
  schreibt Fe^3+ oder Fe+3 (Hinweis bei Fe3+).
- Phasen: (s) (l) (g) (aq) (cr).
- Isotope: ^13C, ^{13}C, D, T in Formeln; Kerne als ^14C, C-14, ^{235}_{92}U; Teilchen n, p, alpha, beta-, beta+,
  gamma, nu, antinu.
- Gleichung: Pfeil ->, →, =, => (Reaktion), <=>, ⇌, <-> (Gleichgewicht); Stoffe mit + getrennt; Koeffizienten
  davor (2, 1/2, 0.5) oder leer = unbekannt.

Ausgleichen exakt über den Nullraum der Zusammensetzungsmatrix mit Brüchen (fractions.Fraction).
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from fractions import Fraction
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).with_name("data")

SYMBOLS = ("H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y "
           "Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os "
           "Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn "
           "Nh Fl Mc Lv Ts Og").split()
Z_OF = {s: i + 1 for i, s in enumerate(SYMBOLS)}
_SYMSET = set(SYMBOLS)

NAMES_DE = ("Wasserstoff Helium Lithium Beryllium Bor Kohlenstoff Stickstoff Sauerstoff Fluor Neon Natrium Magnesium "
            "Aluminium Silicium Phosphor Schwefel Chlor Argon Kalium Calcium Scandium Titan Vanadium Chrom Mangan Eisen "
            "Cobalt Nickel Kupfer Zink Gallium Germanium Arsen Selen Brom Krypton Rubidium Strontium Yttrium Zirconium "
            "Niob Molybdän Technetium Ruthenium Rhodium Palladium Silber Cadmium Indium Zinn Antimon Tellur Iod Xenon "
            "Caesium Barium Lanthan Cer Praseodym Neodym Promethium Samarium Europium Gadolinium Terbium Dysprosium "
            "Holmium Erbium Thulium Ytterbium Lutetium Hafnium Tantal Wolfram Rhenium Osmium Iridium Platin Gold "
            "Quecksilber Thallium Blei Bismut Polonium Astat Radon Francium Radium Actinium Thorium Protactinium Uran "
            "Neptunium Plutonium Americium Curium Berkelium Californium Einsteinium Fermium Mendelevium Nobelium "
            "Lawrencium Rutherfordium Dubnium Seaborgium Bohrium Hassium Meitnerium Darmstadtium Roentgenium "
            "Copernicium Nihonium Flerovium Moscovium Livermorium Tenness Oganesson").split()
NAMES_EN = ("Hydrogen Helium Lithium Beryllium Boron Carbon Nitrogen Oxygen Fluorine Neon Sodium Magnesium Aluminium "
            "Silicon Phosphorus Sulfur Chlorine Argon Potassium Calcium Scandium Titanium Vanadium Chromium Manganese "
            "Iron Cobalt Nickel Copper Zinc Gallium Germanium Arsenic Selenium Bromine Krypton Rubidium Strontium "
            "Yttrium Zirconium Niobium Molybdenum Technetium Ruthenium Rhodium Palladium Silver Cadmium Indium Tin "
            "Antimony Tellurium Iodine Xenon Caesium Barium Lanthanum Cerium Praseodymium Neodymium Promethium Samarium "
            "Europium Gadolinium Terbium Dysprosium Holmium Erbium Thulium Ytterbium Lutetium Hafnium Tantalum Tungsten "
            "Rhenium Osmium Iridium Platinum Gold Mercury Thallium Lead Bismuth Polonium Astatine Radon Francium Radium "
            "Actinium Thorium Protactinium Uranium Neptunium Plutonium Americium Curium Berkelium Californium "
            "Einsteinium Fermium Mendelevium Nobelium Lawrencium Rutherfordium Dubnium Seaborgium Bohrium Hassium "
            "Meitnerium Darmstadtium Roentgenium Copernicium Nihonium Flerovium Moscovium Livermorium Tennessine "
            "Oganesson").split()


class ChemError(ValueError):
    pass


# ----------------------------------------------------------------------------- Daten
@lru_cache(maxsize=None)
def _json(name: str):
    p = DATA / name
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def atomic_weights() -> dict:
    """{Symbol: {"value", "u", "interval"?, "mass_number"? (ohne Standard-Atomgewicht), "note"?}} plus "_source"."""
    d = _json("atomic_weights.json")
    if not d:
        raise ChemError("Atomgewichte fehlen (labcalc/data/atomic_weights.json)")
    return d


def isotope_masses() -> dict:
    """{"13C": {"mass_u", "u_u"}} aus AME2020, sofern vorhanden."""
    return (_json("isotopes.json") or {}).get("nuclides", {})


def name_resolver():
    """Hook: Stoffnamen -> Formel (wird vom Elementrechner mit der Namensliste belegt)."""
    return _RESOLVER[0]


_RESOLVER = [None]


def set_name_resolver(fn):
    _RESOLVER[0] = fn


# ----------------------------------------------------------------------------- Teilchen und Kerne
PARTICLES = {
    # Name: (Anzeige, mhchem, A, Z, Ladung in chemischen Gleichungen)
    "n": ("n", r"^{1}_{0}n", 1, 0, 0), "p": ("p", r"^{1}_{1}p", 1, 1, 1),
    "alpha": ("α", r"^{4}_{2}\alpha", 4, 2, 2), "α": ("α", r"^{4}_{2}\alpha", 4, 2, 2),
    "beta-": ("β⁻", r"\beta^-", 0, -1, -1), "β-": ("β⁻", r"\beta^-", 0, -1, -1), "β⁻": ("β⁻", r"\beta^-", 0, -1, -1),
    "beta+": ("β⁺", r"\beta^+", 0, 1, 1), "β+": ("β⁺", r"\beta^+", 0, 1, 1), "β⁺": ("β⁺", r"\beta^+", 0, 1, 1),
    "e+": ("e⁺", "e+", 0, 1, 1), "positron": ("e⁺", "e+", 0, 1, 1),
    "gamma": ("γ", r"\gamma", 0, 0, 0), "γ": ("γ", r"\gamma", 0, 0, 0),
    "nu": ("ν", r"\nu", 0, 0, 0), "ν": ("ν", r"\nu", 0, 0, 0), "nu_e": ("νₑ", r"\nu_e", 0, 0, 0),
    "antinu": ("ν̄", r"\bar{\nu}", 0, 0, 0), "nubar": ("ν̄", r"\bar{\nu}", 0, 0, 0), "ν̄": ("ν̄", r"\bar{\nu}", 0, 0, 0),
    "d": ("d", r"^{2}_{1}H", 2, 1, 1), "t": ("t", r"^{3}_{1}H", 3, 1, 1),
}

_SUP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻", "0123456789+-")
_SUB = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
_TO_SUB = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
_TO_SUP = str.maketrans("0123456789+-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻")
PHASES = ("s", "l", "g", "aq", "cr", "am")


@dataclass
class Species:
    text: str                                   # wie eingegeben (ohne Koeffizient)
    counts: dict = field(default_factory=dict)  # Element bzw. Isotop ("13C") -> Fraction
    charge: int = 0
    phase: str = ""
    kind: str = "chem"                          # chem | electron | particle | nuclide
    A: int | None = None                        # Massenzahl (Kerne, Teilchen)
    Z: int | None = None                        # Ordnungszahl bzw. Ladungszahl für Kernbilanz
    parts: list = field(default_factory=list)   # [(Faktor, Teilformel)] bei Hydraten
    name: str = ""                              # Name, falls aus der Namensliste aufgelöst
    hints: list = field(default_factory=list)

    @property
    def formula(self) -> str:
        """Normierte Formel ohne Phase (Schlüssel für Daten), z. B. 'SO4^2-'."""
        return self.text_formula(self.text)

    @staticmethod
    def text_formula(t):
        return re.sub(r"\((?:%s)\)$" % "|".join(PHASES), "", t.strip())

    def key(self) -> str:
        return self.formula + (f"({self.phase})" if self.phase else "")

    def unicode(self) -> str:
        if self.kind == "particle":
            return PARTICLES[self.text.strip()][0]
        if self.kind == "nuclide":
            return f"{str(self.A).translate(_TO_SUP)}{SYMBOLS[self.Z - 1]}"
        if self.kind == "electron":
            return "e⁻"
        core = _strip_charge(self.formula)[0]
        pieces = []
        for p in re.split(r"[·•*]", core.replace(" ", "")):
            pieces.extend(_dot_split(p))
        out = []
        for k, p in enumerate(pieces):
            lead = re.match(r"^(\d+(?:\.\d+)?|\d+/\d+)(?=[A-Z(\[{])", p) if k else None
            body = p[lead.end():] if lead else p
            body = re.sub(r"(?<=[A-Za-z\)\]\}])(\d+(?:\.\d+)?)", lambda m: m.group(1).translate(_TO_SUB), body)
            body = re.sub(r"\^\{?(\d+)\}?(?=[A-Z])", lambda m: m.group(1).translate(_TO_SUP), body)
            out.append((lead.group(1) if lead else "") + body)
        s = "·".join(out)
        if self.charge:
            q = abs(self.charge)
            s += (str(q) if q > 1 else "").translate(_TO_SUP) + ("⁺" if self.charge > 0 else "⁻")
        return s + (f"({self.phase})" if self.phase else "")

    def mhchem(self) -> str:
        if self.kind == "particle":
            return PARTICLES[self.text.strip()][1]
        if self.kind == "nuclide":
            return f"^{{{self.A}}}_{{{self.Z}}}{SYMBOLS[self.Z - 1]}"
        if self.kind == "electron":
            return "e-"
        core = _strip_charge(self.formula)[0]
        pieces = []
        for p in re.split(r"[·•*]", core.replace(" ", "")):
            pieces.extend(_dot_split(p))
        core = "*".join(pieces)
        core = re.sub(r"\^\{?(\d+)\}?(?=[A-Z])", r"^{\1}", core)
        if self.charge:
            q = abs(self.charge)
            core += "^{" + (str(q) if q > 1 else "") + ("+" if self.charge > 0 else "-") + "}"
        return core + (f"({self.phase})" if self.phase else "")

    def latex(self) -> str:
        """Formel für den Mathemodus ohne Zusatzpaket (Bericht): ``\\mathrm{SO_{4}}^{2-}``."""
        if self.kind == "particle":
            m = PARTICLES[self.text.strip()][1]
            if m == "e+":
                return r"\mathrm{e}^{+}"
            return re.sub(r"^\^\{(\d+)\}_\{(\d+)\}([A-Za-z]+)$", r"{}^{\1}_{\2}\\mathrm{\3}", m).replace(r"\mathrm{\alpha}", r"\alpha")
        if self.kind == "nuclide":
            return r"{}^{%d}_{%d}\mathrm{%s}" % (self.A, self.Z, SYMBOLS[self.Z - 1])
        if self.kind == "electron":
            return r"\mathrm{e}^{-}"
        if self.kind == "unknown":
            return "?"
        core = _strip_charge(self.formula)[0]
        pieces = []
        for p in re.split(r"[·•*]", core.replace(" ", "")):
            pieces.extend(_dot_split(p))
        out = []
        for k, p in enumerate(pieces):
            lead = re.match(r"^(\d+(?:\.\d+)?|\d+/\d+)(?=[A-Z(\[{])", p) if k else None
            body = p[lead.end():] if lead else p
            body = body.replace("{", r"\{").replace("}", r"\}")
            body = re.sub(r"\^(\d+)(?=[A-Z])", r"{}^{\1}", body)
            body = re.sub(r"(?<=[A-Za-z\)\]\}])(\d+(?:\.\d+)?)", r"_{\1}", body)
            out.append((lead.group(1) + r"\," if lead else "") + body)
        s = r"\mathrm{" + r"\cdot ".join(out) + "}"
        if self.charge:
            q = abs(self.charge)
            s += "^{" + (str(q) if q > 1 else "") + ("+" if self.charge > 0 else "-") + "}"
        return s + (r"\,(\mathrm{%s})" % self.phase if self.phase else "")

    def to_dict(self) -> dict:
        return {"text": self.text, "formula": self.formula, "unicode": self.unicode(), "mhchem": self.mhchem(),
                "counts": {k: _num(v) for k, v in self.counts.items()}, "charge": self.charge, "phase": self.phase,
                "kind": self.kind, "A": self.A, "Z": self.Z, "name": self.name, "hints": self.hints}


def _num(f: Fraction):
    return int(f) if f.denominator == 1 else float(f)


def _strip_charge(s: str) -> tuple[str, int, list]:
    """Ladung am Ende abtrennen -> (Formel, Ladung, Hinweise)."""
    s = s.translate(_SUP).strip()
    hints = []
    m = re.search(r"\^\{?(\d*)([+-])\}?$", s) or re.search(r"\^\{?([+-])(\d*)\}?$", s)
    if m:
        a, b = m.group(1), m.group(2)
        sign, num = (b, a) if b in "+-" else (a, b)
        q = int(num) if num else 1
        return s[:m.start()], q if sign == "+" else -q, hints
    m = re.search(r"([+-])(\d+)$", s)                          # Fe+3
    if m and re.search(r"[A-Za-z\)\]]$", s[:m.start()]):
        q = int(m.group(2))
        return s[:m.start()], q if m.group(1) == "+" else -q, hints
    m = re.search(r"(\++|-+)$", s)                              # NH4+, Cl-, Ca++
    if m:
        q = len(m.group(1))
        core = s[:m.start()]
        mm = re.search(r"([A-Z][a-z]?)(\d+)$", core)
        if mm and re.fullmatch(r"[A-Z][a-z]?\d+", core):        # Fe3+ -> Fe₃⁺ (wie mhchem), Hinweis
            hints.append(f"„{s}“ wird als {mm.group(1)}{mm.group(2).translate(_TO_SUB)} mit Ladung "
                         f"{'+' if m.group(1)[0] == '+' else '-'}{q if q > 1 else ''} gelesen; für "
                         f"{mm.group(1)}{(mm.group(2) + m.group(1)[0]).translate(_TO_SUP)} bitte "
                         f"{mm.group(1)}^{mm.group(2)}{m.group(1)[0]} schreiben.")
        return core, q if m.group(1)[0] == "+" else -q, hints
    return s, 0, hints


def _formula_counts(f: str) -> dict:
    """Formel ohne Ladung/Phase -> {Element|Isotop: Fraction}."""
    f = f.replace(" ", "").translate(_SUB)
    if not f:
        raise ChemError("Leere Formel")
    total: dict = {}
    for k, part in _hydrate_parts(f):
        for el, n in _group_counts(part).items():
            total[el] = total.get(el, Fraction(0)) + k * n
    return total


def _hydrate_parts(f: str) -> list:
    pieces = re.split(r"[·•*]", f)
    out = []
    for p in pieces:
        out.extend(_dot_split(p))
    res = []
    for p in out:
        m = re.match(r"^(\d+(?:\.\d+)?|\d+/\d+)(?=[A-Z(\[{])", p)
        if m and p is not out[0]:
            res.append((Fraction(m.group(1)), p[m.end():]))
        else:
            res.append((Fraction(1), p))
    return res


def _dot_split(p: str) -> list:
    """„CuSO4.5H2O“ als Hydrat lesen, „Fe0.95O“ als Bruchindex."""
    m = re.search(r"(?<=[A-Za-z\d\)\]])\.(\d{1,2})(?=[A-Z(])", p)
    if not m or int(m.group(1)) == 0:
        return [p]
    left, right = p[:m.start()], p[m.start() + 1:]
    try:
        _group_counts(left)
        if re.search(r"(?<![\d.])0$", left):
            return [p]
        return [left] + _dot_split(right)
    except ChemError:
        return [p]


_OPEN = {"(": ")", "[": "]", "{": "}"}


def _group_counts(f: str) -> dict:
    stack = [dict()]
    closers = []
    i = 0
    num = r"(\d+/\d+|\d+(?:\.\d+)?)"
    while i < len(f):
        c = f[i]
        if c in _OPEN:
            stack.append({})
            closers.append(_OPEN[c])
            i += 1
            continue
        if c in ")]}":
            if not closers or closers.pop() != c:
                raise ChemError(f"Klammern passen nicht in „{f}“")
            i += 1
            m = re.match(num, f[i:])
            k = Fraction(m.group(1)) if m else Fraction(1)
            i += m.end() if m else 0
            g = stack.pop()
            for el, n in g.items():
                stack[-1][el] = stack[-1].get(el, Fraction(0)) + n * k
            continue
        m = re.match(r"\^\{?(\d+)\}?", f[i:])                   # Isotop vor dem Symbol
        iso = None
        if m:
            iso = int(m.group(1))
            i += m.end()
        m = re.match(r"[A-Z][a-z]?", f[i:])
        if not m:
            raise ChemError(f"„{f}“: unerwartetes Zeichen „{f[i]}“ an Stelle {i + 1}"
                            + (" (Elementsymbole beginnen mit Grossbuchstaben)" if f[i].islower() else ""))
        sym = m.group()
        if sym not in _SYMSET and len(sym) == 2 and sym[0] in _SYMSET:
            sym = sym[0]
        if sym not in _SYMSET:
            if sym in ("D", "T"):
                iso, sym = (2 if sym == "D" else 3), "H"
                i += 1
            else:
                raise ChemError(f"„{f}“: unbekanntes Element „{m.group()}“")
        else:
            i += len(sym)
        m = re.match(num, f[i:])
        k = Fraction(m.group(1)) if m else Fraction(1)
        if m and k == 0:
            raise ChemError(f"„{f}“: Index 0")
        i += m.end() if m else 0
        key = f"{iso}{sym}" if iso else sym
        stack[-1][key] = stack[-1].get(key, Fraction(0)) + k
    if len(stack) != 1:
        raise ChemError(f"Klammern passen nicht in „{f}“")
    return stack[0]


def parse_species(text: str, nuclear: bool = False) -> Species:
    t = text.strip()
    if not t:
        raise ChemError("Leerer Stoff")
    phase = ""
    m = re.search(r"\((%s)\)$" % "|".join(PHASES), t)
    if m:
        phase = m.group(1)
    core = Species.text_formula(t)
    if core == "?":
        if not nuclear:
            raise ChemError("Der Platzhalter ? ist nur in Kerngleichungen möglich (fehlendes Teilchen bzw. fehlender Kern)")
        return Species("?", {}, 0, phase, "unknown")
    low = core.lower() if core not in ("D", "T") else core
    if core in ("e-", "e^-", "e⁻", "e"):
        if nuclear:
            return Species(t, {}, -1, phase, "particle", 0, -1)
        return Species(t, {}, -1, phase, "electron")
    if low in PARTICLES and core not in _SYMSET:
        _, _, A, Z, q = PARTICLES[low]
        return Species(low, {}, q, phase, "particle", A, Z)
    m = (re.fullmatch(r"\^\{?(\d+)\}?(?:_\{?(\d+)\}?)?([A-Z][a-z]?)", core)
         or re.fullmatch(r"([A-Z][a-z]?)-(\d+)", core))
    if m:
        if core[0] == "^":
            A, zgiven, sym = int(m.group(1)), m.group(2), m.group(3)
        else:
            sym, A, zgiven = m.group(1), int(m.group(2)), None
        if sym not in _SYMSET:
            raise ChemError(f"Unbekanntes Element „{sym}“")
        Z = Z_OF[sym]
        sp = Species(t, {f"{A}{sym}": Fraction(1)}, 0, phase, "nuclide", A, Z)
        if zgiven is not None and int(zgiven) != Z:
            sp.hints.append(f"Angegebene Ordnungszahl {zgiven} passt nicht zu {sym} (Z = {Z}); verwendet wird {Z}.")
        return sp
    try:
        f, q, hints = _strip_charge(core)
        counts = _formula_counts(f)
        return Species(t, counts, q, phase, "chem", hints=hints)
    except ChemError as err:
        res = name_resolver()
        if res:
            hit = res(core)
            if hit:
                sp = parse_species(hit["formula"] + (f"({phase})" if phase and "(" not in hit["formula"][-4:] else ""), nuclear)
                sp.name = hit.get("name") or core
                sp.hints.append(f"„{core}“ gelesen als {sp.unicode()} ({hit.get('name') or core}).")
                return sp
        raise err


# ----------------------------------------------------------------------------- Gleichungen
ARROWS = [("<=>", True), ("<->", True), ("⇌", True), ("⇄", True), ("->", False), ("→", False), ("⟶", False),
          ("=>", False), ("=", False)]
_START = re.compile(r"[\dA-Z(\[{^αβγνenpd]|alpha|beta|gamma|nu", re.I)


@dataclass
class Term:
    coef: Fraction | None
    species: Species
    side: int                                   # -1 Edukt, +1 Produkt


@dataclass
class Equation:
    terms: list
    reversible: bool = False
    nuclear: bool = False
    text: str = ""

    @property
    def reactants(self):
        return [t for t in self.terms if t.side < 0]

    @property
    def products(self):
        return [t for t in self.terms if t.side > 0]


def _split_side(s: str) -> list[str]:
    out, cur, i = [], "", 0
    while i < len(s):
        c = s[i]
        if c == "^":                                            # Ladung bzw. Isotop: bis Ende der Hochzahl
            m = re.match(r"\^\{[^}]*\}|\^[\d]*[+-]?|\^[+-]\d*", s[i:])
            cur += m.group() if m else c
            i += len(m.group()) if m else 1
            continue
        if c == "+":
            j = i + 1
            while j < len(s) and s[j] == " ":
                j += 1
            nxt = s[j] if j < len(s) else ""
            before_space = i > 0 and s[i - 1] == " "
            if nxt == "" or nxt == "+" or nxt in ")]}":
                cur += c                                        # Ladung
            elif cur.strip() == "":
                cur += c
            elif before_space and j > i + 1:
                out.append(cur)
                cur = ""
            elif _START.match(s[j:]):
                if re.search(r"\(\s*$", cur):
                    cur += c
                else:
                    out.append(cur)
                    cur = ""
            else:
                cur += c
            i += 1
            continue
        cur += c
        i += 1
    out.append(cur)
    return [x.strip() for x in out if x.strip()]


def parse_equation(text: str) -> Equation:
    t = str(text).strip()
    if not t:
        raise ChemError("Keine Gleichung")
    arrow = None
    for a, rev in ARROWS:
        k = t.find(a)
        if k >= 0 and not (a == "=" and (t[k - 1:k] in "<>!" or t[k + 1:k + 2] in ">")):
            arrow = (a, rev, k)
            break
    if not arrow:
        sides = [(t, -1)]
        rev = False
    else:
        a, rev, k = arrow
        left, right = t[:k], t[k + len(a):]
        if any(x in right for x, _ in ARROWS if x not in ("=",)) or right.count("->") or "=" in right.replace("=>", ""):
            raise ChemError("Mehr als ein Reaktionspfeil")
        sides = [(left, -1), (right, +1)]
    raw = []
    for s, sign in sides:
        if not s.strip():
            raise ChemError("Eine Seite der Gleichung ist leer")
        for part in _split_side(s):
            m = re.match(r"^(\d+/\d+|\d+\.\d+|\d+|\?)\s*(?=[A-Za-z(\[{^αβγν])", part)
            coef = None
            body = part
            if m and m.group(1) != "?":
                coef = Fraction(m.group(1))
                body = part[m.end():]
                if coef == 0:
                    raise ChemError(f"Koeffizient 0 bei „{part}“")
            elif m:
                body = part[m.end():]
            raw.append((coef, body, sign))
    nuclear = any(_looks_nuclear(b) for _, b, _ in raw)
    terms = [Term(c, parse_species(b, nuclear), sg) for c, b, sg in raw]
    return Equation(terms, rev, nuclear, t)


def _looks_nuclear(b: str) -> bool:
    core = Species.text_formula(b)
    if core in ("D", "T"):
        return False
    if core.lower() in PARTICLES and core not in _SYMSET and core.lower() not in ("e", "p", "d", "t"):
        return True
    if core in ("n",):
        return True
    return bool(re.fullmatch(r"\^\{?\d+\}?(?:_\{?\d+\}?)?[A-Z][a-z]?|[A-Z][a-z]?-\d+", core))


# ----------------------------------------------------------------------------- Lineare Algebra mit Brüchen
def _rref(M: list[list[Fraction]]):
    A = [row[:] for row in M]
    rows = len(A)
    cols = len(A[0]) if A else 0
    piv = []
    r = 0
    for c in range(cols):
        p = next((i for i in range(r, rows) if A[i][c] != 0), None)
        if p is None:
            continue
        A[r], A[p] = A[p], A[r]
        pv = A[r][c]
        A[r] = [x / pv for x in A[r]]
        for i in range(rows):
            if i != r and A[i][c] != 0:
                f = A[i][c]
                A[i] = [x - f * y for x, y in zip(A[i], A[r])]
        piv.append(c)
        r += 1
        if r == rows:
            break
    return A, piv


def nullspace(M: list[list[Fraction]]) -> list[list[Fraction]]:
    cols = len(M[0]) if M else 0
    if not M:
        return [[Fraction(int(i == j)) for i in range(cols)] for j in range(cols)]
    R, piv = _rref(M)
    free = [c for c in range(cols) if c not in piv]
    basis = []
    for f in free:
        v = [Fraction(0)] * cols
        v[f] = Fraction(1)
        for i, pc in enumerate(piv):
            v[pc] = -R[i][f]
        basis.append(v)
    return basis


def _integerise(v: list[Fraction]) -> list[int]:
    den = 1
    for x in v:
        den = den * x.denominator // math.gcd(den, x.denominator)
    ints = [int(x * den) for x in v]
    g = 0
    for x in ints:
        g = math.gcd(g, abs(x))
    return [x // g for x in ints] if g else ints


def conserved(eq: Equation) -> tuple[list[str], list[list[Fraction]]]:
    """Erhaltungsgrössen (Zeilen) × Stoffe (Spalten), Edukte negativ."""
    if eq.nuclear:
        rows = ["A", "Z"]
        M = [[], []]
        for t in eq.terms:
            sp = t.species
            if sp.kind in ("nuclide", "particle"):
                A, Z = sp.A, sp.Z
            else:                                               # Atome in Kerngleichungen: Summe der Kerne
                A = sum(int(n) * _mass_number(k) for k, n in sp.counts.items())
                Z = sum(int(n) * Z_OF[re.sub(r"^\d+", "", k)] for k, n in sp.counts.items())
            M[0].append(Fraction(A * t.side))
            M[1].append(Fraction(Z * t.side))
        return rows, M
    keys = []
    for t in eq.terms:
        for k in t.species.counts:
            if k not in keys:
                keys.append(k)
    keys.sort(key=lambda k: (Z_OF.get(re.sub(r"^\d+", "", k), 999), k))
    rows = keys + (["Ladung"] if any(t.species.charge for t in eq.terms) else [])
    M = []
    for k in keys:
        M.append([t.species.counts.get(k, Fraction(0)) * t.side for t in eq.terms])
    if "Ladung" in rows:
        M.append([Fraction(t.species.charge * t.side) for t in eq.terms])
    return rows, M


def _mass_number(key: str) -> int:
    m = re.match(r"^(\d+)([A-Z][a-z]?)$", key)
    if m:
        return int(m.group(1))
    raise ChemError(f"In einer Kerngleichung braucht {key} eine Massenzahl (z. B. ^12C)")


SOLVABLE_PARTICLES = {"n", "p", "alpha", "α", "beta-", "β-", "β⁻", "beta+", "β+", "β⁺", "e+", "positron", "d", "t"}


def _identify(dA: int, dZ: int) -> str | None:
    table = {(1, 0): "n", (1, 1): "p", (4, 2): "alpha", (0, -1): "beta-", (0, 1): "beta+", (2, 1): "^2H",
             (3, 1): "^3H", (0, 0): "gamma"}
    if (dA, dZ) in table:
        return table[(dA, dZ)]
    if dA >= 1 and 1 <= dZ <= len(SYMBOLS) and dA >= dZ:
        return f"^{dA}{SYMBOLS[dZ - 1]}"
    return None


def _balance_nuclear(eq: Equation) -> dict:
    """Kerngleichung: Kerne und Edukt-Teilchen standardmässig einmal, Produkt-Teilchen werden bestimmt, ? wird erkannt."""
    unknown = [i for i, t in enumerate(eq.terms) if t.species.kind == "unknown"]
    if len(unknown) > 1:
        return {"status": "impossible", "reason": "Höchstens ein Platzhalter ? je Gleichung."}
    coefs = [t.coef for t in eq.terms]
    solve = [i for i, t in enumerate(eq.terms) if t.coef is None and t.side > 0 and t.species.kind == "particle"
             and t.species.text in SOLVABLE_PARTICLES and not unknown]
    for i, t in enumerate(eq.terms):
        if coefs[i] is None and i not in solve:
            coefs[i] = Fraction(1)
    note = None
    if unknown:
        u = unknown[0]
        sub = Equation([t for i, t in enumerate(eq.terms) if i != u], eq.reversible, True, eq.text)
        names, M = conserved(sub)
        cf = [c for i, c in enumerate(coefs) if i != u]
        dA = -sum(a * c for a, c in zip(M[0], cf))
        dZ = -sum(a * c for a, c in zip(M[1], cf))
        side = eq.terms[u].side
        dA, dZ = dA * side / coefs[u], dZ * side / coefs[u]
        if dA.denominator != 1 or dZ.denominator != 1:
            return {"status": "impossible", "reason": "Für ? ergibt sich keine ganze Massen- bzw. Ordnungszahl."}
        name = _identify(int(dA), int(dZ))
        if not name:
            return {"status": "impossible", "reason": f"Für ? fehlen A = {int(dA)}, Z = {int(dZ)}; das ist kein Teilchen "
                                                      "und kein Kern."}
        eq.terms[u] = Term(eq.terms[u].coef, parse_species(name, True), side)
        note = f"? = {eq.terms[u].species.unicode()} (A = {int(dA)}, Z = {int(dZ)})"
    names, M = conserved(eq)
    if solve:
        k = len(solve)
        known = [i for i in range(len(eq.terms)) if i not in solve]
        A = [[row[i] for i in solve] + [-sum(row[j] * coefs[j] for j in known)] for row in M]
        R, piv = _rref(A)
        if k in piv:
            trial = [c if c is not None else Fraction(1) for c in coefs]
            diff = [f"{names[r]}: links {_num(sum(-a * c for a, c in zip(row, trial) if a < 0))}, "
                    f"rechts {_num(sum(a * c for a, c in zip(row, trial) if a > 0))}"
                    for r, row in enumerate(M) if sum(a * c for a, c in zip(row, trial)) != 0]
            return {"status": "impossible", "rows": names,
                    "reason": "Massen- und Ordnungszahl lassen sich mit diesen Teilchen nicht ausgleichen ("
                              + "; ".join(diff) + ")."}
        if len(piv) < k:
            return {"status": "ambiguous", "rows": names, "dim": k - len(piv),
                    "reason": "Zu viele unbekannte Teilchen; bitte Koeffizienten vorgeben."}
        for r, pc in enumerate(piv):
            coefs[solve[pc]] = R[r][k]
        bad = [eq.terms[i].species.unicode() for i in solve if coefs[i] < 0 or coefs[i].denominator != 1]
        if bad:
            return {"status": "sign", "rows": names, "coefs": coefs,
                    "reason": f"{', '.join(bad)}: keine sinnvolle (positive, ganze) Anzahl; Gleichung prüfen."}
        if any(coefs[i] == 0 for i in solve):
            zero = [eq.terms[i].species.unicode() for i in solve if coefs[i] == 0]
            return {"status": "sign", "rows": names, "coefs": coefs, "reason": f"{', '.join(zero)} entsteht nicht (0)."}
    bad = [(names[r], sum(-a * c for a, c in zip(row, coefs) if a < 0), sum(a * c for a, c in zip(row, coefs) if a > 0))
           for r, row in enumerate(M) if sum(a * c for a, c in zip(row, coefs)) != 0]
    res = {"rows": names, "nuclear": True, "reversible": eq.reversible, "coefs": coefs}
    if bad:
        res.update(status="given_wrong" if all(t.coef is not None for t in eq.terms) else "impossible",
                   unbalanced=[b[0] for b in bad],
                   reason="; ".join(f"{n}: links {_num(l)}, rechts {_num(r)}" for n, l, r in bad) + ".")
    else:
        res["status"] = "ok"
    if note:
        res["identified"] = note
    return _finish(eq, res, M)


def balance(eq: Equation) -> dict:
    """Koeffizienten bestimmen. Ergebnis mit status ok | given_ok | given_wrong | impossible | ambiguous | sign."""
    if eq.nuclear:
        return _balance_nuclear(eq)
    names, M = conserved(eq)
    n = len(eq.terms)
    fixed = {i: t.coef for i, t in enumerate(eq.terms) if t.coef is not None}
    res = {"rows": names, "nuclear": eq.nuclear, "reversible": eq.reversible}
    if len(fixed) == n:
        coefs = [t.coef for t in eq.terms]
        bad = [names[r] for r, row in enumerate(M) if sum(a * c for a, c in zip(row, coefs)) != 0]
        res.update(status="given_ok" if not bad else "given_wrong", coefs=coefs, unbalanced=bad)
        if bad:
            # zusätzlich die richtige Lösung anbieten
            alt = _solve(eq, M, {}, names)
            if alt.get("status") == "ok":
                res["suggestion"] = alt["coefs"]
        return _finish(eq, res, M)
    out = _solve(eq, M, fixed, names)
    res.update(out)
    return _finish(eq, res, M)


def _solve(eq, M, fixed, names):
    n = len(eq.terms)
    free = [i for i in range(n) if i not in fixed]
    one_sided = [r for r, row in enumerate(M) if names[r] != "Ladung"
                 and (any(x > 0 for x in row) != any(x < 0 for x in row))]
    if one_sided:
        return {"status": "impossible", "reason": _why_impossible(eq, M, names)}
    if not fixed:
        N = nullspace(M)
        if not N:
            return {"status": "impossible", "reason": _why_impossible(eq, M, names)}
        if len(N) > 1:
            basis = _nice_basis(N)
            return {"status": "ambiguous", "basis": basis, "dim": len(N),
                    "reason": f"Die Gleichung ist nicht eindeutig: {len(N)} unabhängige Reaktionen stecken darin. "
                              "Jede Kombination der Grundlösungen ist ausgeglichen; mehr Angaben (feste Koeffizienten "
                              "oder weniger Stoffe) machen sie eindeutig."}
        v = _integerise(N[0])
        if sum(1 for x in v if x < 0) > sum(1 for x in v if x > 0):
            v = [-x for x in v]
        if any(x <= 0 for x in v):
            return _sign_problem(eq, v)
        return {"status": "ok", "coefs": [Fraction(x) for x in v]}
    # feste Koeffizienten: A_u x_u = -A_f x_f
    Au = [[row[i] for i in free] for row in M]
    b = [-sum(row[i] * fixed[i] for i in fixed) for row in M]
    aug = [r + [bb] for r, bb in zip(Au, b)]
    R, piv = _rref(aug)
    k = len(free)
    if k in piv:
        clash = []
        for r, row in enumerate(M):
            if all(a == 0 or i in fixed for i, a in enumerate(row)):
                l = sum(-a * fixed[i] for i, a in enumerate(row) if a < 0)
                rr = sum(a * fixed[i] for i, a in enumerate(row) if a > 0)
                if l != rr:
                    clash.append(f"{names[r]}: links {_num(l)}, rechts {_num(rr)}")
        why = ("; ".join(clash) + ".") if clash else _why_impossible(eq, M, names)
        return {"status": "impossible", "reason": "Mit den vorgegebenen Koeffizienten lässt sich die Gleichung nicht "
                                                  "ausgleichen. " + why}
    if len(piv) < k:
        return {"status": "ambiguous", "dim": k - len(piv),
                "reason": "Mit den vorgegebenen Koeffizienten bleiben die übrigen nicht eindeutig; bitte weitere festlegen."}
    x = [Fraction(0)] * k
    for i, pc in enumerate(piv):
        x[pc] = R[i][k]
    coefs = [None] * n
    for i, v in fixed.items():
        coefs[i] = Fraction(v)
    for j, i in enumerate(free):
        coefs[i] = x[j]
    if any(c <= 0 for c in coefs):
        return _sign_problem(eq, coefs)
    return {"status": "ok", "coefs": coefs}


def _sign_problem(eq, v):
    neg = [eq.terms[i].species.unicode() for i, x in enumerate(v) if x < 0]
    zero = [eq.terms[i].species.unicode() for i, x in enumerate(v) if x == 0]
    msg = []
    if neg:
        msg.append(f"{', '.join(neg)} müsste{'n' if len(neg) > 1 else ''} auf der anderen Seite stehen")
    if zero:
        msg.append(f"{', '.join(zero)} nimmt nicht teil (Koeffizient 0)")
    return {"status": "sign", "coefs": [Fraction(x) for x in v], "reason": "; ".join(msg) + "."}


def _why_impossible(eq, M, names) -> str:
    one_sided = []
    for r, row in enumerate(M):
        pos = any(x > 0 for x in row)
        neg = any(x < 0 for x in row)
        if pos != neg:
            side = "rechts" if pos else "links"
            one_sided.append(f"{names[r]} kommt nur {side} vor")
    if one_sided:
        return "; ".join(one_sided) + "."
    return ("Kein Satz positiver Koeffizienten erfüllt alle Bilanzen gleichzeitig; prüfen Sie Formeln, Ladungen und "
            "ob ein Stoff fehlt (z. B. H₂O, H⁺, OH⁻ oder e⁻).")


def _nice_basis(N):
    R, _ = _rref([row[:] for row in N])
    return [_integerise(r) for r in R if any(x != 0 for x in r)]


def _finish(eq, res, M):
    res["matrix"] = [[_frac_str(x) for x in row] for row in M]
    coefs = res.get("coefs")
    if coefs and res.get("status") in ("ok", "given_ok"):
        res["text"] = format_equation(eq, coefs)
        res["mhchem"] = format_equation(eq, coefs, "mhchem")
        res["latex"] = format_equation(eq, coefs, "latex")
        res["balance"] = [{"row": res["rows"][r],
                           "left": _num(sum(-a * c for a, c in zip(row, coefs) if a < 0)),
                           "right": _num(sum(a * c for a, c in zip(row, coefs) if a > 0))}
                          for r, row in enumerate(M)]
    if res.get("suggestion"):
        res["suggestion_text"] = format_equation(eq, res["suggestion"])
    for k in ("coefs", "suggestion"):
        if res.get(k):
            res[k] = [_frac_str(c) for c in res[k]]
    res["species"] = [t.species.to_dict() | {"side": t.side} for t in eq.terms]
    res["hints"] = [h for t in eq.terms for h in t.species.hints]
    return res


def _frac_str(c) -> str:
    c = Fraction(c)
    return str(c.numerator) if c.denominator == 1 else f"{c.numerator}/{c.denominator}"


def format_equation(eq: Equation, coefs, style: str = "unicode") -> str:
    arrow = {"unicode": "⇌" if eq.reversible else "→", "mhchem": "<=>" if eq.reversible else "->",
             "latex": r"\rightleftharpoons" if eq.reversible else r"\longrightarrow"}[style]
    sides = {-1: [], 1: []}
    for t, c in zip(eq.terms, coefs):
        c = Fraction(c)
        if style == "latex":
            cs = "" if c == 1 else ((str(c.numerator) if c.denominator == 1 else r"%d/%d" % (c.numerator, c.denominator)) + r"\,")
            sides[t.side].append(cs + t.species.latex())
            continue
        cs = "" if c == 1 else (_frac_str(c) + " ")
        sides[t.side].append(cs + (t.species.unicode() if style == "unicode" else t.species.mhchem()))
    left = " + ".join(sides[-1])
    return left + (f" {arrow} " + " + ".join(sides[1]) if sides[1] else "")


# ----------------------------------------------------------------------------- Massen
def element_weight(key: str) -> tuple[float, float, dict]:
    """Relative Atommasse eines Elements (Standard-Atomgewicht, gekürzt) bzw. Isotops (AME2020)."""
    m = re.match(r"^(\d+)([A-Z][a-z]?)$", key)
    if m:
        iso = isotope_masses().get(key)
        if not iso:
            raise ChemError(f"Isotopenmasse von {key} nicht vorhanden")
        return iso["mass_u"], iso.get("u_u", 0.0), {"isotope": True, "source": "ame2020"}
    w = atomic_weights().get(key)
    if not w:
        raise ChemError(f"Kein Atomgewicht für {key}")
    if w.get("value") is None:
        mn = w.get("mass_number")
        return float(mn), 0.0, {"no_standard": True, "mass_number": mn}
    return w["value"], w.get("u", 0.0), {}


def molar_mass(sp: Species | str) -> dict:
    """M in g/mol mit Unsicherheit (gleiche Elemente voll korreliert, verschiedene unabhängig) und Massenanteilen."""
    if isinstance(sp, str):
        sp = parse_species(sp)
    if sp.kind == "electron":
        raise ChemError("Elektronen haben in chemischen Rechnungen keine molare Masse")
    if sp.kind == "particle":
        raise ChemError("Für Teilchen bitte die Kernmasse verwenden")
    total, var = 0.0, 0.0
    rows, notes = [], []
    for k, n in sp.counts.items():
        a, u, info = element_weight(k)
        nf = float(n)
        total += nf * a
        var += (nf * u) ** 2
        rows.append({"el": k, "n": _num(n), "Ar": a, "u": u, "mass": nf * a, **info})
        if info.get("no_standard"):
            notes.append(f"{k} hat kein Standard-Atomgewicht; verwendet wird die Massenzahl des langlebigsten "
                         f"Isotops [{info['mass_number']}].")
    for r in rows:
        r["frac"] = r["mass"] / total if total else 0.0
    return {"M": total, "u": math.sqrt(var), "unit": "g/mol", "rows": rows, "notes": notes,
            "formula": sp.unicode(), "source": atomic_weights().get("_source", "ciaaw2024")}


def relative_atomic_mass(sym: str) -> float:
    return element_weight(sym.strip())[0]


def empirical_formula(fractions: dict, M: float | None = None, tol: float = 0.03) -> dict:
    """Summenformel aus Massenanteilen (Elementaranalyse); mit molarer Masse auch die Molekülformel."""
    if not fractions:
        raise ChemError("Keine Massenanteile")
    s = sum(float(v) for v in fractions.values())
    if s <= 0:
        raise ChemError("Massenanteile müssen positiv sein")
    mol = {el: float(v) / element_weight(el)[0] for el, v in fractions.items() if float(v) > 0}
    mn = min(mol.values())
    ratio = {el: x / mn for el, x in mol.items()}
    best = None
    for k in range(1, 13):
        err = max(abs(r * k - round(r * k)) for r in ratio.values())
        if err <= tol * k or err <= tol:
            best = (k, err)
            break
    if best is None:
        k = min(range(1, 13), key=lambda k: max(abs(r * k - round(r * k)) for r in ratio.values()))
        best = (k, max(abs(r * k - round(r * k)) for r in ratio.values()))
    k = best[0]
    ints = {el: int(round(r * k)) for el, r in ratio.items()}
    emp = _hill(ints)
    out = {"empirical": emp, "ratio": ratio, "multiplier": k, "max_deviation": best[1], "sum_percent": s}
    if s < 99 or s > 101:
        out.setdefault("notes", []).append(f"Summe der Anteile {s:.1f} % (nicht 100 %); fehlt ein Element (oft O)?")
    if M:
        Me = molar_mass(emp)["M"]
        f = M / Me
        nf = max(1, round(f))
        out["molecular"] = _hill({el: v * nf for el, v in ints.items()})
        out["factor"] = f
        if abs(f - nf) > 0.05 * nf:
            out.setdefault("notes", []).append(f"M / M(empirisch) = {f:.2f} ist keine ganze Zahl; Werte prüfen.")
    return out


def _hill(counts: dict) -> str:
    """Formel nach Hill: C, dann H, dann alphabetisch (ohne C: alphabetisch)."""
    keys = list(counts)
    if "C" in counts:
        order = ["C"] + (["H"] if "H" in counts else []) + sorted(k for k in keys if k not in ("C", "H"))
    else:
        order = sorted(keys)
    return "".join(k + (str(counts[k]) if counts[k] != 1 else "") for k in order if counts[k])


def hill_formula(sp: Species | str) -> str:
    if isinstance(sp, str):
        sp = parse_species(sp)
    c = {k: (int(v) if v.denominator == 1 else float(v)) for k, v in sp.counts.items()}
    s = _hill(c)
    if sp.charge:
        q = abs(sp.charge)
        s += f"^{q if q > 1 else ''}{'+' if sp.charge > 0 else '-'}"
    return s


def unsaturation(sp: Species | str) -> float | None:
    """Doppelbindungsäquivalente (C, H, N, O, Halogene, S, Si, P)."""
    if isinstance(sp, str):
        sp = parse_species(sp)
    c = {re.sub(r"^\d+", "", k): float(v) for k, v in sp.counts.items()}
    if "C" not in c or any(k not in ("C", "H", "N", "O", "S", "F", "Cl", "Br", "I", "Si", "P") for k in c):
        return None
    C = c.get("C", 0) + c.get("Si", 0)
    H = c.get("H", 0) + sum(c.get(x, 0) for x in ("F", "Cl", "Br", "I"))
    N = c.get("N", 0) + c.get("P", 0)
    return C - H / 2 + N / 2 + 1


# ----------------------------------------------------------------------------- Stöchiometrie
R_GAS = 6.02214076e23 * 1.380649e-23   # J/(mol K), exakt: R = N_A·k (SI 2019), volle Genauigkeit
FARADAY = 6.02214076e23 * 1.602176634e-19   # C/mol, exakt: F = N_A·e (SI 2019)


def amount(entry: dict, sp: Species) -> dict:
    """Stoffmenge aus einer Mengenangabe {mass_g | n_mol | V_L (+T_K, p_Pa) | c_molL + V_L}."""
    if entry.get("n_mol") is not None:
        return {"n": float(entry["n_mol"]), "how": "n"}
    if entry.get("mass_g") is not None:
        M = molar_mass(sp)["M"]
        return {"n": float(entry["mass_g"]) / M, "how": "m/M", "M": M}
    if entry.get("c_molL") is not None and entry.get("V_L") is not None:
        return {"n": float(entry["c_molL"]) * float(entry["V_L"]), "how": "c·V"}
    if entry.get("V_L") is not None:
        T = float(entry.get("T_K") or 273.15)
        p = float(entry.get("p_Pa") or 101325.0)
        return {"n": p * float(entry["V_L"]) * 1e-3 / (R_GAS * T), "how": "pV/RT", "T": T, "p": p}
    raise ChemError("Mengenangabe unvollständig")


def stoichiometry(eq: Equation, coefs, amounts: dict, actual: dict | None = None) -> dict:
    """amounts: {Index: Mengenangabe}. Limitierender Stoff, theoretische Mengen, Überschuss, Ausbeute, Atomökonomie."""
    coefs = [Fraction(c) for c in coefs]
    rows = []
    known = {}
    for i, t in enumerate(eq.terms):
        if str(i) in amounts or i in amounts:
            a = amounts.get(str(i), amounts.get(i))
            known[i] = amount(a, t.species)
    reac = [i for i, t in enumerate(eq.terms) if t.side < 0]
    given_reac = [i for i in reac if i in known]
    if not given_reac:
        raise ChemError("Mindestens eine Eduktmenge angeben")
    xi = {i: known[i]["n"] / float(coefs[i]) for i in given_reac}
    lim = min(xi, key=xi.get)
    x = xi[lim]
    for i, t in enumerate(eq.terms):
        nu = float(coefs[i])
        try:
            M = molar_mass(t.species)["M"] if t.species.kind == "chem" else None
        except ChemError:
            M = None
        r = {"i": i, "species": t.species.unicode(), "side": t.side, "nu": _frac_str(coefs[i]), "M": M}
        if t.side < 0:
            r["n_start"] = known[i]["n"] if i in known else None
            r["n_used"] = nu * x
            r["n_left"] = (known[i]["n"] - nu * x) if i in known else None
            r["limiting"] = i == lim
        else:
            r["n_theor"] = nu * x
        if M:
            for k in ("n_start", "n_used", "n_left", "n_theor"):
                if r.get(k) is not None:
                    r[k.replace("n_", "m_")] = r[k] * M
        rows.append(r)
    out = {"extent": x, "limiting": lim, "rows": rows}
    if actual:
        for k, v in actual.items():
            i = int(k)
            r = rows[i]
            if r.get("n_theor"):
                n_act = amount(v, eq.terms[i].species)["n"]
                r["yield_pct"] = 100 * n_act / r["n_theor"]
    try:
        masses_in = sum(float(coefs[i]) * molar_mass(eq.terms[i].species)["M"] for i in reac
                        if eq.terms[i].species.kind == "chem")
        out["atom_economy"] = [{"i": r["i"], "pct": 100 * float(coefs[r["i"]]) * r["M"] / masses_in}
                               for r in rows if r["side"] > 0 and r.get("M")]
    except ChemError:
        pass
    return out


# ----------------------------------------------------------------------------- Elemente
def element_info(sym: str) -> dict:
    sym = sym.strip()
    if sym not in Z_OF:
        raise ChemError(f"Unbekanntes Element „{sym}“")
    Z = Z_OF[sym]
    d = {"Z": Z, "symbol": sym, "name_de": NAMES_DE[Z - 1], "name_en": NAMES_EN[Z - 1]}
    w = atomic_weights().get(sym) or {}
    d["atomic_weight"] = {k: v for k, v in w.items()}
    props = (_json("elements.json") or {}).get("elements", {}).get(sym)
    if props:
        d.update(props)
    data = _json("isotopes.json") or {}
    nuc = data.get("nuclides", {})
    rows = []
    for k in data.get("by_element", {}).get(sym, []):
        n = nuc.get(k) or {}
        ab = n.get("abundance_ciaaw") or {}
        r = {"key": k, "A": n.get("A"), "label": f"{str(n.get('A')).translate(_TO_SUP)}{sym}",
             "mass_u": n.get("mass_u"), "u_u": n.get("u_u"), "estimated": bool(n.get("estimated")),
             "stable": bool(n.get("stable")), "half_life": n.get("half_life"), "half_life_s": n.get("half_life_s"),
             "decay": n.get("decay") or [], "spin_parity": n.get("spin_parity")}
        if ab:
            r["abundance"] = ab.get("fraction")
            r["abundance_text"] = ab.get("text")
            r["abundance_interval"] = ab.get("interval")
        if n.get("particle_unstable"):
            r["half_life"] = "teilcheninstabil"
        rows.append(r)
    if rows:
        d["isotopes"] = rows
        d["isotope_sources"] = data.get("_sources") or {}
    return d


# ----------------------------------------------------------------------------- Rechner-Funktionen
def _str_arg(x, fn):
    if not isinstance(x, str):
        raise ChemError(f'{fn}("Formel") – die Formel in Anführungszeichen, z. B. {fn}("H2SO4")')
    return x


def calc_M(ctx, f):
    return molar_mass(_str_arg(f, "M"))["M"] / 1000.0          # SI: kg/mol


def calc_Ar(ctx, f):
    return relative_atomic_mass(_str_arg(f, "Ar"))


def calc_n(ctx, f, m, unit=None):
    from . import units as U
    kg = U.to_si(float(m), unit) if isinstance(unit, str) else float(m)
    return kg / calc_M(ctx, f)


def calc_mass(ctx, f, n):
    return float(n) * calc_M(ctx, f)


def register_calc_functions():
    """M("…"), Ar("…"), n("…", m[, "g"]), m_of("…", n) in labcalc.expr anmelden (Einheiten in SI)."""
    from . import expr as E
    from . import units as U
    E.register_string_function("M", calc_M, 1, 1, U.kind_dims("molar_mass"),
                               'M("H2SO4") – molare Masse (Standard-Atomgewichte IUPAC/CIAAW)')
    E.register_string_function("Ar", calc_Ar, 1, 1, U.D0, 'Ar("Fe") – relative Atommasse')
    E.register_string_function("n", calc_n, 2, 3, U.kind_dims("amount") if "amount" in U.KINDS else (0, 0, 0, 0, 0, 1, 0),
                               'n("CaCO3", m) – Stoffmenge aus Masse m; n("CaCO3", 5, "g")')
    E.register_string_function("m_of", calc_mass, 2, 2, U.kind_dims("mass") if "mass" in U.KINDS else (0, 1, 0, 0, 0, 0, 0),
                               'm_of("H2O", n) – Masse aus Stoffmenge n')
