'use strict';
// Check of the report import and the portable ZIP (server/portable.js, pieces.js, importer.js).
// Runs on a temporary projects folder, never on the user's projects:  node tools/test_report_import.js
// With a TeX distribution (bundled MiKTeX or PATH) it also compiles the portable ZIP on its own, inside a foreign
// natbib/BibTeX document and inside a biblatex document, and the report that received the imports.
const os = require('os');
const path = require('path');
const fs = require('fs');
const assert = require('assert');
const { spawnSync } = require('child_process');

const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'folio-import-'));
process.env.FOLIO_PROJECTS_DIR = TMP;
process.env.FOLIO_SUITE_DIR = path.join(TMP, '_suite');
const P = require('../server/projects');
const lab = require('../server/lab');
const modules = require('../server/modules');
const combiner = require('../server/combine');
const portable = require('../server/portable');
const importer = require('../server/importer');
const { readZip, createZip } = require('../server/zip');
const tex = require('../server/tex');

const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==', 'base64');
const b64 = (s) => Buffer.from(s).toString('base64');
const files = (id) => P.filesDir(id);
const write = (id, rel, data) => {
  const abs = path.join(files(id), ...rel.split('/'));
  fs.mkdirSync(path.dirname(abs), { recursive: true });
  fs.writeFileSync(abs, data);
};
const read = (id, rel) => fs.readFileSync(path.join(files(id), ...rel.split('/')), 'utf8');

function sourceMain(eq = 'E = \\sigma / \\varepsilon') {
  return String.raw`\documentclass[11pt,a4paper]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage[ngerman]{babel}
\usepackage{graphicx}
\usepackage{amsmath}
\usepackage[backend=biber,style=numeric]{biblatex}
\usepackage{hyperref}
\addbibresource{references.bib}
\addbibresource{lab/references.bib}
\input{lab/labdata}
\newcommand{\Rm}{R_\mathrm{m}}
\newcommand{\Emod}{E_{\Rm}}
\title{Quelle}
\begin{document}
\maketitle
\section{Einleitung}
Nach \cite{mueller2021} gilt Abbildung~\ref{fig:probe}.
\begin{figure}[htbp]
  \centering
  \includegraphics[width=0.5\linewidth]{figs/probe}
  \caption{Probe nach \cite{mueller2021}.}
  \label{fig:probe}
\end{figure}
\begin{equation}
  \Emod = ${eq}
  \label{eq:hooke}
\end{equation}
\section{Ergebnisse}
Die Festigkeit ist \labval{probe}{rm}; siehe Gleichung~\eqref{eq:hooke}.
\[ \Rm = F_\mathrm{max} / S_0 \]
\printbibliography
\end{document}
`;
}
const BIB = `@article{mueller2021,
  author = {M{\\"u}ller, Anna},
  title = {Zugversuche},
  journaltitle = {Werkstoffe},
  date = {2021},
}
`;
function probeBundle(value) {
  return {
    format: lab.FORMAT, module: 'testmod', module_name: 'Test', title: 'Probe', slug: 'probe', lang: 'de', created: '2026-11-18T00:00:00Z',
    items: [
      { kind: 'figure', id: 'kurve', file: 'fig/kurve.png', caption: 'Kurve', label: 'fig:probe-kurve' },
      { kind: 'values', file: 'values.tex', values: [{ key: 'rm', label: 'Rm: Zugfestigkeit', latex: `$${value}\\,\\mathrm{MPa}$`, text: `${value} MPa` }] },
    ],
    files: { 'values.tex': b64(`\\labset{probe}{rm}{$${value}\\,\\mathrm{MPa}$}% Rm\n`), 'fig/kurve.png': PNG.toString('base64') },
    source: { request: { a: 1 }, files: { 'messung.csv': b64('x;y\n1;2\n') } },
  };
}

// --- a minimal .npy / .npz writer for a data.table share
function npy(values, descr) {
  let head = `{'descr': '${descr}', 'fortran_order': False, 'shape': (${values.length},), }`;
  const pad = 64 - ((10 + head.length + 1) % 64);
  head = head + ' '.repeat(pad % 64) + '\n';
  const h = Buffer.alloc(10);
  Buffer.from([0x93, 0x4e, 0x55, 0x4d, 0x50, 0x59, 1, 0]).copy(h);
  h.writeUInt16LE(head.length, 8);
  let body;
  if (descr === '<f8') {
    body = Buffer.alloc(8 * values.length);
    values.forEach((v, i) => body.writeDoubleLE(v, 8 * i));
  } else {
    const n = Math.max(...values.map((v) => v.length));
    body = Buffer.alloc(4 * n * values.length);
    values.forEach((v, i) => [...v].forEach((c, j) => body.writeUInt32LE(c.codePointAt(0), 4 * (n * i + j))));
  }
  return Buffer.concat([h, Buffer.from(head, 'latin1'), body]);
}

function texRun(dir, main, bib) {
  const t = tex.detect();
  if (!t.found) return null;
  const run = (exe, args) => spawnSync(tex.tool(exe), args, { cwd: dir, env: tex.texEnv(), encoding: 'utf8', timeout: 240000 });
  run('pdflatex', ['-interaction=nonstopmode', '-halt-on-error', main]);
  if (bib) run(bib, [main]);
  run('pdflatex', ['-interaction=nonstopmode', '-halt-on-error', main]);
  const r = run('pdflatex', ['-interaction=nonstopmode', '-halt-on-error', main]);
  const log = fs.existsSync(path.join(dir, main + '.log')) ? fs.readFileSync(path.join(dir, main + '.log'), 'latin1') : '';
  return { code: r.status, pdf: fs.existsSync(path.join(dir, main + '.pdf')), errors: log.split('\n').filter((l) => /^! |undefined|multiply defined/.test(l)) };
}

(async () => {
  let ok = 0;
  const step = (name) => {
    ok++;
    console.log(`ok ${ok} - ${name}`);
  };
  try {
    modules.get = async () => ({ id: 'testmod', version: '1.0.0', bundle: {} });
    let nextValue = 500;
    modules.call = async () => probeBundle(nextValue++);

    // ---------------------------------------------------------------- source report
    const S = (await P.createProject({ name: 'Quelle Bericht', template: 'lab-report' })).id;
    write(S, 'main.tex', sourceMain());
    write(S, 'references.bib', BIB);
    write(S, 'figs/probe.png', PNG);
    await lab.save(S, probeBundle(480));
    const T = (await P.createProject({ name: 'Ziel', template: 'lab-report' })).id;

    // ---------------------------------------------------------------- pieces
    const listed = await importer.pieces({ type: 'report', project: S });
    const keys = listed.pieces.map((p) => p.key);
    for (const k of ['figure:fig:probe', 'equation:eq:hooke', 'section:ergebnisse', 'section:einleitung', 'result:probe', 'values:probe', 'image:figs/probe.png', 'image:lab/probe/fig/kurve.png'])
      assert.ok(keys.includes(k), `piece ${k} missing: ${keys.join(', ')}`);
    const eq = listed.pieces.find((p) => p.key === 'equation:eq:hooke');
    assert.deepStrictEqual(eq.needs.macros.sort(), ['Emod', 'Rm'], 'macro closure (\\Emod uses \\Rm)');
    assert.ok(!eq.needs.packages.includes('amsmath'), 'equation is plain LaTeX');
    assert.ok(listed.pieces.find((p) => p.key === 'section:ergebnisse').needs.packages.includes('amsmath'), '\\eqref needs amsmath');
    assert.strictEqual(listed.pieces.find((p) => p.key === 'figure:fig:probe').needs.cites, 1);
    assert.ok(listed.pieces.some((p) => p.kind === 'equation' && /F_\\mathrm\{max\}/.test(p.title)), 'display math listed');
    step('extractor lists figures, equations, sections, results, values and images with their needs');

    // ---------------------------------------------------------------- import (live)
    const r1 = await importer.importPieces(T, { source: { type: 'report', project: S }, keys: ['figure:fig:probe', 'equation:eq:hooke', 'section:ergebnisse'] });
    const m1 = r1.results[0];
    const slug = m1.slug;
    assert.strictEqual(m1.module, 'import');
    assert.strictEqual(m1.link.mode, 'live');
    const fig = m1.items.find((i) => i.kind === 'figure');
    assert.strictEqual(fig.label, `${slug}:fig:probe`);
    assert.ok(fs.existsSync(path.join(files(T), 'lab', slug, fig.file)), 'figure file copied');
    assert.match(fig.caption, /\\cite\{mueller2021\}/);
    const eqItem = m1.items.find((i) => i.kind === 'text' && i.piece === 'equation');
    const eqTex = read(T, `lab/${slug}/${eqItem.file}`);
    assert.match(eqTex, new RegExp(`\\\\label\\{${slug}:eq:hooke\\}`));
    const pre = read(T, `lab/${slug}/preamble.tex`);
    assert.match(pre, /\\providecommand\{\\Rm\}/);
    assert.match(pre, /\\providecommand\{\\Emod\}/);
    assert.match(pre, /\\@ifpackageloaded\{amsmath\}\{\}\{\\@ifpackageloaded\{cleveref\}\{[^\n]*\}\{\\usepackage\{amsmath\}\}\}/);
    const sec = read(T, `lab/${slug}/${m1.items.find((i) => i.piece === 'section').file}`);
    assert.match(sec, new RegExp(`\\\\labval\\{${slug}\\}\\{rm\\}`));
    assert.match(sec, new RegExp(`\\\\eqref\\{${slug}:eq:hooke\\}`));
    assert.match(read(T, `lab/${slug}/values.tex`), new RegExp(`\\\\labset\\{${slug}\\}\\{rm\\}\\{\\$480`));
    assert.match(read(T, 'lab/references.bib'), /@article\{mueller2021,/);
    assert.match(read(T, 'lab/labdata.tex'), new RegExp(`\\\\InputIfFileExists\\{lab/${slug}/preamble\\}`));
    step('import of a figure, an equation and a section brings files, labels, citations, macros, packages and values');

    // ---------------------------------------------------------------- link states
    let st = (await importer.linkStates(T)).find((x) => x.slug === slug);
    assert.strictEqual(st.state, 'current');
    write(S, 'main.tex', sourceMain('\\sigma \\cdot 2'));
    st = (await importer.linkStates(T)).find((x) => x.slug === slug);
    assert.strictEqual(st.state, 'stale');
    assert.deepStrictEqual(st.changed, ['equation:eq:hooke']);
    const up = await importer.update(T, slug, {});
    assert.strictEqual(up.revision, 2);
    assert.match(read(T, `lab/${slug}/${eqItem.file}`), /\\sigma \\cdot 2/);
    assert.strictEqual((await importer.linkStates(T)).find((x) => x.slug === slug).state, 'current');
    await importer.setMode(T, slug, 'pin');
    write(S, 'main.tex', sourceMain('\\sigma \\cdot 3'));
    assert.strictEqual((await importer.linkStates(T)).find((x) => x.slug === slug).state, 'update');
    step('live link: current, stale after a source change, Update rebuilds (new revision); pin offers an update');

    // copy: no link state; a key clash gets a new key
    write(T, 'references.bib', '@book{mueller2021,\n  author = {Other},\n  title = {Different},\n  date = {1999},\n}\n');
    const rc = await importer.importPieces(T, { source: { type: 'report', project: S }, keys: ['section:einleitung'], mode: 'copy' });
    const mc = rc.results[0];
    assert.strictEqual((await importer.linkStates(T)).find((x) => x.slug === mc.slug).state, null);
    const intro = read(T, `lab/${mc.slug}/${mc.items.find((i) => i.kind === 'text').file}`);
    assert.match(intro, new RegExp(`\\\\cite\\{mueller2021-${mc.slug}\\}`), 'clashing key renamed');
    assert.ok(rc.warnings.some((w) => /mueller2021/.test(w)));
    fs.rmSync(path.join(files(T), 'references.bib'));
    write(T, 'references.bib', '% own\n');
    step('copy has no link; a citation key that exists differently in the report is renamed');

    // whole result: copied with its measurement files; follows the source result's revision
    const rr = await importer.importPieces(T, { source: { type: 'report', project: S }, keys: ['result:probe'] });
    const mr = rr.results[0];
    assert.strictEqual(mr.module, 'testmod');
    assert.strictEqual(mr.link.type, 'result');
    assert.ok(fs.existsSync(path.join(files(T), 'lab', mr.slug, 'source', 'messung.csv')));
    assert.strictEqual((await importer.linkStates(T)).find((x) => x.slug === mr.slug).state, 'current');
    await lab.refresh(S, 'probe');
    assert.strictEqual((await importer.linkStates(T)).find((x) => x.slug === mr.slug).state, 'stale');
    const mr2 = await importer.update(T, mr.slug, {});
    assert.match(read(T, `lab/${mr.slug}/values.tex`), /500/);
    assert.strictEqual(mr2.link.revision, 2);
    step('a whole analysis result is copied with its measurement files and follows the source revision');

    // ---------------------------------------------------------------- portable ZIP + reconnect
    write(S, 'main.tex', sourceMain());
    const exp = await portable.exportPortable(S, {});
    assert.strictEqual(exp.prefix, 'quelle-bericht');
    const names = readZip(exp.buffer).map((e) => e.name);
    for (const n of ['README.txt', 'main.tex', 'quelle-bericht/body.tex', 'quelle-bericht/preamble.tex', 'quelle-bericht/quelle-bericht.bib', 'quelle-bericht/quelle-bericht-bibtex.bib', 'quelle-bericht/folio-link.json', 'quelle-bericht/figs/probe.png'])
      assert.ok(names.includes(n), `${n} missing from the portable ZIP`);
    assert.ok(!names.some((n) => /\/source\/|\/history\//.test(n)), 'no lab sources or history');
    const body = readZip(exp.buffer).find((e) => e.name === 'quelle-bericht/body.tex').data.toString('utf8');
    assert.match(body, /\\label\{quelle-bericht:fig:probe\}/);
    assert.match(body, /\\cite\{quelle-bericht:mueller2021\}/);
    assert.match(body, /\\labval\{quelle-bericht\/probe\}\{rm\}/);
    assert.match(body, /\\includegraphics\[width=0.5\\linewidth\]\{quelle-bericht\/figs\/probe.png\}/);
    assert.ok(!/\\maketitle|\\printbibliography/.test(body));
    const bibtex = readZip(exp.buffer).find((e) => e.name === 'quelle-bericht/quelle-bericht-bibtex.bib').data.toString('utf8');
    assert.match(bibtex, /journal = \{Werkstoffe\}/);
    assert.match(bibtex, /year = \{2021\}/);
    step('portable ZIP: prefixed folder, labels, keys and value namespaces; BibTeX copy of the references');

    const stage = await combiner.stageZip('Quelle (portable).zip', exp.buffer);
    const zp = await importer.pieces({ type: 'zip', stage: stage.stage });
    assert.ok(zp.source.link && zp.source.link.reconnects);
    const zkeys = zp.pieces.map((p) => p.key);
    assert.ok(zkeys.includes('figure:fig:probe') && zkeys.includes('equation:eq:hooke'), 'same keys as in the report');
    const rz = await importer.importPieces(T, { source: { type: 'zip', stage: stage.stage }, keys: ['equation:eq:hooke', 'section:ergebnisse'] });
    const mz = rz.results[0];
    assert.strictEqual(mz.link.type, 'report');
    assert.strictEqual(mz.link.project, S);
    assert.match(read(T, `lab/${mz.slug}/values.tex`), /\\labset\{[^}]+\}\{rm\}\{\$500/);
    assert.strictEqual((await importer.linkStates(T)).find((x) => x.slug === mz.slug).state, 'current', 'unchanged report: current');
    step('re-imported portable ZIP reconnects to its report (same pieces, link current)');

    // ---------------------------------------------------------------- shares and index values
    const sb = path.join(TMP, '_suite', 'projects', 'standard');
    const share = (id, n, extra) => {
      const d = path.join(sb, 'sharebox', id);
      fs.mkdirSync(d, { recursive: true });
      fs.writeFileSync(path.join(d, `v${n}.json`), JSON.stringify({ schema: 'suite.shared-result/1', id, version: n, ...extra }));
      fs.writeFileSync(path.join(d, 'share.json'), JSON.stringify({ id, latest: n, issued: n, title: extra.title, kind: extra.kind, producer: { module: 'tga' }, modified: '2026-11-18T00:00:00Z' }));
    };
    await require('../server/suite').list();
    share('s-0000000a', 1, { kind: 'tga.steps', title: 'TGA Stufen', outputs: [{ key: 'loss1', label: 'Massenverlust 1', quantity: { value: 12.34, unit: '%', u: 0.2 } }] });
    const npz = createZip([{ name: 't.npy', data: npy([0, 1, 2], '<f8') }, { name: 'm.npy', data: npy([100, 95.5, 90], '<f8') }, { name: 'note.npy', data: npy(['a', 'b,c', 'd'], '<U3') }]);
    share('s-0000000b', 1, { kind: 'data.table', title: 'Messkurve', data: 'v1.npz', dataset: { columns: [{ key: 't', name: 'Zeit', unit: 's', dtype: 'number', role: 'x' }, { key: 'm', name: 'Masse', unit: '%', dtype: 'number', role: 'y' }, { key: 'note', name: 'Notiz', dtype: 'text' }] } });
    fs.writeFileSync(path.join(sb, 'sharebox', 's-0000000b', 'v1.npz'), npz);
    fs.mkdirSync(path.join(sb, 'index'), { recursive: true });
    fs.writeFileSync(path.join(sb, 'index', 'g-0000000c.json'), JSON.stringify({ schema: 'suite.index-entry/1', id: 'g-0000000c', key: 'M(CaCO3)', label: 'Molare Masse CaCO3', quantity: { value: 100.0869, unit: 'g/mol' }, type: 'tabulated' }));
    const sp = await importer.pieces({ type: 'suite' });
    assert.deepStrictEqual(sp.pieces.map((p) => p.key).sort(), ['index:g-0000000c', 'share:s-0000000a', 'share:s-0000000b']);
    const rs = await importer.importPieces(T, { source: { type: 'suite' }, keys: ['share:s-0000000a', 'share:s-0000000b', 'index:g-0000000c'] });
    const ms = rs.results[0];
    const vals = read(T, `lab/${ms.slug}/values.tex`);
    assert.match(vals, /\(12\{,\}34 \\pm 0\{,\}2\)\\,\\mathrm\{\\%\}/);
    assert.match(vals, /100\{,\}09\\,\\mathrm\{g\/mol\}/);
    const csv = read(T, `lab/${ms.slug}/${ms.items.find((i) => i.kind === 'data').file}`);
    assert.strictEqual(csv, 't,m,note\n0,100,a\n1,95.5,"b,c"\n2,90,d\n');
    assert.deepStrictEqual(ms.items.find((i) => i.kind === 'data').plot, { x: 't', y: 'm' });
    assert.strictEqual((await importer.linkStates(T)).find((x) => x.slug === ms.slug).state, 'current');
    assert.deepStrictEqual(lab.list ? (await lab.list(T)).find((b) => b.slug === ms.slug).refs.shares : [], ['s-0000000a v1', 's-0000000b v1'], 'share versions are protected (labprov)');
    share('s-0000000a', 2, { kind: 'tga.steps', title: 'TGA Stufen', outputs: [{ key: 'loss1', label: 'Massenverlust 1', quantity: { value: 13, unit: '%' } }] });
    assert.strictEqual((await importer.linkStates(T)).find((x) => x.slug === ms.slug).state, 'stale');
    await importer.update(T, ms.slug, {});
    assert.match(read(T, `lab/${ms.slug}/values.tex`), /\$13\\,\\mathrm\{\\%\}\$/);
    assert.strictEqual((await importer.linkStates(T)).find((x) => x.slug === ms.slug).state, 'current');
    step('shared values, a shared data table (npz -> CSV) and an index value import, go stale and update');

    // ---------------------------------------------------------------- compile (optional)
    if (!tex.detect().found) {
      console.log('# no TeX distribution: compile checks skipped');
    } else {
      // the report with the imports, used the way the Lab dialog inserts them
      const m = read(T, 'main.tex').replace('\\section{Diskussion}', [
        `\\input{lab/${slug}/${eqItem.file.replace(/\.tex$/, '')}}`,
        `\\begin{figure}[htbp]\\centering\\includegraphics[width=0.3\\linewidth]{lab/${slug}/${fig.file}}\\caption{${fig.caption}}\\label{${fig.label}}\\end{figure}`,
        `\\input{lab/${slug}/${m1.items.find((i) => i.piece === 'section').file.replace(/\.tex$/, '')}}`,
        `\\input{lab/${mz.slug}/${mz.items.find((i) => i.piece === 'equation').file.replace(/\.tex$/, '')}}`,
        `Werte: \\labval{${ms.slug}}{${ms.items.find((i) => i.kind === 'values').values[0].key}}.`,
        '\\section{Diskussion}',
      ].join('\n'));
      write(T, 'main.tex', m);
      const rep = texRun(files(T), 'main', 'biber');
      assert.ok(rep.pdf && rep.code === 0, `report compile failed: ${rep.errors.join(' | ')}`);
      assert.deepStrictEqual(rep.errors, [], 'report: no undefined references or citations');

      const out = path.join(TMP, 'portable');
      for (const e of readZip(exp.buffer)) if (!e.isDir) {
        fs.mkdirSync(path.dirname(path.join(out, e.name)), { recursive: true });
        fs.writeFileSync(path.join(out, e.name), e.data);
      }
      const alone = texRun(out, 'main', 'biber');
      assert.ok(alone.pdf && alone.code === 0 && !alone.errors.length, `portable alone: ${alone.errors.join(' | ')}`);
      const host = (name, preamble, bibLine, bib) => {
        const d = path.join(TMP, name);
        fs.cpSync(path.join(out, 'quelle-bericht'), path.join(d, 'quelle-bericht'), { recursive: true });
        fs.writeFileSync(path.join(d, 'host.bib'), '@article{hostref, author = {Host, H.}, title = {Host}, journal = {J}, year = {2020}}\n');
        fs.writeFileSync(path.join(d, 'main.tex'), `${preamble.replace('\\usepackage{hyperref}', '\\input{quelle-bericht/preamble}\n\\usepackage{hyperref}')}\n\\begin{document}\n\\section{Host}\\label{fig:probe} Own \\cite{hostref}; imported \\ref{quelle-bericht:fig:probe}.\n\\input{quelle-bericht/body}\n${bibLine}\n\\end{document}\n`);
        return texRun(d, 'main', bib);
      };
      const nat = host('host-natbib', '\\documentclass{report}\n\\usepackage[T1]{fontenc}\n\\usepackage[numbers]{natbib}\n\\usepackage{hyperref}', '\\bibliographystyle{plainnat}\n\\bibliography{host,quelle-bericht/quelle-bericht-bibtex}', 'bibtex');
      assert.ok(nat.pdf && nat.code === 0 && !nat.errors.length, `natbib host: ${nat.errors.join(' | ')}`);
      const bl = host('host-biblatex', '\\documentclass{scrartcl}\n\\usepackage[english]{babel}\n\\usepackage{csquotes}\n\\usepackage[style=authoryear]{biblatex}\n\\addbibresource{host.bib}\n\\addbibresource{quelle-bericht/quelle-bericht.bib}\n\\usepackage{hyperref}\n\\usepackage{cleveref}', '\\printbibliography', 'biber');
      assert.ok(bl.pdf && bl.code === 0 && !bl.errors.length, `biblatex host: ${bl.errors.join(' | ')}`);
      step('MiKTeX: the report with imports, the portable ZIP alone, in a natbib/BibTeX host and in a biblatex host compile cleanly');
    }
    console.log(`\n${ok} checks passed`);
  } catch (e) {
    console.error(e);
    process.exitCode = 1;
  } finally {
    fs.rmSync(TMP, { recursive: true, force: true });
  }
})();
