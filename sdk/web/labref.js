/* Folio Lab: gemeinsames Formular für Quellenangaben (eigene Referenzen, Werkstoffwerte, Gleichungen).
 *
 * Jedes Modul liefert diese Datei unter "labref.js" aus (relative URL, funktioniert allein und unter /m/<id>/).
 * Benutzung im eigenen Dialog des Moduls:
 *   body.innerHTML = LabRef.form(rec)          // Felder, vorbelegt mit rec (oder leer)
 *   const rec = LabRef.read(body)              // Eintrag zurücklesen (dict wie labcite.py)
 *   LabRef.errors(rec)                         // fehlende Angaben, [] = in Ordnung
 *   LabRef.short(rec) / LabRef.text(rec)       // "Müller u. a. 2021" / ausgeschriebene Angabe
 * "BibTeX einfügen" füllt die Felder aus einem @article{…}-Eintrag (z. B. aus Zotero, Google Scholar, doi.org).
 */
(function () {
  "use strict";
  const TYPES = [["article", "Zeitschriftenartikel"], ["book", "Buch"], ["chapter", "Buchkapitel"], ["standard", "Norm"],
    ["datasheet", "Datenblatt"], ["web", "Webseite"], ["thesis", "Abschlussarbeit"], ["report", "Bericht"],
    ["dataset", "Datensatz"], ["misc", "Sonstiges"]];
  const CONT = { article: "Zeitschrift", book: "Verlag", chapter: "Buch (Titel)", standard: "Normungsorganisation",
    datasheet: "Hersteller / Herausgeber", web: "Website / Organisation", thesis: "Hochschule", report: "Institution",
    dataset: "Repositorium / Verlag", misc: "Erschienen in / bei" };
  const FIELDS = ["type", "authors", "title", "container", "year", "volume", "issue", "pages", "doi", "url", "accessed",
    "publisher", "edition", "note", "licence"];
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  function css() {
    if (document.getElementById("labref-css")) return;
    const st = document.createElement("style");
    st.id = "labref-css";
    st.textContent = `.lr{display:grid;grid-template-columns:1fr 1fr;gap:6px 10px;font-size:13px}
.lr label{display:flex;flex-direction:column;gap:2px;font-size:12px;opacity:.9}
.lr input,.lr select,.lr textarea{font:inherit;padding:4px 6px;border:1px solid rgba(127,127,127,.45);border-radius:4px;background:transparent;color:inherit}
.lr .w2{grid-column:1/-1}.lr .lr-hint{font-size:11.5px;opacity:.75}
.lr details{grid-column:1/-1}.lr details textarea{width:100%;min-height:70px;box-sizing:border-box;font-family:monospace;font-size:12px}
.lr .lr-err{grid-column:1/-1;color:#b42318;font-size:12px}`;
    document.head.appendChild(st);
  }

  function form(rec, opts) {
    css();
    const r = Object.assign({ type: "article" }, rec || {});
    const o = Object.assign({ title: "Quelle" }, opts || {});
    const f = (k, label, w2, ph) => `<label class="${w2 ? "w2" : ""}">${label}<input data-lr="${k}" value="${esc(r[k])}" placeholder="${esc(ph || "")}"></label>`;
    return `<div class="lr" data-labref>
  <label>Art<select data-lr="type">${TYPES.map(([v, l]) => `<option value="${v}"${v === r.type ? " selected" : ""}>${l}</option>`).join("")}</select></label>
  ${f("year", "Jahr / Ausgabe", false, "2021")}
  ${f("authors", "Autor:innen (Nachname, V.; …) oder Organisation", true, "Müller, A.; Meier, B.")}
  ${f("title", "Titel", true)}
  <label class="w2"><span data-lr-cont>${esc(CONT[r.type] || CONT.misc)}</span><input data-lr="container" value="${esc(r.container)}"></label>
  ${f("volume", "Band / Jahrgang")}${f("issue", "Heft / Nummer")}
  ${f("pages", "Seiten / Tabelle", false, "106-115, Tab. 2")}${f("edition", "Auflage / Version")}
  ${f("doi", "DOI", false, "10.xxxx/…")}${f("url", "URL", false, "https://…")}
  ${f("accessed", "Abgerufen am", false, new Date().toISOString().slice(0, 10))}${f("licence", "Lizenz (falls bekannt)", false, "CC BY 4.0")}
  ${f("note", "Bemerkung (z. B. Prüfbedingungen, Seite der Tabelle)", true)}
  <details><summary>BibTeX einfügen …</summary><textarea data-lr-bib placeholder="@article{…}"></textarea>
    <div class="lr-hint">Eintrag aus Zotero, Google Scholar oder doi.org einfügen; die Felder werden übernommen.</div></details>
  <div class="lr-err" data-lr-err></div>
</div>`;
  }

  function wire(root) {
    const box = root.querySelector("[data-labref]") || root;
    if (box.dataset.lrWired) return;
    box.dataset.lrWired = "1";
    const sel = box.querySelector('[data-lr="type"]');
    if (sel) sel.addEventListener("change", () => { const s = box.querySelector("[data-lr-cont]"); if (s) s.textContent = CONT[sel.value] || CONT.misc; });
    const bib = box.querySelector("[data-lr-bib]");
    if (bib) bib.addEventListener("input", () => {
      const r = parseBibtex(bib.value);
      if (!r) return;
      for (const k of FIELDS) {
        const el = box.querySelector(`[data-lr="${k}"]`);
        if (el && r[k]) { el.value = r[k]; if (k === "type") el.dispatchEvent(new Event("change")); }
      }
    });
  }

  function read(root) {
    wire(root);
    const box = root.querySelector("[data-labref]") || root;
    const r = {};
    for (const k of FIELDS) {
      const el = box.querySelector(`[data-lr="${k}"]`);
      const v = el ? el.value.trim() : "";
      if (v) r[k] = v;
    }
    if (r.doi) r.doi = r.doi.replace(/^(https?:\/\/(dx\.)?doi\.org\/|doi:\s*)/i, "");
    const e = errors(r), err = box.querySelector("[data-lr-err]");
    if (err) err.textContent = e.join(" · ");
    return r;
  }

  function errors(r) {
    const e = [];
    if (!r || !(r.title || r.doi || r.url)) e.push("Titel, DOI oder URL fehlt");
    if (r && r.doi && !/^10\.\d{4,9}\/[^\s{}\\]+$/.test(r.doi)) e.push("DOI sieht nicht wie 10.xxxx/… aus");
    if (r && r.url && !/^https?:\/\/[^\s{}\\]+$/.test(r.url)) e.push("URL muss mit http(s):// beginnen");
    if (r && r.accessed && !/^\d{4}(-\d{2}(-\d{2})?)?$/.test(r.accessed)) e.push("Abrufdatum als JJJJ-MM-TT");
    return e;
  }

  function authors(s) {
    s = (s || "").trim();
    if (!s) return [];
    const parts = s.includes(";") ? s.split(";") : s.includes(" and ") ? s.split(" and ") : [s];
    return parts.map(x => x.trim()).filter(Boolean);
  }
  const surname = a => a.includes(",") ? a.split(",")[0].trim() : a.trim().split(/\s+/).pop();

  function short(r) {
    if (!r) return "";
    const au = authors(r.authors);
    const who = au.length > 2 ? surname(au[0]) + " u. a." : au.length ? au.map(surname).join(" & ") : (r.container || (r.title || "").slice(0, 30));
    return `${who} ${r.year || ""}`.trim();
  }

  function text(r) {
    if (!r) return "";
    const au = authors(r.authors), p = [];
    if (au.length) p.push(au.join("; ") + (r.year ? ` (${r.year})` : "") + ":");
    else if (r.year) p.push(`(${r.year})`);
    if (r.title) p.push(r.title + ".");
    if (r.container) p.push(r.container + (r.volume ? " " + r.volume : "") + (r.issue ? ` (${r.issue})` : "") + (r.pages ? ", " + r.pages : "") + ".");
    if (r.doi) p.push("doi:" + r.doi);
    if (r.url) p.push(r.url + (r.accessed ? ` (abgerufen ${r.accessed})` : ""));
    if (r.note) p.push(r.note);
    return p.join(" ");
  }

  function parseBibtex(s) {
    const m = /@(\w+)\s*\{\s*[^,]*,([\s\S]*)\}\s*$/.exec((s || "").trim());
    if (!m) return null;
    const type = { article: "article", book: "book", incollection: "chapter", inbook: "chapter", manual: "datasheet",
      online: "web", misc: "misc", phdthesis: "thesis", mastersthesis: "thesis", thesis: "thesis", techreport: "report",
      report: "report", dataset: "dataset", standard: "standard" }[m[1].toLowerCase()] || "misc";
    const f = {};
    const re = /(\w+)\s*=\s*(\{((?:[^{}]|\{[^{}]*\})*)\}|"([^"]*)"|(\d+))/g;
    let x;
    while ((x = re.exec(m[2]))) f[x[1].toLowerCase()] = (x[3] ?? x[4] ?? x[5] ?? "").replace(/[{}]/g, "").replace(/\s+/g, " ").trim();
    return {
      type, authors: (f.author || f.editor || "").split(/\s+and\s+/).join("; "), title: f.title || "",
      container: f.journal || f.journaltitle || f.booktitle || f.publisher || f.organization || f.institution || f.school || f.howpublished || "",
      year: f.year || (f.date || "").slice(0, 4), volume: f.volume || "", issue: f.number || f.issue || "",
      pages: (f.pages || "").replace(/--/g, "-"), doi: f.doi || "", url: f.url || "", accessed: f.urldate || "",
      publisher: f.publisher && (f.journal || f.booktitle) ? f.publisher : "", edition: f.edition || "", note: f.note || "",
    };
  }

  window.LabRef = { form, read, wire, errors, short, text, parseBibtex, TYPES };
})();
