// "Import" in the editor – bring figures, tables, equations, sections, images, data and values from other
// reports, analysis results, shared results / index values and uploaded ZIP or LaTeX projects into this report.
// The server (server/importer.js) stores each import as an analysis result lab/<slug>/; the Lab dialog then inserts
// its pieces and shows whether the source has changed since (live link).
import { api, fileUrl, esc, h, icon, modal, toast } from '../ui.js';

let ctx; // { projectId, refreshFiles(), openLab(slug) }
export function initImport(c) {
  ctx = c;
}

const KINDS = [
  ['figure', 'Figures'], ['table', 'Tables'], ['equation', 'Equations'], ['section', 'Sections'], ['image', 'Images'],
  ['data', 'Data'], ['values', 'Values'], ['result', 'Results'],
];
const KIND_ICON = { figure: 'image', table: 'table', equation: 'sigma', section: 'heading', image: 'image', data: 'data', values: 'calc', result: 'flask' };
const MODE_HINT = {
  live: 'Live: follows the source; marked out of date when the source changes, one click updates it.',
  pin: 'Pinned: stays as imported; an update is offered when the source changes.',
  copy: 'Copy: no link to the source; it never changes.',
};
const staged = []; // ZIPs uploaded in this editor session: {stage, name}

export async function openImport() {
  let srcs;
  try {
    srcs = await api('GET', `/api/import/sources?target=${encodeURIComponent(ctx.projectId)}`);
  } catch (e) {
    toast(e.message, 'error');
    return;
  }
  let current = null; // {id, type, project?, stage?, title}
  let loaded = null; // {source, pieces, problems}
  let filter = '';
  let query = '';
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

  const sourcesList = () => [
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
    listEl.innerHTML = sourcesList()
      .map((s) => (s.group ? `<div class="imp-group">${esc(s.group)}</div>`
        : `<button class="lab-item ${current && current.id === s.id ? 'on' : ''}" data-src="${esc(s.id)}">
            <b>${s.type === 'upload' ? icon('upload') : ''}${esc(s.title)}</b><span>${esc(s.sub || '')}</span></button>`))
      .join('');
    listEl.querySelectorAll('[data-src]').forEach((el) => {
      el.onclick = () => {
        const s = sourcesList().find((x) => x.id === el.dataset.src);
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
    detailEl.innerHTML = `<div class="hint">${icon('loader')} Loading…</div>`;
    try {
      if (s.type === 'results') {
        loaded = {
          source: { type: 'results', title: s.title },
          pieces: srcs.results.map((r) => ({ key: `${r.project}|result:${r.slug}`, kind: 'result', title: r.title, detail: `${r.projectName} · ${r.module_name} · revision ${r.revision}`, preview: r.preview, project: r.project })),
        };
      } else {
        const q = s.type === 'report' ? `type=report&project=${s.project}` : s.type === 'zip' ? `type=zip&stage=${s.stage}` : 'type=suite';
        loaded = await api('GET', `/api/import/pieces?${q}`);
      }
      renderDetail();
    } catch (e) {
      detailEl.innerHTML = `<div class="hint">${esc(e.message)}</div>`;
    }
  }

  const previewUrl = (p) => {
    if (!p.preview || !/\.(png|jpe?g|gif|svg)$/i.test(p.preview)) return null;
    if (current.type === 'zip') return `/api/import/file?type=zip&stage=${current.stage}&path=${encodeURIComponent(p.preview)}`;
    const project = p.project || current.project;
    return project ? fileUrl(project, p.preview) : null;
  };

  function needsText(p) {
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

  function renderDetail() {
    if (!current) {
      detailEl.innerHTML = `<div class="lab-empty">${icon('download')}<h3>Import into this report</h3>
        <p>Choose a source on the left: another report, an analysis result, the shared data and index values of the project, or a ZIP of any LaTeX project.
        Figures, equations and sections bring their files, references, macros and values with them.</p></div>`;
      return;
    }
    const all = loaded.pieces || [];
    const kinds = KINDS.filter(([k]) => all.some((p) => p.kind === k));
    const q = query.trim().toLowerCase();
    const shown = all.filter((p) => (!filter || p.kind === filter) && (!q || `${p.title} ${p.detail || ''} ${p.label || ''} ${p.key}`.toLowerCase().includes(q)));
    const link = loaded.source && loaded.source.link;
    detailEl.innerHTML = `
      <div class="imp-head">
        <div class="grow"><h3>${esc(loaded.source.title || current.title)}</h3>
          ${link ? `<div class="hint">${link.reconnects ? `Exported from the report <b>${esc(link.project.name)}</b>, which is here: imports link to that report.` : `Portable export of <b>${esc(link.project.name)}</b> (that report is not in this Folio).`}</div>` : ''}
          ${(loaded.problems || []).length ? `<div class="hint">${esc(loaded.problems.join(' '))}</div>` : ''}</div>
        <input class="input sm imp-search" type="search" placeholder="Search" value="${esc(query)}">
      </div>
      ${kinds.length > 1 ? `<div class="imp-kinds"><button class="chip ${filter ? '' : 'on'}" data-kind="">All ${all.length}</button>${kinds.map(([k, l]) => `<button class="chip ${filter === k ? 'on' : ''}" data-kind="${k}">${l} ${all.filter((p) => p.kind === k).length}</button>`).join('')}</div>` : ''}
      <div class="imp-pieces">${shown.length ? shown.map((p) => {
        const url = previewUrl(p);
        return `<div class="imp-piece ${chosen.has(p.key) ? 'on' : ''}" data-key="${esc(p.key)}">
          <label class="imp-pick"><input type="checkbox" ${chosen.has(p.key) ? 'checked' : ''}></label>
          ${url ? `<img loading="lazy" src="${esc(url)}" alt="">` : `<span class="imp-ic">${icon(KIND_ICON[p.kind] || 'file')}</span>`}
          <button class="imp-title" title="Show details"><b>${esc(p.title)}</b><span>${esc(needsText(p))}</span></button>
          <div class="imp-more" hidden></div>
        </div>`;
      }).join('') : `<div class="hint">${all.length ? 'Nothing matches.' : 'This source has nothing to import.'}</div>`}</div>`;
    const search = detailEl.querySelector('.imp-search');
    search.oninput = () => {
      query = search.value;
      const pos = search.selectionStart;
      renderDetail();
      const s2 = detailEl.querySelector('.imp-search');
      s2.focus();
      s2.setSelectionRange(pos, pos);
    };
    detailEl.querySelectorAll('[data-kind]').forEach((el) => (el.onclick = () => {
      filter = el.dataset.kind;
      renderDetail();
    }));
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
          ${p.values ? `<div class="imp-vals">${p.values.map((v) => `<span><i>${esc(v.label || v.key)}</i> ${esc(v.text || '')}</span>`).join('')}</div>` : ''}
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
  function updateButton() {
    if (!importBtn) return;
    importBtn.disabled = !chosen.size;
    importBtn.innerHTML = `${icon('download')}Import${chosen.size ? ` ${chosen.size}` : ''}`;
  }

  async function doImport() {
    if (!chosen.size) return false;
    const mode = modeSel.value;
    importBtn.disabled = true;
    importBtn.innerHTML = `${icon('loader')}Importing…`;
    try {
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
    title: 'Import',
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
      const wrap = h(`<label class="imp-mode" title="${esc(MODE_HINT.live)}">Link
        <select class="input sm"><option value="live">Live</option><option value="pin">Pinned</option><option value="copy">Copy</option></select></label>`);
      modeSel = wrap.querySelector('select');
      modeSel.onchange = () => (wrap.title = MODE_HINT[modeSel.value]);
      footer.insertBefore(wrap, footer.firstChild);
      updateButton();
    },
  });
}
