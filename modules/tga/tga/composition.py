"""Zusammensetzung aus TGA-Stufen.

- Vorlagen nach ASTM E1131 (Feuchte/leichtflüchtig, Polymer/mittelflüchtig, brennbarer Kohlenstoff nach Wechsel auf
  Luft, Asche/Füllstoff) und ASTM D7582 (Kurzanalyse: Feuchte, flüchtige Bestandteile, Asche, fixer Kohlenstoff) sowie
  freie Temperaturgrenzen.
- Stöchiometrische Umrechnung: Gehalt einer bekannten Komponente aus ihrer Stufe (z. B. CaCO₃ = Verlust / 0,4397).
  Die theoretischen Verluste werden aus den Standard-Atomgewichten (IUPAC CIAAW 2021, gekürzte Werte) berechnet.
- Kalibrierprüfung mit Calciumoxalat-Monohydrat (drei Stufen) und Zwei-Punkt-Temperaturkalibrierung an
  ITS-90-Fixpunkten.
"""
from __future__ import annotations

import re

import numpy as np

from .readers import Run

# Gekürzte Standard-Atomgewichte (Prohaska u. a. 2022, IUPAC CIAAW 2021; Zr nach CIAAW-Änderung 2024)
ATOMIC_WEIGHT = {
    "H": 1.0080, "Li": 6.94, "B": 10.81, "C": 12.011, "N": 14.007, "O": 15.999, "F": 18.998, "Na": 22.990,
    "Mg": 24.305, "Al": 26.982, "Si": 28.085, "P": 30.974, "S": 32.06, "Cl": 35.45, "K": 39.098, "Ca": 40.078,
    "Ti": 47.867, "Cr": 51.996, "Mn": 54.938, "Fe": 55.845, "Co": 58.933, "Ni": 58.693, "Cu": 63.546, "Zn": 65.38,
    "Br": 79.904, "Sr": 87.62, "Zr": 91.222, "Ag": 107.87, "Sb": 121.76, "Ba": 137.33, "Ce": 140.12, "Pb": 207.2,
}


def formula_mass(f: str) -> float:
    """Molare Masse aus einer Summenformel: Klammern, Hydrate (· oder *), Koeffizienten vor Teilformeln."""
    total = 0.0
    for part in re.split(r"[·*•]", f.replace(" ", "")):
        m = re.match(r"^(\d+(?:\.\d+)?)(.*)$", part)
        k = float(m.group(1)) if m else 1.0
        total += k * _mass(m.group(2) if m else part)
    return total


def _mass(f: str) -> float:
    stack = [0.0]
    i = 0
    while i < len(f):
        c = f[i]
        if c == "(":
            stack.append(0.0)
            i += 1
        elif c == ")":
            i += 1
            m = re.match(r"\d+(?:\.\d+)?", f[i:])
            n = float(m.group()) if m else 1.0
            i += len(m.group()) if m else 0
            v = stack.pop() * n
            stack[-1] += v
        else:
            m = re.match(r"([A-Z][a-z]?)(\d+(?:\.\d+)?)?", f[i:])
            if not m or m.group(1) not in ATOMIC_WEIGHT:
                raise ValueError(f"Formel „{f}“: unbekanntes Element bei „{f[i:]}“")
            stack[-1] += ATOMIC_WEIGHT[m.group(1)] * (float(m.group(2)) if m.group(2) else 1.0)
            i += len(m.group())
    if len(stack) != 1:
        raise ValueError(f"Formel „{f}“: Klammern passen nicht")
    return stack[0]


# Zersetzungen: (Schlüssel, Bezeichnung, Ausgangsstoff, abgegebene Gase [(Koeff., Formel)], fester Rest, Bezugsstoff
# falls anders als Ausgangsstoff). Reaktionswege nach Brown (2001); Verluste berechnet.
REACTIONS = [
    ("caco3", "Calciumcarbonat → CaO + CO₂", "CaCO3", [(1, "CO2")], "CaO", None),
    ("mgco3", "Magnesiumcarbonat → MgO + CO₂", "MgCO3", [(1, "CO2")], "MgO", None),
    ("dolomit", "Dolomit → CaO + MgO + 2 CO₂", "CaMg(CO3)2", [(2, "CO2")], "CaO + MgO", None),
    ("caoh2", "Calciumhydroxid → CaO + H₂O", "Ca(OH)2", [(1, "H2O")], "CaO", None),
    ("mgoh2", "Magnesiumhydroxid (MDH) → MgO + H₂O", "Mg(OH)2", [(1, "H2O")], "MgO", None),
    ("ath", "Aluminiumhydroxid (ATH) → ½ Al₂O₃ + 1½ H₂O", "Al(OH)3", [(1.5, "H2O")], "½ Al2O3", None),
    ("boehmit", "Böhmit → ½ Al₂O₃ + ½ H₂O", "AlO(OH)", [(0.5, "H2O")], "½ Al2O3", None),
    ("gips", "Gips → CaSO₄ + 2 H₂O", "CaSO4·2H2O", [(2, "H2O")], "CaSO4", None),
    ("gips_halb", "Gips → Halbhydrat + 1½ H₂O", "CaSO4·2H2O", [(1.5, "H2O")], "CaSO4·0.5H2O", None),
    ("kaolinit", "Kaolinit → Metakaolin + 2 H₂O", "Al2Si2O5(OH)4", [(2, "H2O")], "Al2Si2O7", None),
    ("talk", "Talk → 3 MgSiO₃ + SiO₂ + H₂O", "Mg3Si4O10(OH)2", [(1, "H2O")], "3 MgSiO3 + SiO2", None),
    ("hydromagnesit", "Hydromagnesit → 5 MgO + 4 CO₂ + 5 H₂O", "Mg5(CO3)4(OH)2·4H2O", [(4, "CO2"), (5, "H2O")], "5 MgO", None),
    ("nahco3", "Natriumhydrogencarbonat → ½ Na₂CO₃ + ½ H₂O + ½ CO₂", "NaHCO3", [(0.5, "H2O"), (0.5, "CO2")], "½ Na2CO3", None),
    ("cuso4", "Kupfersulfat-Pentahydrat → CuSO₄ + 5 H₂O", "CuSO4·5H2O", [(5, "H2O")], "CuSO4", None),
    ("pvc", "PVC → HCl (Dehydrochlorierung)", "C2H3Cl", [(1, "HCl")], "Polyen", None),
    ("oxalat1", "Ca-Oxalat-Monohydrat → CaC₂O₄ + H₂O", "CaC2O4·H2O", [(1, "H2O")], "CaC2O4", None),
    ("oxalat2", "Ca-Oxalat → CaCO₃ + CO", "CaC2O4·H2O", [(1, "CO")], "CaCO3", "CaC2O4·H2O"),
    ("oxalat3", "aus Ca-Oxalat-Monohydrat: CaCO₃ → CaO + CO₂", "CaC2O4·H2O", [(1, "CO2")], "CaO", "CaC2O4·H2O"),
]


def reactions(lang: str = "de") -> list[dict]:
    out = []
    for key, label, start, gases, rest, _ in REACTIONS:
        M = formula_mass(start)
        Mg = sum(k * formula_mass(g) for k, g in gases)
        out.append({"key": key, "label": label, "formula": start, "gases": [[k, g] for k, g in gases], "rest": rest,
                    "M": round(M, 3), "loss": 100.0 * Mg / M, "source": ["ciaaw2021", "brown2001"]})
    return out


def content_from_loss(loss_pct: float, key: str) -> dict:
    r = next((x for x in reactions() if x["key"] == key), None)
    if r is None:
        raise ValueError(f"Unbekannte Zersetzung „{key}“")
    return {"key": key, "label": r["label"], "theory": r["loss"], "content": 100.0 * loss_pct / r["loss"]}


# ----------------------------------------------------------------------------- Vorlagen
PRESETS = {
    "e1131": {"de": "Zusammensetzung nach ASTM E1131 (N₂ → Luft)", "ref": "astm-e1131",
              "params": {"T1": 200.0, "T2": 600.0}},
    "d7582": {"de": "Kurzanalyse nach ASTM D7582 (Feuchte, Flüchtige, Asche, fixer C)", "ref": "astm-d7582",
              "params": {"T1": 107.0, "T2": 950.0}},
    "free": {"de": "Freie Temperaturgrenzen", "ref": None, "params": {"bounds": [200.0, 400.0, 600.0]}},
}


def _m_at_T(run: Run, m, T, stop=None):
    """Masse beim ersten Erreichen von T (nur bis Index stop)."""
    idx = np.nonzero(run.T[:stop] >= T)[0] if run.has_T else []
    if not len(idx):
        return None, None
    j = int(idx[0])
    return float(m[j]), j


def compose(run: Run, preset: str = "e1131", params: dict | None = None, switch: int | None = None) -> dict:
    """Anteile in % der Bezugsmasse (Einwaage oder Bezugsmasse aus dem Protokoll)."""
    from .process import gas_switch
    p = {**PRESETS.get(preset, PRESETS["e1131"])["params"], **(params or {})}
    m = run.pct()
    mg = run.mg()
    n = len(m)
    start = float(np.median(m[:3]))
    warn = []
    if switch is None:
        switch = gas_switch(run)
        if p.get("t_switch") not in (None, ""):
            switch = int(np.searchsorted(run.time(), float(p["t_switch"])))
    rows = []

    def row(name, a_m, b_m, frm, to, note=""):
        v = a_m - b_m
        rows.append({"name": name, "from": frm, "to": to, "pct": float(v),
                     "mg": float(v / 100.0 * (run.meta.get("ref_mg") or run.m0)) if (run.m0 or run.meta.get("ref_mg")) else None,
                     "note": note})

    if preset in ("e1131", "d7582"):
        T1, T2 = float(p["T1"]), float(p["T2"])
        stop = switch if switch else None
        m1, j1 = _m_at_T(run, m, T1, stop)
        if m1 is None:
            raise ValueError(f"{T1:g} °C wird im Lauf nicht erreicht")
        if switch:
            m2, j2 = float(m[switch]), switch
            to2 = f"Gaswechsel ({run.T[switch]:.0f} °C)" if run.has_T else "Gaswechsel"
        else:
            m2, j2 = _m_at_T(run, m, T2)
            if m2 is None:
                m2, j2 = float(m[-1]), n - 1
                warn.append(f"{T2:g} °C nicht erreicht; Ende des Laufs verwendet")
            to2 = f"{T2:g} °C"
        end = float(np.median(m[-3:]))
        if preset == "e1131":
            row("Feuchte / leichtflüchtige Anteile", start, m1, "Start", f"{T1:g} °C")
            row("Mittelflüchtige Anteile (Polymer)", m1, m2, f"{T1:g} °C", to2)
            if switch:
                row("Brennbares (Russ / Kohlenstoff)", m2, end, to2, "Ende")
                rows.append({"name": "Asche / Füllstoff (Rückstand)", "from": "Ende", "to": "", "pct": end,
                             "mg": float(end / 100 * run.m0) if run.m0 else None, "note": ""})
            else:
                rows.append({"name": "Rückstand (Füllstoff, Asche, Russ)", "from": to2, "to": "", "pct": m2,
                             "mg": float(m2 / 100 * run.m0) if run.m0 else None,
                             "note": "ohne Gaswechsel nicht getrennt"})
                warn.append("Kein Gaswechsel erkannt: Russ und Asche lassen sich nicht trennen (Zeit des Wechsels von Hand angeben).")
        else:
            row("Feuchte", start, m1, "Start", f"{T1:g} °C")
            row("Flüchtige Bestandteile", m1, m2, f"{T1:g} °C", to2)
            ash = end if switch else None
            if ash is None:
                warn.append("Asche braucht den Wechsel auf Luft/O₂; ohne Wechsel kein fixer Kohlenstoff.")
            else:
                fixed = 100.0 - (start - m1) - (m1 - m2) - ash
                rows.append({"name": "Fixer Kohlenstoff (Differenz)", "from": "", "to": "", "pct": float(fixed), "mg": None,
                             "note": "100 − Feuchte − Flüchtige − Asche"})
                rows.append({"name": "Asche", "from": "Ende", "to": "", "pct": float(ash), "mg": None, "note": ""})
                dry = 100.0 - (start - m1)
                for r in list(rows):
                    if r["name"] != "Feuchte" and dry > 0:
                        r["dry"] = float(r["pct"] / dry * 100.0)
    else:
        bounds = sorted(float(b) for b in p.get("bounds") or [])
        prev_m, prev_lab = start, "Start"
        for b in bounds:
            mb, _ = _m_at_T(run, m, b)
            if mb is None:
                warn.append(f"{b:g} °C nicht erreicht")
                break
            row(f"{prev_lab} – {b:g} °C", prev_m, mb, prev_lab, f"{b:g} °C")
            prev_m, prev_lab = mb, f"{b:g} °C"
        end = float(np.median(m[-3:]))
        row(f"{prev_lab} – Ende", prev_m, end, prev_lab, "Ende")
        rows.append({"name": "Rückstand", "from": "Ende", "to": "", "pct": end,
                     "mg": float(end / 100 * run.m0) if run.m0 else None, "note": ""})
    return {"preset": preset, "label": PRESETS.get(preset, {}).get("de", preset), "rows": rows, "warnings": warn,
            "switch": switch, "switch_T": float(run.T[switch]) if switch and run.has_T else None,
            "ref": PRESETS.get(preset, {}).get("ref"), "params": p}


# ----------------------------------------------------------------------------- Kalibrierung
OXALATE = [("H₂O", "oxalat1"), ("CO", "oxalat2"), ("CO₂", "oxalat3")]


def check_oxalate(steps: list[dict], tol: float = 0.5) -> dict:
    """Vergleicht die drei grössten Stufen (in Temperaturreihenfolge) mit den theoretischen Verlusten."""
    th = {r["key"]: r["loss"] for r in reactions()}
    big = sorted(sorted(steps, key=lambda s: -s["loss"])[:3], key=lambda s: s.get("T_peak") or s["t_peak"])
    rows = []
    for (gas, key), s in zip(OXALATE, big):
        d = s["loss"] - th[key]
        rows.append({"gas": gas, "theory": th[key], "measured": s["loss"], "delta": d, "ok": abs(d) <= tol,
                     "T_peak": s.get("T_peak")})
    ok = len(rows) == 3 and all(r["ok"] for r in rows)
    return {"rows": rows, "ok": ok, "tol": tol, "complete": len(rows) == 3}


# ITS-90-Fixpunkte (Erstarrungs-/Schmelzpunkte), Preston-Thomas (1990)
ITS90 = {"In": 156.5985, "Sn": 231.928, "Zn": 419.527, "Al": 660.323, "Ag": 961.78}


def two_point(measured: list[tuple[float, float]]) -> dict:
    """Lineare Temperaturkalibrierung T_wahr = a + b·T_gemessen aus Paaren (gemessen, Referenz)."""
    pts = [(float(x), float(y)) for x, y in measured]
    if len(pts) < 1:
        raise ValueError("mindestens ein Kalibrierpunkt")
    if len(pts) == 1:
        return {"a": pts[0][1] - pts[0][0], "b": 1.0, "n": 1}
    x = np.array([p[0] for p in pts])
    y = np.array([p[1] for p in pts])
    b, a = np.polyfit(x, y, 1)
    return {"a": float(a), "b": float(b), "n": len(pts), "resid": [float(v) for v in y - (a + b * x)]}
