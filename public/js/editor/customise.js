// Editing window for one piece of a Folio Lab result: a figure (the module redraws it with a style: journal preset,
// size, font, every drawn element, frame colours, axes and zoom, legend, title, crop), a table (columns, decimals) or a
// text block, plus the caption and, for figures, where the float sits in the document.
// Saving makes a variant ("fork") of the original, stored as its own result in lab/<slug>/: live (follows the
// original on Refresh) or a snapshot (frozen). The original stays untouched.
import { api, fileUrl, esc, h, icon, modal, toast } from '../ui.js';
import { PLACE_POS, PLACE_ALIGN, cleanPlace, zoomFromBox } from './labuses.mjs';
import { GROUPS, buildSpec, stateFrom, effective, rangeKeys, labelTargets, countMatches, replaceAll, dashFor, plainText, partRows, setPart } from './cusedit.mjs';

const PRESETS = [
  ['standard', 'Module default'],
  ['elsevier-1', 'Elsevier, single column (90 mm)'],
  ['elsevier-2', 'Elsevier, double column (190 mm)'],
  ['springer-1', 'Springer, single column (84 mm)'],
  ['springer-2', 'Springer, double column (174 mm)'],
  ['ieee-1', 'IEEE, single column (88 mm)'],
  ['ieee-2', 'IEEE, double column (181 mm)'],
  ['acs-1', 'ACS, single column (82.5 mm)'],
  ['nature-1', 'Nature, single column (89 mm)'],
  ['nature-2', 'Nature, double column (183 mm)'],
  ['thesis', 'Thesis (150 mm, 10 pt)'],
  ['slides', 'Slides (large)'],
];
const PALETTES = [
  ['', 'Module colours'],
  ['okabe-ito', 'Okabe–Ito (colour-blind safe)'],
  ['tol-bright', 'Tol bright (colour-blind safe)'],
  ['grey', 'Greys (print)'],
];
const FONTS = [['', 'as preset'], ['sans', 'Sans serif (DejaVu Sans)'], ['serif', 'Serif (DejaVu Serif)'], ['cm', 'Computer Modern (as LaTeX)']];
const LINESTYLES = [['', '—'], ['-', 'solid'], ['--', 'dashed'], [':', 'dotted'], ['-.', 'dash-dot']];
const LOCS = ['best', 'upper right', 'upper left', 'lower left', 'lower right', 'center right', 'outside'];
const FRAME_COLORS = [['background', 'Background'], ['plot', 'Plot area'], ['axes', 'Axis lines'], ['ticks', 'Ticks'], ['grid', 'Grid'], ['text', 'Labels and titles']];
const KIND = { line: 'Line', lines: 'Lines', markers: 'Markers', area: 'Area', bars: 'Bars', label: 'Value label', text: 'Text', collection: 'Shapes' };
const LINEISH = new Set(['line', 'lines', 'area', 'bars', 'markers', 'collection']);

const plain = (s) => String(s || '').replace(/~?\\cite\{[^}]*\}/g, '').replace(/\\textdegree(\{\})?/g, '°').replace(/\\[,;:! ]/g, ' ').replace(/\\[a-zA-Z]+\{([^}]*)\}/g, '$1').replace(/[{}$\\~]/g, '').replace(/\s+/g, ' ').trim();
const num = (v) => (v === '' || v === null || v === undefined || Number.isNaN(+v) ? undefined : +v);
const sig = (v) => +(+v).toPrecision(4);

/** Header cells of the first tabular row (for the column ticks of a table). */
export function tableColumns(tex) {
  const m = String(tex || '').match(/\\begin\{tabular\}\{((?:[^{}]|\{[^{}]*\})*)\}([\s\S]*?)\\end\{tabular\}/);
  if (!m) return [];
  const body = m[2].replace(/\\(toprule|midrule|bottomrule|hline|addlinespace)\b(\[[^\]]*\])?/g, '').replace(/\\cmidrule(\([^)]*\))?\{[^}]*\}/g, '');
  const first = body.split(/\\\\/).find((r) => r.trim());
  if (!first) return [];
  const cells = [];
  let depth = 0;
  let cur = '';
  for (let i = 0; i < first.length; i++) {
    const c = first[i];
    if (c === '\\' && i + 1 < first.length) { cur += c + first[i + 1]; i++; continue; }
    if (c === '{') depth++;
    else if (c === '}') depth = Math.max(0, depth - 1);
    if (c === '&' && depth === 0) { cells.push(cur); cur = ''; continue; }
    cur += c;
  }
  cells.push(cur);
  return cells.map((c) => plain(c.replace(/\\multicolumn\{\d+\}\{[^}]*\}/g, '')) || '(empty)');
}

/** The SVG of a preview, safe to put in the page: no scripts, event handlers, outside links or style sheets (the
 *  figure's own sheet would style the whole page). Null when it is not an SVG. */
function cleanSvg(text) {
  const doc = new DOMParser().parseFromString(String(text || ''), 'image/svg+xml');
  const svg = doc.documentElement;
  if (!svg || svg.nodeName.toLowerCase() !== 'svg' || doc.querySelector('parsererror')) return null;
  svg.querySelectorAll('script, foreignObject, style, iframe, a').forEach((n) => n.remove());
  for (const n of [svg, ...svg.querySelectorAll('*')]) {
    for (const a of [...n.attributes]) {
      const nm = a.name.toLowerCase();
      if (nm.startsWith('on')) n.removeAttribute(a.name);
      else if ((nm === 'href' || nm === 'xlink:href') && !/^#|^data:image\/(png|jpeg);base64,/i.test(a.value)) n.removeAttribute(a.name);
    }
  }
  // the module's fonts (DejaVu, Computer Modern) are rarely installed in the browser: fall back to look-alikes
  for (const t of svg.querySelectorAll('text')) {
    const ff = t.style.fontFamily;
    if (ff && !/serif|monospace/i.test(ff.replace(/DejaVu Serif|DejaVu Sans/gi, ''))) {
      t.style.fontFamily = /serif|cmr|cmmi|stix|times/i.test(ff) && !/sans/i.test(ff) ? `${ff}, 'Times New Roman', serif` : `${ff}, Verdana, 'Segoe UI', sans-serif`;
    }
  }
  const vb = (svg.getAttribute('viewBox') || '').split(/[\s,]+/).map(Number);
  svg.removeAttribute('width');
  svg.removeAttribute('height');
  svg.setAttribute('class', 'cus-svg');
  const out = document.importNode(svg, true);
  // the glow of selected elements (a CSS filter function does not apply to parts of an SVG everywhere)
  const NS = 'http://www.w3.org/2000/svg';
  const mk = (tag, attrs) => Object.entries(attrs).reduce((n, [k, v]) => (n.setAttribute(k, v), n), document.createElementNS(NS, tag));
  const filter = mk('filter', { id: 'cus-glow', x: '-20%', y: '-20%', width: '140%', height: '140%' });
  filter.append(mk('feDropShadow', { dx: 0, dy: 0, stdDeviation: 1.4, 'flood-color': '#1a73e8', 'flood-opacity': 0.9 }));
  const defs = mk('defs', {});
  defs.append(filter);
  out.prepend(defs);
  out.dataset.w = vb[2] || 400;
  out.dataset.h = vb[3] || 300;
  return out;
}


/**
 * Open the editing window for piece `item` of result `slug` (an original or one of its variants).
 * Resolves to {slug, item, bundle} of the saved variant, or null when cancelled.
 */
export async function openCustomise({ projectId, slug, item, reloadFromDisk }) {
  const base = `/api/projects/${projectId}/lab`;
  const all = await api('GET', base);
  const man = all.find((b) => b.slug === slug);
  if (!man) throw new Error(`No result “${slug}” in this report`);
  const isFork = !!man.fork;
  const origSlug = isFork ? man.fork.of : slug;
  const orig = all.find((b) => b.slug === origSlug) || man;
  const itemId = item || (man.fork && man.fork.item);
  const it = (orig.items || []).find((i) => i.id === itemId && ['figure', 'table', 'text'].includes(i.kind));
  if (!it) throw new Error('Choose a figure, table or text block of this result');
  const kind = it.kind;
  const prev = isFork ? man.fork : null;
  const canStyle = kind === 'figure' && orig.source && orig.module !== 'import';

  const st = stateFrom(prev ? prev.style : {});
  const place = { width: '', pos: '', align: '', ...((prev && prev.place) || {}) };
  // the caption follows what the figure shows (the module writes it from the shown parts) until the user edits it;
  // only an edited caption is stored with the variant
  const forkIt = isFork ? (man.items || []).find((i) => i.id === itemId) : null;
  let capAuto = (forkIt || it).caption || '';
  const ownCap = prev && prev.caption !== undefined && prev.caption !== it.caption && prev.caption !== it.caption_full && prev.caption !== capAuto;
  let caption = ownCap ? prev.caption : capAuto;
  let text = prev && prev.text !== undefined ? prev.text : null;
  const table = { hide: new Set(prev && prev.table ? prev.table.hide || [] : []), digits: prev && prev.table && prev.table.digits !== null && prev.table.digits !== undefined ? prev.table.digits : '' };
  let mode = prev ? prev.mode : 'live';
  let describe = null; // the figure as the module draws it (element keys, axes) before any style
  let nowAxes = []; // per axes where it sits in the shown image, with its limits (drag to zoom)
  let cropMode = false;
  let gidKey = {}; // SVG id of the shown preview -> element key ("@xlabel0" for axis labels)
  let gids = {}; // element key -> SVG ids
  const sel = new Set(); // selected element keys (click, Ctrl adds, Shift a range)
  let anchor = null;
  const find = { q: '', r: '', cs: false };
  let undoReplace = null;

  const body = h(`<div class="cus">
    <div class="cus-view"><div class="cus-pv"></div><div class="hint cus-state"></div></div>
    <div class="cus-form"></div>
  </div>`);
  const pv = body.querySelector('.cus-pv');
  const stateEl = body.querySelector('.cus-state');
  const form = body.querySelector('.cus-form');

  // ------------------------------------------------------------ preview with zoom box, crop handles and selection
  /** Show a preview answer: the SVG (changes show at once, elements can be clicked) or else the PNG. */
  function showResult(r) {
    const now = (r.describe && r.describe.now) || {};
    nowAxes = now.axes || [];
    gids = now.gids || {};
    gidKey = {};
    for (const [k, ids] of Object.entries(gids)) for (const id of ids) gidKey[id] = k;
    const svg = r.svg ? cleanSvg(r.svg) : null;
    if (svg) {
      // the full width of the pane, but no higher than 60 % of the window (no letterbox: the drag maps to the box)
      svg.style.width = `min(100%, ${((60 * svg.dataset.w) / svg.dataset.h).toFixed(1)}vh)`;
      mountStage(svg);
      liveApply();
    } else if (r.png) {
      const img = new Image();
      img.alt = '';
      img.draggable = false;
      img.src = `data:image/png;base64,${r.png}`;
      mountStage(img);
    } else pv.innerHTML = '<div class="hint">No preview image.</div>';
  }
  function mountStage(pic) {
    const stage = h(`<div class="cus-stage${canStyle ? ' can-drag' : ''}${cropMode ? ' cropping' : ''}${pic.tagName === 'IMG' ? '' : ' is-svg'}"><div class="cus-box" hidden></div>${cropMode ? '<div class="cus-crop"><i data-h="w"></i><i data-h="e"></i><i data-h="n"></i><i data-h="s"></i></div>' : ''}</div>`);
    stage.prepend(pic);
    pv.replaceChildren(stage);
    if (canStyle) wireStage(stage, pic);
  }

  /** Change the shown SVG to the form state at once (colour, visibility, width, line style, opacity, size, weight,
   *  plain texts); the module's exact redraw follows. Every change starts from the SVG as it came. */
  function liveApply() {
    const svg = pv.querySelector('svg.cus-svg');
    if (!svg) return;
    svg.querySelectorAll('[data-o]').forEach((n) => (n.dataset.o ? n.setAttribute('style', n.dataset.o) : n.removeAttribute('style')));
    svg.querySelectorAll('[data-ot]').forEach((n) => (n.textContent = n.dataset.ot));
    svg.querySelectorAll('.cus-off, .cus-hl').forEach((n) => n.classList.remove('cus-off', 'cus-hl'));
    const touch = (n) => {
      if (n.dataset.o === undefined) n.dataset.o = n.getAttribute('style') || '';
      return n.style;
    };
    const setText = (g, raw, text) => {
      if (!plainText(text) || !plainText(raw)) return;
      const ts = [...g.querySelectorAll('text')];
      const lines = text.split('\n');
      if (!ts.length || (ts.length !== lines.length && ts.length !== 1)) return;
      ts.forEach((t, k) => {
        if (t.dataset.ot === undefined) t.dataset.ot = t.textContent;
        t.textContent = ts.length === 1 ? text : lines[k];
      });
    };
    const style = (g, d) => {
      if (d.hidden) {
        g.classList.add('cus-off');
        return;
      }
      if (d.alpha !== undefined) touch(g).opacity = d.alpha;
      for (const n of g.querySelectorAll('path, use, rect, circle, ellipse, polygon, polyline, line')) {
        const s = touch(n);
        if (d.color) {
          if (s.stroke && s.stroke !== 'none') s.stroke = d.color;
          if (s.fill && s.fill !== 'none') s.fill = d.color;
        }
        if (n.tagName === 'path' && !n.closest('defs') && s.stroke && s.stroke !== 'none') {
          if (d.lw !== undefined) s.strokeWidth = d.lw;
          if (d.ls) s.strokeDasharray = dashFor(d.ls, d.lw ?? (parseFloat(s.strokeWidth) || 1.5));
        }
      }
      for (const t of g.querySelectorAll('text')) {
        const s = touch(t);
        if (d.color) s.fill = d.color;
        if (d.size !== undefined) s.fontSize = `${d.size}px`;
        if (d.bold !== undefined) s.fontWeight = d.bold ? '700' : '400';
      }
    };
    const byId = (id) => svg.querySelector(`[id="${CSS.escape(id)}"]`);
    for (const e of (describe && describe.elements) || []) {
      const d = effective(st, e);
      for (const id of gids[e.key] || []) {
        const g = byId(id);
        if (!g) continue;
        style(g, d);
        if (d.text !== undefined) setText(g, e.raw, d.text);
      }
    }
    const al = st.groups.axis_labels || {};
    ((describe && describe.axes) || []).forEach((a, i) => {
      for (const k of ['xlabel', 'ylabel']) {
        const g = byId(`cax${i}${k[0]}`);
        if (!g) continue;
        style(g, al);
        const t = (st.axes[i] || {})[k];
        if (t) setText(g, a[k], t);
      }
    });
    for (const k of sel) for (const id of gids[k] || []) byId(id)?.classList.add('cus-hl');
  }

  function wireStage(stage, img) {
    const box = stage.querySelector('.cus-box');
    const crop = stage.querySelector('.cus-crop');
    const ready = () => img.tagName !== 'IMG' || img.complete;
    const frac = (e) => {
      const r = img.getBoundingClientRect();
      return [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))];
    };
    const place2 = (el, x0, y0, x1, y1) => {
      const r = img.getBoundingClientRect();
      const s = stage.getBoundingClientRect();
      el.style.left = `${r.left - s.left + Math.min(x0, x1) * r.width}px`;
      el.style.top = `${r.top - s.top + Math.min(y0, y1) * r.height}px`;
      el.style.width = `${Math.abs(x1 - x0) * r.width}px`;
      el.style.height = `${Math.abs(y1 - y0) * r.height}px`;
    };
    const cropRect = () => { const c = st.crop || [0, 0, 0, 0]; return [c[0], c[1], 1 - c[2], 1 - c[3]]; };
    const showCrop = () => { if (crop) { const [a, b, c, d] = cropRect(); place2(crop, a, b, c, d); } };
    if (crop) (ready() ? showCrop() : img.addEventListener('load', showCrop));
    const setCrop = (x0, y0, x1, y1) => {
      const l = Math.min(x0, x1), r = Math.max(x0, x1), t = Math.min(y0, y1), b = Math.max(y0, y1);
      const cl = (v) => Math.min(0.45, Math.max(0, v));
      st.crop = [cl(l), cl(t), cl(1 - r), cl(1 - b)];
      showCrop();
      syncCropInputs();
    };
    stage.onpointerdown = (e) => {
      if (e.button !== 0 || !ready()) return;
      e.preventDefault();
      const handle = e.target.dataset && e.target.dataset.h;
      const hit = e.target.closest && e.target.closest('[id^="cel"], [id^="cax"]');
      const mods = { ctrl: e.ctrlKey || e.metaKey, shift: e.shiftKey };
      const [sx, sy] = frac(e);
      const r0 = cropRect();
      stage.setPointerCapture(e.pointerId);
      stage.onpointermove = (m) => {
        const [x, y] = frac(m);
        if (cropMode && handle) {
          const r = [...r0];
          if (handle === 'w') r[0] = x;
          if (handle === 'e') r[2] = x;
          if (handle === 'n') r[1] = y;
          if (handle === 's') r[3] = y;
          setCrop(...r);
        } else if (cropMode) setCrop(sx, sy, x, y);
        else {
          box.hidden = false;
          place2(box, sx, sy, x, y);
        }
      };
      stage.onpointerup = (u) => {
        stage.onpointermove = stage.onpointerup = null;
        box.hidden = true;
        if (cropMode) return;
        const [x, y] = frac(u);
        if (Math.abs(x - sx) < 0.015 && Math.abs(y - sy) < 0.015) {
          clickPreview(hit, mods);        // a click, not a box: select what is under the pointer
          return;
        }
        if (Math.abs(x - sx) < 0.015 || Math.abs(y - sy) < 0.015) return;
        const z = zoomFromBox(nowAxes, sx, sy, x, y);
        if (!z.length) {
          toast('Start the box inside a plot', 'info', 3000);
          return;
        }
        for (const { i, ...lim } of z) {
          while (st.axes.length <= i) st.axes.push({});
          Object.assign(st.axes[i], lim);
        }
        render();
        runPreview();
      };
    };
  }

  /** Select an element: alone, Ctrl adds or removes it, Shift adds the range from the last one clicked. */
  function select(key, { ctrl = false, shift = false } = {}) {
    const order = ((describe && describe.elements) || []).map((e) => e.key);
    if (shift && anchor) rangeKeys(order, anchor, key).forEach((k) => sel.add(k));
    else if (ctrl) {
      if (sel.has(key)) sel.delete(key);
      else sel.add(key);
      anchor = key;
    } else {
      const only = sel.size === 1 && sel.has(key);
      sel.clear();
      if (!only) sel.add(key);
      anchor = key;
    }
  }
  function clickPreview(hit, mods) {
    const key = hit && gidKey[hit.id];
    if (!key) {
      if (sel.size && !mods.ctrl && !mods.shift) {
        sel.clear();
        render();
        liveApply();
      }
      return;
    }
    const ax = key.match(/^@([xy])label(\d+)$/);
    const sec = ax ? 'axes' : 'elements';
    if (!ax) select(key, mods);
    render();
    const d = form.querySelector(`details[data-sec="${sec}"]`);
    if (d) d.open = true;
    const target = ax ? form.querySelector(`[data-ax="${ax[2]}"] [data-k="${ax[1]}label"]`) : form.querySelector(`[data-el="${CSS.escape(key)}"]`);
    if (target) {
      target.closest('details.cus-elgrp')?.setAttribute('open', '');
      target.scrollIntoView({ block: 'nearest' });
      if (ax) target.focus();
    }
    liveApply();
  }

  // the module's exact redraw: after a short pause in typing, the one before cancelled, the same spec answered from a
  // cache; the shown SVG already follows every change (liveApply)
  let seq = 0;
  let timer = null;
  let ctrl = null;
  const cache = new Map();
  async function runPreview() {
    if (kind !== 'figure') return;
    clearTimeout(timer);
    const my = ++seq;
    const style = canStyle ? buildSpec(st, { noCrop: cropMode }) : {};
    const key = JSON.stringify(style);
    if (ctrl) ctrl.abort();
    ctrl = null;
    let r = cache.get(key);
    if (!r) {
      ctrl = new AbortController();
      stateEl.innerHTML = `${icon('loader')} The module redraws the figure…`;
      try {
        r = await api('POST', `${base}/${slug}/preview`, { item: itemId, style }, { signal: ctrl.signal });
      } catch (e) {
        if (my === seq) stateEl.textContent = e.message;
        return;
      }
      if (my !== seq) return;
      ctrl = null;
      cache.delete(key);
      cache.set(key, r);
      if (cache.size > 24) cache.delete(cache.keys().next().value);
    }
    if (!describe) describe = r.describe;
    if (typeof r.caption === 'string' && caption === capAuto && r.caption !== capAuto) {
      capAuto = caption = r.caption;        // a hidden part leaves the caption (and its sources) with it
      const cap = form.querySelector('[data-cap]');
      if (cap) cap.value = caption;
    }
    showResult(r);
    const now = (r.describe && r.describe.now) || {};
    const d = now.width_mm ? now : (r.describe || {});
    const notes = (now.notes || []).join(' ');
    stateEl.textContent = [d.width_mm ? `${d.width_mm} mm wide · height ${Math.round(d.width_mm * d.aspect)} mm` : '', cropMode ? 'drag the edges or a new box to crop' : canStyle ? 'drag a box on the plot to zoom, click an element to select it' : '', notes].filter(Boolean).join(' · ');
  }
  const schedule = () => {
    liveApply();
    clearTimeout(timer);
    timer = setTimeout(runPreview, 450);
  };

  async function tablePreview() {
    const r = await api('GET', fileUrl(projectId, `lab/${origSlug}/${it.file}`), undefined, { raw: true });
    return r.text();
  }

  // ------------------------------------------------------------ form
  const opt = (list, sel) => list.map(([v, l]) => `<option value="${esc(v)}" ${String(v) === String(sel) ? 'selected' : ''}>${esc(l)}</option>`).join('');
  function fontOptions() {
    const fonts = (describe && describe.fonts) || [];
    const extra = st.font && !FONTS.some(([v]) => v === st.font) && !fonts.includes(st.font) ? [st.font] : [];
    return `${opt(FONTS, st.font)}${fonts.length || extra.length ? `<optgroup label="Installed fonts">${opt([...extra, ...fonts].map((f) => [f, f]), st.font)}</optgroup>` : ''}`;
  }
  function seriesRows() {
    // older variants styled series by legend name; keep editing them
    const list = Object.keys(st.series).map((label) => ({ label }));
    if (!list.length) return '';
    return `<div class="hint">Series settings of this variant (by legend name)</div>${list.map((s) => {
      const d = st.series[s.label] || {};
      return `<div class="cus-ser" data-ser="${esc(s.label)}">
        <input type="color" value="${esc(d.color || '#000000')}" data-k="color" title="Colour">
        <input class="input sm cus-el-name" data-k="label" value="${esc(d.label ?? '')}" placeholder="${esc(s.label)}" title="Name in the legend">
        <select class="input sm" data-k="ls" title="Line style">${opt(LINESTYLES, d.ls || '')}</select>
        <label class="hint" title="Leave this series out"><input type="checkbox" data-k="hidden" ${d.hidden ? 'checked' : ''}> hide</label></div>`;
    }).join('')}`;
  }
  function elementRow(e) {
    const d = st.elements[e.key] || {};
    const isText = e.kind === 'text' || e.kind === 'label';
    const lines = String(d.text || e.raw || '').includes('\n');   // a one-line field would drop the line break
    const name = isText
      ? lines
        ? `<textarea class="input sm cus-el-name" rows="2" data-k="text" placeholder="${esc(e.raw || e.text)}" title="Text">${esc(d.text ?? '')}</textarea>`
        : `<input class="input sm cus-el-name" data-k="text" value="${esc(d.text ?? '')}" placeholder="${esc(e.text)}" title="Text">`
      : e.named
        ? `<input class="input sm cus-el-name" data-k="label" value="${esc(d.label ?? '')}" placeholder="${esc(e.text)}" title="Name in the legend">`
        : `<span class="cus-el-name" title="${esc(e.key)}">${esc(e.text)}</span>`;
    const ctl = [
      e.kind === 'line' || e.kind === 'lines' ? `<select class="input sm" data-k="ls" title="Line style">${opt(LINESTYLES, d.ls || '')}</select>` : '',
      LINEISH.has(e.kind) && e.kind !== 'markers' ? `<input class="input sm num" data-k="lw" value="${esc(d.lw ?? '')}" placeholder="width" title="Line width (pt)">` : '',
      isText || e.kind === 'markers' || e.kind === 'line' ? `<input class="input sm num" data-k="size" value="${esc(d.size ?? '')}" placeholder="${isText ? 'pt' : 'mark'}" title="${isText ? 'Font size (pt)' : 'Marker size'}">` : '',
    ].join('');
    const changed = Object.keys(d).length;
    const eff = effective(st, e);
    const gc = (st.groups[e.group] || {}).color;
    return `<div class="cus-el${eff.hidden ? ' off' : ''}${sel.has(e.key) ? ' sel' : ''}" data-el="${esc(e.key)}" title="Click to select; Ctrl adds, Shift selects a range">
      <input type="checkbox" data-k="show" ${eff.hidden ? '' : 'checked'} title="Show">
      <input type="color" value="${esc(d.color || gc || e.color || '#000000')}" data-k="color" title="Colour">
      <span class="cus-el-kind">${esc(KIND[e.kind] || e.kind)}</span>${name}<span class="cus-el-ctl">${ctl}</span>
      <button class="btn xs ghost" data-k="reset" title="As the module draws it" ${changed ? '' : 'hidden'}>${icon('x')}</button></div>`;
  }
  /** One row per kind of element: a change applies to all of them; an element's own setting still wins. */
  function groupRows() {
    const counts = (describe && describe.groups) || {};
    const els = (describe && describe.elements) || [];
    const textCol = (describe && describe.colors && describe.colors.text) || '#000000';
    const list = GROUPS.filter(([g]) => counts[g]);
    if (!list.length) return '';
    return `<div class="hint">All of a kind: one change for every one of them.</div><div class="cus-els cus-grps">${list.map(([g, label, props]) => {
      const d = st.groups[g] || {};
      const rep = d.color || (els.find((e) => e.group === g && e.color) || {}).color || textCol;
      const ctl = [
        props.includes('size') ? `<input class="input sm num" data-k="size" value="${esc(d.size ?? '')}" placeholder="${g === 'markers' ? 'mark' : 'pt'}" title="${g === 'markers' ? 'Marker size' : 'Font size (pt)'}">` : '',
        props.includes('lw') ? `<input class="input sm num" data-k="lw" value="${esc(d.lw ?? '')}" placeholder="width" title="Line width (pt)">` : '',
        props.includes('ls') ? `<select class="input sm" data-k="ls" title="Line style">${opt(LINESTYLES, d.ls || '')}</select>` : '',
        props.includes('alpha') ? `<input class="input sm num" data-k="alpha" value="${esc(d.alpha ?? '')}" placeholder="opacity" title="Opacity, 0 to 1">` : '',
        props.includes('bold') ? `<select class="input sm" data-k="bold" title="Weight">${opt([['', 'weight'], ['1', 'bold'], ['0', 'normal']], d.bold === undefined ? '' : d.bold ? '1' : '0')}</select>` : '',
      ].join('');
      return `<div class="cus-el cus-grp${d.hidden ? ' off' : ''}" data-grp="${g}">
        ${props.includes('hidden') ? `<input type="checkbox" data-k="show" ${d.hidden ? '' : 'checked'} title="Show all">` : '<span class="cus-nochk"></span>'}
        <input type="color" value="${esc(rep)}" data-k="color" title="Colour of all">
        <span class="cus-el-name"><b>${esc(label)}</b> <span class="hint">${counts[g]}</span></span><span class="cus-el-ctl">${ctl}</span>
        <button class="btn xs ghost" data-k="reset" title="As the module draws them" ${Object.keys(d).length ? '' : 'hidden'}>${icon('x')}</button></div>`;
    }).join('')}</div>`;
  }
  /** What can be done to all selected elements at once. */
  function selBar() {
    if (!sel.size) return '<div class="hint cus-selhint">Click rows or elements in the preview to select them; Ctrl adds one, Shift a range.</div>';
    return `<div class="cus-selbar"><b>${sel.size} selected</b>
      <button class="btn xs" data-sa="show">Show</button><button class="btn xs" data-sa="hide">Hide</button>
      <input type="color" data-sa="color" title="Colour of the selected">
      <input class="input sm num" data-sa="lw" placeholder="width" title="Line width (pt)">
      <select class="input sm" data-sa="ls" title="Line style">${opt(LINESTYLES, '')}</select>
      <input class="input sm num" data-sa="size" placeholder="size" title="Font or marker size">
      <input class="input sm num" data-sa="alpha" placeholder="opacity" title="Opacity, 0 to 1">
      <button class="btn xs ghost" data-sa="reset" title="As the module draws them">As drawn</button>
      <button class="btn xs ghost" data-sa="none">Clear selection</button></div>`;
  }
  function findRows() {
    const c = countMatches(labelTargets(describe, st), find.q, find.cs);
    return `<div class="cus-find">
      <input class="input sm" data-f="q" value="${esc(find.q)}" placeholder="Find">
      <input class="input sm" data-f="r" value="${esc(find.r)}" placeholder="Replace with">
      <label class="hint"><input type="checkbox" data-f="cs" ${find.cs ? 'checked' : ''}> match case</label></div>
      <div class="row"><span class="hint" data-f="count">${find.q ? `${c.matches} match${c.matches === 1 ? '' : 'es'} in ${c.labels} label${c.labels === 1 ? '' : 's'}` : ''}</span>
      <button class="btn sm" data-act="replace" ${c.matches ? '' : 'disabled'}>Replace all</button>
      <button class="btn sm ghost" data-act="unreplace" ${undoReplace ? '' : 'hidden'}>Undo replace</button></div>
      <div class="hint">Searches texts in the plot, legend names, axis labels and the title, LaTeX as written.</div>`;
  }
  /** The parts the module says the figure shows (envelope, reference curve, field …): switching one off hides its
   *  elements and drops its words and sources from the caption and its sentences from the methods text. */
  function partsBlock() {
    const rows = partRows(it, st, describe);
    if (!rows.length) return '';
    const on = rows.filter((r) => r.shown).length;
    return `<details data-sec="parts"><summary>What the figure shows <span class="hint">${on} of ${rows.length}</span></summary>
      <div class="cus-parts">${rows.map((r) => `<label class="imp-step ${r.shown ? 'on' : ''}" title="${esc(r.cites.length ? `Cites ${r.cites.join(', ')}` : 'No own sources')}"><input type="checkbox" data-part="${esc(r.id)}" ${r.shown ? 'checked' : ''}><span>${esc(r.label)}</span>${r.cites.length ? `<i class="hint">${r.cites.length} source${r.cites.length === 1 ? '' : 's'}</i>` : ''}</label>`).join('')}</div>
      <div class="hint">Off: the part is not drawn, the caption no longer names it, and its sources and methods sentences leave the report.</div></details>`;
  }
  function elementRows() {
    const els = (describe && describe.elements) || [];
    if (!els.length) return `<div class="hint">${describe ? 'Nothing drawn that can be styled one by one.' : 'The elements appear after the first preview.'}</div>`;
    const groups = new Map();
    for (const e of els) {
      const g = e.ax === null || e.ax === undefined ? 'f' : e.ax;
      if (!groups.has(g)) groups.set(g, []);
      groups.get(g).push(e);
    }
    const multi = groups.size > 1;
    return [...groups.entries()].map(([g, list]) => {
      const rows = list.map(elementRow).join('');
      if (!multi) return rows;
      const hidden = list.filter((e) => effective(st, e).hidden).length;
      return `<details class="cus-elgrp" data-sec="el-${g}"><summary>${g === 'f' ? 'Figure texts' : `Plot ${+g + 1}`} <span class="hint">${list.length} element${list.length === 1 ? '' : 's'}${hidden ? `, ${hidden} hidden` : ''}</span></summary>${rows}</details>`;
    }).join('');
  }
  function colorRows() {
    const now = (describe && describe.colors) || {};
    return FRAME_COLORS.map(([k, l]) => `<label class="cus-col"><input type="color" data-fcol="${k}" value="${esc(st.colors[k] || now[k] || '#000000')}"> ${esc(l)}${st.colors[k] ? ' <span class="hint">changed</span>' : ''}</label>`).join('');
  }
  function axesRows() {
    const ax = ((describe && describe.axes) || []).map((a, i) => ({ a, i })).filter(({ a }) => Object.keys(a).length);
    if (!ax.length) return '<div class="hint">The axes appear after the first preview.</div>';
    return ax.map(({ a, i }) => {
      const s = st.axes[i] || {};
      const lim = (v) => (v === undefined || v === null ? '' : sig(v));
      return `<div class="cus-ax" data-ax="${i}">${ax.length > 1 ? `<div class="hint">Plot ${i + 1}</div>` : ''}
        <label>x label <input class="input sm" data-k="xlabel" value="${esc(s.xlabel || '')}" placeholder="${esc(plain(a.xlabel))}"></label>
        <label>y label <input class="input sm" data-k="ylabel" value="${esc(s.ylabel || '')}" placeholder="${esc(plain(a.ylabel))}"></label>
        <label>x from <input class="input sm num" data-k="xmin" value="${esc(s.xmin ?? '')}" placeholder="${lim(a.xlim && a.xlim[0])}"> to <input class="input sm num" data-k="xmax" value="${esc(s.xmax ?? '')}" placeholder="${lim(a.xlim && a.xlim[1])}"></label>
        <label>y from <input class="input sm num" data-k="ymin" value="${esc(s.ymin ?? '')}" placeholder="${lim(a.ylim && a.ylim[0])}"> to <input class="input sm num" data-k="ymax" value="${esc(s.ymax ?? '')}" placeholder="${lim(a.ylim && a.ylim[1])}"></label>
        <span class="cus-checks"><label><input type="checkbox" data-k="xlog" ${s.xlog ? 'checked' : ''}> x log</label>
        <label><input type="checkbox" data-k="ylog" ${s.ylog ? 'checked' : ''}> y log</label>
        <label><input type="checkbox" data-k="grid" ${s.grid === false ? '' : s.grid || (s.grid === undefined && a.grid) ? 'checked' : ''}> grid</label></span></div>`;
    }).join('');
  }
  const pct = (v) => Math.round((v || 0) * 1000) / 10;
  function cropRows() {
    const c = st.crop || [0, 0, 0, 0];
    return `<div class="cus-grid">${['left', 'top', 'right', 'bottom'].map((s, k) => `<label>Cut ${s} (%) <input class="input sm num" data-crop="${k}" value="${pct(c[k]) || ''}" placeholder="0"></label>`).join('')}</div>
      <div class="row"><button class="btn sm" data-act="crop">${cropMode ? 'Done cropping' : 'Crop on the preview'}</button>
      <button class="btn sm ghost" data-act="uncrop" ${st.crop ? '' : 'disabled'}>No crop</button></div>`;
  }
  function syncCropInputs() {
    const c = st.crop || [0, 0, 0, 0];
    form.querySelectorAll('[data-crop]').forEach((el) => (el.value = pct(c[+el.dataset.crop]) || ''));
  }
  function placeRows() {
    const w = place.width === 'full' ? 100 : place.width ? Math.round(place.width * 100) : Math.round((+it.width || 0.9) * 100);
    return `<div class="cus-grid">
      <label class="cus-span">Width <span class="row cus-plw"><input type="range" min="10" max="100" step="5" data-pl="width" value="${w}" ${place.width === 'full' ? 'disabled' : ''}> <span class="hint" data-plw>${place.width === 'full' ? 'page' : `${w} %${place.width ? '' : ' (as inserted)'}`}</span></span></label>
      <label class="cus-span cus-check"><input type="checkbox" data-pl="full" ${place.width === 'full' ? 'checked' : ''}> across both columns (figure*)</label>
      <label>Position <select class="input sm" data-pl="pos">${opt([['', 'as inserted (htbp)'], ...PLACE_POS], place.pos)}</select></label>
      <label>Alignment <select class="input sm" data-pl="align">${opt([['', 'as inserted (centred)'], ...PLACE_ALIGN], place.align)}</select></label></div>
      <div class="hint">Applied where this variant is in your text when you save, and used when you insert it. To change a figure already in the text, right-click it there and choose Customise.</div>`;
  }

  function render() {
    const open = new Set([...form.querySelectorAll('details[open]')].map((d) => d.dataset.sec));
    const capRow = kind === 'text' ? '' : `<label class="cus-cap">Caption <span class="hint">LaTeX; keep <code>\\cite{…}</code> for the sources</span>
      <textarea class="input" rows="3" data-cap>${esc(caption)}</textarea></label>`;
    let parts = '';
    if (kind === 'figure') {
      parts = canStyle ? `
        <label>Journal or layout <select class="input sm" data-st="preset">${opt(PRESETS, st.preset)}</select></label>
        ${partsBlock()}
        <details data-sec="size"><summary>Size and font</summary><div class="cus-grid">
          <label>Width (mm) <input class="input sm num" data-st="width_mm" value="${esc(st.width_mm)}" placeholder="${describe ? describe.width_mm : ''}"></label>
          <label>Height/width <input class="input sm num" data-st="aspect" value="${esc(st.aspect)}" placeholder="${describe ? describe.aspect : ''}"></label>
          <label>Font <select class="input sm" data-st="font">${fontOptions()}</select></label>
          <label>Font size (pt) <input class="input sm num" data-st="font_size" value="${esc(st.font_size)}"></label>
          <label>Line width (pt) <input class="input sm num" data-st="line_width" value="${esc(st.line_width)}"></label></div></details>
        <details data-sec="elements"><summary>Lines, labels and areas</summary>
          <label>Palette for named series <select class="input sm" data-st="palette">${opt(PALETTES, st.palette)}</select></label>
          ${groupRows()}
          <div class="hint">One by one: tick to show, pick a colour, rename or change the text.</div>
          ${selBar()}
          <div class="cus-els">${elementRows()}</div>${seriesRows()}</details>
        <details data-sec="find"><summary>Find and replace in labels</summary>${findRows()}</details>
        <details data-sec="colour"><summary>Frame colours</summary><div class="cus-fcols">${colorRows()}</div>
          <button class="btn sm ghost" data-act="nocolors" ${Object.keys(st.colors).length ? '' : 'disabled'}>Module colours</button></details>
        <details data-sec="axes"><summary>Axes, zoom, legend and title</summary>
          <div class="hint">Drag a box on the preview to show only that area; the limits below change with it.</div>
          <button class="btn sm ghost" data-act="unzoom">Reset zoom</button>
          <div class="cus-axes">${axesRows()}</div>
          <div class="cus-grid">
            <label>Legend <select class="input sm" data-lg="show">${opt([['', 'as drawn'], ['1', 'show'], ['0', 'hide']], st.legend.show === undefined ? '' : st.legend.show ? '1' : '0')}</select></label>
            <label>Position <select class="input sm" data-lg="loc">${opt([['', 'as drawn'], ...LOCS.map((l) => [l, l])], st.legend.loc || '')}</select></label>
            <label><input type="checkbox" data-lg="frame" ${st.legend.frame ? 'checked' : ''}> frame</label>
            <label>Title <input class="input sm" data-st="title" value="${esc(st.title)}" placeholder="${esc(describe ? plain(describe.title) : '')}" ${st.noTitle ? 'disabled' : ''}></label>
            <label><input type="checkbox" data-st="noTitle" ${st.noTitle ? 'checked' : ''}> no title</label></div></details>
        <details data-sec="crop"><summary>Crop</summary>${cropRows()}</details>`
        : '<div class="hint">This result has no stored measurement, so the module cannot redraw the figure. You can still change the caption and the placement.</div>';
      parts += `<details data-sec="place"><summary>Place in the document</summary>${placeRows()}</details>`;
    } else if (kind === 'table') {
      parts = `<div class="cus-cols"><div class="hint">Columns to keep</div><div class="cus-collist">${icon('loader')}</div></div>
        <label>Decimals of plain numbers <input class="input sm num" data-digits value="${esc(table.digits)}" placeholder="as computed"></label>`;
    } else {
      parts = `<label class="cus-text">Text <span class="hint">LaTeX; this variant keeps your wording when the original is refreshed</span>
        <textarea class="input mono" rows="16" data-text>${esc(text ?? '')}</textarea></label>`;
    }
    form.innerHTML = `${capRow}${parts}
      <fieldset class="cus-mode"><legend>Keep the variant</legend>
        <label title="Refresh of the original redraws this variant with the new data"><input type="radio" name="cus-mode" value="live" ${mode === 'live' ? 'checked' : ''}> live: follows the original</label>
        <label title="Frozen as it is now; refresh it on its own when you want"><input type="radio" name="cus-mode" value="snapshot" ${mode === 'snapshot' ? 'checked' : ''}> snapshot: stays as it is</label></fieldset>`;
    form.querySelectorAll('details').forEach((d) => { if (open.has(d.dataset.sec)) d.open = true; });
    wire();
  }

  function wire() {
    const cap = form.querySelector('[data-cap]');
    if (cap) cap.oninput = () => (caption = cap.value);
    form.querySelectorAll('[data-part]').forEach((el) => (el.onchange = () => {
      setPart(st, describe, el.dataset.part, el.checked);
      render();
      schedule();
    }));
    form.querySelectorAll('[name=cus-mode]').forEach((r) => (r.onchange = () => (mode = r.value)));
    form.querySelectorAll('[data-st]').forEach((el) => {
      el.onchange = el.oninput = () => {
        const k = el.dataset.st;
        st[k] = el.type === 'checkbox' ? el.checked : el.value;
        if (k === 'noTitle') form.querySelector('[data-st=title]').disabled = el.checked;
        schedule();
      };
    });
    form.querySelectorAll('[data-lg]').forEach((el) => {
      el.onchange = () => {
        const k = el.dataset.lg;
        if (k === 'frame') st.legend.frame = el.checked;
        else if (el.value === '') delete st.legend[k];
        else st.legend[k] = k === 'show' ? el.value === '1' : el.value;
        schedule();
      };
    });
    form.querySelectorAll('[data-ser]').forEach((row) => {
      row.querySelectorAll('[data-k]').forEach((el) => {
        el.onchange = el.oninput = () => {
          const d = (st.series[row.dataset.ser] ||= {});
          d[el.dataset.k] = el.type === 'checkbox' ? el.checked : el.value;
          schedule();
        };
      });
    });
    const elOf = Object.fromEntries(((describe && describe.elements) || []).map((e) => [e.key, e]));
    form.querySelectorAll('[data-el]').forEach((row) => {
      const key = row.dataset.el;
      row.onclick = (ev) => {
        if (ev.target.closest('input, select, button, textarea, label')) return;
        select(key, { ctrl: ev.ctrlKey || ev.metaKey, shift: ev.shiftKey });
        render();
        liveApply();
      };
      row.querySelectorAll('[data-k]').forEach((el) => {
        const k = el.dataset.k;
        if (k === 'reset') {
          el.onclick = () => {
            delete st.elements[key];
            render();
            schedule();
          };
          return;
        }
        el.onchange = el.oninput = () => {
          const d = (st.elements[key] ||= {});
          if (k === 'show') {
            const grpHidden = !!(st.groups[(elOf[key] || {}).group] || {}).hidden || !!(st.parts[(elOf[key] || {}).part] || {}).hidden;
            delete d.hidden;
            if (el.checked && grpHidden) d.hidden = false;      // shown although its kind is hidden
            if (!el.checked && !grpHidden) d.hidden = true;
            row.classList.toggle('off', !el.checked);
          } else if (el.value === '') delete d[k];
          else d[k] = el.value;
          if (!Object.keys(d).length) delete st.elements[key];
          row.querySelector('[data-k=reset]').hidden = !st.elements[key];
          schedule();
        };
      });
    });
    form.querySelectorAll('[data-grp]').forEach((row) => {
      const g = row.dataset.grp;
      row.querySelectorAll('[data-k]').forEach((el) => {
        const k = el.dataset.k;
        if (k === 'reset') {
          el.onclick = () => {
            delete st.groups[g];
            render();
            schedule();
          };
          return;
        }
        el.oninput = () => {
          const d = (st.groups[g] ||= {});
          if (k === 'show') {
            if (el.checked) delete d.hidden;
            else d.hidden = true;
            row.classList.toggle('off', !el.checked);
          } else if (k === 'bold') {
            if (el.value === '') delete d.bold;
            else d.bold = el.value === '1';
          } else if (el.value === '') delete d[k];
          else d[k] = el.value;
          if (!Object.keys(d).length) delete st.groups[g];
          row.querySelector('[data-k=reset]').hidden = !st.groups[g];
          schedule();
        };
        el.onchange = () => {
          el.oninput();
          render();            // the rows below show the new state of their kind
        };
      });
    });
    form.querySelectorAll('[data-sa]').forEach((el) => {
      const k = el.dataset.sa;
      const each = (fn) => {
        for (const key of sel) {
          const d = (st.elements[key] ||= {});
          fn(d, elOf[key] || {});
          if (!Object.keys(d).length) delete st.elements[key];
        }
      };
      if (el.tagName === 'BUTTON') {
        el.onclick = () => {
          if (k === 'none') sel.clear();
          else if (k === 'reset') each((d) => Object.keys(d).forEach((p) => delete d[p]));
          else
            each((d, e) => {
              const grpHidden = !!(st.groups[e.group] || {}).hidden || !!(st.parts[e.part] || {}).hidden;
              delete d.hidden;
              if (k === 'show' && grpHidden) d.hidden = false;
              if (k === 'hide' && !grpHidden) d.hidden = true;
            });
          render();
          schedule();
        };
        return;
      }
      el.oninput = () => {
        if (el.value === '') return;
        each((d) => (d[k] = el.value));
        schedule();
      };
      el.onchange = () => render();
    });
    form.querySelectorAll('[data-f]').forEach((el) => {
      const k = el.dataset.f;
      if (k === 'count') return;
      el.oninput = () => {
        find[k] = el.type === 'checkbox' ? el.checked : el.value;
        const c = countMatches(labelTargets(describe, st), find.q, find.cs);
        form.querySelector('[data-f=count]').textContent = find.q ? `${c.matches} match${c.matches === 1 ? '' : 'es'} in ${c.labels} label${c.labels === 1 ? '' : 's'}` : '';
        form.querySelector('[data-act=replace]').disabled = !c.matches;
      };
    });
    form.querySelectorAll('[data-fcol]').forEach((el) => {
      el.oninput = () => {
        st.colors[el.dataset.fcol] = el.value;
        schedule();
      };
      el.onchange = () => render();
    });
    form.querySelectorAll('[data-ax]').forEach((row) => {
      row.querySelectorAll('[data-k]').forEach((el) => {
        el.onchange = el.oninput = () => {
          const i = +row.dataset.ax;
          while (st.axes.length <= i) st.axes.push({});
          st.axes[i][el.dataset.k] = el.type === 'checkbox' ? el.checked : el.value;
          schedule();
        };
      });
    });
    form.querySelectorAll('[data-crop]').forEach((el) => {
      el.oninput = () => {
        const c = st.crop || [0, 0, 0, 0];
        c[+el.dataset.crop] = Math.min(0.45, Math.max(0, (num(el.value) || 0) / 100));
        st.crop = c.some((v) => v > 0) ? c : null;
        schedule();
      };
    });
    form.querySelectorAll('[data-pl]').forEach((el) => {
      el.oninput = el.onchange = () => {
        const k = el.dataset.pl;
        if (k === 'full') place.width = el.checked ? 'full' : '';
        else if (k === 'width') place.width = +el.value / 100;
        else place[k] = el.value;
        if (k === 'full') render();
        else if (k === 'width') form.querySelector('[data-plw]').textContent = `${el.value} %`;
      };
    });
    const act = (name, fn) => {
      const b = form.querySelector(`[data-act=${name}]`);
      if (b) b.onclick = fn;
    };
    act('replace', () => {
      undoReplace = JSON.stringify({ elements: st.elements, axes: st.axes, title: st.title });
      const n = replaceAll(st, labelTargets(describe, st), find.q, find.r, find.cs);
      toast(`Replaced in ${n} label${n === 1 ? '' : 's'}`, 'ok', 3000);
      render();
      schedule();
    });
    act('unreplace', () => {
      if (!undoReplace) return;
      Object.assign(st, JSON.parse(undoReplace));
      undoReplace = null;
      render();
      schedule();
    });
    act('nocolors', () => {
      st.colors = {};
      render();
      schedule();
    });
    act('unzoom', () => {
      st.axes.forEach((a) => ['xmin', 'xmax', 'ymin', 'ymax'].forEach((k) => delete a[k]));
      render();
      runPreview();
    });
    act('crop', () => {
      cropMode = !cropMode;
      render();
      runPreview();
    });
    act('uncrop', () => {
      st.crop = null;
      render();
      runPreview();
    });
    const dg = form.querySelector('[data-digits]');
    if (dg) dg.oninput = () => (table.digits = dg.value);
    const tx = form.querySelector('[data-text]');
    if (tx) tx.oninput = () => (text = tx.value);
  }

  async function fillTable() {
    const box = form.querySelector('.cus-collist');
    if (!box) return;
    try {
      const tex = await tablePreview();
      const cols = tableColumns(tex);
      box.innerHTML = cols.length
        ? cols.map((c, i) => `<label class="imp-step ${table.hide.has(i) ? '' : 'on'}"><input type="checkbox" data-col="${i}" ${table.hide.has(i) ? '' : 'checked'}><span>${esc(c)}</span></label>`).join('')
        : '<div class="hint">The columns of this table cannot be read; only the decimals can change.</div>';
      box.querySelectorAll('[data-col]').forEach((c) => (c.onchange = () => {
        if (c.checked) table.hide.delete(+c.dataset.col);
        else table.hide.add(+c.dataset.col);
        c.closest('.imp-step').classList.toggle('on', c.checked);
      }));
      pv.innerHTML = `<pre class="cus-tex">${esc(tex.trim())}</pre>`;
    } catch (e) {
      box.innerHTML = `<div class="hint">${esc(e.message)}</div>`;
    }
  }

  if (kind === 'text' && text === null) {
    try {
      // a methods text starts from the sentences chosen for the report (with their edits), not the full text
      const r = await api('GET', fileUrl(projectId, `lab/${origSlug}/${it.shown_file || it.file}`), undefined, { raw: true });
      text = await r.text();
    } catch {
      text = '';
    }
  }
  render();
  if (kind === 'table') fillTable();
  if (kind === 'text') pv.innerHTML = '<div class="hint">Edit the text on the right. The original text stays in its result.</div>';
  if (kind === 'figure') {
    // first the figure as the module draws it (element keys, axes), then with the stored style if any
    pv.innerHTML = `<img alt="" src="${esc(fileUrl(projectId, `lab/${slug}/${(isFork ? (man.items.find((i) => i.id === itemId) || it) : it).preview || it.file}`))}&v=${encodeURIComponent(man.updated)}">`;
    if (canStyle) stateEl.innerHTML = `${icon('loader')} Reading the figure…`;
    if (canStyle) api('POST', `${base}/${origSlug}/preview`, { item: itemId, style: {} })
      .then((r) => {
        describe = r.describe;
        render();
        stateEl.textContent = '';
        if (Object.keys(buildSpec(st)).length) runPreview();
        else if (r.png || r.svg) {
          showResult(r);
          stateEl.textContent = r.svg ? 'Drag a box on the plot to zoom, click an element to select it' : 'Drag a box on the plot to zoom';
        }
      })
      .catch((e) => (stateEl.textContent = e.message));
  }

  async function save(asNew) {
    const payload = { item: itemId, mode };
    if (kind !== 'text' && (caption !== capAuto || !canStyle)) payload.caption = caption;
    if (kind === 'figure' && canStyle) payload.style = buildSpec(st);
    if (kind === 'figure') payload.place = cleanPlace(place);
    if (kind === 'table') payload.table = { hide: [...table.hide], digits: table.digits === '' ? null : +table.digits };
    if (kind === 'text') payload.text = text;
    if (isFork && !asNew) payload.target = slug;
    const out = await api('POST', `${base}/${origSlug}/fork`, payload);
    if (reloadFromDisk) await reloadFromDisk(`lab/${out.slug}/`).catch(() => {});
    toast(`${isFork && !asNew ? 'Variant updated' : 'Variant saved'}: ${plain(out.title)}`, 'ok', 4000);
    return { slug: out.slug, item: itemId, bundle: out };
  }

  let result = null;
  const buttons = [{ label: 'Cancel', value: null }];
  if (isFork) buttons.push({ label: 'Save as new variant', value: 'new' });
  buttons.push({ label: isFork ? 'Save changes' : 'Save as variant', value: 'save', cls: 'primary' });
  await modal({
    title: `Customise ${kind === 'figure' ? 'figure' : kind === 'table' ? 'table' : 'text'}: ${plain(it.caption || it.title || it.id).slice(0, 60)}`,
    body,
    wide: true,
    buttons,
    onOpen: (m) => m.classList.add('cus-modal'),
    validate: async (v, m) => {
      const btns = m.querySelectorAll('footer .btn');
      btns.forEach((b) => (b.disabled = true));
      try {
        result = await save(v === 'new');
        return true;
      } catch (e) {
        toast(e.message, 'error', 8000);
        btns.forEach((b) => (b.disabled = false));
        return false;
      }
    },
  });
  clearTimeout(timer);
  seq++;
  if (ctrl) ctrl.abort();
  return result;
}
