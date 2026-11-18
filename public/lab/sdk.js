/* Folio Lab SDK for analysis-module pages.
 *
 * A module page served by the hub under /m/<id>/ loads this with <script src="/lab/sdk.js">. It gives:
 *
 *   Lab.sendToReport({
 *     module: "zugversuch",                       // module id
 *     title: "Tensile test sample A",             // default result title
 *     scopes:  [{id, label}],                     // optional: what to send (e.g. this sample / all samples)
 *     include: [{id, label}],                     // optional: content switches passed to build()
 *     build: async ({scope, lang, include, title}) => bundle   // returns a folio-lab-bundle/1 object
 *   })
 *
 * The dialog picks (or creates) a report project, calls build() and stores the bundle in that project.
 * Without the hub (module started on its own) this script is simply absent, so check `window.Lab`.
 * Also adds a small "Folio Lab" button to get back to the home page. See docs/MODULES.md.
 */
(function () {
  'use strict';
  if (window.Lab) return;

  const LS_LANG = 'folio-lab-lang';
  const LS_PROJECT = 'folio-lab-last-project';
  const store = {
    get(k, d) {
      try {
        const v = localStorage.getItem(k);
        return v === null ? d : v;
      } catch {
        return d;
      }
    },
    set(k, v) {
      try {
        localStorage.setItem(k, v);
      } catch {
        /* private mode */
      }
    },
  };

  async function hub(method, url, body) {
    const opt = { method, headers: { 'X-Folio': '1' } };
    if (body !== undefined) {
      opt.headers['Content-Type'] = 'application/json';
      opt.body = JSON.stringify(body);
    }
    const r = await fetch(url, opt);
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw Object.assign(new Error(j.error || `HTTP ${r.status}`), { status: r.status, data: j });
    return j;
  }

  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

  const CSS = `
  :host { all: initial; }
  * { box-sizing: border-box; font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
  [hidden] { display: none !important; }
  .back { position: fixed; left: 12px; bottom: 12px; z-index: 2147483000; display: flex; align-items: center; gap: 6px;
    padding: 6px 12px 6px 10px; border-radius: 999px; background: #1f2937; color: #fff; font-size: 12.5px; font-weight: 600;
    text-decoration: none; box-shadow: 0 4px 14px rgba(0,0,0,.25); opacity: .82; transition: opacity .15s; }
  .back:hover { opacity: 1; }
  .back svg { width: 14px; height: 14px; }
  .ov { position: fixed; inset: 0; z-index: 2147483001; background: rgba(15,23,42,.45); display: flex; align-items: center; justify-content: center; padding: 16px; }
  .dlg { --bg: #fff; --fg: #111827; --mut: #6b7280; --bd: #e5e7eb; --acc: #2563eb; --soft: #f3f4f6;
    width: min(560px, 100%); max-height: calc(100vh - 32px); overflow: auto; background: var(--bg); color: var(--fg);
    border-radius: 12px; box-shadow: 0 20px 60px rgba(0,0,0,.3); font-size: 14px; }
  @media (prefers-color-scheme: dark) { .dlg { --bg: #1f2430; --fg: #e5e7eb; --mut: #9ca3af; --bd: #374151; --acc: #60a5fa; --soft: #2a3040; } }
  .hd { padding: 16px 20px 6px; font-size: 16px; font-weight: 650; }
  .sub { padding: 0 20px 10px; color: var(--mut); font-size: 12.5px; }
  .bd { padding: 6px 20px 12px; display: grid; gap: 12px; }
  label.f { display: grid; gap: 4px; font-size: 12.5px; color: var(--mut); font-weight: 600; }
  input[type=text], select { width: 100%; padding: 7px 9px; border: 1px solid var(--bd); border-radius: 7px; background: var(--bg); color: var(--fg); font-size: 14px; }
  fieldset { border: 1px solid var(--bd); border-radius: 8px; padding: 8px 10px 10px; margin: 0; }
  legend { font-size: 12.5px; color: var(--mut); font-weight: 600; padding: 0 4px; }
  .opts { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 12px; }
  .opts.one { grid-template-columns: 1fr; }
  .opts label { display: flex; gap: 7px; align-items: flex-start; font-size: 13px; line-height: 1.3; cursor: pointer; }
  .opts input { margin: 2px 0 0; }
  .row { display: flex; gap: 10px; }
  .row > * { flex: 1; }
  .ft { display: flex; gap: 8px; justify-content: flex-end; padding: 12px 20px 16px; border-top: 1px solid var(--bd); }
  button { padding: 7px 14px; border-radius: 7px; border: 1px solid var(--bd); background: var(--soft); color: var(--fg); font-size: 13.5px; font-weight: 600; cursor: pointer; }
  button.pri { background: var(--acc); border-color: var(--acc); color: #fff; }
  button:disabled { opacity: .55; cursor: default; }
  .msg { font-size: 13px; padding: 8px 10px; border-radius: 7px; background: var(--soft); }
  .msg.err { background: #fde8e8; color: #9b1c1c; }
  @media (prefers-color-scheme: dark) { .msg.err { background: #4c1d1d; color: #fecaca; } }
  .ok ul { margin: 6px 0 0; padding-left: 18px; }
  .spin { display: inline-block; width: 12px; height: 12px; border: 2px solid currentColor; border-right-color: transparent; border-radius: 50%; animation: s .7s linear infinite; vertical-align: -2px; margin-right: 6px; }
  @keyframes s { to { transform: rotate(360deg); } }
  @media (max-width: 520px) { .opts { grid-template-columns: 1fr; } .row { flex-direction: column; } }
  `;

  let root;
  function shadow() {
    if (root) return root;
    const host = document.createElement('div');
    host.id = 'folio-lab-sdk';
    document.body.appendChild(host);
    root = host.attachShadow({ mode: 'open' });
    const st = document.createElement('style');
    st.textContent = CSS;
    root.appendChild(st);
    return root;
  }

  function backButton() {
    if (!location.pathname.startsWith('/m/')) return;
    const a = document.createElement('a');
    a.className = 'back';
    a.href = '/';
    a.title = 'Back to Folio Lab (analyses and reports)';
    a.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg>Folio Lab';
    shadow().appendChild(a);
  }

  function countKinds(items) {
    const n = {};
    for (const it of items || []) n[it.kind] = (n[it.kind] || 0) + (it.kind === 'values' ? (it.values || []).length : 1);
    const names = { figure: ['figure', 'figures'], table: ['table', 'tables'], values: ['value', 'values'], data: ['data set', 'data sets'], citation: ['reference', 'references'], text: ['text block', 'text blocks'] };
    return Object.entries(n).map(([k, c]) => `${c} ${(names[k] || [k, k])[c === 1 ? 0 : 1]}`);
  }

  async function sendToReport(opts) {
    opts = opts || {};
    if (typeof opts.build !== 'function') throw new Error('Lab.sendToReport needs a build() function');
    const sr = shadow();
    const ov = document.createElement('div');
    ov.className = 'ov';
    const scopes = opts.scopes || [];
    const include = opts.include || [];
    const lang = store.get(LS_LANG, 'de');
    ov.innerHTML = `
      <div class="dlg" role="dialog" aria-modal="true" aria-label="Send to report">
        <div class="hd">Send to report</div>
        <div class="sub">Figures, tables, values, data and references go into the report project under <code>lab/</code>. Insert them there with the <b>Lab</b> button.</div>
        <div class="bd">
          <label class="f">Result title<input type="text" name="title" value="${esc(opts.title || '')}"></label>
          ${scopes.length > 1 ? `<fieldset><legend>What to send</legend><div class="opts one">${scopes.map((s, i) => `<label><input type="radio" name="scope" value="${esc(s.id)}" ${i === 0 ? 'checked' : ''}>${esc(s.label)}</label>`).join('')}</div></fieldset>` : ''}
          <div class="row">
            <label class="f">Report<select name="project"><option value="">Loading…</option></select></label>
            <label class="f">Language of captions and text<select name="lang"><option value="de" ${lang === 'de' ? 'selected' : ''}>Deutsch</option><option value="en" ${lang === 'en' ? 'selected' : ''}>English</option></select></label>
          </div>
          <label class="f" data-newname hidden>Name of the new report<input type="text" name="newname" value="${esc(opts.title || 'Lab report')}"></label>
          ${include.length ? `<fieldset><legend>Content</legend><div class="opts">${include.map((c) => `<label><input type="checkbox" name="inc" value="${esc(c.id)}" checked>${esc(c.label)}</label>`).join('')}</div></fieldset>` : ''}
          <div class="msg" data-msg hidden></div>
        </div>
        <div class="ft"><button data-cancel>Cancel</button><button class="pri" data-go disabled>Send</button></div>
      </div>`;
    sr.appendChild(ov);
    const $ = (s) => ov.querySelector(s);
    const close = () => ov.remove();
    $('[data-cancel]').onclick = close;
    ov.addEventListener('mousedown', (e) => e.target === ov && close());
    ov.addEventListener('keydown', (e) => e.key === 'Escape' && close());
    const msg = (html, err) => {
      const m = $('[data-msg]');
      m.hidden = !html;
      m.className = 'msg' + (err ? ' err' : '');
      m.innerHTML = html || '';
    };

    // projects
    const sel = $('select[name=project]');
    try {
      const projects = await hub('GET', '/api/projects');
      const last = store.get(LS_PROJECT, '');
      sel.innerHTML =
        `<option value="__new__:lab-report">+ New report (Deutsch)</option><option value="__new__:lab-report-en">+ New report (English)</option>` +
        (projects.length ? `<optgroup label="Existing reports">${projects.map((p) => `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('')}</optgroup>` : '');
      sel.value = projects.some((p) => p.id === last) ? last : projects.length ? projects[0].id : '__new__:lab-report';
    } catch (e) {
      msg(`Could not load reports: ${esc(e.message)}`, true);
    }
    const syncNew = () => {
      $('[data-newname]').hidden = !sel.value.startsWith('__new__');
      if (sel.value.startsWith('__new__')) $('select[name=lang]').value = sel.value.endsWith('-en') ? 'en' : 'de';
    };
    sel.onchange = syncNew;
    syncNew();
    $('[data-go]').disabled = false;
    $('input[name=title]').focus();

    async function store_(projectId, bundle, mode) {
      try {
        return await hub('POST', `/api/projects/${projectId}/lab${mode ? `?mode=${mode}` : ''}`, bundle);
      } catch (e) {
        if (e.status !== 409) throw e;
        return new Promise((resolve, reject) => {
          msg(`A result named <b>${esc(bundle.slug)}</b> already exists in this report.
               <div style="margin-top:8px;display:flex;gap:8px"><button data-r>Replace it</button><button data-n>Keep both</button></div>`);
          $('[data-r]').onclick = () => store_(projectId, bundle, 'replace').then(resolve, reject);
          $('[data-n]').onclick = () => store_(projectId, bundle, 'new').then(resolve, reject);
        });
      }
    }

    $('[data-go]').onclick = async () => {
      const go = $('[data-go]');
      go.disabled = true;
      const title = $('input[name=title]').value.trim() || opts.title || 'Result';
      const scopeEl = ov.querySelector('input[name=scope]:checked');
      const inc = {};
      ov.querySelectorAll('input[name=inc]').forEach((c) => (inc[c.value] = c.checked));
      const lng = $('select[name=lang]').value;
      store.set(LS_LANG, lng);
      try {
        msg('<span class="spin"></span>Preparing figures, tables and values…');
        const bundle = await opts.build({ scope: scopeEl ? scopeEl.value : scopes[0] && scopes[0].id, lang: lng, include: inc, title });
        if (!bundle || bundle.error) throw new Error((bundle && bundle.error) || 'The module returned nothing');
        let pid = sel.value;
        if (pid.startsWith('__new__')) {
          msg('<span class="spin"></span>Creating the report…');
          const p = await hub('POST', '/api/projects', { name: $('input[name=newname]').value.trim() || title, template: pid.split(':')[1] });
          pid = p.id;
        }
        msg('<span class="spin"></span>Storing in the report…');
        const man = await store_(pid, bundle);
        store.set(LS_PROJECT, pid);
        const href = `/project/${pid}?lab=${encodeURIComponent(man.slug)}`;
        msg(`<div class="ok"><b>Stored as “${esc(man.title)}”</b> in <code>lab/${esc(man.slug)}/</code>:<ul>${countKinds(man.items).map((s) => `<li>${esc(s)}</li>`).join('')}</ul></div>`);
        const ft = ov.querySelector('.ft');
        ft.innerHTML = `<button data-cancel>Close</button><button class="pri" data-open>Open report</button>`;
        ft.querySelector('[data-cancel]').onclick = close;
        ft.querySelector('[data-open]').onclick = () => {
          window.open(href, `folio-project-${pid}`);
          close();
        };
        if (typeof opts.onSent === 'function') opts.onSent({ project: pid, manifest: man, href });
      } catch (e) {
        msg(esc(e.message || String(e)), true);
        go.disabled = false;
      }
    };
  }

  window.Lab = { version: 1, sendToReport, hub };
  if (document.body) backButton();
  else document.addEventListener('DOMContentLoaded', backButton);
})();
