'use strict';
// Analysis modules: discovery, sidecar processes and the /m/<id>/ reverse proxy.
//
// Every folder under modules/ with a module.json is a module. A module with a runtime is a small
// local HTTP app (Python today, anything that can listen on a port tomorrow). The hub starts it on
// demand on a free localhost port and proxies it under /m/<id>/, so the module page shares the
// hub's origin and can talk to the report side through /lab/sdk.js. See docs/MODULES.md.
const fs = require('fs');
const fsp = fs.promises;
const path = require('path');
const http = require('http');
const net = require('net');
const { spawn, spawnSync } = require('child_process');
const { ROOT, HttpError } = require('./util');

const MODULES_DIR = path.join(ROOT, 'modules');
const SDK_PY = path.join(ROOT, 'sdk', 'python');
const OUTPUTS_DIR = process.env.LAB_OUTPUTS || path.join(ROOT, 'outputs');
const START_TIMEOUT = 45000;

const running = new Map(); // id -> { proc, port, ready: Promise<number>, state, error, log: [] }

// ---------------------------------------------------------------- discovery
async function readManifest(dir) {
  try {
    const m = JSON.parse(await fsp.readFile(path.join(MODULES_DIR, dir, 'module.json'), 'utf8'));
    if (!m.id || !/^[a-z0-9-]{1,40}$/.test(m.id)) return null;
    return { status: 'ready', icon: 'chart', ...m, dir: path.join(MODULES_DIR, dir) };
  } catch {
    return null;
  }
}

async function list() {
  let dirs = [];
  try {
    dirs = (await fsp.readdir(MODULES_DIR, { withFileTypes: true })).filter((d) => d.isDirectory()).map((d) => d.name);
  } catch {
    /* no modules folder */
  }
  const out = [];
  for (const d of dirs) {
    const m = await readManifest(d);
    if (m) out.push(m);
  }
  out.sort((a, b) => (a.order ?? 100) - (b.order ?? 100) || a.name.localeCompare(b.name));
  return out;
}

async function get(id) {
  const m = (await list()).find((x) => x.id === id);
  if (!m) throw new HttpError(404, `Unknown module "${id}"`);
  return m;
}

function publicInfo(m) {
  const r = running.get(m.id);
  const { dir, runtime, ...rest } = m;
  return {
    ...rest,
    runtime: runtime ? runtime.type : null,
    state: m.status !== 'ready' ? m.status : r ? r.state : 'stopped',
    error: r && r.error ? r.error : null,
    url: m.status === 'ready' && runtime ? `/m/${m.id}/` : null,
  };
}

// ---------------------------------------------------------------- python
let pythonCache;
function findPython() {
  if (pythonCache !== undefined) return pythonCache;
  const candidates = [];
  if (process.env.LAB_PYTHON) candidates.push([process.env.LAB_PYTHON, []]);
  const lad = process.env.LOCALAPPDATA;
  if (lad) {
    const base = path.join(lad, 'Programs', 'Python');
    try {
      fs.readdirSync(base)
        .filter((n) => /^Python3\d+$/.test(n))
        .sort((a, b) => +b.slice(7) - +a.slice(7))
        .forEach((n) => candidates.push([path.join(base, n, 'python.exe'), []]));
    } catch {
      /* not installed per-user */
    }
  }
  if (process.platform === 'win32') candidates.push(['py', ['-3']]);
  candidates.push(['python3', []], ['python', []]);
  for (const [cmd, pre] of candidates) {
    try {
      const r = spawnSync(cmd, [...pre, '-c', 'import sys; print(sys.version_info[0]*100+sys.version_info[1])'], {
        encoding: 'utf8',
        windowsHide: true,
        timeout: 8000,
      });
      if (r.status === 0 && +r.stdout.trim() >= 310) return (pythonCache = { cmd, pre });
    } catch {
      /* try next */
    }
  }
  return (pythonCache = null);
}

// ---------------------------------------------------------------- lifecycle
function freePort() {
  return new Promise((resolve, reject) => {
    const s = net.createServer();
    s.unref();
    s.on('error', reject);
    s.listen(0, '127.0.0.1', () => {
      const { port } = s.address();
      s.close(() => resolve(port));
    });
  });
}

function probe(port, p) {
  return new Promise((resolve) => {
    const req = http.get({ host: '127.0.0.1', port, path: p, timeout: 1500 }, (res) => {
      res.resume();
      resolve(res.statusCode < 500);
    });
    req.on('error', () => resolve(false));
    req.on('timeout', () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function start(m) {
  const rt = m.runtime;
  if (!rt) throw new HttpError(400, `Module "${m.id}" has no runtime`);
  let cmd;
  let pre = [];
  if (rt.type === 'python') {
    const py = findPython();
    if (!py) throw new HttpError(500, 'Python 3.10+ not found. Run setup.ps1 or set LAB_PYTHON.');
    ({ cmd, pre } = py);
  } else if (rt.type === 'command') {
    cmd = rt.command;
  } else {
    throw new HttpError(400, `Unsupported runtime "${rt.type}"`);
  }
  const port = await freePort();
  const outputs = path.join(OUTPUTS_DIR, m.id);
  await fsp.mkdir(outputs, { recursive: true });
  const subst = (a) => String(a).replace('{port}', port).replace('{outputs}', outputs).replace('{module}', m.dir);
  const args = [...pre, ...(rt.args || []).map(subst)];
  const env = {
    ...process.env,
    PYTHONPATH: [m.dir, SDK_PY, process.env.PYTHONPATH].filter(Boolean).join(path.delimiter),
    PYTHONIOENCODING: 'utf-8',
    PYTHONUNBUFFERED: '1',
    FOLIO_LAB: '1',
    FOLIO_SUITE_DIR: require('./suite').SUITE_DIR,
  };
  const proc = spawn(cmd, args, { cwd: path.resolve(m.dir, rt.cwd || '.'), env, windowsHide: true });
  const entry = { proc, port, state: 'starting', error: null, log: [] };
  running.set(m.id, entry);
  const keep = (buf) => {
    for (const line of buf.toString('utf8').split(/\r?\n/)) {
      if (!line.trim()) continue;
      entry.log.push(line);
      if (entry.log.length > 200) entry.log.shift();
      console.log(`  [${m.id}] ${line}`);
    }
  };
  proc.stdout.on('data', keep);
  proc.stderr.on('data', keep);

  entry.ready = new Promise((resolve, reject) => {
    let done = false;
    proc.on('exit', (code) => {
      entry.state = 'stopped';
      if (!done) {
        done = true;
        entry.error = `exited with code ${code}: ${entry.log.slice(-6).join(' | ')}`;
        entry.state = 'error';
        reject(new HttpError(502, `Module "${m.id}" could not start (${entry.error})`));
      } else if (running.get(m.id) === entry) {
        running.delete(m.id);
      }
    });
    proc.on('error', (e) => {
      if (done) return;
      done = true;
      entry.state = 'error';
      entry.error = e.message;
      reject(new HttpError(502, `Module "${m.id}" could not start: ${e.message}`));
    });
    const t0 = Date.now();
    (async function poll() {
      while (!done) {
        if (await probe(port, rt.health || '/')) {
          done = true;
          entry.state = 'running';
          return resolve(port);
        }
        if (Date.now() - t0 > START_TIMEOUT) {
          done = true;
          entry.state = 'error';
          entry.error = 'start timed out';
          proc.kill();
          return reject(new HttpError(504, `Module "${m.id}" did not answer within ${START_TIMEOUT / 1000} s`));
        }
        await new Promise((r) => setTimeout(r, 200));
      }
    })();
  });
  return entry.ready;
}

/** Port of the running module, starting it if needed. */
async function ensure(id) {
  const r = running.get(id);
  if (r && r.state !== 'error' && r.state !== 'stopped') return r.ready;
  const m = await get(id);
  if (m.status !== 'ready') throw new HttpError(409, `Module "${m.name}" is ${m.status}`);
  return start(m);
}

function stop(id) {
  const r = running.get(id);
  if (!r) return false;
  running.delete(id);
  try {
    r.proc.kill();
  } catch {
    /* already gone */
  }
  return true;
}

function stopAll() {
  for (const id of [...running.keys()]) stop(id);
}
process.on('exit', stopAll);
for (const sig of ['SIGINT', 'SIGTERM', 'SIGBREAK', 'SIGHUP']) {
  process.on(sig, () => {
    stopAll();
    process.exit(0);
  });
}

// ---------------------------------------------------------------- calls and proxy
/** JSON POST to a module endpoint (used by the hub, e.g. for Refresh). */
async function call(id, p, body) {
  const port = await ensure(id);
  const data = Buffer.from(JSON.stringify(body || {}));
  return new Promise((resolve, reject) => {
    const req = http.request(
      { host: '127.0.0.1', port, path: p, method: 'POST', headers: { 'Content-Type': 'application/json', 'Content-Length': data.length } },
      (res) => {
        const chunks = [];
        res.on('data', (c) => chunks.push(c));
        res.on('end', () => {
          let j;
          try {
            j = JSON.parse(Buffer.concat(chunks).toString('utf8'));
          } catch {
            return reject(new HttpError(502, `Module "${id}" answered with something other than JSON`));
          }
          if (res.statusCode >= 400) return reject(new HttpError(res.statusCode, j.error || `Module "${id}" error ${res.statusCode}`));
          resolve(j);
        });
      }
    );
    req.setTimeout(300000, () => req.destroy(new HttpError(504, `Module "${id}" timed out`)));
    req.on('error', reject);
    req.end(data);
  });
}

const HOP = new Set(['connection', 'keep-alive', 'proxy-connection', 'transfer-encoding', 'upgrade', 'host']);

/** Forward a browser request under /m/<id>/... to the module. */
async function proxy(req, res, id, rest, search) {
  const port = await ensure(id);
  const headers = {};
  for (const [k, v] of Object.entries(req.headers)) if (!HOP.has(k)) headers[k] = v;
  headers.host = `127.0.0.1:${port}`;
  headers['x-forwarded-prefix'] = `/m/${id}`;
  await new Promise((resolve, reject) => {
    const up = http.request({ host: '127.0.0.1', port, path: rest + search, method: req.method, headers }, (ur) => {
      const h = {};
      for (const [k, v] of Object.entries(ur.headers)) if (!HOP.has(k)) h[k] = v;
      res.writeHead(ur.statusCode, h);
      ur.pipe(res);
      ur.on('end', resolve);
      ur.on('error', reject);
    });
    up.setTimeout(300000, () => up.destroy(new HttpError(504, `Module "${id}" timed out`)));
    up.on('error', (e) => reject(e.status ? e : new HttpError(502, `Module "${id}" unreachable: ${e.message}`)));
    req.pipe(up);
  });
}

module.exports = { MODULES_DIR, OUTPUTS_DIR, list, get, publicInfo, ensure, stop, stopAll, call, proxy, findPython };
