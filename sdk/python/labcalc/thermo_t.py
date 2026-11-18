"""Temperaturabhängige Reaktionsgrössen (ER-701): ΔrH(T), ΔrS(T), ΔrG(T), K(T).

Modelle (immer im Ergebnis genannt):
- "cp":    ΔrH(T) = ΔrH°(298) + Σν[H(T) − H(298)], ΔrS(T) = ΔrS°(298) + Σν[S(T) − S(298)] mit den NASA-7-Polynomen
           der Burcat-Datenbank (McBride et al. 2002 für die Form). ΔrH°(298) und ΔrS°(298) stammen aus den gewählten
           Tabellenwerten; die Polynome liefern nur den Temperaturverlauf. Gültig im Bereich jedes Polynoms.
- "cp298": Cp jedes Stoffs konstant (Wert bei 298 K), wenn ein Polynom fehlt.
- "const": ΔrH und ΔrS konstant (Näherung von Ulich, erste Näherung) – immer zusätzlich zum Vergleich.
Phasenumwandlungen zwischen 298 K und T werden nicht berücksichtigt (Hinweis bei kondensierten Stoffen).
"""
from __future__ import annotations

import math

from . import chem as C
from . import thermo as TH

R = TH.R                       # J/(mol K)
T0 = TH.T0


def _coef(n: dict, T: float):
    t = n["T"]
    return n["lo"] if len(t) == 2 or T <= t[1] else n["hi"]


def cp(n: dict, T: float) -> float:
    a = _coef(n, T)
    return R * (a[0] + a[1] * T + a[2] * T ** 2 + a[3] * T ** 3 + a[4] * T ** 4)


def _h(n: dict, T: float) -> float:                       # H(T) in J/mol (Burcat-Konvention)
    a = _coef(n, T)
    return R * T * (a[0] + a[1] * T / 2 + a[2] * T ** 2 / 3 + a[3] * T ** 3 / 4 + a[4] * T ** 4 / 5 + a[5] / T)


def _s(n: dict, T: float) -> float:                       # S°(T) in J/(mol K)
    a = _coef(n, T)
    return R * (a[0] * math.log(T) + a[1] * T + a[2] * T ** 2 / 2 + a[3] * T ** 3 / 3 + a[4] * T ** 4 / 4 + a[6])


def h_rel(n: dict, T: float) -> float:
    """H(T) − H(298,15 K) in kJ/mol."""
    return (_h(n, T) - _h(n, T0)) / 1000


def s_rel(n: dict, T: float) -> float:
    """S(T) − S(298,15 K) in J/(mol K)."""
    return _s(n, T) - _s(n, T0)


def nasa_entry(sp: C.Species, entry_id: str | None, ph: str, key: str | None, H: float | None,
               S: float | None = None) -> dict | None:
    """Burcat-Eintrag mit Polynom zum gewählten Tabelleneintrag: derselbe Eintrag, sonst gleiche Phase und gleicher
    Stoff (InChIKey), Grundzustand bevorzugt, dann ΔfH° und S° am nächsten am gewählten Tabellenwert."""
    cands = TH.candidates(sp)
    same = next((e for e in cands if TH.entry_id(e) == entry_id and e.get("nasa")), None)
    if same:
        return same
    pool = [e for e in cands if e.get("nasa") and e["ph"] == ph and (not key or not e.get("key") or e["key"] == key)]
    if not pool:
        return None
    def dist(e):
        d = abs((e.get("H") or 0) - H) if H is not None else 0
        return d + (abs((e.get("S") or 0) - S) if S is not None else 0)
    return sorted(pool, key=lambda e: (not TH._plain_burcat(e) and not e.get("poly", "").lower().startswith("anharm"),
                                       dist(e)))[0]


def reaction_T(eq: C.Equation, coefs, T: float, choices: dict | None = None, key_hints: dict | None = None) -> dict:
    """Reaktionsgrössen bei T (K) mit Cp(T); Konstant-Näherung zum Vergleich."""
    T = float(T)
    if not 50 <= T <= 6000:
        raise TH.ThermoError("T zwischen 50 und 6000 K angeben")
    base = TH.reaction(eq, coefs, T0, choices, key_hints)
    if base.get("error"):
        return base
    ok = [r for r in base["rows"] if "error" not in r]
    if base.get("dH") is None or base.get("dS") is None:
        raise TH.ThermoError("ΔrH° und ΔrS° bei 298 K werden für die Temperaturabhängigkeit gebraucht")
    species, notes, outside = [], [], []
    polys = []
    for r in ok:
        sp = eq.terms[r["i"]].species
        n = nasa_entry(sp, r.get("id"), r.get("ph"), r.get("key"), r.get("H"), r.get("S"))
        row = {"i": r["i"], "species": r["species"], "nu": r["nu"], "ph": r.get("ph")}
        if n:
            lo, hi = n["nasa"]["T"][0], n["nasa"]["T"][-1]
            row.update({"poly": n.get("name"), "T_range": [lo, hi], "in_range": lo - 1 <= T <= hi + 1,
                        "Cp_T": cp(n["nasa"], T)})
            if not row["in_range"]:
                outside.append(f"{r['species']} ({lo:g}–{hi:g} K)")
        polys.append(n)
        species.append(row)
    dH, dS = base["dH"], base["dS"]
    if all(polys):
        model = "cp"
        dH_T = dH + sum(r["nu"] * h_rel(n["nasa"], T) for r, n in zip(ok, polys))
        dS_T = dS + sum(r["nu"] * s_rel(n["nasa"], T) for r, n in zip(ok, polys))
        dCp_T = sum(r["nu"] * cp(n["nasa"], T) for r, n in zip(ok, polys))
    elif base.get("dCp") is not None:
        model = "cp298"
        dCp = base["dCp"]
        dH_T = dH + dCp * (T - T0) / 1000
        dS_T = dS + dCp * math.log(T / T0)
        dCp_T = dCp
        notes.append("Für " + ", ".join(s["species"] for s, n in zip(species, polys) if not n)
                     + " fehlt ein Cp(T)-Polynom: Cp aller Stoffe konstant mit dem Wert bei 298 K.")
    else:
        model = "const"
        dH_T, dS_T, dCp_T = dH, dS, None
        notes.append("Cp fehlt: ΔrH und ΔrS als temperaturunabhängig angenommen (Näherung).")
    if outside:
        notes.append("Ausserhalb des Gültigkeitsbereichs der Polynome: " + ", ".join(outside) + ".")
    if any(r.get("ph") in ("cr", "l") for r in ok) and abs(T - T0) > 1:
        notes.append("Kondensierte Stoffe: Phasenumwandlungen (Schmelzen, Verdampfen, Modifikationswechsel) "
                     "zwischen 298 K und T sind nicht berücksichtigt.")
    dG_T = dH_T - T * dS_T / 1000
    x = -dG_T * 1000 / (R * T)
    dG_c = dH - T * dS / 1000
    xc = -dG_c * 1000 / (R * T)
    out = {"T": T, "model": model, "dH": dH, "dS": dS, "dG298": base.get("dG"), "dH_T": dH_T, "dS_T": dS_T,
           "dG_T": dG_T, "dCp_T": dCp_T, "lnK_T": x, "lgK_T": x / math.log(10), "K_T": math.exp(x) if x < 700 else math.inf,
           "const": {"dG_T": dG_c, "lgK_T": xc / math.log(10)}, "species": species, "outside": outside,
           "notes": list(dict.fromkeys(base.get("notes", []) + notes)), "dn_gas": base.get("dn_gas"),
           "refs": list(dict.fromkeys(base.get("refs", []) + (["burcat2018", "mcbride2002"] if model == "cp" else [])))}
    if out["dn_gas"] and not any(r.get("ph") == "aq" for r in ok):
        out["lgKc_T"] = out["lgK_T"] + out["dn_gas"] * math.log10(TH.P0 / (R * T * TH.C0))
    if dH_T and dS_T and model != "const":
        # Gleichgewichtstemperatur ΔrG(T) = 0 im Cp-Modell (Bisektion), falls im Bereich 200–3000 K
        f = lambda t: _dG(eq, ok, polys, dH, dS, base, t, model)       # noqa: E731
        lo_, hi_ = 200.0, 3000.0
        if f(lo_) * f(hi_) < 0:
            for _ in range(80):
                mid = (lo_ + hi_) / 2
                lo_, hi_ = (mid, hi_) if f(lo_) * f(mid) > 0 else (lo_, mid)
            out["T_eq"] = (lo_ + hi_) / 2
    return out


def _dG(eq, ok, polys, dH, dS, base, T, model):
    if model == "cp":
        h = dH + sum(r["nu"] * h_rel(n["nasa"], T) for r, n in zip(ok, polys))
        s = dS + sum(r["nu"] * s_rel(n["nasa"], T) for r, n in zip(ok, polys))
    else:
        h = dH + base["dCp"] * (T - T0) / 1000
        s = dS + base["dCp"] * math.log(T / T0)
    return h - T * s / 1000


def dG_points(eq: C.Equation, coefs, Ts, choices=None, key_hints=None) -> dict | None:
    """ΔrG(T) im Cp-Modell für viele T (Datensätze nur einmal gesucht); None ohne Cp-Daten."""
    base = TH.reaction(eq, coefs, T0, choices, key_hints)
    if base.get("error") or base.get("dH") is None or base.get("dS") is None:
        return None
    ok = [r for r in base["rows"] if "error" not in r]
    polys = [nasa_entry(eq.terms[r["i"]].species, r.get("id"), r.get("ph"), r.get("key"), r.get("H"), r.get("S"))
             for r in ok]
    model = "cp" if all(polys) else ("cp298" if base.get("dCp") is not None else None)
    if not model:
        return None
    return {"model": model, "points": [(T, _dG(eq, ok, polys, base["dH"], base["dS"], base, T, model)) for T in Ts]}


def curve(eq: C.Equation, coefs, T1: float, T2: float, n: int = 41, choices=None, key_hints=None) -> dict:
    """lg K(T) im Cp-Modell und in der Konstant-Näherung; van 't Hoff: d ln K / d(1/T) = −ΔrH(T)/R."""
    T1, T2 = sorted((float(T1), float(T2)))
    pts = []
    for k in range(n):
        T = T1 + (T2 - T1) * k / (n - 1)
        r = reaction_T(eq, coefs, T, choices, key_hints)
        if r.get("error"):
            return r
        pts.append({"T": T, "lgK": r["lgK_T"], "lgK_const": r["const"]["lgK_T"], "dH_T": r["dH_T"], "dG_T": r["dG_T"]})
    return {"points": pts, "model": r["model"], "refs": r["refs"], "notes": r["notes"]}


def vant_hoff(lnK1: float, T1: float, T2: float, dH_kJ: float) -> float:
    """ln K(T2) aus ln K(T1) mit konstantem ΔrH (integrierte van-'t-Hoff-Gleichung)."""
    return lnK1 - dH_kJ * 1000 / R * (1 / T2 - 1 / T1)
