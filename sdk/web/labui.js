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
 *  Grössen durch Ziehen, nach dem Aufbau der Seite: LabUI.sizes(prefix)
 *    <aside data-size-col="side" [data-size-edge="left|right"]>  Griff an der Kante; Breite als --lab-side auf dem
 *                                                         umgebenden Bereich (CSS: var(--lab-side, 380px))
 *    <div data-size-h="plot" [data-size-mode="max"]>      Griff an der Unterkante (height bzw. max-height)
 *    <dialog id="…"> und <div data-size-win="name">       rechte Kante, Unterkante oder Ecke ziehen
 *    LabUI.onResize(el, fn)                              Neuzeichnen bei Grössenänderung; Ereignis "lab-size" nach jedem Ziehen
 *    LabUI.resetSizes(prefix)                            alle gemerkten Grössen der Seite löschen
 *  Ansichtseinstellungen (Sprache, aufgeklappte Abschnitte, Grössen) liegen im localStorage; Arbeitsstand nie (A2).
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
.lab-cgrip{position:absolute;width:8px;margin-left:-4px;cursor:col-resize;z-index:30;touch-action:none;background:transparent}
.lab-hgrip{position:relative;height:8px;margin:-4px 0;cursor:row-resize;z-index:5;touch-action:none;background:transparent}
.lab-cgrip::after,.lab-hgrip::after{content:"";position:absolute;border-radius:2px;background:var(--accent,#2a6fdb);opacity:0;transition:opacity .12s}
.lab-cgrip::after{left:3px;width:2px;top:0;bottom:0}.lab-hgrip::after{top:3px;height:2px;left:0;right:0}
.lab-cgrip:hover::after,.lab-hgrip:hover::after,.lab-cgrip:focus-visible::after,.lab-hgrip:focus-visible::after,
.lab-cgrip.drag::after,.lab-hgrip.drag::after{opacity:.55}
.lab-cgrip:focus-visible,.lab-hgrip:focus-visible{outline:none}
.lab-hgrip[hidden],.lab-cgrip[hidden]{display:none}
body.lab-dragging,body.lab-dragging *{user-select:none!important}
body.lab-dragging iframe,body.lab-dragging canvas{pointer-events:none}
.lab-rs[open]{display:flex;flex-direction:column}
.lab-rs>form{flex:1 1 auto;min-height:0;display:flex;flex-direction:column}
.lab-rs>.body,.lab-rs>form>.body{flex:1 1 auto;min-height:0;max-height:none!important;overflow:auto}
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

  // ------------------------------------------------------------------ Grössen durch Ziehen an Kanten
  // Gespeichert wird je Seite (prefix) ein Anteil am Fenster bzw. am umgebenden Bereich, damit eine Einteilung auf
  // einem anderen Bildschirm verhältnisgleich bleibt. Doppelklick oder Pos1 auf einem Griff setzt zurück.
  const MIN_COL = 180, MIN_REST = 280, MIN_H = 48, STEP = 16;
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  // sichtbar? (auch in zugeklappten <details>, die offsetParent behalten)
  const shown = (el) => (el.checkVisibility ? el.checkVisibility() : !!el.offsetParent);
  function sizeStore(prefix) {
    const key = `folio.${prefix}.sizes`;
    return {
      get: (n) => store.get(key, {})[n],
      set: (n, v) => { const s = store.get(key, {}); if (v === null || v === undefined) delete s[n]; else s[n] = v; store.set(key, s); },
    };
  }
  const changed = (el) => {
    el.dispatchEvent(new CustomEvent("lab-size", { bubbles: true }));
    window.dispatchEvent(new Event("resize"));            // Seiten, die nur auf das Fenster hören, zeichnen neu
  };
  function dragging(on) { document.body.classList.toggle("lab-dragging", on); }
  function grip(cls, orient) {
    const d = document.createElement("div");
    d.className = cls;
    d.tabIndex = 0;
    d.setAttribute("role", "separator");
    d.setAttribute("aria-orientation", orient);
    d.title = t("ui.drag");
    return d;
  }
  // Ziehen mit Zeiger: onMove(dx, dy), onEnd()
  function drag(el, onStart, onMove, onEnd) {
    el.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      e.preventDefault();
      const x0 = e.clientX, y0 = e.clientY;
      onStart();
      el.setPointerCapture(e.pointerId);
      el.classList.add("drag");
      dragging(true);
      const mv = (ev) => onMove(ev.clientX - x0, ev.clientY - y0);
      const up = () => {
        el.classList.remove("drag");
        dragging(false);
        el.removeEventListener("pointermove", mv);
        el.removeEventListener("pointerup", up);
        el.removeEventListener("pointercancel", up);
        onEnd();
      };
      el.addEventListener("pointermove", mv);
      el.addEventListener("pointerup", up);
      el.addEventListener("pointercancel", up);
    });
  }
  function keys(el, onStep, onReset) {
    el.addEventListener("keydown", (e) => {
      const k = e.key, s = e.shiftKey ? 4 * STEP : STEP;
      if (k === "Home") { e.preventDefault(); onReset(); return; }
      const d = { ArrowLeft: -s, ArrowUp: -s, ArrowRight: s, ArrowDown: s }[k];
      if (d !== undefined) { e.preventDefault(); onStep(d); }
    });
    el.addEventListener("dblclick", onReset);
  }

  // Spalten: <aside data-size-col="side" [data-size-edge="left|right"]> in einem Grid/Flex-Bereich. Die Breite wird als
  // CSS-Variable --lab-<name> auf den Bereich gesetzt; die Seite nutzt sie, z. B. grid-template-columns: … var(--lab-side, 380px).
  function sizeCol(p, ss) {
    if (p._labSize) return;
    p._labSize = true;
    const c = p.parentElement, name = p.dataset.sizeCol, v = `--lab-${name}`;
    if (getComputedStyle(c).position === "static") c.style.position = "relative";
    const edge = p.dataset.sizeEdge || (p.nextElementSibling ? "right" : "left");
    const g = grip("lab-cgrip", "vertical");
    c.appendChild(g);
    const maxW = () => Math.max(MIN_COL, c.clientWidth - MIN_REST);
    const set = (w) => { c.style.setProperty(v, Math.round(clamp(w, MIN_COL, maxW())) + "px"); };
    const fromStore = () => { const f = ss.get(name); if (typeof f === "number" && f > 0) set(f * c.clientWidth); };
    const place = () => {
      const w = p.offsetWidth, cw = c.clientWidth;
      // eingeklappt, verborgen oder auf schmalem Bildschirm untereinander: kein Griff
      const off = !shown(p) || w < 60 || w > 0.9 * cw;
      g.hidden = off;
      if (off) return;
      g.style.left = (edge === "left" ? p.offsetLeft : p.offsetLeft + w) + "px";
      g.style.top = p.offsetTop + "px";
      g.style.height = p.offsetHeight + "px";
      g.setAttribute("aria-valuenow", String(Math.round(100 * w / cw)));
    };
    let w0 = 0;
    const save = () => { ss.set(name, p.offsetWidth / c.clientWidth); place(); changed(p); };
    drag(g, () => { w0 = p.offsetWidth; }, (dx) => { set(edge === "left" ? w0 - dx : w0 + dx); place(); }, save);
    keys(g, (d) => { set(p.offsetWidth + (edge === "left" ? -d : d)); save(); },
         () => { c.style.removeProperty(v); ss.set(name, null); place(); changed(p); });
    fromStore();
    // Bereich breiter/schmaler (Fenster, eingeklappte Nachbarn): gemerkten Anteil neu anwenden, Griff nachführen
    let cw0 = c.clientWidth;
    const upd = later(() => { if (c.clientWidth !== cw0) { cw0 = c.clientWidth; fromStore(); } place(); });
    const ro = new ResizeObserver(upd);
    ro.observe(p);
    ro.observe(c);
    placers.push(place);
    place();
  }
  // Griffe nach jedem Klick nachführen (Reiter, Aufklappen): sichtbar werdende Bereiche bekommen ihren Griff sofort
  const placers = [];
  const placeAll = () => placers.forEach((f) => { try { f(); } catch (e) { /* entfernt */ } });
  document.addEventListener("click", () => setTimeout(placeAll, 0), true);
  document.addEventListener("toggle", () => setTimeout(placeAll, 0), true);
  // einmal pro Takt ausführen (setTimeout statt requestAnimationFrame: läuft auch in verdeckten Fenstern)
  function later(fn) {
    let q = false;
    return () => { if (q) return; q = true; setTimeout(() => { q = false; fn(); }, 0); };
  }

  // Höhen: <div data-size-h="name" [data-size-mode="max"]>. Griff an der Unterkante; "max" setzt max-height (Tabellen,
  // Listen: kurzer Inhalt bleibt kurz), sonst height (Diagramme, Zeichenflächen).
  function sizeH(el, ss) {
    if (el._labSize) return;
    el._labSize = true;
    const name = el.dataset.sizeH, prop = el.dataset.sizeMode === "max" ? "maxHeight" : "height";
    const orig = el.style[prop];                            // eigener Wert der Seite (inline): beim Zurücksetzen wiederherstellen
    const g = grip("lab-hgrip", "horizontal");
    el.after(g);
    const set = (h) => { el.style[prop] = Math.round(clamp(h, MIN_H, 0.95 * window.innerHeight)) + "px"; };
    const fromStore = () => { const f = ss.get(name); if (typeof f === "number" && f > 0) set(f * window.innerHeight); };
    const place = () => { g.hidden = !shown(el) || el.offsetHeight === 0; };
    let h0 = 0;
    const save = () => { ss.set(name, el.getBoundingClientRect().height / window.innerHeight); changed(el); };
    drag(g, () => { h0 = el.getBoundingClientRect().height; }, (dx, dy) => set(h0 + dy), save);
    keys(g, (d) => { set(el.getBoundingClientRect().height + d); save(); },
         () => { el.style[prop] = orig; ss.set(name, null); changed(el); });
    fromStore();
    placers.push(place);
    new ResizeObserver(later(place)).observe(el);
    let vh0 = window.innerHeight;
    window.addEventListener("resize", later(() => { if (window.innerHeight !== vh0) { vh0 = window.innerHeight; fromStore(); } }));
    place();
  }

  // Fenster und Dialoge: rechte Kante, Unterkante oder Ecke ziehen (8 px breit). Gemerkt nach id bzw. data-size-win.
  const EDGE = 8;
  let winSS = null;
  // Dialoge werden oft für verschiedene Inhalte wiederverwendet: gemerkt nach id und Überschrift
  function winName(el) {
    if (el.dataset.sizeWin) return el.dataset.sizeWin;
    if (el.tagName !== "DIALOG") return "";
    const h = el.querySelector("h1, h2, h3, h4, .title, .head");
    const head = h ? h.textContent.trim().slice(0, 40) : "";
    return el.id || head ? `dlg-${el.id}:${head}` : "";
  }
  function winTarget(e) {
    const list = [...document.querySelectorAll("dialog[open], [data-size-win]")].filter((x) => x.tagName === "DIALOG" || shown(x));   // shown: auch position:fixed (offsetParent dort null)
    for (let i = list.length - 1; i >= 0; i--) {
      const el = list[i], r = el.getBoundingClientRect();
      if (!r.width) continue;
      const inY = e.clientY >= r.top && e.clientY <= r.bottom + EDGE, inX = e.clientX >= r.left && e.clientX <= r.right + EDGE;
      // Griffzone knapp ausserhalb der Kante: innen liegen oft Rollbalken, die das Ziehen sonst schlucken
      const right = inY && e.clientX >= r.right - 1 && e.clientX <= r.right + EDGE, bottom = inX && e.clientY >= r.bottom - 1 && e.clientY <= r.bottom + EDGE;
      if (right || bottom) return { el, right, bottom, r };
    }
    return null;
  }
  function winApply(el, w, h) {
    el.classList.add("lab-rs");
    if (w) { el.style.width = Math.round(clamp(w, 220, window.innerWidth - 16)) + "px"; el.style.maxWidth = "calc(100vw - 16px)"; }
    if (h) { el.style.height = Math.round(clamp(h, 120, window.innerHeight - 16)) + "px"; el.style.maxHeight = "calc(100vh - 16px)"; }
  }
  function winClear(el) {
    el.classList.remove("lab-rs");
    for (const k of ["width", "height", "maxWidth", "maxHeight"]) el.style[k] = "";
  }
  function winRestore(el) {
    const n = winName(el), f = n && winSS && winSS.get(n);
    if (f && f.w && f.h) winApply(el, f.w * window.innerWidth, f.h * window.innerHeight);
    else if (el.tagName === "DIALOG" && el.classList.contains("lab-rs")) winClear(el);   // anderer Inhalt: Grösse der Seite
  }
  function winReset(el) {
    winClear(el);
    const n = winName(el);
    if (n && winSS) winSS.set(n, null);
    changed(el);
  }
  // Ein rechts oder unten verankertes Fenster (right:/bottom:) würde beim Ziehen der rechten Kante nach links wachsen:
  // vor dem Ziehen an derselben Stelle links/oben verankern. Dialoge und Fenster mit transform bleiben, wie sie sind.
  function anchorLeftTop(el) {
    if (el.tagName === "DIALOG") return;
    const cs = getComputedStyle(el);
    if ((cs.position !== "absolute" && cs.position !== "fixed") || cs.transform !== "none") return;
    const fixed = cs.position === "fixed", b = el.getBoundingClientRect();
    el.style.left = (fixed ? b.left : el.offsetLeft) + "px";
    el.style.top = (fixed ? b.top : el.offsetTop) + "px";
    el.style.right = "auto";
    el.style.bottom = "auto";
  }
  function winInit(ss) {    if (winSS) { winSS = ss; return; }
    winSS = ss;
    let cur = null, lastDrag = 0;
    document.addEventListener("pointermove", (e) => {
      if (cur) return;
      const hit = winTarget(e);
      const c = hit ? (hit.right && hit.bottom ? "nwse-resize" : hit.right ? "ew-resize" : "ns-resize") : "";
      document.documentElement.style.cursor = c;
    }, true);
    document.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      const hit = winTarget(e);
      if (!hit) return;
      e.preventDefault();
      e.stopPropagation();
      const { el, right, bottom, r } = hit, x0 = e.clientX, y0 = e.clientY;
      cur = el;
      anchorLeftTop(el);
      dragging(true);
      // ein modaler Dialog bleibt mittig: die gezogene Kante folgt dem Zeiger, wenn die Grösse doppelt wächst
      const k = el.matches(":modal") ? 2 : 1;
      const mv = (ev) => winApply(el, right ? r.width + k * (ev.clientX - x0) : 0, bottom ? r.height + k * (ev.clientY - y0) : 0);
      const up = () => {
        cur = null;
        lastDrag = Date.now();
        dragging(false);
        document.documentElement.style.cursor = "";
        document.removeEventListener("pointermove", mv, true);
        document.removeEventListener("pointerup", up, true);
        const n = winName(el), b = el.getBoundingClientRect();
        if (n && winSS) winSS.set(n, { w: b.width / window.innerWidth, h: b.height / window.innerHeight });
        changed(el);
      };
      document.addEventListener("pointermove", mv, true);
      document.addEventListener("pointerup", up, true);
    }, true);
    // ein Klick auf die Kante soll einen modalen Dialog nicht schliessen (Seiten schliessen bei Klick auf den Hintergrund)
    document.addEventListener("click", (e) => { if (Date.now() - lastDrag < 400) { e.stopPropagation(); e.preventDefault(); } }, true);
    document.addEventListener("dblclick", (e) => { const hit = winTarget(e); if (hit) { e.preventDefault(); winReset(hit.el); } }, true);
    // geöffnete Dialoge bekommen ihre gemerkte Grösse
    new MutationObserver((ms) => {
      for (const m of ms) if (m.type === "attributes" && m.target.tagName === "DIALOG" && m.target.open) winRestore(m.target);
    }).observe(document.documentElement, { subtree: true, attributes: true, attributeFilter: ["open"] });
  }

  function sizes(prefix, root = document) {
    ensureCss();
    const ss = sizeStore(prefix);
    root.querySelectorAll("[data-size-col]").forEach((p) => sizeCol(p, ss));
    root.querySelectorAll("[data-size-h]").forEach((el) => sizeH(el, ss));
    winInit(ss);
    root.querySelectorAll("[data-size-win], dialog[open]").forEach(winRestore);
  }
  function resetSizes(prefix) {
    store.set(`folio.${prefix}.sizes`, {});
    location.reload();
  }
  // Neuzeichnen, wenn ein Element seine Grösse ändert (gebündelt auf einen Frame)
  function onResize(el, fn) {
    let w = el.clientWidth, h = el.clientHeight;
    const ro = new ResizeObserver(later(() => {
      if (el.clientWidth === w && el.clientHeight === h) return;
      w = el.clientWidth; h = el.clientHeight;
      if (w && h) fn();
    }));
    ro.observe(el);
    return ro;
  }

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

  strings({ de: { "ui.source": "Quelle", "ui.method": "Methode", "ui.history": "Herkunft",
                  "ui.drag": "Ziehen ändert die Grösse; Doppelklick setzt zurück", "ui.resetSizes": "Fenstergrössen zurücksetzen" },
            en: { "ui.source": "Source", "ui.method": "Method", "ui.history": "History",
                  "ui.drag": "Drag to resize; double-click resets", "ui.resetSizes": "Reset window sizes" } });

  g.LabUI = { strings, t, apply, setLang, lang: () => lang, onLang: (fn) => listeners.push(fn), langSwitch, folds, popover,
              closePop, tasks, chip, actions, esc, sizes, resetSizes, onResize };
})(window);
