"""Abbildungen (matplotlib) für Export und Bericht. Wellenzahlachse wie üblich fallend (links hohe Wellenzahlen)."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from .readers import ylabel  # noqa: E402

COLORS = ["#007b83", "#c2410c", "#4338ca", "#15803d", "#a21caf", "#b45309", "#0369a1", "#be123c"]
INK, MUTED, GRIDC = "#1f1d24", "#625d6b", "#e4e1ea"


def _style(ax, lang, yunit=None, ylab=None):
    ax.set_xlabel("Wellenzahl [cm⁻¹]" if lang == "de" else "Wavenumber [cm⁻¹]", color=INK)
    if ylab or yunit:
        ax.set_ylabel(ylab or ylabel(yunit, lang), color=INK)
    ax.grid(True, color=GRIDC, lw=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(colors=MUTED, labelsize=8.5)


def _fmt(v, lang, nd=0):
    s = f"{v:.{nd}f}"
    return s.replace(".", ",") if lang == "de" else s


def fig_spectra(series, yunit, lang="de", peaks=None, regions=None, stacked=False, xlim=None, label_peaks=25):
    """series: [{"name", "x", "y"}]; peaks: Peaks der ersten Kurve; regions: [(von, bis, Text)] schattiert."""
    fig, ax = plt.subplots(figsize=(6.6, 3.6 if len(series) < 4 or not stacked else 1.2 + 0.7 * len(series)))
    off = 0.0
    step = 0.0
    if stacked and len(series) > 1:
        step = 1.1 * max(float(np.ptp(s["y"])) for s in series)
    for i, s in enumerate(series):
        col = COLORS[i % len(COLORS)]
        ax.plot(s["x"], np.asarray(s["y"]) + off, color=col, lw=1.0, label=s["name"])
        if stacked:
            off -= step
    for lo, hi, txt in regions or []:
        ax.axvspan(min(lo, hi), max(lo, hi), color="#007b83", alpha=0.08, lw=0)
        if txt:
            ax.text((lo + hi) / 2, 1.0, txt, transform=ax.get_xaxis_transform(), ha="center", va="bottom", fontsize=7,
                    color=MUTED)
    if peaks and series:
        valley = yunit in ("T", "R")
        top = sorted(peaks, key=lambda p: -p.get("prom", 0))
        yr = float(np.ptp(series[0]["y"])) or 1.0
        lo_x, hi_x = (min(xlim), max(xlim)) if xlim else (float(np.min(series[0]["x"])), float(np.max(series[0]["x"])))
        min_dx = 0.02 * (hi_x - lo_x)          # Beschriftungen dürfen sich nicht überlappen
        placed = []
        for p in top:
            if len(placed) >= label_peaks or not (lo_x <= p["x"] <= hi_x):
                continue
            if any(abs(p["x"] - q) < min_dx for q in placed):
                continue
            placed.append(p["x"])
            y0 = p["y"]
            ax.annotate(_fmt(p["x"], lang), (p["x"], y0), xytext=(0, -9 if valley else 9), textcoords="offset points",
                        rotation=90, ha="center", va="top" if valley else "bottom", fontsize=6.5, color=INK)
        lo, hi = ax.get_ylim()
        ax.set_ylim(lo - (0.12 * yr if valley else 0), hi + (0 if valley else 0.12 * yr))
    if xlim:
        ax.set_xlim(max(xlim), min(xlim))
    else:
        xs = np.concatenate([np.asarray(s["x"]) for s in series])
        ax.set_xlim(float(xs.max()), float(xs.min()))
    _style(ax, lang, yunit)
    if stacked:
        ax.set_yticks([])
    if len(series) > 1:
        ax.legend(fontsize=7.5, frameon=False, loc="best")
    fig.tight_layout()
    return fig


def ref_tag(h: dict, lang: str = "de") -> str:
    """Kurze Herkunft einer Referenz für Beschriftungen: „Open Specy/RRUFF“, „Modell“, Name der eigenen Bibliothek."""
    lib = h.get("lib") or ""
    if str(lib).startswith("openspecy"):
        src = (h.get("source") or "").split(":", 1)[0].strip()
        return "Open Specy" + (f"/{src}" if src else "")
    if lib == "modell":
        return "Modell" if lang == "de" else "model"
    return h.get("lib_name") or lib


def fig_search(x, q, hits, lang="de", qname=""):
    """Suchspektrum oben, darunter die besten Treffer (je auf gleiche Höhe skaliert)."""
    hits = [h for h in hits if h.get("y") is not None][:3]
    n = 1 + len(hits)
    fig, ax = plt.subplots(figsize=(6.6, 1.3 + 0.95 * n))
    v = np.isfinite(q)
    ax.plot(x[v], q[v], color=INK, lw=1.0)
    ax.text(0.01, 0.98, qname or ("Probe" if lang == "de" else "Sample"), transform=ax.transAxes, fontsize=8, va="top", color=INK)
    off = 0.0
    for i, h in enumerate(hits):
        off -= 1.15
        y = np.asarray(h["y"], float)
        m = np.isfinite(y)
        ax.plot(x[m], y[m] + off, color=COLORS[(i + 1) % len(COLORS)], lw=1.0)
        ax.text(float(x[v].max()), off + 0.92, f"{i + 1}. {h['name']} (HQI {_fmt(h['hqi'], lang, 1)}) · {ref_tag(h, lang)}",
                fontsize=7.5, color=COLORS[(i + 1) % len(COLORS)], ha="left", va="top")
    ax.set_xlim(float(x[v].max()), float(x[v].min()))
    _style(ax, lang, ylab="Absorbanz, normiert" if lang == "de" else "Absorbance, normalised")
    ax.set_yticks([])
    fig.tight_layout()
    return fig


def fig_mixture(x, q, combo, lang="de", qname=""):
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(6.6, 4.6), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    v = np.isfinite(q)
    a1.plot(x[v], q[v], color=INK, lw=1.1, label=qname or ("Probe" if lang == "de" else "Sample"))
    fit = np.asarray(combo["fit"], float)
    a1.plot(x[v], fit[v], color=COLORS[1], lw=1.0, ls="--",
            label=("Anpassung" if lang == "de" else "Fit") + f" (HQI {_fmt(combo['hqi'], lang, 1)})")
    for i, c in enumerate(combo["components"]):
        y = np.asarray(c["y"], float)
        m = np.isfinite(y)
        a1.fill_between(x[m], 0, y[m], color=COLORS[(i + 2) % len(COLORS)], alpha=0.18, lw=0)
        a1.plot(x[m], y[m], color=COLORS[(i + 2) % len(COLORS)], lw=0.8,
                label=f"{c['name']} ({_fmt(100 * c['frac'], lang)} %) · {ref_tag(c, lang)}")
    a1.legend(fontsize=7, frameon=False, loc="upper left")
    _style(a1, lang, ylab="Absorbanz, normiert" if lang == "de" else "Absorbance, normalised")
    a1.set_xlabel("")
    r = np.asarray(combo["residual"], float)
    m = np.isfinite(r)
    a2.plot(x[m], r[m], color=MUTED, lw=0.8)
    a2.axhline(0, color=GRIDC, lw=0.8)
    _style(a2, lang, ylab="Rest" if lang == "de" else "Residual")
    a2.set_xlim(float(x[v].max()), float(x[v].min()))
    fig.tight_layout()
    return fig
