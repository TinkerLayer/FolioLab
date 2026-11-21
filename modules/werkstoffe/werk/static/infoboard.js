/* Infotafel des Werkstoffe-Moduls: Werkstoffe auswählen, das Kompendium durchgehen, Inhalte anheften, auf einer freien
 * Fläche in Rahmen ordnen und mit den Quellen je Aussage in einen Bericht geben.
 *
 *   InfoBoard.init(host)     host: { api, L, esc, lang, toast, dialog, kpOpen, kpShow, kpEntry, figSpec, chartSpec, chartFamily }
 *   InfoBoard.sync()         nach einem Projekt- oder Umgebungswechsel: Tafeln des aktiven Projekts laden
 *   InfoBoard.decorateEntry / decorateList / chrome / relabel   Haken der Seite
 *
 * Der obere Teil (MODEL) rechnet nur mit Daten und läuft ohne DOM (Prüfung mit Node). Der Server (werk/infoboard.py) baut die
 * Pins mit Inhalt, Quellen und Fingerabdruck; hier werden sie nur angeordnet. */
(function (g) {
  "use strict";

  // ---------------------------------------------------------------- MODEL
  const GRID = 20, CARD_W = 260, WIDE_W = 340, FRAME_W = 640, FRAME_H = 420, MIN_FRAME_W = 200, MIN_FRAME_H = 140;
  const snap = (v) => Math.round(v / GRID) * GRID;
  const uid = (p) => p + Math.random().toString(16).slice(2, 10);
  const newBoard = (name) => ({ id: uid("b"), name: name || "Tafel 1", view: { x: 40, y: 40, z: 1 }, frames: [], cards: [] });
  function emptyDoc(name) { const b = newBoard(name); return { version: 1, rev: 0, active: b.id, boards: [b], selection: [] }; }
  const activeBoard = (doc) => doc.boards.find((b) => b.id === doc.active) || doc.boards[0];
  const overlaps = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
  const rect = (c) => ({ x: c.x, y: c.y, w: c.w || CARD_W, h: c.h || 90 });
  const centre = (c) => { const r = rect(c); return { x: r.x + r.w / 2, y: r.y + r.h / 2 }; };
  const inside = (p, f) => p.x >= f.x && p.x <= f.x + f.w && p.y >= f.y && p.y <= f.y + f.h;

  function freeSpot(board, w, h) {
    const occ = [...board.frames, ...board.cards.map(rect)];
    for (let y = 0; y < 12000; y += GRID * 2) for (let x = 0; x < 1800; x += GRID * 2) {
      const r = { x, y, w: w + GRID, h: h + GRID };
      if (!occ.some((o) => overlaps(r, o))) return { x, y };
    }
    return { x: 0, y: 0 };
  }
  const frameAt = (board, card) => { const p = centre(card); return [...board.frames].reverse().find((f) => inside(p, f)) || null; };
  function setFrame(board, card) { const f = frameAt(board, card); if (f) card.frame = f.id; else delete card.frame; return card; }
  function placeCard(board, pin, at) {
    const w = pin.w || (pin.kind === "figure" || pin.kind === "compare" ? WIDE_W : CARD_W), h = pin.h || (pin.kind === "figure" ? 260 : 96);
    const p = at || freeSpot(board, w, h);
    const c = { ...pin, x: snap(p.x), y: snap(p.y), w, h };
    board.cards.push(c);
    setFrame(board, c);
    return c;
  }
  function moveCards(board, ids, dx, dy) {
    const set = new Set(ids);
    for (const c of board.cards) if (set.has(c.id)) { c.x = snap(c.x + dx); c.y = snap(c.y + dy); setFrame(board, c); }
  }
  function addFrame(board, name, at) {
    const p = at || freeSpot(board, FRAME_W, FRAME_H);
    const f = { id: uid("f"), name: name || "", x: snap(p.x), y: snap(p.y), w: FRAME_W, h: FRAME_H };
    board.frames.push(f);
    for (const c of board.cards) if (!c.frame) setFrame(board, c);
    return f;
  }
  function moveFrame(board, id, dx, dy) {
    const f = board.frames.find((x) => x.id === id); if (!f) return;
    const ax = snap(f.x + dx) - f.x, ay = snap(f.y + dy) - f.y;
    f.x += ax; f.y += ay;
    for (const c of board.cards) if (c.frame === id) { c.x += ax; c.y += ay; }
  }
  function resizeFrame(board, id, w, h) {
    const f = board.frames.find((x) => x.id === id); if (!f) return;
    f.w = Math.max(MIN_FRAME_W, snap(w)); f.h = Math.max(MIN_FRAME_H, snap(h));
    for (const c of board.cards) if (c.frame === id || !c.frame) setFrame(board, c);
  }
  function reorderFrame(board, id, d) {
    const k = board.frames.findIndex((f) => f.id === id), n = k + d;
    if (k < 0 || n < 0 || n >= board.frames.length) return false;
    const [f] = board.frames.splice(k, 1); board.frames.splice(n, 0, f);
    return true;
  }
  function removeFrame(board, id) {
    board.frames = board.frames.filter((f) => f.id !== id);
    for (const c of board.cards) if (c.frame === id) delete c.frame;
  }
  function removeCards(board, ids) { const s = new Set(ids); board.cards = board.cards.filter((c) => !s.has(c.id)); }
  const reading = (a, b) => (Math.round(a.y / 60) - Math.round(b.y / 60)) || (a.x - b.x);
  /* Gleiche Reihenfolge wie infoboard.ordered: Rahmen der Reihe nach, darin Leserichtung, lose Karten zuletzt. */
  function exportOrder(board, frame) {
    const out = board.frames.filter((f) => !frame || f.id === frame).map((f) => ({ frame: f, cards: board.cards.filter((c) => c.frame === f.id).sort(reading) }));
    if (!frame) { const ids = new Set(board.frames.map((f) => f.id)), loose = board.cards.filter((c) => !ids.has(c.frame)).sort(reading); if (loose.length) out.push({ frame: null, cards: loose }); }
    return out;
  }
  const snapshot = (board) => ({ frames: board.frames.map((f) => ({ ...f })), cards: board.cards.map((c) => ({ ...c })) });
  function restore(board, s) { board.frames = s.frames.map((f) => ({ ...f })); board.cards = s.cards.map((c) => ({ ...c })); }
  function fitView(board, W, H) {
    const rs = [...board.frames, ...board.cards.map(rect)];
    if (!rs.length) return { x: 40, y: 40, z: 1 };
    const x0 = Math.min(...rs.map((r) => r.x)), y0 = Math.min(...rs.map((r) => r.y)), x1 = Math.max(...rs.map((r) => r.x + r.w)), y1 = Math.max(...rs.map((r) => r.y + r.h));
    const z = Math.max(0.2, Math.min(1.2, Math.min((W - 60) / Math.max(1, x1 - x0), (H - 60) / Math.max(1, y1 - y0))));
    return { x: Math.round((W - (x1 - x0) * z) / 2 - x0 * z), y: Math.round((H - (y1 - y0) * z) / 2 - y0 * z), z: +z.toFixed(3) };
  }
  const specKey = (s) => {
    if (!s) return "";
    if (s.kind === "figure") return s.fig === "chart" ? "figure:chart:" + JSON.stringify([s.req, s.view, s.limits]) : `figure:${s.fig}:${s.gef || s.mech}:${s.frame ?? ""}`;
    return s.kind === "compare" ? "compare:" + (s.materials || []).join(",") : `${s.kind}:${s.id}`;
  };
  const MODEL = { GRID, emptyDoc, newBoard, activeBoard, freeSpot, frameAt, placeCard, moveCards, addFrame, moveFrame, resizeFrame, reorderFrame, removeFrame, removeCards, exportOrder, snapshot, restore, fitView, specKey };

  // ---------------------------------------------------------------- Oberfläche
  const STYLE = `
#ibBtn { display: inline-flex; align-items: center; gap: 5px; white-space: nowrap; }
#ibBtn .n { font-size: 11px; color: var(--muted); }
#ibWin { position: fixed; left: 0; right: 0; bottom: 0; z-index: 30; display: flex; flex-direction: column; background: var(--bg); border-top: 1px solid var(--line); }
.ibbar { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; padding: 5px 10px; background: var(--panel); border-bottom: 1px solid var(--line); }
.ibbar select { width: auto; max-width: 200px; }
.ibbar .sp { flex: 1; }
.ibbar .z { min-width: 42px; text-align: center; font-size: 12px; color: var(--muted); font-variant-numeric: tabular-nums; }
.ibmenu { position: relative; }
.ibmenu > div { position: absolute; top: calc(100% + 3px); left: 0; z-index: 5; display: flex; flex-direction: column; min-width: 170px; padding: 4px; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; box-shadow: 0 8px 24px rgba(0,0,0,.18); }
.ibmenu > div button { border: 0; background: transparent; text-align: left; }
.ibmenu > div button:hover, .ibmenu > div button:focus-visible { background: var(--accent-soft); }
#ibCanvas { position: relative; flex: 1; min-height: 0; overflow: hidden; outline: none; cursor: grab; touch-action: none;
  background-color: var(--bg); background-image: radial-gradient(circle, color-mix(in srgb, var(--muted) 30%, transparent) 1px, transparent 1.2px); background-size: 20px 20px; }
#ibCanvas.pan { cursor: grabbing; }
#ibLayer { position: absolute; left: 0; top: 0; transform-origin: 0 0; }
.ibempty { position: absolute; inset: 0; display: grid; place-items: center; color: var(--muted); text-align: center; padding: 20px; pointer-events: none; }
.ibframe { position: absolute; border: 1.5px solid var(--line); border-radius: 10px; background: color-mix(in srgb, var(--panel) 45%, transparent); pointer-events: none; }
.ibframe.drop { border-color: var(--accent); background: var(--accent-soft); }
.ibframe:focus-within { border-color: var(--accent); }
.ibfh { position: absolute; left: 0; right: 0; top: 0; display: flex; align-items: center; gap: 5px; padding: 4px 6px 4px 8px; cursor: move; pointer-events: auto; border-radius: 9px 9px 0 0; outline: none; }
.ibfh:focus-visible { box-shadow: inset 0 0 0 2px var(--accent); }
.ibfh .no { flex: none; width: 18px; height: 18px; border-radius: 50%; display: grid; place-items: center; font-size: 11px; font-weight: 600; background: var(--accent); color: var(--accent-ink); }
.ibfh .nm { font-weight: 600; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ibfh input { flex: 1; min-width: 60px; padding: 1px 4px; }
.ibfh .acts { margin-left: auto; display: flex; gap: 2px; opacity: 0; }
.ibframe:hover .ibfh .acts, .ibfh:focus-within .acts, .ibfh:focus .acts { opacity: 1; }
.ibfh .acts button { padding: 0 6px; border-color: transparent; background: transparent; color: var(--muted); }
.ibres { position: absolute; right: 0; bottom: 0; width: 16px; height: 16px; cursor: nwse-resize; pointer-events: auto; background: linear-gradient(135deg, transparent 55%, var(--muted) 55%, var(--muted) 65%, transparent 65%, transparent 78%, var(--muted) 78%, var(--muted) 88%, transparent 88%); border-radius: 0 0 9px 0; opacity: .55; }
.ibcard { position: absolute; background: var(--panel); color: var(--ink); border: 1px solid var(--line); border-radius: 8px; box-shadow: 0 2px 7px rgba(0,0,0,.1); font-size: 12px; line-height: 1.35; cursor: move; outline: none; user-select: none; }
.ibcard:hover { border-color: var(--accent); }
.ibcard:focus-visible, .ibcard.sel { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent); }
.ibcard.note { background: var(--warn-bg); color: var(--warn-ink); }
.ibch { display: flex; align-items: baseline; gap: 5px; padding: 5px 4px 2px 8px; }
.ibch b { flex: 1; min-width: 0; font-size: 12.5px; font-weight: 600; overflow-wrap: anywhere; }
.ibch button { flex: none; border: 0; background: transparent; color: var(--muted); padding: 0 4px; font-size: 11px; }
.ibk { display: block; font-size: 10px; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); padding: 5px 8px 0; }
.ibcb { padding: 1px 8px 7px; overflow-wrap: anywhere; }
.ibcb p { margin: 0; display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical; overflow: hidden; }
.ibcb img { display: block; width: 100%; height: auto; border-radius: 4px; background: #fff; pointer-events: none; }
.ibcb textarea { display: block; width: 100%; min-height: 64px; font: inherit; background: transparent; color: inherit; border: 1px dashed currentColor; border-radius: 4px; resize: vertical; cursor: text; user-select: text; }
.ibtags { display: flex; flex-wrap: wrap; gap: 4px; padding: 0 8px 6px; }
.ibtag { font-size: 10.5px; padding: 0 5px; border-radius: 8px; border: 1px solid var(--line); color: var(--muted); white-space: nowrap; }
.ibtag.warn { color: var(--warn-ink); border-color: currentColor; }
.ibtag.chg { color: var(--err-ink); border-color: currentColor; }
.ibmore { border-top: 1px solid var(--line); padding: 6px 8px; cursor: default; user-select: text; max-height: 340px; overflow: auto; }
.ibmore p { margin: 0 0 4px; }
.ibmore ol { margin: 4px 0; padding-left: 16px; font-size: 11px; color: var(--muted); }
.ibmore table { width: 100%; border-collapse: collapse; font-size: 11px; }
.ibmore td, .ibmore th { border-bottom: 1px solid var(--line); padding: 1px 3px; text-align: left; }
.ibmore .row { margin-top: 6px; }
.ibp { border: 0; background: transparent; color: var(--muted); padding: 0 3px; margin-left: 3px; opacity: 0; vertical-align: -2px; line-height: 1; }
.ibp svg { display: inline-block; width: 12px; height: 12px; }
.ibp.on { opacity: 1; color: var(--accent); }
.ibp.on svg { fill: currentColor; }
.ibp:focus-visible, *:hover > .ibp, td:hover .ibp, tr:hover .ibp, h3:hover > .ibp, h4:hover > .ibp, summary:hover > .ibp { opacity: 1; }
.ibp:hover { color: var(--accent); }
.ibmedia { display: flex; gap: 6px; margin-top: 4px; }
.ibmedia button.on { color: var(--accent); border-color: var(--accent); }
.ibmedia button.on svg { fill: currentColor; }
#ibWalk { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; padding: 4px 10px; border-bottom: 1px solid var(--line); background: var(--soft); font-size: 12px; }
#ibWalk button { padding: 1px 8px; }
#ibWalk .t { flex: 1; min-width: 100px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ibrow { display: flex; align-items: stretch; }
.ibrow > button[data-kpid] { flex: 1; min-width: 0; }
#kpList .ibrow > .ibsel { flex: none; display: block; width: 22px; padding: 0; text-align: center; color: var(--muted); opacity: 0; }
#kpList .ibrow:hover > .ibsel, #kpList .ibsel:focus-visible, #kpList .ibsel.on { opacity: 1; }
#kpList .ibsel.on { color: var(--accent); font-weight: 700; }
#kpList .kpsub { display: flex; align-items: center; justify-content: space-between; }
#kpList .kpsub button { display: inline; width: auto; padding: 0 5px; font-size: 10.5px; opacity: 0; }
#kpList .kpsub:hover button, #kpList .kpsub button:focus-visible { opacity: 1; }
.ibexp ul { list-style: none; margin: 6px 0; padding: 0; }
.ibexp li { padding: 4px 0; border-bottom: 1px solid var(--line); }
.ibexp li label { display: flex; gap: 6px; align-items: baseline; margin: 0; color: var(--ink); font-size: 12.5px; }
.ibexp li small { display: block; color: var(--muted); font-size: 11.5px; margin-left: 22px; }
@media (hover: none) { .ibp, #kpList .ibrow > .ibsel, #kpList .kpsub button { opacity: .6; } }
@media (max-width: 700px) { .ibbar .sp { display: none; } }
`;
  const PIN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 3h6l-1 7 4 4H6l4-4z"/><path d="M12 14v7"/></svg>';
  const U = { H: null, doc: null, project: null, rev: 0, dirty: false, saving: null, t: 0, open: false, sel: new Set(), more: new Set(), undo: [], states: {}, drag: null, walk: [], walkKey: "", root: null, canvas: null, layer: null, menu: false, editFrame: null };
  const $ = (s, el) => (el || document).querySelector(s);
  const $$ = (s, el) => [...(el || document).querySelectorAll(s)];
  const L = (de, en) => U.H.L(de, en);
  const esc = (s) => U.H.esc(s);
  const lang = () => U.H.lang();
  const board = () => activeBoard(U.doc);
  const cont = (c) => (c.content && (c.content[lang()] || c.content.de)) || {};
  const KIND = () => ({ entry: L("Eintrag", "Entry"), section: L("Abschnitt", "Section"), statement: L("Aussage", "Statement"), value: L("Kennwert", "Property"), figure: L("Abbildung", "Figure"), compare: L("Vergleich", "Comparison"), note: L("Eigene Notiz", "Own note") });
  const count = () => (U.doc ? U.doc.boards.reduce((n, b) => n + b.cards.length, 0) : 0);

  // ---- Laden und Speichern (je Projekt)
  function dirty() { U.dirty = true; clearTimeout(U.t); U.t = setTimeout(flush, 250); badge(); }
  async function flush() {
    clearTimeout(U.t);
    if (U.saving) { await U.saving; }
    if (!U.dirty || !U.project || !U.doc) return;
    U.dirty = false;
    const project = U.project;
    U.saving = (async () => {
      const j = await U.H.api("api/infoboard/save", { project, rev: U.rev, doc: U.doc });
      if (project !== U.project) return;
      if (j.conflict) { U.doc = j.doc; U.rev = j.doc.rev || 0; U.undo = []; U.H.toast(L("Die Tafel wurde in einem anderen Fenster geändert; ihr Stand ist geladen.", "The board was changed in another window; its state is loaded."), true); render(); }
      else if (j.error) { U.dirty = true; U.H.toast(L("Tafel nicht gespeichert: ", "Board not saved: ") + j.error, true); }
      else U.rev = j.rev;
    })();
    try { await U.saving; } finally { U.saving = null; }
    if (U.dirty) { clearTimeout(U.t); U.t = setTimeout(flush, 250); }
  }
  async function sync() {
    if (!U.H) return;
    const j = await U.H.api("api/infoboard/load", {});
    if (!j || j.error) { if (j && j._status !== 404) U.H.toast(j.error, true); return; }
    if (j.project === U.project && U.doc) { if (U.open) checkStates(); return; }
    if (U.doc) await flush();
    U.project = j.project; U.doc = j.doc; U.rev = j.doc.rev || 0; U.undo = []; U.sel.clear(); U.more.clear(); U.states = {}; U.walk = []; U.walkKey = "";
    badge(); walkLoad();
    const box = $("#kpEntry"), e = U.H.kpEntry();
    if (box && e && !$("[data-ibk]", box)) decorateEntry(box, e); else redecorate();
    decorateList($("#kpList"));
    chrome();
    if (U.open) { render(); checkStates(); }
  }
  async function checkStates() {
    const pins = U.doc ? U.doc.boards.flatMap((b) => b.cards).filter((c) => c.kind !== "note") : [];
    if (!pins.length) { U.states = {}; return; }
    const j = await U.H.api("api/infoboard/state", { pins });
    if (j && j.states) { U.states = j.states; const a = document.activeElement; if (U.open && !(a && a.matches && a.matches("textarea,input"))) renderLayer(); }
  }
  function badge() {
    const b = $("#ibBtn"); if (!b) return;
    const n = count(), el = $(".n", b);
    if (el) el.textContent = n ? String(n) : "";
  }

  // ---- Auswahl und Weg durch das Kompendium
  const selection = () => (U.doc ? U.doc.selection : []);
  const isSel = (id) => selection().includes(id);
  function toggle(id, on) {
    if (!U.doc) return;
    const s = U.doc.selection, k = s.indexOf(id);
    if (on !== false && k < 0) s.push(id); else if (on !== true && k >= 0) s.splice(k, 1);
    afterSelection();
  }
  function selectMany(ids) {
    if (!U.doc || !ids.length) return;
    const all = ids.every(isSel);
    U.doc.selection = all ? selection().filter((x) => !ids.includes(x)) : [...new Set([...selection(), ...ids])];
    U.H.toast(all ? L(`${ids.length} Werkstoffe aus der Reihe genommen.`, `${ids.length} materials removed from the series.`) : L(`${ids.length} Werkstoffe in der Reihe.`, `${ids.length} materials in the series.`));
    afterSelection();
  }
  function afterSelection() { U.walkKey = ""; dirty(); walkLoad(); decorateList($("#kpList")); chrome(); }
  async function walkLoad() {
    const ids = selection(), key = lang() + "|" + ids.join(",");
    if (key === U.walkKey) return walkRender();
    U.walkKey = key;
    if (!ids.length) { U.walk = []; return walkRender(); }
    const j = await U.H.api("api/infoboard/walk", { ids, lang: lang() });
    if (key === U.walkKey && j.items) { U.walk = j.items; walkRender(); }
  }
  function walkRender() {
    const win = $("#kpWin"); if (!win) return;
    let w = $("#ibWalk");
    if (!selection().length) { if (w) w.remove(); return; }
    if (!w) { w = document.createElement("div"); w.id = "ibWalk"; win.insertBefore(w, $(".kpbody", win)); }
    const cur = (U.H.kpEntry() || {}).id || "", k = U.walk.findIndex((x) => x.id === cur), x = U.walk[k];
    const via = x && x.via ? ` · ${L("zu", "for")} ${x.via}` : "";
    w.innerHTML = `<button type="button" data-w="-1" aria-label="${esc(L("Vorheriger Eintrag der Reihe (Alt+←)", "Previous entry of the series (Alt+←)"))}" title="Alt+←">‹</button>` +
      `<span class="small">${k >= 0 ? k + 1 : "–"} / ${U.walk.length}</span><button type="button" data-w="1" aria-label="${esc(L("Nächster Eintrag der Reihe (Alt+→)", "Next entry of the series (Alt+→)"))}" title="Alt+→">›</button>` +
      `<span class="t" title="${esc((x ? x.title : "") + via)}">${x ? esc(x.title + via) : esc(L("Reihe durchgehen", "Walk through the series"))}</span>` +
      `<span class="small">${esc(L("Reihe", "Series"))}: ${selection().length}</span>` +
      `<button type="button" data-w="pinall" title="${esc(L("Die Einträge aller Werkstoffe der Reihe anheften", "Pin the entries of all materials in the series"))}">${esc(L("Alle anheften", "Pin all"))}</button>` +
      `<button type="button" data-w="clear" title="${esc(L("Reihe leeren", "Clear the series"))}">✕</button>`;
  }
  function walkGo(d) {
    if (!U.walk.length) return;
    const cur = (U.H.kpEntry() || {}).id || "", k = U.walk.findIndex((x) => x.id === cur);
    const n = k < 0 ? (d > 0 ? 0 : U.walk.length - 1) : (k + d + U.walk.length) % U.walk.length;
    U.H.kpShow(U.walk[n].id);
  }
  function onWalk(e) {
    const b = e.target.closest("[data-w]"); if (!b) return;
    const a = b.dataset.w;
    if (a === "clear") { U.doc.selection = []; return afterSelection(); }
    if (a === "pinall") return pinAll();
    walkGo(+a);
  }
  async function pinAll() {
    const ids = selection().filter((m) => !findPinned({ kind: "entry", id: "material:" + m }));
    for (const m of ids) await addPin({ kind: "entry", id: "material:" + m }, true);
    U.H.toast(L(`${ids.length} Einträge angeheftet.`, `${ids.length} entries pinned.`));
  }

  // ---- Anheften
  const findPinned = (spec) => { const k = specKey(spec); return board().cards.find((c) => c.kind !== "note" && specKey(c.spec) === k); };
  function pushUndo() { U.undo.push({ board: board().id, snap: snapshot(board()) }); if (U.undo.length > 40) U.undo.shift(); }
  function undo() {
    const u = U.undo.pop(); if (!u) return;
    const b = U.doc.boards.find((x) => x.id === u.board);
    if (b) { U.doc.active = b.id; restore(b, u.snap); U.sel.clear(); dirty(); render(); redecorate(); }
  }
  async function addPin(spec, quiet) {
    const j = await U.H.api("api/infoboard/pin", { spec, lang: lang() });
    if (!j || j.error || !j.pin) { U.H.toast(L("Nicht angeheftet: ", "Not pinned: ") + ((j && j.error) || ""), true); return null; }
    pushUndo();
    const c = placeCard(board(), j.pin);
    dirty();
    if (U.open) render();
    redecorate();
    if (!quiet) U.H.toast(L(`Angeheftet: ${cont(c).title || ""} (${board().name})`, `Pinned: ${cont(c).title || ""} (${board().name})`));
    return c;
  }
  async function togglePin(spec) {
    if (!U.doc) await sync();
    if (!U.doc) return;
    const c = findPinned(spec), key = specKey(spec);
    if (c) { removeWithUndo([c.id]); return; }
    U.pinning = U.pinning || new Set();
    if (U.pinning.has(key)) return;                 // ein Diagramm braucht einen Moment: ein zweiter Klick legt keine zweite Karte an
    U.pinning.add(key);
    try { await addPin(spec); } finally { U.pinning.delete(key); }
  }
  function removeWithUndo(ids) {
    pushUndo();
    removeCards(board(), ids);
    ids.forEach((id) => U.sel.delete(id));
    dirty();
    if (U.open) render();
    redecorate();
    U.H.toast(L(`Entfernt (${ids.length}). Rückgängig: Strg+Z auf der Tafel.`, `Removed (${ids.length}). Undo: Ctrl+Z on the board.`));
  }
  function redecorate() {
    if (!U.doc) return;
    const box = $("#kpEntry");
    if (box) $$("[data-ibk]", box).forEach((b) => b.classList.toggle("on", !!findPinned(specOf(b))));
    badge();
    chrome();                                       // „Ansicht anheften“ / „Angeheftet“ folgt dem Stand der Tafel
  }
  function specOf(b) {
    const k = b.dataset.ibk;
    if (k === "figure") return U.H.figSpec() || { kind: "figure" };
    return { kind: k, id: b.dataset.ibr };
  }
  const pinBtn = (kind, ref, label) => `<button type="button" class="ibp" data-ibk="${esc(kind)}" data-ibr="${esc(ref)}" title="${esc(label)}" aria-label="${esc(label)}">${PIN}</button>`;
  function decorateEntry(box, e) {
    if (!U.H || !U.doc) return;
    const h3 = $("h3", box);
    if (h3) h3.insertAdjacentHTML("beforeend", pinBtn("entry", e.id, L("Ganzen Eintrag anheften", "Pin the whole entry")));
    $$("[data-kpsec]", box).forEach((s) => {
      const sec = (e.sections || []).find((x) => x.id === s.dataset.kpsec);
      const head = $(":scope > h4, :scope > summary", s);
      if (sec && head && (sec.statements || []).length) head.insertAdjacentHTML("beforeend", pinBtn("section", sec.id, L("Abschnitt anheften", "Pin this section")));
    });
    $$("[data-sid]", box).forEach((el) => {
      const sid = el.dataset.sid;
      if (el.tagName === "TR") { const td = el.lastElementChild; if (td) td.insertAdjacentHTML("beforeend", pinBtn("value", sid, L("Kennwert mit Spanne und Quelle anheften", "Pin the value with range and source"))); }
      else el.insertAdjacentHTML("beforeend", pinBtn("statement", sid, L("Aussage anheften", "Pin this statement")));
    });
    const svg = $("#kpSvg", box);
    if (svg && e.media) {
      const label = e.media === "mech" ? L("Dieses Bild anheften", "Pin this frame") : L("Skizze anheften", "Pin the sketch");
      const after = e.media === "mech" ? (svg.nextElementSibling || svg) : svg;
      after.insertAdjacentHTML("afterend", `<div class="ibmedia"><button type="button" data-ibk="figure" data-ibr="" title="${esc(label)}">${PIN.replace("<svg ", '<svg width="12" height="12" ')} ${esc(label)}</button></div>`);
    }
    redecorate();
    walkRender();
  }
  function decorateList(box) {
    if (!box || !U.H || !U.doc) return;
    $$("button[data-kpid^='material:']", box).forEach((b) => {
      const id = b.dataset.kpid.slice(9);
      let row = b.parentElement;
      if (!row.classList.contains("ibrow")) {
        row = document.createElement("div"); row.className = "ibrow";
        b.parentNode.insertBefore(row, b); row.appendChild(b);
        row.insertAdjacentHTML("beforeend", `<button type="button" class="ibsel" data-ibsel="${esc(id)}"></button>`);
      }
      const t = $(".ibsel", row), on = isSel(id);
      t.classList.toggle("on", on); t.textContent = on ? "✓" : "+";
      t.title = on ? L("Aus der Reihe nehmen", "Remove from the series") : L("Zur Reihe hinzufügen", "Add to the series");
      t.setAttribute("aria-label", t.title + ": " + b.textContent); t.setAttribute("aria-pressed", String(on));
    });
    $$(".kpsub", box).forEach((s) => {
      if (!$("button", s) && familyOf(s).length) s.insertAdjacentHTML("beforeend", `<button type="button" data-ibfam title="${esc(L("Ganze Familie zur Reihe", "Add the whole family to the series"))}" aria-label="${esc(L("Ganze Familie zur Reihe", "Add the whole family to the series"))}">+ ${esc(L("alle", "all"))}</button>`);
    });
  }
  function familyOf(sub) {
    const out = [];
    for (let el = sub.nextElementSibling; el && !el.classList.contains("kpsub"); el = el.nextElementSibling) {
      const b = el.matches("button[data-kpid]") ? el : $("button[data-kpid]", el);
      if (b && b.dataset.kpid.startsWith("material:")) out.push(b.dataset.kpid.slice(9));
    }
    return out;
  }

  // ---- Knöpfe in der Seite (nur wo es etwas anzuheften gibt)
  function chrome() { clearTimeout(U.ct); U.ct = setTimeout(chromeNow, 60); }
  function chromeNow() {
    const o = $("#opts"); if (!o || !U.H) return;
    let p = $("#ibChart", o), f = $("#ibFam", o);
    if (!p) {
      const all = $("#viewAll", o);
      all.insertAdjacentHTML("beforebegin", `<button type="button" id="ibFam" hidden></button><button type="button" id="ibChart" hidden>${PIN.replace("<svg ", '<svg width="12" height="12" style="vertical-align:-1px" ')} <span></span></button>`);
      p = $("#ibChart", o); f = $("#ibFam", o);
      p.addEventListener("click", () => { const s = U.H.chartSpec(); if (s) togglePin(s); });
      f.addEventListener("click", () => { const x = U.H.chartFamily(); if (x) selectMany(x.ids); });
    }
    const spec = U.H.chartSpec();
    p.hidden = !spec;
    if (spec) { const on = !!(U.doc && findPinned(spec)); $("span", p).textContent = on ? L("Angeheftet", "Pinned") : L("Ansicht anheften", "Pin this view"); p.title = L("Das Kennwertdiagramm in der aktuellen Ansicht an die Infotafel heften", "Pin the property chart in its current view to the info board"); }
    const fam = U.H.chartFamily();
    f.hidden = !fam;
    if (fam) { f.textContent = L(`Familie zur Reihe (${fam.ids.length})`, `Family to series (${fam.ids.length})`); f.title = fam.name; }
  }

  // ---- Fläche
  function ensureUI() {
    if (U.root) return;
    const w = document.createElement("div");
    w.id = "ibWin"; w.hidden = true; w.setAttribute("role", "region");
    w.innerHTML = `<div class="ibbar" id="ibBar"></div><div id="ibCanvas" tabindex="0" role="application"><div id="ibLayer"></div><div class="ibempty" id="ibEmpty"></div></div>`;
    document.body.appendChild(w);
    U.root = w; U.canvas = $("#ibCanvas", w); U.layer = $("#ibLayer", w);
    w.addEventListener("click", onClick);
    w.addEventListener("keydown", onKey);
    w.addEventListener("input", onInput);
    w.addEventListener("change", onChange);
    U.canvas.addEventListener("pointerdown", onDown);
    U.canvas.addEventListener("pointermove", onMove);
    U.canvas.addEventListener("pointerup", onUp);
    U.canvas.addEventListener("pointercancel", onUp);
    U.canvas.addEventListener("wheel", onWheel, { passive: false });
    U.canvas.addEventListener("dblclick", onDbl);
    g.addEventListener("resize", place);
  }
  function place() {
    if (!U.root || U.root.hidden) return;
    const h = $("header");
    U.root.style.top = (h ? Math.max(0, h.getBoundingClientRect().bottom) : 0) + "px";
  }
  async function openBoard() {
    if (!U.doc) await sync();
    if (!U.doc) return;
    ensureUI();
    U.open = true; U.root.hidden = false; place();
    $("#ibBtn").setAttribute("aria-pressed", "true");
    render();
    U.canvas.focus();
    checkStates();
  }
  function closeBoard() {
    if (!U.open) return;
    U.open = false; U.root.hidden = true; U.menu = false;
    const b = $("#ibBtn"); b.setAttribute("aria-pressed", "false"); b.focus();
    flush();
  }
  function render() { if (!U.root || !U.open) return; place(); renderBar(); renderLayer(); }
  function renderBar() {
    const b = board(), mats = compareIds();
    $("#ibBar").innerHTML =
      `<select id="ibBoards" aria-label="${esc(L("Tafel wählen", "Choose a board"))}">${U.doc.boards.map((x) => `<option value="${esc(x.id)}"${x.id === b.id ? " selected" : ""}>${esc(x.name)}</option>`).join("")}</select>` +
      `<span class="ibmenu"><button type="button" data-a="menu" aria-haspopup="true" aria-expanded="${U.menu}" aria-label="${esc(L("Tafel verwalten", "Manage boards"))}" title="${esc(L("Tafel verwalten", "Manage boards"))}">⋯</button>${U.menu ? `<div role="menu"><button type="button" role="menuitem" data-a="b-new">${esc(L("Neue Tafel …", "New board …"))}</button><button type="button" role="menuitem" data-a="b-ren">${esc(L("Umbenennen …", "Rename …"))}</button><button type="button" role="menuitem" data-a="b-del"${U.doc.boards.length < 2 ? " disabled" : ""}>${esc(L("Löschen …", "Delete …"))}</button></div>` : ""}</span>` +
      `<button type="button" data-a="frame" title="${esc(L("Neuer Rahmen (F)", "New frame (F)"))}">+ ${esc(L("Rahmen", "Frame"))}</button>` +
      `<button type="button" data-a="note" title="${esc(L("Neue eigene Notiz (N)", "New own note (N)"))}">+ ${esc(L("Notiz", "Note"))}</button>` +
      (mats.length >= 2 ? `<button type="button" data-a="compare">${esc(L(`Vergleichen (${mats.length})`, `Compare (${mats.length})`))}</button>` : "") +
      (U.sel.size ? `<button type="button" data-a="del">${esc(L(`Entfernen (${U.sel.size})`, `Remove (${U.sel.size})`))}</button>` : "") +
      `<span class="sp"></span>` +
      `<button type="button" data-a="undo"${U.undo.length ? "" : " disabled"} title="${esc(L("Rückgängig (Strg+Z)", "Undo (Ctrl+Z)"))}" aria-label="${esc(L("Rückgängig", "Undo"))}">↶</button>` +
      `<button type="button" data-a="zout" aria-label="${esc(L("Verkleinern", "Zoom out"))}">−</button><span class="z" id="ibZoom"></span><button type="button" data-a="zin" aria-label="${esc(L("Vergrössern", "Zoom in"))}">+</button>` +
      `<button type="button" data-a="fit" title="${esc(L("Alles zeigen (0)", "Show everything (0)"))}">${esc(L("Alles", "Fit"))}</button>` +
      `<button type="button" class="primary" data-a="export"${window.Lab ? "" : ` disabled title="${esc(L("Nur in Folio Lab verfügbar", "Only available in Folio Lab"))}"`}>${esc(L("Zum Bericht …", "To report …"))}</button>` +
      `<button type="button" data-a="close" aria-label="${esc(L("Infotafel schliessen", "Close the info board"))}" title="Esc">✕</button>`;
    applyView();
  }
  function applyView() {
    const v = board().view;
    U.layer.style.transform = `translate(${v.x}px, ${v.y}px) scale(${v.z})`;
    const z = $("#ibZoom"); if (z) z.textContent = Math.round(v.z * 100) + " %";
  }
  function frameHtml(f, n) {
    const edit = U.editFrame === f.id;
    return `<div class="ibframe" data-frame="${esc(f.id)}" style="left:${f.x}px;top:${f.y}px;width:${f.w}px;height:${f.h}px">
      <div class="ibfh" data-fhead tabindex="0" role="group" aria-label="${esc(L(`Rahmen ${n + 1}: ${f.name}`, `Frame ${n + 1}: ${f.name}`))}">
        <span class="no" title="${esc(L("Reihenfolge im Bericht", "Order in the report"))}">${n + 1}</span>
        ${edit ? `<input data-fname value="${esc(f.name)}" maxlength="120" aria-label="${esc(L("Name des Rahmens", "Frame name"))}">` : `<span class="nm" title="${esc(L("Doppelklick oder F2: umbenennen", "Double-click or F2: rename"))}">${esc(f.name || L("Ohne Namen", "Unnamed"))}</span>`}
        <span class="acts">
          <button type="button" data-fa="up" title="${esc(L("Im Bericht früher (Alt+←)", "Earlier in the report (Alt+←)"))}" aria-label="${esc(L("Im Bericht früher", "Earlier in the report"))}">‹</button>
          <button type="button" data-fa="down" title="${esc(L("Im Bericht später (Alt+→)", "Later in the report (Alt+→)"))}" aria-label="${esc(L("Im Bericht später", "Later in the report"))}">›</button>
          <button type="button" data-fa="ren" aria-label="${esc(L("Umbenennen", "Rename"))}" title="F2">✎</button>
          <button type="button" data-fa="del" aria-label="${esc(L("Rahmen entfernen, Karten bleiben", "Remove the frame, cards stay"))}" title="${esc(L("Rahmen entfernen, Karten bleiben", "Remove the frame, cards stay"))}">✕</button>
        </span>
      </div><div class="ibres" data-res></div></div>`;
  }
  function tags(c) {
    const out = [], f = c.flag || {}, st = U.states[c.id];
    if (c.kind !== "note") {
      const n = Object.keys(c.sources || {}).length;
      out.push(`<span class="ibtag">${n} ${esc(n === 1 ? L("Quelle", "source") : L("Quellen", "sources"))}</span>`);
      if (f.unchecked) out.push(`<span class="ibtag warn" title="${esc(L("Auf Quellen, die nicht am Original geprüft sind", "On sources not checked against the original"))}">† ${f.unchecked}</span>`);
      if (f.open) out.push(`<span class="ibtag warn" title="${esc(L("Ohne nachvollziehbare Quelle", "Without a traceable source"))}">${esc(L("ohne Quelle", "no source"))} ${f.open}</span>`);
    }
    if (st && st.state === "changed") out.push(`<span class="ibtag chg" title="${esc(L("Das Kompendium hat sich geändert: ", "The compendium has changed: ") + (st.what || []).map((w) => ({ text: L("Text", "text"), sources: L("Quellen", "sources"), check: L("Prüfstatus", "check status") }[w])).join(", "))}">${esc(L("geändert seit dem Anheften", "changed since pinned"))}</span>`);
    if (st && st.state === "missing") out.push(`<span class="ibtag chg">${esc(L("nicht mehr im Kompendium", "no longer in the compendium"))}</span>`);
    return out.length ? `<div class="ibtags">${out.join("")}</div>` : "";
  }
  function preview(c) {
    const t = cont(c);
    if (c.kind === "note") return `<textarea data-note aria-label="${esc(L("Text der Notiz", "Note text"))}">${esc(c.text || "")}</textarea>`;
    if (c.kind === "figure") return c.thumb ? `<img src="${esc(c.thumb)}" alt="${esc(t.title || "")}" draggable="false">` : `<div class="small">${esc(t.figure ? t.figure.caption : "")}</div>`;
    if (c.kind === "compare") { const x = t.table || { rows: [], columns: [] }; return `<div class="small">${x.rows.length} ${esc(L("Kennwerte", "properties"))} · ${x.columns.length} ${esc(L("Werkstoffe", "materials"))}</div>`; }
    const st = (t.blocks || []).flatMap((b) => b.statements || []);
    if (c.kind === "value") { const s = st[0] || {}; return `<div><b>${esc(s.shown || "")}</b>${s.range ? ` <span class="small">(${esc(s.range.join("–"))})</span>` : ""}</div><div class="small">${esc(s.label || "")}</div>`; }
    if (c.kind === "statement") return `<p>${esc((st[0] || {}).text || "")}</p>`;
    return `<div class="small">${st.length} ${esc(st.length === 1 ? L("Aussage", "statement") : L("Aussagen", "statements"))}</div>`;
  }
  function details(c) {
    const t = cont(c), st = (t.blocks || []).flatMap((b) => b.statements || []);
    let h = "";
    if (t.figure) h += `<p class="small">${esc(t.figure.caption)}</p>`;
    if (t.table) h += `<table><tr><th></th>${t.table.columns.map((x) => `<th>${esc(x.name)}</th>`).join("")}</tr>${t.table.rows.slice(0, 40).map((r) => `<tr><td>${esc(r.label)}</td>${r.cells.map((x) => `<td>${x ? esc(x.shown || "") : "–"}</td>`).join("")}</tr>`).join("")}</table>`;
    if (c.kind === "entry" || c.kind === "section") h += st.slice(0, 40).map((s) => `<p>${esc(s.label && !s.prop ? s.label + ": " : "")}${esc(s.text)}</p>`).join("");
    const refs = Object.entries(c.sources || {});
    if (refs.length) h += `<ol>${refs.map(([, q]) => `<li>${esc((q.text && (q.text[lang()] || q.text.de)) || "")}${q.status === "unchecked" ? " †" : q.status === "partial" ? " ◐" : ""}</li>`).join("")}</ol>`;
    const st0 = U.states[c.id];
    h += `<div class="row">${c.entry ? `<button type="button" data-ca="open">${esc(L("Im Kompendium", "In the compendium"))}</button>` : ""}${st0 && st0.state === "changed" ? `<button type="button" data-ca="renew" title="${esc(L("Inhalt und Quellen auf den heutigen Stand setzen", "Update content and sources to the current state"))}">${esc(L("Aktualisieren", "Update"))}</button>` : ""}<button type="button" data-ca="del">${esc(L("Entfernen", "Remove"))}</button></div>`;
    return `<div class="ibmore">${h}</div>`;
  }
  function cardHtml(c) {
    const t = cont(c), open = U.more.has(c.id), title = c.kind === "note" ? KIND().note : (t.title || "");
    return `<div class="ibcard${c.kind === "note" ? " note" : ""}${U.sel.has(c.id) ? " sel" : ""}" data-card="${esc(c.id)}" tabindex="0" role="group" aria-label="${esc(KIND()[c.kind] + ": " + title)}" style="left:${c.x}px;top:${c.y}px;width:${c.w || CARD_W}px">
      <span class="ibk">${esc(KIND()[c.kind] || "")}</span>
      <div class="ibch">${c.kind === "note" ? "" : `<b>${esc(title)}</b>`}<button type="button" data-ca="more" aria-expanded="${open}" aria-label="${esc(open ? L("Einklappen", "Collapse") : L("Aufklappen", "Expand"))}" style="margin-left:auto">${open ? "▴" : "▾"}</button></div>
      <div class="ibcb">${preview(c)}</div>${tags(c)}${open ? (c.kind === "note" ? `<div class="ibmore"><div class="row"><button type="button" data-ca="del">${esc(L("Entfernen", "Remove"))}</button></div></div>` : details(c)) : ""}</div>`;
  }
  function renderLayer() {
    const b = board(), focus = document.activeElement && document.activeElement.closest && document.activeElement.closest("[data-card],[data-fhead]");
    const fk = focus ? (focus.dataset.card || (focus.closest("[data-frame]") || { dataset: {} }).dataset.frame) : null, wasCard = !!(focus && focus.dataset.card);
    U.layer.innerHTML = b.frames.map(frameHtml).join("") + b.cards.map(cardHtml).join("");
    $("#ibEmpty").hidden = b.cards.length + b.frames.length > 0;
    $("#ibEmpty").textContent = L("Noch nichts angeheftet. Im Kompendium erscheint neben jeder Aussage, jedem Kennwert und jedem Bild ein Pin.", "Nothing pinned yet. In the compendium a pin appears next to every statement, value and figure.");
    for (const c of b.cards) { const el = U.layer.querySelector(`[data-card="${CSS.escape(c.id)}"]`); if (el && el.offsetHeight && !U.more.has(c.id)) c.h = el.offsetHeight; }
    applyView();
    if (fk) {
      const el = wasCard ? U.layer.querySelector(`[data-card="${CSS.escape(fk)}"]`) : U.layer.querySelector(`[data-frame="${CSS.escape(fk)}"] [data-fhead]`);
      if (el) el.focus({ preventScroll: true });
    }
    const inp = $("[data-fname]", U.layer);
    if (inp) { inp.focus(); inp.select(); }
  }
  const compareIds = () => [...new Set(board().cards.filter((c) => U.sel.has(c.id) && String(c.entry || "").startsWith("material:")).map((c) => c.entry.slice(9)))];

  // ---- Bedienung der Fläche
  function setZoom(z, cx, cy) {
    const v = board().view, n = Math.max(0.2, Math.min(3, z));
    if (cx === undefined) { const r = U.canvas.getBoundingClientRect(); cx = r.width / 2; cy = r.height / 2; }
    v.x = Math.round(cx - (cx - v.x) * (n / v.z)); v.y = Math.round(cy - (cy - v.y) * (n / v.z)); v.z = +n.toFixed(3);
    applyView(); dirty();
  }
  function doFit() { const r = U.canvas.getBoundingClientRect(); board().view = fitView(board(), r.width, r.height); applyView(); dirty(); }
  function newFrame() {
    pushUndo();
    const f = addFrame(board(), L(`Rahmen ${board().frames.length + 1}`, `Frame ${board().frames.length + 1}`));
    U.editFrame = f.id; dirty(); render();
  }
  function newNote() {
    pushUndo();
    const c = placeCard(board(), { id: uid("n"), kind: "note", text: "", w: CARD_W, h: 120 });
    dirty(); render();
    const t = U.layer.querySelector(`[data-card="${CSS.escape(c.id)}"] textarea`); if (t) t.focus();
  }
  async function doCompare() {
    const ids = compareIds(); if (ids.length < 2) return;
    const c = await addPin({ kind: "compare", materials: ids });
    if (c) { U.sel.clear(); U.sel.add(c.id); render(); }
  }
  async function renewCard(id) {
    const c = board().cards.find((x) => x.id === id); if (!c) return;
    const j = await U.H.api("api/infoboard/renew", { pin: c, lang: lang() });
    if (j.error || !j.pin) return U.H.toast(j.error || L("Nicht möglich", "Not possible"), true);
    pushUndo();
    board().cards[board().cards.indexOf(c)] = j.pin;
    delete U.states[id];
    dirty(); render();
  }
  function openCard(c) {
    const r = c.spec && (c.spec.kind === "section" || c.spec.kind === "statement" || c.spec.kind === "value") ? c.spec.id : c.entry;
    if (c.entry) U.H.kpOpen(r && r.includes("#") ? r : c.entry);
  }
  async function boardDialog(title, value, label) {
    let got = null;
    const res = await U.H.dialog(title, `<label>${esc(label)}<input id="ibName" maxlength="120" value="${esc(value)}"></label>`, [{ value: "cancel", label: L("Abbrechen", "Cancel") }, { value: "ok", label: "OK", primary: true }], "", (body) => { const i = $("#ibName", body); got = value; i.addEventListener("input", () => { got = i.value; }); i.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); $("#dlgFoot button.primary").click(); } }); });
    return res === "ok" ? String(got || "").trim() : null;
  }
  async function onMenu(a) {
    U.menu = false;
    if (a === "b-new") {
      const name = await boardDialog(L("Neue Tafel", "New board"), L(`Tafel ${U.doc.boards.length + 1}`, `Board ${U.doc.boards.length + 1}`), L("Name", "Name"));
      if (name) { const b = newBoard(name); U.doc.boards.push(b); U.doc.active = b.id; U.undo = []; U.sel.clear(); dirty(); }
    } else if (a === "b-ren") {
      const name = await boardDialog(L("Tafel umbenennen", "Rename board"), board().name, L("Name", "Name"));
      if (name) { board().name = name; dirty(); }
    } else if (a === "b-del" && U.doc.boards.length > 1) {
      const b = board();
      const r = await U.H.dialog(L("Tafel löschen", "Delete board"), `<p>${esc(L(`„${b.name}“ mit ${b.cards.length} Karten löschen? Das lässt sich nicht rückgängig machen.`, `Delete “${b.name}” with ${b.cards.length} cards? This cannot be undone.`))}</p>`, [{ value: "cancel", label: L("Abbrechen", "Cancel") }, { value: "del", label: L("Löschen", "Delete"), primary: true }]);
      if (r === "del") { U.doc.boards = U.doc.boards.filter((x) => x !== b); U.doc.active = U.doc.boards[0].id; U.undo = []; U.sel.clear(); dirty(); }
    }
    render(); redecorate();
  }
  function onClick(e) {
    const a = e.target.closest("[data-a]");
    if (a) {
      const k = a.dataset.a;
      if (k === "menu") { U.menu = !U.menu; return renderBar(); }
      if (k.startsWith("b-")) return onMenu(k);
      if (k === "close") return closeBoard();
      if (k === "frame") return newFrame();
      if (k === "note") return newNote();
      if (k === "compare") return doCompare();
      if (k === "del") return removeWithUndo([...U.sel]);
      if (k === "undo") return undo();
      if (k === "zin") return setZoom(board().view.z * 1.2);
      if (k === "zout") return setZoom(board().view.z / 1.2);
      if (k === "fit") return doFit();
      if (k === "export") return exportDialog();
      return;
    }
    if (U.menu && !e.target.closest(".ibmenu")) { U.menu = false; renderBar(); }
    const fa = e.target.closest("[data-fa]");
    if (fa) {
      const id = fa.closest("[data-frame]").dataset.frame, k = fa.dataset.fa;
      if (k === "up" || k === "down") { pushUndo(); if (reorderFrame(board(), id, k === "up" ? -1 : 1)) dirty(); render(); }
      if (k === "ren") { U.editFrame = id; renderLayer(); }
      if (k === "del") { pushUndo(); removeFrame(board(), id); dirty(); render(); }
      return;
    }
    const ca = e.target.closest("[data-ca]");
    if (ca) {
      const id = ca.closest("[data-card]").dataset.card, c = board().cards.find((x) => x.id === id), k = ca.dataset.ca;
      if (k === "more") { if (U.more.has(id)) U.more.delete(id); else U.more.add(id); return renderLayer(); }
      if (k === "del") return removeWithUndo([id]);
      if (k === "renew") return renewCard(id);
      if (k === "open" && c) return openCard(c);
    }
  }
  function onDbl(e) {
    const h = e.target.closest("[data-fhead]");
    if (h && !e.target.closest("button,input")) { U.editFrame = h.closest("[data-frame]").dataset.frame; renderLayer(); return; }
    const card = e.target.closest("[data-card]");
    if (card && !e.target.closest("button,textarea")) { const id = card.dataset.card; if (U.more.has(id)) U.more.delete(id); else U.more.add(id); renderLayer(); }
  }
  function onInput(e) {
    if (e.target.matches("[data-note]")) {
      const c = board().cards.find((x) => x.id === e.target.closest("[data-card]").dataset.card);
      if (c) { c.text = e.target.value; dirty(); }
    }
  }
  function onChange(e) {
    if (e.target.id === "ibBoards") { U.doc.active = e.target.value; U.sel.clear(); U.undo = []; dirty(); render(); redecorate(); }
    if (e.target.matches("[data-fname]")) commitName(e.target);
  }
  function commitName(inp) {
    const f = board().frames.find((x) => x.id === inp.closest("[data-frame]").dataset.frame);
    if (f && inp.value.trim() !== f.name) { pushUndo(); f.name = inp.value.trim(); dirty(); }
    U.editFrame = null; renderLayer();
  }
  function selectOnly(id, add) {
    if (add) { if (U.sel.has(id)) U.sel.delete(id); else U.sel.add(id); } else { U.sel.clear(); U.sel.add(id); }
    renderBar();
    $$("[data-card]", U.layer).forEach((el) => el.classList.toggle("sel", U.sel.has(el.dataset.card)));
  }
  function onDown(e) {
    if (e.button !== 0 && e.button !== 1) return;
    const t = e.target;
    if (t.closest("button,textarea,input,select,.ibmore")) return;
    const res = t.closest("[data-res]"), head = t.closest("[data-fhead]"), card = t.closest("[data-card]"), v = board().view;
    if (e.button === 0 && res) {
      const f = board().frames.find((x) => x.id === res.closest("[data-frame]").dataset.frame);
      U.drag = { kind: "res", id: f.id, sx: e.clientX, sy: e.clientY, w: f.w, h: f.h };
    } else if (e.button === 0 && head) {
      const id = head.closest("[data-frame]").dataset.frame, f = board().frames.find((x) => x.id === id);
      U.drag = { kind: "frame", id, sx: e.clientX, sy: e.clientY, x: f.x, y: f.y, moved: false };
    } else if (e.button === 0 && card) {
      const id = card.dataset.card, add = e.ctrlKey || e.metaKey || e.shiftKey;
      if (add) { selectOnly(id, true); return; }
      if (!U.sel.has(id)) selectOnly(id, false);
      U.drag = { kind: "card", ids: [...U.sel], sx: e.clientX, sy: e.clientY, moved: false, from: Object.fromEntries(board().cards.filter((c) => U.sel.has(c.id)).map((c) => [c.id, { x: c.x, y: c.y }])) };
    } else {
      if (U.sel.size && e.button === 0) { U.sel.clear(); renderBar(); $$(".ibcard.sel", U.layer).forEach((el) => el.classList.remove("sel")); }
      U.drag = { kind: "pan", sx: e.clientX, sy: e.clientY, x: v.x, y: v.y };
      U.canvas.classList.add("pan");
    }
    try { U.canvas.setPointerCapture(e.pointerId); } catch (err) { /* synthetisches Ereignis */ }
  }
  function onMove(e) {
    const d = U.drag; if (!d) return;
    const v = board().view, dx = (e.clientX - d.sx) / v.z, dy = (e.clientY - d.sy) / v.z;
    if (d.kind === "pan") { v.x = d.x + (e.clientX - d.sx); v.y = d.y + (e.clientY - d.sy); applyView(); return; }
    if (!d.moved && Math.abs(e.clientX - d.sx) + Math.abs(e.clientY - d.sy) < 3) return;
    if (!d.moved) { d.moved = true; pushUndo(); }
    if (d.kind === "card") {
      for (const id of d.ids) { const el = U.layer.querySelector(`[data-card="${CSS.escape(id)}"]`), o = d.from[id]; if (el) { el.style.left = o.x + dx + "px"; el.style.top = o.y + dy + "px"; } }
      const c = board().cards.find((x) => x.id === d.ids[0]);
      if (c) { const f = frameAt(board(), { ...c, x: d.from[c.id].x + dx, y: d.from[c.id].y + dy }); $$(".ibframe", U.layer).forEach((el) => el.classList.toggle("drop", !!f && el.dataset.frame === f.id)); }
    } else if (d.kind === "frame") {
      const el = U.layer.querySelector(`[data-frame="${CSS.escape(d.id)}"]`);
      if (el) { el.style.left = d.x + dx + "px"; el.style.top = d.y + dy + "px"; }
      for (const c of board().cards) if (c.frame === d.id) { const ce = U.layer.querySelector(`[data-card="${CSS.escape(c.id)}"]`); if (ce) { ce.style.left = c.x + dx + "px"; ce.style.top = c.y + dy + "px"; } }
    } else if (d.kind === "res") {
      const el = U.layer.querySelector(`[data-frame="${CSS.escape(d.id)}"]`);
      if (el) { el.style.width = Math.max(MIN_FRAME_W, d.w + dx) + "px"; el.style.height = Math.max(MIN_FRAME_H, d.h + dy) + "px"; }
    }
  }
  function onUp(e) {
    const d = U.drag; if (!d) return;
    U.drag = null; U.canvas.classList.remove("pan");
    try { U.canvas.releasePointerCapture(e.pointerId); } catch (err) { /* schon frei */ }
    const v = board().view, dx = (e.clientX - d.sx) / v.z, dy = (e.clientY - d.sy) / v.z;
    if (d.kind === "pan") { dirty(); return; }
    if (!d.moved) return;
    if (d.kind === "card") {
      for (const id of d.ids) { const c = board().cards.find((x) => x.id === id), o = d.from[id]; if (c) { c.x = o.x; c.y = o.y; } }
      moveCards(board(), d.ids, dx, dy);
    } else if (d.kind === "frame") moveFrame(board(), d.id, dx, dy);
    else if (d.kind === "res") resizeFrame(board(), d.id, d.w + dx, d.h + dy);
    dirty(); renderLayer();
  }
  function onWheel(e) {
    if (e.target.closest(".ibmore,textarea")) return;
    e.preventDefault();
    const r = U.canvas.getBoundingClientRect();
    setZoom(board().view.z * (e.deltaY < 0 ? 1.1 : 1 / 1.1), e.clientX - r.left, e.clientY - r.top);
  }
  function onKey(e) {
    const typing = e.target.closest("input,textarea,select");
    const ctrl = e.ctrlKey || e.metaKey, card = e.target.closest("[data-card]"), head = e.target.closest("[data-fhead]");
    const done = () => { e.preventDefault(); e.stopPropagation(); };
    if (e.target.matches("[data-fname]")) {
      if (e.key === "Enter") { done(); commitName(e.target); } else if (e.key === "Escape") { done(); U.editFrame = null; renderLayer(); } else e.stopPropagation();
      return;
    }
    if (typing) { if (e.key === "Escape") { done(); e.target.blur(); if (card) card.focus(); } else e.stopPropagation(); return; }
    if (e.key === "Escape") { done(); if (U.menu) { U.menu = false; renderBar(); } else closeBoard(); return; }
    if (ctrl && e.key.toLowerCase() === "z") { done(); undo(); return; }
    if (ctrl) return;
    const step = e.shiftKey ? 100 : GRID, arrow = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[e.key];
    if (head && !e.target.closest("button")) {
      const id = head.closest("[data-frame]").dataset.frame;
      if (e.altKey && (e.key === "ArrowLeft" || e.key === "ArrowRight")) { done(); pushUndo(); if (reorderFrame(board(), id, e.key === "ArrowLeft" ? -1 : 1)) dirty(); render(); return; }
      if (arrow) { done(); pushUndo(); moveFrame(board(), id, arrow[0], arrow[1]); dirty(); renderLayer(); return; }
      if (e.key === "F2" || e.key === "Enter") { done(); U.editFrame = id; renderLayer(); return; }
      if (e.key === "Delete") { done(); pushUndo(); removeFrame(board(), id); dirty(); render(); U.canvas.focus(); return; }
    }
    if (card && e.target === card) {
      const id = card.dataset.card, c = board().cards.find((x) => x.id === id);
      if (arrow) { done(); pushUndo(); moveCards(board(), U.sel.has(id) ? [...U.sel] : [id], arrow[0], arrow[1]); dirty(); renderLayer(); return; }
      if (e.key === "Enter") { done(); if (U.more.has(id)) U.more.delete(id); else U.more.add(id); renderLayer(); return; }
      if (e.key === " ") { done(); selectOnly(id, true); return; }
      if (e.key === "Delete" || e.key === "Backspace") { done(); removeWithUndo(U.sel.has(id) ? [...U.sel] : [id]); U.canvas.focus(); return; }
      if (e.key.toLowerCase() === "o" && c) { done(); openCard(c); return; }
    }
    if (e.target.closest("button")) { if (e.key !== "Tab") e.stopPropagation(); return; }
    const k = e.key.toLowerCase();
    if (k === "n") { done(); newNote(); } else if (k === "f") { done(); newFrame(); } else if (k === "+" || k === "=") { done(); setZoom(board().view.z * 1.2); } else if (k === "-") { done(); setZoom(board().view.z / 1.2); } else if (k === "0") { done(); doFit(); }
    else if (arrow && e.target === U.canvas) { done(); const v = board().view; v.x -= arrow[0] * 2; v.y -= arrow[1] * 2; applyView(); dirty(); }
  }

  // ---- Export
  function planHtml(p, leave) {
    const fr = p.frames.map((f, k) => `${k + 1}. ${f.name || L("Ohne Namen", "Unnamed")} (${f.n})`).join(" · ");
    let h = `<p class="small">${esc(L("Abschnitte im Bericht", "Sections in the report"))}: ${esc(fr || "–")}</p>`;
    if (p.changed.length) h += `<div class="note warn">${esc(L(`${p.changed.length} Pins haben sich im Kompendium geändert oder fehlen dort. Der Bericht zeigt ihren Stand beim Anheften.`, `${p.changed.length} pins have changed in the compendium or are gone from it. The report shows their state when pinned.`))}<br><span class="small">${p.changed.slice(0, 6).map((c) => esc(c.title)).join(" · ")}</span></div>`;
    if (!p.flagged.length) return h + `<p class="small">${esc(L("Keine Pins ohne Quelle oder auf ungeprüften Quellen.", "No pins without a source or on unchecked sources."))}</p>`;
    h += `<div class="note warn">${esc(L(`${p.flagged.length} Pins ruhen ganz oder teilweise auf Quellen, die nicht am Original geprüft sind, oder haben keine Quelle. Was bleibt, trägt im Bericht das Zeichen † und eine Erklärung.`, `${p.flagged.length} pins rest fully or partly on sources not checked against the original, or have no source. What stays carries the mark † and an explanation in the report.`))}</div>`;
    h += `<div class="row"><button type="button" data-xall="1">${esc(L("Alle weglassen", "Leave all out"))}</button><button type="button" data-xall="0">${esc(L("Alle behalten", "Keep all"))}</button></div><ul>`;
    for (const x of p.flagged) {
      const sample = x.statements.slice(0, 2).map((s) => s.text).join(" · ");
      const what = x.partial ? L(`${x.n} Aussagen betroffen; weggelassen werden nur diese`, `${x.n} statements affected; only these are left out`) : L("wird ganz weggelassen", "is left out entirely");
      h += `<li><label><input type="checkbox" data-leave="${esc(x.pin)}"${leave.has(x.pin) ? " checked" : ""}> <span><b>${esc(x.title)}</b> · ${esc(L("weglassen", "leave out"))}</span></label><small>${esc(what)}${x.n_open ? " · " + esc(L(`${x.n_open} ohne Quelle`, `${x.n_open} without a source`)) : ""}</small><small>${esc(sample.length > 160 ? sample.slice(0, 160) + " …" : sample)}</small></li>`;
    }
    return h + "</ul>";
  }
  const lean = (c) => { const { thumb, ...rest } = c; return rest; };
  function scopeBoard(b, frame) {
    const cards = frame ? b.cards.filter((c) => c.frame === frame) : b.cards;
    return { id: b.id, name: b.name, frames: frame ? b.frames.filter((f) => f.id === frame) : b.frames, cards: cards.map(lean) };
  }
  async function exportDialog() {
    const b = board();
    if (!b.cards.length) return U.H.toast(L("Die Tafel ist leer.", "The board is empty."), true);
    let frame = "", plan = null;
    const leave = new Set();
    const load = async (box) => {
      const out = $("#ibPlan", box);
      out.innerHTML = `<div class="small">${esc(L("prüft …", "checking …"))}</div>`;
      const j = await U.H.api("api/infoboard/plan", { board: scopeBoard(b, frame), frame: frame || null, lang: lang() });
      if (j.error) { out.innerHTML = `<div class="note err">${esc(j.error)}</div>`; return; }
      plan = j; for (const x of [...leave]) if (!j.flagged.some((f) => f.pin === x)) leave.delete(x);
      out.innerHTML = planHtml(j, leave);
    };
    const body = `<div class="ibexp"><label>${esc(L("Was soll in den Bericht?", "What goes into the report?"))}<select id="ibScope"><option value="">${esc(L("Ganze Tafel", "Whole board"))}: ${esc(b.name)}</option>${b.frames.map((f, k) => `<option value="${esc(f.id)}">${esc(L("Rahmen", "Frame"))} ${k + 1}: ${esc(f.name || L("Ohne Namen", "Unnamed"))}</option>`).join("")}</select></label><div id="ibPlan"></div></div>`;
    const r = await U.H.dialog(L("Infotafel zum Bericht", "Info board to report"), body, [{ value: "cancel", label: L("Abbrechen", "Cancel") }, { value: "go", label: L("Weiter …", "Continue …"), primary: true }], "", (box) => {
      $("#ibScope", box).addEventListener("change", (e) => { frame = e.target.value; load(box); });
      box.addEventListener("change", (e) => { if (e.target.matches("[data-leave]")) { if (e.target.checked) leave.add(e.target.dataset.leave); else leave.delete(e.target.dataset.leave); } });
      box.addEventListener("click", (e) => { const a = e.target.closest("[data-xall]"); if (!a || !plan) return; leave.clear(); if (a.dataset.xall === "1") plan.flagged.forEach((x) => leave.add(x.pin)); $("#ibPlan", box).innerHTML = planHtml(plan, leave); });
      load(box);
    }, true);
    if (r !== "go") return;
    await flush();
    const sub = scopeBoard(b, frame), out = [...leave], name = frame ? (b.frames.find((f) => f.id === frame) || {}).name || b.name : b.name;
    window.Lab.sendToReport({
      module: "werkstoffe",
      title: L("Infotafel: ", "Info board: ") + name,
      scopes: [{ id: "cur", label: name }],
      include: [{ id: "figures", label: L("Abbildungen", "Figures") }, { id: "tables", label: L("Tabellen", "Tables") }, { id: "citations", label: L("Quellen je Aussage", "Sources per statement") }, { id: "text", label: L("Text je Rahmen, Methodik", "Text per frame, methods") }],
      build: ({ lang: lg, include, title }) => U.H.api("api/bundle", { sections: [{ tool: "infotafel", req: { board: sub, frame: frame || null, leave_out: out } }], lang: lg, include, title }),
    });
  }

  // ---- Einbindung
  function relabel() {
    if (!U.H) return;
    const b = $("#ibBtn");
    if (b) {
      $(".t", b).textContent = L("Infotafel", "Info board");
      b.title = L("Angeheftete Inhalte des Kompendiums ordnen und mit ihren Quellen in den Bericht geben", "Arrange pinned compendium content and send it to the report with its sources");
    }
    U.walkKey = ""; if (U.doc) walkLoad();
    chrome();
    if (U.open) render();
  }
  function init(host) {
    U.H = host;
    const st = document.createElement("style"); st.textContent = STYLE; document.head.appendChild(st);
    const b = $("#ibBtn");
    if (b) { b.hidden = false; b.addEventListener("click", () => (U.open ? closeBoard() : openBoard())); }
    const list = $("#kpList");
    if (list) list.addEventListener("click", (e) => {
      const t = e.target.closest("[data-ibsel]");
      if (t) { e.stopPropagation(); return toggle(t.dataset.ibsel); }
      const f = e.target.closest("[data-ibfam]");
      if (f) { e.stopPropagation(); selectMany(familyOf(f.closest(".kpsub"))); }
    });
    const entry = $("#kpEntry");
    if (entry) entry.addEventListener("click", (e) => {
      const p = e.target.closest("[data-ibk]");
      if (!p) return;
      e.preventDefault();
      const spec = specOf(p);
      if (spec && (spec.id || spec.fig)) togglePin(spec);
    });
    const win = $("#kpWin");
    if (win) {
      win.addEventListener("click", (e) => { if (e.target.closest("#ibWalk")) onWalk(e); });
      win.addEventListener("keydown", (e) => { if (e.altKey && selection().length && (e.key === "ArrowLeft" || e.key === "ArrowRight")) { e.preventDefault(); e.stopPropagation(); walkGo(e.key === "ArrowRight" ? 1 : -1); } });
    }
    document.addEventListener("visibilitychange", () => { if (document.hidden && U.dirty) flush(); });
    g.addEventListener("pagehide", () => {                 // letzter Versuch; grosse Tafeln sind durch das kurze Speicherintervall ohnehin schon sicher
      if (!U.dirty || !U.project) return;
      const body = JSON.stringify({ project: U.project, rev: U.rev, doc: U.doc });
      if (body.length < 60000) try { fetch("api/infoboard/save", { method: "POST", headers: { "Content-Type": "application/json" }, body, keepalive: true }); } catch (err) { /* Seite geht zu */ }
    });
    relabel();
    return sync();
  }
  const API = { init, sync, relabel, chrome, decorateEntry, decorateList, figChanged: redecorate, toggle, isSel, selectMany, close: closeBoard, get ready() { return !!(U.H && U.doc); }, model: MODEL, _state: U };
  if (typeof module !== "undefined" && module.exports) module.exports = API;
  g.InfoBoard = API;
})(typeof window !== "undefined" ? window : globalThis);
