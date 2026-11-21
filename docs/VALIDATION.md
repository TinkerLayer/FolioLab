# Validation

This page says how Folio Lab's results are checked, what the checks cover and what they do not. If you use Folio Lab
in a publication, read it together with the methods page of each module you used ([docs/methods/](methods/README.md)).

## Status

Folio Lab is research software at version 0.x. Its computations are covered by automated tests (below), but they
have **not been validated independently**, by an inter-laboratory comparison or by a certified reference material.
Treat a result like the output of any new evaluation procedure:

- check it against a known case in your own laboratory;
- report the Folio Lab and module versions (recorded in every result, see [Citing](#citing-a-result));
- state the settings that differ from the defaults.

Every methods page ends with a list of **known limitations**. These are part of the validation statement.

## Running the tests

The tests need only the packages in `requirements.txt`; `scipy` is used by some tests for independent reference
values (`pip install scipy`).

```bash
cd sdk/python
python -m unittest discover -s tests
```

For one module (Windows PowerShell; on Linux/macOS use `:` instead of `;` in PYTHONPATH):

```bash
cd modules/tga
$env:PYTHONPATH = "..\..\sdk\python;."
python -m unittest discover -s tests
```

These end-to-end checks run outside the unit tests:

```bash
python tools/e2e_datasets.py
node tools/test_lab_revisions.js
node tools/test_report_import.js
node tools/test_folio_import.js
node tools/test_lab_forks.js
node tools/test_report_parts.js
node tools/test_lab_uses.js
node tools/test_cus_edit.js
```

- `tools/e2e_datasets.py`: an Excel file goes through the data preparation, is shared as a dataset, used by Rechner,
  Elementrechner, TGA and FTIR, and ends in a report bundle. Every step is checked.
- `tools/test_lab_revisions.js`: report revisions and provenance (`server/lab.js`).
- `tools/test_report_import.js` (9 checks): the piece extractor; importing figures, equations, sections, values,
  whole results, shared values, a shared data table and index values with their files, references and macros; live,
  pinned and copied links (stale after a source change, Update); a clashing cite key; the portable ZIP and its
  re-import. The last check compiles with LaTeX (pdfLaTeX, Biber, BibTeX): the report with imports, the portable ZIP
  alone, inside a foreign natbib/BibTeX document and inside a biblatex document with cleveref. It is skipped when no
  LaTeX is found.
- `tools/test_folio_import.js` (7 checks): *Import from Folio* on the hub side: the whole bundle is kept and the
  pieces not chosen are marked hidden; Short, Full and own choices of the methods sentences give the expected running
  text (same composition as `labbundle.compose_methods`); the "source changed" hash follows the environment's files
  and report request but not its view state.
- `tools/test_report_parts.js` (7 checks): report pieces cite and describe only what they show, on the hub side with a
  stand-in module: a plain curve has no reference source and one methods sentence; Full drops steps of pieces not
  shown; a hidden envelope loses its sentence and citation and gets them back when the variant is removed; a hidden
  reference keeps its source only while another kept piece cites it; Refresh keeps edited sentences. The captions and
  citations of the real modules are checked in their own suites and in `sdk/python/tests/test_parts.py`.
- `tools/test_lab_forks.js` (8 checks): table variants (hidden columns, decimals with point or comma, units kept,
  refusal for spanning cells or rules); a table, text and caption variant is its own result with its own label and
  leaves the original unchanged; editing a variant again updates it in place; a figure without a stored source cannot
  be restyled; changing the methods selection afterwards. That a style in the request redraws the named figure is
  checked in `sdk/python/tests/test_labstyle.py` and, through a real module, in Werkstoffe's tests. Preview, saving a
  styled figure and a table variant from the Lab dialog and the editor's context menu, a live variant following a
  Refresh of its original, and compiling the report were checked on a scratch hub during development. The SDK side (`bundle_of` for a
  stored, not active environment) is in `sdk/python/tests/test_labproject.py`. Importing a figure and values from a
  Zugversuch environment, compiling, link state, Refresh and Update were checked end to end on a scratch hub during
  development (not part of the automated tests). The Werkstoffe compendium and info board (chart selection, pins,
  frames, undo, reload, report export in German and English, leaving out a flagged pin, Refresh) and the transfer of
  project index values into each module were also clicked through on a scratch hub.
- `tools/test_lab_uses.js` (10 checks): the text helpers for results in `.tex` files, such as the placement of figure
  floats.
- `tools/test_cus_edit.js` (8 checks): the helpers of the figure editing window: style groups, what an element looks
  like with its group, range selection, find and replace across labels.

All of them use temporary folders or no files at all and never touch your projects.

GitHub Actions runs all suites on Windows with Python 3.10 and 3.12 on every push
([.github/workflows/tests.yml](../.github/workflows/tests.yml)). Once a week, and on demand, a second job downloads
the [optional reference data](../THIRD_PARTY_NOTICES.md#optional-data-not-in-the-repository) and runs the
Elementrechner and FTIR suites with it.

## What the tests cover

| Suite | Tests | Skipped in the public repository | Methods page |
|---|---|---|---|
| SDK (`sdk/python/tests`) | 270 | 2: the ionisation-energy unit test needs the optional NIST ASD data; the check of the page script needs the local Node in `tools/node` | [provenance](methods/provenance.md), [rechner](methods/rechner.md), [uncertainty](methods/uncertainty.md) |
| Datenaufbereitung (data preparation) | 93 | 1: writing `.xls` needs a writer that is not installed; reading `.xls` is tested via xlrd. Without pyarrow the Parquet tests are skipped too | [datenaufbereitung](methods/datenaufbereitung.md) |
| Elementrechner | 281 | 35: need optional data (stability constants 21, Burcat 13, NIST ASD 7, IUPAC pKa 3; three tests need all four parts and are counted under each) | [elementrechner](methods/elementrechner.md) |
| FTIR | 89 | 3: need the optional Open Specy spectra | [ftir](methods/ftir.md) |
| Mikroskopie (microscopy) | 75 | 0 | [mikroskopie](methods/mikroskopie.md) |
| Rechner (calculator) | 210 | 1: the check of the page script needs the local Node in `tools/node` | [rechner](methods/rechner.md) |
| TGA | 102 | 1 or 2: one checks the hint shown when `pyngb` is missing (skipped when it is installed), one reads a table with the real `pyngb` (skipped when it is missing) | [tga](methods/tga.md) |
| Werkstoffe (materials) | 242 | 2: the info board page checks need the local Node in `tools/node` | [werkstoffe](methods/werkstoffe.md) |
| Zugversuch (tensile test) | 109 | 0 | [zugversuch](methods/zugversuch.md) |
| **Total** | **1471** | **45** | |

Counts: version 0.5.0 (21.11.2026), Windows 11, Python 3.12, public repository with pyngb installed and without a local
Node. With the optional data installed
(`python tools/fetch_optional_data.py all`), all Elementrechner and FTIR tests run.

A skipped test always names its reason and, for optional data, the command that adds it.

### Kinds of test

1. **Known-answer tests.** Synthetic input with an analytically known result. Examples:
   - a tensile curve with E = 70 GPa and a known Rm;
   - TGA runs of calcium oxalate monohydrate with the theoretical losses of 12.33 / 19.17 / 30.12 %;
   - multi-rate TGA data generated with a set activation energy;
   - images with discs and rectangles of known area;
   - fits of noise-free functions with known parameters;
   - balanced equations with a unique solution.

   These are the strongest checks of an algorithm. Since 0.2.0 each module also has a file of known-answer tests
   for its corrected methods (`tests/test_science.py` or `tests/test_known_answers.py`), for example:
   - TGA: Friedman, Ozawa–Flynn–Wall (ASTM E1641 iteration), KAS, Starink and Vyazovkin recover Eₐ = 150 kJ/mol within
     0.5 % on data generated independently with scipy; Student t quantiles against `scipy.stats.t.ppf`;
   - Mikroskopie: TIFF resolution units, non-square pixels, the Miles–Lantuéjoul edge correction exact on average over
     all translations of a periodic field, perimeter against the contourpy level-½ contour;
   - Rechner: integrals, derivatives and fits against analytic values and scipy (`integrate.quad`,
     `optimize.curve_fit`, `special.sici`);
   - FTIR: band areas and widths of T/R spectra against the analytic Gaussian, ALS against a sparse solver, NNLS
     against `scipy.optimize.nnls`;
   - Zugversuch: At/A and Agt/Ag on a synthetic curve with E = 70 GPa, work to fracture against the closed form,
     the Ramberg–Osgood reference curve; load peaks on synthetic sawtooth curves (exact line and exponential envelopes,
     peak counts at 2 / 5 / 10 % thresholds, drop, ratio, reload stiffness and segment work against closed forms, the fit
     window from the first loading; the elastic/plastic division off for curves with 2 load peaks, and no yield
     onset after the maximum or the first load peak);
   - Datenaufbereitung: Dixon r10 critical values against the null distribution (within 0.003, except n = 4,
     α = 0.01: table 0.926, computed 0.921, flagged), UTC and DST handling;
   - Werkstoffe: Cu, Si, NaCl, corundum and rutile line positions and extinctions, Williamson–Hall recovering a set
     size and strain, the ASTM E1049 rainflow example, the E399 SE(B) factors, E112 grain sizes, Tafel and Norton
     parameters recovered from generated data, the ideal Cu–Ni solution against its closed form; in the lattice
     model the Arrhenius vacancy fraction, the classical high-temperature limit of the Debye ⟨u²⟩, the lever-rule
     cementite fraction, carbon on octahedral sites of austenite, and the in-plane coordination of (111), (100), (110)
     and (0001) layers; in the structure tool a structure record for every material of the database, all of them built
     at 20 °C with known references, bond lengths and non-bonded contacts of all 28 polymer chains, the fibre periods
     of PE (Bunn 1939), PP, PTFE and POM helices, views that change across Ac3, the Al solvus and Tm, and the steel
     and Al heat-treatment paths (martensite after quenching, 3rd tempering stage at 400 °C, supersaturated solid
     solution and peak ageing for T6). The phase diagrams: every system closes its regions, and the lever rule
     inside every two-phase region gives fractions that sum to 1. The heat treatment places martensite in-between
     frames only below Ms, in rising order, and austenite only above Ac1. The microstructure library: every sketch
     stays inside its view and its size budget, transformed fractions never fall as progress rises, the Bain c/a runs
     from √2 to the Roberts value, and every source resolves.
   - Measurement uncertainty (SDK, `test_uncertainty.py`): the worked examples of JCGM 101 (GUM Supplement 1). §9.2,
     the additive model with four normal inputs, gives u = 2 and the interval ±3.92; with rectangular inputs Monte Carlo
     gives ±3.88 against the GUM ±3.92. §9.3, the mass calibration, gives the GUM u = 0.0539 mg and the Monte Carlo
     u ≈ 0.075 mg with the interval [1.087; 1.383] mg. Also checked: Welch–Satterthwaite degrees of freedom and
     k from Student t, correlated inputs (a − b with r = 1 gives u = 0; a + b with r = 0.5 gives √3, by GUM and by Monte
     Carlo), the worst case at the corners of the limits,
     the warning for a strongly non-linear model, rounding per GUM 7.2.6, and correlation kept through chains of own
     equations. Werkstoffe checks the K_Q budget, type A from repeated hardness indents and the comparison of all four
     methods.
2. **Independent reference values.** Results compared with numbers that do not come from Folio Lab's own code, such
   as values computed with scipy, tabulated values from NIST-JANAF, NIST ASD or textbooks, and worked examples from
   standards or papers. The expected value and its source are written next to each assertion.
3. **Golden (regression) tests.** A complete report bundle (figures, tables, values, methods text, citations) for a
   fixed input is compared with a stored reference in `tests/golden/`. They detect *unintended changes*. They do not
   prove that the stored result is right, which is what kinds 1 and 2 are for. To regenerate after an intended change,
   run with `FOLIO_GOLDEN_UPDATE=1` and explain the change in the commit. Time stamps, local paths, ids and the
   module version in the Folio Lab software sentence and its citation are masked, so a release alone does not change
   a golden file; every other version number (for example of a cited database) is compared. The tensile module's
   golden test runs on the synthetic curve, because real measurements are not published.
4. **Format tests.** Readers and writers, tested on synthetic files in each documented format. Where no real file
   from an instrument was available, the methods page says so.
5. **Server and workflow tests.** The local HTTP interface of each module, the report bundle, *Refresh* and
   revisions.

Each methods page lists, per computed quantity, the tests that check it and their expected values.

## What the tests do not cover

- **Real instrument files.** Most readers are tested on files written to the documented format, not on exports from
  every instrument and software version. Check the first import of your own files against the instrument software.
- **Literature values that were transcribed by hand** and are not yet checked against the original:
  - ionic radii (Shannon 1976, `labcalc/radii.py`);
  - acid–base indicators (Harris 2016, `labcalc/data/indicators.json`);
  - mean bond enthalpies and cryoscopic constants (Atkins, `labcalc/bonds.py`, `labcalc/vapor.py`);
  - Antoine coefficients (`labcalc/vapor.py`);
  - Joback group values (checked only on the worked acetone example, `labcalc/joback.py`);
  - the property values added to the shared materials database in 0.3.x (`labcalc/data/materials.json`, marked
    `nicht_geprueft` per entry; shown as ⚠ in the Rechner picker). The Rechner tests check units, lookups and
    citations, and a few values against textbook worked examples (Cu density from its lattice parameter, Bragg angle
    of α-Fe), not every tabulated number;
  - the Cromer–Mann form-factor coefficients (`modules/werkstoffe/werk/formfactors.py`, transcribed without the
    original at hand; checked by f(0) = Z and computed line orders) and the phase-diagram key points
    (`werk/data/diagrams.json`).

  The data file or code records this. For ionic radii, Antoine coefficients and colligative constants, the result in
  the Elementrechner also shows it. See [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).
- **Citations and tables not yet verified against the original publication or standard.** For example: the Dixon
  critical values (checked numerically against the null distribution, not against Rorabacher 1991), the procedures of
  ASTM E1641, E1877 and D7582 in the TGA module, the hardness–tensile-strength factor in the Rechner, edition years of
  several standards, and some material sources in the tensile module. Each methods page names these and the program
  marks them.
- **The Werkstoffe compendium as a reference.** Of its 254 sources, 98 are marked as not checked against the original,
  1 is partly checked and 155 have no check on record. Of its 2021 statements, 1090 rest only on unchecked sources and
  318 have no traceable source yet and are marked as open. The tests check that each statement carries its citation
  and status, not that the cited work says what the statement says.
- **Behaviour on other operating systems.** Linux and macOS are expected to work but are not tested.

## Citing a result

Every result sent to a report stores a `bundle.json` in the project with a `provenance` block:

- the Folio Lab version (`suite_version`);
- the module and its version (`module_id`, `module_version`);
- the SHA-256 of each measurement file kept with the result (`source_sha256`);
- the methods used.

The full request is stored as well, so *Refresh* can recompute the result and keep the previous revision. A report
exported as ZIP contains `dependencies.json` with the same information for every result. To cite the software itself,
use [CITATION.cff](../CITATION.cff) and give the version.

## Reporting a wrong result

Please open an issue with:

- the input (or a synthetic file that shows the problem);
- the settings;
- the value Folio Lab gave;
- the value you expected and where it comes from.

See [CONTRIBUTING.md](../CONTRIBUTING.md).
