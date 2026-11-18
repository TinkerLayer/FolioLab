'use strict';
const fs = require('fs');
const fsp = fs.promises;
const path = require('path');
const crypto = require('crypto');

const ROOT = path.resolve(__dirname, '..');

class HttpError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

async function exists(p) {
  try {
    await fsp.access(p);
    return true;
  } catch {
    return false;
  }
}

async function readText(p) {
  try {
    return await fsp.readFile(p, 'utf8');
  } catch {
    return null;
  }
}

/** Recursively list files under dir. Returns [{rel, abs, isDir, size, mtimeMs}] with '/' separators. */
async function walk(dir, rel = '', out = []) {
  let entries;
  try {
    entries = await fsp.readdir(dir, { withFileTypes: true });
  } catch {
    return out;
  }
  for (const e of entries) {
    const abs = path.join(dir, e.name);
    const r = rel ? rel + '/' + e.name : e.name;
    if (e.isDirectory()) {
      out.push({ rel: r, abs, isDir: true, size: 0, mtimeMs: 0 });
      await walk(abs, r, out);
    } else if (e.isFile()) {
      const st = await fsp.stat(abs);
      out.push({ rel: r, abs, isDir: false, size: st.size, mtimeMs: st.mtimeMs });
    }
  }
  return out;
}

async function copyDir(src, dest) {
  await fsp.mkdir(dest, { recursive: true });
  for (const e of await fsp.readdir(src, { withFileTypes: true })) {
    const s = path.join(src, e.name);
    const d = path.join(dest, e.name);
    if (e.isDirectory()) await copyDir(s, d);
    else if (e.isFile()) await fsp.copyFile(s, d);
  }
}

function sha1(data) {
  return crypto.createHash('sha1').update(data).digest('hex');
}

/**
 * Normalise a user-supplied relative path and make sure it stays inside base.
 * Returns { rel, abs }.
 */
function safeJoin(base, rel) {
  if (typeof rel !== 'string' || !rel.trim()) throw new HttpError(400, 'Missing path');
  let r = rel.replace(/\\/g, '/').replace(/^\/+/, '').replace(/\/+$/, '');
  const parts = r.split('/').filter((p) => p && p !== '.');
  if (!parts.length) throw new HttpError(400, 'Invalid path');
  for (const p of parts) {
    if (p === '..') throw new HttpError(400, 'Invalid path');
    if (/[<>:"|?*\x00-\x1f]/.test(p)) throw new HttpError(400, `Invalid character in "${p}"`);
  }
  r = parts.join('/');
  const abs = path.resolve(base, ...parts);
  const baseResolved = path.resolve(base);
  if (abs !== baseResolved && !abs.startsWith(baseResolved + path.sep)) {
    throw new HttpError(400, 'Path escapes project');
  }
  return { rel: r, abs };
}

module.exports = { ROOT, HttpError, exists, readText, walk, copyDir, sha1, safeJoin };
