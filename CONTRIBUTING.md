# Contributing to Folio Lab

Thank you for helping. Folio Lab is scientific software, so a contribution is judged first by whether its results
are correct and traceable, and only then by its features.

## Reporting a problem with a result

If you think a number is wrong, open an issue with:

- the Folio Lab version and the module version (module header, or `modules/<id>/module.json`);
- the input (a minimal file or dataset you are allowed to share), the settings, and the result you got;
- the result you expected, and its source (a standard, a paper, or another program, with its version).

## Changing or adding a calculation

1. **Cite the method.** Every algorithm, constant, equation and reference value names its source: a standard, paper
   or textbook, with a DOI where one exists. Put the citation in the code where the value is used and, for data
   files, in their `_source`/`_from` fields. Do not add data whose licence does not allow redistribution under the
   terms in `THIRD_PARTY_NOTICES.md`. Add such data to `tools/fetch_optional_data.py` instead.
2. **Add a test against an independent reference value**, for example a worked example from the standard, a
   published table, or a synthetic input whose answer is known analytically. Name the source in the test.
   `docs/VALIDATION.md` describes the test suites.
3. **Update the documentation:**
   - the module guide (`modules/<id>/README.md`);
   - its methods page (`docs/methods/<id>.md`), covering what is computed, the defaults, the limits and the
     validation;
   - `CHANGELOG.md`.
4. **Bump the module version** in `modules/<id>/module.json` and the package's `__init__.py` whenever results or
   report output can change.
5. **Re-check golden files.** If report bundles change on purpose, regenerate them with `FOLIO_GOLDEN_UPDATE=1`.
   Explain in the pull request why the output changed.

## Running the tests

```bash
cd sdk/python
python -m unittest discover -s tests
```

For a module, from the module folder, with the SDK on the path:

```bash
cd modules/rechner
PYTHONPATH=../../sdk/python:. python -m unittest discover -s tests
```

On Windows PowerShell: `$env:PYTHONPATH="..\..\sdk\python;."` and then the same command.

## Adding a module

`docs/MODULES.md` describes the module contract: `module.json`, the local HTTP API, result bundles for reports,
environments, sharing and datasets. `docs/ARCHITECTURE.md` explains how the parts fit together.

## Style

- Python 3.10+, standard library plus numpy and matplotlib; ask in an issue before adding a dependency.
- Browser code is plain JavaScript without a build step.
- The user interface is German by default with an English switch. Add every visible string in both languages.
- Server messages are in German; documentation is in English.

## Licence

By contributing you agree that your contribution is licensed under the MIT licence of this repository.
