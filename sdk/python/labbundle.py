"""Folio Lab bundle toolkit for Python analysis modules.

A *bundle* is what an analysis module hands to the report editor: figures (vector PDF plus a
PNG preview), LaTeX tables, live values, CSV data, citations and ready-made text. The hub
writes it into a report project under ``lab/<slug>/``; the editor inserts the pieces.

Format: see docs/MODULES.md ("folio-lab-bundle/1"). Typical use in a module::

    from labbundle import Bundle, booktabs, tex_escape, num
    b = Bundle(module="ftir", module_name="FTIR", title="FTIR Probe A", lang="en")
    b.add_figure(fig, "spectrum", caption="Absorbance spectrum of sample A")
    b.add_table("peaks", booktabs(["Peak", "Wavenumber"], rows), caption="Assigned peaks")
    b.add_values([("A_max", "Maximum absorbance", num(0.82, 2, "en"), "")])
    b.add_citation("iso-xyz", "misc", title="...", year="2020")
    return b.to_dict()
"""
from __future__ import annotations

import base64
import io
import re
import unicodedata
from datetime import datetime

FORMAT = "folio-lab-bundle/1"


# ----------------------------------------------------------------------------- text helpers
def slugify(s: str, maxlen: int = 40) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return (s[:maxlen].rstrip("-")) or "result"


# Unicode characters that pdfLaTeX cannot set in text mode, mapped to LaTeX.
_UNI = {
    "σ": r"$\sigma$", "ε": r"$\varepsilon$", "Δ": r"$\Delta$", "δ": r"$\delta$", "μ": r"$\mu$", "µ": r"$\mu$",
    "λ": r"$\lambda$", "ν": r"$\nu$", "π": r"$\pi$", "α": r"$\alpha$", "β": r"$\beta$", "γ": r"$\gamma$",
    "Ω": r"$\Omega$", "θ": r"$\theta$", "τ": r"$\tau$", "ρ": r"$\rho$", "φ": r"$\varphi$",
    "₀": r"$_0$", "₁": r"$_1$", "₂": r"$_2$", "₃": r"$_3$", "²": r"$^2$", "³": r"$^3$", "⁻": r"$^-$", "¹": r"$^1$",
    "≈": r"$\approx$", "±": r"$\pm$", "·": r"$\cdot$", "×": r"$\times$", "−": r"$-$", "→": r"$\rightarrow$",
    "≤": r"$\leq$", "≥": r"$\geq$", "°": r"\textdegree{}", "–": "--", "—": "---", "…": r"\dots{}",
    "„": ",,", "“": "``", "”": "''", "‘": "`", "’": "'", "√": r"$\surd$", "∞": r"$\infty$",
    "₄": r"$_4$", "₅": r"$_5$", "₆": r"$_6$", "₇": r"$_7$", "₈": r"$_8$", "₉": r"$_9$", "⁰": r"$^0$", "⁴": r"$^4$",
    "⁵": r"$^5$", "⁶": r"$^6$", "⁷": r"$^7$", "⁸": r"$^8$", "⁹": r"$^9$", "⁺": r"$^+$", "⇌": r"$\rightleftharpoons$",
    "<": r"$<$", ">": r"$>$",
}
_SPECIAL = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
            "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}


_SUP = {"⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9", "⁻": "-",
        "⁺": "+"}
_SUB = {"₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4", "₅": "5", "₆": "6", "₇": "7", "₈": "8", "₉": "9"}
_RUN = re.compile("([" + "".join(_SUP) + "]{2,}|[" + "".join(_SUB) + "]{2,})")


def _runs(s: str) -> str:
    """Runs of two or more super-/subscript characters as one group (10⁻⁶ -> $^{-6}$, not $^-^6$)."""
    def rep(m):
        t = m.group(0)
        if t[0] in _SUP:
            return "\x02" + "".join(_SUP[c] for c in t) + "\x03"
        return "\x04" + "".join(_SUB[c] for c in t) + "\x05"
    return _RUN.sub(rep, s)


# Combining accents (ν̃ = ν + U+0303) set as math accents over the base character.
_COMB = {"̃": "tilde", "̂": "hat", "̄": "bar", "̇": "dot", "̈": "ddot", "⃗": "vec"}


def tex_escape(s) -> str:
    """Plain text -> LaTeX text-mode source (special characters, Greek letters and combining accents handled)."""
    out = []
    t = _runs(str(s))
    for i, ch in enumerate(t):
        if ch in _COMB:
            continue
        nxt = t[i + 1] if i + 1 < len(t) else ""
        if nxt in _COMB and (ch.isalpha() or ch in _UNI):
            base = _UNI.get(ch, ch).strip("$")
            out.append(f"$\\{_COMB[nxt]}{{{base}}}$")
        elif ch == "\x02":
            out.append("$^{")
        elif ch == "\x04":
            out.append("$_{")
        elif ch in "\x03\x05":
            out.append("}$")
        elif ch in _SPECIAL:
            out.append(_SPECIAL[ch])
        elif ch in _UNI:
            out.append(_UNI[ch])
        else:
            out.append(ch)
    return "".join(out).replace("$$", "")


def num(v, nd: int = 1, lang: str = "de", unit: str = "") -> str:
    """Number as LaTeX text with the decimal mark of the language and a thin space before the unit."""
    if v is None:
        return "--"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return tex_escape(v)
    if f != f:
        return "--"
    s = f"{f:.{nd}f}"
    if lang == "de":
        s = s.replace(".", ",")
    s = s.replace("-", r"$-$")
    return s + (r"\," + tex_escape(unit) if unit else "")


def cite_keys(*groups) -> list[str]:
    """Citation keys from several lists/strings ("a,b"), in order, without duplicates or blanks."""
    out: list[str] = []
    for g in groups:
        for k in ([g] if isinstance(g, str) else (g or [])):
            for part in str(k).split(","):
                part = part.strip()
                if part and part not in out:
                    out.append(part)
    return out


def cite(keys, sep: str = "~") -> str:
    """``~\\cite{a,b}`` (empty string without keys)."""
    keys = cite_keys(keys)
    return f"{sep}\\cite{{{','.join(keys)}}}" if keys else ""


def cite_caption(caption: str, keys) -> str:
    """Caption with the sources of what it shows: ``... field of group X~\\cite{a,b}.``

    Figures and tables that show third-party data (reference spectra, material values, standards) carry their
    citations in the caption, so inserting only that figure or table into a report still cites its sources."""
    c = cite(keys)
    if not c:
        return caption
    s = caption.rstrip()
    if s.endswith("."):
        return s[:-1] + c + "."
    return s + c


def join_list(frags, lang: str = "de") -> str:
    """"A, B und C" / "A, B and C"."""
    frags = [f for f in frags if f]
    if len(frags) <= 1:
        return "".join(frags)
    return ", ".join(frags[:-1]) + (" und " if lang == "de" else " and ") + frags[-1]


def clean_parts(parts) -> list[dict]:
    """Parts of a figure as declared by a module (see add_figure), checked: {id, label, cites, steps, caption, note,
    match}."""
    out, seen = [], set()
    for p in parts or []:
        if not isinstance(p, dict) or not p.get("id") or str(p["id"]) in seen:
            continue
        pid = str(p["id"])
        if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.:-]{0,59}", pid):
            raise ValueError(f"part id must be alphanumeric (with _ . : -): {pid!r}")
        seen.add(pid)
        m = p.get("match") or []
        out.append({"id": pid, "label": str(p.get("label") or pid), "cites": cite_keys(p.get("cites")),
                    "steps": [str(s) for s in (p.get("steps") or []) if s], "caption": str(p.get("caption") or ""),
                    "note": str(p.get("note") or ""), "list": str(p.get("list") or ""),
                    "match": [m] if isinstance(m, str) else [str(x) for x in m]})
    return out


def compose_caption(caption: str, cites, parts=(), shown=None, lang: str = "de", lead: str | None = None):
    """Caption and citations of a figure from what it shows. Returns (caption, cite keys).

    ``caption`` is the sentence about what is always shown; ``{parts}`` in it marks where the inline fragments of the
    shown parts go (" mit A, B und C"; without the mark they go before the final full stop). ``lead`` is the word
    before the list ("mit"/"with" by language; "" for fragments with their own preposition; one starting with a comma
    is set without a space before it, ", with"). A part's ``note`` is a
    sentence added after the caption. A part's citations follow its fragment (or its note); a part with neither adds
    them to the end of the caption, with the figure's own ``cites``. ``shown``: {part id: bool}, missing = shown."""
    shown = shown or {}
    vis = [p for p in parts if shown.get(p["id"], True)]
    frags, notes, tail, lists = [], [], list(cite_keys(cites)), {}
    for p in vis:
        if p.get("caption"):
            frags.append(p["caption"] + ("" if p.get("note") else cite(p["cites"])))
        if p.get("note") and p.get("list"):     # parts with the same ``list`` share one sentence: "<list> A, B und C."
            if p["list"] not in lists:
                lists[p["list"]] = []
                notes.append(lists[p["list"]])
            lists[p["list"]].append(p["note"] + cite(p["cites"]))
        elif p.get("note"):
            notes.append(cite_caption(p["note"], p["cites"]))
        if not p.get("caption") and not p.get("note"):
            tail += p["cites"]
    for head, items in lists.items():
        notes[next(i for i, x in enumerate(notes) if x is items)] = f"{head} {join_list(items, lang)}."
    lead = lead if lead is not None else ("mit" if lang == "de" else "with")
    pre = lead if lead[:1] in ",;:" else (" " + lead if lead else "")
    ins = (pre + " " + join_list(frags, lang)) if frags else ""
    text = caption.rstrip()
    if "{parts}" in text:
        text = text.replace("{parts}", ins)
    elif ins:
        text = (text[:-1] + ins + ".") if text.endswith(".") else text + ins
    text = cite_caption(text, tail)
    if notes:
        text = text.rstrip() + " " + " ".join(n.strip() for n in notes)
    keys = cite_keys(cites, *[p["cites"] for p in vis])
    return text, keys


def booktabs(header: list[str], rows: list[list[str]], align: str | None = None, small: bool = False,
             escape_header: bool = True) -> str:
    """A complete tabular with booktabs rules. Cells are taken as LaTeX source (escape them yourself)."""
    n = len(header)
    align = align or ("l" + "r" * (n - 1))
    head = " & ".join(tex_escape(h) if escape_header else h for h in header)
    lines = [r"\small" if small else "", rf"\begin{{tabular}}{{{align}}}", r"\toprule", head + r" \\", r"\midrule"]
    lines += [" & ".join(str(c) for c in row) + r" \\" for row in rows]
    lines += [r"\bottomrule", r"\end{tabular}"]
    return "\n".join(x for x in lines if x) + "\n"


def bib_entry(key: str, entry_type: str = "misc", **fields) -> str:
    body = ",\n".join(f"  {k} = {{{v}}}" for k, v in fields.items() if v not in (None, ""))
    return f"@{entry_type}{{{key},\n{body}\n}}\n"


_MODULES: dict | None = None


def module_info(module: str) -> dict:
    """module.json of a module (name, name_en, version) from the modules/ folder next to the SDK; {} if not found."""
    global _MODULES
    if _MODULES is None:
        import json as _json
        from pathlib import Path
        _MODULES = {}
        for p in (Path(__file__).resolve().parents[2] / "modules").glob("*/module.json"):
            try:
                d = _json.loads(p.read_text(encoding="utf-8"))
                _MODULES[str(d.get("id") or p.parent.name)] = d
            except (OSError, ValueError):
                pass
    return _MODULES.get(module, {})


# a sentence that names the standard the evaluation follows (ISO 6892-1, ASTM E1131, DIN EN …, or a cite key like it)
_STD_RE = re.compile(r"\b(ISO|ASTM|DIN|EN|IEC|VDI|ICTAC|JIS)[\s~]?[A-Z]?[\s~]?\d"
                     r"|\\cite[a-z]*\{[^}]*\b(?i:iso|astm|din|en|iec|vdi|ictac|jis)[-\d]")
_SOFT_RE = re.compile(r"Folio[\s~]*Lab")
SHORT_MAX = 3


def short_steps(steps: list) -> set:
    """Ids of the Short methods text (at most SHORT_MAX sentences): what was measured (the first sentence), the
    standard the evaluation follows (the first later sentence naming or citing one) and the software with its version
    and citation. A module that marks steps as short itself keeps its choice (cut to SHORT_MAX)."""
    plain = [s for s in steps if not s.get("eq")]
    own = [s["id"] for s in plain if s.get("own_short")]
    if own:
        return set(own[:SHORT_MAX])
    pick = []
    if plain:
        pick.append(plain[0]["id"])
    std = next((s for s in plain[1:] if _STD_RE.search(s["text"]) and not _SOFT_RE.search(s["text"])), None)
    if std:
        pick.append(std["id"])
    soft = next((s for s in plain if _SOFT_RE.search(s["text"])), None)
    if soft and soft["id"] not in pick:
        pick.append(soft["id"])
    return set(pick[:SHORT_MAX])


def _step_title(tex: str, words: int = 7) -> str:
    """Readable title of a methods step: its first words without LaTeX."""
    s = re.sub(r"~?\\cite[a-z]*\{[^}]*\}", "", tex)
    s = re.sub(r"\\labval\{[^}]*\}\{([^}]*)\}", r"\1", s)
    s = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?\{([^{}]*)\}", r"\2", s)
    s = re.sub(r"\\[a-zA-Z]+", "", s)
    s = re.sub(r"[{}$^_\\]", "", s).replace("~", " ")
    w = s.split()
    return " ".join(w[:words]) + (" …" if len(w) > words else "")


_ABBR = {"z", "b", "bzw", "ca", "nr", "abb", "tab", "fig", "figs", "eq", "eqs", "gl", "vgl", "e", "g", "i", "al", "u", "a",
         "approx", "resp", "max", "min", "s", "sog", "ggf", "inkl", "evtl", "usw", "etc", "vs", "cf", "no", "bspw", "d", "h",
         "mind", "rel", "std", "St", "Kap", "kap", "sec", "ref", "refs", "vol", "pp", "ed", "eds", "dr", "prof"}


def split_sentences(par: str) -> list[str]:
    """A LaTeX paragraph cut into sentences: at . ! ? followed by space and a capital, $ or \\, never inside math or
    braces and not after common abbreviations (z. B., e.g., Fig., Abb., …) or a single letter."""
    out, start, depth, math = [], 0, 0, False
    i, n = 0, len(par)
    while i < n:
        c = par[i]
        if c == "\\" and i + 1 < n:
            i += 2
            continue
        if c == "$":
            math = not math
        elif c == "{":
            depth += 1
        elif c == "}":
            depth = max(0, depth - 1)
        elif c in ".!?" and not math and depth == 0:
            j = i + 1
            while j < n and par[j] in ")'\"":
                j += 1
            if j < n and par[j] in " \t\n":
                k = j
                while k < n and par[k] in " \t\n":
                    k += 1
                if k < n and (par[k].isupper() or par[k] in "$\\"):
                    w = re.search(r"([A-Za-zÄÖÜäöüß]+)$", par[start:i])
                    word = w.group(1) if w else ""
                    if word.lower() not in _ABBR and word not in _ABBR and not (len(word) == 1 and c == "."):
                        out.append(par[start:j].strip())
                        start = k
                        i = k
                        continue
        i += 1
    if par[start:].strip():
        out.append(par[start:].strip())
    return out


def compose_methods(steps: list[dict], texts: dict[str, str], chosen) -> str:
    """Running text of the chosen methods steps (ids, in step order): same paragraph joined by a space, otherwise
    by a blank line. texts: step id -> LaTeX."""
    want = set(chosen)
    parts, last = [], None
    for st in steps:
        if st["id"] not in want:
            continue
        t = texts.get(st["id"], "").strip()
        if not t:
            continue
        if parts:
            parts.append(" " if st.get("par") == last else "\n\n")
        parts.append(t)
        last = st.get("par")
    return "".join(parts) + "\n" if parts else ""


_STEP_TAG = re.compile("\x01([^\x02]*)\x02")


def step_tag(name: str = "") -> str:
    """Mark in a methods text given as a plain string: the sentences from here on belong to the evaluation step
    ``name`` ("" = to none), until the next mark. add_methods removes the marks, so the text, its sentence ids (s1, s2,
    ...) and thus picks and edits saved in a report stay as they were. Pieces name the step (add_figure steps/parts)."""
    return f"\x01{name}\x02"


def _untag(text: str) -> tuple[str, list]:
    """Text without step marks, and the marks as [(offset in the clean text, name)]."""
    out, marks, pos = [], [], 0
    for m in _STEP_TAG.finditer(text):
        out.append(text[pos:m.start()])
        marks.append((sum(len(x) for x in out), m.group(1)))
        pos = m.end()
    out.append(text[pos:])
    return "".join(out), marks

def _mark_matches(fig, parts, labstyle):
    """Mark the artists of parts declared with ``match`` (globs over labstyle element keys, e.g. "*.line:Hüllkurve*")
    that the module did not mark itself."""
    import fnmatch
    want = [(p["id"], p["match"]) for p in parts if p.get("match")]
    if not want:
        return
    for el in labstyle.inventory(fig):
        if el.get("part"):
            continue
        for pid, globs in want:
            if any(fnmatch.fnmatchcase(el["key"], g) for g in globs):
                labstyle.mark(el["artists"], pid)
                break


def _declare(it: dict, steps, parts) -> dict:
    """Mark a piece as declared (what it shows and needs is known): needs.steps and its parts (without the caption
    templates, which stay in the module)."""
    if steps is None and parts is None:
        return it
    it["needs"] = {"steps": [str(s) for s in (steps or []) if s]}
    if parts:
        it["parts"] = [{"id": p["id"], "label": p["label"], "cites": p["cites"], "steps": p["steps"]} for p in parts]
    return it


# ----------------------------------------------------------------------------- bundle
class Bundle:
    def __init__(self, module: str, module_name: str, title: str, lang: str = "de", slug: str | None = None,
                 summary: str = ""):
        self.module, self.module_name, self.title, self.lang = module, module_name, title, lang
        self.slug = slug or slugify(title)
        self.summary = summary
        self.items: list[dict] = []
        self.files: dict[str, bytes] = {}
        self.bib: list[str] = []
        self.values: list[dict] = []
        self.source: dict = {}
        self.styles: dict = {}          # figure id -> style spec (labstyle); also taken from source.request.styles
        self._figs: dict = {}           # figure id -> (Figure, dpi), kept for a styled redraw in to_dict
        self._pending: set = set()      # figure ids whose files to_dict still has to write
        self._lazy: dict = {}           # figure id -> function that draws it (add_figure with a function)
        self._capdef: dict = {}         # figure id -> caption, cites and parts, to set them again for what is shown

    # ---- pieces
    def add_figure(self, fig, id: str, caption: str, width: str = "0.9", dpi: int = 130, close: bool = True,
                   cites=None, parts=None, steps=None, parts_lead: str | None = None):
        """Matplotlib figure -> vector PDF (used by LaTeX) plus PNG preview (shown in the editor).

        The files are written in to_dict (CS-01): a preview for the editing window (source.request.preview) then
        draws only the figure being edited, without PDFs. A figure is drawn as it is when to_dict runs, so a module
        must not change it after adding it (pass close=False and keep drawing only on a new figure).
        fig may also be a function without arguments that returns the figure: it is called only when the figure is
        written, so a preview of another figure skips drawing it.
        cites: citation keys of what the figure always shows (added to the caption, see cite_caption).

        Report pieces cite and describe only what they show (see docs/MODULES.md, "Parts"):
        steps: ids of the methods steps (add_methods) the figure always needs, e.g. the evaluation it plots.
        parts: what can be switched off, each {id, label, cites, steps, caption, note, match}: the artists are marked
        with labstyle.mark(artists, id) (or found by ``match``, globs over labstyle element keys); ``caption`` is an
        inline fragment ("die Hüllkurve") set where ``{parts}`` stands in the caption (or before its full stop) after
        ``parts_lead`` ("mit"/"with"), ``note`` a sentence after the caption. A part hidden in a style spec (Customise,
        or "parts": {id: {"hidden": true}}) drops its fragment, note, citations and steps.
        Passing steps or parts (even []) declares the figure: the hub then knows which methods steps it needs."""
        cites = cite_keys(cites)
        declared_parts = parts is not None          # no parts given: the figure stays undeclared
        parts = clean_parts(parts)
        self._capdef[id] = {"caption": caption, "cites": cites, "parts": parts, "lead": parts_lead}
        caption, all_cites = compose_caption(caption, cites, parts, None, self.lang, parts_lead)
        import matplotlib
        matplotlib.rcParams["pdf.fonttype"] = 42
        if callable(fig) and not hasattr(fig, "savefig"):
            if close:
                self._lazy[id] = fig        # drawn in to_dict, and only when written
                fig = None
            else:
                fig = fig()
        if fig is None:
            self._pending.add(id)
        elif not close:
            # the module may keep drawing on this figure: write it now, as it is
            pdf, png = io.BytesIO(), io.BytesIO()
            fig.savefig(pdf, format="pdf", bbox_inches="tight")
            fig.savefig(png, format="png", dpi=dpi, bbox_inches="tight")
            self.files[f"fig/{id}.pdf"] = pdf.getvalue()
            self.files[f"fig/{id}.png"] = png.getvalue()
        else:
            import matplotlib.pyplot as plt
            plt.close(fig)                  # leaves pyplot; the object can still be saved
            self._pending.add(id)
        self._figs[id] = (fig, dpi)
        it = {"kind": "figure", "id": id, "file": f"fig/{id}.pdf", "preview": f"fig/{id}.png",
              "caption": caption, "label": f"fig:{self.slug}-{id}", "width": width, "cites": all_cites}
        self.items.append(_declare(it, steps, parts if declared_parts else None))

    def add_table(self, id: str, tabular: str, caption: str, notes: str = "", cites=None, steps=None):
        """A LaTeX tabular with its caption. cites: sources of the data shown; steps: ids of the methods steps the
        table needs (declares it, see add_figure)."""
        cites = cite_keys(cites)
        self.files[f"{id}.tex"] = tabular.encode("utf-8")
        it = {"kind": "table", "id": id, "file": f"{id}.tex", "caption": cite_caption(caption, cites),
              "label": f"tab:{self.slug}-{id}", "notes": notes, "cites": cites}
        self.items.append(_declare(it, steps, None))

    def add_data_csv(self, id: str, header: list[str], rows, description: str = "", nd: int = 6,
                     labels: dict[str, str] | None = None, plot: dict | None = None):
        """CSV with point decimals and comma separator (what pgfplots and Excel import expect).

        labels: column -> axis label as LaTeX (e.g. {"F_N": r"Force $F$ [N]"}); plot: default {"x": col, "y": col}
        for the editor's "Plot" action, optionally "style": "marks" for a scatter plot instead of a line.
        Non-numeric columns should be last and have no label."""
        buf = io.StringIO()
        buf.write(",".join(header) + "\n")
        for row in rows:
            buf.write(",".join("" if v is None else (f"{v:.{nd}g}" if isinstance(v, float) else str(v)) for v in row) + "\n")
        self.files[f"data/{id}.csv"] = buf.getvalue().encode("utf-8")
        self.items.append({"kind": "data", "id": id, "file": f"data/{id}.csv", "columns": header,
                           "labels": labels or {}, "plot": plot or {},
                           "description": description, "rows": sum(1 for _ in buf.getvalue().splitlines()) - 1})

    def add_values(self, values, needs: dict | None = None):
        """values: iterable of (key, label, latex_text, plain_text). Usable as \\labval{slug}{key}.
        needs: {key: [methods step ids]}: the steps a single imported value needs (its evaluation)."""
        needs = needs or {}
        for key, label, latex, plain in values:
            if not re.fullmatch(r"[A-Za-z0-9-]+", key):
                raise ValueError(f"value key must be alphanumeric/hyphen: {key!r}")
            v = {"key": key, "label": label, "latex": latex, "text": plain}
            if needs.get(key):
                v["needs"] = [str(s) for s in needs[key]]
            self.values.append(v)

    def add_citation(self, key: str, entry_type: str = "misc", **fields):
        if any(key == c["key"] for c in self.items if c["kind"] == "citation"):
            return
        entry = bib_entry(key, entry_type, **fields)
        self.bib.append(entry)
        self.items.append({"kind": "citation", "key": key, "title": fields.get("title", key)})

    def add_text(self, id: str, latex: str, title: str, steps=None):
        """A text block. steps: ids of the methods steps it needs (declares it; an undeclared text counts as needing
        every step)."""
        self.files[f"text-{id}.tex"] = latex.encode("utf-8")
        self.items.append(_declare({"kind": "text", "id": id, "file": f"text-{id}.tex", "title": title}, steps, None))

    def _software(self):
        info = module_info(self.module)
        en = self.lang == "en"
        name = (info.get("name_en") if en else None) or info.get("name") or self.module_name
        ver = info.get("version")
        key = f"folio-lab-{slugify(self.module, 30)}"
        self.add_citation(key, "misc", author="{Folio Lab}", title=f"Folio Lab: {name}", version=ver,
                          note="analysis module" if en else "Analysemodul")
        return name, ver, key

    def software_clause(self) -> str:
        """"ausgewertet mit Folio Lab, Modul Zugversuch, Version 1.4.1~\\cite{folio-lab-zugversuch}" (lower case, no
        full stop), for the one-sentence methods text of a reduced piece (add_methods brief=)."""
        name, ver, key = self._software()
        if self.lang == "en":
            return f"evaluated with Folio Lab, {name} module{f', version {ver}' if ver else ''}~\\cite{{{key}}}"
        return f"ausgewertet mit Folio Lab, Modul {name}{f', Version {ver}' if ver else ''}~\\cite{{{key}}}"

    def brief_from(self, text: str, evaluated: bool = False) -> str:
        """The one-sentence methods text of a reduced piece: the first sentence of ``text`` plus the software clause.
        evaluated: that sentence already says it was evaluated ("... wurde ausgewertet"), so only "mit Folio Lab ..."
        is added."""
        first = split_sentences(_untag(text)[0].strip())[0].strip().rstrip(".")
        clause = self.software_clause()
        return first + (" " + clause.split(" ", 1)[1] if evaluated else "; " + clause) + "."

    def added_mark(self) -> tuple:
        """Where the piece lists stand now, for needs_since."""
        return len(self.items), len(self.values)

    def needs_since(self, mark: tuple, steps) -> None:
        """Declare the tables and values added since ``mark`` (by a helper that knows nothing of methods steps) as
        needing ``steps``, e.g. the budget tables and +/- values of an uncertainty report."""
        steps = [str(s) for s in steps]
        for v in self.values[mark[1]:]:
            v.setdefault("needs", list(steps))
        for it in self.items[mark[0]:]:
            if it.get("kind") == "table":
                it.setdefault("needs", {"steps": list(steps)})

    def software_sentence(self) -> str:
        """"Ausgewertet wurde mit Folio Lab, Modul Zugversuch, Version 1.4.1~\\cite{folio-lab-zugversuch}." plus its
        citation (version from the module's module.json)."""
        name, ver, key = self._software()
        if self.lang == "en":
            return f"The analysis used Folio Lab, {name} module{f', version {ver}' if ver else ''}~\\cite{{{key}}}."
        return f"Ausgewertet wurde mit Folio Lab, Modul {name}{f', Version {ver}' if ver else ''}~\\cite{{{key}}}."

    def add_methods(self, steps, title: str, id: str = "methodik", sep: str = "\n\n", eq: str = "",
                    eq_title: str | None = None, tail: str = "\n", software: bool = True, brief: str = ""):
        """Methods text as steps the report can pick from (import: tick steps, Short/Full).

        steps: the pieces the module joined with ``sep`` so far: plain LaTeX strings or dicts {id, title, text, short}.
        text-<id>.tex is written exactly as before (pieces joined with sep, then the equations block ``eq``). For
        picking, every string is cut into paragraphs and sentences (each a step titled by its first words); a dict is
        one step (``short: True`` marks the module's own choice for Short). Steps carry their paragraph number ``par`` so a
        selection can be set again as running text (same paragraph: space, else blank line). The equations are a step
        of their own (not short). Also writes methods.json and methods/<step>.tex; the text item lists the steps.

        Short (see short_steps) is at most three sentences: the measurement, the standard and the software; unless
        the text names Folio Lab already, a software sentence with version and citation is added (software=False
        leaves it out).

        brief: one sentence (measurement, standard, machine or software, e.g. ending in ``software_clause()``) that
        stands alone when the imported pieces show no evaluation: a step of its own (``brief``), never part of the full
        text. A step given as a dict with an ``id`` keeps that id, so figures, tables and values can name it as a step
        they need (add_figure steps/parts, add_values needs); a dict with ``of`` instead keeps its running id (s1, s2,
        ..., so picks and sentence edits saved in a report stay valid) and belongs to the step named by ``of``. The hub
        leaves out steps that only serve pieces or parts not shown."""
        steps = [s for s in steps if s]
        if software and not any(_SOFT_RE.search(s if isinstance(s, str) else str(s.get("text") or "")) for s in steps):
            steps.append({"id": "software", "title": "Software", "text": self.software_sentence()})
        texts = [_untag(s)[0] if isinstance(s, str) else str(s.get("text") or "") for s in steps if s]
        full = sep.join(texts)
        if eq:
            full = full.rstrip("\n") + "\n\n" + eq.strip()
        self.files[f"text-{id}.tex"] = (full.rstrip("\n") + tail).encode("utf-8")
        same_par = "\n" not in sep
        out, seen, par = [], set(), -1
        for k, s in enumerate(s for s in steps if s):
            clean, marks = _untag(s) if isinstance(s, str) else (str(s.get("text") or ""), [])
            d = {"text": clean} if isinstance(s, str) else dict(s)
            pars = [p for p in re.split(r"\n[ \t]*\n", clean) if p.strip()]
            at = 0                              # where in the clean text the current sentence starts (for step marks)
            for j, ptxt in enumerate(pars):
                if not (same_par and k > 0 and j == 0) or par < 0:
                    par += 1
                pieces = split_sentences(ptxt) if isinstance(s, str) else [ptxt.strip()]
                for txt in pieces:
                    sid = slugify(d.get("id") or f"s{len(out) + 1}", 30) if not isinstance(s, str) else f"s{len(out) + 1}"
                    while sid in seen:
                        sid += "-x"
                    seen.add(sid)
                    own = bool(d.get("short")) if not isinstance(s, str) else False
                    out.append({"id": sid, "title": str((d.get("title") if not isinstance(s, str) else None) or _step_title(txt)),
                                "own_short": own, "text": txt, "par": par})
                    if isinstance(s, str):
                        hit = clean.find(txt, at)
                        at = hit if hit >= 0 else at
                        tag = next((n for o, n in reversed(marks) if o <= at), "")
                        at += len(txt)
                        base = slugify(tag, 30) if tag else ""
                    else:
                        base = slugify(d.get("of") or d.get("id") or "", 30)
                    if base and sid != base:
                        out[-1]["of"] = base    # the named step this sentence belongs to; it goes with that step
        short = short_steps(out)
        for st in out:
            st["short"] = st["id"] in short
        if eq:
            out.append({"id": "gleichungen", "title": eq_title or ("Gleichungen" if self.lang == "de" else "Equations"),
                        "short": False, "text": eq.strip(), "eq": True, "par": par + 1})
        if brief:
            bid = "kurz"
            while bid in seen:
                bid += "-x"
            out.insert(0, {"id": bid, "title": "Ein Satz" if self.lang == "de" else "One sentence", "short": False,
                           "text": str(brief).strip(), "brief": True, "par": -1})
        meta = []
        for st in out:
            f = f"methods/{st['id']}.tex"
            self.files[f] = (st["text"] + "\n").encode("utf-8")
            meta.append({"id": st["id"], "title": st["title"], "short": st["short"], "par": st["par"], "file": f,
                         **({"eq": True} if st.get("eq") else {}), **({"brief": True} if st.get("brief") else {}),
                         **({"of": st["of"]} if st.get("of") else {})})
        import json as _json
        self.files["methods.json"] = _json.dumps({"id": id, "title": title, "steps": meta},
                                                 ensure_ascii=False, indent=1).encode("utf-8")
        self.items.append({"kind": "text", "id": id, "file": f"text-{id}.tex", "title": title, "methods": True,
                           "steps": meta})
    def _show_parts(self, it: dict, cdef: dict, shown: dict):
        """Set caption, citations and the parts' shown flags of a figure item for what is still visible."""
        for p in it.get("parts") or []:
            if shown.get(p["id"], True):
                p.pop("shown", None)
            else:
                p["shown"] = False
        cap, keys = compose_caption(cdef["caption"], cdef["cites"], cdef["parts"], shown, self.lang, cdef.get("lead"))
        if cap != it["caption"]:
            it.setdefault("caption_full", it["caption"])
        it["caption"], it["cites"] = cap, keys

    def set_source(self, request: dict, files: dict[str, bytes]):
        """What the module needs to rebuild this bundle later (Refresh in the editor)."""
        self.source = {"request": request, "files": {k: base64.b64encode(v).decode("ascii") for k, v in files.items()}}

    # ---- output
    def _render(self):
        """Write the figure files (at to_dict). Redraw the figures named in the style specs (self.styles
        or source.request.styles) and, with source.request.describe_figures, describe every figure for the editing
        window. With source.request.preview = {item, svg?} only that figure is drawn, as PNG (and SVG with element
        ids, see labstyle.tag), no PDF: the editing window's preview, which is never stored."""
        req = (self.source or {}).get("request") or {}
        styles = {**(req.get("styles") if isinstance(req.get("styles"), dict) else {}), **self.styles}
        want_desc = bool(req.get("describe_figures"))
        pv = req.get("preview") if isinstance(req.get("preview"), dict) else None
        import labstyle
        for it in self.items:
            fid = it.get("id")
            if it.get("kind") != "figure" or fid not in self._figs:
                continue
            if pv and fid != pv.get("item"):
                continue                    # a preview draws the edited figure only
            fig, dpi = self._figs[fid]
            if fig is None:
                import matplotlib.pyplot as plt
                fig = self._lazy.pop(fid)()
                plt.close(fig)
            spec = styles.get(fid)
            if not (spec or want_desc or pv):
                if fid in self._pending:    # as the module drew it
                    pdf, png = io.BytesIO(), io.BytesIO()
                    fig.savefig(pdf, format="pdf", bbox_inches="tight")
                    fig.savefig(png, format="png", dpi=dpi, bbox_inches="tight")
                    self.files[it["file"]] = pdf.getvalue()
                    self.files[it["preview"]] = png.getvalue()
                continue
            cdef = self._capdef.get(fid) or {}
            if cdef.get("parts"):
                _mark_matches(fig, cdef["parts"], labstyle)
            if want_desc:
                it["describe"] = labstyle.describe(fig)
            gids = labstyle.tag(fig) if pv and pv.get("svg") else None
            used = labstyle.apply(fig, spec or {})
            if cdef.get("parts"):
                self._show_parts(it, cdef, labstyle.shown_parts(fig, [p["id"] for p in cdef["parts"]], spec=used))
            # one region for PDF and PNG: the tight box, cut by the crop
            bb = labstyle.frame(fig, used.get("crop"))
            if not (pv and gids is not None):
                png = io.BytesIO()
                fig.savefig(png, format="png", dpi=dpi, bbox_inches=bb)
                self.files[it["preview"]] = png.getvalue()
            if pv:
                if gids is not None:
                    import matplotlib
                    svg = io.BytesIO()
                    with matplotlib.rc_context({"svg.fonttype": "none"}):   # texts stay text: edits show at once
                        fig.savefig(svg, format="svg", bbox_inches=bb)
                    self.files[f"fig/{fid}.svg"] = svg.getvalue()
            else:
                pdf = io.BytesIO()
                fig.savefig(pdf, format="pdf", bbox_inches=bb)
                self.files[it["file"]] = pdf.getvalue()
            if spec:
                it["style"] = used
            if want_desc:
                # describe is the figure as the module draws it (element keys are those of a spec); add the state
                # now: size, and per axes where it sits in the image with its limits (drag a box to zoom)
                w, h = fig.get_size_inches()
                it["describe"]["now"] = {"width_mm": round(float(w) * 25.4, 1), "aspect": round(float(h / w), 3) if w else 0.7,
                                         "axes": labstyle.boxes(fig, bb), "notes": used.get("notes") or []}
                if gids is not None:
                    it["describe"]["now"]["gids"] = gids
        self._pending.clear()
        self._lazy.clear()
    def to_dict(self) -> dict:
        self._render()
        self._figs = {}
        files = dict(self.files)
        if self.values:
            lines = [f"% Values of '{self.title}' ({self.module_name}). Generated by Folio Lab; do not edit.",
                     f"% Use as \\labval{{{self.slug}}}{{<key>}}."]
            for v in self.values:
                lines.append(f"\\labset{{{self.slug}}}{{{v['key']}}}{{{v['latex']}}}% {v['label']}")
            files["values.tex"] = ("\n".join(lines) + "\n").encode("utf-8")
            self.items.append({"kind": "values", "file": "values.tex", "values": self.values})
        if self.bib:
            files["refs.bib"] = "\n".join(self.bib).encode("utf-8")
        return {
            "format": FORMAT, "module": self.module, "module_name": self.module_name, "title": self.title,
            "slug": self.slug, "lang": self.lang, "summary": self.summary,
            "created": datetime.now().isoformat(timespec="seconds"),
            "items": self.items,
            "files": {k: base64.b64encode(v).decode("ascii") for k, v in files.items()},
            "source": self.source,
        }
