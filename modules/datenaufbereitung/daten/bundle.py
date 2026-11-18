"""Report bundle of a dataset (DP-10): data CSV (pgfplots), preview figure, column and data tables, flags table,
values, methods text with the reading recipe, cleaning steps, exclusions and file hashes, and the sources of the
statistical methods used."""
from __future__ import annotations

import math

import numpy as np

import labcite
import labdataset as DS
from labbundle import Bundle, booktabs, num, tex_escape
from labcalc import units as U

from . import __version__
from . import clean as C
from .export import FLAG_NAMES

MAX_EMBED = 4 * 1024 * 1024                  # dataset JSON kept in the bundle source for Refresh up to this size
FLAG_EN = {"outlier": "outlier", "below_lod": "below detection limit", "above_range": "above range", "missing": "missing",
           "duplicate": "duplicate", "excluded": "excluded", "interpolated": "interpolated", "parse_error": "unreadable",
           "note": "note"}


def tx(s) -> str:
    """Plain text → LaTeX, pdfLaTeX-safe (Latin-1 only)."""
    return tex_escape(s).encode("latin-1", "replace").decode("latin-1")


def _chain(prov: dict) -> list[dict]:
    out, p = [], prov
    while isinstance(p, dict) and p:
        out.append(p)
        p = p.get("parent_provenance")
    return out


def _fmt(v, lang) -> str:
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "--"
    a = abs(float(v))
    nd = 0 if a >= 1000 else 1 if a >= 100 else 2 if a >= 10 else 3 if a >= 1 else 4
    if 0 < a < 1e-3 or a >= 1e7:
        m, e = f"{float(v):.3e}".split("e")
        return (m.replace(".", ",") if lang == "de" else m).replace("-", r"$-$") + rf"$\cdot10^{{{int(e)}}}$"
    return num(v, nd, lang)


def _col_fmt(vals, lang):
    """One number of decimals per table column (4 significant digits on the largest value; integers without
    decimals); falls back to _fmt per value when the column spans too many orders of magnitude."""
    x = [abs(float(v)) for v in vals if v is not None and math.isfinite(float(v))]
    if not x:
        return lambda v: _fmt(v, lang)
    m, small = max(x), min((a for a in x if a > 0), default=0.0)
    if all(float(a).is_integer() for a in x) and m < 1e7:
        nd = 0
    elif m < 1e-3 or m >= 1e7:
        return lambda v: _fmt(v, lang)
    else:
        nd = min(6, max(0, 3 - math.floor(math.log10(m))))
        if small and small < 10 ** -nd:
            return lambda v: _fmt(v, lang)
    return lambda v: "--" if v is None or not math.isfinite(float(v)) else num(float(v), nd, lang)


def _axis(c) -> str:
    return c["name"] + (f" [{c['unit']}]" if c.get("unit") else "")


def figure(ds: DS.Dataset):
    """x against up to four y columns; outlier flags as red rings, excluded rows as grey crosses."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    nums = [c for c in ds.columns if c["dtype"] == "number"]
    if not nums:
        return None
    xc = next((c for c in nums if c.get("role") == "x"), nums[0])
    ys = [c for c in nums if c is not xc and c.get("role") == "y"] or \
         [c for c in nums if c is not xc and c.get("role") in ("", "condition")][:1]
    if not ys:
        return None
    ys = [c for c in ys if (c.get("unit") or "") == (ys[0].get("unit") or "")][:4]     # one y axis, one unit
    x = ds.data[xc["key"]]
    used = ds.used_mask()
    fig, ax = plt.subplots(figsize=(6.0, 3.6))
    for i, yc in enumerate(ys):
        y = ds.data[yc["key"]]
        u = ds.data[yc["u"]] if yc.get("u") else None
        lab = _axis(yc)
        if u is not None:
            ax.errorbar(x[used], y[used], yerr=u[used], fmt="o", ms=3.5, capsize=2, lw=0.8, label=lab, color=f"C{i}")
        else:
            ax.plot(x[used], y[used], "o-" if ds.rows <= 60 else "-", ms=3.5, lw=1.0, label=lab, color=f"C{i}")
        out = [f["row"] for f in ds.header.get("flags") or [] if f["code"] == "outlier" and f.get("col") == yc["key"]
               and not f.get("excluded")]
        if out:
            ax.plot(x[out], y[out], "o", ms=8, mfc="none", mec="#c0392b", mew=1.2)
        if (~used).any():
            ax.plot(x[~used], y[~used], "x", ms=6, color="0.55")
    ax.set_xlabel(_axis(xc))
    ax.set_ylabel(_axis(ys[0]) if len(ys) == 1 else "")
    if len(ys) > 1:
        ax.legend(fontsize=8, frameon=False)
    ax.grid(alpha=0.25, lw=0.5)
    fig.tight_layout()
    return fig, xc, ys


def u_texts(ds: DS.Dataset, lang: str) -> list[str]:
    """"name: type" for every column with an uncertainty, e.g. "Masse: erweiterte Unsicherheit U (k = 2)"."""
    out = []
    by_key = {c["key"]: c for c in ds.columns}
    for c in ds.columns:
        if c.get("u") and c["u"] in by_key:
            u = by_key[c["u"]]
            out.append(f"{c['name']}: " + DS.u_type_text(u if u.get("u_type") or not c.get("u_type") else c, lang))
    return out


def methods(ds: DS.Dataset, meta: dict, lang: str, describe, cites: list[str], note: str = "") -> str:
    h = ds.header
    chain = _chain(h.get("provenance") or {})
    files = next((p.get("files") for p in chain if p.get("files")), []) or []
    recipe = next((p.get("recipe") for p in chain if p.get("recipe")), []) or []
    mv = next((p.get("module_version") for p in chain if p.get("module_version")), "")
    steps = [s for p in reversed(chain) for s in (p.get("steps") or [])]
    used = ds.used_mask()
    de = lang == "de"
    parts = []
    if files:
        fl = "; ".join(f"{f.get('name', '')}" + (f", Blatt {f['sheet']}" if de and f.get("sheet") else f", sheet {f['sheet']}" if f.get("sheet") else "")
                       + f" (SHA-256 {str(f.get('sha256', ''))[:16]}...)" for f in files[:6])
        parts.append(tx(("Die Daten stammen aus " if de else "The data come from ") + fl + "."))
    if recipe and describe:
        parts.append(tx(("Gelesen mit der Datenaufbereitung" if de else "They were read with the data preparation module")
                        + (f" {mv}" if mv else "") + ": " + "; ".join(describe(s) for s in recipe[:30]) + "."))
    if steps:
        parts.append(tx(("Bereinigung und Umrechnung: " if de else "Cleaning and conversion: ")
                        + "; ".join(f"{s.get('text') or s.get('op')} ({s.get('rows_before')} → {s.get('rows_after')} "
                                    + ("Zeilen)" if de else "rows)") for s in steps[:30]))
                     + (r"~\cite{" + ",".join(cites) + "}" if cites else "") + ".")
    fl = h.get("flags") or []
    counts = {}
    for f in fl:
        counts[f["code"]] = counts.get(f["code"], 0) + 1
    if counts:
        names = FLAG_NAMES if de else FLAG_EN
        parts.append(tx(("Markierungen (keine Zeile wurde dadurch entfernt): " if de else "Flags (no row was removed by a flag): ")
                        + ", ".join(f"{n} {names.get(k, k)}" for k, n in counts.items()) + "."))
    excl = [f for f in fl if f.get("excluded")]
    if excl:
        reasons = sorted({str(f.get("reason") or "").split("; ")[-1] for f in excl if f.get("reason")})
        rows = sorted({f["row"] + 1 for f in excl})
        parts.append(tx((f"Ausgeschlossen wurden {len(rows)} Zeile(n) (" if de else f"{len(rows)} row(s) were excluded (")
                        + ", ".join(str(r) for r in rows[:30]) + (" ..." if len(rows) > 30 else "") + ")"
                        + ((": " + "; ".join(reasons[:6])) if reasons else "") + "."))
    ut = u_texts(ds, lang)
    if ut:
        parts.append(tx(("Art der angegebenen Unsicherheit: " if de else "Type of the stated uncertainty: ")
                        + "; ".join(ut[:8]) + "."))
    cut = [t for p in chain for t in (p.get("truncations") or [])]
    if cut:
        parts.append(tx(("GEKÜRZT: " if de else "TRUNCATED: ") + "; ".join(
            f"{t.get('what', '')} ({t.get('kept')} " + ("von " if de else "of ") + f"{t.get('total')})" for t in cut[:6]) + "."))
    warn = [w for p in chain for w in (p.get("warnings") or [])]
    if warn:
        parts.append(tx(("Hinweise beim Lesen: " if de else "Notes from reading: ") + "; ".join(str(w) for w in warn[:6])
                        + ("" if str(warn[min(5, len(warn) - 1)]).endswith(".") else ".")))
    if note:
        parts.append(tx(note + ("" if note.endswith(".") else ".")))
    sid, ver = meta.get("share") or "", meta.get("version")
    parts.append(tx((f"Der Datensatz „{h['title']}“" if de else f"The dataset “{h['title']}”")
                    + (f" (Version {ver}, Kennung {sid}" if de else f" (version {ver}, ID {sid}") + f", SHA-256 {h['data_hash'][:16]}...)"
                    + (f" umfasst {ds.rows} Zeilen und {len(ds.columns)} Spalten, davon {int(used.sum())} Zeilen verwendet."
                       if de else f" has {ds.rows} rows and {len(ds.columns)} columns; {int(used.sum())} rows are used.")))
    return "\n\n".join(parts) + "\n"


def build(ds: DS.Dataset, meta: dict, request: dict, describe=None, note: str = "") -> dict:
    """`request["mode"]`: "pin" (Refresh keeps this version) or "live" (Refresh moves to the newest version);
    `note`: what Refresh changed (version moved, newest version unreadable), shown in the summary and methods."""
    lang = request.get("lang") or "de"
    de = lang == "de"
    inc = {k: True for k in ("figures", "tables", "values", "data", "citations", "text")}
    inc.update(request.get("include") or {})
    h = ds.header
    title = request.get("title") or h["title"]
    live = request.get("mode") == "live"
    b = Bundle("datenaufbereitung", "Datenaufbereitung" if de else "Data preparation", title, lang=lang,
               slug=request.get("slug") or None,
               summary=(f"{ds.rows} Zeilen × {len(ds.columns)} Spalten, v{meta.get('version')}"
                        + (" (folgt der neuesten Version)" if live else " (feste Version)") if de
                        else f"{ds.rows} rows × {len(ds.columns)} columns, v{meta.get('version')}"
                        + (" (follows the newest version)" if live else " (fixed version)"))
               + (f"; {note}" if note else ""))
    nums = [c for c in ds.columns if c["dtype"] == "number"]
    used = ds.used_mask()
    # sources of the methods in the recipe
    ops = [o for p in _chain(h.get("provenance") or {}) for o in (p.get("ops") or [])]
    srcs = []
    for o in ops:
        m = o.get("method") if o.get("op") == "outliers" else "smooth" if o.get("op") == "smooth" else None
        for k in C.METHOD_SOURCES.get(m, []) if m else []:
            if k not in srcs:
                srcs.append(k)
    cites = [C.SOURCES[k]["key"] for k in srcs] if inc["citations"] else []
    if inc["citations"]:
        for k in srcs:
            rec = {kk: vv for kk, vv in C.SOURCES[k].items() if kk != "key"}
            labcite.to_bib(b, C.SOURCES[k]["key"], rec)
    if inc["data"] and nums:
        texts = [c for c in ds.columns if c["dtype"] == "text"][:3]
        header = [c["key"] for c in nums] + ["used"] + [c["key"] for c in texts]
        rows = []
        arrs = [ds.data[c["key"]] for c in nums]
        tarr = [ds.data[c["key"]] for c in texts]
        for r in range(ds.rows):
            rows.append([None if not math.isfinite(float(a[r])) else float(a[r]) for a in arrs] + [1 if used[r] else 0]
                        + [str(a[r]).replace(",", ";")[:60] for a in tarr])
        xc = next((c for c in nums if c.get("role") == "x"), nums[0])
        yc = next((c for c in nums if c is not xc and c.get("role") == "y"), next((c for c in nums if c is not xc), xc))
        b.add_data_csv("daten", header, rows, description=tx(h["title"]), nd=12,
                       labels={c["key"]: tx(_axis(c)) for c in nums},
                       plot={"x": xc["key"], "y": yc["key"], **({"style": "marks"} if ds.rows <= 200 else {})})
    if inc["figures"]:
        fr = figure(ds)
        if fr:
            fig, xc, ys = fr
            cap = f"{h['title']}: " + ", ".join(c["name"] for c in ys) + (f" über {xc['name']}" if de else f" against {xc['name']}")
            notes = []
            if any(f["code"] == "outlier" and not f.get("excluded") for f in h.get("flags") or []):
                notes.append("rote Ringe: Ausreisser-Markierungen" if de else "red rings: outlier flags")
            if (~used).any():
                notes.append("graue Kreuze: ausgeschlossene Zeilen" if de else "grey crosses: excluded rows")
            if notes:
                cap += " (" + "; ".join(notes) + ")"
            shown = {c["key"] for c in ys}
            fc = [C.SOURCES[k]["key"] for k in srcs if inc["citations"] and (
                (k == "savgol" and any("Savitzky" in (c.get("note") or "") for c in ys)) or
                (k != "savgol" and any(f["code"] == "outlier" and f.get("col") in shown for f in h.get("flags") or [])))]
            b.add_figure(fig, "vorschau", tx(cap + "."), cites=fc)
    if inc["tables"]:
        rows = []
        for c in ds.columns:
            if c["dtype"] == "number":
                v = ds.data[c["key"]][used]
                v = v[np.isfinite(v)]
                kd = U.KINDS.get(c.get("kind") or "")
                kname = (kd.de if de else kd.en) if kd and not str(c.get("kind")).startswith("dim:") else ""
                rows.append([tx(c["name"]), tx(c.get("unit") or "--"), tx(kname), str(v.size),
                             _fmt(float(v.min()) if v.size else None, lang), _fmt(float(v.max()) if v.size else None, lang),
                             _fmt(float(v.mean()) if v.size else None, lang)])
            else:
                rows.append([tx(c["name"]), "--", "Text" if de else "text", str(int((ds.data[c["key"]][used] != "").sum())),
                             "", "", ""])
        hdr = ["Spalte", "Einheit", "Grösse", "n", "Min", "Max", "Mittelwert"] if de else \
              ["Column", "Unit", "Quantity", "n", "Min", "Max", "Mean"]
        b.add_table("spalten", booktabs(hdr, rows, align="lllrrrr"),
                    tx(f"Spalten des Datensatzes {h['title']} (verwendete Zeilen)." if de
                       else f"Columns of the dataset {h['title']} (rows used)."))
        show = ds.columns[:6]
        drows, n15 = [], min(15, ds.rows)
        fmts = {c["key"]: _col_fmt(ds.data[c["key"]][:n15], lang) for c in show if c["dtype"] == "number"}
        for r in range(n15):
            drows.append([str(r + 1)] + [(fmts[c["key"]](float(ds.data[c["key"]][r])) if c["dtype"] == "number"
                                          else tx(str(ds.data[c["key"]][r])[:24])) for c in show])
        b.add_table("daten", booktabs(["#"] + [_axis(c) for c in show], [[x for x in row] for row in drows],
                                      align="r" + "".join("r" if c["dtype"] == "number" else "l" for c in show)),
                    tx((f"Erste {len(drows)} von {ds.rows} Zeilen." if de else f"First {len(drows)} of {ds.rows} rows.")))
        fl = h.get("flags") or []
        if fl:
            names = {c["key"]: c["name"] for c in ds.columns}
            fn = FLAG_NAMES if de else FLAG_EN
            def why(f):                                   # flag reason plus exclusion reason, left-aligned in the p column
                s = " ".join(str(f.get("reason") or f.get("raw") or "").split())
                cut = s if len(s) <= 160 else s[:157].rsplit(" ", 1)[0]
                return "{\\raggedright " + tx(cut) + (" \\dots{}" if cut != s else "") + "\\par}" if s else ""
            frows = [[str(f["row"] + 1), tx(names.get(f.get("col"), "--")), tx(fn.get(f["code"], f["code"])),
                      ("ja" if de else "yes") if f.get("excluded") else "", why(f)]
                     for f in fl[:40]]
            b.add_table("markierungen", booktabs(["Zeile", "Spalte", "Markierung", "ausgeschlossen", "Grund"] if de else
                                                 ["Row", "Column", "Flag", "excluded", "Reason"], frows, align="rlllp{5cm}"),
                        tx((f"Markierungen ({len(fl)}" + (", erste 40)" if len(fl) > 40 else ")") + "; Markierungen entfernen keine Zeilen.")
                           if de else (f"Flags ({len(fl)}" + (", first 40)" if len(fl) > 40 else ")") + "; flags remove no rows.")),
                        cites=cites)
    if inc["values"]:
        b.add_values([("zeilen", "Zeilen" if de else "Rows", str(ds.rows), str(ds.rows)),
                      ("verwendet", "Verwendete Zeilen" if de else "Rows used", str(int(used.sum())), str(int(used.sum()))),
                      ("ausgeschlossen", "Ausgeschlossene Zeilen" if de else "Rows excluded", str(int((~used).sum())),
                       str(int((~used).sum()))),
                      ("version", "Version", str(meta.get("version") or ""), str(meta.get("version") or ""))])
    if inc["text"]:
        b.add_text("methodik", methods(ds, meta, lang, describe, cites, note), "Methodik" if de else "Methods")
    raw = None
    try:
        from .export import to_json
        raw = to_json(ds)
    except (TypeError, ValueError):
        raw = None
    files = {"datensatz.json": raw} if raw is not None and len(raw) <= MAX_EMBED else {}
    b.set_source({**{k: v for k, v in request.items() if k != "source"}, "share": meta.get("share"),
                  "version": meta.get("version"), "mode": "live" if live else "pin", "embedded": bool(files)}, files)
    d = b.to_dict()
    d["module_version"] = __version__        # the version of this running process (the hub records it as is)
    d["source"]["kind"] = "dataset"          # source files are the dataset version (datensatz.json), not raw files
    if note:
        d["refresh_note"] = note
    return d


def rebuild_dataset(source: dict) -> DS.Dataset | None:
    """The dataset kept in the bundle source (exact version used), or None."""
    import base64
    from .export import from_json
    raw = (source.get("files") or {}).get("datensatz.json")
    if not raw:
        return None
    return from_json(base64.b64decode(raw))
