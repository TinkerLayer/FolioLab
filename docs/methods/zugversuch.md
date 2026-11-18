# Zugversuch (tensile test): methods and validation

This file describes what the Zugversuch module computes, how, with which defaults and limits, and which tests check
it. Code paths are relative to `modules/zugversuch/`. User guide: [modules/zugversuch/README.md](../../modules/zugversuch/README.md).

## How to cite results from this module

State the Folio Lab version (`version` in `package.json`) and the module version (`version` in
`modules/zugversuch/module.json`, currently 1.3.0). When a result is sent to a report, Folio Lab writes
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
| Speed | Given v, else v = path / Δt (from a time column, "averaged"), else 1 mm/min with a note. v only scales the time axis: strain, modulus and Rm do not depend on it; times (t_max, hold time, drop duration) and the number of points in the 1 s slope window do. |
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
   The report's methods text describes it this way and states the tolerance (value `tol`).
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
| Hold time | `hold_run`: the contiguous run of points with y ≥ 0.90·y_max (default) that contains i_max; duration = t(last point of the run) − t(first point of the run). A single point below the limit ends the run. For information the result also keeps `spanne` (first to last point above the limit anywhere, the definition before 1.3.0), `summe` (sum of the durations of all runs) and `abschnitte` (number of runs). |
| Plateau | Mean of y for t_ref + 0.8·(t_max − t_ref) ≤ t ≤ t_max with t_ref = max(t₀, 0), i.e. the last 20 % of the time from the force rise to the maximum (the same origin as t_max and the strain) |
| Ratio | y_max / y_yield (needs a yield onset) |

### 3.5 Strain and apparent modulus

Both need the test speed v (mm/min, converted to mm/s) and the gauge length L₀.

- **Strain.** ε(t) = (t − t₀)·v/L₀. It assumes a constant crosshead speed and that the whole path is gauge-length
  extension.
  For a dataset with a strain or length column the strain is the measured one.
- **Agt** (`Agt_pct`; old key `strain_max_pct` kept with the same value) = 100·ε at i_max: total extension at maximum
  force (ISO 6892-1).
- **At** (`At_pct`; old key `strain_break_pct` kept with the same value) = 100·ε at i_break: total extension at
  fracture, under load, at the last point before the drop.
- **Ag** (`Ag_pct`) = Agt − 100·y_max/m_E and **A** (`A_pct`) = At − 100·y_break/m_E: the elastic part is removed as
  in the extensometer method of ISO 6892-1. m_E = k·L₀/v (`E_fit`) is the slope of the linear section in the same
  strain, so the elastic part uses the same compliance as the measured strain. With a crosshead path all four values
  are apparent (marked "scheinbar" in the report).
- Before 1.3.0 the variable `A` was the total strain at break (now `At`) and `Ag` the total strain at maximum (now
  `Agt`).
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

Since 1.3.0 every row has `wertart`, the value type of Rm and Rp: `min` (minimum), `typ` (typical), `mitte` (middle of
the range), `max` or `unklar` (the source does not say). The report adds it to each material's literature note.
Rows whose source or value could not be checked carry `nicht_geprueft` with the reason; they are marked "nicht
geprüft" in the app and with * in the report's material tables:

- PC, PA6-GF30, PA66-GF30 and BOPET film: averaged or "typical" values without a named data sheet.
- Beech (Buche): the cited publication is about hornbeam (Hainbuche).
- Oak (Eiche): the values come from a comparison table in the cited spruce publication, not from a study on oak.
- EN AW-1050A soft: Rm 76 MPa is the lower end of a range given for all tempers, neither a minimum nor a typical value.

The E values of the three woods are bending moduli (`basis` says so); they are not tensile moduli. Titanium Grade 1
uses the ASTM B265 minimum Rp0.2 = 138 MPa (20 ksi), Rm = 240 MPa (35 ksi); before 1.3.0 Rp was 170 MPa.

Groups: a single category, "alle Metalle" (steel, stainless steel, cast iron, aluminium, copper, titanium, magnesium,
nickel) or "alle Werkstoffe". The group used is the chosen comparison group, else the category of the reference
material, else aluminium. An unknown group falls back to aluminium.

### 4.2 Ranking (only with A₀)

For each material in the group:

- ΔRm = 100·(Rm − Rm_mat)/Rm_mat % and d_rel = |Rm − Rm_mat| / Rm_mat (material value as denominator, as in the
  reference comparison).
- Measured ratio = Rm / y_yield (yield onset from section 3.3); material ratio = Rm_mat / Rp_mat. The two are not
  like with like (a deviation threshold against Rp0.2 or ReH), so the ratio only changes the status.
- d_ratio = |ratio − ratio_mat| / ratio_mat, if both ratios exist.
- Score = d_rel.

| Status | Condition (checked in this order) |
|---|---|
| ausgeschlossen (excluded) | d_rel > 0.40 |
| unwahrscheinlich (unlikely) | d_rel > 0.15 |
| zurückgestuft (downgraded, hardening ratio) | d_ratio > 0.15 |
| Kandidat (candidate) | otherwise |

Rows are sorted by status (candidate, downgraded, unlikely, excluded), then by d_rel, then by name; `rank_rm` sorts by
d_rel alone. The criterion is returned with the result (`criterion`, `ratio_basis`) and shown under the candidate
table; the report's methods text states it. Before 1.3.0 d_rel used the measured Rm as denominator and the rows were
sorted by √(d_rel² + d_ratio²). The result is a list of candidates, not an identification.
For each material the module also gives A_needed = Fmax/Rm_mat (the cross-section at which Fmax would equal Rm_mat)
and d_equiv = √(4·A_needed/π).

### 4.3 Classification by Rm

Rm is compared with [Rm_min, Rm_max] of a material: inside → "schliesst ein" (includes), below → "Werkstoff darüber"
(material above), above → "Werkstoff darunter" (material below). A missing bound is replaced by the nominal Rm; the
basis is then "Spanne unvollständig" (one bound missing) or "Mittelwert" (both missing).

### 4.4 Reference material

| Quantity | Formula |
|---|---|
| ΔRm | 100·(Rm − Rm_ref)/Rm_ref % (reference as denominator, as in the ranking) |
| ΔRp | 100·(y_yield − Rp_ref)/Rp_ref %. This sets the yield onset (a threshold) against Rp0.2 or ReH; it is labelled "nicht gleichartig" / "not like with like" in the app and the report and is for orientation only |
| E ratio | E_app / E_ref |

Without A₀ but with a reference material, the module gives A_needed = Fmax/Rm_ref and d_equiv = √(4A/π).

### 4.5 Idealised curves and envelope

A material without its own curve is drawn as an **idealised curve, for orientation only** (`curve_model`,
`ideal_curve`; ε dimensionless, A = A%/100, E in MPa from the material row):

- ε_u = 0.55·A (uniform strain). If ε_u ≤ Rp/E + 0.002: ε_u = min((Rp/E + 0.002 + A)/2, A).
- 0 ≤ ε ≤ ε_u: Ramberg–Osgood relation in its 0.2 % proof-stress form, ε = σ/E + 0.002·(σ/Rp)^n
  (Ramberg & Osgood 1943, NACA Technical Note 902), inverted numerically (σ grid of 4001 points, linear
  interpolation). n is chosen so that the curve reaches Rm at ε_u: n = ln((ε_u − Rm/E)/0.002) / ln(Rm/Rp). The
  curve therefore starts with slope E and passes through (Rp/E + 0.002, Rp) and (ε_u, Rm).
- ε_u < ε ≤ A: σ = Rm − 0.07·Rm·(ε − ε_u)/(A − ε_u).
- Fallbacks: Rp ≥ Rm: elastic with E up to Rp, then flat ("linear-E"); n ≤ 1 (or ε_u − Rm/E ≤ 0.002): elastic up to
  Rp, then a straight line to Rm at ε_u ("bilinear-E"); Rp/E ≥ A: straight line through (A, Rm) ("sekante"; the
  values do not fit linear elasticity).
- Without Rp: σ = min(E·ε, Rm) up to A, or the secant Rm·ε/A if Rm/E ≥ A.
- Outside 0 ≤ ε ≤ A the curve is undefined.

The factors 0.55 and 0.07 are fixed model choices of the specification with no cited source. Before 1.3.0 the curve
had no cited source, used σ = Rp + (Rm − Rp)·((ε − ε_y)/(ε_u − ε_y))^0.45 after ε_y and started with slope Rp/ε_y
(lower than E). The figure caption, the legend and the report's methods text label the curves "idealisiert, zur
Orientierung" / "idealised, for orientation" and cite Ramberg & Osgood.

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
| Import (`/api/own/import`) | Each entry is checked: a structured source must pass `labcite.errors` and a source text must be text, else the entry is skipped with the reason; numbers must be positive and finite (curve points must be number pairs). An entry without any source is imported but marked "keine Quelle angegeben (importiert)"; the app lists these names and shows "nicht geprüft" for them, and the report adds the mark to the literature note. Saving the entry from the form again requires a source. |

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
| hold | hold time (contiguous run, section 3.4) | s |
| ratio | y_max / y_yield | – |
| E | apparent modulus | GPa |
| A0, L0 | cross-section, gauge length | mm², mm |
| v | test speed | mm/min |
| k | slope of the linear section | N/s |
| Agt, At | total extension at maximum force and at fracture | % |
| Ag, A | Agt and At minus the elastic part (section 3.5) | % |
| Wbreak | work to break ∫F dL from the start to the break point, trapezoid rule, /1000 | J |
| Rm_ref, Rp_ref, A_ref, E_ref | values of the reference material | MPa, MPa, %, GPa |

Wbreak (`work_to_break`) integrates over the measured elongation when there is one (a dataset with a strain or length
column, displacement stored in µm); otherwise over the crosshead path x = max(t − t₀, 0)·v. The variable label says
which. **Meaning change in 1.3.0:** `A` and `Ag` were total strains before; own equations that used them now get the
plastic values. Use `At` and `Agt` for the old meaning.

## 6. Specimen catalogue (`data/specimens.json`)

41 entries: ISO 527-2, ISO 527-3, ASTM D882, ASTM D638, ISO 37, DIN 53504, ASTM D412, ISO 6892-1, ASTM E8, DIN 50125,
ISO 1924-2, ISO 1924-3, ISO 13934-1, plus a round specimen and "Frei" (free). Each entry pre-fills b or d and L₀ and
shows a thickness hint; the thickness is always entered by the user. Deviations from the catalogue larger than
10⁻⁹ mm in b, d or L₀ give note 3.1. The ISO 527-2 entries carry `ausgabe` = ISO 527-2:2012; their dimensions follow
that edition. Type 1A has L₀ = 75 mm as in ISO 527-2:2012 (before 1.3.0: 50 mm, the value of the earlier edition and
of the specification). The report cites the standards with these editions: ISO 527-2:2012,
ISO 527-3:2018, ISO 6892-1:2019, ISO 37:2017, ISO 1924-2:2008, ISO 1924-3:2005, ISO 13934-1:2013. DIN 53504,
ASTM D638, ASTM D882, ASTM D412, ASTM E8 and DIN 50125 are cited without an edition, because the edition could not
be confirmed; the report adds the note "Ausgabe prüfen" (check edition) to these citations. Only ISO 527-2 type 1A
L₀ and 5B b and L₀ are checked by tests.

## 7. Approximations of reference methods

- **Strain** comes from time × nominal speed, not from an extensometer (sections 3.5 and 1.1), unless a dataset
  supplies a measured strain.
- **Yield onset** replaces Rp0.2 by a deviation threshold on the force–time curve.
- **Elongation after fracture** A is estimated as At minus σ_break/m_E (extensometer method of ISO 6892-1), not
  measured on the broken specimen; with a crosshead path it is apparent.
- **Apparent modulus** includes the compliance of grips and frame when the path is the crosshead.
- **Idealised material curves** are a Ramberg–Osgood model through E, Rp0.2 and Rm, for orientation, not data.

## 8. Validation

Run `python -m unittest discover -s tests` in `modules/zugversuch`. The suite has 74 tests (19 of them in `tests/test_science.py`, added in 1.3.0, with known answers on the synthetic curve and hand examples).

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
| `tests/test_science.py::StrainAtFracture::test_at_and_a` | At = 12.0 % (6 places, the last point before the drop); A = 12.0 − 100·σ_break/70 000 (3 places, ≈ 11.83 %); m_E = 70 000 MPa; old key `strain_break_pct` = At |
| `tests/test_science.py::StrainAtFracture::test_agt_and_ag` | Agt = 100·ε at max σ (6 places); Ag = Agt − 100·Rm/70 000 (3 places) |
| `tests/test_science.py::StrainAtFracture::test_variables` | equation variables A and At equal the key values |
| `tests/test_science.py::StrainAtFracture::test_work_from_measured_elongation` | Wbreak = A₀·L₀·∫σ dε integrated in closed form (≈ 0.03132 J) ± 0.1 %; label names the measured elongation |
| `tests/test_science.py::Plateau::test_measured_from_force_rise` | with 0.1 mm of slack at 1 mm/min before the curve: t_ref = 6 s ± 0.2 s; plateau start = t_ref + 0.8·(t_max − t_ref); plateau mean equal to the run without slack (6 places) |

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
| `tests/test_science.py::HoldTime` (2 tests) | hand example with a dip: run 5..8 s gives 3 s (old span 7 s, sum 5 s, 2 runs); without a dip old and new definitions agree |
| `tests/test_science.py::RambergOsgood` (3 tests) | EN AW-5052-H38 (Rp 220, Rm 285, A 7 %, E 70 GPa): initial slope = E ± 1 %; σ = Rp ± 0.5 MPa at Rp/E + 0.002; σ = Rm ± 0.5 MPa at ε_u = 0.55·A; n from σ(ε_u) = Rm (9 places); σ(A) = 0.93·Rm |
| `tests/test_science.py::Ranking` (2 tests) | three made-up materials: ΔRm relative to the material value (9 places); score = \|ΔRm\|/Rm_mat; order status first (the closest Rm with a wrong ratio ranks second); reference ΔRm and ΔRp relative to the reference, ΔRp labelled "nicht gleichartig" |
| `tests/test_science.py::MaterialData` (5 tests) | Titanium Grade 1 Rp = 138 MPa, Rm = 240 MPa (ASTM B265 minimum); every row has a value type; PC, PA6-GF30, PA66-GF30, BOPET, beech and oak are marked unchecked; wood `basis` names the bending modulus; ISO 527-2 type 1A L₀ = 75 mm (ISO 527-2:2012) |
| `tests/test_science.py::OwnImport` (2 tests) | import without a source is marked "keine Quelle angegeben (importiert)"; a non-object cite, a non-text source, non-numeric, negative, NaN or zero values and malformed curve points are rejected |

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
| `tests/test_reference_measurement.py::TestParser` (5 tests) | device fields, empty metadata, number of points, time range, units |
| `tests/test_reference_measurement.py::TestForce::test_prepare` | number of active and cut points (exact), sampling rate (0.1 Hz), test type, force mode without A₀ |
| `tests/test_reference_measurement.py::TestForce::test_fit` | fit window start and end (0.1 s), number of points (exact), k (3 places), q (2 places), R² (5 places), maximal residual (2 places) |
| `tests/test_reference_measurement.py::TestForce::test_t0` | foot point ± 0.01 s |
| `tests/test_reference_measurement.py::TestForce::test_yield` | yield onset for each detent, rounded to 0.1 N |
| `tests/test_reference_measurement.py::TestForce::test_max_break` | indices of maximum and break (exact), forces rounded to 0.1 N; hold time 22.5 s (contiguous run; unchanged in 1.3.0 because this recording has no dip) |
| `tests/test_reference_measurement.py::TestForce::test_no_stress_without_a0` | no stress values without A₀ |
| `tests/test_reference_measurement.py::TestStress::test_area` | A₀ = 0.20 mm² for 2 mm × 0.1 mm |
| `tests/test_reference_measurement.py::TestStress::test_values` | Rm, yield onset and break stress to 1 MPa; k to 2 places; ratio to 2 places |
| `tests/test_reference_measurement.py::TestStress::test_ranking` | the two top candidates; one material excluded and one downgraded; d_equiv ± 0.005 mm |
| `tests/test_reference_measurement.py::TestReferenceComparison::test_rm_against_s235` | reference comparison against S235JR |
| `tests/test_reference_measurement.py::TestStress::test_e_schein` | E_app ± 0.05 GPa and the text of note 7.2 |
| `tests/test_reference_measurement.py::TestStress::test_iso_thickness_warning` | note 7.6 for an ISO 527-2 specimen below 1 mm |
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

- **No strain measurement for `.flps` files.** Strain, Agt, Ag, At, A, E_app and Wbreak come from t and the nominal
  speed v. They include seating and machine compliance. With a crosshead path the modulus can be many times too low
  (note 7.2), and the strains are apparent.
- **Yield onset is not Rp0.2.** It depends on the threshold. The reference comparison sets it against tabulated
  Rp0.2 values and labels this "not like with like"; in the ranking the ratio only lowers the status.
- **A is estimated, not measured after fracture.** A = At − σ_break/m_E assumes elastic unloading with the slope of the
  linear section; it is not measured on the reassembled specimen.
- **Fit window is greedy.** Growth stops at the first point that would exceed the tolerance on either side; it is
  not guaranteed to be the longest window. The report says so.
- **Fine time** assumes evenly spaced points within each second.
- **Hold time** is the contiguous run around the maximum; a single noisy point below the threshold ends it.
- **Idealised material curves** use a fixed uniform strain (0.55·A) and drop (7 %) without a cited source.
- **Materials without Rp** get no ratio and are ranked by Rm alone, like all others.
- **Material data** carry a value type, but many data-sheet rows are "unklar"; minimum and typical values are mixed
  within a group.
- **Dataset speed.** For datasets, v sets the time axis and therefore the number of points in the 1 s slope window.
  The default of 1 mm/min is not neutral for the fit.
- **Material and specimen data** are not certified. Some entries are estimates, some sources are secondary or
  averaged and marked "nicht geprüft", and the wood E values are bending moduli. The sources were not re-checked
  online for 1.3.0. Check each value against its source.
- **Standard editions.** DIN 53504, ASTM D638, D882, D412, E8 and DIN 50125 are cited without an edition
  ("Ausgabe prüfen").
- **Displacement units** of `.flps` files are not confirmed for any code; force units only for N.
- **The acceptance test needs a recording that is not published.** The public suite checks values only on a synthetic
  curve; the golden tests are regression tests.
