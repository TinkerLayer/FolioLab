'use strict';
// Check of report revisions and provenance (server/lab.js). Runs on a temporary projects folder, never on the
// user's projects:  node tools/test_lab_revisions.js
const os = require('os');
const path = require('path');
const fs = require('fs');
const assert = require('assert');

const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'folio-revisions-'));
process.env.FOLIO_PROJECTS_DIR = TMP;
const P = require('../server/projects');
const lab = require('../server/lab');
const modules = require('../server/modules');

const b64 = (s) => Buffer.from(s).toString('base64');
function bundle(value, src = 'x;y\n1;2\n') {
  return {
    format: lab.FORMAT, module: 'testmod', module_name: 'Test', title: 'Probe', slug: 'probe', lang: 'de',
    created: '2026-11-17T00:00:00Z',
    items: [{ kind: 'values', values: [{ key: 'rm', label: 'Rm', text: `${value} MPa` }] }],
    files: { 'values.tex': b64(`\\labset{probe}{rm}{${value}}\n`) },
    source: { request: { a: 1 }, files: { 'messung.csv': b64(src) } },
  };
}

(async () => {
  let ok = 0;
  try {
    const { id } = await P.createProject({ name: 'Revisions test' });
    // module stub for Refresh
    let next = 500;
    modules.get = async () => ({ id: 'testmod', version: '9.9.9', bundle: {} });
    modules.call = async () => bundle(next++);

    const m1 = await lab.save(id, bundle(480));
    assert.strictEqual(m1.revision, 1);
    assert.strictEqual(m1.provenance.module_version, '9.9.9');
    assert.strictEqual(m1.provenance.suite_version, require('../package.json').version);
    assert.match(m1.provenance.source_sha256['messung.csv'], /^[0-9a-f]{64}$/);
    ok++;

    // refresh twice -> two old revisions kept
    const m2 = await lab.refresh(id, 'probe');
    const m3 = await lab.refresh(id, 'probe');
    assert.strictEqual(m2.revision, 2);
    assert.strictEqual(m3.revision, 3);
    assert.strictEqual(m3.result_id, m1.result_id);
    assert.strictEqual(m3.provenance.action, 'refresh');
    assert.strictEqual(m3.created, m1.created);
    const revs = await lab.revisions(id, 'probe');
    assert.deepStrictEqual(revs.map((r) => r.revision), [3, 2, 1]);
    const listed = (await lab.list(id))[0];
    assert.strictEqual(listed.history_count, 2);
    ok++;

    // compare
    const d = await lab.compare(id, 'probe', 1, 3);
    assert.deepStrictEqual(d.values.map((v) => [v.a, v.b]), [['480 MPa', '501 MPa']]);
    assert.deepStrictEqual(d.files.changed, ['values.tex']);
    assert.strictEqual(d.source_changed, false);
    ok++;

    // restore revision 1 as revision 4; revision 3 goes to the history
    const m4 = await lab.restore(id, 'probe', 1);
    assert.strictEqual(m4.revision, 4);
    assert.strictEqual(m4.provenance.restored_from, 1);
    const vt = fs.readFileSync(path.join(P.filesDir(id), 'lab', 'probe', 'values.tex'), 'utf8');
    assert.match(vt, /\{480\}/);
    assert.deepStrictEqual((await lab.revisions(id, 'probe')).map((r) => r.revision), [4, 3, 2, 1]);
    await assert.rejects(lab.restore(id, 'probe', 4));
    await assert.rejects(lab.restore(id, 'probe', 7));
    ok++;

    // issue (manual and by export); a later refresh keeps the issued revision in the history
    const iss = await lab.issue(id, 'probe');
    assert.strictEqual(iss.issued.how, 'manual');
    const m5 = await lab.refresh(id, 'probe');
    assert.strictEqual(m5.revision, 5);
    assert.strictEqual(m5.issued, null);
    assert.ok((await lab.revisions(id, 'probe')).find((r) => r.revision === 4).issued);
    await lab.issueAll(id, 'zip');
    assert.strictEqual((await lab.readManifest(id, 'probe')).issued.how, 'zip');
    ok++;

    // an old bundle without the new fields still loads and gets revision 2 on replace
    const old = path.join(P.filesDir(id), 'lab', 'alt');
    fs.mkdirSync(old, { recursive: true });
    fs.writeFileSync(path.join(old, 'bundle.json'), JSON.stringify({ format: lab.FORMAT, module: 'testmod', title: 'Alt', slug: 'alt', items: [], files: [] }));
    assert.strictEqual((await lab.list(id)).find((b) => b.slug === 'alt').revision, 1);
    const r2 = await lab.save(id, { ...bundle(1), slug: 'alt' }, 'replace');
    assert.strictEqual(r2.revision, 2);
    assert.ok(fs.existsSync(path.join(old, 'history', '1', 'bundle.json')));
    // new name -> no history
    const n = await lab.save(id, bundle(2), 'new');
    assert.strictEqual(n.slug, 'probe-2');
    assert.strictEqual(n.revision, 1);
    // references and labdata only list current revisions
    const labdata = fs.readFileSync(path.join(P.filesDir(id), 'lab', 'labdata.tex'), 'utf8');
    assert.ok(!/history/.test(labdata));
    ok++;

    // module version: the one the computing module reports in its bundle wins over module.json; source kind kept
    const mv = await lab.save(id, { ...bundle(3), slug: 'ds', module_version: '0.3.0',
      source: { kind: 'dataset', request: { share: 's-0000abcd', version: 2, x: { id: 's-0000beef', mode: 'live', used: 4 } }, files: { 'datensatz.json': b64('{}') } } }, 'new');
    assert.strictEqual(mv.provenance.module_version, '0.3.0');
    assert.strictEqual(mv.provenance.module_version_from, 'bundle');
    assert.strictEqual(mv.provenance.source_kind, 'dataset');
    assert.strictEqual(m1.provenance.module_version_from, 'module.json');
    assert.strictEqual(m1.provenance.source_kind, 'files');
    ok++;

    // removing a result: never issued -> to the bin (undo handle); issued -> also kept under lab/_removed/ and still
    // listed as a dependency; bin: false deletes for good
    const plain = await lab.save(id, bundle(4), 'new');
    const gone = await lab.remove(id, plain.slug);
    assert.strictEqual(gone.kept, null);
    assert.match(gone.undo, new RegExp(`^${plain.slug}-\\d{4}-`));
    assert.ok(!fs.existsSync(path.join(P.filesDir(id), 'lab', plain.slug)));
    const plain2 = await lab.save(id, bundle(4), 'new');
    assert.deepStrictEqual(await lab.remove(id, plain2.slug, { bin: false }), { kept: null });
    assert.ok(!fs.existsSync(path.join(P.filesDir(id), 'lab', plain.slug)));
    await lab.issue(id, 'ds');
    const rm = await lab.remove(id, 'ds');
    assert.match(rm.kept, /^_removed\/ds-/);
    const keptMan = JSON.parse(fs.readFileSync(path.join(P.filesDir(id), 'lab', ...rm.kept.split('/'), 'bundle.json'), 'utf8'));
    assert.ok(keptMan.removed && keptMan.issued);
    assert.ok(!(await lab.list(id)).some((b) => b.slug === 'ds' || b.slug === '_removed'));
    const deps = await lab.dependencies(id);
    const dr = deps.results.find((r) => r.removed);
    assert.strictEqual(dr.result, rm.kept);
    assert.deepStrictEqual(dr.shares, ['s-0000abcd v2', 's-0000beef v4']);              // binding: the version used
    ok++;
    console.log(`report revisions: ${ok} checks passed`);
  } catch (e) {
    console.error(`report revisions: failed after ${ok} checks`);
    console.error(e);
    process.exitCode = 1;
  } finally {
    fs.rmSync(TMP, { recursive: true, force: true });
  }
})();
