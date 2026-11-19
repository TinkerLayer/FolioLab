"""Kristallographie: Elementarzelle, Netzebenenabstände, Strukturfaktoren, berechnete Pulverdiagramme, CIF.

Eine Phase ist ein dict:
    {"id", "name", "formula", "system", "cell": {"a", "b", "c", "alpha", "beta", "gamma"} (Å, Grad),
     "centring": "P" | "I" | "F" | "C" | "A" | "B" | "R" (R = rhomboedrisch in hexagonaler Aufstellung, obvers),
     "ops": ["x,y,z", …] (optional, Symmetrieoperationen der Raumgruppe ohne Zentrierung),
     "atoms": [{"el", "x", "y", "z", "occ", "B"}] (asymmetrische Einheit oder alle Atome der Zelle),
     "q": Quellenschlüssel, "note": Hinweis}

Intensität einer Pulverlinie (Bragg–Brentano, ohne Absorption, Textur und anomale Dispersion):
    I = Σ |F_hkl|² · LP(θ),   F = Σ_j f_j(s) · occ_j · exp(−B_j s²) · exp(2πi (h x_j + k y_j + l z_j)),
    LP = (1 + cos² 2θ · cos² 2θ_M) / (sin² θ · cos θ),  s = sin θ / λ.
Die Summe läuft über alle (hkl) mit gleichem d (Flächenhäufigkeit m ergibt sich daraus). Quelle: Cullity & Stock.
"""
from __future__ import annotations

import json
import math
import re
from fractions import Fraction
from functools import lru_cache
from pathlib import Path

import numpy as np

from . import formfactors as FF

DATA = Path(__file__).resolve().parent / "data"
REFS = ["cullity", "itc_c"]
B_DEFAULT = 0.5           # Å², isotroper Auslenkungsparameter, wenn die Phase keinen nennt (DECISIONS Round WS)

# Röhrenwellenlängen in Å (Kα1, Kα2, Verhältnis I(Kα2)/I(Kα1)); übliche Standardwerte der Gerätesoftware
TUBES = {
    "Cu": (1.540598, 1.544426, 0.5), "Co": (1.788965, 1.792850, 0.5), "Mo": (0.709300, 0.713590, 0.5),
    "Cr": (2.289700, 2.293606, 0.5), "Fe": (1.936042, 1.939980, 0.5), "Ag": (0.559410, 0.563810, 0.5),
}
TUBE_REF = "bearden1967"

CENTRING = {
    "P": [(0, 0, 0)],
    "I": [(0, 0, 0), (0.5, 0.5, 0.5)],
    "F": [(0, 0, 0), (0, 0.5, 0.5), (0.5, 0, 0.5), (0.5, 0.5, 0)],
    "C": [(0, 0, 0), (0.5, 0.5, 0)],
    "A": [(0, 0, 0), (0, 0.5, 0.5)],
    "B": [(0, 0, 0), (0.5, 0, 0.5)],
    "R": [(0, 0, 0), (2 / 3, 1 / 3, 1 / 3), (1 / 3, 2 / 3, 2 / 3)],
}
SYSTEMS = ("cubic", "tetragonal", "hexagonal", "trigonal", "orthorhombic", "monoclinic", "triclinic")


class CrystError(ValueError):
    pass


# ----------------------------------------------------------------------------- Zelle
class Cell:
    def __init__(self, a, b=None, c=None, alpha=90.0, beta=90.0, gamma=90.0):
        self.a = float(a)
        self.b = float(b if b not in (None, "") else a)
        self.c = float(c if c not in (None, "") else a)
        self.alpha, self.beta, self.gamma = float(alpha), float(beta), float(gamma)
        if min(self.a, self.b, self.c) <= 0:
            raise CrystError("Gitterparameter müssen positiv sein")
        al, be, ga = (math.radians(x) for x in (self.alpha, self.beta, self.gamma))
        self.G = np.array([
            [self.a ** 2, self.a * self.b * math.cos(ga), self.a * self.c * math.cos(be)],
            [self.a * self.b * math.cos(ga), self.b ** 2, self.b * self.c * math.cos(al)],
            [self.a * self.c * math.cos(be), self.b * self.c * math.cos(al), self.c ** 2]])
        det = float(np.linalg.det(self.G))
        if det <= 0:
            raise CrystError("Winkel ergeben keine gültige Zelle")
        self.V = math.sqrt(det)
        self.Gs = np.linalg.inv(self.G)

    @classmethod
    def of(cls, d: dict, system: str | None = None) -> "Cell":
        d = dict(d or {})
        s = (system or "").lower()
        a = d.get("a")
        if s == "cubic":
            return cls(a, a, a)
        if s == "tetragonal":
            return cls(a, a, d.get("c"))
        if s in ("hexagonal", "trigonal"):
            return cls(a, a, d.get("c"), 90, 90, 120)
        return cls(a, d.get("b"), d.get("c"), d.get("alpha", 90), d.get("beta", 90), d.get("gamma", 90))

    def as_dict(self) -> dict:
        return {"a": self.a, "b": self.b, "c": self.c, "alpha": self.alpha, "beta": self.beta, "gamma": self.gamma,
                "V": self.V}

    def d(self, hkl) -> np.ndarray:
        """Netzebenenabstand(e) [Å] für (h,k,l) oder ein N×3-Feld."""
        h = np.atleast_2d(np.asarray(hkl, dtype=float))
        q = np.einsum("ij,jk,ik->i", h, self.Gs, h)
        out = 1.0 / np.sqrt(q)
        return out if np.ndim(hkl) > 1 else out[0]

    def basis(self) -> np.ndarray:
        """Kartesische Zellvektoren als Zeilen (a entlang x, b in der xy-Ebene)."""
        al, be, ga = (math.radians(x) for x in (self.alpha, self.beta, self.gamma))
        ax = np.array([self.a, 0, 0])
        bx = np.array([self.b * math.cos(ga), self.b * math.sin(ga), 0])
        cx = self.c * math.cos(be)
        cy = self.c * (math.cos(al) - math.cos(be) * math.cos(ga)) / math.sin(ga)
        cz = math.sqrt(max(self.c ** 2 - cx ** 2 - cy ** 2, 0))
        return np.array([ax, bx, [cx, cy, cz]])

    def angle_hkl(self, h1, h2) -> float:
        """Winkel zwischen den Normalen zweier Ebenen [Grad]."""
        h1, h2 = np.asarray(h1, float), np.asarray(h2, float)
        c = h1 @ self.Gs @ h2 / math.sqrt((h1 @ self.Gs @ h1) * (h2 @ self.Gs @ h2))
        return math.degrees(math.acos(max(-1, min(1, c))))

    def angle_uvw(self, u1, u2) -> float:
        u1, u2 = np.asarray(u1, float), np.asarray(u2, float)
        c = u1 @ self.G @ u2 / math.sqrt((u1 @ self.G @ u1) * (u2 @ self.G @ u2))
        return math.degrees(math.acos(max(-1, min(1, c))))


def bragg_2theta(d, lam) -> np.ndarray:
    """2θ [Grad] aus d [Å] und λ [Å]; NaN, wo λ/2d > 1."""
    x = np.asarray(lam, float) / (2 * np.asarray(d, float))
    with np.errstate(invalid="ignore"):
        return np.degrees(2 * np.arcsin(np.where(x <= 1, x, np.nan)))


def d_from_2theta(tth, lam) -> np.ndarray:
    return np.asarray(lam, float) / (2 * np.sin(np.radians(np.asarray(tth, float) / 2)))


# ----------------------------------------------------------------------------- Symmetrie
_TERM = re.compile(r"([+-]?)\s*(\d+(?:\.\d+)?(?:/\d+)?)?\s*\*?\s*([xyz])?")


def parse_op(s: str) -> tuple[np.ndarray, np.ndarray]:
    """'-x+1/2, y, -z' -> (R, t); x' = R·x + t."""
    parts = [p.strip().lower().replace(" ", "") for p in str(s).strip().strip("'\"").split(",")]
    if len(parts) != 3:
        raise CrystError(f"Symmetrieoperation „{s}“ nicht lesbar")
    R = np.zeros((3, 3))
    t = np.zeros(3)
    for i, p in enumerate(parts):
        pos = 0
        if not p:
            raise CrystError(f"Symmetrieoperation „{s}“ nicht lesbar")
        while pos < len(p):
            m = _TERM.match(p, pos)
            if not m or m.end() == pos:
                raise CrystError(f"Symmetrieoperation „{s}“ nicht lesbar")
            sign = -1.0 if m.group(1) == "-" else 1.0
            num, var = m.group(2), m.group(3)
            val = float(Fraction(num)) if num else 1.0
            if var:
                R[i, "xyz".index(var)] += sign * val
            elif num:
                t[i] += sign * val
            pos = m.end()
    return R, t


def expand(phase: dict) -> list[dict]:
    """Alle Atome der konventionellen Zelle: Operationen, dann Zentrierung, Lagen mod 1, Doppelte zusammengelegt."""
    ops = [parse_op(o) for o in (phase.get("ops") or ["x,y,z"])]
    cen = CENTRING.get((phase.get("centring") or "P").upper())
    if cen is None:
        raise CrystError(f"Zentrierung „{phase.get('centring')}“ unbekannt")
    out: list[dict] = []
    for at in phase.get("atoms") or []:
        el = FF.element_of(at.get("el"))
        p0 = np.array([float(at["x"]), float(at["y"]), float(at["z"])])
        mine: list[np.ndarray] = []
        for R, t in ops:
            for c in cen:
                p = (R @ p0 + t + np.array(c)) % 1.0
                p[np.isclose(p, 1.0, atol=1e-6)] = 0.0
                if not any(np.all(np.abs(((p - q) + 0.5) % 1.0 - 0.5) < 2e-3) for q in mine):
                    mine.append(p)
        occ = float(at.get("occ", 1) if at.get("occ") not in (None, "") else 1)
        B = at.get("B")
        for p in mine:
            out.append({"el": el, "x": float(p[0]), "y": float(p[1]), "z": float(p[2]), "occ": occ,
                        "B": None if B in (None, "") else float(B), "label": at.get("label") or el})
    if not out:
        raise CrystError("Die Phase enthält keine Atome")
    return out


# ----------------------------------------------------------------------------- Pulverdiagramm
def lp_factor(tth, mono_2theta: float = 0.0) -> np.ndarray:
    th = np.radians(np.asarray(tth, float) / 2)
    c2m = math.cos(math.radians(mono_2theta)) ** 2
    return (1 + np.cos(2 * th) ** 2 * c2m) / (np.sin(th) ** 2 * np.cos(th)) / (1 + c2m)


def _family(hkl) -> tuple:
    return tuple(sorted((abs(int(x)) for x in hkl), reverse=True))


def _rep(group: list, system: str) -> str:
    """Kurzbezeichnung der Linie: eine Darstellung je Form, kubisch mehrere Formen mit '/'."""
    def key(h):
        return (sum(x < 0 for x in h), [-abs(x) for x in h], [-x for x in h])
    if system == "cubic":
        fams = sorted({_family(h) for h in group}, reverse=True)
        return "/".join("".join(str(x) for x in f) for f in fams)
    best = sorted(group, key=key)[0]
    return " ".join(str(x) for x in best) if any(abs(x) > 9 for x in best) else "".join(str(x) for x in best)


def reflections(phase: dict, lam: float = TUBES["Cu"][0], tth_min: float = 5.0, tth_max: float = 140.0,
                mono_2theta: float = 0.0, B: float | None = None, atoms: list | None = None,
                cell: Cell | None = None) -> list[dict]:
    """Pulverlinien zwischen tth_min und tth_max: [{tth, d, hkl, m, F2, I, Irel}], Irel max = 100."""
    cell = cell or Cell.of(phase["cell"], phase.get("system"))
    atoms = atoms if atoms is not None else expand(phase)
    lam = float(lam)
    d_min = lam / (2 * math.sin(math.radians(min(tth_max, 179.0) / 2)))
    lim = [int(math.ceil(L / d_min)) + 1 for L in (cell.a, cell.b, cell.c)]
    rng = [np.arange(-n, n + 1) for n in lim]
    H = np.array(np.meshgrid(*rng, indexing="ij")).reshape(3, -1).T
    H = H[np.any(H != 0, axis=1)]
    d = cell.d(H)
    keep = d >= d_min * (1 - 1e-9)
    H, d = H[keep], d[keep]
    tth = bragg_2theta(d, lam)
    keep = np.isfinite(tth) & (tth >= tth_min) & (tth <= tth_max)
    H, d, tth = H[keep], d[keep], tth[keep]
    if not len(H):
        return []
    s = 1 / (2 * d)
    X = np.array([[a["x"], a["y"], a["z"]] for a in atoms])
    phase_f = np.exp(2j * np.pi * (H @ X.T))                       # N × n_atoms
    els = sorted({a["el"] for a in atoms})
    fcache = {e: FF.f0(e, s) for e in els}
    bdef = B_DEFAULT if B is None else float(B)
    F = np.zeros(len(H), dtype=complex)
    for j, a in enumerate(atoms):
        b = bdef if a.get("B") is None else a["B"]
        F += fcache[a["el"]] * a["occ"] * np.exp(-b * s ** 2) * phase_f[:, j]
    F2 = np.abs(F) ** 2
    order = np.argsort(-d)
    groups: list[list[int]] = []
    for i in order:
        if groups and abs(d[groups[-1][0]] - d[i]) < 1e-5 * d[i]:
            groups[-1].append(int(i))
        else:
            groups.append([int(i)])
    lp = lp_factor(tth, mono_2theta)
    lines = []
    for g in groups:
        f2sum = float(F2[g].sum())
        if f2sum < 1e-6 * max(1.0, float(F2.max())):
            continue
        hk = [tuple(int(x) for x in H[i]) for i in g if F2[i] > 1e-6 * max(1.0, float(F2.max()))]
        i0 = g[0]
        lines.append({"tth": float(tth[i0]), "d": float(d[i0]), "hkl": _rep(hk, phase.get("system", "")),
                      "hkl_list": hk, "m": len(hk), "F2": f2sum / len(hk), "I": f2sum * float(lp[i0])})
    if lines:
        top = max(x["I"] for x in lines)
        for x in lines:
            x["Irel"] = 100 * x["I"] / top
    return lines


def profile(lines: list[dict], tth: np.ndarray, fwhm: float = 0.1, eta: float = 0.5, k_alpha2: tuple | None = None) -> np.ndarray:
    """Berechnetes Diagramm: pseudo-Voigt-Linien (Breite fwhm in Grad 2θ) auf dem Raster tth, optional mit Kα2."""
    tth = np.asarray(tth, float)
    y = np.zeros_like(tth)

    def pv(x0, h):
        dx = (tth - x0) / (fwhm / 2)
        g = np.exp(-math.log(2) * dx ** 2)
        lo = 1 / (1 + dx ** 2)
        return h * (eta * lo + (1 - eta) * g)
    for L in lines:
        y += pv(L["tth"], L["Irel"])
        if k_alpha2:
            l1, l2, ratio = k_alpha2
            x = l2 / l1 * math.sin(math.radians(L["tth"] / 2))
            if x < 1:
                y += pv(2 * math.degrees(math.asin(x)), L["Irel"] * ratio)
    return y


# ----------------------------------------------------------------------------- Gittertypen (kubisch)
CUBIC_TYPES = {"sc": "kubisch primitiv", "bcc": "kubisch raumzentriert", "fcc": "kubisch flächenzentriert",
               "diamond": "Diamantstruktur"}
CUBIC_TYPES_EN = {"sc": "simple cubic", "bcc": "body-centred cubic", "fcc": "face-centred cubic",
                  "diamond": "diamond structure"}


def cubic_allowed(h: int, k: int, l: int, kind: str) -> bool:
    """Auslöschungsregeln: bcc h+k+l gerade; fcc alle gerade oder alle ungerade; Diamant zusätzlich h+k+l ≠ 4n+2."""
    if kind == "sc":
        return True
    if kind == "bcc":
        return (h + k + l) % 2 == 0
    par = {h % 2, k % 2, l % 2}
    if kind == "fcc":
        return len(par) == 1
    if kind == "diamond":
        return len(par) == 1 and not (par == {0} and (h + k + l) % 4 == 2)
    raise CrystError(f"Gittertyp {kind} unbekannt")


def cubic_sequence(kind: str, n: int = 20) -> list[tuple[int, tuple]]:
    """Erlaubte N = h²+k²+l² (aufsteigend) mit einer Darstellung (hkl)."""
    out, seen = [], set()
    for N in range(1, 400):
        for h in range(int(math.isqrt(N)), -1, -1):
            for k in range(h, -1, -1):
                r = N - h * h - k * k
                if r < 0:
                    continue
                l_ = math.isqrt(r)
                if l_ * l_ == r and l_ <= k and cubic_allowed(h, k, l_, kind) and N not in seen:
                    seen.add(N)
                    out.append((N, (h, k, l_)))
        if len(out) >= n:
            break
    return out


# ----------------------------------------------------------------------------- eingebaute Phasen
@lru_cache(maxsize=None)
def _builtin() -> dict:
    data = json.loads((DATA / "phases.json").read_text(encoding="utf-8"))
    return {p["id"]: p for p in data["phasen"]}


def builtin_phases() -> list[dict]:
    return list(_builtin().values())


def phase(pid: str, own: list[dict] | None = None) -> dict:
    for p in own or []:
        if p.get("id") == pid:
            return p
    p = _builtin().get(pid)
    if p is None:
        raise CrystError(f"Phase „{pid}“ unbekannt")
    return p


def density(phase: dict, atoms: list | None = None, cell: Cell | None = None) -> float:
    """Röntgendichte [g/cm³] aus Zellinhalt und Volumen."""
    from labcalc import chem
    cell = cell or Cell.of(phase["cell"], phase.get("system"))
    atoms = atoms if atoms is not None else expand(phase)
    m = sum(chem.element_weight(a["el"])[0] * a["occ"] for a in atoms)    # g/mol je Zelle
    return m / 6.02214076e23 / (cell.V * 1e-24)


# ----------------------------------------------------------------------------- CIF
def _num(s) -> float | None:
    """CIF-Zahl: '4.7589(3)' -> 4.7589, '?' / '.' -> None."""
    s = str(s).strip()
    if s in ("?", ".", ""):
        return None
    s = re.sub(r"\(\d+\)$", "", s)
    try:
        return float(s)
    except ValueError:
        try:
            return float(Fraction(s))
        except (ValueError, ZeroDivisionError):
            return None


def _tokens(line: str) -> list[str]:
    out, i, n = [], 0, len(line)
    while i < n:
        c = line[i]
        if c.isspace():
            i += 1
            continue
        if c in "'\"":
            j = i + 1
            while j < n and not (line[j] == c and (j + 1 == n or line[j + 1].isspace())):
                j += 1
            out.append(line[i + 1:j])
            i = j + 1
            continue
        j = i
        while j < n and not line[j].isspace():
            j += 1
        out.append(line[i:j])
        i = j
    return out


def parse_cif(text: str) -> dict:
    """Erster Datenblock einer CIF-Datei -> Phase (Zelle, Symmetrieoperationen, Atomlagen)."""
    items: dict[str, str] = {}
    loops: list[tuple[list[str], list[list[str]]]] = []
    lines = text.replace("\r", "").split("\n")
    i, n, blocks = 0, len(lines), 0
    while i < n:
        raw = lines[i]
        ln = raw.strip()
        if not ln or ln.startswith("#"):
            i += 1
            continue
        if ln.lower().startswith("data_"):
            blocks += 1
            if blocks > 1:
                break
            items["_data"] = ln[5:]
            i += 1
            continue
        if ln.lower() == "loop_":
            i += 1
            names = []
            while i < n and lines[i].strip().startswith("_"):
                names.append(lines[i].strip().split()[0].lower())
                i += 1
            vals: list[str] = []
            while i < n:
                s = lines[i]
                st = s.strip()
                if not st or st.startswith("#"):
                    i += 1
                    if not st and vals and len(vals) % max(1, len(names)) == 0:
                        continue
                    continue
                if st.startswith("_") or st.lower().startswith(("loop_", "data_")):
                    break
                if s.startswith(";"):
                    buf = [s[1:]]
                    i += 1
                    while i < n and not lines[i].startswith(";"):
                        buf.append(lines[i])
                        i += 1
                    vals.append("\n".join(buf).strip())
                    i += 1
                    continue
                vals.extend(_tokens(st))
                i += 1
            if names:
                rows = [vals[k:k + len(names)] for k in range(0, len(vals) - len(names) + 1, len(names))]
                loops.append((names, rows))
            continue
        if ln.startswith("_"):
            parts = ln.split(None, 1)
            key = parts[0].lower()
            if len(parts) > 1:
                tok = _tokens(parts[1])
                items[key] = tok[0] if tok else ""
                i += 1
                continue
            i += 1
            if i < n and lines[i].startswith(";"):
                buf = [lines[i][1:]]
                i += 1
                while i < n and not lines[i].startswith(";"):
                    buf.append(lines[i])
                    i += 1
                items[key] = "\n".join(buf).strip()
                i += 1
            elif i < n:
                tok = _tokens(lines[i].strip())
                items[key] = tok[0] if tok else ""
                i += 1
            continue
        i += 1

    def loop_with(*names):
        for ns, rows in loops:
            if any(x in ns for x in names):
                return ns, rows
        return None, []

    cell = {k: _num(items.get(f"_cell_length_{k}")) for k in ("a", "b", "c")}
    cell.update({k: _num(items.get(f"_cell_angle_{k}")) or 90.0 for k in ("alpha", "beta", "gamma")})
    if None in (cell["a"], cell["b"], cell["c"]):
        raise CrystError("CIF ohne vollständige Zelle (_cell_length_a/b/c)")
    ns, rows = loop_with("_symmetry_equiv_pos_as_xyz", "_space_group_symop_operation_xyz")
    ops = []
    if ns:
        col = ns.index("_symmetry_equiv_pos_as_xyz") if "_symmetry_equiv_pos_as_xyz" in ns else \
            ns.index("_space_group_symop_operation_xyz")
        ops = [r[col] for r in rows]
    else:
        for k in ("_symmetry_equiv_pos_as_xyz", "_space_group_symop_operation_xyz"):
            if items.get(k):
                ops = [items[k]]
    sg = items.get("_symmetry_space_group_name_h-m") or items.get("_space_group_name_h-m_alt") or ""
    if not ops:
        if sg.replace(" ", "").upper() in ("P1", ""):
            ops = ["x,y,z"]
        else:
            raise CrystError(f"Die CIF-Datei nennt die Raumgruppe {sg}, aber keine Symmetrieoperationen; ohne sie "
                             "lässt sich die Zelle nicht füllen. Bitte eine CIF mit _space_group_symop_operation_xyz "
                             "(z. B. aus der COD) verwenden.")
    for o in ops:
        parse_op(o)
    ns, rows = loop_with("_atom_site_fract_x")
    if not ns:
        raise CrystError("CIF ohne Atomlagen (_atom_site_fract_x)")
    ix = {k: ns.index(k) for k in ns}

    def g(r, k):
        return r[ix[k]] if k in ix and ix[k] < len(r) else None
    atoms = []
    for r in rows:
        sym = g(r, "_atom_site_type_symbol") or g(r, "_atom_site_label")
        el = FF.element_of(sym)
        x, y, z = (_num(g(r, f"_atom_site_fract_{c}")) for c in "xyz")
        if None in (x, y, z):
            continue
        occ = _num(g(r, "_atom_site_occupancy"))
        B = _num(g(r, "_atom_site_b_iso_or_equiv"))
        if B is None:
            U = _num(g(r, "_atom_site_u_iso_or_equiv"))
            B = 8 * math.pi ** 2 * U if U is not None else None
        atoms.append({"el": el, "x": x, "y": y, "z": z, "occ": 1.0 if occ is None else occ, "B": B,
                      "label": g(r, "_atom_site_label") or el})
    if not atoms:
        raise CrystError("CIF ohne lesbare Atomlagen")
    a, b, c = cell["a"], cell["b"], cell["c"]
    al, be, ga = cell["alpha"], cell["beta"], cell["gamma"]
    if abs(a - b) < 1e-4 and abs(b - c) < 1e-4 and all(abs(x - 90) < 1e-3 for x in (al, be, ga)):
        system = "cubic"
    elif abs(a - b) < 1e-4 and all(abs(x - 90) < 1e-3 for x in (al, be)) and abs(ga - 120) < 1e-3:
        system = "hexagonal"
    elif abs(a - b) < 1e-4 and all(abs(x - 90) < 1e-3 for x in (al, be, ga)):
        system = "tetragonal"
    elif all(abs(x - 90) < 1e-3 for x in (al, be, ga)):
        system = "orthorhombic"
    elif sum(abs(x - 90) > 1e-3 for x in (al, be, ga)) == 1:
        system = "monoclinic"
    else:
        system = "triclinic"
    name = items.get("_chemical_name_mineral") or items.get("_chemical_name_common") or \
        items.get("_chemical_name_systematic") or items.get("_chemical_formula_sum") or items.get("_data") or "CIF"
    cod = items.get("_cod_database_code")
    src = {"type": "misc", "title": f"{name} ({sg})".strip(), "note": "CIF-Datei"}
    if items.get("_journal_name_full") or items.get("_publ_section_title"):
        src = {"type": "article", "title": (items.get("_publ_section_title") or name).replace("\n", " ").strip(),
               "container": items.get("_journal_name_full", ""), "year": items.get("_journal_year", ""),
               "volume": items.get("_journal_volume", ""),
               "pages": "-".join(x for x in (items.get("_journal_page_first"), items.get("_journal_page_last")) if x),
               "authors": "; ".join(r[0] for r in loop_with("_publ_author_name")[1]) if loop_with("_publ_author_name")[0] else "",
               "doi": items.get("_journal_paper_doi", "")}
    if cod:
        src["note"] = (src.get("note", "") + f"; COD {cod}").strip("; ")
        src["url"] = f"https://www.crystallography.net/cod/{cod}.html"
    return {"id": "cif-" + re.sub(r"[^a-z0-9]+", "-", (cod or name).lower()).strip("-")[:30],
            "name": str(name).strip(), "formula": items.get("_chemical_formula_sum", "").strip(), "system": system,
            "spacegroup": sg, "cell": {"a": a, "b": b, "c": c, "alpha": al, "beta": be, "gamma": ga},
            "centring": "P", "ops": ops, "atoms": atoms, "source": src, "cif": True}


def phase_info(p: dict, lam: float = TUBES["Cu"][0], lang: str = "de") -> dict:
    """Für die Seite: Zelle, Atome der Zelle, Dichte, Linien."""
    cell = Cell.of(p["cell"], p.get("system"))
    atoms = expand(p)
    try:
        rho = density(p, atoms, cell)
    except Exception:  # noqa: BLE001 - Dichte ist Beigabe
        rho = None
    return {"id": p["id"], "name": p.get("name_en") if lang == "en" and p.get("name_en") else p.get("name"),
            "formula": p.get("formula", ""), "system": p.get("system", ""), "spacegroup": p.get("spacegroup", ""),
            "cell": cell.as_dict(), "atoms": atoms, "basis": cell.basis().tolist(), "rho": rho,
            "Z_atoms": len(atoms), "q": p.get("q"), "source": p.get("source"), "note": p.get("note", ""),
            "lines": reflections(p, lam, cell=cell, atoms=atoms)}
