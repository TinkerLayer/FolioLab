"""Baut die mitgelieferte Referenzbibliothek aus der Open-Specy-Sammlung (gemessene FTIR-Spektren vieler Labore).

    python tools/build_openspecy.py <nobaseline.rds> [<ziel> = ftir/data/openspecy]

Quelle: Open Specy reference library (Cowger et al.), OSF doi:10.17605/OSF.IO/X7DPZ, Datei nobaseline.rds. Die Spektren
stammen von vielen Gruppen (RRUFF, Primpke et al. 2018, FLOPP, AWI-Plattenleser-Datenbank, Kimmel Center, SWGDRUG …);
jeder Eintrag behält seine Herkunft, Messart und Lizenz. Teile stehen unter CC BY-NC (nur nicht-kommerziell).

Schritte:
  1. nur FTIR (kein Raman/NIR); ohne Bodenproben (USDA), Reflexionsmessungen (Form anders als ATR/Transmission),
     AWI-Transmission (dicke Partikel, oft gesättigt) und NIST-Webbook-Spektren (Nutzungsbedingungen)
  2. Namen vereinheitlichen (Kunststoffe, Fasern, Naturstoffe mit deutschen Namen; Minerale, Chemikalien und
     Wirkstoffe mit dem Namen der Quelle), Kategorie festlegen
  3. je Stoff: Ausreisser (falsch beschriftet, leer, verrauscht) entfernen, Doppelte zusammenfassen, höchstens
     MAX_PER_GROUP möglichst verschiedene Spektren behalten
  4. für die Suche vorbereiten (wie library.prep) und als schreibgeschützte Bibliothek speichern
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from rds import RVec, read_rds  # noqa: E402

from ftir import quality as QA  # noqa: E402
from ftir.library import GRID, prep  # noqa: E402

MAX_PER_GROUP = 10
MIN_POINTS = 500                # mindestens 1000 cm⁻¹ im Bereich 400–4000
MIN_SNR = 8.0
OUTLIER_R = 0.5                 # Korrelation mit dem typischen Spektrum des Stoffs
DUP_R = 0.985                   # darüber gelten zwei Spektren als gleich

OPEN_SPECY = ("Open Specy reference library: Cowger W. et al. (2021), Microplastic spectral classification needs an "
              "open source community: Open Specy to the rescue!, Anal. Chem. 93, 7543–7548, "
              "doi:10.1021/acs.analchem.1c00123; Cowger W. et al. (2025), Open Specy 1.0, Anal. Chem., "
              "doi:10.1021/acs.analchem.5c00962 (Angaben nicht geprüft); Daten: OSF doi:10.17605/OSF.IO/X7DPZ")
NV = " (Angaben nicht geprüft / not verified)"     # Zitat ohne geprüfte Einzelheiten: unsichere Angaben weggelassen

# Herkunft: Kurzname, Zitat, Standardkategorie für nicht zugeordnete Namen
ORGS = {
    "rruff": ("RRUFF", "Lafuente B., Downs R.T., Yang H., Stone N. (2015): The power of databases: the RRUFF project. "
                       "In: Highlights in Mineralogical Crystallography, De Gruyter, 1–30; rruff.info", "Füllstoff/Mineral"),
    "primpke et al. 2018": ("Primpke 2018", "Primpke S., Wirth M., Lorenz C., Gerdts G. (2018): Reference database design "
                                            "for the automated analysis of microplastic samples based on Fourier "
                                            "transform infrared (FTIR) spectroscopy. Anal. Bioanal. Chem. 410, 5131–5141, "
                                            "doi:10.1007/s00216-018-1156-x", None),
    "win cowger and sebastian primpke": ("AWI 2024", "Cowger W., Primpke S. et al.: AWI spectra via Open Specy" + NV,
                                         None),
    "flopp, de frond et al. 2021": ("FLOPP", "De Frond H., Rubinovitz R., Rochman C.M. (2021): µATR-FTIR spectral "
                                             "libraries of plastic particles (FLOPP and FLOPP-e) for the analysis of "
                                             "microplastics. Anal. Chem. 93, 15878–15885, doi:10.1021/acs.analchem.1c02549",
                                    None),
    "microplastix": ("Microplastix", "Lenz R. et al. (2023): Microplastix SpecDB v1.0.2, Zenodo, "
                                     "doi:10.5281/zenodo.10149551", None),
    "julia, davidson": ("Davidson 2023", "Davidson J. et al. (2023): Polymer characterization of submerged plastic "
                                         "litter from Lake Tahoe, Dryad, doi:10.5061/dryad.866t1g1vj", None),
    "kimmel_center": ("Kimmel Center", "Kimmel Center for Archaeological Science, Weizmann Institute of Science: "
                                       "IR spectra library" + NV, None),
    "swgdrug": ("SWGDRUG", "Scientific Working Group for the Analysis of Seized Drugs (SWGDRUG): IR library, "
                           "swgdrug.org" + NV, "Wirkstoff"),
    "pslc_database": ("PSLC", "Polymer Science Learning Center (PSLC): spectra collection" + NV, "Chemikalie"),
    "chabuka et al. 2020": ("Chabuka 2020", "Chabuka B.K., Kalivas J.H. (2020), Applied Spectroscopy" + NV, None),
    "aline carvalho": ("Carvalho", "A. Carvalho, über Open Specy", None),
    "argiro adamopoulou": ("Adamopoulou", "A. Adamopoulou, über Open Specy", None),
    "rachel kozloski": ("Kozloski", "R. Kozloski, über Open Specy", None),
    "national renewable energy laboratory": ("NREL", "National Renewable Energy Laboratory, über Open Specy", None),
    "suja sukumaran, thermo fisher scientific": ("Thermo Fisher", "S. Sukumaran, Thermo Fisher Scientific, über Open Specy",
                                                 None),
    "hpu polymer kit 1.0": ("HPU-Kit", "HPU Polymer Kit 1.0, über Open Specy", None),
    "archaeometrielabor": ("Archäometrielabor", "archaeometrielabor.com, über Open Specy", "Naturstoff"),
}
DROP_ORGS = {"nist", "usda", "nist chem web book", "moore institute for plastic pollution research"}

K, E, F, N, L = "Kunststoff", "Elastomer", "Faser", "Naturstoff", "Lack/Beschichtung"
# Stoff-ID -> (deutsch, englisch, Kategorie)
CANON = {
    "pe": ("Polyethylen (PE)", "Polyethylene (PE)", K),
    "pe-ld": ("Polyethylen niedriger Dichte (PE-LD)", "Low-density polyethylene (LDPE)", K),
    "pe-lld": ("Lineares Polyethylen niedriger Dichte (PE-LLD)", "Linear low-density polyethylene (LLDPE)", K),
    "pe-md": ("Polyethylen mittlerer Dichte (PE-MD)", "Medium-density polyethylene (MDPE)", K),
    "pe-hd": ("Polyethylen hoher Dichte (PE-HD)", "High-density polyethylene (HDPE)", K),
    "pe-uld": ("Polyethylen sehr niedriger Dichte (PE-ULD)", "Ultra-low-density polyethylene (ULDPE)", K),
    "pe-wax": ("Polyethylenwachs", "Polyethylene wax", K),
    "pe-ox": ("Polyethylen(wachs), oxidiert", "Polyethylene (wax), oxidized", K),
    "pe-c": ("Polyethylen, chloriert (PE-C)", "Chlorinated polyethylene", K),
    "pp": ("Polypropylen (PP)", "Polypropylene (PP)", K),
    "ps": ("Polystyrol (PS)", "Polystyrene (PS)", K),
    "eps": ("Polystyrol, expandiert (EPS)", "Expanded polystyrene (EPS)", K),
    "pet": ("Polyethylenterephthalat (PET)", "Poly(ethylene terephthalate) (PET)", K),
    "petg": ("PET-G (glykolmodifiziert)", "PETG (glycol-modified PET)", K),
    "pbt": ("Polybutylenterephthalat (PBT)", "Poly(butylene terephthalate) (PBT)", K),
    "pest": ("Polyester (Faser, allgemein)", "Polyester (fibre, unspecified)", K),
    "copes": ("Copolyester", "Copolyester", K),
    "pees": ("Polyetherester", "Polyether ester", K),
    "pla": ("Polylactid (PLA)", "Polylactide (PLA)", K),
    "pc": ("Polycarbonat (PC)", "Polycarbonate (PC)", K),
    "pmma": ("Polymethylmethacrylat (PMMA)", "Poly(methyl methacrylate) (PMMA)", K),
    "pema": ("Polyethylmethacrylat", "Poly(ethyl methacrylate)", K),
    "pbma": ("Poly(n-butylmethacrylat)", "Poly(n-butyl methacrylate)", K),
    "pibma": ("Poly(isobutylmethacrylat)", "Poly(isobutyl methacrylate)", K),
    "bma-ibma": ("Butyl-/Isobutylmethacrylat-Copolymer", "Butyl/isobutyl methacrylate copolymer", K),
    "phema": ("Poly(2-hydroxyethylmethacrylat)", "Poly(2-hydroxyethyl methacrylate)", K),
    "pmeth": ("Polymethacrylat (allgemein)", "Polymethacrylate (unspecified)", K),
    "acrylic": ("Acrylharz (allgemein)", "Acrylic resin (unspecified)", K),
    "acr-an": ("Acrylat-Acrylnitril-Gemisch", "Acrylate/acrylonitrile mixture", K),
    "paa": ("Polyacrylsäure", "Poly(acrylic acid)", K),
    "pan": ("Acrylfaser (Polyacrylnitril)", "Acrylic fibre (polyacrylonitrile)", F),
    "pvc": ("Polyvinylchlorid (PVC)", "Poly(vinyl chloride) (PVC)", K),
    "pvc-p": ("PVC mit Weichmacher (PVC-P)", "Plasticized PVC", K),
    "pvc-x": ("PVC, carboxyliert", "Carboxylated PVC", K),
    "pvdc": ("Vinylidenchlorid-Vinylchlorid-Copolymer", "Vinylidene chloride/vinyl chloride copolymer", K),
    "vc-va": ("Vinylchlorid-Vinylacetat-Hydroxypropylacrylat", "Vinyl chloride/vinyl acetate/hydroxypropyl acrylate", K),
    "pvdf": ("Polyvinylidenfluorid (PVDF)", "Poly(vinylidene fluoride) (PVDF)", K),
    "ptfe": ("Polytetrafluorethylen (PTFE)", "Polytetrafluoroethylene (PTFE)", K),
    "pa": ("Polyamid (allgemein)", "Polyamide (unspecified)", K),
    "pa6": ("Polyamid 6 (PA 6)", "Polyamide 6 (PA 6)", K),
    "pa66": ("Polyamid 6.6 (PA 66)", "Polyamide 6.6 (PA 66)", K),
    "pa6-66": ("Polyamid 6 / 6.6", "Polyamide 6 / 6.6", K),
    "pa11": ("Polyamid 11 (PA 11)", "Polyamide 11 (PA 11)", K),
    "pa12": ("Polyamid 12 (PA 12)", "Polyamide 12 (PA 12)", K),
    "pa612": ("Polyamid 6.12 (PA 612)", "Polyamide 6.12 (PA 612)", K),
    "pa69": ("Polyamid 6.9 (PA 69)", "Polyamide 6.9 (PA 69)", K),
    "copa": ("Copolyamid", "Copolyamide", K),
    "aramid": ("Aramid", "Aramid", K),
    "abs": ("Acrylnitril-Butadien-Styrol (ABS)", "Acrylonitrile butadiene styrene (ABS)", K),
    "san": ("Styrol-Acrylnitril (SAN)", "Styrene acrylonitrile (SAN)", K),
    "sma": ("Styrol-Maleinsäureanhydrid (SMA)", "Styrene maleic anhydride (SMA)", K),
    "sma-me": ("SMA, teilweise Methylester", "SMA, partial methyl ester", K),
    "saa": ("Styrol-Allylalkohol", "Styrene allyl alcohol", K),
    "sbc": ("Styrol-Blockcopolymer (SBC)", "Styrene block copolymer (SBC)", E),
    "seb": ("Styrol-Ethylen-Butylen (SEBS)", "Styrene ethylene butylene (SEBS)", E),
    "sis": ("Styrol-Isopren", "Styrene isoprene", E),
    "nbr": ("Nitrilkautschuk (NBR)", "Nitrile rubber (NBR)", E),
    "epdm": ("Ethylen-Propylen-Dien-Kautschuk (EPDM)", "EPDM rubber", E),
    "epm": ("Ethylen-Propylen-Copolymer", "Ethylene propylene copolymer", E),
    "nr": ("Naturkautschuk (NR)", "Natural rubber (NR)", E),
    "rubber": ("Gummi (allgemein)", "Rubber (unspecified)", E),
    "tire": ("Reifengummi", "Tyre rubber", E),
    "cr": ("Chloroprenkautschuk (CR)", "Chloroprene rubber (CR)", E),
    "si": ("Silikon (PDMS)", "Silicone (PDMS)", E),
    "tpe": ("Thermoplastisches Elastomer (TPE)", "Thermoplastic elastomer (TPE)", E),
    "pu": ("Polyurethan (PU)", "Polyurethane (PU)", K),
    "pu-ester": ("Polyesterurethan", "Polyester urethane", K),
    "pu-ether": ("Polyetherurethan", "Polyether urethane", K),
    "eva": ("Ethylen-Vinylacetat (EVA)", "Ethylene vinyl acetate (EVA)", K),
    "vae": ("Vinylacetat-Ethylen (VAE)", "Vinyl acetate ethylene (VAE)", K),
    "evoh": ("Ethylen-Vinylalkohol (EVOH)", "Ethylene vinyl alcohol (EVOH)", K),
    "eaa": ("Ethylen-Acrylsäure (EAA)", "Ethylene acrylic acid (EAA)", K),
    "emaa": ("Ethylen-Methacrylsäure (EMAA)", "Ethylene methacrylic acid (EMAA)", K),
    "pvoh": ("Polyvinylalkohol (PVA)", "Poly(vinyl alcohol) (PVA)", K),
    "pvac": ("Polyvinylacetat (PVAc)", "Poly(vinyl acetate) (PVAc)", K),
    "pvb": ("Polyvinylbutyral (PVB)", "Poly(vinyl butyral) (PVB)", K),
    "pvp": ("Polyvinylpyrrolidon (PVP)", "Polyvinylpyrrolidone (PVP)", K),
    "peo": ("Polyethylenoxid / Polyethylenglykol", "Poly(ethylene oxide) / poly(ethylene glycol)", K),
    "pom": ("Polyoxymethylen (POM)", "Polyoxymethylene (POM)", K),
    "peek": ("Polyetheretherketon (PEEK)", "Polyether ether ketone (PEEK)", K),
    "pesu": ("Polyethersulfon (PESU)", "Polyether sulfone (PESU)", K),
    "psu": ("Polysulfon (PSU)", "Polysulfone (PSU)", K),
    "ppsu": ("Polyphenylsulfon (PPSU)", "Polyphenylsulfone (PPSU)", K),
    "ppe": ("Polyphenylenether (PPE)", "Poly(phenylene ether) (PPE)", K),
    "pmp": ("Poly(4-methyl-1-penten) (PMP)", "Poly(4-methyl-1-pentene) (PMP)", K),
    "pcl": ("Polycaprolacton (PCL)", "Polycaprolactone (PCL)", K),
    "phb": ("Polyhydroxybuttersäure (PHB)", "Polyhydroxybutyrate (PHB)", K),
    "pdap": ("Polydiallylisophthalat", "Poly(diallyl isophthalate)", K),
    "mvema": ("Methylvinylether-Maleinsäure(anhydrid)", "Methyl vinyl ether maleic acid (anhydride)", K),
    "alkyd": ("Alkydharz", "Alkyd resin", L),
    "epoxy": ("Epoxidharz", "Epoxy resin", L),
    "pes-ep": ("Polyester-Epoxid", "Polyester epoxide", L),
    "ca": ("Celluloseacetat (CA)", "Cellulose acetate (CA)", K),
    "cta": ("Cellulosetriacetat (CTA)", "Cellulose triacetate (CTA)", K),
    "cab": ("Celluloseacetobutyrat (CAB)", "Cellulose acetate butyrate (CAB)", K),
    "cp": ("Cellulosepropionat (CP)", "Cellulose propionate (CP)", K),
    "ec": ("Ethylcellulose", "Ethyl cellulose", K),
    "hec": ("Hydroxyethylcellulose", "Hydroxyethyl cellulose", K),
    "hpc": ("Hydroxypropylcellulose", "Hydroxypropyl cellulose", K),
    "hpmc": ("Hydroxypropylmethylcellulose", "Hydroxypropyl methyl cellulose", K),
    "mc": ("Methylcellulose (Tylose)", "Methyl cellulose", K),
    "cellulose": ("Cellulose", "Cellulose", N),
    "paper": ("Papier / Karton", "Paper / cardboard", N),
    "cotton": ("Baumwolle", "Cotton", F),
    "cellfib": ("Cellulosefaser", "Cellulose fibre", F),
    "viscose": ("Viskose", "Viscose", F),
    "flax": ("Flachs / Leinen", "Flax / linen", F),
    "hemp": ("Hanf", "Hemp", F),
    "jute": ("Jute", "Jute", F),
    "kapok": ("Kapok", "Kapok", F),
    "nettle": ("Brennnesselfaser", "Nettle fibre", F),
    "grass": ("Grasfaser", "Grass fibre", F),
    "poplar": ("Pappelflaum", "Poplar down", F),
    "wool": ("Wolle", "Wool", F),
    "silk": ("Seide", "Silk", F),
    "hair": ("Tierhaar / Fell", "Animal hair / fur", F),
    "chitin": ("Chitin", "Chitin", N),
    "keratin": ("Keratin", "Keratin", N),
    "collagen": ("Kollagen", "Collagen", N),
    "protein": ("Protein", "Protein", N),
    "glue": ("Glutinleim (Haut-, Knochen-, Fischleim)", "Animal glue (hide, bone, fish)", N),
    "starch": ("Stärke", "Starch", N),
    "wood": ("Holz", "Wood", N),
    "bark": ("Rinde", "Bark", N),
    "beeswax": ("Bienenwachs", "Beeswax", N),
    "paraffin": ("Paraffin", "Paraffin", N),
    "amber": ("Bernstein", "Amber", N),
    "bitumen": ("Bitumen / Asphalt", "Bitumen / asphalt", N),
    "coal": ("Kohle", "Coal", N),
    "algae": ("Algen", "Algae", N),
    "leaf": ("Blatt (Pflanze)", "Leaf (plant)", N),
    "cigfilter": ("Zigarettenfilter", "Cigarette filter", K),
    "bone": ("Knochen", "Bone", N),
    "dentin": ("Dentin / Zahnschmelz", "Dentine / enamel", N),
    "humic": ("Huminsäure", "Humic acid", N),
    "fulvic": ("Fulvosäure", "Fulvic acid", N),
    "resin": ("Naturharz (Dammar, Mastix, Weihrauch …)", "Natural resin (dammar, mastic, frankincense …)", N),
    "gum": ("Pflanzengummi", "Plant gum", N),
    "egg": ("Eiweiss", "Egg white", N),
    "pollen": ("Pollen", "Pollen", N),
    "phytolith": ("Phytolith (Pflanzenkieselsäure)", "Phytolith (plant silica)", N),
    "ash": ("Pflanzenasche", "Plant ash", N),
    "date": ("Dattel", "Date (fruit)", N),
    "agave": ("Agavenfaser", "Agave fibre", F),
}

# Abkürzungen und Schreibweisen -> Stoff-ID (Schlüssel: klein, nur Buchstaben/Ziffern/Leerzeichen)
ALIAS = {
    "pe": "pe", "polyethylene": "pe", "polyethylen": "pe", "ldpe": "pe-ld", "low density polyethylen": "pe-ld",
    "low density polyethylene": "pe-ld", "polyethylene low density": "pe-ld", "lldpe": "pe-lld",
    "polyethylene low density linear": "pe-lld", "mdpe": "pe-md", "hdpe": "pe-hd", "polyethylene high density": "pe-hd",
    "uldpe": "pe-uld", "polyethylene wax": "pe-wax", "polyethylene oxidized": "pe-ox", "polyethylene wax oxidized": "pe-ox",
    "polyethylene chlorinated": "pe-c", "polyethylene foamed": "pe",
    "pp": "pp", "polypropylene": "pp", "polypropylene isotactic": "pp",
    "ps": "ps", "polystyrene": "ps", "styrofoam": "eps", "eps": "eps", "polystyrene expanded": "eps", "ps eps": "ps",
    "pet": "pet", "poly ethylene terephthalate": "pet", "polyethylene terephthalate": "pet", "polyethylene terephtalate": "pet",
    "polytehylene terephthalate": "pet", "polytehylene terephthalate amorphous": "pet", "polyethylenterephthalat": "pet",
    "poly ethylene terepthalate": "pet", "polyesterterpthalate": "pet", "pet pest": "pet",
    "pet g": "petg", "pbt": "pbt", "poly butylene terephthalate": "pbt", "polybuthylene terephthalate": "pbt",
    "pes": "pest", "pest": "pest", "polyester": "pest", "copolyester": "copes", "polyetherester": "pees",
    "pla": "pla", "polylactic acid": "pla", "polyactide": "pla",
    "pc": "pc", "polycarbonate": "pc",
    "pmma": "pmma", "poly methyl methacrylate": "pmma", "polymethyl methacrylate": "pmma",
    "poly ethyl methacrylate": "pema", "poly n butyl methacrylate": "pbma", "poly isobutyl methacrylate": "pibma",
    "butyl methacrylate isobutyl methacrolate": "bma-ibma", "poly 2 hydroxyethyl methacrylate": "phema",
    "poly methacrylate": "pmeth", "acrylic": "acrylic", "mixture of ucar acrylate and acrylonitrile": "acr-an",
    "poly acrylic acid": "paa",
    "pvc": "pvc", "poly vinyl chloride": "pvc", "polyvinylchloride": "pvc", "polyvinylchloride with plasticizer": "pvc-p",
    "poly vinyl chloride carboxylated": "pvc-x", "vinylidene chloride vinyl chloride": "pvdc",
    "vinyl chloride vinyl acetate hydroxypropyl acrylate": "vc-va",
    "pvdf": "pvdf", "poly vinylidene fluoride": "pvdf", "ptfe": "ptfe", "poly tetrafluoroethylene": "ptfe",
    "polytetrafluoroethylene": "ptfe", "plumbers tape sealing putty": "ptfe",
    "pa": "pa", "nylon": "pa", "polyamide": "pa", "pa6": "pa6", "nylon 6": "pa6", "polyamide 6": "pa6", "nylon6": "pa6",
    "nyon6": "pa6", "pa66": "pa66", "nylon 6 6": "pa66", "polyamide 66": "pa66", "polymaide 66": "pa66",
    "nylon6 6": "pa66", "pa6 pa66": "pa6-66", "nylon6 and nylon6 6": "pa6-66", "polyamide 6 p6 6": "pa6-66",
    "nylon 11": "pa11", "nylon 12": "pa12", "nylon 6 12": "pa612", "nylon 6 9": "pa69", "nylon 6 3 t": "pa",
    "copolyamide": "copa", "aramid": "aramid",
    "abs": "abs", "san": "san", "styrene maleic anhydride": "sma", "styrene maleic anhydride partial methyl ester": "sma-me",
    "styrene allyl alcohol": "saa", "sbc": "sbc", "seb": "seb", "styrene isoprene": "sis",
    "nitrile": "nbr", "nitrile rubber": "nbr", "acrylonitrile butadiene": "nbr", "polu butadiene acrylonitrile": "nbr",
    "sealing ring epdm": "epdm", "poly ethylene propylene diene": "epdm", "ethylene propylene": "epm",
    "natural rubber": "nr", "rubber": "rubber", "r": "rubber", "crumb rubber from used tires": "tire", "cr": "cr",
    "silicone rubber": "si", "silicone seal reactor": "si", "pdms": "si", "silicone pdms": "si", "sr": "si",
    "thermoplastic elastomere": "tpe",
    "pu": "pu", "polyurethane": "pu", "polyesterurethane": "pu-ester", "polyetherurethane": "pu-ether",
    "polyether urethane with additives": "pu-ether",
    "eva": "eva", "ethylene vinyl acetate": "eva", "ethylene vinyl actetate copolymer": "eva", "peva": "eva",
    "poly vinyl acetate ethylene": "vae", "ethylene vinyl alcohol": "evoh", "ethylene acrylic acid": "eaa", "eaa": "eaa",
    "ethylene methacrylic acid": "emaa",
    "pva": "pvoh", "poly vinyl alcohol": "pvoh", "polyvinyl alcohol": "pvoh", "mowiol": "pvoh",
    "poly vinyl acetate": "pvac", "poly vinyl butyral": "pvb", "polyvinylpyrrolidone": "pvp",
    "poly ethylene glycol": "peo", "poly ethylene oxide": "peo",
    "polyacetal": "pom", "polyoxymethylene": "pom", "peek": "peek", "polyetheretherketone": "peek",
    "poly p phenylene ether sulphone": "pesu", "polysulfone": "psu", "polyphenylsulfone": "ppsu",
    "poly 2 6 dimethyl p phenylene oxide": "ppe", "poly 4 methyl 1 pentene": "pmp", "polycaprolactone": "pcl",
    "polyhydroxybutyric acid": "phb", "poly diallyl isophthalate": "pdap",
    "methyl vinyl ether maleic acid": "mvema", "methyl vinyl ether maleic anhydride": "mvema",
    "alkyd varnish": "alkyd", "alkyd resin": "alkyd", "epoxide resin": "epoxy", "polyester epoxide": "pes-ep",
    "ca": "ca", "cellulose acetate": "ca", "acetate": "ca", "cellulose triacetate": "cta",
    "cellulose acetate butyrate": "cab", "cellulose propionate": "cp", "ethyl cellulose": "ec",
    "hydroxyethyl cellulose": "hec", "hydroxypropyl cellulose": "hpc", "klucel mf in ethanol": "hpc",
    "hydroxypropyl methyl cellulose": "hpmc", "methyl cellulose": "mc", "tylose": "mc", "tylose2": "mc",
    "cellulose": "cellulose", "cellulose wipe": "cellulose", "papercup cellulosic": "paper", "cardboard cellulose": "paper",
    "cotton": "cotton", "c": "cellfib", "viscose": "viscose", "flax": "flax", "linen": "flax", "roasted flax": "flax",
    "hemp": "hemp", "jute": "jute", "kapok": "kapok", "urtica dioica l conar fibra": "nettle", "grass": "grass",
    "turf": "pe", "poplar down": "poplar", "wool": "wool", "camel hair": "hair", "silk": "silk",
    "chitin": "chitin", "keratin": "keratin", "protein": "protein", "starch": "starch",
    "cigarette filter": "cigfilter", "coal": "coal", "anthracite": "coal", "paraffin": "paraffin",
    "paraffin wax": "paraffin", "leaf plant": "leaf", "polyvinylidene fluoride": "pvdf", "polyamide 6 p6 6": "pa6-66",
    "egg white": "egg", "humic acid": "humic", "humic": "humic", "fulvic acid": "fulvic", "gum": "gum",
    "dammar damar gum": "resin", "mastix mastic": "resin", "drachenblut dragons blood resin": "resin",
    "res 11 boswellia sacra": "resin", "res 9 pisticia lentiscus": "resin", "resin": "resin",
    "bone fossil": "bone", "bone": "bone", "dentin": "dentin", "enamel": "dentin", "recent pollen2 olea": "pollen",
    "dor phytolith": "phytolith", "silica": "phytolith", "date fresh 2007 balk": "date", "fibers agave americana": "agave",
    "polyester for blocks": "pest", "polyesther from ts 1861 block": "pest", "jet": "coal", "egyptian blue": None,
    "res": "resin", "cornea porcine treated sample": "collagen", "mgo": None,
}
ALIAS = {k: v for k, v in ALIAS.items() if v}
# Kimmel Center: Gesteine und Tonminerale -> Mineral, Salze/Reagenzien -> Chemikalie
ROCKS = ("basalt", "granite", "gabbro", "diorite", "rhyolite", "schist", "slate", "marble", "obsidian", "pumice",
         "tuff", "loess", "clay", "pozzolana", "kurkar", "flint", "jasper", "terra rossa", "glass", "zeolite", "chalk",
         "marl", "smectite", "bentonite", "illite", "opal", "steatite", "serpentine", "cave wall", "patina", "plaster",
         "galena", "silicate", "montmorillonite", "apatite")
SALTS = ("sodium", "potassium", "ammonium", "calcium", "magnesium", "barium", "silver", "copper", "manganese",
         "mgo", "oxide", "nitrate", "sulphate", "sulfate", "carbonate", "phosphate", "hydroxid", "chloride",
         "fluoride", "oxalate", "citrate", "urea", "uric acid", "guanine")
# Teilwörter (in dieser Reihenfolge geprüft) für Beschreibungen wie "fibre polypropylene dyed", "fur yak"
CONTAINS = [
    ("honeycomb", "beeswax"), ("broodcomb", "beeswax"), ("beeswax", "beeswax"), ("fur ", "hair"), ("wool", "wool"),
    ("silk", "silk"), ("cashmere", "wool"), ("collagen", "collagen"), ("keratin", "keratin"), ("chitin", "chitin"),
    ("parchment", "collagen"), ("glue", "glue"), ("isinglass", "glue"), ("algae", "algae"), ("amber", "amber"),
    ("copal", "amber"), ("bitumen", "bitumen"), ("asphalt", "bitumen"), ("wood", "wood"), ("bark", "bark"),
    ("cotton", "cotton"), ("viscose", "viscose"), ("hemp", "hemp"), ("flax", "flax"), ("linen", "flax"),
    ("jute", "jute"), ("kapok", "kapok"), ("tire", "tire"), ("rubber", "rubber"), ("sealing ring gardena", "rubber"),
]

DROP_NAMES = {"other plastic", "plastic", "empty well", "atmouspheric background", "phillye2m1 sediment", "tpcldpe",
              "black bike handle cover foam", "grignard", "sealant form a gasket", "pe with silicate inorganic",
              "pe silicate bio", "polyethylene with acryloid and pthalocyanine blue"}


def norm(s: str) -> str:
    s = s.lower().replace("_", " ").replace(".", " ").replace("/", " ")
    s = re.sub(r"[^a-z0-9äöüß ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def pretty(s: str) -> str:
    s = re.sub(r"\s+", " ", s.replace("_", " ")).strip(" -;,")
    return s[:1].upper() + s[1:] if s else s


def canon(raw: str, org: str, mclass: str | None, plastic: str | None):
    """-> (gruppe, name_de, name_en, kategorie, variante) oder None"""
    s = (raw or "").strip().lstrip("*").strip()
    s = re.sub(r"__r\d{6}.*$", "", s)                        # RRUFF-Kennung
    s = re.sub(r"\s*\(lot\s*#.*$", "", s, flags=re.I)         # SWGDRUG-Charge
    s = re.sub(r"^\((insitu )?\d+\)\s*", "", s)              # Microplastix "(07) pet"
    if org == "hpu polymer kit 1.0":
        s = re.sub(r"\.\d+$", "", s)                         # HPU "pvc.2"
    if not s or norm(s) in DROP_NAMES or not re.search(r"[a-z]{3}", s.lower()) and norm(s) not in ALIAS:
        return None
    variant = ""
    if org == "kimmel_center":
        # "albite (wards, 72)", "anorthite-wards-45-v-1000-11-kbr", "5490humic" -> Grundname + Zusatz
        s = re.sub(r"^\d+(?=[a-z])", "", s)
        mk = re.match(r"^(.*?)(\s*\(.*|\s*-\s*ward.*|-carolina.*|-kbr|\s+\d.*|\s+(?:synthetic|unheated|heated).*)$", s)
        if mk and len(mk.group(1).strip()) >= 3:
            s = mk.group(1).strip()
            variant = re.sub(r"\s+", " ", re.sub(r"[()|]", " ", mk.group(2))).strip(" -;,")
        if re.search(r"\d{3,}|\b(shy|kesw|wia|nz\d|cor\d)|\b[a-z]+\d+[a-z]*\b", s.lower()):
            return None
        # Schreibweisen wie bei RRUFF, damit gleiche Minerale zusammenkommen
        low = s.lower()
        for a, b in (("cacite", "calcite"), ("whewelite", "whewellite"), ("weddelite", "weddellite"),
                     ("analcite", "analcime"), ("barite", "baryte"), ("celestite", "celestine"),
                     ("montmorrilonite", "montmorillonite"), ("hydrocerrussite", "hydrocerussite"),
                     ("sulfur", "sulphur"), ("cristobolite", "cristobalite"), ("mellilite", "melilite")):
            if low.startswith(a):
                s = b + s[len(a):]
                break
    m = re.match(r"^([a-z]+|\*?[a-z]+)\s*\d+\.\s*(.*)$", s)  # FLOPP "pe 16. white art foam", "c1. black fiber"
    m2 = re.match(r"^([a-z]+)(\d+)\.\s*(.*)$", s)
    if org.startswith("flopp"):
        if m2:
            code, variant = m2.group(1), m2.group(3)
        elif m:
            code, variant = m.group(1), m.group(2)
        else:
            return None
        if code == "acrylic":
            return _mk("pan", variant)
        s = code
    if org == "national renewable energy laboratory":
        parts = s.split("-")
        s, variant = parts[0], " ".join(parts[1:])
    if org.startswith("primpke") and s.lower().startswith("fibre "):
        s, variant = s[6:], "Faser"
    if org.startswith("primpke") and s.lower().startswith("sealing ring") and "epdm" not in s:
        variant = s[13:]
    key = norm(s)
    if key in DROP_NAMES:
        return None
    if key in ALIAS:
        return _mk(ALIAS[key], variant)
    for word, gid in CONTAINS:
        if word in key + " ":
            # Zusatz nur, wenn er mehr sagt als der Stoffname ("fur yak" -> "Yak", "cotton" -> keiner)
            rest = " ".join(w for w in key.split() if w not in word.split() and w not in ("fibre", "fiber", "fur"))
            return _mk(gid, ", ".join(x for x in (rest, variant) if x))
    for p in ("fibre ", "fiber "):
        if key.startswith(p) and key[len(p):] in ALIAS:
            return _mk(ALIAS[key[len(p):]], "Faser")
    # längster bekannter Anfang ("polyamide 6 not stretched" -> PA 6, Zusatz "not stretched")
    words = key.split()
    if org not in ("swgdrug", "pslc_database", "rruff"):
        for k in range(len(words) - 1, 0, -1):
            head = " ".join(words[:k])
            if head in ALIAS and len(head) >= 4:
                return _mk(ALIAS[head], " ".join(words[k:]) + (f", {variant}" if variant else ""))
    # nicht zugeordnet: Name der Quelle, Kategorie nach Herkunft
    name = pretty(s)
    cat = ORGS.get(org, ("", "", None))[2]
    if cat is None:
        if org in ("kimmel_center", "suja sukumaran, thermo fisher scientific"):
            if key.endswith(("ite", "ite s")) or any(w in key for w in ROCKS):
                cat = "Füllstoff/Mineral"
            elif any(w in key for w in SALTS):
                cat = "Chemikalie"
            elif mclass == "mineral":
                cat = "Füllstoff/Mineral"
            else:
                cat = N
        elif plastic == "plastic":
            cat = K
        elif mclass == "mineral":
            cat = "Füllstoff/Mineral"
        else:
            cat = N
    if "prussian blue" in key or "egyptian blue" in key or "ochre" in key or "indigo" in key:
        cat = "Pigment"
    gid = "x:" + re.sub(r"[^a-z0-9]", "", key)
    return gid, name, name, cat, pretty(variant) if variant else ""


def _mk(gid, variant=""):
    de, en, cat = CANON[gid]
    return gid, de, en, cat, pretty(variant) if variant else ""


MODE = {"atr": "ATR", "transmission": "Transmission", "transmittance": "Transmission"}   # "absorbance" ist keine Messart


def unit_column(cols: dict) -> str | None:
    """Spalte der Metadaten mit der Intensitätseinheit, falls die Quelle eine hat (z. B. "intensity_units")."""
    for c in cols:
        lc = str(c).lower()
        if "unit" in lc and ("intens" in lc or lc.startswith("y")):
            return c
    return None


def stored_unit(text) -> str | None:
    """Intensitätseinheit aus den Metadaten -> "A", "T", "R" oder None (fehlt oder unbekannt).
    Nur die Intensitätseinheit zählt, nicht die Messart: eine Transmissionsmessung kann als Absorbanz gespeichert sein."""
    t = str(text or "").lower()
    if "absorb" in t:
        return "A"
    if "transmit" in t or "transmis" in t:
        return "T"
    if "reflect" in t:
        return "R"
    return None


def main(src: str, dst: str):
    o = read_rds(src)
    wn = np.asarray(o.get("wavenumber"), float)
    spectra = o.get("spectra")
    md = o.get("metadata")
    cols = {n: (v.data if isinstance(v, RVec) else v) for n, v in zip(md.names, md)}
    get = lambda c, i: (cols[c][i] if c in cols else None)  # noqa: E731
    n_all = len(spectra)
    rows = []
    why = Counter()
    ucol = unit_column(cols)
    units = Counter()
    print("Intensitätseinheit: " + (f"Spalte „{ucol}“" if ucol else
                                     "keine Spalte in den Metadaten – alle Spektren werden als Absorbanz behandelt"))
    for i in range(n_all):
        st, org, mode = get("spectrum_type", i), get("organization", i) or "", (get("instrument_mode", i) or "").lower()
        if st != "ftir":
            why["kein FTIR"] += 1
            continue
        if org in DROP_ORGS or org not in ORGS:
            why["Quelle ausgeschlossen"] += 1
            continue
        if mode.startswith("reflect") or (org == "win cowger and sebastian primpke" and mode == "transmission"):
            why["Messart ausgeschlossen"] += 1
            continue
        c = canon(get("spectrum_identity", i), org, get("material_class", i), get("plastic_or_not", i))
        if c is None:
            why["Name unbrauchbar"] += 1
            continue
        y = np.asarray(spectra[i], float)
        v = np.isfinite(y)
        if v.sum() < 50:
            why["leer"] += 1
            continue
        # Gespeicherte Intensitätseinheit beachten (T/R werden in prep in Absorbanz bzw. log(1/R) umgerechnet,
        # als Bruchteil gespeicherte Werte vorher in %); ohne Angabe als Absorbanz behandeln und das vermerken
        su = stored_unit(get(ucol, i)) if ucol else None
        yu = su or "A"
        yv = y[v] * 100 if yu in ("T", "R") and np.nanmax(y[v]) <= 1.5 else y[v]
        try:
            g = prep(wn[v], yv, yu)
        except ValueError:
            why["zu kurz"] += 1
            continue
        if np.isfinite(g).sum() < MIN_POINTS:
            why["zu kurz"] += 1
            continue
        q = QA.assess(wn[v], yv, yu)
        units[su or "nicht angegeben"] += 1
        if q["snr"] is not None and q["snr"] < MIN_SNR:
            why["verrauscht"] += 1
            continue
        lic = (get("license", i) or "").upper().replace("CC BY-NC", "CC BY-NC")
        rows.append({"g": g, "gid": c[0], "de": c[1], "en": c[2], "cat": c[3], "variant": c[4], "org": org,
                     "mode": MODE.get(mode, ""), "license": lic, "snr": q["snr"] or 0, "yunit_src": su or ""})
    print(f"{n_all} Spektren gelesen, {len(rows)} geeignet; ausgeschlossen: {dict(why)}")
    print(f"Intensitätseinheiten der geeigneten Spektren: {dict(units)}")

    groups = defaultdict(list)
    for r in rows:
        groups[r["gid"]].append(r)
    # je Stoff ein Name (RRUFF schreibt "allanite-(ce)" und "allanitece") und eine Kategorie (Mineral, wenn RRUFF ihn führt)
    for gid, rs in groups.items():
        if gid.startswith("x:"):
            best = max((r["de"] for r in rs), key=lambda n: (sum(not c.isalnum() for c in n), -len(n)))
            cat = "Füllstoff/Mineral" if any(r["org"] == "rruff" for r in rs) else Counter(r["cat"] for r in rs).most_common(1)[0][0]
            for r in rs:
                r["de"] = r["en"] = best
                r["cat"] = cat
    kept = []
    dropped_out, dropped_dup = 0, 0
    lost = []
    for gid, rs in groups.items():
        G = np.array([r["g"] for r in rs], dtype=np.float64)
        Z = _zscore(G)
        if len(rs) >= 4:
            R = Z @ Z.T
            med = int(np.argmax(np.nanmean(R, 1)))
            ok = R[med] >= OUTLIER_R
            dropped_out += int((~ok).sum())
            if (~ok).sum() >= 5:
                lost.append((gid, len(rs), int((~ok).sum()), dict(Counter(r["org"][:12] for r, k in zip(rs, ok) if not k))))
            rs = [r for r, k in zip(rs, ok) if k]
            Z = Z[ok]
        # möglichst verschiedene Vertreter: mit dem typischsten beginnen, dann jeweils den unähnlichsten hinzunehmen
        R = Z @ Z.T
        order = [int(np.argmax(np.nanmean(R, 1)))]
        while len(order) < min(MAX_PER_GROUP, len(rs)):
            mx = np.max(R[order], 0)
            mx[order] = 9
            j = int(np.argmin(mx))
            if mx[j] >= DUP_R:
                break
            order.append(j)
        dropped_dup += len(rs) - len(order)
        kept += [rs[j] for j in order]
    print(f"{len(kept)} Einträge in {len(groups)} Stoffen; Ausreisser {dropped_out}, doppelt/überzählig {dropped_dup}")
    for x in sorted(lost, key=lambda t: -t[2]):
        print("   Ausreisser:", x)

    kept.sort(key=lambda r: (r["cat"], r["de"].lower(), r["variant"]))
    entries, G = [], []
    seen = Counter()
    for r in kept:
        seen[r["gid"]] += 1
        short, cite, _ = ORGS[r["org"]]
        name = r["de"] + (f" – {r['variant']}" if r["variant"] else "")
        name_en = r["en"] + (f" – {r['variant']}" if r["variant"] else "")
        e = {"id": f"os{len(entries):05d}", "name": name, "name_en": name_en, "group": r["gid"], "category": r["cat"],
             "cas": "", "formula": "", "source": f"{short}: {cite}",
             "comment": "; ".join(x for x in (r["mode"], f"Lizenz {r['license']}" if r["license"] else "") if x),
             "license": r["license"] or "", "mode": r["mode"], "origin": short, "yunit": "A",
             # Einheit laut Quelle ("" = nicht angegeben, als Absorbanz behandelt); der Suchvektor ist immer Absorbanz
             "yunit_src": r["yunit_src"]}
        g = r["g"]
        v = np.where(np.isfinite(g))[0]
        e["xmin"], e["xmax"] = float(GRID[v[0]]), float(GRID[v[-1]])
        entries.append(e)
        G.append(g)
    G = np.array(G, dtype=np.float16)
    out = Path(dst)
    out.mkdir(parents=True, exist_ok=True)
    meta = {"format": "folio-ftir-bibliothek/1", "id": "openspecy", "readonly": True,
            "name": "Referenzen, gemessen (Open Specy)", "name_en": "Measured references (Open Specy)",
            "description": "Gemessene FTIR-Spektren (ATR und Transmission) aus der Open-Specy-Sammlung: Kunststoffe, "
                           "Elastomere, Fasern, Naturstoffe, Minerale, Chemikalien, Wirkstoffe. Je Eintrag Herkunft, "
                           "Messart und Lizenz; Teile nur für nicht-kommerzielle Nutzung (CC BY-NC).",
            "source": OPEN_SPECY, "created": "2026-11-16", "entries": entries,
            "counts": dict(Counter(e["category"] for e in entries)),
            "yunit_note": ("Intensitätseinheit aus der Metadatenspalte „" + ucol + "“; ohne Angabe als Absorbanz behandelt"
                           if ucol else "Quelle ohne Intensitätseinheit; alle Spektren als Absorbanz behandelt"),
            "yunit_counts": dict(Counter(e["yunit_src"] or "nicht angegeben" for e in entries)),
            "origins": {v[0]: v[1] for v in ORGS.values()}}
    np.savez_compressed(out / "data.npz", G=G)
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=0), encoding="utf-8")
    print("Kategorien:", meta["counts"])
    print("Datei:", round((out / "data.npz").stat().st_size / 1e6, 1), "MB +",
          round((out / "meta.json").stat().st_size / 1e6, 1), "MB")


def _zscore(G):
    """Zeilen standardisieren (NaN -> 0), so dass Z @ Z.T / n die Korrelation im gemeinsamen Bereich annähert."""
    Z = np.where(np.isfinite(G), G, np.nan)
    mu = np.nanmean(Z, 1, keepdims=True)
    sd = np.nanstd(Z, 1, keepdims=True)
    sd[sd == 0] = 1
    Z = np.nan_to_num((Z - mu) / sd)
    Z /= np.sqrt((Z * Z).sum(1, keepdims=True)) + 1e-12
    return Z


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else str(HERE.parent / "ftir" / "data" / "openspecy"))
