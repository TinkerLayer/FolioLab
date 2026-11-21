# Elementrechner: methods and validation

This document describes how the Elementrechner module computes each result that a user might report:

* what is computed and the formula used;
* the defaults and limits set in the code;
* the data source and how the code cites it;
* how uncertainty is handled;
* which automated test checks the result, against which value.

The user guide is [modules/elementrechner/README.md](../../modules/elementrechner/README.md). The feature list is
[modules/elementrechner/FEATURES.md](../../modules/elementrechner/FEATURES.md).

Code locations are given as `file:line`. Paths are relative to the repository root. Most of the chemistry is in the
shared core `sdk/python/labcalc/`. The module code is in `modules/elementrechner/elementrechner/`. Tests are given as
`path::TestClass::test_name`, and tolerances as written in the test (`delta` = absolute, `places` = decimal places).

## How to cite results from this module

State the Folio Lab version and the Elementrechner version. The module version is the `version` field in
`modules/elementrechner/module.json`, also `elementrechner.__version__`; it is currently 0.11.0. When you send a
result to a report, the hub writes a `bundle.json` with a `provenance` block that records the Folio Lab version
(`suite_version`) and the module version (`module_version`).

`bundle.json` also has a map of SHA-256 checksums of the source files stored with the bundle (`source_sha256`). The
Elementrechner attaches no source files: it stores its complete input state in the bundle's `source.request`, and
**Refresh** recomputes from that state. For this module the checksum map is therefore empty. The inputs are kept in
the bundle itself.

Refresh uses the code and data installed at that moment. A refresh after an update can therefore change numbers. Each
revision keeps its own module version.

Cite the scientific sources as well. The report section adds a BibTeX entry for every data set and method it used.
These entries are the references to give for tabulated values. The data files carry a build date (`_built`
2026-11-17) and record where they were downloaded from.

## Conventions used throughout

* **Standard state:** 298.15 K and p° = 10⁵ Pa (1 bar), `thermo.py:25-27`. Standard concentration c° = 1 mol/L
  (`thermo.py:28`). Ions in solution follow the convention ΔfH°, ΔfG°, S° of H⁺(aq) = 0 (header of `thermo.json`).
* **Constants:** each one is a literal in the module that uses it.
  * R = N_A·k = 8.31446261815324 J/(mol K), exact in the 2019 SI, computed at full double precision (`chem.R_GAS`). Also used by `thermo.py`,
    `redox.py` and `gas.py:9`.
  * F = N_A·e = 96485.33212331001 C/mol, exact in the 2019 SI (`chem.FARADAY`, used by `redox.py` and the report).
  * k_B = 1.380649·10⁻²³ J/K and h = 6.62607015·10⁻³⁴ J s, both exact (SI 2019), `kinetics.py:16-18`.
  * N_A = 6.02214076·10²³ mol⁻¹, exact; m_u c² = 931.49410372 MeV and mₑ = 5.485799090441·10⁻⁴ u (CODATA 2022);
    1 Ci = 3.7·10¹⁰ Bq; 1 a = 365.2422 d as in NUBASE2020; all in `nuclear.py:22-26`.

  The constants table of the look-up window (`units.CONSTANTS`, provenance in `sources.CONSTANT_SOURCES`) cites
  CODATA 2022 and the SI Brochure 2019.
* **Arithmetic:**
  * Balancing uses exact rational arithmetic (`fractions.Fraction`).
  * The Bateman solution uses 60-digit decimal arithmetic.
  * Everything else is IEEE double precision.
* **Value classes:** every value is marked as one of three kinds.
  * *Tabulated*: from a data set.
  * *Calculated*: derived with a stated formula, for example ΔfG° marked `Gcalc`, or a Ksp marked "berechnet".
  * *Estimated*: from a group-contribution or increment method.

  Estimates are used only when no tabulated value exists, and a result that rests on them carries a warning.

## Bundled data sets

All files are in `sdk/python/labcalc/data/`. The source column quotes the file header (`_source`, `_meta`, `_from`)
as recorded. Counts were taken from the maintainers' complete data. Four sets may not be redistributed. They are
not in the public repository, and `python tools/fetch_optional_data.py <part>` builds them from the original
source (see [THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md)). The tests that need them are skipped without
them.

| File | Content | Source as recorded | Entries |
|---|---|---|---|
| `atomic_weights.json` | Standard atomic weights: abridged value with ±, interval or unabridged value, CIAAW footnotes | `_source` "ciaaw2024"; `_from` ciaaw.org abridged, full and isotopic tables; built 2026-11-17 | 118 elements: 84 with a standard atomic weight, 34 with a mass number only |
| `isotopes.json` | Atomic masses, half-lives, decay modes and branchings, isotopic abundances | `_source` "ame2020"; `_sources` mass "ame2020", half_life "nubase2020", abundance "ciaaw_iso2024"; `_from` AMDC `mass_1.mas20`, `nubase_4.mas20`, ciaaw.org | 5399 nuclides (3558 ground states, 1841 isomers); 2550 with an atomic mass; 254 stable; 289 with abundance |
| `elements.json` | Electron configuration, Pauling electronegativity, oxidation states, first ionisation energy, electron affinity, van der Waals radius, melting and boiling point, density | `_source` "pubchem_pt", PubChem periodic table CSV, accessed 2026-11-17 | 118 elements |
| `ionization.json` | Successive ionisation energies in eV, with flags for theoretical and semi-empirical values | "NIST Atomic Spectra Database, Ionization Energies (Kramida, Ralchenko, Reader & NIST ASD Team)", DOI 10.18434/T4W30F, accessed 2026-11-17 | 110 elements, 5847 values. **Optional** (part `asd`) |
| `thermo.json` | ΔfH°, ΔfG°, S°, Cp° at 298.15 K, 1 bar; NASA-7 polynomials; reference entropies of the elements | "CODATA Key Values (Cox u. a. 1989); NBS-Tabellen (Wagman u. a. 1982, Erratum 1989; digitalisiert NIST 2020); Burcat/Ruscic-Datenbank (Goos, Burcat & Ruscic, Stand 2018; ATcT-Werte)" | 12 263 species entries: 9050 NBS, 3062 Burcat, 151 CODATA. 3062 carry NASA-7 polynomials, 3210 have a calculated ΔfG°, 314 have u(ΔfH°). **The 3062 Burcat entries are optional** (part `burcat`, stored as `optional/thermo_burcat.json` and merged on load); the public file has the CODATA and NBS entries |
| `benson_groups.json` | Benson group values for the gas phase at 298.15 K | Domalski & Hearing 1993, J. Phys. Chem. Ref. Data 22, 805-1159, doi:10.1063/1.555927, Table 2 (gas-phase columns) | 41 groups, 7 corrections |
| `stability.json` | Protonation and stability constants (lg K, ΔH, ΔS), solubility products, with T, I, medium and uncertainty | `_source` "srd46"; `_from` "SRD 46 SQL.zip" (data.nist.gov mds2-2154); built 2026-11-17 | 70 385 rows (55 106 lg K values), 4374 ligands, 154 metals; 495 Ksp entries for 331 formulas. **Optional** (part `srd46`) |
| `pka.json` | pKa values with T, method, rating and literature | `_source` "iupac_pka"; `_from` `iupac_high-confidence_v2_4.csv` (doi 10.5281/zenodo.7236452); licence CC BY-NC 4.0 | 24 017 rows, 11 533 compounds, 441 linked to the collection. **Optional** (part `pka`): see *Optional reference data* in the main README |
| `physprops.json` | Experimental properties: melting, boiling and flash point, density, vapour pressure, solubility, log Kow, refractive index, viscosity, surface tension, Henry constant, enthalpies of vaporisation and combustion, pKa and others | `_source` "pubchem_view" (PubChem PUG View); only ICSC (CC BY 4.0), HSDB, DOE PAC, OSHA, NIOSH; each value keeps the primary reference given there | 1397 substances, 32 214 values, 22 property kinds |
| `molecules.json` | Substance collection: structure, names, CAS, formula for equations | `_source` "pubchem" (PUG REST); German names from Wikidata (CC0) | 1822 substances in 36 classes |
| `indicators.json` | Acid–base indicators: transition ranges and colours | "harris". The note says the values were transferred and should be checked against the edition at hand before publication | 21 indicators (3 with two ranges) |

These tables are written directly in the code. Their source text, as written there, says they were typed in from
reference knowledge and should be checked against the original:

* mean bond enthalpies and lengths: `bonds.py`, 34 entries, Atkins;
* effective ionic radii: `radii.py`, 37 ions, Shannon 1976;
* Antoine coefficients: `vapor.py`, 9 substances, via NIST WebBook with the original sources named per entry;
* cryoscopic and ebullioscopic constants: `vapor.py`, 8 solvents, Atkins;
* Joback group values: `joback.py`, 41 groups, from the tabular reproduction in the Wikipedia article.

## 1 Formula and equation parsing

**What:** the parser turns a typed formula or equation into element counts, charge, phase and coefficients. It is in
`chem.py`.

**What it accepts:**
* Brackets `( ) [ ] { }`, nested. Integer, decimal or fraction indices (`chem.py:304`). An index of 0 is rejected
  (`chem.py:345-346`).
* Hydrates with `·`, `•` or `*` (`chem.py:268`). A dot followed by a 1–2-digit number and a capital letter or "(" is
  also read as a hydrate dot: `CuSO4.5H2O` (`chem.py:282-294`). The hydrate factor may be a fraction or a decimal:
  `CaSO4·1/2H2O`.
* Charges: `^2-`, `^{2-}`, `Fe+3`, `NH4+`, `Ca++` and Unicode superscripts (`chem.py:227-252`). Digits directly
  before a final sign are read as an index, as in mhchem. `Fe3+` therefore means Fe₃⁺, and a hint is shown
  (`chem.py:246-250`).
* Phases `(s) (l) (g) (aq) (cr) (am)` (`chem.py:116`).
* Isotope labels `^13C`, `D` and `T`. Labelled atoms count as separate keys ("13C", "2H") and take their AME2020 mass
  (`chem.py:323-337`).
* Nuclides `^14C`, `C-14` and `^{235}_{92}U`. A Z that does not match the symbol gives a hint (`chem.py:376-389`).
* Particles n, p, α, β⁻, β⁺/e⁺, γ, ν, ν̄, d and t, each with A, Z and charge (`chem.py:99-110`).
* Arrows `->`, `→`, `=>`, `=` (reaction) and `<=>`, `⇌`, `⇄` (equilibrium) (`chem.py:407-408`).
* Coefficients: integer, decimal, fraction, or empty or `?` for unknown.
* Substance names. A term that does not parse as a formula is looked up in the collection (`chem.py:394-403`).

**Validation:**

| Test | Checks |
|---|---|
| `sdk/python/tests/test_chem.py::Parse::test_formula_counts` | Exact counts for Ca3(PO4)2, [Fe(CN)6]⁴⁻, CuSO4·5H2O, CuSO4.5H2O, Fe0.95O (Fe = 19/20), D2O, ^13CH4 |
| `sdk/python/tests/test_chem.py::Parse::test_charges_and_phases` | SO4²⁻, Fe+3, NH4+, Fe3+ (with hint), NaCl(s) |
| `sdk/python/tests/test_chem.py::Parse::test_errors` | Rejects `Xx2`, `Ca(OH` and `?` outside a nuclear equation |
| `modules/elementrechner/tests/test_data.py::Collection::test_size_and_records` | Every formula in the collection parses |

## 2 Molar mass and composition

### Molar mass with standard atomic weights

**What:** M = Σ Nᵢ·A_r,i in g/mol, with M_u taken as 1 g/mol (`chem.py:864-886`). The report text gives the
relative error of that approximation as below 10⁻⁸ (`bundle.py:51-53`). The mass fraction is wᵢ = Nᵢ·A_r,i / M.

**Atomic weights** (`element_weight`, `chem.py:847-861`):
* Every element uses the **abridged** standard atomic weight of CIAAW 2024 and its ± (`value`, `u`). This includes
  elements with an interval, such as H, C, N, O and S. For example, H = 1.0080 ± 0.0002 and C = 12.011 ± 0.002.
* Isotope-labelled atoms use the AME2020 atomic mass and its uncertainty.
* An element without a standard atomic weight (for example Tc, Pm, Po and Z ≥ 93) uses the mass number of its
  longest-lived isotope, with u = 0 and a note (`chem.py:858-860, 880-882`).

**Uncertainty:** u(M) = √( Σ_elements (Nᵢ·uᵢ)² ) (`chem.py:878, 885`).
* Atoms of the same element are treated as fully correlated, so u grows linearly with N.
* Different elements are combined in quadrature.
* The report prints M with this u (`bundle.py:2198`). For example, M(H₂O) = 18.015 g/mol with u = 0.0011 g/mol.
* The ± of the abridged table is used as if it were a standard uncertainty. For elements with an interval it
  describes natural variation of isotopic composition. It is not a GUM standard uncertainty.

**Source in code:** `ciaaw2024` (CIAAW, "Standard Atomic Weights 2024", www.ciaaw.org, accessed 2026-11-17). The
report cites it together with `ciaaw2021` (Prohaska et al., Pure Appl. Chem. 94 (2022) 573-600) (`bundle.py:2051-2053`).

### Hill formula, DBE, monoisotopic mass

* **Hill order:** C, then H, then the other elements alphabetically. Without carbon, all elements are alphabetical
  (`chem.py:929-936`).
* **Degree of unsaturation:** DBE = C − H/2 + N/2 + 1. Si counts as C, halogens as H and P as N. It is undefined for
  other elements (`chem.py:950-960`).
* **Monoisotopic mass** (molecule designer, `design.py:85-110`):
  * For each element, the most abundant isotope by CIAAW abundance is taken, using the interval midpoint where only an
    interval is given. The AME2020 masses of these isotopes are summed.
  * For ions, z·mₑ is subtracted.
  * No uncertainty is given.

### Empirical and molecular formula from elemental analysis

**What** (`chem.py:893-926`):
1. nᵢ = wᵢ / A_r,i.
2. rᵢ = nᵢ / min(n).
3. Take the smallest multiplier k = 1…12 with max |rᵢk − round(rᵢk)| ≤ 0.03·k.
4. If no k qualifies, take the k with the smallest error.

* A warning appears if Σw lies outside 99–101 %.
* Molecular formula: the factor f = M / M(empirical), rounded. A warning appears if f is more than 5 % from an
  integer.
* No uncertainty. No citation in code.

**Validation (molar mass and composition):**

| Test | Checks (expected, tolerance) | Reference |
|---|---|---|
| `modules/elementrechner/tests/test_data.py::AtomicWeights::test_all_elements` | Source is ciaaw2024; 84 standard atomic weights; every element has a value or a mass number | CIAAW 2024 |
| `modules/elementrechner/tests/test_data.py::AtomicWeights::test_values` | H (1.0080, 0.0002), H interval [1.00784, 1.00811], Fe 55.845, Gd 157.249 (2024 change), Zr 91.222, Tc mass number 97, Pu 244; exact | Test header: "CIAAW 2024 (gekürzt), AME2020, NUBASE2020, CIAAW-Isotopenzusammensetzung 2024" |
| `modules/elementrechner/tests/test_data.py::AtomicWeights::test_molar_masses` | H2O 18.015 (places 3), NaCl 58.44 (places 2), C6H12O6 180.156 (places 3), CuSO4·5H2O 249.68 (places 2); TcO4⁻ carries a note | Computed from the abridged weights |
| `modules/elementrechner/tests/test_data.py::Nuclides::test_masses` | ¹²C = 12 exactly; ¹H 1.007825031898 (places 12); ²³⁵U 235.043928117 (places 9); M(¹³CO₂) = 13.00335 + 2·15.999 (places 4) | AME2020 |
| `modules/elementrechner/tests/test_elementrechner.py::Analysis::test_molar_mass` | H2SO4 = 2·1.008 + 32.06 + 4·15.999 (places 6); Hill "H2O4S" | Test fixture weights |
| `modules/elementrechner/tests/test_design.py::Analyze::test_known_and_new` | Ethanol M 46.069 (places 2), DBE 0, monoisotopic mass 46.04186 (places 4) | — |
| `modules/elementrechner/tests/test_shared.py::TheoryTest::test_oxalate_chain` | Mass losses of CaC2O4·H2O: 12.33, 19.17 and 30.12 %; CaCO3 43.97 % (delta 0.02) | Test comment: "ASTM E1582 / Lehrbuchwerte" |
| `modules/elementrechner/tests/test_shared.py::TheoryTest::test_unbalanced_input_is_balanced_and_gas_required` | Mg(OH)2 30.89 %, Al(OH)3 34.64 % (delta 0.05) | — |

Not tested: u(M), the mass fractions and `empirical_formula`.

## 3 Balancing

**What:** stoichiometric coefficients ν with A·ν = 0, where A is the composition matrix (`chem.py:525-822`).

**Algorithm:**
* **Matrix:** one row per element or isotope key, plus a charge row if any species is charged. One column per
  species; reactant columns are negated (`conserved`, `chem.py:576-603`).
* **Null space:** reduced row echelon form over exact fractions (`_rref`, `chem.py:525-546`), then a null-space basis
  (`chem.py:549-562`).
* **Exactly one solution direction:**
  * The vector is scaled by the least common multiple of its denominators and divided by the gcd. This gives the
    smallest integers (`chem.py:565-573`).
  * The sign is chosen so that most entries are positive.
  * A coefficient ≤ 0 means the species is on the wrong side, or does not take part. This is reported as such.
* **No solution:** "impossible". An element that appears on one side only is named (`chem.py:721-728, 785-794`).
* **Several independent solutions:** "ambiguous". The module reports the dimension and an integer basis and does not
  pick one (`chem.py:729-734, 799-801`).
* **Some coefficients given:** the remaining ones are solved from A_u·x_u = −A_f·x_f. Fractions are allowed: ½ N₂
  gives 3/2 H₂ (`chem.py:741-771`).
* **All coefficients given:** the equation is checked. If it fails, the unbalanced rows are named and a correct set is
  suggested (`chem.py:703-712`).

**Nuclear equations** (`_balance_nuclear`, `chem.py:626-692`):
* The rows are mass number A and charge number Z.
* Unknown particle coefficients on the product side are solved and must be positive integers.
* One `?` per equation is identified from (ΔA, ΔZ) (`_identify`, `chem.py:616-623`):
  * (1,0) → n; (1,1) → p; (4,2) → α; (0,−1) → β⁻; (0,1) → β⁺; (2,1) → ²H; (3,1) → ³H; (0,0) → γ;
  * otherwise the nuclide of element Z with mass number A.
* Lepton number is not checked. A `?` with ΔA = ΔZ = 0 is always read as γ, never as a neutrino.

**Uncertainty:** not applicable. The arithmetic is exact. No citation in code.

**Validation:**

| Test | Checks |
|---|---|
| `sdk/python/tests/test_chem.py::Balance::test_textbook` | C3H8 + O2 → [1,5,3,4]; KMnO4 + HCl → [2,16,2,2,8,5]; MnO4⁻ + Fe²⁺ + H⁺ → [1,5,8,1,5,4]; Ca(OH)2 + H3PO4 → [3,2,1,6]; N2 + 3 H2 ⇌ 2 NH3 |
| `sdk/python/tests/test_chem.py::Balance::test_fixed_coefficients` | ½ N2 + H2 → NH3 gives [1/2, 3/2, 1]; "2 H2 + 1 O2 -> 3 H2O" is reported wrong ("H: links 4, rechts 6") and [2,1,2] is suggested |
| `sdk/python/tests/test_chem.py::Balance::test_problems_are_explained` | H2O → H2O2 impossible; H2 + O2 → H2O2 + H2O ambiguous (dimension 2); NaCl → Na + Cl2 + K impossible ("K kommt nur rechts vor") |
| `sdk/python/tests/test_chem.py::Balance::test_nuclear` | ²³⁵U + n fission gives 3 n; ²³⁸U → ²³⁴Th + ? gives α; ²⁷Al + α → ³⁰P + ? gives n; a wrong equation names "A: links 238, rechts 239" |
| `modules/elementrechner/tests/test_elementrechner.py::Server::test_meta_and_run` | Fe + O2 → Fe2O3 gives [4,3,2] |
| `modules/elementrechner/tests/test_redox.py::Redox::test_medium_balancing` | Half-reactions balanced in acidic or basic solution (exact strings) |

The expected coefficients are textbook results. No source is named in the tests.

## 4 Amounts, limiting reagent, yield and atom economy

**What** (`chem.py:963-1033`):
* **Amount:** n = m/M, n = c·V, or n = pV/(RT). In the amounts table the gas defaults are T = 273.15 K and
  p = 101 325 Pa, which is 1 atm and not IUPAC STP (`chem.py:977-978`).
* **Extent of reaction:** ξᵢ = nᵢ/νᵢ for each reactant with an entered amount. ξ = min ξᵢ, and that reactant is the
  limiting reagent. Reactants without an amount are treated as in excess.
* **Theoretical product:** ν·ξ. Excess: n − ν·ξ. Yield % = 100·n(obtained)/n(theoretical).
* **Atom economy %** = 100·ν_P·M_P / Σ ν_E·M_E over the reactants. The report cites `trost1991` (`bundle.py:2151`).
* **Reaction chains** (`chain.py`): the step equations are multiplied by step factors and summed into an overall
  equation. ΔrH°, ΔrG° and lg K are summed with the same factors (Hess's law, 298.15 K). The overall yield is the
  product of the step yields along the chain.
* No uncertainty is propagated.

**Validation:**

| Test | Checks |
|---|---|
| `modules/elementrechner/tests/test_elementrechner.py::Analysis::test_stoich_limiting_and_yield` | Limiting reagent O2; ξ = 20/31.998/5 (places 9); yield = 100·(15/44.009)/(3ξ) (places 6) |
| `modules/elementrechner/tests/test_data.py::Thermo::test_propane_combustion` | Heat for 44.097 g propane −2219.2 kJ (delta 1.5) |
| `modules/elementrechner/tests/test_chain.py::ChainTest::test_hess_equals_direct_overall` | Chain Hess sum equals the direct ΔrH° and ΔrG° of the overall equation (places 6) |
| `modules/elementrechner/tests/test_chain.py::ChainTest::test_forward_amounts_and_overall_yield` | Limiting feed CaO; overall yield 72.0 % |
| `modules/elementrechner/tests/test_chain.py::ChainTest::test_target_mode` | Atom economy 100·74.0927/(100.0869 + 18.0153) (places 2) |

These are internal consistency checks with hand-calculated values.

## 5 Reaction type and net ionic equation

**Reaction type** (`rxtype.py:42-110`): a suggestion, shown with its reason. The rules are applied in this order:
1. Nuclear.
2. Half-reaction (electrons appear in the equation).
3. Redox (oxidation numbers change). Sub-types: combustion, disproportionation, comproportionation, displacement.
4. Otherwise, one of:
   * acid–base, from pKa data; called neutralisation if water forms;
   * precipitation;
   * complex formation;
   * synthesis, decomposition or metathesis, by counting species.

Header in code: "Lehrbuch-Einteilung, Atkins 2018".

**Net ionic equation** (`redox.py:417-519`):
* These are split into ions:
  * dissolved salts;
  * strong acids: HCl, HBr, HI, HNO3 and HClO4 (`acidbase.py:23-24`, "Harris 2016");
  * H2SO4, as 2 H⁺ + SO4²⁻.
* These are kept together:
  * sparingly soluble salts;
  * species marked (s), (l), (g) or (cr);
  * water, weak acids and metals.
* Spectator ions cancel.
* A salt counts as sparingly soluble if its molar solubility s = 10^((lg Ksp − Σνᵢ lg νᵢ)/Σνᵢ) is below 0.01 mol/L
  (`substances.py:410-441`). The code comments this threshold "Lehrbuchgrenze … (Harris 2016)". The solubility is
  ideal: no activities and no side reactions.
* Ksp comes from NIST SRD 46. If SRD 46 has none, it is calculated from ΔfG° and labelled "berechnet"
  (`substances.py:449-467`).

**Validation:**

| Test | Checks |
|---|---|
| `modules/elementrechner/tests/test_redox.py::Ionic::test_net_ionic` | AgNO3 + NaCl → "Ag^+ + Cl^- -> AgCl"; Cu + HNO3 → "3 Cu + 8 H^+ + 2 NO3^- -> 3 Cu^2+ + 2 NO + 4 H2O"; four more exact strings |
| `modules/elementrechner/tests/test_redox.py::Ionic::test_solubility` | AgCl and BaSO4 sparingly soluble; NaCl and CuSO4 not |
| `modules/elementrechner/tests/test_redox.py::ReactionType::test_types` | Precipitation, acid–base, combustion, disproportionation, decomposition, half-reaction |

## 6 Thermochemistry at 298.15 K

### Which data set is used

Formation data come from `thermo.json` and from own substances. When several data sets have the same species, the
priority is (`thermo.py:31`, `PRIO`):

1. **own value** (own substance, with its source);
2. **CODATA Key Values** (Cox et al. 1989);
3. **NBS tables** (Wagman et al. 1982, NIST digital edition 2020);
4. **Burcat/ATcT** (Goos, Burcat & Ruscic 2018). ΔfH° is the ATcT value where the Burcat comment gives one;
5. **Benson estimate** (molecule designer);
6. **Joback estimate** (molecule designer).

Ties are broken in this order (`thermo.py:225-230`):
1. entries with both ΔfH° and S°;
2. the lowest ΔfG°, which picks the most stable modification (graphite before diamond, calcite before aragonite);
3. entries without an unresolved G–H–S mismatch.

The CODATA Key Values have no Cp°. Cp° is then taken from the next data set that has the same phase
(`thermo.py:326-331`). Every species can be switched to another data set in the page.

**Phase:**
* A given phase is used as written; (s) means cr.
* An ion without a phase is taken as aq, else g.
* A neutral (aq) species uses the undissociated "ao" entry before "ai".
* A neutral species without a phase takes the phase with the lowest ΔfG° among cr, l and g. The am and vit phases are
  never chosen automatically (`thermo.py:233-289`).

**Calculated ΔfG°:** where a table gives no ΔfG°, ΔfG° = ΔfH° − T·ΔfS°/1000 is used (`thermo.py:125-132`).
* ΔfS° = S° − Σ nₑ·S°(element) + z·S°(H₂)/2.
* The reference entropies per atom of the elements are stored in `thermo.json` (`refS`). They are taken from CODATA,
  or from NBS where CODATA has none.
* These values carry `Gcalc` and are marked with * in the page.

**Digitisation errors in the NBS file:** when the file was built, every NBS entry was checked against
ΔfG° = ΔfH° − TΔfS°. If the mismatch is over 2 kJ/mol, a decimal shift of ΔfH° or S° by ×10 or ×0.1 is accepted
when it brings the mismatch below 0.5 kJ/mol. Element symbols written in the wrong case are also corrected. Each fix is
stored with the value and shown in the report. The build script is `modules/elementrechner/tools/build_thermo.py`; it
reads raw files that are not in the repository.

### Formulas (`thermo.py:309-407`)

* ΔrX = Σ νᵢ·Xᵢ for X = ΔfH°, S°, ΔfG° and Cp°.
* ΔrG° is computed by two routes:
  * ΔrG°(HS) = ΔrH° − T·ΔrS°;
  * ΔrG°(f) = Σ ν·ΔfG°.

  The **reported ΔrG° is the HS route** when ΔH and S are complete, else the ΔfG° route (`thermo.py:358`). The
  difference between the two is shown.
* ln K = −ΔrG°/(R·298.15 K); lg K = ln K / ln 10. K is reported as ∞ if ln K ≥ 700.
* Kc (gas reactions without aq species, Δn_gas ≠ 0): lg Kc = lg K + Δn_gas·lg(p°/(R·T·c°)) (`thermo.py:372-377`).
* T* = ΔrH°/ΔrS°, given only when ΔH and ΔS have the same sign. The four sign cases are described in words.
* **Heat:** Q = ξ·ΔrH°. Per reactant: ΔrH/ν in kJ/mol and ΔrH/ν/M in kJ/kg. With O₂ as a reactant and CO₂ or H₂O as
  a product, the reaction counts as a combustion. The phase of water decides between gross heating value (water liquid)
  and net heating value (water gaseous).
* **Other temperatures, constant model:** ΔrG(T) = ΔrH° − T·ΔrS°, labelled as an approximation. For the Cp(T) model
  see section 7.
* **Calculated Ksp:** lg Ksp = −ΔrG°/(RT ln 10) for MₐLᵦ(s) ⇌ a M + b L, from formation data, labelled "berechnet".

### Uncertainty

* u(ΔrH°) = √Σ(νᵢ·u(ΔfH°)ᵢ)², and likewise for ΔrS° (`thermo.py:346-354`). Independence is assumed.
* Only CODATA entries and ATcT-based Burcat entries carry uncertainties. NBS entries have none. If any species with
  ΔfH° ≠ 0 lacks an uncertainty, the result is flagged as incomplete, and the page says so.
* The coverage of the CODATA and ATcT ± values is not stated in the code. They are combined as given.
* No uncertainty is computed for ΔrG°, K, Kc or T*. The report section does not print u(ΔrH°).

### Sources in code

`SRC_REFS` (`thermo.py:301-306`) maps each data set to its references:
* CODATA → cox1989;
* NBS → wagman1982, reed2020;
* Burcat → burcat2018, burcat2005, plus atct2004 for ATcT values;
* Benson → domalski1993, benson1969;
* Joback → joback1987, joback_wiki.

### Validation

The `Thermo` tests state "Sollwerte: CODATA Key Values 1989 und NBS-Tabellen 1982 (Hess-Summen von Hand
nachgerechnet)". They check the implementation against hand calculations from the same tables. They are not an
independent comparison.

| Test | Checks (expected, tolerance) |
|---|---|
| `modules/elementrechner/tests/test_data.py::Thermo::test_species_choice` | Default phases H2O → l, C → cr, Br2 → l, Na⁺ → aq, CH3COOH(aq) → ao; ΔfH°(H2O, l) = −285.83 (places 2), source CODATA |
| `modules/elementrechner/tests/test_data.py::Thermo::test_methane_combustion` | ΔrH° −890.36 (delta 0.05); ΔrG° −817.9 (delta 0.2); the two ΔrG° routes agree within 0.05 kJ/mol |
| `modules/elementrechner/tests/test_data.py::Thermo::test_propane_combustion` | ΔrH° −2219.2 (delta 1.0); gross heating value 50.3 MJ/kg (delta 0.1) |
| `modules/elementrechner/tests/test_data.py::Thermo::test_haber_bosch` | ΔrH° −91.88 (delta 0.1); ΔrS° −198.1 (delta 0.3); T* 463.8 K (delta 1.5); lg K 5.75 (delta 0.03); Δn_gas −2 |
| `modules/elementrechner/tests/test_data.py::Thermo::test_decomposition_and_ions` | CaCO3 T* 1123 K (delta 5); Ag⁺ + Cl⁻ → AgCl lg K 9.75 (delta 0.05) |
| `modules/elementrechner/tests/test_data.py::Thermo::test_ksp_from_formation_data` | Calculated lg Ksp: BaSO4 −10.06, AgCl −9.75 (delta 0.05) |
| `modules/elementrechner/tests/test_data.py::Thermo::test_digitisation_fixes` | BaSO4(aq, ai) ΔfH° −1446.91 (delta 0.01), with the fix recorded |
| `modules/elementrechner/tests/test_data.py::Thermo::test_calc_functions` | Calculator functions: dHr −890.36; dfH("H2O(l)") −285 830 J/mol; Cpm0(H2O, l) 75.29 (delta 0.05, from NBS since CODATA has no Cp) |
| `modules/elementrechner/tests/test_elementrechner.py::Server::test_own_thermo_values` | Own value takes precedence over the table; calculated ΔfG°(H2O2, l) −120.33 (delta 0.01) |
| `modules/elementrechner/tests/test_benson_thermo.py::BensonPriority::test_table_value_beats_benson`, `::test_benson_preferred_over_joback` | Priority of tables over Benson over Joback |
| `modules/elementrechner/tests/test_design.py::Estimates::test_thermo_uses_estimate_with_warning` | Estimates are used only without table data, with a warning |

## 7 Temperature dependence, equilibrium composition and flame temperature

### Cp(T) with NASA-7 polynomials (`thermo_t.py`)

**Polynomials** (Burcat data; form as in McBride et al. 2002):
* Cp/R = a₁ + a₂T + a₃T² + a₄T³ + a₅T⁴
* H/(RT) = a₁ + a₂T/2 + a₃T²/3 + a₄T³/4 + a₅T⁴/5 + a₆/T
* S/R = a₁ ln T + a₂T + a₃T²/2 + a₄T³/3 + a₅T⁴/4 + a₇

The low-temperature set is used for T ≤ T_mid (`thermo_t.py:22-39`).

**Model "cp"** (default for the curve):
* ΔrH(T) = ΔrH°(298.15 K) + Σν[H(T) − H(298.15 K)], and likewise for S.
* ΔrH°(298.15 K) and ΔrS°(298.15 K) are the values chosen in section 6. The polynomials supply only the temperature
  course (`thermo_t.py:95-112`). The 298 K values and the increments can therefore come from different data sets.
* A species without its own polynomial takes the polynomial of the same phase and InChIKey (`thermo_t.py:52-67`).

**Other models:**
* "cp298": ΔCp constant at its 298 K value. ΔH + ΔCp(T − T₀) and ΔS + ΔCp·ln(T/T₀).
* "const": ΔH and ΔS constant. It is always shown alongside (dashed curve).

**Results:**
* lg K(T) and lg Kc(T).
* The temperature at which ΔrG = 0. It is found by bisection between 200 and 3000 K, and only if the sign changes
  there (`thermo_t.py:129-137`).
* van 't Hoff: ln K₂ = ln K₁ − ΔH/R·(1/T₂ − 1/T₁).

**Limits:**
* T must be 50–6000 K (`thermo_t.py:73-74`).
* A T outside a polynomial's validity range (±1 K) is flagged.
* Phase transitions are not modelled; a note says so for cr and l species (`thermo_t.py:115-117`).

### Equilibrium composition (`equilibrium.py`)

* **Activities:** gases x·p/p°; solutes c/c°; pure solids and liquids 1.
* **Method:** Σν ln aᵢ(ξ) = ln K, solved by bisection on the feasible range of ξ (tolerance 10⁻¹², up to 200
  iterations).
* If there is no root, complete forward or back reaction is reported. The behaviour is ideal, and a note says so.
* The page uses ln K at the chosen T from the Cp(T) model. By default the initial amounts are the reactant
  coefficients.

### Adiabatic flame temperature (`flame.py`)

* **Balance:** constant pressure, with Σn_E[ΔfH° + H(T₀) − H(298)] = Σn_P[ΔfH° + H(T_ad) − H(298)].
* **Products:** complete combustion to CO₂, H₂O(g), N₂ and SO₂, plus excess O₂. Dissociation is not included; the
  note puts the result "rund 100 K über dem Gleichgewichtswert" for methane/air.
* **Air:** N₂/O₂ = 79/21, with Ar counted as N₂.
* **Limits:** equivalence ratio φ = 0.2–1. The fuel may contain C, H, O, N and S.
* **Solver:** bisection between 298.15 and 6000 K.

### Validation

| Test | Checks (expected, tolerance) | Reference as stated in the test |
|---|---|---|
| `modules/elementrechner/tests/test_thermo_t.py::CpModel::test_nh3_log_kf_against_janaf` | lg Kf(NH3, g) −0.501 / −2.029 / −3.234 at 500 / 700 / 1000 K (delta 0.01) | NIST-JANAF Thermochemical Tables (Chase 1998), table H-083 NH3(g) |
| `modules/elementrechner/tests/test_thermo_t.py::CpModel::test_constant_approximation_differs` | The constant model is more than 0.1 off at 1000 K | — |
| `modules/elementrechner/tests/test_thermo_t.py::CpModel::test_298_matches_table` | The Cp model reproduces the 298 K values (delta 0.05) | — |
| `modules/elementrechner/tests/test_thermo_t.py::CpModel::test_t_eq` | T(ΔrG = 0) between 400 and 500 K; ΔG(T_eq) = 0 (delta 0.01) | — |
| `modules/elementrechner/tests/test_thermo_t.py::CpModel::test_out_of_range_warning` | H2O(l) polynomial (273.15–600 K) flagged at 800 K | — |
| `modules/elementrechner/tests/test_thermo_t.py::Equilibrium::test_n2o4_dissociation_atkins` | N2O4 ⇌ 2 NO2: degree of dissociation 0.19 (delta 0.01); ξ = √(K/(K+4)) (delta 10⁻⁶) | Atkins, Physical Chemistry |
| `modules/elementrechner/tests/test_thermo_t.py::Equilibrium::test_ammonia_composition_satisfies_k` | ln Q = ln K (delta 10⁻⁶) at 1, 100 and 300 bar | Self-consistency |
| `modules/elementrechner/tests/test_kinetics.py::Flame::test_methane_air_against_janaf` | T_ad(CH4/air, φ = 1) 2326.6 K (delta 5); between 2276 and 2376 K | Same energy balance with NIST-JANAF tables C-095, H-064, N-023 and ΔfH°(CH4) = −74.87 kJ/mol (Chase 1998); equilibrium value with dissociation 2226 K (Turns 2012) |

## 8 Estimated properties

All estimates are labelled with their method and source. They take the lowest priority (section 6), and results that
use them carry a warning.

### Benson group additivity (`benson.py`, `benson_groups.json`)

**What:** ΔfH°(g), S°(g) and Cp°(g) at 298.15 K, without Cp(T).

**Formulas:**
* ΔfH = Σ nᵢ·ΔfHᵢ + corrections; Cp likewise.
* S = Σ nᵢ·Sᵢ + corrections − R ln σ + R ln η.
* σ is the total symmetry number, taken from the molecular graph as the number of proper rotations, including internal
  CH₃ and C(CH₃)₃ rotors.
* η = 2 for one stereocentre.
* S° is left out for more than one stereocentre, or when σ cannot be determined.
* Corrections: methyl repulsions, cis, and ortho/meta.
* R = 8.31451 J/(mol K), "wie bei Domalski & Hearing (S. 808)", so that their calculated values are reproduced
  exactly.

**Scope:** neutral molecules of C, H and O only, without fused, bridged or non-aromatic rings. Refused instead of
estimated:
* methane and formaldehyde;
* allenes and ketenes;
* tert-butyl on C=C;
* ambiguous cis on tri- or tetrasubstituted C=C;
* ortho/meta pairs other than hydrocarbon, OH or OR;
* any group missing from the table.

**Stated accuracy** (meta field `accuracy`): "D&H S. 809: Abweichungen bis +-4 kJ/mol (dfH) bzw. +-4 J/(mol K)
(Cp, S) gelten als sehr zufriedenstellend, +-4 bis +-8 als Grenze des Annehmbaren; Gasphase Kohlenwasserstoffe: 70 %
der Residuen von dfH < 4 kJ/mol; CHO: 62 % (dfH), 72 % (S)."

**Standard state:** the table title gives the standard pressure as 101.325 kPa. The values are combined with 1-bar
table data without conversion. For a gas S° the difference is R ln(1.01325) ≈ 0.11 J/(mol K).

| Test | Checks | Reference |
|---|---|---|
| `modules/elementrechner/tests/test_benson.py::Reproduce::test_dh_calculated_values` | 15 molecules: ΔfH, Cp and S (delta 0.015) and σ exactly, for example isobutane −134.73 kJ/mol, 97.27 and 291.82 J/(mol K), σ = 81 | "Calculated" column of Domalski & Hearing 1993, Tables 5–21 (page per row in the test) |
| `modules/elementrechner/tests/test_benson.py::Accuracy::test_against_tabulated` | 18 molecules against the Burcat gas-phase entries in `thermo.json`: ΔfH and S within 4 | Tolerance per D&H p. 809 |
| `modules/elementrechner/tests/test_benson.py::Accuracy::test_heat_capacity` | Cp within 4 J/(mol K) for 10 molecules | Burcat entries |
| `modules/elementrechner/tests/test_benson.py::Refusal::test_design_integration` | Acetone ΔfH −217.19 (delta 0.015) | D&H |

### Joback and Reid (`joback.py`)

**Properties and formulas** (`joback.py:9-16`):
* Tb = 198.2 + ΣTb; Tm = 122.5 + ΣTm.
* Tc = Tb/(0.584 + 0.965ΣTc − (ΣTc)²).
* Pc = (0.113 + 0.0032·N_atoms − ΣPc)⁻²; Vc = 17.5 + ΣVc.
* ΔfH°(g) = 68.29 + ΣH; ΔfG°(g) = 53.88 + ΣG.
* Cp°(g)(T) = (Σa − 37.93) + (Σb + 0.210)T + (Σc − 3.91·10⁻⁴)T² + (Σd + 2.06·10⁻⁷)T³, for 273–1000 K.
* ΔHvap(Tb) = 15.30 + Σ; ΔHfus = −0.88 + Σ.
* Liquid viscosity η = M·exp((Σηa − 597.82)/T + Σηb − 11.202), only if Tm < 298.15 K < 0.7·Tc.

**S°(g):** derived as (ΔfH° − ΔfG°)/T + Σ S°(elements) (`design.py:200-203`). Errors in the group values are
amplified in this difference.

**Scope:** C, H, O, N, S and halogens. Refused:
* charged species, except nitro;
* methane, formaldehyde and carbonates;
* lactone carbonyls;
* sulfones;
* several fragments.

**Accuracy:** no numerical accuracy is stated in the code. Melting points are described as "nur grob" (rough only,
`joback.py:232`).

**Source in code:** Joback & Reid 1987, Chem. Eng. Commun. 57, 233-243, doi:10.1080/00986448708960487. The group
values are taken from the tabular reproduction in the Wikipedia article "Joback method" (accessed 17.11.2026, CC BY-SA
4.0) and checked on the worked example acetone given there.

| Test | Checks | Reference |
|---|---|---|
| `modules/elementrechner/tests/test_design.py::Joback::test_acetone` | Tb 322.11 K, Tc 500.56 K, Pc 48.03 bar, ΔfH° −217.83, ΔfG° −154.54 kJ/mol (delta 0.01) | Worked example acetone from the Joback table (Wikipedia) |

### Other estimates

* **Bond-enthalpy estimate of ΔrH** (`bonds.py`):
  * ΔrH ≈ Σ D(bonds broken) − Σ D(bonds formed), with bonds counted from the structures. All species are treated as
    gases.
  * The code describes the per-bond scatter as "typisch ±10–30 kJ/mol je Bindung" and the deviation from the
    tabulated ΔrH as "oft 10–100 kJ/mol". It is always shown next to the tabulated value.
  * Tests (`modules/elementrechner/tests/test_bonds.py::Bonds::*`) check the arithmetic against the module's own table
    only.
* **log P, log S and TPSA** of a drawn structure are computed in the browser by OpenChemLib 9.26.0. They are cited as
  Sander et al. 2015 (log P, log S) and Ertl et al. 2000 (TPSA). No automated test in this module checks them.
* **Acid–base hints** for a drawn structure point to a related collection compound and its measured pKa. No pKa is
  predicted.

## 9 Acid–base: pH, pKw(T), titration, indicators and buffers

### pH of a mixture (`acidbase.py`)

**Model:** proton balance relative to the forms put in (`acidbase.py:4-7, 288-296`):

[H⁺] − [OH⁻] = Σᵢ cᵢ(hᵢ − n̄ᵢ) + c(strong acid) − c(strong base)

* hᵢ is the number of protons of the form put in, and n̄ᵢ the mean number at the current pH.
* Species fractions αⱼ come from cumulative Σ(pKaⱼ − pH) (`acidbase.py:266-284`).
* Strong acids (fully dissociated): HCl, HBr, HI, HNO3, HClO4, and the first step of H2SO4. OH⁻ is a strong base.
* Spectator ions are listed in `acidbase.py:25-26`.
* Metal-ion hydrolysis is ignored, with a note. A neutral substance without pKa data is treated as inert, with a note.

**Solver:** bisection on pH in [−2, 16.5], 80 iterations. A root outside that range is refused (`acidbase.py:299-310`).

**Ideal solution by default:**
* concentrations, not activities;
* ionic strength I = ½Σcᵢzᵢ², shown;
* a note appears above I = 0.01 mol/L (`acidbase.py:356-372`);
* for activity corrections see section 10.

**Which pKa** (`acid_system`, `acidbase.py:96-153`):
1. NIST SRD 46 protonation constants, if there are any.
2. Otherwise the IUPAC pKa dataset (if installed).
3. Otherwise single values from the PubChem property records or own values.

Among several values for the same step, `substances.choose` (`substances.py:325-336`) sorts by:
1. within 2.5 °C of 25 °C;
2. water as the medium;
3. ionic strength 0;
4. rating: own value, then SRD 46 "kritisch ausgewählt", then IUPAC "Reliable", "Approximate", unrated, calculated,
   "Uncertain", "Very uncertain";
5. distance in T;
6. I.

The chosen value and its source are shown, and the choice can be changed.

### pKw(T)

* **Formula** (`acidbase.py:39-64`): Bandura & Lvov 2006, with the density of water from Kell 1975 at 1 atm.
* **Values:** pKw = 14.946, 13.995, 13.264, 12.696 and 12.252 at 0, 25, 50, 75 and 100 °C.
* **Range:** 0–100 °C; other temperatures are refused.
* **Exactly 25 °C:** the function returns the constant 13.995 ("Bandura & Lvov 2006, 25 °C, 0,1 MPa",
  `substances.py:23`). The formula itself gives 13.99452 there.
* **pKa values are not converted to other temperatures.** Only pKw follows T. Every pKa measured more than 2 °C away
  from the chosen T is named in a note (`acidbase.py:331-343`).
* **pKb:** pKb = 13.995 − pKa(conjugate acid), always at 25 °C (`substances.py:364`).

### Titration curve, equivalence points and indicators

* **Curve:** pH at 161 evenly spaced titrant volumes, with dilution.
* **Equivalence points:** local maxima of |ΔpH/ΔV| above 5 % of the largest slope and above 0.05 (`acidbase.py:404`).
  Each is refined by 30 golden-section steps (`acidbase.py:406-415`).
* **Indicators:** for each equivalence point, the titration error 100·(V − V_eq)/V_eq is computed at the middle and
  at both ends of each indicator's transition range.
  * "geeignet" (suitable): |error| ≤ 0.2 % at the middle and ≤ 1 % at both ends.
  * "bedingt" (conditional): ≤ 1 % at the middle (`acidbase.py:457-502`).
* **Data:** transition ranges from `indicators.json` (Harris 2016). The colour swatches are display aids only.

### Buffers

* **Buffer finder:**
  * acid–base pairs from NIST SRD 46 with |pKa − pH| ≤ 1;
  * 21 common laboratory buffers listed first ("Harris 2016, Kap. Puffer; Good et al. 1966", `acidbase.py:576-579`).
* **Composition:** Henderson–Hasselbalch for the step nearest the target pH (`acidbase.py:513-530`).
* **Buffer capacity:** β = ln 10·([H⁺] + [OH⁻] + Σⱼ c·αⱼ(j − n̄)²).
* **Buffer recipe from real chemicals** (`prep.buffer_recipe`, `prep.py:478-552`): either two forms, or one form plus
  a titrant from a stock solution.
  * Solved by bisection (60 iterations) on the full proton balance at the temperature of the pH tab.
  * Water of crystallisation is removed before the pH calculation.
  * An unreachable pH is refused, and the reachable range is given.

**Uncertainty:** SRD 46 values carry an uncertainty in the data, but it is not propagated. No uncertainty is given for
pH, equivalence volumes or buffer compositions.

### Validation

| Test | Checks (expected, tolerance) | Reference as stated in the test |
|---|---|---|
| `modules/elementrechner/tests/test_redox.py::AcidBase::test_ph_values` | pH of 0.1 M HCl 1.00; 0.1 M CH3COOH 2.88; acetate buffer 1:1 4.76; 0.1 M NH3 11.12; 0.1 M Na2CO3 11.65; 10⁻⁸ M HCl 6.98 (all delta 0.015) | Header: "pH (Harris 2016, Rechenbeispiele)" |
| `modules/elementrechner/tests/test_redox.py::AcidBase::test_titration` | 0.1 M acetic acid with NaOH: V_eq 25.0 mL (delta 0.05), pH at equivalence 8.72 (delta 0.1) | Header: "Äquivalenz 25,00 mL bei pH ≈ 8,7" |
| `modules/elementrechner/tests/test_redox.py::AcidBase::test_pkw_temperature` | pKw 14.946 / 13.995 / 13.264 / 12.696 / 12.252 at 0 / 25 / 50 / 75 / 100 °C (delta 0.002); ρ(4 °C) 999.97 kg/m³ (delta 0.01); 120 °C refused; neutral pH at 50 °C = 13.264/2 | "Tabelle bei 0,1 MPa in Bandura & Lvov 2006"; density maximum (Kell 1975) |
| `modules/elementrechner/tests/test_redox.py::AcidBase::test_indicators` | Acetic acid/NaOH: phenolphthalein "geeignet" with \|error\| < 0.2 %, methyl orange not listed; NH3/HCl: methyl red listed, phenolphthalein not | — |
| `modules/elementrechner/tests/test_redox.py::AcidBase::test_run_state` | 0.1 M NH4Cl pH 5.12 (delta 0.02) | — |
| `modules/elementrechner/tests/test_redox.py::AcidBase::test_common_buffers_first` | All 21 common buffers resolve to SRD 46 data; HEPES and phosphoric acid in the top 5 at pH 7.4 | — |
| `modules/elementrechner/tests/test_prep.py::BufferRecipe::test_phosphate_pair` | Recipe check pH 7.40 (delta 0.005) | Self-consistency |
| `modules/elementrechner/tests/test_prep.py::BufferRecipe::test_tris_with_hcl` | Check pH 7.40 (delta 0.005); Tris mass 0.05·0.5·121.135 g | Self-consistency |
| `modules/elementrechner/tests/test_data.py::Collection::test_pka_values` | Acetic acid pKa 4.76 (delta 0.01, source SRD 46); H3PO4 2.15 / 7.20 (delta 0.1) / 12.35 (delta 0.2); pKb(NH3) 4.75 (delta 0.05) | — |
| `modules/elementrechner/tests/test_elementrechner.py::Substances::test_choice_rule` | Choice rule: SRD 46 at I = 0 before I = 0.1 and before IUPAC "Reliable" | Test fixture |

## 10 Activity corrections (`activity.py`)

**Models** (switchable; the result is shown next to the ideal one):
* **Davies:** lg γ = −A z²(√I/(1 + √I) − 0.3 I). Docstring: "Davies (1962), brauchbar bis I ≈ 0,5 mol/L".
* **Extended Debye–Hückel:** lg γ = −A z² √I/(1 + B a √I). Docstring: "brauchbar bis I ≈ 0,1 mol/L".

**Parameters:**
* A = 1.82483·10⁶·√ρ/(εT)^(3/2) and B = 50.2916·√ρ/(εT)^(1/2) Å⁻¹. At 25 °C, A = 0.511 and B = 0.329.
* ρ from Kell 1975. ε(t) = 87.740 − 0.40008 t + 9.398·10⁻⁴ t² − 1.410·10⁻⁶ t³ (Malmberg & Maryott 1956).
* Valid 0–100 °C (`activity.py:28-40`).

**Ion sizes:**
* H⁺ 900 pm and OH⁻ 350 pm (Kielland 1937).
* Other ions by charge: 400, 600, 900 and 1100 pm for |z| = 1, 2, 3 and ≥ 4. This is an assumption, and it is stated
  in the result (`activity.py:19-20`).

**Limits:**
* Above I = 0.5 (Davies) or 0.1 mol/L (extended Debye–Hückel), the result gets a "Werte nur grob" note. It is not
  refused (`activity.py:17, 62-64`).
* Neutral species have γ = 1.

**Corrected pH:**
* Mixed constants pKa′ = pKa + lg γ(z_{j−1}) − lg γ(z_j).
* I is recomputed and the pH re-solved until the relative change is below 10⁻¹², up to 60 times. There is no warning
  if it does not converge (`activity.py:71-125`).

| Test | Checks | Reference as stated |
|---|---|---|
| `modules/elementrechner/tests/test_activity.py::Gamma::test_constants_25` | A 0.511, B 0.329 (delta 0.002) | — |
| `modules/elementrechner/tests/test_activity.py::Gamma::test_kielland_table` | γ for six (z, a) pairs at I = 0.001, 0.01 and 0.1 (delta 0.01), for example z = 1, a = 900 pm: 0.967 / 0.914 / 0.83 | "Kielland (1937), Tabelle der Einzelionen-Aktivitätskoeffizienten bei 25 °C (auch bei Harris …)" |
| `modules/elementrechner/tests/test_activity.py::Gamma::test_davies` | γ(z = 1, I = 0.1) 0.78 (delta 0.01) | — |
| `modules/elementrechner/tests/test_activity.py::CorrectedPH::test_hcl` | 0.01 M HCl, extended Debye–Hückel: pH 2.04 (delta 0.01) | "Harris: a(H⁺) = 0,914·0,01" |
| `modules/elementrechner/tests/test_activity.py::CorrectedPH::test_acetate_buffer_at_I_01` | ΔpH −0.11 (delta 0.02) at I = 0.1 | — |

## 11 Speciation and saturation index (`speciation.py`)

**Model** (`speciation.py:4-8`):
* Mononuclear complexes MLₙ with lg βₙ (n = 1…8), optionally MHL.
* The pH is fixed (buffered).
* Polynuclear species and precipitates are not included; a note says so.
* Constants are used at the ionic strength at which they were measured. They are concentration constants and are not
  converted to another ionic strength.

**Mass balances** (`speciation.py:78-127`):
* [M]free = c_M/(1 + Σβₙ[L]ⁿ + K_MHL·β₁[L][H]).
* The ligand balance [L]/α_L + Σn[MLₙ] + [MHL] − c_L = 0 is solved by bisection in lg[L] (tolerance 10⁻¹³, up to 200
  iterations).
* α_L, the fraction of fully deprotonated ligand, comes from the ligand pKa values.
* Relative residuals of both balances are reported.
* The charge balance is not closed. The remainder is reported, with a note that buffer and counter-ions balance it.
* For hydroxide as a ligand, [OH⁻] = 10^(pH − 14.0). pKw is fixed at 14.0 and does not follow the temperature
  (`speciation.py:78, 93`).

**Conditional constants:** lg β′ₙ = lg βₙ + n·lg α_L. Only the ligand side reaction is included.

**Saturation index** (`speciation.py:130-167`):
* SI = lg(IAP/Ksp). The stoichiometry is taken from the ion charges.
* I = ½(c₊z₊² + c₋z₋²) + any extra ionic strength entered.
* Activity coefficients are applied only if the Ksp refers to I = 0 or no I is given.
* SI > 0.05 is reported as supersaturated and SI < −0.05 as undersaturated; in between, as near saturation. No amount
  of precipitate is predicted.

**Refused:**
* metal charge ≤ 0;
* no stability constants in SRD 46;
* incomplete ligand protonation constants;
* missing concentrations.

**Data:** `stability.json` (NIST SRD 46). The page adds the reference Baes & Mesmer 1976 for hydroxide.

| Test | Checks | Reference as stated |
|---|---|---|
| `modules/elementrechner/tests/test_speciation.py::Speciation::test_fe_hydrolysis_baes_mesmer` | Fe³⁺/FeOH²⁺ crossing at pH 2.19 (delta 0.03) | "lg *β₁ = −2,19 (Baes & Mesmer 1976)" |
| `modules/elementrechner/tests/test_speciation.py::Speciation::test_cu_nh3_balances_and_steps` | Residuals < 10⁻⁹; fractions sum to 1 (places 10); lg([ML]/[M]) = lg β₁ + lg[L] (places 8) | Internal consistency |
| `modules/elementrechner/tests/test_speciation.py::Speciation::test_ca_edta_conditional` | α_L against the closed formula (places 10); conditional constant (places 8) | Analytic |
| `modules/elementrechner/tests/test_speciation.py::Saturation::test_ksp_close_to_harris` | lg Ksp CaCO3 −8.47 and BaSO4 −9.96 (delta 0.15) | Harris; the test comment says the values were transferred from memory |
| `modules/elementrechner/tests/test_speciation.py::Saturation::test_caco3` | SI = −8 − lg Ksp (places 10); the Davies SI is lower than the ideal SI | Analytic |
| `modules/elementrechner/tests/test_data.py::Collection::test_ksp_and_complexes` | lg Ksp AgCl −9.75 (delta 0.01), Fe(OH)3 −38.8 (delta 0.1); 11.5 < lg β₄(Cu–NH3) < 13.5 | — |

## 12 Redox and electrochemistry (`redox.py`)

**Oxidation numbers:**
* **From a formula** (`redox.py:79-141`), rules in this order:
  1. F −1;
  2. alkali metals +1, alkaline-earth metals +2, Al +3, Zn +2;
  3. H −1 with metals only, else +1;
  4. O −2;
  5. the most electronegative remaining element takes its most negative common state;
  6. the last element follows from the charge.

  Results outside −5…+9 are refused, with a request for the structure.
* **From a structure** (`redox.py:144-182`): bonding electrons go to the more electronegative partner (Pauling values
  from `elements.json`), plus the formal charge (Karen et al. 2016).

**Half-reactions:** balanced through the null space, with e⁻ and H⁺/H₂O (acidic) or OH⁻/H₂O (basic) as free species.

**E° from formation data** (`redox.py:544-556`):
* E° = −ΔrG°(reduction)/(nF), with ΔrG° = Σν ΔfG° from section 6.
* ΔfG°(H⁺, aq) = ΔfG°(e⁻) = 0, so potentials refer to the standard hydrogen electrode.
* There is no separate table of standard potentials.
* E°cell = E°(cathode) − E°(anode), and ΔG° = −nFE°.

**Nernst** (`redox.py:640-669`):
* E = E° − (RT/nF)·ln Q.
* Pure solids, liquids and water have activity 1.
* a(H⁺) = 10^−pH if a pH is given.
* a(OH⁻) = 10^(pH − 13.995), with the 25 °C pKw at every T.
* Species without an entered value are at standard state (activity 1).

**Faraday** (`redox.py:729-778`):
* Q = I·t, n(e⁻) = Q/F, ξ = η·Q/(nF).
* The current efficiency η must be in (0, 1]; the default is 100 %.
* Electrolysis yield = measured mass / theoretical mass at η = 1.

| Test | Checks (expected, tolerance) | Reference as stated |
|---|---|---|
| `modules/elementrechner/tests/test_redox.py::OxidationNumbers::test_formula` | Mn in KMnO4 +7, Cr in Cr2O7²⁻ +6, Fe in Fe3O4 +8/3, O in H2O2 −1, H in NaH −1, O in OF2 +2 (exact) | "nach IUPAC (Karen et al. 2016), von Hand" |
| `modules/elementrechner/tests/test_redox.py::Redox::test_half_reaction_potentials` | E° Cu²⁺/Cu 0.337, Zn²⁺/Zn −0.763, MnO4⁻/Mn²⁺ 1.51, Cl2/Cl⁻ 1.36 V (delta 0.01), computed from ΔfG° | Textbook values, "Bard & Faulkner 2001 / Atkins 2018" |
| `modules/elementrechner/tests/test_redox.py::Redox::test_daniell_from_salts` | Zn + CuSO4: n = 2, E°cell 1.100 V (delta 0.01); Nernst E = E°cell − 0.05916 V (delta 0.0005) | — |
| `modules/elementrechner/tests/test_redox.py::Redox::test_faraday_efficiency_and_yield` | m(Cu) 2.3709 g for 7200 C (places 3); η = 120 % refused | "7200 C / (2 F) · 63,546 g/mol" |
| `modules/elementrechner/tests/test_redox.py::Redox::test_permanganate_hcl` | n = 10; E°cell 0.15 V (delta 0.01) | — |

## 13 Solution preparation, reaction set-up and green metrics

### Preparing solutions (`prep.py`)

**Principle:** the code makes no hidden assumptions (`prep.py:4-13`). The form weighed (for example CuSO₄·5H₂O) and
the reference species (for example Cu²⁺) are explicit. A density needs a source and a temperature. Solutions are
always filled up to volume; volumes are never added. Every step goes to a worksheet.

**Concentration bases:** mol/L, mmol/L, µmol/L, g/L, mg/L, % (w/v), % (w/w) and mol/kg. "ppm" means mg/L, aqueous,
and is labelled so (`prep.py:27-35`).

**Formulas** (`prep.py:170-207`):
* n = c·V; n = β·V/M.
* % (w/w): m = w·ρ·V.
* Molality: m(solvent) = m(solution)/(1 + b·M), n = b·m(solvent).
* % (w/w) and molality without a solution density are refused.
* Purity: m(weighed) = m(pure)/purity.
* Formula units per reference species: the minimum ratio over the elements other than H and O; it must be an integer.

**Rounding and flasks:** the mass is rounded to the balance readability, and the resulting actual concentration is
shown. Volumetric flask sizes follow DIN EN ISO 1042 (`prep.py:23`).

**Stock solutions:** c = w·ρ/M, with the density and its source required; V(aliquot) = n/c.

**Dilution series:** computed backwards, so that each step keeps its volume × replicates. Only linear bases are
allowed; 1–30 steps.

**Mixing:** Σcᵢ·Vᵢ = c·V for any one unknown. The total volume must not exceed the final volume.

### Reaction set-up and green metrics (`reaction_setup.py`)

* **Extent:** ξ = n(reference)/ν(reference). From a target product: ξ = n(target)/(ν·expected yield).
* **Amounts:** nᵢ = equivalentsᵢ·νᵢ·ξ, and m = n·M/purity. A volume needs a stock concentration or a density with its
  source.
* **Limiting reagent and excess** as in section 4.
* **Scaling** keeps equivalents, mol% and concentrations. Observed amounts sit beside the plan and never change it.
* **Green metrics:**
  * E-factor = (m_in − m_product)/m_product (Sheldon 2007).
  * PMI = m_in/m_product (Jimenez-Gonzalez et al. 2011).
  * RME = m_product/Σ m(reactants of the equation) (Constable et al. 2002).
  * Atom economy (Trost 1991).
  * Solvent share.
* **Counting boundary:** reagents, solvents, catalyst, additives or work-up. It is chosen by the user and printed with
  the values. The product mass is the isolated mass if one was entered, else the theoretical mass.
* **Masses:** weighed masses include the impurity fraction (m = n·M/purity).

**Uncertainty:** none.

| Test | Checks (expected, tolerance) |
|---|---|
| `modules/elementrechner/tests/test_prep.py::Solid::test_copper_sulfate` | 250 mL of 0.100 mol/L CuSO4: 6.242 g pentahydrate, 3.990 g anhydrous (delta 0.0005) |
| `modules/elementrechner/tests/test_prep.py::Solid::test_purity_and_rounding` | NaCl 5.844 g (delta 0.001); purity correction a/0.98 (places 9); 1.46 g after rounding |
| `modules/elementrechner/tests/test_prep.py::Stock::test_hcl_from_37_percent` | 1 L of 1 mol/L HCl from 37 % HCl, ρ = 1.184 g/mL: 83.2 mL (delta 0.1) |
| `modules/elementrechner/tests/test_prep.py::Stock::test_certified_standard_and_c1v1` | 1.0 mL and 10.0 mL (places 9) |
| `modules/elementrechner/tests/test_prep.py::Dilution::test_series_1_to_10` | Stock needed 1.1111 mL (places 9) |
| `modules/elementrechner/tests/test_prep.py::Core::test_density_needs_source_and_temperature` | Refusal without a sourced density |
| `modules/elementrechner/tests/test_setup.py::Setup::test_table` | Reagent table masses and volumes, for example 0.05·60.052 g (delta 0.001) |
| `modules/elementrechner/tests/test_setup.py::Green::test_definitions` | E-factor, PMI = E + 1, RME, solvent share (places 9); atom economy 88.106/(60.052 + 46.069) (delta 10⁻⁴) |
| `modules/elementrechner/tests/test_labflow.py::CalculatorFunctions::test_si_in_si_out` | Calculator functions m_prep 6.242·10⁻³ kg, V_reag, rho_gas 1.2498 kg/m³, AE |

The expected values are hand calculations of the definitions. No published worked example is used.

## 14 Gas laws (`gas.py`)

* **Ideal gas:** pV = nRT, solved for any one unknown, in chosen units.
* **Molar volume:** Vm = RT/p. The docstring gives "IUPAC-STP: 0 °C, 100 kPa -> 22,711 L/mol".
* **Gas density:** ρ = pM/(RT), with M from the formula.
* **Dalton:** pᵢ = xᵢ·p. Mole fractions are normalised, with a note.
* **Constant:** R = N_A·k (exact, full precision; `gas.R` = `chem.R_GAS`).
* **Scope:** ideal gas only; real-gas equations are not included.
* **Refused:** T ≤ 0 K, values ≤ 0, unknown units, or not exactly one unknown.

| Test | Checks (expected, tolerance) |
|---|---|
| `modules/elementrechner/tests/test_gas.py::Gas::test_molar_volume` | 22.711 L/mol (0 °C, 100 kPa), 22.414 (0 °C, 1 atm), 24.465 (25 °C, 1 atm) (delta 0.001) |
| `modules/elementrechner/tests/test_gas.py::Gas::test_ideal_any_unknown` | V 22.414 L, p 101.325 kPa, n 1.0 mol, T 273.15 K |
| `modules/elementrechner/tests/test_gas.py::Gas::test_density_and_mass` | ρ(N2, 0 °C, 1 atm) 1.2498 g/L (delta 0.0005); 44.0095 g CO2 → 22.414 L |
| `modules/elementrechner/tests/test_gas.py::Gas::test_dalton` | p(O2) = 0.2095·101.325 kPa (delta 0.01) |

## 15 Nuclear chemistry (`nuclear.py`)

All masses are **atomic** masses (including electrons) from AME2020. Each Q value accounts for the electron masses of
its decay mode, "Krane 1988, Kap. 8–9" (`nuclear.py:3-5`).

### Q value and binding energy

**Q value** (`nuclear.py:90-123`): Q = Δm·931.49410372 MeV/u, with M = atomic mass.

| Mode | Δm |
|---|---|
| α | M(P) − M(D) − M(⁴He) |
| β⁻ and EC | M(P) − M(D) |
| β⁺ | M(P) − M(D) − 2mₑ |
| p | M(P) − M(D) − M(¹H) |
| n | M(P) − M(D) − m(n) |

* EC neglects the electron binding energy, with a note (≤ 0.1 MeV).
* SF, 2β⁻ and induced reactions use ΣM(left) − ΣM(right), with 2mₑ per positron.
* γ and ν are ignored.
* IT and SF have no Q value from `q_value`.
* NUBASE "B+" branches are treated as β⁺.

**Uncertainty:** u(Q) = √(u(M_P)² + u(M_D)²)·931.494 MeV/u (`nuclear.py:114`).
* The uncertainties of ⁴He, ¹H, the neutron and mₑ are left out.
* AME mass correlations are ignored.

**Binding energy** (`nuclear.py:237-246`):
* B = [Z·M(¹H) + N·m(n) − M(A,Z)]·931.494 MeV/u. B/A and the mass defect are also given.
* M(¹H) and m(n) are the AME2020 values from `isotopes.json`.
* No uncertainty is given.

### Decay, activity and chains

**Decay law** (`nuclear.py:250-306`):
* λ = ln 2/T½ and τ = 1/λ. N = N₀e^(−λt), A = λN.
* Specific activity a = λN_A/M.
* Bq ↔ Ci conversion with SI prefixes.
* T½ comes from NUBASE2020, with 1 a = 365.2422 d. Its uncertainty is shown as text only and is not propagated.

**Decay chain** (`chain`, `nuclear.py:309-333`):
* At each step the chain follows the mode with the largest NUBASE branching among α, β⁻, β⁺, EC, n and p.
* SF, IT and 2β⁻ are not followed.
* The chain stops at a stable nuclide or after 8 members (the page default is 4).

**Bateman solution** (`nuclear.py:336-360`):
* Nⱼ(t) = N₀·∏ᵢ<ⱼ(bᵢλᵢ)·Σᵢ≤ⱼ e^(−λᵢt)/∏ₖ≠ᵢ(λₖ − λᵢ), with branching fractions bᵢ.
* It is evaluated with 60-digit decimal arithmetic. The inputs are double-precision.
* Equal decay constants are refused. Reference: Bateman 1910.

**Equilibrium type** (`nuclear.py:363-383`):
* With r = T½(parent)/T½(daughter):
  * secular if r > 1000;
  * transient if 1 < r ≤ 1000;
  * otherwise none.
* The code note calls the limit of 1000 a textbook convention.
* Transient case: A(daughter)/A(parent) → λ_D/(λ_D − λ_P), without the branching fraction. The time of the daughter
  maximum is t_max = ln(λ_D/λ_P)/(λ_D − λ_P).

### Dating (`nuclear.py:386-469`)

All dating methods print their assumptions with the result.

**¹⁴C:**
* Conventional age t = −8033·ln F¹⁴C (Libby half-life 5568 a, Stuiver & Polach 1977).
* Shown beside it: the age with the Cambridge half-life 5730 a (Godwin 1962) and with the NUBASE half-life.
* F¹⁴C must lie in (0, 1.5].
* F¹⁴C is taken as already normalised to δ¹³C = −25 ‰. A δ¹³C input is accepted but not used.
* Ages are in years BP. No calendar calibration is done; the note says calibration needs IntCal20.

**K–Ar:**
* t = (1/λ)·ln(1 + (λ/λₑ)·⁴⁰Ar*/⁴⁰K).
* λ = 5.543·10⁻¹⁰ a⁻¹ and λₑ = 0.581·10⁻¹⁰ a⁻¹ (Steiger & Jäger 1977).

**Ar–Ar:** t = (1/λ)·ln(1 + J·R).

**U–Pb:**
* t = ln(1 + Pb*/U)/λ for ²⁰⁶Pb/²³⁸U and ²⁰⁷Pb/²³⁵U.
* λ(²³⁸U) = 1.55125·10⁻¹⁰ a⁻¹ and λ(²³⁵U) = 9.8485·10⁻¹⁰ a⁻¹ (Jaffey et al. 1971).
* The two ages count as concordant if they differ by less than 1 % (`nuclear.py:439`). No source is cited for this
  limit.

**Rb–Sr isochron:**
* Unweighted least-squares line through at least 3 points (code note: "keine York-Regression; Unsicherheit nur aus der
  Streuung").
* t = ln(1 + m)/λ, with λ(⁸⁷Rb) = 1.3972·10⁻¹¹ a⁻¹ (Villa et al. 2015).
* u(t) comes from the standard error of the slope.
* This is the only dating result with an uncertainty.

### Isotope patterns (`nuclear.py:497-554`)

* **Pattern:** exact convolution over all atoms, binned by nominal mass.
  * Abundances are NUBASE2020 isotopic abundances ("IS"), renormalised.
  * Peaks below 0.1 % of the largest are dropped, up to 40 peaks.
  * For ions, z·mₑ is subtracted.
* **Mean atomic mass of an enriched mixture:** M = Σ xᵢ·M(AME2020), for one element.

### Validation

| Test | Checks (expected, tolerance) | Reference as stated |
|---|---|---|
| `modules/elementrechner/tests/test_nuclear.py::QAndBinding::test_q_values` | U-238 α: Q 4.26986 MeV (delta 0.0005), u 2.99 keV (delta 0.05); C-14 β⁻ 156.476 keV (delta 0.01); F-18 β⁺ 633.9 keV (delta 0.2) | "AME2020: 4269,86 ± 2,99 keV" (U-238) |
| `modules/elementrechner/tests/test_nuclear.py::QAndBinding::test_classify_equations` | Q of K-40 EC 1.5044, Am-241 α 5.6378, Ca-48 2β⁻ 4.2681, n + U-235 → Ba-141 + Kr-92 + 3n 173.28, ¹⁴N(α,p)¹⁷O −1.1919 MeV (tolerance \|Q\|·2·10⁻⁴ + 10⁻⁴) | — |
| `modules/elementrechner/tests/test_nuclear.py::QAndBinding::test_binding` | Fe-56 B/A 8.7904 MeV (delta 0.0005) | — |
| `modules/elementrechner/tests/test_nuclear.py::Decay::test_specific_activity` | Ra-226: 3.658·10¹⁰ Bq/g (relative 0.002) | — |
| `modules/elementrechner/tests/test_nuclear.py::Decay::test_activity_units` | 1 mCi = 37 MBq, 1 µCi = 37 kBq | Definition |
| `modules/elementrechner/tests/test_nuclear.py::Decay::test_bateman_two_members_analytic` | Two-member chain against the closed-form solution (delta 10⁻⁶) | Analytic |
| `modules/elementrechner/tests/test_nuclear.py::Decay::test_bateman_stable_end_conserves` | Sr-90 → Y-90 → Zr-90 conserves ΣN (delta 10⁻³) up to 10¹⁰ s | Conservation |
| `modules/elementrechner/tests/test_nuclear.py::Decay::test_equilibrium_classes` | Sr-90 and Ra-226 secular; Ba-140 transient; Bi-210 none | Qualitative |
| `modules/elementrechner/tests/test_nuclear.py::Dating::test_radiocarbon` | F = 0.5: 5568.0 a and 5730.0 a (delta 0.5) | Analytic |
| `modules/elementrechner/tests/test_nuclear.py::Dating::test_k_ar_formula` | Same formula (delta 1 a) | Self-consistency |
| `modules/elementrechner/tests/test_nuclear.py::Dating::test_u_pb_round_trip` | 1.0·10⁹ a (delta 1); concordance flag | Round trip |
| `modules/elementrechner/tests/test_nuclear.py::Dating::test_rb_sr_isochron` | Synthetic 1 Ga isochron: age (places 6), intercept 0.7 (places 9) | Synthetic |
| `modules/elementrechner/tests/test_nuclear.py::Isotopes::test_cl2_br2` | Cl2 m/z 72: 63.9 % (delta 0.2), 74: 10.2 % (delta 0.1); Br2 158: 51.3 %, 162: 48.7 % (delta 0.2) | — |
| `modules/elementrechner/tests/test_nuclear.py::Isotopes::test_enriched` | ⁶Li 95 % / ⁷Li 5 %: 6.06517 u (delta 2·10⁻⁵) | — |
| `modules/elementrechner/tests/test_data.py::Nuclides::test_half_lives_and_decay` | C-14 5700 a (delta 1); H-3 12.32 a; Tc-99m 6.0066 h; n 609.8 s; K-40 β⁻ 89.28 % | NUBASE2020 |

Ar–Ar dating has no test.

## 16 Kinetics (`kinetics.py`)

**Rate constant definition:** −d[A]/dt = k·[A]ⁿ. This is stated with every result.

**Fits:**
* All fits are ordinary unweighted least squares and need at least 3 points (`kinetics.py:41-60`).
* s² = SSR/(n − 2). The standard errors of slope and intercept and their covariance are reported, together with R².
* Uncertainties are 1σ standard errors.

**Arrhenius** (`kinetics.py:63-78`):
* ln k is fitted against 1/T. Eₐ = −slope·R, and u(Eₐ) = se(slope)·R.
* A = exp(intercept), with u(A) = A·se(intercept), a linearised value; a note says the distribution of A is
  asymmetric.
* The covariance of ln A and Eₐ and the T range of the data are given.

**Eyring** (`kinetics.py:81-94`):
* ln(k/T) is fitted against 1/T. ΔH‡ = −slope·R and ΔS‡ = (intercept − ln(k_B/h))·R.
* Transmission coefficient κ = 1.
* k is in s⁻¹ for first order, or taken with a standard concentration of 1 mol/L for higher orders. No explicit c°
  correction term is applied.

**Reaction order** (`kinetics.py:118-157`):
* Orders 0, 1 and 2 are fitted as c, ln c and 1/c against t.
* The order chosen is the one with the **smallest RMS residual of c back-transformed**, not the largest R² of the
  linearised forms.
* If the runner-up's RMS is less than 1.5 times the best, a note says it fits almost as well.
* Conversion data use c = c₀(1 − X), with 0 ≤ X < 1 and c₀ required.
* Half-lives: c₀/(2k), ln 2/k and 1/(k·c₀) for orders 0, 1 and 2.

**k(T):** k = A·exp(−Eₐ/RT), or k = k_ref·exp(−Eₐ/R·(1/T − 1/T_ref)). Eₐ must be entered with a source.

**Simulation** (`kinetics.py:173-285`):
* Models: orders 0–2, A + B, consecutive A → B → C, and reversible A ⇌ B. All use analytic solutions, including
  equal rate constants.
* A fixed-step fourth-order Runge–Kutta integration (1000 steps by default) runs alongside as a check. Its maximum
  relative deviation is reported but does not gate the result.

**Datasets:** series read from a Datenaufbereitung dataset are converted to K, s and mol/L before the fit. The values
passed are rounded to 12 significant digits (`datasets.py:33`).

**Sources in code:** Arrhenius 1889, Eyring 1935, Atkins 2018, CODATA 2022.

| Test | Checks (expected, tolerance) | Reference as stated |
|---|---|---|
| `modules/elementrechner/tests/test_kinetics.py::Fits::test_arrhenius_exact` | Eₐ 75 kJ/mol and A = 2·10¹⁰ recovered (places 8); R² = 1 | "synthetische Daten mit bekannten Parametern" |
| `modules/elementrechner/tests/test_kinetics.py::Fits::test_arrhenius_noise_within_uncertainty` | 40 runs with 5 % noise: at least 34 within 2σ | Coverage check |
| `modules/elementrechner/tests/test_kinetics.py::Fits::test_eyring_consistent_with_arrhenius` | ΔH‡ ≈ Eₐ − RT̄ (delta 0.05 kJ/mol); ΔH‡ 60 kJ/mol and ΔS‡ −40 J/(mol K) recovered | Synthetic |
| `modules/elementrechner/tests/test_kinetics.py::Fits::test_order_recovered` | Orders 0, 1, 2 and k recovered (places 6) | Synthetic |
| `modules/elementrechner/tests/test_kinetics.py::Fits::test_order_from_conversion` | First order from X–t data | Synthetic |
| `modules/elementrechner/tests/test_kinetics.py::Simulation::test_models_match_rk4` | Relative deviation from RK4 < 10⁻³ (order 0), < 10⁻⁵ (others); mass balance (places 10) | Numerical cross-check |
| `modules/elementrechner/tests/test_datasets.py::DoneWhen::test_same_activation_energy_and_order` | A dataset in °C and 1/min gives the same Eₐ, A, ΔH‡, ΔS‡ and order as the same data in K and s | Unit-conversion consistency |

## 17 Rule-based naming (`naming.py`)

**Method:** substitutive nomenclature after "Favre, H. A.; Powell, W. H.: Nomenclature of Organic Chemistry. IUPAC
Recommendations and Preferred Names 2013. RSC 2014, doi:10.1039/9781849733069" (`naming.py:3-4`). The parent
structure is chosen per P-44 and numbered per P-31.1.4.

**Scope:**
* Open chains and isolated carbocycles, and benzene.
* Principal characteristic groups, in the order acid > ester (one) > amide > nitrile > aldehyde > ketone >
  alcohol/phenol > amine.
* Halogen, nitro and alkoxy as prefixes.
* Secondary and tertiary amines and N-substituted amides.
* 13 aromatic and 17 saturated heteromonocycles.
* Retained names such as acetic acid, phenol, toluene and aniline.

**Refused, "lieber kein Name als ein falscher":**
* fused, bridged and spiro rings;
* partly hydrogenated heterocycles;
* lactams, lactones, ureas, imides and anhydrides;
* several esters;
* salts, ions and isotope labels;
* elements other than C, N, O, S and halogens;
* more than 80 atoms, or chains or rings over 30 atoms.

Any internal error also leads to a refusal (`naming.py:881-882`). No E/Z or R/S descriptors are assigned, and a note
says so. The German name is converted from the English name by rules.

**Order of names in the designer:**
1. If the drawn structure matches a collection or own substance exactly (same structure including stereo), that name
   is proposed.
2. Otherwise the rule-based name, marked "nach Regeln erzeugt (IUPAC 2013)", is proposed. A match in constitution only
   gives a warning.
3. On request, PubChem is asked. Only the SMILES is sent. The name PubChem returns is computed by OpenEye Lexichem TK
   and is used only after the user accepts it.

The name always stays editable.

| Test | Checks | Reference as stated |
|---|---|---|
| `modules/elementrechner/tests/test_design.py::Naming::test_english` | 22 structures, exact names | "Sollwerte nach Favre & Powell 2014 … von Hand geprüft" |
| `modules/elementrechner/tests/test_naming_er403.py::NamingER403::test_heterocycles` | 46 structures | Same |
| `modules/elementrechner/tests/test_naming_er403.py::NamingER403::test_amines` | 16 structures | Same |
| `modules/elementrechner/tests/test_naming_er403.py::NamingER403::test_amides` | 13 structures | Same |
| `modules/elementrechner/tests/test_naming_er403.py::NamingER403::test_german`, `test_design.py::Naming::test_german` | 17 + 4 German names | Same |
| `modules/elementrechner/tests/test_naming_er403.py::NamingER403::test_refusals`, `test_design.py::Naming::test_refusals` | 17 + 3 structures refused | — |

The structure matching in the browser and the PubChem query have no automated test.

## 18 Other look-ups

* **Choice among tabulated property values** (`substances.py:585-607`):
  1. An own measured value always wins. Estimates are used only if no measured value exists.
  2. For temperature-dependent properties, values within 5 °C of the requested T come first. A vapour pressure without
     a temperature is not used.
  3. Then the sources in the order HSDB, ICSC, DOE PAC, NIOSH, OSHA.
  4. Then values that name a primary reference.

  The alternatives stay visible and selectable.
* **Ionisation energies** (`ionization.py`):
  * NIST ASD values in eV. The conversion to kJ/mol uses 96.48533212 kJ/(mol eV) ("CODATA 2022, F/1000").
  * Values that ASD marks as theoretical or semi-empirical are flagged.
  * The element card also shows the first ionisation energy from PubChem.
  * Test: `modules/elementrechner/tests/test_ionization.py::Ionization::test_values` checks H 13.598434599702 eV
    (places 9), He⁺ 54.4177655282 eV and Li 5.391714996 eV. Its header says the reference values come from the same
    NIST export.
* **Effective ionic radii** (`radii.py`):
  * 37 Shannon radii for common ions. The crystal radius is shown as ionic radius + 0.14 Å.
  * The code marks the table "aus Shannon 1976 übertragen, bitte gegen das Original prüfen".
  * `test_ionization.py::Ionization::test_radii` checks values against the same table.
* **Antoine vapour pressure** (`vapor.py`):
  * lg(p/bar) = A − B/(T + C), for 9 solvents, each with its validity range.
  * Outside the range (tolerance 0.5 K), the nearest set is used with a warning. The boiling point at a given pressure
    is found by inverting the equation.

  | Test | Checks | Reference as stated |
  |---|---|---|
  | `modules/elementrechner/tests/test_vapor.py::Antoine::test_water` | p(water, 25 °C) 3.1699 kPa (delta 0.01); 19.946 kPa (delta 0.05); Tb 373.12 K (delta 0.2) | "IAPWS-95/Wagner–Pruss, CRC" |
  | `modules/elementrechner/tests/test_vapor.py::Antoine::test_ethanol` | 7.87 kPa (delta 0.05); Tb 351.44 K (delta 0.3) | "CRC Handbook" |
* **Freezing-point depression and boiling-point elevation:** ΔT = i·K·b, for 8 solvents. A note appears above
  b = 0.1 mol/kg. The test `test_vapor.py::Antoine::test_colligative` checks the arithmetic only.
* **Own data tables** (`tables.py`): CSV or JSON with a required source per table or per row. Rows without a source
  are rejected, and own values take precedence. Tests: `modules/elementrechner/tests/test_tables.py::Tables::*`.

## 19 Measurement uncertainty (`uncert.py`)

Every measured or entered input on the page can carry an uncertainty (the small ± button next to the field; no entry
means exact). One method applies to the whole page: GUM linear (JCGM 100), Monte Carlo (JCGM 101, fixed seed),
Gaussian propagation or worst case, all from `labcalc.uncertainty`. Results show "value ± U" with the budget, notes and
a method comparison in folds; the report gets `\labval{unc-<name>-pm}`, `-u`, `-U`, budget tables and a methods
sentence, and the specs are kept in `source.request`.

* **Molar mass.** Each element is one input A_r. Interval atomic weights count as rectangular distributions over the
  interval, with the midpoint as value (Possolo et al. 2018, Pure Appl. Chem. 90, 395–424); single values with a
  stated U are treated as ±U rectangles as well (a module assumption, not checked against the original). Elements are
  independent; an element occurring n times enters as n·A_r. Isotopes use the AME2020 uncertainty. The midpoints can
  differ slightly from the abridged values used elsewhere; the result says so.
* **Solution from a solid.** c = m·P·k·M_basis/(M_form·V) (or the mass, w/v, w/w and mol/kg forms) with the weighed
  mass m (field "weighed g"; empty = computed mass), purity P, final volume V, density for w/w and mol/kg, and the
  atomic weights.
* **From stock.** c₂ = c_stock·V₁/V₂ in the stock's basis, with the stock content, its density (w/w), the measured
  volume V₁ (field "measured"; empty = computed) and V₂. Targets in w/w or mol/kg get no uncertainty (noted).
* **Dilution series.** c_i = c₀·Π_{j≤i} t_j/f_j; every transfer t_j shares the pipette entry and every flask f_j the
  flask entry, each step an independent draw. Steps are correlated through c₀ and the earlier transfers; the
  correlation matrix r_ik = Σ_q c_i,q c_k,q u_q² / (u_i u_k) is shown and reported.
* **Gas law.** The computed unknown of pV = nRT gets u from the other three inputs (R exact).
* **Yield.** Equation: Y = 100·n_product/(ν_product·ξ) with ξ = min over the reactants of n/ν (the minimum is
  evaluated per trial in Monte Carlo); masses convert with the uncertain molar masses. Reaction set-up: Y from the
  reference amount and the observed product mass.
* **pH.** pH from the proton balance (same equations as `acidbase.py`, solved by bisection, vectorised) as a function
  of the concentrations and pKa values; u(pH) is a propagated uncertainty, labelled as such. Activities and the
  temperature count as exact.
* **Shared values.** The value catalogue and the project index carry `u` (standard uncertainty) and the method; molar
  masses always carry the atomic-weight u.

| Test | Checks | Reference as stated |
|---|---|---|
| `test_uncert.py::QuamA1::test_quam_a1` | c(Cd) 1002.7 mg/L, u ≈ 0.83 (QUAM rounds to 0.9, accepted within 0.1), U(k = 2) within 0.2 of 1.8 | EURACHEM/CITAC QUAM (2012) Example A1 (inputs not checked against the original) |
| `test_uncert.py::MolarMass::test_h2o_by_hand` | M(H₂O) and u against a hand calculation from the CIAAW intervals | Possolo et al. 2018 |
| `test_uncert.py::Series::test_correlation_by_hand` | relative u per step and the correlation matrix against the closed form | hand calculation |
| `test_uncert.py::GasYieldPH::*` | gas-law u by hand, yields, pH model equal to `acidbase.ph`, u(pH) near the weak-acid approximation | hand calculation |

## Running the tests

From `modules/elementrechner`, with `sdk/python` on `PYTHONPATH`:

```
python -m unittest discover -s tests
```

From `sdk/python`:

```
python -m unittest discover -s tests
```

`test_golden.py` compares a full report bundle (Zn + CuSO₄, pH, titration, NaCl) with a stored copy of the module's
own earlier output. It detects changes; it is not a check against an outside reference.

## Known limitations

**Estimated, not tabulated:**
* Benson and Joback values, the bond-enthalpy ΔrH, and log P, log S and TPSA are estimates. They are labelled as such
  and rank below every table.
* Joback values carry no accuracy statement in the code.
* Benson covers C/H/O molecules only.

**Data typed in from reference knowledge:** the code marks these as still to be checked against the printed source:
* the indicator table;
* Antoine and Kf/Kb constants;
* Shannon radii;
* mean bond enthalpies.

**Doubtful values:**
* The crystal radius is computed as ionic radius + 0.14 Å for anions as well. Shannon's convention for anions differs.
* The S–S bond enthalpy (226 kJ/mol) should be checked.

**Uncertainty:**
* Propagated only for:
  * molar mass (from the abridged atomic-weight ±);
  * ΔrH° and ΔrS° (incomplete when NBS data are involved);
  * nuclear Q values (parent and daughter mass only);
  * fit parameters in kinetics and the Rb–Sr isochron.
* There is no uncertainty for ΔrG°, K, pH, speciation, E°, preparation results or other dating methods.
* Uncertainties stored with SRD 46 values are not used.

**Temperature:**
* pKa values and stability constants are used at their measured temperature; only pKw follows T in the pH
  calculation.
* pKb, the OH⁻ activity in the Nernst equation, and speciation use a fixed pKw: 13.995, or 14.0 in speciation.
* The thermochemistry page silently resets a temperature outside 1–6000 K to 298.15 K (`analysis.py:71-72`).
* The Cp(T) model ignores phase transitions.

**Ideal behaviour:**
* Ideal solutions unless an activity model is switched on. Activity models are not refused above their range, only
  flagged.
* Ideal gases only.
* Equilibrium composition, flame temperature and saturation index assume ideal behaviour. The flame temperature
  excludes dissociation.

**Speciation:** mononuclear complexes only, no precipitation, no conversion between ionic strengths, and only the
ligand side reaction in conditional constants.

**Formula parser:** a decimal index greater than 1 followed by another element is read as a hydrate dot. For example,
`Cu1.8S` is read as Cu·8S. Write non-stoichiometric formulas with brackets, or check the parsed formula that is
displayed.

**Elements without a standard atomic weight:** these use an integer mass number with u = 0. For Z ≥ 93, the
"longest-lived isotope" was chosen when the file was built, and half-lives estimated from systematics counted in that
choice.

**Nuclear:**
* Isomers such as Tc-99m cannot be addressed by the decay, activity and chain functions. The "m" is dropped, and the
  ground state is used.
* Chains follow α, β⁻, β⁺, EC, n and p only, so a dominant SF or IT branch is skipped.
* The transient-equilibrium activity ratio ignores the branching fraction.
* δ¹³C normalisation is not done.
* There is no radiocarbon calibration and no dose or radiation-protection calculation.
* The isotope pattern uses NUBASE abundances, while the element card uses CIAAW abundances.

**Naming:** fused, bridged and spiro systems and several other classes are refused rather than named. No
stereodescriptors are assigned.

**Not in the public repository:** the IUPAC pKa dataset (CC BY-NC 4.0). Without it, fewer organic pKa values are
available.

**Refused rather than guessed:**
* unbalanceable or ambiguous equations (the independent solutions are shown);
* % (w/w) or molality without a sourced density;
* unreachable buffer pH;
* Benson, Joback or naming outside their scope;
* T outside 0–100 °C for pKw and activity coefficients, or outside 50–6000 K for Cp(T);
* Faraday efficiency above 100 %;
* fewer than 3 points in a fit.

## References as recorded in the code

These are the reference records in `sdk/python/labcalc/sources.py` and `modules/elementrechner/elementrechner/refs.py`
used by the methods above. They are reproduced field by field. German edition labels ("Auflage") are given as "ed.".

* **ame2020:** Wang, Meng; Huang, W. J.; Kondev, F. G.; Audi, G.; Naimi, S. The AME 2020 atomic mass evaluation (II).
  Tables, graphs and references. Chinese Physics C 45(3) (2021) 030003. doi:10.1088/1674-1137/abddaf
* **arrhenius1889:** Arrhenius, S. Über die Reaktionsgeschwindigkeit bei der Inversion von Rohrzucker durch Säuren.
  Zeitschrift für Physikalische Chemie 4 (1889) 226-248. doi:10.1515/zpch-1889-0416
* **atct2004:** Ruscic, Branko; Pinzon, Reinhardt E.; Morton, Melita L.; von Laszevski, Gregor; Bittner, Sandra J.;
  Nijsure, Sandeep G.; Amin, Kaizar A.; Minkoff, Michael; Wagner, Albert F. Introduction to Active Thermochemical
  Tables: Several "Key" Enthalpies of Formation Revisited. The Journal of Physical Chemistry A 108(45) (2004)
  9979-9997. doi:10.1021/jp047912y
* **atkins:** Atkins, P.; de Paula, J.; Keeler, J. Atkins' Physical Chemistry. Oxford University Press, 2018, 11th ed.
* **baes1976:** Baes, C. F.; Mesmer, R. E. The Hydrolysis of Cations. Wiley, 1976.
* **bandura2006:** Bandura, Andrei V.; Lvov, Serguei N. The Ionization Constant of Water over Wide Ranges of
  Temperature and Density. Journal of Physical and Chemical Reference Data 35(1) (2006) 15-30. doi:10.1063/1.1928231
* **bard:** Bard, A. J.; Faulkner, L. R. Electrochemical Methods: Fundamentals and Applications. Wiley, 2001, 2nd ed.
* **bateman1910:** Bateman, H. The solution of a system of differential equations occurring in the theory of
  radioactive transformations. Proceedings of the Cambridge Philosophical Society 15 (1910) 423-427.
* **benson1969:** Benson, Sidney W.; Cruickshank, F. R.; Golden, D. M.; Haugen, Gilbert R.; O'Neal, H. E.; Rodgers,
  A. S.; Shaw, Robert; Walsh, R. Additivity rules for the estimation of thermochemical properties. Chemical Reviews
  69(3) (1969) 279-324. doi:10.1021/cr60259a002 (method only; no values taken from it)
* **burcat2005:** Burcat, Alexander; Ruscic, Branko. Third Millennium Ideal Gas and Condensed Phase Thermochemical
  Database for Combustion with Updates from Active Thermochemical Tables. Argonne National Laboratory, 2005, report
  ANL-05/20, TAE 960. doi:10.2172/925269
* **burcat2018:** Goos, Elke; Burcat, Alexander; Ruscic, Branko. Extended Third Millennium Ideal Gas and Condensed
  Phase Thermochemical Database for Combustion with Updates from Active Thermochemical Tables. Technion / DLR, 2018.
  https://burcat.technion.ac.il/ (accessed 2026-11-17)
* **chase1998:** Chase, Malcolm W., Jr. NIST-JANAF Thermochemical Tables, Fourth Edition. Journal of Physical and
  Chemical Reference Data, Monograph 9, 1998. doi:10.18434/T42S31 (used as comparison values in tests)
* **ciaaw2021:** Prohaska, Thomas; Irrgeher, Johanna; … Meija, Juris. Standard atomic weights of the elements 2021
  (IUPAC Technical Report). Pure and Applied Chemistry 94(5) (2022) 573-600. doi:10.1515/pac-2019-0603
* **ciaaw2024:** CIAAW. Standard Atomic Weights 2024. IUPAC Commission on Isotopic Abundances and Atomic Weights,
  www.ciaaw.org, 2024. https://www.ciaaw.org/atomic-weights.htm (accessed 2026-11-17)
* **ciaaw_iso2024:** CIAAW. Isotopic Compositions of the Elements 2024. www.ciaaw.org, 2024.
  https://www.ciaaw.org/isotopic-abundances.htm (accessed 2026-11-17)
* **codata2022:** Mohr, P. J.; Newell, D. B.; Taylor, B. N.; Tiesinga, E. CODATA recommended values of the fundamental
  physical constants: 2022. Reviews of Modern Physics 97 (2025) 025002. doi:10.1103/RevModPhys.97.025002
* **constable2002:** Constable, David J. C.; Curzons, Alan D.; Cunningham, Virginia L. Metrics to 'green' chemistry --
  which are the best? Green Chemistry 4(6) (2002) 521-527. doi:10.1039/b206169b
* **cox1989:** Cox, J. D.; Wagman, D. D.; Medvedev, V. A. CODATA Key Values for Thermodynamics. Hemisphere Publishing
  Corp., 1989.
* **davies1962:** Davies, C. W. Ion Association. Butterworths, 1962.
* **domalski1993:** Domalski, Eugene S.; Hearing, Elizabeth D. Estimation of the Thermodynamic Properties of
  C-H-N-O-S-Halogen Compounds at 298.15 K. Journal of Physical and Chemical Reference Data 22(4) (1993) 805-1159.
  doi:10.1063/1.555927
* **ertl2000:** Ertl, Peter; Rohde, Bernhard; Selzer, Paul. Fast calculation of molecular polar surface area as a sum
  of fragment-based contributions and its application to the prediction of drug transport properties. Journal of
  Medicinal Chemistry 43(20) (2000) 3714-3717. doi:10.1021/jm000942e
* **eyring1935:** Eyring, H. The Activated Complex in Chemical Reactions. The Journal of Chemical Physics 3 (1935)
  107-115. doi:10.1063/1.1749604
* **favre2014:** Favre, Henri A.; Powell, Warren H. Nomenclature of Organic Chemistry: IUPAC Recommendations and
  Preferred Names 2013. Royal Society of Chemistry, 2014. doi:10.1039/9781849733069
* **godwin1962:** Godwin, H. Half-life of radiocarbon. Nature 195 (1962) 984. doi:10.1038/195984a0
* **good1966:** Good, Norman E.; Winget, G. Douglas; Winter, Wilhelmina; Connolly, Thomas N.; Izawa, Seikichi; Singh,
  Raizada M. M. Hydrogen Ion Buffers for Biological Research. Biochemistry 5(2) (1966) 467-477.
  doi:10.1021/bi00866a011
* **harris:** Harris, D. C. Quantitative Chemical Analysis. W. H. Freeman, 2016, 9th ed.
* **iupac_pka:** Zheng, Jonathan W.; Lafontant-Joseph, Olivier. IUPAC Digitized pKa Dataset
  (IUPAC/Dissociation-Constants v2.4). Zenodo, 2026. doi:10.5281/zenodo.7236452. Licence CC BY-NC 4.0. "Reproduced by
  permission of International Union of Pure and Applied Chemistry"
* **jaffey1971:** Jaffey, A. H.; Flynn, K. F.; Glendenin, L. E.; Bentley, W. C.; Essling, A. M. Precision measurement
  of half-lives and specific activities of 235U and 238U. Physical Review C 4(5) (1971) 1889-1906.
  doi:10.1103/PhysRevC.4.1889
* **jimenez2011:** Jimenez-Gonzalez, Concepción; Ponder, Celia S.; Broxterman, Quirinus B.; Manley, Julie B. Using
  the Right Green Yardstick: Why Process Mass Intensity Is Used in the Pharmaceutical Industry To Drive More
  Sustainable Processes. Organic Process Research & Development 15(4) (2011) 912-917. doi:10.1021/op200097d
* **joback1987:** Joback, K. G.; Reid, R. C. Estimation of pure-component properties from group-contributions.
  Chemical Engineering Communications 57(1-6) (1987) 233-243. doi:10.1080/00986448708960487
* **joback_wiki:** Wikipedia contributors. Joback method. Wikipedia, The Free Encyclopedia, 2026.
  https://en.wikipedia.org/wiki/Joback_method (accessed 2026-11-17), CC BY-SA 4.0
* **karen2016:** Karen, Pavel; McArdle, Patrick; Takats, Josef. Comprehensive definition of oxidation state (IUPAC
  Recommendations 2016). Pure and Applied Chemistry 88(8) (2016) 831-839. doi:10.1515/pac-2015-1204
* **kell1975:** Kell, George S. Density, Thermal Expansivity, and Compressibility of Liquid Water from 0° to 150 °C:
  Correlations and Tables for Atmospheric Pressure and Saturation Reviewed and Expressed on 1968 Temperature Scale.
  Journal of Chemical and Engineering Data 20(1) (1975) 97-105. doi:10.1021/je60064a005
* **kielland1937:** Kielland, J. Individual Activity Coefficients of Ions in Aqueous Solutions. Journal of the
  American Chemical Society 59 (1937) 1675-1678. doi:10.1021/ja01288a032
* **krane:** Krane, K. S. Introductory Nuclear Physics. Wiley, 1988.
* **malmberg1956:** Malmberg, C. G.; Maryott, A. A. Dielectric Constant of Water from 0 to 100 C. Journal of Research
  of the National Bureau of Standards 56 (1956) 1-8. doi:10.6028/jres.056.001
* **mcbride2002:** McBride, Bonnie J.; Zehe, Michael J.; Gordon, Sanford. NASA Glenn Coefficients for Calculating
  Thermodynamic Properties of Individual Species. NASA Glenn Research Center, NASA/TP-2002-211556, 2002.
* **nistasd:** Kramida, A.; Ralchenko, Yu.; Reader, J.; NIST ASD Team. NIST Atomic Spectra Database, Ionization
  Energies. National Institute of Standards and Technology, 2024. doi:10.18434/T4W30F (accessed 2026-11-17)
* **nistwebbook:** Linstrom, P. J.; Mallard, W. G. (eds.). NIST Chemistry WebBook, NIST Standard Reference Database
  Number 69. National Institute of Standards and Technology, 2025. doi:10.18434/T4D303 (accessed 2026-11-17)
* **nubase2020:** Kondev, F. G.; Wang, M.; Huang, W. J.; Naimi, S.; Audi, G. The NUBASE2020 evaluation of nuclear
  physics properties. Chinese Physics C 45(3) (2021) 030001. doi:10.1088/1674-1137/abddae
* **pubchem2025:** Kim, Sunghwan; … Bolton, Evan E. PubChem 2025 update. Nucleic Acids Research 53(D1) (2025)
  D1516-D1525. doi:10.1093/nar/gkae1059
* **pubchem_pt:** Kim, Sunghwan; Gindulyte, Asta; Zhang, Jian; Thiessen, Paul A.; Bolton, Evan E. PubChem Periodic
  Table and Element pages: improving access to information on chemical elements from authoritative sources. Chemistry
  Teacher International 3(1) (2021) 57-65. doi:10.1515/cti-2020-0006
* **reed2020:** Reed, Laura. Digitized NBS Tables of Chemical Thermodynamic Properties. National Institute of
  Standards and Technology, 2020. doi:10.18434/M32124
* **sander2015:** Sander, Thomas; Freyss, Joel; von Korff, Modest; Rufener, Christian. DataWarrior: An Open-Source
  Program For Chemistry Aware Data Visualization And Analysis. Journal of Chemical Information and Modeling 55(2)
  (2015) 460-473. doi:10.1021/ci500588j
* **shannon1976:** Shannon, R. D. Revised effective ionic radii and systematic studies of interatomic distances in
  halides and chalcogenides. Acta Crystallographica Section A 32(5) (1976) 751-767. doi:10.1107/S0567739476001551
* **sheldon2007:** Sheldon, Roger A. The E Factor: fifteen years on. Green Chemistry 9(12) (2007) 1273-1283.
  doi:10.1039/b713736m
* **srd46:** Burgess, Donald R. NIST SRD 46. Critically Selected Stability Constants of Metal Complexes, Version 8.0.
  National Institute of Standards and Technology, 2004. doi:10.18434/M32154
* **steiger1977:** Steiger, R. H.; Jaeger, E. Subcommission on geochronology: convention on the use of decay
  constants in geo- and cosmochronology. Earth and Planetary Science Letters 36(3) (1977) 359-362.
  doi:10.1016/0012-821X(77)90060-7
* **stuiver1977:** Stuiver, M.; Polach, H. A. Discussion: Reporting of 14C data. Radiocarbon 19(3) (1977) 355-363.
  doi:10.1017/S0033822200003672
* **trost1991:** Trost, Barry M. The atom economy – a search for synthetic efficiency. Science 254(5037) (1991)
  1471-1477. doi:10.1126/science.1962206
* **turns2012:** Turns, S. R. An Introduction to Combustion: Concepts and Applications. McGraw-Hill, 2012, 3rd ed.
* **villa2015:** Villa, I. M.; De Bievre, P.; Holden, N. E.; Renne, P. R. IUPAC-IUGS recommendation on the half life of
  87Rb. Geochimica et Cosmochimica Acta 164 (2015) 382-385. doi:10.1016/j.gca.2015.05.025
* **wagman1982:** Wagman, D. D.; Evans, W. H.; Parker, V. B.; Schumm, R. H.; Halow, I.; Bailey, S. M.; Churney, K. L.;
  Nuttall, R. L. The NBS tables of chemical thermodynamic properties. Selected values for inorganic and C1 and C2
  organic substances in SI units. Journal of Physical and Chemical Reference Data 11, Suppl. 2 (1982). Erratum:
  J. Phys. Chem. Ref. Data 18 (1989) 1807, doi:10.1063/1.555845
* **wikidata:** Vrandečić, Denny; Krötzsch, Markus. Wikidata: a free collaborative knowledgebase. Communications of
  the ACM 57(10) (2014) 78-85. doi:10.1145/2629489

The extended Debye–Hückel equation is attributed to "Debye–Hückel 1923" in the `activity.py` docstring, but there is
no reference record for it.
