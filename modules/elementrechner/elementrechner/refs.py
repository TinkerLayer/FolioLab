"""Quellen des Elementrechners als strukturierte Einträge (labcite). Schlüssel = Zitierschlüssel im Bericht.

Gemeinsame Quellen (CODATA 2022, SI-Broschüre, Green Book, Lehrbücher) kommen aus labcalc.sources.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SDK = Path(__file__).resolve().parents[3] / "sdk" / "python"
if _SDK.is_dir() and str(_SDK) not in sys.path:
    sys.path.insert(0, str(_SDK))

from labcalc import sources as SRC  # noqa: E402

REFS: dict[str, dict] = {
    "ciaaw2021": {"type": "article", "authors": "Prohaska, Thomas; Irrgeher, Johanna; Benefield, Jacqueline; Böhlke, John K.; "
                  "Chesson, Lesley A.; Coplen, Tyler B.; Ding, Tiping; Dunn, Philip J. H.; Gröning, Manfred; "
                  "Holden, Norman E.; Meijer, Harro A. J.; Moossen, Heiko; Possolo, Antonio; Takahashi, Yoshio; "
                  "Vogl, Jochen; Walczyk, Thomas; Wang, Jun; Wieser, Michael E.; Yoneda, Shigekazu; Zhu, Xiang-Kun; "
                  "Meija, Juris",
                  "title": "Standard atomic weights of the elements 2021 (IUPAC Technical Report)",
                  "container": "Pure and Applied Chemistry", "year": "2022", "volume": "94", "issue": "5",
                  "pages": "573-600", "doi": "10.1515/pac-2019-0603"},
    "ciaaw2024": {"type": "web", "authors": "CIAAW",
                  "title": "Standard Atomic Weights 2024",
                  "container": "IUPAC Commission on Isotopic Abundances and Atomic Weights, www.ciaaw.org", "year": "2024",
                  "url": "https://www.ciaaw.org/atomic-weights.htm", "accessed": "2026-11-17",
                  "note": "gekürzte und ungekürzte Werte; Änderungen 2024 für Gd, Lu, Zr"},
    "ciaaw2025ci": {"type": "article", "authors": "IUPAC",
                    "title": "Standard atomic weights of three technology critical elements revised",
                    "container": "Chemistry International", "year": "2025", "volume": "47", "issue": "1", "pages": "20",
                    "doi": "10.1515/ci-2025-0105"},
    "ciaaw_iso2024": {"type": "web", "authors": "CIAAW",
                      "title": "Isotopic Compositions of the Elements 2024",
                      "container": "IUPAC Commission on Isotopic Abundances and Atomic Weights, www.ciaaw.org", "year": "2024",
                      "url": "https://www.ciaaw.org/isotopic-abundances.htm", "accessed": "2026-11-17"},
    "meija2016": {"type": "article", "authors": "Meija, Juris; Coplen, Tyler B.; Berglund, Michael; Brand, Willi A.; "
                  "De Bièvre, Paul; Gröning, Manfred; Holden, Norman E.; Irrgeher, Johanna; Loss, Robert D.; "
                  "Walczyk, Thomas; Prohaska, Thomas",
                  "title": "Isotopic compositions of the elements 2013 (IUPAC Technical Report)",
                  "container": "Pure and Applied Chemistry", "year": "2016", "volume": "88", "issue": "3",
                  "pages": "293-306", "doi": "10.1515/pac-2015-0503"},
    "ame2020": {"type": "article", "authors": "Wang, Meng; Huang, W. J.; Kondev, F. G.; Audi, G.; Naimi, S.",
                "title": "The AME 2020 atomic mass evaluation (II). Tables, graphs and references",
                "container": "Chinese Physics C", "year": "2021", "volume": "45", "issue": "3", "pages": "030003",
                "doi": "10.1088/1674-1137/abddaf"},
    "nubase2020": {"type": "article", "authors": "Kondev, F. G.; Wang, M.; Huang, W. J.; Naimi, S.; Audi, G.",
                   "title": "The NUBASE2020 evaluation of nuclear physics properties",
                   "container": "Chinese Physics C", "year": "2021", "volume": "45", "issue": "3", "pages": "030001",
                   "doi": "10.1088/1674-1137/abddae"},
    "trost1991": {"type": "article", "authors": "Trost, Barry M.", "title": "The atom economy – a search for synthetic efficiency",
                  "container": "Science", "year": "1991", "volume": "254", "issue": "5037", "pages": "1471-1477",
                  "doi": "10.1126/science.1962206"},
    "greenbook": SRC.REFS["greenbook"],
    "codata2022": SRC.REFS["codata2022"],
    "openchemlib": {"type": "web", "authors": "cheminfo; Idorsia Pharmaceuticals",
                    "title": "OpenChemLib JS 9.26.0", "container": "GitHub", "year": "2026",
                    "url": "https://github.com/cheminfo/openchemlib-js", "accessed": "2026-11-17", "licence": "BSD-3-Clause",
                    "note": "Strukturbilder und Moleküleditor"},
    # A6: erwartete IR-Banden je funktioneller Gruppe (labcalc.irbands; dieselbe Angabe wie im FTIR-Modul)
    "socrates2001": {"type": "book", "authors": "Socrates, George",
                     "title": "Infrared and Raman Characteristic Group Frequencies: Tables and Charts",
                     "container": "Wiley, Chichester", "year": "2001", "note": "3. Auflage"},
    # Runde U: Unsicherheit der Standardatomgewichte (Intervall als Rechteckverteilung) und Prüfbeispiel Ansetzen
    "possolo2018": {"type": "article", "authors": "Possolo, Antonio; van der Veen, Adriaan M. H.; Meija, Juris; "
                    "Hibbert, D. Brynn",
                    "title": "Interpreting and propagating the uncertainty of the standard atomic weights "
                             "(IUPAC Technical Report)",
                    "container": "Pure and Applied Chemistry", "year": "2018", "volume": "90", "issue": "2",
                    "pages": "395-424", "doi": "10.1515/pac-2016-0402",
                    "note": "Rechteckverteilung für Intervalle laut Kurzfassung geprüft; Einzelwerte mit Klammer-"
                            "Unsicherheit als Rechteck ±U ist eine Annahme des Moduls (Angaben nicht am Original geprüft)"},
    "quam2012a1": {"type": "book", "authors": "Ellison, S. L. R.; Williams, A.", "year": "2012", "edition": "3. Auflage",
                   "title": "EURACHEM/CITAC Guide CG 4: Quantifying Uncertainty in Analytical Measurement, Beispiel A1: "
                            "Herstellung eines Kalibrierstandards",
                   "container": "Eurachem", "url": "https://www.eurachem.org/index.php/publications/guides/quam",
                   "note": "Prüfwerte c(Cd) = 1002,7 mg/L, u = 0,9 mg/L, U = 1,8 mg/L (k = 2); Angaben nicht am Original "
                           "geprüft"},
}
for _k in ("pubchem2025", "pubchem_pt", "wikidata", "iupac_pka", "zheng2026", "perrin1965", "serjeant1979", "srd46",
           "hsdb", "icsc", "niosh", "osha", "doepac", "bandura2006", "purplebook",
           "cox1989", "wagman1982", "reed2020", "burcat2005", "burcat2018", "atct2004", "atkins",
           "favre2014", "joback1987", "joback_wiki", "ertl2000", "sander2015", "clayden2012",
           "karen2016", "redbook2005", "harris", "bard", "good1966", "kell1975", "sheldon2007", "constable2002", "jimenez2011",
           "krane", "bateman1910", "stuiver1977", "godwin1962", "steiger1977", "jaffey1971", "villa2015",
           "domalski1993", "benson1969", "chase1998", "mcbride2002", "arrhenius1889", "eyring1935", "turns2012", "davies1962", "kielland1937", "malmberg1956", "baes1976", "nistasd", "shannon1976", "nistwebbook"):
    REFS[_k] = SRC.REFS[_k]
