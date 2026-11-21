"""Grafischer Bericht als PDF (A4 hoch), angelehnt an den Handbericht 'Versuch Zugstärke'.

Seite 1  Übersicht: Kennzahlen-Kacheln, Verlauf nach Phasen, Phasenbalken, Probenskizze, Referenzwerkstoff
Seite 2  Linearer Abschnitt: Messpunkte gegen Gerade, Abweichung mit Schwelle, Fliessbeginn je Schwelle
Seite 3  Werkstoffvergleich (nur mit A0): Spannungs-Dehnungs-Feld, Rm-Einordnung, Kandidaten
dann     Lastspitzen (nur bei mindestens 2 Spitzen, fortschreitendes Versagen): Verlauf, Spitzenlasten, Ausgleich, Tabelle
Seite 4  Kennwerte und Gültigkeit: Tabelle, alle Pflichthinweise (Abschnitt 7)

Dazu ein Vergleichsbericht fuer mehrere Messungen.
"""
from __future__ import annotations

import textwrap
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from ..analyse import Result, fmt, material_label, specimen_label
from . import charts as C

A4 = (8.27, 11.69)
INK, MUTED, ACCENT = "#202124", "#5f6368", "#1a73e8"


def _page(title: str, sub: str, nr: int, total: int, name: str):
    fig = plt.figure(figsize=A4)
    fig.patch.set_facecolor("white")
    fig.add_artist(plt.Rectangle((0, 0.955), 1, 0.045, transform=fig.transFigure, fc=ACCENT, ec="none"))
    fig.text(0.06, 0.972, title, fontsize=15, fontweight="bold", color="white", va="center")
    fig.text(0.94, 0.972, name, fontsize=9, color="white", va="center", ha="right")
    if sub:
        lines = textwrap.wrap(sub, width=118) or [""]
        if len(lines) > 2:
            lines = lines[:2]
            lines[1] = lines[1][:114] + " …"
        fig.text(0.06, 0.937 if len(lines) == 1 else 0.933, "\n".join(lines), fontsize=8.5 if len(lines) == 1 else 8,
                 color=MUTED, va="center", linespacing=1.3)
    fig.text(0.94, 0.018, f"Seite {nr} von {total}", fontsize=8, color=MUTED, ha="right")
    fig.text(0.06, 0.018, f"FLPS Auswerte-App · erstellt {datetime.now():%d.%m.%Y %H:%M}", fontsize=8, color=MUTED)
    return fig


def _section(fig, y, text):
    fig.text(0.06, y, text, fontsize=11, fontweight="bold", color=INK)


def _note_codes(r: Result, codes) -> str:
    present = [w["code"] for w in r.warnings if w["code"] in codes]
    seen = []
    for c in present:
        if c not in seen:
            seen.append(c)
    return ("Hinweise " + ", ".join(seen) + " auf der letzten Seite.") if seen else ""


def _subline(r: Result) -> str:
    d = r.device
    parts = [f"{d['model']} SN {d['serial']}", d["start"], specimen_label(r)]
    mat = material_label(r)
    if mat:
        parts.append(mat)
    return "  ·  ".join(parts)


def _kpis(r: Result) -> list[tuple]:
    kv, u, st = r.kv, r.unit, r.mode == "Spannung"
    nd = 0 if st else 1
    tiles = []
    m = kv["max"]
    tiles.append(("Zugfestigkeit Rm" if st else "Maximalkraft Fmax", fmt(m["y"], nd, u),
                  (f"{fmt(m['F'], 1, 'N')} · " if st else "") + f"bei {fmt(m['t'], 1, 's')}", C.MARK["max"], ""))
    y = kv["yield"]
    ep_on = (kv.get("ep") or {}).get("on", True)
    tiles.append((f"Fliessbeginn ({fmt(r.config.yield_threshold * 100, 1)} %)" if ep_on else "Fliessbeginn",
                  fmt(y["y"], nd, u) if y else "–",
                  (f"{fmt(y['F'], 1, 'N')} · bei {fmt(y['t'], 1, 's')}" if y
                   else "nicht gefunden" if ep_on else "elastisch/plastisch nicht eingeteilt"), C.MARK["yield"],
                  "keine Rp0,2" if ep_on else "siehe Hinweis 7.4"))
    b = kv["break"]
    tiles.append(("vor dem Bruch", fmt(b["y"], nd, u) if b else "–",
                  f"bei {fmt(b['t'], 1, 's')}" if b else "kein Bruch erkannt", C.MARK["break"], ""))
    dr = kv["drop"]
    tiles.append(("Abfall Maximum → Bruch", fmt(dr["pct"], 1, "%") if dr else "–",
                  f"{fmt(dr['abs'], nd, u)} in {fmt(dr['dauer'], 1, 's')}" if dr else "", C.PHASE_COLORS[3], ""))
    tiles.append((f"Haltezeit über {fmt(kv['hold']['schwelle'] * 100, 0, '%')}", fmt(kv["hold"]["dauer"], 1, "s"),
                  f"Verhältnis Max/Fliessbeginn {fmt(kv['ratio'], 2)}", C.PHASE_COLORS[2], ""))
    if r.e_schein_gpa is not None:
        tiles.append(("Elastizitätsmodul", fmt(r.e_schein_gpa, 1, "GPa"), f"k = {fmt(kv['fit']['k_N_s'], 3, 'N/s')}",
                      C.PHASE_COLORS[1], "scheinbar"))
    else:
        tiles.append(("Steigung linearer Abschnitt", fmt(kv["fit"]["k"], 2, f"{u}/s"),
                      f"R² = {fmt(kv['fit']['r2'], 5)}", C.PHASE_COLORS[1], ""))
    return tiles


def _ref_card(r: Result, ax):
    """Messung gegen Referenzwerkstoff als waagrechte Balken (Rp, Rm, A, E)."""
    ref = r.reference
    ax.set_title("Referenzwerkstoff", fontsize=10.5, loc="left")
    if ref is None:
        ax.axis("off")
        ax.text(0, 0.6, "Kein Referenzwerkstoff gewählt.", fontsize=9, color=MUTED, transform=ax.transAxes)
        ax.text(0, 0.45, "Auswahl in der Eingabemaske unter Werkstoff.", fontsize=8, color=MUTED, transform=ax.transAxes)
        return
    st = r.mode == "Spannung"
    rows = []
    if st:
        rows.append(("Rm [MPa]", r.kv["Rm"], ref.rm))
        if r.kv["yield"] and ref.rp:
            rows.append(("Fliessb. / Rp [MPa]", r.kv["yield"]["y"], ref.rp))
    if r.e_schein_gpa is not None:
        rows.append(("E [GPa] (schein.)", r.e_schein_gpa, ref.e_gpa))
    if not rows:
        ax.axis("off")
        ax.text(0, 0.75, ref.name, fontsize=10, fontweight="bold", transform=ax.transAxes)
        ax.text(0, 0.6, f"Rm {fmt(ref.rm, 0, 'MPa')} · Rp {fmt(ref.rp, 0, 'MPa') if ref.rp else '–'}\n"
                        f"A {fmt(ref.a_pct, 0, '%')} · E {fmt(ref.e_gpa, 1, 'GPa')}", fontsize=8.5,
                transform=ax.transAxes, va="top", linespacing=1.4)
        if r.ref_cmp and r.ref_cmp.get("A_needed_mm2"):
            txt = (f"Ohne A₀: bei Rm des Referenzwerkstoffs entspräche Fmax einer Fläche von "
                   f"{fmt(r.ref_cmp['A_needed_mm2'], 4, 'mm²')} (Rund-Ø {fmt(r.ref_cmp['d_equiv_mm'], 2, 'mm')}).")
            ax.text(0, 0.28, "\n".join(textwrap.wrap(txt, 40)), fontsize=8, color=MUTED,
                    transform=ax.transAxes, va="top", linespacing=1.35)
        return
    import numpy as np
    yv = np.arange(len(rows))
    rel = [m / ref_v * 100 for _, m, ref_v in rows]
    ax.barh(yv, [100] * len(rows), color="#e8eaed", height=0.55)
    ax.barh(yv, rel, color=[C.MARK["max"] if 80 <= v <= 120 else "#e8710a" for v in rel], height=0.3)
    for i, (lab, m, rv) in enumerate(rows):
        ax.text(max(rel[i], 100) + 3, i, f"{fmt(m, 1 if m < 100 else 0)} / {fmt(rv, 1 if rv < 100 else 0)}",
                va="center", fontsize=8)
    ax.set_yticks(yv)
    ax.set_yticklabels([lab for lab, _, _ in rows], fontsize=8)
    ax.axvline(100, color=C.REF_COLOR, lw=1.2)
    ax.set_xlim(0, max(max(rel), 100) * 1.45)
    ax.set_xlabel(f"Messung in % von {ref.name}", fontsize=8)
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    ax.xaxis.set_major_formatter(C.FuncFormatter(C._cf))


def _wrap_lines(text: str, width: int) -> list[str]:
    return textwrap.wrap(text, width=width) or [""]


UNC_SHOW = ("Rm", "Fmax", "sy", "E", "Agt", "A")


def _short(x: dict) -> str:
    """Ergebnistext ohne den Zusatz „(k = …; p ≈ …)“ bei GUM/Gauss; Intervalle (Monte Carlo, Grösstfehler) ganz."""
    t = x.get("text") or ""
    return t.split(" (")[0] if x.get("method") in ("gum", "gauss") else t


def _unc_line(r: Result):
    """Eine Zeile „Messunsicherheit“ für Seite 4: die wichtigsten Kennwerte mit ± (Budgets im Bericht für Folio)."""
    res = ((r.unc or {}).get("results") or {})
    if not res:
        return None
    meth = r.unc["settings"]["method"]
    parts = [f"{n} {_short(res[n])}" for n in UNC_SHOW
             if n in res and not res[n].get("error") and res[n].get("text")]
    if r.mode != "Spannung":
        parts = [p for p in parts if not p.startswith("Rm")]
    if not parts:
        return None
    name = {"gum": "GUM", "mc": "Monte Carlo", "gauss": "Gauss", "worst": "Grösstfehler"}.get(meth, meth)
    return (f"Messunsicherheit ({name})", "; ".join(parts) + ". Budgets nach ISO 6892-1 Anh. J im Bericht für Folio")


def _page_values(r: Result, nr, total):
    fig = _page("Kennwerte und Gültigkeit", _subline(r), nr, total, r.name)
    kv, st, u = r.kv, r.mode == "Spannung", r.unit
    rows = [("Messpunkte", f"{kv['n_total']} gesamt, {kv['n_active']} aktiv, {kv['n_cut']} abgeschnitten"),
            ("Abtastrate", fmt(kv["rate_hz"], 1, "Hz")),
            ("Querschnitt A₀", f"{fmt(r.a0, 4, 'mm²')} ({r.config.area_source()})" if r.a0 else "fehlt – nur Kraft"),
            ("Messlänge L₀ / Vorschub v", f"{fmt(r.l0, 1, 'mm') if r.l0 else '–'} / "
                                          f"{fmt(r.config.speed_mm_min, 2, 'mm/min') if r.config.speed_mm_min else 'nicht dokumentiert'}"),
            ("Fitfenster", f"{fmt(kv['fit']['t_von'], 1)} – {fmt(kv['fit']['t_bis'], 1, 's')}, n = {kv['fit']['n']}, "
                           f"R² = {fmt(kv['fit']['r2'], 5)}"),
            ("Ausgleichsgerade", f"{'σ' if st else 'F'} = {fmt(kv['fit']['k'], 3)}·t − {fmt(-kv['fit']['q'], 2)}, "
                                 f"grösste Abweichung {fmt(kv['fit']['max_dev'], 2, u)}"),
            ("Fusspunkt t₀", fmt(r.t0, 2, "s")),
            ("Fliessbeginn je Schwelle", " / ".join(f"{fmt(x['schwelle'] * 100, 1)} %: {fmt(x['y'], 0 if st else 1)}"
                                                    for x in r.yield_table if x["y"] is not None) + f" {u}"),
            ("Plateau-Mittel", fmt(kv["plateau"]["mittel"], 1, u)),
            ("Bruchdauer", kv["break_duration_text"])]
    if r.comparison:
        top = r.comparison["rows"][:3]
        rows.append((f"Kandidaten ({r.group})", ", ".join(x["name"] for x in top)))
    eqs = list(getattr(r, "equations", None) or [])
    for e in eqs[:5]:
        val = (e["text"] + (" " + e["unit"] if e.get("unit") else "")) if e.get("value") is not None else f"Fehler: {e.get('error')}"
        src = ""
        if e.get("source"):
            try:
                import labcite
                src = f" (nach {labcite.short(e['source'])})"
            except ImportError:
                src = ""
        rows.append((f"{e['sym'][:14]} (eigene Gl.)",
                     (f"{e['label']}: " if e.get("label") else "") + f"{e['sym']} = {e['expr']} = {val}{src}"))
    if len(eqs) > 5:
        rows.append(("Eigene Gleichungen", f"{len(eqs) - 5} weitere, vollständig im Bericht für Folio"))
    ur = _unc_line(r)
    if ur:
        rows.append(ur)
    ax = fig.add_axes([0.06, 0.52, 0.88, 0.39])
    ax.axis("off")
    y = 1.0
    for k, v in rows:
        ax.text(0, y, k, fontsize=9, color=MUTED, va="top", transform=ax.transAxes)
        for j, line in enumerate(_wrap_lines(v, 70)):
            ax.text(0.32, y - j * 0.045, line, fontsize=9, color=INK, va="top", transform=ax.transAxes)
        y -= 0.055 + 0.045 * (len(_wrap_lines(v, 70)) - 1)
        ax.plot([0, 1], [y + 0.012, y + 0.012], color="#e8eaed", lw=0.6, transform=ax.transAxes)
    _section(fig, 0.49, "Gültigkeit (Pflichthinweise, Abschnitt 7)")
    ax2 = fig.add_axes([0.06, 0.04, 0.88, 0.43])
    ax2.axis("off")
    y = 1.0
    colors = {"warn": "#8a4b00", "error": "#a50e0e", "info": "#2b4a7a"}
    for w in r.warnings:
        lines = _wrap_lines(w["text"], 105)
        ax2.text(0, y, w["code"], fontsize=8, fontweight="bold", color=colors.get(w["level"], INK), va="top",
                 transform=ax2.transAxes)
        for j, line in enumerate(lines):
            ax2.text(0.06, y - j * 0.028, line, fontsize=7.8, color=INK, va="top", transform=ax2.transAxes)
        y -= 0.028 * len(lines) + 0.014
    if r.comparison:
        ax2.text(0, y - 0.01, r.comparison["hinweis"], fontsize=7.8, color=MUTED, va="top", transform=ax2.transAxes,
                 style="italic")
    return fig


PEAK_ROWS = 22        # Zeilen der Spitzentabelle auf der Berichtsseite (alle stehen in der Arbeitsmappe)


def _fit_lines(r: Result) -> list[tuple[str, str, bool]]:
    """(Beschriftung, Text, besser?) der beiden Ausgleichsmodelle für die Berichtsseite."""
    pk = r.kv["peaks"]
    fit = pk.get("fit") or {}
    if fit.get("reason"):
        return [("Ausgleich", "entfällt: " + fit["reason"], False)]
    out = []
    for m in ("line", "exp"):
        d = fit.get(m)
        if not d:
            continue
        name = C.FIT_NAMES["de"][m]
        if not d.get("ok"):
            out.append((name, "nicht möglich: " + str(d.get("error")), False))
            continue
        par = []
        for p in ("a", "b"):
            v, u, ci, un = d[p], d[p + "_u"], d[p + "_ci"], d[p + "_unit"]
            nd = _nd_u(u, v)
            par.append(f"{p} = {fmt(v, nd)} ± {fmt(u, nd)} {un}".rstrip() + (f" (95 %: ± {fmt(ci, nd)})" if ci is not None else ""))
        txt = "; ".join(par) + f"; R² = {fmt(d['r2'], 4)}; n = {d['n']}"
        if not d.get("converged", True):
            txt += "; nicht konvergiert"
        out.append((name, txt, fit.get("best") == m))
    return out


def _nd_u(u, v) -> int:
    """Nachkommastellen: 2 geltende Ziffern der Unsicherheit, ohne Unsicherheit 4 geltende Ziffern des Werts."""
    import math
    ref, sig = (u, 2) if (u is not None and u > 0 and math.isfinite(u)) else (abs(v) if v else 1.0, 4)
    if not ref or not math.isfinite(ref):
        return 2
    return max(0, min(8, sig - 1 - int(math.floor(math.log10(ref)))))


def _page_peaks(r: Result, nr, total):
    """Lastspitzen: Verlauf mit Nummern, Spitzenlasten mit Ausgleich, Tabelle der Spitzen."""
    pk = r.kv["peaks"]
    fig = _page("Lastspitzen (fortschreitendes Versagen)", _subline(r), nr, total, r.name)
    ax = fig.add_axes([0.1, 0.66, 0.84, 0.25])
    C.peaks_curve(r, ax)
    ax.set_title(f"{pk['n']} Lastspitzen, Mindestabfall Δ = {fmt(pk['delta'], 2, r.unit)} "
                 f"({fmt(pk['frac'] * 100, 1)} % von {'Rm' if r.mode == 'Spannung' else 'Fmax'}"
                 + (", begrenzt durch 3 × Anzeigeauflösung" if pk["delta_basis"] == "aufloesung" else "") + ")",
                 loc="left", fontsize=10.5)
    ax = fig.add_axes([0.1, 0.40, 0.46, 0.2])
    C.peaks_fit_chart(r, ax)
    ax.set_title("Spitzenlast über " + ("Dehnung" if pk["x_kind"] == "strain" else
                                        "Traversenweg" if pk["x_kind"] == "travel" else "Zeit"),
                 loc="left", fontsize=10.5)
    y = 0.6
    fig.text(0.6, y, "Ausgleich der Spitzenlasten", fontsize=9.5, fontweight="bold", color=INK)
    y -= 0.022
    for lab, txt, best in _fit_lines(r):
        fig.text(0.6, y, lab + (" – besser" if best else ""), fontsize=8.2, color=INK,
                 fontweight="bold" if best else "normal")
        y -= 0.017
        for line in _wrap_lines(txt, 52):
            fig.text(0.6, y, line, fontsize=7.6, color=INK)
            y -= 0.015
        y -= 0.006
    note = ("Beide Modelle direkt nach kleinsten Quadraten in y; beide haben 2 Parameter, also entscheidet die kleinere "
            "Summe der Fehlerquadrate (das grössere R²). u: Standardunsicherheit; 95 %: Student-t mit n − 2 "
            "Freiheitsgraden.")
    for line in _wrap_lines(note, 58):
        fig.text(0.6, y, line, fontsize=7, color=MUTED)
        y -= 0.013
    # Tabelle der Spitzen
    tab = fig.add_axes([0.06, 0.08, 0.88, 0.27])
    tab.axis("off")
    st = r.mode == "Spannung"
    nd = 0 if st else 1
    xu = pk["x_unit"]
    has_w = any(e["W_J"] is not None for e in pk["list"])
    head = ["Nr.", "t [s]", f"x [{xu}]", f"{'σ' if st else 'F'} [{r.unit}]", "Tal [" + r.unit + "]", "Abfall [%]",
            "Dauer [s]", "F/F vorige", "k [N/s]"] + (["W [J]"] if has_w else [])
    cells = []
    for e in pk["list"][:PEAK_ROWS]:
        cells.append([str(e["nr"]) + ("*" if e.get("excluded") else ""), fmt(e["t"], 1), fmt(e["x"], 2 if xu != "s" else 1),
                      fmt(e["y"], nd + 1), fmt(e["valley_y"], nd + 1), fmt(e["drop_pct"], 1), fmt(e["dauer"], 1),
                      fmt(e["ratio"], 3), fmt(e["k_N_s"], 3)] + ([fmt(e["W_J"], 4)] if has_w else []))
    t = tab.table(cellText=cells, colLabels=head, loc="upper center", cellLoc="center")
    t.auto_set_font_size(False)
    t.set_fontsize(7)
    t.scale(1, 1.05 if len(cells) > 14 else 1.25)
    for (row, col), cell in t.get_celld().items():
        cell.set_edgecolor("#dadce0")
        if row == 0:
            cell.set_facecolor("#e8eaed")
            cell.set_text_props(fontweight="bold")
    foot = (f"Dauer ± ein Abtastintervall ({fmt(pk['dt'], 2, 's')}). k: Steigung des Wiederanstiegs zwischen 20 % und 80 % "
            "des Anstiegs vom vorigen Tal (erste Spitze: ab t₀). "
            + ("W: Arbeit vom vorigen Tal bis zum Tal nach der Spitze. " if has_w else "")
            + ("* nicht im Ausgleich. " if any(e.get("excluded") for e in pk["list"]) else "")
            + (f"Gezeigt {PEAK_ROWS} von {pk['n']} Spitzen, alle in der Arbeitsmappe. " if pk["n"] > PEAK_ROWS else "")
            + "Fmax ist die höchste Spitze; Haltezeit, Plateau und Bruch beziehen sich auf sie (Hinweis 4.9).")
    fig.text(0.06, 0.035, "\n".join(_wrap_lines(foot, 150)), fontsize=7, color=MUTED, va="bottom")
    return fig


def source_entries(r: Result) -> list[tuple[str, object]]:
    """(Nummer, Werkstoff) aller Vergleichswerte, die in den Diagrammen vorkommen: die Kurven des Felds
    (Nummern wie im Diagramm) und, falls ausserhalb der Gruppe, der Referenzwerkstoff (R)."""
    if not (r.mode == "Spannung" and r.comparison):
        return [("R", r.reference)] if r.reference is not None else []
    members = C.field_members(r)
    out = [(str(i), a) for i, a in enumerate(members, 1)]
    if r.reference is not None and all(a.name != r.reference.name for a in members):
        out.append(("R", r.reference))
    return out


_SRC_LH = 0.0122      # Zeilenhöhe (Anteil der Seitenhöhe) bei 7,5 pt


def _source_blocks(r: Result):
    blocks = []
    for nr, a in source_entries(r):
        vals = (f"Rp {fmt(a.rp, 0, 'MPa') if a.rp else '–'} · Rm {fmt(a.rm, 0, 'MPa')}"
                + (f" ({fmt(a.rm_min, 0)}–{fmt(a.rm_max, 0)})" if a.rm_min is not None and a.rm_max is not None else "")
                + f" · A {fmt(a.a_pct, 0, '%')} · E {fmt(a.e_gpa, 1, 'GPa')}"
                + (" · eigener Werkstoff" if getattr(a, "own", False) else "")
                + (" · Kurve aus der Quelle" if getattr(a, "curve", None) else ""))
        url = getattr(a, "url", "")
        yr = getattr(a, "year", "") if not getattr(a, "cite", None) else ""   # strukturierte Quelle enthält das Jahr
        src = _wrap_lines(f"Quelle: {a.source or 'nicht angegeben'}" + (f" ({yr})" if yr else "")
                          + (f" · Basis: {a.basis}" if a.basis else ""), 128)
        if url:
            src += _wrap_lines(url + (f" (abgerufen {a.accessed})" if getattr(a, "accessed", "") else ""), 128)
        blocks.append((nr, a, vals, src))
    return blocks


def _paginate_sources(blocks) -> list[list[tuple[float, tuple]]]:
    """Blöcke auf Seiten verteilen: [[(y, block), ...], ...]."""
    pages, y = [], 0.0
    for blk in blocks:
        need = (1.6 + len(blk[3])) * _SRC_LH
        if not pages or y - need < 0.05:
            pages.append([])
            y = 0.905 - (2 * _SRC_LH if len(pages) == 1 else 0)
        pages[-1].append((y, blk))
        y -= need
    return pages


def _source_pages_needed(r: Result) -> int:
    return len(_paginate_sources(_source_blocks(r)))


def _pages_sources(r: Result, first: int, total: int) -> list:
    """Quellen der Vergleichswerte: jede Kurve des Felds und der Referenzwerkstoff mit Kennwerten und Quelle."""
    pages = []
    for p, page in enumerate(_paginate_sources(_source_blocks(r))):
        fig = _page("Quellen der Vergleichswerte", _subline(r), first + p, total, r.name)
        pages.append(fig)
        if p == 0:
            fig.text(0.06, 0.905, "Nummern wie im Spannungs-Dehnungs-Feld. Die Kurven sind aus diesen Kennwerten idealisiert "
                                  "(Spezifikation 5.2), keine Messkurven.", fontsize=7.5, color=MUTED, va="top")
        for y, (nr, a, vals, src) in page:
            _source_block(fig, y, nr, a, vals, src)
    return pages


def _source_block(fig, y, nr, a, vals, src):
    fig.text(0.06, y, nr, fontsize=8, fontweight="bold", color=C.REF_COLOR if nr == "R" else INK, va="top")
    fig.text(0.1, y, a.name, fontsize=8, fontweight="bold", color=INK, va="top")
    fig.text(0.94, y, vals, fontsize=7.5, color=INK, va="top", ha="right")
    for j, line in enumerate(src):
        fig.text(0.1, y - (j + 1) * _SRC_LH, line, fontsize=7.2, color=MUTED, va="top")


def build_report(r: Result) -> list:
    has_cmp = r.mode == "Spannung" and r.comparison
    has_pk = C.has_peaks(r)
    n_src = _source_pages_needed(r)
    total = (4 if has_cmp else 3) + (1 if has_pk else 0) + n_src
    pages = []

    # ---- Seite 1 Übersicht
    fig = _page(f"Zugversuch {r.name}" if r.kv["test_type"] == "Zug" else f"Druckversuch {r.name}",
                _subline(r), 1, total, r.device["date"])
    tiles = _kpis(r)
    w, h, x0, y0 = 0.29, 0.065, 0.06, 0.845
    for i, (lab, val, sub, col, tag) in enumerate(tiles):
        ax = fig.add_axes([x0 + (i % 3) * (w + 0.005), y0 - (i // 3) * (h + 0.008), w, h])
        C.kpi_tile(ax, lab, val, sub, col, tag)
    ax = fig.add_axes([0.1, 0.43, 0.84, 0.31])
    C.chart1(r, ax, title=False)
    ax.set_title(f"{'Spannung' if r.mode == 'Spannung' else 'Zugkraft'} über Zeit", loc="left", fontsize=11)
    ax = fig.add_axes([0.1, 0.355, 0.84, 0.035])
    C.phase_timeline(r, ax)
    ax = fig.add_axes([0.06, 0.06, 0.46, 0.22])
    C.specimen_sketch(r, ax)
    ax.set_title("Probe", fontsize=10.5, loc="left")
    ax = fig.add_axes([0.66, 0.1, 0.29, 0.16])
    _ref_card(r, ax)
    note = _note_codes(r, ("7.3", "7.4", "7.5", "7.2", "7.6"))
    if note:
        fig.text(0.06, 0.04, note, fontsize=7.5, color=MUTED)
    pages.append(fig)

    # ---- Seite 2 Linearer Abschnitt (wie im Handbericht)
    fig = _page("Linearer Abschnitt und Fliessbeginn", _subline(r), 2, total, r.name)
    ax = fig.add_axes([0.1, 0.6, 0.84, 0.3])
    C.chart2_fit(r, ax, full=True)
    ax.set_title("Messpunkte gegen die verlängerte Ausgleichsgerade", loc="left", fontsize=11)
    ax = fig.add_axes([0.1, 0.33, 0.84, 0.2])
    C.chart2_dev(r, ax)
    ax.set_title("Abweichung der Messpunkte von der Geraden", loc="left", fontsize=11)
    ax = fig.add_axes([0.1, 0.1, 0.4, 0.165])
    C.yield_bars(r, ax)
    ax.set_title("Fliessbeginn je Schwelle", loc="left", fontsize=11)
    f = r.kv["fit"]
    txt = [("Fitfenster", f"{fmt(f['t_von'], 1)} – {fmt(f['t_bis'], 1, 's')}"), ("Messpunkte", str(f["n"])),
           ("Steigung", fmt(f["k_N_s"], 3, "N/s") + (f"\n= {fmt(f['k'], 2, 'MPa/s')}" if r.mode == "Spannung" else "")),
           ("R²", fmt(f["r2"], 5)), ("grösste Abw.", fmt(f["max_dev"], 2, r.unit)), ("Fusspunkt t₀", fmt(r.t0, 2, "s"))]
    yy = 0.25
    for k, v in txt:
        fig.text(0.6, yy, k, fontsize=8.5, color=MUTED)
        fig.text(0.76, yy, v, fontsize=9, color=INK, fontweight="bold", va="top" if "\n" in v else "baseline")
        yy -= 0.03 if "\n" not in v else 0.042
    fig.text(0.06, 0.038, "Die Schwelle ist eine Festlegung, keine Norm; der Fliessbeginn ist keine Rp0,2 (7.4).",
             fontsize=7.5, color=MUTED)
    pages.append(fig)

    # ---- Seite 3 Werkstoffvergleich
    if has_cmp:
        fig = _page(f"Werkstoffvergleich: {r.group}", _subline(r), 3, total, r.name)
        if r.strain is not None:
            numbered = len(r.alloys or []) <= C.NUMBER_MAX   # sonst: Werkstoffe nur auf den Quellenseiten
            ax = fig.add_axes([0.1, 0.6, 0.6 if numbered else 0.84, 0.3])
            C.chart3(r, ax, title=False, key="right" if numbered else "")
            ax.set_title("Spannungs-Dehnungs-Feld (idealisiert) mit Messkurve", loc="left", fontsize=11)
        else:
            fig.text(0.06, 0.75, "Spannungs-Dehnungs-Feld entfällt: Vorschubgeschwindigkeit oder L₀ fehlt.",
                     fontsize=9.5, color=MUTED)
        ax = fig.add_axes([0.3, 0.345, 0.64, 0.2])
        C.rm_strip(r, ax)
        ax.set_title("Einordnung nach Zugfestigkeit", loc="left", fontsize=11)
        ax = fig.add_axes([0.1, 0.11, 0.84, 0.17])
        C.chart4(r, ax, title=False)
        ax.set_title("Fliessbeginn und Zugfestigkeit der Kandidaten", loc="left", fontsize=11)
        fig.text(0.06, 0.035, "Kandidaten, keine Identifikation: eine Übereinstimmung in Rm allein bestimmt den "
                              "Werkstoff nicht. Kurven idealisiert, Quellen am Schluss.", fontsize=7.5, color=MUTED)
        pages.append(fig)

    # ---- Lastspitzen (nur bei fortschreitendem Versagen)
    if has_pk:
        pages.append(_page_peaks(r, len(pages) + 1, total))

    pages.append(_page_values(r, total - n_src, total))
    pages += _pages_sources(r, total - n_src + 1, total)
    return pages


def write_report(r: Result, folder: Path) -> Path:
    path = Path(folder) / f"{r.name}_Bericht.pdf"
    pages = build_report(r)
    with PdfPages(path, metadata={"Title": f"Grafischer Bericht {r.name}", "Creator": "FLPS Auswerte-App"}) as pdf:
        for fig in pages:
            pdf.savefig(fig)
            plt.close(fig)
    return path


# --------------------------------------------------------------------------- Vergleichsbericht
def write_comparison_report(results: list[Result], path: Path) -> Path:
    """Mehrere Messungen auf einer Seite: Überlagerung, Kennzahlen nebeneinander, Tabelle."""
    fig = build_comparison(results)
    names = ", ".join(r.name for r in results)
    path = Path(path)
    with PdfPages(path, metadata={"Title": f"Vergleich {names}", "Creator": "FLPS Auswerte-App"}) as pdf:
        pdf.savefig(fig)
        plt.close(fig)
    return path


def _series_line(results: list[Result]) -> str:
    """Serie mit Messunsicherheit: Mittelwert ± U je Kennwert (Typ A aus der Streuung, flps/uncertainty.series)."""
    if not any(r.unc for r in results):
        return ""
    try:
        from .. import uncertainty as UNC
        ser = UNC.series(results, "de")
    except ImportError:
        return ""
    parts = [f"{n} {_short(ser[n])}" for n in UNC_SHOW if n in ser and ser[n].get("text")]
    if not parts:
        return ""
    n = next(iter(ser.values()))["n"]
    return f"Serie (n = {n}, Mittelwert, Typ A aus der Streuung plus mittleres Einzelbudget): " + "; ".join(parts) + "."


def build_comparison(results: list[Result]):
    names = ", ".join(r.name for r in results)
    modes = {r.mode for r in results}
    if len(modes) > 1:
        raise ValueError("Messungen in Kraft und in Spannung lassen sich nicht in einem Bericht vergleichen. "
                         "A₀ für alle Messungen eingeben oder bei allen leer lassen.")
    fig = _page("Vergleich der Messungen", names, 1, 1, datetime.now().strftime("%d.%m.%Y"))
    ax = fig.add_axes([0.1, 0.63, 0.84, 0.27])
    C.overlay_time(results, ax)
    ax.set_title("Verlauf über Zeit", loc="left", fontsize=11)
    has_eps = any(r.strain is not None and r.mode == "Spannung" for r in results)
    if has_eps:
        ax = fig.add_axes([0.1, 0.37, 0.4, 0.2])
        C.overlay_strain(results, ax)
        ax.set_title("Spannung über Dehnung", loc="left", fontsize=11)
        ax = fig.add_axes([0.58, 0.37, 0.36, 0.2])
    else:
        ax = fig.add_axes([0.1, 0.37, 0.84, 0.2])
    C.grouped_kpis(results, ax)
    ax.set_title("Kennwerte", loc="left", fontsize=11)
    # Tabelle
    tab = fig.add_axes([0.06, 0.06, 0.88, 0.25])
    tab.axis("off")
    st = results[0].mode == "Spannung"
    u = results[0].unit
    head = ["Messung", "A₀ [mm²]", f"Fliessb. [{u}]", f"Max [{u}]", f"vor Bruch [{u}]", "Abfall [%]",
            "Haltezeit [s]", "E schein. [GPa]"]
    cells = []
    for r in results:
        kv = r.kv
        nd = 0 if st else 1
        cells.append([r.name, fmt(r.a0, 4) if r.a0 else "–", fmt(kv["yield"]["y"], nd) if kv["yield"] else "–",
                      fmt(kv["max"]["y"], nd), fmt(kv["break"]["y"], nd) if kv["break"] else "–",
                      fmt(kv["drop"]["pct"], 1) if kv["drop"] else "–", fmt(kv["hold"]["dauer"], 1),
                      fmt(r.e_schein_gpa, 1) if r.e_schein_gpa is not None else "–"])
    widths = [0.24] + [0.76 / (len(head) - 1)] * (len(head) - 1)
    head = [h.replace(" [", "\n[") for h in head]
    t = tab.table(cellText=cells, colLabels=head, loc="upper center", cellLoc="center", colWidths=widths)
    t.auto_set_font_size(False)
    t.set_fontsize(7.5)
    t.scale(1, 1.4)
    for (row, col), cell in t.get_celld().items():
        if row == 0:
            cell.set_height(cell.get_height() * 1.6)
    for (row, col), cell in t.get_celld().items():
        cell.set_edgecolor("#dadce0")
        if row == 0:
            cell.set_facecolor("#e8eaed")
            cell.set_text_props(fontweight="bold")
        elif col == 0:
            cell.set_text_props(color=C.FILE_COLORS[(row - 1) % len(C.FILE_COLORS)], fontweight="bold")
    codes = sorted({w["code"] for r in results for w in r.warnings})
    foot = ("Hinweise je Messung im jeweiligen Einzelbericht (" + ", ".join(codes) + "). "
            + ("Dehnung scheinbar (Traversenweg). " if has_eps else "")
            + "Gleiche Schwellen und Kriterien vorausgesetzt.")
    ser = _series_line(results)
    if ser:
        foot += " " + ser
    fig.text(0.06, 0.04, "\n".join(textwrap.wrap(foot, 135)), fontsize=7.5, color=MUTED, va="bottom")
    return fig
