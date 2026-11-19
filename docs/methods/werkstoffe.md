# Werkstoffe (materials): methods and validation

This document describes what the Werkstoffe module (`modules/werkstoffe/`, module version 0.1.0) computes, how, with
which defaults and limits, which references the code cites, and which automated test checks it. Statements refer to
the code in `modules/werkstoffe/werk/*.py`; file names below are relative to that folder.

All tests named here use **synthetic data or textbook/standard reference values**. No test uses a real instrument
file. Run them with `python -m unittest discover -s tests` in `modules/werkstoffe` (with `sdk/python` on the path).
Test identifiers are given as `TestClass.test_name` in `tests/test_werkstoffe.py`.

## How to cite results from this module

State the Folio Lab version and the module version (`module.json`, field `version`). **To report …** stores the
request and every file used (diffractograms, CIF, tables) in the bundle; **Refresh** recomputes from them. Every
figure, table and methods paragraph cites its sources through `refs.bib`. Diagrams that are not measured carry their
label in the figure and in the text: *schematisch nach zitierten Eckpunkten* (schematic after cited key points),
*berechnet (Lösungsmodell)* (computed, solution model), *Strichmuster berechnet aus Strukturen* (stick patterns
computed from structures), *berechnet (DFT)* for Materials Project values.

## 1 Material selection and cards (`select.py`)

- **Data:** the shared materials database `sdk/python/labcalc/data/materials.json` (136 materials, every value with
  source and value kind, ranges where given). The module adds no values of its own.
- **Ashby chart:** any two properties on log axes; ranges are drawn as boxes. Classes are coloured.
- **Performance index** M = Π P_k^e_k (e.g. E^½/ρ). On log–log axes Y against X, lines of constant M have slope
  −b/a (Ashby, *Materials Selection*, ch. 5). The ranked list gives M and, for excluded materials, the reason
  (property missing, limit not met).
- **Materials Project** entries (`mp-…`, computed by DFT) are excluded unless the toggle is on; they then have their
  own marker and the label *berechnet (DFT)*.
- **Own values:** materials not in the database can be added under *Eigene Werte* with name, x, y and a free-text
  source, in the units of the current axes. They are drawn as hollow diamonds and labelled *eigene Werte*. They count
  for the axes they were entered under only. They are ranked when the index uses nothing but the two axis properties,
  M = x^e_x · y^e_y; otherwise they are listed as excluded ("Kennzahl braucht weitere Eigenschaften"). Limits on x or
  y apply to them. In the report each source becomes a reference (a URL in the text is kept as the link); a point
  without a source is marked *ohne Quellenangabe*.
- **Cards:** for 2–6 materials, every stored value with value kind and source; values not checked against the
  original are marked †.
- Tests: `SelectTest.*` (order of the ranking, MP excluded by default, every card value has a source; own values:
  M = E^½/ρ by hand, merged order and ranks, exclusion with further properties or limits, validation).

## 2 Crystallography (`cryst.py`, `formfactors.py`)

- **Cell:** metric tensor from a, b, c, α, β, γ; d_hkl = 1/√(hᵀG*h); 2θ from Bragg, λ = 2d sin θ.
- **Structure factor:** F = Σ f_j(s) occ_j exp(−B_j s²) exp(2πi(hx + ky + lz)), s = sin θ/λ. Atom positions are
  expanded with the symmetry operators and the centring vectors and merged mod 1.
- **Atomic form factors:** Cromer–Mann (4 Gaussians + c), coefficients from International Tables Vol. C, Table
  6.1.1.4. **They were transcribed from memory.** Checked: f(0) = Z for all elements used
  (`CrystTest.test_formfactor_at_zero_is_Z`) and the order of the strong lines of Cu, Si, NaCl, corundum and rutile
  (below). Anomalous dispersion (f′, f″) is not included.
- **Intensity:** I = Σ |F|² · LP, LP = (1 + cos²2θ cos²2θ_M)/(sin²θ cos θ) (Bragg–Brentano, no absorption, texture
  or microabsorption). Lines with the same d are summed (multiplicity). I_rel is scaled to 100.
- **Default displacement parameter** B = 0,5 Å² when a phase gives none.
- **Built-in phases:** 38 phases (metals, oxides, carbides, nitrides, halides, semiconductors) after Wyckoff (1963),
  listed in `data/phases.json`; marked as not checked against the original.
- **CIF import:** first data block; cell, H–M symbol, symmetry operators (`_symmetry_equiv_pos_as_xyz` or
  `_space_group_symop_operation_xyz`), atom sites with occupancy and B or U_iso (B = 8π²U). A CIF without operators is
  refused unless the space group is P1. Journal, authors and DOI, and a COD number, become the phase's citation.
- Tests:
  - Cu: hkl sequence 111, 200, 220, 311, 222, 400; d and 2θ against Bragg; multiplicities 8 and 6
    (`test_bragg_and_cu_lines`);
  - Si: 200 and 222 absent, 111 strongest (`test_silicon_diamond_extinction`);
  - NaCl: 200 strongest, 111 below 20 % (`test_nacl_200_strongest`);
  - corundum: the three strongest lines at 2θ = 35,15° (104), 43,36° (113), 57,50° (116), 012 at 25,58° (Cu Kα1),
    as in the published powder pattern (`test_corundum_strong_lines`);
  - rutile from a CIF with the 16 operators of P4₂/mnm equals the built-in phase with written-out sites, line for line
    (`test_cif_rutile_equals_builtin`);
  - X-ray density of Cu (`test_density`); d, plane angle and direction length in the Si cell (`test_kristall_tool`).

## 2a Lattice model (`gitter.py`, `data/gitter.json`)

A section of the crystal lattice of a base element at a temperature, with the atoms that are dissolved in it and the
defects that go with them. **It is a model, not a micrograph:** counts, lattice parameter and vibration amplitude are
computed; the position and shape of precipitates, dislocations, stacking faults and grain boundaries are schematic.
The page, the figure tags and the report say so.

- **Phase at T:** allotropes of the base element by temperature (Fe α/γ/δ, Ti α/β, Co ε/α, …); with a solute that has a
  phase diagram in §5 the region at (c, T) and the phase fractions by the lever rule (Callister ch. 9). Above Tm the
  section is a dense random packing (melt) without unit cell.
- **Lattice parameter:** a(T) = a(T₀)·[1 + α (T − T₀)] with α at 25 °C (CRC), or linear between tabulated points where
  they exist (Basinski 1955 for Fe). A constant α underestimates the expansion near Tm (stated in the code).
- **Solute sites:** H, B, C, N, O on interstitial sites (octahedral or tetrahedral hole per lattice type, Porter;
  Hirth 1980 for H in bcc), all other elements substitutional. Radii: metallic radius from the element's own lattice
  (bcc a√3/4, fcc a√2/4, hcp a/2), covalent radii after Cordero 2008. A size difference above 15 % is flagged
  (Hume-Rothery).
- **How many solutes:** the true number for the dissolved fraction, x/(1 − x)·N_sites for interstitials and x·N_sites
  for substitutionals, rounded stochastically with the seed. Solubility: from the phase diagram, complete for the
  listed miscible pairs (Massalski 1990), otherwise a limit the user enters with its source (cited in the report);
  the excess forms the second phase, drawn as a sphere or lamella.
- **Vacancies:** c_v = exp(S_v/k)·exp(−H_v/kT), H_v per element (Ehrhart 1991), S_v = 1,5 k assumed. The section
  shows the true expected number (at room temperature practically always zero). The "exaggerate" factor
  (1…10⁸) multiplies only the drawn number; the factor is printed in the legend, the figure tag, the table and the
  methods text.
- **Thermal vibration:** Debye model ⟨u_x²⟩ = 3ħ²/(m k θ_D)·[Φ(x)/x + 1/4], Φ(x) = (1/x)∫₀ˣ t/(eᵗ − 1) dt,
  x = θ_D/T (Willis & Pryor 1975); atoms displaced normally with σ = √⟨u_x²⟩ (optional factor up to 10, labelled).
- **Local distortion:** neighbours within 2 d₁ of a solute or vacancy are moved radially by u(r) = δ (d₁/r)², δ from the
  radius difference (Eshelby 1956). Schematic.
- **Line and planar defects (schematic):** edge dislocation with the isotropic Volterra displacement field (Hirth &
  Lothe 1982), shortest Burgers vector in the glide plane (fcc a/2⟨110⟩ {111}, bcc a/2⟨111⟩ {110}, hcp a in (0001)),
  ν per element; stacking fault as a Shockley shift a/6⟨112⟩ (fcc) or a/√3 in the basal plane (hcp) of the layers above
  one close-packed plane; symmetric tilt grain boundary of two grains rotated by ±θ/2 (default 16°). With both a grain
  boundary and a stacking fault only the boundary is drawn (note in the result).
- **Unit cell:** the conventional cell placed on lattice sites near one corner of the section; it moves with the
  defects and the grain rotation, so its corners stay on atoms.
- **Slice:** one atomic layer (hkl) through the centre, ±w thick, atoms at their true radius.
- **Data** (`data/gitter.json`): melting points (CRC), Debye temperatures (Kittel), H_v (Ehrhart 1991), lattice
  points of high-temperature forms (Wyckoff 1963, Basinski 1955), covalent radii (Cordero 2008), miscible pairs
  (Massalski 1990); written after the named source and marked *nicht am Original geprüft* in the data and the report.
- Limits: 2–14 cells per edge, at most 12 000 atoms, four solutes. Everything random depends on the seed, so a figure is
  reproducible.
- Tests (`GitterTest.*`):
  - γ-Fe with 0,4 % C at 1000 °C: C on octahedral sites, number = x/(1 − x)·N_Fe within ±1;
  - α-Fe with 0,8 % C at 20 °C: cementite mass fraction 0,8/6,69 by the lever rule;
  - Ni at 900 °C: c_v equals the Arrhenius expression, expected count = c_v·N, drawn count with factor 10⁶ within
    Poisson scatter; no vacancy at 20 °C;
  - Debye ⟨u²⟩ tends to the classical 3ħ²T/(m k θ_D²) at T ≫ θ_D (within 1 %) and stays above zero at 1 K;
  - unit-cell corners on atoms for fcc, bcc and hcp; 14 (fcc) and 9 (bcc) atoms in the cell;
  - slices: in-plane coordination 6 for fcc (111) and hcp (0001), 4 for fcc (100) and bcc (110), nearest distance d₁
    (hcp basal plane: a);
  - melt without unit cell, same seed gives the same atoms, grain-boundary note;
  - own solubility limit: excess as precipitate, its source in `refs.bib` with URL, report figures, table, data and the
    equations in the methods text.

## 3 XRD files (`xrdio.py`)

| Format | What is read | Wavelength |
|---|---|---|
| xy, xye, csv, txt, dat, asc | first two numeric columns (separator and decimal comma detected) | from a header line such as `Wavelength 1.5406`, or the anode name |
| PANalytical `.xrdml` | first scan, `positions axis="2Theta"` (list or start/end), `intensities` or `counts` | `usedWavelength` (Kα1, Kα2, ratio), `anodeMaterial` |
| Bruker `.brml` | `RawData*.xml` in the ZIP; the 2θ column is detected as the first strictly increasing column between 0 and 180° (2θ chosen over θ); intensity = last column | `WaveLengthAlpha1/2`, `WaveLengthRatio`, `TubeMaterial` |
| Bruker `.raw` | version RAW1.01 only (layout after the xylib format description); several ranges are joined | header fields at 624/632/648 |
| Bruker `.uxd` | `_2THETA`/`_START` + `_STEPSIZE` blocks, or two-column data | `_WL1`, `_WL2`, `_WLRATIO`, `_ANODE` |
| Rigaku `.ras` | first `*RAS_INT_START` block; intensity × attenuator factor (third column) | `*HW_XG_WAVE_LENGTH_ALPHA1/2`, `*HW_XG_TARGET_NAME` |

- An anode without wavelengths gets the standard values of that tube (noted). A file without either is evaluated with
  Cu Kα1/Kα2, and the result says *angenommen* (assumed).
- RAW4 (DIFFRAC.SUITE) and RAW version 1/2 files are refused with a message to export `.brml` or `.xy`.
- **No real instrument file was available.** All readers are tested on files written to the format descriptions
  (`ReaderTest.*`): values and wavelengths round-trip; the RAS attenuator is applied; RAW4 is refused; a file whose
  first column is not an angle is refused.

## 4 XRD evaluation (`xrd.py`)

Order (each step can be switched off): Savitzky–Golay smoothing (off by default) → SNIP background (width 2° 2θ) →
optional Kα2 stripping (Rachinger) → local maxima with prominence ≥ 2 % of the largest and spacing ≥ 0,15° →
pseudo-Voigt fit per peak, as a Kα1/Kα2 doublet when λ₂ is known and Kα2 is not stripped (Thompson–Cox–Hastings
profile family) → indexing and lattice parameter → size and strain → phase match → semi-quantification.

- Fitted peaks narrower than two steps are dropped as spikes; peaks below half the minimum height after the fit are
  dropped (mostly Kα2 shoulders); both are noted in the result.
- **Cubic indexing:** for sc, bcc, fcc and diamond, the measured 1/d² are matched to the allowed N = h² + k² + l²;
  the candidate with the smallest relative spread of a (and no missing lines) wins. Peaks below 3 % are not used.
- **Lattice parameter:** least squares over all indexed lines, and Nelson–Riley extrapolation
  a(θ) against ½(cos²θ/sin θ + cos²θ/θ) to θ = 90°.
- **Scherrer:** D = Kλ/(β cos θ), K = 0,9, β = FWHM in rad after subtracting the instrument broadening
  (quadratic by default; Caglioti U, V, W or a constant).
- **Williamson–Hall:** β cos θ = Kλ/D + 4ε sin θ, regression over ≥ 3 peaks.
- **Phase match (own score, similar to search–match figures of merit):** coverage = Σ I_ref of matched lines /
  Σ I_ref of all lines ≥ 3 % in the range; position = 1 − mean|Δ2θ|/tol; score = 100 · coverage · (0,5 + 0,5 ·
  position); tolerance 0,2°, with a common shift searched within ±0,4°. Searching runs over all built-in and loaded
  CIF phases. No ICDD data are used.
- **Semi-quantification:** scale factor per phase S = Σ A_obs / Σ (m|F|²LP/V²) over its matched lines; volume
  fraction ∝ S, mass fraction ∝ S·ρ. This is equivalent to RIR values computed from the structure (Chung 1974;
  Hubbard & Snyder 1988). Absorption contrast, texture, microabsorption and amorphous content are not handled; the
  result is labelled semi-quantitative.
- Tests (`XrdTest.*`): a synthetic Cu pattern (Kα doublet, noise, background) gives 6 peaks at the computed
  positions (±0,01°), fcc, a = 3,6149 Å (±2·10⁻⁴) by least squares and Nelson–Riley, Cu first in the search
  (score > 90); Scherrer against the formula; d against Bragg; direct cubic indexing of fcc and bcc d-sets;
  Williamson–Hall recovers D = 40 nm and ε = 0,002 from synthetic breadths.

## 5 Phase diagrams (`phasediag.py`, `data/diagrams.json`)

- **Schematic diagrams:** Fe–Fe₃C (metastable), Pb–Sn, Al–Si, Cu–Ag and Cu–Ni are drawn through invariant and key
  points as given in Callister & Rethwisch (Fe–C, Pb–Sn, Cu–Ni), Murray & McAlister 1984 (Al–Si) and Subramanian &
  Perepezko 1993 (Cu–Ag). Lines between the cited points are straight or smooth guides, not measured curves: every
  figure and text says *schematisch*.
- **Lever rule:** W_left = (x_r − x₀)/(x_r − x_l) on the horizontal tie line through the chosen point; constituents
  below an eutectic or eutectoid (e.g. proeutectoid ferrite and pearlite); a cooling path with the fraction of every
  phase against T.
- **Computed diagrams:** G_S = RT[x ln x + (1−x)ln(1−x)] + Ω_S x(1−x), G_L = (1−x)ΔH_A(1 − T/T_A) + xΔH_B(1 − T/T_B)
  + RT[…] + Ω_L x(1−x) (Porter & Easterling, ch. 1; ΔC_p neglected); stable phases from the lower convex hull of both
  curves. Ideal solution: Ω = 0. The Cu–Ni preset (T_m, ΔH_m from the shared data) deviates from the assessed
  diagram by up to about 25 K; it is labelled *berechnet (Lösungsmodell)*.
- Tests (`PhaseTest.*`):
  - Fe–C 0,35 % C just below 727 °C: proeutectoid ferrite (0,76 − 0,35)/(0,76 − 0,022) = 0,556, pearlite 0,444;
  - Pb–Sn 40 wt% Sn at 150 °C: α fraction 0,70 from the cited solvus points;
  - the computed Cu–Ni tie line at 1225 °C against the closed-form ideal solution
    x_S/x_L = exp(ΔG_B/RT), (1−x_S)/(1−x_L) = exp(ΔG_A/RT) (±0,15 wt%), and the liquid fraction (±0,01);
  - liquidus end points at the melting temperatures, solidus below liquidus.

## 6 Steel (`steel.py`)

| Quantity | Formula | Source |
|---|---|---|
| CE (IIW) | C + Mn/6 + (Cr+Mo+V)/5 + (Ni+Cu)/15 | EN 1011-2, Annex C, method A |
| CET | C + (Mn+Mo)/10 + (Cr+Cu)/20 + Ni/40 | EN 1011-2, method B |
| Pcm | C + Si/30 + (Mn+Cu+Cr)/20 + Ni/60 + Mo/15 + V/10 + 5B | Ito & Bessyo 1968 |
| Preheat T_p | 697 CET + 160 tanh(d/35) + 62 HD^0,35 + (53 CET − 32) Q − 328 | EN 1011-2, method B (range checked and warned) |
| Ms, Ac1, Ac3 | linear/√C formulas | Andrews 1965 |
| Tempering | P = T(C + lg t), C = 20, equivalent time at another T | Hollomon & Jaffe 1945 |
| Carburising | c = c_s − (c_s − c₀) erf(x/2√(Dt)), D = D₀ exp(−Q/RT); case depth at c = 0,4 % C (default) | Callister ch. 5; D₀, Q from the shared diffusion data |

The ideal critical diameter (Grossmann) was **not built**: the multiplying factors are tables from
ASTM A255 that could not be checked here. Tests: `SteelTest.*` (the three equivalents term by term, Hollomon–Jaffe
and the equivalent time, c at the case depth equals the limit, D against Arrhenius, preheat rises with CET).

## 7 Laminates (`laminate.py`)

Classical laminate theory as in Daniel & Ishai (ch. 7–8) and Jones (ch. 4): Q from E1, E2, G12, ν12; Q̄ by rotation;
A, B, D; mid-plane strains and curvatures; ply strains and stresses at top and bottom of each ply; engineering
constants of symmetric laminates. Failure (reserve factor R = load multiplier to failure): maximum stress,
Tsai–Hill, Tsai–Wu (F12* = −0,5 by default), Hashin plane stress (S_T = Yc/2 by default); first-ply failure.
Lay-up notation `[0/±45/90]s`, `[0/90]2s`. Ply data come from the shared database (UD plies) or are typed in.

Tests (`LaminateTest.*`): an isotropic material gives E_x = E, ν_xy = ν, G_xy for any lay-up; `[0/90]s` has
A11 = A22, A16 = 0, B = 0 and A11 = (Q11 + Q22)·h/2; `[0]₄` under N_x has R(max. stress) = X_t h/N_x; lay-up parser.

## 8 Fatigue (`fatigue.py`)

- **S–N:** lg N = A + B lg σa (ASTM E739, least squares with 95 % band); Basquin σa = σf′(2N)^b, b = 1/B. With
  run-outs, additionally maximum likelihood with censored normal lg N (Nelson 1990).
- **Mean stress:** Goodman, Gerber (tension only), Soderberg, Morrow, SWT (Dowling); Haigh diagram.
- **Marin factors** (Shigley, 10th ed.): ka = a·Rm^b by surface, kb by size, kc by loading, kd, ke by reliability;
  Se′ = 0,5 Rm up to Rm = 1400 MPa, else 700 MPa (steel approximation, stated in the result).
- **Rainflow** after ASTM E1049 (three-point method, half cycles at the end), optional hysteresis filter.
- **Miner** sum D = Σ n/N with the S–N line; cycles below Se are counted separately.
- Tests (`FatigueTest.*`): the E1049 example (−2, 1, −3, 5, −1, 3, −4, 4, −2) gives ranges 3 (½), 4 (1½), 6 (½),
  8 (1), 9 (½); exact Basquin data (σf′ = 900, b = −0,09) are recovered; run-outs move the MLE line to longer
  lives; mean-stress formulas; Marin factors; Miner against the closed form.

## 9 Weibull and fracture mechanics (`reliability.py`)

- **Weibull:** rank regression with Bernard ranks F = (i − 0,3)/(n + 0,4); maximum likelihood (ASTM C1239) without
  the small-sample unbiasing factor (stated); parametric bootstrap intervals (B = 1000, 90 %, seed 20261118, so a
  result is reproducible); quantiles; size effect σ₂ = σ₁(V_eff1/V_eff2)^(1/m) with V_eff for 3- and 4-point bending
  after Quinn 2003.
- **Fracture (ASTM E399):** K_Q for SE(B) (S = 4W) and C(T) with the E399 geometry functions; validity checks
  (a, B, W − a ≥ 2,5(K/Rp0,2)², 0,45 ≤ a/W ≤ 0,55, P_max/P_Q ≤ 1,10); critical crack size and stress
  (Anderson).
- Tests (`ReliabilityTest.*`): the MLE satisfies its score equation (|g| < 10⁻⁸) and σ₀ = (mean σᵐ)^(1/m); Bernard
  ranks; bootstrap reproducible with a seed and bracketing m; size effect; f(0,5) = 2,6625 (SE(B)) and 9,659 (C(T))
  as tabulated in E399; K_Q against the formula; a_c and its inverse.

## 10 Hardness and grain size (`hardness.py`)

- HV = 0,1891 F/d² (ISO 6507-1), HBW = 0,102 · 2F/(πD(D − √(D² − d²))) (ISO 6506-1, d/D range checked),
  HK = 1,451 F/d² (ISO 4545-1); F in N, d in mm; mean, s and 95 % interval of a series.
- **Conversion only from the user's table** (CSV/TSV, first row the scale names, `# Quelle: …` line as the source),
  linear interpolation, no extrapolation; the report cites the user's table. No standard table is bundled. Without a
  table only the rule of thumb Rm ≈ 3,3·HV (steel, Callister) is shown, labelled as such.
- **Grain size (ASTM E112):** G = −6,6457 lg ℓ̄ − 3,298 (mean intercept ℓ̄ in mm), G = 3,321928 lg N_A − 2,954;
  Hall–Petch σ_y = σ₀ + k d^−½ by regression.
- Tests (`HardnessTest.*`): the three hardness formulas; E112 table values G = 0 ↔ ℓ̄ = 0,320 mm and G = 8 ↔
  0,0200 mm; Hall–Petch recovery; table conversion with no extrapolation; no conversion without a table.

## 11 Corrosion and creep (`corrcreep.py`)

- **Tafel:** regression of E on lg|i| on each branch for η = 50–150 mV; intersection → E_corr, i_corr; β in
  mV/decade. Optional Butler–Volmer fit (Levenberg–Marquardt, ±20 mV around E_corr). R_p from ±10 mV (ASTM G59);
  Stern–Geary i_corr = B/R_p. Corrosion rate CR = 3,27·10⁻³ i_corr EW/ρ in mm/a (ASTM G102); EW = M/n from the
  chosen metal.
- **Creep:** Larson–Miller P = T(C + lg t_r), C = 20 or fitted, lg σ as a polynomial in P (degree 2 by default);
  Norton–Arrhenius ε̇ = Aσⁿ exp(−Q/RT) by multiple regression (rates in 1/h).
- Tests (`CorrCreepTest.*`): synthetic Butler–Volmer data (i_corr = 10 µA/cm², β_a = 60, β_c = 120 mV) are
  recovered exactly by the BV fit and within 0,6 µA/cm² by the Tafel lines; units and area; G102 rate; LMP round
  trip; Norton n = 5 and Q = 280 kJ/mol recovered.

## 12 Report (`bundle.py`)

Per tool: figures (matplotlib, PDF), booktabs tables, `\labval` values, CSV data for pgfplots, methods and results
paragraphs, citations. Data files used (diffractograms, CIF, tables) are stored in the bundle and cited as data files.
Tests (`BundleTest.*`, `ServerTest.*`): every `\cite` key resolves to `refs.bib`; schematic and computed labels in the
methods text; no `\text`, `\ce`, `\tfrac`; English output and part selection; load → tool → bundle → rebuild in the
other language over HTTP; foreign origins refused (403); bad files 400.

The page-state bundle (all 14 sections, DE and EN) was compiled with pdfLaTeX + BibTeX without errors or undefined
references during development (not part of the unit tests).

## References as recorded in the code

`werk/refs.py` (module-only sources) and `labcalc/sources.py` (shared). Entries marked *nicht am Original geprüft*
were written from memory and not compared with the original in this round: the standards (ASTM E739, E1049, E399,
E112, C1239, G59, ISO 4545), Wyckoff 1963, Massalski 1990, Murray 1984, Subramanian 1993, Ito & Bessyo 1968,
Shigley, Bernard 1953, Quinn 2003, International Tables Vol. C, Bearden 1967.

## Known limitations

- Cromer–Mann coefficients transcribed from memory (checked only as described in §2); no anomalous dispersion.
- XRD intensities without absorption, texture, microabsorption or preferred orientation; semi-quantification only.
- Indexing is automatic for cubic lattices only; other systems need a reference phase.
- No real instrument files were available for any reader.
- Schematic phase diagrams are teaching diagrams through cited points, not assessed equilibria.
- Computed diagrams use ideal or regular solutions without ΔC_p; Cu–Ni deviates by up to about 25 K.
- Weibull m by MLE is biased high for small n (no C1239 unbiasing factor).
- Empirical steel formulas apply only within their stated composition ranges.
- Hardness conversion depends entirely on the table the user loads.
- Lattice model: a(T) with a constant α away from tabulated points; solubility only where a diagram, a miscible pair or
  an own limit exists (otherwise drawn fully dissolved, with a note); defects, precipitate shape and position are
  schematic; no short-range order, clustering or segregation to defects.
