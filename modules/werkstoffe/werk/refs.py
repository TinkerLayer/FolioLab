"""Quellen des Werkstoffe-Moduls.

Gemeinsame Quellen stehen in ``labcalc.sources.REFS``; hier nur die, die nur dieses Modul braucht. Beide werden über
``rec(key)`` gelesen und mit ``cite(b, keys)`` in einen Bericht geschrieben. Angaben, die in dieser Runde nicht am
Original geprüft wurden, tragen den Hinweis in ``note``.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SDK = Path(__file__).resolve().parents[3] / "sdk" / "python"
if _SDK.is_dir() and str(_SDK) not in sys.path:
    sys.path.insert(0, str(_SDK))

from labcalc import sources as S  # noqa: E402

NG = "Angaben nicht am Original geprüft"

REFS: dict[str, dict] = {
    # ------------------------------------------------------------------ Röntgenbeugung
    "scherrer1918": {
        "type": "article", "authors": "Scherrer, P.",
        "title": "Bestimmung der Grösse und der inneren Struktur von Kolloidteilchen mittels Röntgenstrahlen",
        "container": "Nachrichten von der Gesellschaft der Wissenschaften zu Göttingen, Mathematisch-Physikalische Klasse",
        "year": "1918", "pages": "98-100"},
    "langford1978": {
        "type": "article", "authors": "Langford, J. I.; Wilson, A. J. C.",
        "title": "Scherrer after sixty years: a survey and some new results in the determination of crystallite size",
        "container": "Journal of Applied Crystallography", "year": "1978", "volume": "11", "pages": "102-113",
        "doi": "10.1107/S0021889878012844"},
    "williamson1953": {
        "type": "article", "authors": "Williamson, G. K.; Hall, W. H.",
        "title": "X-ray line broadening from filed aluminium and wolfram", "container": "Acta Metallurgica",
        "year": "1953", "volume": "1", "pages": "22-31", "doi": "10.1016/0001-6160(53)90006-6"},
    "nelson1945": {
        "type": "article", "authors": "Nelson, J. B.; Riley, D. P.",
        "title": "An experimental investigation of extrapolation methods in the derivation of accurate unit-cell "
                 "dimensions of crystals",
        "container": "Proceedings of the Physical Society", "year": "1945", "volume": "57", "pages": "160-177",
        "doi": "10.1088/0959-5309/57/3/302"},
    "rachinger1948": {
        "type": "article", "authors": "Rachinger, W. A.",
        "title": "A correction for the alpha1 alpha2 doublet in the measurement of widths of X-ray diffraction lines",
        "container": "Journal of Scientific Instruments", "year": "1948", "volume": "25", "pages": "254-255",
        "doi": "10.1088/0950-7671/25/7/125"},
    "ryan1988": {
        "type": "article", "authors": "Ryan, C. G.; Clayton, E.; Griffin, W. L.; Sie, S. H.; Cousens, D. R.",
        "title": "SNIP, a statistics-sensitive background treatment for the quantitative analysis of PIXE spectra in "
                 "geoscience applications",
        "container": "Nuclear Instruments and Methods in Physics Research B", "year": "1988", "volume": "34",
        "pages": "396-402", "doi": "10.1016/0168-583X(88)90063-8"},
    "morhac1997": {
        "type": "article", "authors": "Morháč, M.; Kliman, J.; Matoušek, V.; Veselský, M.; Turzo, I.",
        "title": "Background elimination methods for multidimensional coincidence gamma-ray spectra",
        "container": "Nuclear Instruments and Methods in Physics Research A", "year": "1997", "volume": "401",
        "pages": "113-132", "doi": "10.1016/S0168-9002(97)01023-1"},
    "itc_c": {
        "type": "book", "authors": "Brown, P. J.; Fox, A. G.; Maslen, E. N.; O'Keefe, M. A.; Willis, B. T. M.",
        "title": "Intensity of diffracted intensities (Table 6.1.1.4: Cromer-Mann coefficients of the atomic "
                 "scattering factors)",
        "container": "International Tables for Crystallography, Vol. C (Hrsg. E. Prince), IUCr", "year": "2006",
        "pages": "554-595", "doi": "10.1107/97809553602060000600",
        "note": "Koeffizienten aus dem Gedächtnis übertragen, geprüft nur über f(0) = Z; " + NG},
    "bearden1967": {
        "type": "article", "authors": "Bearden, J. A.", "title": "X-ray wavelengths",
        "container": "Reviews of Modern Physics", "year": "1967", "volume": "39", "pages": "78-124",
        "doi": "10.1103/RevModPhys.39.78",
        "note": "Wellenlängen der Röhren als übliche Standardwerte der Gerätesoftware; " + NG},
    "wyckoff1963": {
        "type": "book", "authors": "Wyckoff, R. W. G.", "title": "Crystal Structures, Vol. 1",
        "container": "Interscience, New York", "year": "1963", "edition": "2",
        "note": "Strukturtypen und Gitterparameter der eingebauten Phasen; " + NG},
    "hall1991": {
        "type": "article", "authors": "Hall, S. R.; Allen, F. H.; Brown, I. D.",
        "title": "The crystallographic information file (CIF): a new standard archive file for crystallography",
        "container": "Acta Crystallographica A", "year": "1991", "volume": "47", "pages": "655-685",
        "doi": "10.1107/S010876739101067X"},
    "grazulis2012": {
        "type": "article", "authors": "Gražulis, S.; Daškevič, A.; Merkys, A.; Chateigner, D.; Lutterotti, L.; "
                                      "Quirós, M.; Serebryanaya, N. R.; Moeck, P.; Downs, R. T.; Le Bail, A.",
        "title": "Crystallography Open Database (COD): an open-access collection of crystal structures and platform "
                 "for world-wide collaboration",
        "container": "Nucleic Acids Research", "year": "2012", "volume": "40", "pages": "D420-D427",
        "doi": "10.1093/nar/gkr900"},
    "chung1974": {
        "type": "article", "authors": "Chung, F. H.",
        "title": "Quantitative interpretation of X-ray diffraction patterns of mixtures. I. Matrix-flushing method "
                 "for quantitative multicomponent analysis",
        "container": "Journal of Applied Crystallography", "year": "1974", "volume": "7", "pages": "519-525",
        "doi": "10.1107/S0021889874010375"},
    "hubbard1988": {
        "type": "article", "authors": "Hubbard, C. R.; Snyder, R. L.", "title": "RIR - measurement and use in "
        "quantitative XRD", "container": "Powder Diffraction", "year": "1988", "volume": "3", "pages": "74-77",
        "doi": "10.1017/S0885715600013257"},
    "savitzky1964": {
        "type": "article", "authors": "Savitzky, A.; Golay, M. J. E.",
        "title": "Smoothing and differentiation of data by simplified least squares procedures",
        "container": "Analytical Chemistry", "year": "1964", "volume": "36", "pages": "1627-1639",
        "doi": "10.1021/ac60214a047"},
    "thompson1987": {
        "type": "article", "authors": "Thompson, P.; Cox, D. E.; Hastings, J. B.",
        "title": "Rietveld refinement of Debye-Scherrer synchrotron X-ray data from Al2O3",
        "container": "Journal of Applied Crystallography", "year": "1987", "volume": "20", "pages": "79-83",
        "doi": "10.1107/S0021889887087090"},
    # ------------------------------------------------------------------ Phasendiagramme
    "massalski1990": {
        "type": "book", "authors": "Massalski, T. B. (Hrsg.)", "title": "Binary Alloy Phase Diagrams",
        "container": "ASM International, Materials Park (OH)", "year": "1990", "edition": "2",
        "note": "invariante Punkte, wie in Callister wiedergegeben; " + NG},
    "murray1984": {
        "type": "article", "authors": "Murray, J. L.; McAlister, A. J.", "title": "The Al-Si (aluminum-silicon) system",
        "container": "Bulletin of Alloy Phase Diagrams", "year": "1984", "volume": "5", "pages": "74-84",
        "doi": "10.1007/BF02868729", "note": NG},
    "subramanian1993": {
        "type": "article", "authors": "Subramanian, P. R.; Perepezko, J. H.", "title": "The Ag-Cu (silver-copper) system",
        "container": "Journal of Phase Equilibria", "year": "1993", "volume": "14", "pages": "62-75",
        "doi": "10.1007/BF02652162", "note": NG},
    # ------------------------------------------------------------------ Gitterbetrachter (KG)
    "basinski1955": {
        "type": "article", "authors": "Basinski, Z. S.; Hume-Rothery, W.; Sutton, A. L.",
        "title": "The lattice expansion of iron", "container": "Proceedings of the Royal Society of London A",
        "year": "1955", "volume": "229", "pages": "459-467", "doi": "10.1098/rspa.1955.0102", "note": NG},
    "ehrhart1991": {
        "type": "chapter", "authors": "Ehrhart, P.",
        "title": "Properties and interactions of atomic defects in metals and alloys",
        "container": "Landolt-Börnstein, New Series III/25, Springer, Berlin", "year": "1991",
        "note": "Bildungsenthalpien der Leerstellen; " + NG},
    "cordero2008": {
        "type": "article", "authors": "Cordero, B.; Gómez, V.; Platero-Prats, A. E.; Revés, M.; Echeverría, J.; "
        "Cremades, E.; Barragán, F.; Alvarez, S.", "title": "Covalent radii revisited",
        "container": "Dalton Transactions", "year": "2008", "pages": "2832-2838", "doi": "10.1039/b801115j", "note": NG},
    "hirth1980": {
        "type": "article", "authors": "Hirth, J. P.", "title": "Effects of hydrogen on the properties of iron and steel",
        "container": "Metallurgical Transactions A", "year": "1980", "volume": "11", "pages": "861-890",
        "doi": "10.1007/BF02654700", "note": NG},
    "hirth1982": {
        "type": "book", "authors": "Hirth, J. P.; Lothe, J.", "title": "Theory of Dislocations",
        "container": "Wiley, New York", "year": "1982", "edition": "2",
        "note": "Verschiebungsfeld der Stufenversetzung (isotrop, Volterra), Stapelfehler, Kleinwinkelkorngrenzen"},
    "willis1975": {
        "type": "book", "authors": "Willis, B. T. M.; Pryor, A. W.", "title": "Thermal Vibrations in Crystallography",
        "container": "Cambridge University Press", "year": "1975",
        "note": "mittleres Verschiebungsquadrat im Debye-Modell"},
    "eshelby1956": {
        "type": "chapter", "authors": "Eshelby, J. D.", "title": "The continuum theory of lattice defects",
        "container": "Solid State Physics 3, Academic Press, New York", "year": "1956", "pages": "79-144",
        "doi": "10.1016/S0081-1947(08)60132-0", "note": "Verschiebung um einen Fremdatom-Einschluss proportional zu 1/r²; " + NG},
    # ------------------------------------------------------------------ Stahl
    "ito1968": {
        "type": "misc", "authors": "Ito, Y.; Bessyo, K.",
        "title": "Weldability formula of high strength steels related to heat-affected zone cracking",
        "container": "International Institute of Welding, Doc. IX-576-68", "year": "1968", "note": NG},
    # ------------------------------------------------------------------ Verbunde
    "tsai1971": {
        "type": "article", "authors": "Tsai, S. W.; Wu, E. M.", "title": "A general theory of strength for anisotropic "
        "materials", "container": "Journal of Composite Materials", "year": "1971", "volume": "5", "pages": "58-80",
        "doi": "10.1177/002199837100500106"},
    "azzi1965": {
        "type": "article", "authors": "Azzi, V. D.; Tsai, S. W.", "title": "Anisotropic strength of composites",
        "container": "Experimental Mechanics", "year": "1965", "volume": "5", "pages": "283-288",
        "doi": "10.1007/BF02326292"},
    "hashin1980": {
        "type": "article", "authors": "Hashin, Z.", "title": "Failure criteria for unidirectional fiber composites",
        "container": "Journal of Applied Mechanics", "year": "1980", "volume": "47", "pages": "329-334",
        "doi": "10.1115/1.3153664"},
    "jones1999": {
        "type": "book", "authors": "Jones, R. M.", "title": "Mechanics of Composite Materials",
        "container": "Taylor & Francis, Philadelphia", "year": "1999", "edition": "2"},
    # ------------------------------------------------------------------ Ermüdung
    "astme739": {
        "type": "standard", "authors": "ASTM International",
        "title": "ASTM E739-10 (2015) Standard Practice for Statistical Analysis of Linear or Linearized "
                 "Stress-Life (S-N) and Strain-Life (e-N) Fatigue Data", "container": "ASTM International",
        "year": "2015", "note": NG},
    "astme1049": {
        "type": "standard", "authors": "ASTM International",
        "title": "ASTM E1049-85 (2017) Standard Practices for Cycle Counting in Fatigue Analysis",
        "container": "ASTM International", "year": "2017", "note": NG},
    "nelson1990": {
        "type": "book", "authors": "Nelson, W.",
        "title": "Accelerated Testing: Statistical Models, Test Plans, and Data Analyses",
        "container": "Wiley, New York", "year": "1990", "note": "Maximum-Likelihood-Schätzung mit zensierten Daten"},
    "swt1970": {
        "type": "article", "authors": "Smith, K. N.; Watson, P.; Topper, T. H.",
        "title": "A stress-strain function for the fatigue of metals", "container": "Journal of Materials",
        "year": "1970", "volume": "5", "pages": "767-778"},
    "shigley": {
        "type": "book", "authors": "Budynas, R. G.; Nisbett, J. K.", "title": "Shigley's Mechanical Engineering Design",
        "container": "McGraw-Hill, New York", "year": "2015", "edition": "10",
        "note": "Marin-Faktoren (Oberfläche, Grösse, Belastung, Temperatur, Zuverlässigkeit); " + NG},
    # ------------------------------------------------------------------ Weibull, Bruch
    "bernard1953": {
        "type": "article", "authors": "Bernard, A.; Bos-Levenbach, E. J.",
        "title": "Het uitzetten van waarnemingen op waarschijnlijkheids-papier (The plotting of observations on "
                 "probability paper)", "container": "Statistica Neerlandica", "year": "1953", "volume": "7",
        "pages": "163-173", "doi": "10.1111/j.1467-9574.1953.tb00821.x", "note": NG},
    "efron1993": {
        "type": "book", "authors": "Efron, B.; Tibshirani, R. J.", "title": "An Introduction to the Bootstrap",
        "container": "Chapman & Hall, New York", "year": "1993"},
    "astmc1239": {
        "type": "standard", "authors": "ASTM International",
        "title": "ASTM C1239-13 (2018) Standard Practice for Reporting Uniaxial Strength Data and Estimating Weibull "
                 "Distribution Parameters for Advanced Ceramics", "container": "ASTM International", "year": "2018",
        "note": NG},
    "quinn2003": {
        "type": "article", "authors": "Quinn, G. D.",
        "title": "Weibull strength scaling for standardized rectangular flexure specimens",
        "container": "Journal of the American Ceramic Society", "year": "2003", "volume": "86", "pages": "508-510",
        "doi": "10.1111/j.1151-2916.2003.tb03329.x", "note": NG},
    "astme399": {
        "type": "standard", "authors": "ASTM International",
        "title": "ASTM E399-22 Standard Test Method for Linear-Elastic Plane-Strain Fracture Toughness of Metallic "
                 "Materials", "container": "ASTM International", "year": "2022", "note": NG},
    # ------------------------------------------------------------------ Härte, Gefüge
    "iso4545": {
        "type": "standard", "authors": "ISO", "container": "International Organization for Standardization",
        "title": "ISO 4545-1:2017 Metallic materials - Knoop hardness test - Part 1: Test method", "year": "2017",
        "note": NG},
    "astme112": {
        "type": "standard", "authors": "ASTM International",
        "title": "ASTM E112-13 (2021) Standard Test Methods for Determining Average Grain Size",
        "container": "ASTM International", "year": "2021", "note": NG},
    "hall1951": {
        "type": "article", "authors": "Hall, E. O.", "title": "The deformation and ageing of mild steel: III "
        "Discussion of results", "container": "Proceedings of the Physical Society B", "year": "1951",
        "volume": "64", "pages": "747-753", "doi": "10.1088/0370-1301/64/9/303"},
    "petch1953": {
        "type": "article", "authors": "Petch, N. J.", "title": "The cleavage strength of polycrystals",
        "container": "Journal of the Iron and Steel Institute", "year": "1953", "volume": "174", "pages": "25-28"},
    # ------------------------------------------------------------------ Korrosion, Kriechen
    "stern1957": {
        "type": "article", "authors": "Stern, M.; Geary, A. L.",
        "title": "Electrochemical polarization I. A theoretical analysis of the shape of polarization curves",
        "container": "Journal of the Electrochemical Society", "year": "1957", "volume": "104", "pages": "56-63",
        "doi": "10.1149/1.2428496"},
    "astmg59": {
        "type": "standard", "authors": "ASTM International",
        "title": "ASTM G59-97 (2020) Standard Test Method for Conducting Potentiodynamic Polarization Resistance "
                 "Measurements", "container": "ASTM International", "year": "2020", "note": NG},
    "norton1929": {
        "type": "book", "authors": "Norton, F. H.", "title": "The Creep of Steel at High Temperatures",
        "container": "McGraw-Hill, New York", "year": "1929"},
}


def rec(key: str) -> dict:
    """Quellendatensatz aus diesem Modul oder aus labcalc.sources."""
    if key in REFS:
        return dict(REFS[key])
    if key in S.REFS:
        return S.ref(key)
    raise KeyError(f"Quelle {key} unbekannt")


def known(key: str) -> bool:
    return key in REFS or key in S.REFS


def cite(b, keys) -> list[str]:
    """Quellen in die Literatur des Bundles schreiben; gibt die Schlüssel zurück (unbekannte werden ausgelassen)."""
    import labcite
    out = []
    for k in [keys] if isinstance(keys, str) else (keys or []):
        if k and known(k) and k not in out:
            labcite.to_bib(b, k, rec(k))
            out.append(k)
    return out


def short(key: str, lang: str = "de") -> str:
    import labcite
    return labcite.short(rec(key), lang)


def listing(keys, lang: str = "de") -> list[dict]:
    """Für die Seite: Schlüssel, Kurzform und ausgeschriebene Angabe."""
    import labcite
    out = []
    for k in keys or []:
        if known(k):
            r = rec(k)
            out.append({"key": k, "short": labcite.short(r, lang), "text": labcite.text(r, lang),
                        "unchecked": NG in (r.get("note") or "")})
    return out
