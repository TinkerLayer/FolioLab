'use strict';
// Checks for the text helpers of Folio Lab results in .tex files (public/js/editor/labuses.mjs): placement of figure
// floats. No server, no browser. Usage: node tools/test_lab_uses.js
const assert = require('node:assert/strict');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

const tests = [];
const test = (name, fn) => tests.push([name, fn]);

const FIG = '\\begin{figure}[htbp]\n\t\\centering\n\t\\includegraphics[width=0.9\\linewidth]{lab/zv-1-verlauf/fig/verlauf}\n\t\\caption{Verlauf}\n\t\\label{fig:zv-1-verlauf}\n\\end{figure}';

test('cleanPlace keeps known values only', (U) => {
  assert.deepEqual(U.cleanPlace({ width: 3, pos: 'x', align: 'right' }), { width: 1, align: 'right' });
  assert.deepEqual(U.cleanPlace({ width: 'full', pos: 'H' }), { width: 'full', pos: 'H' });
  assert.deepEqual(U.cleanPlace({ width: '', pos: 'htbp' }), { pos: 'htbp' });
  assert.deepEqual(U.cleanPlace(null), {});
});

test('placeFloat sets width, position and alignment', (U) => {
  const out = U.placeFloat(FIG, { width: 0.5, pos: 'H', align: 'left' });
  assert.match(out, /^\\begin\{figure\}\[H\]/);
  assert.match(out, /\\raggedright/);
  assert.doesNotMatch(out, /\\centering/);
  assert.match(out, /\\includegraphics\[width=0\.5\\linewidth\]\{lab\/zv-1-verlauf\/fig\/verlauf\}/);
  assert.match(out, /\\end\{figure\}$/);
});

test('full width uses figure* and back', (U) => {
  const wide = U.placeFloat(FIG, { width: 'full' });
  assert.match(wide, /^\\begin\{figure\*\}\[htbp\]/);
  assert.match(wide, /width=\\textwidth/);
  assert.match(wide, /\\end\{figure\*\}$/);
  const back = U.placeFloat(wide, { width: 0.8 });
  assert.match(back, /^\\begin\{figure\}\[htbp\]/);
  assert.match(back, /\\end\{figure\}$/);
});

test('placeAll touches only floats of that figure and keeps other options', (U) => {
  const other = FIG.replace(/verlauf/g, 'linear');
  const withAngle = FIG.replace('[width=0.9\\linewidth]', '[angle=90, width=0.9\\linewidth]');
  const text = `Intro\n${withAngle}\n\nMore\n${other}\n`;
  const r = U.placeAll(text, 'lab/zv-1-verlauf/fig/verlauf', { pos: 't', width: 0.6 });
  assert.equal(r.n, 1);
  assert.match(r.text, /\\begin\{figure\}\[t\]\n\t\\centering\n\t\\includegraphics\[width=0\.6\\linewidth, angle=90\]\{lab\/zv-1-verlauf/);
  assert.ok(r.text.includes(other));
  assert.ok(r.text.startsWith('Intro\n'));
});

test('figureFloat for inserting', (U) => {
  const t = U.figureFloat({ path: 'lab/a/fig/b', caption: 'C', label: 'fig:a', width: 0.7, place: { align: 'right', pos: 'b' } });
  assert.equal(t, '\\begin{figure}[b]\n\t\\raggedleft\n\t\\includegraphics[width=0.7\\linewidth]{lab/a/fig/b}\n\t\\caption{C}\n\t\\label{fig:a}\n\\end{figure}\n');
  assert.match(U.figureFloat({ path: 'p', caption: '', label: 'l' }), /\[htbp\]\n\t\\centering\n\t\\includegraphics\[width=0\.9\\linewidth\]/);
});

test('zoomFromBox maps a dragged box to limits (linear, log, twins)', (U) => {
  const ax = { box: [0.1, 0.1, 0.9, 0.9], xlim: [0, 100], ylim: [0, 10], xscale: 'linear', yscale: 'linear' };
  const twin = { ...ax, ylim: [0, 1000], yscale: 'log' };
  // drag from (30 %, 30 %) to (50 %, 70 %) of the image, i.e. 25..50 % of the plot in x and 25..75 % in y
  const z = U.zoomFromBox([ax, { ...twin, ylim: [1, 1000] }], 0.5, 0.7, 0.3, 0.3);
  assert.equal(z.length, 2);
  assert.deepEqual(z[0], { i: 0, xmin: 25, xmax: 50, ymin: 2.5, ymax: 7.5 });
  assert.equal(z[1].ymin, +(10 ** 0.75).toPrecision(4));      // log: a quarter of three decades
  assert.equal(z[1].ymax, +(10 ** 2.25).toPrecision(4));
  assert.deepEqual(U.zoomFromBox([ax], 0.05, 0.05, 0.5, 0.5), []);   // starts outside the plot
  assert.deepEqual(U.zoomFromBox([null, ax], 0.5, 0.5, 0.6, 0.6).map((r) => r.i), [1]);
});

const INFO = {
  slug: 'zv-1', lang: 'de', labels: ['fig:zv-1-verlauf', 'tab:zv-1-kennwerte', 'eq:zv-1-hooke'], keys: ['iso6892-1', 'data-zv-1'],
  values: { Rm: '140\\,MPa' }, numbers: { 'fig:zv-1-verlauf': { num: '3', page: '7' }, 'tab:zv-1-kennwerte': { num: '2', page: '6' } },
  section: 'sections/zv-1.tex',
};
const DOC = String.raw`\section{Ergebnisse}
Die Zugfestigkeit betrug \labval{zv-1}{Rm} (\cref{fig:zv-1-verlauf}), siehe auch Tabelle~\ref{tab:zv-1-kennwerte}
und \cref{fig:zv-1-verlauf,fig:other} sowie Seite~\pageref{fig:zv-1-verlauf}.
Geprüft nach Norm~\cite{iso6892-1}; Werkstoffdaten~\cite[S.~3]{iso6892-1,mat-a}. Fremd: \labval{zv-2}{Rm}~\cite{own}.
\begin{figure}[htbp]
	\centering
	\includegraphics[width=0.9\linewidth]{lab/zv-1/fig/verlauf}
	\caption{Verlauf~\cite{data-zv-1}}
	\label{fig:zv-1-verlauf}
\end{figure}
\begin{table}[htbp]
	\caption{Kennwerte}
	\input{lab/zv-1/kennwerte}
\end{table}
\begin{figure}[htbp]
	\includegraphics{lab/zv-1-2/fig/verlauf}
\end{figure}
% \input{lab/zv-1/text-methodik}
\input{lab/zv-1/text-methodik-auswahl}
\input{sections/zv-1}
Ende.
`;

test('findUses lists floats, inputs, values, references and citations of one result', (U) => {
  const uses = U.findUses({ 'main.tex': DOC, 'lab/zv-1/text-methodik.tex': '\\cite{iso6892-1}', 'sections/zv-1.tex': '\\labval{zv-1}{Rm}' }, INFO);
  const by = (k) => uses.filter((u) => u.kind === k);
  assert.ok(uses.every((u) => u.file === 'main.tex'));
  assert.equal(by('float').length, 2);                                     // not the float of zv-1-2
  assert.match(by('float')[0].what, /figure “Verlauf/);
  assert.deepEqual(by('input').map((u) => u.what), ['\\input{lab/zv-1/text-methodik-auswahl}']);   // not the commented one
  assert.equal(by('section').length, 1);
  assert.deepEqual(by('value').map((u) => u.replace), ['\\labstale[zv-1]{140\\,MPa}']);
  assert.deepEqual(by('ref').map((u) => [u.action, u.replace]), [
    ['freeze', '\\labstale[zv-1]{Abb.~3}'], ['freeze', '\\labstale[zv-1]{2}'], ['drop', '\\cref{fig:other}'], ['freeze', '\\labstale[zv-1]{7}']]);
  assert.deepEqual(by('cite').map((u) => [u.action, u.replace]), [['remove', ''], ['drop', '\\cite[S.~3]{mat-a}']]);
  assert.equal(by('value')[0].line, 2);
});

test('applyUses takes the result out and leaves the rest as it was', (U) => {
  const uses = U.findUses({ 'main.tex': DOC }, INFO);
  const out = U.applyUses(DOC, uses);
  assert.doesNotMatch(out, /lab\/zv-1\/(?!text-methodik\})|\\labval\{zv-1\}|\\input\{sections\/zv-1\}|iso6892-1|data-zv-1/);
  assert.match(out, /betrug \\labstale\[zv-1\]\{140\\,MPa\} \(\\labstale\[zv-1\]\{Abb\.~3\}\)/);
  assert.match(out, /Geprüft nach Norm; Werkstoffdaten~\\cite\[S\.~3\]\{mat-a\}\. Fremd: \\labval\{zv-2\}\{Rm\}~\\cite\{own\}\./);
  assert.match(out, /\\includegraphics\{lab\/zv-1-2\/fig\/verlauf\}/);
  assert.match(out, /% \\input\{lab\/zv-1\/text-methodik\}\nEnde\.\n$/);       // whole lines gone, comment kept
  assert.doesNotMatch(out, /\\begin\{table\}/);
});

test('plainTex shows values as printed', (U) => {
  assert.equal(U.plainTex('140\\,MPa'), '140 MPa');
  assert.equal(U.plainTex('21,1\\,\\%'), '21,1 %');
  assert.equal(U.plainTex('Verlauf~\\cite{x} \\emph{neu}'), 'Verlauf neu');
});

test('without numbers from a compile the reference freezes as ??', (U) => {
  const uses = U.findUses({ 'a.tex': 'See \\ref{eq:zv-1-hooke} and \\eqref{eq:zv-1-hooke}.' }, { ...INFO, lang: 'en' });
  assert.deepEqual(uses.map((u) => u.replace), ['\\labstale[zv-1]{??}', '\\labstale[zv-1]{(??)}']);
  assert.deepEqual(U.findUses({ 'a.tex': 'Nothing here. \\cite{other}' }, INFO), []);
});

(async () => {
  const U = await import(pathToFileURL(path.join(__dirname, '..', 'public', 'js', 'editor', 'labuses.mjs')).href);
  let failed = 0;
  for (const [name, fn] of tests) {
    try {
      await fn(U);
      console.log(`ok   ${name}`);
    } catch (e) {
      failed++;
      console.log(`FAIL ${name}\n     ${e.message.split('\n').join('\n     ')}`);
    }
  }
  console.log(`${tests.length - failed} of ${tests.length} checks passed`);
  process.exit(failed ? 1 : 0);
})();
