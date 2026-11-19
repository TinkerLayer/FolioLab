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


def tex_escape(s) -> str:
    """Plain text -> LaTeX text-mode source (special characters and Greek letters handled)."""
    out = []
    for ch in _runs(str(s)):
        if ch == "\x02":
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

    # ---- pieces
    def add_figure(self, fig, id: str, caption: str, width: str = "0.9", dpi: int = 130, close: bool = True,
                   cites=None):
        """Matplotlib figure -> vector PDF (used by LaTeX) plus PNG preview (shown in the editor).

        cites: citation keys of the data shown (added to the caption, see cite_caption)."""
        cites = cite_keys(cites)
        caption = cite_caption(caption, cites)
        import matplotlib
        matplotlib.rcParams["pdf.fonttype"] = 42
        pdf, png = io.BytesIO(), io.BytesIO()
        fig.savefig(pdf, format="pdf", bbox_inches="tight")
        fig.savefig(png, format="png", dpi=dpi, bbox_inches="tight")
        if close:
            import matplotlib.pyplot as plt
            plt.close(fig)
        self.files[f"fig/{id}.pdf"] = pdf.getvalue()
        self.files[f"fig/{id}.png"] = png.getvalue()
        self.items.append({"kind": "figure", "id": id, "file": f"fig/{id}.pdf", "preview": f"fig/{id}.png",
                           "caption": caption, "label": f"fig:{self.slug}-{id}", "width": width, "cites": cites})

    def add_table(self, id: str, tabular: str, caption: str, notes: str = "", cites=None):
        cites = cite_keys(cites)
        self.files[f"{id}.tex"] = tabular.encode("utf-8")
        self.items.append({"kind": "table", "id": id, "file": f"{id}.tex", "caption": cite_caption(caption, cites),
                           "label": f"tab:{self.slug}-{id}", "notes": notes, "cites": cites})

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

    def add_values(self, values):
        """values: iterable of (key, label, latex_text, plain_text). Usable as \\labval{slug}{key}."""
        for key, label, latex, plain in values:
            if not re.fullmatch(r"[A-Za-z0-9-]+", key):
                raise ValueError(f"value key must be alphanumeric/hyphen: {key!r}")
            self.values.append({"key": key, "label": label, "latex": latex, "text": plain})

    def add_citation(self, key: str, entry_type: str = "misc", **fields):
        if any(key == c["key"] for c in self.items if c["kind"] == "citation"):
            return
        entry = bib_entry(key, entry_type, **fields)
        self.bib.append(entry)
        self.items.append({"kind": "citation", "key": key, "title": fields.get("title", key)})

    def add_text(self, id: str, latex: str, title: str):
        self.files[f"text-{id}.tex"] = latex.encode("utf-8")
        self.items.append({"kind": "text", "id": id, "file": f"text-{id}.tex", "title": title})

    def set_source(self, request: dict, files: dict[str, bytes]):
        """What the module needs to rebuild this bundle later (Refresh in the editor)."""
        self.source = {"request": request, "files": {k: base64.b64encode(v).decode("ascii") for k, v in files.items()}}

    # ---- output
    def to_dict(self) -> dict:
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
