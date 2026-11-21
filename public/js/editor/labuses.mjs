// Pure text helpers for Folio Lab results in the user's .tex files (no DOM, no editor; tested in node by
// tools/test_lab_uses.js):
//   placement of a figure float (width, float position, alignment) and the float text for inserting a figure;
//   the box dragged on a figure preview as new axis limits;
//   every place the text uses a result (findUses) and taking it out as a unit (applyUses): floats and \input lines
//   go, \labval values and references to its labels are frozen as \labstale[<result>]{…}, citation keys only it
//   provides leave their \cite.

// ---------------------------------------------------------------- placement in the document
export const PLACE_POS = [
  ['htbp', 'where it fits (here, top, bottom, page)'],
  ['t', 'top of a page'],
  ['b', 'bottom of a page'],
  ['p', 'page of floats'],
  ['h', 'here if possible'],
  ['H', 'exactly here (float package)'],
];
export const PLACE_ALIGN = [['center', 'centred'], ['left', 'left'], ['right', 'right']];
const ALIGN_CMD = { center: '\\centering', left: '\\raggedright', right: '\\raggedleft' };

/** Placement reduced to known values: {width: 0.1..1 | 'full', pos, align}; empty keys are left out. */
export function cleanPlace(p) {
  const out = {};
  if (!p || typeof p !== 'object') return out;
  if (p.width === 'full') out.width = 'full';
  else if (p.width !== undefined && p.width !== null && p.width !== '' && Number.isFinite(+p.width)) out.width = Math.round(Math.min(1, Math.max(0.1, +p.width)) * 100) / 100;
  if (PLACE_POS.some(([v]) => v === p.pos)) out.pos = p.pos;
  if (ALIGN_CMD[p.align]) out.align = p.align;
  return out;
}

const widthOf = (w) => (w === 'full' ? '\\textwidth' : `${w}\\linewidth`);

/** Set width=… in an \includegraphics option list ("[width=0.9\linewidth, angle=90]"). */
function setWidth(opts, w) {
  const inner = (opts || '').replace(/^\[|\]$/g, '');
  const parts = inner.split(',').map((s) => s.trim()).filter((s) => s && !/^width\s*=/.test(s));
  return `[${[`width=${widthOf(w)}`, ...parts].join(', ')}]`;
}

/** One figure float (\begin{figure}…\end{figure}, also figure*) with the placement applied. */
export function placeFloat(seg, place) {
  const p = cleanPlace(place);
  const m = /^(\s*)\\begin\{(figure\*?)\}(\[[^\]]*\])?/.exec(seg);
  if (!m || !Object.keys(p).length) return seg;
  const env = p.width === 'full' ? 'figure*' : p.width !== undefined && m[2] === 'figure*' ? 'figure' : m[2];
  const opt = p.pos ? `[${p.pos}]` : m[3] || '';
  let body = seg.slice(m[0].length);
  const endTag = `\\end{${m[2]}}`;
  const e = body.lastIndexOf(endTag);
  if (e < 0) return seg;
  const tail = body.slice(e + endTag.length);
  body = body.slice(0, e);
  if (p.align) {
    const cmd = ALIGN_CMD[p.align];
    if (/\\(centering|raggedright|raggedleft)\b/.test(body)) body = body.replace(/\\(centering|raggedright|raggedleft)\b/, cmd);
    else body = `\n\t${cmd}` + body;
  }
  if (p.width !== undefined) body = body.replace(/\\includegraphics(\[[^\]]*\])?\{/, (_, o) => `\\includegraphics${setWidth(o, p.width)}{`);
  return `${m[1]}\\begin{${env}}${opt}${body}\\end{${env}}${tail}`;
}

/** The float for inserting a figure (path without extension). */
export function figureFloat({ path, caption, label, width, place }) {
  const p = cleanPlace(place);
  const w = p.width !== undefined ? p.width : width || '0.9';
  const env = p.width === 'full' ? 'figure*' : 'figure';
  return `\\begin{${env}}[${p.pos || 'htbp'}]\n\t${ALIGN_CMD[p.align || 'center']}\n\t\\includegraphics[width=${widthOf(w)}]{${path}}\n\t\\caption{${caption}}\n\t\\label{${label}}\n\\end{${env}}\n`;
}

const reEsc = (s) => String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/** Every figure float of `text` that includes `path` (without extension), as [{start, end}]. */
export function floatsWith(text, path) {
  const out = [];
  const inc = new RegExp(`\\\\includegraphics(\\[[^\\]]*\\])?\\{\\s*${reEsc(path)}(\\.(pdf|png|jpe?g))?\\s*\\}`);
  const re = /\\begin\{(figure\*?)\}/g;
  let m;
  while ((m = re.exec(text))) {
    const tag = `\\end{${m[1]}}`;
    const e = text.indexOf(tag, m.index);
    if (e < 0) break;
    if (inc.test(text.slice(m.index, e))) out.push({ start: m.index, end: e + tag.length });
    re.lastIndex = e + tag.length;
  }
  return out;
}

/** Apply a placement to every float of `text` that shows `path`. Returns {text, n}. */
export function placeAll(text, path, place) {
  const spots = floatsWith(text, path);
  let out = text;
  for (const s of spots.reverse()) out = out.slice(0, s.start) + placeFloat(out.slice(s.start, s.end), place) + out.slice(s.end);
  return { text: out, n: spots.length };
}

// ---------------------------------------------------------------- zoom: a box dragged on a figure preview
const sig = (v) => +(+v).toPrecision(4);

/** Image share t (0 left/bottom … 1 right/top) of an axis with limits lim -> data value. */
function axisValue(t, lim, scale) {
  t = Math.min(1, Math.max(0, t));
  if (scale === 'log' && lim[0] > 0 && lim[1] > 0) return 10 ** (Math.log10(lim[0]) + t * (Math.log10(lim[1]) - Math.log10(lim[0])));
  return lim[0] + t * (lim[1] - lim[0]);
}

/** A box dragged on the preview (shares of the image, from top left) -> new limits of the axes under it (and its
 *  twins, which share the box). Returns [{i, xmin, xmax, ymin, ymax}] or []. */
export function zoomFromBox(axes, x0, y0, x1, y1) {
  const inBox = (b, x, y) => x >= b[0] && x <= b[2] && y >= b[1] && y <= b[3];
  const hit = (axes || []).findIndex((a) => a && inBox(a.box, x0, y0));
  if (hit < 0) return [];
  const B = axes[hit].box;
  const same = (b) => b.every((v, k) => Math.abs(v - B[k]) < 0.004);
  const out = [];
  axes.forEach((a, i) => {
    if (!a || !same(a.box)) return;
    const [bx0, by0, bx1, by1] = a.box;
    const tx = (x) => (x - bx0) / (bx1 - bx0);
    const ty = (y) => (by1 - y) / (by1 - by0);
    const xs = [axisValue(tx(Math.min(x0, x1)), a.xlim, a.xscale), axisValue(tx(Math.max(x0, x1)), a.xlim, a.xscale)];
    const ys = [axisValue(ty(Math.max(y0, y1)), a.ylim, a.yscale), axisValue(ty(Math.min(y0, y1)), a.ylim, a.yscale)];
    out.push({ i, xmin: sig(xs[0]), xmax: sig(xs[1]), ymin: sig(ys[0]), ymax: sig(ys[1]) });
  });
  return out;
}

// ---------------------------------------------------------------- uses of a result in the text
const CITE_RE = /\\(cite|citep|citet|citealp|citealt|parencite|textcite|autocite|footcite|smartcite|supercite|fullcite|citeauthor|citeyear|nocite|Cite|Parencite|Textcite|Autocite|Smartcite)\*?((?:\s*\[[^\]]*\]){0,2})\s*\{([^{}]*)\}/g;
const REF_RE = /\\(ref|cref|Cref|autoref|Autoref|pageref|eqref|nameref|vref|Vref|cpageref|Cpageref|labelcref)\*?\s*\{([^{}]*)\}/g;
const LABVAL_RE = /\\labval\s*\{([^{}]*)\}\s*\{([^{}]*)\}/g;
const FLOAT_RE = /\\begin\{(figure\*?|table\*?|wrapfigure|wraptable|sidewaysfigure|sidewaystable)\}/g;
const INPUT_RE = /\\(input|include|InputIfFileExists|includegraphics|subfile)\*?(\[[^\]]*\])?\s*\{([^{}]*)\}/g;
const NAMES = {
  de: { fig: 'Abb.', tab: 'Tab.', eq: 'Gl.', sec: 'Abschnitt' },
  en: { fig: 'Fig.', tab: 'Table', eq: 'Eq.', sec: 'Section' },
};

const lineStart = (t, i) => t.lastIndexOf('\n', i - 1) + 1;
const lineEnd = (t, i) => {
  const e = t.indexOf('\n', i);
  return e < 0 ? t.length : e;
};
function lineNo(t, i) {
  let n = 1;
  for (let k = t.indexOf('\n'); k >= 0 && k < i; k = t.indexOf('\n', k + 1)) n++;
  return n;
}
/** An unescaped % before position i on its line. */
const commented = (t, i) => /(^|[^\\])(\\\\)*%/.test(t.slice(lineStart(t, i), i));
/** [a, b) widened to whole lines when only blanks (and a comment after) share them. */
function wholeLines(t, a, b) {
  const ls = lineStart(t, a);
  const le = lineEnd(t, b);
  if (/^[ \t]*$/.test(t.slice(ls, a)) && /^[ \t]*(%.*)?$/.test(t.slice(b, le))) return [ls, Math.min(t.length, le + 1)];
  return [a, b];
}
export const plainTex = (s) => String(s || '').replace(/~?\\cite\{[^}]*\}/g, '').replace(/\\[,;: ]/g, ' ').replace(/\\%/g, '%').replace(/\\[a-zA-Z]+\*?\{([^{}]*)\}/g, '$1').replace(/\\[a-zA-Z]+/g, '').replace(/[{}$~\\]/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 80);

/**
 * Every place of the .tex files that uses result `info.slug`.
 * files: {path: text} (lab/ and the result's own section file are skipped); info: from the hub's uses-info route
 * {slug, lang, labels, keys (citation keys only this result provides), values {key: LaTeX}, numbers {label: {num,
 * page}}, section}. Returns [{file, line, start, end, kind, action, what, replace, value?}] sorted by file and place:
 *   float / input / section  -> remove (whole lines when they stand alone)
 *   value / ref              -> freeze as \labstale[<slug>]{<value or number>}; a reference list that also names
 *                               other labels only loses ours (drop)
 *   cite                     -> drop our keys from the list; a \cite left empty goes, with the tie before it
 * Commented-out text is left alone.
 */
export function findUses(files, info) {
  const slug = info.slug;
  const labels = new Set(info.labels || []);
  const keys = new Set(info.keys || []);
  const names = NAMES[info.lang === 'en' ? 'en' : 'de'];
  const ours = new RegExp(`(^|[{,\\s])lab/${reEsc(slug)}/`);
  const sectionBase = info.section ? info.section.replace(/\.tex$/i, '') : null;
  const out = [];
  for (const [file, text] of Object.entries(files)) {
    if (file.startsWith('lab/') || (info.section && file === info.section)) continue;
    const taken = [];
    const inside = (i) => taken.some(([a, b]) => i >= a && i < b);
    const add = (u) => out.push({ file, line: lineNo(text, u.start), ...u });
    let m;
    FLOAT_RE.lastIndex = 0;
    while ((m = FLOAT_RE.exec(text))) {
      const tag = `\\end{${m[1]}}`;
      const e = text.indexOf(tag, m.index);
      if (e < 0) break;
      const seg = text.slice(m.index, e + tag.length);
      if (!commented(text, m.index) && ours.test(seg)) {
        const [a, b] = wholeLines(text, m.index, e + tag.length);
        taken.push([a, b]);
        const cap = /\\caption(?:\[[^\]]*\])?\{((?:[^{}]|\{[^{}]*\})*)\}/.exec(seg);
        add({ start: a, end: b, kind: 'float', action: 'remove', what: `${/table/.test(m[1]) ? 'table' : 'figure'}${cap ? ` “${plainTex(cap[1])}”` : ''}`, replace: '' });
      }
      FLOAT_RE.lastIndex = e + tag.length;
    }
    INPUT_RE.lastIndex = 0;
    while ((m = INPUT_RE.exec(text))) {
      if (inside(m.index) || commented(text, m.index)) continue;
      const target = m[3].trim().replace(/\.tex$/i, '');
      const sec = sectionBase && target === sectionBase;
      if (!sec && !target.startsWith(`lab/${slug}/`)) continue;
      const [a, b] = wholeLines(text, m.index, m.index + m[0].length);
      taken.push([a, b]);
      add({ start: a, end: b, kind: sec ? 'section' : 'input', action: 'remove', what: sec ? `results section ${info.section}` : `\\${m[1]}{${m[3].trim()}}`, replace: '' });
    }
    LABVAL_RE.lastIndex = 0;
    while ((m = LABVAL_RE.exec(text))) {
      if (inside(m.index) || commented(text, m.index) || m[1].trim() !== slug) continue;
      const v = (info.values || {})[m[2].trim()];
      add({ start: m.index, end: m.index + m[0].length, kind: 'value', action: 'freeze', what: `\\labval{${slug}}{${m[2].trim()}}`, value: v ?? null, replace: `\\labstale[${slug}]{${v ?? '??'}}` });
    }
    REF_RE.lastIndex = 0;
    while ((m = REF_RE.exec(text))) {
      if (inside(m.index) || commented(text, m.index)) continue;
      const list = m[2].split(',').map((s) => s.trim()).filter(Boolean);
      const mine = list.filter((l) => labels.has(l));
      if (!mine.length) continue;
      const start = m.index;
      const end = m.index + m[0].length;
      if (mine.length < list.length) {
        add({ start, end, kind: 'ref', action: 'drop', what: `${mine.join(', ')} from \\${m[1]}`, replace: m[0].replace(/\{[^{}]*\}$/, `{${list.filter((l) => !labels.has(l)).join(',')}}`) });
        continue;
      }
      const num = (l) => {
        const n = (info.numbers || {})[l];
        return n ? (/page/i.test(m[1]) ? n.page : n.num) : '??';
      };
      let val = mine.map(num).join(', ');
      const name = names[mine[0].split(':')[0]];
      if (/^(cref|Cref|autoref|Autoref|vref|Vref)$/.test(m[1]) && name) val = `${name}~${val}`;
      if (m[1] === 'eqref') val = `(${val})`;
      add({ start, end, kind: 'ref', action: 'freeze', what: m[0], value: val, replace: `\\labstale[${slug}]{${val}}` });
    }
    CITE_RE.lastIndex = 0;
    while ((m = CITE_RE.exec(text))) {
      if (inside(m.index) || commented(text, m.index)) continue;
      const list = m[3].split(',').map((s) => s.trim()).filter(Boolean);
      const mine = list.filter((k) => keys.has(k));
      if (!mine.length) continue;
      const rest = list.filter((k) => !keys.has(k));
      let start = m.index;
      const end = m.index + m[0].length;
      if (!rest.length) {
        if (text[start - 1] === '~' || (text[start - 1] === ' ' && /\S/.test(text[start - 2] || ''))) start--;
        add({ start, end, kind: 'cite', action: 'remove', what: `\\${m[1]}{${mine.join(',')}}`, replace: '' });
      } else add({ start, end, kind: 'cite', action: 'drop', what: `${mine.join(', ')} from \\${m[1]}`, replace: `\\${m[1]}${m[2]}{${rest.join(',')}}` });
    }
  }
  return out.sort((a, b) => a.file.localeCompare(b.file) || a.start - b.start);
}

/** The text with the uses of that file (from findUses) applied. */
export function applyUses(text, uses) {
  let out = text;
  for (const u of [...uses].sort((a, b) => b.start - a.start)) out = out.slice(0, u.start) + u.replace + out.slice(u.end);
  return out;
}