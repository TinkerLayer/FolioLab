"""DP-13: Spektren aus einem Datensatz (`data.table`) der Datenaufbereitung.

x-Spalte = Wellenzahl in cm⁻¹ (Einheit 1/cm oder 1/m) oder Wellenlänge (µm, nm, … – umgerechnet als ν̃ = 1/λ, nur
für positive Werte); jede gewählte y-Spalte wird ein Spektrum mit dem Spaltennamen. y-Einheit aus der Spalte:
dimensionslos = Absorbanz (oder Transmission/Reflexion als Bruchteil, wenn der Name es sagt), % = Transmission
(Reflexion, wenn der Name es sagt); eine Wahl in der Oberfläche geht vor. Alles andere wird abgelehnt, ebenso eine
x-Spalte ohne Einheit. Ausgeschlossene Zeilen bleiben weg.

Jedes Spektrum wird als JCAMP-DX gespeichert (mit der Herkunft im Feld ##$FOLIO DATASET) und über `load_bytes` wieder
eingelesen – so übersteht es Neustart, Umgebungswechsel und Bericht-Neuaufbau wie eine geladene Datei.
"""
from __future__ import annotations

import json
import re

import numpy as np

from .readers import DATASET_LDR, ReadError, Spectrum, to_jcamp

YCHOICE = ("auto", "A", "T", "R", "KM", "LR")
_YNAME = {"A": "Absorbanz", "T": "Transmission", "R": "Reflexion", "KM": "Kubelka-Munk", "LR": "log(1/R)"}


def _units():
    from labcalc import units as U
    return U


def _same(unit: str, ref: str) -> bool:
    U = _units()
    try:
        return U.deq(U.parse_unit(unit)[1], U.parse_unit(ref)[1])
    except U.UnitError:
        return False


def _no_unit(unit: str) -> bool:
    return (unit or "").strip() in ("", "-")


def x_values(ds, key: str) -> tuple[np.ndarray, str]:
    """Wellenzahl in cm⁻¹ und eine Notiz zur Umrechnung; ReadError, wenn die Spalte keine Wellenzahl/Wellenlänge ist."""
    c = ds.col(key)
    unit = (c.get("unit") or "").strip()
    if c["dtype"] != "number":
        raise ReadError(f"Spalte „{c['name']}“ ist Text; für die x-Achse werden Zahlen gebraucht")
    if _no_unit(unit):
        raise ReadError(f"Spalte „{c['name']}“ hat keine Einheit; für die x-Achse wird eine Wellenzahl (1/cm) oder eine "
                        "Wellenlänge (µm, nm) gebraucht (Einheit in der Datenaufbereitung setzen)")
    if _same(unit, "1/cm"):
        return ds.in_unit(key, "1/cm"), ""
    if _same(unit, "m"):
        lam = ds.si(key)                                   # Meter
        ok = np.isfinite(lam)
        if (lam[ok] <= 0).any():
            raise ReadError(f"Spalte „{c['name']}“: Wellenlängen müssen positiv sein, um sie in Wellenzahlen umzurechnen")
        with np.errstate(divide="ignore", invalid="ignore"):
            return 0.01 / lam, f"aus Wellenlänge [{unit}] umgerechnet (ν̃ = 1/λ)"
    raise ReadError(f"Spalte „{c['name']}“ ({unit}) passt nicht zur x-Achse: erwartet eine Wellenzahl (1/cm) "
                    "oder eine Wellenlänge (µm, nm)")


def y_kind(c: dict, choice: str = "auto") -> str:
    """y-Einheit eines Spektrums (A, T, R, KM, LR) aus Wahl, Spaltenname und Einheit."""
    if choice in _YNAME:
        return choice
    n, unit = str(c.get("name") or "").lower(), (c.get("unit") or "").strip()
    if re.search(r"refl|remission|%\s*r\b", n):
        return "R"
    if re.search(r"trans|%\s*t\b", n):
        return "T"
    if re.search(r"kubelka|\bk-?m\b", n):
        return "KM"
    if re.search(r"abs|extinkt", n):
        return "A"
    return "T" if (_same(unit, "1") and not _no_unit(unit) and unit != "1") else "A"


def y_values(ds, key: str, choice: str = "auto") -> tuple[np.ndarray, str]:
    c = ds.col(key)
    unit = (c.get("unit") or "").strip()
    if c["dtype"] != "number":
        raise ReadError(f"Spalte „{c['name']}“ ist Text; ein Spektrum braucht Zahlen")
    if not _same(unit or "1", "1"):
        raise ReadError(f"Spalte „{c['name']}“ ({unit}) ist keine Absorbanz oder Transmission: erwartet dimensionslos oder %")
    k = y_kind(c, choice)
    f = _units().parse_unit(unit or "1")[0]
    if k in ("A", "KM", "LR"):
        if abs(f - 1.0) > 1e-12:
            raise ReadError(f"Spalte „{c['name']}“ ({unit}): {_YNAME[k]} ist dimensionslos, nicht in {unit} – "
                            "für Prozentwerte Transmission oder Reflexion wählen")
        return ds.values(key).astype(float), k
    if _no_unit(unit):                                      # Skala unbekannt: wie beim Einlesen von Dateien
        v = ds.values(key).astype(float)
        mx = float(np.nanmax(v)) if np.isfinite(v).any() else 0.0
        return (v * 100.0 if mx <= 1.5 else v), k
    return ds.in_unit(key, "%"), k                         # 1 (Bruchteil), %, ‰ -> %


def guess(c: dict) -> str:
    """Vorschlag für die Oberfläche: "x" (Wellenzahl, Wellenlänge), "y" (dimensionslos/%) oder ""."""
    if c.get("dtype") == "text":
        return ""
    unit = (c.get("unit") or "").strip()
    if not _no_unit(unit) and (_same(unit, "1/cm") or _same(unit, "m")):
        return "x"
    return "y" if _same(unit or "1", "1") else ""


def make_raws(ds, xkey: str, ykeys, choice: str, source: dict) -> list[tuple[bytes, str]]:
    """Datensatz + Spaltenwahl -> [(JCAMP-Inhalt, Dateiname)] je y-Spalte."""
    ykeys = [str(k) for k in (ykeys or []) if k]
    if not xkey:
        raise ReadError("Bitte die x-Spalte (Wellenzahl) wählen.")
    if not ykeys:
        raise ReadError("Bitte mindestens eine y-Spalte wählen.")
    if xkey in ykeys:
        raise ReadError("Die x-Spalte kann nicht zugleich ein Spektrum sein.")
    if choice not in YCHOICE:
        raise ReadError(f"y-Einheit {choice} unbekannt")
    used = ds.used_mask()
    x, note = x_values(ds, xkey)
    cx = ds.col(xkey)
    title = str(ds.header.get("title") or "Datensatz")
    stem0 = re.sub(r"[^\w\-]+", "_", title).strip("_")[:40] or "Datensatz"
    out = []
    for k in dict.fromkeys(ykeys):
        y, yu = y_values(ds, k, choice)
        c = ds.col(k)
        keep = used & np.isfinite(x) & np.isfinite(y)
        sp = Spectrum(str(c["name"])[:120], x[keep], y[keep], yu)
        if len(sp.x) < 10:
            raise ReadError(f"Spalte „{c['name']}“: zu wenige gültige Punkte ({len(sp.x)}) für ein Spektrum")
        if sp.x[0] < 0 or sp.x[-1] > 50000:
            raise ReadError(f"Spalte „{cx['name']}“: x-Werte passen nicht zu Wellenzahlen ({sp.x[0]:g} … {sp.x[-1]:g} cm⁻¹)")
        src = dict(source or {}, columns={"x": {"key": cx["key"], "name": cx["name"], "unit": cx.get("unit") or ""},
                                          "y": {"key": c["key"], "name": c["name"], "unit": c.get("unit") or ""}},
                   yunit=yu, choice=choice, excluded=int((~used).sum()))
        if note:
            src["x_note"] = note
        js = json.dumps(src, ensure_ascii=False, separators=(",", ":")).replace("$$", "$ $")
        raw = to_jcamp(sp, sp.name, {DATASET_LDR: js}).encode("utf-8")
        stem = re.sub(r"[^\w\-]+", "_", str(c["name"])).strip("_")[:40] or c["key"]
        out.append((raw, f"{stem0}_{stem}_v{src.get('version', 1)}.jdx"))
    return out
