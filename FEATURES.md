# Folio Lab – all features, all modules

One page for the whole suite: what is built, what its limits are, and what is still planned. Each module's guide
(`modules/<id>/README.md`) has the step-by-step use, and `docs/methods/<id>.md` the methods, defaults and validation.
The Elementrechner has its own `modules/elementrechner/FEATURES.md` with more detail.

Legend: **built** = in the app (module features are covered by each module's tests) · **partial** = usable, a named part is missing ·
**planned** = agreed, not started · **proposed** = suggested, order or scope not decided yet.

## At a glance

| Module | Version | What it is for | Test methods |
|---|---|---|---|
| Report editor (Folio) and hub | – | LaTeX reports, projects, module launcher, results in reports with revisions | smoke test (compiles every template), `suite-test.js`, revisions test |
| Shared SDK (`sdk/python`, `sdk/web`) | – | Calculation core, sources, environments, sharing, datasets, index, provenance, page parts | 79 |
| Zugversuch (tensile test) | 1.3.0 | IMADA `.flps` force/stress curves, tests from datasets, material comparison, PDF report | 55 |
| Mikroskopie (microscopy) | 1.3.0 | Micrographs: processing, threshold, watershed, measuring, particle analysis, comparison with a dataset | 58 |
| Rechner (calculator) | 1.4.0 | Units, sheets, line variables, 282 sourced equations, equation and system solver, graph with large datasets and fits, matrices, symbol picker, values with origin | 83 |
| FTIR | 1.5.0 | IR spectra: processing, bands, groups, library search, mixtures, OPUS, spectra from datasets | 73 |
| TGA | 0.13.0 | Thermogravimetry: steps, composition, library search, kinetics, DSC, TGA–FTIR, runs from datasets | 84 (1 skipped) |
| Elementrechner (chemistry) | 0.11.0 | Equations, substances, thermochemistry, designer, redox, pH, lab workflows, nuclear, kinetics (also from datasets), speciation | 261 |
| Datenaufbereitung (Data Purification) | 0.3.0 | Excel/CSV/typed tables → marked, parsed, cleaned datasets with units, outlier flags, templates, exports, report; used by Rechner, Elementrechner, TGA, FTIR | 83 (1 skipped) + `tools/e2e_datasets.py` |

Every module (except the Elementrechner, which has its own board) opens on the same **overview**: the project index,
shares addressed to it, its environments and its own shares; a click opens an environment. **⇄** next to a value
(or dataset) sends it to another environment of the same module, live or as a snapshot; **⇄ Verbindungen** in the
header lists and edits these links, and the overview draws them as arrows. An environment box shows small versions
of its graphs (spectra, TG/DTG, stress curves, the last Rechner graph, dataset curves, histograms, ΔrG(T) and
titration curves); a click enlarges them. The hub cards use the same icon as the module header. Inside, a few main tabs,
the rest under "Mehr ▾", and the less used settings folded away. Headers, tabs and folds switch between German and
English (DE|EN); table contents and older result texts are still German.

---

## 1. Suite and report editor

### Hub
- **built** Home page with the analysis modules as cards; a module starts in the background on first use.
- **built** Local only: the app and all modules accept connections from this computer (`127.0.0.1`) only.
- **built** One start file (`Start Folio Lab.bat`); first start installs portable Node.js and MiKTeX and the Python
  packages. Own port (4330), so it runs next to a plain Folio.
- **built** **Projects** above modules: a project selector and "New project …" next to "Analyses"; one default
  project; each older report is listed as a project of its own. Modules follow a project switch.
- **built** Each module card shows the environment it opens in for the active project ("+n" more, summary title).
- **not built** A per-project filter of the report list (all reports stay listed).

### From measurement to report (all modules)
- **built** **Send to report …** in every module: pick an existing or new report (*Lab report* template, German or
  English), the language of captions and text, what to include, one measurement or several as a comparison.
- **built** **Lab** button in the editor lists every result in the report:
  - figures (vector PDF, caption and label);
  - booktabs tables;
  - values as `\labval{<result>}{<key>}`, so the number in the text follows the analysis;
  - data as CSV, with **Plot** for a pgfplots chart;
  - references collected in `lab/references.bib`, with **Cite**;
  - text blocks (methods, results), inserted editable or linked;
  - **Insert results section** (`sections/<result>.tex`).
- **built** **Refresh** recomputes a result from the stored raw file and settings; **English/Deutsch** rebuilds it in
  the other language.
- **built** **Revisions:** Refresh keeps the previous revision (`lab/<slug>/history/<n>/`); compare, restore (as a new
  revision), mark issued. PDF download and ZIP export mark the current revisions issued.
- **built** **Status and history in the Lab dialog:** chips "Revision n of m", "issued"/"draft", "uses n shared
  input(s), n index value(s)"; "history ▾" shows result ID, module and version, measurement files with SHA-256 and,
  for shared inputs and index values, the chain back to the raw file.
- **built** ZIP export adds `lab/dependencies.json` (every result and kept revision: module version, file hashes,
  shared versions and index values used).
- **built** First insert adds `\input{lab/labdata}`, the packages and the bibliography to the main file if missing.

### Editor (from Folio)
- **built** pdfLaTeX, XeLaTeX, LuaLaTeX; missing packages download on first use.
- **built** BibTeX (natbib) and biblatex/Biber detected and run; makeindex, glossaries, nomencl run automatically.
- **built** Images by drag or paste; Figure, Table, Plot (pgfplots from a formula or CSV), Cite and `\ref` helpers.
- **built** Syntax highlighting, autocomplete (commands, labels, citation keys, files), citation hover, autosave,
  outline.
- **built** Error list with underlining; SyncTeX both ways.
- **built** Projects: templates, ZIP import/export, duplicate, rename, **Combine projects** from several authors.
- **built** Shortcuts: Ctrl+S / Ctrl+Enter compile, Ctrl+B bold, Ctrl+I italic.

## 2. Shared across modules

- **built** **Processing protocol** (Mikroskopie, FTIR, TGA): every step is recorded, always applied to the original,
  so screen, export and report match. Steps can be undone one by one, saved and loaded as JSON, applied to all open
  files.
- **built** **Own references** (FTIR, Zugversuch, TGA): add a reference that is not bundled to any comparison graph.
  One shared source form (`labref.js`): type, authors, title, journal/publisher, year, pages, DOI/URL, note, or pasted
  BibTeX. Nothing is saved without a source. In the report it becomes a full `@article`/`@book`/`@manual` entry and is
  cited by every figure and table that shows it.
- **built** **Own equations** (FTIR, Zugversuch, TGA): symbol, label, expression, unit, digits, optional source;
  evaluated on the measured values with units; later equations may use earlier ones; errors stay on their row. Sent
  to the report as `\labval` (`eq-<symbol>`), a table and display math with the source.
- **built** Own references and equations are plain JSON in `outputs/<module>/`, exportable, importable, editable by
  hand.
- **built** **Shared calculation core** (`sdk/python/labcalc`): units and quantity kinds, safe expression evaluator
  (no `eval`), LaTeX/HTML rendering, sourced constants (CODATA 2022, SI Brochure, IUPAC Green Book), chemistry
  (formulas, substances, acid–base, redox, reaction types, structure graph, naming).
- **built** **Units for lab and environment measurements**: pH, conductivity (µS/cm, mS/cm, S/m), redox
  potential, relative humidity (%RH), turbidity (NTU, FNU, FAU), absorbance (AU, mAU), water hardness (°dH, °fH,
  mmol/L), dissolved O₂, salinity, ppm/ppb, illuminance (lx), luminous flux (lm), sound level (dB), dose and dose rate
  (Gy, Sv, µSv/h), catalytic activity (kat), CFU/KBE counts, Torr, cP/cSt, sccm/slm, each with its own quantity kind.
  Scale units (pH, dB, NTU, FNU, FAU, AU) are never converted into each other or into %.
- **built** **Every number has a source:** measured, tabulated, calculated and estimated values are labelled apart;
  modelled reference libraries say so in the UI, figure tags, citations and methods text.
- **built** Result bundles (`folio-lab-bundle/1`) store search and mixture results with their curves, so Refresh does
  not depend on later library edits.
- **built** **Environments** (all six modules): named, persistent pieces of work per module and project
  (`projects/_suite/projects/<pid>/env/<module>/<id>/`: manifest, page state, raw files deduplicated by SHA-256,
  versioned results, trash instead of delete). Loaded files and settings survive a restart.
- **built** **Overview board** (`laboverview.js`, `labboard.js`): boxes for the project index, shares, environments and
  own shares, wires between them, keyboard and Back-button navigation, one column at phone width.
- **built** **Sharing** (`labshare.py`, envelope `suite.shared-result/1`): only selected numbers with unit and
  conditions leave a module, never the raw curve; immutable versions; the consumer binds pinned, live or as a copy,
  with status current / update available / stale / failed. Slices: TGA step table and FTIR peak table → Elementrechner;
  Elementrechner values → Rechner; values between Elementrechner environments.
- **built** **Links between environments in every module** (`laboverview.js`): ⇄ on a value sends it live or as a
  snapshot to another environment (kind `lab.envvalues`, one versioned share per source environment); "⇄
  Verbindungen" lists, changes and removes links; board wires with arrows. Incoming values become variables in own
  equations (TGA, FTIR, Zugversuch), Rechner variables with origin, or a "Übernommene Werte" box (Mikroskopie).
- **built** **Datasets** (`labdataset.py`, schema `suite.dataset/1`; share kind `data.table` with a `.npz` sidecar):
  equal-length columns with name, symbol, kind, unit and role, conditions, flags (never deleting rows; exclusion is a
  recorded decision with reason) and provenance back to file and cells. Versioned; consumers bind live or pinned.
- **built** **Import window** (`labimport.js`): "Datensatz importieren …" in every module, inside an environment or
  on the overview. It lists every dataset of the project ("für dieses Modul" first), with search, a preview (graph,
  columns with ranges, first rows), live or a pinned version, and a "Passt nicht: …" hint. From the overview you also
  choose the target environment or name a new one.
- **built** **Project index** (`labindex.py`): immutable entries with type, unit, conditions, source and provenance;
  alternatives never overwrite. "Projektindex …" in every module; sharing never writes to it.
- **built** **Provenance and retention** (`labprov.py`): "Herkunft" from a value back to the raw file with SHA-256
  check; versions and environments used by a report cannot be deleted; dependency export.
- **built** **Page parts** (`labui.js`): DE/EN strings and switch, folds with remembered state, popovers that stay on
  screen, task lists, status chips. Pages started by an older module server fall back to a minimal built-in version
  with a "restart the module" notice.

## 3. Zugversuch (tensile test)

### Built
- **Reading:** IMADA Force Logger Ver2 `.flps` (MS-NRBF reader, standard library only); sign, fine time, sampling
  rate, active section detected. Several files overlaid.
- **Specimen:** about 40 standard specimens (ISO 527-2/-3, ASTM D638/D882, ISO 37, DIN 53504, ASTM D412,
  ISO 6892-1, DIN 50125, ASTM E8, ISO 1924, ISO 13934) or manual geometry (rectangle, round, tube); specimen sketch
  with dimensions in the form and report.
- **Analysis:** slope and fit window, foot point (seating phase removed), yield onset per threshold, break, key values
  (Fmax, Rm, Rp, A, E, work to break, hold time …) and mandatory warnings.
- **Materials:** 88 reference materials in 15 categories (aluminium, steels, cast iron, copper, titanium, magnesium,
  nickel, plastics, reinforced plastics, films, elastomers, paper, wood, composites), each with source and basis;
  measured vs nominal (Rm, Rp, A, E); comparison group; ranking with candidate / downgraded / unlikely / excluded;
  stress–strain field with numbered curves and key.
- **Own materials:** values plus structured source, optional own curve (e.g. digitised from a paper), stored in
  `eigene_werkstoffe.json`; extra materials can be added to the field regardless of group.
- **Own equations** on the key values and the reference's nominal values.
- **⇄ values** (Rm or Fmax, E, equation results) to other Zugversuch environments, usable there in own equations.
- **Exports:** CSV (decimal comma), Excel workbook with formulas and a built-in formula checker, PNG, data-sheet and
  image-appendix PDF, graphical A4 report (key tiles, phases, deviation from the line, material field, values and
  warnings, source pages), comparison report for two or more measurements.
- **Command line** with batch processing (`flps.cli`).
- **Test from a dataset:** force + elongation or stress + strain from the Datenaufbereitung, evaluated like a `.flps`
  file. Units are converted. Without a time column, the time comes from the path and the test speed. A0 and L0 come from the
  dataset conditions. The report cites the dataset and version; Refresh follows a newer version.
- **Report:** every material in a figure is cited; field table with numbers as in the figure.
- **Page:** tabs Verlauf and Linearer Abschnitt, Werkstofffeld under "Mehr ▾"; reference and comparison, tester and
  remark, less used parameters, own equations, material comparison and device folded (titles show the current
  choice); "⋯" menu with environments, project index and "Kennwerte → Index" (Fmax, Rm).

### Limits
- Material values are standard minimums or typical values; check against your own source before relying on them.

## 4. Mikroskopie (microscopy)

### Built
- **Files:** TIFF (8/16/32-bit, stacks, RGB; calibration from resolution and ImageJ description), PNG, JPEG, BMP, GIF;
  stack slider and Z projection (max, mean, sum, SD, min, median).
- **Scale:** from file, from a line over a known length, or entered pixel size; transfer to other images; automatic
  scale for newly opened images; named presets per objective. **Scale bar** with length, corner, colour, thickness,
  font, label, backing; style to all images; save the image with the bar burned in.
- **Processing (27 steps):** greyscale / channel / 8-bit, invert, contrast, smooth, sharpen, Sobel edges, Gaussian,
  median, mean, minimum, maximum, unsharp mask, background subtraction, image math (add, multiply, log, sqrt, gamma,
  abs), crop, rotate, flip, Z projection; binary: threshold, erode, dilate, open, close, fill holes, outline,
  **watershed** (exact distance transform, h-maxima markers, separates touching particles; cited).
- **Task list** "Aufgaben" as the first tab: open, scale, improve, threshold, binary clean-up, particles, measure,
  results, report – each with a status chip for the current image; measurement and particle tables on demand.
- **Threshold:** 13 automatic methods (default, IsoData, Otsu, triangle, Li, Huang, max entropy, Yen, moments, mean,
  minimum, intermodes, percentile) or manual; compare all methods.
- **Selections and tools:** rectangle, ellipse, polygon, freehand, line (with width), points, magic wand; selection
  list; measure (Ctrl+M); line profile (Ctrl+K).
- **Measurements:** area, perimeter, circularity, ECD, Feret/MinFeret, ellipse axes and angle, aspect ratio,
  roundness, solidity, grey values (mean, SD, min, max, median, integrated density).
- **Particle analysis:** size and circularity filters, edge particles, holes, within a selection; count, area fraction,
  size distribution with number-weighted D10/D50/D90 and volume-weighted Dv10/Dv50/Dv90 (edge-corrected), contours and numbers in the image.
- **Export and report:** image with scale, mask, particle image, histogram, size distribution, CSV, protocol; figures,
  tables, values, data and methods text to the report.
- **⇄ values** from the particle summary (n, area fraction, mean area, ECD, D50) to other environments.
- **Comparison distribution:** a length column of a dataset (e.g. laser diffraction) is drawn over the particle
  histogram on common bins. D10/D50/D90 of both and the D50 ratio are shown. "live" follows new dataset versions,
  "pin" keeps one. The report gets the figure, table, CSV and a citation of the dataset. A scale is needed.

### Limits and possible additions
- Background subtraction is a grey-scale opening (labelled as such), not a rolling ball.
- Threshold references checked by DOI (9 of 11); Tsai 1985 and Prewitt & Mendelsohn 1966 are marked unverified.
- Measurements do not go to the project index yet.

## 5. Rechner (calculator)

### Built
- **Variables** with value (or expression) and free unit; role recognised from name and unit, including typos and
  synonyms ("Geschweindigkeit" in m/s → v; "Spannung" in MPa → σ, in V → U); scope per sheet. Values taken from the
  Elementrechner or the project index keep their origin ("↳ aus Elementrechner · … · Freigabe s-… v n", "hier
  geändert" after an edit), also in the report. The variables panel folds to a narrow rail.
- **Sheets ("Blätter"):** coloured boxes, each a worksheet of calculation lines and equation cards; derive, collapse,
  duplicate. (Called "Umgebungen" before; suite environments now hold the whole worksheet.)
- **Circular references** between equation cards are found and marked on each card involved.
- **Calculation lines:** implicit multiplication, factorial, DEG/RAD, assignments and own functions, units with
  conversion (`->`), complex numbers, calculus (`integral`, `deriv`, `nsolve`, `sum`), statistics and polynomials
  (`mean`, `std`, `linreg`, `polyfit`, `roots`).
- **Line variables:** `50/3 = u` or `u = 50/3` defines `u` (with the unit of the expression) for the following
  lines; ⇄ on the line makes it usable on the other sheets ("u ← Blatt 1") or sends it live or as a snapshot to
  another Rechner environment.
- **Datasets:** "Tabelle aus Datensatz …" in the graph (live or pinned); "Datensatz als Variablen …" binds columns as
  list variables in SI with their unit; `linreg` shows k, d and R² with units; origin line and a Methodik block in the
  report. Large datasets stay on the server: the graph gets only the visible points, thinned to the screen (all
  points up to 4000, then per screen cell or min/max per section).
- **Fits** on dataset and table rows: line, through origin, polynomial 2/3, logarithm, exponential, power, Arrhenius,
  Michaelis–Menten. Each can be linearised (unweighted) or direct. Drag a range in the graph. You get parameters ± u
  (95 %) with units, R², and a linearised view with residuals. Results go → variables; the fit table and figure go to
  the report (e.g. Arrhenius gives Ea in kJ/mol).
- **Solving equations:** a line with `=` and one unknown is solved, e.g. `x^2 - 3 + x = 0` → x₁, x₂ = (−1 ∓ √13)/2.
  The form is exact up to degree 2 and for rational roots, numeric otherwise. The unit of the unknown and conditions
  (`, x > 0`) are handled. Several solutions are stored as `x_1`, `x_2` …; picking one sets `x`.
- **Equation systems:** "Gleichungssystem" on the matrix page, or `;` between equations in a line. Linear systems show
  A, b and rref, with a unique solution, a family with free parameters, or none with the least-squares answer.
  Nonlinear systems are solved by Newton from several starts. A, b and the solution can be saved as matrices.
- **Symbol picker (Σ):** sums, products, integrals, derivatives, roots, Greek letters, relations and units as
  templates, inserted at the cursor with the first gap selected. You don't need to type the code form.
- **Matrices:** matrix window; use in any line (`inv(A)*b`, `A'`, `det(A)`); matrix chips insert at the cursor;
  autocompletion; **→ Matrix** stores a line's matrix result.
- **Equation library, 274 equations:** mechanics, strength of materials (tensile, bending, torsion, buckling, fracture
  mechanics, hardness), geometry, heat, fluids, electrical, optics/microscopy, mathematics, and chemistry (acids and
  bases incl. exact weak-acid pH, buffers, titration; solubility; thermodynamics; electrochemistry; colligative
  properties; kinetics; gases; radioactivity).
- **Sources:** every equation and constant names its source (textbook or standard; CODATA 2022, SI Brochure, Green
  Book), shown on the card and cited in the report.
- **Equation cards** fill in matching variables (symbol and kind must agree), solve for the one missing quantity
  (symbolically or numerically), **derive** further values over several steps, **Wanted …** lists the equations that
  give a quantity and what is missing.
- **Graph (Desmos-style):** functions, sliders with play, implicit curves, parametric and polar curves, points, tables
  pasted from Excel with regression and R², equation-card curves; roots, extrema and intersections on click.
- **Chemistry functions** shared with the Elementrechner (`M()`, `pKa()`, `dGr()`, `pH()` … see §8).
- **Report:** worked calculation per card, quantity table, values, charts as vector PDF plus CSV, marked lines,
  matrices.

## 6. FTIR

### Built
- **Files:** JCAMP-DX (AFFN, SQZ/DIF/DUP, multi-block), Thermo OMNIC `.spa`, GRAMS `.spc`, Agilent MicroLab `.fir`
  (tested with real files), Bruker OPUS binary (detected by its magic bytes; AB and single-channel spectra; other
  blocks listed, not guessed), text/CSV (any delimiter, decimal comma, several spectra, µm/nm converted);
  transmission/absorbance detected.
- **Peak table to the Elementrechner** ("Peaktabelle teilen …"): positions, strengths and group hypotheses, never the
  spectrum. Spectra handed over from TGA–FTIR open on start.
- **Signal quality:** noise, S/N, noisy regions (e.g. diamond ATR window hatched), weak-signal and saturation
  warnings.
- **Processing with live preview:** A ↔ T, Kubelka–Munk, baselines (rubber band, ALS, polynomial, hand-set points),
  smoothing (Savitzky–Golay, mean), CO₂ bridging, ATR correction, normalisation (max, min-max, vector, area, band),
  cut, interpolate, shift, scale, 1st/2nd derivative.
- **Bands:** automatic picking (prominence, spacing, threshold, S/N), position, height, strength, FWHM, up to six
  assignments; manual add/delete; band areas and ratios (e.g. carbonyl index).
- **Functional groups:** about 30 classes rated likely / possible / unlikely with evidence, statements from empty key
  regions; searchable correlation table (85 group frequencies).
- **Library search:** five algorithms (correlation, Euclidean, 1st-derivative correlation/Euclidean, peak search),
  HQI 0–100, range and category filters, masked regions, same-substance grouping, provenance and licence per hit.
- **Mixture analysis:** 2–4 references, non-negative least squares, parsimony penalty, residual view.
- **Libraries:** measured Open Specy spectra (196 in the repository; 1682 of 1223 substances with
  `tools/fetch_optional_data.py openspecy`; read-only, licences noted), a model library of 58
  materials **calculated from literature band positions**, unlimited own libraries (add the current spectrum or import
  files, multi-block JCAMP export, structured sources); overlay a reference from a file.
- **Spectra:** overlay (normalised, stacked), difference spectrum with automatic factor, mean, sum.
- **Own equations** with `A(ν)` and `area(ν1, ν2)`.
- **Spectra from datasets** ("Spektrum aus Datensatz …"): x in 1/cm or a wavelength (converted), one spectrum per
  y column; the dataset ID and version are the spectrum's source. **⇄ values** (band areas, ratios, equation results)
  to other FTIR environments.
- **Export and report:** PNG, JCAMP, CSV, bands, groups, areas, hits, mixture, protocol; figures, tables, values,
  data, sources and text; hits and mixtures cite their references automatically.

### Limits
- OPUS, `.spa` and `.spc` are tested only with generated files, not yet with real ones.
- Peaks do not go to the project index yet.
- Group ratings are hints, not structure elucidation; sulfate/phosphate/silicate rules over-report in dense C–O
  regions. Mixture fractions are area shares (spectral contributions), not mass fractions.

## 7. TGA

### Built
- **Files:** generic text/CSV (header metadata: sample mass, heating rate, gas, crucible) and the text exports of
  NETZSCH Proteus, TA Universal Analysis, TA TRIOS (CSV/XLSX, several sheets), METTLER STARe, PerkinElmer Pyris,
  Shimadzu; column detection with a mapping dialog as fallback; segments (dynamic, isothermal, cooling, gas switch).
- **Processing protocol:** reference mass, cut, segments, temperature correction, blank/buoyancy subtraction,
  Savitzky–Golay, resampling, mg ↔ %.
- **Steps:** automatic from the DTG, limits draggable; onset and endset by tangent (ISO 11358-1), midpoint, DTG peak,
  maximum rate, loss in % and mg.
- **Characteristic values:** T at 1/2/5/10/50 % loss, residue at the end and at a chosen T, isothermal loss.
- **Composition:** ASTM E1131 and ASTM D7582 templates, free limits; stoichiometry (CaCO₃, Mg(OH)₂, Al(OH)₃, gypsum,
  calcium oxalate, PVC → HCl …, from IUPAC atomic weights); calcium-oxalate check; two-point temperature calibration.
- **Library search** (identify the material from its decomposition, after Schindler et al. 2017): DTG curve match with
  shift, plus step comparison; atmosphere and heating-rate warnings.
- **Mixture:** DTG as a non-negative sum of 2–3 references; weights are mass fractions, the rest is "inert".
- **Library:** model library of 71 entries (102 steps, 67 literature sources) **calculated from published step values,
  not measured**; own libraries from a measured run or from step values typed from a paper.
- **Comparison:** overlay (TG/DTG, normalised), step table over runs, mean ± s for repeats.
- **Kinetics** (≥ 3 heating rates): Friedman, Ozawa–Flynn–Wall (ASTM E1641), KAS, Starink, Vyazovkin with Eₐ(α) and
  confidence range, Kissinger, Coats–Redfern, master plot, compensation effect, lifetime (ASTM E1877), ICTAC
  warnings.
- **Peak separation:** Fraser–Suzuki fit, biomass template (hemicellulose, cellulose, lignin).
- **Own references and own equations** (`m(T)`, `dtg(T)`, `loss(T1, T2)` and all step values).
- **DSC / heat flow** (when the file has it): peaks in chosen ranges with linear baseline, area and ΔH per initial
  mass, onset/endset; glass transition (ISO 11357-2 half step height, Δcp); report figure, tables and values.
- **TGA–FTIR coupling:** evolved-gas spectra series (CSV matrix or multi-block JCAMP-DX), Gram–Schmidt curve,
  chemigram for a band, spectrum at a chosen time with background subtracted; "In FTIR öffnen" hands it to the FTIR
  search.
- **Step table to the Elementrechner** ("Stufentabelle teilen …"): losses with onset/peak/endset and residue, never
  the curve; steps to the project index.
- **Runs from datasets** ("Lauf aus Datensatz …"): columns mapped to time, temperature, mass … and converted to
  min, °C, mg; stored as a raw file so environments and Refresh work as with measured files. **⇄ values** (step
  losses, T at x % loss, residue, equation results) to other TGA environments.
- **Export and report:** PNG, CSV, steps, protocol; figures, tables, values (`step1-loss`, `t5`, `residue` …), data,
  sources and text.

### Limits
- Readers are built from documented exports and tested with generated files only, not yet with a real measurement.
- NETZSCH `.ngb-ss3`/`.ngb-bs3`/`.ngb-ds3` are read via pyngb (installed 17 Nov 2026), tested with pyngb's own
  table format but not yet with a real file. TA `.tri` and METTLER binaries are not read; export as text.
- The search narrows down, it does not identify; model curves are not measurements.
- DSC: no temperature calibration step (the instrument's calibration is used, as the methods text says). The
  evolved-gas analysis is not in the report yet.

### Open
- The instrument readers were built from the documented export formats and tested on synthetic files. A reader may
  need adapting to a real export from your instrument; please report files that don't load.

## 8. Elementrechner (chemistry)

Detail: `modules/elementrechner/FEATURES.md`; methods and data sources: `docs/methods/elementrechner.md`.

### Built (phases 1–7, L, S, smaller items, sharing, board)
- **Input:** equations as on paper (charges, phases, hydrates, isotopes, nuclear particles, unknown `?`), German and
  English substance names, floating periodic table (F2), molecule window (F3), amounts table, worked-solution switch.
- **Balancing:** integer null space with exact fractions; impossible and non-unique cases explained; nuclear A and Z.
- **Formulas and stoichiometry:** molar mass with uncertainty (CIAAW 2024), composition, empirical formula from
  elemental analysis, limiting reagent, extent, yield, excess, atom economy.
- **Elements and isotopes:** element card (atomic weight, isotopes from AME2020/NUBASE2020/CIAAW; configuration,
  electronegativity, oxidation states, ionisation energy, electron affinity, radius, melting/boiling point, density
  from the PubChem periodic table).
- **Molecule collection:** 1822 substances with structure, names (1664 German), CAS, InChIKey.
- **Look-up values:** pKa of every step, pKb, Ksp, stability constants, physical properties – each with source,
  conditions and rating; Ksp from ΔfG° where missing (labelled).
- **Own substances** with sourced values and formation data; JSON and SDF exchange.
- **Thermochemistry at 298.15 K:** 12 263 formation-data entries (CODATA, NBS, Burcat/ATcT); ΔrH° (with uncertainty),
  ΔrS°, ΔrG° by two routes, K, Kc, T*, heat, heating value; labelled approximation at other temperatures; ΔG(T) chart.
- **Molecule designer (F4):** OpenChemLib editor; recognition in the collection; rule-based IUPAC names (labelled);
  PubChem on request (structure only); exact descriptors; labelled estimates (log P, log S, TPSA, Joback properties);
  save as own substance.
- **Reaction type** with reasons; **net ionic equation** (solubility threshold from Ksp).
- **Redox:** oxidation numbers, half-reactions, balancing in acidic or basic solution, E° from ΔfG°, E°cell,
  ΔG° = −nFE°, Nernst, Faraday with current efficiency and electrolysis yield, warnings for ambiguous electrodes.
- **pH tab:** pH of any mixture from the proton balance at 0–100 °C (pKw(T) after Bandura & Lvov 2006), species
  fractions, titration curve with equivalence points and suggested indicators (titration error), indicator look-up
  (22 indicators, Harris 2016), buffer finder (common lab buffers first) with composition and buffer capacity.
- **Ansetzen tab (lab workflows):** solution from solids (hydrate-aware, reference species, purity, balance and
  flask rounding, mixtures) and from stocks, reagents or certified standards (density with source required);
  dilution series and mixing with any one unknown; buffer recipe from the chemicals at hand (two forms, or one form
  plus titrant); reaction set-up with equivalents, scaling and observed masses; green metrics (E-factor, PMI, RME,
  atom economy) with a stated counting boundary and a side-by-side comparison; ideal-gas helpers. Every calculation
  has a printable worksheet and goes into the report when its section is open.
- **Kern tab (nuclear chemistry):** nuclear equations checked and classified (α, β⁻, β⁺, EC, IT, SF, reactions) with
  Q from AME2020 masses; binding energy; decay law and specific activity, Bq ↔ Ci; decay chains (Bateman) with N(t)
  chart and equilibrium type; dating (¹⁴C conventional age, K–Ar, Ar–Ar, U–Pb, Rb–Sr isochron) with assumptions;
  isotope patterns and enriched mixtures. No dose or radiation protection, no ¹⁴C calibration.
- **Molecule card:** a drawn molecule goes into the report with its structure as vector graphics, the name and its
  origin, exact, derived and estimated properties.
- **Rechner functions:** `M`, `Ar`, `n`, `pKa`, `pKb`, `Ksp`, `pKsp`, `lgK`, `Tm`, `Tb`, `rho`, `dfH`, `dfG`, `Sm0`,
  `Cpm0`, `dHr`, `dSr`, `dGr`, `lgKr`, `E0r`, `ne`, `oxn`, `pH`, `m_prep`, `V_reag`, `m_buf`, `rho_gas`, `AE`,
  `Qval`, `Bnuc`, `Thalf`, `Aspec`, `Ma`; results sent to the Rechner as named quantities.
- **Temperature dependence and kinetics (phase 7):** Cp(T) from NASA-7 polynomials, ΔH/ΔS/ΔG/K(T), van 't Hoff,
  reaction quotient and equilibrium composition; Arrhenius/Eyring fits with standard errors and residuals, reaction
  order from data, rate-law simulation; adiabatic flame temperature (no dissociation, stated).
- **From datasets:** "Aus Datensatz …" fills Arrhenius/Eyring (T, k), reaction order (t, c or X) and the Rb–Sr
  isochron from a dataset, converting units (°C → K, min → s); result and report name the dataset ID and version.
- **Speciation (S):** Davies / extended Debye–Hückel next to the ideal result, metal–ligand distribution vs pH,
  saturation index ("precipitation possible", no amount).
- **Smaller items:** bond enthalpies and lengths with a labelled ΔrH estimate, ionisation energies (NIST ASD) and
  Shannon radii, Antoine coefficients and K_f/K_b, import of own data tables with required sources.
- **Board and environments:** overview with environments, shares and the project index; tools imported per
  environment; reaction chains with overall equation and Hess sums; research window with "→ Umgebung"; values between
  environments (live or snapshot); TGA and FTIR comparisons from shared inputs.
- **Report:** equation with matrix solution, stoichiometry, composition, thermochemistry with Hess sums and ΔG(T),
  redox, ionic equation, pH, titration, lab set-ups, molecule card, nuclear chemistry, kinetics, speciation, reaction
  chains, copied values, TGA/FTIR comparisons; values and full citations.

### Open
- Older result texts are German only. Not planned: dose and radiation protection, ¹⁴C calibration, pKa(T).

## 9. Datenaufbereitung (Data Purification)

Detail: `modules/datenaufbereitung/README.md`; methods: `docs/methods/datenaufbereitung.md`.

### Built
- **Input:** xlsx/xlsm/xls/ods/csv/txt/json/parquet and pasted cells, kept as a sheet grid (virtual scrolling);
  **typed measurement tables** with cell editing and a sequential entry that takes many values in one line (space,
  `;`, newline, ", "; decimal comma kept; units attach) with a live preview and unit suggestions.
- **Marking:** first guess, data block, header and units lines (also a units line with one unit), roles, metadata
  cells as conditions, repeated blocks, wide → long, transpose; column step with symbol, kind and date/time →
  elapsed time.
- **Parsing:** decimal comma and thousands separators, `E`/`·10^`, `±` → uncertainty column, `<x`/`>x` (value at the
  limit, flagged), n.d./—/Excel errors → missing (flagged), numbers with their own unit converted within the
  dimension. Rows are kept; flags say why.
- **Datasets:** saved with automatic versions on change, shared to Rechner, Elementrechner, TGA, FTIR and other
  environments (⇄, live or snapshot); check chips per version.
- **Convert and clean → new dataset:** unit conversion per column or for the whole dataset, formula columns with
  constants, trim/filter/sort/drop empty, duplicate flags, replicate means (mean, s, n, SE), join on x (interpolated,
  labelled), Savitzky–Golay (labelled), outlier flags (Grubbs sequential or single pass, Dixon one- or two-sided,
  IQR with Hyndman–Fan type 7 quartiles, Hampel by position or x window, studentised fit residual as a rule of thumb),
  exclusion with a required reason; step log with counts; live or pinned to the source; flags travel with replicate
  means and every flag change makes a new version.
- **Templates and batches:** anchors and a block that refits to the file; problems named by cell; batch one dataset
  per file or one combined (union of columns, same quantity converted, differing conditions as columns).
- **Export and report:** CSV (with the columns "verwendet" and "Markierungen"), XLSX (with "Protokoll"), JSON,
  Parquet (optional, needs pyarrow), all reading back the same; report bundle with preview figure, tables, `\labval`
  values, data CSV for pgfplots, cited methods text with file hashes; Refresh pinned to the dataset version in the
  report (default) or live (newest version, noted in the report).
- **End-to-end test:** `tools/e2e_datasets.py` (Excel → mark → clean → Rechner, Elementrechner, TGA, FTIR → bundle →
  exports; 24 checks) in a temporary folder.

### Limits
- `.xls` is read via xlrd but has no unit test. Step texts and server notes are German (also in the English report).
- Replicates group by exact equality; formulas have no row shift (differences to the previous row).

## 10. Suite-wide plans

### Cross-module features – built
- TGA step loss vs the theoretical loss of a decomposition; FTIR peak table vs a drawn structure; Elementrechner values
  in the Rechner with origin; TGA–FTIR evolved-gas spectra into the FTIR search; datasets from the Datenaufbereitung
  in the Rechner, Elementrechner, TGA and FTIR; values between environments in every module.

### Suite architecture – built (`docs/ARCHITECTURE.md`)
Golden tests, report revisions and provenance, projects and persistent environments, typed results and shares, live
bindings and local dependencies, project index, provenance view and retention.

### User interface – built
Overview first, detail on demand, in every module: shared page parts, an overview board per module, a molecule
designer with grid, element palette and bond tool, hub cards and status in the Lab dialog.

### Possible next steps
- Per-project filter of the hub's report list.
- FTIR peaks and Mikroskopie measurements to the project index.
- Table contents and older result texts in English.
- TGA evolved-gas analysis in the report; DSC temperature calibration.
- Dataset variables inside Rechner graph expressions; replicate grouping with a tolerance; row shifts in formulas.

- An image editor module.
