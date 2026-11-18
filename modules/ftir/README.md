# FTIR

Analysis of infrared spectra in Folio Lab. The workflow follows common spectroscopy software (KnowItAll, OMNIC,
OPUS): open a spectrum, process it, mark and assign bands, assess functional groups, search libraries, decompose
mixtures, compare spectra, and transfer the results to a report. Runs locally and needs only numpy and matplotlib.

What each computation does, its formulas, defaults, references and the tests that check it:
[FTIR: methods and validation](../../docs/methods/ftir.md).

The app starts in German. Below, the English label is given first and the German label follows in parentheses on
first mention. Menu entries and tab contents are still German only (see "Overview, environments, sharing"); for
those, the German label is given with an English gloss.

## Important note on the libraries

Wiley's KnowItAll relies on its licensed database of hundreds of thousands of measured spectra. That cannot be
rebuilt. Folio Lab therefore ships three things:

* **Measured references (Open Specy, read-only):** measured FTIR spectra from the Open Specy collection. The public
  repository contains 196 spectra of 104 substances, mostly plastics, from the sources that allow redistribution
  (Microplastix SpecDB, Davidson et al. 2023, Primpke et al. 2018). `python tools/fetch_optional_data.py openspecy`
  adds the other 1486 on your computer as a second library, *Open Specy, restricted licences*. The full set has 1682
  spectra of 1223 substances from the Open Specy collection (Cowger et al. 2021, *Anal. Chem.* 93, 7543–7548,
  doi:10.1021/acs.analchem.1c00123; Cowger et al. 2025, *Anal. Chem.*, doi:10.1021/acs.analchem.5c00962, details not
  verified; data doi:10.17605/OSF.IO/X7DPZ). Among others, it contains RRUFF (minerals), SWGDRUG (drugs), Kimmel Center,
  Primpke 2018 and AWI (plastics, fibres, natural materials), PSLC, FLOPP, Microplastix and more.
  By category: mineral/filler 732, drug 411, plastic 275, chemical 114, natural material 71, fibre 35,
  elastomer 34, paint/coating 6, pigment 4. Each entry names its origin (citation) and, where stated, the
  measurement mode (ATR/transmission) and the licence. 25 entries are explicitly **CC BY-NC (non-commercial
  only)**; the library is intended for internal, non-commercial use. Not included: NIR, Raman, reflectance
  spectra, NIST (terms of use), USDA soil samples, AWI transmission spectra (thick particles, often saturated),
  short spectra (fewer than 500 points on the 2 cm⁻¹ search grid) and noisy spectra (S/N < 8). At most 10
  spectra per substance, chosen to be as different as possible; outliers (r < 0.5 to the most typical spectrum of
  the substance) removed. Paints and coating resins are barely represented; drugs and minerals are numerous.
  To rebuild (after downloading `nobaseline.rds` from the OSF project):
  `python tools/build_openspecy.py <path>/nobaseline.rds` writes `ftir/data/openspecy/` (R is not needed;
  `tools/rds.py` reads the file without executing R code).
* **Model library (read-only):** 58 common plastics, paint binders (styrene-acrylic, polyester-melamine,
  epoxy-phenolic, acrylic-melamine, nitrocellulose, shellac), additives (DEHP, erucamide, vegetable oil),
  elastomers, fillers, solvents and natural materials, **calculated from literature band positions** (position,
  relative intensity, full width at half maximum). These are **not measured spectra**. The library is good enough
  for narrowing down and trying things out; hits from it are indications. The interface, the export and the
  methods text in the report say so each time.
* **Own libraries:** as many as you like, stored under `outputs/ftir/bibliotheken/<name>/`. Fill them with measured
  references: add the current spectrum (with name, category, CAS number, molecular formula, source, comment) or
  import files, including multi-block JCAMP files from other programs or from databases you own. Export as
  multi-block JCAMP. Use these libraries for reliable identifications.
  Sources of libraries and entries are **structured** (shared source form: type, authors, title,
  journal/publisher, year, pages, DOI/URL, note; "BibTeX einfügen …" (paste BibTeX) fills it from a copied
  entry). Older entries with a free-text source are still read. In the report this becomes a complete
  bibliography entry (`@article`, `@book`, `@manual` … with DOI) instead of just a title.

## Overlaying your own reference from a file

*Library (Bibliothek) ▸ Referenz aus Datei einblenden …* (overlay reference from file; also in the *Libraries
(Bibliotheken)* tab): choose a spectrum (any readable format) and give name, category and **source** (title, DOI
or URL is mandatory). The spectrum is saved in the library "Eigene Referenzen" (own references; created when
needed) and immediately overlaid on the sample, normalised. Every library entry can also be overlaid directly with
*Einblenden* (overlay). Overlaid references carry their origin; the report names and cites them in the figure and
its caption.

## Own equations

*Equations (Gleichungen)* tab: own formulas with symbol, label, expression, unit, digits and, optionally, a source,
e.g. the carbonyl index `CI = area(1650, 1850) / area(1420, 1500)`. Variables are the defined band areas and ratios;
functions are `A(ν)` (absorbance at a wavenumber) and `area(ν1, ν2)`; the buttons in the dialog insert them. Later
equations may use earlier ones; errors stay with their row. Stored in `outputs/ftir/eigene_gleichungen.json`;
export and import as JSON. In the report: values as `\labval` (`eq-<symbol>`), a table, and each equation as a
displayed formula in the methods text, with its source.

## Workflow

1. **Open FTIR from its card on the hub start page.** Drag files in or use *File (Datei) ▸ Öffnen …* (open;
   several files, shown as tabs at the top). Supported: JCAMP-DX (`.jdx`, `.dx`; AFFN and compressed
   SQZ/DIF/DUP, multiple blocks), Thermo OMNIC (`.spa`), GRAMS/Galactic (`.spc`, new format, also several
   spectra), Agilent MicroLab (`.fir`, Cary 630 / 4300 Handheld: SPC with resolution, SampleID and source file),
   Bruker OPUS (`.0`, `.1`, …; not yet checked, see Limitations) and text/CSV (comma, semicolon, tab, space;
   decimal comma; several y columns = several spectra; wavelength in µm/nm is converted). Units stated in the file
   (column header, JCAMP `##XUNITS`/`##YUNITS`, SPC axis codes) are used; SPC x axes that are not a wavenumber or
   wavelength are refused. If the file states no unit, it is guessed (x: largest value ≤ 50 → wavelength in µm,
   otherwise cm⁻¹; y: from the values) and a notice appears with the button *Einheiten …* (units) to choose them.
   The *File ▸ Beispiel: …* (example) entries load three calculated examples.
   **Signal quality:** for every spectrum, the noise, the signal-to-noise ratio (status line) and noisy regions
   are determined. Notes appear above the plot: noisy region (typical for diamond ATR at 2300–1900 cm⁻¹,
   hatched in the plot), weak signal (S/N < 50; "check sample contact" below 15), possible saturation
   (absorbance > 1.5).
2. **Edit** (*Edit (Bearbeiten)* tab or *Edit* menu): choose a step and set its parameters. The **preview** shows
   before (grey), baseline (dashed) and after; *Anwenden* (apply) adds the step to the **protocol**. Steps:
   absorbance ↔ transmittance, Kubelka-Munk, baseline (rubber band, ALS, polynomial, anchor points set by hand with
   tool **B**), smoothing (Savitzky-Golay, moving average), bridge CO₂ (2390–2280 and 680–655 cm⁻¹; the wider
   ranges used up to version 1.4 can be chosen; a notice appears if a sample band seems to reach into the range),
   ATR correction (y · ν̃/ν̃_ref, penetration depth ∝ wavelength), normalise (maximum, min-max, vector, area, band;
   "band" only for absorbance-like spectra), cut, interpolate, offset, scale, 1st/2nd derivative. The protocol is always
   applied to the original (interface, export and report are identical). It can be undone step by step, saved and
   loaded as JSON, and applied to all spectra.
3. **Bands** (*Bands (Banden)* tab): automatic search (prominence, minimum distance, threshold, maximum number,
   minimum S/N; minima for transmittance) with position, height, intensity (vs/s/m/w, broad), FWHM and possible
   assignment. Clicking a band shows up to six assignments. Tool **P** sets bands by hand, **D** deletes them.
   **Band areas** (*Band areas (Bandenflächen)*): drag a range with tool **R** or type it in (base: straight line or
   zero), plus **ratios** (*Ratios (Verhältnisse)*) of areas or heights (e.g. carbonyl index). For transmittance
   and reflectance, areas, heights and FWHM are computed on absorbance (−log₁₀(T/100)) or log(1/R); only there are
   they proportional to the amount.
4. **Groups** (*Groups (Gruppen)* tab): assessment of about 30 compound classes (likely / possible / unlikely;
   wahrscheinlich / möglich / unwahrscheinlich) with evidence per band and statements from empty key regions
   ("no carbonyl band …"). Below it, the searchable **correlation table** (85 group frequencies); a click marks the
   range in the spectrum. When you point at the spectrum, the status line names possible assignments.
5. **Search** (*Search (Suche)* tab, **F3**): choose libraries, method (correlation, Euclidean distance, 1st
   derivative correlation/Euclidean, peak search), search range and category; blank out CO₂ and further ranges
   (tool **R**). Hit list with HQI (0–100), coverage and library; *Suchvergleich* (search comparison) shows sample
   and hits one above the other. *Gleiche Stoffe zusammenfassen* (merge identical substances; on by default) shows
   only the best spectrum per substance, "(+n)" names the others; switched off, all appear individually. The hit
   details give origin, measurement mode and licence.
   **Provenance travels with the data:** a reference opened with *Als Spektrum öffnen* (open as spectrum) carries
   library, entry and source in the JCAMP field `##$FOLIO REF`. This survives saving and reopening, and carries
   over into difference, mean and sum spectra. In the report, the spectrum, search, mixture and comparison figures
   and the hit and mixture tables (per row) cite their references automatically in the caption: Open Specy
   (Cowger et al. 2021 and 2025) plus the original database (e.g. RRUFF); the model library as its own entry with the note
   "not measured spectra"; own libraries with name and the source of the entry. The labels in the figures name
   the origin ("· Open Specy/RRUFF", "· model"; "· Modell" in German reports). The export writes the sources to
   `treffer.csv`, `mischung.csv` and `protokoll.txt`.
   *Als Spektrum öffnen* (or a double-click) lays the reference over the sample, normalised.
6. **Mixture** (*Mixture (Mischung)* tab): combinations of up to 2, 3 (default) or 4 references with non-negative
   weights; the list is sorted by HQI, and more components are listed first only if they fit noticeably better.
   The view shows sample, fit, components and residual. Fractions are **area shares** (share of each component in
   the area of the fitted, normalised absorbance spectrum), not mass or volume fractions.
7. **Spectra** (*Spectra (Spektren)* tab): overlay (overlaid, normalised, stacked), rename, **difference spectrum**
   A − f·B (factor automatically by least squares, also within a range chosen with **R**), mean and sum. New
   spectra appear as their own tabs and go into search and report like measured ones.
8. *File ▸ Exportieren (Ordner mit Abbildungen, Tabellen, Protokoll)* (export) writes to `outputs/ftir/<spectrum>/`:
   the spectrum as PNG, JCAMP and CSV, bands, groups, areas, hits, mixture (CSV with semicolon and decimal comma),
   search and mixture figures, and `protokoll.txt`. *File ▸ Spektrum als JCAMP-DX speichern* or *Spektrum als CSV
   speichern* (save spectrum as JCAMP-DX / CSV) downloads the processed spectrum.
9. **To report … (Zum Bericht …)** sends figures (spectrum with bands, search hits, mixture, comparison), tables
   (bands with assignment, groups, hits, mixture, areas), key values (`\labval`: number of bands, strongest band,
   best hit, HQI, areas, ratios), data (CSV for pgfplots), sources (file, Socrates and Silverstein for band
   tables, Savitzky-Golay, ALS, polynomial baseline, ATR, NNLS, Open Specy, depending on use) and text blocks (methods, results). Search and mixture results are
   stored with their curves, so that *Refresh* in the report does not depend on later changes to the libraries.
   Results that are out of date after a change to the protocol are not sent.

View: the mouse wheel zooms (wavenumber), Shift+mouse wheel pans, tool **Z** drags a zoom box (dragged upwards, also
in y), **H** pans, a double-click or **0** shows everything, and *View (Ansicht)* has fixed ranges (fingerprint,
carbonyl, C–H/O–H). **Ctrl+O** (Strg+O) opens, **Ctrl+Z/Y** (Strg+Z/Y) undoes and redoes, **Esc** cancels.

## Methods

* **Search:** sample and references are prepared the same way: absorbance, averaged onto a grid of 400–4000 cm⁻¹
  with 2 cm⁻¹ spacing, rubber-band baseline subtracted, maximum 1 (the user's protocol is applied to the sample
  before that, never to the references). HQI = 100·r² (correlation) or 100·cos (Euclidean)
  in the common, selected range; references that cover less than 90 % of the range are down-weighted in
  proportion. The derivative methods compare the 1st derivative (Savitzky-Golay, 9 points); peak search compares
  the band lists with a tolerance of 6 cm⁻¹ + 0.4 % of the band position; bands of sample and references are
  picked with the same parameters (including S/N ≥ 10).
* **Mixture:** candidates are the best single hits and the best hits for the residual after subtracting the best
  one. Every subset of up to K candidates is fitted with non-negative weights and a free intercept; the
  non-negative least-squares problem (Lawson & Hanson 1974) is solved exactly by enumerating all supports, not with
  the Lawson–Hanson active-set algorithm. HQI = 100·R²; ranking by HQI − 2 per additional component.
* **Groups:** absorbance minus rubber band, maximum 1; required, supporting and contradicting bands per compound
  class with minimum heights (at least 6 × noise); broad bands (O–H, N–H) are judged by the lower quartile of the
  range. If a required band lies outside the measured range or in the noise, the class is at most "possible".
  Statements about missing bands are made only if the noise would still show a band of 2.5 % of the strongest.
* **Noise:** residual after Savitzky-Golay smoothing (7 points, cubic), locally as a running median over
  80 cm⁻¹; σ₀ = robust standard deviation (1.4826 · median |residual| / √(1 − 7/21)) over the quiet points
  (local noise ≤ 2 × the 25th percentile of the local values). S/N = height of the strongest band (maximum of the
  12 cm⁻¹ moving mean above a rubber band, outside noisy regions) / σ₀. Noisy: locally > 3.5 σ₀ (edges down to 2 σ₀) and more noise
  than signal there. Bands need a prominence ≥ 10 × noise (the usual limit of quantification); in noisy regions,
  no bands are set automatically, and the search leaves these regions empty (they count neither for baseline and
  normalisation nor for the comparison; can be switched off).
* **ALS baseline** after Eilers & Boelens (2005) with an own solver; log λ refers to 1 cm⁻¹ point spacing and is
  converted with (1 cm⁻¹/Δν̃)⁴, so the same setting gives the same baseline on any grid (per data point as up to
  1.4 is selectable). **Savitzky-Golay** via least-squares coefficients, no SciPy dependency.
* **Assignments:** all table ranges (± 4 cm⁻¹) containing the band; first those whose shape fits (a band narrower
  than 30 cm⁻¹ is not given a broad table band), then groups of compound classes the group assessment rates
  likely/possible, then position inside the range, narrower range, matching strength.

## Overview, environments, sharing

* FTIR opens on the **Overview (Übersicht)**: project index, the environments (spectra, best hit, bands, groups)
  with "+ Environment" (+ Umgebung), and your own peak-table shares. A click opens an environment; loaded spectra
  with protocol, bands, areas, ratios and colours stay there across a restart.
* In an environment, the tabs Edit, Bands and Search are shown (Spectra from two spectra on); Groups, Mixture,
  Libraries and Equations are under **More ▾ (Mehr ▾)**. *Search parameters (Suchparameter)*, band areas, ratios
  and *Libraries and options (Bibliotheken und Optionen)* are collapsed (the state is remembered). Header, menu
  titles, tabs and overview exist in German and English; menu entries and tab contents are still German.
* *File ▸ Peaktabelle teilen (Elementrechner) …* (share peak table with the Elemental Calculator): shares band
  positions with intensity, relative height and FWHM, the group hypotheses with their verdict, and the statements
  from empty regions, never the spectrum. The Elemental Calculator (Elementrechner) compares them with the bands
  that the groups of a drawn structure lead one to expect.
* Spectra handed over from the TGA-FTIR gas analysis open at start-up or when you return to the page.
* *File ▸ Spectrum from dataset … (Spektrum aus Datensatz …)*: reads a dataset from Data Purification
  (Datenaufbereitung) that was shared with FTIR. x is the wavenumber (1/cm); a wavelength (µm, nm) is converted
  with ν̃ = 1/λ, other units are refused. Each selected y column becomes a spectrum named after the column; the
  y type follows the unit (% → transmittance, dimensionless → absorbance) or the choice in the dialog. Excluded
  rows are left out. "Pinned" or "live" (fest / live) as in TGA (a notice when a newer version exists, no silent
  reload); *Update from dataset (Aus Datensatz aktualisieren)* loads the latest version. The info line and the
  methods text name ID, version and column.
* *File ▸ Projektindex …* (project index) shows the values of the project; band values do not go into the index
  yet.
* **Values to other environments (⇄):** next to band areas, ratios and the results of own equations there is a ⇄
  button: the value goes **live** or as a **snapshot** (Momentaufnahme) to another FTIR environment and can be used
  there in own equations (if the name is taken → `Name_ext`). **⇄ Connections (⇄ Verbindungen)** in the header
  lists all connections.

## Limitations

* `.spa` and `.spc` files from other manufacturers are implemented from the publicly described formats and tested
  only with self-generated files. The same applies to Bruker OPUS (binary format, `.0`, `.1`, …): the result
  spectrum (AB) and single-channel spectra are opened; interferograms and unknown blocks are reported in the
  metadata, not interpreted. **Not yet checked with real OPUS files**; if there are problems, save from OPUS as
  JCAMP-DX or CSV.
* Group assessment and assignments are hints from table values, not structure elucidation. For dense, overlapping
  C–O bands (e.g. paints, coatings), the broad rules for sulfate, phosphate and silicate tend to report too much.
* Mixture fractions are area shares (spectral contribution); mass fractions need a calibration.
* The ATR correction assumes constant refractive indices and weak absorption; it does not correct band shifts
  near strong bands (anomalous dispersion).

## Tests

```
python -m unittest discover -s tests
```

Checks file formats (CSV with decimal comma, JCAMP with DIF/DUP and multiple blocks, `.spa`, `.spc`, Agilent
`.fir`, generated OPUS files), sharing the peak table, signal quality (diamond ATR window, weak signal),
processing, bands, groups, all search methods, mixtures, own and bundled libraries (hits, merging, provenance, RDS
reader), the report and the server. `tests/test_science.py` holds known-answer checks for CO₂ ranges, band
normalisation, ATR factor, ALS λ scaling (solver compared with SciPy if installed), areas on absorbance,
assignments, peak tolerance, mixture area shares and NNLS (SciPy comparison), noise and S/N, units on reading and
Open Specy units.
