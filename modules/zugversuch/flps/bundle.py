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
    from labbundle import Bundle, booktabs, cite, num, slugify, split_sentences, tex_escape  # noqa: E402
except ImportError:  # Modul ausserhalb des Hubs gestartet: SDK aus dem Suite-Ordner holen
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "sdk" / "python"))
    from labbundle import Bundle, booktabs, cite, num, slugify, split_sentences, tex_escape  # noqa: E402

from .analyse import PHASES, Result, specimen_label  # noqa: E402
from .export import charts as C  # noqa: E402

FIG = (6.4, 3.6)
RO_KEY = "ramberg-osgood-1943"   # Modell der idealisierten Werkstoffkurven (flps/alloys.py, curve_model)

# Normen der Probenformen -> Literaturangabe. Ausgabejahr nur, wo es sicher ist; ohne Jahr steht im Literatureintrag
# "Ausgabe prüfen". Die Masse von data/specimens.json für ISO 527-2 folgen der Ausgabe 2012 (Feld "ausgabe" dort).
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
        "fig_curve": "{q}-Zeit-Verlauf der Messung {n} nach Phasen{{parts}}.",
        "fig_fit": "Messpunkte der Messung {n} gegen die verlängerte Ausgleichsgerade des linearen Abschnitts.",
        "fig_dev": "Abweichung der Messpunkte von der Ausgleichsgeraden mit der Schwelle des Fliessbeginns ({thr}\\,\\% von {ref}).",
        "fig_field": "Gemessene Spannungs-Dehnungs-Kurve{{parts}}. Dehnung aus dem {src}.",
        "fig_field_note": "Die Werkstoffkurven sind idealisiert und dienen nur der Orientierung.",
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
        "tab_kv": "Kennwerte der Messung {n}.", "tab_ref": "Messung {n} im Vergleich mit dem Referenzwerkstoff {r} (Sollwerte, nicht gemessen). Abweichung = (Messung $-$ Referenz)/Referenz. Der Fliessbeginn ist eine Abweichungsschwelle, keine $R_{{p0,2}}$; seine Abweichung von der Referenz dient nur der Orientierung.",
        "tab_cmp": "Kennwerte der Messungen im Vergleich.",
        "col_q": "Kennwert", "col_v": "Wert", "col_meas": "gemessen", "col_ref": "Referenz", "col_dev": "Abweichung",
        "col_name": "Messung",
        "data": "Messdaten der Messung {n}: Zeit, Kraft{more}.",
        "rows": {"a0": "Querschnitt $A_0$", "l0": "Messlänge $L_0$", "v": "Prüfgeschwindigkeit", "yield": "Fliessbeginn ({thr}\\,\\%)",
                 "max_s": "Zugfestigkeit $R_m$", "max_f": "Maximalkraft $F_\\mathrm{{max}}$", "brk": "vor dem Bruch",
                 "drop": "Abfall Maximum bis Bruch", "hold": "Haltezeit über {h}\\,\\%", "ratio": "Verhältnis Maximum/Fliessbeginn",
                 "e": "Elastizitätsmodul (scheinbar)", "k": "Steigung linearer Abschnitt", "r2": "Bestimmtheitsmaß $R^2$",
                 "rate": "Abtastrate", "fmax": "Maximalkraft",
                 "agt": "Gesamtdehnung bei Höchstkraft $A_{gt}$", "ag": "Plastische Dehnung bei Höchstkraft $A_g$",
                 "at": "Gesamtdehnung beim Bruch $A_t$", "a": "Bruchdehnung $A$ ($A_t$ ohne elastischen Anteil)",
                 "app": " (scheinbar)", "yield_ref": "Fliessbeginn ({thr}\\,\\%) / $R_{{p0,2}}$ (nicht gleichartig)"},
        "methods_t": "Methodik", "results_t": "Ergebnisse",
        "src_trav": "Traversenweg (scheinbar)", "src_probe": "Weg an der Probe",
        "phase": {"Setzen": "Setzen", "elastisch": "elastisch", "plastisch": "plastisch", "Abfall": "Abfall",
                  "Anstieg": "Anstieg", "Lastspitzen": "Lastspitzen"},
        "fig_curve_np": "{q}-Zeit-Verlauf der Messung {n} nach Phasen (ohne Einteilung elastisch/plastisch){{parts}}.",
        "fig_dev_np": "Abweichung der Messpunkte von der Ausgleichsgeraden.",
    },
    "en": {
        "title1": "Tensile test {n}", "titleN": "Tensile tests {n}",
        "fig_curve": "{q}--time curve of measurement {n} by phase{{parts}}.",
        "fig_fit": "Data points of measurement {n} against the extended regression line of the linear section.",
        "fig_dev": "Deviation of the data points from the regression line, with the yield-onset threshold ({thr}\\,\\% of {ref}).",
        "fig_field": "Measured stress--strain curve{{parts}}. Strain from the {src}.",
        "fig_field_note": "The material curves are idealised, for orientation only.",
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
        "tab_kv": "Key values of measurement {n}.", "tab_ref": "Measurement {n} compared with the reference material {r} (nominal values, not measured). Deviation = (measurement $-$ reference)/reference. The yield onset is a deviation threshold, not $R_{{p0.2}}$; its deviation from the reference is for orientation only.",
        "tab_cmp": "Key values of the measurements compared.",
        "col_q": "Quantity", "col_v": "Value", "col_meas": "measured", "col_ref": "reference", "col_dev": "deviation",
        "col_name": "Measurement",
        "data": "Measured data of {n}: time, force{more}.",
        "rows": {"a0": "Cross-section $A_0$", "l0": "Gauge length $L_0$", "v": "Test speed", "yield": "Yield onset ({thr}\\,\\%)",
                 "max_s": "Tensile strength $R_m$", "max_f": "Maximum force $F_\\mathrm{{max}}$", "brk": "Before break",
                 "drop": "Drop maximum to break", "hold": "Hold time above {h}\\,\\%", "ratio": "Ratio maximum/yield onset",
                 "e": "Elastic modulus (apparent)", "k": "Slope of linear section", "r2": "Coefficient of determination $R^2$",
                 "rate": "Sampling rate", "fmax": "Maximum force",
                 "agt": "Total extension at maximum force $A_{gt}$", "ag": "Plastic extension at maximum force $A_g$",
                 "at": "Total extension at fracture $A_t$", "a": "Percentage elongation after fracture $A$ ($A_t$ minus elastic part)",
                 "app": " (apparent)", "yield_ref": "Yield onset ({thr}\\,\\%) / $R_{{p0.2}}$ (not like with like)"},
        "methods_t": "Methods", "results_t": "Results",
        "src_trav": "crosshead displacement (apparent)", "src_probe": "displacement measured on the specimen",
        "phase": {"Setzen": "settling", "elastisch": "elastic", "plastisch": "plastic", "Abfall": "drop",
                  "Anstieg": "rise", "Lastspitzen": "load peaks"},
        "fig_curve_np": "{q}--time curve of measurement {n} by phase (not divided into elastic and plastic){{parts}}.",
        "fig_dev_np": "Deviation of the data points from the regression line.",
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
    ("(Kurve aus Quelle)", "(curve from source)"), ("(idealisiert, zur Orientierung)", "(idealised, for orientation)"),
    ("(idealisiert)", "(idealised)"), ("obere Grenze", "upper bound"),
    ("untere Grenze", "lower bound"), ("Fliessbeginn", "Yield onset"), ("Zugfestigkeit", "Tensile strength"),
    ("zurückgestuft", "downgraded"), ("unwahrscheinlich", "unlikely"), ("Kandidat", "Candidate"),
    ("Schwelle", "Threshold"), ("vor Bruch", "before break"), ("Bruch", "Break"), ("Setzen", "Settling"), ("Lastspitzen", "Load peaks"), ("Anstieg", "Rise"),
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
    """A function that draws the figure: labbundle calls it only when the figure is written, so the preview of one
    figure in the hub's editing window does not draw the others."""
    def make():
        fig, ax = plt.subplots(figsize=size)
        draw(ax)
        ax.set_title("")
        _translate(fig, lang, keep)
        fig.tight_layout()
        return fig
    return make


def _norm(r: Result):
    from .analyse import SHAPES
    sh = SHAPES.get(r.config.shape, {}) if r.config.specimen_mode == "norm" else {}
    return NORMS.get(sh.get("norm") or "")


def _cite_cmd(keys):
    return r"\cite{" + ",".join(keys) + "}" if keys else ""


def _safe_url(u: str) -> bool:
    """URL fields go into the .bib unescaped; only plain http(s) links without braces or spaces."""
    return bool(u) and u.startswith(("http://", "https://")) and not any(c in u for c in "{}\\ \n")


_VT_EN = (("Mitte der Spanne", "middle of the range"), ("Mindestwert", "minimum"), ("Höchstwert", "maximum"),
          ("Typwert", "typical"), ("unklar", "unclear"))


def _value_type_text(s: str, lang: str) -> str:
    if lang == "de":
        return s
    for de, en in _VT_EN:
        s = s.replace(de, en)
    return s


def _mat_cite(b: Bundle, a, lang: str) -> str:
    """Literaturangabe der Kennwerte eines Vergleichswerkstoffs (Quelle und Basis aus der Werkstoffdatenbank)."""
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
    note = a.source or ("Quelle nicht angegeben" if lang == "de" else "source not given")
    if getattr(a, "value_type", ""):
        note += ("; Wertart: " if lang == "de" else "; value type: ") + _value_type_text(a.value_type, lang)
    if getattr(a, "check_note", ""):
        note += ("; nicht geprüft: " if lang == "de" else "; not checked: ") + a.check_note
    b.add_citation(key, "misc", title=tex_escape(T[lang]["mat_title"].format(n=a.name)),
                   howpublished=tex_escape(a.basis), note=tex_escape(note),
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
        if r.kv.get("A_pct") is not None:       # A = At − elastischer Anteil (Extensometerverfahren, ISO 6892-1)
            key, number, title, year = NORMS["ISO 6892-1"]
            b.add_citation(key, "misc", title=f"{number}: {title}", author="{" + number.split()[0] + "}", year=year)
            cites["iso6892"] = key
        if r.reference is not None:
            cites["mat"] = _mat_cite(b, r.reference, lang)
        if st and r.comparison and r.strain is not None:
            b.add_citation(RO_KEY, "techreport", author="Ramberg, Walter and Osgood, William R.",
                           title="Description of stress-strain curves by three parameters",
                           institution="National Advisory Committee for Aeronautics", type="Technical Note",
                           number="902", year="1943")
            cites["ro"] = RO_KEY
        if st and r.comparison:
            # jede Vergleichskurve im Feld und jeder Kandidat mit eigener Quelle; Gruppe, zusätzlich eingeblendete
            # Werkstoffe und Referenz getrennt, damit ein weggelassener Teil der Grafik seine Quellen mitnimmt
            members = C.field_members(r)
            n_grp = len(r.alloys or [])
            cites["group"] = [_mat_cite(b, a, lang) for a in members[:n_grp]]
            cites["extra"] = [_mat_cite(b, a, lang) for a in members[n_grp:]]
            cites["field"] = cites["group"] + [k for k in cites["extra"] if k not in cites["group"]]
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
    hthr = kv["hold"]["schwelle"] * 100
    vals.append(("holdthr", "Halteschwelle" if lang == "de" else "Hold threshold", num(hthr, 0, lang) + r"\,\%", f"{hthr:.0f} %"))
    if kv["ratio"] is not None:
        vals.append(("ratio", L["rows"]["ratio"], num(kv["ratio"], 2, lang), f"{kv['ratio']:.2f}"))
    tol =kv["fit"]["tol"]
    vals.append(("tol", "Toleranz Fitfenster" if lang == "de" else "Fit-window tolerance", num(tol, 2, lang, u), f"{tol:.2f} {u}"))
    for key, rk, kk in (("Agt", "agt", "Agt_pct"), ("Ag", "ag", "Ag_pct"), ("At", "at", "At_pct"), ("A", "a", "A_pct")):
        if kv.get(kk) is not None:
            vals.append((key, L["rows"][rk], num(kv[kk], 2, lang, "%"), f"{kv[kk]:.2f} %"))
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
            vals.append(("refdRm", "dRm (Referenz)" if lang == "de" else "dRm (reference)",num(r.ref_cmp["d_rm_pct"], 1, lang, "%"), f"{r.ref_cmp['d_rm_pct']:.1f} %"))
    has_pk = C.has_peaks(r)
    ep_on = (r.kv.get("ep") or {}).get("on", True)
    if has_pk:
        vals += _peak_values(r, lang)
    # die Methodenschritte, die ein einzeln eingefügter Wert braucht (seine Auswertung)
    vneeds = {k: ["linear"] for k in ("yield", "yieldF", "thr", "tol", "ratio")}
    vneeds["E"] = ["linear", "modul"]
    vneeds.update({k: ["haltezeit"] for k in ("hold", "holdthr")})
    vneeds.update({k: ["dehnung"] for k in ("Agt", "Ag", "At", "A")})
    vneeds.update({k: ["referenz"] for k in ("refRm", "refdRm")})
    vneeds.update({k: ["lastspitzen"] for k in ("npk", "pkthr", "pkdelta")})
    vneeds.update({v[0]: ["lastspitzen", "ausgleich"] for v in vals if v[0].startswith("pk") and v[0] not in vneeds})
    if inc.get("values", True):
        b.add_values(vals, needs=vneeds)

    if inc.get("figures", True):
        de = lang == "de"
        # Verlauf: die Phasen folgen aus dem linearen Abschnitt (Fliessbeginn); Marken als Teile
        marks = []
        if ep_on and r.yield_idx is not None:
            marks.append({"id": "fliessbeginn", "label": "Fliessbeginn" if de else "Yield onset", "steps": ["linear"],
                          "caption": (f"Fliessbeginn ({thr}\\,\\% von {ref_lbl})" if de else f"yield onset ({thr}\\,\\% of {ref_lbl})")})
        marks.append({"id": "maximum", "label": "Maximum", "caption": "Maximum" if de else "maximum"})
        if r.break_idx is not None:
            marks.append({"id": "bruch", "label": "Bruch" if de else "Break", "caption": "Bruch" if de else "break"})
        b.add_figure(_fig(lambda ax: C.chart1(r, ax, title=False), lang, keep), "verlauf",
                     L["fig_curve" if ep_on else "fig_curve_np"].format(q=q, n=n), steps=["linear"], parts=marks,
                     parts_lead="mit" if de else ", with")
        b.add_figure(_fig(lambda ax: C.chart2_fit(r, ax, full=True), lang, keep), "linear", L["fig_fit"].format(n=n),
                     steps=["linear"])
        b.add_figure(_fig(lambda ax: C.chart2_dev(r, ax), lang, keep, (6.4, 2.8)), "abweichung",
                     L["fig_dev" if ep_on else "fig_dev_np"].format(thr=thr, ref=ref_lbl), steps=["linear"])
        if st and r.strain is not None and r.comparison:
            src = L["src_probe"] if r.config.displacement_source == "probe" else L["src_trav"]
            n_field = len(C.field_members(r))
            fparts = []
            if r.alloys:
                own = any(getattr(a, "curve", None) for a in C.field_members(r)[:len(r.alloys)])
                fparts.append({"id": "feld", "label": (f"Feld der Gruppe {r.group}" if de else f"Field of the group {r.group}"),
                               "cites": cites.get("group", []), "steps": ["vergleich"],
                               "caption": (f"im Feld der Vergleichsgruppe {tex_escape(r.group)}" if de else
                                           f"within the field of the comparison group {tex_escape(r.group)}"),
                               "note": L["fig_field_note"] + L["fig_field_key"]
                                       + ((" Werkstoffe mit eigener Kurve sind nicht idealisiert, sondern aus der angegebenen "
                                           "Quelle übernommen." if de else
                                           " Materials with their own curve are not idealised but taken from the source given.")
                                          if own else "")})
            if r.extras:
                nr0 = n_field - len(r.extras)
                lst = ", ".join(f"{nr0 + i + 1}~{tex_escape(a.name)}" for i, a in enumerate(r.extras))
                fparts.append({"id": "zusatz", "label": "Zusätzlich eingeblendete Werkstoffe" if de else "Additional materials",
                               "cites": cites.get("extra", []), "steps": ["zusatz"],
                               "note": (f"Zusätzlich eingeblendet (farbig, nicht Teil des Felds): {lst}." if de else
                                        f"Additionally shown (coloured, not part of the field): {lst}.")})
            if r.reference is not None:
                fparts.append({"id": "referenz", "label": (f"Referenz {r.reference.name}" if de else f"Reference {r.reference.name}"),
                               "cites": [cites["mat"]] if "mat" in cites else [], "steps": ["referenz"],
                               "caption": (f"mit dem Referenzwerkstoff {tex_escape(r.reference.name)}" if de else
                                           f"with the reference material {tex_escape(r.reference.name)}")})
            b.add_figure(_fig(lambda ax: C.chart3(r, ax, title=False, key="below"), lang, keep,
                              (6.4, 4.0 + C.key_height_in(n_field))), "feld",
                         L["fig_field"].format(src=src), steps=[], parts=fparts, parts_lead="")
        if st and r.comparison:
            b.add_figure(_fig(lambda ax: C.chart4(r, ax, title=False), lang, keep), "kandidaten",
                         L["fig_cand"].format(g=tex_escape(r.group)), cites=cites.get("cand"),
                         steps=["vergleich", "rangfolge"] + (["referenz"] if r.reference is not None else []))
        b.add_figure(_fig(lambda ax: C.specimen_sketch(r, ax), lang, keep, (5.0, 2.0)), "probe",
                     L["fig_sketch"].format(s=tex_escape(specimen_label(r))), width="0.6", steps=[])
        if has_pk:
            _peak_figures(b, r, lang, keep)

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
        app = R["app"] if r.config.displacement_source != "probe" else ""
        for rk, kk in (("agt", "Agt_pct"), ("ag", "Ag_pct"), ("at", "At_pct"), ("a", "A_pct")):
            if kv.get(kk) is not None:
                rows.append([R[rk] + app, num(kv[kk], 2, lang, "%")])
        rows.append([R["k"], num(kv["fit"]["k_N_s"], 3, lang, "N/s")])
        rows.append([R["r2"], num(kv["fit"]["r2"], 5, lang)])
        b.add_table("kennwerte", booktabs([L["col_q"], L["col_v"]], rows), L["tab_kv"].format(n=n),
                    steps=["linear", "haltezeit", "dehnung", "modul"])
        if r.reference is not None and st:
            ref = r.reference
            rr = [[R["max_s"], num(kv["Rm"], 0, lang), num(ref.rm, 0, lang), num(100 * (kv["Rm"] - ref.rm) / ref.rm, 1, lang, "%")]]
            if y and ref.rp:
                rr.append([R["yield_ref"].format(thr=thr),
                           num(y["y"], 0, lang), num(ref.rp, 0, lang), num(100 * (y["y"] - ref.rp) / ref.rp, 1, lang, "%")])
            if r.e_schein_gpa is not None:
                rr.append([R["e"] + " [GPa]", num(r.e_schein_gpa, 1, lang), num(ref.e_gpa, 1, lang),
                           num(100 * (r.e_schein_gpa - ref.e_gpa) / ref.e_gpa, 0, lang, "%")])
            b.add_table("referenz", booktabs([L["col_q"] + " [MPa]", L["col_meas"], L["col_ref"], L["col_dev"]], rr, "lrrr"),
                        L["tab_ref"].format(n=n, r=tex_escape(ref.name)), cites=cites.get("mat"),
                        steps=["referenz", "linear", "modul"])
        if st and r.comparison and "field" in cites:
            _source_tables(b, r, lang, cites)
        if has_pk:
            _peak_tables(b, r, lang)

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
        at = b.added_mark()
        eq_text = Fm.to_report(b, r.equations, lang, cite_prefix="eq").get("latex", "")
        _eq_needs(b, at, ["gleichungen"])

    uo = None
    if r.unc and inc.get("values", True):              # Messunsicherheit: Werte ±, Budgettabellen, Methodentext
        from . import uncertainty as UNC
        n_items, n_vals = len(b.items), len(b.values)
        uo = UNC.to_report(b, r, lang)
        if uo:                                          # Werte ± und Budgettabellen brauchen den Unsicherheitsschritt
            for v in b.values[n_vals:]:
                v["needs"] = ["unsicherheit"]
            for it in b.items[n_items:]:
                if it.get("kind") == "table":
                    it["needs"] = {"steps": ["unsicherheit"]}

    if inc.get("text", True):
        _texts(b, r, lang, cites, eq_text, uo)


def _eq_needs(b: Bundle, at: tuple, steps: list[str]):
    """Eigene Gleichungen: Tabelle, Budgets und Werte seit ``at`` brauchen den Gleichungsblock des Methodentexts."""
    for it in b.items[at[0]:]:
        if it.get("kind") == "table":
            it["needs"] = {"steps": list(steps)}
    b.needs_since(at, steps)


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
        mark = "*" if getattr(a, "check_note", "") else ""
        rows.append((key, [nr, tex_escape(a.name) + mark, num(a.rp, 0, lang) if a.rp else "--", num(a.rm, 0, lang),
                           num(a.a_pct, 0, lang), num(a.e_gpa, 1, lang), cite([key], sep="")]))
    star = any(getattr(a, "check_note", "") for _, a in entries)
    star_txt = (" Mit * markierte Einträge sind nicht geprüft (Grund in der Literaturangabe)." if lang == "de" else
                " Entries marked * are not checked (reason in the reference).") if star else ""
    wood = any(a.category == "Holz" for _, a in entries)
    wood_txt = (" Holz: $E$ ist der Biege-Elastizitätsmodul, nicht der Zug-Elastizitätsmodul." if lang == "de" else
                " Wood: $E$ is the modulus of elasticity in bending, not in tension.") if wood else ""
    for k in range(0, len(rows), per_table):
        chunk = rows[k:k + per_table]
        b.add_table("werkstoffe" + (f"-{k // per_table + 1}" if k else ""),
                    booktabs(L["h_src"], [row for _, row in chunk], "rlrrrrl", small=True, escape_header=False),
                    L["tab_src"].format(g=tex_escape(r.group), cont=L["cont"] if k else "") + star_txt + wood_txt,
                    cites=[key for key, _ in chunk],
                    steps=["vergleich"] + (["zusatz"] if r.extras else []) + (["referenz"] if r.reference is not None else []))


def _texts(b: Bundle, r: Result, lang: str, cites: dict, eq_text: str = "", uo: dict | None = None):
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
    grp = cites.get("group") or cites.get("field") or []
    # Methodenschritte als (id, Text): Grafiken, Tabellen und Werte nennen die ids, die sie brauchen (add_figure steps)
    if lang == "de":
        if o:
            cols = " und ".join(f"{tex_escape(x['name'])} [{unit_of(x)}]" for x in (rl.get("load"), rl.get("ext")) if x)
            m = [("messung", f"Ausgewertet wurde der Datensatz ,,{tex_escape(o.get('title') or r.name)}`` (Version {o.get('version') or '?'})"
                 f"{data_c} einer Probe {spec}{norm_c} mit den Spalten {cols}.")]
            if o.get("time_from") == "elongation":
                m.append(("zeitachse", f"Die Zeitachse der Auswertung wurde aus dem zurückgelegten Weg und der Prüfgeschwindigkeit {V('v')} "
                         "berechnet; Dehnung und Modul folgen damit dem gemessenen Weg."))
            elif c.speed_mm_min:
                m.append(("geschwindigkeit", f"Die Prüfgeschwindigkeit betrug {V('v')}."))
        else:
            m = [("messung", f"Die Zugprüfung erfolgte an einer Probe {spec}{norm_c} auf einem Kraftmessgerät IMADA {tex_escape(d['model'])}"
                 f" (SN {tex_escape(d['serial'])}){data_c}.")]
            if c.speed_mm_min:
                m.append(("geschwindigkeit", f"Die Prüfgeschwindigkeit betrug {V('v')}, die Kraft wurde mit {V('rate')} aufgezeichnet."))
            else:
                m.append(("geschwindigkeit", f"Die Kraft wurde mit {V('rate')} aufgezeichnet; die Prüfgeschwindigkeit ist nicht dokumentiert."))
        if st:
            m.append(("spannung", f"Die Spannung bezieht sich auf den Ausgangsquerschnitt $A_0 = $ {V('A0')}."))
        m.append(("linear", "Der lineare Abschnitt wurde ausgehend von der Stelle der grössten Steigung schrittweise um je einen "
                 "Messpunkt nach links und nach rechts erweitert, solange alle Messpunkte des Fensters um weniger als "
                 f"{V('tol')} von ihrer Ausgleichsgeraden abweichen; die Suche endet, sobald keine Seite mehr wachsen kann "
                 "(gierige Suche, nicht notwendig das längste solche Fenster). " + _ep_text(r, "de", V)))
        m.append(("haltezeit", f"Als Haltezeit gilt die Dauer des zusammenhängenden Abschnitts um das Maximum, in dem die Last mindestens "
                 f"{V('holdthr')} des Maximums beträgt."))
        if r.kv.get("A_pct") is not None:
            iso_c = (" " + _cite_cmd([cites["iso6892"]])) if "iso6892" in cites else ""
            m.append(("dehnung", "Die Dehnung wurde ab dem Fusspunkt der Ausgleichsgeraden gezählt. Die Bruchdehnung $A$ und die "
                     "plastische Dehnung bei Höchstkraft $A_g$ wurden wie beim Extensometerverfahren" + iso_c + " aus den "
                     "Gesamtdehnungen $A_t$ und $A_{gt}$ unter Last bestimmt, abzüglich des elastischen Anteils (Spannung "
                     "geteilt durch die Steigung des linearen Abschnitts derselben Kurve)."))
        if c.displacement_source != "probe" and r.e_schein_gpa is not None:
            m.append(("modul", "Ob der Weg an der Probe gemessen wurde, ist nicht dokumentiert; der berechnete Modul ist deshalb ein "
                     "scheinbarer Wert." if o else
                     "Die Dehnung stammt aus dem Traversenweg und enthält die Nachgiebigkeit des Aufbaus; der daraus "
                     "berechnete Modul ist ein scheinbarer Wert."))
        if cites.get("field"):
            ro_c = ("~" + _cite_cmd([cites["ro"]])) if "ro" in cites else ""
            m.append(("vergleich", f"Verglichen wurde mit den {len(r.alloys)} Werkstoffen der Gruppe {tex_escape(r.group)}; "
                     "ihre Spannungs-Dehnungs-Kurven sind aus den Kennwerten $R_{p0,2}$, $R_m$, $A$ und $E$ "
                     "idealisiert (elastisch mit $E$, dann die Beziehung nach Ramberg und Osgood" + ro_c + " durch "
                     "$R_{p0,2}$ und $R_m$ bei $0{,}55\\,A$, danach ein linearer Abfall um 7\\,\\% bis $A$; ohne "
                     "$R_{p0,2}$ elastisch bis $R_m$). Sie dienen nur der Orientierung und sind keine Messkurven "
                     f"(Kennwerte nach{cite(grp)})."))
            m.append(("rangfolge", "Rangfolge der Kandidaten: zuerst nach Status, bei gleichem Status nach der Abweichung in $R_m$ "
                     "bezogen auf den Wert des Werkstoffs; das Verhältnis von Maximum zu Fliessbeginn senkt nur den "
                     "Status, weil der Fliessbeginn eine Schwelle und keine $R_{p0,2}$ ist."))
            if r.extras and cites.get("extra"):
                lst = ", ".join(tex_escape(a.name) for a in r.extras)
                m.append(("zusatz", f"Zusätzlich eingeblendet, aber nicht Teil des Vergleichs, sind {lst}; ihre Kurven sind "
                                    f"auf dieselbe Weise idealisiert (Kennwerte nach{cite(cites['extra'])})."))
        if r.reference is not None and "mat" in cites:
            m.append(("referenz", f"Als Referenzwerkstoff dient {tex_escape(r.reference.name)} mit Sollwerten "
                                  f"nach{cite([cites['mat']])}; diese Werte sind nicht gemessen."))
        res = []
        if st:
            res.append(f"Die Probe erreichte eine Zugfestigkeit von {V('Rm')} (Maximalkraft {V('Fmax')} nach {V('tmax')}).")
        else:
            res.append(f"Die Maximalkraft betrug {V('Fmax')} nach {V('tmax')}.")
        if r.kv["yield"]:
            res.append(f"Der Fliessbeginn lag bei {V('yield')}, das Verhältnis von Maximum zu Fliessbeginn bei {V('ratio')}.")
        if r.kv["drop"]:
            res.append(f"Vom Maximum bis zum Bruch fiel die Last um {V('drop')}; die Last blieb {V('hold')} ohne "
                       f"Unterbrechung über {V('holdthr')} des Maximums.")
        if r.kv.get("A_pct") is not None:
            app = " (scheinbar, Weg nicht an der Probe gemessen)" if c.displacement_source != "probe" else ""
            res.append(f"Die Gesamtdehnung beim Bruch betrug $A_t = $ {V('At')}, die Bruchdehnung nach Abzug des "
                       f"elastischen Anteils $A = $ {V('A')}{app}.")
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
            m = [("messung", f"The dataset ``{tex_escape(o.get('title') or r.name)}'' (version {o.get('version') or '?'}){data_c} of a "
                 f"specimen {spec}{norm_c} was evaluated, with the columns {cols}.")]
            if o.get("time_from") == "elongation":
                m.append(("zeitachse", f"The time axis of the evaluation was calculated from the travelled displacement and the test speed "
                         f"{V('v')}, so strain and modulus follow the measured displacement."))
            elif c.speed_mm_min:
                m.append(("geschwindigkeit", f"The test speed was {V('v')}."))
        else:
            m = [("messung", f"The tensile test was carried out on a specimen {spec}{norm_c} using an IMADA {tex_escape(d['model'])} force "
                 f"gauge (SN {tex_escape(d['serial'])}){data_c}.")]
            if c.speed_mm_min:
                m.append(("geschwindigkeit", f"The test speed was {V('v')}; force was recorded at {V('rate')}."))
            else:
                m.append(("geschwindigkeit", f"Force was recorded at {V('rate')}; the test speed was not documented."))
        if st:
            m.append(("spannung", f"Stress refers to the initial cross-section $A_0 = $ {V('A0')}."))
        m.append(("linear", "The linear section was found by growing a window from the point of steepest slope, one data point at a "
                 "time to the left and to the right, as long as all points of the window deviate from their regression "
                 f"line by less than {V('tol')}; the search stops when neither side can grow (a greedy search, not "
                 "necessarily the longest such window). " + _ep_text(r, "en", V)))
        m.append(("haltezeit", f"The hold time is the duration of the contiguous section around the maximum in which the load stays at "
                 f"or above {V('holdthr')} of the maximum."))
        if r.kv.get("A_pct") is not None:
            iso_c = (" " + _cite_cmd([cites["iso6892"]])) if "iso6892" in cites else ""
            m.append(("dehnung", "Strain was counted from the foot point of the regression line. The percentage elongation after "
                     "fracture $A$ and the plastic extension at maximum force $A_g$ were obtained as in the extensometer "
                     "method" + iso_c + " from the total extensions under load $A_t$ and $A_{gt}$, minus the elastic part "
                     "(stress divided by the slope of the linear section of the same curve)."))
        if c.displacement_source != "probe" and r.e_schein_gpa is not None:
            m.append(("modul", "Whether the displacement was measured on the specimen is not documented, so the calculated modulus is "
                     "an apparent value." if o else
                     "Strain was derived from the crosshead displacement and includes the compliance of the set-up; the "
                     "modulus calculated from it is an apparent value."))
        if cites.get("field"):
            ro_c = ("~" + _cite_cmd([cites["ro"]])) if "ro" in cites else ""
            m.append(("vergleich", f"The measurement was compared with the {len(r.alloys)} materials of the group "
                     f"{tex_escape(r.group)}; their stress--strain curves are idealised from $R_{{p0.2}}$, $R_m$, $A$ and $E$ "
                     "(elastic with $E$, then the Ramberg--Osgood relation" + ro_c + " through $R_{p0.2}$ and $R_m$ at "
                     "$0.55\\,A$, then a linear drop of 7\\,\\% to $A$; without $R_{p0.2}$ elastic up to $R_m$). They are "
                     f"for orientation only and are not measured curves (property values from{cite(grp)})."))
            m.append(("rangfolge", "Candidates are ranked first by status and, within the same status, by the deviation in $R_m$ "
                     "relative to the material value; the ratio of maximum to yield onset only lowers the status, because "
                     "the yield onset is a threshold, not $R_{p0.2}$."))
            if r.extras and cites.get("extra"):
                lst = ", ".join(tex_escape(a.name) for a in r.extras)
                m.append(("zusatz", f"Also shown, but not part of the comparison: {lst}; their curves are idealised in the "
                                    f"same way (property values from{cite(cites['extra'])})."))
        if r.reference is not None and "mat" in cites:
            m.append(("referenz", f"The reference material is {tex_escape(r.reference.name)}, with nominal values "
                                  f"from{cite([cites['mat']])}; these values are not measured."))
        res = []
        if st:
            res.append(f"The specimen reached a tensile strength of {V('Rm')} (maximum force {V('Fmax')} after {V('tmax')}).")
        else:
            res.append(f"The maximum force was {V('Fmax')} after {V('tmax')}.")
        if r.kv["yield"]:
            res.append(f"Yield onset was at {V('yield')}; the ratio of maximum to yield onset was {V('ratio')}.")
        if r.kv["drop"]:
            res.append(f"From the maximum to the break the load dropped by {V('drop')}; it stayed above {V('holdthr')} "
                       f"of the maximum for {V('hold')} without interruption.")
        if r.kv.get("A_pct") is not None:
            app = " (apparent; displacement not measured on the specimen)" if c.displacement_source != "probe" else ""
            res.append(f"The total extension at fracture was $A_t = $ {V('At')}, the percentage elongation after fracture "
                       f"without the elastic part $A = $ {V('A')}{app}.")
        if r.reference is not None and st:
            mat_c = (" " + _cite_cmd([cites["mat"]])) if "mat" in cites else ""
            res.append(f"Compared with the reference material {tex_escape(r.reference.name)} ($R_m = $ {V('refRm')}{mat_c}), "
                       f"the tensile strength deviates by {V('refdRm')}. Agreement in $R_m$ alone does not identify the material.")
        if r.e_schein_gpa is not None:
            res.append(f"The apparent modulus of {V('E')} is not a material property.")
    if C.has_peaks(r):
        pm, pr = _peak_texts(r, lang, V)
        m += pm
        res += pr
    L = T[lang]
    # jeder Satz ein Schritt mit laufender id (s1, s2, ...: gespeicherte Auswahl und Satzänderungen bleiben gültig),
    # "of" nennt die Auswertung, zu der er gehört; neue Schritte (zusatz, referenz) stehen deshalb hinten
    m = [x for x in m if x[0] not in ("zusatz", "referenz")] + [x for x in m if x[0] in ("zusatz", "referenz")]
    steps = []
    for sid, txt in m:
        for sent in split_sentences(txt.replace("$ \\labval", "$\\labval")):
            steps.append({"of": sid, "text": sent})
    if uo:
        steps.append({"id": "unsicherheit", "title": "Messunsicherheit" if lang == "de" else "Measurement uncertainty",
                      "text": "\n\n" + uo["latex"]})
        got = [f"{tex_escape(x['label'])} {V(x['name'] + '-pm')}" for x in uo["results"].values()]
        res.append(("Mit Messunsicherheit: " if lang == "de" else "With measurement uncertainty: ") + "; ".join(got) + ".")
    # ein Satz für ein eingefügtes Stück ohne Auswertung (eine reine Messkurve): Messung, Norm, Software
    clause = b.software_clause()
    if o:       # der erste Satz sagt bei einem Datensatz schon "ausgewertet"
        clause = ("Software: " if lang == "de" else "software: ") + clause.split(" ", 2)[2]
    brief = m[0][1].replace("$ \\labval", "$\\labval").rstrip().rstrip(".") + "; " + clause + "."
    b.add_methods(steps, L["methods_t"], sep=" ", eq=eq_text or "", brief=brief)
    used = {s.get("of") or s.get("id") for s in steps}
    b.add_text("ergebnisse", " ".join(res) + "\n", L["results_t"],
               steps=[s for s in ("linear", "haltezeit", "dehnung", "modul", "referenz", "lastspitzen", "ausgleich",
                                  "unsicherheit") if s in used])


def _ep_text(r: Result, lang: str, V) -> str:
    """Methodensatz zur Einteilung elastisch/plastisch (Fliessbeginn), je nach Einstellung und Kurve."""
    ep = r.kv.get("ep") or {"on": True, "progressive": False, "setting": "auto"}
    de = lang == "de"
    if ep["on"]:
        until = (("vor der ersten Lastspitze" if de else "before the first load peak") if ep["progressive"]
                 else ("vor dem Maximum" if de else "before the maximum"))
        if de:
            return (f"Als Fliessbeginn gilt der erste Messpunkt nach diesem Fenster und {until}, der um mehr als "
                    f"{V('thr')} des Maximums von der verlängerten Geraden abweicht. Diese Schwelle ist eine Festlegung "
                    "und keine Dehngrenze $R_{p0,2}$.")
        return (f"Yield onset is the first point after this window and {until} that deviates from the extended line "
                f"by more than {V('thr')} of the maximum. This threshold is a convention, not a proof stress $R_{{p0.2}}$.")
    n_pk = (r.kv.get("peaks") or {}).get("n", 0)
    if de:
        why = (f", weil die Kurve {n_pk} Lastspitzen zeigt (fortschreitendes Versagen: Teile versagen nacheinander, eine "
               "Grenze auf der Kraftkurve beschreibt keinen Werkstoffzustand)" if ep["setting"] == "auto"
               else " (abgeschaltet)")
        return (f"Die Kurve wurde nicht in elastisch und plastisch eingeteilt{why}; sie ist in Anstieg"
                + (", Lastspitzen" if ep["progressive"] else "") + " und Abfall gegliedert. Ein Fliessbeginn und die "
                "plastischen Dehnungen $A_g$ und $A$ werden nicht angegeben; die Steigung des linearen Abschnitts "
                "beschreibt die Steifigkeit des Anstiegs.")
    why = (f" because the curve shows {n_pk} load peaks (progressive failure: parts fail one after another, so a limit "
           "on the force curve does not describe a state of the material)" if ep["setting"] == "auto" else " (switched off)")
    return (f"The curve was not divided into elastic and plastic{why}; it is divided into rise"
            + (", load peaks" if ep["progressive"] else "") + " and drop. No yield onset and no plastic extensions "
            "$A_g$ and $A$ are given; the slope of the linear section describes the stiffness of the rise.")


# ----------------------------------------------------------------------------- Lastspitzen (fortschreitendes Versagen)
PEAK_ROWS_PER_TABLE = 40
_MODEL = {"de": {"line": "Gerade", "exp": "Exponentialfunktion"}, "en": {"line": "straight line", "exp": "exponential"}}
_FORMULA = {"line": r"$y = a + b\,x$", "exp": r"$y = a\,\mathrm{e}^{b x}$"}


def _nd_sig(u, v, sig_u: int = 2, sig_v: int = 4) -> int:
    """Nachkommastellen: 2 geltende Ziffern der Unsicherheit, ohne sie 4 geltende Ziffern des Werts."""
    import math
    ref, sig = (u, sig_u) if (u is not None and u > 0 and math.isfinite(u)) else (abs(v) if v else 1.0, sig_v)
    if not ref or not math.isfinite(ref):
        return 2
    return max(0, min(8, sig - 1 - int(math.floor(math.log10(ref)))))


def _pm(v, u, lang, unit="") -> tuple[str, str]:
    """(LaTeX, Text) für Wert ± Standardunsicherheit."""
    nd = _nd_sig(u, v)
    if u is None:
        return num(v, nd, lang, unit), f"{v:.{nd}f} {unit}".strip()
    return (num(v, nd, lang) + r" $\pm$ " + num(u, nd, lang, unit), f"{v:.{nd}f} ± {u:.{nd}f} {unit}".strip())


def _x_text(pk: dict, lang: str) -> str:
    app = pk.get("x_apparent")
    if lang == "de":
        return {"strain": "die Dehnung bei der Spitze ($100\\,v\\,(t - t_0)/L_0$" + (", scheinbar)" if app else ")"),
                "travel": "den Traversenweg $v\\,(t - t_0)$ bei der Spitze (enthält die Nachgiebigkeit des Aufbaus)",
                "time": "die Zeit $t$ bei der Spitze (ohne Prüfgeschwindigkeit gibt es keine Verlängerung)"}[pk["x_kind"]]
    return {"strain": "the strain at the peak ($100\\,v\\,(t - t_0)/L_0$" + (", apparent)" if app else ")"),
            "travel": "the crosshead travel $v\\,(t - t_0)$ at the peak (it includes the compliance of the set-up)",
            "time": "the time $t$ at the peak (without a test speed there is no elongation)"}[pk["x_kind"]]


def _peak_values(r: Result, lang: str) -> list:
    pk = r.kv["peaks"]
    de = lang == "de"
    u = r.unit
    nd = _nd_sig(None, pk["delta"], sig_v=3)
    vals = [("npk", "Anzahl Lastspitzen" if de else "Number of load peaks", str(pk["n"]), str(pk["n"])),
            ("pkthr", "Schwelle Lastabfall" if de else "Load-drop threshold", num(pk["frac"] * 100, 1, lang) + r"\,\%",
             f"{pk['frac'] * 100:.1f} %"),
            ("pkdelta", "Mindestabfall Delta" if de else "Minimum drop Delta", num(pk["delta"], nd, lang, u),
             f"{pk['delta']:.{nd}f} {u}")]
    fit = pk.get("fit") or {}
    if not fit.get("reason"):
        vals.append(("pkn", "Spitzen im Ausgleich" if de else "Peaks in the fit", str(fit["n"]), str(fit["n"])))
        for m, tag in (("line", "L"), ("exp", "E")):
            d = fit.get(m)
            if not (d and d.get("ok")):
                continue
            name = _MODEL[lang][m]
            for p in ("a", "b"):
                lx, tx = _pm(d[p], d[p + "_u"], lang, d[p + "_unit"])
                vals.append((f"pk{tag}{p}", f"{name}: {p}", lx, tx))
            vals.append((f"pk{tag}R2", f"{name}: R2", num(d["r2"], 4, lang), f"{d['r2']:.4f}"))
        if fit.get("best"):
            nm = _MODEL[lang][fit["best"]]
            vals.append(("pkbest", "Besseres Modell" if de else "Better model", nm, nm))
    return vals


def _peak_figures(b: Bundle, r: Result, lang: str, keep: set[str]):
    pk = r.kv["peaks"]
    n = tex_escape(r.name)
    nd = _nd_sig(None, pk["delta"], sig_v=3)
    d = num(pk["delta"], nd, lang, r.unit)
    fit = pk.get("fit") or {}
    best = fit.get("best")
    de = lang == "de"
    # was die Grafik zeigt, als abschaltbare Teile: Spitzen, Täler, Hüllkurve (Ausgleich)
    parts = [{"id": "spitzen", "label": "Lastspitzen" if de else "Load peaks", "steps": ["lastspitzen"],
              "caption": (f"{pk['n']} nummerierten Lastspitzen (je mit einem Lastabfall von mindestens {d} danach)" if de else
                          f"{pk['n']} numbered load peaks (each followed by a load drop of at least {d})")},
             {"id": "taeler", "label": "Täler" if de else "Valleys", "steps": ["lastspitzen"],
              "caption": "den Tälern dazwischen" if de else "the valleys between them"}]
    if best:
        dat = {"line": "Geraden", "exp": "Exponentialfunktion"}[best]
        parts.append({"id": "huellkurve", "label": "Hüllkurve" if de else "Envelope", "steps": ["lastspitzen", "ausgleich"],
                      "caption": (f"der besser passenden {dat} der Spitzenlasten als Hüllkurve" if de else
                                  f"the better-fitting {_MODEL['en'][best]} of the peak loads as envelope")})
    cap = (f"Verlauf der Messung {n} (fortschreitendes Versagen){{parts}}." if de else
           f"Curve of measurement {n} (progressive failure){{parts}}.")
    b.add_figure(_fig(lambda ax: C.peaks_curve(r, ax, lang), lang, keep), "lastspitzen", cap, steps=[], parts=parts,
                 parts_lead="mit" if de else ", with")
    if best:
        cap = (f"Spitzenlasten der Messung {n} über {_x_text(pk, 'de')} mit Ausgleichsgerade und Exponentialfunktion "
               "(beide direkt nach kleinsten Quadraten in $y$); durchgezogen und kräftig die besser passende."
               if lang == "de" else
               f"Peak loads of measurement {n} against {_x_text(pk, 'en')} with a straight line and an exponential "
               "(both direct least squares in $y$); solid and bold: the better fit.")
        b.add_figure(_fig(lambda ax: C.peaks_fit_chart(r, ax, lang), lang, keep, (6.4, 3.4)), "lastspitzen-ausgleich",
                     cap, steps=["lastspitzen", "ausgleich"])


def _peak_tables(b: Bundle, r: Result, lang: str):
    pk = r.kv["peaks"]
    de = lang == "de"
    st = r.mode == "Spannung"
    n = tex_escape(r.name)
    xu = tex_escape(pk["x_unit"])
    has_w = any(e["W_J"] is not None for e in pk["list"])
    head = ["Nr.", "$t$ [s]", f"$x$ [{xu}]", "$F$ [N]"] + (["$\\sigma$ [MPa]"] if st else []) + \
        [("Abfall" if de else "Drop") + " [\\%]", ("Dauer" if de else "Duration") + " [s]", "$F_i/F_{i-1}$",
         "$k$ [N/s]"] + (["$W$ [J]"] if has_w else [])
    xnd = 1 if pk["x_unit"] == "s" else 2
    rows = []
    for e in pk["list"]:
        rows.append([str(e["nr"]) + ("*" if e.get("excluded") else ""), num(e["t"], 1, lang), num(e["x"], xnd, lang),
                     num(e["F"], 1, lang)] + ([num(e["y"], 1, lang)] if st else [])
                    + [num(e["drop_pct"], 1, lang), num(e["dauer"], 1, lang), num(e["ratio"], 3, lang),
                       num(e["k_N_s"], 3, lang)] + ([num(e["W_J"], 4, lang)] if has_w else []))
    dt = num(pk["dt"], 2, lang, "s") if pk.get("dt") else "--"
    star = any(e.get("excluded") for e in pk["list"])
    if de:
        cap = (f"Lastspitzen der Messung {n}. $x$: {_x_text(pk, 'de')}. Abfall: von der Spitze bis zum Tal danach, in "
               f"\\% der Spitze; Dauer: Spitze bis Tal ($\\pm$ ein Abtastintervall, {dt}); $F_i/F_{{i-1}}$: Verhältnis "
               "zur vorigen Spitze; $k$: Steigung des Wiederanstiegs zwischen 20 und 80\\,\\% des Anstiegs vom vorigen "
               "Tal (erste Spitze: ab $t_0$)"
               + ("; $W$: Arbeit vom vorigen Tal bis zum Tal nach der Spitze" if has_w else "")
               + (". * nicht im Ausgleich" if star else "") + ".")
        cont = ", Fortsetzung"
    else:
        cap = (f"Load peaks of measurement {n}. $x$: {_x_text(pk, 'en')}. Drop: from the peak to the following valley, "
               f"in \\% of the peak; duration: peak to valley ($\\pm$ one sampling interval, {dt}); $F_i/F_{{i-1}}$: "
               "ratio to the previous peak; $k$: slope of the reloading between 20 and 80\\,\\% of the rise from the "
               "previous valley (first peak: from $t_0$)"
               + ("; $W$: work from the previous valley to the valley after the peak" if has_w else "")
               + (". * excluded from the fit" if star else "") + ".")
        cont = ", continued"
    align = "r" * len(head)
    for k in range(0, len(rows), PEAK_ROWS_PER_TABLE):
        b.add_table("lastspitzen" + (f"-{k // PEAK_ROWS_PER_TABLE + 1}" if k else ""),
                    booktabs(head, rows[k:k + PEAK_ROWS_PER_TABLE], align, small=True, escape_header=False),
                    cap if not k else cap.split(". ")[0] + cont + ".", steps=["lastspitzen"])
    fit = pk.get("fit") or {}
    if fit.get("reason"):
        return
    frows = []
    for m in ("line", "exp"):
        d = fit.get(m)
        if not d:
            continue
        name = _MODEL[lang][m].capitalize() + " " + _FORMULA[m]
        if fit.get("best") == m:
            name = r"\textbf{" + name + "}"
        if not d.get("ok"):
            frows.append([name, "--", tex_escape(str(d.get("error"))), "", "", ""])
            continue
        for p in ("a", "b"):
            nd = _nd_sig(d[p + "_u"], d[p])
            frows.append([name if p == "a" else "", f"${p}$", num(d[p], nd, lang), num(d[p + "_u"], nd, lang),
                          num(d[p + "_ci"], nd, lang), tex_escape(d[p + "_unit"] or "")])
        frows.append(["", "$R^2$", num(d["r2"], 4, lang), "", "", ""])
    head = [("Modell" if de else "Model"), ("Parameter" if de else "Parameter"), ("Wert" if de else "Value"),
            "$u$", "$\\pm$ 95\\,\\%", ("Einheit" if de else "Unit")]
    nfit = fit["n"]
    if de:
        cap = (f"Ausgleich der Spitzenlasten der Messung {n} über {_x_text(pk, 'de')} mit {nfit} Spitzen. Beide Modelle "
               "direkt nach kleinsten Quadraten in $y$; beide haben zwei Parameter und dieselben $y$, also ist das Modell "
               "mit der kleineren Summe der Fehlerquadrate (dem grösseren $R^2$) das bessere (fett). $u$: "
               f"Standardunsicherheit; 95\\,\\%: Vertrauensbereich mit dem Student-$t$-Quantil für {nfit - 2} "
               "Freiheitsgrade.")
    else:
        cap = (f"Fit of the peak loads of measurement {n} against {_x_text(pk, 'en')}, {nfit} peaks. Both models are "
               "direct least squares in $y$; both have two parameters and the same $y$, so the model with the smaller "
               "sum of squared residuals (the larger $R^2$) is the better one (bold). $u$: standard uncertainty; "
               f"95\\,\\%: confidence interval with the Student $t$ quantile for {nfit - 2} degrees of freedom.")
    b.add_table("lastspitzen-ausgleich", booktabs(head, frows, "llrrrl", small=True, escape_header=False), cap,
                steps=["lastspitzen", "ausgleich"])


def _peak_texts(r: Result, lang: str, V) -> tuple[list[tuple[str, str]], list[str]]:
    pk = r.kv["peaks"]
    st = r.mode == "Spannung"
    ref = "$R_m$" if st else "$F_\\mathrm{max}$"
    fit = pk.get("fit") or {}
    best = fit.get("best")
    res_lim = pk["delta_basis"] == "aufloesung"
    if lang == "de":
        m = [("lastspitzen", f"Lastspitzen (fortschreitendes Versagen) wurden mit einer Schwellenregel mit Hysterese erkannt: Ein "
             f"laufendes Maximum gilt als Lastspitze, sobald die Last um mindestens $\\Delta = $ {V('pkdelta')} darunter "
             f"fällt ({V('pkthr')} von {ref}, mindestens das Dreifache der Anzeigeauflösung"
             + (", hier massgebend" if res_lim else "") + "); danach wird das Minimum (Tal) verfolgt, bis die Last "
             "wieder um mindestens $\\Delta$ darüber steigt, und die Suche nach der nächsten Spitze beginnt dort. Bei "
             "einem flachen Maximum oder Minimum zählt der erste Punkt; nach der letzten Spitze ist das Tal das Minimum "
             "bis zum Ende des aktiven Abschnitts. Die Schwelle ist eine Festlegung, keine Norm.")]
        if not fit.get("reason"):
            m.append(("ausgleich", f"Die Spitzenlasten wurden gegen {_x_text(pk, 'de')} mit einer Geraden {_FORMULA['line']} und "
                     f"einer Exponentialfunktion {_FORMULA['exp']} ausgeglichen, beide direkt nach kleinsten Quadraten "
                     "in $y$ (die Exponentialfunktion mit Levenberg--Marquardt). Da beide Modelle zwei Parameter haben "
                     "und an dieselben Werte angepasst sind, gilt das Modell mit der kleineren Summe der "
                     "Fehlerquadrate, also dem grösseren $R^2$, als das bessere. Die Unsicherheiten sind "
                     "Standardunsicherheiten aus der Kovarianzmatrix am Optimum, die Vertrauensbereiche 95\\,\\% mit "
                     "dem Student-$t$-Quantil für $n - 2$ Freiheitsgrade."))
        res = [f"Die Kurve zeigt {V('npk')} Lastspitzen (fortschreitendes Versagen); {ref} ist die höchste davon, "
               "Haltezeit, Plateau und Bruch beziehen sich auf dieses globale Maximum."]
        if best:
            o = "exp" if best == "line" else "line"
            tb, to = ("L", "E") if best == "line" else ("E", "L")
            dat = {"line": "Geraden", "exp": "Exponentialfunktion"}[best]
            res.append(f"Die Spitzenlasten folgen besser einer {dat} ($R^2 = $ {V('pk' + tb + 'R2')}"
                       + (f" gegenüber {V('pk' + to + 'R2')} für die {_MODEL['de'][o]}" if (fit.get(o) or {}).get("ok") else "")
                       + f"; $a = $ {V('pk' + tb + 'a')}, $b = $ {V('pk' + tb + 'b')}).")
        elif fit.get("reason"):
            res.append("Für einen Ausgleich der Spitzenlasten sind es zu wenige Spitzen (mindestens drei nötig).")
    else:
        m = [("lastspitzen", f"Load peaks (progressive failure) were detected with a threshold rule with hysteresis: a running maximum "
             f"counts as a load peak as soon as the load falls by at least $\\Delta = $ {V('pkdelta')} below it "
             f"({V('pkthr')} of {ref}, at least three times the display resolution"
             + (", which governs here" if res_lim else "") + "); then the minimum (valley) is tracked until the load "
             "rises again by at least $\\Delta$ above it, and the search for the next peak starts there. For a flat "
             "maximum or minimum the first point counts; after the last peak the valley is the minimum up to the end of "
             "the active section. The threshold is a convention, not a standard.")]
        if not fit.get("reason"):
            m.append(("ausgleich", f"The peak loads were fitted against {_x_text(pk, 'en')} with a straight line {_FORMULA['line']} "
                     f"and an exponential {_FORMULA['exp']}, both by direct least squares in $y$ (the exponential with "
                     "Levenberg--Marquardt). Both models have two parameters and are fitted to the same values, so the "
                     "model with the smaller sum of squared residuals, i.e. the larger $R^2$, is taken as the better "
                     "one. Uncertainties are standard uncertainties from the covariance matrix at the optimum; the 95\\,\\% "
                     "confidence intervals use the Student $t$ quantile for $n - 2$ degrees of freedom."))
        res = [f"The curve shows {V('npk')} load peaks (progressive failure); {ref} is the highest of them, and hold "
               "time, plateau and break refer to this global maximum."]
        if best:
            o = "exp" if best == "line" else "line"
            tb, to = ("L", "E") if best == "line" else ("E", "L")
            res.append(f"The peak loads are better described by the {_MODEL['en'][best]} ($R^2 = $ {V('pk' + tb + 'R2')}"
                       + (f" against {V('pk' + to + 'R2')} for the {_MODEL['en'][o]}" if (fit.get(o) or {}).get("ok") else "")
                       + f"; $a = $ {V('pk' + tb + 'a')}, $b = $ {V('pk' + tb + 'b')}).")
        elif fit.get("reason"):
            res.append("There are too few peaks to fit the peak loads (at least three are needed).")
    return m, res


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
        b.add_figure(_fig(lambda ax: C.overlay_time(results, ax), lang, keep), "verlauf", L["fig_ov_time"].format(n=names),
                     steps=[])          # mehrere Messungen: das Bundle hat keinen Methodentext
        if st and any(r.strain is not None for r in results):
            b.add_figure(_fig(lambda ax: C.overlay_strain(results, ax), lang, keep), "dehnung", L["fig_ov_strain"].format(n=names),
                         steps=[])
        b.add_figure(_fig(lambda ax: C.grouped_kpis(results, ax), lang, keep), "kennwerte", L["fig_kpis"].format(n=names),
                     steps=[])
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
        b.add_table("vergleich", booktabs(head, rows, "lrrrrr", small=True, escape_header=False), L["tab_cmp"], steps=[])
    if inc.get("values", True) and any(r.unc for r in results):
        _series_unc(b, results, lang)
    if inc.get("citations", True):
        for r in results:
            nm = _norm(r)
            if nm:
                key, number, title, year = nm
                b.add_citation(key, "misc", title=f"{number}: {title}", author="{" + number.split()[0] + "}", year=year,
                               note="" if year else ("Ausgabe prüfen" if lang == "de" else "check edition"))


def _series_unc(b: Bundle, results: list[Result], lang: str):
    """Serie: Mittelwert ± Unsicherheit je Kennwert (Typ A aus der Streuung der Proben plus mittleres Einzelbudget)."""
    import labcite

    from labcalc import uncertainty as UN

    from . import uncertainty as UNC
    ser = UNC.series(results, lang)
    if not ser:
        return
    at = b.added_mark()
    uo = UN.to_report(b, list(ser.values()), lang, prefix="serie-")
    b.needs_since(at, [])
    keys = [labcite.to_bib(b, k, rec) for k, rec in UNC.SOURCES.items()]
    de = lang == "de"
    n = len([r for r in results if r.unc])
    head = (f"Serie aus {n} Proben: Mittelwert der Kennwerte mit der Standardunsicherheit des Mittelwerts aus der "
            "Streuung der Proben (Typ A, $s/\\sqrt{n}$) und dem Mittel der Einzelbudgets als voll korreliertem Beitrag "
            f"(konservativ){cite(keys)}." if de else
            f"Series of {n} specimens: mean of each property with the standard uncertainty of the mean from the scatter "
            "of the specimens (type A, $s/\\sqrt{n}$) and the mean single-test budget as a fully correlated contribution "
            f"(conservative){cite(keys)}.")
    vals = "; ".join(f"{tex_escape(x['label'])} \\labval{{{b.slug}}}{{serie-{x['name']}-pm}}" for x in ser.values())
    b.add_text("unsicherheit", head + "\n" + uo["latex"] + "\n\n" + vals + ".\n",
               "Messunsicherheit der Serie" if de else "Measurement uncertainty of the series", steps=[])


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
