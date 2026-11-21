'use strict';
// Checks for the helpers of the figure editing window (public/js/editor/cusedit.mjs): style spec with groups, what an
// element looks like with its group, range selection, find and replace across labels. No server, no browser.
// Usage: node tools/test_cus_edit.js
const assert = require('node:assert/strict');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

const tests = [];
const test = (name, fn) => tests.push([name, fn]);

const DESCRIBE = {
  title: 'Spannung über Dehnung',
  axes: [{ xlabel: 'Dehnung in %', ylabel: 'Spannung in MPa' }, {}],
  elements: [
    { key: '0.line:elastisch', kind: 'line', named: true, group: 'lines', text: 'elastisch', raw: 'elastisch' },
    { key: '0.line0', kind: 'line', named: false, group: 'lines', text: 'line (2 points)' },
    { key: '0.text0', kind: 'text', named: false, group: 'annotations', text: '105 MPa', raw: '105 MPa' },
    { key: '0.text1', kind: 'label', named: false, group: 'annotations', text: 'Rm = 140 MPa', raw: '$R_m$ = 140 MPa' },
  ],
};

test('buildSpec keeps groups with their own props only', (U) => {
  const st = U.stateFrom({});
  st.groups.annotations = { color: '#ff0000', size: '8', bold: true, lw: 3 };
  st.groups.lines = { ls: '--', hidden: false };
  st.groups.bogus = { color: '#000000' };
  const s = U.buildSpec(st);
  assert.deepEqual(s.groups, { annotations: { color: '#ff0000', size: 8, bold: true }, lines: { ls: '--' } });
});

test('stateFrom and buildSpec round-trip groups and element overrides', (U) => {
  const spec = { groups: { lines: { lw: 2, hidden: true } }, elements: { '0.line0': { hidden: false, bold: false } } };
  assert.deepEqual(U.buildSpec(U.stateFrom(spec)), spec);
});

test('an element takes its group, its own setting wins', (U) => {
  const st = U.stateFrom({ groups: { lines: { color: '#111111', lw: 2, hidden: true } }, elements: { '0.line0': { hidden: false, color: '#00ff00' } } });
  assert.deepEqual(U.effective(st, DESCRIBE.elements[0]), { color: '#111111', lw: 2, hidden: true });
  assert.deepEqual(U.effective(st, DESCRIBE.elements[1]), { color: '#00ff00', lw: 2, hidden: false });
  assert.deepEqual(U.effective(st, DESCRIBE.elements[2]), {});
});

test('rangeKeys selects from the anchor in list order', (U) => {
  const order = ['a', 'b', 'c', 'd'];
  assert.deepEqual(U.rangeKeys(order, 'b', 'd'), ['b', 'c', 'd']);
  assert.deepEqual(U.rangeKeys(order, 'd', 'a'), ['a', 'b', 'c', 'd']);
  assert.deepEqual(U.rangeKeys(order, 'x', 'c'), ['c']);
});

test('find counts matches across texts, legend names, axis labels and title', (U) => {
  const st = U.stateFrom({ axes: [{ ylabel: 'Stress in MPa' }] });
  const t = U.labelTargets(DESCRIBE, st);
  assert.deepEqual(t.map((x) => x.prop), ['label', 'text', 'text', 'xlabel', 'ylabel', 'title']);
  assert.deepEqual(U.countMatches(t, 'mpa'), { matches: 3, labels: 3 });
  assert.deepEqual(U.countMatches(t, 'mpa', true), { matches: 0, labels: 0 });
  assert.deepEqual(U.countMatches(t, ''), { matches: 0, labels: 0 });
});

test('replace all writes the new texts into the form state', (U) => {
  const st = U.stateFrom({});
  const n = U.replaceAll(st, U.labelTargets(DESCRIBE, st), 'MPa', 'N/mm²');
  assert.equal(n, 3);
  assert.equal(st.elements['0.text0'].text, '105 N/mm²');
  assert.equal(st.elements['0.text1'].text, '$R_m$ = 140 N/mm²');
  assert.equal(st.axes[0].ylabel, 'Spannung in N/mm²');
  assert.equal(st.axes[0].xlabel, undefined);
  const s = U.buildSpec(st);
  assert.equal(s.axes[0].ylabel, 'Spannung in N/mm²');
  // special characters are searched literally, the replacement is taken as it is
  const st2 = U.stateFrom({});
  assert.equal(U.replaceAll(st2, U.labelTargets(DESCRIBE, st2), '$R_m$', '$R_\\mathrm{m}$ ($&)'), 1);
  assert.equal(st2.elements['0.text1'].text, '$R_\\mathrm{m}$ ($&) = 140 MPa');
  // the title and legend names too
  const st3 = U.stateFrom({});
  U.replaceAll(st3, U.labelTargets(DESCRIBE, st3), 'Dehnung', 'Strain');
  assert.equal(st3.title, 'Spannung über Strain');
  U.replaceAll(st3, U.labelTargets(DESCRIBE, st3), 'elastisch', 'elastic');
  assert.equal(st3.elements['0.line:elastisch'].label, 'elastic');
});

test('instant preview helpers: dash patterns and plain texts', (U) => {
  assert.equal(U.dashFor('--', 2), '7.4,3.2');
  assert.equal(U.dashFor('-', 2), 'none');
  assert.equal(U.dashFor(':', 1), '1,1.65');
  assert.ok(U.plainText('105 MPa'));
  assert.ok(!U.plainText('$R_m$'));
  assert.ok(!U.plainText('\\textbf{x}'));
});

test('a part is off when switched off or when all its elements are hidden', (U) => {
  const item = { parts: [{ id: 'env', label: 'Hüllkurve', cites: ['fit'] }, { id: 'ref', label: 'Referenz' }] };
  const desc = { elements: [
    { key: 'a', kind: 'line', group: 'lines', part: 'env' },
    { key: 'b', kind: 'text', group: 'annotations', part: 'env' },
    { key: 'c', kind: 'line', group: 'lines', part: 'ref' },
  ] };
  const st = U.stateFrom({});
  assert.deepEqual(U.partRows(item, st, desc).map((r) => r.shown), [true, true]);
  st.elements.a = { hidden: true };
  assert.equal(U.partRows(item, st, desc)[0].shown, true);        // one of two still visible
  st.elements.b = { hidden: true };
  assert.equal(U.partRows(item, st, desc)[0].shown, false);
  U.setPart(st, desc, 'env', true);                               // on again: its elements come back
  assert.deepEqual(st.elements, {});
  assert.equal(U.partRows(item, st, desc)[0].shown, true);
  U.setPart(st, desc, 'ref', false);
  assert.deepEqual(U.buildSpec(st).parts, { ref: { hidden: true } });
  assert.equal(U.partRows(item, U.stateFrom(U.buildSpec(st)), desc)[1].shown, false);
});

(async () => {
  const U = await import(pathToFileURL(path.join(__dirname, '..', 'public', 'js', 'editor', 'cusedit.mjs')).href);
  let failed = 0;
  for (const [name, fn] of tests) {
    try {
      await fn(U);
      console.log(`ok   ${name}`);
    } catch (e) {
      failed++;
      console.log(`FAIL ${name}\n     ${e.message}`);
    }
  }
  console.log(`${tests.length - failed}/${tests.length} passed`);
  process.exit(failed ? 1 : 0);
})();
