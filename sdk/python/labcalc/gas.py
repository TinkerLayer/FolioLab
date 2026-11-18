"""Gase (Ticket ER-L07): ideales Gasgesetz pV = nRT mit genannten Bedingungen, Molvolumen, Partialdrücke (Dalton),
Gasdichte und Masse–Volumen. Nur ideales Verhalten; reale Gase (van der Waals) erst mit belegten Konstanten.
R = 8,314 462 618 J/(mol·K) (CODATA 2022, exakt).
"""
from __future__ import annotations

from . import chem as C

R = 8.314462618
REFS = ["codata2022", "atkins"]
P_UNITS = {"Pa": 1.0, "kPa": 1e3, "MPa": 1e6, "bar": 1e5, "mbar": 100.0, "hPa": 100.0, "atm": 101325.0,
           "Torr": 101325.0 / 760, "mmHg": 133.322387415, "psi": 6894.757293168}
V_UNITS = {"m3": 1.0, "m³": 1.0, "L": 1e-3, "mL": 1e-6, "cm3": 1e-6, "cm³": 1e-6}
N_UNITS = {"mol": 1.0, "mmol": 1e-3, "kmol": 1e3}
IDEAL_NOTE = ("Ideales Gas: gut bei niedrigem Druck und hoher Temperatur; nahe der Kondensation oder bei hohen "
              "Drücken weicht das reale Gas ab.")


class GasError(C.ChemError):
    pass


def _f(v, what):
    try:
        x = float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        raise GasError(f"{what}: Zahl erwartet")
    return x


def T_K(v, unit="°C") -> float:
    x = _f(v, "Temperatur")
    k = x + 273.15 if unit in ("°C", "C") else x if unit == "K" else None
    if k is None:
        raise GasError("Temperatureinheit °C oder K")
    if k <= 0:
        raise GasError("Temperatur muss über 0 K liegen")
    return k


def _conv(v, unit, table, what):
    if unit not in table:
        raise GasError(f"{what}: Einheit „{unit}“ ({', '.join(table)})")
    x = _f(v, what) * table[unit]
    if x <= 0:
        raise GasError(f"{what} muss grösser als 0 sein")
    return x


def ideal(p=None, V=None, n=None, T=None, p_unit="kPa", V_unit="L", n_unit="mol", T_unit="°C") -> dict:
    """Genau eine der Grössen p, V, n, T offen (None) -> berechnet. Ergebnis in SI und in den gewählten Einheiten."""
    given = {"p": p, "V": V, "n": n, "T": T}
    miss = [k for k, v in given.items() if v in (None, "")]
    if len(miss) != 1:
        raise GasError("Genau eine Grösse leer lassen")
    si = {}
    if p not in (None, ""):
        si["p"] = _conv(p, p_unit, P_UNITS, "Druck")
    if V not in (None, ""):
        si["V"] = _conv(V, V_unit, V_UNITS, "Volumen")
    if n not in (None, ""):
        si["n"] = _conv(n, n_unit, N_UNITS, "Stoffmenge")
    if T not in (None, ""):
        si["T"] = T_K(T, T_unit)
    k = miss[0]
    if k == "p":
        si["p"] = si["n"] * R * si["T"] / si["V"]
    elif k == "V":
        si["V"] = si["n"] * R * si["T"] / si["p"]
    elif k == "n":
        si["n"] = si["p"] * si["V"] / (R * si["T"])
    else:
        si["T"] = si["p"] * si["V"] / (si["n"] * R)
    shown = {"p": si["p"] / P_UNITS[p_unit], "V": si["V"] / V_UNITS[V_unit], "n": si["n"] / N_UNITS[n_unit],
             "T": si["T"] - 273.15 if T_unit in ("°C", "C") else si["T"]}
    return {"solved": k, "si": si, "value": shown[k], "values": shown,
            "units": {"p": p_unit, "V": V_unit, "n": n_unit, "T": T_unit}, "notes": [IDEAL_NOTE], "refs": REFS}


def molar_volume(T=0, p=100, T_unit="°C", p_unit="kPa") -> dict:
    """Molvolumen RT/p in L/mol bei genannten Bedingungen (IUPAC-STP: 0 °C, 100 kPa -> 22,711 L/mol)."""
    t, pp = T_K(T, T_unit), _conv(p, p_unit, P_UNITS, "Druck")
    return {"Vm_L_mol": R * t / pp * 1000, "T_K": t, "p_Pa": pp, "notes": [IDEAL_NOTE], "refs": REFS}


def density(formula_or_M, T=0, p=100, T_unit="°C", p_unit="kPa") -> dict:
    """Gasdichte ρ = pM/(RT) in g/L."""
    M = formula_or_M if isinstance(formula_or_M, (int, float)) else C.molar_mass(str(formula_or_M))["M"]
    t, pp = T_K(T, T_unit), _conv(p, p_unit, P_UNITS, "Druck")
    return {"rho_g_L": pp * M / (R * t) / 1000, "M": M, "T_K": t, "p_Pa": pp, "notes": [IDEAL_NOTE],
            "refs": REFS + ["ciaaw2024"]}


def mass_to_volume(formula, m_g, T=0, p=100, T_unit="°C", p_unit="kPa") -> dict:
    d = density(formula, T, p, T_unit, p_unit)
    m = _f(m_g, "Masse")
    if m <= 0:
        raise GasError("Masse muss grösser als 0 sein")
    return {**d, "m_g": m, "V_L": m / d["rho_g_L"], "n_mol": m / d["M"]}


def mixture(components: dict, p_total, p_unit="kPa", basis="n") -> dict:
    """Dalton: Stoffmengenanteile xᵢ und Partialdrücke pᵢ = xᵢ·p. components = {Name: Stoffmenge} (basis "n") oder
    {Name: Volumenanteil} (basis "x", ideal = Stoffmengenanteil)."""
    if not components:
        raise GasError("Keine Bestandteile")
    vals = {k: _f(v, f"Menge {k}") for k, v in components.items()}
    if any(v < 0 for v in vals.values()):
        raise GasError("Mengen ≥ 0")
    s = sum(vals.values())
    if s <= 0:
        raise GasError("Summe muss grösser als 0 sein")
    pt = _conv(p_total, p_unit, P_UNITS, "Gesamtdruck")
    rows = {k: {"x": v / s, "p": v / s * pt / P_UNITS[p_unit]} for k, v in vals.items()}
    notes = [IDEAL_NOTE]
    if basis == "x" and abs(s - 1) > 1e-6 and abs(s - 100) > 1e-6:
        notes.append(f"Anteile ergeben {s:g}".replace(".", ",") + ", nicht 1 bzw. 100 %; normiert.")
    return {"components": rows, "p_total": pt / P_UNITS[p_unit], "p_unit": p_unit, "notes": notes,
            "refs": REFS}
