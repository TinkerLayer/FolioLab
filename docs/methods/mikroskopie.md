# Mikroskopie (microscopy): methods and validation

This file describes what the Mikroskopie module computes, how, with which defaults and limits, which references the
code cites and which tests check it. Code paths are relative to `modules/mikroskopie/`. User guide:
[modules/mikroskopie/README.md](../../modules/mikroskopie/README.md).

## How to cite results from this module

State the Folio Lab version (`version` in `package.json`) and the module version (`version` in
`modules/mikroskopie/module.json`, currently 1.2.0). When a result is sent to a report, Folio Lab writes
`lab/<result>/bundle.json` in the project. Its `provenance` block records the Folio Lab version, the module id, the module version
and the SHA-256 of every source file stored with the result. "Source files" are the input images kept for *Refresh*, not the
program code. Also state the processing protocol
(every step with its parameters), the threshold method and the particle filters; the report's methods text and
`protokoll.txt` list them. Cite the threshold method with the reference given in section 4.

## 1. Images and calibration

### 1.1 Reading files (`mikro/imageio.py`)

TIFF, PNG, JPEG, BMP and GIF are read with Pillow, up to 2000 frames per file.

| Pillow mode | Treated as |
|---|---|
| `I;16` | 16-bit grey |
| `I` | 16-bit or 32-bit grey, depending on the value range |
| `F` | 32-bit float grey |
| `1`, `L` | 8-bit grey |
| `P`, `RGB` | grey if all channels are equal, else RGB |

### 1.2 Calibration

- **From the file.** A calibration is read only if the TIFF ImageDescription contains a line `unit=` (as written by
  ImageJ) and XResolution is present. Pixel width = 1/XResolution, pixel height = 1/YResolution. The TIFF
  ResolutionUnit tag is ignored, so a TIFF with resolution but without such a description loads uncalibrated.
- **From a line** (`mikro/static/index.html`). Pixel size = known length / line length in pixels. The line length
  is rounded to 2 decimals. Pixels are taken as square.
- **Direct entry.** µm/px, or px/µm (the reciprocal is used). Pixels are square.
- Changing the scale discards existing particle results. Presets are stored in the browser.
- **Sample image.** A synthetic 16-bit image, 768 × 576 px, 0.25 µm/px, with 70 ellipses (semi-axes 4 to 16 px),
  random seed 7. It is used by tests and by *Beispielbild laden*.

## 2. Processing steps (`mikro/ops.py`)

Every step goes into the protocol and is re-applied to the original image for measurement, export and report.

| Step | Algorithm | Default (range) |
|---|---|---|
| Grey | unweighted mean of R, G, B, or weighted 0.299·R + 0.587·G + 0.114·B | – |
| Channel | R, G or B | – |
| To 8 bit | linear map of min..max (or a given range) to 0..255 | – |
| Invert | max − v (32-bit: min + max − v) | – |
| Contrast | percentile stretch to 0..max (0..1 for 32-bit), saturated fraction split equally at both ends | 0.35 % (0–20) |
| Smooth | 3 × 3 box mean | – |
| Sharpen | 3 × 3 kernel: −1 at the 8 neighbours, 12 at the centre, divided by 4 | – |
| Edges | Sobel gradient magnitude | – |
| Gaussian blur | separable, radius ⌈3σ⌉, edge padding | σ = 2 px (0.1–100) |
| Median | square window (2r+1)² | r = 2 (1–10) |
| Mean | square window (2r+1)² | r = 2 (1–50) |
| Minimum, maximum | square window (2r+1)² | r = 1 (1–50) |
| Unsharp mask | (a − w·G_σ(a)) / (1 − w) | σ = 1, w = 0.6 (0.1–0.9) |
| Subtract background | see below | r = 50 px (2–1000), light background option |
| Math | add, multiply, ln(max(v, 0) + 1), square root, gamma (v/top)^γ·top, absolute value; log and root give 32-bit | – |
| Crop, rotate 90°, flip | rotation swaps pixel width and height | – |
| Z projection | max, mean, sum, SD, min, median | – |
| Threshold | section 3 | – |
| Erode, dilate | n passes with a 3 × 3 square element (8-neighbourhood), edge replicated | n = 1 (1–50) |
| Open, close | erode then dilate / dilate then erode | – |
| Fill holes | background not 4-connected to the image border becomes foreground | – |
| Watershed | section 5 | h = 1.0 px (0.1–50) |
| Outline | x and not erode(x) | – |

**Subtract background.** With s = max(1, ⌊r/10⌋): the image is reduced by taking the minimum over s × s blocks; a
grey opening (minimum filter then maximum filter, square window of radius max(1, round(r/s))) gives the background;
it is enlarged bilinearly to the full size and smoothed with a box mean of radius max(1, ⌊s/2⌋).
Result = max(b − min(bg, b), 0). For a light background the image is inverted (max − b) before and after. This
approximates a rolling-ball background but is not the rolling-ball algorithm.

## 3. Threshold (`mikro/threshold.py`)

### 3.1 Histogram and range

- 8-bit images: 256 bins of width 1 at the integer grey values.
- 16-bit and 32-bit images: 256 equal bins between the image minimum and maximum, width w = (max − min)/256.
- Each method returns a bin index k, the last bin of the lower class. The threshold value is t = min + (k + 1)·w.
- Objects on a dark background (`dark`): the range is [t, v_max]. Objects on a light background: [v_min, t − 1]
  for 8-bit, [v_min, t − 10⁻⁶·w] otherwise. For 8-bit, v_min and v_max are widened to 0 and 255.
- A pixel is foreground if lo ≤ v ≤ hi. A threshold can be applied per slice or on the whole stack. The grey image
  before the first threshold is kept for intensity measurements.

### 3.2 Methods

| Key | Shown as | Algorithm as implemented | Reference key |
|---|---|---|---|
| `default` | Default (IsoData-Variante) | Bins 0 and 255 are set to 0. Starting at the first occupied bin, the split moves up one bin at a time; result = mean of the two class means; stops when split + 1 > result | ridler1978 |
| `isodata` | IsoData | Start at the rounded mean; t = round((m₁ + m₂)/2) until stable, at most 1000 iterations | ridler1978 |
| `otsu` | Otsu | maximises the between-class variance (μ_T·ω₀ − μ)² / (ω₀(1 − ω₀)) | otsu1979 |
| `triangle` | Dreieck (Triangle) | line from the histogram peak to one bin beyond the end of the longer tail; bin with the largest perpendicular distance, minus one bin | zack1977 |
| `li` | Li | minimum cross entropy, iterated from the mean: t = (μ_b − μ_o)/(ln μ_b − ln μ_o), until the change is ≤ 0.5 | li1993 |
| `huang` | Huang | minimises fuzziness entropy with membership 1/(1 + \|i − m\|/C), C = last − first occupied bin | huang1995 |
| `maxentropy` | Maximale Entropie | maximises the sum of the entropies of both classes | kapur1985 |
| `yen` | Yen | argmax of −ln(P1sq·P2sq) + 2·ln(P1·(1 − P1)) | yen1995 |
| `moments` | Momente | preserves the first three moments; threshold at the first bin where the cumulative fraction exceeds p₀ | tsai1985 |
| `mean` | Mittelwert | floor of the mean grey value | glasbey1993 |
| `minimum` | Minimum | 3-point smoothing until exactly two peaks remain (at most 10 000 passes, else falls back to `default`); first local minimum | prewitt1966 |
| `intermodes` | Intermodes | same smoothing; floor of the mean of the two peaks | prewitt1966 |
| `percentile` | Perzentil (50 %) | bin where the cumulative fraction is closest to 0.5 | doyle1962 |

The implementations are the module's own. Details such as zeroing bins 0 and 255 in `default`, the extra bin in
`triangle` and the 0.5 stop in `li` are implementation choices; the code does not state which reference
implementation they follow. No method is compared with another implementation in the tests (section 8).

## 4. References as cited in the code

The code (`mikro/threshold.py`, `mikro/watershed.py`) states that the entries with a DOI were checked against Crossref
on 17.11.2026 (authors, year, volume, issue, pages). Two entries have no DOI and are marked as not verified in the code
(`UNVERIFIED`); they are listed here exactly as in the code.

| Key | Reference | DOI |
|---|---|---|
| ridler1978 | Ridler, T. W. and Calvard, S. Picture thresholding using an iterative selection method. IEEE Transactions on Systems, Man, and Cybernetics 8(8):630–632, 1978. | 10.1109/TSMC.1978.4310039 |
| otsu1979 | Otsu, Nobuyuki. A threshold selection method from gray-level histograms. IEEE Transactions on Systems, Man, and Cybernetics 9(1):62–66, 1979. | 10.1109/TSMC.1979.4310076 |
| zack1977 | Zack, G. W. and Rogers, W. E. and Latt, S. A. Automatic measurement of sister chromatid exchange frequency. Journal of Histochemistry and Cytochemistry 25(7):741–753, 1977. | 10.1177/25.7.70454 |
| li1993 | Li, C. H. and Lee, C. K. Minimum cross entropy thresholding. Pattern Recognition 26(4):617–625, 1993. | 10.1016/0031-3203(93)90115-D |
| huang1995 | Huang, Liang-Kai and Wang, Mao-Jiun J. Image thresholding by minimizing the measures of fuzziness. Pattern Recognition 28(1):41–51, 1995. | 10.1016/0031-3203(94)E0043-K |
| kapur1985 | Kapur, J. N. and Sahoo, P. K. and Wong, A. K. C. A new method for gray-level picture thresholding using the entropy of the histogram. Computer Vision, Graphics, and Image Processing 29(3):273–285, 1985. | 10.1016/0734-189X(85)90125-2 |
| yen1995 | Yen, Jui-Cheng and Chang, Fu-Juay and Chang, Shyang. A new criterion for automatic multilevel thresholding. IEEE Transactions on Image Processing 4(3):370–378, 1995. | 10.1109/83.366472 |
| tsai1985 | Tsai, Wen-Hsiang. Moment-preserving thresholding: a new approach. Computer Vision, Graphics, and Image Processing 29(3):377–393, 1985. **Not verified (no DOI in the code).** | – |
| glasbey1993 | Glasbey, C. A. An analysis of histogram-based thresholding algorithms. CVGIP: Graphical Models and Image Processing 55(6):532–537, 1993. | 10.1006/cgip.1993.1040 |
| prewitt1966 | Prewitt, Judith M. S. and Mendelsohn, Mortimer L. The analysis of cell images. Annals of the New York Academy of Sciences 128(3):1035–1053, 1966. **Not verified (no DOI in the code).** | – |
| doyle1962 | Doyle, Worthie. Operations useful for similarity-invariant pattern recognition. Journal of the ACM 9(2):259–267, 1962. | 10.1145/321119.321123 |
| vincent1991 | Vincent, Luc and Soille, Pierre. Watersheds in digital spaces: an efficient algorithm based on immersion simulations. IEEE Transactions on Pattern Analysis and Machine Intelligence 13(6):583–598, 1991. | 10.1109/34.87344 |
| soille2003 | Soille, Pierre. Morphological Image Analysis: Principles and Applications. 2nd edition. Springer, Berlin, 2004. (The key and the code comments say 2003; the entry says 2004.) | 10.1007/978-3-662-05088-0 |
| saito1994 | Saito, Toyofumi and Toriwaki, Jun-Ichiro. New algorithms for euclidean distance transformation of an n-dimensional digitized picture with applications. Pattern Recognition 27(11):1551–1565, 1994. | 10.1016/0031-3203(94)90133-3 |

The report's methods text cites `tsai1985` and `prewitt1966` like the others, without a note that they are not
verified. Check them before publication if you use Moments, Minimum or Intermodes.

## 5. Watershed (`mikro/watershed.py`)

Separates touching particles in a binary mask. It needs a binary image.

1. **Distance transform.** Exact Euclidean distance to the nearest background pixel, computed separably: distance
   along the row, then the minimum over row offsets (after Saito & Toriwaki 1994). Pixels outside the image count as
   background.
2. **Markers.** Regional maxima of the h-maxima transform: morphological reconstruction by dilation of D − h under D,
   8-neighbourhood, tolerance 10⁻³ (after Soille). Maxima less than h pixels above their saddle merge. Default
   h = 1.0 px.
3. **Flooding.** The distance map is flooded from the markers in levels of 0.5 px, from ⌊max/0.5⌋·0.5 down to 0.5
   (immersion after Vincent & Soille 1991). A pixel joins a basin if all its labelled neighbours carry the same label;
   otherwise it becomes a boundary pixel. Afterwards, of two 8-neighbours with different labels, the one with the
   higher label also becomes boundary, so that the lines separate in 8-connectivity.
4. **Result.** The mask minus the boundary pixels (1-pixel lines), as in ImageJ's "Watershed" command.

## 6. Measurement (`mikro/measure.py`, `mikro/label.py`)

### 6.1 Selections (ROIs)

| Quantity | Definition |
|---|---|
| Membership | a pixel belongs to a selection if its centre lies inside |
| Area | pixels × pixel width × pixel height |
| Mean, StdDev, Min, Max, Median | of the pixel values; StdDev with n − 1 |
| Mode | most frequent rounded value |
| IntDen, RawIntDen | Area·Mean; sum of pixel values |
| Perimeter | geometric: rectangle 2(w + h); ellipse by Ramanujan's approximation; polygon as closed path length; whole image 2(W·pw + H·ph) |
| Circularity | min(1, 4π·Area/Perimeter²) |
| Line | sampled at round(L) + 1 points, bilinear interpolation; a width > 1 averages parallel lines. Length uses pixel width and height; angle = atan2(−dy, dx) in degrees |
| Point | pixel value |

If the image is binary and a grey image before the threshold exists, intensities are taken from that grey image.

### 6.2 Particle analysis

Connected components are labelled with a run-based union-find in 8-connectivity. Filters and defaults:

| Parameter | Default | Rule |
|---|---|---|
| Size | 0 to ∞ | in calibrated area units, or pixels if "size in pixels" is set |
| Circularity | 0 to 1 | applied after the size filter |
| Exclude edge particles | on | a particle is dropped if its bounding box touches the image border (not the border of a selection) |
| Include holes | off | if on, holes (background not 4-connected to the border) are filled before labelling |
| Region | none | an area selection masks the image; its area is the denominator of the area fraction |

Per particle (pw, ph = pixel width and height):

| Quantity | Definition |
|---|---|
| Area | pixels × pw × ph |
| Perimeter | marching squares through the pixel centres. Per 2 × 2 cell: 1 or 3 foreground pixels add √0.5; 2 adjacent pixels add 1; 2 diagonal pixels add 2·√0.5. Multiplied by pw. Inner boundaries of holes are included. |
| Circularity | min(1, 4π·Area/Perimeter²) |
| ECD | 2·√(Area/π) |
| Major, Minor, Angle | second central moments of the pixel centres, each plus 1/12 (pixel extent); Major = 4√λ₁, Minor = 4√λ₂, scaled so that π·Major·Minor/4 equals the pixel area, multiplied by pw. Angle = ½·atan2(−2μ₁₁, μ₂₀ − μ₀₂), modulo 180° |
| AR | Major/Minor |
| Roundness | 4·Area/(π·Major²) |
| Convex hull | monotone chain over the corners of the boundary pixels, scaled by pw and ph |
| Feret, FeretAngle | largest distance between two hull vertices, and its angle |
| MinFeret | smallest width of the hull over the normals of its edges |
| Solidity | min(1, Area/hull area) |
| Mean, StdDev, Min, Max, IntDen | of the grey values in the particle; StdDev with n − 1; IntDen = Area·Mean |

Summary: Count, TotalArea, AverageSize (mean area), SDSize (n − 1), AreaFraction = 100·Σ Area / region area (whole
image without a region), mean and SD of Perimeter, Circularity, ECD, Feret, MinFeret, AR, Solidity and Mean.
**D10, D50, D90** are the 10th, 50th and 90th percentiles of the ECD values (`numpy.percentile`, linear
interpolation). They are **number-based**: every particle counts once, whatever its size.

### 6.3 Behaviour on ideal digital discs

The following values were obtained with module version 1.2.0 on ideal digital discs (pixels whose centres lie within
radius r), pixel size 1. They are not part of the test suite; they show the size of the discretisation effects.

| r (px) | Circularity | Perimeter / 2πr | ECD / 2r | Feret / 2r | MinFeret / 2r | Solidity |
|---|---|---|---|---|---|---|
| 3 | 0.958 | 1.087 | 1.064 | 1.202 | 1.000 | 0.941 |
| 5 | 0.862 | 1.087 | 1.009 | 1.131 | 1.000 | 0.909 |
| 10 | 0.882 | 1.068 | 1.003 | 1.063 | 1.000 | 0.946 |
| 20 | 0.897 | 1.059 | 1.003 | 1.031 | 1.000 | 0.965 |
| 50 | 0.902 | 1.053 | 1.000 | 1.012 | 1.000 | 0.984 |
| 100 | 0.899 | 1.055 | 1.000 | 1.007 | 1.000 | 0.991 |

A 40 × 20 px rectangle gives Area 800, Perimeter 118.8 (true 120), Circularity 0.712, Feret 44.72, MinFeret 20,
AR 2.0, Solidity 1.0. Feret and Solidity use the hull of the pixel corners, so they describe the outer pixel edges;
the perimeter runs through the pixel centres. A circularity of 1 is not reached by digital discs; small particles
(r ≤ 5 px) have a strongly biased Feret and solidity.

## 7. Comparison distribution from a dataset (`mikro/compare.py`, `mikro/charts.py`)

- A column counts as a length if its unit is a length unit. Values must be finite and > 0; rows flagged as excluded
  in the dataset are dropped. 3 to 50 000 values. Values are stored in metres with 6 significant digits.
- A calibrated image is required; in pixels the comparison is refused.
- Statistics of both distributions: n, D10, D50, D90 (`numpy.percentile`, linear interpolation), mean, SD (n − 1).
  Ratio = D50 of the particles / D50 of the dataset.
- Chart: common linear bins over the joint range, number of bins = max(6, min(40, 2·⌊√(min(n_a, n_b))⌋)); relative
  frequency in %; dashed lines at both D50.

Both distributions are treated as number-based. Laser diffraction instruments usually report volume-weighted
distributions; the module does not convert between the two.

## 8. Validation

Run `python -m unittest discover -s tests` in `modules/mikroskopie`. The suite has 33 tests and needs no unpublished
data.

| Test | Expected |
|---|---|
| `tests/test_mikro.py::LabelTest::test_against_flood_fill` | on random 40 × 50 masks, 4- and 8-connected labelling gives the same component count as a flood fill, labels 1..n, background 0 |
| `tests/test_mikro.py::LabelTest::test_fill_holes` | an enclosed hole is filled; background touching the border stays |
| `tests/test_mikro.py::ThresholdTest::test_bimodal` | 8-bit mixture N(60, 8) × 20 000 + N(180, 8) × 8000: `default`, `isodata`, `otsu`, `li`, `huang`, `intermodes`, `minimum`, `mean`, `moments` give 80 ≤ t ≤ 170 with upper limit 255; Otsu on a light background gives lower limit 0 and upper limit < 180 |
| `tests/test_mikro.py::ThresholdTest::test_all_methods_run_on_16bit` | all 13 methods return a value within the data range of the 16-bit sample image |
| `tests/test_mikro.py::OpsTest::test_every_op_keeps_shape` | every step with its defaults keeps the image size (crop and rotation as expected) and gives finite values |
| `tests/test_mikro.py::OpsTest::test_rgb_ops`, `::test_errors_are_german_and_name_the_step` | channel and grey conversion; error messages name the step |
| `tests/test_mikro.py::OpsTest::test_background_flattens` | ramp 50 + 0.5·x plus a disc of +200, radius 20: background SD < 3, disc centre > 150 |
| `tests/test_mikro.py::MeasureTest::test_disk_and_rect` | at 0.5 µm/px: disc r = 20 px has Area π·100 ± 6 µm², ECD 20 ± 0.3 µm, circularity > 0.85; rectangle 80 × 40 px has Area 800 ± 0.01 µm², Feret hypot(39.5, 19.5) ± 1 µm, AR 2 ± 0.1 |
| `tests/test_mikro.py::MeasureTest::test_edges_size_and_circularity_filters` | counts 2 (edges excluded), 3 (edges kept), 1 (circularity ≥ 0.6), 1 (size ≥ 250 px) |
| `tests/test_mikro.py::MeasureTest::test_roi_measure` | rectangle: 200 px, 800 µm², mean 100; line: length 60 µm, angle 0; ellipse 40 × 40: π·400 ± 20 px |
| `tests/test_mikro.py::FileTest::test_sample_calibration_roundtrip` | sample image 768 × 576, 16-bit, 0.25 µm/px |
| `tests/test_mikro.py::FileTest::test_png_and_rgb_and_garbage`, `::test_stack` | file types, RGB, invalid files, stacks |
| `tests/test_watershed.py::Watershed::test_edt_exact` | square: distance 16 at the centre; disc r = 15: √226 at the centre (9 places); 0 on background |
| `tests/test_watershed.py::Watershed::test_two_touching_discs` | two overlapping discs (r = 20, centres 34 px apart): 2 parts, 2 markers, area ratio 1 ± 0.05, cut at x = 87 ± 1.5 px, fewer than 40 line pixels |
| `tests/test_watershed.py::Watershed::test_counts_and_single_objects_kept` | chain of three discs plus one single disc gives 4; a single disc stays whole with no line pixels |
| `tests/test_watershed.py::Watershed::test_h_controls_merging` | strongly overlapping discs: h = 0.5 gives 2 parts, h = 15 gives 1 |
| `tests/test_watershed.py::Watershed::test_protocol_step_and_report` | watershed as a protocol step and in the report |
| `tests/test_compare.py::Unit::test_columns_values_stats` | length columns found; µm and mm columns give the same metres; excluded row dropped; D10/D50/D90 equal `numpy.percentile` (9 places); fewer than 3 values and a pixel unit are refused |
| `tests/test_compare.py::Report::test_items_and_citation`, `::test_rebuild_english_and_without_scale`, `::test_chart` | figure, table, values and citation of the dataset; no comparison without a scale; bin edges for a small example (1 to 5, 6 bins) |
| `tests/test_compare.py::Server::test_flow` | column list, live and pinned versions through the server |
| `tests/test_mikro.py::ScaleBarTest` (3), `::BundleTest` (3), `::ServerTest::test_flow` | scale bar, report bundle, server |
| `tests/test_golden.py::GoldenBundle::test_bundle_de`, `::test_bundle_en` | report bundle of the sample image equals a stored snapshot |

The golden tests are regression tests: they show that the result has not changed, not that it is correct. Triangle,
Maximum entropy, Yen and Percentile are only checked for returning a value in range.

## Known limitations

- **No reference implementation check.** No threshold method is compared with ImageJ or the original papers. Four
  methods are only smoke-tested.
- **Two references unverified.** Moments (Tsai 1985) and Minimum/Intermodes (Prewitt & Mendelsohn 1966) have no DOI
  and are marked unverified in the code, but the report cites them without a note.
- **Non-square pixels.** Particle perimeter, Major and Minor are scaled by the pixel width only. With pw ≠ ph they are
  wrong; area, hull, Feret and Solidity use both.
- **TIFF calibration** needs an ImageJ-style description; ResolutionUnit is ignored.
- **Edge exclusion** uses the image border, not the border of a selection. Excluded edge particles still lie in the
  region, so the area fraction is biased low when edge exclusion is on.
- **Holes** are excluded from the area by default but their boundaries add to the perimeter, which lowers the
  circularity.
- **D10/D50/D90 are number-based.** They are not comparable with volume-weighted laser-diffraction values without
  conversion.
- **Filters use square windows.** Median, mean, minimum, maximum and the opening use (2r+1)² squares, not discs.
- **Background subtraction** is an opening on a reduced image, not a rolling ball.
- **Watershed** can cut strongly non-round particles; the result depends on h.
- **Digital discretisation** biases perimeter (about +5 %), circularity (about 0.9 for discs) and, for particles of a
  few pixels, Feret and Solidity (section 6.3).
