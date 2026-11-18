# Folio Lab

**Local data analysis and report writing for laboratory measurements.**

Folio Lab joins a LaTeX report editor with analysis modules in one application that runs on your own computer. You
evaluate a measurement, send the result to a report with one click, and insert its figures, tables, values, data
plots, references and methods text. When a measurement or a setting changes later, **Refresh** updates the report.
Every number in a report can be traced back to its raw file, the software versions and the exact settings used.

> **Status: research software, version 0.x.** The methods are documented and checked by automated tests against
> reference values (see [Validation](docs/VALIDATION.md)), but Folio Lab has not been validated independently. Check
> results that you publish against an independent method or reference, and report the versions you used
> ([How to cite](#citing-folio-lab)).

## Modules

| Module | What it does | Guide | Methods |
|---|---|---|---|
| **Zugversuch** (tensile test) | Force–elongation and stress–strain curves from IMADA Force Logger `.flps` files or datasets: linear range, modulus, yield onset, Rp, Rm, elongation at break, comparison with reference materials, PDF report | [guide](modules/zugversuch/README.md) | [methods](docs/methods/zugversuch.md) |
| **Mikroskopie** (microscopy) | Micrographs (TIFF incl. stacks and calibration, PNG, JPEG): filters, 13 automatic thresholds, binary operations, watershed, measurements, particle size and shape distributions, scale bar | [guide](modules/mikroskopie/README.md) | [methods](docs/methods/mikroskopie.md) |
| **Rechner** (calculator) | Calculation with units, 274 equations with sources, equation and system solver, matrices, a graph for functions and large datasets, fits (linearised or direct) with uncertainties | [guide](modules/rechner/README.md) | [methods](docs/methods/rechner.md) |
| **FTIR** | Infrared spectra (JCAMP-DX, SPA, SPC, Agilent `.fir`, Bruker OPUS, CSV): processing, band picking, functional groups, library search, mixtures | [guide](modules/ftir/README.md) | [methods](docs/methods/ftir.md) |
| **TGA** (thermogravimetry) | Text exports of common instruments: DTG, steps and onsets (ISO 11358-1), composition (ASTM E1131, D7582), kinetics from several heating rates, peak separation, library search | [guide](modules/tga/README.md) | [methods](docs/methods/tga.md) |
| **Datenaufbereitung** (data purification) | Excel, ODS, CSV and typed tables become datasets with units: parsing, unit conversion, cleaning, outlier tests with recorded exclusions, exports | [guide](modules/datenaufbereitung/README.md) | [methods](docs/methods/datenaufbereitung.md) |
| **Elementrechner** (chemistry) | Equations and balancing, stoichiometry, thermochemistry, pH and speciation, redox, solution preparation, gases, nuclear chemistry, kinetics, molecule designer | [guide](modules/elementrechner/README.md) | [methods](docs/methods/elementrechner.md) |

All features are listed on one page in [FEATURES.md](FEATURES.md). The module user interfaces start in German and
switch to English with **DE | EN** in the header.

## Installation

### Windows (tested: Windows 11)

1. Install **Python 3.10 or newer** from [python.org](https://www.python.org/downloads/) (or
   `winget install Python.Python.3.12`). The report editor works without Python, but the analysis modules don't.
2. Download this repository (green **Code** button → *Download ZIP*, or `git clone`), and unpack it to a folder
   without special permissions, for example in your *Documents* folder.
3. Double-click **`Start Folio Lab.bat`**. The first start runs `setup.ps1`. It downloads portable Node.js and
   MiKTeX (about 1 GB) into `tools/`, installs the editor libraries (`npm install`) and the Python packages of the
   modules, and needs no administrator rights. Later starts take a few seconds.
4. Your browser opens <http://localhost:4330>. Keep the console window open while you work. Closing it stops Folio
   Lab.

### Linux and macOS (not tested yet)

The server and modules are written to run on other systems, but this has not been tested. You need Node.js 18 or
newer, Python 3.10 or newer, and a TeX distribution (TeX Live or MacTeX; `pdflatex`, `bibtex` or `biber`). Folio Lab
looks for TeX on the PATH, in `/Library/TeX/texbin`, `/usr/local/bin` and `/usr/bin`:

```bash
npm install
python3 -m pip install -r requirements.txt
node server/index.js --open
```

If TeX is not found, set `FOLIO_TEX_BIN` to the folder that holds `pdflatex`. Please report what works and what
doesn't in an issue.

### Optional reference data

Five reference data sets may be used freely but not redistributed, or their terms are unclear. They are therefore
not in this repository:

- the IUPAC pKa dataset (non-commercial licence);
- two NIST Standard Reference Databases (stability constants SRD 46, ionisation energies SRD 78);
- the Burcat thermochemical database;
- the Open Specy FTIR spectra whose source licence is non-commercial or unstated.

Folio Lab works without them, with less coverage. To add them, the script below downloads them from the original
publishers onto your computer and builds the files Folio Lab reads. You accept the publishers' terms when you run it.

```bash
python tools/fetch_optional_data.py --list
python tools/fetch_optional_data.py all
```

The built files are git-ignored, and each records the URL, date and SHA-256 of its originals. If you already have the
original files, `--from <folder>` uses them instead of downloading; `--remove all` deletes the built files again.
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) lists every bundled and optional data source with its licence and
what each module can do without it.

## From measurement to report

1. On the home page, open a module, for example *Tensile test*. It starts in the background.
2. Load your file and set the specimen, material and test conditions.
3. Click **Zum Bericht …** (*to report*). Choose a report or create one from the *Lab report* template (German or
   English), the language of captions and text, and what to include.
4. In the editor, the **Lab** button lists everything in the report from that result:
   - **Figures** (vector PDF) and **tables** (booktabs) with caption and label.
   - **Values** inserted as `\labval{<result>}{<key>}`. The number in the text follows the analysis.
   - **Data** as CSV, with **Plot** to insert a pgfplots chart.
   - **References** (standards, reference data, the raw file) in `lab/references.bib`.
   - **Methods and results** paragraphs, either pasted as editable text or kept linked to the analysis.
5. **Refresh** recomputes the result from the stored raw file. Each refresh is kept as a revision you can compare
   with earlier ones and restore.

## Reproducibility and provenance

- Every result bundle stores the Folio Lab and module versions, the method settings, the SHA-256 checksum of every raw file, and
  the versions of any shared datasets or values it used. See [docs/methods/provenance.md](docs/methods/provenance.md).
- Shared datasets and values are versioned. A consumer either follows the latest version or pins one; a version used by a
  report cannot be deleted.
- Calculations never round internally. Displayed precision is a view setting.
- Bundled reference libraries that are *modelled from literature values* (the FTIR model library and the TGA
  library) are labelled as such in the interface, the figures and the report, and are never presented as
  measurements.

## Citing Folio Lab

Cite the software as given in [CITATION.cff](CITATION.cff) (GitHub: *Cite this repository*), and state:

- the Folio Lab version (for example *0.1.0*) and the version of each module you used (shown in the module header
  and stored in each report bundle);
- the methods and settings that matter for your result, as written in the methods text Folio Lab puts in the
  report, and the original references it cites for them. Those are the scientific sources; Folio Lab is the
  implementation.

## Customising Folio Lab

- **Own reference materials, spectra and TGA references** with a structured source (authors, title, DOI or pasted
  BibTeX). They become proper bibliography entries in the report.
- **Own equations** evaluated on the measured values, with units, in FTIR, TGA and the tensile test. They go to the
  report as values, a table and display math. Own references and equations are plain JSON files in
  `outputs/<module>/` that you can edit, share, and keep under version control.
- **Own modules:** any program that serves a small local HTTP API and writes result bundles can be a module. See
  [docs/MODULES.md](docs/MODULES.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
- **Settings:**
  - `FOLIO_PORT` or `--port=N` changes the port (default 4330).
  - `LAB_PYTHON` chooses the Python interpreter.
  - `FOLIO_TEX_BIN` chooses a TeX `bin` folder.
  - `FOLIO_PROJECTS_DIR` and `LAB_OUTPUTS` move the data folders.

## Documentation

| Document | Content |
|---|---|
| [docs/VALIDATION.md](docs/VALIDATION.md) | What the test suites check and how to run them |
| [docs/methods/](docs/methods/) | Methods, defaults, limits and validation, per module |
| [docs/methods/provenance.md](docs/methods/provenance.md) | Data provenance, versions, reproducibility |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How hub, modules, projects, environments and sharing fit together |
| [docs/MODULES.md](docs/MODULES.md) | How to write a module; bundle format and APIs |
| [FEATURES.md](FEATURES.md) | All features of all modules |
| [CHANGELOG.md](CHANGELOG.md) | Release notes with module versions |

## Folders

| Path | Content |
|---|---|
| `server/` | Hub: report editor API, LaTeX compiler, module registry and proxy, results in reports |
| `public/` | Home page and report editor |
| `modules/<id>/` | Analysis modules, each with `module.json`, a guide and tests |
| `sdk/python/`, `sdk/web/` | Shared calculation core (`labcalc`), reference data, bundles, datasets, page components |
| `docs/` | Documentation |
| `tools/` | Test and data scripts; Node.js and MiKTeX are installed here by `setup.ps1` (not in the repository) |
| `projects/`, `outputs/` | Your reports and module outputs (created on first use; not in the repository) |

## Report editor features

- **Compiling:** pdfLaTeX, XeLaTeX or LuaLaTeX. Missing LaTeX packages are installed on first use.
- **Bibliography:** BibTeX (natbib) and biblatex with Biber are detected and run for you, as are makeindex, glossaries
  and nomencl.
- **Writing help:** helpers for images, figures, tables, pgfplots, `\cite` and `\ref`. Syntax highlighting,
  autocompletion, autosave and an outline.
- **Errors and SyncTeX:** errors are listed and underlined, and you can jump between source and PDF.
- **Projects:** templates (including *Lab report*), ZIP import and export, and combining projects from several
  authors.

## Testing

Each module and the shared core have `unittest` suites, and the same suites run on GitHub Actions for every push.
See [docs/VALIDATION.md](docs/VALIDATION.md) and [CONTRIBUTING.md](CONTRIBUTING.md#running-the-tests).

## Security and privacy

Folio Lab listens on `127.0.0.1` only. Your files and results stay on your computer. See [SECURITY.md](SECURITY.md).

## Contributing

Bug reports, especially about wrong results, and contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

Folio Lab is released under the [MIT licence](LICENSE). Bundled third-party components and data keep their own
licences, listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
