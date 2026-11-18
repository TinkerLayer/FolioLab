/* Übersicht einer Modulseite (UI-04…09, Q27): Startansicht mit Kästen für die Umgebungen des Moduls, die an das Modul
 * geteilten Ergebnisse anderer Module (nur lesen), den Projektindex und die eigenen Freigaben. Ein Klick auf eine
 * Umgebung öffnet sie (Detailansicht = die bisherige Seite); „◂ Übersicht“ führt zurück. Baut auf labboard.js, labui.js
 * und labenv.js auf; der Server liefert /api/env/info|board|shares (labproject.ModuleEnvs).
 *
 *   const OV = LabOverview.create({
 *     api, toast, module: "rechner",
 *     envs: () => window.ENVS,                       // LabEnv-Objekt (switchTo, createNew, refresh, info)
 *     detail: [document.querySelector("main")],      // was in der Übersicht verborgen wird
 *     crumbs: document.querySelector("header .left"),// hier steht „◂ Übersicht · Name“ (vorne eingefügt)
 *     word: { de: ["Blatt", "Blätter"], en: ["Sheet", "Sheets"] },   // optional: Name der Umgebungen
 *     envHtml: (e, active) => "…",                   // optional: Inhalt eines Umgebungskastens (sonst summary.title/tags)
 *     incoming: { "chem.values": { label: "…", run: (share) => … } },  // optional: Aktion für geteilte Ergebnisse
 *     index: () => LabIndex.browse(api, toast),       // optional: Klick auf den Projektkasten
 *     onView: (v) => …,                               // optional: "board" | "detail"
 *   });
 *   await ENVS.open(); OV.start();                   // Startansicht: Übersicht (oder #umgebung aus der Adresse)
 *
 * Elemente mit dem Attribut data-lov-detail werden in der Übersicht verborgen (z. B. Knöpfe, die nur in einer
 * geöffneten Umgebung Sinn haben). Die Umgebung meldet ihren Kasteninhalt über LabEnv.create({summary: () => ({title,
 * tags})}).
 *
 * Verbindungen zwischen Umgebungen (wie UI-15 im Elementrechner): mit `values` (und/oder eigenen `channels`) bekommen
 * die Umgebungskästen Anschlüsse; eine gezogene Verbindung A → B wählt, was B von A bekommt, live (folgt A) oder als
 * Momentaufnahme. In der geöffneten Umgebung steht vorne in der Brotkrume „⇄ Verbindungen“ (ausgehend, eingehend,
 * Freigaben an andere Module, an dieses Modul geteilt); OV.shareButton(key) liefert einen ⇄-Knopf für ein Ergebnis.
 *
 *   values: { catalogue: () => [{sym, label, value, unit, kind}],      // teilbare Zahlenwerte der offenen Umgebung
 *             apply: async (rows) => …,                                 // verbundene Werte in die offene Umgebung
 *             version: "1.2.0" },                                       // rows: [{key,label,value,unit,kind,from,from_name,share,version,mode}]
 *   channels: [{ kind, label: () => "Datensätze", offers: async (envId) => [{key, label, text}],
 *                link: async (envId, keys, mode) => ({keys?, share?, version?}), apply: async (links) => … }]
 *   Zusammenfassung: summary: () => ({title, tags, values: LabOverview.summaryValues(catalogue)}) – damit Werte nicht
 *   geöffneter Umgebungen wählbar sind. Nach Änderungen OV.changed() rufen (veröffentlicht ausgehende Werte neu).
 *
 * Import (I-03, braucht labimport.js): mit `imports` steht in der Brotkrume der offenen Umgebung „⤓ Importieren“ und
 * auf der Übersicht „⤓ Datensatz importieren …“ (mit Wahl der Ziel-Umgebung, auch einer neuen). Beide öffnen das
 * Import-Fenster; nach der Wahl ist die Ziel-Umgebung offen und `run(pick)` übernimmt den Datensatz.
 *
 *   imports: { actions: [{id, label, hint}], check: (d) => "", run: async (pick) => … }   // pick: siehe labimport.js
 *   OV.importDataset({select?}) öffnet das Fenster auch aus der Seite (z. B. ein Menüeintrag „Aus Datensatz …“).
 */
(function (g) {
  "use strict";
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const MOD = { tga: "TGA", ftir: "FTIR", rechner: "Rechner", zugversuch: "Zugversuch", mikroskopie: "Mikroskopie", elementrechner: "Elementrechner", datenaufbereitung: "Datenaufbereitung" };
  const CSS = `
.lov{padding:12px 16px 20px;overflow:auto;min-height:0}
.lov .lov-head{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:8px}
.lov .lov-head b{font-size:15px}
.lov .lov-hint{font-size:12px;opacity:.75}
.lov .lab-box .lov-t{font-family:ui-monospace,Consolas,monospace;font-size:11.5px;color:var(--ink,#1d2027)}
.lov .lab-box .lov-tags{display:flex;flex-wrap:wrap;gap:3px;margin-top:4px}
.lov .lab-box .lov-tags span{font-size:10.5px;padding:0 6px;border-radius:9px;border:1px solid var(--line,#d8dce4);white-space:nowrap}
.lov-crumbs{display:inline-flex;align-items:center;gap:6px;min-width:0;flex-shrink:1}
.lov-crumbs .lov-back{white-space:nowrap}
.lov-crumbs .lov-env{font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:min(24ch,28vw)}
body.lov-board .lov-hide,body.lov-board [data-lov-detail]{display:none!important}
.lov-pop .row{display:flex;gap:6px;flex-wrap:wrap;margin-top:6px;align-items:center}
.lov-crumbs .lov-con{white-space:nowrap}
.lov-crumbs .lov-con .n{display:inline-block;min-width:16px;padding:0 4px;margin-left:3px;border-radius:8px;font-size:10.5px;background:var(--accent,#6d28d9);color:#fff}
.lov-pop{max-width:min(560px,92vw)}
.lov-pop table{border-collapse:collapse;width:100%;margin-top:4px}
.lov-pop td{padding:2px 6px 2px 0;vertical-align:top;font-size:12px;overflow-wrap:anywhere}
.lov-pop td.k{white-space:nowrap}
.lov-pop .lov-scroll{max-height:42vh;overflow:auto;margin-top:6px}
.lov-pop .lov-sec{margin-top:8px;font-size:11.5px;font-weight:600;color:var(--muted,#5d6472)}
.lov-shr{border:0;background:none;padding:0 3px;cursor:pointer;color:var(--accent,#6d28d9);font-size:13px;line-height:1}
.lov-shr:hover{background:var(--hover,rgba(109,40,217,.08));border-radius:4px}
.lov .lab-box .lov-links{margin-top:4px;font-size:10.5px;color:var(--muted,#5d6472)}
.lov-crumbs .lov-imp,.lov .lov-impb{white-space:nowrap}
.lov .lov-head .lov-impb{margin-left:auto}`;

  const T = {
    de: { "ov.title": "Übersicht", "ov.project": "Projekt", "ov.back": "◂ Übersicht", "ov.back_t": "Zurück zur Übersicht",
          "ov.hint": "Kasten anklicken: öffnen · Kasten ziehen: anordnen · geteilte Ergebnisse links, eigene Freigaben rechts",
          "ov.k_index": "Projekt", "ov.index": "Projektindex", "ov.index_s": "Kuratierte Werte, aus jedem Modul lesbar",
          "ov.k_share": "Geteilt an dieses Modul", "ov.k_own": "Geteilt", "ov.open": "offen", "ov.empty": "noch leer",
          "ov.new_q": "Name:", "ov.latest": "neueste", "ov.from": "Von", "ov.hist": "Herkunft …",
          "ov.ro": "Nur lesbar: ändern kann diese Freigabe nur ihr Ursprungsmodul ({m}).",
          "ov.own_note": "Von diesem Modul geteilt; jede Übergabe ist eine neue Version.",
          "ov.own_wire": "Diese Freigabe stammt aus der verbundenen Umgebung.", "ov.to": "an",
          "ov.kind.tga.steps": "TGA-Stufen", "ov.kind.ftir.peaks": "FTIR-Banden", "ov.kind.chem.values": "Werte",
          "ov.kind.chem.envvalues": "Werte zwischen Umgebungen", "ov.kind.data.table": "Datensatz",
          "ov.kind.lab.envvalues": "Werte zwischen Umgebungen",
          "ov.con": "⇄ Verbindungen", "ov.con_t": "Was diese Umgebung an andere liefert und von ihnen bekommt, was an andere Module geteilt ist",
          "ov.ch_values": "Werte", "ov.ch_value1": "Wert", "ov.live": "live", "ov.copy": "Momentaufnahme", "ov.live_t": "folgt jeder Änderung der Quelle",
          "ov.copy_t": "fester Stand; später von Hand nachführen", "ov.to_env": "An", "ov.go_live": "Live verbinden", "ov.go_copy": "Momentaufnahme",
          "ov.already": "Schon verbunden mit", "ov.one": "Nur eine Umgebung – auf der Übersicht „+ {w}“ anlegen, dann verbinden.",
          "ov.l_hint": "Klick: auswählen, Art ändern oder lösen", "ov.l_head": "{a} → {b}", "ov.l_none": "{a} hat noch nichts zum Teilen.",
          "ov.l_kept": "(nicht mehr vorhanden, letzter Stand bleibt)", "ov.apply": "Übernehmen", "ov.connect": "Verbinden", "ov.unlink": "Lösen",
          "ov.l_modes": "Live: B folgt jeder Änderung in A. Momentaufnahme: B behält den Stand von jetzt.",
          "ov.done": "{n} × {c}: {a} → {b} ({m})", "ov.cm_out": "Liefert an", "ov.cm_in": "Bekommt von", "ov.cm_new": "Neue Verbindung an",
          "ov.cm_pick": "Auswählen …", "ov.cm_own": "An andere Module geteilt", "ov.cm_inc": "An dieses Modul geteilt", "ov.cm_board": "Übersicht öffnen",
          "ov.cm_n": "Verbindungen lassen sich auch auf der Übersicht ziehen: vom Punkt rechts am Kasten zum anderen Kasten.",
          "ov.mode": "Art", "ov.edit": "Bearbeiten", "ov.shr_t": "An eine andere Umgebung geben", "ov.noenv": "Verbindungen gibt es erst, wenn das Modul mit Umgebungen läuft (über den Hub).",
          "ov.gone": "Dieser Wert ist gerade nicht vorhanden.", "ov.from_env": "von {e}",
          "ov.imp": "⤓ Importieren", "ov.imp_t": "Einen Datensatz des Projekts in diese Umgebung holen",
          "ov.impb": "⤓ Datensatz importieren …", "ov.impb_t": "Datensatz des Projekts wählen und in eine Umgebung holen (auch eine neue)",
          "ov.imp_take": "Importieren …" },
    en: { "ov.title": "Overview", "ov.project": "Project", "ov.back": "◂ Overview", "ov.back_t": "Back to the overview",
          "ov.hint": "Click a box: open · drag a box: arrange · shared results on the left, own shares on the right",
          "ov.k_index": "Project", "ov.index": "Project index", "ov.index_s": "Curated values, readable from every module",
          "ov.k_share": "Shared with this module", "ov.k_own": "Shared", "ov.open": "open", "ov.empty": "empty",
          "ov.new_q": "Name:", "ov.latest": "latest", "ov.from": "From", "ov.hist": "History …",
          "ov.ro": "Read-only: only the producing module ({m}) can change this share.",
          "ov.own_note": "Shared by this module; every hand-over is a new version.",
          "ov.own_wire": "This share comes from the connected environment.", "ov.to": "to",
          "ov.kind.tga.steps": "TGA steps", "ov.kind.ftir.peaks": "FTIR bands", "ov.kind.chem.values": "Values",
          "ov.kind.chem.envvalues": "Values between environments", "ov.kind.data.table": "Dataset",
          "ov.kind.lab.envvalues": "Values between environments",
          "ov.con": "⇄ Connections", "ov.con_t": "What this environment gives to and gets from others, and what is shared with other modules",
          "ov.ch_values": "values", "ov.ch_value1": "value", "ov.live": "live", "ov.copy": "snapshot", "ov.live_t": "follows every change of the source",
          "ov.copy_t": "fixed state; bring it up to date by hand later", "ov.to_env": "To", "ov.go_live": "Connect live", "ov.go_copy": "Snapshot",
          "ov.already": "Already connected with", "ov.one": "Only one environment – add one with \"+ {w}\" on the overview, then connect.",
          "ov.l_hint": "Click: choose, change the mode or disconnect", "ov.l_head": "{a} → {b}", "ov.l_none": "{a} has nothing to share yet.",
          "ov.l_kept": "(gone, the last state stays)", "ov.apply": "Apply", "ov.connect": "Connect", "ov.unlink": "Disconnect",
          "ov.l_modes": "Live: B follows every change in A. Snapshot: B keeps the state of now.",
          "ov.done": "{n} × {c}: {a} → {b} ({m})", "ov.cm_out": "Gives to", "ov.cm_in": "Gets from", "ov.cm_new": "New connection to",
          "ov.cm_pick": "Choose …", "ov.cm_own": "Shared with other modules", "ov.cm_inc": "Shared with this module", "ov.cm_board": "Open the overview",
          "ov.cm_n": "Connections can also be drawn on the overview: from the dot on the right of a box to the other box.",
          "ov.mode": "Mode", "ov.edit": "Edit", "ov.shr_t": "Give to another environment", "ov.noenv": "Connections need the module to run with environments (through the hub).",
          "ov.gone": "This value is not available right now.", "ov.from_env": "from {e}",
          "ov.imp": "⤓ Import", "ov.imp_t": "Bring a dataset of the project into this environment",
          "ov.impb": "⤓ Import a dataset …", "ov.impb_t": "Choose a dataset of the project and bring it into an environment (or a new one)",
          "ov.imp_take": "Import …" },
  };

  function create(o) {
    const UI = g.LabUI, LB = g.LabBoard;
    if (!UI || !LB) return null;                              // veralteter Modulserver ohne die Skripte: Seite wie bisher
    UI.strings(T);
    const lang = () => (UI.lang() === "en" ? "en" : "de");
    const word = (n) => (o.word && o.word[lang()] ? o.word[lang()][n] : (lang() === "en" ? ["Environment", "Environments"] : ["Umgebung", "Umgebungen"])[n]);
    const t = (k, v) => UI.t(k, v);
    const kindLabel = (k) => { const s = t("ov.kind." + k); return s === "ov.kind." + k ? k : s; };
    const modName = (p) => (p && (MOD[p.module] || p.module)) || "?";
    if (!document.getElementById("lab-ov-css")) { const s = document.createElement("style"); s.id = "lab-ov-css"; s.textContent = CSS; document.head.appendChild(s); }

    const detail = (o.detail || [document.querySelector("main")]).filter(Boolean);
    detail.forEach((d) => d.classList.add("lov-hide"));
    const view = document.createElement("section");
    view.className = "lov"; view.hidden = true; view.setAttribute("aria-label", t("ov.title"));
    const canImp = !!(o.imports && g.LabImport);
    view.innerHTML = `<div class="lov-head"><b class="lov-title"></b><span class="small lov-proj"></span><span class="lov-hint"></span>${canImp ? `<button type="button" class="lov-impb"></button>` : ""}</div><div class="lov-board"></div>`;
    detail[0].parentNode.insertBefore(view, detail[0]);
    const crumbs = document.createElement("nav");
    crumbs.className = "lov-crumbs"; crumbs.hidden = true; crumbs.setAttribute("aria-label", t("ov.title"));
    crumbs.innerHTML = `<button type="button" class="lov-back"></button><span class="lov-env"></span>${canImp ? `<button type="button" class="lov-imp"></button>` : ""}<button type="button" class="lov-con"></button>`;
    if (o.crumbs) o.crumbs.insertBefore(crumbs, o.crumbs.firstChild); else detail[0].insertBefore(crumbs, detail[0].firstChild);
    crumbs.querySelector(".lov-back").addEventListener("click", () => showBoard());
    crumbs.querySelector(".lov-con").addEventListener("click", (e) => connMenu(e.currentTarget));
    if (canImp) {
      crumbs.querySelector(".lov-imp").addEventListener("click", () => importDataset());
      view.querySelector(".lov-impb").addEventListener("click", () => importDataset({ board: true }));
    }

    const st = { ok: false, b: null, data: { pos: {}, links: [] }, shares: { incoming: [], own: [], envvalues: [] }, view: "detail", saveT: 0, pubT: 0, syncT: 0, loaded: false };
    const E = () => (o.envs ? o.envs() : g.ENVS);
    const info = () => { const e = E(); return (e && e.info) || { envs: [], active: "", project: { name: "" } }; };
    const envName = (id) => { const e = info().envs.find((x) => "env:" + x.id === id); return e ? e.name : String(id).replace(/^env:/, ""); };
    const boxEl = (id) => [...view.querySelectorAll("[data-box]")].find((x) => x.dataset.box === id);

    // ---------------------------------------------------------------- Verbindungen zwischen Umgebungen
    const CH = [];
    if (o.values) CH.push(valuesChannel(o.values));
    for (const c of o.channels || []) if (c && c.kind) CH.push(c);
    const chan = (k) => CH.find((c) => c.kind === k);
    const chLinks = (pred) => st.data.links.filter((l) => chan(l.kind) && pred(l));
    const meBox = () => "env:" + info().active;
    const baseKey = (c, k) => (c && c.baseKey ? c.baseKey(k) : k);
    const keyText = (c, k) => (c && c.keyLabel ? c.keyLabel(k) : k);
    const byLabel = (c, k) => !!(c && c.keyLabel) || String(k).length > 24;      // Datensätze u. ä.: Titel statt ID zeigen
    const modeTxt = (l) => (l.mode === "copy" ? t("ov.copy") + (l.version ? " v" + l.version : "") : t("ov.live"));
    const ready = () => !!(E() && E().ready);

    function valuesChannel(v) {
      const num = (x) => Number(String(x ?? "").replace(",", ".").replace("−", "-"));
      const fmt = (x) => { const n = num(x); if (!Number.isFinite(n)) return String(x ?? ""); const s = String(+n.toPrecision(8)); return lang() === "de" ? s.replace(".", ",") : s; };
      const cat = (envId) => {
        if (envId === info().active) { try { return v.catalogue() || []; } catch (e) { return []; } }
        const e = info().envs.find((x) => x.id === envId);
        return e && e.summary && Array.isArray(e.summary.values) ? e.summary.values : [];
      };
      // Freigabe der Quellumgebung neu veröffentlichen: alle Werte, die eine ihrer Verbindungen nennt (plus `extra`);
      // fehlt ein Wert gerade, bleibt der zuletzt geteilte stehen
      async function publish(envId, extra) {
        const keys = new Set(extra || []);
        chLinks((l) => l.kind === "env.values" && l.from === "env:" + envId).forEach((l) => (l.keys || []).forEach((k) => keys.add(k)));
        if (!keys.size) return null;
        const items = cat(envId).filter((x) => x && keys.has(x.sym)).map(({ sym, label, value, unit, kind }) => ({ sym, label, value, unit, kind }));
        const have = new Set(items.map((x) => x.sym));
        if (items.length < keys.size) {
          const sh = (st.shares.envvalues || []).find((s) => s.producer && s.producer.module === o.module && s.producer.env === envId);
          if (sh) {
            const last = await o.api("api/env/share", { id: sh.id });
            for (const x of (last && last.outputs) || []) if (keys.has(x.key) && !have.has(x.key))
              items.push({ sym: x.key, label: x.label, value: x.quantity.value, unit: x.quantity.unit, kind: (x.conditions || {}).kind || "" });
          }
        }
        const j = await o.api("api/env/envvalues", { env: envId, items, module_version: v.version || "" });
        if (!j || j.error) throw new Error((j && j.error) || "?");
        const list = st.shares.envvalues = st.shares.envvalues || [];
        const i = list.findIndex((s) => s.id === j.id);
        if (i >= 0) list[i].latest = Math.max(list[i].latest || 0, j.version);
        else list.push({ id: j.id, kind: j.kind, title: j.title, latest: j.version, producer: j.producer });
        return j;
      }
      return {
        kind: "env.values", label: (n) => t(n === 1 ? "ov.ch_value1" : "ov.ch_values"),
        offers: async (envId) => cat(envId).filter((x) => x && x.sym && Number.isFinite(num(x.value)))
          .map((x) => ({ key: x.sym, label: x.label || x.sym, text: `${fmt(x.value)}${x.unit ? " " + x.unit : ""}` })),
        link: async (envId, keys, mode) => { const j = await publish(envId, keys); return j ? { share: j.id, version: mode === "copy" ? j.version : undefined } : {}; },
        republish: async (envId) => { await publish(envId); },
        apply: async (links) => {
          const rows = [];
          for (const l of links) {
            if (!l.share) continue;
            const env = await o.api("api/env/share", { id: l.share, ...(l.mode === "copy" && l.version ? { version: l.version } : {}) });
            if (!env || env.error) { if (env && env.error) o.toast(env.error, true); continue; }
            const outs = Object.fromEntries((env.outputs || []).map((x) => [x.key, x]));
            for (const key of l.keys || []) {
              const x = outs[key]; if (!x) continue;
              rows.push({ key, label: x.label || key, value: x.quantity.value, unit: x.quantity.unit || "", kind: (x.conditions || {}).kind || "",
                from: l.from.slice(4), from_name: envName(l.from), share: env.id, version: env.version, mode: l.mode || "live" });
            }
          }
          return v.apply(rows);
        },
      };
    }
    async function loadBoard() {
      const [b, s] = await Promise.all([o.api("api/env/board", {}), o.api("api/env/shares", {})]);
      if (b && !b.error) st.data = { pos: b.pos || {}, links: b.links || [] };
      if (s && !s.error) st.shares = { incoming: s.incoming || [], own: s.own || [], envvalues: s.envvalues || [] };
      st.loaded = true;
    }
    async function applyIn() {
      const me = meBox();
      for (const c of CH) { try { await c.apply(chLinks((l) => l.kind === c.kind && l.to === me)); } catch (e) { console.warn(e); } }
    }
    // nach dem Öffnen oder Wechseln einer Umgebung: verbundene Werte holen (gebündelt, falls mehrfach ausgelöst)
    function syncLinks() {
      if (!st.ok) return Promise.resolve();
      clearTimeout(st.syncT);
      return new Promise((res) => { st.syncT = setTimeout(async () => { try { await loadBoard(); if (CH.length) await applyIn(); } catch (e) { console.warn(e); } updateCon(); res(); }, 60); });
    }
    async function linkSave(c, from, to, keys, mode, quiet) {
      if (!c || from === to) return;
      let extra = {};
      try { extra = (c.link ? await c.link(from.slice(4), keys, mode) : {}) || {}; } catch (e) { o.toast(e.message || String(e), true); return; }
      let l = chLinks((x) => x.kind === c.kind && x.from === from && x.to === to)[0];
      if (!l) { l = { from, to, kind: c.kind, mode, keys: [] }; st.data.links.push(l); }
      l.keys = extra.keys || [...new Set(keys)]; l.mode = mode;
      if (extra.share) l.share = extra.share; else delete l.share;
      if (mode === "copy" && extra.version) l.version = extra.version; else delete l.version;
      saveBoard();
      o.toast(t("ov.done", { n: keys.length, c: c.label(keys.length), a: envName(from), b: envName(to), m: modeTxt(l) }));
      if (!quiet) await afterLinks(to);
    }
    async function unlink(l, quiet) {
      if (!l) return;
      st.data.links = st.data.links.filter((x) => x !== l);
      saveBoard();
      if (!quiet) await afterLinks(l.to);
    }
    async function afterLinks(to) {
      if (to === meBox()) await applyIn();
      if (st.view === "board") render();
      updateCon();
    }
    // A → B: was B von A bekommt (alle Kanäle), Art, lösen
    async function linkPopover(anchor, from, to) {
      const secs = [];
      for (const c of CH) {
        const l = chLinks((x) => x.kind === c.kind && x.from === from && x.to === to)[0];
        const have = new Set(((l && l.keys) || []).map((k) => baseKey(c, k)));
        let offers = [];
        try { offers = (await c.offers(from.slice(4))) || []; } catch (e) { offers = []; }
        const keys = new Set(offers.map((x) => x.key));
        for (const k of have) if (!keys.has(k)) offers.push({ key: k, label: t("ov.l_kept"), text: "" });
        secs.push({ c, ci: CH.indexOf(c), l, have, offers });
      }
      const anyL = secs.some((s) => s.l), anyO = secs.some((s) => s.offers.length);
      const m0 = (secs.find((s) => s.l) || {}).l;
      const mode0 = m0 && m0.mode === "copy" ? "copy" : "live";
      const html = `<div class="lov-pop"><b>${esc(t("ov.l_head", { a: envName(from), b: envName(to) }))}</b>
        ${anyO ? `<div class="lov-scroll">${secs.filter((s) => s.offers.length).map((s) => `${CH.length > 1 ? `<div class="lov-sec">${esc(s.c.label())}</div>` : ""}<table>${s.offers.map((x, i) =>
          `<tr><td><input type="checkbox" data-lk="${s.ci}|${i}"${s.have.has(x.key) ? " checked" : ""} aria-label="${esc(x.label)}"></td><td class="k"><code>${esc(byLabel(s.c, x.key) ? x.label : x.key)}</code></td><td>${esc(x.text || "")}</td><td class="small">${esc(byLabel(s.c, x.key) ? "" : x.label)}</td></tr>`).join("")}</table>`).join("")}</div>`
          : `<div class="small" style="margin-top:6px">${esc(t("ov.l_none", { a: envName(from) }))}</div>`}
        <div class="row"><label title="${esc(t("ov.live_t"))}"><input type="radio" name="lovm" value="live"${mode0 === "live" ? " checked" : ""}> ${esc(t("ov.live"))}</label><label title="${esc(t("ov.copy_t"))}"><input type="radio" name="lovm" value="copy"${mode0 === "copy" ? " checked" : ""}> ${esc(t("ov.copy"))}</label></div>
        <div class="row">${anyO ? `<button type="button" class="primary" data-lsave>${esc(t(anyL ? "ov.apply" : "ov.connect"))}</button>` : ""}${anyL ? `<button type="button" data-lrm>${esc(t("ov.unlink"))}</button>` : ""}</div>
        <div class="small" style="margin-top:4px">${esc(t("ov.l_modes"))}</div></div>`;
      const p = UI.popover(anchor, html);
      p.addEventListener("click", async (e) => {
        if (e.target.closest("[data-lrm]")) { UI.closePop(); for (const s of secs) if (s.l) await unlink(s.l, true); await afterLinks(to); return; }
        if (!e.target.closest("[data-lsave]")) return;
        const mode = p.querySelector('input[name="lovm"]:checked').value;
        const pick = secs.map((s) => ({ s, keys: s.offers.filter((_, i) => { const cb = p.querySelector(`[data-lk="${s.ci}|${i}"]`); return cb && cb.checked; }).map((x) => x.key) }));
        UI.closePop();
        for (const { s, keys } of pick) {
          if (!keys.length) { if (s.l) await unlink(s.l, true); continue; }
          await linkSave(s.c, from, to, keys, mode, true);
        }
        await afterLinks(to);
      });
    }
    // ⇄ an einem Ergebnis der offenen Umgebung
    function share(anchor, key, kind = "env.values") {
      const c = chan(kind);
      if (!st.ok || !c) return o.toast(t("ov.noenv"), true);
      const me = meBox(), others = info().envs.filter((e) => "env:" + e.id !== me);
      Promise.resolve(c.offers(info().active)).then((offers) => {
        const it = (offers || []).find((x) => x.key === key);
        if (!it) return o.toast(t("ov.gone"), true);
        const already = chLinks((l) => l.kind === kind && l.from === me && (l.keys || []).some((k) => baseKey(c, k) === key));
        const html = `<div class="lov-pop"><b>${esc(byLabel(c, it.key) ? it.label : it.key)}${it.text ? (c.keyLabel ? " · " : " = ") + esc(it.text) : ""}</b><div class="small">${esc(byLabel(c, it.key) ? "" : it.label)}</div>
          ${others.length ? `<div class="row"><label>${esc(t("ov.to_env"))} <select data-to>${others.map((e) => `<option value="env:${esc(e.id)}">${esc(e.name)}</option>`).join("")}</select></label></div>
            <div class="row"><button type="button" class="primary" data-go="live" title="${esc(t("ov.live_t"))}">${esc(t("ov.go_live"))}</button><button type="button" data-go="copy" title="${esc(t("ov.copy_t"))}">${esc(t("ov.go_copy"))}</button></div>`
            : `<div class="small" style="margin-top:6px">${esc(t("ov.one", { w: word(0) }))}</div>`}
          ${already.length ? `<div class="small" style="margin-top:6px">${esc(t("ov.already"))}: ${already.map((l) => esc(envName(l.to)) + " (" + esc(modeTxt(l)) + ")").join(", ")}</div>` : ""}</div>`;
        const p = UI.popover(anchor, html);
        p.addEventListener("click", async (e) => {
          const b = e.target.closest("[data-go]"); if (!b) return;
          const to = p.querySelector("[data-to]").value;
          UI.closePop();
          const l = chLinks((x) => x.kind === kind && x.from === me && x.to === to)[0];
          await linkSave(c, me, to, [...new Set([...((l && l.keys) || []).map((k) => baseKey(c, k)), key])], b.dataset.go);
        });
      });
    }
    const shareButton = (key, kind) => (CH.length && ready() && info().envs.length > 1
      ? `<button type="button" class="lov-shr" data-lov-shr="${esc(key)}"${kind ? ` data-lov-kind="${esc(kind)}"` : ""} title="${esc(t("ov.shr_t"))}" aria-label="${esc(t("ov.shr_t"))}: ${esc(key)}">⇄</button>` : "");
    document.addEventListener("click", (e) => {
      const b = e.target.closest && e.target.closest("[data-lov-shr]"); if (!b) return;
      e.preventDefault(); e.stopPropagation();
      share(b, b.dataset.lovShr, b.dataset.lovKind || "env.values");
    }, true);
    // „⇄ Verbindungen“: was diese Umgebung liefert und bekommt, Freigaben an andere Module und an dieses Modul
    async function connMenu(anchor) {
      if (!st.ok) return o.toast(t("ov.noenv"), true);
      await loadBoard();
      const me = meBox(), out = chLinks((l) => l.from === me), inn = chLinks((l) => l.to === me);
      const others = info().envs.filter((e) => "env:" + e.id !== me);
      const row = (l, dir) => {
        const i = st.data.links.indexOf(l), c = chan(l.kind);
        return `<tr><td class="k">${dir === "out" ? "→ " + esc(envName(l.to)) : esc(envName(l.from)) + " →"}</td>
          <td>${(l.keys || []).slice(0, 12).map((k) => `<code>${esc(keyText(c, k))}</code>`).join(" ")}${(l.keys || []).length > 12 ? " …" : ""}${CH.length > 1 ? ` <span class="small">(${esc(c.label())})</span>` : ""}</td>
          <td><select data-cm-mode="${i}" aria-label="${esc(t("ov.mode"))}"><option value="live"${l.mode !== "copy" ? " selected" : ""}>${esc(t("ov.live"))}</option><option value="copy"${l.mode === "copy" ? " selected" : ""}>${esc(t("ov.copy"))}${l.mode === "copy" && l.version ? " v" + l.version : ""}</option></select></td>
          <td class="k"><button type="button" data-cm-edit="${i}" title="${esc(t("ov.edit"))}">…</button><button type="button" data-cm-rm="${i}" title="${esc(t("ov.unlink"))}" aria-label="${esc(t("ov.unlink"))}">✕</button></td></tr>`;
      };
      const own = st.shares.own || [], inc = st.shares.incoming || [];
      const html = `<div class="lov-pop"><b>${esc(t("ov.con").replace(/^⇄\s*/, ""))} · ${esc(envName(me))}</b>
        ${CH.length ? `<div class="lov-sec">${esc(t("ov.cm_out"))}</div>${out.length ? `<table>${out.map((l) => row(l, "out")).join("")}</table>` : `<div class="small">–</div>`}
          <div class="lov-sec">${esc(t("ov.cm_in"))}</div>${inn.length ? `<table>${inn.map((l) => row(l, "in")).join("")}</table>` : `<div class="small">–</div>`}
          <div class="row">${others.length ? `<label>${esc(t("ov.cm_new"))} <select data-cm-to>${others.map((e) => `<option value="env:${esc(e.id)}">${esc(e.name)}</option>`).join("")}</select></label><button type="button" data-cm-add>${esc(t("ov.cm_pick"))}</button>`
            : `<span class="small">${esc(t("ov.one", { w: word(0) }))}</span>`}</div>
          <div class="small" style="margin-top:4px">${esc(t("ov.cm_n"))}</div>` : ""}
        <div class="lov-sec">${esc(t("ov.cm_own"))}</div>${own.length ? `<div class="lov-scroll" style="max-height:22vh"><table>${own.map((s) => `<tr><td>${esc(s.title || s.id)}</td><td class="small">${esc(kindLabel(s.kind))} · v${s.latest} → ${esc((s.recipients || []).map((r) => MOD[r] || r).join(", "))}</td></tr>`).join("")}</table></div>` : `<div class="small">–</div>`}
        <div class="lov-sec">${esc(t("ov.cm_inc"))}</div>${inc.length ? `<div class="lov-scroll" style="max-height:22vh"><table>${inc.map((s, i) => { const act = o.incoming && o.incoming[s.kind];
          return `<tr><td>${esc(s.title || s.id)}</td><td class="small">${esc(kindLabel(s.kind))} · ${esc(modName(s.producer))} · v${s.latest}</td><td class="k">${act ? `<button type="button" data-cm-take="${i}">${esc(typeof act.label === "function" ? act.label() : act.label)}</button>` : ""}</td></tr>`; }).join("")}</table></div>` : `<div class="small">–</div>`}
        <div class="row"><button type="button" data-cm-board>${esc(t("ov.cm_board"))}</button></div></div>`;
      const p = UI.popover(anchor, html);
      p.addEventListener("change", async (e) => {
        const i = e.target.dataset.cmMode; if (i === undefined) return;
        const l = st.data.links[+i]; if (!l) return;
        UI.closePop();
        const c = chan(l.kind);
        await linkSave(c, l.from, l.to, (l.keys || []).map((k) => baseKey(c, k)), e.target.value);
      });
      p.addEventListener("click", async (e) => {
        const rm = e.target.closest("[data-cm-rm]"), ed = e.target.closest("[data-cm-edit]"), tk = e.target.closest("[data-cm-take]");
        if (rm) { UI.closePop(); return unlink(st.data.links[+rm.dataset.cmRm]); }
        if (ed) { const l = st.data.links[+ed.dataset.cmEdit]; UI.closePop(); if (l) linkPopover(anchor, l.from, l.to); return; }
        if (tk) { const s = inc[+tk.dataset.cmTake]; UI.closePop(); if (s) await o.incoming[s.kind].run(s); return; }
        if (e.target.closest("[data-cm-add]")) { const to = p.querySelector("[data-cm-to]").value; UI.closePop(); return linkPopover(anchor, me, to); }
        if (e.target.closest("[data-cm-board]")) { UI.closePop(); showBoard(); }
      });
    }
    function updateCon() {
      const b = crumbs.querySelector(".lov-con");
      b.hidden = !st.ok;
      const me = meBox(), n = st.loaded ? chLinks((l) => l.from === me || l.to === me).length : 0;
      b.innerHTML = esc(t("ov.con")) + (n ? `<span class="n">${n}</span>` : "");
      b.title = t("ov.con_t");
    }
    // Quellseite: nach Änderungen die eigenen Werte für ausgehende Verbindungen nachführen
    function changed() {
      if (!st.ok || !CH.some((c) => c.republish)) return;
      clearTimeout(st.pubT);
      st.pubT = setTimeout(async () => {
        if (!st.loaded) return;
        const me = meBox();
        for (const c of CH) if (c.republish && chLinks((l) => l.kind === c.kind && l.from === me).length) { try { await c.republish(info().active); } catch (e) { /* Wert fehlt gerade */ } }
      }, 1500);
    }

    function texts() {
      view.querySelector(".lov-title").textContent = t("ov.title");
      view.querySelector(".lov-hint").textContent = t("ov.hint");
      const i = info();
      view.querySelector(".lov-proj").textContent = i.project && i.project.name ? `${t("ov.project")}: ${i.project.name}` : "";
      const b = crumbs.querySelector(".lov-back"); b.textContent = t("ov.back"); b.title = t("ov.back_t");
      if (canImp) {
        const ib = crumbs.querySelector(".lov-imp"); ib.textContent = t("ov.imp"); ib.title = t("ov.imp_t"); ib.hidden = !st.ok;
        const bb = view.querySelector(".lov-impb"); bb.textContent = t("ov.impb"); bb.title = t("ov.impb_t");
      }
      const e = i.envs.find((x) => x.id === i.active);
      crumbs.querySelector(".lov-env").textContent = e ? e.name : "";
      updateCon();
    }
    function envHtml(e, active) {
      let h = "";
      if (o.envHtml) { try { h = o.envHtml(e, active); } catch (x) { h = ""; } }
      if (!h) {
        const sm = e.summary || {};
        const tags = Array.isArray(sm.tags) ? sm.tags.slice(0, 8) : [];
        h = (sm.title ? `<div class="lov-t">${esc(sm.title)}</div>` : `<div>${esc(t("ov.empty"))}</div>`)
          + (tags.length ? `<div class="lov-tags">${tags.map((x) => `<span>${esc(x)}</span>`).join("")}</div>` : "");
      }
      const inn = chLinks((l) => l.to === "env:" + e.id);
      if (inn.length) h += `<div class="lov-links">${inn.map((l) => `← ${esc(envName(l.from))}: ${(l.keys || []).length} ${esc(chan(l.kind).label((l.keys || []).length))}`).join("<br>")}</div>`;
      return h;
    }
    function boxes() {
      const i = info(), linkable = CH.length > 0 && i.envs.length > 1;
      const out = [{ id: "idx", col: 0, kind: t("ov.k_index"), title: t("ov.index"), sub: t("ov.index_s") }];
      for (const s of st.shares.incoming) out.push({ id: s.id, col: 0, kind: kindLabel(s.kind), title: s.title || s.id, cls: "share",
        sub: `${modName(s.producer)} · ${(s.producer && (s.producer.env_name || s.producer.env)) || ""} · v${s.latest}`, label: `${t("ov.k_share")}: ${s.title || s.id}` });
      for (const e of i.envs) out.push({ id: "env:" + e.id, col: 1, active: e.id === i.active, in: linkable, out: linkable,
        kind: word(0) + (e.id === i.active ? " · " + t("ov.open") : ""), title: e.name, html: envHtml(e, e.id === i.active), label: `${word(0)} ${e.name}`,
        plots: e.summary && Array.isArray(e.summary.plots) && e.summary.plots.length ? e.summary.plots : null });   // UI-18
      out.push({ id: "add:env", col: 1, cls: "add", float: true, title: "+ " + word(0), label: "+ " + word(0) });
      for (const s of st.shares.own) out.push({ id: s.id, col: 2, kind: t("ov.k_own") + " · " + kindLabel(s.kind), title: s.title || s.id, cls: "share",
        sub: `v${s.latest} → ${(s.recipients || []).map((r) => MOD[r] || r).join(", ")}`, label: `${t("ov.k_own")}: ${s.title || s.id}` });
      return out;
    }
    function links() {
      const ids = new Set(boxes().map((b) => b.id));
      const L = st.data.links.filter((l) => ids.has(l.from) && ids.has(l.to)).map((l) => (chan(l.kind) ? { ...l, mode: l.mode === "copy" ? "pin" : "live", _l: l } : l));
      for (const s of st.shares.own) if (s.producer && s.producer.env && ids.has("env:" + s.producer.env)) L.push({ from: "env:" + s.producer.env, to: s.id, mode: "own" });
      return L;
    }
    function saveBoard() {
      clearTimeout(st.saveT);
      st.saveT = setTimeout(async () => { const j = await o.api("api/env/board", { board: st.data }); if (j && j.error) o.toast(j.error, true); }, 400);
    }
    async function load() {
      const e0 = E(); if (e0 && e0.flush) await e0.flush();      // Kasten der offenen Umgebung zeigt den jetzigen Stand
      await loadBoard();
      const e = E(); if (e && e.refresh) await e.refresh();
    }
    function render() {
      if (!st.ok) return;
      texts();
      const el = view.querySelector(".lov-board");
      if (!st.b) st.b = LB.create(el, {
        boxes, pos: st.data.pos, links: links(),
        onOpen,
        onLink: (from, to) => {
          if (CH.length && String(from).startsWith("env:") && String(to).startsWith("env:") && from !== to) linkPopover(boxEl(to) || view, from, to);
        },
        onUnlink: (l) => {
          const x = (l && l._l) || l;
          if (x && chan(x.kind)) return linkPopover(boxEl(x.to) || view, x.from, x.to);
          if (l && l.mode === "own") o.toast(t("ov.own_wire"));
        },
        onMove: (pos) => { st.data.pos = pos; saveBoard(); },
        wireLabel: (l) => { const x = l._l || l, c = chan(x.kind); return c ? `${(x.keys || []).length} ${c.label((x.keys || []).length)}${x.mode === "copy" ? " · " + t("ov.copy") : ""}` : ""; },
        wireHint: (l) => (chan((l._l || l).kind) ? t("ov.l_hint") : l.mode === "own" ? t("ov.own_wire") : ""),
      });
      st.b.setLinks(links());
      st.b.render();
    }
    async function onOpen(box) {
      if (!box) return;
      const env = E();
      if (box.id === "idx") { if (o.index) o.index(); else if (g.LabIndex) g.LabIndex.browse(o.api, o.toast); return; }
      if (box.id === "add:env") {
        const name = prompt(`${word(0)} – ${t("ov.new_q")}`, "");
        if (name === null) return;
        await env.createNew(name.trim());
        return showDetail();
      }
      if (box.id.startsWith("env:")) {
        const id = box.id.slice(4);
        if (id !== info().active) await env.switchTo(id);
        return showDetail();
      }
      const own = st.shares.own.find((x) => x.id === box.id), s = own || st.shares.incoming.find((x) => x.id === box.id);
      if (!s) return;
      const act = !own && ((o.incoming && o.incoming[s.kind])
        || (canImp && s.kind === "data.table" ? { label: t("ov.imp_take"), run: (x) => importDataset({ board: true, select: x.id }) } : null));
      const html = `<div class="lov-pop"><b>${esc(s.title || s.id)}</b><div class="small">${esc(kindLabel(s.kind))} · ${esc(s.id)} · ${esc(t("ov.latest"))} v${s.latest}</div>
        <div class="small">${esc(t("ov.from"))}: ${esc(modName(s.producer))}${s.producer && s.producer.env_name ? " · " + esc(s.producer.env_name) : ""}${s.producer && s.producer.item_name ? " · " + esc(s.producer.item_name) : ""}${own ? ` · ${esc(t("ov.to"))} ${esc((s.recipients || []).map((r) => MOD[r] || r).join(", "))}` : ""}</div>
        <div class="small" style="margin-top:6px">${esc(own ? t("ov.own_note") : t("ov.ro", { m: modName(s.producer) }))}</div>
        <div class="row">${act ? `<button type="button" class="primary" data-ov-act>${esc(typeof act.label === "function" ? act.label() : act.label)}</button>` : ""}${g.LabIndex ? `<button type="button" data-ov-hist>${esc(t("ov.hist"))}</button>` : ""}</div></div>`;
      const p = UI.popover(boxEl(box.id) || view, html);
      p.addEventListener("click", async (e) => {
        if (e.target.closest("[data-ov-hist]")) { UI.closePop(); g.LabIndex.history(o.api, o.toast, { share: s.id, version: s.latest }); }
        if (e.target.closest("[data-ov-act]")) { UI.closePop(); await act.run(s); }
      });
    }
    // I-03: Datensatz importieren – aus der offenen Umgebung oder von der Übersicht (dann mit Ziel-Umgebung)
    async function importDataset(a = {}) {
      if (!canImp || !st.ok) return null;
      UI.closePop();
      const i = info(), board = !!a.board || st.view === "board";
      const pick = await g.LabImport.open({
        api: o.api, toast: o.toast, module: o.module, select: a.select, mode: a.mode, version: a.version,
        actions: o.imports.actions, check: o.imports.check,
        targets: board ? { envs: i.envs.map((e) => ({ id: e.id, name: e.name })), active: i.active, word: word(0) } : null,
      });
      if (!pick) return null;
      const env = E();
      try {
        if (pick.env && pick.env.create) await env.createNew(pick.env.create);
        else if (pick.env && pick.env.id && pick.env.id !== info().active) await env.switchTo(pick.env.id);
      } catch (e) { o.toast(e.message || String(e), true); return null; }
      if (st.view !== "detail") showDetail(); else texts();
      try { await o.imports.run(pick); } catch (e) { o.toast(e.message || String(e), true); }
      return pick;
    }
    function setView(v) {
      st.view = v;
      document.body.classList.toggle("lov-board", v === "board");
      view.hidden = v !== "board";
      crumbs.hidden = !st.ok || v === "board";
      if (o.onView) { try { o.onView(v); } catch (e) { console.warn(e); } }
    }
    async function showBoard() {
      if (!st.ok) return;
      UI.closePop();
      await load();
      setView("board");
      history.replaceState(null, "", "#uebersicht");
      render();
      view.querySelector(".lab-box.active")?.focus({ preventScroll: true });
    }
    function showDetail() {
      setView("detail");
      texts();
      if (!st.ok) return;
      if (location.hash === "#uebersicht") history.pushState(null, "", "#umgebung");   // Zurück-Taste: wieder Übersicht
      else history.replaceState(null, "", "#umgebung");
      syncLinks();
    }
    function start() {
      const e = E();
      st.ok = !!(e && e.ready);
      updateCon();
      if (!st.ok) { setView("detail"); return; }
      if (location.hash === "#umgebung") showDetail(); else showBoard();
    }
    g.addEventListener("hashchange", () => {
      if (!st.ok) return;
      if (location.hash === "#uebersicht" && st.view !== "board") showBoard();
      else if (location.hash === "#umgebung" && st.view !== "detail") showDetail();
    });
    if (UI.onLang) UI.onLang(() => { texts(); if (st.view === "board") render(); });
    // sync(): nach einem Wechsel über den alten Umgebungsdialog den Namen in der Brotkrume nachführen und die
    // verbundenen Werte der neuen Umgebung holen
    return {
      start, showBoard, showDetail, render, changed, share, shareButton, connMenu, importDataset,
      sync: () => { texts(); if (st.ok) syncLinks(); },
      links: () => chLinks(() => true).map((l) => ({ ...l })),
      get view() { return st.view; }, get ok() { return st.ok; },
    };
  }

  // Wertekatalog für die Zusammenfassung einer Umgebung (Grenze des Servers: 48 KB je Zusammenfassung, Grafiken eingeschlossen)
  function summaryValues(list) {
    const v = (list || []).filter((x) => x && x.sym).slice(0, 80).map((x) => ({ sym: String(x.sym).slice(0, 60), label: String(x.label || x.sym).slice(0, 120),
      value: String(x.value ?? "").slice(0, 30), unit: String(x.unit || "").slice(0, 30), kind: String(x.kind || "").slice(0, 40) }));
    while (v.length && JSON.stringify(v).length > 24000) v.pop();
    return v;
  }

  // Module mit Messläufen und eigenen Gleichungen (TGA, FTIR, Zugversuch): Kennwerte (variables des Servers) und
  // Gleichungsergebnisse aller Läufe als Wertekatalog. Lauf 1 heisst wie die Variable (L1, res), weitere Läufe tragen
  // ihre Nummer (L1_2) – die Namen bleiben stabil, solange die Reihenfolge der Läufe gleich bleibt.
  // runs: [{name, vars: [{name, value, unit, label, ext?}], eqs: [{sym, value, unit, label, error?}]}]
  function runsCatalogue(runs) {
    const out = [], many = (runs || []).length > 1, ok = (x) => x != null && x !== "" && Number.isFinite(+x);
    (runs || []).forEach((r, i) => {
      const sfx = i ? "_" + (i + 1) : "", pre = many ? (r.name || "#" + (i + 1)) + ": " : "", seen = new Set();
      for (const v of r.vars || []) {
        if (!v || v.ext || !v.name || !ok(v.value)) continue;           // übernommene Werte nicht weiterreichen
        const sym = String(v.name).slice(0, 21) + sfx; seen.add(sym);
        out.push({ sym, label: pre + (v.label || v.name), value: +v.value, unit: v.unit || "", kind: "" });
      }
      for (const e of r.eqs || []) {
        if (!e || e.error || !e.sym || !ok(e.value)) continue;
        const sym = String(e.sym).slice(0, 21) + sfx; if (seen.has(sym)) continue;
        out.push({ sym, label: pre + (e.label || e.sym), value: +e.value, unit: e.unit || "", kind: "" });
      }
    });
    return out;
  }
  // Eingehende Werte (rows von values.apply) als Liste für den Server (ext_values); changed: anders als vorher
  function extValues(prev, rows) {
    const list = (rows || []).map((r) => ({ key: r.key, label: r.label, value: r.value, unit: r.unit || "", from: r.from,
      from_name: r.from_name, mode: r.mode, version: r.version }));
    return { list, changed: JSON.stringify(list) !== JSON.stringify(prev || []) };
  }

  g.LabOverview = { create, summaryValues, runsCatalogue, extValues };
})(window);
