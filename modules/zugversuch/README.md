# FLPS evaluation app (Zugversuch, tensile test)

Evaluates IMADA Force Logger Ver2 files (`.flps`). Runs locally and fetches nothing from the network.

**Methods and validation:** [docs/methods/zugversuch.md](../../docs/methods/zugversuch.md) describes every computed
value, its defaults and limits, and the tests that check it.

The app starts in German. Below, a control is named by its English label followed by the German label in parentheses
where the page has an English text; controls that exist only in German are given in German with a translation.

## Starting

**In Folio Lab:** home page, section *Analyses*, card *Zugversuch*. Folio Lab starts the module itself. The button
**Zum Bericht …** (send to report) passes figures, tables, key values (`\labval`), measurement data, references and
text blocks to a report (see `README.md` and `docs/MODULES.md` in the Folio Lab folder). Outputs then go to
`outputs\zugversuch\`.

**Stand-alone:** `python -m flps.ui.server` in this folder. The browser opens `http://127.0.0.1:8765/`.
Load files by drag and drop or with **Open file …** (Datei öffnen …); several files are shown on top of each other in
the chart. Outputs go to `Ausgaben\<name of the source file>\`; an existing folder is only overwritten after asking.

In the commands below, `python` stands for the Python interpreter that runs Folio Lab; run them in this folder.

## Overview and environments (in Folio Lab)

- The module opens on the **Overview** (Übersicht): project index and the environments (files, measurements, Rm or
  Fmax, reference per file) with **+ Environment** (+ Umgebung). A click opens an environment; files and settings stay
  there across a restart.
- Header: *Open file*, measurement chips, **⋯** (Manage environments … / Umgebungen verwalten …, Project index … /
  Projektindex …, Values → index … / Kennwerte → Index … with Fmax and Rm), DE|EN, light/dark. Tabs *Curve*
  (Verlauf) and *Linear section* (Linearer Abschnitt); the *Material field* (Werkstofffeld) is under **More ▾**
  (Mehr ▾).
- Collapsed (the state is remembered), with the current choice in the title: Reference and comparison (Referenz und
  Vergleich: reference, own materials, comparison group, additionally shown materials), Operator and remark (Prüfer
  und Bemerkung), the less common evaluation parameters (Window, tolerance, break and hold thresholds / Fenster,
  Toleranz, Bruch- und Halteschwellen; the slider for the yield onset stays visible), Own equations (Eigene
  Gleichungen), Material comparison (Werkstoffvergleich), Device and file (Gerät und Datei). The notes stay visible.
  Table contents are still in German.
- **Values to other environments (⇄):** next to Rm (or Fmax), E and the results of own equations there is a ⇄: the
  value goes **live** or as a **snapshot** (Momentaufnahme) to another Zugversuch environment and can be used there in
  own equations (a name that is already taken becomes `Name_ext`). **⇄ Connections** (⇄ Verbindungen) in the header
  lists all connections.

## Specimen, material, reports

- **Specimen geometry**: switch *Normprobe* (standard specimen) / *Manuell* (manual).
  - *Normprobe*: choice of about 40 standardised specimens (ISO 527-2/-3, ASTM D638/D882, ISO 37, DIN 53504, ASTM D412,
    ISO 6892-1, DIN 50125, ASTM E8, ISO 1924, ISO 13934). The choice pre-fills b or d and L₀ and shows the standard
    thickness as a hint. The thickness is always entered as measured. Deviating dimensions are allowed and appear as
    note 3.1.
  - *Manuell*: free dimensions without a standard reference; cross-section rectangular, round or tube (outer
    diameter D, wall thickness t).
  - Catalogue: `data/specimens.json`. A specimen sketch with dimensions appears in the input panel and in the report.
- **Material**:
  - *Reference material*: 88 materials in 15 categories in `data/alloys.json`, namely aluminium, steel, stainless
    steel, cast iron, copper, titanium, magnesium, nickel, plastics, reinforced plastics, films, elastomers, paper,
    wood and fibre composites. The measurement is set against the target values (Rm, Rp, A, E).
  - *Comparison group*: sets the group against which the ranking and the material field are computed. Without a
    choice the category of the reference applies, otherwise aluminium. There are also the groups "alle Metalle" (all
    metals) and "alle Werkstoffe" (all materials).
  - **The values are standard minimum values or typical values and must be checked against your own source before
    binding use.** New materials can be added to the JSON file without changing the program.
  - **Eigener Werkstoff …** (own material; button next to the material choice): enter property values (Rp, Rm, A, E,
    category) from a paper or data sheet, together with the source in the shared source form (authors, title,
    journal, year, DOI/URL or pasted BibTeX; nothing is saved without a title, DOI or URL). Optionally an **own curve**
    (strain in %, stress in MPa, for example digitised from a figure): it is drawn instead of the idealised curve and
    marked as "taken from the source". Own materials appear in the material list (marked), are stored readably in
    `outputs/zugversuch/eigene_werkstoffe.json` and can be edited, deleted, exported and imported. Duplicate names
    are rejected.
  - **Zusätzlich im Werkstofffeld zeigen** (also show in the material field): put any bundled or own materials into
    the field regardless of the comparison group; they get a number and a key entry like the others and are cited.
- **Own equations** (Eigene Gleichungen, a section of the input panel): symbol, label, expression, unit, digits,
  optional source. Variables are the key values of the measurement (`Fmax`, `Rm`, `Fy`, `sy`, `Fbreak`, `sbreak`,
  `E`, `A0`, `L0`, `v`, `k`, `Agt`, `Ag`, `At`, `A`, `hold`, `ratio`, `Wbreak`, …) and the target values of the
  reference (`Rm_ref`, `Rp_ref`, `A_ref`, `E_ref`). Variables are plain numbers in the display units (force N, stress
  MPa, E GPa, A₀ mm², lengths mm, strain %); the unit of a result is a label you set. Since 1.3.0 `At` and `Agt` are
  the total extensions at fracture and at maximum force (ISO 6892-1), and `A` and `Ag` are these minus the elastic
  part (stress divided by the slope of the linear section). Before 1.3.0 `A` and `Ag` meant the total extensions;
  equations that used them change their result. `Wbreak` is ∫F dL over the measured elongation when the dataset has
  one, otherwise over the crosshead path. Results appear in the input panel,
  on the key-value page of the PDF report and in the Folio Lab report (`\labval` `eq-<symbol>`, table, formula in the
  methods text with its source). Stored in `outputs/zugversuch/eigene_gleichungen.json`.
  - Each row of `data/alloys.json` names a specific source (standard, data sheet of a named grade, or institute
    publication), optionally with `url`, `jahr` (year) and `abgerufen` (accessed). These appear in the bibliography
    entry of the Folio Lab report and on the source pages. Property values that the source does not give (for example
    E for elastomers, A for wood) are marked in `basis` as estimates. `wertart` gives the value type of Rm and Rp
    (minimum, typical, middle of the range, unclear); `nicht_geprueft` marks rows whose source or value is not
    verified (shown as "nicht geprüft" in the app and with * in the report). Wood E values are bending moduli.
- **Labelled material field:** every comparison curve carries a number at its end (ordered by Rm), and a key next to
  or below the chart names the material. From 31 materials on (for example "alle Werkstoffe") the numbers would be
  unreadable; the materials are then listed only in the key and on the source pages.
- **Graphical report** `<name>_Bericht.pdf` (A4, per measurement, 3 or 4 pages plus sources):
  1. Key-value tiles, curve by phases, phase bar, specimen sketch and reference comparison
  2. Data points against the extended line, deviation with threshold, yield onset per threshold
  3. Material comparison with field, Rm classification and candidates (only with A₀)
  4. Key values and all mandatory notes
  5. *Quellen der Vergleichswerte* (sources of the comparison values): every curve of the field (same number) and the
     reference material with Rp, Rm, A, E, source and basis from `data/alloys.json`
- **Sources in the Folio Lab report:** every material that appears in a figure is passed as a bibliography entry
  (title "Werkstoffkennwerte …", basis, source). The field and candidate figures cite their materials in the caption,
  and the table *Werkstoffe des Spannungs-Dehnungs-Felds* (materials of the stress–strain field; numbers as in the
  figure, `\cite` in each row) is added. If you insert only the figure, its sources are already in the bibliography.
  Own materials with a structured source appear as a full entry (`@article`, `@manual` … with authors and DOI).
- **Comparison report** (button *Vergleichsbericht*, from two measurements on; CLI `--vergleich`): all measurements on
  top of each other, key values side by side and a table. It is stored under `Ausgaben\Vergleiche\`.

## Tensile test from a dataset

**From dataset …** (Aus Datensatz …) or the import on the overview (**⤓ Import a dataset …** / ⤓ Datensatz
importieren …) opens the shared import window with all datasets of the project. Datasets without a force or stress
column are marked "Does not fit" (Passt nicht).

* In the second step the columns are assigned:
  - Force or stress (Kraft oder Spannung);
  - Elongation or strain (Verlängerung oder Dehnung);
  - optionally the time (Zeit);
  - where the displacement was measured (specimen/extensometer, crosshead, not documented);
  - tension or compression.
  Units are converted.
* Without a time column the time is calculated from the displacement: t = Σ|ΔL| / v, with the test speed from the
  dialog (default 1 mm/min). The time then increases strictly.
* A₀ and L₀ are taken from the conditions of the dataset if present, and are fixed for this test. Stress and strain
  are converted into force and elongation with them.
* The evaluation runs as for a `.flps` file.
* The report cites the dataset (title, origin, share ID, version, columns). **Refresh** takes the latest version when
  the dataset is followed live ("always the latest") and the remembered version when it is kept ("keep vN").

## Batch processing

```bash
python -m flps.cli messung.flps --form "ISO 527-2 Typ 5B" --dicke 0.1 --v 1 --weg traverse --werkstoff-ref "EN AW-5052-H38"
python -m flps.cli a.flps b.flps --form "DIN 50125 B 6×30" --werkstoff-ref S235JR --vergleich
python -m flps.cli rohr.flps --manuell --rohr 10 1 --l0 50 --gruppe "alle Metalle"
python -m flps.cli *.flps --a0 0.2 --l0 10 --aus Ausgaben --ueberschreiben
python -m flps.cli --liste-werkstoffe --liste-proben
python -m flps.cli datei.flps --json --formate ""
```

## Tests and acceptance test

```bash
python -m unittest discover -s tests -v
```

`tests/test_science.py` checks the definitions with known answers (hold time, plateau, At/A, work to break,
idealised curve, ranking, material data, import). The acceptance test (`tests/test_reference_measurement.py`) evaluates a reference recording and checks the parser result, the
data preparation, the evaluation in force and in stress, the material ranking and the apparent modulus against
expected values. The reference recording is not part of the public repository; see the methods file for what each
test checks and which tests need the recording.

## Structure

| Path | Content |
| --- | --- |
| `flps/parser.py` | MS-NRBF reader, standard library only |
| `flps/prepare.py` | sign, fine time, sampling rate, active section |
| `flps/analyse.py` | slope, fit window, foot point, yield onset, break, key values, mandatory warnings |
| `flps/alloys.py` | material data, groups, idealised curve, envelope, ranking, reference comparison |
| `flps/export/` | CSV, workbook with formulas and check, PNG, data-sheet and figure-appendix PDF, graphical report and comparison report (`report.py`) |
| `flps/ui/` | local web interface |
| `flps/cli.py` | command line |
| `data/alloys.json` | material values with category, basis and source per row, extendable without a new version |
| `data/specimens.json` | standard specimens with dimensions, standard and intended material groups |
| `tests/` | reference case |

## Conventions

- **Measurement point numbers** are 0-based indices.
- **Hold time** is the duration of the contiguous run of points above the threshold that contains the maximum; a
  point below the threshold ends it.
- **Plateau** is the mean over the last 20 % of the time from the foot point t₀ to the maximum.
- **Ranking**: ΔRm = (Rm − Rm_material)/Rm_material. Status "Kandidat" (candidate) at |ΔRm| ≤ 15 % and
  |Δratio| ≤ 15 % (Δratio also relative to the material value), "zurückgestuft" (downgraded) if only Rm fits,
  "unwahrscheinlich" (unlikely) up to 40 %, above that "ausgeschlossen" (excluded). Rows are sorted by status, then by
  |ΔRm|; the ratio (yield onset against Rp0.2, not like with like) only affects the status. The limits are at the top
  of `flps/alloys.py`.
- **Idealised material curves** (for orientation only): elastic with E, then Ramberg–Osgood (1943) through Rp0.2 and
  Rm at 0.55·A, then a 7 % drop to A.
- **Specimens**: ISO 527-2 dimensions follow ISO 527-2:2012 (type 1A: L₀ = 75 mm).
- **Classification by Rm**: missing Rm_min/Rm_max are replaced by the mean value and marked as "Spanne unvollständig"
  (range incomplete) or "Mittelwert" (mean value).
- **Stress–strain curve**: the measured curve starts at the origin and runs along the fitted line up to the fit
  window; the seating phase is left out.
- **CSV**: decimal comma. The mandatory warnings are in `<name>_Hinweise.txt` next to it, so that the CSV stays a pure
  table.
- **Workbook**: recalculation after writing is done by a built-in formula engine (`flps/export/xlcalc.py`), because
  Excel is not required. It checks for error values and compares the key values with the app. The fit-window limits
  are input cells in the overview sheet; Excel computes everything else from the measurement data.
