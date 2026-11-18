"""Ergebnisse als Folio-Lab-Bundle fuer den Berichtseditor.

Eine Messung: Verlauf, linearer Abschnitt, Abweichung, Spannungs-Dehnungs-Feld und Kandidaten
als Vektorgrafik, Kennwerttabelle, Referenzvergleich, Werte als \\labval-Makros, Messdaten als
CSV, Zitate (Norm der Probe, Quelle der Werkstoffwerte, Rohdaten) und Text fuer Methodik und
Ergebnisse. Mehrere Messungen: Ueberlagerungen, Kennwerte nebeneinander und Vergleichstabelle.
Sprache der Beschriftungen: Deutsch oder Englisch.
"""
from __future__ import annotations

import re

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.text import Text  # noqa: E402
from matplotlib.ticker import FuncFormatter, ScalarFormatter  # noqa: E402

try:
    from labbundle import Bundle, booktabs, cite, num, slugify, tex_escape  # noqa: E402
except ImportError:  # Modul ausserhalb des Hubs gestartet: SDK aus dem Suite-Ordner holen
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "sdk" / "python"))
    from labbundle import Bundle, booktabs, cite, num, slugify, tex_escape  # noqa: E402

from .analyse import PHASES, Result, specimen_label  # noqa: E402
from .export import charts as C  # noqa: E402

FIG = (6.4, 3.6)

# Normen der Probenformen -> Literaturangabe. Ausgabejahr nur, wo es sicher ist.
NORMS = {
    "ISO 527-2": ("iso527-2", "ISO 527-2", "Plastics -- Determination of tensile properties -- Part 2: Test conditions for moulding and extrusion plastics", "2012"),
    "ISO 527-3": ("iso527-3", "ISO 527-3", "Plastics -- Determination of tensile properties -- Part 3: Test conditions for films and sheets", "2018"),
    "ISO 6892-1": ("iso6892-1", "ISO 6892-1", "Metallic materials -- Tensile testing -- Part 1: Method of test at room temperature", "2019"),
    "ISO 37": ("iso37", "ISO 37", "Rubber, vulcanized or thermoplastic -- Determination of tensile stress-strain properties", "2017"),
    "DIN 53504": ("din53504", "DIN 53504", "Prüfung von Kautschuk und Elastomeren -- Bestimmung von Reißfestigkeit, Zugfestigkeit, Reißdehnung und Spannungswerten im Zugversuch", ""),
    "ASTM D638": ("astm-d638", "ASTM D638", "Standard Test Method for Tensile Properties of Plastics", ""),
    "ASTM D882": ("astm-d882", "ASTM D882", "Standard Test Method for Tensile Properties of Thin Plastic Sheeting", ""),
    "ASTM D412": ("astm-d412", "ASTM D412", "Standard Test Methods for Vulcanized Rubber and Thermoplastic Elastomers -- Tension", ""),
    "ASTM E8": ("astm-e8", "ASTM E8/E8M", "Standard Test Methods for Tension Testing of Metallic Materials", ""),
    "DIN 50125": ("din50125", "DIN 50125", "Prüfung metallischer Werkstoffe -- Zugproben", ""),
    "ISO 1924-2": ("iso1924-2", "ISO 1924-2", "Paper and board -- Determination of tensile properties -- Part 2: Constant rate of elongation method (20 mm/min)", "2008"),
    "ISO 1924-3": ("iso1924-3", "ISO 1924-3", "Paper and board -- Determination of tensile properties -- Part 3: Constant rate of elongation method (100 mm/min)", "2005"),
    "ISO 13934-1": ("iso13934-1", "ISO 13934-1", "Textiles -- Tensile properties of fabrics -- Part 1: Determination of maximum force and elongation at maximum force using the strip method", "2013"),
}

# ----------------------------------------------------------------------------- Sprache
T = {
    "de": {
        "title1": "Zugversuch {n}", "titleN": "Zugversuche {n}",
        "fig_curve": "{q}-Zeit-Verlauf der Messung {n} nach Phasen mit Fliessbeginn ({thr}\\,\\% von {ref}), Maximum und Bruch.",
        "fig_fit": "Messpunkte der Messung {n} gegen die verlängerte Ausgleichsgerade des linearen Abschnitts.",
        "fig_dev": "Abweichung der Messpunkte von der Ausgleichsgeraden mit der Schwelle des Fliessbeginns ({thr}\\,\\% von {ref}).",
        "fig_field": "Gemessene Spannungs-Dehnungs-Kurve im idealisierten Feld der Vergleichsgruppe {g}{refpart}. Dehnung aus dem {src}.",
        "fig_cand": "Fliessbeginn und Zugfestigkeit der Messung im Vergleich mit den nächstliegenden Werkstoffen der Gruppe {g}.",
        "fig_field_key": " Die Zahlen an den Kurvenenden bezeichnen die Werkstoffe im Schlüssel; Kennwerte aus den angegebenen Quellen.",
        "tab_src": "Werkstoffe des Spannungs-Dehnungs-Felds {g} mit den Kennwerten, aus denen ihre Kurven idealisiert sind (Nummern wie im Diagramm){cont}.",
        "cont": ", Fortsetzung",
        "h_src": ["Nr.", "Werkstoff", "$R_{p0,2}$ [MPa]", "$R_m$ [MPa]", "$A$ [\\%]", "$E$ [GPa]", "Quelle"],
        "mat_title": "Werkstoffkennwerte {n}",
        "fig_sketch": "Probengeometrie: {s}.",
        "fig_ov_time": "Überlagerter Verlauf der Messungen {n}.",
        "fig_ov_strain": "Überlagerte Spannungs-Dehnungs-Kurven der Messungen {n}.",
        "fig_kpis": "Kennwerte der Messungen {n} im Vergleich.",
        "tab_kv": "Kennwerte der Messung {n}.", "tab_ref": "Messung {n} im Vergleich mit dem Referenzwerkstoff {r} (Sollwerte, nicht gemessen).",
        "tab_cmp": "Kennwerte der Messungen im Vergleich.",
        "col_q": "Kennwert", "col_v": "Wert", "col_meas": "gemessen", "col_ref": "Referenz", "col_dev": "Abweichung",
        "col_name": "Messung",
        "data": "Messdaten der Messung {n}: Zeit, Kraft{more}.",
        "rows": {"a0": "Querschnitt $A_0$", "l0": "Messlänge $L_0$", "v": "Prüfgeschwindigkeit", "yield": "Fliessbeginn ({thr}\\,\\%)",
                 "max_s": "Zugfestigkeit $R_m$", "max_f": "Maximalkraft $F_\\mathrm{{max}}$", "brk": "vor dem Bruch",
                 "drop": "Abfall Maximum bis Bruch", "hold": "Haltezeit über {h}\\,\\%", "ratio": "Verhältnis Maximum/Fliessbeginn",
                 "e": "Elastizitätsmodul (scheinbar)", "k": "Steigung linearer Abschnitt", "r2": "Bestimmtheitsmaß $R^2$",
                 "rate": "Abtastrate", "fmax": "Maximalkraft"},
        "methods_t": "Methodik", "results_t": "Ergebnisse",
        "src_trav": "Traversenweg (scheinbar)", "src_probe": "Weg an der Probe",
        "phase": {"Setzen": "Setzen", "elastisch": "elastisch", "plastisch": "plastisch", "Abfall": "Abfall"},
    },
    "en": {
        "title1": "Tensile test {n}", "titleN": "Tensile tests {n}",
        "fig_curve": "{q}--time curve of measurement {n} by phase, with yield onset ({thr}\\,\\% of {ref}), maximum and break.",
        "fig_fit": "Data points of measurement {n} against the extended regression line of the linear section.",
        "fig_dev": "Deviation of the data points from the regression line, with the yield-onset threshold ({thr}\\,\\% of {ref}).",
        "fig_field": "Measured stress--strain curve within the idealised field of the comparison group {g}{refpart}. Strain from the {src}.",
        "fig_cand": "Yield onset and tensile strength of the measurement compared with the closest materials of the group {g}.",
        "fig_field_key": " Numbers at the curve ends identify the materials in the key; property values from the sources given.",
        "tab_src": "Materials of the stress--strain field {g} with the property values their curves are idealised from (numbers as in the figure){cont}.",
        "cont": ", continued",
        "h_src": ["No.", "Material", "$R_{p0.2}$ [MPa]", "$R_m$ [MPa]", "$A$ [\\%]", "$E$ [GPa]", "Source"],
        "mat_title": "Material properties of {n}",
        "fig_sketch": "Specimen geometry: {s}.",
        "fig_ov_time": "Overlaid curves of the measurements {n}.",
        "fig_ov_strain": "Overlaid stress--strain curves of the measurements {n}.",
        "fig_kpis": "Key values of the measurements {n} compared.",
        "tab_kv": "Key values of measurement {n}.", "tab_ref": "Measurement {n} compared with the reference material {r} (nominal values, not measured).",
        "tab_cmp": "Key values of the measurements compared.",
        "col_q": "Quantity", "col_v": "Value", "col_meas": "measured", "col_ref": "reference", "col_dev": "deviation",
        "col_name": "Measurement",
        "data": "Measured data of {n}: time, force{more}.",
        "rows": {"a0": "Cross-section $A_0$", "l0": "Gauge length $L_0$", "v": "Test speed", "yield": "Yield onset ({thr}\\,\\%)",
                 "max_s": "Tensile strength $R_m$", "max_f": "Maximum force $F_\\mathrm{{max}}$", "brk": "Before break",
                 "drop": "Drop maximum to break", "hold": "Hold time above {h}\\,\\%", "ratio": "Ratio maximum/yield onset",
                 "e": "Elastic modulus (apparent)", "k": "Slope of linear section", "r2": "Coefficient of determination $R^2$",
                 "rate": "Sampling rate", "fmax": "Maximum force"},
        "methods_t": "Methods", "results_t": "Results",
        "src_trav": "crosshead displacement (apparent)", "src_probe": "displacement measured on the specimen",
        "phase": {"Setzen": "settling", "elastisch": "elastic", "plastisch": "plastic", "Abfall": "drop"},
    },
}

# Beschriftungen der Diagramme, Deutsch -> Englisch (laengere zuerst).
_EN = [
    ("Werkstoffe im Feld (Kurvennummer)", "Materials in the field (curve number)"),
    ("Dehnung ε [%] (scheinbar)", "Strain ε [%] (apparent)"), ("Dehnung ε [%]", "Strain ε [%]"),
    ("Spannung σ [MPa]", "Stress σ [MPa]"), ("Spannung [MPa]", "Stress [MPa]"), ("Kraft |F| [N]", "Force |F| [N]"),
    ("Zeit t [s]", "Time t [s]"), ("Abfall (Einschnürung?)", "Drop (necking?)"), ("Abweichung", "Deviation"),
    ("Gerade aus dem Fitfenster", "Line from fit window"), ("Fitfenster", "Fit window"), ("Messpunkte", "Data points"),
    ("Rp0,2 bzw. Streckspannung", "Rp0.2 or yield stress"), ("(Messung)", "(measurement)"), ("Referenzwerkstoff", "Reference material"),
    ("Referenz", "Reference"), ("(Kurven aus Quellen)", "(curves from sources)"),
    ("(Kurve aus Quelle)", "(curve from source)"), ("(idealisiert)", "(idealised)"), ("obere Grenze", "upper bound"),
    ("untere Grenze", "lower bound"), ("Fliessbeginn", "Yield onset"), ("Zugfestigkeit", "Tensile strength"),
    ("zurückgestuft", "downgraded"), ("unwahrscheinlich", "unlikely"), ("Kandidat", "Candidate"),
    ("Schwelle", "Threshold"), ("vor Bruch", "before break"), ("Bruch", "Break"), ("Setzen", "Settling"),
    ("elastisch", "elastic"), ("plastisch", "plastic"), ("Dicke", "Thickness"), ("Kennwerte", "Key values"),
    ("Edelstahl", "Stainless steel"), ("Gusseisen", "Cast iron"), ("Stahl", "Steel"), ("Kupfer", "Copper"),
    ("Titan", "Titanium"), ("Kunststoff verstärkt", "Reinforced plastics"), ("Kunststoff", "Plastics"),
    ("Folie", "Film"), ("Papier", "Paper"), ("Holz", "Wood"), ("Faserverbund", "Fibre composite"),
    ("alle Metalle", "all metals"), ("alle Werkstoffe", "all materials"), ("Feld ", "Field "),
    (" bis ", " to "), (" von ", " of "),
]


def _translate(fig, lang: str, keep: set[str]):
    """Beschriftungen einer fertigen Figur auf Englisch umstellen, Dezimalkomma -> Punkt."""
    if lang != "en":
        return
    def tr(s: str) -> str:
        if not s or s in keep:
            return s
        out = s
        for de, en in _EN:
            if de in out and not any(de in k for k in keep if k in out):
                out = out.replace(de, en)
        out = re.sub(r"^Messung(?=$| \d)", "Measurement", out)
        return re.sub(r"(\d),(\d)", r"\1.\2", out)

    for ax in fig.axes:
        for axis in (ax.xaxis, ax.yaxis):
            fmt_ = axis.get_major_formatter()
            if isinstance(fmt_, FuncFormatter) and getattr(fmt_, "func", None) is C._cf:
                f = ScalarFormatter()
                f.set_useOffset(False)
                axis.set_major_formatter(f)
            elif hasattr(fmt_, "seq"):  # feste Beschriftungen (Kategorien), aeltere matplotlib
                fmt_.seq = [tr(s) for s in fmt_.seq]
            elif isinstance(fmt_, FuncFormatter):  # feste Beschriftungen ab matplotlib 3.10
                axis.set_major_formatter(FuncFormatter(lambda x, pos, _f=fmt_.func: tr(_f(x, pos))))
    for t in fig.findobj(Text):
        if t.get_gid() == "keep":      # Werkstoffnamen und Kurvennummern bleiben, wie sie sind
            continue
        s = t.get_text()
        out = tr(s)
        if out != s:
            t.set_text(out)


def _fig(draw, lang, keep, size=FIG):
    fig, ax = plt.subplots(figsize=size)
    draw(ax)
    ax.set_title("")
    _translate(fig, lang, keep)
    fig.tight_layout()
    return fig


def _norm(r: Result):
    from .analyse import SHAPES
    sh = SHAPES.get(r.config.shape, {}) if r.config.specimen_mode == "norm" else {}
    return NORMS.get(sh.get("norm") or "")


def _cite_cmd(keys):
    return r"\cite{" + ",".join(keys) + "}" if keys else ""


def _safe_url(u: str) -> bool:
    """URL fields go into the .bib unescaped; only plain http(s) links without braces or spaces."""
    return bool(u) and u.startswith(("http://", "https://")) and not any(c in u for c in "{}\\ \n")


def _mat_cite(b: Bundle, a, lang: str) -> str:
    """Literaturangabe der Kennwerte eines Vergleichswerkstoffs (Quelle und Basis aus data/alloys.json)."""
    key = "mat-" + slugify(a.name, 30)
    rec = getattr(a, "cite", None)
    if rec:  # strukturierte Quelle (eigener Werkstoff): richtiger Eintragstyp mit Autoren, DOI, Jahr
        import labcite
        if not labcite.errors(rec):
            extra = {}
            if a.basis:
                note = labcite.clean(rec).get("note")
                extra["note"] = tex_escape("; ".join(x for x in (note, a.basis) if x))
            return labcite.to_bib(b, key, rec, extra)
    url = getattr(a, "url", "")
    b.add_citation(key, "misc", title=tex_escape(T[lang]["mat_title"].format(n=a.name)),
                   howpublished=tex_escape(a.basis), note=tex_escape(a.source or ("Quelle nicht angegeben" if lang == "de" else "source not given")),
                   year=tex_escape(getattr(a, "year", "")),
                   url=url if _safe_url(url) else "", urldate=getattr(a, "accessed", "") if _safe_url(url) else "")
    return key


# ----------------------------------------------------------------------------- Eine Messung
def _single(b: Bundle, r: Result, lang: str, inc: dict, keep: set[str]):
    L = T[lang]
    st = r.mode == "Spannung"
    kv, u = r.kv, r.unit
    nd = 0 if st else 1
    thr = num(r.config.yield_threshold * 100, 1, lang)
    ref_lbl = "R_m" if st else "F_\\mathrm{max}"
    ref_lbl = f"${ref_lbl}$"
    n = tex_escape(r.name)
    q = ("Spannungs" if lang == "de" else "Stress") if st else ("Kraft" if lang == "de" else "Force")

    # Zitate zuerst: die Texte verweisen darauf
    cites = {}
    if inc.get("citations", True):
        nm = _norm(r)
        if nm:
            key, number, title, year = nm
            b.add_citation(key, "misc", title=f"{number}: {title}", author="{" + number.split()[0] + "}",
                           year=year, note="" if year else ("Ausgabe prüfen" if lang == "de" else "check edition"))
            cites["norm"] = key
        if r.reference is not None:
            cites["mat"] = _mat_cite(b, r.reference, lang)
        if st and r.comparison:
            # jede Vergleichskurve im Feld und jeder Kandidat mit eigener Quelle
            cites["field"] = [_mat_cite(b, a, lang) for a in C.field_members(r)]
            if "mat" in cites and cites["mat"] not in cites["field"]:
                cites["field"].append(cites["mat"])
            shown = [row["name"] for row in r.comparison["rows"][:6]]
            by_name = {a.name: a for a in r.alloys}
            cites["cand"] = [_mat_cite(b, by_name[n], lang) for n in shown if n in by_name]
            if "mat" in cites:
                cites["cand"].append(cites["mat"])
        d = r.device
        key = "data-" + b.slug
        o = d.get("origin")
        if o:                                     # I-03: Messdaten aus einem Datensatz des Projekts
            p = o.get("producer") or {}
            where = ", ".join(x for x in ("Folio Lab", p.get("env_name"), p.get("item_name")) if x)
            b.add_citation(key, "misc", title=tex_escape(f"{'Datensatz' if lang == 'de' else 'Dataset'} {o.get('title') or r.name}"),
                           howpublished=tex_escape(where), year=d["date"][-4:],
                           note=tex_escape(f"{o.get('share') or ''}, Version {o.get('version') or '?'}"))
        else:
            b.add_citation(key, "misc", title=tex_escape(f"{'Rohdaten' if lang == 'de' else 'Raw data'} {r.name}.flps"),
                           howpublished=tex_escape(f"IMADA {d['model']}, SN {d['serial']}"),
                           year=d["date"][-4:], note=tex_escape(f"{d['start']} – {d['end']}"))
        cites["data"] = key

    # Werte (immer, sie kosten nichts und machen den Text lebendig)
    vals = []
    m = kv["max"]
    vals.append(("Fmax", L["rows"]["fmax"], num(m["F"], 1, lang, "N"), f"{m['F']:.1f} N"))
    vals.append(("tmax", "t(Fmax)", num(m["t"], 1, lang, "s"), f"{m['t']:.1f} s"))
    if st:
        vals.append(("Rm", L["rows"]["max_s"], num(kv["Rm"], 0, lang, "MPa"), f"{kv['Rm']:.0f} MPa"))
    y = kv["yield"]
    if y:
        vals.append(("yield", L["rows"]["yield"].format(thr=thr), num(y["y"], nd, lang, u), f"{y['y']:.{nd}f} {u}"))
        vals.append(("yieldF", "Kraft bei Fliessbeginn" if lang == "de" else "Force at yield onset", num(y["F"], 1, lang, "N"), f"{y['F']:.1f} N"))
    if kv["break"]:
        vals.append(("break", L["rows"]["brk"], num(kv["break"]["y"], nd, lang, u), f"{kv['break']['y']:.{nd}f} {u}"))
    if kv["drop"]:
        vals.append(("drop", L["rows"]["drop"], num(kv["drop"]["pct"], 1, lang, "%"), f"{kv['drop']['pct']:.1f} %"))
    vals.append(("hold", "Haltezeit" if lang == "de" else "Hold time", num(kv["hold"]["dauer"], 1, lang, "s"), f"{kv['hold']['dauer']:.1f} s"))
    vals.append(("ratio", L["rows"]["ratio"], num(kv["ratio"], 2, lang), f"{kv['ratio']:.2f}"))
    if r.e_schein_gpa is not None:
        vals.append(("E", L["rows"]["e"], num(r.e_schein_gpa, 1, lang, "GPa"), f"{r.e_schein_gpa:.1f} GPa"))
    if r.a0:
        vals.append(("A0", L["rows"]["a0"], num(r.a0, 4, lang, "mm²"), f"{r.a0:.4f} mm²"))
    if r.l0:
        vals.append(("L0", L["rows"]["l0"], num(r.l0, 1, lang, "mm"), f"{r.l0:.1f} mm"))
    if r.config.speed_mm_min:
        vals.append(("v", L["rows"]["v"], num(r.config.speed_mm_min, 2, lang, "mm/min"), f"{r.config.speed_mm_min:.2f} mm/min"))
    vals.append(("rate", L["rows"]["rate"], num(kv["rate_hz"], 1, lang, "Hz"), f"{kv['rate_hz']:.1f} Hz"))
    vals.append(("thr", "Schwelle Fliessbeginn" if lang == "de" else "Yield-onset threshold", thr + r"\,\%", f"{r.config.yield_threshold * 100:.1f} %"))
    if r.reference is not None:
        vals.append(("refRm", "$R_m$ Referenz" if lang == "de" else "Reference $R_m$", num(r.reference.rm, 0, lang, "MPa"), f"{r.reference.rm:.0f} MPa"))
        if r.ref_cmp and r.ref_cmp.get("d_rm_pct") is not None:
            vals.append(("refdRm", "ΔRm", num(r.ref_cmp["d_rm_pct"], 1, lang, "%"), f"{r.ref_cmp['d_rm_pct']:.1f} %"))
    if inc.get("values", True):
        b.add_values(vals)

    if inc.get("figures", True):
        b.add_figure(_fig(lambda ax: C.chart1(r, ax, title=False), lang, keep), "verlauf",
                     L["fig_curve"].format(q=q, n=n, thr=thr, ref=ref_lbl))
        b.add_figure(_fig(lambda ax: C.chart2_fit(r, ax, full=True), lang, keep), "linear", L["fig_fit"].format(n=n))
        b.add_figure(_fig(lambda ax: C.chart2_dev(r, ax), lang, keep, (6.4, 2.8)), "abweichung",
                     L["fig_dev"].format(thr=thr, ref=ref_lbl))
        if st and r.strain is not None and r.comparison:
            refpart = (f" und dem Referenzwerkstoff {tex_escape(r.reference.name)}" if lang == "de" else
                       f" and the reference material {tex_escape(r.reference.name)}") if r.reference else ""
            src = L["src_probe"] if r.config.displacement_source == "probe" else L["src_trav"]
            n_field = len(C.field_members(r))
            extra_txt = ""
            if r.extras:
                nr0 = n_field - len(r.extras)
                lst = ", ".join(f"{nr0 + i + 1}~{tex_escape(a.name)}" for i, a in enumerate(r.extras))
                extra_txt = (f" Zusätzlich eingeblendet (farbig, nicht Teil des Felds): {lst}." if lang == "de" else
                             f" Additionally shown (coloured, not part of the field): {lst}.")
            if any(getattr(a, "curve", None) for a in C.field_members(r)):
                extra_txt += (" Werkstoffe mit eigener Kurve sind nicht idealisiert, sondern aus der angegebenen Quelle "
                              "übernommen." if lang == "de" else
                              " Materials with their own curve are not idealised but taken from the source given.")
            b.add_figure(_fig(lambda ax: C.chart3(r, ax, title=False, key="below"), lang, keep,
                              (6.4, 4.0 + C.key_height_in(n_field))), "feld",
                         L["fig_field"].format(g=tex_escape(r.group), refpart=refpart, src=src) + L["fig_field_key"]
                         + extra_txt, cites=cites.get("field"))
        if st and r.comparison:
            b.add_figure(_fig(lambda ax: C.chart4(r, ax, title=False), lang, keep), "kandidaten",
                         L["fig_cand"].format(g=tex_escape(r.group)), cites=cites.get("cand"))
        b.add_figure(_fig(lambda ax: C.specimen_sketch(r, ax), lang, keep, (5.0, 2.0)), "probe",
                     L["fig_sketch"].format(s=tex_escape(specimen_label(r))), width="0.6")

    if inc.get("tables", True):
        R = L["rows"]
        rows = []
        if r.a0:
            rows.append([R["a0"], num(r.a0, 4, lang, "mm²")])
        if r.l0:
            rows.append([R["l0"], num(r.l0, 1, lang, "mm")])
        if r.config.speed_mm_min:
            rows.append([R["v"], num(r.config.speed_mm_min, 2, lang, "mm/min")])
        if y:
            rows.append([R["yield"].format(thr=thr), num(y["y"], nd, lang, u)])
        rows.append([R["max_s"] if st else R["max_f"], num(m["y"], nd, lang, u)])
        if st:
            rows.append([R["fmax"], num(m["F"], 1, lang, "N")])
        if kv["break"]:
            rows.append([R["brk"], num(kv["break"]["y"], nd, lang, u)])
        if kv["drop"]:
            rows.append([R["drop"], num(kv["drop"]["pct"], 1, lang, "%")])
        rows.append([R["hold"].format(h=num(kv["hold"]["schwelle"] * 100, 0, lang)), num(kv["hold"]["dauer"], 1, lang, "s")])
        rows.append([R["ratio"], num(kv["ratio"], 2, lang)])
        if r.e_schein_gpa is not None:
            rows.append([R["e"], num(r.e_schein_gpa, 1, lang, "GPa")])
        rows.append([R["k"], num(kv["fit"]["k_N_s"], 3, lang, "N/s")])
        rows.append([R["r2"], num(kv["fit"]["r2"], 5, lang)])
        b.add_table("kennwerte", booktabs([L["col_q"], L["col_v"]], rows), L["tab_kv"].format(n=n))
        if r.reference is not None and st:
            ref = r.reference
            rr = [[R["max_s"], num(kv["Rm"], 0, lang), num(ref.rm, 0, lang), num(100 * (kv["Rm"] - ref.rm) / ref.rm, 1, lang, "%")]]
            if y and ref.rp:
                rr.append([R["yield"].format(thr=thr) + " / $R_{p0,2}$" if lang == "de" else R["yield"].format(thr=thr) + " / $R_{p0.2}$",
                           num(y["y"], 0, lang), num(ref.rp, 0, lang), num(100 * (y["y"] - ref.rp) / ref.rp, 1, lang, "%")])
            if r.e_schein_gpa is not None:
                rr.append([R["e"] + " [GPa]", num(r.e_schein_gpa, 1, lang), num(ref.e_gpa, 1, lang),
                           num(100 * (r.e_schein_gpa - ref.e_gpa) / ref.e_gpa, 0, lang, "%")])
            b.add_table("referenz", booktabs([L["col_q"] + " [MPa]", L["col_meas"], L["col_ref"], L["col_dev"]], rr, "lrrr"),
                        L["tab_ref"].format(n=n, r=tex_escape(ref.name)), cites=cites.get("mat"))
        if st and r.comparison and "field" in cites:
            _source_tables(b, r, lang, cites)

    if inc.get("data", True):
        header = ["t_s", "F_N"] + (["sigma_MPa"] if st else []) + (["eps_pct"] if r.strain is not None else []) + ["phase"]
        rows = []
        for i in range(len(r.t)):
            row = [round(float(r.t[i]), 4), float(r.force[i])]
            if st:
                row.append(float(r.y[i]))
            if r.strain is not None:
                row.append(float(r.strain[i] * 100))
            row.append(PHASES[int(r.phases[i])] if i < len(r.phases) else "")
            rows.append(row)
        more = (", Spannung" if lang == "de" else ", stress") if st else ""
        more += (", Dehnung" if lang == "de" else ", strain") if r.strain is not None else ""
        de = lang == "de"
        labels = {"t_s": r"Zeit $t$ [s]" if de else r"Time $t$ [s]", "F_N": r"Kraft $F$ [N]" if de else r"Force $F$ [N]",
                  "sigma_MPa": r"Spannung $\sigma$ [MPa]" if de else r"Stress $\sigma$ [MPa]",
                  "eps_pct": r"Dehnung $\varepsilon$ [\%]" if de else r"Strain $\varepsilon$ [\%]",
                  "phase": "Phase"}
        b.add_data_csv("messdaten", header, rows, L["data"].format(n=r.name, more=more),
                       labels={k: v for k, v in labels.items() if k in header},
                       plot={"x": "t_s", "y": "sigma_MPa" if st else "F_N"})

    eq_text = ""
    if r.equations and inc.get("values", True):
        from labcalc import formulas as Fm
        eq_text = Fm.to_report(b, r.equations, lang, cite_prefix="eq").get("latex", "")

    if inc.get("text", True):
        _texts(b, r, lang, cites, eq_text)


def _source_tables(b: Bundle, r: Result, lang: str, cites: dict, per_table: int = 40):
    """Quellentabelle zum Spannungs-Dehnungs-Feld: jede nummerierte Kurve mit Kennwerten und Literaturangabe.
    Lange Gruppen (z. B. "alle Werkstoffe") werden auf mehrere Tabellen verteilt, damit jede auf eine Seite passt."""
    L = T[lang]
    members = C.field_members(r)
    entries = [(str(i), a) for i, a in enumerate(members, 1)]
    if r.reference is not None and all(a.name != r.reference.name for a in members):
        entries.append(("R", r.reference))
    rows = []
    for nr, a in entries:
        key = _mat_cite(b, a, lang)
        rows.append((key, [nr, tex_escape(a.name), num(a.rp, 0, lang) if a.rp else "--", num(a.rm, 0, lang),
                           num(a.a_pct, 0, lang), num(a.e_gpa, 1, lang), cite([key], sep="")]))
    for k in range(0, len(rows), per_table):
        chunk = rows[k:k + per_table]
        b.add_table("werkstoffe" + (f"-{k // per_table + 1}" if k else ""),
                    booktabs(L["h_src"], [row for _, row in chunk], "rlrrrrl", small=True, escape_header=False),
                    L["tab_src"].format(g=tex_escape(r.group), cont=L["cont"] if k else ""), cites=[key for key, _ in chunk])


def _texts(b: Bundle, r: Result, lang: str, cites: dict, eq_text: str = ""):
    st = r.mode == "Spannung"
    s, c = b.slug, r.config
    V = lambda k: rf"\labval{{{s}}}{{{k}}}"  # noqa: E731
    d = r.device
    norm_c = (" " + _cite_cmd([cites["norm"]])) if "norm" in cites else ""
    data_c = (" " + _cite_cmd([cites["data"]])) if "data" in cites else ""
    spec = tex_escape(specimen_label(r))
    o = d.get("origin")                           # I-03: aus einem Datensatz – kein Gerät, Zeitachse ggf. aus dem Weg
    rl = (o or {}).get("roles") or {}
    unit_of = lambda x: tex_escape(x.get("unit") or "1")  # noqa: E731
    if lang == "de":
        if o:
            cols = " und ".join(f"{tex_escape(x['name'])} [{unit_of(x)}]" for x in (rl.get("load"), rl.get("ext")) if x)
            m = [f"Ausgewertet wurde der Datensatz ,,{tex_escape(o.get('title') or r.name)}`` (Version {o.get('version') or '?'})"
                 f"{data_c} einer Probe {spec}{norm_c} mit den Spalten {cols}."]
            if o.get("time_from") == "elongation":
                m.append(f"Die Zeitachse der Auswertung wurde aus dem zurückgelegten Weg und der Prüfgeschwindigkeit {V('v')} "
                         "berechnet; Dehnung und Modul folgen damit dem gemessenen Weg.")
            elif c.speed_mm_min:
                m.append(f"Die Prüfgeschwindigkeit betrug {V('v')}.")
        else:
            m = [f"Die Zugprüfung erfolgte an einer Probe {spec}{norm_c} auf einem Kraftmessgerät IMADA {tex_escape(d['model'])}"
                 f" (SN {tex_escape(d['serial'])}){data_c}."]
            if c.speed_mm_min:
                m.append(f"Die Prüfgeschwindigkeit betrug {V('v')}, die Kraft wurde mit {V('rate')} aufgezeichnet.")
            else:
                m.append(f"Die Kraft wurde mit {V('rate')} aufgezeichnet; die Prüfgeschwindigkeit ist nicht dokumentiert.")
        if st:
            m.append(f"Die Spannung bezieht sich auf den Ausgangsquerschnitt $A_0 = $ {V('A0')}.")
        m.append("Der lineare Abschnitt wurde als längstes Zeitfenster bestimmt, in dem die Messpunkte innerhalb einer "
                 "festen Toleranz auf einer Geraden liegen. Als Fliessbeginn gilt der erste Messpunkt nach diesem Fenster, "
                 f"der um mehr als {V('thr')} des Maximums von der verlängerten Geraden abweicht. Diese Schwelle ist eine "
                 "Festlegung und keine Dehngrenze $R_{p0,2}$.")
        if c.displacement_source != "probe" and r.e_schein_gpa is not None:
            m.append("Ob der Weg an der Probe gemessen wurde, ist nicht dokumentiert; der berechnete Modul ist deshalb ein "
                     "scheinbarer Wert." if o else
                     "Die Dehnung stammt aus dem Traversenweg und enthält die Nachgiebigkeit des Aufbaus; der daraus "
                     "berechnete Modul ist ein scheinbarer Wert.")
        if cites.get("field"):
            m.append(f"Verglichen wurde mit den {len(r.alloys)} Werkstoffen der Gruppe {tex_escape(r.group)}; "
                     "ihre Spannungs-Dehnungs-Kurven sind aus den Kennwerten $R_{p0,2}$, $R_m$, $A$ und $E$ "
                     f"idealisiert und keine Messkurven (Kennwerte nach{cite(cites['field'])}).")
        res = []
        if st:
            res.append(f"Die Probe erreichte eine Zugfestigkeit von {V('Rm')} (Maximalkraft {V('Fmax')} nach {V('tmax')}).")
        else:
            res.append(f"Die Maximalkraft betrug {V('Fmax')} nach {V('tmax')}.")
        if r.kv["yield"]:
            res.append(f"Der Fliessbeginn lag bei {V('yield')}, das Verhältnis von Maximum zu Fliessbeginn bei {V('ratio')}.")
        if r.kv["drop"]:
            res.append(f"Vom Maximum bis zum Bruch fiel die Last um {V('drop')}; die Last blieb {V('hold')} über 90\\,\\% des Maximums.")
        if r.reference is not None and st:
            mat_c = (" " + _cite_cmd([cites["mat"]])) if "mat" in cites else ""
            res.append(f"Gegenüber dem Referenzwerkstoff {tex_escape(r.reference.name)} ($R_m = $ {V('refRm')}{mat_c}) "
                       f"weicht die Zugfestigkeit um {V('refdRm')} ab. Eine Übereinstimmung in $R_m$ allein bestimmt den "
                       "Werkstoff nicht.")
        if r.e_schein_gpa is not None:
            res.append(f"Der scheinbare Modul von {V('E')} ist kein Werkstoffkennwert.")
    else:
        if o:
            cols = " and ".join(f"{tex_escape(x['name'])} [{unit_of(x)}]" for x in (rl.get("load"), rl.get("ext")) if x)
            m = [f"The dataset ``{tex_escape(o.get('title') or r.name)}'' (version {o.get('version') or '?'}){data_c} of a "
                 f"specimen {spec}{norm_c} was evaluated, with the columns {cols}."]
            if o.get("time_from") == "elongation":
                m.append(f"The time axis of the evaluation was calculated from the travelled displacement and the test speed "
                         f"{V('v')}, so strain and modulus follow the measured displacement.")
            elif c.speed_mm_min:
                m.append(f"The test speed was {V('v')}.")
        else:
            m = [f"The tensile test was carried out on a specimen {spec}{norm_c} using an IMADA {tex_escape(d['model'])} force "
                 f"gauge (SN {tex_escape(d['serial'])}){data_c}."]
            if c.speed_mm_min:
                m.append(f"The test speed was {V('v')}; force was recorded at {V('rate')}.")
            else:
                m.append(f"Force was recorded at {V('rate')}; the test speed was not documented.")
        if st:
            m.append(f"Stress refers to the initial cross-section $A_0 = $ {V('A0')}.")
        m.append("The linear section was determined as the longest time window in which the data points lie on a straight "
                 "line within a fixed tolerance. Yield onset is the first point after this window that deviates from the "
                 f"extended line by more than {V('thr')} of the maximum. This threshold is a convention, not a proof "
                 "stress $R_{p0.2}$.")
        if c.displacement_source != "probe" and r.e_schein_gpa is not None:
            m.append("Whether the displacement was measured on the specimen is not documented, so the calculated modulus is "
                     "an apparent value." if o else
                     "Strain was derived from the crosshead displacement and includes the compliance of the set-up; the "
                     "modulus calculated from it is an apparent value.")
        if cites.get("field"):
            m.append(f"The measurement was compared with the {len(r.alloys)} materials of the group "
                     f"{tex_escape(r.group)}; their stress--strain curves are idealised from $R_{{p0.2}}$, $R_m$, $A$ and $E$ "
                     f"and are not measured curves (property values from{cite(cites['field'])}).")
        res = []
        if st:
            res.append(f"The specimen reached a tensile strength of {V('Rm')} (maximum force {V('Fmax')} after {V('tmax')}).")
        else:
            res.append(f"The maximum force was {V('Fmax')} after {V('tmax')}.")
        if r.kv["yield"]:
            res.append(f"Yield onset was at {V('yield')}; the ratio of maximum to yield onset was {V('ratio')}.")
        if r.kv["drop"]:
            res.append(f"From the maximum to the break the load dropped by {V('drop')}; it stayed above 90\\,\\% of the "
                       f"maximum for {V('hold')}.")
        if r.reference is not None and st:
            mat_c = (" " + _cite_cmd([cites["mat"]])) if "mat" in cites else ""
            res.append(f"Compared with the reference material {tex_escape(r.reference.name)} ($R_m = $ {V('refRm')}{mat_c}), "
                       f"the tensile strength deviates by {V('refdRm')}. Agreement in $R_m$ alone does not identify the material.")
        if r.e_schein_gpa is not None:
            res.append(f"The apparent modulus of {V('E')} is not a material property.")
    L = T[lang]
    b.add_text("methodik", " ".join(m).replace("$ \\labval", "$\\labval") + "\n" + ("\n" + eq_text if eq_text else ""),
               L["methods_t"])
    b.add_text("ergebnisse", " ".join(res) + "\n", L["results_t"])


# ----------------------------------------------------------------------------- Mehrere Messungen
def _multi(b: Bundle, results: list[Result], lang: str, inc: dict, keep: set[str]):
    L = T[lang]
    st = results[0].mode == "Spannung"
    u = results[0].unit
    nd = 0 if st else 1
    names = ", ".join(tex_escape(r.name) for r in results)
    vals = []
    for r in results:
        k = slugify(r.name, 20)
        vals.append((f"{k}-max", f"{r.name} max", num(r.kv["max"]["y"], nd, lang, u), ""))
        if r.kv["yield"]:
            vals.append((f"{k}-yield", f"{r.name} yield", num(r.kv["yield"]["y"], nd, lang, u), ""))
        if r.a0:
            vals.append((f"{k}-A0", f"{r.name} A0", num(r.a0, 4, lang, "mm²"), ""))
    if inc.get("values", True):
        b.add_values(vals)
    if inc.get("figures", True):
        b.add_figure(_fig(lambda ax: C.overlay_time(results, ax), lang, keep), "verlauf", L["fig_ov_time"].format(n=names))
        if st and any(r.strain is not None for r in results):
            b.add_figure(_fig(lambda ax: C.overlay_strain(results, ax), lang, keep), "dehnung", L["fig_ov_strain"].format(n=names))
        b.add_figure(_fig(lambda ax: C.grouped_kpis(results, ax), lang, keep), "kennwerte", L["fig_kpis"].format(n=names))
    if inc.get("tables", True):
        R = L["rows"]
        head = [L["col_name"], "$A_0$ [mm$^2$]", ("Fliessbeginn" if lang == "de" else "Yield onset") + f" [{u}]",
                f"{'$R_m$' if st else '$F_{max}$'} [{u}]", f"{R['brk']} [{u}]", f"{R['drop']} [\\%]"]
        rows = []
        for r in results:
            kv = r.kv
            rows.append([tex_escape(r.name), num(r.a0, 4, lang) if r.a0 else "--",
                         num(kv["yield"]["y"], nd, lang) if kv["yield"] else "--", num(kv["max"]["y"], nd, lang),
                         num(kv["break"]["y"], nd, lang) if kv["break"] else "--",
                         num(kv["drop"]["pct"], 1, lang) if kv["drop"] else "--"])
        b.add_table("vergleich", booktabs(head, rows, "lrrrrr", small=True, escape_header=False), L["tab_cmp"])
    if inc.get("citations", True):
        for r in results:
            nm = _norm(r)
            if nm:
                key, number, title, year = nm
                b.add_citation(key, "misc", title=f"{number}: {title}", author="{" + number.split()[0] + "}", year=year)


# ----------------------------------------------------------------------------- Einstieg
def build(results: list[Result], raw: dict[str, bytes], request: dict, lang: str = "de",
          include: dict | None = None, title: str | None = None) -> dict:
    lang = lang if lang in T else "de"
    inc = {"figures": True, "tables": True, "values": True, "data": True, "citations": True, "text": True,
           **(include or {})}
    if inc["text"]:  # Textbausteine verwenden \labval und \cite
        inc["values"] = inc["citations"] = True
    keep = {r.name for r in results}
    names = ", ".join(r.name for r in results)
    L = T[lang]
    title = title or (L["title1"] if len(results) == 1 else L["titleN"]).format(n=names)
    summary = " · ".join(
        f"{r.name}: {'Rm' if r.mode == 'Spannung' else 'Fmax'} {r.kv['max']['y']:.{0 if r.mode == 'Spannung' else 1}f} {r.unit}"
        for r in results)
    b = Bundle(module="zugversuch", module_name="Zugversuch" if lang == "de" else "Tensile test", title=title,
               lang=lang, slug=request.get("slug") or None, summary=summary)
    if len(results) == 1:
        _single(b, results[0], lang, inc, keep)
    else:
        if len({r.mode for r in results}) > 1:
            raise ValueError("Messungen in Kraft und in Spannung lassen sich nicht in einem Bundle vergleichen.")
        _multi(b, results, lang, inc, keep)
    b.set_source({**request, "slug": b.slug}, raw)
    return b.to_dict()
