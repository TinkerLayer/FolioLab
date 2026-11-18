/* Übersicht als Arbeitsfläche (UI-10): Kästen, die sich ziehen und öffnen lassen, und Verbindungen dazwischen.
 * Ohne Abhängigkeiten; jede Modulseite bindet labboard.js ein. Die Seite bestimmt, was die Kästen bedeuten.
 *
 *   const B = LabBoard.create(el, {
 *     boxes: () => [{ id, col: 0|1|2, kind, title, sub, html, in: bool, out: bool, cls, active, label, float, plots }],
 *                                       // float: nicht verschiebbar, steht immer unter den übrigen Kästen der Spalte
 *                                       // plots (UI-18): kleine Grafiken im Kasten, Klick vergrössert (siehe packPlots)
 *     pos: { id: [x, y] },              // gespeicherte Lage (Server, je Modul und Projekt)
 *     links: [{ from, to, mode }],      // Verbindungen (from = Kasten mit Ausgang, to = Kasten mit Eingang)
 *     onOpen(box),                      // Klick oder Enter: hineinzoomen
 *     onLink(fromId, toId),             // Verbindung gezogen; die Seite entscheidet und ruft setLinks()
 *     onUnlink(link),                   // Klick auf eine Verbindung
 *     onMove(pos),                      // Kasten verschoben: Lage speichern (die Seite verzögert selbst)
 *     wireLabel(link) → Text,           // optional: Beschriftung der Verbindung (z. B. "live", "v3")
 *     wireHint(link) → Text,            // optional: Tooltip statt „Klick: Verbindung lösen“ (z. B. wenn der Klick bearbeitet)
 *   });
 *   B.render();  B.setLinks(links);  B.setPos(pos);
 *
 * Spalten ohne gespeicherte Lage: 0 links (geteilte Eingaben, Projektindex), 1 Mitte (Umgebungen), 2 rechts
 * (Ergebnisse dieses Moduls). Unter 700 px stehen die Kästen untereinander, Verbindungen dann nur über die Auswahllisten.
 */
(function (g) {
  "use strict";
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const CSS = `
.lab-board{position:relative;min-height:420px;overflow:auto;background-color:var(--bg,#f4f5f8);
  background-image:radial-gradient(circle,rgba(120,128,150,.22) 1px,transparent 1.2px);background-size:22px 22px;border-radius:10px}
.lab-board>.lab-wires{position:absolute;left:0;top:0;pointer-events:none;overflow:visible}
.lab-board .lab-wire{fill:none;stroke:var(--accent,#6d28d9);stroke-width:2;opacity:.75}
.lab-board .lab-wire.pin{stroke-dasharray:6 4}
.lab-board .lab-hit{fill:none;stroke:transparent;stroke-width:14;pointer-events:stroke;cursor:pointer}
.lab-board .lab-hit:hover+.lab-wire,.lab-board .lab-wire.hot{stroke-width:3.5;opacity:1}
.lab-board .lab-wlabel{font:11px system-ui,sans-serif;fill:var(--muted,#5d6472);pointer-events:none}
.lab-box{position:absolute;width:230px;background:var(--panel,#fff);border:1px solid var(--line,#d8dce4);border-radius:10px;
  box-shadow:0 2px 8px rgba(0,0,0,.08);cursor:pointer;user-select:none;outline:none}
.lab-box:hover,.lab-box:focus-visible{border-color:var(--accent,#6d28d9)}
.lab-box.active{box-shadow:0 0 0 2px var(--accent,#6d28d9),0 2px 8px rgba(0,0,0,.08)}
.lab-box .bh{display:flex;flex-direction:column;align-items:flex-start;gap:1px;padding:7px 10px 4px;cursor:grab;font-weight:600}
.lab-box.add .bh{align-items:center;cursor:pointer}
.lab-box .bh .k{font-size:10px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted,#5d6472);font-weight:600}
.lab-box .bb{padding:0 10px 9px;font-size:12px;color:var(--muted,#5d6472);overflow-wrap:anywhere}
.lab-box .bb b{color:var(--ink,#1d2027)}
.lab-box.share{border-style:dashed}
.lab-box.add{border-style:dashed;text-align:center;color:var(--muted,#5d6472);background:transparent;box-shadow:none}
.lab-box .lab-port{position:absolute;top:18px;width:12px;height:12px;border-radius:50%;background:var(--panel,#fff);
  border:2px solid var(--accent,#6d28d9)}
.lab-box .lab-port.in{left:-7px}.lab-box .lab-port.out{right:-7px;cursor:crosshair}
.lab-box.drop{box-shadow:0 0 0 3px var(--accent,#6d28d9)}
.lab-board.narrow{display:flex;flex-direction:column;gap:8px;padding:8px;min-height:0}
.lab-board.narrow .lab-box{position:static;width:auto}
.lab-board.narrow .lab-port,.lab-board.narrow>.lab-wires{display:none}
.lab-box .lab-plots{display:grid;grid-template-columns:1fr 1fr;gap:5px;padding:0 9px 9px}
.lab-box .lab-plots.one{grid-template-columns:1fr}
.lab-board.narrow .lab-box .lab-plots{max-width:420px}
.lab-plot{display:flex;flex-direction:column;gap:1px;min-width:0;width:100%;margin:0;padding:3px 4px 2px;border:1px solid var(--line,#d8dce4);
  border-radius:6px;background:var(--bg,#f8f9fb);color:var(--muted,#5d6472);font:10.5px/1.25 system-ui,sans-serif;cursor:zoom-in;text-align:left}
.lab-plot:hover,.lab-plot:focus-visible{border-color:var(--accent,#6d28d9);outline:none}
.lab-plot svg{display:block;width:100%;height:auto;overflow:visible}
.lab-plot .pt{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.lab-plot-pop{position:fixed;z-index:2147483000;width:min(580px,calc(100vw - 24px));background:var(--panel,#fff);color:var(--ink,#1d2027);
  border:1px solid var(--line,#d8dce4);border-radius:10px;box-shadow:0 10px 30px rgba(0,0,0,.2);padding:8px 10px 10px;font:12px system-ui,sans-serif}
.lab-plot-pop .ph{display:flex;align-items:center;gap:6px;margin-bottom:4px}
.lab-plot-pop .ph b{flex:1;min-width:0;overflow-wrap:anywhere;font-size:13px}
.lab-plot-pop .ph button{border:1px solid var(--line,#d8dce4);background:var(--panel,#fff);color:inherit;border-radius:6px;min-width:26px;height:24px;cursor:pointer;font:inherit}
.lab-plot-pop .ph button:hover{border-color:var(--accent,#6d28d9)}
.lab-plot-pop .ph .n{color:var(--muted,#5d6472);font-size:11px}
.lab-plot-pop svg{display:block;width:100%;height:auto}
.lab-plot-pop svg text{font:11px system-ui,sans-serif;fill:var(--muted,#5d6472)}
.lab-plot-pop .lg{display:flex;flex-wrap:wrap;gap:3px 12px;margin-top:4px;color:var(--muted,#5d6472)}
.lab-plot-pop .lg i{display:inline-block;width:14px;height:3px;border-radius:2px;margin-right:5px;vertical-align:middle}`;
  function ensureCss() {
    if (document.getElementById("lab-board-css")) return;
    const s = document.createElement("style"); s.id = "lab-board-css"; s.textContent = CSS; document.head.appendChild(s);
  }

  // ------------------------------------------------------------------ UI-18: Grafiken in den Kästen
  // Kasten: { …, plots: [{ title, xlab, ylab, xrev, series: [{ name, x: [...], y: [...], bar }] }] }
  // packPlots(plots, n) kürzt auf ≤ 4 Grafiken, ≤ 4 Kurven und ≤ n Punkte je Kurve (Min/Max je Abschnitt, damit
  // Spitzen erhalten bleiben) und rundet auf 4 Stellen – so passt alles in die Zusammenfassung der Umgebung.
  const EN = () => /^en/i.test(document.documentElement.lang || "");
  const tx = (de, en) => (EN() ? en : de);
  // Kurvenfarben: die erste in der Akzentfarbe des Moduls, die übrigen mit deutlich anderem Farbton
  const MORE = ["#2563eb", "#d97706", "#16a34a", "#db2777", "#7c3aed", "#0891b2", "#dc2626"];
  function hueOf(c) {
    let r, g, b;
    const m = String(c).trim().match(/^#([0-9a-f]{6})$/i);
    if (m) { const n = parseInt(m[1], 16); r = (n >> 16) & 255; g = (n >> 8) & 255; b = n & 255; }
    else { const k = String(c).match(/\d+(\.\d+)?/g); if (!k || k.length < 3) return null; [r, g, b] = k.slice(0, 3).map(Number); }
    const mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn;
    if (d < 25) return null;                                   // grau: kein Farbton
    const h = mx === r ? ((g - b) / d) % 6 : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
    return (h * 60 + 360) % 360;
  }
  function palette() {
    const ha = hueOf(getComputedStyle(document.documentElement).getPropertyValue("--accent") || "");
    const far = (c) => { if (ha === null) return true; const d = Math.abs(hueOf(c) - ha); return Math.min(d, 360 - d) > 35; };
    return ["var(--accent,#6d28d9)", ...MORE.filter(far)];
  }
  let PAL = null;
  const fin = (v) => typeof v === "number" && isFinite(v);
  let CLIP = 0;
  const r4 = (v) => (fin(v) ? +v.toPrecision(4) : null);
  function packPlots(plots, n = 100) {
    if (!Array.isArray(plots)) return [];
    const out = [];
    for (const p of plots.slice(0, 4)) {
      if (!p || !Array.isArray(p.series)) continue;
      const series = [];
      for (const s of p.series.slice(0, 4)) {
        if (!s || !s.x || !s.y || typeof s.x.length !== "number" || typeof s.y.length !== "number") continue;   // auch Float64Array
        const m = Math.min(s.x.length, s.y.length), idx = [], bad = new Int32Array(m + 1);   // bad: Lücken bis i (Kurve absetzen)
        for (let i = 0; i < m; i++) {
          const ok = s.x[i] != null && s.y[i] != null && fin(+s.x[i]) && fin(+s.y[i]);
          bad[i + 1] = bad[i] + (ok ? 0 : 1);
          if (ok) idx.push(i);
        }
        if (!idx.length) continue;
        let keep = idx;
        if (idx.length > n && !s.bar) {
          const B = Math.max(1, Math.floor(n / 2)), per = idx.length / B, set = new Set([idx[0], idx[idx.length - 1]]);
          for (let b = 0; b < B; b++) {
            let lo = -1, hi = -1;
            for (let k = Math.floor(b * per); k < Math.min(idx.length, Math.floor((b + 1) * per)); k++) {
              const i = idx[k];
              if (lo < 0 || +s.y[i] < +s.y[lo]) lo = i;
              if (hi < 0 || +s.y[i] > +s.y[hi]) hi = i;
            }
            if (lo >= 0) { set.add(lo); set.add(hi); }
          }
          keep = [...set].sort((a, b) => a - b);
        } else if (idx.length > n) keep = idx.filter((_, k) => k % Math.ceil(idx.length / n) === 0);
        const X = [], Y = [];
        keep.forEach((i, k) => {
          if (k && bad[i] - bad[keep[k - 1] + 1] > 0) { X.push(null); Y.push(null); }        // Lücke: Kurve absetzen
          X.push(r4(+s.x[i])); Y.push(r4(+s.y[i]));
        });
        series.push({ name: String(s.name ?? "").slice(0, 60), x: X, y: Y, ...(s.bar ? { bar: true } : {}), ...(s.pts ? { pts: true } : {}) });
      }
      const v = Array.isArray(p.view) && p.view.length === 4 && p.view.every(fin) && p.view[1] > p.view[0] && p.view[3] > p.view[2] ? p.view.map(r4) : null;
      if (series.length) out.push({ title: String(p.title ?? "").slice(0, 80), xlab: String(p.xlab ?? "").slice(0, 50),
        ylab: String(p.ylab ?? "").slice(0, 50), ...(p.xrev ? { xrev: true } : {}), ...(v ? { view: v } : {}), series });
    }
    return out;
  }
  function range(p) {
    if (p.view) return { x0: p.view[0], x1: p.view[1], y0: p.view[2], y1: p.view[3] };   // feste Ansicht (Rechner-Graph)
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (const s of p.series) for (let i = 0; i < s.x.length; i++) {
      const x = s.x[i], y = s.y[i]; if (!fin(x) || !fin(y)) continue;
      x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y);
      if (s.bar) { y0 = Math.min(y0, 0); y1 = Math.max(y1, 0); }
    }
    if (!fin(x0)) return null;
    if (x1 === x0) { x0 -= 1; x1 += 1; }
    if (y1 === y0) { const d = Math.abs(y0) * 0.1 || 1; y0 -= d; y1 += d; }
    const py = (y1 - y0) * 0.06; return { x0, x1, y0: y0 - py, y1: y1 + py };
  }
  function nice(a, b, n) {
    const span = b - a; if (!(span > 0)) return [a];
    const s0 = span / n, mag = 10 ** Math.floor(Math.log10(s0)), f = s0 / mag;
    const st = (f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10) * mag, out = [];
    for (let v = Math.ceil(a / st) * st; v <= b + st * 1e-9; v += st) out.push(+v.toPrecision(12));
    return out;
  }
  function fmt(v) {
    const a = Math.abs(v);
    const s = a !== 0 && (a >= 1e5 || a < 1e-3) ? v.toExponential(1) : String(+v.toPrecision(6));
    return (EN() ? s : s.replace(".", ",")).replace(/-/g, "−");
  }
  // big = false: Vorschau ohne Achsen; big = true: mit Achsen, Teilung und Beschriftung
  function svgPlot(p, W, H, big) {
    const r = range(p); if (!r) return "";
    PAL = PAL || palette();
    const m = big ? { l: 56, r: 14, t: 8, b: 38 } : { l: 2, r: 2, t: 2, b: 2 };
    const iw = W - m.l - m.r, ih = H - m.t - m.b;
    const X = (x) => m.l + (p.xrev ? (r.x1 - x) : (x - r.x0)) / (r.x1 - r.x0) * iw;
    const Y = (y) => m.t + (r.y1 - y) / (r.y1 - r.y0) * ih;
    const sw = big ? 1.6 : 1.3;
    let h = "";
    if (big) {
      const xt = nice(r.x0, r.x1, 6), yt = nice(r.y0, r.y1, 5);
      h += yt.map((v) => `<line x1="${m.l}" x2="${m.l + iw}" y1="${Y(v).toFixed(1)}" y2="${Y(v).toFixed(1)}" stroke="var(--line,#d8dce4)" stroke-width="1"/>`
        + `<text x="${m.l - 5}" y="${(Y(v) + 3.5).toFixed(1)}" text-anchor="end">${esc(fmt(v))}</text>`).join("");
      h += xt.map((v) => `<line x1="${X(v).toFixed(1)}" x2="${X(v).toFixed(1)}" y1="${m.t + ih}" y2="${m.t + ih + 4}" stroke="var(--muted,#5d6472)"/>`
        + `<text x="${X(v).toFixed(1)}" y="${m.t + ih + 16}" text-anchor="middle">${esc(fmt(v))}</text>`).join("");
      h += `<rect x="${m.l}" y="${m.t}" width="${iw}" height="${ih}" fill="none" stroke="var(--muted,#5d6472)" stroke-width="1"/>`;
      if (p.xlab) h += `<text x="${m.l + iw / 2}" y="${H - 4}" text-anchor="middle">${esc(p.xlab)}</text>`;
      if (p.ylab) h += `<text transform="translate(12 ${m.t + ih / 2}) rotate(-90)" text-anchor="middle">${esc(p.ylab)}</text>`;
    } else if (r.y0 < 0 && r.y1 > 0) h += `<line x1="0" x2="${W}" y1="${Y(0).toFixed(1)}" y2="${Y(0).toFixed(1)}" stroke="var(--line,#d8dce4)"/>`;
    const cid = "lpc" + (++CLIP);
    h += `<clipPath id="${cid}"><rect x="${m.l}" y="${m.t}" width="${iw}" height="${ih}"/></clipPath><g clip-path="url(#${cid})">`;
    p.series.forEach((s, k) => {
      const c = PAL[k % PAL.length];
      if (s.pts) {
        h += s.x.map((x, i) => fin(x) && fin(s.y[i]) ? `<circle cx="${X(x).toFixed(1)}" cy="${Y(s.y[i]).toFixed(1)}" r="${big ? 2.6 : 1.4}" fill="${c}"/>` : "").join("");
        return;
      }
      if (s.bar) {
        const bw = Math.max(1, iw / Math.max(1, s.x.length) * 0.8);
        h += s.x.map((x, i) => fin(x) && fin(s.y[i]) ? `<rect x="${(X(x) - bw / 2).toFixed(1)}" y="${Math.min(Y(s.y[i]), Y(0)).toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.abs(Y(0) - Y(s.y[i])).toFixed(1)}" fill="${c}" opacity=".75"/>` : "").join("");
        return;
      }
      let d = "", pen = false;
      for (let i = 0; i < s.x.length; i++) {
        if (!fin(s.x[i]) || !fin(s.y[i])) { pen = false; continue; }
        d += (pen ? "L" : "M") + X(s.x[i]).toFixed(1) + "," + Y(s.y[i]).toFixed(1); pen = true;
      }
      if (s.x.length === 1) h += `<circle cx="${X(s.x[0]).toFixed(1)}" cy="${Y(s.y[0]).toFixed(1)}" r="2.5" fill="${c}"/>`;
      else h += `<path d="${d}" fill="none" stroke="${c}" stroke-width="${sw}" stroke-linejoin="round" stroke-linecap="round"/>`;
    });
    h += `</g>`;
    return `<svg viewBox="0 0 ${W} ${H}" aria-hidden="true">${h}</svg>`;
  }
  function plotsHtml(plots) {
    const P = packPlots(plots, 1e9); if (!P.length) return "";
    PAL = palette();                                       // je Zeichnen neu (Hell/Dunkel ändert die Akzentfarbe)
    const one = P.length === 1;
    return `<div class="lab-plots${one ? " one" : ""}">` + P.map((p, i) =>
      `<button type="button" class="lab-plot" data-plot="${i}" title="${esc((p.title ? p.title + " – " : "") + tx("Klicken: Grafik vergrössern", "Click: enlarge graph"))}">`
      + svgPlot(p, one ? 200 : 96, one ? 62 : 44, false) + (p.title ? `<span class="pt">${esc(p.title)}</span>` : "") + `</button>`).join("") + `</div>`;
  }
  let POP = null;
  function closePop() {
    if (!POP) return;
    document.removeEventListener("pointerdown", POP.out, true); document.removeEventListener("keydown", POP.key, true);
    POP.el.remove(); const f = POP.from; POP = null;
    if (f && f.isConnected) f.focus();
  }
  function showPlot(plots, i, from) {
    closePop();
    const P = packPlots(plots, 1e9); if (!P.length) return;
    const el = document.createElement("div");
    el.className = "lab-plot-pop"; el.setAttribute("role", "dialog");
    PAL = palette();
    let k = Math.max(0, Math.min(P.length - 1, i));
    const draw = () => {
      const p = P[k], named = p.series.filter((s) => s.name);
      el.setAttribute("aria-label", p.title || tx("Grafik", "Graph"));
      el.innerHTML = `<div class="ph"><b>${esc(p.title || tx("Grafik", "Graph"))}</b>`
        + (P.length > 1 ? `<span class="n">${k + 1}/${P.length}</span><button type="button" data-d="-1" title="${tx("Vorige Grafik", "Previous graph")}">‹</button><button type="button" data-d="1" title="${tx("Nächste Grafik", "Next graph")}">›</button>` : "")
        + `<button type="button" data-x title="${tx("Schliessen (Esc)", "Close (Esc)")}">×</button></div>`
        + svgPlot(p, 560, 300, true)
        + (named.length ? `<div class="lg">${p.series.map((s, j) => s.name ? `<span><i style="background:${PAL[j % PAL.length]}"></i>${esc(s.name)}</span>` : "").join("")}</div>` : "");
      el.querySelectorAll("[data-d]").forEach((b) => b.addEventListener("click", () => { k = (k + +b.dataset.d + P.length) % P.length; draw(); }));
      el.querySelector("[data-x]").addEventListener("click", closePop);
    };
    draw();
    document.body.appendChild(el);
    const a = from && from.getBoundingClientRect ? from.getBoundingClientRect() : { left: 20, right: 20, top: 20, bottom: 20 };
    const w = el.offsetWidth, h = el.offsetHeight, vw = innerWidth, vh = innerHeight;
    let x = a.right + 8; if (x + w > vw - 8) x = Math.max(8, a.left - w - 8); if (x + w > vw - 8) x = Math.max(8, (vw - w) / 2);
    let y = Math.min(Math.max(8, a.top - 20), Math.max(8, vh - h - 8));
    el.style.left = x + "px"; el.style.top = y + "px";
    POP = { el, from,
      out: (ev) => { if (!el.contains(ev.target)) closePop(); },
      key: (ev) => { if (ev.key === "Escape") { ev.stopPropagation(); closePop(); } else if (P.length > 1 && (ev.key === "ArrowRight" || ev.key === "ArrowLeft")) { k = (k + (ev.key === "ArrowRight" ? 1 : -1) + P.length) % P.length; draw(); } } };
    setTimeout(() => { if (POP && POP.el === el) { document.addEventListener("pointerdown", POP.out, true); document.addEventListener("keydown", POP.key, true); } }, 0);
    const c = el.querySelector("[data-x]"); if (c) c.focus();
  }

  function create(el, o) {
    ensureCss();
    el.classList.add("lab-board");
    let pos = { ...(o.pos || {}) }, links = [...(o.links || [])], boxes = [];
    // Nur von Hand gezogene Kästen behalten ihre Lage; die übrigen werden bei jedem Zeichnen neu gestapelt,
    // damit ein gewachsener Kasten (längere Zusammenfassung) den nächsten nicht überdeckt.
    let userPos = new Set(Object.keys(pos));
    const W = 230, GAP = 14, COLX = [20, 320, 620];

    function layout() {
      const used = [0, 0, 0];
      for (const b of boxes) if (b.float || !userPos.has(b.id)) delete pos[b.id];   // „+ Umgebung“ (float) immer zuletzt
      for (const b of [...boxes.filter((x) => !x.float), ...boxes.filter((x) => x.float)]) {
        if (pos[b.id]) continue;
        const c = Math.max(0, Math.min(2, b.col ?? 1));
        // unter den schon platzierten Kästen derselben Spalte
        const below = boxes.filter((x) => x !== b && pos[x.id] && Math.abs(pos[x.id][0] - COLX[c]) < 40)
          .map((x) => pos[x.id][1] + (el.querySelector(`[data-box="${CSS_ID(x.id)}"]`)?.offsetHeight || 80));
        const y = Math.max(20 + used[c], ...below.map((v) => v + GAP), 20);
        pos[b.id] = [COLX[c], y];
        used[c] = y - 20 + (el.querySelector(`[data-box="${CSS_ID(b.id)}"]`)?.offsetHeight || 80) + GAP;
      }
    }
    const CSS_ID = (s) => String(s).replace(/["\\]/g, "\\$&");

    function render() {
      boxes = o.boxes();
      const narrow = el.clientWidth > 0 && el.clientWidth < 700;
      el.classList.toggle("narrow", narrow);
      el.innerHTML = `<svg class="lab-wires" width="1" height="1"></svg>` + boxes.map((b) =>
        `<div class="lab-box ${esc(b.cls || "")}${b.active ? " active" : ""}" data-box="${esc(b.id)}" tabindex="0" role="button"
           aria-label="${esc(b.label || b.title)}">${b.in ? `<span class="lab-port in" aria-hidden="true"></span>` : ""}${b.out ? `<span class="lab-port out" data-out="${esc(b.id)}" title="Ziehen, um zu verbinden" aria-hidden="true"></span>` : ""}
           <div class="bh">${b.kind ? `<span class="k">${esc(b.kind)}</span>` : ""}<span>${esc(b.title)}</span></div>
           ${b.sub || b.html ? `<div class="bb">${b.sub ? esc(b.sub) : ""}${b.html || ""}</div>` : ""}${b.plots ? plotsHtml(b.plots) : ""}</div>`).join("");
      closePop();
      if (!narrow) {
        layout();
        for (const b of boxes) place(b.id);
        wires();
      }
      wire();
    }
    function boxEl(id) { return el.querySelector(`[data-box="${CSS_ID(id)}"]`); }
    function place(id) { const e = boxEl(id), p = pos[id]; if (e && p) { e.style.left = p[0] + "px"; e.style.top = p[1] + "px"; } }

    function wires() {
      const svg = el.querySelector(".lab-wires"); if (!svg || el.classList.contains("narrow")) return;
      let maxX = 0, maxY = 0;
      for (const b of boxes) { const e = boxEl(b.id); if (e) { maxX = Math.max(maxX, e.offsetLeft + e.offsetWidth); maxY = Math.max(maxY, e.offsetTop + e.offsetHeight); } }
      svg.setAttribute("width", maxX + 200); svg.setAttribute("height", maxY + 40);   // Platz für Bögen und Beschriftung rechts
      el.style.minHeight = Math.max(420, maxY + 40) + "px";
      // Pfeilspitze zeigt die Richtung; Kästen untereinander (gleiche Spalte) verbindet ein Bogen rechts aussen
      svg.innerHTML = `<defs><marker id="lab-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="var(--accent,#6d28d9)"/></marker></defs>` + links.map((l, i) => {
        const a = boxEl(l.from), b = boxEl(l.to); if (!a || !b) return "";
        const same = Math.abs(a.offsetLeft - b.offsetLeft) < a.offsetWidth * 0.6;
        let d, lx, ly, anchor = "middle";
        if (same) {
          const x1 = a.offsetLeft + a.offsetWidth + 1, y1 = a.offsetTop + 24, x2 = b.offsetLeft + b.offsetWidth + 2, y2 = b.offsetTop + 24;
          const k = 46 + Math.min(70, Math.abs(y2 - y1) / 4);
          d = `M${x1},${y1} C${x1 + k},${y1} ${x2 + k},${y2} ${x2},${y2}`;
          lx = Math.max(x1, x2) + k * 0.78 + 4; ly = (y1 + y2) / 2 + 4; anchor = "start";
        } else {
          const x1 = a.offsetLeft + a.offsetWidth + 1, y1 = a.offsetTop + 24, x2 = b.offsetLeft - 1, y2 = b.offsetTop + 24;
          d = `M${x1},${y1} C${x1 + Math.max(40, (x2 - x1) / 2)},${y1} ${x2 - Math.max(40, (x2 - x1) / 2)},${y2} ${x2},${y2}`;
          lx = (x1 + x2) / 2; ly = (y1 + y2) / 2 - 5;
        }
        const lab = o.wireLabel ? o.wireLabel(l) : "";
        const hint = (o.wireHint && o.wireHint(l)) || "Klick: Verbindung lösen";
        return `<path class="lab-hit" data-link="${i}" d="${d}"><title>${esc(lab ? lab + " – " : "")}${esc(hint)}</title></path><path class="lab-wire ${esc(l.mode || "")}" d="${d}" marker-end="url(#lab-arrow)"/>`
          + (lab ? `<text class="lab-wlabel" x="${lx}" y="${ly}" text-anchor="${anchor}">${esc(lab)}</text>` : "");
      }).join("");
      svg.querySelectorAll("[data-link]").forEach((p) => p.addEventListener("click", (e) => { e.stopPropagation(); o.onUnlink && o.onUnlink(links[+p.dataset.link]); }));
    }

    function wire() {
      el.querySelectorAll(".lab-box").forEach((e) => {
        const id = e.dataset.box, b = boxes.find((x) => x.id === id);
        e.addEventListener("keydown", (ev) => {
          if (ev.target !== e && ev.target.closest("button, a, input, select, textarea")) return;   // Bedienelemente im Kasten
          if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); o.onOpen && o.onOpen(b); }
        });
        e.querySelectorAll("[data-plot]").forEach((p) => p.addEventListener("click", (ev) => { ev.stopPropagation(); showPlot(b.plots, +p.dataset.plot, p); }));
        e.addEventListener("pointerdown", (ev) => {
          if (ev.button !== 0 || el.classList.contains("narrow")) return;
          if (ev.target.closest("button, a, input, select")) return;
          const out = ev.target.closest("[data-out]");
          if (out) return dragWire(ev, id);
          if (!b.float) dragBox(ev, e, b);
        });
        e.addEventListener("click", (ev) => {
          if (e._moved) { e._moved = false; return; }
          if (ev.target.closest("button, a, input, select, [data-out]")) return;
          o.onOpen && o.onOpen(b);
        });
      });
    }

    function dragBox(ev, e, b) {
      const sx = ev.clientX, sy = ev.clientY, p0 = pos[b.id] || [e.offsetLeft, e.offsetTop];
      let moved = false;
      const mv = (m) => {
        const dx = m.clientX - sx, dy = m.clientY - sy;
        if (!moved && Math.hypot(dx, dy) < 4) return;
        moved = true;
        pos[b.id] = [Math.max(0, Math.round(p0[0] + dx)), Math.max(0, Math.round(p0[1] + dy))];
        place(b.id); wires();
      };
      const up = () => {
        document.removeEventListener("pointermove", mv); document.removeEventListener("pointerup", up);
        if (moved) {
          e._moved = true;
          userPos.add(b.id);
          o.onMove && o.onMove(Object.fromEntries([...userPos].filter((k) => pos[k]).map((k) => [k, pos[k]])));
        }
      };
      document.addEventListener("pointermove", mv); document.addEventListener("pointerup", up);
    }

    function dragWire(ev, fromId) {
      ev.preventDefault();
      const svg = el.querySelector(".lab-wires"), a = boxEl(fromId);
      const r0 = el.getBoundingClientRect();
      const x1 = a.offsetLeft + a.offsetWidth + 1, y1 = a.offsetTop + 24;
      const tmp = document.createElementNS("http://www.w3.org/2000/svg", "path");
      tmp.setAttribute("class", "lab-wire hot"); svg.appendChild(tmp);
      let target = null;
      const mv = (m) => {
        const x2 = m.clientX - r0.left + el.scrollLeft, y2 = m.clientY - r0.top + el.scrollTop;
        tmp.setAttribute("d", `M${x1},${y1} C${x1 + 60},${y1} ${x2 - 60},${y2} ${x2},${y2}`);
        const hit = document.elementFromPoint(m.clientX, m.clientY)?.closest?.(".lab-box");
        const ok = hit && hit.dataset.box !== fromId && boxes.find((x) => x.id === hit.dataset.box && x.in);
        if (target && target !== hit) target.classList.remove("drop");
        target = ok ? hit : null;
        if (target) target.classList.add("drop");
      };
      const up = () => {
        document.removeEventListener("pointermove", mv); document.removeEventListener("pointerup", up);
        tmp.remove();
        if (target) { target.classList.remove("drop"); o.onLink && o.onLink(fromId, target.dataset.box); }
      };
      document.addEventListener("pointermove", mv); document.addEventListener("pointerup", up);
    }

    let rz = 0;
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(() => { clearTimeout(rz); rz = setTimeout(() => { if (el.isConnected && !el.hidden) render(); }, 120); }) : null;
    if (ro) ro.observe(el);

    return {
      render,
      setLinks(l) { links = [...(l || [])]; wires(); },
      setPos(p) { pos = { ...(p || {}) }; userPos = new Set(Object.keys(pos)); render(); },
      get pos() { return { ...pos }; },
      get links() { return [...links]; },
      destroy() { if (ro) ro.disconnect(); closePop(); el.innerHTML = ""; },
    };
  }

  g.LabBoard = { create, packPlots, plotsHtml, showPlot, closePop };
})(window);
