'use strict';
// Project storage: projects/<id>/{meta.json, files/, build/, output/}
const fs = require('fs');
const fsp = fs.promises;
const path = require('path');
const crypto = require('crypto');
const { ROOT, HttpError, exists, readText, walk, copyDir, safeJoin } = require('./util');
const { readZip, createZip } = require('./zip');

const PROJECTS_DIR = process.env.FOLIO_PROJECTS_DIR || path.join(ROOT, 'projects');
const TEMPLATES_DIR = path.join(__dirname, 'templates');
const ENGINES = ['pdflatex', 'xelatex', 'lualatex'];

fs.mkdirSync(PROJECTS_DIR, { recursive: true });

function projectDir(id) {
  if (!/^[a-f0-9]{12}$/.test(String(id))) throw new HttpError(404, 'Project not found');
  return path.join(PROJECTS_DIR, id);
}
const filesDir = (id) => path.join(projectDir(id), 'files');
const buildDir = (id) => path.join(projectDir(id), 'build');
const outputDir = (id) => path.join(projectDir(id), 'output');
const metaPath = (id) => path.join(projectDir(id), 'meta.json');

async function readMeta(id) {
  const txt = await readText(metaPath(id));
  if (!txt) throw new HttpError(404, 'Project not found');
  return JSON.parse(txt);
}

async function writeMeta(id, meta) {
  await fsp.writeFile(metaPath(id), JSON.stringify(meta, null, 2));
  return meta;
}

async function touch(id) {
  const meta = await readMeta(id);
  meta.modified = new Date().toISOString();
  await writeMeta(id, meta);
}

async function listProjects() {
  const out = [];
  for (const id of await fsp.readdir(PROJECTS_DIR)) {
    if (!/^[a-f0-9]{12}$/.test(id)) continue;
    try {
      const meta = await readMeta(id);
      meta.hasPdf = await exists(path.join(outputDir(id), 'output.pdf'));
      out.push(meta);
    } catch {
      /* skip broken */
    }
  }
  out.sort((a, b) => (b.modified || '').localeCompare(a.modified || ''));
  return out;
}

async function listTemplates() {
  const out = [];
  for (const t of await fsp.readdir(TEMPLATES_DIR)) {
    const info = await readText(path.join(TEMPLATES_DIR, t, 'template.json'));
    if (info) out.push({ id: t, ...JSON.parse(info) });
  }
  out.sort((a, b) => (a.order || 99) - (b.order || 99));
  return out;
}

function newId() {
  return crypto.randomBytes(6).toString('hex');
}

async function createProject({ name, template = 'blank' }) {
  const templates = await listTemplates();
  const tpl = templates.find((t) => t.id === template) || templates.find((t) => t.id === 'blank');
  const id = newId();
  await fsp.mkdir(filesDir(id), { recursive: true });
  if (tpl) await copyDir(path.join(TEMPLATES_DIR, tpl.id, 'files'), filesDir(id));
  const now = new Date().toISOString();
  const meta = {
    id,
    name: (name || '').trim() || (tpl ? tpl.name : 'Untitled Project'),
    mainFile: (tpl && tpl.mainFile) || 'main.tex',
    engine: (tpl && tpl.engine) || 'pdflatex',
    shellEscape: false,
    template: tpl ? tpl.id : null,
    created: now,
    modified: now,
  };
  await writeMeta(id, meta);
  return meta;
}

/** Unpack a ZIP into base (dropping OS junk and a single shared top-level folder). */
async function extractZip(buffer, base) {
  let entries;
  try {
    entries = readZip(buffer).filter((e) => !e.isDir);
  } catch (e) {
    throw new HttpError(400, e.message);
  }
  entries = entries.filter((e) => !/(^|\/)(__MACOSX|\.DS_Store|Thumbs\.db)(\/|$)/.test(e.name));
  if (!entries.length) throw new HttpError(400, 'ZIP file is empty');
  const tops = new Set(entries.map((e) => e.name.split('/')[0]));
  if (tops.size === 1 && entries.every((e) => e.name.includes('/'))) {
    const pre = [...tops][0] + '/';
    entries = entries.map((e) => ({ ...e, name: e.name.slice(pre.length) }));
  }
  await fsp.mkdir(base, { recursive: true });
  for (const e of entries) {
    let target;
    try {
      target = safeJoin(base, e.name);
    } catch {
      continue;
    }
    await fsp.mkdir(path.dirname(target.abs), { recursive: true });
    await fsp.writeFile(target.abs, e.data);
  }
}

async function importZip(name, buffer) {
  const id = newId();
  try {
    await extractZip(buffer, filesDir(id));
  } catch (e) {
    await fsp.rm(projectDir(id), { recursive: true, force: true });
    throw e;
  }
  const now = new Date().toISOString();
  const meta = {
    id,
    name: (name || '').replace(/\.zip$/i, '').trim() || 'Imported Project',
    mainFile: 'main.tex',
    engine: 'pdflatex',
    shellEscape: false,
    template: null,
    created: now,
    modified: now,
  };
  meta.mainFile = (await detectMainFile(id)) || 'main.tex';
  meta.engine = await detectEngine(id, meta.mainFile);
  await writeMeta(id, meta);
  return meta;
}

/** Find the .tex file containing \documentclass, preferring main.tex / root-level files. */
async function detectMainFile(id) {
  return findMainFile(filesDir(id));
}

async function findMainFile(dir) {
  const files = (await walk(dir)).filter((f) => !f.isDir && /\.tex$/i.test(f.rel));
  const candidates = [];
  for (const f of files) {
    const txt = (await readText(f.abs)) || '';
    if (/^[^%\n]*\\documentclass/m.test(txt)) candidates.push(f.rel);
  }
  const score = (p) => (/(^|\/)main\.tex$/i.test(p) ? 0 : 10) + p.split('/').length;
  candidates.sort((a, b) => score(a) - score(b));
  return candidates[0] || (files[0] && files[0].rel) || null;
}

async function detectEngine(id, mainFile) {
  return engineFromSource((await readText(path.join(filesDir(id), mainFile))) || '');
}

function engineFromSource(txt) {
  if (/\\usepackage(\[[^\]]*\])?\{(fontspec|unicode-math|polyglossia)\}/.test(txt)) return 'xelatex';
  if (/\\usepackage(\[[^\]]*\])?\{(luacode|luatexja|luacolor|lua-visual-debug)\}/.test(txt) || /\\directlua/.test(txt)) return 'lualatex';
  return 'pdflatex';
}

/** Empty project folder + meta; the caller fills files/. */
async function createSkeleton({ name, mainFile = 'main.tex', engine = 'pdflatex', extra = {} }) {
  const id = newId();
  await fsp.mkdir(filesDir(id), { recursive: true });
  const now = new Date().toISOString();
  return writeMeta(id, { id, name, mainFile, engine, shellEscape: false, template: null, created: now, modified: now, ...extra });
}

async function updateMeta(id, patch) {
  const meta = await readMeta(id);
  if (patch.name !== undefined) meta.name = String(patch.name).trim() || meta.name;
  if (patch.mainFile !== undefined) {
    const { rel, abs } = safeJoin(filesDir(id), patch.mainFile);
    if (!(await exists(abs))) throw new HttpError(400, 'Main file does not exist');
    meta.mainFile = rel;
  }
  if (patch.engine !== undefined) {
    if (!ENGINES.includes(patch.engine)) throw new HttpError(400, 'Unknown engine');
    meta.engine = patch.engine;
  }
  if (patch.shellEscape !== undefined) meta.shellEscape = !!patch.shellEscape;
  meta.modified = new Date().toISOString();
  return writeMeta(id, meta);
}

async function deleteProject(id) {
  await readMeta(id);
  await fsp.rm(projectDir(id), { recursive: true, force: true });
}

async function duplicateProject(id) {
  const meta = await readMeta(id);
  const nid = newId();
  await copyDir(filesDir(id), filesDir(nid));
  const now = new Date().toISOString();
  return writeMeta(nid, { ...meta, id: nid, name: meta.name + ' (copy)', created: now, modified: now });
}

async function listFiles(id) {
  await readMeta(id);
  return (await walk(filesDir(id))).map((f) => ({
    path: f.rel,
    type: f.isDir ? 'dir' : 'file',
    size: f.size,
    mtime: f.mtimeMs,
  }));
}

function resolveFile(id, rel) {
  return safeJoin(filesDir(id), rel);
}

async function writeFile(id, rel, data) {
  const { abs, rel: r } = resolveFile(id, rel);
  await fsp.mkdir(path.dirname(abs), { recursive: true });
  await fsp.writeFile(abs, data);
  await touch(id);
  return r;
}

async function makeDir(id, rel) {
  const { abs, rel: r } = resolveFile(id, rel);
  await fsp.mkdir(abs, { recursive: true });
  await touch(id);
  return r;
}

async function renamePath(id, from, to) {
  const a = resolveFile(id, from);
  const b = resolveFile(id, to);
  if (!(await exists(a.abs))) throw new HttpError(404, 'File not found');
  if (await exists(b.abs)) throw new HttpError(409, `"${b.rel}" already exists`);
  await fsp.mkdir(path.dirname(b.abs), { recursive: true });
  await fsp.rename(a.abs, b.abs);
  const meta = await readMeta(id);
  if (meta.mainFile === a.rel) meta.mainFile = b.rel;
  else if (meta.mainFile.startsWith(a.rel + '/')) meta.mainFile = b.rel + meta.mainFile.slice(a.rel.length);
  meta.modified = new Date().toISOString();
  await writeMeta(id, meta);
  return b.rel;
}

async function deletePath(id, rel) {
  const { abs } = resolveFile(id, rel);
  if (!(await exists(abs))) throw new HttpError(404, 'File not found');
  await fsp.rm(abs, { recursive: true, force: true });
  await touch(id);
}

async function zipProject(id, extra = []) {
  const files = (await walk(filesDir(id))).filter((f) => !f.isDir);
  const entries = [];
  for (const f of files) entries.push({ name: f.rel, data: await fsp.readFile(f.abs), mtime: new Date(f.mtimeMs) });
  // Generated entries (e.g. lab/dependencies.json) never replace a file of the same name in the project.
  for (const e of extra) if (!entries.some((x) => x.name === e.name)) entries.push({ mtime: new Date(), ...e });
  return createZip(entries);
}

/** Labels, bibliography keys and file lists for editor autocompletion. */
async function symbols(id) {
  const files = (await walk(filesDir(id))).filter((f) => !f.isDir);
  const labels = [];
  const cites = [];
  const commands = [];
  for (const f of files) {
    if (f.size > 4 * 1024 * 1024) continue;
    if (/\.(tex|sty|cls|ltx)$/i.test(f.rel)) {
      const txt = (await readText(f.abs)) || '';
      const lines = txt.split(/\r?\n/);
      lines.forEach((l, i) => {
        const code = l.replace(/(^|[^\\])%.*$/, '$1');
        for (const m of code.matchAll(/\\label\{([^}]+)\}/g)) labels.push({ label: m[1], file: f.rel, line: i + 1 });
        for (const m of code.matchAll(/\\(?:re)?newcommand\*?\{?\\([A-Za-z@]+)\}?(?:\[(\d)\])?/g))
          commands.push({ name: m[1], args: m[2] ? +m[2] : 0 });
        for (const m of code.matchAll(/\\DeclareMathOperator\*?\{?\\([A-Za-z@]+)\}?/g)) commands.push({ name: m[1], args: 0 });
      });
    } else if (/\.bib$/i.test(f.rel)) {
      const txt = (await readText(f.abs)) || '';
      const re = /@(\w+)\s*[{(]\s*([^,\s]+)\s*,/g;
      let m;
      while ((m = re.exec(txt))) {
        const type = m[1].toLowerCase();
        if (['comment', 'string', 'preamble'].includes(type)) continue;
        const body = txt.slice(m.index, m.index + 3000);
        const title = (/\btitle\s*=\s*[{"]+([^}"]*)/i.exec(body) || [])[1] || '';
        const author = (/\bauthor\s*=\s*[{"]+([^}"]*)/i.exec(body) || [])[1] || '';
        const year = (/\b(?:year|date)\s*=\s*[{"]?(\d{4})/i.exec(body) || [])[1] || '';
        cites.push({ key: m[2], type, title: title.trim(), author: author.trim(), year, file: f.rel });
      }
    }
  }
  return {
    labels,
    cites,
    commands,
    files: files.map((f) => f.rel),
  };
}

module.exports = {
  PROJECTS_DIR,
  ENGINES,
  projectDir,
  filesDir,
  touch,
  buildDir,
  outputDir,
  readMeta,
  writeMeta,
  listProjects,
  listTemplates,
  createProject,
  importZip,
  extractZip,
  detectMainFile,
  findMainFile,
  engineFromSource,
  createSkeleton,
  updateMeta,
  deleteProject,
  duplicateProject,
  listFiles,
  resolveFile,
  writeFile,
  makeDir,
  renamePath,
  deletePath,
  zipProject,
  symbols,
};
