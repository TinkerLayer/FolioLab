# FTIR: methods and validation

This document describes every number the FTIR module (`modules/ftir/`) can put into a report: how it is computed,
with which defaults and limits, which reference the code cites, and which automated test checks it. Everything
here was read from the code of module version 1.4.0. Where the code cites no source, this document says
"no external reference". Where no test checks a computation, it says "no test".

User guide: [`modules/ftir/README.md`](../../modules/ftir/README.md).

## How to cite results from this module

Report the Folio Lab version (`version` in `package.json` at the repository root)
and the FTIR module version (`version` in `modules/ftir/module.json`; 1.4.0). Every report bundle that the module
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
  tests with `python -m unittest discover -s tests` in `modules/ftir`. All 48 tests passed for this document.
* Many tests use synthetic spectra built from the model library (`ftir/refdata.py`, section 9.2). Such tests show
  that the code behaves as designed. They are not evidence of accuracy on measured spectra.

---

## 1. File readers

Format detection (`ftir/readers.py::load_bytes`): Bruker OPUS by its magic bytes `0A 0A FE FE` (any extension);
`.spa` → OMNIC; `.spc`/`.fir`, or second byte `0x4B` → SPC; `.jdx`/`.dx`/`.jcamp`/`.jcm` or text starting with
`##` → JCAMP-DX; other binary content is refused; everything else is read as a text table.

| Format | What is read | Metadata taken | y unit |
|---|---|---|---|
| JCAMP-DX (`readers.py::read_jcamp`) | `##XYDATA=(X++(Y..Y))` in AFFN, SQZ, DIF, DUP (mixed); DIF Y-check values at line starts are dropped; `##XYPOINTS`/`(XY..XY)` and peak tables as x,y pairs; several blocks per file (one spectrum each, a new block starts at `##TITLE`); `$$` comments ignored. x for X++ is a linear axis from `FIRSTX` to `LASTX` (or `FIRSTX + DELTAX·(n−1)`); `NPOINTS` truncates; `XFACTOR`/`YFACTOR` applied | `TITLE` (name), `ORIGIN`, `OWNER`, `DATE`/`LONG DATE`, `SPECTROMETER/DATA SYSTEM`, `RESOLUTION`, `CAS NAME`, `CAS REGISTRY NO`, `MOLFORM`, `SAMPLING PROCEDURE`, `STATE`; Folio fields `##$FOLIO REF` (provenance of library references) and `##$FOLIO DATASET` (provenance from a dataset) | from `YUNITS`: ABSORB… → A; TRANSM… → T (×100 if max ≤ 1.5); KUBELKA… → KM; REFLECT… → R (×100 if max ≤ 1.5); LOG(1/R) → LR; otherwise guessed (below) |
| Thermo OMNIC `.spa` (`read_spa`) | Directory at byte 304 (16-byte entries): key 2 = header (n, y type, first/last x as float32), key 3 = float32 data; fallback to fixed offsets for an older layout. x is linear between first and last x | title (bytes 30–285) | type 17 → A, 16 → T, 11 → R, 12 → LR, 20 → KM; T/R ×100 if max ≤ 1.5; unknown → guessed |
| GRAMS/Galactic `.spc` (`read_spc`) | New format only (byte 1 = `0x4B`); float32 or scaled int16/int32 (exponent 2^(e−16) / 2^(e−32)); common x array, linear x, or per-subfile XY; several subfiles = several spectra | comment (bytes 88–217) as name; resolution text (bytes 36–44); log block `key=value`: `SampleID` → sample, `Spectrum` → source file | y type 2 → A, 3 → KM, 128 → T, 129 → R (T/R ×100 if max ≤ 1.5); other → guessed. x type 2 → µm, 3 → nm, all other codes are taken as cm⁻¹ |
| Agilent MicroLab `.fir` | Read as SPC (above) | as SPC, plus format "Agilent MicroLab (.fir, SPC)" and instrument "Agilent MicroLab" when the extension is `.fir` or the log names MicroLab or an `.a2r` file | as SPC |
| Bruker OPUS (`ftir/opus.py`) | Directory of 12-byte entries; data blocks AB (result, type 15), ScSm and ScRf (single-channel sample/reference) are opened, in that order; for each, the parameter block (type + 16) must give `NPT`, `FXV`, `LXV`; y = float32 × `CSF`; x linear from `FXV` to `LXV`; `DXU` = `WN` (cm⁻¹) or `MI` (µm, converted), other x units refused. Interferograms (IgSm, IgRf), phase (PhSm) and unknown blocks are listed in the metadata, not opened. A corrupt parameter entry stops reading | `SNM` (name), `INS` instrument, `RES` resolution, `NSS` scans, `DAT`, `TIM`, `SFM` sample form; format label "nach öffentlicher Formatbeschreibung, noch nicht mit echten OPUS-Dateien geprüft" | AB: from `PLF` (AB → A, TR → T, RF → R, KM → KM), else guessed; single-channel spectra: `au` |
| Text/CSV (`read_table`) | Tries `;`, tab, `,` and whitespace; keeps the delimiter that gives the most consistent rows (score = rows × min(columns, 6)); decimal comma accepted unless the delimiter is a comma (shared parser `labtable`, also `1.234,5`); the row before the data is the header; footer lines after the data stop reading; ≥ 10 rows; each further numeric column = one spectrum | column header as name suffix and unit hint | from the header text (`abs`, `extinkt`, `a`, `(a)` → A; `kubelka`, `KM` → KM; `refl`, `%R`, `remission` → R; `%T`, `trans` → T), else guessed |

**y-unit guess** (`readers.py::guess_yunit`) when nothing is declared: median between 20 and 110 and maximum ≤ 130
→ T in %; 0.5 < median ≤ 1.05, maximum ≤ 1.25, minimum ≥ −0.05 and (max − median) < 0.5·(median − min) → T as a
fraction, multiplied by 100; otherwise A.

**x-unit for text tables:** header containing `µm`, `um`, `micro`, `mikro` → µm; `nm`, `nano` → nm; no unit and
maximum x ≤ 50 → µm; otherwise cm⁻¹.

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

Not tested: the older `.spa` layout, SPC subfiles with own x values, JCAMP `XUNITS` in µm/nm, OPUS `PLF` other than
absorbance. Only generated files are used; no real instrument file is part of the tests.

## 2. Unit and axis conversions

| Conversion | Formula | Where |
|---|---|---|
| µm → cm⁻¹ | ν̃ = 10⁴ / λ[µm] | `readers.py::x_to_cm1`, `opus.py` |
| nm → cm⁻¹ | ν̃ = 10⁷ / λ[nm] | `readers.py::x_to_cm1` |
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
3. σ₀ = 25th percentile of σ_loc (noise of the quiet sections).
4. Noise-dominated where the span (max − min) of a ≈12 cm⁻¹ moving mean within the same window is < 8 · σ_loc.
   Core noisy points: σ_loc > 3.5 σ₀ and noise-dominated. A noisy region is a run of points with σ_loc > 2 σ₀ and
   noise-dominated that contains a core point; runs are merged across gaps < max(60 cm⁻¹, 3 steps) and kept if
   ≥ 40 cm⁻¹ wide. A region overlapping 2250–1950 cm⁻¹ is labelled "typical of diamond ATR".
5. S/N = 99.5th percentile of (smoothed signal − rubber band) outside noisy regions, divided by σ₀. For T and R the
   signal is −y.
6. Warnings: S/N < 15 "hardly any signal"; S/N < 50 "weak signal"; absorbance: 99.9th percentile > 1.5 "may be
   saturated"; T/R: 0.1th percentile < 1 % "may be saturated". For derivatives only σ₀ is computed.
7. Effective noise per point (for band picking): σ₀, or max(σ₀, σ_loc) where the signal is noise-dominated or the
   point lies in a noisy region.

This S/N is a module-specific definition (strongest band over the noise of the quiet sections), not a standard
one. The report text says "about".

Reference: no external reference.

Validation:

| Test | Checks |
|---|---|
| `modules/ftir/tests/test_ftir.py::QualityTest::test_diamond_window_detected_and_ignored` | synthetic weak PS with 10× noise in 2300–1900 cm⁻¹: exactly one noisy region, upper edge 2250–2340, lower edge 1860–1950 cm⁻¹; warning names diamond ATR; no bands picked in 1900–2300; PS bands at 698 and 1493 found (±4 cm⁻¹); nitrile/isocyanate/alkyne not above "unlikely"; aromatic "likely"; search vector empty in 2000–2200; derivative search still ranks PS first |
| `…::QualityTest::test_clean_and_weak_spectra` | clean synthetic PET: no noisy region, S/N > 50, no S/N warning; very weak spectrum: S/N < 15 with warning, no absence statements, ≤ 2 "likely" classes |

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
| `baseline` | any | method rubber band; ALS log₁₀λ 6 (2–10), p 0.01 (0.0005–0.2); polynomial degree 3 (1–8); anchor points: spline (or linear) |
| `co2` bridge CO₂ bands | any | fixed ranges 2400–2250 and 720–630 cm⁻¹ |
| `atr` ATR correction | A | reference wavenumber 1000 cm⁻¹ (100–5000) |
| `normalize` | any | mode maximum; band position 1720 cm⁻¹ for mode "band" |
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
  at most 10 iterations, stops when the weights no longer change. λ = 10^(log₁₀λ). λ acts per data point, so the
  same λ gives a different stiffness at a different point spacing. Reference in the code:
  "Eilers, Paul H. C. and Boelens, Hans F. M., Baseline Correction with Asymmetric Least Squares Smoothing,
  Leiden University Medical Centre, 2005" (techreport, `bundle.py` REFS `eilers2005`; cited in the report when ALS
  is used).
* **Polynomial, iterative** (`poly_baseline`): x scaled to [−1, 1]; fit a polynomial of the chosen degree; replace
  y by min(y, fit); repeat up to 100 times until nothing changes (tolerance 10⁻⁹ · range). Reference in the code:
  "Lieber & Mahadevan-Jansen 2003" (docstring only; not cited in reports).
* **Anchor points by hand** (`points_baseline`): at least two anchor wavenumbers inside the spectrum. Each anchor
  height is the mean of up to 5 points around the nearest data point. Connection: natural cubic spline (≥ 3
  anchors, default) or straight lines. Outside the outermost anchors, the linear option holds the end values;
  the spline option extends the end polynomial. Reference: no external reference.

Validation: `modules/ftir/tests/test_ftir.py::ProcessTest::test_baselines_remove_offset_and_slope`. A synthetic PET
spectrum plus offset 0.2 and slope 0.1 over 600–4000 cm⁻¹: after rubber band, ALS (λ = 10⁶, p = 0.01) and
polynomial (degree 2), |y| < 0.03 in the band-free 1900–2600 cm⁻¹ region and y(1714 cm⁻¹) within 0.05 of the true
value; anchor points (linear, 4 anchors): |y(2200 cm⁻¹)| < 0.01. The preview baseline length is checked in
`…::ServerTest::test_flow`.

### 4.2 Smoothing

* **Savitzky-Golay** (`savgol`, `sg_coeffs`): convolution coefficients from the least-squares fit of a polynomial
  of the given order over the window (pseudo-inverse of the Vandermonde matrix). Ends: point reflection about the
  first and last value (2y₀ − y_k …). If the window is longer than the spectrum, it is shortened.
  Reference in the code: "Savitzky, Abraham and Golay, Marcel J. E., Smoothing and Differentiation of Data by
  Simplified Least Squares Procedures, Analytical Chemistry 36 (8), 1627–1639, 1964" (`savitzky1964`).
* **Moving mean** (`moving_mean`): unweighted mean over the window; ends padded with the end values. Reference: no
  external reference. Note: the report cites Savitzky and Golay for any smoothing step, including the moving mean
  (`bundle.py`, see Known limitations).

Validation: `modules/ftir/tests/test_ftir.py::ProcessTest::test_savgol_preserves_polynomial` (11 points, order 2:
a quadratic is reproduced to 1e-10 away from the ends and to < 1e-3 at the ends; the first derivative equals
6x − 1 to 1e-8 away from the ends). Moving mean: no test.

### 4.3 CO₂ bridging

In each range 2400–2250 cm⁻¹ and 720–630 cm⁻¹, y is replaced by a straight line between the mean of the edge
points (up to 4 points at each end, including the edge point). Reference: no external reference. Validation: the
step runs in `test_ftir.py::ProcessTest::test_pipeline_steps_described_and_cut`; its values are not checked.

### 4.4 ATR correction

y_corr = y · ν̃ / ν̃_ref (ν̃_ref default 1000 cm⁻¹). This scales for a penetration depth proportional to wavelength.
It uses no refractive index, angle of incidence or crystal material. Reference: no external reference. Validation:
no test.

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
| band | y / max(y) within ±5 cm⁻¹ of the given position (for T/R: divided by max(−y), see Known limitations) |

If the divisor is 0 the spectrum is left unchanged. Reference: no external reference. Validation: maximum mode
gives max = 1 within 1e-6 in `test_ftir.py::ProcessTest::test_pipeline_steps_described_and_cut`; other modes: no
test.

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

FWHM and per-band area are only covered by the golden regression; no test compares them with known values.

## 6. Band areas, heights and ratios

Code: `ftir/peaks.py::integrate`, `ftir/analysis.py::run`.

* Points with lo ≤ ν̃ ≤ hi are used (at least 3, else no value). For T and R, −y is integrated.
* Base "linear": straight line through the first and last point of the range; base "zero": y = 0.
* d = y − base. Area = ∫ d dν̃ (trapezoidal rule, not clipped, can be negative). Height = max d.
  Position = ν̃ at max d (no interpolation). Centroid = ∫ d·ν̃ dν̃ / ∫ d dν̃.
* Ratio = numerator / denominator, either both areas or both heights; no value if the denominator is 0 or missing.

Units: absorbance·cm⁻¹ for absorbance spectra. For T and R spectra the area is in %T·cm⁻¹ of the inverted curve,
not an absorbance area (see Known limitations).

Reference: no external reference.

Validation: `modules/ftir/tests/test_ftir.py::PeaksGroupsTest::test_integrate_triangle` (triangle 0–10 with apex
5: area 25 to 3 decimals, position 5 to 2 decimals). `…::ServerTest::test_flow` checks that a C=O area is positive.
`…::BundleTest::test_single_and_comparison` checks that area and ratio values reach the report.
`modules/ftir/tests/test_golden.py::GoldenBundle::test_bundle_en` locks the example values (C=O 1780–1650 cm⁻¹:
area 8.733, height 0.373, position 1714; ring 745–700 cm⁻¹: area 6.113). No test checks a ratio against a known
value.

## 7. Band assignments

Code: `ftir/groups.py::assign`; table in `sdk/python/labcalc/irbands.py` (85 entries: range, typical intensity,
shape, name, group).

A band at ν̃ matches every table entry whose range, widened by 4 cm⁻¹ on both sides, contains ν̃. Matches are sorted
by (1) inside the unwidened range first, (2) smallest difference between band intensity and tabulated intensity,
(3) narrowest range. The band list shows the first 3, a click shows up to 6, and the report table shows the first
one only. The sort uses no chemical context: the first assignment can be chemically wrong for the sample (see Known
limitations).

Reference in the code: table "nach den gängigen Tabellenwerken: G. Socrates, Infrared and Raman Characteristic
Group Frequencies, 3. Aufl., Wiley 2001; R. M. Silverstein, F. X. Webster, D. J. Kiemle, Spectrometric
Identification of Organic Compounds" (`irbands.py` docstring). The report cites "Socrates, George, Infrared and
Raman Characteristic Group Frequencies: Tables and Charts, 3rd edition, Wiley, Chichester, 2001"
(`socrates2001`). No individual table entry is linked to a page or table of these books.

Validation: `modules/ftir/tests/test_ftir.py::PeaksGroupsTest::test_assignments` (a strong band at 1735 cm⁻¹ gets a
C=O/ester assignment; 2918 cm⁻¹ gets at least one). The golden regression locks the first assignments of the PET
example. No test checks the table values against the cited books.

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
| Citation in the code | "Open Specy reference library: Cowger W. et al. (2025), Open Specy 1.0, Anal. Chem., doi:10.1021/acs.analchem.5c00962; Daten: OSF doi:10.17605/OSF.IO/X7DPZ"; report entry `openspecy2025`: "Cowger, Win and others, Open Specy 1.0: Automated (Hyper)spectroscopy for Microplastics, Analytical Chemistry, 2025, doi 10.1021/acs.analchem.5c00962" |
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

All Open Specy intensities are prepared as absorbance (`prep(…, "A")`); the script does not convert by measurement
mode. Opening an Open Specy entry as a spectrum gives the search vector (baseline-subtracted, maximum 1, 2 cm⁻¹
grid), not the original data.

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

**Peak search:** sample bands are picked on the search vector (section 5 with prominence 1.5 %, distance 6 cm⁻¹,
max 40 and the default S/N criterion 10); reference bands the same way but without the S/N criterion. Reference
bands outside the sample range or in excluded ranges are ignored. Two bands match if |Δν̃| ≤ 6 cm⁻¹ + 0.004·ν̃.
With a = Σ rel of matched sample bands / Σ rel of all sample bands and b = the same for the reference:
HQI = 100 · √(a·b). No coverage penalty.

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
   component's share of the fitted, normalised absorbance area. It is **not** a mass or volume fraction.

The fitted curve, components and residual are returned on the search grid and stored with the result.

Reference in the code (cited in the report): "Lawson, Charles L. and Hanson, Richard J., Solving Least Squares
Problems, Prentice-Hall, Englewood Cliffs, 1974" (`lawson1974`). The code does not use the Lawson-Hanson
algorithm; it enumerates subsets, which gives the same constrained optimum for these small k.

Validation:

| Test | Checks |
|---|---|
| `modules/ftir/tests/test_ftir.py::SearchTest::test_mixture_pe_calcite` | 0.7·PE + 0.5·calcite (model) + offset + noise: best combination is PE + calcite, k = 2 (no third component), HQI > 97, fractions sum to 1 (6 decimals) |
| `…::BundledLibraryTest::test_mixture_candidates_distinct` | 0.6·PP + 0.5·calcite (Open Specy) + noise: best combination contains both, HQI > 97; no combination uses two spectra of the same substance. **Needs the optional Open Specy part** |

No test checks the fractions against the known mixing weights.

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
| `socrates2001` | always (band assignment table) | Socrates, George. Infrared and Raman Characteristic Group Frequencies: Tables and Charts. Edition 3. Wiley, Chichester, 2001 |
| `astm-e1252` | always | "ASTM E1252-98(2021): Standard Practice for General Techniques for Obtaining Infrared Spectra for Qualitative Analysis", ASTM International, 2021 |
| `savitzky1964` | any smoothing step or a derivative | Savitzky, Abraham and Golay, Marcel J. E. Smoothing and Differentiation of Data by Simplified Least Squares Procedures. Analytical Chemistry 36 (8), 1627–1639, 1964 |
| `eilers2005` | ALS baseline | Eilers, Paul H. C. and Boelens, Hans F. M. Baseline Correction with Asymmetric Least Squares Smoothing. Leiden University Medical Centre, 2005 (techreport) |
| `lawson1974` | mixture result | Lawson, Charles L. and Hanson, Richard J. Solving Least Squares Problems. Prentice-Hall, Englewood Cliffs, 1974 |
| `openspecy2025` + `ref-<origin>` | Open Specy hits, components or opened references | Open Specy entry above, plus the entry's original source string from the build script |
| `folio-ftir-modell` | model-library hits, components or opened references | "FTIR model library (Folio Lab): reference spectra calculated from literature band positions"; note "Not measured spectra …" |
| `lib-…`, `src-…` | own-library hits | the library's and the entry's structured source, or the library name |
| `eq-…` | own equations with a source | the source given by the user |

Original-source strings for Open Specy entries are stored in `ftir/data/openspecy/meta.json` (`origins`) and
come from `modules/ftir/tools/build_openspecy.py` (`ORGS`).

Validation: `modules/ftir/tests/test_ftir.py::BundleTest::test_reference_sources_cited_automatically` (needs the optional Open Specy part; search
figure cites `openspecy2025` and `ref-rruff`; hit table cites the model library when a model hit is among the first
10; every cited key exists in `refs.bib`; an opened Open Specy reference keeps its provenance through JCAMP and is
cited in its own caption); `…::BundleTest::test_single_and_comparison`; the golden tests lock the bibliography of
the PET example.

---

## Known limitations

* **Model library hits are not identifications.** The 58 model spectra are calculated from band lists without a
  cited source per material (section 9.2).
* **Assignments ignore chemistry.** The first assignment is chosen by table range width and intensity class only.
  In the golden PET example the report table assigns 2969 cm⁻¹ to "O–H carboxylic acid", 1242 cm⁻¹ to "P=O
  phosphate ester", 1095 cm⁻¹ to "SO₄²⁻ sulfate" and 724 cm⁻¹ to "C–Cl" (`tests/golden/ftir_en.json`). Do not
  report the first assignment without checking it.
* **Group assessment can over-report.** For the PET example, ketone and ether are rated "possible". Broad rules
  (sulfate, phosphate, silicate) over-report for dense C–O regions (README).
* **CO₂ bridging removes real bands.** The fixed range 720–630 cm⁻¹ also covers e.g. polystyrene (≈ 698 cm⁻¹),
  calcite (≈ 712 cm⁻¹) and talc (≈ 669 cm⁻¹); 2400–2250 cm⁻¹ covers most of the isocyanate band range in the
  correlation table (2280–2240 cm⁻¹).
* **Areas on T or R spectra** are areas of the inverted %T curve, not absorbance areas, and are not proportional to
  concentration. Convert to absorbance first.
* **Normalisation "band" on T/R spectra** divides by a negative value (max of −y) and produces negative
  transmittance values.
* **ATR correction** is a simple ν̃/ν̃_ref scaling without refractive index or angle; it is not a full ATR
  correction.
* **ALS stiffness depends on point spacing**, so the same log₁₀λ is not comparable between instruments with
  different data spacing.
* **The search always subtracts its own rubber-band baseline** and normalises to the maximum; HQI values depend on
  this preparation and on the selected ranges, and are not comparable with HQI values from other software.
* **Peak-search HQI tolerance grows with wavenumber** (6 cm⁻¹ + 0.4 %, e.g. ≈ 18 cm⁻¹ at 3000 cm⁻¹).
* **Mixture fractions** are shares of the fitted normalised absorbance area, not mass fractions; no test checks
  them against known weights.
* **Difference spectra** use only the first two selected spectra; the automatic factor is fitted with a free
  offset that is not removed from the result.
* **Open Specy data** are stored as float16 search vectors without the original spectra; for 1308 of 1682 entries
  the measurement mode is not recorded; licences are recorded only where the source gave one. All entries are
  treated as absorbance.
* **Readers:** only generated files are used in the tests; OPUS is not yet checked with real files. y units and µm
  axes are guessed when files do not declare them (section 1); SPC x-type codes other than µm and nm are taken as
  cm⁻¹.
* **Report citations:** ASTM E1252 is cited in every methods text, although the module implements no procedure
  from that standard. Savitzky and Golay are cited for any smoothing step, including the moving mean. The
  polynomial baseline's source is named only in a code comment and is not cited in reports.
* **S/N** is a module-specific definition (99.5th percentile of the baseline-corrected signal over the noise of the
  quiet sections).
* **Validation is synthetic.** Nearly all tests use spectra generated from the model library or taken from the
  libraries being searched. The golden tests detect changes in results, not errors in them. No test uses an
  independent measured spectrum of known composition.
