// Folio Lab in the editor: browse the analysis results stored in this project (lab/<slug>/) and insert
// figures, tables, values, data plots, citations and text. The main file gets the few lines it needs
// (\input{lab/labdata}, packages, bibliography) the first time something is inserted.
import { api, fileUrl, esc, h, icon, modal, confirmBox, toast, store } from '../ui.js';
import { openCustomise } from './customise.js';
import { figureFloat, placeFloat, floatsWith, findUses, plainTex } from './labuses.mjs';

let ctx; // { projectId, project(), editor(), insertSnippet, snipEsc, ensurePackage, ensureTexEditor, getModel, refreshFiles, reloadFromDisk, monaco() }

export function initLab(c) {
  ctx = c;
}

const KIND_LABEL = { figure: 'Figures', table: 'Tables', values: 'Values', data: 'Data', citation: 'References', text: 'Text blocks' };

/** LaTeX snippet text -> readable plain text for lists. */
function plain(s) {
  return String(s ?? '')
    .replace(/~?\\cite\{[^}]*\}/g, '')
    .replace(/\\,/g, ' ')
    .replace(/\\([%&#_$])/g, '$1')
    .replace(/\\textdegree\{\}/g, '°')
    .replace(/\$\\sigma\$/g, 'σ')
    .replace(/\$\\varepsilon\$/g, 'ε')
    .replace(/\$\\Delta\$/g, 'Δ')
    .replace(/\$-\$/g, '−')
    .replace(/[_^]\{([^}]*)\}/g, '$1')
    .replace(/_([A-Za-z0-9])/g, '$1')
    .replace(/[{}$]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}
const texEsc = (s) =>
  String(s ?? '').replace(/[\\&%$#_{}~^]/g, (c) => ({ '\\': '\\textbackslash{}', '~': '\\textasciitilde{}', '^': '\\textasciicircum{}' })[c] || '\\' + c);

// ---------------------------------------------------------------- main-file wiring
async function mainModel() {
  try {
    return (await ctx.getModel(ctx.project().mainFile)).model;
  } catch {
    return null;
  }
}

function insertBefore(model, re, text) {
  const src = model.getValue();
  const idx = src.search(re);
  if (idx < 0) return false;
  const pos = model.getPositionAt(idx + (src[idx] === '\n' ? 1 : 0));
  const monaco = ctx.monaco();
  model.pushEditOperations([], [{ range: new monaco.Range(pos.lineNumber, 1, pos.lineNumber, 1), text }], () => null);
  return true;
}

/** Make sure the main file loads what inserted pieces need. need: {graphics, tables, plot, cite} */
async function ensureWiring(need = {}) {
  const model = await mainModel();
  if (!model) return;
  const monaco = ctx.monaco();
  const added = [];
  let src = model.getValue();
  if (!/\\begin\{document\}/.test(src)) return;

  if (!/\\input\{\s*lab\/labdata(\.tex)?\s*\}/.test(src)) {
    insertBefore(model, /^\s*\\begin\{document\}/m, '% Folio Lab: values from analyses, used as \\labval{<result>}{<key>}\n\\input{lab/labdata}\n\n');
    added.push('\\input{lab/labdata}');
  }
  if (need.graphics) await ctx.ensurePackage('graphicx');
  if (need.tables) await ctx.ensurePackage('booktabs');
  if (need.plot) await ctx.ensurePackage('pgfplots', '\\pgfplotsset{compat=1.18}');

  if (need.cite) {
    src = model.getValue();
    if (/lab\/references/.test(src)) {
      /* already wired */
    } else if (/\\addbibresource\{[^}]*\}/.test(src)) {
      const all = [...src.matchAll(/\\addbibresource(\[[^\]]*\])?\{[^}]*\}[^\n]*\n?/g)];
      const last = all[all.length - 1];
      const pos = model.getPositionAt(last.index + last[0].length);
      const line = last[0].endsWith('\n') ? pos.lineNumber : pos.lineNumber + 1;
      const text = last[0].endsWith('\n') ? '\\addbibresource{lab/references.bib}\n' : '\n\\addbibresource{lab/references.bib}';
      model.pushEditOperations([], [{ range: new monaco.Range(line, 1, line, 1), text }], () => null);
      added.push('\\addbibresource{lab/references.bib}');
    } else if (/\\bibliography\{([^}]*)\}/.test(src)) {
      const m = /\\bibliography\{([^}]*)\}/.exec(src);
      const start = model.getPositionAt(m.index);
      const end = model.getPositionAt(m.index + m[0].length);
      const inner = m[1].trim();
      model.pushEditOperations(
        [],
        [{ range: new monaco.Range(start.lineNumber, start.column, end.lineNumber, end.column), text: `\\bibliography{${inner ? inner + ',' : ''}lab/references}` }],
        () => null
      );
      added.push('lab/references to \\bibliography');
    } else {
      insertBefore(model, /^\s*\\begin\{document\}/m, '\\usepackage[backend=biber,style=numeric,sorting=none]{biblatex}\n\\addbibresource{lab/references.bib}\n');
      if (!/\\printbibliography/.test(model.getValue())) {
        // The cursor usually sits right at \end{document} after the first insert; keep it before the bibliography so
        // the next figure does not land behind it.
        const ed = ctx.editor();
        const keep = ed && ed.getModel() === model ? ed.getPosition() : null;
        insertBefore(model, /^\s*\\end\{document\}/m, '\n\\printbibliography\n');
        if (keep) ed.setPosition(keep);
      }
      added.push('biblatex with lab/references.bib');
    }
  }
  if (added.length) toast(`Added to ${ctx.project().mainFile}: ${added.join(', ')}`, 'info', 4500);
}

/** "· cites 3 sources" under a figure/table whose caption carries the sources of the data it shows. */
function srcHint(it, block = false) {
  const n = (it.cites || []).length;
  if (!n) return '';
  const text = `cites ${n} source${n === 1 ? '' : 's'} automatically`;
  return block ? `<span class="hint lab-src" title="${esc(it.cites.join(', '))}">${text}</span>`
    : ` <span class="hint" title="${esc(it.cites.join(', '))}">· ${text}</span>`;
}

/** "Short: 4 of 12 sentences" for a methods text with steps. */
function stepInfo(it) {
  const st = (it.steps || []).filter((s) => !s.eq && !s.brief);
  if (!st.length) return '';
  if (!it.shown_file) return `all ${st.length} sentences${(it.steps || []).some((s) => s.eq) ? ' + equations' : ''}`;
  const on = new Set(it.shown_steps || []);
  return `${(it.steps || []).filter((s) => !s.eq && on.has(s.id)).length} of ${st.length} sentences${(it.steps || []).some((s) => s.eq && on.has(s.id)) ? ' + equations' : ''}`;
}

/** Figures, tables, data and text blocks of a result (the shown ones, or the hidden ones in their fold). */
function pieces(b, list) {
  const of = (k) => list.filter((i) => i.kind === k);
  const figs = of('figure');
  const tabs = of('table');
  const data = of('data');
  const texts = of('text');
  return `${figs.length ? `<h4>${KIND_LABEL.figure}</h4><div class="lab-figs">${figs.map((it) => `<div class="lab-figbox">
        <button class="lab-fig" data-fig="${esc(it.id)}" title="Insert figure">
          <img loading="lazy" src="${esc(fileUrl(ctx.projectId, `lab/${b.slug}/${it.preview || it.file}`))}&v=${encodeURIComponent(b.updated)}" alt="">
          <span class="cap">${esc(plain(it.caption))}</span>${srcHint(it, true)}</button>
        <button class="btn xs lab-cus" data-cus="${esc(it.id)}" title="Journal layout, size, colours, axes, caption: saved as a variant, the original stays">Customise…</button></div>`).join('')}</div>` : ''}
      ${tabs.length ? `<h4>${KIND_LABEL.table}</h4><div class="lab-rows">${tabs.map((it) => `
        <div class="lab-row"><span class="grow">${esc(plain(it.caption))}${srcHint(it)}</span>
          <button class="btn sm ghost" data-cus="${esc(it.id)}" title="Columns, decimals and caption: saved as a variant, the original stays">Customise…</button>
          <button class="btn sm" data-tab="${esc(it.id)}">${icon('table')}Insert table</button></div>`).join('')}</div>` : ''}
      ${data.length ? `<h4>${KIND_LABEL.data}</h4><div class="lab-rows">${data.map((it) => {
        const cols = it.columns || [];
        const lbl = it.labels || {};
        const numeric = cols.filter((c) => c !== 'phase' && (!Object.keys(lbl).length || (lbl[c] && c !== 'phase')));
        const opt = (sel) => numeric.map((c) => `<option ${c === sel ? 'selected' : ''}>${esc(c)}</option>`).join('');
        const defX = (it.plot && it.plot.x) || numeric[0];
        const defY = (it.plot && it.plot.y) || numeric[1];
        return `<div class="lab-row" data-row="${esc(it.id)}"><span class="grow">${esc(plain(it.description))} <span class="hint">${it.rows || ''} rows</span></span>
          <label class="hint">x <select class="input sm" data-x>${opt(defX)}</select></label>
          <label class="hint">y <select class="input sm" data-y>${opt(defY)}</select></label>
          <button class="btn sm" data-plot="${esc(it.id)}">${icon('chart')}Plot</button>
          <a class="btn sm ghost" href="${esc(fileUrl(ctx.projectId, `lab/${b.slug}/${it.file}`, true))}" title="Download CSV">${icon('download')}</a></div>`;
      }).join('')}</div>` : ''}
      ${texts.length ? `<h4>${KIND_LABEL.text}</h4><div class="lab-rows">${texts.map((it) => `
        <div class="lab-row"><span class="grow">${esc(it.title)}${(it.steps || []).length ? ` <span class="hint">${esc(stepInfo(it))}</span>` : ''}</span>
          ${(it.steps || []).length ? `<button class="btn sm ghost" data-steps="${esc(it.id)}" title="Choose the sentences of the methods text: Short, Full or your own ticks; the full text stays in the folder">Steps…</button>` : ''}
          <button class="btn sm ghost" data-cus="${esc(it.id)}" title="Edit the text as a variant that keeps your wording on Refresh; the original stays">Customise…</button>
          <button class="btn sm" data-text="${esc(it.id)}" title="Paste the paragraph so you can edit it">${icon('edit')}Insert editable</button>
          <button class="btn sm ghost" data-textin="${esc(it.id)}" title="\\input the file; it changes when the results are refreshed">${icon('link')}Insert linked</button></div>
        ${(it.steps || []).length ? `<div class="lab-steps" data-stepbox="${esc(it.id)}" hidden></div>` : ''}`).join('')}</div>` : ''}`;
}

// ---------------------------------------------------------------- snippets
function figureTex(b, it, width) {
  return figureFloat({ path: `lab/${b.slug}/${it.file.replace(/\.pdf$/i, '')}`, caption: it.caption, label: it.label, width: width || it.width, place: b.fork && b.fork.place });
}
function tableTex(b, it) {
  const notes = it.notes ? `\t\\par\\smallskip{\\footnotesize ${it.notes}}\n` : '';
  return `\\begin{table}[htbp]\n\t\\centering\n\t\\caption{${it.caption}}\n\t\\label{${it.label}}\n\t\\input{lab/${b.slug}/${it.file.replace(/\.tex$/i, '')}}\n${notes}\\end{table}\n`;
}
function plotTex(b, it, x, ys, xl, yl) {
  const style = it.plot && it.plot.style === 'marks' ? 'only marks, mark size=1.2pt' : 'no markers, thick';
  const plots = ys.map((y) => `\t\t\t\\addplot+[${style}] table[x=${x}, y=${y}, col sep=comma] {lab/${b.slug}/${it.file}};`).join('\n');
  const legend = ys.length > 1 ? `\n\t\t\t\\legend{${ys.map((y) => texEsc(y.replace(/_/g, ' '))).join(', ')}}` : '';
  return `\\begin{figure}[htbp]\n\t\\centering\n\t\\begin{tikzpicture}\n\t\t\\begin{axis}[width=0.85\\linewidth, height=6.5cm, grid=major, xlabel={${xl}}, ylabel={${yl}}]\n${plots}${legend}\n\t\t\\end{axis}\n\t\\end{tikzpicture}\n\t\\caption{${it.description || 'Measurement data'}}\n\t\\label{fig:${b.slug}-${it.id}-plot}\n\\end{figure}\n`;
}
const COL_LABEL = {
  t_s: 'Time $t$ [s]',
  F_N: 'Force $F$ [N]',
  sigma_MPa: 'Stress $\\sigma$ [MPa]',
  eps_pct: 'Strain $\\varepsilon$ [\\%]',
};
const colLabel = (c) => COL_LABEL[c] || texEsc(c.replace(/_/g, ' '));

/** Content inserted in the preamble breaks the document: move the cursor to the end of the body instead. */
function keepOutOfPreamble() {
  const ed = ctx.editor();
  const model = ed && ed.getModel();
  if (!model) return;
  const src = model.getValue();
  const begin = src.search(/\\begin\{document\}/);
  if (begin < 0 || model.getOffsetAt(ed.getPosition()) > begin) return;
  let idx = src.search(/^[ \t]*\\printbibliography/m);
  if (idx < 0) idx = src.search(/^[ \t]*\\end\{document\}/m);
  if (idx < 0) return;
  const pos = model.getPositionAt(idx);
  ed.setPosition({ lineNumber: pos.lineNumber, column: 1 });
  ed.revealLineInCenter(pos.lineNumber);
  toast('The cursor was in the preamble, so the content went to the end of the document. Move it where you need it.', 'info', 5000);
}

async function insert(raw, need) {
  await ctx.ensureTexEditor();
  keepOutOfPreamble();
  if (!ctx.insertSnippet(ctx.snipEsc(raw) + '$0')) return false;
  await ensureWiring(need);
  return true;
}

/** Insert the pieces just imported from a module environment at the cursor, in the order chosen: figures and
 *  tables as floats, text blocks linked, single values as \labval, then the methods paragraph (equations, assumptions)
 *  when wanted. Data series stay in the Lab dialog (they need an axis choice). Returns what was inserted. */
export async function insertImported(b, keys, { methods = true, variants = {} } = {}) {
  const parts = [];
  const need = { cite: false };
  const vals = [];
  const valueLabel = new Map(b.items.filter((i) => i.kind === 'values').flatMap((i) => i.values || []).map((v) => [v.key, v.label || v.key]));
  const isMethods = (it) => it.kind === 'text' && (it.methods === true || /method|methodik/i.test(`${it.id} ${it.title || ''}`));
  let data = 0;
  for (const k of keys) {
    const [kind, id] = [k.slice(0, k.indexOf(':')), k.slice(k.indexOf(':') + 1)];
    if (kind === 'value') {
      vals.push(id);
      continue;
    }
    const it = b.items.find((i) => i.id === id && i.kind !== 'citation' && i.kind !== 'values');
    if (!it) continue;
    const cites = /\\cite/.test(it.caption || '') || (it.cites || []).length > 0;
    // a figure with parts left out goes in as its live variant (variants: figure id -> saved variant)
    const vb = it.kind === 'figure' && variants[id];
    const vit = vb && (vb.items || []).find((i) => i.id === id && !i.hidden);
    if (vit) {
      parts.push(figureTex(vb, vit));
      need.graphics = true;
      need.cite ||= /\\cite/.test(vit.caption || '');
    } else if (it.kind === 'figure') {
      parts.push(figureTex(b, it));
      need.graphics = true;
      need.cite ||= cites;
    } else if (it.kind === 'table') {
      parts.push(tableTex(b, it));
      need.tables = true;
      need.cite ||= cites;
    } else if (it.kind === 'text' && !isMethods(it)) {
      parts.push(`\\input{lab/${b.slug}/${it.file.replace(/\.tex$/i, '')}}\n`);
      need.cite = true;
    } else if (it.kind === 'data') data++;
  }
  if (vals.length === 1) parts.push(`\\labval{${b.slug}}{${vals[0]}}`);
  else if (vals.length) {
    parts.push(`\\begin{itemize}\n${vals.map((v) => `\t\\item ${valueLabel.get(v)}: \\labval{${b.slug}}{${v}}`).join('\n')}\n\\end{itemize}\n`);
  }
  if (methods) {
    for (const it of b.items.filter((i) => isMethods(i) && !i.hidden)) {
      parts.push(`\\input{lab/${b.slug}/${(it.shown_file || it.file).replace(/\.tex$/i, '')}}\n`);
      need.cite = true;
    }
  }
  if (!parts.length) return { inserted: 0, data };
  const ok = await insert(parts.join('\n'), need);
  return { inserted: ok ? parts.length : 0, data };
}

// ---------------------------------------------------------------- customise (editing window)
const customise = async (slug, item) => {
  const res = await openCustomise({ projectId: ctx.projectId, slug, item, reloadFromDisk: ctx.reloadFromDisk });
  if (res) await placeEverywhere(res).catch((e) => toast(e.message, 'error', 6000));
  return res;
};

// ---------------------------------------------------------------- remove a result as a unit
const USE_ACT = { remove: 'remove', freeze: 'freeze', drop: 'drop' };

/** The confirmation: every place of the text that changes, by file. Resolves true to go ahead. */
async function confirmRemoval(info, uses, file) {
  const byFile = new Map();
  for (const u of uses) {
    if (!byFile.has(u.file)) byFile.set(u.file, []);
    byFile.get(u.file).push(u);
  }
  const line = (u) => {
    const what = u.kind === 'value' ? `<code>${esc(u.what)}</code> → ${esc(plainTex(u.value ?? '??'))}†`
      : u.kind === 'ref' && u.action === 'freeze' ? `<code>${esc(u.what)}</code> → ${esc(plainTex(u.value))}†`
        : u.kind === 'cite' ? `citation <code>${esc(u.what)}</code>`
          : u.kind === 'ref' ? `reference ${esc(u.what)}` : esc(u.what);
    return `<li><span class="uses-act ${u.action}">${USE_ACT[u.action]}</span> line ${u.line}: ${what}</li>`;
  };
  const nFreeze = uses.filter((u) => u.action === 'freeze').length;
  const notes = [
    file ? `<p><code>${esc(file)}</code> belongs to this result; deleting it removes the whole result.</p>` : '',
    uses.length ? `<p>These places in your text use it and change with it, so the report still compiles:</p>` : '<p>No place in your text uses it.</p>',
    ...[...byFile].map(([f, list]) => `<details class="uses-file" open><summary>${esc(f)} · ${list.length} place${list.length === 1 ? '' : 's'}</summary><ul>${list.map(line).join('')}</ul></details>`),
    nFreeze ? `<p class="hint">Frozen values and references keep the text they print now, marked with † (<code>\\labstale</code>); a reference shows ?? if the report has not been compiled since it was inserted.</p>` : '',
    info.section ? `<p class="hint">The results section <code>${esc(info.section)}</code> goes with it.</p>` : '',
    (info.shared_keys || []).length ? `<p class="hint">${info.shared_keys.length} of its references stay, other results or your own .bib files use them.</p>` : '',
    (info.variants || []).length ? `<p class="hint">Its ${info.variants.length} variant${info.variants.length === 1 ? '' : 's'} stay but can no longer follow it on Refresh.</p>` : '',
    '<p class="hint">Undo right after brings back the result and the text in one step.</p>',
  ];
  return (await modal({
    title: `Remove “${plainTex(info.title)}” from the report`,
    body: `<div class="uses-list">${notes.join('')}</div>`,
    wide: uses.length > 4,
    buttons: [{ label: 'Cancel', value: false }, { label: uses.length ? `Remove and change ${uses.length} place${uses.length === 1 ? '' : 's'}` : 'Remove', value: true, cls: 'danger solid' }],
  })) === true;
}

/** Edit the models of `uses` (one undo step per file) and save them. Returns {path: text before}. */
async function applyToModels(uses) {
  const before = {};
  const byFile = new Map();
  for (const u of uses) {
    if (!byFile.has(u.file)) byFile.set(u.file, []);
    byFile.get(u.file).push(u);
  }
  for (const [p, list] of byFile) {
    const { model } = await ctx.getModel(p);
    before[p] = model.getValue();
    const ops = list.map((u) => {
      const a = model.getPositionAt(u.start);
      const z = model.getPositionAt(u.end);
      return { range: { startLineNumber: a.lineNumber, startColumn: a.column, endLineNumber: z.lineNumber, endColumn: z.column }, text: u.replace };
    });
    model.pushStackElement();
    model.pushEditOperations([], ops, () => null);
    model.pushStackElement();
  }
  await Promise.all(Object.keys(before).map((p) => ctx.save(p)));
  return before;
}

async function putBack(before) {
  for (const [p, text] of Object.entries(before)) {
    const { model } = await ctx.getModel(p);
    model.pushEditOperations([], [{ range: model.getFullModelRange(), text }], () => null);
  }
  await Promise.all(Object.keys(before).map((p) => ctx.save(p)));
}

/**
 * Remove result `slug` from the report as a unit: list every place of the .tex files that uses it, take floats and
 * \input lines out, freeze \labval values and references to its labels, drop citation keys only it provides, save,
 * move the result (and its results section) to the bin, and offer one Undo for all of it.
 * opts.file: the file-tree path that was deleted (a file inside the result); opts.onUndo: called after an undo.
 * Resolves true when removed.
 */
export async function removeResult(slug, opts = {}) {
  const base = `/api/projects/${ctx.projectId}`;
  const info = await api('GET', `${base}/lab/${slug}/uses-info`);
  await ctx.refreshFiles().catch(() => {});
  const files = {};
  for (const p of ctx.texFiles()) {
    if (p.startsWith('lab/') || p === info.section) continue;
    files[p] = (await ctx.getModel(p)).model.getValue();
  }
  const uses = findUses(files, info);
  if (!(await confirmRemoval(info, uses, opts.file))) return false;
  const before = uses.length ? await applyToModels(uses) : {};
  let r;
  try {
    r = await api('DELETE', `${base}/lab/${slug}?section=${info.section ? 1 : 0}`);
  } catch (e) {
    await putBack(before);
    throw e;
  }
  ctx.forget(`lab/${slug}`);
  if (info.section) ctx.forget(info.section);
  await ctx.refreshFiles();
  const n = uses.length;
  toast(`Removed “${plainTex(info.title)}”${n ? `; ${n} place${n === 1 ? '' : 's'} in the text changed` : ''}`, 'ok', 12000, {
    label: 'Undo',
    onClick: async () => {
      try {
        await api('POST', `${base}/lab-undo`, { undo: r.undo });
        await putBack(before);
        await ctx.refreshFiles();
        toast('Result and text are back', 'ok');
        if (opts.onUndo) await opts.onUndo();
      } catch (e) {
        toast(e.message, 'error', 8000);
      }
    },
  });
  return true;
}

/** A figure variant with a placement: every float of the .tex files that already shows it gets the width,
 *  position and alignment (one edit per file, so Ctrl+Z in that file takes it back). */
async function placeEverywhere(res) {
  const place = res.bundle && res.bundle.fork && res.bundle.fork.place;
  const nit = res.bundle && (res.bundle.items || []).find((i) => i.id === res.item && !i.hidden);
  if (!place || !nit || nit.kind !== 'figure') return;
  const path = `lab/${res.slug}/${noExt(nit.file)}`;
  let n = 0;
  for (const p of ctx.texFiles()) {
    if (p.startsWith('lab/')) continue;
    const { model } = await ctx.getModel(p);
    const src = model.getValue();
    const ops = floatsWith(src, path).map((s) => {
      const seg = src.slice(s.start, s.end);
      const text = placeFloat(seg, place);
      if (text === seg) return null;
      const a = model.getPositionAt(s.start);
      const z = model.getPositionAt(s.end);
      return { range: { startLineNumber: a.lineNumber, startColumn: a.column, endLineNumber: z.lineNumber, endColumn: z.column }, text };
    }).filter(Boolean);
    if (!ops.length) continue;
    model.pushEditOperations([], ops, () => null);
    n += ops.length;
  }
  if (n) toast(`Placement applied to ${n} figure${n === 1 ? '' : 's'} in the text`, 'info', 4000);
}

const REF_RE = /lab\/([a-z0-9][a-z0-9_-]*)\/([^}\s]+)/i;
const noExt = (f) => String(f || '').replace(/\.(pdf|png|tex)$/i, '');

/** The figure/table float around offset `off`, else the line. */
function refScope(src, off) {
  let best = null;
  const re = /\\begin\{(figure\*?|table\*?)\}/g;
  let m;
  while ((m = re.exec(src)) && m.index <= off) {
    const tag = `\\end{${m[1]}}`;
    const e = src.indexOf(tag, m.index);
    if (e >= 0 && e + tag.length >= off) best = { start: m.index, end: e + tag.length };
  }
  if (best) return best;
  const s = src.lastIndexOf('\n', Math.max(0, off - 1)) + 1;
  let e = src.indexOf('\n', off);
  if (e < 0) e = src.length;
  return { start: s, end: e };
}

/** Piece of result `b` that file path `rel` (without extension) belongs to; a methods selection maps to its text. */
function itemOfPath(b, rel) {
  const base = noExt(rel);
  return (b.items || []).find((i) => ['figure', 'table', 'text'].includes(i.kind) && [i.file, i.shown_file].filter(Boolean).some((f) => noExt(f) === base));
}

/** End index (after the closing brace) of the {…} group starting at s[i] === '{'. */
function groupEnd(s, i) {
  let d = 0;
  for (let j = i; j < s.length; j++) {
    if (s[j] === '\\') { j++; continue; }
    if (s[j] === '{') d++;
    else if (s[j] === '}' && --d === 0) return j + 1;
  }
  return -1;
}

/** In the editor, point the reference in `scope` at the saved variant: the file path and the caption change, the
 *  label stays (your \ref keep working). One undo step. */
function swapRef(model, scope, oldSlug, res) {
  const nit = (res.bundle.items || []).find((i) => i.id === res.item && !i.hidden);
  if (!nit) return false;
  let seg = model.getValue().slice(scope.start, scope.end);
  const re = new RegExp(`lab/${oldSlug.replace(/[-]/g, '\\-')}/[^}\\s]+`);
  if (!re.test(seg)) return false;
  seg = seg.replace(re, `lab/${res.slug}/${noExt(nit.file)}`);
  const c = seg.indexOf('\\caption{');
  if (nit.kind !== 'text' && c >= 0) {
    const e = groupEnd(seg, c + '\\caption'.length);
    if (e > 0) seg = seg.slice(0, c) + `\\caption{${nit.caption}}` + seg.slice(e);
  }
  const place = res.bundle.fork && res.bundle.fork.place;
  if (nit.kind === 'figure' && place && /^\s*\\begin\{figure/.test(seg)) seg = placeFloat(seg, place);
  const a = model.getPositionAt(scope.start);
  const z = model.getPositionAt(scope.end);
  ctx.editor().executeEdits('folio-lab', [{ range: { startLineNumber: a.lineNumber, startColumn: a.column, endLineNumber: z.lineNumber, endColumn: z.column }, text: seg }]);
  return true;
}

/** Editor context menu: customise the Lab figure, table or text at the cursor and point the text at the variant. */
export async function customiseAtCursor() {
  const ed = ctx.editor();
  const model = ed && ed.getModel();
  if (!model) return;
  const src = model.getValue();
  const scope = refScope(src, model.getOffsetAt(ed.getPosition()));
  const m = src.slice(scope.start, scope.end).match(REF_RE);
  if (!m) {
    toast('Put the cursor in a figure or table from Folio Lab (or on an \\input{lab/…} line).', 'info', 5000);
    return;
  }
  try {
    const b = (await api('GET', `/api/projects/${ctx.projectId}/lab`)).find((x) => x.slug === m[1]);
    if (!b) throw new Error(`No result “${m[1]}” in this report`);
    const it = itemOfPath(b, m[2]);
    if (!it) throw new Error(`“${m[2]}” is not a figure, table or text of “${b.title}”`);
    const res = await customise(b.slug, it.id);
    if (!res) return;
    await ctx.refreshFiles();
    if (swapRef(model, refScope(model.getValue(), model.getOffsetAt(ed.getPosition())), b.slug, res)) toast('The text now uses the variant (Ctrl+Z goes back to the original)', 'info', 5000);
  } catch (err) {
    toast(err.message, 'error', 8000);
  }
}

/** After an import: open the editing window for each chosen figure, table or text in turn; a saved variant
 *  replaces the reference just inserted. */
export async function customiseImported(man, keys, variants = {}) {
  const ed = ctx.editor();
  for (const k of keys) {
    const id = k.slice(k.indexOf(':') + 1);
    const it = (man.items || []).find((i) => i.id === id && ['figure', 'table', 'text'].includes(i.kind));
    if (!it) continue;
    const slug = variants[id] ? variants[id].slug : man.slug;     // a variant made at import is edited in place
    let res;
    try {
      res = await customise(slug, it.id);
    } catch (err) {
      toast(err.message, 'error', 8000);
      continue;
    }
    if (!res || !ed || !ed.getModel()) continue;
    const model = ed.getModel();
    const src = model.getValue();
    const at = src.indexOf(`lab/${slug}/${noExt(it.shown_file || it.file)}`);
    if (at >= 0) swapRef(model, refScope(src, at), slug, res);
  }
  await ctx.refreshFiles();
}

// UI-09: status of a result at a glance – revision, issued or draft, shared inputs it uses
function statusChips(b) {
  const n = (b.history_count || 0) + 1;
  const refs = b.refs || { shares: [], index: [] };
  const pl = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`;
  const ext = [refs.shares.length ? pl(refs.shares.length, 'shared input') : '', refs.index.length ? pl(refs.index.length, 'index value') : ''].filter(Boolean).join(', ');
  return [
    `<span class="pill" title="Every Refresh keeps the previous revision">Revision ${b.revision || 1} of ${n}</span>`,
    b.issued
      ? `<span class="pill ok" title="Fixed by ${esc(b.issued.how)} on ${esc(new Date(b.issued.at).toLocaleString())}; a later Refresh makes a new revision">issued</span>`
      : '<span class="pill warn" title="Not yet exported or marked issued; Refresh replaces it with a new revision">draft</span>',
    ext ? `<span class="pill live" title="${esc([...refs.shares, ...refs.index].join(', '))}; details under history">uses ${ext}</span>` : '',
  ].join(' ');
}

// imported results follow their source (live), wait for a click (pinned) or stand alone (copy).
const LINK_MODE = { live: 'Live', pin: 'Pinned', copy: 'Copy' };
function linkPill(b, st) {
  const l = b.link;
  if (!l) return '';
  const from = l.type === 'suite' ? 'the shared data of the project' : l.type === 'env' ? `the environment "${l.env_name || l.env}" (${l.title || l.module})` : l.type === 'zip' ? `the ZIP ${l.name || ''}`.trim() : `"${l.title || l.project || ''}"`;
  if (l.type === 'zip' || l.mode === 'copy') return `<span class="pill" title="Imported from ${esc(from)}; no link to the source">copy</span>`;
  if (!st) return `<span class="pill" title="Checking ${esc(from)}">${LINK_MODE[l.mode] || l.mode} · checking…</span>`;
  const what = [...(st.changed || []), ...(st.missing || [])].join(', ');
  const upd = '<button class="btn xs" data-act="link-update" title="Import the current state of the source again; the previous state stays as a revision">Update</button>';
  if (st.state === 'current') return `<span class="pill ok" title="Same as ${esc(from)}">${LINK_MODE[l.mode]} · source current</span>`;
  if (st.state === 'stale') return `<span class="pill warn" title="${esc(from)} changed: ${esc(what)}">source changed</span> ${upd}`;
  if (st.state === 'update') return `<span class="pill live" title="${esc(from)} changed: ${esc(what)}; pinned, so nothing changed here">update available</span> ${upd}`;
  if (st.state === 'failed') return `<span class="pill err" title="${esc(st.error || `Not found in ${from}: ${what}`)}">source missing</span>`;
  return `<span class="pill">${LINK_MODE[l.mode] || ''}</span>`;
}

// ---------------------------------------------------------------- dialog
export async function openLab(preselect) {
  let bundles = [];
  let links = null; // slug -> link state, loaded after the list because it reads the sources
  let current = preselect || null;
  await ctx.refreshFiles().catch(() => {});
  const body = h(`<div class="lab-dlg">
    <aside class="lab-list"></aside>
    <section class="lab-detail"></section>
  </div>`);
  const listEl = body.querySelector('.lab-list');
  const detailEl = body.querySelector('.lab-detail');
  // List column: drag the divider; kept as a fraction of the dialog width, double-click resets.
  const colGrip = h('<div class="lab-colgrip" title="Drag to resize; double-click resets"></div>');
  body.appendChild(colGrip);
  const setListW = (px) => body.style.setProperty('--lab-list-w', Math.round(Math.max(140, Math.min(body.clientWidth - 240, px))) + 'px');
  new ResizeObserver(() => { const f = store('labListF'); if (typeof f === 'number' && f > 0 && body.clientWidth) setListW(f * body.clientWidth); }).observe(body);
  colGrip.addEventListener('dblclick', () => { body.style.removeProperty('--lab-list-w'); store('labListF', null); });
  colGrip.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    colGrip.setPointerCapture(e.pointerId);
    const x0 = e.clientX, w0 = listEl.getBoundingClientRect().width;
    document.body.classList.add('resizing');
    const move = (ev) => setListW(w0 + ev.clientX - x0);
    const up = () => {
      document.body.classList.remove('resizing');
      colGrip.removeEventListener('pointermove', move);
      colGrip.removeEventListener('pointerup', up);
      store('labListF', listEl.getBoundingClientRect().width / body.clientWidth);
    };
    colGrip.addEventListener('pointermove', move);
    colGrip.addEventListener('pointerup', up);
  });
  let closeDialog = () => {};

  async function reload() {
    bundles = await api('GET', `/api/projects/${ctx.projectId}/lab`);
    if (!bundles.some((b) => b.slug === current)) current = (bundles.find((b) => !b.fork) || bundles[0])?.slug || null;
    renderList();
    renderDetail();
    if (bundles.some((b) => b.link)) loadLinks();
  }

  async function loadLinks() {
    try {
      const all = await api('GET', `/api/projects/${ctx.projectId}/import/links`);
      links = new Map(all.map((s) => [s.slug, s]));
    } catch (e) {
      links = new Map(bundles.filter((b) => b.link).map((b) => [b.slug, { slug: b.slug, state: 'failed', error: e.message, changed: [], missing: [] }]));
    }
    fillLink();
  }

  function fillLink() {
    const b = bundles.find((x) => x.slug === current);
    const el = detailEl.querySelector('.lab-link');
    if (!b || !b.link || !el) return;
    el.innerHTML = linkPill(b, links && links.get(b.slug));
    const btn = el.querySelector('[data-act=link-update]');
    if (btn) btn.onclick = () => rebuild(b, btn, {}, `/api/projects/${ctx.projectId}/import/${b.slug}/update`);
  }

  function renderList() {
    if (!bundles.length) {
      listEl.innerHTML = '';
      return;
    }
    // variants (customised copies) follow their original, indented
    const slugs = new Set(bundles.map((b) => b.slug));
    const ordered = [];
    for (const b of bundles) {
      if (b.fork && slugs.has(b.fork.of)) continue;
      ordered.push(b, ...bundles.filter((f) => f.fork && f.fork.of === b.slug));
    }
    listEl.innerHTML = ordered
      .map(
        (b) => `<button class="lab-item ${b.slug === current ? 'on' : ''} ${b.fork ? 'variant' : ''}" data-slug="${esc(b.slug)}">
          <b>${esc(b.title)}</b><span>${b.fork ? `variant · ${b.fork.mode === 'live' ? 'live' : 'snapshot'}` : esc(b.module_name || b.module)} · ${esc(b.lang === 'en' ? 'EN' : 'DE')} · ${esc(new Date(b.updated).toLocaleString())}</span></button>`
      )
      .join('');
    listEl.querySelectorAll('[data-slug]').forEach((el) => {
      el.onclick = () => {
        current = el.dataset.slug;
        renderList();
        renderDetail();
      };
    });
  }

  /** Choose the sentences of a methods text: Short / Full / own ticks, equations; saved with the result's
   *  pick (no new revision, nothing recomputed). Places that \\input the selection change with it. */
  async function stepEditor(b, it, box) {
    const st = (it.steps || []).filter((s) => !s.eq);
    const hasEq = (it.steps || []).some((s) => s.eq);
    // sentences only needed for pieces or parts not shown (an envelope left out, no reference comparison) stay out
    const inactive = new Set(it.inactive_steps || []);
    const brief = st.find((s) => s.brief);
    const on = new Set(it.shown_file ? it.shown_steps || [] : (it.steps || []).filter((s) => !s.brief && !inactive.has(s.id)).map((s) => s.id));
    const edits = { ...((b.pick && b.pick.methods && b.pick.methods.edits) || {}) };
    const changed = new Set(it.edited_changed || []);
    const texts = {};
    box.innerHTML = `<div class="hint">${icon('loader')} Reading the sentences…</div>`;
    await Promise.all(st.map(async (s) => {
      try {
        texts[s.id] = (await (await api('GET', fileUrl(ctx.projectId, `lab/${b.slug}/${s.file}`), undefined, { raw: true })).text()).trim();
      } catch {
        texts[s.id] = '';
      }
    }));
    const row = (s) => {
      const ed = edits[s.id];
      const off = inactive.has(s.id);
      return `<div class="imp-steprow"><label class="imp-step ${on.has(s.id) && !off ? 'on' : ''}" title="${esc(off ? 'Only needed for pieces or parts this report does not show' : texts[s.id] || s.title)}"><input type="checkbox" data-sid="${esc(s.id)}" ${on.has(s.id) && !off ? 'checked' : ''} ${off ? 'disabled' : ''}><span>${esc(ed ? plain(ed.text) : s.title)}</span>${s.brief ? '<i class="hint">alone, when nothing is evaluated</i>' : s.short ? '<i class="hint">short</i>' : ''}${off ? '<i class="hint">not shown</i>' : ''}${ed ? '<i class="hint">edited</i>' : ''}${ed && changed.has(s.id) ? '<i class="warn" title="The module now writes something else here; your wording is kept. Open the pencil to compare.">module changed</i>' : ''}</label>
        <button class="btn xs ghost" data-ed="${esc(s.id)}" title="Reword this sentence">${icon('edit')}</button>
        <div class="imp-stepedit" hidden>${ed && changed.has(s.id) ? `<div class="hint">Module now: ${esc(texts[s.id])}</div>` : ''}<textarea class="input mono" rows="3">${esc(ed ? ed.text : texts[s.id])}</textarea>
          <div class="row"><button class="btn xs" data-ok>Use</button><button class="btn xs ghost" data-undo ${ed ? '' : 'hidden'}>Module's wording</button></div></div></div>`;
    };
    const draw = () => {
      box.innerHTML = `<div class="lab-stepbtns"><button class="btn xs" data-m="short">Short</button><button class="btn xs" data-m="full">Full</button>
          <span class="hint">or tick sentences, the pencil rewords one · inserted as <code>${esc((it.shown_file || it.file).replace(/\.tex$/i, ''))}</code></span></div>
        <div class="imp-steplist">${st.map(row).join('')}</div>
        ${hasEq ? `<label class="imp-step"><input type="checkbox" data-sid="${esc((it.steps.find((s) => s.eq) || {}).id || '')}" ${[...on].some((id) => (it.steps.find((s) => s.id === id) || {}).eq) ? 'checked' : ''}> with the equations block</label>` : ''}
        <div class="lab-stepbtns"><button class="btn sm primary" data-save>Use this selection</button>
          <button class="btn sm ghost" data-free title="Save the selection, then edit it as one text (a variant that keeps your wording on Refresh)">Edit as free text…</button></div>`;
      box.querySelectorAll('[data-sid]').forEach((c) => (c.onchange = () => {
        if (c.checked) on.add(c.dataset.sid);
        else on.delete(c.dataset.sid);
        c.closest('.imp-step').classList.toggle('on', c.checked);
      }));
      box.querySelectorAll('[data-ed]').forEach((btn) => {
        const sid = btn.dataset.ed;
        const ebox = btn.parentElement.querySelector('.imp-stepedit');
        btn.onclick = () => {
          ebox.hidden = !ebox.hidden;
          if (!ebox.hidden) ebox.querySelector('textarea').focus();
        };
        ebox.querySelector('[data-ok]').onclick = () => {
          const t = ebox.querySelector('textarea').value.trim();
          if (!t || t === texts[sid]) delete edits[sid];
          else edits[sid] = { text: t, orig: edits[sid] && !changed.has(sid) ? edits[sid].orig : texts[sid] };
          changed.delete(sid);
          if (edits[sid]) on.add(sid);
          draw();
        };
        ebox.querySelector('[data-undo]').onclick = () => {
          delete edits[sid];
          changed.delete(sid);
          draw();
        };
      });
      box.querySelector('[data-free]').onclick = async () => {
        if (!(await saveSel(box.querySelector('[data-save]')))) return;
        const fresh = bundles.find((x) => x.slug === b.slug) || b;
        const res = await customise(fresh.slug, it.id).catch((err) => toast(err.message, 'error', 8000));
        if (res) await reload();
      };
      box.querySelectorAll('[data-m]').forEach((m) => (m.onclick = () => {
        on.clear();
        if (m.dataset.m === 'short' && it.reduced && brief) on.add(brief.id);
        else for (const s of st) if (!s.brief && !inactive.has(s.id) && (m.dataset.m === 'full' || s.short)) on.add(s.id);
        draw();
      }));
      box.querySelector('[data-save]').onclick = async (e) => {
        if (await saveSel(e.currentTarget)) await reload();
      };
    };
    async function saveSel(btn) {
      btn.disabled = true;
      const eq = (it.steps || []).some((s) => s.eq && on.has(s.id));
      const ids = (it.steps || []).filter((s) => on.has(s.id) && !s.eq).map((s) => s.id);
      try {
        const r = await api('POST', `/api/projects/${ctx.projectId}/lab/${b.slug}/pick`, { methods: { mode: 'custom', steps: ids, eq, edits } });
        await ctx.reloadFromDisk(`lab/${b.slug}/`);
        const ne = Object.keys(edits).filter((k) => ids.includes(k)).length;
        toast(`Methods text: ${ids.length} of ${st.length} sentences${ne ? `, ${ne} reworded` : ''}${eq ? ' + equations' : ''}`, 'ok');
        if ((r.warnings || []).length) toast(r.warnings.join(' · '), 'info', 8000);
        const i = bundles.findIndex((x) => x.slug === b.slug);
        if (i >= 0) bundles[i] = { ...bundles[i], ...r };
        return true;
      } catch (err) {
        toast(err.message, 'error');
        btn.disabled = false;
        return false;
      }
    }
    draw();
  }

  function renderDetail() {
    const b = bundles.find((x) => x.slug === current);
    if (!b) {
      detailEl.innerHTML = `<div class="lab-empty">${icon('chart')}<h3>No analysis results in this report yet</h3>
        <p>Open an analysis from the <a href="/" target="_blank">Folio Lab home page</a> (for example <b>Zugversuch</b>), load a measurement and press <b>Zum Bericht …</b>. Choose this report as the target. The results then appear here, ready to insert.</p></div>`;
      return;
    }
    const by = (k) => b.items.filter((i) => i.kind === k);
    const variant = b.fork || null;
    const values = variant ? [] : by('values').flatMap((v) => v.values || []);
    const hiddenN = variant ? 0 : b.items.filter((i) => i.hidden).length;
    const origB = variant ? bundles.find((x) => x.slug === variant.of) : null;
    const variants = bundles.filter((x) => x.fork && x.fork.of === b.slug);
    const other = b.lang === 'en' ? 'de' : 'en';
    const imported = b.module === 'import';
    detailEl.innerHTML = `
      <div class="lab-head">
        <div class="grow"><h3>${esc(b.title)}</h3><div class="muted">${esc(b.summary || '')}</div>
          <div class="hint">Stored in <code>lab/${esc(b.slug)}/</code> · ${variant ? `${variant.mode === 'live' ? 'live variant (follows the original on Refresh)' : 'snapshot (frozen)'} of <a href="#" data-goto="${esc(variant.of)}">${esc(origB ? origB.title : variant.of)}</a>` : imported ?`imported from ${esc(b.link ? b.link.title || '' : '')}` : `from <a href="/m/${esc(b.module)}/" target="_blank">${esc(b.module_name || b.module)}</a>${b.provenance && b.provenance.module_version ? ` ${esc(b.provenance.module_version)}` : ''}`}</div>
          <div class="lab-status">${statusChips(b)}${b.link ? ` <span class="lab-link"></span>${b.link.type !== 'zip' ? ` <select class="input xs" data-act="link-mode" title="Live: marked when the source changes · Pinned: an update is offered · Copy: no link">${Object.entries(LINK_MODE).map(([k, v]) => `<option value="${k}" ${b.link.mode === k ? 'selected' : ''}>${v}</option>`).join('')}</select>` : ''}` : ''}
            <a href="#" data-act="revs">revisions ▾</a> · <a href="#" data-act="hist" title="Measurement files, module version and, for shared inputs, the chain back to the raw file">history ▾</a></div>
          <div class="lab-revs" hidden></div><div class="lab-hist" hidden></div></div>
        <div class="lab-actions">
          <button class="btn sm primary" data-act="section" title="Write sections/${esc(b.slug)}.tex with all text, figures and tables, and insert \\input for it">${icon('file-plus')}Insert results section</button>
          ${imported ? '' : `<button class="btn sm" data-act="refresh" ${b.source ? '' : 'disabled'} title="Recompute from the stored measurement files with the current module version">${icon('refresh')}Refresh</button>
          <button class="btn sm" data-act="lang" ${b.source ? '' : 'disabled'} title="Rebuild captions and text in ${other === 'en' ? 'English' : 'German'}">${other === 'en' ? 'English' : 'Deutsch'}</button>`}
          <button class="btn sm ghost danger" data-act="remove" title="Remove these results from the report">${icon('trash')}</button>
        </div>
      </div>
      ${pieces(b, b.items.filter((i) => !i.hidden))}
      ${values.length ? `<h4>${KIND_LABEL.values} <span class="hint">click to insert <code>\\labval</code>; the number updates when the results are refreshed</span></h4>
        <div class="lab-vals">${values.map((v) => `<button class="lab-val" data-val="${esc(v.key)}" title="\\labval{${esc(b.slug)}}{${esc(v.key)}}"><span>${esc(plain(v.label))}</span><b>${esc(v.text || plain(v.latex))}</b></button>`).join('')}</div>` : ''}
      ${hiddenN ? `<details class="lab-more"><summary>Also in this result: ${hiddenN} piece${hiddenN === 1 ? '' : 's'} not chosen at import <span class="hint">kept in <code>lab/${esc(b.slug)}/</code>, insert any of them here</span></summary>${pieces(b, b.items.filter((i) => i.hidden))}</details>` : ''}
      ${variants.length ? `<h4>Variants <span class="hint">customised copies of pieces of this result; the original stays as it is</span></h4><div class="lab-rows">${variants.map((v) => `
        <div class="lab-row"><span class="grow">${esc(v.title)} <span class="pill">${v.fork.mode === 'live' ? 'live' : 'snapshot'}</span></span>
          <button class="btn sm ghost" data-goto="${esc(v.slug)}">Open</button></div>`).join('')}</div>` : ''}
      ${by('citation').length ? `<h4>${KIND_LABEL.citation} <span class="hint">collected in <code>lab/references.bib</code></span></h4><div class="lab-rows">${by('citation').map((it) => `
        <div class="lab-row"><code>${esc(it.key)}</code><span class="grow">${esc(plain(it.title))}</span>
          <button class="btn sm" data-cite="${esc(it.key)}">${icon('cite')}Cite</button></div>`).join('')}</div>` : ''}`;

    const item = (kind, id) => b.items.find((i) => i.kind === kind && (i.id === id || i.key === id));
    const done = (ok) => {
      if (ok) closeDialog();
    };
    const cites = (it) => /\\cite/.test(it.caption || '') || (it.cites || []).length > 0;
    detailEl.querySelectorAll('[data-fig]').forEach((el) => (el.onclick = async () => done(await insert(figureTex(b, item('figure', el.dataset.fig)), { graphics: true, cite: cites(item('figure', el.dataset.fig)) }))));
    detailEl.querySelectorAll('[data-tab]').forEach((el) => (el.onclick = async () => done(await insert(tableTex(b, item('table', el.dataset.tab)), { tables: true, cite: cites(item('table', el.dataset.tab)) }))));
    detailEl.querySelectorAll('[data-val]').forEach((el) => (el.onclick = async () => done(await insert(`\\labval{${b.slug}}{${el.dataset.val}}`, {}))));
    detailEl.querySelectorAll('[data-cite]').forEach((el) => (el.onclick = async () => done(await insert(`\\cite{${el.dataset.cite}}`, { cite: true }))));
    // a methods text with chosen steps inserts its selection (text-…-auswahl.tex); the full text stays beside it
    const textFile = (it) => it.shown_file || it.file;
    detailEl.querySelectorAll('[data-textin]').forEach((el) => (el.onclick = async () => done(await insert(`\\input{lab/${b.slug}/${textFile(item('text', el.dataset.textin)).replace(/\.tex$/i, '')}}\n`, { cite: true }))));
    detailEl.querySelectorAll('[data-text]').forEach(
      (el) =>
        (el.onclick = async () => {
          const it = item('text', el.dataset.text);
          const r = await api('GET', fileUrl(ctx.projectId, `lab/${b.slug}/${textFile(it)}`), undefined, { raw: true });
          done(await insert((await r.text()).trim() + '\n', { cite: true }));
        })
    );
    detailEl.querySelectorAll('[data-goto]').forEach((el) => (el.onclick = (e) => {
      e.preventDefault();
      current = el.dataset.goto;
      renderList();
      renderDetail();
    }));
    detailEl.querySelectorAll('[data-cus]').forEach((el) => (el.onclick = async (e) => {
      e.stopPropagation();
      try {
        const r = await customise(b.slug, el.dataset.cus);
        if (!r) return;
        await ctx.refreshFiles();
        current = r.slug;
        await reload();
      } catch (err) {
        toast(err.message, 'error', 8000);
      }
    }));
    detailEl.querySelectorAll('[data-steps]').forEach((el) => (el.onclick = () => {
      const box = detailEl.querySelector(`[data-stepbox="${CSS.escape(el.dataset.steps)}"]`);
      box.hidden = !box.hidden;
      if (!box.hidden) stepEditor(b, item('text', el.dataset.steps), box);
    }));
    detailEl.querySelectorAll('[data-plot]').forEach(
      (el) =>
        (el.onclick = async () => {
          const row = el.closest('.lab-row');
          const x = row.querySelector('[data-x]').value;
          const y = row.querySelector('[data-y]').value;
          const it = item('data', el.dataset.plot);
          const lab = (c) => (it.labels && it.labels[c]) || colLabel(c);
          done(await insert(plotTex(b, it, x, [y], lab(x), lab(y)), { plot: true }));
        })
    );
    detailEl.querySelector('[data-act=revs]').onclick = (e) => {
      e.preventDefault();
      const box = detailEl.querySelector('.lab-revs');
      box.hidden = !box.hidden;
      if (!box.hidden) renderRevisions(b, box);
    };
    detailEl.querySelector('[data-act=hist]').onclick = (e) => {
      e.preventDefault();
      const box = detailEl.querySelector('.lab-hist');
      box.hidden = !box.hidden;
      if (!box.hidden) renderHistory(b, box);
    };
    detailEl.querySelector('[data-act=section]').onclick = () => resultsSection(b).then(done);
    if (!imported) {
      detailEl.querySelector('[data-act=refresh]').onclick = (e) => rebuild(b, e.currentTarget, {});
      detailEl.querySelector('[data-act=lang]').onclick = (e) => rebuild(b, e.currentTarget, { lang: other });
    }
    fillLink();
    const modeSel = detailEl.querySelector('[data-act=link-mode]');
    if (modeSel) modeSel.onchange = async () => {
      try {
        await api('POST', `/api/projects/${ctx.projectId}/import/${b.slug}/mode`, { mode: modeSel.value });
        toast(`Link: ${LINK_MODE[modeSel.value]}`);
        await reload();
      } catch (err) {
        toast(err.message, 'error');
        modeSel.value = b.link.mode;
      }
    };
    detailEl.querySelector('[data-act=remove]').onclick = async () => {
      try {
        if (await removeResult(b.slug, { onUndo: reload })) {
          current = null;
          await reload();
        }
      } catch (err) {
        toast(err.message, 'error', 8000);
      }
    };
  }

  // UI-09 / A8: "Open history" – what the result rests on, and for shared inputs the chain back to the raw file.
  async function renderHistory(b, box) {
    box.innerHTML = '<div class="hint">Loading…</div>';
    let h;
    try {
      h = await api('GET', `/api/projects/${ctx.projectId}/lab/${b.slug}/history`);
    } catch (err) {
      box.innerHTML = `<div class="hint">${esc(err.message)}</div>`;
      return;
    }
    const sha = (s) => (s ? `<code title="SHA-256 ${esc(s)}">${esc(s.slice(0, 12))}…</code>` : '');
    const step = (s) => `<li class="${s.ok === false ? 'bad' : ''}"><b>${esc(s.title)}</b>${s.ok === false ? ' <span class="pill err">missing</span>' : ''}
      ${s.detail ? `<div class="hint">${esc(s.detail)}</div>` : ''}${s.path ? `<div class="hint"><code>${esc(s.path)}</code> ${sha(s.sha256)}${s.sha_matches_id ? ' · matches the stored ID' : ''}</div>` : ''}</li>`;
    box.innerHTML = `<div class="lab-histbox">
      <div class="hint">Result <code>${esc(h.result_id || '–')}</code> · revision ${h.revision} · ${esc(h.module_name)}${h.module_version ? ` ${esc(h.module_version)}` : ''}${h.action ? ` · ${esc(h.action)}` : ''}</div>
      <h4>Measurement files <span class="hint">stored in <code>lab/${esc(h.slug)}/source/</code></span></h4>
      ${h.source.length ? `<div class="lab-rows">${h.source.map((f) => `<div class="lab-row"><span class="grow">${esc(f.name)}</span>${sha(f.sha256)}</div>`).join('')}</div>` : '<div class="hint">None (computed result or values typed in the module).</div>'}
      ${h.refs.shares.length || h.refs.index.length ? `<h4>Shared inputs and index values</h4>
        ${h.chains_error ? `<div class="hint">Chain not available: ${esc(h.chains_error)}. Used: ${[...h.refs.shares, ...h.refs.index].map(esc).join(', ')}</div>` : ''}
        ${h.chains.map((c) => `<div class="lab-chain"><div><code>${esc(c.ref)}</code></div><ol>${c.steps.map(step).join('')}</ol></div>`).join('')}`
        : '<div class="hint">No shared inputs or project-index values: the result rests on the files above.</div>'}
    </div>`;
  }

  // A1: revision history – every Refresh keeps the previous revision; compare, restore, mark issued.
  async function renderRevisions(b, box) {
    const base = `/api/projects/${ctx.projectId}/lab/${b.slug}`;
    let revs;
    try {
      revs = await api('GET', `${base}/revisions`);
    } catch (err) {
      box.innerHTML = `<div class="hint">${esc(err.message)}</div>`;
      return;
    }
    const cur = revs.find((r) => r.current);
    box.innerHTML = `<div class="lab-rows">${revs.map((r) => `
      <div class="lab-row"><span class="grow"><b>${r.revision}</b> · ${esc(new Date(r.updated).toLocaleString())}${r.action ? ` · ${esc(r.action)}` : ''}${r.module_version ? ` · v${esc(r.module_version)}` : ''}${r.issued ? ' · <b>issued</b>' : ''}${r.current ? ' · current' : ''}</span>
        ${r.current ? (r.issued ? '' : `<button class="btn sm" data-issue title="Fix this revision; exporting PDF or ZIP does the same">Mark issued</button>`)
          : `<button class="btn sm" data-cmp="${r.revision}">Compare</button><button class="btn sm" data-restore="${r.revision}" title="Make a copy of this revision the current one; nothing is deleted">Restore</button>`}</div>`).join('')}</div>
      <div class="lab-cmp"></div>`;
    box.querySelectorAll('[data-cmp]').forEach((el) => (el.onclick = async () => {
      const d = await api('GET', `${base}/compare?a=${el.dataset.cmp}&b=${cur.revision}`);
      const vals = d.values.map((v) => `<div class="lab-row"><span class="grow">${esc(plain(v.label || v.key))}</span><span>${esc(v.a ?? '–')} → <b>${esc(v.b ?? '–')}</b></span></div>`).join('');
      const list = (t, a) => (a.length ? `<div class="hint">${t}: ${a.map(esc).join(', ')}</div>` : '');
      box.querySelector('.lab-cmp').innerHTML = `<h4>Revision ${d.a} → ${d.b}</h4>${vals || '<div class="hint">No value changed.</div>'}
        ${list('Added', d.items.added)}${list('Removed', d.items.removed)}${list('Files changed', d.files.changed)}
        ${d.source_changed ? '<div class="hint">The measurement files differ.</div>' : ''}
        ${d.module_version[0] !== d.module_version[1] ? `<div class="hint">Module version ${esc(d.module_version[0] || '?')} → ${esc(d.module_version[1] || '?')}</div>` : ''}`;
    }));
    box.querySelectorAll('[data-restore]').forEach((el) => (el.onclick = async () => {
      if (!(await confirmBox('Restore revision', `Make revision <b>${el.dataset.restore}</b> the current one? The current revision ${cur.revision} is kept in the history.`, { okLabel: 'Restore' }))) return;
      try {
        await api('POST', `${base}/restore`, { revision: +el.dataset.restore });
        await ctx.refreshFiles();
        await ctx.reloadFromDisk(`lab/${b.slug}/`);
        await ctx.reloadFromDisk('lab/labdata.tex');
        toast(`Revision ${el.dataset.restore} restored`);
        await reload();
      } catch (err) {
        toast(err.message, 'error');
      }
    }));
    const iss = box.querySelector('[data-issue]');
    if (iss) iss.onclick = async () => {
      await api('POST', `${base}/issue`, {});
      toast('Revision marked issued');
      await reload();
    };
  }

  async function rebuild(b, btn, opts, url = `/api/projects/${ctx.projectId}/lab/${b.slug}/refresh`) {
    const label = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `${icon('loader')}Working…`;
    try {
      await api('POST', url, opts);
      await ctx.refreshFiles();
      await ctx.reloadFromDisk(`lab/${b.slug}/`);
      await ctx.reloadFromDisk('lab/labdata.tex');
      await ctx.reloadFromDisk('lab/references.bib');
      toast(opts.lang ? `Results rebuilt in ${opts.lang === 'en' ? 'English' : 'German'}` : b.link ? 'Updated from the source' : 'Results refreshed');
      await reload();
    } catch (err) {
      toast(err.message, 'error', 8000);
      btn.disabled = false;
      btn.innerHTML = label;
    }
  }

  async function resultsSection(b) {
    const path = `sections/${b.slug}.tex`;
    const exists = (await api('GET', `/api/projects/${ctx.projectId}/files`)).some((f) => f.path === path);
    if (exists && !(await confirmBox('Results section exists', `<code>${esc(path)}</code> already exists. Insert <code>\\input{sections/${esc(b.slug)}}</code> again without changing the file?`, { okLabel: 'Insert' })))
      return false;
    const by = (k) => b.items.filter((i) => i.kind === k && !i.hidden);
    const pieceTex = (it) => (it.kind === 'figure' ? figureTex(b, it) : it.kind === 'table' ? tableTex(b, it)
      : `\\input{lab/${b.slug}/${(it.shown_file || it.file).replace(/\.tex$/i, '')}}\n`);
    if (!exists) {
      const de = b.lang !== 'en';
      const parts = [
        `% ${de ? 'Ergebnisteil' : 'Results section'} "${b.title}" (Folio Lab, lab/${b.slug}/).`,
        `% ${de ? 'Diese Datei gehört Ihnen: frei bearbeiten. Abbildungen, Tabellen und \\labval-Werte folgen bei "Refresh" automatisch.' : 'This file is yours to edit. Figures, tables and \\labval values follow automatically on "Refresh".'}`,
        `\\subsection{${texEsc(b.title)}}`,
        `\\label{sec:${b.slug}}`,
        '',
        ...(b.items.some((i) => i.flow)                 // pieces in a set order (info board frames): keep it
          ? b.items.filter((i) => ['text', 'figure', 'table'].includes(i.kind) && !i.hidden).map(pieceTex)
          : [...by('text'), ...by('figure'), ...by('table')].map(pieceTex)),
      ];
      await api('PUT', fileUrl(ctx.projectId, path), parts.join('\n'));
      await ctx.refreshFiles();
    }
    const ok = await insert(`\\input{sections/${b.slug}}\n`, { graphics: by('figure').length > 0, tables: by('table').length > 0, cite: true });
    if (ok && !exists) toast(`Wrote ${path}; edit it like any other file`, 'info', 4500);
    return ok;
  }

  await reload().catch((e) => toast(e.message, 'error'));
  await modal({
    title: 'Analysis results',
    body,
    wide: true,
    buttons: [{ label: 'Close', value: null }],
    onOpen: (m, close) => {
      m.classList.add('lab-modal');
      closeDialog = () => close(null);
    },
  });
}
