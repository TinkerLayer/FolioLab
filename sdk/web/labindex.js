/* Projekt-Index (A7) für Modulseiten. Der Modulserver stellt /api/index/list|add|get bereit (labindex.route).
 *
 *   LabIndex.add(api, toast, {key, label, quantity: {value, unit, u?}, type, conditions?, source?, provenance?})
 *     – fragt Grösse, Art und Notiz nach und legt einen neuen, unveränderlichen Eintrag an.
 *   LabIndex.browse(api, toast, onTake?)
 *     – zeigt alle Einträge des aktiven Projekts nach Grösse (Alternativen untereinander); onTake(entry) übernimmt.
 *   LabIndex.taker({api, toast, get, set, names, vars, refresh, save, el, reveal?})
 *     – Indexwerte als benannte Variablen eigener Gleichungen: .take(entry), .render(), .defs(), .ext(), .own(rows).
 */
(function (g) {
  "use strict";
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const L = (de, en) => (g.LabUI && g.LabUI.lang && g.LabUI.lang() === "en" ? en : de);
  const TYPES = { measured: "gemessen", calculated: "berechnet", tabulated: "Tabellenwert", estimated: "Schätzung" };
  const fmt = (q) => `${Number(q.value).toPrecision(6).replace(/\.?0+(e|$)/, "$1")}${q.u != null ? ` ± ${q.u}` : ""} ${q.unit || ""}`.trim();

  function box(html, wide) {
    const d = document.createElement("dialog");
    d.className = "labindex";
    d.style.cssText = `max-width:${wide ? 760 : 460}px;width:94vw;border:1px solid #bbb;border-radius:8px;padding:16px;font:inherit`;
    d.innerHTML = html;
    document.body.appendChild(d);
    d.addEventListener("close", () => setTimeout(() => d.remove(), 0));
    d.showModal();
    return d;
  }

  function add(api, toast, e) {
    return new Promise((res) => {
      const d = box(`<form method="dialog" style="display:flex;flex-direction:column;gap:8px">
        <b style="font-size:1.05em">In den Projektindex</b>
        <div style="opacity:.8">Ein Indexeintrag ist projektweit aus jedem Modul lesbar und wird nie überschrieben. Ein anderer Wert für
          dieselbe Grösse wird als Alternative daneben abgelegt.</div>
        <div><b>${esc(fmt(e.quantity))}</b> – ${esc(e.label || "")}</div>
        <label>Grösse (Schlüssel, fasst Alternativen zusammen) <input name="key" maxlength="80" style="width:100%" value="${esc(e.key || e.label || "")}"></label>
        <label>Art <select name="type">${Object.entries(TYPES).map(([k, v]) => `<option value="${k}" ${k === e.type ? "selected" : ""}>${v}</option>`).join("")}</select></label>
        <label>Notiz <input name="note" maxlength="300" style="width:100%"></label>
        <div style="display:flex;gap:6px;justify-content:flex-end"><button value="cancel">Abbrechen</button><button value="ok" class="primary">Eintragen</button></div></form>`);
      d.addEventListener("close", async () => {
        if (d.returnValue !== "ok") return res(null);
        const f = d.querySelector("form");
        const j = await api("api/index/add", { ...e, key: f.key.value.trim(), type: f.type.value, note: f.note.value.trim() });
        if (!j || j.error) { toast((j && j.error) || "Fehler", true); return res(null); }
        const alt = (j.alternative_to || []).length;
        toast(`Im Projektindex als ${j.id}${alt ? ` (Alternative zu ${alt} vorhandenen Werten)` : ""}.`);
        res(j);
      });
    });
  }

  // mehrere Ergebnisse auf einmal (z. B. alle Stufen eines TGA-Laufs): ein Dialog mit Häkchen und Schlüssel je Zeile
  function addMany(api, toast, entries, title = "In den Projektindex") {
    return new Promise((res) => {
      const rows = entries.map((e, i) => `<tr><td><input type="checkbox" name="on${i}" checked></td>
        <td><input name="key${i}" maxlength="80" style="width:100%" value="${esc(e.key || e.label || "")}"></td>
        <td style="text-align:right;white-space:nowrap">${esc(fmt(e.quantity))}</td></tr>`).join("");
      const d = box(`<form method="dialog" style="display:flex;flex-direction:column;gap:8px">
        <b style="font-size:1.05em">${esc(title)}</b>
        <div style="opacity:.8">Jede Zeile wird ein eigener, unveränderlicher Eintrag; vorhandene Werte derselben Grösse bleiben als Alternativen bestehen.</div>
        <table style="width:100%">${rows}</table>
        <label>Art <select name="type">${Object.entries(TYPES).map(([k, v]) => `<option value="${k}" ${k === (entries[0] || {}).type ? "selected" : ""}>${v}</option>`).join("")}</select></label>
        <div style="display:flex;gap:6px;justify-content:flex-end"><button value="cancel">Abbrechen</button><button value="ok" class="primary">Eintragen</button></div></form>`, true);
      d.addEventListener("close", async () => {
        if (d.returnValue !== "ok") return res([]);
        const f = d.querySelector("form"), out = [];
        for (let i = 0; i < entries.length; i++) {
          if (!f[`on${i}`].checked) continue;
          const j = await api("api/index/add", { ...entries[i], key: f[`key${i}`].value.trim(), type: f.type.value });
          if (!j || j.error) { toast((j && j.error) || "Fehler", true); break; }
          out.push(j);
        }
        if (out.length) toast(`${out.length} Einträge im Projektindex (${out.map((x) => x.id).join(", ")}).`);
        res(out);
      });
    });
  }

  async function browse(api, toast, onTake) {
    const j = await api("api/index/list", {});
    if (!j || j.error) return toast((j && j.error) || "Fehler", true);
    const rows = j.groups.map((gp) => gp.entries.map((e, i) => {
      const p = e.provenance || {};
      return `<tr${i ? ' style="opacity:.92"' : ""}><td>${i ? "" : `<b>${esc(gp.key)}</b>${gp.entries.length > 1 ? ` <small>(${gp.entries.length} Werte)</small>` : ""}`}</td>
        <td style="text-align:right;white-space:nowrap">${esc(fmt(e.quantity))}</td><td>${esc(TYPES[e.type] || e.type)}</td>
        <td><small>${esc(e.id)} · ${esc([p.module, p.env_name || p.env, p.item_name].filter(Boolean).join(" · "))}${p.share ? ` · ${esc(p.share)} v${esc(p.version)}` : ""}${e.source && e.source.title ? ` · ${esc(e.source.title)}` : ""}${e.note ? ` · ${esc(e.note)}` : ""}</small></td>
        <td style="white-space:nowrap"><button type="button" data-hist="${esc(e.id)}" title="Herkunft bis zur Rohdatei">Herkunft</button>${onTake ? ` <button type="button" data-take="${esc(e.id)}">${esc(L("Übernehmen", "Use"))}</button>` : ""}</td></tr>`;
    }).join("")).join("");
    const d = box(`<form method="dialog" style="display:flex;flex-direction:column;gap:8px">
      <b style="font-size:1.05em">Projektindex</b>
      <div style="opacity:.8">Kuratierte Werte dieses Projekts. Mehrere Werte unter einer Grösse sind Alternativen mit eigener ID.</div>
      ${rows ? `<div style="max-height:60vh;overflow:auto"><table style="width:100%;border-collapse:collapse">${rows}</table></div>` : "<p>Noch leer. Ergebnisse lassen sich in den Modulen über „In den Projektindex …“ eintragen.</p>"}
      <div style="display:flex;justify-content:space-between;gap:6px"><button type="button" data-deps title="Freigabe-Versionen, Indexeinträge und Rohdateien, die Berichte dieses Projekts benutzen">Abhängigkeiten exportieren</button><button value="cancel">Schliessen</button></div></form>`, true);
    const all = Object.fromEntries(j.groups.flatMap((gp) => gp.entries).map((e) => [e.id, e]));
    d.querySelectorAll("[data-take]").forEach((b) => b.addEventListener("click", () => { d.close(); onTake(all[b.dataset.take]); }));
    d.querySelectorAll("[data-hist]").forEach((b) => b.addEventListener("click", () => history(api, toast, { index: b.dataset.hist })));
    d.querySelector("[data-deps]").addEventListener("click", () => exportDeps(api, toast));
  }

  // A8: Herkunft auf Anfrage – ref = {index} | {share, version} | {module, env, item}
  async function history(api, toast, ref) {
    const j = await api("api/prov/chain", { ref });
    if (!j || j.error) return toast((j && j.error) || "Fehler", true);
    const icon = { index: "▣", share: "⇄", env: "▤", raw: "◆", end: "●" };
    const steps = j.steps.map((s) => `<li style="margin:4px 0"><b>${icon[s.level] || "•"} ${esc(s.title)}</b>${s.ok === false ? ' <span style="color:#b00">(fehlt)</span>' : ""}
      <div style="opacity:.85">${esc(s.detail || "")}</div>
      ${s.path ? `<div><small>Pfad: <code style="word-break:break-all">${esc(s.path)}</code></small></div>` : ""}
      ${s.sha256 ? `<div><small>SHA-256: <code>${esc(s.sha256)}</code>${s.sha_matches_id ? " ✓ stimmt mit der gespeicherten ID überein" : ""}</small></div>` : ""}
      ${s.protocol && s.protocol.length ? `<div><small>Bearbeitung: ${s.protocol.map(esc).join(" → ")}</small></div>` : ""}</li>`).join("");
    box(`<form method="dialog" style="display:flex;flex-direction:column;gap:8px"><b style="font-size:1.05em">Herkunft</b>
      <ol style="padding-left:1.2em;margin:0">${steps}</ol>
      <div style="display:flex;justify-content:flex-end"><button value="cancel">Schliessen</button></div></form>`, true);
  }

  async function exportDeps(api, toast) {
    const j = await api("api/prov/deps", {});
    if (!j || j.error) return toast((j && j.error) || "Fehler", true);
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([JSON.stringify(j, null, 2)], { type: "application/json" }));
    a.download = `abhaengigkeiten-${j.project}.json`;
    document.body.appendChild(a); a.click(); a.remove();
    toast(`${j.shares.length} Versionen, ${j.index.length} Indexeinträge, ${j.raw_files.length} Rohdateien aufgelistet.`);
  }

  // ---- Indexwerte als Variablen eigener Gleichungen (labcalc.formulas, Kanal ext_values) ----
  // Der Wert bleibt in seiner Einheit, mit u und Herkunft. Je Wert eine Berichtszeile <name>_idx = <name>; so steht er mit
  // Einheit, ± und Quelle in der Gleichungstabelle. Einheiten prüft der Server (taken.py des Moduls).
  const NAME_RE = /^[A-Za-z][A-Za-z0-9_]{0,23}$/;
  const originOf = (e) => { const p = e.provenance || {}; return [p.module, p.env_name || p.env, p.item_name].filter(Boolean).join(" · "); };
  function symFor(e) {
    const s = String(e.key || "x").normalize("NFKD").replace(/[^A-Za-z0-9_]+/g, "_").replace(/^_+|_+$/g, "").replace(/^(\d)/, "x$1").slice(0, 20);
    return NAME_RE.test(s) ? s : "x";
  }
  function sigDigits(v) {
    const n = String(Math.abs(+v)).replace(/e.*$/, "").replace(".", "").replace(/^0+/, "").length;
    return Math.max(4, Math.min(10, n));
  }
  function takenItem(e, name) {
    const q = e.quantity || {}, o = originOf(e), s = e.source;
    return { key: name, label: String(e.label || e.key || name).slice(0, 80), value: +q.value, unit: q.unit || "", ...(+q.u > 0 ? { u: +q.u } : {}),
      from: "index", from_name: `Projektindex ${e.id}${o ? " · " + o : ""}`, mode: "index", index: e.id, type: e.type || "",
      row: `${name.slice(0, 20)}_idx`, source: s && (s.title || s.doi || s.url) ? s : null };
  }
  const takenDefs = (list) => (list || []).map((t) => ({ sym: t.row, label: `${t.label.slice(0, 50)} · ${t.from_name}`.slice(0, 120), expr: t.key,
    unit: t.unit, digits: sigDigits(t.value), source: t.source || null }));
  const ownRows = (list, rows) => (rows || []).filter((r) => !(list || []).some((t) => t.row === r.sym));

  function askName(e, used) {
    let name = symFor(e);
    for (let i = 1; used.has(name) || used.has(`${name.slice(0, 20)}_idx`); i++) name = `${symFor(e).slice(0, 18)}_i${i > 1 ? i : ""}`;
    const q = e.quantity;
    return new Promise((res) => {
      let over = false;
      const end = (v) => { if (!over) { over = true; res(v); } };
      const d = box(`<form method="dialog" style="display:flex;flex-direction:column;gap:8px">
        <b style="font-size:1.05em">${esc(L("In die eigenen Gleichungen", "Into the own equations"))}</b>
        <div><b>${esc(fmt(q))}</b> – ${esc(e.label || e.key || "")}</div>
        <div class="small" style="opacity:.8">${esc(e.id)}${originOf(e) ? " · " + esc(originOf(e)) : ""}</div>
        <label>${esc(L("Name in den Gleichungen", "Name in the equations"))} <input name="sym" maxlength="24" style="width:100%" spellcheck="false" value="${esc(name)}"></label>
        <div class="small" style="opacity:.8">${esc(L("Gleichungen rechnen mit dem Zahlenwert in dieser Einheit. Neben einer Grösse gleicher Art in anderer Einheit wird die Gleichung abgelehnt.",
          "Equations use the number in this unit. Next to a quantity of the same kind in another unit the equation is refused."))}</div>
        <div data-err role="alert" style="color:#b00" hidden></div>
        <div style="display:flex;gap:6px;justify-content:flex-end"><button value="cancel" formnovalidate>${esc(L("Abbrechen", "Cancel"))}</button><button value="ok" class="primary">${esc(L("Übernehmen", "Use"))}</button></div></form>`);
      const f = d.querySelector("form"), err = d.querySelector("[data-err]");
      f.addEventListener("submit", (ev) => {
        ev.preventDefault();
        if (!ev.submitter || ev.submitter.value !== "ok") { d.close(); return end(null); }
        const s = f.sym.value.trim();
        const msg = !NAME_RE.test(s) ? L("Name: Buchstabe am Anfang, dann Buchstaben, Ziffern oder _ (höchstens 24 Zeichen).", "Name: a letter first, then letters, digits or _ (at most 24 characters).")
          : used.has(s) || used.has(`${s.slice(0, 20)}_idx`) ? L(`„${s}“ ist hier schon vergeben.`, `“${s}” is already used here.`) : "";
        if (msg) { err.textContent = msg; err.hidden = false; return; }
        d.close(); end(s);
      });
      d.addEventListener("close", () => end(null));
    });
  }

  function taker(o) {
    const list = () => o.get() || [];
    async function verify() {                          // reservierte Namen (pi, R …) benennt der Server um: dann nicht still weiter
      const vars = o.vars() || [];
      if (!vars.length) return;
      const bad = list().filter((t) => !vars.some((v) => v.name === t.key && v.ext));
      if (!bad.length) return;
      o.set(list().filter((t) => !bad.includes(t)));
      o.toast(L(`„${bad[0].key}“ ist ein reservierter Name; Wert nicht übernommen.`, `“${bad[0].key}” is a reserved name; value not taken.`), true);
      await o.refresh();
    }
    function render() {
      const el = o.el && o.el();
      if (!el) return;
      const L_ = list();
      el.hidden = !L_.length;
      el.innerHTML = L_.length ? `<div class="small" style="margin:6px 0 2px"><b>${esc(L("Aus dem Projektindex", "From the project index"))}</b></div>` + L_.map((t, i) =>
        `<div style="display:flex;gap:6px;align-items:baseline;flex-wrap:wrap"><code>${esc(t.key)}</code><span>= ${esc(fmt(t))}</span><span class="small" style="opacity:.8;flex:1 1 120px">${esc(t.label)} · ${esc(t.from_name)}</span>
          <button type="button" data-t-h="${i}">${esc(L("Herkunft", "Provenance"))}</button><button type="button" data-t-x="${i}" aria-label="${esc(L("Entfernen", "Remove"))}" title="${esc(L("Entfernen", "Remove"))}">×</button></div>`).join("") : "";
      el.onclick = async (ev) => {
        const h = ev.target.closest("[data-t-h]"), x = ev.target.closest("[data-t-x]");
        if (h) return history(o.api, o.toast, { index: list()[+h.dataset.tH].index });
        if (!x) return;
        o.set(list().filter((_, i) => i !== +x.dataset.tX));
        await o.refresh(); render(); o.save();
      };
    }
    async function take(e) {
      const q = e && e.quantity;
      if (!q || !Number.isFinite(+q.value)) return o.toast(L("Dieser Eintrag hat keinen Zahlenwert.", "This entry has no number."), true);
      const had = list().find((t) => t.index === e.id);
      if (had) return o.toast(L(`Schon übernommen als ${had.key}.`, `Already taken as ${had.key}.`));
      const used = new Set([...(o.names() || []), ...list().flatMap((t) => [t.key, t.row])]);
      const name = await askName(e, used);
      if (!name) return;
      const it = takenItem(e, name);
      o.set([...list(), it]);
      await o.refresh();
      await verify();
      render(); o.save();
      if (o.reveal) o.reveal();
      if (list().includes(it)) o.toast(L(`${name} aus dem Projektindex (${e.id}) übernommen.`, `${name} taken from the project index (${e.id}).`));
    }
    return { take, render, verify, defs: () => takenDefs(list()), own: (rows) => ownRows(list(), rows), ext: (rest) => [...list(), ...(rest || [])] };
  }

  g.LabIndex = { add, addMany, browse, history, exportDeps, taker, takenItem, takenDefs, ownRows, symFor, originOf };
})(window);
