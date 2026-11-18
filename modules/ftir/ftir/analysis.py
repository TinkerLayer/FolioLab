"""Ein Spektrum mit seinem Arbeitsstand auswerten (Oberfläche, Export und Bericht rechnen gleich).

Arbeitsstand (``state``), so wie er im Bericht gespeichert wird:
  {"pipeline": [...], "peaks": {"params": {...}, "add": [cm⁻¹], "remove": [cm⁻¹]} | None,
   "bands": [{"name", "lo", "hi", "base": "linear"|"zero"}], "ratios": [{"name", "num", "den"}],
   "groups": true|false,
   "search": {"algo", "libs", "include", "exclude", "hits": [{"rank", "name", "lib_name", "hqi", "category", "cas", "y"?}],
              "query": [...]} | None,
   "mixture": {"hqi", "components": [{"name", "lib_name", "frac", "y"}], "fit", "residual", "query"} | None,
   "equations": [{"sym", "label", "expr", "unit", "digits", "source"}] | None}
Suche und Mischung werden als Ergebnis gespeichert (mit den Kurven), damit der Bericht nicht von späteren
Änderungen an den Bibliotheken abhängt.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import groups as GR
from . import peaks as PK
from .process import Proc, apply
from .readers import Spectrum


@dataclass
class Analysis:
    name: str
    orig: Spectrum
    proc: Proc
    state: dict
    peaks: list = field(default_factory=list)
    groups: dict | None = None
    bands: list = field(default_factory=list)
    ratios: list = field(default_factory=list)
    equations: list = field(default_factory=list)     # ausgewertete eigene Gleichungen (labcalc.formulas)
    variables: dict = field(default_factory=dict)

    @property
    def sp(self) -> Spectrum:
        return self.proc.spectrum


def run(sp: Spectrum, state: dict | None, lang: str = "de") -> Analysis:
    state = state or {}
    proc = apply(sp, state.get("pipeline") or [], lang)
    a = Analysis(sp.name, sp, proc, state)
    s = proc.spectrum
    pk = state.get("peaks")
    if pk is not None:
        a.peaks = PK.find(s.x, s.y, s.yunit, pk.get("params"), pk.get("add"), pk.get("remove"))
        for p in a.peaks:
            p["assign"] = GR.assign(p["x"], p["strength"], lang)
    if state.get("groups"):
        a.groups = GR.analyse(s.x, s.y, s.yunit, lang)
    for b in state.get("bands") or []:
        r = PK.integrate(s.x, s.y, b.get("lo"), b.get("hi"), s.yunit, b.get("base", "linear"))
        r["name"] = str(b.get("name") or f"{max(r['lo'], r['hi']):.0f}–{min(r['lo'], r['hi']):.0f}")
        a.bands.append(r)
    by = {b["name"]: b for b in a.bands}
    for r in state.get("ratios") or []:
        n, d = by.get(r.get("num")), by.get(r.get("den"))
        val = None
        kind = r.get("kind", "area")
        if n and d:
            nv, dv = (n["area"], d["area"]) if kind == "area" else (n["height"], d["height"])
            val = (nv / dv) if (nv is not None and dv) else None
        a.ratios.append({"name": r.get("name") or f"{r.get('num')}/{r.get('den')}", "num": r.get("num"),
                         "den": r.get("den"), "kind": kind, "value": val})
    a.variables = equation_variables(a)
    if state.get("equations") or state.get("ext_values"):
        F = _formulas()
        if F is not None:
            funcs = equation_functions(a)
            F.merge_ext(a.variables, state.get("ext_values"), funcs)     # Werte anderer Umgebungen (Verbindung)
            if state.get("equations"):
                a.equations = F.evaluate(state["equations"], a.variables, funcs, lang)
    return a


# ----------------------------------------------------------------------------- Eigene Gleichungen
FUNCTIONS_DOC = [
    ("A(ν)", "Absorbanz des bearbeiteten Spektrums bei ν (aus T bzw. R umgerechnet)"),
    ("y(ν)", "Wert des bearbeiteten Spektrums bei ν in seiner Einheit"),
    ("area(ν1, ν2)", "Bandenfläche zwischen ν1 und ν2 über einer Geraden zwischen den Grenzen"),
    ("area0(ν1, ν2)", "Fläche zwischen ν1 und ν2 über null"),
    ("height(ν1, ν2)", "grösste Höhe zwischen ν1 und ν2 über der Geraden"),
]


def _formulas():
    try:
        from labcalc import formulas
    except ImportError:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "sdk" / "python"))
        try:
            from labcalc import formulas
        except ImportError:
            return None
    return formulas


def equation_variables(a: Analysis) -> dict:
    """Ergebnisse als Variablen: Bandenflächen B1…, Höhen H1…, Lagen P1…, Verhältnisse R1…, Bandenzahl, bester Treffer."""
    v: dict = {}

    def put(k, val, unit, label):
        if val is not None and np.isfinite(val):
            v[k] = {"value": float(val), "unit": unit, "label": label}

    for i, r in enumerate(a.bands, 1):
        put(f"B{i}", r.get("area"), "", f"Fläche {r['name']}")
        put(f"H{i}", r.get("height"), "", f"Höhe {r['name']}")
        put(f"P{i}", r.get("pos"), "cm⁻¹", f"Lage des Maximums {r['name']}")
    for i, r in enumerate(a.ratios, 1):
        put(f"R{i}", r.get("value"), "", f"Verhältnis {r['name']}")
    if a.peaks:
        put("npeaks", len(a.peaks), "", "Zahl der Banden")
    hits = (a.state.get("search") or {}).get("hits") or []
    if hits:
        put("hqi1", hits[0].get("hqi"), "", f"HQI des besten Treffers ({hits[0].get('name', '')})")
    return v


def equation_functions(a: Analysis) -> dict:
    from .process import to_absorbance
    s = a.sp
    order = np.argsort(s.x)
    xs, ys = np.asarray(s.x, float)[order], np.asarray(s.y, float)[order]
    absorb = to_absorbance(ys, s.yunit) if s.yunit in ("T", "R") else ys

    def _in(nu):
        nu = float(nu)
        if not xs[0] <= nu <= xs[-1]:
            raise ValueError(f"{nu:g} cm⁻¹ liegt ausserhalb des Spektrums ({xs[0]:.0f}–{xs[-1]:.0f})")
        return nu

    def _area(n1, n2, base="linear", what="area"):
        r = PK.integrate(s.x, s.y, _in(n1), _in(n2), s.yunit, base)
        if r[what] is None:
            raise ValueError("Bereich zu schmal (weniger als drei Messpunkte)")
        return float(r[what])

    return {"A": lambda nu: float(np.interp(_in(nu), xs, absorb)),
            "y": lambda nu: float(np.interp(_in(nu), xs, ys)),
            "area": lambda n1, n2: _area(n1, n2),
            "area0": lambda n1, n2: _area(n1, n2, "zero"),
            "height": lambda n1, n2: _area(n1, n2, what="height")}


def arr(v):
    return None if v is None else np.asarray([np.nan if t is None else t for t in v], dtype=float)
