"""Struktur eines Werkstoffs bei einer Temperatur: Gitter, Elementarzellen, Ketten, Netzwerke und Gefügeskizzen.

Jeder Werkstoff der Datenbank hat in data/gefuege.json einen Datensatz (Art, Zusammensetzung, Zustand, Phasen,
Übergänge, Quelle). build() setzt daraus die Ansichten ("panels") für eine Temperatur zusammen:

- scene: Atome in 3D (Gitterausschnitt aus gitter.build, Elementarzelle einer Phase aus der Raumgruppe mit Bindungen
  und Koordinationspolyedern, Polymerketten, Knäuel und Netzwerke, Glasnetzwerk, turbostratische Kohlenstoffschichten)
- sketch: schematische Gefügeskizze in 2D (Körner, Lamellen, Ausscheidungen, Fasern, Zuschlag …)

Die Kristallstrukturen stammen aus der Crystallography Open Database (data/structures.json, gemeinfrei, mit
COD-Nummer und Veröffentlichung), aus den eingebauten Phasen (data/phases.json) oder aus der Literatur
(data/structures_lit.json). Was ein Modell oder eine Skizze ist, steht in jeder Ansicht und im Bericht.

temper() rechnet einen Wärmebehandlungsweg (Härten und Anlassen, Lösungsglühen und Auslagern, Rekristallisieren)
als Folge von Zuständen für die Animation.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np

from . import cryst
from . import gitter as GT
from . import polymer as PY

DATA = Path(__file__).resolve().parent / "data"
T0 = 273.15
R_GAS = 8.314462618


class StructError(ValueError):
    pass


# ============================================================================ Daten
@lru_cache(maxsize=1)
def _gef() -> dict:
    return json.loads((DATA / "gefuege.json").read_text("utf-8"))


@lru_cache(maxsize=1)
def _cod() -> dict:
    d = json.loads((DATA / "structures.json").read_text("utf-8"))
    return {p["id"]: p for p in d["phasen"]}


@lru_cache(maxsize=1)
def _lit() -> dict:
    return json.loads((DATA / "structures_lit.json").read_text("utf-8"))


def record(mid: str) -> dict:
    r = _gef()["werkstoffe"].get(mid)
    if r is None:
        raise StructError(f"Für „{mid}“ ist keine Struktur hinterlegt")
    return r


@lru_cache(maxsize=1)
def sources_registry() -> dict:
    """Quellen der Strukturdaten: Normen und Bücher aus gefuege.json, Literatur aus structures_lit.json und die
    Veröffentlichungen der COD-Einträge (Schlüssel cod<Nummer>)."""
    out = {}
    out.update(_gef().get("quellen") or {})
    out.update(_lit().get("quellen") or {})
    for p in _cod().values():
        out[f"cod{p['cod']}"] = dict(p["source"])
    return out


def phase_any(pid: str) -> dict:
    """Phase aus COD-, Literatur- oder eingebauten Daten; `_q` = Quellenschlüssel, `_art` = cod|lit|builtin."""
    if pid in _cod():
        p = dict(_cod()[pid])
        p["_q"] = [f"cod{p['cod']}"]
        p["_art"] = "cod"
        return p
    for p in _lit().get("phasen") or []:
        if p["id"] == pid:
            p = dict(p)
            q = p.get("q")
            p["_q"] = [q] if isinstance(q, str) else list(q or [])
            p["_art"] = "lit"
            return p
    for p in cryst.builtin_phases():
        if p["id"] == pid:
            p = dict(p)
            p["_q"] = ["wyckoff1963"]
            p["_art"] = "builtin"
            return p
    if pid == "cao":                                  # Kalk (Natriumchlorid-Typ), für Beton über 500 °C
        return {"id": "cao", "name": "Calciumoxid CaO", "name_en": "Calcium oxide CaO", "system": "cubic",
                "centring": "F", "cell": {"a": 4.811}, "ops": ["x,y,z"],
                "atoms": [{"el": "Ca", "x": 0, "y": 0, "z": 0}, {"el": "O", "x": .5, "y": .5, "z": .5}],
                "_q": ["wyckoff1963"], "_art": "builtin"}
    raise StructError(f"Phase „{pid}“ nicht hinterlegt")


def pname(p: dict, de: bool) -> str:
    return (p.get("name") if de else p.get("name_en") or p.get("name")) or p.get("id", "")


# ============================================================================ Elemente, Farben, Radien
RC = {"H": .31, "Li": 1.28, "B": .84, "C": .76, "N": .71, "O": .66, "F": .57, "Na": 1.66, "Mg": 1.41, "Al": 1.21,
      "Si": 1.11, "P": 1.07, "S": 1.05, "Cl": 1.02, "K": 2.03, "Ca": 1.76, "Ti": 1.60, "V": 1.53, "Cr": 1.39,
      "Mn": 1.39, "Fe": 1.32, "Co": 1.26, "Ni": 1.24, "Cu": 1.32, "Zn": 1.22, "Ga": 1.22, "Ge": 1.20, "As": 1.19,
      "Sr": 1.95, "Zr": 1.75, "Nb": 1.64, "Mo": 1.54, "Ag": 1.45, "Cd": 1.44, "Sn": 1.39, "Cs": 2.44, "Ce": 2.04,
      "Ta": 1.70, "W": 1.62, "Pt": 1.36, "Au": 1.36, "Pb": 1.46, "Y": 1.90}            # Cordero et al. 2008
NONMETAL = {"H", "B", "C", "N", "O", "F", "Si", "P", "S", "Cl", "Ge", "As"}
ANION = {"O", "N", "F", "Cl"}
EL_COL = dict(GT.EL_COL)
EL_COL.update({"O": "#d8423f", "N": "#3f6fd8", "C": "#3a3a3a", "F": "#6cc04a", "Cl": "#2fa86a", "S": "#e5c33a",
               "Na": "#a77bdb", "K": "#8e5fc9", "Ca": "#6fa6c9", "Li": "#c58bd9", "Zr": "#5fa59a", "Ga": "#c49b7b",
               "As": "#9a7bb0", "Sr": "#58a08a", "Ce": "#d8b75a", "Y": "#8fb0c8", "H": "#e8e8e8", "B": "#e8a33c",
               "P": "#e07b39", "Cs": "#6a5acd", "Ge": "#7a9a8a"})


def el_of(label: str) -> str:
    s = str(label or "").strip()
    if len(s) >= 2 and s[1].islower() and s[:2] in RC:
        return s[:2]
    return s[:1].upper() if s[:1].upper() in RC else s[:2]


def _col(el: str) -> str:
    return EL_COL.get(el, "#8a8f98")


class _Scene:
    """Atome, Arten, Bindungen und Polyeder einer 3D-Ansicht."""

    def __init__(self):
        self.P: list = []
        self.K: list = []
        self.kinds: list = []
        self._kid: dict = {}
        self.bonds: list = []
        self.polys: list = []
        self.labels: list = []

    def kind(self, kid: str, el: str, name: str, r: float, color: str | None = None, role: str = "") -> int:
        if kid not in self._kid:
            self._kid[kid] = len(self.kinds)
            self.kinds.append({"id": kid, "el": el, "name": name, "color": color or _col(el), "r": round(r, 3),
                               "role": role})
        return self._kid[kid]

    def add(self, p, k: int) -> int:
        self.P.append([float(p[0]), float(p[1]), float(p[2])])
        self.K.append(k)
        return len(self.P) - 1

    def out(self, cell_corners=None, extra: dict | None = None) -> dict:
        P = np.asarray(self.P, float).reshape(-1, 3)
        box = (P.max(0) - P.min(0)).tolist() if len(P) else [1, 1, 1]
        o = {"atoms": [[round(p[0], 3), round(p[1], 3), round(p[2], 3), k] for p, k in zip(self.P, self.K)],
             "kinds": self.kinds, "bonds": self.bonds, "polys": self.polys, "labels": self.labels,
             "center": (P.mean(0).round(3).tolist() if len(P) else [0, 0, 0]), "box": box,
             "cell": ({"corners": np.asarray(cell_corners).round(3).tolist(), "edges": GT.CELL_EDGES}
                      if cell_corners is not None else None)}
        if extra:
            o.update(extra)
        return o


_CELL_FR = np.array([[x, y, z] for x in (0, 1) for y in (0, 1) for z in (0, 1)], float)


# ============================================================================ Elementarzelle einer Phase
def expand_any(ph: dict) -> list[tuple[str, np.ndarray, float, str]]:
    """Wie cryst.expand, aber ohne Formfaktoren: (Element, Bruchkoordinaten, Besetzung, Label)."""
    ops = [cryst.parse_op(o) for o in (ph.get("ops") or ["x,y,z"])]
    cen = cryst.CENTRING.get((ph.get("centring") or "P").upper()) or [(0, 0, 0)]
    out = []
    for at in ph.get("atoms") or []:
        el = el_of(at.get("el") or at.get("label"))
        p0 = np.array([float(at["x"]), float(at["y"]), float(at["z"])])
        mine: list = []
        for R, t in ops:
            for c in cen:
                p = (R @ p0 + t + np.array(c)) % 1.0
                p[np.isclose(p, 1.0, atol=1e-6)] = 0.0
                if not any(np.all(np.abs(((p - q) + 0.5) % 1.0 - 0.5) < 2e-3) for q in mine):
                    mine.append(p)
        occ = float(at.get("occ", 1) if at.get("occ") not in (None, "") else 1)
        out += [(el, p, occ, at.get("label") or el) for p in mine]
    return out


def _polyhedron_faces(V: np.ndarray) -> list:
    n = len(V)
    if n == 4:
        return [[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]]
    if n == 6:
        c = V.mean(0)
        opp = {}
        for i in range(6):
            opp[i] = int(np.argmax([np.dot(V[i] - c, V[j] - c) * -1 if j != i else -1e9 for j in range(6)]))
        faces = []
        for i in range(6):
            for j in range(i + 1, 6):
                for k in range(j + 1, 6):
                    if opp[i] in (j, k) or opp[j] == k:
                        continue
                    faces.append([i, j, k])
        return faces if len(faces) == 8 else []
    return []


def cell_scene(ph: dict, reps=(1, 1, 1), de: bool = True, max_atoms: int = 900, polyhedra: bool = True) -> dict:
    """Elementarzelle(n) einer Phase mit Bindungen (Kovalenzradien, nicht zwischen zwei Metallen) und Tetraeder- bzw.
    Oktaederpolyedern um Kationen in Oxiden und Nitriden."""
    cell = cryst.Cell.of(ph["cell"], ph.get("system"))
    B = cell.basis()
    reps = np.asarray(reps, int)
    sc = _Scene()
    if ph.get("nur_zelle") or not ph.get("atoms"):
        corners = (_CELL_FR * reps) @ B
        ctr = corners.mean(0)
        sc.labels.append({"p": ctr.round(3).tolist(), "text": ph.get("inhalt") or ph.get("formula") or pname(ph, de)})
        return sc.out(corners, {"schematic": True, "n_cell": 0, "phase": ph.get("id"), "formula": ph.get("formula")})
    base = expand_any(ph)
    shifts = [np.array([i, j, k]) for i in range(-1, reps[0] + 1) for j in range(-1, reps[1] + 1)
              for k in range(-1, reps[2] + 1)]
    cand = []
    for el, f, occ, lab in base:
        for s in shifts:
            q = f + s
            if np.all(q > -0.34) and np.all(q < reps + 0.34):
                cand.append((el, q, occ, lab))
    inside = np.array([bool(np.all(q > -0.01) and np.all(q < reps + 0.01)) for _, q, _, _ in cand])
    X = np.array([q for _, q, _, _ in cand]) @ B
    els = [c[0] for c in cand]
    # Bindungen
    n = len(cand)
    D = np.sqrt(((X[:, None, :] - X[None, :, :]) ** 2).sum(-1)) if n <= 3000 else None
    bonded = np.zeros((n, n), bool)
    if D is not None:
        for i in range(n):
            for j in range(i + 1, n):
                a, b = els[i], els[j]
                if a not in NONMETAL and b not in NONMETAL:
                    continue
                if a in ANION and b in ANION:
                    continue
                lim = 1.18 * (RC.get(a, 1.3) + RC.get(b, 1.3))
                if 0.6 < D[i, j] < lim:
                    bonded[i, j] = bonded[j, i] = True
    keep = inside.copy()
    # Bindungspartner ausserhalb der Zelle (Anionen), damit Polyeder vollständig sind
    for i in np.where(~inside)[0]:
        if els[i] in ANION and bonded[i][inside].any():
            keep[i] = True
    idx = np.where(keep)[0]
    if len(idx) > max_atoms:
        raise StructError(f"Zelle zu gross für die Ansicht ({len(idx)} Atome)")
    m = {}
    occ_note = False
    for i in idx:
        el, q, occ, lab = cand[i]
        part = occ < 0.999
        occ_note |= part
        nm = GT_name(el, de) + (f" ({occ * 100:.0f} % besetzt)" if de else f" ({occ * 100:.0f} % occupied)") if part else GT_name(el, de)
        k = sc.kind(f"{el}{'~' if part else ''}{'o' if not inside[i] else ''}", el, nm,
                    0.5 * RC.get(el, 1.3) if (el in NONMETAL or any(e in NONMETAL for e in els)) else 0.5 * RC.get(el, 1.3) * 1.1,
                    role="occ" if part else ("out" if not inside[i] else ""))
        m[i] = sc.add(X[i], k)
    for i in idx:
        for j in np.where(bonded[i])[0]:
            if j > i and j in m:
                sc.bonds.append([m[i], m[int(j)]])
    if polyhedra and any(e in ANION for e in els):
        for i in idx:
            if not inside[i] or els[i] in ANION or els[i] in ("C", "H"):
                continue
            nb = [int(j) for j in np.where(bonded[i])[0] if j in m and els[j] in ANION]
            if len(nb) in (4, 6):
                faces = _polyhedron_faces(X[nb])
                if faces:
                    sc.polys.append({"v": [m[j] for j in nb], "faces": faces, "color": _col(els[i]), "cn": len(nb),
                                     "center": m[i]})
    corners = (_CELL_FR * reps) @ B
    return sc.out(corners, {"phase": ph.get("id"), "formula": ph.get("formula"), "n_cell": int(inside.sum()),
                            "partial": occ_note, "cellpar": cell.as_dict(), "system": ph.get("system"),
                            "spacegroup": ph.get("spacegroup")})


_EL_NAMES = {"Fe": ("Eisen", "iron"), "C": ("Kohlenstoff", "carbon"), "O": ("Sauerstoff", "oxygen"),
             "N": ("Stickstoff", "nitrogen"), "Si": ("Silicium", "silicon"), "Al": ("Aluminium", "aluminium"),
             "Mg": ("Magnesium", "magnesium"), "Cu": ("Kupfer", "copper"), "Zn": ("Zink", "zinc"),
             "Ca": ("Calcium", "calcium"), "Na": ("Natrium", "sodium"), "Ni": ("Nickel", "nickel"),
             "Cr": ("Chrom", "chromium"), "Ti": ("Titan", "titanium"), "Zr": ("Zirconium", "zirconium"),
             "Sn": ("Zinn", "tin"), "Nb": ("Niob", "niobium"), "Mo": ("Molybdän", "molybdenum"),
             "Mn": ("Mangan", "manganese"), "Li": ("Lithium", "lithium"), "H": ("Wasserstoff", "hydrogen"),
             "B": ("Bor", "boron"), "K": ("Kalium", "potassium"), "F": ("Fluor", "fluorine"),
             "Cl": ("Chlor", "chlorine"), "S": ("Schwefel", "sulfur"), "Y": ("Yttrium", "yttrium")}


def GT_name(el: str, de: bool) -> str:
    n = _EL_NAMES.get(el)
    return f"{el} ({n[0] if de else n[1]})" if n else el


# ============================================================================ Gitterausschnitt mit Teilbesetzung
def section_scene(A: np.ndarray, basis: list, n: int, rng, de: bool, names: dict, cell_mark: bool = True) -> dict:
    """Ausschnitt n×n×n aus Gittervektoren A (Zeilen) und Basis [(Element, Bruchkoordinaten, Besetzung)]; Plätze mit
    Besetzung < 1 werden zufällig besetzt (z. B. Kohlenstoff im Martensit)."""
    sc = _Scene()
    for i in range(n):
        for j in range(n):
            for k in range(n):
                for el, f, occ in basis:
                    if occ < 1 and rng.random() >= occ:
                        continue
                    kk = sc.kind(el, el, names.get(el, el), 0.5 * (RC.get(el, 1.3) if el in NONMETAL else GT.metal_radius(el)[0]))
                    sc.add((np.array([i, j, k]) + np.asarray(f)) @ A, kk)
    mid = n // 2
    corners = (_CELL_FR + mid) @ A if cell_mark else None
    return sc.out(corners)


def martensite_scene(c_wt: float, T: float, rng, de: bool, n: int = 4) -> tuple[dict, dict]:
    """Martensit: tetragonal raumzentriertes Fe mit C auf Oktaederplätzen der z-Untergruppe (Roberts 1953:
    a = 2,866 − 0,013·C, c = 2,866 + 0,116·C in Å, C in Gew.-%)."""
    a = 2.866 - 0.013 * c_wt
    c = 2.866 + 0.116 * c_wt
    x = GT.at_of("Fe", "C", c_wt)
    per_fe = x / max(1 - x, 1e-9)                       # C je Fe
    occ = min(per_fe, 1.0)                              # 2 Fe und 2 z-Plätze je Zelle
    A = np.diag([a, a, c])
    basis = [("Fe", (0, 0, 0), 1.0), ("Fe", (.5, .5, .5), 1.0), ("C", (0, 0, .5), occ), ("C", (.5, .5, 0), occ)]
    names = {"Fe": "Fe (Martensit)" if de else "Fe (martensite)",
             "C": "C auf Oktaederplatz (z)" if de else "C on octahedral site (z)"}
    sc = section_scene(A, basis, n, rng, de, names)
    return sc, {"a": a, "c": c, "c_a": c / a, "C_wt": c_wt}


# ============================================================================ Polymere
def _place_chain(sc: _Scene, ch: dict, origin, rot: float, shear_c=None, zscale: float = 1.0, de: bool = True,
                 pid: str = "", tag: str = ""):
    ca, sa = math.cos(rot), math.sin(rot)
    base = len(sc.P)
    for el, q, role in ch["atoms"]:
        x, y, z = q
        xr, yr = ca * x - sa * y, sa * x + ca * y
        z *= zscale
        p = np.array([xr, yr, 0.0]) + np.asarray(origin, float)
        if shear_c is not None:
            p = p + shear_c * (z / np.linalg.norm(shear_c))
        else:
            p[2] += z
        nm = {"rueckgrat": ("Rückgrat", "backbone"), "ring": ("Ring", "ring"), "seite": ("Seitengruppe", "side group")}[role]
        k = sc.kind(f"{el}:{role}{tag}", el, f"{el} · {nm[0] if de else nm[1]}", 0.42 * RC.get(el, 0.8),
                    role=role)
        sc.add(p, k)
    for i, j in ch["bonds"]:
        sc.bonds.append([base + i, base + j])


def chain_scene(pid: str, units: int, de: bool, helix=None, crystal: bool = True, rng=None) -> dict:
    sc = _Scene()
    hx = helix if crystal else (2, 1)
    ch = PY.chain(pid, units, hx, rng=rng)
    _place_chain(sc, ch, (0, 0, 0), 0.0, de=de, pid=pid)
    return sc.out(None, {"repeat": ch["repeat"], "helix": list(hx or PY.POLY[pid]["helix"]),
                         "formel": PY.POLY[pid]["formel"]})


def polymer_cell_scene(cid: str, de: bool) -> dict:
    ph = phase_any(cid)
    cell = cryst.Cell.of(ph["cell"], ph.get("system"))
    B = cell.basis()
    pid = ph["polymer"]
    hx = tuple(ph.get("helix") or PY.POLY[pid]["helix"])
    one = PY.chain(pid, 1, hx, period=cell.c)
    u = max(1, round(cell.c / max(one["repeat"], 0.3)))
    if hx != (2, 1):
        u = hx[0] * max(1, round(cell.c / (hx[0] * one["repeat"])))
    ch = PY.chain(pid, u, hx, period=cell.c)
    zs = cell.c / max(ch["axis_len"], 1e-6)
    sc = _Scene()
    cvec = B[2]
    for x, y, setting in ph.get("ketten") or [[0, 0, 0]]:
        o = np.array([x, y, 0.0]) @ B
        _place_chain(sc, ch, o, math.radians(setting), shear_c=cvec if abs(cvec[0]) + abs(cvec[1]) > 1e-3 else None,
                     zscale=zs, de=de, pid=pid)
    return sc.out(_CELL_FR @ B, {"phase": cid, "cellpar": cell.as_dict(), "system": ph.get("system"),
                                 "spacegroup": ph.get("spacegroup"), "helix": list(hx), "chains": len(ph.get("ketten") or [1]),
                                 "schematic_pos": bool(ph.get("kettenlage_schematisch"))})


def _backbone_elements(pid: str) -> list[str]:
    out = []
    for t in PY.POLY[pid]["unit"]:
        b, _ = PY._parse(t)
        out.append("C" if b in PY.RINGS else b)
    return out


def coil_scene(pid: str, de: bool, rng, n_chains: int = 5, n_atoms: int = 70, box: float = 22.0,
               xlink: float = 0.0, xel: str = "C", glassy: bool = True) -> dict:
    """Amorphe Knäuel (nur Rückgratatome) in einem Kasten; xlink = Vernetzungsstellen je Rückgratatom."""
    sc = _Scene()
    els = _backbone_elements(pid)
    chains = []
    L = np.array([box] * 3)
    for c in range(n_chains):
        pts = PY.random_coil(n_atoms, L, rng)
        idx = []
        for i, p in enumerate(pts):
            el = els[i % len(els)]
            k = sc.kind(f"{el}:k{c % 6}", el, (f"Kette {c % 6 + 1}" if de else f"chain {c % 6 + 1}"), 0.42 * RC.get(el, .8),
                        color=["#5b7db1", "#c0703c", "#4f9a65", "#9a5fb0", "#b8a03a", "#5aa6a6"][c % 6], role="kette")
            idx.append(sc.add(p, k))
        for a, b in zip(idx, idx[1:]):
            sc.bonds.append([a, b])
        chains.append((idx, pts))
    links = 0
    if xlink > 0:
        want = int(round(xlink * n_chains * n_atoms))
        allp = [(ci, ii, p) for ci, (idx, pts) in enumerate(chains) for ii, p in zip(idx, pts)]
        P = np.array([p for _, _, p in allp])
        tries = 0
        used = set()
        while links < want and tries < 4000:
            tries += 1
            a = int(rng.integers(len(allp)))
            d = np.sqrt(((P - P[a]) ** 2).sum(1))
            cand = [b for b in np.where((d > 2.5) & (d < 6.5))[0] if allp[b][0] != allp[a][0] and b not in used]
            if not cand or a in used:
                continue
            b = int(cand[int(rng.integers(len(cand)))])
            k = sc.kind(f"x:{xel}", xel, ("Vernetzungsstelle " if de else "Cross-link ") + xel, 0.55 * RC.get(xel, .8),
                        color="#d1495b" if xel == "S" else "#e07b39", role="xlink")
            m = sc.add((P[a] + P[b]) / 2, k)
            sc.bonds += [[allp[a][1], m], [m, allp[b][1]]]
            used |= {a, b}
            links += 1
    return sc.out(None, {"links": links, "glassy": glassy})


# ============================================================================ Glas
MOLAR = {"SiO2": 60.08, "B2O3": 69.62, "Al2O3": 101.96, "Na2O": 61.98, "K2O": 94.2, "Li2O": 29.88, "CaO": 56.08,
         "MgO": 40.30, "TiO2": 79.87, "ZnO": 81.38, "BaO": 153.3}
MODIFIER = {"Na2O": ("Na", 2), "K2O": ("K", 2), "Li2O": ("Li", 2), "CaO": ("Ca", 1), "MgO": ("Mg", 1), "ZnO": ("Zn", 1),
            "BaO": ("Ca", 1)}


def glass_scene(netz: dict, de: bool, rng, T: float | None = None, Tg: float | None = None) -> tuple[dict, dict]:
    """Ungeordnetes Netzwerk nach Zachariasen (1932): SiO₄-Tetraeder über Brückensauerstoff verknüpft, aus einem stark
    gestörten Cristobalitgerüst; Netzwerkwandler (Na, K, Ca, Mg) trennen Brücken und sitzen neben den
    Trennstellensauerstoffen; Al und B ersetzen Si (schematisch)."""
    mol = {k: v / MOLAR[k] for k, v in netz.items() if k in MOLAR and v > 0}
    n_si_mol = mol.get("SiO2", 0)
    n_b = 2 * mol.get("B2O3", 0)
    n_al = 2 * mol.get("Al2O3", 0) + 0
    formers = n_si_mol + n_b + n_al + mol.get("TiO2", 0)
    a = 7.16
    nc = 2
    fcc = np.array([[0, 0, 0], [.5, .5, 0], [.5, 0, .5], [0, .5, .5]])
    si = []
    for i in range(nc):
        for j in range(nc):
            for k in range(nc):
                for f in fcc:
                    for d in ((0, 0, 0), (.25, .25, .25)):
                        si.append((np.array([i, j, k]) + f + np.array(d)) * a)
    si = np.array(si)
    nn = a * math.sqrt(3) / 4
    pairs = [(i, j) for i in range(len(si)) for j in range(i + 1, len(si)) if abs(np.linalg.norm(si[i] - si[j]) - nn) < 0.05]
    si = si + rng.normal(0, 0.42, si.shape)
    N = len(si)
    kind_of = ["Si"] * N
    order = rng.permutation(N)
    n_alat = int(round(N * n_al / formers)) if formers else 0
    n_bat = int(round(N * n_b / formers)) if formers else 0
    for i in order[:n_alat]:
        kind_of[i] = "Al"
    for i in order[n_alat:n_alat + n_bat]:
        kind_of[i] = "B"
    # Trennstellen: je Wandleroxid eine Brücke, Al bindet Wandler zum Ladungsausgleich
    mod_cat = []
    for k, (el, per) in MODIFIER.items():
        if mol.get(k):
            mod_cat.append((el, per, mol[k]))
    mod_total = sum(m for _, _, m in mod_cat)
    breaks = int(round(len(pairs) * max(mod_total - n_al / 2, 0) / (2 * formers))) if formers else 0
    breaks = min(breaks, len(pairs) // 2)
    sc = _Scene()
    names = {"Si": "Si (Netzwerkbildner)" if de else "Si (network former)",
             "Al": "Al (im Netzwerk)" if de else "Al (in the network)", "B": "B (im Netzwerk)" if de else "B (in the network)"}
    kid = {}
    for el in ("Si", "Al", "B"):
        kid[el] = sc.kind(el, el, names[el], 0.45 * RC[el])
    ob = sc.kind("Ob", "O", "O, Brücke" if de else "O, bridging", 0.5 * RC["O"])
    onb = sc.kind("Onb", "O", "O, Trennstelle" if de else "O, non-bridging", 0.5 * RC["O"], color="#f08c6c")
    sidx = [sc.add(p, kid[kind_of[i]]) for i, p in enumerate(si)]
    brk = set(rng.choice(len(pairs), size=breaks, replace=False).tolist()) if breaks else set()
    cat_list = []
    for el, per, m in mod_cat:
        cat_list += [(el, per)] * max(1, int(round(breaks * m / max(mod_total, 1e-9))))
    rng.shuffle(cat_list)
    ci = 0
    for pi_, (i, j) in enumerate(pairs):
        s1, s2 = si[i], si[j]
        d = np.linalg.norm(s2 - s1)
        u = (s2 - s1) / d
        if pi_ in brk:
            perp = PY._perp(u)
            o1 = s1 + 1.61 * PY._unit(u + 0.3 * perp)
            o2 = s2 - 1.61 * PY._unit(u - 0.3 * perp)
            a1, a2 = sc.add(o1, onb), sc.add(o2, onb)
            sc.bonds += [[sidx[i], a1], [sidx[j], a2]]
            if ci < len(cat_list):
                el, per = cat_list[ci]
                ci += 1
                kc = sc.kind("M" + el, el, (f"{el} (Netzwerkwandler)" if de else f"{el} (network modifier)"), 0.42 * RC.get(el, 1.5))
                sc.add((o1 + o2) / 2 + perp * 1.2 + rng.normal(0, .2, 3), kc)
            continue
        mid = (s1 + s2) / 2
        h = math.sqrt(max(1.61 ** 2 - (d / 2) ** 2, 0))
        perp = PY._perp(u)
        rot = rng.uniform(0, 2 * math.pi)
        perp = math.cos(rot) * perp + math.sin(rot) * np.cross(u, perp)
        o = sc.add(mid + h * perp, ob)
        sc.bonds += [[sidx[i], o], [o, sidx[j]]]
    info = {"breaks": breaks, "formers": N, "Al": n_alat, "B": n_bat,
            "nbo_per_t": round(2 * breaks / N, 2) if N else 0}
    return sc.out(None, info), info


# ============================================================================ Kohlenstofffaser
def turbostratic_scene(d002: float, Lc_nm: float, order: float, de: bool, rng) -> dict:
    """Turbostratische Graphenschichten: Abstand d002, Stapelhöhe Lc, Schichten gegeneinander verdreht und versetzt
    (Ordnung 1 = graphitisch); Wellung schematisch."""
    sc = _Scene()
    nl = int(max(3, min(10, round(Lc_nm * 10 / d002))))
    R = 6.5 + 5 * order
    a1, a2 = np.array([2.46, 0]), np.array([1.23, 2.1304])
    pts = []
    m = int(R / 1.2) + 3
    for i in range(-m, m + 1):
        for j in range(-m, m + 1):
            for b in (np.zeros(2), np.array([1.23, 0.7101])):
                p = i * a1 + j * a2 + b
                if np.linalg.norm(p) <= R:
                    pts.append(p)
    pts = np.array(pts)
    kc = sc.kind("C", "C", "C (Graphenschicht)" if de else "C (graphene layer)", 0.32)
    amp = 0.7 * (1 - order)
    for L in range(nl):
        rot = rng.normal(0, (1 - order) * 1.2) if order < 0.95 else (0.0 if L % 2 == 0 else 0.0)
        cr, sr = math.cos(rot), math.sin(rot)
        sh = rng.normal(0, 1.2 * (1 - order), 2) + (np.array([1.23, 0.7101]) if L % 2 else 0)
        P = pts @ np.array([[cr, sr], [-sr, cr]]) + sh
        z = L * d002 + amp * np.sin(P[:, 0] / 4.0 + rng.uniform(0, 6))
        idx = [sc.add((p[0], p[1], zz), kc) for p, zz in zip(P, z)]
        D = np.sqrt(((P[:, None, :] - P[None, :, :]) ** 2).sum(-1))
        ii, jj = np.where((D > 1.3) & (D < 1.55))
        sc.bonds += [[idx[a], idx[b]] for a, b in zip(ii, jj) if a < b]
    return sc.out(None, {"layers": nl, "La": round(2 * R, 1)})


# ============================================================================ Gefügeskizzen (2D)
def _tess(n: int, rng, jitter: float = 0.32, sy: float = 1.0):
    """Körner als duale Zerlegung eines verrauschten Dreiecksgitters; sy < 1 streckt die Körner in x (Walzen)."""
    h = 1.0 / n
    pts = {}
    rows = int(math.ceil(n / sy / 0.866)) + 3
    for r in range(-2, rows):
        for c in range(-2, n + 3):
            x = (c + 0.5 * (r % 2)) * h
            y = r * h * 0.866 * sy
            pts[(r, c)] = np.array([x + rng.normal(0, jitter * h), y + rng.normal(0, jitter * h * sy)])

    def nbrs(r, c):
        if r % 2 == 0:
            return [(r, c + 1), (r + 1, c), (r + 1, c - 1), (r, c - 1), (r - 1, c - 1), (r - 1, c)]
        return [(r, c + 1), (r + 1, c + 1), (r + 1, c), (r, c - 1), (r - 1, c), (r - 1, c + 1)]
    polys = []
    for (r, c), p in pts.items():
        nb = nbrs(r, c)
        if not all(k in pts for k in nb):
            continue
        vs = [(p + pts[nb[i]] + pts[nb[(i + 1) % 6]]) / 3 for i in range(6)]
        cx, cy = np.mean(vs, 0)
        if -0.2 < cx < 1.2 and -0.2 < cy < 1.2:
            polys.append([v.round(4).tolist() for v in vs])
    return polys


def _centroid(poly):
    return np.mean(np.asarray(poly), 0)


def _shrink(poly, f):
    c = _centroid(poly)
    return [(c + f * (np.asarray(v) - c)).round(4).tolist() for v in poly]


def _lines_in(poly, angle, spacing, rng, color, sw, op=1.0):
    """Parallele Linien (Lamellen, Latten) im Korn, über Clip auf das Korn begrenzt."""
    # kompakt: der Zeichner erzeugt die Linien selbst (Browser und Bericht), siehe hatch_lines
    return {"t": "hatch", "poly": poly, "a": round(float(angle), 4), "s": spacing, "o": round(float(rng.uniform(0, 1)), 3),
            "stroke": color, "sw": sw, "op": op}


def hatch_lines(it: dict) -> list:
    """Linien eines hatch-Elements (für Renderer ohne eigene Schraffur): [[p0, p1], ...] vor dem Beschneiden."""
    poly = it["poly"]
    c = _centroid(poly)
    d = np.array([math.cos(it["a"]), math.sin(it["a"])])
    nrm = np.array([-d[1], d[0]])
    R = max(np.linalg.norm(np.asarray(v) - c) for v in poly) * 1.1
    out = []
    s = -R + it.get("o", 0) * it["s"]
    while s < R:
        out.append([(c + nrm * s - d * R).tolist(), (c + nrm * s + d * R).tolist()])
        s += it["s"]
    return out


def _dots_in(poly, n, r, rng, color, margin=0.0, elong=0.0, angle=None):
    """Teilchen im Korn als ein kompaktes Element: dots {p: [[x, y], ...], r} bzw. dashes {p: [[x, y, Winkel], ...],
    len} für längliche Teilchen."""
    c = _centroid(poly)
    P = np.asarray(poly)
    pts = []
    tries = 0
    while len(pts) < n and tries < n * 30:
        tries += 1
        q = c + (rng.uniform(-1, 1, 2) * (P.max(0) - P.min(0)) / 2)
        if not _inside(q, P, margin):
            continue
        if elong > 0:
            a = angle if angle is not None else rng.choice([0, math.pi / 2, math.pi / 4])
            pts.append([round(float(q[0]), 4), round(float(q[1]), 4), round(float(a), 3)])
        else:
            pts.append([round(float(q[0]), 4), round(float(q[1]), 4)])
    if not pts:
        return []
    if elong > 0:
        return [{"t": "dashes", "p": pts, "len": elong, "stroke": color, "sw": max(r * 400, 0.8)}]
    return [{"t": "dots", "p": pts, "r": round(r, 4), "fill": color}]


def _inside(q, P, margin=0.0) -> bool:
    x, y = q
    n = len(P)
    ins = False
    for i in range(n):
        x1, y1 = P[i]
        x2, y2 = P[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-12) + x1:
            ins = not ins
    if not ins or margin <= 0:
        return ins
    for i in range(n):
        a, b = np.asarray(P[i]), np.asarray(P[(i + 1) % n])
        t = np.clip(np.dot(q - a, b - a) / max(np.dot(b - a, b - a), 1e-12), 0, 1)
        if np.linalg.norm(q - (a + t * (b - a))) < margin:
            return False
    return True


def _grain_items(polys, fill, stroke="#6b6b6b", sw=0.8):
    return [{"t": "poly", "p": p, "fill": fill, "stroke": stroke, "sw": sw} for p in polys]


C_FERRIT, C_PERLIT, C_ZEM, C_AUST, C_MART, C_CARB = "#eef0f2", "#c9b9a8", "#3b2f2a", "#e7eef7", "#a7b3c2", "#2e2622"
C_AL, C_PREC, C_LIQ, C_BETA = "#e8edf3", "#7a4b2a", "#e8c9a0", "#8f9fb8"


def sk_metal(kind: str, rng, de: bool, **o) -> dict:
    """Gefügeskizze eines Metalls; kind: ferrit-perlit, martensit, angelassen, austenit, ferrit, gjl, gjs, al,
    zweiphasig, fcc, hcp, schmelze, teilschmelze. Schematisch, nicht massstäblich."""
    items, legend = [], []
    n = o.get("n", 6)
    sy = 0.45 if o.get("gewalzt") else 1.0
    polys = _tess(n if not o.get("gewalzt") else n, rng, sy=sy)
    if kind == "schmelze":
        items.append({"t": "poly", "p": [[0, 0], [1, 0], [1, 1], [0, 1]], "fill": C_LIQ, "stroke": "none"})
        for _ in range(60):
            q = rng.uniform(0, 1, 2)
            items.append({"t": "circle", "c": q.round(3).tolist(), "r": 0.004, "fill": "#b48a5a", "op": 0.6})
        legend.append({"color": C_LIQ, "label": "Schmelze" if de else "melt"})
        return {"items": items, "legend": legend}
    if kind == "teilschmelze":
        f_l = o.get("f_l", 0.3)
        items.append({"t": "poly", "p": [[0, 0], [1, 0], [1, 1], [0, 1]], "fill": C_LIQ, "stroke": "none"})
        items += _grain_items([_shrink(p, math.sqrt(max(1 - f_l, 0.05))) for p in polys], o.get("fill", C_AUST))
        legend += [{"color": o.get("fill", C_AUST), "label": o.get("solid", "fest" if de else "solid")},
                   {"color": C_LIQ, "label": "Schmelze" if de else "melt"}]
        return {"items": items, "legend": legend}
    if kind == "ferrit-perlit":
        fp = o.get("f_p", 0.3)
        sel = set(rng.choice(len(polys), size=int(round(fp * len(polys))), replace=False).tolist()) if fp > 0 else set()
        for i, p in enumerate(polys):
            items.append({"t": "poly", "p": p, "fill": C_PERLIT if i in sel else C_FERRIT, "stroke": "#6b6b6b", "sw": .8})
            if i in sel:
                items.append(_lines_in(p, rng.uniform(0, math.pi), 0.012, rng, C_ZEM, 1.1))
        legend += [{"color": C_FERRIT, "label": "Ferrit (α)" if de else "ferrite (α)"},
                   {"color": C_PERLIT, "label": "Perlit (α + Fe₃C-Lamellen)" if de else "pearlite (α + Fe₃C lamellae)"}]
    elif kind in ("martensit", "angelassen"):
        for p in polys:
            items.append({"t": "poly", "p": p, "fill": C_MART, "stroke": "#4b5563", "sw": 1.0})
            for a in rng.uniform(0, math.pi, 2):
                items.append(_lines_in(p, a, 0.02, rng, "#56606e", 0.9, 0.8))
        legend.append({"color": C_MART, "label": ("Martensit (Latten, Pakete)" if kind == "martensit" else
                                                  "angelassener Martensit") if de else
                       ("martensite (laths, packets)" if kind == "martensit" else "tempered martensite")})
        if kind == "angelassen":
            stage = o.get("stage", 1)
            num, r = {1: (12, .003), 2: (10, .004), 3: (8, .006), 4: (5, .011)}.get(stage, (8, .006))
            for p in polys:
                items += _dots_in(p, num, r, rng, C_CARB, elong=(0.02 if stage <= 2 else 0.0))
            legend.append({"color": C_CARB, "label": o.get("carb_label", "Carbide" if de else "carbides")})
    elif kind == "austenit":
        for p in polys:
            items.append({"t": "poly", "p": p, "fill": C_AUST, "stroke": "#6b6b6b", "sw": .8})
            if rng.random() < 0.45:
                a = rng.uniform(0, math.pi)
                c = _centroid(p)
                d = np.array([math.cos(a), math.sin(a)]) * 0.25
                nrm = np.array([-d[1], d[0]]) / 0.25 * 0.012
                band = [(c - d + nrm), (c + d + nrm), (c + d - nrm), (c - d - nrm)]
                items.append({"t": "clip", "poly": p, "items": [{"t": "poly", "p": [b.round(4).tolist() for b in band],
                                                                  "fill": "#d6e0ee", "stroke": "#8a94a6", "sw": .6}]})
        legend.append({"color": C_AUST, "label": o.get("label") or ("Austenit (γ) mit Glühzwillingen" if de else
                                                                     "austenite (γ) with annealing twins")})
        if o.get("gb_carb"):
            for p in polys:
                for v in p:
                    if rng.random() < 0.6:
                        items.append({"t": "circle", "c": v, "r": .006, "fill": C_CARB})
            legend.append({"color": C_CARB, "label": "Cr₂₃C₆ an den Korngrenzen" if de else "Cr₂₃C₆ on grain boundaries"})
    elif kind in ("ferrit", "fcc", "hcp", "bcc"):
        fill = o.get("fill", C_FERRIT)
        for p in polys:
            items.append({"t": "poly", "p": p, "fill": fill, "stroke": "#6b6b6b", "sw": .8})
            if kind == "fcc" and o.get("twins", True) and rng.random() < 0.35:
                items.append(_lines_in(p, rng.uniform(0, math.pi), 0.06, rng, "#9aa3b0", .7))
        legend.append({"color": fill, "label": o.get("label", "")})
    elif kind in ("gjl", "gjs"):
        mat = o.get("matrix", "perlit")
        for p in polys:
            items.append({"t": "poly", "p": p, "fill": C_PERLIT if mat == "perlit" else C_FERRIT, "stroke": "#6b6b6b", "sw": .6})
            if mat == "perlit":
                items.append(_lines_in(p, rng.uniform(0, math.pi), 0.014, rng, C_ZEM, .8, .7))
        if kind == "gjl":
            for _ in range(int(o.get("n_g", 34))):
                c = rng.uniform(0, 1, 2)
                a = rng.uniform(0, math.pi)
                L = rng.uniform(0.08, 0.22)
                pts = [c + np.array([math.cos(a), math.sin(a)]) * L * s + np.array([-math.sin(a), math.cos(a)]) *
                       0.03 * math.sin(3 * s) for s in np.linspace(-.5, .5, 7)]
                items.append({"t": "pline", "p": [q.round(4).tolist() for q in pts], "stroke": "#202020", "sw": 2.4})
            legend.append({"color": "#202020", "label": "Lamellengraphit" if de else "flake graphite"})
        else:
            for _ in range(int(o.get("n_g", 16))):
                c = rng.uniform(0.05, 0.95, 2)
                r = rng.uniform(0.022, 0.04)
                if mat == "perlit":
                    items.append({"t": "circle", "c": c.round(4).tolist(), "r": round(r * 1.7, 4), "fill": C_FERRIT})
                items.append({"t": "circle", "c": c.round(4).tolist(), "r": round(r, 4), "fill": "#202020"})
            legend.append({"color": "#202020", "label": "Kugelgraphit" if de else "spheroidal graphite"})
        legend.insert(0, {"color": C_PERLIT if mat == "perlit" else C_FERRIT,
                          "label": ("perlitische Matrix" if mat == "perlit" else "ferritische Matrix") if de else
                          ("pearlitic matrix" if mat == "perlit" else "ferritic matrix")})
    elif kind == "al":
        st = o.get("state", "ss")
        fill = o.get("fill", C_AL)
        for p in polys:
            items.append({"t": "poly", "p": p, "fill": fill, "stroke": "#6b6b6b", "sw": .8})
        size = {"gp": (34, .0022, 0.0), "peak": (24, .003, .016), "over": (10, .006, 0.0), "eq": (6, .009, 0.0),
                "ss": (0, 0, 0), "disp": (8, .004, 0.0)}.get(st, (0, 0, 0))
        margin = {"peak": .02, "over": .03, "eq": .03}.get(st, 0.0)
        if size[0]:
            for p in polys:
                items += _dots_in(p, size[0], size[1], rng, o.get("pcol", C_PREC), margin=margin, elong=size[2])
                if st in ("over", "eq", "peak"):
                    for v in p:
                        if rng.random() < 0.5:
                            items.append({"t": "circle", "c": v, "r": size[1] * 1.6, "fill": o.get("pcol", C_PREC)})
            legend.append({"color": o.get("pcol", C_PREC), "label": o.get("plabel", "Ausscheidungen" if de else "precipitates")})
        if o.get("cold"):
            for p in polys:
                c = _centroid(p)
                for _ in range(3):
                    q = c + rng.normal(0, .02, 2)
                    pts = [q + rng.normal(0, .012, 2) for _ in range(5)]
                    items.append({"t": "pline", "p": [z.round(4).tolist() for z in pts], "stroke": "#5f6b7a", "sw": .6, "op": .8})
            legend.append({"color": "#5f6b7a", "label": "Versetzungen (kaltverfestigt)" if de else "dislocations (work hardened)"})
        legend.insert(0, {"color": fill, "label": o.get("label", "Mischkristall" if de else "solid solution")})
    elif kind == "zweiphasig":
        fb = o.get("f_b", 0.2)
        items.append({"t": "poly", "p": [[0, 0], [1, 0], [1, 1], [0, 1]], "fill": o.get("bcol", C_BETA), "stroke": "none"})
        items += _grain_items([_shrink(p, math.sqrt(max(1 - fb, 0.04))) for p in polys], o.get("acol", C_FERRIT))
        legend += [{"color": o.get("acol", C_FERRIT), "label": o.get("alabel", "α")},
                   {"color": o.get("bcol", C_BETA), "label": o.get("blabel", "β")}]
    else:
        raise StructError(f"Skizze {kind} unbekannt")
    if o.get("gb_dots"):
        for p in polys:
            for v in p:
                if rng.random() < o.get("gb_frac", .5):
                    items.append({"t": "circle", "c": v, "r": o.get("gb_r", .007), "fill": o.get("gb_col", C_PREC)})
        legend.append({"color": o.get("gb_col", C_PREC), "label": o.get("gb_label", "")})
    if o.get("needles"):
        for p in polys:
            for k in range(len(p)):
                if rng.random() < .35:
                    a, b = np.asarray(p[k]), np.asarray(p[(k + 1) % len(p)])
                    c = (a + b) / 2
                    d = (b - a) / max(np.linalg.norm(b - a), 1e-9)
                    nrm = np.array([-d[1], d[0]])
                    q = c + nrm * rng.uniform(-.02, .02)
                    items.append({"t": "line", "p": [(q - d * .04).round(4).tolist(), (q + d * .04).round(4).tolist()],
                                  "stroke": o.get("needle_col", "#3d4f6b"), "sw": 1.6})
        legend.append({"color": o.get("needle_col", "#3d4f6b"), "label": o.get("needle_label", "")})
    return {"items": items, "legend": legend}


def sk_polymer(xc: float, rng, de: bool, oriented: bool = False, crosslinked: bool = False, melt: bool = False) -> dict:
    """Teilkristallines Polymer im nm-Massstab: kristalline Lamellen (gefaltete, gestreckte Kettenstücke) und amorphe
    Zwischenschichten mit Verbindungsmolekülen; amorph bzw. Schmelze als Knäuel. Schematisch."""
    items, legend = [], []
    items.append({"t": "poly", "p": [[0, 0], [1, 0], [1, 1], [0, 1]], "fill": "#f6f3ec", "stroke": "none"})
    if xc <= 0.01 or melt:
        for _ in range(14):
            q = rng.uniform(0, 1, 2)
            pts = [q]
            d = rng.normal(0, 1, 2)
            for _ in range(60):
                d = d + rng.normal(0, .9, 2)
                d /= max(np.linalg.norm(d), 1e-9)
                q = np.clip(q + d * 0.02 * (np.array([1.8, .4]) if oriented else 1), 0, 1)
                pts.append(q)
            items.append({"t": "pline", "p": [p.round(4).tolist() for p in pts], "stroke": "#5b7db1", "sw": 1.0, "op": .85})
        if crosslinked:
            for _ in range(18):
                q = rng.uniform(.05, .95, 2)
                items.append({"t": "circle", "c": q.round(4).tolist(), "r": .009, "fill": "#d1495b"})
            legend.append({"color": "#d1495b", "label": "Vernetzungsstelle" if de else "cross-link"})
        legend.insert(0, {"color": "#5b7db1", "label": ("Schmelze (Knäuel)" if melt else "amorphe Knäuel") if de else
                          ("melt (coils)" if melt else "amorphous coils")})
        return {"items": items, "legend": legend, "scale": {"len": 0.25, "label": "10 nm"}}
    period = 0.25
    Lc = period * min(max(xc, 0.05), 0.9)
    y = 0.03
    while y < 1:
        band = [[0, y], [1, y], [1, y + Lc], [0, y + Lc]]
        items.append({"t": "poly", "p": band, "fill": "#dfe8d6", "stroke": "#7a9a6a", "sw": .6})
        x = 0.01
        while x < 1:
            items.append({"t": "line", "p": [[round(x, 4), round(y, 4)], [round(x, 4), round(y + Lc, 4)]], "stroke": "#4f7a3f", "sw": .8})
            if rng.random() < 0.5 and x + 0.012 < 1:
                items.append({"t": "pline", "p": [[round(x, 4), round(y + Lc, 4)], [round(x + .006, 4), round(y + Lc + .012, 4)],
                                                  [round(x + .012, 4), round(y + Lc, 4)]], "stroke": "#4f7a3f", "sw": .8})
            x += 0.012
        y0 = y + Lc
        for _ in range(5):
            x0 = rng.uniform(0, 1)
            pts = [np.array([x0, y0])]
            q = pts[0]
            while q[1] < y0 + (period - Lc) - 0.005:
                q = q + np.array([rng.normal(0, .015), abs(rng.normal(.01, .006))])
                pts.append(np.clip(q, 0, 1))
            items.append({"t": "pline", "p": [p.round(4).tolist() for p in pts], "stroke": "#b0703c", "sw": .9})
        y += period
    legend += [{"color": "#dfe8d6", "label": f"kristalline Lamelle (xc ≈ {xc * 100:.0f} %)" if de else
                f"crystalline lamella (xc ≈ {xc * 100:.0f} %)"},
               {"color": "#b0703c", "label": "amorphe Schicht, Verbindungsmoleküle" if de else "amorphous layer, tie molecules"}]
    return {"items": items, "legend": legend, "scale": {"len": 0.2, "label": "10 nm"}}


def sk_composite(phi: float, arr: str, rng, de: bool, fcol: str, mcol: str, flabel: str, mlabel: str) -> dict:
    items = [{"t": "poly", "p": [[0, 0], [1, 0], [1, 1], [0, 1]], "fill": mcol, "stroke": "none"}]
    if arr == "ud":
        r = 0.028
        pts = []
        tries = 0
        target = int(phi / (math.pi * r * r))
        if phi > 0.45:
            dx = 2 * r * 1.02 * math.sqrt(0.9069 / phi) if phi < 0.9 else 2 * r
            row = 0
            yv = r
            while yv < 1 + r:
                xv = r + (row % 2) * dx / 2
                while xv < 1 + r:
                    pts.append(np.array([xv, yv]) + rng.normal(0, r * 0.08, 2))
                    xv += dx
                yv += dx * 0.866
                row += 1
        else:
            while len(pts) < target and tries < 30000:
                tries += 1
                q = rng.uniform(0, 1, 2)
                if all(np.linalg.norm(q - p) > 2.05 * r for p in pts):
                    pts.append(q)
        items += [{"t": "circle", "c": p.round(4).tolist(), "r": r, "fill": fcol, "stroke": "#333", "sw": .4} for p in pts]
        note = "Querschnitt senkrecht zur Faser" if de else "cross-section normal to the fibres"
    elif arr == "kurz":
        n = int(phi * 260)
        for _ in range(n):
            c = rng.uniform(0, 1, 2)
            a = rng.normal(0, 0.5)
            d = np.array([math.cos(a), math.sin(a)]) * rng.uniform(.06, .12)
            items.append({"t": "line", "p": [(c - d).round(4).tolist(), (c + d).round(4).tolist()], "stroke": fcol, "sw": 3.2})
        note = "Kurzfasern, vorwiegend in Fliessrichtung (x)" if de else "short fibres, mostly along the flow (x)"
    else:
        w = 1 / 6
        for i in range(6):
            for j in range(6):
                over = (i + j) % 2 == 0
                x0, y0 = i * w, j * w
                items.append({"t": "poly", "p": [[x0 + .01, y0 + .01], [x0 + w - .01, y0 + .01], [x0 + w - .01, y0 + w - .01], [x0 + .01, y0 + w - .01]],
                              "fill": fcol if over else hex_mix(fcol, "#ffffff", .35), "stroke": "#555", "sw": .5})
                for k in range(1, 6):
                    if over:
                        items.append({"t": "line", "p": [[x0 + .01, y0 + k * w / 6], [x0 + w - .01, y0 + k * w / 6]], "stroke": "#666", "sw": .4})
                    else:
                        items.append({"t": "line", "p": [[x0 + k * w / 6, y0 + .01], [x0 + k * w / 6, y0 + w - .01]], "stroke": "#666", "sw": .4})
        note = "Gewebe (Leinwandbindung), Draufsicht" if de else "woven fabric (plain weave), top view"
    return {"items": items, "legend": [{"color": fcol, "label": flabel}, {"color": mcol, "label": mlabel}], "note": note,
            "scale": {"len": 0.2, "label": "20 µm" if arr != "gewebe" else "2 mm"}}


def hex_mix(h: str, t: str, w: float) -> str:
    a = [int(h[k:k + 2], 16) for k in (1, 3, 5)]
    b = [int(t[k:k + 2], 16) for k in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * w):02x}" for x, y in zip(a, b))


CHAR_COL = "#2b2522"                       # Pyrolysekohle (Farbe der Skizze, schematisch)


def _wall_label(stage: int, de: bool) -> str:
    """Legendentext der cellulosehaltigen Wand bzw. Faser je Erwärmungsstufe (siehe _cellulose_stage)."""
    return [("mit gebundenem Wasser", "with bound water"), ("getrocknet", "dried"),
            ("Hemicellulose zersetzt sich, gebräunt", "hemicellulose decomposing, browned"),
            ("Cellulose zersetzt sich, verkohlt", "cellulose decomposing, charring"),
            ("Pyrolysekohle", "pyrolysis char")][stage][0 if de else 1]


def sk_wood(art: str, mfw: float, rng, de: bool, char: float = 0.0, stage: int = 0) -> dict:
    """Holzquerschnitt; char ∈ [0, 1] färbt die Zellwände zur Kohle hin (gleiche Geometrie für jedes char)."""
    char = float(min(max(char, 0.0), 1.0))
    wall_c, edge_c = hex_mix("#b98b52", CHAR_COL, char), hex_mix("#8a6234", "#111111", char)
    items = [{"t": "poly", "p": [[0, 0], [1, 0], [1, 1], [0, 1]], "fill": "#f4ead8", "stroke": "none"}]
    cols, rows = 11, 14
    shrink = 1 - (0.06 if stage >= 1 else 0) - 0.2 * char        # Wand dünner: Trocknen, dann Masseverlust (schematisch)
    for j in range(rows):
        late = (j % 7) >= 5
        for i in range(cols):
            w, h = 1 / cols, 1 / rows * (0.7 if late else 1.0)
            x0 = i * w + (j % 2) * 0.01
            y0 = j / rows
            wall = (.018 if late else .007) * shrink
            items.append({"t": "poly", "p": [[x0, y0], [x0 + w, y0], [x0 + w, y0 + h], [x0, y0 + h]], "fill": wall_c, "stroke": edge_c, "sw": .4})
            items.append({"t": "poly", "p": [[x0 + wall, y0 + wall], [x0 + w - wall, y0 + wall], [x0 + w - wall, y0 + h - wall], [x0 + wall, y0 + h - wall]],
                          "fill": "#f7efe2", "stroke": "none"})
    if art == "laubholz":
        for _ in range(7):
            c = rng.uniform(.08, .92, 2)
            items.append({"t": "circle", "c": c.round(4).tolist(), "r": .045, "fill": "#f7efe2", "stroke": edge_c, "sw": 1.2})
    if char > 0.55:                                     # Schwindrisse der Kohle (eigener Zufall: Lage unabhängig von T)
        rc = np.random.default_rng(7)
        for _ in range(int(round((char - 0.55) * 14))):
            c = rc.uniform(.1, .9, 2)
            a = rc.uniform(0, math.pi)
            d = np.array([math.cos(a), math.sin(a)]) * rc.uniform(.06, .14)
            items.append({"t": "pline", "p": [(c - d).round(4).tolist(), (c + d * 0.3 + [0.01, -0.01]).round(4).tolist(), (c + d).round(4).tolist()],
                          "stroke": "#f7efe2", "sw": 1.6})
    wl = "Zellwand (Cellulose-Mikrofibrillen in Hemicellulose und Lignin)" if de else "cell wall (cellulose microfibrils in hemicellulose and lignin)"
    leg = [{"color": wall_c, "label": wl + (f", {_wall_label(stage, de)}" if stage else "") if stage < 4 else
            (("Zellwand: " if de else "cell wall: ") + _wall_label(stage, de))},
           {"color": "#f7efe2", "label": ("Zelllumen" + (", Gefässe" if art == "laubholz" else "")) if de else
            ("cell lumen" + (", vessels" if art == "laubholz" else ""))}]
    return {"items": items, "legend": leg, "scale": {"len": 0.2, "label": "50 µm"},
            "note": (f"Querschnitt; Früh- und Spätholz; Mikrofibrillenwinkel der S2-Schicht ≈ {mfw:g}°" if de else
                     f"cross-section; early- and latewood; S2 microfibril angle ≈ {mfw:g}°")}


def sk_paper(filler: float, rng, de: bool, char: float = 0.0, stage: int = 0) -> dict:
    """Fasernetzwerk; char ∈ [0, 1] färbt und verschmälert die Fasern, der mineralische Füllstoff bleibt."""
    char = float(min(max(char, 0.0), 1.0))
    fcol = hex_mix("#c8b48a", CHAR_COL, char)
    items = [{"t": "poly", "p": [[0, 0], [1, 0], [1, 1], [0, 1]], "fill": "#fbfaf6", "stroke": "none"}]
    sw = 5.5 * (1 - (0.05 if stage >= 1 else 0) - 0.35 * char)
    for _ in range(45):
        c = rng.uniform(-.1, 1.1, 2)
        a = rng.normal(0, .45)
        d = np.array([math.cos(a), math.sin(a)])
        pts = [c + d * s + np.array([-d[1], d[0]]) * .02 * math.sin(4 * s) for s in np.linspace(-.35, .35, 9)]
        items.append({"t": "pline", "p": [p.round(4).tolist() for p in pts], "stroke": fcol, "sw": round(sw, 3), "op": .75 + 0.2 * char})
    for _ in range(int(filler * 500)):
        items.append({"t": "circle", "c": rng.uniform(0, 1, 2).round(4).tolist(), "r": .004, "fill": "#9aa5b1"})
    fl = "Zellstofffasern (vorwiegend in Laufrichtung x)" if de else "pulp fibres (mostly along machine direction x)"
    leg = [{"color": fcol, "label": fl + (f", {_wall_label(stage, de)}" if stage else "")}]
    if filler:
        leg.append({"color": "#9aa5b1", "label": "Füllstoff (CaCO₃)" if de else "filler (CaCO₃)"})
    return {"items": items, "legend": leg, "scale": {"len": 0.2, "label": "200 µm"}}


def sk_concrete(f_agg: float, rng, de: bool, T: float) -> dict:
    items = [{"t": "poly", "p": [[0, 0], [1, 0], [1, 1], [0, 1]], "fill": "#b9b4a8", "stroke": "none"}]
    cs = []
    tries = 0
    area = 0.0
    while area < f_agg * 0.85 and tries < 6000:
        tries += 1
        r = rng.uniform(.03, .11)
        c = rng.uniform(0, 1, 2)
        if all(np.linalg.norm(c - q) > (r + rq) * 1.05 for q, rq in cs):
            cs.append((c, r))
            area += math.pi * r * r
    for c, r in cs:
        n = int(rng.integers(6, 10))
        pts = [c + r * rng.uniform(.75, 1.0) * np.array([math.cos(t), math.sin(t)]) for t in np.sort(rng.uniform(0, 2 * math.pi, n))]
        items.append({"t": "poly", "p": [p.round(4).tolist() for p in pts], "fill": "#e3d6b8", "stroke": "#8f8468", "sw": .6})
    for _ in range(25):
        items.append({"t": "circle", "c": rng.uniform(0, 1, 2).round(4).tolist(), "r": float(rng.uniform(.004, .012)), "fill": "#f4f2ee", "stroke": "#8c877c", "sw": .4})
    if T < 500:
        for _ in range(30):
            c = rng.uniform(0, 1, 2)
            pts = [c + .008 * np.array([math.cos(t), math.sin(t)]) for t in np.linspace(0, 2 * math.pi, 7)[:-1]]
            items.append({"t": "poly", "p": [p.round(4).tolist() for p in pts], "fill": "#f7f4ea", "stroke": "#a59f8d", "sw": .4})
    leg = [{"color": "#e3d6b8", "label": "Gesteinskörnung (Quarz)" if de else "aggregate (quartz)"},
           {"color": "#b9b4a8", "label": "Zementstein (C-S-H-Gel)" if de else "cement paste (C-S-H gel)"},
           {"color": "#f4f2ee", "label": "Poren" if de else "pores"}]
    if T < 500:
        leg.append({"color": "#f7f4ea", "label": "Portlandit Ca(OH)₂" if de else "portlandite Ca(OH)₂"})
    return {"items": items, "legend": leg, "scale": {"len": 0.2, "label": "5 mm"}}


def sk_glassceramic(f: float, rng, de: bool) -> dict:
    items = [{"t": "poly", "p": [[0, 0], [1, 0], [1, 1], [0, 1]], "fill": "#cfe0e8", "stroke": "none"}]
    polys = _tess(9, rng)
    items += _grain_items([_shrink(p, math.sqrt(max(f, 0.05))) for p in polys], "#e9e2cf", "#9b8f6a", .6)
    return {"items": items, "legend": [{"color": "#e9e2cf", "label": "Kristalle (β-Spodumen-Mischkristall)" if de else "crystals (β-spodumene solid solution)"},
                                       {"color": "#cfe0e8", "label": "Restglas" if de else "residual glass"}],
            "scale": {"len": 0.2, "label": "1 µm"}}


# ============================================================================ Metalle: Regeln je Legierungsgruppe
# Schmelzbereiche und Lösungsgrenzen: Richtwerte für die Leitlegierung der Gruppe (ASM Handbook Vol. 2, 1990;
# Polmear et al. 2017). Auslagerungsfolgen nach Polmear et al. (2017).
AL = {
    "al-1xxx": {"sol": 646, "liq": 657, "teilchen": "al13fe4", "lbl": ("Al₁₃Fe₄ (Al₃Fe)", "Al₁₃Fe₄ (Al₃Fe)")},
    "al-3xxx": {"sol": 643, "liq": 654, "teilchen": "al6mn", "lbl": ("Al₆Mn-Dispersoide", "Al₆Mn dispersoids")},
    "al-5xxx": {"sol": 607, "liq": 649},
    "al-2xxx": {"sol": 502, "liq": 638, "solvus": 495, "gp": 150, "peak": (190, 12),
                "seq": {"gp": ("GPB-Zonen (Cu-Mg-Cluster)", "GPB zones (Cu–Mg clusters)", None),
                        "peak": ("S″/S′-Al₂CuMg", "S″/S′ Al₂CuMg", "al2cumg-s"),
                        "over": ("S-Al₂CuMg", "S Al₂CuMg", "al2cumg-s"), "eq": ("S-Al₂CuMg und θ-Al₂Cu", "S Al₂CuMg and θ Al₂Cu", "al2cu-theta")},
                "seq_cu": {"gp": ("GP-Zonen (Cu-Scheiben)", "GP zones (Cu discs)", None),
                           "peak": ("θ″/θ′-Al₂Cu", "θ″/θ′ Al₂Cu", "al2cu-thetap"),
                           "over": ("θ′-Al₂Cu", "θ′ Al₂Cu", "al2cu-thetap"), "eq": ("θ-Al₂Cu", "θ Al₂Cu", "al2cu-theta")}},
    "al-6xxx": {"sol": 582, "liq": 652, "solvus": 530, "gp": 100, "peak": (175, 8),
                "seq": {"gp": ("Mg-Si-Cluster, GP-Zonen", "Mg–Si clusters, GP zones", None),
                        "peak": ("β″ (Mg₅Si₆)", "β″ (Mg₅Si₆)", "mg5si6-bpp"),
                        "over": ("β′ / β-Mg₂Si", "β′ / β Mg₂Si", "mg2si"), "eq": ("β-Mg₂Si", "β Mg₂Si", "mg2si")}},
    "al-7xxx": {"sol": 477, "liq": 635, "solvus": 465, "gp": 120, "peak": (120, 24),
                "seq": {"gp": ("GP-Zonen (Zn-Mg)", "GP zones (Zn–Mg)", None),
                        "peak": ("η′ (MgZn₂, metastabil)", "η′ (MgZn₂, metastable)", "mgzn2-etap"),
                        "over": ("η-MgZn₂", "η MgZn₂", "mgzn2"), "eq": ("η-MgZn₂", "η MgZn₂", "mgzn2")}},
}
Q_AGE = 130e3            # J/mol, Aktivierungsenergie der Diffusion von Cu, Mg, Si, Zn in Al (Polmear 2017: 115–140)

MG_AL_SOLVUS = [(25, 0.8), (100, 1.0), (200, 2.3), (300, 5.0), (400, 9.6), (437, 12.7)]   # Gew.-% Al in Mg
TI64_BETA = [(20, 0.08), (600, 0.1), (800, 0.18), (900, 0.38), (950, 0.6), (980, 0.85), (995, 1.0)]  # Lütjering 2007


def _interp(tab, x):
    xs, ys = zip(*tab)
    return float(np.interp(x, xs, ys))


def age_state(series: str, hist: list[tuple[float, float]], de: bool, cu_only: bool = False) -> dict:
    """Ausscheidungszustand einer aushärtbaren Al-Legierung nach Auslagerungsschritten [(T °C, t h)] seit dem
    Abschrecken: äquivalente Zeit bei der Spitzentemperatur über Arrhenius (Q = 130 kJ/mol); unter der GP-Grenze
    entstehen nur GP-Zonen."""
    a = AL[series]
    Tp, tp = a["peak"]
    teq = 0.0
    gp = False
    for T, t in hist:
        if T <= a["gp"] - 20 and t > 0.5:
            gp = True
            continue
        teq += t * math.exp(-Q_AGE / R_GAS * (1 / (T + T0) - 1 / (Tp + T0)))
    seq = a["seq_cu"] if cu_only and "seq_cu" in a else a["seq"]
    r = teq / tp
    if teq <= 0:
        key = "gp" if gp else "ss"
    elif r < 0.3:
        key = "gp" if r < 0.05 else "peak"
        stage = ("unteraltert" if de else "under-aged")
    elif r <= 3:
        key = "peak"
    elif r <= 50:
        key = "over"
    else:
        key = "eq"
    label = {"ss": ("übersättigter Mischkristall", "supersaturated solid solution"),
             "gp": seq["gp"][:2], "peak": seq["peak"][:2], "over": seq["over"][:2], "eq": seq["eq"][:2]}[key]
    zust = {"ss": ("lösungsgeglüht und abgeschreckt", "solution treated and quenched"),
            "gp": ("kaltausgelagert", "naturally aged"), "peak": ("warmausgelagert, nahe Höchsthärte", "artificially aged, near peak"),
            "over": ("überaltert", "over-aged"), "eq": ("stark überaltert, Gleichgewichtsphase", "heavily over-aged, equilibrium phase")}[key]
    if key == "peak" and r < 0.3:
        zust = ("unteraltert", "under-aged")
    return {"key": key, "teq": teq, "ratio": r, "phase": label[0] if de else label[1],
            "cell": seq[key][2] if key in seq else None, "zustand": zust[0] if de else zust[1]}


def temper_hist(zustand: str, series: str) -> list | None:
    """Wärmebehandlungsfolge aus dem Werkstoffzustand (EN 515): T3/T4 kaltausgelagert, T6 warmausgelagert,
    T7 überaltert, O weichgeglüht (langsam abgekühlt), sonst None."""
    z = (zustand or "").upper()
    if series not in AL or "peak" not in AL[series]:
        return None
    Tp, tp = AL[series]["peak"]
    if z.startswith(("T3", "T4")):
        return [(20, 96.0)]
    if z.startswith(("T6", "T8")):
        return [(20, 24.0), (Tp, tp)]
    if z.startswith("T7"):
        return [(Tp, tp), (Tp + 40, 10.0)]
    if z.startswith("O"):
        return [(350, 2.0), (250, 10.0)]
    return None


def steel_stage(Tt: float, th: float) -> tuple[int, float]:
    """Anlassstufe nach Hollomon–Jaffe: P = T_K·(20 + lg t_h); gleichwertige Anlasstemperatur für 1 h."""
    P = (Tt + T0) * (20 + math.log10(max(th, 1e-3)))
    T1 = P / 20 - T0
    if T1 < 80:
        return 0, T1
    if T1 < 200:
        return 1, T1
    if T1 < 300:
        return 2, T1
    if T1 < 500:
        return 3, T1
    return 4, T1


STAGE_TXT = {0: ("Martensit, C zwangsgelöst", "martensite, carbon in forced solution"),
             1: ("1. Anlassstufe: ε-Carbid scheidet sich aus, Martensit verarmt an C (≈ 0,25 %)",
                 "1st tempering stage: ε-carbide precipitates, martensite loses carbon (≈ 0.25 %)"),
             2: ("2. Stufe: Restaustenit zerfällt, ε-Carbid geht in Zementit über",
                 "2nd stage: retained austenite decomposes, ε-carbide turns into cementite"),
             3: ("3. Stufe: Zementit in kubisch raumzentriertem Ferrit, Martensit entspannt",
                 "3rd stage: cementite in body-centred cubic ferrite, martensite relaxed"),
             4: ("4. Stufe: Zementit eingeformt und vergröbert, Erholung und Rekristallisation des Ferrits",
                 "4th stage: cementite spheroidised and coarsened, ferrite recovers and recrystallises")}


def _top_solutes(zus: dict, n: int = 4) -> list[dict]:
    ok = set(GT.solute_list())
    rows = sorted(((el, c) for el, c in (zus or {}).items() if el in ok and c > 0), key=lambda x: -x[1])[:n]
    return [{"el": el, "c": float(c), "einheit": "wt"} for el, c in rows]


def _lattice_panel(host: str, sols: list[dict], T: float, de: bool, rng_seed: int, n: int, title: str,
                   form: str | None = None, cold: bool = False, limits: dict | None = None, note: str = "") -> dict:
    req = {"host": host, "T": T, "n": n, "seed": rng_seed, "solutes": sols,
           "limits": limits if limits is not None else {s["el"]: s["c"] for s in sols},
           "fx": {"disl": bool(cold), "vac": True, "vib": True, "distort": True, "precip": True}}
    if form:
        req["form"] = form
    res = GT.build(req, "de" if de else "en")
    return {"kind": "scene", "sub": "lattice", "id": "gitter", "title": title, "scene": res,
            "caption": note, "refs": res["refs"]}


def _cell_panel(pid: str, de: bool, title: str | None = None, reps=(1, 1, 1), note: str = "", pid_tag: str | None = None) -> dict:
    ph = phase_any(pid)
    sc = cell_scene(ph, reps, de)
    t = title or (("Elementarzelle " if de else "Unit cell ") + pname(ph, de))
    return {"kind": "scene", "sub": "cell", "id": pid_tag or ("zelle:" + pid), "title": t, "scene": sc,
            "phase": {"id": pid, "name": pname(ph, de), "formula": ph.get("formula"), "system": ph.get("system"),
                      "spacegroup": ph.get("spacegroup"), "cell": ph.get("cell"), "cod": ph.get("cod"),
                      "art": ph["_art"], "T_messung": ph.get("T_messung"), "unchecked": bool(ph.get("nicht_geprueft"))},
            "caption": note, "q": ph["_q"]}


def _metal(mid: str, r: dict, T: float, de: bool, rng, hist_override=None, n: int = 5) -> dict:
    """Ansichten eines Metalls bei T. hist_override: Wärmebehandlung für temper()."""
    host = r["basis"]
    rule = r.get("regel", "rein")
    zus = dict(r.get("zus") or {})
    zst = r.get("zustand", "")
    cold = bool(r.get("kaltverformt")) or zst.upper().startswith("H")
    panels, st, notes, refs, q = [], [], [], [], [r.get("q")] if r.get("q") else []
    e = GT._data()["elemente"].get(host, {})
    Tm = e.get("Tm", 1500)
    trans = []
    lat_title = "Gitter bei T" if de else "Lattice at T"
    sk = None
    seed = int(rng.integers(1, 10 ** 6))

    def L(a, b):
        return a if de else b

    # ---------------------------------------------------------------- Stahl
    if rule in ("stahl", "gusseisen"):
        from . import steel as STL
        comp = {k: zus.get(k, 0.0) for k in ("C", "Si", "Mn", "Cr", "Mo", "V", "Ni", "Cu", "B")}
        rep = STL.composition_report({**comp, "C": min(comp["C"], 0.9)})
        Ac1, Ac3, Ms = rep["Ac1"], rep["Ac3"], rep["Ms"]
        refs += ["andrews1965"]
        C = zus.get("C", 0.0)
        hist = hist_override if hist_override is not None else (
            {"kind": "qt", "Tt": r["anlassen"]["T"], "tt": r["anlassen"]["t_h"]} if r.get("anlassen") else
            {"kind": "normal"})
        if rule == "gusseisen":
            Ac1 = 760.0
            notes.append(L("Eutektoide Temperatur durch Si angehoben (≈ 760 °C, Richtwert).", "Eutectoid temperature raised by Si (≈ 760 °C, guide value)."))
            sol_e = 1150.0
            trans += [{"T": Ac1, "label": L("Matrix → Austenit", "matrix → austenite")}, {"T": sol_e, "label": L("eutektische Schmelze", "eutectic melt")},
                      {"T": 1200.0, "label": L("vollständig flüssig (≈)", "fully liquid (≈)")}]
            sols_m = [s for s in _top_solutes({k: v for k, v in zus.items() if k != "C"}, 3)]
            if T >= 1200:
                panels.append(_lattice_panel(host, [], T, de, seed, n, L("Schmelze", "Melt")))
                sk = sk_metal("schmelze", rng, de)
            elif T >= sol_e:
                panels.append(_lattice_panel(host, [{"el": "C", "c": 2.0, "einheit": "wt"}] + sols_m, min(T, 1140), de, seed, n,
                                             L("Austenit neben der Schmelze", "Austenite next to the melt"), form="γ-Fe"))
                sk = sk_metal("teilschmelze", rng, de, f_l=min(0.95, (T - sol_e) / 50), solid=L("Austenit", "austenite"))
            elif T >= Ac1:
                panels.append(_lattice_panel(host, [{"el": "C", "c": 0.8, "einheit": "wt"}] + sols_m, T, de, seed, n,
                                             L("Matrix: Austenit (γ)", "Matrix: austenite (γ)"), form="γ-Fe"))
                sk = sk_metal("gjl" if r.get("graphit") == "lamellen" else "gjs", rng, de, matrix="ferrit")
                sk["legend"][0]["label"] = L("austenitische Matrix", "austenitic matrix")
            else:
                cm = 0.77 if r.get("matrix") == "perlit" else 0.02
                panels.append(_lattice_panel(host, [{"el": "C", "c": cm, "einheit": "wt"}] + sols_m, T, de, seed, n,
                                             L("Matrix: " + ("Perlit (α + Fe₃C)" if cm > .1 else "Ferrit (α)"),
                                               "Matrix: " + ("pearlite (α + Fe₃C)" if cm > .1 else "ferrite (α)"))))
                sk = sk_metal("gjl" if r.get("graphit") == "lamellen" else "gjs", rng, de, matrix=r.get("matrix", "perlit"))
                if cm > .1:
                    panels.append(_cell_panel("fe3c", de, note=L("Zementitlamellen im Perlit der Matrix.", "Cementite lamellae in the pearlite of the matrix.")))
            if T < 1200:
                panels.append(_cell_panel("graphit", de, note=L("Graphit (" + ("Lamellen" if r.get("graphit") == "lamellen" else "Kugeln") + "); Schichten hexagonal, Abstand 3,35 Å.",
                                                                "Graphite (" + ("flakes" if r.get("graphit") == "lamellen" else "nodules") + "); hexagonal layers 3.35 Å apart.")))
            st.append(L(f"Gusseisen mit {('Lamellen' if r.get('graphit') == 'lamellen' else 'Kugel')}graphit ({C:g} % C) in "
                        f"{('perlitischer' if r.get('matrix') == 'perlit' else 'ferritischer')} Matrix.",
                        f"Cast iron with {('flake' if r.get('graphit') == 'lamellen' else 'spheroidal')} graphite ({C:g} % C) in a "
                        f"{('pearlitic' if r.get('matrix') == 'perlit' else 'ferritic')} matrix."))
            refs += ["callister", "porter"]
        else:
            sols = _top_solutes(zus)
            trans += [{"T": Ac1, "label": "Ac1"}, {"T": Ac3, "label": "Ac3"}]
            if hist["kind"] == "qt":
                trans.append({"T": hist["Tt"], "label": L("Anlasstemperatur", "tempering temperature")})
            # Phasen über das Fe-C-Diagramm (gitter), Martensit und Anlassstufen aus der Wärmebehandlung
            qt = hist["kind"] in ("qt", "quenched")
            if qt and T < Ac1:
                Tt, tt = (hist.get("Tt", 20), hist.get("tt", 0)) if hist["kind"] == "qt" else (20, 0)
                if T > Tt:
                    Tt, tt = T, 1.0
                stage, T1 = steel_stage(Tt, tt) if hist["kind"] == "qt" else (0, 20)
                c_mart = C if stage == 0 else (min(C, 0.25) if stage == 1 else (0.1 if stage == 2 else 0.0))
                if stage <= 2:
                    sc, mp = martensite_scene(c_mart, T, rng, de, n=4)
                    panels.append({"kind": "scene", "sub": "lattice", "id": "martensit",
                                   "title": L("Martensit (tetragonal raumzentriert)", "Martensite (body-centred tetragonal)"),
                                   "scene": sc, "caption": L(f"c/a = {mp['c_a']:.4f} bei {c_mart:.2f} % gelöstem C (Roberts 1953). C nur auf den Oktaederplätzen in z-Richtung; ein Teil bleibt leer.",
                                                             f"c/a = {mp['c_a']:.4f} at {c_mart:.2f} % dissolved C (Roberts 1953). C only on the octahedral sites along z; some stay empty."),
                                   "refs": ["roberts1953"]})
                    refs += ["roberts1953"]
                else:
                    panels.append(_lattice_panel(host, [s for s in sols if s["el"] != "C"] + [{"el": "C", "c": 0.005, "einheit": "wt"}], T, de, seed, n,
                                                 L("Ferrit (α), entspannt", "Ferrite (α), relaxed")))
                if stage == 1 or stage == 2:
                    panels.append(_cell_panel("eps-carbid", de, note=L("ε-Carbid (Fe₂,₄C), hexagonal; Kohlenstofflage teilbesetzt.", "ε-carbide (Fe₂.₄C), hexagonal; carbon site partly occupied.")))
                if stage >= 2:
                    panels.append(_cell_panel("fe3c", de))
                carb = {1: L("ε-Carbid, fein", "ε-carbide, fine"), 2: L("ε-Carbid und Zementit", "ε-carbide and cementite"),
                        3: L("Zementit, fein", "cementite, fine"), 4: L("Zementit, eingeformt", "cementite, spheroidised")}.get(stage, "")
                sk = sk_metal("martensit" if stage == 0 else "angelassen", rng, de, stage=stage, carb_label=carb)
                st.append(L(("Gehärtet und angelassen" if hist["kind"] == "qt" else "Gehärtet") + f": {STAGE_TXT[stage][0]}.",
                            ("Quenched and tempered" if hist["kind"] == "qt" else "Quenched") + f": {STAGE_TXT[stage][1]}."))
                if hist["kind"] == "qt":
                    st.append(L(f"Gleichwertige Anlasstemperatur für 1 h nach Hollomon–Jaffe: {T1:.0f} °C.",
                                f"Equivalent tempering temperature for 1 h (Hollomon–Jaffe): {T1:.0f} °C."))
                    refs += ["hollomonjaffe1945"]
                refs += ["krauss2015", "speich1972"]
            else:
                res = _lattice_panel(host, sols, T, de, seed, n, lat_title)
                panels.append(res)
                phs = res["scene"]["phase"]["phases"]
                labels = [p["label"] for p in phs]
                f_g = sum(p["frac"] for p in phs if p["label"] == "γ")
                f_l = sum(p["frac"] for p in phs if p.get("fluessig"))
                if f_l > 0.999:
                    sk = sk_metal("schmelze", rng, de)
                elif f_l > 0:
                    sk = sk_metal("teilschmelze", rng, de, f_l=f_l, fill=C_AUST, solid=L("Austenit/δ-Ferrit", "austenite/δ-ferrite"))
                elif f_g > 0.999:
                    sk = sk_metal("austenit", rng, de)
                elif f_g > 0:
                    sk = sk_metal("zweiphasig", rng, de, f_b=f_g, acol=C_FERRIT, bcol=C_AUST, alabel=L("Ferrit (α)", "ferrite (α)"),
                                  blabel=L("Austenit (γ)", "austenite (γ)"))
                else:
                    fp = min(1.0, C / 0.77)
                    sk = sk_metal("ferrit-perlit", rng, de, f_p=fp)
                    if C > 0.02:
                        panels.append(_cell_panel("fe3c", de, note=L("Zementit Fe₃C, Lamellen im Perlit.", "Cementite Fe₃C, lamellae in pearlite.")))
                st.append(L(f"Phasen bei {T:g} °C nach dem Fe–C-Diagramm: {', '.join(labels)}.",
                            f"Phases at {T:g} °C from the Fe–C diagram: {', '.join(labels)}."))
                if hist["kind"] == "qt" and T >= Ac1:
                    st.append(L("Über Ac1 wird das Anlassgefüge wieder austenitisiert.", "Above Ac1 the tempered structure turns back into austenite."))
            if C > 0.0 and rule == "stahl":
                st.append(L(f"Ac1 ≈ {Ac1:.0f} °C, Ac3 ≈ {Ac3:.0f} °C, Ms ≈ {Ms:.0f} °C (Andrews 1965).",
                            f"Ac1 ≈ {Ac1:.0f} °C, Ac3 ≈ {Ac3:.0f} °C, Ms ≈ {Ms:.0f} °C (Andrews 1965)."))
    # ---------------------------------------------------------------- nichtrostende Stähle
    elif rule in ("edelstahl-austenit", "edelstahl-ferrit"):
        aust = rule == "edelstahl-austenit"
        sol_, liq_ = (1400, 1450) if aust else (1425, 1510)
        trans += [{"T": 450, "label": L("Sensibilisierung ab", "sensitisation from")}, {"T": 850, "label": L("Sensibilisierung bis", "sensitisation to")},
                  {"T": sol_, "label": "Solidus"}, {"T": liq_, "label": "Liquidus"}]
        sols = _top_solutes(zus)
        if T >= liq_:
            panels.append(_lattice_panel(host, sols, T, de, seed, n, L("Schmelze", "Melt")))
            sk = sk_metal("schmelze", rng, de)
        else:
            form = "γ-Fe" if aust else "α-Fe"
            panels.append(_lattice_panel(host, sols, min(T, Tm - 1), de, seed, n,
                                         L("Austenit (γ), durch Ni stabilisiert" if aust else "Ferrit (α), durch Cr stabilisiert",
                                           "Austenite (γ), stabilised by Ni" if aust else "Ferrite (α), stabilised by Cr"), form=form, cold=cold))
            sens = 450 <= T <= 850 and zus.get("C", 0) >= 0.02
            if T >= sol_:
                sk = sk_metal("teilschmelze", rng, de, f_l=(T - sol_) / (liq_ - sol_), fill=C_AUST if aust else C_FERRIT)
            elif aust:
                sk = sk_metal("austenit", rng, de, gb_carb=sens)
            else:
                sk = sk_metal("ferrit", rng, de, label=L("Ferrit (α)", "ferrite (α)"), gb_dots=sens, gb_col=C_CARB,
                              gb_label=L("Cr₂₃C₆ an den Korngrenzen", "Cr₂₃C₆ on grain boundaries"))
            if sens:
                panels.append(_cell_panel("cr23c6", de, note=L("Chromcarbid scheidet sich zwischen 450 und 850 °C an den Korngrenzen aus (Sensibilisierung).",
                                                               "Chromium carbide precipitates on the grain boundaries between 450 and 850 °C (sensitisation).")))
                st.append(L("Im Sensibilisierungsbereich: Cr₂₃C₆ an den Korngrenzen, Cr-Verarmung daneben (interkristalline Korrosion).",
                            "In the sensitisation range: Cr₂₃C₆ on grain boundaries, Cr depletion next to them (intergranular corrosion)."))
            st.append(L(("Austenitischer" if aust else "Ferritischer") + " nichtrostender Stahl: " + ("γ bis Raumtemperatur stabil (Ni)." if aust else "α bis zur Schmelze (Cr schliesst das γ-Gebiet)."),
                        ("Austenitic" if aust else "Ferritic") + " stainless steel: " + ("γ stable down to room temperature (Ni)." if aust else "α up to melting (Cr closes the γ loop).")))
        refs += ["asm1990v1", "porter"]
    # ---------------------------------------------------------------- Aluminium
    elif rule.startswith("al-") and rule in AL:
        a = AL[rule]
        sols_all = _top_solutes(zus)
        trans += [{"T": a["sol"], "label": "Solidus"}, {"T": a["liq"], "label": "Liquidus"}]
        hist = hist_override if hist_override is not None else temper_hist(zst, rule)
        cu_only = rule == "al-2xxx" and zus.get("Mg", 0) < 1.0
        if "solvus" in a:
            trans.append({"T": a["solvus"], "label": L("Solvus (Lösungsglühen)", "solvus (solution treatment)")})
        if T >= a["liq"]:
            panels.append(_lattice_panel(host, sols_all, T, de, seed, n, L("Schmelze", "Melt")))
            sk = sk_metal("schmelze", rng, de)
        elif T >= a["sol"]:
            panels.append(_lattice_panel(host, sols_all, a["sol"] - 1, de, seed, n, L("Mischkristall neben der Schmelze", "Solid solution next to the melt")))
            sk = sk_metal("teilschmelze", rng, de, f_l=(T - a["sol"]) / (a["liq"] - a["sol"]), fill=C_AL)
        elif "solvus" in a:
            if T >= a["solvus"]:
                state = {"key": "ss", "phase": L("alles gelöst", "all dissolved"), "cell": None,
                         "zustand": L("lösungsgeglüht", "solution treated")}
            else:
                h = list(hist) if hist is not None else [(20, 96.0)]
                if T > 30:
                    h = h + [(T, 1.0)]
                state = age_state(rule, h, de, cu_only)
            key = state["key"]
            # in der Matrix gelöst: alles bei ss/gp, bei Ausscheidung nur ein Rest (schematisch 30 % der Legierungselemente)
            frac_sol = {"ss": 1.0, "gp": 1.0, "peak": 0.4, "over": 0.25, "eq": 0.15}[key]
            hard = ("Cu", "Mg", "Si", "Zn")
            sols = [{**s, "c": s["c"] * (frac_sol if s["el"] in hard else 1.0)} for s in sols_all]
            panels.append(_lattice_panel(host, sols, T, de, seed, n, L("Al-Mischkristall bei T", "Al solid solution at T"), cold=cold))
            if state.get("cell"):
                panels.append(_cell_panel(state["cell"], de, note=L(f"Ausscheidung: {state['phase']}.", f"Precipitate: {state['phase']}.")))
            sk = sk_metal("al", rng, de, state=key, plabel=state["phase"], cold=cold, gewalzt=cold)
            if hist_override is None:
                st.append(L(f"Zustand {zst or '–'} bei {T:g} °C: {state['zustand']}; {state['phase']}.",
                            f"Temper {zst or '–'} at {T:g} °C: {state['zustand']}; {state['phase']}."))
            else:
                st.append(L(f"Bei {T:g} °C: {state['zustand']}; {state['phase']}.", f"At {T:g} °C: {state['zustand']}; {state['phase']}."))
            if key in ("gp", "peak", "over", "eq") and state.get("teq"):
                st.append(L(f"Äquivalente Auslagerungszeit bei {a['peak'][0]} °C: {state['teq']:.3g} h (Höchsthärte ≈ {a['peak'][1]} h).",
                            f"Equivalent ageing time at {a['peak'][0]} °C: {state['teq']:.3g} h (peak ≈ {a['peak'][1]} h)."))
            refs += ["polmear2017"]
        else:
            panels.append(_lattice_panel(host, sols_all, T, de, seed, n, lat_title, cold=cold and T < 300))
            if a.get("teilchen"):
                panels.append(_cell_panel(a["teilchen"], de, note=L(a["lbl"][0] + ", grobe Teilchen bzw. Dispersoide.", a["lbl"][1] + ", coarse particles or dispersoids.")))
            sk = sk_metal("al", rng, de, state="disp" if a.get("teilchen") else "ss", plabel=(a.get("lbl") or ("", ""))[0 if de else 1],
                          cold=cold and T < 300, gewalzt=cold and T < 300)
            if rule == "al-5xxx":
                st.append(L("Mg bleibt im Mischkristall gelöst (Mischkristallhärtung); β-Al₃Mg₂ bildet sich erst nach langer Zeit bei 50–200 °C an den Korngrenzen (nicht gezeigt).",
                            "Mg stays dissolved (solid-solution strengthening); β-Al₃Mg₂ forms only after long exposure at 50–200 °C on grain boundaries (not shown)."))
            if cold:
                st.append(L(f"Zustand {zst}: kaltverfestigt; Erholung und Rekristallisation ab ≈ 250–350 °C.",
                            f"Temper {zst}: strain hardened; recovery and recrystallisation from ≈ 250–350 °C."))
                trans.append({"T": 300, "label": L("Rekristallisation (≈)", "recrystallisation (≈)")})
            refs += ["polmear2017"]
        refs += ["asm1990v2"]
    # ---------------------------------------------------------------- Kupfer
    elif rule in ("cu", "cuzn", "cusn"):
        sol_, liq_ = {"cu": (1065, 1083), "cuzn": (902, 920), "cusn": (910, 1040)}[rule]
        Trx = {"cu": 250, "cuzn": 350, "cusn": 400}[rule]
        trans += [{"T": Trx, "label": L("Rekristallisation (≈)", "recrystallisation (≈)")}, {"T": sol_, "label": "Solidus"}, {"T": liq_, "label": "Liquidus"}]
        cw = cold and T < Trx
        sols = _top_solutes(zus)
        if T >= liq_:
            panels.append(_lattice_panel(host, sols, T, de, seed, n, L("Schmelze", "Melt")))
            sk = sk_metal("schmelze", rng, de)
        else:
            f_b = 0.0
            if rule == "cuzn" and zus.get("Zn", 0) > 32:
                f_b = float(np.interp(T, [20, 700, 850], [max(0, (zus["Zn"] - 38.5) / 8), 0.0 + max(0, (zus["Zn"] - 36) / 10), 0.35]))
                trans.append({"T": 456, "label": L("β′ ⇄ β (Ordnung)", "β′ ⇄ β (ordering)")})
            panels.append(_lattice_panel(host, sols, min(T, sol_ - 1), de, seed, n, L("α-Mischkristall (kfz)", "α solid solution (fcc)"), cold=cw))
            if T >= sol_:
                sk = sk_metal("teilschmelze", rng, de, f_l=(T - sol_) / (liq_ - sol_), fill="#f1dfcf")
            elif f_b > 0.01:
                panels.append(_cell_panel("cuzn-beta", de, note=L("β′-CuZn, geordnet (B2); über 456 °C ungeordnet krz (β).", "β′ CuZn, ordered (B2); disordered bcc (β) above 456 °C.")))
                sk = sk_metal("zweiphasig", rng, de, f_b=f_b, acol="#f1dfcf", bcol="#c99a5b", alabel="α", blabel="β′/β")
            else:
                sk = sk_metal("fcc", rng, de, fill="#f1dfcf", label=L("α-Mischkristall mit Glühzwillingen", "α solid solution with annealing twins"),
                              gewalzt=cw)
            if rule == "cusn":
                panels.append(_cell_panel("cu3sn-eps", de, note=L("ε-Cu₃Sn: Gleichgewichtsphase unter ≈ 350 °C, bildet sich praktisch nicht (Diffusion zu langsam); gezeigt zum Vergleich.",
                                                                  "ε Cu₃Sn: equilibrium phase below ≈ 350 °C, practically never forms (diffusion too slow); shown for comparison.")))
            if cw:
                st.append(L(f"Zustand {zst}: kaltverfestigt (Versetzungen, gestreckte Körner).", f"Temper {zst}: strain hardened (dislocations, elongated grains)."))
            elif cold:
                st.append(L(f"Über ≈ {Trx} °C rekristallisiert das kaltverfestigte Gefüge.", f"Above ≈ {Trx} °C the cold-worked structure recrystallises."))
        refs += ["asm1990v2"]
    # ---------------------------------------------------------------- Titan
    elif rule in ("ti", "ti-ab"):
        sols = _top_solutes(zus)
        if rule == "ti":
            res = _lattice_panel(host, sols, T, de, seed, n, lat_title)
            panels.append(res)
            g = res["scene"]["phase"]["gitter_id"]
            sk = sk_metal("schmelze", rng, de) if res["scene"]["liquid"] else sk_metal("hcp" if g == "hdp" else "bcc", rng, de, fill="#e3e7ee",
                                                                                       label=res["scene"]["phase"]["name"])
            trans += [{"T": 882, "label": "α → β"}, {"T": Tm, "label": L("Schmelzen", "melting")}]
        else:
            trans += [{"T": 995, "label": L("β-Transus", "β transus")}, {"T": 1604, "label": "Solidus"}, {"T": 1660, "label": "Liquidus"}]
            if T >= 1660:
                panels.append(_lattice_panel(host, sols, T, de, seed, n, L("Schmelze", "Melt")))
                sk = sk_metal("schmelze", rng, de)
            else:
                fb = _interp(TI64_BETA, T)
                al_ = [s for s in sols if s["el"] in ("Al", "O")]
                v_ = [{"el": "V", "c": min(15.0, zus.get("V", 4) / max(fb, 0.25)), "einheit": "wt"}, {"el": "Fe", "c": 0.6, "einheit": "wt"}]
                if fb < 0.999:
                    panels.append(_lattice_panel(host, al_ + [{"el": "V", "c": 1.5, "einheit": "wt"}], min(T, 990), de, seed, n,
                                                 L("α-Phase (hdp), Al und O gelöst", "α phase (hcp), Al and O dissolved"), form="α-Ti"))
                panels.append(_lattice_panel(host, v_ + [{"el": "Al", "c": 4.0, "einheit": "wt"}], T, de, seed + 1, n,
                                             L("β-Phase (krz), V angereichert", "β phase (bcc), V enriched"), form="β-Ti"))
                sk = sk_metal("zweiphasig", rng, de, f_b=fb, acol="#e3e7ee", bcol="#8f9fb8", alabel=L("α (hdp)", "α (hcp)"), blabel=L("β (krz)", "β (bcc)")) \
                    if T < 1604 else sk_metal("teilschmelze", rng, de, f_l=(T - 1604) / 56, fill="#8f9fb8")
                st.append(L(f"β-Anteil bei {T:g} °C ≈ {fb * 100:.0f} % (Richtwert); Al stabilisiert α, V stabilisiert β.",
                            f"β fraction at {T:g} °C ≈ {fb * 100:.0f} % (guide value); Al stabilises α, V stabilises β."))
                if 480 <= T <= 650:
                    panels.append(_cell_panel("ti3al", de, note=L("α₂-Ti₃Al kann sich bei langer Auslagerung (500–600 °C) in α ordnen.", "α₂ Ti₃Al can order within α after long ageing (500–600 °C).")))
                refs += ["lutjering2007"]
    # ---------------------------------------------------------------- Magnesium
    elif rule == "mg-az":
        al = zus.get("Al", 0.0)
        sols = _top_solutes(zus)
        trans += [{"T": 605, "label": "Solidus"}, {"T": 630, "label": "Liquidus"}]
        solv = float(np.interp(al, [s for _, s in MG_AL_SOLVUS], [t for t, _ in MG_AL_SOLVUS]))
        trans.append({"T": solv, "label": L("Solvus β-Mg₁₇Al₁₂", "β Mg₁₇Al₁₂ solvus")})
        if T >= 630:
            panels.append(_lattice_panel(host, sols, T, de, seed, n, L("Schmelze", "Melt")))
            sk = sk_metal("schmelze", rng, de)
        else:
            sol_al = _interp(MG_AL_SOLVUS, min(T, 437))
            f_beta = max(0.0, (al - sol_al) / (44 - sol_al)) if T < solv else 0.0
            s2 = [{**s, "c": min(s["c"], sol_al) if s["el"] == "Al" else s["c"]} for s in sols]
            panels.append(_lattice_panel(host, s2, min(T, 604), de, seed, n, L("Mg-Mischkristall (hdp)", "Mg solid solution (hcp)"), cold=cold and T < 250))
            if f_beta > 0.002:
                panels.append(_cell_panel("mg17al12", de, note=L(f"β-Mg₁₇Al₁₂, Anteil ≈ {f_beta * 100:.1f} % (Hebelgesetz, Gleichgewicht).",
                                                                 f"β Mg₁₇Al₁₂, fraction ≈ {f_beta * 100:.1f} % (lever rule, equilibrium).")))
            sk = sk_metal("teilschmelze", rng, de, f_l=(T - 605) / 25, fill="#e9f2e2") if T >= 605 else \
                sk_metal("hcp", rng, de, fill="#e9f2e2", label=L("Mg-Mischkristall", "Mg solid solution"), gewalzt=cold and T < 250,
                         gb_dots=f_beta > 0.002, gb_col=C_PREC, gb_label="β-Mg₁₇Al₁₂", gb_frac=min(1.0, f_beta * 40))
            st.append(L(f"Al-Löslichkeit in Mg bei {T:g} °C ≈ {sol_al:.1f} % (Gleichgewicht).", f"Solubility of Al in Mg at {T:g} °C ≈ {sol_al:.1f} % (equilibrium)."))
            if cold and T < 250:
                st.append(L(f"Zustand {zst}: kaltverfestigt, Zwillinge und Versetzungen.", f"Temper {zst}: strain hardened, twins and dislocations."))
            refs += ["nayebhashemi1988"]
        refs += ["asm1990v2"]
    # ---------------------------------------------------------------- Nickel
    elif rule in ("ni", "ni-625", "ni-718"):
        sols = _top_solutes(zus)
        sol_, liq_ = {"ni": (1435, 1446), "ni-625": (1290, 1350), "ni-718": (1260, 1336)}[rule]
        trans += [{"T": sol_, "label": "Solidus"}, {"T": liq_, "label": "Liquidus"}]
        if T >= liq_:
            panels.append(_lattice_panel(host, sols, T, de, seed, n, L("Schmelze", "Melt")))
            sk = sk_metal("schmelze", rng, de)
        else:
            panels.append(_lattice_panel(host, sols, min(T, sol_ - 1), de, seed, n, L("γ-Matrix (kfz)", "γ matrix (fcc)")))
            opts = {}
            if rule == "ni-718":
                trans += [{"T": 900, "label": L("Solvus γ″/γ′", "γ″/γ′ solvus")}, {"T": 1010, "label": L("Solvus δ", "δ solvus")}]
                aged = zst == "ausgehaertet" or (hist_override or {}).get("kind") == "age"
                if T < 900 and aged:
                    panels.append(_cell_panel("ni3nb-gpp", de, note=L("γ″-Ni₃Nb (D0₂₂), Hauptaushärtungsphase, kohärente Scheiben.", "γ″ Ni₃Nb (D0₂₂), main strengthening phase, coherent discs.")))
                    panels.append(_cell_panel("ni3al", de, note=L("γ′-Ni₃(Al,Ti) (L1₂), kleiner Anteil.", "γ′ Ni₃(Al,Ti) (L1₂), minor fraction.")))
                    opts["state"] = "peak"
                if 760 <= T <= 1010 or aged:
                    panels.append(_cell_panel("ni3nb-delta", de, note=L("δ-Ni₃Nb, orthorhombisch, Nadeln an den Korngrenzen (760–1010 °C).", "δ Ni₃Nb, orthorhombic, needles on grain boundaries (760–1010 °C).")))
                    opts.update({"needles": True, "needle_label": L("δ-Ni₃Nb-Nadeln", "δ Ni₃Nb needles")})
                refs += ["reed2006"]
            if rule in ("ni-625", "ni-718"):
                panels.append(_cell_panel("nbc", de, note=L("NbC-Primärcarbide (MC).", "NbC primary carbides (MC).")))
            if T >= sol_:
                sk = sk_metal("teilschmelze", rng, de, f_l=(T - sol_) / (liq_ - sol_), fill="#e4ece4")
            else:
                st_ = opts.pop("state", "ss")
                sk = sk_metal("al", rng, de, state=st_, fill="#e4ece4", label=L("γ-Mischkristall", "γ solid solution"),
                              plabel="γ″/γ′", **opts)
        refs += ["asm1990v2"]
    # ---------------------------------------------------------------- reine Metalle
    else:
        res = _lattice_panel(host, _top_solutes(zus), T, de, seed, n, lat_title, cold=cold)
        panels.append(res)
        forms = e.get("formen", [])
        for f, f2 in zip(forms[:-1], forms[1:]):
            trans.append({"T": f["bis"], "label": f"{f['name']} → {f2['name']}"})
        trans.append({"T": Tm, "label": L("Schmelzen", "melting")})
        g = res["scene"]["phase"]["gitter_id"]
        if res["scene"]["liquid"]:
            sk = sk_metal("schmelze", rng, de)
        else:
            sk = sk_metal({"kfz": "fcc", "krz": "bcc", "hdp": "hcp"}[g], rng, de, fill="#e6e9ee", label=res["scene"]["phase"]["name"])
    if not st and panels and panels[0].get("kind") == "scene":
        ph = panels[0]["scene"].get("phase") or {}
        gname = {"kfz": L("kubisch flächenzentriert", "face-centred cubic"), "krz": L("kubisch raumzentriert", "body-centred cubic"),
                 "hdp": L("hexagonal dichteste Packung", "hexagonal close-packed")}.get(ph.get("gitter_id"), "")
        if panels[0]["scene"].get("liquid"):
            st.append(L(f"Bei {T:g} °C geschmolzen.", f"Molten at {T:g} °C."))
        else:
            st.append(L(f"Bei {T:g} °C: {ph.get('name', '')}" + (f" ({gname})" if gname else "") + ".",
                        f"At {T:g} °C: {ph.get('name', '')}" + (f" ({gname})" if gname else "") + "."))
        nxt = sorted((t for t in trans if t["T"] > T and (cold or "≈" not in t["label"])), key=lambda t: t["T"])
        if nxt:
            st.append(L(f"Nächste Umwandlung: {nxt[0]['label']} bei {nxt[0]['T']:.0f} °C.",
                        f"Next transition: {nxt[0]['label']} at {nxt[0]['T']:.0f} °C."))
        if cold and T < 300:
            st.append(L(f"Zustand {zst}: kaltverfestigt.", f"Temper {zst}: strain hardened."))
    if sk:
        # Metalle öffnen auf dem Gefüge: die Skizze ist die erste Ansicht
        panels.insert(0, {"kind": "sketch", "id": "gefuege", "title": L("Gefüge", "Microstructure"), "sketch": sk,
                       "caption": L("Schematisch, nicht massstäblich: Kornform, Anteile und Lage der Phasen sind angedeutet.",
                                    "Schematic, not to scale: grain shape, fractions and position of phases are indicated.")})
    return {"panels": panels, "statements": st, "notes": notes, "refs": refs, "q": q, "transitions": trans}


# ============================================================================ übrige Werkstoffarten
ZERS = {"pvc": 200, "pom": 230, "ptfe": 500, "peek": 550, "pi": 550, "ppta": 500, "pla": 250, "pa6": 350, "pa66": 350}


def _poly_xc(r: dict, T: float) -> float:
    xc = r.get("xc") or [0, 0]
    x0 = float(np.mean(xc))
    Tm = r.get("Tm")
    if not Tm or x0 <= 0:
        return 0.0
    if T >= Tm:
        return 0.0
    if T > Tm - 40:
        return x0 * (Tm - T) / 40
    return x0


def _poly_cell_id(r: dict, T: float) -> tuple[str | None, bool]:
    if r.get("zelle_T"):
        for z in r["zelle_T"]:
            if T <= z["bis"]:
                return z["zelle"], bool(z.get("ungeordnet"))
        return None, False
    return r.get("zelle"), False


def _polymer(mid: str, r: dict, T: float, de: bool, rng) -> dict:
    def L(a, b):
        return a if de else b
    pid = r["poly"]
    P = PY.POLY[pid]
    Tg, Tm = r.get("Tg"), r.get("Tm")
    Tz = r.get("zersetzt") or ZERS.get(pid, 250 if r["typ"] == "elastomer" else (300 if r["typ"] == "duroplast" else 350))
    trans = []
    if Tg is not None:
        trans.append({"T": Tg, "label": "Tg"})
    if Tm:
        trans.append({"T": Tm, "label": "Tm"})
    for z in r.get("zelle_T") or []:
        if not Tm or z["bis"] < Tm:
            trans.append({"T": z["bis"], "label": L("Kristallumwandlung", "crystal transition")})
    trans.append({"T": Tz, "label": L("Zersetzung (≈)", "decomposition (≈)")})
    panels, st, refs = [], [], ["strobl2007"]
    q = [r.get("q")] if r.get("q") else []
    if T >= Tz:
        st.append(L(f"Über ≈ {Tz:g} °C zersetzt sich {P['name']} (Kettenspaltung, Abspaltung flüchtiger Produkte); keine Struktur gezeigt.",
                    f"Above ≈ {Tz:g} °C {P['name_en']} decomposes (chain scission, volatile products); no structure shown."))
        return {"panels": [], "statements": st, "notes": [], "refs": refs, "q": q, "transitions": trans}
    xc = _poly_xc(r, T)
    cid, disordered = _poly_cell_id(r, T)
    cryst_ok = xc > 0.005 and cid
    hx = None
    if cryst_ok:
        hx = tuple(phase_any(cid).get("helix") or P["helix"])
    one = PY.chain(pid, 1, hx if cryst_ok else (2, 1))
    units = max(2, min(12, round(14 / max(one["repeat"], 0.5))))
    if cryst_ok and hx and hx != (2, 1):
        units = hx[0]
    ch = chain_scene(pid, units, de, hx, crystal=bool(cryst_ok), rng=rng)
    panels.append({"kind": "scene", "sub": "chain", "id": "kette", "title": L("Kette: ", "Chain: ") + P["formel"], "scene": ch,
                   "caption": L(("Konformation wie im Kristall" + (f" (Helix {hx[0]}/{hx[1]})" if hx and hx != (2, 1) else " (gestreckte Zickzackkette)")) if cryst_ok else
                                "gestreckt gezeichnet; im amorphen Zustand liegt sie als Knäuel vor",
                                ("conformation as in the crystal" + (f" (helix {hx[0]}/{hx[1]})" if hx and hx != (2, 1) else " (extended zigzag)")) if cryst_ok else
                                "drawn extended; in the amorphous state it forms a coil") +
                   L(". Nur C, N, O, F, Cl, Si; H nicht gezeigt; Standardbindungslängen.", ". C, N, O, F, Cl, Si only; H not shown; standard bond lengths.")})
    if cryst_ok:
        ph = phase_any(cid)
        sc = polymer_cell_scene(cid, de)
        panels.append({"kind": "scene", "sub": "cell", "id": "zelle:" + cid, "title": L("Kristallzelle ", "Crystal cell ") + pname(ph, de),
                       "scene": sc, "phase": {"id": cid, "name": pname(ph, de), "system": ph.get("system"), "spacegroup": ph.get("spacegroup"),
                                               "cell": ph.get("cell"), "art": ph["_art"], "unchecked": bool(ph.get("nicht_geprueft"))},
                       "caption": L("Zelle aus der Quelle; Ketten mit Modellgeometrie eingesetzt" + (", Lage schematisch" if ph.get("kettenlage_schematisch") else "") +
                                    (". Über 30 °C sind die Helices gegeneinander verdreht (ungeordnet)." if disordered else "."),
                                    "Cell from the source; chains inserted with model geometry" + (", position schematic" if ph.get("kettenlage_schematisch") else "") +
                                    (". Above 30 °C the helices are rotationally disordered." if disordered else ".")),
                       "q": ph["_q"]})
    xl = r.get("vernetzt")
    glassy = Tg is not None and T < Tg
    if xc < 0.995:
        dens = (0.012 if r["typ"] == "elastomer" else 0.08) if xl else 0.0
        cs = coil_scene(pid, de, rng, n_chains=5, n_atoms=60, box=20.0, xlink=dens, xel=P.get("vernetzer", "C"), glassy=glassy)
        panels.append({"kind": "scene", "sub": "coil", "id": "knaeuel",
                       "title": (L("Netzwerk", "Network") if xl else L("Amorphe Bereiche", "Amorphous regions")) + (L(" (glasartig)", " (glassy)") if glassy else L(" (beweglich)", " (mobile)")),
                       "scene": cs, "caption": L("Zufallsknäuel, nur Rückgratatome; jede Farbe eine Kette" + (", rot: Vernetzungsstellen" if xl else "") + ".",
                                                 "Random coils, backbone atoms only; one colour per chain" + (", red: cross-links" if xl else "") + ".")})
    if r["typ"] != "duroplast" and not (r["typ"] == "elastomer" and not r.get("xc")):
        panels.append({"kind": "sketch", "id": "morphologie", "title": L("Morphologie (Skizze)", "Morphology (sketch)"),
                       "sketch": sk_polymer(xc, rng, de, oriented=bool(r.get("orientiert")), crosslinked=bool(xl), melt=bool(Tm and T >= Tm)),
                       "caption": L("Schematisch: Lamellen, amorphe Zwischenschichten und Verbindungsmoleküle.", "Schematic: lamellae, amorphous interlayers and tie molecules.")})
    # Aussagen
    if Tm and T >= Tm:
        st.append(L(f"Über Tm = {Tm:g} °C: Schmelze, Ketten als Knäuel, keine Kristalle.", f"Above Tm = {Tm:g} °C: melt, chains as coils, no crystals."))
    elif xc > 0:
        st.append(L(f"Teilkristallin, Kristallinität ≈ {xc * 100:.0f} %" + (f" (nimmt kurz vor Tm = {Tm:g} °C ab)" if Tm and T > Tm - 40 else "") + ".",
                    f"Semi-crystalline, crystallinity ≈ {xc * 100:.0f} %" + (f" (falls just below Tm = {Tm:g} °C)" if Tm and T > Tm - 40 else "") + "."))
    else:
        st.append(L("Amorph" + (", vernetzt" if xl else "") + ".", "Amorphous" + (", cross-linked" if xl else "") + "."))
    if Tg is not None:
        st.append(L(f"{'Unter' if glassy else 'Über'} Tg = {Tg:g} °C: amorphe Bereiche {'eingefroren (glasartig)' if glassy else 'beweglich (gummiartig' + (')' if xl or xc else ', fliessfähig)')}.",
                    f"{'Below' if glassy else 'Above'} Tg = {Tg:g} °C: amorphous regions {'frozen (glassy)' if glassy else 'mobile (rubbery' + (')' if xl or xc else ', flowing)')}."))
    if r.get("wasser"):
        st.append(L(f"≈ {r['wasser']:g} % Wasser in den amorphen Bereichen senkt Tg.", f"≈ {r['wasser']:g} % water in the amorphous regions lowers Tg."))
    if r.get("xc_dehnung"):
        st.append(L(f"Kristallisiert unter starker Dehnung (bis ≈ {r['xc_dehnung'] * 100:.0f} %).", f"Crystallises under high strain (up to ≈ {r['xc_dehnung'] * 100:.0f} %)."))
    return {"panels": panels, "statements": st, "notes": [], "refs": refs, "q": q, "transitions": trans}


def _crystal(mid: str, r: dict, T: float, de: bool, rng) -> dict:
    def L(a, b):
        return a if de else b
    trans = []
    pid = r.get("phase")
    if r.get("phasen_T"):
        pid = None
        for z in r["phasen_T"]:
            if z["bis"] != r.get("schmelze"):
                trans.append({"T": z["bis"], "label": f"{pname(phase_any(z['phase']), de)} →"})
            if T <= z["bis"] and pid is None:
                pid = z["phase"]
    Tm = r.get("schmelze")
    if Tm:
        trans.append({"T": Tm, "label": L("Schmelzen/Zersetzen", "melting/decomposition")})
    panels, st = [], []
    if Tm and T >= Tm:
        st.append(L(f"Über {Tm:g} °C keine kristalline Phase (Schmelze bzw. Zersetzung).", f"No crystalline phase above {Tm:g} °C (melt or decomposition)."))
    elif pid:
        panels.append(_cell_panel(pid, de))
        ph = phase_any(pid)
        if len(expand_any(ph)) <= 30 and not ph.get("nur_zelle"):
            panels.append(_cell_panel(pid, de, title=L("2×2×2 Zellen", "2×2×2 cells"), reps=(2, 2, 2), pid_tag="zelle2:" + pid))
        st.append(L(f"Phase bei {T:g} °C: {pname(ph, de)} ({ph.get('spacegroup') or ph.get('system')}).",
                    f"Phase at {T:g} °C: {pname(ph, de)} ({ph.get('spacegroup') or ph.get('system')})."))
    elif r.get("phasen_T"):
        st.append(L("Kubisches ZrO₂ (Fluorit-Typ) über 2370 °C: Zelle nicht hinterlegt.", "Cubic ZrO₂ (fluorite type) above 2370 °C: cell not available."))
    if mid == "zro2-3y" and panels:
        panels.append(_cell_panel("zro2-m", de, note=L("Zum Vergleich: monoklines ZrO₂ (stabil unter ≈ 1170 °C ohne Y₂O₃).",
                                                       "For comparison: monoclinic ZrO₂ (stable below ≈ 1170 °C without Y₂O₃).")))
    if r.get("hinweis"):
        st.append(r["hinweis"] if de else r.get("hinweis_en", r["hinweis"]))
    return {"panels": panels, "statements": st, "notes": [], "refs": ["wyckoff1963"], "q": [r.get("q")] if r.get("q") else [], "transitions": trans}


def _glass(mid: str, r: dict, T: float, de: bool, rng) -> dict:
    def L(a, b):
        return a if de else b
    Tg = r.get("Tg")
    sc, info = glass_scene(r["netz"], de, rng, T, Tg)
    st = [L(f"Amorphes Netzwerk; je Tetraeder ≈ {info['nbo_per_t']:g} Trennstellensauerstoffe (aus der Zusammensetzung).",
            f"Amorphous network; ≈ {info['nbo_per_t']:g} non-bridging oxygens per tetrahedron (from the composition).")]
    if Tg:
        st.append(L(f"{'Unter' if T < Tg else 'Über'} Tg = {Tg:g} °C: {'Struktur eingefroren' if T < Tg else 'unterkühlte Schmelze, Netzwerk beweglich'}.",
                    f"{'Below' if T < Tg else 'Above'} Tg = {Tg:g} °C: {'structure frozen' if T < Tg else 'supercooled liquid, network mobile'}."))
    state = (L(" (eingefroren)", " (frozen)") if T < Tg else L(" (unterkühlte Schmelze)", " (supercooled liquid)")) if Tg else ""
    panels = [{"kind": "scene", "sub": "network", "id": "netzwerk", "title": L("Glasnetzwerk", "Glass network") + state, "scene": sc,
               "caption": L("Schematisch nach Zachariasen (1932): Tetraeder über Brückensauerstoff verbunden, ohne Fernordnung.",
                            "Schematic after Zachariasen (1932): tetrahedra linked by bridging oxygen, without long-range order.")}]
    panels.append(_cell_panel("quarz", de, note=L("Zum Vergleich: kristallines SiO₂ (α-Quarz) mit Fernordnung.", "For comparison: crystalline SiO₂ (α-quartz) with long-range order.")))
    return {"panels": panels, "statements": st, "notes": [], "refs": ["zachariasen1932", "shelby2005"], "q": [r.get("q")] if r.get("q") else [],
            "transitions": [{"T": Tg, "label": "Tg"}] if Tg else []}


def _carbonfibre(mid: str, r: dict, T: float, de: bool, rng) -> dict:
    def L(a, b):
        return a if de else b
    sc = turbostratic_scene(r["d002"], r["Lc_nm"], r["ordnung"], de, rng)
    panels = [{"kind": "scene", "sub": "layers", "id": "schichten", "title": L("Turbostratische Schichten", "Turbostratic layers"), "scene": sc,
               "caption": L(f"d₀₀₂ = {r['d002']:g} Å, Stapelhöhe Lc ≈ {r['Lc_nm']:g} nm; Schichten verdreht und versetzt, gewellt (schematisch).",
                            f"d₀₀₂ = {r['d002']:g} Å, stack height Lc ≈ {r['Lc_nm']:g} nm; layers rotated, shifted and wavy (schematic).")},
              _cell_panel("graphit", de, note=L("Zum Vergleich: Graphit (AB-Stapelung, d₀₀₂ = 3,35 Å).", "For comparison: graphite (AB stacking, d₀₀₂ = 3.35 Å)."))]
    st = [L("Kohlenstofffaser: turbostratische Graphenschichten entlang der Faserachse; höhere Ordnung → höherer Modul.",
            "Carbon fibre: turbostratic graphene layers along the fibre axis; more order → higher modulus.")]
    if T > 400:
        st.append(L("An Luft oxidiert die Faser ab ≈ 400–500 °C.", "In air the fibre oxidises from ≈ 400–500 °C."))
    return {"panels": panels, "statements": st, "notes": [], "refs": ["oberlin1984"], "q": [r.get("q")] if r.get("q") else [],
            "transitions": [{"T": 450, "label": L("Oxidation an Luft (≈)", "oxidation in air (≈)")}]}


def _composite(mid: str, r: dict, T: float, de: bool, rng, depth: int) -> dict:
    def L(a, b):
        return a if de else b
    f = build(r["faser"], T, "de" if de else "en", depth=depth + 1, n=4)
    m = build(r["matrix"], T, "de" if de else "en", depth=depth + 1, n=4)
    fname, mname = f["material"]["name"], m["material"]["name"]
    fcol = {"glas": "#cfe3ec", "kohlenstofffaser": "#2d2d2d"}.get(f["material"]["typ"], "#e3c46a")
    sk = sk_composite(r["phi"], r.get("anordnung", "ud"), rng, de, fcol, "#e9dcc2", L("Faser: ", "Fibre: ") + fname, L("Matrix: ", "Matrix: ") + mname)
    panels = [{"kind": "sketch", "id": "verbund", "title": L("Faseranordnung (Skizze)", "Fibre arrangement (sketch)"), "sketch": sk,
               "caption": L(f"Faservolumenanteil φ = {r['phi'] * 100:.0f} %; {sk['note']}.", f"Fibre volume fraction φ = {r['phi'] * 100:.0f} %; {sk['note']}.")}]
    for pre, sub in ((L("Faser: ", "Fibre: "), f), (L("Matrix: ", "Matrix: "), m)):
        for p in sub["panels"][:2]:
            p = dict(p)
            p["title"] = pre + p["title"]
            p["id"] = pre[:1] + ":" + p["id"]
            panels.append(p)
    st = [L(f"Verbund aus {fname} in {mname}, φ = {r['phi'] * 100:.0f} %.", f"Composite of {fname} in {mname}, φ = {r['phi'] * 100:.0f} %.")]
    st += [L("Matrix: ", "Matrix: ") + s for s in m["statements"][:2]]
    trans = [t for t in m["transitions"]]
    return {"panels": panels, "statements": st, "notes": [], "refs": list(dict.fromkeys(f["refs_keys"] + m["refs_keys"])),
            "q": list(dict.fromkeys(f["q"] + m["q"])), "transitions": trans}


# Erwärmen cellulosehaltiger Werkstoffe (Holz, Papier) ohne Luftzutritt, wie in der Thermogravimetrie unter Stickstoff:
# Wasser ab 100 °C; Hauptmasseverlust der Hemicellulose 220–315 °C, der Cellulose 315–400 °C (Yang et al. 2007,
# Kurzfassung); Cellulose depolymerisiert zu Levoglucosan, Kohle aus der Repolymerisation der Produkte (Lin et al. 2009);
# kein Schmelzen vor der Zersetzung (Shafizadeh 1982); Asche bei 525 °C an Luft (ISO 1762).
CELL_T = (100.0, 220.0, 315.0, 400.0)
CELL_ASH_T = 525.0


def _cellulose_stage(T: float) -> int:
    """0 feucht, 1 trocken, 2 Hemicellulose zersetzt sich, 3 Cellulose zersetzt sich, 4 Pyrolysekohle."""
    return sum(T >= t for t in CELL_T)


def _cellulose_char(T: float) -> float:
    """Verkohlungsgrad der Skizze: 0 bis 220 °C, steigt bis 400 °C auf 1 (Farbe schematisch, keine Messgrösse)."""
    return float(min(max((T - CELL_T[1]) / (CELL_T[3] - CELL_T[1]), 0.0), 1.0))


def _natural(mid: str, r: dict, T: float, de: bool, rng) -> dict:
    def L(a, b):
        return a if de else b
    panels = []
    wood = r["typ"] == "holz"
    stage, char = _cellulose_stage(T), _cellulose_char(T)
    if wood:
        sk = sk_wood(r.get("art", "nadelholz"), r.get("mfw_S2", 15), rng, de, char, stage)
        title = L("Holz, Querschnitt (Skizze)", "Wood, cross-section (sketch)") if stage < 4 else L("Holzkohle, Querschnitt (Skizze)", "Wood char, cross-section (sketch)")
    else:
        fill = sum((r.get("fuellstoff") or {}).values())
        sk = sk_paper(fill, rng, de, char, stage)
        title = L("Fasernetzwerk (Skizze)", "Fibre network (sketch)") if stage < 4 else L("Verkohltes Fasernetzwerk (Skizze)", "Charred fibre network (sketch)")
    cap = sk.get("note", "")
    if stage:
        cap = (cap + "; " if cap else "") + L(f"bei {T:g} °C ohne Luftzutritt: {_wall_label(stage, True)}", f"at {T:g} °C without air: {_wall_label(stage, False)}")
    panels.append({"kind": "sketch", "id": "gefuege", "title": title, "sketch": sk, "caption": cap})
    if stage < 4:
        panels.append({"kind": "scene", "sub": "chain", "id": "kette", "title": L("Cellulosekette", "Cellulose chain"),
                       "scene": chain_scene("cellulose", 4, de, None, True, rng),
                       "caption": L("β-1,4-glykosidisch verknüpfte Glucoseringe; H nicht gezeigt.", "β-1,4-linked glucose rings; H not shown.") +
                       (L(" Zwischen 315 und 400 °C spalten die Ketten zu Levoglucosan.", " Between 315 and 400 °C the chains split into levoglucosan.") if stage == 3 else "")})
        sc = polymer_cell_scene("cellulose-ib", de)
        ph = phase_any("cellulose-ib")
        panels.append({"kind": "scene", "sub": "cell", "id": "zelle:cellulose-ib", "title": L("Kristallzelle Cellulose Iβ", "Crystal cell cellulose Iβ"),
                       "scene": sc, "phase": {"id": "cellulose-ib", "name": pname(ph, de), "system": ph.get("system"), "spacegroup": ph.get("spacegroup"),
                                               "cell": ph.get("cell"), "art": ph["_art"], "unchecked": bool(ph.get("nicht_geprueft"))}, "q": ph["_q"],
                       **({"caption": L("Die Kristalle zersetzen sich in diesem Bereich mit der übrigen Cellulose.",
                                        "The crystals decompose in this range together with the rest of the cellulose.")} if stage == 3 else {})})
    comp = ", ".join(f"{k} {v * 100:.0f} %" for k, v in (("Cellulose", r.get("zellulose")), ("Hemicellulose", r.get("hemicellulose")), ("Lignin", r.get("lignin"))) if v)
    st = [L(f"Zusammensetzung (Masse): {comp}.", f"Composition (mass): {comp}.")] if comp else []
    refs = ["fengel1984", "yang2007", "lin2009", "shafizadeh1982"] + (["fpl2010"] if wood else [])
    if stage == 0:
        st.append(L("Gebundenes Wasser in den Zellwänden (Holzfeuchte ≈ 12 % bei 20 °C und 65 % relativer Luftfeuchte)." if wood else
                    "Die Fasern enthalten gebundenes Wasser aus der Raumluft.",
                    "Bound water in the cell walls (moisture content ≈ 12 % at 20 °C and 65 % relative humidity)." if wood else
                    "The fibres hold bound water from the air."))
    else:
        st.append(L("Ab 100 °C verdampft das Wasser; die Wände schwinden.", "From 100 °C the water evaporates; the walls shrink."))
    if 1 <= stage <= 2:
        st.append(L("Cellulose schmilzt nicht und erweicht nicht merklich: sie zersetzt sich, bevor sie schmilzt.",
                    "Cellulose neither melts nor noticeably softens: it decomposes before it melts."))
    if stage >= 2:
        st.append(L("Erwärmen ohne Luftzutritt (Pyrolyse, wie in der Thermogravimetrie unter Stickstoff).",
                    "Heating without air (pyrolysis, as in thermogravimetry under nitrogen)."))
    if stage == 2:
        st.append(L("220–315 °C: Hemicellulose zersetzt sich (Hauptmasseverlust), das Material bräunt; die Cellulose bleibt noch erhalten.",
                    "220–315 °C: hemicellulose decomposes (main mass loss), the material browns; the cellulose still survives."))
    if stage == 3:
        st.append(L("315–400 °C: Cellulose zersetzt sich. Die Ketten spalten zu Levoglucosan (flüchtiger Anhydrozucker); "
                    "aus der Repolymerisation der Produkte entsteht Kohle.",
                    "315–400 °C: cellulose decomposes. The chains split into levoglucosan (a volatile anhydrosugar); "
                    "char forms from the repolymerisation of the products."))
    if stage >= 3 and (r.get("lignin") or 0) > 0:
        st.append(L("Lignin zersetzt sich langsam über einen weiten Bereich (bis etwa 900 °C).",
                    "Lignin decomposes slowly over a wide range (up to about 900 °C)."))
    if stage == 4:
        st.append(L("Über 400 °C ist keine Cellulose mehr vorhanden; zurück bleibt Pyrolysekohle.",
                    "Above 400 °C no cellulose is left; pyrolysis char remains."))
    if T >= CELL_ASH_T:
        st.append(L("An Luft verascht die Kohle; bei 525 °C bleibt nur der anorganische Rest: "
                    + ("bei Holz weniger als 1 %." if wood else "vor allem der Füllstoff (CaCO₃ bleibt bei 525 °C weitgehend erhalten)."),
                    "In air the char burns off; at 525 °C only the inorganic residue remains: "
                    + ("less than 1 % for wood." if wood else "mainly the filler (CaCO₃ largely survives at 525 °C).")))
        refs.append("iso1762")
    trans = [{"T": 100, "label": L("Wasser verdampft", "water evaporates")}, {"T": 220, "label": L("Hemicellulose zersetzt", "hemicellulose decomposes")},
             {"T": 315, "label": L("Cellulose zersetzt", "cellulose decomposes")}, {"T": 400, "label": L("Kohle", "char")},
             {"T": CELL_ASH_T, "label": L("Asche (an Luft)", "ash (in air)")}]
    return {"panels": panels, "statements": st, "notes": [], "refs": list(dict.fromkeys(refs)), "q": [r.get("q")] if r.get("q") else [], "transitions": trans}


def _concrete(mid: str, r: dict, T: float, de: bool, rng) -> dict:
    def L(a, b):
        return a if de else b
    panels = [{"kind": "sketch", "id": "gefuege", "title": L("Beton (Skizze)", "Concrete (sketch)"), "sketch": sk_concrete(r.get("zuschlag", .7), rng, de, T),
               "caption": L("Gesteinskörnung in Zementstein mit Poren; schematisch.", "Aggregate in cement paste with pores; schematic.")}]
    if T < 500:
        panels.append(_cell_panel("portlandit", de, note=L("Portlandit Ca(OH)₂, Schichtstruktur; entwässert bei 450–550 °C zu CaO.", "Portlandite Ca(OH)₂, layered; dehydrates to CaO at 450–550 °C.")))
    else:
        panels.append(_cell_panel("cao", de, note=L("CaO aus entwässertem Portlandit (über ≈ 500 °C).", "CaO from dehydrated portlandite (above ≈ 500 °C).")))
    panels.append(_cell_panel("quarz", de, note=L("Quarz der Gesteinskörnung; α → β bei 573 °C (Volumensprung, Risse).", "Quartz of the aggregate; α → β at 573 °C (volume jump, cracking).")))
    panels.append(_cell_panel("calcit", de, note=L("Calcit CaCO₃ aus der Carbonatisierung von Portlandit.", "Calcite CaCO₃ from carbonation of portlandite.")))
    st = [L("Zementstein: C-S-H-Gel (nanokristallin, ohne Elementarzelle), Portlandit, Ettringit/AFm; Gesteinskörnung Quarz.",
            "Cement paste: C-S-H gel (nanocrystalline, no unit cell), portlandite, ettringite/AFm; quartz aggregate.")]
    for Tl, de_, en_ in ((100, "freies Wasser verdampft", "free water evaporates"), (120, "Ettringit zersetzt", "ettringite decomposes"),
                         (450, "Portlandit entwässert", "portlandite dehydrates"), (573, "Quarz α → β", "quartz α → β"), (700, "Calcit zersetzt", "calcite decomposes")):
        if T >= Tl:
            st.append(L(f"über {Tl} °C: {de_}", f"above {Tl} °C: {en_}"))
    trans = [{"T": 100, "label": L("Wasser", "water")}, {"T": 450, "label": "Ca(OH)₂ → CaO"}, {"T": 573, "label": L("Quarz α → β", "quartz α → β")},
             {"T": 700, "label": "CaCO₃ → CaO"}]
    return {"panels": panels, "statements": st, "notes": [], "refs": ["taylor1997cem"], "q": [r.get("q")] if r.get("q") else [], "transitions": trans}


def _glassceramic(mid: str, r: dict, T: float, de: bool, rng) -> dict:
    def L(a, b):
        return a if de else b
    g = _glass(mid, r, T, de, rng)
    panels = [{"kind": "sketch", "id": "gefuege", "title": L("Glaskeramik (Skizze)", "Glass-ceramic (sketch)"), "sketch": sk_glassceramic(r.get("anteil", .9), rng, de),
               "caption": L(f"Kristallanteil ≈ {r.get('anteil', .9) * 100:.0f} % in Restglas; schematisch.", f"Crystal fraction ≈ {r.get('anteil', .9) * 100:.0f} % in residual glass; schematic.")},
              _cell_panel(r.get("kristall", "spodumen-beta"), de), g["panels"][0]]
    Tg = r.get("Tg")
    g["panels"][0]["title"] = L("Restglas (Netzwerk)", "Residual glass (network)") + (
        (L(" (eingefroren)", " (frozen)") if T < Tg else L(" (erweicht)", " (softened)")) if Tg else "")
    st = [L(f"Glaskeramik: ≈ {r.get('anteil', .9) * 100:.0f} % Kristalle, Rest Glas.", f"Glass-ceramic: ≈ {r.get('anteil', .9) * 100:.0f} % crystals, rest glass.")]
    if Tg:
        st.append(L(f"Restglas {'unter' if T < Tg else 'über'} Tg = {Tg:g} °C: {'eingefroren' if T < Tg else 'beweglich, die Kristalle bleiben'}.",
                    f"Residual glass {'below' if T < Tg else 'above'} Tg = {Tg:g} °C: {'frozen' if T < Tg else 'mobile, the crystals remain'}."))
    if r.get("hinweis"):
        st.append(r["hinweis"] if de else r.get("hinweis_en", r["hinweis"]))
    return {"panels": panels, "statements": st, "notes": [], "refs": ["holand2012", "zachariasen1932"], "q": [r.get("q")] if r.get("q") else [],
            "transitions": g["transitions"]}


# ============================================================================ Einstieg
def materials(lang: str = "de") -> list[dict]:
    """Alle Werkstoffe mit Strukturdatensatz für die Auswahl: id, Name, Klasse, Art."""
    from labcalc import materials as M
    gef = _gef()["werkstoffe"]
    out = []
    for row in M.materials():
        mid = row.get("id")
        if mid in gef:
            s = M.summary(row, lang)
            out.append({"id": mid, "name": s["name"], "klasse": row.get("klasse") or row.get("class"), "typ": gef[mid]["typ"],
                        "zugversuch": bool(row.get("zugversuch"))})
    return out


def _mat_name(mid: str, lang: str) -> tuple[str, dict]:
    from labcalc import materials as M
    for row in M.materials():
        if row.get("id") == mid:
            return M.summary(row, lang)["name"], row
    return mid, {}


def t_range(r: dict, trans: list) -> tuple[float, float]:
    hi = max([t["T"] for t in trans if t.get("T") is not None] + [100]) + 80
    lo = 20.0 if r["typ"] in ("beton", "holz", "papier", "glas", "glaskeramik") else -196.0
    return lo, min(hi, 3500.0)


def build(mid: str, T: float = 20.0, lang: str = "de", seed: int = 1, n: int = 5, depth: int = 0, hist=None) -> dict:
    """Ansichten des Werkstoffs `mid` bei T (°C)."""
    de = lang != "en"
    if depth > 2:
        raise StructError("Verschachtelung zu tief")
    r = record(mid)
    T = float(T)
    if not -273.15 < T < 4000:
        raise StructError("Temperatur zwischen −273 °C und 4000 °C angeben")
    rng = np.random.default_rng(seed)
    typ = r["typ"]
    if typ == "metall":
        out = _metal(mid, r, T, de, rng, hist, n=n)
        if hist is None:
            _lib_gefuege(out, r, T, de, seed)
    elif typ in ("polymer", "elastomer", "duroplast"):
        out = _polymer(mid, r, T, de, rng)
    elif typ == "kristall":
        out = _crystal(mid, r, T, de, rng)
    elif typ == "glas":
        out = _glass(mid, r, T, de, rng)
    elif typ == "glaskeramik":
        out = _glassceramic(mid, r, T, de, rng)
    elif typ == "kohlenstofffaser":
        out = _carbonfibre(mid, r, T, de, rng)
    elif typ == "verbund":
        out = _composite(mid, r, T, de, rng, depth)
    elif typ in ("holz", "papier"):
        out = _natural(mid, r, T, de, rng)
    elif typ == "beton":
        out = _concrete(mid, r, T, de, rng)
    else:
        raise StructError(f"Werkstoffart {typ} unbekannt")
    name, row = _mat_name(mid, lang)
    trans = sorted({(round(t["T"], 1), t["label"]) for t in out["transitions"] if t.get("T") is not None})
    trans = [{"T": t, "label": l} for t, l in trans]
    q = [k for k in out["q"] if k]
    refs = list(out["refs"])
    for p in out["panels"]:
        q += [k for k in p.get("q") or [] if k]
        refs += [k for k in p.get("refs") or [] if isinstance(k, str)]
    notes = list(out["notes"])
    if r.get("hinweis") and typ != "kristall" and typ != "glaskeramik":
        notes.append(r["hinweis"] if de else r.get("hinweis_en", r["hinweis"]))
    if r.get("zus_hinweis"):
        notes.append(r["zus_hinweis"] if de else r.get("zus_hinweis_en", r["zus_hinweis"]))
    unchecked = any((p.get("phase") or {}).get("unchecked") for p in out["panels"])
    if unchecked:
        notes.append("Literaturzellen: Angaben nicht am Original geprüft." if de else "Literature cells: data not checked against the original.")
    lo, hi = t_range(r, trans)
    statements = list(out["statements"])
    no_change = not any(lo < t["T"] < hi for t in trans)        # nichts im Bereich des Reglers: einmal klar sagen
    if no_change:
        statements.append(f"Zwischen {lo:g} und {hi:g} °C keine Umwandlung: die Struktur bleibt wie gezeigt." if de else
                          f"No transformation between {lo:g} and {hi:g} °C: the structure stays as shown.")
    return {"material": {"id": mid, "name": name, "typ": typ, "zustand": r.get("zustand"), "zus": r.get("zus"),
                         "regel": r.get("regel")},
            "T": T, "lang": lang, "range": [lo, hi], "transitions": trans, "panels": out["panels"], "no_change": no_change,
            "statements": statements, "notes": notes, "refs_keys": list(dict.fromkeys(refs + ["cordero2008"] + (["grazulis2012"] if any(str(k).startswith("cod") for k in q) else []))),
            "q": list(dict.fromkeys(q)), "temper": temper_presets(mid, lang)}


# ============================================================================ Wärmebehandlung
def temper_presets(mid: str, lang: str = "de") -> list[dict]:
    """Vorgeschlagene Wärmebehandlungswege für den Werkstoff (leer, wenn keiner passt)."""
    de = lang != "en"
    r = record(mid)
    rule = r.get("regel")
    out = []
    if rule == "stahl" and (r.get("zus") or {}).get("C", 0) >= 0.2:
        from . import steel as STL
        zus = r.get("zus") or {}
        Ac3 = STL.composition_report({k: zus.get(k, 0.0) for k in ("C", "Si", "Mn", "Cr", "Mo", "V", "Ni", "Cu", "B")})["Ac3"]
        Ta = round((Ac3 + 40) / 10) * 10
        for Tt in (200, 400, 600):
            out.append({"id": f"qt{Tt}", "name": (f"Härten {Ta:.0f} °C, Anlassen {Tt} °C / 1 h" if de else
                                                  f"Harden {Ta:.0f} °C, temper {Tt} °C / 1 h"),
                        "kind": "qt", "steps": [{"name": "Austenitisieren" if de else "austenitise", "T": Ta, "t": 0.5},
                                                {"name": "Abschrecken" if de else "quench", "T": 20, "t": 0.0, "quench": True},
                                                {"name": "Anlassen" if de else "temper", "T": Tt, "t": 1.0},
                                                {"name": "Abkühlen" if de else "cool", "T": 20, "t": 0.0}]})
    elif rule in AL and "peak" in AL[rule]:
        a = AL[rule]
        Ts = a["solvus"] + 10
        Tp, tp = a["peak"]
        sol = {"name": "Lösungsglühen" if de else "solution treat", "T": Ts, "t": 1.0}
        q = {"name": "Abschrecken" if de else "quench", "T": 20, "t": 0.0, "quench": True}
        out.append({"id": "t4", "name": "T4: " + ("kaltausgelagert" if de else "naturally aged"), "kind": "age",
                    "steps": [sol, q, {"name": "Kaltauslagern" if de else "natural ageing", "T": 20, "t": 96.0}]})
        out.append({"id": "t6", "name": f"T6: {Tp} °C / {tp} h", "kind": "age",
                    "steps": [sol, q, {"name": "Warmauslagern" if de else "artificial ageing", "T": Tp, "t": float(tp)},
                              {"name": "Abkühlen" if de else "cool", "T": 20, "t": 0.0}]})
        out.append({"id": "t7", "name": "T7: " + ("überaltert" if de else "over-aged") + f" {Tp + 40} °C / 24 h", "kind": "age",
                    "steps": [sol, q, {"name": "Warmauslagern" if de else "artificial ageing", "T": Tp + 40, "t": 24.0},
                              {"name": "Abkühlen" if de else "cool", "T": 20, "t": 0.0}]})
    elif rule == "ni-718":
        out.append({"id": "718", "name": ("Lösungsglühen 980 °C, Auslagern 720/620 °C" if de else "Solution 980 °C, age 720/620 °C"), "kind": "age718",
                    "steps": [{"name": "Lösungsglühen" if de else "solution treat", "T": 980, "t": 1.0},
                              {"name": "Abkühlen" if de else "cool", "T": 20, "t": 0.0, "quench": True},
                              {"name": "Auslagern 1" if de else "age 1", "T": 720, "t": 8.0},
                              {"name": "Auslagern 2" if de else "age 2", "T": 620, "t": 8.0},
                              {"name": "Abkühlen" if de else "cool", "T": 20, "t": 0.0}]})
    elif r.get("typ") == "metall" and (r.get("kaltverformt") or str(r.get("zustand", "")).upper().startswith("H")):
        Tr = {"cu": 400, "cuzn": 500, "cusn": 550, "mg-az": 345}.get(rule, 350)
        out.append({"id": "rx", "name": (f"Rekristallisationsglühen {Tr} °C / 1 h" if de else f"Recrystallisation anneal {Tr} °C / 1 h"), "kind": "rx",
                    "steps": [{"name": "Glühen" if de else "anneal", "T": Tr, "t": 1.0}, {"name": "Abkühlen" if de else "cool", "T": 20, "t": 0.0}]})
    return out


STEP_NAMES = [("Austenitisieren", "austenitise"), ("Abschrecken", "quench"), ("Anlassen", "temper"), ("Abkühlen", "cool"),
              ("Lösungsglühen", "solution treat"), ("Kaltauslagern", "natural ageing"), ("Warmauslagern", "artificial ageing"),
              ("Auslagern 1", "age 1"), ("Auslagern 2", "age 2"), ("Glühen", "anneal")]


def _step_name(name: str, de: bool) -> str:
    """Namen der vorgeschlagenen Schritte in der Sprache des Berichts (eigene Namen bleiben, wie sie sind)."""
    n = str(name or "").strip()
    for d, e in STEP_NAMES:
        if n.lower() in (d.lower(), e.lower()):
            return d if de else e
    return n


def temper(mid: str, steps: list[dict], lang: str = "de", seed: int = 1, kind: str | None = None) -> dict:
    """Zustände entlang eines Wärmebehandlungswegs: Profil T(t) und Bilder am Ende jedes Abschnitts (bei langen
    Haltezeiten zusätzlich nach 10 % und 30 % der Zeit)."""
    de = lang != "en"
    r = record(mid)
    rule = r.get("regel")
    if not steps:
        raise StructError("Keine Schritte angegeben")
    if len(steps) > 8:
        raise StructError("Höchstens 8 Schritte")
    steps = [{**s, "name": _step_name(s.get("name", ""), de)} for s in steps]
    kind = kind or ("qt" if rule == "stahl" else "age" if rule in AL and "peak" in AL.get(rule, {}) else
                    "age718" if rule == "ni-718" else "rx")
    prof = [[0.0, 20.0]]
    t = 0.0
    frames = []
    seed_f = seed
    # Ausgangszustand
    frames.append({"t": 0.0, "T": 20.0, "label": "Ausgangszustand" if de else "initial state", **_frame(mid, 20.0, None, lang, seed_f)})
    keys = [_initial_gef_state(r, kind)]           # Gefügezustand je Schlüsselbild als (Umwandlung, Fortschritt)
    crit = None
    if kind == "qt":
        from . import steel as STL
        zus = r.get("zus") or {}
        crit = STL.composition_report({k2: zus.get(k2, 0.0) for k2 in ("C", "Si", "Mn", "Cr", "Mo", "V", "Ni", "Cu", "B")})
    austenitised = False
    solutioned = False
    quenched = False
    age_hist: list = []
    Tt_hist = None
    rx = False
    for k, s in enumerate(steps):
        Ts = float(s["T"])
        th = max(float(s.get("t", 0) or 0), 0.0)
        if not -50 <= Ts <= 1400:
            raise StructError("Temperaturen zwischen −50 und 1400 °C angeben")
        if not 0 <= th <= 10000:
            raise StructError("Haltezeit zwischen 0 und 10 000 h")
        ramp = 0.02 if s.get("quench") else max(0.1, abs(Ts - prof[-1][1]) / 600)
        t += ramp
        prof.append([round(t, 4), Ts])
        subs = [th] if th <= 2 else [0.1 * th, 0.3 * th, th]
        t_start = t
        for sub in subs:
            # Zustand am Ende des Teilschritts
            hist = None
            if kind == "qt":
                from . import steel as STL
                zus = r.get("zus") or {}
                Ac1 = STL.composition_report({k2: zus.get(k2, 0.0) for k2 in ("C", "Si", "Mn", "Cr", "Mo", "V", "Ni", "Cu", "B")})["Ac1"]
                if Ts >= Ac1 + 20:
                    austenitised, quenched, Tt_hist = True, False, None
                elif s.get("quench") and austenitised:
                    quenched = True
                    austenitised = False
                elif quenched and Ts > 60 and sub > 0:
                    Tt_hist = (Ts, sub) if not Tt_hist or Ts >= Tt_hist[0] else Tt_hist
                if quenched:
                    hist = {"kind": "qt", "Tt": Tt_hist[0], "tt": Tt_hist[1]} if Tt_hist else {"kind": "quenched"}
                else:
                    hist = {"kind": "normal"}
            elif kind == "age":
                a = AL[rule]
                if Ts >= a["solvus"]:
                    solutioned, age_hist = True, []
                elif solutioned and not s.get("quench") and sub > 0:
                    age_hist = [x for x in age_hist if x[2] != k] + [(Ts, sub, k)]
                hist = [(x[0], x[1]) for x in age_hist] if solutioned else None
            elif kind == "age718":
                if Ts >= 950:
                    solutioned, age_hist = True, []
                elif solutioned and 600 <= Ts <= 800 and sub > 0:
                    age_hist.append((Ts, sub))
                hist = {"kind": "age"} if age_hist else {"kind": "solution"}
            else:
                if Ts >= {"cu": 250, "cuzn": 350, "cusn": 400}.get(rule, 300) and sub >= 0.1:
                    rx = True
                hist = {"kind": "rx"} if rx else None
            T_view = Ts if sub > 0 or s.get("quench") else Ts
            frame = _frame(mid, T_view, (kind, hist), lang, seed_f)
            lab = s.get("name") or f"{k + 1}"
            if len(subs) > 1:
                lab += f" ({sub:.3g} h)" if not de else f" ({sub:.3g} h)".replace(".", ",")
            frames.append({"t": round(t_start + sub, 4), "T": Ts, "label": lab, **frame})
            ks = None
            if kind == "qt":
                if austenitised:
                    ks = ("austenitisieren", float(min(1.0, max(0.0, (Ts - crit["Ac1"]) / max(crit["Ac3"] - crit["Ac1"], 1.0)))))
                elif quenched:
                    ks = ("anlassen", _hj_progress(*Tt_hist)) if Tt_hist else ("martensit", 1.0)
                else:
                    ks = ("perlit", 1.0)
            elif kind == "age" and keys[0]:
                ks = ("ausscheidung", _age_progress(rule, age_hist, de)) if solutioned else keys[0]
            elif kind == "rx" and keys[0]:
                ks = ("rekristallisation", 0.8) if rx else keys[0]
            keys.append(ks)
        t += th
        prof.append([round(t, 4), Ts])
    frames = _with_inter_frames(frames, keys, prof, r, seed_f, de, crit)
    return {"material": mid, "kind": kind, "profile": prof, "frames": frames, "steps": steps,
            "refs_keys": list(dict.fromkeys(sum((f["refs_keys"] for f in frames), [])))}


# ---------------------------------------------------------------- Zwischenbilder (Gefüge aus werk.gefuege)
N_INTER = 6          # Zwischenbilder zwischen zwei Schlüsselbildern
RX_RULES = ("cu", "cuzn", "cusn", "al-1xxx", "al-3xxx")


def _state_caption(sk: dict, C: float, de: bool) -> str:
    """Beschreibung eines erreichten Zustands: Text des Gefügebestandteils aus dem Atlas, sonst der Text der
    Umwandlung an dieser Stelle."""
    from . import gefuege as GF
    inf = sk.get("info") or {}
    tid, f = inf.get("tid"), float(inf.get("f", 0))
    cid = None
    if tid == "perlit" and f >= 0.999:
        cid = "ferrit" if C < 0.03 else "zementitnetz" if C > 0.85 else "perlit" if C >= 0.7 else "ferrit_perlit"
    elif tid == "austenitisieren" and f >= 0.999:
        cid = "austenit"
    elif tid == "martensit" and f >= 0.999:
        cid = "martensit_platte" if C > 0.8 else "martensit_latte"
    elif tid == "anlassen" and f >= 0.3:
        cid = "martensit_angelassen"
    elif tid == "ausscheidung":
        cid = "al_mk" if f < 0.1 else "al_gp" if f < 0.4 else "al_theta_strich" if f < 0.8 else "al_ueberaltert"
    elif tid == "rekristallisation":
        cid = "kaltverformt" if f < 0.1 else "rekristallisiert" if f >= 0.7 else None
    if cid and cid in GF.CONSTITUENTS:
        i = GF.info(cid, de)
        return f"{i['name']}: {i['what']}"
    return inf.get("caption", "")


def _lib_gefuege(out: dict, r: dict, T: float, de: bool, seed: int) -> None:
    """Gefügeskizze der Bibliothek (werk.gefuege) für Stähle, Al–Cu und kaltverformte Metalle: dieselbe Geometrie
    wie in der Wärmebehandlung, damit Temperaturregler, Wärmebehandlung und Atlas zusammenpassen."""
    from . import gefuege as GF
    rule = r.get("regel")
    zus = r.get("zus") or {}
    sk = None
    try:
        if rule == "stahl":
            from . import steel as STL
            C = float(zus.get("C", 0.2))
            if T >= 1350:
                return
            crit = STL.composition_report({k: zus.get(k, 0.0) for k in ("C", "Si", "Mn", "Cr", "Mo", "V", "Ni", "Cu", "B")})
            if T >= crit["Ac3"]:
                sk = GF.steel_state(C, "austenit", 1.0, seed, de)
            elif T >= crit["Ac1"]:
                fp = min(C / 0.76, 1.0)
                f = fp + (1 - fp) * (T - crit["Ac1"]) / max(crit["Ac3"] - crit["Ac1"], 1.0)
                sk = GF.steel_state(C, "ab", f, seed, de)
            else:
                tid, f = _initial_gef_state(r, "qt")
                par = {"C": C} if tid in ("perlit", "martensit") else {"C": min(C, 0.6)}
                sk = GF.transition(tid, f, seed, de, **par)
        elif rule == "al-2xxx":
            ks = ("ausscheidung", 0.0) if T >= AL[rule]["solvus"] else _initial_gef_state(r, "age")
            sk = GF.transition(*ks, seed, de)
        elif rule in RX_RULES and (r["kaltverformt"] if "kaltverformt" in r else str(r.get("zustand", "")).upper().startswith(("H", "R2", "R3", "R4"))):
            if T < {"cu": 250, "cuzn": 350, "cusn": 400}.get(rule, 300):
                sk = GF.transition("rekristallisation", 0.0, seed, de)
    except (KeyError, ValueError, StructError):          # Bibliothek deckt den Fall nicht: eigene Skizze bleibt
        return
    if not sk:
        return
    for p in out["panels"]:
        if p.get("id") == "gefuege":
            p["sketch"] = sk
            p["caption"] = _state_caption(sk, float(zus.get("C", 0.2)), de) + (" Schematisch, nicht massstäblich." if de else " Schematic, not to scale.")
            p["refs"] = list(dict.fromkeys(list(p.get("refs") or []) + list(GF.TRANSITIONS[sk["info"]["tid"]]["refs"])))
            out["refs"] = list(dict.fromkeys(list(out["refs"]) + p["refs"]))
            break


def _hj_progress(Tt: float, th: float) -> float:
    """Anlassfortschritt 0…1 aus der gleichwertigen 1-h-Anlasstemperatur (Hollomon–Jaffe, 80…650 °C)."""
    return round(min(1.0, max(0.0, (steel_stage(Tt, th)[1] - 80.0) / 570.0)), 4)


def _age_progress(rule: str, hist: list, de: bool) -> float:
    """Fortschritt der Ausscheidungsfolge aus dem Verhältnis t_eq/t_peak (log. interpoliert): 0,03 übersättigt,
    0,2 GP-Zonen, 0,6 Höchsthärte, 0,85 überaltert, 1 Gleichgewicht."""
    if not hist:
        return 0.03
    st = age_state(rule, [(x[0], x[1]) for x in hist], de)
    if st["teq"] <= 0:
        return 0.2 if st["key"] == "gp" else 0.03
    lr = math.log10(max(st["ratio"], 1e-4))
    return round(float(np.interp(lr, [-3, -1.3, -0.5, 0.0, 0.5, 1.7, 3.0], [0.05, 0.2, 0.45, 0.6, 0.7, 0.85, 1.0])), 4)


def _initial_gef_state(r: dict, kind: str):
    """Gefüge des Lieferzustands als (Umwandlung, Fortschritt); None, wenn die Bibliothek ihn nicht abbildet."""
    z = str(r.get("zustand", "")).upper()
    if kind == "qt":
        if z.startswith("QT") or "VERG" in z:
            return ("anlassen", _hj_progress(600, 1.0))
        if z in ("Q", "GEHAERTET"):
            return ("martensit", 1.0)
        return ("perlit", 1.0)
    if kind == "age" and r.get("regel") == "al-2xxx":       # die Ausscheidungsfolge ist die von Al–Cu
        h = temper_hist(r.get("zustand", ""), r["regel"])
        return ("ausscheidung", _age_progress(r["regel"], [(a, b, 0) for a, b in h] if h else [], True)) if h is not None else ("ausscheidung", 0.03)
    if kind == "rx" and (r.get("kaltverformt") or z.startswith("H")):
        return ("rekristallisation", 0.0)
    return None


def _with_inter_frames(frames: list, keys: list, prof: list, r: dict, seed: int, de: bool, crit: dict | None = None) -> list:
    """Setzt in die Schlüsselbilder das Gefüge der Bibliothek (gleiche Geometrie für alle Bilder eines Seeds) und
    fügt zwischen zwei Zuständen Zwischenbilder der Umwandlung ein (eigenes Gefüge, übrige Ansichten vom
    näheren Schlüsselbild). Die Zwischenbilder liegen dort auf dem Weg, wo die Umwandlung abläuft: Austenit über
    Ac1, Martensit unter Ms (Koistinen–Marburger), Anlassen über 100 °C, Auflösen und Rekristallisation über
    300 bzw. 200 °C."""
    from . import gefuege as GF
    if not any(keys):
        return frames
    C = float((r.get("zus") or {}).get("C", 0.45))
    tp = [p[0] for p in prof]
    TT = [p[1] for p in prof]
    Ms = float(crit["Ms"]) if crit else 300.0
    start = {"austenitisieren": (lambda T: T >= crit["Ac1"]) if crit else (lambda T: T >= 700),
             "martensit": lambda T: T <= Ms, "anlassen": lambda T: T >= 100,
             "rekristallisation": lambda T: T >= 200}

    def window(tid, ta, tb, back):
        """Beginn der Umwandlung im Abschnitt [ta, tb]: erster Zeitpunkt, an dem die Bedingung erfüllt ist."""
        cond = (lambda T: T >= 300) if tid == "ausscheidung" and back else start.get(tid)
        if cond is None or tb <= ta:
            return ta
        ts = np.linspace(ta, tb, 400)
        hit = next((x for x in ts if cond(float(np.interp(x, tp, TT)))), None)
        return float(hit) if hit is not None and hit < tb else ta

    def km(T):
        return 1.0 - math.exp(-0.011 * max(Ms - T, 0.0))

    def sk_of(tid, f):
        par = {"C": C} if tid in ("perlit", "austenitisieren", "martensit") else {"C": min(C, 0.6)} if tid == "anlassen" else {}
        return GF.transition(tid, f, seed, de, **par)

    def panel(sk):
        return {"kind": "sketch", "id": "gefuege", "title": "Gefüge" if de else "Microstructure", "sketch": sk,
                "caption": sk["info"]["caption"]}

    out = []
    for i, fr in enumerate(frames):
        ks = keys[i] if i < len(keys) else None
        if i > 0 and ks and keys[i - 1] is not None:
            tid, fb = ks
            pa = keys[i - 1]
            f0 = pa[1] if pa[0] == tid else 0.0
            if abs(fb - f0) > 1e-3 or pa[0] != tid:
                ta, tb = frames[i - 1]["t"], fr["t"]
                ta = window(tid, ta, tb, fb < f0)
                name = GF.TRANSITIONS[tid]["name"][0 if de else 1]
                T_end = float(np.interp(tb, tp, TT))
                for p in GF.frame_positions(N_INTER + 2)[1:-1]:
                    tt = ta + (tb - ta) * p
                    Tp = float(np.interp(tt, tp, TT))
                    if tid == "martensit" and km(T_end) > 0:
                        f = f0 + (fb - f0) * min(km(Tp) / km(T_end), 1.0)
                    else:
                        f = f0 + (fb - f0) * p
                    sk = sk_of(tid, f)
                    lab = f"{name} · {round(sk['info']['frac'] * 100):d} %"
                    out.append({"t": round(tt, 4), "T": round(Tp, 1), "label": lab,
                                "caption": sk["info"]["caption"], "statements": [sk["info"]["caption"]],
                                "panels": [panel(sk)], "base": None, "near": i - 1 if p < 0.5 else i, "inter": True,
                                "refs_keys": list(GF.TRANSITIONS[tid]["refs"])})
        if ks:
            sk = sk_of(*ks)
            ps = fr.get("panels") or []
            j = next((k for k, p in enumerate(ps) if p.get("id") == "gefuege"), None)
            if j is None:
                ps = [panel(sk)] + ps
            else:
                ps = ps[:j] + [{**ps[j], "sketch": sk, "caption": _state_caption(sk, C, de)}] + ps[j + 1:]
            fr = {**fr, "panels": ps, "refs_keys": list(dict.fromkeys(fr.get("refs_keys", []) + list(GF.TRANSITIONS[ks[0]]["refs"])))}
        fr["key"] = i
        out.append(fr)
    # Index der Schlüsselbilder in der neuen Folge
    pos = {f["key"]: n for n, f in enumerate(out) if not f.get("inter")}
    for f in out:
        if f.get("inter"):
            f["base"] = pos[f.pop("near")]
        f.pop("key", None)
    return out


def _frame(mid: str, T: float, hist, lang: str, seed: int) -> dict:
    """Ein Bild der Animation: die wichtigsten Ansichten bei T nach der Vorgeschichte."""
    r = record(mid)
    de = lang != "en"
    rng = np.random.default_rng(seed)
    kind, h = hist if hist else (None, None)
    if r.get("typ") != "metall":
        b = build(mid, T, lang, seed, n=4)
        return {"panels": b["panels"][:3], "statements": b["statements"], "refs_keys": b["refs_keys"]}
    if kind == "age" and r.get("regel") in AL:
        if h is None:
            out = _metal(mid, r, T, de, rng, hist_override=temper_hist(r.get("zustand", ""), r["regel"]), n=4)
        else:
            out = _metal(mid, r, T, de, rng, hist_override=h if h else [], n=4)
    elif kind == "age718":
        rr = dict(r)
        rr["zustand"] = "ausgehaertet" if (h or {}).get("kind") == "age" else "geglueht"
        out = _metal(mid, rr, T, de, rng, hist_override=h, n=4)
    elif kind == "rx":
        rr = dict(r)
        if h and h.get("kind") == "rx":
            rr["kaltverformt"] = False
            rr["zustand"] = "O"
        out = _metal(mid, rr, T, de, rng, n=4)
    else:
        out = _metal(mid, r, T, de, rng, hist_override=h, n=4)
    return {"panels": out["panels"], "statements": out["statements"], "refs_keys": list(dict.fromkeys(out["refs"]))}
