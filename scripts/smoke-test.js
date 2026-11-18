'use strict';
// Creates a project from every template, compiles it, and reports the result.
// Usage: node scripts/smoke-test.js [--keep]   (server must be running)
const BASE = `http://localhost:${process.env.FOLIO_PORT || 4330}`;
const H = { 'X-Folio': '1', 'Content-Type': 'application/json' };

async function api(method, url, body) {
  const r = await fetch(BASE + url, { method, headers: H, body: body ? JSON.stringify(body) : undefined });
  const data = await r.json();
  if (!r.ok) throw new Error(`${method} ${url}: ${data.error}`);
  return data;
}

(async () => {
  const keep = process.argv.includes('--keep');
  const only = process.argv.find((a) => a.startsWith('--only='));
  let templates = await api('GET', '/api/templates');
  if (only) templates = templates.filter((t) => only.slice(7).split(',').includes(t.id));
  let failed = 0;
  for (const t of templates) {
    const p = await api('POST', '/api/projects', { name: `[smoke] ${t.name}`, template: t.id });
    const r = await api('POST', `/api/projects/${p.id}/compile`, {});
    const runs = r.runs.map((x) => x.tool).join(' > ');
    console.log(`${r.status.padEnd(8)} ${t.id.padEnd(9)} ${(r.duration / 1000).toFixed(1)}s  [${runs}]  errors=${r.errors.length} warnings=${r.warnings.length}`);
    for (const e of r.errors.slice(0, 5)) console.log(`    ERR  ${e.file}:${e.line}  ${e.message}`);
    for (const w of r.warnings.slice(0, 5)) console.log(`    WARN ${w.file}:${w.line}  ${w.message}`);
    if (r.status !== 'success') failed++;
    if (!keep) await api('DELETE', `/api/projects/${p.id}`);
  }
  console.log(failed ? `${failed} template(s) failed` : 'All templates compiled.');
  process.exit(failed ? 1 : 0);
})().catch((e) => {
  console.error(e.message);
  process.exit(2);
});
