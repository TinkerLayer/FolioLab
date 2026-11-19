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

test('applyPick keeps the picked items, citations, values and the methods text', () => {
  const r = lab.applyPick(bundle, { items: ['feld'], values: ['rm'], methods: true });
  assert.deepEqual(r.items.map((i) => i.id || i.kind), ['feld', 'methodik', 'values', 'citation']);
  assert.equal(r.keep('fig/feld.pdf'), true);
  assert.equal(r.keep('fig/kurve.pdf'), false);
  assert.equal(r.keep('fig/kurve.png'), false);                  // preview of a dropped PDF figure goes too
  assert.equal(r.keep('kennwerte.tex'), false);
  assert.equal(r.keep('text-methodik.tex'), true);
  assert.equal(r.isMethods(bundle.items[3]), true);
  assert.equal(r.isMethods(bundle.items[4]), false);
});

test('applyPick without methods drops the methods text', () => {
  const r = lab.applyPick(bundle, { items: ['kennwerte'], methods: false });
  assert.deepEqual(r.items.map((i) => i.id || i.kind), ['kennwerte', 'values', 'citation']);
  assert.equal(r.keep('text-methodik.tex'), false);
});

test('applyPick without a pick keeps the whole bundle', () => {
  assert.equal(lab.applyPick(bundle, null).items.length, bundle.items.length);
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
