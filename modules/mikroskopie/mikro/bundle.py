"""Ergebnisse fuer den Berichtseditor (Folio Lab, Format folio-lab-bundle/1)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

try:
    from labbundle import Bundle, booktabs, num, slugify, step_tag, tex_escape
except ImportError:  # Modul ausserhalb von Folio Lab gestartet
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "sdk" / "python"))
    from labbundle import Bundle, booktabs, num, slugify, step_tag, tex_escape

from . import charts as C
from . import threshold as TH
from .analysis import Analysis, display_for_pre, run
from .imageio import Stack
from .measure import line_scale, sample_line

T = {
    "de": {
        "module": "Mikroskopie", "title1": "Bildanalyse {n}", "titleN": "Bildanalyse {n}",
        "fig_img": "Aufnahme {n}{roi}.", "fig_img_roi": " mit den gemessenen Auswahlen",
        "fig_part": "Erkannte Partikel in {n} ({c} Partikel, Konturen türkis).",
        "fig_hist": "Grauwerthistogramm von {n}{thr}.", "fig_hist_thr": " mit Schwellenbereich ({m})",
        "fig_sizes": "Anzahlverteilung (Q0) des flächengleichen Kreisdurchmessers der Partikel in {n}{e}.",
        "fig_sizes_e": ", randkorrigiert nach Miles und Lantuéjoul",
        "fig_shape": "Zirkularität gegen Äquivalentdurchmesser der Partikel in {n}.",
        "fig_profile": "Grauwertprofil entlang der Linie {l} in {n}.",
        "fig_cmp": "Summenverteilung (Q0, nach Anzahl) des Äquivalentdurchmessers: {n}.",
        "tab_meas": "Messwerte der Auswahlen in {n}.", "tab_part": "Partikelanalyse von {n}.",
        "tab_cmp": "Partikelanalyse im Vergleich.",
        "data_part": "Partikel in {n}: Fläche, Umfang, Form, Feret, Lage, Intensität.",
        "data_prof": "Grauwertprofil entlang {l} in {n}.", "data_meas": "Messwerte der Auswahlen in {n}.",
        "h_quant": "Grösse", "h_val": "Wert",
        "rows": {"count": "Anzahl Partikel (vermessen)", "ncorr": "Anzahl randkorrigiert", "frac": "Flächenanteil",
                 "area": "Mittlere Fläche",
                 "ecd": "Äquivalentdurchmesser", "d": "D10 / D50 / D90 (Anzahl, Q0)",
                 "dv": "Dv10 / Dv50 / Dv90 (Volumen, Q3)", "circ": "Zirkularität",
                 "feret": "Feret-Durchmesser", "ar": "Seitenverhältnis", "sol": "Solidität",
                 "region": "Ausgewertete Fläche"},
        "meas_head": ["Auswahl", "Fläche", "Mittelwert", "Std.-Abw.", "Min", "Max"],
        "cmp_head": ["Bild", "n", "Flächenant. [\\%]", "ECD [{u}]", "D50 (Q0) [{u}]", "Zirk."],
        "fig_ovl": "Grössenverteilung der Partikel in {n}{{parts}} (relative Häufigkeit nach Anzahl, gestrichelt: $D_{{50}}$ (Q0)).",
        "tab_ovl": "Partikel in {n} und Vergleichsverteilung {c}.", "ovl_img": "Partikel (ECD)",
        "ovl_mean": "Mittelwert", "data_ovl": "Vergleichsverteilung {c}.",
        "methods": "Methodik", "results": "Ergebnisse",
    },
    "en": {
        "module": "Microscopy", "title1": "Image analysis {n}", "titleN": "Image analysis {n}",
        "fig_img": "Micrograph {n}{roi}.", "fig_img_roi": " with the measured selections",
        "fig_part": "Detected particles in {n} ({c} particles, outlines in cyan).",
        "fig_hist": "Grey-value histogram of {n}{thr}.", "fig_hist_thr": " with threshold range ({m})",
        "fig_sizes": "Number distribution (Q0) of the equivalent circle diameter of the particles in {n}{e}.",
        "fig_sizes_e": ", edge-corrected after Miles and Lantuéjoul",
        "fig_shape": "Circularity versus equivalent diameter of the particles in {n}.",
        "fig_profile": "Grey-value profile along line {l} in {n}.",
        "fig_cmp": "Cumulative number distribution (Q0) of the equivalent diameter: {n}.",
        "tab_meas": "Measurements of the selections in {n}.", "tab_part": "Particle analysis of {n}.",
        "tab_cmp": "Particle analysis compared.",
        "data_part": "Particles in {n}: area, perimeter, shape, Feret, position, intensity.",
        "data_prof": "Grey-value profile along {l} in {n}.", "data_meas": "Measurements of the selections in {n}.",
        "h_quant": "Quantity", "h_val": "Value",
        "rows": {"count": "Number of particles (measured)", "ncorr": "Number, edge-corrected", "frac": "Area fraction",
                 "area": "Mean area",
                 "ecd": "Equivalent diameter", "d": "D10 / D50 / D90 (number, Q0)",
                 "dv": "Dv10 / Dv50 / Dv90 (volume, Q3)", "circ": "Circularity",
                 "feret": "Feret diameter", "ar": "Aspect ratio", "sol": "Solidity", "region": "Analysed area"},
        "meas_head": ["Selection", "Area", "Mean", "Std. dev.", "Min", "Max"],
        "cmp_head": ["Image", "n", "Area fr. [\\%]", "ECD [{u}]", "D50 (Q0) [{u}]", "Circ."],
        "fig_ovl": "Size distribution of the particles in {n}{{parts}} (relative frequency by number, dashed: $D_{{50}}$ (Q0)).",
        "tab_ovl": "Particles in {n} and comparison distribution {c}.", "ovl_img": "Particles (ECD)",
        "ovl_mean": "Mean", "data_ovl": "Comparison distribution {c}.",
        "methods": "Methods", "results": "Results",
    },
}

PART_COLS = ["#", "Area", "Perim.", "Circ.", "ECD", "Feret", "FeretAngle", "MinFeret", "Major", "Minor", "Angle",
             "AR", "Round", "Solidity", "X", "Y", "BX", "BY", "Width", "Height", "Pixels", "Weight", "Mean", "StdDev",
             "Min", "Max", "IntDen"]


def _u(calib):
    return calib.unit if calib.calibrated else "px"


def _pm(m, s, nd, lang, unit=""):
    if m is None:
        return "--"
    out = num(m, nd, lang)
    if s is not None:
        out += r"\,$\pm$\," + num(s, nd, lang)
    return out + (r"\," + tex_escape(unit) if unit else "")


def _nd(v):
    """Sinnvolle Nachkommastellen fuer eine Laenge/Flaeche."""
    if v is None or v == 0:
        return 1
    a = abs(v)
    return 0 if a >= 100 else 1 if a >= 10 else 2 if a >= 1 else 3


def _fig(b, fig, id, caption, width="0.8", **kw):
    b.add_figure(fig, id, caption, width=width, dpi=150, **kw)


def _cal_text(calib) -> str:
    """Pixelgrösse als Text: quadratisch „0.25 µm/px“, sonst „0.25 × 0.3 µm/px“ (Breite × Höhe)."""
    if calib.square:
        return f"{calib.pw:g} {calib.unit}/px"
    return f"{calib.pw:g} × {calib.ph:g} {calib.unit}/px"


def _data_cite(b: Bundle, a: Analysis, raw_len: int, lang: str):
    st = a.orig
    key = f"data-{b.slug}"
    cal = _cal_text(a.calib) if a.calib.calibrated else ("unkalibriert" if lang == "de" else "uncalibrated")
    b.add_citation(key, "misc", title=tex_escape(a.name),
                   howpublished=("Bilddatei" if lang == "de" else "Image file"),
                   note=tex_escape(f"{st.width}×{st.height} px, {st.type_label()}, {cal}, {raw_len / 1024:.0f} KiB"))
    return key


def _thr_cite(b: Bundle, a: Analysis):
    thr = a.proc.thr
    if not thr or not thr.get("method"):
        return None
    key = TH.METHODS[thr["method"]][1]
    ref = dict(TH.REFERENCES[key])
    et = ref.pop("entry_type")
    if key in TH.UNVERIFIED:
        ref["note"] = "Angaben nicht verifiziert" if b.lang == "de" else "not verified"
    b.add_citation(key, et, **{k: tex_escape(v) if k not in ("pages", "doi") else v for k, v in ref.items()})
    return key


def _uses_ws(a: Analysis) -> bool:
    return any(s.get("op") == "watershed" for s in (a.state.get("pipeline") or []))


def _ws_cite(b: Bundle, a: Analysis):
    """Quellen der Wasserscheide (MI-01), wenn der Schritt im Protokoll ist."""
    if not _uses_ws(a):
        return None
    from . import watershed as WS
    for key in WS.REFS:
        ref = dict(WS.REFERENCES[key])
        et = ref.pop("entry_type")
        b.add_citation(key, et, **{k: tex_escape(v) if k not in ("pages", "doi") else v for k, v in ref.items()})
    return ",".join(WS.REFS)


def _overlay(a: Analysis) -> dict | None:
    """I-04: Vergleichsverteilung aus dem Arbeitsstand (nur mit Partikelanalyse und Längenkalibrierung)."""
    from . import compare as CMP
    c = a.state.get("compare")
    if not c or not a.part or not a.part["rows"] or not a.calib.calibrated or not c.get("values_m"):
        return None
    try:
        vals = CMP.in_unit(c, a.calib.unit)
    except CMP.CompareError:
        return None
    ecd = np.array([r["ECD"] for r in a.part["rows"]], dtype=float)
    w = np.array([r.get("Weight", 1.0) for r in a.part["rows"]], dtype=float)   # Randkorrektur wie in der Zusammenfassung
    return {"cmp": c, "vals": vals, "ecd": ecd, "w": w, "s_img": CMP.stats(ecd, w), "s_ds": CMP.stats(vals)}


def _ovl_cite(b: Bundle, c: dict, lang: str) -> str:
    p = c.get("producer") or {}
    key = "ds-" + slugify(str(c.get("share") or "datensatz"), 30)
    where = ", ".join(x for x in ("Folio Lab", p.get("env_name"), p.get("item_name")) if x)
    col = f"{c.get('name') or c.get('key')} [{c.get('unit') or '1'}]"
    b.add_citation(key, "misc", title=tex_escape(f"{'Datensatz' if lang == 'de' else 'Dataset'} {c.get('title') or c.get('share')}"),
                   howpublished=tex_escape(where), year=str(c.get("created") or "")[:4] or None,
                   note=tex_escape(f"{c.get('share')}, Version {c.get('version')}, "
                                   f"{'Spalte' if lang == 'de' else 'column'} {col}"))
    return key


def _single(b: Bundle, a: Analysis, raw_len: int, lang: str, inc: dict):
    L = T[lang]
    n = tex_escape(a.name)
    u = _u(a.calib)
    ue = tex_escape(u)
    cites = {}
    ov = _overlay(a)
    if ov and inc.get("citations", True):
        cites["cmp"] = _ovl_cite(b, ov["cmp"], lang)
    if inc.get("citations", True):
        cites["data"] = _data_cite(b, a, raw_len, lang)
        k = _thr_cite(b, a)
        if k:
            cites["thr"] = k
        k = _ws_cite(b, a)
        if k:
            cites["ws"] = k
        if a.part is not None:
            from .measure import QUANTILE_REF
            qk, qref = QUANTILE_REF
            qref = dict(qref)
            et = qref.pop("entry_type")
            b.add_citation(qk, et, **{k2: tex_escape(v) if k2 != "pages" else v for k2, v in qref.items()})
            cites["q"] = qk
    part = a.part
    rows = part["rows"] if part else []
    summ = part["summary"] if part else {}

    if inc.get("figures", True):
        disp = a.state.get("display") or {}
        if a.kind == "binary":
            disp = display_for_pre(a)
            base = a.intensity
            kind = "gray" if base.ndim == 2 else "rgb"
        else:
            base, kind = a.img, a.kind
        rgb = C.render(base, kind, disp)
        area_rois = [r for r in (a.state.get("rois") or [])]
        sb = a.state.get("scalebar")
        _fig(b, C.fig_image(rgb, a.calib, lang, rois=area_rois, scalebar=sb),
             "bild", L["fig_img"].format(n=n, roi="{parts}"), steps=[],
             parts=[{"id": "auswahl", "label": "Auswahlen" if lang == "de" else "Selections",
                     "caption": L["fig_img_roi"].split(" ", 2)[2]}] if area_rois else [])
        if part:
            from .measure import outline_rgba
            labels = [r["_px"] for r in rows] if len(rows) <= 300 else None
            _fig(b, C.fig_image(rgb, a.calib, lang, overlay=outline_rgba(part["labels"]), labels=labels, scalebar=sb),
                 "partikel", L["fig_part"].format(n=n, c=len(rows)), steps=["partikel", "schwelle", "wasserscheide"])
        hv = a.intensity
        if hv.ndim == 2:
            thr = a.proc.thr
            m = TH.METHODS.get(thr.get("method"), ("manuell" if lang == "de" else "manual",))[0] if thr else ""
            _fig(b, C.fig_hist(hv, lang, thr), "histogramm",
                 L["fig_hist"].format(n=n, thr="{parts}"), "0.75", steps=[],
                 parts=[{"id": "schwelle", "label": "Schwellenbereich" if lang == "de" else "Threshold range", "steps": ["schwelle"],
                         "caption": L["fig_hist_thr"].format(m=tex_escape(m)).split(" ", 2)[2]}] if thr and thr.get("lo") is not None else [])
        if len(rows) >= 3:
            ecorr = summ.get("EdgeCorrection") == "miles-lantuejoul"
            _fig(b, C.fig_sizes(rows, u, lang), "groessen", L["fig_sizes"].format(n=n, e=L["fig_sizes_e"] if ecorr else ""), "0.75",
                 steps=["partikel", "quantile"])
            _fig(b, C.fig_shape(rows, u, lang), "form", L["fig_shape"].format(n=n), "0.75", steps=["partikel"])
        if ov:
            cname = ov["cmp"].get("name") or ov["cmp"].get("key")
            b.add_figure(C.fig_sizes_overlay(ov["ecd"], ov["vals"], u, lang,
                                             (("Partikel" if lang == "de" else "Particles"), f"{cname}"), weights=ov["w"]),
                         "vergleichsverteilung", L["fig_ovl"].format(n=n), width="0.8", dpi=150,
                         steps=["partikel", "quantile"], parts_lead="und" if lang == "de" else "and",
                         parts=[{"id": "vergleich", "label": _ovl_name(ov["cmp"]),
                                 "caption": ("Vergleichsverteilung " if lang == "de" else "comparison distribution ")
                                 + tex_escape(_ovl_name(ov["cmp"])),
                                 "cites": [cites["cmp"]] if "cmp" in cites else []}])
        for i, r in enumerate([r for r in (a.state.get("rois") or []) if r.get("type") == "line"][:3], 1):
            d, v = sample_line(a.intensity, r["x1"], r["y1"], r["x2"], r["y2"], int(r.get("width") or 1))
            d = d * line_scale(a.calib, r["x2"] - r["x1"], r["y2"] - r["y1"])
            _fig(b, C.fig_profile(d, v, u, lang), f"profil{i}",
                 L["fig_profile"].format(n=n, l=tex_escape(r.get("name") or str(i))), "0.75", steps=[])

    if inc.get("tables", True):
        if a.measurements:
            head = list(L["meas_head"])
            head[1] += f" [{u}²]"
            body = []
            for m in a.measurements:
                if m.get("Type") == "point":
                    continue
                area = m.get("Area")
                label = tex_escape(m["Label"])
                if m.get("Length") is not None:
                    label += f" ({'Linie' if lang == 'de' else 'line'}, {num(m['Length'], 2, lang)}\\,{ue})"
                body.append([label, num(area, _nd(area), lang) if area is not None else "--",
                             num(m.get("Mean"), 1, lang), num(m.get("StdDev"), 1, lang), num(m.get("Min"), 0, lang),
                             num(m.get("Max"), 0, lang)])
            if body:
                b.add_table("messungen", booktabs(head, body, "lrrrrr", small=True), L["tab_meas"].format(n=n), steps=[])
        if part:
            R = L["rows"]
            nd = _nd(summ.get("MeanECD"))
            ndA = _nd(summ.get("AverageSize"))
            ecorr = summ.get("EdgeCorrection") == "miles-lantuejoul"
            tab = [[R["count"], num(summ["Count"], 0, lang)]]
            if ecorr and summ.get("CountCorrected") is not None:
                tab.append([R["ncorr"], num(summ["CountCorrected"], 1, lang)])
            tab += [[R["region"], num(summ["RegionArea"], _nd(summ["RegionArea"]), lang) + r"\," + tex_escape(u + "²")],
                    [R["frac"], num(summ["AreaFraction"], 2, lang) + r"\,\%"],
                    [R["area"], _pm(summ.get("AverageSize"), summ.get("SDSize"), ndA, lang, u + "²")],
                    [R["ecd"], _pm(summ.get("MeanECD"), summ.get("SDECD"), nd, lang, u)]]
            if summ.get("D50") is not None:
                tab.append([R["d"], " / ".join(num(summ[k], nd, lang) for k in ("D10", "D50", "D90")) + r"\," + ue])
            if summ.get("Dv50") is not None:
                tab.append([R["dv"], " / ".join(num(summ[k], nd, lang) for k in ("Dv10", "Dv50", "Dv90")) + r"\," + ue])
            tab += [[R["circ"], _pm(summ.get("MeanCirc"), summ.get("SDCirc"), 2, lang)],
                    [R["feret"], _pm(summ.get("MeanFeret"), summ.get("SDFeret"), nd, lang, u)],
                    [R["ar"], _pm(summ.get("MeanAR"), summ.get("SDAR"), 2, lang)],
                    [R["sol"], _pm(summ.get("MeanSolidity"), summ.get("SDSolidity"), 2, lang)]]
            if lang == "de":
                note = (r"Mittelwert $\pm$ Standardabweichung; ECD: Durchmesser des flächengleichen Kreises. "
                        r"Q0: nach Anzahl gewichtet; Q3: nach Volumen gewichtet (ECD$^3$, Kugeln angenommen). "
                        r"Flächenanteil aus allen Partikeln einschliesslich der am Rand.")
                if ecorr:
                    note += (r" Mittelwerte, Standardabweichungen und D-Werte randkorrigiert: Partikel am Rand der "
                             r"Auswertungsfläche nicht vermessen, die übrigen nach Miles und Lantuéjoul gewichtet.")
            else:
                note = (r"Mean $\pm$ standard deviation; ECD: diameter of the circle of equal area. "
                        r"Q0: weighted by number; Q3: weighted by volume (ECD$^3$, spheres assumed). "
                        r"Area fraction from all particles including those at the border.")
                if ecorr:
                    note += (r" Means, standard deviations and D values edge-corrected: particles at the border of the "
                             r"analysed area not measured, the others weighted after Miles and Lantuéjoul.")
            b.add_table("partikel", booktabs([L["h_quant"], L["h_val"]], tab, "lr"), L["tab_part"].format(n=n), notes=note,
                        steps=["partikel", "quantile", "schwelle", "wasserscheide"])
        if ov:
            si, sd = ov["s_img"], ov["s_ds"]
            nd = _nd(si.get("D50"))
            tab = [["n", num(si["n"], 0, lang), num(sd["n"], 0, lang)]]
            tab += [[f"{k} (Q0)", num(si[k], nd, lang) + r"\," + ue, num(sd[k], nd, lang) + r"\," + ue] for k in ("D10", "D50", "D90")]
            tab += [[f"{k} (Q3)", num(si[k], nd, lang) + r"\," + ue, num(sd[k], nd, lang) + r"\," + ue] for k in ("Dv10", "Dv50", "Dv90")]
            tab.append([L["ovl_mean"] + " (Q0)", _pm(si["mean"], si["sd"], nd, lang, u), _pm(sd["mean"], sd["sd"], nd, lang, u)])
            b.add_table("vergleichsverteilung", booktabs([L["h_quant"], L["ovl_img"], tex_escape(ov["cmp"].get("name") or "")], tab, "lrr"),
                        L["tab_ovl"].format(n=n, c=tex_escape(_ovl_name(ov["cmp"]))),
                        cites=[cites["cmp"]] if "cmp" in cites else None, steps=["partikel", "quantile"],
                        notes=(r"Beide Spalten gleich berechnet: jeder Datensatzwert gilt als ein Teilchen; Q0 nach Anzahl, "
                               r"Q3 nach Volumen ($d^3$) gewichtet. Kennwerte einer Laserbeugungsverteilung (meist Q3) sind "
                               r"keine Einzelwerte und so nicht vergleichbar." if lang == "de" else
                               r"Both columns computed alike: each dataset value counts as one particle; Q0 weighted by "
                               r"number, Q3 by volume ($d^3$). Parameters of a laser-diffraction distribution (usually Q3) "
                               r"are not individual values and cannot be compared this way."))

    if inc.get("values", True):
        vals = []
        if a.calib.calibrated:
            if a.calib.square:
                vals.append(("px", "Pixelgrösse" if lang == "de" else "Pixel size", num(a.calib.pw, 4, lang, f"{u}/px"), f"{a.calib.pw:g} {u}/px"))
            else:
                vals.append(("px", "Pixelgrösse (Breite × Höhe)" if lang == "de" else "Pixel size (width × height)",
                             num(a.calib.pw, 4, lang) + r"\,$\times$\," + num(a.calib.ph, 4, lang, f"{u}/px"), _cal_text(a.calib)))
        st = a.proc.stack
        vals.append(("imgW", "Bildbreite" if lang == "de" else "Image width", num(st.width * a.calib.pw, _nd(st.width * a.calib.pw), lang, u), ""))
        vals.append(("imgH", "Bildhöhe" if lang == "de" else "Image height", num(st.height * a.calib.ph, _nd(st.height * a.calib.ph), lang, u), ""))
        thr = a.proc.thr
        if thr:
            vals.append(("thr", "Schwelle" if lang == "de" else "Threshold", num(thr["lo"], 0, lang) + "--" + num(thr["hi"], 0, lang), f"{thr['lo']:.0f}–{thr['hi']:.0f}"))
            if thr.get("method"):
                vals.append(("thrMethod", "Schwellenmethode" if lang == "de" else "Threshold method", tex_escape(TH.METHODS[thr["method"]][0]), TH.METHODS[thr["method"]][0]))
        if part:
            nd = _nd(summ.get("MeanECD"))
            vals += [("n", "Anzahl Partikel" if lang == "de" else "Particle count", num(summ["Count"], 0, lang), str(summ["Count"])),
                     ("areaFrac", "Flächenanteil" if lang == "de" else "Area fraction", num(summ["AreaFraction"], 2, lang, "%"), f"{summ['AreaFraction']:.2f} %")]
            if summ["Count"]:
                vals += [("meanArea", "Mittlere Fläche" if lang == "de" else "Mean area", num(summ["AverageSize"], _nd(summ["AverageSize"]), lang, u + "²"), ""),
                         ("meanECD", "Mittlerer Äquivalentdurchmesser" if lang == "de" else "Mean equivalent diameter", num(summ["MeanECD"], nd, lang, u), f"{summ['MeanECD']:.{nd}f} {u}"),
                         ("sdECD", "Std.-Abw. Äquivalentdurchmesser" if lang == "de" else "SD of equivalent diameter", num(summ["SDECD"], nd, lang, u), ""),
                         ("meanCirc", "Mittlere Zirkularität" if lang == "de" else "Mean circularity", num(summ["MeanCirc"], 2, lang), f"{summ['MeanCirc']:.2f}"),
                         ("meanFeret", "Mittlerer Feret-Durchmesser" if lang == "de" else "Mean Feret diameter", num(summ["MeanFeret"], nd, lang, u), "")]
                if summ.get("D50") is not None:
                    vals += [(k, f"{k} (Q0)", num(summ[k], nd, lang, u), f"{summ[k]:.{nd}f} {u}") for k in ("D10", "D50", "D90")]
                if summ.get("Dv50") is not None:
                    vals += [(k, f"{k} (Q3)", num(summ[k], nd, lang, u), f"{summ[k]:.{nd}f} {u}") for k in ("Dv10", "Dv50", "Dv90")]
                if summ.get("EdgeCorrection") == "miles-lantuejoul":
                    vals.append(("nCorr", "Anzahl randkorrigiert" if lang == "de" else "Number, edge-corrected",
                                 num(summ["CountCorrected"], 1, lang), f"{summ['CountCorrected']:.1f}"))
        if ov:
            sd, cn = ov["s_ds"], ov["cmp"].get("name") or ""
            nd = _nd(sd.get("D50"))
            vals.append(("cmpN", f"{cn}: n", num(sd["n"], 0, lang), str(sd["n"])))
            vals += [(f"cmp{k}", f"{cn}: {k} (Q0)", num(sd[k], nd, lang, u), f"{sd[k]:.{nd}f} {u}") for k in ("D10", "D50", "D90")]
            vals += [(f"cmp{k}", f"{cn}: {k} (Q3)", num(sd[k], nd, lang, u), f"{sd[k]:.{nd}f} {u}") for k in ("Dv10", "Dv50", "Dv90")]
            r = _ovl_ratio(ov)
            if r is not None:
                vals.append(("cmpRatio", "D50 (Q0) Partikel / " + cn if lang == "de" else "D50 (Q0) particles / " + cn,
                             num(r, 2, lang), f"{r:.2f}"))
        for i, m in enumerate(a.measurements, 1):
            if m.get("Mean") is not None and m.get("Type") != "point":
                vals.append((f"roi{i}Mean", f"{m['Label']}: " + ("Mittelwert" if lang == "de" else "mean"), num(m["Mean"], 1, lang), f"{m['Mean']:.1f}"))
                if m.get("Area") is not None:
                    vals.append((f"roi{i}Area", f"{m['Label']}: " + ("Fläche" if lang == "de" else "area"), num(m["Area"], _nd(m["Area"]), lang, u + "²"), ""))
                if m.get("Length") is not None:
                    vals.append((f"roi{i}Length", f"{m['Label']}: " + ("Länge" if lang == "de" else "length"), num(m["Length"], 2, lang, u), ""))
        need = {"thr": ["schwelle"], "thrMethod": ["schwelle"]}
        need.update({k: ["partikel"] for k in ("n", "areaFrac", "meanArea", "meanECD", "sdECD", "meanCirc", "meanFeret", "nCorr")})
        need.update({v[0]: ["partikel", "quantile"] for v in vals if v[0].startswith(("D10", "D50", "D90", "Dv", "cmp"))})
        b.add_values([(k, tex_escape(lbl), ltx, txt) for k, lbl, ltx, txt in vals], needs=need)

    if inc.get("data", True):
        if rows:
            hdr = [c for c in PART_COLS if c in rows[0]]
            b.add_data_csv("partikel", [_csv_col(c) for c in hdr], [[r.get(c) for c in hdr] for r in rows],
                           L["data_part"].format(n=n),
                           labels={"ECD": f"ECD [{ue}]", "Area": f"Fläche [{ue}$^2$]" if lang == "de" else f"Area [{ue}$^2$]",
                                   "Circ": "Zirkularität" if lang == "de" else "Circularity",
                                   "Feret": f"Feret [{ue}]", "Perim": f"Umfang [{ue}]" if lang == "de" else f"Perimeter [{ue}]",
                                   "AR": "AR", "Solidity": "Solidity", "Mean": "Mittelwert" if lang == "de" else "Mean",
                                   "Weight": "Gewicht (Randkorrektur)" if lang == "de" else "Weight (edge correction)",
                                   "X": f"x [{ue}]", "Y": f"y [{ue}]"},
                           plot={"x": "ECD", "y": "Circ", "style": "marks"})
        if ov:
            b.add_data_csv("vergleichsverteilung", ["d"], [[float(x)] for x in ov["vals"]],
                           L["data_ovl"].format(c=tex_escape(_ovl_name(ov["cmp"]))),
                           labels={"d": f"{tex_escape(ov['cmp'].get('name') or 'd')} [{ue}]"})
        for i, r in enumerate([r for r in (a.state.get("rois") or []) if r.get("type") == "line"][:3], 1):
            d, v = sample_line(a.intensity, r["x1"], r["y1"], r["x2"], r["y2"], int(r.get("width") or 1))
            d = d * line_scale(a.calib, r["x2"] - r["x1"], r["y2"] - r["y1"])
            b.add_data_csv(f"profil{i}", ["d", "value"], [[float(x), float(y)] for x, y in zip(d, v)],
                           L["data_prof"].format(n=n, l=tex_escape(r.get("name") or str(i))),
                           labels={"d": ("Abstand" if lang == "de" else "Distance") + f" [{ue}]",
                                   "value": "Grauwert" if lang == "de" else "Grey value"},
                           plot={"x": "d", "y": "value"})

    uo, eq_text = None, ""
    if inc.get("values", True) and a.part is not None:
        from . import uncertainty as UNC
        unc = UNC.evaluate_all(a, lang) if a.state.get("unc") else None
        if unc:                                         # Messunsicherheit: Werte ±, Budgettabellen, Methodentext
            at = b.added_mark()
            uo = UNC.to_report(b, a, lang, unc)
            b.needs_since(at, ["unsicherheit"])
        if a.state.get("equations"):                    # eigene Gleichungen (mit fortgepflanzter Unsicherheit)
            from labcalc import formulas as Fm
            _v, eqs = UNC.evaluate_equations(a, unc, a.state["equations"], lang)
            if eqs:
                mark = b.added_mark()
                eq_text = Fm.to_report(b, eqs, lang, cite_prefix="eq").get("latex", "")
                for it in b.items[mark[0]:]:            # Tabelle, Budgets und Werte brauchen den Gleichungsblock
                    if it.get("kind") == "table":
                        it["needs"] = {"steps": ["gleichungen"]}
                b.needs_since(mark, ["gleichungen"])

    if inc.get("text", True):
        _texts(b, a, lang, cites, uo, eq_text)


def _csv_col(c):
    return {"#": "id", "Perim.": "Perim", "Circ.": "Circ"}.get(c, c)


def _ovl_name(c: dict) -> str:
    """,,Spalte`` aus ,,Datensatz`` (Version n) – für Bildunterschriften (vor tex_escape)."""
    return f"{c.get('name') or c.get('key')} ({c.get('title') or c.get('share')}, v{c.get('version')})"


def _ovl_ratio(ov: dict):
    from . import compare as CMP
    return CMP.ratio(ov["s_img"].get("D50"), ov["s_ds"].get("D50"))


def _texts(b: Bundle, a: Analysis, lang: str, cites: dict, uo: dict | None = None, eq_text: str = ""):
    s = b.slug
    v = lambda k: f"\\labval{{{s}}}{{{k}}}"  # noqa: E731
    have = {x["key"] for x in b.values}
    st = a.orig
    de = lang == "de"
    c_data = f" \\cite{{{cites['data']}}}" if "data" in cites else ""
    c_thr = f" \\cite{{{cites['thr']}}}" if "thr" in cites else ""
    steps = a.proc.steps
    m = []
    if de:
        m.append(f"Ausgewertet wurde die Aufnahme {tex_escape(a.name)}{c_data} ({st.width}\\,$\\times$\\,{st.height} Pixel, {tex_escape(st.type_label())}"
                 + (f", Pixelgrösse {v('px')}" if "px" in have else ", ohne Längenkalibrierung") + ").")
        if steps:
            m.append("Die Bearbeitung umfasste in dieser Reihenfolge: " + "; ".join(tex_escape(x) for x in steps) + ".")
        if a.proc.thr and a.proc.thr.get("method"):
            m.append(step_tag("schwelle") + f"Die Schwelle wurde automatisch nach der Methode {tex_escape(TH.METHODS[a.proc.thr['method']][0])}{c_thr} bestimmt"
                     + (f" ({v('thr')})." if "thr" in have else "."))
        if _uses_ws(a):
            c_ws = f" \\cite{{{cites['ws']}}}" if "ws" in cites else ""
            m.append(step_tag("wasserscheide") + "Sich berührende Teilchen wurden mit einer Wasserscheide auf der euklidischen Distanzkarte getrennt "
                     f"(Marker aus den h-Maxima, Flutung nach Vincent und Soille){c_ws}.")
        if a.calib.calibrated:
            m.append("Die Pixel wurden als quadratisch behandelt" + (" (nur eine Pixelgrösse bekannt, Pixelhöhe gleich Pixelbreite angenommen)." if a.calib.square_assumed else ".")
                     if a.calib.square else
                     "Die Pixel sind nicht quadratisch; Flächen, Längen, Umfänge, Feret-Durchmesser und Ellipsenachsen wurden mit getrennter Pixelbreite und -höhe berechnet.")
        if a.part is not None:
            P = {**{"size_min": 0, "size_max": None, "circ_min": 0, "circ_max": 1}, **(a.state.get("particles") or {})}
            unit = "Pixel" if P.get("size_in_pixels") else tex_escape(_u(a.calib) + "²")
            smax = "∞" if P.get("size_max") in (None, "", "inf") else num(P["size_max"], 2, lang)
            total = P.get("perimeter") == "total" and not P.get("include_holes")
            m.append(step_tag("partikel") + f"Partikel wurden als zusammenhängende Bereiche des Binärbildes (8er-Nachbarschaft) erfasst, "
                     f"mit einer Fläche von {num(P.get('size_min') or 0, 2, lang)} bis {tex_escape(smax)}\\,{unit} und einer Zirkularität "
                     f"$4\\pi A/U^2$ von {num(P.get('circ_min') or 0, 2, lang)} bis {num(P.get('circ_max') if P.get('circ_max') is not None else 1, 2, lang)}"
                     + ("; Löcher wurden der Partikelfläche zugerechnet" if P.get("include_holes") else "") + ". "
                     "Der Umfang ist die Länge der Marching-Squares-Kontur zwischen den Pixelmitten (gerade Schritte eine "
                     "Pixelkante, Ecken als halbe Pixeldiagonale), "
                     + ("einschliesslich der Ränder von Löchern" if total else "nur die Aussenkontur (Löcher gefüllt)")
                     + "; der Äquivalentdurchmesser (ECD) ist der Durchmesser des flächengleichen Kreises.")
            if P.get("exclude_edges", True):
                m.append(step_tag("partikel") + "Vermessen wurden nur Partikel, deren Begrenzungsrechteck den Rand der ausgewerteten Fläche nicht "
                         "berührt; jedes wurde nach Miles und Lantuéjoul mit dem Kehrwert des Anteils der Lagen gewichtet, "
                         "in denen ein Rechteck seiner Grösse den Rand nicht berührt (Bild $W\\times H$, Rechteck $w\\times h$ "
                         "Pixel: $WH/((W-w-1)(H-h-1))$). Mittelwerte, Standardabweichungen und D-Werte sind mit diesen Gewichten "
                         "berechnet; der Flächenanteil enthält auch die Partikel am Rand.")
            else:
                m.append(step_tag("partikel") + "Partikel am Rand der ausgewerteten Fläche wurden mit ihrem sichtbaren Teil vermessen (keine Randkorrektur).")
            m.append(step_tag("quantile") + "$D_{10}$, $D_{50}$ und $D_{90}$ sind Quantile der Anzahlverteilung (Q0) des ECD, $D_{v10}$, $D_{v50}$ "
                     "und $D_{v90}$ der Volumenverteilung (Q3, Gewicht ECD$^3$, Kugeln angenommen); Quantile nach der "
                     "Mittelpunktsregel (bei gleichen Gewichten Definition 5 nach Hyndman und Fan"
                     + (f" \\cite{{{cites['q']}}}" if "q" in cites else "") + ").")
    else:
        m.append(f"The micrograph {tex_escape(a.name)}{c_data} ({st.width}\\,$\\times$\\,{st.height} pixels, {tex_escape(st.type_label())}"
                 + (f", pixel size {v('px')}" if "px" in have else ", without length calibration") + ") was analysed.")
        if steps:
            m.append("Processing comprised, in this order: " + "; ".join(tex_escape(x) for x in steps) + ".")
        if a.proc.thr and a.proc.thr.get("method"):
            m.append(step_tag("schwelle") + f"The threshold was set automatically with the {tex_escape(TH.METHODS[a.proc.thr['method']][0])} method{c_thr}"
                     + (f" ({v('thr')})." if "thr" in have else "."))
        if _uses_ws(a):
            c_ws = f" \\cite{{{cites['ws']}}}" if "ws" in cites else ""
            m.append(step_tag("wasserscheide") + "Touching particles were separated by a watershed on the Euclidean distance map "
                     f"(markers from the h-maxima, flooding after Vincent and Soille){c_ws}.")
        if a.calib.calibrated:
            m.append("Pixels were treated as square" + (" (only one pixel size known; pixel height assumed equal to pixel width)." if a.calib.square_assumed else ".")
                     if a.calib.square else
                     "The pixels are not square; areas, lengths, perimeters, Feret diameters and ellipse axes were computed with separate pixel width and height.")
        if a.part is not None:
            P = {**{"size_min": 0, "size_max": None, "circ_min": 0, "circ_max": 1}, **(a.state.get("particles") or {})}
            unit = "pixels" if P.get("size_in_pixels") else tex_escape(_u(a.calib) + "²")
            smax = "∞" if P.get("size_max") in (None, "", "inf") else num(P["size_max"], 2, lang)
            total = P.get("perimeter") == "total" and not P.get("include_holes")
            m.append(step_tag("partikel") + f"Particles were detected as connected regions of the binary image (8-connectivity) with an area of "
                     f"{num(P.get('size_min') or 0, 2, lang)} to {tex_escape(smax)}\\,{unit} and a circularity $4\\pi A/P^2$ of "
                     f"{num(P.get('circ_min') or 0, 2, lang)} to {num(P.get('circ_max') if P.get('circ_max') is not None else 1, 2, lang)}"
                     + ("; holes were counted as particle area" if P.get("include_holes") else "") + ". "
                     "The perimeter is the length of the marching-squares contour between the pixel centres (straight steps "
                     "one pixel edge, corners cut by half a pixel diagonal), "
                     + ("including the boundaries of holes" if total else "outer contour only (holes filled)")
                     + "; the equivalent circle diameter (ECD) is the diameter of the circle of equal area.")
            if P.get("exclude_edges", True):
                m.append(step_tag("partikel") + "Only particles whose bounding box does not touch the border of the analysed area were measured; "
                         "each was weighted after Miles and Lantuéjoul by the inverse fraction of positions in which a box of "
                         "its size does not touch the border (image $W\\times H$, box $w\\times h$ pixels: "
                         "$WH/((W-w-1)(H-h-1))$). Means, standard deviations and D values use these weights; the area "
                         "fraction includes the particles at the border.")
            else:
                m.append(step_tag("partikel") + "Particles at the border of the analysed area were measured with their visible part (no edge correction).")
            m.append(step_tag("quantile") + "$D_{10}$, $D_{50}$ and $D_{90}$ are quantiles of the number distribution (Q0) of the ECD, $D_{v10}$, "
                     "$D_{v50}$ and $D_{v90}$ of the volume distribution (Q3, weight ECD$^3$, spheres assumed); quantiles by "
                     "the midpoint rule (for equal weights definition 5 of Hyndman and Fan"
                     + (f" \\cite{{{cites['q']}}}" if "q" in cites else "") + ").")
    if uo:
        m.append({"id": "unsicherheit", "title": "Messunsicherheit" if de else "Measurement uncertainty",
                  "text": "\n\n" + uo["latex"]})
    b.add_methods(m, T[lang]["methods"], sep=" ", eq=eq_text, brief=b.brief_from(m[0], evaluated=True))

    r = []
    if a.part is not None and "n" in have:
        if de:
            r.append(f"In {tex_escape(a.name)} wurden {v('n')} Partikel vermessen"
                     + (f" (randkorrigiert {v('nCorr')})" if "nCorr" in have else "")
                     + f"; die Partikel bedecken {v('areaFrac')} der ausgewerteten Fläche.")
            if "meanECD" in have:
                r.append(f"Der mittlere Äquivalentdurchmesser beträgt {v('meanECD')} (Standardabweichung {v('sdECD')}), die mittlere Fläche {v('meanArea')}.")
            if "D50" in have:
                r.append(f"Die Anzahlverteilung (Q0) hat die Kennwerte $D_{{10}}$ = {v('D10')}, $D_{{50}}$ = {v('D50')} und $D_{{90}}$ = {v('D90')}"
                         + (f"; nach Volumen (Q3) ist $D_{{v50}}$ = {v('Dv50')}." if "Dv50" in have else "."))
            if "meanCirc" in have:
                r.append(f"Die mittlere Zirkularität liegt bei {v('meanCirc')} (1 entspricht einem Kreis), der mittlere Feret-Durchmesser bei {v('meanFeret')}.")
        else:
            r.append(f"{v('n')} particles were measured in {tex_escape(a.name)}"
                     + (f" (edge-corrected {v('nCorr')})" if "nCorr" in have else "")
                     + f"; the particles cover {v('areaFrac')} of the analysed area.")
            if "meanECD" in have:
                r.append(f"The mean equivalent diameter is {v('meanECD')} (standard deviation {v('sdECD')}), the mean area {v('meanArea')}.")
            if "D50" in have:
                r.append(f"The number distribution (Q0) has $D_{{10}}$ = {v('D10')}, $D_{{50}}$ = {v('D50')} and $D_{{90}}$ = {v('D90')}"
                         + (f"; by volume (Q3), $D_{{v50}}$ = {v('Dv50')}." if "Dv50" in have else "."))
            if "meanCirc" in have:
                r.append(f"The mean circularity is {v('meanCirc')} (1 is a circle); the mean Feret diameter is {v('meanFeret')}.")
    c = a.state.get("compare") or {}
    if "cmpD50" in have:                           # I-04: Vergleichsverteilung aus einem Datensatz
        col = f"{tex_escape(c.get('name') or c.get('key') or '')} [{tex_escape(c.get('unit') or '1')}]"
        ttl = tex_escape(c.get("title") or c.get("share") or "")
        c_cmp = f" \\cite{{{cites['cmp']}}}" if "cmp" in cites else ""
        if de:
            r.append(f"Zum Vergleich wurde die Spalte ,,{col}`` des Datensatzes ,,{ttl}`` (Version {c.get('version')}){c_cmp} "
                     f"herangezogen ({v('cmpN')} Werte, jeder als ein Teilchen gezählt). Ihre Anzahlverteilung (Q0) hat $D_{{10}}$ = {v('cmpD10')}, $D_{{50}}$ = {v('cmpD50')} "
                     f"und $D_{{90}}$ = {v('cmpD90')}"
                     + (f"; der $D_{{50}}$ (Q0) der Partikel beträgt das {v('cmpRatio')}-Fache davon." if "cmpRatio" in have else "."))
        else:
            r.append(f"For comparison, the column ``{col}'' of the dataset ``{ttl}'' (version {c.get('version')}){c_cmp} was used "
                     f"({v('cmpN')} values, each counted as one particle). Its number distribution (Q0) has $D_{{10}}$ = {v('cmpD10')}, $D_{{50}}$ = {v('cmpD50')} "
                     f"and $D_{{90}}$ = {v('cmpD90')}"
                     + (f"; the particle $D_{{50}}$ (Q0) is {v('cmpRatio')} times that value." if "cmpRatio" in have else "."))
    for i, mm in enumerate(a.measurements, 1):
        if f"roi{i}Mean" in have:
            lab = tex_escape(mm["Label"])
            if de:
                r.append(f"In der Auswahl {lab} beträgt der mittlere Grauwert {v(f'roi{i}Mean')}"
                         + (f" bei einer Fläche von {v(f'roi{i}Area')}" if f"roi{i}Area" in have else "")
                         + (f" über eine Länge von {v(f'roi{i}Length')}" if f"roi{i}Length" in have else "") + ".")
            else:
                r.append(f"In selection {lab} the mean grey value is {v(f'roi{i}Mean')}"
                         + (f" over an area of {v(f'roi{i}Area')}" if f"roi{i}Area" in have else "")
                         + (f" along a length of {v(f'roi{i}Length')}" if f"roi{i}Length" in have else "") + ".")
    if uo:
        got = [f"{tex_escape(x['label'])} {v('unc-' + x['name'] + '-pm')}" for x in uo["results"].values()]
        r.append(("Mit Messunsicherheit: " if de else "With measurement uncertainty: ") + "; ".join(got) + ".")
    if r:
        b.add_text("ergebnisse", " ".join(r) + "\n", T[lang]["results"],
                   steps=["partikel", "quantile", "schwelle", "wasserscheide", "unsicherheit"])


def _multi(b: Bundle, analyses: list[Analysis], raws: list[int], lang: str, inc: dict):
    L = T[lang]
    u = _u(analyses[0].calib)
    if inc.get("citations", True):
        for a, rl in zip(analyses, raws):
            st = a.orig
            b.add_citation(f"data-{slugify(a.name, 30)}", "misc", title=tex_escape(a.name),
                           howpublished="Bilddatei" if lang == "de" else "Image file",
                           note=tex_escape(f"{st.width}×{st.height} px, {st.type_label()}"))
            _thr_cite(b, a)
    with_p = [a for a in analyses if a.part]
    if inc.get("figures", True):
        if with_p:
            series = [(a.name, [r["ECD"] for r in a.part["rows"]], [r.get("Weight", 1.0) for r in a.part["rows"]])
                      for a in with_p]
            b.add_figure(C.fig_compare(series, u, lang), "vergleich",
                         L["fig_cmp"].format(n=tex_escape(", ".join(a.name for a in with_p))), width="0.8", dpi=150,
                         steps=[])              # mehrere Bilder: das Bundle hat keinen Methodentext
        for i, a in enumerate(analyses, 1):
            base = a.intensity if a.kind == "binary" else a.img
            kind = ("gray" if base.ndim == 2 else "rgb")
            disp = display_for_pre(a) if a.kind == "binary" else (a.state.get("display") or {})
            rgb = C.render(base, kind, disp)
            from .measure import outline_rgba
            ov = outline_rgba(a.part["labels"]) if a.part else None
            b.add_figure(C.fig_image(rgb, a.calib, lang, overlay=ov, scalebar=a.state.get("scalebar")), f"bild{i}",
                         (L["fig_part"].format(n=tex_escape(a.name), c=len(a.part["rows"])) if a.part
                          else L["fig_img"].format(n=tex_escape(a.name), roi="")), width="0.48", dpi=130, steps=[])
    if inc.get("tables", True) and with_p:
        head = [h.format(u=tex_escape(u)) for h in L["cmp_head"]]
        rows = []
        for a in with_p:
            s = a.part["summary"]
            nd = _nd(s.get("MeanECD"))
            rows.append([tex_escape(a.name), num(s["Count"], 0, lang), num(s["AreaFraction"], 2, lang),
                         _pm(s.get("MeanECD"), s.get("SDECD"), nd, lang), num(s.get("D50"), nd, lang),
                         num(s.get("MeanCirc"), 2, lang)])
        b.add_table("vergleich", booktabs(head, rows, "lrrrrr", small=True, escape_header=False), L["tab_cmp"], steps=[])
    if inc.get("values", True) and with_p:
        vals = []
        for a in with_p:
            k = slugify(a.name, 24)
            s = a.part["summary"]
            vals.append((f"{k}-n", f"{a.name}: n", num(s["Count"], 0, lang), str(s["Count"])))
            vals.append((f"{k}-areaFrac", f"{a.name}: %", num(s["AreaFraction"], 2, lang, "%"), ""))
            if s.get("D50") is not None:
                vals.append((f"{k}-D50", f"{a.name}: D50", num(s["D50"], _nd(s["D50"]), lang, u), ""))
        b.add_values([(k, tex_escape(lbl), ltx, txt) for k, lbl, ltx, txt in vals])
        if any(a.state.get("unc") for a in with_p):
            _series_unc(b, with_p, lang)


def _series_unc(b: Bundle, analyses: list[Analysis], lang: str):
    """Mehrere Bilder (Felder): Mittelwert ± Unsicherheit von Flächenanteil, ECD und D50 (ASTM E562: t·s/√n)."""
    import labcite
    from labbundle import cite

    from labcalc import uncertainty as UN

    from . import uncertainty as UNC
    ser = UNC.series(analyses, lang)
    if not ser:
        return
    at = b.added_mark()
    uo = UN.to_report(b, list(ser.values()), lang, prefix="serie-")
    b.needs_since(at, [])
    keys = [labcite.to_bib(b, "astm-e562", UNC.SOURCES["astm-e562"])]
    de = lang == "de"
    n = next(iter(ser.values()))["n"]
    head = (f"Serie aus {n} Bildern (Feldern): Mittelwert je Kennwert, Standardunsicherheit des Mittelwerts aus der "
            "Streuung der Felder ($s/\\sqrt{n}$, $n-1$ Freiheitsgrade, Vertrauensbereich mit dem $t$-Faktor wie bei der "
            f"Punktzählung){cite(keys)}; Längen zusätzlich mit der relativen Unsicherheit des Massstabs, der für alle Bilder "
            "gleich ist." if de else
            f"Series of {n} images (fields): mean of each parameter, standard uncertainty of the mean from the scatter of the "
            "fields ($s/\\sqrt{n}$, $n-1$ degrees of freedom, confidence interval with the $t$ factor as for point "
            f"counting){cite(keys)}; lengths additionally carry the relative uncertainty of the scale, which is the same for "
            "all images.")
    vals = "; ".join(f"{tex_escape(x['label'])} \\labval{{{b.slug}}}{{serie-{x['name']}-pm}}" for x in ser.values())
    b.add_text("unsicherheit", head + "\n" + uo["latex"] + "\n\n" + vals + ".\n",
               "Messunsicherheit der Serie" if de else "Measurement uncertainty of the series", steps=[])


def build(items: list[tuple[Stack, bytes, dict]], request: dict, lang: str = "de", include: dict | None = None,
          title: str | None = None) -> dict:
    """items: (Originalbild, Rohdaten, Arbeitsstand) je Bild."""
    lang = lang if lang in T else "de"
    inc = {"figures": True, "tables": True, "values": True, "data": True, "citations": True, "text": True,
           **(include or {})}
    if inc["text"]:
        inc["values"] = inc["citations"] = True
    analyses = [run(st, state, lang) for st, _, state in items]
    names = ", ".join(a.name for a in analyses)
    L = T[lang]
    title = title or (L["title1"] if len(analyses) == 1 else L["titleN"]).format(n=names)
    parts = []
    for a in analyses:
        s = a.part["summary"] if a.part else None
        frac = f"{s['AreaFraction']:.1f}".replace(".", "," if lang == "de" else ".") if s else ""
        parts.append(f"{a.name}: " + (f"{s['Count']} {'Partikel' if lang == 'de' else 'particles'}, {frac} %" if s else
                                      f"{a.proc.stack.width}×{a.proc.stack.height} px"))
    b = Bundle(module="mikroskopie", module_name=L["module"], title=title, lang=lang,
               slug=request.get("slug") or None, summary=" · ".join(parts))
    if len(analyses) == 1:
        _single(b, analyses[0], len(items[0][1]), lang, inc)
    else:
        _multi(b, analyses, [len(raw) for _, raw, _ in items], lang, inc)
    b.set_source({**request, "slug": b.slug}, {st.name: raw for st, raw, _ in items})
    return b.to_dict()
