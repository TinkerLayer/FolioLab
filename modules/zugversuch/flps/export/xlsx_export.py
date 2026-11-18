"""Arbeitsmappe (Spezifikation 6.2): Messdaten, Uebersicht mit Formeln, Diagramm.

Jeder Kennwert steht als Formel auf das Blatt Messdaten. Nach dem Schreiben wird die Mappe
neu berechnet; liefert eine Formel einen Fehlerwert, wird die Mappe nicht ausgeliefert.
"""
from __future__ import annotations

import math
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.chart import Reference, ScatterChart, Series
from openpyxl.chart.label import DataLabelList
from openpyxl.chart.series import SeriesLabel, StrRef
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from ..analyse import PHASES, Result
from .xlcalc import Book

YELLOW = PatternFill("solid", fgColor="FFF2A8")
HEAD = PatternFill("solid", fgColor="E8EAED")
INPUT = PatternFill("solid", fgColor="E8F0FE")
BOLD = Font(bold=True)
NOTE = Font(italic=True, color="5F6368", size=9)
THIN = Border(bottom=Side(style="thin", color="BDC1C6"))
PHASE_COLORS = ["9AA0A6", "1A73E8", "E8710A", "D93025"]
Q = "'Übersicht'!"
M = "Messdaten!"


class WorkbookError(Exception):
    pass


def write_xlsx(r: Result, folder: Path) -> Path:
    path = folder / f"{r.name}.xlsx"
    wb = Workbook()
    ws_d = wb.active
    ws_d.title = "Messdaten"
    ws_o = wb.create_sheet("Übersicht")
    ws_c = wb.create_sheet("Diagramm")
    p = r.prep
    N = p.n_total
    last = N + 1                       # letzte Datenzeile
    stress = r.mode == "Spannung"
    has_eps = bool(r.v_mm_s and r.l0)

    # ------------------------------------------------------------------ Übersicht
    cells: dict[str, str] = {}
    row = [1]

    def title(text):
        rr = row[0]
        ws_o.cell(rr, 1, text).font = Font(bold=True, size=12)
        ws_o.cell(rr, 1).fill = HEAD
        for c in range(2, 5):
            ws_o.cell(rr, c).fill = HEAD
        row[0] += 1

    def put(key, label, value, unit="", note="", key_value=False, inp=False, fmt=None):
        rr = row[0]
        ws_o.cell(rr, 1, label)
        c = ws_o.cell(rr, 2, value)
        if fmt:
            c.number_format = fmt
        ws_o.cell(rr, 3, unit)
        if note:
            ws_o.cell(rr, 4, note).font = NOTE
        if key_value:
            c.fill = YELLOW
            c.font = BOLD
        elif inp:
            c.fill = INPUT
        for col in range(1, 5):
            ws_o.cell(rr, col).border = THIN
        if key:
            cells[key] = f"{Q}$B${rr}"
        row[0] += 1
        return f"$B${rr}"

    def ref(key):
        return cells[key]

    rng = lambda col: f"{M}${col}$2:${col}${last}"  # noqa: E731

    ws_o.cell(1, 1, f"Übersicht {r.name}").font = Font(bold=True, size=14)
    ws_o.cell(2, 1, "Gelb: Schlüsselwerte. Blau: Eingaben, änderbar; die Mappe rechnet neu.").font = NOTE
    row[0] = 4
    d = r.device
    title("Gerät")
    put(None, "Gerätemodell", d["model"])
    put(None, "Seriennummer", d["serial"])
    put(None, "Quelldatei", r.source)
    put(None, "Zeitraum", f"{d['start']} bis {d['end']}")
    put(None, "Krafteinheit", d["force_unit"], "", "bestätigt" if d["force_unit_confirmed"] else "unbestätigt")
    put(None, "Wegeinheit", d["displacement_unit"], "", "unbestätigt (aus einer Datei abgeleitet)")
    put("n_total", "Messpunkte gesamt", f"=COUNT({rng('A')})")
    put(None, "Versuchsart", p.test_type, "", "aus dem Vorzeichen der Maximalkraft")

    cfg = r.config
    row[0] += 1
    title("Probe und Prüfbedingungen (Eingaben)")
    put(None, "Probenform", cfg.shape)
    put(None, "Querschnitt", cfg.section)
    put(None, "Stegbreite b", cfg.width_mm, "mm", inp=True)
    put(None, "Dicke", cfg.thickness_mm, "mm", inp=True)
    if cfg.section == "rund":
        put(None, "Durchmesser d", cfg.diameter_mm, "mm", inp=True)
    if cfg.section == "rohr":
        put(None, "Aussendurchmesser D", cfg.outer_d_mm, "mm", inp=True)
        put(None, "Wanddicke t", cfg.wall_mm, "mm", inp=True)
    put(None, "Abmessungen", "manuell" if cfg.specimen_mode == "manuell" else "Normprobe")
    if stress:
        put("A0", "Querschnittsfläche A0", r.a0, "mm²", f"{r.config.area_source()}; jede Spannung hängt direkt daran",
            key_value=True, fmt="0.0000")
    else:
        put(None, "Querschnittsfläche A0", "fehlt", "mm²", "ohne A0 keine Spannung (7.1)")
    put("L0", "Messlänge L0", r.l0, "mm", inp=True)
    put("v", "Vorschubgeschwindigkeit v", cfg.speed_mm_min, "mm/min",
        "" if cfg.speed_mm_min else "fehlt: keine Dehnung, kein Modul (7.5)", inp=True)
    put(None, "Weg gemessen", {"probe": "an der Probe", "traverse": "Traversenweg"}.get(cfg.displacement_source or "", "nicht angegeben"))
    put(None, "Werkstoff", cfg.material)
    if r.reference is not None:
        rw = r.reference
        put(None, "Referenzwerkstoff", rw.name, "",
            f"{rw.category}; Rm {rw.rm:g} MPa, Rp {rw.rp if rw.rp else '–'} MPa, E {rw.e_gpa:g} GPa; {rw.basis}; {rw.source}")
    put(None, "Vergleichsgruppe", r.group)
    put(None, "Charge", cfg.batch)
    put(None, "Prüfer", cfg.operator)
    put(None, "Bemerkung", cfg.remark)

    row[0] += 1
    title("Auswerteparameter")
    put("thr", "Schwelle Fliessbeginn", cfg.yield_threshold, "", "Festlegung, keine Norm (7.4)", inp=True, fmt="0.0%")
    put("bu", "Bruchkriterium oben", cfg.break_upper, "", "Vorgänger darüber gilt als belastet", inp=True, fmt="0%")
    put("bl", "Bruchkriterium unten", cfg.break_lower, "", "Wert darunter gilt als entlastet", inp=True, fmt="0%")
    put("hold", "Haltezeitschwelle", cfg.hold_threshold, "", "", inp=True, fmt="0%")
    put("lo", "Fitfenster ab Index", r.fit.lo, "", "aus dem App-Algorithmus 4.2 übernommen", inp=True)
    put("hi", "Fitfenster bis Index", r.fit.hi, "", "aus dem App-Algorithmus 4.2 übernommen", inp=True)

    lo_row, hi_row = r.fit.lo + 2, r.fit.hi + 2
    u = r.unit
    yname = "σ" if stress else "|F|"

    row[0] += 1
    title("Kennwerte (Formeln auf Messdaten)")
    put("Fref", "Bezug Bruchkriterien (grösste Kraft)", f"=MAX({rng('F')})", "N", fmt="0.0")
    if r.drop_idx is not None:
        put("pos_drop", "Position Lastabfall in Messdaten", f"=MATCH(1,{rng('K')},0)", "", "Zeile = Position + 1")
        put("n_active", "Messpunkte aktiv", f"={ref('pos_drop')}", "", "bis einschliesslich erstem Punkt des Lastabfalls")
    else:
        put("n_active", "Messpunkte aktiv", f"={ref('n_total')}", "", "kein Bruch erkannt")
    put(None, "Messpunkte abgeschnitten", f"={ref('n_total')}-{ref('n_active')}")
    put("rate", "Abtastrate", f"=({ref('n_active')}-1)/INDEX({rng('D')},{ref('n_active')})", "Hz", fmt="0.0")
    put("Ymax", "Zugfestigkeit Rm" if stress else "Maximalkraft Fmax", f"=MAX({rng('L')})", u, key_value=True,
        fmt="0.0")
    put("Fmax", "Maximalkraft Fmax", f"=MAX({rng('F')})", "N", fmt="0.0")
    put("imax", "Index Maximum", f"=MATCH({ref('Fmax')},{rng('F')},0)-1")
    put("tmax", "Zeit Maximum", f"=INDEX({rng('D')},{ref('imax')}+1)", "s", fmt="0.0")
    put("k", "Steigung k linearer Abschnitt", f"=SLOPE({M}$L${lo_row}:$L${hi_row},{M}$D${lo_row}:$D${hi_row})",
        f"{u}/s", key_value=True, fmt="0.000")
    put("q", "Achsenabschnitt q", f"=INTERCEPT({M}$L${lo_row}:$L${hi_row},{M}$D${lo_row}:$D${hi_row})", u, fmt="0.00")
    put("r2", "Bestimmtheitsmass R²", f"=RSQ({M}$L${lo_row}:$L${hi_row},{M}$D${lo_row}:$D${hi_row})", fmt="0.00000")
    put("dev", "Grösste Abweichung im Fenster",
        f"=MAX(MAX({M}$M${lo_row}:$M${hi_row}),-MIN({M}$M${lo_row}:$M${hi_row}))", u, fmt="0.00")
    put("t_lo", "Fitfenster Beginn", f"=INDEX({rng('D')},{ref('lo')}+1)", "s", fmt="0.0")
    put("t_hi", "Fitfenster Ende", f"=INDEX({rng('D')},{ref('hi')}+1)", "s", fmt="0.0")
    put("t0", "Fusspunkt t0", f"=-{ref('q')}/{ref('k')}", "s", "Schnitt der Geraden mit der Nulllinie", fmt="0.00")
    if r.yield_idx is not None:
        put("pos_y", "Position Fliessbeginn", f"=MATCH(1,{rng('N')},0)")
        put("Yy", f"{'Spannung' if stress else 'Kraft'} bei Fliessbeginn", f"=INDEX({rng('L')},{ref('pos_y')})", u,
            "Schwelle auf der Kraftkurve, keine Rp0,2 (7.4)", key_value=True, fmt="0.0")
        put("Fy", "Kraft bei Fliessbeginn", f"=INDEX({rng('F')},{ref('pos_y')})", "N", fmt="0.0")
        put("ty", "Zeit Fliessbeginn", f"=INDEX({rng('D')},{ref('pos_y')})", "s", fmt="0.0")
        put("ratio", "Verhältnis Rm zu Streckgrenze" if stress else "Verhältnis Fmax zu Fliessbeginn",
            f"={ref('Ymax')}/{ref('Yy')}", "", "Mass der Verfestigung", fmt="0.00")
    if r.drop_idx is not None:
        put("Yb", f"{'Spannung' if stress else 'Kraft'} vor dem Bruch", f"=INDEX({rng('L')},{ref('pos_drop')}-1)", u,
            key_value=True, fmt="0.0")
        put("Fb", "Bruchkraft", f"=INDEX({rng('F')},{ref('pos_drop')}-1)", "N", fmt="0.0")
        put("tb", "Zeit Bruch", f"=INDEX({rng('D')},{ref('pos_drop')}-1)", "s", fmt="0.0")
        put(None, "Abfall Maximum bis Bruch", f"={ref('Ymax')}-{ref('Yb')}", u, fmt="0.0")
        put(None, "Abfall in Prozent", f"=({ref('Ymax')}-{ref('Yb')})/{ref('Ymax')}*100", "%", fmt="0.0")
        put(None, "Dauer des Abfalls", f"={ref('tb')}-{ref('tmax')}", "s",
            "Abschnitt «Einschnürung» ist nicht belegt, nur die Bruchfläche entscheidet (7.3)", fmt="0.0")
        put(None, "Bruchdauer", f"=\"< \"&FIXED(1/{ref('rate')},1)&\" s\"", "",
            "bei dieser Abtastrate nicht aufgelöst (7.7)")
    put("holdt", "Haltezeit über Haltezeitschwelle", f"=MAX({rng('O')})-MIN({rng('O')})", "s", fmt="0.0")
    put(None, "Plateau-Mittelwert 80–100 % der Zeit bis Maximum",
        f"=AVERAGEIFS({rng('L')},{rng('D')},\">=\"&0.8*{ref('tmax')},{rng('D')},\"<=\"&{ref('tmax')})", u, fmt="0.0")
    if stress and r.v_mm_s and r.l0:
        put("E", "Elastizitätsmodul, scheinbar", f"={ref('k')}*{ref('L0')}/({ref('v')}/60)/1000", "GPa",
            "scheinbar: Traversenweg enthält Nachgiebigkeit von Einspannung und Rahmen (7.2). "
            "E = k · (1/v) · (L0/A0)" if cfg.displacement_source != "probe" else "E = k · (1/v) · (L0/A0)",
            key_value=True, fmt="0.0")
    else:
        put(None, "Elastizitätsmodul, scheinbar", "entfällt", "",
            "es fehlen: " + ", ".join(x for x, ok in (("A0", stress), ("v", r.v_mm_s), ("L0", r.l0)) if not ok))

    row[0] += 1
    title("Hinweise (Abschnitt 7)")
    for w in r.warnings:
        ws_o.cell(row[0], 1, f"[{w['code']}]").font = NOTE
        c = ws_o.cell(row[0], 2, w["text"])
        c.font = NOTE
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ws_o.merge_cells(start_row=row[0], start_column=2, end_row=row[0], end_column=4)
        ws_o.row_dimensions[row[0]].height = 15 * max(1, math.ceil(len(w["text"]) / 110))
        row[0] += 1

    ws_o.column_dimensions["A"].width = 42
    ws_o.column_dimensions["B"].width = 22
    ws_o.column_dimensions["C"].width = 9
    ws_o.column_dimensions["D"].width = 70

    # ------------------------------------------------------------------ Messdaten
    heads = ["Index", "Zeitstempel", "Zeit grob [s]", "Zeit fein [s]", "Kraft mit Vorzeichen [N]", "Kraft Betrag [N]",
             "Spannung [MPa]" if stress else "Spannung [MPa] (A0 fehlt)",
             ("Dehnung scheinbar [%]" if cfg.displacement_source != "probe" else "Dehnung [%]") if has_eps
             else "Dehnung [%] (v oder L0 fehlt)",
             f"Weg [{d['displacement_unit']}]", "Phase", "Lastabfall-Marke", f"Auswertegrösse {yname} [{u}]",
             f"Abweichung Gerade − {yname} [{u}]", "Fliessmarke", "Zeit über Haltezeitschwelle [s]"]
    for i, h in enumerate(heads, 1):
        c = ws_d.cell(1, i, h)
        c.font = BOLD
        c.fill = HEAD
        c.alignment = Alignment(wrap_text=True, vertical="top")
    ws_d.row_dimensions[1].height = 45
    for i in range(N):
        rr = i + 2
        ws_d.cell(rr, 1, i)
        ws_d.cell(rr, 2, p.timestamps[i]).number_format = "DD.MM.YYYY HH:MM:SS"
        ws_d.cell(rr, 3, float(p.t_coarse[i]))
        ws_d.cell(rr, 4, round(float(p.t_fine[i]), 6))
        ws_d.cell(rr, 5, float(p.force_raw[i]))
        ws_d.cell(rr, 6, f"=ABS(E{rr})")
        if stress:
            ws_d.cell(rr, 7, f"=F{rr}/{ref('A0')}").number_format = "0.00"
        if has_eps:
            ws_d.cell(rr, 8, f"=(D{rr}-{ref('t0')})*({ref('v')}/60)/{ref('L0')}*100").number_format = "0.000"
        ws_d.cell(rr, 9, float(p.displacement[i]))
        ws_d.cell(rr, 10, PHASES[int(r.phases[i])])
        if rr == 2:
            ws_d.cell(rr, 11, 0)
        else:
            ws_d.cell(rr, 11, f"=IF(AND(F{rr - 1}>{ref('bu')}*{ref('Fref')},F{rr}<{ref('bl')}*{ref('Fref')}),1,0)")
        ws_d.cell(rr, 12, f"=G{rr}" if stress else f"=F{rr}")
        ws_d.cell(rr, 13, f"={ref('k')}*D{rr}+{ref('q')}-L{rr}").number_format = "0.000"
        ws_d.cell(rr, 14, f"=IF(AND(A{rr}>{ref('hi')},M{rr}>{ref('thr')}*{ref('Ymax')}),1,0)")
        ws_d.cell(rr, 15, f"=IF(L{rr}>={ref('hold')}*{ref('Ymax')},D{rr},\"\")")
    for i, w in enumerate([7, 20, 9, 10, 12, 11, 11, 12, 8, 12, 10, 12, 13, 9, 13], 1):
        ws_d.column_dimensions[get_column_letter(i)].width = w
    ws_d.freeze_panes = "A2"

    # ------------------------------------------------------------------ Diagramm
    n_act = r.prep.n_active
    ph = r.phases[:n_act]
    ws_c.cell(1, 16, "Legendentexte (Formeln)").font = BOLD
    leg_row = 2
    seg_rows = []
    phase_end_t = {0: "t_lo", 1: "ty" if r.yield_idx is not None else "tmax", 2: "tmax", 3: "tb" if r.drop_idx is not None else None}
    for code in range(4):
        idx = [i for i in range(n_act) if ph[i] == code]
        if not idx:
            continue
        lo_i, hi_i = idx[0], min(idx[-1] + 1, n_act - 1)
        name = PHASES[code] if code != 3 else "Abfall (Einschnürung nicht belegt)"
        key = phase_end_t.get(code)
        if key and key in cells:
            ws_c.cell(leg_row, 16, f"=\"{name} bis \"&FIXED({ref(key)},1)&\" s\"")
        else:
            ws_c.cell(leg_row, 16, name)
        seg_rows.append((code, lo_i, hi_i, leg_row))
        leg_row += 1

    ch = ScatterChart()
    ch.title = f"{'Spannungs' if stress else 'Kraft'}-Zeit-Verlauf {r.name}"
    ch.style = 13
    ch.x_axis.title = "Zeit t [s]"
    ch.y_axis.title = "Spannung σ [MPa]" if stress else "Kraft |F| [N]"
    ch.x_axis.delete = False
    ch.y_axis.delete = False
    ch.height, ch.width = 12, 24
    ch.legend.position = "b"
    for code, lo_i, hi_i, lr in seg_rows:
        xs = Reference(ws_d, min_col=4, min_row=lo_i + 2, max_row=hi_i + 2)
        ys = Reference(ws_d, min_col=12, min_row=lo_i + 2, max_row=hi_i + 2)
        s = Series(ys, xs)
        s.tx = SeriesLabel(strRef=StrRef(f"'Diagramm'!$P${lr}"))
        s.marker.symbol = "none"
        s.smooth = False
        s.graphicalProperties.line.solidFill = PHASE_COLORS[code]
        s.graphicalProperties.line.width = 22000
        ch.series.append(s)
    marks = []
    if r.yield_idx is not None:
        marks.append(("ty", "Yy", f"Fliessbeginn ({cfg.yield_threshold * 100:g} %) ", "188038"))
    marks.append(("tmax", "Ymax", "Maximum ", "D93025"))
    if r.drop_idx is not None:
        marks.append(("tb", "Yb", "Bruch ", "202124"))
    for tk, yk, label, color in marks:
        ws_c.cell(leg_row, 16, f"=\"{label}\"&FIXED({ref(yk)},1)&\" {u}\"")
        o_row_t = int(cells[tk].split("$")[-1])
        o_row_y = int(cells[yk].split("$")[-1])
        xs = Reference(ws_o, min_col=2, min_row=o_row_t, max_row=o_row_t)
        ys = Reference(ws_o, min_col=2, min_row=o_row_y, max_row=o_row_y)
        s = Series(ys, xs)
        s.tx = SeriesLabel(strRef=StrRef(f"'Diagramm'!$P${leg_row}"))
        s.marker.symbol = "circle"
        s.marker.size = 9
        s.marker.graphicalProperties.solidFill = color
        s.marker.graphicalProperties.line.solidFill = color
        s.graphicalProperties.line.noFill = True
        s.dLbls = DataLabelList()
        s.dLbls.showVal = True
        s.dLbls.showSerName = False
        s.dLbls.showCatName = False
        s.dLbls.showLegendKey = False
        s.dLbls.position = "t"
        ch.series.append(s)
        leg_row += 1
    ws_c.add_chart(ch, "A1")

    t0r = 27
    ws_c.cell(t0r, 1, "Phasentabelle").font = Font(bold=True, size=12)
    hdr = ["Phase", "von Zeile", "bis Zeile", "von Index", "bis Index", "von t [s]", "bis t [s]"]
    for i, h in enumerate(hdr, 1):
        c = ws_c.cell(t0r + 1, i, h)
        c.font = BOLD
        c.fill = HEAD
    rr = t0r + 2
    for b in r.phase_bounds():
        vals = [b["phase"], b["von"] + 2, b["bis"] + 2, b["von"], b["bis"]]
        for i, v in enumerate(vals, 1):
            ws_c.cell(rr, i, v)
        ws_c.cell(rr, 6, f"=Messdaten!D{b['von'] + 2}").number_format = "0.0"
        ws_c.cell(rr, 7, f"=Messdaten!D{b['bis'] + 2}").number_format = "0.0"
        rr += 1
    ws_c.cell(rr + 1, 1, "Phasengrenzen elastisch/plastisch stammen aus der gesetzten Schwelle (7.4).").font = NOTE
    ws_c.column_dimensions["A"].width = 30
    ws_c.column_dimensions["P"].width = 40

    wb.calculation.fullCalcOnLoad = True
    tmp = path.with_suffix(".tmp.xlsx")
    wb.save(tmp)

    # ------------------------------------------------------------------ Neuberechnung und Pruefung
    try:
        check = load_workbook(tmp)
        book = Book(check)
        errors = book.check_all()
        if errors:
            raise WorkbookError("Formeln mit Fehlerwert: " + ", ".join(f"{s}!{c} {e}" for s, c, e in errors[:10]))
        expect = {"Ymax": float(r.y[r.imax]), "k": r.fit.k, "r2": r.fit.r2, "t0": r.t0,
                  "holdt": r.kv["hold"]["dauer"], "n_active": r.prep.n_active}
        if r.yield_idx is not None:
            expect["Yy"] = float(r.y[r.yield_idx])
        if r.drop_idx is not None:
            expect["Yb"] = float(r.y[r.break_idx])
        if r.e_schein_gpa is not None and "E" in cells:
            expect["E"] = r.e_schein_gpa
        for key, val in expect.items():
            got = book.ref("Übersicht", cells[key])
            if not isinstance(got, (int, float)) or abs(got - val) > 1e-6 * max(1.0, abs(val)):
                raise WorkbookError(f"Formel {key} liefert {got}, App rechnet {val}")
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    if path.exists():
        path.unlink()
    tmp.rename(path)
    return path
