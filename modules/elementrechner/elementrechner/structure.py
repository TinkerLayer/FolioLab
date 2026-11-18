"""Strukturbild als Vektorgrafik (ER-402).

Gezeichnet wird aus den 2D-Koordinaten des Molfiles (V2000), das der Editor (OpenChemLib JS) liefert – mit
matplotlib, ohne Zusatzpaket. Kohlenstoff ohne Ladung bleibt unbeschriftet (Skelettformel); Heteroatome, geladene
Atome und isolierte Atome bekommen ihr Symbol mit implizitem Wasserstoff und Ladung. Keil- und Strichbindungen
werden als Keil bzw. gestrichelt gezeichnet.
"""
from __future__ import annotations

import math

# übliche Wertigkeiten ohne Ladung; mit Ladung: N⁺ 4, O⁻ 1 usw. (isoelektronisch)
VALENCE = {"C": 4, "N": 3, "O": 2, "S": 2, "P": 3, "B": 3, "F": 1, "Cl": 1, "Br": 1, "I": 1, "Si": 4, "Se": 2, "H": 1}
_OLD_CHG = {1: 3, 2: 2, 3: 1, 4: 0, 5: -1, 6: -2, 7: -3}


class MolfileError(ValueError):
    pass


def parse_molfile(text: str) -> dict:
    """V2000-Molfile -> {atoms: [{el, x, y, charge, iso}], bonds: [{a, b, order, stereo}]}."""
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    idx = next((i for i, ln in enumerate(lines) if "V2000" in ln), None)
    if idx is None:
        raise MolfileError("Kein Molfile (V2000) – Strukturbild nicht möglich")
    cl = lines[idx]
    try:
        na, nb = int(cl[0:3]), int(cl[3:6])
    except ValueError as e:
        raise MolfileError("Molfile: Zählzeile unlesbar") from e
    atoms, bonds = [], []
    for ln in lines[idx + 1: idx + 1 + na]:
        try:
            x, y = float(ln[0:10]), float(ln[10:20])
        except ValueError as e:
            raise MolfileError("Molfile: Atomzeile unlesbar") from e
        el = ln[31:34].strip()
        chg = int(ln[36:39]) if len(ln) >= 39 and ln[36:39].strip() else 0
        atoms.append({"el": el, "x": x, "y": y, "charge": _OLD_CHG.get(chg, 0), "iso": None})
    for ln in lines[idx + 1 + na: idx + 1 + na + nb]:
        try:
            a, b, o = int(ln[0:3]), int(ln[3:6]), int(ln[6:9])
        except ValueError as e:
            raise MolfileError("Molfile: Bindungszeile unlesbar") from e
        st = int(ln[9:12]) if len(ln) >= 12 and ln[9:12].strip() else 0
        bonds.append({"a": a - 1, "b": b - 1, "order": o, "stereo": st})
    for ln in lines[idx + 1 + na + nb:]:
        if ln.startswith("M  END"):
            break
        if ln.startswith("M  CHG") or ln.startswith("M  ISO"):
            f = ln[6:].split()
            n = int(f[0])
            for k in range(n):
                ai, v = int(f[1 + 2 * k]) - 1, int(f[2 + 2 * k])
                atoms[ai]["charge" if ln.startswith("M  CHG") else "iso"] = v
    if not atoms:
        raise MolfileError("Molfile ohne Atome")
    return {"atoms": atoms, "bonds": bonds}


def implicit_h(mol: dict, i: int) -> int:
    a = mol["atoms"][i]
    v = VALENCE.get(a["el"])
    if v is None:
        return 0
    q = a["charge"]
    if a["el"] in ("N", "P", "O", "S", "Se"):
        v += q                                   # N⁺ 4, O⁺ 3, O⁻ 1, N⁻ 2
    elif a["el"] in ("C", "Si", "B"):
        v -= abs(q)                              # Carbokation/-anion 3
    else:
        v -= abs(q)
    used = sum(min(b["order"], 3) if b["order"] in (1, 2, 3) else 1.5
               for b in mol["bonds"] if i in (b["a"], b["b"]))
    return max(0, int(round(v - used)))


def label(mol: dict, i: int) -> str | None:
    """Beschriftung eines Atoms (matplotlib-mathtext) oder None (Skelett-C)."""
    a = mol["atoms"][i]
    deg = sum(1 for b in mol["bonds"] if i in (b["a"], b["b"]))
    if a["el"] == "C" and not a["charge"] and deg and not a["iso"]:
        return None
    h = implicit_h(mol, i)
    s = a["el"]
    if a["iso"]:
        s = f"$^{{{a['iso']}}}$" + s
    if h:
        s += "H" + (f"$_{{{h}}}$" if h > 1 else "")
    q = a["charge"]
    if q:
        s += "$^{" + (str(abs(q)) if abs(q) > 1 else "") + ("+" if q > 0 else "-") + "}$"
    return s.replace("$$", "")


def draw(molfile: str, ax=None, scale_in: float = 0.45):
    """Strukturbild zeichnen; gibt die Figur zurück (Vektor, wenn als PDF gespeichert)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon

    mol = parse_molfile(molfile)
    A = mol["atoms"]
    xs, ys = [a["x"] for a in A], [a["y"] for a in A]
    lens = [math.dist((A[b["a"]]["x"], A[b["a"]]["y"]), (A[b["b"]]["x"], A[b["b"]]["y"])) for b in mol["bonds"]]
    L = sorted(lens)[len(lens) // 2] if lens else 1.0
    w = (max(xs) - min(xs)) / L + 1.2
    h = (max(ys) - min(ys)) / L + 1.2
    fig = None
    if ax is None:
        fig, ax = plt.subplots(figsize=(min(6.0, max(1.2, w * scale_in)), min(5.0, max(1.0, h * scale_in))))
    labels = [label(mol, i) for i in range(len(A))]
    lw = 1.3
    for b in mol["bonds"]:
        p, q = A[b["a"]], A[b["b"]]
        x1, y1, x2, y2 = p["x"], p["y"], q["x"], q["y"]
        dx, dy = x2 - x1, y2 - y1
        d = math.hypot(dx, dy) or 1.0
        ux, uy = dx / d, dy / d
        s1 = 0.28 * L if labels[b["a"]] else 0.0           # Platz für die Beschriftung
        s2 = 0.28 * L if labels[b["b"]] else 0.0
        x1, y1, x2, y2 = x1 + ux * s1, y1 + uy * s1, x2 - ux * s2, y2 - uy * s2
        nx, ny = -uy, ux
        if b["stereo"] == 1:                                # Keil (nach vorn)
            wd = 0.09 * L
            ax.add_patch(Polygon([(x1, y1), (x2 + nx * wd, y2 + ny * wd), (x2 - nx * wd, y2 - ny * wd)],
                                 closed=True, color="black", lw=0))
            continue
        if b["stereo"] == 6:                                # Strichkeil (nach hinten)
            for k in range(1, 7):
                t = k / 6
                wd = 0.09 * L * t
                cx, cy = x1 + dx * t * (1 - (s1 + s2) / d), y1 + dy * t * (1 - (s1 + s2) / d)
                ax.plot([cx + nx * wd, cx - nx * wd], [cy + ny * wd, cy - ny * wd], color="black", lw=0.9)
            continue
        offs = {1: [0.0], 2: [-0.07, 0.07], 3: [-0.11, 0.0, 0.11]}.get(b["order"], [-0.07, 0.07])
        for k, o in enumerate(offs):
            ls = "--" if b["order"] == 4 and k == 1 else "-"
            ax.plot([x1 + nx * o * L, x2 + nx * o * L], [y1 + ny * o * L, y2 + ny * o * L], color="black", lw=lw,
                    ls=ls, solid_capstyle="round")
    for a, lab in zip(A, labels):
        if lab:
            col = {"O": "#c0392b", "N": "#1f4fbf", "S": "#a07800", "Cl": "#1d8a3a", "F": "#1d8a3a", "Br": "#8b3a1d",
                   "P": "#c06000"}.get(a["el"], "black")
            ax.text(a["x"], a["y"], lab, ha="center", va="center", fontsize=11, color=col)
    ax.set_aspect("equal")
    ax.set_xlim(min(xs) - 0.6 * L, max(xs) + 0.6 * L)
    ax.set_ylim(min(ys) - 0.6 * L, max(ys) + 0.6 * L)
    ax.axis("off")
    return fig if fig is not None else ax.figure
