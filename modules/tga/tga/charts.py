"""Abbildungen (matplotlib) für Export und Bericht."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

COLORS = ["#b45309", "#007b83", "#4338ca", "#15803d", "#a21caf", "#c2410c", "#0369a1", "#be123c"]
INK, MUTED, GRIDC = "#1f1d24", "#625d6b", "#e4e1ea"


def _part(arts, pid):
    """Mark artists as one part of the figure (labstyle: what the report can switch off with its caption and sources)."""
    if pid:
        for a in arts if isinstance(arts, (list, tuple)) else [arts]:
            a._labpart = pid
    return arts


def _fmt(v, lang, nd=0):
    s = f"{v:.{nd}f}"
    return s.replace(".", ",") if lang == "de" else s


def _style(ax, xlab=None, ylab=None):
    if xlab:
        ax.set_xlabel(xlab, color=INK)
    if ylab:
        ax.set_ylabel(ylab, color=INK)
    ax.grid(True, color=GRIDC, lw=0.6)
    ax.set_axisbelow(True)
    for s in ("top",):
        ax.spines[s].set_visible(False)
    ax.tick_params(colors=MUTED, labelsize=8.5)


def xlabel(x, lang):
    return ("Temperatur [°C]" if lang == "de" else "Temperature [°C]") if x == "T" else ("Zeit [min]" if lang == "de" else "Time [min]")


def ref_tag(h: dict, lang: str = "de") -> str:
    """Kurze Herkunft einer Referenz für Legenden: „Modell, Schindler u. a. 2017“ bzw. „<Bibliothek>, Quelle“."""
    try:
        import labcite
        src = labcite.short(h.get("source") or {}, lang) if labcite.is_record(h.get("source")) else ""
    except ImportError:  # pragma: no cover
        src = ""
    if h.get("lib") == "modell" or h.get("modelled") and h.get("lib") == "modell":
        base = "Modell" if lang == "de" else "model"
    else:
        base = h.get("lib_name") or h.get("lib") or ""
    return base + (f", {src}" if src else "")


def fig_tg_dtg(a, lang="de", x="T", show_steps=True):
    r = a.run
    xs = r.T if x == "T" and r.has_T else r.time()
    xk = "T" if x == "T" and r.has_T else "t"
    m = r.pct()
    d = a.st.get("dtg") or {}
    dtg = -(d.get("dT") if xk == "T" else d.get("dt"))
    fig, ax = plt.subplots(figsize=(6.6, 3.8))
    ax.plot(xs, m, color=COLORS[0], lw=1.2, label="TG")
    _style(ax, xlabel(xk, lang), "Masse [%]" if lang == "de" else "Mass [%]")
    ax2 = ax.twinx()
    ok = np.isfinite(dtg)
    _part(ax2.plot(xs[ok], dtg[ok], color=COLORS[1], lw=0.9, label="DTG"), "dtg")
    ax2.set_ylabel(("DTG, −dm/dT [%/°C]" if xk == "T" else "DTG, −dm/dt [%/min]") if lang == "de" else
                   ("DTG, −dm/dT [%/°C]" if xk == "T" else "DTG, −dm/dt [%/min]"), color=COLORS[1])
    ax2.tick_params(colors=MUTED, labelsize=8.5)
    ax2.spines["top"].set_visible(False)
    if show_steps:
        for s in a.steps:
            on = s.get(f"{xk}_onset") if s["x"] == xk else None
            if on is not None:
                _part(ax.axvline(on, color=MUTED, lw=0.6, ls="--"), "stufen")
            xm = (s[f"{'T' if xk == 'T' else 't'}_start"] + s[f"{'T' if xk == 'T' else 't'}_end"]) / 2 if s.get("T_start") is not None or xk == "t" else None
            if xm is not None:
                _part(ax.annotate(f"−{_fmt(s['loss'], lang, 1)} %", (xm, (s["m_start"] + s["m_end"]) / 2), xytext=(6, 0),
                                  textcoords="offset points", fontsize=7.5, color=INK, va="center"), "stufen")
        res = a.st.get("residue") or {}
        if res.get("end") is not None:
            _part(ax.annotate(("Rückstand " if lang == "de" else "Residue ") + f"{_fmt(res['end'], lang, 1)} %", (xs[-1], res["end"]),
                              xytext=(-4, 8), textcoords="offset points", ha="right", fontsize=7.5, color=INK), "rueckstand")
    # eingeblendete Referenzen (eigene oder aus Bibliotheken), nur über der Temperatur
    ovs = [o for o in (a.state.get("overlays") or []) if o.get("tg") is not None] if xk == "T" else []
    if ovs:
        from .library import GRID
        for i, o in enumerate(ovs):
            c = COLORS[(i + 2) % len(COLORS)]
            tg = np.asarray(o["tg"], float)
            ok_ = np.isfinite(tg)
            _part(ax.plot(GRID[ok_], tg[ok_], color=c, lw=1.0, ls="--", label=f"{o.get('name', '')} ({ref_tag(o, lang)})"), f"referenz{i + 1}")
            if o.get("dtg") is not None:
                dd = np.asarray(o["dtg"], float)
                ok_ = np.isfinite(dd)
                _part(ax2.plot(GRID[ok_], dd[ok_], color=c, lw=0.8, ls=":"), f"referenz{i + 1}")
        ax.set_xlim(float(np.nanmin(xs)), float(np.nanmax(xs)))
    lo, hi = ax.get_ylim()
    ax.set_ylim(min(lo, -2), max(hi, 102))
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, fontsize=7.5, frameon=False, loc="lower left")
    fig.tight_layout()
    return fig


def fig_overlay(series, lang="de", x="T"):
    """series: [{"name", "x", "m", "dtg"}]; oben TG, unten DTG."""
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(6.6, 5.0), sharex=True, gridspec_kw={"height_ratios": [3, 2]})
    for i, s in enumerate(series):
        c = COLORS[i % len(COLORS)]
        _part(a1.plot(s["x"], s["m"], color=c, lw=1.1, label=s["name"]), s.get("part"))
        d = np.asarray(s["dtg"], float)
        ok = np.isfinite(d)
        _part(a2.plot(np.asarray(s["x"])[ok], d[ok], color=c, lw=0.9), s.get("part"))
    _style(a1, None, "Masse [%]" if lang == "de" else "Mass [%]")
    _style(a2, xlabel(x, lang), "DTG [%/°C]" if x == "T" else "DTG [%/min]")
    a1.legend(fontsize=7.5, frameon=False, loc="lower left")
    fig.tight_layout()
    return fig


def fig_search(grid, q, hits, lang="de", qname=""):
    hits = [h for h in hits if h.get("y") is not None][:3]
    fig, ax = plt.subplots(figsize=(6.6, 1.4 + 0.95 * (1 + len(hits))))
    v = np.isfinite(q)
    top = float(np.nanmax(q)) or 1.0
    ax.plot(grid[v], q[v] / top, color=INK, lw=1.1)
    ax.text(0.01, 0.98, qname or ("Probe" if lang == "de" else "Sample"), transform=ax.transAxes, fontsize=8, va="top", color=INK)
    off = 0.0
    for i, h in enumerate(hits):
        off -= 1.15
        y = np.asarray(h["y"], float)
        yt = float(np.nanmax(y)) or 1.0
        c = COLORS[(i + 1) % len(COLORS)]
        _part(ax.plot(grid, y / yt + off, color=c, lw=1.0), f"treffer{i + 1}")
        sh = f", {h['shift']:+d} K" if h.get("shift") else ""
        _part(ax.text(grid[0], off + 0.95, f"{i + 1}. {h['name']} ({_fmt(h['hqi'], lang, 1)}{sh}) · {ref_tag(h, lang)}",
                      fontsize=7.3, color=c, va="top"), f"treffer{i + 1}")
    _style(ax, xlabel("T", lang), "DTG, normiert" if lang == "de" else "DTG, normalised")
    ax.set_yticks([])
    fig.tight_layout()
    return fig


def fig_mixture(grid, q, combo, lang="de", qname=""):
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(6.6, 4.6), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    v = np.isfinite(q)
    a1.plot(grid[v], q[v], color=INK, lw=1.1, label=qname or ("Probe" if lang == "de" else "Sample"))
    fit = np.asarray(combo["fit"], float)
    a1.plot(grid[v], fit[v], color=COLORS[0], lw=1.0, ls="--",
            label=("Anpassung" if lang == "de" else "Fit") + f" ({_fmt(combo['hqi'], lang, 1)})")
    for i, c in enumerate(combo["components"]):
        y = np.asarray(c["y"], float)
        _part(a1.fill_between(grid, 0, y, color=COLORS[(i + 1) % len(COLORS)], alpha=0.18, lw=0), f"komponente{i + 1}")
        _part(a1.plot(grid, y, color=COLORS[(i + 1) % len(COLORS)], lw=0.8,
                      label=f"{c['name']} ({_fmt(100 * c['frac'], lang)} %) · {ref_tag(c, lang)}"), f"komponente{i + 1}")
    a1.legend(fontsize=7, frameon=False, loc="upper left")
    _style(a1, None, "DTG [%/°C]")
    r = np.asarray(combo["residual"], float)
    m = np.isfinite(r)
    a2.plot(grid[m], r[m], color=MUTED, lw=0.8)
    a2.axhline(0, color=GRIDC, lw=0.8)
    _style(a2, xlabel("T", lang), "Rest" if lang == "de" else "Residual")
    fig.tight_layout()
    return fig


def fig_composition(comp, lang="de"):
    rows = [r for r in comp["rows"] if r.get("pct") is not None and r["pct"] > 0]
    fig, ax = plt.subplots(figsize=(6.6, 1.6))
    left = 0.0
    for i, r in enumerate(rows):
        ax.barh(0, r["pct"], left=left, color=COLORS[i % len(COLORS)], height=0.6)
        if r["pct"] > 4:
            ax.text(left + r["pct"] / 2, 0, f"{_fmt(r['pct'], lang, 1)} %", ha="center", va="center", fontsize=7.5, color="white")
        left += r["pct"]
    ax.set_xlim(0, max(100, left))
    ax.set_yticks([])
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.set_xlabel("Anteil [%]" if lang == "de" else "Fraction [%]", color=INK)
    from matplotlib.patches import Patch
    ax.legend([Patch(color=COLORS[i % len(COLORS)]) for i in range(len(rows))], [r["name"] for r in rows],
              fontsize=7, frameon=False, ncol=2, loc="upper center", bbox_to_anchor=(0.5, -0.55))
    fig.tight_layout()
    return fig


def fig_deconv(dc, lang="de", qname=""):
    x = np.asarray(dc["x"], float)
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(6.6, 4.4), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    a1.plot(x, dc["y"], color=INK, lw=1.1, label=qname or "DTG")
    a1.plot(x, dc["fit"], color=COLORS[0], lw=1.0, ls="--", label=("Summe" if lang == "de" else "Sum") + f" (R² {_fmt(dc['r2'], lang, 4)})")
    for i, p in enumerate(dc["peaks"]):
        c = COLORS[(i + 1) % len(COLORS)]
        a1.fill_between(x, 0, p["y"], color=c, alpha=0.18, lw=0)
        a1.plot(x, p["y"], color=c, lw=0.8, label=f"{p['name']}: {_fmt(p['x0'], lang)} °C, {_fmt(p['area'], lang, 1)} %")
    a1.legend(fontsize=7, frameon=False, loc="upper left")
    _style(a1, None, "−dm/dT [%/°C]")
    a2.plot(x, dc["residual"], color=MUTED, lw=0.8)
    a2.axhline(0, color=GRIDC, lw=0.8)
    _style(a2, xlabel("T", lang), "Rest" if lang == "de" else "Residual")
    fig.tight_layout()
    return fig


def fig_dsc(run, dsc, lang="de"):
    """Wärmestrom über T mit den ausgewerteten Peakbereichen (Basislinie, Fläche) und Glasübergängen (TGA-03)."""
    T, hf = run.T, run.extra["hf"]
    fig, ax = plt.subplots(figsize=(6.6, 3.4))
    ax.plot(T, hf, color=INK, lw=1.0)
    for i, p in enumerate(p for p in dsc.get("peaks") or [] if "error" not in p):
        k = np.nonzero((T >= p["lo"]) & (T <= p["hi"]))[0]
        if len(k) < 2:
            continue
        x, y = T[k], hf[k]
        base = np.interp(x, [x[0], x[-1]], [y[: max(3, len(x) // 40)].mean(), y[-max(3, len(x) // 40):].mean()])
        c = COLORS[i % len(COLORS)]
        _part(ax.fill_between(x, base, y, color=c, alpha=0.25, lw=0), "peaks")
        _part(ax.plot(x, base, color=c, lw=0.8, ls="--"), "peaks")
        lab = (f"{_fmt(p['dH'], lang, 1)} J/g" if p.get("dH") is not None else f"{_fmt(p['area'], lang, 1)} {p['area_unit']}")
        _part(ax.annotate(f"{_fmt(p['T_peak'], lang, 1)} °C\n{lab}", (p["T_peak"], hf[k][np.argmin(np.abs(x - p['T_peak']))]),
                          fontsize=7, color=c, ha="center", va="bottom" if p["kind"] == ("exo" if dsc["sign"] == "exo_up" else "endo") else "top"), "peaks")
    for g in (g for g in dsc.get("tg") or [] if "error" not in g):
        _part(ax.axvline(g["Tg_mid"], color=MUTED, lw=0.8, ls=":"), "glas")
        _part(ax.annotate(f"$T_g$ {_fmt(g['Tg_mid'], lang, 1)} °C", (g["Tg_mid"], ax.get_ylim()[1]), fontsize=7, color=MUTED,
                          ha="left", va="top"), "glas")
    unit = {"mW": "mW", "W/g": "W/g", "uV": "µV"}[dsc["unit"]]
    ax.annotate("exo ↑" if dsc["sign"] == "exo_up" else "endo ↑", (0.01, 0.97), xycoords="axes fraction", fontsize=7,
                color=MUTED, va="top")
    _style(ax, xlabel("T", lang), ("Wärmestrom" if lang == "de" else "Heat flow") + f" [{unit}]")
    fig.tight_layout()
    return fig


METHOD_LABEL = {"friedman": "Friedman", "ofw": "Ozawa-Flynn-Wall", "kas": "Kissinger-Akahira-Sunose", "starink": "Starink",
                "vyazovkin": "Vyazovkin"}


def fig_kinetics(res, lang="de", methods=("friedman", "ofw", "kas", "vyazovkin")):
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(6.8, 3.2))
    for i, c in enumerate(res["curves"]):
        a1.plot(c["T"], c["a"], color=COLORS[i % len(COLORS)], lw=1.0, label=f"{_fmt(c['beta'], lang, 0 if c['beta'] == int(c['beta']) else 1)} K/min")
    _style(a1, xlabel("T", lang), "Umsatz α" if lang == "de" else "Conversion α")
    a1.legend(fontsize=7, frameon=False)
    for i, m in enumerate(methods):
        rows = res["iso"]["methods"].get(m) or []
        if not rows:
            continue
        al = [r["alpha"] for r in rows]
        E = [r["E"] for r in rows]
        ci = [r["ci"] or 0 for r in rows]
        a2.errorbar(al, E, yerr=ci if any(ci) else None, color=COLORS[(i + 1) % len(COLORS)], lw=1.0, ms=3, marker="o",
                    capsize=2, label=METHOD_LABEL[m])
    _style(a2, "α", "Eₐ [kJ/mol]")
    a2.legend(fontsize=7, frameon=False)
    fig.tight_layout()
    return fig
