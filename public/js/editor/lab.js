// Folio Lab in the editor: browse the analysis results stored in this project (lab/<slug>/) and insert
// figures, tables, values, data plots, citations and text. The main file gets the few lines it needs
// (\input{lab/labdata}, packages, bibliography) the first time something is inserted.
import { api, fileUrl, esc, h, icon, modal, confirmBox, toast, store } from '../ui.js';

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

// ---------------------------------------------------------------- snippets
function figureTex(b, it, width) {
  return `\\begin{figure}[htbp]\n\t\\centering\n\t\\includegraphics[width=${width || it.width || '0.9'}\\linewidth]{lab/${b.slug}/${it.file.replace(/\.pdf$/i, '')}}\n\t\\caption{${it.caption}}\n\t\\label{${it.label}}\n\\end{figure}\n`;
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
  const from = l.type === 'suite' ? 'the shared data of the project' : l.type === 'zip' ? `the ZIP ${l.name || ''}`.trim() : `"${l.title || l.project || ''}"`;
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
    if (!bundles.some((b) => b.slug === current)) current = bundles[0]?.slug || null;
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
    listEl.innerHTML = bundles
      .map(
        (b) => `<button class="lab-item ${b.slug === current ? 'on' : ''}" data-slug="${esc(b.slug)}">
          <b>${esc(b.title)}</b><span>${esc(b.module_name || b.module)} · ${esc(b.lang === 'en' ? 'EN' : 'DE')} · ${esc(new Date(b.updated).toLocaleString())}</span></button>`
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

  function renderDetail() {
    const b = bundles.find((x) => x.slug === current);
    if (!b) {
      detailEl.innerHTML = `<div class="lab-empty">${icon('chart')}<h3>No analysis results in this report yet</h3>
        <p>Open an analysis from the <a href="/" target="_blank">Folio Lab home page</a> (for example <b>Zugversuch</b>), load a measurement and press <b>Zum Bericht …</b>. Choose this report as the target. The results then appear here, ready to insert.</p></div>`;
      return;
    }
    const by = (k) => b.items.filter((i) => i.kind === k);
    const values = by('values').flatMap((v) => v.values || []);
    const other = b.lang === 'en' ? 'de' : 'en';
    const imported = b.module === 'import';
    detailEl.innerHTML = `
      <div class="lab-head">
        <div class="grow"><h3>${esc(b.title)}</h3><div class="muted">${esc(b.summary || '')}</div>
          <div class="hint">Stored in <code>lab/${esc(b.slug)}/</code> · ${imported ? `imported from ${esc(b.link ? b.link.title || '' : '')}` : `from <a href="/m/${esc(b.module)}/" target="_blank">${esc(b.module_name || b.module)}</a>${b.provenance && b.provenance.module_version ? ` ${esc(b.provenance.module_version)}` : ''}`}</div>
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
      ${by('figure').length ? `<h4>${KIND_LABEL.figure}</h4><div class="lab-figs">${by('figure').map((it) => `
        <button class="lab-fig" data-fig="${esc(it.id)}" title="Insert figure">
          <img loading="lazy" src="${esc(fileUrl(ctx.projectId, `lab/${b.slug}/${it.preview || it.file}`))}&v=${encodeURIComponent(b.updated)}" alt="">
          <span class="cap">${esc(plain(it.caption))}</span>${srcHint(it, true)}</button>`).join('')}</div>` : ''}
      ${by('table').length ? `<h4>${KIND_LABEL.table}</h4><div class="lab-rows">${by('table').map((it) => `
        <div class="lab-row"><span class="grow">${esc(plain(it.caption))}${srcHint(it)}</span>
          <button class="btn sm" data-tab="${esc(it.id)}">${icon('table')}Insert table</button></div>`).join('')}</div>` : ''}
      ${values.length ? `<h4>${KIND_LABEL.values} <span class="hint">click to insert <code>\\labval</code>; the number updates when the results are refreshed</span></h4>
        <div class="lab-vals">${values.map((v) => `<button class="lab-val" data-val="${esc(v.key)}" title="\\labval{${esc(b.slug)}}{${esc(v.key)}}"><span>${esc(plain(v.label))}</span><b>${esc(v.text || plain(v.latex))}</b></button>`).join('')}</div>` : ''}
      ${by('data').length ? `<h4>${KIND_LABEL.data}</h4><div class="lab-rows">${by('data').map((it) => {
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
      ${by('text').length ? `<h4>${KIND_LABEL.text}</h4><div class="lab-rows">${by('text').map((it) => `
        <div class="lab-row"><span class="grow">${esc(it.title)}</span>
          <button class="btn sm" data-text="${esc(it.id)}" title="Paste the paragraph so you can edit it">${icon('edit')}Insert editable</button>
          <button class="btn sm ghost" data-textin="${esc(it.id)}" title="\\input the file; it changes when the results are refreshed">${icon('link')}Insert linked</button></div>`).join('')}</div>` : ''}
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
    detailEl.querySelectorAll('[data-textin]').forEach((el) => (el.onclick = async () => done(await insert(`\\input{lab/${b.slug}/text-${el.dataset.textin}}\n`, { cite: true }))));
    detailEl.querySelectorAll('[data-text]').forEach(
      (el) =>
        (el.onclick = async () => {
          const it = item('text', el.dataset.text);
          const r = await api('GET', fileUrl(ctx.projectId, `lab/${b.slug}/${it.file}`), undefined, { raw: true });
          done(await insert((await r.text()).trim() + '\n', { cite: true }));
        })
    );
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
      const ok = await confirmBox(
        'Remove results',
        `Remove <b>${esc(b.title)}</b> (<code>lab/${esc(b.slug)}/</code>) from this report? Places in your text that use it will show <b>??</b> or missing figures until you remove them.`,
        { okLabel: 'Remove', danger: true }
      );
      if (!ok) return;
      try {
        await api('DELETE', `/api/projects/${ctx.projectId}/lab/${b.slug}`);
        await ctx.refreshFiles();
        toast('Results removed');
        await reload();
      } catch (err) {
        toast(err.message, 'error');
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
    const by = (k) => b.items.filter((i) => i.kind === k);
    if (!exists) {
      const de = b.lang !== 'en';
      const parts = [
        `% ${de ? 'Ergebnisteil' : 'Results section'} "${b.title}" (Folio Lab, lab/${b.slug}/).`,
        `% ${de ? 'Diese Datei gehört Ihnen: frei bearbeiten. Abbildungen, Tabellen und \\labval-Werte folgen bei "Refresh" automatisch.' : 'This file is yours to edit. Figures, tables and \\labval values follow automatically on "Refresh".'}`,
        `\\subsection{${texEsc(b.title)}}`,
        `\\label{sec:${b.slug}}`,
        '',
        ...by('text').map((it) => `\\input{lab/${b.slug}/text-${it.id}}\n`),
        ...by('figure').map((it) => figureTex(b, it)),
        ...by('table').map((it) => tableTex(b, it)),
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
