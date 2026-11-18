'use strict';
// Combine several independent LaTeX projects into one.
//
// Rules (also summarised in the merge report the user sees):
//  * The first part is the "base": its document class, preamble layout and title are kept.
//  * Each part's document body goes into parts/NN-name.tex; main.tex \inputs them in order.
//  * Files are merged into the same folder tree. Identical files are stored once; a different
//    file at the same path is renamed (name-pN.ext) and that part's references are rewritten.
//  * All .bib files are merged into one. Identical entries are kept once; a different entry with
//    an existing key gets key-pN and that part's citations are rewritten.
//  * Duplicate \label names in later parts are renamed (label-pN) together with their references.
//  * Packages/definitions missing from the base are added; clashes are skipped and reported.
//  * One bibliography and one \appendix are placed after all parts.
const fs = require('fs');
const fsp = fs.promises;
const path = require('path');
const crypto = require('crypto');
const { HttpError, readText, walk, sha1 } = require('./util');
const P = require('./projects');

const STAGING = path.join(P.PROJECTS_DIR, '.staging');
const STAGE_TTL_MS = 24 * 3600 * 1000;
const ARTIFACT_RE = /\.(aux|log|out|toc|lof|lot|loa|bbl|blg|bcf|run\.xml|fls|fdb_latexmk|synctex|synctex\.gz|nav|snm|vrb|xdv|ilg|glg|alg)$/i;
const TEXT_RE = /\.(tex|ltx)$/i;
const BIB_PKGS = ['biblatex', 'natbib', 'cite', 'apacite', 'harvard', 'chicago', 'jurabib', 'achicago'];
const LOAD_LAST = ['hyperref', 'cleveref', 'bookmark', 'hypcap', 'autonum'];
const EXCLUSIVE = [['subfig', 'subcaption'], ['subfigure', 'subcaption'], ['subfig', 'subfigure']];
const GRAPHIC_EXTS = ['.pdf', '.png', '.jpg', '.mps', '.jpeg', '.jbig2', '.jb2', '.PDF', '.PNG', '.JPG', '.JPEG', '.eps'];
const NO_CHAPTER_CLASSES = /^(article|scrartcl|amsart|beamer|letter|IEEEtran|llncs|revtex4-?\d?|acmart|standalone|minimal)$/;

fs.mkdirSync(STAGING, { recursive: true });

// ====================================================================== small TeX helpers

/** Remove an unescaped % comment from one line. */
function stripLineComment(line) {
  for (let i = 0; i < line.length; i++) {
    if (line[i] === '\\') {
      i++;
      continue;
    }
    if (line[i] === '%') return line.slice(0, i);
  }
  return line;
}
const stripComments = (text) => text.split('\n').map(stripLineComment).join('\n');

/** First/last uncommented match of re in text: { index, length } or null. */
function findUncommented(text, re, last = false) {
  const g = new RegExp(re.source, re.flags.includes('g') ? re.flags : re.flags + 'g');
  let found = null;
  let m;
  while ((m = g.exec(text))) {
    const lineStart = text.lastIndexOf('\n', m.index) + 1;
    const prefix = text.slice(lineStart, m.index);
    if (stripLineComment(prefix) !== prefix) continue; // inside a comment
    found = { index: m.index, length: m[0].length };
    if (!last) break;
  }
  return found;
}

/** Read a balanced {...} group starting at text[i] === '{'. */
function readGroup(text, i) {
  if (text[i] !== '{') return null;
  let depth = 0;
  for (let j = i; j < text.length; j++) {
    const c = text[j];
    if (c === '\\') {
      j++;
      continue;
    }
    if (c === '{') depth++;
    else if (c === '}' && --depth === 0) return { content: text.slice(i + 1, j), end: j + 1 };
  }
  return null;
}

/** Argument of \cmd (skipping optional [...] args), e.g. title text. */
function commandArg(code, cmd) {
  const m = new RegExp(`\\\\${cmd}\\*?\\s*(?:\\[[^\\]]*\\]\\s*)*`).exec(code);
  if (!m) return null;
  const g = readGroup(code, m.index + m[0].length);
  return g ? g.content : null;
}

const norm = (s) => String(s).replace(/%.*$/gm, '').replace(/\s+/g, ' ').trim();
const plainText = (s) =>
  String(s || '')
    .replace(/\\\\(\[[^\]]*\])?/g, ' ')
    .replace(/\\(and|thanks\{[^}]*\}|footnote\{[^}]*\})/g, ',')
    .replace(/\\[a-zA-Z@]+\*?/g, '')
    .replace(/[{}~$]/g, ' ')
    .replace(/\s+/g, ' ')
    .replace(/\s+,/g, ',')
    .trim();

function slugify(s) {
  const t = String(s)
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/\.zip$/, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 40);
  return t || 'part';
}

function withSuffix(rel, suffix) {
  const slash = rel.lastIndexOf('/');
  const dot = rel.lastIndexOf('.');
  return dot > slash ? rel.slice(0, dot) + suffix + rel.slice(dot) : rel + suffix;
}

const posixNorm = (p) => path.posix.normalize(p.replace(/\\/g, '/')).replace(/^(\.\/)+/, '');

// ====================================================================== preamble parsing

/** Split a preamble into statements: lines grouped until braces/brackets balance. */
function splitStatements(text) {
  const lines = text.split(/\r?\n/);
  const out = [];
  let buf = [];
  let depth = 0;
  let bdepth = 0;
  let makeat = false;
  const flush = () => {
    if (!buf.length) return;
    const raw = buf.join('\n');
    out.push({ raw, code: stripComments(raw) });
    buf = [];
    depth = 0;
    bdepth = 0;
  };
  for (const line of lines) {
    const code = stripLineComment(line);
    buf.push(line);
    if (/\\makeatletter/.test(code)) makeat = true;
    if (makeat) {
      if (/\\makeatother/.test(code)) {
        makeat = false;
        flush();
      }
      continue;
    }
    for (let i = 0; i < code.length; i++) {
      const c = code[i];
      if (c === '\\') {
        i++;
        continue;
      }
      if (c === '{') depth++;
      else if (c === '}') depth--;
      else if (depth === 0 && c === '[') bdepth++;
      else if (depth === 0 && c === ']') bdepth = Math.max(0, bdepth - 1);
    }
    if (depth <= 0 && bdepth <= 0) flush();
  }
  flush();
  return out.map(classify);
}

const PKG_RE = /\\(?:usepackage|RequirePackage)\s*(?:\[([^\]]*)\])?\s*\{([^}]*)\}(?:\s*\[[^\]]*\])?/g;

function classify(st) {
  const c = st.code.trim();
  if (!c) return { ...st, kind: 'blank' };
  if (/^\\documentclass\b/.test(c)) {
    const m = /\\documentclass\s*(?:\[([^\]]*)\])?\s*\{([^}]*)\}/.exec(c);
    return { ...st, kind: 'class', cls: m ? m[2].trim() : '', clsOpts: m ? (m[1] || '').trim() : '' };
  }
  if (c.replace(PKG_RE, '').trim() === '' && PKG_RE.test(c)) {
    PKG_RE.lastIndex = 0;
    const pkgs = [];
    for (const m of c.matchAll(PKG_RE)) {
      for (const name of m[2].split(',').map((x) => x.trim()).filter(Boolean)) pkgs.push({ name, opts: (m[1] || '').replace(/\s+/g, ' ').trim() });
    }
    return { ...st, kind: 'packages', pkgs };
  }
  PKG_RE.lastIndex = 0;
  let m;
  if ((m = /^\\(title|author|date|subtitle|institute)\b/.exec(c))) return { ...st, kind: 'meta', field: m[1], value: commandArg(c, m[1]) };
  if (/^\\graphicspath\b/.test(c)) {
    const g = commandArg(c, 'graphicspath') || '';
    return { ...st, kind: 'graphicspath', paths: [...g.matchAll(/\{([^}]*)\}/g)].map((x) => x[1]) };
  }
  if (/^\\addbibresource\b/.test(c)) return { ...st, kind: 'bibresource', file: commandArg(c, 'addbibresource') };
  if (/^\\bibliography\b/.test(c)) return { ...st, kind: 'bibliography', file: commandArg(c, 'bibliography') };
  if (/^\\bibliographystyle\b/.test(c)) return { ...st, kind: 'bibstyle', style: commandArg(c, 'bibliographystyle') };
  if ((m = /^\\(usetikzlibrary|usepgfplotslibrary)\s*\{([^}]*)\}\s*$/.exec(c)))
    return { ...st, kind: 'library', lib: m[1], names: m[2].split(',').map((x) => x.trim()).filter(Boolean) };
  if (/^\\pgfplotsset\s*\{\s*compat\s*=/.test(c)) return { ...st, kind: 'compat' };
  const key = definitionKey(c);
  if (key) return { ...st, kind: 'def', key };
  return { ...st, kind: 'other' };
}

function definitionKey(c) {
  let m;
  if ((m = /^\\(?:newcommand|renewcommand|providecommand|DeclareRobustCommand|DeclareMathOperator|NewDocumentCommand|RenewDocumentCommand)\*?\s*\{?\s*\\([A-Za-z@]+)/.exec(c))) return 'cmd:' + m[1];
  if ((m = /^\\(?:def|gdef|edef|xdef|let)\s*\\([A-Za-z@]+)/.exec(c))) return 'cmd:' + m[1];
  if ((m = /^\\(?:newenvironment|renewenvironment|NewDocumentEnvironment)\*?\s*\{([^}]+)\}/.exec(c))) return 'env:' + m[1];
  if ((m = /^\\newtheorem\*?\s*\{([^}]+)\}/.exec(c))) return 'env:' + m[1];
  if ((m = /^\\definecolor\s*\{([^}]+)\}/.exec(c))) return 'color:' + m[1];
  if ((m = /^\\colorlet\s*\{([^}]+)\}/.exec(c))) return 'color:' + m[1];
  if ((m = /^\\newcolumntype\s*\{?(.)\}?/.exec(c))) return 'coltype:' + m[1];
  if ((m = /^\\newlength\s*\{?\\([A-Za-z@]+)/.exec(c))) return 'len:' + m[1];
  if ((m = /^\\newcounter\s*\{([^}]+)\}/.exec(c))) return 'counter:' + m[1];
  if ((m = /^\\newacronym\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}/.exec(c))) return 'acro:' + m[1];
  return null;
}

// ====================================================================== .bib parsing

function parseBib(text, file) {
  const out = [];
  const re = /@\s*([a-zA-Z]+)\s*([{(])/g;
  let m;
  while ((m = re.exec(text))) {
    const type = m[1].toLowerCase();
    const open = m[2];
    const close = open === '{' ? '}' : ')';
    let depth = 0;
    let end = -1;
    for (let j = m.index + m[0].length - 1; j < text.length; j++) {
      const c = text[j];
      if (c === '{' || (open === '(' && c === '(' && depth === 0)) depth++;
      else if (c === '}' || (open === '(' && c === ')' && depth === 1)) {
        depth--;
        if (depth === 0 && c === close) {
          end = j + 1;
          break;
        }
      }
    }
    if (end < 0) break;
    const raw = text.slice(m.index, end);
    re.lastIndex = end;
    if (type === 'comment') continue;
    if (type === 'string' || type === 'preamble') {
      out.push({ kind: type, raw, norm: norm(raw) });
      continue;
    }
    const body = raw.slice(m[0].length);
    const comma = body.indexOf(',');
    if (comma < 0) continue;
    const key = body.slice(0, comma).trim();
    out.push({ kind: 'entry', type, key, raw, norm: norm(raw.replace(key, '')).toLowerCase(), file });
  }
  return out;
}

// ====================================================================== loading a part

async function loadPart(dir, { name, source, engine: metaEngine } = {}) {
  const all = (await walk(dir)).filter((f) => !f.isDir);
  const mainFile = await P.findMainFile(dir);
  const part = { name, source, dir, mainFile, files: [], tex: new Map(), problems: [] };
  if (!mainFile) {
    part.problems.push('No .tex file with \\documentclass was found.');
    return part;
  }
  const mainText = (await readText(path.join(dir, mainFile))) || '';
  const begin = findUncommented(mainText, /\\begin\s*\{document\}/);
  const end = findUncommented(mainText, /\\end\s*\{document\}/, true);
  if (!begin || !end || end.index < begin.index) {
    part.problems.push(`${mainFile} has no \\begin{document} … \\end{document}.`);
    return part;
  }
  part.preambleText = mainText.slice(0, begin.index);
  part.body = mainText.slice(begin.index + begin.length, end.index).replace(/^\r?\n/, '');
  part.statements = splitStatements(part.preambleText);
  const cls = part.statements.find((s) => s.kind === 'class');
  part.docClass = cls ? cls.cls : '';
  part.engine = metaEngine && metaEngine !== 'pdflatex' ? metaEngine : P.engineFromSource(mainText);
  part.packages = new Map();
  for (const s of part.statements) if (s.kind === 'packages') for (const p of s.pkgs) part.packages.set(p.name, p.opts);
  part.graphicspath = part.statements.filter((s) => s.kind === 'graphicspath').flatMap((s) => s.paths);
  part.bibSystem = part.packages.has('biblatex')
    ? 'biblatex'
    : /\\bibliography\s*\{/.test(stripComments(mainText)) || ['natbib', 'cite', 'apacite'].some((p) => part.packages.has(p))
      ? 'bibtex'
      : null;
  const job = path.posix.basename(mainFile).replace(/\.[^.]+$/, '');
  part.bibEntries = [];
  for (const f of all) {
    if (f.rel === mainFile) continue;
    if (ARTIFACT_RE.test(f.rel)) continue;
    if (f.rel.toLowerCase() === (job + '.pdf').toLowerCase()) continue; // the part's own compiled output
    if (f.rel === 'merge-report.txt') continue;
    part.files.push({ rel: f.rel, abs: f.abs, size: f.size });
    if (TEXT_RE.test(f.rel)) part.tex.set(f.rel, (await readText(f.abs)) || '');
    if (/\.bib$/i.test(f.rel)) part.bibEntries.push(...parseBib((await readText(f.abs)) || '', f.rel));
  }
  // Also look at preamble files pulled in with \input (packages/definitions there matter for clashes).
  part.extraPreamble = [];
  for (const s of part.statements) {
    const m = /^\\(?:input|include)\s*\{([^}]+)\}/.exec(s.code.trim());
    if (!m) continue;
    const ref = posixNorm(m[1]);
    const t = part.tex.get(ref) ?? part.tex.get(ref + '.tex');
    if (t != null) part.extraPreamble.push(...splitStatements(t));
  }
  return part;
}

/** Short summary for the UI card. */
async function summarize(part) {
  const meta = (f) => part.statements?.find((s) => s.kind === 'meta' && s.field === f)?.value;
  const sections = [];
  const scan = (text) => {
    for (const m of stripComments(text).matchAll(/\\(chapter|section)\*?\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}/g)) sections.push(plainText(m[2]));
  };
  if (part.body) {
    scan(part.body);
    for (const m of stripComments(part.body).matchAll(/\\(?:input|include)\s*\{([^}]+)\}/g)) {
      const ref = posixNorm(m[1]);
      const t = part.tex.get(ref) ?? part.tex.get(ref + '.tex');
      if (t) scan(t);
    }
  }
  return {
    mainFile: part.mainFile,
    engine: part.engine || 'pdflatex',
    docClass: part.docClass || '',
    title: plainText(meta('title')),
    author: plainText(meta('author')),
    sections: sections.slice(0, 12),
    sectionCount: sections.length,
    usesChapters: !!part.body && [part.body, ...part.tex.values()].some((t) => /\\chapter\b/.test(stripComments(t))),
    classHasChapters: !!part.docClass && !NO_CHAPTER_CLASSES.test(part.docClass),
    counts: {
      files: part.files.length,
      images: part.files.filter((f) => /\.(png|jpe?g|pdf|eps|gif|svg)$/i.test(f.rel)).length,
      references: part.bibEntries?.filter((e) => e.kind === 'entry').length || 0,
    },
    bibSystem: part.bibSystem || null,
    problems: part.problems,
  };
}

// ====================================================================== staging

async function cleanupStaging() {
  for (const d of await fsp.readdir(STAGING).catch(() => [])) {
    const p = path.join(STAGING, d);
    try {
      const st = await fsp.stat(p);
      if (Date.now() - st.mtimeMs > STAGE_TTL_MS) await fsp.rm(p, { recursive: true, force: true });
    } catch {
      /* ignore */
    }
  }
}

async function stageZip(name, buffer) {
  await cleanupStaging();
  const sid = crypto.randomBytes(6).toString('hex');
  const dir = path.join(STAGING, sid);
  try {
    await P.extractZip(buffer, path.join(dir, 'files'));
  } catch (e) {
    await fsp.rm(dir, { recursive: true, force: true });
    throw e;
  }
  const info = { stage: sid, name: String(name || 'Project').replace(/\.zip$/i, ''), source: name };
  await fsp.writeFile(path.join(dir, 'stage.json'), JSON.stringify(info));
  const part = await loadPart(path.join(dir, 'files'), info);
  return { ...info, ...(await summarize(part)) };
}

async function analyzeProject(id) {
  const meta = await P.readMeta(id);
  const part = await loadPart(P.filesDir(id), { name: meta.name, source: `project "${meta.name}"`, engine: meta.engine });
  return { project: id, name: meta.name, source: `Folio project`, ...(await summarize(part)) };
}

async function removeStage(sid) {
  if (!/^[a-f0-9]{12}$/.test(sid)) throw new HttpError(400, 'Bad stage id');
  await fsp.rm(path.join(STAGING, sid), { recursive: true, force: true });
}

async function resolvePartRef(ref) {
  if (ref && ref.stage) {
    if (!/^[a-f0-9]{12}$/.test(ref.stage)) throw new HttpError(400, 'Bad stage id');
    const dir = path.join(STAGING, ref.stage);
    const info = JSON.parse((await readText(path.join(dir, 'stage.json'))) || 'null');
    if (!info) throw new HttpError(410, 'An uploaded ZIP has expired. Please add it again.');
    return loadPart(path.join(dir, 'files'), { name: ref.name || info.name, source: info.source });
  }
  if (ref && ref.project) {
    const meta = await P.readMeta(ref.project);
    return loadPart(P.filesDir(ref.project), { name: ref.name || meta.name, source: `Folio project "${meta.name}"`, engine: meta.engine });
  }
  throw new HttpError(400, 'Invalid part');
}

// ====================================================================== reference rewriting

const LABEL_CMD_RE = /\\(label|ref|eqref|cref|Cref|autoref|Autoref|pageref|nameref|vref|Vref|cpageref|Cpageref|labelcref|subref|zlabel|zref|crefrange|Crefrange)(\*?)\s*\{([^}]*)\}/g;
const CITE_CMD_RE = /\\([a-zA-Z]*cite[a-zA-Z]*|nocite)(\*?)((?:\s*\[[^\]]*\])*)\s*\{([^}]*)\}/g;

function renameLabelsAndKeys(text, labelMap, keyMap) {
  if (labelMap.size) {
    text = text.replace(LABEL_CMD_RE, (all, cmd, star, arg) => `\\${cmd}${star}{${arg.split(',').map((k) => labelMap.get(k.trim()) ?? k).join(',')}}`);
    text = text.replace(/\\hyperref\s*\[([^\]]*)\]/g, (all, k) => `\\hyperref[${labelMap.get(k.trim()) ?? k}]`);
  }
  if (keyMap.size) {
    text = text.replace(CITE_CMD_RE, (all, cmd, star, opts, arg) =>
      arg.includes('\\') ? all : `\\${cmd}${star}${opts}{${arg.split(',').map((k) => { const t = k.trim(); return keyMap.has(t) ? k.replace(t, keyMap.get(t)) : k; }).join(',')}}`
    );
  }
  return text;
}

function collectLabels(text) {
  const out = new Set();
  for (const m of stripComments(text).matchAll(/\\(?:label|zlabel)\s*\{([^}]+)\}/g)) out.add(m[1].trim());
  return out;
}

/** File lookup helpers: set = Map(lowercased rel -> rel). */
function lookup(set, rel) {
  return set.get(posixNorm(rel).toLowerCase()) || null;
}
function resolveGraphic(ref, gpaths, set) {
  const dirs = ['', ...gpaths];
  const hasExt = /\.[A-Za-z0-9]{2,5}$/.test(ref);
  for (const d of dirs) {
    const base = posixNorm((d ? d.replace(/\/?$/, '/') : '') + ref);
    if (hasExt) {
      const hit = lookup(set, base);
      if (hit) return hit;
    }
    for (const e of GRAPHIC_EXTS) {
      const hit = lookup(set, base + e);
      if (hit) return hit;
    }
  }
  return null;
}
function resolveTex(ref, set) {
  return lookup(set, ref) || lookup(set, ref + '.tex');
}

/**
 * Rewrite file references whose target would resolve differently in the combined project.
 * intended(ref, kind) -> final rel or null; combined(ref, kind) -> rel or null.
 */
function rewriteFileRefs(text, intended, combined, onRewrite) {
  const fix = (ref, kind, style) => {
    const r = ref.trim();
    if (!r || /[#\\]/.test(r)) return null;
    const want = intended(r, kind);
    if (!want) return null;
    const got = combined(r, kind);
    if (got && got.toLowerCase() === want.toLowerCase()) return null;
    let out = want;
    if (kind === 'tex' && (style === 'include' || !/\.tex$/i.test(r))) out = want.replace(/\.tex$/i, '');
    onRewrite(r, out);
    return out;
  };
  // \includegraphics, \input, \include, listings, pdfpages, ...
  text = text.replace(
    /\\(includegraphics|input|include|subfile|InputIfFileExists|lstinputlisting|includepdf|verbatiminput|includesvg|includestandalone)(\*?)(\s*(?:\[[^\]]*\]\s*)*)\{([^}\n]+)\}/g,
    (all, cmd, star, opts, ref) => {
      const kind = cmd === 'includegraphics' ? 'graphic' : ['input', 'include', 'subfile', 'InputIfFileExists', 'includestandalone'].includes(cmd) ? 'tex' : 'exact';
      const out = fix(ref, kind, cmd);
      return out ? `\\${cmd}${star}${opts}{${out}}` : all;
    }
  );
  // \inputminted{lang}{file}
  text = text.replace(/\\inputminted(\s*(?:\[[^\]]*\]\s*)?)\{([^}]*)\}\s*\{([^}\n]+)\}/g, (all, opts, lang, ref) => {
    const out = fix(ref, 'exact');
    return out ? `\\inputminted${opts}{${lang}}{${out}}` : all;
  });
  // pgfplots: \addplot table[...]{file}, \pgfplotstableread{file}, \pgfplotstabletypeset[...]{file}
  text = text.replace(/(\btable|\\pgfplotstableread|\\pgfplotstabletypeset)(\s*(?:\[[^\]]*\]\s*)?)\{([^}\n\\]+)\}/g, (all, cmd, opts, ref) => {
    const out = fix(ref, 'exact');
    return out ? `${cmd}${opts}{${out}}` : all;
  });
  return text;
}

// ====================================================================== combine

async function combine({ name, parts: refs, options = {} }) {
  if (!Array.isArray(refs) || refs.length < 2) throw new HttpError(400, 'Choose at least two projects to combine.');
  if (refs.length > 50) throw new HttpError(400, 'Too many parts.');
  const parts = [];
  for (const [i, ref] of refs.entries()) {
    const part = await resolvePartRef(ref);
    if (part.problems.length) throw new HttpError(400, `"${part.name}": ${part.problems.join(' ')}`);
    part.num = i + 1;
    part.suffix = `-p${i + 1}`;
    part.slug = slugify(part.name);
    parts.push(part);
  }
  const base = parts[0];
  const R = {
    parts: parts.map((p) => ({ num: p.num, name: p.name, source: p.source, mainFile: p.mainFile })),
    renamedFiles: [],
    renamedLabels: [],
    renamedKeys: [],
    rewrittenRefs: [],
    addedPackages: [],
    skipped: [],
    removed: [],
    notes: [],
    stats: { copied: 0, shared: 0, references: 0, duplicateReferences: 0 },
  };
  const nn = (p) => String(p.num).padStart(2, '0');
  const partFile = (p) => `parts/${nn(p)}-${p.slug}.tex`;
  const appendixFile = (p) => `parts/${nn(p)}-${p.slug}-appendix.tex`;

  // ---------------------------------------------------------- bibliography system
  const sysPart = parts.find((p) => p.bibSystem);
  const bibSystem = sysPart ? sysPart.bibSystem : null;
  const anyBib = parts.some((p) => p.files.some((f) => /\.bib$/i.test(f.rel)));
  const mergeBib = !!bibSystem && anyBib;
  let bibPath = null;
  if (mergeBib) {
    const fromStatements = (p) => {
      const s = p.statements.find((x) => x.kind === 'bibresource' || x.kind === 'bibliography');
      if (s && s.file) return s.file.split(',')[0].trim();
      const m = /\\(?:bibliography|addbibresource)\s*(?:\[[^\]]*\])?\s*\{([^},]+)/.exec(stripComments(p.body));
      return m ? m[1].trim() : null;
    };
    let candidate = fromStatements(sysPart) || 'references.bib';
    if (!/\.bib$/i.test(candidate)) candidate += '.bib';
    bibPath = posixNorm(candidate);
  }
  for (const p of parts) {
    if (p.bibSystem && bibSystem && p.bibSystem !== bibSystem)
      R.notes.push(`Part ${p.num} "${p.name}" uses ${p.bibSystem === 'biblatex' ? 'biblatex' : 'BibTeX'}, but the combined document uses ${bibSystem === 'biblatex' ? 'biblatex (from part ' + sysPart.num + ')' : 'BibTeX (from part ' + sysPart.num + ')'}. Check its citation commands${bibSystem === 'biblatex' ? ' (\\citep/\\citet need biblatex\'s natbib=true option)' : ' (\\autocite, \\parencite, \\textcite are biblatex-only)'}.`);
  }

  // ---------------------------------------------------------- labels and citation keys
  const labelOwner = new Map();
  const bibKeys = new Map(); // lower(key) -> { norm, part }
  const bibOut = [];
  const bibSeen = new Set();
  for (const p of parts) {
    p.labelMap = new Map();
    p.keyMap = new Map();
    const labels = new Set([...collectLabels(p.body), ...[...p.tex.values()].flatMap((t) => [...collectLabels(t)])]);
    for (const l of labels) {
      if (labelOwner.has(l)) {
        let n = l + p.suffix;
        while (labelOwner.has(n) || labels.has(n)) n += 'x';
        p.labelMap.set(l, n);
        labelOwner.set(n, p.num);
        R.renamedLabels.push({ part: p.num, from: l, to: n });
      } else labelOwner.set(l, p.num);
    }
    if (mergeBib) {
      for (const e of p.bibEntries) {
        if (e.kind !== 'entry') {
          if (!bibSeen.has(e.norm)) {
            bibSeen.add(e.norm);
            bibOut.push(e.raw);
          }
          continue;
        }
        const k = e.key.toLowerCase();
        const ex = bibKeys.get(k);
        if (!ex) {
          bibKeys.set(k, { norm: e.norm, part: p.num });
          bibOut.push(e.raw);
          R.stats.references++;
        } else if (ex.norm === e.norm || ex.part === p.num) {
          if (ex.part !== p.num) R.stats.duplicateReferences++;
        } else {
          let nk = e.key + p.suffix;
          while (bibKeys.has(nk.toLowerCase())) nk += 'x';
          bibKeys.set(nk.toLowerCase(), { norm: e.norm, part: p.num });
          bibOut.push(e.raw.replace(e.key, nk));
          p.keyMap.set(e.key, nk);
          R.stats.references++;
          R.renamedKeys.push({ part: p.num, from: e.key, to: nk });
        }
      }
    }
    p.body = renameLabelsAndKeys(p.body, p.labelMap, p.keyMap);
    for (const [rel, t] of p.tex) p.tex.set(rel, renameLabelsAndKeys(t, p.labelMap, p.keyMap));
  }

  // ---------------------------------------------------------- bodies: front matter, bibliography, appendix
  let bibPrint = null;
  let bibStyle = null;
  let bibAfterAppendix = false;
  for (const p of parts) {
    let body = p.body;
    const code = stripComments(body);
    const appIdx = findUncommented(body, /^[ \t]*\\appendix\b/m);
    const printIdx = findUncommented(body, /\\printbibliography\b|\\bibliography\s*\{/);
    if (p === (sysPart || base) && appIdx && printIdx && printIdx.index > appIdx.index) bibAfterAppendix = true;
    const removeCmd = (re, keep) => {
      body = body.replace(re, (m, ...rest) => {
        const offset = rest[rest.length - 2];
        const lineStart = body.lastIndexOf('\n', offset) + 1;
        if (stripLineComment(body.slice(lineStart, offset)) !== body.slice(lineStart, offset)) return m;
        if (keep) keep(m);
        R.removed.push({ part: p.num, cmd: m.trim() });
        return '';
      });
    };
    if (bibSystem) {
      removeCmd(/\\printbibliography\s*(\[[^\]]*\])?/g, (m) => {
        if (p === sysPart || (!bibPrint && bibSystem === 'biblatex')) bibPrint = bibPrint || m.trim();
      });
      removeCmd(/\\bibliographystyle\s*\{[^}]*\}/g, (m) => {
        if (!bibStyle || p === sysPart) bibStyle = bibStyle && p !== sysPart ? bibStyle : commandArg(m, 'bibliographystyle');
      });
      removeCmd(/\\bibliography\s*\{[^}]*\}/g);
      removeCmd(/\\addbibresource\s*(\[[^\]]*\])?\s*\{[^}]*\}/g);
    }
    if (p !== base) {
      removeCmd(/\\(maketitle|tableofcontents|listoffigures|listoftables)\b/g);
      if (/\\begin\s*\{titlepage\}/.test(code)) R.notes.push(`Part ${p.num} "${p.name}" contains its own title page; you may want to remove it.`);
    }
    if (p !== base && NO_CHAPTER_CLASSES.test(base.docClass) && [code, ...p.tex.values()].some((t) => /\\chapter\b/.test(stripComments(t))))
      R.notes.push(
        `Part ${p.num} "${p.name}" uses \\chapter, but the "${base.docClass}" class of part 1 has no chapters, so it will not compile. Put a part with chapters (class report/book/scrbook/scrreprt) first, or change its \\chapter commands to \\section.`
      );
    const app = findUncommented(body, /^[ \t]*\\appendix\b[^\n]*\n?/m);
    if (app) {
      p.appendix = body.slice(app.index + app.length);
      body = body.slice(0, app.index);
    }
    p.body = body.replace(/^(?:[ \t]*\r?\n)+/, '').replace(/\s+$/, '') + '\n';
    for (const [rel, t] of p.tex) {
      if (!bibSystem) continue;
      // Bibliography commands inside \input'd files would print a second reference list.
      if (/\\printbibliography\b|\\bibliography\s*\{/.test(stripComments(t)))
        R.notes.push(`Part ${p.num}: ${rel} prints a bibliography itself; the combined document already prints one at the end.`);
    }
  }
  if (bibSystem === 'biblatex') bibPrint = bibPrint || '\\printbibliography';
  if (bibSystem === 'bibtex') bibStyle = bibStyle || (sysPart.statements.find((s) => s.kind === 'bibstyle')?.style ?? 'plain');

  // ---------------------------------------------------------- file placement
  const placed = new Map(); // lower(rel) -> { rel, data, hash, owner }
  const reserve = (rel, owner = 0) => placed.set(rel.toLowerCase(), { rel, reserved: true, owner });
  reserve('main.tex');
  reserve('merge-report.txt');
  if (bibPath) reserve(bibPath);
  for (const p of parts) {
    reserve(partFile(p));
    if (p.appendix) reserve(appendixFile(p));
  }
  for (const p of parts) {
    p.fileMap = new Map();
    p.owned = new Set();
    for (const f of p.files) {
      if (mergeBib && /\.bib$/i.test(f.rel)) continue;
      const isTex = p.tex.has(f.rel);
      const data = isTex ? p.tex.get(f.rel) : await fsp.readFile(f.abs);
      const hash = sha1(data);
      const ex = placed.get(f.rel.toLowerCase());
      let target = f.rel;
      if (ex && !ex.reserved && ex.hash === hash) {
        p.fileMap.set(f.rel, ex.rel);
        R.stats.shared++;
        continue;
      }
      if (ex) {
        let n = 1;
        target = withSuffix(f.rel, p.suffix);
        while (placed.has(target.toLowerCase())) target = withSuffix(f.rel, `${p.suffix}-${++n}`);
        R.renamedFiles.push({ part: p.num, from: f.rel, to: target });
      }
      placed.set(target.toLowerCase(), { rel: target, data, hash, owner: p.num, isTex });
      p.fileMap.set(f.rel, target);
      if (isTex) p.owned.add(target);
      R.stats.copied++;
    }
  }

  // ---------------------------------------------------------- preamble merge
  const known = { pkgs: new Map(), defs: new Map(), other: new Set(), libs: new Map(), compat: false };
  const learn = (sts, partNum) => {
    for (const s of sts) {
      if (s.kind === 'packages') for (const pk of s.pkgs) if (!known.pkgs.has(pk.name)) known.pkgs.set(pk.name, { opts: pk.opts, part: partNum });
      if (s.kind === 'def' && !known.defs.has(s.key)) known.defs.set(s.key, norm(s.code));
      if (s.kind === 'other') known.other.add(norm(s.code));
      if (s.kind === 'library') for (const n of s.names) known.libs.set(s.lib + ':' + n, true);
      if (s.kind === 'compat') known.compat = true;
    }
  };
  learn(base.statements, 1);
  learn(base.extraPreamble, 1);

  const earlyPkgs = [];
  const latePkgs = [];
  const extras = []; // { part, text }
  const gpaths = [...base.graphicspath];
  const authors = [];
  const addAuthor = (a) => {
    for (const piece of String(a || '').split(/\\and\b/)) {
      const t = piece.trim();
      if (t && !authors.some((x) => norm(x) === norm(t))) authors.push(t);
    }
  };
  addAuthor(base.statements.find((s) => s.kind === 'meta' && s.field === 'author')?.value);
  let title = base.statements.find((s) => s.kind === 'meta' && s.field === 'title') ? null : undefined;
  let engine = base.engine || 'pdflatex';
  const babelLangs = (base.packages.get('babel') || '').split(',').map((x) => x.trim()).filter(Boolean);
  let babelChanged = false;

  for (const p of parts.slice(1)) {
    if (p.docClass && base.docClass && p.docClass !== base.docClass)
      R.notes.push(`Part ${p.num} "${p.name}" was written for the "${p.docClass}" class; the combined document uses "${base.docClass}" from part 1.`);
    if (p.engine && p.engine !== 'pdflatex' && engine === 'pdflatex') {
      engine = p.engine;
      R.notes.push(`Part ${p.num} needs ${p.engine === 'xelatex' ? 'XeLaTeX' : 'LuaLaTeX'} (fontspec/unicode), so the combined project compiles with it. Check fonts and inputenc/fontenc lines.`);
    }
    for (const g of p.graphicspath) if (!gpaths.includes(g)) gpaths.push(g);
    for (const s of p.statements) {
      if (s.kind === 'packages') {
        for (const pk of s.pkgs) {
          const have = known.pkgs.get(pk.name);
          if (BIB_PKGS.includes(pk.name) && bibSystem) {
            const sysPkgs = [...known.pkgs.keys()].filter((n) => BIB_PKGS.includes(n));
            if (!have && sysPkgs.length && !sysPkgs.includes(pk.name)) {
              R.skipped.push({ part: p.num, what: `\\usepackage{${pk.name}}`, why: `conflicts with ${sysPkgs.join(', ')}` });
              continue;
            }
          }
          const excl = EXCLUSIVE.find(([a, b]) => (pk.name === a && known.pkgs.has(b)) || (pk.name === b && known.pkgs.has(a)));
          if (excl && !have) {
            R.skipped.push({ part: p.num, what: `\\usepackage{${pk.name}}`, why: `cannot be combined with ${excl.find((x) => x !== pk.name)}` });
            continue;
          }
          if (have) {
            if (!pk.opts || norm(pk.opts) === norm(have.opts)) continue;
            if (pk.name === 'babel') {
              for (const l of pk.opts.split(',').map((x) => x.trim()).filter(Boolean)) {
                if (!babelLangs.includes(l)) {
                  babelLangs.unshift(l); // keep the base's main language last
                  babelChanged = true;
                }
              }
              continue;
            }
            const haveSet = new Set(have.opts.split(',').map((x) => norm(x)).filter(Boolean));
            const missing = pk.opts.split(',').map((x) => norm(x)).filter((x) => x && !haveSet.has(x));
            if (missing.length) R.skipped.push({ part: p.num, what: `options [${missing.join(', ')}] for ${pk.name}`, why: `part ${have.part} already loads it as [${have.opts || 'no options'}]` });
            continue;
          }
          known.pkgs.set(pk.name, { opts: pk.opts, part: p.num });
          const line = `\\usepackage${pk.opts ? `[${pk.opts}]` : ''}{${pk.name}}`;
          (LOAD_LAST.includes(pk.name) ? latePkgs : earlyPkgs).push({ part: p.num, line, name: pk.name });
          R.addedPackages.push({ part: p.num, pkg: pk.name });
        }
        continue;
      }
      if (s.kind === 'meta') {
        if (s.field === 'author') addAuthor(s.value);
        if (s.field === 'title' && title === undefined) title = s.raw;
        continue;
      }
      if (['blank', 'class', 'graphicspath', 'bibresource', 'bibliography', 'bibstyle'].includes(s.kind)) continue;
      if (s.kind === 'compat') {
        if (!known.compat) {
          known.compat = true;
          extras.push({ part: p.num, text: s.raw.trim() });
        }
        continue;
      }
      if (s.kind === 'library') {
        const fresh = s.names.filter((n) => !known.libs.has(s.lib + ':' + n));
        fresh.forEach((n) => known.libs.set(s.lib + ':' + n, true));
        if (fresh.length) extras.push({ part: p.num, text: `\\${s.lib}{${fresh.join(',')}}` });
        continue;
      }
      if (s.kind === 'def') {
        const have = known.defs.get(s.key);
        if (have === undefined) {
          known.defs.set(s.key, norm(s.code));
          extras.push({ part: p.num, text: s.raw.trim() });
        } else if (have !== norm(s.code)) {
          R.skipped.push({ part: p.num, what: s.code.trim().split('\n')[0].slice(0, 90), why: `${s.key.replace(/^\w+:/, '')} is already defined differently by an earlier part` });
        }
        continue;
      }
      if (known.other.has(norm(s.code))) continue;
      known.other.add(norm(s.code));
      extras.push({ part: p.num, text: s.raw.trim() });
    }
    learn(p.extraPreamble, p.num);
  }
  if (title === undefined) title = null;

  // ---------------------------------------------------------- file reference rewriting
  const combinedSet = new Map();
  for (const v of placed.values()) combinedSet.set(v.rel.toLowerCase(), v.rel);
  const combinedResolve = (ref, kind) =>
    kind === 'graphic' ? resolveGraphic(ref, gpaths, combinedSet) : kind === 'tex' ? resolveTex(ref, combinedSet) : lookup(combinedSet, ref);
  for (const p of parts) {
    const own = new Map(p.files.map((f) => [f.rel.toLowerCase(), f.rel]));
    const intended = (ref, kind) => {
      const hit = kind === 'graphic' ? resolveGraphic(ref, p.graphicspath, own) : kind === 'tex' ? resolveTex(ref, own) : lookup(own, ref);
      return hit ? p.fileMap.get(hit) || null : null;
    };
    const log = (where) => (from, to) => R.rewrittenRefs.push({ part: p.num, file: where, from, to });
    p.body = rewriteFileRefs(p.body, intended, combinedResolve, log(p.mainFile));
    if (p.appendix) p.appendix = rewriteFileRefs(p.appendix, intended, combinedResolve, log(p.mainFile));
    for (const e of extras.filter((x) => x.part === p.num)) e.text = rewriteFileRefs(e.text, intended, combinedResolve, log('preamble'));
    if (p === base) for (const s of base.statements) s.raw = rewriteFileRefs(s.raw, intended, combinedResolve, log('preamble'));
    for (const [orig, target] of p.fileMap) {
      if (!p.owned.has(target)) continue;
      const entry = placed.get(target.toLowerCase());
      entry.data = rewriteFileRefs(entry.data, intended, combinedResolve, log(target));
    }
  }

  // ---------------------------------------------------------- assemble main.tex
  const out = [];
  const date = new Date().toISOString().slice(0, 10);
  out.push(`% Combined with Folio on ${date} from ${parts.length} projects:`);
  for (const p of parts) out.push(`%   ${p.num}. ${p.name}  ->  ${partFile(p)}`);
  out.push('% To change the order, move the \\input lines in the document body below.');
  out.push('% See merge-report.txt for everything that was renamed or skipped.');
  out.push('');
  const lastPkgIdx = base.statements.reduce((acc, s, i) => (s.kind === 'packages' ? i : acc), -1);
  const firstLateIdx = base.statements.findIndex((s) => s.kind === 'packages' && s.pkgs.some((pk) => LOAD_LAST.includes(pk.name)));
  const earlyAt = firstLateIdx >= 0 ? firstLateIdx : lastPkgIdx;
  const gpLine = gpaths.length ? `\\graphicspath{${gpaths.map((g) => `{${g}}`).join('')}}` : null;
  let gpDone = false;
  let bibResDone = false;
  const mergedAuthor = options.mergeAuthors !== false && authors.length > 1 ? `\\author{${authors.join(' \\and ')}}` : null;
  let authorDone = false;
  const emitEarly = () => {
    if (!earlyPkgs.length) return;
    out.push('% --- packages added from other parts ---');
    for (const e of earlyPkgs) out.push(`${e.line} % part ${e.part}`);
  };
  const emitLate = () => {
    for (const e of latePkgs) out.push(`${e.line} % part ${e.part}`);
  };
  base.statements.forEach((s, i) => {
    if (i === earlyAt && firstLateIdx >= 0) emitEarly();
    if (s.kind === 'graphicspath') {
      if (!gpDone && gpLine) out.push(gpLine);
      gpDone = true;
      return;
    }
    if (mergeBib && (s.kind === 'bibresource' || s.kind === 'bibliography')) {
      if (!bibResDone && bibSystem === 'biblatex') out.push(`\\addbibresource{${bibPath}}`);
      bibResDone = true;
      return;
    }
    if (bibSystem && s.kind === 'bibstyle') return;
    if (s.kind === 'packages' && babelChanged && s.pkgs.some((pk) => pk.name === 'babel')) {
      out.push(s.raw.replace(/\\usepackage\s*(\[[^\]]*\])?\s*\{babel\}/, `\\usepackage[${babelLangs.join(',')}]{babel}`));
      return;
    }
    if (s.kind === 'meta' && s.field === 'author' && mergedAuthor) {
      if (!authorDone) out.push(mergedAuthor);
      authorDone = true;
      return;
    }
    out.push(s.raw);
    if (i === earlyAt && firstLateIdx < 0) emitEarly();
    if (i === lastPkgIdx) emitLate();
  });
  if (lastPkgIdx < 0) {
    emitEarly();
    emitLate();
  }
  if (!gpDone && gpLine) out.push(gpLine);
  if (mergeBib && bibSystem === 'biblatex' && !bibResDone) out.push(`\\addbibresource{${bibPath}}`);
  if (title) out.push(title);
  if (mergedAuthor && !authorDone) out.push(mergedAuthor);
  const byPart = new Map();
  for (const e of extras) {
    if (!byPart.has(e.part)) byPart.set(e.part, []);
    byPart.get(e.part).push(e.text);
  }
  for (const [num, texts] of byPart) {
    out.push('', `% --- added from part ${num}: ${parts[num - 1].name} ---`, ...texts);
  }
  while (out.length && out[out.length - 1].trim() === '') out.pop();
  out.push('', '\\begin{document}', '');
  parts.forEach((p, i) => {
    if (i > 0 && options.newPage) out.push('\\clearpage');
    out.push(`\\input{${partFile(p).replace(/\.tex$/, '')}} % ${p.name}`);
  });
  const bibLines = [];
  if (bibSystem === 'biblatex') bibLines.push(bibPrint);
  if (bibSystem === 'bibtex' && mergeBib) bibLines.push(`\\bibliographystyle{${bibStyle}}`, `\\bibliography{${bibPath.replace(/\.bib$/i, '')}}`);
  const appendixParts = parts.filter((p) => p.appendix && p.appendix.trim());
  if (!bibAfterAppendix && bibLines.length) out.push('', ...bibLines);
  if (appendixParts.length) {
    out.push('', '\\appendix');
    for (const p of appendixParts) out.push(`\\input{${appendixFile(p).replace(/\.tex$/, '')}} % appendix of ${p.name}`);
  }
  if (bibAfterAppendix && bibLines.length) out.push('', ...bibLines);
  out.push('', '\\end{document}', '');

  // ---------------------------------------------------------- write the new project
  const projectName = String(name || '').trim() || parts.map((p) => p.name).join(' + ').slice(0, 80);
  const meta = await P.createSkeleton({ name: projectName, mainFile: 'main.tex', engine, extra: { combinedFrom: R.parts } });
  const dest = P.filesDir(meta.id);
  const write = async (rel, data) => {
    const abs = path.join(dest, ...rel.split('/'));
    await fsp.mkdir(path.dirname(abs), { recursive: true });
    await fsp.writeFile(abs, data);
  };
  try {
    for (const v of placed.values()) if (!v.reserved) await write(v.rel, v.data);
    await write('main.tex', out.join('\n').replace(/\n{3,}/g, '\n\n'));
    for (const p of parts) {
      const header = `% Part ${p.num}: ${p.name}\n% Source: ${p.source}, originally ${p.mainFile}\n\n`;
      await write(partFile(p), header + p.body);
      if (p.appendix && p.appendix.trim()) await write(appendixFile(p), `% Appendix of part ${p.num}: ${p.name}\n\n` + p.appendix.replace(/\s+$/, '') + '\n');
    }
    if (mergeBib) await write(bibPath, `% Combined bibliography (${R.stats.references} entries) created by Folio on ${date}\n\n` + bibOut.join('\n\n') + '\n');
    R.engine = engine;
    R.bibSystem = bibSystem;
    R.bibPath = bibPath;
    await write('merge-report.txt', reportText(R, projectName));
  } catch (e) {
    await P.deleteProject(meta.id).catch(() => {});
    throw e;
  }
  return { project: meta, report: R };
}

function reportText(R, name) {
  const L = [];
  L.push(`Merge report for "${name}"`, `Created ${new Date().toLocaleString()}`, '');
  L.push('Order of parts:');
  for (const p of R.parts) L.push(`  ${p.num}. ${p.name}  (${p.source}, main file ${p.mainFile})`);
  L.push('', `Part 1 provides the document class, preamble layout and title.`);
  L.push(`Compiler: ${R.engine}. Bibliography: ${R.bibSystem ? `${R.bibSystem} with ${R.bibPath}` : 'none'}.`);
  L.push(`Files: ${R.stats.copied} copied, ${R.stats.shared} identical files stored once.`);
  if (R.bibSystem) L.push(`References: ${R.stats.references} entries, ${R.stats.duplicateReferences} duplicates merged.`);
  const section = (title, rows) => {
    if (!rows.length) return;
    L.push('', title);
    for (const r of rows) L.push('  ' + r);
  };
  section('Renamed files (same name, different content):', R.renamedFiles.map((r) => `part ${r.part}: ${r.from} -> ${r.to}`));
  section('Renamed citation keys (same key, different source):', R.renamedKeys.map((r) => `part ${r.part}: ${r.from} -> ${r.to}`));
  section('Renamed labels (used by an earlier part):', R.renamedLabels.map((r) => `part ${r.part}: ${r.from} -> ${r.to}`));
  section('Rewritten file references:', R.rewrittenRefs.map((r) => `part ${r.part} (${r.file}): {${r.from}} -> {${r.to}}`));
  section('Packages added to the preamble:', R.addedPackages.map((r) => `${r.pkg} (from part ${r.part})`));
  section('Skipped (please check):', R.skipped.map((r) => `part ${r.part}: ${r.what} - ${r.why}`));
  section('Moved or removed commands:', R.removed.map((r) => `part ${r.part}: ${r.cmd}`));
  section('Notes:', R.notes);
  return L.join('\n') + '\n';
}

module.exports = {
  stageZip, analyzeProject, removeStage, combine,
  // shared TeX helpers (server/portable.js, server/pieces.js)
  tex: {
    stripLineComment, stripComments, findUncommented, readGroup, commandArg, splitStatements, definitionKey, parseBib, loadPart,
    renameLabelsAndKeys, collectLabels, resolveGraphic, resolveTex, lookup, rewriteFileRefs, slugify, posixNorm, plainText,
    LABEL_CMD_RE, CITE_CMD_RE, LOAD_LAST, BIB_PKGS, ARTIFACT_RE,
  },
};
