// Shared UI helpers: API calls, icons, modals, toasts, context menus, theme.

export async function api(method, url, body, { raw = false } = {}) {
  const opts = { method, headers: { 'X-Folio': '1' } };
  if (body !== undefined) {
    if (body instanceof Blob || body instanceof ArrayBuffer || typeof body === 'string') opts.body = body;
    else {
      opts.body = JSON.stringify(body);
      opts.headers['Content-Type'] = 'application/json';
    }
  }
  const r = await fetch(url, opts);
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`;
    try {
      msg = (await r.json()).error || msg;
    } catch {
      /* not json */
    }
    throw new Error(msg);
  }
  if (raw) return r;
  const ct = r.headers.get('content-type') || '';
  return ct.includes('json') ? r.json() : r.text();
}

export const fileUrl = (id, path, download = false) =>
  `/api/projects/${id}/file?path=${encodeURIComponent(path)}${download ? '&download=1' : ''}`;

export function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
}

export function h(html) {
  const t = document.createElement('template');
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

// ---------------------------------------------------------------- icons
const P = {
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  'folder-open': '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h7a2 2 0 0 1 2 2v1"/><path d="M3 19l2.5-7.5A2 2 0 0 1 7.4 10H21l-2.6 7.6a2 2 0 0 1-1.9 1.4H3z"/>',
  'folder-plus': '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M12 10v6M9 13h6"/>',
  file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
  'file-plus': '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M12 11v6M9 14h6"/>',
  'file-text': '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>',
  image: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M21 16l-5-5-9 9"/>',
  pdf: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M8.5 16.5c2-1 5-5 4-7-.6-1.1-2-.4-1.5 1.5.6 2.4 3 4.6 5 5"/>',
  flask: '<path d="M9 3h6M10 3v6L4.6 18.2A2 2 0 0 0 6.3 21h11.4a2 2 0 0 0 1.7-2.8L14 9V3"/><path d="M7.5 14h9"/>',
  data: '<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M4 10h16M4 15h16M10 4v16"/>',
  book: '<path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"/><path d="M4 19V5M19 19v2H6"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  upload: '<path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>',
  download: '<path d="M12 4v12M7 11l5 5 5-5"/><path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/>',
  edit: '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13.5 6.5l4 4"/>',
  copy: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/>',
  play: '<path d="M7 4v16l13-8z"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="1.5"/>',
  refresh: '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/>',
  loader: '<path d="M12 3a9 9 0 1 0 9 9"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  chevron: '<path d="M9 6l6 6-6 6"/>',
  'chevron-down': '<path d="M6 9l6 6 6-6"/>',
  'chevron-up': '<path d="M6 15l6-6 6 6"/>',
  grip: '<circle cx="9" cy="6" r="1"/><circle cx="15" cy="6" r="1"/><circle cx="9" cy="12" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="9" cy="18" r="1"/><circle cx="15" cy="18" r="1"/>',
  merge: '<path d="M6 3v6a6 6 0 0 0 6 6h0a6 6 0 0 1 6 6"/><path d="M18 3v6a6 6 0 0 1-6 6"/><path d="M9 21h6"/>',
  'arrow-left': '<path d="M19 12H5M11 18l-6-6 6-6"/>',
  'arrow-right': '<path d="M5 12h14M13 6l6 6-6 6"/>',
  logs: '<path d="M4 6h16M4 12h10M4 18h13"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  moon: '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
  'zoom-in': '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4M11 8v6M8 11h6"/>',
  'zoom-out': '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4M8 11h6"/>',
  'fit-width': '<path d="M4 12h16M7 9l-3 3 3 3M17 9l3 3-3 3"/><path d="M4 4v2M20 4v2M4 18v2M20 18v2"/>',
  x: '<path d="M6 6l12 12M18 6L6 18"/>',
  star: '<path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.5 2.9 1-6.1L3.2 9.5l6.1-.9z"/>',
  more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/>',
  chart: '<path d="M4 20V4M4 20h16"/><path d="M7 15l4-5 3 3 5-7"/>',
  layers: '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>',
  slides: '<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8M12 17v4"/>',
  quote: '<path d="M7 7h4v4c0 3-1.5 5-4 6M14 7h4v4c0 3-1.5 5-4 6"/>',
  blank: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
  bold: '<path d="M7 5h6a3.5 3.5 0 0 1 0 7H7zM7 12h7a3.5 3.5 0 0 1 0 7H7z"/>',
  italic: '<path d="M10 5h8M6 19h8M14 5l-4 14"/>',
  list: '<path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.5" cy="6" r=".8"/><circle cx="4.5" cy="12" r=".8"/><circle cx="4.5" cy="18" r=".8"/>',
  'list-ol': '<path d="M10 6h10M10 12h10M10 18h10M4 4.5h1.5V9M4 9h3M4 14.5c.5-.7 2.8-.8 2.8.6 0 1.1-2.8 2.2-2.8 3.4h3"/>',
  sigma: '<path d="M18 6V4H6l6 8-6 8h12v-2"/>',
  calc: '<rect x="5" y="2.5" width="14" height="19" rx="2"/><path d="M8 6.5h8v3H8z"/><path d="M8.5 13h.01M12 13h.01M15.5 13h.01M8.5 16.5h.01M12 16.5h.01M15.5 16.5h.01"/>',
  table: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M3 15h18M9 4v16M15 4v16"/>',
  heading: '<path d="M6 4v16M18 4v16M6 12h12"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3A4 4 0 0 0 11 18.7l1-1"/>',
  cite: '<path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"/><path d="M9 8h6M9 12h4"/>',
  ref: '<path d="M7 4h10v17l-5-4-5 4z"/>',
  sidebar: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/>',
  columns: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M12 4v16"/>',
  code: '<path d="M8 7l-5 5 5 5M16 7l5 5-5 5"/>',
  eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  external: '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
  check: '<path d="M5 12l5 5L20 7"/>',
  alert: '<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18v.01"/>',
  broom: '<path d="M19 4l-7 7M8 11l5 5-2 5c-3-1-6-4-7-7z"/>',
};
export function icon(name, cls = '') {
  return `<svg class="i ${cls}" viewBox="0 0 24 24" aria-hidden="true">${P[name] || P.file}</svg>`;
}

// ---------------------------------------------------------------- theme
export function applyTheme(theme = localStorage.getItem('folio.theme') || 'system') {
  if (theme === 'system') document.documentElement.removeAttribute('data-theme');
  else document.documentElement.setAttribute('data-theme', theme);
  try {
    localStorage.setItem('folio.theme', theme);
  } catch {
    /* storage unavailable */
  }
  window.dispatchEvent(new CustomEvent('folio-theme'));
}
export function isDark() {
  const t = document.documentElement.getAttribute('data-theme');
  if (t) return t === 'dark';
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
}
export function store(key, value) {
  try {
    if (value === undefined) return JSON.parse(localStorage.getItem('folio.' + key));
    localStorage.setItem('folio.' + key, JSON.stringify(value));
  } catch {
    return undefined;
  }
}

// ---------------------------------------------------------------- toast
let toastHost;
export function toast(msg, type = 'info', ms = 3200) {
  if (!toastHost) {
    toastHost = h('<div class="toasts"></div>');
    document.body.appendChild(toastHost);
  }
  const t = h(`<div class="toast ${type}">${esc(msg)}</div>`);
  toastHost.appendChild(t);
  setTimeout(() => t.remove(), ms);
}

// ---------------------------------------------------------------- modal
/**
 * modal({ title, body (html or element), buttons: [{label, value, cls}], wide, onOpen(el), validate(value, el) })
 * Resolves with the clicked button's value (null on cancel/escape).
 */
export function modal({ title, body = '', buttons = [{ label: 'OK', value: true, cls: 'primary' }], wide = false, onOpen, validate }) {
  return new Promise((resolve) => {
    const back = h(`<div class="modal-backdrop"><div class="modal ${wide ? 'wide' : ''}" role="dialog" aria-modal="true">
      <header><h2>${esc(title)}</h2><button class="btn ghost icon sm" data-close title="Close">${icon('x')}</button></header>
      <div class="body"></div><footer></footer></div></div>`);
    const m = back.querySelector('.modal');
    const bodyEl = m.querySelector('.body');
    if (typeof body === 'string') bodyEl.innerHTML = body;
    else bodyEl.appendChild(body);
    const footer = m.querySelector('footer');
    const close = (v) => {
      document.removeEventListener('keydown', onKey, true);
      back.remove();
      resolve(v);
    };
    const attempt = async (v) => {
      if (v !== null && v !== false && validate) {
        const ok = await validate(v, m);
        if (ok === false) return;
      }
      close(v);
    };
    buttons.forEach((b) => {
      const btn = h(`<button class="btn ${b.cls || ''}">${esc(b.label)}</button>`);
      btn.onclick = () => attempt(b.value);
      footer.appendChild(btn);
    });
    const onKey = (e) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        close(null);
      } else if (e.key === 'Enter' && !e.shiftKey && e.target.tagName !== 'TEXTAREA' && e.target.tagName !== 'BUTTON') {
        const primary = buttons.find((b) => (b.cls || '').includes('primary'));
        if (primary) {
          e.preventDefault();
          attempt(primary.value);
        }
      }
    };
    document.addEventListener('keydown', onKey, true);
    back.addEventListener('mousedown', (e) => {
      if (e.target === back) close(null);
    });
    m.querySelector('[data-close]').onclick = () => close(null);
    document.body.appendChild(back);
    modalGrip(m, title);
    if (onOpen) onOpen(m, close);
    const first = m.querySelector('input:not([type=checkbox]):not([type=radio]), select, textarea');
    if (first) {
      first.focus();
      if (first.select) first.select();
    } else footer.lastElementChild?.focus();
  });
}

// Resizable modals: drag the bottom-right corner; the size is kept per dialog title as a fraction of the window,
// double-click on the corner resets it. The modal is centred horizontally, so its width grows by twice the drag.
function modalGrip(m, title) {
  const key = 'modalSize';
  const all = () => { try { return store(key) || {}; } catch { return {}; } };
  const apply = (w, h) => {
    m.classList.add('sized');
    m.style.maxWidth = 'calc(100vw - 32px)';
    m.style.width = Math.round(Math.max(280, Math.min(window.innerWidth - 32, w))) + 'px';
    m.style.height = Math.round(Math.max(160, Math.min(window.innerHeight - 32, h))) + 'px';
  };
  const f = all()[title];
  if (f && f.w && f.h) apply(f.w * window.innerWidth, f.h * window.innerHeight);
  const g = h('<div class="modal-grip" title="Drag to resize; double-click resets"></div>');
  m.appendChild(g);
  g.addEventListener('dblclick', () => {
    m.classList.remove('sized');
    for (const k of ['width', 'height', 'maxWidth']) m.style[k] = '';
    const s = all(); delete s[title]; store(key, s);
  });
  g.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    g.setPointerCapture(e.pointerId);
    const r = m.getBoundingClientRect(), x0 = e.clientX, y0 = e.clientY;
    document.body.classList.add('resizing', 'diag');
    const move = (ev) => apply(r.width + 2 * (ev.clientX - x0), r.height + (ev.clientY - y0));
    const up = () => {
      document.body.classList.remove('resizing', 'diag');
      g.removeEventListener('pointermove', move);
      g.removeEventListener('pointerup', up);
      const b = m.getBoundingClientRect(), s = all();
      s[title] = { w: b.width / window.innerWidth, h: b.height / window.innerHeight };
      store(key, s);
    };
    g.addEventListener('pointermove', move);
    g.addEventListener('pointerup', up);
  });
}

export async function prompt(title, label, value = '', { okLabel = 'OK', hint = '', selectBase = false } = {}) {
  let input;
  const res = await modal({
    title,
    body: `<label class="field"><span>${esc(label)}</span><input class="input" value="${esc(value)}" spellcheck="false"></label>${hint ? `<div class="hint">${esc(hint)}</div>` : ''}`,
    buttons: [
      { label: 'Cancel', value: null },
      { label: okLabel, value: 'ok', cls: 'primary' },
    ],
    onOpen: (m) => {
      input = m.querySelector('input');
      if (selectBase) {
        setTimeout(() => {
          const dot = value.lastIndexOf('.');
          const slash = value.lastIndexOf('/');
          input.setSelectionRange(slash + 1, dot > slash ? dot : value.length);
        });
      }
    },
  });
  return res ? input.value.trim() : null;
}

export function confirmBox(title, message, { okLabel = 'OK', danger = false } = {}) {
  return modal({
    title,
    body: `<p style="margin:0">${message}</p>`,
    buttons: [
      { label: 'Cancel', value: false },
      { label: okLabel, value: true, cls: danger ? 'danger solid' : 'primary' },
    ],
  }).then((v) => !!v);
}

// ---------------------------------------------------------------- context menu
let openMenu = null;
export function contextMenu(x, y, items) {
  closeMenu();
  const m = h('<div class="ctx-menu" role="menu"></div>');
  for (const it of items) {
    if (it === '-') {
      m.appendChild(document.createElement('hr'));
      continue;
    }
    if (!it) continue;
    const b = h(`<button class="${it.danger ? 'danger' : ''}" role="menuitem">${it.icon ? icon(it.icon) : ''}<span>${esc(it.label)}</span></button>`);
    b.onclick = () => {
      closeMenu();
      it.action();
    };
    m.appendChild(b);
  }
  document.body.appendChild(m);
  const r = m.getBoundingClientRect();
  m.style.left = Math.min(x, window.innerWidth - r.width - 8) + 'px';
  m.style.top = Math.min(y, window.innerHeight - r.height - 8) + 'px';
  openMenu = m;
  setTimeout(() => {
    document.addEventListener('mousedown', onDocDown, true);
    document.addEventListener('keydown', onDocKey, true);
  });
}
function onDocDown(e) {
  if (openMenu && !openMenu.contains(e.target)) closeMenu();
}
function onDocKey(e) {
  if (e.key === 'Escape') closeMenu();
}
export function closeMenu() {
  if (openMenu) openMenu.remove();
  openMenu = null;
  document.removeEventListener('mousedown', onDocDown, true);
  document.removeEventListener('keydown', onDocKey, true);
}

export function relTime(iso) {
  const d = new Date(iso);
  const s = (Date.now() - d.getTime()) / 1000;
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  if (s < 86400 * 7) return `${Math.floor(s / 86400)} d ago`;
  return d.toLocaleDateString();
}

export function fmtSize(n) {
  if (n < 1024) return n + ' B';
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
  return (n / 1024 / 1024).toFixed(1) + ' MB';
}
