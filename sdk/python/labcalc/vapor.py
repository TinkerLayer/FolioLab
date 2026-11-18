"""Dampfdruck (Antoine) und kolligative Konstanten (ER-X03, Gate Q8).

Antoine-Form wie im NIST Chemistry WebBook: lg(p/bar) = A − B/(T/K + C), jeweils mit Gültigkeitsbereich und
Originalquelle. Kryoskopische und ebullioskopische Konstanten K_f, K_b in K·kg/mol (Atkins, Tabelle der
kolligativen Konstanten). Beide Tabellen aus Referenzwissen übertragen – bitte gegen die Quelle prüfen
(DECISIONS ER-X03).
"""
from __future__ import annotations

import math

from . import chem as C

CHECK = "aus Referenzwissen übertragen, bitte gegen die Quelle prüfen"
REFS = ["nistwebbook"]

# Name -> (Aliase, [(Tmin K, Tmax K, A, B, C, Originalquelle)])
ANTOINE: dict[str, tuple[tuple[str, ...], list[tuple[float, float, float, float, float, str]]]] = {
    "Wasser": (("water", "h2o"), [
        (273.0, 303.0, 5.40221, 1838.675, -31.737, "Bridgeman & Aldrich 1964"),
        (304.0, 333.0, 5.20389, 1733.926, -39.485, "Bridgeman & Aldrich 1964"),
        (334.0, 363.0, 5.0768, 1659.793, -45.854, "Bridgeman & Aldrich 1964"),
        (344.0, 373.0, 5.08354, 1663.125, -45.622, "Liu & Lindsay 1970")]),
    "Ethanol": (("ethanol", "c2h5oh", "c2h6o"), [(292.77, 366.63, 5.37229, 1670.409, -40.191, "Ambrose & Sprake 1970")]),
    "Methanol": (("methanol", "ch3oh", "ch4o"), [(288.10, 356.83, 5.20409, 1581.341, -33.50, "Ambrose & Sprake 1970")]),
    "Aceton": (("acetone", "aceton", "c3h6o"), [(259.16, 507.60, 4.42448, 1312.253, -32.445, "Ambrose, Sprake & Townsend 1974")]),
    "Benzol": (("benzene", "benzol", "c6h6"), [(287.70, 354.07, 4.01814, 1203.835, -53.226, "Eon, Pommier & Guiochon 1971")]),
    "Toluol": (("toluene", "toluol", "c7h8"), [(308.52, 384.66, 4.07827, 1343.943, -53.773, "Williamson & Harrison 1957")]),
    "n-Hexan": (("hexane", "n-hexane", "hexan", "c6h14"), [(286.18, 342.69, 4.00266, 1171.53, -48.784, "Williamson & Harrison 1957")]),
    "Chloroform": (("chloroform", "trichlormethan", "chcl3"), [(215.0, 334.4, 4.20772, 1233.129, -40.953, "Stull 1947")]),
    "Essigsäure": (("acetic acid", "essigsaure", "essigsäure", "ch3cooh", "c2h4o2"), [(290.26, 391.01, 4.68206, 1642.54, -39.764, "McDonald, Shrader & Stull 1959")]),
}

# Name -> (Aliase, Tf / K, K_f, Tb / K, K_b)   K in K·kg/mol; None = nicht tabelliert
COLLIG: dict[str, tuple[tuple[str, ...], float, float | None, float | None, float | None]] = {
    "Wasser": (("water", "h2o"), 273.15, 1.86, 373.15, 0.51),
    "Benzol": (("benzene", "benzol", "c6h6"), 278.68, 5.12, 353.24, 2.53),
    "Essigsäure": (("acetic acid", "essigsaure", "essigsäure", "ch3cooh", "c2h4o2"), 289.8, 3.90, 391.1, 3.07),
    "Tetrachlormethan": (("ccl4", "carbon tetrachloride", "tetrachlorkohlenstoff"), 250.2, 30.0, 349.9, 4.95),
    "Schwefelkohlenstoff": (("cs2", "carbon disulfide", "kohlenstoffdisulfid"), 161.6, 3.8, 319.4, 2.37),
    "Naphthalin": (("naphthalene", "naphthalin", "c10h8"), 353.4, 6.94, 491.1, 5.8),
    "Phenol": (("phenol", "c6h5oh", "c6h6o"), 314.0, 7.27, 454.9, 3.04),
    "Campher": (("camphor", "kampfer", "campher", "c10h16o"), 452.0, 40.0, None, None),
}


def _find(table: dict, name: str) -> str:
    q = str(name).strip().lower()
    for k, v in table.items():
        if q == k.lower() or q in v[0]:
            return k
    raise C.ChemError(f"„{name}“ nicht in der Tabelle; vorhanden: {', '.join(table)}")


def solvents() -> dict:
    return {"antoine": list(ANTOINE), "colligative": list(COLLIG)}


TOL = 0.5   # K; die Bereichsgrenzen der Quelle sind gerundet


def _de(x: float, f: str = "g") -> str:
    return format(x, f).replace(".", ",")


def _inside(T, t0, t1) -> bool:
    return t0 - TOL <= T <= t1 + TOL


def _pick(ranges, T):
    inside = [r for r in ranges if _inside(T, r[0], r[1])]
    if inside:
        return inside[-1], False
    return min(ranges, key=lambda r: min(abs(T - r[0]), abs(T - r[1]))), True


def vapour_pressure(name: str, T: float) -> dict:
    """Dampfdruck bei T (K). Ausserhalb des Gültigkeitsbereichs: nächster Satz, mit Warnung."""
    k = _find(ANTOINE, name)
    if not T > 0:
        raise C.ChemError("Temperatur muss positiv sein (in K)")
    (t0, t1, A, B, Cc, ref), out = _pick(ANTOINE[k][1], T)
    if T + Cc <= 0:
        raise C.ChemError(f"Antoine-Gleichung für {k} bei {T:.2f} K nicht auswertbar")
    p_bar = 10 ** (A - B / (T + Cc))
    notes = [f"Antoine-Koeffizienten {CHECK}."]
    if out:
        notes.insert(0, f"{_de(T, '.2f')} K liegt ausserhalb des Gültigkeitsbereichs {_de(t0)}–{_de(t1)} K; Wert extrapoliert, nicht belastbar.")
    return {"name": k, "T": T, "p_bar": p_bar, "p_kPa": p_bar * 100, "A": A, "B": B, "C": Cc, "range": [t0, t1],
            "orig": ref, "out_of_range": out, "notes": notes, "refs": REFS}


def boiling_point(name: str, p_bar: float = 1.01325) -> dict:
    """Siedetemperatur beim Druck p (bar) durch Umkehrung der Antoine-Gleichung; der passende Bereich wird gesucht."""
    k = _find(ANTOINE, name)
    if not p_bar > 0:
        raise C.ChemError("Druck muss positiv sein")
    best = None
    for (t0, t1, A, B, Cc, ref) in ANTOINE[k][1]:
        T = B / (A - math.log10(p_bar)) - Cc
        out = not _inside(T, t0, t1)
        if best is None or (best[1] and not out):
            best = (T, out, (t0, t1), ref)
    T, out, rng, ref = best
    notes = [f"Antoine-Koeffizienten {CHECK}."]
    if out:
        notes.insert(0, f"Ergebnis {_de(T, '.1f')} K ausserhalb des Gültigkeitsbereichs {_de(rng[0])}–{_de(rng[1])} K; nicht belastbar.")
    return {"name": k, "p_bar": p_bar, "T": T, "range": list(rng), "orig": ref, "out_of_range": out, "notes": notes, "refs": REFS}


def colligative(name: str, b: float, i: float = 1.0) -> dict:
    """ΔT_b = i K_b b, ΔT_f = i K_f b (ideal verdünnte Lösung, b in mol/kg)."""
    k = _find(COLLIG, name)
    if b < 0 or i <= 0:
        raise C.ChemError("Molalität ≥ 0 und van-'t-Hoff-Faktor > 0 erforderlich")
    _al, Tf, Kf, Tb, Kb = COLLIG[k]
    out = {"name": k, "b": b, "i": i, "Kf": Kf, "Kb": Kb, "Tf0": Tf, "Tb0": Tb, "refs": ["atkins"],
           "notes": [f"Konstanten {CHECK}.", "Nur für ideal verdünnte Lösungen (b ≲ 0,1 mol/kg)."]}
    if Kf is not None:
        out["dTf"] = i * Kf * b
        out["Tf"] = Tf - out["dTf"]
    if Kb is not None and Tb is not None:
        out["dTb"] = i * Kb * b
        out["Tb"] = Tb + out["dTb"]
    if b > 0.1:
        out["notes"].append(f"b = {_de(b)} mol/kg ist für das Grenzgesetz hoch; Abweichungen von mehreren Prozent möglich.")
    return out


def constant(name: str, which: str) -> float:
    k = _find(COLLIG, name)
    v = COLLIG[k][2 if which == "f" else 4]
    if v is None:
        raise C.ChemError(f"keine {'kryoskopische' if which == 'f' else 'ebullioskopische'} Konstante für {k} tabelliert")
    return v


def register_calc_functions():
    from . import expr as E
    from . import units as U
    E.register_string_function("pvap", lambda ctx, q, T: vapour_pressure(str(q), float(T))["p_bar"] * 1e5, 2, 2,
                               U.kind_dims("pressure"), 'pvap("Wasser", T) – Dampfdruck nach Antoine (T in K, NIST WebBook)')
    E.register_string_function("Kb", lambda ctx, q: constant(str(q), "b"), 1, 1, U.kind_dims("cryo_const"),
                               'Kb("Wasser") – ebullioskopische Konstante (Atkins)')
    E.register_string_function("Kf", lambda ctx, q: constant(str(q), "f"), 1, 1, U.kind_dims("cryo_const"),
                               'Kf("Wasser") – kryoskopische Konstante (Atkins)')
