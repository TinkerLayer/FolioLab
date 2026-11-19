"""Abbildungen für den Bericht (matplotlib, Agg). Jede Funktion nimmt das Ergebnis eines Werkzeugs (tools.py)."""
from __future__ import annotations

import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import Polygon  # noqa: E402

COLORS = ["#007b83", "#c2410c", "#4338ca", "#15803d", "#a21caf", "#b45309", "#0369a1", "#be123c"]
INK, MUTED, GRIDC = "#1f1d24", "#625d6b", "#e4e1ea"
CLASS_COLORS = {"metall": "#0369a1", "keramik": "#b45309", "polymer": "#15803d", "elastomer": "#65a30d",
                "verbund": "#a21caf", "glas": "#0891b2", "faser": "#be123c", "naturstoff": "#854d0e",
                "schaum": "#64748b", "halbleiter": "#4338ca", "element": "#475569"}


def _de(lang):
    return lang == "de"


def _fmt(v, lang, nd=2):
    if v is None:
        return "–"
    s = f"{v:.{nd}f}"
    return s.replace(".", ",") if lang == "de" else s


def _ax(ax, xl=None, yl=None):
    if xl:
        ax.set_xlabel(xl, color=INK)
    if yl:
        ax.set_ylabel(yl, color=INK)
    ax.grid(True, color=GRIDC, lw=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(colors=INK, labelsize=8)


def _unit(u):
    return u.replace("^3", "³").replace("^2", "²").replace("^0.5", "^½") if u else u


def _lab(axis):
    u = _unit(axis.get("unit") or "")
    return f"{axis['label']} [{u}]" if u and u not in ("1", "") else axis["label"]


def _tag(fig, text):
    fig.text(0.995, 0.005, text, ha="right", va="bottom", fontsize=6.5, color=MUTED, style="italic")


# ----------------------------------------------------------------------------- Auswahl
def fig_ashby(res: dict, lang: str = "de", label_top: int = 12, show_mp: bool = True):
    fig, ax = plt.subplots(figsize=(6.6, 4.8))
    pts = res["points"]
    ranked = {r["id"]: r["rank"] for r in (res.get("rank") or {}).get("ranked", [])}
    seen = set()
    for p in pts:
        if p["x"] is None or p["y"] is None or p["x"] <= 0 or p["y"] <= 0:
            continue
        if p["mp"] and not show_mp:
            continue
        col = CLASS_COLORS.get(p["klasse"], MUTED)
        lab = None
        key = ("mp" if p["mp"] else p["klasse"])
        if key not in seen:
            seen.add(key)
            lab = (("berechnet (DFT)" if _de(lang) else "computed (DFT)") if p["mp"]
                   else res["classes"].get(p["klasse"], p["klasse"]))
        xe = [[p["x"] - p["xmin"]], [p["xmax"] - p["x"]]] if p.get("xmin") and p.get("xmax") else None
        ye = [[p["y"] - p["ymin"]], [p["ymax"] - p["y"]]] if p.get("ymin") and p.get("ymax") else None
        if xe or ye:
            ax.errorbar(p["x"], p["y"], xerr=xe, yerr=ye, fmt="none", ecolor=col, alpha=0.35, lw=2.2)
        if p["mp"]:
            ax.scatter([p["x"]], [p["y"]], marker="^", facecolors="none", edgecolors=col if col != MUTED else "#334155",
                       s=22, lw=0.9, label=lab, zorder=3)
        else:
            ax.scatter([p["x"]], [p["y"]], s=18, color=col, edgecolors="white", lw=0.4, label=lab, zorder=3)
        r = ranked.get(p["id"])
        if r and r <= label_top:
            ax.annotate(f"{r}", (p["x"], p["y"]), xytext=(3, 3), textcoords="offset points", fontsize=6.5, color=INK)
    own = res.get("own") or []
    for k, p in enumerate(own):
        ax.scatter([p["x"]], [p["y"]], marker="D", s=30, facecolors="white", edgecolors=INK, lw=1.1, zorder=4,
                   label=(("eigene Werte" if _de(lang) else "own values") if k == 0 else None))
        r = ranked.get(p["id"])
        ax.annotate(p["name"] + (f" ({r})" if r else ""), (p["x"], p["y"]), xytext=(4, -9),
                    textcoords="offset points", fontsize=6.5, color=INK)
    ax.set_xscale("log")
    ax.set_yscale("log")
    sl = res.get("slope")
    rk = (res.get("rank") or {}).get("ranked") or []
    if sl is not None and rk:
        best = next((p for p in list(pts) + list(own) if p["id"] == rk[0]["id"]), None)
        if best:
            x0, x1 = ax.get_xlim()
            xs = np.logspace(math.log10(x0), math.log10(x1), 20)
            for k, f in enumerate((1.0, 0.5, 0.25)):
                ys = best["y"] * f * (xs / best["x"]) ** sl
                ax.plot(xs, ys, ls="--", lw=0.8, color=INK if k == 0 else MUTED, alpha=0.8 if k == 0 else 0.5)
            ax.set_xlim(x0, x1)
            ax.text(0.01, 0.01, ("Linien gleicher Kennzahl, Steigung " if _de(lang) else "Lines of equal index, slope ")
                    + _fmt(sl, lang, 2), transform=ax.transAxes, fontsize=7, color=MUTED)
    _ax(ax, _lab(res["x"]), _lab(res["y"]))
    ax.grid(True, which="minor", color=GRIDC, lw=0.3)
    ax.legend(fontsize=7, frameon=False, loc="upper left", ncol=2)
    fig.tight_layout()
    return fig


def fig_rank(rank: dict, label: str, lang: str = "de", top: int = 15):
    rows = rank["ranked"][:top]
    fig, ax = plt.subplots(figsize=(6.2, 0.28 * max(len(rows), 3) + 0.9))
    y = np.arange(len(rows))[::-1]
    ax.barh(y, [r["M"] for r in rows], color=[CLASS_COLORS.get(r["klasse"], MUTED) for r in rows],
            hatch=None, alpha=0.9)
    for yi, r in zip(y, rows):
        if r.get("mp"):
            ax.text(r["M"], yi, " DFT", va="center", fontsize=6.5, color=MUTED)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{r['rank']}. {r['name']}" for r in rows], fontsize=7)
    _ax(ax, label)
    ax.grid(axis="y", visible=False)
    fig.tight_layout()
    return fig


# ----------------------------------------------------------------------------- Kristall
def fig_lines(info: dict, lang: str = "de", label_min: float = 4.0):
    fig, ax = plt.subplots(figsize=(6.6, 3.2))
    pr = info.get("profile")
    if pr:
        y = np.asarray(pr["y"], float)
        ax.plot(pr["x"], 100 * y / (y.max() or 1), color=COLORS[0], lw=0.9)
    for L in info["lines"]:
        ax.vlines(L["tth"], 0, L["Irel"], color=COLORS[1], lw=1.0)
        if L["Irel"] >= label_min:
            ax.text(L["tth"], L["Irel"] + 2, L["hkl"], rotation=90, ha="center", va="bottom", fontsize=6.5, color=INK)
    ax.set_ylim(0, 125)
    lam = info.get("lam") or [None]
    _ax(ax, "2θ [°]", ("Intensität, relativ [%]" if _de(lang) else "Relative intensity [%]"))
    _tag(fig, ("berechnet, λ = " if _de(lang) else "computed, λ = ") + f"{lam[0]:.5f} Å".replace(".", "," if _de(lang) else "."))
    fig.tight_layout()
    return fig


ELCOL = {"O": "#dc2626", "C": "#334155", "N": "#2563eb", "H": "#e5e7eb", "Si": "#a16207", "Ti": "#64748b", "Fe": "#b45309",
         "Cu": "#c2410c", "Al": "#94a3b8", "Na": "#7c3aed", "Cl": "#16a34a", "Zn": "#6366f1", "Ca": "#15803d",
         "F": "#65a30d", "Mg": "#059669", "Ga": "#0e7490", "As": "#9333ea", "W": "#1e3a8a", "Ce": "#a21caf"}


def fig_cell(info: dict, lang: str = "de"):
    """Elementarzelle: Atome in [0, 1]³ (mit Randbildern) in Kartesischen Koordinaten."""
    fig = plt.figure(figsize=(4.4, 4.2))
    ax = fig.add_subplot(111, projection="3d")
    A = np.asarray(info["basis"], float)
    corners = np.array([[i, j, k] for i in (0, 1) for j in (0, 1) for k in (0, 1)], float)
    for a in corners:
        for b in corners:
            if np.sum(np.abs(a - b)) == 1 and tuple(a) < tuple(b):
                P = np.array([a, b]) @ A
                ax.plot(P[:, 0], P[:, 1], P[:, 2], color=MUTED, lw=0.8)
    seen_el = {}
    for at in info.get("atoms_cell") or info["atoms"]:
        f = np.array([at["x"], at["y"], at["z"]], float) % 1.0
        imgs = [f]
        for ax_i in range(3):
            imgs += [g + np.eye(3)[ax_i] for g in list(imgs) if abs(g[ax_i]) < 1e-3]
        col = ELCOL.get(at["el"], COLORS[len(seen_el) % len(COLORS)])
        for g in imgs:
            P = g @ A
            ax.scatter([P[0]], [P[1]], [P[2]], s=70, color=col, edgecolors="black", linewidths=0.3,
                       label=at["el"] if at["el"] not in seen_el else None, depthshade=True)
            seen_el[at["el"]] = col
    ax.set_box_aspect(np.ptp(np.vstack([corners @ A]), axis=0) + 1e-9)
    ax.set_axis_off()
    ax.legend(fontsize=7, frameon=False, loc="upper left")
    ax.view_init(elev=18, azim=-60)
    fig.tight_layout()
    return fig


# ----------------------------------------------------------------------------- Gitter
def _pow10(v: float) -> str:
    """Überhöhungsfaktor lesbar: 1e6 -> 10⁶, 250 -> 250."""
    e = math.log10(v) if v > 0 else 0
    if v >= 1e4 and abs(e - round(e)) < 1e-9:
        return "10" + str(int(round(e))).translate(str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻"))
    return f"{v:.3g}" if v < 1e4 else f"{v:.2e}"


def _cell_frac(cell):
    C = np.asarray(cell["corners"], float)
    E = np.stack([C[4] - C[0], C[2] - C[0], C[1] - C[0]], 1)
    inv = np.linalg.inv(E)
    return lambda P: (np.asarray(P, float) - C[0]) @ inv.T


def fig_lattice(res: dict, lang: str = "de", cell_only: bool = False, shrink: float = 0.45):
    """Gitterausschnitt (3D) mit hervorgehobener Elementarzelle, Leerstellen und Versetzungslinie; cell_only: nur die
    Atome der Elementarzelle."""
    de = _de(lang)
    fig = plt.figure(figsize=(5.2, 4.8) if not cell_only else (4.2, 4.0))
    ax = fig.add_subplot(111, projection="3d")
    A = np.asarray(res["atoms"], float)
    P, K = A[:, :3], A[:, 3].astype(int)
    V = np.asarray(res.get("vacancies") or np.zeros((0, 3)), float).reshape(-1, 3)
    cell = res.get("cell")
    inside = np.zeros(len(P), bool)
    vin = np.zeros(len(V), bool)
    if cell:
        f = _cell_frac(cell)
        inside = np.all((f(P) > -0.08) & (f(P) < 1.08), axis=1)
        if len(V):
            vin = np.all((f(V) > -0.08) & (f(V) < 1.08), axis=1)
    if cell_only and cell:
        P, K, inside = P[inside], K[inside], inside[inside]
        V = V[vin]
    lo, hi = (P.min(0), P.max(0)) if len(P) else (np.zeros(3), np.ones(3))
    span = float(np.max(hi - lo)) or 1.0
    ppa = (fig.get_size_inches()[0] * 72 * 0.62) / span          # Punkte je Å (grob)
    kinds = res["kinds"]
    hl = bool(cell) and not cell_only
    for k, kd in enumerate(kinds):
        named = False
        for dim, sel in ((True, (K == k) & ~inside), (False, (K == k) & inside)):
            if not sel.any() or (dim and cell_only):
                continue
            s = (2 * kd["r"] * shrink * ppa * (0.8 if dim and hl else 1)) ** 2
            # Fremdatome und zweite Phase ausserhalb der Zelle kräftiger als die Matrix, damit sie sichtbar bleiben
            a_dim = 0.45 if kd["role"] in ("host", "liq") else 0.8
            ax.scatter(P[sel, 0], P[sel, 1], P[sel, 2], s=s, color=kd["color"],
                       edgecolors="#00000055" if dim and hl else "black", linewidths=0.25,
                       alpha=a_dim if dim and hl else 1.0, depthshade=not (dim and hl), label=None if named else kd["name"])
            named = True
    if len(V):
        r_h = next((kd["r"] for kd in kinds if kd["role"] in ("host", "liq")), kinds[0]["r"])
        ax.scatter(V[:, 0], V[:, 1], V[:, 2], s=(2 * r_h * shrink * ppa) ** 2, facecolors="none", edgecolors=INK,
                   linewidths=0.8, linestyle="--", label=("Leerstelle" if de else "Vacancy") +
                   (f" (×{_pow10(res['boost'])})" if res.get("boost", 1) > 1 else ""))
    if cell:
        C = np.asarray(cell["corners"], float)
        for a, b in cell["edges"]:
            ax.plot(*np.stack([C[a], C[b]], 1), color=COLORS[1], lw=1.6)
    if res.get("disl") and not cell_only:
        c = res["disl"]["core"]
        ax.plot([c[0], c[0]], [0, res["box"][1]], [c[2], c[2]], color="#b91c1c", lw=2, ls="--",
                label=("Stufenversetzung" if de else "Edge dislocation"))
    ax.set_box_aspect(np.maximum(hi - lo, 1e-6), zoom=1.3)
    ax.set_axis_off()
    ax.view_init(elev=16, azim=-58)
    fig.subplots_adjust(0, 0, 1, 1)
    lg = ax.legend(fontsize=6.5, frameon=False, loc="upper left", markerscale=0.5)
    for h in getattr(lg, "legend_handles", None) or getattr(lg, "legendHandles", []):
        h.set_alpha(1)
    tag = ["Modell" if de else "Model"]
    if res.get("boost", 1) > 1:
        tag.append((f"Leerstellen ×{_pow10(res['boost'])} überhöht" if de else f"vacancies ×{_pow10(res['boost'])} exaggerated"))
    if res.get("vib_boost", 1) > 1:
        tag.append((f"Schwingung ×{res['vib_boost']:.3g}" if de else f"vibration ×{res['vib_boost']:.3g}"))
    tag.append((f"Atome ×{shrink:g} verkleinert" if de else f"atoms scaled ×{shrink:g}"))
    _tag(fig, " · ".join(tag))
    return fig


def slice_points(res: dict, plane: str):
    """Atome einer Atomlage (hkl) durch die Mitte des Ausschnitts, projiziert in die Ebene: (Q [n×2], kinds, V, w)."""
    g, a, c = res["phase"]["gitter_id"], res["lattice"]["a"], res["lattice"]["c"]
    if g == "hdp":
        n = {"0001": [0, 0, 1], "10-10": [math.sqrt(3) / 2, .5, 0], "11-20": [.5, math.sqrt(3) / 2, 0]}.get(plane)
        sp = {"0001": (c or a) / 2, "10-10": a / (2 * math.sqrt(3)), "11-20": a / 2}.get(plane)
    else:
        n = {"100": [1, 0, 0], "110": [1, 1, 0], "111": [1, 1, 1]}.get(plane)
        sp = ({"100": a / 2, "110": a / (2 * math.sqrt(2)), "111": a / math.sqrt(3)} if g == "kfz" else
              {"100": a / 2, "110": a / math.sqrt(2), "111": a / (2 * math.sqrt(3))}).get(plane)
    if n is None:
        return None
    n = np.asarray(res["frame"], float) @ np.asarray(n, float)
    n /= np.linalg.norm(n)
    A = np.asarray(res["atoms"], float)
    P, K = A[:, :3], A[:, 3].astype(int)
    cen = np.asarray(res["box"], float) / 2
    s = (P - cen) @ n
    host = np.array([res["kinds"][k]["role"] in ("host", "liq") for k in K])
    s0 = s[host][np.argmin(np.abs(s[host]))] if host.any() else 0.0
    w = min(0.45 * sp, 0.4 + 2 * (res.get("sigma") or 0) * (res.get("vib_boost") or 1))
    up = np.array([0, 0, 1.0]) if abs(n[2]) < 0.9 else np.array([1.0, 0, 0])
    u = np.cross(up, n)
    u /= np.linalg.norm(u)
    v = np.cross(n, u)
    sel = np.abs(s - s0) < w
    Q = np.stack([(P[sel] - cen) @ u, (P[sel] - cen) @ v], 1)
    V = np.asarray(res.get("vacancies") or np.zeros((0, 3)), float).reshape(-1, 3)
    vs = np.abs((V - cen) @ n - s0) < w if len(V) else np.zeros(0, bool)
    QV = np.stack([(V[vs] - cen) @ u, (V[vs] - cen) @ v], 1) if vs.any() else np.zeros((0, 2))
    return Q, K[sel], QV, w


def fig_slice(res: dict, plane: str, lang: str = "de"):
    de = _de(lang)
    sp = slice_points(res, plane)
    if sp is None:
        return None
    Q, K, QV, w = sp
    fig, ax = plt.subplots(figsize=(4.6, 4.6))
    from matplotlib.patches import Circle
    kinds = res["kinds"]
    order = np.argsort([-kinds[k]["r"] for k in K])
    seen = set()
    for j in order:
        kd = kinds[K[j]]
        ax.add_patch(Circle(Q[j], kd["r"] * 0.92, facecolor=kd["color"], edgecolor="white", lw=0.4,
                            label=None if K[j] in seen else kd["name"]))
        seen.add(K[j])
    r_h = next((kd["r"] for kd in kinds if kd["role"] in ("host", "liq")), kinds[0]["r"])
    for j, q in enumerate(QV):
        ax.add_patch(Circle(q, r_h * 0.92, facecolor="none", edgecolor=INK, lw=0.8, ls="--",
                            label=("Leerstelle" if de else "Vacancy") if j == 0 else None))
    ext = float(np.abs(Q).max()) + 2 if len(Q) else 5
    ax.set_xlim(-ext, ext)
    ax.set_ylim(-ext, ext)
    ax.set_aspect("equal")
    ax.set_xlabel("Å", color=INK)
    ax.tick_params(colors=INK, labelsize=7)
    for s_ in ("top", "right"):
        ax.spines[s_].set_visible(False)
    ax.legend(fontsize=6.5, frameon=False, loc="upper left", bbox_to_anchor=(1.0, 1.0))
    fig.tight_layout()
    _tag(fig, (f"Atomlage ({plane}), Dicke ±{w:.2f} Å, wahre Grösse" if de else f"Atomic layer ({plane}), ±{w:.2f} Å, true size").replace(".", "," if de else "."))
    return fig


# ----------------------------------------------------------------------------- XRD
def fig_xrd(res: dict, lang: str = "de", show_bg: bool = True):
    sticks = res.get("sticks") or []
    if sticks:
        fig, (ax, ax2) = plt.subplots(2, 1, figsize=(6.8, 4.6), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    else:
        fig, ax = plt.subplots(figsize=(6.8, 3.6))
        ax2 = None
    c = res["curve"]
    ax.plot(c["x"], res.get("raw") or c["y"], color=COLORS[0], lw=0.7, label="Messung" if _de(lang) else "Measured")
    if show_bg and any(c["bg"]):
        ax.plot(c["x"], c["bg"], color=MUTED, lw=0.7, ls="--", label="Untergrund (SNIP)" if _de(lang) else "Background (SNIP)")
    pk = res.get("peaks") or []
    if pk:
        bgx = np.interp([p["tth"] for p in pk], c["x"], c["bg"])
        ax.plot([p["tth"] for p in pk], [p["height"] + b for p, b in zip(pk, bgx)], "v", color=COLORS[1], ms=3.5,
                label=("Reflexe" if _de(lang) else "Peaks"))
        hk = {q["peak"]: q["hkl"] for q in (res.get("ref_match") or {}).get("pairs", [])}
        for i, (p, b) in enumerate(zip(pk, bgx)):
            if i in hk:
                ax.annotate(hk[i], (p["tth"], p["height"] + b), xytext=(0, 5), textcoords="offset points", rotation=90,
                            ha="center", va="bottom", fontsize=6.5, color=INK)
    _ax(ax, None if ax2 else "2θ [°]", ("Intensität [Zählungen]" if _de(lang) else "Intensity [counts]"))
    ax.legend(fontsize=7, frameon=False, loc="upper right")
    if ax2 is not None:
        for k, s in enumerate(sticks):
            col = COLORS[(k + 2) % len(COLORS)]
            for L in s["lines"]:
                ax2.vlines(L["tth"], k, k + 0.9 * L["I"] / 100, color=col, lw=1.0)
            ax2.text(c["x"][0], k + 0.5, " " + (s.get("name") or s["id"]), fontsize=7, color=col, va="center")
        ax2.set_yticks([])
        ax2.set_ylim(0, len(sticks))
        _ax(ax2, "2θ [°]")
        ax2.grid(False)
        _tag(fig, "Linien berechnet aus der Struktur" if _de(lang) else "Lines computed from the structure")
    fig.tight_layout()
    return fig


def fig_wh(wh: dict, lang: str = "de"):
    fig, ax = plt.subplots(figsize=(4.6, 3.3))
    x, y = np.asarray(wh["x"]), np.asarray(wh["y"]) * 1e3
    ax.plot(x, y, "o", color=COLORS[0], ms=4)
    xs = np.linspace(0, max(x) * 1.05, 10)
    ax.plot(xs, (wh["intercept"] + wh["strain"] * xs) * 1e3, color=COLORS[1], lw=1)
    _ax(ax, "4 sin θ", "β cos θ [mrad]")
    fig.tight_layout()
    return fig


def fig_nr(nr: dict, lang: str = "de"):
    fig, ax = plt.subplots(figsize=(4.6, 3.3))
    x, y = np.asarray(nr["x"]), np.asarray(nr["y"])
    ax.plot(x, y, "o", color=COLORS[0], ms=4)
    xs = np.linspace(0, max(x) * 1.05, 10)
    ax.plot(xs, nr["a0"] + nr["slope"] * xs, color=COLORS[1], lw=1)
    _ax(ax, "cos²θ (1/sin θ + 1/θ) / 2", "a [Å]")
    ax.ticklabel_format(axis="y", useOffset=False)
    fig.tight_layout()
    return fig


# ----------------------------------------------------------------------------- Phasendiagramme
def fig_diagram(res: dict, lang: str = "de"):
    d = res["diagram"]
    fig, ax = plt.subplots(figsize=(6.4, 4.6))
    for k, rg in enumerate(d["regions"]):
        P = np.asarray(rg["poly"], float)
        two = "+" in rg["label"]
        ax.add_patch(Polygon(P, closed=True, facecolor=("#f1f5f9" if two else "#e0f2f1"), edgecolor=INK, lw=0.8))
        cx, cy = P[:, 0].mean(), P[:, 1].mean()
        ax.text(cx, cy, rg["label"], ha="center", va="center", fontsize=7.5, color=INK)
    for inv in d["invariants"]:
        ax.hlines(inv["T"], inv["x"][0], inv["x"][-1], color=INK, lw=1.0)
        ax.text(inv["x"][-1], inv["T"], f" {inv['T']:g} °C", fontsize=6.5, va="center", color=MUTED)
    lv = res.get("lever")
    if lv and lv.get("tie"):
        ax.plot(lv["tie"], [lv["T"]] * 2, color=COLORS[1], lw=1.6)
        ax.plot([lv["x"]], [lv["T"]], "o", color=COLORS[1], ms=4)
    if lv or res.get("cooling"):
        x = (lv or {}).get("x")
        if x is None and res.get("cooling"):
            x = res["cooling"].get("x")
        if x is not None:
            ax.axvline(x, color=COLORS[0], lw=0.8, ls=":")
    ax.set_xlim(*d["xlim"])
    ax.set_ylim(*d["Tlim"])
    _ax(ax, d["x_label"], "T [°C]")
    ax.grid(False)
    _tag(fig, "schematisch, aus Eckpunkten der Literatur" if _de(lang) else "schematic, from literature key points")
    fig.tight_layout()
    return fig


def fig_computed(res: dict, lang: str = "de"):
    c, p = res["computed"], res["model"]
    fig, ax = plt.subplots(figsize=(6.0, 4.2))
    for k, (name, col) in enumerate((("liquidus", COLORS[1]), ("solidus", COLORS[0]), ("solvus", COLORS[2]))):
        pts = c["points"].get(name) or []
        if pts:
            P = np.asarray(pts, float)
            o = np.argsort(P[:, 0])
            ax.plot(P[o, 0], P[o, 1], ".", ms=1.6, color=col, label=name.capitalize())
    lv = res.get("lever")
    if lv and lv.get("tie"):
        ax.plot(lv["tie"], [lv["T"]] * 2, color=INK, lw=1.4)
        ax.plot([lv["x"]], [lv["T"]], "o", color=INK, ms=4)
    unit = c.get("unit", "wt")
    ax.set_xlim(0, 100)
    ax.set_ylim(*p["Tlim"])
    _ax(ax, f"{p['B']} [{'Ma.-%' if unit == 'wt' else 'At.-%'}]" if _de(lang) else f"{p['B']} [{'wt%' if unit == 'wt' else 'at%'}]",
        "T [°C]")
    ax.legend(fontsize=7, frameon=False, loc="upper left")
    _tag(fig, ("berechnet: " if _de(lang) else "computed: ")
         + (("ideale Lösung" if _de(lang) else "ideal solution") if not (p.get("omega_L") or p.get("omega_S"))
            else ("reguläre Lösung" if _de(lang) else "regular solution")))
    fig.tight_layout()
    return fig


# ----------------------------------------------------------------------------- Stahl
def fig_carb(carb: dict, lang: str = "de"):
    fig, ax = plt.subplots(figsize=(5.2, 3.4))
    ax.plot(carb["x_mm"], carb["c"], color=COLORS[0], lw=1.2)
    ax.axhline(carb["c_limit"], color=MUTED, lw=0.8, ls="--")
    if carb.get("depth_mm"):
        ax.axvline(carb["depth_mm"], color=COLORS[1], lw=0.8, ls=":")
        ax.text(carb["depth_mm"], carb["cs"], " " + _fmt(carb["depth_mm"], lang, 2) + " mm", fontsize=7, color=COLORS[1], va="top")
    _ax(ax, ("Abstand von der Oberfläche [mm]" if _de(lang) else "Distance from surface [mm]"),
        ("C-Gehalt [Ma.-%]" if _de(lang) else "Carbon content [wt%]"))
    fig.tight_layout()
    return fig


# ----------------------------------------------------------------------------- Laminat
def fig_laminate(res: dict, lang: str = "de"):
    fig, axs = plt.subplots(1, 3, figsize=(7.0, 3.6), sharey=True)
    names = ["σ₁", "σ₂", "τ₁₂"]
    for k, ax in enumerate(axs):
        for p in res["plies"]:
            z = [pt["z"] for pt in p["points"]]
            s = [pt["sig_12"][k] for pt in p["points"]]
            ax.plot(s, z, color=COLORS[0], lw=1.2)
            ax.axhspan(p["z0"], p["z1"], color=("#f1f5f9" if p["k"] % 2 else "white"), lw=0)
            if k == 0:
                ax.text(ax.get_xlim()[0], (p["z0"] + p["z1"]) / 2, f" {p['angle']:g}°", fontsize=6, va="center", color=MUTED)
        ax.axvline(0, color=MUTED, lw=0.6)
        _ax(ax, names[k] + " [MPa]", "z [mm]" if k == 0 else None)
    axs[0].invert_yaxis()
    fig.tight_layout()
    return fig


# ----------------------------------------------------------------------------- Ermüdung
def fig_sn(res: dict, lang: str = "de"):
    fig, ax = plt.subplots(figsize=(5.8, 3.9))
    pts = res["points"]
    f = [p for p in pts if not p["runout"]]
    r = [p for p in pts if p["runout"]]
    ax.plot([p["N"] for p in f], [p["sar"] for p in f], "o", color=COLORS[0], ms=4.5, label="Bruch" if _de(lang) else "Failure")
    if r:
        ax.plot([p["N"] for p in r], [p["sar"] for p in r], ">", mfc="none", color=COLORS[0], ms=6,
                label="Durchläufer" if _de(lang) else "Run-out")
    ln = res["line"]
    ax.plot(ln["N"], ln["sa"], color=COLORS[1], lw=1.2, label="Basquin" + (" (ML)" if res["fit"].get("mle") else ""))
    if res.get("band"):
        b = res["band"]
        ax.plot(b["N_lo"], b["sa"], color=COLORS[1], lw=0.7, ls="--")
        ax.plot(b["N_hi"], b["sa"], color=COLORS[1], lw=0.7, ls="--",
                label=("95-%-Vorhersagebereich (KQ)" if _de(lang) else "95 % prediction band (LSQ)"))
    ax.set_xscale("log")
    ax.set_yscale("log")
    _ax(ax, ("Lastwechsel N" if _de(lang) else "Cycles N"),
        ("Spannungsamplitude σ_a [MPa]" if _de(lang) else "Stress amplitude σa [MPa]"))
    ax.grid(True, which="minor", color=GRIDC, lw=0.3)
    ax.legend(fontsize=7, frameon=False)
    fig.tight_layout()
    return fig


def fig_haigh(res: dict, lang: str = "de"):
    fig, ax = plt.subplots(figsize=(5.4, 3.7))
    for k, (m, d) in enumerate(res["haigh"].items()):
        ax.plot(d["sm"], d["sa"], color=COLORS[k % len(COLORS)], lw=1.1, label=m.capitalize())
    for p in res.get("points") or []:
        if p.get("sm"):
            ax.plot([p["sm"]], [p["sa"]], "o", color=INK, ms=3.5)
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)
    _ax(ax, ("Mittelspannung σ_m [MPa]" if _de(lang) else "Mean stress σm [MPa]"),
        ("Amplitude σ_a [MPa]" if _de(lang) else "Amplitude σa [MPa]"))
    ax.legend(fontsize=7, frameon=False)
    fig.tight_layout()
    return fig


def fig_rainflow(rf: dict, lang: str = "de"):
    cyc = rf["cycles"]
    fig, ax = plt.subplots(figsize=(5.2, 3.2))
    rng = np.array([c["range"] for c in cyc])
    cnt = np.array([c["count"] for c in cyc])
    nb = min(30, max(5, int(np.sqrt(len(rng))) + 2))
    ax.hist(rng, bins=nb, weights=cnt, color=COLORS[0], alpha=0.85)
    _ax(ax, ("Schwingbreite" if _de(lang) else "Range"), ("Zyklen" if _de(lang) else "Cycles"))
    fig.tight_layout()
    return fig


# ----------------------------------------------------------------------------- Weibull, Bruch
def fig_weibull(res: dict, lang: str = "de"):
    L = res["lsq"]
    best = res[res["method"]]
    fig, ax = plt.subplots(figsize=(5.2, 3.8))
    ax.plot(L["X"], L["Y"], "o", color=COLORS[0], ms=4, label=("Messwerte (Bernard-Rang)" if _de(lang) else "Data (Bernard rank)"))
    xs = np.linspace(min(L["X"]) - 0.05, max(L["X"]) + 0.05, 20)
    for k, (m, s0, lab) in enumerate(((L["m"], L["sigma0"], "KQ" if _de(lang) else "LSQ"),
                                      (res["mle"]["m"], res["mle"]["sigma0"], "ML"))):
        ax.plot(xs, m * (xs - math.log(s0)), color=COLORS[1 + k], lw=1.0, ls="-" if k else "--",
                label=f"{lab}: m = {_fmt(m, lang, 1)}, σ₀ = {_fmt(s0, lang, 0)}")
    _ax(ax, "ln σ", "ln ln(1/(1 − F))")
    sec = ax.secondary_yaxis("right", functions=(lambda y: 100 * (1 - np.exp(-np.exp(y))),
                                                 lambda p: np.log(-np.log(1 - np.clip(p, 1e-6, 99.9999) / 100))))
    sec.set_ylabel("F [%]", color=INK)
    sec.tick_params(labelsize=7)
    ax.legend(fontsize=7, frameon=False, loc="upper left")
    fig.tight_layout()
    return fig


def fig_crack(cr: dict, lang: str = "de"):
    fig, ax = plt.subplots(figsize=(5.0, 3.4))
    c = cr["curve"]
    ax.plot(c["sigma"], c["a_mm"], color=COLORS[0], lw=1.2)
    ax.plot([cr["sigma"]], [cr["a_c_mm"]], "o", color=COLORS[1], ms=4)
    ax.set_yscale("log")
    _ax(ax, "σ [MPa]", ("kritische Risslänge a_c [mm]" if _de(lang) else "critical crack length a_c [mm]"))
    fig.tight_layout()
    return fig


# ----------------------------------------------------------------------------- Härte
def fig_hp(hp: dict, lang: str = "de"):
    fig, ax = plt.subplots(figsize=(4.8, 3.3))
    x = np.asarray(hp["x"])
    ax.plot(x, hp["y"], "o", color=COLORS[0], ms=4)
    xs = np.linspace(0, x.max() * 1.1, 10)
    ax.plot(xs, hp["sigma0"] + hp["k"] * xs, color=COLORS[1], lw=1)
    _ax(ax, "d^(−½) [m^(−½)]", ("Streckgrenze [MPa]" if _de(lang) else "Yield strength [MPa]"))
    fig.tight_layout()
    return fig


# ----------------------------------------------------------------------------- Korrosion, Kriechen
def fig_tafel(res: dict, lang: str = "de"):
    fig, ax = plt.subplots(figsize=(5.4, 3.8))
    E, j = np.asarray(res["curve"]["E"], float), np.asarray(res["curve"]["j"], float)
    ok = np.abs(j) > 0
    ax.plot(np.abs(j[ok]), E[ok], color=COLORS[0], lw=1.0, label=("Messung" if _de(lang) else "Measured"))
    lg = np.linspace(math.log10(res["icorr"]) - 0.3, math.log10(np.abs(j[ok]).max()), 20)
    ax.plot(10 ** lg, res["fit_a"]["a"] + res["fit_a"]["b"] * lg, ls="--", color=COLORS[1], lw=0.9,
            label=f"β_a = {_fmt(res['ba'], lang, 0)} mV/dec")
    ax.plot(10 ** lg, res["fit_c"]["a"] + res["fit_c"]["b"] * lg, ls="--", color=COLORS[2], lw=0.9,
            label=f"β_c = {_fmt(res['bc'], lang, 0)} mV/dec")
    ax.plot([res["icorr"]], [res["Ecorr"]], "o", color=INK, ms=4)
    ax.set_xscale("log")
    _ax(ax, "|i| [µA/cm²]", "E [V]")
    ax.legend(fontsize=7, frameon=False)
    fig.tight_layout()
    return fig


def fig_lmp(lmp: dict, lang: str = "de"):
    fig, ax = plt.subplots(figsize=(5.2, 3.5))
    ax.plot(lmp["P"], 10 ** np.asarray(lmp["lg_sigma"]), "o", color=COLORS[0], ms=4)
    ax.plot(lmp["curve"]["P"], lmp["curve"]["sigma"], color=COLORS[1], lw=1.1)
    ax.set_yscale("log")
    _ax(ax, f"P = T (C + lg t_r), C = {_fmt(lmp['C'], lang, 1)}", "σ [MPa]")
    fig.tight_layout()
    return fig


def fig_norton(nt: dict, lang: str = "de"):
    fig, ax = plt.subplots(figsize=(5.0, 3.4))
    Ts = sorted({p["T"] for p in nt["points"]})
    for k, T in enumerate(Ts):
        P = [p for p in nt["points"] if p["T"] == T]
        s = np.array([p["s"] for p in P])
        ax.plot(s, [p["rate"] for p in P], "o", color=COLORS[k % len(COLORS)], ms=4, label=f"{T:g} °C")
        ss = np.linspace(s.min() * 0.9, s.max() * 1.1, 10)
        Q = (nt.get("Q_kJ") or 0) * 1e3
        lg = nt["lgA"] + nt["n"] * np.log10(ss) - (Q / (8.314462618 * (T + 273.15) * math.log(10)) if Q else 0)
        ax.plot(ss, 10 ** lg, color=COLORS[k % len(COLORS)], lw=0.9)
    ax.set_xscale("log")
    ax.set_yscale("log")
    _ax(ax, "σ [MPa]", ("Kriechrate ε̇ [1/h]" if _de(lang) else "Creep rate ε̇ [1/h]"))
    ax.legend(fontsize=7, frameon=False)
    fig.tight_layout()
    return fig


def close(fig):
    plt.close(fig)
