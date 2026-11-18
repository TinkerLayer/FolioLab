# Mikroskopie (microscopy)

Evaluation of microscope images in Folio Lab: open an image, process it, separate objects from the background, measure,
count and size particles, and send the results to a report. Runs locally and needs only numpy, matplotlib and Pillow.

**Methods and validation:** [docs/methods/mikroskopie.md](../../docs/methods/mikroskopie.md) describes every computed
value, its defaults and limits, the cited references and the tests that check it.

The app starts in German. Below, a control is named by its English label followed by the German label in parentheses
where the page has an English text; controls that exist only in German are given in German with a translation.

## Workflow

1. **Home page ▸ Analyses ▸ Mikroskopie.** Drag an image in, or *File ▸ Bild öffnen …* (Datei ▸ Bild öffnen …, open
   image). Several images are possible and appear as tabs at the top. *File ▸ Beispielbild laden* (load sample image)
   shows the workflow on a 16-bit image with a scale.
2. **Scale** (tab *Scale* / Massstab, or a click on "Massstab …" / "ohne Massstab – festlegen" (no scale – set it) at
   the bottom right of the status bar): TIFF files with a calibration (resolution and unit) are taken over. The tab
   shows the pixel size, the image size and the source (file, line, preset, transferred from …).
   * **Calibrate from a line** (*Aus Linie*): drag the line tool over a known length (the microscope's burnt-in scale
     bar, a stage micrometer). The pixel length is taken over continuously; enter the known length and unit, then
     *Use* (Übernehmen). Or **enter the pixel size** (*Pixelgrösse eingeben*, µm/px or px/µm). *Aus Datei* (from file)
     restores the calibration of the file; *Entfernen* (remove) measures in pixels.
   * **Transfer to other images** (Auf andere Bilder übertragen): copies the scale of the current image to the ticked
     other images (also *Image ▸ Massstab auf alle Bilder übertragen*, transfer scale to all images). With "Neu
     geöffnete Bilder ohne Kalibrierung bekommen denselben Massstab" (newly opened images without calibration get the
     same scale), images opened afterwards without their own calibration get the scale set last.
   * **Presets** (Vorlagen): save a scale under a name (for example per objective) and apply it later with one click.
     Presets are stored in the browser.
   * **Scale bar** (Massstabsbalken): on/off, length (automatic, about one fifth of the image width, or fixed), corner,
     colour (white/black), bar thickness, font size, label, backing. *Stil auf alle Bilder* (style to all images)
     applies the look to all open images. The bar appears at once in the image, in the export and in the report;
     *Bild mit Balken speichern* (save image with bar) writes the image at full resolution with the bar burnt in as
     PNG.
   * Calibration and scale bar travel with the protocol (*Speichern …/Laden …*, save/load).
3. **Processing** (menus *Image* / Bild, *Process* / Prozess, *Binary* / Binär): every step goes into the **Protocol**
   (Protokoll) and is applied again to the original image when measuring, exporting and reporting. Steps can be removed
   one by one, undone (Ctrl+Z), saved as JSON and applied to all loaded images.
4. **Threshold** (tab *Threshold* / Schwelle): 13 automatic methods or manual limits, red preview. *Alle Methoden
   vergleichen* (compare all methods) shows the threshold and the object fraction per method. *Anwenden* (apply) makes
   the image binary.
5. **Particles** (tab *Particles* / Partikel): size, circularity, edge particles, holes, optionally only inside a
   selection. Result: count, area fraction, area, equivalent circle diameter (ECD) with D10/D50/D90, circularity,
   Feret, aspect ratio, solidity, grey values; outlines and numbers in the image, table under *Results* (Ergebnisse).
6. **Measure:** draw a selection, **Ctrl+M**. Without a selection the whole image is measured. **T** adds the selection
   to the list (tab *Selections* / Auswahlen); the list goes into the report. **Ctrl+K** shows the line profile of a
   line.
7. **File ▸ Exportieren** (export) writes to `outputs/mikroskopie/<image>/`: image with scale, mask, particle image,
   histogram, size distribution, CSV (semicolon, decimal comma) and `protokoll.txt`.
8. **To report …** (Zum Bericht …) sends figures, tables, key values (`\labval`), particle and profile data (CSV),
   sources (image file, threshold method) and text blocks (methods, results) to a Folio Lab report. *Refresh* in the
   report recomputes from the stored image file and the protocol.

## Tools

| Tool | Key | Use |
|---|---|---|
| Rectangle, ellipse | R, O | drag; Shift = square/circle; dragging inside the selection moves it |
| Polygon | G | click; double click, Enter or a click on the start point closes it |
| Freehand | F | drag |
| Line | L | drag, Shift snaps to 45°; width in the options bar |
| Points | P | click, Shift+click for more |
| Region by click | W | selects the connected region with the same value (± tolerance) |
| Magnifier, pan | Z, H | the mouse wheel always zooms; space bar or middle mouse button pans; 0 = fit, 1 = 100 % |

## Files

TIFF (8, 16, 32 bit, stacks, RGB; calibration from the resolution and an ImageJ description), PNG, JPEG, BMP, GIF.
Stacks have a slice slider; *Image ▸ Z-Projektion* (Z projection) combines them.

## Measured quantities

| Quantity | Meaning |
|---|---|
| Area | number of pixels × pixel area (a pixel belongs to a selection if its centre lies inside) |
| Perimeter | contour through the centres of the boundary pixels (edge lengths 1, √2 or √0.5) |
| Circularity | 4π·area/perimeter², 1 = circle (digital circles reach about 0.9) |
| ECD | diameter of the circle with the same area |
| Feret, MinFeret | largest and smallest distance between parallel tangents to the convex hull |
| Major, Minor, Angle | axes of the ellipse with the same area moments |
| AR, Roundness, Solidity | Major/Minor, 4·area/(π·Major²), area/area of the convex hull |
| Grey values | mean, standard deviation, min, max, median, integrated density; for binary images taken from the image **before** the threshold |

## Overview, tasks, environments

- The module opens on the **Overview** (Übersicht): project index and the environments (image names, scale,
  particles, measurements) with "+ Environment" (+ Umgebung). A click opens an environment; images with their protocol
  and scale stay there across a restart.
- The first tab is **Tasks** (Aufgaben): the workflow as a numbered list (Open image, Set scale, Improve image / Bild
  verbessern, Set threshold, Refine binary image / Binärbild nachbearbeiten, Analyse particles, Measure, Results and
  tables, To report) with a status per step for the current image ("✓ 0,25 µm/px", "n Schritte" (n steps), "✓ binär"
  (binary), "✓ n Partikel" (n particles), "erst Schwelle" (threshold first)). *Improve image* and *Refine binary
  image* offer the steps of the menus Process and Binary. The menus themselves are unchanged.
- Tasks and Display (Anzeige) are always visible; Scale, Threshold, Particles, Selections, Results and Protocol are
  under **More ▾** (Mehr ▾) or reached through a task. Transfer of the scale, presets, scale bar and the particle
  filters (Filters (size, shape, edge)) are collapsed. Header, menu titles, tabs, tasks and overview exist in German
  and English.
- *Project index …* (Projektindex …) shows the values of the project; measured values do not go into the index yet.
- **Values to other environments (⇄):** in the particle summary there is a ⇄ next to count, area fraction, mean area,
  ECD and D50. The value goes **live** or as a **snapshot** (Momentaufnahme) to another Mikroskopie environment and
  appears there in the box "Received values (connection)" (Übernommene Werte (Verbindung)). The microscopy module has
  no own equations. **⇄ Connections** (⇄ Verbindungen) in the header lists all connections.

## Comparison distribution from a dataset

**Comparison distribution …** (Vergleichsverteilung …) next to the particle views, or the import on the overview,
opens the shared import window.

* You choose a length column of a dataset, for example diameters from laser diffraction (nm … mm).
* The values are laid over the particle histogram with common classes, as relative frequency. Dashed lines mark the
  two D50 values.
* Next to it are D10/D50/D90, mean and count of both distributions and the ratio of the two D50 values.
* Requirements: a scale (otherwise there is no common unit) and a particle analysis.
* When the dataset is followed live ("always the latest"), the newest version is taken on opening, with a note. When
  the version is kept ("keep vN"), it stays, and a newer one is announced.
* In the report (only for a single image) there are a figure, a table, CSV, values (`cmpD50`, `cmpRatio` …) and a
  bibliography entry for the dataset with share ID, version and column.

## Limitations

- *Binary ▸ Wasserscheide* (watershed) separates touching particles (distance transform, markers from h-maxima).
  Strongly non-round particles can be cut; then increase h.
- *Hintergrund abziehen* (subtract background) estimates the background with an opening over a square window. This is
  similar to a rolling ball but not identical. Choose a radius larger than the largest objects.
- The references of the threshold methods and of the watershed were checked by DOI against Crossref (17.11.2026).
  Not confirmed, and therefore to be checked before publication: Moments (Tsai 1985) and Minimum/Intermodes (Prewitt
  & Mendelsohn 1966).

## Development

| File | Content |
|---|---|
| `mikro/imageio.py` | reading files, calibration, sample image |
| `mikro/ops.py` | processing steps (catalogue for menus and protocol) |
| `mikro/threshold.py` | 13 threshold methods with references |
| `mikro/label.py` | connected components (4/8), hole filling |
| `mikro/measure.py` | selections, measurements, particle analysis |
| `mikro/analysis.py` | evaluating the working state of an image (shared by server, export, report) |
| `mikro/charts.py` | figures, colour tables |
| `mikro/bundle.py` | result for the report (`folio-lab-bundle/1`) |
| `mikro/server.py`, `mikro/static/index.html` | local interface |

Tests: `python -m unittest discover -s tests` (in this folder). Stand-alone start:
`python -m mikro.server --port 8766` (opens the browser; the button *To report* appears only in Folio Lab).
