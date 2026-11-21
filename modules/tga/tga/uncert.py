"""Messunsicherheit der TGA-Ergebnisse (Massenverluste, Rückstand, charakteristische Temperaturen, Zusammensetzung,
Gehalte, Wiederholungen, Kinetik).

Arbeitsstand (je Lauf, von der Seite für alle Läufe gleich gesendet)::

    state["unc"] = {key: {"parts": [...]}}          wie LabUnc.all(); Schlüssel siehe KEYS
    state["unc_method"] = {"method": "gum"|"mc"|"gauss"|"worst", "p": 0.95, "k": None}

Modelle (je Ergebnis eines, alle Eingangsgrössen darin gemeinsam, damit z. B. m₀ in Zähler und Nenner richtig wirkt):

* Massenverlust einer Stufe   L = 100 · (m_a − m_b + δ_Drift) / m₀          (m_a, m_b: TGA-Waage an den Stufengrenzen)
* Rückstand                   R = 100 · (m_E + δ_Drift) / m₀
* Zusammensetzung             X = 100 · (m_P − m_Q + δ_Drift) / B,  m_i = m_i + s_i · (T_i − T_i,nom)
                              (B = m₀ bzw. bei ASTM D7582 die Masse am Start; s_i örtliche Steigung an einer
                              Temperaturgrenze, T_i mit Kalibrier- und Fühlerunsicherheit)
* Gehalt aus Stöchiometrie    X = 100 · L / L_theor
* Temperatur (T_x %, Onset, Endset, DTG-Spitze)
                              T = T_Ablesung + δT_Kal + δT_Auswertung
                              δT_Auswertung: Tangentenkonstruktion (Onset/Endset), Massenunsicherheit über die örtliche
                              Steigung (T_x %, Onset/Endset), Interpolation bzw. Abtastung (Punktabstand).

Grundlage: GUM (JCGM 100:2008) und GUM S1 (JCGM 101:2008) über ``labcalc.uncertainty``; Onset/Endset nach
ISO 11358-1; Temperaturkalibrierung nach ASTM E1582, Massenkalibrierung nach ASTM E2040.
"""
from __future__ import annotations

import math

import numpy as np

try:
    from labcalc import uncertainty as UN
except ImportError:  # Modul ausserhalb von Folio Lab
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "sdk" / "python"))
    from labcalc import uncertainty as UN

KEYS = ("m0", "bal", "drift", "T_cal", "T_tc", "beta")

L10N = {
    "de": {"m0": "Einwaage m₀", "ref": "Bezugsmasse (TGA-Waage)", "ma": "Masse am Stufenbeginn (TGA-Waage)",
           "mb": "Masse am Stufenende (TGA-Waage)", "me": "Masse am Ende (TGA-Waage)", "drift": "Drift / Auftrieb",
           "T": "Temperaturablesung (Fühler)", "Tcal": "Temperaturkalibrierung", "Teval": "Auswertung",
           "slope": "Massenunsicherheit über die Steigung |dm/dT| = {s} %/K", "interp": "Interpolation (Punktabstand {d} K)",
           "sample": "Abtastung (Punktabstand {d} K)", "tang": "Tangentenkonstruktion (Wendepunkt ±{n} Punkte)",
           "base": "Massenablesung an der Basislinie",
           "loss": "Verlust Stufe {i}", "onset": "Onset Stufe {i}", "peak": "DTG-Spitze Stufe {i}", "endset": "Endset Stufe {i}",
           "tl": "T bei {L} % Verlust", "res": "Rückstand am Ende", "Tb": "Temperaturgrenze {T} °C", "start": "Masse am Start",
           "rd": "Masse bei {T}", "rep_A": "Wiederholungen (Typ A)", "rep_B": "Typ B (Mittel der Einzelbudgets)",
           "rep": "{l} (Mittel aus {n} Läufen)", "kin": "Vertrauensbereich der Regression ({n} Heizraten)",
           "ea": "Eₐ {m}", "ea_a": "Eₐ {m} (α = {a})", "no_ref": "Einwaage unbekannt: Massenbudgets nicht möglich.",
           "bad": "{k}: {e}"},
    "en": {"m0": "Sample mass m₀", "ref": "Reference mass (TGA balance)", "ma": "Mass at step start (TGA balance)",
           "mb": "Mass at step end (TGA balance)", "me": "Mass at the end (TGA balance)", "drift": "Drift / buoyancy",
           "T": "Temperature reading (sensor)", "Tcal": "Temperature calibration", "Teval": "Evaluation",
           "slope": "Mass uncertainty through the slope |dm/dT| = {s} %/K", "interp": "Interpolation (point spacing {d} K)",
           "sample": "Sampling (point spacing {d} K)", "tang": "Tangent construction (inflection point ±{n} points)",
           "base": "Mass reading at the baseline",
           "loss": "Loss step {i}", "onset": "Onset step {i}", "peak": "DTG peak step {i}", "endset": "Endset step {i}",
           "tl": "T at {L} % loss", "res": "Residue at the end", "Tb": "Temperature limit {T} °C", "start": "Mass at start",
           "rd": "Mass at {T}", "rep_A": "Repeats (type A)", "rep_B": "Type B (mean of the single budgets)",
           "rep": "{l} (mean of {n} runs)", "kin": "Confidence interval of the regression ({n} heating rates)",
           "ea": "Eₐ {m}", "ea_a": "Eₐ {m} (α = {a})", "no_ref": "Sample mass unknown: no mass budgets.",
           "bad": "{k}: {e}"},
}


def specs(state: dict) -> dict:
    u = (state or {}).get("unc")
    if not isinstance(u, dict):
        return {}
    return {k: v for k, v in u.items() if isinstance(v, dict) and isinstance(v.get("parts"), list) and v["parts"]}


def active(state: dict) -> bool:
    s = specs(state)
    return any(k in s for k in KEYS)


def method(state: dict) -> dict:
    m = (state or {}).get("unc_method") or {}
    meth = m.get("method") if m.get("method") in UN.METHODS else "gum"
    try:
        p = float(m.get("p") or UN.P_DEFAULT)
    except (TypeError, ValueError):
        p = UN.P_DEFAULT
    k = m.get("k")
    try:
        k = float(k) if k not in (None, "", 0) else None
    except (TypeError, ValueError):
        k = None
    return {"method": meth, "p": p, "k": k}


def _inp(name, value, unit, label, spec=None, extra=()):
    parts = list((spec or {}).get("parts") or []) + [p for p in extra if p]
    d = {"name": name, "value": float(value), "unit": unit, "label": label, "parts": parts}
    if spec and spec.get("dof") not in (None, "", "inf"):
        d["dof"] = spec["dof"]
    return d


def _u(spec, value, unit="") -> float:
    """Standardunsicherheit einer Angabe bei einem Wert (0 ohne Angabe)."""
    if not spec:
        return 0.0
    try:
        return float(UN.make_input({"name": "x", "value": value, "unit": unit, "parts": spec.get("parts") or []})["u"])
    except UN.UncError:
        return 0.0


class Ctx:
    """Gemeinsame Grössen eines Laufs für alle Budgets."""

    def __init__(self, a, state: dict, lang: str):
        self.a, self.lang = a, lang
        self.L = L10N.get(lang, L10N["de"])
        self.s = specs(state)
        self.m = method(state)
        r = a.run
        self.ref_from_tga = bool(r.meta.get("ref_mg"))
        self.ref = float(r.meta.get("ref_mg") or r.m0) if (r.meta.get("ref_mg") or r.m0) else None
        self.notes: list[str] = []
        self.u_bal = _u(self.s.get("bal"), (self.ref or 0.0), "mg")
        self.u_drift = _u(self.s.get("drift"), 0.0, "mg")
        self.u_ref = _u(self.s.get("bal") if self.ref_from_tga else self.s.get("m0"), self.ref or 0.0, "mg")
        self.T = r.T
        d = a.st.get("dtg") or {}
        self.dmdT = np.asarray(d.get("dT"), float) if d.get("dT") is not None else None
        self.results: list[dict] = []

    # ------------------------------------------------------------------ Auswertung
    def ev(self, model, ins, rid, label, unit, group):
        try:
            r = UN.evaluate(model, ins, self.m["method"], p=self.m["p"], k=self.m["k"], lang=self.lang, unit=unit,
                            label=label, name=rid)
        except (UN.UncError, ValueError, ZeroDivisionError, FloatingPointError) as e:
            self.notes.append(self.L["bad"].format(k=label, e=e))
            return None
        if not r.get("uncertain_n"):
            return None
        u = r.get("u")
        if u is None:                                     # Grösstfehler: Standardunsicherheit für Weitergabe nach Gauss
            try:
                u = UN.evaluate(model, ins, "gauss", lang=self.lang)["u"]
            except UN.UncError:
                u = None
        if not u and not r.get("U"):                      # nichts Unsicheres: kein Budget
            return None
        out = {"id": rid, "group": group, "label": label, "unit": unit, "value": r["value"], "u": u, "res": r}
        self.results.append(out)
        return out

    def ref_input(self):
        L = self.L
        if self.ref_from_tga:
            return _inp("m0", self.ref, "mg", L["ref"], self.s.get("bal"))
        return _inp("m0", self.ref, "mg", L["m0"], self.s.get("m0"))

    def mg(self, pct):
        return float(pct) / 100.0 * self.ref

    def u_mass_pct(self, level=None) -> float:
        """Standardunsicherheit einer Massenablesung in % (Waage, Drift; bei Verlustschwellen auch m₀)."""
        if not self.ref:
            return 0.0
        u2 = 2 * (100 * self.u_bal / self.ref) ** 2 + (100 * self.u_drift / self.ref) ** 2
        if level:
            u2 += (float(level) * self.u_ref / self.ref) ** 2
        return math.sqrt(u2)

    def spacing(self, i) -> float:
        T = self.T
        n = len(T)
        i = int(min(max(i, 1), n - 1))
        return float(abs(T[i] - T[i - 1])) or float(abs(np.median(np.diff(T[: min(n, 50)])))) or 1.0

    def slope(self, i) -> float | None:
        """dm/dT in %/K an Index i (DTG der Auswertung)."""
        if self.dmdT is None or not (0 <= i < len(self.dmdT)) or not np.isfinite(self.dmdT[i]):
            return None
        return float(self.dmdT[i])

    def temp(self, T, rid, label, eval_parts):
        L = self.L
        ins = [_inp("T_meas", T, "°C", L["T"], self.s.get("T_tc")),
               _inp("dT_cal", 0.0, "K", L["Tcal"], self.s.get("T_cal")),
               _inp("dT_eval", 0.0, "K", L["Teval"], None, eval_parts)]
        return self.ev(lambda v: v["T_meas"] + v["dT_cal"] + v["dT_eval"], ins, rid, label, "°C", "temps")


def _gl(v):
    return f"{float(v):.3g}".replace(".", ",")


def _idx(T, v):
    k = np.nonzero(np.asarray(T) >= float(v))[0]
    return int(k[0]) if len(k) else len(T) - 1


# ============================================================================== Budgets eines Laufs
def evaluate(a, state: dict, lang: str = "de") -> dict | None:
    """Alle Budgets eines Laufs; None, wenn keine Unsicherheit angegeben ist."""
    if not active(state):
        return None
    c = Ctx(a, state, lang)
    L = c.L
    r = a.run
    s = c.s
    loss_models = {}
    # ---------------------------------------------------------------- Massenverluste der Stufen
    if c.ref:
        for st in a.steps:
            i = st["no"]
            ins = [c.ref_input(), _inp("m_a", c.mg(st["m_start"]), "mg", L["ma"], s.get("bal")),
                   _inp("m_b", c.mg(st["m_end"]), "mg", L["mb"], s.get("bal")),
                   _inp("d_drift", 0.0, "mg", L["drift"], s.get("drift"))]

            def f(v):
                return 100.0 * (v["m_a"] - v["m_b"] + v["d_drift"]) / v["m0"]
            loss_models[i] = (f, ins)
            c.ev(f, ins, f"step{i}-loss", L["loss"].format(i=i), "%", "steps")
        res = a.st.get("residue") or {}
        if res.get("end") is not None:
            ins = [c.ref_input(), _inp("m_E", c.mg(res["end"]), "mg", L["me"], s.get("bal")),
                   _inp("d_drift", 0.0, "mg", L["drift"], s.get("drift"))]
            c.ev(lambda v: 100.0 * (v["m_E"] + v["d_drift"]) / v["m0"], ins, "residue", L["res"], "%", "char")
    elif any(k in s for k in ("m0", "bal", "drift")):
        c.notes.append(L["no_ref"])
    # ---------------------------------------------------------------- Temperaturen der Stufen
    if r.has_T:
        for st in a.steps:
            if st.get("x") != "T":
                continue
            i = st["no"]
            for key, which in (("T_onset", "onset"), ("T_endset", "endset")):
                if st.get(key) is None:
                    continue
                c.temp(st[key], f"step{i}-{which}", L[which].format(i=i), _tangent_parts(c, st, which))
            if st.get("T_peak") is not None:
                p = _idx(r.T, st["T_peak"])
                c.temp(st["T_peak"], f"step{i}-peak", L["peak"].format(i=i),
                       [{"kind": "resolution", "d": c.spacing(p), "label": L["sample"].format(d=_gl(c.spacing(p)))}])
        for lv, x in (a.st.get("loss_T") or {}).items():
            if not x or x.get("T") is None:
                continue
            j = _idx(r.T, x["T"])
            parts = [{"kind": "resolution", "d": c.spacing(j), "label": L["interp"].format(d=_gl(c.spacing(j)))}]
            sl = c.slope(j)
            um = c.u_mass_pct(float(lv))
            if sl and abs(sl) > 1e-9 and um > 0:
                parts.append({"kind": "u", "u": um / abs(sl), "label": L["slope"].format(s=_gl(abs(sl)))})
            c.temp(x["T"], f"t{lv}", L["tl"].format(L=lv), parts)
    # ---------------------------------------------------------------- Zusammensetzung
    comp = a.comp
    if comp and comp.get("rows") and comp.get("_read") and c.ref:
        _composition(c, comp)
    # ---------------------------------------------------------------- Gehalte aus Stöchiometrie
    for n, rx in enumerate(a.reactions, 1):
        m = loss_models.get(rx.get("step"))
        if not m or not rx.get("theory"):
            continue
        f0, ins = m
        th = float(rx["theory"])
        c.ev(lambda v, f0=f0, th=th: 100.0 * f0(v) / th, ins, f"content{n}", rx["label"], "%", "comp")
    return {"method": c.m, "results": c.results, "notes": c.notes, "keys": sorted(s)}


def _tangent_parts(c: Ctx, st: dict, which: str) -> list[dict]:
    """Beiträge der Auswertung zu Onset bzw. Endset: Lage der Wendetangente, Massenablesung, Abtastung."""
    L = c.L
    r = c.a.run
    T = r.T
    m = r.pct()
    a_, b_ = int(st["a"]), int(st["b"])
    out = []
    q = _idx(T, st.get("T_inflection", st["T_peak"])) if st.get("T_inflection") is not None else _idx(T, st["T_peak"])
    q = min(max(q, a_), b_)
    base = st.get("base_pre" if which == "onset" else "base_post") or [0.0, m[a_]]
    ref_val = st.get("T_onset" if which == "onset" else "T_endset")
    if c.dmdT is not None and ref_val is not None:
        g = -c.dmdT[a_:b_ + 1]
        if np.isfinite(g).any() and np.nanmax(g) > 0:
            gq = g[q - a_]
            near = [k for k in range(max(a_, q - 50), min(b_, q + 50) + 1) if np.isfinite(g[k - a_]) and g[k - a_] >= 0.9 * gq]
            lo_k, hi_k = (min(near), max(near)) if near else (q, q)
            if hi_k - lo_k < 2:
                lo_k, hi_k = max(a_, q - 1), min(b_, q + 1)
            vals = []
            for k in range(lo_k, hi_k + 1):
                s_ = c.slope(k)
                if not s_ or abs(s_ - base[0]) < 1e-12:
                    continue
                x = (base[1] - (m[k] - s_ * T[k])) / (s_ - base[0])
                if np.isfinite(x):
                    vals.append(float(x))
            if len(vals) >= 2:
                half = (max(vals) - min(vals)) / 2
                if half > 0:
                    out.append({"kind": "limits", "a": half, "dist": "rect",
                                "label": L["tang"].format(n=max(q - lo_k, hi_k - q))})
            um = c.u_mass_pct()
            tang = st.get("tangent") or [None]
            if um > 0 and tang[0] and abs(tang[0] - base[0]) > 1e-12:
                out.append({"kind": "u", "u": um / abs(tang[0] - base[0]), "label": L["base"]})
    out.append({"kind": "resolution", "d": c.spacing(q), "label": L["sample"].format(d=_gl(c.spacing(q)))})
    return out


def _composition(c: Ctx, comp: dict):
    L = c.L
    s = c.s
    rd = comp["_read"]
    uT = bool(s.get("T_cal") or s.get("T_tc"))

    def reading(key):
        x = rd[key]
        lab = L["start"] if key == "S" else (L["rd"].format(T=f"{x['T']:g} °C") if x.get("T") is not None else
                                              (L["me"] if key == "E" else key))
        ins = [_inp(f"m_{key}", c.mg(x["pct"]), "mg", lab, s.get("bal"))]
        slope_mg = 0.0
        if x.get("T") is not None and x.get("i") is not None and uT:
            sl = c.slope(int(x["i"]))
            if sl:
                slope_mg = sl / 100.0 * c.ref
                parts = list((s.get("T_cal") or {}).get("parts") or []) + list((s.get("T_tc") or {}).get("parts") or [])
                ins.append({"name": f"T_{key}", "value": float(x["T"]), "unit": "°C",
                            "label": L["Tb"].format(T=f"{x['T']:g}"), "parts": parts})
        return ins, slope_mg

    for n, row in enumerate(comp["rows"], 1):
        t = row.get("_terms")
        if not t:
            continue
        ins = [c.ref_input()] if t.get("basis") != "S" else []
        terms = {}
        need = [t.get("plus"), t.get("minus"), "S" if t.get("basis") == "S" else None]
        for key in need:
            if not key or key in terms or key not in rd:
                continue
            ii, sl = reading(key)
            ins += ii
            terms[key] = (float(rd[key]["T"]) if rd[key].get("T") is not None else None, sl)
        if t.get("plus") not in terms or (t.get("minus") and t["minus"] not in terms):
            continue
        ins.append(_inp("d_drift", 0.0, "mg", L["drift"], s.get("drift")))

        def M(v, key, terms=terms):
            T0, sl = terms[key]
            val = v[f"m_{key}"]
            if sl and f"T_{key}" in v:
                val = val + sl * (v[f"T_{key}"] - T0)
            return val

        def f(v, t=t, M=M):
            num = M(v, t["plus"]) - (M(v, t["minus"]) if t.get("minus") else 0.0) + v["d_drift"]
            den = M(v, "S") if t.get("basis") == "S" else v["m0"]
            return 100.0 * num / den
        c.ev(f, ins, f"comp{n}", row["name"], "%", "comp")


# ============================================================================== Weitergabe
VAR_OF = {"loss": "L{i}", "onset": "Ton{i}", "peak": "Tp{i}", "endset": "Tend{i}"}


def variables_u(variables: dict, unc: dict | None, state: dict):
    """Standardunsicherheiten an die Variablen der eigenen Gleichungen hängen (Weitergabe, Projektindex)."""
    if not unc:
        return
    by = {r["id"]: r for r in unc["results"]}

    def put(var, rid):
        r = by.get(rid)
        if var in variables and r and r.get("u"):
            variables[var]["u"] = float(r["u"])
            variables[var]["unc"] = {"method": unc["method"]["method"], **UN.plain(r["res"])}
    for rid in by:
        if rid.startswith("step"):
            no, _, kind = rid[4:].partition("-")
            if kind in VAR_OF:
                put(VAR_OF[kind].format(i=no), rid)
        elif rid.startswith("t") and rid[1:].isdigit():
            put(f"T{rid[1:]}", rid)
        elif rid == "residue":
            put("res", rid)
        elif rid.startswith("comp"):
            put(f"C{rid[4:]}", rid)
        elif rid.startswith("content"):
            put(f"X{rid[7:]}", rid)
    sp = specs(state)
    for var, key, unit in (("m0", "m0", "mg"), ("beta", "beta", "K/min")):
        if var in variables and key in sp:
            u = _u(sp[key], variables[var]["value"], unit)
            if u > 0:
                variables[var]["u"] = u
    # Verlust in mg: Differenz zweier Ablesungen mit Drift
    sb, sd = sp.get("bal"), sp.get("drift")
    if sb or sd:
        for k, v in variables.items():
            if k.startswith("Lmg") and isinstance(v, dict):
                u = math.sqrt(2 * _u(sb, v["value"], "mg") ** 2 + _u(sd, 0.0, "mg") ** 2)
                if u > 0:
                    v["u"] = u


def plain(unc: dict | None) -> dict:
    """{id: {value, u, U, k, p, method, text}} für die Seite und geteilte Werte."""
    out = {}
    for r in (unc or {}).get("results") or []:
        res = r["res"]
        out[r["id"]] = {"value": r["value"], "u": r.get("u"), "U": res.get("U"), "text": res.get("text"),
                        "method": res.get("method")}
    return out


# ============================================================================== Wiederholungen (Typ A)
def replicate_keys(analyses) -> list[tuple[str, str, str]]:
    """Kennwerte, die alle Läufe haben: (Schlüssel, Bezeichnung, Einheit)."""
    def keys(a):
        out = {}
        for st in a.steps:
            i = st["no"]
            out[f"step{i}-loss"] = (st["loss"], "loss", i, "%")
            if st.get("x") == "T" and st.get("T_peak") is not None:
                out[f"step{i}-peak"] = (st["T_peak"], "peak", i, "°C")
            if st.get("x") == "T" and st.get("T_onset") is not None:
                out[f"step{i}-onset"] = (st["T_onset"], "onset", i, "°C")
        for lv, x in (a.st.get("loss_T") or {}).items():
            if x and x.get("T") is not None:
                out[f"t{lv}"] = (x["T"], "tl", lv, "°C")
        res = a.st.get("residue") or {}
        if res.get("end") is not None:
            out["residue"] = (res["end"], "res", None, "%")
        for n, row in enumerate((a.comp or {}).get("rows") or [], 1):
            out[f"comp{n}"] = (row["pct"], "comp", row["name"], "%")
        return out
    ks = [keys(a) for a in analyses]
    common = [k for k in ks[0] if all(k in x for x in ks[1:])]
    return [(k, ks[0][k][1], ks[0][k][2], ks[0][k][3]) for k in common], ks


def replicates(analyses, state: dict, lang: str = "de") -> dict:
    """Mittelwert ± U aus Wiederholungen derselben Probe: Typ A (s/√n, n − 1 Freiheitsgrade) und, wo die einzelnen
    Läufe ein Budget haben, Typ B als Mittel ihrer Standardunsicherheiten (systematisch, durch Mittelung nicht kleiner)."""
    L = L10N.get(lang, L10N["de"])
    m = method(state)
    if len(analyses) < 2:
        return {"results": [], "n": len(analyses), "method": m}
    common, ks = replicate_keys(analyses)
    per_run = [{r["id"]: r for r in ((a.unc or {}).get("results") or [])} for a in analyses]
    out = []
    for key, kind, arg, unit in common:
        xs = [float(k[key][0]) for k in ks]
        if not all(np.isfinite(xs)):
            continue
        label = (L[kind].format(i=arg) if kind in ("loss", "peak", "onset") else L["tl"].format(L=arg) if kind == "tl"
                 else L["res"] if kind == "res" else str(arg))
        parts = [{"kind": "repeats", "values": xs, "label": L["rep_A"]}]
        ub = [pr[key]["u"] for pr in per_run if key in pr and pr[key].get("u")]
        if len(ub) == len(analyses):
            parts.append({"kind": "u", "u": float(np.mean(ub)), "label": L["rep_B"]})
        if np.ptp(xs) == 0 and len(parts) == 1:
            continue
        ins = [{"name": "x", "value": float(np.mean(xs)), "unit": unit, "label": label, "parts": parts}]
        lab = L["rep"].format(l=label, n=len(xs))
        try:
            r = UN.evaluate(lambda v: v["x"], ins, m["method"], p=m["p"], k=m["k"], lang=lang, unit=unit, label=lab,
                            name=f"rep-{key}")
        except UN.UncError:
            continue
        out.append({"id": f"rep-{key}", "label": lab, "unit": unit, "value": r["value"], "u": r.get("u"),
                    "n": len(xs), "values": xs, "typeB": bool(len(parts) > 1), "res": r})
    return {"results": out, "n": len(analyses), "method": m}


# ============================================================================== Kinetik
KIN_NAMES = {"friedman": "Friedman", "ofw": "OFW", "kas": "KAS", "starink": "Starink"}


def kinetics(res: dict, state: dict | None, lang: str = "de", alpha: float = 0.5) -> list[dict]:
    """Vertrauensbereiche der Kinetik im Stil der Messunsicherheit: E ± 95-%-Vertrauensbereich der Regression
    (Student-t, n − 2 Freiheitsgrade). Nichts wird zusätzlich eingerechnet (keine doppelte Zählung von Temperatur- oder
    Massenunsicherheit; die Streuung der Läufe steckt bereits im Vertrauensbereich)."""
    from .kinetics import _t95
    L = L10N.get(lang, L10N["de"])
    m = method(state or {})
    iso = res.get("iso") or {}
    n = len(iso.get("betas") or [])
    dof = n - 2
    if dof < 1:
        return []
    t95 = _t95(dof)
    out = []

    def one(E, ci, rid, label):
        if E is None or ci is None or not math.isfinite(ci) or ci <= 0:
            return
        ins = [{"name": "E_a", "value": float(E), "unit": "kJ/mol", "label": L["kin"].format(n=n),
                "parts": [{"kind": "u", "u": float(ci) / t95, "dof": dof, "label": L["kin"].format(n=n)}]}]
        try:
            r = UN.evaluate(lambda v: v["E_a"], ins, m["method"], p=m["p"], k=m["k"], lang=lang, unit="kJ/mol",
                            label=label, name=rid)
        except UN.UncError:
            return
        out.append({"id": rid, "label": label, "unit": "kJ/mol", "value": r["value"], "u": r.get("u"), "ci": ci, "res": r})
    k = res.get("kissinger") or {}
    if not k.get("error"):
        one(k.get("E"), k.get("ci"), "ea-kissinger", L["ea"].format(m="Kissinger"))
    for mk, nm in KIN_NAMES.items():
        rows = (iso.get("methods") or {}).get(mk) or []
        if not rows:
            continue
        r0 = min(rows, key=lambda x: abs(x["alpha"] - alpha))
        if abs(r0["alpha"] - alpha) > 0.051:
            continue
        a_txt = f"{r0['alpha']:.2g}".replace(".", ",") if lang == "de" else f"{r0['alpha']:.2g}"
        one(r0.get("E"), r0.get("ci"), f"ea-{mk}-a{int(round(r0['alpha'] * 100)):02d}", L["ea_a"].format(m=nm, a=a_txt))
    return out


# ============================================================================== Bericht
def report(b, unc: dict | None, lang: str, prefix: str = "", extra: list | None = None, table: str | None = None) -> dict | None:
    """\\labval <id>-pm/-u/-U, Budgettabellen, Übersichtstabelle und Quellen; Methodentext separat (methods_text)."""
    results = [dict(r["res"], name=r["id"]) for r in ((unc or {}).get("results") or [])] + \
        [dict(r["res"], name=r["id"]) for r in (extra or [])]
    if not results:
        return None
    from labbundle import booktabs, tex_escape
    uo = UN.to_report(b, results, lang, prefix=prefix)
    de = lang == "de"
    rows = []
    for r in results:
        rows.append([tex_escape(r.get("label") or r["name"]), tex_escape(r.get("text") or ""),
                     tex_escape(r.get("method_name") or "")])
    pid = prefix.rstrip("-")
    tid = table or f"unsicherheit{('-' + pid) if pid else ''}"
    b.add_table(tid, booktabs(["Grösse" if de else "Quantity", "Wert ± U" if de else "Value ± U",
                               "Verfahren" if de else "Method"], rows, align="lll", small=True),
                ("Messunsicherheit der Kennwerte (Budgets in den Einzeltabellen)." if de else
                 "Measurement uncertainty of the results (budgets in the individual tables)."), cites=uo["cites"] or None)
    uo["tables"] = list(uo.get("tables") or []) + [tid]
    return uo


def methods_text(unc: dict | None, uo: dict | None, cite_fn, lang: str, kin: bool = False, rep: int = 0) -> str:
    """Methodensatz: Verfahren, Eingangsgrössen, Modelle (cite_fn(keys) -> "~\\cite{…}")."""
    if not uo:
        return ""
    de = lang == "de"
    m = ((unc or {}).get("method") or {}).get("method") or "gum"
    name = UN.NAMES["de" if de else "en"][m]
    c = cite_fn(uo.get("cites") or [])
    keys = set((unc or {}).get("keys") or [])
    if de:
        ins = [x for k, x in (("m0", "Einwaage"), ("bal", "Ablesung der TGA-Waage"), ("drift", "Drift und Auftrieb"),
                              ("T_cal", "Temperaturkalibrierung"), ("T_tc", "Temperaturfühler"), ("beta", "Heizrate")) if k in keys]
        models = not (kin or rep)
        t = (f"Messunsicherheiten wurden nach dem Verfahren „{name}“{c} bestimmt"
             + (f"; Eingangsgrössen: {', '.join(ins)}" if ins and models else "") + ".")
        if models:
            t += (" Massenverluste und Rückstand folgen aus $L = 100\\,(m_a - m_b + \\delta_\\mathrm{Drift})/m_0$, die "
                  "Zusammensetzung aus den Massen an ihren Grenzen; an Temperaturgrenzen geht die Temperaturunsicherheit über "
                  "die örtliche Steigung $\\mathrm{d}m/\\mathrm{d}T$ ein. Charakteristische Temperaturen: $T = T_\\mathrm{Ablesung} "
                  "+ \\delta T_\\mathrm{Kal} + \\delta T_\\mathrm{Auswertung}$, wobei $\\delta T_\\mathrm{Auswertung}$ die Lage der "
                  "Wendetangente (Onset, Endset), die Massenunsicherheit über die Steigung ($T_{x\\,\\%}$) und die Interpolation "
                  "bzw. Abtastung zwischen Messpunkten enthält.")
        if rep:
            t += (f" Für {rep} Wiederholungen derselben Probe ist der Mittelwert mit Typ-A-Unsicherheit $s/\\sqrt{{n}}$ "
                  "($n-1$ Freiheitsgrade) angegeben, kombiniert mit dem Mittel der Typ-B-Unsicherheiten der Einzelläufe.")
        if kin:
            t += (" Für die Kinetik ist der 95-\\%-Vertrauensbereich der Regression als Unsicherheit angegeben; Temperatur- "
                  "und Massenunsicherheiten sind dort nicht zusätzlich eingerechnet.")
    else:
        ins = [x for k, x in (("m0", "sample mass"), ("bal", "TGA balance reading"), ("drift", "drift and buoyancy"),
                              ("T_cal", "temperature calibration"), ("T_tc", "temperature sensor"), ("beta", "heating rate")) if k in keys]
        models = not (kin or rep)
        t = (f"Measurement uncertainties were evaluated with the method “{name}”{c}"
             + (f"; inputs: {', '.join(ins)}" if ins and models else "") + ".")
        if models:
            t += (" Mass losses and the residue follow from $L = 100\\,(m_a - m_b + \\delta_\\mathrm{drift})/m_0$, the "
                  "composition from the masses at its limits; at temperature limits the temperature uncertainty enters through "
                  "the local slope $\\mathrm{d}m/\\mathrm{d}T$. Characteristic temperatures: $T = T_\\mathrm{reading} + "
                  "\\delta T_\\mathrm{cal} + \\delta T_\\mathrm{evaluation}$, where $\\delta T_\\mathrm{evaluation}$ covers the "
                  "position of the inflection tangent (onset, endset), the mass uncertainty through the slope ($T_{x\\,\\%}$) "
                  "and the interpolation or sampling between data points.")
        if rep:
            t += (f" For {rep} repeats of the same sample the mean is given with the type A uncertainty $s/\\sqrt{{n}}$ "
                  "($n-1$ degrees of freedom), combined with the mean type B uncertainty of the single runs.")
        if kin:
            t += (" For the kinetics the 95~\\% confidence interval of the regression is given as uncertainty; temperature and "
                  "mass uncertainties are not added there.")
    return t
