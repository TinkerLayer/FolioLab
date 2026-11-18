# Datenaufbereitung: methods and validation

This document describes what the Datenaufbereitung (Data Purification) module computes when it reads a file, marks
it, converts units, cleans rows and flags outliers. Every default and limit below is taken from the code in
`modules/datenaufbereitung/daten/` and `sdk/python/`. Every reference is given exactly as it appears in the code. Each
section ends with the tests that check it.

How the resulting numbers are traced back to the raw file in a report is described in
[provenance.md](provenance.md).

## How to cite

State the software and the module version:

> Data were prepared with Folio Lab 0.1.0, module Datenaufbereitung 0.2.0.

The Folio Lab version is in `package.json`; a report result records it as `provenance.suite_version`. The module version is in `modules/datenaufbereitung/module.json`
(`"version": "0.2.0"`, identical to `daten/__init__.py`). Every dataset also records the module version that read
the file (`provenance.module_version`). If you use an outlier test or smoothing, also cite the method source listed
in that section. The methods text in a report bundle does this automatically.

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
14. [Known limitations](#known-limitations)

Test paths below are relative to the project root. Module tests run with
`python -m unittest discover -s tests` from `modules/datenaufbereitung` with `PYTHONPATH=../../sdk/python;.`.

---

## 1. Readers

Code: `daten/readers.py`, `daten/sheet.py`, `sdk/python/labtable.py`.

| Format | How it is read |
|---|---|
| `.xlsx`, `.xlsm` | openpyxl, read-only, stored values (`data_only`). A formula without a cached value is read as empty and noted. Hidden sheets are noted. Merged ranges are read. |
| `.xls` | xlrd. |
| `.ods` | Python standard library (zip + XML). Repeated rows are capped at 100 000, repeated columns at 1 024. |
| `.csv`, `.txt`, `.tsv`, `.dat`, `.asc`, `.prn` | Text decoding and dialect detection as below. |
| `.json` | Own dataset format `suite.dataset/1`; pandas `split`, `columns`, `records`; plain rows. |
| `.parquet` | pyarrow. |
| Pasted cells | Cells copied from a spreadsheet. |

**Text decoding** (`labtable.decode`): a UTF-16 byte-order mark, or UTF-16 without one when detected, then
`utf-8-sig`, `cp1252`, `latin-1`, in that order.

**Dialect detection** (`labtable.sniff`): the delimiter is chosen among tab, `;`, `,` and space. A decimal comma is
assumed when more numbers parse with a comma than with a point. The longest numeric block is taken as data; a units
row and a header row above it are recognised.

**Limits**: a sheet holds at most 10 000 000 cells and 16 384 columns.

**Validation**

| Test | Checks |
|---|---|
| `modules/datenaufbereitung/tests/test_readers.py::FormatsTest::test_same_grid_from_every_format` | The same table written as xlsx, ods, csv, json and parquet gives the same cell grid. |
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
* The `±` value is stored as given. The code does not interpret it as a standard or an expanded uncertainty.
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

### Sequential entry (measurement sheets)

In the one-after-another entry, a line is split at line breaks, tabs, `;` and whitespace. A token with two or more
commas is split at the commas. A token with one comma is a decimal number. Tests:
`…/test_manual.py::ManualModelTest::test_parse_entry`, `…/test_manual.py::ManualServerTest::test_sequential_entry_routes`,
`…/test_manual.py::ManualServerTest::test_unit_info`.

## 3. Dates and times

Code: `daten/parse.py`, `daten/recipe.py`.

| Form | Example | Notes |
|---|---|---|
| ISO date-time | `2024-03-01 12:30`, `2024-03-01T12:30:05.5` | A time-zone suffix is accepted but **ignored**. |
| German date | `01.03.24`, `01.03.2024 12:30:05` | Two-digit years get +2000. |
| Time of day | `12:30`, `12:30:05` | Hours up to 47 are accepted. |
| Excel date cell | – | Read as a date. |

* A text column counts as a time column when at least 80 % of its filled cells parse and at least 2 cells are filled.
* **Elapsed time**: the first value is the start. The unit is chosen from the span: < 120 s → s; < 7 200 s → min;
  < 3 d → h; otherwise d.
* **Past midnight**: for times of day, a step backwards of more than 12 h adds one day.
* The start time is stored as a condition named "<column> Start".
* A date column whose finite values are all below 2 × 86 400 s is treated as time-of-day only.
* There is no time-zone or daylight-saving handling.

**Validation**

| Test | Expected |
|---|---|
| `…/test_clean.py::FormatTest::test_times` | `12:00:05` → 43 205 s; times 23:50, 00:00, 00:10 → [0, 10, 20] min with start 23:50:00. |
| `…/test_clean.py::FormatTest::test_colprop_symbol_kind_and_raw_time` | Symbol, quantity kind and raw time columns. |

## 4. From marked sheet to dataset

Code: `daten/recipe.py`, `sdk/python/labdataset.py`.

* The marks (data block, header rows, units row, roles, metadata cells, repeats, wide → long, transpose) form a
  **recipe**. The recipe is stored in the dataset's provenance and can be replayed.
* A column is a number column when numbers plus recognised markers make up at least 50 % of its filled cells.
* Unreadable cells become NaN with a `parse_error` flag. The raw text is kept for at most 5 000 unreadable cells
  per column. Flags are kept for at most 20 000 cells per column.
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
* SE becomes the uncertainty of the mean column.
* Uncertainty and text columns that are neither *by* nor value columns are dropped.
* For temperatures, s and SE get the kind "temperature difference".
* **All flags are cleared after averaging.**

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
* Rows whose x is not exactly an x of the other dataset get an `interpolated` flag (at most 20 000).
* A note "linear interpoliert aus … v…" names the source dataset and its version.

**Validation**

| Test | Expected |
|---|---|
| `…/test_clean.py::CleanTest::test_trim_filter_sort_drop` | Row range, filters, sort order and empty rows. |
| `…/test_clean.py::CleanTest::test_flags_follow_rows` | Flags stay with their rows. |
| `…/test_clean.py::CleanTest::test_duplicates_flagged_not_removed` | Duplicates flagged, row count unchanged. |
| `…/test_clean.py::CleanTest::test_replicates` | Means k = [1.1, 2.1, 3.0]; s = √0.02; SE = 0.1; n = [2, 2, 1]. |
| `…/test_clean.py::CleanTest::test_replicates_default_leaves_uncertainty_out` | Uncertainty columns are not averaged. |
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
| Grubbs | G = max\|xᵢ − x̄\| / s | α = 0.05, two-sided | 3 | yes |
| Dixon Q | r₁₀ = gap / range | α = 0.05 (0.10, 0.05, 0.01) | 3 (maximum 10) | no |
| Tukey / IQR | fences Q1 − k·IQR, Q3 + k·IQR | k = 1.5 | 4 | no |
| Hampel / MAD | \|xᵢ − median\| > k · 1.4826 · MAD | k = 3 | 3 | no |
| Fit residual | externally studentized residual | degree 1, k = 3 | degree + 3 | yes, at most max(1, ⌊n/4⌋) points |

### Statistical helpers

* Student t quantiles: the regularized incomplete beta function by continued fraction, inverted by bisection on
  [−1000, 1000] until the interval is narrower than 10⁻¹².
* Quartiles: `numpy.percentile` with linear interpolation.

### Grubbs

* s is the sample standard deviation (n − 1).
* Sides: two-sided (largest |xᵢ − x̄|), *max* (largest value) or *min* (smallest value).
* Critical value:

  G_crit = ((n − 1) / √n) · √( t² / (n − 2 + t²) )

  with t = t₁₋α/(2n), n−2 for the two-sided test and t = t₁₋α/n, n−2 for a one-sided test.
* If G > G_crit, the point is flagged, removed from the sample, and the test is repeated on the rest. This continues
  until no point exceeds G_crit, n < 3 or s = 0. There is no cap on the number of rounds. α is the same in every
  round.
* The flag stores α.
* References as cited in the code: `grubbs1969` Grubbs, Frank E. 1969. "Procedures for Detecting Outlying
  Observations in Samples". Technometrics 11, 1-21. doi:10.1080/00401706.1969.10490657; and `nist-esh` NIST/SEMATECH.
  "e-Handbook of Statistical Methods". https://www.itl.nist.gov/div898/handbook/ (accessed 2026-11-17).

### Dixon Q

* Only the r₁₀ ratio is used for every n from 3 to 10:

  Q_low = (x₍₂₎ − x₍₁₎) / (x₍ₙ₎ − x₍₁₎), Q_high = (x₍ₙ₎ − x₍ₙ₋₁₎) / (x₍ₙ₎ − x₍₁₎)

  Both ends are compared with the same critical value.
* n outside 3–10 is an error. A range of 0 gives no flags.
* Critical values (table `DIXON_Q` in `clean.py`, comment "Rorabacher (1991), Table"):

  | n | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
  |---|---|---|---|---|---|---|---|---|
  | α = 0.10 | 0.941 | 0.765 | 0.642 | 0.560 | 0.507 | 0.468 | 0.437 | 0.412 |
  | α = 0.05 | 0.970 | 0.829 | 0.710 | 0.625 | 0.568 | 0.526 | 0.493 | 0.466 |
  | α = 0.01 | 0.994 | 0.926 | 0.821 | 0.740 | 0.680 | 0.634 | 0.598 | 0.568 |

* Not iterated.
* If α is not one of 0.10, 0.05, 0.01, the table for 0.05 is used, but the rule text and the flag record the α that
  was entered (see Known limitations).
* References as cited in the code: `dean1951` Dean, R. B.; Dixon, W. J. 1951. "Simplified Statistics for Small
  Numbers of Observations". Analytical Chemistry 23, 636-638. doi:10.1021/ac60052a025; and `rorabacher1991`
  Rorabacher, David B. 1991. "Statistical Treatment for Rejection of Deviant Values: Critical Values of Dixon's Q
  Parameter and Related Subrange Ratios at the 95% Confidence Level". Analytical Chemistry 63, 139-146.
  doi:10.1021/ac00002a010.

### Tukey / IQR

* IQR = Q3 − Q1. Values outside [Q1 − k·IQR, Q3 + k·IQR] are flagged.
* Quartiles by linear interpolation (`numpy.percentile` default), not Tukey's hinges.
* Reference as cited in the code: `tukey1977` Tukey, John W. 1977. Exploratory Data Analysis. Addison-Wesley.

### Hampel / MAD

* MAD = median(|xᵢ − median(x)|). A value is flagged when |xᵢ − median| > k · 1.4826 · MAD.
* If MAD = 0, nothing is flagged.
* With a window w > 0, the median and MAD are taken over the w finite values before and after each point (by
  position, not by x distance), truncated at the ends.
* Reference as cited in the code: `hampel1974` Hampel, Frank R. 1974. "The Influence Curve and Its Role in Robust
  Estimation". Journal of the American Statistical Association 69, 383-393. doi:10.1080/01621459.1974.10482962.

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
* k is a fixed threshold. It is not converted from a significance level and has no correction for testing n points.
* If the polynomial cannot follow the curve, the ends of the curve are flagged. Choose the degree to suit the data.
* Reference as cited in the code: `nist-esh` (see Grubbs).

**Validation**

| Test | Expected |
|---|---|
| `…/test_clean.py::OutlierTest::test_t_quantile` | t₀.₉₇₅,₁₀ = 2.228139; t₀.₉₉₅,₃ = 5.840909. |
| `…/test_clean.py::OutlierTest::test_grubbs_nist_example` | NIST e-Handbook example data (Tietjen–Moore): G = 2.4687; one-sided 5 % critical value 2.032; the value at index 7 is flagged. |
| `…/test_clean.py::OutlierTest::test_dixon_example` | n = 10, Q = 0.4545: flagged at α = 0.10 (0.4545 > 0.412), not at α = 0.05 (≤ 0.466); n = 11 raises an error. |
| `…/test_clean.py::OutlierTest::test_iqr_hampel_residual` | IQR and Hampel flag index 5; fit residual with k = 2.5 flags index 4; a masked outlier is found at index 10 with degree 3. |
| `…/test_clean.py::OutlierTest::test_by_group` | Dixon per group flags row 4. |
| `…/test_clean.py::OutlierTest::test_flags_never_remove_rows_and_exclusion_is_separate` | Flagging keeps the row count; only exclusion changes the used rows. |
| `tools/e2e_datasets.py` | Fit residual (degree 3, k = 3) on a test sheet flags row 11. |

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
* The CSV export contains all rows and has no marker for excluded rows (see [Exports](#12-exports)).

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
| Impossible values | negative SI values for kinds that cannot be negative: mass, length, area, volume, amount, concentration, mass concentration, density, molar mass, frequency, temperature, rate constant, activity, resistance |
| Units | number columns without a unit |

Test: `…/test_clean.py::OutlierTest::test_checks`.

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
| CSV | Header "name [unit]", comma separator, full float precision (`repr`), empty for NaN. All rows, without a flag or exclusion column. |
| XLSX | Sheet "Daten": names row, units row, values. Sheet "Protokoll": title, rows, columns, SHA-256 of the data, source files with SHA-256, sheet and ranges, reading recipe, cleaning steps with row counts, conditions, columns, flags (at most 100 000). |
| JSON | `{schema, header, data}`. Lossless. On re-import the data hash is checked. |
| Parquet | Columns "name [unit]" as float64 or string. The full dataset header is in the schema metadata key `suite.dataset`. |

Round trips are compared with a relative tolerance of 10⁻¹².

**Validation**

| Test | Expected |
|---|---|
| `…/test_share.py::ExportTest::test_round_trips` | JSON and Parquet read back to the same dataset. |
| `…/test_share.py::ExportTest::test_xlsx_protocol_sheet` | "Protokoll" sheet content. |
| `tools/e2e_datasets.py` | Exports round-trip in the full chain. |

## 13. Dataset versioning and derived datasets

Code: `daten/datasets.py`, `sdk/python/labshare.py`, `sdk/python/labdataset.py`. Details of storage and integrity are
in [provenance.md](provenance.md).

* Saving publishes a new **version** only if the signature changed: data hash, title, or column key, name, unit,
  role or kind; or the dataset meta. **Flags are not part of the signature** (see Known limitations).
* Autosave runs 4 s after the last change, and only if something changed.
* A dataset made with **Convert and clean** is a *derived* dataset. It stores its parent, the parent version, the
  mode (follow or pinned) and the operations (at most 40).
* **Follow** (live): when the parent gets a new version, the child is computed again. Chains up to 6 levels are
  followed. If a step fails, the child keeps its last version and stores the error.
* **Pinned**: the child stays at its parent version until the user brings it to the new one.
* The provenance of a derived dataset records each step with rows, flags and excluded rows before and after, and the
  provenance of the parent.

**Validation**

| Test | Expected |
|---|---|
| `…/test_datasets.py::DatasetServerTest::test_publish_versions_open_and_live_child` | Saving unchanged data keeps the version; a live child follows to v2; a pinned child moves to v2 on request; a broken formula keeps the latest version 1 and records an error. |
| `…/test_datasets.py::DatasetServerTest::test_connected_table_follows_in_place` | A live connected table is replaced in place. |

---

## Known limitations

* **Dixon α**: an α other than 0.10, 0.05 or 0.01 silently uses the 0.05 table, while the rule text and the flag
  record the α entered (`clean.py`, `op_outliers`).
* **Dixon r₁₀ only**: the same ratio is used for all n from 3 to 10, and both ends are tested against one critical
  value. The code does not state whether α is one- or two-sided.
* **Iterated Grubbs** uses the same α in every round, with no correction such as the generalized ESD procedure. The
  overall false-positive rate is therefore not α.
* **Fit residual** uses a fixed threshold k, not a significance level, and does not correct for testing n points.
* **IQR** quartiles use linear interpolation, which can differ slightly from Tukey's hinges.
* **Hampel** windows count neighbours by position and ignore x spacing.
* **"Impossible values"** treats every length as non-negative, so negative displacements or positions are warned.
* **Averaging replicates clears all flags** of the averaged rows.
* **Flags are not in the version signature.** A change that only alters flags or exclusions does not create a new
  version, and a live child whose result differs only in flags is not republished.
* **CSV export** has no exclusion marker. Use XLSX, JSON or Parquet when exclusions matter.
* **Times**: time-zone suffixes are ignored; there is no daylight-saving handling.
* **`±` values** are stored as given; the type of uncertainty (standard, expanded, coverage factor) is not recorded.
* **Silent caps**: raw text is kept for at most 5 000 unreadable cells per column and flags for at most 20 000 cells
  per column when reading; ODS repeats are capped at 100 000 rows and 1 024 columns.
* **`.xls`** reading has no test of its own.
* Step texts, notes and the methods text are in German, also in an English report.
