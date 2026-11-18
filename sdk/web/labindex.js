/* Projekt-Index (A7) für Modulseiten. Der Modulserver stellt /api/index/list|add|get bereit (labindex.route).
 *
 *   LabIndex.add(api, toast, {key, label, quantity: {value, unit, u?}, type, conditions?, source?, provenance?})
 *     – fragt Grösse, Art und Notiz nach und legt einen neuen, unveränderlichen Eintrag an.
 *   LabIndex.browse(api, toast, onTake?)
 *     – zeigt alle Einträge des aktiven Projekts nach Grösse (Alternativen untereinander); onTake(entry) übernimmt.
 */
(function (g) {
  "use strict";
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
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
        <td style="white-space:nowrap"><button type="button" data-hist="${esc(e.id)}" title="Herkunft bis zur Rohdatei">Herkunft</button>${onTake ? ` <button type="button" data-take="${esc(e.id)}">Übernehmen</button>` : ""}</td></tr>`;
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

  g.LabIndex = { add, addMany, browse, history, exportDeps };
})(window);
