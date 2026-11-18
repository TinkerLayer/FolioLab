# Data provenance, versions and reproducibility

This document describes how Folio Lab records where a number comes from. It covers the dataset format, versioned
shares, report bundles and their revisions, and what is protected from deletion. It ends with what to state in a
paper. Every statement is taken from the code in `sdk/python/` (`labdataset.py`, `labshare.py`, `labproject.py`,
`labprov.py`, `labindex.py`, `labbundle.py`), `server/lab.js` and `modules/datenaufbereitung/daten/`.

How each value is computed in the Datenaufbereitung module is described in
[datenaufbereitung.md](datenaufbereitung.md).

## How to cite

Name the Folio Lab version (`package.json`) and the version of each module that produced a number
(`modules/<module>/module.json`). For the Datenaufbereitung this is 0.3.0. Each report result records both
versions in its `bundle.json` (`suite_version`, `module_version`, and where the module version came from:
`module_version_from`) (see [Report bundles](#4-report-bundles)), so you can read it there.

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
      → [derived dataset: parent share + version + cleaning steps (+ joined datasets) → … → parent's raw file]
        → report result (bundle.json: module version, SHA-256 of stored source files, request naming share + version)
          → revisions (history/<n>/), issued mark, dependencies.json in the ZIP export
            → removed but issued results kept under lab/_removed/
```

## 2. Datasets (`suite.dataset/1`)

Code: `sdk/python/labdataset.py`.

A dataset is one table of equal-length columns. It is stored as `<stem>.json` (header) and `<stem>.npz` (values,
loaded without pickles).

| Header field | Content |
|---|---|
| `schema` | `suite.dataset/1` |
| `title`, `rows` | title and row count |
| `columns` | per column: `key`, `name`, `symbol`, `kind`, `unit`, `dtype` (number or text), `role`, `u` (linked uncertainty column), `cells` (source cell range), `note`; for uncertainty columns `u_type` (empty = not stated, `u`, `U`, `sd`, `se`, `ci`), `u_k` (coverage factor, only with `U`), `u_level` (%, only with `ci`) |
| `conditions` | name → value, unit, and the cell it came from |
| `flags` | per flagged cell: `row`, `col`, `code`, `excluded`, `reason`, `rule`, `raw` (original text), `alpha` |
| `provenance` | see below |
| `data_hash` | SHA-256 of the values, see below |
| `flags_hash` | SHA-256 of the flags and exclusions, see below |

**Provenance of a dataset read from a file**:

| Field | Content |
|---|---|
| `files` | per source file: `name`, `sha256` (of the whole file), `sheet`, `ranges` (cell ranges), `raw` (name of the stored raw file) |
| `recipe` | the reading steps (marks), replayable |
| `module_version` | version of the module process that read the file |
| `truncations` | every cut made while reading: `what`, `kept`, `total`, `from_row` (only when something was cut) |
| `warnings` | possible daylight-saving jumps in local date/time columns (only when found) |

**Provenance of a derived dataset** (made with Convert and clean): `derived_from` (parent share, version, title),
`ops` (the operations), `steps` (per step: `op`, `text`, rows, flags and excluded rows before and after),
`inputs` (datasets joined in, with share, version and title), `module_version` (the process that computed this
version; a live child computed again after a parent change records the recomputing process) and
`parent_provenance` (the full provenance of the parent).

**Data hash.** `data_hash` is a SHA-256 over the column keys, units and data types (as JSON) followed by the values
of each column: numbers as 64-bit floats, text joined with the separator U+001F. It is recomputed whenever a dataset is
built and compared with the stored value when a dataset is loaded. A changed value is therefore detected.
The hash does **not** cover column names, roles, kinds, conditions, flags, exclusions or provenance.

**Flags hash.** `flags_hash` is a SHA-256 over the flags in their stored order, each as
[row, col, code, excluded, reason, rule, raw, alpha] (compact JSON). It is recomputed when a dataset is built and
checked on loading when the stored header has one (headers written before 0.3.0 have none and load as before). A
changed flag or exclusion is therefore detected, separately from the values.

Missing values are stored as NaN. There is no imputation.

## 3. Shares and versions

Code: `sdk/python/labshare.py`.

A dataset is passed to other modules as a **share** of kind `data.table`.

| File | Content |
|---|---|
| `sharebox/<s-xxxxxxxx>/share.json` | producer, title, kind, recipients, latest version, `issued` (highest number ever given), `deleted` (tombstones) |
| `sharebox/<s-xxxxxxxx>/v<n>.json` | envelope of version n (`suite.shared-result/1`) |
| `sharebox/<s-xxxxxxxx>/v<n>.npz` | values of version n |

Envelope fields: `schema`, `id`, `version`, `created`, `producer` (`module`, `env`, `env_name`, `item`,
`item_name`, `module_version`, `raw`), `kind`, `title`, `outputs` (row and column count), `sources`, `dataset`
(the header) and `hash` (the data hash). The data file may be at most 200 MB.

* Each publish writes a new version n = 1 + the largest of: existing version files, `issued`, and the versions of
  all tombstones. **A version number is never given twice**, also after the latest version was deleted. Older
  versions stay readable.
* Deleting a version (only when no report uses it, see [Retention guards](#8-retention-guards)) removes its files and
  leaves a tombstone in `share.json`: `{version, deleted, hash, created}`. Reading it later gives "Version n wurde am
  … gelöscht". Deleting the last remaining version, or the whole share, removes the share folder; a new share always
  gets a new ID.
* Only the producing module can publish a new version of a share. A share stays a dataset share.
* Loading a version recomputes the data hash (and the flags hash, when the envelope has one) and refuses the version
  if it does not match.
* The Datenaufbereitung publishes a new version only when its signature changed: data hash, flags hash, title, a
  column's key, name, unit, role, kind, symbol, uncertainty link, note or uncertainty type, the conditions, the parent
  version or joined versions of a derived dataset, or the dataset meta.

### Bindings: live, pinned, copy

A consumer binds a share in one of three modes. `resolve` reports the state:

| Mode | Behaviour | Status values |
|---|---|---|
| pin | a fixed version | `current`; `update` when a newer version exists (the binding stays until the user changes it) |
| live | always the latest version | `current`; `stale` when a newer version exists than the one the result was computed with |
| copy | the envelope (and for datasets the values) is copied into the consumer | `current` or `update`; still `current` and usable when the share is deleted |

For pin and live, the status is `failed` when the share or the version is missing.

In the Datenaufbereitung, connections between environments are *live* or *snapshot*. A derived dataset either
*follows* its parent (live, chains up to 6 levels) or is *pinned* to a parent version. A live child is computed
again whenever the parent's signature changes, including a change of flags or exclusions only.

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
| `lab/_removed/<slug>-<time>/` | a removed result that had an issued revision, with all its revisions |
| `lab/labdata.tex`, `lab/references.bib` | values and citations of all results, regenerated |

**Manifest fields** written by the hub on save:

| Field | Content |
|---|---|
| `format`, `module`, `module_name`, `title`, `slug`, `lang`, `summary` | identification |
| `created`, `updated` | timestamps |
| `items`, `files` | figures, tables, data, values, citations, texts |
| `source.request` | the request that produced the result; for the Datenaufbereitung: `lang`, `include`, `title`, `slug`, `share`, `version`, `mode` (`pin` or `live`), `embedded` |
| `source.files` | names of the stored source files |
| `source.kind` | what the source files are, if the bundle says so (`dataset` for the Datenaufbereitung) |
| `result_id` | a UUID that stays the same across revisions |
| `revision` | revision number |
| `provenance.module_id` | module ID |
| `provenance.module_version` | the bundle's `module_version` (the version of the module process that computed it) if it has one, otherwise the version in the module's `module.json` at save time |
| `provenance.module_version_from` | `bundle` or `module.json` (or `null` when neither is known) |
| `provenance.methods` | a methods identifier if the bundle supplies one; the Datenaufbereitung does not |
| `provenance.source_sha256` | SHA-256 of each file stored under `lab/<slug>/source/`, i.e. exactly what the module gets back on Refresh. For measurement modules these are the raw files; for the Datenaufbereitung it is the dataset version (`datensatz.json`), not the raw file behind it |
| `provenance.source_kind` | `source.kind` of the bundle, else `files` when source files exist, else `null` |
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
  reasons, the type of each stated uncertainty, any truncation ("GEKÜRZT") and daylight-saving warning, a Refresh
  note when the version moved, and dataset title, version, ID, data SHA-256 (first 16 hex digits) and rows used;
* citations of the statistical methods used (`refs.bib`);
* `module_version` (this module process) and `source.kind = "dataset"`.

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
| Remove | A result that was never issued is deleted with all its revisions. A result with an issued revision (current or in `history/`) is **moved** to `lab/_removed/<slug>-<time>/` with all its revisions; its manifest gets `removed: {at, reason}`. It no longer appears in the report, `labdata.tex` or `references.bib`, but it is listed in `dependencies.json` (`removed: true`) and its share versions stay protected. |

**ZIP export.** The ZIP contains all files of the report project and `lab/dependencies.json`
(`folio-lab-dependencies/1`). For every result and every kept revision it lists the revision, whether it is
current, `issued`, `result_id`, module, module version, `source_sha256` and the share versions and index entries it
used (also through bindings `{id, mode, used/version}`), including removed but kept results. The note in the file
says that shares and index entries stay in the Folio Lab project and are not in the ZIP.

## 6. Refresh

Code: `server/lab.js` (`refresh`), `modules/datenaufbereitung/daten/server.py` (`bundle_route`),
`modules/datenaufbereitung/daten/bundle.py` (`rebuild_dataset`).

* **Refresh** sends the stored request and source files back to the module and saves the result as a new revision
  (`action: refresh`; a language change gives `action: language`).
* In the Datenaufbereitung, the request stores a **mode** chosen when the dataset is sent to the report:
  * `pin` ("this version", default; also every bundle made before 0.3.0): Refresh rebuilds the **same** dataset
    version with the current module code and language — from the dataset stored in the bundle, or, if none is
    stored (larger than 4 MB), from that share version in the module's active project.
  * `live` ("newest version"): Refresh loads the **newest** version of the share from the active project. When it
    is newer, the summary and the methods text say "Aktualisiert: Datensatz … von Version a auf die neueste Version
    b", and the request records the new version. When the newest version cannot be read, the kept version is used
    and the note says so.
* A test checks that a pinned rebuild gives the same version and data hash, and that a live rebuild moves to the
  newest version with the note.

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
| derived | for a derived dataset: "Abgeleitet aus „title“ (s-… vN)" and its step texts |
| input | for each dataset joined in: its share and version |
| raw | per source file: name, sheet, cell ranges, stored SHA-256. If the raw file is still in the environment, its SHA-256 is computed again and compared. |

For a derived dataset the chain continues with the parent's share version and its full chain (recursively, at most
8 levels) down to the parent's raw file. If the parent version cannot be read any more, the chain shows that and
then the source files from the stored `parent_provenance`, marked "gespeicherter SHA-256, Rohdatei nicht geprüft".

Raw files are stored in the environment as `raw/<first 16 hex digits of SHA-256>-<name>`.

## 8. Retention guards

Code: `sdk/python/labprov.py`, `sdk/python/labshare.py`, `sdk/python/labproject.py`.

| Guard | Rule |
|---|---|
| Share version | A share version (or a whole share) that is used by any report result — current, in `history/`, or removed but kept under `lab/_removed/` — cannot be deleted. "Used" means named in the request as an envelope, as `{share, version}`, or as a binding `{id, mode, used/version}` (the version used). |
| Parent versions | The versions a used dataset was derived from (`derived_from`), joined with (`inputs`, pinned joins) are protected too, transitively; the message says "… über s-… vN". |
| Version numbers | Never reused; deleted versions leave a tombstone (see [Shares and versions](#3-shares-and-versions)). |
| Report results | A result with an issued revision is not deleted when removed but moved to `lab/_removed/` (see [Revisions](#5-revisions-compare-restore-issued)). |
| Environment | An environment that produced a share version used in a report cannot be deleted. |
| Deleted environment | Deleting an environment moves it to a trash folder (`_papierkorb`). |
| Raw files | When raw files are cleaned up, files named by an item's result, by a share's `producer.raw`, or in a dataset's `provenance.files[].raw` (combined batch datasets) are kept. |
| Index entries | Cannot be changed after creation. |
| Datasets | A loaded version whose values do not match its data hash (or whose flags do not match its flags hash) is refused. |

**Retention rule in short**: whatever a report result has used — directly, through a binding, or as the parent of a
dataset it used — and whatever an issued revision rests on, stays in the project until the report no longer refers
to it. A removed result with an issued revision keeps referring to it (from `lab/_removed/`); delete that folder by
hand only if the issued document no longer needs to be reproducible.

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
8. **Uncertainties**: the type of each stated uncertainty (u, U with k, s, SE, confidence interval with level), as
   recorded in the column properties; "nicht angegeben" means it was not stated.
9. **Archive**: deposit the raw files, the exported dataset (JSON or XLSX; CSV keeps the used/excluded state and the
   flag texts in two extra columns) and the report ZIP with `dependencies.json`.

Example wording:

> Raw data (file names and SHA-256 in the supplementary material) were read and cleaned with Folio Lab 0.2.0,
> module Datenaufbereitung 0.3.0. Outliers were flagged with the Grubbs test (two-sided, applied sequentially with
> α = 0.05 per step, so the overall error rate is not 0.05) and
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
| Flags hash | `sdk/python/tests/test_labdataset.py::DatasetTest::test_flags_hash` | Same values with a changed exclusion: equal `data_hash`, different `flags_hash`; an edited exclusion in a saved file is refused on loading. |
| Uncertainty type | `sdk/python/tests/test_labdataset.py::DatasetTest::test_uncertainty_type` | Default "nicht angegeben", U with k, refusals. |
| Version numbers | `sdk/python/tests/test_labdataset.py::ShareTest::test_version_numbers_never_reused` | v2 deleted → tombstone with hash, `issued` 2, reading v2 says "gelöscht"; the next publish is v3. |
| Chain of a derived dataset | `sdk/python/tests/test_labdataset.py::ShareTest::test_chain_of_derived_dataset_reaches_raw_file` | Levels share, dataset, env, derived, share, dataset, env, raw; the parent's raw SHA-256 matches; with the parent version gone, the stored parent provenance is shown "nicht geprüft". |
| Parent guard | `sdk/python/tests/test_labdataset.py::ShareTest::test_parent_of_used_derived_dataset_is_kept` | A report using the child protects the parent version ("über s-… v1"); deleting it, or the whole parent share, is refused. |
| Bindings and removed results | `sdk/python/tests/test_labdataset.py::ShareTest::test_removed_results_and_bindings_count_as_use` | A live binding protects its `used` version; a removed but issued result under `_removed/` protects its version ("entfernt, aufbewahrt"). |
| Raw files of combined datasets | `sdk/python/tests/test_labdataset.py::ShareTest::test_raw_files_named_in_dataset_provenance_are_kept` | A raw file named only in `provenance.files[].raw` survives `drop_raw`. |
| Flag-only change | `modules/datenaufbereitung/tests/test_datasets.py::DatasetServerTest::test_flag_only_change_is_a_new_version_and_live_child_follows` | New version on an exclusion alone; the live child follows and records the recomputing module version. |
| Refresh pin/live | `modules/datenaufbereitung/tests/test_share.py::ShareServerTest::test_template_batch_export_bundle` | Pinned refresh keeps the version; live refresh moves to the newest with the note. |
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
| Revisions | `tools/test_lab_revisions.js` (script, no named tests) | First save is revision 1 with module version and 64-hex source SHA-256; two refreshes give revisions 2 and 3 with the same `result_id`; compare shows 480 → 501 MPa and a changed `values.tex` with `source_changed` false; restoring revision 1 gives revision 4; restoring the current or a missing revision is refused; after marking issued, a refresh gives revision 5 with `issued: null` and the issued revision stays in history; issue-all for ZIP; an old bundle without these fields counts as revision 1; a bundle's own `module_version` wins (`module_version_from: bundle`, `source_kind: dataset`), otherwise `module.json` and `files`; removing a never-issued result deletes it, removing an issued one moves it to `_removed/` where `dependencies.json` still lists it with its share versions (binding: the version used). |
| End to end | `tools/e2e_datasets.py` (script) | Excel → dataset → cleaning → Calculator, Elemental Calculator, TGA, FTIR → report; the methods text names exclusions and the dataset ID; rebuild gives the same hash; exports round-trip. |

---

## Known limitations

* **Datasets saved before 0.3.0** have no `flags_hash`; their flags are not checked on loading. Their signature
  is computed from the flags themselves, so the first save after the update does not create a spurious version.
* **Deleting a whole share** (or its last version) removes the folder, including the tombstones; this is only
  possible when no report uses any of its versions.
* **Removed results** under `lab/_removed/` are kept indefinitely; there is no user interface to list or purge them
  (they appear in `dependencies.json`). Removing such a folder by hand lifts the protection of the versions it used.
* **Refresh without an embedded dataset** (over 4 MB) and every *live* Refresh depend on the share being in the
  module's active project.
* **Source SHA-256 in the report** is the hash of the embedded dataset file for the Datenaufbereitung
  (`source_kind: dataset`), not of the raw measurement file. The raw files' hashes are in the dataset provenance and
  in the methods text (shortened).
* **Module version** in the report is the version of the module process that built the bundle when the bundle says
  so (`module_version_from: bundle`); for modules that do not send it, it is `module.json` at save time, which can be
  newer than a still-running old process. The version that read the raw file is in the dataset provenance.
* **Chain depth**: the chain of derived datasets stops after 8 levels (the Datenaufbereitung allows 6).
* Chain texts, notes and the methods text are in German, also in an English report.
