# Changelog

All notable changes to Folio Lab are listed here. The suite version (this file, `package.json`, `CITATION.cff`)
follows [Semantic Versioning](https://semver.org/). Each analysis module also has its own version in
`modules/<id>/module.json`. A module's version changes whenever its results or its report output can change, so
**quote both the suite version and the module version** when you report a result.

Versions below 1.0.0 mean that the methods are tested by the project's own test suites (see `docs/VALIDATION.md`)
but have not yet been validated independently.

## [0.2.0] – 2026-11-18

Scientific corrections after a review of every methods page against the code and the cited sources. **Several
results change.** Results made with 0.1.0 stay reproducible with 0.1.0; the module versions in a report's provenance
tell which version produced a number.

| Component | Version |
|---|---|
| Report editor and hub | 0.2.0 |
| Zugversuch (tensile test) | 1.3.0 |
| Mikroskopie (microscopy) | 1.3.0 |
| Rechner (calculator) | 1.4.0 |
| FTIR | 1.5.0 |
| TGA | 0.13.0 |
| Elementrechner (chemistry) | 0.11.0 |
| Datenaufbereitung (data purification) | 0.3.0 |

### Changed results

**Zugversuch 1.3.0**
- `A` and `Ag` now follow ISO 6892-1 (plastic elongation): A = At − σ_break/E and Ag = Agt − Rm/E, with E the slope
  of the linear section. The former values (total strain under load) are now `At` and `Agt`. **Own equations that use
  `A` or `Ag` give new results.**
- Hold time is the contiguous time above the threshold around the maximum; a dip ends it.
- The plateau mean is taken over the last 20 % of the time from the force rise t₀ to the maximum (was: from the first
  point).
- Reference ranking: ΔRm relative to the material's Rm, sorted by status, then |ΔRm|; the hardening ratio only lowers
  the status.
- Idealised material curves start with slope E (Ramberg–Osgood 1943) instead of Rp/ε_y.
- Wbreak uses the measured elongation when the dataset has one.
- Data: titanium Grade 1 Rp0.2 170 → 138 MPa (ASTM B265 minimum); ISO 527-2 type 1A L₀ 50 → 75 mm
  (ISO 527-2:2012).

**Mikroskopie 1.3.0**
- The particle area fraction includes particles touching the border (it was biased low; sample image 4.10 → 4.50 %).
- With edge exclusion, the remaining particles get Miles–Lantuéjoul weights; means, SDs, D-values and histograms are
  weighted, and an edge-corrected count is reported.
- D10/D50/D90 are labelled number-weighted (Q0) and use the midpoint quantile rule (Hyndman–Fan definition 5) instead
  of linear interpolation (definition 7). New volume-weighted Dv10/Dv50/Dv90 (Q3, from ECD³). The dataset comparison
  computes both sides the same way.
- The particle perimeter is the outer boundary (holes filled) by default; circularity rises for particles with holes.
  "Lochränder zum Umfang zählen" restores the total perimeter.
- TIFF files without an ImageJ description are calibrated from XResolution/YResolution and ResolutionUnit (inch, cm),
  except common print resolutions (72, 96, 300 dpi …), which stay uncalibrated.
- With a selected region, edge exclusion uses the region border.

**Rechner 1.4.0**
- Integrals: adaptive Gauss–Kronrod 7/15 with an error estimate. Integrals that do not converge are refused
  (∫₁^∞ sin x/x dx gave 2.293; the true value is 0.6247). Endpoint singularities are much more accurate
  (∫₀¹ x^(−1/2) dx: 1.9946 → 2.0000000).
- Derivatives: relative step with error control, one-sided at domain boundaries (d/dx √x at 10⁻⁴ = 50;
  d/dx sin(1000x) at 0.001: 539.21 → 540.30), with a note at kinks.
- `->` to °C or °F converts a temperature difference without the offset (shown as Δ°C); new syntax `-> Δ°C`.
- Units are carried through integral, derivative, nsolve, sum/product, lists, matrices and linear algebra; a unit that
  cannot be determined is shown as "?".
- Exact derived constants (ħ, R, F, σ, Wien b) at full double precision.
- °fH = 10 mg CaCO₃/L = 0.09991 mmol/L (was 0.1); °dH from M(CaO) (0.178326 mmol/L).
- `IE()` returns an energy (J; write `-> eV`); `IE_eV()` keeps the plain number in eV.
- Fits: R² through the origin uses the uncentred total sum of squares; direct fits use every point valid for the model
  (not only those valid for the linearisation); new fit rows default to direct.
- Formula-card check: tolerance from the rounding of the inputs (was a fixed 10⁻³).
- Report: values with 6 significant digits; value ± u rounded to the uncertainty.

**FTIR 1.5.0**
- First band assignment considers band shape and the functional-group rating (PET: 2969, 1579, 1242, 1095,
  1018 cm⁻¹ now correct).
- S/N: signal = maximum of the smoothed, baseline-corrected spectrum instead of the 99.5th percentile; σ₀ is a robust
  SD of the quiet points (it was 9–24 % low). S/N values are not comparable with 1.4 (PET example 333 → 353).
- CO₂ bridging defaults to the CO₂ bands only, 2390–2280 and 680–655 cm⁻¹ (was 2400–2250 / 720–630, which erased
  polystyrene 698, calcite 712 and isocyanate bands); "wide" stays selectable; a notice when a sample band overlaps.
- ALS baseline λ refers to 1 cm⁻¹ point spacing, so the same λ works at any resolution (per-point λ selectable).
- Band areas and FWHM of transmittance/reflectance spectra are computed on absorbance / log(1/R) (were on −%T).
- Peak-search HQI: library bands use the same S/N criterion as the sample.

**TGA 0.13.0**
- Ozawa–Flynn–Wall Eₐ is refined iteratively as in ASTM E1641 (exact b(E/RT)) instead of Doyle's constant 1.052:
  about −1 % at E/RT ≈ 30 (example 182.6 → 180.5 kJ/mol). Option `ofw="doyle"` keeps the uncorrected value.
- 95 % confidence intervals of activation energies use exact Student t quantiles; before, 2.0 was used for 11–30
  degrees of freedom and 1.96 above.
- Lifetime (ASTM E1877) uses the model-free Toop relation with the OFW Eₐ at the failure conversion by default; the
  model-based Arrhenius extrapolation stays as an option. Not checked against the text of the standard.
- Extrapolated onset and endset use the inflection point and the local slope dm/dT on the temperature axis; results
  change only when the heating rate varies within a step.
- ASTM D7582 proximate analysis on the as-determined basis (rescaled to the mass at start), plus the dry basis.
- PerkinElmer files use the corrected weight instead of "Unsubtracted Weight"; unitless Kelvin temperature columns are
  detected; TRIOS multi-sheet times are made continuous.

**Datenaufbereitung 0.3.0**
- Dixon's Q test refuses an untabulated α (the 0.05 column was used silently); two-sided tests flag only the end with
  the larger Q; one-sided tests use the 2α column.
- Times with a UTC offset are converted to UTC (the offset was dropped); a DST jump inside a series gives a warning.
- Replicate means carry the flags of their member rows (they were cleared).
- Signed quantities (Δ…, Änderung, Differenz, Verlust …) are no longer flagged as impossible when negative.
- A change to flags alone creates a new dataset version; live child datasets are recomputed.
- CSV export: two new final columns, "verwendet" and "Markierungen".

**Elementrechner 0.11.0**
- R and F are exact (N_A·k, N_A·e) at full precision everywhere; displayed results are unchanged.

### Fixed

- **Report editor and hub:** the module version in provenance is taken from the module that computed the result; an
  issued result is moved to `lab/_removed/` instead of being deleted; shared dataset version numbers are never reused;
  the provenance chain of a derived dataset reaches the raw file; the Refresh mode (pin or live) is stored and stated.
- **Zugversuch:** the fit-window text describes the greedy search and states the tolerance; the hold text uses the
  configured threshold; a yield onset compared with Rp0.2 is labelled "not like with like"; idealised curves are
  labelled "for orientation only"; each material shows its value type (minimum, typical …), unverified sources are
  marked and wood E values are labelled bending moduli; imported materials are checked for source and numbers;
  standards without a confirmed edition say "check edition".
- **Mikroskopie:** non-square pixels are handled throughout; TIFF ResolutionUnit is honoured; the Minimum/Intermodes
  and Moments thresholds handle edge cases; "Hintergrund abziehen" is renamed "(Graustufen-Öffnung)" / "(grey-scale
  opening)", because it is not a rolling ball; citation key `soille2004`.
- **Rechner:** the report no longer crashes on "nicht definiert"; Levenberg–Marquardt reports convergence; graph
  regression rows give parameter uncertainties; Lineweaver–Burk is named and its bias noted; double roots are found in
  formula cards; rational roots with large denominators are found exactly; `ch_pOH` states pKw = 14 at 25 °C (new card
  with pKw); `hard_Rm` is marked as a rule of thumb; ISO titles in English; Trost 1991 and Numerical Recipes cited
  completely; 282 formulas.
- **FTIR:** band normalisation refused for T/R spectra; ASTM E1252 no longer cited (it is not implemented);
  Savitzky–Golay cited only where used; Harrick 1967 (ATR correction), Lieber 2003 (polynomial baseline),
  Silverstein 2014 and Cowger 2021 added; Open Specy sources completed or marked "not verified"; mixture fractions
  labelled area shares (not mass fractions); guessed units shown and selectable ("Einheiten …"); SPC x types honoured;
  OPUS extensions `.0`–`.9` accepted; the band-area table header in reports.
- **TGA:** Senum–Yang approximation coefficient (88x → 86x; Vyazovkin Eₐ changes by less than 0.05 kJ/mol); the
  Vyazovkin method cites the 1997 paper it implements; replicate mean ± s from unrounded values; the search weight is
  passed and adjustable; ASTM E1582 cited with the temperature calibration; ASTM editions marked "to be filled in".
- **Datenaufbereitung:** ODS files with long empty runs no longer shift columns; reading caps raised and every
  truncation reported; the type of a stated uncertainty (u, U with k, SD, SE, CI) can be recorded; Parquet gives a clear
  message when pyarrow is missing; the residual rule is described as a rule of thumb, the IQR fences as Hyndman–Fan
  type 7 quantiles, Grubbs as the sequential procedure; Hampel window optionally in x units.
- **Tests and CI:** golden comparisons tolerate floating-point noise near zero and figure-size differences between
  matplotlib releases (both failed on Python 3.10 only); pyarrow is installed in CI.

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
