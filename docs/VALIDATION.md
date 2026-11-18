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

Two end-to-end checks run outside the unit tests:

```bash
python tools/e2e_datasets.py
node tools/test_lab_revisions.js
```

- `tools/e2e_datasets.py`: an Excel file goes through the data preparation, is shared as a dataset, used by Rechner,
  Elementrechner, TGA and FTIR, and ends in a report bundle. Every step is checked.
- `tools/test_lab_revisions.js`: report revisions and provenance (`server/lab.js`).

Both use temporary folders and never touch your projects.

GitHub Actions runs all suites on Windows with Python 3.10 and 3.12 on every push
([.github/workflows/tests.yml](../.github/workflows/tests.yml)). Once a week, and on demand, a second job downloads
the [optional reference data](../THIRD_PARTY_NOTICES.md#optional-data-not-in-the-repository) and runs the
Elementrechner and FTIR suites with it.

## What the tests cover

| Suite | Tests | Skipped in the public repository | Methods page |
|---|---|---|---|
| SDK (`sdk/python/tests`) | 79 | 0 | [provenance](methods/provenance.md) |
| Datenaufbereitung (data preparation) | 61 | 1: writing `.xls` needs a writer that is not installed; reading `.xls` is tested via xlrd | [datenaufbereitung](methods/datenaufbereitung.md) |
| Elementrechner | 261 | 34: need optional data (stability constants 20, Burcat 12, NIST ASD 6, IUPAC pKa 2; the golden report test needs four parts and is counted under each) | [elementrechner](methods/elementrechner.md) |
| FTIR | 48 | 3: need the optional Open Specy spectra | [ftir](methods/ftir.md) |
| Mikroskopie (microscopy) | 33 | 0 | [mikroskopie](methods/mikroskopie.md) |
| Rechner (calculator) | 66 | 0 | [rechner](methods/rechner.md) |
| TGA | 61 | 1: checks the hint shown when `pyngb` is missing, so it is skipped when `pyngb` is installed | [tga](methods/tga.md) |
| Zugversuch (tensile test) | 36 | 0 | [zugversuch](methods/zugversuch.md) |
| **Total** | **645** | **39** | |

Counts: version 0.1.0, Windows 11, Python 3.12. With the optional data installed
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

   These are the strongest checks of an algorithm.
2. **Independent reference values.** Results compared with numbers that do not come from Folio Lab's own code, such
   as values computed with scipy, tabulated values from NIST-JANAF, NIST ASD or textbooks, and worked examples from
   standards or papers. The expected value and its source are written next to each assertion.
3. **Golden (regression) tests.** A complete report bundle (figures, tables, values, methods text, citations) for a
   fixed input is compared with a stored reference in `tests/golden/`. They detect *unintended changes*. They do not
   prove that the stored result is right, which is what kinds 1 and 2 are for. To regenerate after an intended change,
   run with `FOLIO_GOLDEN_UPDATE=1` and explain the change in the commit. The tensile module's golden test runs on
   the synthetic curve, because real measurements are not published.
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
  - Joback group values (checked only on the worked acetone example, `labcalc/joback.py`).

  The data file or code records this. For ionic radii, Antoine coefficients and colligative constants, the result in
  the Elementrechner also shows it. See [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).
- **Citations not yet verified against the original publication.** For example, two threshold methods in the
  microscopy module (Tsai 1985, Prewitt & Mendelsohn 1966). Each methods page names these.
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
