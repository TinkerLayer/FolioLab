// "Import from Folio" in the editor. First the Folio modules of the active project: module → environment → any figure,
// table, value or text block of that environment's report, imported with the references, values and methods text it
// needs and inserted at the cursor (server/folio.js). Below them the older sources: other reports, analysis results,
// shared results / index values and uploaded ZIP or LaTeX projects (server/importer.js). Every import is stored as an
// analysis result lab/<slug>/; the Lab dialog shows whether its source has changed since (live link).
import { api, fileUrl, esc, h, icon, modal, toast } from '../ui.js';
import { insertImported } from './lab.js';

let ctx; // { projectId, refreshFiles(), openLab(slug) }
export function initImport(c) {
  ctx = c;
}

const KINDS = [
  ['figure', 'Figures'], ['table', 'Tables'], ['equation', 'Equations'], ['section', 'Sections'], ['image', 'Images'],
  ['value', 'Values'], ['text', 'Text'], ['data', 'Data'], ['values', 'Values'], ['result', 'Results'],
];
const KIND_ICON = { figure: 'image', table: 'table', equation: 'sigma', section: 'heading', image: 'image', data: 'data', values: 'calc', value: 'calc', text: 'edit', result: 'flask' };
const MODE_HINT = {
  live: 'Live: follows the source; marked out of date when the source changes, one click updates it.',
  pin: 'Pinned: stays as imported; an update is offered when the source changes.',
  copy: 'Copy: no link to the source; it never changes.',
};
const staged = []; // ZIPs uploaded in this editor session: {stage, name}
let lastModule = null; // the module opened last in this editor session

/** LaTeX caption -> readable text. */
const plain = (s) => String(s ?? '').replace(/~?\\cite\{[^}]*\}/g, '').replace(/\\[a-zA-Z]+\{([^}]*)\}/g, '$1').replace(/\\([%&#_$])/g, '$1').replace(/[_^]\{([^}]*)\}/g, '$1').replace(/[{}$\\]/g, '').replace(/\s+/g, ' ').trim();
const when = (iso) => {
  const d = iso ? new Date(iso) : null;
  return d && !isNaN(d) ? d.toLocaleDateString(undefined, { day: '2-digit', month: '2-digit', year: '2-digit' }) : '';
};

export async function openImport() {
  let srcs;
  let folio = { project: null, modules: [] };
  try {
    [srcs, folio] = await Promise.all([
      api('GET', `/api/import/sources?target=${encodeURIComponent(ctx.projectId)}`),
      api('GET', '/api/folio/modules').catch(() => ({ project: null, modules: [] })),
    ]);
  } catch (e) {
    toast(e.message, 'error');
    return;
  }
  let current = null; // {id, type, project?, stage?, module?, env?, title}
  let loaded = null; // {source, pieces, problems} or, for an environment, the pieces of server/folio.js
  let filter = '';
  let query = '';
  let openMod = folio.modules.some((m) => m.id === lastModule) ? lastModule : null;
  let methods = true;
  const chosen = new Set();
  let closeDialog = () => {};

  const body = h(`<div class="lab-dlg imp-dlg">
    <aside class="lab-list imp-sources"></aside>
    <section class="lab-detail imp-detail"></section>
  </div>`);
  const listEl = body.querySelector('.imp-sources');
  const detailEl = body.querySelector('.imp-detail');
  const fileInput = h('<input type="file" accept=".zip,application/zip" hidden>');
  body.appendChild(fileInput);

  const envSub = (e) => {
    if (e.empty) return 'empty';
    const bits = [];
    if (e.files) bits.push(`${e.files} file${e.files === 1 ? '' : 's'}`);
    if (e.title && !e.files) bits.push(e.title);
    if (e.modified) bits.push(when(e.modified));
    return bits.join(' · ') || 'saved state';
  };

  const otherSources = () => [
    ...(srcs.reports.length ? [{ group: 'Other reports' }] : []),
    ...srcs.reports.map((r) => ({ id: `r:${r.id}`, type: 'report', project: r.id, title: r.name, sub: 'figures, tables, equations, sections, values, files' })),
    { group: 'Analysis results' },
    { id: 'results', type: 'results', title: 'All analysis results', sub: `${srcs.results.length} in other reports` },
    { group: 'Shared data and index values' },
    { id: 'suite', type: 'suite', title: srcs.suite.name || 'Active project', sub: `${srcs.suite.shares.length} shared, ${srcs.suite.index.length} index values` },
    { group: 'ZIP or LaTeX project' },
    ...staged.map((z) => ({ id: `z:${z.stage}`, type: 'zip', stage: z.stage, title: z.name, sub: 'uploaded ZIP' })),
    { id: 'upload', type: 'upload', title: 'Upload ZIP…', sub: 'any LaTeX project, also a portable export' },
  ];

  function renderSources() {
    const mods = folio.modules.map((m) => {
      const open = openMod === m.id;
      const n = m.envs.filter((e) => !e.empty).length;
      const dot = `<i class="imp-dot" style="background:${esc(m.color || 'var(--accent)')}"></i>`;
      return `<button class="lab-item imp-mod ${open ? 'open' : ''}" data-mod="${esc(m.id)}" aria-expanded="${open}">
          <b>${dot}${esc(m.name)}<span class="imp-caret">${open ? '▾' : '▸'}</span></b><span>${n ? `${n} environment${n === 1 ? '' : 's'} with content` : 'no saved work yet'}</span></button>
        ${open ? `<div class="imp-envs">${m.envs.map((e) => `<button class="lab-item imp-env ${current && current.id === `e:${m.id}/${e.id}` ? 'on' : ''}" data-env="${esc(m.id)}/${esc(e.id)}" ${e.empty ? 'disabled' : ''}>
            <b>${esc(e.name)}${e.active ? ' <em class="hint">open in module</em>' : ''}</b><span>${esc(envSub(e))}</span></button>`).join('') || '<div class="hint">No environments</div>'}</div>` : ''}`;
    }).join('');
    listEl.innerHTML = `${folio.modules.length ? `<div class="imp-group">Folio modules${folio.project ? ` · ${esc(folio.project.name)}` : ''}</div>${mods}` : ''}
      <details class="imp-more-src" ${current && current.type !== 'env' ? 'open' : ''}><summary class="imp-group">Other sources</summary>
      ${otherSources().map((s) => (s.group ? `<div class="imp-group sub">${esc(s.group)}</div>`
        : `<button class="lab-item ${current && current.id === s.id ? 'on' : ''}" data-src="${esc(s.id)}">
            <b>${s.type === 'upload' ? icon('upload') : ''}${esc(s.title)}</b><span>${esc(s.sub || '')}</span></button>`)).join('')}</details>`;
    listEl.querySelectorAll('[data-mod]').forEach((el) => {
      el.onclick = () => {
        openMod = openMod === el.dataset.mod ? null : el.dataset.mod;
        lastModule = openMod || lastModule;
        renderSources();
      };
    });
    listEl.querySelectorAll('[data-env]').forEach((el) => {
      el.onclick = () => {
        const [module, env] = el.dataset.env.split('/');
        const m = folio.modules.find((x) => x.id === module);
        const e = m.envs.find((x) => x.id === env);
        select({ id: `e:${module}/${env}`, type: 'env', module, env, title: e.name, moduleName: m.name });
      };
    });
    listEl.querySelectorAll('[data-src]').forEach((el) => {
      el.onclick = () => {
        const s = otherSources().find((x) => x.id === el.dataset.src);
        if (s.type === 'upload') return fileInput.click();
        select(s);
      };
    });
  }

  fileInput.onchange = async () => {
    const file = fileInput.files[0];
    fileInput.value = '';
    if (!file) return;
    detailEl.innerHTML = `<div class="hint">${icon('loader')} Reading ${esc(file.name)}…</div>`;
    try {
      const r = await fetch(`/api/import/stage?name=${encodeURIComponent(file.name)}`, { method: 'POST', headers: { 'X-Folio': '1' }, body: file });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.error || r.statusText);
      staged.unshift({ stage: d.stage, name: d.name || file.name });
      await select({ id: `z:${d.stage}`, type: 'zip', stage: d.stage, title: d.name || file.name });
    } catch (e) {
      detailEl.innerHTML = `<div class="hint">${esc(e.message)}</div>`;
    }
  };

  async function select(s) {
    current = s;
    chosen.clear();
    filter = '';
    query = '';
    renderSources();
    detailEl.innerHTML = s.type === 'env'
      ? `<div class="hint">${icon('loader')} ${esc(s.moduleName)} is building the report of “${esc(s.title)}”… (a few seconds the first time)</div>`
      : `<div class="hint">${icon('loader')} Loading…</div>`;
    try {
      if (s.type === 'env') {
        const d = await api('GET', `/api/folio/env?module=${encodeURIComponent(s.module)}&env=${encodeURIComponent(s.env)}&target=${encodeURIComponent(ctx.projectId)}`);
        if (current !== s) return;
        // the methods text comes with the pieces (switch below), so it is not a piece of its own
        loaded = { ...d, source: { title: s.title }, pieces: d.pieces.filter((p) => !(p.kind === 'text' && p.methods)) };
      } else if (s.type === 'results') {
        loaded = {
          source: { type: 'results', title: s.title },
          pieces: srcs.results.map((r) => ({ key: `${r.project}|result:${r.slug}`, kind: 'result', title: r.title, detail: `${r.projectName} · ${r.module_name} · revision ${r.revision}`, preview: r.preview, project: r.project })),
        };
      } else {
        const q = s.type === 'report' ? `type=report&project=${s.project}` : s.type === 'zip' ? `type=zip&stage=${s.stage}` : 'type=suite';
        loaded = await api('GET', `/api/import/pieces?${q}`);
      }
      if (current === s) renderDetail();
    } catch (e) {
      if (current === s) detailEl.innerHTML = `<div class="hint">${esc(e.message)}</div>`;
    }
  }

  const previewUrl = (p) => {
    if (!p.preview || !/\.(png|jpe?g|gif|svg)$/i.test(p.preview)) return null;
    if (current.type === 'env') return `/api/folio/file?stage=${encodeURIComponent(loaded.stage)}&path=${encodeURIComponent(p.preview)}`;
    if (current.type === 'zip') return `/api/import/file?type=zip&stage=${current.stage}&path=${encodeURIComponent(p.preview)}`;
    const project = p.project || current.project;
    return project ? fileUrl(project, p.preview) : null;
  };

  function needsText(p) {
    if (current.type === 'env') {
      if (p.kind === 'value') return p.text || plain(p.latex);
      if (p.kind === 'data') return `${(p.columns || []).length} columns${p.rows ? ` · ${p.rows} rows` : ''} · plot it from the Lab dialog`;
      const n = (p.cites || []).length;
      return n ? `cites ${n} source${n === 1 ? '' : 's'}` : '';
    }
    const n = p.needs;
    if (!n) return p.detail || '';
    const parts = [];
    if (n.files) parts.push(`${n.files} file${n.files === 1 ? '' : 's'}`);
    if (n.cites) parts.push(`${n.cites} reference${n.cites === 1 ? '' : 's'}`);
    if (n.values) parts.push(`${n.values} value${n.values === 1 ? '' : 's'}`);
    if (n.macros.length) parts.push(`macros ${n.macros.map((m) => '\\' + m).join(' ')}`);
    if (n.packages.length) parts.push(`packages ${n.packages.join(', ')}`);
    return parts.join(' · ');
  }

  /** What an environment import brings along, shown folded under the pieces. */
  function comesWith() {
    const refs = loaded.references || [];
    const meth = loaded.methods || [];
    const bits = [`${refs.length} reference${refs.length === 1 ? '' : 's'}`];
    if (meth.length) bits.push('methods text');
    bits.push('all values of the result');
    return `<details class="imp-with"><summary>Comes with: ${esc(bits.join(' · '))}</summary>
      <div class="hint">The references go to <code>lab/references.bib</code> and are printed where the inserted pieces cite them.
      ${meth.length ? 'The methods text holds the equations and assumptions of the evaluation, with its own citations.' : ''}
      The result keeps its link to the environment, so it can be updated when the environment changes.</div>
      ${refs.length ? `<ol class="imp-refs">${refs.map((r) => `<li><code>${esc(r.key)}</code> ${esc(plain(r.title))}</li>`).join('')}</ol>` : ''}</details>`;
  }

  function pieceRow(p) {
    const url = previewUrl(p);
    return `<div class="imp-piece ${chosen.has(p.key) ? 'on' : ''}" data-key="${esc(p.key)}">
      <label class="imp-pick"><input type="checkbox" ${chosen.has(p.key) ? 'checked' : ''}></label>
      ${url ? `<img loading="lazy" src="${esc(url)}" alt="">` : `<span class="imp-ic">${icon(KIND_ICON[p.kind] || 'file')}</span>`}
      <button class="imp-title" title="Show details"><b>${esc(current.type === 'env' ? plain(p.title) : p.title)}</b><span>${esc(needsText(p))}</span></button>
      <div class="imp-more" hidden></div>
    </div>`;
  }

  function renderDetail() {
    if (!current) {
      detailEl.innerHTML = `<div class="lab-empty">${icon('download')}<h3>Import from Folio</h3>
        <p>${folio.modules.length ? 'Open a module on the left and choose one of its environments. Its graphs, tables and values appear here; tick what you need and it goes in at the cursor, with its references, values and methods text.'
          : 'No module of the active project has saved work yet.'}</p>
        <p class="hint">Other reports, analysis results, shared data and ZIP uploads are under “Other sources”.</p></div>`;
      return;
    }
    const env = current.type === 'env';
    const all = loaded.pieces || [];
    const kinds = KINDS.filter(([k]) => all.some((p) => p.kind === k));
    const q = query.trim().toLowerCase();
    const shown = all.filter((p) => (!filter || p.kind === filter) && (!q || `${plain(p.title)} ${p.detail || ''} ${p.text || ''} ${p.label || ''} ${p.key}`.toLowerCase().includes(q)));
    const link = loaded.source && loaded.source.link;
    const figs = env ? shown.filter((p) => p.kind === 'figure') : [];
    const vals = env ? shown.filter((p) => p.kind === 'value') : [];
    const rows = env ? shown.filter((p) => p.kind !== 'figure' && p.kind !== 'value') : shown;
    detailEl.innerHTML = `
      <div class="imp-head">
        <div class="grow"><h3>${esc(env ? current.title : loaded.source.title || current.title)}</h3>
          ${env ? `<div class="hint">${esc(current.moduleName)}${loaded.summary ? ` · ${esc(plain(loaded.summary).slice(0, 160))}` : ''}</div>` : ''}
          ${link ? `<div class="hint">${link.reconnects ? `Exported from the report <b>${esc(link.project.name)}</b>, which is here: imports link to that report.` : `Portable export of <b>${esc(link.project.name)}</b> (that report is not in this Folio).`}</div>` : ''}
          ${(loaded.problems || []).length ? `<div class="hint">${esc(loaded.problems.join(' '))}</div>` : ''}</div>
        ${all.length > 8 ? `<input class="input sm imp-search" type="search" placeholder="Search" value="${esc(query)}">` : ''}
      </div>
      ${kinds.length > 1 ? `<div class="imp-kinds"><button class="chip ${filter ? '' : 'on'}" data-kind="">All ${all.length}</button>${kinds.map(([k, l]) => `<button class="chip ${filter === k ? 'on' : ''}" data-kind="${k}">${l} ${all.filter((p) => p.kind === k).length}</button>`).join('')}</div>` : ''}
      ${figs.length ? `<div class="imp-tiles">${figs.map((p) => {
        const url = previewUrl(p);
        return `<button class="imp-tile ${chosen.has(p.key) ? 'on' : ''}" data-key="${esc(p.key)}" title="${esc(plain(p.title))}">
          ${url ? `<img loading="lazy" src="${esc(url)}" alt="">` : `<span class="imp-ic">${icon('image')}</span>`}
          <span class="cap">${esc(plain(p.title))}</span>${(p.cites || []).length ? `<span class="hint">cites ${p.cites.length}</span>` : ''}<i class="imp-check">${icon('check')}</i></button>`;
      }).join('')}</div>` : ''}
      ${rows.length ? `<div class="imp-pieces">${rows.map(pieceRow).join('')}</div>` : ''}
      ${vals.length ? `<div class="imp-valgrid">${vals.map((p) => `<button class="lab-val imp-val ${chosen.has(p.key) ? 'on' : ''}" data-key="${esc(p.key)}" title="\\labval{…}{${esc(p.id)}}"><span>${esc(plain(p.title))}</span><b>${esc(p.text || plain(p.latex))}</b></button>`).join('')}</div>` : ''}
      ${!shown.length ? `<div class="hint">${all.length ? 'Nothing matches.' : 'This source has nothing to import.'}</div>` : ''}
      ${env ? comesWith() : ''}`;
    const search = detailEl.querySelector('.imp-search');
    if (search) {
      search.oninput = () => {
        query = search.value;
        const pos = search.selectionStart;
        renderDetail();
        const s2 = detailEl.querySelector('.imp-search');
        s2.focus();
        s2.setSelectionRange(pos, pos);
      };
    }
    detailEl.querySelectorAll('[data-kind]').forEach((el) => (el.onclick = () => {
      filter = el.dataset.kind;
      renderDetail();
    }));
    const toggle = (key, el) => {
      if (chosen.has(key)) chosen.delete(key);
      else chosen.add(key);
      el.classList.toggle('on', chosen.has(key));
      updateButton();
    };
    detailEl.querySelectorAll('.imp-tile, .imp-val').forEach((el) => (el.onclick = () => toggle(el.dataset.key, el)));
    detailEl.querySelectorAll('.imp-piece').forEach((row) => {
      const key = row.dataset.key;
      const p = all.find((x) => x.key === key);
      row.querySelector('input').onchange = (e) => {
        if (e.target.checked) chosen.add(key);
        else chosen.delete(key);
        row.classList.toggle('on', e.target.checked);
        updateButton();
      };
      row.querySelector('.imp-title').onclick = () => {
        const more = row.querySelector('.imp-more');
        more.hidden = !more.hidden;
        if (more.hidden || more.dataset.done) return;
        more.dataset.done = '1';
        const url = previewUrl(p);
        const n = p.needs || {};
        more.innerHTML = `${url ? `<img class="imp-big" src="${esc(url)}" alt="">` : ''}
          ${p.snippet ? `<pre class="imp-snip">${esc(p.snippet)}</pre>` : ''}
          ${p.notes ? `<div class="hint">${esc(plain(p.notes))}</div>` : ''}
          ${p.values ? `<div class="imp-vals">${p.values.map((v) => `<span><i>${esc(v.label || v.key)}</i> ${esc(v.text || '')}</span>`).join('')}</div>` : ''}
          ${(p.cites || []).length && env ? `<div class="hint">Cites ${esc(p.cites.map((c) => plain(c.title)).join('; '))}</div>` : ''}
          ${(n.missing || []).length ? `<div class="hint">Not found in the source: ${esc(n.missing.join(', '))}</div>` : ''}
          ${(n.missingKeys || []).length ? `<div class="hint">Cited without a .bib entry: ${esc(n.missingKeys.join(', '))}</div>` : ''}
          ${p.detail && p.needs ? `<div class="hint">${esc(p.detail)}</div>` : ''}
          ${p.unit ? `<div class="hint">In <code>${esc(p.unit)}</code></div>` : ''}`;
      };
    });
    updateButton();
  }

  let importBtn = null;
  let modeSel = null;
  let methodsBox = null;
  function updateButton() {
    if (methodsBox) methodsBox.hidden = !(current && current.type === 'env' && (loaded.methods || []).length);
    if (!importBtn) return;
    importBtn.disabled = !chosen.size;
    const env = current && current.type === 'env';
    importBtn.innerHTML = `${icon('download')}${env ? 'Insert' : 'Import'}${chosen.size ? ` ${chosen.size}` : ''}`;
  }

  async function doEnvImport(mode) {
    const order = loaded.pieces.map((p) => p.key);
    const keys = [...chosen].sort((a, b) => order.indexOf(a) - order.indexOf(b));
    const r = await api('POST', `/api/projects/${ctx.projectId}/import`, { source: { type: 'env', stage: loaded.stage }, keys, mode, methods });
    const man = r.results[0];
    await ctx.refreshFiles();
    closeDialog();
    const res = await insertImported(man, keys, { methods: methods && (loaded.methods || []).length > 0 });
    const nref = (loaded.references || []).length;
    toast(`${res.inserted ? 'Inserted' : 'Imported'} ${keys.length} piece${keys.length === 1 ? '' : 's'} from “${current.title}”${nref ? ` with ${nref} reference${nref === 1 ? '' : 's'}` : ''} · in the Lab dialog as “${plain(man.title)}”`, 'ok', 5000);
    if (res.data) toast('Data series are in the Lab dialog: choose the axes there and insert a plot.', 'info', 7000);
    if ((r.warnings || []).length) toast(r.warnings.slice(0, 4).join(' · '), 'info', 12000);
    return true;
  }

  async function doImport() {
    if (!chosen.size) return false;
    const mode = modeSel.value;
    importBtn.disabled = true;
    importBtn.innerHTML = `${icon('loader')}Importing…`;
    try {
      if (current.type === 'env') return await doEnvImport(mode);
      const groups = new Map(); // source JSON -> keys
      for (const key of chosen) {
        let source;
        let k = key;
        if (current.type === 'results') {
          const [project, rest] = key.split('|');
          source = { type: 'report', project };
          k = rest;
        } else source = current.type === 'report' ? { type: 'report', project: current.project } : current.type === 'zip' ? { type: 'zip', stage: current.stage } : { type: 'suite' };
        const sk = JSON.stringify(source);
        if (!groups.has(sk)) groups.set(sk, []);
        groups.get(sk).push(k);
      }
      let last = null;
      const warnings = [];
      for (const [sk, keys] of groups) {
        const r = await api('POST', `/api/projects/${ctx.projectId}/import`, { source: JSON.parse(sk), keys, mode });
        last = r.results[r.results.length - 1] || last;
        warnings.push(...(r.warnings || []));
      }
      await ctx.refreshFiles();
      toast(`Imported ${chosen.size} piece${chosen.size === 1 ? '' : 's'}${warnings.length ? ' – see the notes in the next dialog' : ''}`, 'ok', 4000);
      if (warnings.length) toast(warnings.slice(0, 4).join(' · '), 'info', 12000);
      closeDialog();
      if (last) ctx.openLab(last.slug);
      return true;
    } catch (e) {
      toast(e.message, 'error', 8000);
      updateButton();
      return false;
    }
  }

  renderSources();
  renderDetail();
  await modal({
    title: 'Import from Folio',
    body,
    wide: true,
    buttons: [{ label: 'Cancel', value: null }, { label: 'Import', value: 'go', cls: 'primary' }],
    validate: async () => {
      await doImport();
      return false; // doImport closes the dialog itself
    },
    onOpen: (m, close) => {
      m.classList.add('lab-modal');
      closeDialog = () => close(null);
      const footer = m.querySelector('footer');
      importBtn = footer.querySelector('.btn.primary');
      const wrap = h(`<div class="imp-foot">
        <label class="imp-mode" title="${esc(MODE_HINT.live)}">Link
          <select class="input sm"><option value="live">Live</option><option value="pin">Pinned</option><option value="copy">Copy</option></select></label>
        <label class="imp-methods" title="Adds the paragraph with the equations and assumptions of the evaluation after the pieces" hidden>
          <input type="checkbox" checked> with methods text</label></div>`);
      modeSel = wrap.querySelector('select');
      modeSel.onchange = () => (wrap.querySelector('.imp-mode').title = MODE_HINT[modeSel.value]);
      methodsBox = wrap.querySelector('.imp-methods');
      methodsBox.querySelector('input').onchange = (e) => (methods = e.target.checked);
      footer.insertBefore(wrap, footer.firstChild);
      updateButton();
    },
  });
}
