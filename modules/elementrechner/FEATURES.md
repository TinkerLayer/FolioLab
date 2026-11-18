# Elementrechner – feature overview

This page is the short version: what the tool can do today and what is still open, in the order it was built
(phases 1–7, lab workflows, speciation, smaller items, sharing, board UI, datasets). The user guide is `README.md`;
methods, data sources and validation are in `docs/methods/elementrechner.md`. Codes in brackets (ER-…) are internal
work-item numbers.

Legend: **done** = built and tested · **partial** = usable, something named is missing · **planned** = not started.

Principle: every number has a source. Tabulated values, values calculated from them, and estimates are never mixed;
estimates and calculated values are always labelled.

## At a glance

| Area | Status | Phase |
|---|---|---|
| Input: equations, formulas, names, periodic table, molecule window | done | 1–2 |
| Balancing (elements, charge, nuclear) | done | 1 |
| Molar mass, composition, stoichiometry, yield | done | 1 |
| Isotopes and element cards | done | 1 |
| Molecule collection with structures | done | 2 |
| Look-up values (pKa, pKb, Ksp, log K, physical properties) | done | 2 |
| Own substances with sourced values | done | 2–3 |
| Thermochemistry at 298 K (ΔH, ΔS, ΔG, K, T*, heat) | done | 3 |
| Molecule designer (draw, recognise, name, estimate incl. Benson, save, report card, grid and bond tool) | done | 4, UI |
| Redox, electrochemistry, ionic equations, pH, titration, buffers, indicators | done | 5 |
| Lab workflows: solution preparation, dilution and mixing, reaction setup and scaling, green metrics, gas helpers | done | L |
| Nuclear chemistry (Q-value, decay, chains, dating, isotope patterns) | done | 6 |
| Temperature dependence with Cp(T), equilibrium composition, kinetics, flame temperature | done | 7 |
| Speciation, activity models, saturation index | done | S |
| Bond enthalpies, ionisation energies, ionic radii, Antoine, own data tables | done | smaller items |
| Using FTIR/TGA results, values to the Rechner, project index, provenance | done | X / suite A3–A8 |
| Board: environments, tools per environment, reaction chains, research window, values between environments | done | UI |
| Report to Folio | done for every section | – |

## Done

### Input
- **Equation line** written as on paper: `->`, `=`, `<=>`; charges `SO4^2-`, `Fe^3+`; phases `(s) (l) (g) (aq)`;
  hydrates `CuSO4·5H2O`; isotopes `^14C`, `D`, `T`; particles `n`, `alpha`, `beta-`, `gamma`; unknown particle `?`.
  Leave coefficients empty and they are determined.
- **Substance names** (German and English) instead of formulas: `Essigsäure + NaOH -> …`. The formula is always shown.
- **Periodic table** as a floating window at the top right (F2). Click inserts the symbol; the equation stays editable.
  Shift+click opens the element card. Colour by block or atomic mass.
- **Molecule window** (F3): search the collection by name, formula, CAS or class, with structure images. Click inserts
  the formula. Species of the current equation are shown as chips; unknown ones are flagged and can be created as own
  substances or drawn in the designer.
- **Amounts table** under the equation: mass, amount, gas volume at T/p, concentration × volume.
- **Detail switch**: full worked solutions or results only.

### Balancing
- Integer null space of the composition matrix (elements plus charge), exact fractions.
- Says when an equation is impossible (and which element does not balance) or not unique (shows the independent
  solutions instead of guessing). Checks given coefficients.
- Nuclear equations: conservation of A and Z, the missing particle is identified.

### Formulas and stoichiometry
- Molar mass with uncertainty from the CIAAW 2024 standard atomic weights; mass fractions; empirical and molecular
  formula from elemental analysis.
- Limiting reagent, extent of reaction, theoretical amounts and masses, yield, excess, atom economy (Trost).

### Elements and isotopes
- Element card: Z, atomic weight (interval and abridged value), isotopes with mass (AME2020), abundance (CIAAW) and
  half-life and decay mode (NUBASE2020).
- Since phase 5 the card also has real data for electron configuration, Pauling electronegativity, common oxidation
  states, first ionisation energy, electron affinity, van der Waals radius, melting/boiling point, density and
  standard state, from the PubChem periodic table (Kim et al. 2021). Earlier versions of this page listed some of
  these before the data existed. Atomic weights still come from CIAAW only.

### Molecule collection
- 1822 substances (inorganics, acids/bases/salts, gases, solvents, reagents, organics of all classes, monomers,
  amino acids, sugars, fatty acids, minerals, fillers, polymers by repeat unit). German name for 1664 of them.
- Structure, names, CAS from PubChem; German names from Wikidata; key = InChIKey. Formulas for equations are built
  from the structure (salts, hydrates) and checked against PubChem.

### Look-up values
- pKa of every step (NIST SRD 46, IUPAC digitized pKa dataset, PubChem/HSDB), pKb via pKw, solubility products,
  stability constants log K / log β (NIST SRD 46), physical properties (melting/boiling/flash point, density,
  vapour pressure, solubility, log Kow, refractive index, viscosity, surface tension, Henry constant, enthalpies of
  vaporisation and combustion) from open sources only, each with its primary source.
- All values shown with source, temperature, ionic strength, medium and rating; a fixed rule proposes one, the
  choice can be changed.
- Ksp missing from SRD 46 is calculated from ΔfG° and labelled "berechnet" (BaSO₄ −10.06, calcite −8.42).

### Own substances
- With or without structure (mixtures, products, polymers); own values each with a source (shared source form);
  formation data ΔfH°, ΔfG°, S°, Cp° per phase. Own values take precedence over tables.
- Stored in `eigene_stoffe.json`; export/import as JSON and SDF.

### Thermochemistry (298.15 K, 1 bar)
- Formation data: CODATA Key Values, NBS tables (NIST digital edition), Burcat/ATcT — 12 263 entries.
  Missing ΔfG° is calculated from ΔfH° and S° and marked. Digitisation errors in the NBS file are detected and
  corrected with a note.
- Stable phase chosen automatically when none is given; ions in solution; isomers separated by name or notation;
  every data set can be switched per species.
- ΔrH° (with uncertainty), ΔrS°, ΔrG° by both routes with their difference, K and lg K, Kc via Δn(gas), the four
  (ΔH, ΔS) cases in words, T* = ΔH/ΔS, heat for the entered amount, heating value per kg and per mol.
- Other temperatures as a labelled approximation (ΔH, ΔS constant); ΔG(T) chart with T*.
- Activation energy: stated explicitly that it does not follow from the equation; no estimate.

### Molecule designer (phase 4)
- Floating designer window (F4) with the OpenChemLib structure editor: atoms, bonds, charges, stereo, ring templates;
  paste SMILES or a molfile, or start from a collection substance. Also opens from an unknown species in the equation
  ("zeichnen", warns if the drawn formula does not match), from the own-substance form ("Zeichnen …", fills the form)
  and from every substance card.
- Name after drawing: (1) recognised in the collection or own substances (same structure; same constitution with
  different stereo is reported as such); (2) rule-based IUPAC 2013 name, marked "nach Regeln erzeugt", German and
  English; (3) PubChem on request, sending only the structure, with a notice each time. The name always stays editable.
- Scope of the rule-based names: open chains and carbocycles, benzene derivatives, esters, and the common groups
  (acid, nitrile, aldehyde, ketone, alcohol/phenol, primary amine, halogen, nitro, ether, acyl, multiple bonds),
  substituted substituents, retained names (acetic acid, phenol, toluene …); since ER-403 also common heterocycles,
  secondary/tertiary amines and N-substituted amides. Refused instead of guessed: fused/bridged/spiro rings, lactams,
  partly hydrogenated rings, salts and ions, several equal rings. Checked on more than 140 structures.
- Exact from the structure: formula, molar mass, monoisotopic mass, DBE, functional groups, H-bond donors and
  acceptors, rotatable bonds, stereo centres.
- Estimated, each labelled with method and source: log P and log S (Sander 2015, via OpenChemLib), TPSA (Ertl 2000);
  boiling and melting point, critical data, ΔfH°(g), ΔfG°(g), Cp(T), enthalpies of vaporisation and fusion, liquid
  viscosity (Joback & Reid 1987); S°(g) derived from the Joback values and CODATA element entropies.
- Acid–base hint from the acidic/basic groups, pointing to a related collection compound and its measured pKa — no
  predicted pKa. Reaction hints from the functional groups.
- Save the drawn molecule as an own substance in one click (structure, name, estimated values flagged as
  estimates); estimates have the lowest priority everywhere: formation data only when no own or tabulated data exist,
  properties only when no measured value exists. A reaction result that rests on estimates carries a warning. In the
  own-substance form, estimates are listed separately, read-only and removable.

### Reaction type and ionic equation (phase 5)
- Reaction type chips under the equation, each with its reason: redox, combustion, disproportionation,
  comproportionation, single and double displacement, acid–base/neutralisation, precipitation, complex formation,
  synthesis, decomposition, nuclear, half-reaction.
- Net ionic equation for reactions in solution. Dissolved salts and strong acids are split into ions; spectator ions
  cancel. Kept together: sparingly soluble salts (molar solubility below 0.01 mol/L, calculated from Ksp, Harris
  2016), species marked (s), (l) or (g), water, weak acids, metals. Examples: Zn + CuSO₄ gives Zn + Cu²⁺ → Zn²⁺ + Cu;
  AgNO₃ + NaCl gives Ag⁺ + Cl⁻ → AgCl; CH₃COOH + NaOH gives CH₃COOH + OH⁻ → CH₃COO⁻ + H₂O.

### Redox and electrochemistry (phase 5)
- Oxidation numbers per atom from the structure, or the mean value from the formula; which element is oxidised and
  which reduced.
- Half-reactions, built from the ionic equation when the salt form does not split cleanly (e.g. KMnO₄ + HCl,
  dichromate + Fe²⁺). Balancing in acidic or basic solution (H⁺/H₂O or OH⁻/H₂O added) with one click; electrons
  transferred.
- E° of each half-reaction computed from ΔfG° (decision: no separate E° table); E°cell = E°(cathode) − E°(anode);
  ΔG° = −nFE°; spontaneity. E° from ΔrG° of the equation as written is shown for comparison.
- Nernst at entered concentrations or pressures; Faraday (charge, current × time, deposited mass).
- Faraday with current efficiency η (default 100 %) and electrolysis yield from a measured mass per product; warnings
  when more than one element is oxidised or reduced, or for dis-/comproportionation (0.6.0).

### pH, titration and buffers (phase 5, pH tab)
- pH of any mixture (`0,1 M CH3COOH; 0,05 M CH3COONa`) from the full proton balance: strong and weak acids and bases,
  polyprotic acids, salts. Shows species fractions and the pKa values used, with source.
- Temperature 0–100 °C (0.6.0): pKw(T) after Bandura & Lvov 2006 with the water density of Kell 1975 (13.995 at
  25 °C, 13.264 at 50 °C); pKw and neutral pH are shown. pKa values stay at their measured temperature, with a note,
  not extrapolated.
- Titration curve with equivalence points (chart), and for each equivalence point suitable indicators with their
  colour change and titration error (0.6.0). Example: acetic acid with NaOH gives phenolphthalein, not methyl orange.
- Indicator look-up: 22 common acid–base indicators with transition range and colours (Harris 2016), plus the colour
  each shows at the pH of the current solution.
- Buffer finder: acid–base pairs with pKa within pH ± 1, common lab buffers first (phosphate, Tris, HEPES, MES, MOPS,
  PIPES, acetate, citrate, borate …; Harris 2016, Good et al. 1966), then by distance. Click gives the composition by
  Henderson–Hasselbalch and the exact proton balance, plus buffer capacity β.
- Ideal-dilute model by default; activity coefficients switchable since ER-S01.

### Calculator (Rechner) link
- Functions in both tools: `M()`, `Ar()`, `n()`, `pKa()`, `pKb()`, `Ksp()`, `pKsp()`, `lgK()`, `Tm()`, `Tb()`,
  `rho()`, `dfH()`, `dfG()`, `Sm0()`, `Cpm0()`, `dHr()`, `dSr()`, `dGr()`, `lgKr()`, and since phase 5 `E0r()`,
  `ne()`, `oxn()`, `pH()`. `pH("…", T)` takes an optional temperature (0–100 = °C, 273.15–373.15 = K).
- One click sends results (molar masses, amounts, ΔrH°, ΔrS°, ΔrG°, K, T*, E°, n, E) to the Rechner as named
  quantities.

### Report (Folio)
- Balanced equation with worked matrix solution, element balance, stoichiometry table, molar masses and composition,
  elemental analysis, thermochemistry with Hess sums and data table (estimated values marked), ΔG(T) figure.
- Phase 5: oxidation-number table, net ionic equation, half-reactions, E°cell, ΔG° = −nFE°, Nernst and Faraday; pH
  with species table, temperature, pKw and neutral pH; titration curve with equivalence points and the suggested
  indicator; current efficiency and electrolysis yield.
- `\labval` values (e.g. `dH-r`, `dG-r`, `K-298`, `T-star`, `Q-r`, `hv`, `E0-r`, `n-e`, `E-r`, `ph`, `V-eq1`), every
  data source cited; Refresh rebuilds the section from the saved state, in German or English.
- Since 0.8.0 also: molecule card, nuclear chemistry, Cp(T) and equilibrium, kinetics and flame temperature,
  speciation and saturation index, reaction chains (`reaktionskette`, `kette-*`), copied values with "eingesetzt in"
  (`uebernommene-werte`), TGA comparison (`tga-vergleich`) and FTIR comparison (`ftir-vergleich`) naming the share ID
  and version.

### Measurement series from datasets (0.9.0)
- "Aus Datensatz …" next to the Arrhenius/Eyring (T, k), reaction-order (t, c or X) and Rb–Sr isochron inputs, shown
  when a dataset is addressed to the Elementrechner. Units are converted to what the fit expects (°C → K, min → s,
  k's time part → s, c or X by unit); excluded and incomplete rows are left out for all chosen columns together.
- Pinned (the version at import) or live (newest version on opening); the origin line and the report sentence name
  the dataset ID and version; editing the inputs by hand clears the origin. A dataset in °C and min gives the same
  Eₐ and order as the same data in K and s (test).

### More look-ups (smaller items, 0.8.0)
- Mean bond enthalpies and lengths (34 bonds, Atkins) with a labelled bond-enthalpy estimate of ΔrH next to the
  tabulated value.
- Successive ionisation energies from NIST ASD (110 elements, licence and DOI in the data file; Rechner `IE("Na", 1)`)
  and 37 Shannon ionic radii (marked "please check").
- Antoine coefficients for 9 solvents with validity range (warning outside it), K_f/K_b for 8 solvents; Rechner
  `pvap`, `Kf`, `Kb`.
- Own data tables (CSV or JSON) with a required source per table or row; rows without source are rejected; own values
  take precedence and export in the import format.

### Overview, environments and sharing (0.8.0)
- **Board** as the start view: the project index and shares sent to the Elementrechner (left, read-only), the
  environments (middle, with "+ Umgebung"), the module's own shares (right). Wires: share → environment is a binding
  (pinned, live or copy), environment → environment carries values.
- **Environment detail:** the input plus only the tools imported into it ("+ Werkzeug"); nothing on by default.
  Task list "Was möchten Sie tun?" opens the right tool. Species cards under the equation; unknown species can be
  drawn and inserted. "Werte …" drawer of typed results.
- **Reaction chains:** several steps per environment, links from products to later reactants, overall equation by step
  factors, Hess sums, forward and target mode, AE/E-factor/PMI over the chain.
- **Research window "Nachschlagen"**: elements, substances, table values, solvents, indicators, constants (CODATA
  2022 / SI 2019 with source), sources; "→ Umgebung" copies a value with its provenance, "Einsetzen" records where it
  was used.
- **Values between environments** (⇄): live (default) or snapshot, one versioned share per source environment, a new
  version only when a value changes; changed live values that were already inserted are marked.
- **Shared inputs:** TGA step table → measured vs theoretical loss of a balanced decomposition; FTIR peak table →
  bands expected from the drawn structure's groups. Pinned, live or copy; status current / update / stale / failed;
  "Herkunft …" shows the chain back to the raw file. The footer button "Geteilte Eingabe …" appears only when there is
  something to bind; it is always under "Modul ▾".
- **Rechner and project index:** "An den Rechner" publishes a versioned `chem.values` share; the Rechner shows where
  each value came from. Molar masses and other values go to the project index ("In den Projektindex …").
- German/English switch for the header, tasks, tabs, cards and board; older result texts are still German only.

## Planned and open

### Additional features (feature specification of 17 Nov 2026)
Source: `01_Elementrechner_Additional_Features.md` (features F01–F15, written against version 0.4.0). The table says
where each feature stands after version 0.8.0. Lab workflows (L) were built first (0.7.0), then phases 6 and 7, the
speciation and smaller items, the sharing slices and the UI phase (0.8.0).

| Feature | State after 0.8.0 | Goes into |
|---|---|---|
| F01 Prepare a solution from a solid (hydrate-aware, purity, worksheet) | done (0.7.0) | – |
| F02 Prepare from a liquid reagent or stock (mass fraction, density, assay) | done (0.7.0) | – |
| F03 Serial dilution, mixing several stocks, reverse calculation | done (0.7.0) | – |
| F04 Reaction setup and scaling (equivalents, reagent table, rescaling, observed vs planned) | done (0.7.0) | – |
| F05 Green metrics: E-factor, reaction mass efficiency, PMI, stated process boundary | done (0.7.0), plans compared side by side | – |
| F06 Redox and electrochemistry | done (current efficiency and electrolysis yield in 0.6.0) | – |
| F07 Acid–base, buffers, titration | done (pKw(T), indicators, common buffers first in 0.6.0; buffer recipe from real chemicals in 0.7.0) | – |
| F08 Speciation, saturation index, activity models | done (ER-S01…S03) | S |
| F09 Gas-law and physical-state helpers in the tool | done (0.7.0; ideal gas only) | – |
| F10 Cp(T) thermodynamics, Q, equilibrium composition | done (ER-701/702) | 7 |
| F11 Kinetic fitting and simulation | done (ER-703/704) | – |
| F12 Nuclear chemistry and isotopes | done (tab "Kern"; no IntCal calibration, no dose) | – |
| F13 Molecule cards, vector structures, naming, Benson, more property tables | done (ER-401…404, ER-X01…X04) | – |
| F14 Use results shared by FTIR/TGA (peak table, TGA mass loss vs theory) | done (A3, A6) | – |
| F15 Task-first UI, "Use in …" with typed objects, stale/live inputs | done (UI-02, UI-11…15, A4) | – |

Rules from the specification adopted for all new work (most already apply):
- **No hidden assumptions:** never assume a density, additive volumes, an activity model or a standard state. If a
  needed value is missing, ask for it (e.g. molality → molarity needs a density).
- **Chemical identity is explicit:** hydrate vs anhydrous form, salt vs active ion, isotopologue, phase. Never swap one
  for another silently.
- **Every result states its basis:** e.g. "c(Cu²⁺)" vs "c(CuSO₄·5H₂O)", "E-factor including solvents".
- **Measured, derived and estimated values stay visibly apart;** unsupported cases say "unsupported" instead of
  guessing.
- **Corrections create a new version;** a value already in a report is never silently replaced (Folio Refresh already
  rebuilds from the saved state).
- **Sharing is always an explicit user action** (as today with "Send to report").

### L – Lab workflows (new)
- **Solution from a solid (F01) – done (tab "Ansetzen"):** target concentration and its basis (mol/L, mmol/L, µmol/L,
  g/L, mg/L, % (w/v), % (w/w), mol/kg) for a named reference species (e.g. Cu²⁺ while weighing CuSO₄·5H₂O), final
  volume, purity → mass to weigh, with every step, rounding to the balance (and the resulting actual concentration),
  smallest fitting volumetric flask, and a printable worksheet. Several solids in one solution (own mixtures). Mass
  fraction and molality need the density of the finished solution with source and temperature; without it the tool
  refuses. Checked: 250 mL 0,100 mol/L CuSO₄ = 6,242 g pentahydrate or 3,990 g anhydrous.
- **Solution from a liquid reagent, stock or certified standard (F02) – done:** stock as mol/L, g/L, mg/L, % (w/v) or
  % (w/w) with density (source and temperature required) → aliquot volume, or mass to weigh; stated for the substance
  or the reference species (e.g. 1000 mg/L Cu standard). Always "fill up to volume", never added volumes. Checked:
  1 L 1 mol/L HCl from 37 % HCl (ρ = 1,184 g/mL) = 83,2 mL. No bundled density table yet (enter from the data
  sheet).
- **Dilution series and mixing (F03) – done:** step table (concentration, transfer from the previous step, fill-up
  volume, approximate solvent) where each step keeps the chosen volume × replicates; warning below the minimum
  pipetting volume; only for mol/L, g/L, % (w/v). Mixing several stocks with several species by solute balance;
  solve Σ cᵢVᵢ = cV for any one unknown.
- **Reaction setup and scaling (F04) – done:** reagent table from the balanced equation in the main input (role,
  equivalents, purity, stock solution or neat liquid with sourced density → mass and volume), reference amount or a
  target product amount with expected yield, limiting reagent and excess; solvents, catalysts (mol%) and additives
  listed but outside the stoichiometry; observed masses and isolated yield beside the plan, never over it; rescale by
  a factor (equivalents and mol% stay).
- **Green metrics (F05) – done:** E-factor (Sheldon 2007), PMI (Jimenez-Gonzalez et al. 2011), reaction mass
  efficiency (Constable et al. 2002), solvent share and atom economy; the counting boundary (reagents, solvents,
  catalyst, additives, workup) is chosen and printed with the values; isolated or theoretical product mass stated.
  Comparing two plans side by side exists in `labcalc` (`compare`); in the page it follows with the report (L09).
- **Gas helpers (F09) – done:** pV = nRT with any one unknown in chosen units, molar volume at stated T and p,
  gas density pM/(RT) from a formula, Dalton partial pressures of a mixture; ideal behaviour only, with a note. Real
  gases (van der Waals) wait for sourced constants.
- **Buffer recipe (F07) – done:** a real recipe from the chemicals at hand: either two forms (e.g. NaH₂PO₄·H₂O +
  Na₂HPO₄·2H₂O) or one form adjusted with a titrant from a stock solution (e.g. Tris + 1 mol/L HCl). Solved exactly
  with the proton balance at the pH-tab temperature; check pH and ionic strength shown; unreachable pH refused with
  the reachable range; same worksheet and print as F01.
- **Rechner and report (done):** Rechner functions `m_prep`, `V_reag`, `m_buf`, `rho_gas`, `AE` (SI in, SI out) and
  library formulas for E-factor, PMI, RME, yield and mixing, each with its source. The report gets an "Ansetzen"
  section with every open calculation: worksheets (German report), dilution table, reagent table, green metrics with
  their counting boundary, and a side-by-side comparison of up to four saved set-ups.

### S – Speciation and activity (new)
- **Done (ER-S01…S03):** Davies / extended Debye–Hückel switch in the pH tab (corrected next to ideal, also for
  buffers); metal–ligand distribution vs pH with conditional constants and balance residuals; saturation index.
- Activity coefficients (Davies; extended Debye–Hückel) with their validity range, switchable, and the effect shown
  next to the ideal result.
- Metal–ligand speciation vs pH from the stability constants already in the data (NIST SRD 46); conditional constants.
- Saturation index and "precipitation possible" (not a predicted amount); charge and mass balance residuals and solver
  diagnostics shown.
- Start with documented systems (phosphate, carbonate, Cu²⁺/NH₃) and widen only with reference checks.

### X – Results from other tools and calculation history (done, see "Overview, environments and sharing")
- Take a TGA step result (mass loss %) and compare it with the theoretical loss of a decomposition from the equation
  (e.g. CaC₂O₄·H₂O, CaCO₃ → CaO + CO₂), with the deviation and assumptions recorded.
- Take an FTIR peak table or functional-group hypothesis and compare it with a structure.
- A local calculation history: inputs, method, sources, outputs; dependent results marked stale when an input changes.
- How results move between tools (Shareboxes, environments, a project-wide index) is specified in
  `02_Elementrechner_Architecture_and_Modularization.md` and `03_Laboratory_Suite_Architecture_and_Sharing_Policies.md`.
  That is a suite-wide change to all modules, planned in `docs/ARCHITECTURE.md`: the TGA comparison is its first
  slice (stage A3), the FTIR comparison stage A6, the Elementrechner's internal tool families and variable drawer
  stage A9 (together with the UI phase).

### Phase 4 remainder
- **Done:** Benson group additivity for ΔfH°(g), S°(g) and Cp°(g) at 298 K (group values from Domalski & Hearing
  1993, C/H/O molecules without non-benzene rings); labelled "Benson", preferred over Joback, after tabulated values.
- **Done:** designer molecule card in the report (structure, name and its origin with citation, exact, derived and
  estimated properties in one table, estimates marked with their method and source).
- **Done:** structure images in the report as vector PDF, drawn from the editor's 2D coordinates (skeletal formula,
  heteroatom labels with implicit H and charges, wedge and hashed bonds).
- **Done:** wider rule-based naming – common aromatic and saturated heterocycles (pyridine, furan, thiophene,
  pyrrole, imidazole, oxolane, piperidine, morpholine …), secondary and tertiary amines, N-substituted amides,
  retained acetamide/formamide/acetonitrile. Fused rings, lactams and partly hydrogenated rings are still refused
  (PubChem on request).

### Phase 5 remainder
Done in 0.6.0 (tickets ER-501…503). Activity coefficients (Davies / extended Debye–Hückel) moved to S. Not planned:
pKa at other temperatures (no sourced ΔH of ionisation in the data; the note says so).

### Phase 6 – nuclear chemistry (done, tab "Kern")
- **Done:** nuclear equations read and checked (Z and A conserved), mode recognised (α, β⁻, β⁺, EC, IT, SF, 2β⁻,
  n, p, induced reaction); Q-value from AME2020 atomic masses with the electron handling per mode and its
  uncertainty; binding energy per nucleon and mass defect.
- **Done:** decay law (N, A, m at time t; half-life, mean life), specific activity, Bq ↔ Ci with prefixes.
- **Done:** decay chains along the main branch (NUBASE2020), Bateman solution in 60-digit decimal arithmetic, N(t)
  chart, secular / transient / no equilibrium with activity ratio and time of the daughter maximum.
- **Done:** dating – ¹⁴C (conventional age BP with the Libby half-life, Cambridge and NUBASE half-lives beside it;
  calibration note, no calendar ages), K–Ar, Ar–Ar (J), U–Pb (²⁰⁶Pb/²³⁸U, ²⁰⁷Pb/²³⁵U, concordance), Rb–Sr isochron;
  assumptions printed with each result.
- **Done:** isotope pattern of a formula (NUBASE2020 abundances), mean atomic mass of enriched mixtures.
- **Done:** Rechner functions `Qval`, `Bnuc`, `Thalf`, `Aspec`, `Ma`; report section "Kernchemie" with values, chain
  figure and isotope-pattern table, cited to AME2020, NUBASE2020, CODATA 2022, Bateman 1910 and the dating sources.
- Not included: dose and radiation protection; radiocarbon calibration against IntCal20 (conventional ages only).

### Phase 7 – temperature dependence and kinetics
- **Done (ER-701):** Cp(T) from the Burcat NASA-7 polynomials: ΔH(T), ΔS(T), ΔG(T), K(T) with validity ranges
  flagged, T where ΔrG = 0, van 't Hoff; the constant approximation is shown alongside (dashed curve). Checked
  against NIST-JANAF for NH₃ (±0,01 in log Kf).
- **Done (ER-702):** reaction quotient Q and direction; equilibrium composition from initial amounts (gas at p,
  solution at V), solver diagnostics shown; ideal behaviour stated.
- **Done (ER-703/704):** kinetics from own data: Eₐ and A (Arrhenius), ΔH‡/ΔS‡ (Eyring) with standard errors and
  residual plots; reaction order 0/1/2 from concentration– or conversion–time data; rate-law simulation (0th–2nd
  order, A + B, consecutive, reversible) with RK4 check; k(T) and half-life from an entered Eₐ with source.
- **Done (ER-705):** adiabatic flame temperature at constant pressure (complete combustion, no dissociation, φ ≤ 1),
  checked against a NIST-JANAF hand calculation for methane/air.
- From F10/F11: the current constant-ΔH/ΔS approximation stays as a selectable, labelled method; fits keep the data
  range, model, residual plot and parameter uncertainties; integrate rate laws to predict concentration vs time.

### Last phase – UI refinement (all Folio Lab tools) – done
Requested 17 Nov 2026 and built in UI-01…16 (see "Overview, environments and sharing"); kept here as the brief. Principle: a minimal first view that unfolds into detail
on demand, instead of many windows and text at once.
- Type an equation, then click a species in it: details unfold (name, structure if known, molar mass, key data);
  "draw structure" when none is defined.
- Draw a molecule and insert it into the equation; formula, molar mass etc. are then defined there.
- Advanced sections (worked solution, thermochemistry, redox, look-ups) appear when asked for, not all the time.
- Molecule designer: bonds snap to a grid shown as faint dots, so long chains are quick to draw; an easy element
  palette (N, O, S, P, halogens, Si, any element from the periodic table), not just C and H.
- The same principle applies to the Rechner, FTIR, TGA and tensile tools.
- From F15: task-first entry points (identify substance, balance, scale reaction, prepare solution, calculate pH,
  thermodynamics, kinetics); "Use in …" passes the substance or result itself, not its text; results show when an
  input has changed and they need recalculating.
- Noted during phase 5: the thermochemistry table overflows sideways in a narrow window; the acid/base-medium
  buttons announce the whole equation to screen readers instead of "sauer"/"basisch". Phase 5 sections are already
  folded by default.

### Smaller items – done
All built in ER-X01…X04 (see "More look-ups"); molarity, dilution, gas helpers and E-factor went into L.

### Still open
- Older result texts inside the panes are German only (headers, tasks, tabs, cards and board are German/English).
- Not planned: dose and radiation protection; radiocarbon calibration (IntCal20); pKa at other temperatures.
