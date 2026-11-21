"""Figure styles for report figures.

A *style spec* changes how a module's matplotlib figure looks without touching the module: the figure is drawn as
usual, then ``apply(fig, spec)`` adjusts size, fonts, colours, line widths, legend, axis labels, ranges, ticks, title
and grid, and can hide series. ``labbundle.Bundle`` applies the spec of a figure id when the bundle's request carries
``styles: {figure id: spec}`` (the hub sends it for a styled fork of a figure, see docs/MODULES.md).

Spec (every key optional)::

    {"preset": "elsevier-1",           # journal preset, its values are defaults for the keys below
     "width_mm": 90, "aspect": 0.7,    # figure width and height/width
     "font": "serif" | "sans", "font_size": 8,
     "line_width": 1.0,                # all data lines (series may override)
     "palette": ["#1b6ca8", ...],      # colours in series order
     "series": {"<legend label>": {"color": "#c00", "lw": 1.5, "ls": "--", "hidden": true, "label": "new name"}},
     "legend": {"show": true, "loc": "best", "frame": false},
     "title": "…" | "",                # "" removes the title
     "axes": [{"xlabel": "…", "ylabel": "…", "xlim": [0, 10], "ylim": [null, 5], "xscale": "log",
               "grid": true, "xticks": 5, "yticks": 4}],  # per axes, in order; one entry for a single plot
     "elements": {"<key>": {"hidden": true, "color": "#c00", "lw": 1, "ls": "--", "alpha": 0.5,
                            "size": 6, "bold": true, "text": "…", "label": "…"}},   # any drawn element, keys from describe()
     "colors": {"background": "#fff", "plot": "#fafafa", "axes": "#333", "ticks": "#333", "grid": "#ddd",
                "text": "#111"},
     "crop": [0.0, 0.05, 0.1, 0.0],    # cut off left, top, right, bottom (share of the figure; labbundle saves it)
     "groups": {"annotations": {"color": "#333", "size": 7, "bold": false, "hidden": false},
                "lines": {"lw": 1.2, "ls": "--", "alpha": 0.8, "color": "#000"}, ...},
     "parts": {"envelope": {"hidden": true}}}   # parts the module declared (labbundle add_figure parts=)

Groups (``GROUPS``) edit every element of a kind at once: ``axis_labels``, ``tick_labels``, ``series_names`` (legend
entries), ``annotations`` (texts and value labels in the plot), ``lines``, ``markers`` and ``areas`` (bands, bars,
shapes). An entry in ``elements`` overrides its group for that one element (``"hidden": false`` shows it although its
group is hidden).

Parts are what a figure shows in the module's own terms (the envelope, a reference curve, the field of a group, the
markers of an evaluation): the module marks the artists of a part with ``mark(artists, "envelope")`` (or labbundle
matches them by key) and declares the part with its citations, methods steps and caption fragment. ``"parts"`` hides a
whole part; it sits between groups and elements (an element's own entry still wins). ``shown_parts`` tells which parts
are still visible after ``apply``, so the caption, citations and methods text can follow what is shown.

``font`` is "serif", "sans", "cm" (Computer Modern, as LaTeX) or the name of any installed font (``font_names()``); a
font that is missing where the module runs falls back to DejaVu Sans with a note.

Element keys (``describe()["elements"]``) are per axes ``<i>.<kind><n>`` for unnamed elements in drawing order
(``0.line2``, ``1.text0``, ``0.patch1``, ``0.bars0``) and ``<i>.<kind>:<legend label>`` for named ones, with the
numbers of the label replaced by ``#`` (``0.line:Maximum: #,# N``) and ``~1``, ``~2`` for repeated labels; ``f.text<n>``
for figure texts. Named keys survive a refresh with other data; numbered ones count in drawing order, so a module that
draws a different number of helper lines on new data shifts them.

Values are checked and clipped; unknown keys are ignored, so a spec from a newer version does not break an older
module."""
from __future__ import annotations

import re

# Journal presets: column widths and font sizes from the author guidelines (rounded; check the current guide of the
# journal before submission).
PRESETS = {
    "standard": {"label": "Standard (module)", "label_en": "Standard (module)"},
    "elsevier-1": {"label": "Elsevier, 1 Spalte (90 mm)", "label_en": "Elsevier, single column (90 mm)",
                   "width_mm": 90, "font": "sans", "font_size": 7, "line_width": 1.0},
    "elsevier-2": {"label": "Elsevier, 2 Spalten (190 mm)", "label_en": "Elsevier, double column (190 mm)",
                   "width_mm": 190, "font": "sans", "font_size": 8, "line_width": 1.0},
    "springer-1": {"label": "Springer, 1 Spalte (84 mm)", "label_en": "Springer, single column (84 mm)",
                   "width_mm": 84, "font": "sans", "font_size": 8, "line_width": 1.0},
    "springer-2": {"label": "Springer, 2 Spalten (174 mm)", "label_en": "Springer, double column (174 mm)",
                   "width_mm": 174, "font": "sans", "font_size": 8, "line_width": 1.0},
    "ieee-1": {"label": "IEEE, 1 Spalte (88 mm)", "label_en": "IEEE, single column (88 mm)",
               "width_mm": 88.9, "font": "serif", "font_size": 8, "line_width": 1.0},
    "ieee-2": {"label": "IEEE, 2 Spalten (181 mm)", "label_en": "IEEE, double column (181 mm)",
               "width_mm": 181, "font": "serif", "font_size": 8, "line_width": 1.0},
    "acs-1": {"label": "ACS, 1 Spalte (82,5 mm)", "label_en": "ACS, single column (82.5 mm)",
              "width_mm": 82.5, "font": "sans", "font_size": 7, "line_width": 1.0},
    "nature-1": {"label": "Nature, 1 Spalte (89 mm)", "label_en": "Nature, single column (89 mm)",
                 "width_mm": 89, "font": "sans", "font_size": 7, "line_width": 0.8},
    "nature-2": {"label": "Nature, 2 Spalten (183 mm)", "label_en": "Nature, double column (183 mm)",
                 "width_mm": 183, "font": "sans", "font_size": 7, "line_width": 0.8},
    "thesis": {"label": "Abschlussarbeit (150 mm, 10 pt)", "label_en": "Thesis (150 mm, 10 pt)",
               "width_mm": 150, "font": "serif", "font_size": 10, "line_width": 1.2},
    "slides": {"label": "Folien (gross)", "label_en": "Slides (large)", "width_mm": 240, "aspect": 0.56,
               "font": "sans", "font_size": 14, "line_width": 2.0},
}

# colour-blind safe palettes (Okabe & Ito 2008; Tol 2021 "bright")
PALETTES = {
    "okabe-ito": ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#56B4E9", "#F0E442", "#000000"],
    "tol-bright": ["#4477AA", "#EE6677", "#228833", "#CCBB44", "#66CCEE", "#AA3377", "#BBBBBB"],
    "grey": ["#000000", "#555555", "#888888", "#aaaaaa"],
}

_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$|^#[0-9a-fA-F]{3}$|^[a-z]{3,20}$")
_LS = {"-", "--", ":", "-.", "solid", "dashed", "dotted", "dashdot"}
_LOC = {"best", "upper right", "upper left", "lower left", "lower right", "right", "center left", "center right",
        "lower center", "upper center", "center", "outside"}
_FONT = re.compile(r"^[\w .&'+,()-]{1,80}$")
_KEY = re.compile(r"^(?:\d{1,2}|f)\.[a-z]+(?:\d{1,4}|:.{1,120})$", re.S)
COLOR_KEYS = ("background", "plot", "axes", "ticks", "grid", "text")
PART_ATTR = "_labpart"             # attribute on an artist: the id of the part it belongs to
_PART = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.:-]{0,59}$")
# groups by kind (CS-02) and what each can change
GROUPS = {
    "axis_labels": ("color", "size", "bold", "hidden"),
    "tick_labels": ("color", "size", "hidden"),
    "series_names": ("color", "size", "bold"),
    "annotations": ("color", "size", "bold", "hidden"),
    "lines": ("color", "lw", "ls", "alpha", "hidden"),
    "markers": ("color", "size", "alpha", "hidden"),
    "areas": ("color", "alpha", "hidden"),
}

_FONTS = None


def font_names() -> list:
    """Installed fonts matplotlib can embed in a PDF (TrueType), sorted; "cm" stands for Computer Modern."""
    global _FONTS
    if _FONTS is None:
        try:
            from matplotlib import font_manager as fm
            _FONTS = sorted({f.name for f in fm.fontManager.ttflist if str(f.fname).lower().endswith((".ttf", ".ttc"))},
                            key=str.lower)
        except Exception:
            _FONTS = []
    return _FONTS


def _family(name):
    """Font family list for a spec font, plus a note when it had to fall back."""
    if name == "serif":
        return ["DejaVu Serif", "Times New Roman", "serif"], None
    if name == "sans":
        return ["DejaVu Sans", "Arial", "sans-serif"], None
    if name == "cm":
        return ["cmr10", "DejaVu Serif"], None      # glyphs cmr10 lacks (minus, °) come from DejaVu
    if name in font_names():
        return [name, "DejaVu Sans"], None
    return ["DejaVu Sans"], f"Font “{name}” is not installed where the module runs; DejaVu Sans is used."


def _num(v, lo, hi, default=None):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    if x != x:
        return default
    return min(hi, max(lo, x))


def _txt(v, n=200):
    return None if v is None else str(v)[:n]


def clean(spec) -> dict:
    """A spec reduced to known keys with checked values (what is stored and applied)."""
    if not isinstance(spec, dict):
        return {}
    out = {}
    p = spec.get("preset")
    if isinstance(p, str) and p in PRESETS:
        out["preset"] = p
    for k, lo, hi in (("width_mm", 30, 400), ("aspect", 0.2, 2.5), ("font_size", 4, 30), ("line_width", 0.1, 8)):
        v = _num(spec.get(k), lo, hi)
        if v is not None:
            out[k] = v
    if isinstance(spec.get("font"), str) and _FONT.match(spec["font"]):
        out["font"] = spec["font"]
    pal = spec.get("palette")
    if isinstance(pal, str) and pal in PALETTES:
        out["palette"] = pal
    elif isinstance(pal, list):
        cols = [c for c in pal[:20] if isinstance(c, str) and _COLOR.match(c)]
        if cols:
            out["palette"] = cols
    ser = spec.get("series")
    if isinstance(ser, dict):
        s2 = {}
        for name, d in list(ser.items())[:60]:
            if not isinstance(d, dict):
                continue
            e = {}
            if isinstance(d.get("color"), str) and _COLOR.match(d["color"]):
                e["color"] = d["color"]
            lw = _num(d.get("lw"), 0.1, 8)
            if lw is not None:
                e["lw"] = lw
            if d.get("ls") in _LS:
                e["ls"] = d["ls"]
            if d.get("hidden"):
                e["hidden"] = True
            if d.get("label") is not None:
                e["label"] = _txt(d["label"], 120)
            if e:
                s2[str(name)[:120]] = e
        if s2:
            out["series"] = s2
    lg = spec.get("legend")
    if isinstance(lg, dict):
        e = {}
        if "show" in lg:
            e["show"] = bool(lg["show"])
        if lg.get("loc") in _LOC:
            e["loc"] = lg["loc"]
        if "frame" in lg:
            e["frame"] = bool(lg["frame"])
        if e:
            out["legend"] = e
    if spec.get("title") is not None:
        out["title"] = _txt(spec["title"], 200)
    axs = spec.get("axes")
    if isinstance(axs, list):
        a2 = []
        for d in axs[:12]:
            e = {}
            if isinstance(d, dict):
                for k in ("xlabel", "ylabel"):
                    if d.get(k) is not None:
                        e[k] = _txt(d[k], 160)
                for k in ("xlim", "ylim"):
                    v = d.get(k)
                    if isinstance(v, list) and len(v) == 2:
                        lim = [_num(v[0], -1e300, 1e300), _num(v[1], -1e300, 1e300)]
                        if any(x is not None for x in lim):
                            e[k] = lim
                for k in ("xscale", "yscale"):
                    if d.get(k) in ("linear", "log"):
                        e[k] = d[k]
                if "grid" in d:
                    e["grid"] = bool(d["grid"])
                for k in ("xticks", "yticks"):
                    v = _num(d.get(k), 2, 20)
                    if v is not None:
                        e[k] = int(v)
            a2.append(e)
        if any(a2):
            out["axes"] = a2
    els = spec.get("elements")
    if isinstance(els, dict):
        e2 = {}
        for key, d in list(els.items())[:400]:
            if not isinstance(d, dict) or not isinstance(key, str) or not _KEY.match(key):
                continue
            e = {}
            if isinstance(d.get("color"), str) and _COLOR.match(d["color"]):
                e["color"] = d["color"]
            for k, lo, hi in (("lw", 0, 8), ("alpha", 0, 1), ("size", 1, 40)):
                v = _num(d.get(k), lo, hi)
                if v is not None:
                    e[k] = v
            if d.get("ls") in _LS:
                e["ls"] = d["ls"]
            if d.get("hidden"):
                e["hidden"] = True
            elif d.get("hidden") is False:
                e["hidden"] = False         # shown although its group is hidden
            if isinstance(d.get("bold"), bool):
                e["bold"] = d["bold"]
            for k, n in (("text", 300), ("label", 120)):
                if d.get(k) is not None:
                    e[k] = _txt(d[k], n)
            if e:
                e2[key] = e
        if e2:
            out["elements"] = e2
    grp = spec.get("groups")
    if isinstance(grp, dict):
        g2 = {}
        for name, props in GROUPS.items():
            d = grp.get(name)
            if not isinstance(d, dict):
                continue
            e = {}
            if "color" in props and isinstance(d.get("color"), str) and _COLOR.match(d["color"]):
                e["color"] = d["color"]
            for k, lo, hi in (("lw", 0, 8), ("alpha", 0, 1), ("size", 1, 40)):
                if k in props:
                    v = _num(d.get(k), lo, hi)
                    if v is not None:
                        e[k] = v
            if "ls" in props and d.get("ls") in _LS:
                e["ls"] = d["ls"]
            if "bold" in props and "bold" in d:
                e["bold"] = bool(d["bold"])
            if "hidden" in props and d.get("hidden"):
                e["hidden"] = True
            if e:
                g2[name] = e
        if g2:
            out["groups"] = g2
    prt = spec.get("parts")
    if isinstance(prt, dict):
        p2 = {str(k): {"hidden": True} for k, d in list(prt.items())[:60]
              if isinstance(d, dict) and d.get("hidden") and _PART.match(str(k))}
        if p2:
            out["parts"] = p2
    cols = spec.get("colors")
    if isinstance(cols, dict):
        c2 = {k: cols[k] for k in COLOR_KEYS if isinstance(cols.get(k), str) and _COLOR.match(cols[k])}
        if c2:
            out["colors"] = c2
    crop = spec.get("crop")
    if isinstance(crop, list) and len(crop) == 4:
        c = [_num(v, 0, 0.45, 0.0) for v in crop]
        if any(c):
            out["crop"] = [round(v, 4) for v in c]
    return out


def resolved(spec) -> dict:
    """Spec with the preset's values as defaults."""
    s = clean(spec)
    base = {k: v for k, v in PRESETS.get(s.get("preset") or "", {}).items() if not k.startswith("label")}
    return {**base, **s}


def _data_artists(ax):
    """Lines and collections of an axes that carry data (with their legend label)."""
    out = []
    for ln in ax.get_lines():
        out.append(ln)
    for c in ax.collections:
        out.append(c)
    return out


def _plain(s, n=80):
    s = re.sub(r"\\[a-zA-Z]+\{([^}]*)\}", r"\1", str(s or ""))
    s = re.sub(r"[{}$\\]", "", s).replace("\n", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s[:n] + ("…" if len(s) > n else "")


def _hex(c):
    from matplotlib.colors import to_hex
    try:
        import numpy as np
        a = np.asarray(c, dtype=object if isinstance(c, str) else float)
        if a.ndim == 2:
            if not len(a):
                return None
            c = a[0]
        return to_hex(c)
    except Exception:
        try:
            return to_hex(c)
        except Exception:
            return None


def _line_text(ln):
    import numpy as np
    try:
        x = np.asarray(ln.get_xdata(), dtype=float)
        y = np.asarray(ln.get_ydata(), dtype=float)
    except Exception:
        return "line"
    fmt = lambda v: f"{v:.4g}"
    if len(x) == 2 and len(y) == 2:
        if y[0] == y[1] and x[0] != x[1]:
            return f"horizontal line at {fmt(y[0])}"
        if x[0] == x[1] and y[0] != y[1]:
            return f"vertical line at {fmt(x[0])}"
    ls = ln.get_linestyle()
    if ls in ("None", "", " ", "none") and ln.get_marker() not in (None, "None", "", " ", "none"):
        return f"markers ({len(x)} points)"
    return f"line ({len(x)} points)"


def _line_group(ln):
    """A Line2D drawn as markers only belongs to the markers group, any other to the lines group."""
    ls = ln.get_linestyle()
    if ls in ("None", "", " ", "none") and ln.get_marker() not in (None, "None", "", " ", "none"):
        return "markers"
    return "lines"


def _coll_kind(c):
    n = type(c).__name__
    if n == "PathCollection":
        return "markers"
    if n in ("LineCollection",):
        return "lines"
    if "Poly" in n or "FillBetween" in n:
        return "area"
    return "collection"


_NUM = re.compile(r"[-−]?\d+(?:[.,]\d+)*")


def _nkey(i, kind, lab, seen):
    """Key of a named element: its legend label with the numbers taken out (a label like "Maximum: 100,0 N" keeps
    its key when new data change the value); equal labels are told apart by their order."""
    base = f"{i}.{kind}:{_NUM.sub('#', lab).strip()[:110]}"
    k = seen.get(base, 0)
    seen[base] = k + 1
    return base if k == 0 else f"{base}~{k}"


def inventory(fig) -> list:
    """Every drawn element of a figure: [{key, ax, kind, text, named, artists}] in a stable order (see the module
    docstring for the keys). Axes titles, labels, ticks and legends are styled by their own spec keys."""
    from matplotlib.container import BarContainer
    out = []
    for i, ax in enumerate(fig.axes):
        if not ax.get_visible():
            continue
        in_bars = set()
        seen = {}
        nb = 0
        for c in ax.containers:
            if isinstance(c, BarContainer):
                ps = list(c.patches)
                in_bars.update(id(p) for p in ps)
                lab = c.get_label() or ""
                named = bool(lab) and not lab.startswith("_")
                key = _nkey(i, "bars", lab, seen) if named else f"{i}.bars{nb}"
                if not named:
                    nb += 1
                out.append({"key": key, "ax": i, "kind": "bars", "named": named, "group": "areas",
                            "raw": lab if named else None,
                            "text": lab if named else f"bars ({len(ps)})", "artists": ps, "container": c})
        n = 0
        for ln in ax.get_lines():
            lab = ln.get_label() or ""
            named = bool(lab) and not lab.startswith("_")
            key = _nkey(i, "line", lab, seen) if named else f"{i}.line{n}"
            if not named:
                n += 1
            out.append({"key": key, "ax": i, "kind": "line", "named": named, "text": lab if named else _line_text(ln),
                        "group": _line_group(ln), "raw": lab if named else None, "artists": [ln]})
        n = 0
        for c in ax.collections:
            lab = c.get_label() or ""
            named = bool(lab) and not lab.startswith("_")
            kind = _coll_kind(c)
            key = _nkey(i, "coll", lab, seen) if named else f"{i}.coll{n}"
            if not named:
                n += 1
            try:
                cnt = len(c.get_offsets()) if kind == "markers" else len(c.get_paths())
            except Exception:
                cnt = 0
            out.append({"key": key, "ax": i, "kind": kind, "named": named, "raw": lab if named else None,
                        "group": "markers" if kind == "markers" else "lines" if kind == "lines" else "areas",
                        "text": lab if named else f"{kind} ({cnt})", "artists": [c]})
        n = 0
        for p in ax.patches:
            if id(p) in in_bars:
                continue
            if n >= 80:
                break
            lab = p.get_label() or ""
            named = bool(lab) and not lab.startswith("_")
            key = _nkey(i, "patch", lab, seen) if named else f"{i}.patch{n}"
            if not named:
                n += 1
            out.append({"key": key, "ax": i, "kind": "area", "named": named, "group": "areas", "raw": lab if named else None,
                        "text": lab if named else ("shaded band" if type(p).__name__ in ("Rectangle", "Polygon") else "shape"),
                        "artists": [p]})
        for n, t in enumerate(ax.texts[:120]):
            out.append({"key": f"{i}.text{n}", "ax": i, "kind": "label" if hasattr(t, "arrow_patch") or type(t).__name__ == "Annotation" else "text",
                        "named": False, "group": "annotations", "raw": t.get_text(),
                        "text": _plain(t.get_text()) or "(empty text)", "artists": [t]})
    sup = getattr(fig, "_suptitle", None)
    for n, t in enumerate([t for t in fig.texts if t is not sup][:40]):
        out.append({"key": f"f.text{n}", "ax": None, "kind": "text", "named": False, "group": "annotations",
                    "raw": t.get_text(), "text": _plain(t.get_text()) or "(empty text)", "artists": [t]})
    for it in out:
        it["part"] = _part_of([it.get("container")] + list(it["artists"]))
    return out


def _part_of(arts):
    for a in arts:
        p = getattr(a, PART_ATTR, None) if a is not None else None
        if p:
            return p
    return None


def mark(artists, part: str):
    """Mark artists (one, a list, what ax.plot returns, a BarContainer or the result of fill_between) as belonging to
    part ``part`` of the figure. Returns what it was given, so it can wrap a drawing call:
    ``mark(ax.plot(x, y, label="Hüllkurve"), "envelope")``."""
    from matplotlib.container import Container
    todo = [artists]
    while todo:
        a = todo.pop()
        if a is None:
            continue
        if isinstance(a, (list, tuple)) or isinstance(a, Container):
            if isinstance(a, Container):
                setattr(a, PART_ATTR, part)
            todo.extend(list(a))
            continue
        try:
            setattr(a, PART_ATTR, part)
        except Exception:
            pass
    return artists


def part_artists(fig, items=None) -> dict:
    """{part id: [artists]} of the marked artists of a figure (from the inventory)."""
    out = {}
    for it in (items if items is not None else inventory(fig)):
        if it.get("part"):
            out.setdefault(it["part"], []).extend(it["artists"])
    return out


def shown_parts(fig, parts, items=None, spec=None) -> dict:
    """{part id: visible?} for the declared part ids: a part is shown while any of its artists is visible; a part
    hidden in ``spec["parts"]`` is not shown; a part without marked artists counts as shown (nothing to tell)."""
    arts = part_artists(fig, items)
    hid = set(((spec or {}).get("parts") or {}).keys())
    out = {}
    for p in parts:
        if p in hid:
            out[p] = False
        elif arts.get(p):
            out[p] = any(a.get_visible() for a in arts[p])
        else:
            out[p] = True
    return out


def _color_of(art):
    for g in ("get_color", "get_facecolor", "get_edgecolor"):
        if hasattr(art, g):
            c = _hex(getattr(art, g)())
            if c:
                return c
    return None


def _set_color(art, c):
    import matplotlib.text as mtext
    if isinstance(art, mtext.Text):
        art.set_color(c)
        ap = getattr(art, "arrow_patch", None)
        if ap is not None:
            ap.set_color(c)
        return
    if type(art).__name__ == "Line2D":
        art.set_color(c)
        if str(art.get_markerfacecolor()).lower() != "none":
            art.set_markerfacecolor(c)
        art.set_markeredgecolor(c)
        return
    if hasattr(art, "get_fill") and not art.get_fill():
        art.set_edgecolor(c)          # an outline only
        return
    if hasattr(art, "set_facecolor"):
        import numpy as np
        from matplotlib.colors import to_rgba_array
        try:
            ec = to_rgba_array(art.get_edgecolor())
            edged = bool(len(ec)) and float(ec[0][3]) > 0
        except Exception:
            edged = False
        art.set_facecolor(c)
        if edged:
            art.set_edgecolor(c)
        return
    art.set_color(c)


def _style_art(art, d, mtext):
    """One artist with the props of an element or group entry (color, lw, ls, alpha, size, bold, text, hidden)."""
    is_text = isinstance(art, mtext.Text)
    if d.get("color"):
        try:
            _set_color(art, d["color"])
        except Exception:
            pass
    if "lw" in d and hasattr(art, "set_linewidth") and not is_text:
        art.set_linewidth(d["lw"])
    if d.get("ls") and hasattr(art, "set_linestyle") and not is_text:
        try:
            art.set_linestyle(d["ls"])
        except Exception:
            pass
    if "alpha" in d:
        art.set_alpha(d["alpha"])
    if "size" in d:
        if is_text:
            art.set_fontsize(d["size"])
        elif hasattr(art, "set_markersize"):
            art.set_markersize(d["size"])
        elif hasattr(art, "set_sizes"):
            art.set_sizes([d["size"] ** 2])
    if is_text and "bold" in d:
        art.set_fontweight("bold" if d["bold"] else "normal")
    if is_text and d.get("text") is not None:
        art.set_text(d["text"])
    if d.get("hidden"):
        art.set_visible(False)


def _style_texts(texts, d, mtext):
    for t in texts:
        if t is not None:
            _style_art(t, {k: v for k, v in d.items() if k != "text"}, mtext)


def _plotted(ax) -> list:
    return [*ax.lines, *ax.collections, *ax.patches]


def _extent(a, ax) -> tuple:
    """Data range of a plotted artist as ``((x0, x1) or None, (y0, y1) or None)``. A coordinate that is not in data
    units (the height of a vertical line, the width of a band) has no range."""
    import numpy as np
    from matplotlib.collections import Collection
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    try:
        if isinstance(a, Line2D):
            xy, tr = np.asarray(a.get_xydata(), float), a.get_transform()
        elif isinstance(a, Collection):
            tr = a.get_offset_transform()
            off = np.ma.filled(np.ma.asarray(a.get_offsets(), float), np.nan)
            if len(off) and any(tr.contains_branch_seperately(ax.transData)):
                xy = off
            else:                                    # filled areas and line collections have their data in the paths
                tr = a.get_transform()
                verts = [p.vertices for p in a.get_paths() if len(p.vertices)]
                if not verts:
                    return None, None
                xy = np.vstack(verts)
        elif isinstance(a, Patch):
            xy, tr = a.get_path().transformed(a.get_patch_transform()).vertices, a.get_data_transform()
        else:
            return None, None
        in_data = tr.contains_branch_seperately(ax.transData)
    except (AttributeError, TypeError, ValueError):
        return None, None
    out = []
    for k in (0, 1):
        v = xy[:, k][np.isfinite(xy[:, k])] if in_data[k] else xy[:0, k]
        out.append((float(v.min()), float(v.max())) if v.size else None)
    return tuple(out)


def _refit(fig, shown_before: set) -> None:
    """After hiding parts of a figure: an axis that only reached so far for what is now hidden closes in on what is
    still shown. A limit at zero stays, and so does a limit the visible data reach anyway."""
    import numpy as np
    gone = {id(a) for ax in fig.axes for a in _plotted(ax) if id(a) in shown_before and not a.get_visible()}
    if not gone:
        return
    for ax in fig.axes:
        for dim, (get, put, scale, shared) in enumerate(((ax.get_xlim, ax.set_xlim, ax.get_xscale(), ax.get_shared_x_axes()),
                                                         (ax.get_ylim, ax.set_ylim, ax.get_yscale(), ax.get_shared_y_axes()))):
            if scale not in ("linear", "log"):
                continue
            log = scale == "log"
            conv = (lambda v: float(np.log10(max(v, 1e-300)))) if log else float
            vis, hid = [], []
            for sib in shared.get_siblings(ax):
                for a in _plotted(sib):
                    e = _extent(a, sib)[dim]
                    if e is None or (log and e[1] <= 0):
                        continue
                    if id(a) in gone:
                        hid.append((conv(e[0]), conv(e[1])))
                    elif a.get_visible():
                        vis.append((conv(e[0]), conv(e[1])))
            if not hid or not vis:
                continue
            l0, l1 = get()
            lo, hi = conv(min(l0, l1)), conv(max(l0, l1))
            span = hi - lo
            if not span > 0:
                continue
            v0, v1 = min(x[0] for x in vis), max(x[1] for x in vis)
            pad = 0.08 * ((v1 - v0) or span)
            new_lo, new_hi = lo, hi
            if min(x[0] for x in hid) < v0 and v0 - lo > 0.15 * span and (log or lo != 0):
                new_lo = max(lo, v0 - pad)
            if max(x[1] for x in hid) > v1 and hi - v1 > 0.15 * span and (log or hi != 0):
                new_hi = min(hi, v1 + pad)
            if (new_lo, new_hi) == (lo, hi):
                continue
            a, b = (10 ** new_lo, 10 ** new_hi) if log else (new_lo, new_hi)
            if log:                                  # exactly the old limit where it did not move
                a, b = (min(l0, l1) if new_lo == lo else a), (max(l0, l1) if new_hi == hi else b)
            put(b, a) if l0 > l1 else put(a, b)
            leg = ax.get_legend()                    # the curve now fills the axes: the key finds a free corner again
            if leg is not None and hasattr(leg, "set_loc"):
                leg.set_loc("best")


def apply(fig, spec) -> dict:
    """Apply a style spec to a matplotlib figure in place. Returns the resolved spec that was applied (with
    ``notes`` when something could not be done as asked, e.g. a missing font)."""
    s = resolved(spec)
    if not s:
        return s
    import matplotlib.text as mtext
    from matplotlib.ticker import MaxNLocator
    notes = []
    items = inventory(fig) if (s.get("elements") or s.get("groups") or s.get("parts")) else []   # keys as drawn
    shown_before = {id(a) for ax in fig.axes for a in _plotted(ax) if a.get_visible()}

    # size
    w0, h0 = fig.get_size_inches()
    if "width_mm" in s or "aspect" in s:
        w = s.get("width_mm", w0 * 25.4) / 25.4
        asp = s.get("aspect", h0 / w0 if w0 else 0.7)
        fig.set_size_inches(w, w * asp)
    # fonts: keep the hierarchy (titles > labels > ticks/legend) around the chosen size
    fam = None
    if s.get("font"):
        fam, note = _family(s["font"])
        if note:
            notes.append(note)
    fs = s.get("font_size")
    if fam or fs:
        titles = set()
        for ax in fig.axes:
            titles.update({id(ax.title), id(getattr(ax, "_left_title", None)), id(getattr(ax, "_right_title", None))})
        if getattr(fig, "_suptitle", None) is not None:
            titles.add(id(fig._suptitle))
        labels = set()
        for ax in fig.axes:
            labels.update({id(ax.xaxis.label), id(ax.yaxis.label)})
        for t in fig.findobj(mtext.Text):
            if fam:
                t.set_fontfamily(fam)
                if s.get("font") == "cm":
                    t.set_math_fontfamily("cm")
            if fs:
                t.set_fontsize(fs + 1 if id(t) in titles else (fs if id(t) in labels else max(4.0, fs - 1)))
        if fam:
            for ax in fig.axes:
                try:
                    ax.tick_params(labelfontfamily=fam[0])
                except (TypeError, ValueError):
                    pass
    # series
    pal = s.get("palette")
    if isinstance(pal, str):
        pal = PALETTES.get(pal)
    series = s.get("series") or {}
    lw = s.get("line_width")
    relabel = False
    for ax in fig.axes:
        k = 0
        for art in _data_artists(ax):
            lab = art.get_label() or ""
            named = bool(lab) and not lab.startswith("_")
            d = series.get(lab, {}) if named else {}
            is_line = hasattr(art, "set_linewidth") and hasattr(art, "get_xdata")
            if lw and is_line and art.get_linewidth() > 0:
                art.set_linewidth(lw)
            if pal and named:
                try:
                    art.set_color(pal[k % len(pal)])
                except Exception:
                    pass
                k += 1
            if d.get("color"):
                try:
                    art.set_color(d["color"])
                except Exception:
                    pass
            if d.get("lw") and hasattr(art, "set_linewidth"):
                art.set_linewidth(d["lw"])
            if d.get("ls") and hasattr(art, "set_linestyle"):
                art.set_linestyle(d["ls"])
            if d.get("hidden"):
                art.set_visible(False)
                art.set_label("_hidden_" + lab)
                relabel = True
            elif d.get("label") is not None:
                art.set_label(d["label"])
                relabel = True
    # groups by kind, then single elements: an element's own entry overrides its group
    els = s.get("elements") or {}
    grp = s.get("groups") or {}
    prt = s.get("parts") or {}
    for it in items:
        g = grp.get(it.get("group")) or {}
        p = prt.get(it.get("part")) or {}
        d = els.get(it["key"]) or {}
        if not (g or p or d):
            continue
        for art in it["artists"]:
            _style_art(art, {**g, **p, **d}, mtext)
        hidden = d.get("hidden", p.get("hidden", g.get("hidden")))
        if it["named"] and (hidden or d.get("label") is not None):
            tgt = [it["container"]] if it.get("container") is not None else it["artists"]
            for a in tgt:
                a.set_label(("_hidden_" + a.get_label()) if hidden else d["label"])
            relabel = True
    # a hidden part also takes its artists outside the element list along (a key drawn as its own legend, …)
    if prt:
        listed = {id(a) for it in items for a in it["artists"]}
        for ax in fig.axes:
            for a in ax.get_children():
                if id(a) not in listed and getattr(a, PART_ATTR, None) in prt:
                    a.set_visible(False)
    _refit(fig, shown_before)                    # before the axes below, so limits set by hand still win
    # colours of the frame
    cols = s.get("colors") or {}
    if cols.get("background"):
        fig.patch.set_facecolor(cols["background"])
    for ax in fig.axes:
        if cols.get("plot"):
            ax.set_facecolor(cols["plot"])
        if cols.get("axes"):
            for sp in ax.spines.values():
                sp.set_edgecolor(cols["axes"])
        if cols.get("ticks"):
            ax.tick_params(which="both", colors=cols["ticks"])
        if cols.get("grid"):
            ax.tick_params(which="both", grid_color=cols["grid"])
        if cols.get("text"):
            for t in (ax.title, getattr(ax, "_left_title", None), getattr(ax, "_right_title", None), ax.xaxis.label, ax.yaxis.label):
                if t is not None:
                    t.set_color(cols["text"])
            ax.tick_params(which="both", labelcolor=cols["text"])
    if cols.get("text") and getattr(fig, "_suptitle", None) is not None:
        fig._suptitle.set_color(cols["text"])
    # legend
    lg = s.get("legend") or {}
    for ax in fig.axes:
        old = ax.get_legend()
        want = lg.get("show", old is not None)
        if not want:
            if old is not None:
                old.remove()
            continue
        if old is None and not lg.get("show"):
            continue
        if old is not None and not relabel and not lg and not (pal or series or els or grp or cols.get("text")):
            continue
        h, l_ = ax.get_legend_handles_labels()
        if not h:
            if old is not None:
                old.remove()
            continue
        kw = {}
        loc = lg.get("loc")
        if loc == "outside":
            kw.update(loc="upper left", bbox_to_anchor=(1.02, 1.0), borderaxespad=0)
        elif loc:
            kw["loc"] = loc
        elif old is not None:
            kw["loc"] = old._loc
            bb = old.get_bbox_to_anchor()
            if old._bbox_to_anchor is not None:
                kw["bbox_to_anchor"] = bb.transformed(ax.transAxes.inverted()).bounds[:2]
        frame = lg.get("frame", old.get_frame_on() if old is not None else True)
        size = max(4.0, (fs or 9) - 1) if fs else (old.get_texts()[0].get_fontsize() if old is not None and old.get_texts() else None)
        new = ax.legend(h, l_, frameon=frame, **({"fontsize": size} if size else {}), **kw)
        for t in new.get_texts():
            if fam:
                t.set_fontfamily(fam)
            if cols.get("text"):
                t.set_color(cols["text"])
        if cols.get("background") or cols.get("plot"):
            new.get_frame().set_facecolor(cols.get("plot") or cols["background"])
    # title
    if "title" in s:
        if getattr(fig, "_suptitle", None) is not None:
            fig._suptitle.set_text(s["title"])
        elif fig.axes:
            fig.axes[0].set_title(s["title"])
    # axes
    for i, d in enumerate(s.get("axes") or []):
        if i >= len(fig.axes) or not d:
            continue
        ax = fig.axes[i]
        if "xlabel" in d:
            ax.set_xlabel(d["xlabel"])
        if "ylabel" in d:
            ax.set_ylabel(d["ylabel"])
        if "xscale" in d:
            ax.set_xscale(d["xscale"])
        if "yscale" in d:
            ax.set_yscale(d["yscale"])
        if "xlim" in d:
            lo, hi = ax.get_xlim()
            ax.set_xlim(d["xlim"][0] if d["xlim"][0] is not None else lo, d["xlim"][1] if d["xlim"][1] is not None else hi)
        if "ylim" in d:
            lo, hi = ax.get_ylim()
            ax.set_ylim(d["ylim"][0] if d["ylim"][0] is not None else lo, d["ylim"][1] if d["ylim"][1] is not None else hi)
        if "grid" in d:
            ax.grid(d["grid"])
        if "xticks" in d:
            ax.xaxis.set_major_locator(MaxNLocator(d["xticks"]))
        if "yticks" in d:
            ax.yaxis.set_major_locator(MaxNLocator(d["yticks"]))
        if fs:
            ax.tick_params(labelsize=max(4.0, fs - 1))
        if fam:
            for t in ax.get_xticklabels() + ax.get_yticklabels():
                t.set_fontfamily(fam)
    # groups of texts that are not drawn elements (CS-02): axis labels, tick labels, legend entries
    if grp.get("axis_labels"):
        for ax in fig.axes:
            _style_texts((ax.xaxis.label, ax.yaxis.label), grp["axis_labels"], mtext)
    tl = grp.get("tick_labels") or {}
    if tl:
        for ax in fig.axes:
            kw = {}
            if tl.get("color"):
                kw["labelcolor"] = tl["color"]
            if "size" in tl:
                kw["labelsize"] = tl["size"]
            if tl.get("hidden"):
                kw.update(labelbottom=False, labeltop=False, labelleft=False, labelright=False)
            if kw:
                ax.tick_params(which="both", **kw)
    if grp.get("series_names"):
        legends = [ax.get_legend() for ax in fig.axes] + list(getattr(fig, "legends", []))
        for lgd in legends:
            if lgd is not None:
                _style_texts(lgd.get_texts(), grp["series_names"], mtext)
    if notes:
        s["notes"] = notes
    return s


def frame(fig, crop=None):
    """The region a styled figure is saved with (inches): the tight box with matplotlib's usual padding, cut by
    ``crop`` [left, top, right, bottom] as shares of that box. PDF and PNG use the same region."""
    import matplotlib
    from matplotlib.transforms import Bbox
    fig.draw_without_rendering()
    bb = fig.get_tightbbox().padded(matplotlib.rcParams.get("savefig.pad_inches", 0.1) or 0.0)
    if crop:
        l, t, r, b = crop
        w, h = bb.width, bb.height
        bb = Bbox.from_extents(bb.x0 + l * w, bb.y0 + b * h, bb.x1 - r * w, bb.y1 - t * h)
    return bb


def boxes(fig, bb) -> list:
    """Per axes where it sits in an image saved with region ``bb`` (shares of the image, from top left:
    [x0, y0, x1, y1]) with its current limits and scales; the editing window maps a dragged box to data with it."""
    out = []
    for ax in fig.axes:
        if not ax.get_visible() or not ax.axison:
            out.append(None)
            continue
        e = ax.get_window_extent()
        dpi = fig.dpi
        x0, x1 = e.x0 / dpi, e.x1 / dpi
        y0, y1 = e.y0 / dpi, e.y1 / dpi
        f = lambda v: round(float(v), 5)
        out.append({"box": [f((x0 - bb.x0) / bb.width), f((bb.y1 - y1) / bb.height), f((x1 - bb.x0) / bb.width),
                            f((bb.y1 - y0) / bb.height)],
                    "xlim": [float(v) for v in ax.get_xlim()], "ylim": [float(v) for v in ax.get_ylim()],
                    "xscale": ax.get_xscale(), "yscale": ax.get_yscale()})
    return out


def tag(fig, items=None) -> dict:
    """SVG ids for the editing window's instant preview (CS-01): every drawn element gets ``cel<n>`` (``cel<n>-<k>``
    when it has several artists, e.g. bars) and the axis labels ``cax<i>x``/``cax<i>y``. Call before ``apply`` so the
    keys are those of the figure as drawn. Returns {element key: [ids]} plus "@xlabel<i>"/"@ylabel<i>"."""
    out = {}
    for n, it in enumerate(items if items is not None else inventory(fig)):
        arts = it["artists"]
        ids = [f"cel{n}"] if len(arts) == 1 else [f"cel{n}-{k}" for k in range(min(len(arts), 200))]
        for a, gid in zip(arts, ids):
            a.set_gid(gid)
        out[it["key"]] = ids
    for i, ax in enumerate(fig.axes):
        ax.xaxis.label.set_gid(f"cax{i}x")
        ax.yaxis.label.set_gid(f"cax{i}y")
        out[f"@xlabel{i}"] = [f"cax{i}x"]
        out[f"@ylabel{i}"] = [f"cax{i}y"]
    return out


def describe(fig) -> dict:
    """What the editing window offers for a figure: size, per axes the labels, limits and scales, the named series
    with their colours, every drawn element (``elements``), whether there is a legend and a title, and the fonts."""
    w, h = fig.get_size_inches()
    axes, series = [], []
    seen = set()
    for ax in fig.axes:
        if not ax.get_visible() or not ax.axison:
            axes.append({})
            continue
        axes.append({"xlabel": ax.get_xlabel(), "ylabel": ax.get_ylabel(), "xlim": [round(float(v), 6) for v in ax.get_xlim()],
                     "ylim": [round(float(v), 6) for v in ax.get_ylim()], "xscale": ax.get_xscale(), "yscale": ax.get_yscale(),
                     "legend": ax.get_legend() is not None, "grid": any(l.get_visible() for l in ax.get_xgridlines() + ax.get_ygridlines())})
        for art in _data_artists(ax):
            lab = art.get_label() or ""
            if lab.startswith("_") or lab in seen:
                continue
            seen.add(lab)
            series.append({"label": lab, "color": _color_of(art)})
    elements = []
    counts = {g: 0 for g in GROUPS}
    for it in inventory(fig):
        a = it["artists"][0] if it["artists"] else None
        e = {"key": it["key"], "ax": it["ax"], "kind": it["kind"], "text": it["text"], "named": it["named"],
             "group": it.get("group"), "color": _color_of(a) if a is not None else None,
             "visible": bool(a.get_visible()) if a is not None else True}
        if it.get("raw") is not None:
            e["raw"] = str(it["raw"])[:1000]        # the full text, for find and replace (CS-04)
        if it.get("part"):
            e["part"] = it["part"]
        elements.append(e)
        if it.get("group") in counts:
            counts[it["group"]] += 1
    for ax in fig.axes:
        if ax.get_visible() and ax.axison:
            counts["axis_labels"] += sum(1 for t in (ax.xaxis.label, ax.yaxis.label) if t.get_text())
            counts["tick_labels"] += 1
            lgd = ax.get_legend()
            if lgd is not None:
                counts["series_names"] += len(lgd.get_texts())
    title = fig._suptitle.get_text() if getattr(fig, "_suptitle", None) is not None else (fig.axes[0].get_title() if fig.axes else "")
    ax0 = next((a for a in fig.axes if a.get_visible() and a.axison), None)
    frame_cols = {}
    try:
        frame_cols = {"background": _hex(fig.patch.get_facecolor())}
        if ax0 is not None:
            frame_cols.update(plot=_hex(ax0.get_facecolor()), axes=_hex(next(iter(ax0.spines.values())).get_edgecolor()),
                              text=_hex(ax0.xaxis.label.get_color()),
                              ticks=_hex(ax0.xaxis.get_major_ticks()[0].tick1line.get_color()) if ax0.xaxis.get_major_ticks() else None,
                              grid=_hex(ax0.xaxis.get_major_ticks()[0].gridline.get_color()) if ax0.xaxis.get_major_ticks() else None)
    except Exception:
        pass
    return {"width_mm": round(float(w) * 25.4, 1), "aspect": round(float(h / w), 3) if w else 0.7, "axes": axes, "series": series,
            "elements": elements, "groups": counts, "colors": frame_cols, "title": title, "fonts": font_names()}
