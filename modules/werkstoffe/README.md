# Werkstoffe (materials)

Materials science and engineering in one page: choosing materials, crystallography and XRD, phase diagrams and steel,
and the mechanics and lab data of a materials lab (laminates, fatigue, Weibull, fracture, hardness, corrosion, creep).
Every value and every equation has a source; anything that is computed or drawn schematically, rather than measured,
says so in the page, the figure and the report.

Module version: see `module.json` (currently 0.5.0). Methods, formulas, defaults, limits and test references:
[docs/methods/werkstoffe.md](../../docs/methods/werkstoffe.md).

## Starting

- **In Folio Lab:** open **Werkstoffe** on the home page. The module server starts in the background.
- **On its own:** `python -m werk.server` in `modules/werkstoffe` (with `sdk/python` on `PYTHONPATH`). It serves the
  page on port 8775 and opens a browser. Options: `--port N`, `--aus <folder>` (outputs and environments),
  `--kein-browser`.

The page starts in German; **DE | EN** in the header switches the language.

## The page at a glance

- **Search (`Ctrl+K`, field in the header):** one search over tools, views and modes, materials (names, aliases,
  designations), phase diagrams, crystal phases and compendium entries, grouped by kind. Enter opens the tool with the
  material or view set; Shift+Enter opens a material in *Struktur*. With an empty field it lists the last used tools and
  all tools by task.
- **Rail on the left:** three groups by task: **Auswahl & Kennwerte**, **Struktur & Gefüge**, **Prüfen & Auswerten**.
- **Tabs on the right:** the tools of the group, last used first. The order is set when you enter a group, so no tab
  moves under the pointer; the rest are under **Mehr ▾**.
- **Middle:** the chart of the current tool. Wheel zooms, drag pans, double-click or `0` resets; hover shows values;
  some charts take clicks (add a material to the comparison, set a point in a phase diagram, rotate the unit cell).
  Views of a tool (e.g. *Muster · Williamson–Hall · Nelson–Riley* in XRD) are buttons above the chart.
- **Inputs and results** are in the pane on the right. Less common settings are folded away.
- **Kompendium:** the button in the header, or *im Kompendium* above the chart, which opens the entry of the current
  view. 195 entries: the tools and their views, the mechanism animations, the microstructure atlas, topics, and one
  entry per material (designation, every property with range, unit, source and check status, linked phases, atlas
  entries and mechanisms). The list has groups, a filter by kind and its own search. Every statement has a stable id
  and its own citation; a statement without a traceable source is marked as such, and every source shows its check
  status (†: not checked against the original, no mark: no check on record, which does not mean checked).
- **Info board (*Infotafel*, button in the header):** a free canvas for what you collect from the compendium. Pick one
  material or a series: *Zur Reihe* on the material card, the family button above the chart, **+ Reihe** or Alt+Enter in
  the search, or **+** next to a material or family in the compendium list. With a series, the compendium shows a bar to
  walk through the selected materials and the atlas and mechanism entries linked to them (‹ ›, Alt+← →). A pin appears on
  hover or keyboard focus next to an entry, section, statement, value and figure, and above the Ashby chart for its
  current view. A pin stores its ids, sources, check status and a copy of the content, so a later change in the
  compendium shows as *changed since pinned* and only enters a report when you press *Update*. On the board: drag cards,
  wheel zooms, drag pans; named frames can be moved, resized and reordered (their number is the order in the report);
  notes are your own text and are never cited; selecting two or more material cards offers a comparison table that is
  itself a pin. Several boards per project, saved with the project. Keys: arrows move, Shift larger steps, Enter unfolds,
  Space adds to the selection, Delete removes, Ctrl+Z undoes, N note, F frame, O opens the entry, 0 shows everything.
- **Project index:** *Datei → Projektindex* can put a stored value into the numeric field used last. The unit is
  converted to that of the field; a value of a different dimension is refused.
- **Measurement uncertainty** (Bruch, Härte, Stahl): **±** next to an input sets its uncertainty (instrument,
  resolution, limits, repeats, certificate …); the fold *Messunsicherheit* picks the method (GUM linear, Monte Carlo,
  Gauss, worst case) and opens your own instruments. Results show value ± U with a budget and a comparison of the
  methods; the report gets the same with a budget table. In Härte the scatter of the indents enters as type A by
  itself; force and length measurement are added in the fold.
- **Menus:** *Datei* (open files, CIF, tables, report, project index, save view as SVG), *Werkzeuge*, *Ansicht*,
  *Hilfe* (what the labels *schematisch*, *berechnet* and † mean).
- **Overview:** with a project open, the module starts in the environment overview like the other modules. Datasets
  shared from Datenaufbereitung can be imported into S–N, Weibull, hardness, creep and polarisation tools.

## Tools

| Area | Tool | What it does |
|---|---|---|
| Auswahl & Kennwerte | Ashby-Diagramm | any two properties from the shared materials database on log axes, one dot per material (materials known only by a range sit at its geometric mean, marked *nur Spanne*); performance index lines, limits, ranked list with reasons; your own values with their source (*Eigene Werte*); Materials Project points only with the toggle (*berechnet (DFT)*). A click selects a material: its cited range appears as a pale box and a card shows the main values with range and source, the decoded designation, and buttons to compare, copy (tab-separated) or share all values or single ones (Esc steps back). *Familien zeigen* draws the family outlines; a family's points appear after a click on it |
|  | Karten | side-by-side cards of 2–6 materials with value kind and source; search by name, alias or designation. **Bezeichnung entschlüsseln** decodes a designation (EN 573 / EN AW, EN 10027-1/-2, ISO 1043, UNS, AISI/SAE, …) into its parts, nominal composition and equivalents |
|  | Laminat | CLT: ABD, engineering constants, ply stresses through the thickness, max stress / Tsai–Hill / Tsai–Wu / Hashin, first-ply failure |
| Struktur & Gefüge | Struktur | any material of the shared database at a temperature: the views switch with T (the slider spends its travel on the transition ranges, marked on the track, and compresses stretches where nothing changes; arrow keys move by 1 °C, Shift by 10 °C). Metals: matrix lattice with solutes, unit cells of the precipitates and second phases, microstructure sketch; polymers: chain, crystal cell, amorphous coil or network, morphology; ceramics and glasses: unit cell with coordination polyhedra, glass network; composites, wood, paper, concrete as sketches with their constituents. *Wärmebehandlung*: steel quench and temper, Al/Mg/Ni ageing, recrystallisation, as a path T(t) with key frames and in-between frames to step through or play (cross-faded, speed 0.5–4×, ← →). Wood and paper react to heat (water loss, hemicellulose, cellulose, char, ash in air); a material with no transformation in the range says so in one line. Steels, Al–Cu alloys and cold-worked metals open on their microstructure; *Schliffbild* shows the sketches as an etched micrograph |
|  | Phasendiagramm | about 30 binary systems grouped by family (steels and irons incl. the stable Fe–C system, Fe–Cr, Fe–Ni; Al with Cu, Si, Mg, Mn, Zn, Fe; Cu with Zn, Sn, Ni, Ag; Mg, Ti and Ni alloys; solders; teaching systems; ceramics such as Al₂O₃–SiO₂ and ZrO₂–Y₂O₃), drawn as smooth boundary lines through cited key points (schematic between them, as each diagram's *Datengrundlage* fold says), or a computed ideal/regular-solution diagram; click sets the point; lever rule, constituents, cooling path, and a sketch of the microstructure at that point (with a link into the atlas) |
|  | Gitter | lattice section of a base element at a temperature: phase and a(T), dissolved atoms on interstitial or lattice sites in their true number, second phase above the solubility limit, equilibrium vacancies, Debye vibration, distortion; schematic edge dislocation, stacking fault and tilt grain boundary; views 3D (rotate, zoom), unit cell, atomic layer (hkl); optional labelled exaggeration of vacancies and vibration; examples (C45, austenite, Cu–Ni, Al–Si, Cu near Tm) |
|  | Kristall | cell, (hkl) plane and [uvw] direction in a rotatable cell; d, angles, X-ray density; computed powder pattern for a chosen tube |
|  | Stahl | CE (IIW), CET, Pcm, preheat (EN 1011-2), Ms, Ac1, Ac3, Hollomon–Jaffe, carburising profile and case depth |
| Prüfen & Auswerten | XRD | open a diffractogram (xy/CSV/TXT, `.xrdml`, `.brml`, `.raw` RAW1.01, `.uxd`, `.ras`); background, peaks, cubic indexing, lattice parameter (Nelson–Riley), Scherrer, Williamson–Hall, phase search against built-in and CIF phases, stick overlays, semi-quantification |
|  | Härte | HV/HB/HK from indents; conversion only with your own table file; E112 grain size; Hall–Petch |
|  | Ermüdung | S–N fit with run-outs and band, Haigh diagram, Marin factors, rainflow and Miner |
|  | Weibull | LSQ and MLE, bootstrap intervals, quantiles, size effect |
|  | Bruch | K_Q for SE(B) and C(T) with the E399 checks; critical crack size |
|  | Korrosion | Tafel lines and Butler–Volmer fit of a polarisation curve, Stern–Geary, corrosion rate (G102) |
|  | Kriechen | Larson–Miller and Norton–Arrhenius |

Synthetic example data, labelled as such, are loaded from the tool's compendium entry.

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
- **Info board → Zum Bericht …:** the whole board or one frame, one report section per frame in frame order (loose cards
  last). Text, figures and tables cite exactly the sources of their pins, per statement. Before the export, pins that
  rest on unchecked sources or have no source are listed, with the choice to leave them out; what stays carries † and a
  note saying what the mark means. The mark says nothing about a check having taken place: no mark means no check on
  record. The bundle stores the full pin records, so **Refresh** reproduces the report from the state at export.
- **Ergebnisse in den Projektindex …** and the environment overview share values with other modules.

## Data at a glance

| Data | Source |
|---|---|
| Material properties | shared database `sdk/python/labcalc/data/materials.json` (one value, one source; marked † where not checked) |
| Built-in crystal structures (38) | Wyckoff, *Crystal Structures* (1963) — `werk/data/phases.json` |
| Atomic form factors | Cromer–Mann coefficients, International Tables Vol. C, Table 6.1.1.4 (transcribed; see the methods page) |
| Phase-diagram key points | melting points, invariant reactions and maximum solubilities after the assessments named per system (Massalski *Binary Alloy Phase Diagrams*, ASM Handbook Vol. 3, the J. Phase Equilibria / Bull. Alloy Phase Diagrams evaluations, Callister & Rethwisch); lines in between traced schematically; values not checked against the originals are marked — `werk/data/diagrams.json` and `werk/data/diagrams/*.json` |
| Compendium | `werk/data/kompendium_text.json` (statements with id, DE, EN and citation keys), `werk/data/kompendium.json` (groups, examples), `werk/views.py` (view sources), `werk/gefuege.py` (mechanisms, atlas); material entries are generated from the cited material data |
| Property ranges | typical ranges per material and property (handbooks and datasheets named per range, not checked against the originals) — `sdk/python/labcalc/data/ranges.json` |
| Designation decoder | rules after EN 573-1/-3, EN 515, EN 10027-1/-2, EN 1412, EN 1706, ISO 1043-1/-2, UNS and AISI/SAE — `sdk/python/labcalc/designation.py` |
| X-ray tube wavelengths | standard values as used by instrument software (Bearden 1967) |
| Structure data of phases (25) | Crystallography Open Database (public domain), COD number per phase — `werk/data/structures.json`, built by `tools/build_structures.py` |
| Further cells (23), mostly polymer crystals and phases missing in the COD | literature named per phase, transcribed and marked † — `werk/data/structures_lit.json` |
| Microstructure sketches (29 constituents, 10 transformations, 12 mechanisms) | drawn after the textbooks and atlases named per entry (schematic, not checked against the originals) — `werk/gefuege.py`, `werk/data/gefuege_quellen.json` |
| Structure record per material (136) | nominal composition, temper, crystallinity, fibre and matrix, etc. after the sources named per entry, marked † — `werk/data/gefuege.json` |

No ICDD/PDF data and no hardness conversion tables are included.

## Tests

From `modules/werkstoffe`, with `sdk/python` on the Python path:

```
python -m unittest discover -s tests
```
