'use strict';
// SyncTeX: jump from source line to PDF position (forward) and from PDF click to source line (inverse).
const { execFile } = require('child_process');
const path = require('path');
const { tool, texEnv } = require('./tex');

function runSynctex(args, cwd) {
  return new Promise((resolve) => {
    const exe = tool('synctex');
    if (!exe) return resolve('');
    execFile(exe, args, { cwd, env: texEnv(), windowsHide: true, timeout: 15000 }, (err, stdout) => {
      resolve(stdout || '');
    });
  });
}

function parseRecords(out) {
  const records = [];
  let cur = null;
  for (const line of out.split(/\r?\n/)) {
    const m = /^(\w+):(.*)$/.exec(line);
    if (!m) continue;
    const [, k, v] = m;
    if (k === 'Output' || (k === 'Page' && cur && cur.Page !== undefined) || (k === 'Input' && cur && cur.Input !== undefined)) {
      if (cur) records.push(cur);
      cur = {};
    }
    if (!cur) cur = {};
    cur[k] = v;
  }
  if (cur) records.push(cur);
  return records;
}

/** Returns [{ page, h, v, width, height }] in PDF points, top-left origin. */
async function forward(buildDir, pdfName, file, line, column = 0) {
  const input = path.join(buildDir, file);
  const out = await runSynctex(['view', '-i', `${line}:${column}:${input}`, '-o', path.join(buildDir, pdfName)], buildDir);
  return parseRecords(out)
    .filter((r) => r.Page)
    .map((r) => ({
      page: +r.Page,
      h: +r.h,
      v: +r.v,
      width: +r.W,
      height: +r.H,
      x: +r.x,
      y: +r.y,
    }));
}

/** Returns { file, line } relative to the project, or null. */
async function inverse(buildDir, pdfName, page, x, y) {
  const out = await runSynctex(['edit', '-o', `${page}:${x}:${y}:${path.join(buildDir, pdfName)}`], buildDir);
  const rec = parseRecords(out).find((r) => r.Input);
  if (!rec) return null;
  let f = path.normalize(rec.Input.trim());
  const bd = path.normalize(buildDir);
  if (f.toLowerCase().startsWith(bd.toLowerCase())) f = f.slice(bd.length);
  f = f.replace(/\\/g, '/').replace(/^\/+/, '').replace(/^(\.\/)+/, '');
  return { file: f, line: Math.max(1, +rec.Line || 1) };
}

module.exports = { forward, inverse };
