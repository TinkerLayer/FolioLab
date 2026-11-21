'use strict';
// IF: unit checks for the hub side of "Import from Folio" (no server needed).
// Usage: node tools/test_folio_import.js
const assert = require('node:assert/strict');
const os = require('node:os');
const path = require('node:path');
const fs = require('node:fs');

// keep every path the server modules compute away from real data
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'folio-import-test-'));
process.env.FOLIO_PROJECTS_DIR = path.join(tmp, 'projects');
process.env.FOLIO_SUITE_DIR = path.join(tmp, 'projects', '_suite');
process.env.LAB_OUTPUTS = path.join(tmp, 'out');

const lab = require('../server/lab');
const folio = require('../server/folio');

let n = 0;
const test = (name, fn) => {
  fn();
  n++;
  console.log(`ok  ${name}`);
};

const bundle = {
  items: [
    { kind: 'figure', id: 'feld', file: 'fig/feld.pdf', preview: 'fig/feld.png' },
    { kind: 'figure', id: 'kurve', file: 'fig/kurve.pdf' },
    { kind: 'table', id: 'kennwerte', file: 'kennwerte.tex' },
    { kind: 'text', id: 'methodik', title: 'Methodik', file: 'text-methodik.tex' },
    { kind: 'text', id: 'ergebnisse', title: 'Ergebnisse', file: 'text-ergebnisse.tex' },
    { kind: 'values', file: 'values.tex' },
    { kind: 'citation', key: 'iso6892' },
  ],
};

const shown = (r) => r.items.filter((i) => !i.hidden).map((i) => i.id || i.kind);

test('applyPick keeps the whole bundle and marks what is not shown', () => {
  const r = lab.applyPick(bundle, { items: ['feld'], values: ['rm'], methods: true });
  assert.deepEqual(shown(r), ['feld', 'methodik', 'values', 'citation']);
  assert.equal(r.items.length, bundle.items.length);                // nothing dropped (IM-02)
  assert.equal(r.items.find((i) => i.id === 'kurve').hidden, true);
  for (const f of ['fig/feld.pdf', 'fig/kurve.pdf', 'fig/kurve.png', 'kennwerte.tex', 'text-methodik.tex']) assert.equal(r.keep(f), true);
  assert.equal(r.isMethods(bundle.items[3]), true);
  assert.equal(r.isMethods(bundle.items[4]), false);
  assert.equal(bundle.items[1].hidden, undefined);                  // the input is not changed
});

test('applyPick without methods hides the methods text', () => {
  const r = lab.applyPick(bundle, { items: ['kennwerte'], methods: false });
  assert.deepEqual(shown(r), ['kennwerte', 'values', 'citation']);
  assert.equal(r.keep('text-methodik.tex'), true);
});

test('applyPick without a pick keeps the whole bundle', () => {
  assert.equal(lab.applyPick(bundle, null).items.length, bundle.items.length);
  assert.deepEqual(shown(lab.applyPick(bundle, { items: null, methods: true })), bundle.items.map((i) => i.id || i.kind));
});

// methods text with steps (labbundle add_methods): Short, Full, own selection, equations
const steps = [
  { id: 's1', title: 'Probe', short: true, par: 0, file: 'methods/s1.tex' },
  { id: 's2', title: 'Fit', short: false, par: 0, file: 'methods/s2.tex' },
  { id: 's3', title: 'Norm', short: true, par: 1, file: 'methods/s3.tex' },
  { id: 'gleichungen', title: 'Gleichungen', short: false, par: 2, file: 'methods/gleichungen.tex', eq: true },
];
const texts = { 'methods/s1.tex': 'Eins.\n', 'methods/s2.tex': 'Zwei.\n', 'methods/s3.tex': 'Drei~\\cite{n}.\n', 'methods/gleichungen.tex': '\\[a=b\\]\n' };
const sb = { items: [{ kind: 'figure', id: 'feld', file: 'fig/feld.pdf' }, { kind: 'text', id: 'methodik', title: 'Methodik', file: 'text-methodik.tex', methods: true, steps }] };
const read = (rel) => texts[rel] || '';

test('Short methods: the short steps as running text in text-methodik-auswahl.tex', () => {
  const r = lab.applyPick(sb, { items: ['feld'], methods: { mode: 'short', eq: false } }, read);
  const m = r.items.find((i) => i.id === 'methodik');
  assert.equal(m.shown_file, 'text-methodik-auswahl.tex');
  assert.deepEqual(m.shown_steps, ['s1', 's3']);
  assert.equal(r.extra['text-methodik-auswahl.tex'], 'Eins.\n\nDrei~\\cite{n}.\n');
});

test('Full with equations keeps the original file; own selection joins one paragraph with a space', () => {
  const full = lab.applyPick(sb, { items: ['feld'], methods: { mode: 'full', eq: true } }, read);
  assert.equal(full.items.find((i) => i.id === 'methodik').shown_file, undefined);
  assert.deepEqual(full.extra, {});
  const own = lab.applyPick(sb, { items: ['feld'], methods: { mode: 'custom', steps: ['s1', 's2', 'weg'], eq: true } }, read);
  assert.equal(own.extra['text-methodik-auswahl.tex'], 'Eins. Zwei.\n\n\\[a=b\\]\n');
  assert.match(own.warnings[0], /weg/);
  const none = lab.applyPick(sb, { items: ['feld'], methods: { mode: 'custom', steps: [], eq: false } }, read);
  assert.equal(none.items.find((i) => i.id === 'methodik').hidden, true);
});

test('composeMethods matches labbundle.compose_methods', () => {
  assert.equal(lab.composeMethods(steps, read, ['s2', 's3']), 'Zwei.\n\nDrei~\\cite{n}.\n');
  assert.equal(lab.composeMethods(steps, read, []), '');
});
test('envHash follows files and report request, not UI state', () => {
  const st = { items: { a: { raw: 'r1', name: 'x' } }, client: { report: { sections: ['feld'] }, sel: 1 } };
  const h = folio.envHash(st);
  assert.equal(h, folio.envHash({ ...st, client: { ...st.client, sel: 7, view: 'zoom' } }));
  assert.notEqual(h, folio.envHash({ ...st, items: { a: { raw: 'r2' } } }));
  assert.notEqual(h, folio.envHash({ ...st, client: { report: { sections: ['kurve'] } } }));
  // without a report request the page state that modules derive it from counts
  const a = folio.envHash({ items: {}, client: { items: [{ p: 1 }] } });
  assert.notEqual(a, folio.envHash({ items: {}, client: { items: [{ p: 2 }] } }));
  assert.equal(folio.envHash(null), folio.envHash({}));
});

fs.rmSync(tmp, { recursive: true, force: true });
console.log(`${n} checks passed.`);
