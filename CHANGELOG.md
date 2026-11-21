# Changelog

All notable changes to Folio Lab are listed here. The suite version (this file, `package.json`, `CITATION.cff`)
follows [Semantic Versioning](https://semver.org/). Each analysis module also has its own version in
`modules/<id>/module.json`. A module's version changes whenever its results or its report output can change, so
**quote both the suite version and the module version** when you report a result.

Versions below 1.0.0 mean that the methods are tested by the project's own test suites (see `docs/VALIDATION.md`)
but have not yet been validated independently.

## [0.5.0] – 2026-11-21

Changes since 0.4.0:
- measurement uncertainty in every module, with budgets in the report;
- the Werkstoffe compendium as a reference work with citations at statement level, and an info board that collects its
  content and exports it to a report with the individual sources;
- report pieces that cite and describe only what they show, and figures, tables and texts that can be customised;
- a Rechner with drawn equations, symbolic derivatives, stored matrix results and lines in any order;
- values from the project index usable in every module.

Numbers change in the cases listed under *Changed results*. Every module gets a new version because its report output
changes.

| Component | Version | Since 0.4.0 |
|---|---|---|
| Report editor and hub | 0.5.0 | choose what an import shows, Customise, remove a result as a unit, source triage |
| Zugversuch (tensile test) | 1.5.0 | was 1.4.0: uncertainty, fit on coarse display resolution (below), index values in own equations |
| Mikroskopie (microscopy) | 1.4.0 | was 1.3.0: uncertainty, index values in own equations |
| Rechner (calculator) | 1.8.0 | was 1.5.0: lines in any order, ranges, uncertainty, derivatives, drawn equations, matrix results, complex eigenvalues (below) |
| FTIR | 1.6.0 | was 1.5.0: uncertainty, index values in own equations |
| TGA | 0.14.0 | was 0.13.1: uncertainty, index values in own equations |
| Elementrechner (chemistry) | 0.12.0 | was 0.11.0: uncertainty, index values in input fields |
| Datenaufbereitung (data purification) | 0.4.0 | was 0.3.0: uncertainty columns, index values as constants |
| Werkstoffe (materials) | 0.5.0 | was 0.1.0: structure tool, microstructure atlas, compendium, info board, uncertainty, reworked selection |

### Changed results
- **Rechner, complex eigenvalues:** `L = eig(R)` showed the right complex values, but the stored `L` held zeros, so
  every later line using `L` calculated with 0. Results that used a stored complex eigenvalue or eigenvector were wrong
  and change.
- **Zugversuch, coarse display resolution:** on curves such as a thin wire (0.1 N per step on 0.0088 mm², i.e. 11.3 MPa
  per step) the linear-section fit grew along a run of equal readings and came out flat. The foot point t₀ = −q/k then
  lay near 10¹⁶ s, so the apparent modulus was about 0, every strain about −10¹² %, and the load-peak strains and their
  envelope fits were meaningless. The fit tolerance is now at least two display steps (note 4.2 says when it is raised),
  and a fit line that does not rise gives no foot point (note 4.3). Results change only for curves whose tolerance was
  below two display steps.

### Added
- **Werkstoffe, info board:** select one material or a series, walk through the compendium and pin entries, sections,
  single values, statements, figures and the current property chart to a free canvas. Cards can be arranged, collected
  in named frames, annotated and compared, with undo and several boards per project. The export follows the frame
  order, gives each statement its own citation, warns about pins on unchecked sources and keeps those it is told to
  keep with the † mark.
- **Werkstoffe, compendium as a reference work:** 195 entries, 136 of them materials, with values, ranges, designation,
  linked mechanisms and microstructures. Every statement shows its own source or is marked as open, and every source
  shows whether it was checked against the original.
- **Values across modules:** Zugversuch, FTIR, TGA, Mikroskopie, Datenaufbereitung, Elementrechner and Werkstoffe can
  take a value from the project index into their equations or fields, with unit conversion and a refusal for the wrong
  dimension. Where the target can use it, the uncertainty and origin come along.
- **Report pieces cite and describe only what they show:** a plain measurement curve brings no comparison or reference
  sources and a one-sentence methods text (measurement, standard, software). Methods steps follow the imported pieces.
  An envelope, reference curve, field, fit, marker group or other element switched off at import or hidden in Customise
  loses its caption mention, methods sentence and citation, unless another kept piece still needs them. Edited
  sentences survive Refresh. When a hidden part was the only reason for an axis range, the axis closes in on what is
  still shown. Figures follow this in all modules with optional figure elements, and the pieces of Elementrechner,
  Zugversuch, TGA, FTIR and Mikroskopie declare which steps they need.
- **Rechner, matrices and input:** `AB = C`, `inv(A) = Q`, `adj(A) = Q`, `eig(A) = Q`, `rref(A) = Q`, `A*X = B` and
  `X*A = B` store into a free name. All symbol keys are drawn with boxes, including systems with a brace, conditions
  and `d/dx(...)`. The graph accepts `y'` and `diff(y, x)`.
- **Rechner 1.8.0, equations and derivatives:**
  - **Drawn templates:** the ∫Σπ button opens integral, d/dx, sum, product, roots, fraction, power, absolute value and
    matrix as boxes to fill in, drawn in the input line, with Tab between boxes and nesting. Enter applies, Esc restores.
    The line keeps the text form.
  - **Results to other modules:** ⇄ also puts a value into the project index, with its unit and uncertainty. Every
    module can read it there; the Rechner can use it as a variable.
  - **Symbolic derivatives:** `f'(x)`, `f''(x)`, `diff(expr, x)` and `diff(expr, x, n)` with sum, product, quotient and
    chain rule, simplified results and units. Where no rule exists, a numerical value with a visible note. The graph
    plots them with the derived term in the legend.
  - **Formula cards:** the list of quantities became buttons; the clicked one is calculated. The drop-down is gone.
  - **Page values:** lines such as `m = 2 kg` feed the cards of the sheet and can be overridden in the card.
  - **Sharing:** card results and solved quantities go to other sheets, environments and modules with their unit.
  - **Matrices:** `adj`, `cof`; results are stored as named matrices or values, `D = adj(A)` and `A*B = C` store directly.
- **Werkstoffe 0.5.0, tools reworked:**
  - **Property chart:** the overview shows dots only and a selected material shows its range. *Show families* draws
    family outlines; a family's points appear after a click on the family.
  - **Heating:** wood and paper now react to temperature: water loss at 100 °C, no melting, hemicellulose 220–315 °C,
    cellulose 315–400 °C (levoglucosan, char), ash at 525 °C in air, each with its source. Glasses and the glass-ceramic
    show Tg. A material with no transformation in the range says so in one line.
  - **Search:** one field (`Ctrl+K`) over tools, views, materials with aliases and designations, phase diagrams,
    crystal phases and the compendium. Tools are grouped by task, last used first.
  - **Compendium:** view explanations, mechanism animations, the microstructure atlas, usage notes, example data and
    decoder explanations moved into one searchable window with full sources. The tools show results first, with one
    link into the matching entry. Report figures keep their citations.
- **Werkstoffe 0.3.0, materials:**
  - **Ashby charts:** a click on a material no longer copies it straight away. It selects the material: its range
    is outlined in green over its family's outline, and a card shows the main values with range and source. From
    the card you can compare, copy, add to the report or share all values or a single one. Every material is drawn
    as a pale ellipse over its range; typical ranges from handbooks fill in materials that had no value
    (*nur Spanne*).
  - **Designation decoder:** EN AW-1050A H14, 42CrMo4+QT, X5CrNi18-10, 1.4301, CW614N, PA6-GF30, UNS and AISI/SAE
    are explained part by part, with nominal composition and equivalents. It appears on the cards, the selection
    card, the structure view and the tensile test's reference material.
  - **Phase diagrams:** about 30 binary systems in family groups, drawn as smooth boundary lines: steels and irons,
    Al, Cu, Mg, Ti and Ni alloys, solders, teaching systems and ceramics. Every alloy of the module now has a
    diagram. A note per diagram says what is cited and what is simplified. A clicked point shows the
    microstructure there.
  - **Microstructure:** a library of 29 constituents (*Gefügeatlas*, with fact sheets) and 12 animated
    mechanisms. The mechanisms include the Bain strain as a 3-D cell, pearlite, bainite, martensite, tempering,
    precipitation and recrystallisation. Heat treatments get in-between frames placed where the change happens,
    with cross-faded playback. Steels, Al–Cu alloys and cold-worked metals open on their microstructure. An
    optional etched-micrograph look is available.
  - **Martensite cells:** tetragonal cells for 0.45 and 1 % C show the split (101)/(110) and (002)/(200) peaks.
- **Werkstoffe 0.2.0, structure tool (*Struktur*):** every material of the shared database, including all tensile-test
  materials, at a temperature you choose. The views change when T crosses a transition: matrix lattice with solutes,
  unit cells of precipitates and second phases, martensite, polymer chains and crystal cells, amorphous coils and
  networks, ceramic cells with coordination polyhedra, glass networks, and microstructure sketches. A heat-treatment
  mode steps through steel quench and temper, Al/Mg/Ni ageing and recrystallisation along a T(t) path. 25 phase
  structures come from the Crystallography Open Database (public domain), 23 more cells from the literature. Report
  section with all views, a phase table and, for a heat treatment, the path, the frames and the steps. In the hub,
  the tensile test's reference material has a link *Struktur ansehen* that opens this view for it.
- **Choose what an import shows:** importing pieces of a module keeps the whole result in its folder; what you did not
  pick stays available in the Lab dialog under *Also in this result*. The methods text comes in sentences: *Short*
  (the essential sentences, the default), *Full*, or your own ticks, with or without the equations, in the import
  dialog and later in the Lab dialog (*Steps…*). All modules with a methods text write it this way.
- **Customise figures, tables and text (*Customise…*):** in the Lab dialog, after an import (*then customise*), or
  from the editor's context menu on a lab figure or table. For a figure the module redraws it with a journal layout
  (Elsevier, Springer, IEEE, ACS, Nature, thesis, slides), size, font, colour-blind safe palettes, per-series colour,
  line style, name and visibility, axis labels, ranges and log scales, legend and title, with a live preview. Tables:
  columns to keep and decimals. Text: your own wording. Each is saved as a variant beside the original, *live*
  (follows the original on Refresh) or a *snapshot*; from the context menu the text then points at the variant.
- **Customise every part of a figure:** every drawn line, marker, area, bar and text can be hidden, recoloured,
  restyled or renamed (*Lines, labels and areas*); frame colours (background, plot area, axes, ticks, grid, text);
  any installed font or Computer Modern; drag a box on the preview to zoom into a data range (*Reset zoom* undoes it);
  crop the figure with numbers or handles on the preview; and its place in the document: width, full text width
  (`figure*`), position (here, top, bottom, own page, exactly here) and alignment, applied to every place the figure
  is used.
- **Edit many parts of a figure at once:** *All of a kind* sets colour, size, weight, width, line style, opacity or
  visibility for every axis label, tick label, legend entry, text in the plot, line, marker or area together; single
  elements keep their own settings. Select several elements with Ctrl or Shift in the list, or click them in the
  preview, and change them together. *Find and replace in labels* searches texts, legend names, axis labels and the
  title and replaces all matches (with Undo).
- **Faster figure editing:** the preview changes at once while you edit (colour, visibility, width, line style,
  size, plain texts); the module's exact drawing follows after a short pause. A redraw now draws only the edited
  figure, without PDFs (Zugversuch: about 0.25 s instead of 4–5 s), an earlier state comes back from a cache, and an
  outdated redraw is cancelled.
- **Shorter, editable methods text:** *Short* is now at most three sentences: what was measured, the standard
  followed and the software used. Every module's methods text ends with a sentence naming Folio Lab, the module and
  its version, with a citation. Any sentence can be reworded (pencil next to the step) in the import dialog and in
  *Steps…*; your wording is kept on Refresh, and you are told when the module's own sentence changed. *Edit as free
  text…* turns the whole selection into your own text.
- **Remove a result as a unit:** removing a result (Lab dialog *Remove*, deleting its `lab/` folder in the file tree,
  or *Remove result…* in the citation picker, where a result's references are grouped under it) lists every place
  of your text that uses it. Its figures, tables, `\input` lines and results section go; values and references to it
  keep the text they print, marked with † and highlighted in the editor; citation keys only it provided are dropped.
  One *Undo* brings back the result and the text. Removed results stay in the project's bin for 14 days.
- **Rechner 1.6.0, calculation lines in any order:** a sheet is evaluated in dependency order, so a result can stand
  above the lines that define its inputs (`z = y + x`, `y = 5`, `x = f(t) = t^5 - 3`, `t = 3` gives 245); circular
  definitions are reported; ▴/▾ and Alt+↑/↓ move lines; the report lists the lines with every name defined before
  it is used. A name that nothing defines yet stays as a symbol (*z = 5 + x*) instead of an error.
- **Rechner 1.6.0, ranges, lists and sliders:** `t = 0..10 step 0.5`, `t = 0..1 count 5`, `t = [1; 2; 5; 7.5]` and
  `t = 0..5 slider`. Lines that use them give a list with a small curve and a folded value table; with a slider, the
  value at the slider position and a curve over its range. *→ Grafik* draws such a line in the graph and keeps it
  connected. In the report each gets a value table, a figure and a CSV.
- **Rechner 1.6.0, solve a formula for any quantity:** pick the quantity on the card or click it under the formula in
  the library; the card shows the formula rearranged for it, and while values are missing, the rearranged formula
  with the known values inserted.
- **Measurement uncertainty, across the suite:** a small **±** button next to an input sets its uncertainty: a
  standard or expanded uncertainty (calibration certificate), limits ±a with a distribution, a resolution, ± % of the
  value, a manufacturer's spec ±(% + digits), repeat readings (type A), a standard deviation of n values, a confidence
  interval, or an instrument from the library. Several contributions add in quadrature. The library has calipers,
  micrometers, balances, volumetric glassware, pipettes, burettes, Pt100 and thermocouple classes, and force and
  extensometer classes, each with its standard; your own instruments are kept for the whole suite and can be shared
  as a file. Pick the method once: **GUM linear** (sensitivities, Welch–Satterthwaite, k from Student t), **Monte
  Carlo** after GUM Supplement 1 (adaptive, fixed seed), **Gaussian propagation** or **worst case**. Each result shows
  value ± U rounded per GUM 7.2.6, a folded budget (contribution of every input), notes such as a strongly non-linear
  model, the sources, and a comparison of all four methods. Inputs can be correlated. Own equations carry the
  uncertainty of their inputs along. Values shared with other modules and the project index keep their standard
  uncertainty. In the report: *value ± U*, a budget table per result and a methods sentence citing JCGM 100/101 or
  DIN 1319-4.
- **Werkstoffe 0.4.0:**
  - **Uncertainty** for K_Q and the critical crack length, for the hardness mean (indent scatter as type A plus force
    and length measurement) and for CE, CET, Pcm, Ms, Ac1, Ac3 and the preheat temperature.
  - **What a view shows and its sources:** every view of every tool has one line saying what it shows, a fold *What
    happens here?* with the explanation, and the sources of that view first. Figures in the report cite the sources
    of the view they show.
  - **Temperature slider of the structure tool:** the slider only spends travel where something happens. Stretches
    without a transition are compressed to a short step and the transition ranges are marked on the track. The arrow
    keys still move by exactly 1 °C (10 °C with Shift), and the marks under the track jump to a transition.
- **Uncertainty in the other modules:**
  - **Rechner 1.7.0:** `x = 5,0 ± 0,1 mm`, `± 0,2 (k=2)` and `± a rect` in a line; the uncertainty follows every line
    that uses it, with correlation kept (x + x gives 2u, a difference of a value with itself gives 0); method per sheet
    with optional correlations; ± buttons on value lines; results with budget and method comparison.
  - **Datenaufbereitung 0.4.0:** ± columns (U and k, s, standard error, confidence interval) used as standard
    uncertainties; *Wiederholmessung …* gives mean, s, u = s/√n and ν = n − 1; formula columns get a `u(name)` column;
    instrument and other type B uncertainty per column in *Convert and clean*; report table and ±u error bars.
  - **Elementrechner 0.12.0:** molar masses with the CIAAW intervals; preparation from a solid or a stock, dilution
    series (with the correlation between the steps), gas law, reaction set-up and yields, and pH with ±.
  - **FTIR 1.6.0:** noise per point (automatic, from a band-free region, or stated) carried exactly into areas,
    heights and A(ν), with the correlation between bands, so ratios and own indices are right; wavenumber accuracy and
    limit placement as type B.
  - **TGA 0.14.0:** budgets for step losses, residue, onset, endset, DTG peak, T at x % loss, composition and
    stoichiometric content; replicates as type A; kinetics with the regression confidence interval.
  - **Mikroskopie 1.4.0:** scale calibration (stage micrometer, edge reading or pixel size) carried into sizes,
    D10/D50/D90 and areas; sampling by bootstrap with a fixed seed, counts by √N, several images by mean ± t·s/√n
    (ASTM E562); own equations.
  - **Zugversuch 1.5.0:** budgets for S0, Fmax, Rm, yield force or stress, E (slope scatter, force and extensometer
    class, L0, S0, test speed), Agt/At and Ag/A; a series as mean ± type A; ± line in the PDF and a sheet in the
    workbook.

### Fixed
- **Werkstoffe, own crystal cell:** the fields b, c, α, β and γ were shown for every crystal system, although most
  systems ignore some of them. Only the free parameters of the chosen system are now shown and sent.
- **Werkstoffe, invalid input:** an empty field, text, NaN or a value outside a formula's domain ended in an internal
  error, and some XRD and Weibull settings could hang. Each now gives a clear input error.
- **Servers:** a refused request from a foreign origin could abort the connection before its answer arrived.
- **Values with a unit in text:** results of own equations and uncertainty values printed with `\labval` inside a
  sentence no longer stop LaTeX (they were written as bare math). `MPa√m` is now set as MPa·m^½ instead of "MPam^½".

## [0.4.0] – 2026-11-19

Changes since 0.3.0:
- materials science in the calculator, on a shared, sourced materials database;
- a new Werkstoffe (materials) module, including a lattice viewer;
- "Import from Folio": graphs, tables and values of any module environment go into a report at the cursor, with their
  references.

No module computes different numbers than in 0.3.0, except for one TGA fix (below). The Rechner's report output
changes (new equations and citations), so it gets a new version, and TGA gets a patch version for the fix. The other
modules only gained the environment import, so their versions stay the same.

| Component | Version | Since 0.3.0 |
|---|---|---|
| Report editor and hub | 0.4.0 | Import from Folio (module → environment → pieces) |
| Zugversuch (tensile test) | 1.4.0 | unchanged results; comparison materials from the shared database; environment import |
| Mikroskopie (microscopy) | 1.3.0 | unchanged (environment import) |
| Rechner (calculator) | 1.5.0 | was 1.4.0: materials science equations and functions, `mat()`, `erf`; report cites material sources |
| FTIR | 1.5.0 | unchanged (environment import) |
| TGA | 0.13.1 | was 0.13.0: report of a later run in a file with several runs (fix below); environment import |
| Elementrechner (chemistry) | 0.11.0 | unchanged (environment import) |
| Datenaufbereitung (data purification) | 0.3.0 | unchanged (environment import) |
| Werkstoffe (materials) | 0.1.0 | new |

### Added

**Shared materials database** (`sdk/python/labcalc/data/materials.json`, `labcalc/materials.py`)
- 136 materials in eight classes: metals and alloys, polymers, ceramics, glasses, composites (UD plies), fibres,
  semiconductors, natural materials. They include 18 pure elements, steels in several heat-treatment states, technical
  ceramics and glasses.
- Properties: density, E, G, ν, Rp, Rm, A, compressive and flexural strength, hardness, K_Ic, Weibull modulus,
  Tm/Tg, α, λ, c_p, electrical resistivity, band gap, lattice parameters, crystal structure, and the ply values of UD
  composites. Each value has a source, a value kind (typical, minimum, maximum, mid-range, unclear) and, where given, a
  range.
- Values that were not checked against their original source in this round are marked as such, in the picker and in
  the report.
- Diffusion data D₀ and Q for ten species/host pairs.

**Rechner**
- New area "Werkstoffkunde" with 83 equations in 13 sections, each with a source. The sections run from
  crystallography, defects and diffusion through deformation, creep, fatigue, fracture and Weibull, composites,
  polymers, electrical and thermal properties, corrosion, and steel and heat treatment, to materials selection.
  The library now has 365 equations.
- New functions in calculation lines (group "Werkstoffe"):
  - `mat("1.4301", "Rm")`
  - the shortcuts `E_mat`, `Rp_mat`, `rho_mat`, `Tm_mat`, `alpha_mat`, `a_lat` and others
  - `D_diff("C", "γ-Fe", T)`, `Q_diff`, `D0_diff`

  Names work in German or English and as designations (EN AW-6061-T6, 1.4301, AISI 304). The report cites the source
  of every material value used.
- New basic functions `erf` and `erfc`.
- New quantity kinds: energy density, diffusion flux, corrosion rate, mobility, current density, Lorenz number.
- Library tab "Werkstoffe": search, class chips, a card per material with value, value kind and source. Clicking a
  value inserts `mat("…", "…")`. Material names and properties autocomplete inside `mat("` and the `_mat("`
  functions.

**Optional data:** `python tools/fetch_optional_data.py mp` adds computed Materials Project data. It needs your own free
API key in `MP_API_KEY`. The data covers density, bulk and shear modulus, isotropic E and ν, band gap and space group
of the stable phase of 38 elements and compounds. The entries are kept apart from the measured ones as
"… (berechnet, mp-…)" and are marked as DFT values. They are left out of the public repository like the other optional
parts.

**Werkstoffe module 0.1.0** (`modules/werkstoffe`, new): materials science in one page.
- Selection: Ashby chart of any two properties from the shared database, performance index lines, limits, ranked list
  with reasons, your own values with their source; Materials Project points only with the toggle, labelled
  *berechnet (DFT)*. Material cards for 2–6 materials.
- Crystallography and XRD: 38 built-in phases and CIF import, computed powder patterns, rotatable unit cell; readers
  for xy/CSV/TXT, `.xrdml`, `.brml`, `.raw` (RAW1.01), `.uxd`, `.ras`; background, peak fit, cubic indexing,
  Nelson–Riley, Scherrer, Williamson–Hall, phase search, semi-quantification.
- Phases and steel: five diagrams drawn schematically from cited key points and labelled so, computed
  ideal/regular-solution diagrams, lever rule and cooling path; carbon equivalents, preheat, Ms, Ac1/Ac3,
  Hollomon–Jaffe, carburising.
- Mechanics and lab data: laminate theory with four failure criteria, fatigue (S–N with run-outs, Haigh, Marin,
  rainflow, Miner), Weibull with bootstrap, E399 fracture toughness, hardness from indents (conversion only from your
  own table file), E112 grain size, Hall–Petch, Tafel/Butler–Volmer corrosion, Larson–Miller and Norton creep.
- Every tool goes to the report with figures, tables, values, data and cited methods text; synthetic example data in
  every tool, labelled as such. Methods: `docs/methods/werkstoffe.md`.
- Lattice tool *Gitter* (Kristall area): lattice section of a base element at a temperature with phase and a(T),
  dissolved atoms on interstitial or lattice sites in their true number, second phase above the solubility limit,
  equilibrium vacancies, Debye vibration and distortion, schematic edge dislocation, stacking fault and tilt grain
  boundary; 3D, unit-cell and slice views; exaggeration of vacancies and vibration only with a visible factor. Report
  section with 3D, cell and slice figures, table, values, atom positions as data, and the equations in the methods text.

**Import from Folio** (editor, hub, all modules)
- The Import dialog starts with the modules of the active project: module → environment → its graphs, tables, text
  blocks and single values on the right, with previews and "comes with: n references · methods text". The chosen
  pieces go in at the cursor with their references; the methods text is optional. Other reports, shared values and ZIP
  upload stay below as further sources.
- Every module builds a report for any stored environment without switching to it (`/api/env/bundle`, SDK
  `ModuleEnvs.peek`/`bundle_of`). The page keeps its current report request in the saved environment, so an
  environment can be imported after it has been opened once in this version (Zugversuch, Rechner and
  Datenaufbereitung also derive it from older environments where their saved state allows).
- The import is saved as a result of the real module (only the chosen pieces), linked to the environment
  (live/pinned/copy). "Source changed" when the environment's files or report request change; Update rebuilds from
  the environment, Refresh keeps the choice.

### Changed
- The Zugversuch reads its 88 comparison materials from the shared database. `modules/zugversuch/data/alloys.json` was
  removed; its rows are in the database unchanged. `--legierungen` still accepts a file in the old format. Results,
  reports and goldens are identical.
- Shared report text (`labbundle.tex_escape`): a run of superscript or subscript characters becomes one LaTeX group
  (10⁻⁶ → `$^{-6}$` instead of one group per character), and ₄–₉, ⁰, ⁴–⁹, ⁺, ⇌, <, > are now converted. Report text of
  other modules changes only where these characters occur; the output looks the same.
- The overview's module names include "Werkstoffe".

### Fixed
- TGA: when a file holds several runs, the report of the second or a later run used the data of the first run. The
  report now uses the chosen run, and Refresh keeps it. Reports of files with a single run are unchanged.

## [0.3.0] – 2026-11-18

Changes since 0.2.0:
- report import from anywhere in Folio Lab, and a portable LaTeX ZIP for other projects;
- environments can be deleted from the overview;
- resizable layouts on every page;
- in the Zugversuch, load peaks for materials that fail progressively, and a switch for the elastic/plastic division.

**Zugversuch results change** for curves with two or more load peaks, and for curves whose yield onset lay after the
maximum (see "Changed results"). All other modules compute the same numbers as in 0.2.0. Their pages changed only in
layout, so their versions stay the same.

| Component | Version | Since 0.2.0 |
|---|---|---|
| Report editor and hub | 0.3.0 | import, portable ZIP, resizable panels |
| Zugversuch (tensile test) | 1.4.0 | was 1.3.0: load peaks, elastic/plastic switch, movable legends; results change |
| Mikroskopie (microscopy) | 1.3.0 | unchanged (layout only) |
| Rechner (calculator) | 1.4.0 | unchanged (layout only) |
| FTIR | 1.5.0 | unchanged (layout only) |
| TGA | 0.13.0 | unchanged (layout only) |
| Elementrechner (chemistry) | 0.11.0 | unchanged (layout only) |
| Datenaufbereitung (data purification) | 0.3.0 | unchanged (layout only) |

### Added

**Report editor: Import**
- New "Import" button next to Lab. It takes figures, tables, equations (numbered or not), whole sections, images, data
  files and values from these sources:
  - other reports;
  - whole analysis results;
  - the shared data and index values of the active project;
  - an uploaded ZIP of any LaTeX project.

  Search, a kind filter and a preview (picture or LaTeX) help find the piece.
- Every piece brings what it needs: its files, its `.bib` entries, the macros it uses, the packages they need and its
  `\labval` values. Labels get a prefix, so nothing clashes with the report. A cite key that the report already has
  with a different entry is renamed, with a note.
- An import becomes an analysis result of the report (`lab/import-…/`). It is inserted from the Analysis results
  dialog like any other result.
- Imports are *live* by default. When the source changes, the dialog says "source changed", and *Update* fetches the
  new state; the old state stays as a revision. *Pinned* only offers the update. *Copy* has no link.
- Shared data tables are imported as CSV, ready for the Plot button. Shared values and index values become `\labval`
  values with their unit and uncertainty.

**Report export: portable LaTeX ZIP**
- The download menu in the editor (and on the start page) has "Portable LaTeX for other projects (.zip)". The ZIP holds
  a folder `<prefix>/` with:
  - `body.tex` and `preamble.tex`;
  - `<prefix>.bib` (biblatex) and `<prefix>-bibtex.bib` (BibTeX);
  - the figures, tables and data the report uses.
- Labels and cite keys get the prefix, so the folder can sit next to other content. `preamble.tex` loads only packages
  the host has not loaded and defines nothing twice.
- A `main.tex` at the top compiles the folder on its own. `README.txt` gives the lines a host document needs, for
  biblatex and for BibTeX. Measurement sources, history and removed results are left out.
- `folio-link.json` records where each result came from. If the original report is in Folio, importing the ZIP back
  links the pieces to that report again.

**All module pages and the report editor**
- **Delete environments from the overview.**
  - Hover over an environment box (or focus it) and click the small × at the top right, or press Delete.
  - A warning names the environment first.
  - Once confirmed, the environment moves to the project's trash (`_papierkorb`) and its connections are removed. An
    open environment is replaced by the standard one.
  - The standard environment has no ×.
- **Resizable layouts.**
  - Drag the edge of a side panel, the bottom edge of a chart, table or list, or the edge or corner of a dialog or
    floating window.
  - Sizes are remembered per module and browser as fractions of the window, so a layout keeps its proportions on
    another screen.
  - Double-click a handle to reset it; "Fenstergrössen zurücksetzen" in the view menu resets all of them.
  - Keyboard: focus a handle and use the arrow keys.
- In the report editor, the Files/Outline split, dialogs and the result list in "Analysis results" are resizable. The
  sidebar and PDF pane widths now stay in proportion to the window.

**Zugversuch 1.4.0: load peaks for progressive failure** (ropes, fibre bundles, composites; methods section 3.8)
- **Detection.** Peaks are found by a hysteresis rule: a peak counts when the load then drops by at least
  Δ = max(5 % of Fmax, 3 × display resolution). The fraction can be set per test, and single peaks can be left out of
  the fit.
- **Values per peak:**
  - time and elongation (strain with v and L₀, crosshead travel with v only, otherwise time);
  - load, the valley after it, and the drop in N and % with its duration;
  - ratio to the previous peak;
  - reload stiffness (20–80 % of the rise);
  - work per segment and cumulative work.
- **Fits.** The peak loads are fitted against the elongation at the peak, with a line and with an exponential.
  - Both fits report parameters ± u, a 95 % CI, R² and SSE.
  - The fit with the smaller residual sum of squares is highlighted.
  - No fit is made with fewer than 3 peaks.
- **Output:**
  - the page ("Lastspitzen");
  - the PDF report;
  - an Excel sheet with a self-check;
  - the Folio bundle (figure, table, values, methods text).

  Equation variables `npk`, `Fpk1`…`Fpk20` and the fit parameters are available. An info note (4.9) explains that
  Fmax is the highest peak.

**Zugversuch 1.4.0: elastic/plastic switch**
- "Elastisch/plastisch einteilen" (divide into elastic and plastic) can be *Automatisch* (default), *Ein* or *Aus*.
- *Automatisch* does not divide curves with two or more load peaks. In ropes, fibre bundles and composites the parts
  fail one after another, so a limit on the force curve does not describe a state of the material.
- Without the division:
  - the curve is coloured as rise, load peaks and drop;
  - the yield slider is hidden;
  - yield onset, ratio, Ag and A are left out;
  - note 7.4 and the report's methods text say why (methods section 3.3).
- New phases "Anstieg" (rise) and "Lastspitzen" (load peaks, from the first to the last peak) appear in the page, the
  CSV, the workbook, the PDF report and the bundle.

**Zugversuch 1.4.0: movable legends**
- Chart legends on the page can be dragged out of the way. The place is remembered per chart; double-click resets it.
- In the PDF charts the curve legend is placed where it covers the least data.

### Changed results

**Zugversuch 1.4.0** (compared with 1.3.0)
- **Fit window.** On curves with two or more load peaks, the largest slope for the stiffness fit window is searched
  only up to the first peak, and the window ends at the first peak at the latest. E, the fit line and t₀ therefore
  come from the first loading, not from a steeper reload after a drop. Curves with a single peak are unchanged.
- **Yield onset before the maximum.** The yield onset is now searched only before the maximum (with two or more load
  peaks, before the first peak). In 1.3.0 a curve that stays linear up to its maximum could get a yield onset on the
  falling flank after the maximum. Such curves now have none, and therefore no ratio, plastic phase or detent value
  there.
- **No division for two or more load peaks.** By default these curves now have no yield onset, ratio, Ag and A. Set
  *Ein* to get them back; they are then searched before the first peak.
- **Phases.** On curves with two or more load peaks, the sawtooth from the first to the last peak is "Lastspitzen" and
  the drop starts at the last peak. In 1.3.0 the curve was plastic up to the maximum, with the drop after it. No value
  depends on the phases.

## [0.2.0] – 2026-11-18

Scientific corrections after a review of every methods page against the code and the cited sources. **Several
results change.** Results made with 0.1.0 stay reproducible with 0.1.0; the module versions in a report's provenance
tell which version produced a number.

| Component | Version |
|---|---|
| Report editor and hub | 0.2.0 |
| Zugversuch (tensile test) | 1.3.0 |
| Mikroskopie (microscopy) | 1.3.0 |
| Rechner (calculator) | 1.4.0 |
| FTIR | 1.5.0 |
| TGA | 0.13.0 |
| Elementrechner (chemistry) | 0.11.0 |
| Datenaufbereitung (data purification) | 0.3.0 |

### Changed results

**Zugversuch 1.3.0**
- `A` and `Ag` now follow ISO 6892-1 (plastic elongation): A = At − σ_break/E and Ag = Agt − Rm/E, with E the slope
  of the linear section. The former values (total strain under load) are now `At` and `Agt`. **Own equations that use
  `A` or `Ag` give new results.**
- Hold time is the contiguous time above the threshold around the maximum; a dip ends it.
- The plateau mean is taken over the last 20 % of the time from the force rise t₀ to the maximum (was: from the first
  point).
- Reference ranking: ΔRm relative to the material's Rm, sorted by status, then |ΔRm|; the hardening ratio only lowers
  the status.
- Idealised material curves start with slope E (Ramberg–Osgood 1943) instead of Rp/ε_y.
- Wbreak uses the measured elongation when the dataset has one.
- Data: titanium Grade 1 Rp0.2 170 → 138 MPa (ASTM B265 minimum); ISO 527-2 type 1A L₀ 50 → 75 mm
  (ISO 527-2:2012).

**Mikroskopie 1.3.0**
- The particle area fraction includes particles touching the border (it was biased low; sample image 4.10 → 4.50 %).
- With edge exclusion, the remaining particles get Miles–Lantuéjoul weights; means, SDs, D-values and histograms are
  weighted, and an edge-corrected count is reported.
- D10/D50/D90 are labelled number-weighted (Q0) and use the midpoint quantile rule (Hyndman–Fan definition 5) instead
  of linear interpolation (definition 7). New volume-weighted Dv10/Dv50/Dv90 (Q3, from ECD³). The dataset comparison
  computes both sides the same way.
- The particle perimeter is the outer boundary (holes filled) by default; circularity rises for particles with holes.
  "Lochränder zum Umfang zählen" restores the total perimeter.
- TIFF files without an ImageJ description are calibrated from XResolution/YResolution and ResolutionUnit (inch, cm),
  except common print resolutions (72, 96, 300 dpi …), which stay uncalibrated.
- With a selected region, edge exclusion uses the region border.

**Rechner 1.4.0**
- Integrals: adaptive Gauss–Kronrod 7/15 with an error estimate. Integrals that do not converge are refused
  (∫₁^∞ sin x/x dx gave 2.293; the true value is 0.6247). Endpoint singularities are much more accurate
  (∫₀¹ x^(−1/2) dx: 1.9946 → 2.0000000).
- Derivatives: relative step with error control, one-sided at domain boundaries (d/dx √x at 10⁻⁴ = 50;
  d/dx sin(1000x) at 0.001: 539.21 → 540.30), with a note at kinks.
- `->` to °C or °F converts a temperature difference without the offset (shown as Δ°C); new syntax `-> Δ°C`.
- Units are carried through integral, derivative, nsolve, sum/product, lists, matrices and linear algebra; a unit that
  cannot be determined is shown as "?".
- Exact derived constants (ħ, R, F, σ, Wien b) at full double precision.
- °fH = 10 mg CaCO₃/L = 0.09991 mmol/L (was 0.1); °dH from M(CaO) (0.178326 mmol/L).
- `IE()` returns an energy (J; write `-> eV`); `IE_eV()` keeps the plain number in eV.
- Fits: R² through the origin uses the uncentred total sum of squares; direct fits use every point valid for the model
  (not only those valid for the linearisation); new fit rows default to direct.
- Formula-card check: tolerance from the rounding of the inputs (was a fixed 10⁻³).
- Report: values with 6 significant digits; value ± u rounded to the uncertainty.

**FTIR 1.5.0**
- First band assignment considers band shape and the functional-group rating (PET: 2969, 1579, 1242, 1095,
  1018 cm⁻¹ now correct).
- S/N: signal = maximum of the smoothed, baseline-corrected spectrum instead of the 99.5th percentile; σ₀ is a robust
  SD of the quiet points (it was 9–24 % low). S/N values are not comparable with 1.4 (PET example 333 → 353).
- CO₂ bridging defaults to the CO₂ bands only, 2390–2280 and 680–655 cm⁻¹ (was 2400–2250 / 720–630, which erased
  polystyrene 698, calcite 712 and isocyanate bands); "wide" stays selectable; a notice when a sample band overlaps.
- ALS baseline λ refers to 1 cm⁻¹ point spacing, so the same λ works at any resolution (per-point λ selectable).
- Band areas and FWHM of transmittance/reflectance spectra are computed on absorbance / log(1/R) (were on −%T).
- Peak-search HQI: library bands use the same S/N criterion as the sample.

**TGA 0.13.0**
- Ozawa–Flynn–Wall Eₐ is refined iteratively as in ASTM E1641 (exact b(E/RT)) instead of Doyle's constant 1.052:
  about −1 % at E/RT ≈ 30 (example 182.6 → 180.5 kJ/mol). Option `ofw="doyle"` keeps the uncorrected value.
- 95 % confidence intervals of activation energies use exact Student t quantiles; before, 2.0 was used for 11–30
  degrees of freedom and 1.96 above.
- Lifetime (ASTM E1877) uses the model-free Toop relation with the OFW Eₐ at the failure conversion by default; the
  model-based Arrhenius extrapolation stays as an option. Not checked against the text of the standard.
- Extrapolated onset and endset use the inflection point and the local slope dm/dT on the temperature axis; results
  change only when the heating rate varies within a step.
- ASTM D7582 proximate analysis on the as-determined basis (rescaled to the mass at start), plus the dry basis.
- PerkinElmer files use the corrected weight instead of "Unsubtracted Weight"; unitless Kelvin temperature columns are
  detected; TRIOS multi-sheet times are made continuous.

**Datenaufbereitung 0.3.0**
- Dixon's Q test refuses an untabulated α (the 0.05 column was used silently); two-sided tests flag only the end with
  the larger Q; one-sided tests use the 2α column.
- Times with a UTC offset are converted to UTC (the offset was dropped); a DST jump inside a series gives a warning.
- Replicate means carry the flags of their member rows (they were cleared).
- Signed quantities (Δ…, Änderung, Differenz, Verlust …) are no longer flagged as impossible when negative.
- A change to flags alone creates a new dataset version; live child datasets are recomputed.
- CSV export: two new final columns, "verwendet" and "Markierungen".

**Elementrechner 0.11.0**
- R and F are exact (N_A·k, N_A·e) at full precision everywhere; displayed results are unchanged.

### Fixed

- **Report editor and hub:** the module version in provenance is taken from the module that computed the result; an
  issued result is moved to `lab/_removed/` instead of being deleted; shared dataset version numbers are never reused;
  the provenance chain of a derived dataset reaches the raw file; the Refresh mode (pin or live) is stored and stated.
- **Zugversuch:** the fit-window text describes the greedy search and states the tolerance; the hold text uses the
  configured threshold; a yield onset compared with Rp0.2 is labelled "not like with like"; idealised curves are
  labelled "for orientation only"; each material shows its value type (minimum, typical …), unverified sources are
  marked and wood E values are labelled bending moduli; imported materials are checked for source and numbers;
  standards without a confirmed edition say "check edition".
- **Mikroskopie:** non-square pixels are handled throughout; TIFF ResolutionUnit is honoured; the Minimum/Intermodes
  and Moments thresholds handle edge cases; "Hintergrund abziehen" is renamed "(Graustufen-Öffnung)" / "(grey-scale
  opening)", because it is not a rolling ball; citation key `soille2004`.
- **Rechner:** the report no longer crashes on "nicht definiert"; Levenberg–Marquardt reports convergence; graph
  regression rows give parameter uncertainties; Lineweaver–Burk is named and its bias noted; double roots are found in
  formula cards; rational roots with large denominators are found exactly; `ch_pOH` states pKw = 14 at 25 °C (new card
  with pKw); `hard_Rm` is marked as a rule of thumb; ISO titles in English; Trost 1991 and Numerical Recipes cited
  completely; 282 formulas.
- **FTIR:** band normalisation refused for T/R spectra; ASTM E1252 no longer cited (it is not implemented);
  Savitzky–Golay cited only where used; Harrick 1967 (ATR correction), Lieber 2003 (polynomial baseline),
  Silverstein 2014 and Cowger 2021 added; Open Specy sources completed or marked "not verified"; mixture fractions
  labelled area shares (not mass fractions); guessed units shown and selectable ("Einheiten …"); SPC x types honoured;
  OPUS extensions `.0`–`.9` accepted; the band-area table header in reports.
- **TGA:** Senum–Yang approximation coefficient (88x → 86x; Vyazovkin Eₐ changes by less than 0.05 kJ/mol); the
  Vyazovkin method cites the 1997 paper it implements; replicate mean ± s from unrounded values; the search weight is
  passed and adjustable; ASTM E1582 cited with the temperature calibration; ASTM editions marked "to be filled in".
- **Datenaufbereitung:** ODS files with long empty runs no longer shift columns; reading caps raised and every
  truncation reported; the type of a stated uncertainty (u, U with k, SD, SE, CI) can be recorded; Parquet gives a clear
  message when pyarrow is missing; the residual rule is described as a rule of thumb, the IQR fences as Hyndman–Fan
  type 7 quantiles, Grubbs as the sequential procedure; Hampel window optionally in x units.
- **Tests and CI:** golden comparisons tolerate floating-point noise near zero and figure-size differences between
  matplotlib releases (both failed on Python 3.10 only); pyarrow is installed in CI.

## [0.1.0] – 2026-11-18

First public release.

| Component | Version |
|---|---|
| Report editor and hub | 0.1.0 |
| Zugversuch (tensile test) | 1.2.0 |
| Mikroskopie (microscopy) | 1.2.0 |
| Rechner (calculator) | 1.3.0 |
| FTIR | 1.4.0 |
| TGA | 0.12.0 |
| Elementrechner (chemistry) | 0.10.0 |
| Datenaufbereitung (data purification) | 0.2.0 |

Highlights:

- **Report editor:** a LaTeX editor with projects, templates, a bibliography, SyncTeX, and results from the
  analysis modules (figures, tables, values, data, citations, text blocks) kept in step with the analysis by
  **Refresh**, plus revisions and provenance (Folio Lab version, module version and SHA-256 of every source file).
- **Analysis modules:** tensile tests from IMADA `.flps` files or datasets; micrograph processing and particle
  analysis; FTIR processing, band analysis and library search; TGA steps, composition, kinetics and library search;
  data purification into typed datasets with units; a calculator with units, 281 sourced equations, an equation and
  system solver, fits and large-dataset graphs; a chemistry calculator.
- **Shared data:** versioned datasets and values that can be shared between modules, either live or pinned to a version.
- **Documentation for citing:** one methods-and-validation page per module (`docs/methods/`), a validation overview
  (`docs/VALIDATION.md`) and a licence record for every data source (`THIRD_PARTY_NOTICES.md`).
- **Reference data:** only data that may be redistributed is included. Five sets that may not be redistributed are
  added on your computer by `python tools/fetch_optional_data.py all`:
  - the IUPAC pKa dataset;
  - NIST SRD 46 and the NIST ASD ionisation energies;
  - the Burcat thermochemical database;
  - 1,486 Open Specy spectra with restricted licences.

  Every module works without them. The tests that need them are skipped and say so.
- **Tests:** 645 automated tests; the tensile module is tested on a synthetic curve with a known answer, because real
  measurements are not published.
