"""Messunsicherheit der Kennwerte eines Zugversuchs (Rechnung: labcalc.uncertainty im SDK).

Einstellungen je Versuch in ``Config.unc`` (mit der Seite gespeichert, im Bericht unter source.request)::

    {"method": "gum" | "mc" | "gauss" | "worst", "p": 0.95, "k": None, "lang": "de",
     "force_class": "kraft-iso7500-1" | None,    # Kraftmesseinrichtung, Klasse nach ISO 7500-1
     "ext_class": "extenso-iso9513-1" | None,    # Längenänderungs-Messeinrichtung, Klasse nach ISO 9513
     "specs": {Feld: {"parts": [...], "note"?}}} # ± an den Eingabefeldern (width_mm, thickness_mm, diameter_mm,
                                                 # outer_d_mm, wall_mm, a0, l0_mm, speed_mm_min)

Modelle (ISO 6892-1:2019 Anhang J; UNCERT Code of Practice 07), S0 aus der Geometrie (b·h, π d²/4,
π/4 (D² − (D − 2t)²) oder direkt eingegeben):

    Rm  = Fmax / S0
    sy  = Fy / S0            Fliessbeginn (Schwelle auf der Kraftkurve, keine Rp0,2): kein Einfluss der Dehnungsmessung,
                             dafür die Lage des Punkts im Abtastintervall
    E   = ΔF · L0 / (S0 · ΔL · v/v0) / 1000      über das Fitfenster; ΔF mit dem Standardfehler der Steigung (Typ A,
                                                n − 2 Freiheitsgrade) und der Kraftklasse, ΔL mit der Extensometerklasse
    Agt = 100 · ΔL(Fmax) · (v/v0) / L0,   At = 100 · ΔL(Bruch) · (v/v0) / L0
    Ag  = 100 · (ΔL(Fmax) − ΔL_el) · (v/v0) / L0,   A = 100 · (ΔL(Bruch) − ΔL_el,Bruch) · (v/v0) / L0

ΔL = v0 · (t − t0) ist der Weg aus Zeit und Prüfgeschwindigkeit v0; v/v0 trägt die Unsicherheit der Geschwindigkeit
(entfällt, wenn die Zeitachse aus einem gemessenen Weg berechnet wurde: dann kürzt sich v heraus). ReH, ReL und Rp0,2
bestimmt das Modul nicht.
"""
from __future__ import annotations

import math

import numpy as np

METHODS = ("gum", "mc", "gauss", "worst")
# Eingabefelder der Seite mit ±: Schlüssel -> (Name im Modell, Bezeichnung de, en, Einheit)
FIELDS = {
    "width_mm": ("b", "Stegbreite b", "width b", "mm"),
    "thickness_mm": ("h", "Dicke h", "thickness h", "mm"),
    "diameter_mm": ("d", "Durchmesser d", "diameter d", "mm"),
    "outer_d_mm": ("D", "Aussendurchmesser D", "outer diameter D", "mm"),
    "wall_mm": ("t", "Wanddicke t", "wall thickness t", "mm"),
    "a0": ("S0", "Querschnitt S0 (direkt)", "cross-section S0 (entered)", "mm²"),
    "l0_mm": ("L0", "Messlänge L0", "gauge length L0", "mm"),
    "speed_mm_min": ("v", "Prüfgeschwindigkeit v", "test speed v", "mm/min"),
}
# Ergebnisse in fester Reihenfolge: Name -> (Bezeichnung de, en, Variable der eigenen Gleichungen)
RESULTS = {          # Klartext (Bericht: tex_escape, Seite: textContent)
    "S0": ("Querschnitt S0", "cross-section S0", "A0"),
    "Fmax": ("Höchstkraft Fmax", "maximum force Fmax", "Fmax"),
    "Rm": ("Zugfestigkeit Rm", "tensile strength Rm", "Rm"),
    "Fy": ("Kraft bei Fliessbeginn", "force at yield onset", "Fy"),
    "sy": ("Spannung bei Fliessbeginn", "stress at yield onset", "sy"),
    "E": ("Elastizitätsmodul E", "elastic modulus E", "E"),
    "Agt": ("Gesamtdehnung bei Höchstkraft Agt", "total extension at maximum force Agt", "Agt"),
    "Ag": ("Plastische Dehnung bei Höchstkraft Ag", "plastic extension at maximum force Ag", "Ag"),
    "At": ("Gesamtdehnung beim Bruch At", "total extension at fracture At", "At"),
    "A": ("Bruchdehnung A", "percentage elongation after fracture A", "A"),
}
MODEL_TEXT = {
    "Agt": "Agt = 100 · ΔL(Fmax) / L0", "At": "At = 100 · ΔL(Bruch) / L0",
    "Ag": "Ag = 100 · (ΔL(Fmax) − ΔL_el) / L0", "A": "A = 100 · (ΔL(Bruch) − ΔL_el) / L0",
}

# Modul-eigene Quellen (labcite-Format). Nicht am Original geprüft: so gekennzeichnet.
SOURCES = {
    "iso6892-1-anhj": {
        "type": "standard", "authors": "ISO", "year": "2019",
        "title": "ISO 6892-1:2019 Metallic materials – Tensile testing – Part 1: Method of test at room temperature, "
                 "Annex J: Estimation of the uncertainty of measurement",
        "container": "International Organization for Standardization",
        "note": "Anhang J (Messunsicherheit von Rm, ReH, ReL, Rp, A); Angaben nicht am Original geprüft"},
    "uncert-cop07": {
        "type": "report", "authors": "Gabauer, W.", "year": "2000",
        "title": "The Determination of Uncertainties in Tensile Testing",
        "container": "UNCERT Manual of Codes of Practice for the Determination of Uncertainties in Mechanical Tests on "
                     "Metallic Materials, Code of Practice 07",
        "note": "Ausgabe 1, EU-Projekt SMT4-CT97-2165; Angaben nicht am Original geprüft"},
}


def _un():
    """labcalc.uncertainty (SDK); ausserhalb des Hubs aus dem Suite-Ordner."""
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


def settings(cfg) -> dict | None:
    """Einstellungen aus Config.unc geprüft; None = keine Unsicherheitsauswertung."""
    u = getattr(cfg, "unc", None)
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
    specs = {}
    for key, sp in (u.get("specs") or {}).items():
        if key in FIELDS and isinstance(sp, dict) and isinstance(sp.get("parts"), list) and sp["parts"]:
            specs[key] = sp
    cls = lambda x: str(x).strip()[:80] if isinstance(x, str) and x.strip() else None  # noqa: E731
    return {"method": u.get("method") if u.get("method") in METHODS else "gum",
            "p": min(max(p, 0.5), 0.999), "k": k if (k and k > 0) else None,
            "lang": "en" if u.get("lang") == "en" else "de",
            "force_class": cls(u.get("force_class")), "ext_class": cls(u.get("ext_class")), "specs": specs}


def _parts(st, key) -> list:
    return [dict(p) for p in (st["specs"].get(key) or {}).get("parts") or [] if isinstance(p, dict)]


def _inp(name, value, unit, label, parts, note="") -> dict:
    return {"name": name, "value": float(value), "unit": unit, "label": label, "parts": [p for p in parts if p],
            **({"note": note} if note else {})}


def _field(st, key, value, lang) -> dict:
    nm, de, en, unit = FIELDS[key]
    return _inp(nm, value, unit, de if lang == "de" else en, _parts(st, key))


def _geometry(r, st, lang):
    """Eingangsgrössen des Querschnitts und S0 als Funktion (numpy-fähig), Formeltext."""
    c = r.config
    if c.a0_mm2 is not None and c.a0_mm2 > 0:
        return [_field(st, "a0", c.a0_mm2, lang)], (lambda v: v["S0"]), "S0 (direkt)" if lang == "de" else "S0 (entered)"
    if c.section == "rund":
        return [_field(st, "diameter_mm", c.diameter_mm, lang)], (lambda v: np.pi * v["d"] ** 2 / 4), "π d² / 4"
    if c.section == "rohr":
        return ([_field(st, "outer_d_mm", c.outer_d_mm, lang), _field(st, "wall_mm", c.wall_mm, lang)],
                (lambda v: np.pi / 4 * (v["D"] ** 2 - (v["D"] - 2 * v["t"]) ** 2)), "π/4 (D² − (D − 2t)²)")
    return ([_field(st, "width_mm", c.width_mm, lang), _field(st, "thickness_mm", c.thickness_mm, lang)],
            (lambda v: v["b"] * v["h"]), "b · h")


def _force_parts(r, st, lang) -> list:
    out = []
    if st["force_class"]:
        out.append({"kind": "instrument", "id": st["force_class"]})
    res = r.prep.resolution
    if res and math.isfinite(res) and res > 0:
        out.append({"kind": "resolution", "d": float(res),
                    "label": "Anzeigeauflösung der Kraft" if lang == "de" else "force display resolution"})
    return out


def _slope_se(r):
    """Standardfehler der Steigung des linearen Abschnitts (in Einheiten von y je s) und Punktzahl."""
    lo, hi = r.fit.lo, r.fit.hi
    x, y = np.asarray(r.t[lo:hi + 1], float), np.asarray(r.y[lo:hi + 1], float)
    n = len(x)
    if n < 3:
        return None, n
    res = y - (r.fit.k * x + r.fit.q)
    sxx = float(np.sum((x - x.mean()) ** 2))
    if sxx <= 0:
        return None, n
    se = math.sqrt(float(np.sum(res ** 2)) / (n - 2) / sxx)
    if se <= 1e-9 * abs(r.fit.k):         # exakte Gerade (synthetische Kurve): kein Typ-A-Beitrag
        return None, n
    return se, n


def _dl_parts(r, st, dl, lang, with_time=True) -> list:
    out = []
    if st["ext_class"]:
        out.append({"kind": "instrument", "id": st["ext_class"]})
    dt = r.prep.dt
    if with_time and r.v_mm_s and math.isfinite(dt) and dt > 0:
        out.append({"kind": "resolution", "d": float(dt * r.v_mm_s),
                    "label": "Zeitauflösung (ein Abtastintervall · v)" if lang == "de" else "time resolution (one sampling interval · v)"})
    return out


def _v_used(r) -> bool:
    """Geht die Unsicherheit von v in den Weg ein? Nicht, wenn die Zeitachse aus einem gemessenen Weg stammt."""
    o = r.device.get("origin") or {}
    return o.get("time_from") != "elongation"


def models(r, st, lang: str = "de") -> dict:
    """Name -> {f, inputs, unit, label, model, notes} für alle Kennwerte, die die Messung hat."""
    de = lang == "de"
    out = {}
    lab = lambda n: RESULTS[n][0 if de else 1]  # noqa: E731
    kv = r.kv
    geo, s0f, s0txt = _geometry(r, st, lang) if r.a0 else ([], None, "")
    Fparts = _force_parts(r, st, lang)
    Fmax = kv["max"]["F"]
    fin = _inp("F", Fmax, "N", "Höchstkraft Fmax" if de else "maximum force Fmax", Fparts)
    if r.a0:
        out["S0"] = {"f": s0f, "inputs": geo, "unit": "mm²", "label": lab("S0"), "model": "S0 = " + s0txt, "notes": []}
    out["Fmax"] = {"f": (lambda v: v["F"]), "inputs": [fin], "unit": "N", "label": lab("Fmax"), "model": "Fmax",
                   "notes": []}
    if r.a0:
        out["Rm"] = {"f": (lambda v: v["F"] / s0f(v)), "inputs": [fin] + geo, "unit": "MPa", "label": lab("Rm"),
                     "model": "Rm = Fmax / S0", "notes": []}
    y = kv.get("yield")
    if y:
        i = y["idx"]
        step = abs(float(r.force[i]) - float(r.force[i - 1])) if i > 0 else 0.0
        parts = list(Fparts)
        if step > 0:
            parts.append({"kind": "limits", "a": step / 2, "dist": "rect",
                          "label": "Lage im Abtastintervall (±½ Kraftschritt)" if de else "position within the sampling interval (±½ force step)"})
        fy = _inp("Fy", y["F"], "N", "Kraft bei Fliessbeginn" if de else "force at yield onset", parts)
        note = ("Fliessbeginn als Schwelle auf der Kraftkurve, keine Rp0,2: der Einfluss der Dehnungsmessung nach "
                "ISO 6892-1, Anhang J, entfällt." if de else
                "Yield onset is a threshold on the force curve, not Rp0.2: the influence of the strain measurement "
                "(ISO 6892-1, Annex J) does not apply.")
        if r.a0:
            out["sy"] = {"f": (lambda v: v["Fy"] / s0f(v)), "inputs": [fy] + geo, "unit": "MPa", "label": lab("sy"),
                         "model": "sy = Fy / S0", "notes": [note]}
        else:
            out["Fy"] = {"f": (lambda v: v["Fy"]), "inputs": [fy], "unit": "N", "label": lab("Fy"), "model": "Fy",
                         "notes": [note]}
    v0 = r.config.speed_mm_min
    use_v = _v_used(r) and v0
    vin = [_field(st, "speed_mm_min", v0, lang)] if use_v else []
    vr = (lambda v: v["v"] / v0) if use_v else (lambda v: 1.0)
    app = r.config.displacement_source != "probe"
    app_note = ("Weg nicht an der Probe gemessen: die Nachgiebigkeit des Aufbaus ist nicht in der Unsicherheit "
                "enthalten (Wert scheinbar)." if de else
                "Displacement not measured on the specimen: the compliance of the set-up is not part of the uncertainty "
                "(apparent value).")
    se, n = _slope_se(r)
    if r.e_schein_gpa is not None and r.a0 and r.l0 and r.v_mm_s:
        lo, hi = r.fit.lo, r.fit.hi
        dtw = float(r.t[hi] - r.t[lo])
        kN = r.fit.k * r.a0
        dparts = []
        if se is not None:
            dparts.append({"kind": "sd", "sd": se * r.a0 * dtw, "n": 1, "dof": max(1, n - 2),
                           "label": (f"Standardfehler der Steigung (Regression, n = {n})" if de else
                                     f"standard error of the slope (regression, n = {n})")})
        if st["force_class"]:
            dparts.append({"kind": "instrument", "id": st["force_class"]})
        dF = _inp("dF", kN * dtw, "N", "Kraftzunahme im Fitfenster ΔF" if de else "force increase in the fit window ΔF", dparts)
        dL = _inp("dLE", r.v_mm_s * dtw, "mm", "Verlängerung im Fitfenster ΔL" if de else "extension in the fit window ΔL",
                  _dl_parts(r, st, r.v_mm_s * dtw, lang, with_time=False))
        L0 = _field(st, "l0_mm", r.l0, lang)
        out["E"] = {"f": (lambda v: v["dF"] * v["L0"] / (s0f(v) * v["dLE"] * vr(v)) / 1000.0),
                    "inputs": [dF, dL, L0] + geo + vin, "unit": "GPa", "label": lab("E"),
                    "model": "E = ΔF · L0 / (S0 · ΔL) / 1000",
                    "notes": ([app_note] if app else []) + [
                        "Typ A aus dem Standardfehler der Steigung (n − 2 Freiheitsgrade)." if de else
                        "Type A from the standard error of the slope (n − 2 degrees of freedom)."]}
    if r.strain is not None and r.l0 and r.v_mm_s:
        L0 = _field(st, "l0_mm", r.l0, lang)
        m_e = r.fit.k * r.l0 / r.v_mm_s if (r.fit.k > 0 and (kv.get("ep") or {}).get("on", True)) else None
        pts = [("Agt", "At", r.imax, float(r.y[r.imax]), kv.get("Agt_pct"), "Ag", kv.get("Ag_pct"))]
        if r.break_idx is not None:
            pts.append(("At", None, r.break_idx, float(r.y[r.break_idx]), kv.get("At_pct"), "A", kv.get("A_pct")))
        t0_note = ("Fusspunkt t0 aus der Ausgleichsgeraden gilt als exakt." if de else
                   "Foot point t0 from the regression line is treated as exact.")
        for tot, _x, idx, yv, tot_val, pl, pl_val in pts:
            if tot_val is None:
                continue
            dl0 = float(r.t[idx] - r.t0) * r.v_mm_s
            if dl0 <= 0:
                continue
            nm = "dLm" if tot == "Agt" else "dLb"
            lbl = (("Verlängerung bei Höchstkraft ΔL" if tot == "Agt" else "Verlängerung beim Bruch ΔL") if de else
                   ("extension at maximum force ΔL" if tot == "Agt" else "extension at fracture ΔL"))
            dl = _inp(nm, dl0, "mm", lbl, _dl_parts(r, st, dl0, lang))
            notes = ([app_note] if app else []) + [t0_note]
            out[tot] = {"f": (lambda v, nm=nm: 100.0 * v[nm] * vr(v) / v["L0"]), "inputs": [dl, L0] + vin,
                        "unit": "%", "label": lab(tot), "model": MODEL_TEXT[tot], "notes": notes}
            if pl_val is not None and m_e:
                el0 = yv / m_e * r.l0                                 # elastische Verlängerung in mm
                eparts = []
                if se is not None and r.fit.k > 0:
                    eparts.append({"kind": "sd", "sd": abs(el0) * se / r.fit.k, "n": 1, "dof": max(1, n - 2),
                                   "label": (f"Steigung des linearen Abschnitts (Typ A, n = {n})" if de else
                                             f"slope of the linear section (type A, n = {n})")})
                el = _inp(nm + "el", el0, "mm", "elastischer Anteil ΔL_el" if de else "elastic part ΔL_el", eparts)
                out[pl] = {"f": (lambda v, nm=nm: 100.0 * (v[nm] - v[nm + "el"]) * vr(v) / v["L0"]),
                           "inputs": [dl, el, L0] + vin, "unit": "%", "label": lab(pl), "model": MODEL_TEXT[pl],
                           "notes": notes}
    return out


def _refs_text(lang) -> list[str]:
    try:
        import labcite
        return [labcite.text(rec, lang) for rec in SOURCES.values()]
    except ImportError:
        return [rec["title"] for rec in SOURCES.values()]


def _zero(res: dict) -> bool:
    """Ergebnis ohne jede Unsicherheit (u = 0 und U = 0) wird nicht gezeigt."""
    return not (res.get("u") or 0) > 0 and not (res.get("U") or 0) > 0


def evaluate_all(r, lang: str | None = None) -> dict | None:
    """Unsicherheit aller Kennwerte nach dem gewählten Verfahren. Rückgabe {"settings", "results": {Name: Ergebnis}}."""
    st = settings(r.config)
    if st is None:
        return None
    lang = lang or st["lang"]
    UN = _un()
    try:
        ms = models(r, st, lang)
    except Exception as e:  # noqa: BLE001 – Fehler gehören zur Unsicherheit, nie zur Auswertung
        return {"settings": st, "results": {}, "error": str(e)}
    out = {}
    for name, m in ms.items():
        try:
            res = UN.evaluate(m["f"], m["inputs"], st["method"], p=st["p"], k=st["k"], lang=lang, unit=m["unit"],
                              label=m["label"], name=name)
        except (UN.UncError, ValueError, ZeroDivisionError, FloatingPointError) as e:
            out[name] = {"name": name, "label": m["label"], "error": str(e)}
            continue
        if _zero(res):
            continue                                  # hängt von keiner unsicheren Eingabe ab
        res["model"] = m["model"]
        res["note_texts"] = list(res.get("note_texts") or []) + m["notes"]
        res["refs_full"] = list(dict.fromkeys(_refs_text(lang) + list(res.get("refs_full") or [])))
        out[name] = res
    return {"settings": st, "results": out}


def compare(r, name: str, lang: str | None = None) -> dict:
    """Alle vier Verfahren für einen Kennwert (Seite: „Verfahren vergleichen“)."""
    st = settings(r.config)
    if st is None:
        raise ValueError("Keine Messunsicherheit eingestellt")
    lang = lang or st["lang"]
    m = models(r, st, lang).get(name)
    if m is None:
        raise ValueError(f"Kennwert {name} hat keine Unsicherheit")
    return _un().compare(m["f"], m["inputs"], p=st["p"], k=st["k"], lang=lang, unit=m["unit"], label=m["label"],
                         name=name)


def var_u(r) -> dict:
    """Variable der eigenen Gleichungen -> Standardunsicherheit (für die Fortpflanzung und den Wertekatalog)."""
    out = {}
    if not r.unc:
        return out
    meth = r.unc["settings"]["method"]
    for name, res in (r.unc.get("results") or {}).items():
        if res.get("error") or res.get("u") is None:
            continue
        out[RESULTS[name][2]] = {"u": float(res["u"]), "unc_method": meth}
    st = r.unc["settings"]
    UN = _un()
    for key, var, val in (("l0_mm", "L0", r.l0), ("speed_mm_min", "v", r.config.speed_mm_min)):
        if val and st["specs"].get(key):
            try:
                x = UN.make_input({"name": var, "value": val, "parts": _parts(st, key)}, st["lang"])
            except UN.UncError:
                continue
            if x["u"] > 0:
                out[var] = {"u": float(x["u"]), "unc_method": meth}
    return out


def point_value(r, name):
    """Kennwert der Auswertung (nicht der Mittelwert der Monte-Carlo-Stichprobe)."""
    kv = r.kv
    return {"S0": r.a0, "Fmax": kv["max"]["F"], "Rm": kv.get("Rm"), "Fy": (kv.get("yield") or {}).get("F"),
            "sy": (kv.get("yield") or {}).get("y") if r.a0 else None, "E": r.e_schein_gpa, "Agt": kv.get("Agt_pct"),
            "Ag": kv.get("Ag_pct"), "At": kv.get("At_pct"), "A": kv.get("A_pct")}.get(name)


def series(results, lang: str = "de") -> dict:
    """Mehrere Proben einer Serie: Mittelwert ± Unsicherheit je Kennwert.

    Typ A aus der Streuung der Einzelwerte (s/√n, n − 1 Freiheitsgrade); dazu der Mittelwert der Einzelunsicherheiten
    als voll korreliert angenommener Beitrag (dieselben Messmittel; konservativ, weil die zufälligen Anteile der
    Einzelbudgets schon in der Streuung stecken). Rückgabe Name -> Ergebnis (nur mit mindestens zwei Proben)."""
    withu = [r for r in results if getattr(r, "unc", None) and r.unc.get("results")]
    if len(withu) < 2:
        return {}
    UN = _un()
    st = withu[0].unc["settings"]
    de = lang == "de"
    out = {}
    for name in RESULTS:
        rows = [(point_value(r, name), (r.unc["results"].get(name) or {}).get("u")) for r in withu]
        rows = [(v, u) for v, u in rows if v is not None and u is not None]
        if len(rows) < 2:
            continue
        vals = [float(v) for v, _ in rows]
        ub = float(np.mean([u for _, u in rows]))
        unit = withu[0].unc["results"][name].get("unit", "")
        ins = [{"name": "m", "value": float(np.mean(vals)), "unit": unit,
                "label": f"Mittelwert der Proben (n = {len(vals)})" if de else f"mean of the specimens (n = {len(vals)})",
                "parts": [{"kind": "repeats", "values": vals,
                           "label": "Streuung der Proben (Typ A)" if de else "scatter of the specimens (type A)"}]},
               {"name": "dB", "value": 0.0, "unit": unit,
                "label": "Einzelunsicherheit (Mittel, voll korreliert)" if de else "single-test uncertainty (mean, fully correlated)",
                "parts": [{"kind": "u", "u": ub, "label": "Mittel der Einzelbudgets" if de else "mean of the single budgets"}]}]
        lbl = RESULTS[name][0 if de else 1] + (" (Serie)" if de else " (series)")
        try:
            res = UN.evaluate(lambda v: v["m"] + v["dB"], ins, st["method"], p=st["p"], k=st["k"], lang=lang, unit=unit,
                              label=lbl, name=name)
        except UN.UncError:
            continue
        if _zero(res):
            continue
        res["n"] = len(vals)
        res["sd"] = float(np.std(vals, ddof=1))
        res["note_texts"] = list(res.get("note_texts") or []) + [
            "Mittelwert der Einzelunsicherheiten als voll korreliert angenommen (konservativ)." if de else
            "Mean single-test uncertainty treated as fully correlated (conservative)."]
        out[name] = res
    return out


def pm_text(res: dict, lang: str = "de") -> str:
    """„140 ± 3 MPa“ bzw. das Intervall (Monte Carlo, Grösstfehler) für PDF und Tabellen."""
    if not res or res.get("error"):
        return "–"
    return res.get("text") or ""


# ------------------------------------------------------------------------------------------------ Bericht
def to_report(b, r, lang: str = "de", prefix: str = "") -> dict | None:
    """Unsicherheit der Kennwerte in ein Bundle: Werte (<Name>-pm, -u, -U), Budgettabellen, Methodentext (zitiert
    ISO 6892-1 Anhang J und UNCERT CoP 07 neben JCGM/DIN/Taylor und den Messmitteln). None ohne Einstellung."""
    import labcite
    from labbundle import cite

    unc = evaluate_all(r, lang)
    if not unc:
        return None
    res = [x for x in unc["results"].values() if not x.get("error")]
    if not res:
        return None
    UN = _un()
    uo = UN.to_report(b, res, lang, prefix)
    keys = [labcite.to_bib(b, k, rec) for k, rec in SOURCES.items()]
    st = unc["settings"]
    de = lang == "de"
    names = tex_safe(", ".join(x["label"] for x in res))
    dev = []
    if st["force_class"]:
        dev.append(("Kraftmesseinrichtung " if de else "force-measuring system ") + _iname(st["force_class"], lang))
    if st["ext_class"]:
        dev.append(("Längenänderungs-Messeinrichtung " if de else "extensometer ") + _iname(st["ext_class"], lang))
    head = (f"Für {names} wurde die Messunsicherheit aus Modellgleichungen nach ISO 6892-1, Anhang J, und dem UNCERT "
            f"Code of Practice 07{cite(keys)} bestimmt: $R_m = F_\\mathrm{{max}}/S_0$ mit $S_0$ aus den gemessenen "
            "Abmessungen, der Modul aus Kraft- und Wegzunahme im linearen Abschnitt (Typ A aus dem Standardfehler der "
            "Steigung), die Dehnungen aus der Verlängerung bezogen auf $L_0$." if de else
            f"For {names} the measurement uncertainty was evaluated from model equations following ISO 6892-1, Annex J, "
            f"and the UNCERT Code of Practice 07{cite(keys)}: $R_m = F_\\mathrm{{max}}/S_0$ with $S_0$ from the measured "
            "dimensions, the modulus from the force and extension increase in the linear section (type A from the "
            "standard error of the slope), the extensions from the elongation related to $L_0$.")
    if dev:
        head += (" Berücksichtigt: " if de else " Included: ") + "; ".join(tex_safe(d) for d in dev) + "."
    head += (" $R_{eH}$, $R_{eL}$ und $R_{p0,2}$ bestimmt das Modul nicht; der Fliessbeginn ist eine Schwelle auf der "
             "Kraftkurve, sein Budget enthält die Lage im Abtastintervall statt des Einflusses der Dehnungsmessung."
             if de else
             " $R_{eH}$, $R_{eL}$ and $R_{p0.2}$ are not determined by the module; the yield onset is a threshold on the "
             "force curve, its budget contains the position within the sampling interval instead of the influence of the "
             "strain measurement.")
    if r.config.displacement_source != "probe":
        head += (" Der Weg wurde nicht an der Probe gemessen; die Nachgiebigkeit des Aufbaus ist nicht in der "
                 "Unsicherheit enthalten." if de else
                 " The displacement was not measured on the specimen; the compliance of the set-up is not part of the "
                 "uncertainty.")
    return {"values": uo["values"], "tables": uo["tables"], "cites": list(dict.fromkeys(keys + uo["cites"])),
            "latex": head + "\n" + uo["latex"], "results": {x["name"]: x for x in res}}


def _iname(iid: str, lang: str) -> str:
    try:
        it = _un().instrument(iid)
    except Exception:  # noqa: BLE001
        return iid
    nm = it.get("name")
    return (nm.get(lang) or nm.get("de")) if isinstance(nm, dict) else str(nm or iid)


def tex_safe(s: str) -> str:
    from labbundle import tex_escape
    return tex_escape(s)
