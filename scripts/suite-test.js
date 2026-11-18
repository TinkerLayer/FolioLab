'use strict';
// A2: suite project registry. Runs on a temporary projects folder; the real `projects/` is never read or written.
//   tools\node\node.exe scripts\suite-test.js
const fs = require('fs');
const os = require('os');
const path = require('path');
const assert = require('assert');

const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'folio-suite-'));
process.env.FOLIO_PROJECTS_DIR = dir;
delete process.env.FOLIO_SUITE_DIR;
fs.mkdirSync(path.join(dir, 'aaaaaaaaaaaa'));
fs.writeFileSync(path.join(dir, 'aaaaaaaaaaaa', 'meta.json'), JSON.stringify({ id: 'aaaaaaaaaaaa', name: 'Bericht A', modified: '2026-11-01' }));
const before = fs.readFileSync(path.join(dir, 'aaaaaaaaaaaa', 'meta.json'), 'utf8');

const suite = require('../server/suite');
const projects = require('../server/projects');

(async () => {
  let l = await suite.list();
  assert.deepStrictEqual(l.projects.map((p) => p.id), ['standard', 'r-aaaaaaaaaaaa'], 'existing report appears as a project');
  assert.strictEqual(l.projects[1].reports[0].name, 'Bericht A');
  assert.strictEqual(l.active, 'standard');
  const p = await suite.create({ name: 'Polymere' });
  await suite.update(p.id, { addReport: 'aaaaaaaaaaaa' });
  l = await suite.list();
  assert.deepStrictEqual(l.projects.map((x) => x.id), ['standard', p.id], 'legacy entry folded into the new project');
  await suite.activate(p.id);
  assert.strictEqual((await suite.list()).active, p.id);
  await assert.rejects(suite.activate('../x'));
  await assert.rejects(suite.activate('nope'));
  assert.strictEqual(fs.readFileSync(path.join(dir, 'aaaaaaaaaaaa', 'meta.json'), 'utf8'), before, 'report untouched');
  assert.deepStrictEqual((await projects.listProjects()).map((x) => x.id), ['aaaaaaaaaaaa'], '_suite is not a report');
  console.log('suite registry: ok');

  // UI-09: open environment per module of the active project (files as sdk/python/labproject.py writes them)
  assert.deepStrictEqual((await suite.envs()).modules, {}, 'no environments yet');
  const envDir = path.join(suite.SUITE_DIR, 'projects', p.id, 'env', 'tga');
  for (const [id, name, title] of [['standard', 'Standard', ''], ['e-1a2b', 'Charge 7', 'PVC · 2 Läufe']]) {
    fs.mkdirSync(path.join(envDir, id), { recursive: true });
    fs.writeFileSync(path.join(envDir, id, 'manifest.json'), JSON.stringify({ id, name, summary: title ? { title } : undefined }));
  }
  fs.writeFileSync(path.join(envDir, '_board.json'), '{}');
  fs.writeFileSync(path.join(envDir, '_aktiv.json'), JSON.stringify({ id: 'e-1a2b' }));
  const ev = (await suite.envs()).modules.tga;
  assert.strictEqual(ev.count, 2, '_board.json is not an environment');
  assert.deepStrictEqual(ev.active, { id: 'e-1a2b', name: 'Charge 7', title: 'PVC · 2 Läufe' });
  console.log('suite environments: ok');

  // UI-09: history and dependencies of a report result (shared inputs found in the stored request)
  const lab = require('../server/lab');
  const res = path.join(dir, 'aaaaaaaaaaaa', 'files', 'lab', 'tga-1');
  const man = (rev, request) => ({ format: lab.FORMAT, module: 'nicht-da', module_name: 'TGA', title: 'TGA', slug: 'tga-1', items: [], revision: rev,
    result_id: 'r1', source: { request }, provenance: { module_version: '0.9', source_sha256: { 'run.txt': 'ab'.repeat(32) } } });
  fs.mkdirSync(path.join(res, 'history', '1'), { recursive: true });
  fs.writeFileSync(path.join(res, 'history', '1', 'bundle.json'), JSON.stringify(man(1, { steps: [] })));
  fs.writeFileSync(path.join(res, 'bundle.json'), JSON.stringify(man(2, { share: { share: 's-0123abcd', version: 2 }, x: [{ index: 'g-89abcdef' }] })));
  const [b] = await lab.list('aaaaaaaaaaaa');
  assert.deepStrictEqual(b.refs, { shares: ['s-0123abcd v2'], index: ['g-89abcdef'] });
  const hi = await lab.history('aaaaaaaaaaaa', 'tga-1');
  assert.deepStrictEqual(hi.source, [{ name: 'run.txt', sha256: 'ab'.repeat(32) }]);
  assert.ok(hi.chains_error, 'unknown module: chain not available, the rest still answers');
  const dep = await lab.dependencies('aaaaaaaaaaaa');
  assert.deepStrictEqual(dep.results.map((r) => [r.revision, r.current, r.shares.length]), [[2, true, 1], [1, false, 0]]);
  const zip = require('../server/zip').readZip(await projects.zipProject('aaaaaaaaaaaa', [{ name: 'lab/dependencies.json', data: Buffer.from('{}') }]));
  assert.ok(zip.some((e) => e.name === 'lab/dependencies.json'), 'dependencies.json in the ZIP');
  console.log('lab history and dependencies: ok');
})()
  .catch((e) => {
    console.error(e);
    process.exitCode = 1;
  })
  .finally(() => fs.rmSync(dir, { recursive: true, force: true }));
