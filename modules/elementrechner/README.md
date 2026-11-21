# Elementrechner

Chemistry on paper, with a source for every number. The Elementrechner (German for "element calculator") balances
equations and works out molar masses, amounts, yields, thermochemistry, pH, speciation, redox potentials, solution
recipes, gas quantities, nuclear Q values and decay, dating ages and kinetic parameters. It also names drawn molecules.
It runs locally inside Folio Lab and sends results, with their references, to a LaTeX report.

The module keeps three kinds of values apart and labels each one:

* **tabulated** values, taken from a cited data set (atomic weights, formation data, pKa, stability constants …);
* **calculated** values, derived from tabulated values with a stated formula (for example ΔfG° from ΔfH° and S°, or
  Ksp from ΔfG°);
* **estimated** values from group-contribution methods (Benson, Joback) and other increment schemes. These are used
  only when no tabulated value exists.

Module version: see `module.json` (currently 0.12.0). Feature list: [FEATURES.md](FEATURES.md). Methods, formulas,
defaults, limits and test references: [docs/methods/elementrechner.md](../../docs/methods/elementrechner.md).

## Starting

* **In Folio Lab:** open **Elementrechner** on the home page. The module server starts in the background.
* **On its own:** `python -m elementrechner.server`, run from `modules/elementrechner`. It serves the page on port
  8769 and opens a browser. Options: `--port N`, `--out <folder>` (where own substances are stored) and `--no-browser`.

The page starts in German. Switch to English with **DE | EN** in the header. Some result texts inside the panes are
still German only. In this guide, labels are given in English, with the German label in parentheses the first time
they appear.

## The page at a glance

* **Overview (Übersicht)**: the start view when the project has environments. It shows the project index and shares
  from other modules on the left, your environments in the middle, and this module's own shares on the right. Click a
  box to open an environment. Use **◂ Overview (◂ Übersicht)** in the header to return.
* **Environment**: one working state. It holds an equation, the tools you added and their inputs. Environments are
  kept across restarts.
* **What would you like to do? (Was möchten Sie tun?)**: a task list at the top that opens the right tool.
* **Reaction equation (Reaktionsgleichung)**: the main input line. The species in the equation appear as cards below
  it.
* **+ Tool (+ Werkzeug)**: adds a tool to the environment. Nothing is on by default.
* **Tabs** on the right: Substance (Stoff), Elemental analysis (Elementaranalyse), Own substances (Eigene Stoffe), pH,
  Prepare (Ansetzen), Kinetics (Kinetik), Nuclear (Kern) and Sources (Quellen).
* **Header buttons**:
  * **Worked steps / Results only (Rechenweg / Nur Ergebnisse)**: show the full worked solution, or results only.
  * *Periodensystem* (periodic table, F2), *Moleküle* (molecule collection, F3) and *Designer* (molecule designer,
    F4). These three labels are German only.
  * **Values … (Werte …)**: the results of the page as typed quantities.
  * **📖 Look up (📖 Nachschlagen)**: elements, substances, tabulated values, solvents, indicators, constants and
    sources.
  * **Connections ▾ (Verbindungen ▾)** and **Module ▾ (Modul ▾)**.
  * **To report … (Zum Bericht …)**.

## Main workflows

### Balance an equation
Task **Balance an equation (Gleichung ausgleichen)**, or type into **Reaction equation**. Write it as on paper:

* arrows `->` or `=`, and `<=>` for an equilibrium;
* charges `SO4^2-`, `Fe^3+`;
* phases `(s) (l) (g) (aq)`;
* hydrates `CuSO4·5H2O` (`*` also works);
* isotopes `^14C`, `D`, `T`;
* particles `n`, `alpha`, `beta-`, `gamma`, and `?` for an unknown particle.

Leave coefficients empty and they are determined. Coefficients you enter are checked. If an equation cannot be
balanced, the page says which element fails. If the balance is not unique, it shows the independent solutions rather
than picking one. Under the equation you find:

* the reaction type, with its reason;
* the net ionic equation;
* oxidation numbers and half-reactions;
* E° from formation data, Nernst and Faraday.

You can type substance names instead of formulas (German or English, for example `Essigsäure + NaOH -> …`). The
formula used is always shown.

### Molar mass, composition and formula from analysis
* Task **Identify a substance (Stoff bestimmen)**, or the **Substance (Stoff)** tab: enter a formula, name or CAS
  number. You get the molar mass with its uncertainty, mass fractions and the substance card.
* Task **Formula from analysis (Summenformel aus Analyse)**, or the **Elemental analysis (Elementaranalyse)** tab:
  enter mass fractions, and optionally a molar mass. You get the empirical and the molecular formula.

### Amounts, limiting reagent and yield
Add the tool **Amounts and stoichiometry (Mengen und Stöchiometrie)**. Enter the mass, amount, gas volume or
concentration × volume of one or more reactants. You get:

* the limiting reagent and the extent of reaction;
* theoretical amounts and masses, and the excess;
* atom economy;
* the yield, if you enter the amount of product obtained.

For several steps, use the reaction chain with **+ Step (+ Schritt)**. It builds the overall equation, applies Hess's
law and gives the overall yield.

### Thermochemistry and equilibrium
Task **Thermodynamics (Thermodynamik)**, or the tool **Thermochemistry (Thermochemie)**. You get:

* ΔrH°, ΔrS°, ΔrG°, K and lg K at 298.15 K and 1 bar, and the temperature T* at which ΔrG° changes sign;
* the heat for the entered amounts.

Each species shows which data set its values come from, and you can switch data sets per species. For other
temperatures, a Cp(T) model from NASA polynomials is used where they exist. The constant-ΔH/ΔS approximation is shown
alongside. The same card also gives the reaction quotient and the equilibrium composition.

### pH, titration, buffers and speciation
Task **Calculate pH (pH berechnen)**, or the **pH** tab. Enter a mixture such as `0,1 M CH3COOH; 0,05 M CH3COONa`.
You get:

* the pH from the full proton balance, between 0 and 100 °C;
* species fractions, and the pKa values used, with their sources;
* a titration curve with equivalence points and suitable indicators;
* a buffer finder;
* activity corrections (Davies or extended Debye–Hückel), shown next to the ideal result;
* metal–ligand speciation and the saturation index.

### Preparing solutions and planning reactions
Use the **Prepare (Ansetzen)** tab.

* Task **Prepare a solution (Lösung ansetzen)**:
  * mass to weigh from a solid (hydrate-aware, with purity);
  * aliquot volume from a liquid reagent or stock solution;
  * dilution series and mixing;
  * buffer recipes from real chemicals;
  * ideal-gas helpers.
* Task **Plan a reaction (Ansatz berechnen)**: a reagent table from the balanced equation, with equivalents and
  purities, scaling, and green metrics (E-factor, PMI, RME, atom economy).

Mass fractions and molalities need the density of the solution, with its source and temperature. Without it, the
module refuses the calculation instead of assuming a value.

### Kinetics
Task **Kinetics (Kinetik)**. The tab covers:

* activation energy and pre-exponential factor (Arrhenius), and ΔH‡ and ΔS‡ (Eyring), from (T, k) data;
* reaction order 0, 1 or 2 from concentration–time or conversion–time data;
* rate-law simulation;
* k(T) from a sourced Eₐ;
* adiabatic flame temperature.

**From dataset … (Aus Datensatz …)** reads a series from a dataset made in the Datenaufbereitung module and converts
its units.

### Nuclear chemistry
Task **Nuclear chemistry (Kernchemie)**, or the **Nuclear (Kern)** tab. The tab covers:

* Q values and binding energy;
* the decay law and specific activity;
* decay chains with the Bateman solution;
* dating: ¹⁴C, K–Ar, Ar–Ar, U–Pb and the Rb–Sr isochron;
* isotope patterns and the mean atomic mass of enriched mixtures.

### Look-ups, own substances and the molecule designer
* Task **Look up values (Werte nachschlagen)**, or **📖 Look up**. You get pKa, Ksp, lg K and physical properties. Each
  value comes with its source, temperature, ionic strength and medium. A fixed rule proposes one value, and you can
  choose another. A value can be copied, with its source, into the environment and inserted into input fields from
  there; the report then records where it was used.
* **Own substances (Eigene Stoffe)**: substances outside the collection, each value with a source. Own values take
  precedence over tables. They are stored in `eigene_stoffe.json` in the module's output folder, and can be exported
  and imported as JSON or SDF.
* *Designer* (F4): draw a structure, or paste SMILES or a molfile. You get:
  * the exact formula, molar mass and monoisotopic mass;
  * a rule-based IUPAC name, or the name of the matching collection entry;
  * estimated properties, each labelled with its method.

  The structure can be saved as an own substance.

### Measurement uncertainty

* A small **±** next to an input states its uncertainty (value, limits, % of value, repeats, or glassware and balances
  from the instrument library). Without one the value is exact.
* **± GUM** in the header picks the method once for the page (GUM, Monte Carlo, Gauss, worst case) and opens your own
  instruments.
* Uncertainties are given for the molar mass (always: CIAAW intervals as rectangular distributions, Possolo et al.
  2018), the concentration of a solution from a solid ("weighed g") or from stock ("measured"), every step of a
  dilution series (with the correlation of the steps), the unknown of the gas law, the yield (equation and reaction
  set-up) and the pH (from ± on c and pKa, in the fold under the pH result).
* Each result shows "value ± U". The budget and the method comparison sit in folds. The values go to the value drawer
  and the project index with `u`, and to the report with budget tables. Details: `docs/methods/elementrechner.md`,
  section 19.

## Sending results on

* **To report … (Zum Bericht …)** creates a report section with:
  * the equations and worked solutions;
  * tables and figures;
  * `\labval` values such as `dH-r`, `dG-r`, `K-298`, `ph` and `V-eq1`;
  * a reference for every data source used.

  In the editor, **Refresh** rebuilds the section from the saved inputs.
* **Values … (Werte …)** sends results to the Rechner (calculator) module, or to the project index with
  **To project index … (In den Projektindex …)**. Each hand-over is a new version.
* **Project index … (Projektindex …):** *Use* (*Übernehmen*) adds a value to the taken values with its unit,
  uncertainty and origin; from there it goes into an input field. A field that declares a unit converts the value
  and refuses a different dimension.
* **Connections ▾ (Verbindungen ▾)** shares values between environments, either live or as a snapshot.
* **Shared input … (Geteilte Eingabe …)**, under **Module ▾**, compares:
  * a TGA step table with the theoretical mass loss of a balanced decomposition;
  * an FTIR peak table with the bands expected from a drawn structure.

## Data at a glance

All data are in `sdk/python/labcalc/data/`. The methods document lists each file with its recorded source and number
of entries.

| Data | Source as recorded |
|---|---|
| Standard atomic weights | CIAAW 2024 (abridged values; intervals kept) |
| Isotope masses, half-lives, decay modes, abundances | AME2020, NUBASE2020, CIAAW isotopic compositions 2024 |
| Formation data ΔfH°, ΔfG°, S°, Cp° and NASA-7 polynomials | CODATA Key Values (Cox et al. 1989); NBS tables (Wagman et al. 1982, NIST digital edition 2020); Burcat/Ruscic database (2018, with ATcT values) |
| Stability constants, protonation constants, solubility products | NIST SRD 46, version 8.0 |
| pKa (organic compounds) | IUPAC Digitized pKa Dataset v2.4. Licence CC BY-NC 4.0: not part of the public repository; see *Optional reference data* in the [Folio Lab README](../../README.md). Without it, pKa values come from NIST SRD 46, the PubChem property records and own values only |
| Physical properties | PubChem PUG View, from open-licence sources only (ICSC, HSDB, DOE PAC, OSHA, NIOSH), each with its primary reference |
| Molecule collection (1822 substances) | PubChem (structures, names, CAS numbers); German names from Wikidata |
| Element properties | PubChem Periodic Table |
| Ionisation energies | NIST Atomic Spectra Database |
| Benson group values | Domalski & Hearing 1993 |
| Acid–base indicators | Harris, *Quantitative Chemical Analysis*, 9th ed. 2016 |
| Physical constants | CODATA 2022 and the SI Brochure (2019) |

A few small tables were typed in from textbooks, and the code marks them as still to be checked against the printed
source:

* the indicators;
* Antoine coefficients;
* cryoscopic and ebullioscopic constants;
* Shannon ionic radii;
* mean bond enthalpies.

The methods document says which ones.

## Tests

From `modules/elementrechner`, with `sdk/python` on the Python path:

```
python -m unittest discover -s tests
```

The shared chemistry core has its own tests in `sdk/python/tests/test_chem.py`. The methods document lists which test
checks which result against which reference value.
