import { api, esc, h, icon, modal, prompt, confirmBox, toast, contextMenu, relTime, applyTheme, isDark } from './ui.js';
import { openCombine } from './combine.js';

const $ = (s) => document.querySelector(s);
let projects = [];
let templates = [];

$('#new-btn').innerHTML = `${icon('plus')}New report`;
$('#upload-btn').innerHTML = `${icon('upload')}Upload .zip`;
$('#combine-btn').innerHTML = `${icon('merge')}Combine projects`;
$('#combine-btn').onclick = async () => {
  const p = await openCombine({ projects });
  if (p) await load();
};
// While the Combine window is open, dropped files belong to it, not to the page-wide import.
const combineOpen = () => !!document.querySelector('.cmb-backdrop');

function themeIcon() {
  $('#theme-btn').innerHTML = icon(isDark() ? 'sun' : 'moon');
}
$('#theme-btn').onclick = () => {
  applyTheme(isDark() ? 'light' : 'dark');
  themeIcon();
};
themeIcon();

async function loadStatus() {
  try {
    const s = await api('GET', '/api/status');
    const el = $('#tex-status');
    if (s.tex.found) {
      el.className = 'pill ok';
      el.innerHTML = `<span class="dot"></span>${esc(s.tex.distribution)} ready`;
      el.title = s.tex.binDir;
    } else {
      el.className = 'pill err';
      el.innerHTML = '<span class="dot"></span>No TeX found';
      const b = $('#tex-banner');
      b.classList.remove('hidden');
      b.innerHTML = `<b>No LaTeX distribution was found.</b> Run <code>setup.ps1</code> in the Folio folder (it installs a portable MiKTeX), then restart Folio.`;
    }
  } catch (e) {
    toast('Cannot reach the Folio server: ' + e.message, 'error');
  }
}

// ---------------------------------------------------------------- analysis modules
// UI-17: the card shows the module's own header icon (module.json "icon_svg", inner markup of a 24×24 stroke icon).
// Only plain shapes and geometry attributes are kept; anything else falls back to the generic icon named in "icon".
const SVG_TAGS = new Set(['path', 'circle', 'rect', 'line', 'polyline', 'polygon', 'ellipse', 'g']);
const SVG_ATTRS = new Set(['d', 'cx', 'cy', 'r', 'rx', 'ry', 'x', 'y', 'x1', 'y1', 'x2', 'y2', 'width', 'height', 'points', 'transform', 'fill', 'opacity', 'stroke-width']);
function modIcon(m) {
  const src = typeof m.icon_svg === 'string' ? m.icon_svg.trim() : '';
  if (src && src.length < 4000) {
    try {
      const doc = new DOMParser().parseFromString(`<svg xmlns="http://www.w3.org/2000/svg">${src}</svg>`, 'image/svg+xml');
      const root = doc.documentElement;
      const ok = (el) => SVG_TAGS.has(el.localName) && [...el.attributes].every((a) => SVG_ATTRS.has(a.name) && !/url\(|script:|[<>]/i.test(a.value)) && [...el.children].every(ok);
      if (root.localName === 'svg' && !doc.getElementsByTagName('parsererror').length && root.children.length && [...root.children].every(ok)) {
        const build = (el) => `<${el.localName}${[...el.attributes].map((a) => ` ${a.name}="${esc(a.value)}"`).join('')}>${[...el.children].map(build).join('')}</${el.localName}>`;
        return `<svg class="i" viewBox="0 0 24 24" aria-hidden="true">${[...root.children].map(build).join('')}</svg>`;
      }
    } catch { /* fall back */ }
  }
  return icon(m.icon || 'chart');
}
async function loadModules() {
  const host = $('#modules');
  let mods = [];
  try {
    mods = await api('GET', '/api/modules');
  } catch (e) {
    host.innerHTML = `<div class="empty">Could not list analysis modules: ${esc(e.message)}</div>`;
    return;
  }
  host.innerHTML = '';
  for (const m of mods) {
    const planned = m.status !== 'ready';
    const state = planned ? 'planned' : m.state;
    const badge = { planned: 'Planned', running: 'Running', starting: 'Starting', error: 'Error', stopped: '' }[state] || '';
    const name = m.name_en && m.name_en !== m.name ? `${m.name_en} <span class="muted" style="font-weight:400">· ${esc(m.name)}</span>` : esc(m.name);
    const card = h(`<${planned ? 'div' : 'a'} class="mod-card ${planned ? 'planned' : ''}" ${planned ? '' : `href="${esc(m.url)}"`} style="--mod:${esc(m.color || '')}">
      <div class="mod-icon">${modIcon(m)}</div>
      <div class="mod-head"><b>${name}</b>${badge ? `<span class="mod-badge ${esc(state)}">${badge}</span>` : ''}</div>
      <div class="mod-desc">${esc(m.description_en || m.description || '')}</div>
      <div class="mod-meta">${(m.accepts || []).map(esc).join(' ')}${m.error ? ` · <span style="color:var(--err)">${esc(m.error)}</span>` : ''}</div>
      ${planned ? '' : `<div class="mod-env" data-env="${esc(m.id)}" hidden></div>`}
    </${planned ? 'div' : 'a'}>`);
    if (planned) card.title = 'This module is planned. See docs/MODULES.md to build it.';
    host.appendChild(card);
  }
  host.appendChild(h(`<div class="mod-card add" title="Add a folder with a module.json under modules/">More analyses (e.g. FTIR) plug in as modules.<br>See docs/MODULES.md</div>`));
  loadEnvs();
}

// UI-09: which environment each module opens in the active project; switching happens on the module's overview
async function loadEnvs() {
  let s;
  try {
    s = await api('GET', '/api/suite/envs');
  } catch {
    return;
  }
  document.querySelectorAll('[data-env]').forEach((el) => {
    const e = s.modules[el.dataset.env];
    el.hidden = !(e && e.active);
    if (!e || !e.active) return;
    el.innerHTML = `${icon('layers')}<span class="me-n">${esc(e.active.name)}${e.count > 1 ? ` <span class="muted">+${e.count - 1}</span>` : ''}</span>${e.active.title ? `<span class="me-t muted">· ${esc(e.active.title)}</span>` : ''}`;
    el.title = `${e.active.name}${e.active.title ? ' · ' + e.active.title : ''}\nOpen environment in this project${e.count > 1 ? ` (${e.count} environments; switch on the module's overview)` : ''}`;
  });
}
window.addEventListener('suite-changed', loadEnvs);

async function load() {
  projects = await api('GET', '/api/projects');
  render();
}

function render() {
  const q = $('#search').value.trim().toLowerCase();
  const list = projects.filter((p) => !q || p.name.toLowerCase().includes(q));
  const host = $('#list');
  if (!projects.length) {
    host.innerHTML = `<div class="empty"><h3>No reports yet</h3><p>Create a report from a template (try <b>Lab report</b>), upload a .zip, or send results from an analysis above.</p>
      <button class="btn primary" id="empty-new">${icon('plus')}New report</button></div>`;
    $('#empty-new').onclick = newProject;
    return;
  }
  if (!list.length) {
    host.innerHTML = `<div class="empty">No projects match “${esc(q)}”.</div>`;
    return;
  }
  host.innerHTML = `<table class="proj-table"><thead><tr><th>Name</th><th style="width:150px">Compiler</th><th style="width:160px">Last modified</th><th style="width:200px"></th></tr></thead><tbody></tbody></table>`;
  const tbody = host.querySelector('tbody');
  for (const p of list) {
    const tr = h(`<tr>
      <td><div class="proj-name">${icon('file-text')}<span>${esc(p.name)}</span></div></td>
      <td class="muted">${esc({ pdflatex: 'pdfLaTeX', xelatex: 'XeLaTeX', lualatex: 'LuaLaTeX' }[p.engine] || p.engine)}</td>
      <td class="muted" title="${esc(new Date(p.modified).toLocaleString())}">${esc(relTime(p.modified))}</td>
      <td><div class="proj-actions">
        <button class="btn ghost icon sm" data-a="pdf" title="Download PDF" ${p.hasPdf ? '' : 'disabled'}>${icon('pdf')}</button>
        <button class="btn ghost icon sm" data-a="zip" title="Download source (.zip)">${icon('download')}</button>
        <button class="btn ghost icon sm" data-a="copy" title="Duplicate">${icon('copy')}</button>
        <button class="btn ghost icon sm" data-a="rename" title="Rename">${icon('edit')}</button>
        <button class="btn ghost icon sm danger" data-a="delete" title="Delete">${icon('trash')}</button>
      </div></td></tr>`);
    tr.onclick = (e) => {
      const a = e.target.closest('[data-a]');
      if (a) {
        e.stopPropagation();
        action(a.dataset.a, p);
      } else location.href = `/project/${p.id}`;
    };
    tr.oncontextmenu = (e) => {
      e.preventDefault();
      contextMenu(e.clientX, e.clientY, [
        { label: 'Open', icon: 'eye', action: () => (location.href = `/project/${p.id}`) },
        { label: 'Rename', icon: 'edit', action: () => action('rename', p) },
        { label: 'Duplicate', icon: 'copy', action: () => action('copy', p) },
        { label: 'Download source (.zip)', icon: 'download', action: () => action('zip', p) },
        { label: 'Download portable LaTeX (.zip)', icon: 'download', action: () => action('portable', p) },
        p.hasPdf ? { label: 'Download PDF', icon: 'pdf', action: () => action('pdf', p) } : null,
        '-',
        { label: 'Delete', icon: 'trash', danger: true, action: () => action('delete', p) },
      ]);
    };
    tbody.appendChild(tr);
  }
}

async function action(a, p) {
  try {
    if (a === 'pdf') location.href = `/api/projects/${p.id}/output.pdf?download=1`;
    else if (a === 'zip') location.href = `/api/projects/${p.id}/zip`;
    else if (a === 'portable') location.href = `/api/projects/${p.id}/zip?portable=1`;
    else if (a === 'copy') {
      await api('POST', `/api/projects/${p.id}/duplicate`);
      toast('Project duplicated');
      await load();
    } else if (a === 'rename') {
      const name = await prompt('Rename project', 'Project name', p.name, { okLabel: 'Rename' });
      if (name) {
        await api('PATCH', `/api/projects/${p.id}`, { name });
        await load();
      }
    } else if (a === 'delete') {
      const ok = await confirmBox('Delete project', `Delete <b>${esc(p.name)}</b> and all its files? This cannot be undone.`, { okLabel: 'Delete', danger: true });
      if (ok) {
        await api('DELETE', `/api/projects/${p.id}`);
        toast('Project deleted');
        await load();
      }
    }
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function newProject() {
  if (!templates.length) templates = await api('GET', '/api/templates');
  let selected = templates[0]?.id || 'blank';
  const body = h(`<div>
    <label class="field"><span>Project name</span><input class="input" id="np-name" placeholder="My document"></label>
    <div style="font-size:12.5px;font-weight:600;color:var(--text-muted);margin:4px 0 8px">Template</div>
    <div class="tpl-grid"></div></div>`);
  const grid = body.querySelector('.tpl-grid');
  for (const t of templates) {
    const c = h(`<button class="tpl-card ${t.id === selected ? 'selected' : ''}" data-id="${esc(t.id)}">
      <div class="tpl-icon">${icon(t.icon || 'file')}</div><b>${esc(t.name)}</b><span>${esc(t.description || '')}</span></button>`);
    c.onclick = () => {
      selected = t.id;
      grid.querySelectorAll('.tpl-card').forEach((x) => x.classList.toggle('selected', x === c));
    };
    c.ondblclick = () => body.closest('.modal').querySelector('.btn.primary').click();
    grid.appendChild(c);
  }
  const res = await modal({
    title: 'New project',
    body,
    wide: true,
    buttons: [
      { label: 'Cancel', value: null },
      { label: 'Create project', value: 'ok', cls: 'primary' },
    ],
  });
  if (!res) return;
  try {
    const name = body.querySelector('#np-name').value.trim();
    const p = await api('POST', '/api/projects', { name, template: selected });
    location.href = `/project/${p.id}`;
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function importZip(file) {
  if (!/\.zip$/i.test(file.name)) return toast('Please choose a .zip file', 'error');
  toast(`Importing ${file.name}…`);
  try {
    const p = await fetch(`/api/projects/import?name=${encodeURIComponent(file.name)}`, {
      method: 'POST',
      headers: { 'X-Folio': '1' },
      body: file,
    }).then(async (r) => {
      const d = await r.json();
      if (!r.ok) throw new Error(d.error);
      return d;
    });
    location.href = `/project/${p.id}`;
  } catch (e) {
    toast('Import failed: ' + e.message, 'error');
  }
}

$('#new-btn').onclick = newProject;
$('#upload-btn').onclick = () => $('#zip-input').click();
$('#zip-input').onchange = (e) => e.target.files[0] && importZip(e.target.files[0]);
$('#search').oninput = render;

let dragDepth = 0;
let overlay = null;
window.addEventListener('dragenter', (e) => {
  if (!e.dataTransfer.types.includes('Files') || combineOpen()) return;
  dragDepth++;
  if (!overlay) {
    overlay = h('<div class="drop-overlay">Drop a .zip to import it as a project</div>');
    document.body.appendChild(overlay);
  }
});
window.addEventListener('dragleave', () => {
  if (--dragDepth <= 0 && overlay) {
    overlay.remove();
    overlay = null;
    dragDepth = 0;
  }
});
window.addEventListener('dragover', (e) => e.preventDefault());
window.addEventListener('drop', (e) => {
  e.preventDefault();
  dragDepth = 0;
  overlay?.remove();
  overlay = null;
  if (combineOpen()) return;
  const f = e.dataTransfer.files[0];
  if (f) importZip(f);
});

loadStatus();
loadModules();
load().catch((e) => toast(e.message, 'error'));
