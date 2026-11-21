'use strict';
// Report pieces cite and describe only what they show: methods steps and citations follow the imported pieces and
// the parts switched off in a variant (no server, no module: the module's rebuild is replaced by a stand-in).
// Usage: node tools/test_report_parts.js
const assert = require('node:assert/strict');
const os = require('node:os');
const path = require('node:path');
const fs = require('node:fs');

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'folio-parts-test-'));
process.env.FOLIO_PROJECTS_DIR = path.join(tmp, 'projects');
process.env.FOLIO_SUITE_DIR = path.join(tmp, 'projects', '_suite');
process.env.LAB_OUTPUTS = path.join(tmp, 'out');

const P = require('../server/projects');
const modules = require('../server/modules');
const lab = require('../server/lab');

const b64 = (s) => Buffer.from(s, 'utf8').toString('base64');
const SENT = {
  kurz: 'Die Zugprüfung erfolgte an einer Probe nach ISO 527-2~\\cite{iso}; ausgewertet mit Folio Lab~\\cite{sw}.',
  s1: 'Die Zugprüfung erfolgte an einer Probe nach ISO 527-2~\\cite{iso}.',
  s2: 'Der lineare Abschnitt wurde schrittweise erweitert.',
  s3: 'Verglichen wurde mit der Gruppe~\\cite{ro,gruppe}.',
  s4: 'Als Referenzwerkstoff dient S235~\\cite{mat}.',
  s5: 'Lastspitzen wurden mit einer Schwellenregel erkannt.',
  s6: 'Die Hüllkurve ist eine Ausgleichsgerade~\\cite{fit}.',
  s7: 'Ausgewertet wurde mit Folio Lab~\\cite{sw}.',
};
const STEPS = [
  { id: 'kurz', title: 'Ein Satz', short: false, par: -1, brief: true },
  { id: 's1', title: 'Messung', short: true, par: 0 },
  { id: 's2', title: 'Linear', short: false, par: 0, of: 'linear' },
  { id: 's3', title: 'Vergleich', short: false, par: 0, of: 'vergleich' },
  { id: 's4', title: 'Referenz', short: false, par: 0, of: 'referenz' },
  { id: 's5', title: 'Spitzen', short: false, par: 0, of: 'lastspitzen' },
  { id: 's6', title: 'Ausgleich', short: false, par: 0, of: 'ausgleich' },
  { id: 's7', title: 'Software', short: true, par: 0 },
].map((s) => ({ ...s, file: `methods/${s.id}.tex` }));

// what labbundle does for a figure with parts: shown flags, caption and citations of what is still visible
function figure(id, base, defs, spec) {
  const off = (spec && spec.parts) || {};
  const vis = defs.filter((d) => !(off[d.id] && off[d.id].hidden));
  const cites = [...new Set(vis.flatMap((d) => d.cites))];
  const caption = [base, ...vis.map((d) => d.text)].join(' ') + (cites.length ? `~\\cite{${cites.join(',')}}` : '');
  const full = [base, ...defs.map((d) => d.text)].join(' ') + `~\\cite{${[...new Set(defs.flatMap((d) => d.cites))].join(',')}}`;
  return {
    kind: 'figure', id, file: `fig/${id}.pdf`, preview: `fig/${id}.png`, label: `fig:${id}`, caption, cites,
    ...(caption !== full ? { caption_full: full } : {}),
    needs: { steps: [] },
    parts: defs.map((d) => ({ id: d.id, label: d.id, cites: d.cites, steps: d.steps, ...(off[d.id] && off[d.id].hidden ? { shown: false } : {}) })),
  };
}
const FELD = [
  { id: 'feld', text: 'im Feld der Gruppe.', cites: ['gruppe'], steps: ['vergleich'] },
  { id: 'referenz', text: 'mit der Referenz S235.', cites: ['mat'], steps: ['referenz'] },
];
const SPITZEN = [
  { id: 'spitzen', text: 'mit Lastspitzen.', cites: [], steps: ['lastspitzen'] },
  { id: 'huellkurve', text: 'mit Hüllkurve.', cites: ['fit'], steps: ['lastspitzen', 'ausgleich'] },
];

function bundle(slug, styles = {}) {
  const files = { 'text-methodik.tex': b64(`${STEPS.filter((s) => !s.brief).map((s) => SENT[s.id]).join(' ')}\n`) };
  for (const s of STEPS) files[s.file] = b64(`${SENT[s.id]}\n`);
  for (const f of ['feld', 'lastspitzen']) { files[`fig/${f}.pdf`] = b64('%PDF-1.4'); files[`fig/${f}.png`] = b64('png'); }
  files['referenz.tex'] = b64('\\begin{tabular}{l}x\\end{tabular}\n');
  files['linear.tex'] = b64('\\begin{tabular}{l}x\\end{tabular}\n');
  return {
    format: lab.FORMAT, slug, title: 'Zugversuch', module: 'zugversuch', module_name: 'Zugversuch', module_version: '1.0.0', lang: 'de',
    items: [
      figure('feld', 'Gemessene Kurve', FELD, styles.feld),
      figure('lastspitzen', 'Verlauf', SPITZEN, styles.lastspitzen),
      { kind: 'table', id: 'referenz', file: 'referenz.tex', caption: 'Referenz~\\cite{mat}', cites: ['mat'], label: 'tab:referenz', needs: { steps: ['referenz', 'linear'] } },
      { kind: 'table', id: 'linear', file: 'linear.tex', caption: 'Ohne Angabe', label: 'tab:linear' },
      { kind: 'text', id: 'methodik', title: 'Methodik', file: 'text-methodik.tex', methods: true, steps: STEPS },
      { kind: 'values', values: [{ key: 'Fmax', label: 'Fmax', latex: '1', text: '1' }, { key: 'yield', label: 'Fliessbeginn', latex: '2', text: '2', needs: ['linear'] }] },
      ...['iso', 'sw', 'ro', 'gruppe', 'mat', 'fit'].map((key) => ({ kind: 'citation', key, title: key })),
    ],
    files,
    source: { request: { slug }, files: {} },
  };
}
modules.get = async () => ({ id: 'zugversuch', bundle: { rebuild: '/api/bundle/rebuild' } });
modules.call = async (_m, _ep, body) => bundle(body.source.request.slug, body.source.request.styles || {});

let id;
let serial = 0;
const read = (slug, rel) => fs.readFileSync(path.join(lab.labDir(id), slug, rel), 'utf8');
/** A stored result that shows `items`, methods as chosen. */
async function imported(items, methods = { mode: 'short', eq: false }) {
  const slug = `zug${++serial}`;
  await lab.save(id, bundle(slug), 'new', { action: 'test' });
  return { slug, man: await lab.repick(id, slug, { items, methods }) };
}
const meth = (m) => m.items.find((i) => i.id === 'methodik');
const shownText = (slug, it) => read(slug, it.shown_file || it.file);
const off = (...ids) => ({ parts: Object.fromEntries(ids.map((x) => [x, { hidden: true }])) });

const tests = [];
const test = (name, fn) => tests.push([name, fn]);

test('a plain measurement curve brings no reference source and one methods sentence', async () => {
  const { slug } = await imported(['feld']);
  const v = await lab.fork(id, slug, { item: 'feld', mode: 'live', style: off('feld', 'referenz') });
  const fig = v.items.find((i) => i.id === 'feld');
  assert.deepEqual(fig.cites, []);
  assert.doesNotMatch(fig.caption, /cite|Referenz|Feld/);
  const man = await lab.readManifest(id, slug);
  assert.equal(meth(man).reduced, true);
  assert.deepEqual(meth(man).shown_steps, ['kurz']);
  const text = shownText(slug, meth(man));
  assert.equal(text.trim(), SENT.kurz);
  assert.doesNotMatch(text, /\\cite\{[^}]*(mat|gruppe|ro|fit)/);
});

test('Full leaves out what only unshown pieces need', async () => {
  const { slug, man } = await imported(['feld'], { mode: 'full', eq: true });
  assert.deepEqual(meth(man).inactive_steps, ['s2', 's5', 's6']);
  const text = shownText(slug, meth(man));
  assert.match(text, /Verglichen wurde/);
  assert.match(text, /Referenzwerkstoff/);
  assert.doesNotMatch(text, /Lastspitzen|Hüllkurve|lineare/);
});

test('hiding the envelope removes its sentence and its citation', async () => {
  const { slug } = await imported(['lastspitzen'], { mode: 'full', eq: true });
  assert.match(shownText(slug, meth(await lab.readManifest(id, slug))), /Hüllkurve/);
  const v = await lab.fork(id, slug, { item: 'lastspitzen', mode: 'live', style: off('huellkurve') });
  const fig = v.items.find((i) => i.id === 'lastspitzen');
  assert.doesNotMatch(fig.caption, /Hüllkurve|cite/);
  assert.deepEqual(fig.cites, []);
  const text = shownText(slug, meth(await lab.readManifest(id, slug)));
  assert.match(text, /Lastspitzen wurden/);          // the peaks are still shown
  assert.doesNotMatch(text, /Hüllkurve|\\cite\{fit/);
});

test('removing the variant brings the sentence back', async () => {
  const { slug } = await imported(['lastspitzen'], { mode: 'full', eq: true });
  const v = await lab.fork(id, slug, { item: 'lastspitzen', mode: 'live', style: off('huellkurve') });
  assert.doesNotMatch(shownText(slug, meth(await lab.readManifest(id, slug))), /Hüllkurve/);
  await lab.remove(id, v.slug, {});
  assert.match(shownText(slug, meth(await lab.readManifest(id, slug))), /Hüllkurve/);
});

test('hiding a reference curve drops its source unless another kept piece cites it', async () => {
  const alone = await imported(['feld'], { mode: 'full', eq: true });
  const v1 = await lab.fork(id, alone.slug, { item: 'feld', mode: 'live', style: off('referenz') });
  assert.deepEqual(v1.items.find((i) => i.id === 'feld').cites, ['gruppe']);
  assert.doesNotMatch(shownText(alone.slug, meth(await lab.readManifest(id, alone.slug))), /\\cite\{mat/);

  const kept = await imported(['feld', 'referenz'], { mode: 'full', eq: true });
  const v2 = await lab.fork(id, kept.slug, { item: 'feld', mode: 'live', style: off('referenz') });
  assert.deepEqual(v2.items.find((i) => i.id === 'feld').cites, ['gruppe']);
  const man = await lab.readManifest(id, kept.slug);
  assert.equal(man.items.find((i) => i.id === 'referenz').hidden, undefined);
  assert.match(shownText(kept.slug, meth(man)), /\\cite\{mat/);     // the table still shows the material
});

test('Refresh keeps edited sentences and what is switched off', async () => {
  const { slug } = await imported(['lastspitzen'], { mode: 'full', eq: true });
  const edits = { s5: { text: 'Lastspitzen, eigene Fassung.', orig: SENT.s5 }, s6: { text: 'Hüllkurve, eigene Fassung.', orig: SENT.s6 } };
  await lab.repick(id, slug, { methods: { mode: 'full', eq: true, edits } });
  await lab.fork(id, slug, { item: 'lastspitzen', mode: 'live', style: off('huellkurve') });
  await lab.refresh(id, slug);
  const man = await lab.readManifest(id, slug);
  const text = shownText(slug, meth(man));
  assert.match(text, /Lastspitzen, eigene Fassung\./);
  assert.doesNotMatch(text, /Hüllkurve/);            // the edit of a sentence that is not shown stays stored, unset
  assert.deepEqual(Object.keys(man.pick.methods.edits).sort(), ['s5', 's6']);
  assert.deepEqual(meth(man).edited_steps, ['s5']);
});

test('a value brings the step it needs; an undeclared piece still means the whole text', async () => {
  const applied = (pick) => lab.applyPick(bundle('x'), pick, (rel) => Buffer.from(bundle('x').files[rel] || '', 'base64').toString('utf8'));
  const withValue = applied({ items: [], values: ['yield'], methods: { mode: 'full', eq: true } });
  assert.deepEqual(withValue.items.find((i) => i.id === 'methodik').inactive_steps, ['s3', 's4', 's5', 's6']);
  const undeclared = applied({ items: ['linear'], values: [], methods: { mode: 'full', eq: true } });
  const m = undeclared.items.find((i) => i.id === 'methodik');
  assert.equal(m.inactive_steps, undefined);
  assert.equal(m.shown_file, undefined);
});

(async () => {
  try {
    id = (await P.createSkeleton({ name: 'Parts test' })).id;
    let n = 0;
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
