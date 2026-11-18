// Folio editor: wires together file tree, Monaco, PDF preview, compile pipeline and dialogs.
import { api, fileUrl, esc, h, icon, modal, prompt, confirmBox, toast, contextMenu, applyTheme, isDark, store, fmtSize } from '../ui.js';
import { registerLatex, languageFor, outline } from './latex-lang.js';
import { PdfViewer } from './pdfviewer.js';
import { FileTree, IMAGE_RE, BINARY_RE } from './filetree.js';
import { initLab, openLab } from './lab.js';
import { initImport, openImport } from './import.js';

const $ = (s) => document.querySelector(s);
const projectId = location.pathname.split('/')[2];
const ENGINE_NAMES = { pdflatex: 'pdfLaTeX', xelatex: 'XeLaTeX', lualatex: 'LuaLaTeX' };
const LATEX_IMG_RE = /\.(png|jpe?g|pdf|eps)$/i;

let monaco;
let editor;
let project;
let files = [];
let symbols = { labels: [], cites: [], commands: [], files: [] };
const models = new Map(); // path -> { model, savedVersion, saving, timer, viewState }
let tabs = [];
let activePath = null;
let lastTexPath = null;
let lastResult = null;
let compiling = false;
let pendingCompile = false;
let logsOpen = false;
let logsTab = 'errors';
let texStatus = null;

const settings = {
  autoCompile: store('autoCompile') ?? false,
  fontSize: store('fontSize') ?? 14,
  wordWrap: store('wordWrap') ?? true,
  layout: store('layout') || 'split',
  sidebar: store('sidebar') ?? true,
};

// ---------------------------------------------------------------- static UI
document.querySelectorAll('[data-icon]').forEach((el) => {
  el.insertAdjacentHTML('afterbegin', icon(el.dataset.icon));
});
const labelled = { figure: 'Figure', table: 'Table', plot: 'Plot', cite: 'Cite', lab: 'Lab' };
document.querySelectorAll('[data-fmt]').forEach((b) => {
  if (labelled[b.dataset.fmt]) b.insertAdjacentHTML('beforeend', `<span>${labelled[b.dataset.fmt]}</span>`);
});
$('#btn-sync-fwd').insertAdjacentHTML('beforeend', '<span>PDF</span>');

function themeIcon() {
  $('#btn-theme').innerHTML = icon(isDark() ? 'sun' : 'moon');
  if (monaco) monaco.editor.setTheme(isDark() ? 'folio-dark' : 'folio-light');
}
$('#btn-theme').onclick = () => {
  applyTheme(isDark() ? 'light' : 'dark');
  themeIcon();
};
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', themeIcon);
themeIcon();

// ---------------------------------------------------------------- layout
const mainEl = $('#main');
function applyLayout() {
  mainEl.classList.toggle('layout-editor', settings.layout === 'editor');
  mainEl.classList.toggle('layout-pdf', settings.layout === 'pdf');
  mainEl.classList.toggle('no-sidebar', !settings.sidebar);
  document.querySelectorAll('[data-layout]').forEach((b) => b.classList.toggle('active', b.dataset.layout === settings.layout));
  $('#btn-sidebar').classList.toggle('active', settings.sidebar);
  applySizes();
}
// Pane sizes are kept as fractions of the window (sidebar, PDF) or of the sidebar (outline), so a layout keeps its
// proportions on another screen. Older pixel values (sidebarW, pdfW) are converted once.
const W = () => window.innerWidth;
function paneFrac(key, legacy) {
  let f = store(key);
  if (typeof f !== 'number') {
    const px = store(legacy);
    if (typeof px === 'number' && px > 0) { f = px / W(); store(key, f); }
  }
  return typeof f === 'number' && f > 0 ? f : null;
}
function applySizes() {
  const sf = paneFrac('sidebarF', 'sidebarW');
  const pf = paneFrac('pdfF', 'pdfW');
  const of = store('outlineF');
  const set = (v, val) => (val === null ? mainEl.style.removeProperty(v) : mainEl.style.setProperty(v, val));
  set('--sidebar-w', sf ? Math.round(Math.max(150, Math.min(0.5 * W(), sf * W()))) + 'px' : null);
  set('--pdf-w', pf ? Math.round(Math.max(220, Math.min(W() - 300, pf * W()))) + 'px' : null);
  set('--outline-h', typeof of === 'number' && of > 0 ? Math.round(100 * Math.max(0.1, Math.min(0.9, of))) + '%' : null);
}
window.addEventListener('resize', applySizes);
document.querySelectorAll('[data-layout]').forEach((b) => {
  b.onclick = () => {
    settings.layout = b.dataset.layout;
    store('layout', settings.layout);
    applyLayout();
  };
});
$('#btn-sidebar').onclick = () => {
  settings.sidebar = !settings.sidebar;
  store('sidebar', settings.sidebar);
  applyLayout();
};
function bindGutter(gutter, onMove, onReset) {
  gutter.title = 'Drag to resize; double-click resets';
  if (onReset) gutter.addEventListener('dblclick', () => { onReset(); applySizes(); });
  gutter.addEventListener('pointerdown', (e) => {
    e.preventDefault();
    gutter.setPointerCapture(e.pointerId);
    gutter.classList.add('dragging');
    document.body.classList.add('resizing');
    document.body.classList.toggle('rows', gutter.classList.contains('hgutter'));
    const move = (ev) => onMove(ev.clientX, ev.clientY);
    const up = () => {
      gutter.classList.remove('dragging');
      document.body.classList.remove('resizing', 'rows');
      gutter.removeEventListener('pointermove', move);
      gutter.removeEventListener('pointerup', up);
    };
    gutter.addEventListener('pointermove', move);
    gutter.addEventListener('pointerup', up);
  });
}
bindGutter($('#gutter-side'), (x) => {
  const w = Math.max(150, Math.min(0.5 * W(), x));
  mainEl.style.setProperty('--sidebar-w', w + 'px');
  store('sidebarF', w / W());
}, () => { store('sidebarF', null); store('sidebarW', null); });
bindGutter($('#gutter-pdf'), (x) => {
  const w = Math.max(220, Math.min(W() - 300, W() - x));
  mainEl.style.setProperty('--pdf-w', w + 'px');
  store('pdfF', w / W());
}, () => { store('pdfF', null); store('pdfW', null); });
// Files / Outline split in the sidebar
bindGutter($('#gutter-outline'), (x, y) => {
  const sb = $('.sidebar').getBoundingClientRect();
  const f = Math.max(0.1, Math.min(0.9, (sb.bottom - y) / sb.height));
  mainEl.style.setProperty('--outline-h', Math.round(100 * f) + '%');
  store('outlineF', f);
}, () => store('outlineF', null));
applyLayout();

$('#outline-toggle').onclick = () => {
  const s = $('#outline-section');
  s.classList.toggle('collapsed');
  store('outlineCollapsed', s.classList.contains('collapsed'));
};
if (store('outlineCollapsed')) $('#outline-section').classList.add('collapsed');

// ---------------------------------------------------------------- PDF viewer
const pdf = new PdfViewer($('#pdf-scroll'), {
  onDoubleClick: syncInverse,
  onChange: updatePdfToolbar,
});
function updatePdfToolbar() {
  const n = pdf.numPages;
  $('#page-label').textContent = n ? `Page ${pdf.currentPage()} of ${n}` : '';
  $('#zoom-label').textContent = n ? Math.round(pdf.currentZoom() * 100) + '%' : '';
  $('#zoom-fit').classList.toggle('active', pdf.mode === 'page-width');
}
$('#zoom-in').onclick = () => pdf.zoomIn();
$('#zoom-out').onclick = () => pdf.zoomOut();
$('#zoom-fit').onclick = () => pdf.setMode('page-width');
$('#zoom-label').onclick = (e) => {
  const r = e.target.getBoundingClientRect();
  contextMenu(r.left, r.bottom + 4, [
    { label: 'Fit width', icon: 'fit-width', action: () => pdf.setMode('page-width') },
    { label: 'Fit page', icon: 'eye', action: () => pdf.setMode('page-fit') },
    '-',
    ...[0.5, 0.75, 1, 1.25, 1.5, 2, 3].map((z) => ({ label: `${z * 100}%`, action: () => pdf.setZoom(z) })),
  ]);
};
$('#pdf-open').href = `/api/projects/${projectId}/output.pdf`;

// ---------------------------------------------------------------- monaco
function loadMonaco() {
  return new Promise((resolve, reject) => {
    window.MonacoEnvironment = { getWorkerUrl: () => '/vendor/monaco/vs/base/worker/workerMain.js' };
    window.require.config({ paths: { vs: '/vendor/monaco/vs' } });
    window.require(['vs/editor/editor.main'], () => resolve(window.monaco), reject);
  });
}

function createEditor() {
  registerLatex(monaco, () => symbols);
  editor = monaco.editor.create($('#monaco'), {
    model: null,
    theme: isDark() ? 'folio-dark' : 'folio-light',
    automaticLayout: true,
    fontSize: settings.fontSize,
    fontFamily: '"Cascadia Code", "Cascadia Mono", Consolas, "JetBrains Mono", monospace',
    fontLigatures: false,
    wordWrap: settings.wordWrap ? 'on' : 'off',
    minimap: { enabled: false },
    scrollBeyondLastLine: false,
    tabSize: 2,
    insertSpaces: true,
    quickSuggestions: false,
    wordBasedSuggestions: 'off',
    suggestOnTriggerCharacters: true,
    snippetSuggestions: 'inline',
    suggest: { showWords: false, preview: true },
    unicodeHighlight: { ambiguousCharacters: false, invisibleCharacters: false },
    renderLineHighlight: 'line',
    padding: { top: 8 },
    smoothScrolling: true,
    bracketPairColorization: { enabled: false },
    stickyScroll: { enabled: true },
    glyphMargin: false,
    folding: true,
    lineNumbersMinChars: 3,
  });
  const K = monaco.KeyMod;
  const C = monaco.KeyCode;
  editor.addCommand(K.CtrlCmd | C.KeyS, () => compile());
  editor.addCommand(K.CtrlCmd | C.Enter, () => compile());
  editor.addCommand(K.CtrlCmd | C.KeyB, () => wrap('\\textbf{', '}'));
  editor.addCommand(K.CtrlCmd | C.KeyI, () => wrap('\\textit{', '}'));
  editor.addAction({
    id: 'folio.syncForward',
    label: 'Show this line in the PDF',
    keybindings: [K.CtrlCmd | K.Alt | C.RightArrow],
    contextMenuGroupId: 'navigation',
    run: () => syncForward(),
  });
  editor.addAction({
    id: 'folio.compile',
    label: 'Compile document',
    contextMenuGroupId: 'navigation',
    run: () => compile(),
  });

  // Paste or drop images directly into the editor.
  const host = $('#monaco');
  host.addEventListener(
    'paste',
    async (e) => {
      const imgs = [...(e.clipboardData?.files || [])].filter((f) => f.type.startsWith('image/'));
      if (!imgs.length) return;
      e.preventDefault();
      e.stopPropagation();
      const f = imgs[0];
      const ext = (f.type.split('/')[1] || 'png').replace('jpeg', 'jpg');
      const stamp = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 14);
      const path = `images/pasted-${stamp}.${ext}`;
      await putFile(path, f);
      await refreshFiles();
      insertFigure(path, '');
      toast(`Saved pasted image as ${path}`);
    },
    true
  );
  host.addEventListener(
    'dragover',
    (e) => {
      if (e.dataTransfer.types.includes('Files')) e.preventDefault();
    },
    true
  );
  host.addEventListener(
    'drop',
    async (e) => {
      if (!e.dataTransfer.files.length) return;
      e.preventDefault();
      e.stopPropagation();
      const list = [...e.dataTransfer.files];
      const target = editor.getTargetAtClientPoint(e.clientX, e.clientY);
      if (target?.position) editor.setPosition(target.position);
      const uploaded = await uploadFiles(
        list.map((f) => ({ file: f, rel: f.name })),
        (f) => (IMAGE_RE.test(f.name) || /\.(pdf|eps)$/i.test(f.name) ? 'images' : '')
      );
      for (const p of uploaded) if (LATEX_IMG_RE.test(p)) insertFigure(p, '');
    },
    true
  );
}

// ---------------------------------------------------------------- project & files
async function loadProject() {
  project = await api('GET', `/api/projects/${projectId}`);
  files = project.files;
  document.title = `${project.name} — Folio Lab`;
  $('#proj-title').textContent = project.name;
  renderCompileButton();
}

async function refreshFiles() {
  files = await api('GET', `/api/projects/${projectId}/files`);
  tree.setFiles(files, project.mainFile);
  scheduleSymbols(0);
}

let symTimer;
function scheduleSymbols(delay = 1200) {
  clearTimeout(symTimer);
  symTimer = setTimeout(async () => {
    try {
      symbols = await api('GET', `/api/projects/${projectId}/symbols`);
    } catch {
      /* ignore */
    }
  }, delay);
}

const tree = new FileTree($('#tree'), projectId, {
  onOpen: (p) => openFile(p),
  onContext: treeContext,
  onMove: (from, to) => renameFile(from, to),
  onUpload: (list, folder) => uploadFiles(list, () => folder),
});

function treeContext(path, type, x, y) {
  const isDir = type === 'dir';
  const folder = !path ? '' : isDir ? path : path.includes('/') ? path.slice(0, path.lastIndexOf('/')) : '';
  const items = [
    { label: 'New file', icon: 'file-plus', action: () => newFile(folder) },
    { label: 'New folder', icon: 'folder-plus', action: () => newFolder(folder) },
    { label: 'Upload files…', icon: 'upload', action: () => pickUpload(folder) },
  ];
  if (path) {
    items.push('-');
    if (!isDir && /\.tex$/i.test(path) && path !== project.mainFile)
      items.push({ label: 'Set as main document', icon: 'star', action: () => setMainFile(path) });
    if (!isDir && LATEX_IMG_RE.test(path)) items.push({ label: 'Insert as figure', icon: 'image', action: () => insertFigure(path, '') });
    items.push({ label: 'Rename / move…', icon: 'edit', action: () => renamePrompt(path) });
    if (!isDir) items.push({ label: 'Download', icon: 'download', action: () => (location.href = fileUrl(projectId, path, true)) });
    items.push('-', { label: 'Delete', icon: 'trash', danger: true, action: () => deleteFile(path, isDir) });
  }
  contextMenu(x, y, items);
}

async function putFile(path, body) {
  await api('PUT', `/api/projects/${projectId}/file?path=${encodeURIComponent(path)}`, body);
}

async function newFile(folder = tree.currentFolder()) {
  const name = await prompt('New file', 'File name (e.g. chapter1.tex, references.bib, data.csv)', '', { okLabel: 'Create' });
  if (!name) return;
  const path = (folder ? folder + '/' : '') + name.replace(/^\/+/, '');
  if (files.some((f) => f.path === path)) return toast(`"${path}" already exists`, 'error');
  try {
    let content = '';
    if (/\.tex$/i.test(path)) content = `\\section{${name.replace(/\.tex$/i, '').replace(/[_-]/g, ' ')}}\n\n`;
    await putFile(path, content);
    await refreshFiles();
    openFile(path);
    if (/\.tex$/i.test(path) && path !== project.mainFile)
      toast(`Add \\input{${path.replace(/\.tex$/i, '')}} to ${project.mainFile} to include it`, 'info', 5000);
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function newFolder(folder = tree.currentFolder()) {
  const name = await prompt('New folder', 'Folder name', '', { okLabel: 'Create' });
  if (!name) return;
  try {
    const path = (folder ? folder + '/' : '') + name;
    await api('POST', `/api/projects/${projectId}/folder`, { path });
    tree.expanded.add(path);
    await refreshFiles();
  } catch (e) {
    toast(e.message, 'error');
  }
}

let uploadFolder = '';
function pickUpload(folder = tree.currentFolder()) {
  uploadFolder = folder;
  $('#upload-input').value = '';
  $('#upload-input').click();
}
$('#upload-input').onchange = (e) => {
  const list = [...e.target.files].map((f) => ({ file: f, rel: f.name }));
  if (list.length) uploadFiles(list, () => uploadFolder);
};

/** list: [{file, rel}], folderFor(file) -> target folder. Returns uploaded paths. */
async function uploadFiles(list, folderFor) {
  const done = [];
  let overwriteAll = false;
  for (const { file, rel } of list) {
    const folder = folderFor(file) || '';
    const path = (folder ? folder + '/' : '') + rel;
    if (!overwriteAll && files.some((f) => f.path === path)) {
      const ok = await confirmBox('File exists', `<b>${esc(path)}</b> already exists. Replace it?`, { okLabel: 'Replace' });
      if (!ok) continue;
      overwriteAll = list.length > 1;
    }
    try {
      await putFile(path, file);
      done.push(path);
      const m = models.get(path);
      if (m) {
        const text = await file.text();
        m.model.setValue(text);
        m.savedVersion = m.model.getVersionId();
      }
    } catch (e) {
      toast(`Upload of ${rel} failed: ${e.message}`, 'error');
    }
  }
  if (done.length) {
    await refreshFiles();
    toast(done.length === 1 ? `Uploaded ${done[0]}` : `Uploaded ${done.length} files`);
    if (activePath && done.includes(activePath) && !models.has(activePath)) showPreview(activePath);
  }
  return done;
}

async function renamePrompt(path) {
  const to = await prompt('Rename or move', 'New path (use / for folders)', path, { okLabel: 'Rename', selectBase: true });
  if (to && to !== path) renameFile(path, to);
}

async function renameFile(from, to) {
  try {
    await saveAll();
    const res = await api('POST', `/api/projects/${projectId}/rename`, { from, to });
    const newPath = res.path;
    // Re-key open models and tabs under the new path(s).
    for (const [p, entry] of [...models]) {
      if (p === from || p.startsWith(from + '/')) {
        const np = newPath + p.slice(from.length);
        const text = entry.model.getValue();
        const wasActive = activePath === p;
        entry.model.dispose();
        models.delete(p);
        createModel(np, text);
        if (wasActive) activePath = np;
      }
    }
    tabs = tabs.map((t) => (t === from || t.startsWith(from + '/') ? newPath + t.slice(from.length) : t));
    if (activePath === from) activePath = newPath;
    project = { ...project, ...(await api('GET', `/api/projects/${projectId}`)) };
    await refreshFiles();
    if (activePath) openFile(activePath);
    renderTabs();
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function deleteFile(path, isDir) {
  const ok = await confirmBox('Delete', `Delete <b>${esc(path)}</b>${isDir ? ' and everything in it' : ''}?`, { okLabel: 'Delete', danger: true });
  if (!ok) return;
  try {
    await api('DELETE', `/api/projects/${projectId}/file?path=${encodeURIComponent(path)}`);
    for (const p of [...tabs]) if (p === path || p.startsWith(path + '/')) closeTab(p, true);
    for (const [p, e] of [...models]) {
      if (p === path || p.startsWith(path + '/')) {
        clearTimeout(e.timer);
        e.model.dispose();
        models.delete(p);
      }
    }
    await refreshFiles();
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function setMainFile(path) {
  try {
    project = { ...project, ...(await api('PATCH', `/api/projects/${projectId}`, { mainFile: path })) };
    tree.setFiles(files, project.mainFile);
    toast(`${path} is now the main document`);
  } catch (e) {
    toast(e.message, 'error');
  }
}

$('#btn-new-file').onclick = () => newFile();
$('#btn-new-folder').onclick = () => newFolder();
$('#btn-upload').onclick = () => pickUpload();

$('#proj-title').onclick = async () => {
  const name = await prompt('Rename project', 'Project name', project.name, { okLabel: 'Rename' });
  if (!name) return;
  project = { ...project, ...(await api('PATCH', `/api/projects/${projectId}`, { name })) };
  $('#proj-title').textContent = project.name;
  document.title = `${project.name} — Folio Lab`;
};

// ---------------------------------------------------------------- models, tabs, saving
function isText(path) {
  return !BINARY_RE.test(path) && !/\.svg$/i.test(path);
}

function createModel(path, text) {
  const uri = monaco.Uri.from({ scheme: 'file', path: '/' + path });
  const existing = monaco.editor.getModel(uri);
  if (existing) existing.dispose();
  const model = monaco.editor.createModel(text, languageFor(path), uri);
  const entry = { model, savedVersion: model.getVersionId(), saving: null, timer: null, viewState: null };
  models.set(path, entry);
  model.onDidChangeContent(() => {
    scheduleSave(path);
    if (path === activePath) scheduleOutline();
  });
  applyMarkersTo(path);
  return entry;
}

async function getModel(path) {
  if (models.has(path)) return models.get(path);
  const r = await api('GET', fileUrl(projectId, path), undefined, { raw: true });
  return createModel(path, await r.text());
}

async function openFile(path, { line } = {}) {
  const f = files.find((x) => x.path === path);
  if (!f) return toast(`File not found: ${path}`, 'error');
  if (activePath && models.has(activePath)) models.get(activePath).viewState = editor.saveViewState();
  if (!tabs.includes(path)) tabs.push(path);
  activePath = path;
  store(`last.${projectId}`, path);
  renderTabs();
  tree.select(path);
  if (!isText(path) || f.size > 8 * 1024 * 1024) {
    showPreview(path);
    renderOutline();
    return;
  }
  $('#preview').classList.add('hidden');
  $('#monaco').classList.remove('hidden');
  $('#fmt-toolbar').classList.remove('hidden');
  try {
    const entry = await getModel(path);
    if (activePath !== path) return;
    editor.setModel(entry.model);
    if (entry.model.getLanguageId() === 'latex') lastTexPath = path;
    if (entry.viewState) editor.restoreViewState(entry.viewState);
    if (line) revealLine(line);
    editor.focus();
  } catch (e) {
    toast(`Could not open ${path}: ${e.message}`, 'error');
  }
  renderOutline();
}

function revealLine(line) {
  const model = editor.getModel();
  if (!model) return;
  line = Math.min(Math.max(1, line), model.getLineCount());
  editor.revealLineInCenter(line);
  editor.setPosition({ lineNumber: line, column: 1 });
  const deco = editor.createDecorationsCollection([
    { range: new monaco.Range(line, 1, line, 1), options: { isWholeLine: true, className: 'line-flash' } },
  ]);
  setTimeout(() => deco.clear(), 1600);
}

function showPreview(path) {
  $('#monaco').classList.add('hidden');
  $('#fmt-toolbar').classList.add('hidden');
  const host = $('#preview');
  host.classList.remove('hidden');
  const f = files.find((x) => x.path === path) || { size: 0 };
  const url = fileUrl(projectId, path) + '&t=' + (f.mtime || Date.now());
  if (IMAGE_RE.test(path)) {
    host.innerHTML = `<div><div class="img-wrap"><img alt="${esc(path)}" src="${url}"></div>
      <div class="meta"><span id="img-dims">${esc(path)} · ${fmtSize(f.size)}</span>
      <div class="row">${LATEX_IMG_RE.test(path) ? `<button class="btn primary" id="pv-insert">${icon('image')}Insert as figure</button>` : '<span class="hint">SVG files need the svg package plus Inkscape; convert to PDF or PNG for LaTeX.</span>'}
      <a class="btn" href="${fileUrl(projectId, path, true)}">${icon('download')}Download</a></div></div></div>`;
    const img = host.querySelector('img');
    img.onload = () => ($('#img-dims').textContent = `${path} · ${img.naturalWidth}×${img.naturalHeight}px · ${fmtSize(f.size)}`);
  } else if (/\.pdf$/i.test(path)) {
    host.innerHTML = `<iframe src="${url}" title="${esc(path)}"></iframe>`;
    host.style.padding = '0';
    return;
  } else {
    host.innerHTML = `<div class="welcome">${icon('file', '')}<p><b>${esc(path)}</b><br>${fmtSize(f.size)} · binary file (not editable here)</p>
      <a class="btn" href="${fileUrl(projectId, path, true)}">${icon('download')}Download</a></div>`;
  }
  host.style.padding = '';
  const ins = host.querySelector('#pv-insert');
  if (ins) ins.onclick = () => figureDialog(path);
}

function renderTabs() {
  const el = $('#tabs');
  el.replaceChildren(
    ...tabs.map((p) => {
      const entry = models.get(p);
      const dirty = entry && entry.model.getVersionId() !== entry.savedVersion;
      const t = h(`<div class="tab ${p === activePath ? 'active' : ''}" title="${esc(p)}">
        <span>${esc(p.split('/').pop())}</span>${dirty ? '<span class="dirty-dot"></span>' : ''}
        <button class="x" title="Close">${icon('x')}</button></div>`);
      t.onclick = (e) => {
        if (e.target.closest('.x')) closeTab(p);
        else openFile(p);
      };
      t.onauxclick = (e) => {
        if (e.button === 1) closeTab(p);
      };
      return t;
    })
  );
  el.querySelector('.active')?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
}

function closeTab(p, silent = false) {
  const i = tabs.indexOf(p);
  if (i < 0) return;
  tabs.splice(i, 1);
  if (activePath === p) {
    activePath = null;
    const next = tabs[i] || tabs[i - 1];
    if (next) openFile(next);
    else {
      editor.setModel(null);
      $('#monaco').classList.add('hidden');
      $('#preview').classList.remove('hidden');
      $('#preview').innerHTML = '<div class="welcome">Select a file from the file tree to start editing.</div>';
      renderOutline();
    }
  }
  renderTabs();
}

function scheduleSave(path) {
  const e = models.get(path);
  if (!e) return;
  clearTimeout(e.timer);
  e.timer = setTimeout(() => save(path), 600);
  updateSaveState();
  renderTabsDebounced();
}
let tabTimer;
function renderTabsDebounced() {
  clearTimeout(tabTimer);
  tabTimer = setTimeout(renderTabs, 150);
}

async function save(path) {
  const e = models.get(path);
  if (!e) return;
  clearTimeout(e.timer);
  e.timer = null;
  while (e.saving) await e.saving;
  const v = e.model.getVersionId();
  if (v === e.savedVersion || e.model.isDisposed()) return;
  e.saving = putFile(path, e.model.getValue())
    .then(() => {
      e.savedVersion = v;
    })
    .catch((err) => toast(`Saving ${path} failed: ${err.message}`, 'error'))
    .finally(() => {
      e.saving = null;
    });
  updateSaveState();
  await e.saving;
  updateSaveState();
  renderTabs();
  if (/\.(tex|bib|sty|cls)$/i.test(path)) scheduleSymbols();
  if (settings.autoCompile) scheduleAutoCompile();
}

async function saveAll() {
  await Promise.all([...models.keys()].map((p) => save(p)));
}

function anyDirty() {
  for (const e of models.values()) if (e.saving || e.model.getVersionId() !== e.savedVersion) return true;
  return false;
}
function updateSaveState() {
  $('#save-state').textContent = anyDirty() ? 'Saving…' : 'All saved';
}
window.addEventListener('beforeunload', (e) => {
  if (anyDirty()) {
    saveAll();
    e.preventDefault();
    e.returnValue = '';
  }
});

let autoTimer;
function scheduleAutoCompile() {
  clearTimeout(autoTimer);
  autoTimer = setTimeout(() => compile(), 1200);
}

// ---------------------------------------------------------------- outline
let outlineTimer;
function scheduleOutline() {
  clearTimeout(outlineTimer);
  outlineTimer = setTimeout(renderOutline, 400);
}
function renderOutline() {
  const el = $('#outline');
  const entry = activePath && models.get(activePath);
  if (!entry || entry.model.getLanguageId() !== 'latex') {
    el.innerHTML = '<div class="outline-empty">Open a .tex file to see its outline.</div>';
    return;
  }
  const items = outline(entry.model.getValue());
  if (!items.length) {
    el.innerHTML = '<div class="outline-empty">No sections in this file.</div>';
    return;
  }
  const min = Math.min(...items.map((i) => i.level));
  el.replaceChildren(
    ...items.map((it) => {
      const lvl = it.level - min;
      const b = h(`<button class="outline-item l${lvl}" style="padding-left:${10 + lvl * 12}px">${esc(it.title)}</button>`);
      b.onclick = () => {
        revealLine(it.line);
        editor.focus();
      };
      return b;
    })
  );
}

// ---------------------------------------------------------------- compile
function renderCompileButton() {
  const b = $('#btn-compile');
  b.innerHTML = compiling ? `${icon('loader', 'spin')}<span>Compiling…</span>` : `${icon('refresh')}<span>Recompile</span>`;
  b.title = compiling ? 'Click to stop' : 'Compile (Ctrl+S / Ctrl+Enter)';
}
$('#btn-compile').onclick = () => (compiling ? stopCompile() : compile());
$('#btn-compile-menu').onclick = (e) => {
  const r = e.currentTarget.getBoundingClientRect();
  const eng = project?.engine;
  contextMenu(r.right - 220, r.bottom + 4, [
    { label: 'Recompile from scratch', icon: 'broom', action: () => compile({ clean: true }) },
    compiling ? { label: 'Stop compilation', icon: 'stop', action: stopCompile } : null,
    { label: `Auto-compile: ${settings.autoCompile ? 'On' : 'Off'}`, icon: settings.autoCompile ? 'check' : 'x', action: () => setAutoCompile(!settings.autoCompile) },
    '-',
    ...Object.entries(ENGINE_NAMES).map(([k, v]) => ({ label: v, icon: k === eng ? 'check' : '', action: () => setEngine(k) })),
  ]);
};
function setAutoCompile(v) {
  settings.autoCompile = v;
  store('autoCompile', v);
  toast(`Auto-compile ${v ? 'enabled' : 'disabled'}`);
}
async function setEngine(engine) {
  project = { ...project, ...(await api('PATCH', `/api/projects/${projectId}`, { engine })) };
  toast(`Compiler set to ${ENGINE_NAMES[engine]}`);
  compile();
}

async function stopCompile() {
  await api('POST', `/api/projects/${projectId}/stop`).catch(() => {});
}

let overlayTimer;
function showCompileOverlay(on) {
  const el = $('#compile-overlay');
  clearInterval(overlayTimer);
  if (!on) {
    el.classList.add('hidden');
    return;
  }
  const t0 = Date.now();
  const tick = () => {
    const s = Math.floor((Date.now() - t0) / 1000);
    el.innerHTML = `${icon('loader', 'spin')}<span>Compiling… ${s}s${s >= 8 ? ' — first runs download missing LaTeX packages, this can take a minute' : ''}</span>`;
  };
  tick();
  el.classList.remove('hidden');
  overlayTimer = setInterval(tick, 1000);
}

async function compile(opts = {}) {
  if (compiling) {
    pendingCompile = true;
    return;
  }
  compiling = true;
  renderCompileButton();
  showCompileOverlay(true);
  try {
    await saveAll();
    const r = await api('POST', `/api/projects/${projectId}/compile`, opts);
    lastResult = r;
    if (r.pdf) {
      await pdf.load(`/api/projects/${projectId}/output.pdf?b=${r.buildId}`);
      $('#pdf-empty').classList.add('hidden');
    } else if (!pdf.numPages) {
      $('#pdf-empty').classList.remove('hidden');
      $('#pdf-empty').innerHTML = `<div><div class="big">Compilation failed</div>No PDF was produced. Check the logs for details.</div>`;
    }
    applyMarkers();
    updateLogsButton();
    if (r.status === 'failure' || r.status === 'timeout') {
      logsTab = 'errors';
      toggleLogs(true);
    } else if (logsOpen) renderLogs();
    if (r.status === 'cancelled') toast('Compilation stopped');
    if (r.status === 'timeout') toast('Compilation timed out', 'error');
  } catch (e) {
    if (!/already running/.test(e.message)) toast('Compile failed: ' + e.message, 'error');
  } finally {
    compiling = false;
    renderCompileButton();
    showCompileOverlay(false);
    if (pendingCompile) {
      pendingCompile = false;
      compile();
    }
  }
}

// ---------------------------------------------------------------- logs & markers
function resolveLogFile(file) {
  if (!file) return null;
  if (files.some((f) => f.path === file)) return file;
  const base = file.split('/').pop();
  const hit = files.find((f) => f.type === 'file' && f.path.split('/').pop() === base);
  return hit ? hit.path : null;
}

function applyMarkersTo(path) {
  if (!monaco || !lastResult) return;
  const e = models.get(path);
  if (!e) return;
  const sev = { error: monaco.MarkerSeverity.Error, warning: monaco.MarkerSeverity.Warning, typesetting: monaco.MarkerSeverity.Info };
  const lineCount = e.model.getLineCount();
  const markers = [...lastResult.errors, ...lastResult.warnings, ...lastResult.typesetting]
    .filter((x) => x.line && !x.external && resolveLogFile(x.file) === path)
    .map((x) => {
      const line = Math.min(x.line, lineCount);
      return {
        severity: sev[x.level] || monaco.MarkerSeverity.Info,
        message: x.message + (x.hint ? '\n\n' + x.hint : '') + (x.content ? '\n' + x.content : ''),
        startLineNumber: line,
        startColumn: 1,
        endLineNumber: line,
        endColumn: e.model.getLineMaxColumn(line),
        source: 'LaTeX',
      };
    });
  monaco.editor.setModelMarkers(e.model, 'latex', markers);
}
function applyMarkers() {
  for (const p of models.keys()) applyMarkersTo(p);
}

function updateLogsButton() {
  const b = $('#btn-logs');
  const r = lastResult;
  let badge = '';
  if (r?.errors.length) badge = `<span class="log-badge">${r.errors.length}</span>`;
  else if (r?.warnings.length) badge = `<span class="log-badge warn">${r.warnings.length}</span>`;
  b.innerHTML = `${icon('logs')}<span>Logs</span>${badge}`;
  b.classList.toggle('active', logsOpen);
}
$('#btn-logs').onclick = () => toggleLogs();
function toggleLogs(force) {
  logsOpen = force ?? !logsOpen;
  $('#logs').classList.toggle('hidden', !logsOpen);
  if (logsOpen && settings.layout === 'editor') {
    settings.layout = 'split';
    applyLayout();
  }
  if (logsOpen) renderLogs();
  updateLogsButton();
}

function renderLogs() {
  const el = $('#logs');
  const r = lastResult;
  if (!r) {
    el.innerHTML = `<div class="log-ok muted">Compile the document to see logs.</div>`;
    return;
  }
  const groups = { errors: r.errors, warnings: r.warnings, typesetting: r.typesetting };
  if (logsTab === 'errors' && !r.errors.length && r.warnings.length) logsTab = 'warnings';
  const tabBtn = (key, label, n) =>
    `<button class="btn sm ${logsTab === key ? 'active' : 'ghost'}" data-tab="${key}">${label}${n !== undefined ? ` <span class="n">${n}</span>` : ''}</button>`;
  const runs = r.runs.map((x) => x.tool).join(' → ');
  const statusText = {
    success: 'Compiled successfully',
    error: 'Compiled with errors',
    failure: 'Compilation failed',
    timeout: 'Timed out',
    cancelled: 'Stopped',
  }[r.status];
  el.innerHTML = `<div class="log-tabs">
      ${tabBtn('errors', 'Errors', r.errors.length)}${tabBtn('warnings', 'Warnings', r.warnings.length)}${tabBtn('typesetting', 'Typesetting', r.typesetting.length)}
      ${tabBtn('raw', 'Raw log')}${r.bibLog ? tabBtn('bib', r.bibTool === 'biber' ? 'Biber log' : 'BibTeX log') : ''}
      <span style="flex:1"></span><button class="btn ghost icon sm" data-close title="Back to PDF">${icon('x')}</button></div>
    <div class="log-summary">${esc(statusText)} with ${esc(ENGINE_NAMES[r.engine] || r.engine)} in ${(r.duration / 1000).toFixed(1)}s · ${esc(runs)}</div>
    <div class="log-body" style="flex:1;display:flex;flex-direction:column;min-height:0"></div>`;
  el.querySelectorAll('[data-tab]').forEach((b) => {
    b.onclick = () => {
      logsTab = b.dataset.tab;
      renderLogs();
    };
  });
  el.querySelector('[data-close]').onclick = () => toggleLogs(false);
  const body = el.querySelector('.log-body');
  if (logsTab === 'raw' || logsTab === 'bib') {
    const pre = h('<pre class="log-raw"></pre>');
    pre.textContent = logsTab === 'raw' ? r.log : r.bibLog;
    body.appendChild(pre);
    return;
  }
  const list = groups[logsTab] || [];
  const listEl = h('<div class="log-list"></div>');
  if (!list.length) {
    listEl.innerHTML = `<div class="log-ok">${icon('check')} No ${logsTab === 'typesetting' ? 'typesetting issues' : logsTab}.</div>`;
  }
  for (const e of list) {
    const file = resolveLogFile(e.file);
    const where = file ? `${file}${e.line ? `, line ${e.line}` : ''}` : e.file ? `${e.file}${e.line ? `, line ${e.line}` : ''}` : '';
    const item = h(`<div class="log-entry ${e.level}">
      <div class="msg">${esc(e.message)}</div>
      ${where ? `<button class="loc ${file ? '' : 'static'}">${esc(where)}</button>` : ''}
      ${e.hint ? `<div class="fix">${icon('alert')}<span>${esc(e.hint)}</span></div>` : ''}
      ${e.content ? `<pre>${esc(e.content)}</pre>` : ''}</div>`);
    const loc = item.querySelector('.loc');
    if (loc && file) loc.onclick = () => openFile(file, { line: e.line || 1 });
    listEl.appendChild(item);
  }
  body.appendChild(listEl);
}

// ---------------------------------------------------------------- SyncTeX
async function syncForward() {
  if (!activePath || !/\.tex$/i.test(activePath) || !editor.getModel()) return toast('Open a .tex file first');
  if (!lastResult?.pdf && !pdf.numPages) return toast('Compile the document first');
  const pos = editor.getPosition();
  try {
    const boxes = await api(
      'GET',
      `/api/projects/${projectId}/synctex/forward?file=${encodeURIComponent(activePath)}&line=${pos.lineNumber}&column=${pos.column}`
    );
    if (!boxes.length) return toast('No matching location in the PDF (try recompiling)');
    if (logsOpen) toggleLogs(false);
    if (settings.layout === 'editor') {
      settings.layout = 'split';
      applyLayout();
    }
    pdf.highlight(boxes);
  } catch (e) {
    toast(e.message, 'error');
  }
}
$('#btn-sync-fwd').onclick = syncForward;

async function syncInverse(page, x, y) {
  try {
    const r = await api('GET', `/api/projects/${projectId}/synctex/inverse?page=${page}&x=${x.toFixed(2)}&y=${y.toFixed(2)}`);
    if (!r.file) return toast('No source location found for that spot');
    const file = resolveLogFile(r.file);
    if (!file) return toast(`Source is outside the project (${r.file})`);
    if (settings.layout === 'pdf') {
      settings.layout = 'split';
      applyLayout();
    }
    openFile(file, { line: r.line });
  } catch (e) {
    toast(e.message, 'error');
  }
}

// ---------------------------------------------------------------- inserting content
const snipEsc = (s) => String(s).replace(/[\\$}]/g, '\\$&');

function insertSnippet(text) {
  if (!editor.getModel() || editor.getModel().getLanguageId() !== 'latex') {
    toast('Open a .tex file to insert content');
    return false;
  }
  editor.focus();
  editor.getContribution('snippetController2').insert(text);
  return true;
}

function wrap(before, after) {
  const model = editor.getModel();
  if (!model) return;
  const sel = editor.getSelection();
  const text = model.getValueInRange(sel);
  if (text) {
    editor.executeEdits('folio', [{ range: sel, text: before + text + after, forceMoveMarkers: true }]);
  } else {
    insertSnippet(snipEsc(before) + '$1' + snipEsc(after));
  }
  editor.focus();
}

/** Adds \usepackage{pkg} to the main file's preamble if it's missing. */
async function ensurePackage(pkg, extra = '') {
  try {
    const e = await getModel(project.mainFile);
    const text = e.model.getValue();
    const cls = /\\documentclass(\[[^\]]*\])?\{([^}]*)\}/.exec(text)?.[2];
    if (pkg === 'graphicx' && cls === 'beamer') return;
    if (pkg === 'graphicx' && /\\usepackage(\[[^\]]*\])?\{[^}]*\b(graphicx|pgfplots|tikz)\b/.test(text)) return;
    const re = new RegExp(`\\\\(usepackage|RequirePackage)(\\[[^\\]]*\\])?\\{[^}]*\\b${pkg}\\b[^}]*\\}`);
    if (re.test(text)) return;
    const idx = text.search(/^\s*\\begin\{document\}/m);
    if (idx < 0) return;
    const pos = e.model.getPositionAt(idx);
    const line = text.slice(idx).startsWith('\n') ? pos.lineNumber + 1 : pos.lineNumber;
    e.model.pushEditOperations([], [{ range: new monaco.Range(line, 1, line, 1), text: `\\usepackage{${pkg}}\n${extra ? extra + '\n' : ''}` }], () => null);
    toast(`Added \\usepackage{${pkg}} to ${project.mainFile}`);
  } catch {
    /* main file missing; ignore */
  }
}

function slug(s) {
  return String(s).toLowerCase().replace(/\.[^.]+$/, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'item';
}

/** If an image/binary preview is showing, switch back to the last LaTeX file so inserts land there. */
async function ensureTexEditor() {
  const m = activePath && models.get(activePath);
  if (m && m.model.getLanguageId() === 'latex' && !$('#monaco').classList.contains('hidden')) return;
  const target = (lastTexPath && files.some((f) => f.path === lastTexPath) && lastTexPath) || project.mainFile;
  await openFile(target);
}

async function insertFigure(path, caption, { width = '0.8', label } = {}) {
  await ensureTexEditor();
  const lbl = label || 'fig:' + slug(path.split('/').pop());
  const ok = insertSnippet(
    `\\begin{figure}[htbp]\n\t\\centering\n\t\\includegraphics[width=${snipEsc(width)}\\linewidth]{${snipEsc(path)}}\n\t\\caption{\${1:${snipEsc(caption || 'Caption')}}}\n\t\\label{${snipEsc(lbl)}}\n\\end{figure}\n$0`
  );
  if (ok) ensurePackage('graphicx');
}

async function figureDialog(preselect) {
  const images = files.filter((f) => f.type === 'file' && LATEX_IMG_RE.test(f.path));
  let selected = preselect || images[0]?.path || null;
  const body = h(`<div>
    <div class="row" style="margin-bottom:8px"><span class="grow" style="font-size:12.5px;font-weight:600;color:var(--text-muted)">Choose an image</span>
      <button class="btn sm" id="fd-upload">${icon('upload')}Upload image…</button></div>
    <div class="pick-grid" id="fd-grid"></div>
    <div class="grid2" style="margin-top:14px">
      <label class="field"><span>Caption</span><input class="input" id="fd-caption" placeholder="Describe the figure"></label>
      <label class="field"><span>Label</span><input class="input" id="fd-label"></label>
    </div>
    <label class="field"><span>Width</span><select class="input" id="fd-width">
      ${['0.3', '0.4', '0.5', '0.6', '0.7', '0.8', '0.9', '1.0'].map((w) => `<option value="${w}" ${w === '0.8' ? 'selected' : ''}>${Math.round(w * 100)}% of the line width</option>`).join('')}
    </select></label>
    <input type="file" accept="image/*,.pdf,.eps" hidden id="fd-file"></div>`);
  const grid = body.querySelector('#fd-grid');
  const labelInput = body.querySelector('#fd-label');
  const renderGrid = (list) => {
    grid.innerHTML = list.length ? '' : '<div class="hint" style="grid-column:1/-1">No images in this project yet — upload one.</div>';
    for (const f of list) {
      const it = h(`<div class="pick-item ${f.path === selected ? 'selected' : ''}" title="${esc(f.path)}">
        ${IMAGE_RE.test(f.path) ? `<img loading="lazy" src="${fileUrl(projectId, f.path)}&t=${f.mtime}">` : `<div class="noimg">${icon('pdf')}</div>`}
        <div class="fn">${esc(f.path.split('/').pop())}</div></div>`);
      it.onclick = () => {
        selected = f.path;
        labelInput.value = 'fig:' + slug(f.path.split('/').pop());
        grid.querySelectorAll('.pick-item').forEach((x) => x.classList.toggle('selected', x === it));
      };
      grid.appendChild(it);
    }
  };
  renderGrid(images);
  if (selected) labelInput.value = 'fig:' + slug(selected.split('/').pop());
  body.querySelector('#fd-upload').onclick = () => body.querySelector('#fd-file').click();
  body.querySelector('#fd-file').onchange = async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    const [p] = await uploadFiles([{ file: f, rel: f.name }], () => 'images');
    if (p) {
      selected = p;
      labelInput.value = 'fig:' + slug(p.split('/').pop());
      renderGrid(files.filter((x) => x.type === 'file' && LATEX_IMG_RE.test(x.path)));
    }
  };
  const res = await modal({
    title: 'Insert figure',
    body,
    wide: true,
    buttons: [
      { label: 'Cancel', value: null },
      { label: 'Insert', value: 'ok', cls: 'primary' },
    ],
    validate: () => {
      if (!selected) {
        toast('Choose or upload an image first');
        return false;
      }
    },
  });
  if (!res) return;
  await insertFigure(selected, body.querySelector('#fd-caption').value.trim(), {
    width: body.querySelector('#fd-width').value,
    label: labelInput.value.trim(),
  });
}

async function tableDialog() {
  const body = h(`<div>
    <div class="grid2">
      <label class="field"><span>Columns</span><input class="input" type="number" min="1" max="20" value="3" id="td-cols"></label>
      <label class="field"><span>Rows (without header)</span><input class="input" type="number" min="1" max="50" value="3" id="td-rows"></label>
      <label class="field"><span>Caption</span><input class="input" id="td-caption" placeholder="Table caption"></label>
      <label class="field"><span>Label</span><input class="input" id="td-label" value="tab:my-table"></label>
    </div>
    <label class="check"><input type="checkbox" id="td-booktabs" checked><span>Use booktabs rules (recommended)<div class="hint">Adds \\usepackage{booktabs} if needed.</div></span></label>
    <label class="check"><input type="checkbox" id="td-float" checked><span>Wrap in a floating table environment with caption</span></label></div>`);
  const res = await modal({ title: 'Insert table', body, buttons: [{ label: 'Cancel', value: null }, { label: 'Insert', value: 'ok', cls: 'primary' }] });
  if (!res) return;
  const cols = Math.max(1, Math.min(20, +body.querySelector('#td-cols').value || 3));
  const rows = Math.max(1, Math.min(50, +body.querySelector('#td-rows').value || 3));
  const bt = body.querySelector('#td-booktabs').checked;
  const fl = body.querySelector('#td-float').checked;
  let n = 1;
  const cell = (d) => `\${${n++}:${d}}`;
  const ind = fl ? '\t\t' : '\t';
  const lines = [];
  lines.push(`${ind}${bt ? '\\\\toprule' : '\\\\hline'}`);
  lines.push(ind + Array.from({ length: cols }, (_, i) => cell(`Header ${i + 1}`)).join(' & ') + ' \\\\\\\\');
  lines.push(`${ind}${bt ? '\\\\midrule' : '\\\\hline'}`);
  for (let r = 0; r < rows; r++) lines.push(ind + Array.from({ length: cols }, () => cell(' ')).join(' & ') + ' \\\\\\\\');
  lines.push(`${ind}${bt ? '\\\\bottomrule' : '\\\\hline'}`);
  const spec = bt ? 'l' + 'c'.repeat(cols - 1) : '|' + Array(cols).fill('c').join('|') + '|';
  const tabular = `${fl ? '\t' : ''}\\\\begin{tabular}{${spec}}\n${lines.join('\n')}\n${fl ? '\t' : ''}\\\\end{tabular}`;
  const caption = snipEsc(body.querySelector('#td-caption').value.trim() || 'Caption');
  const label = snipEsc(body.querySelector('#td-label').value.trim());
  const snip = fl
    ? `\\\\begin{table}[htbp]\n\t\\\\centering\n\t\\\\caption{${caption}}\n\t\\\\label{${label}}\n${tabular}\n\\\\end{table}\n$0`
    : `${tabular}\n$0`;
  await ensureTexEditor();
  if (insertSnippet(snip) && bt) ensurePackage('booktabs');
}

async function plotDialog() {
  const dataFiles = files.filter((f) => f.type === 'file' && /\.(csv|dat|txt|tsv)$/i.test(f.path));
  let mode = 'function';
  const body = h(`<div>
    <div class="seg"><button data-m="function" class="on">Function</button><button data-m="data">Data file (CSV)</button></div>
    <div id="pd-fn">
      <label class="field"><span>Expression in x</span><input class="input mono" id="pd-expr" value="x^2"></label>
      <div class="hint" style="margin:-6px 0 12px">pgfplots uses degrees for trig functions: write <code>sin(deg(x))</code> for radians.</div>
      <div class="grid2">
        <label class="field"><span>x from</span><input class="input" id="pd-from" value="-3"></label>
        <label class="field"><span>x to</span><input class="input" id="pd-to" value="3"></label>
      </div>
    </div>
    <div id="pd-data" class="hidden">
      ${dataFiles.length ? `<label class="field"><span>Data file</span><select class="input" id="pd-file">${dataFiles.map((f) => `<option>${esc(f.path)}</option>`).join('')}</select></label>
      <div class="grid2"><label class="field"><span>x column</span><select class="input" id="pd-x"></select></label>
      <label class="field"><span>y column</span><select class="input" id="pd-y"></select></label></div>` : '<p class="hint">No .csv/.dat files in the project. Upload one first (first row = column names).</p>'}
    </div>
    <div class="grid2">
      <label class="field"><span>x-axis label</span><input class="input" id="pd-xl" value="$x$"></label>
      <label class="field"><span>y-axis label</span><input class="input" id="pd-yl" value="$y$"></label>
      <label class="field"><span>Caption</span><input class="input" id="pd-cap" placeholder="Optional — wraps the plot in a figure"></label>
      <label class="field"><span>Legend entry</span><input class="input" id="pd-leg" placeholder="Optional"></label>
    </div>
    <label class="check"><input type="checkbox" id="pd-marks"><span>Show markers</span></label></div>`);
  const seg = body.querySelectorAll('.seg button');
  seg.forEach((b) => {
    b.onclick = () => {
      mode = b.dataset.m;
      seg.forEach((x) => x.classList.toggle('on', x === b));
      body.querySelector('#pd-fn').classList.toggle('hidden', mode !== 'function');
      body.querySelector('#pd-data').classList.toggle('hidden', mode !== 'data');
      if (mode === 'data') body.querySelector('#pd-marks').checked = true;
    };
  });
  let sep = 'comma';
  const loadCols = async () => {
    const sel = body.querySelector('#pd-file');
    if (!sel) return;
    const text = await api('GET', fileUrl(projectId, sel.value));
    const first = String(text).split(/\r?\n/).find((l) => l.trim() && !l.startsWith('#') && !l.startsWith('%')) || '';
    sep = first.includes(',') ? 'comma' : first.includes(';') ? 'semicolon' : first.includes('\t') ? 'tab' : 'space';
    const cols = first.split(/[,;\t ]+/).filter(Boolean);
    const opts = cols.map((c) => `<option>${esc(c)}</option>`).join('');
    body.querySelector('#pd-x').innerHTML = opts;
    body.querySelector('#pd-y').innerHTML = opts;
    if (cols[1]) body.querySelector('#pd-y').value = cols[1];
  };
  body.querySelector('#pd-file')?.addEventListener('change', loadCols);
  loadCols().catch(() => {});

  const res = await modal({ title: 'Insert plot', body, wide: true, buttons: [{ label: 'Cancel', value: null }, { label: 'Insert', value: 'ok', cls: 'primary' }] });
  if (!res) return;
  const v = (id) => body.querySelector(id)?.value.trim() || '';
  const marks = body.querySelector('#pd-marks').checked;
  const style = `thick, blue${marks ? ', mark=*' : ', no markers'}`;
  let addplot;
  if (mode === 'data') {
    if (!v('#pd-file')) return toast('No data file selected', 'error');
    addplot = `\\addplot[${style}] table[x=${v('#pd-x')}, y=${v('#pd-y')}, col sep=${sep}] {${v('#pd-file')}};`;
  } else {
    addplot = `\\addplot[${style}, domain=${v('#pd-from') || -3}:${v('#pd-to') || 3}, samples=100] {${v('#pd-expr') || 'x^2'}};`;
  }
  const leg = v('#pd-leg') ? `\n\t\t\\addlegendentry{${v('#pd-leg')}}` : '';
  const axis = `\\begin{tikzpicture}\n\t\\begin{axis}[xlabel={${v('#pd-xl')}}, ylabel={${v('#pd-yl')}}, grid=major, width=0.8\\linewidth, height=6cm]\n\t\t${addplot}${leg}\n\t\\end{axis}\n\\end{tikzpicture}`;
  const cap = v('#pd-cap');
  const raw = cap
    ? `\\begin{figure}[htbp]\n\t\\centering\n${axis.replace(/^/gm, '\t')}\n\t\\caption{${cap}}\n\t\\label{fig:${slug(cap)}}\n\\end{figure}\n`
    : axis + '\n';
  if (insertSnippet(snipEsc(raw) + '$0')) ensurePackage('pgfplots', '\\pgfplotsset{compat=1.18}');
}

async function citeDialog() {
  symbols = await api('GET', `/api/projects/${projectId}/symbols`).catch(() => symbols);
  const cites = symbols.cites;
  const main = (await getModel(project.mainFile).catch(() => null))?.model.getValue() || '';
  const defCmd = /\{biblatex\}/.test(main) ? 'autocite' : /\{natbib\}/.test(main) ? 'citep' : 'cite';
  const chosen = new Set();
  const body = h(`<div>
    ${cites.length ? '' : '<p class="hint">No entries found in this project\'s .bib files. Create a <b>references.bib</b> file and add entries, then load it with <code>\\addbibresource{references.bib}</code> (biblatex) or <code>\\bibliography{references}</code> (BibTeX).</p>'}
    <div class="row" style="margin-bottom:10px"><input class="input grow" id="cd-q" placeholder="Search by key, title or author"><select class="input" id="cd-cmd" style="width:140px">
      ${['cite', 'autocite', 'parencite', 'textcite', 'citep', 'citet', 'footcite'].map((c) => `<option ${c === defCmd ? 'selected' : ''}>${c}</option>`).join('')}</select></div>
    <div class="cite-list" id="cd-list"></div></div>`);
  const listEl = body.querySelector('#cd-list');
  const render = () => {
    const q = body.querySelector('#cd-q').value.toLowerCase();
    listEl.replaceChildren(
      ...cites
        .filter((c) => !q || `${c.key} ${c.title} ${c.author}`.toLowerCase().includes(q))
        .map((c) => {
          const row = h(`<label class="cite-row"><input type="checkbox" ${chosen.has(c.key) ? 'checked' : ''}><div>
            <div class="k">${esc(c.key)}</div><div class="t">${esc(c.title || '(no title)')}</div>
            <div class="a">${esc([c.author, c.year].filter(Boolean).join(' · '))}</div></div></label>`);
          row.querySelector('input').onchange = (e) => (e.target.checked ? chosen.add(c.key) : chosen.delete(c.key));
          return row;
        })
    );
  };
  body.querySelector('#cd-q').oninput = render;
  render();
  const res = await modal({ title: 'Insert citation', body, wide: true, buttons: [{ label: 'Cancel', value: null }, { label: 'Insert', value: 'ok', cls: 'primary' }] });
  if (!res) return;
  const cmd = body.querySelector('#cd-cmd').value;
  await ensureTexEditor();
  if (!chosen.size) {
    if (insertSnippet(`\\\\${cmd}{$0}`)) editor.trigger('folio', 'editor.action.triggerSuggest', {});
    return;
  }
  insertSnippet(`\\\\${cmd}{${snipEsc([...chosen].join(','))}}$0`);
}

const FMT = {
  bold: () => wrap('\\textbf{', '}'),
  italic: () => wrap('\\textit{', '}'),
  section: () => insertSnippet('\\\\section{${1:Title}}\n$0'),
  itemize: () => insertSnippet('\\\\begin{itemize}\n\t\\\\item $0\n\\\\end{itemize}'),
  enumerate: () => insertSnippet('\\\\begin{enumerate}\n\t\\\\item $0\n\\\\end{enumerate}'),
  math: (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    contextMenu(r.left, r.bottom + 4, [
      { label: 'Inline math  $…$', icon: 'sigma', action: () => wrap('$', '$') },
      { label: 'Numbered equation', icon: 'sigma', action: () => insertSnippet('\\\\begin{equation}\n\t${1:E = mc^2}\n\t\\\\label{eq:${2:label}}\n\\\\end{equation}\n$0') },
      { label: 'Unnumbered display math  \\[…\\]', icon: 'sigma', action: () => insertSnippet('\\\\[\n\t$1\n\\\\]\n$0') },
      { label: 'Aligned equations', icon: 'sigma', action: () => insertSnippet('\\\\begin{align}\n\t${1:a} &= ${2:b} \\\\\\\\\n\t${3:c} &= ${4:d}\n\\\\end{align}\n$0') },
    ]);
  },
  figure: () => figureDialog(),
  table: () => tableDialog(),
  plot: () => plotDialog(),
  cite: () => citeDialog(),
  ref: () => {
    if (insertSnippet('\\\\ref{$0}')) editor.trigger('folio', 'editor.action.triggerSuggest', {});
  },
  link: () => insertSnippet('\\\\href{${1:https://}}{${2:link text}}$0'),
  lab: () => openLab(),
  import: () => openImport(),
};
document.querySelectorAll('[data-fmt]').forEach((b) => {
  b.onclick = (e) => FMT[b.dataset.fmt](e);
});

// ---------------------------------------------------------------- Folio Lab (analysis results, see lab.js)
/** Re-read open models under a path prefix after the server rewrote those files (unless they have unsaved edits). */
async function reloadFromDisk(prefix) {
  for (const [p, e] of models) {
    if (!p.startsWith(prefix) || e.model.isDisposed() || e.model.getVersionId() !== e.savedVersion) continue;
    try {
      const r = await api('GET', fileUrl(projectId, p), undefined, { raw: true });
      e.model.setValue(await r.text());
      e.savedVersion = e.model.getVersionId();
    } catch {
      /* file gone */
    }
  }
  updateSaveState();
}
initLab({
  projectId,
  project: () => project,
  monaco: () => monaco,
  editor: () => editor,
  insertSnippet,
  snipEsc,
  ensurePackage,
  ensureTexEditor,
  getModel,
  refreshFiles,
  reloadFromDisk,
});
initImport({ projectId, refreshFiles, openLab });

// ---------------------------------------------------------------- settings
$('#btn-settings').onclick = async () => {
  const texFiles = files.filter((f) => f.type === 'file' && /\.tex$/i.test(f.path));
  const theme = localStorage.getItem('folio.theme') || 'system';
  const body = h(`<div>
    <div class="grid2">
      <label class="field"><span>Compiler</span><select class="input" id="s-engine">
        ${Object.entries(ENGINE_NAMES).map(([k, v]) => `<option value="${k}" ${k === project.engine ? 'selected' : ''}>${v}</option>`).join('')}</select></label>
      <label class="field"><span>Main document</span><select class="input" id="s-main">
        ${texFiles.map((f) => `<option ${f.path === project.mainFile ? 'selected' : ''}>${esc(f.path)}</option>`).join('')}</select></label>
    </div>
    <div class="hint" style="margin:-6px 0 12px">Use XeLaTeX or LuaLaTeX for system fonts (fontspec) and full Unicode.</div>
    <label class="check"><input type="checkbox" id="s-shell" ${project.shellEscape ? 'checked' : ''}><span>Enable shell-escape
      <div class="hint">Needed by minted, gnuplot plots, the svg package and externalised TikZ. Only enable for documents you trust: it lets LaTeX run programs on your computer.</div></span></label>
    <label class="check"><input type="checkbox" id="s-auto" ${settings.autoCompile ? 'checked' : ''}><span>Auto-compile after edits</span></label>
    <div class="grid2">
      <label class="field"><span>Editor font size</span><input class="input" type="number" min="10" max="28" id="s-font" value="${settings.fontSize}"></label>
      <label class="field"><span>Theme</span><select class="input" id="s-theme">
        ${['system', 'light', 'dark'].map((t) => `<option ${t === theme ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
    </div>
    <label class="check"><input type="checkbox" id="s-wrap" ${settings.wordWrap ? 'checked' : ''}><span>Wrap long lines</span></label>
    <div class="row" style="margin-top:6px"><button class="btn" id="s-clean">${icon('broom')}Clear cached build files</button>
      <span class="hint">${texStatus?.found ? `TeX: ${esc(texStatus.distribution)}` : 'No TeX distribution found'}</span></div></div>`);
  body.querySelector('#s-clean').onclick = async () => {
    await api('POST', `/api/projects/${projectId}/clean`);
    toast('Build cache cleared');
  };
  const res = await modal({ title: 'Settings', body, buttons: [{ label: 'Cancel', value: null }, { label: 'Save', value: 'ok', cls: 'primary' }] });
  if (!res) return;
  const patch = {
    engine: body.querySelector('#s-engine').value,
    shellEscape: body.querySelector('#s-shell').checked,
  };
  const main = body.querySelector('#s-main').value;
  if (main) patch.mainFile = main;
  const changed = patch.engine !== project.engine || patch.shellEscape !== project.shellEscape || patch.mainFile !== project.mainFile;
  try {
    project = { ...project, ...(await api('PATCH', `/api/projects/${projectId}`, patch)) };
  } catch (e) {
    toast(e.message, 'error');
  }
  settings.autoCompile = body.querySelector('#s-auto').checked;
  settings.fontSize = Math.max(10, Math.min(28, +body.querySelector('#s-font').value || 14));
  settings.wordWrap = body.querySelector('#s-wrap').checked;
  store('autoCompile', settings.autoCompile);
  store('fontSize', settings.fontSize);
  store('wordWrap', settings.wordWrap);
  editor.updateOptions({ fontSize: settings.fontSize, wordWrap: settings.wordWrap ? 'on' : 'off' });
  applyTheme(body.querySelector('#s-theme').value);
  themeIcon();
  tree.setFiles(files, project.mainFile);
  if (changed) compile();
};

$('#btn-download').onclick = () => {
  if (!lastResult?.pdf && !pdf.numPages) return toast('Compile the document first');
  location.href = `/api/projects/${projectId}/output.pdf?download=1`;
};
// two kinds of ZIP. The Folio project re-imports into Folio; the portable one works in any LaTeX project.
function portablePrefix(name) {
  let p = String(name || '').normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40) || 'bericht';
  if (!/^[a-z]/.test(p)) p = 'r-' + p;
  if (p.length > 24) p = p.slice(0, 25).replace(/-[^-]*$/, '') || p.slice(0, 24);
  return p.slice(0, 24).replace(/-+$/, '') || 'bericht';
}
async function downloadPortable() {
  const prefix = await prompt('Portable LaTeX (.zip)', 'Prefix for the folder, labels and citation keys', portablePrefix(project.name), {
    okLabel: 'Download',
    hint: 'The ZIP holds one folder with the text, a preamble, the references (biblatex and BibTeX) and only the files the text uses. README.txt lists the lines another LaTeX project needs.',
  });
  if (prefix == null) return;
  try {
    const r = await fetch(`/api/projects/${projectId}/zip?portable=1&prefix=${encodeURIComponent(prefix)}`);
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || `Export failed (${r.status})`);
    const cd = r.headers.get('Content-Disposition') || '';
    const m = /filename\*=UTF-8''([^;]+)/.exec(cd);
    const a = document.createElement('a');
    a.href = URL.createObjectURL(await r.blob());
    a.download = m ? decodeURIComponent(m[1]) : `${prefix}.zip`;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => (URL.revokeObjectURL(a.href), a.remove()), 1000);
  } catch (e) {
    toast(e.message, 'error');
  }
}
$('#btn-zip').onclick = (e) => {
  const r = e.currentTarget.getBoundingClientRect();
  contextMenu(r.left, r.bottom + 4, [
    { label: 'Folio project (.zip)', icon: 'folder', action: () => (location.href = `/api/projects/${projectId}/zip`) },
    { label: 'Portable LaTeX for other projects (.zip) …', icon: 'download', action: downloadPortable },
  ]);
};

// Global shortcuts (when focus is outside Monaco)
document.addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && (e.key === 's' || e.key === 'Enter')) {
    e.preventDefault();
    compile();
  }
});

// ---------------------------------------------------------------- boot
(async function boot() {
  try {
    await loadProject();
  } catch (e) {
    document.body.innerHTML = `<div class="empty" style="margin:15vh auto;max-width:440px"><h3>Project not found</h3><p>${esc(e.message)}</p><a class="btn primary" href="/">Back to projects</a></div>`;
    return;
  }
  updateLogsButton();
  updateSaveState();
  tree.setFiles(files, project.mainFile);
  api('GET', '/api/status').then((s) => {
    texStatus = s.tex;
    if (!s.tex.found) toast('No TeX distribution found — run setup.ps1, then restart Folio.', 'error', 10000);
  });
  scheduleSymbols(0);

  monaco = await loadMonaco();
  createEditor();
  themeIcon();

  const last = store(`last.${projectId}`);
  const first = files.some((f) => f.path === last) ? last : files.some((f) => f.path === project.mainFile) ? project.mainFile : files.find((f) => f.type === 'file')?.path;
  if (first) await openFile(first);
  else {
    $('#monaco').classList.add('hidden');
    $('#preview').classList.remove('hidden');
    $('#preview').innerHTML = '<div class="welcome">This project is empty. Create or upload a file to start.</div>';
  }

  if (project.build?.pdf) {
    try {
      await pdf.load(`/api/projects/${projectId}/output.pdf?b=${project.build.buildId}`);
      $('#pdf-empty').classList.add('hidden');
    } catch {
      /* stale */
    }
  }
  if (!project.compiling) compile();

  // Results may arrive from an analysis tab at any time: pick up new files when this tab comes back.
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') refreshFiles().catch(() => {});
  });
  // Opened from an analysis ("Open report"): show the results that were just sent.
  const labSlug = new URLSearchParams(location.search).get('lab');
  if (labSlug) {
    history.replaceState(null, '', location.pathname);
    openLab(labSlug);
  }
})();
