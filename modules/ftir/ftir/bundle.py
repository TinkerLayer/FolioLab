"""Ergebnisse für den Berichtseditor (Folio Lab, Format folio-lab-bundle/1)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np

try:
    from labbundle import Bundle, booktabs, cite, cite_keys, num, slugify, tex_escape
except ImportError:  # Modul ausserhalb von Folio Lab gestartet
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "sdk" / "python"))
    from labbundle import Bundle, booktabs, cite, cite_keys, num, slugify, tex_escape
import labcite  # noqa: E402

from . import charts as C
from . import peaks as PK
from . import quality as QA
from .analysis import Analysis, arr, run
from .library import GRID, MODEL_ID
from .readers import load_bytes, ylabel
from .search import ALGOS

CM = r"cm$^{-1}$"
_SUP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻", "0123456789+-")
_SUB = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
_EXTRA = {"≡": r"$\equiv$", "ν": r"$\nu$", "λ": r"$\lambda$"}


def tx(s) -> str:
    """Text -> LaTeX, auch mit chemischen Hoch-/Tiefzahlen (CO₃²⁻, cm⁻¹) und ≡."""
    out = []
    for part in re.split(r"([⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻]+|[₀₁₂₃₄₅₆₇₈₉]+|[≡νλ])", str(s)):
        if not part:
            continue
        if part[0] in "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻":
            out.append("$^{" + part.translate(_SUP) + "}$")
        elif part[0] in "₀₁₂₃₄₅₆₇₈₉":
            out.append("$_{" + part.translate(_SUB) + "}$")
        elif part in _EXTRA:
            out.append(_EXTRA[part])
        else:
            out.append(tex_escape(part))
    return "".join(out)


T = {
    "de": {
        "module": "FTIR", "title1": "FTIR {n}", "titleN": "FTIR-Vergleich",
        "fig_spec": "FTIR-Spektrum von {n}{pk}.", "fig_spec_pk": " mit den gefundenen Banden (Wellenzahlen in " + CM + ")",
        "fig_cmp": "FTIR-Spektren im Vergleich: {n}.",
        "fig_search": "Bibliothekssuche für {n}: Probe (oben) und die besten Treffer ({a}).",
        "fig_mix": "Mischungsanalyse für {n}: Probe, angepasste Mischung und Anteile der Komponenten; unten der Rest.",
        "tab_peaks": "Banden von {n} mit möglichen Zuordnungen.",
        "tab_groups": "Funktionelle Gruppen in {n} (Hinweise aus der Korrelationstabelle).",
        "tab_hits": "Bibliothekssuche für {n} ({a}); HQI 100 = deckungsgleich.",
        "tab_mix": "Mischungsanalyse für {n} (HQI {h}); Anteile an der Absorbanz, keine Massenanteile.",
        "tab_bands": "Bandenflächen von {n}.", "tab_cmp": "FTIR-Proben im Vergleich.",
        "h_peaks": ["Nr.", r"$\tilde\nu$ [" + CM + "]", "{y}", "Int.", "FWHM [" + CM + "]", "Zuordnung"],
        "h_groups": ["Stoffklasse", "Bewertung", "Banden"],
        "h_hits": ["Rang", "Referenz", "Bibliothek", "HQI"],
        "h_mix": ["Komponente", "Bibliothek", r"Anteil [\%]"],
        "h_bands": ["Bande", "Bereich [" + CM + "]", "Fläche", "Höhe", "Lage [" + CM + "]"],
        "h_cmp": ["Probe", "Bester Treffer", "HQI", "Stärkste Bande [" + CM + "]", "Banden"],
        "verdict": {"wahrscheinlich": "wahrscheinlich", "möglich": "möglich", "unwahrscheinlich": "unwahrscheinlich"},
        "methods": "Methodik", "results": "Ergebnisse", "data_spec": "Spektrum {n} ({y}).", "data_peaks": "Banden von {n}.",
        "strongest": "stärkste Bande", "npeaks": "Anzahl Banden", "hit": "Bester Treffer", "hqi": "HQI bester Treffer",
        "mixhqi": "HQI Mischung", "ratio": "Verhältnis",
    },
    "en": {
        "module": "FTIR", "title1": "FTIR {n}", "titleN": "FTIR comparison",
        "fig_spec": "FTIR spectrum of {n}{pk}.", "fig_spec_pk": " with the detected bands (wavenumbers in " + CM + ")",
        "fig_cmp": "FTIR spectra compared: {n}.",
        "fig_search": "Library search for {n}: sample (top) and best hits ({a}).",
        "fig_mix": "Mixture analysis for {n}: sample, fitted mixture and component contributions; residual below.",
        "tab_peaks": "Bands of {n} with possible assignments.",
        "tab_groups": "Functional groups in {n} (indications from the correlation table).",
        "tab_hits": "Library search for {n} ({a}); HQI 100 = identical.",
        "tab_mix": "Mixture analysis for {n} (HQI {h}); contributions to absorbance, not mass fractions.",
        "tab_bands": "Band areas of {n}.", "tab_cmp": "FTIR samples compared.",
        "h_peaks": ["No.", r"$\tilde\nu$ [" + CM + "]", "{y}", "Int.", "FWHM [" + CM + "]", "Assignment"],
        "h_groups": ["Compound class", "Assessment", "Bands"],
        "h_hits": ["Rank", "Reference", "Library", "HQI"],
        "h_mix": ["Component", "Library", r"Contribution [\%]"],
        "h_bands": ["Band", "Range [" + CM + "]", "Area", "Height", "Position [" + CM + "]"],
        "h_cmp": ["Sample", "Best hit", "HQI", "Strongest band [" + CM + "]", "Bands"],
        "verdict": {"wahrscheinlich": "likely", "möglich": "possible", "unwahrscheinlich": "unlikely"},
        "methods": "Methods", "results": "Results", "data_spec": "Spectrum {n} ({y}).", "data_peaks": "Bands of {n}.",
        "strongest": "strongest band", "npeaks": "Number of bands", "hit": "Best hit", "hqi": "HQI of best hit",
        "mixhqi": "HQI of mixture", "ratio": "Ratio",
    },
}

REFS = {
    "socrates2001": ("book", dict(author="Socrates, George", title="Infrared and Raman Characteristic Group Frequencies: Tables and Charts",
                                  edition="3", publisher="Wiley", address="Chichester", year="2001")),
    "astm-e1252": ("misc", dict(title="ASTM E1252-98(2021): Standard Practice for General Techniques for Obtaining Infrared Spectra for Qualitative Analysis",
                                howpublished="ASTM International", year="2021")),
    "savitzky1964": ("article", dict(author="Savitzky, Abraham and Golay, Marcel J. E.",
                                     title="Smoothing and Differentiation of Data by Simplified Least Squares Procedures",
                                     journal="Analytical Chemistry", volume="36", number="8", pages="1627--1639", year="1964")),
    "eilers2005": ("techreport", dict(author="Eilers, Paul H. C. and Boelens, Hans F. M.",
                                      title="Baseline Correction with Asymmetric Least Squares Smoothing",
                                      institution="Leiden University Medical Centre", year="2005")),
    "lawson1974": ("book", dict(author="Lawson, Charles L. and Hanson, Richard J.", title="Solving Least Squares Problems",
                                publisher="Prentice-Hall", address="Englewood Cliffs", year="1974")),
    "openspecy2025": ("article", dict(author="Cowger, Win and others", title="Open Specy 1.0: Automated (Hyper)spectroscopy "
                                      "for Microplastics", journal="Analytical Chemistry", year="2025",
                                      doi="10.1021/acs.analchem.5c00962")),
}


def _cite(b: Bundle, key: str):
    et, f = REFS[key]
    b.add_citation(key, et, **{k: (v if k in ("pages",) else tex_escape(v)) for k, v in f.items()})
    return key


MODEL_KEY = "folio-ftir-modell"


def _model_cite(b: Bundle, lang: str) -> str:
    de = lang == "de"
    b.add_citation(MODEL_KEY, "misc",
                   title=tex_escape("Modellbibliothek FTIR (Folio Lab): aus Literatur-Bandenlagen berechnete Referenzspektren"
                                    if de else "FTIR model library (Folio Lab): reference spectra calculated from literature "
                                    "band positions"),
                   howpublished=tex_escape("Folio Lab, Modul FTIR" if de else "Folio Lab, FTIR module"),
                   note=tex_escape("Keine gemessenen Spektren; Lage, relative Stärke und Halbwertsbreite der Hauptbanden nach "
                                   "gängigen Tabellenwerken (u. a. Socrates 2001)" if de else
                                   "Not measured spectra; position, relative intensity and width of the main bands from "
                                   "standard tables (e.g. Socrates 2001)"))
    return MODEL_KEY


def _structured(rec):
    """Gültige strukturierte Quelle oder None (ältere oder unvollständige Angaben fallen auf den Freitext zurück)."""
    return rec if isinstance(rec, dict) and labcite.is_record(rec) and not labcite.errors(rec) else None


def ref_keys(b: Bundle, refs, lang: str) -> list[str]:
    """Literaturangaben für Referenzspektren (Treffer, Mischungskomponenten, geöffnete Referenzen).

    Open Specy: Sammlung (Cowger et al. 2025) und das ursprüngliche Labor/die ursprüngliche Datenbank des Spektrums.
    Modellbibliothek: eigener Eintrag mit dem Hinweis, dass es keine Messungen sind. Eigene Bibliotheken: die Bibliothek
    und, falls angegeben, die Quelle des Eintrags."""
    de = lang == "de"
    keys = []
    for h in refs or []:
        lib = h.get("lib") or ""
        src = (h.get("source") or "").strip()
        if str(lib).startswith("openspecy"):
            keys.append(_cite(b, "openspecy2025"))
            if ":" in src:
                short, full = src.split(":", 1)
                key = "ref-" + re.sub(r"[^a-z0-9]+", "-", short.lower()).strip("-")
                b.add_citation(key, "misc", title=tex_escape(full.strip()), note=tex_escape(short.strip()))
                keys.append(key)
        elif lib == MODEL_ID:
            keys.append(_model_cite(b, lang))
        elif lib:
            name = h.get("lib_name") or lib
            key = "lib-" + slugify(name, 30)
            lc, ec = _structured(h.get("lib_cite")), _structured(h.get("cite"))
            if lc:   # Sammlung mit eigener Quelle (z. B. veröffentlichter Datensatz)
                labcite.to_bib(b, key, lc)
            else:
                b.add_citation(key, "misc", title=tex_escape((f"FTIR-Referenzbibliothek „{name}“" if de else f"FTIR reference library “{name}”")),
                               howpublished=tex_escape("eigene Bibliothek in Folio Lab" if de else "own library in Folio Lab"))
            keys.append(key)
            if ec:   # Quelle des einzelnen Spektrums: richtiger Eintragstyp mit Autoren, Jahr, DOI
                keys.append(labcite.to_bib(b, labcite.key_for("src", ec, h.get("name") or ""), ec))
            elif src:
                skey = "src-" + slugify(src, 40)
                b.add_citation(skey, "misc", title=tex_escape(src),
                               note=tex_escape((f"Referenz in der Bibliothek „{name}“" if de else f"reference in the library “{name}”")))
                keys.append(skey)
    return cite_keys(keys)


def _tags(a: Analysis, lang: str) -> list[str]:
    out = []
    for h in a.orig.meta.get("refs") or []:
        t = C.ref_tag(h, lang)
        if t not in out:
            out.append(t)
    return out


def _label(a: Analysis, lang: str) -> str:
    """Name für Legenden; Referenzspektren tragen ihre Herkunft („Calcit · Open Specy/RRUFF“)."""
    tags = _tags(a, lang)
    return a.name + (" · " + ", ".join(tags) if tags else "")


def _ref_libs(a: Analysis, lang: str) -> str:
    return ", ".join(tx(t) for t in _tags(a, lang))


def _is_model(a: Analysis) -> bool:
    refs = a.orig.meta.get("refs") or []
    return bool(refs) and all(h.get("lib") == MODEL_ID for h in refs)


def _n(v, nd, lang):
    return num(v, nd, lang) if v is not None and np.isfinite(v) else "--"


def _ynd(sp):
    return 1 if sp.yunit in ("T", "R") else 3


def _uses(a: Analysis, op, **kw):
    for st in a.state.get("pipeline") or []:
        if st.get("op") == op and all(st.get(k, None) == v for k, v in kw.items()):
            return True
    return False


def _data_cite(b: Bundle, a: Analysis, fname: str, raw_len: int, lang: str, key: str):
    sp = a.orig
    fmt = sp.meta.get("format", "")
    note = f"{fmt}, {sp.x[-1]:.0f}–{sp.x[0]:.0f} cm-1, {len(sp.x)} Punkte" if lang == "de" else \
        f"{fmt}, {sp.x[-1]:.0f}–{sp.x[0]:.0f} cm-1, {len(sp.x)} points"
    d = sp.meta.get("dataset") or {}
    if d.get("share"):                                  # DP-13
        note += f", {'Datensatz' if lang == 'de' else 'dataset'} {d['share']} v{d.get('version')}"
    b.add_citation(key, "misc", title=tex_escape(a.name), howpublished=tex_escape(fname),
                   note=tex_escape(note + f", {raw_len / 1024:.0f} KiB"))
    return key


def _ds_sentence(a: Analysis, lang: str, named: bool = False) -> str:
    """DP-13: Herkunft eines Spektrums aus einem Datensatz der Datenaufbereitung (ID, Version, Spalten)."""
    d = (a.orig.meta or {}).get("dataset") or {}
    if not d.get("share"):
        return ""
    n = int(d.get("excluded") or 0)
    col = ((d.get("columns") or {}).get("y") or {}).get("name")
    if lang == "de":
        s = (f"Das Spektrum{' ' + a.name if named else ''} stammt aus dem Datensatz „{d.get('title') or d['share']}“ "
             f"(ID {d['share']}, Version {d.get('version')}{', Spalte ' + col if col else ''}) der Datenaufbereitung")
        if d.get("x_note"):
            s += "; die Wellenzahlen wurden aus Wellenlängen berechnet (1/λ)"
        s += f"; {n} als ausgeschlossen markierte Zeile{'n' if n != 1 else ''} blieb{'en' if n != 1 else ''} unberücksichtigt." if n else "."
    else:
        s = (f"The spectrum{' ' + a.name if named else ''} comes from dataset “{d.get('title') or d['share']}” "
             f"(ID {d['share']}, version {d.get('version')}{', column ' + col if col else ''}) of the data preparation module")
        if d.get("x_note"):
            s += "; wavenumbers were calculated from wavelengths (1/λ)"
        s += f"; {n} row{'s' if n != 1 else ''} marked as excluded {'were' if n != 1 else 'was'} left out." if n else "."
    return tx(s)


def _regions(a: Analysis):
    return [(r["lo"], r["hi"], r["name"]) for r in a.bands if r.get("area") is not None]


def _with_lib(h: dict) -> dict:
    """Ältere gespeicherte Treffer ohne Bibliothekskennung: Modellbibliothek am Namen erkennen."""
    if not h.get("lib") and "Modell" in (h.get("lib_name") or ""):
        h["lib"] = MODEL_ID
    return h


def _search_parts(a: Analysis):
    s = a.state.get("search") or {}
    hits = [_with_lib(h) for h in s.get("hits") or []]
    q = arr(s.get("query"))
    for h in hits:
        if h.get("y") is not None:
            h["y"] = arr(h["y"])
    return s, hits, q


def _mix_parts(a: Analysis):
    m = a.state.get("mixture") or {}
    if not m.get("components"):
        return None
    out = dict(m)
    out["fit"] = arr(m.get("fit"))
    out["residual"] = arr(m.get("residual"))
    out["query"] = arr(m.get("query"))
    out["components"] = [_with_lib(dict(c, y=arr(c.get("y")))) for c in m["components"]]
    return out


def _single(b: Bundle, a: Analysis, fname: str, raw_len: int, lang: str, inc: dict, prefix: str = ""):
    L = T[lang]
    n = tx(a.name)
    sp = a.sp
    yl = ylabel(sp.yunit, lang)
    cites = {}
    if inc.get("citations", True):
        cites["data"] = _data_cite(b, a, fname, raw_len, lang, f"data-{b.slug}{('-' + prefix) if prefix else ''}")
        cites["tab"] = _cite(b, "socrates2001")
        cites["astm"] = _cite(b, "astm-e1252")
        if _uses(a, "smooth", method="sg") or _uses(a, "deriv") or _uses(a, "smooth"):
            cites["sg"] = _cite(b, "savitzky1964")
        if _uses(a, "baseline", method="als"):
            cites["als"] = _cite(b, "eilers2005")
    s, hits, q = _search_parts(a)
    mix = _mix_parts(a)
    if mix and inc.get("citations", True):
        cites["nnls"] = _cite(b, "lawson1974")
    self_refs = a.orig.meta.get("refs") or []      # das Spektrum ist (oder enthält) eine Bibliotheksreferenz
    comps = list((mix or {}).get("components") or [])
    drawn = [h for h in hits if h.get("y") is not None][:3]     # wie C.fig_search
    rk = {}                                                      # Literaturangaben je Bestandteil
    if inc.get("citations", True):
        rk = {"self": ref_keys(b, self_refs, lang), "drawn": ref_keys(b, drawn, lang),
              "hits": ref_keys(b, hits[:10], lang), "mix": ref_keys(b, comps, lang)}
        used = list(hits[:10]) + comps + list(self_refs)
        os_keys = [k for h in used if str(h.get("lib")).startswith("openspecy") for k in ref_keys(b, [h], lang)]
        if os_keys:
            cites["openspecy"] = "openspecy2025"
            origins = [k for k in cite_keys(os_keys) if k != "openspecy2025"]
            if origins:
                cites["origins"] = ",".join(origins)
        if any(h.get("lib") == MODEL_ID for h in used):
            cites["model"] = MODEL_KEY
        own = cite_keys([ref_keys(b, [h], lang) for h in used if h.get("lib") not in (MODEL_ID, None, "") and not str(h.get("lib")).startswith("openspecy")])
        if own:
            cites["own"] = ",".join(own)
        if rk["self"]:
            cites["self"] = ",".join(rk["self"])
    algo = ALGOS.get(s.get("algo", "corr"), ALGOS["corr"])[0 if lang == "de" else 1]
    pid = prefix
    if inc.get("figures", True):
        fig = C.fig_spectra([{"name": _label(a, lang), "x": sp.x, "y": sp.y}], sp.yunit, lang, peaks=a.peaks, regions=_regions(a))
        b.add_figure(fig, f"spektrum{pid}", L["fig_spec"].format(n=n, pk=L["fig_spec_pk"] if a.peaks else ""), width="0.9", dpi=150,
                     cites=rk.get("self"))
        if hits and q is not None and drawn:
            b.add_figure(C.fig_search(GRID, q, hits, lang, a.name), f"suche{pid}", L["fig_search"].format(n=n, a=tex_escape(algo)),
                         width="0.9", dpi=150, cites=rk.get("drawn"))
        if mix and mix["query"] is not None:
            b.add_figure(C.fig_mixture(GRID, mix["query"], mix, lang, a.name), f"mischung{pid}", L["fig_mix"].format(n=n),
                         width="0.9", dpi=150, cites=rk.get("mix"))
    if inc.get("tables", True):
        if a.peaks:
            head = [h.replace("{y}", tx(yl)) for h in L["h_peaks"]]
            rows = []
            for i, p in enumerate(a.peaks, 1):
                rows.append([str(i), num(p["x"], 0, lang), num(p["y"], _ynd(sp), lang), p["strength"] + (" br" if p.get("shape") else ""),
                             _n(p["fwhm"], 0, lang), tx((p.get("assign") or ["–"])[0])])
            b.add_table(f"banden{pid}" if False else f"peaks{pid}", booktabs(head, rows, align="rrrlrl", small=True, escape_header=False),
                        L["tab_peaks"].format(n=n))
        if a.groups and a.groups.get("classes"):
            rows = [[tx(c["name"]), L["verdict"][c["verdict"]], f"{c['found']}/{c['needed']}"]
                    for c in a.groups["classes"] if c["verdict"] != "unwahrscheinlich"]
            if rows:
                notes = " ".join(tx(x["text"]) for x in a.groups.get("absent", []))
                b.add_table(f"gruppen{pid}", booktabs(L["h_groups"], rows, align="llr", small=True), L["tab_groups"].format(n=n), notes=notes)
        cell = (lambda h: tx(C.ref_tag(h, lang)) + (cite(ref_keys(b, [h], lang)) if rk else ""))  # noqa: E731
        if hits:
            rows = [[str(h.get("rank", i + 1)), tx(h["name"]), cell(h), num(h["hqi"], 1, lang)]
                    for i, h in enumerate(hits[:10])]
            b.add_table(f"treffer{pid}", booktabs(L["h_hits"], rows, align="rllr", small=True), L["tab_hits"].format(n=n, a=tex_escape(algo)),
                        cites=rk.get("hits"))
        if mix:
            rows = [[tx(c["name"]), cell(c), num(100 * c["frac"], 0, lang)] for c in mix["components"]]
            b.add_table(f"mischung{pid}", booktabs(L["h_mix"], rows, align="llr", small=True),
                        L["tab_mix"].format(n=n, h=num(mix["hqi"], 1, lang)), cites=rk.get("mix"))
        if a.bands:
            rows = [[tx(r["name"]), f"{num(r['hi'], 0, lang)}--{num(r['lo'], 0, lang)}", _n(r["area"], 3, lang),
                     _n(r["height"], 3, lang), _n(r["pos"], 0, lang)] for r in a.bands]
            notes = "; ".join(f"{tx(r['name'])}: {_n(r['value'], 3, lang)}" for r in a.ratios)
            b.add_table(f"flaechen{pid}", booktabs(L["h_bands"], rows, align="lrrrr", small=True), L["tab_bands"].format(n=n), notes=notes)
    if inc.get("values", True):
        vals = []
        k = (prefix + "-") if prefix else ""
        if a.peaks:
            vals.append((f"{k}npeaks", L["npeaks"], str(len(a.peaks)), str(len(a.peaks))))
            top = max(a.peaks, key=lambda p: p["prom"])
            vals.append((f"{k}peak1", L["strongest"], num(top["x"], 0, lang, ""), f"{top['x']:.0f} cm-1"))
        if hits:
            vals.append((f"{k}hit1", L["hit"], tx(hits[0]["name"]), hits[0]["name"]))
            vals.append((f"{k}hqi1", L["hqi"], num(hits[0]["hqi"], 1, lang), f"{hits[0]['hqi']:.1f}"))
        if mix:
            vals.append((f"{k}mixhqi", L["mixhqi"], num(mix["hqi"], 1, lang), f"{mix['hqi']:.1f}"))
        for i, r in enumerate(a.bands, 1):
            if r["area"] is not None:
                vals.append((f"{k}band{i}", tex_escape(r["name"]), num(r["area"], 3, lang), f"{r['area']:.4g}"))
        for i, r in enumerate(a.ratios, 1):
            if r["value"] is not None:
                vals.append((f"{k}ratio{i}", f"{L['ratio']} {tex_escape(r['name'])}", num(r["value"], 3, lang), f"{r['value']:.4g}"))
        if vals:
            b.add_values(vals)
        if a.equations:     # eigene Gleichungen: Werte, Tabelle, abgesetzte Formeln (mit Quelle) für den Methodentext
            from labcalc import formulas as Fm
            rep = Fm.to_report(b, a.equations, lang, prefix=(prefix + "-") if prefix else "", cite_prefix="eq")
            a.eq_latex = rep.get("latex", "")
    if inc.get("data", True):
        step = max(1, len(sp.x) // 4000)
        yname = {"A": "A", "T": "T_pct", "R": "R_pct", "KM": "KM"}.get(sp.yunit, "y")
        b.add_data_csv(f"spektrum{pid}", ["wn_cm1", yname], [[float(x), float(y)] for x, y in zip(sp.x[::step], sp.y[::step])],
                       L["data_spec"].format(n=n, y=tx(yl)), labels={"wn_cm1": r"$\tilde\nu$ [" + CM + "]", yname: tx(yl)},
                       plot={"x": "wn_cm1", "y": yname, "xdir": "reverse"})
        if a.peaks:
            b.add_data_csv(f"peaks{pid}", ["wn_cm1", yname, "fwhm_cm1"], [[p["x"], p["y"], p["fwhm"]] for p in a.peaks],
                           L["data_peaks"].format(n=n), labels={"wn_cm1": r"$\tilde\nu$ [" + CM + "]", yname: tx(yl)},
                           plot={"x": "wn_cm1", "y": yname, "style": "marks"})
    return cites, s, hits, mix, algo


def _methods(a: Analysis, cites: dict, s: dict, hits, mix, algo: str, lang: str) -> str:
    c = lambda k: (r"~\cite{" + cites[k] + "}") if k in cites else ""  # noqa: E731
    sp, o = a.sp, a.orig
    de = lang == "de"
    steps = "; ".join(tx(x) for x in a.proc.steps)
    meta = o.meta
    src = [tx(v) for v in (meta.get("instrument"), meta.get("sampling")) if v]
    try:
        res = float(meta.get("resolution"))
        src.append(("Auflösung " if de else "resolution ") + num(res, 0 if res == int(res) else 1, lang) + "~" + CM)
    except (TypeError, ValueError):
        pass
    src = ", ".join(src)
    q = QA.assess(sp.x, sp.y, sp.yunit)
    pk_snr = float(((a.state.get("peaks") or {}).get("params") or {}).get("snr", PK.DEFAULT["snr"]) or 0)
    rngs = ", ".join(f"{num(hi, 0, lang)}--{num(lo, 0, lang)}" for hi, lo in q["noisy"])
    if de:
        noise_t = ""
        if q["snr"] is not None:
            noise_t = (f" Das Signal-Rausch-Verhältnis (stärkste Bande zu Rauschen, Rauschen aus dem Rest einer "
                       f"Savitzky-Golay-Glättung) beträgt etwa {num(q['snr'], 0, lang)}.")
        if rngs:
            noise_t += (f" Der verrauschte Bereich {rngs}~" + CM + " (bei Diamant-ATR absorbiert der Kristall dort selbst) "
                        "blieb bei Bandensuche, Gruppenbewertung und Bibliothekssuche unberücksichtigt.")
    else:
        noise_t = ""
        if q["snr"] is not None:
            noise_t = (f" The signal-to-noise ratio (strongest band to noise, noise from the residual of a "
                       f"Savitzky-Golay smooth) is about {num(q['snr'], 0, lang)}.")
        if rngs:
            noise_t += (f" The noisy region {rngs}~" + CM + " (where a diamond ATR crystal absorbs) was ignored for band "
                        "picking, functional-group rating and library search.")
    if de:
        t = (f"Das Spektrum {tx(a.name)}{c('data')} wurde im Bereich {num(o.x[-1], 0, lang)}--{num(o.x[0], 0, lang)}~" + CM +
             f" ausgewertet ({len(o.x)} Datenpunkte{', ' + src if src else ''})." + c("astm"))
        ds = _ds_sentence(a, lang)
        t += f" {ds}" if ds else ""
        if "self" in cites:
            t += (f" Es ist bzw. enthält ein Referenzspektrum aus {_ref_libs(a, lang)}{c('self')}"
                  + (", nicht gemessen, sondern aus Bandenlagen berechnet" if _is_model(a) else "") + ".")
        t += f" Bearbeitung: {steps}." if steps else " Das Spektrum wurde unbearbeitet ausgewertet."
        if "sg" in cites:
            t += f" Geglättet bzw. abgeleitet wurde nach Savitzky und Golay{c('sg')}."
        if "als" in cites:
            t += f" Die Basislinie wurde mit asymmetrischen kleinsten Quadraten bestimmt{c('als')}."
        if a.peaks:
            p = (a.state.get("peaks") or {}).get("params") or {}
            t += (f" Banden wurden als lokale Maxima mit einer Prominenz von mindestens {num(p.get('prominence', 2), 1, lang)}~\\% "
                  f"des Wertebereichs" + (f", mindestens dem {num(pk_snr, 0, lang)}-fachen Rauschen" if pk_snr else "") +
                  f" und einem Mindestabstand von {num(p.get('distance', 8), 0, lang)}~" + CM +
                  f" gesucht und anhand einer Korrelationstabelle der Gruppenfrequenzen zugeordnet{c('tab')}.")
        t += noise_t
        if hits:
            libs = ", ".join(sorted({tx(h.get('lib_name', '')) for h in hits}))
            t += (f" Die Bibliothekssuche ({tex_escape(algo)}) verglich das vorbehandelte Spektrum (Absorbanz, Basislinie, "
                  f"Maximum 1, Raster 2~" + CM + f") mit {libs}; die Trefferqualität HQI reicht von 0 bis 100.")
            if any(h.get("lib") == MODEL_ID for h in hits):
                t += (f" Die Modellbibliothek{c('model')} enthält aus Literatur-Bandenlagen berechnete, keine gemessenen "
                      "Referenzspektren; Treffer daraus sind als Hinweis zu verstehen.")
            if "openspecy" in cites:
                t += (f" Die gemessenen Referenzen stammen aus der Open-Specy-Sammlung{c('openspecy')}"
                      + (f" (ursprünglich{c('origins')})" if "origins" in cites else "") + ".")
            if "own" in cites:
                t += f" Eigene Referenzen:{c('own')}."
        if mix:
            t += (f" Für die Mischungsanalyse wurden Kombinationen von Referenzen mit nicht-negativen Gewichten an das "
                  f"Spektrum angepasst{c('nnls')}; die Anteile beziehen sich auf die Absorbanz, nicht auf die Masse.")
    else:
        t = (f"Spectrum {tx(a.name)}{c('data')} was evaluated between {num(o.x[-1], 0, lang)} and {num(o.x[0], 0, lang)}~" + CM +
             f" ({len(o.x)} data points{', ' + src if src else ''})." + c("astm"))
        ds = _ds_sentence(a, lang)
        t += f" {ds}" if ds else ""
        if "self" in cites:
            t += (f" It is or contains a reference spectrum from {_ref_libs(a, lang)}{c('self')}"
                  + (", calculated from band positions, not measured" if _is_model(a) else "") + ".")
        t += f" Processing: {steps}." if steps else " The spectrum was evaluated without processing."
        if "sg" in cites:
            t += f" Smoothing/derivatives followed Savitzky and Golay{c('sg')}."
        if "als" in cites:
            t += f" The baseline was estimated by asymmetric least squares{c('als')}."
        if a.peaks:
            p = (a.state.get("peaks") or {}).get("params") or {}
            t += (f" Bands were picked as local maxima with a prominence of at least {num(p.get('prominence', 2), 1, lang)}~\\% "
                  f"of the data range" + (f", at least {num(pk_snr, 0, lang)} times the noise" if pk_snr else "") +
                  f" and a minimum distance of {num(p.get('distance', 8), 0, lang)}~" + CM +
                  f", and assigned using a correlation table of group frequencies{c('tab')}.")
        t += noise_t
        if hits:
            libs = ", ".join(sorted({tx(h.get('lib_name', '')) for h in hits}))
            t += (f" The library search ({tex_escape(algo)}) compared the pre-processed spectrum (absorbance, baseline, "
                  f"maximum 1, 2~" + CM + f" grid) with {libs}; the hit quality index HQI ranges from 0 to 100.")
            if any(h.get("lib") == MODEL_ID for h in hits):
                t += (f" The model library{c('model')} contains references calculated from literature band positions, not "
                      "measured spectra; its hits are indications.")
            if "openspecy" in cites:
                t += (f" Measured references are from the Open Specy collection{c('openspecy')}"
                      + (f" (originally{c('origins')})" if "origins" in cites else "") + ".")
            if "own" in cites:
                t += f" Own references:{c('own')}."
        if mix:
            t += (f" For the mixture analysis, combinations of references were fitted with non-negative weights{c('nnls')}; "
                  "contributions refer to absorbance, not mass.")
    return t + "\n"


def _results(a: Analysis, hits, mix, lang: str, slug: str, prefix: str) -> str:
    de = lang == "de"
    k = (prefix + "-") if prefix else ""
    parts = []
    if a.peaks:
        top = sorted(a.peaks, key=lambda p: -p["prom"])[:5]
        lst = ", ".join(num(p["x"], 0, lang) for p in sorted(top, key=lambda p: -p["x"]))
        parts.append((f"Das Spektrum von {tx(a.name)} zeigt \\labval{{{slug}}}{{{k}npeaks}} Banden; die stärksten liegen bei {lst}~" + CM + ".")
                     if de else (f"The spectrum of {tx(a.name)} shows \\labval{{{slug}}}{{{k}npeaks}} bands; the strongest are at {lst}~" + CM + "."))
    if a.groups and a.groups.get("classes"):
        likely = [tx(c["name"]) for c in a.groups["classes"] if c["verdict"] == "wahrscheinlich"][:5]
        if likely:
            parts.append(("Die Bandenlagen sprechen für: " if de else "The band positions indicate: ") + ", ".join(likely) + ".")
        for x in a.groups.get("absent", [])[:2]:
            parts.append(tx(x["text"]))
    if hits:
        parts.append((f"Bester Bibliothekstreffer ist \\labval{{{slug}}}{{{k}hit1}} mit einem HQI von \\labval{{{slug}}}{{{k}hqi1}}."
                       if de else f"The best library hit is \\labval{{{slug}}}{{{k}hit1}} with an HQI of \\labval{{{slug}}}{{{k}hqi1}}."))
        if len(hits) > 1 and hits[0]["hqi"] - hits[1]["hqi"] < 3:
            parts.append(f"Der zweite Treffer ({tx(hits[1]['name'])}, HQI {num(hits[1]['hqi'], 1, lang)}) liegt dicht dahinter."
                         if de else f"The second hit ({tx(hits[1]['name'])}, HQI {num(hits[1]['hqi'], 1, lang)}) is close.")
    if mix:
        comp = ", ".join(f"{tx(c['name'])} ({num(100 * c['frac'], 0, lang)}~\\%)" for c in mix["components"])
        parts.append((f"Als Mischung passt {comp} (HQI \\labval{{{slug}}}{{{k}mixhqi}})." if de else
                      f"As a mixture, {comp} fits (HQI \\labval{{{slug}}}{{{k}mixhqi}})."))
    return " ".join(parts) + "\n" if parts else ""


def build(items, request: dict, lang: str = "de", include: dict | None = None, title: str | None = None) -> dict:
    """items: [(rohdaten, dateiname, index_in_datei, state)]."""
    inc = {k: True for k in ("figures", "tables", "values", "data", "citations", "text")}
    inc.update(include or {})
    L = T[lang]
    analyses = []
    for raw, fname, idx, state in items:
        sps = load_bytes(raw, fname)
        if idx >= len(sps):
            raise ValueError(f"{fname}: Spektrum {idx + 1} fehlt")
        sp = sps[idx]
        if state.get("_label"):
            sp.name = str(state["_label"])
        a = run(sp, state, lang)
        analyses.append((a, fname, len(raw)))
    if not analyses:
        raise ValueError("Kein Spektrum gewählt.")
    if len(analyses) == 1:
        default_title = L["title1"].format(n=analyses[0][0].name)
    else:
        default_title = L["titleN"]
    b = Bundle(module="ftir", module_name=L["module"], title=title or default_title, lang=lang, slug=request.get("slug"))
    if len(analyses) == 1:
        a, fname, rl = analyses[0]
        cites, s, hits, mix, algo = _single(b, a, fname, rl, lang, inc)
        b.summary = f"{a.name}: {len(a.peaks)} " + ("Banden" if lang == "de" else "bands") + \
            (f", {hits[0]['name']} (HQI {hits[0]['hqi']:.1f})" if hits else "")
        if inc.get("text", True):
            eq = getattr(a, "eq_latex", "")
            b.add_text("methodik", _methods(a, cites, s, hits, mix, algo, lang) + ("\n" + eq if eq else ""), L["methods"])
            res = _results(a, hits, mix, lang, b.slug, "")
            if res:
                b.add_text("ergebnisse", res, L["results"])
    else:
        rows, meth, res = [], [], []
        if inc.get("figures", True):
            series = [{"name": _label(a, lang), "x": a.sp.x, "y": a.sp.y} for a, _, _ in analyses]
            units = {a.sp.yunit for a, _, _ in analyses}
            refs = [h for a, _, _ in analyses for h in a.orig.meta.get("refs") or []]
            b.add_figure(C.fig_spectra(series, units.pop() if len(units) == 1 else "au", lang, stacked=True), "vergleich",
                         L["fig_cmp"].format(n=", ".join(tx(a.name) for a, _, _ in analyses)), width="0.9", dpi=150,
                         cites=ref_keys(b, refs, lang) if inc.get("citations", True) else None)
        for i, (a, fname, rl) in enumerate(analyses, 1):
            cites, s, hits, mix, algo = _single(b, a, fname, rl, lang, inc, prefix=f"p{i}")
            top = max(a.peaks, key=lambda p: p["prom"]) if a.peaks else None
            rows.append([tx(a.name), tx(hits[0]["name"]) if hits else "--", num(hits[0]["hqi"], 1, lang) if hits else "--",
                         num(top["x"], 0, lang) if top else "--", str(len(a.peaks))])
            if i == 1:
                meth.append(_methods(a, cites, s, hits, mix, algo, lang))
            elif _ds_sentence(a, lang):                  # DP-13: Herkunft weiterer Spektren aus Datensätzen
                meth.append(_ds_sentence(a, lang, named=True) + "\n")
            res.append(_results(a, hits, mix, lang, b.slug, f"p{i}"))
            if getattr(a, "eq_latex", ""):
                res.append(f"{tx(a.name)}: " + a.eq_latex)
        if inc.get("tables", True):
            b.add_table("vergleich", booktabs(L["h_cmp"], rows, align="llrrr", small=True, escape_header=False), L["tab_cmp"])
        if inc.get("text", True):
            b.add_text("methodik", "".join(meth), L["methods"])
            r = "\n".join(x for x in res if x)
            if r:
                b.add_text("ergebnisse", r, L["results"])
        b.summary = ", ".join(a.name for a, _, _ in analyses)
    files = {}
    for (a, fname, _), (raw, _, _, _) in zip(analyses, items):
        files[fname] = raw
    b.set_source(request, files)
    return b.to_dict()
