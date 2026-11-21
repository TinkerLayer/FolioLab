# Mikroskopie (microscopy): methods and validation

This file describes what the Mikroskopie module computes, how, with which defaults and limits, which references the
code cites and which tests check it. Code paths are relative to `modules/mikroskopie/`. User guide:
[modules/mikroskopie/README.md](../../modules/mikroskopie/README.md).

## How to cite results from this module

State the Folio Lab version (`version` in `package.json`) and the module version (`version` in
`modules/mikroskopie/module.json`, currently 1.3.0). When a result is sent to a report, Folio Lab writes
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

Pixel width pw (x) and pixel height ph (y) are kept separately (`Calib`). Every area, length, perimeter, Feret
diameter, ellipse axis and ECD uses both (section 6). When only one size is known, ph = pw is assumed and the
calibration carries the flag `square_assumed`; the report's methods text then says "pixel height assumed equal to
pixel width", and the file source says so in the scale pane.

- **From the file** (`_calibration`, TIFF tags 282 XResolution, 283 YResolution, 296 ResolutionUnit, 270
  ImageDescription). XResolution and YResolution are used separately: pw = 1/XResolution, ph = 1/YResolution.
  1. ImageDescription with a line `unit=` (as written by ImageJ): the resolution is in pixels per that unit
     (ImageJ then usually writes ResolutionUnit 1); `unit=pixel` means uncalibrated.
  2. Otherwise ResolutionUnit (TIFF 6.0): 2 = inch, 3 = centimetre give an absolute pixel size, converted to µm
     (25 400 µm/inch, 10 000 µm/cm); a missing tag counts as 2 (inch), the TIFF 6.0 default, and the source text
     says so. 1 = no absolute unit: not used as a scale (uncalibrated).
  3. Without XResolution: uncalibrated. Without YResolution: ph = pw, `square_assumed`.
  Inch resolutions that programs write as a print setting (72, 96, 150, 200, 240, 300, 350, 400, 600, 1200 dpi,
  equal in x and y; `PRINT_DPI`) are not used as a scale: 72 dpi would mean 352.8 µm/px. Other inch values are used,
  with a warning in the source text.
- **From a line** (`mikro/static/index.html`). Pixel size = known length / line length in pixels. The line length
  is rounded to 2 decimals. Pixels are taken as square (pw = ph); the pane says so.
- **Direct entry.** µm/px, or px/µm (the reciprocal is used). Pixels are square.
- A calibration set in the page refers to the original image; after an odd number of 90° rotations in the protocol,
  pw and ph are swapped (`analysis.run`). A calibration read from the file is rotated with the image.
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
| Subtract background (grey-scale opening) | see below | r = 50 px (2–1000), light background option |
| Math | add, multiply, ln(max(v, 0) + 1), square root, gamma (v/top)^γ·top, absolute value; log and root give 32-bit | – |
| Crop, rotate 90°, flip | rotation swaps pixel width and height | – |
| Z projection | max, mean, sum, SD, min, median | – |
| Threshold | section 3 | – |
| Erode, dilate | n passes with a 3 × 3 square element (8-neighbourhood), edge replicated | n = 1 (1–50) |
| Open, close | erode then dilate / dilate then erode | – |
| Fill holes | background not 4-connected to the image border becomes foreground | – |
| Watershed | section 5 | h = 1.0 px (0.1–50) |
| Outline | x and not erode(x) | – |

**Subtract background (grey-scale opening).** With s = max(1, ⌊r/10⌋): the image is reduced by taking the minimum
over s × s blocks; a flat grey-scale opening (minimum filter then maximum filter, square window of radius
max(1, round(r/s))) gives the background; it is enlarged bilinearly to the full size and smoothed with a box mean of
radius max(1, ⌊s/2⌋). Result = max(b − min(bg, b), 0). For a light background the image is inverted (max − b) before
and after. This is **not** the rolling-ball algorithm (Sternberg 1983, an opening with a non-flat, ball-shaped
structuring element); the step is therefore named "Hintergrund abziehen (Graustufen-Öffnung)" / "Subtract background
(grey-scale opening)" in the menu, and the protocol and report describe it as "grey-scale opening, square window,
r = … px". Up to version 1.2.0 the menu and report said only "Hintergrund abziehen" / "Subtract background".

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
| `moments` | Momente | preserves the first three moments (m₁, m₂, m₃ of the normalised histogram; two levels z₀, z₁ from z² + c₁z + c₀ = 0, p₀ = (z₁ − m₁)/(z₁ − z₀)); threshold = p₀-tile: the first bin whose cumulative fraction is ≥ p₀ (tolerance 10⁻⁹) | tsai1985 |
| `mean` | Mittelwert | floor of the mean grey value | glasbey1993 |
| `minimum` | Minimum | 3-point smoothing (edges replicated) until exactly two peaks remain (at most 10 000 passes, else falls back to `default`); first local minimum between the two peaks | prewitt1966 |
| `intermodes` | Intermodes | same smoothing; floor of the mean of the two peaks | prewitt1966 |
| `percentile` | Perzentil (50 %) | bin where the cumulative fraction is closest to 0.5 | doyle1962 |

The implementations are the module's own. Details such as zeroing bins 0 and 255 in `default`, the extra bin in
`triangle` and the 0.5 stop in `li` are implementation choices; the code does not state which reference
implementation they follow. No method is compared with another implementation in the tests (section 9).

Changes in 1.3.0: `moments` used "cumulative fraction > p₀" before; with "≥ p₀" a two-level image is split exactly
into its two values, as Tsai's p₀-tile intends (for real histograms the cumulative fraction practically never equals
p₀ at a bin, so results do not change). `minimum` returned the first local minimum anywhere, which could lie before
the first peak when the histogram falls from bin 0; it now searches only between the two peaks, as the method
(valley between the two maxima) requires.

## 4. References as cited in the code

The code (`mikro/threshold.py`, `mikro/watershed.py`, `mikro/measure.py`) states that the entries with a DOI were
checked against Crossref on 17.11.2026 (authors, year, volume, issue, pages). `tsai1985` and `prewitt1966` have no DOI;
in 1.3.0 the implemented algorithms were checked against the methods they cite (Tsai: the first three moments are
preserved and the threshold is the p₀-tile; Prewitt & Mendelsohn: smoothing to two maxima, then the midpoint of the
maxima or the valley between them, as also described by Glasbey 1993), and authors, title, journal, volume, pages and
year were confirmed; DOI and issue number are left out because they could not be checked offline. Both are no longer
in `UNVERIFIED` (now empty); a key listed there gets the note "Angaben nicht verifiziert" / "not verified" in the
report's bibliography. `hyndman1996` (quantile definition, section 6.2) is cited without DOI for the same reason.

| Key | Reference | DOI |
|---|---|---|
| ridler1978 | Ridler, T. W. and Calvard, S. Picture thresholding using an iterative selection method. IEEE Transactions on Systems, Man, and Cybernetics 8(8):630–632, 1978. | 10.1109/TSMC.1978.4310039 |
| otsu1979 | Otsu, Nobuyuki. A threshold selection method from gray-level histograms. IEEE Transactions on Systems, Man, and Cybernetics 9(1):62–66, 1979. | 10.1109/TSMC.1979.4310076 |
| zack1977 | Zack, G. W. and Rogers, W. E. and Latt, S. A. Automatic measurement of sister chromatid exchange frequency. Journal of Histochemistry and Cytochemistry 25(7):741–753, 1977. | 10.1177/25.7.70454 |
| li1993 | Li, C. H. and Lee, C. K. Minimum cross entropy thresholding. Pattern Recognition 26(4):617–625, 1993. | 10.1016/0031-3203(93)90115-D |
| huang1995 | Huang, Liang-Kai and Wang, Mao-Jiun J. Image thresholding by minimizing the measures of fuzziness. Pattern Recognition 28(1):41–51, 1995. | 10.1016/0031-3203(94)E0043-K |
| kapur1985 | Kapur, J. N. and Sahoo, P. K. and Wong, A. K. C. A new method for gray-level picture thresholding using the entropy of the histogram. Computer Vision, Graphics, and Image Processing 29(3):273–285, 1985. | 10.1016/0734-189X(85)90125-2 |
| yen1995 | Yen, Jui-Cheng and Chang, Fu-Juay and Chang, Shyang. A new criterion for automatic multilevel thresholding. IEEE Transactions on Image Processing 4(3):370–378, 1995. | 10.1109/83.366472 |
| tsai1985 | Tsai, Wen-Hsiang. Moment-preserving thresholding: a new approach. Computer Vision, Graphics, and Image Processing 29:377–393, 1985. | – |
| glasbey1993 | Glasbey, C. A. An analysis of histogram-based thresholding algorithms. CVGIP: Graphical Models and Image Processing 55(6):532–537, 1993. | 10.1006/cgip.1993.1040 |
| prewitt1966 | Prewitt, Judith M. S. and Mendelsohn, Mortimer L. The analysis of cell images. Annals of the New York Academy of Sciences 128:1035–1053, 1966. | – |
| doyle1962 | Doyle, Worthie. Operations useful for similarity-invariant pattern recognition. Journal of the ACM 9(2):259–267, 1962. | 10.1145/321119.321123 |
| vincent1991 | Vincent, Luc and Soille, Pierre. Watersheds in digital spaces: an efficient algorithm based on immersion simulations. IEEE Transactions on Pattern Analysis and Machine Intelligence 13(6):583–598, 1991. | 10.1109/34.87344 |
| soille2004 | Soille, Pierre. Morphological Image Analysis: Principles and Applications. 2nd edition. Springer, Berlin, 2004. (2nd edition 2003; the cited DOI belongs to the corrected 2nd printing of 2004, so key and year are 2004. Up to 1.2.0 the key was `soille2003` with year 2004.) | 10.1007/978-3-662-05088-0 |
| saito1994 | Saito, Toyofumi and Toriwaki, Jun-Ichiro. New algorithms for euclidean distance transformation of an n-dimensional digitized picture with applications. Pattern Recognition 27(11):1551–1565, 1994. | 10.1016/0031-3203(94)90133-3 |
| hyndman1996 | Hyndman, Rob J. and Fan, Yanan. Sample quantiles in statistical packages. The American Statistician 50(4):361–365, 1996. Cited in the report's methods text whenever particles are analysed. | – |

Named in the code and this page but not in the report's bibliography: the rolling-ball method (S. R. Sternberg,
"Biomedical image processing", Computer 16(1):22–34, 1983, doi:10.1109/MC.1983.1654163), which the module does
**not** implement (section 2), and the Miles–Lantuéjoul edge correction (section 6.2), for which no reference is
given because it could not be verified offline.

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
| Line | sampled at round(L) + 1 points (L in pixels), bilinear interpolation; a width > 1 averages parallel lines. Length = √((dx·pw)² + (dy·ph)²); angle = atan2(−dy, dx) in degrees (pixel grid) |
| Line profile | distance along the line = pixel distance × \|(dx·pw, dy·ph)\| / \|(dx, dy)\| (`line_scale`), so the last point is at the line's calibrated length; before 1.3.0 the pixel distance was multiplied by pw only |
| Point | pixel value |

If the image is binary and a grey image before the threshold exists, intensities are taken from that grey image.

### 6.2 Particle analysis

Connected components are labelled with a run-based union-find in 8-connectivity. Filters and defaults:

| Parameter | Default | Rule |
|---|---|---|
| Size | 0 to ∞ | in calibrated area units, or pixels if "size in pixels" is set |
| Circularity | 0 to 1 | applied after the size filter |
| Edge correction (`exclude_edges`) | on | see "Edge correction" below |
| Include holes | off | if on, holes (background not 4-connected to the border) are filled before labelling |
| Perimeter (`perimeter`) | `outer` | `outer`: outer contour only (holes filled for the perimeter); `total`: also the contours of holes (the only behaviour up to 1.2.0). UI: "Lochränder zum Umfang zählen" |
| Region | none | an area selection masks the image; its area is the denominator of the area fraction |

Per particle (pw, ph = pixel width and height; all quantities use both):

| Quantity | Definition |
|---|---|
| Area | pixels × pw × ph |
| Perimeter | length of the marching-squares contour at level ½ between the pixel centres, i.e. the polygon through the midpoints of the edges between foreground and background pixel centres (crack boundary with every corner cut by half a pixel diagonal). Per 2 × 2 cell of pixel centres: 1 or 3 foreground pixels add ½·√(pw² + ph²); 2 horizontally adjacent add pw; 2 vertically adjacent add ph; 2 diagonal (saddle, treated as separate) add √(pw² + ph²). With pw = ph = 1: straight steps 1, corners √½. Default: outer contour only, computed on the particle with its holes filled (a particle lying inside the hole of another keeps its own perimeter) |
| Circularity | min(1, 4π·Area/Perimeter²), Area without holes unless "include holes" |
| ECD | 2·√(Area/π) |
| Major, Minor, Angle | second central moments of the pixel centres in calibrated units (x·pw, y·ph), each plus the pixel extent (pw²/12, ph²/12); Major = 4√λ₁, Minor = 4√λ₂, scaled so that π·Major·Minor/4 equals the Area. Angle = ½·atan2(−2μ₁₁, μ₂₀ − μ₀₂) in calibrated coordinates, modulo 180° |
| AR | Major/Minor |
| Roundness | 4·Area/(π·Major²) |
| Convex hull | monotone chain over the corners of the boundary pixels, scaled by pw and ph |
| Feret, FeretAngle | largest distance between two hull vertices, and its angle |
| MinFeret | smallest width of the hull over the normals of its edges |
| Solidity | min(1, Area/hull area) |
| Weight | edge-correction weight (1 without edge correction) |
| Mean, StdDev, Min, Max, IntDen | of the grey values in the particle; StdDev with n − 1; IntDen = Area·Mean |

Up to 1.2.0, perimeter, Major and Minor were scaled by pw only (wrong when pw ≠ ph); the line profile likewise.

**Edge correction** (default on). R = the analysed area (whole image, or the selected region), |R| its number of
pixels; the interior of R is R without the pixels that have an 8-neighbour outside R (for the whole image: without
the outermost row and column on each side).
1. A particle is measured only if its bounding box (w × h pixels) lies entirely in the interior of R. For the whole
   image this is the rule of 1.2.0 ("bounding box does not touch the image border"); for a region it is new (1.2.0
   ignored the border of a region).
2. Each measured particle gets the Miles–Lantuéjoul weight wᵢ = |R| / N(w, h), where N(w, h) is the number of
   integer positions in which a w × h box lies entirely in the interior of R (summed-area table; for the whole image
   N = (W − w − 1)(H − h − 1)). wᵢ is the inverse probability that a particle of this size, placed at random, is
   measured; large particles touch the border more often and get larger weights.
3. Means and SDs of the summary, the D values and the size histograms use these weights. Weighted mean
   Σwx/Σw; weighted SD with denominator Σw − Σw²/Σw (n − 1 for equal weights).
4. CountCorrected = Σwᵢ estimates the number of particles in R (reference point: bounding-box corner); Density =
   CountCorrected / region area.
5. AreaFraction = 100 · ForegroundArea / region area, where ForegroundArea is the area of **all** particles that pass
   the size and circularity filters, including those at the border (their visible part). 1.2.0 used only the
   non-edge particles, which biased the area fraction low. Note that the filters are applied to the visible part of
   border particles. TotalArea is still the area of the measured particles.
Without edge correction all particles are measured with their visible part and every weight is 1.

Summary keys: Count (measured), CountCorrected, Density, TotalArea, ForegroundArea, AreaFraction, RegionArea,
AverageSize/SDSize (area), Mean/SD of Perimeter, Circularity, ECD, Feret, MinFeret, AR, Solidity and Mean, the D
values, EdgeCorrection (`miles-lantuejoul` or `none`) and Perimeter (`outer` or `total`).

**D values.** D10, D50, D90 are quantiles of the **number-weighted** ECD distribution (Q0; weights wᵢ).
Dv10, Dv50, Dv90 are quantiles of the **volume-weighted** distribution (Q3; weights wᵢ·ECDᵢ³, i.e. each particle as a
sphere of diameter ECD), the basis on which laser-diffraction instruments usually report D values. Weighted quantiles
use the midpoint rule (`measure.wquantile`): sorted values xᵢ sit at Pᵢ = (Sᵢ − wᵢ/2)/Sₙ (Sᵢ = cumulative weight),
linear interpolation in between, the first/last value outside [P₁, Pₙ]. For equal weights this is definition 5 of
Hyndman & Fan (1996) (numpy `method="hazen"`); it does not depend on the scale of the weights, which a volume weighting
needs. Up to 1.2.0 the D values were unweighted `numpy.percentile` (linear, definition 7) and labelled without a basis.

### 6.3 Behaviour on ideal digital discs

The following values were obtained with module version 1.2.0 on ideal digital discs (pixels whose centres lie within
radius r), pixel size 1; for square pixels and particles without holes the computation is unchanged in 1.3.0. They
are not part of the test suite; they show the size of the discretisation effects.

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
the perimeter runs along the pixel edges with cut corners. A circularity of 1 is not reached by digital discs; small
particles (r ≤ 5 px) have a strongly biased Feret and solidity.

**Non-square pixels** increase the perimeter bias: a disc of radius 30 µm sampled with pw × ph = 0.5 × 1.5 µm (3:1)
gives Perimeter/2πR = 1.127 and circularity 0.79; with 0.5 × 1.0 µm (2:1) 1.091 and 0.84; with square pixels of
1 µm 1.056 and 0.90 (values from `tests/test_known_answers.py` geometry, 1.3.0). Area, ECD, Major and Minor stay
within 1–2 % of the true values.

## 7. Comparison distribution from a dataset (`mikro/compare.py`, `mikro/charts.py`)

- A column counts as a length if its unit is a length unit. Values must be finite and > 0; rows flagged as excluded
  in the dataset are dropped. 3 to 50 000 values. Values are stored in metres with 6 significant digits.
- A calibrated image is required; in pixels the comparison is refused.
- Statistics of both distributions are computed the same way (`compare.stats`): n; D10, D50, D90 number-weighted
  (Q0); Dv10, Dv50, Dv90 volume-weighted (Q3, weight d³); mean and SD (Q0). Quantiles by the midpoint rule of section
  6.2. Particles carry their edge-correction weights, so their values equal the particle summary; every dataset
  value counts as one particle (weight 1). Ratio = D50 (Q0) of the particles / D50 (Q0) of the dataset.
- Chart: common linear bins over the joint range, number of bins = max(6, min(40, 2·⌊√(min(n_a, n_b))⌋)); relative
  frequency by number in % (particles weighted); dashed lines at both D50 (Q0).
- The page, CSV export and report label every D value with its basis (Q0 or Q3) and state that a dataset value is
  treated as one particle.

The comparison is only like with like if the dataset column holds individual particle sizes. Laser-diffraction
instruments usually report a volume-weighted distribution (or its Dv values); such values are not individual sizes
and cannot be compared this way. The module does not convert a measured Q3 distribution into Q0.

## 8. Measurement uncertainty and own equations (`mikro/uncertainty.py`, since 1.4.0)

Optional; settings in the state as `unc` (`method`, `p`, `k`, `specs` for `cal_len`, `cal_px`, `cal_pw`, `cal` = how
the scale was made: line `L`/`N` or pixel size `pw`, `boot` = number of bootstrap resamples, default 1000). Without
them nothing changes. Propagation by `labcalc.uncertainty` (GUM linear, Monte Carlo after GUM S1, Gaussian, worst
case). Results without any uncertain input (u = 0 and U = 0) are not shown.

| Value | Model | Contributions |
|---|---|---|
| pixel size s | s = L / N (line; used when L/N equals the applied pixel size) or s = pw | certificate of the stage micrometer (U, k) on L; reading of the line ends (e.g. limits ±1 px, rectangular) on N; or ± on pw |
| mean ECD, D10, D50, D90 (Q0), Dv50, mean Feret | Y = Q·(s/s₀) | scale (relative), sampling: bootstrap standard deviation over the particles (type A) |
| mean area | Y = Q·(s/s₀)² | scale twice (relative), bootstrap |
| count | N | √N (Poisson counting statistics) |
| area fraction A_A | Σ a_i / A | bootstrap over the particle areas; the scale cancels |

The bootstrap resamples the measured particles with replacement (edge-correction weights kept) and uses a fixed
seed (20261119), so a result is reproducible; it is labelled "Bootstrap …, Typ A" in the budget. Several images in
one report (fields): mean ± Student-t interval of s/√n over the fields (ASTM E562 style), with the common scale term
for lengths treated as fully correlated. A helper `binomial_u(k, n)` = √(p(1 − p)/n) gives the uncertainty of a
number fraction; the module reports no number fractions yet, so it is only used in the tests.

Sources (module records, all marked "Angaben nicht am Original geprüft", not checked against the original): Efron
and Tibshirani 1993 (bootstrap), Taylor 1997 ch. 11 (Poisson counting), ASTM E562 (point counting; mean ± t·s/√n
over fields).

Own equations (`labcalc.formulas`, stored as `eigene_gleichungen.json` in the module's output folder): variables are
`n`, `nCorr`, `areaFrac`, `meanArea`, `meanECD`, `sdECD`, `meanCirc`, `meanFeret`, `D10` … `Dv90`, `region`, `px`;
the u of a variable with a budget is propagated with the chosen method. The report gets `unc-<name>-pm` / `-u` /
`-U`, budget tables, `eq-…` values and a methods paragraph; several images add `serie-<name>-…`.

## 9. Validation

Run `python -m unittest discover -s tests` in `modules/mikroskopie`. The suite has 68 tests and needs no unpublished
data. `tests/test_uncertainty.py` (10 tests) checks: u(s)/s = √((u_L/L)² + (u_N/N)²) for U = 0.5 µm (k = 2) on 50 µm
and ±1 px on 200 px; the L and N contributions to u(D50) equal D50·u(L)/L and D50·u(N)/N, twice that for the mean
area; without the sampling term u(D50)/D50 equals u(s)/s; u(count) = √N; `binomial_u(20, 100)` = 0.04; the area
fraction budget has no scale term; the bootstrap is reproducible; all four methods; own equations get u; series
mean ± s/√n; report bundle. `tests/test_known_answers.py` (24 tests, added in 1.3.0) holds known-answer tests with analytic expectations or
independent references (contourpy, numpy's Hazen percentile).

| Test (`tests/test_known_answers.py`) | Expected |
|---|---|
| `TiffResolution::test_inch_and_separate_x_y` | XResolution 2540, YResolution 1270 px/inch → pw = 10 µm, ph = 20 µm |
| `TiffResolution::test_centimetre` | 1000 px/cm → 10 µm/px |
| `TiffResolution::test_no_absolute_unit_is_no_scale` | ResolutionUnit 1 → uncalibrated |
| `TiffResolution::test_imagej_description_wins` | `unit=micron`, 4 and 2 px/unit → 0.25 × 0.5 µm |
| `TiffResolution::test_only_x_resolution_assumes_square_and_says_so`, `::test_calib_from_dict_without_ph_is_square_assumed` | ph = pw, flag set, source text says so |
| `NonSquarePixels::test_rectangle_exact` | 40 × 20 px at 0.5 × 2 µm: Area 800 µm², Feret √(20² + 40²), MinFeret 20, Perimeter 2·39·0.5 + 2·19·2 + 2·√(0.5² + 2²), AR 2, Angle 90° (9 places) |
| `NonSquarePixels::test_rotation_with_swapped_pixel_size_gives_same_values` | image rotated by 90° with pw and ph swapped gives identical values |
| `NonSquarePixels::test_physical_disc_on_rectangular_pixels` | disc R = 30 µm at 0.5 × 1.5 µm: Area πR² ± 1 %, ECD, Major, Minor 2R ± 2 %, Feret, MinFeret ± 4 %; perimeter equals contourpy's level-½ contour length (6 places) |
| `NonSquarePixels::test_line_length_and_profile_scale` | line length √((dx·pw)² + (dy·ph)²); last profile point at that length |
| `NonSquarePixels::test_report_states_pixel_geometry` | methods text says "nicht quadratisch" or "Pixelhöhe gleich Pixelbreite angenommen" |
| `OuterPerimeter::test_square_ring` | 30 px square with 10 px hole: outer 4·29 + 4√½, total adds 4·9 + 4√½ (9 places) |
| `OuterPerimeter::test_disc_ring_equals_disc`, `::test_particle_inside_hole_keeps_its_own_perimeter` | ring's outer perimeter = its disc's; an island in a hole keeps its own perimeter |
| `EdgeCorrection::test_whole_image`, `::test_oval_region` | periodic field (one 9 × 7 and one 3 × 3 px particle per 24 × 24 cell), averaged over all 576 window translations: corrected count per type = \|R\|/576 and area fraction = 12.5 % exactly (9 places); unweighted counts are biased: 30·28/576 vs 36·32/576 |
| `EdgeCorrection::test_weights_and_summary` | weight WH/((W − w − 1)(H − h − 1)); area fraction includes the corner particle |
| `Quantiles::test_equal_weights_are_hazen` | equals `numpy.percentile(method="hazen")` (10⁻¹²) |
| `Quantiles::test_volume_weighting` | d = 1, 2, 10 with d³: D50 = 2 + 499.5/504·8; invariant to weight scale |
| `Quantiles::test_summary_q0_q3_and_comparison_alike` | particle summary and `compare.stats` give identical Q0 and Q3 values |
| `ThresholdMethods::test_moments_two_level_image` | 70 % at 50, 30 % at 200 → lower class {50} |
| `ThresholdMethods::test_minimum_ignores_falling_start` | falling start plus modes at 60 and 180: Minimum and Intermodes 120 ± 3 |
| `ThresholdMethods::test_references_consistent` | year in every key equals the year field; `soille2004`; no unverified keys |
| `BackgroundName::test_named_for_what_it_is` | menu and protocol say "Graustufen-Öffnung" / "grey-scale opening", never "rolling" |

Earlier tests:

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
| `tests/test_compare.py::Unit::test_columns_values_stats` | length columns found; µm and mm columns give the same metres; excluded row dropped; D10/D50/D90 equal `numpy.percentile(method="hazen")` (9 places), Dv50 > D50; fewer than 3 values and a pixel unit are refused |
| `tests/test_compare.py::Report::test_items_and_citation`, `::test_rebuild_english_and_without_scale`, `::test_chart` | figure, table, values and citation of the dataset; no comparison without a scale; bin edges for a small example (1 to 5, 6 bins); legend says "D50 (Q0)" |
| `tests/test_compare.py::Server::test_flow` | column list, live and pinned versions through the server |
| `tests/test_mikro.py::ScaleBarTest` (3), `::BundleTest` (3), `::ServerTest::test_flow` | scale bar, report bundle, server |
| `tests/test_golden.py::GoldenBundle::test_bundle_de`, `::test_bundle_en` | report bundle of the sample image equals a stored snapshot |

The golden tests are regression tests: they show that the result has not changed, not that it is correct. Triangle,
Maximum entropy, Yen and Percentile are only checked for returning a value in range. The goldens were regenerated
for 1.3.0 (area fraction, edge-weighted means and D values, Q0/Q3 labels, Dv values, weight column, background step
name, `hyndman1996` citation).

## Known limitations

- **No reference implementation check.** No threshold method is compared with ImageJ or the original papers. Four
  methods are only smoke-tested. The references for Moments and Minimum/Intermodes have no DOI and no issue number
  (not checkable offline).
- **TIFF inch resolutions.** A TIFF without an ImageJ description but with ResolutionUnit inch (or no ResolutionUnit,
  inch by TIFF 6.0) is calibrated unless the value is a common print setting (`PRINT_DPI`). An unusual print value
  (e.g. 110 dpi) would still be taken as a scale; the scale pane shows the source with a warning, check it. PNG pHYs and JPEG/JFIF densities are
  not read.
- **Non-square pixels** are handled in all measurements, but the perimeter's digitisation bias grows with the pixel
  aspect ratio (section 6.3). A calibration from a line or by direct entry is always square.
- **Edge correction** assumes a stationary particle field (particles placed independently of the field of view). It
  corrects with the bounding box, so it is exact only for the box-containment rule used here; particles larger than
  the interior of the field are never measured and cannot be corrected for. Size and circularity filters act on the
  visible part of border particles when the area fraction is computed. With a region, the area of particles cut by
  the region border counts with its part inside the region.
- **Volume-weighted D values** assume spheres with diameter ECD (projected-area diameter); they are not a measured
  volume distribution and differ from laser diffraction, which also depends on the optical model.
- **Comparison** treats each dataset value as one particle; it is not valid for D values or class data of a
  laser-diffraction distribution.
- **Filters use square windows.** Median, mean, minimum, maximum and the background opening use (2r+1)² squares,
  not discs.
- **Background subtraction** is a flat grey-scale opening on a reduced image, not a rolling ball; it is named so.
- **Watershed** can cut strongly non-round particles; the result depends on h.
- **Digital discretisation** biases perimeter (about +5 % for square pixels, more for non-square ones), circularity
  (about 0.9 for discs) and, for particles of a few pixels, Feret and Solidity (section 6.3).
