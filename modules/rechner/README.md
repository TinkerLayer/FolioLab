# Rechner

Scientific calculator for Folio Lab: variables with units, **sheets** (boxes with calculation lines and formula
cards; formerly called "environments"), a Desmos-style graph and matrices. **To report …** (*Zum Bericht …*) sends
results to a Folio Lab report (worked calculation, table of quantities, `\labval`, plots, calculation lines,
matrices). Everything runs locally. The whole working state belongs to an **environment** of the project (see below)
and survives a restart; saving as a JSON file still works (**⋯ ▸ Save as file** (*Als Datei speichern*) / **Load
from file …** (*Aus Datei laden …*), Ctrl+S). Older working states (one worksheet) are moved into a sheet when
loaded.

What each computation does, its limits, references and the tests that check it are described in
[Rechner: methods and validation](../../docs/methods/rechner.md).

The app starts in German. Labels are given as **English label** (*German label*). Parts of the page exist only in
German (see below); their labels are given in German with a translation in quotation marks.

## Overview, environments and origin

* The Rechner opens on the **Overview** (*Übersicht*): project index, values that the Elemental Calculator module
  has sent to the Rechner, the Rechner's environments (**+ Environment** (*+ Umgebung*)) and its own shares. A click
  opens an environment; **◂ Overview** (*◂ Übersicht*) or the browser's back button leads back. An environment holds
  the whole working state with all sheets.
* **Take as variables** (*Als Variablen übernehmen*, in a values box on the overview) and *In den Rechner
  übernehmen* ("send to the Rechner") in the Elemental Calculator create variables with an **origin**:
  "↳ aus Elementrechner · Umgebung · Freigabe s-… v n" ("from Elemental Calculator · environment · share s-… v n");
  after a change of value or unit it reads "hier geändert" ("changed here"). **Project index …** (*Projektindex …*,
  header) takes over an index value with the origin "↳ Projektindex g-…". The table of quantities in the report names
  the origin. *Herkunft* ("origin") shows the chain back to the measurement file.
* Header: tabs, DEG/RAD, **complex** (*komplex*), project index, **⋯** (manage environments, save/load file), DE|EN,
  To report. The variables fold into a narrow bar **Variables (n) ▸** (*Variablen (n) ▸*); the library is closed at
  the start. Header, bar and overview are available in German and English; the rest of the page is still German.
* Formula cards that need each other (also through derived values) are marked as a **circular reference**
  (*Zirkelbezug*).

## Layout: variables and sheets

* **Variables** (*Variablen*, left panel): name, value and unit. The name is free (`v`, `Geschwindigkeit`,
  `Dicke Blech`, umlauts allowed; spaces become `_`), the value may be an expression (`2*3`, `1e-3`), the unit is
  typed freely (`km/h`, `N/mm^2`, `kg/m` …).
* **Recognition:** while you type, the Rechner suggests the **role** in the formulas from name and unit, also for
  typos and synonyms: "Geschweindigkeit" in m/s, "Tempo" or "Geschw" become *v* (velocity), "Gewicht" ("weight") in
  kg becomes *m*, "Strecke" ("distance") becomes *s*. For ambiguous words the unit decides ("Spannung" in MPa → *σ*
  (stress), in V → *U* (voltage)); without a unit the candidates are offered for selection (*Meinten Sie …*, "Did you
  mean …"). A recognised variable "stands for" *v*: formulas, derive and search for missing values treat it like *v*;
  in calculation lines both names work (`Geschwindigkeit/t` and `v/t`). If *v* is already taken on the same sheet,
  the role stays free and *v1*, *v2* … are offered. *ändern* ("change") shows all suggestions, *keine Rolle* ("no
  role") and the kind of quantity by hand.
* If a name matches nothing, the unit determines the kind of quantity (`x1` in mm → length). For units without a
  predefined kind (e.g. kg/m) a kind "quantity in kg/m" is created: the variable calculates with its unit in
  calculation lines but is not inserted into formulas automatically.
* Measurement units from the lab and environmental analysis have a kind as well: `pH` (scale, not picohenry),
  µS/cm (conductivity), %RH, NTU/FNU, AU, °dH, lx, dB, Gy/Sv, kat, CFU/mL and others. A pH value is inserted into
  formulas as a number (e.g. c(H⁺) from pH). Scales (pH, dB, NTU, FNU, FAU, AU) cannot be converted into each other
  or into %.
* Under *gilt in* ("applies in") you see where the variable is inserted: *alle* ("all", including future sheets) or
  individual sheets. Clicking a sheet while "all" applies restricts the variable to that sheet; after that, every
  click switches a sheet on or off.
* **Sheets** (*Blätter*, centre): coloured boxes, each a worksheet of its own. The head shows the variables that apply
  there (a click removes one, ＋ adds one), plus *ableiten* ("derive"), fold, duplicate, remove. This way, for example,
  two variants with different masses can be calculated side by side.
* **Library** (*Bibliothek*, right): formula collection (a click creates a card on the selected sheet) and
  functions/constants (a click inserts into the last used input line).

## Calculation lines

At the bottom of each sheet, *Rechnung eingeben* ("enter a calculation"); Enter creates the line. Lines can be
edited directly (Enter: new line, Backspace in an empty line: delete, arrow keys: move). Each line knows the
variables of the sheet, the results of the formula cards, the derived values and the assignments of the lines above:

| Input | Meaning |
|---|---|
| `2(3+4)^2`, `5!`, `2pi`, `3e-4` | implicit multiplication, power, factorial, power of ten |
| `sin(30)` | angle according to the **DEG/RAD** setting (top) |
| `k = 2*v`, `f(x) = x^2 - 2` | assignment and user function (valid in the following lines) |
| `inv(A)*b`, `A'`, `A[2,1]`, `det(A)*2`, `A^2+E` | matrices from the Matrices tab (valid on every sheet) |
| `integral(f(x), x, 0, 2)`, `deriv(x^3, x, 2)`, `nsolve(x^2 == 2, x, 1)`, `sum(k^2, k, 1, 10)` | calculus |
| `mean(L)`, `std(L)`, `linreg(x, y)`, `polyfit(x, y, 2)`, `roots([1,0,-4])` | statistics, polynomials |
| `v/t`, `E_kin -> kJ` | calculates in SI with units; `->` converts |
| `sqrt(-4)` with **complex** on | complex results, `2 + 3i` |

With `v` = 72 km/h and `t` = 8 s, `v/t` gives **2.5 m/s²**. ★ marks a line for the report (default: on).

**Own variables in calculation lines:** `50/3 = u` (name on the right) and `u = 50/3` (name on the left) create `u`;
the unit comes from the expression (`v*t = s_w` has m). `u` applies in the following lines of the same sheet. The
**⇄** button on such a line offers:

* **Use it on the other sheets too** (*Auch auf den anderen Blättern verwenden*) – the other sheets see `u` as a
  button "u ← Blatt 1". If two sheets pass on the same name, the first sheet's applies; the line shows a warning.
* **To another environment …** (*An eine andere Umgebung …*) – choose an environment and **live** or **snapshot**
  (*Momentaufnahme*). There `u` appears as a variable with the origin "↳ aus Umgebung …" ("from environment …");
  with "live" it changes along as soon as `u` is recalculated here, the snapshot keeps the current state.
  **⇄ Connections** (*⇄ Verbindungen*) in the header lists all connections (change, disconnect); on the overview they
  appear as arrows between the environments and can be drawn there as well.

**Inserting matrices:** above the calculation lines of each sheet, the matrices from the Matrices tab are shown as
buttons (name and size); a click inserts the name at the cursor of the last used line. While you type, an
**autocomplete** suggests matrices, variables, values of the sheet, constants and functions (↑/↓ choose, Tab or
Enter accept, Esc closes). If the result of a line is a matrix or a vector, *→ Matrix* stores it under a name in the
Matrices tab, so that it can be used there and on all sheets.

## Dataset as variables

At the bottom of the variable bar, **Dataset as variables …** (*Datensatz als Variablen …*) opens the datasets that
Data Purification (*Datenaufbereitung*) has shared with the Rechner. After choosing a dataset, tick numeric columns
and choose **follows (newest version)** (*folgt (neueste Version)*) or **pinned (this version)** (*fest (diese
Version)*). Each chosen column becomes a list that applies on all sheets:

* Name = column key (`sigma`, `eps`, `F`); reserved names get `_ds` appended (`e` → `e_ds`).
* Values in SI units, the column's unit is kept: `mean(sigma)` gives Pa, so does `sigma/eps`, `max(F)` gives N,
  `mean(sigma) -> MPa` converts. Also `std`, `var`, `sum`, `len`, `trapz`, elements (`sigma[2]`).
* Excluded rows (marked "excluded") and rows with a gap in one of the chosen columns are dropped from **all** chosen
  columns, so that the lists match pairwise.
* `linreg(eps, sigma)` shows k, d and R², each with its unit (k in unit of y/x, d in unit of y);
  `linreg(eps, sigma)[1]`, or `fit = linreg(eps, sigma)` followed by `fit[1]`, keep the unit of the slope.
* A variable or matrix of the same name takes precedence; the bar reports the hidden column.

Below the column buttons (a click inserts the name into the last used line) the **Origin** (*Herkunft*) is shown:
title, share ID, version, follows/pinned and how many rows are used. A pinned binding offers **update to vN**
(*auf vN aktualisieren*) as soon as a newer version exists; a following binding calculates with the newest version on
every calculation (and when you return to the page). The binding is stored in the environment's working state, the
values are not – they come from the share each time. In the report, the *Methods* section names dataset, share ID and
version as soon as a calculation line uses such a variable; the version used is stored in the report's source (so it
is protected from deletion). **Refresh** in the editor takes the newest version for "follows" and the remembered one
for "pinned".

**Import a dataset …** (*Datensatz importieren …*; graph, variable bar or overview) opens the shared import window.
It lists all datasets of the project, those shared with the Rechner first, with search, preview and the choice between
"follows" and a fixed version. After that the dataset goes **Into the graph** (*In die Grafik*) or is bound **As
variables** (*Als Variablen*). From the overview, the target environment is chosen as well, or a new one is created.

## Solving equations and systems of equations

* A calculation line with `=` and exactly one unknown quantity is solved for it: `x^2 - 3 + x = 0` gives
  x₁ = (−1 − √13)/2 and x₂ = (−1 + √13)/2.
  - Polynomials up to degree 2 and rational roots are solved exactly, everything else numerically.
  - The unit of the unknown follows from the other quantities (`0.5*m*v^2 = Ek` gives v in m/s).
  - Conditions restrict the solutions: `…, x > 0`.
* Several solutions are stored as `x_1`, `x_2` …. `x` itself applies if there is exactly one solution or one is
  chosen. A numerical search shows at most 12 solutions (polynomials show all their real roots). Periodic functions
  get a note.
* **Solve a system of equations** (*Gleichungssystem lösen*) on the Matrices page, or `;` between equations in one
  line (`2x + 3y = 1; x - y = 2`):
  - Linear systems show A, b and the row echelon form. The result is a unique solution, a family of solutions with
    free parameters, or "no solution" with the least-squares solution.
  - Nonlinear systems are solved with Newton's method from several starting points.
  - A, b and the solution can be stored as matrices `A`, `b`, `xsol`.
* The **Σ symbol picker** (tooltip *Symbols and templates* / *Symbole und Vorlagen*) at the inputs inserts templates:
  sum, product, integral, derivative, roots, Greek letters, relations and units. The first gap is selected, so the
  code notation is not needed.

## Formula cards, derive, search for missing values

* *Formeln* ("formulas", 281, sorted by field and searchable): mechanics, strength of materials (tensile test,
  bending, torsion, buckling, fracture mechanics with K_I, hardness), geometry, heat, fluid mechanics, electrical
  engineering, optics/microscopy, mathematics and **chemistry**:
  - *Acids and bases:* pKa/pKb, ion product, pH of strong acids/bases, **weak acids and bases** (approximation and
    exact quadratic solution, e.g. 0.1 M acetic acid with pKa 4.76: pH 2.88), degree of dissociation, Ostwald's
    dilution law, Henderson–Hasselbalch, buffer capacity, ampholyte, diprotic acid, equivalence point of weak acids,
    titration.
  - *Solubility and equilibrium:* solubility product (AB and AₓBᵧ), pKsp, Kc ↔ Kp.
  - *Thermodynamics:* ΔG = ΔH − TΔS, crossover temperature, ΔG° = −RT ln K, ΔG = ΔG° + RT ln Q, van 't Hoff,
    Clausius–Clapeyron, heat of reaction, Kirchhoff.
  - *Electrochemistry:* Nernst, ΔG = −zFE, K from E°, cell potential.
  - *Colligative properties:* molality, mole fraction, Raoult, boiling-point elevation, freezing-point depression,
    osmotic pressure.
  - *Kinetics:* zero, first and second order with half-lives, Arrhenius (two temperatures), Eyring.
  - *Gases:* molar volume, Dalton, van der Waals.
  - *Radioactivity:* decay law, half-life, mean lifetime, activity (also time-dependent and from the mass), remaining
    fraction, specific activity, mass defect. Units Bq, Ci (with prefixes), Da.
* **Sources:** every formula names its source (textbook with keyword, or standard), every constant its own (CODATA
  2022, SI Brochure, IUPAC Green Book). The formula card shows "Quelle: …" ("source: …") and the origin of the
  constants used, and so does the tooltip in the library. In the report every worked calculation cites its formula
  and its constants (`\cite`); the calculation lines cite the constants used. The constants are the CODATA 2022
  values.
* In the card, the sheet's variables are inserted, but only if symbol **and** kind of quantity match (the `a` of the
  crack length is not the `a` of the acceleration). If there is exactly one variable of a kind and exactly one
  quantity of that kind in the formula, it is taken as well. Via *Quelle* ("source") each quantity can be assigned
  explicitly (variable, derived value, result of another card on the same sheet) or left free.
* If exactly one quantity is missing, it is calculated; at the top of the card the wanted quantity can also be set.
  The rearranged formula, the inserted values and the result (unit selectable) are shown. Formulas that cannot be
  rearranged in closed form are solved numerically; several solutions are offered for selection.
* *ableiten* ("derive"): general laws (marked *auto* in the collection) calculate further values from the variables,
  also over several stages (from `v` and `t` follows `a`, with `m` further `F`). ⇣ takes a derived value over as a
  variable of this sheet.
* *Gesucht …* ("wanted …") lists all formulas that yield a quantity, sorted by the number of missing values, with
  hints on how a missing value could be obtained. ＋ creates the missing value as a variable of this sheet.

## Graph

As in Desmos: a list of expressions on the left, the canvas on the right. Drawing happens while you type.

| Expression | gives |
|---|---|
| `y = x^2 - 2`, `f(x) = sin(x)/x` | function of x |
| `a = 1.5` | slider (▶ plays; limits left/right clickable) |
| `y = a x^2 + b` | missing names offer *Schieberegler anlegen* ("create slider"); `ax` counts as a·x, `sinx` as sin(x) |
| `x^2 + y^2 = 9`, `x = y^2` | equations in x and y |
| `(cos(t), sin(t))`, `r = 1 + cos(θ)` | parametric and polar curves (range below the line) |
| `(2, f(2))` | point |
| `integral(f(x), x, 0, 2)` | value |
| table (＋ → *Tabelle*), `y1 ~ m x1 + b` | measured values (paste from Excel) and regression with R² |
| formula curve (＋ → *Formelkurve*) | result of a formula card over one of its quantities |

The coloured circle shows/hides, right-click chooses the colour. Dragging pans, the mouse wheel zooms (Shift only x,
Alt only y). A click on a curve marks roots, extrema and intersections (a click on a point shows the coordinates),
press and hold traces the curve. ⚙ contains grid, view window, equal scaling, the choice of which sheet the variables
come from, and the labelling for the report. The camera remembers the view for the report.

**Large datasets:** the values stay on the server, the page receives only the visible points. Up to 4000 points all
are sent to the page. Above that, one point per screen cell is shown, for lines minimum and maximum per segment, so
that no peak is lost. Zooming reloads. The server draws the report figure, thinned in the same way to the figure's
resolution.

**Fit …** (*Anpassen …*) on a dataset or table row:
* Models: straight line, line through origin, polynomial of degree 2/3, logarithm, exponential, power, Arrhenius,
  Michaelis–Menten.
* Each model can be fitted **linearised** (*linearisiert*; unweighted straight line through the transformed values)
  or **direct** (*direkt*; least squares in y). The range is set by dragging in the graph.
* Result: parameters ± standard uncertainty with units (the 95 % confidence interval is in the tooltip), R², the
  linearised plot with residuals and the curve in the graph. Arrhenius gives Eₐ in kJ/mol and converts °C to K.
* **→ Variables** (*→ Variablen*) takes over the parameters. In the report, table and figure appear with dataset and
  version.

## Report

**To report …** (only visible inside Folio Lab) produces:

* *Worked calculation*: for each formula card the rearranged formula and the inserted values (`\[ … \]`, without
  amsmath), with several sheets one section per sheet,
* *Table of quantities* (booktabs): symbol, name, value, origin (sheet, or Elemental Calculator share or project index
  with version),
* *Values* for `\labval{<report>}{<key>}`; card values are called `k1-m` etc., with several sheets `u2-k1-m`,
* *Plots* as vector PDF plus CSV of the curve points, regressions with parameters and R²,
* the *calculation lines* marked with ★ and the *matrices*.

**Refresh** in the editor recalculates everything from the stored working state, **English/Deutsch** switches the
language.

## Technical notes

Calculation core in the SDK, shared with FTIR, Tensile test and TGA: `sdk/python/labcalc/units.py` (units, kinds of
quantity, constants), `expr.py` (parsing and evaluation, only permitted expressions, no `eval`), `render.py`
(LaTeX/HTML, rearranging), `sources.py` (sources for formulas and constants); `rechner/{units,expr,render}.py` only
forward to them. In the module: `library.py` (formula collection), `solver.py` (worksheet, derive, search),
`recognize.py` (recognise variables from name and unit, synonyms), `workspace.py` (sheets and scopes; internally still
`envs`), `graph.py` (expression list of the graph: classification, sliders, implicit curves, regression, special
points), `console.py`, `plots.py`, `bundle.py`, `server.py`, `dsvars.py` (resolve dataset bindings: columns as lists
with units). The server is stateless: the page sends the working state with every request (`/api/workspace`,
`/api/graph`).

New formulas: in `library.py` one line `EQ(id, field, topic, "lhs = rhs", Name, name, {symbol: "kind|label|label"}, auto=…)`.
Variables without an entry take the default from `SYMBOLS`. The source comes from `SECTION_SRC` (per field/topic) or
`SRC_OVERRIDE` (per formula), keys from `labcalc/sources.py`. The tests check every formula for unit consistency,
that every variable can be solved back, and that every formula and every constant has a source.

Start without Folio Lab: `python -m rechner.server` (port 8767). Tests: `python -m unittest discover -s tests`.
