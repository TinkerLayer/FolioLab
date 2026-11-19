# Rechner: methods and validation

This document describes what the Rechner (Calculator) module computes: unit conversion, constants, the equation
library, formula cards, equation and system solving, statistics, the fit tool, graphs, calculus, complex numbers and
matrices. Every default and limit below is taken from the code in `modules/rechner/rechner/` and
`sdk/python/labcalc/`. Every reference is given exactly as it appears in the code. Where the code cites nothing, this
is stated as "no external reference; standard textbook method". Each section ends with the tests that check it.

For how to use the page, see the [module README](../../modules/rechner/README.md).

## How to cite results from this module

State the software and the module version:

> Calculated with Folio Lab 0.4.0, module Rechner 1.5.0.

- The Folio Lab version is `version` in the top-level `package.json`.
- The module version is `version` in `modules/rechner/module.json` (`"1.4.0"`). It is identical to `__version__` in
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
15. [Materials database and lookup functions](#15-materials-database-and-lookup-functions)
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
| Formula card on the page | 5 |
| Table of quantities and `\labval` values in the report (`VALUE_DIGITS`) | 6 |
| R² in the report | 5 |
| Regression and fit parameters in the report | value ± u: u to 2 significant digits, value to the same decimal place; without u 6 digits (see [section 9](#9-fit-tool)) |

Report the number with the precision your input data support, not the displayed digits.

**Not defined.** A NaN result (outside the domain, e.g. `sqrt(-1)` without complex mode) is shown as "nicht definiert"
/ "not defined"; ±∞ as ±∞. Before 1.4.0 the report renderer raised an error on these values.

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
| °dH | 10/56.077 = 0.1783263 mmol/L | German hardness, 10 mg CaO/L; M(CaO) = 40.078 + 15.999 g/mol |
| °fH | 10/100.086 = 0.0999141 mmol/L | French hardness, 10 mg CaCO₃/L; M(CaCO₃) = 40.078 + 12.011 + 3·15.999 g/mol |
| °C | K with offset 273.15 | |
| °F | factor 5/9 K, offset 459.67·5/9 | |

**Temperature.** An offset applies only when the unit stands alone. `20 °C` is 293.15 K. In compound units
(`°C/min`, `J/(kg·°C)`) the offset is dropped and the unit is a difference. A value can be read as a difference
explicitly (`diff=True` in the code); `10 °C` as a difference is 10 K.

**Temperature differences with `->`.** Since 1.4.0 a conversion to °C or °F decides whether the expression is an
absolute temperature or a difference. Each term gets a weight: a temperature quantity or `T0` counts 1, a
temperature-difference quantity counts 0, sums add the weights, a product with a number scales it. Weight 0 (e.g.
`T2 - T1`) is converted as a difference, without the offset, and shown as `Δ°C`/`Δ°F` with a note. Weight 1 (e.g.
`(T1 + T2)/2`) is converted with the offset. Any other weight is converted as a temperature, with a note that a
difference is written `-> Δ°C`. The target can be given as a difference explicitly with the prefix `Δ`, `Delta` or
`delta` (`-> Δ°F`). The old behaviour (always with offset) is what `-> °C` does for an absolute temperature.

**Scales.** pH, dB, NTU, FNU, FAU and AU are scales. They convert only to themselves. `pH` is the scale, not
picohenry.

**Kinds of quantity.** About 90 kinds (velocity, pressure, concentration …) each have a dimension and a list of
display units. `auto_unit` picks a readable unit; temperatures between 200 K and 2000 K are shown in °C.

**Units through functions.** Units propagate through arithmetic, powers and functions such as `sqrt`, `mean`, `std`,
`sum`, `sort`, `cumsum` and `diff`. `var` gives the unit squared. Since 1.4.0 (`dims_of` in
`sdk/python/labcalc/expr.py`):

| Function | Unit of the result |
|---|---|
| `integral(f, x, a, b)` | unit of f × unit of x (x from the limits) |
| `deriv(f, x, x0, n)` | unit of f / (unit of x)ⁿ |
| `nsolve(eq, x, start)` | from the start value; otherwise solved from the equation (as in [section 6](#6-equations-in-calculation-lines)) |
| `sum(expr, k, a, b)` | unit of expr; `prod`: unit to the power of the number of factors |
| list, matrix literal | common unit of the elements; mixed units: unknown |
| `inv`, `det`, `dot`, `kron`, `cross`, `linsolve`, `trace`, `eig`, `svd`, `norm`, `transpose` | from the units of the operands |
| `polyfit`, `polyval`, `roots`, `linreg` (outside calculation lines) | no unit if all inputs have none, otherwise unknown |

If the unit cannot be determined but quantities with units occur, the result is shown with the unit **`?`** and a
note ("Einheit unbekannt: …"); before 1.4.0 such results were shown without a unit, i.e. as if dimensionless.
A derived SI unit that matches a kind of quantity is shown by its coherent name (`J/(mol·K)` instead of
`m²·kg/(s²·K·mol)`).

**Reference.** No external reference; standard textbook method. The value of u and Da is the CODATA 2022 atomic mass
constant (see [section 3](#3-constants)). Water hardness: definitions of °dH and °fH by mass of CaO and CaCO₃ per
litre; molar masses from the IUPAC standard atomic weights as used in the code (40.078, 12.011, 15.999).

**Limitations.**
- The difference/absolute decision for `->` uses kinds of quantity; a plain number in K (no kind) counts as an
  absolute temperature. Use `-> Δ°C` to force a difference.
- Matrix entries carry one common unit; matrices with mixed units get `?`.

**Validation.**

| Test | Checks |
|---|---|
| `modules/rechner/tests/test_rechner.py::Units::test_parse` | 72 km/h = 20 m/s; 1 N/mm² = 10⁶ Pa; 20 °C = 293.15 K; 10 °C as difference = 10 K; 1 L/(mol·cm) = 0.1 m²/mol; 1 kWh = 3.6·10⁶ J |
| `modules/rechner/tests/test_rechner.py::Units::test_kinds` | 2.5·10⁸ Pa is shown in MPa; kg·m/s² is shown as N |
| `sdk/python/tests/test_units.py::UnitsU01Test::test_conversions` | e.g. 760 Torr = 1 atm, 1 °dH = 10/56.077 mmol/L, 1 °fH = 10/100.086 mmol/L, 1 mTorr = 0.133322 Pa (5 places, relative) |
| `sdk/python/tests/test_numerics.py::ExactConstants::test_hardness_units` | °dH and °fH from the molar masses (10 places) |
| `sdk/python/tests/test_numerics.py::UnitsThroughFunctions::test_calculus_keeps_units` | ∫v dx over [0, t] in m; deriv in m/s; sum; inv in 1/s; mixed list unknown; var in m²; nsolve unit from the equation |
| `sdk/python/tests/test_numerics.py::UnitsThroughFunctions::test_delta_syntax` | `Δ°C`, `Delta °F` recognised; 10 K as °F difference = 18 |
| `modules/rechner/tests/test_science.py::TemperatureDifference` | T2 − T1 (10 K) → 18 Δ°F and 10 Δ°C; (T1 + T2)/2 → 25 °C; `-> Δ°F` forces a difference |
| `modules/rechner/tests/test_science.py::UnitsThroughFunctions` | integral → m, deriv → m, sum → m/s, `[v, t]` → `?` with a note, `Rgas*298.15` → J/(mol·K) |
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
| `hbar` | h/(2π) = 1.0545718176461565·10⁻³⁴ | J·s | codata2022 | yes (computed in double precision) |
| `kB` | 1.380649·10⁻²³ | J/K | si2019 | yes |
| `NA` | 6.02214076·10²³ | 1/mol | si2019 | yes |
| `Rgas` | N_A·k = 8.31446261815324 | J/(mol·K) | codata2022 | yes (computed in double precision) |
| `G_grav` | 6.67430·10⁻¹¹ | m³/(kg·s²) | codata2022 | no, rel. u 2.2·10⁻⁵ |
| `eps0` | 8.8541878188·10⁻¹² | F/m | codata2022 | no |
| `mu0` | 1.25663706127·10⁻⁶ | N/A² | codata2022 | no |
| `q_e` | 1.602176634·10⁻¹⁹ | C | si2019 | yes |
| `m_e` | 9.1093837139·10⁻³¹ | kg | codata2022 | no |
| `m_p` | 1.67262192595·10⁻²⁷ | kg | codata2022 | no |
| `m_n` | 1.67492750056·10⁻²⁷ | kg | codata2022 | no |
| `m_u` | 1.66053906892·10⁻²⁷ | kg | codata2022 | no |
| `sigma_SB` | 2π⁵k⁴/(15h³c²) = 5.6703744191844314·10⁻⁸ | W/(m²·K⁴) | codata2022 | yes (computed in double precision) |
| `F_c` | N_A·e = 96485.33212331001 | C/mol | codata2022 | yes (computed in double precision) |
| `T0` | 273.15 | K | si2019 | yes |
| `p_n` | 101325 | Pa | codata2022 | yes |
| `p_std` | 10⁵ | Pa | greenbook | yes |
| `c_std` | 1000 | mol/m³ | greenbook | yes |
| `b_std` | 1 | mol/kg | greenbook | yes |
| `MPa1` | 10⁶ | Pa | si2019 | yes |
| `b_wien` | hc/(k·x), x = 5(1 − e⁻ˣ) = 4.965114231744276 (Newton) → 2.8977719551851722·10⁻³ | m·K | codata2022 | yes (computed in double precision) |

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

**Exact derived constants.** Since 1.4.0 `hbar`, `Rgas`, `sigma_SB`, `F_c` and `b_wien` are computed from the
defining constants h, c, k, N_A and e (SI 2019) in full double precision (`units.py`: `HBAR`, `R_GAS`, `FARADAY`,
`SIGMA_SB`, `WIEN_B`). Before, they were stored truncated to 10 significant digits (relative error up to about
10⁻¹⁰). `labcalc.fitting` uses the same R. The CODATA 2022 tables print these values to 10 digits; the computed
values agree with them to the last printed digit (tested).

**Limitations.** Other SDK modules (`chem.R_GAS`, `kinetics.R`, `gas.R`, `redox.F`) still use the 10-digit values;
they serve the Elemental Calculator and were not changed here.

**Validation.**

| Test | Checks |
|---|---|
| `modules/rechner/tests/test_rechner.py::Chemistry::test_codata_2022` | ε₀ = 8.8541878188·10⁻¹² and mₑ = 9.1093837139·10⁻³¹ exactly; R = N_A·k (8 places); F = N_A·e (4 places) |
| `modules/rechner/tests/test_rechner.py::Chemistry::test_every_equation_and_constant_sourced` | every constant has a complete source record |
| `sdk/python/tests/test_numerics.py::ExactConstants::test_derived_constants` | ħ = h/2π, R = N_A·k, F = N_A·e (15 places, relative), σ formula (14 places), x of Wien's law solves x = 5(1 − e⁻ˣ); all five agree with the CODATA 2022 10-digit values to 10⁻⁹ |

---

## 4. Equation library

**What is computed.** The library (`modules/rechner/rechner/library.py`) holds 365 equations (the count in `module.json` is checked by a test). Each has an ID, a field,
a topic, the equation `lhs = rhs`, its variables with a kind of quantity, and a source.

| Field | Equations |
|---|---|
| Materials science (Werkstoffkunde) | 83 |
| Chemistry | 77 |
| Strength of materials | 56 |
| Mechanics | 49 |
| Heat | 24 |
| Electrical engineering | 22 |
| Optics and microscopy | 18 |
| Fluid mechanics | 16 |
| Geometry | 14 |
| Mathematics | 6 |

129 equations are marked *auto*: they are general laws used by *derive* (see [section 5](#5-formula-cards-derive-and-search)).

**How the source is assigned.** In order of priority: the `src` argument of the equation, then `SRC_OVERRIDE` (per
equation), then `SECTION_SRC` (per field and topic). Book sources get the note "Stichwort: <English name of the
equation>", which names the topic under which the equation is found. No page numbers are given; the code states that
page numbers are only given where they were checked.

| Source key | Equations | Used for |
|---|---|---|
| halliday | 86 | mechanics, heat, gases, electrical engineering |
| callister | 35 | true stress and strain, notch, rule of mixtures, Hall–Petch; most of materials science (crystallography, defects, phases, polymers, electrical properties, corrosion) |
| gross2 | 34 | stress and strain, bending, torsion and buckling, vessels; thermal stress |
| harris | 26 | concentration, acids and bases, solubility, lab practice |
| atkins | 25 | chemical thermodynamics, colligative properties, kinetics |
| bronstein | 20 | geometry, mathematics |
| white | 16 | fluid mechanics |
| hecht | 11 | light, lenses |
| dowling | 10 | fatigue, creep, deformation laws |
| krane | 9 | radioactivity |
| greenbook | 8 | amount of substance and concentration |
| bard | 8 | electrochemistry; Faraday corrosion |
| iso6892 | 7 | tensile test |
| anderson | 7 | fracture mechanics |
| murphy | 7 | imaging and microscopy |
| porter | 7 | diffusion, nucleation, phase transformations |
| bergman | 6 | heat transfer |
| daniel2006 | 6 | composites: laminate stiffness, Tsai–Hill |
| ashby | 5 | performance indices (materials selection) |
| weibull1951 | 3 | Weibull distribution and size effect |
| iso178, halpin1976, astmg102, andrews1965 | 2 each | three-point bending; Halpin–Tsai; corrosion rate; Ms and Ac3 |
| iso6507, iso6506, iso18265 | 1 each | Vickers, Brinell, tensile strength from hardness |
| sheldon2007, jimenez2011, constable2002 | 1 each | E factor, process mass intensity, reaction mass efficiency |
| cullity, avrami1939, hollomon1945, larsonmiller1952, basquin1910, miner1945, kingery1955, wlf1955, fox1956, mark2007, treloar1975, sze2007, pilling1923, en1011_2, hollomonjaffe1945 | 1 each | Scherrer, Avrami, Hollomon flow curve, Larson–Miller, Basquin, Miner, thermal shock, WLF, Fox, polymer data, rubber elasticity, semiconductors, Pilling–Bedworth, carbon equivalent, tempering parameter |

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
- iso6892: ISO. ISO 6892-1:2019 Metallic materials – Tensile testing – Part 1: Method of test at room temperature.
  International Organization for Standardization, 2019. (German title in the note.)
- iso178: ISO. ISO 178:2019 Plastics – Determination of flexural properties. 2019.
- iso6507: ISO. ISO 6507-1:2018 Metallic materials – Vickers hardness test – Part 1: Test method. 2018.
- iso6506: ISO. ISO 6506-1:2014 Metallic materials – Brinell hardness test – Part 1: Test method. 2014.
- iso18265: ISO. ISO 18265:2013 Metallic materials – Conversion of hardness values. 2013. Code note: the factor 3.3
  in the Rechner is a rule of thumb, not checked against the tables of the standard; a reliable conversion needs the
  tables.

References of the materials-science area and the materials database (DOIs checked against Crossref on 18 Nov 2026;
page ranges only where Crossref states them):
- dowling: Dowling, N. E. Mechanical Behavior of Materials. Pearson, 2013, 4th edition.
- daniel2006: Daniel, I. M.; Ishai, O. Engineering Mechanics of Composite Materials. Oxford University Press, 2006,
  2nd edition.
- ashby: Ashby, M. F. Materials Selection in Mechanical Design. Butterworth-Heinemann, 2017, 5th edition.
- cullity: Cullity, B. D.; Stock, S. R. Elements of X-Ray Diffraction. Pearson, 2014, 3rd edition.
- weibull1951: Weibull, W. A statistical distribution function of wide applicability. J. Appl. Mech. 18 (1951)
  293–297, doi:10.1115/1.4010337.
- halpin1976: Halpin, J. C.; Kardos, J. L. The Halpin-Tsai equations: a review. Polym. Eng. Sci. 16 (1976) 344–352,
  doi:10.1002/pen.760160512.
- astmg102: ASTM G102-89 (reapproved 2015), Calculation of Corrosion Rates from Electrochemical Measurements.
- andrews1965: Andrews, K. W. Empirical formulae for the calculation of some transformation temperatures. J. Iron
  Steel Inst. 203 (1965).
- avrami1939: Avrami, M. Kinetics of phase change I. J. Chem. Phys. 7 (1939) 1103–1112, doi:10.1063/1.1750380.
- hollomon1945: Hollomon, J. H. Tensile deformation. Trans. AIME 162 (1945).
- larsonmiller1952: Larson, F. R.; Miller, J. A time-temperature relationship for rupture and creep stresses. Trans.
  ASME 74 (1952).
- basquin1910: Basquin, O. H. The exponential law of endurance tests. Proc. ASTM 10 (1910).
- miner1945: Miner, M. A. Cumulative damage in fatigue. J. Appl. Mech. 12 (1945) A159–A164, doi:10.1115/1.4009458.
- kingery1955: Kingery, W. D. Factors affecting thermal stress resistance of ceramic materials. J. Am. Ceram. Soc. 38
  (1955) 3–15, doi:10.1111/j.1151-2916.1955.tb14545.x.
- wlf1955: Williams, M. L.; Landel, R. F.; Ferry, J. D. J. Am. Chem. Soc. 77 (1955) 3701–3707,
  doi:10.1021/ja01619a008.
- fox1956: Fox, T. G. Bull. Am. Phys. Soc. 1 (1956).
- mark2007: Mark, J. E. (ed.) Physical Properties of Polymers Handbook. Springer, 2007, doi:10.1007/978-0-387-69002-5.
- treloar1975: Treloar, L. R. G. The Physics of Rubber Elasticity. Oxford University Press, 1975.
- sze2007: Sze, S. M.; Ng, K. K. Physics of Semiconductor Devices. Wiley, 2007, doi:10.1002/0470068329.
- pilling1923: Pilling, N. B.; Bedworth, R. E. J. Inst. Metals 29 (1923).
- en1011_2: EN 1011-2:2001, welding of ferritic steels (carbon equivalent CE, IIW).
- hollomonjaffe1945: Hollomon, J. H.; Jaffe, L. D. Time-temperature relations in tempering steel. Trans. AIME 162
  (1945).
- crc97: Haynes, W. M. (ed.) CRC Handbook of Chemistry and Physics. CRC Press, 2016, 97th edition (properties of the
  elements).
- kittel: Kittel, C. Introduction to Solid State Physics. Wiley, 2005, 8th edition (structures, lattice parameters).
- hopcroft2010: Hopcroft, M. A.; Nix, W. D.; Kenny, T. W. What is the Young's modulus of silicon? J. Microelectromech.
  Syst. 19 (2010) 229–238, doi:10.1109/JMEMS.2009.2039697.
- jain2013 and dejong2015 (optional Materials Project part only): APL Mater. 1 (2013) 011002,
  doi:10.1063/1.4812323; Sci. Data 2 (2015) 150009, doi:10.1038/sdata.2015.9.

Since 1.4.0 the ISO titles are the English titles; the German title is kept in each `note`.

Further entries added in 1.4.0 (not used by a library equation):
- trost1991: Trost, Barry M. "The atom economy – a search for synthetic efficiency". Science 254(5037), 1471-1477
  (1991). doi:10.1126/science.1962206. Cited by the green-chemistry metrics (`labcalc.reaction_setup.METRIC_REFS`) and
  the `AE` function.
- press2007: Press, W. H.; Teukolsky, S. A.; Vetterling, W. T.; Flannery, B. P. Numerical Recipes: The Art of
  Scientific Computing. Cambridge University Press, 2007, 3rd edition. Cited for the continued fraction of the
  incomplete beta function (§6.4) and the derivative step selection (§5.7).
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
- `ch_pOH` uses `pH + pOH = 14`; its title says 25 °C and its note says that 14 is pKw of water at 25 °C. Since 1.4.0`n  `ch_pOH_pKw` (`pH + pOH = pKw`) takes pKw as a variable for other temperatures. Other acid–base equations take pKw as a variable; its label states 14.00 at
  25 °C.
- `ch_weak_acid` is the approximation `pH = 0.5·(pKa − log10(c_a/c°))`. Its note says it holds for c/Ka > 100.
  `ch_weak_acid_exact` solves Ka = x²/(c − x) and neglects water autoprotolysis (note: valid up to about pH 6). The
  same holds for the weak-base pair.
- `ch_T_switch`, `ch_vanthoff` and `ch_kirchhoff` assume ΔH, ΔS or ΔCp constant over the range (stated in the notes).
- `hard_Rm` converts hardness to tensile strength with the factor 3.3. Since 1.4.0 its title says "rule of thumb, ≈" and`n  its note says that the factor is not checked against the tables of ISO 18265 and is indicative only for unalloyed and`n  low-alloy steels of medium strength. Not checked: the factor was not compared with the ISO 18265 tables (no access`n  offline).

**Validation.**

| Test | Checks |
|---|---|
| `modules/rechner/tests/test_rechner.py::Library::test_size` | at least 200 equations, unique IDs |`n| `modules/rechner/tests/test_science.py::ModuleMeta::test_equation_count_in_description` | the count in `module.json` (DE and EN) equals the number of equations |`n| `modules/rechner/tests/test_science.py::ModuleMeta::test_poh_states_25_degrees` | `ch_pOH` title states 25 °C; `ch_pOH_pKw` uses pKw; `hard_Rm` note says "not checked" |
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
   |lhs − rhs| ≤ 10⁻⁷ · max(|lhs|, |rhs|). Since 1.4.0 touching roots (double roots, no sign change) are also
   searched: at each local minimum of |lhs − rhs| on the grid with the same sign on both neighbours and at most 0.2
   times their value, |f| is minimised by golden-section search and polished by Newton steps on f′ (the routines of
   `labcalc.solve`); the root is accepted if |lhs − rhs| ≤ 10⁻¹⁰ · max(|lhs|, |rhs|) (`TOUCH_RTOL`). Positive kinds
   keep only roots > 0.
4. **Choice of root.** The first positive root is taken. For angles, a root in [0, π/2] is preferred. The user can
   choose another root.
5. **Check.** If all variables have values, the card checks the equation. Relative difference
   rel = |lhs − rhs| / max(|lhs|, |rhs|). Since 1.4.0 the tolerance comes from the rounding of the inputs: each value
   typed as a decimal number has a relative rounding δᵢ = half a unit of its last digit / |value| (`2.50` → 0.002;
   integers without a decimal point and expressions count as exact). δᵢ is propagated to first order,
   tol = Σ |∂(lhs − rhs)/∂xᵢ| · |xᵢ| · δᵢ / max(|lhs|, |rhs|), with forward differences (step 10⁻⁶ · |xᵢ|), and
   bounded to [10⁻⁹, 10⁻²] (`CHECK_RTOL_MIN`, `CHECK_RTOL_MAX`). The card is "OK" if rel ≤ tol and shows both numbers.
   Before 1.4.0 the tolerance was a fixed 10⁻³.

**Derive.** Equations marked *auto* compute further values from the sheet variables. Each step needs an equation with
exactly one missing variable. At most 5 rounds and 80 derived values.

**Search for missing values** (*Gesucht …*) lists equations that yield a quantity, sorted by the number of missing
values.

**Reference.** No external reference; standard textbook method (isolation, grid scan and bisection).

**Units and uncertainty.** All values are in SI during calculation. The result is shown in a selectable unit with 5
significant digits. No uncertainty is propagated.

**Limitations.**
- The numerical search finds roots where the residual changes sign on the grid or has a pronounced local minimum of
  |f| between grid points. Roots outside 10⁻¹⁵ … 10¹⁵ in magnitude, and touching roots that the grid does not
  resolve (two roots within one grid step), are missed.
- The automatic root choice (first positive root) may not be the physically relevant one. Check the offered roots.
- The check tolerance assumes that the typed digits are the precision of the values. Values taken from other cards
  or derived values count as exact; values with a known measurement uncertainty are not used.

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
| `modules/rechner/tests/test_science.py::CardCheck::test_rounding_of` | `2.50` → 0.002; `1.5e3` → 50/1500; `7` exact |
| `modules/rechner/tests/test_science.py::CardCheck::test_tolerance_from_input_rounding` | F = m·a with 10 N, 2.0 kg, 5.01 m/s²: tolerance 0.026 capped at 10⁻² (hand calculation), 0.2 % passes; 10, 2, 6 (exact): tolerance 10⁻⁹, fails; 10, 2, 5 passes |
| `modules/rechner/tests/test_science.py::CardCheck::test_tolerance_scales_with_digits` | 5-digit inputs: tolerance < 10⁻⁴, 0.02 % difference fails |
| `modules/rechner/tests/test_science.py::TouchingRoots` | s = v0·t + a·t²/2 with s = −4 m, v0 = −4 m/s, a = 2 m/s²: double root t = 2 s (6 places), found once |

---

## 6. Equations in calculation lines

**What is computed.** A calculation line with `=` and exactly one unknown is solved for it
(`sdk/python/labcalc/solve.py`). Conditions after a comma (`, x > 0`) filter the solutions.

**Polynomials** (up to degree 24).
- Coefficients are kept as exact fractions where they are rational.
- Degree 1 and 2 are solved exactly; the quadratic result is shown in surd form.
- Rational roots are detected and divided out. Each numerical root is approximated by a fraction
  (`Fraction.limit_denominator`) and accepted only if the polynomial is exactly 0 there (fraction arithmetic). Since
  1.4.0 the denominator bound follows the rational root theorem: for integer coefficients the denominator of a root
  p/q in lowest terms divides the leading coefficient, so the bound is max(1000, |leading coefficient after scaling to
  integers|), at most 10¹². Before it was a fixed 1000. A remaining quadratic is solved exactly.
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
- A rational root is found exactly only if its floating-point approximation is close enough for
  `limit_denominator` to recover it; for leading coefficients above 10¹² the bound is capped and such roots are shown
  numerically.

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
| `sdk/python/tests/test_numerics.py::RationalRoots::test_denominator_above_1000` | (1001x − 1)(x² − 2)(x − 3) = 0: exact roots 1/1001 and 3, two roots ±√2 (hand expansion) |

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

**Data preparation.** Only pairs with finite x and y are used. For the linearised forms, points with y ≤ 0 (exp),
x ≤ 0 or y ≤ 0 (pow, mm), k ≤ 0 or T ≤ 0 (arrh), or x ≤ 0 (log) are removed with a note. Since 1.4.0 the direct mode
uses every point at which the model itself is defined: exp and mm all points, pow x > 0, arrh T > 0 K. Points that
were only invalid for the linearisation (e.g. y ≤ 0 for exp) are kept; the start values come from the linearisable
points, with the note "Startwerte aus den N linearisierbaren Punkten; angepasst an alle M Punkte". Fewer pairs than
parameters is an error. Values are used in the units of the columns, not SI.

**Default mode.** New fit rows on the page start in the direct mode since 1.4.0. The linearised mode stays
selectable; `labcalc.fitting.fit()` keeps `mode="lin"` as its default for existing callers.

**Linear models** (lin, prop, poly2, poly3, log). Ordinary least squares by `numpy.linalg.lstsq`. Covariance:
`cov = s²·(AᵀA)⁻¹` with `s² = SSE/(n − p)`. Linearised and direct mode give the same result for these models.

**Linearised mode** (exp, pow, arrh, mm). An unweighted straight line `Y = c + s·X` is fitted to the transformed
points as above. The parameters are calculated back:
- exp, pow: a = e^c, b = s
- arrh: A = e^c, Ea = −s·R/1000 in kJ/mol, with R = N_A·k = 8.31446261815324 J/(mol·K) (exact, see
  [section 3](#3-constants))
- mm: Vmax = 1/c, Km = s/c. This is the Lineweaver–Burk (double-reciprocal) plot; the result carries
  `method: "Lineweaver–Burk"`, the plot title names it and a note says that it is biased because the reciprocals give
  small S and v a large weight, and recommends the direct fit.

The covariance is propagated to first order: `cov_p = G·cov·Gᵀ`, where G is the Jacobian of the back-transformation.
The result carries `u_method: "first_order_back_transform"` and a note "Unsicherheit … aus der Geraden
zurückgerechnet (erste Ordnung, symmetrisch)"; the report adds the same remark.

**Direct mode** (exp, pow, arrh, mm). Least squares in the original y with the Levenberg–Marquardt method:
- Start: the linearised result. Internal parameters ln a (exp, pow), ln A and −Ea/R (arrh), Vmax and Km (mm).
- Forward-difference Jacobian with step 10⁻⁷ · max(1, |q|).
- λ starts at 10⁻³, is divided by 10 after a successful step and multiplied by 10 after a failed one (up to 16 tries
  per iteration). At most 200 iterations. Stop when the decrease in SSE is ≤ 10⁻¹⁵ × SSE.
- Convergence (since 1.4.0, `fitting.converged`): at the final parameters the residual vector r must be (nearly)
  orthogonal to every column of the Jacobian, |Jᵢᵀr| ≤ GTOL·‖Jᵢ‖·‖r‖ with GTOL = 10⁻⁴ (the gradient test of MINPACK),
  or ‖r‖² ≤ 10⁻²⁴·‖y‖² (exact fit). The result carries `converged`; if false, a note says the result and its
  uncertainties are unreliable, and the report repeats it.
- Covariance: `(SSE/(n − p))·pinv(JᵀJ)` at the solution, propagated to the reported parameters to first order
  (`u_method: "jacobian"` for mm, `"jacobian_first_order"` for exp, pow, arrh, whose internal parameters are ln a
  or ln A).

**Arrhenius temperature.** x must be a temperature. °C and °F are converted to K; x without a unit is read as K
(with a note). A has the unit of k; Ea is in kJ/mol.

**Reported quantities.**
- Each parameter: value, standard uncertainty `u = √cov_ii`, and `ci = t·u` with t the two-sided 95 % Student-t
  quantile for n − p degrees of freedom.
- R² = 1 − SSE/SST in the original y, with SST = Σ(y − ȳ)² for models with an intercept. For the model through the
  origin (prop) SST = Σy² (uncentred) since 1.4.0, with a note and `r2_centred: false`; the centred value is not
  meaningful without an intercept and can be negative.
- `r2_lin`: R² of the straight line in the linearised coordinates (linearised models only).
- Residual standard deviation `s = √(SSE/(n − p))`.
- If n = p: no uncertainty, with a note.

**Student-t quantile** (`sdk/python/labcalc/stats.py`). Bisection on the t distribution function, which is
computed from the regularised incomplete beta function by continued fraction. Range ±1000, stop at an interval
below 10⁻¹². Reference as cited in the code: Press, W. H.; Teukolsky, S. A.; Vetterling, W. T.; Flannery, B. P.
Numerical Recipes: The Art of Scientific Computing, 3rd ed., Cambridge University Press 2007, §6.4 (`press2007`). The
quantile is exact to the bisection tolerance; SciPy is not used at run time (compared with `scipy.stats.t.ppf` in the
tests).

**What the user sees.** The page shows value ± standard uncertainty u; the 95 % interval is in the tooltip. The
report states: "Values are given ± standard uncertainty; 95 % confidence with t = …".

**Report precision.** u is rounded to 2 significant digits and the value to the same decimal place. Since 1.4.0 this
also holds for |value| ≥ 10⁵ or < 10⁻³: value and u are then printed with a common power of ten,
`(1.23457 ± 0.00023)·10⁷`. Before, such values were printed with 4 significant digits regardless of u. Without u
the value has 6 significant digits.

**Units of parameters.** Built from the column units: lin m in y/x, b in y; prop m in y/x; poly coefficients in
y/xᵏ; log a and b in y; exp a in y, b in 1/x; pow a and b without unit (a note says that a holds for x and y in the
column units); arrh A in y, Ea in kJ/mol; mm Vmax in y, Km in x. For log, a is y at x = 1 in the unit of x; since
1.4.0 a note states that unit and the result carries `a_xunit`.

**Graph fits use all values.** A fit on a dataset uses every non-excluded row in the optional x range, not the thinned
points drawn on the screen.

**Reference.** No external reference for the fitting algorithms; standard textbook method (ordinary least squares,
Levenberg–Marquardt, first-order error propagation). The convergence test follows the gradient criterion of MINPACK
(no page reference given). The t quantile cites Press et al. 2007, §6.4.

**Limitations.**
- Linearised fits are unweighted. Transforming y (ln y, 1/v) changes the error structure. Lineweaver–Burk (mm,
  linearised) is known to weight low-concentration points heavily; the result is labelled and a note recommends the
  direct mode.
- Uncertainties are first-order (linear) approximations. For A in Arrhenius and a in exp/pow, the true interval is
  asymmetric; the reported u is symmetric (labelled "erste Ordnung").
- The convergence test is a necessary condition for a local minimum; it does not prove a global one.
- Uncertainties assume independent, equally distributed errors in y and no errors in x.

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
| `sdk/python/tests/test_numerics.py::Fitting::test_line_uncertainty_analytic` | straight line, 6 points: u(m) = s/√Sxx and u(b) = s·√(1/n + x̄²/Sxx) (textbook formulas, 12 places) |
| `sdk/python/tests/test_numerics.py::Fitting::test_direct_uses_all_points_and_matches_curve_fit` | exp, 8 points, one y < 0: n = 8, converged; parameters equal `scipy.optimize.curve_fit` (rel. 10⁻⁶), u equal √diag(cov) of curve_fit (rel. 10⁻⁴) |
| `sdk/python/tests/test_numerics.py::Fitting::test_r2_through_origin_uncentred` | prop: m = Σxy/Σx², R² = 1 − SSE/Σy² (12 places) |
| `sdk/python/tests/test_numerics.py::Fitting::test_convergence_criterion` | residual orthogonal to J: converged; residual along a column: not converged |
| `sdk/python/tests/test_numerics.py::Fitting::test_lineweaver_burk_labelled` | mm linearised: method Lineweaver–Burk, first-order back-transform, bias note |
| `sdk/python/tests/test_numerics.py::Fitting::test_log_model_states_unit_of_x` | log with x in mm: `a_xunit` = mm and note "x = 1 mm" |
| `sdk/python/tests/test_numerics.py::Fitting::test_t_quantiles_against_scipy` | t(0.975, ν) for ν = 1, 2, 3, 5, 10, 30, 100 equals `scipy.stats.t.ppf` (9 places) |
| `modules/rechner/tests/test_science.py::ReportDigits` | `9.81234 ± 0.0123` → `9.812 \pm 0.012`; `12345678 ± 2345` → `(1.23457 \pm 0.00023)\cdot 10^{7}`; 6 digits without u |

The models poly3 and pow have no dedicated numerical test.

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
at most 200 iterations and 12 λ tries per iteration. The result with the smallest SSE is kept. Since 1.4.0 each
parameter also gets a standard uncertainty u = √diag(s²·pinv(JᵀJ)) from the Jacobian at the optimum
(s² = SSE/(n − p)) and a 95 % interval t·u with the Student-t quantile for n − p degrees of freedom; the page shows
"± u" with the interval in the tooltip, the report "value ± u" with the same remark as the fit tool. Convergence is
tested as in [section 9](#9-fit-tool); if it fails, the page and the report show a warning.

**Special points** on a clicked curve: roots by a 4000-point scan plus bisection; extrema by golden-section search (80
iterations); intersections and the y intercept. At most 60 points.

**Older plot format.** `modules/rechner/rechner/plots.py` contains an older fit (`/api/fit`) based on
`numpy.polyfit` with log-linearisation for exp, pow and log, R² only.

**Reference.** No external reference; standard textbook method.

**Limitations.**
- Regression-row uncertainties are first-order (Jacobian) values and assume independent, equal errors in y.
- Roots and extrema are found only where the scan resolves them; closely spaced roots can be missed.
- Implicit curves are approximate at the grid resolution.

**Validation.**

| Test | Checks |
|---|---|
| `modules/rechner/tests/test_rechner.py::Graph::test_large_dataset_thinned_and_fitted` | 200 000 points: fewer than 5000 sent as a line; at most 30 000 as points |
| `modules/rechner/tests/test_rechner.py::Graph::test_regression_and_poi` | table (0,1), (1,3), (2,5), (3,7) with `y1 ~ m x1 + b`: m = 2, b = 1 (6 places), R² = 1; roots of x² − 4: two, one at 2 (5 places) |
| `modules/rechner/tests/test_rechner.py::Graph::test_slider_implicit_value` | slider, implicit circle, ∫sin x from 0 to π = 2 (6 places) |
| `modules/rechner/tests/test_rechner.py::Graph::test_classify` | expression types are recognised |
| `modules/rechner/tests/test_science.py::GraphRegression::test_line_uncertainty` | `y1 ~ m x1 + b`, 6 points: u(m), u(b) equal the textbook formulas (7 places); t equals `scipy.stats.t.ppf(0.975, 4)`; ci = t·u; converged |
| `modules/rechner/tests/test_rechner.py::ConsoleAndPlots::test_analysis_and_fit` | roots of x² − 2: ±√2 (rel. 10⁻⁸); tan x on [−2, 2]: one root (poles excluded); x³ − 3x: max then min; older fit: k = 2, R² = 1, exp b = 1 (3 places) |

---

## 11. Integral, derivative, root finding, sum and product

Code: `sdk/python/labcalc/expr.py`.

**`integral(f, x, a, b)`** (since 1.4.0; `quad`, `quad_est`).
- Global adaptive Gauss–Kronrod rule G7/K15 with the node and weight constants of QUADPACK `qk15` (K15 is exact for
  polynomials up to degree 22, G7 up to degree 13; tested).
- Start: 16 equal subintervals. Error estimate per subinterval |K15 − G7|. While the total error estimate exceeds the
  goal max(10⁻¹⁰·|I|, 50·ε·∫|f|) (ε = machine epsilon), the subintervals with the largest error (up to 64 per round)
  are halved. At most 2000 subintervals. Global bisection as in QUADPACK QAG, without extrapolation (no QAGS ε
  algorithm).
- Infinite limits: substitution x = a + t/(1 − t), dx = dt/(1 − t)² over t in [0, 1] (the K15 nodes never touch
  t = 1). An integral from −∞ to ∞ is split at 0.
- If the goal is not reached and the error estimate exceeds 10⁻⁶·|I| (`QUAD_ACCEPT`), **no value is returned**: the
  line shows the error "Integral konvergiert numerisch nicht (Schätzwert …, geschätzter Fehler …)". Between the goal
  and that limit the value is returned with a note giving the estimated relative error.
- A non-finite integrand value at a node is an error.

**`deriv(f, x, x0[, n])`** (since 1.4.0; `deriv_est`). Orders 1 and 2.
- Step ladder hₖ = h_max·10^(−k/2), from h_max = 0.1·max(|x0|, 1) down to 10⁻⁹·min(|x0|, 1) (relative step, also for
  small |x0|).
- On each step: central difference with one Richardson step, D = (4·D(h/2) − D(h))/3. If a stencil point lies outside
  the domain (NaN), the one-sided second-order formula is used instead (forward, else backward), also with a
  Richardson step; so `deriv(sqrt(x), x, 1e-4)` gives 50.
- The step is chosen where two neighbouring estimates agree best (Ridders-type selection, Press et al. 2007, §5.7);
  the difference, but at least the round-off estimate 10·ε·max|f|/h (60·ε·max|f|/h² for n = 2), is the error
  estimate.
- If the left and right one-sided estimates at the chosen step differ by more than 10⁻³ relative and by more than
  100 times the error estimate (a kink, e.g. |x| at 0), their difference becomes the error estimate.
- A note is shown if the estimated relative error exceeds 10⁻⁶, or "keine verlässliche Fehlerschätzung (Funktion an
  der Stelle nicht glatt?)" if no estimate is possible.

**`nsolve(equation, x, start)`.** Newton's method from the start value (at most 100 iterations, tolerance 10⁻¹²).
If that fails, a sign-change scan over growing spans (1 to 10⁶, 401 points each) followed by bisection (tolerance
10⁻¹³, 200 iterations). With two start values the root is bracketed between them.

**`sum(expr, k, a, b)`, `prod(…)`.** Direct summation, at most 10⁶ terms. If b < a the result is 0 (sum) or 1
(product).

**Reference.** Gauss–Kronrod constants: QUADPACK `qk15` (Piessens, de Doncker-Kapenga, Überhuber, Kahaner, QUADPACK,
Springer 1983; not checked against the book offline: the constants were verified numerically by their polynomial
exactness). Derivative step selection: Press et al. 2007, §5.7 (`press2007`). Otherwise standard textbook methods.

**Units.** Since 1.4.0 the unit is carried: integral → unit of f × unit of x, deriv → unit of f / unit of xⁿ, nsolve →
unit of x, sum → unit of the terms (see [section 2](#2-units-and-conversion)).

**Changed results in 1.4.0** (old → new):
- ∫₁^∞ sin(x)/x dx: 2.293 (wrong, no warning) → error "konvergiert numerisch nicht" (true value 0.6247132564).
- ∫₀¹ 1/√x dx: 1.9946 → 1.99999999988.
- ∫₀¹ |x − 0.3| dx: 0.28999996 → 0.2899999999975.
- d/dx sin(1000x) at 0.001: 539.21 → 540.3023058680 (exact 1000·cos 1 = 540.3023058681398).
- d/dx √x at 10⁻⁴: not defined (NaN, report error) → 50.

**Limitations.**
- The integral does not extrapolate (no QAGS ε algorithm). Strong endpoint singularities such as 1/√x converge
  slowly and reach about 10⁻¹⁰ relative; oscillating integrands on infinite intervals are refused rather than
  computed. Split such integrals or use a finite limit.
- The error estimate |K15 − G7| is heuristic; it can be optimistic for integrands with features narrower than the
  start intervals that no node hits.
- The derivative is a numerical estimate; at kinks and discontinuities the value is the mean of both sides with a
  note.
- `nsolve` returns one root; which one depends on the start value.

**Validation.**

| Test | Checks |
|---|---|
| `modules/rechner/tests/test_rechner.py::Expressions::test_calculus` | ∫₀³ x² dx = 9 (9 places); ∫ e^(−x²) over (−∞, ∞) = √π (7 places); d/dx x³ at 2 = 12 (6 places); nsolve x² = 2 from 1: √2 (10 places); Σk² for k = 1…10 = 385 |
| `modules/rechner/tests/test_rechner.py::Graph::test_slider_implicit_value` | ∫₀^π sin x dx = 2 (6 places) |
| `sdk/python/tests/test_numerics.py::Integral::test_gauss_kronrod_constants` | K15 exact for x⁰ … x²², G7 for x⁰ … x¹² (14 places); weights sum to 2 |
| `sdk/python/tests/test_numerics.py::Integral::test_known_integrals` | ∫₀³x² = 9; Gauss integral √π; ∫₀^∞ e⁻ˣ sin x = 1/2; ∫₁^∞ x⁻² = 1; ∫₀¹ 1/√x = 2; ∫₀¹ \|x − 0.3\| = 0.29 (all to 10⁻⁸ relative, analytic) |
| `sdk/python/tests/test_numerics.py::Integral::test_against_scipy` | ∫₀² x ln x, ∫₀^∞ 1/(1 + x²), ∫₀¹⁰ cos² x equal `scipy.integrate.quad` (9 places) |
| `sdk/python/tests/test_numerics.py::Integral::test_oscillating_improper_integral_refused` | ∫₁^∞ sin x/x raises the non-convergence error; true value π/2 − Si(1) = 0.6247132564277136 (SciPy `sici`) |
| `sdk/python/tests/test_numerics.py::Integral::test_error_estimate` | ∫₀¹ eˣ = e − 1 (13 places), converged, error estimate < 10⁻¹² |
| `sdk/python/tests/test_numerics.py::Derivative::test_known_derivatives` | √x at 10⁻⁴: 50; sin(1000x) at 0.001: 1000·cos 1; x + 1 at 10⁻¹⁰: 1; x³ at 2: 12 (n = 1 and 2); eˣ at 0 (n = 2): 1; sin x at 10⁶: cos 10⁶ (analytic) |
| `sdk/python/tests/test_numerics.py::Derivative::test_one_sided_at_domain_boundary` | x^1.5 at 0: 0 (one-sided) |
| `sdk/python/tests/test_numerics.py::Derivative::test_kink_gets_note` | \|x\| at 0 gives a note |
| `sdk/python/tests/test_numerics.py::Derivative::test_render_not_defined` | NaN and ±∞ are rendered ("nicht definiert") instead of raising |

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

**Limitations.** A matrix carries one common unit (since 1.4.0 propagated through `inv`, `det`, `dot`, `linsolve` …,
see [section 2](#2-units-and-conversion)); entries with different units give the unit `?`. `rref` uses a fixed tolerance, so the rank of badly scaled matrices can
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

Since 1.4.0 `IE("Na", n)` is an energy (value in J, 1 eV = 1.602176634·10⁻¹⁹ J exactly), so `IE("Na") -> eV` shows
eV and `IE("Na")*NA -> kJ/mol` works. The old behaviour, a plain number in eV, is available as `IE_eV("Na", n)`. The
conversion factor eV → kJ/mol in `labcalc.ionization` is F/1000 with the exact F.

The values of these functions are not validated by the Rechner tests; the tests only check that the functions are
registered (and, for `IE`, its dimension and the eV/J factor: `sdk/python/tests/test_numerics.py::Ionization`). Their
methods belong to the Elemental Calculator module.

## 15. Materials database and lookup functions

**Data.** `sdk/python/labcalc/data/materials.json` (format `folio-materials/1`), read by `labcalc/materials.py`; the
Zugversuch reads the same file (its 88 comparison materials are the rows with `"zugversuch": true`, fields unchanged).
136 materials: metals and alloys 70, polymers 32, composites 8, ceramics 7, fibres 6, natural materials 6, glasses 4,
semiconductors 3. Each value is stored as `{"v", "u", "art", "min", "max", "q"}`: value in a readable unit, value kind
(`typ`, `min`, `max`, `mitte` = middle of a stated range, `unklar`), optional range, source (a key of
`labcalc.sources.REFS` or a source text such as a standard and product form). `value()` converts to SI with
`labcalc.units`. Pure elements fall back to the shared element data for ρ and Tm (PubChem). Entries and values not
compared against their source in this round carry `nicht_geprueft`; the picker shows ⚠ and the report keeps the note.
Nothing is derived inside the curated data (no K from E and ν); a missing property is an error that lists the
properties present.

**Names.** `find()` compares a normalised key (case, ß/ss, spaces, hyphens, dots, brackets ignored; "gamma"/"alpha" =
γ/α) against id, German and English name and aliases (designations such as 1.4301, AISI 304, X5CrNi18-10); a unique
partial match is accepted, several are refused with the candidates.

**Functions in calculation lines** (group "Werkstoffe", `labcalc/materials.py:register_calc_functions`):
`mat("name", "prop")` returns the SI quantity with its kind (`mat("S235JR", "Rp")` = 2.35·10⁸ Pa; `-> MPa` converts);
shortcuts `rho_mat`, `E_mat`, `G_mat`, `nu_mat`, `Rp_mat`, `Rm_mat`, `A_mat`, `KIc_mat`, `Tm_mat`, `Tg_mat`,
`alpha_mat`, `lambda_mat`, `cp_mat`, `rhoel_mat`, `Eg_mat`, `a_lat`, `c_lat`. Diffusion: `D_diff("C", "γ-Fe", T)` =
D₀·exp(−Q/(R·T)) with D₀ and Q from Callister (Table 5.2), `D0_diff`, `Q_diff`. The kind of quantity of each call is
known before evaluation, so units and dimension checks work as for numbers with units.

**Report.** `rechner/bundle.py` scans each calculation line for these calls (`materials.cite_records`) and cites the
source of every value used: a reference key as a proper bibliography entry, a source text as `@misc` with title,
basis, URL and access date.

**Optional computed data.** `tools/fetch_optional_data.py mp` queries the Materials Project summary endpoint
(`formula`, `is_stable=true`) with the user's own key (`MP_API_KEY`) for 38 elements and compounds and writes
`labcalc/data/optional/materials_mp.json` (`materials.mp_rows`): for each formula, the stable phase with the lowest
energy above the hull; density; K and G as Voigt–Reuss–Hill averages; isotropic E = 9KG/(3K+G) and
ν = (3K−2G)/(2(3K+G)); band gap (not for metals); space group and crystal system. The entries are separate
(`mp-…`, "… (berechnet, mp-…)"), never mixed into measured values, and every value carries the DFT note. Tested with a
fixed sample (`sdk/python/tests/test_materials.py::OptionalMaterialsProject`); no download in the tests.

**Validated by** `sdk/python/tests/test_materials.py` (file validation, every value sourced, unit conversion, names
and aliases, ambiguity, SI values, function dimensions, citations) and `modules/rechner/tests/test_rechner.py`
(`MaterialsScience`: Bragg angle of α-Fe (110) with Cu Kα 44.67°, density of Cu from the lattice parameter 8935 kg/m³,
carbon equivalent and Ms, Avrami and WLF, Pilling–Bedworth ratio of Al 1.29, corrosion rate of Fe 11.6 µm/a, report
citations, workspace values; `Server.test_materials_routes`).

---

## Known limitations

1. **No uncertainty propagation in calculation lines and formula cards.** Only the fit tool and graph regression rows
   report uncertainties.
2. **Integral without extrapolation.** Adaptive G7/K15 with error estimate; non-converged integrals are refused, not
   computed (section 11). Strong endpoint singularities reach about 10⁻¹⁰ relative.
3. **Numerical derivative** is an estimate with error control; at kinks it returns the mean slope with a note
   (section 11).
4. **Temperature differences** with `->`: decided from kinds of quantity; plain numbers in K count as absolute
   temperatures; use `-> Δ°C` to force a difference (section 2).
5. **Unknown units** are shown as `?` (mixed lists and matrices, polynomial functions on quantities with units).
6. **Linearised fits are unweighted**; Lineweaver–Burk is labelled as biased; new fit rows default to the direct mode
   (section 9).
7. **First-order uncertainties** in the fit tool and regression rows; asymmetric intervals for A, a are reported as
   symmetric and labelled "first order".
8. **Convergence test** of Levenberg–Marquardt is the gradient criterion; it does not prove a global minimum.
9. **Numerical root finding is not exhaustive**: formula cards search 10⁻¹⁵ … 10¹⁵ (sign changes and pronounced
   touching roots); calculation lines show at most 12 numerical solutions; nonlinear systems use 35 starts and show at
   most 8 solutions.
10. **Formula-card check tolerance** comes from the typed digits of the inputs (10⁻⁹ … 10⁻²); measurement
    uncertainties are not used.
11. **Chemistry equations use concentrations, not activities**; `ch_pOH` assumes pKw = 14 (25 °C; `ch_pOH_pKw` for
    other temperatures); the hardness-to-strength conversion `hard_Rm` is a rule of thumb, not checked against
    ISO 18265.
12. **Constants are used without their uncertainty.** Exact derived constants are computed in double precision in
    `units.py`; other SDK modules of the Elemental Calculator still use 10-digit values.
13. **Display precision** is limited (5 digits on cards, 6 digits for `\labval` and the quantity table, R² 5 digits).
14. **`rand` is unseeded**; results using it are not reproducible.
15. **Report bundles** record the Folio Lab and module versions and the calculation request, but no source-file
    hashes (the Rechner has no source files).
16. **Material values are nominal.** They are typical or minimum values from handbooks, standards and data sheets, not
    the properties of a particular batch; several values are marked "not checked against the source" (⚠). Results of
    `mat()` inherit both.
17. **Materials Project values are computed** (DFT, GGA): band gaps are usually much too small, densities and moduli
    differ by a few per cent from experiment, and the stable phase at 0 K may not be the phase used in practice (e.g.
    graphite rather than diamond for C, monoclinic ZrO₂).
