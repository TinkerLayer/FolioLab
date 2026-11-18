"""Diagramme (Spezifikation 6.3) und Grafiken fuer den grafischen Bericht.

Regeln fuer die Bilddateien: keine Erklaertexte im Bild, nur Titel, Achsenbeschriftung, Legende und
Zahlen an den Marken. Dezimalkomma, Einheiten in der Achsenbeschriftung.
Jede Funktion zeichnet auf eine uebergebene Achse, damit der Bericht sie wiederverwenden kann.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Patch, Polygon, Rectangle  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

from .. import alloys as alloys_mod  # noqa: E402
from ..analyse import PHASES, Result, fmt  # noqa: E402

PHASE_COLORS = ["#9aa0a6", "#1a73e8", "#e8710a", "#d93025", "#000000", "#cccccc"]
MARK = {"yield": "#188038", "max": "#d93025", "break": "#202124"}
REF_COLOR = "#9334e6"
FILE_COLORS = ["#d93025", "#1a73e8", "#188038", "#e8710a", "#9334e6", "#007b83"]

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold",
    "axes.grid": True, "grid.alpha": 0.3, "axes.spines.top": False, "axes.spines.right": False,
    "legend.frameon": False, "axes.unicode_minus": True, "pdf.fonttype": 42,
})


def _cf(x, _=None):
    s = f"{x:.10g}"
    if "e" in s:
        s = f"{x:.2f}"
    return s.replace(".", ",").replace("-", "−")


def _comma(ax, x=True, y=True):
    if x:
        ax.xaxis.set_major_formatter(FuncFormatter(_cf))
    if y:
        ax.yaxis.set_major_formatter(FuncFormatter(_cf))


def _ylabel(r: Result) -> str:
    return "Spannung σ [MPa]" if r.mode == "Spannung" else "Kraft |F| [N]"


def _nd(r: Result) -> int:
    """Nachkommastellen der Marken: N auf 0,1, MPa ganzzahlig."""
    return 0 if r.mode == "Spannung" else 1


def _sym(r: Result) -> str:
    return "σ" if r.mode == "Spannung" else "F"


def _new(ax, size=(10, 5.6)):
    if ax is None:
        fig, ax = plt.subplots(figsize=size)
        return ax, True
    return ax, False


def chart_titles(r: Result) -> list[str]:
    q = "Spannung" if r.mode == "Spannung" else "Kraft"
    return [
        f"{q}s-Zeit-Verlauf nach Phasen",
        "Linearer Abschnitt: Ausgleichsgerade und Abweichung",
        f"Spannungs-Dehnungs-Feld {r.group} (idealisiert) mit Messkurve",
        "Streckgrenze und Zugfestigkeit der Kandidaten",
    ]


def _phase_label(code: int) -> str:
    return "Abfall (Einschnürung?)" if code == 3 else PHASES[code]


# --------------------------------------------------------------------------- 1 Verlauf
def chart1(r: Result, ax=None, title: bool = True):
    ax, own = _new(ax)
    t, y = r.t, r.y
    ph = r.phases[:len(t)]
    for code in range(4):  # der einzelne Lastabfall-Punkt gehoert zur Linie der Abfallphase
        idx = np.where(ph == code)[0]
        if not len(idx):
            continue
        lo, hi = idx[0], min(idx[-1] + 1, len(t) - 1)  # an Folgephase anschliessen
        ax.plot(t[lo:hi + 1], y[lo:hi + 1], color=PHASE_COLORS[code], lw=1.8, label=_phase_label(code))
    u, nd = r.unit, _nd(r)
    marks = []
    if r.yield_idx is not None:
        marks.append(("yield", r.yield_idx, f"Fliessbeginn ({fmt(r.config.yield_threshold * 100, 1)} %)"))
    marks.append(("max", r.imax, "Maximum"))
    if r.break_idx is not None:
        marks.append(("break", r.break_idx, "Bruch"))
    offsets = {"yield": ((8, 10), "left"), "max": ((-12, 10), "right"), "break": ((-12, -28), "right")}
    for key, i, lab in marks:
        ax.plot(t[i], y[i], "o", ms=8, color=MARK[key], zorder=5, label=f"{lab}: {fmt(y[i], nd, u)}")
        off, ha = offsets[key]
        ax.annotate(f"{fmt(y[i], nd, u)}\n{fmt(t[i], 1, 's')}", (t[i], y[i]), textcoords="offset points",
                    xytext=off, ha=ha, fontsize=9, color=MARK[key], fontweight="bold")
    ax.set_xlabel("Zeit t [s]")
    ax.set_ylabel(_ylabel(r))
    if title:
        ax.set_title(chart_titles(r)[0])
    ax.set_xlim(0, t[-1] * 1.02)
    ax.set_ylim(0, y.max() * 1.15)
    ax.legend(loc="lower right", fontsize=8.5, ncol=2)
    _comma(ax)
    return ax.figure if own else None


# --------------------------------------------------------------------------- 2 Linearer Abschnitt
def _lin_end(r: Result) -> int:
    return min(len(r.t) - 1, (r.yield_idx or r.fit.hi) + int(3 * r.prep.rate_hz) + 20)


def chart2_fit(r: Result, ax, title: str | None = None, full: bool = False):
    t, y, u = r.t, r.y, r.unit
    end = len(t) - 1 if full else _lin_end(r)
    sl = slice(0, end + 1)
    ax.axvspan(t[r.fit.lo], t[r.fit.hi], color=PHASE_COLORS[1], alpha=0.10,
               label=f"Fitfenster {fmt(t[r.fit.lo], 1)} bis {fmt(t[r.fit.hi], 1, 's')}, n = {r.fit.n}")
    ax.plot(t[sl], y[sl], ".", ms=3.5, color="#3c78b4", label="Messpunkte")
    tt = np.array([r.t0, t[end]])
    ax.plot(tt, r.fit.k * tt + r.fit.q, "--", color="#c5221f", lw=1.4,
            label=f"Gerade aus dem Fitfenster, {_sym(r)} = {fmt(r.fit.k, 3)}·t − {fmt(-r.fit.q, 2)}")
    if r.yield_idx is not None:
        i = r.yield_idx
        ax.plot(t[i], y[i], "o", ms=8, color=MARK["yield"], zorder=5)
        ax.annotate(fmt(y[i], _nd(r), u), (t[i], y[i]), textcoords="offset points", xytext=(8, -14),
                    fontsize=9, color=MARK["yield"], fontweight="bold")
    ax.set_ylabel(_ylabel(r))
    ax.set_xlabel("Zeit t [s]")
    ax.set_xlim(0, t[end] * 1.02)
    ax.set_ylim(0, y[sl].max() * (1.6 if full else 1.15))
    if title:
        ax.set_title(title)
    ax.legend(loc="upper left", fontsize=8.5)
    _comma(ax)


def chart2_dev(r: Result, ax, title: str | None = None):
    t, y, u = r.t, r.y, r.unit
    end = _lin_end(r)
    dev = r.fit.k * t + r.fit.q - y
    thr = r.config.yield_threshold * r.y[r.imax]
    start = max(0, r.fit.lo - int(1.5 * r.prep.rate_hz))
    sl = slice(start, end + 1)
    ax.axvspan(t[r.fit.lo], t[r.fit.hi], color=PHASE_COLORS[1], alpha=0.10)
    ax.axhline(0, color="#5f6368", lw=0.8)
    ax.axhline(thr, color="#9aa0a6", ls="--", lw=1.0)
    ax.annotate(f"Schwelle {fmt(r.config.yield_threshold * 100, 1)} % von {'Rm' if r.mode == 'Spannung' else 'Fmax'}",
                (t[start], thr), textcoords="offset points", xytext=(4, 4), fontsize=8.5, color="#5f6368")
    ax.plot(t[sl], dev[sl], "-", color="#7b1fa2", lw=1.6)
    if r.yield_idx is not None:
        i = r.yield_idx
        ax.plot(t[i], dev[i], "v", ms=9, color="#7b1fa2", zorder=5)
        ax.annotate(fmt(t[i], 1, "s"), (t[i], dev[i]), textcoords="offset points", xytext=(10, -4),
                    fontsize=9.5, color="#7b1fa2", fontweight="bold")
    ax.set_xlabel("Zeit t [s]")
    ax.set_ylabel(f"Abweichung [{u}]")
    lim = max(thr * 3.5, abs(r.fit.max_dev) * 3)
    ax.set_ylim(-max(r.fit.max_dev * 2.5, thr * 0.4), lim)
    ax.set_xlim(t[start], t[end])
    if title:
        ax.set_title(title)
    _comma(ax)


def chart2(r: Result):
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 7.2), gridspec_kw={"height_ratios": [3, 2]})
    chart2_fit(r, a1, chart_titles(r)[1])
    chart2_dev(r, a2)
    fig.tight_layout()
    return fig


# --------------------------------------------------------------------------- 3 Werkstofffeld
def measured_strain_curve(r: Result):
    """Messkurve fuer das Spannungs-Dehnungs-Diagramm mit Fusspunktkorrektur (4.3)."""
    m = r.strain >= 0
    m[:r.fit.lo] = False
    end = (r.break_idx if r.break_idx is not None else len(r.t) - 1) + 1
    m[end:] = False
    return np.concatenate([[0.0], r.strain[m] * 100]), np.concatenate([[0.0], r.y[m]])


NUMBER_MAX = 30   # mehr Vergleichskurven: keine Nummern an den Kurven (unlesbar), Schlüssel und Quellen bleiben


def field_members(r: Result) -> list:
    """Werkstoffe des Spannungs-Dehnungs-Felds in der Reihenfolge ihrer Kurvennummern (nach Rm, dann Name).
    Diagramm, Schlüssel, Quellentabelle und Literaturangaben verwenden dieselbe Nummerierung."""
    base = sorted(r.alloys or [], key=lambda a: (a.rm, a.name))
    names = {a.name for a in base}
    # zusätzlich eingeblendete Werkstoffe (andere Gruppen, eigene) hinten anhängen, gleiche Nummerierung
    return base + [a for a in (getattr(r, "extras", None) or []) if a.name not in names]


EXTRA_COLORS = ["#188038", "#e37400", "#a142f4", "#12b5cb", "#c5221f", "#795548", "#f538a0", "#5f6368"]


def curve_kind(a) -> str:
    return "Kurve aus Quelle" if getattr(a, "curve", None) else "idealisiert"


def _a_end(a) -> float:
    """Letzte Dehnung der Kurve eines Werkstoffs in % (eigene Kurve: letzter Punkt, sonst A)."""
    c = getattr(a, "curve", None)
    return max(a.a_pct, c[-1][0]) if c else a.a_pct


def short_name(name: str) -> str:
    return name.replace("EN AW-", "")


def key_layout(n: int, where: str) -> tuple[int, float]:
    """(Spalten, Schriftgrösse) des Werkstoffschlüssels."""
    if where == "below":
        return (2 if n <= 8 else 3 if n <= 30 else 4), (7.0 if n <= 30 else 6.0)
    return (1 if n <= 24 else 2 if n <= 48 else 3), (6.5 if n <= 30 else 5.5)


def key_height_in(n: int) -> float:
    """Zusätzliche Bildhöhe in Zoll, die der Schlüssel unter dem Diagramm braucht."""
    ncol, fs = key_layout(n, "below")
    return 0.35 + -(-n // ncol) * fs * 1.45 / 72


def _curve_numbers(ax, ends):
    """Kurvennummern am Ende jeder Vergleichskurve; überlappende Nummern werden nach oben versetzt
    und mit einer feinen Linie an ihr Kurvenende gebunden."""
    s = ax.figure.dpi / 72.0          # Pixel je Punkt
    by = {nr: (x, y) for nr, x, y in ends}
    pts = sorted(((nr, *ax.transData.transform(by[nr])) for nr in by), key=lambda p: (p[2], p[1]))
    placed = []
    for nr, xd, yd in pts:
        y = yd
        for _ in range(6):                     # höchstens 6 Stufen versetzen, sonst lieber knapp daneben
            if not any(abs(xd - px) < 13 * s and abs(y - py) < 8 * s for px, py in placed):
                break
            y += 8 * s
        placed.append((xd, y))
        dy = (y - yd) / s
        ax.annotate(str(nr), by[nr], xytext=(2.5, dy), textcoords="offset points", fontsize=6, color="#3c4043",
                    ha="left", va="center", zorder=4, gid="keep",
                    bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none", alpha=0.75),
                    arrowprops=dict(arrowstyle="-", color="#9aa0a6", lw=0.4, shrinkA=0, shrinkB=0) if dy > 0.5 else None)


def _field_key(ax, members, where: str):
    """Schlüssel Kurvennummer -> Werkstoff als eigene Legende (ax.legend bleibt für die Kurvenarten frei)."""
    from matplotlib.legend import Legend
    from matplotlib.lines import Line2D
    from matplotlib.transforms import offset_copy
    n = len(members)
    ncol, fs = key_layout(n, where)
    handles = [Line2D([], [], ls="none") for _ in members]
    labels = [f"{i}  {short_name(a.name)}" for i, a in enumerate(members, 1)]
    title = "Werkstoffe im Feld (Kurvennummer)" if n <= NUMBER_MAX else "Werkstoffe im Feld"
    kw = dict(handlelength=0, handletextpad=0, ncol=ncol, fontsize=fs, columnspacing=1.4, labelspacing=0.25,
              title=title, title_fontsize=fs + 0.5, alignment="left", frameon=False)
    if where == "below":           # fester Abstand unter der Achse (Teilstriche und Achsenbeschriftung)
        below = offset_copy(ax.transAxes, fig=ax.figure, y=-32, units="points")
        key = Legend(ax, handles, labels, loc="upper center", bbox_to_anchor=(0.5, 0.0), bbox_transform=below, **kw)
    else:
        key = Legend(ax, handles, labels, loc="upper left", bbox_to_anchor=(1.02, 1.0), borderaxespad=0, **kw)
    for t in key.get_texts():
        t.set_gid("keep")          # Werkstoffnamen nicht übersetzen
    ax.add_artist(key)
    key.set_clip_on(False)         # add_artist schneidet sonst an der Achsenfläche ab
    return key


def chart3(r: Result, ax=None, title: bool = True, key: str = "right"):
    """Spannungs-Dehnungs-Feld. key: "right" (neben dem Diagramm), "below" (darunter) oder "" (kein Schlüssel).
    Jede Vergleichskurve trägt ihre Nummer aus field_members()."""
    if r.mode != "Spannung" or r.strain is None:
        return None
    ax, own = _new(ax)
    members = field_members(r)
    group = sorted(r.alloys or [], key=lambda a: (a.rm, a.name))   # Hüllkurve nur aus der Vergleichsgruppe
    extras = members[len(group):]
    x, yy = measured_strain_curve(r)
    eps_max = max(_a_end(a) for a in members) / 100.0
    eps, up, lo, curves = alloys_mod.envelope(group or members, eps_max=eps_max)
    ends = []
    for nr, c in enumerate(curves if group else [], 1):
        ax.plot(eps * 100, c, "-", color="#9aa0a6", lw=0.6, alpha=0.8)
        ok = np.where(np.isfinite(c))[0]
        if len(ok):
            ends.append((nr, eps[ok[-1]] * 100, c[ok[-1]]))
    kind = "Kurven aus Quellen" if group and all(getattr(a, "curve", None) for a in group) else "idealisiert, zur Orientierung"
    ax.fill_between(eps * 100, lo, up, color="#1a73e8", alpha=0.12, lw=0, label=f"Feld {r.group} ({kind})")
    ax.plot(eps * 100, up, "-", color="#1a73e8", lw=1.4, label="obere Grenze")
    ax.plot(eps * 100, lo, "--", color="#1a73e8", lw=1.4, label="untere Grenze")
    ymax_x = 0.0
    for j, a in enumerate(extras):
        nr = len(group) + j + 1
        c = alloys_mod.ideal_curve(a, eps)
        ax.plot(eps * 100, c, "-", color=EXTRA_COLORS[j % len(EXTRA_COLORS)], lw=1.5,
                label=f"{nr} {short_name(a.name)} ({curve_kind(a)})", gid="keep")
        ok = np.where(np.isfinite(c))[0]
        if len(ok):
            ends.append((nr, eps[ok[-1]] * 100, c[ok[-1]]))
            ymax_x = max(ymax_x, float(np.nanmax(c)))
    if r.reference is not None:
        ref = r.reference
        e2 = np.linspace(0, _a_end(ref) / 100.0, 800)
        ax.plot(e2 * 100, alloys_mod.ideal_curve(ref, e2), "-", color=REF_COLOR, lw=2.2,
                label=f"Referenz {ref.name} ({curve_kind(ref)})")
    ax.plot(x, yy, "-", color="#d93025", lw=2.2, label=r.name)
    ax.plot(r.strain[r.imax] * 100, r.y[r.imax], "o", color=MARK["max"], ms=7)
    ax.annotate(fmt(r.y[r.imax], 0, "MPa"), (r.strain[r.imax] * 100, r.y[r.imax]),
                textcoords="offset points", xytext=(6, 6), fontsize=9, color=MARK["max"], fontweight="bold")
    ax.set_xlabel("Dehnung ε [%] (scheinbar)" if r.config.displacement_source != "probe" else "Dehnung ε [%]")
    ax.set_ylabel("Spannung σ [MPa]")
    if title:
        ax.set_title(chart_titles(r)[2])
    ref_a = _a_end(r.reference) if r.reference is not None else 0
    ax.set_xlim(0, max(eps.max() * 100, x.max(), ref_a) * 1.03)
    ymax = max(np.nanmax(up), yy.max(), r.reference.rm if r.reference is not None else 0, ymax_x)
    ax.set_ylim(0, ymax * 1.1)
    if own:
        ax.figure.tight_layout()
    if ends and len(members) <= NUMBER_MAX:
        _curve_numbers(ax, ends)
    if key and members:
        _field_key(ax, members, key)
    # oben rechts (hohe Festigkeit bei hoher Dehnung) ist das Feld praktisch immer leer: dort verdeckt die
    # Legende weder Kurven noch Kurvennummern
    ax.legend(loc="upper right", fontsize=8.5)
    _comma(ax)
    return ax.figure if own else None


# --------------------------------------------------------------------------- 4 Kandidaten
def chart4(r: Result, ax=None, title: bool = True, top: int = 6):
    if r.mode != "Spannung" or not r.comparison:
        return None
    ax, own = _new(ax)
    rows = list(r.comparison["rows"][:top])
    if r.reference is not None and all(row["name"] != r.reference.name for row in rows):
        rows.append({"name": r.reference.name, "Rp": r.reference.rp, "Rm": r.reference.rm})
    names = ["Messung"] + [row["name"].replace("EN AW-", "") for row in rows]
    y_meas = r.kv["yield"]["y"] if r.kv.get("yield") else 0.0
    rp = [y_meas] + [row["Rp"] or 0 for row in rows]
    rm = [r.kv["Rm"]] + [row["Rm"] for row in rows]
    is_ref = [False] + [r.reference is not None and row["name"] == r.reference.name for row in rows]
    x = np.arange(len(names))
    w = 0.38
    c_rp = ["#e8710a"] + ["#c39bf0" if ref else "#fbbc04" for ref in is_ref[1:]]
    c_rm = ["#d93025"] + [REF_COLOR if ref else "#1a73e8" for ref in is_ref[1:]]
    edge = ["#202124"] + ["none"] * len(rows)
    b1 = ax.bar(x - w / 2, rp, w, color=c_rp, edgecolor=edge, lw=1.2)
    b2 = ax.bar(x + w / 2, rm, w, color=c_rm, edgecolor=edge, lw=1.2)
    for bars, vals in ((b1, rp), (b2, rm)):
        for b, v in zip(bars, vals):
            if v:
                ax.annotate(fmt(v, 0), (b.get_x() + b.get_width() / 2, b.get_height()),
                            textcoords="offset points", xytext=(0, 2), ha="center", fontsize=8)
    lab_rp = f"Fliessbeginn {fmt(r.config.yield_threshold * 100, 1)} % (Messung) / Rp0,2 bzw. Streckspannung"
    handles = [Patch(color="#fbbc04", label=lab_rp), Patch(color="#1a73e8", label="Rm"),
               Patch(facecolor="#d93025", edgecolor="#202124", label="Messung")]
    if r.reference is not None:
        handles.append(Patch(color=REF_COLOR, label="Referenzwerkstoff"))
    ax.legend(handles=handles, loc="upper left", fontsize=7.5, ncol=2, framealpha=0.95)
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=25, ha="right", rotation_mode="anchor", fontsize=8)
    ax.get_xticklabels()[0].set_fontweight("bold")
    ax.set_ylabel("Spannung [MPa]")
    if title:
        ax.set_title(chart_titles(r)[3])
    ax.set_ylim(0, max(rm) * 1.55)
    ax.grid(axis="x", visible=False)
    ax.yaxis.set_major_formatter(FuncFormatter(_cf))
    if own:
        ax.figure.tight_layout()
    return ax.figure if own else None


# --------------------------------------------------------------------------- Berichtsgrafiken
def rm_strip(r: Result, ax, max_rows: int = 14):
    """Rm-Spannen der Vergleichsgruppe als Balken, gemessene Zugfestigkeit als senkrechte Linie."""
    rm = r.kv.get("Rm")
    rows = r.comparison["rows"] if r.comparison else []
    rows = sorted(rows[:max_rows], key=lambda row: row["Rm"])
    if r.reference is not None and all(row["name"] != r.reference.name for row in rows):
        ref = r.reference
        rows.append({"name": ref.name, "Rm": ref.rm, "Rm_min": ref.rm_min, "Rm_max": ref.rm_max, "status": "Referenz"})
    colors = {"Kandidat": "#188038", "zurückgestuft (Verfestigungsverhältnis)": "#e8710a",
              "unwahrscheinlich": "#9aa0a6", "ausgeschlossen": "#dadce0", "Referenz": REF_COLOR}
    for i, row in enumerate(rows):
        lo = row.get("Rm_min") if row.get("Rm_min") is not None else row["Rm"]
        hi = row.get("Rm_max") if row.get("Rm_max") is not None else row["Rm"]
        c = REF_COLOR if (r.reference is not None and row["name"] == r.reference.name) else colors.get(row.get("status"), "#9aa0a6")
        if hi > lo:
            ax.barh(i, hi - lo, left=lo, height=0.5, color=c, alpha=0.55)
        ax.plot(row["Rm"], i, "o", color=c, ms=6)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([row["name"].replace("EN AW-", "") for row in rows], fontsize=8)
    if rm:
        ax.axvline(rm, color="#d93025", lw=2)
        ax.annotate(f"Messung {fmt(rm, 0, 'MPa')}", (rm, len(rows) - 0.4), textcoords="offset points",
                    xytext=(4, 0), fontsize=8.5, color="#d93025", fontweight="bold")
    ax.set_xlabel("Zugfestigkeit Rm [MPa]")
    ax.grid(axis="y", visible=False)
    ax.set_ylim(-0.6, len(rows) - 0.2)
    handles = [Patch(color=colors[k], label=k.split(" (")[0]) for k in ("Kandidat", "zurückgestuft (Verfestigungsverhältnis)", "unwahrscheinlich")]
    if r.reference is not None:
        handles.append(Patch(color=REF_COLOR, label="Referenz"))
    ax.legend(handles=handles, loc="lower right", fontsize=7.5)
    ax.xaxis.set_major_formatter(FuncFormatter(_cf))


def yield_bars(r: Result, ax):
    """Fliessbeginn je Schwelle: zeigt, wie stark die gesetzte Schwelle das Ergebnis verschiebt."""
    rows = [row for row in r.yield_table if row["y"] is not None]
    labels = [f"{fmt(row['schwelle'] * 100, 1)} %" for row in rows]
    vals = [row["y"] for row in rows]
    cols = [MARK["yield"] if abs(row["schwelle"] - r.config.yield_threshold) < 1e-12 else "#a8dab5" for row in rows]
    bars = ax.bar(labels, vals, color=cols, width=0.6)
    for b, v in zip(bars, vals):
        ax.annotate(fmt(v, _nd(r)), (b.get_x() + b.get_width() / 2, v), textcoords="offset points",
                    xytext=(0, 2), ha="center", fontsize=8.5, fontweight="bold")
    ax.axhline(r.y[r.imax], color=MARK["max"], ls="--", lw=1)
    ax.annotate(f"Maximum {fmt(r.y[r.imax], _nd(r), r.unit)}", (0, r.y[r.imax]), xycoords=("axes fraction", "data"),
                textcoords="offset points", xytext=(2, 3), fontsize=8, color=MARK["max"])
    ax.set_ylabel(f"Fliessbeginn [{r.unit}]")
    ax.set_xlabel(f"Schwelle in % von {'Rm' if r.mode == 'Spannung' else 'Fmax'}")
    ax.set_ylim(0, r.y[r.imax] * 1.15)
    ax.grid(axis="x", visible=False)
    ax.yaxis.set_major_formatter(FuncFormatter(_cf))


def phase_timeline(r: Result, ax):
    """Phasen als waagrechter Zeitbalken."""
    t = r.t
    for b in r.phase_bounds():
        code = PHASES.index(b["phase"]) if b["phase"] in PHASES else 5
        if code > 3:
            continue
        t0, t1 = t[b["von"]], t[min(b["bis"] + 1, len(t) - 1)]
        ax.barh(0, t1 - t0, left=t0, height=0.6, color=PHASE_COLORS[code])
        if t1 - t0 > t[-1] * 0.07:
            ax.text((t0 + t1) / 2, 0, f"{_phase_label(code)}\n{fmt(t1 - t0, 1, 's')}", ha="center", va="center",
                    fontsize=7.5, color="white", fontweight="bold")
    ax.set_xlim(0, t[-1])
    ax.set_yticks([])
    ax.set_xlabel("Zeit t [s]")
    ax.grid(False)
    for s in ("left", "top", "right"):
        ax.spines[s].set_visible(False)
    ax.xaxis.set_major_formatter(FuncFormatter(_cf))


def specimen_sketch(r: Result, ax):
    """Massstaebliche Skizze der Probe mit Bemassung (Normprobe) bzw. Querschnitt (manuell)."""
    from ..analyse import SHAPES
    c = r.config
    sh = SHAPES.get(c.shape, {}) if c.specimen_mode == "norm" else {}
    ax.set_aspect("equal")
    ax.axis("off")
    col, edge = "#e8f0fe", "#1a73e8"
    if c.section in ("rund", "rohr"):
        d = c.diameter_mm if c.section == "rund" else c.outer_d_mm
        if not d:
            ax.text(0.5, 0.5, "Durchmesser fehlt", ha="center", va="center", transform=ax.transAxes, color="#5f6368")
            return
        L0 = r.l0 or 5 * d
        l1 = sh.get("l1") or L0 * 1.2
        D2 = sh.get("b2") or d * 1.6
        l3 = sh.get("l3") or l1 + 4 * d
        grip = (l3 - l1) / 2
        pts = [(0, -D2 / 2), (grip * 0.8, -D2 / 2), (grip, -d / 2), (grip + l1, -d / 2), (l3 - grip * 0.8, -D2 / 2),
               (l3, -D2 / 2), (l3, D2 / 2), (l3 - grip * 0.8, D2 / 2), (grip + l1, d / 2), (grip, d / 2),
               (grip * 0.8, D2 / 2), (0, D2 / 2)]
        ax.add_patch(Polygon(pts, closed=True, fc=col, ec=edge, lw=1.5))
        ax.plot([0, l3], [0, 0], "-.", color="#9aa0a6", lw=0.7)
        mid = l3 / 2
        _dim(ax, mid - L0 / 2, mid + L0 / 2, -D2 / 2 - D2 * 0.35, f"L₀ = {fmt(L0, 1)}")
        _vdim(ax, mid, -d / 2, d / 2, f"{'d' if c.section == 'rund' else 'D'} = {fmt(d, 2)}")
        if c.section == "rohr" and c.wall_mm:
            inner = d - 2 * c.wall_mm
            ax.add_patch(Rectangle((grip, -inner / 2), l1, inner, fc="white", ec=edge, lw=0.8, ls="--"))
        ax.set_xlim(-l3 * 0.05, l3 * 1.05)
        ax.set_ylim(-D2 * 1.1, D2 * 0.9)
        return
    b = c.width_mm
    if not b:
        ax.text(0.5, 0.5, "Stegbreite fehlt", ha="center", va="center", transform=ax.transAxes, color="#5f6368")
        return
    L0 = r.l0 or b * 5
    l1 = sh.get("l1")
    b2 = sh.get("b2")
    l3 = sh.get("l3") or max(L0 * 1.5, L0 + 4 * b)
    if l1 and b2 and b2 > b:  # Schulterstab
        rr = sh.get("r") or (b2 - b)
        trans = min((l3 - l1) / 2 * 0.55, max(rr * 0.6, (b2 - b)))
        g0 = (l3 - l1) / 2 - trans
        xs = np.linspace(0, 1, 20)
        curve = (1 - np.cos(np.pi * xs)) / 2
        top = [(0, b2 / 2), (g0, b2 / 2)] + [(g0 + trans * u, b2 / 2 - (b2 - b) / 2 * v) for u, v in zip(xs, curve)]
        top += [(l3 - g0 - trans + trans * u, b / 2 + (b2 - b) / 2 * v) for u, v in zip(xs, curve)] + [(l3, b2 / 2)]
        pts = top + [(x, -y) for x, y in reversed(top)]
        H = b2
    else:  # Streifen
        pts = [(0, -b / 2), (l3, -b / 2), (l3, b / 2), (0, b / 2)]
        H = b
        l1 = None
    ax.add_patch(Polygon(pts, closed=True, fc=col, ec=edge, lw=1.5))
    mid = l3 / 2
    ax.plot([mid - L0 / 2] * 2, [-b / 2, b / 2], color="#d93025", lw=1)
    ax.plot([mid + L0 / 2] * 2, [-b / 2, b / 2], color="#d93025", lw=1)
    _dim(ax, mid - L0 / 2, mid + L0 / 2, -H / 2 - H * 0.35, f"L₀ = {fmt(L0, 1)}", color="#d93025")
    _dim(ax, 0, l3, H / 2 + H * 0.35, f"l₃ = {fmt(l3, 0)}" + (" (schem.)" if not sh.get("l3") else ""))
    _vdim(ax, mid + L0 / 2 + l3 * 0.04, -b / 2, b / 2, f"b = {fmt(b, 2)}")
    if b2 and b2 > b:
        _vdim(ax, l3 * 0.03, -b2 / 2, b2 / 2, f"{fmt(b2, 1)}", left=True)
    ax.set_xlim(-l3 * (0.16 if (b2 and b2 > b) else 0.05), l3 * 1.12)
    ax.set_ylim(-H * 1.2, H * 1.2)
    if c.thickness_mm:
        ax.text(l3 * 1.0, -H * 1.05, f"Dicke {fmt(c.thickness_mm, 2, 'mm')}", ha="right", fontsize=8, color="#3c4043")


def _dim(ax, x0, x1, y, text, color="#3c4043"):
    ax.annotate("", (x0, y), (x1, y), arrowprops=dict(arrowstyle="<->", color=color, lw=0.9))
    ax.text((x0 + x1) / 2, y, text, ha="center", va="bottom", fontsize=8, color=color,
            bbox=dict(fc="white", ec="none", pad=0.5))


def _vdim(ax, x, y0, y1, text, left=False):
    ax.annotate("", (x, y0), (x, y1), arrowprops=dict(arrowstyle="<->", color="#3c4043", lw=0.9))
    ax.annotate(text, (x, (y0 + y1) / 2), xytext=(-4 if left else 4, 0), textcoords="offset points",
                ha="right" if left else "left", va="center", fontsize=8, color="#3c4043")


def kpi_tile(ax, label: str, value: str, sub: str = "", color: str = "#1a73e8", tag: str = ""):
    ax.axis("off")
    ax.add_patch(FancyBboxPatch((0.02, 0.04), 0.96, 0.92, boxstyle="round,pad=0,rounding_size=0.06",
                                transform=ax.transAxes, fc="#f8f9fa", ec="#dadce0", lw=0.8))
    ax.add_patch(Rectangle((0.02, 0.04), 0.035, 0.92, transform=ax.transAxes, fc=color, ec="none"))
    ax.text(0.1, 0.76, label, transform=ax.transAxes, fontsize=8, color="#5f6368", va="center")
    ax.text(0.1, 0.44, value, transform=ax.transAxes, fontsize=15, fontweight="bold", color="#202124", va="center")
    if sub:
        ax.text(0.1, 0.16, sub, transform=ax.transAxes, fontsize=7.5, color="#5f6368", va="center")
    if tag:
        ax.text(0.95, 0.76, tag, transform=ax.transAxes, fontsize=7, color="#8a4b00", ha="right", va="center",
                bbox=dict(boxstyle="round,pad=0.25", fc="#fff4e0", ec="none"))


# --------------------------------------------------------------------------- Vergleich mehrerer Messungen
def overlay_time(results: list[Result], ax):
    for i, r in enumerate(results):
        c = FILE_COLORS[i % len(FILE_COLORS)]
        ax.plot(r.t, r.y, "-", color=c, lw=1.8, label=r.name)
        ax.plot(r.t[r.imax], r.y[r.imax], "o", color=c, ms=7)
        ax.annotate(fmt(r.y[r.imax], _nd(r), r.unit), (r.t[r.imax], r.y[r.imax]), textcoords="offset points",
                    xytext=(-6, 8), ha="right", fontsize=8.5, color=c, fontweight="bold")
    r0 = results[0]
    ax.set_xlabel("Zeit t [s]")
    ax.set_ylabel(_ylabel(r0))
    ax.set_ylim(0, max(r.y.max() for r in results) * 1.15)
    ax.set_xlim(0, max(r.t[-1] for r in results) * 1.02)
    ax.legend(loc="lower right", fontsize=8.5)
    _comma(ax)


def overlay_strain(results: list[Result], ax):
    for i, r in enumerate(results):
        if r.strain is None or r.mode != "Spannung":
            continue
        x, y = measured_strain_curve(r)
        ax.plot(x, y, "-", color=FILE_COLORS[i % len(FILE_COLORS)], lw=1.8, label=r.name)
    ax.set_xlabel("Dehnung ε [%] (scheinbar)")
    ax.set_ylabel("Spannung σ [MPa]")
    ax.set_ylim(bottom=0)
    ax.set_xlim(left=0)
    ax.legend(loc="lower right", fontsize=8.5)
    _comma(ax)


def grouped_kpis(results: list[Result], ax):
    keys = [("Fliessbeginn", lambda r: r.kv["yield"]["y"] if r.kv["yield"] else None),
            ("Maximum", lambda r: r.y[r.imax]),
            ("vor Bruch", lambda r: r.kv["break"]["y"] if r.kv["break"] else None),
            ("Plateau", lambda r: r.kv["plateau"]["mittel"])]
    n = len(results)
    w = 0.8 / n
    x = np.arange(len(keys))
    for i, r in enumerate(results):
        vals = [fn(r) or 0 for _, fn in keys]
        bars = ax.bar(x - 0.4 + w / 2 + i * w, vals, w, color=FILE_COLORS[i % len(FILE_COLORS)], label=r.name)
        for b, v in zip(bars, vals):
            if v:
                ax.annotate(fmt(v, _nd(r)), (b.get_x() + b.get_width() / 2, v), textcoords="offset points",
                            xytext=(0, 2), ha="center", fontsize=7.5)
    ax.set_xticks(x)
    ax.set_xticklabels([k for k, _ in keys], fontsize=8)
    ax.set_ylabel(_ylabel(results[0]))
    ax.grid(axis="x", visible=False)
    top = max(r.y[r.imax] for r in results)
    ncol = 1 if any(len(r.name) > 16 for r in results) else 2
    ax.set_ylim(0, top * (1.2 + 0.1 * -(-n // ncol)))
    ax.legend(loc="upper left", fontsize=7.5, ncol=ncol, framealpha=0.95)
    ax.yaxis.set_major_formatter(FuncFormatter(_cf))


# --------------------------------------------------------------------------- Bilddateien
def build_figures(r: Result) -> list[tuple[int, str, object]]:
    titles = chart_titles(r)
    figs = []
    for nr, fn in enumerate((chart1, chart2, chart3, chart4), start=1):
        fig = fn(r)
        if fig is not None:
            fig.tight_layout()
            figs.append((nr, titles[nr - 1], fig))
    return figs


def write_pngs(r: Result, folder: Path, dpi: int = 160) -> list[Path]:
    out = []
    for nr, title, fig in build_figures(r):
        p = folder / f"{r.name}_Diagramm_{nr}.png"
        fig.savefig(p, dpi=dpi, bbox_inches="tight", pad_inches=0.15)  # Werkstoffschlüssel neben dem Diagramm
        plt.close(fig)
        out.append(p)
    return out
