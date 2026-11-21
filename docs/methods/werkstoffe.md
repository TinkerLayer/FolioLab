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
- **Ashby chart:** any two properties on log axes; each material is drawn as a pale ellipse spanning its range in x
  and y, and each class as an outline around its members. Classes are coloured.
- **Ranges:** where a material has a single value, its range comes from the database entry; where it has none, from
  `labcalc/data/ranges.json` (typical ranges per material and property, each with its source; written from the
  handbooks and datasheets named there and not checked against the originals). A material known only by a range is
  placed at the geometric mean √(min·max) and labelled *nur Spanne* in the tooltip, card and report.
- **Selection card:** a click on a point selects the material instead of copying it anywhere. Its ellipse is outlined
  in green, and a card lists the main properties (value, range, unit, source), the decoded designation and buttons to
  compare, copy as tab-separated text, add to the report, or share every value or a single one through the shared
  overview (values `<tag>_<property>`).
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
- **Designation decoder** (`labcalc/designation.py`): splits a designation into its parts by the rules of the standard
  it follows and explains each: EN 573-1/-3 and EN 515 (EN AW-1050A H14, EN AW-AlMg3), EN 1706 (EN AC-…), EN 10027-1
  (S235JR, 42CrMo4, X5CrNi18-10, with alloy factors 4/10/100/1000 and the +QT/+N/+A suffixes), EN 10027-2 material
  numbers, EN 1412 (CW…), ISO 1043-1/-2 (PA6-GF30), UNS and AISI/SAE. Nominal composition ranges and equivalents are
  shown only where the rules or the database give them. Unknown parts are listed as unknown, never guessed. Some
  rarely used codes (EN 10027-2 groups 88/89, a few ISO 1043-2 letters) are written from memory and not checked
  against the current editions.
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

## 2b Material structure (`struktur.py`, `polymer.py`, `data/gefuege.json`, `data/structures*.json`)

Every material of the shared database (136, including all tensile-test materials) has a structure record in
`data/gefuege.json`: the type (metal, thermoplastic, elastomer, thermoset, crystal, glass, glass-ceramic, composite,
carbon fibre, wood, paper, concrete) and what the views need (nominal composition and temper of alloys, crystallinity
and Tg/Tm of polymers, network formers and modifiers of glasses, fibre, matrix and volume fraction of composites, …).
The values come from the standards and textbooks named per entry and are marked *nicht am Original geprüft*. For a
temperature `build(material, T)` returns views ("panels"), statements, the transitions in the range and the sources.
**The views are models or sketches, not micrographs;** unit cells are the only part taken directly from structure data.
The page tag, the figure tag and the report caption say which is which.

- **Structure data.** 25 phases from the Crystallography Open Database (Gražulis et al. 2012), converted by
  `tools/build_structures.py` (cell, symmetry operations, sites with occupancy; COD number and the publication of the
  entry are kept and cited). 23 further cells, mainly polymer crystals (PE, PP, PA6, PET, PTFE, POM, cellulose Iβ, …)
  and phases the COD lacks, transcribed from the literature (`structures_lit.json`); where the atom positions were not
  transcribed (`nur_zelle`) the cell is drawn with a labelled schematic filling.
- **Unit cells.** Sites expanded with the symmetry operations, duplicates merged (0,01 Å), images on faces, edges and
  corners added, plus anions bonded to a cation inside the cell (drawn faint). Bonds where
  d < 1,18·(r_c,i + r_c,j) with covalent radii after Cordero 2008 and at least one non-metal; coordination polyhedra
  for cations with 4 or 6 bonded anions (convex hull). Partly occupied sites are drawn dashed with their occupancy.
- **Metals.** Rules per alloy family turn composition, temper and T into phases:
  - **Steels and cast irons:** Ac1, Ac3 and Ms after Andrews 1965; below Ac1 ferrite + cementite (normalised) or
    martensite and its tempering stages (quenched and tempered); between Ac1 and Ac3 α + γ; above Ac3 austenite.
    Martensite c/a = 1 + 0,045·w_C (Roberts 1953) in a bct section with carbon on octahedral sites. Tempering stages
    from the Hollomon–Jaffe parameter P = T(C + lg t), converted to the equivalent 1 h temperature (Hollomon & Jaffe
    1945; stages after Speich & Leslie 1972 and Krauss 2015): < 100 °C as quenched, 100–200 °C ε-carbide, 200–300 °C
    retained austenite decomposes, 300–500 °C cementite in ferrite, above 500 °C spheroidised cementite. Austenitic
    stainless steels: γ, sensitisation (Cr₂₃C₆ on grain boundaries) between 450 and 850 °C. Grey and ductile iron:
    flake or spheroidal graphite in a pearlitic or ferritic matrix.
  - **Age-hardening Al alloys (2xxx, 6xxx, 7xxx):** solidus, solvus and the precipitation sequence per series after
    Polmear 2017 (GP zones → θ″/θ′ → θ; GP → β″ → β′ → β; GP → η′ → η; S in 2xxx with Mg ≥ 1 %). The state follows
    the time–temperature history converted to an equivalent time at the peak temperature with an Arrhenius factor,
    Q = 130 kJ/mol (diffusion of Mg/Si/Cu in Al, order of magnitude). Non-hardening alloys: Al₁₃Fe₄ particles (1xxx)
    or Al₆Mn dispersoids (3xxx) as their own cells; 5xxx as a Mg solid solution (β-Al₃Mg₂ is named in the statements
    but not drawn); cold-worked tempers with elongated grains and a recrystallisation mark at ≈ 300 °C.
  - **Cu, Ti, Mg, Ni:** Cu–Zn α/α+β, Cu–Sn; α-Ti, α + β of Ti-6Al-4V with the β fraction rising to the β transus
    (≈ 995 °C, Lütjering & Williams 2007); AZ alloys with β-Mg₁₇Al₁₂ below the solvus (Nayeb-Hashemi & Clark 1988);
    Ni alloys with γ′/γ″ and δ (Reed 2006). Pure metals use the allotropes of the lattice model (§2a); their
    statements name the phase, its lattice and the next transition above T.
  - The matrix lattice is the lattice model of §2a with the alloy's composition as the solubility limit, so the solutes
    shown are the dissolved ones and no extra precipitate is drawn in the lattice; precipitates appear as their own
    unit cells and in the sketch.
- **Polymers.** The chain is built from its repeat unit (`polymer.py`): backbone bond lengths C–C 1,54, C–O 1,43, C–N
  1,45, Si–O 1,64 Å; zigzag with 112° bond angle, or a helix whose radius follows from the fibre period (PE 2,55 Å,
  Bunn 1939; PP 3/1 6,50 Å, Natta 1960; PTFE 13/6 16,8 Å, POM 9/5 17,39 Å; PLA 10/3 28,8 Å); side groups in
  tetrahedral or trigonal directions; rings with their entry and exit bonds along the chain. H atoms are not shown.
  Tactic chains alternate or randomise the side. Crystal cell from the literature with chains of this geometry;
  amorphous regions as random coils (fixed bond length and angle, random torsion, reflected at the walls of the box;
  not self-avoiding) with the crystallinity of the record;
  elastomers and thermosets as networks with cross-links (S or C) at the density of the record. Above Tg the coil is
  labelled mobile, above Tm molten, above the decomposition temperature decomposed.
- **Ceramics and glasses.** Crystals as unit cells with polyhedra (corundum, SiC, Si₃N₄, MgO, diamond, Si, Ge, GaAs,
  β-Sn/α-Sn below 13 °C), switching by T where the record lists phases per temperature range. 3Y-TZP shows the
  tetragonal cell up to 2370 °C (stabilised by Y₂O₃) next to monoclinic ZrO₂ for comparison; the cubic phase above is
  named but has no cell. Glasses as a Zachariasen network
  (Zachariasen 1932): a distorted cristobalite-like SiO₄ network, bridging oxygens broken in proportion to the modifier
  content (non-bridging O per tetrahedron reported), modifier cations in the holes; above Tg labelled as a supercooled
  melt.
- **Carbon fibres and composites.** Turbostratic carbon (Oberlin 1984): graphene layers with random rotation and shift,
  spacing d₀₀₂, layer count from the stack height Lc and waviness from the degree of order given in the record. Composites as a sketch of the fibre arrangement (UD, fabric, short
  fibre) with the fibre volume fraction, plus the views of fibre and matrix (one level of nesting).
- **Wood, paper, concrete, glass-ceramics:** sketches only (cell walls with early- and latewood and the S2 microfibril
  angle; fibre network; aggregate in C-S-H paste with pores and, below ≈ 500 °C, portlandite, plus the cells of
  portlandite, CaO and calcite; crystals in residual glass).
- **Microstructure sketches** are drawn from a jittered hexagonal grain tessellation (seeded): lamellae and laths as
  hatching within a grain, particles as dots, needles along grain boundaries. They show the kind of microstructure,
  not its size; the scale bars on polymer and composite sketches are orders of magnitude.
- **Transitions and range.** The slider spans −196 °C (20 °C for glass, wood, paper and concrete) to 80 K above the
  highest transition; its marks are the transitions of the material (Ac1/Ac3, solvus, β transus, Tg, Tm,
  decomposition, …). Moving across a mark changes the views.
- **Heat treatment (`temper`).** A path of up to 8 steps (T from −50 to 1400 °C, hold 0 to 10 000 h, cooling in air or
  quenched). Presets: hardening at Ac3 + 40 K and tempering at 200, 400 or 600 °C for 1 h (steels with C ≥ 0,2 %);
  T4, T6 and T7 for age-hardening Al alloys at their solution and ageing temperatures; the two-step ageing of
  alloy 718; recrystallisation annealing of cold-worked metals. The time axis adds assumed ramps of
  max(0,1 h, ΔT/600 K·h⁻¹), i.e. 10 K/min and at least 6 min, and 0,02 h for a quench. A frame is computed at the end
  of each step and, for holds longer than 2 h, also after 10 % and 30 % of the hold.
  Each frame is a full set of views at that point of the history. Step names of the presets follow the report
  language; own names stay as entered.
- **In-between frames.** For steels (quench and temper), Al–Cu ageing and the recrystallisation of cold-worked Cu,
  brass and Al, six frames of the microstructure are inserted between two key frames. They sit where the change
  happens on the path: austenite forms above Ac1 and martensite below Ms. The martensite fraction follows
  Koistinen–Marburger, f = 1 − exp(−0,011 (Ms − T)), normalised to the end temperature. Tempering is shown above
  100 °C with a progress (T₁ − 80)/570 from the Hollomon–Jaffe equivalent 1-h temperature T₁. Precipitates dissolve
  above 300 °C. Ageing progress follows log(t_eq/t_peak), interpolated through 0,03 (supersaturated), 0,2 (GP
  zones), 0,6 (peak), 0,85 (over-aged) and 1 (equilibrium). Every frame of one path uses the same random geometry,
  and the player cross-fades between frames. In-between frames appear only in the page; the report shows the key
  frames.
- **Microstructure library (`gefuege.py`, `data/gefuege_quellen.json`).** It covers 29 constituents (ferrite,
  pearlite, ferrite–pearlite, cementite network, ledeburite, Widmanstätten ferrite, upper and lower bainite, lath and
  plate martensite, tempered martensite, spheroidite, austenite, δ-ferrite, duplex, flake and nodular cast iron, Al
  solid solution, GP zones, θ′, over-aged Al–Cu, Al–Si and Pb–Sn eutectics, dendrites, lamellar and bimodal Ti,
  α/β brass, cold-worked and recrystallised grains). Each comes with a fact sheet: description, how it forms,
  etchant, typical hardness and field of view. The library also has 10 transformations drawn at any progress
  0 … 1 and 12 animated mechanisms, including the Bain strain fcc → bct as a 3-D scene with c/a going from √2 to the
  Roberts value. The drawings follow textbooks and atlases (Krauss, Bhadeshia, Porter & Easterling, Humphreys &
  Hatherly, ASM Handbook Vol. 9 and others named per entry, not checked against the originals). They are schematic
  and not to scale. Steels, Al–Cu alloys and cold-worked metals open on these sketches at any temperature, so the
  temperature slider, the heat treatment and the atlas show the same picture.
- **Phase-diagram inset.** A clicked point in a phase diagram shows the microstructure after slow cooling to it
  (equilibrium), as follows:
  - Fe–C below A1: ferrite, ferrite–pearlite, pearlite, cementite network or ledeburite, by carbon content. Fe–C
    between A1 and A3: austenite growing into ferrite, at the lever-rule fraction.
  - Pb–Sn and Al–Si below the eutectic: their eutectic sketch.
  - Al–Cu (Al) + θ, α/β brass, α + β titanium: their constituent sketch.
  - Fields with liquid: dendrites at the solid fraction.
  - Any other single phase: grains of that phase.
  - Any other two-phase field: no sketch.
- **Etched view.** Optionally the sketches are shown as a micrograph: greyscale, film grain, a slight blur and
  vignetting. Only the rendering changes; the drawing stays schematic.
- **Cellulose on heating (wood, paper).** Five marks on the temperature axis, for heating without air unless stated:
  - 100 °C: bound water evaporates and the walls shrink. Wood holds about 12 % moisture at 20 °C and 65 % relative
    humidity (Wood Handbook, FPL-GTR-190, 2010†).
  - No melting: cellulose decomposes before it melts (Shafizadeh, *J. Anal. Appl. Pyrolysis* 3 (1982) 283–305,
    doi:10.1016/0165-2370(82)80017-X†).
  - 220–315 °C: hemicellulose decomposes; 315–400 °C: cellulose decomposes; lignin decomposes slowly over a wide range
    (Yang et al., *Fuel* 86 (2007) 1781–1788, doi:10.1016/j.fuel.2006.12.013; the two ranges were checked against the
    abstract, the rest is marked †).
  - The first step of cellulose pyrolysis is depolymerisation to levoglucosan; char forms from the polymerisation of
    the products (Lin et al., *J. Phys. Chem. C* 113 (2009) 20097–20107, doi:10.1021/jp906702p; checked against excerpts of the article). Above 400 °C the view
    shows char, without chain and crystal cell.
  - 525 °C, in air: ash, the inorganic residue (ISO 1762:2019†). For paper mainly the filler, for wood below 1 %
    (Wood Handbook†).

  The darkening of the sketch runs linearly from 220 to 400 °C. It is schematic and not a measured quantity. † means
  *Angaben nicht am Original geprüft*.
- **Materials without a transformation.** If no transition lies inside the slider's range, the result carries
  `no_change: true` and one line says that the structure stays as shown (for example SiC, Si₃N₄, diamond). Glasses and
  the glass-ceramic mark their network as frozen or as a supercooled liquid at Tg.
- Limits: rules per alloy family, not a thermodynamic calculation (no CALPHAD); no nucleation or growth kinetics, no
  amount of retained austenite, no segregation; the equivalent-time conversion uses one activation energy for all
  Al alloys; polymer conformations in the coil are random, not equilibrated; glass networks are topological sketches
  (no real Si–O–Si angle distribution). Three to seven cells per edge in the lattice view.
- Tests (`StrukturTest.*`):
  - every material of the shared database has a structure record; all 136 build at 20 °C with at least one
    statement, known references and below 400 kB;
  - C45E +QT ferrite at 20 °C and austenite at 850 °C; EN AW-6061-T6 with the β″ cell at 20 °C and without it at
    560 °C; PE-HD molten at 200 °C;
  - all 28 polymer chains: bonded distances 1,1–1,9 Å, non-bonded distances (beyond 1–3 neighbours) above 2,05 Å;
    repeat lengths of PE (2,55 Å), PP (6,50/3 Å), PTFE (16,8/13 Å) and POM (17,39/9 Å);
  - steel path: martensite after quenching, 3rd tempering stage after 1 h at 400 °C, monotonic time axis, at most 8
    steps; Al path: supersaturated solid solution after quenching and peak ageing for T6; no presets for PE;
  - step names translated, own names kept; sketches compact (hatching instead of single lines); report figures for
    scenes, sketches, the path and the frame grid render.
- Tests (`StructureOverTemperature.*`): a temperature sweep over every material either changes the result or sets
  `no_change`; wood and paper show six distinct states with cited transitions.

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

- **Schematic diagrams:** about 30 binary systems in `data/diagrams.json` and `data/diagrams/*.json`, grouped by
  family: steels and irons (Fe–Fe₃C metastable, Fe–C stable, Fe–Cr, Fe–Ni), aluminium (Al with Cu, Si, Mg, Mn, Zn,
  Fe), copper (Cu–Zn, Cu–Sn, Cu–Ni, Cu–Ag), magnesium, titanium and nickel alloys, solders, teaching systems and
  ceramics (e.g. Al₂O₃–SiO₂, ZrO₂–Y₂O₃, MgO–Al₂O₃). Melting points, invariant reactions and maximum solubilities are
  taken from the assessments named per system (Massalski 1990, ASM Handbook Vol. 3, the J. Phase Equilibria and Bull.
  Alloy Phase Diagrams evaluations, Callister & Rethwisch). Each boundary is a named curve through those points,
  smoothed by a Catmull–Rom spline; the regions are built from the curves, so lines and regions always agree. Lines
  between the cited points are traced, not measured: every figure and text says *schematisch*, and the fold
  *Datengrundlage dieses Diagramms* names what is cited and what is simplified (e.g. ζ in Cu–Sn left out, FeNi₃
  ordering as one dome).
- **Phases outside the plotted range:** where a partner phase lies beyond the axis (graphite at 100 % C in the stable
  Fe–C system, the liquid near 43 % Sn at 676 °C in Cu–Sn), the region carries the true composition where it is
  known; otherwise the lever rule uses the axis end and the diagram's note says so.
- **Lever rule:** W_left = (x_r − x₀)/(x_r − x_l) on the horizontal tie line through the chosen point; constituents
  below an eutectic or eutectoid (e.g. proeutectoid ferrite and pearlite); a cooling path with the fraction of every
  phase against T.
- **Computed diagrams:** G_S = RT[x ln x + (1−x)ln(1−x)] + Ω_S x(1−x), G_L = (1−x)ΔH_A(1 − T/T_A) + xΔH_B(1 − T/T_B)
  + RT[…] + Ω_L x(1−x) (Porter & Easterling, ch. 1; ΔC_p neglected); stable phases from the lower convex hull of both
  curves. Ideal solution: Ω = 0. The Cu–Ni preset (T_m, ΔH_m from the shared data) deviates from the assessed
  diagram by up to about 25 K; it is labelled *berechnet (Lösungsmodell)*.
- Tests (`PhaseTest.*`):
  - Fe–C 0,35 % C just below 727 °C: proeutectoid ferrite (0,76 − 0,35)/(0,76 − 0,022) = 0,556, pearlite 0,444;
  - Pb–Sn 40 wt% Sn at 150 °C: α fraction 0,67 (Callister's worked example; ±0,02 for the traced solvus);
  - every system validates (closed regions, curves inside the box), and in every two-phase region the lever rule at
    an inner point gives two fractions that sum to 1 (`test_runde_mt.DiagramCoverage`);
  - Al–Mn 3 wt% at 500 °C uses the stoichiometric Al₆Mn (25,3 wt% Mn) as the partner phase;
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

## 11a Measurement uncertainty (`tools.py`, shared `labcalc/uncertainty.py`)

The calculation is the suite's ([uncertainty.md](uncertainty.md)); this module supplies the models and inputs. The
model is always the module's own function, so the budget follows the same formula as the result.

| Result | Model | Inputs with ± |
|---|---|---|
| K_Q (E399) | `reliability.k_q` for the chosen geometry | P_Q, B, W, a, S (SE(B)) |
| critical crack length a_c | (K_Ic/(Y σ))²/π · 1000 mm | K_Ic, σ, Y |
| hardness mean | H̄ · (F/F̄)(d̄/d)² (HV, HK); for HBW the Brinell ratio with the ball diameter | H̄ from the indents (type A, n − 1 degrees of freedom, from two indents on), F, d |
| CE, CET, Pcm, Ms, Ac1, Ac3 | `steel.formulas` | every element |
| preheat temperature T_p (EN 1011-2) | `steel.preheat_tp` with CET from the composition | elements, thickness, HD, heat input |

The hardness model separates the scatter of the indents (in H̄) from a systematic error of the force or the length
measurement, which acts on every indent alike. A result that depends on no uncertain input (for example Ac1 when only
C has an uncertainty) is not shown and not reported. The uncertainty of the empirical formulas themselves (CE, Ms,
Ac1, Ac3, T_p) is not included; the budget covers the inputs only.

Tests (`UncertaintyViewsTest.*`): the K_Q value equals the result without uncertainty, its budget lists exactly the
inputs given, all four methods are compared; three indents give type A with ν = 2; Ac1 is dropped when only C is
uncertain; the report has `bruch-kq-budget` and cites JCGM 100.

## 11b What a view shows (`views.py`, `kompendium.py`, `finder.py`)

Each view of each tool has a one-line description, an explanation and the reference keys that view relies on
(`views.V`, `views.S_CAT` for the structure panels). A tool result carries only the keys and the id of the matching
compendium entry (`views_info[view] = {keys, entry}`). The page lists that view's sources first, and report figures of
a view cite those keys.

**Compendium** (`kompendium.py`, `data/kompendium.json`, route `kompendium`). Entries: `tool:<tool>` with one section
per view (`tool:<tool>#<view>`), usage notes and example data; `mech:<id>` (mechanism animations); `atlas:<id>`
(constituents with fact sheet and sketch); `topic:<id>` (cellulose on heating, designations, uncertainty). Every entry
has reference keys that resolve in `refs.py` and are written out in full. Mechanisms and atlas entries can still be
sent to a report.

**Search** (`finder.py`, route `finden`). The index holds tools, views and modes, materials of the shared database
(name, English name, aliases, id, family), phase diagrams, crystal phases and the full text of the compendium. Text is
compared in lower case without diacritics (ä = ae, ß = ss). Rank: exact title, title prefix, all words at a word start
in the title, word match elsewhere, then a compact substring without spaces and hyphens (`x5crni` finds `X5CrNi18-10`).

**Input checks** (`tools.run`). NaN or infinity anywhere in a request, empty fields where a number is required, text
in a number field and values outside a formula's domain return a clear input error (HTTP 400) and no longer an internal
error. Tests (`ToolAudit.*`): every numeric input of every tool changes the result; empty and edge values neither crash
nor hang. Tests (`Search.*`, `Compendium.*`): every tool, material and entry is findable; every former view text is in
the compendium; every entry has resolving sources.

The structure tool's temperature slider maps positions 0–1000 piecewise linearly onto T. Around every transition
temperature of the material (Ac1, Ac3, solvus, Tg, Tm, decomposition …) lies a zone of ± max(8 K, 3 % of the range);
zones closer than 12 % of the range merge. The stretches between zones, where no view changes, share 20 % of the
travel (at least 3 % each); the zones share the rest in proportion to their width and are shaded on the track. The
arrow keys still move T by exactly 1 °C (10 °C with Shift).

## 12 Report (`bundle.py`)

Uncertainty results add the values `<tool>-<name>-pm`, `-U`, `-u`, a budget table `<tool>-<name>-budget` and one
methods sentence per method (see [uncertainty.md](uncertainty.md)).

The structure tool writes one figure per view (the view shown on the page first), a table of the phases with their
cells and data source, and for a heat treatment the T(t) path, a grid of the frames in one view, the steps and the
state of each frame; the captions say model, sketch or unit cell from structure data.

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
- Structure tool: phases from rules per alloy family, not from a thermodynamic calculation; frames of a heat treatment
  without kinetics of nucleation and growth (in-between frames interpolate the progress, except martensite after
  Koistinen–Marburger); sketches not to scale; literature cells not checked against the original. The ageing
  sequence of the library is that of Al–Cu, so 6xxx and 7xxx alloys get no in-between frames.
- Cellulose: one fixed set of temperature marks. Real decomposition ranges shift with heating rate, atmosphere and
  composition, and the view does not model mass loss or char yield.
- Phase diagrams: where a partner phase lies beyond the plotted axis and no true composition is stored (the liquid
  near 43 % Sn at 676 °C in Cu–Sn), the lever rule uses the axis end. ζ in Cu–Sn, the FeNi₃ two-phase fields, Ni₂Cr
  ordering and the Cu–Ni miscibility gap are not drawn. Ti–V, the Ag–Pt peritectic, the ZrO₂–Y₂O₃ eutectoid, the
  MgO–Al₂O₃ eutectic compositions, the Ni–Cr eutectic and the maximum solubility in Al–Mg are uncertain and want
  checking against the assessments.
- Property ranges and the designation decoder were written from the handbooks and standards named, without
  comparing them to the originals.
- Lattice model: a(T) with a constant α away from tabulated points; solubility only where a diagram, a miscible pair or
  an own limit exists (otherwise drawn fully dissolved, with a note); defects, precipitate shape and position are
  schematic; no short-range order, clustering or segregation to defects.
