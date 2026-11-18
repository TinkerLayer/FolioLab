# Zugversuch (tensile test): methods and validation

This file describes what the Zugversuch module computes, how, with which defaults and limits, and which tests check
it. Code paths are relative to `modules/zugversuch/`. User guide: [modules/zugversuch/README.md](../../modules/zugversuch/README.md).

## How to cite results from this module

State the Folio Lab version (`version` in `package.json`) and the module version (`version` in
`modules/zugversuch/module.json`, currently 1.2.0). When a result is sent to a report, Folio Lab writes
`lab/<result>/bundle.json` in the project. Its `provenance` block records the Folio Lab version, the module id, the module version
and the SHA-256 of every source file stored with the result. "Source files" are the input files kept for *Refresh* (the
`.flps` file or the converted dataset), not the program code. Also state the evaluation settings that differ from the defaults below; the report's methods text lists them.

Every key value in this module is a property of one recording on one set-up. The module names its own limits as
mandatory notes (section 9). Quote them with the values.

## 1. Input

### 1.1 IMADA `.flps` files (`flps/parser.py`)

A `.flps` file is a .NET BinaryFormatter stream (MS-NRBF). The parser is written with the standard library only. It
reads the object `IMADA.SingleSaveData` (serial number, model name, comment, gauge series) and its array `Data[]`.
Each point carries `Num`, `Force` (double), `ForceDecimalPoint`, `ForceUnit`, `Displacement` (integer),
`DisplacementUnit`, `DateTime` and some operator and condition fields.

- **Time stamps.** `DateTime` is read as 62-bit ticks of 100 ns since 1 January 0001. The `Kind` bits are ignored.
- **Force units.** Codes 0 to 7 map to mN, cN, N, kN, gf, kgf, ozf, lbf and are converted to newtons with fixed
  factors (for example gf = 9.80665·10⁻³ N). Only code 2 (N) has been confirmed on real files. Any other code raises
  note 1.4 ("force unit unconfirmed").
- **Displacement units.** Codes 0 to 3 map to mm, cm, in and "none"; code 4 (µm) is used only for converted
  datasets. No displacement code has been confirmed on real files. The displacement column is exported to CSV and
  the workbook but **not used in the evaluation**: strain is computed from time and test speed (section 4).
- **Plausibility check.** If the model name contains a capacity such as `-500N` or `-5kN`
  (pattern `-(\d+(?:\.\d+)?)\s*(k?N)`), the file is rejected with error 1.4 when max |F| exceeds 1.05 × capacity.

### 1.2 Tensile test from a dataset (`flps/dataset.py`)

A tabular dataset can be turned into a measurement that then runs through the same parser and evaluation.

| Step | Rule |
|---|---|
| Column kinds | From the column unit: force, stress, length, time, strain. A dimensionless column counts as strain only if its name contains `dehn`, `strain`, `eps` or `ε`. |
| Required | One load column (force or stress) and a path column (length or strain) or a time column. Stress needs A₀, strain needs L₀. 10 to 200 000 valid rows. |
| Conversion | F = σ·A₀ (σ in MPa, A₀ in mm²). ΔL = ε·L₀ or the length in mm. ΔL starts at 0. |
| Time from path | path = Σ\|ΔL\|. t = path / (v/60), with v in mm/min. |
| Speed | Given v, else v = path / Δt (from a time column, "averaged"), else 1 mm/min with a note. |
| Time from column | If there is no path column, the time column is used; it must not decrease. |
| Strictly increasing time | Equal times are separated by 2 µs steps. |
| Sign | Tension is stored as negative force, compression as positive. |
| Display resolution | Decimals dp = clip(⌈−log₁₀(Fmax/10⁴)⌉, 0, 5). |

Once a measurement comes from a dataset, the values used to convert it stay fixed (`_fix_dataset_geometry` in
`flps/analyse.py`): A₀ if the load was a stress, L₀ if the path was a strain, v if the time was computed from the
path. A different entry is replaced and reported as an info note with code "I-03".

## 2. Data preparation (`flps/prepare.py`)

| Quantity | Rule |
|---|---|
| Fine time | Points with the same time stamp form a group of n points. Point k (0-based) of the group gets t = t_stamp − t_start + k/n seconds. This assumes the logger stamps whole seconds. |
| Test type | "Zug" (tension) if the raw force at max \|F\| is negative, else "Druck" (compression). The evaluation then uses \|F\|. |
| Display resolution | 10^(−ForceDecimalPoint) of the first point if 0 ≤ dp < 6, else 0.1 N. |
| Break (load drop) | First index i with \|F\|[i−1] > upper·Fmax and \|F\|[i] < lower·Fmax. Fmax is taken over all points. Defaults upper = 0.10, lower = 0.01. |
| Active section | Index 0 up to the drop index (inclusive), or to the last point if no break is found (info note 4.6). |
| Sampling rate | rate = i_end / (t_fine[i_end] − t_fine[0]), with i_end the last index of the active section. One sampling interval is 1/rate. |

## 3. Evaluation (`flps/analyse.py`)

All steps use the active section. t is the fine time minus its first value.

### 3.1 Cross-section A₀ (`Config.area`)

| Case | A₀ |
|---|---|
| A₀ entered directly | that value |
| Round | π·d²/4 |
| Tube | π/4·(D² − (D − 2t)²), only if 0 < t ≤ D/2 |
| Rectangle | b·thickness |

With A₀ the evaluation runs in stress, y = |F|/A₀ in MPa. Without A₀ it runs in force, y = |F| in N, and note 7.1
applies.

### 3.2 Slope and linear section

1. **Window.** wp = max(2, round(rate · window)) points, with window = 1.0 s by default (10 points if the rate is not
   finite). h = max(1, ⌊wp/2⌋).
2. **Sliding slope.** s_i = (y[i+h] − y[i−h]) / (t[i+h] − t[i−h]). At the ends the window is clipped to the data.
3. **Start of the fit.** The index of the largest slope, ± 3 points (`fit_start_points`).
4. **Growing the fit window.** In each round the window tries to grow by one point to the left, then by one point to
   the right. A step is kept if the least-squares line (`numpy.polyfit`, degree 1) over the new window has a maximal
   absolute residual strictly below the tolerance. Growth stops when neither side can grow. The tolerance is 1.0 MPa in
   stress mode and 0.20 N in force mode. This is a greedy search; it does not guarantee the longest possible window.
5. **Fit result.** Slope k, intercept q, R² = 1 − SS_res/SS_tot, maximal residual, number of points.
6. **Foot point.** t₀ = −q/k, the time where the fitted line crosses zero. Strain and the time to maximum are
   measured from t₀; this removes the seating phase.

### 3.3 Yield onset

The yield onset is the first index after the fit window with (k·t + q) − y > threshold · y_max. The default
threshold is 0.02 (2 % of Rm, or of Fmax in force mode). The same search is repeated for the slider detents 0.005,
0.01, 0.02 and 0.05 and shown as a table. If threshold · y_max is below twice the display resolution (divided by A₀
in stress mode), note 4.4 warns that the threshold triggers on noise. If no point exceeds the threshold, note 4.4
says so.

**This is a threshold on the force–time curve, not a proof stress Rp0.2** (note 7.4).

### 3.4 Maximum, break, hold, plateau

| Quantity | Definition |
|---|---|
| Maximum | i_max = argmax y; Fmax = \|F\|[i_max]; Rm = y_max (stress mode only) |
| Break point | The point before the load drop: i_break = i_drop − 1 |
| Load drop | y_max − y_break; in % of y_max; duration t_break − t_max |
| Break duration | Shown as "< one sampling interval"; it is not resolved |
| Hold time | Points with y ≥ 0.90·y_max (default); duration = t(last such point) − t(first such point). Points below the limit in between are included. |
| Plateau | Mean of y for 0.8·t_max ≤ t ≤ t_max, with t counted from the start of the active section (not from t₀) |
| Ratio | y_max / y_yield (needs a yield onset) |

### 3.5 Strain and apparent modulus

Both need the test speed v (mm/min, converted to mm/s) and the gauge length L₀.

- **Strain.** ε(t) = (t − t₀)·v/L₀. It assumes a constant crosshead speed and that the whole path is gauge-length
  extension.
- **Ag** (`strain_max_pct`) = 100·ε at i_max.
- **A** (`strain_break_pct`) = 100·ε at i_break. This is the total strain under load at the last point before the
  drop. It is not the elongation after fracture of ISO 6892-1 or similar standards.
- **Apparent modulus.** E_app = k_N · (1/v) · (L₀/A₀) / 1000 in GPa, with k_N = k·A₀ in N/s. It needs v, L₀ and A₀.
  In stress mode this reduces to k·L₀/v/1000. When the displacement was not measured on the specimen, note 7.2
  applies; it also warns when E_app is below half of the smallest E in the comparison group.

### 3.6 Phases

Each point gets one phase for the coloured curve and the CSV: seating (before the fit window), elastic (from the fit
window), plastic (from the yield onset), drop (from the maximum), break (the drop index) and "after break" for points
after the active section.

### 3.7 Defaults and limits

| Setting | Default | Notes |
|---|---|---|
| Slope window | 1.0 s | converted to points with the sampling rate |
| Fit tolerance | 1.0 MPa / 0.20 N | stress / force mode |
| Fit start | ± 3 points | around the largest slope |
| Yield threshold | 0.02 | slider detents 0.005, 0.01, 0.02, 0.05 |
| Break criteria | upper 0.10, lower 0.01 | fractions of Fmax over all points |
| Hold threshold | 0.90 | fraction of y_max |
| Additional materials in the field | at most 20 | |
| Own equations | at most 60 | |
| Values received from other environments | at most 200 | |

## 4. Material comparison (`flps/alloys.py`, `data/alloys.json`)

### 4.1 Material data

`data/alloys.json` holds 88 materials in 15 categories (aluminium 17, steel 9, stainless steel 4, cast iron 2, copper
6, titanium 4, magnesium 2, nickel 3, plastics 20, reinforced plastics 2, films 4, elastomers 6, paper 3, wood 3,
fibre composites 3). Each row has Rp0.2 (may be empty), Rm, A, E, Rm_min, Rm_max, a `basis` and a `quelle` (source),
optionally a URL, a year and an access date. Sources are standards (minimum values), manufacturer data sheets of named
grades or institute publications; values that the source does not give are marked as estimates ("Schätzwert") in
`basis`. **These are not certified values. Check every value you quote against the cited source.**

Groups: a single category, "alle Metalle" (steel, stainless steel, cast iron, aluminium, copper, titanium, magnesium,
nickel) or "alle Werkstoffe". The group used is the chosen comparison group, else the category of the reference
material, else aluminium. An unknown group falls back to aluminium.

### 4.2 Ranking (only with A₀)

For each material in the group:

- d_rel = |Rm_mat − Rm| / Rm (measured Rm as denominator).
- Measured ratio = Rm / y_yield (yield onset from section 3.3); material ratio = Rm_mat / Rp_mat.
- d_ratio = |ratio_mat − ratio| / ratio, if both ratios exist.
- Score = √(d_rel² + d_ratio²), or d_rel alone if a ratio is missing.

| Status | Condition (checked in this order) |
|---|---|
| ausgeschlossen (excluded) | d_rel > 0.40 |
| unwahrscheinlich (unlikely) | d_rel > 0.15 |
| zurückgestuft (downgraded, hardening ratio) | d_ratio > 0.15 |
| Kandidat (candidate) | otherwise |

Rows are sorted by score; a second rank sorts by d_rel. The result is a list of candidates, not an identification.
For each material the module also gives A_needed = Fmax/Rm_mat (the cross-section at which Fmax would equal Rm_mat)
and d_equiv = √(4·A_needed/π).

### 4.3 Classification by Rm

Rm is compared with [Rm_min, Rm_max] of a material: inside → "schliesst ein" (includes), below → "Werkstoff darüber"
(material above), above → "Werkstoff darunter" (material below). A missing bound is replaced by the nominal Rm; the
basis is then "Spanne unvollständig" (one bound missing) or "Mittelwert" (both missing).

### 4.4 Reference material

| Quantity | Formula |
|---|---|
| ΔRm | 100·(Rm − Rm_ref)/Rm_ref % (reference as denominator; the ranking uses the measured Rm) |
| ΔRp | 100·(y_yield − Rp_ref)/Rp_ref %, comparing the yield onset with Rp0.2 |
| E ratio | E_app / E_ref |

Without A₀ but with a reference material, the module gives A_needed = Fmax/Rm_ref and d_equiv = √(4A/π).

### 4.5 Idealised curves and envelope

A material without its own curve is drawn as an idealised stress–strain curve (ε dimensionless, A = A%/100,
E in MPa):

- ε_y = Rp/E + 0.002; ε_u = 0.55·A.
- 0 ≤ ε ≤ ε_y: σ = Rp·ε/ε_y.
- ε_y < ε ≤ ε_u: σ = Rp + (Rm − Rp)·((ε − ε_y)/(ε_u − ε_y))^0.45.
- ε_u < ε ≤ A: σ = Rm − 0.07·Rm·(ε − ε_u)/(A − ε_u).
- Without Rp, or if ε_y ≥ A: σ = Rm·ε/A.
- If ε_u ≤ ε_y: ε_u = (ε_y + A)/2.
- Outside 0 ≤ ε ≤ A the curve is undefined.

The exponent 0.45, the factors 0.55 and 0.07 are fixed model choices with no cited source. The initial slope is
Rp/ε_y, which is lower than E. The curves show the order of magnitude of a material class, not a measured curve.

A material with its own curve (from a source) is interpolated linearly in % strain and is undefined outside its
range. The envelope is the pointwise maximum and minimum of all defined curves on a 1500-point strain grid up to the
largest A.

### 4.6 Own materials

| Rule | Value |
|---|---|
| Name | at most 80 characters; must not match a bundled material |
| Category | at most 40 characters; default "Eigene Werkstoffe" |
| Values | positive; Rp ≤ Rm; Rm_min ≤ Rm_max |
| Without a curve | Rm, A and E are required |
| Curve | 3 to 5000 points, strictly increasing strain, (0, 0) is added. Rm = maximum stress, A = last strain, E = secant to the last point with σ ≤ 0.3·max (for display) |
| Source | Saving from the form needs a structured source or a source text |

## 5. Own equations (`sdk/python/labcalc/formulas.py`)

Symbols match `^[A-Za-z][A-Za-z0-9_]{0,23}$`. At most 60 equations; later equations may use earlier ones; digits 1 to
10 (default 4). An error (for example a division by zero or a non-finite result) stays with its row. Variables are
plain numbers; units are not carried through the calculation.

| Variable | Meaning | Unit |
|---|---|---|
| Fmax | maximum force | N |
| tmax | t_max − t₀ | s |
| Rm | maximum stress | MPa |
| Fy, sy | force and stress at the yield onset | N, MPa |
| Fbreak, sbreak | force and stress at the break point | N, MPa |
| drop | load drop | % |
| hold | hold time | s |
| ratio | y_max / y_yield | – |
| E | apparent modulus | GPa |
| A0, L0 | cross-section, gauge length | mm², mm |
| v | test speed | mm/min |
| k | slope of the linear section | N/s |
| Ag, A | strain at maximum and at break | % |
| Wbreak | work to break, trapezoid of F over x = max(t − t₀, 0)·v from the start to the break point, /1000 | J |
| Rm_ref, Rp_ref, A_ref, E_ref | values of the reference material | MPa, MPa, %, GPa |

Wbreak uses the crosshead path computed from v and t, not a measured displacement.

## 6. Specimen catalogue (`data/specimens.json`)

41 entries: ISO 527-2, ISO 527-3, ASTM D882, ASTM D638, ISO 37, DIN 53504, ASTM D412, ISO 6892-1, ASTM E8, DIN 50125,
ISO 1924-2, ISO 1924-3, ISO 13934-1, plus a round specimen and "Frei" (free). Each entry pre-fills b or d and L₀ and
shows a thickness hint; the thickness is always entered by the user. Deviations from the catalogue larger than
10⁻⁹ mm in b, d or L₀ give note 3.1. The report cites the standards with these editions: ISO 527-2:2012,
ISO 527-3:2018, ISO 6892-1:2019, ISO 37:2017, ISO 1924-2:2008, ISO 1924-3:2005, ISO 13934-1:2013. DIN 53504,
ASTM D638, ASTM D882, ASTM D412, ASTM E8 and DIN 50125 are cited without an edition. No test checks the catalogue
dimensions against the standards.

## 7. Approximations of reference methods

- **Strain** comes from time × nominal speed, not from an extensometer (sections 3.5 and 1.1).
- **Yield onset** replaces Rp0.2 by a deviation threshold on the force–time curve.
- **Elongation at break** A is total strain under load, not plastic elongation after fracture.
- **Apparent modulus** includes the compliance of grips and frame when the path is the crosshead.
- **Idealised material curves** are a fixed model, not data.

## 8. Validation

Run `python -m unittest discover -s tests` in `modules/zugversuch`. The suite has 54 tests.

### 8.1 Synthetic curve (runs in the public repository)

`tests/test_dataset.py` defines a curve with known answers: linear with E = 70 GPa up to 105 MPa, then hardening
σ = 105 + 35·(1 − exp(−(ε − ε_y)/0.02)) MPa, a linear drop of 20 MPa after ε = 0.09, break at ε = 0.12 with the load
falling below 1 % of Fmax. A₀ = 0.2 mm², L₀ = 10 mm, v = 1 mm/min.

| Test | Expected |
|---|---|
| `tests/test_dataset.py::Translate::test_same_result_both_ways` | Rm = max σ ± 0.01 MPa; E_app = 70 GPa ± 3 %; Ag = strain at max σ ± 0.05 percentage points; stress + strain and force + elongation routes agree within 10⁻³; break found; type tension |
| `tests/test_dataset.py::Translate::test_geometry_locked` | A₀, L₀ and v stay at the dataset values, each with a note; Rm unchanged; force + elongation with A₀ = 0.4 mm² gives Rm/2 |
| `tests/test_dataset.py::Translate::test_time_axis_speed_and_duplicates` | v averaged from a time column = 2.0 mm/min (6 places); equal paths give strictly increasing time stamps; default 1 mm/min with a note; compression gives positive force |
| `tests/test_dataset.py::Translate::test_guess_and_columns` | column kinds, geometry read from conditions (A₀ 0.2 mm², L₀ 10 mm from 1 cm, v 1 mm/min); unitless column without a strain name is not strain |
| `tests/test_dataset.py::Translate::test_errors` | missing load, wrong kinds, missing A₀ or L₀, missing path, non-positive or non-numeric geometry, too few rows are rejected |
| `tests/test_dataset.py::ServerFlow::test_flow` | import, new version, restart and citation through the module server |
| `tests/test_golden_synthetic.py::GoldenSynthetic::test_known_values` | same curve through the full path: Rm = max σ ± 0.01 MPa; E_app = 70 GPa ± 3 % |
| `tests/test_golden_synthetic.py::GoldenSynthetic::test_bundle_de`, `::test_bundle_en` | report bundle equals the stored snapshot (`tests/golden/zugversuch_synth_*.json`) |

### 8.2 Materials, specimens, cross-sections (no measurement needed)

| Test | Expected |
|---|---|
| `tests/test_reference.py::TestMaterialsAndSpecimens::test_database` | main categories present; more than 60 materials; every row has a source; names unique |
| `tests/test_reference.py::TestMaterialsAndSpecimens::test_default_group_is_aluminium` | without a group, only aluminium materials are compared |
| `tests/test_reference.py::TestMaterialsAndSpecimens::test_ideal_curves_all_finite` | every idealised curve is finite on 0..A and its maximum is within 2 % of Rm |
| `tests/test_reference.py::TestMaterialsAndSpecimens::test_specimens` | expected specimen names present; ISO 527-2 type 5B has b = 2 mm and L₀ = 10 mm |
| `tests/test_reference.py::TestMaterialsAndSpecimens::test_tube_area` | tube D = 10 mm, t = 1 mm: A₀ = π/4·(100 − 64) mm² (9 places); t = 6 mm > D/2 gives no area |
| `tests/test_reference.py::TestAlloyCurve::test_curve_shape` | first material (A = 30 %): σ(0) = 0, σ(0.30) = 0.93·Rm, undefined at 0.31 |
| `tests/test_reference.py::TestCliAndServer::test_cli_norm_round` | DIN 50125 B 6×30 gives a round specimen, d = 6 mm, L₀ = 30 mm, A₀ = 9π mm² |
| `tests/test_reference.py::TestCliAndServer::test_cli_manual_tube` | `--manuell --rohr 10 1` gives A₀ = π/4·(100 − 64) mm² |
| `tests/test_reference.py::TestCliAndServer::test_server_meta_and_envelope` | the steel envelope contains S235JR and no aluminium alloy |
| `tests/test_own.py::OwnMaterialTest::test_validation` | missing Rm, Rp > Rm and an empty name are rejected; decimal comma accepted |
| `tests/test_own.py::OwnMaterialTest::test_curve_text_and_derived_values` | own curve: Rm 140, A 40 % from the points; linear interpolation, e.g. σ(1 %) = 35 + 45·0.5/1.5 MPa; undefined beyond the last point |
| `tests/test_own.py::OwnMaterialTest::test_merge_skips_builtin_names` | an own material with a bundled name is refused |

### 8.3 Tests on a whole measurement

`tests/_input.py` supplies a measurement: the maintainers' reference recording if it is present, otherwise the
synthetic curve of section 8.1 converted with `flps.dataset.make_raw`. These tests check outputs and plumbing, not
values: `tests/test_reference.py::TestExports` (3 tests), `tests/test_bundle.py::BundleTest` (6 tests; Rm in the
values file is 140 MPa on the synthetic curve), `tests/test_own.py::ExtrasAndEquationsTest` (an own equation
Rm/Rm_ref·100 matches to 6 places; Wbreak > 0; Rm/0 is reported as an error) and `tests/test_own.py::ServerOwnTest`.

### 8.4 Acceptance test on the reference recording (not public)

The acceptance test evaluates one real recording with stored expected values. The recording is not in the public
repository, so these classes and tests are skipped there:

| Test | What is checked |
|---|---|
| `tests/test_reference.py::TestParser` (5 tests) | device fields, empty metadata, number of points, time range, units |
| `tests/test_reference.py::TestForce::test_prepare` | number of active and cut points (exact), sampling rate (0.1 Hz), test type, force mode without A₀ |
| `tests/test_reference.py::TestForce::test_fit` | fit window start and end (0.1 s), number of points (exact), k (3 places), q (2 places), R² (5 places), maximal residual (2 places) |
| `tests/test_reference.py::TestForce::test_t0` | foot point ± 0.01 s |
| `tests/test_reference.py::TestForce::test_yield` | yield onset for each detent, rounded to 0.1 N |
| `tests/test_reference.py::TestForce::test_max_break` | indices of maximum and break (exact), forces rounded to 0.1 N |
| `tests/test_reference.py::TestForce::test_no_stress_without_a0` | no stress values without A₀ |
| `tests/test_reference.py::TestStress::test_area` | A₀ = 0.20 mm² for 2 mm × 0.1 mm |
| `tests/test_reference.py::TestStress::test_values` | Rm, yield onset and break stress to 1 MPa; k to 2 places; ratio to 2 places |
| `tests/test_reference.py::TestStress::test_ranking` | the two top candidates; one material excluded and one downgraded; d_equiv ± 0.005 mm |
| `tests/test_reference.py::TestStress::test_e_schein` | E_app ± 0.05 GPa and the text of note 7.2 |
| `tests/test_reference.py::TestStress::test_iso_thickness_warning` | note 7.6 for an ISO 527-2 specimen below 1 mm |
| `tests/test_reference.py::TestMaterialsAndSpecimens::test_reference_material_and_group` | group follows the reference category; ΔRm = 100·(Rm − Rm_ref)/Rm_ref to 6 places; "alle Metalle" gives more than 30 rows |
| `tests/test_reference.py::TestMaterialsAndSpecimens::test_norm_deviation_and_mismatch_notes` | notes for a deviating width and for a reference material not intended for the specimen |
| `tests/test_reference.py::TestCliAndServer::test_server_sketch` | specimen sketch |
| `tests/test_golden.py::GoldenBundle` (2 tests) | report bundle equals a stored snapshot |

The golden tests (`test_golden.py`, `test_golden_synthetic.py`) are regression tests. They show that a result has not
changed, not that it is correct.

## 9. Mandatory notes

| Code | Level | When |
|---|---|---|
| 1.4 | warning / error | force unit not confirmed / force above 1.05 × the capacity in the model name |
| 3.1 | info | dimensions differ from the chosen standard specimen; manual mode |
| 4.4 | warning | yield threshold below twice the resolution; no yield onset found |
| 4.6 | info | no break found |
| 7.1 | warning | no A₀: force only, no stresses, comparison or ranking |
| 7.2 | warning | path not measured on the specimen: modulus is apparent; also when E_app < 0.5 × the smallest E of the group |
| 7.3 | info | always: necking is not proven by a falling force |
| 7.4 | info | always: the elastic–plastic limit is a threshold, not Rp0.2 |
| 7.5 | warning | no test speed documented |
| 7.6 | warning / info | ISO 527-2 shape with a thickness below 1 mm; thickness hint exceeded; other ISO 527-2 note; reference category not intended for the specimen |
| 7.7 | info | always: time uncertainty of one sampling interval |
| I-03 | info | dataset notes and fixed geometry |

## Known limitations

- **No strain measurement.** Strain, Ag, A, E_app and Wbreak all come from t and the nominal speed v. They include
  seating and machine compliance. With a crosshead path the modulus can be many times too low (note 7.2).
- **Yield onset is not Rp0.2.** It depends on the threshold. The reference comparison and the ranking ratio still set
  it against tabulated Rp0.2 values.
- **A is not elongation after fracture.** It is compared with tabulated A values that are usually elongation after
  fracture.
- **Fit window is greedy.** Growth stops at the first point that would exceed the tolerance on either side. The
  report's methods text calls it the longest window; it is not guaranteed to be.
- **Fine time** assumes evenly spaced points within each second.
- **Hold time** includes dips below the threshold between the first and last point above it. The generated report text
  states 90 % even when the hold threshold is changed.
- **Plateau** is measured from the start of the active section, not from t₀.
- **ΔRm** uses the measured Rm as denominator in the ranking and the reference Rm in the reference comparison.
- **Materials without Rp** are ranked by Rm alone.
- **Dataset speed.** For datasets, v sets the time axis and therefore the number of points in the 1 s slope window.
  The default of 1 mm/min is not neutral for the fit.
- **Material and specimen data** are not certified. Some entries are estimates, some sources are secondary or
  averaged, and the wood E values come from bending tests. Check each value against its source.
- **Displacement units** of `.flps` files are not confirmed for any code; force units only for N.
- **The acceptance test needs a recording that is not published.** The public suite checks values only on a synthetic
  curve; the golden tests are regression tests.
