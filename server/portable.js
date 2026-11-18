'use strict';
// Portable LaTeX export of a report.
//
// The normal project ZIP is a Folio project: it re-imports into Folio, but its \input lines, labels and the
// lab/ folder only make sense together. The portable ZIP is meant for any other LaTeX project:
//
//   main.tex                     compiles the export on its own
//   <prefix>/body.tex            the document text; every file path points into <prefix>/
//   <prefix>/preamble.tex        packages only if not loaded yet, definitions only if not defined yet, \labval values
//   <prefix>/<prefix>.bib        the cited references for biblatex (biber)
//   <prefix>/<prefix>-bibtex.bib the same references with BibTeX entry types and fields (natbib, plain BibTeX)
//   <prefix>/...                 only the figures, tables and data files the text uses
//   <prefix>/folio-link.json     where each result came from, so Folio Lab can reconnect it later
//   README.txt                   the lines a host document needs
//
// Labels and citation keys get the prefix "<prefix>:" and \labval namespaces "<prefix>/<result>", so two exports
// (or an export and the host's own labels) never clash. Lab sources, revision history and removed results stay out.
const fsp = require('fs').promises;
const path = require('path');
const { HttpError } = require('./util');
const P = require('./projects');
const lab = require('./lab');
const { createZip } = require('./zip');
const T = require('./combine').tex;

const PREFIX_RE = /^[a-z][a-z0-9-]{0,39}$/;
// Packages that set up the whole document (fonts, page, language, links, bibliography). A host document makes these
// choices itself, so preamble.tex leaves them out; main.tex keeps them.
const LAYOUT_PKGS = new Set([
  'inputenc', 'inputenx', 'fontenc', 'lmodern', 'fontspec', 'unicode-math', 'xltxtra', 'xunicode', 'luatextra', 'ucs',
  'geometry', 'typearea', 'babel', 'polyglossia', 'hyperref', 'bookmark', 'hypcap', 'biblatex', 'natbib', 'cite',
  'apacite', 'harvard', 'chicago', 'jurabib', 'achicago', 'fancyhdr', 'scrlayer-scrpage', 'titlesec', 'tocloft',
  'setspace', 'parskip', 'microtype', 'lastpage', 'showframe', 'layout', 'mathptmx', 'times', 'helvet', 'courier',
  'newtxtext', 'newtxmath', 'libertine', 'libertinus', 'mathpazo', 'palatino', 'charter', 'kpfonts', 'lato',
  'sourcesanspro', 'tgheros', 'tgtermes', 'cleveref', 'autonum',
]);
// Packages kept, but without their options (the options only style the document).
const STYLE_OPTS = new Set(['caption', 'subcaption']);
const EXCLUDED_RE = /^lab\/(?:[^/]+\/(?:source|history)\/|_removed\/)/;

// \labval / \labset as in lab/labdata.tex (server/lab.js); \providecommand keeps a host's own copy.
const LABVAL_DEFS = String.raw`\providecommand\labset[3]{\expandafter\gdef\csname labv@#1@#2\endcsname{#3}}
\providecommand\labval[2]{\@ifundefined{labv@#1@#2}{\textbf{??}\PackageWarning{folio-lab}{Value #1/#2 undefined}}{\csname labv@#1@#2\endcsname}}`;

// Commands a host may lack; defined at \begin{document} only when still undefined.
const FALLBACKS = [
  ['parencite', String.raw`\@ifundefined{parencite}{\let\parencite\cite}{}`],
  ['autocite', String.raw`\@ifundefined{autocite}{\let\autocite\cite}{}`],
  ['textcite', String.raw`\@ifundefined{textcite}{\@ifundefined{citet}{\let\textcite\cite}{\let\textcite\citet}}{}`],
  ['citep', String.raw`\@ifundefined{citep}{\let\citep\cite}{}`],
  ['citet', String.raw`\@ifundefined{citet}{\let\citet\cite}{}`],
  ['eqref', String.raw`\@ifundefined{eqref}{\let\eqref\folio@eqref}{}`, String.raw`\def\folio@eqref#1{(\ref{#1})}`],
  ['cref', String.raw`\@ifundefined{cref}{\let\cref\ref}{}`],
  ['Cref', String.raw`\@ifundefined{Cref}{\let\Cref\ref}{}`],
  ['autoref', String.raw`\@ifundefined{autoref}{\let\autoref\ref}{}`],
];

function prefixFor(name, override) {
  if (override != null && override !== '') {
    const p = String(override).trim().toLowerCase();
    if (!PREFIX_RE.test(p)) throw new HttpError(400, 'Prefix: lowercase letters, digits and hyphens, starting with a letter (max. 40).');
    return p;
  }
  // default: slug of the project name, at most 24 characters, cut at a hyphen (same rule as the editor's prompt)
  let p = T.slugify(name || 'bericht');
  if (!/^[a-z]/.test(p)) p = 'r-' + p;
  if (p.length > 24) p = p.slice(0, 25).replace(/-[^-]*$/, '') || p.slice(0, 24);
  return p.slice(0, 24).replace(/-+$/, '') || 'bericht';
}

// ---------------------------------------------------------------------------- small helpers

/** Remove uncommented matches of re from text; onHit(match) for each removed one. */
function removeUncommented(text, re, onHit) {
  return text.replace(re, (m, ...rest) => {
    const src = rest[rest.length - 1];
    const offset = rest[rest.length - 2];
    const lineStart = src.lastIndexOf('\n', offset) + 1;
    const before = src.slice(lineStart, offset);
    if (T.stripLineComment(before) !== before) return m;
    if (onHit) onHit(m.trim());
    return '';
  });
}

const commentOut = (raw) => raw.trim().split(/\r?\n/).map((l) => '% ' + l).join('\n');

/** Every cite key used in text (\cite-like commands); '*' when \nocite{*} appears. */
function citedKeys(text) {
  const out = new Set();
  for (const m of T.stripComments(text).matchAll(T.CITE_CMD_RE)) {
    if (m[4].includes('\\')) continue;
    for (const k of m[4].split(',')) if (k.trim()) out.add(k.trim());
  }
  return out;
}

/** Rewrite \labval{ns}{…} (and \labset) namespaces: map(ns) -> new ns or null. Returns { text, used:Set }. */
function renameLabval(text, map) {
  const used = new Set();
  const out = text.replace(/\\(labval|labset)(\s*)\{([^{}]*)\}/g, (all, cmd, sp, ns) => {
    const n = map(ns.trim());
    if (!n) return all;
    used.add(ns.trim());
    return `\\${cmd}${sp}{${n}}`;
  });
  return { text: out, used };
}

// ---------------------------------------------------------------------------- bibliography

/** Split one .bib entry into { type, key, fields:[{name, value}] }; value keeps its braces/quotes as {…}. */
function parseEntry(raw) {
  const head = /^@\s*([A-Za-z]+)\s*([{(])\s*([^,\s]*)\s*,/.exec(raw);
  if (!head) return null;
  const body = raw.slice(head[0].length, raw.length - 1);
  const fields = [];
  let i = 0;
  const ws = () => {
    while (i < body.length && /\s/.test(body[i])) i++;
  };
  while (i < body.length) {
    while (i < body.length && /[\s,]/.test(body[i])) i++;
    const m = /^([A-Za-z][\w:.+-]*)\s*=\s*/.exec(body.slice(i));
    if (!m) break;
    i += m[0].length;
    let val = '';
    for (;;) {
      ws();
      if (body[i] === '{') {
        const g = T.readGroup(body, i);
        if (!g) {
          i = body.length;
          break;
        }
        val += '{' + g.content + '}';
        i = g.end;
      } else if (body[i] === '"') {
        let j = i + 1;
        let d = 0;
        for (; j < body.length; j++) {
          const c = body[j];
          if (c === '\\') {
            j++;
            continue;
          }
          if (c === '{') d++;
          else if (c === '}') d--;
          else if (c === '"' && d === 0) break;
        }
        val += '{' + body.slice(i + 1, j) + '}';
        i = j + 1;
      } else {
        const mm = /^[^,#\s})]+/.exec(body.slice(i));
        if (!mm) break;
        val += mm[0];
        i += mm[0].length;
      }
      ws();
      if (body[i] === '#') {
        i++;
        val += ' # ';
        continue;
      }
      break;
    }
    fields.push({ name: m[1].toLowerCase(), value: val.trim() });
  }
  return { type: head[1].toLowerCase(), key: head[3], fields };
}

const unbrace = (v) => {
  const s = String(v || '').trim();
  if (s.startsWith('{')) {
    const g = T.readGroup(s, 0);
    if (g && g.end === s.length) return g.content;
  }
  return s;
};

function writeEntry(type, key, fields) {
  return `@${type}{${key},\n` + fields.map((f) => `  ${f.name} = ${f.value}`).join(',\n') + '\n}';
}

/** Rename the key of a raw biblatex entry. */
const rekey = (raw, key) => raw.replace(/^(@\s*[A-Za-z]+\s*[{(]\s*)([^,\s]*)/, (all, a) => a + key);

const MONTHS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'];
const BIBTEX_TYPES = new Set(['article', 'book', 'booklet', 'conference', 'inbook', 'incollection', 'inproceedings', 'manual', 'mastersthesis', 'misc', 'phdthesis', 'proceedings', 'techreport', 'unpublished']);

/** A biblatex entry rewritten with BibTeX entry types and fields (for natbib or plain BibTeX hosts). */
function toBibtex(raw, key) {
  const e = parseEntry(raw);
  if (!e) return null;
  const get = (n) => e.fields.find((f) => f.name === n);
  const has = (n) => !!get(n);
  let type = e.type;
  const fields = [];
  const notes = [];
  if (['online', 'www', 'electronic', 'dataset', 'software', 'standard', 'patent', 'periodical', 'artwork', 'audio', 'video', 'image', 'movie', 'music', 'performance', 'misc', 'unpublished'].includes(type)) type = type === 'unpublished' ? 'unpublished' : 'misc';
  else if (type === 'report') type = 'techreport';
  else if (type === 'thesis') type = /master|ma\b|diplom|bachelor/i.test(unbrace((get('type') || {}).value)) ? 'mastersthesis' : 'phdthesis';
  else if (['mvbook', 'bookinbook', 'collection', 'mvcollection', 'reference', 'mvreference'].includes(type)) type = type.includes('collection') || type.includes('reference') ? 'book' : 'book';
  else if (['inreference', 'suppbook', 'suppcollection'].includes(type)) type = 'incollection';
  else if (['mvproceedings'].includes(type)) type = 'proceedings';
  else if (!BIBTEX_TYPES.has(type)) type = 'misc';
  for (const f of e.fields) {
    const v = f.value;
    switch (f.name) {
      case 'journaltitle':
        if (!has('journal')) fields.push({ name: 'journal', value: v });
        break;
      case 'location':
        if (!has('address')) fields.push({ name: 'address', value: v });
        break;
      case 'institution':
        fields.push({ name: type.endsWith('thesis') ? 'school' : 'institution', value: v });
        break;
      case 'date': {
        const d = /^(\d{4})(?:-(\d{2}))?/.exec(unbrace(v));
        if (d && !has('year')) fields.push({ name: 'year', value: `{${d[1]}}` });
        if (d && d[2] && !has('month') && +d[2] >= 1 && +d[2] <= 12) fields.push({ name: 'month', value: MONTHS[+d[2] - 1] });
        break;
      }
      case 'urldate':
        notes.push(`Accessed ${unbrace(v)}`);
        break;
      case 'subtitle':
        break; // folded into the title below
      case 'title': {
        const sub = get('subtitle');
        fields.push({ name: 'title', value: sub ? `{${unbrace(v)}: ${unbrace(sub.value)}}` : v });
        break;
      }
      case 'note':
        notes.unshift(unbrace(v));
        break;
      case 'type':
        if (type === 'techreport' || type === 'misc') fields.push(f);
        break;
      case 'editortype':
      case 'langid':
      case 'keywords':
      case 'file':
        break;
      default:
        fields.push(f);
    }
  }
  // @misc: plain BibTeX ignores url, plainnat prints it; howpublished works in both (and url would print it twice)
  const url = get('url');
  if (url && type === 'misc' && !has('howpublished')) {
    fields.splice(fields.findIndex((f) => f.name === 'url'), 1);
    fields.push({ name: 'howpublished', value: `{\\url{${unbrace(url.value)}}}` });
  }
  if (notes.length) fields.push({ name: 'note', value: `{${notes.join('. ')}}` });
  return writeEntry(type, key, fields);
}

// ---------------------------------------------------------------------------- preamble

/** One preamble statement for preamble.tex: a guarded line, a commented one, or null (left out). */
function portableStatement(s, ctx) {
  switch (s.kind) {
    case 'blank':
    case 'class':
    case 'meta':
    case 'graphicspath':
    case 'bibresource':
    case 'bibliography':
    case 'bibstyle':
      return null;
    case 'packages': {
      const out = [];
      for (const pk of s.pkgs) {
        if (LAYOUT_PKGS.has(pk.name)) {
          ctx.layout.push(pk.name);
          continue;
        }
        const after = pk.name === 'pgfplots' && ctx.compat ? ctx.compat : '';
        const opts = STYLE_OPTS.has(pk.name) ? '' : pk.opts; // caption styling is the host's choice
        const use = `\\usepackage${opts ? `[${opts}]` : ''}{${pk.name}}${after}`;
        // amsmath after cleveref is an error: then only warn (\eqref falls back to (\ref), see FALLBACKS)
        out.push(pk.name === 'amsmath'
          ? `\\@ifpackageloaded{amsmath}{}{\\@ifpackageloaded{cleveref}{\\PackageWarning{folio-lab}{amsmath is needed: input this file before cleveref}}{${use}}}`
          : `\\@ifpackageloaded{${pk.name}}{}{${use}}`);
      }
      return out.length ? out.join('\n') : null;
    }
    case 'compat':
      return null; // set together with pgfplots, and only when this file loads it
    case 'library':
      return `\\@ifundefined{${s.lib}}{}{${s.code.trim()}}`;
    case 'def': {
      const c = s.code.trim();
      const [kind, name] = [s.key.slice(0, s.key.indexOf(':')), s.key.slice(s.key.indexOf(':') + 1)];
      if (/^\\(?:renewcommand|renewenvironment|RenewDocumentCommand)\b/.test(c)) {
        ctx.commented.push(c.split('\n')[0]);
        return commentOut(s.raw) + '   % changes an existing command: left to the host document';
      }
      if (/^\\newcommand\b/.test(c)) return c.replace(/^\\newcommand/, '\\providecommand');
      if (kind === 'color') return `\\@ifundefinedcolor{${name}}{%\n${c}\n}{}`;
      if (kind === 'counter') return `\\@ifundefined{c@${name}}{%\n${c}\n}{}`;
      if (kind === 'coltype' || kind === 'acro') return c;
      return `\\@ifundefined{${name}}{%\n${c}\n}{}`;
    }
    default:
      ctx.commented.push(s.code.trim().split('\n')[0]);
      return commentOut(s.raw);
  }
}

/** The project's preamble statements with \input'ed preamble files expanded (lab/labdata is dropped). */
function expandStatements(part) {
  const out = [];
  for (const s of part.statements) {
    const m = /^\\(?:input|include)\s*\{([^}]+)\}\s*$/.exec(s.code.trim());
    if (m) {
      const ref = T.posixNorm(m[1]);
      if (/^lab\/labdata(\.tex)?$/.test(ref)) {
        out.push({ ...s, kind: 'labdata' });
        continue;
      }
      const t = part.tex.get(ref) ?? part.tex.get(ref + '.tex');
      if (t != null) {
        out.push({ ...s, kind: 'preamble-file', inner: T.splitStatements(t) });
        continue;
      }
    }
    out.push(s);
  }
  return out;
}

// ---------------------------------------------------------------------------- export

/**
 * Build the portable export of project id. Returns { buffer, prefix, filename, report }.
 * opts.prefix overrides the folder / label prefix (default: slug of the project name).
 */
async function exportPortable(id, opts = {}) {
  const meta = await P.readMeta(id);
  const prefix = prefixFor(meta.name, opts.prefix);
  const part = await T.loadPart(P.filesDir(id), { name: meta.name, source: 'Folio project', engine: meta.engine });
  if (part.problems.length) throw new HttpError(400, part.problems.join(' '));
  const report = { prefix, files: [], labels: 0, keys: 0, missingFiles: [], dynamicRefs: [], commented: [], layout: [], missingKeys: [] };

  // ------------------------------------------------ files the text uses
  const own = new Map(part.files.filter((f) => !EXCLUDED_RE.test(f.rel)).map((f) => [f.rel.toLowerCase(), f.rel]));
  const used = new Set();
  const queue = [];
  const intended = (ref, kind) => {
    const hit = kind === 'graphic' ? T.resolveGraphic(ref, part.graphicspath, own) : kind === 'tex' ? T.resolveTex(ref, own) : T.lookup(own, ref);
    if (!hit) {
      if (!/^lab\/labdata(\.tex)?$/.test(T.posixNorm(ref))) report.missingFiles.push(ref);
      return null;
    }
    if (/^lab\/labdata\.tex$/i.test(hit)) return null;
    if (!used.has(hit)) {
      used.add(hit);
      if (part.tex.has(hit)) queue.push(hit);
    }
    return `${prefix}/${hit}`;
  };
  const rewrite = (text) => {
    for (const m of T.stripComments(text).matchAll(/\\(?:includegraphics|input|include|InputIfFileExists)\*?\s*(?:\[[^\]]*\]\s*)*\{([^}\n]*[#\\][^}\n]*)\}/g)) report.dynamicRefs.push(m[1]);
    return T.rewriteFileRefs(text, intended, () => null, () => {});
  };

  // the document text: front matter and bibliography commands move to main.tex / the host
  const front = [];
  let bibPrint = null;
  let bibStyle = null;
  let body = part.body;
  body = removeUncommented(body, /\\input\s*\{\s*lab\/labdata(?:\.tex)?\s*\}[ \t]*\r?\n?/g);
  body = removeUncommented(body, /\\(?:maketitle|tableofcontents|listoffigures|listoftables)\b[ \t]*/g, (m) => front.push(m));
  const stripBib = (text, record) => {
    text = removeUncommented(text, /\\printbibliography\s*(?:\[[^\]]*\])?[ \t]*/g, (m) => record && (bibPrint = bibPrint || m));
    text = removeUncommented(text, /\\bibliographystyle\s*\{[^}]*\}[ \t]*/g, (m) => record && (bibStyle = bibStyle || T.commandArg(m, 'bibliographystyle')));
    text = removeUncommented(text, /\\bibliography\s*\{[^}]*\}[ \t]*/g);
    return removeUncommented(text, /\\addbibresource\s*(?:\[[^\]]*\])?\s*\{[^}]*\}[ \t]*/g);
  };
  body = rewrite(stripBib(body, true));
  const texOut = new Map();
  while (queue.length) {
    const rel = queue.shift();
    texOut.set(rel, rewrite(stripBib(part.tex.get(rel) || '', false)));
  }
  report.missingFiles = [...new Set(report.missingFiles)];
  report.dynamicRefs = [...new Set(report.dynamicRefs)];

  // ------------------------------------------------ values: \labval{<result>} -> \labval{<prefix>/<result>}
  const results = await lab.list(id).catch(() => []);
  const slugs = new Set(results.map((r) => r.slug));
  const nsMap = (ns) => (slugs.has(ns) ? `${prefix}/${ns}` : null);
  const valueSlugs = new Set();
  {
    const r = renameLabval(body, nsMap);
    body = r.text;
    r.used.forEach((s) => valueSlugs.add(s));
    for (const [rel, t] of texOut) {
      const x = renameLabval(t, nsMap);
      texOut.set(rel, x.text);
      x.used.forEach((s) => valueSlugs.add(s));
    }
  }

  // ------------------------------------------------ labels and citation keys
  const allText = () => [body, ...texOut.values()].join('\n');
  const labelMap = new Map();
  for (const t of [body, ...texOut.values()]) for (const l of T.collectLabels(t)) labelMap.set(l, `${prefix}:${l}`);
  const cited = citedKeys(allText());
  const nociteAll = cited.has('*');
  // entries: the files the preamble names first (own references before lab/references.bib), then any other .bib
  const named = [];
  for (const s of part.statements) if ((s.kind === 'bibresource' || s.kind === 'bibliography') && s.file) for (const f of s.file.split(',')) named.push(T.posixNorm(f.trim().replace(/\.bib$/i, '') + '.bib').toLowerCase());
  const rank = (f) => {
    const i = named.indexOf(String(f).toLowerCase());
    return i >= 0 ? i : named.length + (/^lab\//.test(f) ? 1 : 0);
  };
  const entries = part.bibEntries.filter((e) => e.kind === 'entry' && !EXCLUDED_RE.test(e.file)).sort((a, b) => rank(a.file) - rank(b.file));
  const byKey = new Map();
  for (const e of entries) if (!byKey.has(e.key.toLowerCase())) byKey.set(e.key.toLowerCase(), e);
  const chosen = new Map();
  const want = (k) => {
    const e = byKey.get(String(k).toLowerCase());
    if (!e || chosen.has(e.key)) return;
    chosen.set(e.key, e);
    const x = parseEntry(e.raw);
    for (const f of (x && x.fields) || []) if (['crossref', 'xref', 'xdata'].includes(f.name)) unbrace(f.value).split(',').forEach((k2) => want(k2.trim()));
  };
  if (nociteAll) for (const e of byKey.values()) want(e.key);
  for (const k of cited) if (k !== '*') {
    if (byKey.has(k.toLowerCase())) want(k);
    else report.missingKeys.push(k);
  }
  const keyMap = new Map([...chosen.keys()].map((k) => [k, `${prefix}:${k}`]));
  const renameRefs = (t) =>
    T.renameLabelsAndKeys(t, labelMap, keyMap).replace(/(\b(?:crossref|xref|xdata)\s*=\s*\{)([^}]*)\}/g, (all, a, ks) => a + ks.split(',').map((k) => keyMap.get(k.trim()) || k).join(',') + '}');
  body = renameRefs(body);
  for (const [rel, t] of texOut) texOut.set(rel, renameRefs(t));
  report.labels = labelMap.size;
  report.keys = keyMap.size;
  const bibRaw = [...chosen.values()].map((e) => renameRefs(rekey(e.raw, keyMap.get(e.key))));
  const bibtexRaw = [...chosen.values()].map((e) => toBibtex(renameRefs(e.raw), keyMap.get(e.key))).filter(Boolean);

  // ------------------------------------------------ preamble.tex
  const statements = expandStatements(part);
  const compatSt = [...statements, ...statements.flatMap((s) => s.inner || [])].find((s) => s.kind === 'compat');
  const ctx = { layout: [], commented: [], compat: compatSt ? compatSt.code.trim() : '' };
  const pre = [];
  const emit = (s) => {
    if (s.kind === 'labdata') return;
    if (s.kind === 'preamble-file') {
      s.inner.forEach(emit);
      return;
    }
    const line = portableStatement(s, ctx);
    if (line) pre.push(line);
  };
  statements.forEach(emit);
  const textAll = allText();
  if (bibtexRaw.some((b) => /\\url\{/.test(b)) || /\\url\b/.test(textAll)) pre.unshift('\\@ifpackageloaded{url}{}{\\usepackage{url}}');
  const values = [];
  for (const slug of [...valueSlugs].sort()) {
    const t = part.tex.get(`lab/${slug}/values.tex`);
    if (t == null) continue;
    values.push(renameLabval(t, nsMap).text.trim());
  }
  const fbUsed = FALLBACKS.filter(([cmd]) => new RegExp(`\\\\${cmd}\\b`).test(textAll + bibtexRaw.join('\n')));
  const fallbacks = [...fbUsed.filter((x) => x[2]).map((x) => x[2]), ...(fbUsed.length ? ['\\AtBeginDocument{%', ...fbUsed.map(([, line]) => '  ' + line + '%'), '}'] : [])];
  const date = new Date().toISOString().slice(0, 10);
  const version = (() => {
    try {
      return require('../package.json').version;
    } catch {
      return '';
    }
  })();
  const preamble = [
    `% Preamble of "${meta.name}", exported by Folio Lab ${version} on ${date}.`,
    `% Use in another document: \\input{${prefix}/preamble} after your own packages, before hyperref and cleveref.`,
    '% Packages are loaded only when the host has not loaded them; definitions only when the name is still free.',
    ctx.layout.length ? `% Left to the host document (page, fonts, language, links, bibliography): ${[...new Set(ctx.layout)].join(', ')}.` : '',
    '\\makeatletter',
    ...pre,
    '',
    '% Values from the analysis results: \\labval{<namespace>}{<key>}',
    LABVAL_DEFS,
    ...values,
    fallbacks.length ? '\n% Fallbacks for commands the host may not have (defined only when missing)\n' + fallbacks.join('\n') : '',
    '\\makeatother',
    '',
  ].filter((x) => x !== '').join('\n');
  report.commented = ctx.commented;
  report.layout = [...new Set(ctx.layout)];

  // ------------------------------------------------ main.tex (stand-alone)
  const bibSystem = part.bibSystem || (keyMap.size ? 'bibtex' : null);
  const main = [];
  if (part.engine && part.engine !== 'pdflatex') main.push(`% !TEX program = ${part.engine}`);
  main.push(`% Stand-alone build of the portable export "${prefix}" (Folio Lab ${version}, ${date}).`, '% To use the content in another document, see README.txt.', '');
  const firstLate = part.statements.findIndex((s) => s.kind === 'packages' && s.pkgs.some((pk) => T.LOAD_LAST.includes(pk.name) || pk.name === 'hyperref'));
  const lastPkg = part.statements.reduce((a, s, i) => (s.kind === 'packages' ? i : a), -1);
  const at = firstLate >= 0 ? firstLate : lastPkg + 1;
  const inputPre = [`\\input{${prefix}/preamble}`];
  if (bibSystem === 'biblatex' && keyMap.size) inputPre.push(`\\addbibresource{${prefix}/${prefix}.bib}`);
  const keepMain = (s) => {
    if (s.kind === 'labdata' || s.kind === 'graphicspath' || s.kind === 'bibliography' || s.kind === 'bibstyle') return;
    if (s.kind === 'bibresource') return; // replaced by the export's own .bib (inputPre)
    if (s.kind === 'preamble-file') {
      s.inner.forEach(keepMain);
      return;
    }
    if (s.kind === 'def' && !/^\\(?:renewcommand|renewenvironment|RenewDocumentCommand)\b/.test(s.code.trim())) return;
    if (s.kind === 'packages' || s.kind === 'compat' || s.kind === 'library' || s.kind === 'class' || s.kind === 'meta' || s.kind === 'blank' || s.kind === 'def' || s.kind === 'other')
      main.push(T.rewriteFileRefs(s.raw, intended, () => null, () => {}));
  };
  statements.forEach((s, i) => {
    if (i === at) main.push(...inputPre);
    keepMain(s);
  });
  if (at >= statements.length) main.push(...inputPre);
  while (main.length && main[main.length - 1].trim() === '') main.pop();
  main.push('', '\\begin{document}');
  main.push(...front);
  main.push(`\\input{${prefix}/body}`);
  if (keyMap.size && bibSystem === 'biblatex') main.push(bibPrint || '\\printbibliography');
  if (keyMap.size && bibSystem === 'bibtex') main.push(`\\bibliographystyle{${bibStyle || (part.statements.find((s) => s.kind === 'bibstyle') || {}).style || 'plain'}}`, `\\bibliography{${prefix}/${prefix}-bibtex}`);
  main.push('\\end{document}', '');

  // ------------------------------------------------ link file and README
  const link = {
    format: 'folio-link/1',
    prefix,
    exported: new Date().toISOString(),
    suite_version: version || null,
    project: { id, name: meta.name },
    results: results.map((r) => ({
      slug: r.slug,
      namespace: `${prefix}/${r.slug}`,
      used: valueSlugs.has(r.slug) || [...used].some((f) => f.startsWith(`lab/${r.slug}/`)),
      title: r.title,
      module: r.module,
      module_name: r.module_name || r.module,
      result_id: r.result_id || null,
      revision: r.revision || 1,
      issued: r.issued || null,
      module_version: (r.provenance && r.provenance.module_version) || null,
      refs: r.refs || { shares: [], index: [] },
    })),
    labels: Object.fromEntries(labelMap),
    keys: Object.fromEntries(keyMap),
    files: [...used].sort(),
  };
  const readme = readmeText({ meta, prefix, version, date, engine: part.engine, bibSystem, report, hasBib: keyMap.size > 0 });

  // ------------------------------------------------ ZIP
  const now = new Date();
  const zipEntries = [];
  const add = (name, data) => zipEntries.push({ name, data: Buffer.isBuffer(data) ? data : Buffer.from(data, 'utf8'), mtime: now });
  add('README.txt', readme);
  add('main.tex', main.join('\n').replace(/\n{3,}/g, '\n\n'));
  add(`${prefix}/body.tex`, `% Text of "${meta.name}" (portable export, Folio Lab ${version}, ${date}).\n% Labels and citation keys carry the prefix "${prefix}:". Include with \\input{${prefix}/body}.\n\n` + body.replace(/\s+$/, '') + '\n');
  add(`${prefix}/preamble.tex`, preamble);
  if (keyMap.size) {
    add(`${prefix}/${prefix}.bib`, `% References of "${meta.name}" for biblatex (biber). Keys carry the prefix "${prefix}:".\n\n` + bibRaw.join('\n\n') + '\n');
    add(`${prefix}/${prefix}-bibtex.bib`, `% References of "${meta.name}" for BibTeX / natbib (entry types converted from biblatex). Keys carry the prefix "${prefix}:".\n\n` + bibtexRaw.join('\n\n') + '\n');
  }
  add(`${prefix}/folio-link.json`, JSON.stringify(link, null, 2));
  for (const rel of [...used].sort()) {
    const data = texOut.has(rel) ? texOut.get(rel) : await fsp.readFile(path.join(P.filesDir(id), ...rel.split('/')));
    add(`${prefix}/${rel}`, data);
  }
  report.files = zipEntries.map((e) => e.name);
  const filename = `${String(meta.name).replace(/[\\/:*?"<>|]/g, '_')} (portable).zip`;
  return { buffer: createZip(zipEntries), prefix, filename, report };
}

function readmeText({ meta, prefix, version, date, engine, bibSystem, report, hasBib }) {
  const L = [];
  L.push(`Portable LaTeX export of "${meta.name}"`, `Folio Lab ${version}, ${date}`, '');
  L.push('CONTENTS');
  L.push(`  main.tex                       builds this export on its own (${engine && engine !== 'pdflatex' ? engine : 'pdflatex'}${hasBib ? (bibSystem === 'biblatex' ? ' + biber' : ' + bibtex') : ''})`);
  L.push(`  ${prefix}/body.tex               the text`);
  L.push(`  ${prefix}/preamble.tex           packages (only those not loaded yet), definitions, values`);
  if (hasBib) {
    L.push(`  ${prefix}/${prefix}.bib  references for biblatex (biber)`);
    L.push(`  ${prefix}/${prefix}-bibtex.bib  the same references for BibTeX / natbib`);
  }
  L.push(`  ${prefix}/folio-link.json       origin of the results (only Folio Lab reads it)`);
  L.push(`  ${prefix}/...                    figures, tables and data used by the text`);
  L.push('');
  L.push('USE IN ANOTHER LATEX PROJECT');
  L.push(`  1. Copy the folder ${prefix}/ next to the main .tex file of that project.`);
  L.push('  2. Preamble, after your own packages but before hyperref and cleveref:');
  L.push(`       \\input{${prefix}/preamble}`);
  L.push('  3. Where the text belongs:');
  L.push(`       \\input{${prefix}/body}`);
  if (hasBib) {
    L.push('  4. References, depending on the host document:');
    L.push(`       biblatex:       \\addbibresource{${prefix}/${prefix}.bib}       (preamble)`);
    L.push(`       BibTeX/natbib:  \\bibliography{<your files>,${prefix}/${prefix}-bibtex}`);
  }
  L.push('');
  L.push(`Labels and citation keys start with "${prefix}:" (for example \\ref{${prefix}:fig:...}), so they cannot clash`);
  L.push(`with the host's own. Values are printed with \\labval{${prefix}/<result>}{<key>}.`);
  L.push('The paths in body.tex are relative to the host\'s main file, so the folder must sit next to it.');
  L.push('A Folio Lab report can import this ZIP again and reconnect the results (folio-link.json).');
  if (report.layout.length) {
    L.push('', 'LEFT TO THE HOST DOCUMENT (main.tex loads them; preamble.tex does not):');
    L.push('  ' + report.layout.join(', '));
  }
  if (report.commented.length) {
    L.push('', 'PREAMBLE LINES COMMENTED OUT IN preamble.tex (they change the host document; enable them if needed):');
    for (const c of report.commented) L.push('  ' + c.slice(0, 100));
  }
  if (report.missingFiles.length) {
    L.push('', 'FILES REFERENCED BUT NOT FOUND IN THE PROJECT:');
    for (const f of report.missingFiles) L.push('  ' + f);
  }
  if (report.dynamicRefs.length) {
    L.push('', 'FILE REFERENCES BUILT FROM MACROS (not rewritten; check the paths):');
    for (const f of report.dynamicRefs) L.push('  ' + f);
  }
  if (report.missingKeys.length) {
    L.push('', 'CITED BUT NOT IN ANY .bib FILE OF THE PROJECT:');
    L.push('  ' + report.missingKeys.join(', '));
  }
  return L.join('\r\n') + '\r\n';
}

module.exports = { exportPortable, prefixFor, parseEntry, toBibtex, rekey, unbrace, portableStatement, citedKeys, renameLabval, removeUncommented, LAYOUT_PKGS, LABVAL_DEFS, FALLBACKS };
