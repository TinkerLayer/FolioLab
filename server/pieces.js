'use strict';
// Piece extractor: everything in a LaTeX project (a Folio report or an unpacked ZIP) that can be imported
// into a report on its own: figures, tables, equations, sections, images, data files, the analysis results stored
// under lab/ and their values.
//
// Each piece has a stable key (its label, file or section title; otherwise a content hash), so a later version of
// the same source can be searched for the same piece (live links, RI-05). analyze() lists what the piece needs:
// files (recursively through \input), labels, cited keys with their .bib entries, user macros (preamble
// definitions, also those used by other definitions), the packages its commands need and the \labval values.
const fsp = require('fs').promises;
const path = require('path');
const crypto = require('crypto');
const { readText } = require('./util');
const T = require('./combine').tex;
const PT = require('./portable');

const EXCLUDED_RE = /^lab\/(?:[^/]+\/(?:source|history)\/|_removed\/)/;
const IMAGE_RE = /\.(pdf|png|jpe?g|eps)$/i;
const DATA_RE = /\.(csv|tsv|dat)$/i;
const ENV_RE = /\\begin\s*\{((?:figure|table|wrapfigure|wraptable|sidewaysfigure|sidewaystable|equation|align|gather|multline|flalign|eqnarray|displaymath)\*?)\}/g;
const SECTION_RE = /\\(chapter|section|subsection|subsubsection)\*?\s*(?:\[[^\]]*\]\s*)?\{/g;
const LEVEL = { chapter: 0, section: 1, subsection: 2, subsubsection: 3 };
const MAX_PIECES = 2000;

// Commands that tell which package a piece needs (also when the source got it through its class or another package).
const PKG_HINTS = {
  amsmath: /\\(?:text|dfrac|tfrac|operatorname|eqref|tag|intertext|boldsymbol|binom|substack|xrightarrow|xleftarrow)\b|\\begin\s*\{(?:align|gather|multline|flalign|split|aligned|gathered|alignedat|cases|pmatrix|bmatrix|Bmatrix|vmatrix|Vmatrix|matrix|smallmatrix)\*?\}/,
  amssymb: /\\(?:mathbb|mathfrak|leqslant|geqslant|varnothing|blacksquare|therefore|because|lesssim|gtrsim|checkmark|nexists|complement)\b/,
  booktabs: /\\(?:toprule|midrule|bottomrule|cmidrule|addlinespace)\b/,
  graphicx: /\\(?:includegraphics|rotatebox|scalebox|resizebox|reflectbox)\b/,
  xcolor: /\\(?:textcolor|color|colorbox|fcolorbox|rowcolor|cellcolor|columncolor|definecolor)\b/,
  siunitx: /\\(?:SI|si|num|qty|unit|ang|SIrange|qtyrange|numrange|qtylist|sisetup)\b/,
  tikz: /\\begin\s*\{tikzpicture\}|\\tikz\b/,
  pgfplots: /\\begin\s*\{(?:axis|semilogxaxis|semilogyaxis|loglogaxis|polaraxis|groupplot)\}|\\addplot\b/,
  multirow: /\\multirow\b/,
  tabularx: /\\begin\s*\{tabularx\}/,
  longtable: /\\begin\s*\{longtable\}/,
  subcaption: /\\begin\s*\{sub(?:figure|table)\}|\\subcaption(?:box)?\b/,
  float: /\\begin\s*\{(?:figure|table)\*?\}\s*\[\s*H\s*\]/,
  wrapfig: /\\begin\s*\{wrap(?:figure|table)\}/,
  rotating: /\\begin\s*\{sideways(?:figure|table)\}/,
  makecell: /\\(?:makecell|thead)\b/,
  threeparttable: /\\begin\s*\{threeparttable\}/,
  mhchem: /\\(?:ce|pu)\s*\{/,
  chemformula: /\\ch\s*\{/,
  bm: /\\bm\b/,
  csquotes: /\\enquote\b/,
  caption: /\\(?:captionof|captionsetup)\b/,
  listings: /\\begin\s*\{lstlisting\}|\\lstinline\b|\\lstinputlisting\b/,
  cancel: /\\(?:cancel|bcancel|xcancel|cancelto)\b/,
  mathtools: /\\(?:coloneqq|eqqcolon|mathclap|mathllap|mathrlap|shortintertext)\b/,
  gensymb: /\\(?:degree|celsius|ohm|perthousand|micro)\b/,
  upgreek: /\\up(?:alpha|beta|gamma|delta|epsilon|mu|pi|sigma|tau|phi|omega)\b/,
  url: /\\url\b/,
  esint: /\\(?:oiint|oiiint|sqint)\b/,
};
// Packages that a piece never pulls in on its own: they shape the whole document (see portable.js) or clash.
const SKIP_PKGS = new Set([...PT.LAYOUT_PKGS, 'subfig', 'subfigure', 'minted']);

const sha = (s) => crypto.createHash('sha1').update(s).digest('hex');
const escRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/** Comments blanked out with spaces, offsets unchanged. */
function maskComments(text) {
  return text.split('\n').map((line) => {
    const code = T.stripLineComment(line);
    return code.length === line.length ? line : code + ' '.repeat(line.length - code.length);
  }).join('\n');
}

/** End offset of the \end{env} that closes the \begin{env} at `from` (same-name nesting counted), or -1. */
function envEnd(masked, env, from) {
  const re = new RegExp(`\\\\(begin|end)\\s*\\{${escRe(env)}\\}`, 'g');
  re.lastIndex = from;
  let depth = 0;
  let m;
  while ((m = re.exec(masked))) {
    if (m[1] === 'begin') depth++;
    else if (--depth === 0) return m.index + m[0].length;
  }
  return -1;
}

/** \[ … \] blocks outside the given ranges. */
function displayMath(masked, taken) {
  const out = [];
  const inTaken = (i) => taken.some(([a, b]) => i >= a && i < b);
  for (let i = 0; i < masked.length - 1; i++) {
    if (masked[i] !== '\\' || masked[i + 1] !== '[') continue;
    let bs = 0;
    for (let j = i - 1; j >= 0 && masked[j] === '\\'; j--) bs++;
    if (bs % 2 === 1) continue; // \\[2pt] line break
    if (inTaken(i)) continue;
    let k = i + 2;
    let end = -1;
    for (; k < masked.length - 1; k++) {
      if (masked[k] === '\\' && masked[k + 1] === ']') {
        let b2 = 0;
        for (let j = k - 1; j >= i + 2 && masked[j] === '\\'; j--) b2++;
        if (b2 % 2 === 0) {
          end = k + 2;
          break;
        }
      }
      if (masked[k] === '\\') k++;
    }
    if (end < 0) break;
    out.push([i, end]);
    i = end - 1;
  }
  return out;
}

const cleanTitle = (s, n = 90) => {
  const t = T.plainText(String(s || '').replace(/\\(?:label|cite[a-z]*)\s*(?:\[[^\]]*\])*\{[^}]*\}/g, '')).replace(/\s+/g, ' ').trim();
  return t.length > n ? t.slice(0, n - 1) + '…' : t;
};

/** Equations are listed by their LaTeX (plain text loses too much). */
const mathTitle = (s) => {
  const t = String(s || '').replace(/\\label\s*\{[^}]*\}/g, '').replace(/\s+/g, ' ').trim();
  return t.length > 80 ? t.slice(0, 79) + '…' : t;
};

// ---------------------------------------------------------------------------- source loading

/** Analysis results stored in a project folder (lab/<slug>/bundle.json), without history and removed ones. */
async function readResults(dir) {
  const out = [];
  let ents = [];
  try {
    ents = await fsp.readdir(path.join(dir, 'lab'), { withFileTypes: true });
  } catch {
    return out;
  }
  for (const d of ents) {
    if (!d.isDirectory() || !/^[a-z0-9][a-z0-9-]{0,59}$/.test(d.name)) continue;
    try {
      const m = JSON.parse(await fsp.readFile(path.join(dir, 'lab', d.name, 'bundle.json'), 'utf8'));
      if (m && Array.isArray(m.items)) out.push({ ...m, slug: d.name });
    } catch {
      /* folder without manifest */
    }
  }
  return out.sort((a, b) => String(a.title || a.slug).localeCompare(String(b.title || b.slug)));
}

/**
 * Load a source folder. opts: {name, source, engine, strip}. strip = portable prefix (from folio-link.json):
 * labels "<prefix>:x" and paths "<prefix>/x" count as "x" for the piece keys, so a re-imported portable ZIP finds
 * the same pieces as its original report.
 */
async function loadSource(dir, opts = {}) {
  const part = await T.loadPart(dir, { name: opts.name, source: opts.source, engine: opts.engine });
  const results = await readResults(dir);
  let link = null;
  if (!opts.noLink) {
    // a portable export: <prefix>/folio-link.json next to main.tex
    for (const f of part.files) {
      if (!/^[a-z][a-z0-9-]{0,39}\/folio-link\.json$/.test(f.rel)) continue;
      try {
        const j = JSON.parse((await readText(f.abs)) || 'null');
        if (j && j.format === 'folio-link/1' && j.prefix && f.rel === `${j.prefix}/folio-link.json`) link = j;
      } catch {
        /* not ours */
      }
    }
  }
  const src = {
    dir, part, results, link, strip: link ? link.prefix : opts.strip || null,
    own: new Map(part.files.filter((f) => !EXCLUDED_RE.test(f.rel)).map((f) => [f.rel.toLowerCase(), f.rel])),
  };
  // preamble statements, \input'ed preamble files expanded
  src.statements = [];
  for (const s of part.statements || []) {
    const m = /^\\(?:input|include)\s*\{([^}]+)\}\s*$/.exec(s.code.trim());
    const t = m ? part.tex.get(T.posixNorm(m[1])) ?? part.tex.get(T.posixNorm(m[1]) + '.tex') : null;
    if (m && /^lab\/labdata(\.tex)?$/.test(T.posixNorm(m[1]))) continue;
    if (t != null) src.statements.push(...T.splitStatements(unguard(t)));
    else src.statements.push(s);
  }
  src.defs = new Map();
  for (const s of src.statements) if (s.kind === 'def' && !src.defs.has(s.key) && !/^cmd:lab(?:val|set)$/.test(s.key)) src.defs.set(s.key, s); // \labval: values travel separately
  src.packages = new Map();
  for (const s of src.statements) if (s.kind === 'packages') for (const pk of s.pkgs) if (!src.packages.has(pk.name)) src.packages.set(pk.name, pk.opts);
  src.compat = (src.statements.find((s) => s.kind === 'compat') || {}).code || '';
  src.libraries = src.statements.filter((s) => s.kind === 'library');
  // bibliography: files named in the preamble first, results' copies last; first entry per key wins
  const named = [];
  for (const s of part.statements || []) if ((s.kind === 'bibresource' || s.kind === 'bibliography') && s.file) for (const f of s.file.split(',')) named.push(T.posixNorm(f.trim().replace(/\.bib$/i, '') + '.bib').toLowerCase());
  const rank = (f) => {
    const i = named.indexOf(String(f).toLowerCase());
    return i >= 0 ? i : named.length + (/^lab\//.test(f) ? 1 : 0);
  };
  src.bib = new Map();
  for (const e of (part.bibEntries || []).filter((x) => x.kind === 'entry' && !EXCLUDED_RE.test(x.file)).sort((a, b) => rank(a.file) - rank(b.file)))
    if (!src.bib.has(e.key.toLowerCase())) src.bib.set(e.key.toLowerCase(), e);
  return src;
}

/** A preamble file as portable.js writes it (guards, \makeatletter) read back as plain statements. */
function unguard(t) {
  return t
    .replace(/^[ \t]*\\make(?:atletter|atother)[ \t]*$/gm, '')
    .replace(/\\@ifpackageloaded\{([^}]*)\}\{\}\{(\\usepackage(?:\[[^\]]*\])?\{[^}]*\})([^\n]*)\}[ \t]*$/gm, (a, n, use, after) => use + (after ? '\n' + after : ''))
    .replace(/\\@ifundefined(?:color)?\{[^}]*\}\{%\r?\n([\s\S]*?)\r?\n\}\{\}/g, '$1')
    .replace(/\\@ifundefined\{([a-zA-Z]+)\}\{\}\{(\\use(?:tikz|pgfplots)library\{[^}]*\})\}/g, '$2');
}

const unstrip = (src, s) => (src.strip ? String(s).split(`${src.strip}:`).join('').split(`${src.strip}/`).join('') : String(s));

// ---------------------------------------------------------------------------- dependencies of a piece

function usedDefs(src, text) {
  const chosen = new Map();
  const uses = (key, t) => {
    const name = key.slice(key.indexOf(':') + 1);
    const kind = key.slice(0, key.indexOf(':'));
    if (kind === 'cmd' || kind === 'len') return new RegExp(`\\\\${escRe(name)}(?![A-Za-z@])`).test(t);
    if (kind === 'env') return new RegExp(`\\\\begin\\s*\\{${escRe(name)}\\}`).test(t);
    if (kind === 'color') return new RegExp(`[{,!]\\s*${escRe(name)}\\s*[},!]`).test(t);
    if (kind === 'counter') return new RegExp(`\\{${escRe(name)}\\}|\\\\the${escRe(name)}\\b`).test(t);
    if (kind === 'coltype') return /\\begin\s*\{(?:tabular|tabularx|tabulary|longtable|array)\*?\}/.test(t);
    return false;
  };
  let frontier = [text];
  while (frontier.length) {
    const t = frontier.join('\n');
    frontier = [];
    for (const [key, s] of src.defs) {
      if (chosen.has(key) || !uses(key, t)) continue;
      chosen.set(key, s);
      frontier.push(s.code);
    }
  }
  return [...chosen.values()];
}

function neededPackages(src, text) {
  const out = new Map();
  for (const [name, opts] of src.packages) {
    if (SKIP_PKGS.has(name)) continue;
    const hint = PKG_HINTS[name];
    if (!hint || hint.test(text)) out.set(name, opts);
  }
  for (const [name, re] of Object.entries(PKG_HINTS)) {
    if (out.has(name) || SKIP_PKGS.has(name) || !re.test(text)) continue;
    if (name === 'subcaption' && (src.packages.has('subfig') || src.packages.has('subfigure'))) continue;
    out.set(name, '');
  }
  if (out.has('pgfplots')) out.delete('tikz'); // pgfplots loads it
  return out;
}

/** What one piece of LaTeX needs from its source. */
function analyze(src, latex) {
  const files = new Set();
  const missing = new Set();
  const queue = [];
  const intended = (ref, kind) => {
    const hit = kind === 'graphic' ? T.resolveGraphic(ref, src.part.graphicspath || [], src.own) : kind === 'tex' ? T.resolveTex(ref, src.own) : T.lookup(src.own, ref);
    if (!hit) {
      if (!/^lab\/labdata(\.tex)?$/.test(T.posixNorm(ref))) missing.add(ref);
      return null;
    }
    if (/^lab\/labdata\.tex$/i.test(hit)) return null;
    if (!files.has(hit)) {
      files.add(hit);
      if (src.part.tex.has(hit)) queue.push(hit);
    }
    return null;
  };
  const texts = [latex];
  T.rewriteFileRefs(latex, intended, () => null, () => {});
  while (queue.length) {
    const t = src.part.tex.get(queue.shift()) || '';
    texts.push(t);
    T.rewriteFileRefs(t, intended, () => null, () => {});
  }
  const full = T.stripComments(texts.join('\n'));
  const labels = [...T.collectLabels(full)];
  const cited = PT.citedKeys(full);
  const bib = new Map();
  const missingKeys = [];
  const want = (k) => {
    const e = src.bib.get(String(k).toLowerCase());
    if (!e || bib.has(e.key)) return;
    bib.set(e.key, e);
    const x = PT.parseEntry(e.raw);
    for (const f of (x && x.fields) || []) if (['crossref', 'xref', 'xdata'].includes(f.name)) PT.unbrace(f.value).split(',').forEach((k2) => want(k2.trim()));
  };
  for (const k of cited) {
    if (k === '*') continue;
    if (src.bib.has(k.toLowerCase())) want(k);
    else missingKeys.push(k);
  }
  const values = [];
  for (const m of full.matchAll(/\\labval\s*\{([^{}]*)\}\s*\{([^{}]*)\}/g)) values.push({ ns: m[1].trim(), key: m[2].trim() });
  const defs = usedDefs(src, full);
  const packages = neededPackages(src, full + '\n' + defs.map((d) => d.code).join('\n'));
  return {
    files: [...files].sort(), missing: [...missing], labels, cites: [...bib.keys()], missingKeys, bib: [...bib.values()], values,
    defs, packages, libraries: /tikzpicture|\\tikz\b|\\begin\s*\{axis\}/.test(full) ? src.libraries : [], text: full,
  };
}

// ---------------------------------------------------------------------------- listing

function textUnits(src) {
  // the body and every .tex file reachable from it through \input / \include, in reading order
  const units = [];
  const seen = new Set();
  const visit = (rel, text) => {
    units.push({ rel, text });
    const masked = maskComments(text);
    for (const m of masked.matchAll(/\\(?:input|include|subfile|InputIfFileExists)\s*\{([^}\n]+)\}/g)) {
      const hit = T.resolveTex(m[1].trim(), src.own);
      if (!hit || seen.has(hit) || /^lab\/labdata\.tex$/i.test(hit)) continue;
      seen.add(hit);
      if (src.part.tex.has(hit)) visit(hit, src.part.tex.get(hit));
    }
  };
  if (src.part.body != null) visit(src.part.mainFile || 'main.tex', src.part.body);
  return units;
}

/** All pieces of a loaded source: [{key, kind, title, detail, unit, latex?, file?, preview?, …}] */
function listPieces(src) {
  const pieces = [];
  const keys = new Map();
  const add = (p) => {
    if (pieces.length >= MAX_PIECES) return;
    let k = p.key;
    const n = (keys.get(k) || 0) + 1;
    keys.set(k, n);
    if (n > 1) k = `${k}~${n}`;
    pieces.push({ ...p, key: k });
  };
  const resultOfFile = (rel) => {
    const m = /^lab\/([^/]+)\//.exec(unstrip(src, rel));
    return m ? src.results.find((r) => r.slug === m[1]) : null;
  };

  // LaTeX pieces of the text
  for (const u of textUnits(src)) {
    const masked = maskComments(u.text);
    const taken = [];
    ENV_RE.lastIndex = 0;
    let m;
    while ((m = ENV_RE.exec(masked))) {
      const env = m[1];
      const end = envEnd(masked, env, m.index);
      if (end < 0) continue;
      taken.push([m.index, end]);
      ENV_RE.lastIndex = end;
      const latex = u.text.slice(m.index, end);
      const kind = /figure/.test(env) ? 'figure' : /table/.test(env) ? 'table' : 'equation';
      const code = T.stripComments(latex);
      const label = (/\\label\s*\{([^}]+)\}/.exec(code) || [])[1];
      const caption = T.commandArg(code, 'caption');
      const graphics = [...code.matchAll(/\\includegraphics\*?\s*(?:\[[^\]]*\]\s*)*\{([^}]+)\}/g)].map((x) => x[1].trim());
      const key = label ? `${kind}:${unstrip(src, label.trim())}`
        : kind === 'figure' && graphics.length === 1 ? `figure@${unstrip(src, graphics[0]).replace(/\.(pdf|png|jpe?g|eps)$/i, '')}`
        : `${kind}#${sha(unstrip(src, code).replace(/\s+/g, ' ')).slice(0, 10)}`;
      const math = kind === 'equation' ? mathTitle(code.replace(/\\(?:begin|end)\s*\{[^}]*\}/g, '')) : '';
      const title = cleanTitle(caption) || math || (label ? label.trim() : '') || cleanTitle(code.replace(/\\(?:begin|end)\s*\{[^}]*\}/g, ''), 70) || env;
      const preview = graphics.length ? T.resolveGraphic(graphics[0], src.part.graphicspath || [], src.own) : null;
      add({ key, kind, env, title, label: label ? label.trim() : null, unit: u.rel, latex, preview: previewOf(src, preview), simple: kind === 'figure' && graphics.length === 1 && !/tikzpicture|\\begin\s*\{sub/.test(code) ? { graphic: preview, caption: caption || '', width: (/width\s*=\s*([0-9.]+)\s*\\(?:line|text)width/.exec(code) || [])[1] || null } : null });
    }
    for (const [a, b] of displayMath(masked, taken)) {
      const latex = u.text.slice(a, b);
      const code = T.stripComments(latex);
      add({ key: `equation#${sha(unstrip(src, code).replace(/\s+/g, ' ')).slice(0, 10)}`, kind: 'equation', env: 'displaymath', title: mathTitle(code.slice(2, -2)) || 'Equation', unit: u.rel, latex });
    }
    // sections: from the heading to the next heading of the same or a higher level
    const heads = [];
    SECTION_RE.lastIndex = 0;
    while ((m = SECTION_RE.exec(masked))) {
      const g = T.readGroup(u.text, m.index + m[0].length - 1);
      if (!g) continue;
      heads.push({ at: m.index, level: LEVEL[m[1]], cmd: m[1], title: g.content });
    }
    const stop = (() => {
      const s = masked.search(/\\(?:printbibliography|bibliography\s*\{|appendix\b)/);
      return s < 0 ? u.text.length : s;
    })();
    heads.forEach((h, i) => {
      if (h.at >= stop) return;
      let end = stop;
      for (const n of heads.slice(i + 1)) if (n.level <= h.level) {
        end = Math.min(end, n.at);
        break;
      }
      const latex = u.text.slice(h.at, end).replace(/\s+$/, '') + '\n';
      add({ key: `section:${T.slugify(T.plainText(h.title))}`, kind: 'section', env: h.cmd, title: cleanTitle(h.title) || h.cmd, unit: u.rel, latex });
    });
  }

  // analysis results and their values
  for (const r of src.results) {
    add({ key: `result:${r.slug}`, kind: 'result', title: r.title || r.slug, detail: `${r.module_name || r.module || 'result'}${r.revision ? ` · revision ${r.revision}` : ''}`, slug: r.slug, revision: r.revision || 1, result_id: r.result_id || null, preview: previewOf(src, firstFigure(r)) });
    const vals = r.items.filter((i) => i.kind === 'values').flatMap((i) => i.values || []);
    if (vals.length) add({ key: `values:${r.slug}`, kind: 'values', title: `${r.title || r.slug}: ${vals.length} value${vals.length === 1 ? '' : 's'}`, slug: r.slug, values: vals.map((v) => ({ key: v.key, label: v.label, text: v.text, latex: v.latex })) });
  }

  // image and data files anywhere in the project
  const imgs = new Map();
  for (const f of src.part.files) {
    if (EXCLUDED_RE.test(f.rel) || /^[^/]+\/folio-link\.json$/.test(f.rel)) continue;
    if (IMAGE_RE.test(f.rel)) {
      const stem = f.rel.replace(/\.[^.]+$/, '').toLowerCase();
      const e = imgs.get(stem) || {};
      const vector = /\.(pdf|eps)$/i.test(f.rel);
      if (!vector) e.png = e.png || f.rel; // preview
      if (vector || !e.file) e.file = vector && e.file && /\.(pdf|eps)$/i.test(e.file) ? e.file : vector ? f.rel : e.file || f.rel;
      imgs.set(stem, e);
    } else if (DATA_RE.test(f.rel)) {
      const r = resultOfFile(f.rel);
      const it = r && r.items.find((i) => i.kind === 'data' && `lab/${r.slug}/${i.file}` === unstrip(src, f.rel));
      add({ key: `data:${unstrip(src, f.rel)}`, kind: 'data', title: it ? cleanTitle(it.description) || path.posix.basename(f.rel) : path.posix.basename(f.rel), detail: f.rel, file: f.rel, item: it || null, size: f.size });
    }
  }
  for (const e of imgs.values()) {
    const r = resultOfFile(e.file);
    const it = r && r.items.find((i) => i.kind === 'figure' && `lab/${r.slug}/${i.file}` === unstrip(src, e.file));
    add({ key: `image:${unstrip(src, e.file)}`, kind: 'image', title: it ? cleanTitle(it.caption) : path.posix.basename(e.file), detail: e.file, file: e.file, preview: e.png || (/\.(png|jpe?g)$/i.test(e.file) ? e.file : null) });
  }
  return pieces;
}

function firstFigure(r) {
  const f = r.items.find((i) => i.kind === 'figure');
  return f ? `lab/${r.slug}/${f.preview || f.file}` : null;
}
function previewOf(src, rel) {
  if (!rel) return null;
  if (/\.(png|jpe?g)$/i.test(rel)) return rel;
  const png = T.lookup(src.own, rel.replace(/\.[^.]+$/, '.png'));
  return png || null;
}

/** The \labset value of <ns>/<key> in a source: lab/<ns>/values.tex, or a portable preamble (\labset{<prefix>/<ns>}). */
function valueOf(src, ns, key) {
  const look = (text, name) => {
    const re = new RegExp(`\\\\labset\\s*\\{${escRe(name)}\\}\\s*\\{${escRe(key)}\\}\\s*`, 'g');
    const m = re.exec(text || '');
    if (!m) return null;
    const g = T.readGroup(text, m.index + m[0].length);
    return g ? g.content : null;
  };
  let latex = look(src.part.tex.get(`lab/${ns}/values.tex`), ns);
  if (latex == null && src.strip) for (const t of src.part.tex.values()) if ((latex = look(t, `${src.strip}/${ns}`)) != null) break;
  if (latex == null) return null;
  const r = src.results.find((x) => x.slug === ns);
  const v = r && r.items.filter((i) => i.kind === 'values').flatMap((i) => i.values || []).find((x) => x.key === key);
  return { latex, label: v ? v.label : key, text: v ? v.text : null };
}

/** Short JSON for the import dialog (no LaTeX bodies, no file contents). */
function summary(src, p) {
  const out = { key: p.key, kind: p.kind, title: p.title, detail: p.detail || null, unit: p.unit || null, preview: p.preview || null, label: p.label || null };
  if (p.latex) {
    const a = analyze(src, p.latex);
    out.snippet = p.latex.length > 1200 ? p.latex.slice(0, 1200) + '\n…' : p.latex;
    out.needs = { files: a.files.length, cites: a.cites.length, macros: a.defs.map((d) => d.key.replace(/^\w+:/, '')), packages: [...a.packages.keys()], values: a.values.length, missing: a.missing, missingKeys: a.missingKeys };
  }
  if (p.kind === 'values') out.values = p.values;
  if (p.kind === 'result') Object.assign(out, { slug: p.slug, revision: p.revision });
  if (p.kind === 'data') out.size = p.size;
  return out;
}

/** Content hash of a piece: its text, the files and .bib entries it uses and the macros it needs. */
async function pieceHash(src, p) {
  const h = crypto.createHash('sha256');
  h.update(p.kind + '\n');
  const fileHash = async (rel) => {
    try {
      h.update(unstrip(src, rel) + ':' + crypto.createHash('sha256').update(await fsp.readFile(path.join(src.dir, ...rel.split('/')))).digest('hex') + '\n');
    } catch {
      h.update(unstrip(src, rel) + ':missing\n');
    }
  };
  if (p.latex) {
    const a = analyze(src, p.latex);
    h.update(unstrip(src, p.latex));
    for (const f of a.files) await fileHash(f);
    for (const e of a.bib) h.update(unstrip(src, e.raw));
    // same hash for a report and its portable export: \newcommand vs \providecommand, prefixed namespaces
    for (const d of a.defs) h.update(d.key + '=' + d.code.trim().replace(/^\\(?:newcommand|providecommand)/, '\\newcommand') + '\n');
    for (const v of a.values) {
      const ns = unstrip(src, v.ns);
      h.update(`${ns}/${v.key}=${(valueOf(src, ns, v.key) || {}).latex || ''}\n`);
    }
  } else if (p.file) await fileHash(p.file);
  else if (p.kind === 'values') h.update(JSON.stringify(p.values));
  else if (p.kind === 'result') {
    const r = src.results.find((x) => x.slug === p.slug);
    h.update(JSON.stringify({ id: r && r.result_id, rev: r && r.revision, updated: r && r.updated }));
  }
  return h.digest('hex');
}

module.exports = { loadSource, listPieces, analyze, summary, pieceHash, valueOf, readResults, unstrip, maskComments, PKG_HINTS, EXCLUDED_RE };
