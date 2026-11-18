"""Mittlere Bindungsenthalpien und Bindungslängen (ER-X01) und die Schätzung von ΔrH für Gasreaktionen.

ΔrH ≈ Σ D(gebrochene Bindungen) − Σ D(gebildete Bindungen); nur für Stoffe in der Gasphase sinnvoll, Mittelwerte
über viele Verbindungen (typisch ±10–30 kJ/mol je Bindung). Immer als Schätzung neben dem Tabellenwert.
Werte: mittlere Bindungsenthalpien bei 298 K und typische Bindungslängen nach Atkins' Physical Chemistry (Tabellen der
mittleren Bindungsenthalpien und Bindungslängen); aus dem Nachschlagewissen übertragen – siehe DECISIONS.
"""
from __future__ import annotations

from . import chem as C

REFS = ["atkins"]
# (Element A, Element B, Ordnung) -> (D in kJ/mol, Länge in pm); Ordnung 1.5 = aromatisch
TABLE = {
    ("H", "H", 1): (436, 74), ("C", "H", 1): (412, 109), ("N", "H", 1): (388, 101), ("H", "O", 1): (463, 96),
    ("F", "H", 1): (565, 92), ("Cl", "H", 1): (431, 127), ("Br", "H", 1): (366, 141), ("H", "I", 1): (299, 161),
    ("H", "S", 1): (338, 134),
    ("C", "C", 1): (348, 154), ("C", "C", 2): (612, 134), ("C", "C", 3): (838, 120), ("C", "C", 1.5): (518, 140),
    ("C", "N", 1): (305, 147), ("C", "N", 2): (613, 128), ("C", "N", 3): (890, 116),
    ("C", "O", 1): (360, 143), ("C", "O", 2): (743, 120), ("C", "F", 1): (484, 135), ("C", "Cl", 1): (338, 177),
    ("Br", "C", 1): (276, 194), ("C", "I", 1): (238, 214), ("C", "S", 1): (259, 182),
    ("N", "N", 1): (163, 145), ("N", "N", 2): (409, 125), ("N", "N", 3): (945, 110), ("N", "O", 1): (157, 140),
    ("O", "O", 1): (157, 148), ("O", "O", 2): (497, 121),
    ("F", "F", 1): (155, 142), ("Cl", "Cl", 1): (242, 199), ("Br", "Br", 1): (193, 228), ("I", "I", 1): (151, 267),
    ("S", "S", 1): (226, 205),
}
DIATOMIC = {"H2": "[H][H]", "O2": "O=O", "N2": "N#N", "F2": "FF", "Cl2": "ClCl", "Br2": "BrBr", "I2": "II",
            "HCl": "Cl", "HF": "F", "HBr": "Br", "HI": "I", "H2O": "O", "CO2": "O=C=O", "NH3": "N", "CH4": "C"}


def _key(a, b, o):
    x, y = sorted((a, b))
    return (x, y, o)


TABLE = {_key(a, b, o): v for (a, b, o), v in TABLE.items()}


def lookup(a: str, b: str, order: float = 1) -> dict:
    v = TABLE.get(_key(a, b, order))
    if not v:
        raise C.ChemError(f"keine mittlere Bindungsenthalpie für {a}–{b} (Ordnung {order:g})")
    return {"D": v[0], "length_pm": v[1], "refs": REFS}


def bond_counts(smiles: str) -> dict:
    from . import molgraph as G
    g = G.parse(smiles)
    out = {}
    for a, b, o in g.bonds:
        k = _key(g.el[a], g.el[b], o)
        out[k] = out.get(k, 0) + 1
    for i, el in enumerate(g.el):
        if g.h[i]:
            k = _key(el, "H", 1)
            out[k] = out.get(k, 0) + g.h[i]
    return out


def _smiles(text: str) -> str | None:
    from . import substances as S
    sp = C.parse_species(text)
    f = text.split("(")[0].strip()
    if f in DIATOMIC:
        return DIATOMIC[f]
    key = S.resolve(text) or S.resolve(f)
    m = S.get(key) if key else None
    if m and m.get("smiles"):
        return m["smiles"]
    del sp
    return None


def estimate(eq: C.Equation, coefs) -> dict:
    """ΔrH-Schätzung aus mittleren Bindungsenthalpien für die ausgeglichene Gleichung."""
    from fractions import Fraction
    total, rows, missing = 0.0, [], []
    for t, c in zip(eq.terms, coefs):
        nu = float(Fraction(str(c)))
        smi = _smiles(t.species.text)
        if not smi:
            missing.append(t.species.text)
            continue
        cnt = bond_counts(smi)
        e = 0.0
        for k, n in cnt.items():
            v = TABLE.get(k)
            if not v:
                raise C.ChemError(f"keine mittlere Bindungsenthalpie für {k[0]}–{k[1]} (Ordnung {k[2]:g}) in {t.species.text}")
            e += n * v[0]
        total += (1 if t.side < 0 else -1) * nu * e                  # Edukte: Bindungen brechen (+), Produkte bilden (−)
        rows.append({"species": t.species.text, "nu": nu, "side": t.side, "bonds": {f"{a}–{b} ({o:g})": n for (a, b, o), n in cnt.items()},
                     "D_sum": e})
    if missing:
        raise C.ChemError("Struktur unbekannt für " + ", ".join(missing) + " (Bindungen nicht zählbar)")
    notes = ["Schätzung aus mittleren Bindungsenthalpien (Gasphase, 298 K); Abweichung vom Tabellenwert oft "
             "10–100 kJ/mol. Kondensierte Stoffe brauchen zusätzlich Verdampfungs- bzw. Sublimationsenthalpien."]
    if any(t.species.phase in ("l", "s", "aq") for t in eq.terms):
        notes.append("Die Gleichung enthält kondensierte Stoffe: Schätzung gilt für alle Stoffe gasförmig.")
    return {"dH_est": total, "rows": rows, "notes": notes, "refs": REFS, "estimate": True}
