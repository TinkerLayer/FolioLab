"""PDF-Ausgaben (Spezifikation 6.4 Datenblatt und 6.5 Bildanhang).

Verwendet DejaVu Sans (aus matplotlib, voller Unicode-Umfang: σ, ε, ², Ω, tiefgestellte Ziffern).
"""
from __future__ import annotations

import io
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (KeepInFrame, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)

from ..analyse import Result, fmt
from . import charts

_FONT_OK = False


def _fonts():
    global _FONT_OK
    if _FONT_OK:
        return
    base = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
    pdfmetrics.registerFont(TTFont("DejaVu", str(base / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(base / "DejaVuSans-Bold.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVu-Oblique", str(base / "DejaVuSans-Oblique.ttf")))
    from reportlab.pdfbase.pdfmetrics import registerFontFamily
    registerFontFamily("DejaVu", normal="DejaVu", bold="DejaVu-Bold", italic="DejaVu-Oblique",
                       boldItalic="DejaVu-Bold")
    _FONT_OK = True


def _styles():
    _fonts()
    return {
        "h1": ParagraphStyle("h1", fontName="DejaVu-Bold", fontSize=14, leading=17, spaceAfter=2),
        "h2": ParagraphStyle("h2", fontName="DejaVu-Bold", fontSize=9.5, leading=12, spaceBefore=5, spaceAfter=2,
                             textColor=colors.HexColor("#1A73E8")),
        "p": ParagraphStyle("p", fontName="DejaVu", fontSize=7.8, leading=10, alignment=TA_LEFT),
        "small": ParagraphStyle("s", fontName="DejaVu", fontSize=6.9, leading=8.6, textColor=colors.HexColor("#3C4043")),
        "cell": ParagraphStyle("c", fontName="DejaVu", fontSize=7.6, leading=9.4),
        "cellb": ParagraphStyle("cb", fontName="DejaVu-Bold", fontSize=7.6, leading=9.4),
    }


def _tbl(data, widths, st, head=True, key_rows=()):
    S = st["cell"]
    rows = [[c if isinstance(c, Paragraph) else Paragraph(str(c), st["cellb"] if (head and i == 0) else S)
             for c in row] for i, row in enumerate(data)]
    t = Table(rows, colWidths=widths, hAlign="LEFT")
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#DADCE0")),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    if head:
        style.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EAED")))
    for k in key_rows:
        style.append(("BACKGROUND", (0, k), (-1, k), colors.HexColor("#FFF2A8")))
    t.setStyle(TableStyle(style))
    return t


def write_datasheet(r: Result, folder: Path) -> Path:
    st = _styles()
    path = folder / f"{r.name}_Datenblatt.pdf"
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm,
                            title=f"Datenblatt {r.name}", author="FLPS Auswerte-App")
    W = A4[0] - 28 * mm
    kv, d, cfg = r.kv, r.device, r.config
    stress = r.mode == "Spannung"
    u = r.unit
    story = []
    art = "Zugversuch" if kv["test_type"] == "Zug" else "Druckversuch"
    story.append(Paragraph(f"Datenblatt {art} – {r.name}", st["h1"]))

    # Kopf
    src = {"probe": "an der Probe", "traverse": "Traversenweg"}.get(cfg.displacement_source or "", "nicht angegeben")
    left = [["Gerät", f"{d['model']}, SN {d['serial']}"],
            ["Zeitraum", f"{d['start']} – {d['end'][-8:]}"],
            ["Krafteinheit", f"{d['force_unit']} ({'bestätigt' if d['force_unit_confirmed'] else 'unbestätigt'})"],
            ["Messpunkte", f"{kv['n_total']} gesamt, {kv['n_active']} aktiv, {kv['n_cut']} abgeschnitten"],
            ["Abtastrate", fmt(kv["rate_hz"], 1, "Hz")],
            ["Versuchsart", f"{kv['test_type']} (aus Vorzeichen der Maximalkraft)"]]
    from ..analyse import material_label, specimen_label
    geo = specimen_label(r)
    right = [["Probe", geo],
             ["A₀", fmt(r.a0, 4, "mm²") + f" ({cfg.area_source()})" if r.a0 else "fehlt – keine Spannungen"],
             ["L₀", fmt(r.l0, 1, "mm") if r.l0 else "fehlt"],
             ["Vorschub v", f"{fmt(cfg.speed_mm_min, 2, 'mm/min')}" if cfg.speed_mm_min else "nicht dokumentiert"],
             ["Weg", src],
             ["Werkstoff / Charge", f"{material_label(r) or '–'} / {cfg.batch or '–'}"],
             ["Vergleichsgruppe", r.group],
             ["Prüfer", cfg.operator or "–"]]
    if cfg.remark:
        right.append(["Bemerkung", cfg.remark])
    tl = _tbl(left, [24 * mm, W / 2 - 26 * mm], st, head=False)
    tr = _tbl(right, [26 * mm, W / 2 - 26 * mm], st, head=False)
    head = Table([[tl, tr]], colWidths=[W / 2, W / 2])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(head)

    # Kennwerte
    story.append(Paragraph("Kennwerte", st["h2"]))
    thr = fmt(cfg.yield_threshold * 100, 1, "%")

    def sig(v):
        return fmt(v / r.a0, 0) if (stress and v is not None) else "–"

    rows = [["Grösse", "Kraft [N]", "Spannung [MPa]", "Zeit [s]", "Messpunkt"]]
    keys = []
    if kv["yield"]:
        y = kv["yield"]
        rows.append([f"Fliessbeginn (Schwelle {thr}, keine Rp0,2)", fmt(y["F"], 1), sig(y["F"]), fmt(y["t"], 1), y["idx"]])
        keys.append(len(rows) - 1)
    m = kv["max"]
    rows.append(["Maximalkraft / Zugfestigkeit Rm" if stress else "Maximalkraft Fmax", fmt(m["F"], 1), sig(m["F"]),
                 fmt(m["t"], 1), m["idx"]])
    keys.append(len(rows) - 1)
    if kv["break"]:
        b = kv["break"]
        rows.append(["Kraft vor dem Bruch", fmt(b["F"], 1), sig(b["F"]), fmt(b["t"], 1), b["idx"]])
        keys.append(len(rows) - 1)
        dr = kv["drop"]
        rows.append([f"Abfall Maximum → Bruch ({fmt(dr['pct'], 1, '%')})", fmt(dr["abs_F"], 1), sig(dr["abs_F"]),
                     fmt(dr["dauer"], 1), "–"])
        rows.append(["Bruchdauer", "–", "–", kv["break_duration_text"], "–"])
    else:
        rows.append(["Bruch", "kein Bruch erkannt", "–", "–", "–"])
    pl = kv["plateau"]
    plF = pl["mittel"] * r.a0 if (stress and pl["mittel"] is not None) else pl["mittel"]
    rows.append(["Plateau-Mittel (80–100 % der Zeit bis Fmax)", fmt(plF, 1), sig(plF),
                 f"{fmt(pl['t_von'], 1)}–{fmt(pl['t_bis'], 1)}", "–"])
    h = kv["hold"]
    rows.append([f"Haltezeit über {fmt(h['schwelle'] * 100, 0, '%')} von {'Rm' if stress else 'Fmax'}",
                 f"> {fmt(h['grenze'] * (r.a0 if stress else 1), 1)}", f"> {fmt(h['grenze'], 0)}" if stress else "–",
                 fmt(h["dauer"], 1), "–"])
    if kv["ratio"]:
        rows.append(["Verhältnis Rm / Streckgrenze (Verfestigung)" if stress else "Verhältnis Fmax / Fliessbeginn",
                     fmt(kv["ratio"], 2), fmt(kv["ratio"], 2) if stress else "–", "–", "–"])
    story.append(_tbl(rows, [W * 0.42, W * 0.14, W * 0.16, W * 0.14, W * 0.14], st, key_rows=keys))

    # Linearer Abschnitt
    story.append(Paragraph("Linearer Abschnitt (Ausgleichsgerade, Abschnitt 4.2)", st["h2"]))
    f = kv["fit"]
    sym = "σ" if stress else "F"
    rows = [["Grösse", "Wert", "Grösse", "Wert"],
            ["Fitfenster", f"{fmt(f['t_von'], 1)} – {fmt(f['t_bis'], 1, 's')}, n = {f['n']}",
             "Gerade", f"{sym} = {fmt(f['k'], 3)} · t − {fmt(-f['q'], 2)}"],
            ["Steigung k", f"{fmt(f['k_N_s'], 3, 'N/s')}" + (f" = {fmt(f['k'], 2, 'MPa/s')}" if stress else ""),
             "R²", fmt(f["r2"], 5)],
            ["Grösste Abweichung", f"{fmt(f['max_dev'], 2, u)} (Toleranz {fmt(f['tol'], 2, u)})",
             "Fusspunkt t₀ = −q/k", fmt(r.t0, 2, "s")]]
    yt = r.yield_table
    rows.append(["Fliessbeginn je Schwelle", " / ".join(fmt(x["schwelle"] * 100, 1) for x in yt) + " %",
                 "Kraft dabei", " / ".join(fmt(x["F"], 1) for x in yt) + " N"])
    story.append(_tbl(rows, [W * 0.2, W * 0.32, W * 0.18, W * 0.30], st))

    # Elastizitaetsmodul
    story.append(Paragraph("Elastizitätsmodul (scheinbar)", st["h2"]))
    formula = "E<sub>schein</sub> = k · (1 / v) · (L₀ / A₀), k in N/s, v in mm/s"
    missing = [n for n, ok in (("A₀", r.a0), ("v", r.v_mm_s), ("L₀", r.l0)) if not ok]
    if r.e_schein_gpa is not None:
        txt = (f"{formula}<br/>= {fmt(f['k_N_s'], 3)} N/s · (1 / {fmt(r.v_mm_s, 4)} mm/s) · "
               f"({fmt(r.l0, 1)} mm / {fmt(r.a0, 4)} mm²) = <b>{fmt(r.e_schein_gpa, 1)} GPa, scheinbar</b>. "
               "Kein Werkstoffkennwert.")
        if cfg.displacement_source != "probe":
            txt += (" Der Weg stammt aus der Traverse bzw. ist nicht dokumentiert: er enthält die Nachgiebigkeit von "
                    "Einspannung und Rahmen, der wahre Modul liegt um ein Vielfaches höher.")
        low = [w for w in r.warnings if w["code"] == "7.2" and "Hälfte" in w["text"]]
        if low:
            txt += " " + low[0]["text"]
    else:
        txt = f"{formula}<br/>Entfällt. Offene Grössen: {', '.join(missing)}."
    story.append(Paragraph(txt, st["p"]))

    # Gueltigkeit
    story.append(Paragraph("Gültigkeit", st["h2"]))
    for w in r.warnings:
        story.append(Paragraph(f"<b>[{w['code']}]</b> {w['text']}", st["small"]))
    if stress and r.comparison:
        top = r.comparison["rows"][:3]
        story.append(Paragraph(
            "<b>Vergleich:</b> nächste Kandidaten " + ", ".join(f"{x['name']} (Rm {fmt(x['Rm'], 0)} MPa)" for x in top)
            + ". " + r.comparison["hinweis"], st["small"]))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(f"Erstellt mit der FLPS Auswerte-App aus {Path(r.source).name}.", st["small"]))

    frame_h = A4[1] - 24 * mm
    doc.build([KeepInFrame(W, frame_h, story, mode="shrink")])
    return path


def write_image_appendix(r: Result, folder: Path) -> Path:
    _fonts()
    path = folder / f"{r.name}_Bildanhang.pdf"
    figs = charts.build_figures(r)
    pw, ph = landscape(A4)
    c = canvas.Canvas(str(path), pagesize=(pw, ph))
    c.setTitle(f"Bildanhang {r.name}")
    total = len(figs)
    margin = 12 * mm
    for page, (nr, title, fig) in enumerate(figs, 1):
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=200, bbox_inches="tight", pad_inches=0.15)
        plt.close(fig)
        buf.seek(0)
        img = ImageReader(buf)
        iw, ih = img.getSize()
        avail_w, avail_h = pw - 2 * margin, ph - 2 * margin - 16 * mm
        s = min(avail_w / iw, avail_h / ih)
        w, h = iw * s, ih * s
        x = (pw - w) / 2
        y = margin + 14 * mm + (avail_h - h) / 2
        c.drawImage(img, x, y, w, h)
        c.setFont("DejaVu-Bold", 11)
        c.drawCentredString(pw / 2, y - 7 * mm, f"Abbildung {nr}: {title}")
        c.setFont("DejaVu", 8)
        c.drawRightString(pw - margin, margin - 4 * mm, f"Seite {page} von {total}")
        c.drawString(margin, margin - 4 * mm, r.name)
        c.showPage()
    c.save()
    return path
