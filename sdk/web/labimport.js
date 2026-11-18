/* Import-Fenster (I-02): Datensätze (`data.table`) des Projekts finden, ansehen und in ein Werkzeug übernehmen –
 * so leicht wie das Teilen. Jedes Modul darf jeden Datensatz lesen (I-01); die an das Modul gerichteten stehen oben
 * („Für dieses Modul“). Links die Liste mit Suche, rechts die Vorschau (Bild, Spalten mit Wertebereich, Versionen,
 * erste Zeilen); unten das Ziel (Umgebung, nur auf der Übersicht) und die Übernahme.
 * Server: /api/env/datasets (Liste) und /api/env/dataset (Vorschau) aus labproject.ModuleEnvs.
 *
 *   const pick = await LabImport.open({
 *     api, module: "tga",
 *     select: "s-1234abcd",                                         // optional: vorgewählt
 *     actions: [{ id: "run", label: "Als Lauf öffnen", hint: "…" }], // optional: Ziele im Werkzeug (erstes = Hauptknopf)
 *     check: (d) => "",                                             // optional: Grund, warum der Datensatz nicht passt
 *     targets: { envs: [{ id, name }], active: "standard", word: "Umgebung" },  // optional (Übersicht): Ziel-Umgebung
 *   });
 *   // → null (abgebrochen) oder {id, title, version, latest, mode: "live"|"pin", rows, columns, producer, action, env}
 *   //   env: null | {id} | {create: "Name"}
 *
 * Braucht labui.js (Sprache); ohne bleibt es deutsch.
 */
(function (g) {
  "use strict";
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const MOD = { tga: "TGA", ftir: "FTIR", rechner: "Rechner", zugversuch: "Zugversuch", mikroskopie: "Mikroskopie", elementrechner: "Elementrechner", datenaufbereitung: "Datenaufbereitung" };
  const COL = ["#2563eb", "#dc2626", "#059669"];
  const CSS = `
dialog.limp{width:min(980px,96vw);max-width:96vw;height:min(680px,90vh);padding:0;border:1px solid var(--line,#d8dce4);border-radius:12px;
  background:var(--panel,#fff);color:var(--ink,#1d2027);box-shadow:0 18px 50px rgba(0,0,0,.28);overflow:hidden}
dialog.limp[open]{display:flex;flex-direction:column}
dialog.limp::backdrop{background:rgba(15,18,25,.38)}
.limp-head{display:flex;align-items:center;gap:10px;padding:10px 14px;border-bottom:1px solid var(--line,#d8dce4);flex-wrap:wrap}
.limp-head b{font-size:15px}
.limp-head input{flex:1;min-width:160px;padding:5px 8px;border:1px solid var(--line,#d8dce4);border-radius:6px;font:inherit;background:transparent;color:inherit}
.limp-x{border:0;background:none;font-size:16px;cursor:pointer;color:inherit;padding:2px 6px;border-radius:6px}
.limp-x:hover{background:var(--hover,rgba(0,0,0,.06))}
.limp-main{flex:1;display:grid;grid-template-columns:minmax(220px,2fr) 3fr;min-height:0}
.limp-list{overflow:auto;border-right:1px solid var(--line,#d8dce4);padding:6px 6px 10px}
.limp-g{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--muted,#5d6472);margin:8px 6px 4px}
.limp-it{display:block;width:100%;text-align:left;border:1px solid transparent;border-radius:8px;background:none;padding:6px 8px;cursor:pointer;font:inherit;color:inherit}
.limp-it:hover{background:var(--hover,rgba(0,0,0,.04))}
.limp-it.on{border-color:var(--accent,#6d28d9);background:var(--sel,rgba(109,40,217,.07))}
.limp-it .t{font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.limp-it .s,.limp-it .c{font-size:11.5px;color:var(--muted,#5d6472);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.limp-it .w{font-size:11px;color:#b45309}
.limp-pv{overflow:auto;padding:10px 14px 14px;min-width:0}
.limp-pv h3{margin:0 0 2px;font-size:15px;overflow-wrap:anywhere}
.limp-pv .sub{font-size:12px;color:var(--muted,#5d6472)}
.limp-chips{display:flex;flex-wrap:wrap;gap:4px;margin:6px 0}
.limp-chips span{font-size:11px;padding:0 7px;border-radius:9px;border:1px solid var(--line,#d8dce4);white-space:nowrap}
.limp-thumb{margin:6px 0;border:1px solid var(--line,#d8dce4);border-radius:8px;padding:4px 6px}
.limp-thumb svg{display:block;width:100%;height:auto}
.limp-thumb .lg{display:flex;gap:10px;flex-wrap:wrap;font-size:11px}
.limp-thumb .lg i{display:inline-block;width:10px;height:3px;margin-right:4px;vertical-align:middle}
.limp-pv table{border-collapse:collapse;width:100%;font-size:12px;margin-top:4px}
.limp-pv th{text-align:left;font-weight:600;color:var(--muted,#5d6472);font-size:11px;padding:2px 8px 2px 0;border-bottom:1px solid var(--line,#d8dce4)}
.limp-pv td{padding:2px 8px 2px 0;vertical-align:top;overflow-wrap:anywhere}
.limp-pv td.n{font-family:ui-monospace,Consolas,monospace;white-space:nowrap}
.limp-pv details{margin-top:8px}
.limp-pv details>summary{cursor:pointer;font-size:12px;font-weight:600}
.limp-first{overflow:auto;max-width:100%}
.limp-ver{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:8px 0 4px;font-size:12.5px}
.limp-ver label{display:flex;align-items:center;gap:6px;min-width:0;max-width:100%}
.limp-ver select{min-width:0;max-width:100%;flex:1 1 auto}
.limp-warn{margin-top:8px;padding:6px 8px;border-radius:6px;background:#fff3d6;color:#7a5200;font-size:12px}
.limp-empty{padding:18px;font-size:13px;color:var(--muted,#5d6472);line-height:1.5}
.limp-foot{display:flex;align-items:center;gap:8px;padding:10px 14px;border-top:1px solid var(--line,#d8dce4);flex-wrap:wrap}
.limp-foot .grow{flex:1}
.limp-foot .to{display:flex;gap:6px;align-items:center;font-size:12.5px;flex-wrap:wrap}
.limp-foot .to input{width:14ch;padding:3px 6px;border:1px solid var(--line,#d8dce4);border-radius:6px;font:inherit;background:transparent;color:inherit}
.limp-foot .hint{font-size:11.5px;color:var(--muted,#5d6472);width:100%}
@media (max-width:700px){.limp-main{grid-template-columns:1fr;grid-template-rows:minmax(120px,38%) 1fr}
  .limp-list{border-right:0;border-bottom:1px solid var(--line,#d8dce4)}}
@media (prefers-color-scheme:dark){.limp-warn{background:#43360f;color:#f3d27a}.limp-it .w{color:#f3d27a}}`;

  const T = {
    de: { "imp.title": "Datensatz importieren", "imp.search": "Suchen: Titel, Spalte, Umgebung …", "imp.close": "Schliessen",
          "imp.g_me": "Für dieses Modul", "imp.g_all": "Weitere Datensätze im Projekt", "imp.none_q": "Nichts gefunden.",
          "imp.none": "Im Projekt gibt es noch keine Datensätze. Sie entstehen in der Datenaufbereitung: Tabelle öffnen, aufbereiten, „Als Datensatz speichern“.",
          "imp.load": "Lädt …", "imp.from": "Aus {m}", "imp.rows": "{n} Zeilen", "imp.cols": "{n} Spalten", "imp.excl": "{n} ausgeschlossen",
          "imp.derived": "abgeleitet", "imp.ver": "Version", "imp.live": "immer die neueste (v{v}, live)", "imp.pin": "v{v} festhalten",
          "imp.live_t": "Live: das Werkzeug folgt neuen Versionen. Festgehalten: es bleibt bei dieser Version, bis Sie wechseln.",
          "imp.c_name": "Spalte", "imp.c_unit": "Einheit", "imp.c_range": "Bereich", "imp.text": "Text", "imp.first": "Erste Zeilen",
          "imp.to": "Nach", "imp.new": "+ Neue {w} …", "imp.new_name": "Name", "imp.cancel": "Abbrechen", "imp.ok": "Importieren",
          "imp.nofit": "Passt nicht: {e}", "imp.err": "Vorschau nicht verfügbar: {e}" },
    en: { "imp.title": "Import a dataset", "imp.search": "Search: title, column, environment …", "imp.close": "Close",
          "imp.g_me": "For this module", "imp.g_all": "More datasets in the project", "imp.none_q": "Nothing found.",
          "imp.none": "The project has no datasets yet. They are made in Data preparation: open a table, prepare it, \"Save as dataset\".",
          "imp.load": "Loading …", "imp.from": "From {m}", "imp.rows": "{n} rows", "imp.cols": "{n} columns", "imp.excl": "{n} excluded",
          "imp.derived": "derived", "imp.ver": "Version", "imp.live": "always the latest (v{v}, live)", "imp.pin": "keep v{v}",
          "imp.live_t": "Live: the tool follows new versions. Kept: it stays with this version until you switch.",
          "imp.c_name": "Column", "imp.c_unit": "Unit", "imp.c_range": "Range", "imp.text": "text", "imp.first": "First rows",
          "imp.to": "Into", "imp.new": "+ New {w} …", "imp.new_name": "Name", "imp.cancel": "Cancel", "imp.ok": "Import",
          "imp.nofit": "Does not fit: {e}", "imp.err": "Preview not available: {e}" },
  };
  let ready = false;
  function ensure() {
    if (ready) return;
    ready = true;
    if (g.LabUI) g.LabUI.strings(T);
    if (!document.getElementById("lab-imp-css")) { const s = document.createElement("style"); s.id = "lab-imp-css"; s.textContent = CSS; document.head.appendChild(s); }
  }
  const lang = () => (g.LabUI && g.LabUI.lang() === "en" ? "en" : "de");
  function t(k, v) {
    if (g.LabUI) return g.LabUI.t(k, v);
    let s = T.de[k] || k;
    if (v) s = s.replace(/\{(\w+)\}/g, (m, x) => (v[x] !== undefined ? v[x] : m));
    return s;
  }
  function num(x) {
    if (x === null || x === undefined || x === "") return "";
    if (typeof x !== "number") return String(x);
    const a = Math.abs(x);
    let s = a !== 0 && (a >= 1e6 || a < 1e-3) ? x.toExponential(3).replace(/\.?0+e/, "e") : String(+x.toPrecision(5));
    return lang() === "de" ? s.replace(".", ",") : s;
  }
  const modName = (p) => (p && (MOD[p.module] || p.module)) || "?";
  const day = (iso) => { if (!iso) return ""; const d = new Date(iso); return isNaN(d) ? "" : d.toLocaleDateString(lang() === "en" ? "en-GB" : "de-CH"); };

  // kleines Bild (Serien des Servers, schon ausgedünnt)
  function thumbSvg(th) {
    if (!th || !th.series || !th.series.length) return "";
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (const s of th.series) s.x.forEach((x, i) => { const y = s.y[i]; if (x == null || y == null) return; x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y); });
    if (!isFinite(x0) || !isFinite(y0)) return "";
    if (x1 === x0) { x0 -= 1; x1 += 1; }
    if (y1 === y0) { y0 -= 1; y1 += 1; }
    const W = 360, H = 130, L = 4, R = 4, Tp = 6, B = 6;
    const X = (x) => L + (x - x0) / (x1 - x0) * (W - L - R), Y = (y) => H - B - (y - y0) / (y1 - y0) * (H - Tp - B);
    const paths = th.series.map((s, k) => {
      const pts = [];
      s.x.forEach((x, i) => { const y = s.y[i]; if (x != null && y != null) pts.push(`${X(x).toFixed(1)},${Y(y).toFixed(1)}`); });
      const many = pts.length > 60;
      return many ? `<polyline fill="none" stroke="${COL[k % 3]}" stroke-width="1.4" points="${pts.join(" ")}"/>`
        : pts.map((p) => { const [a, b] = p.split(","); return `<circle cx="${a}" cy="${b}" r="2" fill="${COL[k % 3]}"/>`; }).join("");
    }).join("");
    const lg = th.series.length > 1 ? `<div class="lg">${th.series.map((s, k) => `<span><i style="background:${COL[k % 3]}"></i>${esc(s.name)}</span>`).join("")}</div>` : "";
    return `<div class="limp-thumb"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(th.ylab)} / ${esc(th.xlab)}">
      <rect x="0" y="0" width="${W}" height="${H}" fill="none"/>${paths}</svg>
      <div class="sub">${esc(th.ylab)} · ${esc(th.xlab)} (${num(x0)} … ${num(x1)})</div>${lg}</div>`;
  }

  async function open(o) {
    ensure();
    const api = o.api;
    const j = await api("api/env/datasets", {});
    if (j && j.error) { if (o.toast) o.toast(j.error, true); return null; }
    const list = (j && j.datasets) || [];
    const val = (x) => (typeof x === "function" ? x() : x) || "";
    const acts = (o.actions && o.actions.length ? o.actions : [{ id: "import", label: t("imp.ok") }]).map((a) => ({ id: a.id, label: val(a.label), hint: val(a.hint) }));
    const tg = o.targets && o.targets.envs ? o.targets : null;
    const st = { q: "", sel: null, ver: "live", pv: {}, to: tg ? tg.active : null, newName: "" };
    if (o.select && list.some((x) => x.id === o.select)) { st.sel = o.select; if (o.mode === "pin" && o.version) st.ver = String(o.version); }
    else if (list.length) st.sel = list[0].id;

    return new Promise((resolve) => {
      let result = null, settled = false;
      const d = document.createElement("dialog");
      // Chrome schickt "close" erst mit dem nächsten gezeichneten Bild (Tab im Hintergrund: gar nicht) – darum beim
      // Klick sofort auflösen; "close" bleibt für Esc.
      const settle = () => { if (settled) return; settled = true; if (d.open) d.close(); d.remove(); resolve(result); };
      d.className = "limp";
      d.setAttribute("aria-label", t("imp.title"));
      d.innerHTML = `<div class="limp-head"><b>${esc(o.title || t("imp.title"))}</b>
          <input type="search" data-q placeholder="${esc(t("imp.search"))}" aria-label="${esc(t("imp.search"))}"${list.length ? "" : " hidden"}>
          <button type="button" class="limp-x" data-x aria-label="${esc(t("imp.close"))}" title="${esc(t("imp.close"))}">✕</button></div>
        <div class="limp-main"><div class="limp-list" data-list role="listbox" aria-label="${esc(t("imp.title"))}"></div><div class="limp-pv" data-pv aria-live="polite"></div></div>
        <div class="limp-foot">${tg ? `<span class="to"><label>${esc(t("imp.to"))} <select data-to>${tg.envs.map((e) => `<option value="${esc(e.id)}"${e.id === tg.active ? " selected" : ""}>${esc(e.name)}</option>`).join("")}
            <option value="+new">${esc(t("imp.new", { w: tg.word || "Umgebung" }))}</option></select></label><input data-newname hidden aria-label="${esc(t("imp.new_name"))}" placeholder="${esc(t("imp.new_name"))}"></span>` : ""}
          <span class="grow"></span><button type="button" data-cancel>${esc(t("imp.cancel"))}</button>
          ${acts.map((a, i) => `<button type="button" data-act="${esc(a.id)}"${i === 0 ? ' class="primary"' : ""}${a.hint ? ` title="${esc(a.hint)}"` : ""}>${esc(a.label)}</button>`).join("")}
          ${acts.some((a) => a.hint) && acts.length > 1 ? `<span class="hint">${acts.map((a) => a.hint ? `<b>${esc(a.label)}</b>: ${esc(a.hint)}` : "").filter(Boolean).join(" · ")}</span>` : ""}</div>`;
      document.body.appendChild(d);
      const $l = d.querySelector("[data-list]"), $p = d.querySelector("[data-pv]"), $q = d.querySelector("[data-q]");
      const cur = () => list.find((x) => x.id === st.sel) || null;
      const visible = () => {
        const q = st.q.trim().toLowerCase();
        if (!q) return list;
        return list.filter((x) => [x.title, x.producer && x.producer.env_name, x.producer && x.producer.item_name, modName(x.producer),
          ...(x.columns || []).map((c) => `${c.name} ${c.unit || ""} ${c.key}`)].join(" ").toLowerCase().includes(q));
      };
      const fits = (x) => { if (!o.check) return ""; try { return o.check(x) || ""; } catch (e) { return ""; } };

      function renderList() {
        if (!list.length) { $l.innerHTML = `<div class="limp-empty">${esc(t("imp.none"))}</div>`; return; }
        const v = visible();
        if (!v.length) { $l.innerHTML = `<div class="limp-empty">${esc(t("imp.none_q"))}</div>`; return; }
        const item = (x) => {
          const bad = fits(x), p = x.producer || {};
          return `<button type="button" role="option" class="limp-it${x.id === st.sel ? " on" : ""}" data-id="${esc(x.id)}" aria-selected="${x.id === st.sel}">
            <div class="t">${esc(x.title || x.id)}</div>
            <div class="s">${esc([p.env_name, p.item_name].filter(Boolean).join(" · ") || modName(p))} · v${x.latest} · ${esc(t("imp.rows", { n: x.rows }))}</div>
            <div class="c">${esc((x.columns || []).map((c) => c.name + (c.unit ? ` [${c.unit}]` : "")).join(", "))}</div>
            ${bad ? `<div class="w">${esc(t("imp.nofit", { e: bad }))}</div>` : ""}</button>`;
        };
        const me = v.filter((x) => x.for_me), rest = v.filter((x) => !x.for_me);
        $l.innerHTML = (me.length ? `<div class="limp-g">${esc(t("imp.g_me"))}</div>${me.map(item).join("")}` : "")
          + (rest.length ? `<div class="limp-g">${esc(t("imp.g_all"))}</div>${rest.map(item).join("")}` : "");
      }
      async function preview() {
        const x = cur();
        if (!x) { $p.innerHTML = ""; updateFoot(); return; }
        const key = x.id + "@" + (st.ver === "live" ? "" : st.ver);
        if (!st.pv[key]) {
          $p.innerHTML = `<div class="limp-empty">${esc(t("imp.load"))}</div>`;
          const r = await api("api/env/dataset", { id: x.id, version: st.ver === "live" ? undefined : +st.ver });
          st.pv[key] = r || { error: "?" };
          if (cur() !== x || key !== x.id + "@" + (st.ver === "live" ? "" : st.ver)) return;     // inzwischen anders gewählt
        }
        const r = st.pv[key];
        if (r.error) { $p.innerHTML = `<div class="limp-warn">${esc(t("imp.err", { e: r.error }))}</div>`; updateFoot(); return; }
        const p = r.producer || {};
        const chips = [t("imp.rows", { n: r.rows }), t("imp.cols", { n: r.columns.length }), r.excluded ? t("imp.excl", { n: r.excluded }) : "",
          r.derived ? t("imp.derived") : "", "v" + r.version + (r.version === r.latest ? "" : " / " + r.latest)].filter(Boolean);
        const vers = r.versions && r.versions.length ? r.versions : [{ version: r.latest }];
        const verSel = `<div class="limp-ver"><label>${esc(t("imp.ver"))} <select data-ver title="${esc(t("imp.live_t"))}">
            <option value="live"${st.ver === "live" ? " selected" : ""}>${esc(t("imp.live", { v: r.latest }))}</option>
            ${vers.map((v) => `<option value="${v.version}"${st.ver === String(v.version) ? " selected" : ""}>${esc(t("imp.pin", { v: v.version }))}${v.created ? " · " + esc(day(v.created)) : ""}${v.rows != null ? " · " + esc(t("imp.rows", { n: v.rows })) : ""}</option>`).join("")}</select></label></div>`;
        const cols = `<table><thead><tr><th>${esc(t("imp.c_name"))}</th><th>${esc(t("imp.c_unit"))}</th><th>${esc(t("imp.c_range"))}</th></tr></thead><tbody>${r.columns.map((c) => {
          const e = r.ext && r.ext[c.key];
          return `<tr><td>${esc(c.name)}${c.role && c.role !== "value" ? ` <span class="sub">(${esc(c.role)})</span>` : ""}</td><td>${esc(c.unit || (c.dtype === "text" ? "" : "1"))}</td>
            <td class="n">${c.dtype === "text" ? esc(t("imp.text")) : e ? `${esc(num(e[0]))} … ${esc(num(e[1]))}` : "–"}</td></tr>`;
        }).join("")}</tbody></table>`;
        const f = r.first || { keys: [], n: 0, values: {} };
        const first = f.n ? `<details><summary>${esc(t("imp.first"))}</summary><div class="limp-first"><table><thead><tr>${f.keys.map((k) => { const c = r.columns.find((y) => y.key === k) || { name: k }; return `<th>${esc(c.name)}</th>`; }).join("")}</tr></thead>
          <tbody>${Array.from({ length: f.n }, (_, i) => `<tr>${f.keys.map((k) => `<td class="n">${esc(num((f.values[k] || [])[i]))}</td>`).join("")}</tr>`).join("")}</tbody></table></div></details>` : "";
        const bad = fits({ ...x, columns: r.columns, rows: r.rows });
        $p.innerHTML = `<h3>${esc(r.title || x.title)}</h3>
          <div class="sub">${esc(t("imp.from", { m: modName(p) }))}${p.env_name ? " · " + esc(p.env_name) : ""}${p.item_name ? " · " + esc(p.item_name) : ""}${r.created ? " · " + esc(day(r.created)) : ""}</div>
          <div class="limp-chips">${chips.map((c) => `<span>${esc(c)}</span>`).join("")}</div>
          ${thumbSvg(r.thumb)}${verSel}${cols}${first}${bad ? `<div class="limp-warn">${esc(t("imp.nofit", { e: bad }))}</div>` : ""}`;
        updateFoot();
      }
      function updateFoot() {
        const x = cur();
        d.querySelectorAll("[data-act]").forEach((b) => { b.disabled = !x; });
      }
      function choose(id) {
        if (id === st.sel) return;
        st.sel = id; st.ver = "live";
        $l.querySelectorAll(".limp-it").forEach((b) => { const on = b.dataset.id === id; b.classList.toggle("on", on); b.setAttribute("aria-selected", String(on)); });
        preview();
      }
      function finish(action) {
        const x = cur();
        if (!x) return;
        const key = x.id + "@" + (st.ver === "live" ? "" : st.ver), r = st.pv[key] && !st.pv[key].error ? st.pv[key] : null;
        let env = null;
        if (tg) {
          const to = d.querySelector("[data-to]").value;
          if (to === "+new") {
            const nm = d.querySelector("[data-newname]").value.trim();
            if (!nm) { d.querySelector("[data-newname]").focus(); return; }
            env = { create: nm };
          } else env = { id: to };
        }
        result = { id: x.id, title: (r && r.title) || x.title, latest: x.latest, mode: st.ver === "live" ? "live" : "pin",
          version: st.ver === "live" ? x.latest : +st.ver, rows: r ? r.rows : x.rows, columns: r ? r.columns : x.columns,
          producer: x.producer, for_me: x.for_me, action, env };
        settle();
      }

      d.addEventListener("click", (e) => {
        if (e.target === d || e.target.closest("[data-x],[data-cancel]")) { settle(); return; }
        const it = e.target.closest(".limp-it"); if (it) { choose(it.dataset.id); return; }
        const a = e.target.closest("[data-act]"); if (a && !a.disabled) finish(a.dataset.act);
      });
      d.addEventListener("dblclick", (e) => { if (e.target.closest(".limp-it")) finish(acts[0].id); });
      d.addEventListener("change", (e) => {
        if (e.target.matches("[data-ver]")) { st.ver = e.target.value; preview(); }
        if (e.target.matches("[data-to]")) {
          const nn = d.querySelector("[data-newname]"); nn.hidden = e.target.value !== "+new";
          if (!nn.hidden) { if (!nn.value) nn.value = `${tg.word || "Umgebung"} ${tg.envs.length + 1}`; nn.focus(); nn.select(); }
        }
      });
      if ($q) $q.addEventListener("input", () => { st.q = $q.value; renderList(); const v = visible(); if (v.length && !v.some((x) => x.id === st.sel)) choose(v[0].id); });
      d.addEventListener("keydown", (e) => {
        if (e.key === "ArrowDown" || e.key === "ArrowUp") {
          if (e.target.matches("select,input[data-newname]")) return;
          const v = visible(); if (!v.length) return;
          e.preventDefault();
          const i = v.findIndex((x) => x.id === st.sel), k = Math.max(0, Math.min(v.length - 1, i + (e.key === "ArrowDown" ? 1 : -1)));
          choose(v[k].id);
          $l.querySelector(".limp-it.on")?.scrollIntoView({ block: "nearest" });
        } else if (e.key === "Enter" && (e.target === $q || e.target.closest(".limp-it") || e.target.matches("[data-newname]"))) {
          e.preventDefault(); finish(acts[0].id);
        }
      });
      d.addEventListener("close", settle);
      renderList();
      preview();
      d.showModal();
      ($q && !$q.hidden ? $q : d.querySelector("[data-cancel]")).focus();
      if (st.sel) $l.querySelector(".limp-it.on")?.scrollIntoView({ block: "nearest" });
    });
  }

  g.LabImport = { open };
})(window);
