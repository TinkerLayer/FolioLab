# Rechner: methods and validation

This document describes what the Rechner (Calculator) module computes: unit conversion, constants, the equation
library, formula cards, equation and system solving, statistics, the fit tool, graphs, calculus, complex numbers and
matrices. Every default and limit below is taken from the code in `modules/rechner/rechner/` and
`sdk/python/labcalc/`. Every reference is given exactly as it appears in the code. Where the code cites nothing, this
is stated as "no external reference; standard textbook method". Each section ends with the tests that check it.

For how to use the page, see the [module README](../../modules/rechner/README.md).

## How to cite results from this module

State the software and the module version:

> Calculated with Folio Lab 0.1.0, module Rechner 1.3.0.

- The Folio Lab version is `version` in the top-level `package.json`.
- The module version is `version` in `modules/rechner/module.json` (`"1.3.0"`). It is identical to `__version__` in
  `modules/rechner/rechner/__init__.py`.
- Every report bundle writes a `bundle.json` with a `provenance` block. It records `suite_version` (Folio Lab), `module_id`, `module_version` and
  `source_sha256` (the SHA-256 hash of each source file attached to the bundle), plus a `result_id` and a `revision`.
- The Rechner attaches no source files to its bundles, so `source_sha256` is empty for Rechner bundles. Instead the
  complete calculation request (the working state) is stored under `source.request` in `bundle.json`. The report can
  be rebuilt from it. When a calculation uses a dataset variable, the request also records the share ID and the
  dataset version used.
- The Folio Lab version is recorded with each result as `provenance.suite_version` in its `bundle.json`.
- If you report a formula-card result, also cite the formula source and the constant sources listed in the card. The
  report does this automatically with `\cite`.
- If you report a fit, state the model, the mode (linearised or direct), n and whether the ± value is the standard
  uncertainty or the 95 % interval (see [section 9](#9-fit-tool)).

## Contents

1. [Evaluation and number display](#1-evaluation-and-number-display)
2. [Units and conversion](#2-units-and-conversion)
3. [Constants](#3-constants)
4. [Equation library](#4-equation-library)
5. [Formula cards, derive and search](#5-formula-cards-derive-and-search)
6. [Equations in calculation lines](#6-equations-in-calculation-lines)
7. [Systems of equations](#7-systems-of-equations)
8. [Statistics and dataset variables](#8-statistics-and-dataset-variables)
9. [Fit tool](#9-fit-tool)
10. [Graph: drawing, thinning, regression, special points](#10-graph-drawing-thinning-regression-special-points)
11. [Integral, derivative, root finding, sum and product](#11-integral-derivative-root-finding-sum-and-product)
12. [Complex numbers](#12-complex-numbers)
13. [Matrices](#13-matrices)
14. [Chemistry lookup functions](#14-chemistry-lookup-functions)
15. [Known limitations](#known-limitations)

Test paths are relative to the project root. SDK tests run with `python -m unittest discover -s tests` from
`sdk/python`. Module tests run with the same command from `modules/rechner`.

---

## 1. Evaluation and number display

**What is computed.** Each input is parsed into a restricted Python syntax tree and evaluated with numpy
(`sdk/python/labcalc/expr.py`). `eval` is never used. Unknown names are an error.

**Notation.** Implicit multiplication (`2(3+4)`, `a b`), `^` for powers, `!` for factorial, `e` notation for powers
of ten. Trigonometric functions use the DEG/RAD setting of the page. Formula cards always calculate in radians.

**Number display.** Results are computed in double precision. They are displayed rounded:

| Where | Significant digits |
|---|---|
| Calculation line on the page | 10 |
| Calculation line in the report | 8 |
| Matrix in the report | 6 |
| Formula-card result, table of quantities, `\labval` values | 5 |
| Regression parameters and R² in the report | 5 |
| Fit parameters in the report | see [section 9](#9-fit-tool) |

Report the number with the precision your input data support, not the displayed digits.

**Validation.**

| Test | Checks |
|---|---|
| `modules/rechner/tests/test_rechner.py::Expressions::test_calculator_notation` | `2(3+4)^2` = 98, `5!` = 120, `sin(30)` in DEG = 0.5, `a b` = 6 |
| `modules/rechner/tests/test_rechner.py::Expressions::test_safety` | `__import__('os')`, `open('x')`, `().__class__`, `lambda: 1` are rejected |
| `modules/rechner/tests/test_rechner.py::Expressions::test_statements` | assignment, function and conversion statements are recognised |
| `modules/rechner/tests/test_golden.py::GoldenBundle::test_sheet_de` (and `test_sheet_en`, `test_envs_de`, `test_envs_en`) | report bundles match stored reference output |

---

## 2. Units and conversion

**What is computed.** Every quantity in a calculation line or card is converted to SI before calculation. Its unit is
tracked as a vector of exponents of the seven SI base units (m, kg, s, A, K, mol, cd). Results are shown in a
readable unit chosen per kind of quantity, or in the unit requested with `->`. Code:
`sdk/python/labcalc/units.py`.

**Unit definitions.** SI base and derived units with the SI prefixes from Y to a (`µ` and `u` for micro). Selected
non-SI units and their factors to SI:

| Unit | Factor to SI | Note |
|---|---|---|
| atm | 101325 Pa | |
| Torr | 101325/760 Pa | |
| mmHg | 133.322387415 Pa | |
| psi | 6894.757293168 Pa | |
| cal | 4.184 J | thermochemical calorie |
| eV | 1.602176634·10⁻¹⁹ J | |
| Wh | 3600 J | |
| M | 1000 mol/m³ | molar, mol/L |
| a | 365.25 d | year |
| u, Da | 1.66053906892·10⁻²⁷ kg | CODATA 2022 value |
| Ci | 3.7·10¹⁰ Bq | |
| P (poise), St (stokes) | 0.1 Pa·s, 10⁻⁴ m²/s | |
| sccm, slm | 10⁻⁶/60 m³/s, 10⁻³/60 m³/s | |
| °dH | 0.17832 mmol/L | German hardness, 10 mg CaO/L |
| °fH | 0.1 mmol/L | French hardness |
| °C | K with offset 273.15 | |
| °F | factor 5/9 K, offset 459.67·5/9 | |

**Temperature.** An offset applies only when the unit stands alone. `20 °C` is 293.15 K. In compound units
(`°C/min`, `J/(kg·°C)`) the offset is dropped and the unit is a difference. A value can be read as a difference
explicitly (`diff=True` in the code); `10 °C` as a difference is 10 K.

**Scales.** pH, dB, NTU, FNU, FAU and AU are scales. They convert only to themselves. `pH` is the scale, not
picohenry.

**Kinds of quantity.** About 90 kinds (velocity, pressure, concentration …) each have a dimension and a list of
display units. `auto_unit` picks a readable unit; temperatures between 200 K and 2000 K are shown in °C.

**Units through functions.** Units propagate through arithmetic, powers and functions such as `sqrt`, `mean`, `std`,
`sum`, `sort`, `cumsum` and `diff`. `var` gives the unit squared. The result of `integral`, `deriv`, `nsolve`,
`sum(expr, k, a, b)`, `polyfit` and similar functions carries **no unit**.

**Reference.** No external reference; standard textbook method. The value of u and Da is the CODATA 2022 atomic mass
constant (see [section 3](#3-constants)).

**Limitations.**
- Converting a temperature **difference** with `->` to °C or °F applies the offset. A difference of 10 K converted
  with `-> °C` shows −263.15 °C. Convert differences to K.
- Results of calculus functions lose their unit (see above).
- °fH uses 0.1 mmol/L; 10 mg CaCO₃/L is 0.0999 mmol/L.

**Validation.**

| Test | Checks |
|---|---|
| `modules/rechner/tests/test_rechner.py::Units::test_parse` | 72 km/h = 20 m/s; 1 N/mm² = 10⁶ Pa; 20 °C = 293.15 K; 10 °C as difference = 10 K; 1 L/(mol·cm) = 0.1 m²/mol; 1 kWh = 3.6·10⁶ J |
| `modules/rechner/tests/test_rechner.py::Units::test_kinds` | 2.5·10⁸ Pa is shown in MPa; kg·m/s² is shown as N |
| `sdk/python/tests/test_units.py::UnitsU01Test::test_conversions` | e.g. 760 Torr = 1 atm, 1 °dH = 0.17832 mmol/L, 1 mTorr = 0.133322 Pa (5 places, relative) |
| `sdk/python/tests/test_units.py::UnitsU01Test::test_ph_is_a_scale` | pH is a scale, not picohenry |
| `sdk/python/tests/test_units.py::UnitsU01Test::test_every_kind_converts_within_itself` | every display unit of every kind converts |
| `sdk/python/tests/test_units.py::UnitsU01Test::test_kinds_for_new_units` | new units have a kind |
| `sdk/python/tests/test_units.py::UnitsU01Test::test_dataset_ph_column` | a pH column keeps its scale |

---

## 3. Constants

**What is computed.** Named constants are available in calculation lines and are inserted into formula cards.
Values: `sdk/python/labcalc/units.py` (`CONSTANTS`). Sources: `sdk/python/labcalc/sources.py`
(`CONSTANT_SOURCES`).

| Name | Value | Unit | Source key | Exact in code |
|---|---|---|---|---|
| `pi`, `e` | π, e | 1 | bronstein | yes |
| `g0` | 9.80665 | m/s² | codata2022 (note: 3rd CGPM 1901) | yes |
| `c0` | 299792458 | m/s | si2019 | yes |
| `hP` | 6.62607015·10⁻³⁴ | J·s | si2019 | yes |
| `hbar` | 1.054571817·10⁻³⁴ | J·s | codata2022 | yes (stored to 10 digits) |
| `kB` | 1.380649·10⁻²³ | J/K | si2019 | yes |
| `NA` | 6.02214076·10²³ | 1/mol | si2019 | yes |
| `Rgas` | 8.314462618 | J/(mol·K) | codata2022 | yes (stored to 10 digits) |
| `G_grav` | 6.67430·10⁻¹¹ | m³/(kg·s²) | codata2022 | no, rel. u 2.2·10⁻⁵ |
| `eps0` | 8.8541878188·10⁻¹² | F/m | codata2022 | no |
| `mu0` | 1.25663706127·10⁻⁶ | N/A² | codata2022 | no |
| `q_e` | 1.602176634·10⁻¹⁹ | C | si2019 | yes |
| `m_e` | 9.1093837139·10⁻³¹ | kg | codata2022 | no |
| `m_p` | 1.67262192595·10⁻²⁷ | kg | codata2022 | no |
| `m_n` | 1.67492750056·10⁻²⁷ | kg | codata2022 | no |
| `m_u` | 1.66053906892·10⁻²⁷ | kg | codata2022 | no |
| `sigma_SB` | 5.670374419·10⁻⁸ | W/(m²·K⁴) | codata2022 | yes (stored to 10 digits) |
| `F_c` | 96485.33212 | C/mol | codata2022 | yes (stored to 10 digits) |
| `T0` | 273.15 | K | si2019 | yes |
| `p_n` | 101325 | Pa | codata2022 | yes |
| `p_std` | 10⁵ | Pa | greenbook | yes |
| `c_std` | 1000 | mol/m³ | greenbook | yes |
| `b_std` | 1 | mol/kg | greenbook | yes |
| `MPa1` | 10⁶ | Pa | si2019 | yes |
| `b_wien` | 2.897771955·10⁻³ | m·K | codata2022 | yes (stored to 10 digits) |

**References, as cited in the code.**
- codata2022: Mohr, P. J.; Newell, D. B.; Taylor, B. N.; Tiesinga, E. "CODATA recommended values of the fundamental
  physical constants: 2022". Reviews of Modern Physics 97, 025002 (2025). doi:10.1103/RevModPhys.97.025002.
- si2019: BIPM. The International System of Units (SI). Bureau International des Poids et Mesures, 2019, 9th edition.
- greenbook: Cohen, E. R.; Cvitaš, T.; Frey, J. G.; Holmström, B.; Kuchitsu, K.; Marquardt, R.; Mills, I.; Pavese,
  F.; Quack, M.; Stohner, J.; Strauss, H. L.; Takami, M.; Thor, A. J. Quantities, Units and Symbols in Physical
  Chemistry (IUPAC Green Book). RSC Publishing, 2007, 3rd edition. doi:10.1039/9781847557889.
- bronstein: Bronshtein, I. N.; Semendyayev, K. A.; Musiol, G.; Mühlig, H. Handbook of Mathematics. Springer, 2015,
  6th edition.

**Uncertainty.** Constants are used as exact numbers. The uncertainty of inexact constants (G, ε₀, μ₀, particle
masses) is recorded in the source note but is not propagated.

**Limitations.** `hbar`, `Rgas`, `sigma_SB`, `F_c` and `b_wien` are exact by definition but are stored truncated to
10 significant digits. The relative error is about 10⁻¹⁰.

**Validation.**

| Test | Checks |
|---|---|
| `modules/rechner/tests/test_rechner.py::Chemistry::test_codata_2022` | ε₀ = 8.8541878188·10⁻¹² and mₑ = 9.1093837139·10⁻³¹ exactly; R = N_A·k (8 places); F = N_A·e (4 places) |
| `modules/rechner/tests/test_rechner.py::Chemistry::test_every_equation_and_constant_sourced` | every constant has a complete source record |

---

## 4. Equation library

**What is computed.** The library (`modules/rechner/rechner/library.py`) holds 281 equations. Each has an ID, a field,
a topic, the equation `lhs = rhs`, its variables with a kind of quantity, and a source.

| Field | Equations |
|---|---|
| Chemistry | 76 |
| Strength of materials | 56 |
| Mechanics | 49 |
| Heat | 24 |
| Electrical engineering | 22 |
| Optics and microscopy | 18 |
| Fluid mechanics | 16 |
| Geometry | 14 |
| Mathematics | 6 |

109 equations are marked *auto*: they are general laws used by *derive* (see [section 5](#5-formula-cards-derive-and-search)).

**How the source is assigned.** In order of priority: the `src` argument of the equation, then `SRC_OVERRIDE` (per
equation), then `SECTION_SRC` (per field and topic). Book sources get the note "Stichwort: <English name of the
equation>", which names the topic under which the equation is found. No page numbers are given; the code states that
page numbers are only given where they were checked.

| Source key | Equations | Used for |
|---|---|---|
| halliday | 86 | mechanics, heat, gases, electrical engineering |
| gross2 | 32 | stress and strain, bending, torsion and buckling, vessels |
| atkins | 25 | chemical thermodynamics, colligative properties, kinetics |
| harris | 25 | concentration, acids and bases, solubility, lab practice |
| bronstein | 20 | geometry, mathematics |
| white | 16 | fluid mechanics |
| hecht | 11 | light, lenses |
| krane | 9 | radioactivity |
| greenbook | 8 | amount of substance and concentration |
| iso6892 | 7 | tensile test |
| murphy | 7 | imaging and microscopy |
| bard | 7 | electrochemistry |
| callister | 6 | true stress and strain, notch, rule of mixtures, Hall–Petch |
| anderson | 6 | fracture mechanics |
| bergman | 6 | heat transfer |
| iso178 | 2 | three-point bending |
| porter | 2 | diffusion |
| iso6507 | 1 | Vickers hardness |
| iso6506 | 1 | Brinell hardness |
| iso18265 | 1 | tensile strength from hardness |
| sheldon2007 | 1 | E factor |
| jimenez2011 | 1 | process mass intensity |
| constable2002 | 1 | reaction mass efficiency |

**References, as cited in the code** (`sdk/python/labcalc/sources.py`; codata2022, si2019, greenbook and bronstein are
in [section 3](#3-constants)):
- halliday: Halliday, D.; Resnick, R.; Walker, J. Fundamentals of Physics. Wiley, 2014, 10th edition.
- gross2: Gross, D.; Hauger, W.; Schröder, J.; Wall, W. A. Technische Mechanik 2: Elastostatik. Springer Vieweg,
  2017, 13th edition.
- callister: Callister, W. D.; Rethwisch, D. G. Materials Science and Engineering: An Introduction. Wiley, 2018, 10th
  edition.
- anderson: Anderson, T. L. Fracture Mechanics: Fundamentals and Applications. CRC Press, 2017, 4th edition.
- bergman: Bergman, T. L.; Lavine, A. S.; Incropera, F. P.; DeWitt, D. P. Fundamentals of Heat and Mass Transfer.
  Wiley, 2011, 7th edition.
- white: White, F. M. Fluid Mechanics. McGraw-Hill, 2011, 7th edition.
- hecht: Hecht, E. Optics. Pearson, 2017, 5th edition.
- murphy: Murphy, D. B.; Davidson, M. W. Fundamentals of Light Microscopy and Electronic Imaging. Wiley-Blackwell,
  2012, 2nd edition.
- krane: Krane, K. S. Introductory Nuclear Physics. Wiley, 1988.
- atkins: Atkins, P.; de Paula, J.; Keeler, J. Atkins' Physical Chemistry. Oxford University Press, 2018, 11th
  edition.
- harris: Harris, D. C. Quantitative Chemical Analysis. W. H. Freeman, 2016, 9th edition.
- bard: Bard, A. J.; Faulkner, L. R. Electrochemical Methods: Fundamentals and Applications. Wiley, 2001, 2nd edition.
- porter: Porter, D. A.; Easterling, K. E.; Sherif, M. Y. Phase Transformations in Metals and Alloys. CRC Press,
  2009, 3rd edition.
- iso6892: ISO. ISO 6892-1:2019 (title in the code in German: tensile testing of metallic materials, part 1, method
  of test at room temperature). International Organization for Standardization, 2019.
- iso178: ISO. ISO 178:2019 (title in the code in German: plastics, determination of flexural properties), 2019.
- iso6507: ISO. ISO 6507-1:2018 (title in the code in German: Vickers hardness test of metallic materials, part 1),
  2018.
- iso6506: ISO. ISO 6506-1:2014 (title in the code in German: Brinell hardness test of metallic materials, part 1),
  2014.
- iso18265: ISO. ISO 18265:2013 (title in the code in German: conversion of hardness values of metallic materials),
  2013. Code note: the factor 3.3 is a rule of thumb; a reliable conversion needs the tables of the standard.
- sheldon2007: Sheldon, Roger A. "The E Factor: fifteen years on". Green Chemistry 9(12), 1273-1283 (2007).
  doi:10.1039/b713736m.
- constable2002: Constable, David J. C.; Curzons, Alan D.; Cunningham, Virginia L. "Metrics to 'green' chemistry --
  which are the best?". Green Chemistry 4(6), 521-527 (2002). doi:10.1039/b206169b.
- jimenez2011: Jimenez-Gonzalez, Concepción; Ponder, Celia S.; Broxterman, Quirinus B.; Manley, Julie B. "Using the
  Right Green Yardstick: Why Process Mass Intensity Is Used in the Pharmaceutical Industry To Drive More Sustainable
  Processes". Organic Process Research & Development 15(4), 912-917 (2011). doi:10.1021/op200097d.

**Units.** Each variable has a kind of quantity. All equations are dimensionally consistent (checked by test).
Concentrations enter logarithms as `c/c_std` (c° = 1 mol/L), pressures as `p/p_std` where used.

**Chemistry assumptions visible in the equations.**
- Concentrations are used in place of activities. No activity coefficients appear.
- `ch_pOH` uses `pH + pOH = 14` (25 °C). Other acid–base equations take pKw as a variable; its label states 14.00 at
  25 °C.
- `ch_weak_acid` is the approximation `pH = 0.5·(pKa − log10(c_a/c°))`. Its note says it holds for c/Ka > 100.
  `ch_weak_acid_exact` solves Ka = x²/(c − x) and neglects water autoprotolysis (note: valid up to about pH 6). The
  same holds for the weak-base pair.
- `ch_T_switch`, `ch_vanthoff` and `ch_kirchhoff` assume ΔH, ΔS or ΔCp constant over the range (stated in the notes).
- `hard_Rm` converts hardness to tensile strength with the factor 3.3, a rule of thumb (see iso18265 above).

**Validation.**

| Test | Checks |
|---|---|
| `modules/rechner/tests/test_rechner.py::Library::test_size` | at least 200 equations, unique IDs |
| `modules/rechner/tests/test_rechner.py::Library::test_dimensions` | both sides of every equation have the same dimension (strict) |
| `modules/rechner/tests/test_rechner.py::Library::test_every_variable_solvable` | for every equation, every variable is recovered from the others (rel. tol. 10⁻⁵) |
| `modules/rechner/tests/test_rechner.py::Library::test_isolate` | `kin_v_t` isolated for a gives `(v - v0) / t` |
| `modules/rechner/tests/test_rechner.py::Chemistry::test_every_equation_and_constant_sourced` | every equation has a complete source |
| `modules/rechner/tests/test_rechner.py::Chemistry::test_weak_acid` | 0.1 mol/L, pKa 4.76: exact pH 2.883 (3 places) and equal to the closed form (9 places); approximation 2.88; back-solving gives 0.1 mol/L |
| `modules/rechner/tests/test_rechner.py::Chemistry::test_weak_base_and_strong` | 0.1 mol/L, pKb 4.75, pKw 14: pH 11.125; strong acid 0.01 mol/L: pH 2.0; strong base 0.01 mol/L: pH 12.0 |
| `modules/rechner/tests/test_rechner.py::Chemistry::test_buffer_and_dissociation` | Henderson–Hasselbalch at equal concentrations: 4.76; α = 0.5 at pH = pKa; buffer capacity at pH = pKa: ln 10 · c/4 |
| `modules/rechner/tests/test_rechner.py::Chemistry::test_nernst_and_thermo` | Nernst, E° 0.34 V, z 2, Q 100, 298.15 K: 0.2808 V; ΔG = ΔH − TΔS; ln K = −ΔG°/RT |
| `modules/rechner/tests/test_rechner.py::Chemistry::test_radioactivity_and_colligative` | activity after one half-life: 50 Bq of 100 Bq; λ = ln 2 for T½ = 1 s; ΔTf = 3.72 K for i 2, Kf 1.86 K·kg/mol, b 1 mol/kg |

These chemistry tests check the formulas against hand calculations with the same formulas. They do not compare with
measured data.

---

## 5. Formula cards, derive and search

**What is computed.** A formula card evaluates one library equation on a sheet (`modules/rechner/rechner/solver.py`).
If exactly one variable has no value, it is calculated. The target can also be set by hand.

**Algorithm.**
1. **Insert values.** A sheet variable is inserted if symbol and kind of quantity both match. If there is exactly one
   user value of a kind (not the kind "number") and exactly one variable of that kind in the equation, it is inserted
   too. `pi`, `e`, `MPa1` and `c_std` are never replaced by user values.
2. **Symbolic isolation.** The equation is rearranged for the target if the target occurs exactly once. Inverse
   functions use their principal branch. For an even power, the negative root is added unless the kind of quantity is
   positive.
3. **Numerical solving** if isolation is impossible. The residual is scanned on a grid: `logspace(-15, 15, 1201)`,
   plus negative values and `linspace(-1, 1, 201)` if the kind can be negative. Angles use `linspace(-π, π, 1441)`.
   Each sign change is bisected (200 iterations, relative tolerance 10⁻¹⁵). A root is accepted if
   |lhs − rhs| ≤ 10⁻⁷ · max(|lhs|, |rhs|). Positive kinds keep only roots > 0.
4. **Choice of root.** The first positive root is taken. For angles, a root in [0, π/2] is preferred. The user can
   choose another root.
5. **Check.** If all variables have values, the card checks the equation. It is "OK" if the relative difference is
   below 10⁻³.

**Derive.** Equations marked *auto* compute further values from the sheet variables. Each step needs an equation with
exactly one missing variable. At most 5 rounds and 80 derived values.

**Search for missing values** (*Gesucht …*) lists equations that yield a quantity, sorted by the number of missing
values.

**Reference.** No external reference; standard textbook method (isolation, grid scan and bisection).

**Units and uncertainty.** All values are in SI during calculation. The result is shown in a selectable unit with 5
significant digits. No uncertainty is propagated.

**Limitations.**
- The numerical search finds roots only where the residual changes sign on the grid. Roots outside 10⁻¹⁵ … 10¹⁵ in
  magnitude and roots where the residual touches zero without a sign change are missed.
- The automatic root choice (first positive root) may not be the physically relevant one. Check the offered roots.
- The 10⁻³ tolerance of the check is loose for precise data.

**Validation.**

| Test | Checks |
|---|---|
| `modules/rechner/tests/test_rechner.py::Sheet::test_derive_v_t_gives_a` | v 72 km/h, t 8 s: a = 2.5 m/s²; with m 1.2 t: F = 3000 N |
| `modules/rechner/tests/test_rechner.py::Sheet::test_card_auto_and_target` | m = 1200 kg from F and a; crack length a = (K_I/(Y·σ))²/π |
| `modules/rechner/tests/test_rechner.py::Sheet::test_numeric_and_units` | s = v0·t + a·t²/2 solved numerically for t: (−5 + √425)/2 s (8 places) |
| `modules/rechner/tests/test_rechner.py::Sheet::test_card_cycle_marked` | two cards that need each other are marked as a circular reference |
| `modules/rechner/tests/test_rechner.py::Sheet::test_missing` | missing variable is reported |
| `modules/rechner/tests/test_rechner.py::Sheet::test_goal` | search lists equations for power and for K_I |
| `modules/rechner/tests/test_rechner.py::Sheet::test_curve` | formula curve over σ has the requested points and falls |

---

## 6. Equations in calculation lines

**What is computed.** A calculation line with `=` and exactly one unknown is solved for it
(`sdk/python/labcalc/solve.py`). Conditions after a comma (`, x > 0`) filter the solutions.

**Polynomials** (up to degree 24).
- Coefficients are kept as exact fractions where they are rational.
- Degree 1 and 2 are solved exactly; the quadratic result is shown in surd form.
- Rational roots are detected (denominator up to 1000, then checked exactly) and divided out. A remaining quadratic is
  solved exactly.
- Other roots: `numpy.roots` (eigenvalues of the companion matrix), then 6 Newton steps. Roots closer than 10⁻⁴ are
  merged.
- All real roots are listed. Complex roots are hidden unless complex mode is on; a note says so.

**Other equations** (numerical).
- The residual is scanned on three grids in turn: ±10 (4001 points), ±10³ (logarithmic from 10⁻⁶ plus linear), and
  ±10¹⁵ (logarithmic).
- Sign changes are bisected to 10⁻¹³. Touching roots (no sign change) are found by golden-section minimisation of |f|
  and Newton steps on f′. They are accepted if |f| ≤ 10⁻¹² times the scale of the equation.
- Each root is polished with 4 Newton steps.
- At most 12 solutions are shown, those closest to 0, with a note. If a grid already holds more than 12 solutions,
  the search stops there with the note "many solutions (periodic?)" and the range searched.

**Unit of the unknown.** It is found from the other quantities by solving linear equations in the dimension
exponents. If the units do not fit, a note is shown and the unknown has no unit.

**Reference.** No external reference; standard textbook method.

**Limitations.**
- Numerical roots outside ±10¹⁵, or between grid points without a sign change and not found by the minimiser, are
  missed.
- Rational roots with a denominator above 1000 are treated as irrational (still found numerically).

**Validation.**

| Test | Checks |
|---|---|
| `sdk/python/tests/test_solve.py::Equations::test_quadratic_surd` | x² − 3 + x = 0: method quadratic; x₂ = (−1 + √13)/2 (14 places) |
| `sdk/python/tests/test_solve.py::Equations::test_rational_roots_split_off` | x³ − 2x = 0: exact root 0, others ±√2 in surd form |
| `sdk/python/tests/test_solve.py::Equations::test_numeric_and_touching` | x·eˣ = 1: 0.5671432904097838 (12 places); cos x = 1 finds 2π (within 10⁻⁸) and notes periodicity |
| `sdk/python/tests/test_solve.py::Equations::test_identity_and_none` | identity, no solution, x² + 1 = 0 has 2 complex solutions in complex mode |
| `sdk/python/tests/test_solve.py::Equations::test_dims` | ½·m·v² = Ek with m 2 kg, Ek 100 J: v = ±10 m/s, unit m/s; inconsistent units give a note |
| `sdk/python/tests/test_solve.py::Equations::test_bound_names_are_not_unknown` | the integration variable is not an unknown |
| `modules/rechner/tests/test_rechner.py::Solve::test_quadratic_exact_and_pick` | x₁ + x₂ = −1; picked root (−1 + √13)/2 |
| `modules/rechner/tests/test_rechner.py::Solve::test_kinds_of_equations` | y = 2y − 3: 3; x³ − 6x² + 11x − 6 = 0: 1, 2, 3; eˢ = 10⁶: ln 10⁶ (9 places); 2x + 3 = 4: 1/2 |
| `modules/rechner/tests/test_rechner.py::Solve::test_units_of_the_unknown` | v = 10 m/s, 36 km/h |

---

## 7. Systems of equations

**What is computed.** Several equations separated by `;`, or entered under **Solve a system of equations**
(`sdk/python/labcalc/solve.py`).

**Linear systems.**
- Linearity is detected by evaluating the residuals at random points (fixed seed) and comparing with a linear model
  (relative tolerance 10⁻⁹).
- The augmented matrix is reduced to row echelon form. If all coefficients are rational, this is done exactly in
  fractions (limit denominator 10000, tolerance 10⁻¹²). Otherwise partial pivoting with tolerance 10⁻¹¹ × the largest
  entry is used.
- Result: **unique** solution, **infinite** (parametric form in the free variables), or **none**. For "none" the
  least-squares solution (`numpy.linalg.lstsq`) and its residual are shown.

**Nonlinear systems.**
- Need as many equations as unknowns.
- Damped Newton method: forward-difference Jacobian with step 10⁻⁷ · max(1, |x|), least-squares step, step halving
  down to 10⁻⁶, at most 80 iterations.
- 35 starting points: 0.5, 1, −1, 2, 0.1 in all unknowns, and 10 random points each with σ = 1, 10 and 100 (fixed
  seed).
- A solution is accepted if the residual check passes (relative 10⁻⁹). Duplicates are merged. At most 8 solutions;
  a note says "further solutions possible".

**Reference.** No external reference; standard textbook method.

**Limitations.** The nonlinear search is not exhaustive. Solutions far from the starting points can be missed. The
random starts use a fixed seed, so results are reproducible.

**Validation.**

| Test | Checks |
|---|---|
| `sdk/python/tests/test_solve.py::Systems::test_linear_exact` | 2x + 3y = 1, x − y = 2: x = 7/5, y = −3/5 exactly; rank 2 |
| `sdk/python/tests/test_solve.py::Systems::test_infinite_and_none` | x + y = 3, 2x + 2y = 6: infinite, x = 3 − y; x + y = 3, x + y = 4: none, least squares x = 1.75 |
| `sdk/python/tests/test_solve.py::Systems::test_nonlinear` | x² + y² = 25, x − y = 1: (−3, −4) and (4, 3) |
| `modules/rechner/tests/test_rechner.py::Solve::test_systems` | the same cases through calculation lines, including stored names p_1, q_1 … |
| `modules/rechner/tests/test_rechner.py::Solve::test_report_shows_solutions` | report shows the solution steps |

---

## 8. Statistics and dataset variables

**What is computed** (`sdk/python/labcalc/expr.py`).

| Function | Definition |
|---|---|
| `mean`, `median`, `min`, `max` | numpy |
| `std`, `var` | sample standard deviation and variance (denominator n − 1) |
| `linreg(x, y)` | least-squares straight line `numpy.polyfit(x, y, 1)`; returns `[k, d, R²]` with y = k·x + d and R² = 1 − SSE/SST |
| `polyfit(x, y, n)` | `numpy.polyfit`; coefficients from the highest power down; no limit on n |
| `polyval`, `roots` | numpy; `roots` returns real values if the imaginary parts are ≤ 10⁻¹² relative |
| `interp`, `trapz` | linear interpolation; trapezoidal rule |
| `seq`, `linspace` | sequences; `seq` gives at most 10⁶ values |
| `rand` | unseeded random numbers |

**Units.** In calculation lines, `linreg` returns k in the unit of y/x, d in the unit of y, and R² without a unit.
`std` keeps the unit; `var` gives the unit squared.

**Dataset variables** (`modules/rechner/rechner/dsvars.py`). Columns of a shared dataset become lists.
- At most 8 bindings and 20 columns per binding.
- Values are in SI. Excluded rows and rows with a gap in any chosen column are removed from **all** chosen columns.
- Reserved names get the suffix `_ds`.
- A binding either follows the newest version or is pinned. The report records the version used.

**Reference.** No external reference; standard textbook method.

**Uncertainty.** `linreg` and `polyfit` return no uncertainties. Use the fit tool ([section 9](#9-fit-tool)) when
you need parameter uncertainties.

**Limitations.** `rand` is not seeded, so results using it are not reproducible. `polyfit` has no limit on the
degree; fits of high degree are ill-conditioned.

**Validation.**

| Test | Checks |
|---|---|
| `modules/rechner/tests/test_rechner.py::DatasetVariables::test_linreg_units` | k = 2·10¹⁰ Pa, d = 10⁶ Pa, R² = 1, units carried |
| `modules/rechner/tests/test_rechner.py::DatasetVariables::test_report_names_dataset_version` | report source records dataset version 2 |
| `modules/rechner/tests/test_rechner.py::DatasetVariables::test_live_follows_pinned_stays` | following binding moves to the new version, pinned binding stays |

`mean`, `median`, `std`, `var` and `polyfit` have no dedicated numerical tests in this module; they are thin wrappers
around numpy.

---

## 9. Fit tool

**What is computed.** Least-squares fit of a model to a data series y(x) with parameter uncertainties
(`sdk/python/labcalc/fitting.py`). Used by **Fit …** in the graph, on dataset and table rows.

**Models.**

| Key | Model | Parameters | Linearised form |
|---|---|---|---|
| lin | y = m·x + b | m, b | – |
| prop | y = m·x | m | – |
| poly2 | y = a·x² + b·x + c | a, b, c | – |
| poly3 | y = a·x³ + b·x² + c·x + d | a, b, c, d | – |
| log | y = a + b·ln x | a, b | y over ln x |
| exp | y = a·e^(b·x) | a, b | ln y = ln a + b·x |
| pow | y = a·x^b | a, b | ln y = ln a + b·ln x |
| arrh | k = A·e^(−Ea/(R·T)) | A, Ea | ln k = ln A − (Ea/R)·(1/T) |
| mm | v = Vmax·S/(Km + S) | Vmax, Km | 1/v = 1/Vmax + (Km/Vmax)·(1/S) (Lineweaver–Burk) |

**Data preparation.** Only pairs with finite x and y are used. For log forms, points with y ≤ 0 (exp), x ≤ 0 or
y ≤ 0 (pow, mm), k ≤ 0 or T ≤ 0 (arrh), or x ≤ 0 (log) are removed with a note. Fewer pairs than parameters is an
error. Values are used in the units of the columns, not SI.

**Linear models** (lin, prop, poly2, poly3, log). Ordinary least squares by `numpy.linalg.lstsq`. Covariance:
`cov = s²·(AᵀA)⁻¹` with `s² = SSE/(n − p)`. Linearised and direct mode give the same result for these models.

**Linearised mode** (exp, pow, arrh, mm). An unweighted straight line `Y = c + s·X` is fitted to the transformed
points as above. The parameters are calculated back:
- exp, pow: a = e^c, b = s
- arrh: A = e^c, Ea = −s·R/1000 in kJ/mol, with R = 8.314462618 J/(mol·K)
- mm: Vmax = 1/c, Km = s/c

The covariance is propagated to first order: `cov_p = G·cov·Gᵀ`, where G is the Jacobian of the back-transformation.

**Direct mode** (exp, pow, arrh, mm). Least squares in the original y with the Levenberg–Marquardt method:
- Start: the linearised result. Internal parameters ln a (exp, pow), ln A and −Ea/R (arrh), Vmax and Km (mm).
- Forward-difference Jacobian with step 10⁻⁷ · max(1, |q|).
- λ starts at 10⁻³, is divided by 10 after a successful step and multiplied by 10 after a failed one (up to 16 tries
  per iteration). At most 200 iterations. Stop when the decrease in SSE is ≤ 10⁻¹⁵ × SSE.
- Covariance: `(SSE/(n − p))·pinv(JᵀJ)` at the solution, propagated to the reported parameters to first order.

**Arrhenius temperature.** x must be a temperature. °C and °F are converted to K; x without a unit is read as K
(with a note). A has the unit of k; Ea is in kJ/mol.

**Reported quantities.**
- Each parameter: value, standard uncertainty `u = √cov_ii`, and `ci = t·u` with t the two-sided 95 % Student-t
  quantile for n − p degrees of freedom.
- R² = 1 − SSE/SST in the original y, with SST about the mean of y (also for the model through the origin).
- `r2_lin`: R² of the straight line in the linearised coordinates (linearised models only).
- Residual standard deviation `s = √(SSE/(n − p))`.
- If n = p: no uncertainty, with a note.

**Student-t quantile** (`sdk/python/labcalc/stats.py`). Bisection on the t distribution function, which is
computed from the regularised incomplete beta function by continued fraction. Range ±1000, stop at an interval
below 10⁻¹². Reference as cited in the code: "Numerical Recipes 6.4".

**What the user sees.** The page shows value ± standard uncertainty u; the 95 % interval is in the tooltip. The
report states: "Values are given ± standard uncertainty; 95 % confidence with t = …".

**Report precision.** u is rounded to 2 significant digits and the value to the same decimal place. If |value| ≥ 10⁵
or < 10⁻³, the value is printed with 4 significant digits and u with 2.

**Units of parameters.** Built from the column units: lin m in y/x, b in y; prop m in y/x; poly coefficients in
y/xᵏ; log a and b in y; exp a in y, b in 1/x; pow a and b without unit (a note says that a holds for x and y in the
column units); arrh A in y, Ea in kJ/mol; mm Vmax in y, Km in x.

**Graph fits use all values.** A fit on a dataset uses every non-excluded row in the optional x range, not the thinned
points drawn on the screen.

**Reference.** No external reference for the fitting algorithms; standard textbook method (ordinary least squares,
Levenberg–Marquardt, first-order error propagation). The t quantile cites "Numerical Recipes 6.4".

**Limitations.**
- Linearised fits are unweighted. Transforming y (ln y, 1/v) changes the error structure. Lineweaver–Burk (mm,
  linearised) is known to weight low-concentration points heavily. Prefer the direct mode for reporting.
- The direct mode also drops points removed for the linearisation (e.g. y ≤ 0 for exp).
- Uncertainties are first-order (linear) approximations. For A in Arrhenius and a in exp/pow, the true interval is
  asymmetric; the reported u is symmetric.
- The Levenberg–Marquardt routine reports no convergence status. If it stops at the iteration limit, no warning is
  shown.
- The parameter a of the log model depends on the unit of x, but only the pow model has a note about units.
- Uncertainties assume independent, equally distributed errors in y and no errors in x.
- In the report, a value with |value| ≥ 10⁵ or < 10⁻³ is printed with 4 significant digits, which can be fewer
  digits than its uncertainty justifies.

**Validation.**

| Test | Checks |
|---|---|
| `sdk/python/tests/test_fitting.py::Stats::test_t_quantiles` | t(0.975, 10) = 2.2281 (3 places); t(0.975, 1) = 12.706 (2 places) |
| `sdk/python/tests/test_fitting.py::Fitting::test_line_with_units_and_ci` | 50 points, y = 2.5x + 0.3 with noise σ = 0.01: m = 2.5, b = 0.3 (2 places); units MPa/% and MPa; ci = u·t(48); R² > 0.999; n 50, dof 48 |
| `sdk/python/tests/test_fitting.py::Fitting::test_exponential_linearised_and_direct` | y = 4·e^(−0.8x) with 0.5 % noise: a = 4.0 (1 place), b = −0.8 (2 places), both modes |
| `sdk/python/tests/test_fitting.py::Fitting::test_arrhenius_in_celsius_gives_kj_per_mol` | noise-free data in °C: Ea = 50.000 kJ/mol (3 places), A = 10⁷ (relative, 3 places) |
| `sdk/python/tests/test_fitting.py::Fitting::test_michaelis_menten` | noise-free data, direct: Vmax = 10, Km = 2 (4 places) |
| `sdk/python/tests/test_fitting.py::Fitting::test_polynomial_and_predict` | poly2 recovers [0.5, −1, 1] (abs. 10⁻⁹); prediction at 3 is 2.5 |
| `sdk/python/tests/test_fitting.py::Fitting::test_non_positive_values_for_log_forms` | y ≤ 0 removed with note; too few valid points is an error |
| `sdk/python/tests/test_fitting.py::Fitting::test_too_few_points` | one point is an error |
| `modules/rechner/tests/test_rechner.py::Graph::test_large_dataset_thinned_and_fitted` | 200 000 points, one excluded: fit uses 199 999; m = 3.0 N/s (3 places); x range restricts the fit |
| `modules/rechner/tests/test_rechner.py::Graph::test_fit_on_table_into_bundle` | Arrhenius fit on a table gives Ea > 50 kJ/mol and appears in the report |

The tests check parameter values. No test compares the reported standard uncertainties with an independent reference
(e.g. the analytic formula for a straight line or a reference data set). The models prop, poly3, log and pow have no
numerical test.

---

## 10. Graph: drawing, thinning, regression, special points

Code: `modules/rechner/rechner/graph.py`.

**Thinning of large data series.** The full data stay on the server.
- Up to 4000 points (`MAX_PTS`), all points are sent.
- Points: those inside the view plus a 5 % margin. If more than 4000, one point per screen cell of 2 px is kept. The
  cell size is doubled (up to 32 px) until at most 30 000 points (`MAX_CELLS`) remain.
- Lines: the points in the x range plus their neighbours. If more than 4000, the minimum and maximum of each chunk of
  k = ⌈n/(2·max(w, 100))⌉ points are kept in order, so no peak is lost.
- A series is drawn as a line by default if it has more than 2000 points and at least 98 % of the x steps are
  non-decreasing.
- The report figure is computed in the same way with a fixed size of 1400 × 900 px.
- Thinning affects drawing only. Fits use all values (see [section 9](#9-fit-tool)).

**Curves.** Functions of x are sampled at max(400, min(2400, 2·w)) points. Parametric curves use 2000 points.
Implicit equations in x and y are drawn with marching squares on a grid of max(80, min(260, w/4)) ×
max(60, min(200, h/4)) cells.

**Regression rows** (`y1 ~ model`). Levenberg–Marquardt from 5 starting values (all parameters 1, 0.5, −1, 0.1 or 2),
at most 200 iterations and 12 λ tries per iteration. The result with the smallest SSE is kept. Only R² is reported,
no uncertainty.

**Special points** on a clicked curve: roots by a 4000-point scan plus bisection; extrema by golden-section search (80
iterations); intersections and the y intercept. At most 60 points.

**Older plot format.** `modules/rechner/rechner/plots.py` contains an older fit (`/api/fit`) based on
`numpy.polyfit` with log-linearisation for exp, pow and log, R² only.

**Reference.** No external reference; standard textbook method.

**Limitations.**
- Regression rows give no uncertainty and no convergence status. Use **Fit …** for reportable parameters.
- Roots and extrema are found only where the scan resolves them; closely spaced roots can be missed.
- Implicit curves are approximate at the grid resolution.

**Validation.**

| Test | Checks |
|---|---|
| `modules/rechner/tests/test_rechner.py::Graph::test_large_dataset_thinned_and_fitted` | 200 000 points: fewer than 5000 sent as a line; at most 30 000 as points |
| `modules/rechner/tests/test_rechner.py::Graph::test_regression_and_poi` | table (0,1), (1,3), (2,5), (3,7) with `y1 ~ m x1 + b`: m = 2, b = 1 (6 places), R² = 1; roots of x² − 4: two, one at 2 (5 places) |
| `modules/rechner/tests/test_rechner.py::Graph::test_slider_implicit_value` | slider, implicit circle, ∫sin x from 0 to π = 2 (6 places) |
| `modules/rechner/tests/test_rechner.py::Graph::test_classify` | expression types are recognised |
| `modules/rechner/tests/test_rechner.py::ConsoleAndPlots::test_analysis_and_fit` | roots of x² − 2: ±√2 (rel. 10⁻⁸); tan x on [−2, 2]: one root (poles excluded); x³ − 3x: max then min; older fit: k = 2, R² = 1, exp b = 1 (3 places) |

---

## 11. Integral, derivative, root finding, sum and product

Code: `sdk/python/labcalc/expr.py`.

**`integral(f, x, a, b)`.**
- Composite Gauss–Legendre rule with 16 nodes per subinterval and 96 equal subintervals.
- A second value with 24 subintervals is computed but not used. No error estimate is reported.
- Infinite limits: substitution x = a + t/(1 − t), dx = dt/(1 − t)², integrated over t from 0 to 1 − 10⁻¹². An
  integral from −∞ to ∞ is split at 0.
- A non-finite result is an error.

**`deriv(f, x, x0[, n])`.** Central differences with step h = 10⁻³ · max(1, |x0|) and one Richardson step:
D = (4·D(h/2) − D(h))/3. Orders 1 and 2 only.

**`nsolve(equation, x, start)`.** Newton's method from the start value (at most 100 iterations, tolerance 10⁻¹²).
If that fails, a sign-change scan over growing spans (1 to 10⁶, 401 points each) followed by bisection (tolerance
10⁻¹³, 200 iterations). With two start values the root is bracketed between them.

**`sum(expr, k, a, b)`, `prod(…)`.** Direct summation, at most 10⁶ terms. If b < a the result is 0 (sum) or 1
(product).

**Reference.** No external reference; standard textbook method.

**Units.** These functions return plain numbers; the unit of the integrand is not carried.

**Limitations.**
- The integral has no error estimate and no adaptivity. Smooth integrands are accurate to near machine precision.
  Integrands with endpoint singularities are less accurate: ∫₀¹ 1/√x dx gives 1.9946 instead of 2 (−0.27 %).
  Oscillating integrands on infinite intervals can be badly wrong without a warning: ∫₁^∞ sin(x)/x dx gives 2.293
  instead of 0.6247. Integrands with kinks are integrated less precisely (∫₀¹ |x − 0.3| dx gives 0.28999996 instead
  of 0.29).
- The derivative step is at least 10⁻³ in absolute terms. Functions that vary on a smaller scale are inaccurate
  (d/dx sin(1000x) at x = 0.001 gives 539.21 instead of 540.30). Near a domain boundary the stencil can leave the
  domain (√x at 10⁻⁴ evaluates √ of a negative number); the result is undefined.
- `nsolve` returns one root; which one depends on the start value.

**Validation.**

| Test | Checks |
|---|---|
| `modules/rechner/tests/test_rechner.py::Expressions::test_calculus` | ∫₀³ x² dx = 9 (9 places); ∫ e^(−x²) over (−∞, ∞) = √π (7 places); d/dx x³ at 2 = 12 (6 places); nsolve x² = 2 from 1: √2 (10 places); Σk² for k = 1…10 = 385 |
| `modules/rechner/tests/test_rechner.py::Graph::test_slider_implicit_value` | ∫₀^π sin x dx = 2 (6 places) |

The examples under "Limitations" were computed for this document; they are not part of the test suite.

---

## 12. Complex numbers

**What is computed.** With **complex** on, `sqrt`, `ln`, `asin` and `acos` of real arguments outside their real
domain use numpy's `emath` functions and return complex values. A negative real number raised to a non-integer power
gives a complex result. `i` and `j` are the imaginary unit.

Without complex mode these cases give NaN ("not defined"). Equation solving hides complex roots unless complex mode
is on (see [section 6](#6-equations-in-calculation-lines)).

**Reference.** No external reference; standard textbook method. Principal branches as in numpy.

**Validation.**

| Test | Checks |
|---|---|
| `modules/rechner/tests/test_rechner.py::Expressions::test_complex` | `sqrt(-4)` is NaN without complex mode and 2i with it |
| `sdk/python/tests/test_solve.py::Equations::test_identity_and_none` | x² + 1 = 0 has 2 solutions in complex mode |

---

## 13. Matrices

**What is computed.** Matrices from the Matrices tab and matrix literals `[[1,2],[3,4]]` (`sdk/python/labcalc/expr.py`).

| Operation | Implementation |
|---|---|
| `A*B`, `A'` (transpose), `A[i,j]` | numpy; indices count from 1 |
| `A/B` | A · inv(B) |
| `A^n` | `numpy.linalg.matrix_power`, integer n only |
| `det`, `inv`, `eig`, `eigvec`, `svd`, `pinv`, `cond`, `rank`, `norm` | numpy / LAPACK |
| `rref` | Gauss–Jordan elimination, tolerance 10⁻¹² |
| `linsolve(A, b)` | numpy linear solver |

A singular matrix in `inv` or `linsolve` is an error.

**Reference.** No external reference; standard textbook method.

**Limitations.** No units on matrix entries. `rref` uses a fixed tolerance, so the rank of badly scaled matrices can
be misjudged; check with `rank` and `cond`.

**Validation.**

| Test | Checks |
|---|---|
| `modules/rechner/tests/test_rechner.py::Expressions::test_matrices` | A·A, transpose, inv([[1,2],[3,4]]) = [[−2, 1], [1.5, −0.5]], det = −2, linsolve([[2,1],[1,3]], [3,5]) = [0.8, 1.4], rref, singular matrix is an error |
| `modules/rechner/tests/test_rechner.py::ConsoleAndPlots::test_console` | `b = inv(A)` in a calculation line |

---

## 14. Chemistry lookup functions

Calculation lines can call chemistry functions that take a formula or element as text, for example molar mass `M`,
`pKa`, `Ksp`, standard thermodynamic data `dfH`, `dfG`, `Sm0`, ionisation energy `IE`, vapour pressure `pvap` and
nuclear data `Thalf`, `Qval`. They are registered in `sdk/python/labcalc/expr.py` and come from the Elemental
Calculator's data. Their help texts name these data sources:

| Functions | Source named in the help text |
|---|---|
| `M`, `Ar`, `n`, `m_of` | IUPAC/CIAAW standard atomic weights |
| `pKa`, `pKb`, `Ksp`, `pKsp`, `lgK` | NIST SRD 46 / IUPAC dataset |
| `Tm`, `Tb`, `rho` | PubChem: HSDB/ICSC |
| `dfH`, `dfG`, `Sm0`, `Cpm0`, `dHr`, `dSr`, `dGr`, `lgKr` | CODATA/NBS/Burcat |
| `Qval`, `Bnuc`, `Ma` | AME2020 |
| `Thalf` | NUBASE2020 |
| `IE` | NIST ASD |
| `pvap` | Antoine, NIST WebBook |
| `Kb`, `Kf` | Atkins |
| `AE` | Trost 1991 |

The values of these functions are not validated by the Rechner tests; the tests only check that the functions are
registered. Their methods belong to the Elemental Calculator module.

---

## Known limitations

1. **No uncertainty propagation in calculation lines and formula cards.** Only the fit tool reports uncertainties.
2. **Integral without error estimate.** Oscillating integrands on infinite intervals and endpoint singularities can
   give wrong results without a warning (section 11).
3. **Fixed derivative step** of at least 10⁻³; inaccurate for functions that vary on smaller scales, undefined near
   domain boundaries (section 11).
4. **Temperature differences** converted with `->` to °C or °F are shifted by the offset (section 2).
5. **Units are lost** through `integral`, `deriv`, `nsolve`, `sum(expr, …)`, `polyfit` and matrix entries.
6. **Linearised fits are unweighted**; Lineweaver–Burk in particular is biased. Use the direct mode for reporting
   (section 9).
7. **First-order uncertainties** in the fit tool; asymmetric intervals for A, a are reported as symmetric.
8. **No convergence status** from the Levenberg–Marquardt routines in the fit tool and in graph regression rows.
9. **Fit uncertainties are not checked against an independent reference** in the tests.
10. **Graph regression rows** (`y1 ~ …`) report R² only, no uncertainty.
11. **Numerical root finding is not exhaustive**: formula cards search 10⁻¹⁵ … 10¹⁵; calculation lines show at most 12
    numerical solutions; nonlinear systems use 35 starts and show at most 8 solutions.
12. **Formula-card check tolerance** is 10⁻³ relative.
13. **Chemistry equations use concentrations, not activities**; `ch_pOH` assumes 25 °C; the hardness-to-strength
    conversion uses a rule-of-thumb factor.
14. **Constants are used without their uncertainty**; five exact derived constants are stored to 10 significant
    digits.
15. **Display precision** is limited (5 digits for cards and `\labval`); in the report, fit values with |value| ≥ 10⁵
    or < 10⁻³ are printed with 4 significant digits regardless of their uncertainty.
16. **`rand` is unseeded**; results using it are not reproducible.
17. **Report bundles** record the Folio Lab and module versions and the calculation request, but no source-file
    hashes (the Rechner has no source files).
