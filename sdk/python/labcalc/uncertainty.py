"""Messunsicherheit: Eingangsgrössen beschreiben, Unsicherheit eines Ergebnisses nach vier Verfahren bestimmen.

Eingangsgrösse (``make_input``)::

    {"name": "d", "value": 10.02, "unit": "mm", "label": "Durchmesser",
     "parts": [                                    # Beiträge, quadratisch addiert (jeder einzeln in Monte Carlo)
        {"kind": "repeats", "values": [10.01, 10.03, 10.02]},          # Typ A: Mittelwert, s/√n, n − 1 Freiheitsgrade
        {"kind": "resolution", "d": 0.01},                              # Ziffernschritt → Rechteck a = d/2
        {"kind": "limits", "a": 0.02, "dist": "rect"},                  # Grenzen ±a (rect | tri | arcsine | normal = 3σ)
        {"kind": "u", "u": 0.004},                                      # Standardunsicherheit
        {"kind": "U", "U": 0.01, "k": 2},                               # erweiterte Unsicherheit, z. B. Kalibrierschein
        {"kind": "rel", "pct": 0.5, "dist": "rect"},                    # ± Prozent vom Wert
        {"kind": "spec", "pct": 0.05, "digits": 2, "d": 0.01},          # ±(% vom Messwert + n Digits)
        {"kind": "sd", "sd": 0.02, "n": 5},                             # Standardabweichung einzelner Werte, n Werte
        {"kind": "ci", "half": 0.03, "level": 95, "n": 5},              # Vertrauensbereich
        {"kind": "instrument", "id": "pt100-a"}],                       # aus der Messmittelliste (labcalc/data)
     "dof": None, "source": {...}, "note": "..."}

Verfahren (``evaluate(model, inputs, method)``):

* ``gum``   – GUM-Fortpflanzungsgesetz erster Ordnung mit Empfindlichkeitskoeffizienten (zentrale Differenzen),
              optionalen Korrelationen, Welch–Satterthwaite und k aus der t-Verteilung (JCGM 100:2008, 5, G.4, G.6).
* ``mc``    – Monte-Carlo-Verfahren nach GUM Supplement 1 (JCGM 101:2008), adaptiv (7.9), Überdeckungsintervall
              wahrscheinlichkeitssymmetrisch und kürzestes (7.7).
* ``gauss`` – klassisches Gausssches Fehlerfortpflanzungsgesetz mit Standardunsicherheiten, ohne Korrelation und
              ohne Erweiterungsfaktor (DIN 1319-4; Taylor 1997, Kap. 3).
* ``worst`` – Grösstfehler: Extremwerte des Modells über die Grenzen der Eingangsgrössen (alle Ecken bis 10
              Grössen, sonst lineare Schranke Σ|cᵢ|aᵢ).

Modell: Python-Funktion ``f(values: dict) -> float | ndarray`` (arbeitet möglichst mit numpy-Feldern) oder
``{"expr": "F/(pi*d^2/4)"}`` (``labcalc.expr``, ohne ``eval``). Werte ohne Unsicherheit gelten als exakt.
"""
from __future__ import annotations

import itertools
import json
import math
import re
import time
from statistics import NormalDist
from pathlib import Path

import numpy as np

from . import expr as E
from . import units as U
from .stats import t_ppf

METHODS = ("gum", "mc", "gauss", "worst")
DISTS = ("normal", "rect", "tri", "arcsine", "t")
KINDS = ("u", "U", "limits", "resolution", "rel", "spec", "repeats", "sd", "ci", "instrument")
P_DEFAULT = 0.95
MC_BLOCK = 10_000
MC_MAX = 1_000_000
MC_LOOP_MAX = 4_000          # nicht vektorisierbare Modelle: Blockgrösse der Einzelauswertungen
MC_LOOP_SECONDS = 4.0        # … und Zeitbudget, danach Abbruch mit Hinweis (GUM S1 7.9 adaptiv, sonst begrenzt)
MAX_INPUTS = 60
MAX_CORNERS = 10

REF_KEYS = {"gum": ["jcgm100"], "mc": ["jcgm101", "jcgm100"], "gauss": ["din1319-4", "taylor1997"],
            "worst": ["din1319-4", "jcgm100"]}

NAMES = {
    "de": {"gum": "GUM (linear)", "mc": "Monte Carlo (GUM S1)", "gauss": "Gausssche Fehlerfortpflanzung",
           "worst": "Grösstfehler (Extremwerte)",
           "normal": "normal", "rect": "Rechteck", "tri": "Dreieck", "arcsine": "U-förmig", "t": "t (Typ A)"},
    "en": {"gum": "GUM (linear)", "mc": "Monte Carlo (GUM S1)", "gauss": "Gaussian error propagation",
           "worst": "Worst case (extreme values)",
           "normal": "normal", "rect": "rectangular", "tri": "triangular", "arcsine": "U-shaped", "t": "t (type A)"},
}


class UncError(ValueError):
    pass


# ============================================================================== Eingangsgrössen
def _num(v, what: str) -> float:
    try:
        f = float(str(v).replace(",", ".").replace("−", "-")) if not isinstance(v, (int, float)) else float(v)
    except (TypeError, ValueError):
        raise UncError(f"{what}: keine Zahl") from None
    if not math.isfinite(f):
        raise UncError(f"{what}: nicht endlich")
    return f


def _pos(v, what: str, zero_ok: bool = True) -> float:
    f = _num(v, what)
    if f < 0 or (f == 0 and not zero_ok):
        raise UncError(f"{what}: muss positiv sein")
    return f


DIST_FACTOR = {"rect": math.sqrt(3), "tri": math.sqrt(6), "arcsine": math.sqrt(2), "normal": 3.0}


def _part(p: dict, value: float, unit: str, lang: str = "de") -> dict:
    """Einen Beitrag auf {u, dist, a, dof, type, label, …} zurückführen (a = Halbbreite bzw. Grenze für Grösstfehler)."""
    if not isinstance(p, dict):
        raise UncError("Beitrag: Objekt erwartet")
    kind = str(p.get("kind") or "u")
    if kind not in KINDS:
        raise UncError(f"Beitrag: unbekannte Art „{kind}“")
    de = lang == "de"
    label = str(p.get("label") or "")[:120]
    src = p.get("source") if isinstance(p.get("source"), dict) else None
    out = {"kind": kind, "label": label, "type": "B", "dof": math.inf, "source": src}
    if kind == "u":
        u = _pos(p.get("u"), "u")
        out.update(u=u, dist="normal", a=2 * u, a_note="2u")
        out["label"] = label or ("Standardunsicherheit" if de else "standard uncertainty")
    elif kind == "U":
        Uv, k = _pos(p.get("U"), "U"), _pos(p.get("k", 2), "k", zero_ok=False)
        out.update(u=Uv / k, dist="normal", a=Uv, k=k, a_note=f"U (k = {k:g})")
        out["label"] = label or ((f"erweiterte Unsicherheit (k = {k:g})" if de else f"expanded uncertainty (k = {k:g})"))
    elif kind in ("limits", "rel", "spec", "resolution"):
        dist = str(p.get("dist") or "rect")
        if kind == "resolution":
            a, dist = _pos(p.get("d"), "Ziffernschritt", zero_ok=False) / 2, "rect"
            out["label"] = label or ("Auflösung" if de else "resolution")
        elif kind == "limits":
            a = _pos(p.get("a"), "Halbbreite")
            out["label"] = label or ("Grenzen ±a" if de else "limits ±a")
        elif kind == "rel":
            a = _pos(p.get("pct"), "Prozent") / 100 * abs(value)
            out["label"] = label or (f"±{_g(p.get('pct'))} % vom Wert" if de else f"±{_g(p.get('pct'))} % of value")
        else:
            pct = _pos(p.get("pct", 0), "Prozent")
            n = _pos(p.get("digits", 0), "Digits")
            d = _pos(p.get("d", 0), "Ziffernschritt")
            a = pct / 100 * abs(value) + n * d
            out["label"] = label or (f"±({_g(pct)} % + {_g(n)} Digits)" if de else f"±({_g(pct)} % + {_g(n)} digits)")
        if dist not in DIST_FACTOR:
            raise UncError(f"Verteilung „{dist}“ unbekannt")
        out.update(u=a / DIST_FACTOR[dist], dist=dist, a=a)
    elif kind == "repeats":
        vals = [_num(x, "Wiederholwert") for x in list(p.get("values") or [])[:10000]]
        if len(vals) < 2:
            raise UncError("Wiederholmessung: mindestens zwei Werte")
        arr = np.asarray(vals, float)
        n, s = len(arr), float(arr.std(ddof=1))
        out.update(type="A", u=s / math.sqrt(n), dist="t" if n > 3 else "normal", dof=n - 1, n=n, mean=float(arr.mean()),
                   s=s, a=2 * s / math.sqrt(n), a_note="2s/√n")
        out["label"] = label or (f"Wiederholungen (n = {n})" if de else f"repeats (n = {n})")
    elif kind == "sd":
        s = _pos(p.get("sd"), "s")
        n = int(_pos(p.get("n", 1), "n", zero_ok=False))
        out.update(type="A", u=s / math.sqrt(n), dist="t" if n > 3 else "normal", dof=(n - 1) if n > 1 else math.inf,
                   n=n, s=s, a=2 * s / math.sqrt(n), a_note="2s/√n")
        out["label"] = label or (f"Standardabweichung, n = {n}" if de else f"standard deviation, n = {n}")
    elif kind == "ci":
        half = _pos(p.get("half"), "Halbbreite")
        lvl = _num(p.get("level", 95), "Niveau")
        n = int(_pos(p.get("n", 0), "n"))
        q = 0.5 + lvl / 200
        z = t_ppf(q, n - 1) if n > 1 else _z(q)
        out.update(type="A" if n > 1 else "B", u=half / z, dist="t" if n > 3 else "normal",
                   dof=(n - 1) if n > 1 else math.inf, a=half, a_note=f"{_g(lvl)} %")
        out["label"] = label or (f"Vertrauensbereich {_g(lvl)} %" if de else f"confidence interval {_g(lvl)} %")
    elif kind == "instrument":
        sub = instrument_parts(str(p.get("id") or ""), value, unit, p.get("params") or {}, lang)
        return {"kind": "instrument", "id": p.get("id"), "parts": sub}
    if p.get("dof") not in (None, "", "inf"):
        out["dof"] = max(1.0, _num(p.get("dof"), "Freiheitsgrade"))
    return out


def _z(q: float) -> float:
    """Quantil der Standardnormalverteilung."""
    return float(NormalDist().inv_cdf(q))


def _g(v) -> str:
    try:
        return f"{float(v):g}"
    except (TypeError, ValueError):
        return str(v)


def make_input(spec: dict, lang: str = "de") -> dict:
    """Eingangsgrösse prüfen; liefert {name, value, unit, label, u, dof, type, parts:[…], …}."""
    if not isinstance(spec, dict):
        raise UncError("Eingangsgrösse: Objekt erwartet")
    name = str(spec.get("name") or "").strip()
    if not name:
        raise UncError("Eingangsgrösse ohne Namen")
    unit = str(spec.get("unit") or "")[:30]
    raw_parts = list(spec.get("parts") or [])[:20]
    value = spec.get("value")
    reps = next((p for p in raw_parts if isinstance(p, dict) and p.get("kind") == "repeats"), None)
    if value in (None, "") and reps:
        value = float(np.mean([_num(x, "Wiederholwert") for x in reps.get("values") or [0]]))
    value = _num(value, f"{name}: Wert")
    parts = []
    for p in raw_parts:
        try:
            r = _part(p, value, unit, lang)
        except UncError as e:
            raise UncError(f"{name}: {e}") from None
        if r.get("kind") == "instrument" and "parts" in r:
            parts += r["parts"]
        elif r.get("u") is not None:
            parts.append(r)
    u2 = sum(p["u"] ** 2 for p in parts)
    u = math.sqrt(u2)
    # Freiheitsgrade der Grösse (Welch–Satterthwaite über die Beiträge)
    den = sum(p["u"] ** 4 / p["dof"] for p in parts if math.isfinite(p["dof"]) and p["u"] > 0)
    dof = (u2 * u2 / den) if den > 0 else math.inf
    if len(parts) == 1:
        dof = parts[0]["dof"]
    if spec.get("dof") not in (None, "", "inf"):
        dof = max(1.0, _num(spec["dof"], "Freiheitsgrade"))
    typ = "A" if parts and all(p["type"] == "A" for p in parts) else ("A+B" if any(p["type"] == "A" for p in parts) else "B")
    return {"name": name, "value": value, "unit": unit, "label": str(spec.get("label") or name)[:120], "u": u,
            "dof": dof, "type": typ if parts else "", "parts": parts, "exact": not parts or u == 0,
            "source": spec.get("source") if isinstance(spec.get("source"), dict) else None,
            "note": str(spec.get("note") or "")[:300],
            "a": sum(p["a"] for p in parts), "dist": parts[0]["dist"] if len(parts) == 1 else ("normal" if parts else "")}


def standard_u(spec: dict, value: float, unit: str = "", lang: str = "de") -> dict:
    """Für die Vorschau im ±-Fenster: eine Grösse mit ihren Beiträgen auswerten (Wert, u, Freiheitsgrade)."""
    inp = make_input({"name": "x", "value": value, "unit": unit, "parts": spec.get("parts") if isinstance(spec, dict) else []},
                     lang)
    return {k: _jsonable(inp[k]) for k in ("value", "u", "dof", "type", "a", "parts", "exact")}


# ============================================================================== Messmittel
_DATA = Path(__file__).with_name("data") / "instruments.json"
_INSTR: dict | None = None
_OWN: list[dict] = []          # vom Modulserver gesetzt (eigene Messmittel der Suite), siehe set_own_instruments


def _instr_data() -> dict:
    global _INSTR
    if _INSTR is None:
        _INSTR = json.loads(_DATA.read_text(encoding="utf-8"))
    return _INSTR


def set_own_instruments(items: list[dict]):
    """Eigene Messmittel (Datei der Suite) für diese Auswertung bekannt machen."""
    global _OWN
    _OWN = [dict(x, own=True) for x in (items or []) if isinstance(x, dict) and x.get("id")]


def instruments(lang: str = "de") -> list[dict]:
    """Messmittelliste: eingebaute (mit Quelle) und eigene."""
    d = _instr_data()
    out = []
    for it in d["instruments"] + _OWN:
        name = it.get("name")
        out.append({**it, "name": (name.get(lang) or name.get("de")) if isinstance(name, dict) else str(name or it["id"]),
                    "group_name": d["groups"].get(it.get("group"), {}).get(lang, it.get("group", "")) if it.get("group") else ""})
    return out


def instrument(iid: str) -> dict:
    for it in _instr_data()["instruments"] + _OWN:
        if it.get("id") == iid:
            return it
    raise UncError(f"Messmittel „{iid}“ unbekannt")


def instrument_parts(iid: str, value: float, unit: str, params: dict | None = None, lang: str = "de") -> list[dict]:
    """Beiträge eines Messmittels für einen Messwert (Grenzen als Ausdruck in x = |Wert in der Messmittel-Einheit|)."""
    it = instrument(iid)
    iu = str(it.get("unit") or "")
    conv = 1.0
    x = abs(value)
    if iu and unit and iu != unit:
        if not U.compatible(iu, unit):
            raise UncError(f"Einheit {unit} passt nicht zum Messmittel ({iu})")
        x = abs(float(U.from_si(U.to_si(value, unit), iu)))
        conv = float(U.from_si(U.to_si(1.0, iu, diff=True), unit, diff=True))
    names = {"x": x}
    for prm in it.get("params") or []:
        v = (params or {}).get(prm["name"], prm.get("default"))
        names[prm["name"]] = _num(v, prm.get("label", prm["name"]))
    nm = it.get("name")
    iname = (nm.get(lang) or nm.get("de")) if isinstance(nm, dict) else str(nm or iid)
    src = it.get("source")
    out = []
    for p in it.get("parts") or []:
        try:
            node = E.parse(str(p["a"]), E.Ctx().callables())
            a = float(E.evaluate(node, E.Ctx(names=dict(names)))) * conv
        except (E.CalcError, SyntaxError, ValueError, TypeError, KeyError) as e:
            raise UncError(f"Messmittel {iid}: Grenze nicht auswertbar ({e})") from None
        dist = p.get("dist", "rect")
        if dist not in DIST_FACTOR:
            raise UncError(f"Messmittel {iid}: Verteilung „{dist}“ unbekannt")
        lab = p.get("label")
        lab = (lab.get(lang) or lab.get("de")) if isinstance(lab, dict) else (lab or "")
        out.append({"kind": "instrument", "id": iid, "label": f"{iname}: {lab}" if lab else iname, "type": "B",
                    "u": abs(a) / DIST_FACTOR[dist], "a": abs(a), "dist": dist, "dof": math.inf,
                    "source": src if isinstance(src, dict) else None, "source_key": src if isinstance(src, str) else None})
    return out


def check_own_instrument(it: dict) -> dict:
    """Eigenes Messmittel prüfen (Speichern über labunc.route)."""
    if not isinstance(it, dict):
        raise UncError("Messmittel: Objekt erwartet")
    name = str(it.get("name") or "").strip()[:120]
    if not name:
        raise UncError("Messmittel: Name fehlt")
    parts = []
    for p in list(it.get("parts") or [])[:8]:
        a = str((p or {}).get("a") or "").strip()[:200]
        if not a:
            continue
        dist = (p or {}).get("dist", "rect")
        if dist not in DIST_FACTOR:
            raise UncError(f"Verteilung „{dist}“ unbekannt")
        parts.append({"label": str(p.get("label") or "")[:80], "a": a, "dist": dist})
    if not parts:
        raise UncError("Messmittel: mindestens eine Grenze (z. B. 0,02 oder 0,5/100*x)")
    params = []
    for prm in list(it.get("params") or [])[:6]:
        if prm and str(prm.get("name") or "").isidentifier():
            params.append({"name": prm["name"], "label": str(prm.get("label") or prm["name"])[:60],
                           "default": _num(prm.get("default", 0), "Parameter")})
    out = {"id": it.get("id"), "name": name, "group": "own", "unit": str(it.get("unit") or "")[:20], "parts": parts,
           "params": params, "note": str(it.get("note") or "")[:400],
           "source": it.get("source") if isinstance(it.get("source"), dict) else None,
           "calibrated": str(it.get("calibrated") or "")[:20]}
    names = {"x": 1.0, **{p["name"]: p["default"] for p in params}}
    for p in parts:                                          # Ausdrücke vorab prüfen
        try:
            float(E.evaluate(E.parse(p["a"], E.Ctx().callables()), E.Ctx(names=dict(names))))
        except Exception as e:  # noqa: BLE001 – Meldung an die Oberfläche
            raise UncError(f"Grenze „{p['a']}“: {e}") from None
    return out


# ============================================================================== Modell
def model_from_expr(expr: str, functions: dict | None = None, constants: dict | None = None):
    """Ausdruck als Modellfunktion (vektorisiert über numpy-Felder)."""
    funcs = dict(functions or {})
    node = E.parse(str(expr), E.Ctx().callables() | frozenset(funcs))
    const = dict(constants or {})

    def f(vals):
        return E.evaluate(node, E.Ctx(names={**const, **vals}), dict(funcs))
    f.expr = str(expr)
    return f


def _as_model(model):
    if callable(model):
        return model
    if isinstance(model, dict) and model.get("expr"):
        return model_from_expr(model["expr"], model.get("functions"), model.get("constants"))
    if isinstance(model, str):
        return model_from_expr(model)
    raise UncError("Modell: Funktion oder Ausdruck erwartet")


def _scalar(v) -> float:
    a = np.asarray(v, dtype=float)
    if a.ndim:
        if a.size != 1:
            raise UncError("Modell liefert keine einzelne Zahl")
        a = a.reshape(())
    f = float(a)
    if not math.isfinite(f):
        raise UncError("Modell liefert keinen endlichen Wert")
    return f


def _eval_many(f, base: dict, cols: dict, m: int):
    """Modell für m Wertesätze: zuerst vektorisiert, sonst einzeln (höchstens MC_LOOP_MAX)."""
    vals = {**base, **cols}
    try:
        with np.errstate(all="ignore"):
            y = np.asarray(f(vals), dtype=float)
        if y.shape == (m,):
            return y, True
        if y.ndim == 0 and m == 1:
            return y.reshape(1), True
    except Exception:  # noqa: BLE001 – Rückfall auf Einzelauswertung
        pass
    m2 = min(m, MC_LOOP_MAX)
    y = np.empty(m2)
    for i in range(m2):
        try:
            y[i] = _scalar(f({**base, **{k: float(v[i]) for k, v in cols.items()}}))
        except Exception:  # noqa: BLE001
            y[i] = np.nan
    return y, False


def _prep(inputs, lang):
    ins = []
    seen = set()
    for s in list(inputs or [])[:MAX_INPUTS]:
        x = s if isinstance(s, dict) and "parts" in s and "u" in s else make_input(s, lang)
        if x["name"] in seen:
            raise UncError(f"Grösse „{x['name']}“ doppelt")
        seen.add(x["name"])
        ins.append(x)
    return ins


def _corr_matrix(ins, corr) -> np.ndarray | None:
    """corr: [{"a": name, "b": name, "r": 0.5}, …] oder {"a|b": r}."""
    if not corr:
        return None
    idx = {x["name"]: i for i, x in enumerate(ins)}
    R = np.eye(len(ins))
    pairs = corr.items() if isinstance(corr, dict) else [((c.get("a"), c.get("b")), c.get("r")) for c in corr]
    any_r = False
    for key, r in pairs:
        a, b = (key.split("|") if isinstance(key, str) else key)
        if a not in idx or b not in idx or a == b:
            continue
        r = _num(r, "Korrelation")
        if not -1 <= r <= 1:
            raise UncError("Korrelationskoeffizient zwischen −1 und 1")
        R[idx[a], idx[b]] = R[idx[b], idx[a]] = r
        any_r = any_r or r != 0
    if not any_r:
        return None
    if np.linalg.eigvalsh(R).min() < -1e-10:
        raise UncError("Korrelationen sind nicht verträglich (Matrix nicht positiv semidefinit)")
    return R


def sensitivities(f, ins) -> tuple[float, list[float], list[str]]:
    """y = f(x) und cᵢ = ∂f/∂xᵢ (zentrale Differenzen, Schritt uᵢ/100 bzw. relativ 1e-6); Hinweise auf Nichtlinearität."""
    base = {x["name"]: x["value"] for x in ins}
    y = _scalar(f(dict(base)))
    cs, notes = [], []
    for x in ins:
        if x["exact"]:
            cs.append(0.0)
            continue
        h = x["u"] / 100 or 1e-6 * max(abs(x["value"]), 1e-12)
        try:
            yp = _scalar(f({**base, x["name"]: x["value"] + h}))
            ym = _scalar(f({**base, x["name"]: x["value"] - h}))
        except (UncError, Exception) as e:  # noqa: BLE001
            raise UncError(f"Empfindlichkeit für {x['name']} nicht bestimmbar: {e}") from None
        c = (yp - ym) / (2 * h)
        cs.append(c)
        # Nichtlinearität im Bereich ±u (GUM 5.1.2): Anteil des quadratischen Glieds
        try:
            u = x["u"]
            y2p = _scalar(f({**base, x["name"]: x["value"] + u}))
            y2m = _scalar(f({**base, x["name"]: x["value"] - u}))
            quad = abs(y2p + y2m - 2 * y) / 2
            if abs(c * u) > 0 and quad > 0.1 * abs(c * u):
                notes.append(f"nonlinear:{x['name']}")
            elif c == 0 and quad > 0:
                notes.append(f"nonlinear:{x['name']}")
        except Exception:  # noqa: BLE001
            notes.append(f"edge:{x['name']}")
    return y, cs, notes


def k_for(dof: float, p: float = P_DEFAULT) -> float:
    """Erweiterungsfaktor aus der t-Verteilung (GUM G.6.4: ν_eff auf die nächstkleinere ganze Zahl)."""
    if not math.isfinite(dof) or dof > 1e6:
        return float(_z(0.5 + p / 2))
    return float(t_ppf(0.5 + p / 2, max(1, math.floor(dof))))


# ============================================================================== Verfahren
def _budget(ins, cs, uc):
    rows = []
    for x, c in zip(ins, cs):
        cu = abs(c) * x["u"]
        rows.append({"name": x["name"], "label": x["label"], "value": x["value"], "unit": x["unit"], "u": x["u"],
                     "type": x["type"], "dist": x["dist"], "dof": x["dof"], "c": c, "cu": cu, "a": x["a"],
                     "share": (cu * cu / (uc * uc) * 100) if uc > 0 else 0.0, "exact": x["exact"],
                     "parts": [{k: p.get(k) for k in ("label", "u", "dist", "dof", "type", "a", "kind", "source", "source_key", "id")}
                               for p in x["parts"]], "source": x.get("source")})
    return rows


def gum(f, ins, R=None, p=P_DEFAULT, k=None) -> dict:
    y, cs, notes = sensitivities(f, ins)
    cu = np.array([c * x["u"] for x, c in zip(ins, cs)])
    var = float(cu @ (R if R is not None else np.eye(len(ins))) @ cu) if len(ins) else 0.0
    uc = math.sqrt(max(var, 0.0))
    den = sum(v ** 4 / x["dof"] for v, x in zip(cu, ins) if math.isfinite(x["dof"]) and v != 0)
    dof = (uc ** 4 / den) if den > 0 else math.inf
    if R is not None and math.isfinite(dof):
        notes.append("ws_corr")
    kk = float(k) if k else k_for(dof, p)
    U_ = kk * uc
    return {"method": "gum", "value": y, "u": uc, "k": kk, "U": U_, "p": p, "dof": dof, "lo": y - U_, "hi": y + U_,
            "budget": _budget(ins, cs, uc), "notes": notes, "k_fixed": bool(k)}


def gauss(f, ins) -> dict:
    y, cs, notes = sensitivities(f, ins)
    uc = math.sqrt(sum((c * x["u"]) ** 2 for x, c in zip(ins, cs)))
    return {"method": "gauss", "value": y, "u": uc, "k": 1.0, "U": uc, "p": None, "dof": None,
            "lo": y - uc, "hi": y + uc, "budget": _budget(ins, cs, uc), "notes": notes}


def worst(f, ins) -> dict:
    y, cs, notes = sensitivities(f, ins)
    act = [x for x in ins if not x["exact"] and x["a"] > 0]
    base = {x["name"]: x["value"] for x in ins}
    lin = sum(abs(c) * x["a"] for x, c in zip(ins, cs))
    out = {"method": "worst", "value": y, "linear": lin, "budget": _budget(ins, cs, math.sqrt(sum((c * x["u"]) ** 2
                                                                                          for x, c in zip(ins, cs)))),
           "notes": notes, "limits_note": sorted({p.get("a_note") for x in act for p in x["parts"] if p.get("a_note")})}
    for row, x, c in zip(out["budget"], ins, cs):
        row["ca"] = abs(c) * x["a"]
    if not act:
        out.update(lo=y, hi=y, U_minus=0.0, U_plus=0.0, corners=0)
        return out
    if len(act) <= MAX_CORNERS:
        signs = np.array(list(itertools.product((-1.0, 1.0), repeat=len(act))))
        cols = {x["name"]: x["value"] + signs[:, i] * x["a"] for i, x in enumerate(act)}
        ys, _vec = _eval_many(f, base, cols, len(signs))
        ys = ys[np.isfinite(ys)]
        # Inneres stichprobenartig prüfen (nicht monotone Modelle)
        rng = np.random.default_rng(12345)
        m = 2000
        cols2 = {x["name"]: x["value"] + rng.uniform(-1, 1, m) * x["a"] for x in act}
        ys2, _ = _eval_many(f, base, cols2, m)
        ys2 = ys2[np.isfinite(ys2)]
        lo, hi = float(min(ys.min(initial=y), y)), float(max(ys.max(initial=y), y))
        if ys2.size and (ys2.min() < lo - 1e-12 * abs(lo) or ys2.max() > hi + 1e-12 * abs(hi)):
            notes.append("interior")
            lo, hi = min(lo, float(ys2.min())), max(hi, float(ys2.max()))
        out.update(lo=lo, hi=hi, U_minus=y - lo, U_plus=hi - y, corners=int(2 ** len(act)))
    else:
        out.update(lo=y - lin, hi=y + lin, U_minus=lin, U_plus=lin, corners=0)
        notes.append("linear_bound")
    out["U"] = max(out["U_minus"], out["U_plus"])
    return out


def _draw(rng, x, m, R_normal=None):
    """Stichproben einer Grösse: Summe der Beiträge (GUM S1 6.4)."""
    v = np.full(m, x["value"], float)
    for p in x["parts"]:
        if p["u"] <= 0:
            continue
        if p["dist"] == "normal":
            v += rng.standard_normal(m) * p["u"]
        elif p["dist"] == "rect":
            v += rng.uniform(-p["a"], p["a"], m)
        elif p["dist"] == "tri":
            v += rng.triangular(-p["a"], 0.0, p["a"], m)
        elif p["dist"] == "arcsine":
            v += p["a"] * np.cos(np.pi * rng.uniform(0, 1, m))
        elif p["dist"] == "t":                            # skalierte, verschobene t-Verteilung (S1 6.4.9.7)
            v += rng.standard_t(p["dof"], m) * p["u"]
    return v


def _interval(ys, p):
    ys = np.sort(ys)
    m = ys.size
    q = int(p * m + 0.5)
    lo_s, hi_s = float(ys[int((1 - p) / 2 * m)]), float(ys[min(m - 1, int((1 - p) / 2 * m) + q)])
    w = ys[q:] - ys[: m - q]
    j = int(np.argmin(w)) if w.size else 0
    return (lo_s, hi_s), (float(ys[j]), float(ys[min(m - 1, j + q)]))


def monte_carlo(f, ins, R=None, p=P_DEFAULT, seed=20261119, ndig=2, max_trials=MC_MAX) -> dict:
    y0, cs, notes = sensitivities(f, ins)
    rng = np.random.default_rng(int(seed))
    base = {x["name"]: x["value"] for x in ins if x["exact"]}
    act = [x for x in ins if not x["exact"]]
    corr_idx = []
    if R is not None:
        corr_idx = [i for i, x in enumerate(ins) if not x["exact"] and np.any(np.abs(R[i] - np.eye(len(ins))[i]) > 0)]
        if corr_idx:
            notes.append("corr_normal")
            L = np.linalg.cholesky(R[np.ix_(corr_idx, corr_idx)] + 1e-12 * np.eye(len(corr_idx)))
    blocks, all_y, vec = [], [], True
    h = 0
    stable = False
    t0 = time.monotonic()
    while True:
        m = MC_BLOCK if vec else min(MC_BLOCK, MC_LOOP_MAX)
        cols = {}
        for x in act:
            if any(ins[i]["name"] == x["name"] for i in corr_idx):
                continue
            cols[x["name"]] = _draw(rng, x, m)
        if corr_idx:
            z = rng.standard_normal((m, len(corr_idx))) @ L.T
            for j, i in enumerate(corr_idx):
                cols[ins[i]["name"]] = ins[i]["value"] + z[:, j] * ins[i]["u"]
        ys, vec_ok = _eval_many(f, base, cols, m)
        vec = vec and vec_ok
        ys = ys[np.isfinite(ys)]
        if ys.size < 0.9 * min(m, MC_LOOP_MAX):
            notes.append("mc_invalid")
        all_y.append(ys)
        if ys.size > 10:
            (lo, hi), _ = _interval(ys, p)
            blocks.append((float(ys.mean()), float(ys.std(ddof=1)), lo, hi))
        h += 1
        total = sum(a.size for a in all_y)
        if h >= 2 and len(blocks) >= 2:
            B = np.array(blocks)
            u_est = float(np.concatenate(all_y).std(ddof=1))
            if u_est == 0:
                stable = True
                break
            l = math.floor(math.log10(u_est)) - (ndig - 1)
            delta = 0.5 * 10 ** l
            sd = B.std(axis=0, ddof=1) / math.sqrt(len(B))
            if np.all(2 * sd <= delta):
                stable = True
                break
        if total >= max_trials:
            notes.append("mc_max")
            break
        if not vec and time.monotonic() - t0 >= MC_LOOP_SECONDS:      # >=: die Windows-Uhr tickt in ~16 ms
            notes.append("mc_loop")
            break
    ys = np.concatenate(all_y)
    if ys.size < 100:
        raise UncError("Monte Carlo: zu wenige gültige Modellwerte")
    (lo, hi), (slo, shi) = _interval(ys, p)
    mean, sd = float(ys.mean()), float(ys.std(ddof=1))
    counts, edges = np.histogram(ys, bins=40)
    return {"method": "mc", "value": mean, "y_model": y0, "u": sd, "p": p, "lo": lo, "hi": hi, "short": [slo, shi],
            "U_minus": mean - lo, "U_plus": hi - mean, "U": max(mean - lo, hi - mean), "k": None, "dof": None,
            "M": int(ys.size), "seed": int(seed), "stable": stable, "vectorised": vec,
            "hist": {"counts": counts.tolist(), "edges": [float(e) for e in edges]},
            "budget": _budget(ins, cs, math.sqrt(sum((c * x["u"]) ** 2 for x, c in zip(ins, cs)))), "notes": notes}


def evaluate(model, inputs, method: str = "gum", corr=None, p: float = P_DEFAULT, k=None, seed=20261119,
             lang: str = "de", unit: str = "", label: str = "", name: str = "") -> dict:
    """Unsicherheit eines Ergebnisses nach einem Verfahren. Rückgabe JSON-fähig (``text`` für die Anzeige)."""
    if method not in METHODS:
        raise UncError(f"Verfahren „{method}“ unbekannt")
    f = _as_model(model)
    ins = _prep(inputs, lang)
    R = _corr_matrix(ins, corr)
    p = float(p or P_DEFAULT)
    if not 0.5 <= p < 1:
        raise UncError("Überdeckungswahrscheinlichkeit zwischen 50 und 99,9 %")
    if method == "gum":
        r = gum(f, ins, R, p, k)
    elif method == "gauss":
        r = gauss(f, ins)
        if R is not None:
            r["notes"].append("gauss_no_corr")
    elif method == "worst":
        r = worst(f, ins)
        if R is not None:
            r["notes"].append("worst_no_corr")
    else:
        r = monte_carlo(f, ins, R, p, seed)
    r.update(unit=unit, label=label, name=name, refs=REF_KEYS[method], method_name=NAMES.get(lang, NAMES["de"])[method],
             inputs_n=len(ins), uncertain_n=sum(1 for x in ins if not x["exact"]))
    r["text"] = fmt_result(r, lang)
    r["note_texts"] = note_texts(r["notes"], lang)
    r["refs_full"] = refs_text(r, lang)
    return _jsonable(r)


def refs_text(r: dict, lang: str = "de") -> list[str]:
    """Ausgeschriebene Quellen eines Ergebnisses: Verfahren und verwendete Messmittel (für „Was passiert hier?“)."""
    from .sources import REFS
    try:
        import labcite as C
    except ImportError:                                   # labcalc ohne SDK-Pfad: nur Titel
        C = None
    keys = list(r.get("refs") or [])
    recs = []
    for row in r.get("budget") or []:
        for prt in row.get("parts") or []:
            src = prt.get("source") or prt.get("source_key")
            if isinstance(src, str) and src not in keys:
                keys.append(src)
            elif isinstance(src, dict) and src not in recs:
                recs.append(src)
    out = []
    for rec in [REFS[k] for k in keys if k in REFS] + recs:
        out.append((C.text(rec, lang) if C else str(rec.get("title") or "")).replace("{", "").replace("}", ""))
    return list(dict.fromkeys(out))


def gum_rows(model, values: dict, u: dict) -> dict:
    """GUM linear Zeile für Zeile (Tabellenspalten, Kurvenpunkte), unabhängige Eingangsgrössen.

    values: Name -> Zahl oder Feld (gleiche Länge); u: Name -> Standardunsicherheit (Zahl oder Feld), fehlend = exakt.
    Rückgabe {"value": Feld, "u": Feld, "cu": {Name: |cᵢ|·uᵢ als Feld}}; Zeilen ohne endlichen Wert bleiben NaN.
    """
    f = _as_model(model)
    n = max([np.size(v) for v in values.values()] + [1])
    X = {k: np.broadcast_to(np.asarray(v, float), (n,)).astype(float) for k, v in values.items()}
    with np.errstate(all="ignore"):
        y = np.broadcast_to(np.asarray(f(dict(X)), float), (n,)).astype(float)
        var = np.zeros(n)
        cu = {}
        for k, uk in (u or {}).items():
            if k not in X:
                continue
            uk = np.broadcast_to(np.asarray(uk, float), (n,))
            if not np.any(uk > 0):
                continue
            h = np.where(uk > 0, uk / 100, 1e-9)
            yp = np.asarray(f({**X, k: X[k] + h}), float)
            ym = np.asarray(f({**X, k: X[k] - h}), float)
            c = (yp - ym) / (2 * h)
            cu[k] = np.abs(c * np.where(uk > 0, uk, 0))
            var += cu[k] ** 2
    return {"value": y, "u": np.sqrt(var), "cu": cu}


def compare(model, inputs, corr=None, p=P_DEFAULT, k=None, seed=20261119, lang="de", unit="", label="", name="") -> dict:
    """Alle vier Verfahren nebeneinander (für die Übersicht „Verfahren vergleichen“)."""
    out = {}
    for m in METHODS:
        try:
            out[m] = evaluate(model, inputs, m, corr, p, k, seed, lang, unit, label, name)
        except UncError as e:
            out[m] = {"method": m, "error": str(e)}
    return out


# ============================================================================== Ausgabe
def _dec_places(U_: float, sig: int = 2) -> int:
    if not U_ or not math.isfinite(U_):
        return 6
    return sig - 1 - math.floor(math.log10(abs(U_)))


def round_pm(y: float, U_: float, sig: int = 2) -> tuple[str, str, int]:
    """Wert und Unsicherheit gerundet (GUM 7.2.6: U auf zwei signifikante Stellen, Wert auf dieselbe Stelle)."""
    if not (U_ > 0) or not math.isfinite(U_):
        return f"{y:.6g}", "0", 0
    d = _dec_places(U_, sig)
    if d > 0:
        return f"{round(y, d):.{d}f}", f"{round(U_, d):.{d}f}", d
    q = 10 ** (-d)
    return f"{round(y / q) * q:.0f}", f"{round(U_ / q) * q:.0f}", d


def _loc(s: str, lang: str) -> str:
    return s.replace(".", ",") if lang == "de" else s


def fmt_result(r: dict, lang: str = "de") -> str:
    """Kurzer Ergebnistext, z. B. „12,34 ± 0,56 mm (k = 2,00; p ≈ 95 %)“."""
    unit = (" " + r["unit"]) if r.get("unit") else ""
    m = r["method"]
    if m in ("gum", "gauss"):
        ys, us, _ = round_pm(r["value"], r["U"])
        ks = f"{r['k']:.2f}"
        tail = (f" (k = {_loc(ks, lang)}; p ≈ {round(r['p'] * 100):d} %)" if m == "gum"
                else (" (Standardunsicherheit)" if lang == "de" else " (standard uncertainty)"))
        return f"{_loc(ys, lang)} ± {_loc(us, lang)}{unit}{tail}"
    if m == "mc":
        Um = max(r["U_minus"], r["U_plus"])
        ys, _, d = round_pm(r["value"], Um)
        lo, hi = (f"{round(v, max(d, 0)):.{max(d, 0)}f}" for v in (r["lo"], r["hi"]))
        return (f"{_loc(ys, lang)}{unit}, {round(r['p'] * 100):d} %: [{_loc(lo, lang)}; {_loc(hi, lang)}]{unit}"
                + (f" (u = {_loc(round_pm(r['value'], r['u'])[1], lang)})"))
    ys, _, d = round_pm(r["value"], max(r.get("U_minus", 0), r.get("U_plus", 0)) or abs(r["value"]) * 1e-6)
    dm = max(d, 0)
    lo, hi = f"{r['lo']:.{dm}f}", f"{r['hi']:.{dm}f}"
    return (f"{_loc(ys, lang)}{unit} ({'min.' if lang == 'de' else 'min'} {_loc(lo, lang)}, "
            f"{'max.' if lang == 'de' else 'max'} {_loc(hi, lang)})")


NOTE_TEXT = {
    "de": {"nonlinear": "Modell im Bereich ±u von {x} deutlich nichtlinear: GUM (linear) ungenau, Monte Carlo empfohlen",
           "edge": "{x}: Modell bei Wert ± u nicht auswertbar (Definitionsbereich)",
           "ws_corr": "Mit Korrelationen ist die Welch–Satterthwaite-Formel nur eine Näherung",
           "corr_normal": "Korrelierte Grössen werden in Monte Carlo als gemeinsam normalverteilt angenommen (GUM S1 6.4.8)",
           "mc_invalid": "Monte Carlo: ein Teil der Stichproben lag ausserhalb des Definitionsbereichs und wurde verworfen",
           "mc_loop": "Monte Carlo: Modell nicht vektorisierbar, Zahl der Versuche begrenzt (Intervall unsicherer)",
           "mc_max": "Monte Carlo: Höchstzahl der Versuche erreicht, bevor das Intervall auf zwei Stellen stabil war",
           "interior": "Grösstfehler: Extremwert liegt im Inneren der Grenzen, nicht an einer Ecke",
           "linear_bound": "Grösstfehler: mehr als 10 unsichere Grössen, lineare Schranke Σ|cᵢ|aᵢ statt Ecken",
           "gauss_no_corr": "Gausssche Fehlerfortpflanzung berücksichtigt keine Korrelationen",
           "worst_no_corr": "Grösstfehler berücksichtigt keine Korrelationen"},
    "en": {"nonlinear": "Model clearly nonlinear within ±u of {x}: GUM (linear) inaccurate, Monte Carlo recommended",
           "edge": "{x}: model not defined at value ± u",
           "ws_corr": "With correlations the Welch–Satterthwaite formula is only an approximation",
           "corr_normal": "Correlated quantities are sampled as jointly normal in Monte Carlo (GUM S1 6.4.8)",
           "mc_invalid": "Monte Carlo: some trials fell outside the model's domain and were discarded",
           "mc_loop": "Monte Carlo: model not vectorisable, number of trials limited (interval less certain)",
           "mc_max": "Monte Carlo: maximum number of trials reached before the interval was stable to two digits",
           "interior": "Worst case: an extreme value lies inside the limits, not at a corner",
           "linear_bound": "Worst case: more than 10 uncertain quantities, linear bound Σ|cᵢ|aᵢ instead of corners",
           "gauss_no_corr": "Gaussian error propagation ignores correlations",
           "worst_no_corr": "Worst case ignores correlations"},
}


def note_texts(notes, lang="de") -> list[str]:
    T = NOTE_TEXT.get(lang, NOTE_TEXT["de"])
    out = []
    for n in dict.fromkeys(notes or []):
        key, _, x = n.partition(":")
        if key in T:
            out.append(T[key].format(x=x))
    return out


def _jsonable(o):
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (np.floating, np.integer)):
        o = o.item()
    if isinstance(o, float) and not math.isfinite(o):
        return None if math.isnan(o) else ("inf" if o > 0 else "-inf")
    return o


def plain(r: dict) -> dict:
    """Kurzform für geteilte Werte, Projektindex und Datensätze: {u, U, k, p, method, dof}."""
    return {k: r.get(k) for k in ("u", "U", "k", "p", "method", "dof", "lo", "hi") if r.get(k) is not None}


# ============================================================================== Bericht
TX = {
    "de": {"h": ["Grösse", "Wert", "Art", "Verteilung", "$u(x_i)$", "$\\nu_i$", "$c_i$", "$|c_i|\\,u(x_i)$", "Anteil"],
           "cap": "Unsicherheitsbudget für {y} ({m}).", "exact": "exakt",
           "gum": "Die Messunsicherheit von {ys} wurde nach dem Leitfaden zur Angabe der Unsicherheit beim Messen bestimmt "
                  "(GUM, lineare Fortpflanzung, {c1}); die erweiterte Unsicherheit gilt mit k = {k} für eine "
                  "Überdeckungswahrscheinlichkeit von etwa {p} %{dof}.",
           "mc": "Die Messunsicherheit von {ys} wurde mit dem Monte-Carlo-Verfahren nach GUM Supplement 1 bestimmt "
                 "({c1}; {M} Versuche); angegeben ist das wahrscheinlichkeitssymmetrische {p}-%-Überdeckungsintervall.",
           "gauss": "Die Unsicherheit von {ys} wurde mit dem Gaussschen Fehlerfortpflanzungsgesetz aus den "
                    "Standardunsicherheiten der Eingangsgrössen bestimmt ({c1}); angegeben ist die Standardunsicherheit.",
           "worst": "Für {ys} wurde der Grösstfehler aus den Grenzen der Eingangsgrössen bestimmt ({c1}): das Modell wurde "
                    "an allen Kombinationen der Grenzen ausgewertet.",
           "dof": "; effektive Freiheitsgrade nach Welch–Satterthwaite ν = {n}"},
    "en": {"h": ["Quantity", "Value", "Type", "Distribution", "$u(x_i)$", "$\\nu_i$", "$c_i$", "$|c_i|\\,u(x_i)$", "Share"],
           "cap": "Uncertainty budget for {y} ({m}).", "exact": "exact",
           "gum": "The measurement uncertainty of {ys} was evaluated following the Guide to the Expression of Uncertainty "
                  "in Measurement (GUM, linear propagation, {c1}); the expanded uncertainty uses k = {k} for a coverage "
                  "probability of about {p} %{dof}.",
           "mc": "The measurement uncertainty of {ys} was evaluated with the Monte Carlo method of GUM Supplement 1 "
                 "({c1}; {M} trials); the probabilistically symmetric {p} % coverage interval is given.",
           "gauss": "The uncertainty of {ys} was evaluated with the Gaussian law of error propagation from the standard "
                    "uncertainties of the inputs ({c1}); the standard uncertainty is given.",
           "worst": "For {ys} the worst-case deviation was evaluated from the limits of the inputs ({c1}): the model was "
                    "evaluated at every combination of the limits.",
           "dof": "; effective degrees of freedom after Welch–Satterthwaite ν = {n}"},
}


def to_report(b, results: list[dict], lang: str = "de", prefix: str = "") -> dict:
    """Unsicherheitsergebnisse in ein labbundle.Bundle schreiben.

    results: Ausgaben von ``evaluate`` mit ``name`` (Schlüssel), ``label`` und ``unit``. Schreibt je Ergebnis die Werte
    ``<name>-pm`` (Wert ± U), ``<name>-u``, ``<name>-U``, eine Budgettabelle und gibt den Methodentext zurück.
    Zitiert JCGM 100/101, DIN 1319-4, Taylor und die Quellen der Messmittel.
    Rückgabe: {"values", "tables", "cites", "latex"}.
    """
    from labbundle import booktabs, cite, tex_escape

    import labcite as C

    from . import render as RD
    from .sources import REFS

    L = TX.get(lang, TX["de"])
    vals, tables, cites, texts = [], [], [], []
    loc = (lambda s: s.replace(".", "{,}")) if lang == "de" else (lambda s: s)
    for r in results or []:
        if not r or r.get("error") or r.get("value") is None:
            continue
        key = re.sub(r"[^A-Za-z0-9-]", "-", f"{prefix}{r.get('name') or 'y'}").strip("-") or "y"
        unit_tex = (r"\," + RD.unit_tex(r["unit"])) if r.get("unit") else ""
        ck = []
        for rk in r.get("refs") or REF_KEYS[r["method"]]:
            if rk in REFS:
                ck.append(C.to_bib(b, f"unc-{rk}", REFS[rk]))
        for row in r.get("budget") or []:                 # Quellen der Messmittel und Eingangsgrössen
            srcs = [(row.get("source"), row["name"])] + [(prt.get("source") or prt.get("source_key"), prt.get("id") or row["name"])
                                                         for prt in row.get("parts") or []]
            for src, nm in srcs:
                if isinstance(src, str) and src in REFS:
                    ck.append(C.to_bib(b, f"unc-{src}", REFS[src]))
                elif isinstance(src, dict) and (src.get("title") or src.get("doi") or src.get("url")):
                    ck.append(C.to_bib(b, C.key_for("unc", src, str(nm)), src))
        ck = list(dict.fromkeys(ck))
        cites += ck
        m = r["method"]
        if m in ("gum", "gauss"):
            ys, us, _ = round_pm(r["value"], r["U"])
            pm = f"{loc(ys)} \\pm {loc(us)}"
            vals += [(f"{key}-pm", tex_escape(r.get("label") or key), f"$({pm}){unit_tex}$" if unit_tex else f"${pm}$",
                      r.get("text", "")),
                     (f"{key}-U", "U", f"${loc(us)}{unit_tex}$", us)]
        else:
            Um = max(r.get("U_minus") or 0, r.get("U_plus") or 0)
            ys, _, d = round_pm(r["value"], Um or 1e-12)
            dm = max(d, 0)
            lo, hi = f"{r['lo']:.{dm}f}", f"{r['hi']:.{dm}f}"
            vals += [(f"{key}-pm", tex_escape(r.get("label") or key), f"${loc(ys)}{unit_tex}\\;[{loc(lo)};\\,{loc(hi)}]$",
                      r.get("text", ""))]
        if r.get("u") is not None:
            vals.append((f"{key}-u", "u", f"${loc(round_pm(r['value'], r['u'])[1])}{unit_tex}$", round_pm(r["value"], r["u"])[1]))
        rows = []
        for row in r.get("budget") or []:
            nm = f"${RD.sym_tex(row['name'])}$" + (" " + tex_escape(row["label"]) if row.get("label") and row["label"] != row["name"] else "")
            if row.get("exact"):
                rows.append([nm, _tnum(row["value"], lang) + (r"\," + f"${RD.unit_tex(row['unit'])}$" if row.get("unit") else ""),
                             L["exact"], "", "", "", "", "", ""])
                continue
            dof = row.get("dof")
            rows.append([nm, _tnum(row["value"], lang) + (" " + f"${RD.unit_tex(row['unit'])}$" if row.get("unit") else ""),
                         tex_escape(row.get("type") or ""), tex_escape(NAMES.get(lang, NAMES["de"]).get(row.get("dist"), row.get("dist") or "")),
                         _tnum(row["u"], lang), "$\\infty$" if dof in (None, "inf") or (isinstance(dof, float) and not math.isfinite(dof)) else _tnum(dof, lang, 3),
                         _tnum(row["c"], lang), _tnum(row["cu"], lang), _tnum(row.get("share", 0), lang, 3) + r"\,\%"])
        if rows:
            tid = f"{key}-budget"
            b.add_table(tid, booktabs(L["h"], rows, escape_header=False),
                        caption=L["cap"].format(y=tex_escape(r.get("label") or key), m=tex_escape(r.get("method_name") or m)))
            tables.append(tid)
        lab = str(r.get("label") or key)
        ys_txt = f"${RD.sym_tex(lab)}$" if re.fullmatch(r"[A-Za-z]+_[A-Za-z0-9]+", lab) else tex_escape(lab)
        dof_t = ""
        if m == "gum" and r.get("dof") not in (None, "inf") and isinstance(r.get("dof"), (int, float)) and math.isfinite(r["dof"]):
            dof_t = L["dof"].format(n=_tnum(r["dof"], lang, 3))
        args = dict(c1=cite(ck, sep=" ").strip() if ck else "", k=_tnum(r.get("k") or 0, lang, 3),
                    p=round((r.get("p") or 0.95) * 100), dof=dof_t, M=r.get("M", ""))
        gk = (m, tuple(sorted(args.items())))
        if texts and texts[-1][0] == gk:              # gleiches Verfahren, gleiche Angaben: ein Satz für alle Grössen
            texts[-1][1].append(ys_txt)
        else:
            texts.append((gk, [ys_txt], args))
    out = []
    for (m, _), names, args in texts:
        ys = names[0] if len(names) == 1 else ", ".join(names[:-1]) + (" und " if lang == "de" else " and ") + names[-1]
        out.append(L[m].format(ys=ys, **args))
    b.add_values(vals)
    return {"values": [v[0] for v in vals], "tables": tables, "cites": list(dict.fromkeys(cites)), "latex": "\n".join(out)}


def _tnum(v, lang, sig=3) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(f):
        return "$\\infty$"
    s = f"{f:.{sig}g}"
    if "e" in s:
        mnt, ex = s.split("e")
        s = f"{mnt}\\cdot 10^{{{int(ex)}}}"
    s = s.replace(".", "{,}") if lang == "de" else s
    return f"${s}$"

