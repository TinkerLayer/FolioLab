# Measurement uncertainty: methods and validation

Code: `sdk/python/labcalc/uncertainty.py` (calculation, report output), `sdk/python/labcalc/data/instruments.json`
(instrument library), `sdk/python/labunc.py` (the `api/unc/…` routes every module server offers),
`sdk/web/labunc.js` (± button, editor, method picker, result view). Tests: `sdk/python/tests/test_uncertainty.py`
and the uncertainty tests of each module.

Every module that offers uncertainty uses this one implementation, so a result evaluated in two modules is
evaluated the same way.

## 1 Inputs

An input quantity has a value, a unit and a list of **contributions**. Each contribution gives a standard
uncertainty u, a type (A or B), a distribution and degrees of freedom ν. The contributions of one input add in
quadrature, u(x)² = Σ uᵢ², and its ν follows from Welch–Satterthwaite over the contributions (one contribution keeps
its own ν).

| Contribution | Standard uncertainty | Type, ν | Source |
|---|---|---|---|
| standard uncertainty u | u | B, ∞ (or as entered) | JCGM 100 4.3 |
| expanded uncertainty U with k (certificate) | U/k | B, ∞ | JCGM 100 4.3.3 |
| limits ±a, rectangular / triangular / U-shaped / normal (a = 3σ) | a/√3, a/√6, a/√2, a/3 | B, ∞ | JCGM 100 4.3.7–4.3.9; JCGM 101 6.4 |
| resolution d (digit step) | (d/2)/√3 | B, ∞ | JCGM 100 F.2.2.1 |
| ± p % of the value | (p/100·\|x\|)/√3 (or the chosen distribution) | B, ∞ | EURACHEM/CITAC CG 4, Appendix E |
| manufacturer's spec ±(p % + n digits) | (p/100·\|x\| + n·d)/√3 | B, ∞ | EURACHEM/CITAC CG 4, Appendix E |
| repeat readings x₁…xₙ | s/√n | A, n − 1 | JCGM 100 4.2 |
| standard deviation s of n values | s/√n | A, n − 1 | JCGM 100 4.2 |
| confidence interval ±h at level p with n values | h / t((1+p)/2, n − 1) | A, n − 1 | JCGM 100 4.3.4 |
| instrument | the contributions the library entry defines for that value | per entry | per entry |

Repeat readings also offer *use the mean as the value*. A type A contribution with ν < ∞ is sampled in Monte
Carlo from the scaled and shifted t distribution (JCGM 101 6.4.9).

### Instrument library

`instruments.json` holds generic instruments, each with its limit a as an expression of the reading x (in the
instrument's unit) and optional parameters, its distribution and its source. The groups are length (digital
caliper, micrometer), mass (analytical and precision balance; repeatability, linearity and resolution as separate
contributions), volume (class A volumetric flasks after ISO 1042, single-volume pipettes after ISO 648, burettes
after ISO 385, triangular distribution as in EURACHEM/CITAC CG 4; piston pipettes after ISO 8655-2), temperature
(Pt100 classes AA, A, B after IEC 60751; thermocouple type K class 1 and 2 and type S class 1 after IEC 60584-1),
force (testing-machine classes 0.5, 1 and 2 after ISO 7500-1) and extension (extensometer classes 0.2, 0.5, 1 and 2
after ISO 9513), plus *manufacturer's statement* with free limits. Values from standards not checked against the
original are marked *Angaben nicht am Original geprüft*. A real instrument's calibration certificate always takes
precedence: enter its U and k instead.

**Own instruments** are stored for the whole suite in `<suite>/messmittel.json` (`folio-messmittel/1`), with name,
unit, contributions and a source; they can be exported and imported as a file.

### Correlation

Inputs are independent unless a correlation coefficient r(xᵢ, xⱼ) is entered. The matrix must be positive
semi-definite; otherwise the evaluation stops with a message.

## 2 Methods

The model y = f(x₁, …, x_N) is either a function of the module or an expression (own equations). Inputs without a
contribution are exact.

### GUM linear (JCGM 100, 5.1–5.2, G.4)

Sensitivities cᵢ = ∂f/∂xᵢ by central differences with step u(xᵢ)/100.
u_c(y)² = Σᵢ Σⱼ cᵢ cⱼ u(xᵢ) u(xⱼ) r(xᵢ, xⱼ). Effective degrees of freedom by Welch–Satterthwaite,
ν_eff = u_c⁴ / Σ (cᵢ u(xᵢ))⁴/νᵢ, rounded down. Coverage factor k = t((1+p)/2, ν_eff), or a fixed k when chosen
(k = 2 is the usual choice for p ≈ 95 %). The budget lists, per input, u, type, distribution, ν, c, |c|·u and its share
of u_c². For each input, y is also evaluated at xᵢ ± u(xᵢ); when the quadratic part |y(x+u) + y(x−u) − 2y|/2 exceeds
10 % of |cᵢ u(xᵢ)| (JCGM 100 5.1.2), a note says the model is clearly non-linear there and advises Monte Carlo.

### Monte Carlo (JCGM 101)

Inputs are drawn from their distributions (each contribution separately, so a rectangular plus a normal part keep
their shapes); correlated inputs are drawn jointly normal via a Cholesky factor. The adaptive procedure of JCGM 101
7.9 runs blocks of 10⁴ trials until twice the standard deviation of the block results for mean, u and both interval
ends is at most δ = ½·10ˡ, where 10ˡ is the second significant digit of u (n_dig = 2), with at most 10⁶ trials. A
model that cannot take arrays is evaluated trial by trial in blocks of 4000, under the same stop rule, for at most
about 4 s; then a note says the number of trials was limited. The seed is fixed (20261119), so a result is
reproducible. Reported: the mean, u = standard deviation, the probabilistically symmetric interval at p (JCGM 101
7.7) and the shortest interval, and a histogram.

### Gaussian error propagation (DIN 1319-4; Taylor 1997, ch. 3)

u(y)² = Σ (cᵢ u(xᵢ))², independent inputs, k = 1: the standard uncertainty without a coverage factor, as in many lab
courses.

### Worst case

y is evaluated at every corner of the limits [xᵢ − aᵢ, xᵢ + aᵢ] (aᵢ is the half-width each contribution states,
or 2u for a normal one) for up to 10 uncertain inputs, plus random interior points to catch a non-monotonic model
(a note says when an interior point lies outside). With more inputs the linear bound Σ |cᵢ| aᵢ is used. Reported:
the interval [min; max].

### Comparison

*Compare methods* evaluates all four on the same inputs and lists value, u, interval and k or M side by side.

## 3 Rounding and output

U is rounded to two significant digits and the value to the same decimal place (JCGM 100 7.2.6); a Monte Carlo
interval is rounded to the place of its larger half-width. A result that depends on no uncertain input has u = 0
and is not shown.

In a report, `to_report` writes per result the values `<name>-pm` (value ± U with unit, or value with the interval),
`<name>-U` and `<name>-u`, a budget table `<name>-budget`, and one methods sentence per method that names the
quantities, the method, k and p (or M), cites JCGM 100, JCGM 101 or DIN 1319-4 and Taylor, and cites the source of
every instrument used. Values shared with other modules or the project index carry `u` and the method.

## 4 Tests

| Check | Expected | Test |
|---|---|---|
| JCGM 101 9.2.2: Y = X₁ + X₂ + X₃ + X₄, normal inputs with u = 1 | u = 2, interval ±3.92 (GUM and Monte Carlo) | `test_additive_normal` |
| JCGM 101 9.2.3: same with rectangular inputs | Monte Carlo ±3.88, GUM ±3.92 | `test_additive_rect` |
| JCGM 101 9.3: mass calibration | GUM u = 0.0539 mg; Monte Carlo u ≈ 0.075 mg, interval [1.087; 1.383] mg | `test_mass_calibration` |
| Welch–Satterthwaite | a + b, u = 1 each, ν = 4 and ∞: ν_eff = 16, k = 2.120; fixed k = 2 kept | `test_welch_satterthwaite` |
| correlation | a − b with r = 1: u = 0; a + b with r = 0.5: u = √3 (GUM and Monte Carlo) | `test_correlation` |
| Gaussian propagation and worst case | closed forms for a·b | `test_gauss_and_worst` |
| non-linear model | note; Monte Carlo u larger than GUM for x² at x = u | `test_nonlinear_note_and_compare` |
| model without arrays | evaluated trial by trial, u = 0.2 for 2a with u(a) = 0.1 | `test_scalar_only_model` |
| rounding | GUM 7.2.6 examples, U = 0 | `test_rounding`, `test_zero_uncertainty_rounding` |
| instruments | Pt100 class A at 100 °C: a = 0.35 °C (also when the reading is in K); type K class 1 at 800 °C: 3.2 °C; 10 mL pipette class A: u = 0.02/√6 mL; 100 mL flask read in L; extensometer class 1; caliper with its own MPE; every class has a source; own instrument with a = 0.01 + x/1000 | `test_instruments`, `test_own_instrument` |
| own equations | correlation kept through a chain of equations; shared values keep u | `test_chain_keeps_correlation`, `test_ext_values_carry_u` |
| report | values, budget table, citations | `test_report_with_unc`, `test_bundle` |

## 5 Limitations

- Only one output quantity per evaluation; several outputs of one model are evaluated separately, so their mutual
  correlation is not reported.
- Correlated inputs are sampled jointly *normal* in Monte Carlo, whatever their stated distribution.
- The instrument library gives generic limits from standards and guides. They are not a calibration; values not
  checked against the original standard are marked.
- Uncertainty of the model itself (for example an empirical formula such as CE or Ms) is not included unless entered
  as an input.

## References

- JCGM 100:2008, *Evaluation of measurement data – Guide to the expression of uncertainty in measurement* (GUM).
- JCGM 101:2008, *Supplement 1 to the GUM – Propagation of distributions using a Monte Carlo method*.
- JCGM 200:2012, *International vocabulary of metrology* (VIM).
- DIN 1319-4:1999-02, *Grundlagen der Messtechnik – Teil 4: Auswerten von Messungen; Messunsicherheit* (not checked
  against the original).
- Taylor, J. R. (1997): *An Introduction to Error Analysis*, 2nd ed., University Science Books, ch. 3.
- Ellison, S. L. R.; Williams, A. (eds.) (2012): *EURACHEM/CITAC Guide CG 4: Quantifying Uncertainty in Analytical
  Measurement*, 3rd ed.
- IEC 60751:2022, IEC 60584-1:2013, ISO 7500-1:2018, ISO 9513:2012, ISO 1042:1998, ISO 648:2008, ISO 385:2005,
  ISO 8655-2:2022 for the instrument classes (not checked against the originals).
