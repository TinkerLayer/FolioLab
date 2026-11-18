"""Quellen für Formelsammlung und Konstanten (Rechner, eigene Gleichungen, Elementrechner).

Jeder Eintrag ist ein Quellendatensatz im Format von ``labcite`` (type, authors, title, container, year, …), damit
Oberfläche und Bericht ihn gleich behandeln: kurz im Tooltip, ausgeschrieben im Literaturverzeichnis.

Konstanten: CODATA 2022 (NIST), definierte SI-Konstanten nach der SI-Broschüre (9. Ausgabe, 2019).
Formeln: Lehrbücher und Normen je Sachgebiet; ``note`` nennt das Thema, unter dem die Formel dort steht.
Seitenzahlen werden nur genannt, wo sie geprüft sind.
"""
from __future__ import annotations

REFS: dict[str, dict] = {
    # ------------------------------------------------------------------ Konstanten
    "codata2022": {
        "type": "article", "authors": "Mohr, P. J.; Newell, D. B.; Taylor, B. N.; Tiesinga, E.",
        "title": "CODATA recommended values of the fundamental physical constants: 2022",
        "container": "Reviews of Modern Physics", "year": "2025", "volume": "97", "pages": "025002",
        "doi": "10.1103/RevModPhys.97.025002", "url": "https://physics.nist.gov/cuu/Constants/",
        "note": "Werte wie in der NIST-Tabelle (2022 CODATA adjustment)"},
    "si2019": {
        "type": "standard", "authors": "{BIPM}",                     # Körperschaft; Kurzform „BIPM 2019“
        "title": "The International System of Units (SI)", "container": "Bureau International des Poids et Mesures", "year": "2019", "edition": "9. Ausgabe",
        "url": "https://www.bipm.org/en/publications/si-brochure",
        "note": "definierende Konstanten (Tab. 1) und Celsius-Temperatur"},
    "greenbook": {
        "type": "book", "authors": "Cohen, E. R.; Cvitaš, T.; Frey, J. G.; Holmström, B.; Kuchitsu, K.; Marquardt, R.; "
                                   "Mills, I.; Pavese, F.; Quack, M.; Stohner, J.; Strauss, H. L.; Takami, M.; Thor, A. J.",
        "title": "Quantities, Units and Symbols in Physical Chemistry (IUPAC Green Book)",
        "container": "RSC Publishing", "year": "2007", "edition": "3. Auflage", "doi": "10.1039/9781847557889",
        "note": "Hrsg.; Standardzustand und Standardkonzentration"},
    "bronstein": {
        "type": "book", "authors": "Bronshtein, I. N.; Semendyayev, K. A.; Musiol, G.; Mühlig, H.",
        "title": "Handbook of Mathematics", "container": "Springer", "year": "2015", "edition": "6. Auflage"},
    # ------------------------------------------------------------------ Physik, Technik
    "halliday": {
        "type": "book", "authors": "Halliday, D.; Resnick, R.; Walker, J.", "title": "Fundamentals of Physics",
        "container": "Wiley", "year": "2014", "edition": "10. Auflage"},
    "gross2": {
        "type": "book", "authors": "Gross, D.; Hauger, W.; Schröder, J.; Wall, W. A.",
        "title": "Technische Mechanik 2: Elastostatik", "container": "Springer Vieweg", "year": "2017",
        "edition": "13. Auflage"},
    "callister": {
        "type": "book", "authors": "Callister, W. D.; Rethwisch, D. G.",
        "title": "Materials Science and Engineering: An Introduction", "container": "Wiley", "year": "2018",
        "edition": "10. Auflage"},
    "iso6892": {
        "type": "standard", "authors": "ISO", "container": "International Organization for Standardization",
        "title": "ISO 6892-1:2019 Metallische Werkstoffe – Zugversuch – Teil 1: Prüfverfahren bei Raumtemperatur",
        "year": "2019"},
    "iso178": {
        "type": "standard", "authors": "ISO", "container": "International Organization for Standardization",
        "title": "ISO 178:2019 Kunststoffe – Bestimmung der Biegeeigenschaften", "year": "2019"},
    "anderson": {
        "type": "book", "authors": "Anderson, T. L.", "title": "Fracture Mechanics: Fundamentals and Applications",
        "container": "CRC Press", "year": "2017", "edition": "4. Auflage"},
    "iso6507": {
        "type": "standard", "authors": "ISO", "container": "International Organization for Standardization",
        "title": "ISO 6507-1:2018 Metallische Werkstoffe – Härteprüfung nach Vickers – Teil 1: Prüfverfahren",
        "year": "2018"},
    "iso6506": {
        "type": "standard", "authors": "ISO", "container": "International Organization for Standardization",
        "title": "ISO 6506-1:2014 Metallische Werkstoffe – Härteprüfung nach Brinell – Teil 1: Prüfverfahren",
        "year": "2014"},
    "iso18265": {
        "type": "standard", "authors": "ISO", "container": "International Organization for Standardization",
        "title": "ISO 18265:2013 Metallische Werkstoffe – Umwertung von Härtewerten", "year": "2013",
        "note": "Faktor 3,3 ist ein Faustwert; belastbare Umwertung nur mit den Tabellen der Norm"},
    "bergman": {
        "type": "book", "authors": "Bergman, T. L.; Lavine, A. S.; Incropera, F. P.; DeWitt, D. P.",
        "title": "Fundamentals of Heat and Mass Transfer", "container": "Wiley", "year": "2011", "edition": "7. Auflage"},
    "white": {
        "type": "book", "authors": "White, F. M.", "title": "Fluid Mechanics", "container": "McGraw-Hill",
        "year": "2011", "edition": "7. Auflage"},
    "hecht": {
        "type": "book", "authors": "Hecht, E.", "title": "Optics", "container": "Pearson", "year": "2017",
        "edition": "5. Auflage"},
    "murphy": {
        "type": "book", "authors": "Murphy, D. B.; Davidson, M. W.",
        "title": "Fundamentals of Light Microscopy and Electronic Imaging", "container": "Wiley-Blackwell",
        "year": "2012", "edition": "2. Auflage"},
    "krane": {
        "type": "book", "authors": "Krane, K. S.", "title": "Introductory Nuclear Physics", "container": "Wiley",
        "year": "1988"},
    "bateman1910": {
        "type": "article", "authors": "Bateman, H.",
        "title": "The solution of a system of differential equations occurring in the theory of radioactive "
                 "transformations", "container": "Proceedings of the Cambridge Philosophical Society", "year": "1910",
        "volume": "15", "pages": "423-427"},
    "stuiver1977": {
        "type": "article", "authors": "Stuiver, M.; Polach, H. A.", "title": "Discussion: Reporting of 14C data",
        "container": "Radiocarbon", "year": "1977", "volume": "19", "issue": "3", "pages": "355-363",
        "doi": "10.1017/S0033822200003672"},
    "godwin1962": {
        "type": "article", "authors": "Godwin, H.", "title": "Half-life of radiocarbon", "container": "Nature",
        "year": "1962", "volume": "195", "pages": "984", "doi": "10.1038/195984a0"},
    "steiger1977": {
        "type": "article", "authors": "Steiger, R. H.; Jaeger, E.",
        "title": "Subcommission on geochronology: convention on the use of decay constants in geo- and "
                 "cosmochronology", "container": "Earth and Planetary Science Letters", "year": "1977",
        "volume": "36", "issue": "3", "pages": "359-362", "doi": "10.1016/0012-821X(77)90060-7"},
    "jaffey1971": {
        "type": "article", "authors": "Jaffey, A. H.; Flynn, K. F.; Glendenin, L. E.; Bentley, W. C.; Essling, A. M.",
        "title": "Precision measurement of half-lives and specific activities of 235U and 238U",
        "container": "Physical Review C", "year": "1971", "volume": "4", "issue": "5", "pages": "1889-1906",
        "doi": "10.1103/PhysRevC.4.1889"},
    "villa2015": {
        "type": "article", "authors": "Villa, I. M.; De Bievre, P.; Holden, N. E.; Renne, P. R.",
        "title": "IUPAC-IUGS recommendation on the half life of 87Rb",
        "container": "Geochimica et Cosmochimica Acta", "year": "2015", "volume": "164", "pages": "382-385",
        "doi": "10.1016/j.gca.2015.05.025"},
    # ------------------------------------------------------------------ Chemie
    "atkins": {
        "type": "book", "authors": "Atkins, P.; de Paula, J.; Keeler, J.", "title": "Atkins' Physical Chemistry",
        "container": "Oxford University Press", "year": "2018", "edition": "11. Auflage"},
    "harris": {
        "type": "book", "authors": "Harris, D. C.", "title": "Quantitative Chemical Analysis",
        "container": "W. H. Freeman", "year": "2016", "edition": "9. Auflage"},
    "bard": {
        "type": "book", "authors": "Bard, A. J.; Faulkner, L. R.",
        "title": "Electrochemical Methods: Fundamentals and Applications", "container": "Wiley", "year": "2001",
        "edition": "2. Auflage"},
    "porter": {
        "type": "book", "authors": "Porter, D. A.; Easterling, K. E.; Sherif, M. Y.",
        "title": "Phase Transformations in Metals and Alloys", "container": "CRC Press", "year": "2009",
        "edition": "3. Auflage"},
    # ------------------------------------------------------------------ Stoffdaten (Sammlung und Nachschlagewerte)
    "pubchem2025": {
        "type": "article", "authors": "Kim, Sunghwan; Chen, Jie; Cheng, Tiejun; Gindulyte, Asta; He, Jia; He, Siqian; "
        "Li, Qingliang; Shoemaker, Benjamin A.; Thiessen, Paul A.; Yu, Bo; Zaslavsky, Leonid; Zhang, Jian; Bolton, Evan E.",
        "title": "PubChem 2025 update", "container": "Nucleic Acids Research", "year": "2025", "volume": "53",
        "issue": "D1", "pages": "D1516-D1525", "doi": "10.1093/nar/gkae1059",
        "note": "Strukturen, Namen, CAS-Nummern; Abruf über PUG REST am 17.11.2026"},
    "pubchem_pt": {
        "type": "article", "authors": "Kim, Sunghwan; Gindulyte, Asta; Zhang, Jian; Thiessen, Paul A.; Bolton, Evan E.",
        "title": "PubChem Periodic Table and Element pages: improving access to information on chemical elements from "
        "authoritative sources", "container": "Chemistry Teacher International", "year": "2021", "volume": "3",
        "issue": "1", "pages": "57-65", "doi": "10.1515/cti-2020-0006"},
    "wikidata": {
        "type": "article", "authors": "Vrandečić, Denny; Krötzsch, Markus", "title": "Wikidata: a free collaborative "
        "knowledgebase", "container": "Communications of the ACM", "year": "2014", "volume": "57", "issue": "10",
        "pages": "78-85", "doi": "10.1145/2629489",
        "note": "deutsche Stoffnamen (CC0), Abfrage über query.wikidata.org am 17.11.2026"},
    "iupac_pka": {"short": "IUPAC pKa-Datensatz", 
        "type": "misc", "authors": "Zheng, Jonathan W.; Lafontant-Joseph, Olivier",
        "title": "IUPAC Digitized pKa Dataset (IUPAC/Dissociation-Constants v2.4)", "container": "Zenodo",
        "year": "2026", "doi": "10.5281/zenodo.7236452", "licence": "CC BY-NC 4.0",
        "note": "Reproduced by permission of International Union of Pure and Applied Chemistry"},
    "zheng2026": {
        "type": "article", "authors": "Zheng, Jonathan W.; Lafontant-Joseph, Olivier; Green, William H.",
        "title": "Digitized dataset of aqueous acid dissociation constants", "container": "RSC Advances",
        "year": "2026", "volume": "16", "issue": "23", "pages": "21397-21412", "doi": "10.1039/D6RA02418A"},
    "perrin1965": {
        "type": "book", "authors": "Perrin, D. D.", "title": "Dissociation Constants of Organic Bases in Aqueous "
        "Solution", "container": "Butterworths (IUPAC)", "year": "1965", "note": "Supplement 1972"},
    "serjeant1979": {
        "type": "book", "authors": "Serjeant, E. P.; Dempsey, B.", "title": "Ionisation Constants of Organic Acids in "
        "Aqueous Solution", "container": "Pergamon Press (IUPAC Chemical Data Series 23)", "year": "1979"},
    "srd46": {"short": "NIST SRD 46", 
        "type": "misc", "authors": "Burgess, Donald R.", "title": "NIST SRD 46. Critically Selected Stability "
        "Constants of Metal Complexes, Version 8.0", "container": "National Institute of Standards and Technology",
        "year": "2004", "doi": "10.18434/M32154",
        "note": "nach Martell, A. E.; Smith, R. M.: Critical Stability Constants; Abruf 2026"},
    "hsdb": {"short": "HSDB 2026", 
        "type": "web", "authors": "National Library of Medicine", "title": "Hazardous Substances Data Bank (HSDB)",
        "container": "über PubChem", "year": "2026", "url": "https://pubchem.ncbi.nlm.nih.gov/source/hsdb",
        "accessed": "2026-11-17", "note": "U.S. Government Work; Primärquelle je Wert angegeben"},
    "icsc": {"short": "ICSC 2026", 
        "type": "web", "authors": "ILO; WHO", "title": "International Chemical Safety Cards (ICSC)",
        "container": "über PubChem", "year": "2026", "url": "https://www.ilo.org/dyn/icsc/showcard.home",
        "accessed": "2026-11-17", "licence": "CC BY 4.0"},
    "niosh": {"short": "NIOSH 2026", 
        "type": "web", "authors": "NIOSH", "title": "NIOSH Pocket Guide to Chemical Hazards", "container": "über PubChem",
        "year": "2026", "url": "https://www.cdc.gov/niosh/npg/", "accessed": "2026-11-17"},
    "osha": {"short": "OSHA 2026", 
        "type": "web", "authors": "OSHA", "title": "OSHA Occupational Chemical Database", "container": "über PubChem",
        "year": "2026", "url": "https://www.osha.gov/chemicaldata/", "accessed": "2026-11-17"},
    "doepac": {"short": "DOE PAC 2026", 
        "type": "web", "authors": "U.S. Department of Energy", "title": "PAC (Protective Action Criteria) Chemical "
        "Database", "container": "über PubChem", "year": "2026", "url": "https://pubchem.ncbi.nlm.nih.gov/source/"
        "PAC%20Chemical%20Database", "accessed": "2026-11-17"},
    "purplebook": {
        "type": "book", "authors": "Jones, R. G.; Kahovec, J.; Stepto, R.; Wilks, E. S.; Hess, M.; Kitayama, T.; "
        "Metanomski, W. V. (Hrsg.)", "title": "Compendium of Polymer Terminology and Nomenclature: IUPAC "
        "Recommendations 2008", "container": "RSC Publishing", "year": "2009", "isbn": "978-0-85404-491-7",
        "note": "Wiederholeinheiten der Polymere"},
    # ------------------------------------------------------------------ Thermochemie (Bildungsgrössen bei 298,15 K)
    "cox1989": {"short": "CODATA Key Values",
        "type": "book", "authors": "Cox, J. D.; Wagman, D. D.; Medvedev, V. A.",
        "title": "CODATA Key Values for Thermodynamics", "container": "Hemisphere Publishing Corp.", "year": "1989",
        "url": "https://www.codata.info/resources/databases/key1.html",
        "note": "ΔfH°, S°, H°(298)−H°(0) bei 298,15 K und 1 bar; Tabellenabruf 2026"},
    "wagman1982": {"short": "NBS-Tabellen 1982",
        "type": "article", "authors": "Wagman, D. D.; Evans, W. H.; Parker, V. B.; Schumm, R. H.; Halow, I.; "
        "Bailey, S. M.; Churney, K. L.; Nuttall, R. L.",
        "title": "The NBS tables of chemical thermodynamic properties. Selected values for inorganic and C1 and C2 "
        "organic substances in SI units", "container": "Journal of Physical and Chemical Reference Data",
        "year": "1982", "volume": "11", "issue": "Suppl. 2",
        "note": "Erratum: J. Phys. Chem. Ref. Data 18 (1989) 1807, doi:10.1063/1.555845"},
    "reed2020": {"short": "NBS-Tabellen (NIST digital)",
        "type": "misc", "authors": "Reed, Laura",
        "title": "Digitized NBS Tables of Chemical Thermodynamic Properties", "container": "National Institute of "
        "Standards and Technology", "year": "2020", "doi": "10.18434/M32124",
        "note": "digitalisierte Fassung von Wagman et al. 1982; offensichtliche Digitalisierungsfehler (Kommastelle, "
                "Grossschreibung der Elementsymbole) werden beim Einlesen mit der Beziehung ΔfG° = ΔfH° − TΔfS° "
                "erkannt, korrigiert und beim Wert vermerkt"},
    "burcat2005": {"short": "Burcat & Ruscic 2005",
        "type": "report", "authors": "Burcat, Alexander; Ruscic, Branko",
        "title": "Third Millennium Ideal Gas and Condensed Phase Thermochemical Database for Combustion with Updates "
        "from Active Thermochemical Tables", "container": "Argonne National Laboratory", "year": "2005",
        "doi": "10.2172/925269", "note": "Bericht ANL-05/20, TAE 960"},
    "burcat2018": {"short": "Burcat-Datenbank",
        "type": "web", "authors": "Goos, Elke; Burcat, Alexander; Ruscic, Branko",
        "title": "Extended Third Millennium Ideal Gas and Condensed Phase Thermochemical Database for Combustion with "
        "Updates from Active Thermochemical Tables", "container": "Technion / DLR", "year": "2018",
        "url": "https://burcat.technion.ac.il/", "accessed": "2026-11-17",
        "note": "NASA-7-Polynome; frei verwendbar mit Quellenangabe, kein Weiterverkauf"},
    "arrhenius1889": {"type": "article", "authors": "Arrhenius, S.",
                      "title": "Über die Reaktionsgeschwindigkeit bei der Inversion von Rohrzucker durch Säuren",
                      "container": "Zeitschrift für Physikalische Chemie", "year": "1889", "volume": "4",
                      "pages": "226-248", "doi": "10.1515/zpch-1889-0416"},
    "nistasd": {"type": "web", "authors": "Kramida, A.; Ralchenko, Yu.; Reader, J.; NIST ASD Team",
                "title": "NIST Atomic Spectra Database, Ionization Energies", "container": "National Institute of Standards and Technology",
                "year": "2024", "doi": "10.18434/T4W30F", "url": "https://physics.nist.gov/PhysRefData/ASD/ionEnergy.html",
                "accessed": "2026-11-17", "licence": "NIST data (US government work), citation requested"},
    "nistwebbook": {"type": "web", "authors": "Linstrom, P. J.; Mallard, W. G. (Hrsg.)",
                    "title": "NIST Chemistry WebBook, NIST Standard Reference Database Number 69",
                    "container": "National Institute of Standards and Technology", "year": "2025", "doi": "10.18434/T4D303",
                    "url": "https://webbook.nist.gov/chemistry/", "accessed": "2026-11-17",
                    "note": "Antoine-Parameter (Phasenumwandlungsdaten) mit den dort genannten Originalquellen"},
    "shannon1976": {"type": "article", "authors": "Shannon, R. D.",
                    "title": "Revised effective ionic radii and systematic studies of interatomic distances in halides and chalcogenides",
                    "container": "Acta Crystallographica Section A", "year": "1976", "volume": "32", "issue": "5",
                    "pages": "751-767", "doi": "10.1107/S0567739476001551"},
    "baes1976": {"type": "book", "authors": "Baes, C. F.; Mesmer, R. E.", "title": "The Hydrolysis of Cations",
                 "container": "Wiley", "year": "1976"},
    "davies1962": {"type": "book", "authors": "Davies, C. W.", "title": "Ion Association", "container": "Butterworths",
                   "year": "1962"},
    "kielland1937": {"type": "article", "authors": "Kielland, J.",
                     "title": "Individual Activity Coefficients of Ions in Aqueous Solutions",
                     "container": "Journal of the American Chemical Society", "year": "1937", "volume": "59",
                     "pages": "1675-1678", "doi": "10.1021/ja01288a032"},
    "malmberg1956": {"type": "article", "authors": "Malmberg, C. G.; Maryott, A. A.",
                     "title": "Dielectric Constant of Water from 0 to 100 C",
                     "container": "Journal of Research of the National Bureau of Standards", "year": "1956",
                     "volume": "56", "pages": "1-8", "doi": "10.6028/jres.056.001"},
    "turns2012": {"type": "book", "authors": "Turns, S. R.",
                  "title": "An Introduction to Combustion: Concepts and Applications", "container": "McGraw-Hill",
                  "year": "2012", "edition": "3. Auflage"},
    "eyring1935": {"type": "article", "authors": "Eyring, H.", "title": "The Activated Complex in Chemical Reactions",
                   "container": "The Journal of Chemical Physics", "year": "1935", "volume": "3", "pages": "107-115",
                   "doi": "10.1063/1.1749604"},
    "chase1998": {"short": "NIST-JANAF (Chase 1998)",
        "type": "book", "authors": "Chase, Malcolm W., Jr.",
        "title": "NIST-JANAF Thermochemical Tables, Fourth Edition",
        "container": "Journal of Physical and Chemical Reference Data, Monograph 9", "year": "1998",
        "doi": "10.18434/T42S31", "url": "https://janaf.nist.gov/",
        "note": "einzelne Tabellenwerte als Vergleich in den Tests (log Kf, ΔfG°(T)); die Tabellen selbst sind nicht enthalten"},
    "mcbride2002": {"short": "McBride et al. 2002",
        "type": "report", "authors": "McBride, Bonnie J.; Zehe, Michael J.; Gordon, Sanford",
        "title": "NASA Glenn Coefficients for Calculating Thermodynamic Properties of Individual Species",
        "container": "NASA Glenn Research Center, NASA/TP-2002-211556", "year": "2002",
        "url": "https://ntrs.nasa.gov/citations/20020085330",
        "note": "Form der NASA-7-Polynome: Cp/R, H/RT, S/R"},
    "atct2004": {"short": "Ruscic et al. 2004 (ATcT)",
        "type": "article", "authors": "Ruscic, Branko; Pinzon, Reinhardt E.; Morton, Melita L.; von Laszevski, Gregor; "
        "Bittner, Sandra J.; Nijsure, Sandeep G.; Amin, Kaizar A.; Minkoff, Michael; Wagner, Albert F.",
        "title": "Introduction to Active Thermochemical Tables: Several \"Key\" Enthalpies of Formation Revisited",
        "container": "The Journal of Physical Chemistry A", "year": "2004", "volume": "108", "issue": "45",
        "pages": "9979-9997", "doi": "10.1021/jp047912y"},
    "bandura2006": {
        "type": "article", "authors": "Bandura, Andrei V.; Lvov, Serguei N.", "title": "The Ionization Constant of Water "
        "over Wide Ranges of Temperature and Density", "container": "Journal of Physical and Chemical Reference Data",
        "year": "2006", "volume": "35", "issue": "1", "pages": "15-30", "doi": "10.1063/1.1928231",
        "note": "pKw = 13,995 bei 25 °C und 0,1 MPa"},
    "good1966": {
        "type": "article", "authors": "Good, Norman E.; Winget, G. Douglas; Winter, Wilhelmina; Connolly, Thomas N.; "
        "Izawa, Seikichi; Singh, Raizada M. M.", "title": "Hydrogen Ion Buffers for Biological Research",
        "container": "Biochemistry", "year": "1966", "volume": "5", "issue": "2", "pages": "467-477",
        "doi": "10.1021/bi00866a011", "note": "Good-Puffer (MES, PIPES, HEPES, Tricin, Bicin u. a.)"},
    "sheldon2007": {
        "type": "article", "authors": "Sheldon, Roger A.", "title": "The E Factor: fifteen years on",
        "container": "Green Chemistry", "year": "2007", "volume": "9", "issue": "12", "pages": "1273-1283",
        "doi": "10.1039/b713736m", "note": "E-Faktor = Abfallmasse / Produktmasse"},
    "constable2002": {
        "type": "article", "authors": "Constable, David J. C.; Curzons, Alan D.; Cunningham, Virginia L.",
        "title": "Metrics to 'green' chemistry -- which are the best?", "container": "Green Chemistry", "year": "2002",
        "volume": "4", "issue": "6", "pages": "521-527", "doi": "10.1039/b206169b",
        "note": "Reaktionsmasseneffizienz RME"},
    "jimenez2011": {
        "type": "article", "authors": "Jimenez-Gonzalez, Concepción; Ponder, Celia S.; Broxterman, Quirinus B.; "
        "Manley, Julie B.", "title": "Using the Right Green Yardstick: Why Process Mass Intensity Is Used in the "
        "Pharmaceutical Industry To Drive More Sustainable Processes", "container": "Organic Process Research & "
        "Development", "year": "2011", "volume": "15", "issue": "4", "pages": "912-917", "doi": "10.1021/op200097d",
        "note": "Prozessmassenintensität PMI"},
    "kell1975": {
        "type": "article", "authors": "Kell, George S.", "title": "Density, Thermal Expansivity, and Compressibility of "
        "Liquid Water from 0° to 150 °C: Correlations and Tables for Atmospheric Pressure and Saturation Reviewed and "
        "Expressed on 1968 Temperature Scale", "container": "Journal of Chemical and Engineering Data", "year": "1975",
        "volume": "20", "issue": "1", "pages": "97-105", "doi": "10.1021/je60064a005",
        "note": "Dichte von Wasser bei 1 atm (für pKw(T) nach Bandura & Lvov)"},
    # ------------------------------------------------------------------ Moleküldesigner (Namen und Schätzungen)
    "favre2014": {"short": "IUPAC 2013 (Favre & Powell)",
        "type": "book", "authors": "Favre, Henri A.; Powell, Warren H.",
        "title": "Nomenclature of Organic Chemistry: IUPAC Recommendations and Preferred Names 2013",
        "container": "Royal Society of Chemistry", "year": "2014", "doi": "10.1039/9781849733069",
        "note": "Substitutionsnomenklatur, Wahl der Stammverbindung P-44, Bezifferung P-31.1.4, Lokanten P-14"},
    "joback1987": {"short": "Joback & Reid 1987",
        "type": "article", "authors": "Joback, K. G.; Reid, R. C.",
        "title": "Estimation of pure-component properties from group-contributions",
        "container": "Chemical Engineering Communications", "year": "1987", "volume": "57", "issue": "1-6",
        "pages": "233-243", "doi": "10.1080/00986448708960487"},
    "joback_wiki": {"short": "Joback-Tabelle (Wikipedia)",
        "type": "web", "authors": "Wikipedia contributors", "title": "Joback method",
        "container": "Wikipedia, The Free Encyclopedia", "year": "2026",
        "url": "https://en.wikipedia.org/wiki/Joback_method", "accessed": "2026-11-17", "licence": "CC BY-SA 4.0",
        "note": "Gruppenbeiträge nach Joback & Reid 1987 in tabellarischer Wiedergabe; geprüft am Beispiel Aceton"},
    "domalski1993": {"short": "Domalski & Hearing 1993",
        "type": "article", "authors": "Domalski, Eugene S.; Hearing, Elizabeth D.",
        "title": "Estimation of the Thermodynamic Properties of C-H-N-O-S-Halogen Compounds at 298.15 K",
        "container": "Journal of Physical and Chemical Reference Data", "year": "1993", "volume": "22", "issue": "4",
        "pages": "805-1159", "doi": "10.1063/1.555927", "url": "https://srd.nist.gov/jpcrdreprint/1.555927.pdf",
        "accessed": "2026-11-17",
        "note": "Benson-Gruppenwerte Gasphase (Table 2, S. 816-819), je Gruppe an einer Beispielverbindung der "
                "Tables 4-21 nachgerechnet"},
    "benson1969": {"short": "Benson et al. 1969",
        "type": "article", "authors": "Benson, Sidney W.; Cruickshank, F. R.; Golden, D. M.; Haugen, Gilbert R.; "
        "O'Neal, H. E.; Rodgers, A. S.; Shaw, Robert; Walsh, R.",
        "title": "Additivity rules for the estimation of thermochemical properties", "container": "Chemical Reviews",
        "year": "1969", "volume": "69", "issue": "3", "pages": "279-324", "doi": "10.1021/cr60259a002",
        "note": "Gruppenadditivitätsverfahren (Begründung); Zahlenwerte stammen aus Domalski & Hearing 1993"},
    "ertl2000": {"short": "Ertl et al. 2000 (TPSA)",
        "type": "article", "authors": "Ertl, Peter; Rohde, Bernhard; Selzer, Paul",
        "title": "Fast calculation of molecular polar surface area as a sum of fragment-based contributions and its "
        "application to the prediction of drug transport properties", "container": "Journal of Medicinal Chemistry",
        "year": "2000", "volume": "43", "issue": "20", "pages": "3714-3717", "doi": "10.1021/jm000942e"},
    "sander2015": {"short": "Sander et al. 2015 (DataWarrior)",
        "type": "article", "authors": "Sander, Thomas; Freyss, Joel; von Korff, Modest; Rufener, Christian",
        "title": "DataWarrior: An Open-Source Program For Chemistry Aware Data Visualization And Analysis",
        "container": "Journal of Chemical Information and Modeling", "year": "2015", "volume": "55", "issue": "2",
        "pages": "460-473", "doi": "10.1021/ci500588j",
        "note": "Inkrementverfahren für clogP und logS, wie in OpenChemLib umgesetzt"},
    "clayden2012": {
        "type": "book", "authors": "Clayden, J.; Greeves, N.; Warren, S.", "title": "Organic Chemistry",
        "container": "Oxford University Press", "year": "2012", "edition": "2. Auflage"},
    # ------------------------------------------------------------------ Redox, Säure–Base (Phase 5)
    "karen2016": {"short": "Karen et al. 2016 (IUPAC)",
        "type": "article", "authors": "Karen, Pavel; McArdle, Patrick; Takats, Josef",
        "title": "Comprehensive definition of oxidation state (IUPAC Recommendations 2016)",
        "container": "Pure and Applied Chemistry", "year": "2016", "volume": "88", "issue": "8", "pages": "831-839",
        "doi": "10.1515/pac-2015-1204",
        "note": "Ionenzerlegung: Bindungselektronen gehen an den elektronegativeren Partner"},
    "redbook2005": {"short": "IUPAC Red Book 2005",
        "type": "book", "authors": "Connelly, N. G.; Damhus, T.; Hartshorn, R. M.; Hutton, A. T.",
        "title": "Nomenclature of Inorganic Chemistry – IUPAC Recommendations 2005", "container": "RSC Publishing",
        "year": "2005", "note": "Hrsg.; Oxidationszahl"},
}


def ref(key: str, note: str = "") -> dict:
    """Kopie eines Quellendatensatzes; ``note`` (z. B. Kapitelthema) wird angehängt."""
    r = dict(REFS[key])
    if note:
        r["note"] = (r["note"] + "; " if r.get("note") else "") + note
    return r


# Herkunft jeder Konstante in units.CONSTANTS: (Quelle, exakt?, Hinweis)
CONSTANT_SOURCES: dict[str, tuple[str, bool, str]] = {
    "pi": ("bronstein", True, "mathematische Konstante"),
    "e": ("bronstein", True, "mathematische Konstante"),
    "g0": ("codata2022", True, "Normfallbeschleunigung, festgelegter Wert (3. CGPM 1901)"),
    "c0": ("si2019", True, "definierende Konstante"),
    "hP": ("si2019", True, "definierende Konstante"),
    "hbar": ("codata2022", True, "aus h abgeleitet, exakt"),
    "kB": ("si2019", True, "definierende Konstante"),
    "NA": ("si2019", True, "definierende Konstante"),
    "Rgas": ("codata2022", True, "R = N_A·k, exakt"),
    "G_grav": ("codata2022", False, "relative Standardunsicherheit 2,2·10⁻⁵"),
    "eps0": ("codata2022", False, "Messwert, Unsicherheit 0,0000000014·10⁻¹²"),
    "mu0": ("codata2022", False, "Messwert, Unsicherheit 0,00000000020·10⁻⁶"),
    "q_e": ("si2019", True, "definierende Konstante"),
    "m_e": ("codata2022", False, "Unsicherheit 0,0000000028·10⁻³¹ kg"),
    "m_p": ("codata2022", False, "Unsicherheit 0,00000000052·10⁻²⁷ kg"),
    "m_n": ("codata2022", False, "Unsicherheit 0,00000000085·10⁻²⁷ kg"),
    "m_u": ("codata2022", False, "atomare Masseneinheit, Unsicherheit 0,00000000052·10⁻²⁷ kg"),
    "sigma_SB": ("codata2022", True, "aus definierenden Konstanten, exakt"),
    "F_c": ("codata2022", True, "F = N_A·e, exakt"),
    "T0": ("si2019", True, "Celsius-Temperatur t = T − 273,15 K"),
    "p_n": ("codata2022", True, "Standardatmosphäre, festgelegter Wert"),
    "p_std": ("greenbook", True, "Standarddruck p° = 1 bar (IUPAC)"),
    "c_std": ("greenbook", True, "Standardkonzentration c° = 1 mol/dm³"),
    "b_std": ("greenbook", True, "Standardmolalität b° = 1 mol/kg"),
    "MPa1": ("si2019", True, "1 MPa = 1 N/mm², Einheitenumrechnung"),
    "b_wien": ("codata2022", True, "Wiensche Verschiebungskonstante, aus definierenden Konstanten"),
}
