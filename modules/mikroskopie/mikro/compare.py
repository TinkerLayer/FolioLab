"""I-04: Vergleichsverteilung aus einem Datensatz (`data.table` der Datenaufbereitung).

Eine Längenspalte eines Datensatzes (z. B. Partikelgrössen aus der Laserbeugung oder aus einer anderen Auswertung) wird
über die Grössenverteilung der Partikelanalyse gelegt; beide bekommen D10/D50/D90 anzahlgewichtet (Q0) und
Dv10/Dv50/Dv90 volumengewichtet (Q3, aus d³), mit derselben Quantildefinition wie `measure`. Jeder Datensatzwert gilt
als ein Teilchen; Kennwerte einer Laserbeugungsverteilung (meist Q3) sind keine Einzelwerte und gehören nicht hierher. Die Werte
werden in Metern gespeichert, damit eine spätere Änderung der Bildkalibrierung (µm ↔ nm) nichts verfälscht; im Bericht
stehen sie in der Einheit der Kalibrierung. Der Arbeitsstand trägt die Werte selbst, damit der Bericht ohne den Datensatz
neu gebaut werden kann, und Freigabe + Version, damit die Herkunftskette die benutzte Version festhält.
"""
from __future__ import annotations

import math

import numpy as np

LENGTH = (1, 0, 0, 0, 0, 0, 0)
MAX_VALUES = 50_000


class CompareError(ValueError):
    pass


def _dims(unit: str):
    from labcalc import units as U
    try:
        f, dims, _ = U.parse_unit(unit or "")
    except Exception:  # noqa: BLE001 - unbekannte Einheit
        return None, None
    return f, dims


def is_length(col: dict) -> bool:
    if col.get("dtype") == "text":
        return False
    from labcalc import units as U
    f, dims = _dims(col.get("unit") or "")
    return dims is not None and U.deq(dims, LENGTH)


def metres_per(unit: str) -> float:
    """Faktor Einheit -> m für die Kalibriereinheit des Bildes (µm, nm, mm, cm, m, in)."""
    if not unit or unit == "px":
        raise CompareError("Das Bild hat keinen Massstab – erst kalibrieren, dann vergleichen")
    from labcalc import units as U
    f, dims = _dims({"um": "µm", "micron": "µm"}.get(unit, unit))
    if dims is None or not U.deq(dims, LENGTH):
        raise CompareError(f"Kalibriereinheit „{unit}“ ist keine Länge")
    return float(f)


def length_columns(ds) -> list[dict]:
    out = []
    used = ds.used_mask()
    for c in ds.columns:
        if is_length(c):
            v = ds.si(c["key"])[used]
            out.append({"key": c["key"], "name": c.get("name") or c["key"], "unit": c.get("unit") or "",
                        "n": int(np.sum(np.isfinite(v) & (v > 0)))})
    return out


def values_m(ds, key: str) -> np.ndarray:
    col = ds.col(key)
    if not is_length(col):
        raise CompareError(f"„{col.get('name') or key}“ ({col.get('unit') or 'ohne Einheit'}) ist keine Länge")
    v = ds.si(key)[ds.used_mask()]
    v = v[np.isfinite(v) & (v > 0)]
    if v.size < 3:
        raise CompareError(f"„{col.get('name') or key}“ hat nur {v.size} positive Werte; es braucht mindestens 3")
    if v.size > MAX_VALUES:
        raise CompareError(f"Zu viele Werte ({v.size}); höchstens {MAX_VALUES}")
    return v


def stats(v, w=None) -> dict:
    """n, D10/D50/D90 anzahlgewichtet (Q0), Dv10/Dv50/Dv90 volumengewichtet (Q3, Gewicht d³), Mittelwert und
    Standardabweichung (Q0). Gleiche Quantildefinition wie die Partikelanalyse (measure.wquantile, Mittelpunktsregel),
    damit Partikel und Datensatz auf derselben Basis verglichen werden. w: Anzahlgewichte (Partikel: Randkorrektur),
    für Datensatzwerte 1 – jeder Wert gilt als ein Teilchen."""
    from .measure import wmean_sd, wquantile
    v = np.asarray(v, dtype=float)
    w = np.ones_like(v) if w is None else np.asarray(w, dtype=float)
    ok = np.isfinite(v) & np.isfinite(w) & (w > 0)
    v, w = v[ok], w[ok]
    if not v.size:
        return {"n": 0, "D10": None, "D50": None, "D90": None, "Dv10": None, "Dv50": None, "Dv90": None,
                "mean": None, "sd": None}
    d10, d50, d90 = wquantile(v, w, (0.1, 0.5, 0.9))
    v10, v50, v90 = wquantile(v, w * v ** 3, (0.1, 0.5, 0.9))
    mean, sd = wmean_sd(v, w)
    return {"n": int(v.size), "D10": d10, "D50": d50, "D90": d90, "Dv10": v10, "Dv50": v50, "Dv90": v90,
            "mean": mean, "sd": sd}


def in_unit(cmp: dict, unit: str) -> np.ndarray:
    """Gespeicherte Werte (m) in der Kalibriereinheit des Bildes."""
    return np.asarray(cmp.get("values_m") or [], dtype=float) / metres_per(unit)


def record(ds, env: dict, sid: str, mode: str, key: str) -> dict:
    """Arbeitsstand der Vergleichsverteilung (geht mit in den Bericht)."""
    col = ds.col(key)
    v = values_m(ds, key)
    p = env.get("producer") or {}
    return {"share": sid, "version": env["version"], "mode": mode, "key": key, "name": col.get("name") or key,
            "unit": col.get("unit") or "", "title": env.get("title") or "", "created": env.get("created"),
            "producer": {k: p.get(k) for k in ("module", "env_name", "item_name")},
            "values_m": [float(f"{x:.6g}") for x in v]}


def ratio(a, b):
    return a / b if (a is not None and b and math.isfinite(a) and math.isfinite(b)) else None
