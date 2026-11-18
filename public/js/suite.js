// A2: project selector on the hub page. Modules keep their environments per project and pick up a change when
// their tab gets focus again. Existing reports appear as projects of their own and are never changed.
const sel = document.getElementById('suite-project');
const btn = document.getElementById('suite-new');

async function call(method, url, body) {
  const r = await fetch(url, {
    method,
    // UI-09: the hub refuses POST without X-Folio (CSRF guard); the selector never sent it, so switching failed with 403
    headers: body ? { 'Content-Type': 'application/json', 'X-Folio': '1' } : { 'X-Folio': '1' },
    body: body ? JSON.stringify(body) : undefined,
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}

async function load() {
  try {
    const s = await call('GET', '/api/suite');
    sel.innerHTML = '';
    for (const p of s.projects) {
      const o = document.createElement('option');
      o.value = p.id;
      const n = p.reports.length;
      o.textContent = p.name + (p.legacy ? ' (report)' : n ? ` (${n} report${n === 1 ? '' : 's'})` : '');
      o.selected = p.id === s.active;
      sel.appendChild(o);
    }
    window.dispatchEvent(new Event('suite-changed')); // UI-09: module cards show the project's open environments
  } catch (e) {
    sel.parentElement.hidden = true;
    btn.hidden = true;
  }
}

sel.addEventListener('change', async () => {
  try {
    await call('POST', '/api/suite/active', { id: sel.value });
  } catch (e) {
    alert(e.message);
  }
  load();
});
btn.addEventListener('click', async () => {
  const name = prompt('Name of the new project:');
  if (!name || !name.trim()) return;
  try {
    const p = await call('POST', '/api/suite/projects', { name: name.trim() });
    await call('POST', '/api/suite/active', { id: p.id });
  } catch (e) {
    alert(e.message);
  }
  load();
});
load();
