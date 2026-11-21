# Methods and validation

One page per module. Each page describes every computed quantity, with:

- the algorithm and formulas;
- the defaults and limits;
- the references, as cited in the code and in the generated report;
- the tests that check it, with their expected values;
- the known limitations.

The pages describe the code as it is. Where the code and a cited source differ, or a value has not been checked, the
page says so.

| Module | Page | What it covers |
|---|---|---|
| Datenaufbereitung (data preparation) | [datenaufbereitung.md](datenaufbereitung.md) | reading tables, units, cleaning steps, outlier tests, smoothing, datasets and versions |
| Provenance (all modules) | [provenance.md](provenance.md) | how a number in a report is traced to its raw file: dataset versions, hashes, report revisions, what to state in a methods section |
| Measurement uncertainty (all modules) | [uncertainty.md](uncertainty.md) | input contributions, instrument library, GUM linear, Monte Carlo (GUM S1), Gaussian propagation, worst case, rounding, report output |
| Rechner (calculator) | [rechner.md](rechner.md) | expression evaluation, units, constants, equation library, solver, fits, graphs |
| Elementrechner (element calculator) | [elementrechner.md](elementrechner.md) | formulas and balancing, thermochemistry, equilibria, acid–base, speciation, redox, nuclear chemistry, kinetics; data sets used |
| FTIR | [ftir.md](ftir.md) | readers, processing, bands and areas, assignments, library search, mixtures |
| TGA | [tga.md](tga.md) | readers, steps and onsets, composition, library search, kinetics, DSC |
| Werkstoffe (materials) | [werkstoffe.md](werkstoffe.md) | materials selection, crystallography, XRD readers and evaluation, phase diagrams, steel, laminates, fatigue, Weibull and fracture, hardness, corrosion, creep |
| Mikroskopie (microscopy) | [mikroskopie.md](mikroskopie.md) | calibration, processing, thresholds, particle analysis, measurements |
| Zugversuch (tensile test) | [zugversuch.md](zugversuch.md) | `.flps` reader, preparation, fit window, key values, comparison with reference materials |

See also:

- [VALIDATION.md](../VALIDATION.md): how the software is tested overall, and what the tests do not cover.
- [THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md): every data source with its licence.
