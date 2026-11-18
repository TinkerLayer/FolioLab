"""Bearbeitungsschritte für TGA-Läufe (Protokoll wie im FTIR-Modul) sowie DTG und Segmente.

Jeder Schritt ist ein dict {"op": ..., Parameter}; die Liste wird immer auf den Originallauf angewendet, in der
Oberfläche, im Export und im Bericht gleich. Numerik ohne SciPy (Savitzky-Golay über Kleinste-Quadrate-Koeffizienten,
Savitzky & Golay 1964, doi:10.1021/ac60214a047).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .readers import Run


class OpError(ValueError):
    pass


def P(key, label, type="number", default=None, **kw):
    return {"key": key, "label": label, "type": type, "default": default, **kw}


OPS = {
    "ref_mass": {"de": "Bezugsmasse (100 %) festlegen", "en": "Set reference mass (100 %)", "params": [
        P("mode", "Bezug", "select", "initial", options=[["initial", "Einwaage / erster Wert"], ["at_T", "Masse bei Temperatur …"],
                                                         ["at_t", "Masse nach Zeit …"], ["value", "Masse von Hand [mg]"]]),
        P("T", "Temperatur [°C] (z. B. nach Trocknung)", default=120), P("t", "Zeit [min]", default=0),
        P("value", "Masse [mg]", default=0)]},
    "cut": {"de": "Bereich ausschneiden", "en": "Cut range", "params": [
        P("axis", "Achse", "select", "T", options=[["T", "Temperatur [°C]"], ["t", "Zeit [min]"]]),
        P("lo", "von", default=30), P("hi", "bis", default=900)]},
    "segments": {"de": "Segmente behalten", "en": "Keep segments", "params": [
        P("keep", "Segmentnummern (z. B. 1,3)", "text", "1")]},
    "tcal": {"de": "Temperaturkalibrierung", "en": "Temperature calibration", "params": [
        P("a", "Verschiebung a [K]", default=0), P("b", "Steigung b", default=1, step=0.0001)]},
    "buoyancy": {"de": "Auftriebskorrektur (linear)", "en": "Buoyancy correction (linear)", "params": [
        P("c", "scheinbare Zunahme [µg/K]", default=0, step=0.01), P("T0", "ab Temperatur [°C]", default=25)]},
    "smooth": {"de": "Masse glätten", "en": "Smooth mass", "params": [
        P("method", "Verfahren", "select", "sg", options=[["sg", "Savitzky-Golay"], ["mean", "Gleitender Mittelwert"]]),
        P("points", "Fensterbreite [Punkte, ungerade]", default=11, min=3, max=301, step=2),
        P("order", "Polynomgrad (Savitzky-Golay)", default=2, min=1, max=5, step=1)]},
    "resample": {"de": "Gleichmässig neu abtasten", "en": "Resample", "params": [
        P("step", "Zeitschritt [min]", default=0.1, min=0.001)]},
    "to_mg": {"de": "In mg umrechnen", "en": "Convert to mg", "params": []},
}


@dataclass
class Proc:
    run: Run
    steps: list = field(default_factory=list)


# ----------------------------------------------------------------------------- Numerik (wie ftir/process.py)
def sg_coeffs(window: int, order: int, deriv: int = 0) -> np.ndarray:
    window = max(3, int(window) | 1)
    order = min(int(order), window - 1)
    k = window // 2
    A = np.vander(np.arange(-k, k + 1, dtype=float), order + 1, increasing=True)
    c = np.linalg.pinv(A)[deriv] * math.factorial(deriv)
    return c[::-1]


def savgol(y: np.ndarray, window: int, order: int, deriv: int = 0, dx: float = 1.0) -> np.ndarray:
    y = np.asarray(y, dtype=float)
    window = max(3, int(window) | 1)
    if window > len(y):
        window = len(y) if len(y) % 2 else len(y) - 1
    if window < 3:
        return np.gradient(y) if deriv == 1 else y.copy()
    order = min(int(order), window - 1)
    k = window // 2
    c = sg_coeffs(window, order, deriv)
    yp = np.concatenate([2 * y[0] - y[k:0:-1], y, 2 * y[-1] - y[-2:-k - 2:-1]])
    out = np.convolve(yp, c, mode="valid")
    return out / (dx ** deriv) if deriv else out


def moving_mean(y: np.ndarray, window: int) -> np.ndarray:
    window = max(1, int(window) | 1)
    k = window // 2
    yp = np.concatenate([np.full(k, y[0]), y, np.full(k, y[-1])])
    return np.convolve(yp, np.ones(window) / window, mode="valid")


def _num(st, key, dflt):
    try:
        v = float(st.get(key, dflt))
    except (TypeError, ValueError):
        raise OpError(f"Ungültiger Wert für {key}")
    if not math.isfinite(v):
        raise OpError(f"Ungültiger Wert für {key}")
    return v


# ----------------------------------------------------------------------------- Segmente
def rate_of(run: Run, width_min: float = 0.5) -> np.ndarray:
    """Heizrate K/min je Punkt (aus Programmtemperatur, sonst Probentemperatur), über ~width_min geglättet."""
    t = run.time()
    T = run.extra.get("Tprog", run.T)
    if not np.isfinite(T).any() or len(t) < 3:
        return np.zeros(len(t))
    dt = np.median(np.diff(t)) or 1.0
    w = max(3, int(width_min / dt) | 1)
    w = min(w, (len(t) - 1) | 1 if len(t) > 3 else 3)
    Ts = moving_mean(np.nan_to_num(T, nan=float(np.nanmean(T))), w)
    r = np.gradient(Ts, t)
    return r


def segments(run: Run) -> list[dict]:
    """Abschnitte: Heizen, Isotherm, Kühlen; zusätzlich getrennt bei Gaswechsel oder Segmentspalte der Datei."""
    n = len(run.m)
    t = run.time()
    if n < 3:
        return []
    r = rate_of(run)
    kind = np.where(r > 0.3, 1, np.where(r < -0.3, -1, 0))
    if not run.has_T:
        kind[:] = 0
    cut = np.zeros(n, dtype=bool)
    cut[1:] = kind[1:] != kind[:-1]
    for key in ("seg", "gas"):
        a = run.extra.get(key)
        if a is not None:
            cut[1:] |= a[1:] != a[:-1]
    starts = [0] + [int(i) for i in np.nonzero(cut)[0]]
    # sehr kurze Abschnitte (< 0,4 min) dem Vorgänger zuschlagen, ausser bei Gaswechsel/Segmentwechsel
    hard = set()
    for key in ("seg", "gas"):
        a = run.extra.get(key)
        if a is not None:
            hard |= {int(i) + 1 for i in np.nonzero(a[1:] != a[:-1])[0]}
    keep = [starts[0]]
    for s in starts[1:]:
        if s in hard or t[min(s, n - 1)] - t[keep[-1]] >= 0.4:
            keep.append(s)
    # auch das letzte kurze Stück anhängen
    bounds = keep + [n]
    out = []
    names = run.meta.get("gas_names") or []
    for k in range(len(bounds) - 1):
        i0, i1 = bounds[k], bounds[k + 1]
        if i1 - i0 < 2:
            continue
        kk = kind[i0:i1]
        kd = int(np.sign(np.round(np.mean(kk))))
        rr = float(np.median(r[i0:i1]))
        g = run.extra.get("gas")
        gas = names[int(g[i0])] if g is not None and names and int(g[i0]) < len(names) else run.meta.get("gas", "")
        seg = {"i0": i0, "i1": i1, "kind": {1: "heat", 0: "iso", -1: "cool"}[kd], "rate": round(rr, 2),
               "T0": float(run.T[i0]) if run.has_T else None, "T1": float(run.T[i1 - 1]) if run.has_T else None,
               "t0": float(t[i0]), "t1": float(t[i1 - 1]), "gas": gas}
        if out and out[-1]["kind"] == seg["kind"] and out[-1]["gas"] == seg["gas"] and i0 not in hard:
            out[-1].update(i1=i1, T1=seg["T1"], t1=seg["t1"])
        else:
            out.append(seg)
    # sehr kurze Abschnitte (Übergänge) dem Nachbarn mit gleichem Gas zuschlagen
    k = 0
    while k < len(out) and len(out) > 1:
        s = out[k]
        if s["t1"] - s["t0"] < 0.4:
            prev = out[k - 1] if k > 0 else None
            nxt = out[k + 1] if k + 1 < len(out) else None
            if prev is not None and prev["gas"] == s["gas"]:
                prev.update(i1=s["i1"], T1=s["T1"], t1=s["t1"])
                out.pop(k)
                continue
            if nxt is not None and nxt["gas"] == s["gas"]:
                nxt.update(i0=s["i0"], T0=s["T0"], t0=s["t0"])
                out.pop(k)
                continue
        k += 1
    for k, s in enumerate(out, 1):
        s["no"] = k
        s["label"] = {"heat": f"Heizen {s['rate']:.3g} K/min", "iso": "Isotherm", "cool": "Kühlen"}[s["kind"]] + \
            (f", {s['gas']}" if s["gas"] else "")
    return out


def gas_switch(run: Run) -> int | None:
    """Index des ersten Gaswechsels (aus Gasspalte), sonst None."""
    g = run.extra.get("gas")
    if g is None:
        return None
    ch = np.nonzero(g[1:] != g[:-1])[0]
    return int(ch[0] + 1) if len(ch) else None


# ----------------------------------------------------------------------------- DTG
def dtg(run: Run, width_C: float = 4.0, order: int = 2, ref: float | None = None) -> dict:
    """DTG als dm/dt (%/min) und dm/dT (%/°C), Savitzky-Golay über die Punktfolge, Kettenregel für ungleiche Abstände.

    width_C: Fensterbreite in Kelvin (bei Heizrate) bzw. umgerechnet in Punkte; dm/dT ist in isothermen Abschnitten
    nicht definiert (NaN).
    """
    m = run.pct(ref)
    t = run.time()
    n = len(m)
    if n < 7:
        z = np.zeros(n)
        return {"dt": z, "dT": z.copy(), "points": 0}
    rate = run.meta.get("rate") or 10.0
    dt_pt = float(np.median(np.diff(t))) or 1.0
    pts = int(round(width_C / max(1e-6, abs(rate)) / dt_pt))
    pts = max(5, min(pts | 1, (n // 3) | 1))
    dm = savgol(m, pts, order, 1)
    dti = savgol(t, pts, 1, 1)
    dti[np.abs(dti) < 1e-12] = np.nan
    dmdt = dm / dti
    if run.has_T:
        dTi = savgol(np.nan_to_num(run.T, nan=0.0), pts, 1, 1)
        slow = np.abs(dTi / dti) < 0.3          # weniger als 0,3 K/min -> isotherm
        dTi[np.abs(dTi) < 1e-9] = np.nan
        dmdT = dm / dTi
        dmdT[slow] = np.nan
    else:
        dmdT = np.full(n, np.nan)
    return {"dt": dmdt, "dT": dmdT, "points": int(pts)}


# ----------------------------------------------------------------------------- Schritte
def describe_step(st: dict, lang: str = "de") -> str:
    op = st.get("op")
    d = OPS.get(op, {})
    name = d.get("de" if lang == "de" else "en", op)
    if op == "ref_mass":
        mode = st.get("mode", "initial")
        return f"{name}: " + {"initial": "Einwaage", "at_T": f"Masse bei {st.get('T')} °C", "at_t": f"Masse nach {st.get('t')} min",
                              "value": f"{st.get('value')} mg"}.get(mode, mode)
    if op == "cut":
        u = "°C" if st.get("axis", "T") == "T" else "min"
        return f"{name}: {st.get('lo')}–{st.get('hi')} {u}"
    if op == "segments":
        return f"{name}: {st.get('keep')}"
    if op == "tcal":
        return f"{name}: T = {st.get('a', 0)} K + {st.get('b', 1)} · T_gemessen"
    if op == "buoyancy":
        return f"{name}: {st.get('c')} µg/K ab {st.get('T0', 25)} °C"
    if op == "smooth":
        return f"{name}: {'Savitzky-Golay' if st.get('method', 'sg') == 'sg' else 'Mittelwert'}, {st.get('points', 11)} Punkte"
    if op == "resample":
        return f"{name}: {st.get('step')} min"
    return name


def _sub(run: Run, mask) -> Run:
    mask = np.asarray(mask, dtype=bool)
    return run.copy(T=run.T[mask], m=run.m[mask], t=None if run.t is None else run.t[mask],
                    extra={k: v[mask] for k, v in run.extra.items()})


def apply_step(run: Run, st: dict, i: int = 0) -> Run:
    op = st.get("op")
    if op not in OPS:
        raise OpError(f"Schritt {i + 1}: unbekannter Bearbeitungsschritt „{op}“")
    if op == "ref_mass":
        mode = st.get("mode", "initial")
        mg = run.mg()
        base = mg if mg is not None else run.m
        if mode == "initial":
            ref = run.m0 if mg is not None and run.m0 else float(np.median(base[:3]))
        elif mode == "at_T":
            T = _num(st, "T", 120)
            if not run.has_T:
                raise OpError("Keine Temperatur im Lauf")
            idx = np.nonzero(run.T >= T)[0]
            if not len(idx):
                raise OpError(f"Schritt {i + 1}: {T:g} °C wird nicht erreicht")
            ref = float(base[idx[0]])
        elif mode == "at_t":
            tt = run.time()
            ref = float(np.interp(_num(st, "t", 0), tt, base))
        else:
            ref = _num(st, "value", 0)
            if mg is None:
                raise OpError("Bezugsmasse in mg braucht die Einwaage")
        if not ref or ref <= 0:
            raise OpError(f"Schritt {i + 1}: Bezugsmasse ist null")
        meta = dict(run.meta, ref=describe_step(st), ref_mg=ref if mg is not None else None)
        return run.copy(m=base / ref * 100.0, unit="%", meta=meta)
    if op == "cut":
        lo, hi = sorted((_num(st, "lo", 30), _num(st, "hi", 900)))
        a = run.T if st.get("axis", "T") == "T" else run.time()
        mask = (a >= lo) & (a <= hi)
        if mask.sum() < 10:
            raise OpError(f"Schritt {i + 1}: im Bereich liegen kaum Messpunkte")
        return _sub(run, mask)
    if op == "segments":
        try:
            keep = {int(x) for x in str(st.get("keep", "1")).replace(";", ",").split(",") if x.strip()}
        except ValueError:
            raise OpError(f"Schritt {i + 1}: Segmentnummern als Liste, z. B. 1,3")
        mask = np.zeros(len(run.m), dtype=bool)
        for s in segments(run):
            if s["no"] in keep:
                mask[s["i0"]:s["i1"]] = True
        if mask.sum() < 10:
            raise OpError(f"Schritt {i + 1}: Segmente {sorted(keep)} enthalten kaum Punkte")
        return _sub(run, mask)
    if op == "tcal":
        a, b = _num(st, "a", 0), _num(st, "b", 1)
        if not 0.5 < b < 1.5:
            raise OpError("Steigung der Kalibrierung unplausibel")
        ex = dict(run.extra)
        if "Tprog" in ex:
            ex["Tprog"] = a + b * ex["Tprog"]
        return run.copy(T=a + b * run.T, extra=ex)
    if op == "buoyancy":
        c = _num(st, "c", 0) / 1000.0          # mg/K
        T0 = _num(st, "T0", 25)
        dT = np.clip(run.T - T0, 0, None)
        if run.unit == "mg":
            return run.copy(m=run.m - c * dT)
        if not run.m0:
            raise OpError("Auftriebskorrektur in % braucht die Einwaage")
        return run.copy(m=run.m - c * dT / run.m0 * 100.0)
    if op == "smooth":
        n = int(_num(st, "points", 11))
        if st.get("method", "sg") == "mean":
            return run.copy(m=moving_mean(run.m, n))
        return run.copy(m=savgol(run.m, n, int(_num(st, "order", 2))))
    if op == "resample":
        s = _num(st, "step", 0.1)
        tt = run.time()
        if s <= 0 or (tt[-1] - tt[0]) / s > 200000:
            raise OpError("Zeitschritt zu klein")
        if np.any(np.diff(tt) <= 0):
            o = np.argsort(tt, kind="stable")
            tt = tt[o]
            run = run.copy(T=run.T[o], m=run.m[o], t=tt, extra={k: v[o] for k, v in run.extra.items()})
        g = np.arange(tt[0], tt[-1] + 1e-12, s)
        ex = {k: (np.interp(g, tt, v) if k in ("Tprog", "dtg", "hf", "flow") else v[np.clip(np.searchsorted(tt, g), 0, len(tt) - 1)])
              for k, v in run.extra.items()}
        T = np.interp(g, tt, run.T) if run.has_T else np.full(len(g), np.nan)
        return run.copy(t=g, T=T, m=np.interp(g, tt, run.m), extra=ex)
    if op == "to_mg":
        mg = run.mg()
        if mg is None:
            raise OpError("Umrechnung in mg braucht die Einwaage")
        return run.copy(m=mg, unit="mg", meta={k: v for k, v in run.meta.items() if k not in ("ref", "ref_mg")})
    raise OpError(f"Schritt {i + 1}: nicht umgesetzt")


def apply(run: Run, pipeline: list | None, lang: str = "de") -> Proc:
    cur = run
    steps = []
    for i, st in enumerate(pipeline or []):
        if not isinstance(st, dict):
            raise OpError(f"Schritt {i + 1}: ungültig")
        cur = apply_step(cur, st, i)
        steps.append(describe_step(st, lang))
    return Proc(cur, steps)
