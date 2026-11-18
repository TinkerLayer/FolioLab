'use strict';
// Compile pipeline: sync sources -> engine -> (bibtex|biber, makeindex, glossaries) -> rerun until stable.
const fs = require('fs');
const fsp = fs.promises;
const path = require('path');
const { spawn, execFile } = require('child_process');
const { exists, readText, walk, sha1, HttpError } = require('./util');
const P = require('./projects');
const tex = require('./tex');
const { parseTexLog, parseBibtexLog, parseBiberLog } = require('./logparser');

const MAX_RUNS = 5;
const RUN_TIMEOUT_MS = 10 * 60 * 1000; // first runs may download packages
const AUX_EXTS = /\.(aux|toc|lof|lot|loa|out|nav|snm|bcf|glo|acn|nlo|idx|thm|loe)$/i;
const running = new Map(); // id -> { proc, cancelled }

/** Mirror source files into the build dir without touching generated aux files. */
async function syncSources(src, dest) {
  await fsp.mkdir(dest, { recursive: true });
  const manifestPath = path.join(dest, '.folio-sources.json');
  let previous = [];
  try {
    previous = JSON.parse(await fsp.readFile(manifestPath, 'utf8'));
  } catch {
    /* first build */
  }
  const files = await walk(src);
  const current = [];
  for (const f of files) {
    const target = path.join(dest, f.rel);
    if (f.isDir) {
      await fsp.mkdir(target, { recursive: true });
      continue;
    }
    current.push(f.rel);
    let st = null;
    try {
      st = await fsp.stat(target);
    } catch {
      /* missing */
    }
    if (!st || st.size !== f.size || Math.abs(st.mtimeMs - f.mtimeMs) > 1) {
      await fsp.mkdir(path.dirname(target), { recursive: true });
      await fsp.copyFile(f.abs, target);
      const t = new Date(f.mtimeMs);
      await fsp.utimes(target, t, t);
    }
  }
  const cur = new Set(current);
  for (const rel of previous) {
    if (!cur.has(rel)) await fsp.rm(path.join(dest, rel), { force: true });
  }
  await fsp.writeFile(manifestPath, JSON.stringify(current));
}

function killTree(proc) {
  if (!proc || proc.exitCode !== null) return;
  if (process.platform === 'win32') {
    execFile('taskkill', ['/pid', String(proc.pid), '/T', '/F'], { windowsHide: true }, () => {});
  } else {
    proc.kill('SIGKILL');
  }
}

function run(state, exe, args, cwd) {
  return new Promise((resolve) => {
    const started = Date.now();
    let output = '';
    let proc;
    try {
      proc = spawn(exe, args, { cwd, env: tex.texEnv(), windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
    } catch (e) {
      return resolve({ code: -1, output: String(e), ms: 0 });
    }
    state.proc = proc;
    const onData = (d) => {
      if (output.length < 2_000_000) output += d.toString();
    };
    proc.stdout.on('data', onData);
    proc.stderr.on('data', onData);
    const timer = setTimeout(() => {
      state.timedOut = true;
      killTree(proc);
    }, RUN_TIMEOUT_MS);
    proc.on('error', (e) => {
      clearTimeout(timer);
      resolve({ code: -1, output: output + String(e), ms: Date.now() - started });
    });
    proc.on('close', (code) => {
      clearTimeout(timer);
      state.proc = null;
      resolve({ code, output, ms: Date.now() - started });
    });
  });
}

async function hashFiles(dir, filter) {
  const files = (await walk(dir)).filter((f) => !f.isDir && filter(f.rel)).sort((a, b) => a.rel.localeCompare(b.rel));
  const parts = [];
  for (const f of files) parts.push(f.rel + ':' + sha1(await fsp.readFile(f.abs)));
  return sha1(parts.join('\n'));
}

async function readState(file) {
  try {
    return JSON.parse(await fsp.readFile(file, 'utf8'));
  } catch {
    return {};
  }
}

async function compile(id, opts = {}) {
  const meta = await P.readMeta(id);
  if (running.has(id)) throw new HttpError(409, 'A compile is already running for this project');
  const engine = opts.engine && P.ENGINES.includes(opts.engine) ? opts.engine : meta.engine;
  const mainFile = meta.mainFile;
  const started = Date.now();
  const t = tex.detect();
  if (!t.found) {
    return {
      status: 'failure',
      errors: [{ level: 'error', message: 'No TeX distribution found. Run setup.ps1 (Windows) or install TeX Live / MiKTeX.' }],
      warnings: [],
      typesetting: [],
      log: '',
      runs: [],
      duration: 0,
    };
  }
  const src = P.filesDir(id);
  if (!(await exists(path.join(src, mainFile)))) {
    return {
      status: 'failure',
      errors: [{ level: 'error', message: `Main file "${mainFile}" not found. Choose a main document in the project settings.` }],
      warnings: [],
      typesetting: [],
      log: '',
      runs: [],
      duration: 0,
    };
  }

  const state = { proc: null, cancelled: false, timedOut: false };
  running.set(id, state);
  try {
    const build = P.buildDir(id);
    const stateFile = path.join(build, '.folio-state.json');
    if (opts.clean) await fsp.rm(build, { recursive: true, force: true });
    await syncSources(src, build);
    const prev = await readState(stateFile);
    if (prev.engine && prev.engine !== engine) {
      // Different engines write incompatible aux data; start fresh.
      for (const f of await walk(build)) if (!f.isDir && AUX_EXTS.test(f.rel)) await fsp.rm(f.abs, { force: true });
    }

    const job = path.basename(mainFile).replace(/\.[^.]+$/, '');
    const jobPath = (ext) => path.join(build, job + ext);
    const runs = [];
    const engineArgs = ['-synctex=1', '-interaction=nonstopmode', '-file-line-error'];
    if (t.distribution === 'MiKTeX') engineArgs.push('-max-print-line=10000', '-enable-installer');
    // Off = TeX's default "restricted" mode (only safe tools like epstopdf may run).
    if (meta.shellEscape) engineArgs.push('-shell-escape');
    if (opts.draft) engineArgs.push('-draftmode');
    engineArgs.push(mainFile.replace(/\\/g, '/'));

    const engineExe = tex.tool(engine);
    let log = '';
    let engineRuns = 0;
    const runEngine = async () => {
      const r = await run(state, engineExe, engineArgs, build);
      engineRuns++;
      runs.push({ tool: engine, ms: r.ms, code: r.code });
      log = (await readText(jobPath('.log'))) || r.output;
      return r;
    };

    let auxHash = await hashFiles(build, (r) => AUX_EXTS.test(r));
    const bibState = prev.bib || {};
    const idxState = prev.idx || {};
    let bibLog = '';
    let bibTool = null;

    const first = await runEngine();
    let fatal = !(await exists(jobPath('.pdf'))) && /Emergency stop|Fatal error occurred|no output PDF/i.test(log);

    while (!state.cancelled && !state.timedOut && !fatal) {
      let extra = false;

      // --- Bibliography
      const aux = (await readText(jobPath('.aux'))) || '';
      const bcfExists = await exists(jobPath('.bcf'));
      if (/Please \(?re\)?run Biber|run Biber on the file/i.test(log) || (bcfExists && !/\\bibdata\{/.test(aux))) {
        bibTool = 'biber';
      } else if (/\\bibdata\{/.test(aux)) {
        bibTool = 'bibtex';
      }
      if (bibTool) {
        const inputHash =
          bibTool === 'biber'
            ? sha1((await readText(jobPath('.bcf'))) || '')
            : sha1(
                (await walk(build))
                  .filter((f) => !f.isDir && /\.aux$/i.test(f.rel))
                  .map((f) => fs.readFileSync(f.abs, 'utf8').split('\n').filter((l) => /^\\(citation|bibdata|bibstyle|@input)/.test(l)).join('\n'))
                  .join('\n')
              );
        const sources = await hashFiles(build, (r) => /\.(bib|bst|bbx|cbx|lbx)$/i.test(r));
        const key = bibTool + ':' + inputHash + ':' + sources;
        if (bibState.key !== key || !(await exists(jobPath('.bbl')))) {
          const exe = tex.tool(bibTool);
          const r = await run(state, exe, [job], build);
          runs.push({ tool: bibTool, ms: r.ms, code: r.code });
          bibLog = (await readText(jobPath('.blg'))) || r.output;
          bibState.key = key;
          extra = true;
        } else {
          bibLog = (await readText(jobPath('.blg'))) || '';
        }
      }

      // --- Index / glossaries / nomenclature (all via makeindex)
      const indexJobs = [
        { input: '.idx', args: (j) => [j + '.idx'] },
        { input: '.nlo', args: (j) => [j + '.nlo', '-s', 'nomencl.ist', '-o', j + '.nls'] },
        { input: '.glo', needs: '.ist', args: (j) => ['-s', j + '.ist', '-t', j + '.glg', '-o', j + '.gls', j + '.glo'] },
        { input: '.acn', needs: '.ist', args: (j) => ['-s', j + '.ist', '-t', j + '.alg', '-o', j + '.acr', j + '.acn'] },
      ];
      for (const ij of indexJobs) {
        if (!(await exists(jobPath(ij.input)))) continue;
        if (ij.needs && !(await exists(jobPath(ij.needs)))) continue;
        const h = sha1(await fsp.readFile(jobPath(ij.input)));
        if (idxState[ij.input] === h) continue;
        const r = await run(state, tex.tool('makeindex'), ij.args(job), build);
        runs.push({ tool: 'makeindex', ms: r.ms, code: r.code });
        idxState[ij.input] = h;
        extra = true;
      }

      const newAuxHash = await hashFiles(build, (r) => AUX_EXTS.test(r));
      const auxChanged = newAuxHash !== auxHash;
      auxHash = newAuxHash;
      const rerunMsg = /(Rerun to get|Please rerun LaTeX|Label\(s\) may have changed|Rerun LaTeX|Table widths have changed|rerunfilecheck Warning: File .* has changed|Temporary extract file .* changed|Rerun to get outlines right)/i.test(log);
      if (!(extra || auxChanged || rerunMsg) || engineRuns >= MAX_RUNS) break;
      await runEngine();
    }

    await fsp.writeFile(stateFile, JSON.stringify({ engine, bib: bibState, idx: idxState }));

    // --- Results
    const parsed = parseTexLog(log, build);
    let bibParsed = { errors: [], warnings: [] };
    if (bibLog) bibParsed = bibTool === 'biber' ? parseBiberLog(bibLog, build) : parseBibtexLog(bibLog, build);
    const errors = [...parsed.errors, ...bibParsed.errors];
    const warnings = [...parsed.warnings, ...bibParsed.warnings];
    await addMissingFileHints(src, errors);

    const pdfPath = jobPath('.pdf');
    let pdf = false;
    try {
      const st = await fsp.stat(pdfPath);
      pdf = st.mtimeMs >= started - 1000 && st.size > 0;
    } catch {
      /* no pdf */
    }
    const out = P.outputDir(id);
    await fsp.mkdir(out, { recursive: true });
    const buildId = Date.now().toString(36);
    if (pdf) {
      await fsp.copyFile(pdfPath, path.join(out, 'output.pdf'));
    }
    await fsp.writeFile(path.join(out, 'output.log'), log || '');
    await fsp.writeFile(
      path.join(out, 'build.json'),
      JSON.stringify({ buildId, job, mainFile, engine, pdf, at: new Date().toISOString() })
    );

    let status = 'success';
    if (state.cancelled) status = 'cancelled';
    else if (state.timedOut) status = 'timeout';
    else if (!pdf) status = 'failure';
    else if (errors.length) status = 'error';

    if (!pdf && !errors.length && !state.cancelled) {
      const tail = (first.output || '').split(/\r?\n/).filter(Boolean).slice(-8).join('\n');
      errors.push({ level: 'error', message: 'No PDF was produced.', content: tail });
    }

    return {
      status,
      pdf,
      buildId,
      engine,
      mainFile,
      job,
      duration: Date.now() - started,
      runs,
      errors,
      warnings,
      typesetting: parsed.typesetting,
      log,
      bibLog,
      bibTool,
    };
  } finally {
    running.delete(id);
  }
}

/**
 * "File `x.png' not found" is a common, confusing error (the PDF shows an empty box).
 * Look for the file elsewhere in the project and tell the user exactly how to fix it.
 */
async function addMissingFileHints(src, errors) {
  const missing = errors.filter((e) => /File [`']([^']+)' not found/.test(e.message));
  if (!missing.length) return;
  const all = (await walk(src)).filter((f) => !f.isDir).map((f) => f.rel);
  const base = (p) => p.split('/').pop().toLowerCase();
  const stem = (p) => base(p).replace(/\.[^.]+$/, '');
  for (const e of missing) {
    const wanted = /File [`']([^']+)' not found/.exec(e.message)[1];
    const hasExt = /\.[^./]+$/.test(wanted);
    const hits = all.filter((r) => (hasExt ? base(r) === base(wanted) : stem(r) === stem(wanted)));
    if (hits.length) {
      const dir = hits[0].includes('/') ? hits[0].slice(0, hits[0].lastIndexOf('/') + 1) : '';
      e.hint =
        `This file exists in the project as "${hits.join('", "')}", but LaTeX searched a different folder. ` +
        (dir
          ? `Add the folder to \\graphicspath, e.g. \\graphicspath{{./${dir}}}, or write the full path ${hits[0]} in the command.`
          : 'Check the folder in the command or in \\graphicspath.');
    } else {
      const similar = all.filter((r) => stem(r).replace(/[\s_-]+/g, '') === stem(wanted).replace(/[\s_-]+/g, ''));
      e.hint = similar.length
        ? `No file with exactly this name exists, but "${similar[0]}" looks similar (check spaces, underscores and capital letters).`
        : `No file named "${wanted.split('/').pop()}" exists in this project. Upload it (drag it onto the file tree) or check the spelling.`;
    }
  }
}

function stop(id) {
  const s = running.get(id);
  if (!s) return false;
  s.cancelled = true;
  killTree(s.proc);
  return true;
}

async function clean(id) {
  await fsp.rm(P.buildDir(id), { recursive: true, force: true });
}

module.exports = { compile, stop, clean, isRunning: (id) => running.has(id) };
