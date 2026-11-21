"""Arbeitsstand eines Laufs -> alle Ergebnisse (Oberfläche, Export und Bericht rechnen gleich).

state = {
  "pipeline": [...],                                  Bearbeitungsprotokoll (process.OPS)
  "steps": {"opts": {...}, "manual": [{"lo","hi","x"}]},  Stufen automatisch oder mit gesetzten Grenzen
  "composition": {"preset": "e1131", "params": {...}} | None,
  "reactions": [{"step": 1, "key": "caco3"}],          Gehalt aus Stufe (Stöchiometrie)
  "calib": true,                                       Kalibrierprüfung Calciumoxalat
  "deconv": {"lo", "hi", "peaks": [...], "fix_pos"},   Fraser-Suzuki-Trennung der DTG
  "search": {...}, "mixture": {...},                   gespeicherte Treffer (wie FTIR)
  "equations": [{"sym","label","expr","unit","digits","source"}],
}
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from . import composition as CO
from . import deconv as DC
from . import process as PR
from . import steps as ST
from .readers import Run


def arr(v):
    if v is None:
        return None
    return np.asarray(v, dtype=float)


@dataclass
class Analysis:
    name: str
    orig: Run
    run: Run
    proc: PR.Proc
    state: dict
    st: dict = field(default_factory=dict)          # Ergebnis steps.analyse
    comp: dict | None = None
    reactions: list = field(default_factory=list)
    calib: dict | None = None
    deconv: dict | None = None
    dsc: dict | None = None
    equations: list = field(default_factory=list)
    variables: dict = field(default_factory=dict)
    unc: dict | None = None                         # Messunsicherheit (uncert.evaluate), nur mit Angaben im Arbeitsstand

    @property
    def steps(self):
        return self.st.get("steps", [])


def variables(a: Analysis) -> tuple[dict, dict]:
    """Messwerte als Variablen für eigene Gleichungen, dazu Funktionen m(T), dtg(T), loss(T1, T2)."""
    v = {}
    r = a.run
    if r.m0:
        v["m0"] = {"value": r.m0, "unit": "mg", "label": "Einwaage"}
    if r.meta.get("rate"):
        v["beta"] = {"value": r.meta["rate"], "unit": "K/min", "label": "Heizrate"}
    res = a.st.get("residue") or {}
    if res.get("end") is not None:
        v["res"] = {"value": res["end"], "unit": "%", "label": "Rückstand am Ende"}
    for L, x in (a.st.get("loss_T") or {}).items():
        if x and x.get("T") is not None:
            v[f"T{L}"] = {"value": x["T"], "unit": "°C", "label": f"T bei {L} % Verlust"}
    for s in a.steps:
        k = s["no"]
        v[f"L{k}"] = {"value": s["loss"], "unit": "%", "label": f"Verlust Stufe {k}"}
        if s.get("T_onset") is not None:
            v[f"Ton{k}"] = {"value": s["T_onset"], "unit": "°C", "label": f"Onset Stufe {k}"}
        if s.get("T_peak") is not None:
            v[f"Tp{k}"] = {"value": s["T_peak"], "unit": "°C", "label": f"DTG-Spitze Stufe {k}"}
        if s.get("T_endset") is not None:
            v[f"Tend{k}"] = {"value": s["T_endset"], "unit": "°C", "label": f"Endset Stufe {k}"}
        if s.get("loss_mg") is not None:
            v[f"Lmg{k}"] = {"value": s["loss_mg"], "unit": "mg", "label": f"Verlust Stufe {k} in mg"}
    if a.comp:
        for i, row in enumerate(a.comp["rows"], 1):
            v[f"C{i}"] = {"value": row["pct"], "unit": "%", "label": row["name"]}
    for i, rx in enumerate(a.reactions, 1):
        v[f"X{i}"] = {"value": rx["content"], "unit": "%", "label": f"Gehalt {rx['label']}"}
    for i, p in enumerate((a.dsc or {}).get("peaks") or [], 1):
        if p.get("dH") is not None:
            v[f"H{i}"] = {"value": p["dH_signed"], "unit": "J/g", "label": f"Enthalpie Peak {i} (endotherm positiv)"}
        if p.get("T_peak") is not None:
            v[f"Tdsc{i}"] = {"value": p["T_peak"], "unit": "°C", "label": f"Peaktemperatur DSC {i}"}
    for i, g in enumerate((a.dsc or {}).get("tg") or [], 1):
        if g.get("Tg_mid") is not None:
            v[f"Tg{i}"] = {"value": g["Tg_mid"], "unit": "°C", "label": f"Glasübergang {i} (Mittelpunkt)"}
    m = r.pct()
    T = r.T
    d = a.st.get("dtg") or {}

    def m_at(TT):
        k = np.nonzero(T >= float(TT))[0]
        if not len(k):
            raise ValueError(f"{float(TT):g} °C wird nicht erreicht")
        return float(m[k[0]])

    def dtg_at(TT):
        k = np.nonzero(T >= float(TT))[0]
        if not len(k) or d.get("dT") is None:
            raise ValueError(f"{float(TT):g} °C wird nicht erreicht")
        return float(-d["dT"][k[0]])

    def loss(T1, T2):
        return m_at(T1) - m_at(T2)

    return v, {"m": m_at, "dtg": dtg_at, "loss": loss}


def run(orig: Run, state: dict | None, lang: str = "de") -> Analysis:
    state = state or {}
    proc = PR.apply(orig, state.get("pipeline") or [], lang)
    r = proc.run
    a = Analysis(orig.name, orig, r, proc, state)
    so = state.get("steps") or {}
    a.st = ST.analyse(r, so.get("opts"), so.get("manual"))
    c = state.get("composition")
    if c:
        try:
            a.comp = CO.compose(r, c.get("preset", "e1131"), c.get("params"))
        except ValueError as e:
            a.comp = {"error": str(e), "rows": [], "warnings": [str(e)], "preset": c.get("preset")}
    for rx in state.get("reactions") or []:
        s = next((x for x in a.steps if x["no"] == int(rx.get("step", 0))), None)
        if s is None:
            continue
        try:
            out = CO.content_from_loss(s["loss"], rx.get("key"))
        except ValueError:
            continue
        out["step"] = s["no"]
        a.reactions.append(out)
    if state.get("calib"):
        a.calib = CO.check_oxalate(a.steps, float(state.get("calib_tol", 0.5)) if isinstance(state.get("calib_tol"), (int, float)) else 0.5)
    dc = state.get("deconv")
    if dc and dc.get("peaks"):
        try:
            d = a.st["dtg"]
            mask = np.isfinite(d["dT"]) & (r.T >= float(dc["lo"])) & (r.T <= float(dc["hi"]))
            a.deconv = DC.fit(r.T[mask], -d["dT"][mask], dc["peaks"], bool(dc.get("fix_pos")))
            a.deconv["range"] = [float(dc["lo"]), float(dc["hi"])]
            a.deconv["preset"] = dc.get("preset")
        except (ValueError, KeyError, np.linalg.LinAlgError) as e:
            a.deconv = {"error": str(e)}
    if state.get("dsc"):                                   # TGA-03
        from . import dsc as DS
        a.dsc = DS.evaluate(r, state["dsc"])
    from . import uncert as UC
    a.unc = UC.evaluate(a, state, lang)                     # Messunsicherheit, nur mit Angaben (state["unc"])
    eqs = state.get("equations") or []
    v, funcs = variables(a)
    UC.variables_u(v, a.unc, state)                         # u reist mit in eigene Gleichungen und geteilte Werte
    a.variables = v
    if eqs or state.get("ext_values"):
        from labcalc import formulas as F
        F.merge_ext(v, state.get("ext_values"), funcs)       # Werte anderer Umgebungen (Verbindung)
        if eqs:
            from .taken import guard                         # Indexwerte: unpassende Einheiten ablehnen
            a.equations = guard(F.evaluate(eqs, v, funcs, lang, unc=UC.method(state)), v, funcs, lang)
    return a


def _f(x):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else x
