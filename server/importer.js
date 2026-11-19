'use strict';
// Report import: bring pieces of other sources into a report as an analysis result lab/<slug>/.
//
// Sources: other reports of the hub (any piece, or a whole analysis result), uploaded ZIP / LaTeX projects (staged
// as for combining), and the shared results and index values of the active suite project.
// One import = one result (module "import"): figures, tables (as text items), equations, sections, images, data,
// values and the references they cite, plus lab/<slug>/preamble.tex with the packages and macros they need
// (loaded through lab/labdata.tex). A whole analysis result is copied as it is (its module can still refresh it).
//
// Links (manifest.link): mode live (default; marked out of date when the source changes, one click updates),
// pin (fixed; an update is offered) or copy (no link, origin kept for the record). States follow the Sharebox:
// current / stale (live) / update (pin) / failed (source gone). A portable ZIP brings folio-link.json; when the
// report it came from exists here, the import links to that report instead of the ZIP.
const fs = require('fs');
const fsp = fs.promises;
const path = require('path');
const crypto = require('crypto');
const { HttpError, readText, walk } = require('./util');
const P = require('./projects');
const lab = require('./lab');
const suite = require('./suite');
const T = require('./combine').tex;
const PT = require('./portable');
const PC = require('./pieces');
const { readZip } = require('./zip');

const STAGING = path.join(P.PROJECTS_DIR, '.staging');
const MODES = ['live', 'pin', 'copy'];
const SHARE_RE = /^s-[0-9a-f]{8}$/;
const INDEX_RE = /^g-[0-9a-f]{8}$/;
const PID_RE = /^[a-f0-9]{12}$/;
const SUITE_PID_RE = /^[a-z0-9][a-z0-9-]{0,39}$/;
const FILE_OK = /^[A-Za-z0-9_][A-Za-z0-9_.\-/]{0,120}$/;

const b64 = (data) => Buffer.from(data).toString('base64');
const texEsc = (s) => String(s ?? '').replace(/[\\&%$#_{}~^]/g, (c) => ({ '\\': '\\textbackslash{}', '~': '\\textasciitilde{}', '^': '\\textasciicircum{}' })[c] || '\\' + c);

// ---------------------------------------------------------------------------- sources

async function suiteDir() {
  const s = await suite.list();
  return { project: s.active, name: (s.projects.find((p) => p.id === s.active) || {}).name || s.active, dir: path.join(suite.SUITE_DIR, 'projects', s.active) };
}

/** What the import dialog offers for target report `target`. */
async function sources(target) {
  const reports = (await P.listProjects()).filter((r) => r.id !== target);
  const results = [];
  for (const r of reports) {
    for (const b of await PC.readResults(P.filesDir(r.id))) {
      results.push({ project: r.id, projectName: r.name, slug: b.slug, title: b.title || b.slug, module: b.module, module_name: b.module_name || b.module, revision: b.revision || 1, updated: b.updated || null, preview: firstPreview(b) });
    }
  }
  const s = await suiteDir();
  const shares = (await readShares(s.dir)).map((m) => ({ id: m.id, title: m.title, kind: m.kind, latest: m.latest, producer: m.producer && (m.producer.module_name || m.producer.module), env: m.producer && m.producer.env_name }));
  const index = (await readIndex(s.dir)).map((e) => ({ id: e.id, key: e.key, label: e.label, quantity: e.quantity, type: e.type }));
  return { reports: reports.map((r) => ({ id: r.id, name: r.name, modified: r.modified })), results, suite: { project: s.project, name: s.name, shares, index } };
}
function firstPreview(b) {
  const f = (b.items || []).find((i) => i.kind === 'figure');
  return f ? `lab/${b.slug}/${f.preview || f.file}` : null;
}

async function readShares(dir) {
  const out = [];
  for (const d of await fsp.readdir(path.join(dir, 'sharebox'), { withFileTypes: true }).catch(() => [])) {
    if (!d.isDirectory() || !SHARE_RE.test(d.name)) continue;
    try {
      const m = JSON.parse(await fsp.readFile(path.join(dir, 'sharebox', d.name, 'share.json'), 'utf8'));
      if (m && m.latest) out.push({ ...m, id: d.name });
    } catch {
      /* broken share */
    }
  }
  return out.sort((a, b) => String(b.modified || '').localeCompare(String(a.modified || '')));
}
async function readEnvelope(dir, id, version) {
  return JSON.parse(await fsp.readFile(path.join(dir, 'sharebox', id, `v${+version}.json`), 'utf8'));
}
async function readIndex(dir) {
  const out = [];
  for (const f of await fsp.readdir(path.join(dir, 'index')).catch(() => [])) {
    if (!/^g-[0-9a-f]{8}\.json$/.test(f)) continue;
    try {
      out.push(JSON.parse(await fsp.readFile(path.join(dir, 'index', f), 'utf8')));
    } catch {
      /* broken entry */
    }
  }
  return out.sort((a, b) => String(a.key).localeCompare(String(b.key)) || String(a.created).localeCompare(String(b.created)));
}

/** Folder of a LaTeX source: {type:'report', project} or {type:'zip', stage}. */
async function sourceDir(desc) {
  if (desc.type === 'report') {
    if (!PID_RE.test(String(desc.project || ''))) throw new HttpError(400, 'Invalid report');
    const meta = await P.readMeta(desc.project);
    return { dir: P.filesDir(desc.project), name: meta.name, engine: meta.engine, title: meta.name };
  }
  if (desc.type === 'zip') {
    if (!/^[a-f0-9]{12}$/.test(String(desc.stage || ''))) throw new HttpError(400, 'Bad stage id');
    const dir = path.join(STAGING, desc.stage);
    const info = JSON.parse((await readText(path.join(dir, 'stage.json'))) || 'null');
    if (!info) throw new HttpError(410, 'The uploaded ZIP has expired. Please add it again.');
    return { dir: path.join(dir, 'files'), name: info.name, title: info.name, zipName: info.source };
  }
  throw new HttpError(400, 'Unknown source');
}

/** Pieces of a source for the dialog. desc: report | zip | suite. */
async function pieces(desc) {
  if (desc.type === 'suite') {
    const s = await suiteDir();
    const out = [];
    for (const m of await readShares(s.dir)) {
      const isData = m.kind === 'data.table';
      out.push({ key: `share:${m.id}`, kind: isData ? 'data' : 'values', title: m.title || m.id, detail: `${m.producer ? m.producer.module_name || m.producer.module || '' : ''}${m.producer && m.producer.env_name ? ` · ${m.producer.env_name}` : ''} · version ${m.latest}`, share: m.id, version: m.latest });
    }
    for (const e of await readIndex(s.dir)) {
      out.push({ key: `index:${e.id}`, kind: 'values', title: `${e.label || e.key}`, detail: `${fmtPlain(e.quantity)} · ${e.type || ''}`.trim(), entry: e.id });
    }
    return { source: { type: 'suite', project: s.project, title: s.name }, pieces: out };
  }
  const sd = await sourceDir(desc);
  const src = await PC.loadSource(sd.dir, { name: sd.name, engine: sd.engine });
  const reconnect = src.link && (await reconnectTarget(src.link));
  return {
    source: { ...desc, title: sd.title, link: src.link ? { prefix: src.link.prefix, project: src.link.project, reconnects: !!reconnect } : null },
    pieces: PC.listPieces(src).map((p) => PC.summary(src, p)),
    problems: src.part.problems || [],
  };
}

/** A portable ZIP's original report, if it exists in this hub. */
async function reconnectTarget(link) {
  const id = link && link.project && link.project.id;
  if (!PID_RE.test(String(id || ''))) return null;
  try {
    await P.readMeta(id);
    return id;
  } catch {
    return null;
  }
}

/** Resolve a file of a source for previews (images only). */
async function sourceFile(desc, rel) {
  const sd = await sourceDir(desc);
  if (!/\.(png|jpe?g|pdf|gif|svg)$/i.test(String(rel || ''))) throw new HttpError(400, 'Only images can be previewed');
  return require('./util').safeJoin(sd.dir, rel).abs;
}

// ---------------------------------------------------------------------------- formatting values

function langOf(mainText) {
  const m = /\\usepackage\s*\[([^\]]*)\]\s*\{babel\}/.exec(T.stripComments(mainText || ''));
  const last = m ? m[1].split(',').map((x) => x.trim()).filter(Boolean).pop() : '';
  return /^(english|british|american|UKenglish|USenglish|australian|canadian|newzealand)$/i.test(last || '') ? 'en' : 'de';
}
function fmtNum(v, lang) {
  if (typeof v !== 'number' || !Number.isFinite(v)) return { tex: String(v), text: String(v) };
  let s = Number.isInteger(v) && Math.abs(v) < 1e7 ? String(v) : String(Number(v.toPrecision(5)));
  let exp = '';
  const m = /^(-?[\d.]+)e([+-]?\d+)$/.exec(s);
  if (m) {
    s = m[1];
    exp = String(+m[2]);
  }
  const dec = lang === 'en' ? '.' : ',';
  const text = s.replace('.', dec) + (exp ? `·10^${exp}` : '');
  const tex = s.replace('.', lang === 'en' ? '.' : '{,}') + (exp ? `\\cdot 10^{${exp}}` : '');
  return { tex, text };
}
function unitTex(u) {
  const s = String(u || '').trim();
  if (!s) return '';
  const t = s
    .replace(/\\/g, '')
    .replace(/[{}$#&_]/g, '')
    .replace(/%/g, '\\%')
    .replace(/°/g, '^{\\circ}')
    .replace(/[µμ]/g, '\\mu ')
    .replace(/Ω/g, '\\Omega ')
    .replace(/[·*]/g, '\\cdot ')
    .replace(/²/g, '^2')
    .replace(/³/g, '^3')
    .replace(/[^\x20-\x7e]/g, '');
  return `\\mathrm{${t}}`;
}
function fmtQuantity(q, lang) {
  const v = fmtNum(q && q.value, lang);
  const u = q && q.u != null ? fmtNum(q.u, lang) : null;
  const unit = (q && q.unit) || '';
  const tex = `$${u ? `(${v.tex} \\pm ${u.tex})` : v.tex}${unit ? `\\,${unitTex(unit)}` : ''}$`;
  const text = `${u ? `(${v.text} ± ${u.text})` : v.text}${unit ? ' ' + unit : ''}`;
  return { tex, text };
}
const fmtPlain = (q) => (q ? `${q.value}${q.u != null ? ` ± ${q.u}` : ''}${q.unit ? ' ' + q.unit : ''}` : '');
const safeKey = (k) => String(k || 'v').replace(/[^A-Za-z0-9._:-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60) || 'v';

// ---------------------------------------------------------------------------- npz (data.table shares)

function readNpy(buf) {
  if (buf.readUInt32BE(0) !== 0x934e554d || buf[4] !== 0x50 || buf[5] !== 0x59) throw new Error('not an .npy array');
  const major = buf[6];
  const hl = major === 1 ? buf.readUInt16LE(8) : buf.readUInt32LE(8);
  const off = (major === 1 ? 10 : 12) + hl;
  const head = buf.slice(major === 1 ? 10 : 12, off).toString('latin1');
  const descr = (/'descr'\s*:\s*'([^']+)'/.exec(head) || [])[1];
  if (/'fortran_order'\s*:\s*True/.test(head)) throw new Error('fortran order not supported');
  const shape = ((/'shape'\s*:\s*\(([^)]*)\)/.exec(head) || [])[1] || '').split(',').map((x) => x.trim()).filter(Boolean).map(Number);
  const n = shape.reduce((a, b) => a * b, 1);
  const m = /^([<>|=])([a-zA-Z])(\d+)$/.exec(descr || '');
  if (!m) throw new Error(`dtype ${descr} not supported`);
  const [, end, kind, sizeS] = m;
  const size = +sizeS;
  const le = end !== '>';
  const out = new Array(n);
  for (let i = 0; i < n; i++) {
    const p = off + i * (kind === 'U' ? size * 4 : size);
    if (kind === 'f') out[i] = size === 8 ? (le ? buf.readDoubleLE(p) : buf.readDoubleBE(p)) : le ? buf.readFloatLE(p) : buf.readFloatBE(p);
    else if (kind === 'i') out[i] = size === 8 ? Number(le ? buf.readBigInt64LE(p) : buf.readBigInt64BE(p)) : size === 4 ? (le ? buf.readInt32LE(p) : buf.readInt32BE(p)) : size === 2 ? (le ? buf.readInt16LE(p) : buf.readInt16BE(p)) : buf.readInt8(p);
    else if (kind === 'u') out[i] = size === 8 ? Number(le ? buf.readBigUInt64LE(p) : buf.readBigUInt64BE(p)) : size === 4 ? (le ? buf.readUInt32LE(p) : buf.readUInt32BE(p)) : size === 2 ? (le ? buf.readUInt16LE(p) : buf.readUInt16BE(p)) : buf.readUInt8(p);
    else if (kind === 'b') out[i] = buf[p] !== 0;
    else if (kind === 'U') {
      let s = '';
      for (let c = 0; c < size; c++) {
        const cp = le ? buf.readUInt32LE(p + 4 * c) : buf.readUInt32BE(p + 4 * c);
        if (!cp) break;
        s += String.fromCodePoint(cp);
      }
      out[i] = s;
    } else if (kind === 'S') out[i] = buf.slice(p, p + size).toString('latin1').replace(/\0+$/, '');
    else throw new Error(`dtype ${descr} not supported`);
  }
  return out;
}

/** CSV of a data.table share version: {csv, columns, labels, rows}. */
async function shareCsv(dir, env) {
  const name = String(env.data || '');
  if (!/^v\d+\.npz$/.test(name)) throw new HttpError(400, 'Shared data: file missing');
  const arrays = {};
  for (const e of readZip(await fsp.readFile(path.join(dir, 'sharebox', env.id, name)))) {
    if (e.isDir || !/\.npy$/.test(e.name)) continue;
    arrays[e.name.replace(/\.npy$/, '')] = readNpy(e.data);
  }
  const cols = ((env.dataset && env.dataset.columns) || []).filter((c) => arrays[c.key]);
  if (!cols.length) throw new HttpError(400, 'Shared data has no readable columns');
  const keys = cols.map((c) => safeKey(c.key).replace(/[.:]/g, '_'));
  const rows = Math.max(...cols.map((c) => arrays[c.key].length));
  const cell = (v) => (v == null ? '' : typeof v === 'number' ? (Number.isFinite(v) ? String(v) : 'nan') : /[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v));
  const lines = [keys.join(',')];
  for (let i = 0; i < rows; i++) lines.push(cols.map((c) => cell(arrays[c.key][i])).join(','));
  const labels = {};
  cols.forEach((c, i) => {
    labels[keys[i]] = `${texEsc(c.name || c.key)}${c.unit ? ` [${texEsc(c.unit)}]` : ''}`;
  });
  const x = cols.findIndex((c) => c.role === 'x');
  const y = cols.findIndex((c, i) => c.role === 'y' && i !== x);
  const numeric = cols.map((c, i) => (c.dtype === 'text' ? -1 : i)).filter((i) => i >= 0);
  return {
    csv: lines.join('\n') + '\n', columns: keys, labels, rows,
    plot: numeric.length >= 2 ? { x: keys[x >= 0 ? x : numeric[0]], y: keys[y >= 0 ? y : numeric.find((i) => i !== (x >= 0 ? x : numeric[0]))] } : null,
  };
}

// ---------------------------------------------------------------------------- building an import

/** Keys of all .bib entries already in the target report (own files and other results): lower(key) -> Set(norm). */
async function targetBib(id, exceptSlug) {
  const out = new Map();
  const files = (await walk(P.filesDir(id))).filter((f) => !f.isDir && /\.bib$/i.test(f.rel) && !PC.EXCLUDED_RE.test(f.rel) && f.rel !== 'lab/references.bib' && !(exceptSlug && f.rel.startsWith(`lab/${exceptSlug}/`)));
  for (const f of files) for (const e of T.parseBib((await readText(f.abs)) || '', f.rel)) if (e.kind === 'entry') out.set(e.key.toLowerCase(), (out.get(e.key.toLowerCase()) || new Set()).add(e.norm));
  return out;
}

/** Collects files, items, bib entries, values and preamble statements of one import bundle. */
class Builder {
  constructor(slug, lang, taken) {
    this.slug = slug;
    this.lang = lang;
    this.taken = taken; // target bib: lower(key) -> norm
    this.files = {}; // bundle rel -> Buffer|string
    this.items = [];
    this.ids = new Set();
    this.bib = new Map(); // final key -> raw
    this.values = []; // {key, label, latex, text}
    this.valueKeys = new Set();
    this.statements = [];
    this.stmtSeen = new Set();
    this.compat = '';
    this.warnings = [];
    this.pieces = [];
    this.relMap = new Map(); // source dir + rel -> bundle rel
  }
  id(base) {
    let s = T.slugify(base).slice(0, 40) || 'item';
    let k = s;
    for (let n = 2; this.ids.has(k); n++) k = `${s}-${n}`;
    this.ids.add(k);
    return k;
  }
  fileName(src, rel) {
    const k = src.dir + '|' + rel;
    if (this.relMap.has(k)) return this.relMap.get(k);
    let r = PC.unstrip(src, rel);
    const m = /^lab\/([^/]+)\/(.*)$/.exec(r);
    r = (m ? `${m[1]}/${m[2]}` : `files/${r}`).split('/').map((seg) => seg.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').replace(/[^A-Za-z0-9_.-]+/g, '_').replace(/^[._-]+/, '') || 'x').join('/');
    if (r.length > 110) r = r.slice(0, 60) + '-' + crypto.createHash('sha1').update(r).digest('hex').slice(0, 8) + path.posix.extname(r);
    let out = r;
    for (let n = 2; Object.prototype.hasOwnProperty.call(this.files, out) || [...this.relMap.values()].includes(out); n++) out = r.replace(/(\.[^./]+)?$/, `-${n}$1`);
    this.relMap.set(k, out);
    return out;
  }
  addStatement(s) {
    const k = s.kind === 'packages' ? 'pkg:' + s.pkgs.map((p) => p.name).join(',') : s.key || s.code;
    if (this.stmtSeen.has(k)) return;
    this.stmtSeen.add(k);
    this.statements.push(s);
  }
  /** Cite keys: kept unless the target already has a different entry under that key. Returns the key map. */
  cite(src, entries) {
    const map = new Map();
    for (const e of entries) {
      const orig = PC.unstrip(src, e.key);
      const raw = PC.unstrip(src, e.raw);
      const norm = T.parseBib(raw, '')[0];
      const n = norm ? norm.norm : '';
      let key = orig;
      // any other entry under the key clashes: the report loads all .bib files and only one entry per key wins
      const clash = (k) => [...(this.taken.get(k.toLowerCase()) || [])].some((x) => x !== n) || (this.bib.has(k) && this.bib.get(k).norm !== n);
      for (let i = 2; clash(key); i++) key = `${orig}-${this.slug}${i > 2 ? i : ''}`;
      if (key !== orig) this.warnings.push(`Reference key ${orig} exists with another entry in this report; imported as ${key}.`);
      map.set(e.key, key);
      if (!this.bib.has(key)) this.bib.set(key, { raw: PT.rekey(raw, key), norm: n, title: PT.unbrace(((PT.parseEntry(raw) || { fields: [] }).fields.find((f) => f.name === 'title') || {}).value || '') });
    }
    return map;
  }
  value(key, label, latex, text) {
    let k = safeKey(key);
    for (let n = 2; this.valueKeys.has(k); n++) k = `${safeKey(key)}-${n}`;
    this.valueKeys.add(k);
    this.values.push({ key: k, label: label || key, latex, text: text || null });
    return k;
  }

  /** Labels defined by all LaTeX pieces of this import (call before adding them). */
  prepare(src, pieces) {
    this.labels = new Map();
    for (const p of pieces) if (p.latex) for (const l of PC.analyze(src, p.latex).labels) this.labels.set(l, `${this.slug}:${PC.unstrip(src, l)}`);
  }

  /** A LaTeX piece (figure, table, equation, section). */
  latexPiece(src, p) {
    const a = PC.analyze(src, p.latex);
    const slug = this.slug;
    const rename = new Map();
    const intended = (ref, kind) => {
      const hit = kind === 'graphic' ? T.resolveGraphic(ref, src.part.graphicspath || [], src.own) : kind === 'tex' ? T.resolveTex(ref, src.own) : T.lookup(src.own, ref);
      if (!hit || /^lab\/labdata\.tex$/i.test(hit)) return null;
      const out = this.fileName(src, hit);
      rename.set(hit, out);
      return `lab/${slug}/${out}`;
    };
    // labels of every piece in this import, so a section can refer to an equation imported with it
    const labelMap = new Map([...(this.labels || []), ...a.labels.map((l) => [l, `${slug}:${PC.unstrip(src, l)}`])]);
    const keyMap = this.cite(src, a.bib);
    // values: \labval{<ns>}{<key>} -> \labval{<slug>}{<new key>}
    const nss = [...new Set(a.values.map((v) => PC.unstrip(src, v.ns)))];
    const valMap = new Map();
    for (const v of a.values) {
      const ns = PC.unstrip(src, v.ns);
      const id = `${v.ns}\u0000${v.key}`;
      if (valMap.has(id)) continue;
      const got = PC.valueOf(src, ns, v.key);
      if (!got) {
        this.warnings.push(`Value ${ns}/${v.key} was not found in the source.`);
        continue;
      }
      valMap.set(id, this.value(nss.length > 1 ? `${ns}-${v.key}` : v.key, got.label, got.latex, got.text));
    }
    const fix = (text) => {
      let t = T.rewriteFileRefs(text, intended, () => null, () => {});
      t = T.renameLabelsAndKeys(t, labelMap, keyMap);
      return t.replace(/\\labval(\s*)\{([^{}]*)\}(\s*)\{([^{}]*)\}/g, (all, s1, ns, s2, key) => {
        const k = valMap.get(`${ns.trim()}\u0000${key.trim()}`);
        return k ? `\\labval${s1}{${slug}}${s2}{${k}}` : all;
      });
    };
    const text = fix(p.latex);
    // included .tex files are part of the piece: rewritten the same way
    let guard = 0;
    for (const [hit, out] of rename) {
      if (++guard > 500) break;
      if (src.part.tex.has(hit)) this.files[out] = fix(src.part.tex.get(hit));
      else if (!Object.prototype.hasOwnProperty.call(this.files, out)) this.files[out] = { abs: path.join(src.dir, ...hit.split('/')) };
    }
    for (const r of a.missing) this.warnings.push(`${p.title}: file ${r} not found in the source.`);
    for (const k of a.missingKeys) this.warnings.push(`${p.title}: \\cite{${k}} has no entry in the source.`);
    const refs = [...T.stripComments(text).matchAll(T.LABEL_CMD_RE)].filter((m) => !/^z?label$/.test(m[1])).flatMap((m) => m[3].split(',').map((x) => x.trim()));
    const dangling = [...new Set(refs.filter((r) => r && !r.startsWith(slug + ':')))];
    if (dangling.length) this.warnings.push(`${p.title}: refers to ${dangling.slice(0, 5).join(', ')}${dangling.length > 5 ? ' …' : ''} outside the imported piece.`);
    for (const d of a.defs) this.addStatement(d);
    if (a.packages.size) for (const [name, opts] of a.packages) this.addStatement({ kind: 'packages', pkgs: [{ name, opts }], code: `\\usepackage{${name}}`, raw: '' });
    for (const l of a.libraries) this.addStatement(l);
    if (src.compat) this.compat = this.compat || src.compat.trim();

    const label = p.label ? labelMap.get(p.label) : null;
    if (p.simple && p.simple.graphic && rename.has(p.simple.graphic)) {
      const file = rename.get(p.simple.graphic);
      const id = this.id(`fig-${p.label || p.title}`);
      let preview = null;
      const png = !/\.(png|jpe?g)$/i.test(file) ? T.lookup(src.own, p.simple.graphic.replace(/\.[^.]+$/, '.png')) : null;
      if (png) {
        preview = this.fileName(src, png);
        this.files[preview] = { abs: path.join(src.dir, ...png.split('/')) };
      }
      const capRaw = T.commandArg(T.stripComments(text), 'caption') || '';
      this.items.push({ kind: 'figure', id, file, preview, caption: capRaw, label: label || `fig:${slug}-${id}`, width: p.simple.width || '0.9', cites: [...keyMap.values()] });
      this.pieces.push({ key: p.key, kind: p.kind, item: id });
      return;
    }
    const id = this.id(`${p.kind === 'equation' ? 'eq' : p.kind === 'section' ? 'sec' : p.kind === 'table' ? 'tab' : 'fig'}-${p.label || p.title}`);
    this.files[`text-${id}.tex`] = `% Imported by Folio Lab: ${p.kind} "${String(p.title).replace(/[\r\n]+/g, ' ')}"\n` + text.replace(/\s+$/, '') + '\n';
    this.items.push({ kind: 'text', id, file: `text-${id}.tex`, title: `${p.kind === 'equation' ? 'Equation' : p.kind === 'section' ? 'Section' : p.kind === 'table' ? 'Table' : 'Figure'}: ${p.title}`, piece: p.kind, label: label || null });
    this.pieces.push({ key: p.key, kind: p.kind, item: id });
  }

  imagePiece(src, p) {
    const file = this.fileName(src, p.file);
    this.files[file] = { abs: path.join(src.dir, ...p.file.split('/')) };
    let preview = null;
    if (p.preview && p.preview !== p.file) {
      preview = this.fileName(src, p.preview);
      this.files[preview] = { abs: path.join(src.dir, ...p.preview.split('/')) };
    }
    const id = this.id(`img-${path.posix.basename(p.file).replace(/\.[^.]+$/, '')}`);
    this.items.push({ kind: 'figure', id, file, preview, caption: texEsc(p.title), label: `fig:${this.slug}-${id}`, width: '0.8' });
    this.pieces.push({ key: p.key, kind: p.kind, item: id });
    this.needGraphics = true;
  }

  async dataPiece(src, p) {
    const file = this.fileName(src, p.file);
    const abs = path.join(src.dir, ...p.file.split('/'));
    this.files[file] = { abs };
    const id = this.id(`data-${path.posix.basename(p.file).replace(/\.[^.]+$/, '')}`);
    let item = p.item ? { ...p.item } : null;
    if (!item) {
      const head = ((await readText(abs)) || '').split(/\r?\n/);
      const sep = /\t/.test(head[0]) ? '\t' : /;/.test(head[0]) && !/,/.test(head[0]) ? ';' : ',';
      const cols = head[0].split(sep).map((c) => c.trim().replace(/^"|"$/g, ''));
      item = { columns: cols, rows: head.filter((l) => l.trim()).length - 1, description: p.title };
      if (sep !== ',') this.warnings.push(`${p.title}: columns are separated by "${sep === '\t' ? 'tab' : sep}"; set col sep in pgfplots accordingly.`);
    }
    this.items.push({ ...item, kind: 'data', id, file, description: item.description || p.title });
    this.pieces.push({ key: p.key, kind: p.kind, item: id });
  }

  valuesPiece(src, p) {
    const r = src.results.find((x) => x.slug === p.slug);
    const n0 = this.values.length;
    for (const v of p.values || []) {
      const got = PC.valueOf(src, p.slug, v.key);
      if (!got && !v.latex) continue;
      this.value(v.key, v.label, (got && got.latex) || v.latex, v.text);
    }
    if (r) {
      // the references the values rest on come along (the result's own refs.bib)
      const bib = src.part.bibEntries.filter((e) => e.kind === 'entry' && e.file === `lab/${p.slug}/refs.bib`);
      this.cite(src, bib);
    }
    this.pieces.push({ key: p.key, kind: p.kind, values: this.values.slice(n0).map((v) => v.key) });
  }

  /** The folio-lab-bundle/1 object for lab.save. */
  async bundle({ title, summary, link, lang }) {
    const files = {};
    for (const [rel, data] of Object.entries(this.files)) {
      if (!FILE_OK.test(rel) || rel.includes('..')) throw new HttpError(400, `Cannot store ${rel}`);
      files[rel] = b64(data && data.abs ? await fsp.readFile(data.abs) : data);
    }
    const slug = this.slug;
    if (this.values.length) {
      files['values.tex'] = b64(
        `% Values imported by Folio Lab into '${title.replace(/[\r\n]+/g, ' ')}'. Generated; do not edit.\n% Use as \\labval{${slug}}{<key>}.\n` +
          this.values.map((v) => `\\labset{${slug}}{${v.key}}{${v.latex}}% ${String(v.label).replace(/[\r\n%]+/g, ' ')}`).join('\n') + '\n'
      );
      this.items.push({ kind: 'values', file: 'values.tex', values: this.values.map((v) => ({ key: v.key, label: v.label, latex: v.latex, text: v.text || v.latex })) });
    }
    if (this.bib.size) {
      files['refs.bib'] = b64([...this.bib.values()].map((e) => e.raw).join('\n\n') + '\n');
      for (const [key, e] of this.bib) this.items.push({ kind: 'citation', key, title: e.title || key });
    }
    if (this.statements.length || this.needGraphics) {
      const ctx = { layout: [], commented: [], compat: this.compat };
      if (this.needGraphics) this.statements.unshift({ kind: 'packages', pkgs: [{ name: 'graphicx', opts: '' }], code: '\\usepackage{graphicx}', raw: '' });
      const lines = this.statements.map((s) => PT.portableStatement(s, ctx)).filter(Boolean);
      if (lines.length)
        files['preamble.tex'] = b64(`% Packages and macros of the imported pieces in '${title.replace(/[\r\n]+/g, ' ')}' (Folio Lab).\n% Loaded by lab/labdata.tex; a package is loaded only when the report has not loaded it, a macro only when the name is free.\n\\makeatletter\n${lines.join('\n')}\n\\makeatother\n`);
    }
    return {
      format: lab.FORMAT, module: 'import', module_name: 'Import', title, slug, lang: lang || this.lang, summary,
      created: new Date().toISOString(), items: this.items, files,
      source: { kind: 'import', request: link }, link, module_version: null,
      methods: null,
    };
  }
}

// ---------------------------------------------------------------------------- import

function checkMode(mode) {
  const m = mode || 'live';
  if (!MODES.includes(m)) throw new HttpError(400, 'Mode must be live, pin or copy');
  return m;
}

/**
 * Import pieces into report `id`. body: {source: {type, project|stage}, keys: [...], mode, title?}
 * Returns {results: [manifest…], warnings}.
 */
async function importPieces(id, body = {}, opts = {}) {
  await P.readMeta(id);
  const desc = body.source || {};
  if (desc.type === 'env') return require('./folio').importEnv(id, body, opts); // Pieces of a module environment
  const mode = checkMode(body.mode);
  const keys = Array.isArray(body.keys) ? body.keys.map(String).slice(0, 500) : [];
  if (!keys.length) throw new HttpError(400, 'Choose at least one piece to import');
  if (desc.type === 'suite') return importSuite(id, desc, keys, mode, body, opts);
  const sd = await sourceDir(desc);
  const src = await PC.loadSource(sd.dir, { name: sd.name, engine: sd.engine });
  const all = PC.listPieces(src);
  const chosen = keys.map((k) => all.find((p) => p.key === k) || null);
  const missing = keys.filter((k, i) => !chosen[i]);
  if (missing.length && !opts.slug) throw new HttpError(400, `Not found in the source: ${missing.join(', ')}`);
  const out = { results: [], warnings: [] };

  // a portable ZIP whose report exists here links to that report
  const reconnect = desc.type === 'zip' && src.link ? await reconnectTarget(src.link) : null;
  const linkSource = reconnect ? { type: 'report', project: reconnect } : desc.type === 'report' ? { type: 'report', project: desc.project } : { type: 'zip', name: sd.zipName || sd.name };
  if (reconnect) out.warnings.push(`This ZIP was exported from the report "${src.link.project.name}"; the import links to that report.`);

  // whole analysis results: copied as they are
  for (const p of chosen.filter((x) => x && x.kind === 'result')) {
    out.results.push(await copyResult(id, src, p, { mode, linkSource, sd, replaceSlug: opts.slug }));
  }
  const rest = chosen.filter((x) => x && x.kind !== 'result');
  if (rest.length) {
    const mainText = await readText(path.join(P.filesDir(id), (await P.readMeta(id)).mainFile || 'main.tex'));
    const lang = langOf(mainText);
    const base = `import-${T.slugify(sd.title || 'quelle')}`.slice(0, 50).replace(/-+$/, '');
    const slug = opts.slug || (await lab.uniqueSlug(id, base));
    const B = new Builder(slug, lang, await targetBib(id, opts.slug));
    B.prepare(src, rest);
    for (const p of rest) {
      if (p.latex) B.latexPiece(src, p);
      else if (p.kind === 'image') B.imagePiece(src, p);
      else if (p.kind === 'data') await B.dataPiece(src, p);
      else if (p.kind === 'values') B.valuesPiece(src, p);
    }
    for (const k of missing) B.warnings.push(`${k}: no longer in the source; left out.`);
    const versions = {};
    for (const p of rest) versions[p.key] = await PC.pieceHash(src, p);
    const title = String(body.title || '').trim().slice(0, 120) || (rest.length === 1 ? rest[0].title : `${rest.length} pieces from ${sd.title}`);
    const link = {
      ...linkSource, mode, title: sd.title, keys: rest.map((p) => p.key), versions,
      imported: new Date().toISOString(), ...(desc.type === 'zip' ? { zip: sd.zipName || sd.name } : {}),
    };
    const bundle = await B.bundle({ title, summary: `Imported from ${sd.title}: ${rest.map((p) => p.title).slice(0, 6).join('; ')}${rest.length > 6 ? ' …' : ''}`, link, lang });
    out.results.push(await lab.save(id, bundle, opts.slug ? 'replace' : undefined, { action: opts.slug ? 'update' : 'import' }));
    out.warnings.push(...B.warnings);
  }
  return out;
}

/** Copy a whole analysis result of another report (with its measurement files, so its module can refresh it). */
async function copyResult(id, src, p, { mode, linkSource, sd, replaceSlug }) {
  const dir = path.join(src.dir, 'lab', p.slug);
  const man = JSON.parse(await fsp.readFile(path.join(dir, 'bundle.json'), 'utf8'));
  const files = {};
  const source = {};
  for (const f of await walk(dir)) {
    if (f.isDir || f.rel === 'bundle.json' || /^(history|_removed)\//.test(f.rel)) continue;
    if (f.rel.startsWith('source/')) source[f.rel.slice(7)] = b64(await fsp.readFile(f.abs));
    else files[f.rel] = b64(await fsp.readFile(f.abs));
  }
  const link = {
    ...linkSource, type: 'result', mode, title: sd.title, slug: p.slug, result_id: man.result_id || null, revision: man.revision || 1,
    imported: new Date().toISOString(),
  };
  const bundle = {
    format: lab.FORMAT, module: man.module, module_name: man.module_name, title: man.title, slug: replaceSlug || man.slug || p.slug, lang: man.lang,
    summary: man.summary, created: man.created, items: man.items, files,
    source: man.source && man.source.request ? { request: man.source.request, files: source, kind: man.provenance && man.provenance.source_kind } : null,
    module_version: (man.provenance && man.provenance.module_version) || null, methods: (man.provenance && man.provenance.methods) || null, link,
  };
  return lab.save(id, bundle, replaceSlug ? 'replace' : 'new', { action: replaceSlug ? 'update' : 'import' });
}

/** Shares and index values of the active suite project. */
async function importSuite(id, desc, keys, mode, body, opts) {
  const s = await suiteDir();
  const mainText = await readText(path.join(P.filesDir(id), (await P.readMeta(id)).mainFile || 'main.tex'));
  const lang = langOf(mainText);
  const slug = opts.slug || (await lab.uniqueSlug(id, `import-${T.slugify(s.name || 'projekt')}`.slice(0, 50).replace(/-+$/, '')));
  const B = new Builder(slug, lang, new Map());
  const refs = [];
  const versions = {};
  for (const key of keys) {
    let m;
    if ((m = /^share:(s-[0-9a-f]{8})$/.exec(key))) {
      const meta = JSON.parse((await readText(path.join(s.dir, 'sharebox', m[1], 'share.json'))) || 'null');
      if (!meta) {
        if (opts.slug) continue;
        throw new HttpError(404, `Shared result ${m[1]} not found`);
      }
      const prev = opts.prev && opts.prev.refs ? opts.prev.refs.find((r) => r.id === m[1]) : null;
      const version = prev && prev.mode === 'pin' && !opts.latest ? prev.version : meta.latest;
      const env = await readEnvelope(s.dir, m[1], version);
      if (env.kind === 'data.table') {
        const d = await shareCsv(s.dir, env);
        const id2 = B.id(`data-${env.title || m[1]}`);
        const file = `data/${id2}.csv`;
        B.files[file] = d.csv;
        B.items.push({ kind: 'data', id: id2, file, columns: d.columns, labels: d.labels, plot: d.plot, rows: d.rows, description: `${env.title} (shared, version ${env.version})` });
        B.pieces.push({ key, kind: 'data', item: id2 });
      } else {
        const n0 = B.values.length;
        for (const o of env.outputs || []) {
          const f = fmtQuantity(o.quantity, lang);
          B.value(`${T.slugify(env.title || m[1]).slice(0, 20)}-${o.key}`, o.label || o.key, f.tex, f.text);
        }
        B.pieces.push({ key, kind: 'values', values: B.values.slice(n0).map((v) => v.key) });
      }
      // shape known to labprov/refsIn: {id, mode, version, used} protects the version from deletion
      refs.push({ id: m[1], mode, version: env.version, used: env.version, title: env.title });
      versions[key] = String(env.version);
    } else if ((m = /^index:(g-[0-9a-f]{8})$/.exec(key))) {
      const e = JSON.parse((await readText(path.join(s.dir, 'index', `${m[1]}.json`))) || 'null');
      if (!e) {
        if (opts.slug) continue;
        throw new HttpError(404, `Index value ${m[1]} not found`);
      }
      const f = fmtQuantity(e.quantity, lang);
      const k = B.value(e.key, e.label || e.key, f.tex, f.text);
      B.pieces.push({ key, kind: 'values', values: [k] });
      refs.push({ index: m[1], key: e.key });
      versions[key] = m[1];
    } else throw new HttpError(400, `Unknown piece ${key}`);
  }
  const title = String(body.title || '').trim().slice(0, 120) || (keys.length === 1 ? `${s.name}: ${refs[0] && (refs[0].title || refs[0].key)}` : `${keys.length} values and data from ${s.name}`);
  const link = { type: 'suite', mode, project: s.project, title: s.name, keys, versions, refs, imported: new Date().toISOString() };
  const bundle = await B.bundle({ title, summary: `Shared results and index values of the project ${s.name}`, link, lang });
  return { results: [await lab.save(id, bundle, opts.slug ? 'replace' : undefined, { action: opts.slug ? 'update' : 'import' })], warnings: B.warnings };
}

// ---------------------------------------------------------------------------- link states and update

/** State of one linked result: {slug, type, mode, state, changed:[keys], missing:[keys], error?} */
async function linkState(id, man, cache = new Map()) {
  const link = man.link;
  const base = { slug: man.slug, type: link && link.type, mode: link && link.mode, title: link && link.title };
  if (!link || link.mode === 'copy') return { ...base, state: null };
  const verdict = (changed, missing) => ({
    ...base, changed, missing,
    state: missing.length ? 'failed' : changed.length ? (link.mode === 'live' ? 'stale' : 'update') : 'current',
  });
  try {
    if (link.type === 'env') return await require('./folio').linkState(man);
    if (link.type === 'result') {
      const dir = link.project && PID_RE.test(link.project) ? P.filesDir(link.project) : null;
      if (!dir) return { ...base, state: null };
      const m = JSON.parse((await readText(path.join(dir, 'lab', link.slug, 'bundle.json'))) || 'null');
      if (!m || (link.result_id && m.result_id && m.result_id !== link.result_id)) return { ...verdict([], [link.slug]), error: 'The result is no longer in the source report' };
      return { ...verdict((m.revision || 1) > (link.revision || 1) ? [link.slug] : [], []), latest: m.revision || 1, used: link.revision || 1 };
    }
    if (link.type === 'report') {
      await P.readMeta(link.project).catch(() => {
        throw new HttpError(404, 'The source report no longer exists');
      });
      let src = cache.get(link.project);
      if (!src) {
        src = await PC.loadSource(P.filesDir(link.project), { noLink: true });
        src.list = PC.listPieces(src);
        cache.set(link.project, src);
      }
      const changed = [];
      const missing = [];
      for (const k of link.keys || []) {
        const p = src.list.find((x) => x.key === k);
        if (!p) missing.push(k);
        else if ((await PC.pieceHash(src, p)) !== (link.versions || {})[k]) changed.push(k);
      }
      return verdict(changed, missing);
    }
    if (link.type === 'suite') {
      const s = await suiteDir();
      if (s.project !== link.project) return { ...base, state: 'failed', error: `Belongs to the project ${link.title}; open it to update` };
      const changed = [];
      const missing = [];
      for (const r of link.refs || []) {
        if (r.id) {
          const meta = JSON.parse((await readText(path.join(s.dir, 'sharebox', r.id, 'share.json'))) || 'null');
          if (!meta) missing.push(`share:${r.id}`);
          else if (meta.latest > (r.used || r.version)) changed.push(`share:${r.id}`);
        } else if (r.index && !fs.existsSync(path.join(s.dir, 'index', `${r.index}.json`))) missing.push(`index:${r.index}`);
      }
      return verdict(changed, missing);
    }
    return { ...base, state: null }; // a ZIP without a report here: nothing to follow
  } catch (e) {
    return { ...base, state: 'failed', error: e.message };
  }
}

async function linkStates(id) {
  const cache = new Map();
  const out = [];
  for (const man of await lab.list(id)) if (man.link) out.push(await linkState(id, man, cache));
  return out;
}

/** Rebuild an imported result from its source (Update / Refresh). opts.mode changes the link mode first. */
async function update(id, slug, opts = {}) {
  const man = await lab.readManifest(id, slug);
  const link = man.link;
  if (!link) throw new HttpError(400, 'This result is not linked to a source');
  const mode = opts.mode ? checkMode(opts.mode) : link.mode;
  if (link.type === 'zip' || mode === 'copy') throw new HttpError(400, 'A copy has no source to update from');
  if (link.type === 'result') {
    const res = await importPieces(id, { source: { type: 'report', project: link.project }, keys: [`result:${link.slug}`], mode }, { slug });
    return res.results[0];
  }
  if (link.type === 'report') {
    const res = await importPieces(id, { source: { type: 'report', project: link.project }, keys: link.keys, mode, title: man.title }, { slug });
    return res.results[0];
  }
  if (link.type === 'suite') {
    const res = await importSuite(id, { type: 'suite' }, link.keys, mode, { title: man.title }, { slug, prev: link, latest: true });
    return res.results[0];
  }
  if (link.type === 'env') return require('./folio').update(id, man, { ...opts, mode });
  throw new HttpError(400, 'Unknown link');
}

/** Change how an imported result follows its source (live, pin, copy) without rebuilding it. */
async function setMode(id, slug, mode) {
  const m = checkMode(mode);
  const dir = path.join(lab.labDir(id), slug);
  const man = await lab.readManifest(id, slug);
  if (!man.link) throw new HttpError(400, 'This result is not linked to a source');
  man.link.mode = m;
  if (man.source && man.source.request && man.module === 'import') man.source.request.mode = m;
  if (man.link.refs) for (const r of man.link.refs) if (r.id) r.mode = m;
  await fsp.writeFile(path.join(dir, 'bundle.json'), JSON.stringify(man, null, 2));
  return man;
}

module.exports = { sources, pieces, sourceFile, importPieces, linkStates, linkState, update, setMode, readNpy, fmtQuantity, langOf };
