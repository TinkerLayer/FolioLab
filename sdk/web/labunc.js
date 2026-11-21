/* Messunsicherheit in den Modulseiten (Runde U). Ohne Abhängigkeiten; nutzt LabUI (falls geladen) für Sprache und Stil.
 *
 *  Eingabe neben jedem Zahlenfeld
 *    LabUnc.attach(input, {key, label, unit: "mm" | () => "mm", onChange})   kleiner ±-Knopf hinter dem Feld; mit
 *                                                          Angabe zeigt er die Standardunsicherheit („± 0,012“)
 *    LabUnc.get(key) → {parts:[…], dof?, note?} | null      LabUnc.set(key, spec)   LabUnc.all() → {key: spec}
 *    LabUnc.load({key: spec})                               gespeicherten Stand wiederherstellen (ersetzt alles)
 *    LabUnc.onChange(fn)                                    nach jeder Änderung (fn(key, spec))
 *    LabUnc.edit(anchor, {value, unit, label, spec}) → Promise<spec | null | undefined>  (undefined = abgebrochen)
 *  Ein Beitrag (parts) hat die Form von labcalc.uncertainty: {kind: u | U | limits | resolution | rel | spec | repeats
 *    | sd | ci | instrument, …}; mehrere Beiträge werden quadratisch addiert.
 *  Verfahren und Ergebnis
 *    LabUnc.methodPicker(el, {method, p, k, onChange})      GUM linear | Monte Carlo | Gauss | Grösstfehler
 *    LabUnc.result(el, res, {compare: async () => cmp, label: true | "K_Q"})   „Wert ± U“, Budget (Fold), Hinweise,
 *                                                          Quellen, Vergleich; label: Grösse vor dem Wert nennen
 *    LabUnc.text(res)                                       Kurztext des Ergebnisses
 *    LabUnc.instrumentsDialog()                             eigene Messmittel anlegen, ändern, teilen
 *  Server: POST api/unc/<aktion> (labunc.route in jedem Modulserver); LabUnc.init({api}) ersetzt den Abruf.
 */
(function (g) {
  "use strict";
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const UI = () => g.LabUI;
  const lang = () => (UI() && UI().lang ? UI().lang() : (document.documentElement.lang || "de")).slice(0, 2) === "en" ? "en" : "de";
  const S = {
    de: {
      btn: "Messunsicherheit angeben", title: "Messunsicherheit", none: "keine Angabe – gilt als exakt", add: "+ Beitrag",
      apply: "Übernehmen", remove: "Entfernen", cancel: "Abbrechen", u: "Standardunsicherheit u", U: "Erweiterte Unsicherheit U (k)",
      limits: "Grenzen ±a", resolution: "Auflösung (Ziffernschritt)", rel: "± % vom Wert", spec: "Herstellerangabe ±(% + Digits)",
      repeats: "Wiederholmessung", sd: "Standardabweichung, n Werte", ci: "Vertrauensbereich", instrument: "Messmittel …",
      dist: "Verteilung", normal: "normal", rect: "Rechteck", tri: "Dreieck", arcsine: "U-förmig", t: "t",
      vals: "Werte (Leerzeichen, ; oder Zeilen)", dof: "Freiheitsgrade", note: "Quelle / Notiz (z. B. Kalibrierschein, Datenblatt)",
      res: "Ergebnis der Eingabe", type: "Typ", useMean: "Mittelwert als Wert übernehmen", params: "Parameter",
      method: "Verfahren", gum: "GUM (linear)", mc: "Monte Carlo (GUM S1)", gauss: "Gausssche Fehlerfortpflanzung", worst: "Grösstfehler",
      p: "Überdeckung", kfix: "fester k", kauto: "k aus ν (t-Verteilung)", budget: "Unsicherheitsbudget", compare: "Verfahren vergleichen",
      h: ["Grösse", "Wert", "Typ", "Vert.", "u(xᵢ)", "νᵢ", "cᵢ", "|cᵢ|·u", "Anteil"], exact: "exakt", sources: "Quellen", notes: "Hinweise",
      inst: "Messmittel", own: "Eigene Messmittel …", ownT: "Eigene Messmittel", name: "Name", unit: "Einheit", lim: "Grenze a (Ausdruck in x)",
      save: "Speichern", del: "Löschen", newI: "Neues Messmittel", exp: "Exportieren", imp: "Importieren", choose: "– wählen –",
      cmpH: ["Verfahren", "Wert", "u", "Intervall / ±", "Bemerkung"], pick: "Messmittel wählen", search: "Suchen …",
      a_note: "Grösstfehler nutzt die Grenzen der Eingaben: Halbbreite a, sonst U bzw. 2u",
      what: "Was passiert hier?", whatT: "Jede Eingangsgrösse bekommt eine Standardunsicherheit (Typ A aus Wiederholungen, Typ B aus Angaben). Das gewählte Verfahren pflanzt sie durch die Rechnung fort; das Budget zeigt, welche Grösse wie viel beiträgt.",
      M: "Versuche", stable: "stabil", unstable: "nicht stabil",
    },
    en: {
      btn: "Enter measurement uncertainty", title: "Measurement uncertainty", none: "none – treated as exact", add: "+ Contribution",
      apply: "Apply", remove: "Remove", cancel: "Cancel", u: "Standard uncertainty u", U: "Expanded uncertainty U (k)",
      limits: "Limits ±a", resolution: "Resolution (digit step)", rel: "± % of value", spec: "Manufacturer spec ±(% + digits)",
      repeats: "Repeat measurements", sd: "Standard deviation, n values", ci: "Confidence interval", instrument: "Instrument …",
      dist: "Distribution", normal: "normal", rect: "rectangular", tri: "triangular", arcsine: "U-shaped", t: "t",
      vals: "Values (space, ; or lines)", dof: "Degrees of freedom", note: "Source / note (e.g. calibration certificate, data sheet)",
      res: "Result of the entry", type: "Type", useMean: "Use the mean as value", params: "Parameters",
      method: "Method", gum: "GUM (linear)", mc: "Monte Carlo (GUM S1)", gauss: "Gaussian error propagation", worst: "Worst case",
      p: "Coverage", kfix: "fixed k", kauto: "k from ν (t distribution)", budget: "Uncertainty budget", compare: "Compare methods",
      h: ["Quantity", "Value", "Type", "Dist.", "u(xᵢ)", "νᵢ", "cᵢ", "|cᵢ|·u", "Share"], exact: "exact", sources: "Sources", notes: "Notes",
      inst: "Instrument", own: "Own instruments …", ownT: "Own instruments", name: "Name", unit: "Unit", lim: "Limit a (expression in x)",
      save: "Save", del: "Delete", newI: "New instrument", exp: "Export", imp: "Import", choose: "– choose –",
      cmpH: ["Method", "Value", "u", "Interval / ±", "Remark"], pick: "Choose instrument", search: "Search …",
      a_note: "Worst case uses the limits of the inputs: half-width a, else U or 2u",
      what: "What happens here?", whatT: "Every input gets a standard uncertainty (type A from repeats, type B from stated values). The chosen method propagates them through the calculation; the budget shows how much each input contributes.",
      M: "trials", stable: "stable", unstable: "not stable",
    },
  };
  const t = (k) => (S[lang()] || S.de)[k] ?? S.de[k] ?? k;
  const num = (x) => { const n = Number(String(x ?? "").trim().replace(/\s/g, "").replace(",", ".").replace("−", "-")); return Number.isFinite(n) ? n : NaN; };
  const loc = (s) => (lang() === "de" ? String(s).replace(".", ",") : String(s));
  const fmtG = (v, sig = 3) => { if (v == null || v === "inf") return "∞"; const n = +v; if (!Number.isFinite(n)) return "∞"; let s = n.toPrecision(sig); if (/e/.test(s)) { const [m, e] = s.split("e"); s = `${+m}·10^${+e}`; } else s = String(+s); return loc(s); };

  // ------------------------------------------------------------------ Server
  let api = async (action, body) => {
    const r = await fetch("api/unc/" + action, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ lang: lang(), ...(body || {}) }) });
    const j = await r.json().catch(() => ({ error: "HTTP " + r.status }));
    if (!r.ok && !j.error) j.error = "HTTP " + r.status;
    return j;
  };
  let INSTR = null;
  async function instrumentsList(force) {
    if (!INSTR || force) { const j = await api("instruments", {}); if (j && !j.error) INSTR = j; else throw new Error((j && j.error) || "?"); }
    return INSTR;
  }

  // ------------------------------------------------------------------ Stil
  const CSS = `
.lu-btn{font:inherit;font-size:11.5px;line-height:1.4;padding:0 6px;margin-left:4px;border-radius:6px;border:1px dashed var(--line,#bbb);background:transparent;color:inherit;opacity:.65;cursor:pointer;white-space:nowrap;vertical-align:middle}
.lu-btn:hover,.lu-btn:focus-visible{opacity:1;border-style:solid;border-color:var(--accent,#2a6fdb)}
.lu-btn.on{opacity:1;border-style:solid;border-color:var(--accent,#2a6fdb);color:var(--accent,#2a6fdb)}
.lu-pop{position:absolute;z-index:80;width:min(440px,94vw);max-height:min(78vh,640px);overflow:auto;background:var(--panel,#fff);color:inherit;border:1px solid var(--line,#ccc);border-radius:10px;box-shadow:0 12px 32px rgba(0,0,0,.25);padding:10px 12px;font-size:13px;line-height:1.45}
.lu-pop h4{margin:0 0 6px;font-size:13.5px}.lu-pop .lu-sub{opacity:.7;font-size:12px;margin-bottom:6px}
.lu-part{border:1px solid var(--line,#ddd);border-radius:8px;padding:6px 8px;margin:6px 0;display:grid;gap:4px}
.lu-part .lu-ph{display:flex;justify-content:space-between;align-items:center;gap:6px;font-weight:600;font-size:12px}
.lu-row{display:flex;flex-wrap:wrap;gap:6px;align-items:center}.lu-row label{display:flex;gap:4px;align-items:center;font-size:12px}
.lu-pop input,.lu-pop select,.lu-pop textarea{font:inherit;font-size:12.5px;padding:2px 5px;border:1px solid var(--line,#ccc);border-radius:5px;background:var(--bg,#fff);color:inherit;min-width:0}
.lu-pop input[type=text].n{width:7em}.lu-pop textarea{width:100%;min-height:44px;resize:vertical}
.lu-x{border:0;background:transparent;cursor:pointer;color:inherit;opacity:.6;font-size:14px}.lu-x:hover{opacity:1}
.lu-foot{display:flex;gap:6px;justify-content:flex-end;margin-top:8px;flex-wrap:wrap}
.lu-foot button,.lu-add{font:inherit;font-size:12.5px;padding:3px 10px;border-radius:6px;border:1px solid var(--line,#ccc);background:transparent;color:inherit;cursor:pointer}
.lu-foot .pri{background:var(--accent,#2a6fdb);border-color:var(--accent,#2a6fdb);color:#fff}
.lu-sum{margin-top:6px;padding:6px 8px;border-radius:8px;background:var(--soft,rgba(127,127,127,.08));font-size:12.5px}
.lu-err{color:#b42318}
.lu-res .lu-main{font-weight:600}.lu-res table{border-collapse:collapse;font-size:12px;width:100%}
.lu-res th,.lu-res td{padding:2px 5px;text-align:right;border-bottom:1px solid var(--line,#e3e3e3);white-space:nowrap}
.lu-res th:first-child,.lu-res td:first-child{text-align:left;white-space:normal}
.lu-bar{display:inline-block;height:7px;border-radius:3px;background:var(--accent,#2a6fdb);vertical-align:middle;margin-left:4px;opacity:.75}
.lu-meth{display:flex;flex-wrap:wrap;gap:6px;align-items:center}.lu-meth select,.lu-meth input{font:inherit;font-size:12.5px}
.lu-note{font-size:12px;opacity:.85;margin:3px 0}
.lu-ilist{max-height:220px;overflow:auto;border:1px solid var(--line,#ddd);border-radius:6px;margin:4px 0}
.lu-ilist button{display:block;width:100%;text-align:left;border:0;border-bottom:1px solid var(--line,#eee);background:transparent;color:inherit;padding:4px 7px;cursor:pointer;font:inherit;font-size:12.5px}
.lu-ilist button:hover,.lu-ilist button:focus-visible{background:var(--soft,rgba(127,127,127,.1))}
.lu-ilist .g{font-weight:600;font-size:11.5px;opacity:.7;padding:4px 7px;background:var(--soft,rgba(127,127,127,.06))}
.lu-hist{display:block;width:100%;height:46px;margin-top:4px}`;
  let cssDone = false;
  function ensureCss() { if (cssDone) return; cssDone = true; const s = document.createElement("style"); s.textContent = CSS; document.head.appendChild(s); }

  // ------------------------------------------------------------------ Register
  const REG = new Map();      // key -> {spec, inputs:Set}
  const listeners = [];
  function onChange(fn) { listeners.push(fn); }
  function fire(key, spec) { for (const f of listeners) { try { f(key, spec); } catch (e) { console.error(e); } } }
  const has = (spec) => !!(spec && Array.isArray(spec.parts) && spec.parts.length);
  function get(key) { const r = REG.get(key); return r && has(r.spec) ? JSON.parse(JSON.stringify(r.spec)) : null; }
  function set(key, spec, silent) {
    const r = REG.get(key) || { spec: null, btns: new Set() };
    r.spec = has(spec) ? spec : null; REG.set(key, r);
    r.btns.forEach((b) => { if (b.isConnected) paint(b, key); else r.btns.delete(b); });   // abgehängte Knöpfe (neu gezeichnete Seite) vergessen
    if (!silent) fire(key, r.spec);
  }
  function all() { const o = {}; REG.forEach((r, k) => { if (has(r.spec)) o[k] = r.spec; }); return o; }
  function load(obj) { REG.forEach((r, k) => set(k, null, true)); for (const [k, v] of Object.entries(obj || {})) set(k, v, true); }

  // Standardunsicherheit lokal (für den Knopf; Messmittel kommen vom Server und stehen als u_cache in der Angabe)
  const FAC = { rect: Math.sqrt(3), tri: Math.sqrt(6), arcsine: Math.SQRT2, normal: 3 };
  function partU(p, value) {
    const v = Math.abs(num(value)) || 0;
    switch (p.kind) {
      case "u": return num(p.u);
      case "U": return num(p.U) / (num(p.k) || 2);
      case "limits": return num(p.a) / (FAC[p.dist || "rect"] || FAC.rect);
      case "resolution": return num(p.d) / 2 / FAC.rect;
      case "rel": return num(p.pct) / 100 * v / (FAC[p.dist || "rect"] || FAC.rect);
      case "spec": return ((num(p.pct) || 0) / 100 * v + (num(p.digits) || 0) * (num(p.d) || 0)) / FAC.rect;
      case "repeats": { const a = parseVals(p.values); if (a.length < 2) return NaN; const m = a.reduce((x, y) => x + y, 0) / a.length; const s = Math.sqrt(a.reduce((x, y) => x + (y - m) ** 2, 0) / (a.length - 1)); return s / Math.sqrt(a.length); }
      case "sd": return num(p.sd) / Math.sqrt(num(p.n) || 1);
      case "ci": return num(p.half) / 1.96;
      case "instrument": return num(p.u_cache);
      default: return NaN;
    }
  }
  function specU(spec, value) { if (!has(spec)) return 0; let s = 0; for (const p of spec.parts) { const u = partU(p, value); if (Number.isFinite(u)) s += u * u; } return Math.sqrt(s); }
  function parseVals(v) {
    if (Array.isArray(v)) return v.map(num).filter(Number.isFinite);
    return String(v ?? "").replace(/(\d),(\d)/g, "$1.$2").split(/[\s;]+/).map(num).filter(Number.isFinite);
  }

  // ------------------------------------------------------------------ ±-Knopf
  function attach(input, o) {
    ensureCss();
    o = o || {};
    const key = o.key || input.id || input.name;
    if (!key) throw new Error("LabUnc.attach: key fehlt");
    if (input._lu) return input._lu;
    const b = document.createElement("button");
    b.type = "button"; b.className = "lu-btn"; b.dataset.luKey = key;
    b._lu = { input, o };
    input.insertAdjacentElement("afterend", b);
    input._lu = b;
    const r = REG.get(key) || { spec: null, btns: new Set() };
    r.btns.forEach((x) => { if (!x.isConnected) r.btns.delete(x); });
    r.btns.add(b); REG.set(key, r);
    paint(b, key);
    b.addEventListener("click", async () => {
      const unit = typeof o.unit === "function" ? o.unit() : (o.unit || "");
      const res = await edit(b, { value: input.value, unit, label: o.label || key, spec: get(key) });
      if (res === undefined) return;
      if (res && res.useMean != null) { input.value = loc(String(+res.useMean.toPrecision(10))); input.dispatchEvent(new Event("input", { bubbles: true })); input.dispatchEvent(new Event("change", { bubbles: true })); delete res.useMean; }
      set(key, res);
      if (o.onChange) o.onChange(get(key));
    });
    input.addEventListener("input", () => paint(b, key));
    return b;
  }
  function paint(b, key) {
    const spec = (REG.get(key) || {}).spec;
    const inp = b._lu && b._lu.input;
    const u = specU(spec, inp ? inp.value : 0);
    b.classList.toggle("on", has(spec));
    b.textContent = has(spec) ? (Number.isFinite(u) && u > 0 ? "± " + fmtG(u, 2) : "± …") : "±";
    b.title = has(spec) ? `${t("u")}: ${fmtG(u, 3)}` : t("btn");
    b.setAttribute("aria-label", b.title);
  }

  // ------------------------------------------------------------------ Schwebefenster
  let openPop = null;
  function closePop() { if (openPop) { const p = openPop; openPop = null; p.remove(); if (p._done) p._done(undefined); } }
  function pop(anchor, html) {
    ensureCss(); closePop();
    const p = document.createElement("div");
    p.className = "lu-pop"; p.setAttribute("role", "dialog"); p.innerHTML = html;
    document.body.appendChild(p);
    const r = anchor.getBoundingClientRect(), vw = document.documentElement.clientWidth;
    const w = p.offsetWidth, h = p.offsetHeight;
    let left = Math.min(Math.max(8, r.left + window.scrollX), window.scrollX + vw - w - 8);
    let top = r.bottom + window.scrollY + 6;
    if (r.bottom + h + 12 > window.innerHeight && r.top > h + 12) top = r.top + window.scrollY - h - 6;
    p.style.left = left + "px"; p.style.top = top + "px";
    // wächst der Inhalt (Beitrag, Messmittelliste), im Fenster halten
    const fit = () => {
      const b = p.getBoundingClientRect();
      if (b.bottom > window.innerHeight - 8) p.style.top = Math.max(window.scrollY + 8, window.scrollY + window.innerHeight - b.height - 8) + "px";
    };
    new MutationObserver(fit).observe(p, { childList: true, subtree: true });
    const off = (ev) => { if (openPop === p && !p.contains(ev.target) && !anchor.contains(ev.target) && !ev.target.closest(".lu-pop")) { document.removeEventListener("mousedown", off, true); closePop(); } };
    setTimeout(() => document.addEventListener("mousedown", off, true), 0);
    p.addEventListener("keydown", (e) => { if (e.key === "Escape") { e.stopPropagation(); closePop(); anchor.focus && anchor.focus(); } });
    openPop = p;
    return p;
  }

  const KINDS = ["u", "U", "limits", "resolution", "rel", "spec", "repeats", "sd", "ci", "instrument"];
  const DISTS = ["rect", "tri", "normal", "arcsine"];
  const sel = (name, opts, v) => `<select data-f="${name}">${opts.map((o) => `<option value="${o}"${o === v ? " selected" : ""}>${esc(t(o))}</option>`).join("")}</select>`;
  const fld = (name, label, v, cls = "n") => `<label>${esc(label)} <input type="text" class="${cls}" data-f="${name}" value="${esc(v ?? "")}" inputmode="decimal"></label>`;
  function partHtml(p, i) {
    let body = "";
    switch (p.kind) {
      case "u": body = fld("u", "u", p.u) + fld("dof", t("dof"), p.dof); break;
      case "U": body = fld("U", "U", p.U) + fld("k", "k", p.k ?? 2); break;
      case "limits": body = fld("a", "a", p.a) + `<label>${t("dist")} ${sel("dist", DISTS, p.dist || "rect")}</label>`; break;
      case "resolution": body = fld("d", "d", p.d); break;
      case "rel": body = fld("pct", "%", p.pct) + `<label>${t("dist")} ${sel("dist", DISTS, p.dist || "rect")}</label>`; break;
      case "spec": body = fld("pct", "%", p.pct) + fld("digits", "Digits", p.digits ?? 2) + fld("d", "d", p.d); break;
      case "repeats": body = `<textarea data-f="values" placeholder="${esc(t("vals"))}">${esc(Array.isArray(p.values) ? p.values.map((x) => loc(x)).join(" ") : p.values || "")}</textarea>
        <label><input type="checkbox" data-f="useMean"${p.useMean ? " checked" : ""}> ${esc(t("useMean"))}</label>`; break;
      case "sd": body = fld("sd", "s", p.sd) + fld("n", "n", p.n); break;
      case "ci": body = fld("half", "±", p.half) + fld("level", "%", p.level ?? 95) + fld("n", "n", p.n); break;
      case "instrument": body = `<div class="lu-row"><b data-inst>${esc(p.name || p.id || "")}</b> <button type="button" class="lu-add" data-pickinst="${i}">${esc(t("pick"))}</button></div>
        ${(p.paramDefs || []).map((d) => fld("param:" + d.name, d.label, (p.params || {})[d.name] ?? d.default, "n")).join("")}`; break;
    }
    return `<div class="lu-part" data-i="${i}"><div class="lu-ph"><span>${esc(t(p.kind))}</span><button type="button" class="lu-x" data-del="${i}" aria-label="×">×</button></div><div class="lu-row">${body}</div></div>`;
  }

  function edit(anchor, o) {
    return new Promise((resolve) => {
      const st = { parts: JSON.parse(JSON.stringify((o.spec && o.spec.parts) || [])), note: (o.spec && o.spec.note) || "" };
      const p = pop(anchor, "");
      p._done = resolve;
      let tm = 0;
      const render = () => {
        p.innerHTML = `<h4>${esc(t("title"))}: ${esc(o.label || "")}</h4>
          <div class="lu-sub">${esc(loc(o.value ?? ""))} ${esc(o.unit || "")}</div>
          <div data-parts>${st.parts.length ? st.parts.map(partHtml).join("") : `<div class="lu-note">${esc(t("none"))}</div>`}</div>
          <div class="lu-row"><select data-addkind aria-label="${esc(t("add"))}"><option value="">${esc(t("add"))}</option>${KINDS.map((k) => `<option value="${k}">${esc(t(k))}</option>`).join("")}</select></div>
          <label style="display:block;margin-top:6px;font-size:12px">${esc(t("note"))}<textarea data-note>${esc(st.note)}</textarea></label>
          <div class="lu-sum" data-sum></div>
          <div class="lu-foot"><button type="button" data-own>${esc(t("own"))}</button><span style="flex:1"></span>
            <button type="button" data-rm>${esc(t("remove"))}</button><button type="button" data-cancel>${esc(t("cancel"))}</button><button type="button" class="pri" data-ok>${esc(t("apply"))}</button></div>`;
        preview();
      };
      const read = () => {
        p.querySelectorAll(".lu-part").forEach((el) => {
          const pt = st.parts[+el.dataset.i]; if (!pt) return;
          el.querySelectorAll("[data-f]").forEach((f) => {
            const k = f.dataset.f;
            const v = f.type === "checkbox" ? f.checked : f.value;
            if (k.startsWith("param:")) { pt.params = pt.params || {}; pt.params[k.slice(6)] = num(v); }
            else if (k === "values") pt.values = parseVals(v);
            else if (k === "dist" || k === "useMean") pt[k] = v;
            else pt[k] = v === "" ? undefined : num(v);
          });
        });
        const n = p.querySelector("[data-note]"); if (n) st.note = n.value;
      };
      const clean = () => st.parts.map((x) => { const c = {}; for (const [k, v] of Object.entries(x)) if (v !== undefined && v !== "" && !(typeof v === "number" && !Number.isFinite(v)) && !["name", "paramDefs", "useMean"].includes(k)) c[k] = v; return c; });
      const preview = () => {
        clearTimeout(tm);
        const box = p.querySelector("[data-sum]"); if (!box) return;
        if (!st.parts.length) { box.textContent = t("none"); return; }
        tm = setTimeout(async () => {
          const j = await api("preview", { value: num(o.value), unit: o.unit || "", parts: clean() });
          if (!p.isConnected) return;
          if (!j || j.error) { box.innerHTML = `<span class="lu-err">${esc((j && j.error) || "?")}</span>`; return; }
          (j.parts || []).forEach((q, i) => { if (st.parts[i] && st.parts[i].kind === "instrument") st.parts[i].u_cache = q.u; });
          const rows = (j.parts || []).map((q) => `<div>${esc(q.label)}: u = ${fmtG(q.u)} <span style="opacity:.7">(${esc(t(q.dist) || q.dist)}${q.type === "A" ? ", Typ A" : ""})</span></div>`).join("");
          box.innerHTML = `${rows}<div style="margin-top:3px"><b>u = ${fmtG(j.u)}</b> ${esc(o.unit || "")} · ${t("dof")} ν = ${fmtG(j.dof)} · ${t("type")} ${esc(j.type || "–")}</div>`;
        }, 180);
      };
      const finish = (val) => { p._done = null; closePop(); resolve(val); };
      p.addEventListener("input", () => { read(); preview(); });
      p.addEventListener("change", async (e) => {
        if (e.target.matches("[data-addkind]")) {
          const k = e.target.value; if (!k) return; read();
          const np = { kind: k }; if (k === "limits" || k === "rel") np.dist = "rect"; if (k === "U") np.k = 2; if (k === "ci") np.level = 95;
          st.parts.push(np); render();
          if (k === "instrument") pickInstrument(p.querySelector(`[data-pickinst="${st.parts.length - 1}"]`), st.parts.length - 1);
          else { const f = p.querySelector(`.lu-part[data-i="${st.parts.length - 1}"] [data-f]`); if (f) f.focus(); }
        } else { read(); preview(); }
      });
      async function pickInstrument(btn, i) {
        let L; try { L = await instrumentsList(); } catch (e) { UI() && UI().chip ? alert(e.message) : alert(e.message); return; }
        const box = document.createElement("div");
        box.innerHTML = `<input type="search" placeholder="${esc(t("search"))}" style="width:100%"><div class="lu-ilist"></div>`;
        btn.closest(".lu-part").appendChild(box);
        const list = box.querySelector(".lu-ilist"), q = box.querySelector("input");
        const draw = () => {
          const s = q.value.trim().toLowerCase(), by = {};
          for (const it of L.items) if (!s || (it.name + " " + it.id).toLowerCase().includes(s)) (by[it.group || ""] = by[it.group || ""] || []).push(it);
          list.innerHTML = L.groups.filter((gr) => by[gr.id]).map((gr) => `<div class="g">${esc(gr.name)}</div>` + by[gr.id].map((it) =>
            `<button type="button" data-id="${esc(it.id)}">${esc(it.name)}<small style="opacity:.65"> · ${esc(it.unit || "")}${it.ref && it.ref.title ? " · " + esc(String(it.ref.title).split(" ")[0] + " " + (String(it.ref.title).split(" ")[1] || "")) : ""}</small></button>`).join("")).join("");
        };
        draw(); q.focus();
        q.addEventListener("input", (e) => { e.stopPropagation(); draw(); });
        list.addEventListener("click", (e) => {
          const b = e.target.closest("[data-id]"); if (!b) return;
          const it = L.items.find((x) => x.id === b.dataset.id); read();
          st.parts[i] = { kind: "instrument", id: it.id, name: it.name, paramDefs: it.params || [], params: Object.fromEntries((it.params || []).map((d) => [d.name, d.default])) };
          render();
        });
      }
      p.addEventListener("click", (e) => {
        const d = e.target.closest("[data-del]"); if (d) { read(); st.parts.splice(+d.dataset.del, 1); render(); return; }
        const pi = e.target.closest("[data-pickinst]"); if (pi) { read(); pickInstrument(pi, +pi.dataset.pickinst); return; }
        if (e.target.closest("[data-cancel]")) return finish(undefined);
        if (e.target.closest("[data-rm]")) return finish(null);
        if (e.target.closest("[data-own]")) { instrumentsDialog().then(() => { INSTR = null; }); return; }
        if (e.target.closest("[data-ok]")) {
          read();
          const rep = st.parts.find((x) => x.kind === "repeats" && x.useMean);
          const out = st.parts.length ? { parts: clean(), ...(st.note.trim() ? { note: st.note.trim() } : {}) } : null;
          if (out && rep) { const a = parseVals(rep.values); if (a.length) out.useMean = a.reduce((x, y) => x + y, 0) / a.length; }
          return finish(out);
        }
      });
      // Instrument-Parameter beim Wiederöffnen: Definitionen nachladen
      (async () => {
        if (!st.parts.some((x) => x.kind === "instrument")) return;
        try { const L = await instrumentsList(); st.parts.forEach((x) => { if (x.kind !== "instrument") return; const it = L.items.find((y) => y.id === x.id); if (it) { x.name = it.name; x.paramDefs = it.params || []; } }); render(); } catch (e) { /* offline */ }
      })();
      render();
      const f = p.querySelector("[data-f], [data-addkind]"); if (f) f.focus();
    });
  }

  // ------------------------------------------------------------------ Verfahren
  function methodPicker(el, o) {
    ensureCss(); o = o || {};
    const st = { method: o.method || "gum", p: o.p || 0.95, k: o.k || null };
    el.classList.add("lu-meth");
    const draw = () => {
      el.innerHTML = `<label>${esc(t("method"))} <select data-m>${["gum", "mc", "gauss", "worst"].map((m) => `<option value="${m}"${m === st.method ? " selected" : ""}>${esc(t(m))}</option>`).join("")}</select></label>
        ${st.method === "gum" || st.method === "mc" ? `<label>${esc(t("p"))} <select data-p>${[0.6827, 0.9, 0.95, 0.9545, 0.99].map((v) => `<option value="${v}"${Math.abs(v - st.p) < 1e-9 ? " selected" : ""}>${loc((v * 100).toFixed(v === 0.6827 || v === 0.9545 ? 2 : 0))} %</option>`).join("")}</select></label>` : ""}
        ${st.method === "gum" ? `<label><input type="checkbox" data-kf${st.k ? " checked" : ""}> ${esc(t("kfix"))}</label>${st.k ? `<input type="text" data-k value="${loc(st.k)}" style="width:4em" aria-label="k">` : ""}` : ""}`;
    };
    draw();
    const emit = () => o.onChange && o.onChange({ method: st.method, p: st.p, k: st.method === "gum" ? st.k : null });
    el.addEventListener("change", (e) => {
      if (e.target.matches("[data-m]")) st.method = e.target.value;
      else if (e.target.matches("[data-p]")) st.p = +e.target.value;
      else if (e.target.matches("[data-kf]")) st.k = e.target.checked ? 2 : null;
      else if (e.target.matches("[data-k]")) { const k = num(e.target.value); st.k = k > 0 ? k : 2; }
      draw(); emit();
    });
    return { get: () => ({ ...st }), set: (v) => { Object.assign(st, v || {}); draw(); } };
  }

  // ------------------------------------------------------------------ Ergebnis
  function roundPm(y, U) {
    if (!(U > 0) || !Number.isFinite(U)) return [String(+(+y).toPrecision(6)), "0", 6];
    const d = 1 - Math.floor(Math.log10(Math.abs(U)));
    if (d > 0) return [(+y).toFixed(d), (+U).toFixed(d), d];
    const q = 10 ** -d; return [String(Math.round(y / q) * q), String(Math.round(U / q) * q), d];
  }
  function text(r) {
    if (!r || r.error) return r && r.error ? "⚠ " + r.error : "";
    return r.text || "";
  }
  function hist(r) {
    const h = r.hist; if (!h || !h.counts) return "";
    const mx = Math.max(...h.counts), n = h.counts.length, e0 = h.edges[0], e1 = h.edges[n], X = (v) => ((v - e0) / (e1 - e0)) * 300;
    const bars = h.counts.map((c, i) => `<rect x="${(i / n) * 300}" y="${40 - (c / mx) * 38}" width="${300 / n - 0.6}" height="${(c / mx) * 38}" fill="currentColor" opacity=".35"/>`).join("");
    return `<svg class="lu-hist" viewBox="0 0 300 42" preserveAspectRatio="none" role="img" aria-label="Histogramm">${bars}
      <line x1="${X(r.lo)}" x2="${X(r.lo)}" y1="0" y2="42" stroke="var(--accent,#2a6fdb)"/><line x1="${X(r.hi)}" x2="${X(r.hi)}" y1="0" y2="42" stroke="var(--accent,#2a6fdb)"/></svg>`;
  }
  function budgetHtml(r) {
    const rows = (r.budget || []).map((b) => b.exact
      ? `<tr><td>${esc(b.name)}${b.label && b.label !== b.name ? ` <small>${esc(b.label)}</small>` : ""}</td><td>${fmtG(b.value, 6)} ${esc(b.unit || "")}</td><td colspan="7" style="text-align:left;opacity:.7">${esc(t("exact"))}</td></tr>`
      : `<tr><td>${esc(b.name)}${b.label && b.label !== b.name ? ` <small>${esc(b.label)}</small>` : ""}</td><td>${fmtG(b.value, 6)} ${esc(b.unit || "")}</td><td>${esc(b.type || "")}</td>
        <td>${esc(t(b.dist) || b.dist || "")}</td><td>${fmtG(b.u)}</td><td>${fmtG(b.dof)}</td><td>${fmtG(b.c)}</td><td>${fmtG(b.cu)}</td>
        <td>${fmtG(b.share, 3)} %<span class="lu-bar" style="width:${Math.max(1, Math.min(60, b.share * 0.6))}px"></span></td></tr>`).join("");
    return `<table><thead><tr>${t("h").map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table>`;
  }
  function refsHtml(r) {
    const refs = (r.refs_full || []);
    return refs.length ? `<ul style="margin:3px 0 0 16px;padding:0">${refs.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : "";
  }
  function result(el, r, o) {
    ensureCss(); o = o || {};
    if (!r) { el.innerHTML = ""; return; }
    if (r.error) { el.innerHTML = `<div class="lu-err">${esc(r.error)}</div>`; return; }
    const meta = r.method === "mc" ? ` · M = ${loc(r.M)} ${esc(t("M"))} (${esc(r.stable ? t("stable") : t("unstable"))})` : "";
    const fold = (id, sum, inner) => `<details class="lab-fold" data-fold="${id}"><summary>${esc(sum)}</summary>${inner}</details>`;
    el.classList.add("lu-res");
    const lab = o.label === true ? (r.label || r.name || "") : (o.label || "");
    el.innerHTML = `<div class="lu-main">${lab ? `<b>${esc(lab)}</b> = ` : ""}${esc(text(r))}</div>
      <div class="lu-note">${esc(r.method_name || t(r.method))}${meta}</div>
      ${r.method === "mc" ? hist(r) : ""}
      ${(r.note_texts || []).map((n) => `<div class="lu-note">⚠ ${esc(n)}</div>`).join("")}
      ${r.method === "worst" ? `<div class="lu-note">${esc(t("a_note"))}${r.limits_note && r.limits_note.length ? " (" + esc(r.limits_note.join(", ")) + ")" : ""}</div>` : ""}
      ${fold("unc-budget", t("budget"), budgetHtml(r))}
      ${o.compare ? fold("unc-compare", t("compare"), `<div data-cmp style="font-size:12px">…</div>`) : ""}
      ${fold("unc-what", t("what"), `<div class="lu-note">${esc(t("whatT"))}</div>${refsHtml(r)}`)}`;
    if (o.compare) {
      const d = el.querySelector('[data-fold="unc-compare"]');
      d.addEventListener("toggle", async () => {
        if (!d.open || d._done) return; d._done = true;
        const box = d.querySelector("[data-cmp]");
        try { compareTable(box, await o.compare()); } catch (e) { box.innerHTML = `<span class="lu-err">${esc(e.message)}</span>`; }
      });
    }
  }
  function compareTable(el, cmp) {
    const rows = ["gum", "mc", "gauss", "worst"].map((m) => {
      const r = cmp && cmp[m]; if (!r) return "";
      if (r.error) return `<tr><td>${esc(t(m))}</td><td colspan="4" class="lu-err">${esc(r.error)}</td></tr>`;
      const pm = r.method === "gum" || r.method === "gauss" ? "± " + fmtG(r.U) : `[${fmtG(r.lo, 5)}; ${fmtG(r.hi, 5)}]`;
      return `<tr><td>${esc(t(m))}</td><td>${fmtG(r.value, 6)}</td><td>${r.u != null ? fmtG(r.u) : "–"}</td><td>${pm}</td><td style="text-align:left">${esc(r.method === "gum" ? "k = " + fmtG(r.k) : r.method === "mc" ? "M = " + r.M : r.method === "worst" ? "Σ|c|a = " + fmtG(r.linear) : "k = 1")}</td></tr>`;
    }).join("");
    el.innerHTML = `<table><thead><tr>${t("cmpH").map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table>`;
  }

  // ------------------------------------------------------------------ Eigene Messmittel
  function instrumentsDialog() {
    ensureCss();
    return new Promise((resolve) => {
      const d = document.createElement("dialog");
      d.className = "lu-pop"; d.style.position = "fixed"; d.style.width = "min(560px,94vw)";
      document.body.appendChild(d);
      let L = null, cur = null;
      const close = () => { d.close(); d.remove(); resolve(); };
      const draw = () => {
        const own = (L ? L.items : []).filter((x) => x.own);
        d.innerHTML = `<h4>${esc(t("ownT"))}</h4>
          <div class="lu-ilist">${own.map((x) => `<button type="button" data-ed="${esc(x.id)}">${esc(x.name)} <small style="opacity:.65">${esc(x.unit || "")}</small></button>`).join("") || `<div class="lu-note" style="padding:4px 7px">–</div>`}</div>
          <div class="lu-row"><button type="button" class="lu-add" data-new>${esc(t("newI"))}</button><button type="button" class="lu-add" data-exp>${esc(t("exp"))}</button>
            <label class="lu-add" style="cursor:pointer">${esc(t("imp"))}<input type="file" accept=".json,application/json" data-imp hidden></label></div>
          ${cur ? `<div class="lu-part"><div class="lu-row">${fld("name", t("name"), cur.name, "")}${fld("unit", t("unit"), cur.unit, "n")}</div>
            ${(cur.parts || [{}]).map((q, i) => `<div class="lu-row" data-pi="${i}">${fld("plabel", "", q.label || "", "n")}${fld("pa", t("lim"), q.a || "", "")} ${sel("pdist", DISTS, q.dist || "rect")}</div>`).join("")}
            <div class="lu-row"><button type="button" class="lu-add" data-addp>+ ${esc(t("lim"))}</button></div>
            <label style="font-size:12px">${esc(t("note"))}<textarea data-f="note">${esc(cur.note || "")}</textarea></label>
            <div class="lu-row">${fld("calibrated", "Kalibriert am", cur.calibrated || "", "n")}</div>
            <div class="lu-foot">${cur.id ? `<button type="button" data-delI>${esc(t("del"))}</button>` : ""}<button type="button" class="pri" data-save>${esc(t("save"))}</button></div><div data-msg></div></div>` : ""}
          <div class="lu-foot"><button type="button" data-close>${esc(t("cancel"))}</button></div>`;
      };
      const readCur = () => {
        if (!cur) return;
        const v = (n) => { const f = d.querySelector(`[data-f="${n}"]`); return f ? f.value : ""; };
        cur.name = v("name"); cur.unit = v("unit"); cur.note = v("note"); cur.calibrated = v("calibrated");
        cur.parts = [...d.querySelectorAll("[data-pi]")].map((r) => ({ label: r.querySelector('[data-f="plabel"]').value, a: r.querySelector('[data-f="pa"]').value, dist: r.querySelector('[data-f="pdist"]').value }));
      };
      d.addEventListener("click", async (e) => {
        const ed = e.target.closest("[data-ed]");
        if (ed) { cur = JSON.parse(JSON.stringify(L.items.find((x) => x.id === ed.dataset.ed))); draw(); return; }
        if (e.target.closest("[data-new]")) { cur = { name: "", unit: "", parts: [{ a: "", dist: "rect" }] }; draw(); return; }
        if (e.target.closest("[data-addp]")) { readCur(); cur.parts.push({ a: "", dist: "rect" }); draw(); return; }
        if (e.target.closest("[data-close]")) return close();
        if (e.target.closest("[data-exp]")) {
          const j = await api("own_export", {});
          const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([JSON.stringify(j, null, 1)], { type: "application/json" }));
          a.download = "messmittel.json"; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000); return;
        }
        if (e.target.closest("[data-delI]")) { await api("own_delete", { id: cur.id }); cur = null; L = await instrumentsList(true); draw(); return; }
        if (e.target.closest("[data-save]")) {
          readCur();
          const j = await api("own_save", { item: { id: cur.id, name: cur.name, unit: cur.unit, parts: cur.parts, note: cur.note, calibrated: cur.calibrated, params: cur.params || [], source: cur.source } });
          const m = d.querySelector("[data-msg]");
          if (!j || j.error) { if (m) m.innerHTML = `<span class="lu-err">${esc((j && j.error) || "?")}</span>`; return; }
          cur = null; L = await instrumentsList(true); draw();
        }
      });
      d.addEventListener("change", async (e) => {
        if (!e.target.matches("[data-imp]")) return;
        const f = e.target.files && e.target.files[0]; if (!f) return;
        try { const data = JSON.parse(await f.text()); await api("own_import", { data }); L = await instrumentsList(true); draw(); } catch (err) { alert(err.message); }
      });
      d.addEventListener("cancel", (e) => { e.preventDefault(); close(); });
      instrumentsList(true).then((x) => { L = x; draw(); }).catch((e) => { d.innerHTML = `<div class="lu-err">${esc(e.message)}</div><div class="lu-foot"><button type="button" data-close>×</button></div>`; });
      draw();
      d.showModal();
    });
  }

  g.LabUnc = {
    init: (o) => { if (o && o.api) api = o.api; }, attach, get, set, all, load, onChange, edit, methodPicker, result, compareTable,
    text, roundPm, instrumentsDialog, specU, strings: S,
  };
})(window);
