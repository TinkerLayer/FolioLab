# Datenaufbereitung: methods and validation

This document describes what the Datenaufbereitung (Data Purification) module computes when it reads a file, marks
it, converts units, cleans rows and flags outliers. Every default and limit below is taken from the code in
`modules/datenaufbereitung/daten/` and `sdk/python/`. Every reference is given exactly as it appears in the code. Each
section ends with the tests that check it.

How the resulting numbers are traced back to the raw file in a report is described in
[provenance.md](provenance.md).

## How to cite

State the software and the module version:

> Data were prepared with Folio Lab 0.5.0, module Datenaufbereitung 0.4.0.

The Folio Lab version is in `package.json`; a report result records it as `provenance.suite_version`. The module version is in `modules/datenaufbereitung/module.json`
(`"version": "0.3.0"`, identical to `daten/__init__.py`). Every dataset records the version of the module process
that computed it (`provenance.module_version`; a derived dataset that is computed again gets the version of the
process that recomputed it). A report bundle carries the same version (`module_version`), so the report records the
version that actually ran, not the one in `module.json` at the time of saving (see [provenance.md](provenance.md)).
If you use an outlier test or smoothing, also cite the method source listed in that section. The methods text in a
report bundle does this automatically.

Version 0.3.0 changed results in several places; they are listed at the end of each section and summarised under
[Changes in 0.3.0](#changes-in-030).

## Contents

1. [Readers](#1-readers)
2. [Cell parsing](#2-cell-parsing)
3. [Dates and times](#3-dates-and-times)
4. [From marked sheet to dataset](#4-from-marked-sheet-to-dataset)
5. [Units and unit conversion](#5-units-and-unit-conversion)
6. [Formula columns](#6-formula-columns)
7. [Cleaning steps](#7-cleaning-steps)
8. [Outlier tests](#8-outlier-tests)
9. [Exclusion semantics](#9-exclusion-semantics)
10. [Checks](#10-checks)
11. [Templates and batches](#11-templates-and-batches)
12. [Exports](#12-exports)
13. [Dataset versioning and derived datasets](#13-dataset-versioning-and-derived-datasets)
14. [Changes in 0.3.0](#changes-in-030)
15. [Measurement uncertainty](#measurement-uncertainty)
16. [Known limitations](#known-limitations)

Test paths below are relative to the project root. Module tests run with
`python -m unittest discover -s tests` from `modules/datenaufbereitung` with `PYTHONPATH=../../sdk/python;.`.

---

## 1. Readers

Code: `daten/readers.py`, `daten/sheet.py`, `sdk/python/labtable.py`.

| Format | How it is read |
|---|---|
| `.xlsx`, `.xlsm` | openpyxl, read-only, stored values (`data_only`). A formula without a cached value is read as empty and noted. Hidden sheets are noted. Merged ranges are read. |
| `.xls` | xlrd. |
| `.ods` | Python standard library (zip + XML). Runs of repeated empty cells keep their width, so a value after them stays in its column (up to the 16 384-column limit; more columns are refused). A *filled* row repeated more than 100 000 times is read 100 000 times; this is noted on the page and stored in the dataset provenance (`truncations`). Trailing empty rows are not stored. |
| `.csv`, `.txt`, `.tsv`, `.dat`, `.asc`, `.prn` | Text decoding and dialect detection as below. |
| `.json` | Own dataset format `suite.dataset/1`; pandas `split`, `columns`, `records`; plain rows. |
| `.parquet` | pyarrow – an **optional** dependency, not installed with the module. Without it, reading or exporting Parquet gives the message "Parquet braucht das Python-Paket pyarrow (pip install pyarrow)." (HTTP 400 from the module server); all other formats work. |
| Pasted cells | Cells copied from a spreadsheet. |

Date-time cells with a time zone (Parquet timestamps with a zone, for example) are stored as UTC; date-time cells
without one keep their wall-clock time (see [section 3](#3-dates-and-times)).

**Text decoding** (`labtable.decode`): a UTF-16 byte-order mark, or UTF-16 without one when detected, then
`utf-8-sig`, `cp1252`, `latin-1`, in that order.

**Dialect detection** (`labtable.sniff`): the delimiter is chosen among tab, `;`, `,` and space. A decimal comma is
assumed when more numbers parse with a comma than with a point. The longest numeric block is taken as data; a units
row and a header row above it are recognised.

**Limits**: a sheet holds at most 10 000 000 cells and 16 384 columns.

**Validation**

| Test | Checks |
|---|---|
| `modules/datenaufbereitung/tests/test_readers.py::FormatsTest::test_same_grid_from_every_format` | The same table written as xlsx, ods, csv and json gives the same cell grid. |
| `…/test_readers.py::FormatsTest::test_same_grid_from_parquet` | The same grid from Parquet (skipped without pyarrow). |
| `…/test_readers.py::FormatsTest::test_parquet_without_pyarrow_is_a_clean_error` | With pyarrow made unavailable, reading Parquet raises the German message above, not `ModuleNotFoundError`. |
| `…/test_readers.py::FormatsTest::test_ods_long_empty_runs_keep_positions` | A value after 1 500 repeated empty cells stays in column 1 502; a filled row repeated 200 000 times is read 100 000 times and the cut is recorded. |
| `…/test_readers.py::FormatsTest::test_time_zones` | `2024-03-31 00:30+01:00` → UTC 2024-03-30 23:30; a naive date-time keeps its wall-clock value. |
| `…/test_readers.py::FormatsTest::test_xlsx_details` | Merged cells, hidden sheets, formulas without cached value. |
| `…/test_readers.py::FormatsTest::test_ods_repeats_and_spans` | ODS repeated rows/columns and spans. |
| `…/test_readers.py::FormatsTest::test_refusals_and_refs` | Unsupported files are refused; cell references. |
| `…/test_readers.py::FormatsTest::test_large_sheet` | 100 000 rows load. |
| `…/test_readers.py::FormatsTest::test_xls_if_writer_available` | Skipped when no `.xls` writer is installed; it does not test reading. |
| `sdk/python/tests/test_labtable.py::SniffTest::test_german_semicolon_with_units_row` | `;` delimiter, decimal comma, units row. |
| `sdk/python/tests/test_labtable.py::SniffTest::test_english_comma_tab_space` | `,`, tab and space delimiters with decimal point. |
| `sdk/python/tests/test_labtable.py::SniffTest::test_decode` | Encodings. |

## 2. Cell parsing

Code: `sdk/python/labtable.py` (`number`), `daten/sheet.py` (`cell_number`), `daten/parse.py`.

### Numbers

| Text | Read as |
|---|---|
| `12,5` | 12.5 (decimal comma) |
| `1.234,5`, `1 234,5` | 1234.5 (German grouping) |
| `1,234.5`, `1,234,567` | English grouping |
| `1.234.567` | 1234567 (point as thousands separator) |
| `1'234.5` | 1234.5 |
| `−3` (Unicode minus) | −3 |
| `1,2E-3`, `1,2·10^-3`, `1,2×10⁻³` | 0.0012 |

In text files that are known to use a decimal point, a pattern `\d{1,3}(,\d{3})+` is read as a thousands group.

### Markers

A cell that is not a plain number keeps its row. It gets a value (or NaN) and a **flag** with a code.

| Cell text | Value | Flag code |
|---|---|---|
| `<0,5`, `≤0,5`, `<=0,5`, `unter 0,5`, `below 0,5`, `less than 0,5` | the limit (0.5) | `below_lod` |
| A bare limit word: `<LOD`, `BDL`, `LOD`, `LOQ`, `NWG`, `BG`, `NG`, `DL`, `QL`, `Nachweisgrenze` and the other words listed in `parse.py` | NaN | `below_lod` |
| `>1000` | the limit (1000) | `above_range` |
| `n.d.`, `nd`, `n.a.`, `na`, `n/a`, `k.A.`, `-`, `–`, `—`, `?`, `nan`, `null`, `none`, `leer`, `fehlt`, `missing`, `/`, `x`, `*`, `not detected` and similar | NaN | `missing` |
| Excel error values (`#NV`, `#DIV/0!`, `#N/A`, …) | NaN | `missing` |
| `12,3 ± 0,4`, `12,3 +/- 0,4`, `12,3 +- 0,4` | 12.3, uncertainty 0.4 | – |
| `5 mm` in a column whose unit is cm | 0.5 (converted) | `note` |
| `0,5 g` in a column whose unit is mg/L | – (dimension does not match) | `parse_error` |
| Any other unreadable text in a number column | NaN | `parse_error` |

Rules:

* For `<` and `>` with a unit, the limit is converted to the column unit if the dimension matches.
* For `±`, the uncertainty is converted with the same factor but **without** a temperature offset.
* The `±` value is stored as given. Its **type** is a column property (`u_type`, set in *Column properties* in the
  page or by the `colprop` step) and is "nicht angegeben" (not stated) unless chosen:

  | `u_type` | Meaning | Extra field |
  |---|---|---|
  | (empty) | not stated (default) | – |
  | `u` | standard uncertainty u | – |
  | `U` | expanded uncertainty U | coverage factor `u_k` (required, 0 < k < 100) |
  | `sd` | standard deviation s | – |
  | `se` | standard error of the mean | – |
  | `ci` | half-width of a confidence interval | level `u_level` in % (required, 0–100) |

  The type is stored on the uncertainty column, shown as a check chip (a warning while it is not stated), in the
  XLSX "Protokoll" column table, in the report methods text ("Art der angegebenen Unsicherheit") and in JSON. It is
  only recorded; no value is converted between types. Averaging replicates sets `se` on the SE column it creates.
* A `±` uncertainty goes into the linked uncertainty column (only into empty cells) or into a new column `u(name)`.
* The flag reason for `<` values reads "Wert = Grenze (…)" (value = limit).

**Validation**

| Test | Expected |
|---|---|
| `modules/datenaufbereitung/tests/test_clean.py::FormatTest::test_markers` | `<0,01` → 0.01, `below_lod`; `1,5 ± 0,1 g` in mg → 1500 ± 100; `0,02 g/L` in mg/L → 20 with `note`; `0,5 g` in mg/L → None. |
| `…/test_clean.py::FormatTest::test_sheet_with_every_format` | A sheet with every format gives `[12.5, 1234.5, 0.12, 0.12, 0.01, nan, 1000, nan, nan, nan, 12.3, 20, 15, nan]`; all 14 rows are kept. |
| `…/test_recipe.py::GuessExtractTest::test_header_units_meta` | `<0,01` is flagged with reason "Wert = Grenze (<0,01)". |
| `sdk/python/tests/test_labtable.py::NumberTest::test_formats` | Decimal comma, grouping, exponent forms. |
| `sdk/python/tests/test_labtable.py::NumberTest::test_not_numbers` | Text that must not be read as a number. |
| `…/test_manual.py::ManualModelTest::test_parse_entry` | Sequential entry in measurement sheets (see below). |
| `sdk/python/tests/test_labdataset.py::DatasetTest::test_uncertainty_type` | Default "nicht angegeben"; `U` with k = 2 → "erweiterte Unsicherheit U (k = 2)"; k is dropped for `ci`; unknown types and k ≤ 0 refused. |
| `…/test_clean.py::TimesAndReadingTest::test_uncertainty_type_from_recipe` | `colprop` with `u_type: "U", u_k: 2` on a value column lands on its `u(m)` column; U without k and unknown types are refused. |
| `…/test_clean.py::ScientificFixesTest::test_uncertainty_type_chip` | Chip "info" with "k = 2" when stated, "warn" with "nicht angegeben" otherwise. |

### Sequential entry (measurement sheets)

In the one-after-another entry, a line is split at line breaks, tabs, `;` and whitespace. A token with two or more
commas is split at the commas. A token with one comma is a decimal number. Tests:
`…/test_manual.py::ManualModelTest::test_parse_entry`, `…/test_manual.py::ManualServerTest::test_sequential_entry_routes`,
`…/test_manual.py::ManualServerTest::test_unit_info`.

## 3. Dates and times

Code: `daten/parse.py`, `daten/recipe.py`.

| Form | Example | Notes |
|---|---|---|
| ISO date-time | `2024-03-01 12:30`, `2024-03-01T12:30:05.5`, `2024-03-31T00:30+01:00`, `…Z`, `… +0000` | With a time-zone suffix the value is converted to **UTC**; without one it is local wall-clock time as written. |
| German date | `01.03.24`, `01.03.2024 12:30:05` | Two-digit years get +2000. |
| Time of day | `12:30`, `12:30:05` | Hours up to 47 are accepted. |
| Excel date cell | – | Read as a date. |

* A text column counts as a time column when at least 80 % of its filled cells parse and at least 2 cells are filled.
* **Elapsed time**: the first value is the start. The unit is chosen from the span: < 120 s → s; < 7 200 s → min;
  < 3 d → h; otherwise d.
* **Past midnight**: for times of day, a step backwards of more than 12 h adds one day.
* The start time is stored as a condition named "<column> Start".
* A date column whose finite values are all below 2 × 86 400 s is treated as time-of-day only.
* **Time zones.** A column whose values all carry an offset is read in UTC; the start condition ends in " UTC" and
  elapsed times across a daylight-saving change are correct. A column without offsets (the usual case, and every
  spreadsheet date cell) is **assumed to be local wall-clock time as written, without daylight-saving correction**;
  the column note says "Ortszeit ohne Zeitzone, keine Sommerzeit-Korrektur". A column that mixes both gets a warning
  (the two groups are an offset apart).
* **Daylight-saving warnings** (`parse.dst_check`, local and mixed columns only) are shown on the page as
  "ACHTUNG …" notes and stored in the dataset provenance (`warnings`) and the report methods text:
  * time running backwards (end of summer time, or wrong order);
  * a step that differs from the median step by about one hour (± max(60 s, 10 % of the median step)), only when
    the median step is below 3 000 s;
  * a range of absolute dates that covers 00:00–05:00 of a changeover Sunday under the EU rule (last Sunday of March
    and October, since 1996) or the USA/Canada rule (second Sunday of March, first Sunday of November, since 2007).
    Other regions and earlier rules are not checked.
  The values are not corrected; the user decides (for example by entering times with an offset).

**Validation**

| Test | Expected |
|---|---|
| `…/test_clean.py::FormatTest::test_times` | `12:00:05` → 43 205 s; times 23:50, 00:00, 00:10 → [0, 10, 20] min with start 23:50:00. |
| `…/test_clean.py::TimesAndReadingTest::test_offsets_are_converted_to_utc` | `2024-03-31T00:30+01:00`, `2024-03-30T23:30Z` and `… +0000` give the same UTC second; the naive text is one hour later; offsets across the EU change give 30-min steps; mixed columns are "mixed"; EU change 2024 = 31.03.2024. |
| `…/test_clean.py::TimesAndReadingTest::test_dst_jump_in_local_times_is_warned` | Local times 01:00, 01:30, 03:00 … on 31.03.2024 warn about a 1 h step and the changeover date; the same instants with offsets give [0, 30, 60, 90] min without a warning and a start "… UTC". |
| `…/test_clean.py::FormatTest::test_colprop_symbol_kind_and_raw_time` | Symbol, quantity kind and raw time columns. |

## 4. From marked sheet to dataset

Code: `daten/recipe.py`, `sdk/python/labdataset.py`.

* The marks (data block, header rows, units row, roles, metadata cells, repeats, wide → long, transpose) form a
  **recipe**. The recipe is stored in the dataset's provenance and can be replayed.
* A column is a number column when numbers plus recognised markers make up at least 50 % of its filled cells.
* Unreadable cells become NaN with a `parse_error` flag that keeps the cell text (at most 200 characters). Reading
  flags (unreadable cells and markers) are stored for at most 200 000 cells per column and kind (`MAX_CELL_FLAGS`
  in `recipe.py`; at most 5 000 000 cells fit into a dataset). When more occur, the values are still read; the page
  shows "GEKÜRZT: …" and the dataset provenance records `truncations` = [{what, kept, total, from_row}], which also
  appear in the XLSX "Protokoll" and the report methods text. (Before 0.3.0, raw text was kept for the first 5 000
  unreadable cells and flags for 20 000 cells per column; the rest was dropped without a note.)
* Units are cleaned before lookup (for example `std` → h, `sec` → s, `l` → L). An unknown unit is refused.
* Column roles: x, y, uncertainty, group, label, condition, or none.
* Metadata cells become **conditions** (at most 40 per dataset) or constant columns.

### Dataset limits and schema (`suite.dataset/1`)

| Limit | Value |
|---|---|
| Rows | 1 000 000 |
| Columns | 200 |
| Cells | 5 000 000 |
| Column key | `^[A-Za-z_][A-Za-z0-9_]{0,39}$` |
| Conditions | 40 |
| Values | finite or NaN; infinite values are refused |

Flag codes: `outlier`, `missing`, `below_lod`, `above_range`, `duplicate`, `excluded`, `interpolated`,
`parse_error`, `note`.

The quantity kind of a column must fit its unit; otherwise it is inferred from the unit.

**Validation**

| Test | Checks |
|---|---|
| `…/test_recipe.py::GuessExtractTest::test_tidy` | A tidy table is guessed and extracted. |
| `…/test_recipe.py::GuessExtractTest::test_units_line_with_one_unit` | A units row with a single unit. |
| `…/test_recipe.py::GuessExtractTest::test_side_by_side_blocks` | Repeated blocks. |
| `…/test_recipe.py::GuessExtractTest::test_wide_to_long` | Wide → long. |
| `…/test_recipe.py::GuessExtractTest::test_transpose_and_skip` | Transpose and skipped rows. |
| `…/test_recipe.py::GuessExtractTest::test_csv_first_guess_uses_reader_guess` | First guess for CSV. |
| `…/test_recipe.py::GuessExtractTest::test_refusals` | Invalid marks are refused. |
| `sdk/python/tests/test_labdataset.py::DatasetTest::test_kinds_si_and_mask` | Kinds, SI conversion, used-row mask. |
| `sdk/python/tests/test_labdataset.py::DatasetTest::test_refusals` | Invalid keys, units, infinite values. |
| `…/test_clean.py::CleanTest::test_replay_gives_same_dataset` | Replaying the stored recipe and steps gives the same dataset. |
| `…/test_clean.py::TimesAndReadingTest::test_flag_truncation_is_reported` | With the cap set to 3, a column with 6 `n.d.` cells keeps 3 flags and records {kept 3, total 6, from_row 8}; all 12 rows stay. |

## 5. Units and unit conversion

Code: `daten/datasets.py` (`convert`), `sdk/python/labcalc/units.py`, `sdk/python/labdataset.py`.

* A conversion requires the same dimensions **and** a compatible unit (`units.compatible`).
* Scales (pH, dB, NTU/FNU/FAU, AU) are only compatible with the same scale. They are never converted into % or into
  each other.
* Temperatures are converted with offset (°C → K adds 273.15). Difference kinds (temperature difference, uncertainty
  columns) are converted without offset.
* With **keep original**, the converted column gets the key `<key>_<unit>`. If the original was the x column, the
  copy gets role y.
* "Whole dataset: every column in" converts every column of the same quantity at once.

**Validation**

| Test | Expected |
|---|---|
| `…/test_datasets.py::DeriveTest::test_convert_and_refusals` | F → kN: [0, 1.257, 2.514]; T → K: [293.15, 294.15, 295.15]; mm → µm with *keep original*; force → MPa refused; a formula with the wrong dimension refused. |
| `sdk/python/tests/test_labdataset.py::DatasetTest::test_temperature_offset_and_difference` | Offset for temperatures, no offset for differences. |

## 6. Formula columns

Code: `daten/datasets.py` (`formula`), `sdk/python/labcalc/expr.py`.

* A formula is parsed with the Calculator's expression parser and evaluated in **SI units**.
* Dimensions are checked strictly. The dimension of the result must equal the dimension of the target unit;
  otherwise the formula is refused.
* Constants need identifier names and must not shadow a column key. A constant can be typed or taken from a cell.
* A complex result is an error. A non-finite result is stored as NaN.
* Options: `replaces` (the new column replaces an existing one) and `keep`.

**Validation**

| Test | Expected |
|---|---|
| `…/test_datasets.py::DeriveTest::test_formula_n_to_mpa_replaces_column` | `σ = F / A0` gives [0, 100, 200] MPa with kind `pressure` and replaces the column. |

## 7. Cleaning steps

Code: `daten/clean.py`. Steps run after conversions and formulas, top to bottom. Each step records rows, flags and
excluded rows before and after (the Log). A step that would create more than 50 000 flags is refused with an error.
Row numbers are 1-based on the page and 0-based internally.

| Step | What it computes | Defaults and rules |
|---|---|---|
| Keep a row range | Keeps rows *first* to *last*. | 1-based, both ends inclusive. |
| Filter rows | Keeps rows that satisfy a condition. | Numbers: `<`, `≤`, `>`, `≥`, `=`, `≠`, between, has a value. Rows with NaN in the column are always dropped by a numeric filter. Text: `=`, `≠`, contains (case-insensitive), not empty. |
| Sort | Stable sort by one column. | Numbers: NaN last in both directions. Text: stable; descending is the reversed ascending order, so empty text comes first when ascending. |
| Drop empty rows | Drops rows where all chosen columns are empty. | Default: all number columns. |
| Flag duplicates | Flags rows whose chosen columns equal an earlier row exactly. | Default: all columns. The first occurrence is not flagged. Reason "wie Zeile N". Nothing is removed. |
| Average replicates | Groups rows with exactly equal *by* values and averages the chosen columns. | See below. |
| Smooth (Savitzky–Golay) | Local polynomial smoothing. | See below. |
| Join another dataset | Interpolates columns of a second dataset onto x. | See below. |
| Flag outliers | See [section 8](#8-outlier-tests). | |
| Exclude (with reason) | See [section 9](#9-exclusion-semantics). | |

Flags follow their rows through filtering, sorting and trimming.

### Average replicates

* Rows are grouped by exact equality of the *by* columns. Excluded rows are not averaged. A group whose rows are
  all excluded is dropped.
* For each value column:
  * mean x̄ = Σxᵢ / n
  * standard deviation s = √(Σ(xᵢ − x̄)² / (n − 1)); NaN if n ≤ 1
  * n = number of finite values
  * standard error SE = s / √n
* SE becomes the uncertainty of the mean column; the SE column has `u_type` = `se`.
* Uncertainty and text columns that are neither *by* nor value columns are dropped.
* For temperatures, s and SE get the kind "temperature difference".
* **Flags go to the means** (since 0.3.0; before, all flags were cleared). For each group, every flag of a used
  (not excluded) row on a kept column, or without a column, becomes one flag of the same code on the mean row, with
  the rule "Mittelwert enthält markierte Werte (<first rule>)" and the reason "aus Zeile(n) …" (1-based source rows).
  So a mean that contains a value at the detection limit, an unexcluded outlier, an interpolated or converted value
  keeps that information. Flags of cells without a value (`missing`, `parse_error`, or NaN) are not carried: those
  cells only reduce n. Flags of columns that are dropped are counted in the step text. Excluded rows were already
  left out of the means and are named in the step text.

### Smooth (Savitzky–Golay)

* Window w (default 11; odd; ≥ 3) and polynomial order p (default 2; 0 ≤ p < w − 1).
* Coefficients come from the pseudo-inverse of the Vandermonde matrix of the window.
* At the edges, a polynomial is fitted to the first and the last window (as scipy `savgol_filter` with
  `mode="interp"`).
* Only runs of finite values with length ≥ w are smoothed.
* A warning is issued when x is not equally spaced (largest deviation > 1 % of the median step).
* By default the original stays and a new column `<key>_sg` is added.
* Reference as cited in the code (`savitzky1964`): Savitzky, Abraham; Golay, Marcel J. E. 1964. "Smoothing and
  Differentiation of Data by Simplified Least Squares Procedures". Analytical Chemistry 36, 1627-1639.
  doi:10.1021/ac60214a047.

### Join another dataset

* Only used rows of the other dataset are taken. Its x is converted to the unit of x here. For duplicate x values,
  the first one is kept.
* Linear interpolation (`numpy.interp`). Outside the range of the other x the value is NaN (no extrapolation).
* Rows whose x is not exactly an x of the other dataset get an `interpolated` flag (at most 20 000 per column; when
  more rows are interpolated, the step text says "GEKÜRZT: …" with the count).
* A note "linear interpoliert aus … v…" names the source dataset and its version. The dataset provenance lists the
  joined dataset and its version under `inputs`; they are part of the version signature and of the provenance chain.

**Validation**

| Test | Expected |
|---|---|
| `…/test_clean.py::CleanTest::test_trim_filter_sort_drop` | Row range, filters, sort order and empty rows. |
| `…/test_clean.py::CleanTest::test_flags_follow_rows` | Flags stay with their rows. |
| `…/test_clean.py::CleanTest::test_duplicates_flagged_not_removed` | Duplicates flagged, row count unchanged. |
| `…/test_clean.py::CleanTest::test_replicates` | Means k = [1.1, 2.1, 3.0]; s = √0.02; SE = 0.1; n = [2, 2, 1]. |
| `…/test_clean.py::CleanTest::test_replicates_default_leaves_uncertainty_out` | Uncertainty columns are not averaged. |
| `…/test_clean.py::ScientificFixesTest::test_replicate_means_keep_flags` | An outlier in row 2 and a `below_lod` in row 6 go to the means of their groups ("aus Zeile(n) 2", "aus Zeile(n) 6"); the missing cell and the excluded row give no flag; SE has `u_type` `se`. |
| `…/test_clean.py::CleanTest::test_join_interpolates_and_labels` | Result [300, 305, …, 330, nan]; rows 1, 3, 5 flagged `interpolated`. |
| `…/test_clean.py::CleanTest::test_smooth_savgol` | Equal to scipy `savgol_filter(mode="interp")` within 1e-10 when scipy is installed; error against the true curve < 0.05. |
| `…/test_clean.py::CleanTest::test_replay_gives_same_dataset` | Steps replay to the same dataset. |

## 8. Outlier tests

Code: `daten/clean.py` (`op_outliers` and the test functions).

Common rules for all tests:

* Only **non-excluded** rows are tested.
* Optionally, each group (exact values of a *by* column) is tested separately.
* A test only **flags** values (code `outlier`, with column, rule and reason). It never removes or excludes a row.
* Missing values are left out of the test.

| Test | Statistic | Default | Minimum n | Iterated |
|---|---|---|---|---|
| Grubbs | G = max\|xᵢ − x̄\| / s | α = 0.05 per step, two-sided | 3 | sequential (default) or single pass |
| Dixon Q | r₁₀ = gap / range | two-sided α = 0.05 (0.10, 0.05, 0.01); one-sided α 0.05, 0.025, 0.005 | 3 (maximum 10) | no |
| Tukey / IQR | fences Q1 − k·IQR, Q3 + k·IQR | k = 1.5 | 4 | no |
| Hampel / MAD | \|xᵢ − median\| > k · 1.4826 · MAD | k = 3, whole column | 3 | no |
| Fit residual | externally studentised residual | degree 1, k = 3 (rule of thumb) | degree + 3 | yes, at most max(1, ⌊n/4⌋) points |

k must be greater than 0 (refused otherwise).

### Statistical helpers

* Student t quantiles: the regularized incomplete beta function by continued fraction, inverted by bisection on
  [−1000, 1000] until the interval is narrower than 10⁻¹².
* Quartiles: `numpy.percentile` with its default linear interpolation, which is sample quantile **definition 7** of
  Hyndman and Fan (1996).

### Grubbs

* s is the sample standard deviation (n − 1).
* Sides: two-sided (largest |xᵢ − x̄|), *max* (largest value) or *min* (smallest value).
* Critical value:

  G_crit = ((n − 1) / √n) · √( t² / (n − 2 + t²) )

  with t = t₁₋α/(2n), n−2 for the two-sided test and t = t₁₋α/n, n−2 for a one-sided test.
* **Sequential procedure (default, "sequenziell (α je Schritt)")**: if G > G_crit, the point is flagged, set aside,
  and the test is repeated on the rest with the **same α in every step**, until a step is not significant, n < 3 or
  s = 0. There is no cap on the number of steps. The flag reason names the step ("Schritt 2"), and the rule reads
  "α = 0,05 je Schritt, …, sequenziell". This is repeated application of a single-outlier test, as discussed in
  ASTM E178 (edition not checked; not cited in the bundle). Its error rate is **not controlled at α** as a whole:
  under the null hypothesis the first step has level α, but once a real outlier has been set aside each further step
  can flag a good value with probability about α, and masking and swamping are not controlled. When more than one
  value is flagged, the step text adds "sequenziell mit α je Schritt – die Fehlerrate des ganzen Verfahrens ist
  nicht α". For a procedure with a stated overall level, use the generalized ESD test (not implemented).
* **Single pass** (untick "sequenziell"; `iterate: false`): only the most extreme value is tested once at α.
* The flag stores α.
* References as cited in the code: `grubbs1969` Grubbs, Frank E. 1969. "Procedures for Detecting Outlying
  Observations in Samples". Technometrics 11, 1-21. doi:10.1080/00401706.1969.10490657; and `nist-esh` NIST/SEMATECH.
  "e-Handbook of Statistical Methods". https://www.itl.nist.gov/div898/handbook/, doi:10.18434/M32189 (accessed
  2026-11-17). The e-Handbook is cited for the Grubbs test (it has a section on it, with the example used in the
  tests); since 0.3.0 it is no longer cited for the fit residual.

### Dixon Q

* Only the r₁₀ ratio is used for every n from 3 to 10:

  Q_low = (x₍₂₎ − x₍₁₎) / (x₍ₙ₎ − x₍₁₎), Q_high = (x₍ₙ₎ − x₍ₙ₋₁₎) / (x₍ₙ₎ − x₍₁₎)

* n outside 3–10 is an error. A range of 0 gives no flags.
* Critical values (table `DIXON_Q` in `clean.py`, attributed to Rorabacher 1991):

  | n | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
  |---|---|---|---|---|---|---|---|---|
  | α = 0.10 | 0.941 | 0.765 | 0.642 | 0.560 | 0.507 | 0.468 | 0.437 | 0.412 |
  | α = 0.05 | 0.970 | 0.829 | 0.710 | 0.625 | 0.568 | 0.526 | 0.493 | 0.466 |
  | α = 0.01 | 0.994 | 0.926 | 0.821 | 0.740 | 0.680 | 0.634 | 0.598 | 0.568 |

  **Not checked against the publication** (it was not available when this was written). The values were checked
  numerically instead: for a normal parent,
  P(Q_high > c) = n(n − 1) ∫∫_{a<b} φ(a) φ(b) [Φ(b − c(b − a)) − Φ(a)]^(n−2) da db, and the two-sided level is
  α = P(max(Q_low, Q_high) > c) ≈ 2 P(Q_high > c) (both ends exceed c only when c < 0.5, with probability below
  10⁻⁴ here). Solving for c (grid quadrature and, for n = 3–7, adaptive integration; a Monte Carlo simulation
  agrees) reproduces every table value within 0.003 **as two-sided levels**, except **n = 4, α = 0.01**: the table
  has 0.926, the computation gives 0.921. The table value is kept (not replaced by a computed one); at n = 4 it is
  slightly conservative. Computed values, for reference:

  | n | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
  |---|---|---|---|---|---|---|---|---|
  | α = 0.10 | 0.9413 | 0.7655 | 0.6424 | 0.5624 | 0.5074 | 0.4671 | 0.4362 | 0.4118 |
  | α = 0.05 | 0.9702 | 0.8297 | 0.7102 | 0.6275 | 0.5689 | 0.5256 | 0.4922 | 0.4656 |
  | α = 0.01 | 0.9940 | 0.9207 | 0.8232 | 0.7427 | 0.6811 | 0.6336 | 0.5963 | 0.5661 |

* **Sides.** α in the table is two-sided. *Two-sided* (default): the end with the larger ratio is tested, and only
  that end can be flagged (before 0.3.0 both ends were compared with the two-sided value and both could be flagged).
  *Only maximum* / *only minimum*: that end is tested one-sided at α, using the two-sided column 2α, so the one-sided
  levels are 0.05, 0.025 and 0.005.
* **Untabulated α is refused** with "Dixon: α = … ist für den … Test nicht tabelliert … – kein Ersatzwert" (before
  0.3.0 the 0.05 column was used silently). The page offers only the tabulated levels for the chosen side.
* Not iterated.
* References as cited in the code: `dean1951` Dean, R. B.; Dixon, W. J. 1951. "Simplified Statistics for Small
  Numbers of Observations". Analytical Chemistry 23, 636-638. doi:10.1021/ac60052a025; and `rorabacher1991`
  Rorabacher, David B. 1991. "Statistical Treatment for Rejection of Deviant Values: Critical Values of Dixon's Q
  Parameter and Related Subrange Ratios at the 95% Confidence Level". Analytical Chemistry 63, 139-146.
  doi:10.1021/ac00002a010.

### Tukey / IQR

* IQR = Q3 − Q1. Values outside [Q1 − k·IQR, Q3 + k·IQR] (Tukey's fences) are flagged.
* Quartiles: `numpy.percentile` with linear interpolation, i.e. Hyndman–Fan definition 7 (position (n − 1)p + 1).
  These are **not** Tukey's hinges, so the fences can differ slightly from a textbook box plot: for 1, 2, …, 8 the
  quartiles are 2.75 and 6.25, the hinges 2.5 and 6.5. The rule text says "Quartile nach Hyndman–Fan Typ 7".
* References as cited in the code: `tukey1977` Tukey, John W. 1977. Exploratory Data Analysis. Addison-Wesley (for
  the fences); `hyndman1996` Hyndman, Rob J.; Fan, Yanan 1996. "Sample Quantiles in Statistical Packages". The
  American Statistician 50, 361-365 (for the quartile definition; no DOI given because it was not verified).

### Hampel / MAD

* MAD = median(|xᵢ − median(x)|). A value is flagged when |xᵢ − median| > k · 1.4826 · MAD.
* If MAD = 0, nothing is flagged.
* 1.4826 ≈ 1/Φ⁻¹(0.75) scales the MAD to estimate σ of a normal distribution.
* Window w = 0 (default): one median and MAD for the whole column (or group).
* Window w > 0 **by position** (no x column chosen): the median and MAD are taken over the w finite values before
  and after each point, truncated at the ends. The spacing of x is ignored; the rule text says "nach Position,
  x-Abstand nicht berücksichtigt".
* Window w > 0 **in x units** ("Fenster in" an x column; `x` in the step): the window of point i holds all finite
  values with |xⱼ − xᵢ| ≤ w, so unequal spacing and gaps are respected. Values without a finite x are not tested
  (counted in the step text).
* Reference as cited in the code: `hampel1974` Hampel, Frank R. 1974. "The Influence Curve and Its Role in Robust
  Estimation". Journal of the American Statistical Association 69, 383-393. doi:10.1080/01621459.1974.10482962.
  Whether this paper is the best source for the MAD-based identifier as implemented (moving window, factor 1.4826)
  was **not checked** against its content.

### Fit residual

* A polynomial of degree d (default 1) is fitted by least squares in centred and scaled x. Leverages hᵢᵢ come from
  the QR decomposition.
* With residuals eᵢ, SSE = Σeᵢ² and p = d + 1 parameters:

  s²₍ᵢ₎ = (SSE − eᵢ² / (1 − hᵢᵢ)) / (n − p − 1)

  tᵢ = eᵢ / √( s²₍ᵢ₎ · (1 − hᵢᵢ) )

  tᵢ = 0 if hᵢᵢ ≥ 1 − 10⁻⁹ or s²₍ᵢ₎ ≤ 0.
* The point with the largest |tᵢ| is flagged if |tᵢ| > k (default 3). The fit is repeated without it. At most
  max(1, ⌊n/4⌋) points are flagged. The loop needs n − p − 1 ≥ 1.
* n < d + 3 is an error.
* tᵢ is the externally studentised (deleted) residual; k is a threshold on |tᵢ|. The default 3 is a **rule of
  thumb**, not a significance level: under normal errors each |tᵢ| follows a t distribution with n − p − 1 degrees of
  freedom, but no correction is made for testing n points, so the chance of at least one false flag grows with n.
  The rule text says "extern studentisiertes Residuum |t| > k = 3, Faustregel, kein Signifikanzniveau".
* If the polynomial cannot follow the curve, the ends of the curve are flagged. Choose the degree to suit the data.
* No source is cited (before 0.3.0 the NIST e-Handbook was cited here; whether it covers deleted residuals with this
  threshold was not verified, so the citation was dropped).

**Validation**

| Test | Expected |
|---|---|
| `…/test_clean.py::OutlierTest::test_t_quantile` | t₀.₉₇₅,₁₀ = 2.228139; t₀.₉₉₅,₃ = 5.840909. |
| `…/test_clean.py::OutlierTest::test_grubbs_nist_example` | NIST e-Handbook example data (Tietjen–Moore): G = 2.4687; one-sided 5 % critical value 2.032; the value at index 7 is flagged. |
| `…/test_clean.py::OutlierTest::test_dixon_example` | n = 10, Q = 0.4545: flagged at α = 0.10 (0.4545 > 0.412), not at α = 0.05 (≤ 0.466); n = 11 raises an error. |
| `…/test_clean.py::OutlierTest::test_iqr_hampel_residual` | IQR and Hampel flag index 5; fit residual with k = 2.5 flags index 4; a masked outlier is found at index 10 with degree 3. |
| `…/test_clean.py::OutlierTest::test_by_group` | Dixon per group flags row 4. |
| `…/test_clean.py::OutlierTest::test_flags_never_remove_rows_and_exclusion_is_separate` | Flagging keeps the row count; only exclusion changes the used rows. |
| `tools/e2e_datasets.py` | Fit residual (degree 3, k = 3) on a test sheet flags row 11; the methods text calls k a rule of thumb and cites no source for it. |
| `…/test_clean.py::ScientificFixesTest::test_dixon_untabulated_alpha_refused_and_sides` | α = 0.02, 0.2, 0.001 (two-sided) and 0.01 (one-sided) refused; two-sided flags only the low end (Q = 0.455) of the n = 10 example; one-sided *min* at 0.05 uses 0.412 and flags it, at 0.025 (0.466) not; with Q_low = 0.45 and Q_high = 0.46 (both > 0.412) only the high end is flagged. |
| `…/test_clean.py::ScientificFixesTest::test_dixon_table_matches_null_distribution` | The integral above (grid quadrature, scipy `ndtr`; skipped without scipy) puts the true two-sided critical value within ±0.003 of each table value, and between 0.918 and 0.924 for n = 4, α = 0.01. |
| `…/test_clean.py::ScientificFixesTest::test_grubbs_sequential_and_single_pass` | NIST example flags index 7 in both modes; rule texts "je Schritt … sequenziell" and "ein Durchgang". |
| `…/test_clean.py::ScientificFixesTest::test_iqr_quartiles_are_hyndman_fan_type_7` | 1 … 8, 30: Q1 = 3, Q3 = 7, fences −3 and 13, only 30 flagged; 1 … 8 with k = 1: fences 2.75 − 3.5 and 6.25 + 3.5. |
| `…/test_clean.py::ScientificFixesTest::test_hampel_window_in_x_units` | x = 0, 1, 2, 3, 10 … 14 and y with 9.0 at x = 14: window ±2 in x flags only the last point (median 5.0, MAD 1.4826 · 0.1, 3 values); ±1.5 flags nothing; the positional rule text says the x spacing is ignored. |
| `…/test_clean.py::ScientificFixesTest::test_residual_rule_text` | Rule text names the studentised residual and the rule of thumb; k ≤ 0 refused. |

## 9. Exclusion semantics

Code: `daten/clean.py` (`exclude`), `sdk/python/labdataset.py` (`used_mask`).

* **Flags never delete rows.** A flag only describes a value.
* Only the step **Exclude (with reason)** takes rows out of the evaluation. A reason is required (at most 300
  characters).
* Exclusion by rows: each named row gets the code `excluded`. Existing flags on that row (optionally only in one
  column) are changed to `excluded` and the reason is appended. A row without flags gets a new `excluded` flag.
* Exclusion by codes: all flags with the chosen codes (optionally one column, optionally a rule text) become
  `excluded`.
* A row with any `excluded` flag is not *used* (`used_mask` is False). Excluded rows stay in the dataset.
* The Calculator, the Elemental Calculator, TGA and FTIR leave out excluded rows. The Calculator and the Elemental
  Calculator also leave out rows with a gap in any chosen column.
* The CSV export contains all rows and, by default, the columns "verwendet" (1/0) and "Markierungen" (see
  [Exports](#12-exports)).

**Validation**

| Test | Expected |
|---|---|
| `…/test_clean.py::OutlierTest::test_flags_never_remove_rows_and_exclusion_is_separate` | Row count unchanged by flags; excluded rows not used. |
| `tools/e2e_datasets.py` | Two rows excluded; the step log counts them; the Calculator uses 12 rows; the Elemental Calculator drops the 2 excluded rows; the methods text names the exclusions. |

## 10. Checks

Code: `daten/clean.py` (`checks`). Shown as chips for every version.

| Check | Rule |
|---|---|
| Rows | read, used, excluded |
| Missing | missing values in used rows; uncertainty columns are not counted |
| Flags | count per code; a warning for `parse_error` and for outliers without a decision |
| x monotonic | the x column (role x, otherwise the first number column) |
| Gaps | a step \|Δx\| > 3 × median \|Δx\| |
| n per group | for group, label and text condition columns with 2–60 distinct values; a warning if n < 3 |
| Impossible values | negative SI values for kinds that cannot be negative: mass, area, volume, amount, concentration, mass concentration, density, molar mass, frequency, (absolute) temperature, rate constant, activity, resistance. **Length is not checked** (positions, displacements and ΔL are signed). Columns whose name, symbol or key marks a difference or change are skipped for every kind: a leading Δ, δ, ∆ or "d" followed by a capital letter (dL, dT; case-sensitive, so "Dichte" is still checked), "delta", or a word such as Änderung, Differenz, Verschiebung, Verlust, Zunahme, Abnahme, change, difference, displacement, shift, loss, gain, drift. Uncertainty columns are skipped. |
| Type of uncertainty | for every uncertainty column: its `u_type` text; a warning while it is "nicht angegeben" |
| Units | number columns without a unit |

Tests: `…/test_clean.py::OutlierTest::test_checks`, `…/test_clean.py::ScientificFixesTest::test_signed_quantities_not_impossible`
(ΔL, a position and "Massenänderung" with negative values give no chip; a negative mass and a negative density do),
`…/test_clean.py::ScientificFixesTest::test_uncertainty_type_chip`.

## 11. Templates and batches

Code: `daten/templates.py`, `daten/server.py`.

* A template stores the marks and **anchors**: texts of header and units rows and metadata labels (at most 80).
  Anchors are compared after collapsing whitespace and ignoring case.
* When a template is applied, the data block grows or shrinks: it continues while rows hold numbers and stops at an
  empty row or after more than 2 rows with text only. Blocks that repeat keep their fixed length.
* If an anchor does not match, the template is refused with the cell, the expected and the found text.
* At most 200 templates; names are unique ignoring case. Stored in `outputs/datenaufbereitung/datenaufbereitung_vorlagen.json`.
* A batch takes at most 200 files.
  * **One dataset per file**: title "<template> – <file>". A second run publishes new versions of the same datasets.
  * **One combined dataset**: a column "Datei" with role group. Columns are matched by name. Different data types
    are refused. A column in another unit of the same quantity is converted to the unit of the first file
    (uncertainties and temperature differences without offset); incompatible units are refused. Missing columns
    stay empty, with a note. Conditions that are equal in all files stay conditions. Numeric conditions that differ
    and share a unit become a number column; others become a text column.
  * The provenance of a combined dataset lists all files and the template steps, not the steps as fitted to each
    file.

**Validation**

| Test | Expected |
|---|---|
| `…/test_share.py::TemplateTest::test_template_reads_b_and_c_refuses_moved_header` | A template reads two other files and refuses one with a moved header. |
| `…/test_share.py::TemplateTest::test_combine_with_file_column` | Combined dataset with a "Datei" column. |
| `…/test_share.py::TemplateTest::test_combine_converts_same_quantity` | Same quantity in another unit is converted. |
| `…/test_share.py::ShareServerTest::test_template_batch_export_bundle` | Batch per file gives [20, 6] rows; a second run leaves the data unchanged; the combined dataset has 36 rows. |

## 12. Exports

Code: `daten/export.py`.

| Format | Content |
|---|---|
| CSV | Header "name [unit]", comma separator, full float precision (`repr`), empty for NaN. All rows. By default two columns follow the data: **"verwendet"** (1 = used, 0 = excluded by a recorded decision) and **"Markierungen"** (every flag of the row: kind, column, "ausgeschlossen: reason" or the reason). Request `flags: false` for the data columns only. Re-import drops the two columns. |
| XLSX | Sheet "Daten": names row, units row, values. Sheet "Protokoll": title, rows, columns, SHA-256 of the data, source files with SHA-256, sheet and ranges, reading recipe, cleaning steps with row counts, conditions, truncations ("GEKÜRZT"), columns with the type of uncertainty, flags (at most 100 000; a line says when more exist – all are in JSON). |
| JSON | `{schema, header, data}`. Lossless. On re-import the data hash is checked. |
| Parquet | Optional (pyarrow, see [Readers](#1-readers)). Columns "name [unit]" as float64 or string. The full dataset header is in the schema metadata key `suite.dataset`. |

An unknown format is refused with HTTP 400. Round trips are compared with a relative tolerance of 10⁻¹².

**Validation**

| Test | Expected |
|---|---|
| `…/test_share.py::ExportTest::test_round_trips` | CSV, XLSX and JSON (and Parquet when pyarrow is installed) read back to the same dataset. |
| `…/test_share.py::ExportTest::test_csv_keeps_cleaning_state` | The excluded row ends with `0,Ausreisser in c (ausgeschlossen: Luftblase)`, a used row with `1,`; `flags=False` has no such columns; re-import equals the dataset. |
| `…/test_share.py::ExportTest::test_parquet_round_trip` | Parquet round trip (skipped without pyarrow). |
| `…/test_share.py::ExportTest::test_parquet_without_pyarrow` | With pyarrow unavailable, Parquet export raises the German message. |
| `…/test_share.py::ShareServerTest::test_template_batch_export_bundle` | Through the server: exports give HTTP 200; Parquet without pyarrow gives HTTP 400 with the German message (no `ModuleNotFoundError`); an unknown format gives 400; `flags: false` works. |
| `…/test_share.py::ExportTest::test_xlsx_protocol_sheet` | "Protokoll" sheet content. |
| `tools/e2e_datasets.py` | Exports round-trip in the full chain. |

## 13. Dataset versioning and derived datasets

Code: `daten/datasets.py`, `sdk/python/labshare.py`, `sdk/python/labdataset.py`. Details of storage and integrity are
in [provenance.md](provenance.md).

* Saving publishes a new **version** only if the signature changed (`datasets._sig`): data hash, **flags hash**
  (flags and exclusions, see [provenance.md](provenance.md)), title, column key, name, unit, role, kind, symbol,
  uncertainty link, note and uncertainty type; conditions; for a derived dataset the parent and parent version and
  the joined datasets with their versions; or the dataset meta. Since 0.3.0 a change of flags or exclusions alone
  gives a new version, and a live child whose result differs only in flags is published again.
* Version numbers are never reused, also after a version was deleted (tombstones, see provenance.md).
* Autosave runs 4 s after the last change, and only if something changed.
* A dataset made with **Convert and clean** is a *derived* dataset. It stores its parent, the parent version, the
  mode (follow or pinned) and the operations (at most 40).
* **Follow** (live): when the parent gets a new version, the child is computed again. Chains up to 6 levels are
  followed. If a step fails, the child keeps its last version and stores the error.
* **Pinned**: the child stays at its parent version until the user brings it to the new one.
* The provenance of a derived dataset records each step with rows, flags and excluded rows before and after, the
  provenance of the parent, and the module version of the process that computed it. Its provenance chain shows the
  derivation and then the parent's full chain down to the raw file (see provenance.md).

### Report bundle and Refresh

* "In den Bericht" offers two choices: **this version** (`mode: "pin"`, default) and **newest version**
  (`mode: "live"`). The mode is stored in the bundle request.
* Refresh of a *pinned* bundle rebuilds the same version (from the dataset kept in the bundle, else from the
  project). Bundles made before 0.3.0 have no mode and are treated as pinned.
* Refresh of a *live* bundle loads the newest version of the dataset from the active project. If it is newer, the
  summary and the methods text say "Aktualisiert: Datensatz … von Version a auf die neueste Version b". If the
  newest version cannot be read, the kept version is used and that is said instead.
* The bundle carries `module_version` (this process) and `source.kind = "dataset"`: the file kept under `source/`
  is the dataset version (`datensatz.json`), so the report's `source_sha256` is the hash of that version, not of the
  raw file (that hash is in the dataset provenance).
* The methods text also states the type of uncertainty of each uncertainty column, every truncation ("GEKÜRZT")
  and the daylight-saving warnings of the dataset.

**Validation**

| Test | Expected |
|---|---|
| `…/test_datasets.py::DatasetServerTest::test_flag_only_change_is_a_new_version_and_live_child_follows` | Same values with a new exclusion → version 2 (`data_hash` equal); the live child gets version 2 with the exclusion; publishing again is unchanged; the recomputed child records module version 9.9.9 (the recomputing process), its first version 0.3.0. |
| `…/test_share.py::BundleTest::test_bundle_pieces_and_pdflatex_safety` | `module_version`, `source.kind = "dataset"`, mode `pin`; NIST e-Handbook with doi 10.18434/M32189 in the bib for Grubbs; "Art der angegebenen Unsicherheit: c: nicht angegeben". |
| `…/test_share.py::BundleTest::test_bundle_states_uncertainty_type_and_refresh_note` | "erweiterte Unsicherheit U (k = 2)" and the refresh note in the methods text; summary "folgt der neuesten Version". |
| `…/test_share.py::ShareServerTest::test_template_batch_export_bundle` | After a new version of the share, a pinned bundle refreshes to the old version, a live bundle to the new one with "von Version a auf die neueste Version b". |
| `…/test_datasets.py::DatasetServerTest::test_publish_versions_open_and_live_child` | Saving unchanged data keeps the version; a live child follows to v2; a pinned child moves to v2 on request; a broken formula keeps the latest version 1 and records an error. |
| `…/test_datasets.py::DatasetServerTest::test_connected_table_follows_in_place` | A live connected table is replaced in place. |

---

## Changes in 0.3.0

Results that can differ from 0.2.0 when the same data are processed again:

| Where | 0.2.0 | 0.3.0 |
|---|---|---|
| Dixon, α not 0.10/0.05/0.01 | 0.05 column used silently | refused with a message |
| Dixon, two-sided | both ends compared with the two-sided value; both could be flagged | only the end with the larger ratio |
| Dixon, sides | – | *only maximum* / *only minimum* at one-sided α 0.05, 0.025, 0.005 |
| Average replicates | all flags cleared | flags carried to the means ("aus Zeile(n) …") |
| Impossible values | negative lengths and Δ-columns flagged as impossible | lengths and difference/change columns not checked |
| Times with an offset (`+01:00`, `Z`) | offset ignored | converted to UTC |
| Local times across a DST change | no notice | warning on the page, in the provenance and the methods text |
| ODS: value after > 1 024 repeated empty cells | moved left to the wrong column | stays in its column |
| Reading flags per column | raw text for the first 5 000 unreadable cells, flags for 20 000 cells, the rest dropped without a note | up to 200 000 per column and kind; any cut is reported and stored |
| Flags only changed | no new version; live children not republished | new version; live children republished |
| CSV export | no cleaning state | columns "verwendet" and "Markierungen" (default) |
| Fit residual citation | NIST e-Handbook | no source (rule of thumb stated) |
| IQR citation | Tukey 1977 | Tukey 1977 and Hyndman & Fan 1996 (quartile definition) |
| NIST citation | no DOI | doi:10.18434/M32189 |
| Bundle Refresh | always the same version | pinned (default) or newest version, with a note |

## Measurement uncertainty

Code: `daten/uncert.py`.

**± columns → standard uncertainty.** The numbers of an uncertainty column stay as read, with their stated type. Where
an uncertainty is used, it is converted per row into a standard uncertainty u in the unit of its value column
(`uncert.std_u`; the factor comes from `labcalc.uncertainty.standard_u`):

| `u_type` | u | Source |
|---|---|---|
| `u` | as given | JCGM 100:2008, 2.3.1 |
| `se` | as given (standard uncertainty of the mean) | JCGM 100:2008, 4.2.3 |
| `U` (with k) | U/k | JCGM 100:2008, 4.3.3 |
| `sd` | s (standard uncertainty of a single value; for a mean of n values choose `se`) | JCGM 100:2008, 4.2.2 |
| `ci` (with level p) | half-width / z₍₁₊ₚ₎/₂ (normal distribution assumed, ν unknown; 1.96 at 95 %) | JCGM 100:2008, 4.3.4 |
| not stated | not used | – |

An uncertainty column in another unit of the same dimension is scaled without offset (µm against mm, K against °C).
The check chip of the column and the methods text name the conversion ("→ u = U/k mit k = 2 (JCGM 100:2008, 4.3.3)").

**Repeated measurement (`uncert.repeats`, route `/api/repeat`).** The numbers of the selected cells (at most
10 000): mean x̄, s with n − 1, u = s/√n, ν = n − 1 (type A, JCGM 100:2008, 4.2.2–4.2.3). The page keeps it with the
file and offers it as a value with `u` in the value catalogue of the environment.

**Formula columns (`uncert.formula_u`).** If the columns named in a formula have a standard uncertainty, the new
column gets an uncertainty column `u(name)` (`u_type` `u`, linked with `u`). Per row,
u²(y) = Σ (∂f/∂xᵢ)² u²(xᵢ) with central differences (step uᵢ/100) in SI (`labcalc.uncertainty.gum_rows`, first order,
inputs independent, JCGM 100:2008, 5.1.2). Constants are exact. A row whose input has a value but no u, or whose result
is missing, gets no u. The step `{"unc": false}` switches this off.

**Type-B column (step `{"op": "unc", "col", "parts"}`).** The parts are the shared input format of
`labcalc.uncertainty` (instrument classes of the shared library with their sources, limits ±a with a distribution,
resolution, % of value, manufacturer spec). u_B is evaluated per distinct value (at most 100 000) and written to
`u_B(name)`; if the column already had a usable uncertainty, `u(name) gesamt` = √(u² + u_B²) is added and becomes the
linked column (rows without a stated ± use u_B alone).

**Report.** Table `unsicherheiten` (column, uncertainty column, conversion, n, median u, median u/|x|); a methods
sentence that uncertainties are standard uncertainties, how formula and type-B columns got theirs, citing JCGM 100
and the sources of the instruments; error bars in the figure show ±u (as given while the type is not stated).

**Validation.**

| Test | Checks |
|---|---|
| `modules/datenaufbereitung/tests/test_uncertainty.py::Conversion::test_factors` | U/k = 0.5 for k = 2; 1/1.959964 at 95 %; s, SE as is; not stated → none |
| `…::test_pm_column_converts` | `1,5 ± 0,2` with U, k = 2 → u = 0.1; µm against mm; chip text |
| `…::test_repeats` | mean, s, s/√5, ν = 4 |
| `…::Derived::test_formula_column_u_matches_hand` | u(F·L) = √((L u_F)² + (F u_L)²) per row; missing u → no u; constant exact |
| `…::test_type_b_column` | a/√3; calliper class (MPE and reading) from the library; combined with a stated ± |
| `…::Report::test_bundle_shows_u_columns_and_method` | table, methods text with conversion, GUM and `unc-jcgm100` |
| `…::Routes::test_labunc_and_repeat` | `/labunc.js`, `/api/unc/instruments`, `/api/repeat` |

## Known limitations

* **Dixon table not checked against the publication.** The values agree with an independent computation of the
  null distribution within 0.003, except n = 4, α = 0.01 (0.926 vs 0.921); the table value is kept.
* **Dixon r₁₀ only**: the same ratio is used for all n from 3 to 10 (Dixon's r₁₁, r₂₁, r₂₂ for larger n are not
  implemented); one-sided tests are limited to α = 0.05, 0.025, 0.005.
* **Sequential Grubbs** uses the same α in every step. Its overall error rate is not α (see section 8); the
  generalized ESD procedure is not implemented. Use the single pass when one suspect value is tested.
* **Fit residual** uses a rule-of-thumb threshold k, not a significance level, and does not correct for testing n
  points. No source is cited.
* **IQR** quartiles are Hyndman–Fan type 7, not Tukey's hinges.
* **Hampel** by position ignores the x spacing; choose an x column for a window in x units.
* **Impossible values** are not checked for lengths at all, so a negative thickness or diameter is not warned. The
  difference-name rule is a heuristic on names and symbols.
* **Times without a zone** are taken as local wall-clock time. Daylight-saving changes are only *detected* (EU and
  USA/Canada rules since 1996/2007, three heuristics), never corrected. Other regions are not checked.
* **Uncertainty propagation** is first order with independent inputs (no correlation between columns or rows).
  A confidence interval is converted with the normal distribution (the number of values behind it is not known).
  Cleaning steps other than formulas (smoothing, joining, averaging) do not propagate a stated ±; averaging gives the
  standard error instead.
* **Caps** (all reported): 200 000 reading flags per column and kind; 20 000 `interpolated` flags per joined
  column; ODS filled-row repeats read 100 000 times; 100 000 flags listed in the XLSX "Protokoll"; 50 000 flags per
  cleaning step (refused).
* **Parquet** needs the optional package pyarrow.
* **`.xls`** reading has no test of its own.
* A column whose every cell is "value ± u" is guessed as a text label; mark it as y to read it.
* Step texts, notes and the methods text are in German, also in an English report.
