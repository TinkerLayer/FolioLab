"""Metall–Ligand-Speziation (ER-S02) aus den Stabilitätskonstanten (NIST SRD 46) und den Protonierungskonstanten
des Liganden.

Modell: einkernige Komplexe MLₙ (lg βₙ) und, wo vorhanden, MHL (lg K = [MHL]/[ML][H]); pH vorgegeben (gepuffert).
Massenbilanzen für Metall und Ligand werden gelöst (Bisektion in lg[L]); die Ladungsbilanz ist bei vorgegebenem pH
nicht geschlossen – ihr Rest ist die Ladung, die Puffer und Gegenionen ausgleichen müssen (wird angegeben).
Hydroxid als Ligand: [OH⁻] folgt aus dem pH. Mehrkernige Komplexe und Niederschläge sind nicht enthalten.
Konstanten gelten bei ihrer Ionenstärke (Konzentrationskonstanten); keine Umrechnung.
"""
from __future__ import annotations

import math

from . import acidbase as AB
from . import chem as C
from . import substances as S

REFS = ["srd46", "harris"]
HYDROXIDE = {"oh-", "oh⁻", "hydroxide", "hydroxid", "hydroxide ion", "hydroxidion"}


class SpeciationError(C.ChemError):
    pass


def _charge(text: str) -> int:
    """Ladung aus „Cu2+“, „Cu^2+“, „Fe³⁺“, „Fe+3“."""
    import re
    t = text.strip().translate(str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻", "0123456789+-"))
    m = re.search(r"\^?(\d*)([+-])(\d*)$", t)
    if not m:
        return 0
    n = int(m.group(1) or m.group(3) or 1)
    return n if m.group(2) == "+" else -n


def system(metal: str, ligand: str, T_C: float = 25.0) -> dict:
    zM = _charge(metal)
    if zM <= 0:
        raise SpeciationError("Metallion mit positiver Ladung angeben, z. B. Cu2+")
    betas, src = {}, {}
    for n in range(1, 9):
        try:
            v = S.logk(metal, ligand, n, T_C)
        except C.ChemError:
            continue
        betas[n], src[n] = v["value"], {k: v.get(k) for k in ("T_C", "I", "ref", "label")}
    if not betas:
        raise SpeciationError(f"keine Stabilitätskonstanten für {metal} / {ligand} in NIST SRD 46")
    hyd = ligand.strip().lower() in HYDROXIDE
    out = {"metal": metal, "ligand": ligand, "zM": zM, "betas": betas, "src": src, "hydroxide": hyd, "K_MHL": None,
           "notes": []}
    missing = [n for n in range(1, max(betas) + 1) if n not in betas]
    if missing:
        out["notes"].append("Keine Konstante für n = " + ", ".join(map(str, missing)) + " (Spezies fehlt im Modell).")
    if hyd:
        out.update(zL=-1, lig_steps=None)
        out["notes"].append("Hydroxokomplexe: nur einkernige Spezies; mehrkernige Komplexe und Fällung (Hydroxid, Oxid) "
                            "sind nicht berücksichtigt.")
        return out
    key = S.resolve(ligand)
    acid = AB.acid_system(key) if key else None
    if not acid or min(acid["steps"]) != 1:
        raise SpeciationError(f"keine vollständigen Protonierungskonstanten für den Liganden {ligand}")
    out["lig_steps"] = {j: v["value"] for j, v in acid["steps"].items()}
    out["zL"] = -acid["n"] + (0 if acid["n"] else 0)
    for v in S.logk_values(metal, ligand)["values"]:
        if v.get("def") == "[MHL]/[ML][H]" and abs((v.get("T_C") or 25) - T_C) <= 5:
            out["K_MHL"] = v["value"]
            break
    return out


def _alpha_L(sysd, pH):
    return dict(AB._forms({"steps": sysd["lig_steps"]}, pH)).get(0, 0.0)


def at_pH(sysd: dict, pH: float, c_M: float, c_L: float | None, pKw: float = 14.0) -> dict:
    H = 10 ** -pH
    b = sysd["betas"]
    kmhl = 10 ** sysd["K_MHL"] if sysd.get("K_MHL") is not None else 0.0

    def species(L):
        terms = {0: 1.0}
        for n, lb in b.items():
            terms[n] = 10 ** (lb + n * math.log10(L)) if L > 0 else 0.0
        mhl = kmhl * terms.get(1, 0.0) * H
        den = sum(terms.values()) + mhl
        M = c_M / den
        return M, {n: M * t for n, t in terms.items()}, M * mhl

    if sysd["hydroxide"]:
        L = 10 ** (pH - pKw)
        aL, iters = 1.0, 0
        M, conc, mhl = species(L)
        lig_res = None
    else:
        if not c_L or c_L <= 0:
            raise SpeciationError("Gesamtkonzentration des Liganden angeben")
        aL = _alpha_L(sysd, pH)
        if aL <= 0:
            aL = 1e-300

        def g(lgL):
            L = 10 ** lgL
            M, conc, mhl = species(L)
            return L / aL + sum(n * c for n, c in conc.items()) + mhl - c_L
        lo, hi = -40.0, math.log10(c_L * aL)
        iters = 0
        if g(hi) < 0:
            hi = math.log10(c_L)
        while hi - lo > 1e-13 and iters < 200:
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if g(mid) < 0 else (lo, mid)
            iters += 1
        L = 10 ** ((lo + hi) / 2)
        M, conc, mhl = species(L)
        lig_res = (L / aL + sum(n * c for n, c in conc.items()) + mhl - c_L) / c_L
    met_res = (sum(conc.values()) + mhl - c_M) / c_M
    zM, zL = sysd["zM"], sysd["zL"]
    charge = sum((zM + n * zL) * c for n, c in conc.items()) + mhl * (zM + zL + 1)
    rows = [{"n": n, "c": c, "frac": c / c_M, "charge": zM + n * zL} for n, c in sorted(conc.items())]
    if kmhl:
        rows.append({"n": "MHL", "c": mhl, "frac": mhl / c_M, "charge": zM + zL + 1})
    return {"pH": pH, "L_free": L, "alpha_L": aL, "M_free": M, "rows": rows, "iterations": iters,
            "residual_metal": met_res, "residual_ligand": lig_res, "charge_rest": charge,
            "conditional": {n: lb + n * math.log10(aL) for n, lb in b.items()}}


def saturation(salt: str, cation: str, c_cat: float, anion: str, c_an: float, I_extra: float = 0.0,
               model: str | None = "davies", T_C: float = 25.0) -> dict:
    """ER-S03: Sättigungsindex SI = lg(IAP/Ksp). IAP aus Aktivitäten (Davies bzw. erweiterte D–H), wenn Ksp bei
    I = 0 gilt; sonst aus Konzentrationen (Konzentrationskonstante). Ergebnis: „Fällung möglich“ (SI > 0) – keine
    vorhergesagte Menge (Kinetik, Übersättigung, Komplexbildung bleiben aussen vor)."""
    from . import activity as ACT
    zc, za = _charge(cation), _charge(anion)
    if zc <= 0 or za >= 0:
        raise SpeciationError("Kation mit positiver und Anion mit negativer Ladung angeben, z. B. Ca2+ und CO3^2-")
    if c_cat <= 0 or c_an <= 0:
        raise SpeciationError("Konzentrationen > 0 angeben")
    g = math.gcd(zc, -za)
    nu_c, nu_a = -za // g, zc // g
    k = S.ksp(salt, T_C)
    lgksp = k["value"]
    I = 0.5 * (c_cat * zc * zc + c_an * za * za) + max(0.0, I_extra)
    thermo = (k.get("I") in (None, 0, 0.0))
    if model and thermo:
        lgc, lga = ACT.log_gamma(zc, I, model, None, T_C), ACT.log_gamma(za, I, model, None, T_C)
    else:
        lgc = lga = 0.0
    lg_iap = nu_c * (math.log10(c_cat) + lgc) + nu_a * (math.log10(c_an) + lga)
    si = lg_iap - lgksp
    state = "übersättigt: Fällung möglich" if si > 0.05 else ("untersättigt: keine Fällung" if si < -0.05 else
                                                               "nahe Sättigung")
    notes = ["SI > 0 heisst nur, dass Fällung thermodynamisch möglich ist; ob und wie viel ausfällt, hängt von "
             "Keimbildung, Kinetik und Nebenreaktionen ab (keine Mengenvorhersage).",
             "Freie Ionenkonzentrationen eingesetzt: Komplexbildung und Protolyse (z. B. CO₃²⁻/HCO₃⁻) sind nicht "
             "berücksichtigt."]
    if not thermo:
        notes.append(f"Ksp gilt bei I = {k.get('I')} mol/L (Konzentrationskonstante): IAP aus Konzentrationen.")
    elif model:
        notes += ACT._notes(model, I)
    return {"salt": salt, "cation": cation, "anion": anion, "nu": [nu_c, nu_a], "c": [c_cat, c_an], "I": I,
            "model": model if thermo else None, "lg_gamma": [lgc, lga], "lg_IAP": lg_iap, "lgKsp": lgksp,
            "ksp_src": {x: k.get(x) for x in ("source", "T_C", "I", "label", "quality")}, "SI": si, "state": state,
            "notes": notes, "refs": list(dict.fromkeys(["srd46"] + list(k.get("sources") or [])
                                                        + (ACT.REFS[:2] if model and thermo else [])))}


def distribution(metal: str, ligand: str, c_M: float, c_L: float | None = None, pH_from: float = 0.0,
                 pH_to: float = 14.0, n: int = 141, T_C: float = 25.0) -> dict:
    if c_M <= 0:
        raise SpeciationError("Metallkonzentration > 0 angeben")
    sysd = system(metal, ligand, T_C)
    pts = [at_pH(sysd, pH_from + (pH_to - pH_from) * i / (n - 1), c_M, c_L) for i in range(n)]
    worst = max(max(abs(p["residual_metal"]), abs(p["residual_ligand"] or 0)) for p in pts)
    notes = list(sysd["notes"]) + [
        "pH vorgegeben (gepuffert): die Ladungsbilanz gleichen Puffer und Gegenionen aus; ihr Rest ist angegeben.",
        "Konstanten bei ihrer Ionenstärke (NIST SRD 46), nicht umgerechnet."]
    return {"metal": metal, "ligand": ligand, "c_M": c_M, "c_L": c_L, "betas": sysd["betas"], "src": sysd["src"],
            "K_MHL": sysd.get("K_MHL"), "lig_steps": sysd.get("lig_steps"), "zM": sysd["zM"], "zL": sysd["zL"],
            "points": pts, "max_residual": worst, "notes": notes, "refs": REFS}
