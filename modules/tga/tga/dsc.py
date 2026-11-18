"""DSC/Wärmestrom-Auswertung, wenn der Lauf eine Wärmestromspalte hat (TGA-03; STA-Geräte).

state["dsc"] = {
  "unit": "mW" | "W/g" | "uV",          Einheit der Wärmestromspalte (µV = DTA-Signal, nicht kalibriert)
  "sign": "exo_up" | "endo_up",         Darstellungskonvention der Datei (NETZSCH/DIN 51007: exo nach oben)
  "peaks": [{"lo": °C, "hi": °C}],       Bereiche für Peaks (Basislinie linear zwischen den Bereichsenden)
  "tg":    [{"lo": °C, "hi": °C}],       Bereiche für Glasübergänge (Basislinien vor und nach der Stufe)
}

Verfahren nach ISO 11357-1 (Peakintegration, extrapolierte Onset/Endset-Temperatur als Schnitt der Wendetangente mit
der Basislinie) und ISO 11357-2 (Glasübergang: Mittelpunkttemperatur bei halber Stufenhöhe, Tangenten-Onset).
Enthalpie = Fläche über der Zeit / Einwaage; endotherm positiv. Kalibrierung der Temperatur und des Wärmestroms
(ISO 11357-1, ASTM E967 bzw. E968) ist Sache des Geräts; das Modul rechnet mit den Dateiwerten.
"""
from __future__ import annotations

import numpy as np

REFS = ["iso11357-1", "iso11357-2", "astm-e967", "astm-e793"]
UNITS = ("mW", "W/g", "uV")


class DSCError(ValueError):
    pass


def _sel(T, t, hf, lo, hi):
    lo, hi = float(min(lo, hi)), float(max(lo, hi))
    k = np.nonzero(np.isfinite(T) & np.isfinite(hf) & (T >= lo) & (T <= hi))[0]
    if len(k) < 12:
        raise DSCError(f"Bereich {lo:g}–{hi:g} °C enthält zu wenige Messpunkte")
    # nur der erste zusammenhängende Abschnitt (Heizsegment), falls die Temperatur den Bereich mehrfach durchläuft
    gaps = np.nonzero(np.diff(k) > 1)[0]
    if len(gaps):
        k = k[: gaps[0] + 1]
    return T[k], t[k] * 60.0, hf[k]


def _edge(n: int) -> int:
    return max(3, n // 40)


def peak(T, t, hf, lo, hi, unit="mW", sign="exo_up", m0=None) -> dict:
    """Ein Peak im Bereich lo..hi: lineare Basislinie (über der Zeit), Fläche, Spitze, Onset, Endset."""
    x, ts, y = _sel(np.asarray(T, float), np.asarray(t, float), np.asarray(hf, float), lo, hi)
    e = _edge(len(x))
    t0, t1 = ts[:e].mean(), ts[-e:].mean()
    y0, y1 = y[:e].mean(), y[-e:].mean()
    base = y0 + (y1 - y0) * (ts - t0) / (t1 - t0 if t1 != t0 else 1.0)
    d = y - base
    i = int(np.argmax(np.abs(d)))
    endo_dir = -1.0 if sign == "exo_up" else 1.0
    kind = "endo" if np.sign(d[i]) == endo_dir else "exo"
    area = float(np.trapezoid(d, ts)) if hasattr(np, "trapezoid") else float(np.trapz(d, ts))
    out = {"lo": float(x[0]), "hi": float(x[-1]), "kind": kind, "T_peak": float(x[i]), "height": float(abs(d[i])),
           "area": abs(area), "area_unit": {"mW": "mJ", "W/g": "J/g", "uV": "µV·s"}[unit]}
    # Wendetangenten: grösste Steigung |dd/dT| vor bzw. nach der Spitze
    g = np.gradient(d, x)
    for side, rng in (("T_onset", range(0, i)), ("T_endset", range(i + 1, len(x)))):
        rng = [j for j in rng if np.isfinite(g[j]) and g[j] != 0]
        if not rng:
            out[side] = None
            continue
        j = max(rng, key=lambda q: abs(g[q]) * (1 if np.sign(d[q]) == np.sign(d[i]) else 0))
        Tc = float(x[j] - d[j] / g[j])
        out[side] = Tc if x[0] - 1 <= Tc <= x[-1] + 1 else None
    if unit == "mW":
        if m0:
            out["dH"] = abs(area) / float(m0)            # mJ/mg = J/g
        else:
            out["note"] = "Einwaage fehlt: Enthalpie nur als Fläche in mJ"
    elif unit == "W/g":
        out["dH"] = abs(area)
    else:
        out["note"] = "µV-Signal ohne Kalibrierung: nur Fläche, keine Enthalpie"
    if out.get("dH") is not None:
        out["dH_signed"] = out["dH"] if kind == "endo" else -out["dH"]
    return out


def _line(x, y):
    A = np.vstack([x, np.ones_like(x)]).T
    a, b = np.linalg.lstsq(A, y, rcond=None)[0]
    return float(a), float(b)


def glass(T, t, hf, lo, hi, unit="mW", m0=None, rate=None) -> dict:
    """Glasübergang im Bereich lo..hi nach ISO 11357-2: Basislinien aus dem ersten und letzten Viertel."""
    x, ts, y = _sel(np.asarray(T, float), np.asarray(t, float), np.asarray(hf, float), lo, hi)
    q = max(4, len(x) // 4)
    a1, b1 = _line(x[:q], y[:q])
    a2, b2 = _line(x[-q:], y[-q:])
    f1, f2 = a1 * x + b1, a2 * x + b2
    mid = (f1 + f2) / 2
    s = np.sign(y - mid)
    cross = np.nonzero(np.diff(s) != 0)[0]
    cross = [c for c in cross if q // 2 <= c <= len(x) - q // 2] or list(cross)
    if not len(cross):
        raise DSCError(f"im Bereich {lo:g}–{hi:g} °C keine Stufe gefunden")
    c = cross[0]
    w = (mid[c] - y[c]) / ((y[c + 1] - y[c]) - (mid[c + 1] - mid[c]))
    Tg = float(x[c] + w * (x[c + 1] - x[c]))
    step = float((a2 * Tg + b2) - (a1 * Tg + b1))
    g = np.gradient(y, x)
    inner = range(q // 2, len(x) - q // 2)
    j = max(inner, key=lambda k: abs(g[k]) if np.sign(g[k]) == np.sign(step) else 0)
    tan_b = y[j] - g[j] * x[j]
    T_on = (tan_b - b1) / (a1 - g[j]) if g[j] != a1 else None
    T_end = (tan_b - b2) / (a2 - g[j]) if g[j] != a2 else None
    out = {"lo": float(x[0]), "hi": float(x[-1]), "Tg_mid": Tg, "T_onset": None if T_on is None else float(T_on),
           "T_endset": None if T_end is None else float(T_end), "step": abs(step),
           "step_unit": {"mW": "mW", "W/g": "W/g", "uV": "µV"}[unit]}
    beta = float(rate) / 60.0 if rate else None                   # K/s
    if beta:
        if unit == "mW" and m0:
            out["dcp"] = abs(step) / float(m0) / beta             # (mW/mg)/(K/s) = J/(g·K)
        elif unit == "W/g":
            out["dcp"] = abs(step) / beta
    return out


def evaluate(run, cfg: dict) -> dict | None:
    """Alle konfigurierten Peaks und Glasübergänge eines Laufs; Fehler je Bereich, nie für den ganzen Lauf."""
    hf = run.extra.get("hf")
    if hf is None or not cfg:
        return None
    unit = cfg.get("unit") if cfg.get("unit") in UNITS else run.meta.get("hf_unit") if run.meta.get("hf_unit") in UNITS else "mW"
    sign = "endo_up" if cfg.get("sign") == "endo_up" else "exo_up"
    m0 = run.m0 if run.m0 else None
    t = run.time()
    out = {"unit": unit, "sign": sign, "m0": m0, "rate": run.meta.get("rate"), "peaks": [], "tg": [], "refs": REFS}
    for p in cfg.get("peaks") or []:
        try:
            out["peaks"].append(peak(run.T, t, hf, float(p["lo"]), float(p["hi"]), unit, sign, m0))
        except (DSCError, KeyError, TypeError, ValueError) as e:
            out["peaks"].append({"lo": p.get("lo"), "hi": p.get("hi"), "error": str(e)})
    for p in cfg.get("tg") or []:
        try:
            out["tg"].append(glass(run.T, t, hf, float(p["lo"]), float(p["hi"]), unit, m0, run.meta.get("rate")))
        except (DSCError, KeyError, TypeError, ValueError, np.linalg.LinAlgError) as e:
            out["tg"].append({"lo": p.get("lo"), "hi": p.get("hi"), "error": str(e)})
    return out
