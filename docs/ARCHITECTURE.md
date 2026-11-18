# Suite architecture: projects, environments, Shareboxes, provenance

Status: **built** (all stages in §4 are done). §2 describes the starting point before this architecture was added;
§2a says what was built and where it lives; §4 and §5 keep the build stages and design decisions as a record of why
the suite looks the way it does.

The architecture follows an internal specification for the Elementrechner and for sharing between laboratory modules
(not published), referred to below as "spec 01–03". The feature list for all modules is in `FEATURES.md`; module
conventions are in `docs/MODULES.md`.

## 1. The target in one paragraph

A **project** contains modules; each module contains **environments** (self-contained pieces of work that own their
raw data, variables, calculations and result history). Results leave an environment only through a **Sharebox**:
an explicit, versioned publication of selected, typed outputs to chosen recipients, who bind to it **live**, **pinned**
to a version, or as a **snapshot**. A separate, deliberately curated **project Global Index** holds project-wide
references. A **provenance graph** traces every number in a report back through every step and version to its source
measurement. A chemist doing a simple task never has to touch any of this.

## 2. Where Folio Lab stood before the work (starting point)

| Specification concept | Today | Gap |
|---|---|---|
| **Project** | `projects/<id>/` is one Folio report. Analysis modules are not tied to a project; they are global. | No container above modules. Needs a decision (§5, D1). |
| **Module** | Built: each module is its own local web app started by the hub (`module.json`, `/m/<id>/`). | Fits. Image Editor does not exist. |
| **Environment** | None persisted. FTIR, TGA, Mikroskopie, Zugversuch hold loaded files in the module process memory (lost on restart); settings and Rechner/Elementrechner work live in the browser's localStorage, with JSON save/load in the Rechner. The Rechner has "Umgebungen", but they are boxes inside one worksheet. | Persistent, named environments with stable IDs per module. Name clash with the Rechner's "Umgebungen" (D3). |
| **Local variables** | Rechner: variables with scope per box. Elementrechner: no variable store; values flow through the page state. Others: measured values exist as `\labval` keys and as variables for own equations. | Typed, ID-based variables per environment, visible to all tools of that module. |
| **Sharebox** | None. Only the Elementrechner → Rechner button, which copies values once through a localStorage inbox (untyped, no version, no origin). | Everything: registry, typed outputs, recipients, versions, subscriptions. |
| **Global Index** | None. Closest: own references, libraries and equations in `outputs/<module>/` – but those are the user's personal data across all projects. | New, project-scoped, append-only. Personal libraries stay separate (D4). |
| **Report binding** | Each result in a report is a bundle under `lab/<slug>/` with a copy of the raw files and the request that rebuilds it – in effect a **snapshot with its recipe**. *Refresh* rebuilds it and overwrites it (`mode=replace`); only `created`/`updated` timestamps are kept. | Report revisions (old result kept), module and method version, file hashes, explicit pin/refresh. |
| **Provenance** | Partly: every module records its processing protocol or full state in `source.request`; own references and equations are stored as full records; sources are cited everywhere. | Stable object IDs, version numbers, hashes, module/algorithm version, a queryable record of what was derived from what. |
| **Typed results** | `labcalc` has quantities with units and dimensions; bundle values carry key, label, LaTeX and text only. | A shared result envelope (`suite.shared-result/1`) built on `labcalc` quantities. |
| **Permissions** | Single user on one computer; everything is local (`127.0.0.1`). | Most of spec §10 (users, teams, revocation) does not apply now. What does apply: no implicit scope expansion (one shared output never drags others along). |

What already matches the spirit of the specification: every number has a source; measured, tabulated, calculated
and estimated values are labelled apart; raw files stay with the result that used them; processing is recorded as a
replayable protocol; nothing is sent to a report without an explicit click.

## 2a. What is built

| Concept | Where | What it does |
|---|---|---|
| **Project** | Hub `server/suite.js`, registry `projects/_suite/suite.json`; `GET/POST/PATCH /api/suite…`; selector in `public/js/suite.js` | A container of reports and module environments. One default project; each older report appears as project `r-<id>` until added elsewhere. Report folders are never moved or changed. Modules get `FOLIO_SUITE_DIR` and follow a switch on focus. `GET /api/suite/envs` lists the active environment per module for the start-page cards. |
| **Environment** | `sdk/python/labproject.py` (`Environments`, `ModuleEnvs`), page helper `sdk/web/labenv.js` | `projects/_suite/projects/<pid>/env/<module>/<eid>/`: `manifest.json` (name, summary for the board), page state, raw files by SHA-256, versioned results, trash. Active one in `_aktiv.json`, board layout and links in `_board.json`. Routes `/api/env/open|info|client|switch|create|rename|delete|board|shares|share|envvalues`. |
| **Overview / board** | `sdk/web/labboard.js`, `sdk/web/laboverview.js`; Elementrechner own board | Boxes for index, shares, environments and own shares; wires = bindings (arrows; same-column links drawn as loops); start view of every module. Environment → environment links in every module: ⇄ next to a value, "⇄ Verbindungen" menu, channels for values (`lab.envvalues`) and datasets (`env.datasets`). |
| **Datasets** | `sdk/python/labdataset.py` (`suite.dataset/1`), `labshare.publish_dataset` / `dataset_of` (kind `data.table`, `.npz` sidecar); producer module `modules/datenaufbereitung` | Typed tables with units, kinds, roles, conditions, flags (exclusion recorded with reason, never deleting rows) and provenance to file and cells; versioned; readable by every module through the shared import window (`sdk/web/labimport.js`) and read live or pinned by Rechner (graph, fits, list variables), Elementrechner (kinetics, isochron), TGA (runs), FTIR (spectra), Zugversuch (a whole test) and Mikroskopie (comparison distribution), each converting units and naming dataset ID and version. End-to-end check `tools/e2e_datasets.py`. |
| **Sharebox** | `sdk/python/labshare.py` | Envelope `suite.shared-result/1` (producer module, environment, item, module version, raw-file ID; outputs = numbers with unit and conditions; SHA-256). `projects/_suite/projects/<pid>/sharebox/<id>/v<n>.json`, immutable; recipients checked; `resolve(binding)` for pin / live / copy with current / update / stale / failed; invalid corrections refused. |
| **Slices** | TGA `/api/share/steps`, FTIR `/api/share/peaks`, Elementrechner `shared.py` (`/api/share/list|get|compare|resolve|board|envvalues`), Rechner inbox, `/api/dataset*` in Rechner, Elementrechner, TGA, FTIR | TGA steps and FTIR peaks → Elementrechner; Elementrechner values → Rechner (`chem.values`); values between Elementrechner environments (`chem.envvalues`) and between environments of every other module (`lab.envvalues`); datasets (`data.table`) from the Datenaufbereitung to four modules. |
| **Local dependencies** | `sdk/python/labdeps.py` | Order, cycles, downstream; Rechner marks circular equation cards. |
| **Global Index** | `sdk/python/labindex.py`, `sdk/web/labindex.js` | `projects/_suite/projects/<pid>/index/g-*.json`, one immutable file per entry; alternatives recorded with `alternative_to`. In every module. |
| **Report revisions** | Hub `server/lab.js` | `lab/<slug>/history/<n>/`; `result_id`, `revision`, `provenance` (module and version, file SHA-256, action), `issued`; routes revisions / compare / restore / issue / history. |
| **Provenance** | `sdk/python/labprov.py` (`/api/prov/chain|report|deps` in every module), hub `lab.history()` and `lab.dependencies()` | Chain index entry or share version → environment and item → raw file with SHA-256 check; retention (used versions and environments cannot be deleted); `lab/dependencies.json` in the ZIP export. |
| **Page parts** | `sdk/web/labui.js` | DE/EN strings and switch, folds, popovers, tasks, chips; fallback when an older module server lacks the scripts. |

Rule 8 holds: a user who never opens a share dialog sees one default project and one default environment per module,
and today's clicks (send to report, send to Rechner, Rechner chemistry functions) work as before.

## 3. Decisions taken from the specification

These hold for all further work, whatever order is chosen:

1. Raw measurement data stays in the module/environment that imported it. Other modules get selected results
   (peak table, step losses, fitted parameters, figure package), never the raw file by default.
2. Sharing is always an explicit action. Publishing to a Sharebox never adds anything to the Global Index.
3. A consumer never edits the producer's result; it makes a new, derived result that records which version it used.
4. Corrections create new versions; old published versions and old report revisions stay readable.
5. A calculation records the version it actually used, even when bound live.
6. A report binds to fixed versions; a live-linked section says so visibly; Refresh creates a new report revision.
7. Invalid or unfinished results are never published; live consumers stay on the last valid version.
8. Simple work needs no configuration: one default project and one default environment per module are created
   automatically; today's workflows keep working unchanged.
9. Inside the Elementrechner, tool families (substances, reactions, solutions, thermodynamics, kinetics, nuclear)
   are internal sections of one module; one environment may use all of them (spec 02).
10. The existing direct paths stay: Rechner functions such as `M()` or `pH()`, the "send to Rechner" button and
    *Send to report* keep working; they are re-based on typed results rather than replaced by a sharing dialog.

## 4. Stages

All stages are **done**. Each was tested before the next one started. An end-to-end check ran TGA → share →
Elementrechner (pinned) → report → compile → Refresh → revisions → history → ZIP on a separate test installation.
The stage names combine the specification's suite stages (S0–S6) and Elementrechner migration steps (M0–M6).

| Stage | Goal | Done when | Depends on |
|---|---|---|---|
| **A0 Inventory** (S0, M0) | Golden tests for today's bundles and module states; list every place state is kept. | Each module's current report output is reproduced byte-for-byte or within stated tolerances by a test. | – |
| **A1 Report revisions and provenance minimum** (S1, part of S4) | Bundles record module ID and version, method versions, SHA-256 of every source file, a result ID and revision number. Refresh keeps the previous revision under `lab/<slug>/history/<n>/` and shows "revision n of m"; the Lab dialog can compare and restore. | A refreshed result shows what changed and the old one is still there. | A0. No project decision needed. |
| **A2 Projects and persistent environments** (S0, M1) | A project container; per module a server-side environment store (raw files, protocol, state, results with versions), one default environment created automatically; an environment switcher in each module. Replaces "lost on restart" and localStorage-as-record; localStorage stays for view settings only. | Close and restart Folio Lab: every module reopens its environments as left. Old JSON saves import into a default environment. | D1, D2, D3. |
| **A3 Typed results and Sharebox MVP, pinned and snapshot** (S2, M3, M4) | `suite.shared-result/1` envelope on `labcalc` quantities; a project-level Sharebox registry in the hub; "Share …" in a producing module; "Add shared input …" in a consuming one. First vertical slice: **TGA step mass loss → Elementrechner** compares it with the theoretical loss of a balanced decomposition (spec UC02). | TGA run shares only its step table; the Elementrechner shows measured vs theoretical with the TGA result ID and version; the raw curve never leaves TGA. | A2. |
| **A4 Live updates and local dependencies** (S3, M3) | Live bindings follow the latest valid publication; dependent results become "stale" or recompute; dependency graph inside an environment (Rechner, Elementrechner); cycle detection. | Correct a TGA step: the live Elementrechner comparison updates, a pinned one stays, the report keeps its revision. | A3. |
| **A5 Existing bridges on the new base** (UC03, M4) | Elementrechner → Rechner transfer and the Rechner chemistry functions carry typed, versioned values with origin; *Send to report* publishes into the report as a pinned binding. | Same clicks as today; the Rechner shows where a value came from and its version. | A3. |
| **A6 Second slice: FTIR → Elementrechner** (spec's first slice) | FTIR publishes a peak table and group hypotheses; the Elementrechner compares them with a structure (expected bands from its functional groups). | The interpretation names the FTIR result version; FTIR correction updates only live consumers. | A3, Elementrechner feature X. |
| **A7 Global Index** (S5) | "Add to project index" on any result: a new, immutable entry with type, units, conditions, source and provenance; readable from every environment; alternatives get new entries, never overwrite. | Two alternative values for the same quantity coexist with clear IDs. | A2. |
| **A8 Provenance view and hardening** (S6) | "Open history" on any value: the chain back to the source file, on demand; retention rules (a version used by a report cannot be deleted); project export with its dependencies. | From a report value, the full path to the raw file and every step is shown. | A1–A7. |
| **A9 Elementrechner restructuring** (M2, M5) | Tool families as internal sections (T1 substances, T2 reactions, T3 solutions, T4 thermodynamics with kinetics, T6 nuclear), a variable drawer, "Use in …" between tools. | A simple equation takes no more clicks than today. | Merges with the final UI phase. |

Image Editor: named in the specification as a recipient for figure packages. It is a new module and not part of
these stages; A3's envelope already defines `FigurePackage`, so it can be added later.

**Why TGA → Elementrechner first instead of the specification's FTIR slice:** both ends exist today (TGA steps and its
stoichiometry table; Elementrechner balancing and molar masses), so the slice tests the sharing mechanism alone. The
FTIR slice also needs a new Elementrechner feature (interpreting peaks against a structure) and is better second.

## 5. Decisions (answered)

Decisions taken: **D1** = (b) a new container; **D2** = as proposed, under `projects/_suite/` so report folders
stay untouched; **D3** = Rechner boxes are "Blätter"; **D4** = personal libraries stay personal; **D5** = recompute
when cheap, otherwise stale; **D6/D7** = as proposed (snapshots copied, pinned versions locked while used, revision
fixed on PDF/ZIP export or "issued"); **D8** = chemistry work and the architecture stages interleaved, the user
interface last. The original proposals:

| # | Question | Proposal |
|---|---|---|
| D1 | What is a **project**? (a) each Folio report is a project; (b) a new container that holds several reports and the module environments. | (b): matches the specification (Folio is one module inside the project). Existing reports become projects with one report each; nothing is lost. |
| D2 | Where do environments live on disk? | `projects/<project>/env/<module>/<env-id>/` with a manifest, raw files and versions, so a project export carries everything. |
| D3 | The Rechner's existing "Umgebungen" (boxes in one worksheet) clash with suite environments. | Rename the Rechner boxes to "Blätter" (sheets); a Rechner suite environment contains several sheets. |
| D4 | Are personal libraries, own substances and own equations (today in `outputs/<module>/`) project data? | Keep them personal and cross-project, as today; a project may pin copies into its Global Index. |
| D5 | When does a live consumer recompute vs. only mark stale? | Recompute automatically when cheap and deterministic (Elementrechner, Rechner); mark stale otherwise (kinetics fits, library searches). |
| D6 | Snapshot storage | Snapshots are copies inside the consuming project (as report bundles are today); pinned versions are references with a retention lock. |
| D7 | What counts as an *issued* report revision? | A revision is fixed when the user exports the PDF or ZIP, or marks it "issued"; until then the working draft may follow live bindings, visibly labelled. |
| D8 | Order relative to the chemistry phases | Open: A1 can start now without D1–D3; A2 onwards needs D1–D3. |

## 6. What stays true for every module meanwhile

New module work (Elementrechner lab workflows, phases 6 and 7, the TGA reader) follows the rules of §3 already, so
nothing has to be redone later: results as `labcalc` quantities with units and basis, sources as `labcite` records,
processing as a replayable protocol, no hidden assumptions, nothing shared without a click.
