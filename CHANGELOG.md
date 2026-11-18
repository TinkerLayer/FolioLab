# Changelog

All notable changes to Folio Lab are listed here. The suite version (this file, `package.json`, `CITATION.cff`)
follows [Semantic Versioning](https://semver.org/). Each analysis module also has its own version in
`modules/<id>/module.json`. A module's version changes whenever its results or its report output can change, so
**quote both the suite version and the module version** when you report a result.

Versions below 1.0.0 mean that the methods are tested by the project's own test suites (see `docs/VALIDATION.md`)
but have not yet been validated independently.

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
