// Project file tree: nested folders, selection, drag & drop (OS uploads and internal moves).
import { esc, icon, store } from '../ui.js';

export const IMAGE_RE = /\.(png|jpe?g|gif|bmp|webp|svg)$/i;
export const BINARY_RE = /\.(png|jpe?g|gif|bmp|webp|tiff?|ico|pdf|eps|ps|zip|gz|tgz|tar|7z|rar|ttf|otf|woff2?|pfb|afm|docx?|xlsx?|pptx?|odt|mp4|mov|mp3|wav|exe|dll|so|dylib|class|jar|pyc|synctex)$/i;

export function fileIcon(path) {
  if (/\.(tex|sty|cls|ltx|dtx)$/i.test(path)) return { name: 'file-text', cls: 'tex' };
  if (/\.(bib|bst|bbx|cbx)$/i.test(path)) return { name: 'book', cls: 'bib' };
  if (IMAGE_RE.test(path) || /\.(eps|tiff?)$/i.test(path)) return { name: 'image', cls: 'img' };
  if (/\.pdf$/i.test(path)) return { name: 'pdf', cls: 'pdf' };
  if (/\.(csv|tsv|dat|txt|json|xlsx?)$/i.test(path)) return { name: 'data', cls: 'data' };
  return { name: 'file', cls: '' };
}

export class FileTree {
  constructor(el, projectId, { onOpen, onContext, onMove, onUpload }) {
    this.el = el;
    this.projectId = projectId;
    this.onOpen = onOpen;
    this.onContext = onContext;
    this.onMove = onMove;
    this.onUpload = onUpload;
    this.files = [];
    this.mainFile = null;
    this.selected = null;
    this.expanded = new Set(store(`tree.${projectId}`) || []);
    this.bindRootDnD();
    el.addEventListener('contextmenu', (e) => {
      if (e.target === el) {
        e.preventDefault();
        this.onContext(null, 'dir', e.clientX, e.clientY);
      }
    });
  }

  setFiles(files, mainFile) {
    this.files = files;
    this.mainFile = mainFile;
    this.render();
  }

  select(path) {
    this.selected = path;
    // Make sure parents are expanded
    if (path) {
      const parts = path.split('/');
      for (let i = 1; i < parts.length; i++) this.expanded.add(parts.slice(0, i).join('/'));
      this.persist();
    }
    this.render();
    const el = this.el.querySelector(`[data-path="${CSS.escape(path || '')}"]`);
    el?.scrollIntoView({ block: 'nearest' });
  }

  /** Folder that new files should go into, based on the selection. */
  currentFolder() {
    const s = this.selected;
    if (!s) return '';
    const f = this.files.find((x) => x.path === s);
    if (f && f.type === 'dir') return s;
    return s.includes('/') ? s.slice(0, s.lastIndexOf('/')) : '';
  }

  persist() {
    store(`tree.${this.projectId}`, [...this.expanded]);
  }

  buildTree() {
    const root = { children: new Map() };
    for (const f of this.files) {
      const parts = f.path.split('/');
      let node = root;
      parts.forEach((part, i) => {
        const p = parts.slice(0, i + 1).join('/');
        if (!node.children.has(part)) node.children.set(part, { name: part, path: p, type: i === parts.length - 1 ? f.type : 'dir', children: new Map() });
        node = node.children.get(part);
      });
    }
    return root;
  }

  render() {
    const root = this.buildTree();
    const frag = document.createDocumentFragment();
    const walk = (node, depth) => {
      const kids = [...node.children.values()].sort((a, b) =>
        a.type !== b.type ? (a.type === 'dir' ? -1 : 1) : a.name.localeCompare(b.name, undefined, { sensitivity: 'base', numeric: true })
      );
      for (const k of kids) {
        frag.appendChild(this.renderItem(k, depth));
        if (k.type === 'dir' && this.expanded.has(k.path)) walk(k, depth + 1);
      }
    };
    walk(root, 0);
    this.el.replaceChildren(frag);
    if (!this.files.length) this.el.innerHTML = '<div class="outline-empty">No files yet. Drop files here to upload.</div>';
  }

  renderItem(node, depth) {
    const isDir = node.type === 'dir';
    const open = isDir && this.expanded.has(node.path);
    const fi = isDir ? { name: open ? 'folder-open' : 'folder', cls: 'folder' } : fileIcon(node.path);
    const el = document.createElement('div');
    el.className = `tree-item${open ? ' open' : ''}${this.selected === node.path ? ' selected' : ''}`;
    el.dataset.path = node.path;
    el.dataset.type = node.type;
    el.draggable = true;
    el.style.paddingLeft = 6 + depth * 14 + 'px';
    el.title = node.path;
    el.innerHTML = `<span class="chev">${isDir ? icon('chevron') : ''}</span><span class="ficon ${fi.cls}">${icon(fi.name)}</span>
      <span class="name">${esc(node.name)}</span>${node.path === this.mainFile ? '<span class="main-badge" title="Main document">MAIN</span>' : ''}
      <button class="btn ghost icon sm more" title="More">${icon('more')}</button>`;
    el.onclick = (e) => {
      if (e.target.closest('.more')) {
        const r = e.target.closest('.more').getBoundingClientRect();
        this.selected = node.path;
        this.render();
        this.onContext(node.path, node.type, r.left, r.bottom + 2);
        return;
      }
      if (isDir) {
        if (open) this.expanded.delete(node.path);
        else this.expanded.add(node.path);
        this.persist();
        this.selected = node.path;
        this.render();
      } else {
        this.onOpen(node.path);
      }
    };
    el.oncontextmenu = (e) => {
      e.preventDefault();
      e.stopPropagation();
      this.selected = node.path;
      this.render();
      this.onContext(node.path, node.type, e.clientX, e.clientY);
    };
    el.ondragstart = (e) => {
      e.dataTransfer.setData('text/x-folio-path', node.path);
      e.dataTransfer.effectAllowed = 'move';
    };
    const folder = isDir ? node.path : node.path.includes('/') ? node.path.slice(0, node.path.lastIndexOf('/')) : '';
    el.ondragover = (e) => {
      e.preventDefault();
      e.stopPropagation();
      this.clearDropTargets();
      const target = isDir ? el : this.el.querySelector(`[data-path="${CSS.escape(folder)}"]`) || this.el;
      target.classList.add('drop-target');
    };
    el.ondragleave = () => el.classList.remove('drop-target');
    el.ondrop = (e) => this.handleDrop(e, folder);
    return el;
  }

  clearDropTargets() {
    this.el.querySelectorAll('.drop-target').forEach((x) => x.classList.remove('drop-target'));
    this.el.classList.remove('drop-target');
  }

  bindRootDnD() {
    this.el.addEventListener('dragover', (e) => {
      e.preventDefault();
      if (e.target === this.el) {
        this.clearDropTargets();
        this.el.classList.add('drop-target');
      }
    });
    this.el.addEventListener('dragleave', (e) => {
      if (!this.el.contains(e.relatedTarget)) this.clearDropTargets();
    });
    this.el.addEventListener('drop', (e) => this.handleDrop(e, ''));
  }

  async handleDrop(e, folder) {
    e.preventDefault();
    e.stopPropagation();
    this.clearDropTargets();
    const moved = e.dataTransfer.getData('text/x-folio-path');
    if (moved) {
      const name = moved.split('/').pop();
      const to = folder ? `${folder}/${name}` : name;
      if (to !== moved && !folder.startsWith(moved + '/') && folder !== moved) this.onMove(moved, to);
      return;
    }
    const items = [...(e.dataTransfer.items || [])];
    const entries = items.map((it) => it.webkitGetAsEntry && it.webkitGetAsEntry()).filter(Boolean);
    if (entries.length) {
      const files = [];
      await Promise.all(entries.map((en) => collectEntry(en, '', files)));
      this.onUpload(files, folder);
    } else if (e.dataTransfer.files.length) {
      this.onUpload([...e.dataTransfer.files].map((f) => ({ file: f, rel: f.name })), folder);
    }
  }
}

/** Recursively read a dropped file/folder entry into [{ file, rel }]. */
function collectEntry(entry, prefix, out) {
  return new Promise((resolve) => {
    if (entry.isFile) {
      entry.file(
        (f) => {
          out.push({ file: f, rel: prefix + f.name });
          resolve();
        },
        () => resolve()
      );
    } else if (entry.isDirectory) {
      const reader = entry.createReader();
      const all = [];
      const read = () =>
        reader.readEntries(async (batch) => {
          if (!batch.length) {
            await Promise.all(all.map((c) => collectEntry(c, prefix + entry.name + '/', out)));
            resolve();
          } else {
            all.push(...batch);
            read();
          }
        }, () => resolve());
      read();
    } else resolve();
  });
}
