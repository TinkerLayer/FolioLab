"""Abbildungen fuer Bericht und Export (matplotlib): Bild mit Massstab, Partikel-Overlay, Histogramm,
Groessenverteilung, Form gegen Groesse, Linienprofil, Vergleich mehrerer Bilder."""
from __future__ import annotations

import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import colormaps  # noqa: E402
from matplotlib.patches import Ellipse, Polygon, Rectangle  # noqa: E402

LUTS = {
    "grays": "Graustufen", "inverted": "Graustufen invertiert", "inferno": "Glut (inferno)", "magma": "Magma",
    "viridis": "Viridis", "turbo": "Spektrum (turbo)", "red": "Rot", "green": "Grün", "blue": "Blau",
    "magenta": "Magenta", "cyan": "Cyan", "yellow": "Gelb",
}
_SOLID = {"red": (1, 0, 0), "green": (0, 1, 0), "blue": (0, 0, 1), "magenta": (1, 0, 1), "cyan": (0, 1, 1),
          "yellow": (1, 1, 0)}


def lut_table(name: str) -> np.ndarray:
    """256×3 uint8."""
    x = np.linspace(0, 1, 256)
    if name == "grays" or name not in LUTS:
        t = np.stack([x, x, x], 1)
    elif name == "inverted":
        t = np.stack([1 - x, 1 - x, 1 - x], 1)
    elif name in _SOLID:
        t = np.outer(x, _SOLID[name])
    else:
        t = colormaps[name](x)[:, :3]
    return np.round(t * 255).astype(np.uint8)


def all_luts() -> dict:
    return {k: {"label": v, "table": lut_table(k).tolist()} for k, v in LUTS.items()}


def render(img: np.ndarray, kind: str, display: dict | None) -> np.ndarray:
    """2D-Graustufen (mit Anzeigebereich und LUT) oder RGB -> H×W×3 uint8."""
    display = display or {}
    if kind == "rgb":
        lo, hi = float(display.get("min", 0)), float(display.get("max", 255))
        if hi <= lo:
            hi = lo + 1
        return np.clip((img.astype(np.float32) - lo) / (hi - lo) * 255, 0, 255).astype(np.uint8)
    v = img.astype(np.float32)
    lo = float(display["min"]) if display.get("min") is not None else float(np.nanmin(v))
    hi = float(display["max"]) if display.get("max") is not None else float(np.nanmax(v))
    if hi <= lo:
        hi = lo + 1
    idx = np.clip((v - lo) / (hi - lo) * 255, 0, 255).astype(np.uint8)
    return lut_table(display.get("lut", "grays"))[idx]


def nice_length(total: float) -> float:
    """Runde Laenge fuer den Massstabsbalken (etwa ein Fuenftel der Bildbreite)."""
    target = total / 5
    if target <= 0:
        return 1
    e = 10 ** math.floor(math.log10(target))
    for f in (5, 2, 1):
        if f * e <= target:
            return f * e
    return e


def _fmt(v, lang):
    s = f"{v:g}"
    return s.replace(".", ",") if lang == "de" else s


# Massstabsbalken: gleiche Einstellungen und gleiche Lageberechnung wie in der Seite (index.html, sbGeom).
# thick und font in Prozent der kürzeren Bildseite, len in der Einheit der Kalibrierung (None = automatisch).
SCALEBAR_DEFAULT = {"len": None, "pos": "br", "color": "white", "thick": 1.2, "font": 3.0, "label": True, "box": False}


def scalebar_opts(v):
    """state["scalebar"] -> Einstellungen oder None (kein Balken).

    False: kein Balken; True/None: Vorgabe; dict: Einstellungen (fehlende Schlüssel aus der Vorgabe, show=False aus).
    """
    if v is False:
        return None
    o = dict(SCALEBAR_DEFAULT)
    if isinstance(v, dict):
        if v.get("show") is False:
            return None
        o.update({k: v[k] for k in SCALEBAR_DEFAULT if v.get(k) is not None})

    def num(x, lo, hi, d):
        try:
            x = float(x)
        except (TypeError, ValueError):
            return d
        return min(hi, max(lo, x)) if math.isfinite(x) else d

    try:
        ln = float(o["len"]) if o["len"] not in (None, "") else None
    except (TypeError, ValueError):
        ln = None
    o["len"] = ln if ln is not None and math.isfinite(ln) and ln > 0 else None
    o["pos"] = o["pos"] if o["pos"] in ("br", "bl", "tr", "tl") else "br"
    o["color"] = "black" if o["color"] == "black" else "white"
    o["thick"] = num(o["thick"], 0.2, 10, SCALEBAR_DEFAULT["thick"])
    o["font"] = num(o["font"], 0.5, 15, SCALEBAR_DEFAULT["font"])
    o["label"] = bool(o["label"])
    o["box"] = bool(o["box"])
    return o


def scalebar_geom(W, H, calib, opts, lang="de", text_w=None):
    """Lage des Balkens in Bildpixeln: Balken, Beschriftung (Mitte) und Kasten."""
    base = min(W, H)
    L = opts["len"] or nice_length(W * calib.pw)
    px = L / calib.pw
    bh = max(1.0, base * opts["thick"] / 100)
    fpx = base * opts["font"] / 100
    m = base * 0.04
    text = f"{_fmt(L, lang)} {calib.unit}"
    th = fpx * 1.15 if opts["label"] else 0.0
    gap = fpx * 0.25 if opts["label"] else 0.0
    tw = (text_w if text_w is not None else 0.62 * fpx * len(text)) if opts["label"] else 0.0
    bw = max(px, tw)
    blk = th + gap + bh
    pad = fpx * 0.35 if opts["box"] else 0.0
    x0 = W - m - pad - bw if opts["pos"][1] == "r" else m + pad
    y0 = H - m - pad - blk if opts["pos"][0] == "b" else m + pad
    return {"L": L, "px": px, "text": text, "font_px": fpx,
            "bar": (x0 + (bw - px) / 2, y0 + th + gap, px, bh),
            "text_xy": (x0 + bw / 2, y0 + th / 2),
            "box": (x0 - pad, y0 - pad, bw + 2 * pad, blk + 2 * pad)}


def draw_scalebar(ax, W, H, calib, opts, lang="de", width_in=6.4):
    g = scalebar_geom(W, H, calib, opts, lang)
    fg, bg = ("black", "white") if opts["color"] == "black" else ("white", "black")
    if opts["box"]:
        x, y, w, h = g["box"]
        ax.add_patch(Rectangle((x, y), w, h, facecolor=bg, edgecolor="none", alpha=0.65))
    x, y, w, h = g["bar"]
    ax.add_patch(Rectangle((x, y), w, h, facecolor=fg, edgecolor="none" if opts["box"] else bg,
                           lw=0 if opts["box"] else 0.6))
    if opts["label"]:
        pt = g["font_px"] * width_in * 72 / W          # Bildpixel -> Punkt
        kw = {} if opts["box"] else {"path_effects": [pe.withStroke(linewidth=max(1.5, pt * 0.2), foreground=bg)]}
        ax.text(*g["text_xy"], g["text"], color=fg, ha="center", va="center", fontsize=pt, fontweight="bold", **kw)
    return g


def fig_image(rgb: np.ndarray, calib, lang="de", overlay: np.ndarray | None = None, rois=None, scalebar=True,
              labels=None, width_in=6.4):
    """Bild als Abbildung; scalebar: False, True oder Einstellungen (siehe scalebar_opts)."""
    H, W = rgb.shape[:2]
    h_in = width_in * H / W
    fig = plt.figure(figsize=(width_in, h_in))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.imshow(rgb, interpolation="nearest", extent=(0, W, H, 0))
    if overlay is not None:
        ax.imshow(overlay, interpolation="nearest", extent=(0, W, H, 0))
    for r in rois or []:
        _draw_roi(ax, r)
    if labels:
        fs = max(5, min(9, 900 / max(W, H) * 6))
        for i, (x, y) in enumerate(labels, 1):
            ax.text(x, y, str(i), color="#ffeb3b", fontsize=fs, ha="center", va="center", fontweight="bold")
    opts = scalebar_opts(scalebar)
    if opts and calib.calibrated:
        draw_scalebar(ax, W, H, calib, opts, lang, width_in)
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)
    ax.axis("off")
    return fig


def _draw_roi(ax, r, color="#ffeb3b"):
    t = r.get("type")
    kw = dict(fill=False, ec=color, lw=1.2)
    if t == "rect":
        ax.add_patch(Rectangle((r["x"], r["y"]), r["w"], r["h"], **kw))
    elif t == "oval":
        ax.add_patch(Ellipse((r["x"] + r["w"] / 2, r["y"] + r["h"] / 2), abs(r["w"]), abs(r["h"]), **kw))
    elif t in ("polygon", "freehand", "traced"):
        ax.add_patch(Polygon(np.asarray(r["pts"]), closed=True, **kw))
    elif t == "line":
        ax.plot([r["x1"], r["x2"]], [r["y1"], r["y2"]], color=color, lw=1.4)
    elif t == "point":
        p = np.asarray(r.get("pts") or [])
        if len(p):
            ax.plot(p[:, 0], p[:, 1], "+", color=color, ms=8, mew=1.6)
    name = r.get("name")
    if name and t != "point":
        x = r.get("x", r.get("x1", (r.get("pts") or [[0, 0]])[0][0]))
        y = r.get("y", r.get("y1", (r.get("pts") or [[0, 0]])[0][1]))
        ax.text(x, y, " " + name, color=color, fontsize=7, va="bottom",
                path_effects=[pe.withStroke(linewidth=2, foreground="black")])


def _style(ax):
    ax.grid(True, alpha=0.3)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def fig_hist(values: np.ndarray, lang="de", thr: dict | None = None, unit_label=None):
    fig, ax = plt.subplots(figsize=(6.4, 3.0))
    v = values[np.isfinite(values)].ravel()
    ax.hist(v, bins=256, color="#5f6368", histtype="stepfilled", alpha=0.85)
    if thr and thr.get("lo") is not None:
        ax.axvspan(thr["lo"], thr["hi"], color="#d93025", alpha=0.15,
                   label=("Schwellenbereich" if lang == "de" else "Threshold range"))
        ax.axvline(thr["value"] if thr.get("value") is not None else thr["lo"], color="#d93025", lw=1.2)
        ax.legend(frameon=False, fontsize=8)
    ax.set_xlabel(unit_label or ("Grauwert" if lang == "de" else "Grey value"))
    ax.set_ylabel("Pixel" if lang == "de" else "Pixels")
    ax.set_yscale("log")
    _style(ax)
    fig.tight_layout()
    return fig


def _weights(rows):
    return np.array([float(r.get("Weight", 1.0) or 1.0) for r in rows], dtype=float)


def fig_sizes(rows: list[dict], unit: str, lang="de", key="ECD"):
    """Anzahlverteilung (Q0). Mit Randkorrektur zaehlt jedes Partikel mit seinem Gewicht (Miles-Lantuéjoul)."""
    from .measure import wquantile
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    v = np.array([r[key] for r in rows], dtype=float)
    w = _weights(rows)
    corr = bool(v.size) and not np.allclose(w, 1.0)
    if v.size:
        bins = max(5, min(40, int(math.sqrt(v.size)) * 2))
        ax.hist(v, bins=bins, weights=w, color="#1a73e8", alpha=0.85, edgecolor="white")
        d50 = wquantile(v, w, (0.5,))[0]
        ax.axvline(d50, color="#d93025", lw=1.4, ls="--", label=f"D50 (Q0) = {_fmt(round(d50, 3), lang)} {unit}")
        ax.legend(frameon=False, fontsize=8)
    lab = {"ECD": ("Äquivalentdurchmesser", "Equivalent circle diameter"), "Feret": ("Feret-Durchmesser", "Feret diameter")}
    ax.set_xlabel(f"{lab.get(key, (key, key))[0 if lang == 'de' else 1]} [{unit}]")
    ylab = ("Anzahl" if lang == "de" else "Count")
    if corr:
        ylab += " (randkorrigiert)" if lang == "de" else " (edge-corrected)"
    ax.set_ylabel(ylab)
    _style(ax)
    fig.tight_layout()
    return fig


def overlay_bins(a: np.ndarray, b: np.ndarray, n: int | None = None) -> np.ndarray:
    """Gemeinsame Klassen für zwei Verteilungen (Bereich beider, Anzahl nach der kleineren Stichprobe)."""
    v = np.concatenate([a, b])
    lo, hi = float(np.min(v)), float(np.max(v))
    if hi <= lo:
        hi = lo + 1.0
    n = n or max(6, min(40, int(math.sqrt(min(a.size, b.size))) * 2))
    return np.linspace(lo, hi, n + 1)


def fig_sizes_overlay(ecd, other, unit: str, lang="de", names=("Partikel", "Datensatz"), weights=None):
    """I-04: Grössenverteilung der Partikel mit einer Vergleichsverteilung aus einem Datensatz (relative Häufigkeit,
    gemeinsame Klassen, beide anzahlgewichtet Q0; Partikel mit den Gewichten der Randkorrektur) und den D50 beider."""
    from .measure import wquantile
    a = np.asarray(ecd, dtype=float)
    b = np.asarray(other, dtype=float)
    wa = np.ones_like(a) if weights is None else np.asarray(weights, dtype=float)
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    if a.size and b.size:
        edges = overlay_bins(a, b)
        for v, wv, col, name, kw in ((a, wa, "#1a73e8", names[0], {"alpha": 0.55, "edgecolor": "white"}),
                                     (b, np.ones_like(b), "#e37400", names[1], {"histtype": "step", "lw": 1.8})):
            ax.hist(v, bins=edges, weights=wv * 100.0 / wv.sum(), color=col, label=f"{name} (n = {v.size})", **kw)
            d50 = wquantile(v, wv, (0.5,))[0]
            ax.axvline(d50, color=col, lw=1.3, ls="--", label=f"D50 (Q0) = {_fmt(round(d50, 3), lang)} {unit}")
        ax.legend(frameon=False, fontsize=8)
    ax.set_xlabel(("Äquivalentdurchmesser / Länge" if lang == "de" else "Equivalent diameter / length") + f" [{unit}]")
    ax.set_ylabel(("Relative Häufigkeit (Anzahl)" if lang == "de" else "Relative frequency (number)") + " [%]")
    _style(ax)
    fig.tight_layout()
    return fig


def fig_shape(rows: list[dict], unit: str, lang="de"):
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    x = np.array([r["ECD"] for r in rows], dtype=float)
    y = np.array([r["Circ."] for r in rows], dtype=float)
    ax.scatter(x, y, s=14, color="#9334e6", alpha=0.75, edgecolors="none")
    ax.set_ylim(0, 1.05)
    ax.set_xlabel(("Äquivalentdurchmesser" if lang == "de" else "Equivalent circle diameter") + f" [{unit}]")
    ax.set_ylabel("Zirkularität" if lang == "de" else "Circularity")
    _style(ax)
    fig.tight_layout()
    return fig


def fig_profile(dist: np.ndarray, vals: np.ndarray, unit: str, lang="de"):
    fig, ax = plt.subplots(figsize=(6.4, 3.0))
    ax.plot(dist, vals, color="#1a73e8", lw=1.3)
    ax.set_xlabel(("Abstand" if lang == "de" else "Distance") + f" [{unit}]")
    ax.set_ylabel("Grauwert" if lang == "de" else "Grey value")
    _style(ax)
    fig.tight_layout()
    return fig


def fig_compare(series: list, unit: str, lang="de"):
    """Summenverteilung Q0 des Aequivalentdurchmessers je Bild; series: (Name, Werte) oder (Name, Werte, Gewichte)."""
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    colors = ["#1a73e8", "#d93025", "#188038", "#9334e6", "#e37400", "#007b83"]
    for i, s in enumerate(series):
        name, v = s[0], np.asarray(s[1], dtype=float)
        w = np.ones_like(v) if len(s) < 3 or s[2] is None else np.asarray(s[2], dtype=float)
        o = np.argsort(v, kind="stable")
        v, w = v[o], w[o]
        if v.size:
            ax.step(v, np.cumsum(w) / w.sum() * 100, where="post", color=colors[i % len(colors)],
                    lw=1.5, label=f"{name} (n = {v.size})")
    ax.set_xlabel(("Äquivalentdurchmesser" if lang == "de" else "Equivalent circle diameter") + f" [{unit}]")
    ax.set_ylabel(("Summenhäufigkeit Q0" if lang == "de" else "Cumulative frequency Q0") + " [%]")
    ax.set_ylim(0, 102)
    ax.legend(frameon=False, fontsize=8)
    _style(ax)
    fig.tight_layout()
    return fig

