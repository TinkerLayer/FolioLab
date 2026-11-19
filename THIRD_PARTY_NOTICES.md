# Third-party notices

Folio Lab's own code and documentation are under the MIT licence ([LICENSE](LICENSE)). This file lists everything in
the repository, or installed by it, that comes from someone else: software, reference data and literature values.
For each item it gives the source, the terms under which it is included, and how to cite it.

**Data policy.** The repository contains only data that may be redistributed:

- data in the public domain or under CC0;
- data under CC BY, with attribution given below;
- individual numerical values taken from the literature with a citation (facts are not protected by copyright).

Data that is free to *use* but may not be *redistributed*, or whose terms are unclear, is not in the repository.
[`tools/fetch_optional_data.py`](tools/fetch_optional_data.py) downloads it from the original publisher onto your
computer and builds the files Folio Lab reads (see [Optional data](#optional-data-not-in-the-repository)). Every
module works without it.

The licence checks below were made at the original source in November 2026. They are a good-faith reading of the
published terms, not legal advice. If you find a problem, please open an issue (see [SECURITY.md](SECURITY.md) for
anything sensitive).

## Software

### Included in the repository

| Component | Version | Licence | Where | Use |
|---|---|---|---|---|
| [OpenChemLib JS](https://github.com/cheminfo/openchemlib-js) | 9.26.0, unmodified | BSD-3-Clause, © 2015–2017 cheminfo | `modules/elementrechner/elementrechner/static/vendor/openchemlib/` (licence text included there) | 2D structure drawings and the molecule editor |

The upstream LICENSE file of OpenChemLib contains an unfilled `{{ project }}` placeholder. It is kept unchanged, as
shipped by the project.

### Installed by `setup.ps1` / `npm install` (not in the repository)

| Component | Version | Licence |
|---|---|---|
| [Node.js](https://nodejs.org/) | portable build, current LTS at install time | MIT and others (see its LICENSE) |
| [Monaco Editor](https://github.com/microsoft/monaco-editor) (`monaco-editor`) | 0.52.2 | MIT |
| [PDF.js](https://github.com/mozilla/pdf.js) (`pdfjs-dist`) | 4.10.38 | Apache-2.0 |
| [MiKTeX](https://miktex.org/) and the LaTeX packages it installs on demand | current at install time | LPPL and others, per package |

### Python packages (installed with pip from `requirements*.txt`)

| Package | Licence | Required? |
|---|---|---|
| numpy | BSD-3-Clause | yes |
| matplotlib (also supplies the DejaVu fonts used in figures) | matplotlib licence (PSF-based); DejaVu fonts: Bitstream Vera licence | yes |
| Pillow | MIT-CMU (HPND) | yes |
| openpyxl | MIT | yes |
| reportlab | BSD-3-Clause | yes |
| xlrd | BSD-3-Clause | optional (.xls files) |
| pyarrow | Apache-2.0 | optional (Parquet files) |
| pyngb | MIT | optional (NETZSCH .ngb files) |
| scipy | BSD-3-Clause | tests only (independent reference values) |

Numerical constants taken from published algorithms are listed with the method on the module's methods page (for
example the Gauss–Kronrod 7/15 nodes and weights as published with QUADPACK, public domain, in the Rechner).

## Reference data in the repository

The data files record their own provenance: `_source`, `_built`, `_from` and, per value, the source key. Citation
keys refer to `sdk/python/labcalc/sources.py` and `modules/elementrechner/elementrechner/refs.py`. The modules add
these citations to a report automatically whenever a value from the source is used.

### Chemistry and physics (`sdk/python/labcalc/data/`)

| File | Content | Source | Terms | Cite |
|---|---|---|---|---|
| `atomic_weights.json` | standard atomic weights | CIAAW, *Standard Atomic Weights 2024*, ciaaw.org | internationally adopted reference values (facts); no report text or tables are copied | CIAAW 2024; Prohaska et al. 2022, Pure Appl. Chem. 94, 573, doi:10.1515/pac-2019-0603 |
| `isotopes.json` | atomic masses, half-lives, decay modes | AME2020 and NUBASE2020 data files (amdc.impcas.ac.cn) | CC BY 3.0 (the Chinese Physics C papers that publish the tables) | Wang et al. 2021, Chinese Phys. C 45, 030003, doi:10.1088/1674-1137/abddaf; Kondev et al. 2021, Chinese Phys. C 45, 030001, doi:10.1088/1674-1137/abddae |
| `isotopes.json` | isotopic abundances | CIAAW, *Isotopic Compositions of the Elements 2024* | reference values (facts) | CIAAW 2024 |
| `elements.json` | element properties (electronegativity, radii, melting points, …) | PubChem Periodic Table (NCBI/NLM) | US government work, not subject to copyright in the US | Kim et al. 2021, Chem. Teach. Int. 3, 57, doi:10.1515/cti-2020-0006 |
| `molecules.json` | structures, names, formulas, identifiers of the compound collection | PubChem PUG REST (computed properties); German names, synonyms and QIDs from Wikidata | NCBI places no restrictions on the data it computes; Wikidata CC0. CAS numbers are used as identifiers only | Kim et al. 2025, Nucleic Acids Res. 53, D1516, doi:10.1093/nar/gkae1059; Wikidata |
| `physprops.json` | measured physical properties | PubChem PUG View, **only** these sources: HSDB (NLM), DOE PAC, OSHA, NIOSH, ICSC | HSDB, DOE, OSHA and NIOSH: US government works, public domain. **ICSC: CC BY 4.0, © ILO and WHO**: values extracted and converted to the units Folio Lab uses; each value keeps its source and original text | per value, e.g. "International Chemical Safety Cards (ICSC), ILO/WHO, via PubChem" |
| `thermo.json` | ΔfH°, ΔfG°, S°, Cp° at 298.15 K | CODATA Key Values (151 species); NBS Tables as digitised by NIST (9,050 species) | CODATA: internationally agreed reference values (facts). NBS digitisation (NIST mds2-2124): NIST public data, 17 U.S.C. §105, with a royalty-free grant to redistribute | Cox, Wagman & Medvedev 1989; Wagman et al. 1982, J. Phys. Chem. Ref. Data 11, Suppl. 2; Reed 2020, doi:10.18434/M32124 |
| `benson_groups.json` | Benson group values, gas phase (C/H and C/H/O groups only) | Domalski & Hearing 1993 | individual numerical values with citation | J. Phys. Chem. Ref. Data 22, 805, doi:10.1063/1.555927 |
| `indicators.json` | acid–base indicators: transition range, colours | Harris, *Quantitative Chemical Analysis*, 9th ed. 2016 | individual values with citation; colour swatches are display aids only | Harris 2016. **Not yet checked against the printed edition.** |
| `labcalc/joback.py` (table in code) | Joback group contributions | Joback & Reid 1987; transcribed from the Wikipedia article "Joback method" | the numbers are the published parameters of Joback & Reid. The Wikipedia text is CC BY-SA 4.0: attribution "Wikipedia contributors, *Joback method*, en.wikipedia.org, CC BY-SA 4.0" | Joback & Reid 1987, Chem. Eng. Commun. 57, 233, doi:10.1080/00986448708960487. **Checked only against the worked acetone example.** |
| `labcalc/radii.py` (table in code) | effective ionic radii, a selection | Shannon 1976 | individual values with citation | Acta Cryst. A 32, 751, doi:10.1107/S0567739476001551. **Not yet checked against the original table**; the result shows this note |
| `labcalc/bonds.py`, `labcalc/vapor.py` (tables in code) | mean bond enthalpies and lengths (34); cryoscopic and ebullioscopic constants (8 solvents); Antoine coefficients (9 substances) | Atkins, *Physical Chemistry*, 11th ed.; Antoine coefficients from the original sources named per entry (as listed in the NIST Chemistry WebBook) | individual values with citation | per entry. **Not yet checked against the originals** |
| `labcalc/units.py`, `sources.py` | physical constants | CODATA 2022 (NIST), SI Brochure | reference values | Mohr et al. 2025, Rev. Mod. Phys. 97, 025002, doi:10.1103/RevModPhys.97.025002 |

Literature values that are marked "not yet checked" are listed again in [docs/VALIDATION.md](docs/VALIDATION.md).
Check them before you rely on them in a publication.

### FTIR reference spectra (`modules/ftir/ftir/data/openspecy/`)

196 measured spectra from the [Open Specy](https://osf.io/x7dpz) collection: only the sources whose original
licence allows redistribution.

| Source | Spectra | Licence at the source | Cite |
|---|---|---|---|
| Microplastix SpecDB v1.0.2 (Lenz et al. 2023) | 41 | CC BY 4.0 (Zenodo) | doi:10.5281/zenodo.10149551 |
| Davidson et al. 2023, plastic litter from Lake Tahoe | 29 | CC0 1.0 (Dryad) | doi:10.5061/dryad.866t1g1vj |
| Primpke et al. 2018, Anal. Bioanal. Chem. | 126 | CC BY 4.0 (article and electronic supplementary material) | doi:10.1007/s00216-018-1156-x |

The spectra were taken from Open Specy's processed library file (`nobaseline.rds`; Open Specy: Cowger et al. 2021,
Anal. Chem. 93, 7543–7548, doi:10.1021/acs.analchem.1c00123, and Cowger et al. 2025, Anal. Chem.,
doi:10.1021/acs.analchem.5c00962, details of the 2025 paper not verified). Folio Lab then resampled them to a
2 cm⁻¹ grid (400–4000 cm⁻¹), treated them as absorbance (the processed file states no intensity unit), normalised
them and merged duplicates (`modules/ftir/tools/build_openspecy.py`). These are changes in the sense of CC BY. Each
entry keeps its source and licence, and a report that uses a spectrum cites both its source and Open Specy. The
remaining 1,486 Open Specy spectra are optional (see below).

The FTIR **model library** and the band table (`ftir/refdata.py`, `labcalc/irbands.py`) contain band positions from
the literature (e.g. Socrates, *Infrared and Raman Characteristic Group Frequencies*, 3rd ed.). The spectra are
computed by Folio Lab from those positions. They are labelled "modelled" everywhere and are not measured spectra.

### TGA, tensile test, other modules

- `modules/tga/tga/data/referenzen.json`: decomposition steps (onset, peak, mass loss, residue) of reference
  materials. The values come from the text and tables of the publications named in each entry. Folio Lab computes the
  DTG curves from these values and labels them as modelled.
- `sdk/python/labcalc/data/materials.json` (shared materials database of the Rechner, the Zugversuch and the
  Werkstoffe module): property
  values of 136 materials. Each value names its source: a handbook or textbook (e.g. CRC Handbook, Callister, Kittel,
  Ashby, Daniel & Ishai, Mark), a standard with product form, or a manufacturer data sheet or database entry with URL
  and access date (the 88 former Zugversuch rows). Individual values are given with citation; the selection and
  arrangement are Folio Lab's own work. Values not yet compared against their source are marked.
- `modules/zugversuch/data/specimens.json`: specimen dimensions from the standards named in each entry.
- `modules/werkstoffe/werk/data/phases.json`: 38 crystal structures (space group, cell, atom positions) from
  Wyckoff, *Crystal Structures*, 2nd ed., Wiley 1963. Structural data are facts; the selection is Folio Lab's own.
- `modules/werkstoffe/werk/formfactors.py`: Cromer–Mann form-factor coefficients after *International Tables for
  Crystallography* Vol. C, Table 6.1.1.4 (individual numerical constants, cited; transcribed and marked as not
  checked against the original).
- `modules/werkstoffe/werk/data/diagrams.json`: key points (temperatures, compositions) of five binary phase
  diagrams from Callister & Rethwisch, Murray & McAlister 1984 and Subramanian & Perepezko 1993, cited per diagram.
  The lines between them are drawn by Folio Lab and labelled *schematisch*.
- `modules/werkstoffe/werk/data/gitter.json` (lattice model): allotropes and transition temperatures, lattice
  parameters and expansion coefficients, Debye temperatures, vacancy formation enthalpies, interstitial sites and
  miscible pairs of 17 base elements, from the CRC Handbook, Wyckoff 1963, Basinski et al. 1955, Kittel, Ehrhart 1991,
  Porter & Easterling and Massalski 1990; covalent radii from Cordero et al. 2008. Individual numerical facts, each
  cited in the data and in reports, written after the named source and marked as not checked against the original;
  the selection is Folio Lab's own.
- X-ray tube wavelengths: standard values (Bearden 1967) as used by instrument software.
- XRD file readers: written from published format descriptions (PANalytical XRDML schema, Bruker documentation, the
  xylib format notes for RAW1.01). No code from xylib or other readers is included.
- CIF files from the Crystallography Open Database (CC0) can be opened by the user; none are included.
- No ICDD/PDF reference patterns and no hardness conversion tables (ISO 18265, ASTM E140) are included; the hardness
  tool converts only with a table file the user makes from their own copy.
- `server/templates/`: report templates and sample images. These are Folio Lab's own work; the images are generated
  by `scripts/make-sample-images.js`.

## Optional data (not in the repository)

These parts are downloaded from the original publisher by `python tools/fetch_optional_data.py <part>` (or `all`).
They are built on your computer and are listed in `.gitignore`. **Do not commit or redistribute them.** By running the
script you accept the terms of each source. Several allow non-commercial use only, so check them before using
Folio Lab commercially.

| Part | Content | Terms (why it is not in the repository) | Cite |
|---|---|---|---|
| `pka` | IUPAC Digitized pKa Dataset v2.4 | CC BY-NC 4.0 (non-commercial) | Zheng & Lafontant-Joseph, Zenodo, doi:10.5281/zenodo.7236452; Zheng, Lafontant-Joseph & Green 2026, RSC Adv. 16, 21397, doi:10.1039/D6RA02418A |
| `srd46` | NIST SRD 46 v8.0, critically selected stability constants | NIST Standard Reference Data are copyrighted (15 U.S.C. §290e); the dataset README grants broad use. Because the two statements conflict, it is not redistributed | NIST SRD 46, doi:10.18434/M32154 (after Martell & Smith, *Critical Stability Constants*) |
| `asd` | NIST Atomic Spectra Database (SRD 78): ionisation energies | Standard Reference Data, "all rights reserved" | Kramida, Ralchenko, Reader & NIST ASD Team, doi:10.18434/T4W30F |
| `burcat` | Burcat/Goos/Ruscic thermochemical database (3,062 species, NASA-7 polynomials, ATcT values) | free with citation; sale and copying into commercial publications need the author's written agreement | Goos, Burcat & Ruscic, *Extended Third Millennium … Thermochemical Database*, burcat.technion.ac.il |
| `mp` | Materials Project: computed density, bulk and shear modulus, band gap and space group of 38 elements and compounds | CC BY 4.0, so it could be redistributed; it is not in the repository because the API needs each user's own free key (`MP_API_KEY`) and the data change with database versions | Jain et al. 2013, APL Mater. 1, 011002, doi:10.1063/1.4812323; de Jong et al. 2015, Sci. Data 2, 150009, doi:10.1038/sdata.2015.9 |
| `openspecy` | 1,486 further Open Specy spectra: RRUFF, SWGDRUG, Kimmel Center, FLOPP, AWI 2024, Kozloski, PSLC, Thermo Fisher, NREL and others | per source: CC BY-NC, "personal educational purposes" (RRUFF), "all rights reserved" (SWGDRUG), or no licence stated | Cowger et al. 2021 and 2025 and the source of each spectrum (kept in the data) |

Without these parts:

- **pKa values:** `srd46` and `pka` are the main sources. Without them only the HSDB values in `physprops.json`
  remain, and buffer and titration calculations for many acids are unavailable.
- **Complex formation and speciation** need `srd46`.
- **Ionisation-energy series** need `asd`. `elements.json` still lists the first ionisation energy of each element
  (PubChem).
- **Thermochemistry** uses CODATA and NBS values at 298.15 K. The temperature-dependent Cp(T) model, flame
  temperatures and the comparison of Benson estimates with tabulated values need `burcat`.
- **The FTIR search** has 196 instead of 1,682 measured spectra.

The tests that need a part are skipped and name it (see [docs/VALIDATION.md](docs/VALIDATION.md)).

## Not included

- Real measurement files are never part of the repository (`*.flps` and other raw data). The tests use synthetic
  data with known answers.
- Values from NIST-JANAF appear only as individual comparison numbers inside tests. The tables themselves are not
  included.
