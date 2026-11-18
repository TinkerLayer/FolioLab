"""Adiabate Flammentemperatur bei konstantem Druck (ER-705).

Energiebilanz Σ n_E [ΔfH°_E + H_E(T₀) − H_E(298)] = Σ n_P [ΔfH°_P + H_P(T_ad) − H_P(298)] mit Cp(T) aus den
NASA-7-Polynomen (Burcat). Vollständige Verbrennung zu CO₂, H₂O(g), N₂ (und SO₂), Überschuss-O₂ bleibt.
Dissoziation (CO, H₂, OH, H, O, NO) ist nicht berücksichtigt; dadurch liegt T_ad oberhalb von etwa 2000 K
spürbar zu hoch (Methan/Luft: rund 100 K über dem Gleichgewichtswert). Das steht in jedem Ergebnis.
Nur magere und stöchiometrische Gemische (φ ≤ 1); fette Gemische brauchen ein Gleichgewichtsmodell.
"""
from __future__ import annotations

from . import chem as C
from . import thermo as TH
from . import thermo_t as TT

AIR_N2_O2 = 79.0 / 21.0          # Molverhältnis N₂/O₂ in trockener Luft (gerundet, Ar zu N₂ gezählt)


class FlameError(C.ChemError):
    pass


def _entry(text: str, ph: str | None):
    sp = C.parse_species(text)
    cands = [e for e in TH.candidates(sp) if not ph or e["ph"] == ph]
    best = TH._best(cands)
    if not best or best.get("H") is None:
        raise FlameError(f"Keine Bildungsenthalpie für {text}")
    n = TT.nasa_entry(sp, TH.entry_id(best), best["ph"], best.get("key"), best.get("H"), best.get("S"))
    return {"species": text, "H": best["H"], "src": best["src"], "refs": TH.SRC_REFS.get(best["src"], []),
            "nasa": n["nasa"] if n else None, "poly": n.get("name") if n else None}


def adiabatic(fuel: str, phi: float = 1.0, oxidant: str = "air", T0: float = 298.15) -> dict:
    sp = C.parse_species(fuel)
    comp = {k: float(v) for k, v in sp.counts.items()}
    bad = set(comp) - {"C", "H", "O", "N", "S"}
    if bad or not (comp.get("C") or comp.get("H")):
        raise FlameError("Brennstoff aus C, H, O, N, S angeben (mindestens C oder H)")
    if not 0.2 <= phi <= 1.0:
        raise FlameError("Äquivalenzverhältnis φ zwischen 0,2 und 1 (fette Gemische nicht unterstützt)")
    if oxidant not in ("air", "O2"):
        raise FlameError("Oxidationsmittel: air oder O2")
    c, h, o, n, s = (comp.get(k, 0) for k in "CHONS")
    o2_st = c + h / 4 + s - o / 2
    if o2_st <= 0:
        raise FlameError("Brennstoff braucht keinen Sauerstoff")
    o2 = o2_st / phi
    n2_air = o2 * AIR_N2_O2 if oxidant == "air" else 0.0
    react = [(fuel, None, 1.0), ("O2", "g", o2)] + ([("N2", "g", n2_air)] if n2_air else [])
    prod = [(k, "g", v) for k, v in (("CO2", c), ("H2O", h / 2), ("SO2", s), ("N2", n / 2 + n2_air),
                                       ("O2", o2 - o2_st)) if v > 1e-12]
    rows, refs = [], []
    hr = 0.0
    for text, ph, nu in react:
        e = _entry(text, ph)
        if abs(T0 - TH.T0) > 0.01 and not e["nasa"]:
            raise FlameError(f"Für {text} fehlt Cp(T); Anfangstemperatur nur 298,15 K möglich")
        hr += nu * (e["H"] + (TT.h_rel(e["nasa"], T0) if e["nasa"] and abs(T0 - TH.T0) > 0.01 else 0.0))
        rows.append({"side": "E", "species": text, "n": nu, "H": e["H"], "poly": e["poly"]})
        refs += e["refs"]
    pe = []
    for text, ph, nu in prod:
        e = _entry(text, ph)
        if not e["nasa"]:
            raise FlameError(f"Für {text} fehlt ein Cp(T)-Polynom")
        pe.append((e, nu))
        rows.append({"side": "P", "species": text, "n": nu, "H": e["H"], "poly": e["poly"]})
        refs += e["refs"]

    def f(T):
        return sum(nu * (e["H"] + TT.h_rel(e["nasa"], T)) for e, nu in pe) - hr

    lo, hi = TH.T0, 6000.0
    if f(lo) > 0:
        raise FlameError("Reaktion setzt keine Wärme frei (Produkte bei 298 K energiereicher)")
    if f(hi) < 0:
        raise FlameError("T_ad über 6000 K: ausserhalb der Polynome")
    for _ in range(100):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if f(mid) < 0 else (lo, mid)
    T = (lo + hi) / 2
    outside = [e["species"] for e, _ in pe if not e["nasa"]["T"][0] - 1 <= T <= e["nasa"]["T"][-1] + 1]
    tot = sum(nu for _, nu in pe)
    notes = ["Vollständige Verbrennung, Dissoziation nicht berücksichtigt: oberhalb von etwa 2000 K liegt der Wert "
             "zu hoch (Methan/Luft rund 100 K über dem Gleichgewichtswert).",
             "Konstanter Druck, keine Wärmeverluste; H₂O gasförmig."]
    if oxidant == "air":
        notes.append("Luft als 21 % O₂ und 79 % N₂ (Argon zu N₂ gezählt).")
    if outside:
        notes.append("Ausserhalb des Gültigkeitsbereichs der Polynome: " + ", ".join(outside) + ".")
    return {"fuel": fuel, "phi": phi, "oxidant": oxidant, "T0": T0, "T_ad": T, "dH_comb": sum(nu * e["H"] for e, nu in pe) - hr,
            "O2_stoich": o2_st, "rows": rows,
            "products": [{"species": e["species"], "n": nu, "x": nu / tot} for e, nu in pe],
            "notes": notes, "refs": list(dict.fromkeys(refs + ["burcat2018", "mcbride2002", "turns2012"]))}
