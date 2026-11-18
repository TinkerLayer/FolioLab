# Data provenance, versions and reproducibility

This document describes how Folio Lab records where a number comes from. It covers the dataset format, versioned
shares, report bundles and their revisions, and what is protected from deletion. It ends with what to state in a
paper. Every statement is taken from the code in `sdk/python/` (`labdataset.py`, `labshare.py`, `labproject.py`,
`labprov.py`, `labindex.py`, `labbundle.py`), `server/lab.js` and `modules/datenaufbereitung/daten/`.

How each value is computed in the Datenaufbereitung module is described in
[datenaufbereitung.md](datenaufbereitung.md).

## How to cite

Name the Folio Lab version (`package.json`) and the version of each module that produced a number
(`modules/<module>/module.json`). For the Datenaufbereitung this is 0.2.0. Each report result records both
versions in its `bundle.json` (`suite_version`, `module_version`) (see [Report bundles](#4-report-bundles)), so you can read it there.

## Contents

1. [The chain at a glance](#1-the-chain-at-a-glance)
2. [Datasets](#2-datasets-suitedataset1)
3. [Shares and versions](#3-shares-and-versions)
4. [Report bundles](#4-report-bundles)
5. [Revisions, compare, restore, issued](#5-revisions-compare-restore-issued)
6. [Refresh](#6-refresh)
7. [Tracing a value back](#7-tracing-a-value-back)
8. [Retention guards](#8-retention-guards)
9. [What to state in a methods section](#9-what-to-state-in-a-methods-section)
10. [Validation](#10-validation)
11. [Known limitations](#known-limitations)

---

## 1. The chain at a glance

```
raw file (stored in the environment, named by its SHA-256)
  → dataset (suite.dataset/1: values + flags + provenance with file SHA-256, sheet, cell ranges, recipe)
    → share version s-xxxxxxxx v<n> (immutable envelope + data file, checked by the data hash)
      → [derived dataset: parent share + version + cleaning steps]
        → report result (bundle.json: module version, SHA-256 of stored source files, request naming share + version)
          → revisions (history/<n>/), issued mark, dependencies.json in the ZIP export
```

## 2. Datasets (`suite.dataset/1`)

Code: `sdk/python/labdataset.py`.

A dataset is one table of equal-length columns. It is stored as `<stem>.json` (header) and `<stem>.npz` (values,
loaded without pickles).

| Header field | Content |
|---|---|
| `schema` | `suite.dataset/1` |
| `title`, `rows` | title and row count |
| `columns` | per column: `key`, `name`, `symbol`, `kind`, `unit`, `dtype` (number or text), `role`, `u` (linked uncertainty column), `cells` (source cell range), `note` |
| `conditions` | name → value, unit, and the cell it came from |
| `flags` | per flagged cell: `row`, `col`, `code`, `excluded`, `reason`, `rule`, `raw` (original text) |
| `provenance` | see below |
| `data_hash` | SHA-256, see below |

**Provenance of a dataset read from a file**:

| Field | Content |
|---|---|
| `files` | per source file: `name`, `sha256` (of the whole file), `sheet`, `ranges` (cell ranges), `raw` (name of the stored raw file) |
| `recipe` | the reading steps (marks), replayable |
| `module_version` | version of the module that read the file |

**Provenance of a derived dataset** (made with Convert and clean): `derived_from` (parent), `ops` (the operations),
`steps` (per step: `op`, `text`, rows, flags and excluded rows before and after) and `parent_provenance` (the full
provenance of the parent).

**Data hash.** `data_hash` is a SHA-256 over the column keys, units and data types (as JSON) followed by the values
of each column: numbers as 64-bit floats, text joined with the separator U+001F. It is recomputed whenever a dataset is
built and compared with the stored value when a dataset is loaded. A changed value is therefore detected.
The hash does **not** cover column names, roles, kinds, conditions, flags, exclusions or provenance.

Missing values are stored as NaN. There is no imputation.

## 3. Shares and versions

Code: `sdk/python/labshare.py`.

A dataset is passed to other modules as a **share** of kind `data.table`.

| File | Content |
|---|---|
| `sharebox/<s-xxxxxxxx>/share.json` | producer, title, kind, recipients, latest version |
| `sharebox/<s-xxxxxxxx>/v<n>.json` | envelope of version n (`suite.shared-result/1`) |
| `sharebox/<s-xxxxxxxx>/v<n>.npz` | values of version n |

Envelope fields: `schema`, `id`, `version`, `created`, `producer` (`module`, `env`, `env_name`, `item`,
`item_name`, `module_version`, `raw`), `kind`, `title`, `outputs` (row and column count), `sources`, `dataset`
(the header) and `hash` (the data hash). The data file may be at most 200 MB.

* Each publish writes a new version n = (highest existing version) + 1. Older versions stay readable.
* Only the producing module can publish a new version of a share. A share stays a dataset share.
* Loading a version recomputes the data hash and refuses the version if it does not match the envelope.
* The Datenaufbereitung publishes a new version only when the data hash, the title, a column's key, name, unit, role
  or kind, or the dataset meta changed (see [Known limitations](#known-limitations) for flags).

### Bindings: live, pinned, copy

A consumer binds a share in one of three modes. `resolve` reports the state:

| Mode | Behaviour | Status values |
|---|---|---|
| pin | a fixed version | `current`; `update` when a newer version exists (the binding stays until the user changes it) |
| live | always the latest version | `current`; `stale` when a newer version exists than the one the result was computed with |
| copy | the envelope (and for datasets the values) is copied into the consumer | `current` or `update`; still `current` and usable when the share is deleted |

For pin and live, the status is `failed` when the share or the version is missing.

In the Datenaufbereitung, connections between environments are *live* or *snapshot*. A derived dataset either
*follows* its parent (live, chains up to 6 levels) or is *pinned* to a parent version.

### Project index

Code: `sdk/python/labindex.py`. Single curated values (`suite.index-entry/1`, ID `g-xxxxxxxx`) are append-only. An
entry cannot be changed. A different value for the same quantity is a new entry that lists the earlier ones in
`alternative_to`. Each entry records its type (measured, calculated, tabulated, estimated), an optional structured
source and its provenance (module, environment, item, share, version, module version).

## 4. Report bundles

Code: `sdk/python/labbundle.py`, `modules/datenaufbereitung/daten/bundle.py`, `server/lab.js`.

A module sends a bundle (`folio-lab-bundle/1`) to a report. The hub stores it in the report project:

| Path | Content |
|---|---|
| `lab/<slug>/bundle.json` | manifest (below) |
| `lab/<slug>/…` | figures (PDF and PNG preview), tables (`.tex`), data (`.csv`), texts, `values.tex`, `refs.bib` |
| `lab/<slug>/source/…` | the source files the module needs to rebuild the result |
| `lab/<slug>/history/<n>/` | earlier revisions |
| `lab/labdata.tex`, `lab/references.bib` | values and citations of all results, regenerated |

**Manifest fields** written by the hub on save:

| Field | Content |
|---|---|
| `format`, `module`, `module_name`, `title`, `slug`, `lang`, `summary` | identification |
| `created`, `updated` | timestamps |
| `items`, `files` | figures, tables, data, values, citations, texts |
| `source.request` | the request that produced the result; for the Datenaufbereitung: `lang`, `include`, `title`, `slug`, `share`, `version`, `embedded` |
| `source.files` | names of the stored source files |
| `result_id` | a UUID that stays the same across revisions |
| `revision` | revision number |
| `provenance.module_id` | module ID |
| `provenance.module_version` | the bundle's `module_version` if it has one, otherwise the version in the module's `module.json` at save time |
| `provenance.methods` | a methods identifier if the bundle supplies one; the Datenaufbereitung does not |
| `provenance.source_sha256` | SHA-256 of each stored source file |
| `provenance.action` | `new`, `replace`, `refresh`, `language` or `restore` (with `restored_from`) |
| `issued` | `null`, or `{at, how}` |

**What the Datenaufbereitung puts in a bundle**:

* the dataset as JSON (`datensatz.json`) as source file, if it is at most 4 MB. `source_sha256` then holds the
  SHA-256 of this dataset file, not of the raw measurement file;
* values `zeilen` (rows), `verwendet` (used), `ausgeschlossen` (excluded) and `version`;
* a data CSV with the number columns, a `used` column and up to 3 text columns, 12 significant digits;
* a figure (excluded rows as grey crosses, open outlier flags as red rings, error bars from uncertainty columns);
* tables of columns (n, min, max, mean over used rows), the first 15 rows and the flags (first 40);
* a methods text with the source files and their SHA-256 (first 16 hex digits), the module version that read the
  files, the reading recipe, the cleaning steps with row counts and citations, flag counts, excluded rows with
  reasons, and dataset title, version, ID, data SHA-256 (first 16 hex digits) and rows used;
* citations of the statistical methods used (`refs.bib`).

## 5. Revisions, compare, restore, issued

Code: `server/lab.js`. Labels in the report editor: **revisions ▾**, **history ▾**, **Compare**, **Restore**,
**Mark issued**, and the pills "Revision n of m", "issued", "draft".

| Action | What happens |
|---|---|
| Save (replace) | The current revision is moved to `history/<rev>/`. The new revision number is the highest so far + 1. `result_id` is kept. `issued` is reset to `null`. |
| Compare | Two revisions: value texts that changed, items added or removed, files whose SHA-256 differs, whether the source files changed (`source_changed`), the pair of module versions and the pair of languages. |
| Restore | Copies an old revision as a new revision (`action: restore`, `restored_from`). The current revision is archived first. Restoring the current revision is refused. |
| Mark issued | Stores `{at, how}` with `how` = `manual`, `pdf` or `zip`. Downloading the PDF and the ZIP export mark all current revisions as issued. |
| After issued | A later save or refresh creates a new revision with `issued: null`. The issued revision stays in `history/`. |
| Remove | Deletes the result and all its revisions. |

**ZIP export.** The ZIP contains all files of the report project and `lab/dependencies.json`
(`folio-lab-dependencies/1`). For every result and every kept revision it lists the revision, whether it is
current, `issued`, `result_id`, module, module version, `source_sha256` and the share versions and index entries it
used. The note in the file says that shares and index entries stay in the Folio Lab project and are not in the ZIP.

## 6. Refresh

Code: `server/lab.js` (`refresh`), `modules/datenaufbereitung/daten/server.py` (`bundle_route`),
`modules/datenaufbereitung/daten/bundle.py` (`rebuild_dataset`).

* **Refresh** sends the stored request and source files back to the module and saves the result as a new revision
  (`action: refresh`; a language change gives `action: language`).
* In the Datenaufbereitung, Refresh uses the dataset stored in the bundle. If none is stored (larger than 4 MB), it
  loads the share version named in the request from the module's active project.
* **Refresh never moves to a newer dataset version.** It rebuilds the same dataset version with the current module
  code and language. To use a newer dataset version, send the dataset to the report again.
* A test checks that a rebuild gives the same data hash.

## 7. Tracing a value back

Code: `sdk/python/labprov.py` (`chain`, `chain_for_report`, `dependencies`).

For a report result, the hub lists the shares and index entries named in its request and asks the module for the
chain of each:

| Level | Shown |
|---|---|
| index | entry, value, type, date (if the value came from the project index) |
| share | share ID and version, producer module, environment, item, module version, date |
| dataset | title, rows × columns, columns with unit and source cells, number of recipe steps |
| env | environment and item that produced the dataset |
| raw | per source file: name, sheet, cell ranges, stored SHA-256. If the raw file is still in the environment, its SHA-256 is computed again and compared. |

Raw files are stored in the environment as `raw/<first 16 hex digits of SHA-256>-<name>`.

## 8. Retention guards

Code: `sdk/python/labprov.py`, `sdk/python/labshare.py`, `sdk/python/labproject.py`.

| Guard | Rule |
|---|---|
| Share version | A share version (or a whole share) that is named in any report result, current or in `history/`, cannot be deleted. |
| Environment | An environment that produced a share version used in a report cannot be deleted. |
| Deleted environment | Deleting an environment moves it to a trash folder (`_papierkorb`). |
| Raw files | When raw files are cleaned up, files named by an item's result or by a share's `producer.raw` are kept. |
| Index entries | Cannot be changed after creation. |
| Datasets | A loaded version whose values do not match its data hash is refused. |

## 9. What to state in a methods section

To make a number reproducible, state:

1. **Software**: Folio Lab version and the version of every module used (from `module.json`, also recorded in each
   result's `bundle.json` and in `dependencies.json`).
2. **Raw data**: file names and their SHA-256 (in the dataset provenance, in the XLSX export sheet "Protokoll" and,
   shortened to 16 hex digits, in the methods text).
3. **Dataset**: dataset ID (`s-xxxxxxxx`), version, and data SHA-256 (in the methods text and the "Protokoll" sheet).
4. **Reading and cleaning**: the reading recipe and every cleaning step in order, with the parameters (method, α or
   k, degree, window, grouping). The methods text and the "Protokoll" sheet list them.
5. **Outlier decisions**: which test flagged which values, and which rows were excluded and why. State that flagged
   values were only excluded by an explicit decision, and how many rows were used.
6. **Method references**: the references of the outlier tests and smoothing used, as written to `refs.bib`.
7. **Units and conversions**: target units and formulas of derived columns.
8. **Archive**: deposit the raw files, the exported dataset (JSON or XLSX, which keep flags and exclusions) and the
   report ZIP with `dependencies.json`.

Example wording:

> Raw data (file names and SHA-256 in the supplementary material) were read and cleaned with Folio Lab 0.1.0,
> module Datenaufbereitung 0.2.0. Outliers were flagged with the Grubbs test (α = 0.05, two-sided, iterated) and
> 2 of 14 rows were excluded after inspection (reasons listed in the supplement). The analysis used dataset
> s-xxxxxxxx version 3 (data SHA-256 …).

## 10. Validation

Paths are relative to the project root.

| Part | Test | Checks |
|---|---|---|
| Dataset format and hash | `sdk/python/tests/test_labdataset.py::DatasetTest::test_round_trip` | Save and load give the same dataset; tampering is detected. |
| Dataset rules | `sdk/python/tests/test_labdataset.py::DatasetTest::test_refusals` | Invalid datasets are refused. |
| Used rows | `sdk/python/tests/test_labdataset.py::DatasetTest::test_kinds_si_and_mask` | Excluded rows are not used. |
| Share versions and bindings | `sdk/python/tests/test_labdataset.py::ShareTest::test_publish_pin_live_copy_delete` | Pinned binding reports `update`, live reports `stale`; a copy survives deleting the share; a tampered `.npz` is refused ("Prüfsumme"). |
| Chain to the cells | `sdk/python/tests/test_labdataset.py::ShareTest::test_chain_to_file_and_cells` | Chain levels share, dataset, env, raw; the raw file's SHA-256 matches. |
| Share states | `sdk/python/tests/test_labshare.py::Share::test_live_pin_copy_states` | All bindings `current` at first; after a new version: pin `update` (stays at v1), live `stale` (gets v2 with 12.6), copy `update`; an invalid version is not published; a missing share gives `failed` for live and `current` for a copy. |
| Share versions | `sdk/python/tests/test_labshare.py::Share::test_publish_versions_and_list` | Version numbering and listing. |
| Producer and recipients | `sdk/python/tests/test_labshare.py::Share::test_recipient_and_producer_checked` | Only the producer can publish; recipients checked. |
| Report → raw file | `sdk/python/tests/test_labprov.py::Provenance::test_report_value_to_raw_file` | A report value is traced to its raw file. |
| Retention guards | `sdk/python/tests/test_labprov.py::Provenance::test_used_version_and_environment_cannot_be_deleted` | A used share version and its environment cannot be deleted. |
| Export dependencies | `sdk/python/tests/test_labprov.py::Provenance::test_dependencies_for_export` | Shares, index entries and raw files listed. |
| Raw file cleanup | `sdk/python/tests/test_labproject.py::Store::test_drop_raw_keeps_files_used_by_results` | Raw files used by results are kept. |
| Environment trash | `sdk/python/tests/test_labproject.py::Store::test_delete_moves_to_trash_and_default_is_kept` | Deleting moves to the trash. |
| Index | `sdk/python/tests/test_labindex.py::Index::test_alternatives_coexist` | Alternatives coexist. |
| Dataset versions | `modules/datenaufbereitung/tests/test_datasets.py::DatasetServerTest::test_publish_versions_open_and_live_child` | Unchanged save keeps the version; live child follows; pinned child moves on request; failure keeps the last version. |
| Bundle and rebuild | `modules/datenaufbereitung/tests/test_share.py::BundleTest::test_bundle_pieces_and_pdflatex_safety` | Bundle pieces; rebuild gives the same data hash. |
| Bundle in the full chain | `modules/datenaufbereitung/tests/test_share.py::ShareServerTest::test_template_batch_export_bundle` | Batch, export and bundle through the server. |
| Revisions | `tools/test_lab_revisions.js` (script, no named tests) | First save is revision 1 with module version and 64-hex source SHA-256; two refreshes give revisions 2 and 3 with the same `result_id`; compare shows 480 → 501 MPa and a changed `values.tex` with `source_changed` false; restoring revision 1 gives revision 4; restoring the current or a missing revision is refused; after marking issued, a refresh gives revision 5 with `issued: null` and the issued revision stays in history; issue-all for ZIP; an old bundle without these fields counts as revision 1. |
| End to end | `tools/e2e_datasets.py` (script) | Excel → dataset → cleaning → Calculator, Elemental Calculator, TGA, FTIR → report; the methods text names exclusions and the dataset ID; rebuild gives the same hash; exports round-trip. |

---

## Known limitations

* **Flags and exclusions are not in the data hash** and not in the signature that decides whether a new dataset
  version is published. A change that only alters flags or exclusions may not produce a new version, and a live
  derived dataset whose result differs only in flags is not republished.
* **Derived datasets in the chain view**: the chain reads only the top-level source files of a dataset. For a
  derived dataset it shows "Keine Quelldatei angegeben" (no source file given), although the parent's provenance is
  stored in `parent_provenance`. The methods text does follow the parent.
* **Parent shares are not guarded**: a report that uses a derived dataset protects that dataset's share version, but
  not the parent share it was derived from.
* **Combined batch datasets**: their share has no `producer.raw`, so the raw-file cleanup does not keep their raw
  files on that basis.
* **Version numbers can be reused**: after the latest version of a share is deleted, the next publish gets the same
  number again.
* **Removing a report result** deletes all its revisions, including issued ones, without a guard.
* **Refresh** does not move to a newer dataset version. Without an embedded dataset (over 4 MB) it depends on the
  share still being in the module's active project.
* **Source SHA-256 in the report** is the hash of the embedded dataset file for the Datenaufbereitung, not of the raw
  measurement file. The raw files' hashes are in the dataset provenance and in the methods text (shortened).
* **Module version** in the report is taken from `module.json` at save time; the version that read the raw file is in
  the dataset provenance. The two can differ.
* **CSV export** has no flag or exclusion column; use JSON or XLSX for archiving.
* Chain texts, notes and the methods text are in German, also in an English report.
