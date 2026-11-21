# Datenaufbereitung (Data Purification)

Turns Excel sheets, instrument exports and measurement values typed in by hand into **clean datasets with units**
that the Calculator (Rechner), the Elemental Calculator (Elementrechner), TGA and FTIR take over directly. You show
the module *where* the data are and *what* they mean; it reads, checks, converts and records every step. The original
file stays unchanged, rows are never deleted silently, and every dataset leads back to the cell in the source file.
Version 0.4.0.

Methods, parameters, references and validation of every step: [`docs/methods/datenaufbereitung.md`](../../docs/methods/datenaufbereitung.md).
How a number in a report is traced back to the raw file: [`docs/methods/provenance.md`](../../docs/methods/provenance.md).

The page starts in German; English labels are given below with the German label in parentheses on first mention.

## Overview and environments

* The module opens on the **Overview** (Übersicht): project index, datasets of other modules, the environments
  (called "collections" in this module) with **+ Collection** (+ Sammlung), and the module's own datasets. A click
  opens an environment; loaded files, measurement sheets, marks and datasets stay there across a restart.
* **⇄ Connections** (⇄ Verbindungen, in the header) and **⇄** next to a dataset connect environments: the dataset
  appears in the other environment as a table (read only), either **live** (follows every new version; the table is
  replaced in place) or as a **snapshot** (Momentaufnahme; stays at the version of now). One environment can thus
  record and another evaluate. On the Overview, the connections are arrows between the environments; they can be
  dragged there.
* The box of an environment shows a small graph per dataset (x column or row number against up to three number
  columns); a click enlarges it. Older datasets get their graph the next time they are saved.

## Getting data in

* **Load file …** (Datei laden …) or drag files into the window: Excel (`.xlsx`, `.xlsm`, `.xls`), LibreOffice
  (`.ods`), CSV/TXT (delimiter and decimal comma are detected), JSON, Parquet (optional: needs the Python package
  pyarrow, `pip install pyarrow`; without it the module says so and all other formats work). **Paste cells …** (Zellen einfügen …)
  takes cells copied from Excel. Each sheet is a tab; the grid loads only the visible part, so large sheets stay
  responsive.
* **New measurement sheet …** (Neue Messtabelle …) creates an empty table for single measurement results. Type into
  the cells (Enter moves down, Tab moves right) or click a **column or row header**: this opens the entry that fills
  the cells one after another.
  - Type **all values on one line**, separated by spaces, `;`, line breaks or ", "; the preview shows what will be
    written, **Enter** writes them all at once. `12,5` stays one number (decimal comma), `1,2,3` are three values,
    `0,1 0,2, 0,3` are also three.
  - A **unit** right after a number belongs to it (`12,5 N`, `3 mm`); the first value with a unit sets the unit of
    the column, later values in a different unit are refused (the whole column can be converted later). `1,2·10^-3`
    and `1,2E-3` are read.
  - ↑ or Backspace in the empty field goes back to the last value, Esc closes.
  - **Assign unit …** (Einheit zuweisen …; right-click on selected columns) suggests matching units while you type,
    as in the Calculator. These include measurement units such as pH, µS/cm, %RH, NTU/FNU, AU, °dH, mg/L O₂, lx, dB
    and µSv/h; pH, dB, turbidity and absorbance are scales and are never converted into % or into each other.

## Mark: what the numbers mean

In the **Mark** section (Markieren, side panel) start with **First guess** (Erste Vermutung) and correct it, or select
a range and assign it with a right-click:

* **Data block** (Datenblock), **Header row(s)** (Kopfzeile(n)), **Units row** (Einheitenzeile), skip rows; a units
  row with only one unit ("t | c" over " | mg/L") is recognised.
* **Column role** (Rolle der Spalten): x, y, uncertainty (of the column to its left), group, label, ignore.
* **Symbol and quantity …** (Symbol und Grösse …): symbol, quantity kind, the **type of uncertainty** of the column's
  ± values (not stated, standard uncertainty u, expanded uncertainty U with k, standard deviation, standard error,
  confidence interval with level; shown in checks, export and report) and, for date/time columns, the conversion
  into **elapsed time** (s, min, h or d automatically; counting on past midnight; the start time becomes a
  condition). Times with an offset (`+01:00`, `Z`) are converted to UTC; times without one are taken as local time
  as written, and a possible daylight-saving jump is warned about (ACHTUNG), not corrected.
* **Metadata cell → condition …** (Metadatenzelle → Bedingung …, e.g. "Temperatur: 25 °C") or **→ constant column**;
  **Selection is the next block (repeats)** (one block per run), **Wide → long** (Breit → lang), **Swap rows and
  columns** (Zeilen und Spalten tauschen).
* When reading, cells are recognised instead of discarded; the row stays and a **flag** says why:

  | Cell | Result |
  |---|---|
  | `1.234,5`, `1,2E-3`, `1,2·10^-3` | number |
  | `12,3 ± 0,4` | value 12.3 and a new uncertainty column `u(name)` = 0.4 |
  | `<0,5`, `< NWG` | value = limit (or empty), flag "< LOD" (< NWG) |
  | `>1000` | value = limit, flag "> range" (> Messbereich) |
  | `n.d.`, `—`, `k.A.`, `#NV`, `#DIV/0!` | missing (empty), flag "missing" (fehlt) |
  | `5 mm` in a column in cm | converted to cm, flag "converted" (umgerechnet) |

  The preview shows flagged cells in colour; the column header counts the flags.
* **Check as dataset** (Als Datensatz prüfen) reports whether the table is a valid dataset.

## Saving and sharing a dataset

* **Save as dataset …** (Als Datensatz speichern …) turns the marked sheet into a dataset (title of your choice). The
  Calculator, the Elemental Calculator, TGA, FTIR and the Datenaufbereitung itself can take it over. After every
  change a new **version** is created automatically (4 s after the last input), but only when values, flags or
  exclusions, names, units, roles, column properties or the title have changed; **Save now** (Jetzt speichern) does
  it by hand. Version numbers are never given twice, also after a version was deleted.
* In the dataset section:
  - **Checks** (Prüfung; chips, per version): rows read/used/excluded, missing values, flags, x monotonic, gaps
    (step > 3 × median), n per group, impossible values (negative mass, concentration, T < 0 K; not for lengths or
    columns named as a difference or change such as ΔL), type of each uncertainty, columns without unit.
  - **Export** (Exportieren): CSV (header "name [unit]", plus the columns "verwendet" 1/0 and "Markierungen" with the
    flags of each row), XLSX (sheets "Daten" and "Protokoll" with files, recipe, steps, cuts, uncertainty types and
    flags), JSON (lossless, reads back in), Parquet (optional, see above; units in the metadata).
  - **Send to report …** (An Bericht senden …; only inside Folio Lab): preview figure (excluded rows grey, outliers
    ringed in red, error bars from uncertainty columns), tables (columns, first 15 rows, flags), values as `\labval`
    (rows, used, excluded, version), data as CSV for pgfplots, the sources of the methods and a methods text (files
    with SHA-256, recipe, steps with row counts, exclusions with reason, uncertainty types, cuts and time warnings).
    Choose **this version** (Refresh keeps it) or **newest version** (Refresh follows new versions of the dataset and
    says "von Version a auf b"). The dataset travels with the report (up to 4 MB as JSON); **Refresh** of a fixed
    version therefore does not need the share.
* **Open dataset …** (Datensatz öffnen …, **File** menu) lists all datasets of the project and shows one as a table
  (read only).

## Convert and clean → new dataset

**⇆ Convert and clean …** (⇆ Umrechnen und bereinigen …) on a dataset makes a *new* dataset; the old one stays
unchanged.

* **Convert units:** a new unit per column (suggestions matching the quantity), or **Whole dataset: every column in**
  (Ganzer Datensatz: alle Spalten in) for all columns of the same quantity at once (e.g. mm → µm). **keep original**
  (Original behalten) leaves the old column in place.
* **New columns from formulas** with units (`σ = F / A0` in MPa) and **constants** (type them in, **from cell …**,
  aus Zelle …, or **from index …**, which keeps the unit, uncertainty and origin of a project index value).
* **Clean** (Bereinigen, folded): steps run after conversions and formulas, top to bottom, and can be reordered:

  | Step | What it does |
  |---|---|
  | Keep a row range (Zeilenbereich behalten) | first to last row |
  | Filter rows (Zeilen filtern) | `<`, `≤`, `>`, `≥`, `=`, `≠`, between, has a value; for text: contains, not empty |
  | Sort (Sortieren) | ascending or descending, missing numbers last |
  | Drop empty rows (Leere Zeilen entfernen) | in one column or everywhere |
  | Flag duplicates (Doppelte markieren) | flags only, removes nothing |
  | Average replicates (Wiederholungen mitteln) | groups of equal values → mean, s, n, standard error (uncertainty columns are not averaged); flags of the averaged values go to the mean |
  | Smooth (Savitzky–Golay) (Glätten) | new column `…_sg`, labelled as smoothed |
  | Join another dataset (Mit anderem Datensatz verbinden) | columns of a second dataset interpolated linearly onto the x here, no extrapolation, labelled "interpolated" |
  | Flag outliers (Ausreisser markieren) | Grubbs (sequential with α per step, or a single pass), Dixon Q (n 3–10; two-sided tests the end with the larger ratio, or only maximum/minimum; only tabulated α), Tukey/IQR, Hampel/MAD (window by position or in x units), fit residual (threshold k is a rule of thumb); per group if wanted; every method with its source where one is cited |
  | Exclude (with reason) (Ausschliessen (mit Grund)) | rows (`3, 7, 12–15`) or all rows with certain flags; the reason is required |

* **Flagging deletes no row.** Only "Exclude" takes rows out of the evaluation; they stay in the dataset (grey,
  struck through) and are left out by the Calculator, the Elemental Calculator, TGA and FTIR. In the preview, every
  flag has **exclude** (ausschliessen) next to it: it asks for the reason and adds the row to an exclusion step with
  the same reason.
* The preview shows the first rows, the checks and the **Log** (Protokoll): per step rows, flags and excluded rows
  before → after.
* **When the source changes** (Wenn sich die Quelle ändert): *follow* (folgen) computes again as soon as the source
  has a new version (chains over several levels); *pinned* (fest) stays at its version and later offers **bring to
  vN** (auf vN bringen). If a formula no longer fits (e.g. a renamed column), the last version stays and the error is
  shown. **Change …** (Ändern …) reopens the dialog with all steps.

**About the fit residual:** the deviation from a polynomial (degree of your choice) is tested, externally
studentised and stepwise (at most a quarter of the points); k = 3 is a rule of thumb, not a significance level.
With nearly noise-free data the scatter is tiny; a polynomial that cannot follow the curve (e.g. degree 3 on an
exponential curve) then flags the ends. Choose a suitable degree or use another method.

## Measurement uncertainty

* **± columns become standard uncertainties.** A ± column keeps its numbers and its stated type (Mark ▸ *Symbol and
  quantity …*). Wherever an uncertainty is used (formula columns, figure error bars, report, check chips) it is turned
  into a standard uncertainty u per row, and the check chip and the methods text say how: u as given; standard error =
  u of the mean; U/k; standard deviation s = u of a single value; confidence interval: half-width / z (normal
  distribution, e.g. 1.96 for 95 %). A ± column whose type is *not stated* is not used as u.
* **Repeated measurement** (*Wiederholmessung …*, in the selection panel when at least two numbers are selected):
  mean, s, u = s/√n and ν = n − 1 of the selected cells. It is stored with the file under a name and offered to other
  environments and modules as a value with its uncertainty (⇄ connections, value catalogue).
* **Formula columns** (*Convert and clean*): if the columns used have a standard uncertainty, the new column gets an
  uncertainty column `u(name)` computed row by row with the GUM law of propagation (first order, independent inputs).
  Constants count as exact; a row whose input has no stated u gets no u.
* **Type-B uncertainty of a column:** the small **±** next to a column in *Convert and clean* opens the shared
  uncertainty editor (instrument classes from the library, limits, resolution, % of value …). It adds a column
  `u_B(name)`; if the column already had a ± uncertainty, a column `u(name) gesamt` = √(u² + u_B²) is added and linked.
* **Report:** a table of the uncertainty columns (type, conversion, median u), the method in the methods text with
  JCGM 100 and the sources of the instruments; error bars show ±u.

## Templates and batches

* **Save as template …** (Als Vorlage speichern …; in the Mark section, as soon as the sheet reads as valid)
  remembers the marks of a sheet together with anchors (texts of the header, units and metadata). Stored in
  `outputs/datenaufbereitung/datenaufbereitung_vorlagen.json`.
* **Templates and batch …** (Vorlagen und Stapel …, **File** menu):
  - **Apply to this sheet** (Auf dieses Blatt): checks the anchors; the data block adapts to the number of rows. If
    something does not fit, it says where: "A4: expected "t", found "Zeit"".
  - **Batch** (Stapel): one template on several loaded files, either **one dataset per file** (je Datei ein
    Datensatz; a second run makes new versions of the same datasets) or **one combined dataset** (ein gemeinsamer
    Datensatz) with a column "Datei". In the combined dataset, columns are merged by name (missing ones stay empty,
    with a note), the same quantity in another unit is converted into the unit of the first file (e.g. min → h), and
    conditions that differ between files become columns.

## Who uses the datasets

| Module | Where | What |
|---|---|---|
| Calculator (Rechner) | Graph: *Table from dataset …* (Tabelle aus Datensatz …); variable bar: *Dataset as variables …* (Datensatz als Variablen …) | points with units; columns as lists in SI (`mean(c)`, `linreg(t, ln(c/c0))`) |
| Elemental Calculator (Elementrechner) | *From dataset …* (Aus Datensatz …) for Arrhenius/Eyring, reaction order, Rb–Sr isochron | T in K, t and k in s, c or X according to the unit |
| TGA | *File ▸ Run from dataset …* (Datei ▸ Lauf aus Datensatz …) | time, temperature, mass in min, °C, mg |
| FTIR | *File ▸ Spectrum from dataset …* (Datei ▸ Spektrum aus Datensatz …) | wavenumber (also from µm/nm), one y column per spectrum |

All of them name the dataset ID and version in the result and the report; excluded rows are left out everywhere.

## Limitations

* `.xls` is read with xlrd but has no test of its own (no `.xls` writer installed).
* Parquet needs pyarrow, which is not installed with the module (`pip install pyarrow`); its tests are skipped
  without it.
* The Dixon table is not checked against the publication (numerically checked; see the methods page).
* Server and reading notes, the step texts in the log and the methods text of the steps are in German (also in an
  English report); the page labels exist in German and English.
* Formulas can only use columns, constants and the functions of the Calculator; row shifts (differences to the
  previous row) do not exist yet.
* Limits per dataset: 1 000 000 rows, 200 columns, 5 000 000 cells; per sheet 10 000 000 cells.

## Structure and tests

`daten/readers.py` (files → sheets), `sheet.py` (cell grid), `manual.py` (measurement sheets), `recipe.py` (marks,
first guess, long table, dataset), `parse.py` (cell contents, times), `datasets.py` (saving, versions, deriving,
chains), `clean.py` (cleaning steps, outlier tests, checks), `templates.py` (templates, batches), `export.py`,
`bundle.py` (report), `server.py`, `static/index.html`. Shared with the other modules: `sdk/python/labdataset.py`
(schema `suite.dataset/1`), `labshare.py` (share kind `data.table`), `labtable.py` (text tables), `labcalc` (units,
formulas).

```
cd modules/datenaufbereitung
set PYTHONPATH=..\..\sdk\python;.
python -m unittest discover -s tests
```

End to end across all modules (in its own temporary folder, never the project): `python -I tools/e2e_datasets.py`
in the main folder – Excel → mark → clean → Calculator, Elemental Calculator, TGA, FTIR → report → export.
