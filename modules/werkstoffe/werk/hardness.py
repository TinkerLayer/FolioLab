"""Härte aus Eindruckmessungen, Umwertung nur mit einer Tabelle des Nutzers, Korngrösse (ASTM E112), Hall–Petch.

- Vickers (ISO 6507-1): HV = 0,1891 F / d², F in N, d = Mittel der Diagonalen in mm
- Brinell (ISO 6506-1): HBW = 0,102 · 2F / (π D (D − √(D² − d²))), D Kugeldurchmesser, d Eindruckdurchmesser in mm
- Knoop (ISO 4545-1): HK = 1,451 F / d², d lange Diagonale in mm
- Umwertung zwischen Härteskalen oder in Zugfestigkeit: nur über eine Tabelle, die der Nutzer aus seinem eigenen
  Exemplar der Norm (z. B. ISO 18265) lädt; lineare Interpolation, kein Extrapolieren. Ohne Tabelle nur die als
  Faustregel gekennzeichnete Näherung Rm ≈ 3,3 · HV (für Stähle, Callister).
- Korngrösse (ASTM E112): G = −6,6457 lg ℓ̄ − 3,298 (ℓ̄ mittlere Sehnenlänge in mm, Linienschnittverfahren);
  G = 3,321928 lg N_A − 2,954 (N_A Körner je mm² bei 1×, Planimetrie)
- Hall–Petch: σ_y = σ₀ + k_y d^(−1/2)
"""
from __future__ import annotations

import math

import numpy as np

from .fit import linreg

REFS = {"HV": ["iso6507"], "HBW": ["iso6506"], "HK": ["iso4545"], "rule": ["callister"], "e112": ["astme112"],
        "hp": ["hall1951", "petch1953"]}
G_N = 9.80665


class HardError(ValueError):
    pass


def vickers(F_N: float, d1_mm: float, d2_mm: float | None = None) -> dict:
    d = (d1_mm + (d2_mm if d2_mm else d1_mm)) / 2
    if F_N <= 0 or d <= 0:
        raise HardError("Prüfkraft und Diagonalen müssen positiv sein")
    hv = 0.1891 * F_N / d ** 2
    asym = abs(d1_mm - d2_mm) / d if d2_mm else 0.0
    notes = []
    if asym > 0.05:
        notes.append("Diagonalen weichen um mehr als 5 % voneinander ab (ISO 6507-1: Probe geneigt oder anisotrop?)")
    return {"value": hv, "d": d, "scale": f"HV{_kgf(F_N)}", "notes": notes}


def brinell(F_N: float, D_mm: float, d1_mm: float, d2_mm: float | None = None) -> dict:
    d = (d1_mm + (d2_mm if d2_mm else d1_mm)) / 2
    if not 0 < d < D_mm:
        raise HardError("Eindruckdurchmesser muss zwischen 0 und dem Kugeldurchmesser liegen")
    hb = 0.102 * 2 * F_N / (math.pi * D_mm * (D_mm - math.sqrt(D_mm ** 2 - d ** 2)))
    notes = []
    r = d / D_mm
    if not 0.24 <= r <= 0.6:
        notes.append("d/D ausserhalb 0,24–0,6 (ISO 6506-1): Ergebnis nicht normgerecht")
    return {"value": hb, "d": d, "scale": f"HBW {D_mm:g}/{_kgf(F_N)}", "notes": notes, "d_D": r}


def knoop(F_N: float, d_mm: float) -> dict:
    if F_N <= 0 or d_mm <= 0:
        raise HardError("Prüfkraft und Diagonale müssen positiv sein")
    return {"value": 1.451 * F_N / d_mm ** 2, "d": d_mm, "scale": f"HK{_kgf(F_N)}", "notes": []}


def _kgf(F_N: float) -> str:
    k = F_N / G_N
    return f"{k:.3g}".rstrip("0").rstrip(".") if k < 1 else f"{k:.0f}" if abs(k - round(k)) < 0.05 else f"{k:.2g}"


def series(values) -> dict:
    v = np.asarray([float(x) for x in values], float)
    if not len(v):
        raise HardError("Keine Werte")
    out = {"n": len(v), "mean": float(v.mean()), "min": float(v.min()), "max": float(v.max())}
    if len(v) > 1:
        from labcalc.stats import t_ppf
        s = float(v.std(ddof=1))
        out.update(sd=s, ci95=t_ppf(0.975, len(v) - 1) * s / math.sqrt(len(v)))
    return out


# ----------------------------------------------------------------------------- Umwertung über Nutzertabelle
def parse_table(text: str) -> dict:
    """Umwertungstabelle aus Text (CSV/TSV): Kopfzeile mit Skalennamen (z. B. HV;HB;HRC;Rm), dann Zahlen. Leere
    Zellen erlaubt. Zeilen mit # sind Kommentar; '# Quelle: …' wird als Quellenangabe übernommen."""
    import labtable
    src = ""
    rows = []
    head = None
    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.startswith("#"):
            m = s.lstrip("#").strip()
            if m.lower().startswith(("quelle:", "source:")):
                src = m.split(":", 1)[1].strip()
            continue
        sep = "\t" if "\t" in s else (";" if ";" in s else ",")
        parts = [p.strip() for p in s.split(sep)]
        if head is None:
            head = parts
            continue
        rows.append([labtable.number(p) for p in parts] + [None] * (len(head) - len(parts)))
    if not head or len(head) < 2 or len(rows) < 2:
        raise HardError("Tabelle braucht eine Kopfzeile mit mindestens zwei Skalen und zwei Zeilen")
    cols = {h: [r[i] for r in rows] for i, h in enumerate(head)}
    return {"scales": head, "cols": cols, "source": src, "n": len(rows)}


def convert(table: dict, value: float, src_scale: str, dst_scale: str) -> dict:
    a, b = table["cols"].get(src_scale), table["cols"].get(dst_scale)
    if a is None or b is None:
        raise HardError(f"Skala {src_scale} oder {dst_scale} nicht in der Tabelle")
    pts = sorted((x, y) for x, y in zip(a, b) if x is not None and y is not None)
    if len(pts) < 2:
        raise HardError("Zu wenige gemeinsame Werte für diese beiden Skalen")
    xs = [p[0] for p in pts]
    if not xs[0] <= value <= xs[-1]:
        return {"value": None, "note": f"{value:g} {src_scale} ausserhalb der Tabelle ({xs[0]:g}–{xs[-1]:g}); nicht extrapoliert"}
    return {"value": float(np.interp(value, xs, [p[1] for p in pts])), "note": "linear interpoliert"}


def rule_of_thumb_Rm(HV: float) -> dict:
    return {"value": 3.3 * HV, "note": "Faustregel Rm ≈ 3,3·HV (Stahl, Callister), keine Umwertung nach Norm"}


# ----------------------------------------------------------------------------- Korngrösse
def grain_intercept(total_length_mm: float, intercepts: float, magnification: float = 1.0) -> dict:
    """ℓ̄ = L_T / (M · N); L_T Gesamtlänge der Messlinien auf dem Bild (mm), N gezählte Schnittpunkte."""
    if intercepts <= 0 or total_length_mm <= 0:
        raise HardError("Länge und Zahl der Schnittpunkte müssen positiv sein")
    l_mm = total_length_mm / (magnification * intercepts)
    G = -6.6457 * math.log10(l_mm) - 3.298
    return {"l_mm": l_mm, "l_um": l_mm * 1e3, "G": G}


def grain_planimetric(grains_per_mm2: float) -> dict:
    if grains_per_mm2 <= 0:
        raise HardError("Kornzahl muss positiv sein")
    G = 3.321928 * math.log10(grains_per_mm2) - 2.954
    return {"NA": grains_per_mm2, "G": G, "d_um": 1e3 / math.sqrt(grains_per_mm2)}


def G_to_l(G: float) -> float:
    """Mittlere Sehnenlänge in µm zu einer Korngrössenkennzahl G."""
    return 10 ** (-(G + 3.298) / 6.6457) * 1e3


def hall_petch(d_um, sigma) -> dict:
    """Ausgleichsgerade σ_y = σ₀ + k d^(−1/2); d in µm, σ in MPa; k in MPa·√m."""
    d = np.asarray(d_um, float) * 1e-6
    s = np.asarray(sigma, float)
    if len(d) < 2 or np.any(d <= 0):
        raise HardError("Mindestens zwei positive Korngrössen nötig")
    f = linreg(d ** -0.5, s)
    return {"sigma0": f["a"], "k": f["b"], "s_sigma0": f.get("sa"), "s_k": f.get("sb"), "r2": f["r2"], "n": f["n"],
            "x": (d ** -0.5).tolist(), "y": s.tolist()}
