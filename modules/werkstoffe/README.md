# Werkstoffe (materials)

Materials science and engineering in one page: choosing materials, crystallography and XRD, phase diagrams and steel,
and the mechanics and lab data of a materials lab (laminates, fatigue, Weibull, fracture, hardness, corrosion, creep).
Every value and every equation has a source; anything that is computed or drawn schematically, rather than measured,
says so in the page, the figure and the report.

Module version: see `module.json` (currently 0.1.0). Methods, formulas, defaults, limits and test references:
[docs/methods/werkstoffe.md](../../docs/methods/werkstoffe.md).

## Starting

- **In Folio Lab:** open **Werkstoffe** on the home page. The module server starts in the background.
- **On its own:** `python -m werk.server` in `modules/werkstoffe` (with `sdk/python` on `PYTHONPATH`). It serves the
  page on port 8775 and opens a browser. Options: `--port N`, `--aus <folder>` (outputs and environments),
  `--kein-browser`.

The page starts in German; **DE | EN** in the header switches the language.

## The page at a glance

- **Rail on the left:** the four areas **Auswahl** (selection), **Kristall** (crystal), **Phasen** (phases) and
  **Mechanik** (mechanics).
- **Tabs on the right:** the tools of the area. Mechanics shows Laminat, Ermüdung, Weibull and Härte; Bruch, Korrosion
  and Kriechen are under **Mehr ▾**.
- **Middle:** the chart of the current tool. Wheel zooms, drag pans, double-click or `0` resets; hover shows values;
  some charts take clicks (add a material to the comparison, set a point in a phase diagram, rotate the unit cell).
  Views of a tool (e.g. *Muster · Williamson–Hall · Nelson–Riley* in XRD) are buttons above the chart.
- **Inputs and results** are in the pane on the right. Less common settings are folded away.
- **Menus:** *Datei* (open files, CIF, tables, report, project index, save view as SVG), *Werkzeuge*, *Ansicht*,
  *Hilfe* (what the labels *schematisch*, *berechnet* and † mean).
- **Overview:** with a project open, the module starts in the environment overview like the other modules. Datasets
  shared from Datenaufbereitung can be imported into S–N, Weibull, hardness, creep and polarisation tools.

## Tools

| Area | Tool | What it does |
|---|---|---|
| Auswahl | Ashby-Diagramm | any two properties from the shared materials database on log axes; performance index lines, limits, ranked list with reasons; your own values with their source (*Eigene Werte*); Materials Project points only with the toggle (*berechnet (DFT)*) |
| | Karten | side-by-side cards of 2–6 materials with value kind and source; search by name, alias or designation |
| Kristall | Kristall | cell, (hkl) plane and [uvw] direction in a rotatable cell; d, angles, X-ray density; computed powder pattern for a chosen tube |
| | Gitter | lattice section of a base element at a temperature: phase and a(T), dissolved atoms on interstitial or lattice sites in their true number, second phase above the solubility limit, equilibrium vacancies, Debye vibration, distortion; schematic edge dislocation, stacking fault and tilt grain boundary; views 3D (rotate, zoom), unit cell, atomic layer (hkl); optional labelled exaggeration of vacancies and vibration; examples (C45, austenite, Cu–Ni, Al–Si, Cu near Tm) |
| | XRD | open a diffractogram (xy/CSV/TXT, `.xrdml`, `.brml`, `.raw` RAW1.01, `.uxd`, `.ras`); background, peaks, cubic indexing, lattice parameter (Nelson–Riley), Scherrer, Williamson–Hall, phase search against built-in and CIF phases, stick overlays, semi-quantification |
| Phasen | Phasendiagramm | Fe–Fe₃C, Pb–Sn, Al–Si, Cu–Ag, Cu–Ni (schematic after cited points) or a computed ideal/regular-solution diagram; click sets the point; lever rule, constituents, cooling path |
| | Stahl | CE (IIW), CET, Pcm, preheat (EN 1011-2), Ms, Ac1, Ac3, Hollomon–Jaffe, carburising profile and case depth |
| Mechanik | Laminat | CLT: ABD, engineering constants, ply stresses through the thickness, max stress / Tsai–Hill / Tsai–Wu / Hashin, first-ply failure |
| | Ermüdung | S–N fit with run-outs and band, Haigh diagram, Marin factors, rainflow and Miner |
| | Weibull | LSQ and MLE, bootstrap intervals, quantiles, size effect |
| | Härte | HV/HB/HK from indents; conversion only with your own table file; E112 grain size; Hall–Petch |
| | Bruch | K_Q for SE(B) and C(T) with the E399 checks; critical crack size |
| | Korrosion | Tafel lines and Butler–Volmer fit of a polarisation curve, Stern–Geary, corrosion rate (G102) |
| | Kriechen | Larson–Miller and Norton–Arrhenius |

Every tool has **Beispieldaten (synthetisch)**: synthetic example data generated in the page, labelled as such.

## Files

- Diffractograms: drop the file on the page or **Datei → Öffnen …**. If the file names no wavelength, Cu Kα is
  assumed and the result says so; choose the tube under *Wellenlänge*.
- CIF (e.g. from the Crystallography Open Database): **Datei → CIF öffnen …**. The phase is used in the crystal tool,
  as a reference phase and in the search, and its publication is cited.
- Tables (S–N data, strengths, indents, creep data, polarisation curves): open a CSV/TXT, paste into a grid, or
  import a shared dataset. Columns are mapped in a small dialog.
- Hardness conversion table: a CSV/TSV you make from **your own copy** of the standard, first row the scale names
  (e.g. `HV;HB;HRC;Rm`), optionally a line `# Quelle: ISO 18265:2013, Tabelle A.1`. It is never bundled with the
  module.

## Sending results on

- **Zum Bericht …** (Lab button): the current tool or all computed tools as one report section: figures, tables,
  `\labval` values, data for pgfplots, methods and results text, and a reference for every source and data file.
  **Refresh** in the editor rebuilds it from the stored inputs and files.
- **Ergebnisse in den Projektindex …** and the environment overview share values with other modules.

## Data at a glance

| Data | Source |
|---|---|
| Material properties | shared database `sdk/python/labcalc/data/materials.json` (one value, one source; marked † where not checked) |
| Built-in crystal structures (38) | Wyckoff, *Crystal Structures* (1963) — `werk/data/phases.json` |
| Atomic form factors | Cromer–Mann coefficients, International Tables Vol. C, Table 6.1.1.4 (transcribed; see the methods page) |
| Phase-diagram key points | Callister & Rethwisch; Murray & McAlister 1984 (Al–Si); Subramanian & Perepezko 1993 (Cu–Ag) — `werk/data/diagrams.json` |
| X-ray tube wavelengths | standard values as used by instrument software (Bearden 1967) |

No ICDD/PDF data and no hardness conversion tables are included.

## Tests

From `modules/werkstoffe`, with `sdk/python` on the Python path:

```
python -m unittest discover -s tests
```
