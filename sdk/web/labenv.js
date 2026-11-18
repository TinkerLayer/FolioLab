/* Umgebungen (A2) für Modulseiten: geladene Dateien und Arbeitsstand bleiben über Neustarts erhalten.
 * Der Modulserver stellt /api/env/open|info|client|switch|create|rename|delete bereit (labproject.ModuleEnvs).
 *
 *   const ENVS = LabEnv.create({
 *     api, toast,                       // Funktionen der Seite
 *     keep: ["name", "pipeline", …],    // Felder je Eintrag, die gespeichert werden
 *     list: () => S.runs,               // aktuelle Einträge (Objekte mit .id)
 *     sel: () => S.sel,
 *     reset: () => { S.runs = []; S.sel = -1; },
 *     add: async (d, saved) => { … },   // Eintrag aus Serverbeschreibung d anlegen, gespeicherte Felder übernehmen
 *     done: (sel, extra) => { … },      // danach auswählen und neu zeichnen
 *     extra: () => ({…}),               // optional: Zustand der Seite ausserhalb der Einträge
 *     label: document.querySelector("#envName"),
 *   });
 *   await ENVS.open();  ENVS.save() nach Änderungen;  ENVS.dialog() aus dem Menü.
 */
(function (g) {
  "use strict";
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  // Die Zusammenfassung muss unter die Grenze des Servers passen (labproject.MAX_SUMMARY, 48 KB); sonst bliebe die alte
  // stehen. UI-18: Grafiken (plots) zuerst ausdünnen, dann weniger Grafiken, zuletzt den Wertekatalog kürzen.
  const MAX_SUMMARY = 46000;
  const size = (x) => JSON.stringify(x).length;
  function fitSummary(s) {
    if (!s || typeof s !== "object") return s;
    const pack = (p, n) => (g.LabBoard && g.LabBoard.packPlots ? g.LabBoard.packPlots(p, n) : []);
    s = { ...s };
    if (Array.isArray(s.plots)) {
      s.plots = pack(s.plots, 120);
      for (const n of [60, 30]) if (size(s) > MAX_SUMMARY) s.plots = pack(s.plots, n);
      while (s.plots.length > 1 && size(s) > MAX_SUMMARY) s.plots = s.plots.slice(0, -1);
      if (!s.plots.length) delete s.plots;
    }
    if (Array.isArray(s.values) && size(s) > MAX_SUMMARY) { s.values = [...s.values]; while (s.values.length && size(s) > MAX_SUMMARY) s.values.pop(); }
    if (size(s) > MAX_SUMMARY) delete s.plots;
    return s;
  }

  function create(o) {
    let info = null, timer = 0, ready = false;
    const snapshot = () => ({
      sel: o.sel(),
      items: Object.fromEntries(o.list().map((x) => [x.id, Object.fromEntries(o.keep.map((k) => [k, x[k]]))])),
      extra: o.extra ? o.extra() : null,
      ...(o.summary ? { summary: fitSummary(o.summary()) } : {}),      // UI-10: kurze Zusammenfassung für die Übersicht
    });
    const title = () => {
      if (!info || !o.label) return;
      const e = info.envs.find((x) => x.id === info.active);
      o.label.textContent = `${info.project.name} · ${e ? e.name : info.active}`;
      o.label.hidden = false;
    };
    async function apply(j) {
      if (!j || j.error) { if (j) o.toast("Umgebung: " + j.error, true); return; }
      info = { project: j.project, envs: j.envs, active: j.active };
      ready = false;
      o.reset();
      const saved = (j.client && j.client.items) || {};
      for (const d of j.items || []) {
        const s = saved[d.id] || {};
        const keep = Object.fromEntries(o.keep.filter((k) => s[k] !== undefined && s[k] !== null).map((k) => [k, s[k]]));
        try { await o.add(d, keep); } catch (e) { o.toast(`${d.name || d.id}: ${e.message}`, true); }
      }
      const n = o.list().length;
      const sel = j.client && Number.isInteger(j.client.sel) ? j.client.sel : 0;
      // "reload": die Seite lädt sich neu. Bis dahin nichts mehr speichern – sonst schriebe das pagehide-Speichern den
      // alten Seitenzustand in die eben geöffnete Umgebung.
      if (o.done(n ? Math.min(Math.max(sel, 0), n - 1) : -1, j.client ? j.client.extra : null) === "reload") { clearTimeout(timer); return; }
      ready = true;
      title();
    }
    function save() {
      if (!ready) return;
      clearTimeout(timer);
      timer = setTimeout(() => o.api("api/env/client", { client: snapshot() }), 800);
    }
    function flush(keepalive = false) {
      if (!ready) return Promise.resolve();
      clearTimeout(timer);
      if (keepalive) {
        try {
          fetch("api/env/client", { method: "POST", keepalive: true, headers: { "Content-Type": "application/json" }, body: JSON.stringify({ client: snapshot() }) });
        } catch (e) { /* Seite schliesst */ }
        return Promise.resolve();
      }
      return o.api("api/env/client", { client: snapshot() });
    }
    async function open() {
      await apply(await o.api("api/env/open", {}));
      g.addEventListener("pagehide", () => flush(true));
      g.addEventListener("focus", check);
    }
    async function check() {
      if (!ready) return;
      const j = await o.api("api/env/open", { check: 1 });
      if (j && j.changed) await apply(j);
    }
    function ask(i) {
      // eigener kleiner Dialog, damit jede Seite ihn unverändert nutzen kann
      return new Promise((res) => {
        const d = document.createElement("dialog");
        d.className = "labenv";
        d.style.cssText = "max-width:440px;width:92vw;border:1px solid #bbb;border-radius:8px;padding:16px;font:inherit";
        const opts = i.envs.map((e) => `<option value="${esc(e.id)}" ${e.id === i.active ? "selected" : ""}>${esc(e.name)}${e.id === i.active ? " (offen)" : ""}</option>`).join("");
        d.innerHTML = `<form method="dialog" style="display:flex;flex-direction:column;gap:8px">
          <b style="font-size:1.05em">Umgebungen</b>
          <div style="opacity:.8">Projekt: <b>${esc(i.project.name)}</b>. Eine Umgebung behält ihre Dateien und den Arbeitsstand, auch nach einem Neustart.</div>
          <select name="id" size="6" style="width:100%">${opts}</select>
          <label>Name (für Neu anlegen oder Umbenennen) <input name="name" maxlength="80" style="width:100%"></label>
          <div style="display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end">
            <button value="cancel">Schliessen</button><button value="del">Löschen</button><button value="ren">Umbenennen</button>
            <button value="new">Neu anlegen</button><button value="go" class="primary">Öffnen</button></div></form>`;
        document.body.appendChild(d);
        d.addEventListener("close", () => {
          const f = d.querySelector("form");
          res({ act: d.returnValue || "cancel", id: f.id.value, name: f.name.value.trim() });
          d.remove();
        });
        d.showModal();
      });
    }
    async function dialog() {
      const i = await o.api("api/env/info", {});
      if (i.error) return o.toast(i.error, true);
      info = { ...info, project: i.project, envs: i.envs, active: i.active };
      const r = await ask(i);
      if (r.act === "cancel") return;
      await flush();
      if (r.act === "go" && r.id && r.id !== i.active) await apply(await o.api("api/env/switch", { id: r.id }));
      else if (r.act === "new") await apply(await o.api("api/env/create", { name: r.name }));
      else if (r.act === "ren") {
        if (!r.name) return o.toast("Bitte einen neuen Namen eingeben.", true);
        const j = await o.api("api/env/rename", { id: r.id, name: r.name });
        if (j.error) return o.toast(j.error, true);
        info.envs = j.envs; title();
      } else if (r.act === "del") {
        if (r.id === "standard") return o.toast("Die Standardumgebung bleibt immer erhalten.", true);
        if (!confirm("Umgebung in den Papierkorb verschieben? Die Dateien bleiben im Projektordner unter _papierkorb.")) return;
        await apply(await o.api("api/env/delete", { id: r.id }));
      }
    }
    // UI-10: Steuerung aus der Übersicht (ohne Dialog)
    async function refresh() {
      const i = await o.api("api/env/info", {});
      if (i && !i.error) { info = { ...info, project: i.project, envs: i.envs, active: i.active }; title(); }
      return info;
    }
    async function switchTo(id) { await flush(); if (info && id === info.active) return; await apply(await o.api("api/env/switch", { id })); }
    async function createNew(name) { await flush(); await apply(await o.api("api/env/create", { name: name || "" })); }
    async function rename(id, name) {
      const j = await o.api("api/env/rename", { id, name });
      if (j.error) { o.toast(j.error, true); return; }
      info.envs = j.envs; title();
    }
    // In den Papierkorb (_papierkorb) verschieben; die Standardumgebung bleibt. true, wenn gelöscht.
    async function remove(id) {
      if (id === "standard") { o.toast("Die Standardumgebung bleibt immer erhalten.", true); return false; }
      await flush();
      const j = await o.api("api/env/delete", { id });
      if (!j || j.error) { o.toast("Umgebung: " + ((j && j.error) || "Löschen fehlgeschlagen"), true); return false; }
      await apply(j);
      return true;
    }
    return { open, save, flush, check, dialog, refresh, switchTo, createNew, rename, remove, get ready() { return ready; }, get info() { return info; } };
  }

  g.LabEnv = { create };
})(window);
