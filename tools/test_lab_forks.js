'use strict';
// Checks for variants (forks) of a result and for changing the methods selection afterwards (no server, no module).
// Usage: node tools/test_lab_forks.js
const assert = require('node:assert/strict');
const os = require('node:os');
const path = require('node:path');
const fs = require('node:fs');

// keep every path the server modules compute away from real data
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'folio-fork-test-'));
process.env.FOLIO_PROJECTS_DIR = path.join(tmp, 'projects');
process.env.FOLIO_SUITE_DIR = path.join(tmp, 'projects', '_suite');
process.env.LAB_OUTPUTS = path.join(tmp, 'out');

const P = require('../server/projects');
const lab = require('../server/lab');

const b64 = (s) => Buffer.from(s, 'utf8').toString('base64');
const TABLE = '\\begin{tabular}{lrr}\n\\toprule\nProbe & $R_m$ [MPa] & $A$ [\\%]\\\\\n\\midrule\nP1 & 412.345 & 21.06\\\\\nP2 & 398.1 & 19.5\\\\\n\\bottomrule\n\\end{tabular}\n';

let n = 0;
const tests = [];
const test = (name, fn) => tests.push([name, fn]);

test('tableVariant hides columns and sets decimals', () => {
  const out = lab.tableVariant(TABLE, { hide: [2], digits: 1 });
  assert.match(out, /\\begin\{tabular\}\{lr\}/);
  assert.match(out, /P1 & 412\.3\s*\\\\/);
  assert.match(out, /P2 & 398\.1\s*\\\\/);
  assert.doesNotMatch(out, /21\.06|\[\\%\]/);
  assert.equal(lab.tableVariant(TABLE, { hide: [], digits: null }), TABLE);
});

test('tableVariant keeps the decimal comma and refuses what it cannot rewrite', () => {
  const de = TABLE.replace('412.345', '412,345').replace('398.1', '398,1').replace('21.06', '21,06').replace('19.5', '19,5');
  assert.match(lab.tableVariant(de, { hide: [], digits: 2 }), /412,35 & 21,06/);
  assert.throws(() => lab.tableVariant(TABLE.replace('Probe &', '\\multicolumn{2}{c}{x} &'), { hide: [1], digits: null }), /cannot be hidden/);
  assert.throws(() => lab.tableVariant(TABLE.replace('{lrr}', '{l|rr}'), { hide: [1], digits: null }), /cannot be hidden/);
  assert.throws(() => lab.tableVariant(TABLE, { hide: [0, 1, 2], digits: null }), /At least one column/);
});

let id;
const base = {
  format: lab.FORMAT,
  slug: 'zug',
  title: 'Zugversuch',
  module: 'zugversuch',
  module_version: '1.0.0',
  lang: 'de',
  items: [
    { kind: 'figure', id: 'feld', file: 'fig/feld.pdf', preview: 'fig/feld.png', caption: 'Feld~\\cite{iso}', label: 'fig:zug-feld' },
    { kind: 'table', id: 'kennwerte', file: 'kennwerte.tex', caption: 'Kennwerte', label: 'tab:zug-kennwerte' },
    {
      kind: 'text', id: 'methodik', title: 'Methodik', file: 'text-methodik.tex', methods: true,
      steps: [
        { id: 's1', title: 'Probe', short: true, par: 0, file: 'methods/s1.tex' },
        { id: 's2', title: 'Fit', short: false, par: 0, file: 'methods/s2.tex' },
      ],
    },
    { kind: 'citation', key: 'iso', title: 'ISO 6892-1' },
  ],
  files: {
    'fig/feld.pdf': b64('%PDF-1.4 fake'),
    'fig/feld.png': b64('png'),
    'kennwerte.tex': b64(TABLE),
    'text-methodik.tex': b64('Eins. Zwei.\n'),
    'methods/s1.tex': b64('Eins.\n'),
    'methods/s2.tex': b64('Zwei.\n'),
  },
  source: null,
};
const read = (slug, rel) => fs.readFileSync(path.join(lab.labDir(id), slug, rel), 'utf8');

test('a table variant is its own result; the original stays as it is', async () => {
  const v = await lab.fork(id, 'zug', { item: 'kennwerte', caption: 'Nur Rm', table: { hide: [2], digits: 0 }, mode: 'snapshot' });
  assert.notEqual(v.slug, 'zug');
  assert.equal(v.fork.of, 'zug');
  assert.equal(v.fork.mode, 'snapshot');
  const it = v.items.find((i) => i.id === 'kennwerte');
  assert.equal(it.caption, 'Nur Rm');
  assert.equal(it.hidden, undefined);
  assert.equal(it.label, `tab:${v.slug}`); // own label: the original and the variant can both be in the report
  assert.equal(v.items.find((i) => i.id === 'feld').hidden, true);
  assert.match(read(v.slug, 'kennwerte.tex'), /P1 & 412\s*\\\\/);
  assert.equal(read('zug', 'kennwerte.tex'), TABLE);
  assert.equal((await lab.readManifest(id, 'zug')).items.find((i) => i.id === 'kennwerte').caption, 'Kennwerte');
});

test('editing a variant again updates it in place; via the variant\'s own slug as well', async () => {
  const [v] = await lab.forksOf(id, 'zug');
  const again = await lab.fork(id, v.slug, { item: 'kennwerte', caption: 'Rm und A', table: { hide: [], digits: 1 }, mode: 'live' });
  assert.equal(again.slug, v.slug);
  assert.equal(again.fork.mode, 'live');
  assert.equal(again.revision, 2);
  assert.match(read(v.slug, 'kennwerte.tex'), /412\.3 & 21\.1/);
  assert.equal((await lab.forksOf(id, 'zug')).length, 1);
});

test('a text variant keeps its own wording; a figure without a stored source cannot be restyled', async () => {
  const t = await lab.fork(id, 'zug', { item: 'methodik', text: 'Eigene Fassung.\n' });
  assert.equal(read(t.slug, 'text-methodik.tex'), 'Eigene Fassung.\n');
  assert.equal(t.items.find((i) => i.id === 'methodik').shown_file, undefined);
  await assert.rejects(lab.fork(id, 'zug', { item: 'feld', style: { preset: 'elsevier-1' } }), /cannot redraw/);
  const f = await lab.fork(id, 'zug', { item: 'feld', caption: 'Nur die Beschriftung' });
  assert.equal(f.items.find((i) => i.id === 'feld').caption, 'Nur die Beschriftung');
  await assert.rejects(lab.fork(id, 'zug', { item: 'nichts' }), /Choose a figure/);
  assert.equal((await lab.forksOf(id, 'zug')).length, 3);
});

test('repick changes the methods selection without a new computation', async () => {
  const r = await lab.repick(id, 'zug', { methods: { mode: 'custom', steps: ['s2'], eq: false } });
  const m = r.items.find((i) => i.id === 'methodik');
  assert.equal(m.shown_file, 'text-methodik-auswahl.tex');
  assert.deepEqual(m.shown_steps, ['s2']);
  assert.equal(read('zug', 'text-methodik-auswahl.tex'), 'Zwei.\n');
  assert.equal(read('zug', 'text-methodik.tex'), 'Eins. Zwei.\n'); // the full text stays
  const full = await lab.repick(id, 'zug', { methods: { mode: 'full', eq: true } });
  assert.equal(full.items.find((i) => i.id === 'methodik').shown_file, undefined);
});

test('an edited sentence replaces the module\'s and is flagged when the module changes it', async () => {
  const r = await lab.repick(id, 'zug', { methods: { mode: 'full', eq: true, edits: { s2: { text: 'Zwei, eigene Fassung.', orig: 'Zwei.' }, 'bad key!': { text: 'x' } } } });
  const m = r.items.find((i) => i.id === 'methodik');
  assert.equal(m.shown_file, 'text-methodik-auswahl.tex');
  assert.deepEqual(m.edited_steps, ['s2']);
  assert.equal(m.edited_changed, undefined);
  assert.equal(read('zug', 'text-methodik-auswahl.tex'), 'Eins. Zwei, eigene Fassung.\n');
  assert.deepEqual(Object.keys(r.pick.methods.edits), ['s2']);
  // the module's sentence is now different from the one the user replaced
  fs.writeFileSync(path.join(lab.labDir(id), 'zug', 'methods', 's2.tex'), 'Zwei, neu berechnet.\n');
  const again = await lab.repick(id, 'zug', {});
  const m2 = again.items.find((i) => i.id === 'methodik');
  assert.deepEqual(m2.edited_changed, ['s2']);
  assert.match(again.warnings.join(' '), /changed a sentence you edited/);
  assert.equal(read('zug', 'text-methodik-auswahl.tex'), 'Eins. Zwei, eigene Fassung.\n');
  // short: an edit of a sentence that is not shown changes nothing
  const short = await lab.repick(id, 'zug', { methods: { mode: 'short', eq: false, edits: { s2: { text: 'X', orig: 'Zwei.' } } } });
  assert.equal(short.items.find((i) => i.id === 'methodik').edited_steps, undefined);
});

test('uses-info lists labels, own keys, values and compiled numbers; remove goes to the bin and undo brings it back', async () => {
  const r = await lab.save(id, { ...base, slug: 'weg', items: [...base.items.map((i) => (i.label ? { ...i, label: i.label.replace('zug', 'weg') } : i)), { kind: 'citation', key: 'own-k', title: 'Own' }] }, 'new', { action: 'test' });
  const slug = r.slug;
  fs.writeFileSync(path.join(lab.labDir(id), slug, 'refs.bib'), '@misc{iso,\n title={ISO}\n}\n@misc{own-k,\n title={Own}\n}\n');
  fs.writeFileSync(path.join(lab.labDir(id), 'zug', 'refs.bib'), '@misc{iso,\n title={ISO}\n}\n');
  fs.writeFileSync(path.join(lab.labDir(id), slug, 'values.tex'), '\\labset{weg}{Rm}{140\\,MPa}%\n');
  fs.mkdirSync(P.buildDir(id), { recursive: true });
  fs.writeFileSync(path.join(P.buildDir(id), 'main.aux'), `\\newlabel{fig:${slug}-feld}{{4}{9}{Feld}{figure.4}{}}\n`);
  fs.mkdirSync(path.join(P.filesDir(id), 'sections'), { recursive: true });
  fs.writeFileSync(path.join(P.filesDir(id), 'sections', `${slug}.tex`), 'Abschnitt\n');
  const info = await lab.usesInfo(id, slug);
  assert.ok(info.labels.includes(`fig:${slug}-feld`));
  assert.deepEqual(info.keys, ['own-k']);              // iso is provided by "zug" as well
  assert.deepEqual(info.shared_keys, ['iso']);
  assert.equal(info.values.Rm, '140\\,MPa');
  assert.deepEqual(info.numbers[`fig:${slug}-feld`], { num: '4', page: '9' });
  assert.equal(info.section, `sections/${slug}.tex`);
  const gone = await lab.remove(id, slug, { section: true });
  assert.ok(gone.undo);
  assert.equal(fs.existsSync(path.join(lab.labDir(id), slug)), false);
  assert.equal(fs.existsSync(path.join(P.filesDir(id), 'sections', `${slug}.tex`)), false);
  assert.doesNotMatch(fs.readFileSync(path.join(lab.labDir(id), 'references.bib'), 'utf8'), /own-k/);
  const back = await lab.restoreRemoved(id, gone.undo);
  assert.equal(back.slug, slug);
  assert.equal(read(slug, 'values.tex'), '\\labset{weg}{Rm}{140\\,MPa}%\n');
  assert.equal(fs.readFileSync(path.join(P.filesDir(id), 'sections', `${slug}.tex`), 'utf8'), 'Abschnitt\n');
  assert.match(fs.readFileSync(path.join(lab.labDir(id), 'references.bib'), 'utf8'), /own-k/);
  await assert.rejects(lab.restoreRemoved(id, gone.undo), /no longer be undone/);
  await assert.rejects(lab.restoreRemoved(id, '../x'), /Nothing to restore/);
});

(async () => {
  try {
    id = (await P.createSkeleton({ name: 'Fork test' })).id;
    await lab.save(id, base, 'new', { action: 'test' });
    for (const [name, fn] of tests) {
      await fn();
      n++;
      console.log(`ok  ${name}`);
    }
    console.log(`${n} checks passed.`);
  } catch (e) {
    console.error(e);
    process.exitCode = 1;
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
})();
