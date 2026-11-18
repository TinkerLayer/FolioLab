"""Ergebnisse des Rechners fuer den Bericht (Format folio-lab-bundle/1).

Inhalt: Rechenweg der Formelkarten, Tabelle der Groessen, Werte fuer \\labval, Diagramme (Bild und CSV),
markierte Nebenrechnungen und Matrizen. Die Quelle ist der Arbeitsstand selbst; "Aktualisieren" rechnet alles neu.
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

_SDK = Path(__file__).resolve().parents[3] / "sdk" / "python"
if _SDK.is_dir() and str(_SDK) not in sys.path:
    sys.path.insert(0, str(_SDK))

from labbundle import Bundle, booktabs, slugify, tex_escape  # noqa: E402

import numpy as np  # noqa: E402

from . import expr as E  # noqa: E402
from . import graph as G  # noqa: E402
from . import library as L  # noqa: E402
from . import plots as P  # noqa: E402
from . import render as R  # noqa: E402
from . import solver as S  # noqa: E402
from . import units as U  # noqa: E402
from . import workspace as W  # noqa: E402

T = {
    "de": {"module": "Rechner", "title": "Berechnung", "worked": "Rechenweg", "table": "Verwendete Grössen",
           "h_sym": "Symbol", "h_name": "Grösse", "h_val": "Wert", "h_src": "Herkunft", "given": "gegeben",
           "calc": "berechnet: {}", "der": "abgeleitet: {}", "side": "Nebenrechnungen", "mat": "Matrizen",
           "plot": "Diagramm {}", "tab_cap": "Gegebene und berechnete Grössen.", "data": "Kurvenpunkte von {}",
           "intro": "Die Rechnung folgt den angegebenen Formeln; Zwischenwerte sind in SI-Einheiten gerechnet.",
           "nothing": "Keine Inhalte gewählt oder noch nichts berechnet.", "fit": "Anpassung {name}: ${tex}$, $R^2 = {r2}$.",
           "env": "Blatt", "reg": "Regression \\texttt{{{src}}}: {params}; $R^2 = {r2}$ ($n = {n}$).",
           "reg_u": "Angegeben ist der Wert $\\pm$ Standardunsicherheit aus der Kovarianzmatrix am Optimum; "
                    "Vertrauensbereich 95 \\% mit $t = {t}$ ({dof} Freiheitsgrade).",
           "noconv": "Achtung: die Anpassung ist nicht konvergiert; die Werte sind unzuverlässig.",
           "gfit_lb": "Lineweaver--Burk-Gerade; bekannt verzerrt, die direkte Anpassung ist vorzuziehen",
           "gfit_fo": "Die Unsicherheiten der zurückgerechneten Parameter sind Näherungen erster Ordnung.",
           "methods": "Methodik",
           "ds_intro": "Die Rechenzeilen verwenden Spalten von Datensätzen aus der Datenaufbereitung als Listen in "
                       "SI-Einheiten; ausgeschlossene Zeilen und Zeilen mit Lücken sind in allen gewählten Spalten "
                       "entfernt.",
           "ds_one": "Datensatz \\emph{{{title}}} (Freigabe {share}, Version {version}, {mode}): {cols}; "
                     "{used} von {rows} Zeilen verwendet.",
           "ds_live": "folgt der neuesten Version", "ds_pin": "fest auf diese Version",
           "gfit": "Anpassung {name} ({how}) an {y} über {x}{src}: {params}; $R^2 = {r2}$, $n = {n}${rng}. "
                   "Angegeben ist der Wert $\\pm$ Standardunsicherheit; Vertrauensbereich 95 \\% mit $t = {t}$.",
           "gfit_lin": "linearisiert, Ausgleichsgerade durch die umgerechneten Punkte", "gfit_dir": "direkt, kleinste Quadrate in y",
           "gfit_rng": ", nur {lo} $\\le x \\le$ {hi}", "gfit_ds": " (Datensatz \\emph{{{t}}})",
           "ds_plot": "Datensatz \\emph{{{title}}} (Freigabe {share}, Version {version}): {n} Zeilen; im Bild auf die Auflösung verdichtet."},
    "en": {"module": "Calculator", "title": "Calculation", "worked": "Worked calculation", "table": "Quantities used",
           "h_sym": "Symbol", "h_name": "Quantity", "h_val": "Value", "h_src": "Source", "given": "given",
           "calc": "calculated: {}", "der": "derived: {}", "side": "Side calculations", "mat": "Matrices",
           "plot": "Plot {}", "tab_cap": "Given and calculated quantities.", "data": "Curve points of {}",
           "intro": "The calculation follows the equations shown; intermediate values are computed in SI units.",
           "nothing": "Nothing selected or nothing calculated yet.", "fit": "Fit {name}: ${tex}$, $R^2 = {r2}$.",
           "env": "Sheet", "reg": "Regression \\texttt{{{src}}}: {params}; $R^2 = {r2}$ ($n = {n}$).",
           "reg_u": "Values are given $\\pm$ standard uncertainty from the covariance matrix at the optimum; "
                    "95 \\% confidence with $t = {t}$ ({dof} degrees of freedom).",
           "noconv": "Warning: the fit did not converge; the values are unreliable.",
           "gfit_lb": "Lineweaver--Burk line; known to be biased, the direct fit is preferable",
           "gfit_fo": "The uncertainties of back-transformed parameters are first-order approximations.",
           "methods": "Methods",
           "ds_intro": "The calculation lines use columns of datasets from Datenaufbereitung as lists in SI units; "
                       "excluded rows and rows with gaps are removed from all chosen columns.",
           "ds_one": "Dataset \\emph{{{title}}} (share {share}, version {version}, {mode}): {cols}; "
                     "{used} of {rows} rows used.",
           "ds_live": "follows the newest version", "ds_pin": "pinned to this version",
           "gfit": "Fit {name} ({how}) of {y} versus {x}{src}: {params}; $R^2 = {r2}$, $n = {n}${rng}. "
                   "Values are given $\\pm$ standard uncertainty; 95 \\% confidence with $t = {t}$.",
           "gfit_lin": "linearised, straight line through the transformed points", "gfit_dir": "direct, least squares in y",
           "gfit_rng": ", only {lo} $\\le x \\le$ {hi}", "gfit_ds": " (dataset \\emph{{{t}}})",
           "ds_plot": "Dataset \\emph{{{title}}} (share {share}, version {version}): {n} rows; thinned to the resolution in the figure."},
}


def fold_eq(a, b):
    from .recognize import fold
    return fold(a) == fold(b)


def _key(sym, used):
    k = E.plain_name(sym).translate(str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"}))
    k = re.sub(r"[^A-Za-z0-9]+", "-", k).strip("-") or "wert"
    base, i = k, 2
    while k in used:
        k = f"{base}-{i}"
        i += 1
    used.add(k)
    return k


def _axl(sym, unit):
    ut = R.unit_tex(unit)
    return f"${R.sym_tex(sym)}$" + (f" in ${ut}$" if ut else "")


VALUE_DIGITS = 6        # gültige Ziffern für Werte ohne Unsicherheit im Bericht (Tabelle, \labval, Anpassung)


def _pm_tex(v, u, unit, lang):
    """Wert ± Unsicherheit mit Einheit: Unsicherheit auf zwei gültige Ziffern, der Wert auf dieselbe Dezimalstelle
    (also mit so vielen Ziffern, wie die Unsicherheit trägt, auch bei grossen und kleinen Beträgen: dann mit
    gemeinsamer Zehnerpotenz). Ohne Unsicherheit VALUE_DIGITS gültige Ziffern."""
    if v is None:
        return "--"
    dec = "{,}" if lang == "de" else "."
    if u and u > 0 and math.isfinite(u) and math.isfinite(v):
        last = math.floor(math.log10(u)) - 1                 # Stelle der zweiten gültigen Ziffer von u
        if abs(v) >= 1e5 or abs(v) < 1e-3:
            ev = max(math.floor(math.log10(abs(v))) if v != 0 else last, last + 1)
            d = max(0, ev - last)
            m, mu = v / 10.0 ** ev, u / 10.0 ** ev
            s = f"({m:.{d}f} \\pm {mu:.{d}f})".replace(".", dec) + r"\cdot 10^{%d}" % ev
        else:
            d = max(0, -last)
            s = f"{v:.{d}f} \\pm {u:.{d}f}".replace(".", dec)
            if unit and R.unit_tex(unit):                   # Klammer nur, wenn eine Einheit folgt
                s = "(" + s + ")"
    else:
        s = R.num_tex(v, lang, VALUE_DIGITS)
    ut = R.unit_tex(unit) if unit else ""
    return s + (r"\," + ut if ut else "")


def _fit_note(o, L_, lang):
    ps = ", ".join(f"${R.sym_tex(p['sym'])} = {_pm_tex(p.get('value'), p.get('u'), p.get('unit'), lang)}$" for p in o.get("params") or [])
    rng = o.get("range")
    src = L_["gfit_ds"].format(t=tex_escape(o["of_title"])) if o.get("of_title") else ""
    how = L_["gfit_lin" if o.get("mode") != "direct" else "gfit_dir"]
    if o.get("method") == "Lineweaver–Burk":
        how += "; " + L_["gfit_lb"]
    txt = L_["gfit"].format(
        name=tex_escape(o.get("name") or ""), how=how,
        y=f"${R.sym_tex(o.get('yname') or 'y')}$", x=f"${R.sym_tex(o.get('xname') or 'x')}$", src=src, params=ps,
        r2=R.num_tex(o["r2"], lang, 5) if o.get("r2") is not None else "--", n=o.get("n"),
        rng=L_["gfit_rng"].format(lo=f"${R.num_tex(rng[0], lang, 4)}$", hi=f"${R.num_tex(rng[1], lang, 4)}$") if rng else "",
        t=R.num_tex(o["t"], lang, 4) if o.get("t") else "--")
    if o.get("u_method") == "first_order_back_transform":
        txt += " " + L_["gfit_fo"]
    if o.get("converged") is False:
        txt += " " + L_["noconv"]
    return txt


def _plot_ctx(req, plot, runs):
    """Grössen für die Ausdrücke eines Diagramms neu bestimmen (damit "Aktualisieren" geänderte Werte übernimmt)."""
    ctx = dict(plot.get("ctx") or {})
    ctx.setdefault("angle", req.get("angle", "rad"))
    ctx.setdefault("complex", req.get("complex"))
    ctx["vars"] = req.get("vars") or ctx.get("vars") or {}
    if "env" not in plot:
        return ctx
    env_id = str(plot.get("env") or "")
    for env, n, sh, out, ok in runs:
        if env_id and str(env.get("id")) == env_id:
            ctx["quantities"] = {k["sym"]: {"si": k["si"], "kind": k["kind"]} for k in out["known"]}
            return ctx
    glob = S.Sheet({"values": [v for v in req.get("values") or [] if v.get("scope", "all") in (None, "all", "")],
                    "lang": req.get("lang", "de")})
    glob.load_values()
    ctx["quantities"] = {kn.sym: {"si": kn.si, "kind": kn.kind} for kn in glob.user.values()}
    return ctx


def build(request: dict, lang="de", include=None, title=None) -> dict:
    L_ = T["en" if lang == "en" else "de"]
    inc = {"worked": True, "table": True, "values": True, "plots": True, "console": True, "matrices": True}
    inc.update(include or {})
    title = title or request.get("title") or L_["title"]
    req = {**W.from_legacy(request), "lang": lang}
    envs = [e for e in req.get("envs") or [] if isinstance(e, dict)]
    multi = len(envs) > 1
    env_name = {str(e.get("id")): (e.get("name") or "").strip() or f"{L_['env']} {n}" for n, e in enumerate(envs, 1)}

    # Jede Umgebung rechnen
    runs = []                                                  # (env, Nummer, Arbeitsblatt, Ergebnis, ok-Karten)
    for n, (env, sh, out) in enumerate(W.run_all(req, envs)[0], 1):   # mit weitergegebenen Zeilenvariablen
        cards = W.env_cards(env)
        ok = [(c, o) for c, o in zip(cards, out["cards"]) if o.get("status") == "ok"]
        runs.append((env, n, sh, out, ok))
    n_ok = sum(len(r[4]) for r in runs)
    b = Bundle(module="rechner", module_name=L_["module"], title=title, lang=lang, slug=request.get("slug"),
               summary=f"{n_ok} " + ("Formeln" if lang == "de" else "equations"))
    any_content = False

    # Quellen: je Formel ihre Quelle, je verwendete Konstante deren Quelle (CODATA 2022, SI-Broschüre, …)
    import labcite
    from labcalc import sources as SRC
    cited: dict[str, str] = {}

    def cite_src(skey):
        if skey not in cited:
            cited[skey] = labcite.to_bib(b, "rf-" + skey, SRC.REFS[skey])
        return cited[skey]

    def eq_cites(eq):
        keys = [cite_src(eq.source_key)]
        for cn in dict.fromkeys(eq.consts):
            ck = SRC.CONSTANT_SOURCES.get(cn, (None,))[0]
            if ck and ck != "bronstein":                       # π und e brauchen keinen Beleg im Text
                keys.append(cite_src(ck))
        return ",".join(dict.fromkeys(keys))

    # ---- Methodik (DP-11): Datensätze, deren Spalten in Rechenzeilen stehen, mit Freigabe-ID und Version
    ds_used = set()
    for env, n, sh, out, ok in runs:
        ds_used.update(out.get("ds_used") or [])
    ds_text = []
    for info in req.get("dsinfo") or []:
        vs = [v for v in info.get("vars") or [] if v["name"] in ds_used]
        if not vs or info.get("error"):
            continue
        cols = ", ".join(f"${R.sym_tex(v['name'])}$" + (f" (${R.unit_tex(v['unit'])}$)" if R.unit_tex(v["unit"]) else "")
                         for v in vs)
        ds_text.append(L_["ds_one"].format(title=tex_escape(info.get("title") or info["share"]), share=tex_escape(info["share"]),
                                           version=info.get("version"), cols=cols, used=info.get("used"), rows=info.get("rows"),
                                           mode=L_["ds_pin" if info.get("mode") == "pin" else "ds_live"]))
    if ds_text:
        b.add_text("methodik", L_["ds_intro"] + "\n\n" + "\n\n".join(ds_text) + "\n", L_["methods"])
        any_content = True

    # ---- Rechenweg, je Umgebung ein Abschnitt, wenn es mehrere gibt
    if inc["worked"] and n_ok:
        parts = [L_["intro"], ""]
        for env, n, sh, out, ok in runs:
            if not ok:
                continue
            if multi:
                parts.append(r"\subsubsection*{%s}" % tex_escape(env_name[str(env.get("id"))]))
            for c, o in ok:
                eq = L.BY_ID[o["eq"]]
                name = eq.de if lang == "de" else eq.en
                parts.append(r"\noindent\textbf{%s} \cite{%s}" % (tex_escape(name), eq_cites(eq)))
                parts.append(r"\[ %s \]" % o["sol_tex"])
                parts.append(r"\[ %s \]" % o["sub_tex"])
                parts.append("")
        b.add_text("rechenweg", "\n".join(parts), L_["worked"])
        any_content = True

    # ---- Tabelle und Werte
    rows, vals, used = [], [], set()

    def add_row(sym, label, si, unit, kind, src_text, key_hint=None, cite=""):
        k = U.ensure_kind(kind)
        v = S.to_unit(si, unit, k)
        qt = "$" + R.qty_tex(v, unit, lang, VALUE_DIGITS) + "$"
        rows.append(["$" + R.sym_tex(sym) + "$", tex_escape(label), qt, tex_escape(src_text) + (r" \cite{%s}" % cite if cite else "")])
        vals.append((_key(key_hint or sym, used), tex_escape(f"{E.plain_name(sym)}: {label}"), qt,
                     re.sub(r"<[^>]+>", "", R.qty_html(v, unit, lang, VALUE_DIGITS)).replace("&#8239;", " ")))

    seen_user = set()
    for env, n, sh, out, ok in runs:
        for kn in sh.user.values():
            if kn.src in seen_user:                            # Variable für "alle" nur einmal aufführen
                continue
            seen_user.add(kn.src)
            vid = kn.src[5:]
            v = next((x for x in req.get("values") or [] if str(x.get("id")) == vid), {})
            sc = v.get("scope", "all")
            src = L_["given"]
            if multi and isinstance(sc, list):
                src += " (" + ", ".join(env_name[str(e)] for e in sc if str(e) in env_name) + ")"
            og = v.get("origin") if isinstance(v.get("origin"), dict) else None
            if og and og.get("index"):                         # A7: aus dem Projektindex (unveränderlicher Eintrag)
                src = (("Projektindex " if lang == "de" else "project index ") + str(og["index"])
                       + (f" ({og['from']})" if og.get("from") else "")
                       + ((", hier geändert" if lang == "de" else ", edited here") if og.get("edited") else ""))
            elif og:                                           # A5: übernommen, mit fester Freigabe-Version
                src = (("aus " if lang == "de" else "from ") + str(og.get("module_name") or og.get("module") or "?")
                       + (f", {og['env_name']}" if og.get("env_name") else "")
                       + (f", {og['share']} v{og.get('version')}" if og.get("share") else "")
                       + ((", hier geändert" if lang == "de" else ", edited here") if og.get("edited") else ""))
            label = kn.label or U.ensure_kind(kn.kind).de
            if kn.name != kn.sym:                              # eigener Name, z. B. "Geschwindigkeit_Auto" als v
                own = E.plain_name(kn.name).replace("_", " ")
                label = own if fold_eq(own, label) else f"{own} ({label})"
            add_row(kn.sym, label, kn.si, kn.unit, kn.kind, src, key_hint=kn.name)
    for env, n, sh, out, ok in runs:
        card_no = {id(c): k for k, c in enumerate(W.env_cards(env), 1)}    # "K1" im UI, sprachunabhängig
        where = f" ({env_name[str(env.get('id'))]})" if multi else ""
        pre = f"u{n}-" if multi else ""
        for c, o in ok:
            r = o["result"]
            if (r["sym"], r["kind"]) in sh.user:
                continue
            eq = L.BY_ID[o["eq"]]
            add_row(r["sym"], r["label"], r["si"], r["unit"], r["kind"],
                    L_["calc"].format(eq.de if lang == "de" else eq.en) + where, key_hint=pre + r["sym"] if multi else None,
                    cite=eq_cites(eq))
            for v in o["vars"]:
                if v.get("src") == "manual":
                    add_row(v["sym"], v["de"] if lang == "de" else v["en"], v["si"], v["unit"], v["kind"], L_["given"] + where,
                            key_hint=f"{pre}k{card_no[id(c)]}-{v['sym']}")
        if env.get("derive", True) is not False and request.get("include_derived"):
            for kn in sh.derived.values():
                add_row(kn.sym, kn.label, kn.si, kn.unit, kn.kind, L_["der"].format(kn.prov["name"]) + where,
                        key_hint=pre + kn.sym if multi else None)
    if inc["table"] and rows:
        b.add_table("groessen", booktabs([L_["h_sym"], L_["h_name"], L_["h_val"], L_["h_src"]], rows, "llrl"), L_["tab_cap"])
        any_content = True
    if inc["values"] and vals:
        b.add_values(vals)
        any_content = True

    # ---- Diagramme
    env_by_id = {str(e.get("id")): e for e in envs}
    ctx = P.make_ctx(request.get("ctx") or {})
    if inc["plots"]:
        for i, plot in enumerate(request.get("plots") or [], 1):
            new_style = "rows" in plot
            fns = [] if new_style else [f for f in plot.get("functions", []) if f.get("visible") is not False and f.get("kind") != "curve"]
            vis_rows = [r for r in plot.get("rows") or [] if not r.get("hidden")] if new_style else []
            curves = []
            for cc in plot.get("curves") or []:
                env = env_by_id.get(str(cc.get("env"))) or (envs[0] if envs else None)
                if env is None:
                    continue
                try:
                    cv = S.card_curve(W.env_sheet_state(req, env), cc["card"], cc["xvar"], float(cc["x0"]), float(cc["x1"]), 200)
                    xl, yl = _axl(cv["xsym"], cv["xunit"]), _axl(cv["ysym"], cv["yunit"])
                    over = "über" if lang == "de" else "versus"
                    curves.append({"x": cv["x"], "y": cv["y"], "xl": xl, "yl": yl, "color": cc.get("color"),
                                   "label": f"${R.sym_tex(cv['ysym'])}({R.sym_tex(cv['xsym'])})$: {cv['name']}",
                                   "desc": f"{E.plain_name(cv['ysym'])} {over} {E.plain_name(cv['xsym'])} ({cv['name']})"})
                    if not fns and not vis_rows:     # Achsen der Formelkurve nur, wenn sie allein im Diagramm steht
                        plot = {**plot, "xlabel": plot.get("xlabel") or xl, "ylabel": plot.get("ylabel") or yl}
                except (E.CalcError, KeyError, ValueError, TypeError):
                    pass
            if new_style:
                if not vis_rows and not curves:
                    continue
                ptitle = plot.get("title") or L_["plot"].format(i)
                fig, data, gres = G.figure(plot, _plot_ctx(req, plot, runs), lang, curves)
                b.add_figure(fig, f"diagramm{i}", tex_escape(ptitle))
                for j, d in enumerate(data, 1):
                    rows_ = [[x, y] for x, y in zip(d["x"], d["y"]) if x is not None and y is not None]
                    if not rows_:
                        continue
                    cols = d.get("columns") or ["x", "y"]
                    b.add_data_csv(f"diagramm{i}-{j}", ["x", "y"], rows_, L_["data"].format(d["label"]),
                                   labels={"x": f"${tex_escape(cols[0])}$", "y": f"${tex_escape(cols[1])}$"},
                                   plot={"x": "x", "y": "y", **({"style": "marks"} if d.get("points") else {})})
                for j, cv in enumerate(curves, 1):
                    b.add_data_csv(f"diagramm{i}-kurve{j}", ["x", "y"], [[x, y] for x, y in zip(cv["x"], cv["y"]) if y is not None],
                                   L_["data"].format(cv["desc"]), labels={"x": cv["xl"], "y": cv["yl"]}, plot={"x": "x", "y": "y"})
                notes = []
                for r in vis_rows:
                    o = gres.get(str(r.get("id"))) or {}
                    if o.get("type") == "regression":
                        us = o.get("u") or {}
                        pt = ", ".join(f"${R.sym_tex(p)} = {_pm_tex(float(v), us.get(p), '', lang)}$" for p, v in (o.get("params") or {}).items())
                        txt = L_["reg"].format(src=tex_escape(r.get("src", "").strip()), params=pt, r2=R.num_tex(o["r2"], lang, 5), n=o.get("n"))
                        if any(x is not None for x in us.values()) and o.get("t"):
                            txt += " " + L_["reg_u"].format(t=R.num_tex(o["t"], lang, 4), dof=o.get("dof"))
                        if o.get("converged") is False:
                            txt += " " + L_["noconv"]
                        notes.append(txt)
                    elif o.get("type") == "fit":
                        notes.append(_fit_note(o, L_, lang))
                    elif o.get("type") == "table" and o.get("ds"):
                        d = o["ds"]
                        notes.append(L_["ds_plot"].format(title=tex_escape(d.get("title") or ""), share=tex_escape(str((r.get("ds") or {}).get("id") or "")),
                                                          version=d.get("version"), n=d.get("rows")))
                if notes:
                    b.add_text(f"diagramm{i}-anpassung", "\n\n".join(notes) + "\n", ptitle)
                any_content = True
                continue
            if not fns and not curves:
                continue
            ptitle = plot.get("title") or L_["plot"].format(i)
            fig = P.figure(plot, ctx, lang, curves)
            b.add_figure(fig, f"diagramm{i}", tex_escape(ptitle))
            notes = []
            for j, f in enumerate(fns, 1):
                try:
                    s = P.sample(f, ctx, plot.get("view") or {}, 300)
                except E.CalcError:
                    continue
                xs, ys = s["x"], s["y"]
                rows_ = [[x, y] for x, y in zip(xs, ys) if x is not None and y is not None]
                if rows_:
                    b.add_data_csv(f"diagramm{i}-{j}", ["x", "y"], rows_, L_["data"].format(P._label(f)),
                                   labels={"x": "$x$", "y": "$y$"}, plot={"x": "x", "y": "y", **({"style": "marks"} if s.get("points") else {})})
                if s.get("fit"):
                    fr = s["fit"]
                    notes.append(L_["fit"].format(name=tex_escape(fr["name"] if lang == "de" else P.FIT_MODELS[fr["model"]][1]),
                                                  tex=fr["tex"] if lang == "de" else fr["tex"].replace("{,}", "."),
                                                  r2=R.num_tex(fr["r2"], lang, 5)))
            for j, cv in enumerate(curves, 1):
                b.add_data_csv(f"diagramm{i}-kurve{j}", ["x", "y"], [[x, y] for x, y in zip(cv["x"], cv["y"]) if y is not None],
                               L_["data"].format(cv["desc"]), labels={"x": cv["xl"], "y": cv["yl"]}, plot={"x": "x", "y": "y"})
            if notes:
                b.add_text(f"diagramm{i}-anpassung", " ".join(notes) + "\n", ptitle)
            any_content = True

    # ---- Nebenrechnungen und Matrizen
    if inc["console"]:
        lines = [r"\[ %s = %s \]" % (h.get("tex", ""), h.get("result_tex", "")) for h in request.get("console") or []
                 if h.get("tex") and h.get("result_tex")]
        for env, n, sh, out, ok in runs:
            mine = []
            for it in env.get("items") or []:
                if it.get("type") != "calc" or it.get("report") is False:
                    continue
                o = (out.get("lines") or {}).get(str(it.get("id"))) or {}
                # Konstanten in der Zeile (z. B. Rgas, NA) mit ihrer Quelle belegen
                names = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", it.get("src") or ""))
                ck = [cite_src(SRC.CONSTANT_SOURCES[c][0]) for c in names
                      if c in SRC.CONSTANT_SOURCES and c in U.CONSTANTS and SRC.CONSTANT_SOURCES[c][0] != "bronstein"]
                tail = (r" \quad \mbox{\cite{%s}}" % ",".join(dict.fromkeys(ck))) if ck else ""
                if o.get("kind") == "func" and o.get("tex"):
                    mine.append(r"\[ %s%s \]" % (o["tex"], tail))
                elif o.get("kind") in ("solve", "system", "check") and o.get("tex") and o.get("result_tex"):
                    sep = r"\quad " if o["kind"] == "check" else r"\quad\Rightarrow\quad "      # S-01/S-02
                    mine.append(r"\[ %s%s%s%s \]" % (o["tex"], sep, o["result_tex"], tail))
                elif o.get("tex") and o.get("result_tex"):
                    mine.append(r"\[ %s = %s%s \]" % (o["tex"], o["result_tex"], tail))
            if mine and multi:
                lines.append(r"\noindent\textit{%s}" % tex_escape(env_name[str(env.get("id"))]))
            lines += mine
        if any(l.startswith(r"\[") for l in lines):
            b.add_text("nebenrechnungen", "\n".join(lines) + "\n", L_["side"])
            any_content = True
    if inc["matrices"]:
        mats = []
        for name, m in (request.get("matrices") or {}).items():
            try:
                a = np.asarray(E.from_json(m), dtype=float)
            except (TypeError, ValueError):
                continue
            if a.ndim != 2 or a.size == 0:
                continue
            rows_ = [" & ".join(R.num_tex(float(x), lang, 6) for x in r) for r in a.tolist()]
            mats.append(r"\[ %s = \left(\begin{array}{%s}%s\end{array}\right) \]" % (R.sym_tex(E.norm_name(name)), "c" * a.shape[1], r" \\ ".join(rows_)))
        if mats:
            b.add_text("matrizen", "\n".join(mats) + "\n", L_["mat"])
            any_content = True
    if not any_content:
        raise ValueError(L_["nothing"])
    src = {k: v for k, v in request.items() if k not in ("dsvals", "dsinfo")}     # Werte kommen beim Aktualisieren neu
    if req.get("dsinfo"):                                       # A8: welche Version dieser Bericht benutzt hat
        src["dsvars"] = [{**bd, "version": i.get("version") or bd.get("version")}
                         for bd, i in zip(req.get("dsvars") or [], req["dsinfo"])]
    b.set_source({**src, "slug": b.slug, "lang": lang, "include": inc, "title": title}, {})
    return b.to_dict()
