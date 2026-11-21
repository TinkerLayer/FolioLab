"""Gefügebilder: schematische Schliffbilder der Gefügebestandteile von Metallen und stetige Umwandlungsfolgen.

Skizzenformat wie struktur.sk_metal (Einheitsquadrat, y nach oben, Strichstärken für ≈ 520 px). Erlaubte Elemente:
poly, circle, line, pline, dots, dashes, hatch, clip, text. Die Geometrie einer Umwandlung wird je Seed einmal gebaut
und mit dem Fortschritt f ∈ [0, 1] nur aufgedeckt oder wachsen gelassen; eine Bildfolge wirkt dadurch stetig.

- CONSTITUENTS, sketch(): Galerie der Gefügebestandteile (Stahl, Gusseisen, Al, Ti, Cu, Eutektika, allgemein)
- TRANSITIONS, transition(): Umwandlungen (Austenitisieren, Perlit, Martensit, Anlassen, Bainit, Ausscheidung, …)
- MECHANISMS, mechanism(): Bildfolgen für die Animation, Bain-Verzerrung als 3D-Szene
- steel_state(), al_state(): Zustände der Wärmebehandlung aus struktur.py als Skizzen
Alles schematisch, nicht massstäblich. Quellen: data/gefuege_quellen.json und die Register des Moduls (refs.py).
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np

from . import struktur as SK

DATA = Path(__file__).resolve().parent / "data"
ITEM_TYPES = ("poly", "circle", "line", "pline", "dots", "dashes", "hatch", "clip", "text")
PI = math.pi

# ============================================================================ Farben (hell: Matrix, dunkel: Carbide)
FER, FER_GB = "#f3f1ea", "#77726a"                    # Ferrit, Ferritkorngrenze
P_BG, P_LAM, P_EDGE = "#d2c1aa", "#3b2e27", "#8a7867"  # Perlit: Grund, Zementitlamellen, Koloniegrenze
P_DARK = "#7b6656"                                    # Perlit, nicht aufgelöst
CEM, CEM_EDGE = "#fbf7ec", "#4d4038"                  # massiver Zementit (in Nital hell) mit Kontur
AUS, AUS_IF = "#dfe7f1", "#93a0b0"                    # Austenit, Grenzfläche
GB = "#4f555c"                                        # Korngrenze
M_A, M_B, M_LATH, M_GB = "#b6bfc9", "#a3adb9", "#5b6571", "#2f353c"
M_PLATE, M_PLATE_E, M_RIB = "#7f8994", "#4a525b", "#22282e"
RA = "#eef2f7"
B_UP, B_UP_E, B_LO, B_LO_E = "#b8beb0", "#8d9488", "#a3aab2", "#68707a"
CARB = "#2a221e"
GRAPH = "#262626"
AL, AL_GB, AL_PREC = "#eceff3", "#6e747c", "#6b4a33"
SI = "#555a62"
LIQ, DEND, DEND_E = "#f1e1c6", "#e3e9ef", "#7c8693"
EUT_BG, EUT_LAM = "#c4bdb1", "#4e4842"
TI_A, TI_B = "#eef0e6", "#8d98a8"
MS_A, MS_B = "#efdfb9", "#c09a5c"
DEF, DEF_SLIP, REX = "#d3d8de", "#77808b", "#f4f2ec"
PB, SN = "#5e636b", "#eef0f2"


def _cl(x, lo=0.0, hi=1.0):
    return lo if x < lo else hi if x > hi else x


def _L(de, a, b):
    return a if de else b


def _num(x, nd, de):
    s = f"{x:.{nd}f}"
    return s.replace(".", ",") if de else s


def _mix(c1, c2, t):
    t = _cl(t)
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def _ease(t):
    t = _cl(t)
    return t * t * (3 - 2 * t)


def _seed(rng) -> int:
    if isinstance(rng, (int, np.integer)):
        return int(rng)
    if hasattr(rng, "integers"):
        return int(rng.integers(0, 2 ** 31 - 1))
    if hasattr(rng, "randint"):
        return int(rng.randint(0, 2 ** 31 - 1))
    return 1


# ============================================================================ Geometrie (Polygone als Tupellisten, CCW)
VIEW = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]


def _area(P):
    if len(P) < 3:
        return 0.0
    s = 0.0
    x0, y0 = P[-1]
    for x1, y1 in P:
        s += x0 * y1 - x1 * y0
        x0, y0 = x1, y1
    return 0.5 * s


def _ctr(P):
    n = len(P)
    if n == 0:
        return (0.5, 0.5)
    A = cx = cy = 0.0
    x0, y0 = P[-1]
    for x1, y1 in P:
        cr = x0 * y1 - x1 * y0
        A += cr
        cx += (x0 + x1) * cr
        cy += (y0 + y1) * cr
        x0, y0 = x1, y1
    if abs(A) < 1e-12:
        return (sum(p[0] for p in P) / n, sum(p[1] for p in P) / n)
    return (cx / (3 * A), cy / (3 * A))


def _mean(P):
    n = len(P)
    return (sum(p[0] for p in P) / n, sum(p[1] for p in P) / n)


def _perim(P):
    return sum(math.hypot(P[i][0] - P[i - 1][0], P[i][1] - P[i - 1][1]) for i in range(len(P)))


def _perim_pt(P, t):
    """Punkt beim Bruchteil t des Umfangs."""
    L = _perim(P) * (t % 1.0)
    n = len(P)
    for i in range(n):
        a, b = P[i], P[(i + 1) % n]
        s = math.hypot(b[0] - a[0], b[1] - a[1])
        if L <= s or i == n - 1:
            u = L / s if s > 1e-12 else 0.0
            return (a[0] + u * (b[0] - a[0]), a[1] + u * (b[1] - a[1]))
        L -= s
    return P[0]


def _half(P, a, b, c):
    """Teil des Polygons mit a·x + b·y ≤ c (Sutherland-Hodgman, eine Kante)."""
    out = []
    if not P:
        return out
    px, py = P[-1]
    dp = a * px + b * py - c
    for qx, qy in P:
        dq = a * qx + b * qy - c
        if dq <= 0:
            if dp > 0:
                t = dp / (dp - dq)
                out.append((px + t * (qx - px), py + t * (qy - py)))
            out.append((qx, qy))
        elif dp < 0:
            t = dp / (dp - dq)
            out.append((px + t * (qx - px), py + t * (qy - py)))
        px, py, dp = qx, qy, dq
    return out


def _edges(P):
    out = []
    n = len(P)
    for i in range(n):
        x1, y1 = P[i]
        x2, y2 = P[(i + 1) % n]
        a, b = y2 - y1, x1 - x2
        out.append((a, b, a * x1 + b * y1))
    return out


def _cut(P, C):
    """P geschnitten mit dem konvexen Polygon C (CCW)."""
    for a, b, c in _edges(C):
        P = _half(P, a, b, c)
        if len(P) < 3:
            return []
    return P


def _inset(P, d):
    """Konvexes Polygon um d (Zahl oder je Kante) nach innen versetzt."""
    Q = P
    for i, (a, b, c) in enumerate(_edges(P)):
        L = math.hypot(a, b)
        if L < 1e-12:
            continue
        di = d[i] if isinstance(d, (list, tuple, np.ndarray)) else d
        Q = _half(Q, a, b, c - di * L)
        if len(Q) < 3:
            return []
    return Q


def _ccw(P):
    return P if _area(P) >= 0 else P[::-1]


def _disc(c, r, m=36):
    return [(c[0] + r * math.cos(2 * PI * k / m), c[1] + r * math.sin(2 * PI * k / m)) for k in range(m)]


def _chord(E, p, d):
    """Parameterbereich (t0, t1) der Geraden p + t·d im konvexen Polygon mit Kanten E, sonst None."""
    lo, hi = -1e9, 1e9
    for a, b, c in E:
        den = a * d[0] + b * d[1]
        num = c - a * p[0] - b * p[1]
        if abs(den) < 1e-14:
            if num < 0:
                return None
        elif den > 0:
            hi = min(hi, num / den)
        else:
            lo = max(lo, num / den)
    return (lo, hi) if lo < hi else None


def _inside(E, p, eps=0.0):
    return all(a * p[0] + b * p[1] <= c - eps * math.hypot(a, b) for a, b, c in E)


def _bbox(P):
    xs = [p[0] for p in P]
    ys = [p[1] for p in P]
    return min(xs), min(ys), max(xs), max(ys)


def _vis(P, m=0.0):
    if len(P) < 3:
        return False
    x0, y0, x1, y1 = _bbox(P)
    return x1 > -m and y1 > -m and x0 < 1 + m and y0 < 1 + m


def _sample_in(P, n, rng, view=True):
    """n Zufallspunkte im konvexen Polygon (Verwerfungsverfahren), wahlweise nur im Bild."""
    Q = _cut(P, VIEW) if view else P
    if len(Q) < 3 or n <= 0:
        return np.zeros((0, 2))
    x0, y0, x1, y1 = _bbox(Q)
    E = np.array(_edges(Q))
    out = []
    got = 0
    for _ in range(8):
        k = max(n * 2, 16)
        X = np.column_stack([rng.uniform(x0, x1, k), rng.uniform(y0, y1, k)])
        ok = (X @ E[:, :2].T <= E[:, 2] + 1e-12).all(1)
        out.append(X[ok])
        got += int(ok.sum())
        if got >= n:
            break
    X = np.concatenate(out)[:n]
    return X


def _seg_dist(X, A, B, chunk=500):
    """Kleinster Abstand der Punkte X zu den Strecken A→B."""
    X = np.asarray(X, float)
    if len(A) == 0 or len(X) == 0:
        return np.full(len(X), 1e9)
    A = np.asarray(A, float)
    D = np.asarray(B, float) - A
    L2 = np.maximum((D ** 2).sum(1), 1e-14)
    out = np.empty(len(X))
    for i in range(0, len(X), chunk):
        x = X[i:i + chunk]
        t = np.clip(((x[:, None, :] - A[None]) * D[None]).sum(-1) / L2[None], 0, 1)
        q = A[None] + t[..., None] * D[None]
        out[i:i + chunk] = np.sqrt(((x[:, None, :] - q) ** 2).sum(-1)).min(1)
    return out


def _cells(S, w=None, box=None, k=14):
    """Power-Diagramm (Voronoi für w = 0) der Punkte S im konvexen Kasten box; eine Zelle je Punkt (leer möglich)."""
    S = np.asarray(S, float).reshape(-1, 2)
    n = len(S)
    box = box or [(-0.15, -0.15), (1.15, -0.15), (1.15, 1.15), (-0.15, 1.15)]
    if n == 1:
        return [list(box)]
    w = np.zeros(n) if w is None else np.asarray(w, float)
    D = ((S[:, None, :] - S[None, :, :]) ** 2).sum(-1)
    kk = min(k, n - 1)
    nb = np.argsort(D, 1)[:, 1:kk + 1]
    sq = (S ** 2).sum(1)
    out = []
    for i in range(n):
        P = list(box)
        xi, yi = S[i]
        for j in nb[i]:
            P = _half(P, 2 * (S[j, 0] - xi), 2 * (S[j, 1] - yi), sq[j] - sq[i] - w[j] + w[i])
            if len(P) < 3:
                P = []
                break
        out.append(P)
    return out


def _grains(rng, n, k=1.0, m=0.14, lloyd=1, vert=False):
    """Körner als Voronoi-Zellen (mit Lloyd-Glättung) im erweiterten Feld; k > 1 streckt die Körner in x
    (vert: in y). Gibt CCW-Polygone zurück, die ins Bild reichen."""
    H = float(k)
    N = max(4, int(round(n * (1 + 2 * m) ** 2)))
    S = np.column_stack([rng.uniform(-m, 1 + m, N), rng.uniform(-m * H, (1 + m) * H, N)])
    box = [(-m, -m * H), (1 + m, -m * H), (1 + m, (1 + m) * H), (-m, (1 + m) * H)]
    C = _cells(S, box=box)
    for _ in range(lloyd):
        S = np.array([_ctr(P) if len(P) >= 3 else tuple(s) for P, s in zip(C, S)])
        C = _cells(S, box=box)
    out = []
    for P in C:
        if len(P) < 3:
            continue
        Q = [(x, y / H) for x, y in P]
        if vert:
            Q = [(y, x) for x, y in Q][::-1]
        if _vis(Q, 0.01):
            out.append(Q)
    return out


def _lens(A, B, hw, m=7, expo=1.0):
    """Linse (Platte) von A nach B mit halber Dicke hw; spitze Enden."""
    dx, dy = B[0] - A[0], B[1] - A[1]
    L = math.hypot(dx, dy) or 1e-9
    nx, ny = -dy / L, dx / L
    ss = [(i + 1) / (m + 1) for i in range(m)]
    h = [hw * (4 * s * (1 - s)) ** expo for s in ss]
    lo = [(A[0] + s * dx - nx * hh, A[1] + s * dy - ny * hh) for s, hh in zip(ss, h)]
    up = [(A[0] + s * dx + nx * hh, A[1] + s * dy + ny * hh) for s, hh in zip(ss, h)]
    return [tuple(A)] + lo + [tuple(B)] + up[::-1]


def _chaikin(P, it=2):
    for _ in range(it):
        Q = []
        n = len(P)
        for i in range(n):
            a, b = P[i], P[(i + 1) % n]
            Q.append((0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]))
            Q.append((0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1]))
        P = Q
    return P


def _rot(d, a):
    c, s = math.cos(a), math.sin(a)
    return (c * d[0] - s * d[1], s * d[0] + c * d[1])


# ============================================================================ Elemente
def _r(P):
    return [[round(float(x), 4), round(float(y), 4)] for x, y in P]


def _pt(p):
    return [round(float(p[0]), 4), round(float(p[1]), 4)]


def _op(d, op):
    if op is not None and op < 0.995:
        d["op"] = round(max(float(op), 0.0), 3)
    return d


def _poly(P, fill, stroke=None, sw=0.8, op=None):
    d = {"t": "poly", "p": _r(P), "fill": fill, "stroke": stroke or "none"}
    if stroke:
        d["sw"] = sw
    return _op(d, op)


VIEWX = [(-0.004, -0.004), (1.004, -0.004), (1.004, 1.004), (-0.004, 1.004)]


def _hpoly(P):
    """Polygon einer Schraffur, wie es ausgegeben wird: aufs Bild beschnitten (spart Linien) und gerundet."""
    x0, y0, x1, y1 = _bbox(P)
    if x0 < -0.004 or y0 < -0.004 or x1 > 1.004 or y1 > 1.004:
        P = _cut(P, VIEWX)
    return [tuple(v) for v in _r(P)] if len(P) >= 3 else []


def _hatch_lines(Pr, a, s, o):
    """Lage der Schraffurlinien wie im Zeichner: (Punkt, Richtung) je Linie für ein Polygon aus _hpoly."""
    cx, cy = _mean(Pr)
    R = max(math.hypot(v[0] - cx, v[1] - cy) for v in Pr) * 1.1
    a = round(float(a) % PI, 4)
    d = (math.cos(a), math.sin(a))
    nr = (-d[1], d[0])
    s = round(float(s), 5)
    u = -R + round(float(o) % 1.0, 3) * s
    out = []
    while u < R:
        out.append(((cx + nr[0] * u, cy + nr[1] * u), d))
        u += s
    return out


def _hatch(P, a, s, o, stroke, sw, op=None):
    Pr = _hpoly(P)
    if not Pr:
        return {"t": "clip", "poly": [[0, 0], [0, 0], [0, 0]], "items": []}
    return _op({"t": "hatch", "poly": [list(v) for v in Pr], "a": round(float(a) % PI, 4), "s": round(float(s), 5),
                "o": round(float(o) % 1.0, 3), "stroke": stroke, "sw": sw}, op)


def _line(p, q, stroke, sw, op=None):
    return _op({"t": "line", "p": [_pt(p), _pt(q)], "stroke": stroke, "sw": sw}, op)


def _pline(pts, stroke, sw, op=None):
    return _op({"t": "pline", "p": _r(pts), "stroke": stroke, "sw": round(float(sw), 2)}, op)


def _clip(P, items):
    return {"t": "clip", "poly": _r(P), "items": items}


def _circle(c, r, fill, stroke=None, sw=0.8, op=None):
    d = {"t": "circle", "c": _pt(c), "r": round(float(r), 4), "fill": fill}
    if stroke:
        d["stroke"] = stroke
        d["sw"] = sw
    return _op(d, op)


def _dashes(parts, stroke, op=None, lq=0.0012, wq=0.2):
    """Längliche Teilchen (x, y, Winkel, Länge, Strichstärke) zu wenigen dashes-Elementen gebündelt."""
    groups = {}
    dots = []
    for x, y, a, L, w in parts:
        if w <= 0.05:
            continue
        if L < 0.0015:                                   # fast rund: als Punkt (Strecken der Länge 0 zeichnet nicht jeder)
            if w >= 0.5:
                dots.append((x, y, w / 2 / 520 + L / 2))
            continue
        key = (int(round(L / lq)), int(round(w / wq)))
        groups.setdefault(key, []).append([round(float(x), 4), round(float(y), 4), round(float(a) % PI, 3)])
    out = []
    for (lk, wk), p in sorted(groups.items()):
        out.append(_op({"t": "dashes", "p": p, "len": round(max(lk, 1) * lq, 4), "stroke": stroke,
                        "sw": round(max(wk * wq, 0.2), 2)}, op))
    return out + _dots(dots, stroke, op, rq=0.0003)


def _dots(parts, fill, op=None, rq=0.0004):
    groups = {}
    for x, y, r in parts:
        if r <= 2e-4:
            continue
        groups.setdefault(int(round(r / rq)), []).append([round(float(x), 4), round(float(y), 4)])
    return [_op({"t": "dots", "p": p, "r": round(max(k, 1) * rq, 4), "fill": fill}, op)
            for k, p in sorted(groups.items())]


def _leg(color, label):
    return {"color": color, "label": label}


def _scale(field_um, de):
    """Massstab: 20 % der Bildbreite (None: kein Massstab, z. B. wenn Teilchengrössen über Dekaden schematisch sind)."""
    if not field_um:
        return None
    v = 0.2 * field_um
    if v >= 1:
        lab = f"{v:g} µm"
    else:
        lab = f"{v * 1000:g} nm"
    return {"len": 0.2, "label": lab.replace(".", ",") if de else lab}


# ============================================================================ Stahl: Ferrit, Perlit, Zementitnetz
@lru_cache(maxsize=48)
def _fp_geom(seed: int, C: float, n: int, s: float) -> dict:
    """Ehemalige Austenitkörner mit Saum (voreutektoider Ferrit oder Sekundärzementit, Dicke nach Hebelgesetz) und
    Kernen, die in Perlitkolonien zerlegt sind (Keime auf der Kerngrenze, je Kolonie eigene Lamellenrichtung)."""
    rng = np.random.default_rng(seed)
    G = _grains(rng, n)
    F = _grains(rng, max(4, int(n * 2.6))) if C < 0.765 else []
    fac = [tuple(rng.uniform(0.55, 1.45, len(P))) for P in G]
    At = sum(_area(P) for P in G)
    if C < 0.765:
        target = _cl((0.77 - C) / (0.77 - 0.022))
    elif C > 0.775:
        target = _cl((C - 0.77) / (6.67 - 0.77))
    else:
        target = 0.0

    def core(i, d):
        return _inset(G[i], [d * x for x in fac[i]]) if d > 0 else G[i]

    d = 0.0
    if target > 0:
        lo, hi = 0.0, 0.3
        for _ in range(16):
            mid = 0.5 * (lo + hi)
            band = 1 - sum(_area(core(i, mid)) for i in range(len(G))) / At
            if band < target:
                lo = mid
            else:
                hi = mid
        d = 0.5 * (lo + hi)
    grains = []
    for i, P in enumerate(G):
        gr = {"P": P, "fac": fac[i], "dl": tuple(rng.uniform(0, 0.45, len(P)))}
        Q = _core_at(gr, d, 1.0)
        tg = rng.uniform(0, 0.15)
        cols = []
        if len(Q) >= 3 and _area(Q) > 3e-5:
            per = _perim(Q)
            m = int(_cl(round(per / 0.19), 1, 5)) if _area(Q) > 0.003 else 1
            t0 = rng.uniform()
            nuc = [_perim_pt(Q, t0 + (k + rng.uniform(-0.25, 0.25)) / m) for k in range(m)]
            cells = _cells(np.array(nuc), box=Q) if m > 1 else [Q]
            for nu, c in zip(nuc, cells):
                if len(c) < 3:
                    continue
                R = max(math.hypot(v[0] - nu[0], v[1] - nu[1]) for v in c) * 1.06 + 1e-3
                cols.append({"P": c, "nuc": nu, "R": R, "t": tg + rng.uniform(0, 0.2), "a": rng.uniform(0, PI),
                             "s": s * rng.uniform(1.0, 1.5), "o": rng.uniform()})
        gr.update({"core": Q, "cols": cols})
        grains.append(gr)
    return {"G": grains, "F": F, "d": d, "C": C, "At": At, "target": target}


def _round_corners(Q, r):
    """Ecken eines konvexen Polygons um den Anteil r ≤ 0,25 jeder Kante abschneiden (bleibt konvex, stetig in r)."""
    if r <= 1e-4 or len(Q) < 3:
        return Q
    out = []
    n = len(Q)
    for i in range(n):
        a, b = Q[i], Q[(i + 1) % n]
        out.append(((1 - r) * a[0] + r * b[0], (1 - r) * a[1] + r * b[1]))
        out.append((r * a[0] + (1 - r) * b[0], r * a[1] + (1 - r) * b[1]))
    return out


def _core_at(gr, d, q):
    """Kern eines Korns, wenn der Saum zum Anteil q gewachsen ist: Kanten beginnen verzögert (dl), Ecken (Tripelpunkte)
    zuerst."""
    if q <= 0 or d <= 0:
        return gr["P"]
    ds = [d * f * _cl((q - t) / (1 - t)) for f, t in zip(gr["fac"], gr["dl"])]
    Q = _inset(gr["P"], ds)
    return _round_corners(Q, 0.22 * _ease(min(q * 3, 1.0))) if len(Q) >= 3 else []


def _col_items(c, k, op=None):
    """Perlitkolonie, zu k ∈ [0, 1] gewachsen (Scheibe um den Keim ∩ Zelle); Lamellen fest zur fertigen Kolonie."""
    if k <= 0:
        return [], 0.0
    rev = c["P"] if k >= 1 else _cut(_disc(c["nuc"], c["R"] * k), c["P"])
    if len(rev) < 3:
        return [], 0.0
    h = _hatch(c["P"], c["a"], c["s"], c["o"], P_LAM, 1.0, op)
    return [_poly(rev, P_BG, P_EDGE, 0.45, op), h if k >= 1 else _clip(rev, [h])], _area(rev)


def _fp_split(C, target):
    hypo, hyper = C < 0.765, C > 0.775
    return (0.12 + 0.45 * target) if hypo else (0.22 if hyper else 0.0)


def _perlit_items(g, f, de):
    C = g["C"]
    hypo, hyper = C < 0.765, C > 0.775
    f1 = _fp_split(C, g["target"])
    q = _cl(f / f1) if f1 > 0 else 1.0
    p = _cl((f - f1) / (1 - f1)) if f1 < 1 else 0.0
    items, legend = [], []
    if hypo and q > 0:
        items += [_poly(P, FER, FER_GB, 0.6) for P in g["F"]]
    done = 0.0
    gamma_left = False
    for gr in g["G"]:
        P = gr["P"]
        if hyper and q > 0:
            items.append(_poly(P, CEM, CEM_EDGE, 0.7))
        core = _core_at(gr, g["d"], q)
        if len(core) >= 3 and (gr["cols"] or q == 0):
            cov = sum(_area(c["P"]) for c in gr["cols"] if p >= 1)
            if p < 1 or cov < _area(core) * 0.999:
                st = GB if q == 0 else (CEM_EDGE if hyper else AUS_IF)
                items.append(_poly(core, AUS, st, 0.9 if q == 0 else 0.5))
                gamma_left = True
        done += _area(P) - (_area(core) if len(core) >= 3 and gr["cols"] else 0.0)
        for c in gr["cols"]:
            it, a = _col_items(c, (p - c["t"]) / (1 - c["t"]) if p > c["t"] else 0.0)
            items += it
            done += a
    if hypo and q > 0:
        legend.append(_leg(FER, _L(de, "voreutektoider Ferrit (α)", "proeutectoid ferrite (α)")))
    if hyper and q > 0:
        legend.append(_leg(CEM, _L(de, "Sekundärzementit (Korngrenzennetz)", "secondary cementite (grain-boundary network)")))
    if p > 0:
        legend.append(_leg(P_BG, _L(de, "Perlit: Kolonien aus α + Fe₃C-Lamellen", "pearlite: colonies of α + Fe₃C lamellae")))
    if gamma_left:
        legend.append(_leg(AUS, _L(de, "Austenit (γ), noch nicht umgewandelt", "austenite (γ), not yet transformed")))
    return items, legend, _cl(done / g["At"])


def _aust_items(g, f, de):
    """Austenitisieren: erst der Perlit (Kern schrumpft von der Kerngrenze her), dann Ferrit bzw. Zementitnetz."""
    C = g["C"]
    hypo, hyper = C < 0.765, C > 0.775
    fP = 0.4 if hypo else (0.55 if hyper else 1.0)
    qA = _cl(f / fP)
    qB = _cl((f - fP) / (1 - fP)) if fP < 1 else 0.0
    items, legend = [], []
    if hypo and qB < 1:
        items += [_poly(P, FER, FER_GB, 0.6) for P in g["F"]]
    gam = 0.0
    pear_left = False
    for gr in g["G"]:
        P = gr["P"]
        if hyper and qB < 1:
            items.append(_poly(P, CEM, CEM_EDGE, 0.7))
        gp = _core_at(gr, g["d"], 1 - qB) if (hypo or hyper) else P
        if len(gp) >= 3 and (gr["cols"] or qB > 0):
            items.append(_poly(gp, AUS, GB if qB >= 1 or not (hypo or hyper) else AUS_IF, 0.9 if qB >= 1 else 0.5))
            gam += _area(gp)
        core = gr["core"]
        if qA < 1 and gr["cols"] and len(core) >= 3:
            cc = _ctr(core)
            Dc = max(math.hypot(v[0] - cc[0], v[1] - cc[1]) for v in core) * 1.02
            rem = _inset(core, Dc * (1 - math.sqrt(1 - qA))) if qA > 0 else core
            if len(rem) >= 3:
                sub = []
                for c in gr["cols"]:
                    sub += _col_items(c, 1.0)[0]
                items.append(_clip(rem, sub))
                gam -= _area(rem)
                pear_left = True
    if hypo and qB < 1:
        legend.append(_leg(FER, _L(de, "Ferrit (α)", "ferrite (α)")))
    if hyper and qB < 1:
        legend.append(_leg(CEM, _L(de, "Zementitnetz (löst sich über Acm)", "cementite network (dissolves above Acm)")))
    if pear_left:
        legend.append(_leg(P_BG, _L(de, "Perlit (löst sich über Ac1)", "pearlite (dissolves above Ac1)")))
    legend.append(_leg(AUS, _L(de, "Austenit (γ)", "austenite (γ)")))
    return items, legend, _cl(gam / g["At"])


# ============================================================================ Kugelzementit (Einformen)
@lru_cache(maxsize=16)
def _sph_geom(seed: int, n: int) -> dict:
    g = _fp_geom(seed, 0.77, n, 0.017)
    rng = np.random.default_rng(seed + 7)
    pcs = []
    cols = []
    for gr in g["G"]:
        for c in gr["cols"]:
            Q = _cut(c["P"], VIEW)
            if len(Q) < 3:
                continue
            cols.append(c["P"])
            Pr = [tuple(v) for v in _r(c["P"])]
            cx, cy = _mean(Pr)
            R = max(math.hypot(v[0] - cx, v[1] - cy) for v in Pr) * 1.1
            a = round(c["a"] % PI, 4)
            d = (math.cos(a), math.sin(a))
            nr = (-d[1], d[0])
            E = _edges(Q)
            s = round(c["s"], 5)
            u = -R + round(c["o"], 3) * s
            while u < R:
                p0 = (cx + nr[0] * u, cy + nr[1] * u)
                ch = _chord(E, p0, d)
                if ch and ch[1] - ch[0] > 0.006:
                    L = ch[1] - ch[0]
                    m = max(1, int(round(L / 0.045)))
                    for j in range(m):
                        t = ch[0] + (j + 0.5) * L / m
                        pcs.append((p0[0] + t * d[0], p0[1] + t * d[1], a, L / m, rng.uniform(0.3, 1.7), rng.uniform()))
                u += s
    return {"g": g, "pc": np.array(pcs), "cols": cols}


def _sph_items(G, s, de):
    pc = G["pc"]
    items = []
    bg = _mix(P_BG, FER, (s - 0.12) / 0.5)
    eo = 1 - 0.7 * _cl((s - 0.2) / 0.5)
    for P in G["cols"]:
        items.append(_poly(P, bg, _mix(P_EDGE, FER_GB, s), 0.45 + 0.25 * _cl(s / 0.6)))
    w0 = 1.1
    parts = []
    z, tau, L0 = pc[:, 4], pc[:, 5], pc[:, 3]
    g1 = np.clip((s - 0.12 * tau) / 0.3, 0, 1)
    g2 = np.clip((s - 0.3 - 0.08 * tau) / 0.35, 0, 1)
    g3 = _cl((s - 0.7) / 0.3)
    D = np.sqrt(4 * 0.68 * L0 * 520 * w0 / PI)
    zc = 0.85 * g3
    vol = np.maximum(z - zc, 0)
    K = z.sum() / max(vol.sum(), 1e-9)
    Dk = D * np.sqrt(vol * K) * (1 + 0.15 * g3)
    L = L0 * (1 - 0.32 * g1) * (1 - g2) ** 1.4
    W = w0 + (D * np.sqrt(z) - w0) * g2
    W = np.where(g3 > 0, Dk, W)
    for i in range(len(pc)):
        parts.append((pc[i, 0], pc[i, 1], pc[i, 2], L[i], W[i]))
    items += _dashes(parts, P_LAM, wq=0.25)
    legend = [_leg(bg, _L(de, "Ferrit (α)", "ferrite (α)")),
              _leg(P_LAM, _L(de, "Zementit (Fe₃C): Lamellen → Kugeln", "cementite (Fe₃C): lamellae → spheroids"))]
    return items, legend, _cl(s)


# ============================================================================ Martensit (Latten und Platten)
def _plates_in(P, rng, hw_ratio=0.06, nmax=24, Lmin=0.022, dirs=None, Lcap=9.0, from_edge=False, init=None):
    """Platten nacheinander in ein konvexes Korn legen: jede Platte endet an den früheren (Mittelrippe als Strecke);
    die erste durchquert das Korn, spätere werden kleiner (fraktale Aufteilung). init: schon liegende Platten."""
    E = _edges(P)
    x0, y0, x1, y1 = _bbox(P)
    if dirs is None:
        b = rng.uniform(0, PI)
        dirs = [b + k * PI / 4 + rng.normal(0, 0.08) for k in range(4)]
    out = list(init or [])
    n0 = len(out)
    tries = 0
    cc = _ctr(P)
    while len(out) < nmax and tries < nmax * 10:
        tries += 1
        if from_edge:
            q = _perim_pt(P, rng.uniform())
            dd = math.hypot(cc[0] - q[0], cc[1] - q[1]) or 1.0
            p = (q[0] + 0.004 * (cc[0] - q[0]) / dd, q[1] + 0.004 * (cc[1] - q[1]) / dd)
        elif not out:
            p = (cc[0] + rng.normal(0, 0.01), cc[1] + rng.normal(0, 0.01))
        else:
            p = (rng.uniform(x0, x1), rng.uniform(y0, y1))
        if not _inside(E, p, 0.0005 if from_edge else 0.002):
            continue
        bad = False
        for A, B, hw in out:
            dx, dy = B[0] - A[0], B[1] - A[1]
            L2 = dx * dx + dy * dy
            u = ((p[0] - A[0]) * dx + (p[1] - A[1]) * dy) / L2
            if 0 < u < 1:
                dist = abs((p[0] - A[0]) * dy - (p[1] - A[1]) * dx) / math.sqrt(L2)
                if dist < hw * 4 * u * (1 - u) + 0.003:
                    bad = True
                    break
        if bad:
            continue
        a = dirs[int(rng.integers(len(dirs)))] + rng.normal(0, 0.05)
        d = (math.cos(a), math.sin(a))
        if from_edge and (d[0] * (cc[0] - p[0]) + d[1] * (cc[1] - p[1])) < 0:
            d = (-d[0], -d[1])
        ch = _chord(E, p, d)
        if not ch:
            continue
        t0, t1 = ch
        if from_edge:
            t0 = max(t0, -0.002)
        for A, B, hw in out:
            sx, sy = B[0] - A[0], B[1] - A[1]
            den = d[0] * sy - d[1] * sx
            if abs(den) < 1e-9:
                continue
            ax, ay = A[0] - p[0], A[1] - p[1]
            t = (ax * sy - ay * sx) / den
            u = (ax * d[1] - ay * d[0]) / den
            if 0 <= u <= 1:
                sn = abs(den) / math.hypot(sx, sy)
                mg = (hw * 4 * u * (1 - u)) / max(sn, 0.3) + 0.002
                if t > 0:
                    t1 = min(t1, t - mg)
                else:
                    t0 = max(t0, t + mg)
        L = t1 - t0
        if L < Lmin:
            continue
        if L > Lcap:
            if from_edge:
                t1 = t0 + Lcap
            else:
                mid = 0.5 * (t0 + t1) + rng.uniform(-0.3, 0.3) * (L - Lcap)
                t0, t1 = mid - Lcap / 2, mid + Lcap / 2
            L = Lcap
        A = (p[0] + t0 * d[0], p[1] + t0 * d[1])
        B = (p[0] + t1 * d[0], p[1] + t1 * d[1])
        out.append((A, B, hw_ratio * L + 0.0015))
    return out[n0:] if init else out


@lru_cache(maxsize=32)
def _mart_geom(seed: int, C: float, n: int, mode: str = "auto") -> dict:
    """Ehemalige Austenitkörner; je Korn Latten (Pakete → Blöcke → Latten) oder Platten (Linsen mit Mittelrippe).
    Jede Einheit hat eine feste Bildungszeit; Blöcke eines Pakets entstehen nebeneinander."""
    rng = np.random.default_rng(seed)
    G = _grains(rng, n)
    pp = 0.0 if mode == "lath" else _cl((C - 0.6) / 0.4)
    units, packets = [], []
    for P in G:
        tg = rng.uniform()
        if rng.random() < pp or pp >= 1:
            pls = _plates_in(P, rng, hw_ratio=0.055, nmax=40, Lmin=0.016)
            N = len(pls)
            for k, (A, B, hw) in enumerate(pls):
                Lp = _lens(A, B, hw, m=5)
                tone = rng.random() < 0.5
                if _vis(Lp):
                    units.append({"k": "plate", "A": A, "B": B, "poly": Lp, "area": _area(Lp), "tone": tone,
                                  "t": 0.3 * tg + 0.7 * (k / max(N, 1)) ** 0.8 + rng.uniform(0, 0.04)})
            continue
        m = int(_cl(round(_area(P) / 0.028), 2, 4))
        seeds = _sample_in(P, m, rng, view=False)
        Q_ = _cells(seeds, box=P) if len(seeds) > 1 else [P]
        base = rng.uniform(0, PI)
        for Q in Q_:
            if len(Q) < 3:
                continue
            th = base + int(rng.integers(0, 3)) * PI / 3 + rng.normal(0, 0.1)
            d = (math.cos(th), math.sin(th))
            nr = (-d[1], d[0])
            us = [v[0] * nr[0] + v[1] * nr[1] for v in Q]
            u, u1 = min(us), max(us)
            pid = len(packets)
            tp = rng.uniform()
            packets.append({"P": Q, "th": th, "nr": nr, "u0": u, "s": rng.uniform(0.0092, 0.0108), "o": rng.uniform()})
            j = 0
            while u < u1 - 1e-4:
                ue = min(u + rng.uniform(0.016, 0.04), u1)
                if u1 - ue < 0.008:
                    ue = u1
                Bk = _half(_half(Q, -nr[0], -nr[1], -u), nr[0], nr[1], ue)
                if len(Bk) >= 3 and _area(Bk) > 1e-6:
                    units.append({"k": "block", "poly": Bk, "area": _area(Bk), "pk": pid, "ub": ue, "ua": u,
                                  "shade": j % 2, "t": 0.25 * tg + 0.45 * tp + 0.012 * j + rng.uniform(0, 0.01)})
                    j += 1
                u = ue
    # Blöcke eines Pakets in räumlicher Folge: Zeiten innerhalb des Pakets monoton machen
    last = {}
    for u_ in units:
        if u_["k"] == "block":
            pk = u_["pk"]
            if pk in last and u_["t"] <= last[pk]:
                u_["t"] = last[pk] + 1e-6
            last[pk] = u_["t"]
    units.sort(key=lambda x: x["t"])
    return {"G": G, "units": units, "packets": packets, "At": sum(_area(P) for P in G),
            "Au": sum(u["area"] for u in units), "pp": pp}


def _mart_items(g, f, de, lath_op=0.85):
    items = [_poly(P, AUS, None) for P in g["G"]]
    target = f * g["Au"]
    cum = 0.0
    shown = []
    for u in g["units"]:
        if f < 1 and cum + u["area"] > target + 1e-12:
            break
        cum += u["area"]
        shown.append(u)
    reach = {}
    for u in shown:
        if u["k"] == "block":
            items.append(_poly(u["poly"], M_A if u["shade"] else M_B, M_LATH, 0.45))
            reach[u["pk"]] = max(reach.get(u["pk"], -9), u["ub"])
    for pk, ub in reach.items():
        k = g["packets"][pk]
        us = [v[0] * k["nr"][0] + v[1] * k["nr"][1] for v in k["P"]]
        h = _hatch(k["P"], k["th"], k["s"], k["o"], M_LATH, 0.55, lath_op)
        if ub >= max(us) - 1e-9:
            items.append(h)
        else:
            Q = _half(k["P"], k["nr"][0], k["nr"][1], ub)
            if len(Q) >= 3:
                items.append(_clip(Q, [h]))
    for u in shown:
        if u["k"] == "plate":
            A, B = u["A"], u["B"]
            items.append(_poly(u["poly"], M_PLATE if u["tone"] else "#8d97a2", M_PLATE_E, 0.6))
            items.append(_line((A[0] + 0.1 * (B[0] - A[0]), A[1] + 0.1 * (B[1] - A[1])),
                               (A[0] + 0.9 * (B[0] - A[0]), A[1] + 0.9 * (B[1] - A[1])), M_RIB, 1.1))
    items += [_poly(P, "none", M_GB, 1.1) for P in g["G"]]
    legend = []
    has_l = any(u["k"] == "block" for u in shown)
    has_p = any(u["k"] == "plate" for u in shown)
    if has_l:
        legend.append(_leg(M_A, _L(de, "Lattenmartensit: Pakete, Blöcke, Latten", "lath martensite: packets, blocks, laths")))
    if has_p:
        legend.append(_leg(M_PLATE, _L(de, "Plattenmartensit (Linsen mit Mittelrippe)", "plate martensite (lenses with midrib)")))
    if cum < g["At"] * 0.995:
        legend.append(_leg(AUS, _L(de, "Austenit / Restaustenit (γ)", "austenite / retained austenite (γ)")))
    legend.append(_leg(M_GB, _L(de, "ehemalige Austenitkorngrenze", "prior austenite grain boundary")))
    return items, legend, _cl(cum / g["At"])


# ============================================================================ Anlassen
@lru_cache(maxsize=16)
def _temper_geom(seed: int, C: float, n: int) -> dict:
    g = _mart_geom(seed, C, n, "lath")
    rng = np.random.default_rng(seed + 11)
    kC = _cl(C / 0.4, 0.5, 1.3)
    eps, cem, ra = [], [], []
    for u in g["units"]:
        if u["k"] != "block":
            continue
        pk = g["packets"][u["pk"]]
        th = pk["th"]
        X = _sample_in(u["poly"], int(rng.poisson(_area(_cut(u["poly"], VIEW)) * 650 * kC)) if _vis(u["poly"]) else 0, rng)
        for x, y in X:
            eps.append((x, y, th + (PI / 3 if rng.random() < 0.5 else -PI / 3), rng.uniform(0.02, 0.17),
                        rng.uniform(0.33, 0.46)))
        if rng.random() < 0.45:
            nr = pk["nr"]
            ch = _chord(_edges(u["poly"]), (nr[0] * u["ua"], nr[1] * u["ua"]), (math.cos(th), math.sin(th)))
            if ch:
                p0 = (nr[0] * u["ua"], nr[1] * u["ua"])
                ra.append(((p0[0] + ch[0] * math.cos(th), p0[1] + ch[0] * math.sin(th)),
                           (p0[0] + ch[1] * math.cos(th), p0[1] + ch[1] * math.sin(th))))
    for pk in g["packets"]:
        Q = _cut(pk["P"], VIEW)
        if len(Q) < 3:
            continue
        E = _edges(Q)
        a = round(pk["th"] % PI, 4)
        for k, (p0, d) in enumerate(_hatch_lines(_hpoly(pk["P"]), pk["th"], pk["s"], pk["o"])):
            if k % 2:                                    # Zementit auf jeder zweiten Lattengrenze
                continue
            ch = _chord(E, p0, d)
            if ch:
                t = ch[0] + rng.uniform(0.005, 0.03)
                while t < ch[1] - 0.005:
                    cem.append((p0[0] + t * d[0], p0[1] + t * d[1], a, rng.uniform(0.28, 0.42),
                                rng.uniform(0.010, 0.022) * kC ** 0.5, rng.uniform(0.3, 1.7)))
                    t += rng.uniform(0.04, 0.065) / kC ** 0.5
    # Budget: Lattenschraffur kostet ≈ 1200 Elemente, Teilchen bei hohem C ausdünnen
    eps = [e for e in eps if -0.01 <= e[0] <= 1.01 and -0.01 <= e[1] <= 1.01]
    eps = [eps[i] for i in sorted(rng.permutation(len(eps))[:620])] if len(eps) > 620 else eps
    cem = [cem[i] for i in sorted(rng.permutation(len(cem))[:760])] if len(cem) > 760 else cem
    return {"g": g, "eps": np.array(eps).reshape(-1, 5), "cem": np.array(cem).reshape(-1, 6), "ra": ra}


def _temper_items(T, s, de):
    g = T["g"]
    items = []
    fade = _cl((s - 0.4) / 0.55)
    ca, cb = _mix(M_A, "#e9e7df", fade), _mix(M_B, "#e2e0d8", fade)
    for u in g["units"]:
        if u["k"] == "block":
            items.append(_poly(u["poly"], ca if u["shade"] else cb, _mix(M_LATH, "#a9a59c", fade), 0.45))
    for k in g["packets"]:
        items.append(_hatch(k["P"], k["th"], k["s"], k["o"], M_LATH, 0.55, 0.85 * (1 - 0.82 * fade)))
    raop = 1 - _cl((s - 0.18) / 0.17)
    if raop > 0:
        items += [_line(a, b, RA, 1.4, 0.9 * raop) for a, b in T["ra"]]
    items += [_poly(P, "none", M_GB, 1.1) for P in g["G"]]
    e = T["eps"]
    parts = []
    if len(e) and s < 0.47:
        grow = np.clip((s - e[:, 3]) / 0.08, 0, 1)
        dis = np.clip((e[:, 4] - s) / 0.1, 0, 1)
        L = 0.0105 * grow * dis
        for i in np.where(L > 0.0016)[0]:
            parts.append((e[i, 0], e[i, 1], e[i, 2], L[i], 1.05))
    items += _dashes(parts, "#3d3631", lq=0.0012, wq=0.25)
    c = T["cem"]
    parts = []
    if len(c) and s > 0.28:
        Lf, z = c[:, 4], c[:, 5]
        g1 = np.clip((s - c[:, 3]) / 0.12, 0, 1)
        g2 = _cl((s - 0.5) / 0.25)
        g3 = _cl((s - 0.75) / 0.25)
        D = np.sqrt(4 * Lf * 520 * 1.3 / PI) * 0.8
        zc = 0.8 * g3
        vol = np.maximum(z - zc, 0)
        K = z.sum() / max(vol.sum(), 1e-9)
        L = Lf * g1 * (1 - g2) ** 1.5
        W = np.where(g3 > 0, D * np.sqrt(vol * K) * (1 + 0.25 * g3), 1.1 + (D * np.sqrt(z) - 1.1) * g2) * np.minimum(g1 * 3, 1)
        for i in range(len(c)):
            parts.append((c[i, 0], c[i, 1], c[i, 2], L[i], W[i]))
    items += _dashes(parts, CARB, wq=0.25)
    legend = [_leg(ca, _L(de, "Martensit → Ferrit (Latten verblassen: Erholung)", "martensite → ferrite (laths fade: recovery)")),
              _leg(M_GB, _L(de, "ehemalige Austenitkorngrenze", "prior austenite grain boundary"))]
    if s < 0.47:
        legend.append(_leg("#3d3631", _L(de, "ε-Carbid (Fe₂,₄C), fein, in den Latten", "ε-carbide (Fe₂.₄C), fine, inside laths")))
    if s > 0.28:
        legend.append(_leg(CARB, _L(de, "Zementit (Fe₃C): Filme → Kugeln", "cementite (Fe₃C): films → spheroids")))
    if raop > 0:
        legend.append(_leg(RA, _L(de, "Restaustenit-Filme (zerfallen in Stufe 2)", "retained austenite films (decompose in stage 2)")))
    return items, legend, _cl(s)


# ============================================================================ Bainit
@lru_cache(maxsize=16)
def _bain_up_geom(seed: int, n: int) -> dict:
    """Oberer Bainit: Garben paralleler Latten, die von Korngrenzen ins Korn wachsen; Zementit zwischen den Latten."""
    rng = np.random.default_rng(seed)
    G = _grains(rng, n)
    laths, carbs = [], []
    w, gap = 0.0105, 0.0042
    pitch = w + gap
    for P in G:
        cc = _ctr(P)
        m = int(_cl(round(_perim(P) / 0.3), 2, 4))
        sites = [_perim_pt(P, t) for t in (rng.uniform() + np.arange(m) / m + rng.uniform(-0.08, 0.08, m))]
        dirs = []
        seeds = []
        for q in sites:
            a = math.atan2(cc[1] - q[1], cc[0] - q[0]) + rng.uniform(-0.45, 0.45)
            d = (math.cos(a), math.sin(a))
            dirs.append(d)
            seeds.append((q[0] + 0.06 * d[0], q[1] + 0.06 * d[1]))
        cells = _cells(np.array(seeds), box=P)
        tg = rng.uniform(0, 0.15)
        for q, d, Q in zip(sites, dirs, cells):
            if len(Q) < 3 or not _vis(Q):
                continue
            nr = (-d[1], d[0])
            E = _edges(Q)
            us = [(v[0] - q[0]) * nr[0] + (v[1] - q[1]) * nr[1] for v in Q]
            ts = tg + rng.uniform(0, 0.15)
            u = min(us) + pitch * 0.5
            row = []
            while u < max(us) - w * 0.4:
                p0 = (q[0] + u * nr[0], q[1] + u * nr[1])
                ch = _chord(E, p0, d)
                if ch and ch[1] - ch[0] > 0.02:
                    Lm = (ch[1] - ch[0]) * rng.uniform(0.86, 0.99)
                    row.append({"p0": p0, "t0": ch[0], "Lm": Lm, "d": d, "nr": nr, "Q": Q,
                                "t": ts + 0.03 * rng.uniform(), "v": rng.uniform(0.85, 1.15), "u": u})
                else:
                    row.append(None)
                u += pitch
            # Nachbarlatten entstehen nacheinander von der Mitte der Garbe aus (sympathetische Keimbildung)
            k0 = len(row) // 2
            for k, r in enumerate(row):
                if r:
                    r["t"] += 0.007 * abs(k - k0)
            laths += [r for r in row if r]
            for a_, b_ in zip(row, row[1:]):
                if not a_ or not b_:
                    continue
                pg = (0.5 * (a_["p0"][0] + b_["p0"][0]), 0.5 * (a_["p0"][1] + b_["p0"][1]))
                t0 = max(a_["t0"], b_["t0"]) + 0.006
                t1 = min(a_["t0"] + a_["Lm"], b_["t0"] + b_["Lm"]) - 0.006
                t = t0 + rng.uniform(0, 0.02)
                while t < t1:
                    Lc = rng.uniform(0.01, 0.024)
                    carbs.append((pg[0] + (t + Lc / 2) * d[0], pg[1] + (t + Lc / 2) * d[1], math.atan2(d[1], d[0]),
                                  Lc, t + Lc - min(a_["t0"], b_["t0"]), id(a_), id(b_)))
                    t += Lc + rng.uniform(0.022, 0.045)
    idx = {id(r): i for i, r in enumerate(laths)}
    carbs = [(x, y, a, L, need, idx[ia], idx[ib]) for x, y, a, L, need, ia, ib in carbs]
    return {"G": G, "laths": laths, "carbs": carbs, "w": w, "At": sum(_area(P) for P in G)}


def _lath_len(r, f):
    k = _cl((f - r["t"]) / max(0.86 - r["t"], 0.05) * r["v"])
    return r["Lm"] * k


def _bain_up_items(g, f, de, matrix=AUS):
    items = [_poly(P, matrix, None) for P in g["G"]]
    w = g["w"]
    Ls = [_lath_len(r, f) for r in g["laths"]]
    done = 0.0
    parts = []
    for r, L in zip(g["laths"], Ls):
        if L < 0.003:
            continue
        d, p0 = r["d"], r["p0"]
        m = r["t0"] + L / 2
        # Latte als Strich mit runden Enden (kompakt): Länge ohne die Kappen
        parts.append((p0[0] + m * d[0], p0[1] + m * d[1], math.atan2(d[1], d[0]), max(L - w * 0.6, 0.0016), w * 520))
        done += L * w
    items += _dashes(parts, B_UP, lq=0.003, wq=0.5)
    parts = []
    for x, y, a, L, need, ia, ib in g["carbs"]:
        reach = min(Ls[ia] + g["laths"][ia]["t0"], Ls[ib] + g["laths"][ib]["t0"]) - min(g["laths"][ia]["t0"], g["laths"][ib]["t0"])
        if reach > need + 0.01:
            k = _cl((reach - need - 0.01) / 0.03) * _cl((f - 0.25) / 0.3)
            if k > 0:
                parts.append((x, y, a, L * (0.4 + 0.6 * k), 0.9 + 0.8 * k))
    items += _dashes(parts, CARB, lq=0.002, wq=0.3)
    items += [_poly(P, "none", GB, 0.9) for P in g["G"]]
    legend = [_leg(B_UP, _L(de, "Bainitferrit: Latten in Garben", "bainitic ferrite: laths in sheaves")),
              _leg(CARB, _L(de, "Zementit ZWISCHEN den Latten", "cementite BETWEEN the laths")),
              _leg(matrix, _L(de, "Austenit (γ) → beim Abkühlen Martensit/Restaustenit", "austenite (γ) → martensite/retained austenite on cooling"))]
    return items, legend, _cl(done / g["At"])


@lru_cache(maxsize=16)
def _bain_lo_geom(seed: int, n: int) -> dict:
    """Unterer Bainit: dünne Platten von Korngrenzen und von anderen Platten aus; Carbide in den Platten, eine
    Richtung, ≈ 60° zur Plattenachse."""
    rng = np.random.default_rng(seed)
    G = _grains(rng, n)
    plates = []
    for P in G:
        b = rng.uniform(0, PI)
        dirs = [b + k * PI / 3 + rng.normal(0, 0.06) for k in range(3)]
        tg = rng.uniform(0, 0.25)
        pls = _plates_in(P, rng, hw_ratio=0.072, nmax=16, Lmin=0.035, dirs=dirs, Lcap=0.22, from_edge=True)
        pls += _plates_in(P, rng, hw_ratio=0.072, nmax=32, Lmin=0.03, dirs=dirs, Lcap=0.16, init=pls)
        pls += _plates_in_more(P, rng, pls, dirs)
        for k, (A, B, hw) in enumerate(pls):
            L = math.hypot(B[0] - A[0], B[1] - A[1])
            if not _vis(_lens(A, B, hw, 3)):
                continue
            d = ((B[0] - A[0]) / L, (B[1] - A[1]) / L)
            side = 1 if rng.random() < 0.5 else -1
            ca = math.atan2(d[1], d[0]) + side * math.radians(rng.uniform(55, 62))
            cs = []
            s = rng.uniform(0.006, 0.012)
            while s < L - 0.006:
                cs.append(s)
                s += rng.uniform(0.011, 0.015)
            plates.append({"A": A, "d": d, "L": L, "hw": hw, "t": tg + 0.55 * k / max(len(pls), 1) + rng.uniform(0, 0.05),
                           "ca": ca, "cs": cs})
    return {"G": G, "plates": plates, "At": sum(_area(P) for P in G)}


def _plates_in_more(P, rng, pls, dirs):
    """Weitere Platten, die an bestehenden Platten keimen (autokatalytisch), mit derselben Sperrlogik."""
    out = list(pls)
    E = _edges(P)
    for _ in range(40):
        if len(out) >= 34 or not pls:
            break
        A, B, hw = out[int(rng.integers(len(out)))]
        u = rng.uniform(0.2, 0.8)
        dx, dy = B[0] - A[0], B[1] - A[1]
        L = math.hypot(dx, dy)
        nx, ny = -dy / L, dx / L
        sg = 1 if rng.random() < 0.5 else -1
        h = hw * 4 * u * (1 - u) + 0.004
        p = (A[0] + u * dx + sg * nx * h, A[1] + u * dy + sg * ny * h)
        if not _inside(E, p, 0.003):
            continue
        a = dirs[int(rng.integers(len(dirs)))] + rng.normal(0, 0.05)
        d = (math.cos(a), math.sin(a))
        if d[0] * nx * sg + d[1] * ny * sg < 0:
            d = (-d[0], -d[1])
        if abs(d[0] * dx / L + d[1] * dy / L) > 0.9:
            continue
        ch = _chord(E, p, d)
        if not ch:
            continue
        t1 = ch[1]
        for A2, B2, hw2 in out:
            sx, sy = B2[0] - A2[0], B2[1] - A2[1]
            den = d[0] * sy - d[1] * sx
            if abs(den) < 1e-9:
                continue
            ax, ay = A2[0] - p[0], A2[1] - p[1]
            t = (ax * sy - ay * sx) / den
            uu = (ax * d[1] - ay * d[0]) / den
            if 0 <= uu <= 1 and t > 0.001:
                sn = abs(den) / math.hypot(sx, sy)
                t1 = min(t1, t - hw2 * 4 * uu * (1 - uu) / max(sn, 0.3) - 0.002)
        Lp = min(t1, rng.uniform(0.06, 0.2))
        if Lp < 0.035:
            continue
        out.append((p, (p[0] + Lp * d[0], p[1] + Lp * d[1]), 0.072 * Lp + 0.0015))
    return out[len(pls):]


def _bain_lo_items(g, f, de, matrix=AUS):
    items = [_poly(P, matrix, None) for P in g["G"]]
    parts = []
    done = 0.0
    for pl in g["plates"]:
        k = _cl((f - pl["t"]) / 0.3)
        if k <= 0:
            continue
        L = pl["L"] * k
        A, d = pl["A"], pl["d"]
        B = (A[0] + L * d[0], A[1] + L * d[1])
        hw = pl["hw"] * (0.6 + 0.4 * k)
        Lp = _lens(A, B, hw, m=6, expo=0.7)
        items.append(_poly(Lp, B_LO, B_LO_E, 0.5))
        done += _area(Lp)
        kc = _cl((f - pl["t"] - 0.12) / 0.25)
        if kc > 0:
            sa = abs(math.sin(pl["ca"] - math.atan2(d[1], d[0])))
            for s in pl["cs"]:
                if s > L - 0.006:
                    break
                u = s / L
                h = hw * (4 * u * (1 - u)) ** 0.7
                cl = 2 * h / max(sa, 0.3) * 0.75 * kc
                if cl > 0.002:
                    parts.append((A[0] + s * d[0], A[1] + s * d[1], pl["ca"], cl, 0.9))
    items += _dashes(parts, CARB, lq=0.001, wq=0.3)
    items += [_poly(P, "none", GB, 0.9) for P in g["G"]]
    legend = [_leg(B_LO, _L(de, "Bainitplatten (unterer Bainit)", "bainite plates (lower bainite)")),
              _leg(CARB, _L(de, "Carbide IN den Platten, eine Richtung, ≈ 60° zur Achse", "carbides INSIDE the plates, one variant, ≈ 60° to the axis")),
              _leg(matrix, _L(de, "Austenit (γ) → beim Abkühlen Martensit", "austenite (γ) → martensite on cooling"))]
    return items, legend, _cl(done / g["At"])


# ============================================================================ Aushärten Al-Cu
@lru_cache(maxsize=16)
def _prec_geom(seed: int, n: int) -> dict:
    rng = np.random.default_rng(seed)
    G = _grains(rng, n)
    P_ = []
    gbp = []
    for P in G:
        Q = _cut(P, VIEW)
        if len(Q) < 3:
            continue
        phi = rng.uniform(0, PI / 2)
        X = _sample_in(P, int(rng.poisson(_area(Q) * 1050)), rng)
        A = np.array(P)
        B = np.roll(A, -1, 0)
        dist = _seg_dist(X, A, B)
        for (x, y), dd in zip(X, dist):
            P_.append((x, y, phi + (PI / 2 if rng.random() < 0.5 else 0.0), dd))
        for i in range(len(P)):
            a, b = P[i], P[(i + 1) % len(P)]
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            t = rng.uniform(0, 0.03)
            while t < L:
                q = (a[0] + (b[0] - a[0]) * t / L, a[1] + (b[1] - a[1]) * t / L)
                if -0.01 < q[0] < 1.01 and -0.01 < q[1] < 1.01:
                    gbp.append((q[0], q[1], rng.uniform(0.5, 1.5)))
                t += rng.uniform(0.022, 0.04)
    X = np.array(P_).reshape(-1, 4)
    N = len(X)
    r = rng.uniform(size=(N, 8))
    lev = np.zeros(N, int)
    lev[r[:, 0] < 0.45] = 1
    lev[(lev == 1) & (r[:, 1] < 0.6)] = 2
    lev[(lev == 2) & (r[:, 2] < 0.3)] = 3
    return {"G": G, "X": X, "lev": lev, "r": r, "gb": np.array(gbp).reshape(-1, 3)}


def _prec_items(g, s, de):
    items = [_poly(P, AL, AL_GB, 0.9) for P in g["G"]]
    X, lev, r = g["X"], g["lev"], g["r"]
    tGP = 0.05 + 0.15 * r[:, 3]
    t2 = 0.27 + 0.11 * r[:, 4]
    pfz = 0.035 * _cl((s - 0.52) / 0.4)
    near = np.clip((X[:, 3] - pfz) / 0.006, 0, 1)
    dots, d2, d3 = [], [], []
    for i in range(len(X)):
        x, y, a, dist = X[i]
        lv = lev[i]
        # GP-Zonen
        gp_end = t2[i] if lv >= 1 else 0.3 + 0.12 * r[i, 5]
        if s > tGP[i] and s < gp_end + 0.04:
            # GP-Zone: Scheibchen auf {100}, im Schnitt kantig als kurzer Strich
            k = _cl((s - tGP[i]) / 0.06) * _cl((gp_end + 0.04 - s) / 0.04)
            dots.append((x, y, a, 0.0045 * k, 0.8))
        if lv < 1 or s < t2[i]:
            continue
        L = 0.0045 + 0.0065 * _cl((s - t2[i]) / 0.07)
        w = 0.95
        if lv >= 2:
            g3 = _cl((s - 0.47 - 0.05 * r[i, 6]) / 0.12)
            Lp = 0.022 + 0.018 * r[i, 7]
            L = L + (Lp - 0.011) * g3
            w = 0.95 + 1.1 * g3
        else:
            L *= _cl((0.6 + 0.06 * r[i, 6] - s) / 0.08)
        if lv >= 3:
            g4 = _cl((s - 0.74) / 0.13)
            L *= (1 - g4) ** 1.5
            w = w + (5.2 * (0.5 + r[i, 6]) ** 0.5 - w) * g4
            g5 = _cl((s - 0.87) / 0.13)
            if g5 > 0:
                zc = 0.55 * g5
                v = max(r[i, 6] + 0.2 - zc, 0) / (1.2 - zc)
                w = 5.2 * math.sqrt(v * 1.25) * (1 + 0.3 * g5) if v > 0 else 0.0
        elif lv == 2:
            k = _cl((0.9 + 0.04 * r[i, 5] - s) / 0.1)
            L *= k
            w *= k ** 0.5
        L *= near[i]
        w *= near[i] if lv < 3 else 1.0
        if L > 1e-4 or (lv >= 3 and w > 0.3):
            (d3 if lv >= 2 else d2).append((x, y, a, L, w))
    items += _dashes(dots, "#8a6a52", lq=0.0009, wq=0.25)
    items += _dashes(d2, "#7a5a44", lq=0.0012, wq=0.25)
    items += _dashes(d3, AL_PREC, lq=0.0015, wq=0.3)
    gb = g["gb"]
    kgb = _cl((s - 0.5) / 0.45) ** (1 / 3) if s > 0.5 else 0.0
    if kgb > 0:
        items += _dots([(x, y, 0.0055 * z * kgb) for x, y, z in gb], AL_PREC)
    legend = [_leg(AL, _L(de, "α-Al-Mischkristall", "α-Al solid solution"))]
    if 0.05 < s < 0.45:
        legend.append(_leg("#8a6a52", _L(de, "GP-Zonen (Cu-Scheibchen, kohärent)", "GP zones (Cu discs, coherent)")))
    if 0.27 < s < 0.65:
        legend.append(_leg("#7a5a44", _L(de, "θ″ (kohärente Plättchen)", "θ″ (coherent platelets)")))
    if s > 0.47:
        legend.append(_leg(AL_PREC, _L(de, "θ′ (teilkohärent, {100}) / θ-Al₂Cu (inkohärent)", "θ′ (semi-coherent, {100}) / θ-Al₂Cu (incoherent)")))
    if s > 0.55:
        legend.append(_leg(AL, _L(de, "ausscheidungsfreie Zone (PFZ) an den Korngrenzen", "precipitate-free zone (PFZ) at grain boundaries")))
    if s < 0.08:
        legend[0] = _leg(AL, _L(de, "übersättigter Mischkristall (Cu gelöst)", "supersaturated solid solution (Cu dissolved)"))
    return items, legend, _cl(s)


# ============================================================================ Rekristallisation
@lru_cache(maxsize=16)
def _rex_geom(seed: int, n_def: int, n_new: int) -> dict:
    rng = np.random.default_rng(seed)
    D = _grains(rng, n_def, k=3.6)
    V = {}
    for P in D:
        for v in P:
            V[(round(v[0], 3), round(v[1], 3))] = v
    V = [v for v in V.values() if -0.12 < v[0] < 1.12 and -0.12 < v[1] < 1.12]
    rng.shuffle(V)
    need = int(n_new * 1.35)
    S = []
    for v in V:
        if len(S) >= need * 0.6:
            break
        if all(math.hypot(v[0] - s[0], v[1] - s[1]) > 0.07 for s in S):
            S.append(tuple(v))
    tries = 0
    while len(S) < need and tries < 4000:
        tries += 1
        P = D[int(rng.integers(len(D)))]
        i = int(rng.integers(len(P)))
        a, b = P[i], P[(i + 1) % len(P)]
        u = rng.uniform()
        q = (a[0] + u * (b[0] - a[0]), a[1] + u * (b[1] - a[1]))
        if not (-0.12 < q[0] < 1.12 and -0.12 < q[1] < 1.12):
            continue
        if all(math.hypot(q[0] - s[0], q[1] - s[1]) > 0.07 for s in S):
            S.append(q)
    S = np.array(S)
    box = [(-0.14, -0.14), (1.14, -0.14), (1.14, 1.14), (-0.14, 1.14)]
    cells = _cells(S, box=box)
    t = rng.uniform(0.1, 0.55, len(S))
    R = np.array([max(math.hypot(v[0] - s[0], v[1] - s[1]) for v in c) * 1.06 + 1e-3 if c else 0.0
                  for c, s in zip(cells, S)])
    z = rng.uniform(0, 1, len(S))
    slip = [(rng.choice([-1, 1]) * rng.uniform(0.45, 0.8), rng.uniform(0.013, 0.02), rng.uniform(),
             _mix(DEF, "#c4cad2", rng.uniform())) for _ in D]
    return {"D": D, "S": S, "cells": cells, "t": t, "R": R, "z": z, "slip": slip, "box": box}


def _rex_items(g, f, de, twins=False):
    gp = _cl(f / 0.7)
    h = _cl((f - 0.7) / 0.3)
    items = []
    so = 0.8 * (1 - 0.45 * _cl(gp / 0.2))
    if h < 1 and gp < 1:
        for P, (a, s, o, col) in zip(g["D"], g["slip"]):
            items.append(_poly(P, col, GB, 0.8))
            items.append(_hatch(P, a, s, o, DEF_SLIP, 0.55, so))
    done = 0.0
    At = 1.0
    if h <= 0:
        for c, s_, t, R in zip(g["cells"], g["S"], g["t"], g["R"]):
            if len(c) < 3 or gp <= t:
                continue
            k = (gp - t) / (1 - t)
            rev = c if k >= 1 else _cut(_disc(s_, R * k), c)
            if len(rev) >= 3:
                items.append(_poly(rev, REX, GB, 0.85))
                done += _area(_cut(rev, VIEW))
    else:
        w = h * 0.09 * (g["z"] - 0.55)
        for c in _cells(g["S"], w=w, box=g["box"]):
            if len(c) >= 3 and _vis(c):
                items.append(_poly(c, REX, GB, 0.85))
        done = 1.0
    legend = []
    if gp < 1:
        legend.append(_leg(DEF, _L(de, "verformte Körner mit Gleitbändern", "deformed grains with slip bands")))
    if gp > 0.15:
        legend.append(_leg(REX, _L(de, "rekristallisierte Körner (versetzungsarm)", "recrystallised grains (low dislocation density)")))
    return items, legend, _cl(done / At)


# ============================================================================ Erstarrung, Dendriten
@lru_cache(maxsize=16)
def _dend_geom(seed: int, n_col: int, n_eq: int, lam2: float = 0.03, wall: bool = True) -> dict:
    """Säulendendriten von der Formwand (unten) und gleichachsige Dendriten im Inneren; Arme als Stämme mit
    Seitenarmen. Jeder Dendrit bleibt in seiner Zelle."""
    rng = np.random.default_rng(seed)
    nuc = []
    if wall and n_col:
        for i in range(n_col):
            x = (i + 0.5 + rng.uniform(-0.2, 0.2)) / n_col
            nuc.append(("col", (x, 0.2), rng.uniform(-0.18, 0.18)))
    k = 0
    while sum(1 for q in nuc if q[0] == "eq") < n_eq and k < 400:
        k += 1
        p = (rng.uniform(0.12, 0.88), rng.uniform(0.5 if wall and n_col else 0.12, 0.9))
        if all(math.hypot(p[0] - q[1][0], p[1] - q[1][1]) > (0.26 if wall and n_col else 0.3) for q in nuc):
            nuc.append(("eq", p, rng.uniform(0, PI / 2)))
    box = [(-0.05, -0.05), (1.05, -0.05), (1.05, 1.05), (-0.05, 1.05)]
    cells = _cells(np.array([q[1] for q in nuc]), box=box)
    arms = []
    for (kind, p, ang), Q in zip(nuc, cells):
        if len(Q) < 3:
            continue
        E = _edges(Q)
        if kind == "col":
            d = (math.sin(ang), math.cos(ang))
            nr = (-d[1], d[0])
            us = [(v[0] - p[0]) * nr[0] + (v[1] - p[1]) * nr[1] for v in Q]
            lam1 = 0.075
            u = min(us) + lam1 * rng.uniform(0.35, 0.65)
            t0 = rng.uniform(0.0, 0.08)
            while u < max(us) - lam1 * 0.3:
                q = (p[0] + u * nr[0], p[1] + u * nr[1])
                ch = _chord(E, q, d)
                if ch:
                    root = (q[0] + ch[0] * d[0], q[1] + ch[0] * d[1])
                    Lm = (ch[1] - ch[0]) - 0.012
                    arms.append(_arm(root, d, Lm, E, lam1 * 0.48, lam2, rng, t0 + rng.uniform(0, 0.05), 0.72, False))
                u += lam1 * rng.uniform(0.9, 1.1)
        else:
            t0 = rng.uniform(0.28, 0.42)
            for j in range(4):
                a = ang + j * PI / 2 + rng.normal(0, 0.04)
                d = (math.cos(a), math.sin(a))
                ch = _chord(E, p, d)
                if not ch:
                    continue
                Lm = ch[1] * 0.9
                arms.append(_arm(p, d, Lm, E, 9.0, lam2, rng, t0, 0.5, True))
    return {"cells": [Q for Q in cells if len(Q) >= 3], "arms": arms, "nuc": nuc}


def _arm(root, d, Lm, E, l2cap, lam2, rng, t0, dur, eq):
    nr = (-d[1], d[0])
    secs = []
    for sg in (1, -1):
        s = lam2 * rng.uniform(0.5, 1.2)
        while s < Lm - 0.012:
            q = (root[0] + s * d[0], root[1] + s * d[1])
            dd = (sg * nr[0], sg * nr[1])
            ch = _chord(E, q, dd)
            lim = (ch[1] - 0.006) if ch else 0.0
            # Hüllkurve: nahe der Spitze kurze Arme (parabolische Spitze), gleichachsig auch nahe dem Keim
            env = min(0.9 * s, 0.75 * (Lm - s) + 0.01) if eq else l2cap * (0.3 + 0.7 * math.sqrt(max(0.0, 1 - s / Lm)))
            l2 = min(l2cap, lim, env) * rng.uniform(0.55, 1.0)
            if l2 > 0.006 and rng.random() > 0.08:
                secs.append((s, sg, l2))
            s += lam2 * rng.uniform(0.8, 1.25)
    secs.sort()
    return {"root": root, "d": d, "Lm": max(Lm, 0.0), "secs": secs, "t0": t0, "dur": dur}


def _arm_state(a, f):
    T = a["Lm"] * _cl((f - a["t0"]) / a["dur"])
    out = []
    for s, sg, l2 in a["secs"]:
        if T > s + 0.006:
            out.append((s, sg, min(l2, 0.75 * (T - s - 0.006))))
    return T, out


def _arm_paths(a, f):
    """Linienzüge eines Dendritenarms mit relativer Breite: Stamm (Wurzel dicker als Spitze) und je Seite ein
    Zickzack (Wurzel → Spitze → Wurzel → nächste Wurzel …), der innere Teil der Seitenarme nochmals breiter, damit
    die Arme spitz zulaufen."""
    T, secs = _arm_state(a, f)
    if T < 0.002:
        return [], 0.0, 0.0
    r, d = a["root"], a["d"]
    nr = (-d[1], d[0])
    paths = [([r, (r[0] + T * d[0], r[1] + T * d[1])], 0.7)]
    if T > 0.02:
        paths.append(([r, (r[0] + 0.6 * T * d[0], r[1] + 0.6 * T * d[1])], 1.0))
    L2 = 0.0
    for sg in (1, -1):
        full, half = [], []
        for s, g_, l2 in secs:
            if g_ != sg:
                continue
            b = (r[0] + s * d[0], r[1] + s * d[1])
            full += [b, (b[0] + sg * l2 * nr[0], b[1] + sg * l2 * nr[1]), b]
            half += [b, (b[0] + sg * 0.5 * l2 * nr[0], b[1] + sg * 0.5 * l2 * nr[1]), b]
            L2 += l2
        if full:
            paths.append((full, 0.42))
            paths.append((half, 0.6))
    return paths, T, L2


def _dend_draw(arm_paths, wp, layers):
    """layers: [(Farbe, Zusatzbreite px, Faktor)], von aussen nach innen; jede Lage über allen Armen. Eine schmale
    Kernlage (Faktor < 0,6) folgt nur der Mittellinie. Koordinaten auf 3 Stellen (dicke Striche, kleineres JSON)."""
    out = []
    for c, add, mul in layers:
        for ps in arm_paths:
            for pts, rel in ps:
                if mul < 0.6 and rel not in (0.7, 0.42):
                    continue
                out.append(_op({"t": "pline", "p": [[round(float(x), 3), round(float(y), 3)] for x, y in pts],
                                "stroke": c, "sw": round(float(wp * rel * mul + add), 2)}, None))
    return out


def _dend_items(g, f, de, f_eut=0.3, style="melt", col=DEND, edge=DEND_E, eut_kind="lamellar"):
    wp = 3.0 + 10.0 * (1 - _cl(f_eut)) ** 0.6
    ws = 0.5 * wp
    items = []
    e = _cl((f - 0.85) / 0.15) if style == "melt" else 1.0
    if style == "melt":
        items.append(_poly(VIEW, LIQ, None))
    rng = np.random.default_rng(len(g["arms"]))
    if e > 0 and eut_kind != "none":
        for Q in g["cells"]:
            items.append(_poly(Q, EUT_BG, None, op=e))
            if eut_kind == "lamellar":
                items.append(_hatch(Q, rng.uniform(0, PI), 0.0085, rng.uniform(), EUT_LAM, 0.9, 0.85 * e))
    paths = []
    solid = 0.0
    for a in g["arms"]:
        ps, T, L2 = _arm_paths(a, f)
        if ps:
            paths.append(ps)
            solid += T * 0.85 * wp / 520 + L2 * ws / 520
    if style == "coring":
        layers = [(edge, 1.8, 1.0), ("#c3ccd6", 0.0, 1.0), ("#eef2f6", 0.0, 0.42)]
    else:
        layers = [(edge, 1.6, 1.0), (col, 0.0, 1.0)]
    items += _dend_draw(paths, wp, layers)
    frac = _cl(solid * 1.25) * (1 - f_eut) + e * f_eut if style == "melt" else 1.0
    return items, frac


def _dend_segments(g, f=1.0):
    A, B, W = [], [], []
    for a in g["arms"]:
        T, secs = _arm_state(a, f)
        r, d = a["root"], a["d"]
        nr = (-d[1], d[0])
        A.append(r)
        B.append((r[0] + T * d[0], r[1] + T * d[1]))
        W.append(0)
        for s, sg, l2 in secs:
            b = (r[0] + s * d[0], r[1] + s * d[1])
            A.append(b)
            B.append((b[0] + sg * l2 * nr[0], b[1] + sg * l2 * nr[1]))
            W.append(1)
    return np.array(A).reshape(-1, 2), np.array(B).reshape(-1, 2), np.array(W)


# ============================================================================ Einzelbilder (Galerie)
def _sk_ferrit(rng, de, n=22, fill=FER, label=None):
    G = _grains(rng, n)
    items = [_poly(P, _mix(fill, "#d9d6cc", rng.uniform(0, 0.35)), FER_GB, 0.8) for P in G]
    return items, [_leg(fill, label or _L(de, "Ferrit (α), polygonal", "ferrite (α), polygonal"))]


def _twin_bands(P, rng, nmax=3, fill="#d0dae6", stroke="#7d8794"):
    out = []
    E = _edges(P)
    a = rng.uniform(0, PI)
    d = (math.cos(a), math.sin(a))
    nr = (-d[1], d[0])
    us = [v[0] * nr[0] + v[1] * nr[1] for v in P]
    for _ in range(int(rng.integers(1, nmax + 1))):
        w = rng.uniform(0.006, 0.026)
        u = rng.uniform(min(us) + 0.01, max(us) - w - 0.005)
        if u >= max(us) - w:
            continue
        S = _half(_half(P, -nr[0], -nr[1], -u), nr[0], nr[1], u + w)
        if rng.random() < 0.3 and len(S) >= 3:
            c = _ctr(S)
            sg = 1 if rng.random() < 0.5 else -1
            S = _half(S, sg * d[0], sg * d[1], sg * (c[0] * d[0] + c[1] * d[1]) + rng.uniform(-0.03, 0.03))
        if len(S) >= 3:
            out.append(_poly(S, fill, stroke, 0.6))
    return out


def _sk_austenit(rng, de, n=14):
    G = _grains(rng, n)
    items = []
    shades = ["#e6edf4", "#dde6f0", "#eef2f7", "#d6e0ec", "#e2e9f2"]
    for P in G:
        base = shades[int(rng.integers(len(shades)))]
        items.append(_poly(P, base, GB, 0.85))
        items += _twin_bands(P, rng, 3, _mix(base, "#9fb0c4", 0.35), "#6f7a88")
    return items, [_leg("#e2e9f2", _L(de, "Austenit (γ)", "austenite (γ)")),
                   _leg("#c6d1de", _L(de, "Glühzwillinge (gerade, parallele Grenzen)", "annealing twins (straight, parallel boundaries)"))]


def _sk_widman(rng, de, n=6):
    G = _grains(rng, n)
    items = []
    plates = []
    for P in G:
        fac = rng.uniform(0.6, 1.4, len(P))
        core = _inset(P, [0.011 * x for x in fac])
        items.append(_poly(P, FER, FER_GB, 0.5))
        if len(core) < 3:
            continue
        items.append(_poly(core, "#a8957f", P_EDGE, 0.5))
        items.append(_hatch(core, rng.uniform(0, PI), 0.0085, rng.uniform(), P_LAM, 0.9, 0.45))
        E = _edges(core)
        cc = _ctr(core)
        for i in range(len(core)):
            a, b = core[i], core[(i + 1) % len(core)]
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            if L < 0.06 or rng.random() < 0.25:
                continue
            e = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
            nin = (-e[1], e[0])
            dd = _rot(nin, rng.uniform(-0.55, 0.55))
            s = rng.uniform(0.012, 0.03)
            Lmax = rng.uniform(0.1, 0.24)
            while s < L - 0.012:
                base = (a[0] + s * e[0], a[1] + s * e[1])
                ch = _chord(E, (base[0] + 0.001 * nin[0], base[1] + 0.001 * nin[1]), dd)
                if ch and rng.random() < 0.85:
                    Lp = min(Lmax * rng.uniform(0.6, 1.0), ch[1] * 0.55)
                    w = rng.uniform(0.007, 0.012)
                    tip = (base[0] + Lp * dd[0], base[1] + Lp * dd[1])
                    W = [(base[0] - e[0] * w / 2 - nin[0] * 0.004, base[1] - e[1] * w / 2 - nin[1] * 0.004),
                         (base[0] + e[0] * w / 2 - nin[0] * 0.004, base[1] + e[1] * w / 2 - nin[1] * 0.004), tip]
                    plates.append(_poly(_ccw(W), FER, None))
                s += rng.uniform(0.02, 0.032)
    items += plates
    return items, [_leg(FER, _L(de, "Ferrit: Korngrenzensaum und Widmanstätten-Seitenplatten", "ferrite: grain-boundary allotriomorphs and Widmanstätten side plates")),
                   _leg("#a8957f", _L(de, "Perlit (fein, kaum aufgelöst)", "pearlite (fine, barely resolved)"))]


def _sk_ledeb(rng, de, C=3.8):
    items = [_poly(VIEW, CEM, None)]
    fprim = _cl((4.3 - C) / (4.3 - 2.11))
    segA = np.zeros((0, 2))
    segB = np.zeros((0, 2))
    segW = 0.0
    if fprim > 0.02:
        g = _dend_geom(_seed(rng), 0, 3 + int(fprim * 4), 0.035, False)
        wp = 9 + 16 * fprim
        paths = [_arm_paths(a, 1.0)[0] for a in g["arms"]]
        items += _dend_draw(paths, wp, [(CEM_EDGE, 1.2, 1.0), (P_DARK, 0.0, 1.0)])
        segA, segB, _ = _dend_segments(g)
        segW = 0.6 * wp / 520 / 2 + 0.012
    cells = _grains(rng, 9)
    dots = []
    for P in cells:
        Q = _cut(P, VIEW)
        if len(Q) < 3:
            continue
        cc = _ctr(P)
        phi = rng.uniform(0, PI)
        d = (math.cos(phi), math.sin(phi))
        nr = (-d[1], d[0])
        E = _edges(P)
        x0, y0, x1, y1 = _bbox(P)
        Rr = max(math.hypot(v[0] - cc[0], v[1] - cc[1]) for v in P)
        a = 0.026
        pts = []
        for i in range(-int(Rr / a) - 2, int(Rr / a) + 3):
            for j in range(-int(Rr / (a * 0.85)) - 2, int(Rr / (a * 0.85)) + 3):
                u = (i + 0.5 * (j % 2)) * a + rng.normal(0, a * 0.12)
                v = j * a * 0.85 + rng.normal(0, a * 0.12)
                q = (cc[0] + u * d[0] + v * nr[0], cc[1] + u * d[1] + v * nr[1])
                if -0.02 < q[0] < 1.02 and -0.02 < q[1] < 1.02 and _inside(E, q, 0.004):
                    pts.append(q)
        if not pts:
            continue
        X = np.array(pts)
        rr = np.hypot(X[:, 0] - cc[0], X[:, 1] - cc[1]) / max(Rr, 1e-6)
        keep = _seg_dist(X, segA, segB) > segW if len(segA) else np.ones(len(X), bool)
        for (x, y), q, k in zip(X, rr, keep):
            if k:
                r = rng.uniform(0.0055, 0.009) * (1 + 0.4 * q)
                if rng.random() < 0.35:              # Teil der Inseln länglich (Stäbchen quer zur Kolonie)
                    dots.append((x, y, phi + PI / 2 + rng.normal(0, 0.35), r * rng.uniform(1.2, 2.6), 2 * r * 520 * 0.8))
                else:
                    dots.append((x, y, 0.0, 0.0, 2 * r * 520))
    items += _dashes(dots, P_DARK, lq=0.003, wq=1.2)
    leg = [_leg(CEM, _L(de, "Zementit (eutektisch, hell)", "cementite (eutectic, bright)")),
           _leg(P_DARK, _L(de, "Perlit (aus Austenit des Ledeburits, dunkle Inseln)", "pearlite (from the ledeburite austenite, dark islands)"))]
    if fprim > 0.02:
        leg.append(_leg(P_DARK, _L(de, "Primärdendriten (γ → Perlit)", "primary dendrites (γ → pearlite)")))
    return items, leg


def _sk_delta(rng, de):
    G = _grains(rng, 7, k=3.2, vert=True)
    shades = ["#e6edf4", "#dde6f0", "#eef2f7", "#d6e0ec"]
    items = [_poly(P, shades[int(rng.integers(4))], GB, 0.8) for P in G]
    parts = []
    for P in G:
        E = _edges(P)
        cx = _ctr(P)
        ang = PI / 2 + rng.normal(0, 0.12)
        d = (math.cos(ang), math.sin(ang))
        nr = (-d[1], d[0])
        us = [(v[0] - cx[0]) * nr[0] + (v[1] - cx[1]) * nr[1] for v in P]
        u = min(us) + rng.uniform(0.015, 0.03)
        while u < max(us) - 0.012:
            q = (cx[0] + u * nr[0], cx[1] + u * nr[1])
            ch = _chord(E, q, d)
            if ch:
                t = ch[0] + 0.01
                pts = []
                off = 0.0
                while t < ch[1] - 0.01:
                    off = 0.7 * off + rng.normal(0, 0.004)
                    pts.append((q[0] + t * d[0] + off * nr[0], q[1] + t * d[1] + off * nr[1]))
                    if rng.random() < 0.35:
                        sg = rng.choice([-1, 1])
                        b = pts[-1]
                        L = rng.uniform(0.006, 0.016)
                        parts.append(_pline([b, (b[0] + sg * L * nr[0] + 0.3 * L * d[0], b[1] + sg * L * nr[1] + 0.3 * L * d[1])],
                                            "#6b737d", 2.0))
                    t += rng.uniform(0.012, 0.022)
                    if rng.random() < 0.14 and len(pts) > 2:
                        parts.append(_pline(pts, "#6b737d", 2.6))
                        pts = []
                        t += rng.uniform(0.008, 0.025)
                if len(pts) > 1:
                    parts.append(_pline(pts, "#6b737d", 2.6))
            u += rng.uniform(0.034, 0.048)
    items += parts
    return items, [_leg("#e2e9f2", _L(de, "Austenit (γ), Säulenkörner des Schweissguts", "austenite (γ), columnar weld-metal grains")),
                   _leg("#6b737d", _L(de, "δ-Ferrit, vermikular (Skelett in den Dendritenkernen)", "δ-ferrite, vermicular (skeletal, in dendrite cores)"))]


def _sk_duplex(rng, de):
    items = [_poly(VIEW, "#aab2bb", None)]
    G = _grains(rng, 34, k=6.0, lloyd=0)
    isl = []
    for P in G:
        if rng.random() < 0.85:
            Q = _inset(P, rng.uniform(0.004, 0.011))
            if len(Q) >= 3:
                Q = _chaikin(Q, 2)
                isl.append(_poly(Q, "#eef2f6", "#6f7884", 0.6))
    items += isl
    return items, [_leg("#aab2bb", _L(de, "Ferrit (α), Matrix (dunkel geätzt)", "ferrite (α), matrix (etched dark)")),
                   _leg("#eef2f6", _L(de, "Austenit (γ), gestreckte Inseln", "austenite (γ), elongated islands"))]


P_CAST = "#bba891"                                    # Perlit im Gusseisen bei kleiner Vergrösserung


def _pearlite_matrix(rng, n=10, op=0.55, s=0.0095):
    items = []
    for P in _grains(rng, n):
        items.append(_poly(P, P_CAST, P_EDGE, 0.5))
        items.append(_hatch(P, rng.uniform(0, PI), s, rng.uniform(), P_LAM, 0.85, op))
    return items


def _sk_gjl(rng, de):
    items = _pearlite_matrix(rng)
    fl = []
    for _ in range(46):
        c = rng.uniform(-0.05, 1.05, 2)
        a = rng.uniform(0, PI)
        L = rng.uniform(0.05, 0.22)
        k = rng.normal(0, 2.0)
        w = rng.uniform(0.004, 0.0075)
        d = (math.cos(a), math.sin(a))
        nr = (-d[1], d[0])
        ss = np.linspace(-L / 2, L / 2, 11)
        up, lo = [], []
        for s in ss:
            off = k * s * s
            hw = w * (1 - (2 * s / L) ** 2) ** 0.6 + 0.0006
            base = (c[0] + s * d[0] + off * nr[0], c[1] + s * d[1] + off * nr[1])
            up.append((base[0] + hw * nr[0], base[1] + hw * nr[1]))
            lo.append((base[0] - hw * nr[0], base[1] - hw * nr[1]))
        fl.append(_poly(lo + up[::-1], GRAPH, None))
        if rng.random() < 0.35:
            s0 = rng.uniform(-L / 4, L / 4)
            b = (c[0] + s0 * d[0] + k * s0 * s0 * nr[0], c[1] + s0 * d[1] + k * s0 * s0 * nr[1])
            d2 = _rot(d, rng.choice([-1, 1]) * rng.uniform(0.4, 0.9))
            L2 = rng.uniform(0.03, 0.08)
            fl.append(_poly(_lens(b, (b[0] + L2 * d2[0], b[1] + L2 * d2[1]), w * 0.7, 5, 0.6), GRAPH, None))
    items += fl
    return items, [_leg(P_CAST, _L(de, "perlitische Matrix", "pearlitic matrix")),
                   _leg(GRAPH, _L(de, "Lamellengraphit (Form I, Anordnung A)", "flake graphite (form I, distribution A)"))]


def _sk_gjs(rng, de, ferrite_ring=1.75):
    items = _pearlite_matrix(rng)
    nod = []
    k = 0
    while len(nod) < 26 and k < 2000:
        k += 1
        c = rng.uniform(0.0, 1.0, 2)
        r = rng.uniform(0.017, 0.034)
        if all(math.hypot(c[0] - q[0], c[1] - q[1]) > (r + q[2]) * ferrite_ring + 0.01 for q in nod):
            nod.append((c[0], c[1], r))
    for x, y, r in nod:
        items.append(_poly(_chaikin(_disc((x, y), r * ferrite_ring * (1 + rng.uniform(0, 0.1)), 9), 1), FER, FER_GB, 0.5))
    for x, y, r in nod:
        items.append(_circle((x, y), r, GRAPH, "#111111", 0.6))
    return items, [_leg(P_CAST, _L(de, "perlitische Matrix", "pearlitic matrix")),
                   _leg(FER, _L(de, "Ferrithof um die Kugel (Ochsenauge)", "ferrite halo around the nodule (bull's eye)")),
                   _leg(GRAPH, _L(de, "Kugelgraphit (Form VI)", "spheroidal graphite (form VI)"))]


def _sk_al_mk(rng, de):
    G = _grains(rng, 9)
    items = [_poly(P, _mix(AL, "#d5dbe2", rng.uniform(0, 0.6)), AL_GB, 0.9) for P in G]
    dots = []
    for P in G:
        for v in P:
            if rng.random() < 0.35:
                dots.append((v[0], v[1], rng.uniform(0.003, 0.006)))
        for x, y in _sample_in(P, int(rng.integers(0, 4)), rng):
            dots.append((x, y, rng.uniform(0.0025, 0.005)))
    items += _dots(dots, "#4a4f57")
    return items, [_leg(AL, _L(de, "α-Al-Mischkristall (Legierungselemente gelöst)", "α-Al solid solution (alloying elements dissolved)")),
                   _leg("#4a4f57", _L(de, "Primärphasen (z. B. Al₇Cu₂Fe), unlöslich", "constituent particles (e.g. Al₇Cu₂Fe), insoluble"))]


def _sk_alsi(rng, de, modified=False):
    g = _dend_geom(_seed(rng), 0, 4, 0.032, False)
    items = [_poly(VIEW, "#dfe3e8", None)]
    A, B, W = _dend_segments(g)
    wp = 9.5
    X = rng.uniform(0, 1, (2600 if modified else 1500, 2))
    keep = _seg_dist(X, A, B) > wp * 1.3 * 0.8 / 520 / 2 + 0.005
    X = X[keep]
    if modified:
        items += _dots([(x, y, 0.0017) for x, y in X], SI)
    else:
        X = X[:700]
        parts = [(x, y, rng.uniform(0, PI), rng.uniform(0.012, 0.034), rng.uniform(1.2, 2.0)) for x, y in X]
        items += _dashes(parts, SI, lq=0.004, wq=0.4)
    paths = [_arm_paths(a, 1.0)[0] for a in g["arms"]]
    items += _dend_draw(paths, wp * 1.3, [(DEND_E, 1.4, 1.0), (AL, 0.0, 1.0)])
    return items, [_leg(AL, _L(de, "α-Al (primäre Dendriten)", "α-Al (primary dendrites)")),
                   _leg(SI, _L(de, "Si im Eutektikum: " + ("faserig (veredelt, Na/Sr)" if modified else "nadel- und plattenförmig (unveredelt)"),
                               "Si in the eutectic: " + ("fibrous (modified, Na/Sr)" if modified else "acicular/plate-like (unmodified)")))]


def _sk_pbsn(rng, de, x_sn=55.0):
    items = []
    for P in _grains(rng, 9):
        items.append(_poly(P, SN, "#9aa0a8", 0.4))
        items.append(_hatch(P, rng.uniform(0, PI), 0.0115, rng.uniform(), PB, 2.0))
    leg = [_leg(SN, _L(de, "Eutektikum: β-Sn (hell) + α-Pb-Lamellen (dunkel)", "eutectic: β-Sn (light) + α-Pb lamellae (dark)"))]
    if x_sn < 61.0:
        fp = _cl((61.9 - x_sn) / (61.9 - 18.3))
        g = _dend_geom(_seed(rng), 0, 2 + int(5 * fp), 0.028, False)
        wp = 7 + 18 * fp
        paths = [_arm_paths(a, 1.0)[0] for a in g["arms"]]
        items += _dend_draw(paths, wp, [("#d8dbe0", 3.0, 1.0), (PB, 0.0, 1.0)])
        leg.insert(0, _leg(PB, _L(de, "primäres α (Pb-reich), Dendriten", "primary α (Pb-rich), dendrites")))
    elif x_sn > 62.8:
        fp = _cl((x_sn - 61.9) / (97.8 - 61.9))
        g = _dend_geom(_seed(rng), 0, 2 + int(5 * fp), 0.028, False)
        wp = 7 + 18 * fp
        paths = [_arm_paths(a, 1.0)[0] for a in g["arms"]]
        items += _dend_draw(paths, wp, [(PB, 1.4, 1.0), (SN, 0.0, 1.0)])
        leg.insert(0, _leg(SN, _L(de, "primäres β (Sn-reich), Dendriten", "primary β (Sn-rich), dendrites")))
    return items, leg


def _sk_ti_lam(rng, de, basket=0.25):
    G = _grains(rng, 4)
    items = []
    for P in G:
        items.append(_poly(P, TI_A, "#3f4650", 1.0))
        core = _inset(P, 0.006)
        if len(core) < 3:
            continue
        m = int(_cl(round(_area(P) / 0.05), 3, 7))
        seeds = _sample_in(core, m, rng, view=False)
        for Q in (_cells(seeds, box=core) if len(seeds) > 1 else [core]):
            if len(Q) < 3:
                continue
            small = rng.random() < basket
            items.append(_poly(Q, TI_A, "#9aa2ad", 0.5))
            items.append(_hatch(Q, rng.uniform(0, PI), 0.0085 if small else 0.012, rng.uniform(), "#6d7a90", 1.6 if small else 2.1))
    return items, [_leg(TI_A, _L(de, "α-Lamellen in Kolonien, α-Saum an den β-Korngrenzen", "α lamellae in colonies, grain-boundary α layer")),
                   _leg("#6d7a90", _L(de, "β-Restlamellen zwischen den α-Platten", "retained β between the α plates"))]


def _sk_ti_bim(rng, de):
    items = []
    for P in _grains(rng, 12):
        items.append(_poly(P, "#a7b0bd", None))
        items.append(_hatch(P, rng.uniform(0, PI), 0.0075, rng.uniform(), "#e4e7df", 1.3))
    for P in _grains(rng, 46):
        if rng.random() < 0.5:
            Q = _inset(P, 0.012 + rng.uniform(0, 0.008))
            if len(Q) >= 3:
                items.append(_poly(_chaikin(Q, 2), TI_A, "#6f7883", 0.6))
    return items, [_leg(TI_A, _L(de, "primäres α (gleichachsig, globular)", "primary α (equiaxed, globular)")),
                   _leg("#a7b0bd", _L(de, "umgewandeltes β (feine α-Lamellen + β)", "transformed β (fine α lamellae + β)"))]


def _sk_messing(rng, de):
    G = _grains(rng, 24)
    items = []
    needles = []
    for P in G:
        if rng.random() < 0.42:
            items.append(_poly(P, MS_B, "#6e5a3c", 0.8))
            E = _edges(P)
            a = rng.uniform(0, PI)
            for _ in range(int(rng.integers(1, 4))):
                q = _perim_pt(P, rng.uniform())
                cc = _ctr(P)
                d = _rot(((cc[0] - q[0]), (cc[1] - q[1])), rng.uniform(-0.6, 0.6))
                L = math.hypot(*d)
                d = (d[0] / L, d[1] / L)
                ch = _chord(E, (q[0] + 0.002 * d[0], q[1] + 0.002 * d[1]), d)
                if ch:
                    Lp = ch[1] * rng.uniform(0.3, 0.6)
                    needles.append(_poly(_lens(q, (q[0] + Lp * d[0], q[1] + Lp * d[1]), 0.006 + 0.03 * Lp, 5, 0.8), MS_A, "#8a7552", 0.4))
        else:
            items.append(_poly(P, MS_A, "#6e5a3c", 0.8))
            items += _twin_bands(P, rng, 2, _mix(MS_A, "#d6c08e", 0.6), "#8a7552")
    items += needles
    return items, [_leg(MS_A, _L(de, "α-Messing (kfz, mit Zwillingen)", "α brass (fcc, with twins)")),
                   _leg(MS_B, _L(de, "β-Messing (krz, dunkler geätzt)", "β brass (bcc, etched darker)"))]


# ============================================================================ Galerie: Datensätze
def _C(fam, n_de, n_en, w_de, w_en, c_de, c_en, e_de, e_en, hv, refs, field, scale=None):
    """field: Bildbreite in µm für den Massstabsbalken (None: ohne Balken, scale nennt dann die typische Bildbreite)."""
    return {"name": (n_de, n_en), "family": fam, "what": (w_de, w_en), "conditions": (c_de, c_en),
            "etch": (e_de, e_en), "hv": hv, "refs": refs, "field_um": field,
            "scale": scale or (f"{field:g} µm" if field >= 1 else f"{field * 1000:g} nm")}


CONSTITUENTS: dict[str, dict] = {
    "ferrit": _C("stahl", "Ferrit", "Ferrite",
                 "Kubisch-raumzentrierter Mischkristall α-Fe mit höchstens 0,02 % C. Im Schliff helle, polygonale Körner mit "
                 "dünnen Korngrenzen; einzelne Körner ätzen je nach Orientierung etwas verschieden. Weich und zäh, Festigkeit "
                 "steigt mit feinerem Korn (Hall-Petch).",
                 "Body-centred cubic solid solution α-Fe with at most 0.02 % C. Bright polygonal grains with thin boundaries; "
                 "individual grains etch slightly differently with orientation. Soft and tough; strength rises with finer grain "
                 "size (Hall-Petch).",
                 "langsame Abkühlung, < 0,02 % C oder IF-Stahl", "slow cooling, < 0.02 % C or IF steel",
                 "Nital 2–3 %", "2–3 % nital", [70, 120], ["krauss2015", "asm2004v9", "callister"], 200),
    "perlit": _C("stahl", "Perlit", "Pearlite",
                 "Eutektoid aus Ferrit und Zementit (Fe₃C), der bei A1 = 727 °C kooperativ aus Austenit wächst. Kolonien mit je "
                 "einer Lamellenrichtung; in einem ehemaligen Austenitkorn liegen mehrere Kolonien verschiedener Orientierung. "
                 "Im Lichtmikroskop dunkel; der Lamellenabstand (0,1–1 µm) bestimmt die Festigkeit.",
                 "Eutectoid of ferrite and cementite (Fe₃C) growing cooperatively from austenite at A1 = 727 °C. Colonies each "
                 "with one lamella direction; one prior austenite grain holds several colonies of different orientation. "
                 "Dark in the light microscope; the interlamellar spacing (0.1–1 µm) controls strength.",
                 "langsame Abkühlung unter A1, 0,77 % C", "slow cooling below A1, 0.77 % C",
                 "Nital 3 % oder Pikral 4 %", "3 % nital or 4 % picral", [200, 320], ["mehl1956", "zener1946", "bhadeshia2017", "asm2004v9"], 50),
    "ferrit_perlit": _C("stahl", "Ferrit-Perlit (untereutektoid)", "Ferrite-pearlite (hypoeutectoid)",
                        "Unter A3 bildet sich zuerst voreutektoider Ferrit an den Austenitkorngrenzen (Allotriomorphe), der Rest "
                        "wird bei A1 zu Perlit. Helle Ferritkörner umschliessen dunkle Perlitinseln; der Perlitanteil folgt dem "
                        "Hebelgesetz (≈ C/0,77). Typisch für Baustähle (S235, C45 normalgeglüht).",
                        "Below A3 proeutectoid ferrite forms first at the austenite grain boundaries (allotriomorphs); the rest "
                        "becomes pearlite at A1. Bright ferrite grains surround dark pearlite islands; the pearlite fraction "
                        "follows the lever rule (≈ C/0.77). Typical of structural steels (S235, normalised C45).",
                        "normalgeglüht, 0,02–0,77 % C", "normalised, 0.02–0.77 % C",
                        "Nital 3 %", "3 % nital", [130, 220], ["krauss2015", "bhadeshia2017", "callister"], 100),
    "zementitnetz": _C("stahl", "Perlit mit Zementitnetz (übereutektoid)", "Pearlite with cementite network (hypereutectoid)",
                       "Zwischen Acm und A1 scheidet sich Sekundärzementit als zusammenhängender Film auf den Austenitkorngrenzen "
                       "aus; der Kornrest wird Perlit. In Nital erscheint das Netz hell mit dunkler Kontur, in alkalischem "
                       "Natriumpikrat dunkel. Das Netz versprödet den Stahl; Abhilfe ist Weichglühen.",
                       "Between Acm and A1 secondary cementite precipitates as a continuous film on the austenite grain "
                       "boundaries; the grain interiors become pearlite. In nital the network looks bright with a dark outline, in "
                       "alkaline sodium picrate dark. The network embrittles the steel; spheroidise annealing helps.",
                       "langsame Abkühlung, > 0,77 % C", "slow cooling, > 0.77 % C",
                       "Nital 3 % (Fe₃C hell); Natriumpikrat alkalisch (Fe₃C dunkel)", "3 % nital (Fe₃C bright); alkaline sodium picrate (Fe₃C dark)",
                       [250, 350], ["krauss2015", "vandervoort1984", "asm2004v9"], 100),
    "ledeburit": _C("gusseisen", "Ledeburit (umgewandelt)", "Ledeburite (transformed)",
                    "Eutektikum aus Austenit und Zementit, das bei 1147 °C erstarrt (4,3 % C); der Austenit zerfällt beim Abkühlen "
                    "zu Perlit. Kennzeichen ist das Leopardenfell-Muster: dunkle Perlitinseln in heller Zementitmatrix; bei "
                    "untereutektischem Hartguss zusätzlich dunkle Primärdendriten. Sehr hart und spröde (verschleissfest).",
                    "Eutectic of austenite and cementite solidifying at 1147 °C (4.3 % C); the austenite becomes pearlite on "
                    "cooling. Hallmark is the leopard-skin pattern: dark pearlite islands in a bright cementite matrix; "
                    "hypoeutectic white iron also shows dark primary dendrites. Very hard and brittle (wear resistant).",
                    "weisses Gusseisen, rasche Erstarrung, 2,1–4,3 % C", "white cast iron, fast solidification, 2.1–4.3 % C",
                    "Nital 3 %", "3 % nital", [450, 650], ["asm2004v9", "asm1990v1", "callister"], 200),
    "widmanstaetten": _C("stahl", "Widmanstätten-Ferrit", "Widmanstätten ferrite",
                         "Bei rascherer Abkühlung grober Austenitkörner wachsen aus dem Korngrenzenferrit Seitenplatten keilförmig "
                         "und parallel ins Korn (Sägezahnmuster); dazwischen Perlit. Typisch für Schweissnähte, Stahlguss und "
                         "überhitzte Schmiedestücke; senkt die Zähigkeit.",
                         "On faster cooling of coarse austenite grains, side plates grow wedge-shaped and parallel from the "
                         "grain-boundary ferrite into the grain (saw-tooth pattern), with pearlite in between. Typical of welds, "
                         "cast steel and overheated forgings; lowers toughness.",
                         "grobes γ-Korn, mittlere Abkühlgeschwindigkeit, 0,2–0,5 % C", "coarse γ grains, intermediate cooling rate, 0.2–0.5 % C",
                         "Nital 3 %", "3 % nital", [150, 230], ["bhadeshia2017", "asm2004v9", "porter"], 200),
    "bainit_oben": _C("stahl", "Oberer Bainit", "Upper bainite",
                      "Entsteht isotherm bei ≈ 400–550 °C: Bündel (Garben) paralleler Ferritlatten wachsen von den Korngrenzen; "
                      "der Kohlenstoff wird in den Austenit zwischen den Latten abgegeben und scheidet sich dort als Zementit aus. "
                      "Merkmal: Carbide ZWISCHEN den Latten, federartiges Bild. Weniger zäh als unterer Bainit.",
                      "Forms isothermally at ≈ 400–550 °C: sheaves of parallel ferrite laths grow from the grain boundaries; carbon "
                      "is rejected into the austenite between the laths, where cementite precipitates. Hallmark: carbides BETWEEN "
                      "the laths, feathery look. Less tough than lower bainite.",
                      "isotherm ≈ 400–550 °C (über der Perlitnase nicht erreichbar)", "isothermal ≈ 400–550 °C",
                      "Nital 2 %; LePera (Farbätzung)", "2 % nital; LePera (tint etch)", [300, 450], ["bhadeshia2015", "bhadeshia2017", "asm2004v9"], 20),
    "bainit_unten": _C("stahl", "Unterer Bainit", "Lower bainite",
                       "Entsteht isotherm knapp über Ms (≈ 250–400 °C): dünne, nadelförmige Platten in mehreren Richtungen. Ein Teil "
                       "des Kohlenstoffs scheidet sich als feine Carbide IN den Platten aus, alle in einer Richtung unter ≈ 60° zur "
                       "Plattenachse. Ähnelt angelassenem Martensit; hohe Festigkeit bei guter Zähigkeit.",
                       "Forms isothermally just above Ms (≈ 250–400 °C): thin acicular plates in several directions. Part of the "
                       "carbon precipitates as fine carbides INSIDE the plates, all in one direction at ≈ 60° to the plate axis. "
                       "Resembles tempered martensite; high strength with good toughness.",
                       "isotherm ≈ 250–400 °C, über Ms", "isothermal ≈ 250–400 °C, above Ms",
                       "Nital 2 %", "2 % nital", [400, 600], ["bhadeshia2015", "bhadeshia2017", "asm2004v9"], 20),
    "martensit_latte": _C("stahl", "Lattenmartensit", "Lath martensite",
                          "Diffusionslos aus Austenit bei < 0,6 % C. Ein ehemaliges Austenitkorn zerfällt in Pakete (gleiche "
                          "Habitusebene), diese in Blöcke und in feine parallele Latten (0,1–0,5 µm) mit hoher Versetzungsdichte. "
                          "Die alten Austenitkorngrenzen bleiben erkennbar. Hart, bei niedrigem C noch recht zäh.",
                          "Diffusionless from austenite at < 0.6 % C. A prior austenite grain splits into packets (same habit "
                          "plane), blocks and fine parallel laths (0.1–0.5 µm) with a high dislocation density. Prior austenite "
                          "grain boundaries stay visible. Hard, yet fairly tough at low carbon.",
                          "Abschrecken unter Ms, < 0,6 % C", "quenching below Ms, < 0.6 % C",
                          "Nital 2 %; Pikrinsäure gesättigt (ehemalige γ-Korngrenzen)", "2 % nital; saturated picric acid (prior γ boundaries)",
                          [380, 550], ["krauss2015", "bhadeshia2017", "koistinen1959"], 50),
    "martensit_platte": _C("stahl", "Plattenmartensit", "Plate martensite",
                           "Bei > 1 % C linsenförmige Platten mit Mittelrippe (verzwillingt). Die ersten Platten durchqueren das "
                           "Korn, spätere werden immer kleiner; zwischen ihnen bleibt Restaustenit, weil Mf unter Raumtemperatur "
                           "liegt. Sehr hart, spröde; Mikrorisse, wo Platten aufeinandertreffen.",
                           "Above 1 % C, lens-shaped plates with a (twinned) midrib. The first plates cross the grain, later ones "
                           "get ever smaller; retained austenite remains between them because Mf lies below room temperature. "
                           "Very hard and brittle; microcracks where plates impinge.",
                           "Abschrecken, > 1,0 % C", "quenching, > 1.0 % C",
                           "Nital 2 % (Restaustenit hell)", "2 % nital (retained austenite bright)", [750, 900], ["krauss2015", "bhadeshia2017", "porter"], 50),
    "martensit_angelassen": _C("stahl", "Angelassener Martensit", "Tempered martensite",
                               "Beim Anlassen zerfällt der übersättigte Martensit: erst ε-Carbid, dann Zementit auf Latten- und "
                               "Blockgrenzen, bei höherer Temperatur kugelig eingeformt und vergröbert. Die Lattenstruktur "
                               "verblasst (Erholung); Härte sinkt, Zähigkeit steigt (Vergüten).",
                               "On tempering, the supersaturated martensite decomposes: first ε-carbide, then cementite on lath and "
                               "block boundaries, spheroidised and coarsened at higher temperature. The lath structure fades "
                               "(recovery); hardness drops, toughness rises (quench and temper).",
                               "Härten + Anlassen 400–650 °C", "hardening + tempering 400–650 °C",
                               "Nital 2 %", "2 % nital", [250, 500], ["speich1972", "krauss2015", "jack1951"], 20),
    "spheroidit": _C("stahl", "Kugelzementit (GKZ)", "Spheroidite",
                     "Glühen knapp unter A1 (oder Pendeln um A1) formt die Zementitlamellen zu Kugeln ein, weil das die Grenzfläche "
                     "verkleinert; grosse Kugeln wachsen auf Kosten kleiner (Ostwald-Reifung). Ferritmatrix mit dunklen, runden "
                     "Carbiden; weichster Zustand, gut kaltumformbar und zerspanbar.",
                     "Annealing just below A1 (or cycling around A1) spheroidises the cementite lamellae, lowering the interface "
                     "area; large particles grow at the expense of small ones (Ostwald ripening). Ferrite matrix with dark round "
                     "carbides; softest condition, good for cold forming and machining.",
                     "Weichglühen 680–720 °C, viele Stunden", "spheroidise annealing 680–720 °C, many hours",
                     "Pikral 4 %", "4 % picral", [150, 200], ["krauss2015", "lifshitz1961", "asm2004v9"], 20),
    "austenit": _C("stahl", "Austenit", "Austenite",
                   "Kubisch-flächenzentrierter Mischkristall γ (z. B. CrNi-Stahl 1.4301). Polygonale Körner mit Glühzwillingen: "
                   "gerade, parallele Grenzen, die ein Korn ganz oder teilweise durchqueren – typisch für kfz-Metalle mit "
                   "niedriger Stapelfehlerenergie. Nicht magnetisch, zäh, stark kaltverfestigend.",
                   "Face-centred cubic solid solution γ (e.g. CrNi steel 304). Polygonal grains with annealing twins: straight, "
                   "parallel boundaries crossing a grain fully or partly – typical of fcc metals with low stacking-fault energy. "
                   "Non-magnetic, tough, strongly work hardening.",
                   "lösungsgeglüht und abgeschreckt, CrNi-Stahl", "solution annealed and quenched, CrNi steel",
                   "V2A-Beize oder Oxalsäure 10 % elektrolytisch", "aqua regia–based (V2A) or 10 % oxalic acid, electrolytic",
                   [150, 200], ["asm2004v9", "humphreys2004", "lippold2005"], 200),
    "delta_ferrit": _C("stahl", "δ-Ferrit im Schweissgut", "δ-ferrite in weld metal",
                       "Austenitisches Schweissgut (z. B. 308L) erstarrt primär ferritisch; beim Abkühlen wandelt der meiste δ-Ferrit "
                       "in Austenit um, ein Rest von 3–10 % bleibt in den Dendritenkernen als vermikulares Skelett. Er verhindert "
                       "Heissrisse, kann aber bei 600–900 °C zu σ-Phase verspröden.",
                       "Austenitic weld metal (e.g. 308L) solidifies as primary ferrite; on cooling most δ-ferrite becomes "
                       "austenite, a residue of 3–10 % stays in the dendrite cores as a vermicular skeleton. It prevents hot "
                       "cracking but can embrittle to σ phase at 600–900 °C.",
                       "Schweissgut CrNi, Erstarrungsmodus FA", "CrNi weld metal, FA solidification mode",
                       "Murakami (färbt δ) oder Oxalsäure 10 % elektrolytisch", "Murakami's (tints δ) or 10 % oxalic acid, electrolytic",
                       [160, 220], ["lippold2005", "asm2004v9"], 200),
    "duplex": _C("stahl", "Duplexstahl (Ferrit + Austenit)", "Duplex stainless steel (ferrite + austenite)",
                 "Etwa gleiche Anteile Ferrit und Austenit (z. B. 1.4462). Nach dem Warmwalzen und Lösungsglühen liegen gestreckte "
                 "Austenitinseln in einer Ferritmatrix, parallel zur Walzrichtung. Höhere Festigkeit als austenitische Stähle, "
                 "sehr gute Beständigkeit gegen Spannungsrisskorrosion.",
                 "Roughly equal fractions of ferrite and austenite (e.g. 2205). After hot rolling and solution annealing, "
                 "elongated austenite islands lie in a ferrite matrix parallel to the rolling direction. Higher strength than "
                 "austenitic grades, very good resistance to stress corrosion cracking.",
                 "warmgewalzt + lösungsgeglüht 1020–1100 °C", "hot rolled + solution annealed 1020–1100 °C",
                 "Beraha II (Ferrit dunkel) oder NaOH elektrolytisch", "Beraha II (ferrite dark) or NaOH, electrolytic",
                 [230, 290], ["gunn1997", "asm2004v9"], 200),
    "gjl": _C("gusseisen", "Gusseisen mit Lamellengraphit (GJL)", "Grey cast iron (flake graphite)",
              "Graphit erstarrt in gekrümmten, verzweigten Lamellen (räumlich zusammenhängende Rosetten der eutektischen "
              "Zellen); Matrix meist Perlit. Die Lamellenspitzen wirken als Kerben: geringe Zugfestigkeit und Bruchdehnung, "
              "aber sehr gute Dämpfung und Wärmeleitung. Einteilung nach ISO 945 (Form I, Anordnung A–E).",
              "Graphite solidifies as curved, branched flakes (interconnected rosettes of the eutectic cells); the matrix is "
              "usually pearlite. Flake tips act as notches: low tensile strength and elongation, but excellent damping and "
              "thermal conductivity. Classified per ISO 945 (form I, distribution A–E).",
              "Gusseisen 3–3,6 % C, 1,8–2,5 % Si, langsame Erstarrung", "cast iron 3–3.6 % C, 1.8–2.5 % Si, slow solidification",
              "ungeätzt (Graphit), dann Nital 3 %", "unetched (graphite), then 3 % nital", [160, 250], ["iso945", "en1561", "asm2004v9"], 500),
    "gjs": _C("gusseisen", "Gusseisen mit Kugelgraphit (GJS)", "Ductile cast iron (spheroidal graphite)",
              "Mg-Behandlung lässt den Graphit kugelig erstarren. Um jede Kugel entzieht der Graphit der Matrix Kohlenstoff, "
              "sodass ein Ferrithof entsteht (Ochsenauge), dazwischen Perlit. Kugeln wirken kaum als Kerben: Bruchdehnung bis "
              "über 15 %, stahlähnliche Festigkeit.",
              "Mg treatment makes graphite solidify as spheroids. Around each nodule the graphite draws carbon from the "
              "matrix, leaving a ferrite halo (bull's eye) with pearlite in between. Nodules hardly act as notches: elongation "
              "up to over 15 %, steel-like strength.",
              "Gusseisen mit Mg-Behandlung (0,03–0,05 % Mg)", "cast iron, Mg treated (0.03–0.05 % Mg)",
              "ungeätzt (Graphit), dann Nital 3 %", "unetched (graphite), then 3 % nital", [160, 250], ["iso945", "en1563", "asm2004v9"], 500),
    "al_mk": _C("aluminium", "Al-Mischkristall (lösungsgeglüht)", "Al solid solution (solution treated)",
                "Nach dem Lösungsglühen und Abschrecken ist das Legierungselement (z. B. Cu) im kfz α-Al gelöst; nur unlösliche "
                "Primärphasen (Fe-, Si-haltig) bleiben als dunkle Teilchen. Grosse, gleichachsige Körner, die nach Keller nur "
                "schwach kontrastieren. Weich und gut umformbar, bis die Kaltauslagerung einsetzt.",
                "After solution treatment and quenching the alloying element (e.g. Cu) is dissolved in fcc α-Al; only insoluble "
                "constituent particles (Fe-, Si-bearing) remain as dark particles. Large equiaxed grains with weak contrast "
                "after Keller's etch. Soft and formable until natural ageing sets in.",
                "lösungsgeglüht ≈ 500 °C, abgeschreckt", "solution treated ≈ 500 °C, quenched",
                "Keller-Ätzmittel", "Keller's reagent", [30, 70], ["polmear2017", "asm2004v9"], 200),
    "al_gp": _C("aluminium", "GP-Zonen (Al-Cu)", "GP zones (Al-Cu)",
                "Guinier-Preston-Zonen: einlagige, kohärente Cu-Scheibchen auf {100}-Ebenen, wenige nm gross und sehr dicht "
                "(10¹⁷–10¹⁸ cm⁻³). Nur im Transmissionselektronenmikroskop sichtbar; im Lichtmikroskop sieht das Gefüge wie der "
                "Mischkristall aus. Ursache der Kaltaushärtung.",
                "Guinier-Preston zones: monolayer coherent Cu discs on {100} planes, a few nm across and very dense "
                "(10¹⁷–10¹⁸ cm⁻³). Visible only by TEM; in the light microscope the structure looks like the solid solution. "
                "Cause of natural ageing.",
                "kaltausgelagert (T4) oder kurz bei 100–150 °C", "naturally aged (T4) or briefly at 100–150 °C",
                "– (TEM, Hellfeld)", "– (TEM, bright field)", [90, 120], ["guinier1938", "preston1938", "polmear2017"], None,
                "≈ 200 nm (TEM)"),
    "al_theta_strich": _C("aluminium", "θ′-Platten (Al-Cu, spitzenausgelagert)", "θ′ plates (Al-Cu, peak aged)",
                          "Teilkohärente θ′-Platten (Al₂Cu, tetragonal) auf {100}; im Schnitt erscheinen zwei Orientierungen "
                          "unter 90°. Zusammen mit θ″ ergeben sie die Höchsthärte. An den Korngrenzen beginnt eine "
                          "ausscheidungsfreie Zone (PFZ).",
                          "Semi-coherent θ′ plates (Al₂Cu, tetragonal) on {100}; a section shows two orientations at 90°. "
                          "Together with θ″ they give peak hardness. A precipitate-free zone (PFZ) starts at grain boundaries.",
                          "warmausgelagert 160–190 °C (T6)", "artificially aged 160–190 °C (T6)",
                          "– (TEM, Hellfeld, ⟨100⟩-Zone)", "– (TEM, bright field, ⟨100⟩ zone)", [120, 150],
                          ["silcock1954", "polmear2017", "porter"], None, "≈ 1 µm (TEM)"),
    "al_ueberaltert": _C("aluminium", "Überaltert (θ grob, PFZ)", "Overaged (coarse θ, PFZ)",
                         "Zu lange oder zu heiss ausgelagert: inkohärentes θ-Al₂Cu vergröbert durch Ostwald-Reifung, die Teilchen "
                         "werden wenige und gross, Versetzungen umgehen sie (Orowan). Grobe Teilchen auf den Korngrenzen und eine "
                         "breite PFZ; Festigkeit und Korrosionsbeständigkeit sinken.",
                         "Aged too long or too hot: incoherent θ-Al₂Cu coarsens by Ostwald ripening, particles become few and "
                         "large, dislocations bypass them (Orowan). Coarse particles on grain boundaries and a wide PFZ; strength "
                         "and corrosion resistance drop.",
                         "warmausgelagert > 200 °C oder sehr lange (T7)", "aged > 200 °C or very long (T7)",
                         "Keller-Ätzmittel / TEM", "Keller's reagent / TEM", [70, 100], ["polmear2017", "lifshitz1961", "porter"],
                         None, "≈ 2 µm (TEM)"),
    "al_si_eutektikum": _C("aluminium", "Al-Si-Guss (Dendriten + Eutektikum)", "Al-Si casting (dendrites + eutectic)",
                           "Untereutektische Al-Si-Gusslegierung (z. B. AlSi7Mg): helle α-Al-Dendriten, dazwischen das "
                           "Eutektikum aus Al und Silicium. Unveredelt ist das Si grob nadel- bzw. plattenförmig (spröde), nach "
                           "Veredelung mit Na oder Sr fein faserig – die Bruchdehnung steigt deutlich.",
                           "Hypoeutectic Al-Si casting alloy (e.g. A356): bright α-Al dendrites with the Al-Si eutectic in between. "
                           "Unmodified, the Si is coarse and acicular/plate-like (brittle); modified with Na or Sr it becomes "
                           "fine and fibrous – elongation rises markedly.",
                           "Guss, 5–12 % Si", "cast, 5–12 % Si", "0,5 % HF oder ungeätzt", "0.5 % HF or unetched",
                           [55, 90], ["polmear2017", "asm2004v9", "kurz1998"], 400),
    "pb_sn_eutektikum": _C("eutektisch", "Pb-Sn-Eutektikum", "Pb-Sn eutectic",
                           "Bei 183 °C erstarren α (Pb-reich) und β (Sn-reich) gekoppelt in Kolonien feiner Lamellen; der "
                           "Lamellenabstand folgt λ²·v = konst. (Jackson-Hunt). Abseits von 61,9 % Sn erstarren zuerst "
                           "Primärdendriten (hier α), das Eutektikum füllt den Rest. Weichlot.",
                           "At 183 °C α (Pb-rich) and β (Sn-rich) solidify cooperatively in colonies of fine lamellae; the spacing "
                           "follows λ²·v = const. (Jackson-Hunt). Off 61.9 % Sn, primary dendrites (here α) solidify first and "
                           "the eutectic fills the rest. Soft solder.",
                           "Erstarrung, ≈ 40–62 % Sn", "solidification, ≈ 40–62 % Sn",
                           "Essigsäure + Salpetersäure in Glycerin (1:1:8)", "acetic + nitric acid in glycerol (1:1:8)",
                           [12, 16], ["jackson1966", "kurz1998", "callister"], 100),
    "dendriten": _C("allgemein", "Gussgefüge mit Dendriten", "Cast dendritic structure",
                    "Bei der Erstarrung wachsen Dendriten mit Stämmen in ⟨100⟩-Richtung und Seitenarmen im Abstand λ₂; λ₂ sinkt mit "
                    "schnellerer Abkühlung. Kerne der Arme sind arm an Legierungselement, die zuletzt erstarrten Zwischenräume "
                    "angereichert (Kristallseigerung); beim Ätzen zeichnet sich das als Schattierung ab. Diffusionsglühen gleicht aus.",
                    "During solidification dendrites grow with trunks along ⟨100⟩ and side arms spaced λ₂; λ₂ falls with faster "
                    "cooling. Arm cores are lean in solute, the last-to-freeze interdendritic regions enriched (coring); etching "
                    "shows this as shading. Homogenising anneals remove it.",
                    "Guss, Erstarrung im Zweiphasengebiet", "casting, freezing range",
                    "je nach Legierung (z. B. Klemm, Oberhoffer)", "alloy-specific (e.g. Klemm's, Oberhoffer's)",
                    None, ["kurz1998", "porter", "asm2004v9"], 1000),
    "ti_lamellar": _C("titan", "Ti-6Al-4V lamellar", "Ti-6Al-4V lamellar",
                      "Langsam aus dem β-Gebiet abgekühlt: an den ehemaligen β-Korngrenzen ein α-Saum, im Korn Kolonien paralleler "
                      "α-Platten mit dünnen β-Restlamellen; bei schnellerer Abkühlung kleinere, verflochtene Kolonien "
                      "(Korbgeflecht). Gute Bruchzähigkeit und Kriechfestigkeit, geringere Duktilität.",
                      "Slowly cooled from the β field: an α layer on the prior β grain boundaries, inside colonies of parallel α "
                      "plates with thin retained β; faster cooling gives smaller interwoven colonies (basketweave). Good fracture "
                      "toughness and creep strength, lower ductility.",
                      "geglüht über β-Transus (≈ 995 °C), langsam abgekühlt", "annealed above β transus (≈ 995 °C), slowly cooled",
                      "Kroll-Ätzmittel", "Kroll's reagent", [300, 350], ["lutjering2007", "asm2004v9"], 500),
    "ti_bimodal": _C("titan", "Ti-6Al-4V bimodal", "Ti-6Al-4V bimodal",
                     "Umgeformt und geglüht im α+β-Gebiet: gleichachsiges Primär-α (hell, globular) neben umgewandeltem β mit "
                     "feinen α-Lamellen. Bester Kompromiss aus Festigkeit, Duktilität und Ermüdungsfestigkeit; Standard für "
                     "Schmiedeteile.",
                     "Worked and annealed in the α+β field: equiaxed primary α (bright, globular) next to transformed β with "
                     "fine α lamellae. Best balance of strength, ductility and fatigue strength; standard for forgings.",
                     "Umformen + Glühen im α+β-Gebiet (≈ 950 °C)", "working + annealing in the α+β field (≈ 950 °C)",
                     "Kroll-Ätzmittel", "Kroll's reagent", [310, 350], ["lutjering2007", "asm2004v9"], 100),
    "messing_ab": _C("kupfer", "α/β-Messing (CuZn40)", "α/β brass (Muntz metal)",
                     "Bei ≈ 40 % Zn liegen kfz α (hell, mit Glühzwillingen) und krz β (dunkler) nebeneinander; beim Abkühlen "
                     "scheidet sich α auch nadelförmig im β aus. β macht die Legierung warmumformbar und fester, α duktil.",
                     "At ≈ 40 % Zn, fcc α (bright, with annealing twins) and bcc β (darker) coexist; on cooling, α also "
                     "precipitates as needles in β. β makes the alloy hot-workable and stronger, α ductile.",
                     "CuZn40, warmumgeformt", "CuZn40, hot worked",
                     "Eisen(III)-chlorid–Salzsäure in Ethanol; Klemm I", "ferric chloride–HCl in ethanol; Klemm's I",
                     [100, 160], ["asm1990v2", "asm2004v9"], 200),
    "kaltverformt": _C("allgemein", "Kaltverformt", "Cold worked",
                       "Durch Walzen gestreckte, abgeplattete Körner mit Gleitbändern und hoher Versetzungsdichte (10¹⁵–10¹⁶ m⁻²). "
                       "Festigkeit und Härte steigen (Kaltverfestigung), Duktilität sinkt; die gespeicherte Energie treibt später "
                       "die Rekristallisation.",
                       "Grains elongated and flattened by rolling, with slip bands and a high dislocation density "
                       "(10¹⁵–10¹⁶ m⁻²). Strength and hardness rise (work hardening), ductility drops; the stored energy later "
                       "drives recrystallisation.",
                       "Kaltwalzen, z. B. 60 % Dickenabnahme", "cold rolling, e.g. 60 % reduction",
                       "Nital 2 % (Stahl)", "2 % nital (steel)", [180, 250], ["humphreys2004", "callister"], 200),
    "rekristallisiert": _C("allgemein", "Rekristallisiert", "Recrystallised",
                           "Nach Glühen über der Rekristallisationstemperatur (≈ 0,4 Tm) entstehen neue, versetzungsarme, "
                           "gleichachsige Körner; Festigkeit und Duktilität kehren auf den Glühzustand zurück. Die Korngrösse "
                           "hängt von Verformungsgrad, Temperatur und Zeit ab.",
                           "After annealing above the recrystallisation temperature (≈ 0.4 Tm), new, low-dislocation equiaxed "
                           "grains form; strength and ductility return to the annealed level. Grain size depends on strain, "
                           "temperature and time.",
                           "Rekristallisationsglühen ≈ 0,4–0,5 Tm", "recrystallisation anneal ≈ 0.4–0.5 Tm",
                           "Nital 2 % (Stahl)", "2 % nital (steel)", [90, 130], ["humphreys2004", "callister"], 200),
}


def info(cid: str, de: bool = True) -> dict:
    """Datensatz eines Gefügebestandteils in einer Sprache (für Seite und Bericht)."""
    c = CONSTITUENTS[cid]
    i = 0 if de else 1
    return {"id": cid, "name": c["name"][i], "family": c["family"], "what": c["what"][i],
            "conditions": c["conditions"][i], "etch": c["etch"][i], "hv": c["hv"], "refs": list(c["refs"]),
            "scale": c["scale"]}


def catalog(de: bool = True) -> list[dict]:
    return [info(k, de) for k in CONSTITUENTS]


_TR_OF = {"perlit": ("perlit", 1.0, {"C": 0.77, "n": 7}), "ferrit_perlit": ("perlit", 1.0, {"C": 0.35, "n": 8}),
          "zementitnetz": ("perlit", 1.0, {"C": 1.2, "n": 7}),
          "bainit_oben": ("bainit_oben", 1.0, {}), "bainit_unten": ("bainit_unten", 1.0, {}),
          "martensit_latte": ("martensit", 1.0, {"C": 0.2}), "martensit_platte": ("martensit", 1.0, {"C": 1.4}),
          "martensit_angelassen": ("anlassen", 0.62, {}), "spheroidit": ("sphaeroidisieren", 0.9, {}),
          "al_gp": ("ausscheidung", 0.2, {}), "al_theta_strich": ("ausscheidung", 0.62, {}),
          "al_ueberaltert": ("ausscheidung", 0.97, {}), "kaltverformt": ("rekristallisation", 0.0, {}),
          "rekristallisiert": ("rekristallisation", 0.72, {})}


def sketch(cid: str, rng, de: bool = True, **params) -> dict:
    """Gefügeskizze eines Bestandteils aus CONSTITUENTS. rng: numpy-Generator oder ganze Zahl (Seed)."""
    if cid not in CONSTITUENTS:
        raise SK.StructError(f"Gefügebestandteil „{cid}“ unbekannt")
    seed = _seed(rng)
    c = CONSTITUENTS[cid]
    if cid in _TR_OF:
        tid, f, p = _TR_OF[cid]
        p = {**p, **params}
        f = float(p.pop("f", f))
        sk = transition(tid, f, seed, de, **p)
        sk.pop("info", None)
    else:
        r = np.random.default_rng(seed)
        fn = {"ferrit": _sk_ferrit, "austenit": _sk_austenit, "widmanstaetten": _sk_widman, "ledeburit": _sk_ledeb,
              "delta_ferrit": _sk_delta, "duplex": _sk_duplex, "gjl": _sk_gjl, "gjs": _sk_gjs, "al_mk": _sk_al_mk,
              "al_si_eutektikum": _sk_alsi, "pb_sn_eutektikum": _sk_pbsn, "ti_lamellar": _sk_ti_lam,
              "ti_bimodal": _sk_ti_bim, "messing_ab": _sk_messing}.get(cid)
        if fn is not None:
            items, legend = fn(r, de, **params)
        elif cid == "dendriten":
            g = _dend_geom(seed, 5, 3, 0.037, True)
            items, _ = _dend_items(g, 1.0, de, f_eut=float(params.get("f_eut", 0.35)), style="coring", eut_kind="none")
            items.insert(0, _poly(VIEW, "#b3aa9c", None))
            legend = [_leg("#eef2f6", _L(de, "Dendritenkern (arm an Legierungselement)", "dendrite core (solute-lean)")),
                      _leg("#c3ccd6", _L(de, "Randzone der Arme", "outer arm region")),
                      _leg("#b3aa9c", _L(de, "interdendritisch, angereichert (zuletzt erstarrt)", "interdendritic, enriched (last to freeze)"))]
        else:
            raise SK.StructError(f"Skizze für „{cid}“ fehlt")
        sk = {"items": items, "legend": legend}
    sk.pop("scale", None)
    sc = _scale(c["field_um"], de)
    if sc:
        sk["scale"] = sc
    sk["schematic"] = True
    return sk


# ============================================================================ Umwandlungen
def _steps_of(tid: str, C: float = 0.45) -> list:
    if tid == "austenitisieren":
        hypo, hyper = C < 0.765, C > 0.775
        fP = 0.4 if hypo else (0.55 if hyper else 1.0)
        st = [(0.0, fP,
               "Knapp über Ac1 (727 °C) bildet sich Austenit zuerst im Perlit: Keime an den Grenzflächen Ferrit/Zementit und "
               "an den Koloniegrenzen; die Zementitlamellen lösen sich auf und liefern den Kohlenstoff (≈ 0,77 %).",
               "Just above Ac1 (727 °C) austenite forms first in the pearlite: nuclei at ferrite/cementite interfaces and colony "
               "boundaries; the cementite lamellae dissolve and supply the carbon (≈ 0.77 %).")]
        if hypo:
            st.append((fP, 1.0, "Zwischen Ac1 und Ac3 wächst der Austenit in den Ferrit hinein; der Kohlenstoff verteilt sich "
                       "durch Diffusion. Über Ac3 ist alles Austenit; Halten gleicht die Konzentration aus.",
                       "Between Ac1 and Ac3 austenite grows into the ferrite while carbon redistributes by diffusion. Above Ac3 "
                       "everything is austenite; holding evens out the concentration."))
        elif hyper:
            st.append((fP, 1.0, "Zwischen Ac1 und Accm löst sich das Zementitnetz auf und reichert den Austenit an; über "
                       "Accm ist das Gefüge vollständig austenitisch (Härten erfolgt meist darunter, mit Restcarbiden).",
                       "Between Ac1 and Accm the cementite network dissolves and enriches the austenite; above Accm the "
                       "structure is fully austenitic (hardening is usually done below, with residual carbides)."))
        return st
    if tid == "perlit":
        hypo, hyper = C < 0.765, C > 0.775
        tgt = _cl((0.77 - C) / 0.748) if hypo else (_cl((C - 0.77) / 5.9) if hyper else 0.0)
        f1 = _fp_split(C, tgt)
        st = []
        if hypo:
            st.append((0.0, f1, "Unter Ar3 scheidet sich voreutektoider Ferrit an den Austenitkorngrenzen aus (Allotriomorphe). "
                       "Ferrit löst kaum Kohlenstoff; er wird in den Restaustenit abgeschoben, bis dieser 0,77 % C erreicht.",
                       "Below Ar3 proeutectoid ferrite precipitates on the austenite grain boundaries (allotriomorphs). Ferrite "
                       "dissolves almost no carbon; it is pushed into the remaining austenite until that reaches 0.77 % C."))
        elif hyper:
            st.append((0.0, f1, "Unter Arcm scheidet sich Sekundärzementit als Film auf den Austenitkorngrenzen aus; der "
                       "Austenit verarmt dabei bis auf 0,77 % C.",
                       "Below Arcm secondary cementite precipitates as a film on the austenite grain boundaries; the austenite "
                       "is depleted down to 0.77 % C."))
        m = f1 + 0.4 * (1 - f1)
        st.append((f1, m, "Bei Ar1 keimen Perlitkolonien an den Korngrenzen bzw. an der Grenzfläche zum voreutektoiden Gefüge. "
                   "Ferrit und Zementit wachsen gekoppelt (kooperativ): Kohlenstoff diffundiert vor der Front seitlich vom "
                   "Ferrit zum Zementit.",
                   "At Ar1 pearlite colonies nucleate on grain boundaries or on the interface with the proeutectoid phase. "
                   "Ferrite and cementite grow cooperatively: carbon diffuses sideways ahead of the front from ferrite to "
                   "cementite."))
        st.append((m, 1.0, "Die Kolonien wachsen mit konstanter Geschwindigkeit, bis sie aufeinandertreffen; jede hat eine "
                   "eigene Lamellenrichtung. Der Lamellenabstand sinkt mit der Unterkühlung (Zener: λ ∝ 1/ΔT).",
                   "Colonies grow at constant rate until they impinge; each has its own lamella direction. The spacing "
                   "decreases with undercooling (Zener: λ ∝ 1/ΔT)."))
        return st
    if tid == "martensit":
        plate = C >= 0.8
        return [(0.0, 0.04, "Über Ms bleibt der unterkühlte Austenit erhalten: rasches Abschrecken hat die Diffusion "
                 "(Perlit, Bainit) unterdrückt.",
                 "Above Ms the undercooled austenite survives: fast quenching has suppressed diffusion (pearlite, bainite)."),
                (0.04, 0.6, "Unter Ms klappen Martensiteinheiten diffusionslos um (Scherung und Bain-Verzerrung), schubweise "
                 "mit Schallgeschwindigkeit. Die Menge hängt nur von der Unterkühlung ab: f = 1 − exp(−0,011·(Ms − T)) "
                 "(Koistinen-Marburger).",
                 "Below Ms martensite units shear into place without diffusion (shear plus Bain strain), in bursts at the "
                 "speed of sound. The amount depends only on undercooling: f = 1 − exp(−0.011·(Ms − T)) "
                 "(Koistinen-Marburger)."),
                (0.6, 1.0, ("Die ersten Platten durchqueren das Korn, spätere füllen die Reste und werden immer kleiner. "
                            "Zwischen den Linsen bleibt Restaustenit, weil Mf unter Raumtemperatur liegt." if plate else
                            "Latten gleicher Habitusebene bilden Blöcke und Pakete im ehemaligen Austenitkorn; dessen "
                            "Korngrenzen bleiben sichtbar. Kaum Restaustenit."),
                 ("The first plates cross the grain, later ones fill the remaining space and get ever smaller. Retained "
                  "austenite stays between the lenses because Mf lies below room temperature." if plate else
                  "Laths of one habit plane form blocks and packets inside the prior austenite grain, whose boundaries "
                  "remain visible. Hardly any retained austenite."))]
    return [tuple(x) for x in TRANSITIONS[tid]["steps"]]


TRANSITIONS: dict[str, dict] = {
    "austenitisieren": {"name": ("Austenitisieren", "Austenitising"), "field_um": 100,
                        "refs": ["krauss2015", "porter", "callister"], "kind": "growth"},
    "perlit": {"name": ("Perlitbildung", "Pearlite formation"), "field_um": 100,
               "refs": ["mehl1956", "zener1946", "porter", "bhadeshia2017"], "kind": "growth"},
    "martensit": {"name": ("Martensitbildung", "Martensite formation"), "field_um": 50,
                  "refs": ["koistinen1959", "bain1924", "krauss2015", "bhadeshia2017"], "kind": "growth"},
    "anlassen": {"name": ("Anlassen von Martensit", "Tempering of martensite"), "field_um": 20,
                 "refs": ["speich1972", "jack1951", "krauss2015", "lifshitz1961"], "kind": "stage",
                 "steps": [(0.0, 0.2, "Stufe 1 (≈ 100–200 °C): Kohlenstoff entmischt sich; feine ε-Carbide (Fe₂,₄C) scheiden "
                            "sich in den Latten aus, die Tetragonalität des Martensits nimmt ab.",
                            "Stage 1 (≈ 100–200 °C): carbon segregates; fine ε-carbides (Fe₂.₄C) precipitate inside the laths, "
                            "the tetragonality of martensite decreases."),
                           (0.2, 0.35, "Stufe 2 (≈ 200–300 °C): Restaustenit-Filme zwischen den Latten zerfallen in Ferrit und "
                            "Carbid.",
                            "Stage 2 (≈ 200–300 °C): retained-austenite films between laths decompose into ferrite and carbide."),
                           (0.35, 0.55, "Stufe 3 (≈ 250–400 °C): ε-Carbid löst sich auf; Zementit (Fe₃C) bildet sich als Filme "
                            "auf Latten- und Blockgrenzen.",
                            "Stage 3 (≈ 250–400 °C): ε-carbide dissolves; cementite (Fe₃C) forms as films on lath and block "
                            "boundaries."),
                           (0.55, 0.78, "Über ≈ 400 °C formen sich die Zementitfilme zu Kugeln ein; Versetzungen ordnen sich "
                            "um (Erholung), die Lattenstruktur verblasst.",
                            "Above ≈ 400 °C the cementite films spheroidise; dislocations rearrange (recovery) and the lath "
                            "structure fades."),
                           (0.78, 1.0, "Über ≈ 600 °C Ostwald-Reifung: kleine Carbide lösen sich auf, grosse wachsen; "
                            "der Ferrit rekristallisiert teilweise. Härte sinkt, Zähigkeit steigt.",
                            "Above ≈ 600 °C Ostwald ripening: small carbides dissolve, large ones grow; the ferrite partly "
                            "recrystallises. Hardness falls, toughness rises.")]},
    "bainit_oben": {"name": ("Oberer Bainit", "Upper bainite"), "field_um": 20,
                    "refs": ["bhadeshia2015", "bhadeshia2017"], "kind": "growth",
                    "steps": [(0.0, 0.12, "Isotherm bei ≈ 400–550 °C: Bainitferrit keimt an den Austenitkorngrenzen.",
                               "Isothermal at ≈ 400–550 °C: bainitic ferrite nucleates on the austenite grain boundaries."),
                              (0.12, 0.55, "Latten wachsen scherend nebeneinander zu Garben (sheaves); jede bleibt klein, weil "
                               "die plastische Verformung des Austenits sie stoppt. Der Kohlenstoff geht in den Austenit "
                               "zwischen den Latten.",
                               "Laths grow by shear side by side into sheaves; each stays small because plastic deformation "
                               "of the austenite stops it. Carbon is rejected into the austenite between the laths."),
                              (0.55, 1.0, "Aus dem kohlenstoffreichen Austenit zwischen den Latten scheidet sich Zementit als "
                               "Filme und Stängel aus – Carbide ZWISCHEN den Latten, federartiges Bild.",
                               "Cementite precipitates as films and stringers from the carbon-enriched austenite between the "
                               "laths – carbides BETWEEN the laths, feathery appearance.")]},
    "bainit_unten": {"name": ("Unterer Bainit", "Lower bainite"), "field_um": 20,
                     "refs": ["bhadeshia2015", "bhadeshia2017"], "kind": "growth",
                     "steps": [(0.0, 0.12, "Isotherm knapp über Ms (≈ 250–400 °C): Bainitplatten keimen an Korngrenzen.",
                                "Isothermal just above Ms (≈ 250–400 °C): bainite plates nucleate on grain boundaries."),
                               (0.12, 0.5, "Dünne Platten wachsen in mehreren Richtungen, auch von bereits gebildeten Platten aus "
                                "(autokatalytisch). Bei der tiefen Temperatur kann der Kohlenstoff nicht mehr ganz in den "
                                "Austenit abwandern.",
                                "Thin plates grow in several directions, also from existing plates (autocatalysis). At the low "
                                "temperature the carbon can no longer fully escape into the austenite."),
                               (0.5, 1.0, "Carbide scheiden sich IN den Platten aus, als feine Teilchen in einer einzigen "
                                "Richtung unter ≈ 60° zur Plattenachse – das Unterscheidungsmerkmal zum oberen Bainit.",
                                "Carbides precipitate INSIDE the plates as fine particles in a single direction at ≈ 60° to the "
                                "plate axis – the distinguishing feature from upper bainite.")]},
    "ausscheidung": {"name": ("Aushärten Al-Cu", "Age hardening Al-Cu"), "field_um": None,
                     "refs": ["guinier1938", "preston1938", "silcock1954", "polmear2017", "porter"], "kind": "stage",
                     "steps": [(0.0, 0.08, "Nach Lösungsglühen und Abschrecken: übersättigter α-Al-Mischkristall mit gelöstem "
                                "Cu und eingefrorenen Leerstellen.",
                                "After solution treatment and quenching: supersaturated α-Al solid solution with dissolved Cu "
                                "and quenched-in vacancies."),
                               (0.08, 0.3, "GP-Zonen: einlagige Cu-Scheibchen auf {100}, kohärent, wenige nm gross; erste "
                                "Härtesteigerung (Kaltauslagern).",
                                "GP zones: monolayer Cu discs on {100}, coherent, a few nm; first hardening (natural ageing)."),
                               (0.3, 0.5, "θ″ (GP II): mehrlagige kohärente Plättchen; ihre Kohärenzspannungen behindern die "
                                "Versetzungen stark.",
                                "θ″ (GP II): multilayer coherent platelets whose coherency strains strongly impede "
                                "dislocations."),
                               (0.5, 0.75, "θ′: teilkohärente Platten auf {100}, im Schnitt zwei Orientierungen unter 90° – "
                                "Höchsthärte. An den Korngrenzen entsteht eine ausscheidungsfreie Zone (PFZ).",
                                "θ′: semi-coherent plates on {100}, two orientations at 90° in section – peak hardness. A "
                                "precipitate-free zone (PFZ) appears along grain boundaries."),
                               (0.75, 1.0, "Überalterung: inkohärentes θ (Al₂Cu) vergröbert durch Ostwald-Reifung; grobe "
                                "Teilchen auf den Korngrenzen, breitere PFZ; die Härte sinkt.",
                                "Overageing: incoherent θ (Al₂Cu) coarsens by Ostwald ripening; coarse grain-boundary "
                                "particles, wider PFZ; hardness falls.")]},
    "rekristallisation": {"name": ("Rekristallisation und Kornwachstum", "Recrystallisation and grain growth"),
                          "field_um": 200, "refs": ["humphreys2004", "callister"], "kind": "growth",
                          "steps": [(0.0, 0.12, "Kaltverformt: gestreckte Körner mit Gleitbändern und hoher Versetzungsdichte. "
                                     "Erholung: Versetzungen ordnen sich zu Subkorngrenzen, die Festigkeit sinkt kaum.",
                                     "Cold worked: elongated grains with slip bands and a high dislocation density. Recovery: "
                                     "dislocations arrange into sub-grain boundaries; strength drops little."),
                                    (0.12, 0.7, "Primäre Rekristallisation: versetzungsarme Keime an Korngrenzen und "
                                     "Tripelpunkten wachsen in das verformte Gefüge; die gespeicherte Verformungsenergie "
                                     "treibt die Grosswinkelkorngrenzen.",
                                     "Primary recrystallisation: low-dislocation nuclei at grain boundaries and triple junctions "
                                     "grow into the deformed matrix; the stored energy drives the high-angle boundaries."),
                                    (0.7, 1.0, "Kornwachstum: getrieben von der Korngrenzenenergie wachsen grosse Körner auf "
                                     "Kosten kleiner; die mittlere Korngrösse steigt (d² − d₀² ∝ t).",
                                     "Grain growth: driven by grain-boundary energy, large grains grow at the expense of small "
                                     "ones; the mean grain size rises (d² − d₀² ∝ t).")]},
    "erstarrung": {"name": ("Erstarrung mit Dendriten", "Dendritic solidification"), "field_um": 2000,
                   "refs": ["kurz1998", "porter", "jackson1966"], "kind": "growth",
                   "steps": [(0.0, 0.1, "Schmelze über der Liquidustemperatur; an der kalten Formwand (unten) bilden sich die "
                              "ersten Keime.",
                              "Melt above the liquidus; the first nuclei form on the cold mould wall (bottom)."),
                             (0.1, 0.5, "Säulenkristalle wachsen gegen den Wärmefluss: Stämme in ⟨100⟩-Richtung, Seitenarme im "
                              "Abstand λ₂. Vor der Front reichert sich das Legierungselement in der Schmelze an "
                              "(konstitutionelle Unterkühlung).",
                              "Columnar crystals grow against the heat flow: trunks along ⟨100⟩, side arms spaced λ₂. Solute "
                              "piles up in the melt ahead of the front (constitutional undercooling)."),
                             (0.5, 0.85, "Im Inneren keimen gleichachsige Dendriten; die Restschmelze zwischen den Armen wird "
                              "immer reicher an Legierungselement.",
                              "Equiaxed dendrites nucleate in the bulk; the remaining melt between the arms becomes ever "
                              "richer in solute."),
                             (0.85, 1.0, "Die letzte Schmelze erreicht die eutektische Zusammensetzung und erstarrt als "
                              "Eutektikum zwischen den Dendriten (Seigerung).",
                              "The last liquid reaches the eutectic composition and freezes as eutectic between the "
                              "dendrites (segregation).")]},
    "sphaeroidisieren": {"name": ("Einformen (Weichglühen)", "Spheroidising"), "field_um": 20,
                         "refs": ["krauss2015", "lifshitz1961", "porter"], "kind": "stage",
                         "steps": [(0.0, 0.3, "Lamellarer Perlit bei ≈ 700 °C (knapp unter A1): die Lamellen schnüren sich an "
                                    "Fehlern und Koloniegrenzen ab.",
                                    "Lamellar pearlite at ≈ 700 °C (just below A1): the lamellae pinch off at faults and "
                                    "colony boundaries."),
                                   (0.3, 0.7, "Die Bruchstücke runden sich ein; treibende Kraft ist die kleinere Grenzfläche "
                                    "Ferrit/Zementit.",
                                    "The fragments become rounded; the driving force is the smaller ferrite/cementite "
                                    "interface area."),
                                   (0.7, 1.0, "Ostwald-Reifung: kleine Kugeln lösen sich auf, grosse wachsen (r³ ∝ t). Ergebnis: "
                                    "Kugelzementit in Ferrit (GKZ), weich und gut kaltumformbar.",
                                    "Ostwald ripening: small spheroids dissolve, large ones grow (r³ ∝ t). Result: spheroidised "
                                    "cementite in ferrite, soft and easy to cold form.")]},
}
for _t in ("austenitisieren", "perlit", "martensit"):
    TRANSITIONS[_t]["steps"] = _steps_of(_t, 0.45 if _t != "martensit" else 0.2)


def caption(tid: str, f: float, de: bool = True, **params) -> str:
    st = _steps_of(tid, float(params.get("C", 0.45 if tid != "martensit" else 0.2)))
    for lo, hi, a, b in st:
        if lo <= f <= hi or f < lo:
            return a if de else b
    return st[-1][2] if de else st[-1][3]


def transition(tid: str, f: float, seed: int = 1, de: bool = True, **params) -> dict:
    """Skizze einer Umwandlung beim Fortschritt f ∈ [0, 1]; gleiche Geometrie für alle f eines Seeds.
    params: C (Stahl), n (Körner), f_eut (Erstarrung). info.frac = umgewandelter Flächenanteil (bzw. Fortschritt)."""
    if tid not in TRANSITIONS:
        raise SK.StructError(f"Umwandlung „{tid}“ unbekannt")
    f = _cl(float(f))
    seed = int(seed)
    C = float(params.get("C", 0.45 if tid in ("austenitisieren", "perlit") else 0.2 if tid in ("martensit", "anlassen") else 0.45))
    n = params.get("n")
    if tid == "perlit":
        g = _fp_geom(seed, round(C, 3), int(n or 8), round(float(params.get("s", 0.0085)), 5))
        items, legend, frac = _perlit_items(g, f, de)
    elif tid == "austenitisieren":
        g = _fp_geom(seed, round(C, 3), int(n or 8), round(float(params.get("s", 0.0085)), 5))
        items, legend, frac = _aust_items(g, f, de)
    elif tid == "martensit":
        g = _mart_geom(seed, round(C, 3), int(n or 7), "auto")
        items, legend, frac = _mart_items(g, f, de)
    elif tid == "anlassen":
        T = _temper_geom(seed, round(C, 3), int(n or 5))
        items, legend, frac = _temper_items(T, f, de)
    elif tid == "bainit_oben":
        g = _bain_up_geom(seed, int(n or 5))
        items, legend, frac = _bain_up_items(g, f, de)
    elif tid == "bainit_unten":
        g = _bain_lo_geom(seed, int(n or 5))
        items, legend, frac = _bain_lo_items(g, f, de)
    elif tid == "ausscheidung":
        g = _prec_geom(seed, int(n or 5))
        items, legend, frac = _prec_items(g, f, de)
    elif tid == "rekristallisation":
        g = _rex_geom(seed, int(n or 14), int(params.get("n_new", 40)))
        items, legend, frac = _rex_items(g, f, de)
    elif tid == "erstarrung":
        fe = float(params.get("f_eut", 0.3))
        g = _dend_geom(seed, int(params.get("n_col", 5)), int(params.get("n_eq", 3)), 0.03, True)
        items, frac = _dend_items(g, f, de, f_eut=fe)
        legend = [_leg(DEND, _L(de, "Dendriten (Primärkristalle)", "dendrites (primary crystals)"))]
        if f < 1:
            legend.append(_leg(LIQ, _L(de, "Schmelze", "melt")))
        if f > 0.85:
            legend.append(_leg(EUT_BG, _L(de, "Eutektikum (letzte Schmelze)", "eutectic (last liquid)")))
    elif tid == "sphaeroidisieren":
        G = _sph_geom(seed, int(n or 6))
        items, legend, frac = _sph_items(G, f, de)
    else:  # pragma: no cover
        raise SK.StructError(tid)
    cap = caption(tid, f, de, C=C)
    out = {"items": items, "legend": legend, "schematic": True,
           "info": {"tid": tid, "f": round(f, 4), "frac": round(float(frac), 4), "caption": cap}}
    sc = _scale(TRANSITIONS[tid]["field_um"], de)
    if sc:
        out["scale"] = sc
    return out


# ============================================================================ Mechanismen (Bildfolgen)
def _bain_scene(t: float, de: bool, C: float = 0.6) -> dict:
    """Zwei kfz-Zellen mit der eingeschriebenen trz-Zelle (c/a = √2); Bain-Verzerrung bis zum Martensit (Roberts)."""
    a = 3.555 + 0.044 * C
    am, cm = 2.866 - 0.013 * C, 2.866 + 0.116 * C
    t = _cl(t)
    la = 1 + (am / (a / math.sqrt(2)) - 1) * t
    lc = 1 + (cm / a - 1) * t
    ctr = np.array([a, a / 2, a / 2])
    e1 = np.array([1, -1, 0]) / math.sqrt(2)
    e2 = np.array([1, 1, 0]) / math.sqrt(2)
    e3 = np.array([0, 0, 1.0])
    R = np.column_stack([e1, e2, e3])
    M = R @ np.diag([la, la, lc]) @ R.T

    def tr(p):
        return ctr + M @ (np.asarray(p, float) - ctr)

    pts = set()
    for cx in (0, 1):
        for x in (0, 1):
            for y in (0, 1):
                for z in (0, 1):
                    pts.add((cx + x, y, z))
        for p in ((0.5, 0.5, 0), (0.5, 0.5, 1), (0.5, 0, 0.5), (0.5, 1, 0.5), (0, 0.5, 0.5), (1, 0.5, 0.5)):
            pts.add((cx + p[0], p[1], p[2]))
    O = np.array([a / 2, a / 2, 0])
    u, v, c = np.array([a / 2, -a / 2, 0]), np.array([a / 2, a / 2, 0]), np.array([0, 0, a])
    bct = {tuple(np.round((O + i * u + j * v + k * c) / a * 2).astype(int)) for i in (0, 1) for j in (0, 1) for k in (0, 1)}
    bct.add((2, 1, 1))
    sc = SK._Scene()
    k_in = sc.kind("fe_bct", "Fe", _L(de, "Fe in der trz-Zelle", "Fe in the bct cell"), 0.62, "#8d6e63")
    k_out = sc.kind("fe_fcc", "Fe", _L(de, "Fe (übrige kfz-Plätze)", "Fe (other fcc sites)"), 0.62, "#c9b8b0", role="out")
    k_c = sc.kind("c_oct", "C", _L(de, "C auf Oktaederlücke (z)", "C on octahedral site (z)"), 0.38, "#2b2b2b")
    idx = {}
    for p in sorted(pts):
        key = tuple(int(round(q * 2)) for q in p)
        idx[key] = sc.add(tr(np.array(p) * a), k_in if key in bct else k_out)
    for p in ((0.5, 0.5, 0.5), (1.5, 0.5, 0.5)):
        sc.add(tr(np.array(p) * a), k_c)
    for cx in (0, 1):
        corners = [(2 * (cx + x), 2 * y, 2 * z) for x in (0, 1) for y in (0, 1) for z in (0, 1)]
        for i in range(8):
            for j in range(i + 1, 8):
                if sum(abs(corners[i][q] - corners[j][q]) for q in range(3)) == 2:
                    sc.bonds.append([idx[corners[i]], idx[corners[j]]])
    cc = [tr(O + i * u + j * v + k * c) for i in (0, 1) for j in (0, 1) for k in (0, 1)]
    a_b = a / math.sqrt(2) * la
    c_b = a * lc
    ca = c_b / a_b
    top = tr(np.array([a, a / 2, a * 1.25]))
    sc.labels.append({"p": top.round(3).tolist(), "text": f"c/a = {_num(ca, 3, de)}"})
    sc.labels.append({"p": tr(np.array([a, -0.35 * a, -0.1 * a])).round(3).tolist(),
                      "text": _L(de, f"a = {_num(a_b, 2, de)} Å, c = {_num(c_b, 2, de)} Å",
                                 f"a = {_num(a_b, 2, de)} Å, c = {_num(c_b, 2, de)} Å")})
    corners = np.array([cc[0], cc[1], cc[2], cc[3], cc[4], cc[5], cc[6], cc[7]])
    return sc.out(corners, {"c_a": round(ca, 4), "a_bct": round(a_b, 4), "c_bct": round(c_b, 4),
                            "strain": {"a": round(la - 1, 4), "c": round(lc - 1, 4)}, "C_wt": C, "model": "bain"})


_BAIN_STEPS = [(0.0, 0.12, "Kfz-Austenit: zwei Elementarzellen. Darin steckt eine raumzentrierte tetragonale Zelle mit "
                "c/a = √2 ≈ 1,41 (dunkle Atome).",
                "Fcc austenite: two unit cells. They contain a body-centred tetragonal cell with c/a = √2 ≈ 1.41 (dark "
                "atoms)."),
               (0.12, 0.88, "Bain-Verzerrung: die trz-Zelle wird längs c um ≈ 18–20 % gestaucht und längs a um ≈ 12 % "
                "gedehnt – ohne Diffusion, jedes Atom bewegt sich nur einen Bruchteil des Atomabstands.",
                "Bain strain: the bct cell is compressed along c by ≈ 18–20 % and stretched along a by ≈ 12 % – without "
                "diffusion; every atom moves only a fraction of the interatomic distance."),
               (0.88, 1.0, "Ergebnis: tetragonaler Martensit. Der Kohlenstoff auf den Oktaederlücken in z-Richtung verhindert "
                "das kubische Gitter: c/a = 1 + 0,045·C (Roberts). Die tatsächliche Gitterinvariante Scherung kommt hinzu.",
                "Result: tetragonal martensite. Carbon on the z octahedral sites prevents the cubic lattice: c/a = 1 + "
                "0.045·C (Roberts). The lattice-invariant shear adds to this in reality.")]

MECHANISMS: dict[str, dict] = {
    "bain": {"name": ("Bain-Verzerrung kfz → trz", "Bain strain fcc → bct"), "kind": "scene",
             "refs": ["bain1924", "roberts1953", "porter"]},
    "austenitisieren": {"name": TRANSITIONS["austenitisieren"]["name"], "kind": "sketch", "tid": "austenitisieren",
                        "params": {"C": 0.45}},
    "perlit": {"name": TRANSITIONS["perlit"]["name"], "kind": "sketch", "tid": "perlit", "params": {"C": 0.45}},
    "martensit": {"name": TRANSITIONS["martensit"]["name"], "kind": "sketch", "tid": "martensit", "params": {"C": 0.2}},
    "martensit_platte": {"name": ("Plattenmartensit", "Plate martensite"), "kind": "sketch", "tid": "martensit",
                         "params": {"C": 1.3}},
    "anlassen": {"name": TRANSITIONS["anlassen"]["name"], "kind": "sketch", "tid": "anlassen", "params": {}},
    "bainit_oben": {"name": TRANSITIONS["bainit_oben"]["name"], "kind": "sketch", "tid": "bainit_oben", "params": {}},
    "bainit_unten": {"name": TRANSITIONS["bainit_unten"]["name"], "kind": "sketch", "tid": "bainit_unten", "params": {}},
    "ausscheidung": {"name": TRANSITIONS["ausscheidung"]["name"], "kind": "sketch", "tid": "ausscheidung", "params": {}},
    "rekristallisation": {"name": TRANSITIONS["rekristallisation"]["name"], "kind": "sketch", "tid": "rekristallisation",
                          "params": {}},
    "erstarrung": {"name": TRANSITIONS["erstarrung"]["name"], "kind": "sketch", "tid": "erstarrung", "params": {}},
    "sphaeroidisieren": {"name": TRANSITIONS["sphaeroidisieren"]["name"], "kind": "sketch", "tid": "sphaeroidisieren",
                         "params": {}},
}
for _m in MECHANISMS.values():
    if "tid" in _m:
        _m["refs"] = TRANSITIONS[_m["tid"]]["refs"]


def frame_positions(n: int) -> list[float]:
    """n Fortschrittswerte in [0, 1], an den Enden dichter (ease-in-out)."""
    n = int(_cl(n, 2, 600))
    return [round(0.5 - 0.5 * math.cos(PI * k / (n - 1)), 5) for k in range(n)]


def mechanism(mid: str, lang: str = "de", seed: int = 1, n: int = 24) -> dict:
    """Bildfolge eines Mechanismus: frames [{f, label, caption, panel}] mit panel = {kind: sketch|scene, …}."""
    if mid not in MECHANISMS:
        raise SK.StructError(f"Mechanismus „{mid}“ unbekannt")
    de = lang != "en"
    m = MECHANISMS[mid]
    n = int(_cl(int(n), 12, 60))
    frames = []
    for k, f in enumerate(frame_positions(n)):
        if m["kind"] == "scene":
            sc = _bain_scene(f, de)
            cap = next((s[2] if de else s[3] for s in _BAIN_STEPS if s[0] <= f <= s[1]), _BAIN_STEPS[-1][2 if de else 3])
            frames.append({"f": f, "label": f"c/a = {_num(sc['c_a'], 3, de)}", "caption": cap,
                           "panel": {"kind": "scene", "scene": sc}})
        else:
            sk = transition(m["tid"], f, seed, de, **m["params"])
            inf = sk["info"]
            lab = (f"{_L(de, 'Fortschritt', 'progress')} {round(f * 100):d} % · "
                   f"{_L(de, 'umgewandelt', 'transformed')} {round(inf['frac'] * 100):d} %")
            frames.append({"f": f, "label": lab, "caption": inf["caption"], "panel": {"kind": "sketch", "sketch": sk}})
    return {"id": mid, "name": m["name"][0 if de else 1], "frames": frames, "refs_keys": list(m["refs"])}


# ============================================================================ Zustände der Wärmebehandlung
def steel_state(C: float, state: str, f: float = 1.0, seed: int = 1, de: bool = True) -> dict:
    """Stahlzustände aus struktur.py als Skizze: normal, austenit, ab (f = γ-Anteil), gehaertet (f = Martensitanteil),
    angelassen (f = Anlassfortschritt), bainit_oben, bainit_unten, sphaeroidit."""
    C = float(C)
    f = _cl(float(f))
    if state == "normal":
        return transition("perlit", 1.0, seed, de, C=C)
    if state == "austenit":
        return transition("austenitisieren", 1.0, seed, de, C=C)
    if state == "ab":
        g = _fp_geom(int(seed), round(C, 3), 8, 0.0085)
        lo, hi = 0.0, 1.0
        for _ in range(18):                          # Fortschritt so wählen, dass der γ-Anteil f entspricht
            mid = 0.5 * (lo + hi)
            if _aust_items(g, mid, de)[2] < f:
                lo = mid
            else:
                hi = mid
        return transition("austenitisieren", 0.5 * (lo + hi), seed, de, C=C)
    if state == "gehaertet":
        return transition("martensit", f, seed, de, C=C)
    if state == "angelassen":
        return transition("anlassen", f, seed, de, C=min(C, 0.6))
    if state in ("bainit_oben", "bainit_unten"):
        return transition(state, f, seed, de)
    if state == "sphaeroidit":
        return transition("sphaeroidisieren", 0.9 if f >= 1 else f, seed, de)
    raise SK.StructError(f"Stahlzustand „{state}“ unbekannt")


AL_STATES = {"ss": 0.03, "gp": 0.2, "peak": 0.6, "over": 0.85, "eq": 1.0}


def al_state(key: str, seed: int = 1, de: bool = True) -> dict:
    """Al-Cu-Zustände (ss, gp, peak, over, eq) aus der Ausscheidungsfolge bei festem Fortschritt."""
    if key not in AL_STATES:
        raise SK.StructError(f"Al-Zustand „{key}“ unbekannt")
    return transition("ausscheidung", AL_STATES[key], seed, de)


# ============================================================================ Quellen, Prüfhilfen
@lru_cache(maxsize=1)
def sources() -> dict:
    """Eigene Quellen der Gefügebilder (data/gefuege_quellen.json)."""
    return json.loads((DATA / "gefuege_quellen.json").read_text("utf-8")).get("quellen") or {}


def all_refs() -> list[str]:
    keys = []
    for c in CONSTITUENTS.values():
        keys += c["refs"]
    for t in TRANSITIONS.values():
        keys += t["refs"]
    for m in MECHANISMS.values():
        keys += m["refs"]
    return sorted(set(keys))


def count_primitives(sk_or_items) -> int:
    """Zahl der gezeichneten Grundelemente (Schraffurlinien wie im Zeichner gezählt)."""
    items = sk_or_items.get("items", []) if isinstance(sk_or_items, dict) else sk_or_items
    n = 0
    for it in items:
        t = it["t"]
        if t in ("dots", "dashes"):
            n += len(it["p"])
        elif t == "hatch":
            P = it["poly"]
            cx, cy = _mean(P)
            R = max(math.hypot(v[0] - cx, v[1] - cy) for v in P) * 1.1
            n += int(math.ceil((2 * R - it.get("o", 0) * it["s"]) / it["s"]))
        elif t == "clip":
            n += count_primitives(it.get("items") or [])
        else:
            n += 1
    return n
