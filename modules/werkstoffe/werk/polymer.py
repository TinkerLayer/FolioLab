"""Polymerketten als Atommodell: Wiederholeinheit + Konformation (Zickzack/Helix) → Kette, Kristallzelle mit Ketten,
amorphe Knäuel, teilkristallines Gefüge und vernetzte Netzwerke (werk/struktur.py setzt sie zusammen).

Nur Schweratome (C, N, O, F, Cl, Si); Wasserstoff wird nicht gezeigt. Bindungslängen sind Standardwerte (C–C 1,54 Å,
C–O 1,43 Å, C–N 1,47 Å, Si–O 1,64 Å, C=O 1,23 Å, aromatisch 1,39 Å), die Helix folgt der Angabe der Quelle der
Kristallzelle (Wiederholeinheiten je Windungen). Das Modell zeigt Aufbau, Konformation und Packung; es ist keine
verfeinerte Kristallstruktur (Atomlagen nicht aus der Quelle übertragen). Der Imidring des Polyimids ist vereinfacht.
"""
from __future__ import annotations

import math

import numpy as np

RINGS = ("Ph", "Glc", "Chx")

POLY = {
    "pe": {"name": "Polyethylen", "name_en": "Polyethylene", "unit": ["C", "C"], "helix": (2, 1), "formel": "–CH₂–CH₂–"},
    "pp": {"name": "Polypropylen (isotaktisch)", "name_en": "Polypropylene (isotactic)", "unit": ["C", "C(CH3)"],
           "helix": (3, 1), "takt": "iso", "formel": "–CH₂–CH(CH₃)–"},
    "ps": {"name": "Polystyrol (ataktisch)", "name_en": "Polystyrene (atactic)", "unit": ["C", "C(Ph)"], "helix": (2, 1),
           "takt": "a", "formel": "–CH₂–CH(C₆H₅)–"},
    "pvc": {"name": "Polyvinylchlorid", "name_en": "Poly(vinyl chloride)", "unit": ["C", "C(Cl)"], "helix": (2, 1),
            "takt": "syn", "formel": "–CH₂–CHCl–"},
    "ptfe": {"name": "Polytetrafluorethylen", "name_en": "Polytetrafluoroethylene", "unit": ["C(F)(F)"],
             "helix": (13, 6), "formel": "–CF₂–CF₂–"},
    "pmma": {"name": "Polymethylmethacrylat (ataktisch)", "name_en": "Poly(methyl methacrylate) (atactic)",
             "unit": ["C", "C(CH3)(COOCH3)"], "helix": (2, 1), "takt": "a", "formel": "–CH₂–C(CH₃)(COOCH₃)–"},
    "pom": {"name": "Polyoxymethylen", "name_en": "Polyoxymethylene", "unit": ["C", "O"], "helix": (9, 5),
            "formel": "–CH₂–O–"},
    "pa6": {"name": "Polyamid 6", "name_en": "Polyamide 6", "unit": ["N", "C(=O)", "C", "C", "C", "C", "C"],
            "helix": (2, 1), "formel": "–NH–CO–(CH₂)₅–"},
    "pa66": {"name": "Polyamid 66", "name_en": "Polyamide 66",
             "unit": ["N", "C", "C", "C", "C", "C", "C", "N", "C(=O)", "C", "C", "C", "C", "C(=O)"], "helix": (2, 1),
             "formel": "–NH–(CH₂)₆–NH–CO–(CH₂)₄–CO–"},
    "pa12": {"name": "Polyamid 12", "name_en": "Polyamide 12", "unit": ["N", "C(=O)"] + ["C"] * 11, "helix": (2, 1),
             "formel": "–NH–CO–(CH₂)₁₁–"},
    "pet": {"name": "Polyethylenterephthalat", "name_en": "Poly(ethylene terephthalate)",
            "unit": ["O", "C(=O)", "Ph", "C(=O)", "O", "C", "C"], "helix": (2, 1), "formel": "–O–CO–C₆H₄–CO–O–CH₂–CH₂–"},
    "pbt": {"name": "Polybutylenterephthalat", "name_en": "Poly(butylene terephthalate)",
            "unit": ["O", "C(=O)", "Ph", "C(=O)", "O", "C", "C", "C", "C"], "helix": (2, 1),
            "formel": "–O–CO–C₆H₄–CO–O–(CH₂)₄–"},
    "petg": {"name": "PET, glykolmodifiziert", "name_en": "PET, glycol-modified",
             "unit": ["O", "C(=O)", "Ph", "C(=O)", "O", "C", "Chx", "C"], "helix": (2, 1),
             "formel": "–O–CO–C₆H₄–CO–O–CH₂–C₆H₁₀–CH₂– (Anteil CHDM)"},
    "pc": {"name": "Polycarbonat (Bisphenol A)", "name_en": "Polycarbonate (bisphenol A)",
           "unit": ["O", "C(=O)", "O", "Ph", "C(CH3)(CH3)", "Ph"], "helix": (2, 1),
           "formel": "–O–CO–O–C₆H₄–C(CH₃)₂–C₆H₄–"},
    "peek": {"name": "Polyetheretherketon", "name_en": "Poly(ether ether ketone)",
             "unit": ["Ph", "O", "Ph", "O", "Ph", "C(=O)"], "helix": (2, 1), "formel": "–C₆H₄–O–C₆H₄–O–C₆H₄–CO–"},
    "pla": {"name": "Polylactid", "name_en": "Poly(lactic acid)", "unit": ["O", "C(CH3)", "C(=O)"], "helix": (10, 3),
            "formel": "–O–CH(CH₃)–CO–"},
    "pi": {"name": "Polyimid (PMDA-ODA)", "name_en": "Polyimide (PMDA-ODA)",
           "unit": ["N", "C(=O)", "Ph", "C(=O)", "N", "Ph", "O", "Ph"], "helix": (2, 1),
           "formel": "Pyromellitdiimid–C₆H₄–O–C₆H₄– (Imidring vereinfacht)"},
    "ppta": {"name": "Poly(p-phenylenterephthalamid)", "name_en": "Poly(p-phenylene terephthalamide)",
             "unit": ["Ph", "C(=O)", "N", "Ph", "N", "C(=O)"], "helix": (2, 1), "formel": "–C₆H₄–CO–NH–C₆H₄–NH–CO–"},
    "abs": {"name": "ABS (SAN-Matrix mit Polybutadien)", "name_en": "ABS (SAN matrix with polybutadiene)",
            "unit": ["C", "C(Ph)", "C", "C(CN)", "C", "C", "C", "C"], "helix": (2, 1), "takt": "a",
            "formel": "–CH₂–CH(C₆H₅)–, –CH₂–CH(CN)–, –CH₂–CH=CH–CH₂–"},
    "nr": {"name": "cis-1,4-Polyisopren", "name_en": "cis-1,4-polyisoprene", "unit": ["C", "C(CH3)", "C", "C"],
           "helix": (2, 1), "formel": "–CH₂–C(CH₃)=CH–CH₂–", "vernetzer": "S"},
    "epdm": {"name": "Ethylen-Propylen-Dien", "name_en": "Ethylene-propylene-diene", "unit": ["C", "C", "C", "C(CH3)"],
             "helix": (2, 1), "takt": "a", "formel": "–CH₂–CH₂–, –CH₂–CH(CH₃)– (+ Dien)", "vernetzer": "C"},
    "nbr": {"name": "Acrylnitril-Butadien", "name_en": "Acrylonitrile-butadiene", "unit": ["C", "C", "C", "C", "C", "C(CN)"],
            "helix": (2, 1), "takt": "a", "formel": "–CH₂–CH=CH–CH₂–, –CH₂–CH(CN)–", "vernetzer": "S"},
    "vmq": {"name": "Polydimethylsiloxan (Silikon)", "name_en": "Polydimethylsiloxane (silicone)",
            "unit": ["Si(CH3)(CH3)", "O"], "helix": (2, 1), "formel": "–Si(CH₃)₂–O–", "vernetzer": "C"},
    "fkm": {"name": "Fluorkautschuk (VDF-HFP)", "name_en": "Fluoroelastomer (VDF-HFP)",
            "unit": ["C(F)(F)", "C", "C(F)(F)", "C(F)(CF3)"], "helix": (2, 1), "takt": "a",
            "formel": "–CF₂–CH₂–, –CF₂–CF(CF₃)–", "vernetzer": "C"},
    "tpu": {"name": "Thermoplastisches Polyurethan", "name_en": "Thermoplastic polyurethane",
            "unit": ["O", "C(=O)", "N", "Ph", "C", "Ph", "N", "C(=O)", "O", "C", "C", "C", "C"], "helix": (2, 1),
            "formel": "Hartsegment –O–CO–NH–C₆H₄–CH₂–C₆H₄–NH–CO–, Weichsegment –O–(CH₂)₄–"},
    "ep": {"name": "Epoxidharz (DGEBA, aminisch vernetzt)", "name_en": "Epoxy (DGEBA, amine-cured)",
           "unit": ["O", "Ph", "C(CH3)(CH3)", "Ph", "O", "C", "C", "C", "N"], "helix": (2, 1),
           "formel": "Bisphenol-A-Diglycidylether, mit Amin vernetzt", "vernetzer": "N"},
    "pf": {"name": "Phenolharz", "name_en": "Phenolic resin", "unit": ["Ph", "C"], "helix": (2, 1),
           "formel": "Phenolringe über –CH₂– vernetzt", "vernetzer": "C"},
    "cellulose": {"name": "Cellulose", "name_en": "Cellulose", "unit": ["Glc", "O"], "helix": (2, 1),
                  "formel": "(C₆H₁₀O₅)ₙ, β-1,4-glykosidisch"},
}

def _parse(tok: str) -> tuple[str, list[str]]:
    if "(" not in tok:
        return tok, []
    return tok[:tok.index("(")], [s.rstrip(")") for s in tok[tok.index("(") + 1:].split("(")]


def _perp(v: np.ndarray) -> np.ndarray:
    a = np.array([1.0, 0, 0]) if abs(v[0]) < 0.9 else np.array([0, 1.0, 0])
    p = np.cross(v, a)
    return p / np.linalg.norm(p)


def _ring(center: np.ndarray, axis: np.ndarray, normal: np.ndarray, r: float = 1.39, n: int = 6) -> list[np.ndarray]:
    """n Ringatome um center; Atom 0 liegt in Richtung axis, Atom n/2 gegenüber; Ebene ⟂ normal."""
    u = axis / np.linalg.norm(axis)
    w = np.cross(normal, u)
    if np.linalg.norm(w) < 1e-6:
        w = _perp(u)
    w /= np.linalg.norm(w)
    return [center + r * (math.cos(2 * math.pi * k / n) * u + math.sin(2 * math.pi * k / n) * w) for k in range(n)]


class _Mol:
    def __init__(self):
        self.atoms: list = []     # (el, xyz, rolle)
        self.bonds: list = []

    def add(self, el, p, role) -> int:
        self.atoms.append((el, np.asarray(p, float), role))
        return len(self.atoms) - 1

    def bond(self, i, j):
        if i is not None and j is not None:
            self.bonds.append((i, j))


BOND = {"C": 1.54, "O": 1.43, "N": 1.45, "Si": 1.64}
# Faserperiode (Å) je Helix (Wiederholgruppen, Windungen); daraus Steigung je Atom und Helixradius.
# PE 2,55 (Bunn 1939), PP 6,50 (Natta 1960), PTFE 16,8 / 19,5 (Bunn 1954, Clark 1962), POM 17,39 (Tadokoro 1960),
# PLA 28,8 (Hoogsteen 1990).
REPEAT = {(13, 6): 16.8, (15, 7): 19.5, (9, 5): 17.39, (3, 1): 6.50, (10, 3): 28.8}
ZIG = math.radians(34.0)          # Winkel der Zickzackbindung zur Kettenachse (Bindungswinkel 112°)
TET = (math.radians(54.75))       # halber Tetraederwinkel zwischen zwei Substituenten


def _bond_len(a: str, b: str) -> float:
    if "Si" in (a, b):
        return 1.64 if "O" in (a, b) else 1.87
    if "O" in (a, b):
        return 1.43
    if "N" in (a, b):
        return 1.45
    return 1.54


def _unit(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else v


def _subst_dirs(p, a, c, n_sub: int, sp2: bool = False, sign: float = 1.0) -> list[np.ndarray]:
    """Richtungen der Substituenten am Rückgratatom p mit Nachbarn a, c (tetraedrisch bzw. trigonal)."""
    u = _unit(-(_unit(a - p) + _unit(c - p)))
    if np.linalg.norm(u) < 1e-6:
        u = _perp(_unit(c - p))
    n = _unit(np.cross(a - p, c - p))
    if np.linalg.norm(n) < 1e-6:
        n = _unit(np.cross(u, c - p))
    if sp2:
        return [u]
    d1 = math.cos(TET) * u + math.sin(TET) * n * sign
    d2 = math.cos(TET) * u - math.sin(TET) * n * sign
    return [d1, d2][:max(n_sub, 1)] if n_sub <= 2 else [d1, d2]


def _side(m: "_Mol", at: int, pos: np.ndarray, kind: str, dirv: np.ndarray, parent: str = "C"):
    dirv = _unit(dirv)
    z = np.array([0, 0, 1.0])
    w = _unit(np.cross(dirv, z))
    if np.linalg.norm(w) < 1e-6:
        w = _perp(dirv)
    w2 = np.cross(dirv, w)
    if kind == "CH3":
        m.bond(at, m.add("C", pos + (1.87 if parent == "Si" else 1.53) * dirv, "seite"))
    elif kind == "=O":
        m.bond(at, m.add("O", pos + 1.23 * dirv, "seite"))
    elif kind in ("Cl", "F"):
        m.bond(at, m.add(kind, pos + (1.78 if kind == "Cl" else 1.35) * dirv, "seite"))
    elif kind == "CF3":
        c = m.add("C", pos + 1.54 * dirv, "seite")
        m.bond(at, c)
        for t in range(3):
            ang = 2 * math.pi * t / 3
            m.bond(c, m.add("F", m.atoms[c][1] + 1.35 * (0.33 * dirv + 0.94 * (math.cos(ang) * w + math.sin(ang) * w2)),
                            "seite"))
    elif kind == "CN":
        c = m.add("C", pos + 1.47 * dirv, "seite")
        m.bond(at, c)
        m.bond(c, m.add("N", m.atoms[c][1] + 1.16 * dirv, "seite"))
    elif kind == "COOCH3":                       # Esterebene quer zur Kettenachse
        c = m.add("C", pos + 1.52 * dirv, "seite")
        m.bond(at, c)
        cp = m.atoms[c][1]
        m.bond(c, m.add("O", cp + 1.23 * (0.5 * dirv + 0.866 * w), "seite"))
        o = m.add("O", cp + 1.34 * (0.5 * dirv - 0.866 * w), "seite")
        m.bond(c, o)
        m.bond(o, m.add("C", m.atoms[o][1] + 1.43 * dirv, "seite"))
    elif kind == "Ph":                           # Ringebene ⟂ Kettenachse
        ctr = pos + (1.50 + 1.39) * dirv
        idx = [m.add("C", q, "seite") for q in _ring(ctr, -dirv, w2)]
        m.bond(at, idx[0])
        for k in range(6):
            m.bond(idx[k], idx[(k + 1) % 6])
    else:
        m.bond(at, m.add("C", pos + 1.5 * dirv, "seite"))


def chain(pid: str, n_units: int, helix: tuple[int, int] | None = None, rng=None, tact: str | None = None,
          period: float | None = None) -> dict:
    """Kette entlang +z ab z ≈ 0 (Zickzack bzw. Helix). helix = (Wiederholeinheiten, Windungen); period = Faserperiode
    der Helix in Å (sonst Tabellenwert). Rückgabe: atoms [(el, xyz, rolle)], bonds, axis_len, repeat (Länge je
    Wiederholeinheit). Rollen: "rueckgrat", "ring", "seite"."""
    p = POLY[pid]
    rng = rng or np.random.default_rng(1)
    hx = tuple(helix or p["helix"])
    tact = tact or p.get("takt", "iso")
    toks = [_parse(t) for t in p["unit"]]
    per_unit = len(toks)
    zig = hx == (2, 1) or any(b in RINGS for b, _ in toks)
    if not zig:
        n_at = hx[0] * per_unit
        theta = 2 * math.pi * hx[1] / n_at
        per = period or REPEAT.get(hx)
        bl = float(np.mean([_bond_len(toks[i][0], toks[(i + 1) % per_unit][0]) for i in range(per_unit)]))
        rise = per / n_at if per else 1.15
        chord = math.sqrt(max(bl ** 2 - rise ** 2, 0.2))
        r_h = chord / (2 * math.sin(theta / 2))

    # 1. Rückgrat (eine Einheit mehr als Nachbar für die letzten Seitengruppen)
    nodes = []                    # (unit k, token idx, base, sides, entry pos, exit pos, ring pts or None, normal)
    pos, side, phi, prev_el = None, 1.0, 0.0, None
    for k in range(-1, n_units + 1):
        for ti, (base, sides) in enumerate(toks):
            if base in RINGS:
                bl = 1.45 if prev_el in ("O", "N") else 1.50
                if pos is None:
                    ipso = np.zeros(3)
                else:
                    ipso = pos + bl * np.array([side * math.sin(ZIG), 0.0, math.cos(ZIG)])
                    side = -side
                r = 1.42 if base == "Glc" else (1.52 if base == "Chx" else 1.39)
                ctr = ipso + np.array([0, 0, r])
                ang = math.pi / 2 + (0.5 if len(nodes) % 2 else -0.5)
                normal = np.array([math.cos(ang), math.sin(ang), 0.0])
                pts = _ring(ctr, np.array([0, 0, -1.0]), normal, r)
                nodes.append((k, ti, base, sides, pts[0], pts[3], pts, normal))
                pos, prev_el = pts[3], "C"
                pos = pos.copy()
                continue
            if pos is None:
                q = np.array([0.0, 0.0, 0.0]) if zig else np.array([r_h, 0.0, 0.0])
            elif zig:
                bl = _bond_len(prev_el, base) if prev_el in ("O", "N", "Si") or base in ("O", "N", "Si") else 1.54
                if nodes and nodes[-1][6] is not None:
                    bl = 1.45 if base in ("O", "N") else 1.50
                q = pos + bl * np.array([side * math.sin(ZIG), 0.0, math.cos(ZIG)])
                side = -side
            else:
                phi += theta
                q = np.array([r_h * math.cos(phi), r_h * math.sin(phi), pos[2] + rise])
            nodes.append((k, ti, base, sides, q, q, None, None))
            pos, prev_el = q, base

    # 2. Atome und Bindungen, Seitengruppen aus den Nachbarlagen
    m = _Mol()
    last = None
    sgn = 1.0
    for ni, (k, ti, base, sides, ent, ext, pts, normal) in enumerate(nodes):
        if k < 0:
            continue
        if k >= n_units:
            break
        if pts is not None:
            els = ["C"] * 6
            if base == "Glc":
                els[5] = "O"                 # Ringsauerstoff O5 neben C1 (Atom 0)
            role = "rueckgrat" if base == "Glc" else "ring"
            idx = [m.add(e, q, role) for e, q in zip(els, pts)]
            for j in range(6):
                m.bond(idx[j], idx[(j + 1) % 6])
            m.bond(last, idx[0])
            if base == "Glc":                # OH an C2, C3, CH2OH an C5 (in der Ringebene nach außen)
                ctr = (pts[0] + pts[3]) / 2
                for a, el, ln in ((1, "O", 1.43), (2, "O", 1.43)):
                    m.bond(idx[a], m.add(el, pts[a] + ln * _unit(pts[a] - ctr), "seite"))
                c6 = m.add("C", pts[4] + 1.52 * _unit(pts[4] - ctr), "seite")
                m.bond(idx[4], c6)
                m.bond(c6, m.add("O", m.atoms[c6][1] + 1.43 * _unit(0.5 * normal + 0.5 * _unit(pts[4] - ctr)),
                                 "seite"))
            last = idx[3]
            continue
        i = m.add(base, ent, "rueckgrat")
        m.bond(last, i)
        last = i
        if not sides:
            continue
        a = nodes[ni - 1][5] if ni > 0 else ent - (nodes[ni + 1][4] - ent)
        c = nodes[ni + 1][4]
        if tact == "a":
            sgn = 1.0 if rng.random() < 0.5 else -1.0
        elif tact == "syn":
            sgn = -sgn
        sp2 = sides == ["=O"]
        dirs = _subst_dirs(ent, a, c, len(sides), sp2, sgn)
        for s, dv in zip(sides, dirs):
            _side(m, i, ent, s, dv, base)
    z0 = next(nd[4][2] for nd in nodes if nd[0] == 0)
    zn = next(nd[4][2] for nd in nodes if nd[0] == n_units)
    shift = np.array([0.0, 0.0, z0])
    atoms = [(el, q - shift, role) for el, q, role in m.atoms]
    return {"atoms": atoms, "bonds": m.bonds, "axis_len": float(zn - z0), "repeat": float(zn - z0) / max(n_units, 1)}


def units_for(pid: str, length: float, helix=None) -> int:
    one = chain(pid, 1, helix)
    hx = tuple(helix or POLY[pid]["helix"])
    n = max(1, round(length / max(one["repeat"], 0.5)))
    return max(n, hx[0]) if hx != (2, 1) and length < 40 else n


def random_coil(n_atoms: int, box: np.ndarray, rng, b: float = 1.54, start=None, angle: float = 112.0,
                lo: np.ndarray | None = None) -> np.ndarray:
    """Zufallsknäuel mit fester Bindungslänge und Bindungswinkel, zufällige Torsion; an den Wänden des Kastens
    [lo, lo + box] gespiegelt."""
    lo = np.zeros(3) if lo is None else np.asarray(lo, float)
    hi = lo + box
    pts = np.zeros((n_atoms, 3))
    pts[0] = start if start is not None else lo + rng.uniform(0.1, 0.9, 3) * box
    d = rng.normal(size=3)
    d /= np.linalg.norm(d)
    ca, sa = math.cos(math.radians(180 - angle)), math.sin(math.radians(180 - angle))
    for i in range(1, n_atoms):
        w = _perp(d)
        tor = rng.uniform(0, 2 * math.pi)
        w = math.cos(tor) * w + math.sin(tor) * np.cross(d, w)
        d = ca * d + sa * w
        d /= np.linalg.norm(d)
        q = pts[i - 1] + b * d
        for k in range(3):
            if q[k] < lo[k]:
                q[k] = 2 * lo[k] - q[k]
                d[k] = -d[k]
            elif q[k] > hi[k]:
                q[k] = 2 * hi[k] - q[k]
                d[k] = -d[k]
        pts[i] = q
    return pts
