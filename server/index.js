'use strict';
// Folio Lab hub: report editor API, analysis-module proxy (/m/<id>/) and static frontend. Localhost only.
const http = require('http');
const fs = require('fs');
const fsp = fs.promises;
const path = require('path');
const { ROOT, HttpError, exists } = require('./util');
const P = require('./projects');
const compiler = require('./compiler');
const synctex = require('./synctex');
const tex = require('./tex');
const combiner = require('./combine');
const modules = require('./modules');
const lab = require('./lab');
const suite = require('./suite');
const portable = require('./portable');
const importer = require('./importer');
const folio = require('./folio');

// 4330 by default so Folio Lab can run next to a plain Folio (4321). Override with FOLIO_PORT or --port=N.
const PORT = +(process.argv.find((a) => a.startsWith('--port=')) || '').slice(7) || +process.env.FOLIO_PORT || 4330;
const HOST = process.env.FOLIO_HOST || '127.0.0.1';
const PUBLIC = path.join(ROOT, 'public');
const NM = path.join(ROOT, 'node_modules');
const MAX_BODY = 512 * 1024 * 1024;

const STATIC_MOUNTS = [
  ['/vendor/monaco/', path.join(NM, 'monaco-editor', 'min')],
  ['/vendor/pdfjs/', path.join(NM, 'pdfjs-dist', 'build')],
  ['/vendor/pdfjs-cmaps/', path.join(NM, 'pdfjs-dist', 'cmaps')],
  ['/vendor/pdfjs-fonts/', path.join(NM, 'pdfjs-dist', 'standard_fonts')],
  ['/', PUBLIC],
];

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.map': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.webp': 'image/webp',
  '.bmp': 'image/bmp',
  '.ico': 'image/x-icon',
  '.pdf': 'application/pdf',
  '.ttf': 'font/ttf',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.pfb': 'application/octet-stream',
  '.bcmap': 'application/octet-stream',
  '.tex': 'text/plain; charset=utf-8',
  '.bib': 'text/plain; charset=utf-8',
  '.txt': 'text/plain; charset=utf-8',
  '.csv': 'text/plain; charset=utf-8',
  '.log': 'text/plain; charset=utf-8',
};
const mime = (p) => MIME[path.extname(p).toLowerCase()] || 'application/octet-stream';

// ---------------------------------------------------------------- helpers
function send(res, status, body, headers = {}) {
  res.writeHead(status, { 'Cache-Control': 'no-store', ...headers });
  res.end(body);
}
function json(res, data, status = 200) {
  send(res, status, JSON.stringify(data), { 'Content-Type': 'application/json; charset=utf-8' });
}
async function sendFile(res, abs, extraHeaders = {}) {
  let st;
  try {
    st = await fsp.stat(abs);
  } catch {
    throw new HttpError(404, 'Not found');
  }
  if (!st.isFile()) throw new HttpError(404, 'Not found');
  res.writeHead(200, { 'Content-Type': mime(abs), 'Content-Length': st.size, 'Cache-Control': 'no-store', ...extraHeaders });
  fs.createReadStream(abs).pipe(res);
}
function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    req.on('data', (c) => {
      size += c.length;
      if (size > MAX_BODY) {
        reject(new HttpError(413, 'Upload too large'));
        req.destroy();
        return;
      }
      chunks.push(c);
    });
    req.on('end', () => resolve(Buffer.concat(chunks)));
    req.on('error', reject);
  });
}
async function readJson(req) {
  const b = await readBody(req);
  if (!b.length) return {};
  try {
    return JSON.parse(b.toString('utf8'));
  } catch {
    throw new HttpError(400, 'Invalid JSON');
  }
}
function contentDisposition(name) {
  const ascii = name.replace(/[^\x20-\x7e]/g, '_').replace(/"/g, '');
  return `attachment; filename="${ascii}"; filename*=UTF-8''${encodeURIComponent(name)}`;
}

// ---------------------------------------------------------------- routes
const routes = [];
function route(method, pattern, handler) {
  const keys = [];
  const re = new RegExp('^' + pattern.replace(/:(\w+)/g, (_, k) => (keys.push(k), '([^/]+)')) + '$');
  routes.push({ method, re, keys, handler });
}

route('GET', '/api/status', async (req, res, p, q) => {
  const t = tex.detect(q.get('refresh') === '1');
  json(res, { tex: t, version: require('../package.json').version, engines: P.ENGINES });
});

route('GET', '/api/templates', async (req, res) => json(res, await P.listTemplates()));
route('GET', '/api/projects', async (req, res) => json(res, await P.listProjects()));
route('POST', '/api/projects', async (req, res) => json(res, await P.createProject(await readJson(req)), 201));
route('POST', '/api/projects/import', async (req, res, p, q) => {
  const buf = await readBody(req);
  json(res, await P.importZip(q.get('name') || 'Imported Project', buf), 201);
});

// Combine several projects into one (see server/combine.js).
route('POST', '/api/combine/stage', async (req, res, p, q) => {
  const buf = await readBody(req);
  json(res, await combiner.stageZip(q.get('name') || 'Project.zip', buf), 201);
});
route('DELETE', '/api/combine/stage/:sid', async (req, res, p) => {
  await combiner.removeStage(p.sid);
  json(res, { ok: true });
});
route('POST', '/api/combine/analyze', async (req, res) => {
  const body = await readJson(req);
  json(res, await combiner.analyzeProject(String(body.project || '')));
});
route('POST', '/api/combine', async (req, res) => json(res, await combiner.combine(await readJson(req)), 201));

route('GET', '/api/projects/:id', async (req, res, p) => {
  const meta = await P.readMeta(p.id);
  const files = await P.listFiles(p.id);
  let build = null;
  try {
    build = JSON.parse(await fsp.readFile(path.join(P.outputDir(p.id), 'build.json'), 'utf8'));
  } catch {
    /* never compiled */
  }
  json(res, { ...meta, files, build, compiling: compiler.isRunning(p.id) });
});
route('PATCH', '/api/projects/:id', async (req, res, p) => json(res, await P.updateMeta(p.id, await readJson(req))));
route('DELETE', '/api/projects/:id', async (req, res, p) => {
  compiler.stop(p.id);
  await P.deleteProject(p.id);
  json(res, { ok: true });
});
route('POST', '/api/projects/:id/duplicate', async (req, res, p) => json(res, await P.duplicateProject(p.id), 201));
route('GET', '/api/projects/:id/zip', async (req, res, p, q) => {
  const meta = await P.readMeta(p.id);
  await lab.issueAll(p.id, 'zip').catch(() => {}); // Q22 a): export fixes the current result revisions
  if (q.get('portable') === '1') {
    // self-contained folder for any other LaTeX project (server/portable.js)
    const out = await portable.exportPortable(p.id, { prefix: q.get('prefix') || '' });
    send(res, 200, out.buffer, { 'Content-Type': 'application/zip', 'Content-Disposition': contentDisposition(out.filename) });
    return;
  }
  const deps = await lab.dependencies(p.id).catch(() => null); // A8 / UI-09: what the results rest on
  const buf = await P.zipProject(p.id, deps ? [{ name: 'lab/dependencies.json', data: Buffer.from(JSON.stringify(deps, null, 2)) }] : []);
  send(res, 200, buf, {
    'Content-Type': 'application/zip',
    'Content-Disposition': contentDisposition(meta.name.replace(/[\\/:*?"<>|]/g, '_') + '.zip'),
  });
});

route('GET', '/api/projects/:id/files', async (req, res, p) => json(res, await P.listFiles(p.id)));
route('GET', '/api/projects/:id/file', async (req, res, p, q) => {
  await P.readMeta(p.id);
  const { abs, rel } = P.resolveFile(p.id, q.get('path'));
  const headers = q.get('download') === '1' ? { 'Content-Disposition': contentDisposition(path.basename(rel)) } : {};
  await sendFile(res, abs, headers);
});
route('PUT', '/api/projects/:id/file', async (req, res, p, q) => {
  await P.readMeta(p.id);
  const data = await readBody(req);
  const rel = await P.writeFile(p.id, q.get('path'), data);
  json(res, { ok: true, path: rel, size: data.length });
});
route('DELETE', '/api/projects/:id/file', async (req, res, p, q) => {
  await P.deletePath(p.id, q.get('path'));
  json(res, { ok: true });
});
route('POST', '/api/projects/:id/folder', async (req, res, p) => {
  const body = await readJson(req);
  json(res, { ok: true, path: await P.makeDir(p.id, body.path) });
});
route('POST', '/api/projects/:id/rename', async (req, res, p) => {
  const body = await readJson(req);
  json(res, { ok: true, path: await P.renamePath(p.id, body.from, body.to) });
});
route('GET', '/api/projects/:id/symbols', async (req, res, p) => json(res, await P.symbols(p.id)));

route('POST', '/api/projects/:id/compile', async (req, res, p) => {
  const body = await readJson(req);
  json(res, await compiler.compile(p.id, body));
});
route('POST', '/api/projects/:id/stop', async (req, res, p) => json(res, { stopped: compiler.stop(p.id) }));
route('POST', '/api/projects/:id/clean', async (req, res, p) => {
  await P.readMeta(p.id);
  await compiler.clean(p.id);
  json(res, { ok: true });
});
route('GET', '/api/projects/:id/output.pdf', async (req, res, p, q) => {
  const meta = await P.readMeta(p.id);
  const headers =
    q.get('download') === '1'
      ? { 'Content-Disposition': contentDisposition(meta.name.replace(/[\\/:*?"<>|]/g, '_') + '.pdf') }
      : { 'Content-Disposition': 'inline' };
  if (q.get('download') === '1') await lab.issueAll(p.id, 'pdf').catch(() => {}); // Q22 a)
  await sendFile(res, path.join(P.outputDir(p.id), 'output.pdf'), headers);
});
route('GET', '/api/projects/:id/output.log', async (req, res, p) => {
  await P.readMeta(p.id);
  await sendFile(res, path.join(P.outputDir(p.id), 'output.log'));
});

route('GET', '/api/projects/:id/synctex/forward', async (req, res, p, q) => {
  const build = JSON.parse(await fsp.readFile(path.join(P.outputDir(p.id), 'build.json'), 'utf8'));
  const boxes = await synctex.forward(P.buildDir(p.id), build.job + '.pdf', q.get('file'), +q.get('line') || 1, +q.get('column') || 0);
  json(res, boxes);
});
route('GET', '/api/projects/:id/synctex/inverse', async (req, res, p, q) => {
  const build = JSON.parse(await fsp.readFile(path.join(P.outputDir(p.id), 'build.json'), 'utf8'));
  const r = await synctex.inverse(P.buildDir(p.id), build.job + '.pdf', +q.get('page'), +q.get('x'), +q.get('y'));
  json(res, r || {});
});

// ---------------------------------------------------------------- analysis modules (server/modules.js)
route('GET', '/api/suite', async (req, res) => json(res, await suite.list()));
route('GET', '/api/suite/envs', async (req, res) => json(res, await suite.envs())); // UI-09: open environment per module
route('POST', '/api/suite/projects', async (req, res) => json(res, await suite.create(await readJson(req)), 201));
route('PATCH', '/api/suite/projects/:pid', async (req, res, p) => json(res, await suite.update(p.pid, await readJson(req))));
route('POST', '/api/suite/active', async (req, res) => json(res, await suite.activate((await readJson(req)).id)));
route('GET', '/api/modules', async (req, res) => json(res, (await modules.list()).map(modules.publicInfo)));
route('POST', '/api/modules/:id/start', async (req, res, p) => {
  await modules.ensure(p.id);
  json(res, modules.publicInfo(await modules.get(p.id)));
});
route('POST', '/api/modules/:id/stop', async (req, res, p) => json(res, { stopped: modules.stop(p.id) }));

// ---------------------------------------------------------------- results in reports (server/lab.js)
route('GET', '/api/projects/:id/lab', async (req, res, p) => json(res, await lab.list(p.id)));
route('POST', '/api/projects/:id/lab', async (req, res, p, q) => json(res, await lab.save(p.id, await readJson(req), q.get('mode') || undefined), 201));
route('POST', '/api/projects/:id/lab/:slug/refresh', async (req, res, p) => json(res, await lab.refresh(p.id, p.slug, await readJson(req))));
route('POST', '/api/projects/:id/lab/:slug/pick', async (req, res, p) => json(res, await lab.repick(p.id, p.slug, await readJson(req))));
route('POST', '/api/projects/:id/lab/:slug/fork', async (req, res, p) => json(res, await lab.fork(p.id, p.slug, await readJson(req))));
route('POST', '/api/projects/:id/lab/:slug/preview', async (req, res, p) => json(res, await lab.preview(p.id, p.slug, await readJson(req))));
route('GET', '/api/projects/:id/lab/:slug/forks', async (req, res, p) => json(res, await lab.forksOf(p.id, p.slug)));
route('GET', '/api/projects/:id/lab/:slug/revisions', async (req, res, p) => json(res, await lab.revisions(p.id, p.slug)));
route('GET', '/api/projects/:id/lab/:slug/history', async (req, res, p) => json(res, await lab.history(p.id, p.slug))); // UI-09
route('GET', '/api/projects/:id/lab/:slug/compare', async (req, res, p, q) => json(res, await lab.compare(p.id, p.slug, q.get('a'), q.get('b'))));
route('POST', '/api/projects/:id/lab/:slug/restore', async (req, res, p) => json(res, await lab.restore(p.id, p.slug, (await readJson(req)).revision)));
route('POST', '/api/projects/:id/lab/:slug/issue', async (req, res, p) => json(res, await lab.issue(p.id, p.slug, 'manual')));
route('DELETE', '/api/projects/:id/lab/:slug', async (req, res, p, q) => {
  json(res, { ok: true, ...(await lab.remove(p.id, p.slug, { section: q.get('section') === '1' })) });
});
route('GET', '/api/projects/:id/lab/:slug/uses-info', async (req, res, p) => json(res, await lab.usesInfo(p.id, p.slug)));
route('POST', '/api/projects/:id/lab-undo', async (req, res, p) => json(res, await lab.restoreRemoved(p.id, (await readJson(req)).undo)));

// ---------------------------------------------------------------- import into reports (server/importer.js)
const srcDesc = (q) => ({ type: q.get('type'), project: q.get('project'), stage: q.get('stage') });
route('GET', '/api/import/sources', async (req, res, p, q) => json(res, await importer.sources(q.get('target') || '')));
route('GET', '/api/import/pieces', async (req, res, p, q) => json(res, await importer.pieces(srcDesc(q))));
route('GET', '/api/import/file', async (req, res, p, q) => sendFile(res, await importer.sourceFile(srcDesc(q), q.get('path'))));
route('POST', '/api/import/stage', async (req, res, p, q) => {
  const buf = await readBody(req);
  json(res, await combiner.stageZip(q.get('name') || 'Project.zip', buf), 201);
});
// Module environments of the active suite project as import sources (server/folio.js)
route('GET', '/api/folio/modules', async (req, res) => json(res, await folio.listModules()));
route('GET', '/api/folio/env', async (req, res, p, q) => json(res, await folio.envPieces(q.get('module'), q.get('env'), q.get('lang'), q.get('target'))));
route('GET', '/api/folio/file', async (req, res, p, q) => sendFile(res, await folio.stageFile(q.get('stage'), q.get('path'))));
route('POST', '/api/projects/:id/import', async (req, res, p) => json(res, await importer.importPieces(p.id, await readJson(req)), 201));
route('GET', '/api/projects/:id/import/links', async (req, res, p) => json(res, await importer.linkStates(p.id)));
route('POST', '/api/projects/:id/import/:slug/update', async (req, res, p) => json(res, await importer.update(p.id, p.slug, await readJson(req))));
route('POST', '/api/projects/:id/import/:slug/mode', async (req, res, p) => json(res, await importer.setMode(p.id, p.slug, (await readJson(req)).mode)));

// ---------------------------------------------------------------- static
async function serveStatic(req, res, pathname) {
  if (pathname === '/' || pathname === '/index.html') return sendFile(res, path.join(PUBLIC, 'index.html'));
  if (/^\/project\/[a-f0-9]{12}\/?$/.test(pathname)) return sendFile(res, path.join(PUBLIC, 'editor.html'));
  for (const [prefix, dir] of STATIC_MOUNTS) {
    if (!pathname.startsWith(prefix)) continue;
    const rel = decodeURIComponent(pathname.slice(prefix.length));
    const abs = path.resolve(dir, rel);
    if (!abs.startsWith(path.resolve(dir) + path.sep)) continue;
    if (await exists(abs)) return sendFile(res, abs, prefix.startsWith('/vendor/') ? { 'Cache-Control': 'max-age=86400' } : {});
  }
  throw new HttpError(404, 'Not found');
}

// ---------------------------------------------------------------- server
function isAllowedHost(host) {
  if (!host) return false;
  const h = host.replace(/:\d+$/, '').replace(/^\[|\]$/g, '');
  return h === 'localhost' || h === '127.0.0.1' || h === '::1' || h === HOST;
}

const server = http.createServer(async (req, res) => {
  try {
    // Guard against DNS rebinding and cross-site requests from other web pages.
    if (!isAllowedHost(req.headers.host)) throw new HttpError(403, 'Forbidden host');
    const url = new URL(req.url, `http://${req.headers.host}`);
    const pathname = url.pathname;
    const mm = /^\/m\/([a-z0-9-]+)(\/.*)?$/.exec(pathname);
    if (mm) {
      if (!mm[2]) return send(res, 302, '', { Location: `/m/${mm[1]}/${url.search}` });
      if (req.method !== 'GET' && req.method !== 'HEAD' && req.headers.origin) {
        let oh = '';
        try {
          oh = new URL(req.headers.origin).host;
        } catch {
          /* malformed */
        }
        if (!isAllowedHost(oh)) throw new HttpError(403, 'Forbidden origin');
      }
      return await modules.proxy(req, res, mm[1], mm[2], url.search);
    }
    if (pathname.startsWith('/api/')) {
      if (req.method !== 'GET' && req.headers['x-folio'] !== '1') throw new HttpError(403, 'Missing X-Folio header');
      for (const r of routes) {
        if (r.method !== req.method) continue;
        const m = r.re.exec(pathname);
        if (!m) continue;
        const params = {};
        r.keys.forEach((k, i) => (params[k] = decodeURIComponent(m[i + 1])));
        return await r.handler(req, res, params, url.searchParams);
      }
      throw new HttpError(404, 'Unknown API route');
    }
    if (req.method !== 'GET' && req.method !== 'HEAD') throw new HttpError(405, 'Method not allowed');
    await serveStatic(req, res, pathname);
  } catch (e) {
    const status = e.status || 500;
    if (status === 500) console.error(e);
    if (!res.headersSent) json(res, { error: e.message || 'Server error', ...(e.body || {}) }, status);
    else res.end();
  }
});

server.on('error', (e) => {
  if (e.code === 'EADDRINUSE') {
    console.error(`Port ${PORT} is already in use. Is Folio Lab already running? Open http://localhost:${PORT}`);
    process.exit(1);
  }
  throw e;
});

server.listen(PORT, HOST, () => {
  const t = tex.detect();
  console.log('');
  console.log('  Folio Lab - data analysis and report writing');
  console.log(`  Open:      http://localhost:${PORT}`);
  console.log(`  Projects:  ${P.PROJECTS_DIR}`);
  console.log(`  TeX:       ${t.found ? `${t.distribution} (${t.binDir})` : 'NOT FOUND - run setup.ps1'}`);
  modules.list().then((ms) => console.log(`  Modules:   ${ms.map((m) => m.name + (m.status === 'ready' ? '' : ' (' + m.status + ')')).join(', ') || 'none'}`));
  console.log('  Press Ctrl+C to stop.');
  console.log('');
  if (process.argv.includes('--open')) {
    const url = `http://localhost:${PORT}`;
    const cmd = process.platform === 'win32' ? 'cmd' : process.platform === 'darwin' ? 'open' : 'xdg-open';
    const args = process.platform === 'win32' ? ['/c', 'start', '', url] : [url];
    require('child_process').spawn(cmd, args, { detached: true, stdio: 'ignore', windowsHide: true }).unref();
  }
});
