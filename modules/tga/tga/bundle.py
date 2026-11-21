"""Ergebnisse für den Berichtseditor (Folio Lab, Format folio-lab-bundle/1)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

try:
    import labcite
    from labbundle import Bundle, booktabs, cite, cite_keys, num, step_tag, tex_escape
except ImportError:  # Modul ausserhalb von Folio Lab gestartet
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "sdk" / "python"))
    import labcite
    from labbundle import Bundle, booktabs, cite, cite_keys, num, step_tag, tex_escape

from . import charts as C
from . import kinetics as K
from . import uncert as UC
from .analysis import Analysis, arr, run
from .library import GRID, MODEL_ID
from .readers import load_bytes
from .refs import REFS

T = {
    "de": {"module": "TGA", "title1": "TGA {n}", "titleN": "TGA-Vergleich", "methods": "Methodik", "results": "Ergebnisse",
           "fig_tg": "Thermogravimetrie von {n}: Masse (TG){{parts}}.", "fig_tg_dtg": "Massenverlustrate (DTG)", "fig_tg_st": "Stufen mit extrapolierten Onsets",
           "fig_cmp": "TG- und DTG-Kurven im Vergleich: {n}.", "fig_search": "Bibliothekssuche für {n}: DTG der Probe (oben) und die besten Treffer{mod}.",
           "fig_search_mod": "; Modellreferenzen sind aus Literaturwerten berechnet, nicht gemessen",
           "fig_mix": "Mischungsanalyse für {n}: DTG der Probe, angepasste Mischung und Komponenten; unten der Rest.",
           "fig_comp": "Zusammensetzung von {n} ({p}).", "fig_dc": "Trennung der DTG von {n} in Fraser-Suzuki-Spitzen.",
           "fig_kin": "Kinetik aus {k} Heizraten: Umsatz α(T) und Aktivierungsenergie Eₐ(α).",
           "tab_steps": "Massenverluststufen von {n}.", "tab_char": "Kennwerte von {n}: Temperatur bei x~\\% Massenverlust und Rückstand.",
           "tab_comp": "Zusammensetzung von {n} ({p}).", "tab_rx": "Gehalte aus der Stöchiometrie der Zersetzung ({n}).",
           "tab_cal": "Kalibrierprüfung mit Calciumoxalat-Monohydrat ({n}).", "tab_hits": "Bibliothekssuche für {n}; 100 = deckungsgleich.",
           "tab_mix": "Mischungsanalyse für {n} (Anpassung {h}); Gewichte = Massenanteile.", "tab_dc": "Fraser-Suzuki-Spitzen der DTG von {n}.",
           "tab_cmp": "TGA-Läufe im Vergleich.", "tab_kin": "Aktivierungsenergie Eₐ [kJ/mol] je Umsatz α (± 95-\\%-Vertrauensbereich).",
           "h_steps": ["Nr.", r"$T_\mathrm{on}$ [°C]", r"$T_\mathrm{p}$ [°C]", r"$T_\mathrm{end}$ [°C]", r"Verlust [\%]", "Verlust [mg]"],
           "h_char": ["Kennwert", "Wert"], "h_comp": ["Anteil", "Bereich", r"[\%]"], "h_rx": ["Zersetzung", "Stufe", r"theor. Verlust [\%]", r"Gehalt [\%]"],
           "h_cal": ["Abgabe", r"theoretisch [\%]", r"gemessen [\%]", "Abweichung"], "h_hits": ["Rang", "Referenz", "Herkunft", "Wert", "Verschiebung [K]"],
           "h_mix": ["Komponente", "Herkunft", r"Anteil [\%]"], "h_dc": ["Spitze", r"$T_\mathrm{p}$ [°C]", r"Fläche [\%]"],
           "h_cmp": ["Probe", r"$T_{5\%}$ [°C]", r"Stufe 1 [\%]", r"$T_\mathrm{p,1}$ [°C]", r"Rückstand [\%]"],
           "res": "Rückstand", "mean": "Mittelwert ± s"},
    "en": {"module": "TGA", "title1": "TGA {n}", "titleN": "TGA comparison", "methods": "Methods", "results": "Results",
           "fig_tg": "Thermogravimetry of {n}: mass (TG){{parts}}.", "fig_tg_dtg": "rate of mass loss (DTG)", "fig_tg_st": "steps with extrapolated onsets",
           "fig_cmp": "TG and DTG curves compared: {n}.", "fig_search": "Library search for {n}: DTG of the sample (top) and best hits{mod}.",
           "fig_search_mod": "; model references are calculated from literature values, not measured",
           "fig_mix": "Mixture analysis for {n}: sample DTG, fitted mixture and components; residual below.",
           "fig_comp": "Composition of {n} ({p}).", "fig_dc": "Separation of the DTG of {n} into Fraser-Suzuki peaks.",
           "fig_kin": "Kinetics from {k} heating rates: conversion α(T) and activation energy Eₐ(α).",
           "tab_steps": "Mass loss steps of {n}.", "tab_char": "Characteristic values of {n}: temperature at x~\\% mass loss and residue.",
           "tab_comp": "Composition of {n} ({p}).", "tab_rx": "Contents from decomposition stoichiometry ({n}).",
           "tab_cal": "Calibration check with calcium oxalate monohydrate ({n}).", "tab_hits": "Library search for {n}; 100 = identical.",
           "tab_mix": "Mixture analysis for {n} (fit {h}); weights = mass fractions.", "tab_dc": "Fraser-Suzuki peaks of the DTG of {n}.",
           "tab_cmp": "TGA runs compared.", "tab_kin": "Activation energy Eₐ [kJ/mol] per conversion α (± 95~\\% confidence interval).",
           "h_steps": ["No.", r"$T_\mathrm{on}$ [°C]", r"$T_\mathrm{p}$ [°C]", r"$T_\mathrm{end}$ [°C]", r"Loss [\%]", "Loss [mg]"],
           "h_char": ["Quantity", "Value"], "h_comp": ["Fraction", "Range", r"[\%]"], "h_rx": ["Decomposition", "Step", r"theor. loss [\%]", r"Content [\%]"],
           "h_cal": ["Released", r"theory [\%]", r"measured [\%]", "Deviation"], "h_hits": ["Rank", "Reference", "Origin", "Score", "Shift [K]"],
           "h_mix": ["Component", "Origin", r"Fraction [\%]"], "h_dc": ["Peak", r"$T_\mathrm{p}$ [°C]", r"Area [\%]"],
           "h_cmp": ["Sample", r"$T_{5\%}$ [°C]", r"Step 1 [\%]", r"$T_\mathrm{p,1}$ [°C]", r"Residue [\%]"],
           "res": "Residue", "mean": "Mean ± s"},
}
MODEL_KEY = "folio-tga-modell"


def tx(s) -> str:
    return tex_escape(str(s)).replace("₂", "$_2$").replace("₃", "$_3$").replace("ₐ", "$_a$").replace("α", r"$\alpha$")


def _n(v, nd, lang):
    return num(v, nd, lang) if v is not None and np.isfinite(v) else "--"


def mcite(b: Bundle, key: str) -> str:
    return labcite.to_bib(b, "tga-" + key, REFS[key])


def ref_keys(b: Bundle, refs, lang: str) -> list[str]:
    """Literatur der verwendeten Referenzen: Quelle des Eintrags; Modellbibliothek zusätzlich mit Hinweis."""
    de = lang == "de"
    keys = []
    for h in refs or []:
        src = h.get("source")
        if h.get("lib") == MODEL_ID:
            b.add_citation(MODEL_KEY, "misc", title=tex_escape(
                "Modellbibliothek TGA (Folio Lab): aus veröffentlichten Stufenwerten berechnete DTG-Kurven" if de else
                "TGA model library (Folio Lab): DTG curves calculated from published step values"),
                howpublished=tex_escape("Folio Lab, Modul TGA" if de else "Folio Lab, TGA module"),
                note=tex_escape("Keine gemessenen Kurven; Werte je Eintrag mit eigener Quelle" if de else
                                "Not measured curves; values of each entry with their own source"))
            keys.append(MODEL_KEY)
        elif h.get("lib"):
            name = h.get("lib_name") or h["lib"]
            k = "tgalib-" + labcite.key_for("", {"title": name})
            b.add_citation(k, "misc", title=tex_escape(f"TGA-Referenzbibliothek „{name}“" if de else f"TGA reference library “{name}”"),
                           howpublished=tex_escape("eigene Bibliothek in Folio Lab" if de else "own library in Folio Lab"))
            keys.append(k)
        if labcite.is_record(src):
            keys.append(labcite.to_bib(b, labcite.key_for("tgaref", src, h.get("name", "")), src))
        elif isinstance(src, str) and src.strip():
            r = labcite.from_legacy(src)
            keys.append(labcite.to_bib(b, labcite.key_for("tgaref", r, h.get("name", "")), r))
    return cite_keys(keys)


def _uses(a: Analysis, op):
    return any(st.get("op") == op for st in a.state.get("pipeline") or [])


def _search(a: Analysis):
    s = a.state.get("search") or {}
    hits = [dict(h, y=arr(h.get("y"))) for h in s.get("hits") or []]
    return s, hits, arr(s.get("query"))


def _mix(a: Analysis):
    m = a.state.get("mixture") or {}
    if not m.get("components"):
        return None
    return dict(m, fit=arr(m.get("fit")), residual=arr(m.get("residual")), query=arr(m.get("query")),
                components=[dict(c, y=arr(c.get("y"))) for c in m["components"]])


def _eq_needs(b: Bundle, at: tuple, steps: list):
    """Eigene Gleichungen: Tabelle, Budgets und Werte seit ``at`` brauchen den Gleichungsblock des Methodentexts."""
    for it in b.items[at[0]:]:
        if it.get("kind") == "table":
            it["needs"] = {"steps": list(steps)}
    b.needs_since(at, steps)


def _single(b: Bundle, a: Analysis, fname: str, raw_len: int, lang: str, inc: dict, prefix: str = ""):
    L = T[lang]
    n = tx(a.name)
    pid = prefix
    k = (prefix + "-") if prefix else ""
    cit = inc.get("citations", True)
    cites = {}
    if cit:
        fmt = a.orig.meta.get("format", "")
        cites["data"] = f"data-{b.slug}{('-' + prefix) if prefix else ''}"
        dsrc = a.orig.meta.get("dataset") or {}
        if dsrc.get("share"):                          # DP-13: statt des Dateiformats die Datensatz-Version
            fmt = f"{'Datensatz' if lang == 'de' else 'dataset'} {dsrc['share']} v{dsrc.get('version')}"
        b.add_citation(cites["data"], "misc", title=tex_escape(a.name), howpublished=tex_escape(fname),
                       note=tex_escape(f"{fmt}, {len(a.orig.m)} " + ("Punkte" if lang == "de" else "points") + f", {raw_len / 1024:.0f} KiB"))
        cites["iso"] = mcite(b, "iso11358-1")
        if _uses(a, "smooth") or True:
            cites["sg"] = mcite(b, "savgol")
        if a.comp and a.comp.get("ref"):
            cites["comp"] = mcite(b, a.comp["ref"])
        if a.reactions:
            cites["stoich"] = ",".join([mcite(b, "ciaaw2021"), mcite(b, "brown2001")])
        if a.deconv and not a.deconv.get("error"):
            cites["fs"] = ",".join([mcite(b, "frasersuzuki"), mcite(b, "perejon2011")] +
                                   ([mcite(b, "yang2007")] if a.deconv.get("preset") == "biomass" else []))
        if _uses(a, "tcal"):
            cites["tcal"] = mcite(b, "astm-e1582")
        if a.dsc and (a.dsc.get("peaks") or a.dsc.get("tg")):
            cites["dsc"] = ",".join(mcite(b, x) for x in (["iso11357-1"] + (["iso11357-2"] if a.dsc.get("tg") else [])))
    s, hits, q = _search(a)
    mix = _mix(a)
    drawn = [h for h in hits if h.get("y") is not None][:3]
    rk = {}
    if cit and (hits or mix):
        cites["schindler"] = mcite(b, "schindler2017")
        rk = {"drawn": ref_keys(b, drawn, lang), "hits": ref_keys(b, hits[:10], lang),
              "mix": ref_keys(b, (mix or {}).get("components") or [], lang)}
        cites["refs"] = ",".join(cite_keys(rk["hits"] + rk["mix"]))
    ovs = [o for o in a.state.get("overlays") or [] if o.get("tg") is not None]
    if cit and ovs:
        rk["overlay"] = ref_keys(b, ovs, lang)
    st = a.steps
    if inc.get("figures", True):
        de = lang == "de"
        tparts = [{"id": "dtg", "label": "DTG", "steps": ["dtg"], "caption": L["fig_tg_dtg"]}]
        if st:
            tparts.append({"id": "stufen", "label": "Stufen" if de else "Steps", "steps": ["dtg", "stufen"], "caption": L["fig_tg_st"]})
        if (a.st.get("residue") or {}).get("end") is not None:
            tparts.append({"id": "rueckstand", "label": "Rückstand" if de else "Residue"})
        for i, o in enumerate(ovs, 1):                 # jede eingeblendete Referenz mit ihrer eigenen Quelle
            tparts.append({"id": f"referenz{i}", "label": o.get("name") or f"{i}", "list": "Gestrichelt zum Vergleich:" if de else "Dashed for comparison:",
                           "note": tx(o.get("name", "")) + (((" (modelliert aus Literaturwerten)" if de else " (modelled from literature values)"))
                                                            if o.get("modelled") else ""),
                           "cites": ref_keys(b, [o], lang) if cit else []})
        b.add_figure(C.fig_tg_dtg(a, lang), f"tg{pid}", L["fig_tg"].format(n=n), width="0.9", dpi=150,
                     cites=[cites["data"]] if cit else None, steps=[], parts=tparts)
        if hits and q is not None and drawn:
            mod = any(h.get("modelled") for h in drawn)
            hparts = [{"id": f"treffer{i}", "label": h.get("name") or f"{i}", "cites": ref_keys(b, [h], lang) if cit else []}
                      for i, h in enumerate(drawn, 1)]
            b.add_figure(C.fig_search(GRID, q, hits, lang, a.name), f"suche{pid}",
                         L["fig_search"].format(n=n, mod=L["fig_search_mod"] if mod else ""), width="0.9", dpi=150,
                         steps=["suche", "dtg"], parts=hparts)
        if mix and mix["query"] is not None:
            mparts = [{"id": f"komponente{i}", "label": x.get("name") or f"{i}", "cites": ref_keys(b, [x], lang) if cit else []}
                      for i, x in enumerate(mix.get("components") or [], 1)]
            b.add_figure(C.fig_mixture(GRID, mix["query"], mix, lang, a.name), f"mischung{pid}", L["fig_mix"].format(n=n),
                         width="0.9", dpi=150, steps=["mischung", "dtg"], parts=mparts)
        if a.comp and a.comp.get("rows"):
            b.add_figure(C.fig_composition(a.comp, lang), f"zusammensetzung{pid}", L["fig_comp"].format(n=n, p=tx(a.comp["label"])),
                         width="0.9", dpi=150, cites=[cites["comp"]] if cites.get("comp") else None, steps=["zusammensetzung"])
        if a.deconv and not a.deconv.get("error"):
            b.add_figure(C.fig_deconv(a.deconv, lang, a.name), f"trennung{pid}", L["fig_dc"].format(n=n), width="0.9", dpi=150,
                         cites=cites["fs"].split(",") if cites.get("fs") else None, steps=["dtg", "trennung"])
        if a.dsc and any("error" not in p for p in (a.dsc.get("peaks") or []) + (a.dsc.get("tg") or [])):
            dk = cites["dsc"].split(",") if cites.get("dsc") else []
            dparts = []
            if any("error" not in p for p in a.dsc.get("peaks") or []):
                dparts.append({"id": "peaks", "label": "Peaks", "cites": dk[:1],
                               "caption": ("ausgewerteten Peaks (Basislinie gestrichelt, Fläche schattiert)" if lang == "de" else
                                           "evaluated peaks (baseline dashed, area shaded)")})
            if any("error" not in g for g in a.dsc.get("tg") or []):
                dparts.append({"id": "glas", "label": "Glasübergänge" if lang == "de" else "Glass transitions", "cites": dk[-1:],
                               "caption": "Glasübergängen" if lang == "de" else "glass transitions"})
            b.add_figure(C.fig_dsc(a.run, a.dsc, lang), f"dsc{pid}",
                         f"Wärmestrom von {n}{{parts}}." if lang == "de" else f"Heat flow of {n}{{parts}}.",
                         width="0.9", dpi=150, steps=["dsc"], parts=dparts)
    if inc.get("tables", True):
        if st:
            rows = [[str(x["no"]), _n(x.get("T_onset"), 1, lang), _n(x.get("T_peak"), 1, lang), _n(x.get("T_endset"), 1, lang),
                     _n(x["loss"], 2, lang), _n(x.get("loss_mg"), 3, lang)] for x in st]
            b.add_table(f"stufen{pid}", booktabs(L["h_steps"], rows, align="rrrrrr", small=True, escape_header=False),
                        L["tab_steps"].format(n=n), cites=[cites["iso"]] if cit else None, steps=["dtg", "stufen"])
        rows = []
        for lv, x in (a.st.get("loss_T") or {}).items():
            if x and x.get("T") is not None:
                rows.append([f"$T_{{{lv}\\%}}$", _n(x["T"], 1, lang) + " °C"])
        res = a.st.get("residue") or {}
        if res.get("end") is not None:
            rows.append([L["res"] + (f" ({_n(res.get('T_end'), 0, lang)} °C)" if res.get("T_end") is not None else ""),
                         _n(res["end"], 2, lang) + r"~\%"])
        if rows:
            b.add_table(f"kennwerte{pid}", booktabs(L["h_char"], rows, align="lr", small=True), L["tab_char"].format(n=n), steps=[])
        if a.comp and a.comp.get("rows"):
            basis = a.comp.get("basis")
            rows = []
            for r in a.comp["rows"]:
                row = [tx(r["name"]), tx(f"{r['from']} – {r['to']}" if r.get("to") else r["from"]), _n(r["pct"], 2, lang)]
                if basis:                                  # ASTM D7582: wie bestimmt und wasserfrei
                    row.append(_n(r.get("dry"), 2, lang))
                rows.append(row)
            notes = " ".join(tx(w) for w in ([basis[lang if lang in basis else "en"]] if basis else []) + list(a.comp.get("warnings") or []))
            head = L["h_comp"] + ([r"trocken [\%]" if lang == "de" else r"dry [\%]"] if basis else [])
            b.add_table(f"zusammensetzung{pid}", booktabs(head, rows, align="llrr" if basis else "llr", small=True, escape_header=False),
                        L["tab_comp"].format(n=n, p=tx(a.comp["label"])), notes=notes,
                        cites=[cites["comp"]] if cites.get("comp") else None, steps=["zusammensetzung"])
        if a.reactions:
            rows = [[tx(r["label"]), str(r["step"]), _n(r["theory"], 2, lang), _n(r["content"], 1, lang)] for r in a.reactions]
            b.add_table(f"stoechiometrie{pid}", booktabs(L["h_rx"], rows, align="lrrr", small=True, escape_header=False),
                        L["tab_rx"].format(n=n), cites=cites["stoich"].split(",") if cites.get("stoich") else None,
                        steps=["dtg", "stufen", "stoechiometrie"])
        if a.calib and a.calib.get("rows"):
            rows = [[tx(r["gas"]), _n(r["theory"], 2, lang), _n(r["measured"], 2, lang), _n(r["delta"], 2, lang)] for r in a.calib["rows"]]
            b.add_table(f"kalibrierung{pid}", booktabs(L["h_cal"], rows, align="lrrr", small=True, escape_header=False), L["tab_cal"].format(n=n), steps=[])
        cell = (lambda h: tx(C.ref_tag(h, lang)) + (cite(ref_keys(b, [h], lang)) if rk else ""))  # noqa: E731
        if hits:
            rows = [[str(h.get("rank", i + 1)), tx(h["name"]), cell(h), num(h["hqi"], 1, lang), f"{h.get('shift', 0):+d}"]
                    for i, h in enumerate(hits[:10])]
            b.add_table(f"treffer{pid}", booktabs(L["h_hits"], rows, align="rlllr", small=True), L["tab_hits"].format(n=n), cites=rk.get("hits"),
                        steps=["suche", "dtg"])
        if mix:
            rows = [[tx(c["name"]), cell(c), num(100 * c["frac"], 1, lang)] for c in mix["components"]]
            if mix.get("inert", 0) > 0.005:
                rows.append([tx("ohne Massenverlust (inert)" if lang == "de" else "no mass loss (inert)"), "", num(100 * mix["inert"], 1, lang)])
            b.add_table(f"mischung{pid}", booktabs(L["h_mix"], rows, align="llr", small=True, escape_header=False),
                        L["tab_mix"].format(n=n, h=num(mix["hqi"], 1, lang)), cites=rk.get("mix"), steps=["mischung", "dtg"])
        if a.deconv and not a.deconv.get("error"):
            rows = [[tx(p["name"]), _n(p["x0"], 1, lang), _n(p["area"], 2, lang)] for p in a.deconv["peaks"]]
            b.add_table(f"trennung{pid}", booktabs(L["h_dc"], rows, align="lrr", small=True, escape_header=False), L["tab_dc"].format(n=n),
                        steps=["dtg", "trennung"])
        pk = [p for p in (a.dsc or {}).get("peaks") or [] if "error" not in p]
        if pk:
            de = lang == "de"
            kind = {"endo": "endotherm" if de else "endothermic", "exo": "exotherm" if de else "exothermic"}
            rows = [[str(i), kind[p["kind"]], _n(p["lo"], 0, lang) + "--" + _n(p["hi"], 0, lang), _n(p.get("T_onset"), 1, lang),
                     _n(p["T_peak"], 1, lang), _n(p.get("T_endset"), 1, lang),
                     _n(p["dH"], 2, lang) if p.get("dH") is not None else _n(p["area"], 2, lang) + " " + tx(p["area_unit"])]
                    for i, p in enumerate(pk, 1)]
            hdr = (["Nr.", "Art", r"Bereich [°C]", r"$T_\mathrm{on}$ [°C]", r"$T_\mathrm{p}$ [°C]", r"$T_\mathrm{end}$ [°C]", r"$\Delta h$ [J/g]"]
                   if de else ["No.", "Type", r"Range [°C]", r"$T_\mathrm{on}$ [°C]", r"$T_\mathrm{p}$ [°C]", r"$T_\mathrm{end}$ [°C]", r"$\Delta h$ [J/g]"])
            b.add_table(f"dsc-peaks{pid}", booktabs(hdr, rows, align="llrrrrr", small=True, escape_header=False),
                        (f"DSC-Peaks von {n} (lineare Basislinie, Enthalpie bezogen auf die Einwaage)." if de else
                         f"DSC peaks of {n} (linear baseline, enthalpy per initial mass)."),
                        cites=cites["dsc"].split(",")[:1] if cites.get("dsc") else None, steps=["dsc"])
        gs = [g for g in (a.dsc or {}).get("tg") or [] if "error" not in g]
        if gs:
            de = lang == "de"
            rows = [[str(i), _n(g.get("T_onset"), 1, lang), _n(g["Tg_mid"], 1, lang), _n(g.get("T_endset"), 1, lang),
                     _n(g.get("dcp"), 3, lang)] for i, g in enumerate(gs, 1)]
            hdr = (["Nr.", r"$T_\mathrm{g,on}$ [°C]", r"$T_\mathrm{g,mid}$ [°C]", r"$T_\mathrm{g,end}$ [°C]", r"$\Delta c_p$ [J/(g\,K)]"])
            b.add_table(f"dsc-tg{pid}", booktabs(hdr, rows, align="lrrrr", small=True, escape_header=False),
                        (f"Glasübergänge von {n} (Mittelpunkt bei halber Stufenhöhe)." if de else
                         f"Glass transitions of {n} (midpoint at half step height)."),
                        cites=cites["dsc"].split(",")[-1:] if cites.get("dsc") else None, steps=["dsc"])
    eq = None
    if a.equations and any(r.get("value") is not None for r in a.equations):
        from labcalc import formulas as F
        at = b.added_mark()
        eq = F.to_report(b, a.equations, lang, prefix=k)
        # im Methodentext stehen nur die Gleichungen des ersten Laufs (build); weitere Läufe brauchen keinen Schritt
        _eq_needs(b, at, ["gleichungen"] if prefix in ("", "p1") else [])
    a.unc_report = None
    if a.unc and a.unc.get("results") and (inc.get("values", True) or inc.get("tables", True)):
        at = b.added_mark()
        a.unc_report = UC.report(b, a.unc, lang, prefix=k)     # \labval <id>-pm/-u/-U, Budgets, Übersicht
        b.needs_since(at, ["unsicherheit"])
        ks = set(a.unc.get("keys") or [])
        if a.unc_report and cit:                       # Grundlagen der Modelle: Kalibrierung von Temperatur und Waage
            a.unc_report["cites"] = list(a.unc_report.get("cites") or []) + \
                ([mcite(b, "astm-e1582")] if "T_cal" in ks else []) + ([mcite(b, "astm-e2040")] if ks & {"bal", "drift"} else [])
    if inc.get("values", True):
        vals = []
        for x in st:
            i = x["no"]
            vals.append((f"{k}step{i}-loss", f"Verlust Stufe {i}" if lang == "de" else f"Loss step {i}", num(x["loss"], 2, lang) + r"\,\%", f"{x['loss']:.2f} %"))
            for key, lab in (("T_onset", "Onset"), ("T_peak", "DTG-Spitze" if lang == "de" else "DTG peak"), ("T_endset", "Endset")):
                if x.get(key) is not None:
                    vals.append((f"{k}step{i}-{key[2:]}", f"{lab} {i}", num(x[key], 1, lang) + r"\,°C", f"{x[key]:.1f} °C"))
        for lv, x in (a.st.get("loss_T") or {}).items():
            if x and x.get("T") is not None:
                vals.append((f"{k}t{lv}", f"T {lv} %", num(x["T"], 1, lang) + r"\,°C", f"{x['T']:.1f} °C"))
        res = a.st.get("residue") or {}
        if res.get("end") is not None:
            vals.append((f"{k}residue", L["res"], num(res["end"], 2, lang) + r"\,\%", f"{res['end']:.2f} %"))
        if a.comp:
            for i, r in enumerate(a.comp.get("rows") or [], 1):
                vals.append((f"{k}comp{i}", tx(r["name"]), num(r["pct"], 2, lang) + r"\,\%", f"{r['pct']:.2f} %"))
        for i, r in enumerate(a.reactions, 1):
            vals.append((f"{k}content{i}", tx(r["label"]), num(r["content"], 1, lang) + r"\,\%", f"{r['content']:.1f} %"))
        for i, p in enumerate([p for p in (a.dsc or {}).get("peaks") or [] if "error" not in p], 1):
            vals.append((f"{k}dsc{i}-tp", f"DSC Peak {i}", num(p["T_peak"], 1, lang) + r"\,°C", f"{p['T_peak']:.1f} °C"))
            if p.get("dH") is not None:
                vals.append((f"{k}dsc{i}-dh", f"Delta h {i}", num(p["dH_signed"], 2, lang) + r"\,J/g", f"{p['dH_signed']:.2f} J/g"))
        for i, g in enumerate([g for g in (a.dsc or {}).get("tg") or [] if "error" not in g], 1):
            vals.append((f"{k}tg{i}", f"Tg {i}", num(g["Tg_mid"], 1, lang) + r"\,°C", f"{g['Tg_mid']:.1f} °C"))
        if hits:
            vals.append((f"{k}hit1", "Bester Treffer" if lang == "de" else "Best hit", tx(hits[0]["name"]), hits[0]["name"]))
            vals.append((f"{k}hqi1", "Trefferwert" if lang == "de" else "Hit score", num(hits[0]["hqi"], 1, lang), f"{hits[0]['hqi']:.1f}"))
        if vals:
            b.add_values(vals, needs={v[0]: _value_steps(v[0][len(k):]) for v in vals if _value_steps(v[0][len(k):])})
    if inc.get("data", True):
        r = a.run
        step = max(1, len(r.m) // 3000)
        d = a.st.get("dtg") or {}
        dt = -np.nan_to_num(d.get("dT"), nan=0.0) if d.get("dT") is not None else np.zeros(len(r.m))
        b.add_data_csv(f"tg{pid}", ["t_min", "T_C", "m_pct", "dtg_pct_C"],
                       [[float(x), float(y), float(z), float(w)] for x, y, z, w in
                        zip(r.time()[::step], np.nan_to_num(r.T[::step]), r.pct()[::step], dt[::step])],
                       f"TG/DTG {n}.", labels={"T_C": "T [°C]", "m_pct": r"m [\%]", "dtg_pct_C": r"DTG [\%/°C]"},
                       plot={"x": "T_C", "y": "m_pct"})
    return cites, hits, mix, eq


def _value_steps(key: str) -> list[str]:
    """Methodenschritte, die ein einzeln eingefügter Wert braucht (Schlüssel ohne Präfix der Messung)."""
    for pre, steps in (("step", ["dtg", "stufen"]), ("comp", ["zusammensetzung"]), ("content", ["dtg", "stufen", "stoechiometrie"]),
                       ("dsc", ["dsc"]), ("tg", ["dsc"]), ("hit", ["suche", "dtg"]), ("hqi", ["suche", "dtg"])):
        if key.startswith(pre):
            return steps
    return []


_RESULT_STEPS = ["dtg", "stufen", "zusammensetzung", "stoechiometrie", "trennung", "suche", "mischung", "dsc", "unsicherheit"]


def _dsc_text(a: Analysis, c, lang: str) -> str:
    """Methodensatz zur Wärmestromauswertung (TGA-03)."""
    d = a.dsc or {}
    if not any("error" not in p for p in (d.get("peaks") or []) + (d.get("tg") or [])):
        return ""
    de = lang == "de"
    conv = ("exotherm nach oben" if d["sign"] == "exo_up" else "endotherm nach oben") if de else \
        ("exothermic up" if d["sign"] == "exo_up" else "endothermic up")
    if de:
        t = (f" Das Wärmestromsignal ({conv}) wurde nach ISO~11357-1{c('dsc')} ausgewertet: lineare Basislinie zwischen den "
             "Bereichsgrenzen, Peakfläche über der Zeit, extrapolierte Onset- und Endtemperatur als Schnitt der Wendetangente "
             "mit der Basislinie; Enthalpien sind auf die Einwaage bezogen und endotherm positiv.")
        if d.get("tg"):
            t += " Glasübergänge: Mittelpunkttemperatur bei halber Stufenhöhe zwischen den extrapolierten Basislinien (ISO~11357-2)."
        if d["unit"] == "uV":
            t += " Das Signal liegt in µV vor (nicht kalibriert); angegeben sind nur Flächen."
        t += " Temperatur- und Wärmestromkalibrierung stammen aus dem Gerät und wurden nicht geprüft."
    else:
        t = (f" The heat-flow signal ({conv}) was evaluated according to ISO~11357-1{c('dsc')}: linear baseline between the range "
             "limits, peak area over time, extrapolated onset and endset as intersection of the inflection tangent with the "
             "baseline; enthalpies refer to the initial mass and are positive for endothermic events.")
        if d.get("tg"):
            t += " Glass transitions: midpoint temperature at half step height between the extrapolated baselines (ISO~11357-2)."
        if d["unit"] == "uV":
            t += " The signal is in µV (not calibrated); only areas are given."
        t += " Temperature and heat-flow calibration come from the instrument and were not checked."
    return t


def _ds_sentence(a: Analysis, lang: str, named: bool = False) -> str:
    """DP-13: Herkunft eines Laufs aus einem Datensatz der Datenaufbereitung (ID und Version)."""
    d = (a.orig.meta or {}).get("dataset") or {}
    if not d.get("share"):
        return ""
    n = int(d.get("excluded") or 0)
    if lang == "de":
        s = (f"Die Messwerte{' von ' + a.name if named else ''} stammen aus dem Datensatz „{d.get('title') or d['share']}“ "
             f"(ID {d['share']}, Version {d.get('version')}) der Datenaufbereitung")
        s += f"; {n} als ausgeschlossen markierte Zeile{'n' if n != 1 else ''} blieb{'en' if n != 1 else ''} unberücksichtigt." if n else "."
    else:
        s = (f"The data{' of ' + a.name if named else ''} come from dataset “{d.get('title') or d['share']}” "
             f"(ID {d['share']}, version {d.get('version')}) of the data preparation module")
        s += f"; {n} row{'s' if n != 1 else ''} marked as excluded {'were' if n != 1 else 'was'} left out." if n else "."
    return tx(s)


def _weights_text(a: Analysis, lang: str) -> str:
    """Gewichtung des Trefferwerts (Kurve/Stufen), wie sie bei der Suche gewählt war."""
    s = a.state.get("search") or {}
    mode = s.get("mode") or "both"
    de = lang == "de"
    if mode == "curve":
        return " Trefferwert: nur Kurvenvergleich." if de else " Hit score: curve comparison only."
    if mode == "steps":
        return " Trefferwert: nur Stufenvergleich." if de else " Hit score: step comparison only."
    try:
        w = float(s.get("w_curve", 0.6) if s.get("w_curve") is not None else 0.6)
    except (TypeError, ValueError):
        w = 0.6
    pc, ps = num(100 * w, 0, lang), num(100 * (1 - w), 0, lang)
    return (f" Trefferwert: {pc}~\\% Kurven- und {ps}~\\% Stufenvergleich." if de else
            f" Hit score: {pc}~\\% curve and {ps}~\\% step comparison.")


def _methods(a: Analysis, cites: dict, hits, mix, eq, lang: str) -> str:
    c = lambda k: (r"~\cite{" + cites[k] + "}") if cites.get(k) else ""  # noqa: E731
    de = lang == "de"
    r, o = a.run, a.orig
    meta = o.meta
    bits = []
    if o.m0:
        bits.append((f"Einwaage {num(o.m0, 3, lang)}~mg" if de else f"sample mass {num(o.m0, 3, lang)}~mg"))
    if meta.get("rate"):
        bits.append((f"Heizrate {num(meta['rate'], 1, lang)}~K/min" if de else f"heating rate {num(meta['rate'], 1, lang)}~K/min"))
    if meta.get("gas"):
        g = " → ".join(meta.get("gases") or [meta["gas"]])
        bits.append(("Atmosphäre " if de else "atmosphere ") + tx(g))
    if meta.get("crucible"):
        bits.append(("Tiegel " if de else "crucible ") + tx(meta["crucible"]))
    if meta.get("instrument"):
        bits.append(tx(meta["instrument"]))
    proc = "; ".join(tx(x) for x in a.proc.steps)
    w = (a.state.get("steps") or {}).get("opts", {}) or {}
    width = w.get("width", 4.0)
    if de:
        t = (f"Der Lauf {tx(a.name)}{c('data')} ({', '.join(bits) if bits else 'Messbedingungen nicht in der Datei'}) wurde nach "
             f"ISO~11358-1{c('iso')} ausgewertet.")
        ds = _ds_sentence(a, lang)
        t += f" {ds}" if ds else ""
        t += f" Bearbeitung: {proc}." if proc else ""
        if cites.get("tcal"):
            t += (f" Die Temperaturachse wurde linear korrigiert ($T' = a + bT$; zur Temperaturkalibrierung von Thermowaagen vgl. "
                  f"ASTM~E1582{c('tcal')}); $a$ und $b$ wurden vom Anwender vorgegeben.")
        t += step_tag("dtg")
        t += (f" Die DTG wurde mit einem Savitzky-Golay-Filter{c('sg')} über etwa {num(width, 0, lang)}~K berechnet."
              + step_tag("stufen") + " Stufen wurden aus den Spitzen der Massenverlustrate bestimmt" +
              (" (Grenzen von Hand gesetzt)" if a.st.get("manual") else "") +
              "; die extrapolierte Onset- und Endtemperatur ist der Schnittpunkt der Tangente im Wendepunkt der TG-Kurve über "
              "der Temperatur (örtliche Steigung dm/dT) mit der verlängerten Basislinie vor bzw. nach der Stufe.")
        if a.comp and a.comp.get("rows"):
            t += step_tag("zusammensetzung") + f" Die Zusammensetzung folgt {tx(a.comp['label'])}{c('comp')}."
        if a.reactions:
            t += step_tag("stoechiometrie") + f" Gehalte aus Stufen wurden über die theoretischen Massenverluste der Zersetzung berechnet (Atomgewichte nach IUPAC{c('stoich')})."
        if a.deconv and not a.deconv.get("error"):
            t += step_tag("trennung") + f" Überlappende Stufen wurden durch Anpassung von Fraser-Suzuki-Spitzen an die DTG getrennt{c('fs')}."
        if hits:
            libs = ", ".join(sorted({tx(h.get('lib_name', '')) for h in hits}))
            t += step_tag("suche") + (f" Zur Identifizierung wurde die DTG mit Referenzen aus {libs} verglichen (Kurvenähnlichkeit und Stufenwerte, "
                  f"vgl. Schindler u.~a.{c('schindler')}); Referenzen durften um bis zu ±{int((a.state.get('search') or {}).get('shift', 20))}~K verschoben werden.")
            t += _weights_text(a, lang)
            if any(h.get("lib") == MODEL_ID for h in hits):
                t += " Modellreferenzen sind aus veröffentlichten Stufenwerten berechnet, nicht gemessen; Treffer daraus sind Hinweise."
            if cites.get("refs"):
                t += f" Quellen der Referenzen:{c('refs')}."
        if mix:
            t += step_tag("mischung") + " Für die Mischungsanalyse wurde die DTG als nichtnegative Summe von Referenz-DTGs angepasst; die Gewichte sind Massenanteile."
        t += step_tag("dsc") + _dsc_text(a, c, lang)
        if eq and eq.get("latex"):
            t += step_tag("gleichungen") + "\n\n" + eq["latex"]
    else:
        t = (f"Run {tx(a.name)}{c('data')} ({', '.join(bits) if bits else 'conditions not in the file'}) was evaluated according to "
             f"ISO~11358-1{c('iso')}.")
        ds = _ds_sentence(a, lang)
        t += f" {ds}" if ds else ""
        t += f" Processing: {proc}." if proc else ""
        if cites.get("tcal"):
            t += (f" The temperature axis was corrected linearly ($T' = a + bT$; for the temperature calibration of thermogravimetric "
                  f"analyzers cf. ASTM~E1582{c('tcal')}); $a$ and $b$ were set by the user.")
        t += step_tag("dtg")
        t += (f" The DTG was calculated with a Savitzky-Golay filter{c('sg')} over about {num(width, 0, lang)}~K."
              + step_tag("stufen") + " Steps were taken from the peaks of the mass loss rate" + (" (limits set by hand)" if a.st.get("manual") else "") +
              "; the extrapolated onset and endset are the intersections of the tangent at the inflection point of the TG "
              "curve over temperature (local slope dm/dT) with the extended baseline before and after the step.")
        if a.comp and a.comp.get("rows"):
            t += step_tag("zusammensetzung") + f" The composition follows {tx(a.comp['label'])}{c('comp')}."
        if a.reactions:
            t += step_tag("stoechiometrie") + f" Contents were calculated from theoretical decomposition losses (IUPAC atomic weights{c('stoich')})."
        if a.deconv and not a.deconv.get("error"):
            t += step_tag("trennung") + f" Overlapping steps were separated by fitting Fraser-Suzuki peaks to the DTG{c('fs')}."
        if hits:
            libs = ", ".join(sorted({tx(h.get('lib_name', '')) for h in hits}))
            t += step_tag("suche") + (f" For identification the DTG was compared with references from {libs} (curve similarity and step values, cf. "
                  f"Schindler et al.{c('schindler')}).")
            t += _weights_text(a, lang)
            if any(h.get("lib") == MODEL_ID for h in hits):
                t += " Model references are calculated from published step values, not measured; their hits are indications."
            if cites.get("refs"):
                t += f" Sources of the references:{c('refs')}."
        if mix:
            t += step_tag("mischung") + " For the mixture analysis the DTG was fitted as a non-negative sum of reference DTGs; weights are mass fractions."
        t += step_tag("dsc") + _dsc_text(a, c, lang)
        if eq and eq.get("latex"):
            t += step_tag("gleichungen") + "\n\n" + eq["latex"]
    ut = UC.methods_text(a.unc, getattr(a, "unc_report", None), lambda ks: cite(ks) if ks else "", lang)
    if ut:                                             # Messunsicherheit: Verfahren, Eingangsgrössen, Modelle
        t += step_tag("unsicherheit") + "\n\n" + ut
    return t + "\n"


def _results(a: Analysis, hits, mix, lang: str, slug: str, prefix: str) -> str:
    de = lang == "de"
    k = (prefix + "-") if prefix else ""
    parts = []
    st = a.steps
    if st:
        lst = ", ".join(f"\\labval{{{slug}}}{{{k}step{x['no']}-loss}}" + (f" (Spitze \\labval{{{slug}}}{{{k}step{x['no']}-peak}})" if de and x.get("T_peak") is not None
                                                                            else f" (peak \\labval{{{slug}}}{{{k}step{x['no']}-peak}})" if x.get("T_peak") is not None else "")
                        for x in st)
        parts.append((f"{tx(a.name)} verliert in {len(st)} Stufe{'n' if len(st) > 1 else ''} Masse: {lst}." if de else
                      f"{tx(a.name)} loses mass in {len(st)} step{'s' if len(st) > 1 else ''}: {lst}."))
    if (a.st.get("loss_T") or {}).get("5"):
        parts.append((f"5~\\% Massenverlust sind bei \\labval{{{slug}}}{{{k}t5}} erreicht." if de else
                      f"5~\\% mass loss is reached at \\labval{{{slug}}}{{{k}t5}}."))
    if (a.st.get("residue") or {}).get("end") is not None:
        parts.append((f"Der Rückstand beträgt \\labval{{{slug}}}{{{k}residue}}." if de else f"The residue is \\labval{{{slug}}}{{{k}residue}}."))
    if a.calib and a.calib.get("rows"):
        parts.append(("Die Kalibrierprüfung mit Calciumoxalat ist " + ("bestanden." if a.calib["ok"] else "nicht bestanden.")) if de else
                     ("The calcium oxalate check " + ("passed." if a.calib["ok"] else "failed.")))
    if hits:
        parts.append((f"Bester Bibliothekstreffer ist \\labval{{{slug}}}{{{k}hit1}} (Wert \\labval{{{slug}}}{{{k}hqi1}})." if de else
                      f"The best library hit is \\labval{{{slug}}}{{{k}hit1}} (score \\labval{{{slug}}}{{{k}hqi1}})."))
    if mix:
        comp = ", ".join(f"{tx(c['name'])} ({num(100 * c['frac'], 0, lang)}~\\%)" for c in mix["components"])
        parts.append((f"Als Mischung passt {comp}." if de else f"As a mixture, {comp} fits."))
    return " ".join(parts) + "\n" if parts else ""


def _kinetics(b: Bundle, analyses, req: dict, lang: str, inc: dict) -> str:
    de = lang == "de"
    ids = set(req.get("names") or [])
    runs = [a.run for a, _, _ in analyses if not ids or a.name in ids]
    res = K.run_all(runs, float(req["T_lo"]), float(req["T_hi"]), req.get("opts"))
    keys = {}
    if inc.get("citations", True):
        for kk in ("friedman", "ozawa", "flynnwall", "kas", "starink", "vyazovkin1997", "senumyang", "kissinger", "coatsredfern",
                   "ictac2011", "ictac2014", "astm-e1641"):
            keys[kk] = mcite(b, kk)
        if res.get("lifetime"):
            keys["e1877"] = mcite(b, "astm-e1877")
            if res["lifetime"].get("method") == "toop":
                keys["toop"] = mcite(b, "toop1971")
    if inc.get("figures", True):
        b.add_figure(C.fig_kinetics(res, lang), "kinetik", T[lang]["fig_kin"].format(k=len(runs)).replace("ₐ", "$_a$").replace("α", r"$\alpha$"),
                     width="0.95", dpi=150, cites=[keys[x] for x in ("friedman", "ozawa", "kas", "vyazovkin1997") if x in keys] or None,
                     steps=["kinetik"])
    meths = ["friedman", "ofw", "kas", "starink", "vyazovkin"]
    if inc.get("tables", True):
        al = [x for x in res["iso"]["alphas"] if abs(round(x * 10) - x * 10) < 1e-6]
        rows = []
        for x in al:
            row = [num(x, 1, lang)]
            for m in meths:
                r = next((y for y in res["iso"]["methods"][m] if abs(y["alpha"] - x) < 1e-6), None)
                row.append("--" if r is None else num(r["E"], 1, lang) + (f" ± {num(r['ci'], 1, lang)}" if r.get("ci") else ""))
            rows.append(row)
        head = [r"$\alpha$", "Friedman", "OFW", "KAS", "Starink", "Vyazovkin"]
        b.add_table("kinetik", booktabs(head, rows, align="rrrrrr", small=True, escape_header=False), T[lang]["tab_kin"].replace("ₐ", "$_a$"), steps=["kinetik"])
    vals = []
    for m in meths:
        s = res["iso"]["summary"].get(m)
        if s:
            vals.append((f"ea-{m}", f"Eₐ {C.METHOD_LABEL[m]}".replace("ₐ", "a"), num(s["mean"], 1, lang) + r"\,kJ/mol", f"{s['mean']:.1f} kJ/mol"))
    kis = res.get("kissinger") or {}
    if kis.get("E"):
        vals.append(("ea-kissinger", "Ea Kissinger", num(kis["E"], 1, lang) + r"\,kJ/mol", f"{kis['E']:.1f} kJ/mol"))
    if inc.get("values", True) and vals:
        b.add_values(vals, needs={v[0]: ["kinetik"] for v in vals})
    st0 = next((a.state for a, _, _ in analyses if UC.active(a.state)), None)
    kin_unc = ""
    if st0 is not None:                                # Vertrauensbereiche im Stil der Messunsicherheit (nicht doppelt)
        ku = UC.kinetics(res, st0, lang)
        uo = UC.report(b, None, lang, extra=ku, table="unsicherheit-kinetik") if ku else None
        if uo:
            kin_unc = " " + UC.methods_text({"method": UC.method(st0), "keys": []}, uo,
                                            lambda ks: cite(ks) if ks else "", lang, kin=True)
    c = lambda *ks: r"~\cite{" + ",".join(keys[x] for x in ks if x in keys) + "}" if keys else ""  # noqa: E731
    s = res["iso"]["summary"]
    betas = ", ".join(num(x, 1, lang) for x in res["iso"]["betas"])
    doyle = res["iso"].get("ofw") == "doyle"
    lt = res.get("lifetime")
    if de:
        t = (f"Die Kinetik der Stufe zwischen {num(req['T_lo'], 0, lang)} und {num(req['T_hi'], 0, lang)}~°C wurde aus {len(runs)} Läufen "
             f"mit {betas}~K/min nach den Empfehlungen des ICTAC{c('ictac2011', 'ictac2014')} bestimmt: isokonversional nach Friedman{c('friedman')}, "
             f"Ozawa-Flynn-Wall{c('ozawa', 'flynnwall', 'astm-e1641')}, Kissinger-Akahira-Sunose{c('kas')}, Starink{c('starink')} und "
             f"Vyazovkin{c('vyazovkin1997', 'senumyang')}, dazu Kissinger{c('kissinger')} und Coats-Redfern{c('coatsredfern')}.")
        if doyle:
            t += (" Für OFW wurde der konstante Faktor 1,052 der Doyle-Näherung verwendet (nicht iteriert); E$_a$ ist dadurch "
                  "für E$_a$/(RT) um 30 um etwa 1~\\% zu hoch.")
        else:
            t += (" Für OFW wurde E$_a$ ausgehend von der Doyle-Näherung (Faktor 1,052) wie in ASTM~E1641 iterativ mit dem Faktor "
                  "$b(E_a/RT)$ verfeinert; $b$ wurde aus der exakten Ableitung des Temperaturintegrals (Näherung nach Senum und Yang) "
                  "berechnet, nicht aus der Tabelle der Norm.")
        t += (" Das Vyazovkin-Verfahren ist in seiner Grundform umgesetzt (Temperaturintegral von 0 bis $T_\\alpha$ bei linearem Heizen). "
              "Vertrauensbereiche: 95~\\%, Student-$t$ mit $n-2$ Freiheitsgraden ($n$ = Zahl der Läufe).")
        if s.get("friedman"):
            t += f" Im Bereich $\\alpha$~=~0,1--0,9 beträgt E$_a$ nach Friedman im Mittel {num(s['friedman']['mean'], 1, lang)}~kJ/mol (Spanne {num(s['friedman']['min'], 0, lang)}--{num(s['friedman']['max'], 0, lang)})."
        if res.get("model"):
            t += f" Der Master-Plot passt am besten zum Modell {tx(res['model'])} ({tx(K.MODELS[res['model']][0])})."
        for w in res["iso"]["warnings"]:
            t += " " + tx(w)
        if lt and lt.get("method") == "toop":
            t += (f" Die Lebensdauer bis {num(100 * lt['alpha_f'], 0, lang)}~\\% Umsatz wurde ohne Reaktionsmodell über die "
                  f"Toop-Beziehung{c('toop')} berechnet, auf der ASTM~E1877{c('e1877')} beruht: "
                  "$t_f = (E_a/(R\\beta))\\,p(E_a/(RT_c))\\,\\exp(E_a/(RT))$, mit $T_c$ der Temperatur bei diesem Umsatz im dynamischen "
                  f"Lauf und E$_a$~=~{num(lt['E'], 1, lang)}~kJ/mol (OFW bei diesem Umsatz, iteriert). Die Umsetzung wurde nicht gegen "
                  "den Text der Norm geprüft. Sie ist eine Extrapolation weit unter den Messtemperaturen und nur als Anhaltswert zu verstehen.")
        elif lt:
            t += (f" Die Lebensdauer bis {num(100 * lt['alpha_f'], 0, lang)}~\\% Umsatz wurde durch Arrhenius-Extrapolation mit dem Modell "
                  f"{tx(lt.get('model') or '')} und $A$ aus den Friedman-Achsenabschnitten berechnet (in Anlehnung an ASTM~E1877{c('e1877')}, "
                  "nicht gegen den Text der Norm geprüft). Sie ist eine Extrapolation weit unter den Messtemperaturen und nur als "
                  "Anhaltswert zu verstehen.")
    else:
        t = (f"The kinetics of the step between {num(req['T_lo'], 0, lang)} and {num(req['T_hi'], 0, lang)}~°C were determined from {len(runs)} runs "
             f"at {betas}~K/min following the ICTAC recommendations{c('ictac2011', 'ictac2014')}: isoconversional methods of Friedman{c('friedman')}, "
             f"Ozawa-Flynn-Wall{c('ozawa', 'flynnwall', 'astm-e1641')}, Kissinger-Akahira-Sunose{c('kas')}, Starink{c('starink')} and "
             f"Vyazovkin{c('vyazovkin1997', 'senumyang')}, plus Kissinger{c('kissinger')} and Coats-Redfern{c('coatsredfern')}.")
        if doyle:
            t += (" For OFW the constant factor 1.052 of Doyle's approximation was used (not iterated); E$_a$ is therefore about "
                  "1~\\% too high for E$_a$/(RT) near 30.")
        else:
            t += (" For OFW, E$_a$ was refined iteratively as in ASTM~E1641, starting from Doyle's approximation (factor 1.052), with "
                  "the factor $b(E_a/RT)$; $b$ was calculated from the exact derivative of the temperature integral (Senum-Yang "
                  "approximation), not taken from the table of the standard.")
        t += (" The Vyazovkin method is implemented in its basic form (temperature integral from 0 to $T_\\alpha$ for linear heating). "
              "Confidence intervals: 95~\\%, Student $t$ with $n-2$ degrees of freedom ($n$ = number of runs).")
        if s.get("friedman"):
            t += f" For $\\alpha$~=~0.1--0.9 the mean Friedman E$_a$ is {num(s['friedman']['mean'], 1, lang)}~kJ/mol."
        for w in res["iso"]["warnings"]:
            t += " " + tx(w)
        if lt and lt.get("method") == "toop":
            t += (f" The lifetime to {num(100 * lt['alpha_f'], 0, lang)}~\\% conversion was calculated without a reaction model from the "
                  f"Toop relation{c('toop')}, on which ASTM~E1877{c('e1877')} is based: "
                  "$t_f = (E_a/(R\\beta))\\,p(E_a/(RT_c))\\,\\exp(E_a/(RT))$, with $T_c$ the temperature at this conversion in the "
                  f"dynamic run and E$_a$~=~{num(lt['E'], 1, lang)}~kJ/mol (OFW at this conversion, iterated). The implementation was "
                  "not checked against the text of the standard. It is an extrapolation far below the measured temperatures and "
                  "only an indication.")
        elif lt:
            t += (f" The lifetime to {num(100 * lt['alpha_f'], 0, lang)}~\\% conversion was calculated by Arrhenius extrapolation with "
                  f"model {tx(lt.get('model') or '')} and $A$ from the Friedman intercepts (following ASTM~E1877{c('e1877')}, not "
                  "checked against the text of the standard). It is an extrapolation far below the measured temperatures and only "
                  "an indication.")
    return t + kin_unc + "\n"


def build(items, request: dict, lang: str = "de", include: dict | None = None, title: str | None = None) -> dict:
    """items: [(rohdaten, dateiname, mapping, state)]."""
    inc = {k: True for k in ("figures", "tables", "values", "data", "citations", "text")}
    inc.update(include or {})
    L = T[lang]
    analyses = []
    for raw, fname, mapping, state in items:
        r = load_bytes(raw, fname, mapping or None)[int(state.get("_idx") or 0)]    # Lauf idx einer Datei mit mehreren Läufen
        if state.get("_label"):
            r.name = str(state["_label"])
        analyses.append((run(r, state, lang), fname, len(raw)))
    if not analyses:
        raise ValueError("Kein Lauf gewählt.")
    title = title or (L["title1"].format(n=analyses[0][0].name) if len(analyses) == 1 else L["titleN"])
    b = Bundle(module="tga", module_name=L["module"], title=title, lang=lang, slug=request.get("slug"))
    meth, res = [], []
    if len(analyses) == 1:
        a, fname, rl = analyses[0]
        cites, hits, mix, eq = _single(b, a, fname, rl, lang, inc)
        meth.append(_methods(a, cites, hits, mix, eq, lang))
        res.append(_results(a, hits, mix, lang, b.slug, ""))
        b.summary = f"{a.name}: {len(a.steps)} " + ("Stufen" if lang == "de" else "steps")
    else:
        if inc.get("figures", True):
            series = []
            for a, _, _ in analyses:
                d = a.st.get("dtg") or {}
                series.append({"name": a.name, "x": a.run.T, "m": a.run.pct(), "dtg": -d["dT"] if d.get("dT") is not None else np.zeros(len(a.run.m))})
            for i, se in enumerate(series, 1):
                se["part"] = f"lauf{i}"
            b.add_figure(C.fig_overlay(series, lang), "vergleich", L["fig_cmp"].format(n="").replace(": .", "{parts}."),
                         width="0.9", dpi=150, steps=[], parts_lead=":",
                         parts=[{"id": f"lauf{i}", "label": a.name, "caption": tx(a.name)}
                                for i, (a, _, _) in enumerate(analyses, 1)])
        rows, raw_vals = [], []
        for i, (a, fname, rl) in enumerate(analyses, 1):
            cites, hits, mix, eq = _single(b, a, fname, rl, lang, inc, prefix=f"p{i}")
            t5 = (a.st.get("loss_T") or {}).get("5") or {}
            s1 = a.steps[0] if a.steps else {}
            vals_i = [t5.get("T"), s1.get("loss"), s1.get("T_peak"), (a.st.get("residue") or {}).get("end")]
            raw_vals.append(vals_i)                       # volle Genauigkeit für Mittelwert und s
            rows.append([tx(a.name)] + [_n(v, nd, lang) for v, nd in zip(vals_i, (1, 2, 1, 2))])
            if i == 1:
                meth.append(_methods(a, cites, hits, mix, eq, lang))
            elif _ds_sentence(a, lang):                  # DP-13: Herkunft weiterer Läufe aus Datensätzen
                meth.append(_ds_sentence(a, lang, named=True) + "\n")
            res.append(_results(a, hits, mix, lang, b.slug, f"p{i}"))
        if inc.get("tables", True):
            def ms(col):
                v = [float(r[col]) for r in raw_vals if r[col] is not None and np.isfinite(r[col])]
                return f"{num(np.mean(v), 2, lang)} ± {num(np.std(v, ddof=1), 2, lang)}" if len(v) > 1 else "--"
            rows.append([L["mean"]] + [ms(j) for j in range(4)])
            b.add_table("vergleich", booktabs(L["h_cmp"], rows, align="lrrrr", small=True, escape_header=False), L["tab_cmp"],
                        steps=["dtg", "stufen"])
        if request.get("unc_replicates"):              # Wiederholungen derselben Probe: Mittelwert ± U (Typ A + B)
            st0 = (items[0][3] if items else {}) or {}
            rep = UC.replicates([a for a, _, _ in analyses], st0, lang)
            at = b.added_mark()
            uo = UC.report(b, None, lang, extra=rep["results"], table="unsicherheit-wiederholungen") if rep["results"] else None
            b.needs_since(at, ["unsicherheit"])
            if uo:
                meth.append(step_tag("unsicherheit") + UC.methods_text({"method": rep["method"], "keys": sorted(UC.specs(st0))}, uo,
                                                                       lambda ks: cite(ks) if ks else "", lang, rep=len(analyses)) + "\n")
        b.summary = ", ".join(a.name for a, _, _ in analyses)
    kin = request.get("kinetics")
    if kin and len(analyses) >= 3:
        kt = _kinetics(b, analyses, kin, lang, inc)
        if kt:
            meth.append(step_tag("kinetik") + kt)
    if inc.get("text", True):
        b.add_methods(meth, L["methods"], sep="\n", brief=b.brief_from(meth[0], evaluated=True) if meth else "")
        r = "\n".join(x for x in res if x)
        if r:
            b.add_text("ergebnisse", r, L["results"], steps=_RESULT_STEPS + (["kinetik"] if kin else []))
    files = {fname: raw for (raw, fname, _, _) in items}
    b.set_source(request, files)
    return b.to_dict()
