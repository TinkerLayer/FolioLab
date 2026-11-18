/* Gemeinsame UI-Bausteine der Module (UI-01). Ohne Abhängigkeiten; jede Seite bindet labui.js ein.
 *
 *  Sprache (Q24 = b: Deutsch, Englisch umschaltbar)
 *    LabUI.strings({de: {key: "…"}, en: {key: "…"}})   Texte der Seite anmelden (mehrfach möglich)
 *    LabUI.t("key", {n: 3})                             Text in der aktiven Sprache, {n} wird ersetzt
 *    <x data-i18n="key">  <x data-i18n-title="key">     LabUI.apply() setzt Text/Titel/Platzhalter
 *    LabUI.langSwitch(el)                               DE|EN-Umschalter; LabUI.onLang(fn) für eigenes Neuzeichnen
 *  Aufklappen (Fortschreitende Offenlegung)
 *    <details class="lab-fold" data-fold="id">           Zustand bleibt je Seite gemerkt (LabUI.folds(prefix))
 *  Details auf Klick
 *    LabUI.popover(anchor, html)                        schliesst bei Klick daneben oder Esc
 *  Aufgaben-Einstieg
 *    LabUI.tasks(el, [{id, label, hint, act}])          Liste „Was möchten Sie tun?“
 *  Status
 *    LabUI.chip("ok" | "warn" | "err" | "info" | "live", text)  → HTML
 *  Quelle / Methode / Herkunft
 *    LabUI.actions({source, method, history})           → Element mit kleinen Knöpfen; jeder öffnet ein Popover
 *                                                         (source/method: HTML-Text; history: async () => HTML)
 *  Ansichtseinstellungen (Sprache, aufgeklappte Abschnitte) liegen im localStorage; Arbeitsstand nie (A2).
 */
(function (g) {
  "use strict";
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* gesperrt */ } },
  };

  // ------------------------------------------------------------------ Stil (einmal, mit Rückfallfarben)
  const CSS = `
.lab-fold>summary{cursor:pointer;font-weight:600;list-style:none;display:flex;align-items:center;gap:6px;padding:4px 0}
.lab-fold>summary::-webkit-details-marker{display:none}
.lab-fold>summary::before{content:"▸";display:inline-block;width:1em;transition:transform .12s}
.lab-fold[open]>summary::before{transform:rotate(90deg)}
.lab-pop{position:absolute;z-index:60;max-width:min(420px,92vw);background:var(--panel,#fff);color:inherit;border:1px solid var(--line,#ccc);
  border-radius:8px;box-shadow:0 10px 28px rgba(0,0,0,.22);padding:10px 12px;font-size:13px;line-height:1.45}
.lab-tasks{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:6px}
.lab-tasks button{text-align:left;padding:8px 10px;border-radius:8px;border:1px solid var(--line,#ccc);background:var(--panel,#fff);cursor:pointer;font:inherit}
.lab-tasks button:hover,.lab-tasks button:focus-visible{border-color:var(--accent,#2a6fdb)}
.lab-tasks small{display:block;opacity:.75;margin-top:2px}
.lab-chip{display:inline-block;padding:1px 8px;border-radius:999px;font-size:11.5px;line-height:1.6;border:1px solid transparent;white-space:nowrap}
.lab-chip.ok{background:#e3f4e6;color:#1d6b2c}.lab-chip.warn{background:#fff3d6;color:#7a5200}
.lab-chip.err{background:#fde4e4;color:#9b1c1c}.lab-chip.info{background:#e6eefc;color:#1f4f9e}.lab-chip.live{background:#efe6fc;color:#5a2a9e}
.lab-actions{display:inline-flex;gap:4px;vertical-align:middle}
.lab-actions button{font-size:11.5px;padding:1px 7px;border-radius:6px;border:1px solid var(--line,#ccc);background:transparent;cursor:pointer;color:inherit}
.lab-lang{display:inline-flex;border:1px solid var(--line,#ccc);border-radius:6px;overflow:hidden}
.lab-lang button{border:0;background:transparent;padding:2px 8px;cursor:pointer;font:inherit;font-size:12px;color:inherit}
.lab-lang button[aria-pressed="true"]{background:var(--accent,#2a6fdb);color:#fff}
@media (prefers-color-scheme:dark){.lab-chip.ok{background:#1d3b24;color:#9be0aa}.lab-chip.warn{background:#43360f;color:#f3d27a}
  .lab-chip.err{background:#4a1d1d;color:#f3a3a3}.lab-chip.info{background:#1c2c4a;color:#a8c4f5}.lab-chip.live{background:#2f1f4a;color:#cdb2f5}}`;
  function ensureCss() {
    if (document.getElementById("lab-ui-css")) return;
    const s = document.createElement("style");
    s.id = "lab-ui-css";
    s.textContent = CSS;
    document.head.appendChild(s);
  }

  // ------------------------------------------------------------------ Sprache
  const LANG_KEY = "folio.lang";
  const S = { de: {}, en: {} };
  let lang = store.get(LANG_KEY, "de") === "en" ? "en" : "de";
  const listeners = [];
  function strings(tbl) { for (const l of ["de", "en"]) Object.assign(S[l], (tbl && tbl[l]) || {}); }
  function t(key, vars) {
    let s = S[lang][key] ?? S.de[key] ?? key;
    if (vars) s = s.replace(/\{(\w+)\}/g, (m, k) => (vars[k] !== undefined ? vars[k] : m));
    return s;
  }
  function apply(root = document) {
    root.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
    root.querySelectorAll("[data-i18n-title]").forEach((el) => { el.title = t(el.dataset.i18nTitle); });
    root.querySelectorAll("[data-i18n-placeholder]").forEach((el) => { el.placeholder = t(el.dataset.i18nPlaceholder); });
    root.querySelectorAll("[data-i18n-label]").forEach((el) => { el.setAttribute("aria-label", t(el.dataset.i18nLabel)); });
    document.documentElement.lang = lang;
  }
  function setLang(l) {
    lang = l === "en" ? "en" : "de";
    store.set(LANG_KEY, lang);
    apply();
    document.querySelectorAll(".lab-lang button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.lang === lang)));
    listeners.forEach((fn) => { try { fn(lang); } catch (e) { console.warn(e); } });
  }
  function langSwitch(el) {
    ensureCss();
    el.classList.add("lab-lang");
    el.setAttribute("role", "group");
    el.setAttribute("aria-label", "Sprache / Language");
    el.innerHTML = ["de", "en"].map((l) => `<button type="button" data-lang="${l}" aria-pressed="${l === lang}">${l.toUpperCase()}</button>`).join("");
    el.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => setLang(b.dataset.lang)));
    return el;
  }

  // ------------------------------------------------------------------ Aufklappen mit Gedächtnis
  function folds(prefix, root = document) {
    ensureCss();
    const key = `folio.${prefix}.folds`;
    const st = store.get(key, {});
    root.querySelectorAll("details[data-fold]").forEach((d) => {
      const id = d.dataset.fold;
      if (st[id] !== undefined) d.open = !!st[id];
      if (d._labFold) return;
      d._labFold = true;
      d.addEventListener("toggle", () => { const s2 = store.get(key, {}); s2[id] = d.open; store.set(key, s2); });
    });
  }

  // ------------------------------------------------------------------ Popover
  let openPop = null;
  function closePop() { if (openPop) { openPop.remove(); openPop = null; } }
  function popover(anchor, html) {
    ensureCss();
    closePop();
    const p = document.createElement("div");
    p.className = "lab-pop";
    p.setAttribute("role", "dialog");
    p.innerHTML = html;
    document.body.appendChild(p);
    // UI-14: im Sichtfenster platzieren (fixed): unten, wenn Platz ist; sonst nach oben, wenn dort mehr Platz ist;
    // die Höhe wird auf den verfügbaren Platz begrenzt und der Inhalt rollt. Nichts wird am Rand abgeschnitten.
    const r = anchor.getBoundingClientRect(), vw = document.documentElement.clientWidth, vh = window.innerHeight, M = 8, G = 6;
    p.style.position = "fixed";
    p.style.left = Math.max(M, Math.min(r.left, vw - p.offsetWidth - M)) + "px";
    const h = p.offsetHeight, below = vh - r.bottom - G - M, above = r.top - G - M;
    if (h > below && above > below) {
      const mh = Math.max(80, above);
      p.style.maxHeight = mh + "px";
      p.style.top = Math.max(M, r.top - G - Math.min(h, mh)) + "px";
    } else {
      p.style.maxHeight = Math.max(80, below) + "px";
      p.style.top = Math.min(r.bottom + G, vh - M - 80) + "px";
    }
    p.style.overflow = "auto";
    p.style.overscrollBehavior = "contain";
    openPop = p;
    setTimeout(() => {
      const off = (ev) => { if (!p.contains(ev.target) && ev.target !== anchor) { closePop(); document.removeEventListener("mousedown", off); } };
      document.addEventListener("mousedown", off);
    }, 0);
    return p;
  }
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closePop(); });
  // fixed: beim Rollen ausserhalb oder bei Grössenänderung schliessen, damit es nicht vom Anker wegschwebt
  document.addEventListener("scroll", (e) => { if (openPop && !(e.target instanceof Node && openPop.contains(e.target))) closePop(); }, true);
  let popW = window.innerWidth;                             // Bildschirmtastatur ändert nur die Höhe: dann offen lassen
  window.addEventListener("resize", () => { if (window.innerWidth !== popW) { popW = window.innerWidth; closePop(); } });

  // ------------------------------------------------------------------ Aufgaben, Status, Aktionen
  function tasks(el, list) {
    ensureCss();
    el.classList.add("lab-tasks");
    el.innerHTML = list.map((x) => `<button type="button" data-task="${esc(x.id)}">${esc(x.label)}${x.hint ? `<small>${esc(x.hint)}</small>` : ""}</button>`).join("");
    el.querySelectorAll("[data-task]").forEach((b) => b.addEventListener("click", () => {
      const x = list.find((y) => y.id === b.dataset.task);
      if (x && x.act) x.act(b);
    }));
    return el;
  }
  const chip = (kind, text) => { ensureCss(); return `<span class="lab-chip ${esc(kind)}">${esc(text)}</span>`; };

  function actions(o) {
    ensureCss();
    const el = document.createElement("span");
    el.className = "lab-actions";
    const add = (key, label, fn) => {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = label;
      b.addEventListener("click", async () => popover(b, await fn()));
      el.appendChild(b);
    };
    if (o.source) add("source", t("ui.source"), async () => o.source);
    if (o.method) add("method", t("ui.method"), async () => o.method);
    if (o.history) add("history", t("ui.history"), async () => { try { return await o.history(); } catch (e) { return esc(e.message); } });
    return el;
  }

  strings({ de: { "ui.source": "Quelle", "ui.method": "Methode", "ui.history": "Herkunft" },
            en: { "ui.source": "Source", "ui.method": "Method", "ui.history": "History" } });

  g.LabUI = { strings, t, apply, setLang, lang: () => lang, onLang: (fn) => listeners.push(fn), langSwitch, folds, popover,
              closePop, tasks, chip, actions, esc };
})(window);
