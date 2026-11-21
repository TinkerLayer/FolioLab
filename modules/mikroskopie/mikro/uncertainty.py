"""Messunsicherheit der Partikelkennwerte (Rechnung: labcalc.uncertainty im SDK).

Einstellungen im Arbeitsstand ``state["unc"]`` (mit dem Bild gespeichert, im Bericht unter source.request)::

    {"method": "gum" | "mc" | "gauss" | "worst", "p": 0.95, "k": None, "lang": "de",
     "cal": {"mode": "line", "L": 50, "N": 412.3} | {"mode": "px", "pw": 0.121},   # wie der Massstab entstand
     "specs": {"cal_len": {"parts": [...]},    # bekannte Länge (Objektmikrometer: Zertifikat U, k)
               "cal_px":  {"parts": [...]},    # Linienlänge in Pixeln (Kantenablesung, z. B. ±1 px)
               "cal_pw":  {"parts": [...]}}}   # direkt eingegebene Pixelgrösse

Modelle:
    Massstab        s = L / N  (Linie) bzw. s = pw (eingegeben)
    Längen          Y = Q · (s/s0)        ECD-Mittel, D10, D50, D90, Dv50, Feret-Mittel
    Flächen         Y = Q · (s/s0)²       mittlere Partikelfläche
    Anzahl          N mit u(N) = √N       Zählstatistik (Poisson; Taylor 1997, Kap. 11)
    Flächenanteil   A_A = Σ a_i / A       s kürzt sich heraus; u aus dem Bootstrap über die Partikel
Q trägt die Stichprobenunsicherheit (Typ A) aus einem Bootstrap über die Partikel (B = 1000, fester Seed, Efron und
Tibshirani 1993), mit denselben Gewichten (Randkorrektur) wie die Kennwerte. Mehrere Bilder (Felder): Mittelwert mit
s/√n und t-Faktor nach ASTM E562; der Massstab gilt für alle Bilder gleich (voll korreliert).
Anzahlanteile (k von n) bekämen die Binomialunsicherheit √(p(1 − p)/n) (``binomial_u``); das Modul bildet derzeit
keine Anzahlanteile.
"""
from __future__ import annotations

import math

import numpy as np

METHODS = ("gum", "mc", "gauss", "worst")
SEED = 20261119
B_DEFAULT = 1000
CAL_KEYS = ("cal_len", "cal_px", "cal_pw")

# Modul-eigene Quellen (labcite-Format); nicht am Original geprüft: so gekennzeichnet
SOURCES = {
    "efron1993": {
        "type": "book", "authors": "Efron, B.; Tibshirani, R. J.", "year": "1993",
        "title": "An Introduction to the Bootstrap", "container": "Chapman & Hall",
        "note": "Kap. 6 (Bootstrap-Standardfehler); Angaben nicht am Original geprüft"},
    "astm-e562": {
        "type": "standard", "authors": "ASTM", "container": "ASTM International", "year": "2019",
        "title": "ASTM E562 Standard Test Method for Determining Volume Fraction by Systematic Manual Point Count",
        "note": "Mittelwert der Felder, Vertrauensbereich t·s/√n; Angaben nicht am Original geprüft"},
    "taylor1997-11": {
        "type": "book", "authors": "Taylor, J. R.", "year": "1997",
        "title": "An Introduction to Error Analysis: The Study of Uncertainties in Physical Measurements",
        "container": "University Science Books", "edition": "2. Auflage",
        "note": "Kap. 11 (Poisson-Verteilung, Zählstatistik √N); Angaben nicht am Original geprüft"},
}

# Ergebnis -> (Schlüssel der Zusammenfassung, Potenz von s, Bezeichnung de, en, Variable der Gleichungen)
SIZES = {
    "meanECD": ("MeanECD", 1, "Mittlerer Äquivalentdurchmesser", "mean equivalent diameter"),
    "D10": ("D10", 1, "D10 (Q0)", "D10 (Q0)"),
    "D50": ("D50", 1, "D50 (Q0)", "D50 (Q0)"),
    "D90": ("D90", 1, "D90 (Q0)", "D90 (Q0)"),
    "Dv50": ("Dv50", 1, "Dv50 (Q3)", "Dv50 (Q3)"),
    "meanFeret": ("MeanFeret", 1, "Mittlerer Feret-Durchmesser", "mean Feret diameter"),
    "meanArea": ("AverageSize", 2, "Mittlere Partikelfläche", "mean particle area"),
}


def _un():
    try:
        from labcalc import uncertainty as UN
    except ImportError:
        import sys
        from pathlib import Path
        p = Path(__file__).resolve().parents[3] / "sdk" / "python"
        if p.is_dir() and str(p) not in sys.path:
            sys.path.insert(0, str(p))
        from labcalc import uncertainty as UN
    return UN


def settings(state: dict | None) -> dict | None:
    u = (state or {}).get("unc")
    if not isinstance(u, dict):
        return None
    try:
        p = float(u.get("p") or 0.95)
    except (TypeError, ValueError):
        p = 0.95
    try:
        k = float(u["k"]) if u.get("k") not in (None, "", 0) else None
    except (TypeError, ValueError):
        k = None
    specs = {key: sp for key, sp in (u.get("specs") or {}).items()
             if key in CAL_KEYS and isinstance(sp, dict) and isinstance(sp.get("parts"), list) and sp["parts"]}
    cal = u.get("cal") if isinstance(u.get("cal"), dict) else {}
    try:
        B = int(u.get("boot") or B_DEFAULT)
    except (TypeError, ValueError):
        B = B_DEFAULT
    return {"method": u.get("method") if u.get("method") in METHODS else "gum", "p": min(max(p, 0.5), 0.999),
            "k": k if (k and k > 0) else None, "lang": "en" if u.get("lang") == "en" else "de", "specs": specs,
            "cal": cal, "boot": min(max(B, 100), 5000)}


def binomial_u(k: int, n: int) -> float:
    """Standardunsicherheit eines Anzahlanteils p = k/n (Binomialverteilung): √(p(1 − p)/n)."""
    if n <= 0:
        raise ValueError("n muss positiv sein")
    p = k / n
    return math.sqrt(p * (1 - p) / n)


def poisson_u(n: float) -> float:
    """Zählstatistik: u(N) = √N (Poisson)."""
    return math.sqrt(max(float(n), 0.0))


def _parts(st, key) -> list:
    return [dict(p) for p in (st["specs"].get(key) or {}).get("parts") or [] if isinstance(p, dict)]


def scale_inputs(calib, st, lang="de"):
    """Eingangsgrössen des Massstabs und s(v): Linie (L, N) oder direkt eingegebene Pixelgrösse pw."""
    de = lang == "de"
    s0 = float(calib.pw)
    unit = calib.unit
    cal = st["cal"]
    try:
        L, N = float(cal.get("L") or 0), float(cal.get("N") or 0)
    except (TypeError, ValueError):
        L = N = 0.0
    if cal.get("mode") == "line" and L > 0 and N > 0 and abs(L / N - s0) <= 1e-6 * s0:
        ins = [{"name": "L", "value": L, "unit": unit, "label": "bekannte Länge (Objektmikrometer)" if de else
                "known length (stage micrometer)", "parts": _parts(st, "cal_len")},
               {"name": "N", "value": N, "unit": "px", "label": "Linienlänge in Pixeln" if de else "line length in pixels",
                "parts": _parts(st, "cal_px")}]
        return ins, (lambda v: v["L"] / v["N"]), s0, "s = L / N"
    ins = [{"name": "pw", "value": s0, "unit": f"{unit}/px", "label": "Pixelgrösse" if de else "pixel size",
            "parts": _parts(st, "cal_pw")}]
    return ins, (lambda v: v["pw"]), s0, "s = pw"


def _boot(stat, n, B, seed=SEED):
    """Bootstrap-Standardabweichung einer Statistik über n Partikel (Ziehen mit Zurücklegen, fester Seed)."""
    if n < 2:
        return None
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(B):
        idx = rng.integers(0, n, n)
        v = stat(idx)
        if v is not None and math.isfinite(v):
            vals.append(v)
    return float(np.std(vals, ddof=1)) if len(vals) > 1 else None


def bootstrap(part: dict, B: int = B_DEFAULT, seed: int = SEED) -> dict:
    """Typ-A-Unsicherheit (Bootstrap-Standardabweichung) der Kennwerte einer Partikelanalyse."""
    from .measure import wmean_sd, wquantile
    rows = part.get("rows") or []
    n = len(rows)
    out = {}
    if n >= 2:
        ecd = np.array([r["ECD"] for r in rows], float)
        w = np.array([r.get("Weight", 1.0) for r in rows], float)
        area = np.array([r["Area"] for r in rows], float)
        fer = np.array([r["Feret"] for r in rows], float)
        out["meanECD"] = _boot(lambda i: wmean_sd(ecd[i], w[i])[0], n, B, seed)
        out["meanArea"] = _boot(lambda i: wmean_sd(area[i], w[i])[0], n, B, seed)
        out["meanFeret"] = _boot(lambda i: wmean_sd(fer[i], w[i])[0], n, B, seed)
        for k, q in (("D10", 0.1), ("D50", 0.5), ("D90", 0.9)):
            out[k] = _boot(lambda i, q=q: wquantile(ecd[i], w[i], (q,))[0], n, B, seed)
        out["Dv50"] = _boot(lambda i: wquantile(ecd[i], w[i] * ecd[i] ** 3, (0.5,))[0], n, B, seed)
    fg = np.asarray(part.get("fg_areas") or [], float)
    reg = (part.get("summary") or {}).get("RegionArea")
    if fg.size >= 2 and reg:
        out["areaFrac"] = _boot(lambda i: float(fg[i].sum() / reg * 100), fg.size, B, seed)
    return out


def models(a, st, lang: str = "de") -> dict:
    """Name -> {f, inputs, unit, label, model, notes} der Partikelkennwerte."""
    de = lang == "de"
    part = a.part
    if not part:
        return {}
    summ = part.get("summary") or {}
    n = len(part.get("rows") or [])
    unit = a.calib.unit if a.calib.calibrated else "px"
    boot = bootstrap(part, st["boot"])
    blabel = (f"Stichprobe: Bootstrap über die Partikel (B = {st['boot']}, Seed {SEED}), Typ A" if de else
              f"sampling: bootstrap over the particles (B = {st['boot']}, seed {SEED}), type A")
    out = {}
    sins, sf, s0, stxt = scale_inputs(a.calib, st, lang) if a.calib.calibrated else ([], None, 1.0, "")
    if a.calib.calibrated:
        out["px"] = {"f": sf, "inputs": sins, "unit": f"{unit}/px", "label": "Pixelgrösse" if de else "pixel size",
                     "model": stxt, "notes": []}
    nt = ("Massstab für x und y gleich (quadratische Pixel); bei nicht quadratischen Pixeln gilt die relative "
          "Unsicherheit für beide Richtungen." if de else
          "Scale equal in x and y (square pixels); for non-square pixels the relative uncertainty applies to both.")
    for name, (key, pw, lde, len_) in SIZES.items():
        q0 = summ.get(key)
        if q0 is None or not n:
            continue
        parts = []
        if boot.get(name):
            parts.append({"kind": "sd", "sd": boot[name], "n": 1, "label": blabel})
        u_ = unit + ("²" if pw == 2 else "")
        qin = {"name": "Q", "value": float(q0), "unit": u_, "label": (lde if de else len_) + (" (Bild, Massstab s0)" if de else
               " (image, scale s0)"), "parts": parts}
        if a.calib.calibrated:
            f = (lambda v, pw=pw: v["Q"] * (sf(v) / s0) ** pw)
            model = f"Y = Q · (s/s0)" + ("²" if pw == 2 else "")
        else:
            f = (lambda v: v["Q"])
            model = "Y = Q"
        out[name] = {"f": f, "inputs": [qin] + sins, "unit": u_, "label": lde if de else len_, "model": model,
                     "notes": [nt] if (a.calib.calibrated and not a.calib.square) else []}
    N = summ.get("Count")
    if N:
        out["n"] = {"f": (lambda v: v["N"]), "unit": "", "label": "Anzahl Partikel" if de else "particle count",
                    "inputs": [{"name": "N", "value": float(N), "unit": "", "label": "gezählte Partikel" if de else "counted particles",
                                "parts": [{"kind": "u", "u": poisson_u(N), "label": "Zählstatistik (Poisson, √N)" if de else
                                           "counting statistics (Poisson, √N)"}]}],
                    "model": "u(N) = √N", "notes": []}
    if summ.get("AreaFraction") is not None and boot.get("areaFrac"):
        out["areaFrac"] = {"f": (lambda v: v["AA"]), "unit": "%", "label": "Flächenanteil" if de else "area fraction",
                           "inputs": [{"name": "AA", "value": float(summ["AreaFraction"]), "unit": "%",
                                       "label": "Flächenanteil" if de else "area fraction",
                                       "parts": [{"kind": "sd", "sd": boot["areaFrac"], "n": 1, "label": blabel}]}],
                           "model": "A_A = Σ a_i / A",
                           "notes": ["Der Massstab kürzt sich heraus (Fläche der Partikel und der Auswertung skalieren gleich)."
                                     if de else "The scale cancels (particle and analysed area scale alike)."]}
    return out


def _refs_text(lang: str, name: str) -> list[str]:
    """Ausgeschriebene Modul-Quellen eines Kennwerts (Bootstrap; Anzahl: Zählstatistik)."""
    keys = ["taylor1997-11"] if name == "n" else ([] if name == "px" else ["efron1993"])
    try:
        import labcite
        return [labcite.text(SOURCES[k], lang) for k in keys]
    except ImportError:
        return [SOURCES[k]["title"] for k in keys]


def _zero(res: dict) -> bool:
    """Ergebnis ohne jede Unsicherheit (u = 0 und U = 0) wird nicht gezeigt."""
    return not (res.get("u") or 0) > 0 and not (res.get("U") or 0) > 0


def evaluate_all(a, lang: str | None = None) -> dict | None:
    st = settings(a.state)
    if st is None:
        return None
    lang = lang or st["lang"]
    UN = _un()
    out = {}
    try:
        ms = models(a, st, lang)
    except Exception as e:  # noqa: BLE001 – Fehler gehören zur Unsicherheit, nie zur Auswertung
        return {"settings": st, "results": {}, "error": str(e)}
    for name, m in ms.items():
        try:
            res = UN.evaluate(m["f"], m["inputs"], st["method"], p=st["p"], k=st["k"], lang=lang, unit=m["unit"],
                              label=m["label"], name=name)
        except (UN.UncError, ValueError, ZeroDivisionError) as e:
            out[name] = {"name": name, "label": m["label"], "error": str(e)}
            continue
        if _zero(res):
            continue                                  # hängt von keiner unsicheren Eingabe ab
        res["model"] = m["model"]
        res["note_texts"] = list(res.get("note_texts") or []) + m["notes"]
        res["refs_full"] = list(dict.fromkeys(list(res.get("refs_full") or []) + _refs_text(lang, name)))
        out[name] = res
    rel = None
    if out.get("px") and out["px"].get("u") is not None and out["px"].get("value"):
        rel = out["px"]["u"] / out["px"]["value"]
    return {"settings": st, "results": out, "rel_scale": rel}


def compare(a, name: str, lang: str | None = None) -> dict:
    st = settings(a.state)
    if st is None:
        raise ValueError("Keine Messunsicherheit eingestellt")
    lang = lang or st["lang"]
    m = models(a, st, lang).get(name)
    if m is None:
        raise ValueError(f"Kennwert {name} hat keine Unsicherheit")
    return _un().compare(m["f"], m["inputs"], p=st["p"], k=st["k"], lang=lang, unit=m["unit"], label=m["label"], name=name)


def variables(a, unc: dict | None) -> dict:
    """Kennwerte als Variablen der eigenen Gleichungen (Name -> {value, unit, label, u?})."""
    if not a.part:
        return {}
    s = a.part.get("summary") or {}
    unit = a.calib.unit if a.calib.calibrated else "px"
    v = {}

    def put(name, value, u_, label):
        if value is not None and math.isfinite(float(value)):
            v[name] = {"value": float(value), "unit": u_, "label": label}

    put("n", s.get("Count"), "", "Anzahl Partikel")
    put("nCorr", s.get("CountCorrected"), "", "Anzahl randkorrigiert")
    put("areaFrac", s.get("AreaFraction"), "%", "Flächenanteil")
    put("meanArea", s.get("AverageSize"), unit + "²", "Mittlere Fläche")
    put("meanECD", s.get("MeanECD"), unit, "Mittlerer Äquivalentdurchmesser")
    put("sdECD", s.get("SDECD"), unit, "Std.-Abw. Äquivalentdurchmesser")
    put("meanCirc", s.get("MeanCirc"), "", "Mittlere Zirkularität")
    put("meanFeret", s.get("MeanFeret"), unit, "Mittlerer Feret-Durchmesser")
    for k in ("D10", "D50", "D90", "Dv10", "Dv50", "Dv90"):
        put(k, s.get(k), unit, f"{k} ({'Q0' if k[1] != 'v' else 'Q3'})")
    put("region", s.get("RegionArea"), unit + "²", "Ausgewertete Fläche")
    if a.calib.calibrated:
        put("px", a.calib.pw, f"{unit}/px", "Pixelgrösse")
    for name, res in ((unc or {}).get("results") or {}).items():
        if name in v and not res.get("error") and res.get("u") is not None:
            v[name]["u"] = float(res["u"])
    return v


def evaluate_equations(a, unc: dict | None, defs, lang: str = "de") -> tuple[dict, list]:
    """Eigene Gleichungen mit den Kennwerten (Unsicherheit wird fortgepflanzt, Verfahren wie oben)."""
    vars_ = variables(a, unc)
    ext = (getattr(a, "state", None) or {}).get("ext_values")   # aus dem Projektindex übernommene Werte
    if not defs and not ext:
        return vars_, []
    try:
        from labcalc import formulas as F
    except ImportError:
        return vars_, []
    F.merge_ext(vars_, ext)
    if not defs:
        return vars_, []
    from .taken import guard                               # Indexwerte: unpassende Einheiten ablehnen
    st = (unc or {}).get("settings")
    opts = {"method": st["method"], "p": st["p"], "k": st["k"]} if st else None
    return vars_, guard(F.evaluate([d for d in defs if isinstance(d, dict)][:60], vars_, lang=lang, unc=opts), vars_, lang=lang)


def series(analyses, lang: str = "de") -> dict:
    """Mehrere Bilder (Felder): Mittelwert ± Unsicherheit je Kennwert. Typ A aus der Streuung der Felder (t·s/√n nach
    ASTM E562 über die Freiheitsgrade n − 1); Längen dazu die relative Unsicherheit des Massstabs (für alle Bilder
    gleich, voll korreliert)."""
    rows = [(a, evaluate_all(a, lang)) for a in analyses if a.part]
    rows = [(a, u) for a, u in rows if u]
    if len(rows) < 2:
        return {}
    UN = _un()
    st = rows[0][1]["settings"]
    de = lang == "de"
    rels = [u.get("rel_scale") for _, u in rows if u.get("rel_scale")]
    rel = float(np.mean(rels)) if rels else 0.0
    out = {}
    names = [("areaFrac", "AreaFraction", 0, "%", "Flächenanteil", "area fraction"),
             ("meanECD", "MeanECD", 1, None, "Mittlerer Äquivalentdurchmesser", "mean equivalent diameter"),
             ("D50", "D50", 1, None, "D50 (Q0)", "D50 (Q0)")]
    for name, key, pw, unit, lde, len_ in names:
        vals = [a.part["summary"].get(key) for a, _ in rows]
        vals = [float(x) for x in vals if x is not None]
        if len(vals) < 2:
            continue
        u_ = unit or (rows[0][0].calib.unit if rows[0][0].calib.calibrated else "px")
        ins = [{"name": "m", "value": float(np.mean(vals)), "unit": u_,
                "label": (f"Mittelwert der Felder (n = {len(vals)})" if de else f"mean of the fields (n = {len(vals)})"),
                "parts": [{"kind": "repeats", "values": vals,
                           "label": "Streuung der Felder (Typ A, ASTM E562)" if de else "scatter of the fields (type A, ASTM E562)"}]}]
        if pw and rel > 0:
            ins.append({"name": "ks", "value": 1.0, "unit": "", "label": "Massstab (für alle Bilder gleich)" if de else
                        "scale (same for all images)", "parts": [{"kind": "u", "u": rel * pw}]})
            f = (lambda v: v["m"] * v["ks"])
        else:
            f = (lambda v: v["m"])
        try:
            res = UN.evaluate(f, ins, st["method"], p=st["p"], k=st["k"], lang=lang, unit=u_,
                              label=(lde if de else len_) + (" (Serie)" if de else " (series)"), name=name)
        except UN.UncError:
            continue
        if _zero(res):
            continue
        res["n"] = len(vals)
        try:
            import labcite
            res["refs_full"] = list(res.get("refs_full") or []) + [labcite.text(SOURCES["astm-e562"], lang)]
        except ImportError:
            pass
        out[name] = res
    return out


# ------------------------------------------------------------------------------------------------ Bericht
def to_report(b, a, lang: str = "de", unc: dict | None = None) -> dict | None:
    """Werte (<Name>-pm, -u, -U), Budgettabellen und Methodentext eines Bildes; None ohne Einstellung."""
    import labcite
    from labbundle import cite, tex_escape

    unc = unc or evaluate_all(a, lang)
    if not unc:
        return None
    res = [x for x in unc["results"].values() if not x.get("error")]
    if not res:
        return None
    UN = _un()
    uo = UN.to_report(b, res, lang, "unc-")
    keys = [labcite.to_bib(b, k, rec) for k, rec in SOURCES.items() if k != "astm-e562"]
    de = lang == "de"
    st = unc["settings"]
    rel = unc.get("rel_scale")
    head = (("Die Messunsicherheit der Partikelkennwerte setzt sich aus dem Massstab "
             + ("($s = L/N$ aus einer Linie über eine bekannte Länge)" if st["cal"].get("mode") == "line" else "(Pixelgrösse)")
             + " und der Stichprobe der Partikel zusammen: Längen skalieren mit $s$, Flächen mit $s^2$; die "
             f"Stichprobenunsicherheit ist ein Bootstrap über die Partikel (B = {st['boot']}, fester Startwert {SEED}, "
             "Typ A) mit den Gewichten der Randkorrektur, die Anzahl trägt die Zählstatistik $\\sqrt{N}$, der "
             f"Flächenanteil die Bootstrap-Streuung der Partikelflächen{cite(keys)}.")
            if de else
            ("The measurement uncertainty of the particle parameters combines the scale "
             + ("($s = L/N$ from a line over a known length)" if st["cal"].get("mode") == "line" else "(pixel size)")
             + " and the sample of particles: lengths scale with $s$, areas with $s^2$; the sampling uncertainty is a "
             f"bootstrap over the particles (B = {st['boot']}, fixed seed {SEED}, type A) with the edge-correction weights, "
             "the count carries the counting statistics $\\sqrt{N}$, the area fraction the bootstrap scatter of the particle "
             f"areas{cite(keys)}."))
    if rel:
        head += (f" Relative Standardunsicherheit des Massstabs: {tex_escape(f'{rel * 100:.3g}')}\\,\\%." if de else
                 f" Relative standard uncertainty of the scale: {tex_escape(f'{rel * 100:.3g}')}\\,\\%.")
    return {"values": uo["values"], "tables": uo["tables"], "cites": list(dict.fromkeys(keys + uo["cites"])),
            "latex": head + "\n" + uo["latex"], "results": {x["name"]: x for x in res}}
