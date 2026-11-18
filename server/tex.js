'use strict';
// Locates a TeX distribution: the bundled portable MiKTeX first, then PATH, then common install dirs.
const fs = require('fs');
const path = require('path');
const { ROOT } = require('./util');

const EXE = process.platform === 'win32' ? '.exe' : '';
const TOOLS = ['pdflatex', 'xelatex', 'lualatex', 'bibtex', 'biber', 'makeindex', 'synctex'];

let cached = null;

function candidateDirs() {
  const dirs = [];
  if (process.env.FOLIO_TEX_BIN) dirs.push(process.env.FOLIO_TEX_BIN);
  dirs.push(path.join(ROOT, 'tools', 'miktex', 'texmfs', 'install', 'miktex', 'bin', 'x64'));
  dirs.push(path.join(ROOT, 'tools', 'miktex', 'texmfs', 'install', 'miktex', 'bin'));
  for (const p of (process.env.PATH || '').split(path.delimiter)) if (p) dirs.push(p);
  if (process.platform === 'win32') {
    const la = process.env.LOCALAPPDATA;
    const pf = process.env.ProgramFiles || 'C:\\Program Files';
    if (la) dirs.push(path.join(la, 'Programs', 'MiKTeX', 'miktex', 'bin', 'x64'));
    dirs.push(path.join(pf, 'MiKTeX', 'miktex', 'bin', 'x64'));
    try {
      const years = fs.readdirSync('C:\\texlive').filter((d) => /^\d{4}$/.test(d)).sort().reverse();
      for (const y of years) {
        dirs.push(path.join('C:\\texlive', y, 'bin', 'windows'));
        dirs.push(path.join('C:\\texlive', y, 'bin', 'win64'));
        dirs.push(path.join('C:\\texlive', y, 'bin', 'win32'));
      }
    } catch {
      /* no TeX Live */
    }
  } else {
    dirs.push('/Library/TeX/texbin', '/usr/local/bin', '/usr/bin');
  }
  return dirs;
}

function detect(force = false) {
  if (cached && !force) return cached;
  let binDir = null;
  for (const d of candidateDirs()) {
    try {
      if (fs.existsSync(path.join(d, 'pdflatex' + EXE))) {
        binDir = d;
        break;
      }
    } catch {
      /* ignore */
    }
  }
  const tools = {};
  if (binDir) {
    for (const t of TOOLS) {
      const p = path.join(binDir, t + EXE);
      tools[t] = fs.existsSync(p) ? p : null;
    }
  }
  cached = {
    found: !!binDir,
    binDir,
    tools,
    bundled: !!binDir && binDir.startsWith(path.join(ROOT, 'tools')),
    distribution: binDir ? (/miktex/i.test(binDir) ? 'MiKTeX' : /texlive/i.test(binDir) ? 'TeX Live' : 'TeX') : null,
  };
  return cached;
}

/** Environment for spawning TeX tools. */
function texEnv(extra = {}) {
  const t = detect();
  const env = { ...process.env, ...extra };
  if (t.binDir) {
    const key = Object.keys(env).find((k) => k.toUpperCase() === 'PATH') || 'PATH';
    env[key] = t.binDir + path.delimiter + (env[key] || '');
  }
  env.max_print_line = '10000';
  env.error_line = '254';
  env.half_error_line = '238';
  return env;
}

function tool(name) {
  const t = detect();
  if (!t.binDir) return null;
  return t.tools[name] || path.join(t.binDir, name + EXE);
}

module.exports = { detect, texEnv, tool };
