'use strict';
// "Import" from the Folio modules into a report: module → environment → the pieces of that environment's
// report bundle (figures, tables, single values, text blocks, data), each with the references, values and methods
// text it needs. The module builds the bundle from the stored environment without switching its active environment
// (sdk/python/labproject.py ModuleEnvs.bundle_of, route /api/env/bundle). An imported piece is a normal result of its
// real module (lab/<slug>/, a subset of the bundle's items, `pick`), linked to the environment (live / pinned / copy).
const fs = require('fs');
const fsp = fs.promises;
const path = require('path');
const crypto = require('crypto');
const { HttpError, readText } = require('./util');
const P = require('./projects');
const lab = require('./lab');
const suite = require('./suite');
const modules = require('./modules');

const STAGE = path.join(P.PROJECTS_DIR, '.staging', 'folio');
const ID = /^[a-z0-9][a-z0-9-]{0,39}$/;
const STAGE_RE = /^[a-z0-9-]{1,40}-[a-z0-9-]{1,40}-[0-9a-f]{12}-(de|en)$/;
const MODES = ['live', 'pin', 'copy'];
const METHODS_RE = /method|methodik/i;

const sha = (s) => crypto.createHash('sha256').update(s).digest('hex');

async function activeProject() {
  const s = await suite.list();
  const p = s.projects.find((x) => x.id === s.active) || {};
  return { id: s.active, name: p.name || s.active, dir: path.join(suite.SUITE_DIR, 'projects', s.active) };
}

async function readJsonFile(abs, fallback = null) {
  const t = await readText(abs);
  if (!t) return fallback;
  try {
    return JSON.parse(t);
  } catch {
    return fallback;
  }
}

/** Content hash of what decides an environment's report: the stored files and the page's report request (or its
 *  page state where a module derives the request from it). UI-only changes (selection, view) do not count. */
function envHash(state) {
  const st = state || {};
  const items = Object.fromEntries(Object.entries(st.items || {}).map(([k, v]) => [k, v && v.raw]));
  const c = st.client || {};
  return sha(JSON.stringify([items, c.report || null, c.report ? null : c.items || null, c.report ? null : c.extra || null]));
}

/** Modules that can build reports and the environments of the active project, newest work first after Standard. */
async function listModules() {
  const proj = await activeProject();
  const mods = (await modules.list()).filter((m) => m.status === 'ready' && m.runtime && m.bundle);
  const out = [];
  for (const m of mods) {
    const base = path.join(proj.dir, 'env', m.id);
    const active = ((await readJsonFile(path.join(base, '_aktiv.json'))) || {}).id || 'standard';
    const envs = [];
    for (const d of await fsp.readdir(base, { withFileTypes: true }).catch(() => [])) {
      if (!d.isDirectory() || d.name.startsWith('_') || !ID.test(d.name)) continue;
      const man = await readJsonFile(path.join(base, d.name, 'manifest.json'));
      if (!man) continue;
      const st = await readJsonFile(path.join(base, d.name, 'state.json'), {});
      const c = (st && st.client) || {};
      const sum = man.summary || {};
      const nItems = Object.keys((st && st.items) || {}).length;
      envs.push({
        id: man.id || d.name, name: man.name || d.name, created: man.created, modified: man.modified, active: (man.id || d.name) === active,
        title: sum.title || '', tags: Array.isArray(sum.tags) ? sum.tags.slice(0, 4) : [],
        values: Array.isArray(sum.values) ? sum.values.length : 0, plots: Array.isArray(sum.plots) ? sum.plots.length : 0,
        files: nItems, report: !!c.report, empty: !nItems && !c.report && !c.extra,
      });
    }
    envs.sort((a, b) => (a.id !== 'standard') - (b.id !== 'standard') || String(a.created || '').localeCompare(String(b.created || '')));
    out.push({ id: m.id, name: m.name, name_en: m.name_en || m.name, color: m.color || null, icon_svg: m.icon_svg || null, version: m.version || null, envs });
  }
  return { project: { id: proj.id, name: proj.name }, modules: out };
}

function checkIds(module, env) {
  if (!ID.test(String(module || ''))) throw new HttpError(400, 'Invalid module');
  if (!ID.test(String(env || ''))) throw new HttpError(400, 'Invalid environment');
}

/** Describe the pieces of a staged bundle for the dialog. */
function describe(stage, b) {
  const cites = new Map((b.items || []).filter((i) => i.kind === 'citation').map((i) => [i.key, i.title || i.key]));
  const methods = (b.items || []).filter((i) => i.kind === 'text' && (METHODS_RE.test(i.id) || METHODS_RE.test(i.title || '')));
  const pieces = [];
  for (const it of b.items || []) {
    const cite = (it.cites || []).map((k) => ({ key: k, title: cites.get(k) || k }));
    if (it.kind === 'figure') pieces.push({ key: `item:${it.id}`, kind: 'figure', id: it.id, title: it.caption || it.id, preview: it.preview || null, cites: cite });
    else if (it.kind === 'table') pieces.push({ key: `item:${it.id}`, kind: 'table', id: it.id, title: it.caption || it.id, notes: it.notes || '', cites: cite, snippet: (b._texts || {})[it.file] || '' });
    else if (it.kind === 'data') pieces.push({ key: `item:${it.id}`, kind: 'data', id: it.id, title: it.description || it.id, columns: it.columns || [], rows: it.rows || null });
    else if (it.kind === 'text') pieces.push({ key: `item:${it.id}`, kind: 'text', id: it.id, title: it.title || it.id, methods: methods.includes(it), snippet: ((b._texts || {})[it.file] || '').slice(0, 1500) });
    else if (it.kind === 'values') for (const v of it.values || []) pieces.push({ key: `value:${v.key}`, kind: 'value', id: v.key, title: v.label || v.key, text: v.text || '', latex: v.latex || '' });
  }
  return {
    stage, module: b.module, module_name: b.module_name, title: b.title, lang: b.lang, summary: b.summary || '',
    origin: b.origin || null, references: [...cites].map(([key, title]) => ({ key, title })),
    methods: methods.map((m) => ({ id: m.id, title: m.title || m.id })), pieces,
  };
}

/** Language of the target report (main file), so imported captions match it. */
async function reportLang(target) {
  try {
    const meta = await P.readMeta(String(target || ''));
    return require('./importer').langOf(await readText(path.join(P.filesDir(meta.id || target), meta.mainFile || 'main.tex')));
  } catch {
    return 'de';
  }
}

/** Build (or reuse) the report bundle of an environment and return its pieces. lang: 'de' | 'en' | (target report). */
async function envPieces(module, env, lang, target) {
  checkIds(module, env);
  const lg = lang === 'en' || lang === 'de' ? lang : target ? await reportLang(target) : 'de';
  const m = await modules.get(module);
  if (!m.bundle || m.status !== 'ready') throw new HttpError(400, `${m.name} cannot write report pieces`);
  const proj = await activeProject();
  const edir = path.join(proj.dir, 'env', module, env);
  const man = await readJsonFile(path.join(edir, 'manifest.json'));
  if (!man) throw new HttpError(404, 'This environment no longer exists');
  const hash = envHash(await readJsonFile(path.join(edir, 'state.json'), {}));
  const key = `${module}-${env}-${sha(hash + (m.version || '')).slice(0, 12)}-${lg}`;
  const dir = path.join(STAGE, key);
  let b = await readJsonFile(path.join(dir, 'bundle.json'));
  if (!b) {
    const fresh = await modules.call(module, '/api/env/bundle', { env, lang: lg });
    if (!fresh || fresh.format !== lab.FORMAT) throw new HttpError(502, `${m.name} returned no report bundle`);
    await fsp.rm(dir, { recursive: true, force: true });
    await fsp.mkdir(path.join(dir, 'files'), { recursive: true });
    const texts = {};
    for (const [rel, b64] of Object.entries(fresh.files || {})) {
      if (!/^[A-Za-z0-9_][A-Za-z0-9_.\-/]{0,120}$/.test(rel) || rel.includes('..')) continue;
      const abs = path.join(dir, 'files', rel);
      await fsp.mkdir(path.dirname(abs), { recursive: true });
      const buf = Buffer.from(b64, 'base64');
      await fsp.writeFile(abs, buf);
      if (/\.tex$/.test(rel) && buf.length < 60000) texts[rel] = buf.toString('utf8');
    }
    b = { ...fresh, files: Object.keys(fresh.files || {}), _texts: texts, _hash: hash, _env: { project: proj.id, module, env, name: man.name } };
    await fsp.writeFile(path.join(dir, 'bundle.json'), JSON.stringify(b));
    // older stages of the same environment are no longer needed
    for (const d of await fsp.readdir(STAGE).catch(() => [])) {
      if (d !== key && d.startsWith(`${module}-${env}-`)) await fsp.rm(path.join(STAGE, d), { recursive: true, force: true }).catch(() => {});
    }
  }
  return describe(key, b);
}

async function stageBundle(stage) {
  if (!STAGE_RE.test(String(stage || ''))) throw new HttpError(400, 'Invalid stage');
  const b = await readJsonFile(path.join(STAGE, stage, 'bundle.json'));
  if (!b) throw new HttpError(404, 'The pieces of this environment are gone; open it again in the dialog');
  return b;
}

/** A preview or text file of a staged bundle (PNG previews in the dialog). */
async function stageFile(stage, rel) {
  await stageBundle(stage);
  if (!/^[A-Za-z0-9_][A-Za-z0-9_.\-/]{0,120}$/.test(String(rel || '')) || rel.includes('..')) throw new HttpError(400, 'Invalid path');
  return path.join(STAGE, stage, 'files', rel);
}

const applyPick = (b, pick) => lab.applyPick(b, pick);

/** Import chosen pieces of a staged environment bundle into report `id`. body: {source: {type: 'env', stage},
 *  keys: ['item:<id>', 'value:<key>'], mode, methods}. Returns {results: [manifest], warnings, pick}. */
async function importEnv(id, body = {}, opts = {}) {
  await P.readMeta(id);
  const mode = body.mode || 'live';
  if (!MODES.includes(mode)) throw new HttpError(400, 'Mode must be live, pin or copy');
  const b = await stageBundle((body.source || {}).stage);
  const keys = Array.isArray(body.keys) ? body.keys.map(String).slice(0, 500) : [];
  if (!keys.length) throw new HttpError(400, 'Choose at least one piece to import');
  const ids = new Set((b.items || []).map((i) => i.id));
  const vals = new Set((b.items || []).filter((i) => i.kind === 'values').flatMap((i) => (i.values || []).map((v) => v.key)));
  const pick = { items: [], values: [], methods: body.methods !== false };
  const missing = [];
  for (const k of keys) {
    const [kind, rest] = [k.slice(0, k.indexOf(':')), k.slice(k.indexOf(':') + 1)];
    if (kind === 'item' && ids.has(rest)) pick.items.push(rest);
    else if (kind === 'value' && vals.has(rest)) pick.values.push(rest);
    else missing.push(k);
  }
  if (missing.length && !opts.slug) throw new HttpError(400, `Not in this environment: ${missing.join(', ')}`);
  const { items, keep } = applyPick(b, pick);
  const dir = path.join(STAGE, body.source.stage, 'files');
  const files = {};
  for (const rel of b.files || []) if (keep(rel)) files[rel] = (await fsp.readFile(path.join(dir, rel))).toString('base64');
  const env = b._env || {};
  const chosen = (b.items || []).filter((i) => pick.items.includes(i.id));
  const one = chosen.length === 1 && !pick.values.length ? chosen[0] : null;
  const plainTitle = (s) => String(s || '').replace(/\\[a-zA-Z]+\{([^}]*)\}/g, '$1').replace(/[{}$\\~]/g, '').replace(/\s+/g, ' ').trim().slice(0, 90);
  const title = opts.title || (one ? `${env.name}: ${plainTitle(one.caption || one.title || one.description || one.id)}` : `${b.module_name || b.module}: ${env.name}`);
  const link = {
    type: 'env', mode, module: env.module, env: env.module ? env.env : null, env_name: env.name, project: env.project,
    title: `${b.module_name || b.module} · ${env.name}`, hash: b._hash, imported: new Date().toISOString(),
  };
  const bundle = {
    format: lab.FORMAT, module: b.module, module_name: b.module_name, title, slug: opts.slug || b.slug, lang: b.lang,
    summary: b.summary, created: b.created, items, files,
    source: mode === 'copy' ? null : b.source, module_version: b.module_version || null, methods: b.methods || null,
    link: mode === 'copy' ? { ...link, type: 'env', mode: 'copy' } : link, pick,
  };
  const man = await lab.save(id, bundle, opts.slug ? 'replace' : 'new', { action: opts.slug ? 'update' : 'import' });
  return { results: [man], warnings: missing.map((k) => `${k}: no longer in the environment; left out.`), pick };
}

/** Link state of a result imported from an environment. */
async function linkState(man) {
  const link = man.link;
  const base = { slug: man.slug, type: 'env', mode: link.mode, title: link.title };
  if (link.mode === 'copy') return { ...base, state: null };
  const proj = await activeProject();
  if (link.project && link.project !== proj.id) return { ...base, state: 'failed', error: `Belongs to another project; activate it to update` };
  const edir = path.join(proj.dir, 'env', String(link.module), String(link.env));
  if (!ID.test(String(link.module)) || !ID.test(String(link.env)) || !(await readJsonFile(path.join(edir, 'manifest.json')))) {
    return { ...base, state: 'failed', changed: [], missing: [link.env], error: 'The environment no longer exists' };
  }
  const now = envHash(await readJsonFile(path.join(edir, 'state.json'), {}));
  const changed = now !== link.hash ? [link.env] : [];
  return { ...base, changed, missing: [], state: changed.length ? (link.mode === 'live' ? 'stale' : 'update') : 'current' };
}

/** Rebuild an environment import from the environment's current state (Update). */
async function update(id, man, opts = {}) {
  const link = man.link;
  const mode = opts.mode || link.mode;
  if (mode === 'copy') throw new HttpError(400, 'A copy has no source to update from');
  const d = await envPieces(link.module, link.env, (opts.lang || man.lang) === 'en' ? 'en' : 'de');
  const pick = man.pick || { items: [], values: [], methods: true };
  const keys = [...(pick.items || []).map((k) => `item:${k}`), ...(pick.values || []).map((k) => `value:${k}`)];
  const res = await importEnv(id, { source: { type: 'env', stage: d.stage }, keys, mode, methods: pick.methods !== false }, { slug: man.slug, title: man.title });
  return res.results[0];
}

module.exports = { listModules, envPieces, stageFile, importEnv, linkState, update, applyPick, envHash };
