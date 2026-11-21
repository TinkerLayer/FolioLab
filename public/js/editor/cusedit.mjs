// Pure helpers of the figure editing window (customise.js): the style spec from the form state and back, groups by
// kind, find and replace across labels, range selection, and what the instant preview changes in the SVG. No DOM
// access here, so tools/test_cus_edit.js can check it in node.

/** Groups by kind: one edit changes every element of the kind (same names and props as labstyle.GROUPS). */
export const GROUPS = [
  ['axis_labels', 'Axis labels', ['color', 'size', 'bold', 'hidden']],
  ['tick_labels', 'Tick labels', ['color', 'size', 'hidden']],
  ['series_names', 'Legend entries', ['color', 'size', 'bold']],
  ['annotations', 'Texts in the plot', ['color', 'size', 'bold', 'hidden']],
  ['lines', 'Lines', ['color', 'lw', 'ls', 'alpha', 'hidden']],
  ['markers', 'Markers', ['color', 'size', 'alpha', 'hidden']],
  ['areas', 'Areas and bars', ['color', 'alpha', 'hidden']],
];
const GROUP_PROPS = Object.fromEntries(GROUPS.map(([g, , p]) => [g, p]));

const num = (v) => (v === '' || v === null || v === undefined || Number.isNaN(+v) ? undefined : +v);

/** One element or group entry with only what is set. */
function entry(d, allowed) {
  const e = {};
  const ok = (k) => !allowed || allowed.includes(k);
  if (ok('hidden') && d.hidden === true) e.hidden = true;
  if (ok('hidden') && d.hidden === false) e.hidden = false;
  if (ok('color') && d.color) e.color = d.color;
  if (ok('ls') && d.ls) e.ls = d.ls;
  for (const k of ['lw', 'size', 'alpha']) if (ok(k) && num(d[k]) !== undefined) e[k] = num(d[k]);
  if (ok('bold') && typeof d.bold === 'boolean') e.bold = d.bold;
  return e;
}

/** Turn the form state into a style spec with only what the user set. */
export function buildSpec(st, { noCrop = false } = {}) {
  const s = {};
  if (st.preset && st.preset !== 'standard') s.preset = st.preset;
  for (const k of ['width_mm', 'aspect', 'font_size', 'line_width']) if (num(st[k]) !== undefined) s[k] = num(st[k]);
  if (st.font) s.font = st.font;
  if (st.palette) s.palette = st.palette;
  const ser = {};
  for (const [lab, d] of Object.entries(st.series || {})) {
    const e = {};
    if (d.color) e.color = d.color;
    if (d.ls) e.ls = d.ls;
    if (num(d.lw) !== undefined) e.lw = num(d.lw);
    if (d.hidden) e.hidden = true;
    if (d.label !== undefined && d.label !== '' && d.label !== lab) e.label = d.label;
    if (Object.keys(e).length) ser[lab] = e;
  }
  if (Object.keys(ser).length) s.series = ser;
  const els = {};
  for (const [key, d] of Object.entries(st.elements || {})) {
    const e = entry(d);
    if (d.text !== undefined && d.text !== '') e.text = d.text;
    if (d.label !== undefined && d.label !== '') e.label = d.label;
    if (Object.keys(e).length) els[key] = e;
  }
  if (Object.keys(els).length) s.elements = els;
  const grp = {};
  for (const [g, d] of Object.entries(st.groups || {})) {
    if (!GROUP_PROPS[g]) continue;
    const e = entry(d, GROUP_PROPS[g]);
    if (e.hidden === false) delete e.hidden;
    if (Object.keys(e).length) grp[g] = e;
  }
  if (Object.keys(grp).length) s.groups = grp;
  const prt = Object.fromEntries(Object.entries(st.parts || {}).filter(([, d]) => d && d.hidden).map(([k]) => [k, { hidden: true }]));
  if (Object.keys(prt).length) s.parts = prt;
  const cols = Object.fromEntries(Object.entries(st.colors || {}).filter(([, v]) => v));
  if (Object.keys(cols).length) s.colors = cols;
  if (!noCrop && st.crop && st.crop.some((v) => v > 0.0005)) s.crop = st.crop.map((v) => Math.round(v * 1e4) / 1e4);
  if (st.legend && Object.keys(st.legend).length) s.legend = { ...st.legend };
  if (st.noTitle) s.title = '';
  else if (st.title) s.title = st.title;
  const axes = (st.axes || []).map((a) => {
    const o = {};
    if (a.xlabel) o.xlabel = a.xlabel;
    if (a.ylabel) o.ylabel = a.ylabel;
    const lim = (lo, hi) => (num(lo) !== undefined || num(hi) !== undefined ? [num(lo) ?? null, num(hi) ?? null] : undefined);
    const xl = lim(a.xmin, a.xmax);
    const yl = lim(a.ymin, a.ymax);
    if (xl) o.xlim = xl;
    if (yl) o.ylim = yl;
    if (a.xlog) o.xscale = 'log';
    if (a.ylog) o.yscale = 'log';
    if (a.grid !== undefined) o.grid = a.grid;
    return o;
  });
  if (axes.some((a) => Object.keys(a).length)) s.axes = axes;
  return s;
}

/** Form state from a stored spec (editing a variant again). */
export function stateFrom(spec = {}) {
  const st = {
    preset: spec.preset || 'standard', width_mm: spec.width_mm ?? '', aspect: spec.aspect ?? '', font: spec.font || '',
    font_size: spec.font_size ?? '', line_width: spec.line_width ?? '', palette: typeof spec.palette === 'string' ? spec.palette : '',
    series: {}, elements: {}, groups: {}, parts: {}, colors: { ...(spec.colors || {}) }, crop: Array.isArray(spec.crop) ? [...spec.crop] : null,
    legend: { ...(spec.legend || {}) }, title: spec.title || '', noTitle: spec.title === '', axes: [],
  };
  for (const [k, d] of Object.entries(spec.series || {})) st.series[k] = { ...d };
  for (const [k, d] of Object.entries(spec.elements || {})) st.elements[k] = { ...d };
  for (const [k, d] of Object.entries(spec.groups || {})) if (GROUP_PROPS[k]) st.groups[k] = { ...d };
  for (const [k, d] of Object.entries(spec.parts || {})) if (d && d.hidden) st.parts[k] = { hidden: true };
  st.axes = (spec.axes || []).map((a) => ({
    xlabel: a.xlabel || '', ylabel: a.ylabel || '', xmin: a.xlim ? a.xlim[0] ?? '' : '', xmax: a.xlim ? a.xlim[1] ?? '' : '',
    ymin: a.ylim ? a.ylim[0] ?? '' : '', ymax: a.ylim ? a.ylim[1] ?? '' : '', xlog: a.xscale === 'log', ylog: a.yscale === 'log', grid: a.grid,
  }));
  return st;
}

/** What one element looks like with its group, its part (what the module says it shows, e.g. the envelope) and its
 *  own entry (own wins): the props the instant preview sets. */
export function effective(st, el) {
  const g = (el && el.group && st.groups && st.groups[el.group]) || {};
  const p = (el && el.part && st.parts && st.parts[el.part]) || {};
  const d = (st.elements && st.elements[el.key]) || {};
  const out = { ...entry(g, GROUP_PROPS[el.group]), ...(p.hidden ? { hidden: true } : {}), ...entry(d) };
  if (d.text !== undefined && d.text !== '') out.text = d.text;
  return out;
}

/** Keys from `anchor` to `key` in list order (Shift-click), both included. */
export function rangeKeys(order, anchor, key) {
  const a = order.indexOf(anchor);
  const b = order.indexOf(key);
  if (a < 0 || b < 0) return [key];
  return order.slice(Math.min(a, b), Math.max(a, b) + 1);
}

/** Every label find and replace can change: texts in the plot, legend names, axis labels and the title, each with
 *  its current text (the user's edit or as drawn). */
export function labelTargets(describe, st) {
  const out = [];
  if (!describe) return out;
  for (const e of describe.elements || []) {
    const d = (st.elements || {})[e.key] || {};
    if (e.kind === 'text' || e.kind === 'label') out.push({ type: 'el', key: e.key, prop: 'text', name: e.text, value: d.text || e.raw || '' });
    else if (e.named) out.push({ type: 'el', key: e.key, prop: 'label', name: e.text, value: d.label || e.raw || e.text || '' });
  }
  (describe.axes || []).forEach((a, i) => {
    if (!a || !Object.keys(a).length) return;
    const s = (st.axes || [])[i] || {};
    for (const k of ['xlabel', 'ylabel']) if (s[k] || a[k]) out.push({ type: 'ax', i, prop: k, name: `${k[0]} label`, value: s[k] || a[k] });
  });
  if (!st.noTitle && (st.title || describe.title)) out.push({ type: 'title', prop: 'title', name: 'title', value: st.title || describe.title });
  return out;
}

const escRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const finder = (q, cs) => new RegExp(escRe(q), cs ? 'g' : 'gi');

/** Matches of `q` in the targets: {matches, labels}. */
export function countMatches(targets, q, cs = false) {
  if (!q) return { matches: 0, labels: 0 };
  let matches = 0;
  let labels = 0;
  for (const t of targets) {
    const n = (String(t.value).match(finder(q, cs)) || []).length;
    matches += n;
    if (n) labels++;
  }
  return { matches, labels };
}

/** Replace every match in the targets, writing the new texts into the form state. Returns the labels changed. */
export function replaceAll(st, targets, q, rep, cs = false) {
  if (!q) return 0;
  let n = 0;
  for (const t of targets) {
    const v = String(t.value);
    const nv = v.replace(finder(q, cs), () => rep);
    if (nv === v) continue;
    n++;
    if (t.type === 'el') (st.elements[t.key] ||= {})[t.prop] = nv;
    else if (t.type === 'ax') {
      while (st.axes.length <= t.i) st.axes.push({});
      st.axes[t.i][t.prop] = nv;
    } else st.title = nv;
  }
  return n;
}

/** Parts a figure item declares (labbundle add_figure parts) with whether the spec state shows them: [{id, label,
 *  cites, shown}]. A part hidden in the state is off; otherwise it is on unless every element of it is hidden. */
export function partRows(item, st, describe) {
  const els = (describe && describe.elements) || [];
  return ((item && item.parts) || []).map((p) => {
    const mine = els.filter((e) => e.part === p.id);
    const off = !!(st.parts && st.parts[p.id] && st.parts[p.id].hidden) || (mine.length > 0 && mine.every((e) => effective(st, e).hidden));
    return { id: p.id, label: p.label || p.id, cites: p.cites || [], shown: !off };
  });
}

/** Switch a part on or off in the state: off hides the part; on clears the part and the hidden flags of its elements. */
export function setPart(st, describe, id, on) {
  st.parts ||= {};
  if (!on) {
    st.parts[id] = { hidden: true };
    return;
  }
  delete st.parts[id];
  for (const e of ((describe && describe.elements) || []).filter((x) => x.part === id)) {
    const d = st.elements[e.key];
    if (!d) continue;
    delete d.hidden;
    if (!Object.keys(d).length) delete st.elements[e.key];
  }
}

/** SVG stroke-dasharray of a matplotlib line style at width lw (matplotlib's scaled dash patterns). */
export function dashFor(ls, lw = 1.5) {
  const w = Math.max(lw || 1, 0.1);
  const p = { '--': [3.7, 1.6], dashed: [3.7, 1.6], ':': [1, 1.65], dotted: [1, 1.65], '-.': [6.4, 1.6, 1, 1.6], dashdot: [6.4, 1.6, 1, 1.6] }[ls];
  return p ? p.map((v) => +(v * w).toFixed(2)).join(',') : 'none';
}

/** A text the SVG can show as it is (no LaTeX math or commands): only those are changed instantly. */
export const plainText = (s) => typeof s === 'string' && !/[$\\{}]/.test(s);
