# TGA

Evaluation of thermogravimetric measurements (TGA, TG/DTG) in Folio Lab. Its scope follows common instrument software
(NETZSCH Proteus, TA TRIOS/Universal Analysis, METTLER STARe) and open evaluation programs (kinetics as in
pICNIK/pkynetics, Fraser–Suzuki separation as in mixchar, quick analysis as in tga_data_analysis): open a run, process
it, determine steps and characteristic values, calculate the composition, **narrow down the material from its
decomposition behaviour** (library search as in KnowItAll or NETZSCH Identify), compare runs, kinetics from several
heating rates, take results into a report. Runs locally and needs only numpy and matplotlib (openpyxl for TRIOS
`.xlsx`). The methods are re-implemented in numpy and documented with their literature in the source code; no code
from the programs named above.

**Methods and validation:** every computation, its formulas, defaults, references and the tests that check it are
described in [`docs/methods/tga.md`](../../docs/methods/tga.md). Read it before reporting a number from this module.

The app starts in German. Below, buttons and menus are given with their English label and the German label in
parentheses on first mention. Menu entries and the contents of the tabs are currently German only; they are quoted
in German with an English gloss.

## About the library

There is no open collection of measured TGA curves; the commercial counterparts (NETZSCH Identify, METTLER reference
library) are licensed. Folio Lab therefore ships:

* **Model library (read-only):** 71 entries (26 plastics, 21 minerals/fillers, 11 biomass, 6 elastomers,
  6 calibration standards, 1 carbon) with 102 steps from 67 literature sources. Each entry gives its steps (onset,
  DTG peak, end, mass loss), residue, atmosphere, heating rate and its source (structured, with DOI). The values are
  taken from the text and tables of the sources, not from figures. The curves are **calculated** from them as
  Fraser–Suzuki peaks; **they are not measured curves.** The interface, the figure label ("· Modell"), the citation
  and the methods text each say so. Hits from this library are indications. To rebuild:
  `python tools/build_refs.py` writes `tga/data/referenzen.json`.
* **Own libraries:** any number under `outputs/tga/bibliotheken/<id>/` (`meta.json`, measured curves in
  `data.npz`), readable and editable by hand, export/import as JSON. Two ways to fill them, each with a source:
  - *Aktuellen Lauf als Referenz …* (current run as reference): the measured curve is stored.
  - *Referenz aus Stufenwerten …* (reference from step values): type in steps from a publication (onset, peak,
    end, loss, residue, atmosphere, heating rate); the curve is calculated as in the model library.
  Without a selected library the entry goes to "Eigene Referenzen" (own references), which is created if needed.

## Workflow

1. **Folio Lab home page ▸ Analyses ▸ TGA.** Drag files in or use **File** (*Datei*) ▸ *Öffnen …* (open; several
   files, shown as tabs at the top). Read are generic text/CSV (comma, semicolon, tab; decimal comma; header lines
   with sample mass, heating rate, gas, crucible) and the text exports of NETZSCH Proteus (ASCII, `##` header),
   TA Universal Analysis, TA TRIOS (CSV/XLSX; several sheets with a time column are joined into one run, one segment
   per sheet), METTLER STARe, PerkinElmer Pyris and
   Shimadzu. Columns are recognised (time, sample/program temperature, mass in mg or %, DTG, gas, flow, segment,
   heat flow); if that fails, *Öffnen mit Spaltenzuordnung …* (open with column mapping) opens a dialog. Segments
   (dynamic, isothermal, cooling, gas switch) are recognised. The **Examples** (*Beispiele*) menu loads synthetic
   runs (marked "synthetisch").
2. **Processing** (tab **Edit**, *Bearbeiten*): reference mass (sample mass, at a temperature, after a time, or a
   value by hand), cut, select segments, temperature correction, buoyancy correction (blank subtraction is in the
   **Compare** tab), smoothing (Savitzky–Golay), resampling, mg ↔ %. The
   steps form a **protocol** that is always applied to the original (interface, export and report agree), can be
   saved/loaded as JSON and applied to all runs.
3. **Steps** (tab **Steps**, *Stufen*): automatic from the DTG, limits can be moved by hand. For each step the
   extrapolated onset and end temperature per ISO 11358-1 (tangent at the inflection point), midpoint, DTG peak,
   maximum rate, loss in % and mg.
4. **Values** (tab **Values**, *Kennwerte*): T at 1/2/5/10/50 % loss, residue at the end and at a chosen
   temperature, isothermal loss. Collapsed below:
   - **DSC / heat flow evaluation** (*DSC / Wärmestrom auswerten …*; only if the file has a heat flow): peaks in
     chosen ranges with a linear baseline, area and ΔH per sample mass (endothermic positive), onset/endset; glass
     transition per ISO 11357-2 (half step height, Δcp from the heating rate). Units mW, W/g, µV (then area only).
   - **Evolved gas analysis (TGA-FTIR)** (*Gasanalyse (TGA-FTIR) …*): load a series of gas spectra (CSV matrix
     time × wavenumber or JCAMP-DX with several blocks), Gram–Schmidt curve (after de Haseth & Isenhour 1977),
     chemigram of a band; a click in the curve selects the time, *In FTIR öffnen* (open in FTIR) passes the
     spectrum (background subtracted) to the FTIR search (outside Folio Lab as a `.jdx` download).
5. **Composition** (*Zusammensetzung*): templates ASTM E1131 (moisture, polymer, carbon after switching to air,
   ash) and ASTM D7582 (proximate analysis), free limits; **stoichiometry** (content from one step, e.g.
   CaCO₃ = loss / 0.4397; Mg(OH)₂, Al(OH)₃, gypsum, calcium oxalate, PVC → HCl …, calculated from the IUPAC atomic
   weights); **calcium oxalate check** (12.33 / 19.17 / 30.12 %) and two-point temperature calibration.
6. **Search** (tab **Search**, *Suche*): curve comparison of the DTG (cosine, reference shiftable by ±shift K) plus
   comparison of the steps (peak temperature, loss, residue), hit score 0–100, principle after Schindler et al. 2017
   (doi:10.1007/s10973-017-6208-5). A different atmosphere or heating rate is flagged; filter by category.
   *Im Lauf einblenden* (overlay on the run) lays the reference over the run.
7. **Mixture** (*Mischung*): DTG of the sample as a non-negative sum of 2–3 references; the weights are **mass
   fractions**, mass without loss in the measured range remains as "inert".
8. **Compare** (*Vergleich*): overlay runs (TG/DTG, normalised), step table across all runs, mean ± s for
   replicates.
9. **Kinetics** (*Kinetik*; ≥ 3 heating rates, one step): Friedman, Ozawa–Flynn–Wall (ASTM E1641), KAS, Starink,
   Vyazovkin with Eₐ(α) and confidence interval, Kissinger, Coats–Redfern, master plot, compensation effect,
   lifetime per ASTM E1877. Warnings following the ICTAC recommendations (too few or too close heating rates, Eₐ
   strongly dependent on α …).
10. **Separation** (*Trennung*): fit overlapping DTG steps as Fraser–Suzuki peaks; biomass template (hemicellulose,
    cellulose, lignin).
11. **Equations** (tab **Equations**, *Gleichungen*), see below.
12. File ▸ *Exportieren (Ordner mit Abbildung, Stufen, Protokoll)* (export) writes to `outputs/tga/<run>/`:
    `tg_dtg.png`, `lauf.csv`, `stufen.csv`, `protokoll.txt`. **To report …** (*Zum Bericht …*) sends figures (TG +
    DTG with steps, search, mixture, comparison, composition, kinetics, separation), tables, values (`\labval`, e.g.
    `step1-loss`, `t5`, `residue`), data (CSV for pgfplots), sources and text blocks (methods, results). Search and
    mixture results are stored with their curves, so that **Refresh** in the report editor does not depend on later
    changes to the libraries.

View: x = temperature or time, DTG on the right axis on/off, the mouse wheel zooms, a double click shows everything.

## Overview, environments, sharing

* The TGA opens on the **Overview** (*Übersicht*): project index, the environments (runs, steps per run, best hit,
  kinetics) with "**+ Environment**" (*+ Umgebung*) and the module's own shares, linked to the environment they come
  from. A click opens an environment; loaded runs, protocol and steps stay there across a restart.
* Inside an environment the tabs Edit, Steps, Values and Search are shown (from two runs on also Compare); the
  others are under **More ▾** (*Mehr ▾*). Detection settings (**Detection**, *Erkennung*), segments and file
  (**Segments and file**, *Segmente und Datei*), stoichiometry (**Content from stoichiometry**, *Gehalt aus
  Stöchiometrie*), calibration (**Calibration**, *Kalibrierung*) and the library options (**Libraries and options**,
  *Bibliotheken und Optionen*) are collapsed. Header, menu titles, tabs and overview exist in German and English.
* File ▸ *Stufentabelle teilen (Elementrechner) …* (share step table): shares only the losses per step with
  onset/peak/end and the residue, never the curve. Sharing the same run again creates a new version. In the
  Elementrechner this becomes the comparison with the theoretical loss of a decomposition.
* File ▸ *Stufen in den Projektindex …* (steps to the project index) and *Projektindex …* (project index); in the
  index list, *Herkunft* (history) leads from a value back to the measurement file (with SHA-256).
* File ▸ **Run from dataset …** (*Lauf aus Datensatz …*; since 0.11): reads a dataset of the Datenaufbereitung that
  was shared with the TGA. Columns are assigned to roles (time, temperature, mass; others under **More columns**,
  *Weitere Spalten*) and converted to min, °C, mg or %; if a unit does not fit its role, the run is refused. Rows
  marked as excluded are left out; sample mass, heating rate and gas come from the conditions. **pinned** (*fest*)
  keeps one version; in both modes a note appears as soon as a newer version exists, and nothing changes by itself;
  **Update from dataset** (*Aus Datensatz aktualisieren*) loads it with the same mapping. The info line and the
  methods text name ID and version; the report records the version for archiving.
* **Values to other environments (⇄):** next to step loss, temperatures at x % loss, residue and the results of
  own equations there is ⇄. It sends the value **live** or as a **snapshot** (*Momentaufnahme*) to another TGA
  environment; there it can be used in own equations (dashed button "← Name"; if the name is taken, it is called
  `Name_ext`). Run 1 keeps the name (`L1`), further runs carry their number (`L1_2`). **⇄ Connections**
  (*⇄ Verbindungen*) in the header lists all connections; on the overview they are arrows between the environments.

## Overlaying own references

**View** (*Ansicht*) ▸ *Referenz einblenden …* (overlay reference) lays a library entry over the run.
*Eigene Referenz eingeben und einblenden …* (enter and overlay own reference) takes step values from a publication
together with their source, stores them in "Eigene Referenzen" (own references) and overlays them at once. The
source form (shared with FTIR and Zugversuch, `labref.js`) knows the type (article, book, standard, data sheet, web,
…), authors, title, journal/publisher, year, pages, DOI/URL and also accepts pasted BibTeX. Nothing is stored
without a source. In the report the reference appears as a full bibliography entry and is cited by every figure or
table that shows it.

## Own equations

In the **Equations** tab create your own formulas (symbol, label, expression, unit, digits, optional source).
Variables are the measured values: `m0` (sample mass), `beta` (heating rate), `res` (residue), `T1`…`T50` (T at x %
loss), for each step k `Lk`, `Lmgk`, `Tonk`, `Tpk`, `Tendk`, composition `C1…`, stoichiometry `X1…`; functions
`m(T)`, `dtg(T)`, `loss(T1, T2)`. Later equations may use earlier ones. Units are carried through the calculation
(shared calculation core with the Rechner, `labcalc`). Stored in `outputs/tga/eigene_gleichungen.json`,
export/import as JSON. In the report: values as `\labval` (`eq-<symbol>`), a table and the equations as display
math in the methods text, with source.

## Limitations

* The readers are built from the documented text exports and tested with self-made files; not yet with any real
  measurement file. Binary formats (TA `.tri`, METTLER) are not read; export them from the instrument software as
  text/CSV. NETZSCH `.ngb-ss3`/`.ngb-bs3`/`.ngb-ds3` is read if the optional package pyngb (MIT) is installed
  (`pip install pyngb`; it brings polars, pyarrow and scipy, together about 120 MB). `.ngb-ds3` (sample and
  correction in one file) is read corrected, as Proteus shows it; units come from the file. Without the package the
  error message explains both ways. The column mapping is tested with a stand-in module, not yet with a real `.ngb`
  file.
* The search narrows down, it does not identify: many materials decompose in similar ranges, step positions depend
  on heating rate, sample mass, crucible and atmosphere. Model curves are not measurements.
* DSC: no calibration step of its own (ASTM E967); the instrument calibration is taken over unchecked, and the
  methods text says so. The gas analysis does not yet go into the report.

## Tests

```
python -m unittest discover -s tests
```

Checks all readers (synthetic files per format, column mapping, segments), protocol, steps and onset on synthetic
calcium oxalate (known losses), composition and stoichiometry, search (the generating reference ranks first) and
mixture (known fractions), kinetics (a given Eₐ is recovered), Fraser–Suzuki separation, own libraries, own
equations, DSC (known peak area and Tg), gas analysis (known Gram–Schmidt maxima), sharing the step table, report and
the server.
