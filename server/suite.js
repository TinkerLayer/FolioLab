'use strict';
// A2: suite projects (Q17 = a) – a container holding Folio reports and the module environments.
// Existing reports are never touched (Q18 = a): each one not yet in a suite project appears as a project of its own,
// referring to the report by ID. The registry is `projects/_suite/suite.json` (the report list skips that folder);
// modules read it through sdk/python/labproject.py (FOLIO_SUITE_DIR).
const fs = require('fs');
const fsp = fs.promises;
const path = require('path');
const crypto = require('crypto');
const { HttpError, readText } = require('./util');
const P = require('./projects');

const SUITE_DIR = process.env.FOLIO_SUITE_DIR || path.join(P.PROJECTS_DIR, '_suite');
const REG = path.join(SUITE_DIR, 'suite.json');
const DEFAULT = 'standard';
const ID = /^[a-z0-9][a-z0-9-]{0,39}$/;
const now = () => new Date().toISOString().replace(/\.\d+Z$/, 'Z');

async function write(reg) {
  await fsp.mkdir(SUITE_DIR, { recursive: true });
  const tmp = REG + '.' + crypto.randomBytes(3).toString('hex') + '.tmp';
  await fsp.writeFile(tmp, JSON.stringify(reg, null, 1));
  await fsp.rename(tmp, REG);
}

async function read() {
  let reg = null;
  try {
    reg = JSON.parse((await readText(REG)) || 'null');
  } catch {
    reg = null;
  }
  let changed = false;
  if (!reg || !Array.isArray(reg.projects) || !reg.projects.length) {
    reg = { version: 1, active: DEFAULT, projects: [{ id: DEFAULT, name: 'Standardprojekt', reports: [], created: now() }] };
    changed = true;
  }
  const known = new Set(reg.projects.flatMap((p) => p.reports || []));
  for (const r of await P.listProjects()) {
    if (known.has(r.id)) continue;
    reg.projects.push({ id: 'r-' + r.id, name: r.name, reports: [r.id], legacy: true, created: now() });
    changed = true;
  }
  if (!reg.projects.some((p) => p.id === reg.active)) {
    reg.active = reg.projects[0].id;
    changed = true;
  }
  if (changed) await write(reg);
  return reg;
}

async function list() {
  const reg = await read();
  const names = Object.fromEntries((await P.listProjects()).map((r) => [r.id, r.name]));
  return {
    active: reg.active,
    projects: reg.projects.map((p) => ({
      ...p,
      reports: (p.reports || []).map((id) => ({ id, name: names[id] || null, missing: !names[id] })),
    })),
  };
}

function find(reg, id) {
  const p = reg.projects.find((x) => x.id === id);
  if (!p) throw new HttpError(404, 'Projekt nicht gefunden');
  return p;
}

async function create({ name } = {}) {
  const reg = await read();
  const p = { id: 'p-' + crypto.randomBytes(4).toString('hex'), name: String(name || '').trim().slice(0, 80) || 'Neues Projekt', reports: [], created: now() };
  reg.projects.push(p);
  await write(reg);
  return p;
}

async function update(id, body = {}) {
  const reg = await read();
  const p = find(reg, id);
  if (typeof body.name === 'string' && body.name.trim()) p.name = body.name.trim().slice(0, 80);
  if (typeof body.addReport === 'string') {
    if (!/^[a-f0-9]{12}$/.test(body.addReport)) throw new HttpError(400, 'Ungültige Bericht-ID');
    for (const q of reg.projects) q.reports = (q.reports || []).filter((r) => r !== body.addReport);  // ein Bericht gehört zu einem Projekt
    p.reports.push(body.addReport);
    reg.projects = reg.projects.filter((q) => !(q.legacy && !q.reports.length) || q.id === reg.active);
  }
  await write(reg);
  return p;
}

async function activate(id) {
  if (!ID.test(String(id))) throw new HttpError(400, 'Ungültige Projekt-ID');
  const reg = await read();
  find(reg, id);
  reg.active = id;
  await write(reg);
  return { active: id };
}

/** UI-09: per module the open environment of the active project and how many there are (read only; the modules
 *  write these files through sdk/python/labproject.py: env/<module>/_aktiv.json and <env>/manifest.json). */
async function envs() {
  const reg = await read();
  const base = path.join(SUITE_DIR, 'projects', reg.active, 'env');
  const out = {};
  let mods = [];
  try {
    mods = (await fsp.readdir(base, { withFileTypes: true })).filter((d) => d.isDirectory() && ID.test(d.name)).map((d) => d.name);
  } catch {
    return { project: reg.active, modules: out };
  }
  for (const mod of mods) {
    const dir = path.join(base, mod);
    let list = [];
    for (const d of await fsp.readdir(dir, { withFileTypes: true }).catch(() => [])) {
      if (!d.isDirectory() || d.name.startsWith('_')) continue;
      try {
        const m = JSON.parse(await fsp.readFile(path.join(dir, d.name, 'manifest.json'), 'utf8'));
        list.push({ id: m.id || d.name, name: m.name || d.name, title: (m.summary && m.summary.title) || '' });
      } catch {
        /* not an environment */
      }
    }
    let act = 'standard';
    try {
      act = JSON.parse(await fsp.readFile(path.join(dir, '_aktiv.json'), 'utf8')).id || act;
    } catch {
      /* default */
    }
    out[mod] = { count: list.length, active: list.find((e) => e.id === act) || list[0] || null };
  }
  return { project: reg.active, modules: out };
}

module.exports = { SUITE_DIR, list, create, update, activate, envs };
