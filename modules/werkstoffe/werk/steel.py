"""Stahl: Kohlenstoffäquivalente, Vorwärmtemperatur, Umwandlungstemperaturen, Anlassparameter, Aufkohlen.

Alle Formeln sind empirisch und gelten nur in ihrem Gültigkeitsbereich; Gehalte in Gew.-%.
- CE(IIW) = C + Mn/6 + (Cr + Mo + V)/5 + (Ni + Cu)/15                                    (EN 1011-2, Anh. C, Verf. A)
- CET = C + (Mn + Mo)/10 + (Cr + Cu)/20 + Ni/40                                          (EN 1011-2, Anh. C, Verf. B)
- Pcm = C + Si/30 + (Mn + Cu + Cr)/20 + Ni/60 + Mo/15 + V/10 + 5 B                       (Ito & Bessyo 1968)
- T_p = 697·CET + 160·tanh(d/35) + 62·HD^0,35 + (53·CET − 32)·Q − 328  [°C]               (EN 1011-2, Verf. B)
  gültig für CET 0,2–0,5 %, d 10–90 mm, HD 1–20 ml/100 g, Q 0,5–4,0 kJ/mm
- Ms = 539 − 423 C − 30,4 Mn − 17,7 Ni − 12,1 Cr − 7,5 Mo  [°C]                           (Andrews 1965)
- Ac1 = 723 − 10,7 Mn − 16,9 Ni + 29,1 Si + 16,9 Cr + 290 As + 6,38 W  [°C]               (Andrews 1965)
- Ac3 = 910 − 203 √C − 15,2 Ni + 44,7 Si + 104 V + 31,5 Mo + 13,1 W  [°C]                 (Andrews 1965)
- Hollomon–Jaffe: P = T (C_HJ + lg t), T in K, t in h, C_HJ ≈ 20                         (Hollomon & Jaffe 1945)
- Aufkohlen: c(x, t) = c_s − (c_s − c₀) erf(x / (2 √(D t))),  D = D₀ exp(−Q/(R T))         (Fick, Callister Kap. 5)
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

_SDK = Path(__file__).resolve().parents[3] / "sdk" / "python"
if _SDK.is_dir() and str(_SDK) not in sys.path:
    sys.path.insert(0, str(_SDK))

ELEMENTS = ("C", "Si", "Mn", "Cr", "Mo", "V", "Ni", "Cu", "B", "W", "As")
R = 8.314462618

RANGES_ANDREWS = {"C": (0.11, 0.6), "Mn": (0.04, 4.87), "Si": (0.11, 1.89), "Cr": (0, 4.48), "Ni": (0, 5.04),
                  "Mo": (0, 5.4)}
REFS = {"ce": ["en1011_2"], "cet": ["en1011_2"], "pcm": ["ito1968"], "preheat": ["en1011_2"],
        "ms": ["andrews1965"], "ac": ["andrews1965"], "hj": ["hollomonjaffe1945"], "carb": ["callister"]}


class SteelError(ValueError):
    pass


def _c(comp: dict) -> dict:
    out = {}
    for k in ELEMENTS:
        v = comp.get(k)
        try:
            out[k] = float(v) if v not in (None, "") else 0.0
        except (TypeError, ValueError):
            raise SteelError(f"Gehalt {k} ist keine Zahl") from None
        if out[k] < 0 or out[k] > 30:
            raise SteelError(f"Gehalt {k} = {out[k]} % ausserhalb 0–30 %")
    return out


def formulas(c: dict) -> dict:
    """Kennzahlen aus der Zusammensetzung (Gew.-%); Werte dürfen numpy-Felder sein (Messunsicherheit, Monte Carlo)."""
    import numpy as np
    return {"CE": c["C"] + c["Mn"] / 6 + (c["Cr"] + c["Mo"] + c["V"]) / 5 + (c["Ni"] + c["Cu"]) / 15,
            "CET": c["C"] + (c["Mn"] + c["Mo"]) / 10 + (c["Cr"] + c["Cu"]) / 20 + c["Ni"] / 40,
            "Pcm": c["C"] + c["Si"] / 30 + (c["Mn"] + c["Cu"] + c["Cr"]) / 20 + c["Ni"] / 60 + c["Mo"] / 15 + c["V"] / 10 + 5 * c["B"],
            "Ms": 539 - 423 * c["C"] - 30.4 * c["Mn"] - 17.7 * c["Ni"] - 12.1 * c["Cr"] - 7.5 * c["Mo"],
            "Ac1": 723 - 10.7 * c["Mn"] - 16.9 * c["Ni"] + 29.1 * c["Si"] + 16.9 * c["Cr"] + 290 * c["As"] + 6.38 * c["W"],
            "Ac3": 910 - 203 * np.sqrt(c["C"]) - 15.2 * c["Ni"] + 44.7 * c["Si"] + 104 * c["V"] + 31.5 * c["Mo"] + 13.1 * c["W"]}


def preheat_tp(cet, d, HD, Q):
    """Vorwärmtemperatur nach EN 1011-2 (CET-Verfahren); vektorisierbar."""
    import numpy as np
    return 697 * cet + 160 * np.tanh(d / 35) + 62 * HD ** 0.35 + (53 * cet - 32) * Q - 328


def composition_report(comp: dict, preheat: dict | None = None) -> dict:
    """Alle Kennzahlen einer Zusammensetzung mit Hinweisen zum Gültigkeitsbereich."""
    c = _c(comp)
    f = formulas(c)
    ce, cet, pcm, ms, ac1, ac3 = (float(f[k]) for k in ("CE", "CET", "Pcm", "Ms", "Ac1", "Ac3"))
    notes = []
    out_rng = [k for k, (lo, hi) in RANGES_ANDREWS.items() if not (lo <= c[k] <= hi)]
    if out_rng:
        notes.append("Ms/Ac1/Ac3: " + ", ".join(out_rng) + " ausserhalb des Datensatzes von Andrews (1965)")
    if c["C"] > 0.25:
        notes.append("Pcm ist für niedriggekohlte Stähle (C ≤ 0,25 %) gedacht")
    out = {"comp": c, "CE": ce, "CET": cet, "Pcm": pcm, "Ms": ms, "Ac1": ac1, "Ac3": ac3, "notes": notes}
    if preheat:
        out["preheat"] = preheat_temp(cet, **preheat)
    return out


def preheat_temp(cet: float, d: float = 20, HD: float = 5, Q: float = 1.0) -> dict:
    d, HD, Q = float(d), float(HD), float(Q)
    tp = float(preheat_tp(cet, d, HD, Q))
    warn = []
    for name, v, lo, hi in (("CET", cet, 0.2, 0.5), ("d", d, 10, 90), ("HD", HD, 1, 20), ("Q", Q, 0.5, 4.0)):
        if not lo <= v <= hi:
            warn.append(f"{name} = {v:g} ausserhalb {lo:g}–{hi:g}")
    return {"Tp": tp, "d": d, "HD": HD, "Q": Q, "warn": warn, "needed": tp > 0}


def hollomon_jaffe(T_C: float | None = None, t_h: float | None = None, P: float | None = None, C: float = 20.0) -> dict:
    """Zwei der drei Grössen (T, t, P) geben die dritte."""
    if P is None:
        if T_C is None or t_h is None or t_h <= 0:
            raise SteelError("T und t (> 0) nötig")
        P = (T_C + 273.15) * (C + math.log10(t_h))
    elif t_h is None:
        if T_C is None:
            raise SteelError("Zu P braucht es T oder t")
        t_h = 10 ** (P / (T_C + 273.15) - C)
    elif T_C is None:
        if t_h <= 0:
            raise SteelError("t muss > 0 sein")
        T_C = P / (C + math.log10(t_h)) - 273.15
    return {"T_C": T_C, "t_h": t_h, "P": P, "C": C}


def equivalent_tempering(T1_C: float, t1_h: float, T2_C: float, C: float = 20.0) -> dict:
    """Gleiche Anlasswirkung bei T2: t2 = 10^(T1 (C + lg t1)/T2 − C)."""
    P = (T1_C + 273.15) * (C + math.log10(t1_h))
    return {"P": P, "t2_h": 10 ** (P / (T2_C + 273.15) - C), "T2_C": T2_C, "C": C}


def diffusivity(D0: float, Q_kJ: float, T_C: float) -> float:
    return D0 * math.exp(-Q_kJ * 1e3 / (R * (T_C + 273.15)))


def _erf(x):
    return np.vectorize(math.erf)(x)


def _erfinv(y: float) -> float:
    """Inverse Fehlerfunktion durch Bisektion (|y| < 1)."""
    if not -1 < y < 1:
        raise SteelError("erf⁻¹ nur für −1 < y < 1")
    lo, hi = -6.0, 6.0
    for _ in range(100):
        m = 0.5 * (lo + hi)
        if math.erf(m) < y:
            lo = m
        else:
            hi = m
    return 0.5 * (lo + hi)


def carburise_profile(c0: float, cs: float, T_C: float, t_h: float, D0: float | None = None, Q_kJ: float | None = None,
                      c_limit: float = 0.4, depth_mm: float | None = None) -> dict:
    src = None
    if D0 is None or Q_kJ is None:
        from labcalc import materials as M
        d = M.diffusion("C", "γ-Fe")
        D0, Q_kJ = d["D0"], d["Q"] / 1000.0
        src = {"q": d.get("q") or d.get("quelle"), "teilchen": d.get("teilchen"), "wirt": d.get("wirt")}
    if not (cs > c0 >= 0):
        raise SteelError("Randgehalt c_s muss grösser als der Grundgehalt c₀ sein")
    D = diffusivity(D0, Q_kJ, T_C)
    t = t_h * 3600
    L = 2 * math.sqrt(D * t)                                   # m
    xmax = float(depth_mm) / 1e3 if depth_mm else 4 * L
    x = np.linspace(0, xmax, 201)
    c = cs - (cs - c0) * _erf(x / L)
    out = {"D": D, "D0": D0, "Q_kJ": Q_kJ, "x_mm": (x * 1e3).tolist(), "c": c.tolist(), "c0": c0, "cs": cs,
           "c_limit": c_limit, "T_C": T_C, "t_h": t_h, "src": src}
    if c0 < c_limit < cs:
        z = _erfinv((cs - c_limit) / (cs - c0))
        out["depth_mm"] = z * L * 1e3
    else:
        out["depth_mm"] = None
    return out
