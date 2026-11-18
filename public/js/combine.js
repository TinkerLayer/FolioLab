// "Combine projects" window: collect ZIPs / existing projects, order them, merge them into one project.
import { api, esc, h, icon, modal, toast } from './ui.js';

const ENGINE = { pdflatex: 'pdfLaTeX', xelatex: 'XeLaTeX', lualatex: 'LuaLaTeX' };
const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;

async function uploadStage(file) {
  const r = await fetch(`/api/combine/stage?name=${encodeURIComponent(file.name)}`, { method: 'POST', headers: { 'X-Folio': '1' }, body: file });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || r.statusText);
  return d;
}

export async function openCombine({ projects = [] } = {}) {
  const items = []; // { key, status: 'loading'|'ready'|'error', info, file, error }
  let seq = 0;
  let result = null;

  const body = h(`<div class="cmb-root">
    <p class="cmb-intro">Add the <b>.zip</b> exports of the projects you want to merge, then drag them into the order they should appear in.
      Images, data and bibliographies are merged into one folder tree; the text of each project becomes one part of the new document.</p>
    <div class="cmb-drop" tabindex="0">
      ${icon('upload')}
      <div><b>Drop .zip files here</b> <span class="muted">or</span> <button type="button" class="btn sm" data-browse>Browse…</button></div>
      <input type="file" accept=".zip,application/zip" multiple hidden>
    </div>
    <div class="cmb-existing">
      <span class="muted">Or add a project from this computer:</span>
      <select class="input"><option value="">Choose a project…</option>${projects
        .map((p) => `<option value="${esc(p.id)}">${esc(p.name)}</option>`)
        .join('')}</select>
    </div>
    <div class="cmb-list" aria-label="Parts in order"></div>
    <div class="cmb-options">
      <label class="field"><span>Name of the combined project</span><input class="input" data-name placeholder="Combined document"></label>
      <label class="check"><input type="checkbox" data-newpage checked><span>Start each part on a new page</span></label>
      <label class="check"><input type="checkbox" data-authors checked><span>List the authors of all parts on the title page</span></label>
    </div>
  </div>`);
  const list = body.querySelector('.cmb-list');
  const drop = body.querySelector('.cmb-drop');
  const fileInput = drop.querySelector('input[type=file]');
  const select = body.querySelector('.cmb-existing select');
  const nameInput = body.querySelector('[data-name]');
  let nameTouched = false;
  nameInput.oninput = () => (nameTouched = true);
  let combineBtn = null;

  function suggestName() {
    if (nameTouched) return;
    const ready = items.filter((i) => i.status === 'ready');
    nameInput.value = ready.length >= 2 ? ready.map((i) => i.info.name).join(' + ').slice(0, 80) : '';
  }

  function render() {
    list.innerHTML = '';
    if (!items.length) {
      list.innerHTML = `<div class="cmb-empty">No projects added yet. Add at least two.</div>`;
    }
    items.forEach((it, idx) => {
      const card = h(`<div class="cmb-card ${it.status}" draggable="${it.status !== 'loading'}" data-key="${it.key}"></div>`);
      const num = `<div class="cmb-num">${idx + 1}</div>`;
      const handle = `<div class="cmb-grip" title="Drag to reorder">${icon('grip')}</div>`;
      const controls = `<div class="cmb-ctrl">
        <button type="button" class="btn ghost icon sm" data-up title="Move up" ${idx === 0 ? 'disabled' : ''}>${icon('chevron-up')}</button>
        <button type="button" class="btn ghost icon sm" data-down title="Move down" ${idx === items.length - 1 ? 'disabled' : ''}>${icon('chevron-down')}</button>
        <button type="button" class="btn ghost icon sm danger" data-remove title="Remove">${icon('x')}</button></div>`;
      let main;
      if (it.status === 'loading') {
        main = `<div class="cmb-main"><div class="cmb-title">${esc(it.label)}</div><div class="cmb-meta">${icon('loader', 'spin')} Reading project…</div></div>`;
      } else if (it.status === 'error') {
        main = `<div class="cmb-main"><div class="cmb-title">${esc(it.label)}</div><div class="cmb-meta err">${icon('alert')} ${esc(it.error)}</div></div>`;
      } else {
        const s = it.info;
        const facts = [
          s.mainFile,
          ENGINE[s.engine] || s.engine,
          s.docClass && `class ${s.docClass}`,
          plural(s.counts.files + 1, 'file'),
          s.counts.images && plural(s.counts.images, 'image'),
          s.counts.references && plural(s.counts.references, 'reference'),
        ].filter(Boolean);
        const chips = s.sections
          .slice(0, 6)
          .map((x) => `<span class="cmb-chip">${esc(x)}</span>`)
          .join('');
        const more = s.sectionCount > 6 ? `<span class="cmb-chip more">+${s.sectionCount - 6}</span>` : '';
        main = `<div class="cmb-main">
          <div class="cmb-title">${esc(s.name)} ${idx === 0 ? '<span class="cmb-base" title="The first part provides the document class, page layout, preamble and title page">Base: layout &amp; title</span>' : ''}
            <span class="cmb-src">${esc(s.project ? 'project on this computer' : s.source || '')}</span></div>
          ${s.title || s.author ? `<div class="cmb-doc">${s.title ? `<b>${esc(s.title)}</b>` : ''}${s.title && s.author ? ' · ' : ''}${s.author ? esc(s.author) : ''}</div>` : ''}
          <div class="cmb-meta">${facts.map(esc).join(' · ')}</div>
          ${chips || more ? `<div class="cmb-chips">${chips}${more}</div>` : ''}
        </div>`;
      }
      card.innerHTML = handle + num + main + controls;
      card.querySelector('[data-up]').onclick = () => move(idx, idx - 1);
      card.querySelector('[data-down]').onclick = () => move(idx, idx + 1);
      card.querySelector('[data-remove]').onclick = () => remove(idx);
      card.addEventListener('dragstart', (e) => {
        dragKey = it.key;
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/x-folio-part', it.key);
        requestAnimationFrame(() => card.classList.add('dragging'));
      });
      card.addEventListener('dragend', () => {
        dragKey = null;
        card.classList.remove('dragging');
        indicator.remove();
      });
      list.appendChild(card);
    });
    const ready = items.filter((i) => i.status === 'ready').length;
    const busy = items.some((i) => i.status === 'loading');
    const base = items[0]?.status === 'ready' ? items[0].info : null;
    const chapterParts = items.slice(1).filter((i) => i.status === 'ready' && i.info.usesChapters);
    if (base && !base.classHasChapters && chapterParts.length) {
      const fix = items.find((i) => i.status === 'ready' && i.info.classHasChapters);
      list.appendChild(
        h(`<div class="cmb-warn">${icon('alert')}<div><b>${chapterParts.map((i) => esc(i.info.name)).join(', ')}</b> use${chapterParts.length === 1 ? 's' : ''} chapters, but the first project's class
          (<code>${esc(base.docClass || 'unknown')}</code>) has none.${fix ? ` Move <b>${esc(fix.info.name)}</b> to the top to use its class.` : ' The combined document will not compile until those chapters become sections.'}</div></div>`)
      );
    }
    if (combineBtn) {
      combineBtn.disabled = ready < 2 || busy;
      combineBtn.title = ready < 2 ? 'Add at least two projects' : busy ? 'Waiting for uploads…' : '';
    }
    suggestName();
  }

  function move(from, to) {
    if (to < 0 || to >= items.length || from === to) return;
    const [it] = items.splice(from, 1);
    items.splice(to, 0, it);
    render();
  }
  function remove(idx) {
    const [it] = items.splice(idx, 1);
    if (it.info?.stage) api('DELETE', `/api/combine/stage/${it.info.stage}`).catch(() => {});
    render();
  }

  // ---- reordering by drag and drop
  let dragKey = null;
  const indicator = h('<div class="cmb-insert"></div>');
  const dropIndex = (y) => {
    const cards = [...list.querySelectorAll('.cmb-card:not(.dragging)')];
    for (const c of cards) {
      const r = c.getBoundingClientRect();
      if (y < r.top + r.height / 2) return c;
    }
    return null;
  };
  list.addEventListener('dragover', (e) => {
    if (!dragKey) return;
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = 'move';
    const before = dropIndex(e.clientY);
    if (before) list.insertBefore(indicator, before);
    else list.appendChild(indicator);
  });
  list.addEventListener('drop', (e) => {
    if (!dragKey) return;
    e.preventDefault();
    e.stopPropagation();
    const from = items.findIndex((i) => i.key === dragKey);
    const beforeEl = indicator.nextElementSibling;
    indicator.remove();
    const [it] = items.splice(from, 1);
    const beforeIdx = beforeEl ? items.findIndex((i) => i.key === beforeEl.dataset.key) : -1;
    items.splice(beforeIdx < 0 ? items.length : beforeIdx, 0, it);
    dragKey = null;
    render();
  });

  // ---- adding parts
  function addFiles(files) {
    const zips = [...files].filter((f) => /\.zip$/i.test(f.name));
    if (zips.length < files.length) toast('Only .zip files can be combined; other files were ignored.', 'error');
    for (const file of zips) {
      const it = { key: 'k' + ++seq, status: 'loading', label: file.name };
      items.push(it);
      uploadStage(file)
        .then((info) => Object.assign(it, { status: 'ready', info }))
        .catch((e) => Object.assign(it, { status: 'error', error: e.message }))
        .finally(() => (items.includes(it) ? render() : it.info?.stage && api('DELETE', `/api/combine/stage/${it.info.stage}`).catch(() => {})));
    }
    render();
  }
  async function addProject(id) {
    const p = projects.find((x) => x.id === id);
    const it = { key: 'k' + ++seq, status: 'loading', label: p ? p.name : 'Project' };
    items.push(it);
    render();
    try {
      it.info = await api('POST', '/api/combine/analyze', { project: id });
      it.status = 'ready';
    } catch (e) {
      Object.assign(it, { status: 'error', error: e.message });
    }
    render();
  }
  drop.querySelector('[data-browse]').onclick = () => fileInput.click();
  drop.onkeydown = (e) => (e.key === 'Enter' || e.key === ' ') && e.target === drop && (e.preventDefault(), fileInput.click());
  fileInput.onchange = () => {
    addFiles(fileInput.files);
    fileInput.value = '';
  };
  select.onchange = () => {
    if (select.value) addProject(select.value);
    select.value = '';
  };

  const cleanupStages = () => {
    for (const it of items) if (it.info?.stage) api('DELETE', `/api/combine/stage/${it.info.stage}`).catch(() => {});
  };

  const choice = await modal({
    title: 'Combine projects',
    body,
    wide: true,
    buttons: [
      { label: 'Cancel', value: null },
      { label: 'Combine', value: 'go', cls: 'primary' },
    ],
    onOpen(m) {
      m.classList.add('cmb-modal');
      combineBtn = m.querySelector('footer .btn.primary');
      combineBtn.innerHTML = `${icon('merge')}Combine`;
      // File drops anywhere on the dialog add ZIPs here instead of importing them as projects.
      const back = m.closest('.modal-backdrop');
      back.classList.add('cmb-backdrop');
      back.addEventListener('dragover', (e) => {
        if (dragKey || !e.dataTransfer.types.includes('Files')) return;
        e.preventDefault();
        e.stopPropagation();
        drop.classList.add('over');
      });
      back.addEventListener('dragleave', (e) => {
        if (!back.contains(e.relatedTarget)) drop.classList.remove('over');
      });
      back.addEventListener('drop', (e) => {
        if (dragKey) return;
        e.preventDefault();
        e.stopPropagation();
        drop.classList.remove('over');
        if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
      });
      render();
    },
    async validate(v, m) {
      const parts = items.filter((i) => i.status === 'ready');
      if (parts.length < 2) {
        toast('Add at least two projects to combine.', 'error');
        return false;
      }
      combineBtn.disabled = true;
      combineBtn.innerHTML = `${icon('loader', 'spin')}Combining…`;
      try {
        result = await api('POST', '/api/combine', {
          name: nameInput.value.trim(),
          parts: parts.map((i) => (i.info.stage ? { stage: i.info.stage, name: i.info.name } : { project: i.info.project, name: i.info.name })),
          options: { newPage: body.querySelector('[data-newpage]').checked, mergeAuthors: body.querySelector('[data-authors]').checked },
        });
        return true;
      } catch (e) {
        toast('Combining failed: ' + e.message, 'error');
        combineBtn.innerHTML = `${icon('merge')}Combine`;
        render();
        return false;
      }
    },
  });
  cleanupStages();
  if (!choice || !result) return null;
  return showReport(result);
}

async function showReport({ project, report: R }) {
  const sec = (title, rows, cls = '') =>
    rows.length ? `<details class="cmb-sec ${cls}" ${cls === 'warn' ? 'open' : ''}><summary>${esc(title)} <span class="cmb-count">${rows.length}</span></summary><ul>${rows.map((r) => `<li>${r}</li>`).join('')}</ul></details>` : '';
  const code = (s) => `<code>${esc(s)}</code>`;
  const pn = (n) => `<span class="muted">part ${n}</span>`;
  const warnings = [
    ...R.skipped.map((r) => `${pn(r.part)} ${code(r.what)} — ${esc(r.why)}`),
    ...R.notes.map((n) => esc(n)),
  ];
  const body = h(`<div class="cmb-report">
    <div class="cmb-ok">${icon('check')}<div><b>${esc(project.name)}</b> was created from ${R.parts.length} projects.
      <div class="muted">Compiler ${esc(ENGINE[R.engine] || R.engine)} · ${R.stats.copied} files copied, ${R.stats.shared} identical files stored once${R.bibSystem ? ` · ${R.stats.references} references in ${esc(R.bibPath)}` : ''}</div></div></div>
    <ol class="cmb-order">${R.parts.map((p) => `<li><b>${esc(p.name)}</b> <span class="muted">→ parts/${String(p.num).padStart(2, '0')}-…tex</span></li>`).join('')}</ol>
    ${sec('Please check', warnings, 'warn')}
    ${sec('Files renamed because the name was taken by different content', R.renamedFiles.map((r) => `${pn(r.part)} ${code(r.from)} → ${code(r.to)}`))}
    ${sec('Citation keys renamed (same key, different source)', R.renamedKeys.map((r) => `${pn(r.part)} ${code(r.from)} → ${code(r.to)}`))}
    ${sec('Labels renamed (already used by an earlier part)', R.renamedLabels.map((r) => `${pn(r.part)} ${code(r.from)} → ${code(r.to)}`))}
    ${sec('File references updated', R.rewrittenRefs.map((r) => `${pn(r.part)} ${code(r.from)} → ${code(r.to)}`))}
    ${sec('Packages added to the preamble', R.addedPackages.map((r) => `${code(r.pkg)} ${pn(r.part)}`))}
    ${sec('Commands moved or removed from the parts', R.removed.map((r) => `${pn(r.part)} ${code(r.cmd)}`))}
    ${R.stats.duplicateReferences ? `<p class="muted">${plural(R.stats.duplicateReferences, 'duplicate reference')} merged.</p>` : ''}
    <p class="hint">Everything above is also saved in <b>merge-report.txt</b> inside the new project. To change the order later, move the <code>\\input</code> lines in <b>main.tex</b>.</p>
  </div>`);
  const open = await modal({
    title: 'Projects combined',
    body,
    wide: true,
    buttons: [
      { label: 'Close', value: null },
      { label: 'Open project', value: 'open', cls: 'primary' },
    ],
  });
  if (open) location.href = `/project/${project.id}`;
  return project;
}
