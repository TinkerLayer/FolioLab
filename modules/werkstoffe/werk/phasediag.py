"""Binäre Phasendiagramme: schematische Lehrdiagramme aus zitierten Punkten und berechnete Diagramme (ideale und
reguläre Lösung), Hebelgesetz, Gefügebestandteile, Abkühlpfad.

Hebelgesetz (Callister, Kap. 9): im Zweiphasengebiet liegen die Phasenzusammensetzungen an den Enden der waagrechten
Konode; Anteil der linken Phase W_l = (x_r − x₀)/(x_r − x_l), der rechten W_r = (x₀ − x_l)/(x_r − x_l).

Berechnete Diagramme (Porter & Easterling, Kap. 1): Gibbs-Energie je Mol der Mischung, bezogen auf die reinen
festen Komponenten,
    G_S(x) = RT [x ln x + (1−x) ln(1−x)] + Ω_S x(1−x)
    G_L(x) = (1−x) ΔH_A (1 − T/T_A) + x ΔH_B (1 − T/T_B) + RT [x ln x + (1−x) ln(1−x)] + Ω_L x(1−x)
(ΔC_p der Schmelzumwandlung vernachlässigt). Die stabilen Phasen folgen aus der unteren konvexen Hülle beider Kurven
(gemeinsame Tangente). x ist der Stoffmengenanteil von B; Angaben in Gew.-% werden mit den Molmassen umgerechnet.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parent / "data"
R = 8.314462618
REFS = ["callister"]
REFS_MODEL = ["porter"]


class DiagramError(ValueError):
    pass


GROUPS = {"lehre": ("Lehrsysteme", "Teaching systems"), "al": ("Aluminium", "Aluminium"),
          "cu": ("Kupfer", "Copper"), "fe": ("Eisen und Stahl", "Iron and steel"), "ni": ("Nickel", "Nickel"),
          "ti": ("Titan", "Titanium"), "mg": ("Magnesium", "Magnesium"), "lot": ("Lote", "Solders"),
          "keramik": ("Keramik", "Ceramics")}


def _catmull(pts, n=8):
    """Centripetale Catmull-Rom-Kurve durch alle Punkte (läuft durch jeden zitierten Punkt, ohne Schleifen)."""
    P = [tuple(map(float, p)) for p in pts]
    if len(P) < 3:
        return [list(p) for p in P]
    ext = [(2 * P[0][0] - P[1][0], 2 * P[0][1] - P[1][1]), *P, (2 * P[-1][0] - P[-2][0], 2 * P[-1][1] - P[-2][1])]
    out = [list(P[0])]

    def tj(ti, a, b, sx, sy):
        d = math.hypot((b[0] - a[0]) / sx, (b[1] - a[1]) / sy)
        return ti + max(d, 1e-9) ** 0.5

    xs = [p[0] for p in P]
    ys = [p[1] for p in P]
    sx = (max(xs) - min(xs)) or 1.0
    sy = (max(ys) - min(ys)) or 1.0
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        t0 = 0.0
        t1 = tj(t0, p0, p1, sx, sy)
        t2 = tj(t1, p1, p2, sx, sy)
        t3 = tj(t2, p2, p3, sx, sy)
        for k in range(1, n + 1):
            t = t1 + (t2 - t1) * k / n
            def lerp(a, b, ta, tb):
                return [(tb - t) / (tb - ta) * a[j] + (t - ta) / (tb - ta) * b[j] for j in (0, 1)]
            a1 = lerp(p0, p1, t0, t1)
            a2 = lerp(p1, p2, t1, t2)
            a3 = lerp(p2, p3, t2, t3)
            b1 = lerp(a1, a2, t0, t2)
            b2 = lerp(a2, a3, t1, t3)
            out.append(lerp(b1, b2, t1, t2))
    out[-1] = list(P[-1])
    return [[round(x, 5), round(y, 4)] for x, y in out]


def _expand(s: dict) -> dict:
    """Format 2: benannte Linien ("curves": {id: {"pts": [[x, T], …], "kind": "liquidus"|…, "smooth": true}}) werden zu
    dichten Kurven; Gebiete nennen sie in "poly" als "id" oder "-id" (umgekehrt) zwischen einzelnen Punkten. So
    stimmen Flächen, Hebelgesetz und gezeichnete Linien überein."""
    curves = s.get("curves") or {}
    dense = {}
    for cid, c in curves.items():
        pts = c["pts"] if isinstance(c, dict) else c
        smooth = c.get("smooth", True) if isinstance(c, dict) else True
        dense[cid] = _catmull(pts) if smooth else [list(map(float, p)) for p in pts]
    if not dense:
        return s
    out = dict(s)
    regs = []
    for r in s["regions"]:
        poly = []
        for item in r["poly"]:
            if isinstance(item, str):
                rev = item.startswith("-")
                seg = dense[item[1:] if rev else item]
                seg = seg[::-1] if rev else seg
                for p in seg:
                    if not poly or abs(poly[-1][0] - p[0]) > 1e-9 or abs(poly[-1][1] - p[1]) > 1e-9:
                        poly.append(list(p))
            else:
                if not poly or poly[-1] != list(item):
                    poly.append(list(item))
        if len(poly) > 2 and poly[0] == poly[-1]:
            poly.pop()
        regs.append({**r, "poly": poly})
    out["regions"] = regs
    out["lines"] = [{"id": cid, "kind": (c.get("kind") if isinstance(c, dict) else "") or "", "pts": dense[cid],
                     "label": (c.get("label") if isinstance(c, dict) else None)} for cid, c in curves.items()]
    return out


@lru_cache(maxsize=None)
def _data() -> dict:
    d = json.loads((DATA / "diagrams.json").read_text(encoding="utf-8"))
    d = {**d, "systeme": list(d["systeme"]), "quellen": dict(d.get("quellen") or {})}
    folder = DATA / "diagrams"
    for p in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        f = json.loads(p.read_text(encoding="utf-8"))
        d["quellen"].update(f.get("quellen") or {})
        for s in f.get("systeme") or ([f["system"]] if f.get("system") else []):
            d["systeme"] = [x for x in d["systeme"] if x["id"] != s["id"]] + [s]   # a file replaces a built-in system
    d["systeme"] = [_expand(s) for s in d["systeme"]]
    return d


def sources() -> dict:
    """Quellen, die mit den Diagrammdateien kommen (für refs.rec)."""
    return _data()["quellen"]


def systems(lang: str = "de") -> list[dict]:
    out = []
    for s in _data()["systeme"]:
        g = GROUPS.get(s.get("gruppe") or "lehre", GROUPS["lehre"])
        out.append({"id": s["id"], "name": s.get("name_en") if lang == "en" else s["name"], "kind": "schematic",
                    "q": s["q"], "group": g[1] if lang == "en" else g[0], "melt": True})
    for s in _data()["berechnet"]:
        out.append({"id": s["id"], "name": s.get("name_en") if lang == "en" else s["name"], "kind": "computed",
                    "q": s["q"], "group": "Modell" if lang != "en" else "Model"})
    return out


def validate(s: dict, n: int = 90) -> list[str]:
    """Prüft ein (expandiertes) schematisches Diagramm: Gebiete innerhalb der Grenzen, jeder Punkt des Rasters in genau
    einem Gebiet (Punkte nahe einer Grenze ausgenommen), Zweiphasengebiete mit zwei Phasen, Quellen bekannt.
    Gibt eine Liste von Problemen zurück (leer = in Ordnung)."""
    probs = []
    (x0, x1), (T0, T1) = s["xlim"], s["Tlim"]
    sx, sy = (x1 - x0), (T1 - T0)
    labels = [r["label"] for r in s["regions"]]
    if len(set(labels)) != len(labels):
        probs.append("doppelte Gebietsnamen")
    edges = []
    for r in s["regions"]:
        P = r["poly"]
        if len(P) < 3:
            probs.append(f"{r['label']}: weniger als 3 Punkte")
        for x, T in P:
            if not (x0 - 1e-6 * sx <= x <= x1 + 1e-6 * sx and T0 - 1e-6 * sy <= T <= T1 + 1e-6 * sy):
                probs.append(f"{r['label']}: Punkt ({x}, {T}) ausserhalb")
                break
        if not 1 <= len(r["phases"]) <= 2:
            probs.append(f"{r['label']}: {len(r['phases'])} Phasen")
        edges += [(P[i], P[(i + 1) % len(P)]) for i in range(len(P))]
    E = np.array([[a[0], a[1], b[0], b[1]] for a, b in edges], float)
    E[:, [0, 2]] = (E[:, [0, 2]] - x0) / sx
    E[:, [1, 3]] = (E[:, [1, 3]] - T0) / sy
    bad = {"gap": [], "overlap": []}
    for i in range(n):
        for j in range(n):
            u, v = (i + 0.5) / n, (j + 0.5) / n
            # Abstand zu allen Kanten (normiert)
            ax, ay, bx, by = E[:, 0], E[:, 1], E[:, 2], E[:, 3]
            dx, dy = bx - ax, by - ay
            L = dx * dx + dy * dy
            t = np.clip(((u - ax) * dx + (v - ay) * dy) / np.where(L > 0, L, 1), 0, 1)
            d = np.hypot(ax + t * dx - u, ay + t * dy - v).min()
            if d < 0.004:
                continue
            x, T = x0 + u * sx, T0 + v * sy
            hits = [r["label"] for r in s["regions"] if _inside(r["poly"], x, T)]
            if not hits:
                bad["gap"].append((round(x, 3), round(T, 1)))
            elif len(hits) > 1:
                bad["overlap"].append((round(x, 3), round(T, 1), tuple(hits)))
    if bad["gap"]:
        probs.append(f"{len(bad['gap'])} Rasterpunkte in keinem Gebiet, z. B. {bad['gap'][:3]}")
    if bad["overlap"]:
        probs.append(f"{len(bad['overlap'])} Rasterpunkte in mehreren Gebieten, z. B. {bad['overlap'][:3]}")
    from . import refs as RF
    for k in s.get("q") or []:
        if not RF.known(k):
            probs.append(f"Quelle {k} unbekannt")
    for inv in s.get("invariants") or []:
        if not (len(inv.get("x") or []) == 3 and inv["x"][0] <= inv["x"][1] <= inv["x"][2]):
            probs.append(f"invariante Reaktion bei {inv.get('T')}: x nicht [links, Mitte, rechts]")
    return probs


def system(sid: str) -> dict:
    for s in _data()["systeme"]:
        if s["id"] == sid:
            return s
    raise DiagramError(f"Phasendiagramm „{sid}“ unbekannt")


def preset(sid: str) -> dict:
    for s in _data()["berechnet"]:
        if s["id"] == sid:
            return dict(s)
    raise DiagramError(f"Modellsystem „{sid}“ unbekannt")


# ----------------------------------------------------------------------------- schematisch
def _inside(poly, x, T) -> bool:
    """Punkt im Polygon (Strahlverfahren); Punkte auf dem Rand zählen als innen."""
    n = len(poly)
    inside = False
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (min(x1, x2) - 1e-9 <= x <= max(x1, x2) + 1e-9 and min(y1, y2) - 1e-9 <= T <= max(y1, y2) + 1e-9):
            cross = (x2 - x1) * (T - y1) - (y2 - y1) * (x - x1)
            if abs(cross) <= 1e-9 * max(1.0, abs(x2 - x1) + abs(y2 - y1)) * 100:
                return True
        if (y1 > T) != (y2 > T):
            xi = x1 + (T - y1) * (x2 - x1) / (y2 - y1)
            if x < xi:
                inside = not inside
    return inside


def _cuts(poly, T) -> list[float]:
    xs = []
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if y1 == y2:
            if abs(y1 - T) < 1e-9:
                xs += [x1, x2]
            continue
        if min(y1, y2) - 1e-9 <= T <= max(y1, y2) + 1e-9:
            xs.append(x1 + (T - y1) * (x2 - x1) / (y2 - y1))
    return xs


def region_at(s: dict, x: float, T: float) -> dict | None:
    # Gebiete mit einer Phase zuletzt prüfen: Punkte auf einer Grenze gehören zum Zweiphasengebiet
    regs = sorted(s["regions"], key=lambda r: -len(r["phases"]))
    for r in regs:
        if _inside(r["poly"], x, T):
            return r
    return None


def lever(s: dict, x: float, T: float, lang: str = "de") -> dict:
    """Phasen, ihre Zusammensetzungen und Anteile am Punkt (x, T) eines schematischen Diagramms."""
    lo, hi = s["xlim"]
    if not (lo <= x <= hi):
        raise DiagramError(f"Zusammensetzung ausserhalb {lo}–{hi}")
    r = region_at(s, x, T)
    if r is None:
        raise DiagramError("Punkt liegt ausserhalb des Diagramms")
    for inv in s.get("invariants", []):
        if abs(T - inv["T"]) < 1e-9 and inv["x"][0] <= x <= inv["x"][2]:
            return {"region": r["label"], "phases": [], "invariant": inv["reaction"], "T": T, "x": x,
                    "note": ("Auf der invarianten Linie sind die Anteile unbestimmt; etwas darüber oder darunter wählen."
                             if lang == "de" else "On the invariant line the fractions are undetermined; choose a "
                             "temperature slightly above or below.")}
    if len(r["phases"]) == 1:
        return {"region": r["label"], "phases": [{"name": r["phases"][0], "x": x, "frac": 1.0}], "T": T, "x": x}
    cuts = _cuts(r["poly"], T)
    xl, xr = min(cuts), max(cuts)
    # Verbindung ausserhalb des gezeichneten Bereichs (z. B. Al₆Mn bei 25,3 Gew.-% in einem Diagramm bis 10 %):
    # ihre wahre Zusammensetzung statt des Diagrammrands
    px = r.get("phase_x") or {}
    if r["phases"][0] in px:
        xl = float(px[r["phases"][0]])
    if r["phases"][1] in px:
        xr = float(px[r["phases"][1]])
    if xr - xl < 1e-12:
        return {"region": r["label"], "phases": [{"name": r["phases"][0], "x": x, "frac": 1.0}], "T": T, "x": x}
    wl = (xr - x) / (xr - xl)
    return {"region": r["label"], "T": T, "x": x, "tie": [xl, xr],
            "phases": [{"name": r["phases"][0], "x": xl, "frac": wl}, {"name": r["phases"][1], "x": xr, "frac": 1 - wl}]}


def constituents(s: dict, x: float, lang: str = "de") -> list[dict]:
    """Gefügebestandteile knapp unter jeder eutektischen/eutektoiden Linie, deren Bereich x enthält
    (Callister Gl. 9.10–9.11 bzw. 9.20–9.23 in allgemeiner Form)."""
    out = []
    for inv in s.get("invariants", []):
        if inv["type"] not in ("eutectic", "eutectoid") or "constituents" not in inv:
            continue
        xl, xe, xr = inv["x"]
        names = inv.get("constituents_en") if lang == "en" else inv["constituents"]
        if not (xl < x < xr):
            continue
        if x <= xe:
            prim = (xe - x) / (xe - xl)
            parts = [{"name": names[0], "frac": prim}, {"name": names[1], "frac": 1 - prim}]
        else:
            prim = (x - xe) / (xr - xe)
            parts = [{"name": names[2], "frac": prim}, {"name": names[1], "frac": 1 - prim}]
        out.append({"T": inv["T"], "reaction": inv["reaction"], "parts": parts})
    return out


def cooling(s: dict, x: float, dT: float = 1.0, lang: str = "de") -> dict:
    """Abkühlung bei fester Zusammensetzung: Übergänge (Temperatur, Gebiet vorher → nachher) und Phasenanteile
    über der Temperatur."""
    T0, T1 = s["Tlim"][1], s["Tlim"][0]
    Ts = np.arange(T0, T1 - 1e-9, -abs(dT))
    events, curve = [], {}
    last = None
    for T in Ts:
        r = region_at(s, x, float(T))
        lab = r["label"] if r else None
        if last is not None and lab != last:
            # Übergang genauer eingrenzen (Bisektion)
            a, b = float(T) + dT, float(T)
            for _ in range(30):
                m = 0.5 * (a + b)
                rm = region_at(s, x, m)
                if (rm["label"] if rm else None) == last:
                    a = m
                else:
                    b = m
            events.append({"T": 0.5 * (a + b), "from": last, "to": lab})
        last = lab
        try:
            lv = lever(s, x, float(T), lang)
        except DiagramError:
            continue
        for ph in lv["phases"]:
            curve.setdefault(ph["name"], {})[float(T)] = ph["frac"]
    names = list(curve)
    series = [{"name": n, "T": [float(t) for t in Ts], "frac": [curve[n].get(float(t), 0.0) for t in Ts]} for n in names]
    return {"events": events, "series": series}


# ----------------------------------------------------------------------------- berechnet (ideal/regulär)
def _mix(x, T):
    return R * T * (x * np.log(x) + (1 - x) * np.log(1 - x))


def gibbs(p: dict, T_K: float, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(G_S, G_L) in J/mol bei T [K] auf dem Raster x."""
    TA, TB = p["TmA"] + 273.15, p["TmB"] + 273.15
    gA = p["HA"] * 1e3 * (1 - T_K / TA)
    gB = p["HB"] * 1e3 * (1 - T_K / TB)
    mix = _mix(x, T_K)
    GS = mix + p.get("omega_S", 0) * 1e3 * x * (1 - x)
    GL = (1 - x) * gA + x * gB + mix + p.get("omega_L", 0) * 1e3 * x * (1 - x)
    return GS, GL


def _hull(xs, gs, ph):
    """Untere konvexe Hülle (monotone Kette) über Punkte (x, G, Phase), nach x sortiert."""
    order = np.lexsort((gs, xs))
    H: list[int] = []
    for i in order:
        while len(H) >= 2:
            x1, y1 = xs[H[-2]], gs[H[-2]]
            x2, y2 = xs[H[-1]], gs[H[-1]]
            if (x2 - x1) * (gs[i] - y1) - (y2 - y1) * (xs[i] - x1) <= 0:
                H.pop()
            else:
                break
        if H and abs(xs[H[-1]] - xs[i]) < 1e-15:
            continue
        H.append(int(i))
    return H


def equilibrium(p: dict, T_C: float, n: int = 1201) -> list[dict]:
    """Stabile Bereiche bei T: [{"kind": "one", "phase", "x0", "x1"} | {"kind": "two", "phases", "x": [xl, xr]}]."""
    T = T_C + 273.15
    x = np.linspace(1e-6, 1 - 1e-6, n)
    GS, GL = gibbs(p, T, x)
    xs = np.r_[x, x]
    gs = np.r_[GS, GL]
    ph = np.r_[np.zeros(n, int), np.ones(n, int)]
    H = _hull(xs, gs, ph)
    dx = x[1] - x[0]
    segs: list[dict] = []
    names = ["S", "L"]
    for a, b in zip(H[:-1], H[1:]):
        if xs[b] - xs[a] > 1.5 * dx or ph[a] != ph[b]:
            segs.append({"kind": "two", "phases": [names[ph[a]], names[ph[b]]], "x": [float(xs[a]), float(xs[b])]})
        else:
            if segs and segs[-1]["kind"] == "one" and segs[-1]["phase"] == names[ph[a]]:
                segs[-1]["x1"] = float(xs[b])
            else:
                segs.append({"kind": "one", "phase": names[ph[a]], "x0": float(xs[a]), "x1": float(xs[b])})
    return segs


def wt_to_x(p, w):
    """Gew.-% B -> Stoffmengenanteil B."""
    w = np.asarray(w, float) / 100
    return (w / p["MB"]) / (w / p["MB"] + (1 - w) / p["MA"])


def x_to_wt(p, x):
    x = np.asarray(x, float)
    return 100 * x * p["MB"] / (x * p["MB"] + (1 - x) * p["MA"])


def computed_diagram(p: dict, nT: int = 161, n: int = 801, unit: str = "wt") -> dict:
    """Grenzlinien eines berechneten Diagramms: je Temperatur die Enden aller Konoden (Liquidus, Solidus, Solvus)."""
    T0, T1 = p.get("Tlim") or [min(p["TmA"], p["TmB"]) - 300, max(p["TmA"], p["TmB"]) + 50]
    Ts = np.linspace(T0, T1, nT)
    pts = {"liquidus": [], "solidus": [], "solvus": []}
    three = []
    conv = (lambda v: float(x_to_wt(p, v))) if unit == "wt" and p.get("MA") else (lambda v: 100 * float(v))
    prev_kinds = None
    for T in Ts:
        segs = equilibrium(p, float(T), n)
        kinds = tuple(tuple(s["phases"]) for s in segs if s["kind"] == "two")
        for s in segs:
            if s["kind"] != "two":
                continue
            (pa, pb), (xa, xb) = s["phases"], s["x"]
            if {pa, pb} == {"S", "L"}:
                xl_ = xa if pa == "L" else xb
                xs_ = xb if pa == "L" else xa
                pts["liquidus"].append([conv(xl_), float(T)])
                pts["solidus"].append([conv(xs_), float(T)])
            else:
                pts["solvus"].append([conv(xa), float(T)])
                pts["solvus"].append([conv(xb), float(T)])
        if prev_kinds is not None and kinds != prev_kinds and any(set(k) == {"S"} for k in kinds + prev_kinds) \
                and any("L" in k for k in kinds + prev_kinds):
            three.append(float(T))
        prev_kinds = kinds
    return {"points": pts, "three_phase_T": three, "unit": unit, "Tlim": [float(T0), float(T1)]}


def lever_computed(p: dict, x_in: float, T_C: float, unit: str = "wt", n: int = 2001) -> dict:
    """Hebelgesetz im berechneten Diagramm; Anteile als Stoffmengen- und (mit Molmassen) Massenanteile."""
    x0 = float(wt_to_x(p, x_in)) if unit == "wt" and p.get("MA") else x_in / 100
    segs = equilibrium(p, T_C, n)
    conv = (lambda v: float(x_to_wt(p, v))) if unit == "wt" and p.get("MA") else (lambda v: 100 * float(v))
    for s in segs:
        if s["kind"] == "one" and s["x0"] - 1e-9 <= x0 <= s["x1"] + 1e-9:
            return {"T": T_C, "x": x_in, "phases": [{"name": s["phase"], "x": x_in, "frac": 1.0}],
                    "region": s["phase"]}
        if s["kind"] == "two" and s["x"][0] <= x0 <= s["x"][1]:
            xl, xr = s["x"]
            fl = (xr - x0) / (xr - xl)                       # Stoffmengenanteil der linken Phase
            if unit == "wt" and p.get("MA"):
                ml = fl * (xl * p["MB"] + (1 - xl) * p["MA"])
                mr = (1 - fl) * (xr * p["MB"] + (1 - xr) * p["MA"])
                fw = ml / (ml + mr)
            else:
                fw = fl
            names = [s["phases"][0] + ("₁" if s["phases"][0] == s["phases"][1] else ""),
                     s["phases"][1] + ("₂" if s["phases"][0] == s["phases"][1] else "")]
            return {"T": T_C, "x": x_in, "region": " + ".join(names), "tie": [conv(xl), conv(xr)],
                    "phases": [{"name": names[0], "x": conv(xl), "frac": fw},
                               {"name": names[1], "x": conv(xr), "frac": 1 - fw}]}
    raise DiagramError("Zusammensetzung nicht im berechneten Bereich")
