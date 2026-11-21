"""Auswahlen (ROIs), Messungen, Linienprofil und Partikelanalyse.

ROI-Koordinaten sind Bildpixel mit (0, 0) in der linken oberen Ecke des ersten Pixels; ein Pixel (x, y)
deckt [x, x+1) × [y, y+1) ab und gehoert zu einer Flaechen-ROI, wenn sein Mittelpunkt innen liegt.

ROI-Formen:
  {"type": "rect", "x", "y", "w", "h"}        {"type": "oval", "x", "y", "w", "h"}
  {"type": "polygon"|"freehand"|"traced", "pts": [[x, y], ...]}
  {"type": "line", "x1", "y1", "x2", "y2", "width"}   {"type": "point", "pts": [[x, y], ...]}
"""
from __future__ import annotations

import math

import numpy as np
from matplotlib.path import Path

from .imageio import Calib
from .label import fill_holes, label

AREA_TYPES = ("rect", "oval", "polygon", "freehand", "traced")


def gray_of(img: np.ndarray) -> np.ndarray:
    """2D-Graustufen fuer Messungen; RGB wird ungewichtet gemittelt."""
    return img.astype(np.float32).mean(axis=-1) if img.ndim == 3 else img.astype(np.float32)


# ----------------------------------------------------------------------------- ROI-Masken
def roi_mask(roi: dict, shape: tuple[int, int]) -> tuple[np.ndarray, int, int]:
    """(Maske ueber dem begrenzenden Rechteck, y0, x0). Leere Maske, wenn ausserhalb."""
    H, W = shape
    t = roi.get("type")
    if t in ("rect", "oval"):
        x, y, w, h = (float(roi[k]) for k in ("x", "y", "w", "h"))
        if w < 0:
            x, w = x + w, -w
        if h < 0:
            y, h = y + h, -h
        x0, y0 = max(0, int(math.floor(x))), max(0, int(math.floor(y)))
        x1, y1 = min(W, int(math.ceil(x + w))), min(H, int(math.ceil(y + h)))
        if x1 <= x0 or y1 <= y0:
            return np.zeros((0, 0), bool), 0, 0
        yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float64) + 0.5
        if t == "rect":
            m = (xx >= x) & (xx < x + w) & (yy >= y) & (yy < y + h)
        else:
            cx, cy, rx, ry = x + w / 2, y + h / 2, max(w / 2, 1e-9), max(h / 2, 1e-9)
            m = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2 <= 1.0
        return m, y0, x0
    if t in ("polygon", "freehand", "traced"):
        pts = np.asarray(roi.get("pts") or [], dtype=np.float64)
        if len(pts) < 3:
            return np.zeros((0, 0), bool), 0, 0
        x0, y0 = max(0, int(math.floor(pts[:, 0].min()))), max(0, int(math.floor(pts[:, 1].min())))
        x1, y1 = min(W, int(math.ceil(pts[:, 0].max()))), min(H, int(math.ceil(pts[:, 1].max())))
        if x1 <= x0 or y1 <= y0:
            return np.zeros((0, 0), bool), 0, 0
        yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float64) + 0.5
        inside = Path(pts).contains_points(np.column_stack([xx.ravel(), yy.ravel()]))
        return inside.reshape(xx.shape), y0, x0
    raise ValueError(f"Keine Flächenauswahl: {t}")


def full_mask(roi: dict | None, shape) -> np.ndarray:
    m = np.zeros(shape, bool)
    if roi is None:
        m[:] = True
        return m
    sub, y0, x0 = roi_mask(roi, shape)
    if sub.size:
        m[y0:y0 + sub.shape[0], x0:x0 + sub.shape[1]] = sub
    return m


def roi_perimeter(roi: dict, calib: Calib) -> float:
    t = roi.get("type")
    if t == "rect":
        return 2 * (abs(roi["w"]) * calib.pw + abs(roi["h"]) * calib.ph)
    if t == "oval":
        a, b = abs(roi["w"]) * calib.pw / 2, abs(roi["h"]) * calib.ph / 2
        h = ((a - b) / (a + b)) ** 2 if a + b > 0 else 0
        return math.pi * (a + b) * (1 + 3 * h / (10 + math.sqrt(4 - 3 * h)))  # Ramanujan
    pts = np.asarray(roi.get("pts") or [], dtype=np.float64)
    if len(pts) < 2:
        return 0.0
    q = np.vstack([pts, pts[:1]])
    dx, dy = np.diff(q[:, 0]) * calib.pw, np.diff(q[:, 1]) * calib.ph
    return float(np.hypot(dx, dy).sum())


# ----------------------------------------------------------------------------- Messen
def _stats(vals: np.ndarray) -> dict:
    if vals.size == 0:
        return {"Mean": None, "StdDev": None, "Min": None, "Max": None, "Median": None, "Mode": None}
    v = vals.astype(np.float64)
    vals_r = np.round(v)
    uniq, cnt = np.unique(vals_r, return_counts=True)
    return {"Mean": float(v.mean()), "StdDev": float(v.std(ddof=1)) if v.size > 1 else 0.0, "Min": float(v.min()),
            "Max": float(v.max()), "Median": float(np.median(v)), "Mode": float(uniq[np.argmax(cnt)])}


def line_scale(calib: Calib, dx: float, dy: float) -> float:
    """Kalibrierte Laenge je Pixelschritt entlang der Richtung (dx, dy): |(dx·pw, dy·ph)| / |(dx, dy)|.
    Bei nicht quadratischen Pixeln haengt sie von der Richtung ab; bei quadratischen ist sie pw."""
    L = math.hypot(dx, dy)
    return math.hypot(dx * calib.pw, dy * calib.ph) / L if L > 0 else calib.pw


# Quelle der Quantildefinition (Format wie threshold.REFERENCES)
QUANTILE_REF = ("hyndman1996", dict(entry_type="article", author="Hyndman, Rob J. and Fan, Yanan",
                                    title="Sample quantiles in statistical packages", journal="The American Statistician",
                                    volume="50", number="4", pages="361--365", year="1996"))


def wquantile(x, w, qs) -> list:
    """Gewichtete Quantile, Mittelpunktsregel: die sortierten Werte x_i stehen bei P_i = (S_i − w_i/2)/S_n
    (S_i = kumulierte Gewichte), dazwischen linear interpoliert, ausserhalb [P_1, P_n] der erste bzw. letzte Wert.
    Mit gleichen Gewichten ist das Definition 5 nach Hyndman & Fan (1996), P_i = (i − ½)/n. Unabhaengig vom
    Massstab der Gewichte, daher auch fuer Volumengewichte (d³) geeignet."""
    x = np.asarray(x, dtype=np.float64)
    w = np.broadcast_to(np.asarray(w, dtype=np.float64), x.shape)
    ok = np.isfinite(x) & np.isfinite(w) & (w > 0)
    x, w = x[ok], w[ok]
    if not x.size:
        return [None for _ in qs]
    o = np.argsort(x, kind="stable")
    x, w = x[o], w[o]
    S = np.cumsum(w)
    P = (S - w / 2) / S[-1]
    return [float(np.interp(q, P, x)) for q in qs]


def wmean_sd(x, w) -> tuple:
    """Gewichteter Mittelwert und Standardabweichung mit Nenner Σw − Σw²/Σw (gleich n − 1 bei gleichen Gewichten)."""
    x = np.asarray(x, dtype=np.float64)
    w = np.asarray(w, dtype=np.float64)
    if not x.size:
        return None, None
    V1 = w.sum()
    m = float((w * x).sum() / V1)
    den = V1 - (w * w).sum() / V1
    sd = float(math.sqrt(max((w * (x - m) ** 2).sum() / den, 0.0))) if x.size > 1 and den > 0 else None
    return m, sd


def sample_line(img: np.ndarray, x1, y1, x2, y2, width: int = 1) -> tuple[np.ndarray, np.ndarray]:
    """Grauwerte entlang einer Linie (bilinear, Schritt 1 Pixel); bei width > 1 quer gemittelt."""
    g = gray_of(img)
    H, W = g.shape
    L = math.hypot(x2 - x1, y2 - y1)
    n = max(2, int(round(L)) + 1)
    t = np.linspace(0, 1, n)
    xs, ys = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
    offs = [0.0]
    width = int(width or 1)
    if width > 1 and L > 0:
        offs = np.linspace(-(width - 1) / 2, (width - 1) / 2, width)
    nx, ny = (-(y2 - y1) / L, (x2 - x1) / L) if L > 0 else (0, 0)
    acc = np.zeros(n)
    for o in offs:
        px = np.clip(xs + nx * o - 0.5, 0, W - 1)
        py = np.clip(ys + ny * o - 0.5, 0, H - 1)
        x0, y0 = np.floor(px).astype(int), np.floor(py).astype(int)
        x1_, y1_ = np.minimum(x0 + 1, W - 1), np.minimum(y0 + 1, H - 1)
        fx, fy = px - x0, py - y0
        v = (g[y0, x0] * (1 - fx) * (1 - fy) + g[y0, x1_] * fx * (1 - fy) + g[y1_, x0] * (1 - fx) * fy
             + g[y1_, x1_] * fx * fy)
        acc += v
    return t * L, acc / len(offs)


def measure(img: np.ndarray, roi: dict | None, calib: Calib) -> dict:
    """Messwerte einer Auswahl (oder des ganzen Bildes) auf dem 2D-Bild."""
    g = gray_of(img)
    H, W = g.shape
    t = (roi or {}).get("type", "image")
    if t == "line":
        x1, y1, x2, y2 = (float(roi[k]) for k in ("x1", "y1", "x2", "y2"))
        _, vals = sample_line(img, x1, y1, x2, y2, int(roi.get("width") or 1))
        dx, dy = (x2 - x1) * calib.pw, (y2 - y1) * calib.ph
        row = {"Type": "line", "Length": float(math.hypot(dx, dy)),
               "Angle": float(math.degrees(math.atan2(-(y2 - y1), x2 - x1))) + 0.0,
               "X": (x1 + x2) / 2 * calib.pw, "Y": (y1 + y2) / 2 * calib.ph}
        row.update(_stats(vals))
        return row
    if t == "point":
        out = []
        for x, y in roi.get("pts") or []:
            xi, yi = min(W - 1, max(0, int(x))), min(H - 1, max(0, int(y)))
            out.append({"X": (xi + 0.5) * calib.pw, "Y": (yi + 0.5) * calib.ph, "Value": float(g[yi, xi])})
        return {"Type": "point", "Count": len(out), "Points": out,
                "Mean": float(np.mean([p["Value"] for p in out])) if out else None}
    m = full_mask(roi, (H, W))
    vals = g[m]
    n = int(m.sum())
    ys, xs = np.nonzero(m)
    row = {"Type": t if roi else "image", "Area": n * calib.pw * calib.ph, "Pixels": n}
    row.update(_stats(vals))
    if n:
        row["X"] = float((xs.mean() + 0.5) * calib.pw)
        row["Y"] = float((ys.mean() + 0.5) * calib.ph)
        row["IntDen"] = row["Area"] * row["Mean"]
        row["RawIntDen"] = float(vals.astype(np.float64).sum())
        bx0, by0, bx1, by1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
        row.update({"BX": bx0 * calib.pw, "BY": by0 * calib.ph, "Width": (bx1 - bx0) * calib.pw, "Height": (by1 - by0) * calib.ph})
    if roi:
        row["Perim."] = roi_perimeter(roi, calib)
        if row["Perim."] > 0:
            row["Circ."] = min(1.0, 4 * math.pi * row["Area"] / row["Perim."] ** 2)
    else:
        row["Perim."] = 2 * (W * calib.pw + H * calib.ph)
    return row


# ----------------------------------------------------------------------------- Partikel
def _hull(points: np.ndarray) -> np.ndarray:
    """Konvexe Huelle (monotone Kette), gegen den Uhrzeigersinn."""
    pts = np.unique(points, axis=0)
    if len(pts) < 3:
        return pts
    pts = pts[np.lexsort((pts[:, 1], pts[:, 0]))]

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts.tolist():
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts.tolist()):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return np.array(lower[:-1] + upper[:-1], dtype=np.float64)


def _feret(hull: np.ndarray) -> tuple[float, float, float]:
    """(Feret max, Winkel in Grad, minimale Breite) einer konvexen Huelle."""
    if len(hull) < 2:
        return 0.0, 0.0, 0.0
    d = hull[:, None, :] - hull[None, :, :]
    dist = np.hypot(d[..., 0], d[..., 1])
    i, j = np.unravel_index(np.argmax(dist), dist.shape)
    p, q = hull[i], hull[j]
    if p[0] > q[0]:
        p, q = q, p
    ang = math.degrees(math.atan2(-(q[1] - p[1]), q[0] - p[0])) % 180.0
    if len(hull) < 3:
        return float(dist.max()), ang, 0.0
    e = np.roll(hull, -1, axis=0) - hull
    n = np.column_stack([-e[:, 1], e[:, 0]])
    ln = np.hypot(n[:, 0], n[:, 1])
    ok = ln > 0
    n = n[ok] / ln[ok, None]
    proj = hull @ n.T
    widths = proj.max(axis=0) - proj.min(axis=0)
    return float(dist.max()), ang, float(widths.min())


def _shoelace(p: np.ndarray) -> float:
    if len(p) < 3:
        return 0.0
    x, y = p[:, 0], p[:, 1]
    return 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def _perimeters(lab: np.ndarray, n: int, pw: float = 1.0, ph: float = 1.0) -> np.ndarray:
    """Umfang je Label: Laenge der Marching-Squares-Kontur auf Hoehe ½ zwischen den Pixelmitten, d. h. des Polygons
    durch die Mitten der Kanten zwischen Vordergrund- und Hintergrundpixel. Je 2×2-Zelle aus Pixelmitten:
    1 oder 3 Vordergrundpixel -> ½·|(pw, ph)| (Ecke abgeschnitten); 2 waagrecht benachbarte -> pw;
    2 senkrecht benachbarte -> ph; 2 diagonale (Sattel, als getrennt behandelt) -> |(pw, ph)|.
    Mit pw = ph = 1: gerade Schritte 1, Ecken √½. Alle Konturen zaehlen, auch die von Loechern.
    In einer 2×2-Zelle liegt bei 8er-Nachbarschaft hoechstens ein Label."""
    p = np.pad(lab, 1)
    a, b, c, d = p[:-1, :-1], p[:-1, 1:], p[1:, :-1], p[1:, 1:]
    L = np.maximum(np.maximum(a, b), np.maximum(c, d))
    fa, fb, fc, fd = a > 0, b > 0, c > 0, d > 0
    cnt = fa.astype(np.int8) + fb + fc + fd
    diag = (cnt == 2) & (fa == fd)        # Sattel: zwei diagonale Pixel
    horiz = (cnt == 2) & (fa == fb) & ~diag   # obere oder untere Zeile belegt: waagrechte Kante
    hyp = math.hypot(pw, ph)
    seg = np.where((cnt == 1) | (cnt == 3), hyp / 2, 0.0)
    seg = np.where(horiz, pw, seg)
    seg = np.where((cnt == 2) & ~diag & ~horiz, ph, seg)
    seg = np.where(diag, hyp, seg)
    return np.bincount(L.ravel(), weights=seg.ravel(), minlength=n + 1)


def _outer_perimeter(sub: np.ndarray, pw: float, ph: float) -> float:
    """Aeusserer Umfang einer Einzelmaske (Loecher gefuellt), gleicher Schaetzer wie _perimeters."""
    f = fill_holes(np.pad(sub, 1))
    return float(_perimeters(f.astype(np.int32), 1, pw, ph)[1])


def _interior(reg: np.ndarray) -> np.ndarray:
    """Inneres einer Auswertungsflaeche: Pixel, deren 8 Nachbarn alle in der Flaeche liegen (Bildrand zaehlt aussen)."""
    p = np.pad(reg, 1, constant_values=False)
    H, W = reg.shape
    out = reg.copy()
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            out &= p[dy:dy + H, dx:dx + W]
    return out


DEFAULT_PARTICLE = {"size_min": 0.0, "size_max": None, "circ_min": 0.0, "circ_max": 1.0, "exclude_edges": True,
                    "include_holes": False, "size_in_pixels": False, "perimeter": "outer"}

SUMMARY_KEYS = ("Perim.", "Circ.", "ECD", "Feret", "MinFeret", "AR", "Solidity", "Mean")


def particles(binary: np.ndarray, intensity: np.ndarray | None, calib: Calib, params: dict | None = None,
              region: dict | None = None) -> dict:
    """Partikelanalyse auf einer Binaermaske (Objekte > 0), 8er-Nachbarschaft.

    Liefert {"rows": [...], "summary": {...}, "labels": Labelbild der behaltenen Partikel}.
    Groessen in kalibrierten Einheiten (oder Pixeln, wenn size_in_pixels).

    Randkorrektur (exclude_edges): gezaehlt und vermessen werden nur Partikel, deren Begrenzungsrechteck ganz im
    Inneren der Auswertungsflaeche liegt (ganzes Bild: beruehrt den Bildrand nicht). Jedes bekommt das Gewicht
    w = |R| / N(w, h) nach Miles und Lantuéjoul: |R| = Pixel der Flaeche, N = Anzahl der Lagen, in denen ein
    Rechteck seiner Groesse ganz im Inneren liegt (ganzes Bild: (W − w − 1)(H − h − 1)). Verteilungskennwerte sind
    mit w gewichtet. Der Flaechenanteil zaehlt alle Partikel, die die Filter passieren, auch die am Rand."""
    P = {**DEFAULT_PARTICLE, **(params or {})}
    m = np.asarray(binary) > 0
    H, W = m.shape
    reg = full_mask(region, (H, W)) if region and region.get("type") in AREA_TYPES else None
    if reg is not None:
        m &= reg
    if P["include_holes"]:
        m = fill_holes(m)
    lab, n = label(m, conn=8)
    pa = calib.pw * calib.ph
    g = gray_of(intensity) if intensity is not None else None
    res = {"rows": [], "summary": {}, "labels": np.zeros_like(lab)}
    reg_px = int(reg.sum()) if reg is not None else H * W
    region_area = reg_px * pa
    edge_corr = bool(P["exclude_edges"])
    outer = P.get("perimeter", "outer") != "total"
    if n == 0:
        res["summary"] = {"Count": 0, "CountCorrected": 0.0, "Density": 0.0, "TotalArea": 0.0, "ForegroundArea": 0.0,
                          "AverageSize": None, "AreaFraction": 0.0, "RegionArea": region_area,
                          "EdgeCorrection": "miles-lantuejoul" if edge_corr else "none",
                          "Perimeter": "outer" if outer else "total"}
        return res
    flat = lab.ravel()
    yy, xx = np.indices((H, W))
    area_px = np.bincount(flat, minlength=n + 1).astype(np.float64)
    sx = np.bincount(flat, weights=xx.ravel() + 0.5, minlength=n + 1)
    sy = np.bincount(flat, weights=yy.ravel() + 0.5, minlength=n + 1)
    sxx = np.bincount(flat, weights=(xx.ravel() + 0.5) ** 2, minlength=n + 1)
    syy = np.bincount(flat, weights=(yy.ravel() + 0.5) ** 2, minlength=n + 1)
    sxy = np.bincount(flat, weights=(xx.ravel() + 0.5) * (yy.ravel() + 0.5), minlength=n + 1)
    pw, ph = calib.pw, calib.ph
    perim_all = _perimeters(lab, n, pw, ph)           # alle Konturen (aussen und Loecher)
    holes = None
    if outer and not P["include_holes"]:
        hm = fill_holes(m) & ~m
        holes = hm if hm.any() else None
    # Randkorrektur: Inneres der Flaeche und Anzahl der Lagen eines w × h-Rechtecks darin
    if reg is None:
        def inside(x0, y0, x1, y1):
            return x0 >= 1 and y0 >= 1 and x1 <= W - 1 and y1 <= H - 1

        def npos(w, h):
            return max(0, W - w - 1) * max(0, H - h - 1)
    else:
        C = np.zeros((H + 1, W + 1), dtype=np.int64)
        C[1:, 1:] = _interior(reg).astype(np.int64).cumsum(0).cumsum(1)
        cache: dict = {}

        def inside(x0, y0, x1, y1):
            return int(C[y1, x1] - C[y0, x1] - C[y1, x0] + C[y0, x0]) == (x1 - x0) * (y1 - y0)

        def npos(w, h):
            if (w, h) not in cache:
                if w > W or h > H:
                    cache[(w, h)] = 0
                else:
                    S = C[h:, w:] - C[:-h, w:] - C[h:, :-w] + C[:-h, :-w]
                    cache[(w, h)] = int(np.count_nonzero(S == w * h))
            return cache[(w, h)]
    order = np.argsort(flat, kind="stable")
    bounds = np.searchsorted(flat[order], np.arange(n + 2))
    if g is not None:
        gv = g.ravel()[order]
        sg = np.bincount(flat, weights=g.ravel(), minlength=n + 1)
        sgg = np.bincount(flat, weights=g.ravel().astype(np.float64) ** 2, minlength=n + 1)
    # Randpixel fuer die Huelle
    er = np.zeros_like(m)
    er[1:-1, 1:-1] = m[1:-1, 1:-1] & m[:-2, 1:-1] & m[2:, 1:-1] & m[1:-1, :-2] & m[1:-1, 2:]
    edge = m & ~er
    eflat = np.where(edge.ravel(), flat, 0)
    eorder = np.argsort(eflat, kind="stable")
    ebounds = np.searchsorted(eflat[eorder], np.arange(n + 2))
    ex, ey = xx.ravel()[eorder], yy.ravel()[eorder]
    # Begrenzungsrechteck
    xs_all, ys_all = xx.ravel()[order], yy.ravel()[order]

    keep_ids = []
    rows = []
    unit_area = 1.0 if P["size_in_pixels"] else pa
    smin = float(P["size_min"] or 0.0)
    smax = float(P["size_max"]) if P["size_max"] not in (None, "", "inf", "Infinity") else math.inf
    fg_area = 0.0
    fg_areas = []                                     # Flächen aller Partikel des Flächenanteils (Bootstrap der Unsicherheit)
    for k in range(1, n + 1):
        a_px = area_px[k]
        s, e = bounds[k], bounds[k + 1]
        bx0, bx1 = int(xs_all[s:e].min()), int(xs_all[s:e].max()) + 1
        by0, by1 = int(ys_all[s:e].min()), int(ys_all[s:e].max()) + 1
        size = a_px * unit_area
        if size < smin or size > smax:
            continue
        perim = float(perim_all[k])
        if holes is not None and holes[by0:by1, bx0:bx1].any():
            perim = _outer_perimeter(lab[by0:by1, bx0:bx1] == k, pw, ph)
        area = a_px * pa
        circ = min(1.0, 4 * math.pi * area / perim ** 2) if perim > 0 else 1.0
        if circ < float(P["circ_min"] or 0) or circ > float(P["circ_max"] if P["circ_max"] is not None else 1):
            continue
        fg_area += area                               # Flaechenanteil: auch Randpartikel
        fg_areas.append(area)
        if edge_corr:
            if not inside(bx0, by0, bx1, by1):
                continue
            wt = reg_px / npos(bx1 - bx0, by1 - by0)
        else:
            wt = 1.0
        cx, cy = sx[k] / a_px, sy[k] / a_px
        # zweite Zentralmomente in kalibrierten Einheiten (x mit pw, y mit ph), je + Ausdehnung eines Pixels²/12
        mu20 = (sxx[k] / a_px - cx * cx + 1 / 12) * pw * pw
        mu02 = (syy[k] / a_px - cy * cy + 1 / 12) * ph * ph
        mu11 = (sxy[k] / a_px - cx * cy) * pw * ph
        common = math.sqrt(max(((mu20 - mu02) / 2) ** 2 + mu11 ** 2, 0))
        l1 = max((mu20 + mu02) / 2 + common, 1e-300)
        l2 = max((mu20 + mu02) / 2 - common, 1e-300)
        major, minor = 4 * math.sqrt(l1), 4 * math.sqrt(l2)
        scale = math.sqrt(area / (math.pi * major * minor / 4)) if major * minor > 0 else 1.0
        major, minor = major * scale, minor * scale
        angle = math.degrees(0.5 * math.atan2(-2 * mu11, mu20 - mu02)) % 180.0
        es, ee = ebounds[k], ebounds[k + 1]
        px, py = ex[es:ee].astype(np.float64), ey[es:ee].astype(np.float64)
        corners = np.concatenate([np.column_stack([px, py]), np.column_stack([px + 1, py]),
                                  np.column_stack([px, py + 1]), np.column_stack([px + 1, py + 1])])
        corners[:, 0] *= calib.pw
        corners[:, 1] *= calib.ph
        hull = _hull(corners)
        feret, fang, minferet = _feret(hull)
        hull_area = _shoelace(hull)
        row = {"#": len(rows) + 1, "Area": area, "Perim.": perim, "Circ.": circ,
               "ECD": 2 * math.sqrt(area / math.pi), "Feret": feret, "FeretAngle": fang, "MinFeret": minferet,
               "Major": major, "Minor": minor, "Angle": angle, "AR": major / minor if minor > 0 else None,
               "Round": 4 * area / (math.pi * major ** 2) if major > 0 else None,
               "Solidity": min(1.0, area / hull_area) if hull_area > 0 else 1.0,
               "X": cx * calib.pw, "Y": cy * calib.ph, "BX": bx0 * calib.pw, "BY": by0 * calib.ph,
               "Width": (bx1 - bx0) * calib.pw, "Height": (by1 - by0) * calib.ph, "Pixels": int(a_px),
               "Weight": wt, "_px": [cx, cy]}
        if g is not None:
            mean = sg[k] / a_px
            var = max(sgg[k] / a_px - mean * mean, 0.0)
            vv = gv[s:e]
            row.update({"Mean": mean, "StdDev": math.sqrt(var * a_px / (a_px - 1)) if a_px > 1 else 0.0,
                        "Min": float(vv.min()), "Max": float(vv.max()), "IntDen": area * mean})
        rows.append(row)
        keep_ids.append(k)
    keep = np.zeros(n + 1, dtype=np.int32)
    keep[keep_ids] = np.arange(1, len(keep_ids) + 1, dtype=np.int32)
    res["labels"] = keep[lab]
    res["rows"] = rows
    res["fg_areas"] = fg_areas
    areas = np.array([r["Area"] for r in rows], dtype=np.float64)
    wts = np.array([r["Weight"] for r in rows], dtype=np.float64)
    m_a, sd_a = wmean_sd(areas, wts)
    summ = {"Count": len(rows), "CountCorrected": float(wts.sum()),
            "Density": float(wts.sum() / region_area) if region_area else None,
            "TotalArea": float(areas.sum()) if rows else 0.0, "ForegroundArea": float(fg_area),
            "AverageSize": m_a, "SDSize": sd_a,
            "AreaFraction": float(fg_area / region_area * 100) if region_area else 0.0,
            "RegionArea": float(region_area),
            "EdgeCorrection": "miles-lantuejoul" if edge_corr else "none",
            "Perimeter": "outer" if outer else "total"}
    for key in SUMMARY_KEYS:
        sel = [(r[key], r["Weight"]) for r in rows if r.get(key) is not None]
        mean, sd = wmean_sd([v for v, _ in sel], [x for _, x in sel])
        summ["Mean" + key.rstrip(".")] = mean
        summ["SD" + key.rstrip(".")] = sd
    if rows:
        ecd = np.array([r["ECD"] for r in rows], dtype=np.float64)
        # Q0: anzahlgewichtet (je Partikel Gewicht w); Q3: volumengewichtet mit w·ECD³ (Kugeln mit d = ECD)
        summ["D10"], summ["D50"], summ["D90"] = wquantile(ecd, wts, (0.1, 0.5, 0.9))
        summ["Dv10"], summ["Dv50"], summ["Dv90"] = wquantile(ecd, wts * ecd ** 3, (0.1, 0.5, 0.9))
    res["summary"] = summ
    return res


def outline_rgba(labels: np.ndarray, color=(0, 220, 255), fill_alpha: int = 50) -> np.ndarray:
    """RGBA-Overlay: Konturen der Partikel kraeftig, Flaeche leicht eingefaerbt."""
    m = labels > 0
    er = np.zeros_like(m)
    er[1:-1, 1:-1] = m[1:-1, 1:-1] & m[:-2, 1:-1] & m[2:, 1:-1] & m[1:-1, :-2] & m[1:-1, 2:]
    edge = m & ~er
    out = np.zeros(labels.shape + (4,), dtype=np.uint8)
    out[m] = (*color, fill_alpha)
    out[edge] = (*color, 255)
    return out
