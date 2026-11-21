/* Runs the info board's page script against a small DOM stub and an in-memory server.
 * Usage: node infoboard_dom.js <fixture.json>   Prints {"passed": n, "failed": [...]} and exits 1 on a failure.
 * The fixture holds real pins and a real compendium entry written by test_infoboard.py. */
"use strict";
const fs = require("fs");
const path = require("path");

// ---------------------------------------------------------------- DOM stub
const VOID = new Set(["input", "img", "br", "hr", "meta", "link", "path", "circle", "rect", "line"]);
const decode = (s) => s.replace(/&(amp|lt|gt|quot|#39);/g, (_, x) => ({ amp: "&", lt: "<", gt: ">", quot: '"', "#39": "'" }[x]));
const kebab = (k) => k.replace(/[A-Z]/g, (c) => "-" + c.toLowerCase());

function splitSelector(s) {
  const out = []; let cur = "", q = "", br = 0;
  for (const c of s) {
    if (q) { if (c === q) q = ""; } else if (c === '"' || c === "'") q = c; else if (c === "[") br++; else if (c === "]") br--;
    if (c === "," && !q && !br) { out.push(cur.trim()); cur = ""; } else cur += c;
  }
  if (cur.trim()) out.push(cur.trim());
  return out;
}
const TOKEN = /^(?:(\*|[a-zA-Z][\w-]*)|#([\w-]+)|\.([\w-]+)|\[([\w-]+)(?:(\^?=)(?:"([^"]*)"|'([^']*)'|([^\]]+)))?\]|(:scope))/;
function parseComplex(s) {
  const parts = []; let rest = s.trim(), comb = " ";
  while (rest) {
    const tests = [];
    let m;
    while (rest && (m = TOKEN.exec(rest))) {
      tests.push(m); rest = rest.slice(m[0].length);
    }
    if (!tests.length) throw new Error("selector not supported: " + s);
    parts.push({ comb, tests });
    const c = /^\s*(>)?\s*/.exec(rest);
    comb = c[1] ? ">" : " ";
    rest = rest.slice(c[0].length);
  }
  return parts;
}
function testEl(el, m, scope) {
  if (m[1]) return m[1] === "*" || el.tag === m[1].toLowerCase();
  if (m[2]) return el.getAttribute("id") === m[2];
  if (m[3]) return el.classList.contains(m[3]);
  if (m[9]) return el === scope;
  if (!el.hasAttribute(m[4])) return false;
  if (!m[5]) return true;
  const want = m[6] ?? m[7] ?? m[8], have = el.getAttribute(m[4]);
  return m[5] === "=" ? have === want : have.startsWith(want);
}
function matchParts(el, parts, k, scope) {
  if (!parts[k].tests.every((m) => testEl(el, m, scope))) return false;
  if (k === 0) return true;
  if (parts[k].comb === ">") return !!el.parentNode && el.parentNode.tag !== "#document" && matchParts(el.parentNode, parts, k - 1, scope);
  for (let p = el.parentNode; p && p.tag !== "#document"; p = p.parentNode) if (matchParts(p, parts, k - 1, scope)) return true;
  return false;
}
const matchSel = (el, sel, scope) => splitSelector(sel).some((c) => { const p = parseComplex(c); return matchParts(el, p, p.length - 1, scope); });

class Txt { constructor(t) { this.text = t; this.parentNode = null; this.isText = true; } }
class El {
  constructor(tag) {
    this.tag = String(tag).toLowerCase(); this.kids = []; this.parentNode = null; this.attrs = {}; this._l = {}; this.style = {};
    const self = this;
    this.dataset = new Proxy({}, {
      get: (_, k) => (typeof k === "string" ? self.attrs["data-" + kebab(k)] : undefined),
      set: (_, k, v) => { self.attrs["data-" + kebab(k)] = String(v); return true; },
    });
    this.classList = {
      contains: (c) => (self.attrs.class || "").split(/\s+/).includes(c),
      add: (c) => { if (!self.classList.contains(c)) self.attrs.class = ((self.attrs.class || "") + " " + c).trim(); },
      remove: (c) => { self.attrs.class = (self.attrs.class || "").split(/\s+/).filter((x) => x !== c).join(" "); },
      toggle: (c, on) => { const v = on === undefined ? !self.classList.contains(c) : !!on; if (v) self.classList.add(c); else self.classList.remove(c); return v; },
    };
  }
  get tagName() { return this.tag.toUpperCase(); }
  get id() { return this.attrs.id || ""; } set id(v) { this.attrs.id = v; }
  get className() { return this.attrs.class || ""; } set className(v) { this.attrs.class = v; }
  get hidden() { return "hidden" in this.attrs; } set hidden(v) { if (v) this.attrs.hidden = ""; else delete this.attrs.hidden; }
  get children() { return this.kids.filter((k) => !k.isText); }
  get parentElement() { return this.parentNode && this.parentNode.tag !== "#document" ? this.parentNode : null; }
  get lastElementChild() { const c = this.children; return c[c.length - 1] || null; }
  get nextElementSibling() { if (!this.parentNode) return null; const c = this.parentNode.children; return c[c.indexOf(this) + 1] || null; }
  get offsetHeight() { return 90; }
  get offsetParent() { return this.parentNode; }
  get title() { return this.attrs.title || ""; } set title(v) { this.attrs.title = v; }
  get value() {
    if (this._value !== undefined) return this._value;
    if (this.tag === "select") { const o = this.querySelectorAll("option"), s = o.find((x) => x.hasAttribute("selected")) || o[0]; return s ? s.getAttribute("value") ?? s.textContent : ""; }
    return this.attrs.value ?? "";
  }
  set value(v) { this._value = String(v); }
  get checked() { return this._checked !== undefined ? this._checked : "checked" in this.attrs; } set checked(v) { this._checked = !!v; }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  hasAttribute(k) { return k in this.attrs; }
  removeAttribute(k) { delete this.attrs[k]; }
  get textContent() { return this.kids.map((k) => (k.isText ? k.text : k.textContent)).join(""); }
  set textContent(v) { this.kids = []; if (v !== "") this.append_(new Txt(String(v))); }
  get innerHTML() { return ""; }
  set innerHTML(h) { this.kids = []; for (const n of parseHtml(h)) this.append_(n); }
  append_(n) { if (n.parentNode) n.parentNode.kids = n.parentNode.kids.filter((x) => x !== n); n.parentNode = this; this.kids.push(n); return n; }
  appendChild(n) { return this.append_(n); }
  insertBefore(n, ref) {
    if (n.parentNode) n.parentNode.kids = n.parentNode.kids.filter((x) => x !== n);
    n.parentNode = this; const k = this.kids.indexOf(ref); this.kids.splice(k < 0 ? this.kids.length : k, 0, n); return n;
  }
  remove() { if (this.parentNode) this.parentNode.kids = this.parentNode.kids.filter((x) => x !== this); this.parentNode = null; }
  insertAdjacentHTML(pos, html) {
    const nodes = parseHtml(html);
    if (pos === "beforeend") nodes.forEach((n) => this.append_(n));
    else {
      const p = this.parentNode, at = p.kids.indexOf(this) + (pos === "afterend" ? 1 : 0);
      nodes.forEach((n, k) => { n.parentNode = p; p.kids.splice(at + k, 0, n); });
    }
  }
  walk(fn) { for (const k of this.kids) if (!k.isText) { fn(k); k.walk(fn); } }
  querySelectorAll(sel) { const out = []; this.walk((e) => { if (matchSel(e, sel, this)) out.push(e); }); return out; }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
  matches(sel) { return matchSel(this, sel, this); }
  closest(sel) { for (let n = this; n && n.tag !== "#document"; n = n.parentNode) if (matchSel(n, sel, n)) return n; return null; }
  addEventListener(t, f) { (this._l[t] = this._l[t] || []).push(f); }
  focus() { document.activeElement = this; }
  blur() { if (document.activeElement === this) document.activeElement = document.body; }
  select() {}
  click() { return fire(this, "click"); }
  getBoundingClientRect() { return { left: 0, top: 0, right: 1000, bottom: 40, width: 1000, height: 700 }; }
  setPointerCapture() {}
  releasePointerCapture() {}
}
function parseHtml(html) {
  const root = new El("#frag"), tagRe = /<(\/?)([a-zA-Z][\w-]*)((?:\s+[^\s=>/]+(?:=(?:"[^"]*"|'[^']*'|[^\s>]+))?)*)\s*(\/?)>/y;
  let cur = root, i = 0;
  while (i < html.length) {
    const lt = html.indexOf("<", i);
    if (lt < 0) { cur.append_(new Txt(decode(html.slice(i)))); break; }
    if (lt > i) cur.append_(new Txt(decode(html.slice(i, lt))));
    tagRe.lastIndex = lt;
    const m = tagRe.exec(html);
    if (!m) { cur.append_(new Txt("<")); i = lt + 1; continue; }
    i = tagRe.lastIndex;
    const tag = m[2].toLowerCase();
    if (m[1]) { let n = cur; while (n !== root && n.tag !== tag) n = n.parentNode; if (n !== root) cur = n.parentNode; continue; }
    const el = new El(tag);
    for (const a of m[3].matchAll(/([^\s=]+)(?:=(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g)) el.attrs[a[1]] = decode(a[2] ?? a[3] ?? a[4] ?? "");
    cur.append_(el);
    if (tag === "textarea") { const e = html.indexOf("</textarea>", i); el._value = decode(html.slice(i, e)); i = e + 11; continue; }
    if (!VOID.has(tag) && !m[4]) cur = el;
  }
  const out = [...root.kids]; out.forEach((n) => { n.parentNode = null; }); root.kids = [];
  return out;
}
function fire(el, type, props) {
  const ev = { type, target: el, defaultPrevented: false, _stop: false, preventDefault() { this.defaultPrevented = true; }, stopPropagation() { this._stop = true; }, button: 0, clientX: 0, clientY: 0, deltaY: 0, ctrlKey: false, metaKey: false, shiftKey: false, altKey: false, key: "", pointerId: 1, ...(props || {}) };
  for (let n = el; n && !ev._stop; n = n.parentNode) for (const f of (n._l[type] || []).slice()) f(ev);
  return ev;
}

const document = new El("#document");
document.head = document.appendChild(new El("head")); document.body = document.appendChild(new El("body"));
document.activeElement = document.body; document.hidden = false;
document.createElement = (t) => new El(t);
global.document = document; global.window = global;
global.CSS = { escape: (s) => String(s) };
const winL = {}; global.addEventListener = (t, f) => { (winL[t] = winL[t] || []).push(f); };
document.body.innerHTML = `<header id="hd"><button id="ibBtn" hidden><span class="t"></span><span class="n"></span></button></header>
  <div id="opts"><div id="viewSeg"></div><button id="viewAll"></button></div>
  <div id="kpWin"><div class="head"></div><div class="kpbody"><nav id="kpList"></nav><article id="kpEntry"></article></div></div>
  <div id="dlgBody"></div><div id="dlgFoot"></div>`;

// ---------------------------------------------------------------- checks
const failed = []; let passed = 0;
const ok = (c, msg) => { if (c) passed++; else failed.push(msg); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const clone = (o) => JSON.parse(JSON.stringify(o));
const $ = (s, el) => (el || document).querySelector(s);
const $$ = (s, el) => (el || document).querySelectorAll(s);
const FX = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));

const IB = require(path.join(__dirname, "..", "werk", "static", "infoboard.js"));
const M = IB.model, U = IB._state;

// ---------------------------------------------------------------- in-memory server
const SRV = { cur: "A", docs: { A: M.emptyDoc("Tafel A"), B: M.emptyDoc("Tafel B") }, saves: [], bundle: null, states: {}, plans: 0, n: 0 };
async function api(p, b) {
  await sleep(0);
  const act = p.replace("api/infoboard/", "");
  if (act === "load") return { project: SRV.cur, doc: clone(SRV.docs[SRV.cur]) };
  if (act === "save") {
    const cur = SRV.docs[b.project];
    if (b.rev !== (cur.rev || 0)) return { conflict: true, project: b.project, doc: clone(cur) };
    const doc = clone(b.doc); doc.rev = (cur.rev || 0) + 1; SRV.docs[b.project] = doc; SRV.saves.push(b.project);
    return { ok: true, project: b.project, rev: doc.rev };
  }
  if (act === "pin") {
    const pin = FX.pins[M.specKey(b.spec)];
    return pin ? { pin: { ...clone(pin), id: "p" + (++SRV.n) } } : { error: "no fixture for " + M.specKey(b.spec) };
  }
  if (act === "state") return { states: Object.fromEntries(b.pins.map((x) => [x.id, SRV.states[x.id] || { state: "ok" }])) };
  if (act === "renew") return { pin: { ...clone(b.pin), renewed: true } };
  if (act === "walk") return { items: [{ id: "material:" + b.ids[0], title: FX.entry.title, kind: "material", via: "" }, { id: "atlas:perlit", title: "Perlit", kind: "atlas", via: FX.entry.title }] };
  if (act === "plan") {
    SRV.plans++;
    const cards = b.board.cards.filter((c) => c.kind !== "note");
    const flagged = cards.filter((c) => c.flag && (c.flag.unchecked || c.flag.open)).map((c) => ({ pin: c.id, title: (c.content.de || {}).title, kind: c.kind, partial: ["entry", "section", "compare"].includes(c.kind), n: c.flag.n || 1, n_open: c.flag.open || 0, statements: [{ id: "x", text: "text", reason: "unchecked" }] }));
    return { frames: b.board.frames.map((f) => ({ id: f.id, name: f.name, n: 1 })), flagged, changed: [], n_pins: cards.length };
  }
  if (p === "api/bundle") { SRV.bundle = clone(b); return {}; }
  return { error: "unknown " + p };
}

// ---------------------------------------------------------------- page host
let LANG = "de", script = null, curEntry = null; const shown = [], opened = [];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const host = {
  api, esc, L: (de, en) => (LANG === "en" ? en : de), lang: () => LANG, toast() {},
  dialog: async (title, body, buttons, left, onOpen) => { const b = $("#dlgBody"); b.innerHTML = body; if (onOpen) onOpen(b); return script ? script(b) : "cancel"; },
  kpOpen: (id) => { opened.push(id); }, kpShow: (id) => { shown.push(id); curEntry = { id }; IB.decorateEntry($("#kpEntry"), FX.entry); },
  kpEntry: () => curEntry, figSpec: () => FX.figspec, chartSpec: () => null, chartFamily: () => null,
};
function entryHtml(e) {
  const vals = (e.statements || []).filter((s) => s.prop).slice(0, 3);
  const secs = (e.sections || []).filter((s) => (s.statements || []).length).slice(0, 2);
  return `<h3>${esc(e.title)}</h3><table><tbody>${vals.map((s) => `<tr data-sid="${esc(s.id)}"><td>${esc(s.label)}</td><td class="kpcite"></td></tr>`).join("")}</tbody></table>` +
    secs.map((s) => `<details class="kpsec" data-kpsec="${esc(s.id)}"><summary>${esc(s.title)}</summary>${s.statements.map((x) => `<p data-sid="${esc(x.id)}">${esc(x.text)}</p>`).join("")}</details>`).join("");
}
const cardEl = (id) => $(`[data-card="${id}"]`);
const cards = () => M.activeBoard(U.doc).cards;
const bar = (a) => $(`[data-a="${a}"]`);

// ---------------------------------------------------------------- run
(async () => {
  global.Lab = { sendToReport(o) { global.__sent = o; } };
  await IB.init(host);
  ok(!$("#ibBtn").hidden, "the entry point is visible after init");
  ok(IB.ready && U.project === "A", "the board of the active project is loaded");
  ok($("#ibWin") === null, "no board surface exists before it is opened");

  // Selection and walk
  $("#kpList").innerHTML = `<div class="kpsub">Stahl</div><button data-kpid="material:${FX.mat}">A</button><button data-kpid="material:${FX.mat2}">B</button><div class="kpsub">Themen</div><button data-kpid="topic:x">T</button>`;
  IB.decorateList($("#kpList"));
  const subs = $$(".kpsub", $("#kpList"));
  ok($("[data-ibfam]", subs[0]) && !$("[data-ibfam]", subs[1]), "family control only where the group holds materials");
  fire($(`[data-ibsel="${FX.mat}"]`), "click");
  ok(IB.isSel(FX.mat), "a material joins the series from the list");
  await sleep(10);
  ok($("#ibWalk"), "the walk bar appears with a series");
  fire($("[data-w='1']"), "click");
  ok(shown[shown.length - 1] === "material:" + FX.mat, "next opens the first entry of the walk");
  fire($("[data-w='1']"), "click");
  ok(shown[shown.length - 1] === "atlas:perlit", "next moves on to a linked entry");
  fire($("[data-w='-1']"), "click");
  ok(shown[shown.length - 1] === "material:" + FX.mat, "previous goes back");
  fire($("[data-ibfam]"), "click");
  ok(IB.isSel(FX.mat2), "the family joins the series");

  // Pin controls
  curEntry = { id: FX.entry.id };
  $("#kpEntry").innerHTML = entryHtml(FX.entry);
  IB.decorateEntry($("#kpEntry"), FX.entry);
  ok($("h3 [data-ibk='entry']", $("#kpEntry")), "entry head has a pin");
  ok($("tr [data-ibk='value']", $("#kpEntry")), "a value row has a pin");
  ok($("summary [data-ibk='section']", $("#kpEntry")), "a section has a pin");
  ok($("p [data-ibk='statement']", $("#kpEntry")), "a statement has a pin");
  const pinE = $("h3 [data-ibk='entry']", $("#kpEntry"));
  fire(pinE, "click"); await sleep(10);
  ok(cards().length === 1 && cards()[0].kind === "entry", "pinning adds a card");
  ok(cards()[0].entry === FX.entry.id && Object.keys(cards()[0].sources || {}).length > 0, "the card keeps entry id and sources");
  ok(pinE.classList.contains("on"), "the pin control shows the pinned state");
  fire(pinE, "click"); await sleep(10);
  ok(cards().length === 0, "pinning again removes");
  fire(pinE, "click"); await sleep(10);
  fire($("tr [data-ibk='value']", $("#kpEntry")), "click"); await sleep(10);
  fire($("p [data-ibk='statement']", $("#kpEntry")), "click"); await sleep(10);
  ok(cards().length === 3, "entry, value and statement pinned");

  // Surface
  fire($("#ibBtn"), "click"); await sleep(10);
  ok($("#ibWin") && !$("#ibWin").hidden, "the board opens");
  ok($$("[data-card]").length === 3, "cards are drawn");
  fire(bar("frame"), "click");
  let inp = $("[data-fname]");
  ok(!!inp, "a new frame asks for its name");
  inp.value = "Zweiter"; fire(inp, "keydown", { key: "Enter" });
  const f1 = M.activeBoard(U.doc).frames[0];
  ok(f1.name === "Zweiter", "the frame is named");
  fire(bar("frame"), "click"); inp = $("[data-fname]"); inp.value = "Erster"; fire(inp, "keydown", { key: "Enter" });
  const f2 = M.activeBoard(U.doc).frames[1];
  ok(f2.x !== f1.x || f2.y !== f1.y, "the second frame does not sit on the first");

  const drag = (id, tx, ty) => {
    const c = cards().find((x) => x.id === id), a = { clientX: 10, clientY: 10 }, b = { clientX: 10 + tx - c.x, clientY: 10 + ty - c.y };
    fire(cardEl(id), "pointerdown", a); fire(U.canvas, "pointermove", b); fire(U.canvas, "pointerup", b);
  };
  const [c0, c1, c2] = cards().map((c) => c.id);
  drag(c0, f1.x + 40, f1.y + 60);
  ok(cards().find((c) => c.id === c0).frame === f1.id, "dragging a card into a frame files it there");
  drag(c1, f2.x + 40, f2.y + 60);
  drag(c2, f2.x + 40, f2.y + 200);
  ok(cards().find((c) => c.id === c2).frame === f2.id, "second frame holds its cards");
  const before = cards().find((c) => c.id === c0);
  const bx = before.x;
  fire($(`[data-frame="${f1.id}"] [data-fhead]`), "pointerdown", { clientX: 0, clientY: 0 });
  fire(U.canvas, "pointermove", { clientX: 100, clientY: 0 }); fire(U.canvas, "pointerup", { clientX: 100, clientY: 0 });
  ok(cards().find((c) => c.id === c0).x === bx + 100, "moving a frame moves its cards");
  fire($(`[data-frame="${f1.id}"] [data-res]`), "pointerdown", { clientX: 0, clientY: 0 });
  fire(U.canvas, "pointermove", { clientX: 120, clientY: 80 }); fire(U.canvas, "pointerup", { clientX: 120, clientY: 80 });
  ok(M.activeBoard(U.doc).frames[0].w === 760, "a frame can be resized");
  fire($(`[data-frame="${f2.id}"] [data-fa="up"]`), "click");
  ok(M.activeBoard(U.doc).frames[0].id === f2.id, "frames can be reordered");
  ok(M.exportOrder(M.activeBoard(U.doc)).map((x) => x.frame && x.frame.id)[0] === f2.id, "export order follows the frame order");

  // Note, keyboard, undo
  fire(bar("note"), "click");
  const noteC = cards().find((c) => c.kind === "note");
  const ta = $(`[data-card="${noteC.id}"] textarea`);
  ta.value = "Meine Notiz"; fire(ta, "input");
  ok(noteC.text === "Meine Notiz" && !noteC.sources, "a note holds the user's text and no sources");
  const k0 = cards().find((c) => c.id === noteC.id).x;
  cardEl(noteC.id).focus();
  fire(cardEl(noteC.id), "keydown", { key: "ArrowRight" });
  ok(cards().find((c) => c.id === noteC.id).x === k0 + 20, "arrow keys move a focused card");
  ok(document.activeElement && document.activeElement.dataset.card === noteC.id, "focus survives the redraw");
  fire(cardEl(noteC.id), "keydown", { key: "Delete" });
  ok(!cards().some((c) => c.id === noteC.id), "Delete removes the card");
  fire(U.canvas, "keydown", { key: "z", ctrlKey: true });
  ok(cards().some((c) => c.id === noteC.id), "Ctrl+Z brings it back");
  fire(cardEl(c1), "keydown", { key: "Enter" });
  ok(U.more.has(c1) && $(`[data-card="${c1}"] .ibmore`), "Enter unfolds a card");
  ok($(`[data-card="${c1}"] .ibmore ol li`), "the unfolded card lists its sources");
  fire($(`[data-card="${c1}"] [data-ca="open"]`), "click");
  ok(opened.length === 1, "a card opens its compendium entry");
  fire(cardEl(c1), "keydown", { key: "Enter" });

  // Changed since pinned
  SRV.states[c1] = { state: "changed", what: ["text"] };
  await IB.sync(); await sleep(10);
  ok($(`[data-card="${c1}"] .ibtag.chg`), "a changed pin carries its badge");
  U.more.add(c1); fire(cardEl(c1), "keydown", { key: "x" });
  IB.relabel();
  fire($(`[data-card="${c1}"] [data-ca="renew"]`), "click"); await sleep(10);
  ok(cards().find((c) => c.id === c1).renewed, "a changed pin can be updated on request");
  delete SRV.states[c1]; U.more.delete(c1); IB.relabel();

  // Compare
  const addCard = async (spec) => { const j = await api("api/infoboard/pin", { spec }); return M.placeCard(M.activeBoard(U.doc), j.pin); };
  const m2 = await addCard({ kind: "entry", id: "material:" + FX.mat2 });
  IB.relabel();
  fire(cardEl(c0), "pointerdown", {}); fire(U.canvas, "pointerup", {});
  fire(cardEl(m2.id), "pointerdown", { ctrlKey: true });
  ok(bar("compare"), "two material pins offer a comparison");
  fire(bar("compare"), "click"); await sleep(10);
  const cmp = cards().find((c) => c.kind === "compare");
  ok(cmp && cmp.content.de.table.rows.length > 0, "the comparison is a pinned table");

  // Figure pin
  host.figSpec = () => ({ kind: "figure", fig: "atlas", gef: "perlit" });
  const atlas = { id: "atlas:perlit", title: "Perlit", media: "atlas", sections: [], statements: [] };
  curEntry = { id: atlas.id };
  $("#kpEntry").innerHTML = '<h3>Perlit</h3><svg id="kpSvg"></svg>';
  IB.decorateEntry($("#kpEntry"), atlas);
  const figBtn = $(".ibmedia [data-ibk='figure']", $("#kpEntry"));
  ok(!!figBtn, "a figure has a pin control");
  fire(figBtn, "click"); await sleep(10);
  const figC = cards().find((c) => c.kind === "figure");
  ok(figC && figBtn.classList.contains("on"), "the figure is pinned");
  ok(figC && $(`[data-card="${figC.id}"] img`), "the figure card shows its preview");

  // Several boards
  script = (b) => { const i = $("#ibName", b); i.value = "Zweite Tafel"; fire(i, "input"); return "ok"; };
  fire(bar("menu"), "click"); fire(bar("b-new"), "click"); await sleep(10);
  ok(U.doc.boards.length === 2 && M.activeBoard(U.doc).name === "Zweite Tafel", "a second board can be created");
  const sel = $("#ibBoards"); sel.value = U.doc.boards[0].id; fire(sel, "change");
  ok(M.activeBoard(U.doc).id === U.doc.boards[0].id, "boards can be switched");

  // Export
  script = async (b) => {
    await sleep(15);
    const leave = $("[data-leave]", b);
    ok(!!leave, "the warning lists a flagged pin");
    if (leave) { leave.checked = true; fire(leave, "change"); global.__left = leave.dataset.leave; }
    return "go";
  };
  fire(bar("export"), "click"); await sleep(60);
  ok(!!global.__sent, "export goes through Lab.sendToReport");
  await global.__sent.build({ lang: "de", include: { figures: true }, title: "x" });
  const sec = SRV.bundle.sections[0];
  ok(sec.tool === "infotafel", "the bundle request names the board");
  ok(sec.req.leave_out.includes(global.__left), "left-out pins are passed on");
  ok(sec.req.board.frames[0].id === f2.id, "the request keeps the frame order");
  ok(sec.req.board.cards.every((c) => !c.thumb), "previews are not sent to the report");
  ok(sec.req.board.cards.filter((c) => c.kind !== "note").every((c) => c.content && c.sources), "the request stores the full pin records");

  // Project switch and reload
  await sleep(320);
  ok(SRV.docs.A.boards[0].cards.length >= 4, "the board was saved to its project");
  const nA = M.activeBoard(U.doc).cards.length;
  bar("note") && fire(bar("note"), "click");
  SRV.cur = "B"; await IB.sync();
  ok(U.project === "B" && M.activeBoard(U.doc).name === "Tafel B", "a project switch loads that project's board");
  ok(SRV.docs.A.boards[0].cards.length === nA + 1, "pending edits are written to the old project first");
  ok(M.activeBoard(SRV.docs.B).cards.length === 0, "nothing leaked into the other project");
  SRV.cur = "A"; await IB.sync();
  ok(M.activeBoard(U.doc).cards.length === nA + 1, "switching back restores the board");

  // Language and close
  LANG = "en"; IB.relabel();
  ok($(".t", $("#ibBtn")).textContent === "Info board", "the entry point follows the language");
  ok($("[data-a='close']").getAttribute("aria-label") === "Close the info board", "the toolbar follows the language");
  fire(U.canvas, "keydown", { key: "Escape" });
  ok($("#ibWin").hidden, "Esc closes the board");
  await sleep(20);
  console.log(JSON.stringify({ passed, failed }));
  process.exit(failed.length ? 1 : 0);
})().catch((e) => { console.log(JSON.stringify({ passed, failed: [...failed, "crash: " + (e && e.stack)] })); process.exit(1); });
