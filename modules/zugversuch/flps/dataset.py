"""I-03: Zugversuch aus einem Datensatz (`data.table` der Datenaufbereitung).

Ein Datensatz mit Kraft und Verlängerung oder mit Spannung und Dehnung wird als ganzer Zugversuch ausgewertet, genau wie
eine .flps-Datei. Dazu werden die gewählten Spalten in eine kleine JSON-Datei `folio-flps-dataset/1` übersetzt; sie liegt
wie eine Messdatei in der Umgebung, und Neuaufbau, Bericht und Aktualisierung lesen sie über `parser.parse_bytes` wieder.

Die Auswertung arbeitet über der Zeit (Spezifikation Abschnitt 2–4: Steigung im Zeitfenster, Dehnung = (t − t0)·v/L0).
Gibt es eine Verlängerung oder Dehnung, entsteht die Zeit deshalb aus dem zurückgelegten Weg und der
Prüfgeschwindigkeit, t = Σ|ΔL| / v. So ergeben Dehnung, Modul und Rm dieselben Werte wie direkt aus Spannung und Dehnung,
auch wenn die Prüfgeschwindigkeit nicht konstant war. Eine Zeitspalte liefert dann nur die Prüfgeschwindigkeit, wenn keine
angegeben ist. Ohne Weg wird die Zeitspalte benutzt (wie bei der .flps-Datei).

Aus Spannung wird die Kraft F = σ·A0, aus Dehnung die Verlängerung ΔL = ε·L0; beides braucht die Probenmasse.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta

import numpy as np

SCHEMA = "folio-flps-dataset/1"
MAX_POINTS = 200_000
KINDS = {"force": (1, 1, -2), "stress": (-1, 1, -2), "length": (1, 0, 0), "time": (0, 0, 1), "strain": (0, 0, 0)}


class DatasetTestError(ValueError):
    pass


def kind_of(col: dict) -> str | None:
    """force | stress | length | strain | time | None (Text oder andere Grösse)."""
    if col.get("dtype") == "text":
        return None
    from labcalc import units as U
    try:
        _, dims, _ = U.parse_unit(col.get("unit") or "")
    except Exception:  # noqa: BLE001 - unbekannte Einheit: nicht zuordnen
        return None
    if any(abs(x) > 1e-9 for x in dims[3:]):
        return None
    for k, d in KINDS.items():
        if U.deq(dims[:3], d):
            if k == "strain" and not (col.get("unit") or col.get("kind") in ("strain", "ratio", "fraction")):
                return "strain" if any(s in str(col.get("name", "")).lower() for s in ("dehn", "strain", "eps", "ε")) else None
            return k
    return None


def guess(columns: list[dict]) -> dict:
    """Vorschlag {load, ext, t} aus den Einheiten (erste passende Spalte, x-Rolle bevorzugt für den Weg)."""
    by = {}
    for c in columns:
        k = kind_of(c)
        if k:
            by.setdefault(k, []).append(c)
    first = lambda *ks: next((c["key"] for k in ks for c in sorted(by.get(k, []), key=lambda c: c.get("role") != "x")), None)  # noqa: E731
    load = next((c["key"] for k in ("stress", "force") for c in by.get(k, [])), None)
    return {"load": load, "ext": first("strain", "length"), "t": first("time")}


def _cond(header: dict) -> dict:
    """A0, L0, v aus den Bedingungen des Datensatzes (wenn dort mit Einheit angegeben)."""
    from labcalc import units as U
    out = {}
    for name, v in (header.get("conditions") or {}).items():
        val = v.get("value") if isinstance(v, dict) else None
        if not isinstance(val, (int, float)) or isinstance(val, bool):
            continue
        try:
            f, dims, _ = U.parse_unit(v.get("unit") or "")
        except Exception:  # noqa: BLE001
            continue
        n = str(name).lower()
        if U.deq(dims, (2, 0, 0, 0, 0, 0, 0)):
            out.setdefault("a0_mm2", val * f * 1e6)
        elif U.deq(dims, (1, 0, -1, 0, 0, 0, 0)):
            out.setdefault("speed_mm_min", val * f * 60_000)
        elif U.deq(dims, (1, 0, 0, 0, 0, 0, 0)) and ("l0" in n or "mess" in n or "gauge" in n):
            out.setdefault("l0_mm", val * f * 1000)
    return out


def columns_info(ds) -> dict:
    """Spalten mit erkannter Grösse, Rollenvorschlag und Probenmasse aus den Bedingungen (für den Dialog)."""
    cols = [{**{k: c.get(k) for k in ("key", "name", "unit", "dtype", "role")}, "q": kind_of(c)} for c in ds.columns]
    return {"columns": cols, "guess": guess(ds.columns), "geometry": _cond(ds.header), "rows": ds.rows}


def _pos(x, what: str) -> float | None:
    if x in (None, ""):
        return None
    try:
        v = float(str(x).replace(",", "."))
    except ValueError:
        raise DatasetTestError(f"{what}: keine Zahl") from None
    if not math.isfinite(v) or v <= 0:
        raise DatasetTestError(f"{what} muss grösser als 0 sein")
    return v


def _strict(t: np.ndarray, step: float = 2e-6) -> np.ndarray:
    """Streng steigende Zeit: gleiche Zeitstempel würden beim Einlesen wie in der .flps-Datei über eine Sekunde verteilt
    (Abschnitt 2.2) und kämen so aus der Reihenfolge. Gleiche Werte (kein Weg zwischen zwei Zeilen) rücken um 2 µs."""
    t = np.asarray(t, dtype=float)
    k = np.arange(len(t)) * step                                          # s[i] = max(t[i], s[i-1] + step)
    return np.maximum.accumulate(t - k) + k


def make_raw(ds, roles: dict, geo: dict, source: dict) -> tuple[bytes, str, dict]:
    """Datensatz + Zuordnung → (JSON-Bytes, Dateiname, Einstellungen für die Auswertung)."""
    roles = {k: (str(v) if v else None) for k, v in (roles or {}).items()}
    if not roles.get("load"):
        raise DatasetTestError("Bitte die Spalte für Kraft oder Spannung wählen")
    lc = ds.col(roles["load"])
    lk = kind_of(lc)
    if lk not in ("force", "stress"):
        raise DatasetTestError(f"„{lc['name']}“ ({lc.get('unit') or '1'}) ist weder eine Kraft noch eine Spannung")
    ec = ds.col(roles["ext"]) if roles.get("ext") else None
    ek = kind_of(ec) if ec else None
    if ec and ek not in ("length", "strain"):
        raise DatasetTestError(f"„{ec['name']}“ ({ec.get('unit') or '1'}) ist weder eine Verlängerung noch eine Dehnung")
    tc = ds.col(roles["t"]) if roles.get("t") else None
    if tc and kind_of(tc) != "time":
        raise DatasetTestError(f"„{tc['name']}“ ({tc.get('unit') or '1'}) ist keine Zeit")
    if not ec and not tc:
        raise DatasetTestError("Es braucht einen Weg (Verlängerung oder Dehnung) oder eine Zeitspalte")
    a0 = _pos(geo.get("a0_mm2"), "A0")
    l0 = _pos(geo.get("l0_mm"), "L0")
    v = _pos(geo.get("speed_mm_min"), "Prüfgeschwindigkeit")
    if lk == "stress" and a0 is None:
        raise DatasetTestError("A0 fehlt: aus der Spannung wird die Kraft F = σ·A0 (Rm, Rp und E hängen nicht von A0 ab)")
    if ek == "strain" and l0 is None:
        raise DatasetTestError("L0 fehlt: aus der Dehnung wird die Verlängerung ΔL = ε·L0 (Dehnung und E hängen nicht von L0 ab)")

    keep = ds.used_mask() & np.isfinite(ds.si(lc["key"]))
    if ec:
        keep &= np.isfinite(ds.si(ec["key"]))
    if tc:
        keep &= np.isfinite(ds.si(tc["key"]))
    n = int(keep.sum())
    if n < 10:
        raise DatasetTestError(f"Zu wenige gültige Zeilen ({n}); es braucht mindestens 10")
    if n > MAX_POINTS:
        raise DatasetTestError(f"Zu viele Zeilen ({n}); höchstens {MAX_POINTS}")
    L = ds.si(lc["key"])[keep]
    F = L / 1e6 * a0 if lk == "stress" else L                             # Pa → MPa · mm² = N
    dL = None
    if ec:
        e = ds.si(ec["key"])[keep]
        dL = e * l0 if ek == "strain" else e * 1000.0                     # mm
        dL = dL - dL[0]
    tt = ds.si(tc["key"])[keep] if tc else None
    notes = []
    if dL is not None:
        path = np.concatenate([[0.0], np.cumsum(np.abs(np.diff(dL)))])
        if path[-1] <= 0:
            raise DatasetTestError("Der Weg ändert sich nicht – Verlängerung oder Dehnung prüfen")
        if v is None and tt is not None and tt[-1] != tt[0]:
            v = float(path[-1] / abs(tt[-1] - tt[0]) * 60.0)              # mittlere Geschwindigkeit aus der Zeitspalte
            notes.append("Prüfgeschwindigkeit aus der Zeitspalte gemittelt")
        if v is None:
            v = 1.0
            notes.append("Prüfgeschwindigkeit nicht angegeben: 1 mm/min angenommen; sie verschiebt nur die Zeitachse")
        t = path / (v / 60.0)
        time_from = "elongation"
    else:
        t = tt - tt[0]
        if np.any(np.diff(t) < 0):
            raise DatasetTestError("Die Zeit läuft nicht vorwärts – Spalte oder Reihenfolge prüfen")
        time_from = "column"
    t = _strict(t)
    sign = 1.0 if geo.get("compression") else -1.0                        # IMADA: Zug negativ
    fmax = float(np.max(np.abs(F))) or 1.0
    dp = int(min(5, max(0, math.ceil(-math.log10(fmax / 1e4)))))         # Anzeigeauflösung ≈ Fmax / 10⁴
    raw = {"schema": SCHEMA, "title": str(source.get("title") or ds.header.get("title") or "Datensatz")[:120],
           "source": source, "start": source.get("created") or "",
           "roles": {r: (c and {"key": c["key"], "name": c["name"], "unit": c.get("unit") or "", "q": q})
                     for r, c, q in (("load", lc, lk), ("ext", ec, ek), ("t", tc, "time" if tc else None))},
           "geometry": {"a0_mm2": a0, "l0_mm": l0, "speed_mm_min": v, "compression": bool(geo.get("compression")),
                        "displacement_source": geo.get("displacement_source") or None},
           "time_from": time_from, "notes": notes, "decimals": dp,
           "t": [round(float(x), 6) for x in t], "F": [round(float(sign * abs(x)), dp + 2) for x in F],
           "dL": [round(float(x), 6) for x in dL] if dL is not None else None}
    cfg = {"specimen_mode": "manuell", "a0_mm2": a0, "l0_mm": l0, "speed_mm_min": v,
           "displacement_source": raw["geometry"]["displacement_source"]}
    safe = "".join(ch if ch.isalnum() or ch in " -_()." else "_" for ch in raw["title"]).strip() or "Datensatz"
    return json.dumps(raw, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), f"{safe}.json", cfg


def is_dataset(data: bytes) -> bool:
    return data[:1] == b"{" and SCHEMA.encode() in data[:400]


def parse(data: bytes, path: str = ""):
    """JSON `folio-flps-dataset/1` → FlpsFile (Kraft in N, Weg in µm, Zeitstempel aus der Zeitachse)."""
    from .parser import FlpsError, FlpsFile, Point
    try:
        d = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise FlpsError(f"Datensatzdatei unlesbar ({e})") from None
    if not isinstance(d, dict) or d.get("schema") != SCHEMA:
        raise FlpsError("Keine Datensatzdatei des Zugversuchs")
    t, F, dL = d.get("t") or [], d.get("F") or [], d.get("dL")
    if not t or len(t) != len(F) or (dL is not None and len(dL) != len(F)):
        raise FlpsError("Datensatzdatei: Spalten ungleich lang")
    try:
        start = datetime.fromisoformat(str(d.get("start") or "")[:19])
    except ValueError:
        start = datetime(2000, 1, 1)
    dp = int(d.get("decimals") or 3)
    pts = [Point(num=i + 1, force=float(F[i]), force_decimal_point=dp, force_unit=2,
                 displacement=int(round(float(dL[i]) * 1000)) if dL is not None else 0, displacement_unit=4,
                 timestamp=start + timedelta(seconds=float(t[i]))) for i in range(len(t))]
    src = d.get("source") or {}
    return FlpsFile(path=path, serial_number="", model_name="Datensatz", comment=str(d.get("title") or ""),
                    gauge_series=None, points=pts,
                    origin={"title": d.get("title"), "share": src.get("share"), "version": src.get("version"),
                            "mode": src.get("mode"), "producer": src.get("producer") or {}, "roles": d.get("roles") or {},
                            "geometry": d.get("geometry") or {}, "time_from": d.get("time_from"), "notes": d.get("notes") or []})
