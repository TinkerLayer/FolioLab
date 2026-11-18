"""DP-12: Datensätze der Datenaufbereitung (`data.table`) als Messreihen für Arrhenius/Eyring, die Reaktionsordnung
und die Rb–Sr-Isochrone.

`route(envs, req)`:
  {"list": true}   an den Elementrechner adressierte Datensätze: Titel, neueste Version, Spalten mit Einheit, Art und
                   einer Grobeinordnung `dim` (T, t, c, k, 1), damit die Seite passende Spalten vorschlagen kann
  {"id", "mode": "live"|"pin", "version"?, "tool", "cols": {Rolle: Spaltenschlüssel}, "data"?}
                   Zahlen der gewählten Spalten einer Version (live = neueste, pin = die angegebene), umgerechnet in die
                   Einheit, die das Werkzeug erwartet, dazu die Herkunft (`origin`) für Ergebnis und Bericht

Einheiten der Werkzeuge: T in K, t in s, c in mol/L, Umsatz X und Isotopenverhältnisse dimensionslos (% → Anteil).
Eine Geschwindigkeitskonstante behält ihre Konzentrationseinheit, die Zeit wird Sekunde (1/min → s⁻¹,
L/(mol·min) → L mol⁻¹ s⁻¹); eine k-Spalte ohne Einheit bleibt unverändert. Eine Spalte anderer Dimension wird mit einer
Meldung abgelehnt. Zeilen, die im Datensatz ausgeschlossen sind, und Zeilen mit fehlendem Wert in einer der gewählten
Spalten fallen für alle Rollen gemeinsam weg (Wertepaare bleiben beisammen).
"""
from __future__ import annotations

import numpy as np
from labcalc import units as U
from labdataset import DatasetError
from labproject import EnvError
from labshare import DATA_KIND, Sharebox, dataset_of

ME = "elementrechner"
# Werkzeug -> Rollen (Schlüssel, Zielart): K, s, mol/L, "1" dimensionslos, "k" Geschwindigkeitskonstante, "cX" c oder X
TOOLS = {
    "arrhenius": (("T", "K"), ("k", "k")),
    "order": (("t", "s"), ("c", "cX")),
    "rbsr": (("x", "1"), ("y", "1")),
}
ALIAS = {"eyring": "arrhenius"}
DIGITS = 12                     # signifikante Stellen der übergebenen Zahlen (Umrechnung °C → K ohne 298.15000000000003)
_SUP = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
_D1, _DK, _DS, _DC = (U.parse_unit(u)[1] for u in ("1", "K", "s", "mol/L"))


def _rate_exp(d) -> float | None:
    """Exponent a, wenn die Dimension (mol/L)^a / s ist (Geschwindigkeitskonstante der Ordnung 1 − a), sonst None."""
    m, kg, s, A, K, mol, cd = d
    if abs(s + 1) > 1e-9 or any(abs(x) > 1e-9 for x in (kg, A, K, cd)) or abs(m + 3 * mol) > 1e-9:
        return None
    return float(mol)


def _k_target(a: float) -> tuple[str, str]:
    """(Einheit zum Umrechnen, Anzeige) einer Geschwindigkeitskonstante mit Zeit in s."""
    if abs(a) < 1e-9:
        return "1/s", "s⁻¹"
    parse = f"(mol/L)^{a:g}/s"
    if abs(a - round(a)) < 1e-9:
        n = int(round(abs(a)))
        e = "" if n == 1 else str(n).translate(_SUP)
        return parse, (f"mol{e} L⁻{e or '¹'} s⁻¹" if a > 0 else f"L{e} mol⁻{e or '¹'} s⁻¹")
    return parse, f"(mol/L)^{a:g} s⁻¹"


def dim_tag(col: dict) -> str:
    """Grobe Einordnung einer Spalte für Vorschläge: T, t, c, k, 1 oder leer."""
    if col.get("dtype", "number") != "number":
        return ""
    try:
        d = U.parse_unit(col.get("unit") or "")[1]
    except U.UnitError:
        return ""
    for tag, ref in (("1", _D1), ("T", _DK), ("t", _DS), ("c", _DC)):
        if U.deq(d, ref):
            return tag
    return "k" if _rate_exp(d) is not None else ""


def _box(envs) -> Sharebox:
    envs.ensure()
    return Sharebox(envs.suite, envs.project)


def list_datasets(box: Sharebox) -> list[dict]:
    out = []
    for m in box.list(ME, DATA_KIND):
        try:
            env = box.get(m["id"], None, ME)
        except EnvError:
            continue
        h, p = env.get("dataset") or {}, m.get("producer") or {}
        out.append({"id": m["id"], "title": m.get("title"), "latest": m.get("latest"), "modified": m.get("modified"),
                    "rows": h.get("rows"), "producer": {k: p.get(k) for k in ("module", "env_name", "item_name")},
                    "columns": [{**{k: c.get(k) for k in ("key", "name", "unit", "kind", "dtype", "role")}, "dim": dim_tag(c)}
                                for c in h.get("columns") or []]})
    return out


def _target(ds, key: str, want: str, data: str | None) -> tuple[str, str, str | None]:
    """(Einheit zum Umrechnen, Anzeige, data) für eine Spalte und Zielart; lehnt andere Dimensionen ab."""
    c = ds.col(key)
    name, unit = c["name"], c.get("unit") or ""
    if c["dtype"] != "number":
        raise DatasetError(f"Spalte „{name}“ enthält Text, keine Zahlen")
    d = U.parse_unit(unit)[1]
    if want == "k":
        if U.deq(d, _D1):                                  # k ohne Einheit: Zahlen bleiben, wie sie sind
            return "1", "", None
        a = _rate_exp(d)
        if a is None:
            raise DatasetError(f"Spalte „{name}“ ({unit}) ist keine Geschwindigkeitskonstante "
                               "(erwartet z. B. 1/s, 1/min, mol/(L·s) oder L/(mol·s))")
        p, show = _k_target(a)
        return p, show, None
    if want == "cX":
        data = data if data in ("c", "X") else ("X" if U.deq(d, _D1) else "c")
        want = "mol/L" if data == "c" else "1"
    if not U.deq(d, U.parse_unit(want)[1]):
        if want == "1":
            raise DatasetError(f"Spalte „{name}“ ({unit}) ist nicht dimensionslos; erwartet wird ein "
                               + ("Umsatz zwischen 0 und 1" if data == "X" else "Verhältnis ohne Einheit"))
        raise DatasetError(f"Spalte „{name}“ ({unit or 'ohne Einheit'}) lässt sich nicht in {want} umrechnen "
                           "(andere Dimension)")
    return want, ("" if want == "1" else want), data


def _round(x: float) -> float:
    return float(f"{x:.{DIGITS}g}")


def read(box: Sharebox, req: dict) -> dict:
    tool = ALIAS.get(req.get("tool"), req.get("tool"))
    if tool not in TOOLS:
        raise ValueError("Unbekanntes Werkzeug für Datensätze")
    sid = str(req.get("id") or "")
    mode = "pin" if req.get("mode") == "pin" else "live"
    res = box.resolve({"id": sid, "mode": mode, "version": req.get("version")}, ME)
    if res["status"] == "failed":
        raise EnvError(res.get("error") or "Datensatz nicht verfügbar")
    env = res["envelope"]
    ds = dataset_of(env, box.base / sid)
    cols = req.get("cols") if isinstance(req.get("cols"), dict) else {}
    data = req.get("data") if req.get("data") in ("c", "X") else None
    plan = []
    for role, want in TOOLS[tool]:
        key = cols.get(role)
        if not isinstance(key, str) or not key:
            raise ValueError(f"Spalte für {role} wählen")
        unit, show, d = _target(ds, key, want, data)       # Spalte fehlt (neuere Version) → DatasetError mit Meldung
        if want == "cX":
            data = d
        plan.append((role, key, unit, show))
    used = ds.used_mask()
    conv = {role: ds.in_unit(key, unit) for role, key, unit, _ in plan}
    ok = used.copy()
    for a in conv.values():
        ok &= np.isfinite(a)
    n = int(ok.sum())
    if n == 0:
        raise DatasetError("Der Datensatz hat in diesen Spalten keine verwendbaren Zeilen")
    n_excl, n_miss = int((~used).sum()), int((used & ~ok).sum())
    names = {role: ds.col(key)["name"] for role, key, _, _ in plan}
    units = {role: ds.col(key).get("unit") or "" for role, key, _, _ in plan}
    to = {role: show for role, _, _, show in plan}
    origin = {"id": sid, "title": env.get("title"), "version": env["version"], "mode": mode, "tool": tool,
              "cols": {role: key for role, key, _, _ in plan}, "names": names, "units": units, "to": to,
              "n": n, "dropped": n_excl + n_miss}
    if tool == "order":
        origin["data"] = data
    out = {"id": sid, "title": env.get("title"), "version": env["version"], "latest": res["latest"], "status": res["status"],
           "mode": mode, "rows": ds.rows, "n": n, "dropped": {"excluded": n_excl, "missing": n_miss},
           "values": {role: [_round(x) for x in a[ok].tolist()] for role, a in conv.items()},
           "names": names, "units": units, "to": to, "origin": origin, "notes": []}
    if tool == "arrhenius":
        out["unit_k"] = to["k"] or None
        if not to["k"]:
            out["notes"].append(f"Spalte „{names['k']}“ hat keine Einheit: k unverändert übernommen")
    if tool == "order":
        out["data"] = data
    return out


def route(envs, req: dict) -> dict:
    box = _box(envs)
    if req.get("list"):
        return {"datasets": list_datasets(box)}
    return read(box, req)


# ----------------------------------------------------------------------------- Herkunft in Ergebnis und Bericht
def clean_origin(o) -> dict | None:
    """Herkunft aus dem Seitenzustand (über die Anfrage) auf bekannte Felder und Längen begrenzen."""
    if not isinstance(o, dict) or not str(o.get("id") or "").strip():
        return None
    s = lambda v, n=120: str(v if v is not None else "")[:n]  # noqa: E731
    try:
        v = int(o.get("version") or 0)
    except (TypeError, ValueError):
        v = 0
    out = {"id": s(o.get("id"), 40), "title": s(o.get("title"), 160), "version": v,
           "mode": "pin" if o.get("mode") == "pin" else "live"}
    for f in ("cols", "names", "units", "to"):
        d = o.get(f)
        if isinstance(d, dict):
            out[f] = {s(k, 20): s(x, 80) for k, x in list(d.items())[:6]}
    for f in ("n", "dropped"):
        try:
            x = int(o.get(f) or 0)
        except (TypeError, ValueError):
            continue
        out[f] = x if 0 <= x < 10 ** 9 else 0
    if o.get("data") in ("c", "X"):
        out["data"] = o["data"]
    return out


ORDER_UNIT = {"c": {0: "mol L⁻¹ s⁻¹", 1: "s⁻¹", 2: "L mol⁻¹ s⁻¹"}, "X": {1: "s⁻¹"}}


def order_unit(best: int, data: str) -> str:
    """Einheit von k der besten Ordnung, wenn t in s und c in mol/L aus einem Datensatz stammen."""
    return ORDER_UNIT.get(data if data in ("c", "X") else "c", {}).get(best, "")
