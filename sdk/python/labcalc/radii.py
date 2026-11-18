"""Effektive Ionenradien nach Shannon (1976), Auswahl häufiger Ionen (ER-X02, Gate Q5).

Werte in Å, effektive Ionenradien (Bezug O²⁻ = 1,40 Å, KZ VI); Kristallradien = Ionenradius + 0,14 Å.
Aus Referenzwissen übertragen (Shannon 1976, Tab. 1) – bitte gegen die Originaltabelle prüfen (DECISIONS ER-X02).
"""
from __future__ import annotations

from . import chem as C

SOURCE = "shannon1976"
CHECK = "aus Shannon 1976 übertragen, bitte gegen das Original prüfen"

# (Element, Ladung, Koordinationszahl, Spinzustand oder "", effektiver Ionenradius / Å)
TABLE: list[tuple[str, int, int, str, float]] = [
    ("Li", 1, 6, "", 0.76), ("Na", 1, 6, "", 1.02), ("K", 1, 6, "", 1.38), ("Rb", 1, 6, "", 1.52),
    ("Cs", 1, 6, "", 1.67), ("Ag", 1, 6, "", 1.15),
    ("Be", 2, 4, "", 0.27), ("Mg", 2, 6, "", 0.72), ("Ca", 2, 6, "", 1.00), ("Sr", 2, 6, "", 1.18),
    ("Ba", 2, 6, "", 1.35), ("Mn", 2, 6, "HS", 0.83), ("Fe", 2, 6, "HS", 0.78), ("Co", 2, 6, "HS", 0.745),
    ("Ni", 2, 6, "", 0.69), ("Cu", 2, 6, "", 0.73), ("Zn", 2, 6, "", 0.74), ("Cd", 2, 6, "", 0.95),
    ("Hg", 2, 6, "", 1.02), ("Pb", 2, 6, "", 1.19),
    ("Al", 3, 6, "", 0.535), ("Sc", 3, 6, "", 0.745), ("Cr", 3, 6, "", 0.615), ("Fe", 3, 6, "HS", 0.645),
    ("Y", 3, 6, "", 0.900), ("La", 3, 6, "", 1.032),
    ("Si", 4, 6, "", 0.40), ("Ti", 4, 6, "", 0.605), ("Zr", 4, 6, "", 0.72), ("Sn", 4, 6, "", 0.69),
    ("Ce", 4, 6, "", 0.87),
    ("F", -1, 6, "", 1.33), ("Cl", -1, 6, "", 1.81), ("Br", -1, 6, "", 1.96), ("I", -1, 6, "", 2.20),
    ("O", -2, 6, "", 1.40), ("S", -2, 6, "", 1.84),
]


def for_element(sym: str) -> list[dict]:
    """Alle tabellierten Ionen eines Elements, mit Kristallradius und Herkunftsvermerk."""
    return [{"ion": f"{e}{abs(q) if abs(q) > 1 else ''}{'+' if q > 0 else '-'}", "charge": q, "cn": cn, "spin": sp,
             "r_ion": r, "r_cryst": round(r + 0.14, 3), "unit": "Å", "source": SOURCE, "check": CHECK}
            for e, q, cn, sp, r in TABLE if e == sym]


def radius(sym: str, charge: int, cn: int = 6) -> float:
    for e, q, c, _sp, r in TABLE:
        if e == sym and q == charge and c == cn:
            return r
    raise C.ChemError(f"Kein Shannon-Radius für {sym} (Ladung {charge:+d}, KZ {cn}) in der Auswahl.")
