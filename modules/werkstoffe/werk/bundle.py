"""Ergebnisse für den Berichtseditor (Format folio-lab-bundle/1).

Ein Bericht besteht aus Abschnitten {"tool", "req"}; jeder wird mit demselben Werkzeug wie auf der Seite gerechnet
(tools.run) und schreibt Abbildungen, Tabellen, Werte, Daten, Quellen und Methodentext. Werte, die aus der
Werkstoffdatenbank, der Literatur oder einem Modell stammen, sind in Bildunterschrift und Text als solche benannt.
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

_SDK = Path(__file__).resolve().parents[3] / "sdk" / "python"
if _SDK.is_dir() and str(_SDK) not in sys.path:
    sys.path.insert(0, str(_SDK))

import labcite  # noqa: E402
from labbundle import _UNI, Bundle, booktabs, num, slugify, step_tag, tex_escape  # noqa: E402

from . import charts as CH  # noqa: E402
from . import refs as RF  # noqa: E402
from . import tools as T  # noqa: E402

_EXTRA = {"ε̇": r"$\dot\varepsilon$", "η": r"$\eta$", "κ": r"$\kappa$", "½": r"$\frac{1}{2}$", "⅓": r"$\frac{1}{3}$",
          "⅔": r"$\frac{2}{3}$", "ϑ": r"$\vartheta$", "Θ": r"$\Theta$", "′": "'", "″": r"\ensuremath{^{\prime\prime}}", "⁄": "/", "Å": r"\AA{}", "≠": r"$\neq$",
          "₁₂": r"$_{12}$"}

NAMES = {
    "auswahl": ("Werkstoffauswahl", "Material selection"), "karten": ("Werkstoffvergleich", "Material comparison"),
    "kristall": ("Kristallstruktur", "Crystal structure"), "struktur": ("Werkstoffstruktur", "Material structure"), "gitter": ("Gittermodell", "Lattice model"), "xrd": ("Röntgenbeugung", "X-ray diffraction"),
    "phasen": ("Zustandsdiagramm", "Phase diagram"), "stahl": ("Stahl", "Steel"), "laminat": ("Laminat", "Laminate"),
    "ermuedung": ("Ermüdung", "Fatigue"), "weibull": ("Weibull-Statistik", "Weibull statistics"),
    "bruch": ("Bruchmechanik", "Fracture mechanics"), "haerte": ("Härte und Gefüge", "Hardness and microstructure"),
    "korrosion": ("Korrosion", "Corrosion"), "kriechen": ("Kriechen", "Creep"),
}


def tx(s) -> str:
    s = str(s)
    for k, v in _EXTRA.items():
        s = s.replace(k, "\x00" + str(list(_EXTRA).index(k)) + "\x01")
    out = tex_escape(s)
    return re.sub("\x00(\\d+)\x01", lambda m: _EXTRA[list(_EXTRA)[int(m.group(1))]], out)


_UNI_ONLY = {k: v for k, v in {**_UNI, **_EXTRA}.items() if k not in "<>" and not k.isascii()}


def uni(s: str) -> str:
    """Unicode-Zeichen ausserhalb von $…$ in LaTeX umsetzen (LaTeX-Befehle bleiben unberührt)."""
    parts = re.split(r"(?<!\\)\$", s)
    for i in range(0, len(parts), 2):
        p = parts[i]
        for k in sorted(_UNI_ONLY, key=len, reverse=True):
            if k in p:
                p = p.replace(k, _UNI_ONLY[k])
        parts[i] = p
    return "$".join(parts).replace("$$", "")


def big(v: float, lang: str) -> str:
    """Grosse Zahlen als a·10^n."""
    if v is None:
        return "--"
    if abs(v) < 1e5:
        return num(v, 0, lang)
    e = int(f"{v:e}".split("e")[1])
    m = v / 10 ** e
    return (num(m, 2, lang).rstrip("0").rstrip(",.") if abs(m - round(m)) > 1e-9 else str(int(round(m)))) + f"\\,$\\cdot$\\,10$^{{{e}}}$"


SYM = {"E": "E", "rho": "\\rho", "Rp": "R_p", "KIc": "K_{Ic}", "lambda": "\\lambda", "alpha": "\\alpha", "Rm": "R_m",
       "G": "G", "cp": "c_p", "Tm": "T_m", "nu": "\\nu", "A": "A"}


def idx_tex(expo: dict) -> str:
    """Kennzahl als LaTeX, z. B. {'E': 0.5, 'rho': -1} -> $E^{1/2}/\\rho$."""
    from fractions import Fraction

    def term(p, e):
        f = Fraction(abs(e)).limit_denominator(6)
        s = SYM.get(p, "\\mathrm{" + p + "}")
        return s if f == 1 else f"{s}^{{{f.numerator}/{f.denominator}}}" if f.denominator != 1 else f"{s}^{{{f.numerator}}}"
    num_ = [term(p, e) for p, e in expo.items() if e > 0]
    den = [term(p, e) for p, e in expo.items() if e < 0]
    top = " ".join(num_) or "1"
    if not den:
        return f"${top}$"
    bot = " ".join(den)
    return f"${top}/" + (f"({bot})" if len(den) > 1 else bot) + "$"


def pname(ph: dict, lang: str) -> str:
    return (ph.get("name_en") if lang == "en" and ph.get("name_en") else ph.get("name")) or ph.get("id", "")


LAM_SRC = {"Einstellung": ("Einstellung", "setting"), "Datei": ("aus der Datei", "from the file"),
           "angenommen: Cu Kα1/Kα2": ("nicht in der Datei, Cu Kα1/Kα2 angenommen", "not in the file, Cu Kα1/Kα2 assumed")}


def used_items(sections: list[dict]) -> list[str]:
    """IDs geladener Dateien, die die Abschnitte brauchen (für die Quelle des Bundles)."""
    out = []
    for s in sections:
        r = s.get("req") or {}
        for k in ("item",):
            if r.get(k) and r[k] not in out:
                out.append(str(r[k]))
        conv = (r.get("convert") or {}).get("table")
        if conv and conv not in out:
            out.append(str(conv))
        for pid in [r.get("phase"), (r.get("opt") or {}).get("phase_ref")] + list((r.get("opt") or {}).get("overlay") or []) \
                + list((r.get("opt") or {}).get("quant_ids") or []) + list((r.get("opt") or {}).get("search_ids") or []):
            if isinstance(pid, str) and pid.startswith("cif:") and pid[4:] not in out:
                out.append(pid[4:])
    return out


class Sec:
    """Sammelt, was ein Abschnitt schreibt."""

    def __init__(self, b: Bundle, lang: str, inc: dict, pid: str, ctx: T.Ctx):
        self.b, self.lang, self.inc, self.pid, self.ctx = b, lang, inc, pid, ctx
        self.m: list[str] = []          # Methodik
        self.r: list[str] = []          # Ergebnisse
        self.vals: list[tuple] = []
        self.own: list[str] = []        # Schlüssel eigener Quellen (Freitext des Nutzers), schon in der Literatur

    @property
    def de(self):
        return self.lang == "de"

    def L(self, de, en):
        return de if self.de else en

    def id(self, s):
        return f"{self.pid}-{s}" if s else self.pid

    def cite(self, keys) -> list[str]:
        if not self.inc.get("citations", True):
            return []
        keys = [keys] if isinstance(keys, str) else list(keys or [])
        out = RF.cite(self.b, [k for k in keys if k not in self.own])
        return out + [k for k in keys if k in self.own and k not in out]

    def own_cite(self, name: str, src: str) -> str:
        """Eigene Quellenangabe (Freitext) als Literatureintrag; gibt den Schlüssel zurück, leer ohne Angabe."""
        if not src or not self.inc.get("citations", True):
            return ""
        key = "own-" + slugify(src, 30)
        if key not in self.own:
            m = re.search(r"https?://\S+", src)
            url = m.group(0).rstrip(".,;)") if m else ""
            title = (src.replace(url, "").strip(" ,;:-") if url else src) or url
            rec = labcite.from_legacy(title, url=url)
            n0 = len(self.b.bib)
            labcite.to_bib(self.b, key, rec)
            _sortkey(self.b, n0, src[:40])
            self.own.append(key)
        return key

    def c(self, keys) -> str:
        k = self.cite(keys)
        return f"~\\cite{{{','.join(k)}}}" if k else ""

    def fig(self, f, id, caption, cites=None, width="0.8"):
        if self.inc.get("figures", True):
            self.b.add_figure(f, self.id(id), caption, width=width, dpi=150, cites=self.cite(cites or []), steps=[self.pid])
        else:
            CH.close(f)

    def table(self, id, head, rows, align, caption, cites=None, notes="", small=False):
        if self.inc.get("tables", True) and rows:
            self.b.add_table(self.id(id), booktabs([tx(h) for h in head], rows, align, small=small, escape_header=False),
                             caption, notes=notes, cites=self.cite(cites or []), steps=[self.pid])

    def val(self, key, label, v, nd=2, unit="", text=None):
        if v is None:
            return None
        k = re.sub(r"[^A-Za-z0-9-]+", "-", f"{self.pid}-{key}").strip("-")
        self.vals.append((k, tx(label), num(v, nd, self.lang, unit), text if text is not None else f"{v:.{nd}f} {unit}".strip()))
        return f"\\labval{{{self.b.slug}}}{{{k}}}"

    def unc(self, res: dict):
        """Messunsicherheit (Runde U): Werte ± U, Budgettabellen und ein Methodensatz mit Quellen."""
        rs = [dict(v, name=self.id("" if k == self.pid else k.lower())) for k, v in (res.get("unc") or {}).items()
              if isinstance(v, dict) and not v.get("error") and v.get("value") is not None]
        if not rs:
            return
        from labcalc import uncertainty as UN
        o = UN.to_report(self.b, rs, self.lang)
        if o["latex"]:
            self.m.append(o["latex"])

    def data(self, id, header, rows, desc, labels=None, plot=None):
        if self.inc.get("data", True) and rows:
            self.b.add_data_csv(self.id(id), header, rows, desc, labels=labels or {}, plot=plot or {})

    def finish(self):
        self.m = [uni(x) for x in self.m]
        self.r = [uni(x) for x in self.r]
        if self.inc.get("values", True) and self.vals:
            self.b.add_values(self.vals)


def _sortkey(b: Bundle, n0: int, text: str):
    """Sortierschlüssel für einen eben angelegten Eintrag ohne Autor (sonst BibTeX-Warnung). Nicht als Argument
    key= übergeben: das stösst mit dem Parameter key von add_citation zusammen."""
    if len(b.bib) > n0:
        b.bib[-1] = b.bib[-1].replace(",\n", f",\n  key = {{{tex_escape(text)}}},\n", 1)


def _file_cite(s: Sec, it: dict) -> str:
    key = "data-" + slugify(it["name"], 30)
    if s.inc.get("citations", True):
        n0 = len(s.b.bib)
        s.b.add_citation(key, "misc", title=tex_escape(it["name"]),
                         howpublished=s.L("Messdatei", "Data file"))
        _sortkey(s.b, n0, it["name"])
    return f"~\\cite{{{key}}}"


def _src_keys(res) -> list[str]:
    return [r["key"] for r in (res.get("refs") or [])]


def _unchecked(s: Sec, res) -> str:
    """Hinweis, wenn Quellenangaben nicht am Original geprüft wurden."""
    if any(r.get("unchecked") for r in res.get("refs") or []):
        return s.L(" Einzelne Quellenangaben sind als nicht am Original geprüft gekennzeichnet.",
                   " Some source details are marked as not checked against the original.")
    return ""


# ----------------------------------------------------------------------------- Auswahl
def _as_entered(v: float, lang: str) -> str:
    """Eigene Werte so, wie sie eingegeben wurden (bis 6 Stellen, ohne angehängte Nullen)."""
    t = f"{v:.6g}"
    if "e" in t:
        m, e = t.split("e")
        return f"${m.replace('.', ',' if lang == 'de' else '.')}\\cdot 10^{{{int(e)}}}$"
    return t.replace(".", ",") if lang == "de" else t


def w_auswahl(s: Sec, res: dict, req: dict):
    rk = res.get("rank") or {}
    idx = req.get("index")
    from . import select as SL
    form = idx_tex(res.get("expo") or {}) if res.get("expo") else ""
    iname = SL.INDICES[idx][0 if s.de else 1].split(":")[0] if idx in SL.INDICES else ""
    lab = f"{tx(iname)} ({form})" if iname else form
    pts = res["points"]
    keys = sorted({q for p in pts for q in p["q"]})
    view = req.get("view") or {}
    groups = bool(view.get("groups"))
    mp = any(p["mp"] for p in pts) and not groups
    sel = next((p for p in pts if p["id"] == view.get("sel")), None) if view.get("sel") else None
    fam = (sel or {}).get("familie") or view.get("fam") if groups else None
    fname = SL.family_name(fam, s.lang) if fam else ""
    what = (s.L("Umrisse: Gesamtbereich jeder Werkstofffamilie aus Werten und Spannen der Werkstoffdatenbank",
                "outlines: overall range of each material family from the values and ranges of the materials database")
            + (s.L(f"; Punkte: {fname}", f"; points: {fname}") if fam else "")) if groups else \
        s.L("Werte aus der Werkstoffdatenbank", "values from the materials database")
    if sel:
        what += s.L(f"; grün: {sel['name']} mit seiner Spanne", f"; green: {sel['name']} with its range")
    cap = tx(s.L(f"Werkstoffe im Diagramm {res['y']['label']} über {res['x']['label']} ({what}"
                 f"{', Dreiecke: berechnet (DFT), Materials Project' if mp else ''})",
                 f"Materials in the chart {res['y']['label']} versus {res['x']['label']} ({what}"
                 f"{', triangles: computed (DFT), Materials Project' if mp else ''})"))
    own = res.get("own") or []
    okeys = {p["id"]: s.own_cite(p["name"], p.get("src", "")) for p in own}
    if own:
        names = ", ".join(p["name"] for p in own)
        cap += tx(s.L(f"; Rauten: eigene Werte ({names})", f"; diamonds: own values ({names})"))
    if rk:
        cap += s.L(f"; Zahlen: Rang nach der Kennzahl {lab}.", f"; numbers: rank by the index {lab}.")
    else:
        cap += "."
    s.fig(CH.fig_ashby(res, s.lang, view=view), "diagramm", cap,
          cites=["ashby"] + keys + (["jain2013"] if mp else []) + [k for k in okeys.values() if k])
    if own:
        no_src = s.L("ohne Quellenangabe", "no source given")
        orows = [[tx(p["name"]), _as_entered(p["x"], s.lang), _as_entered(p["y"], s.lang),
                  (f"\\cite{{{okeys[p['id']]}}}" if okeys[p["id"]] else
                   (tx(p["src"]) if p.get("src") else "\\emph{" + no_src + "}"))] for p in own]
        s.table("eigen", [s.L("Werkstoff", "Material"), f"{res['x']['label']} [{res['x']['unit']}]",
                          f"{res['y']['label']} [{res['y']['unit']}]", s.L("Quelle", "Source")], orows, "lrrl",
                s.L("Eigene Werte im Diagramm (vom Nutzer eingegeben, mit seiner Quellenangabe).",
                    "Own values in the chart (entered by the user, with their source)."),
                cites=[k for k in okeys.values() if k])
        miss = [p["name"] for p in own if not p.get("src")]
        s.m.append(s.L(f"Zusätzlich sind {len(own)} eigene Werte eingetragen; ihre Quellen nennt die Tabelle der "
                       "eigenen Werte." + (f" Für {tx(', '.join(miss))} ist keine Quelle angegeben." if miss else ""),
                       f"In addition, {len(own)} own values are plotted; the table of own values gives their sources."
                       + (f" No source is given for {tx(', '.join(miss))}." if miss else "")))
    if rk:
        rows = [[str(r["rank"]), tx(r["name"]) + (r" (DFT)" if r["mp"] else "") + ("$^\\dagger$" if r["unchecked"] else "")
                 + (s.L(" (eigen)", " (own)") if r.get("own") else ""),
                 tx(res["classes"].get(r["klasse"], s.L("eigener Wert", "own value") if r.get("own") else r["klasse"])),
                 num(r["M"], 3 if r["M"] < 10 else 2, s.lang)]
                for r in rk["ranked"][:20]]
        note = s.L(r"$^\dagger$ Mindestens ein Wert ist nicht am Original geprüft (siehe Werkstoffdatenbank).",
                   r"$^\dagger$ At least one value is not checked against the original (see materials database).") \
            if any(r["unchecked"] for r in rk["ranked"][:20]) else ""
        s.table("rang", [s.L("Rang", "Rank"), s.L("Werkstoff", "Material"), s.L("Klasse", "Class"), "M"], rows, "rllr",
                s.L(f"Rangliste nach der Kennzahl {lab} ({rk['n_ok']} Werkstoffe mit allen Werten, {rk['n_out']} "
                    "ausgeschlossen).", f"Ranking by the index {lab} ({rk['n_ok']} materials with all values, "
                                        f"{rk['n_out']} excluded)."), cites=["ashby"], notes=note)
        if rk["ranked"]:
            top = rk["ranked"][0]
            v1 = s.val("best-M", s.L("Kennzahl des besten Werkstoffs", "Index of the best material"), top["M"], 3)
            s.r.append(s.L(f"Nach der Kennzahl {lab} steht {tx(top['name'])} vorn (M = {v1}, in den Einheiten der Datenbank).",
                           f"By the index {lab}, {tx(top['name'])} ranks first (M = {v1}, in the units of the database)."))
        if req.get("limits"):
            lim = "; ".join(f"{l['prop']} {('≥ ' + str(l['min'])) if l.get('min') not in (None, '') else ''}"
                            f"{(' ≤ ' + str(l['max'])) if l.get('max') not in (None, '') else ''}" for l in req["limits"])
            s.m.append(s.L(f"Ausgeschlossen wurden Werkstoffe ausserhalb der Grenzen {tx(lim)} sowie solche ohne die "
                           "nötigen Werte.", f"Materials outside the limits {tx(lim)} and those without the required "
                                             "values were excluded."))
    s.m.insert(0, s.L(f"Die Auswahl folgt der Methode nach Ashby{s.c('ashby')}: eine Leistungskennzahl M als Produkt von "
                      "Potenzen der Eigenschaften wird für alle Werkstoffe der Datenbank berechnet und absteigend "
                      "geordnet; im doppelt-logarithmischen Diagramm liegen Werkstoffe gleicher Kennzahl auf Geraden. "
                      "Die Werte sind Typwerte oder Spannen aus der Literatur; die Quelle jedes Werts nennt die "
                      "Werkstoffdatenbank." + (" Einträge aus dem Materials Project sind mit Dichtefunktionaltheorie "
                                               f"berechnet{s.c(['jain2013', 'dejong2015'])} und als solche gekennzeichnet." if mp else ""),
                      f"The selection follows Ashby's method{s.c('ashby')}: a performance index M, a product of powers of "
                      "properties, is computed for all materials of the database and sorted in descending order; on "
                      "double-logarithmic axes, materials of equal index lie on straight lines. Values are typical "
                      "values or ranges from the literature; the materials database gives the source of each value."
                      + (" Entries from the Materials Project are computed by density functional theory"
                         f"{s.c(['jain2013', 'dejong2015'])} and marked as such." if mp else "")))
    s.data("punkte", ["x", "y", "name", "klasse"], [[p["x"], p["y"], p["name"].replace(",", " "), p["klasse"]] for p in pts]
           + [[p["x"], p["y"], p["name"].replace(",", " "), "eigen"] for p in own],
           tx(s.L("Punkte des Diagramms.", "Points of the chart.")),
           labels={"x": tx(f"{res['x']['label']} [{res['x']['unit']}]"), "y": tx(f"{res['y']['label']} [{res['y']['unit']}]")},
           plot={"x": "x", "y": "y", "style": "marks"})


def w_karten(s: Sec, res: dict, req: dict):
    cards = res["cards"]
    if not cards:
        return
    keys = sorted({w["key"] for c in cards for w in c["werte"] if w.get("key")})
    head = [s.L("Eigenschaft", "Property")] + [c["name"] for c in cards]
    rows = []
    for r in res["rows"]:
        cells = [tx(r["label"])]
        for w in r["cells"]:
            if not w:
                cells.append("--")
            else:
                cells.append(tx(w["text"]) + (f"~\\cite{{{w['key']}}}" if w.get("key") and s.inc.get("citations", True) else "")
                             + ("$^\\dagger$" if w.get("nicht_geprueft") else ""))
        rows.append(cells)
    s.cite(keys)
    note = s.L(r"$^\dagger$ Nicht am Original geprüft.", r"$^\dagger$ Not checked against the original.") \
        if any(w and w.get("nicht_geprueft") for r in res["rows"] for w in r["cells"]) else ""
    s.table("vergleich", head, rows, "l" + "r" * len(cards),
            tx(s.L("Kennwerte im Vergleich (Werkstoffdatenbank, Quelle je Wert).",
                   "Properties compared (materials database, source per value).")), cites=keys, notes=note, small=True)
    s.m.append(s.L("Die Kennwerte stammen aus der gemeinsamen Werkstoffdatenbank; jeder Wert trägt seine Quelle und "
                   "die Art (Typwert, Mindestwert, Spanne).", "The properties come from the shared materials database; "
                   "each value carries its source and its kind (typical, minimum, range)."))


# ----------------------------------------------------------------------------- Kristall
def _phase_cite(s: Sec, info: dict) -> list[str]:
    if info.get("q"):
        return [info["q"]]
    src = info.get("source")
    if src and s.inc.get("citations", True):
        key = "cif-" + slugify(info.get("name") or info["id"], 24)
        labcite.to_bib(s.b, key, src)
        return [key]
    return []


def w_kristall(s: Sec, res: dict, req: dict):
    lam = res["lam"][0]
    pc = _phase_cite(s, res)
    s.cite(pc)
    name = res["name"]
    s.fig(CH.fig_lines(res, s.lang), "linien",
          tx(s.L(f"Berechnetes Pulverdiagramm von {name} (λ = {lam:.5f} Å, Linien und Profil, Pseudo-Voigt).",
                 f"Computed powder pattern of {name} (λ = {lam:.5f} Å, lines and profile, pseudo-Voigt).")),
          cites=["cullity", "itc_c"] + pc)
    try:
        f = CH.fig_cell(res, s.lang)
        s.fig(f, "zelle", tx(s.L(f"Elementarzelle von {name}.", f"Unit cell of {name}.")), cites=pc, width="0.5")
    except Exception:  # noqa: BLE001 - 3D-Bild ist Beigabe
        pass
    L = res["lines"][:30]
    s.table("linien", ["hkl", "d [Å]", "2θ [°]", "m", "I_rel [%]"],
            [[tx(x["hkl"]), num(x["d"], 4, s.lang), num(x["tth"], 3, s.lang), str(x["m"]), num(x["Irel"], 1, s.lang)] for x in L],
            "lrrrr", tx(s.L(f"Berechnete Reflexe von {name}.", f"Computed reflections of {name}.")), cites=["cullity"] + pc, small=True)
    c = res["cell"]
    va = s.val("a", "a", c["a"], 4, "Å")
    vv = s.val("V", s.L("Zellvolumen", "Cell volume"), c["V"], 2, "Å³")
    vr = s.val("rho", s.L("Röntgendichte", "X-ray density"), res.get("rho"), 3, "g/cm³")
    s.r.append(s.L(f"{tx(name)} ({tx(res['spacegroup'])}): a = {va}, Zellvolumen {vv}" + (f", Röntgendichte {vr}." if vr else "."),
                   f"{tx(name)} ({tx(res['spacegroup'])}): a = {va}, cell volume {vv}" + (f", X-ray density {vr}." if vr else ".")))
    s.m.append(s.L("Reflexlagen aus der Bragg-Gleichung mit dem metrischen Tensor der Zelle; Intensitäten "
                   "$I = m\\,|F_{hkl}|^2\\,LP$ mit dem Strukturfaktor aus den Atomlagen (Symmetrie und Zentrierung "
                   f"ausgeschrieben), Atomformfaktoren nach Cromer und Mann{s.c('itc_c')}, isotropem Debye-Waller-Faktor "
                   "(ohne Angabe $B = 0{,}5$\\,Å$^2$) und Lorentz-Polarisationsfaktor für ungefiltertes Licht"
                   f"{s.c('cullity')}. Die Intensitäten sind integriert; Absorption, Textur und Extinktion sind nicht "
                   "berücksichtigt." + (f" Struktur nach{s.c(pc)}." if pc else ""),
                   "Reflection positions from Bragg's law with the metric tensor of the cell; intensities "
                   "$I = m\\,|F_{hkl}|^2\\,LP$ with the structure factor from the atom positions (symmetry and centring "
                   f"expanded), Cromer-Mann form factors{s.c('itc_c')}, an isotropic Debye-Waller factor (if not given "
                   f"$B = 0.5$\\,Å$^2$) and the Lorentz-polarisation factor for unfiltered radiation{s.c('cullity')}. "
                   "Intensities are integrated; absorption, texture and extinction are not considered."
                   + (f" Structure after{s.c(pc)}." if pc else "")).replace("Å", r"\AA{}"))


# ----------------------------------------------------------------------------- Struktur
def _vk(tool: str, view: str) -> list[str]:
    """Feste Quellen einer Ansicht (views.py) für ihre Abbildung."""
    from . import views as VW
    return VW.figure_keys(tool, view)


def _panel_cites(p: dict) -> list[str]:
    keys = list(p.get("q") or [])
    for k in p.get("refs") or []:
        k = k["key"] if isinstance(k, dict) else k
        if k not in keys:
            keys.append(k)
    if any(str(k).startswith("cod") for k in keys):
        keys.append("grazulis2012")                         # die Datenbank selbst, neben dem Eintrag
    return keys


def _panel_caption(s: Sec, p: dict, name: str, at: str) -> str:
    kind = (s.L("Skizze, schematisch, nicht massstäblich", "Sketch, schematic, not to scale") if p.get("kind") == "sketch" else
            s.L("Elementarzelle aus Strukturdaten", "Unit cell from structure data") if p.get("phase") else
            s.L("Modell, kein Messbild", "Model, not a micrograph"))
    ph = p.get("phase") or {}
    extra = ""
    if ph:
        extra = (f" {ph.get('spacegroup')}" if ph.get("spacegroup") else "") + (f", COD {ph['cod']}" if ph.get("cod") else "")
    parts = [f"{name}, {p['title']}{extra} {at}.", (p.get("caption") or "").strip(), kind + "."]
    return tx(" ".join(x for x in parts if x).replace("..", "."))


def w_struktur(s: Sec, res: dict, req: dict):
    lang = s.lang
    mat = res.get("material") or {}
    name = res.get("name") or mat.get("name") or str(req.get("material", ""))
    keys = [r["key"] for r in res.get("refs") or []]
    if res.get("mech"):                                    # Mechanismus: acht Bilder der Folge
        fr = res["frames"]
        pick = sorted({round(k * (len(fr) - 1) / 7) for k in range(8)})
        sel = [{**fr[k], "label": f"{round(100 * fr[k].get('f', 0)):d} %"} for k in pick]
        s.fig(CH.fig_temper_frames({"frames": sel}, lang, "mech"), "mech",
              tx(s.L(f"{name}: Bildfolge (schematisch, nach den angegebenen Quellen).",
                     f"{name}: sequence of frames (schematic, after the sources given).")), cites=keys[:6], width="0.95")
        s.table("mech", ["#", s.L("Fortschritt", "Progress"), s.L("Was geschieht", "What happens")],
                [[str(n + 1), tx(sel[n]["label"]),
                  tx(sel[n].get("caption") or "") if n == 0 or sel[n].get("caption") != sel[n - 1].get("caption") else s.L("(wie oben)", "(as above)")]
                 for n in range(len(sel))],
                "rlp{0.62\\linewidth}", tx(s.L(f"{name}: Abschnitte der Bildfolge.", f"{name}: stages of the sequence.")),
                cites=keys[:6], small=True)
        s.r.append(tx(" ".join(dict.fromkeys(f.get("caption") or "" for f in sel))))
        s.m.append(s.L(f"Schematische Bildfolge „{tx(name)}“ nach der Literatur{s.c(keys[:5])}; Geometrie und Ablauf sind angedeutet, nicht berechnet.",
                       f"Schematic sequence “{tx(name)}” after the literature{s.c(keys[:5])}; geometry and course are indicated, not computed."))
        return
    if res.get("atlas"):                                   # Gefügeatlas: Skizze und Steckbrief
        inf = res.get("info") or {}
        p = (res.get("panels") or [None])[0]
        if p:
            s.fig(CH.fig_panel(p, lang), "atlas", tx(s.L(f"Gefüge {name} (Skizze, schematisch; typischer Bildausschnitt {inf.get('scale', '')}).",
                                                        f"Microstructure {name} (sketch, schematic; typical field of view {inf.get('scale', '')}).")),
                  cites=keys[:4], width="0.85")
        hv = inf.get("hv") or []
        s.table("atlas", [s.L("Merkmal", "Property"), s.L("Angabe", "Value")],
                [[tx(s.L("Beschreibung", "Description")), tx(inf.get("what", ""))],
                 [tx(s.L("Entsteht durch", "Formed by")), tx(inf.get("conditions", ""))],
                 [tx(s.L("Ätzung", "Etchant")), tx(inf.get("etch", ""))],
                 [tx(s.L("Härte (typisch)", "Hardness (typical)")), f"{num(hv[0], 0, lang)}–{num(hv[1], 0, lang)} HV" if len(hv) == 2 else "–"]],
                "lp{0.7\\linewidth}", tx(s.L(f"Steckbrief {name}.", f"Fact sheet {name}.")), cites=keys[:4], small=True)
        s.r.append(tx(f"{name}: {inf.get('what', '')}"))
        s.m.append(s.L(f"Gefügeskizze „{tx(name)}“ nach Lehrbüchern und Atlanten{s.c(keys[:4])}, schematisch und nicht massstäblich.",
                       f"Microstructure sketch “{tx(name)}” after textbooks and atlases{s.c(keys[:4])}, schematic and not to scale."))
        return
    if res.get("frames"):                                  # Wärmebehandlung
        fr = [f for f in res["frames"] if not f.get("inter")]      # Schlüsselbilder; Zwischenbilder nur im Browser
        steps = res.get("steps") or []
        s.fig(CH.fig_temper_path(res, lang), "weg",
              tx(s.L(f"Wärmebehandlung von {name}: Temperaturverlauf mit den Zeitpunkten der Bilder (Heiz- und Abkühlzeiten angenommen).",
                     f"Heat treatment of {name}: temperature path with the times of the frames (heating and cooling times assumed).")),
              cites=_vk("struktur", "weg"), width="0.8")
        view = str(req.get("show") or "")
        s.fig(CH.fig_temper_frames(res, lang, view), "bilder",
              tx(s.L(f"{name} entlang der Wärmebehandlung, je Bild dieselbe Ansicht (Modell bzw. Skizze, schematisch).",
                     f"{name} along the heat treatment, the same view in each frame (model or sketch, schematic).")),
              cites=keys[:6], width="0.95")
        s.table("schritte", [s.L("Schritt", "Step"), "T [°C]", s.L("Halten [h]", "Hold [h]"), s.L("Abkühlen", "Cooling")],
                [[tx(x.get("name") or str(n + 1)), num(x.get("T", 0), 0, lang), num(x.get("t", 0) or 0, 2, lang),
                  tx(s.L("abgeschreckt", "quenched") if x.get("quench") else s.L("an Luft", "in air"))] for n, x in enumerate(steps)],
                "lrrl", tx(s.L(f"Schritte der Wärmebehandlung von {name}.", f"Heat-treatment steps of {name}.")))
        s.table("bilder", ["#", s.L("Bild", "Frame"), "t [h]", "T [°C]", s.L("Zustand", "State")],
                [[str(n + 1), tx(f["label"]), num(f["t"], 2, lang), num(f["T"], 0, lang), tx(" ".join(f.get("statements") or [])[:220])]
                 for n, f in enumerate(fr)],
                "rlrrp{0.45\\linewidth}", tx(s.L(f"Zustände von {name} entlang der Wärmebehandlung.", f"States of {name} along the heat treatment.")),
                cites=keys[:6], small=True)
        last = fr[-1]
        s.r.append(tx(s.L(f"{name} nach der Wärmebehandlung ({last['label']}, {last['T']:.0f} °C): ",
                          f"{name} after the heat treatment ({last['label']}, {last['T']:.0f} °C): ")) + tx(" ".join(last.get("statements") or [])))
        s.m.append(s.L("Zustände entlang des Wärmebehandlungswegs aus Regeln der Literatur: Anlassstufen des Martensits über den "
                       f"Hollomon–Jaffe-Parameter, Ausscheidungsfolgen aushärtbarer Legierungen mit Arrhenius-gleichwertigen Zeiten{s.c(keys[:4])}. "
                       "Die Bilder sind Modelle bzw. Skizzen; Heiz- und Abkühlzeiten sind angenommen.",
                       "States along the heat-treatment path from rules in the literature: tempering stages of martensite via the "
                       f"Hollomon-Jaffe parameter, precipitation sequences of age-hardening alloys with Arrhenius-equivalent times{s.c(keys[:4])}. "
                       "The frames are models or sketches; heating and cooling times are assumed."))
        return
    T = res["T"]
    at = s.L("bei", "at") + f" {T:.0f} °C"
    shown = str(req.get("show") or "")
    panels = sorted(res.get("panels") or [], key=lambda p: p["id"] != shown)
    for p in panels:
        try:
            f = CH.fig_panel(p, lang)
        except Exception:  # noqa: BLE001 - eine Ansicht darf den Bericht nicht verhindern
            continue
        s.fig(f, "a-" + re.sub(r"[^a-z0-9]+", "-", p["id"].lower()).strip("-"), _panel_caption(s, p, name, at),
              cites=_panel_cites(p) or keys[:3], width="0.85" if p.get("kind") == "sketch" else "0.75")
    cells = [p for p in panels if p.get("phase")]
    if cells:
        rows = []
        for p in cells:
            ph = p["phase"]
            c = ph.get("cell") or {}
            rows.append([tx(ph.get("name") or ""), tx(ph.get("formula") or ""), tx(ph.get("spacegroup") or "–"),
                         ", ".join(num(c[k], 3, lang) for k in ("a", "b", "c") if c.get(k)) or "–",
                         tx(f"COD {ph['cod']}" if ph.get("cod") else s.L("Literatur", "literature") if ph.get("art") == "lit" else s.L("eingebaut", "built-in"))])
        s.table("phasen", [s.L("Phase", "Phase"), s.L("Formel", "Formula"), s.L("Raumgruppe", "Space group"), "a, b, c [Å]", s.L("Daten", "Data")],
                rows, "lllll", tx(s.L(f"Phasen und Elementarzellen von {name} {at}.", f"Phases and unit cells of {name} {at}.")),
                cites=[k for p in cells for k in _panel_cites(p)])
    s.r.append(tx(s.L(f"{name} {at}: ", f"{name} {at}: ")) + tx(" ".join(res.get("statements") or [])))
    s.m.append(s.L(f"Strukturansichten von {tx(name)} {tx(at)}: Phasen nach Zustandsdiagramm bzw. Werkstoffregeln, Elementarzellen aus "
                   f"Strukturdaten (Crystallography Open Database bzw. Literatur), Ketten und Netzwerke als Modelle mit "
                   f"Standardbindungslängen, Gefüge als Skizzen{s.c(keys[:5])}.",
                   f"Structure views of {tx(name)} {tx(at)}: phases from the phase diagram or material rules, unit cells from "
                   f"structure data (Crystallography Open Database or literature), chains and networks as models with standard "
                   f"bond lengths, microstructures as sketches{s.c(keys[:5])}.") + (" " + tx(" ".join(res.get("notes") or [])) if res.get("notes") else ""))


# ----------------------------------------------------------------------------- Gitter
def _sci(v: float, lang: str, nd: int = 2) -> str:
    """Zahl für LaTeX-Text, kleine und grosse als a·10^n."""
    if v is None:
        return "--"
    if v == 0:
        return "0"
    e = int(f"{v:e}".split("e")[1])
    if -3 <= e <= 4:
        return num(v, max(nd, -e + 1), lang)
    return num(v / 10 ** e, nd, lang) + f"\\,$\\cdot$\\,10$^{{{e}}}$"


def w_gitter(s: Sec, res: dict, req: dict):
    de, lang = s.de, s.lang
    keys = [r["key"] if isinstance(r, dict) else r for r in res.get("refs") or []]
    lat_keys = [k for k in keys if k not in ("callister", "porter", "ehrhart1991", "willis1975", "eshelby1956", "hirth1982",
                                             "hirth1980", "cordero2008", "massalski1990", "kittel")]
    host, T = res["host"], res["T"]
    sols = res.get("solutes") or []
    unit_of = {"at": s.L("At.-\\%", "at\\%"), "wt": s.L("Gew.-\\%", "wt\\%")}
    comp = host + "".join(f"--{num(x['c'], 2, lang)}\\,{unit_of.get(x['einheit'], '')}\\,{x['el']}" for x in sols)
    ph = res["phase"]
    phase = tx(ph["name"]) + ("" if res["liquid"] else f" ({tx(ph['gitter'])})")
    own = [s.own_cite(f"{el}", src) for el, src in (req.get("limit_src") or {}).items()]
    own = [k for k in own if k]
    boost, vb = res.get("boost", 1) or 1, res.get("vib_boost", 1) or 1
    def fac(v):
        e = math.log10(v) if v > 0 else 0
        if v >= 1e4 and abs(e - round(e)) < 1e-9:
            return f"10$^{{{int(round(e))}}}$"
        return _sci(v, lang, 1) if v >= 1e4 else num(v, 0 if float(v).is_integer() else 1, lang)
    labels = []
    if boost > 1:
        labels.append(s.L(f"Leerstellen {fac(boost)}-fach überhöht", f"vacancies exaggerated {fac(boost)}-fold"))
    if vb > 1:
        labels.append(s.L(f"Schwingungsamplitude {fac(vb)}-fach überhöht", f"vibration amplitude exaggerated {fac(vb)}-fold"))
    schem = [x for x, on in ((s.L("Ausscheidung", "precipitate"), any(z.get("atoms") for z in res.get("second") or [])),
                             (s.L("Versetzung", "dislocation"), bool(res.get("disl"))), (s.L("Stapelfehler", "stacking fault"), bool(res.get("sf"))),
                             (s.L("Korngrenze", "grain boundary"), bool(res.get("gb")))) if on]
    tail = tx(s.L("Modell, kein Messbild", "Model, not a micrograph") + ("; " + ", ".join(schem) + s.L(" schematisch", " schematic") if schem else "")) + \
        ("; " + "; ".join(labels) if labels else "") + "."
    at_T = s.L("bei", "at") + f" {num(T, 0, lang)}\\," + tx("°C")
    s.fig(CH.fig_lattice(res, lang), "gitter",
          s.L("Gitterausschnitt von ", "Lattice section of ") + comp + " " + at_T + ": " +
          tx(s.L(f"{ph['name']}, {res['count']} Atome, Elementarzelle hervorgehoben. ",
                 f"{ph['name']}, {res['count']} atoms, unit cell highlighted. ")) + tail,
          cites=["callister"] + lat_keys[:3] + own, width="0.75")
    if res.get("cell"):
        s.fig(CH.fig_lattice(res, lang, cell_only=True), "zelle",
              tx(s.L(f"Elementarzelle von {ph['name']} ({ph['gitter']}) aus dem Ausschnitt, mit Fremdatomen und Leerstellen, "
                     f"die in ihr liegen. Modell.", f"Unit cell of {ph['name']} ({ph['gitter']}) taken from the section, with the "
                     f"solutes and vacancies inside it. Model.")), cites=["callister"], width="0.5")
    if req.get("slice") and not res["liquid"]:
        f = CH.fig_slice(res, req["slice"], lang)
        if f is not None:
            s.fig(f, "schnitt", tx(s.L(f"Atomlage ({req['slice']}) durch die Mitte des Ausschnitts, Atome in wahrer Grösse "
                                       f"(Metall- bzw. Kovalenzradius). Modell.",
                                       f"Atomic layer ({req['slice']}) through the centre of the section, atoms at true size "
                                       f"(metallic or covalent radius). Model.")), cites=["callister"], width="0.55")
    # Kennwerte
    lt = res["lattice"]
    rows = []
    va = None
    if not res["liquid"]:
        va = s.val("a", s.L("Gitterparameter a", "Lattice parameter a"), lt["a"], 4, "Å")
        rows.append([tx(s.L("Gitterparameter a", "Lattice parameter a")), num(lt["a"], 4, lang) + r"\,\AA{}",
                     tx(s.L("Daten, auf T umgerechnet", "data, converted to T"))])
        if lt.get("c"):
            s.val("c", s.L("Gitterparameter c", "Lattice parameter c"), lt["c"], 4, "Å")
            rows.append([tx(s.L("Gitterparameter c", "Lattice parameter c")), num(lt["c"], 4, lang) + r"\,\AA{}",
                         tx(s.L("Daten, auf T umgerechnet", "data, converted to T"))])
        s.val("d1", s.L("Abstand nächster Nachbarn", "Nearest-neighbour distance"), lt["dnn"], 3, "Å")
        rows.append([tx(s.L("Abstand nächster Nachbarn", "Nearest-neighbour distance")), num(lt["dnn"], 3, lang) + r"\,\AA{}",
                     tx(s.L("berechnet", "computed"))])
    hom = (T + 273.15) / (res["Tm"] + 273.15)
    s.val("TTm", s.L("Homologe Temperatur", "Homologous temperature"), hom, 3)
    rows.append([tx(s.L("Homologe Temperatur T/Tm", "Homologous temperature T/Tm")), num(hom, 3, lang), tx(s.L("berechnet", "computed"))])
    vac = res.get("vac") or {}
    if vac.get("Hv"):
        s.vals.append((re.sub(r"[^A-Za-z0-9-]+", "-", f"{s.pid}-cv").strip("-"), tx(s.L("Leerstellenanteil", "Vacancy fraction")),
                       _sci(vac["c"], lang), f"{vac['c']:.3e}"))
        rows.append([tx(s.L("Leerstellenanteil", "Vacancy fraction")) + " $c_v$", _sci(vac["c"], lang),
                     tx(s.L("berechnet (Modell)", "computed (model)"))])
        rows.append([tx(s.L("Leerstellen im Ausschnitt erwartet / gezeigt", "Vacancies in the section expected / shown")),
                     _sci(vac["expected"], lang) + " / " + str(vac["placed"]),
                     tx(s.L("berechnet", "computed")) + (s.L(", Bild ×", ", figure ×").replace("×", "$\\times$") + fac(boost) if boost > 1 else "")])
    if res.get("sigma"):
        s.val("u", s.L("Schwingungsamplitude", "Vibration amplitude"), res["sigma"], 3, "Å")
        rows.append([tx(s.L("Schwingungsamplitude √⟨u²⟩", "Vibration amplitude √⟨u²⟩")).replace("√⟨u²⟩", r"$\sqrt{\langle u_x^2\rangle}$"),
                     num(res["sigma"], 3, lang) + r"\,\AA{}", tx(s.L("berechnet (Debye)", "computed (Debye)"))])
    s.val("N", s.L("Atome im Ausschnitt", "Atoms in the section"), res["count"], 0, text=str(res["count"]))
    s.table("kennwerte", [s.L("Grösse", "Quantity"), s.L("Wert", "Value"), s.L("Herkunft", "Origin")], rows,
            r"p{0.4\linewidth}rp{0.24\linewidth}",
            s.L("Kennwerte des Gitters von ", "Lattice data of ") + comp + " " + at_T + ".",
            cites=["callister", "ehrhart1991", "willis1975"] + lat_keys[:3], small=True)
    how = {"diagramm": s.L("Zustandsdiagramm", "phase diagram"), "vollstaendig": s.L("lückenlos", "complete"),
           "eigen": s.L("eigene Grenze", "own limit"), "unbekannt": s.L("nicht hinterlegt", "not available")}
    if sols:
        site = {"sub": s.L("Gitterplatz", "lattice site"), "okt": s.L("Oktaederlücke", "octahedral"), "tet": s.L("Tetraederlücke", "tetrahedral")}
        s.table("fremdatome", [s.L("Element", "Element"), s.L("Platz", "Site"), s.L("Δr/r", "Δr/r"), s.L("erwartet", "expected"),
                               s.L("gezeigt", "shown"), s.L("Löslichkeit", "Solubility")],
                [[tx(x["el"]), tx(site.get(x.get("site"), "")), num(100 * x["misfit"], 0, lang) + r"\,\%", num(x.get("expected") or 0, 1, lang),
                  str(x.get("placed") or 0), tx(how.get(x["how"], x["how"]))] for x in sols], "llrrrl",
                tx(s.L("Fremdatome im Ausschnitt: Platz nach Grösse und Art, Zahl aus dem gelösten Anteil.",
                       "Solute atoms in the section: site by size and kind, number from the dissolved fraction.")),
                cites=["cordero2008", "callister"] + own, small=True)
    # Daten der Atomlagen (zitierbar, nachrechenbar)
    kinds = res["kinds"]
    s.data("atome", ["x_A", "y_A", "z_A", "art"], [[a[0], a[1], a[2], kinds[a[3]]["name"]] for a in res["atoms"]],
           tx(s.L(f"Atomlagen des Gittermodells ({res['count']} Atome, Å)", f"Atom positions of the lattice model ({res['count']} atoms, Å)")),
           labels={"x_A": "x [Å]", "y_A": "y [Å]", "z_A": "z [Å]"})
    # Ergebnis und Methodik
    sec_txt = "; ".join(f"{tx(z['name'])} {num(100 * z['frac'], 1, lang)}\\,\\%" for z in res.get("second") or [])
    s.r.append(f"{comp} {at_T}: {phase}" + (f", $a$ = {va}" if va else "") +
               (s.L("; zweite Phase nach dem Hebelgesetz: ", "; second phase by the lever rule: ") + sec_txt if sec_txt else "") + ".")
    m = []
    m.append(s.L(f"Die Phase bei der Temperatur folgt aus der Allotropie des Grundelements bzw. dem Zustandsdiagramm, die "
                 f"Anteile aus dem Hebelgesetz{s.c('callister')}. Der Gitterparameter wird auf die Temperatur umgerechnet, "
                 f"$a(T) = a(T_0)\\,[1 + \\alpha\\,(T - T_0)]$ bzw. linear zwischen Messpunkten{s.c(lat_keys[:3])}.",
                 f"The phase at the temperature follows from the allotropy of the base element or the phase diagram, the "
                 f"fractions from the lever rule{s.c('callister')}. The lattice parameter is converted to the temperature, "
                 f"$a(T) = a(T_0)\\,[1 + \\alpha\\,(T - T_0)]$, or interpolated between measured points{s.c(lat_keys[:3])}."))
    if sols:
        m.append(s.L(f"H, B, C, N und O besetzen Zwischengitterplätze (Oktaeder- bzw. Tetraederlücke je Gittertyp"
                     f"{s.c(['porter', 'cordero2008'])}), alle übrigen Elemente Gitterplätze; ein Radienunterschied über 15\\,\\% "
                     f"wird nach Hume-Rothery gemeldet{s.c('callister')}. Ihre Zahl im Ausschnitt ist der gelöste Anteil mal der "
                     f"Zahl der Plätze, die Plätze sind zufällig gewählt (Startwert {res['seed']}).",
                     f"H, B, C, N and O occupy interstitial sites (octahedral or tetrahedral per lattice type"
                     f"{s.c(['porter', 'cordero2008'])}), all other elements lattice sites; a radius difference above 15\\,\\% "
                     f"is flagged after Hume-Rothery{s.c('callister')}. Their number in the section is the dissolved fraction "
                     f"times the number of sites; the sites are chosen at random (seed {res['seed']})."))
    if vac.get("Hv"):
        m.append(s.L(f"Leerstellen im Gleichgewicht: $c_v = \\exp(S_v/k)\\,\\exp(-H_v/kT)$ mit $H_v = {num(vac['Hv'], 2, lang)}$\\,eV "
                     f"und angenommenem $S_v = {num(vac['Sv'], 1, lang)}\\,k${s.c(['ehrhart1991', 'porter'])}"
                     + (f"; im Bild {fac(boost)}-fach überhöht." if boost > 1 else "; im Bild die wahre erwartete Zahl."),
                     f"Equilibrium vacancies: $c_v = \\exp(S_v/k)\\,\\exp(-H_v/kT)$ with $H_v = {num(vac['Hv'], 2, lang)}$\\,eV "
                     f"and an assumed $S_v = {num(vac['Sv'], 1, lang)}\\,k${s.c(['ehrhart1991', 'porter'])}"
                     + (f"; exaggerated {fac(boost)}-fold in the figure." if boost > 1 else "; the figure shows the true expected number.")))
    if res.get("sigma"):
        m.append(s.L(f"Die thermische Auslenkung folgt dem Debye-Modell, "
                     f"$\\langle u_x^2\\rangle = \\frac{{3\\hbar^2}}{{m k \\theta_D}}\\left[\\frac{{\\Phi(x)}}{{x}} + \\frac{{1}}{{4}}\\right]$, "
                     f"$\\Phi(x) = \\frac{{1}}{{x}}\\int_0^x \\frac{{t}}{{e^t - 1}}\\,dt$, "
                     f"$x = \\theta_D/T$, $\\theta_D = {num(res['theta_D'], 0, lang)}$\\,K{s.c('willis1975')}; die Atome sind "
                     f"normalverteilt um ihre Plätze verschoben" + (f" (Amplitude {fac(vb)}-fach überhöht)." if vb > 1 else "."),
                     f"Thermal displacement follows the Debye model, "
                     f"$\\langle u_x^2\\rangle = \\frac{{3\\hbar^2}}{{m k \\theta_D}}\\left[\\frac{{\\Phi(x)}}{{x}} + \\frac{{1}}{{4}}\\right]$, "
                     f"$\\Phi(x) = \\frac{{1}}{{x}}\\int_0^x \\frac{{t}}{{e^t - 1}}\\,dt$, "
                     f"$x = \\theta_D/T$, $\\theta_D = {num(res['theta_D'], 0, lang)}$\\,K{s.c('willis1975')}; atoms are displaced "
                     f"normally about their sites" + (f" (amplitude exaggerated {fac(vb)}-fold)." if vb > 1 else ".")))
    if (res.get("fx") or {}).get("distort") and not res["liquid"]:
        m.append(s.L(f"Um Fremdatome und Leerstellen sind die Nachbarn radial um $u(r) = \\delta\\,(d_1/r)^2$ bis $2d_1$ verschoben, "
                     f"$\\delta$ aus dem Radienunterschied; schematisch{s.c('eshelby1956')}.",
                     f"Around solutes and vacancies the neighbours are displaced radially by $u(r) = \\delta\\,(d_1/r)^2$ up to $2d_1$, "
                     f"$\\delta$ from the radius difference; schematic{s.c('eshelby1956')}."))
    if res.get("disl") or res.get("sf") or res.get("gb"):
        d = res.get("disl") or {}
        m.append(s.L((f"Stufenversetzung mit dem isotropen Verschiebungsfeld nach Volterra, $b = {num(d['b'], 3, lang)}$\\,\\AA{{}}, "
                      f"$\\nu = {num(d['nu'], 2, lang)}$. " if d else "") +
                     ("Stapelfehler als Verschiebung der Lagen über einer dichtest gepackten Ebene. " if res.get("sf") else "") +
                     ("Symmetrische Kippkorngrenze aus zwei gegeneinander gedrehten Körnern. " if res.get("gb") else "") +
                     f"Lage und Grösse dieser Fehler sind schematisch{s.c('hirth1982')}.",
                     (f"Edge dislocation with the isotropic Volterra displacement field, $b = {num(d['b'], 3, lang)}$\\,\\AA{{}}, "
                      f"$\\nu = {num(d['nu'], 2, lang)}$. " if d else "") +
                     ("Stacking fault as a shift of the layers above a close-packed plane. " if res.get("sf") else "") +
                     ("Symmetric tilt grain boundary from two grains rotated against each other. " if res.get("gb") else "") +
                     f"Position and size of these defects are schematic{s.c('hirth1982')}."))
    if own:
        m.append(s.L(f"Eigene Löslichkeitsgrenzen nach{s.c(own)}.", f"Own solubility limits after{s.c(own)}."))
    for n_ in res.get("notes") or []:
        m.append(tx(n_))
    s.m.append(" ".join(m))


# ----------------------------------------------------------------------------- XRD
def w_xrd(s: Sec, res: dict, req: dict):
    it = s.ctx.get(req["item"], "xrd")
    fc = _file_cite(s, it)
    pk = res["peaks"]
    name = it["name"]
    lam = res["lam1"]
    sticks = res.get("sticks") or []
    pcs = []
    for st in sticks:
        try:
            ph = s.ctx.phase(st["id"])
            pcs += _phase_cite(s, {"q": ph.get("q"), "source": ph.get("source"), "name": ph.get("name"), "id": ph["id"]})
        except Exception:  # noqa: BLE001
            pass
    s.fig(CH.fig_xrd(res, s.lang), "diagramm",
          tx(s.L(f"Diffraktogramm {name} mit Untergrund und gefundenen Reflexen"
                 + (" sowie berechneten Linien der Vergleichsphasen." if sticks else "."),
                 f"Diffraction pattern {name} with background and detected peaks"
                 + (" and computed lines of the reference phases." if sticks else "."))) + fc,
          cites=(["cullity"] + pcs) if sticks else _vk("xrd", "pattern"))
    hk = {q["peak"]: q["hkl"] for q in (res.get("ref_match") or {}).get("pairs", [])}
    rows = []
    for i, p in enumerate(pk):
        rows.append([num(p["tth"], 3, s.lang), num(p["d"], 4, s.lang), num(p.get("fwhm"), 3, s.lang),
                     num(p["Irel"], 1, s.lang), num(p.get("D_nm"), 1, s.lang), tx(hk.get(i, ""))])
    s.table("reflexe", ["2θ [°]", "d [Å]", "FWHM [°]", "I_rel [%]", "D [nm]", "hkl"], rows, "rrrrrl",
            tx(s.L(f"Reflexe in {name} (Pseudo-Voigt-Anpassung, Kristallitgrösse nach Scherrer).",
                   f"Peaks in {name} (pseudo-Voigt fit, crystallite size after Scherrer).")), small=True)
    from .xrd import DEFAULTS
    o = {**DEFAULTS, **(req.get("opt") or {})}
    s.val("n", s.L("Zahl der Reflexe", "Number of peaks"), len(pk), 0, text=str(len(pk)))
    vlam = s.val("lam", "λ", lam, 5, "Å")
    lsrc = LAM_SRC.get(res["lam_src"], (res["lam_src"], res["lam_src"]))[0 if s.de else 1]
    m = [s.L(f"Ausgewertet wurde {tx(name)}{fc} mit λ = {vlam} ({tx(lsrc)}).",
             f"{tx(name)}{fc} was evaluated with λ = {vlam} ({tx(lsrc)}).")]
    if int(o.get("smooth") or 0) >= 5:
        m.append(s.L(f"Geglättet nach Savitzky und Golay{s.c('savitzky1964')} (Fenster {o['smooth']}, Grad 2).",
                     f"Smoothed after Savitzky and Golay{s.c('savitzky1964')} (window {o['smooth']}, degree 2)."))
    if o.get("bg"):
        m.append(s.L(f"Untergrund mit dem SNIP-Verfahren{s.c(['ryan1988', 'morhac1997'])} (Breite {num(o['bg_width'], 1, s.lang)}°).",
                     f"Background by the SNIP method{s.c(['ryan1988', 'morhac1997'])} (width {num(o['bg_width'], 1, s.lang)}°)."))
    if o.get("strip_ka2"):
        m.append(s.L(f"Kα2 nach Rachinger abgezogen{s.c('rachinger1948')}.", f"Kα2 stripped after Rachinger{s.c('rachinger1948')}."))
    m.append(s.L("Reflexe wurden als lokale Maxima mit topographischer Prominenz gesucht und gruppenweise mit "
                 "Pseudo-Voigt-Profilen und linearem Untergrund nach Levenberg-Marquardt angepasst"
                 + (", als Kα1/Kα2-Dublett mit festem Lageversatz und Intensitätsverhältnis" if res.get("doublet") else "") + ".",
                 "Peaks were located as local maxima with topographic prominence and fitted group-wise with pseudo-Voigt "
                 "profiles and a linear background by Levenberg-Marquardt"
                 + (", as a Kα1/Kα2 doublet with fixed position offset and intensity ratio" if res.get("doublet") else "") + "."))
    if any(p.get("D_nm") for p in pk):
        corr = {"quadratic": s.L("quadratisch", "quadratic"), "linear": s.L("linear", "linear")}.get(o["correction"], o["correction"])
        m.append(s.L(f"Kristallitgrösse nach Scherrer{s.c(['scherrer1918', 'langford1978'])} mit K = {num(o['K'], 2, s.lang)}"
                     + (f", Gerätebreite {num(o['inst_fwhm'], 3, s.lang)}° ({corr} abgezogen)" if float(o.get("inst_fwhm") or 0) > 0
                        else ", ohne Abzug der Gerätebreite (Werte sind Untergrenzen)") + ".",
                     f"Crystallite size after Scherrer{s.c(['scherrer1918', 'langford1978'])} with K = {num(o['K'], 2, s.lang)}"
                     + (f", instrumental breadth {num(o['inst_fwhm'], 3, s.lang)}° (subtracted, {corr})" if float(o.get("inst_fwhm") or 0) > 0
                        else ", without subtracting the instrumental breadth (values are lower bounds)") + "."))
    wh = res.get("wh")
    if wh:
        s.fig(CH.fig_wh(wh, s.lang), "wh", tx(s.L("Williamson-Hall-Auftragung.", "Williamson-Hall plot.")), cites=["williamson1953"], width="0.55")
        vd = s.val("whD", s.L("Kristallitgrösse (Williamson-Hall)", "Crystallite size (Williamson-Hall)"), wh.get("D_nm"), 1, "nm")
        ve = s.val("whStrain", s.L("Mikrodehnung (Williamson-Hall)", "Microstrain (Williamson-Hall)"), wh["strain"] * 100, 4, "%")
        m.append(s.L(f"Williamson-Hall-Gerade{s.c('williamson1953')}: $\\beta\\cos\\theta = K\\lambda/D + 4\\varepsilon\\sin\\theta$.",
                     f"Williamson-Hall line{s.c('williamson1953')}: $\\beta\\cos\\theta = K\\lambda/D + 4\\varepsilon\\sin\\theta$."))
        s.r.append(s.L(f"Nach Williamson-Hall beträgt die Kristallitgrösse {vd or '--'} und die Mikrodehnung {ve} "
                       f"(R² = {num(wh['r2'], 3, s.lang)}).",
                       f"Williamson-Hall gives a crystallite size of {vd or '--'} and a microstrain of {ve} "
                       f"(R² = {num(wh['r2'], 3, s.lang)}).").replace("R²", "$R^2$"))
    cr = res.get("cubic_refined")
    if cr and res.get("cubic"):
        best = res["cubic"][0]
        va = s.val("aCubic", s.L("Gitterparameter (kubisch indiziert)", "Lattice parameter (cubic indexing)"), cr["a"], 4, "Å")
        s.r.append(s.L(f"Die Reflexe lassen sich {tx(best['label'])} indizieren mit a = {va}.",
                       f"The peaks index as {tx(best.get('label_en') or best['label'])} with a = {va}."))
        if cr.get("nr"):
            s.fig(CH.fig_nr(cr["nr"], s.lang), "nr", tx(s.L("Extrapolation nach Nelson und Riley.", "Nelson-Riley extrapolation.")),
                  cites=["nelson1945"], width="0.55")
            va0 = s.val("aNR", s.L("Gitterparameter (Nelson-Riley)", "Lattice parameter (Nelson-Riley)"), cr["nr"]["a0"], 5, "Å")
            s.r.append(s.L(f"Extrapoliert nach Nelson und Riley{s.c('nelson1945')}: a₀ = {va0}.",
                           f"Extrapolated after Nelson and Riley{s.c('nelson1945')}: a₀ = {va0}.").replace("a₀", "$a_0$"))
    rm = res.get("ref_match")
    if rm:
        ph = s.ctx.phase(rm["id"])
        pc = _phase_cite(s, {"q": ph.get("q"), "source": ph.get("source"), "name": ph.get("name"), "id": ph["id"]})
        vs = s.val("refScore", s.L("Übereinstimmung mit der Vergleichsphase", "Match with the reference phase"), rm["score"], 1)
        s.r.append(s.L(f"Mit der berechneten Phase {tx(pname(ph, 'de'))}{s.c(pc)} stimmen {len(rm['pairs'])} von {rm.get('n_ref', 0)} "
                       f"Linien überein (Gütezahl {vs} von 100, Verschiebung {num(rm['shift'], 3, s.lang)}°).",
                       f"{len(rm['pairs'])} of {rm.get('n_ref', 0)} lines of the computed phase {tx(pname(ph, 'en'))}{s.c(pc)} "
                       f"match (score {vs} of 100, shift {num(rm['shift'], 3, s.lang)}°)."))
    sr = res.get("search")
    if sr:
        def _pn(pid, fallback):
            try:
                return pname(s.ctx.phase(pid), s.lang)
            except Exception:  # noqa: BLE001
                return fallback
        rows = [[str(i + 1), tx(_pn(r["id"], r["name"])), num(r["score"], 1, s.lang), num(100 * r["coverage"], 0, s.lang),
                 num(100 * r["explained"], 0, s.lang), num(r["shift"], 3, s.lang)] for i, r in enumerate(sr[:8])]
        s.table("suche", ["#", s.L("Phase", "Phase"), s.L("Güte", "Score"), s.L("Abdeckung [%]", "Coverage [%]"),
                          s.L("erklärt [%]", "explained [%]"), "Δ2θ [°]"], rows, "rlrrrr",
                tx(s.L("Phasensuche gegen berechnete Diagramme (eingebaute Strukturen und geladene CIF).",
                       "Phase search against computed patterns (built-in structures and loaded CIF).")), small=True)
        m.append(s.L("Die Phasensuche vergleicht die Reflexlagen mit Diagrammen, die aus den Kristallstrukturen berechnet "
                     f"wurden (nicht aus einer Pulverdatenbank){s.c('wyckoff1963')}: Gütezahl = 100 · Abdeckung · (0,5 + 0,5 · Lage), "
                     "Abdeckung = Anteil der Referenzintensität mit zugeordnetem Reflex, Lage = 1 − mittlere |Δ2θ| / Toleranz "
                     f"(Toleranz {num(o['tol'], 2, s.lang)}°, gemeinsame Verschiebung bis ±{num(2 * float(o['tol']), 2, s.lang)}°).",
                     "The phase search compares the peak positions with patterns computed from the crystal structures (not "
                     f"from a powder database){s.c('wyckoff1963')}: score = 100 · coverage · (0.5 + 0.5 · position), coverage = "
                     "share of the reference intensity with an assigned peak, position = 1 − mean |Δ2θ| / tolerance "
                     f"(tolerance {num(o['tol'], 2, s.lang)}°, common shift up to ±{num(2 * float(o['tol']), 2, s.lang)}°)."))
    q = res.get("quant")
    if q and q.get("rows"):
        rows = [[tx(pname(s.ctx.phase(r["id"]), s.lang)), str(r["n"]), num(100 * r["vol"], 1, s.lang), num(100 * r["mass"], 1, s.lang)]
                for r in q["rows"]]
        s.table("anteile", [s.L("Phase", "Phase"), s.L("Linien", "Lines"), s.L("Vol.-%", "vol%"), s.L("Ma.-%", "wt%")], rows, "lrrr",
                tx(s.L("Halbquantitative Phasenanteile (aus der Struktur berechnete Referenzintensitäten).",
                       "Semi-quantitative phase fractions (reference intensities computed from the structure).")), cites=["chung1974"])
        for r in q["rows"]:
            s.val(f"mass-{slugify(r['name'], 16)}", s.L(f"Massenanteil {r['name']}", f"Mass fraction {r['name']}"), 100 * r["mass"], 1, "%")
        m.append(s.L(f"Phasenanteile halbquantitativ nach dem Verfahren der Referenzintensitäten{s.c(['chung1974', 'hubbard1988'])}, "
                     "die Referenzintensitäten aus der Struktur berechnet; Absorptionsunterschiede, Textur, Mikroabsorption und "
                     "amorphe Anteile sind nicht berücksichtigt.",
                     f"Phase fractions semi-quantitatively by the reference intensity method{s.c(['chung1974', 'hubbard1988'])}, "
                     "with reference intensities computed from the structure; absorption contrast, texture, microabsorption "
                     "and amorphous content are not considered."))
    s.m += [x.replace("Å", r"\AA{}") for x in m]
    c = res["curve"]
    s.data("kurve", ["tth", "counts", "bg"], [[a, b, d] for a, b, d in zip(c["x"], res.get("raw") or c["y"], c["bg"])],
           tx(s.L(f"Diffraktogramm {name} und Untergrund.", f"Pattern {name} and background.")),
           labels={"tth": r"$2\theta$ [\textdegree{}]", "counts": s.L("Intensität", "Intensity"), "bg": s.L("Untergrund", "Background")},
           plot={"x": "tth", "y": "counts"})


# ----------------------------------------------------------------------------- Phasendiagramme
def w_phasen(s: Sec, res: dict, req: dict):
    if res.get("computed"):
        p = res["model"]
        q = list(p.get("q") or [])
        s.fig(CH.fig_computed(res, s.lang), "diagramm",
              tx(s.L(f"Berechnetes Zustandsdiagramm {p['A']}–{p['B']} (Modell, kein gemessenes Diagramm).",
                     f"Computed phase diagram {p['A']}–{p['B']} (model, not a measured diagram).")), cites=["porter"] + q)
        ideal = not (p.get("omega_L") or p.get("omega_S"))
        s.m.append(s.L(f"Das Diagramm ist aus einem Lösungsmodell berechnet{s.c('porter')}: "
                       + ("ideale Lösung" if ideal else f"reguläre Lösung mit Ω_L = {num(p['omega_L'], 1, s.lang)} und Ω_S = {num(p['omega_S'], 1, s.lang)} kJ/mol")
                       + " in Schmelze und Mischkristall, Schmelzenthalpien und -temperaturen der reinen Stoffe"
                       f"{s.c(q)}; die Gleichgewichte folgen aus der konvexen Hülle der freien Enthalpie (gemeinsame Tangente).",
                       f"The diagram is computed from a solution model{s.c('porter')}: "
                       + ("ideal solution" if ideal else f"regular solution with Ω_L = {num(p['omega_L'], 1, s.lang)} and Ω_S = {num(p['omega_S'], 1, s.lang)} kJ/mol")
                       + " in liquid and solid, with melting enthalpies and temperatures of the pure components"
                       f"{s.c(q)}; equilibria follow from the convex hull of the Gibbs energy (common tangent).").replace("Ω_L", "$\\Omega_L$").replace("Ω_S", "$\\Omega_S$"))
        lv = res.get("lever")
        if lv and lv.get("phases"):
            for ph in lv["phases"]:
                s.val(f"frac-{slugify(ph['name'], 8)}", s.L(f"Anteil {ph['name']}", f"Fraction {ph['name']}"), 100 * ph["frac"], 1, "%")
            s.r.append(s.L(f"Bei {num(lv['T'], 0, s.lang)}\\,°C und {num(lv['x'], 1, s.lang)} % {tx(p['B'])} liegen nach dem Modell "
                           + " und ".join(f"{num(100 * ph['frac'], 1, s.lang)} % {tx(ph['name'])} ({num(ph['x'], 1, s.lang)} %)" for ph in lv["phases"]) + " vor.",
                           f"At {num(lv['T'], 0, s.lang)}\\,°C and {num(lv['x'], 1, s.lang)} % {tx(p['B'])}, the model gives "
                           + " and ".join(f"{num(100 * ph['frac'], 1, s.lang)} % {tx(ph['name'])} ({num(ph['x'], 1, s.lang)} %)" for ph in lv["phases"]) + ".").replace("%", "\\%").replace("°", "\\textdegree{}"))
        return
    d = res["diagram"]
    q = list(d.get("q") or [])
    s.fig(CH.fig_diagram(res, s.lang), "diagramm",
          tx(s.L(f"Zustandsdiagramm {d['name']}, schematisch: geglättete Linien durch Eckpunkte aus der Literatur.",
                 f"Phase diagram {d['name']}, schematic: smoothed lines through key points from the literature.")), cites=q)
    s.m.append(s.L(f"Das Zustandsdiagramm {tx(d['name'])} ist schematisch: Die invarianten Punkte (Temperatur und Zusammensetzung) "
                   f"stammen aus der Literatur{s.c(q)}, die Linien dazwischen sind nachgezeichnet und geglättet (Catmull-Rom-Spline). Phasenanteile nach dem Hebelgesetz "
                   f"auf der Konode{s.c('callister')}; Gefügebestandteile aus dem Hebelgesetz knapp oberhalb der invarianten Reaktion.",
                   f"The phase diagram {tx(d['name'])} is schematic: the invariant points (temperature and composition) are taken "
                   f"from the literature{s.c(q)}; the lines between them are traced and smoothed (Catmull-Rom spline). Phase fractions by the lever rule on the tie line"
                   f"{s.c('callister')}; microconstituents from the lever rule just above the invariant reaction."))
    lv = res.get("lever")
    if lv:
        if lv.get("phases"):
            rows = [[tx(ph["name"]), num(ph["x"], 3, s.lang), num(100 * ph["frac"], 1, s.lang)] for ph in lv["phases"]]
            s.table("hebel", [s.L("Phase", "Phase"), s.L("Zusammensetzung", "Composition"), s.L("Anteil [%]", "Fraction [%]")], rows, "lrr",
                    tx(s.L(f"Hebelgesetz bei {lv['T']:g} °C, x = {lv['x']:g} ({lv['region']}).",
                           f"Lever rule at {lv['T']:g} °C, x = {lv['x']:g} ({lv['region']}).")), cites=["callister"] + q)
            for ph in lv["phases"]:
                s.val(f"frac-{slugify(ph['name'], 8) or 'p'}", s.L(f"Anteil {ph['name']}", f"Fraction {ph['name']}"), 100 * ph["frac"], 1, "%")
            s.r.append(s.L(f"Bei {num(lv['T'], 0, s.lang)}\\,\\textdegree{{}}C liegt die Legierung im Feld {tx(lv['region'])}: "
                           + ", ".join(f"{num(100 * ph['frac'], 1, s.lang)}\\,\\% {tx(ph['name'])}" for ph in lv["phases"]) + ".",
                           f"At {num(lv['T'], 0, s.lang)}\\,\\textdegree{{}}C the alloy lies in the field {tx(lv['region'])}: "
                           + ", ".join(f"{num(100 * ph['frac'], 1, s.lang)}\\,\\% {tx(ph['name'])}" for ph in lv["phases"]) + "."))
        elif lv.get("note"):
            s.r.append(tx(lv["note"]))
    mic = res.get("micro")
    if mic and lv:
        try:
            p = {"kind": "sketch", "id": "gefuege", "title": mic.get("name") or "", "sketch": mic["sketch"]}
            s.fig(CH.fig_panel(p, s.lang), "gefuege-punkt",
                  tx(s.L(f"Gefüge bei {lv['T']:g} °C und x = {lv['x']:g} nach langsamer Abkühlung (Skizze, schematisch). {mic.get('caption', '')}",
                         f"Microstructure at {lv['T']:g} °C and x = {lv['x']:g} after slow cooling (sketch, schematic). {mic.get('caption', '')}")),
                  cites=list(mic.get("refs") or [])[:4], width="0.75")
        except Exception:  # noqa: BLE001 - die Skizze darf den Bericht nicht verhindern
            pass
    for k, cst in enumerate(res.get("constituents") or []):
        rows = [[tx(pt["name"]), num(100 * pt["frac"], 1, s.lang)] for pt in cst["parts"]]
        s.table(f"gefuege{k + 1}" if k else "gefuege", [s.L("Gefügebestandteil", "Microconstituent"), s.L("Anteil [%]", "Fraction [%]")],
                rows, "lr", tx(s.L(f"Gefügebestandteile unterhalb {cst['T']:g} °C ({cst['reaction']}).",
                                   f"Microconstituents below {cst['T']:g} °C ({cst['reaction']}).")), cites=["callister"] + q)
        s.r.append(s.L("Nach der Reaktion " + tx(cst["reaction"]) + " bei " + num(cst["T"], 0, s.lang) + "\\,\\textdegree{}C: "
                       + ", ".join(f"{num(100 * pt['frac'], 1, s.lang)}\\,\\% {tx(pt['name'])}" for pt in cst["parts"]) + ".",
                       "After the reaction " + tx(cst["reaction"]) + " at " + num(cst["T"], 0, s.lang) + "\\,\\textdegree{}C: "
                       + ", ".join(f"{num(100 * pt['frac'], 1, s.lang)}\\,\\% {tx(pt['name'])}" for pt in cst["parts"]) + "."))
    co = res.get("cooling")
    if co and co.get("events"):
        rows = [[num(e["T"], 0, s.lang), tx(e["from"]), tx(e["to"])] for e in co["events"]]
        s.table("abkuehlung", ["T [°C]", s.L("von", "from"), s.L("nach", "to")], rows, "rll",
                tx(s.L("Phasenwechsel beim langsamen Abkühlen (Gleichgewicht, schematisches Diagramm).",
                       "Phase changes on slow cooling (equilibrium, schematic diagram).")), cites=q)


# ----------------------------------------------------------------------------- Stahl
def w_stahl(s: Sec, res: dict, req: dict):
    s.unc(res)
    rows = []
    cmap = [("CE", "CE (IIW)", 2, "%", "en1011_2"), ("CET", "CET", 2, "%", "en1011_2"), ("Pcm", "Pcm", 3, "%", "ito1968"),
            ("Ms", "Ms", 0, "°C", "andrews1965"), ("Ac1", "Ac1", 0, "°C", "andrews1965"), ("Ac3", "Ac3", 0, "°C", "andrews1965")]
    for k, lab, nd, u, q in cmap:
        if res.get(k) is not None:
            rows.append([tx(lab), num(res[k], nd, s.lang, u if u != "%" else ""), "~\\cite{" + q + "}" if s.inc.get("citations", True) else ""])
            s.val(k, lab, res[k], nd, u if u != "%" else "")
    s.cite([c[4] for c in cmap])
    comp = res.get("comp") or {}
    ctext = ", ".join(f"{k} {num(v, 3, s.lang)}" for k, v in comp.items() if v)
    s.table("kennwerte", [s.L("Kennwert", "Quantity"), s.L("Wert", "Value"), s.L("Quelle", "Source")], rows, "lrl",
            tx(s.L(f"Kennwerte aus der Zusammensetzung (Ma.-%: {ctext}).", f"Quantities from the composition (wt%: {ctext}).")).replace(
                tx(ctext), ctext))
    s.m.append(s.L("Kohlenstoffäquivalente nach IIW (CE) und CET nach EN 1011-2" + s.c("en1011_2") + ", Pcm nach Ito und Bessyo"
                   + s.c("ito1968") + "; Ms, Ac1 und Ac3 nach den empirischen Formeln von Andrews" + s.c("andrews1965")
                   + " (gültig nur im Bereich der Stähle, aus denen sie gewonnen wurden).",
                   "Carbon equivalents after IIW (CE) and CET after EN 1011-2" + s.c("en1011_2") + ", Pcm after Ito and Bessyo"
                   + s.c("ito1968") + "; Ms, Ac1 and Ac3 by Andrews' empirical formulas" + s.c("andrews1965")
                   + " (valid only within the range of the steels they were derived from)."))
    for n in res.get("notes") or []:
        s.r.append(tx(n) + ".")
    ph = res.get("preheat")
    if ph:
        v = s.val("Tp", s.L("Vorwärmtemperatur", "Preheat temperature"), ph["Tp"], 0, "°C")
        s.r.append(s.L(f"Vorwärmtemperatur nach EN 1011-2, Verfahren B{s.c('en1011_2')}: {v} (Blechdicke {num(ph['d'], 0, s.lang)}\\,mm, "
                       f"Wasserstoff {num(ph['HD'], 0, s.lang)}\\,ml/100\\,g, Wärmeeinbringung {num(ph['Q'], 1, s.lang)}\\,kJ/mm).",
                       f"Preheat temperature after EN 1011-2, method B{s.c('en1011_2')}: {v} (plate thickness {num(ph['d'], 0, s.lang)}\\,mm, "
                       f"hydrogen {num(ph['HD'], 0, s.lang)}\\,ml/100\\,g, heat input {num(ph['Q'], 1, s.lang)}\\,kJ/mm)."))
        for w in ph.get("warn") or []:
            s.r.append(tx(w) + ".")
    hj = res.get("hj")
    if hj:
        vp = s.val("HJ", s.L("Anlassparameter", "Tempering parameter"), hj["P"], 0, text=f"{hj['P']:.0f}")
        s.r.append(s.L(f"Anlassparameter nach Hollomon und Jaffe{s.c('hollomonjaffe1945')} $P = T\\,(C + \\lg t)$ mit C = {num(hj['C'], 0, s.lang)}: P = {vp}",
                       f"Hollomon-Jaffe tempering parameter{s.c('hollomonjaffe1945')} $P = T\\,(C + \\lg t)$ with C = {num(hj['C'], 0, s.lang)}: P = {vp}")
                   + (s.L(f"; gleichwertig bei {num(hj['equiv']['T2_C'], 0, s.lang)}\\,\\textdegree{{}}C sind {num(hj['equiv']['t2_h'], 2, s.lang)}\\,h.",
                          f"; equivalent at {num(hj['equiv']['T2_C'], 0, s.lang)}\\,\\textdegree{{}}C is {num(hj['equiv']['t2_h'], 2, s.lang)}\\,h.")
                      if hj.get("equiv") else "."))
    cb = res.get("carb")
    if cb:
        src = cb.get("src") or {}
        q = [src.get("q")] if src.get("q") else []
        s.fig(CH.fig_carb(cb, s.lang), "aufkohlung",
              tx(s.L(f"Kohlenstoffprofil nach {cb['t_h']:g} h bei {cb['T_C']:g} °C (Lösung der Diffusionsgleichung, halbunendlicher Körper).",
                     f"Carbon profile after {cb['t_h']:g} h at {cb['T_C']:g} °C (solution of the diffusion equation, semi-infinite body).")),
              cites=["callister"] + q, width="0.6")
        vd = s.val("caseDepth", s.L("Einsatzhärtungstiefe (Grenzgehalt)", "Case depth (limit content)"), cb.get("depth_mm"), 2, "mm")
        s.m.append(s.L(f"Aufkohlung als Diffusion in einen halbunendlichen Körper mit konstanter Randkonzentration{s.c('callister')}: "
                       "$c(x,t) = c_s - (c_s - c_0)\\,\\mathrm{erf}(x / (2\\sqrt{Dt}))$, $D = D_0 \\exp(-Q/(RT))$ mit "
                       f"$D_0$ = {num(cb['D0'] * 1e6, 1, s.lang)}\\,mm$^2$/s und Q = {num(cb['Q_kJ'], 0, s.lang)}\\,kJ/mol{s.c(q)}.",
                       f"Carburising as diffusion into a semi-infinite body with constant surface concentration{s.c('callister')}: "
                       "$c(x,t) = c_s - (c_s - c_0)\\,\\mathrm{erf}(x / (2\\sqrt{Dt}))$, $D = D_0 \\exp(-Q/(RT))$ with "
                       f"$D_0$ = {num(cb['D0'] * 1e6, 1, s.lang)}\\,mm$^2$/s and Q = {num(cb['Q_kJ'], 0, s.lang)}\\,kJ/mol{s.c(q)}."))
        if vd:
            s.r.append(s.L(f"Der Gehalt {num(cb['c_limit'], 2, s.lang)}\\,\\% C wird in {vd} Tiefe erreicht.",
                           f"The content of {num(cb['c_limit'], 2, s.lang)}\\,\\% C is reached at a depth of {vd}."))
        s.data("profil", ["x_mm", "c"], list(zip(cb["x_mm"], cb["c"])), tx(s.L("Kohlenstoffprofil.", "Carbon profile.")),
               labels={"x_mm": "x [mm]", "c": s.L("C [Ma.-\\%]", "C [wt\\%]")}, plot={"x": "x_mm", "y": "c"})


# ----------------------------------------------------------------------------- Laminat
CRIT = {"maxstress": ("Maximalspannung", "Maximum stress"), "tsaihill": ("Tsai-Hill", "Tsai-Hill"),
        "tsaiwu": ("Tsai-Wu", "Tsai-Wu"), "hashin": ("Hashin", "Hashin")}


def w_laminat(s: Sec, res: dict, req: dict):
    mat = res.get("material")
    mq = sorted({v["key"] for v in (mat or {}).get("src", {}).values() if v.get("key")})
    layup = req.get("layup") or ""
    e = res["eng"]
    rows = [[tx("E_x"), num(e["Ex"], 2, s.lang, "GPa")], [tx("E_y"), num(e["Ey"], 2, s.lang, "GPa")],
            [tx("G_xy"), num(e["Gxy"], 2, s.lang, "GPa")], [tx("ν_xy"), num(e["nuxy"], 3, s.lang)]]
    rows = [[r[0].replace("E\\_x", "$E_x$").replace("E\\_y", "$E_y$").replace("G\\_xy", "$G_{xy}$").replace("$\\nu$\\_xy", "$\\nu_{xy}$"), r[1]] for r in rows]
    s.table("steifigkeit", [s.L("Grösse", "Quantity"), s.L("Wert", "Value")], rows, "lr",
            tx(s.L(f"Ingenieurkonstanten des Laminats {layup} (Membran, aus A⁻¹).", f"Engineering constants of the laminate {layup} (membrane, from A⁻¹).")),
            cites=["daniel2006"] + mq)
    for k, lab, nd, u in (("Ex", "E_x", 2, "GPa"), ("Ey", "E_y", 2, "GPa"), ("Gxy", "G_xy", 2, "GPa"), ("nuxy", "ν_xy", 3, "")):
        s.val(k, lab, e[k], nd, u)
    fp = res.get("fpf") or {}
    rows = []
    for k, f in fp.items():
        if not f:
            continue
        rows.append([tx(CRIT.get(k, (k, k))[0 if s.de else 1]), num(f["R"], 2, s.lang), str(f["ply"]), num(f["angle"], 0, s.lang),
                     tx(f.get("mode") or "")])
        s.val(f"R-{k}", s.L(f"Reservefaktor {CRIT.get(k, (k,))[0]}", f"Reserve factor {CRIT.get(k, (k, k))[1]}"), f["R"], 2)
    s.table("versagen", [s.L("Kriterium", "Criterion"), "R", s.L("Lage", "Ply"), s.L("Winkel [°]", "Angle [°]"), s.L("Art", "Mode")],
            rows, "lrrrl", tx(s.L("Erstes Lagenversagen: Reservefaktor R (Last mal R bis zum Versagen der ersten Lage).",
                                  "First-ply failure: reserve factor R (load times R until the first ply fails).")),
            cites=["tsai1971", "azzi1965", "hashin1980"])
    s.fig(CH.fig_laminate(res, s.lang), "spannungen",
          tx(s.L(f"Spannungen in Lagenkoordinaten über die Dicke, Laminat {layup}.", f"Stresses in ply coordinates through the thickness, laminate {layup}.")),
          cites=["daniel2006"], width="0.85")
    s.m.append(s.L(f"Klassische Laminattheorie{s.c(['daniel2006', 'jones1999'])}: reduzierte Steifigkeiten je Lage, Transformation in "
                   "Laminatkoordinaten, ABD-Matrix, Verzerrungen und Krümmungen aus den Schnittgrössen. Versagenskriterien: "
                   f"Maximalspannung, Tsai-Hill{s.c('azzi1965')}, Tsai-Wu{s.c('tsai1971')} (F₁₂* = {num(float(req.get('F12') if req.get('F12') not in (None, '') else -0.5), 2, s.lang)}) "
                   f"und Hashin{s.c('hashin1980')}; ausgewertet an Ober- und Unterseite jeder Lage."
                   + (f" Lagenkennwerte {tx(mat['name'])}{s.c(mq)}." if mat else " Lagenkennwerte vom Nutzer."),
                   f"Classical laminate theory{s.c(['daniel2006', 'jones1999'])}: reduced stiffnesses per ply, transformation into laminate "
                   "coordinates, ABD matrix, strains and curvatures from the stress resultants. Failure criteria: maximum stress, "
                   f"Tsai-Hill{s.c('azzi1965')}, Tsai-Wu{s.c('tsai1971')} (F₁₂* = {num(float(req.get('F12') if req.get('F12') not in (None, '') else -0.5), 2, s.lang)}) "
                   f"and Hashin{s.c('hashin1980')}; evaluated at the top and bottom of each ply."
                   + (f" Ply properties {tx(mat['name'])}{s.c(mq)}." if mat else " Ply properties entered by the user.")).replace("F₁₂*", "$F_{12}^*$"))
    if fp:
        worst = min((f for f in fp.values() if f), key=lambda f: f["R"])
        s.r.append(s.L(f"Die erste Lage versagt bei R = {num(worst['R'], 2, s.lang)} (Lage {worst['ply']}, {num(worst['angle'], 0, s.lang)}\\,\\textdegree{{}}).",
                       f"The first ply fails at R = {num(worst['R'], 2, s.lang)} (ply {worst['ply']}, {num(worst['angle'], 0, s.lang)}\\,\\textdegree{{}})."))
    if not res.get("symmetric"):
        s.r.append(s.L("Das Laminat ist nicht symmetrisch (B ≠ 0): Membran- und Biegeverformung sind gekoppelt.",
                       "The laminate is not symmetric (B ≠ 0): membrane and bending deformation are coupled.").replace("≠", "$\\neq$"))


# ----------------------------------------------------------------------------- Ermüdung
def w_ermuedung(s: Sec, res: dict, req: dict):
    model = req.get("model") or "none"
    if res.get("fit"):
        f = res["fit"]
        best = f.get("mle") or f["lsq"]
        s.fig(CH.fig_sn(res, s.lang), "woehler", tx(s.L("Wöhlerlinie nach Basquin.", "S-N curve after Basquin.")),
              cites=["basquin1910"] + (["nelson1990"] if f.get("mle") else []), width="0.7")
        rows = [[s.L("kleinste Quadrate", "least squares"), num(f["lsq"]["sigma_f"], 0, s.lang), num(f["lsq"]["b"], 4, s.lang),
                 num(f["lsq_fit"]["r2"], 3, s.lang)]]
        if f.get("mle"):
            rows.append([s.L("Maximum Likelihood", "maximum likelihood"), num(f["mle"]["sigma_f"], 0, s.lang), num(f["mle"]["b"], 4, s.lang), "--"])
        s.table("basquin", [s.L("Verfahren", "Method"), "σ_f' [MPa]", "b", "R²"], rows, "lrrr",
                tx(s.L(f"Basquin-Parameter ({f['n_fail']} Brüche, {f['n_runout']} Durchläufer).",
                       f"Basquin parameters ({f['n_fail']} failures, {f['n_runout']} run-outs).")), cites=["basquin1910", "astme739"])
        vs = s.val("sigmaf", "σ_f'", best["sigma_f"], 0, "MPa")
        vb = s.val("b", s.L("Basquin-Exponent", "Basquin exponent"), best["b"], 4)
        s.m.append(s.L(f"Wöhlerlinie nach Basquin{s.c('basquin1910')} $\\sigma_a = \\sigma_f' (2N)^b$, ausgeglichen als lg N über lg σ_a "
                       f"nach ASTM E739{s.c('astme739')}" + (f"; Durchläufer als zensierte Werte nach Maximum Likelihood{s.c('nelson1990')}" if f.get("mle") else "") + ".",
                       f"S-N curve after Basquin{s.c('basquin1910')} $\\sigma_a = \\sigma_f' (2N)^b$, fitted as lg N on lg σ_a "
                       f"after ASTM E739{s.c('astme739')}" + (f"; run-outs as censored values by maximum likelihood{s.c('nelson1990')}" if f.get("mle") else "") + ".").replace("σ_a", "$\\sigma_a$"))
        s.r.append(s.L(f"Basquin: σ_f' = {vs}, b = {vb}.", f"Basquin: σ_f' = {vs}, b = {vb}.").replace("σ_f'", "$\\sigma_f'$"))
        if model != "none":
            names = {"goodman": "Goodman", "gerber": "Gerber", "soderberg": "Soderberg", "morrow": "Morrow", "swt": "Smith-Watson-Topper"}
            s.m.append(s.L(f"Mittelspannungen wurden nach {names.get(model, model)}{s.c(['swt1970'] if model == 'swt' else ['dowling'])} in "
                           "gleichwertige Wechselamplituden umgerechnet.",
                           f"Mean stresses were converted to equivalent fully reversed amplitudes after {names.get(model, model)}"
                           f"{s.c(['swt1970'] if model == 'swt' else ['dowling'])}."))
        if res.get("S_at_N"):
            vn = s.val("SatN", s.L("Dauerfestigkeit bei N", "Strength at N"), res["S_at_N"], 0, "MPa")
            s.r.append(s.L(f"Bei N = {big(float(req['N_target']), s.lang)} ergibt die Linie {vn}.",
                           f"At N = {big(float(req['N_target']), s.lang)} the curve gives {vn}."))
        s.data("woehler", ["N", "sar", "runout"], [[p["N"], p["sar"], int(p["runout"])] for p in res["points"]],
               tx(s.L("Wöhlerversuche (gleichwertige Amplitude).", "Fatigue tests (equivalent amplitude).")),
               labels={"N": "N", "sar": r"$\sigma_{ar}$ [MPa]"}, plot={"x": "N", "y": "sar", "style": "marks"})
    mr = res.get("marin")
    if mr:
        rows = [[k, num(mr[k], 3, s.lang)] for k in ("ka", "kb", "kc", "kd", "ke")] + [["Se'", num(mr["Se_prime"], 0, s.lang, "MPa")],
                                                                                     ["Se", num(mr["Se"], 0, s.lang, "MPa")]]
        s.table("marin", [s.L("Faktor", "Factor"), s.L("Wert", "Value")], [[tx(a), b] for a, b in rows], "lr",
                tx(s.L("Dauerfestigkeit des Bauteils nach Marin (Näherungen nach Shigley).", "Component endurance limit after Marin (approximations after Shigley).")),
                cites=["shigley"])
        vse = s.val("Se", s.L("Bauteil-Dauerfestigkeit", "Component endurance limit"), mr["Se"], 0, "MPa")
        s.m.append(s.L(f"Bauteildauerfestigkeit $S_e = k_a k_b k_c k_d k_e S_e'$ nach Marin mit den Faktoren aus Shigley{s.c('shigley')}"
                       + ("; $S_e'$ aus der Stahlnäherung $0{,}5\\,R_m$ (höchstens 700\\,MPa)." if "Näherung" in " ".join(mr.get("notes") or []) else "."),
                       f"Component endurance limit $S_e = k_a k_b k_c k_d k_e S_e'$ after Marin with factors from Shigley{s.c('shigley')}"
                       + ("; $S_e'$ from the steel approximation $0.5\\,R_m$ (at most 700\\,MPa)." if "Näherung" in " ".join(mr.get("notes") or []) else ".")))
        s.r.append(s.L(f"Bauteildauerfestigkeit: {vse}.", f"Component endurance limit: {vse}."))
    if res.get("haigh"):
        s.fig(CH.fig_haigh(res, s.lang), "haigh", tx(s.L(f"Haigh-Diagramm mit S_e = {res['haigh_Se']:.0f} MPa.",
                                                          f"Haigh diagram with S_e = {res['haigh_Se']:.0f} MPa.")), cites=["dowling"], width="0.65")
    rf = res.get("rainflow")
    if rf:
        s.fig(CH.fig_rainflow(rf, s.lang), "rainflow", tx(s.L(f"Rainflow-Zählung ({rf['n_cycles']:g} Zyklen).", f"Rainflow count ({rf['n_cycles']:g} cycles).")),
              cites=["astme1049"], width="0.6")
        s.m.append(s.L(f"Lastfolge mit dem Rainflow-Verfahren nach ASTM E1049{s.c('astme1049')} gezählt.",
                       f"Load history counted by the rainflow method after ASTM E1049{s.c('astme1049')}."))
        mi = res.get("miner")
        if mi:
            vd = s.val("D", s.L("Schadenssumme", "Damage sum"), mi["D"], 4, text=f"{mi['D']:.4g}")
            s.m.append(s.L(f"Schadenssumme linear nach Palmgren-Miner{s.c('miner1945')}.", f"Damage summed linearly after Palmgren-Miner{s.c('miner1945')}."))
            s.r.append(s.L(f"Schadenssumme je Durchlauf D = {vd}" + (f", rechnerisch {num(mi['blocks_to_failure'], 0, s.lang)} Durchläufe bis zum Bruch." if mi.get("blocks_to_failure") and mi["blocks_to_failure"] < 1e12 else "."),
                           f"Damage per pass D = {vd}" + (f", i.e. {num(mi['blocks_to_failure'], 0, s.lang)} passes to failure." if mi.get("blocks_to_failure") and mi["blocks_to_failure"] < 1e12 else ".")))


# ----------------------------------------------------------------------------- Weibull, Bruch
def w_weibull(s: Sec, res: dict, req: dict):
    meth = res["method"]
    best = res[meth]
    s.fig(CH.fig_weibull(res, s.lang), "diagramm", tx(s.L(f"Weibull-Diagramm ({best['n']} Proben).", f"Weibull plot ({best['n']} specimens).")),
          cites=["weibull1951", "bernard1953"], width="0.65")
    bo = res.get("boot") or {}
    rows = [[s.L("Weibull-Modul m", "Weibull modulus m"), num(best["m"], 2, s.lang),
             (num(bo["m_ci"][0], 2, s.lang) + " -- " + num(bo["m_ci"][1], 2, s.lang)) if bo else "--"],
            [s.L("Skalenparameter σ₀", "Scale parameter σ₀"), num(best["sigma0"], 1, s.lang),
             (num(bo["sigma0_ci"][0], 1, s.lang) + " -- " + num(bo["sigma0_ci"][1], 1, s.lang)) if bo else "--"]]
    for P, v in res["q"].items():
        rows.append([s.L(f"Festigkeit bei P_f = {float(P) * 100:g} %", f"Strength at P_f = {float(P) * 100:g} %"), num(v, 1, s.lang), "--"])
    lev = int(round(100 * bo.get("level", 0.9)))
    s.table("kennwerte", [s.L("Grösse", "Quantity"), s.L("Wert", "Value"), s.L(f"{lev}-%-Bereich", f"{lev} % interval")],
            [[tx(r[0]), r[1], r[2]] for r in rows], "lrr",
            tx(s.L(f"Weibull-Parameter ({'Maximum Likelihood' if meth == 'mle' else 'Rangregression'}).",
                   f"Weibull parameters ({'maximum likelihood' if meth == 'mle' else 'rank regression'}).")),
            cites=["weibull1951"] + (["astmc1239"] if meth == "mle" else ["bernard1953"]) + (["efron1993"] if bo else []))
    vm = s.val("m", s.L("Weibull-Modul", "Weibull modulus"), best["m"], 2)
    vs = s.val("sigma0", s.L("Skalenparameter", "Scale parameter"), best["sigma0"], 1)
    s.m.append(s.L(f"Zweiparametrige Weibull-Verteilung{s.c('weibull1951')} $P_f = 1 - \\exp(-(\\sigma/\\sigma_0)^m)$, "
                   + (f"Parameter nach Maximum Likelihood (ASTM C1239{s.c('astmc1239')}, ohne Korrekturfaktor für kleine Stichproben)"
                      if meth == "mle" else f"Parameter aus der Regression der Ränge $F_i = (i - 0{{,}}3)/(n + 0{{,}}4)${s.c('bernard1953')}")
                   + (f"; Vertrauensbereiche durch parametrischen Bootstrap{s.c('efron1993')} ({bo['B']} Stichproben, Startwert {bo['seed']})." if bo else "."),
                   f"Two-parameter Weibull distribution{s.c('weibull1951')} $P_f = 1 - \\exp(-(\\sigma/\\sigma_0)^m)$, "
                   + (f"parameters by maximum likelihood (ASTM C1239{s.c('astmc1239')}, without small-sample correction factor)"
                      if meth == "mle" else f"parameters from regression on the ranks $F_i = (i - 0.3)/(n + 0.4)${s.c('bernard1953')}")
                   + (f"; confidence intervals by parametric bootstrap{s.c('efron1993')} ({bo['B']} samples, seed {bo['seed']})." if bo else ".")))
    s.r.append(s.L(f"Weibull-Modul m = {vm}, Skalenparameter σ₀ = {vs}.", f"Weibull modulus m = {vm}, scale parameter σ₀ = {vs}.").replace("σ₀", "$\\sigma_0$"))
    sz = res.get("size")
    if sz:
        v2 = s.val("sigma2", s.L("Festigkeit beim zweiten Volumen", "Strength at the second volume"), sz["sigma2"], 1)
        s.m.append(s.L(f"Grösseneffekt über effektive Volumina{s.c(['weibull1951', 'quinn2003'])}: $\\sigma_2/\\sigma_1 = (V_1/V_2)^{{1/m}}$.",
                       f"Size effect via effective volumes{s.c(['weibull1951', 'quinn2003'])}: $\\sigma_2/\\sigma_1 = (V_1/V_2)^{{1/m}}$."))
        s.r.append(s.L(f"Auf das zweite effektive Volumen übertragen: σ₀ = {v2}.", f"Scaled to the second effective volume: σ₀ = {v2}.").replace("σ₀", "$\\sigma_0$"))
    s.data("werte", ["sigma", "F"], list(zip(res["lsq"]["x"], res["lsq"]["F"])), tx(s.L("Festigkeiten und Ränge.", "Strengths and ranks.")),
           labels={"sigma": r"$\sigma$", "F": "F"}, plot={"x": "sigma", "y": "F", "style": "marks"})


def w_bruch(s: Sec, res: dict, req: dict):
    s.unc(res)
    kq = res.get("kq")
    if kq:
        geom = {"senb": "SE(B)", "ct": "C(T)"}.get((req.get("kq") or {}).get("geom", "senb"), "")
        rows = [[tx(c["name"]), num(c["value"], 3, s.lang), num(c.get("limit"), 3, s.lang), s.L("ja", "yes") if c["ok"] else s.L("nein", "no")]
                for c in kq["checks"]]
        s.table("e399", [s.L("Prüfung", "Check"), s.L("Wert", "Value"), s.L("Grenze", "Limit"), "OK"], rows, "lrrl",
                tx(s.L(f"Gültigkeit nach ASTM E399, Probe {geom}.", f"Validity after ASTM E399, specimen {geom}.")), cites=["astme399"])
        vk = s.val("KQ", "K_Q", kq["K"], 2, "MPa√m")
        s.m.append(s.L(f"K_Q nach ASTM E399{s.c('astme399')} mit der Geometriefunktion f(a/W) der Probe {geom}.",
                       f"K_Q after ASTM E399{s.c('astme399')} with the geometry function f(a/W) of the {geom} specimen.").replace("K_Q", "$K_Q$"))
        s.r.append(s.L(f"$K_Q$ = {vk}; " + ("die Prüfungen sind erfüllt, $K_Q$ gilt als $K_{Ic}$." if kq["valid_KIc"] else
                                           ("mindestens eine Prüfung ist nicht erfüllt, $K_Q$ ist kein gültiger $K_{Ic}$." if kq["complete"]
                                            else "nicht alle Prüfungen sind möglich (Rp oder P_max fehlt).")),
                       f"$K_Q$ = {vk}; " + ("all checks pass, $K_Q$ qualifies as $K_{Ic}$." if kq["valid_KIc"] else
                                            ("at least one check fails, $K_Q$ is not a valid $K_{Ic}$." if kq["complete"]
                                             else "not all checks are possible (Rp or P_max missing)."))).replace("P_max", "$P_{max}$"))
    cr = res.get("crack")
    if cr:
        s.fig(CH.fig_crack(cr, s.lang), "risslaenge", tx(s.L("Kritische Risslänge über der Spannung.", "Critical crack length versus stress.")),
              cites=["anderson"], width="0.6")
        va = s.val("ac", s.L("kritische Risslänge", "critical crack length"), cr["a_c_mm"], 2, "mm")
        s.m.append(s.L(f"Kritische Risslänge $a_c = (1/\\pi)(K_{{Ic}}/(Y\\sigma))^2${s.c('anderson')}.",
                       f"Critical crack length $a_c = (1/\\pi)(K_{{Ic}}/(Y\\sigma))^2${s.c('anderson')}."))
        s.r.append(s.L(f"Bei σ = {num(cr['sigma'], 0, s.lang)}\\,MPa und Y = {num(cr['Y'], 2, s.lang)} ist die kritische Risslänge {va}.",
                       f"At σ = {num(cr['sigma'], 0, s.lang)}\\,MPa and Y = {num(cr['Y'], 2, s.lang)} the critical crack length is {va}.").replace("σ", "$\\sigma$"))


# ----------------------------------------------------------------------------- Härte
def w_haerte(s: Sec, res: dict, req: dict):
    s.unc(res)
    meth = res["method"]
    q = {"HV": "iso6507", "HBW": "iso6506", "HK": "iso4545"}[meth]
    ok = [r for r in res["rows"] if "value" in r]
    if ok:
        rows = [[str(i + 1), num(r["d"], 4, s.lang), tx(r["scale"]), num(r["value"], 0 if r["value"] >= 100 else 1, s.lang)] for i, r in enumerate(ok)]
        st = res["stats"]
        s.table("eindruecke", ["#", "d [mm]", s.L("Skala", "Scale"), s.L("Härte", "Hardness")], rows, "rrlr",
                tx(s.L(f"Härte aus den Eindrücken ({meth}).", f"Hardness from the indents ({meth}).")), cites=[q])
        vm = s.val("mean", s.L("Mittlere Härte", "Mean hardness"), st["mean"], 0 if st["mean"] >= 100 else 1, ok[0]["scale"].split()[0])
        vs = s.val("sd", s.L("Standardabweichung", "Standard deviation"), st.get("sd"), 1)
        names = {"HV": "Vickers", "HBW": "Brinell", "HK": "Knoop"}
        form = {"HV": "HV = 0{,}1891\\,F/d^2", "HBW": "HBW = 0{,}102 \\cdot 2F/(\\pi D (D - \\sqrt{D^2 - d^2}))", "HK": "HK = 1{,}451\\,F/d^2"}[meth]
        if not s.de:
            form = form.replace("{,}", ".")
        s.m.append(s.L(f"Härte nach {names[meth]}{s.c(q)}: ${form}$ (F in N, d in mm).", f"Hardness after {names[meth]}{s.c(q)}: ${form}$ (F in N, d in mm)."))
        s.r.append(s.L(f"Mittlere Härte {vm}" + (f" (Standardabweichung {vs}, n = {st['n']})." if vs else "."),
                       f"Mean hardness {vm}" + (f" (standard deviation {vs}, n = {st['n']})." if vs else ".")))
        for r in ok:
            for n in r.get("notes") or []:
                s.r.append(tx(n) + ".")
    if res.get("converted") and res.get("table"):
        tb = res["table"]
        key = "umwertung-" + slugify(tb["name"], 20)
        if s.inc.get("citations", True):
            s.b.add_citation(key, "misc", title=tex_escape(tb["source"] or tb["name"]),
                             note=tex_escape(s.L("vom Nutzer geladene Umwertungstabelle", "conversion table loaded by the user")))
        cv = res["converted"]
        to = (req.get("convert") or {}).get("to")
        if cv.get("value") is not None:
            v = s.val("conv", s.L(f"Umgewertet in {to}", f"Converted to {to}"), cv["value"], 1, to if to == "Rm" else "")
            s.r.append(s.L(f"Umgewertet nach der Tabelle~\\cite{{{key}}} (linear interpoliert): {v} {tx(to)}.",
                           f"Converted with the table~\\cite{{{key}}} (linear interpolation): {v} {tx(to)}."))
        else:
            s.r.append(tx(cv.get("note") or ""))
    elif res.get("rule"):
        v = s.val("RmRule", s.L("Zugfestigkeit (Faustregel)", "Tensile strength (rule of thumb)"), res["rule"]["value"], 0, "MPa")
        s.r.append(s.L(f"Nur als Faustregel für Stahl{s.c('callister')}: $R_m \\approx 3{{,}}3\\cdot HV$ = {v} (keine Umwertung nach Norm).",
                       f"Only as a rule of thumb for steel{s.c('callister')}: $R_m \\approx 3.3\\cdot HV$ = {v} (not a standard conversion)."))
    g = res.get("grain")
    if g:
        vg = s.val("G", s.L("Korngrössenkennzahl G", "Grain size number G"), g["G"], 1)
        s.m.append(s.L(f"Korngrösse nach ASTM E112{s.c('astme112')}" + (": Linienschnittverfahren, $G = -6{,}6457 \\lg \\bar\\ell - 3{,}298$ ($\\bar\\ell$ in mm)."
                                                                      if "l_mm" in g else ": Planimetrie, $G = 3{,}3219 \\lg N_A - 2{,}954$."),
                       f"Grain size after ASTM E112{s.c('astme112')}" + (": intercept method, $G = -6.6457 \\lg \\bar\\ell - 3.298$ ($\\bar\\ell$ in mm)."
                                                                         if "l_mm" in g else ": planimetric method, $G = 3.3219 \\lg N_A - 2.954$.")))
        if "l_mm" in g:
            vl = s.val("l", s.L("mittlere Sehnenlänge", "mean intercept length"), g["l_um"], 1, "µm")
            s.r.append(s.L(f"Mittlere Sehnenlänge {vl}, Korngrössenkennzahl G = {vg}.", f"Mean intercept length {vl}, grain size number G = {vg}."))
        else:
            s.r.append(s.L(f"Korngrössenkennzahl G = {vg}.", f"Grain size number G = {vg}."))
    hp = res.get("hp")
    if hp:
        s.fig(CH.fig_hp(hp, s.lang), "hallpetch", tx(s.L("Hall-Petch-Auftragung.", "Hall-Petch plot.")), cites=["hall1951", "petch1953"], width="0.55")
        v0 = s.val("hpSigma0", "σ₀", hp["sigma0"], 0, "MPa")
        vk = s.val("hpK", "k_y", hp["k"], 3, "MPa√m")
        s.m.append(s.L(f"Hall-Petch-Gerade{s.c(['hall1951', 'petch1953'])} $\\sigma_y = \\sigma_0 + k_y d^{{-1/2}}$.",
                       f"Hall-Petch line{s.c(['hall1951', 'petch1953'])} $\\sigma_y = \\sigma_0 + k_y d^{{-1/2}}$."))
        s.r.append(s.L(f"Hall-Petch: $\\sigma_0$ = {v0}, $k_y$ = {vk} ($R^2$ = {num(hp['r2'], 3, s.lang)}).",
                       f"Hall-Petch: $\\sigma_0$ = {v0}, $k_y$ = {vk} ($R^2$ = {num(hp['r2'], 3, s.lang)})."))


# ----------------------------------------------------------------------------- Korrosion, Kriechen
def w_korrosion(s: Sec, res: dict, req: dict):
    fc = ""
    if req.get("item"):
        fc = _file_cite(s, s.ctx.get(req["item"]))
    s.fig(CH.fig_tafel(res, s.lang), "tafel", tx(s.L("Polarisationskurve mit Tafel-Geraden.", "Polarisation curve with Tafel lines.")) + fc,
          cites=["stern1957"], width="0.65")
    ve = s.val("Ecorr", "E_corr", res["Ecorr"], 3, "V")
    vi = s.val("icorr", "i_corr", res["icorr"], 3, "µA/cm²")
    va = s.val("ba", "β_a", res["ba"], 0, "mV/dec")
    vc = s.val("bc", "β_c", res["bc"], 0, "mV/dec")
    s.m.append(s.L(f"Tafel-Auswertung{s.c(['stern1957', 'bard'])}: je Ast eine Gerade E über lg|i| im Bereich η = "
                   f"{num(1e3 * float(req.get('eta_min') or 0.05), 0, s.lang)} bis {num(1e3 * float(req.get('eta_max') or 0.15), 0, s.lang)}\\,mV; "
                   "der Schnittpunkt ergibt $E_{corr}$ und $i_{corr}$.",
                   f"Tafel evaluation{s.c(['stern1957', 'bard'])}: one line E versus lg|i| per branch in the range η = "
                   f"{num(1e3 * float(req.get('eta_min') or 0.05), 0, s.lang)} to {num(1e3 * float(req.get('eta_max') or 0.15), 0, s.lang)}\\,mV; "
                   "their intersection gives $E_{corr}$ and $i_{corr}$.").replace("η", "$\\eta$"))
    s.r.append(s.L(f"$E_{{corr}}$ = {ve}, $i_{{corr}}$ = {vi}, $\\beta_a$ = {va}, $\\beta_c$ = {vc}.",
                   f"$E_{{corr}}$ = {ve}, $i_{{corr}}$ = {vi}, $\\beta_a$ = {va}, $\\beta_c$ = {vc}."))
    if res.get("Rp"):
        vr = s.val("Rp", "R_p", res["Rp"], 1, "Ω·cm²")
        s.m.append(s.L(f"Polarisationswiderstand aus der Steigung in ±10\\,mV um $E_{{corr}}$ (ASTM G59{s.c('astmg59')}), Stern-Geary-Konstante "
                       "$B = \\beta_a\\beta_c/(2{,}303(\\beta_a + \\beta_c))$.",
                       f"Polarisation resistance from the slope within ±10\\,mV of $E_{{corr}}$ (ASTM G59{s.c('astmg59')}), Stern-Geary constant "
                       "$B = \\beta_a\\beta_c/(2.303(\\beta_a + \\beta_c))$.").replace("±", "$\\pm$"))
        s.r.append(s.L(f"$R_p$ = {vr}.", f"$R_p$ = {vr}."))
    if res.get("bv") and not res["bv"].get("error"):
        bv = res["bv"]
        s.m.append(s.L("Zusätzlich wurde die Butler-Volmer-Gleichung um $E_{corr}$ angepasst (Levenberg-Marquardt).",
                       "In addition, the Butler-Volmer equation was fitted around $E_{corr}$ (Levenberg-Marquardt)."))
        s.r.append(s.L(f"Butler-Volmer: $i_{{corr}}$ = {num(bv['icorr'], 3, s.lang)}\\,$\\mu$A/cm$^2$, $\\beta_a$ = {num(bv['ba'], 0, s.lang)}, $\\beta_c$ = {num(bv['bc'], 0, s.lang)}\\,mV/dec.",
                       f"Butler-Volmer: $i_{{corr}}$ = {num(bv['icorr'], 3, s.lang)}\\,$\\mu$A/cm$^2$, $\\beta_a$ = {num(bv['ba'], 0, s.lang)}, $\\beta_c$ = {num(bv['bc'], 0, s.lang)}\\,mV/dec."))
    if res.get("rate"):
        vcr = s.val("CR", s.L("Abtragsrate", "Corrosion rate"), res["rate"]["mm_a"], 4, "mm/a")
        s.m.append(s.L(f"Abtragsrate nach ASTM G102{s.c('astmg102')}: $CR = K_1\\,i_{{corr}}\\,EW/\\rho$ mit EW = {num(res['EW'], 2, s.lang)} und "
                       f"ρ = {num(res['rho'], 3, s.lang)}\\,g/cm$^3$.",
                       f"Corrosion rate after ASTM G102{s.c('astmg102')}: $CR = K_1\\,i_{{corr}}\\,EW/\\rho$ with EW = {num(res['EW'], 2, s.lang)} and "
                       f"ρ = {num(res['rho'], 3, s.lang)}\\,g/cm$^3$.").replace("ρ", "$\\rho$"))
        s.r.append(s.L(f"Abtragsrate {vcr}.", f"Corrosion rate {vcr}."))


def w_kriechen(s: Sec, res: dict, req: dict):
    lmp = res.get("lmp")
    if lmp:
        s.fig(CH.fig_lmp(lmp, s.lang), "lmp", tx(s.L("Larson-Miller-Auftragung.", "Larson-Miller plot.")), cites=["larsonmiller1952"], width="0.6")
        vc = s.val("C", "C", lmp["C"], 1)
        s.m.append(s.L(f"Larson-Miller-Parameter{s.c('larsonmiller1952')} $P = T\\,(C + \\lg t_r)$ (T in K, $t_r$ in h), "
                       + ("C angepasst (kleinste Streuung)" if lmp["C_fitted"] else f"C = {num(lmp['C'], 0, s.lang)}")
                       + f"; lg σ als Polynom {lmp['deg']}. Grades in P.",
                       f"Larson-Miller parameter{s.c('larsonmiller1952')} $P = T\\,(C + \\lg t_r)$ (T in K, $t_r$ in h), "
                       + ("C fitted (least scatter)" if lmp["C_fitted"] else f"C = {num(lmp['C'], 0, s.lang)}")
                       + f"; lg σ as a polynomial of degree {lmp['deg']} in P.").replace("σ", "$\\sigma$"))
        s.r.append(s.L(f"Larson-Miller: C = {vc}, $R^2$ = {num(lmp['r2'], 3, s.lang)}.", f"Larson-Miller: C = {vc}, $R^2$ = {num(lmp['r2'], 3, s.lang)}."))
        pr = res.get("predict")
        if pr and pr.get("t_h"):
            vt = s.val("tr", s.L("Bruchzeit", "Rupture time"), pr["t_h"], 0, "h")
            p = req.get("predict") or {}
            s.r.append(s.L(f"Für σ = {num(float(p['s']), 0, s.lang)}\\,MPa bei {num(float(p['T']), 0, s.lang)}\\,\\textdegree{{}}C ergibt die Kurve {vt}.",
                           f"For σ = {num(float(p['s']), 0, s.lang)}\\,MPa at {num(float(p['T']), 0, s.lang)}\\,\\textdegree{{}}C the curve gives {vt}.").replace("σ", "$\\sigma$"))
        elif pr:
            s.r.append(tx(pr.get("note") or ""))
    nt = res.get("norton")
    if nt:
        s.fig(CH.fig_norton(nt, s.lang), "norton", tx(s.L("Kriechraten nach Norton.", "Creep rates after Norton.")), cites=["norton1929"], width="0.6")
        vn = s.val("n", s.L("Spannungsexponent", "Stress exponent"), nt["n"], 2)
        vq = s.val("Q", s.L("Aktivierungsenergie", "Activation energy"), nt.get("Q_kJ"), 0, "kJ/mol")
        s.m.append(s.L(f"Stationäres Kriechen nach Norton{s.c(['norton1929', 'dowling'])}: $\\dot\\varepsilon = A\\sigma^n\\exp(-Q/(RT))$, "
                       "Ausgleich in lg-Form (multiple Regression).",
                       f"Steady-state creep after Norton{s.c(['norton1929', 'dowling'])}: $\\dot\\varepsilon = A\\sigma^n\\exp(-Q/(RT))$, "
                       "fitted in log form (multiple regression)."))
        s.r.append(s.L(f"Norton: n = {vn}" + (f", Q = {vq}." if vq else "."), f"Norton: n = {vn}" + (f", Q = {vq}." if vq else ".")))


WRITERS = {"auswahl": w_auswahl, "karten": w_karten, "kristall": w_kristall, "struktur": w_struktur, "gitter": w_gitter, "xrd": w_xrd, "phasen": w_phasen,
           "stahl": w_stahl, "laminat": w_laminat, "ermuedung": w_ermuedung, "weibull": w_weibull, "bruch": w_bruch,
           "haerte": w_haerte, "korrosion": w_korrosion, "kriechen": w_kriechen}


def build(request: dict, ctx: T.Ctx, files: dict[str, bytes]) -> dict:
    if any(x.get("tool") == "infotafel" for x in request.get("sections") or []):     # Infotafel: aus den Pin-Datensätzen
        from . import infoboard as IB
        return IB.build_bundle(request)
    lang = request.get("lang") if request.get("lang") in ("de", "en") else "de"
    inc = {"figures": True, "tables": True, "values": True, "data": True, "citations": True, "text": True,
           **(request.get("include") or {})}
    if inc["text"]:
        inc["values"] = inc["citations"] = True
    secs = [x for x in (request.get("sections") or []) if x.get("tool") in WRITERS]
    if not secs:
        raise T.ToolError("Kein Abschnitt für den Bericht")
    labels = [NAMES[x["tool"]][0 if lang == "de" else 1] for x in secs]
    title = request.get("title") or ((("Werkstoffe: " if lang == "de" else "Materials: ") + ", ".join(dict.fromkeys(labels))))
    b = Bundle(module="werkstoffe", module_name="Werkstoffe" if lang == "de" else "Materials", title=title, lang=lang,
               slug=request.get("slug") or None, summary=" · ".join(dict.fromkeys(labels)))
    count: dict[str, int] = {}
    methods, results, pids = [], [], []
    for x in secs:
        tool = x["tool"]
        count[tool] = count.get(tool, 0) + 1
        pid = tool if count[tool] == 1 else f"{tool}{count[tool]}"
        req = {**(x.get("req") or {}), "lang": lang}
        res = T.run(tool, req, ctx)
        s = Sec(b, lang, inc, pid, ctx)
        mark = b.added_mark()
        WRITERS[tool](s, res, req)
        s.finish()
        b.needs_since(mark, [pid])                     # Tabellen und Werte gehören zum Methodentext ihres Werkzeugs
        pids.append(pid)
        head = NAMES[tool][0 if lang == "de" else 1]
        if s.m:
            methods.append(step_tag(pid) + f"\\paragraph{{{tex_escape(head)}}} " + " ".join(s.m) + _unchecked(s, res))
        if s.r:
            results.append(f"\\paragraph{{{tex_escape(head)}}} " + " ".join(s.r))
    if inc["text"]:
        if methods:
            b.add_methods(methods, "Methodik" if lang == "de" else "Methods")
        if results:
            b.add_text("ergebnisse", "\n\n".join(results) + "\n", "Ergebnisse" if lang == "de" else "Results", steps=pids)
    b.set_source({**request, "slug": b.slug}, files)
    return b.to_dict()
