# FTIR: methods and validation

This document describes every number the FTIR module (`modules/ftir/`) can put into a report: how it is computed,
with which defaults and limits, which reference the code cites, and which automated test checks it. Everything
here was read from the code of module version 1.5.0. Where the code cites no source, this document says
"no external reference". Where no test checks a computation, it says "no test".

User guide: [`modules/ftir/README.md`](../../modules/ftir/README.md).

## How to cite results from this module

Report the Folio Lab version (`version` in `package.json` at the repository root)
and the FTIR module version (`version` in `modules/ftir/module.json`; 1.5.0). Every report bundle that the module
sends to a report records, in its manifest, the Folio Lab version (`provenance.suite_version`), the module version
(`provenance.module_version`) and the SHA-256 hash
of each source data file stored in the bundle (`provenance.source_sha256`) (`server/lab.js`). The bundle also
stores the source files and the processing state, so the result can be recomputed. *Refresh* in the report
recomputes with the module version installed at that moment and records it in a new revision. If you report a
library hit, also name the library and, for measured references, the original source of the reference spectrum
(the report does this in the caption automatically, see section 15). Hits from the model library are not
identifications (section 9.2).

## Conventions

* Spectra are held internally with **ascending** wavenumber ν̃ in cm⁻¹; plots reverse the axis.
* y-unit codes used below: `A` absorbance, `T` transmittance in %, `R` reflectance in %, `KM` Kubelka-Munk,
  `LR` log(1/R), `au` arbitrary units, `D1`/`D2` first/second derivative.
* Test references have the form `path::TestClass::test_name`, with paths relative to the repository root. Run the
  tests with `python -m unittest discover -s tests` in `modules/ftir`. All 73 tests passed for this document
  (48 in the earlier files plus 25 in `tests/test_science.py`, which holds known-answer checks for the changes of
  version 1.5; two of them compare with SciPy and are skipped if SciPy is not installed; tests needing the optional
  Open Specy part are skipped without it).
* Many tests use synthetic spectra built from the model library (`ftir/refdata.py`, section 9.2). Such tests show
  that the code behaves as designed. They are not evidence of accuracy on measured spectra.

---

## 1. File readers

Format detection (`ftir/readers.py::load_bytes`): Bruker OPUS by its magic bytes `0A 0A FE FE` (any extension);
`.spa` → OMNIC; `.spc`/`.fir`, or second byte `0x4B` → SPC; `.jdx`/`.dx`/`.jcamp`/`.jcm` or text starting with
`##` → JCAMP-DX; other binary content is refused; everything else is read as a text table. The hub offers the
extensions `.jdx .dx .jcamp .jcm .spa .spc .fir .csv .txt .dpt` and the OPUS numeric extensions `.0` … `.9`
(`module.json` `accepts`); OPUS files with other extensions are still recognised by their magic bytes when opened in
the module.

| Format | What is read | Metadata taken | y unit |
|---|---|---|---|
| JCAMP-DX (`readers.py::read_jcamp`) | `##XYDATA=(X++(Y..Y))` in AFFN, SQZ, DIF, DUP (mixed); DIF Y-check values at line starts are dropped; `##XYPOINTS`/`(XY..XY)` and peak tables as x,y pairs; several blocks per file (one spectrum each, a new block starts at `##TITLE`); `$$` comments ignored. x for X++ is a linear axis from `FIRSTX` to `LASTX` (or `FIRSTX + DELTAX·(n−1)`); `NPOINTS` truncates; `XFACTOR`/`YFACTOR` applied | `TITLE` (name), `ORIGIN`, `OWNER`, `DATE`/`LONG DATE`, `SPECTROMETER/DATA SYSTEM`, `RESOLUTION`, `CAS NAME`, `CAS REGISTRY NO`, `MOLFORM`, `SAMPLING PROCEDURE`, `STATE`; Folio fields `##$FOLIO REF` (provenance of library references) and `##$FOLIO DATASET` (provenance from a dataset) | from `YUNITS`: ABSORB… → A; TRANSM… → T (×100 if max ≤ 1.5); KUBELKA… → KM; REFLECT… → R (×100 if max ≤ 1.5); LOG(1/R) → LR; otherwise guessed (below). x from `XUNITS`: 1/CM → cm⁻¹, MICRO… → µm, NANO… → nm; missing or unknown `XUNITS` → guessed (below) |
| Thermo OMNIC `.spa` (`read_spa`) | Directory at byte 304 (16-byte entries): key 2 = header (n, y type, first/last x as float32), key 3 = float32 data; fallback to fixed offsets for an older layout. x is linear between first and last x | title (bytes 30–285) | type 17 → A, 16 → T, 11 → R, 12 → LR, 20 → KM; T/R ×100 if max ≤ 1.5; unknown → guessed |
| GRAMS/Galactic `.spc` (`read_spc`) | New format only (byte 1 = `0x4B`); float32 or scaled int16/int32 (exponent 2^(e−16) / 2^(e−32)); common x array, linear x, or per-subfile XY; several subfiles = several spectra | comment (bytes 88–217) as name; resolution text (bytes 36–44); log block `key=value`: `SampleID` → sample, `Spectrum` → source file | y type 2 → A, 3 → KM, 10 → LR, 128 → T, 129 → R (T/R ×100 if max ≤ 1.5); other → guessed. x type (`fxtype`) 1 → cm⁻¹, 2 → µm, 3 → nm, 13 → Raman shift in cm⁻¹ (read, with a notice that assignments and libraries are for IR), 0 (arbitrary) → guessed (below); every other code (e.g. 4 seconds, 5 minutes, 6 Hz …) is refused with a German message. The code is stored as `spc_fxtype` |
| Agilent MicroLab `.fir` | Read as SPC (above) | as SPC, plus format "Agilent MicroLab (.fir, SPC)" and instrument "Agilent MicroLab" when the extension is `.fir` or the log names MicroLab or an `.a2r` file | as SPC |
| Bruker OPUS (`ftir/opus.py`) | Directory of 12-byte entries; data blocks AB (result, type 15), ScSm and ScRf (single-channel sample/reference) are opened, in that order; for each, the parameter block (type + 16) must give `NPT`, `FXV`, `LXV`; y = float32 × `CSF`; x linear from `FXV` to `LXV`; `DXU` = `WN` (cm⁻¹) or `MI` (µm, converted), other x units refused. Interferograms (IgSm, IgRf), phase (PhSm) and unknown blocks are listed in the metadata, not opened. A corrupt parameter entry stops reading | `SNM` (name), `INS` instrument, `RES` resolution, `NSS` scans, `DAT`, `TIM`, `SFM` sample form; format label "nach öffentlicher Formatbeschreibung, noch nicht mit echten OPUS-Dateien geprüft" | AB: from `PLF` (AB → A, TR → T, RF → R, KM → KM), else guessed; single-channel spectra: `au` |
| Text/CSV (`read_table`) | Tries `;`, tab, `,` and whitespace; keeps the delimiter that gives the most consistent rows (score = rows × min(columns, 6)); decimal comma accepted unless the delimiter is a comma (shared parser `labtable`, also `1.234,5`); the row before the data is the header; footer lines after the data stop reading; ≥ 10 rows; each further numeric column = one spectrum | column header as name suffix and unit hint | from the header text (`abs`, `extinkt`, `a`, `(a)` → A; `kubelka`, `KM` → KM; `refl`, `%R`, `remission` → R; `%T`, `trans` → T), else guessed. x from the first header: `µm`, `um` (as a word), `micro`, `mikro` → µm; `nm`, `nano` → nm; `cm-1`, `cm^-1`, `cm⁻¹`, `1/cm`, `wavenumber`, `Wellenzahl` → cm⁻¹; otherwise guessed |

**Units the file does not state** (`readers.py::x_axis`, `y_values`). Order of precedence: (1) the unit stated in
the file; (2) the user's choice in the dialog *Einheiten …* (units; options x: cm⁻¹, µm, nm; y: A, T, R, KM, log(1/R),
arbitrary), passed to the reader as `{"xunit", "yunit"}` and stored with the spectrum (`read_opts`, also in the
report bundle, so *Refresh* reads the file the same way); (3) a guess, recorded in the metadata as
`x_unit`/`y_unit` "… (geraten)" and shown as a notice (`kind` `guess_x`/`guess_y`) with the button *Einheiten …*.

* **x guess:** largest x value ≤ 50 (`X_MICRON_MAX`) → wavelength in µm, otherwise wavenumber in cm⁻¹. Rationale:
  mid-IR wavenumbers are far above 50 cm⁻¹ and mid-IR wavelengths far below 50 µm; no external reference.
* **y guess** (`guess_from_values`): median between 20 and 110 and maximum ≤ 130 → T in %; 0.5 < median ≤ 1.05,
  maximum ≤ 1.25, minimum ≥ −0.05 and (max − median) < 0.5·(median − min) → T as a fraction, multiplied by 100;
  otherwise A.
* Unknown choices are refused (German message). OPUS uses the same rule for the y unit when `PLF` is missing.

**Common checks for every reader** (`Spectrum.__post_init__`, `_check`, `make_uniform`): non-finite points are
dropped; points are sorted by x; repeated x values keep the first; at least 10 points; x must lie within
0–50 000 cm⁻¹. If spacing varies by more than 2 % of the median step, the spectrum is linearly interpolated onto a
uniform grid with the median step (n = round((x_max − x_min)/step) + 1) and the metadata records `resampled`.

**Writers.** JCAMP-DX 4.24 `(XY..XY)` with x to 4 decimals and y to 6 significant digits; Folio provenance fields
are written as `##$FOLIO REF`/`##$FOLIO DATASET`. CSV with x to 4 decimals and y to 7 significant digits. The
export tables (`banden.csv`, `treffer.csv` …) use semicolons, decimal commas and 6 significant digits.

Reference: no external reference (the OPUS docstring says the layout follows "die öffentlich dokumentierte Struktur,
wie sie freie Leser beschreiben"; no source is named).

Validation:

| Test | Checks |
|---|---|
| `modules/ftir/tests/test_ftir.py::ReaderTest::test_csv_semicolon_decimal_comma_transmission` | `;` + decimal comma, %T header → unit T, 3401 points, ascending x, value at 2000 cm⁻¹ equal to input to 2 decimals |
| `…::ReaderTest::test_csv_multiple_columns` | three y columns → three spectra |
| `…::ReaderTest::test_jcamp_roundtrip` | write and read JCAMP: unit A, y equal within rtol 1e-5, atol 1e-6 |
| `…::ReaderTest::test_jcamp_compressed_difdup` | SQZ/DIF/DUP with Y-check values: y = integers × 0.0001 within 1e-9, correct point count and last x |
| `…::ReaderTest::test_jcamp_multiblock_and_transmission_fraction` | two blocks with their titles; fractional transmittance converted to % (max > 50) |
| `…::ReaderTest::test_spa` | name, unit A, y within 1e-5; type 16 → T in % |
| `…::ReaderTest::test_spc_float_and_int` | float32 y within 1e-5; scaled int32 y within 1e-6 |
| `…::ReaderTest::test_agilent_fir` | generated `.fir`: y within 1e-5, resolution "4", SampleID, instrument, source file |
| `…::ReaderTest::test_rejects_garbage` | binary garbage and a 2-row CSV are refused |
| `…::ReaderTest::test_samples_load` | the three built-in examples load |
| `modules/ftir/tests/test_opus.py::Opus::test_round_trip_absorbance` | generated OPUS file: name from `SNM`, unit A, x 400–4000, y within 1e-6 after `CSF` = 0.5, maximum at 1720 cm⁻¹, sample form read |
| `…::Opus::test_micrometre_axis_and_single_channel` | µm axis converted (x₀ = 400 within 1e-3), single channel → `au` |
| `…::Opus::test_unknown_blocks_reported_not_guessed` | unknown block and interferogram listed in metadata, not opened |
| `…::Opus::test_broken_files_rejected` | truncated file, block outside file, interferogram-only file refused |
| `…::Opus::test_param_block_corruption_detected` | corrupt parameter entry raises an error |
| `modules/ftir/tests/test_science.py::UnitsTest::test_table_without_units_guessed_with_warning_and_override` | table without header: x guessed cm⁻¹ and y guessed A, both with a notice; with the choice {cm-1, A} no notice and `read_opts` stored; unknown choice refused |
| `…::UnitsTest::test_micrometre_rule_and_declared_header` | x 2.5–25 without unit → µm (max 4000 cm⁻¹ = 10⁴/2.5) with notice; header "Wellenzahl [cm-1]" → taken as cm⁻¹, no notice |
| `…::UnitsTest::test_spc_fxtype` | SPC fxtype 3 (nm) 2500–25000 → 4000–400 cm⁻¹ (10⁷/λ); fxtype 2 (µm) → 4000 cm⁻¹; fxtype 4 refused; fxtype 0 guessed with notice; fytype 128 with 0.5 → T = 50 % |

Not tested: the older `.spa` layout, SPC subfiles with own x values, JCAMP `XUNITS` in µm/nm, OPUS `PLF` other than
absorbance, the *Einheiten …* dialog itself (interface). Only generated files are used; no real instrument file is
part of the tests.

## 2. Unit and axis conversions

| Conversion | Formula | Where |
|---|---|---|
| µm → cm⁻¹ | ν̃ = 10⁴ / λ[µm] | `readers.py::x_axis`, `opus.py` |
| nm → cm⁻¹ | ν̃ = 10⁷ / λ[nm] | `readers.py::x_axis` |
| any length unit (datasets) → cm⁻¹ | ν̃ = 0.01 / λ[m]; λ must be > 0 | `dataset.py::x_values` |
| T or R → A (or log(1/R)) | A = −log₁₀(max(T/100, 10⁻⁴)), so A ≤ 4 | `process.py::to_absorbance` |
| A → T | T = 100 · 10^(−A) | step `to_trans` |
| R → Kubelka-Munk | f(R) = (1 − R)² / (2R), with R = %R/100 clipped to [10⁻⁴, 1] | step `km` |

Converting R with "In Absorbanz umrechnen" gives log(1/R) and labels it `LR`.

Reference: no external reference.

Validation: `modules/ftir/tests/test_ftir.py::ProcessTest::test_absorbance_transmission_roundtrip` (T → A equals
the generating absorbance within 1e-9; A → T returns the input within rtol 1e-9);
`modules/ftir/tests/test_dataset.py::DatasetSpectra::test_transmittance_and_wavelength` (µm column → 400–4000 cm⁻¹
within 1e-3). Kubelka-Munk values: no test (only that the step refuses absorbance input,
`test_ftir.py::ProcessTest::test_op_requires_unit`).

## 3. Signal quality: noise, S/N, noisy regions, saturation

Used for the status line, the warnings, the report sentence on S/N, and as input to band picking (section 5),
group assessment (section 8) and search (section 10). Code: `ftir/quality.py`.

1. Residual r = y − SG₇,₃(y) (Savitzky-Golay, 7 points, cubic).
2. Local noise σ_loc(ν̃) = 1.4826 · median(|r|) / √(1 − h₀), running median over w points,
   w = min(101, max(9, int(80 cm⁻¹ / step))); h₀ = 7/21 is the centre coefficient of the 7-point filter.
3. σ₀ in two stages: preliminary value s = 25th percentile of σ_loc; then σ₀ = 1.4826 · median(|r|) / √(1 − h₀)
   over all points with σ_loc ≤ 2·s (the quiet points: noisy windows and dense band regions, where the residual
   contains signal, are left out). For white Gaussian noise σ₀ estimates its standard deviation: in the test the
   mean ratio σ₀/σ over 8 noise realisations is 0.98–1.00 at 0.5–2 cm⁻¹ spacing and 0.975 at 4 cm⁻¹ (measured
   0.92 at 8 cm⁻¹, not part of the test). Up to 1.4, σ₀ was the 25th percentile alone, which lies below σ (mean
   ratio 0.91 at 1 cm⁻¹, 0.82 at 4 cm⁻¹, 0.76 at 8 cm⁻¹ spacing).
4. Noise-dominated where the span (max − min) of a ≈12 cm⁻¹ moving mean within the same window is < 8 · σ_loc.
   Core noisy points: σ_loc > 3.5 σ₀ and noise-dominated. A noisy region is a run of points with σ_loc > 2 σ₀ and
   noise-dominated that contains a core point; runs are merged across gaps < max(60 cm⁻¹, 3 steps) and kept if
   ≥ 40 cm⁻¹ wide. A region overlapping 2250–1950 cm⁻¹ is labelled "typical of diamond ATR".
5. S/N = signal / σ₀. Signal = height of the strongest band = maximum of (m − rubber band of m) over the points
   outside noisy regions, where m is the moving mean of y over round(12 cm⁻¹/step) points (made odd). For T and R
   the signal is computed on −y (in %T). The moving mean keeps single noise spikes small; bands narrower than about
   12 cm⁻¹ FWHM are lowered by it (a Gaussian of FWHM 40 cm⁻¹ by ≈ 2 %). Up to 1.4 the signal was the 99.5th
   percentile instead of the maximum.
6. Warnings: S/N < 15 "hardly any signal"; S/N < 50 "weak signal"; absorbance: 99.9th percentile > 1.5 "may be
   saturated"; T/R: 0.1th percentile < 1 % "may be saturated". For derivatives only σ₀ is computed.
7. Effective noise per point (for band picking): σ₀, or max(σ₀, σ_loc) where the signal is noise-dominated or the
   point lies in a noisy region.

This S/N is a module-specific definition (strongest band over the noise of the quiet sections), not a standard
one. The report text says "about" and states the definition above.

Reference: the residual uses a Savitzky-Golay filter (`savitzky1964`, cited in the report whenever an S/N value is
given); the robust scale 1.4826 · median|r| (consistent for the normal distribution) and the rest of the procedure:
no external reference.

Validation:

| Test | Checks |
|---|---|
| `modules/ftir/tests/test_ftir.py::QualityTest::test_diamond_window_detected_and_ignored` | synthetic weak PS with 10× noise in 2300–1900 cm⁻¹: exactly one noisy region, upper edge 2250–2340, lower edge 1860–1950 cm⁻¹; warning names diamond ATR; no bands picked in 1900–2300; PS bands at 698 and 1493 found (±4 cm⁻¹); nitrile/isocyanate/alkyne not above "unlikely"; aromatic "likely"; search vector empty in 2000–2200; derivative search still ranks PS first |
| `…::QualityTest::test_clean_and_weak_spectra` | clean synthetic PET: no noisy region, S/N > 50, no S/N warning; very weak spectrum: S/N < 15 with warning, no absence statements, ≤ 2 "likely" classes |
| `modules/ftir/tests/test_science.py::SnrTest::test_sigma_is_standard_deviation_of_white_noise` | white noise σ = 0.01 at 0.5, 1, 2, 4 cm⁻¹ spacing: mean σ₀/σ over 8 seeds = 1 ± 0.05 |
| `…::SnrTest::test_snr_is_band_height_over_sigma` | one Gaussian band, height 1, FWHM 40 cm⁻¹, σ = 0.01: signal 0.98 ± 0.02, S/N 98 ± 8 (expected 100 × 0.98 from the moving-mean attenuation) |

## 4. Processing steps (the protocol)

A protocol is a list of steps. It is always applied to the original spectrum, in the same way for the interface,
the export and the report (`ftir/process.py::apply`). Steps that need a particular y unit refuse other units.

| Step (`op`) | Needs | Parameters: default (limits in the interface) |
|---|---|---|
| `to_abs` convert to absorbance | T or R | – |
| `to_trans` convert to transmittance | A | – |
| `km` Kubelka-Munk | R | – |
| `cut` cut range | any | lo 650, hi 4000 cm⁻¹; at least 10 points must remain |
| `interp` fixed spacing | any | step 2 cm⁻¹ (choices 0.5, 1, 2, 4, 8) |
| `smooth` smoothing | any | method Savitzky-Golay; window 9 points (3–101, odd); polynomial order 2 (1–5) |
| `baseline` | any | method rubber band; ALS log₁₀λ 6 (2–10), λ refers to 1 cm⁻¹ spacing (`lam_ref` "cm1", default) or per data point ("point", behaviour up to 1.4), p 0.01 (0.0005–0.2); polynomial degree 3 (1–8); anchor points: spline (or linear) |
| `co2` bridge CO₂ bands | any | `ranges` "narrow" (default): 2390–2280 and 680–655 cm⁻¹; "wide" (up to 1.4): 2400–2250 and 720–630 cm⁻¹ |
| `atr` ATR correction | A | reference wavenumber 1000 cm⁻¹ (100–5000; ≤ 0 refused) |
| `normalize` | any (mode "band": A, LR, KM or `au` only) | mode maximum; band position 1720 cm⁻¹ for mode "band" |
| `offset` | any | mode minimum → 0; or add a value (0) |
| `scale` | any | factor 1 |
| `deriv` derivative (Savitzky-Golay) | any | order 1 (or 2); window 11 points (5–101, odd) |

### 4.1 Baselines

The baseline is subtracted. For T and R the baseline is fitted to −y and the result is shifted so the baseline
lies at 100 % (y − b + 100).

* **Rubber band** (`rubberband`): lower convex hull of the points (Andrew's monotone chain), connected by straight
  lines. No parameters. Fitted to the unsmoothed data in this step. Reference: no external reference.
* **ALS** (`als_baseline`): minimises Σ wᵢ(yᵢ − zᵢ)² + λ Σ(Δ²zᵢ)² by solving (W + λDᵀD) z = W y with the
  five-banded matrix DᵀD of second differences (own LDLᵀ solver); weights wᵢ = p where yᵢ > zᵢ, else 1 − p;
  at most 10 iterations, stops when the weights no longer change.
  **λ and point spacing** (`als_lambda`): the penalty acts per data point. With spacing h, Σ wᵢ(yᵢ − zᵢ)² +
  λ Σ(Δ²zᵢ)² ≈ (1/h)·[∫ w (y − z)² dν̃ + λ h⁴ ∫ (z'')² dν̃], so the smoothness depends on λh⁴. By default
  (`lam_ref` "cm1") the entered log₁₀λ refers to 1 cm⁻¹ spacing and the solver uses λ = 10^(log₁₀λ) · (1 cm⁻¹/h)⁴,
  h = median spacing; the same setting then gives the same baseline on any grid. With "point" (behaviour up to
  1.4), λ = 10^(log₁₀λ) per data point. For 1 cm⁻¹ data both are identical; for 2 cm⁻¹ data "cm1" uses λ/16,
  for 4 cm⁻¹ λ/256. The scaling is derived here from the discretisation; Eilers & Boelens do not give it.
  Reference (cited when ALS is used): "Eilers, Paul H. C. and Boelens, Hans F. M., Baseline Correction with
  Asymmetric Least Squares Smoothing, Leiden University Medical Centre, 2005" (techreport, `eilers2005`).
* **Polynomial, iterative** (`poly_baseline`): x scaled to [−1, 1]; fit a polynomial of the chosen degree; replace
  y by min(y, fit); repeat up to 100 times until nothing changes (tolerance 10⁻⁹ · range). Reference (cited in the
  report when used, `lieber2003`): Lieber, C. A. and Mahadevan-Jansen, A., "Automated method for subtraction of
  fluorescence from biological Raman spectra", Applied Spectroscopy 57 (11), 1363–1367, 2003 (no DOI given; not
  verified against the publication here).
* **Anchor points by hand** (`points_baseline`): at least two anchor wavenumbers inside the spectrum. Each anchor
  height is the mean of up to 5 points around the nearest data point. Connection: natural cubic spline (≥ 3
  anchors, default) or straight lines. Outside the outermost anchors, the linear option holds the end values;
  the spline option extends the end polynomial. Reference: no external reference.

Validation: `modules/ftir/tests/test_ftir.py::ProcessTest::test_baselines_remove_offset_and_slope`. A synthetic PET
spectrum plus offset 0.2 and slope 0.1 over 600–4000 cm⁻¹: after rubber band, ALS (λ = 10⁶, p = 0.01) and
polynomial (degree 2), |y| < 0.03 in the band-free 1900–2600 cm⁻¹ region and y(1714 cm⁻¹) within 0.05 of the true
value; anchor points (linear, 4 anchors): |y(2200 cm⁻¹)| < 0.01. The preview baseline length is checked in
`…::ServerTest::test_flow`.

| Test | Checks |
|---|---|
| `modules/ftir/tests/test_science.py::AlsTest::test_lambda_scaling` | h = 2 cm⁻¹, log₁₀λ 6: λ = 10⁶/16 ("cm1"), 10⁶ ("point"); h = 1: 10⁶ |
| `…::AlsTest::test_same_baseline_on_any_grid` | same curve on 1 and 2 cm⁻¹ grids: baselines agree within 1e-4 with "cm1" (measured 7e-6), differ by > 5e-3 with "point" |
| `…::AlsTest::test_banded_solver_against_scipy` | own LDLᵀ solver of (W + λDᵀD) z = W y equals `scipy.sparse.linalg.spsolve` (rtol 1e-8; n = 300, λ = 10⁴, random weights); skipped without SciPy |
| `…::AlsTest::test_old_behaviour_selectable` | "point" is described as "je Punkt"; unknown `lam_ref` refused |

### 4.2 Smoothing

* **Savitzky-Golay** (`savgol`, `sg_coeffs`): convolution coefficients from the least-squares fit of a polynomial
  of the given order over the window (pseudo-inverse of the Vandermonde matrix). Ends: point reflection about the
  first and last value (2y₀ − y_k …). If the window is longer than the spectrum, it is shortened.
  Reference in the code: "Savitzky, Abraham and Golay, Marcel J. E., Smoothing and Differentiation of Data by
  Simplified Least Squares Procedures, Analytical Chemistry 36 (8), 1627–1639, 1964" (`savitzky1964`).
* **Moving mean** (`moving_mean`): unweighted mean over the window; ends padded with the end values. Reference: no
  external reference. The report describes it in its own sentence and cites Savitzky and Golay only for
  Savitzky-Golay smoothing, derivatives and the noise estimate (section 3).

Validation: `modules/ftir/tests/test_ftir.py::ProcessTest::test_savgol_preserves_polynomial` (11 points, order 2:
a quadratic is reproduced to 1e-10 away from the ends and to < 1e-3 at the ends; the first derivative equals
6x − 1 to 1e-8 away from the ends). Moving mean: no test.

### 4.3 CO₂ bridging

Atmospheric CO₂ absorbs with the antisymmetric stretch ν₃ (band centre ≈ 2349 cm⁻¹, P and R branches) and the
bending mode ν₂ (Q branch ≈ 667 cm⁻¹). In each range, y is replaced by a straight line between the mean of the edge
points (up to 4 points at each end, including the edge point).

* **Ranges** (`CO2_SETS`): "narrow" (default since 1.5) 2390–2280 and 680–655 cm⁻¹, covering only these bands, so
  that sample bands next to them stay (polystyrene ≈ 698, calcite ≈ 712 cm⁻¹; the isocyanate range of the
  correlation table, 2280–2240 cm⁻¹, now only touches the range at its upper limit). Talc (≈ 669 cm⁻¹) still lies
  inside 680–655 cm⁻¹ at the position of the CO₂ Q branch; the overlap check below cannot tell the two apart, so for
  talc-filled samples leave the step out or use a fresh background. "wide" 2400–2250 and 720–630 cm⁻¹ is the behaviour up to 1.4. The limits are module choices; no
  external reference. Whether the narrow ranges hold all of the CO₂ absorption of a given instrument and
  resolution: not checked.
* **Overlap check** (`co2_overlap`, on the band direction, i.e. −y for T/R): a notice (`kind` `co2_overlap`, shown
  under the spectrum and written into the methods text as "Hinweis/Note") if (1) in the 15 cm⁻¹ flanks just
  outside a range the curve deviates from the straight line through the flanks by more than max(5σ, 0.2 × the
  largest deviation inside the range) — a sample band reaches across the limit — or (2) the largest deviation inside
  the range (if > 5σ) lies outside 2330–2370 cm⁻¹ (ν₃) or 662–672 cm⁻¹ (ν₂). σ: σ₀ of the whole curve (section 3).
* Reference: no external reference for ranges or check (band positions of CO₂ are textbook values).

Validation:

| Test | Checks |
|---|---|
| `modules/ftir/tests/test_science.py::Co2Test::test_narrow_keeps_neighbouring_sample_bands` | PS + calcite model: values at 698 and 712 cm⁻¹ unchanged with "narrow", changed with "wide"; 2270 cm⁻¹ unchanged |
| `…::Co2Test::test_overlap_warning` | synthetic CO₂ doublet 2360/2340 + 668 cm⁻¹ on a flat line: no notice; plus a band at 2285 cm⁻¹ (FWHM 30): notice for 2390–2280 |
| `…::Co2Test::test_unknown_ranges_refused` | unknown range set refused |

### 4.4 ATR correction

y_corr = y · ν̃ / ν̃_ref (ν̃_ref default 1000 cm⁻¹, must be > 0). Basis: the penetration depth of the evanescent wave
is d_p = λ / (2π n₁ √(sin²θ − (n₂/n₁)²)) (Harrick 1967; λ wavelength, n₁ crystal, n₂ sample refractive index, θ
angle of incidence). At fixed θ and constant n₁, n₂, d_p ∝ λ ∝ 1/ν̃, and for weak absorption the ATR absorbance is
proportional to d_p; multiplying by ν̃/ν̃_ref brings every band to the penetration depth at ν̃_ref.
Assumptions: constant refractive indices (no dispersion, which shifts and distorts strong bands), weak absorption,
same θ and number of reflections; refractive index, angle and crystal material are not used, so this is the usual
"simple" ATR correction, not an optical model. Reference (cited in the report when used, `harrick1967`): Harrick,
N. J., Internal Reflection Spectroscopy, Interscience Publishers, New York, 1967 (no page given).

Validation: `modules/ftir/tests/test_science.py::AtrTest::test_atr_factor_is_wavenumber_over_reference` (y = 1 →
ν̃/1000 exactly; two equal bands at 3000 and 1000 cm⁻¹ → ratio 3 after correction; ν̃_ref = 0 refused).

### 4.5 Derivatives

Savitzky-Golay derivative with polynomial order 2 for the first and 3 for the second derivative, divided by
Δν̃^order, where Δν̃ is the median point spacing. Result units are y per cm⁻¹ (or per cm⁻²); the unit becomes `D1`
or `D2`. Derivatives are not used for search (the original is searched instead, section 10) and cannot be stored
as library references. Reference: as for Savitzky-Golay (4.2). Validation: the derivative of the SG function is
tested (4.2); the `deriv` step itself and the second derivative: no test.

### 4.6 Normalisation

| Mode | Formula |
|---|---|
| maximum | y / max\|y\| |
| min-max | (y − min y) / (max y − min y) |
| vector | y / √(Σ yᵢ²) (sum over points; not weighted by spacing) |
| area | y / \|∫ y dν̃\| (trapezoidal rule) |
| band | y / max(y) within ±5 cm⁻¹ of the given position; only for absorbance-like spectra (A, LR, KM, `au`); T and R are refused with the German message to convert to absorbance first; refused if the maximum there is ≤ 0 |

If the divisor of the other modes is 0 the spectrum is left unchanged. Reference: no external reference.
Validation: maximum mode gives max = 1 within 1e-6 in
`test_ftir.py::ProcessTest::test_pipeline_steps_described_and_cut`;
`test_science.py::NormalizeTest::test_peak_normalisation_refused_for_transmission` (T refused; after conversion
to absorbance the band at 1714 cm⁻¹ is 1 within 1e-12) and `…::test_peak_normalisation_needs_positive_band`; min-max,
vector and area modes: no test.

### 4.7 Cut, interpolate, offset, scale

Cut keeps lo ≤ ν̃ ≤ hi. Interpolate: linear interpolation onto ν̃ = k·step from the first multiple of the step at or
above the first point up to the last point. Offset: subtract the minimum, or add a value. Scale: multiply by a
factor. Validation: cut bounds in `test_ftir.py::ProcessTest::test_pipeline_steps_described_and_cut`; interpolate,
offset, scale: no test.

## 5. Band picking

Code: `ftir/peaks.py::find`. For T and R, bands are minima: the search runs on −y.

1. Noise (if the S/N criterion is on, ≥ 30 points, not a derivative): section 3 on the searched curve. Noisy
   regions are excluded.
2. Range = max − min of the curve outside noisy regions.
3. Candidates are local maxima (centre of flat tops).
4. Prominence = height above the higher of the two minima found on each side up to the next higher point (or the
   end of the spectrum).
5. Kept if: prominence ≥ `prominence` % × range; height ≥ min + `threshold` % × range; prominence ≥ `snr` × effective
   noise at the band; band not in a noisy region.
6. Greedy selection by prominence with minimum spacing `distance`, at most `max` bands.

Defaults: prominence 2 %, distance 8 cm⁻¹, threshold 0 %, max 60, snr 10. (The code comment calls 10 × noise the
usual limit of quantification and explains that this prominence also includes baseline waviness.)

Reported per band:

* Position: vertex of the parabola through the maximum and its two neighbours (if the parabola opens downward and
  the vertex lies within one step); height: the parabola's value there (for T/R the transmittance at the minimum).
* FWHM: width at half the prominence, linearly interpolated between neighbouring points, limited to the band's
  feet.
* Area (export column `Flaeche`): trapezoidal area above the straight line between the feet, clipped at zero,
  within ±3 FWHM (FWHM at least 2 cm⁻¹).
* For T and R, bands are found and positioned on −y, but FWHM and area are computed on the curve converted to
  absorbance (−log₁₀(T/100)) or log(1/R), with the same feet; the report notes this under the band table. On −%T a
  band is wider than in absorbance and its area is not proportional to the amount (up to 1.4 both were taken from
  −%T).
* Relative intensity rel = prominence / largest prominence; label vs (rel ≥ 0.75), s (≥ 0.4), m (≥ 0.15), w
  (below); "br" (broad) if FWHM > 60 cm⁻¹.
* Bands set by hand: highest point within ±max(6 cm⁻¹, 2 steps) of the click; feet searched within ±60 cm⁻¹.
  Bands deleted by hand: any band within ±max(3 cm⁻¹, 1.5 steps).

Reference: no external reference for the algorithm. The report cites `socrates2001` for the assignments (section
7).

Validation:

| Test | Checks |
|---|---|
| `modules/ftir/tests/test_ftir.py::PeaksGroupsTest::test_pet_peaks_and_manual_edit` | model PET (prominence 3 %): bands within ±2 cm⁻¹ of 1713, 1240, 1094, 723; strongest labelled vs; band removed at 1713 and set by hand at 1600 |
| `…::PeaksGroupsTest::test_valleys_in_transmission` | transmittance: band within ±2 cm⁻¹ of 1713; minimum y < 30 %T |
| `…::QualityTest::test_diamond_window_detected_and_ignored` | no bands in the noisy window; PS bands found |
| `modules/ftir/tests/test_golden.py::GoldenBundle::test_bundle_en` (and `test_bundle_de`) | regression of the complete report for the synthetic PET example (`samples.make("pet")`): 14 bands, the band table and `data/peaks.csv` must match the stored file `tests/golden/ftir_en.json` |

| `modules/ftir/tests/test_science.py::AreaBasisTest::test_peak_width_and_area_of_transmission_band` | Gaussian absorbance band (height 0.8, σ = 10 cm⁻¹) given as %T: FWHM 23.548 ± 0.05 cm⁻¹ (2√(2 ln 2)·σ), area 20.053 ± 0.01 (0.8·σ·√(2π)), position and height stay in %T |

## 6. Band areas, heights and ratios

Code: `ftir/peaks.py::integrate`, `ftir/analysis.py::run`.

* Points with lo ≤ ν̃ ≤ hi are used (at least 3, else no value). T is converted to absorbance A = −log₁₀(T/100)
  and R to log(1/R) before integrating (`AREA_BASIS`; the result records `basis`). Only there are areas and heights
  proportional to the amount (Lambert-Beer). Up to 1.4, −%T was integrated.
* Base "linear": straight line through the first and last point of the range; base "zero": y = 0.
* d = y − base. Area = ∫ d dν̃ (trapezoidal rule, not clipped, can be negative). Height = max d.
  Position = ν̃ at max d (no interpolation). Centroid = ∫ d·ν̃ dν̃ / ∫ d dν̃.
* Ratio = numerator / denominator, either both areas or both heights; no value if the denominator is 0 or missing.

Units: absorbance·cm⁻¹ for absorbance and transmittance spectra, log(1/R)·cm⁻¹ for reflectance; the report adds
"Areas and heights in absorbance (converted from transmittance [%])" under the table, and the export columns get
the suffix `_A` or `_LR` (`banden.csv`, `flaechen.csv`). The equation functions `area`, `height`, `area0` use the
same routine.

Reference: no external reference (Lambert-Beer as textbook background).

Validation: `modules/ftir/tests/test_ftir.py::PeaksGroupsTest::test_integrate_triangle` (triangle 0–10 with apex
5: area 25 to 3 decimals, position 5 to 2 decimals);
`modules/ftir/tests/test_science.py::AreaBasisTest::test_integrate_transmission_on_absorbance` (Gaussian absorbance
band as %T: area 0.8·10·√(2π) = 20.053 to 3 decimals, equal to the absorbance integration to 9 decimals, height
0.8, basis "A"); `…::test_reflectance_basis` (basis "LR"). `…::ServerTest::test_flow` checks that a C=O area is positive.
`…::BundleTest::test_single_and_comparison` checks that area and ratio values reach the report.
`modules/ftir/tests/test_golden.py::GoldenBundle::test_bundle_en` locks the example values (C=O 1780–1650 cm⁻¹:
area 8.733, height 0.373, position 1714; ring 745–700 cm⁻¹: area 6.113). No test checks a ratio against a known
value.

## 7. Band assignments

Code: `ftir/groups.py::assign`; table in `sdk/python/labcalc/irbands.py` (85 entries: range, typical intensity,
shape, name, group).

A band at ν̃ matches every table entry whose range, widened by `ASSIGN_TOL` = 4 cm⁻¹ on both sides, contains ν̃.
Matches are sorted by:

1. **Shape:** a band with FWHM < `BROAD_MIN` = 30 cm⁻¹ does not fit a table band marked broad ("br": O–H,
   carbonate, sulfate …); such entries go last.
2. **Context:** entries whose group (`Gruppe` column) belongs to a compound class that the functional-group
   assessment of the whole spectrum (section 8) rates "likely" come first, then "possible", then all others
   (`groups.py::context_of`, `class_groups`: the groups of all required and supporting table bands of the class).
3. Inside the unwidened range before inside the widened one.
4. Narrower table range first.
5. Smallest difference between band intensity and tabulated intensity.

Intensity comes last because the band intensity is relative to the strongest band of the spectrum and says little
about the group. Up to 1.4 the order was (3), (5), (4) without shape and context, which put sharp PET bands on
broad O–H, sulfate and phosphate entries. The band list shows the first 3, a click shows up to 6 (using the band
width and the context of the last analysis), and the report table shows the first one only. Assignments remain
suggestions from a table: where the table has no entry for a band (PET: aromatic C–H out-of-plane at ≈ 724 and
≈ 873 cm⁻¹, CH₂ wagging ≈ 1340 cm⁻¹, ring mode ≈ 1410 cm⁻¹, O–CH₂ ≈ 972 cm⁻¹, as commonly assigned for PET; not
checked against a source here), the first suggestion is still wrong
(golden PET example: 1410 → NH₄⁺, 1342 → S=O, 972 → trans-alkene, 873 → carbonate, 724 → CH₂ rocking).

Thresholds 4 and 30 cm⁻¹ and the ranking: no external reference. Reference for the table (cited in the report
whenever bands or groups are reported): Socrates, George, Infrared and Raman Characteristic Group Frequencies:
Tables and Charts, 3rd edition, Wiley, Chichester, 2001 (`socrates2001`); Silverstein, Robert M., Webster,
Francis X., Kiemle, David J. and Bryce, David L., Spectrometric Identification of Organic Compounds, 8th edition,
Wiley, 2014 (`silverstein2014`). No individual table entry is linked to a page or table of these books.

Validation:

| Test | Checks |
|---|---|
| `modules/ftir/tests/test_ftir.py::PeaksGroupsTest::test_assignments` | a strong band at 1735 cm⁻¹ gets a C=O/ester assignment; 2918 cm⁻¹ gets at least one |
| `modules/ftir/tests/test_science.py::AssignTest::test_pet_bands_assigned_to_ester_and_ring` | model PET: ester class gives context rank 0; first assignment of 1715, 1242, 1095 cm⁻¹ contains "Ester", of 1579 cm⁻¹ "aromat" (textbook PET assignment) |
| `…::AssignTest::test_sharp_band_not_assigned_to_broad_group` | 1095 cm⁻¹: without width sulfate first, with FWHM 20 cm⁻¹ not sulfate |
| `modules/ftir/tests/test_golden.py::GoldenBundle` | first assignments of the 14 PET bands |

No test checks the table values against the cited books.

## 8. Functional-group assessment

Code: `ftir/groups.py::analyse`. 29 compound classes, each with required, supporting and contradicting bands
(table ids or explicit ranges, each with a minimum intensity level).

**Preparation** (`_probe`): convert to absorbance; noisy regions from section 3; subtract a rubber band fitted to a
≈10 cm⁻¹ moving mean of the quiet points; divide by the maximum of the quiet points (strongest band = 1). Bands
are picked as in section 5 with prominence 1.5 %, distance 6 cm⁻¹, max 120, snr 6. σ is the noise in units of the
strongest band.

**Band test** for a range and level (s 0.15, m 0.06, w 0.03): the needed height is max(level, 6σ).

* Fewer than 3 points in range → "outside"; more than half of the range noisy → "noisy"; both count as not
  checkable.
* Narrow band: the highest picked band in range with prominence ≥ needed height → present ("ok"); a lower band →
  "weak"; no band → "missing".
* Broad band (table shape "br", e.g. O–H, N–H): 25th percentile of the normalised absorbance in the range ≥ needed
  height → present; or a picked band with prominence ≥ needed height and FWHM ≥ 40 cm⁻¹; else "weak".

**Verdict** for a class with n_req checkable required bands, of which n_ok present, n_sup supporting present and
n_con contradicting present:

* likely: all required present and no contradiction;
* possible: the first (key) required band present, at most one required band not present, n_req = 1 or n_ok ≥ 2,
  and n_con ≤ (0 if a band is missing, else 1);
* otherwise unlikely;
* "likely" is lowered to "possible" if a required band could not be checked (outside the range or noisy).
* Score (for ordering) = n_ok/n_req + 0.15·n_sup − 0.35·n_con (− 0.1 when lowered). Classes without a checkable
  required band are omitted.

**Absence statements** (4 key regions: 1850–1650, 3600–3150, 3000–2840, 2270–2100 cm⁻¹): made only if
3σ/√k < 0.025 (k = points in a ≈8 cm⁻¹ moving mean), more than 5 points lie in the region, less than 30 % of it is
noisy, and the 98th percentile of the smoothed normalised absorbance is < 0.025 (2.5 % of the strongest band).
Otherwise the result says that the noise is too high for such statements.

Reference: table as in section 7; the class rules and thresholds have no external reference.

Validation:

| Test | Checks |
|---|---|
| `modules/ftir/tests/test_ftir.py::PeaksGroupsTest::test_groups_pet_and_mixture` | synthetic PET: aromatic and ester "likely"; acid, amide, nitrile, silicate, alcohol "unlikely"; no "no aliphatic C–H" statement; an "no O–H" statement; synthetic PE + calcite: alkyl and carbonate "likely" |
| `…::QualityTest::test_diamond_window_detected_and_ignored` | noisy diamond window does not produce nitrile/isocyanate/alkyne |
| `…::QualityTest::test_clean_and_weak_spectra` | weak spectrum: no absence statements, a noise note, ≤ 2 "likely" classes |
| `…::ServerTest::test_share_peaks` | shared peak table of the PET example contains a band at 1700–1730 cm⁻¹ and ester "likely" or "possible" |
| `modules/ftir/tests/test_golden.py::GoldenBundle::test_bundle_en` | regression of the group table of the PET example (aromatic ring and ester likely; ketone and ether possible) |

All inputs are synthetic. No test uses measured spectra with known composition.

## 9. Bundled and own libraries

All libraries hold, per entry, a search vector on the grid 400–4000 cm⁻¹ in 2 cm⁻¹ steps (1801 points) prepared as
in section 10.1.

### 9.1 Measured references: Open Specy

| Property | Value |
|---|---|
| Origin | Open Specy reference library, file `nobaseline.rds` of the OSF project doi:10.17605/OSF.IO/X7DPZ; built with `modules/ftir/tools/build_openspecy.py` (library record dated 2026-11-16) |
| Citation in the code | "Open Specy reference library: Cowger W. et al. (2021), Microplastic spectral classification needs an open source community: Open Specy to the rescue!, Anal. Chem. 93, 7543–7548, doi:10.1021/acs.analchem.1c00123; Cowger W. et al. (2025), Open Specy 1.0, Anal. Chem., doi:10.1021/acs.analchem.5c00962 (Angaben nicht geprüft); Daten: OSF doi:10.17605/OSF.IO/X7DPZ" (`build_openspecy.py` `OPEN_SPECY`, also in the shipped `meta.json`). Report entries: `cowger2021` (Cowger, Win and others, Analytical Chemistry 93, 7543–7548, 2021, doi 10.1021/acs.analchem.1c00123) and `openspecy2025` (Cowger, Win and others, Open Specy 1.0: Automated (Hyper)spectroscopy for Microplastics, Analytical Chemistry, 2025, doi 10.1021/acs.analchem.5c00962, with the note "details not verified": author list, volume and pages of the 2025 article were not checked) |
| Count | 1682 spectra of 1223 substances in the full build. **Public repository: 196 spectra of 104 substances** (Microplastix 41, Davidson 2023 29, Primpke 2018 126; plastic 149, fibre 15, natural material 13, elastomer 11, paint/coating 6, mineral/filler 2). The other 1486 are built locally by `tools/fetch_optional_data.py openspecy` into a second library `openspecy-restricted` (see THIRD_PARTY_NOTICES.md) |
| Categories (full build) | mineral/filler 732, drug 411, plastic 275, chemical 114, natural material 71, fibre 35, elastomer 34, paint/coating 6, pigment 4 |
| Original sources (entries) | RRUFF 564, SWGDRUG 413, Kimmel Center 240, Primpke 2018 126, PSLC 89, FLOPP 52, AWI 2024 44, Microplastix 41, Davidson 2023 29, Thermo Fisher 18, NREL 11, Archäometrielabor 9, HPU polymer kit 7, Chabuka 2020 5, individual contributors via Open Specy 34 |
| Measurement mode recorded | ATR 205, transmission 169, not recorded 1308 |
| Licence recorded | "CC BY-NC" for 25 entries (all from one contributor set); no licence recorded for the other 1657. The code does not record a licence for the collection as a whole |
| Storage | search vectors only, as float16 (about 3 significant digits); the original spectra are not stored |

Each entry keeps its original source as a citation string (`source`), which the report cites next to Open Specy.

**Selection by the build script:** FTIR spectra only (no Raman, NIR); sources NIST, NIST Chemistry WebBook, USDA and
Moore Institute excluded, as are sources not on the script's list; reflectance spectra excluded; AWI transmission
spectra excluded (the script notes thick particles, often saturated); spectra with fewer than 500 finite points on
the search grid (less than 1000 cm⁻¹) or S/N < 8 (section 3) excluded. Names are unified and categories assigned
by rules. Per substance with at least 4 spectra, spectra with correlation < 0.5 to the most typical spectrum (the
one with the highest mean correlation) are removed. Then up to 10 spectra are kept, starting with the most typical
and adding the least similar; spectra with r ≥ 0.985 to one already kept are dropped as duplicates.

**Intensity unit.** Since 1.5 the build script looks for an intensity-unit column in the Open Specy metadata
(`unit_column`: a column name containing "unit" and "intens" or starting with "y") and honours it per spectrum
(`stored_unit`: "absorb…" → A, "transmi…" → T, "reflect…" → R; T/R given as a fraction are scaled to %); the S/N
selection and `prep` then use that unit. Without such a column, or for an unreadable value, the spectrum is treated
as absorbance, and the library record says so (`yunit_note`, per entry `yunit_src`, counts in `yunit_counts`). The
measurement mode (ATR/transmission) is not taken as the unit, because a transmission measurement can be stored as
absorbance. **The shipped `ftir/data/openspecy` was built before this change** (with all intensities as
absorbance) and could not be rebuilt here (the source file `nobaseline.rds` is not in the repository, and nothing
may be downloaded); whether `nobaseline.rds` has a unit column at all: not checked. Only its citation strings were
updated to the corrected text. Opening an Open Specy entry as a spectrum gives the search vector
(baseline-subtracted, maximum 1, 2 cm⁻¹ grid), not the original data.

### 9.2 Model library: modelled, not measured

| Property | Value |
|---|---|
| Content | 58 materials: plastic 20, filler/mineral 10, solvent 10, natural material 7, paint/coating 6, elastomer 3, additive 2 (`ftir/refdata.py`) |
| How made | each material is a list of bands (position, relative height, FWHM); spectrum = Σ hⱼ·[0.5/(1 + t²) + 0.5·exp(−ln2·t²)] with t = (ν̃ − cⱼ)/(wⱼ/2), i.e. pseudo-Voigt bands (half Lorentzian, half Gaussian), divided by its maximum |
| Source in the code | "Modell aus Literatur-Bandenlagen"; docstring: positions and intensities of the main bands "folgen den üblichen Tabellenwerken und Polymer-Atlanten; Bandenformen, Nebenbanden und Intensitätsverhältnisse sind vereinfacht". The report entry `folio-ftir-modell` says "position, relative intensity and width of the main bands from standard tables (e.g. Socrates 2001)". No source is given for any individual material or band |

**What this means for identification.** These spectra are **modelled from literature band positions, not
measured**. Band shapes, weak bands, intensity ratios, baseline features, sample-preparation and instrument effects
are absent or simplified. A high HQI against a model entry means that the main bands of the sample lie where the
model puts them. It does not identify the material, and it cannot exclude materials missing from the 58 entries.
Use model hits only to narrow down candidates, then confirm against measured references (Open Specy or your own).
The interface, the export (`protokoll.txt`) and the report methods text state that model hits are indications,
and the report cites the model library as its own entry with the note "Not measured spectra".

### 9.3 Own libraries and own references

Own libraries are stored in `outputs/ftir/bibliotheken/<id>/` (`meta.json` with entries, `data.npz` with search
vectors and the original x, y as float32). Adding an entry stores the processed spectrum as it is at that moment
(derivatives are refused) and its search vector (section 10.1). Entry metadata: name, category, CAS number, formula,
source (free text or structured), comment. A structured source (`labcite`) must contain a title, DOI or URL; a DOI
must look like `10.xxxx/…`; an article needs a journal or DOI. "Referenz aus Datei einblenden" stores files in the
library "Eigene Referenzen" and requires a source in the dialog. Export: multi-block JCAMP-DX 5.01 with name, CAS,
formula, source, category and comment.

Validation:

| Test | Checks |
|---|---|
| `modules/ftir/tests/test_ftir.py::BundledLibraryTest::test_loaded_readonly_and_attributed` | Open Specy loads read-only, > 1000 entries with the optional part (> 150 and plastics only in the public repository), 1801 grid points, five main categories, every entry has source, substance and name, CC BY-NC entries present, cannot be changed or deleted |
| `…::BundledLibraryTest::test_rds_reader` | the RDS reader on a generated file |
| `…::SearchTest::test_user_library_persist_search_export` | own library: model library refuses additions; entries survive reload; own PET ranks first; JCAMP export/import round trip; update, remove, delete |
| `…::ServerTest::test_reference_from_file_with_source_and_equations` | incomplete source refused and nothing stored; complete source stored with DOI and carried with the opened spectrum, the hit and the report bibliography |

Not tested: the build script's selection steps (only its RDS reader is tested) and the accuracy of any model band
position.

## 10. Library search

Code: `ftir/library.py::prep`, `ftir/search.py`, `ftir/server.py::query_of`.

### 10.1 Search vector

Sample and references are prepared the same way (`prep`):

1. Convert T and R to absorbance (section 2); KM, LR and `au` are used as they are.
2. If the point spacing is < 2 cm⁻¹: moving mean over round(2 cm⁻¹/step) points (made odd).
3. Linear interpolation onto the grid 400–4000 cm⁻¹, 2 cm⁻¹; empty (NaN) outside the measured range.
4. Blank ranges (for the sample: noisy regions from section 3, on by default) are set empty.
5. Subtract a rubber band (lower convex hull) fitted to the non-empty points. This happens even if the user already
   corrected the baseline.
6. Divide by the maximum. At least 20 non-empty grid points are required.

The user's protocol (section 4) is applied to the sample before this preparation, never to the references, which
went through steps 1–6 only (Open Specy: from `nobaseline.rds` as supplied; own libraries: the processed spectrum
at the time of adding). The rubber band of step 5 is therefore the one baseline treatment common to both sides;
the report's methods text says so.

The sample vector comes from the processed spectrum; for a derivative or an `au` spectrum the unprocessed original
is used instead.

### 10.2 Hit quality index (HQI) per algorithm

All scores are computed over the common points: grid points where the sample and the reference both have values
and that lie inside the search ranges and outside the excluded ranges (default excluded: 2400–2280 cm⁻¹, CO₂).
Let q and l be the sample and reference values over the n common points.

| Algorithm | Formula | Range |
|---|---|---|
| `corr` correlation | r = Σ(q − q̄)(l − l̄) / √(Σ(q − q̄)² · Σ(l − l̄)²); HQI = 100 · max(0, r)² | 0–100 |
| `euclid` Euclidean distance | cos = Σ q·l / √(Σ q² · Σ l²); HQI = 100 · max(0, cos). For unit-length vectors this equals 100 · (1 − d²/2), d the Euclidean distance | 0–100 |
| `dcorr` 1st derivative, correlation | as `corr`, on the derivative vectors | 0–100 |
| `deuclid` 1st derivative, Euclidean | as `euclid`, on the derivative vectors | 0–100 |
| `peaks` peak search | see below | 0–100 |

Derivative vectors (`library.py::deriv`): Savitzky-Golay first derivative, 9 points, order 2, spacing 2 cm⁻¹, on
the non-empty span; interior gaps are bridged linearly for the filter and then emptied again together with 4
points on either side; divided by max |derivative|.

**Coverage penalty** (all except `peaks`): coverage c = n / n_q, where n_q is the number of sample points inside
the selected ranges. HQI is multiplied by min(1, c/0.9). HQI = 0 if n < 10.

**Peak search:** sample and reference bands are picked on their search vectors with the same parameters
(`search.PEAK_PARAMS`: section 5 with prominence 1.5 %, distance 6 cm⁻¹, max 40 and S/N ≥ 10). Up to 1.4 the
reference bands were picked without the S/N criterion, so noisy references contributed noise peaks the sample
could never match. Reference bands outside the sample range or in excluded ranges are ignored. Two bands match if
|Δν̃| ≤ 6 cm⁻¹ + 0.004·ν̃ (`PEAK_TOL`, `PEAK_TOL_REL`; 8 cm⁻¹ at 500, 10 at 1000, 18 at 3000 cm⁻¹). The tolerance
grows with wavenumber because bands above 2800 cm⁻¹ (O–H, N–H, C–H) are broader and shift more with hydrogen
bonding and sample state; the values are a module choice (no external reference). With a = Σ rel of matched
sample bands / Σ rel of all sample bands and b = the same for the reference: HQI = 100 · √(a·b). No coverage
penalty.

**Hit list:** sorted by HQI; optional category filter; up to 25 hits by default (the interface asks for 30).
"Merge identical substances" (default on) keeps the best hit per substance (Open Specy `group`, otherwise per
entry) and counts the rest as "+n". For the first 10 hits, the reference is overlaid after scaling by the
least-squares factor a = Σ q·l / Σ l².

Reference: no external reference for any HQI formula or the coverage penalty. The report names the algorithm
and the library and states that HQI ranges from 0 to 100.

Validation:

| Test | Checks |
|---|---|
| `modules/ftir/tests/test_ftir.py::SearchTest::test_identical_reference_scores_100` | identical PS model spectrum: `corr` HQI = 100 ± 0.05 |
| `…::SearchTest::test_every_algorithm_finds_pet` | synthetic PET (shifted 1 cm⁻¹, widened 10 %, baseline, noise σ = 0.003) against the model library: each of the 5 algorithms ranks PET first with HQI > 85 and a lead > 20 over the second hit |
| `…::SearchTest::test_coating_resins_distinct` | styrene-acrylic, polyester-melamine, epoxy-phenolic: correct first hit with a lead > 3 |
| `…::BundledLibraryTest::test_measured_references_found_and_collapsed` | 7 Open Specy spectra (PP, PET, PA 6, calcite, quartz, cotton, caffeine) + noise σ = 0.004 + offset 0.03: right substance first (PET may match polyester fibre), HQI > 95; merged list has one hit per substance; first HQI identical with and without merging (2 decimals); model spectra of PS, PP, PA 6 and kaolinite find their measured counterpart in the top 3. **Needs the optional Open Specy part** (skipped without it) |
| `…::QualityTest::test_diamond_window_detected_and_ignored` | blanked noisy region; `dcorr` ranks PS first |
| `…::ServerTest::test_flow` | search through the server returns PET first and a query of 1801 points |
| `modules/ftir/tests/test_golden.py::GoldenBundle::test_bundle_en` | regression: the PET example against the model library gives PET first with HQI 94.1 |
| `modules/ftir/tests/test_science.py::SearchMixTest::test_peak_tolerance` | tolerance 10 cm⁻¹ at 1000 and 18 cm⁻¹ at 3000 cm⁻¹ |
| `…::SearchMixTest::test_same_peak_criteria_for_sample_and_library` | a noisy PET spectrum as sample and as the only reference of an own library: identical band lists (within 0.05 cm⁻¹, float32 storage) and peak-search HQI 100 |

The sample spectra in these tests are taken from the same libraries that are searched (with added shift, noise or
offset). No test searches a measured spectrum of known identity that is not itself in the library.

## 11. Mixture analysis

Code: `ftir/search.py::mixture`.

1. Candidates: the best references by `corr` HQI with coverage ≥ 0.9, one per substance, up to 24; plus up to 8
   further references (one per substance, not yet chosen) that best match the residual
   r = max(0, q − a·l_best), where a is the least-squares scale of the best single hit.
2. Common points: inside the search ranges and where the sample and all candidates have values (≥ 20 points).
3. For every subset S of k candidates (k = 1 … K, K = 2, 3 or 4, default 3; for K = 4 only the first 16
   candidates): fit q ≈ Σ wⱼ lⱼ + c with wⱼ ≥ 0 and a free intercept c. The fit centres q and lⱼ and solves the
   non-negative least-squares problem exactly by trying every support subset (unconstrained least squares on the
   subset, kept only if all weights > 0, best reduction of the residual sum of squares). Only fits in which all k
   weights are positive are kept.
4. HQI = 100 · R², R² = 1 − SS_res / SS_tot of the centred fit.
5. Ranking score = HQI − 2·(k − 1); duplicate subsets removed; top 8 returned.
6. Fraction of component j = wⱼ · Σ max(lⱼ, 0) / Σₖ wₖ · Σ max(lₖ, 0), sums over the common points. This is the
   component's **area share** (spectral contribution) of the fitted, normalised absorbance spectrum
   (`frac_kind` "area"). It is **not** a mass or volume fraction; converting it would need a calibration with
   known mixtures. The interface ("Flächenanteil", "% Fläche"), the figure legend ("% area"), the report table
   header ("Area share [%]"), caption, methods and results text, and the export (`mischung.csv` column
   `Flaechenanteil_Prozent (spektraler Beitrag, kein Massenanteil)`) say so.

The fitted curve, components and residual are returned on the search grid and stored with the result.

Reference (cited in the report for the problem only): "Lawson, Charles L. and Hanson, Richard J., Solving Least
Squares Problems, Prentice-Hall, Englewood Cliffs, 1974" (`lawson1974`) for the non-negative least-squares problem.
The code does not use the Lawson–Hanson active-set algorithm; it solves the problem exactly by exhaustive
enumeration of supports (`_nnls_small`), which gives the same constrained optimum for these small k. The methods
text states this.

Validation:

| Test | Checks |
|---|---|
| `modules/ftir/tests/test_ftir.py::SearchTest::test_mixture_pe_calcite` | 0.7·PE + 0.5·calcite (model) + offset + noise: best combination is PE + calcite, k = 2 (no third component), HQI > 97, fractions sum to 1 (6 decimals) |
| `…::BundledLibraryTest::test_mixture_candidates_distinct` | 0.6·PP + 0.5·calcite (Open Specy) + noise: best combination contains both, HQI > 97; no combination uses two spectra of the same substance. **Needs the optional Open Specy part** |

| `modules/ftir/tests/test_science.py::SearchMixTest::test_mixture_fractions_are_area_shares` | PE + calcite: every component has `frac_kind` "area" and its fraction equals the independently recomputed area share (5 decimals) |
| `…::SearchMixTest::test_nnls_small_matches_scipy` | 20 random 60 × 4 problems: enumerated NNLS weights equal `scipy.optimize.nnls` within 1e-8; skipped without SciPy |

No test checks the fractions against known mass fractions (they are not meant to be mass fractions).

## 12. Difference, mean and sum spectra

Code: `ftir/server.py::derive`.

* Each selected spectrum is processed with its own protocol; T and R are converted to absorbance.
* Common range: from the highest first point to the lowest last point; all spectra are linearly interpolated onto
  the points of the first spectrum in that range (≥ 10 points required).
* Difference A − f·B (only the first two spectra are used): f is given, or by default
  f = Σ(a − ā)(b − b̄) / Σ(b − b̄)² over the common range or over a range chosen with tool R (least squares with a
  free offset). The offset itself is not subtracted from the result.
* Mean: arithmetic mean point by point. Sum: point-by-point sum.
* The result keeps the y unit if all inputs share it, else `au`. It inherits the provenance of any library
  references among the inputs (`##$FOLIO REF`) and is stored as JCAMP-DX (y to 6 significant digits).

Reference: no external reference.

Validation: `modules/ftir/tests/test_ftir.py::ServerTest::test_flow` checks that a difference spectrum is created
and keeps the provenance of the reference. The factor value, the mean and the sum: no test.

## 13. Own equations

Code: `ftir/analysis.py`, `sdk/python/labcalc/formulas.py`, expression parser `labcalc.expr` (restricted syntax tree,
no `eval`).

* Variables: band areas `B1…`, heights `H1…`, positions `P1…` (cm⁻¹), ratios `R1…` (numbered in the order defined),
  `npeaks`, and `hqi1` (HQI of the best stored hit); values shared from other environments (name clash → `_ext`
  suffix).
* Functions, all on the processed spectrum: `A(ν)` absorbance at ν by linear interpolation (T/R converted with
  section 2); `y(ν)` value in the spectrum's own unit; `area(ν1, ν2)` and `height(ν1, ν2)` as section 6 with a
  straight-line base; `area0(ν1, ν2)` with base zero. A wavenumber outside the spectrum, or a range with fewer than
  3 points, gives an error for that equation.
* Equations are evaluated in order; later ones may use earlier ones. Name: a letter followed by letters, digits or
  `_`, up to 24 characters; reserved names are refused. Digits 1–10 (default 4) only affect display. At most 60
  equations. Errors stay with their row.
* A source, if given, is checked as in section 9.3 and cited in the report.

Reference: no external reference (the user may attach one per equation).

Validation: `modules/ftir/tests/test_ftir.py::ServerTest::test_reference_from_file_with_source_and_equations`:
`CI = area(1650, 1850)/area(1420, 1500)` equals `B1/B2` to 6 decimals; `A(1715)` > 0; `A(5000)` gives an
"outside the spectrum" error and no report value; the name `area` is refused; the equation, its value and its DOI
reach the report.

### 13.1 Measurement uncertainty

Opt-in: computed only when the working state carries entries (`state["unc"]` with `nu` and/or `noise`,
`state["unc_noise"]` with the noise mode, `state["unc_method"]`). Propagation through the shared
`labcalc.uncertainty` (GUM, JCGM 100:2008; GUM Supplement 1, JCGM 101:2008).

**Noise σᵢ per data point**, on the curve the areas are computed on (absorbance, or log(1/R); T and R converted as
in section 6):

- *auto*: `quality.effective_noise` (section 3; residual of a 7-point cubic Savitzky–Golay smooth, robust standard
  deviation, local value where noise dominates), type A;
- *region*: root mean square of the residuals after a straight-line fit in a user-chosen band-free region,
  s = √(Σr²/(n−2)), n − 2 degrees of freedom; at least 5 points;
- *manual*: the stated standard uncertainty per point.

**Linear forms.** Every noise-dependent result is written as Q = Σ cᵢ yᵢ. Band area over a line between the limits
(trapezoid weights wᵢ, tᵢ the relative position): cᵢ = wᵢ, then c₀ −= Σ wᵢ(1 − tᵢ) and cₙ −= Σ wᵢ tᵢ (exact, the
endpoint noise included); over zero: cᵢ = wᵢ. Height: the unit vector at the maximum minus the baseline interpolation
weights. A(ν): the two linear interpolation weights; y(ν) the same, scaled by dy/dA. Peak position (parabola through
three points, section 5): the derivative of the vertex with respect to the three ordinates, converted to the area
basis. Then u²(Q) = Σ cᵢ²σᵢ² and cov(Q, Q') = Σ cᵢ c'ᵢ σᵢ².

**Further inputs:** wavenumber accuracy δν̃ (shared by all positions, sensitivity −1; for A(ν) and y(ν) the local
slope); interpolation between data points for every position (resolution part, d = point spacing, rectangular);
choice of the limits for areas and heights (half the spread when either limit moves by ±1 point, rectangular).
Template *Ph. Eur. 2.2.24*: ±1.0 cm⁻¹ (polystyrene band at 1601.2 cm⁻¹), rectangular — details not verified
against the original; ASTM E1421 (FT-MIR performance tests) is listed as a module source record with the same note.

**Ratios** are evaluated in one model, R = (N + εN + βN)/(D + εD + βD), with the noise inputs εN, εD correlated by
r = cov/(uN uD). **Own equations:** variables B/H/P/R and every call of A, y, area, area0, height become inputs
(identical calls share one), with all noise correlations between them; the call arguments are treated as exact and,
in Monte Carlo, a call returns its value plus the sampled deviation. The Gaussian method ignores correlations
(as in `labcalc.uncertainty`).

**Report:** `\labval{<id>-pm}`, `-u`, `-U` for `peak<n>`, `band<i>-area|height|pos`, `ratio<i>`, budget tables, a
summary table `unsicherheit…`, and a methods sentence.

**Validation:** `modules/ftir/tests/test_uncert.py` – linear forms reproduce `peaks.integrate` (also for T),
noise u against Σw²σ² for an area over zero and linear in σ, ratio u equal to the linearised value with correlation and
smaller than without, disjoint bands uncorrelated, position u = √(a²/3 + d²/12), equations through `area()` equal to
`B1/B2`, A(ν) at a grid point, report values.

## 14. Spectra from datasets

Code: `ftir/dataset.py`, `ftir/server.py::ds_spectra`. Reads a table (`data.table`) shared by the Data Purification
module (Datenaufbereitung).

* x column: numbers with a unit. A wavenumber unit (dimension of 1/cm, e.g. 1/cm, 1/m) is converted to cm⁻¹. A
  length unit (µm, nm, …) is converted with ν̃ = 1/λ (values must be positive). Any other unit, or no unit, is
  refused.
* y columns: numbers with a dimensionless unit (empty, 1, %, ‰ …); other units are refused. y kind: the choice in
  the dialog; else from the column name (refl/remission/%R → R; trans/%T → T; kubelka/KM → KM; abs/extinkt → A);
  else from the unit (a dimensionless unit other than "1", e.g. % → T; "1" or empty → A). A, KM and LR must have
  scale factor 1 (a % column cannot be absorbance). T and R are converted to %; without a unit, values ≤ 1.5 are
  multiplied by 100.
* Rows marked as excluded in the dataset and non-finite rows are left out; ≥ 10 points; x within 0–50 000 cm⁻¹.
* Each spectrum is stored as JCAMP-DX with `##$FOLIO DATASET` (dataset ID, title, version, live/pinned, source
  module, columns, y kind, number of excluded rows, conversion note) and read back through the normal reader
  (section 1), including resampling if the spacing became uneven.
* The report methods text names dataset title, ID, version and column, the 1/λ conversion if used, and the number
  of excluded rows.

Reference: no external reference.

Validation:

| Test | Checks |
|---|---|
| `modules/ftir/tests/test_dataset.py::DatasetSpectra::test_two_columns_two_spectra` | two y columns → two spectra named after the columns, unit A, x ascending, y equal to the dataset within rtol 1e-5; provenance survives a reload |
| `…::DatasetSpectra::test_transmittance_and_wavelength` | µm column → 400–4000 cm⁻¹ (3 decimals); % and fraction columns → T; value at 1000 cm⁻¹ equal to 3 decimals; dialog choice R overrides |
| `…::DatasetSpectra::test_unit_mismatch_refused` | 7 wrong inputs refused with the right message (mass unit as x, x without unit, mg as y, % as absorbance, text column, no y column, x = y); nothing created |
| `…::DatasetSpectra::test_excluded_refresh_and_report` | excluded outlier row absent and spectrum resampled; methods text names ID, version 1, column and "1 … excluded row"; update to version 2 gives 2 × the original values (rtol 1e-5); pinned spectrum stays at version 1 |

## 15. What the report cites

`ftir/bundle.py` adds these references automatically:

| Key | When | Reference exactly as stored in the code |
|---|---|---|
| `data-<slug>` | always | the source file name, format, range, number of points and size |
| `socrates2001` | bands or groups reported (band assignment table) | Socrates, George. Infrared and Raman Characteristic Group Frequencies: Tables and Charts. Edition 3. Wiley, Chichester, 2001 |
| `silverstein2014` | bands or groups reported | Silverstein, Robert M., Webster, Francis X., Kiemle, David J. and Bryce, David L. Spectrometric Identification of Organic Compounds. Edition 8. Wiley, 2014 |
| `savitzky1964` | Savitzky-Golay smoothing, a derivative, or an S/N value (noise estimate); not for the moving mean | Savitzky, Abraham and Golay, Marcel J. E. Smoothing and Differentiation of Data by Simplified Least Squares Procedures. Analytical Chemistry 36 (8), 1627–1639, 1964 |
| `eilers2005` | ALS baseline | Eilers, Paul H. C. and Boelens, Hans F. M. Baseline Correction with Asymmetric Least Squares Smoothing. Leiden University Medical Centre, 2005 (techreport) |
| `lieber2003` | polynomial baseline | Lieber, Chad A. and Mahadevan-Jansen, Anita. Automated method for subtraction of fluorescence from biological Raman spectra. Applied Spectroscopy 57 (11), 1363–1367, 2003 |
| `harrick1967` | ATR correction | Harrick, N. J. Internal Reflection Spectroscopy. Interscience Publishers, New York, 1967 |
| `lawson1974` | mixture result (NNLS problem) | Lawson, Charles L. and Hanson, Richard J. Solving Least Squares Problems. Prentice-Hall, Englewood Cliffs, 1974 |
| `cowger2021` + `openspecy2025` + `ref-<origin>` | Open Specy hits, components or opened references | Open Specy entries above (2025 with the note "details not verified"), plus the entry's original source string from the build script |
| `folio-ftir-modell` | model-library hits, components or opened references | "FTIR model library (Folio Lab): reference spectra calculated from literature band positions"; note "Not measured spectra …" |
| `lib-…`, `src-…` | own-library hits | the library's and the entry's structured source, or the library name |
| `eq-…` | own equations with a source | the source given by the user |

ASTM E1252 is no longer cited (up to 1.4 it was cited in every methods text although the module implements no
procedure from that standard).

Original-source strings for Open Specy entries are stored in `ftir/data/openspecy/meta.json` (`origins`, per entry
`source`) and come from `modules/ftir/tools/build_openspecy.py` (`ORGS`). Completed in 1.5 where the details are
certain: RRUFF (Lafuente, Downs, Yang, Stone 2015, "The power of databases: the RRUFF project", in Highlights in
Mineralogical Crystallography, De Gruyter, 1–30), FLOPP (De Frond, Rubinovitz, Rochman 2021, Anal. Chem. 93,
15878–15885, doi:10.1021/acs.analchem.1c02549), Primpke 2018 (Primpke, Wirth, Lorenz, Gerdts, Anal. Bioanal. Chem.
410, 5131–5141, doi:10.1007/s00216-018-1156-x). Entries whose details could not be checked here carry
"(Angaben nicht geprüft / not verified)": AWI 2024 (DOI and year dropped), Kimmel Center, SWGDRUG, PSLC, Chabuka
2020. The Davidson 2023, Microplastix and individual-contributor strings are unchanged and were not re-checked.

Validation: `modules/ftir/tests/test_ftir.py::BundleTest::test_reference_sources_cited_automatically` (needs the optional Open Specy part; search
figure cites `openspecy2025` and `ref-rruff`; hit table cites the model library when a model hit is among the first
10; every cited key exists in `refs.bib`; an opened Open Specy reference keeps its provenance through JCAMP and is
cited in its own caption); `…::BundleTest::test_single_and_comparison`; the golden tests lock the bibliography of
the PET example.

---

## Known limitations

* **Model library hits are not identifications.** The 58 model spectra are calculated from band lists without a
  cited source per material (section 9.2).
* **Assignments are table suggestions.** Since 1.5 they take band shape and the group assessment into account
  (section 7), which fixes the PET example for 2969, 1715, 1579, 1242, 1095 and 1018 cm⁻¹. Bands for which the
  correlation table has no fitting entry still get a wrong first suggestion (PET: 1410 → NH₄⁺, 1342 → S=O,
  972 → trans-alkene, 873 → carbonate, 724 → CH₂ rocking; `tests/golden/ftir_en.json`). Do not report the first
  assignment without checking it.
* **Group assessment can over-report.** For the PET example, ketone and ether are rated "possible". Broad rules
  (sulfate, phosphate, silicate) over-report for dense C–O regions (README). Because assignments now follow the
  group assessment, an over-rated class can also move its table entries up.
* **CO₂ bridging** uses narrow ranges (2390–2280, 680–655 cm⁻¹) since 1.5; talc (≈ 669 cm⁻¹) still lies inside,
  and whether the narrow ranges hold all CO₂ absorption of every instrument was not checked. The overlap notice is a
  heuristic (section 4.3). The wide ranges of 1.4 remain selectable and cut e.g. polystyrene 698 and calcite
  712 cm⁻¹. Protocols saved with 1.4 contain no `ranges` and now use the narrow ranges.
* **ATR correction** is the simple ν̃/ν̃_ref scaling (constant refractive indices, weak absorption); it does not
  correct the band shifts and distortions near strong bands caused by dispersion.
* **ALS λ scaling** with (1 cm⁻¹/h)⁴ is derived here from the discretisation of the penalty, not taken from Eilers
  & Boelens; it makes the setting independent of the point spacing for smooth baselines (test: 7·10⁻⁶ difference
  between 1 and 2 cm⁻¹ grids). Protocols saved with 1.4 contain no `lam_ref`; they now use "cm1", which gives a
  different baseline only for data not spaced at 1 cm⁻¹ (choose "point" to reproduce 1.4).
* **The search always subtracts its own rubber-band baseline** and normalises to the maximum; HQI values depend on
  this preparation and on the selected ranges, and are not comparable with HQI values from other software.
* **Peak-search HQI tolerance grows with wavenumber** (6 cm⁻¹ + 0.4 %, e.g. ≈ 18 cm⁻¹ at 3000 cm⁻¹); the values are
  a module choice without external reference.
* **Mixture fractions** are area shares of the fitted normalised absorbance spectrum, not mass fractions; no
  calibration is offered.
* **Difference spectra** use only the first two selected spectra; the automatic factor is fitted with a free
  offset that is not removed from the result.
* **Open Specy data** are stored as float16 search vectors without the original spectra; for 1308 of 1682 entries
  the measurement mode is not recorded; licences are recorded only where the source gave one. The shipped build
  treats all entries as absorbance (built before the unit handling of 1.5; not rebuilt here, section 9.1). The
  2025 Open Specy citation and several original-source strings are marked "not verified".
* **Readers:** only generated files are used in the tests; OPUS is not yet checked with real files. Units that a
  file does not state are guessed by fixed rules (x ≤ 50 → µm; y from the values) with a notice and can be chosen
  by the user; a wrong guess that the user does not correct gives wrong results.
* **S/N** is a module-specific definition (strongest band over σ₀). σ₀ estimates the white-noise standard deviation
  within a few percent at 0.5–4 cm⁻¹ spacing but ≈ 8 % low at 8 cm⁻¹; correlated noise (e.g. after smoothing) is
  underestimated, because the 7-point Savitzky-Golay residual removes its low-frequency part. Since σ₀ changed in
  1.5 (≈ 9 % higher than before at 1 cm⁻¹), S/N values and the S/N ≥ 10 band criterion are not comparable with 1.4
  results.
* **Assignments in `sdk/python/labcalc/irbands.py`** (outside this module) lack entries for several PET bands
  (see above); the table cites Silverstein without edition there.
* **Validation is synthetic.** Nearly all tests use spectra generated from the model library or taken from the
  libraries being searched. The golden tests detect changes in results, not errors in them. No test uses an
  independent measured spectrum of known composition.
