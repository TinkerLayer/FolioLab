# Analysis modules

How modules work today. The planned move to projects, environments, Shareboxes and provenance is in
`docs/ARCHITECTURE.md`; new module code should already follow its §3 rules.

An analysis module is a small local web app that evaluates one kind of measurement, for example
tensile tests (`modules/zugversuch`) or FTIR spectra (`modules/ftir`). Folio Lab starts it on demand,
shows it at `/m/<id>/`, and stores its results in report projects. The report editor then inserts figures, tables,
values, data plots, references and text from those results.

```
 browser ── /            hub (Node, server/index.js) ── projects/<id>/files/lab/<slug>/...
         ── /m/<id>/...  ─ proxy ─▶ module (Python, own port on 127.0.0.1)
         ── /lab/sdk.js  "send to report" dialog for module pages
```

## 1. Add a module

Create `modules/<id>/module.json`:

```json
{
  "id": "ftir",
  "name": "FTIR",
  "name_en": "FTIR",
  "description": "German description (shown in the module's own language)",
  "description_en": "English description for the home page",
  "icon": "layers",
  "color": "#007b83",
  "status": "ready",
  "order": 20,
  "accepts": [".spa", ".csv"],
  "runtime": {
    "type": "python",
    "args": ["-m", "ftir.server", "--port", "{port}", "--out", "{outputs}"],
    "health": "/api/meta"
  },
  "bundle": { "build": "/api/bundle", "rebuild": "/api/bundle/rebuild" }
}
```

| Field | Meaning |
|---|---|
| `id` | Folder name, lowercase letters, digits and `-`. Becomes the URL `/m/<id>/`. |
| `status` | `ready`, or `planned` to show a "Planned" card without starting anything. |
| `icon` | An icon name from `public/js/ui.js` (`chart`, `layers`, `data`, `flask`, ...). Used when `icon_svg` is missing. |
| `icon_svg` | Optional: the inner markup of a 24×24 stroke icon, the same as the `class="brand"` SVG in the page header, so the hub card and the module show one picture. Only `path`, `circle`, `rect`, `line`, `polyline`, `polygon`, `ellipse`, `g` and plain geometry attributes are drawn; anything else falls back to `icon`. `sdk/python/tests/test_icons.py` checks that it matches the page. |
| `runtime.type` | `python` (the hub finds Python 3.10+) or `command` with `runtime.command`. |
| `runtime.args` | `{port}` is a free port the module must listen on (127.0.0.1 only), `{outputs}` is `outputs/<id>/` for files the module writes, `{module}` is the module folder. |
| `runtime.health` | A GET path that answers once the module is ready. The hub waits up to 45 s. |
| `bundle.rebuild` | Endpoint the hub calls for **Refresh** (default `/api/bundle/rebuild`). |

Put the Python packages in `modules/<id>/requirements.txt`; `setup.ps1` installs them. The module folder and
`sdk/python` are on `PYTHONPATH`, so `import labbundle` works. Environment: `FOLIO_LAB=1`, `PYTHONIOENCODING=utf-8`.
Output of the module process appears in the Folio Lab console window prefixed with `[<id>]`.

Rules for the module's web page:

- Use **relative** URLs (`fetch("api/x")`, not `"/api/x"`), because the page lives under `/m/<id>/`.
- Load the SDK with `<script src="/lab/sdk.js"></script>`. It is only there when the page runs inside Folio Lab,
  so show the "send to report" button only if `window.Lab` exists. The module keeps working on its own.
- Reject POSTs whose `Origin` header is not localhost (the hub checks too).

## 2. Send results to a report

In the module page:

```js
Lab.sendToReport({
  module: "ftir",
  title: "FTIR sample A",
  scopes: [{ id: "sel", label: "Selected spectrum" }, { id: "all", label: "All spectra (overlay)" }],
  include: [{ id: "figures", label: "Figures" }, { id: "tables", label: "Peak table" }],
  build: ({ scope, lang, include, title }) =>
    fetch("api/bundle", { method: "POST", body: JSON.stringify({ scope, lang, include, title }) }).then(r => r.json()),
});
```

The dialog lets the user pick or create a report (template **Lab report**), the language (`de`/`en`) and the content,
calls `build()` and stores the returned bundle. If a result with the same name exists, the user chooses *Replace*
or *Keep both*. `include` is a map `{id: true|false}` of the switches you offered.

### Import from any environment

The editor's **Import from Folio** dialog lists the environments of every module and imports single pieces of their
reports. For that a module must be able to build the report of a stored environment without switching to it:

- **Page:** pass `report: () => body` to `LabEnv.create({...})`, where `body` is exactly what *Send to report* would
  POST to `api/bundle` now (sections/scope, `lang`, `include`, `title`), or `null` if there is nothing to report. It is
  saved with the environment as `client.report`; errors in it never block saving.
- **Server:** set `ModuleEnvs.env_bundle = fn(stored, report, lang) -> bundle`. `stored` has the same shape as
  `stored()`, but for the requested environment; build the bundle from those files and the request, as the
  stateless rebuild (`/api/bundle/rebuild`) does. Optionally set `env_default_report = fn(stored, client, eid)` to
  derive a request for environments saved before `client.report` existed (Zugversuch, Rechner and
  Datenaufbereitung do). The SDK serves
  `POST /api/env/bundle {env, lang}` and adds `origin` (module, project, environment, name, modified). Raise
  `EnvError` (or `ValueError`/`KeyError`) with a German message when nothing can be built; the dialog shows it.
- **Hub:** `GET /api/folio/modules`, `GET /api/folio/env?module&env&lang&target` (pieces: figures with PNG preview,
  tables, text, data, every `\labval` value; references; methods text; cached by content hash), `GET /api/folio/file`
  (previews). `POST /api/projects/:id/import` with `{source: {type: "env", stage}, keys, mode, methods}` saves the
  chosen pieces as a result of the real module with `pick` and `link: {type: "env", …}`; the link is "changed" when
  the hash of the environment's files and report request differs.

## 3. The bundle (`folio-lab-bundle/1`)

Build it in Python with `sdk/python/labbundle.py`:

```python
from labbundle import Bundle, booktabs, num, tex_escape

b = Bundle(module="ftir", module_name="FTIR", title=title, lang=lang, slug=request.get("slug"))
b.add_figure(fig, "spectrum", caption="Absorbance spectrum of sample A.")            # matplotlib figure
b.add_figure(fig2, "search", caption="Best library hits.", cites=["openspecy2025"])  # caption gets ~\cite{...}
b.add_table("peaks", booktabs(["Peak", r"$\tilde\nu$ [cm$^{-1}$]"], rows, escape_header=False),
            caption="Assigned peaks.")
b.add_values([("Amax", "Maximum absorbance", num(0.82, 2, lang), "0.82")])          # \labval{slug}{Amax}
b.add_data_csv("spectrum", ["wn_cm1", "A"], rows, "Spectrum of sample A",
               labels={"wn_cm1": r"Wavenumber [cm$^{-1}$]", "A": "Absorbance"}, plot={"x": "wn_cm1", "y": "A"})
b.add_citation("example-std", "misc", title="Standard used: ...", year="2021")
b.add_text("methods", r"Spectra were recorded ... \cite{example-std}.", title="Methods")
b.set_source(request, {"sampleA.spa": raw_bytes})                                   # enables Refresh
return b.to_dict()
```

JSON shape (all `files` are base64):

```json
{
  "format": "folio-lab-bundle/1", "module": "ftir", "module_name": "FTIR",
  "title": "FTIR sample A", "slug": "ftir-sample-a", "lang": "en", "summary": "one line for the list",
  "items": [
    {"kind": "figure",   "id": "spectrum", "file": "fig/spectrum.pdf", "preview": "fig/spectrum.png", "caption": "...", "label": "fig:ftir-sample-a-spectrum", "width": "0.9"},
    {"kind": "table",    "id": "peaks", "file": "peaks.tex", "caption": "...", "label": "tab:ftir-sample-a-peaks", "notes": ""},
    {"kind": "values",   "file": "values.tex", "values": [{"key": "Amax", "label": "...", "latex": "0.82", "text": "0.82"}]},
    {"kind": "data",     "id": "spectrum", "file": "data/spectrum.csv", "columns": ["wn_cm1", "A"], "labels": {}, "plot": {}, "description": "...", "rows": 1800},
    {"kind": "citation", "key": "example-std", "title": "..."},
    {"kind": "text",     "id": "methods", "file": "text-methods.tex", "title": "Methods"}
  ],
  "files": {"fig/spectrum.pdf": "...", "values.tex": "...", "refs.bib": "..."},
  "source": {"request": {"...": "whatever the module needs to rebuild"}, "files": {"sampleA.spa": "..."}}
}
```

Conventions:

- `caption`, `label` (`fig:`/`tab:` + slug + id), value `latex`, table and text files are **LaTeX source**. Escape
  plain text with `tex_escape()`; `num()` writes numbers with the decimal mark of the language and a thin space before the unit.
- Figures: vector PDF for LaTeX plus a PNG preview for the editor (`add_figure` does both, when `to_dict()` runs).
  `add_figure` also takes a function without arguments that returns the figure; it is called only when the figure
  is written, so the editing window's preview of one figure does not draw the others (Zugversuch does this).
- CSV: point decimals, comma separator, header row (what pgfplots expects). Text columns last, without a label.
  `plot` may carry `"style": "marks"` for scatter data (e.g. one row per particle); the editor's **Plot** then
  draws points instead of a line.
- Value keys: letters, digits and `-`. Citation keys: unique per source (prefix them, e.g. `data-<slug>`).
- **Sources travel with the figure.** A figure or table that shows third-party data (reference spectra, material
  values, standards) passes their keys as `cites=[...]` to `add_figure`/`add_table`. The SDK appends `~\cite{...}` to
  the caption and records `"cites"` on the item, so inserting only that figure or table still puts its sources in the
  bibliography (the editor wires up `lab/references.bib` when a caption cites). The editor shows "cites n sources
  automatically" next to such items. Label the plotted references in the figure itself as well (names, or numbers
  with a key), so the picture can be read without the caption.
- `source.request` must be enough to rebuild the same bundle; the hub adds the stored `slug` to it.
  Rebuild endpoint body: `{"source": {"request": {...}, "files": {name: base64}}, "lang"?: "de"|"en"}`.
  Pass the request on to `set_source` as received (extra keys included): the hub adds `styles`,
  `describe_figures` and `preview` to it for styled figures (below).
- **Methods text in steps.** Write the methods text with
  `b.add_methods(paragraphs, title, id="methodik", sep="\n\n", eq=equations_tex)` instead of `add_text`. The full text
  is still `text-<id>.tex`; in addition every sentence becomes a step (`methods/<step>.tex`, listed on the item as
  `steps: [{id, title, short, own_short, par, file, eq?}]`). *Short* is three sentences at most: the first sentence
  (what was measured), the first later sentence that names a standard (ISO, DIN, EN, ASTM, VDI or a cited standard) and
  the software sentence. A module can choose its own short steps by passing steps as dicts `{id, title, text,
  short: True}` (`own_short`); those are cut to three. The software sentence ("The analysis used Folio Lab, <module> module, version
  <x>", cited as `folio-lab-<module>`, name and version from `module.json`) is added as the last step unless the text
  already names Folio Lab; pass `software=False` to leave it out. The equations block is one step with `eq: true`. Sentences are not split inside `$…$`, inside braces,
  after common abbreviations or after single letters. The import dialog and the Lab dialog offer Short / Full / own
  ticks; the hub sets the chosen steps as running text in `text-<id>-auswahl.tex` and records it on the item
  (`shown_file`, `shown_steps`). Same paragraph: joined with a space; otherwise a blank line.
- **Pieces cite and describe only what they show.** Declare per figure what it is made of, so that a reduced piece
  brings neither sources nor methods sentences for anything it does not show:
  - `add_figure(fig, id, "Curve{parts}.", cites=[always], steps=[always], parts=[...], parts_lead="with")`. A part is
    `{id, label, cites, steps, caption, note, list, match}`: `caption` is an inline fragment set at `{parts}`, `note` a
    sentence after the caption, parts with the same `list` share one sentence ("<list> A, B and C."). Mark its artists
    with `labstyle.mark(artists, part_id)` or give `match` globs over element keys.
  - A part is off when the style spec says `"parts": {id: {"hidden": true}}` or when all its artists are hidden in
    Customise. The SDK then rebuilds caption and `cites` from the visible parts; `caption_full` keeps the whole caption.
  - `add_table(..., steps=[...])`, `add_values(values, needs={key: [steps]})`, `add_text(..., steps=[...])` name the
    steps those pieces need. For tables and values added by a helper use `mark = b.added_mark()` and
    `b.needs_since(mark, steps)`.
  - Sentence ids stay running (`s1`, `s2`, ...), so saved picks and edits survive. Name the evaluation step with a dict
    step `{"of": name, "text": sentence}` or with `step_tag("name")` inside a plain string (runs until the next mark;
    `step_tag("")` = no step). Add new steps at the end.
  - `add_methods(..., brief=b.brief_from(text))` gives the one-sentence text (measurement, standard, software) used
    under *Short* when no shown piece needs an evaluation step. It is stored as step `kurz` and is not in the full text.
  - The hub (`stepScope` in `server/lab.js`) keeps a step when a shown piece, part or value names it, or when no piece
    names it. An undeclared figure, table or text counts as needing everything, so old bundles behave as before. A
    live variant stands in for its piece, and the text follows when a variant is saved or removed. Edited sentences
    stay stored, also while their step is not shown.
- **Figure styles.** `add_figure` keeps the matplotlib figure until `to_dict()`. When `source.request.styles` is
  `{figure id: spec}` (or `b.styles` is set), the SDK applies the spec with `sdk/python/labstyle.py` and redraws that
  figure's PDF and PNG; the item gets `style` (the spec used, preset values filled in). With
  `source.request.describe_figures` every figure gets `describe` (size, axes with labels, limits and scales, the named
  series with colours, title) as the module drew it, plus `describe.now` (size after the style). Spec keys: `preset`
  (journal column widths and fonts, see `labstyle.PRESETS`), `width_mm`, `aspect`, `font`, `font_size`, `line_width`,
  `palette` (name or colour list), `series {legend label: {color, lw, ls, hidden, label}}`, `legend {show, loc,
  frame}`, `title`, `axes [{xlabel, ylabel, xlim, ylim, xscale, yscale, grid, xticks, yticks}]`,
  `elements {key: {hidden, color, lw, ls, alpha, size, bold, text, label}}` for any drawn line, marker, area, bar or
  text, `groups {kind: {...}}` for every element of a kind at once (`axis_labels`, `tick_labels`, `series_names`,
  `annotations`, `lines`, `markers`, `areas`; the props each takes are in `labstyle.GROUPS`; an element's own entry
  wins, `hidden: false` shows it although its kind is hidden), `colors {background, plot, axes, ticks, grid, text}` and
  `crop [left, top, right, bottom]` (share of the figure cut off). `font` is serif, sans, cm (Computer Modern) or any
  font installed where the module runs (missing ones fall back with a note). Element keys come from
  `describe.elements` (each with its `group` and, for texts and named elements, the full `raw` text):
  `<axes>.<kind><n>` in drawing order, or `<axes>.<kind>:<legend label>` for named elements (numbers in the label
  become `#`, so they survive new data); `f.text<n>` for figure texts. `describe.groups` counts the elements per kind.
  `describe.now` adds the axes boxes in the saved image, so the editor can turn a box dragged on the preview into axis
  limits. Values are checked and clipped; unknown keys are ignored. A module needs nothing beyond `add_figure` and
  passing the request on.
- **Preview of the editing window.** With `source.request.preview = {item, svg}` the SDK draws only figure `item`, no
  PDF: an SVG with texts kept as text and element ids (`describe.now.gids`, element key → SVG ids, `@xlabel<i>` and
  `@ylabel<i>` for axis labels), or a PNG when `svg` is false. The window changes colours, visibility, widths, line
  styles, sizes and plain texts in that SVG at once and asks the module for the exact drawing after a short pause; the
  hub keeps the last 40 previews in memory, so going back to an earlier state costs nothing.

## 4. What the hub does with it

`POST /api/projects/<id>/lab[?mode=replace|new]` stores the bundle in the report project:

| Path in the project | Content |
|---|---|
| `lab/<slug>/` | the bundle files, `bundle.json` (manifest without base64) and `source/` (raw measurement files) |
| `lab/references.bib` | all bundles' `refs.bib`, de-duplicated by key (regenerated) |
| `lab/labdata.tex` | `\labset`/`\labval` and an `\input` of every bundle's `values.tex` (regenerated) |

Other endpoints: `GET /api/projects/<id>/lab` (list; each entry has `refs` = shares and index values it uses),
`POST .../lab/<slug>/refresh` (body `{lang?}`), `DELETE .../lab/<slug>[?section=1]`, `GET /api/modules`,
`POST /api/modules/<id>/start|stop`. All non-GET `/api` calls need the header `X-Folio: 1`.

Revisions and provenance: every replace or Refresh moves the previous revision to
`lab/<slug>/history/<n>/`; the manifest carries `result_id`, `revision`, `provenance` (Folio Lab version from `package.json`,
module ID and version from `module.json`, SHA-256 of every source file, action) and `issued`. Endpoints `.../lab/<slug>/revisions`, `compare`,
`restore`, `issue` and `GET .../lab/<slug>/history` (result info, source hashes, and for shared inputs and index values
the chain from the producing module's `/api/prov/report`; `chains_error` when that module cannot answer). The ZIP
export adds `lab/dependencies.json` (`folio-lab-dependencies/1`) and marks current revisions issued.

Suite: `GET /api/suite`, `POST /api/suite/projects`, `PATCH /api/suite/projects/<pid>` (e.g.
`{addReport}`) and `POST /api/suite/active` for projects;
`GET /api/suite/envs` returns the active environment per module for the start-page cards. Modules are started with
`FOLIO_SUITE_DIR` and read the same `projects/_suite/` folder.

The hub never edits the user's own `.tex` files. The editor's **Lab** button adds, the first time something is
inserted, `\input{lab/labdata}`, the needed packages (`graphicx`, `booktabs`, `pgfplots`) and the bibliography hookup
(`\addbibresource{lab/references.bib}` or `lab/references` in `\bibliography{...}`) to the main file.

**Refresh** recomputes a result from its stored source files with the current module version (or in the other
language). Figures, tables, `\labval` values and *linked* text (`\input{lab/<slug>/text-...}`) update; captions and
*editable* text that were pasted into the user's files stay as the user left them. **Insert results section** writes
`sections/<slug>.tex` once; that file belongs to the user afterwards.

**Choosing what is shown, and variants.** An import keeps the whole bundle in `lab/<slug>/`; the manifest field
`pick {items, values, methods}` says what was chosen, and pieces not chosen carry `hidden: true` (the Lab dialog lists
them under "Also in this result"). `POST .../lab/<slug>/pick` `{items?, values?, methods?}` changes the choice without
recomputing (`methods`: `{mode: full|short|custom|none, steps, eq, edits {step: {text, orig}}}`). An edited sentence
replaces the module's wording in every mode where that step is shown (the item gets `edited_steps`); when a later
Refresh changes the module's sentence (`orig` no longer matches), the item gets `edited_changed` and a warning, and the
user's wording is kept. A **variant** (fork) is a styled or edited copy of
one figure, table or text, stored as its own result:

- `POST .../lab/<slug>/preview` `{item, style}` returns `{png, describe, style, caption}`: the module redraws the
  figure; nothing is saved.
- `POST .../lab/<slug>/fork` `{item, style?, caption?, text?, table? {hide: [column index], digits}, mode:
  live|snapshot, title?, target?}` saves the variant (manifest field `fork {of, item, kind, mode, style, caption, text,
  table, created}`, own label `fig:`/`tab:` + its slug). With `target` (or when `<slug>` is itself a variant) it
  updates that variant in place as a new revision. Table variants hide columns and round numbers with decimals
  (integers stay); tables with `\multicolumn` or rules in the column layout cannot lose columns.
- `GET .../lab/<slug>/forks` lists the variants of a result. A **live** variant is rebuilt from its original's
  current source on every Refresh of the original; a **snapshot** keeps its own stored source and is refreshed only on
  its own. A figure can be restyled only if its result has a stored source (not for copies from other reports).
- A figure variant can carry `place {width: 0.1..1|"full", pos: htbp|h|t|b|p|H, align: center|left|right}` (where it
  sits in the document). The editor applies it to every float in the user's `.tex` files that shows that figure
  (`figure*` for full width); `lab/labdata.tex` loads `float` when a variant uses `H`.

**Removing a result as a unit.** `GET .../lab/<slug>/uses-info` returns what the editor needs to find the result in
the user's text: `labels`, `keys` (citation keys no other result and no own `.bib` file provides), `shared_keys`,
`values`, `numbers {label: {num, page}}` from the `.aux` files of the last compile, `section` and `variants`. The
editor (`public/js/editor/labuses.mjs`, `findUses`) lists every place: floats and `\input` lines of the result and its
results-section `\input` are removed, `\labval` values and references to its labels are frozen as
`\labstale[<slug>]{<printed text>}` (prints the text with a dagger; `??` if never compiled), and its citation keys are
dropped from `\cite` lists. After the user confirms, the editor saves the changed files and calls
`DELETE .../lab/<slug>?section=1`, which moves the result (and `sections/<slug>.tex`) into the project's bin
`lab-bin/<slug>-<time>/` and returns `{kept, undo}`. An issued result is also kept in `lab/_removed/` as before.
`POST .../lab-undo {undo}` brings the result back; the editor restores the text. Bin entries older than 14 days are
deleted on the next removal. The same flow runs from the Lab dialog, from deleting `lab/<slug>` in the file tree and
from the citation picker, where a result's references are grouped under it.

**Import into a report** (no module involved): `GET /api/import/sources?target=<id>`,
`GET /api/import/pieces?type=report|zip|suite&project=|stage=`, `POST /api/import/stage?name=` (raw ZIP),
`POST /api/projects/<id>/import` `{source: {type, project|stage}, keys, mode: live|pin|copy}`,
`GET .../import/links`, `POST .../import/<slug>/update` and `.../import/<slug>/mode`. The hub writes an ordinary
bundle with module `import` (items figure/text/values/data/citation, `refs.bib`, `values.tex`, and `preamble.tex` for
the macros and packages the pieces need, which `lab/labdata.tex` inputs) and a manifest field `link`. A whole analysis
result is copied with its own module, so its Refresh still goes to that module. Refresh of an `import` bundle is the
same as Update. `GET /api/projects/<id>/zip?portable=1[&prefix=]` writes the portable LaTeX ZIP (see
`docs/methods/provenance.md`, section 6).

## 5. Own references, own equations, sources

Every module that compares a measurement with reference data lets the user add references that are not bundled, and
every module with measured values lets the user add equations. FTIR, Zugversuch and TGA follow the same conventions;
a new module should too.

**Source record (`sdk/python/labcite.py`).** A source is a dict, never a free-text string:
`{type, authors, title, container, year, volume, issue, pages, doi, url, accessed, note, licence}` with `type` one of
`article`, `book`, `chapter`, `standard`, `datasheet`, `web`, `thesis`, `report`, `dataset`, `misc`.

```python
import labcite
labcite.errors(rec)                      # [] = ok; title, DOI or URL required, DOI/URL/date syntax checked
rec = labcite.clean(rec)                 # trims, normalises the DOI, drops unknown fields
key = labcite.to_bib(b, "ref-" + slug, rec)   # adds @article/@book/@manual/@online/... to the bundle, returns the key
labcite.short(rec)                       # "Müller u. a. 2021" for figure labels
labcite.text(rec)                        # full reference as one line (export files, tooltips)
labcite.from_legacy("Some free text")    # wraps old string sources so existing data keeps working
```

**Source form in the page (`sdk/web/labref.js`).** Serve it from the module at the relative path `labref.js`
(`labcite.web_asset("labref.js")`) and load it with `<script src="labref.js">`, so it works standalone and under
`/m/<id>/`. `LabRef.form(rec)` returns the HTML for the module's own dialog (type, authors, title, journal/publisher,
year, pages, DOI/URL, note, and "BibTeX einfügen", which fills the fields from a pasted entry); `LabRef.read(root)`
reads it back, `LabRef.errors(rec)` validates it. Check on the server again before saving.

**Persistence (`sdk/python/labuser.py`).** User data lives as readable JSON in the module's outputs folder, so it is
open, versionable and editable by hand:

```python
from labuser import JsonStore
eqs = JsonStore(out_root / "eigene_gleichungen.json", kind="folio-gleichungen/1")
eqs.items(); eqs.put(item); eqs.delete(id); eqs.export(); eqs.import_(data, replace=False)
```

Own references go to a `JsonStore` file (Zugversuch: `eigene_werkstoffe.json`, endpoints `/api/own/*`) or, where
the module has library folders, to a library "Eigene Referenzen" under `outputs/<id>/bibliotheken/` (FTIR, TGA). Offer *Export* and *Import* (JSON) so sets can
be shared.

**Own equations (`sdk/python/labcalc/formulas.py`).** An equation is `{sym, label, expr, unit, digits, source?}`.
The module exposes its measured values as variables (`{name: {value, unit, label}}`) and optionally functions (FTIR
`A(nu)`, `area(nu1, nu2)`; TGA `m(T)`, `dtg(T)`, `loss(T1, T2)`):

```python
from labcalc import formulas as F
results = F.evaluate(defs, variables, functions)   # in order, later equations may use earlier ones; units checked;
                                                    # an error stays on its row and never stops the analysis
out = F.to_report(b, results, lang)                 # \labval eq-<sym>, a table, display math; cites each source
methods_tex += out["latex"]
```

Endpoints, same in every module: `GET /api/equations/list`, `POST /api/equations/save|delete|export|import`.
The expression language, units and LaTeX rendering are the Rechner's (`labcalc.expr`, `labcalc.units`,
`labcalc.render`); `modules/rechner/rechner/{expr,units,render}.py` are shims onto them.

**Sources of constants and textbook equations (`sdk/python/labcalc/sources.py`).** `REFS` holds the structured
records (CODATA 2022, SI Brochure, IUPAC Green Book, standard textbooks, ISO standards); `CONSTANT_SOURCES` names the
source of every constant in `labcalc.units`, and `units.constants_list()` returns it with each constant. Cite them with
`labcite.to_bib(b, "rf-" + key, sources.REFS[key])`. A new constant or library equation without a source fails the
Rechner tests.

**Materials database (`sdk/python/labcalc/materials.py`, `labcalc/data/materials.json`).** One sourced list of material
properties for every module (the Rechner, the Zugversuch and the Werkstoffe module). Use
`materials.value(name, prop)` (SI value, value kind, range, source key or record, "not checked" note),
`materials.get(name, prop)` (SI float), `materials.search(q, klasse, prop)` and `materials.card(name, lang)`; cite a
value with its `key` from `sources.REFS` or, when `key` is `None`, with `labcite.to_bib` on its `source` record (the
Rechner uses `labcite.key_for("mw", source)`). Never copy values into a module's own file; add or correct them in the
database (`materials.validate()` must stay empty, `sdk/python/tests/test_materials.py`). Optional parts
(`data/optional/materials_*.json`, e.g. the Materials Project part) are appended without replacing curated entries.

**Report rules.**

- A figure or table that draws a user reference passes its key in `cites=[...]`, and the reference is labelled in the
  figure with `labcite.short(rec)`, like bundled references.
- `source.request` stores the **full records** that were used (reference values and curve, equation definitions,
  source records), not just their ids. *Refresh* then rebuilds the same report even after the user edits or deletes
  the reference or equation.
- Modelled reference data (FTIR and TGA model libraries) is labelled "modelled, not measured" in the UI, in the figure
  label, in its citation and in the methods text.

### Measurement uncertainty

Every module lets the user attach an uncertainty to a measured or entered value and carries it into results, shared
values, the project index and the report. The calculations live in `sdk/python/labcalc/uncertainty.py`; the server
routes and the suite's own instruments in `sdk/python/labunc.py`; the page parts in `sdk/web/labunc.js`.

**Inputs.** An uncertain input is `{"name", "value", "unit", "label", "parts": [...]}`. Each part is one contribution,
and the parts add in quadrature:

| `kind` | Fields | Standard uncertainty |
|---|---|---|
| `u` | `u`, optional `dof` | as given |
| `U` | `U`, `k` (default 2) | U/k |
| `limits` | `a`, `dist` (`rect`, `tri`, `arcsine`, `normal` = 3σ) | a/√3, a/√6, a/√2, a/3 |
| `resolution` | `d` | d/(2√3) |
| `rel` | `pct`, `dist` | pct % of the value, then as `limits` |
| `spec` | `pct`, `digits`, `d` | (pct % · \|x\| + digits · d)/√3 |
| `repeats` | `values` | s/√n, n − 1 degrees of freedom (type A) |
| `sd` | `sd`, `n` | s/√n (type A) |
| `ci` | `half`, `level`, `n` | half / t |
| `instrument` | `id`, optional `params` | from `labcalc/data/instruments.json` or the suite's `messmittel.json` |

A value without parts is exact. Every built-in instrument names its source (a standard in `labcalc/sources.py`).

**Methods.** `UN.evaluate(model, inputs, method, corr=None, p=0.95, k=None, unit=, label=, name=)` with `method` one
of `gum`, `mc`, `gauss`, `worst`. `UN.compare(...)` runs all four. The model is a Python function of a dict of values
that should accept numpy arrays (Monte Carlo is then vectorised), or `{"expr": "F/(pi*d^2/4)"}`. A scalar-only model
still works, but Monte Carlo then stops at 4000 trials and says so. Correlations are optional:
`[{"a": "x1", "b": "x2", "r": 0.5}]`. The result is JSON with `value`, `u`, `U`, `k`, `lo`, `hi`, `budget`,
`notes`, `note_texts`, `text`, `refs`, `refs_full`.

**In a module.**

1. Server: add `"/labunc.js"` to the served SDK files, and route
   `if p.startswith("/api/unc/"): return self._json(labunc.route(STATE.envs, p.rsplit("/", 1)[1], self._req()))`.
   Call `labunc.load_own(envs)` before evaluating if an input may name an own instrument.
2. Page: `<script src="labunc.js">`. Use `LabUnc.attach(input, {key, label, unit})` next to every numeric input that
   holds a measured or entered value. Keep `LabUnc.all()` in the saved state and the request, and restore it with
   `LabUnc.load(state.unc)`. Offer `LabUnc.methodPicker` once per module (the method is part of the state), and show
   results with `LabUnc.result(el, res, {compare})`.
3. Results: every result that depends on an uncertain input gets an uncertainty from the chosen method. Show it as
   "value ± U" with the budget in a fold. A result whose model is a whole curve evaluation (a fit, a peak search)
   gets a model the module writes down explicitly (e.g. `Rm = Fmax/S0`). Otherwise it gets the fit's own parameter
   uncertainty, labelled as such.
4. Carrying: the value catalogue sends `u` (standard uncertainty) and `unc` (method name) with each value.
   `labcalc.formulas.evaluate` propagates `u`/`unc` of variables into own equations. `merge_ext` keeps `u` of incoming
   values. Project-index entries take `quantity.u`.
5. Report: `UN.to_report(b, results, lang, prefix)` writes `\labval{slug}{<name>-pm}` (value ± U), `-u`, `-U`, a
   budget table `<name>-budget` and a methods sentence. It cites the method (JCGM 100/101, DIN 1319-4, Taylor) and
   every instrument's source. Keep the inputs' specs in `source.request`, so Refresh reproduces the same numbers. Monte
   Carlo uses a fixed seed.

## 6. Checklist for a new module (e.g. FTIR)

1. `modules/ftir/module.json` with `"status": "ready"` and a runtime.
2. A server with `GET /` (page), a health path, the module's own API, `POST /api/bundle` and `POST /api/bundle/rebuild`.
3. `requirements.txt`, then run `setup.ps1`.
4. In the page: relative URLs, `<script src="/lab/sdk.js">`, a button calling `Lab.sendToReport`.
5. Tests next to the module (`modules/ftir/tests`). Two reference implementations:
   - `modules/zugversuch`: `flps/bundle.py` (bundle), `flps/ui/server.py` (endpoints), `flps/ui/static/index.html` (button).
   - `modules/mikroskopie`: an image module whose `source.request` is a recorded processing protocol plus the
     selections and particle settings (`mikro/analysis.py` replays it for the UI, export and bundle alike);
     `mikro/bundle.py`, `mikro/server.py`, `mikro/static/index.html`. It also shows binary pixel transfer to the page
     (`/api/pixels`) and a multi-image comparison bundle.
   - `modules/rechner`: a module without input files. The page holds the whole working state and sends it with every
     request (stateless server); `source.request` is that state and `source.files` is empty. `rechner/bundle.py` shows
     text blocks with display math (`\[ … \]`, no amsmath) and values built from user-defined quantities.

## 7. Shared page parts and project features (`sdk/web`, `sdk/python`)

Every module server serves these files from `sdk/web` at its own root (`labcite.web_asset(name)`), so they work
standalone and under `/m/<id>/`.

| File | What it gives a page | Server side |
|---|---|---|
| `labui.js` | `LabUI.strings/t/apply/langSwitch` (German, English switch, `data-i18n`, `data-i18n-title`, `-placeholder`, `-label`); `LabUI.folds(prefix)` remembers `<details class="lab-fold" data-fold>`; `LabUI.popover(anchor, html)` (fixed in the viewport: below, or above when there is more room; height capped with inner scrolling; closes on outside scroll, Esc, a click outside or a width change); `LabUI.tasks(el, [{id,label,hint,act}])` task entry list; `LabUI.chip(kind, text)` with kinds ok/warn/err/info/live; `LabUI.actions({source, method, history})` small Quelle/Methode/Herkunft buttons opening popovers | none |
| `labenv.js` | `LabEnv.create({...})`: environments dialog, autosave of the page state, restore after restart; optional `summary()` for the board; `refresh/switchTo/createNew/rename` without the dialog. A page that reloads in `done` must return `"reload"` so the old state is not saved into the new environment | `labproject.ModuleEnvs.route` at `/api/env/*` |
| `labindex.js` | `LabIndex.add/addMany/browse` (project index, alternatives), `LabIndex.history(ref)` (chain to the raw file), `LabIndex.exportDeps` | `labindex.route` at `/api/index/*`, `labprov.route` at `/api/prov/*` |
| `labref.js` | source record form | – |
| `labboard.js` | `LabBoard.create(el, {boxes, pos, links, onOpen, onLink, onUnlink, onMove, wireLabel, wireHint})`: overview board with draggable boxes (columns 0 shared inputs / index, 1 environments, 2 own results), click or Enter opens a box, wires drawn from an output port onto a box with an input; below 700 px a plain list (links then only via the drop-downs). Only dragged boxes keep a position (`onMove` gets just those); `float: true` boxes are never stored and stay last in their column | `ModuleEnvs.route("board")` at `/api/env/board`: `{pos, links}` per module and project in `env/<module>/_board.json` |
| `laboverview.js` | `LabOverview.create({api, toast, module, envs, detail, crumbs, word, envHtml, incoming, index, onView})` → `{start, showBoard, showDetail, sync}`: start view with the project index, shares addressed to the module (popover: kind, producer, version, read-only note, optional module action from `incoming[kind]`, "Herkunft …"), the environments (box content from `LabEnv` `summary`) with "+ Umgebung", and own shares wired to their environment. `detail` elements and anything marked `data-lov-detail` are hidden on the board; "◂ Übersicht" crumb and the Back button return (`#uebersicht`/`#umgebung`). Needs `labui.js`, `labboard.js`, `labenv.js`; returns `null` without them | `ModuleEnvs.route("shares")` at `/api/env/shares` (heads only: incoming and own) and `route("share")` at `/api/env/share` (one envelope, only if addressed to or produced by the module) |

**Board model.** The overview of a module shows its environments as boxes, the share boxes it reads
(read-only: only the owner module changes a share) and the shares it produces. A wire from a share to an environment
*is* the binding (mode pin/live/copy, as in "Geteilte Eingabe …"); a wire from an environment to a share means
"produced by". The drop-down and the wire write the same link, so either view can be used. Each environment stores a
short `summary` (≤ 48 KB) in its client state; the server copies it into the manifest so the overview can show all
environments without loading them. Tools are imported into an environment on demand (none on by default) and appear
in its detail view as titled cards.

**Graphs in the box.** A summary may carry `plots: [{title, xlab, ylab, xrev?, view?: [x0, x1, y0, y1],
series: [{name, x, y, bar?, pts?}]}]`. The box shows small graphs; a click opens an enlarged graph with axes,
legend and ‹ › paging. Pass the plots through `LabBoard.packPlots(plots, n)` (≤ 4 plots, ≤ 4 series, ≤ n points per
series by min/max decimation, `null` keeps a gap, 4 significant digits). `LabEnv` calls `fitSummary` on every
snapshot and thins or drops plots until the summary fits. The Elementrechner draws its own board and passes `plots`
to `LabBoard` itself. `LabBoard.plotsHtml(plots)` and `LabBoard.showPlot(plots, i, anchor)` are exported for other
places.

**Environment → environment (Elementrechner).** A wire between two environment boxes (kind `env.values`,
fields `mode` live|copy, `keys`, `share`, `version` for copy) passes chosen values. The source publishes one share
per environment (`chem.envvalues`, new version only on change); the summary carries a value catalogue
(`values: [{sym, label, value, unit, kind}]`) so values can be picked without opening the source. The same link is
made with ⇄ next to a result, on the board or in the header drop-down "Verbindungen".

**Environment → environment in every module (`laboverview.js`).** The same model for all modules that use the
shared overview. `LabOverview.create` takes two more options:

- `values: {catalogue(), apply(rows), version}` – the values channel. `catalogue()` returns the open environment's
  numeric values `[{sym, label, value, unit, kind}]`; `apply(rows)` receives the incoming values
  `[{key, label, value, unit, kind, from, from_name, share, version, mode}]`. The overview publishes through
  `/api/env/envvalues` (`ModuleEnvs.publish_env_values`, kind `lab.envvalues`, recipient = the module, new version only
  on change) and fetches the bound versions for `apply`.
- `channels: [{kind, label(n), offers(env), link(...), apply(links), baseKey, keyLabel}]` – further channels, e.g.
  the Datenaufbereitung's `env.datasets` (key = share ID for live, `ID@version` for a copy).

The returned object adds `share(anchor, key, kind)` (popover: target environment, live or snapshot),
`shareButton(key, kind)` (the ⇄ button HTML; empty when there is no second environment), `connMenu(anchor)` (the
"⇄ Verbindungen" menu), `changed()` (republish 1,5 s after a recalculation) and `links()`. Helpers:
`LabOverview.summaryValues(list)` (≤ 80 values, ≤ 24 KB, for `LabEnv` summaries), `runsCatalogue(runs)` (values of
modules with several runs: run 1 keeps the name, later runs get `_2`, `_3`; incoming values are not passed on) and
`extValues(prev, rows)` (incoming rows as the server list `ext_values`; `changed` says whether to recompute). Modules
with own equations merge incoming values with `labcalc.formulas.merge_ext(variables, ext_values, reserved)`: an
incoming key never overwrites an own variable, a taken name becomes `<key>_ext`.

**Datasets (`labdataset.py`, share kind `data.table`).** A dataset (`suite.dataset/1`) is a table of equal-length
columns (`key`, `name`, `symbol`, `kind`, `unit`, `dtype`, `role`, `u` → uncertainty column, `note`) with
`conditions`, `flags` (`row`, `col`, `code`, `reason`, `excluded`; flags never remove rows) and `provenance` (files
with SHA-256 and ranges, recipe, cleaning steps with counts, parent dataset). `Sharebox.publish_dataset` stores the
header in the envelope and the values in a `.npz` sidecar; `labshare.dataset_of(envelope, folder)` reads it back.
Useful methods: `used_mask()` (rows not excluded), `si(key)` and `in_unit(key, unit)` (converted columns, optionally
`used_only`), `page(r0, r1)`.
Producers are the Datenaufbereitung (recipients: Rechner, Elementrechner, TGA, FTIR, Datenaufbereitung); a consumer
lists `Sharebox.list(recipient=<module>, kind="data.table")`, binds `{id, mode: live|pin, version}` and resolves it on
use, never storing the values in its own state. Rules every consumer follows: convert with `labcalc.units` into the
unit it needs and refuse a wrong dimension; drop excluded rows (and incomplete rows across the chosen columns); name
the dataset ID and version in the result, the methods text and the bundle's `source.request` (retention).
`tools/e2e_datasets.py` runs the whole flow across the modules in a temporary folder.

**Import window (`sdk/web/labimport.js`).** Every module may read every `data.table` share of the project; the
recipients only sort "für dieses Modul" first. `/api/env/datasets` lists them (`for_me`, columns, rows, latest
version) and `/api/env/dataset {id, version?}` gives the preview (versions, column ranges, first rows, thumbnail).
A module wires it through `LabOverview.create({..., imports: {actions, check, run}})`:
- `actions`: buttons in the window, e.g. Rechner `graph` / `vars`, Zugversuch `test`, Mikroskopie `cmp`;
- `check(dataset)` returns "" or a short reason; the dataset stays selectable and shows "Passt nicht: …";
- `run(pick)` does the import. `pick` = `{id, title, latest, mode: live|pin, version, rows, columns, producer, for_me,
  action, env}`.
`OV.importDataset({select?})` opens it from the page; the overview's import button adds a target environment (an
existing one or a new one by name), switches or creates it, shows the environment and then calls `run`. Without a hub
(`OV.ok` false) a module keeps its old dataset list.

Python side: `labshare.Sharebox` (typed, versioned shares; `publish`, `list`, `get`, `resolve` pin/copy/live,
`delete` guarded), `labdeps` (order, cycles, stale), `labindex.ProjectIndex`, `labprov` (chain, report references,
retention guards, dependency list).

Rules for module pages:
- View settings (language, open sections) may live in `localStorage`; work never does (use `LabEnv`).
- New sections start folded; long explanations go into a popover, not into the page.
- Status words are chips (`LabUI.chip`), not coloured free text.
- Every user-visible string goes through `LabUI.t` with a German and an English entry; German is the default.
- A value that came from elsewhere shows where from (origin line or `LabUI.actions({history})`).
- Every region the user looks at can be resized by dragging an edge. Call `LabUI.sizes("<prefix>")` once the page is
  built (it may be called again after inserting new elements; wired elements are skipped). Mark the regions:
  - side columns: `data-size-col="<name>"` on a panel inside a grid/flex container, and use `var(--lab-<name>, <px>)`
    for that column in the CSS (the helper sets the variable on the container; the handle sits on the panel's inner
    edge, or on `data-size-edge="left|right"`);
  - heights: `data-size-h="<name>"` on charts, tables, lists and previews (`data-size-mode="max"` sets `max-height`
    for scrolling tables and lists, so short content stays short);
  - `<dialog>` elements are resizable at their right edge, bottom edge or corner without markup; other floating windows
    get `data-size-win="<name>"`.

  Sizes are stored per page as fractions of the window or the surrounding area, so a layout keeps its proportions on
  another screen. Double-click or Home on a handle resets it, arrow keys move a focused handle, and
  `LabUI.resetSizes(prefix)` clears all of them. Charts that draw at their box size redraw through `LabUI.onResize(el, fn)`.
- First user: the Elementrechner (language switch in the header, chips in "Geteilte Eingabe …").
