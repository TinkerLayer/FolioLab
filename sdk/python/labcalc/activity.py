"""Aktivitätskoeffizienten (ER-S01): Davies und erweiterte Debye–Hückel-Gleichung.

lg γ = −A z² (√I/(1+√I) − 0,3 I)                       Davies (1962), brauchbar bis I ≈ 0,5 mol/L
lg γ = −A z² √I / (1 + B a √I)                          erweitert (Debye–Hückel 1923, Ionengrössen a nach Kielland 1937),
                                                        brauchbar bis I ≈ 0,1 mol/L
A und B aus der Dielektrizitätszahl von Wasser (Malmberg & Maryott 1956) und der Dichte (Kell 1975):
A = 1,82483·10⁶ √ρ / (εT)^{3/2},  B = 50,2916 √ρ / (εT)^{1/2} Å⁻¹ (ρ in g/cm³); bei 25 °C A = 0,511, B = 0,329.
Neutrale Teilchen: γ = 1. pH korrigiert = −lg a(H⁺).
"""
from __future__ import annotations

import math

from . import acidbase as AB

MODELS = ("davies", "edh")
LIMIT = {"davies": 0.5, "edh": 0.1}
# Ionengrössen a in pm (Kielland 1937); andere Ionen: typische Werte je Ladung (Annahme, im Ergebnis genannt)
SIZE_H, SIZE_OH = 900.0, 350.0
SIZE_BY_CHARGE = {1: 400.0, 2: 600.0, 3: 900.0, 4: 1100.0}
REFS = ["davies1962", "kielland1937", "malmberg1956", "kell1975", "harris"]


class ActivityError(ValueError):
    pass


def dielectric(T_C: float) -> float:
    """Dielektrizitätszahl von Wasser 0–100 °C (Malmberg & Maryott 1956)."""
    t = float(T_C)
    return 87.740 - 0.40008 * t + 9.398e-4 * t * t - 1.410e-6 * t ** 3


def dh_constants(T_C: float = 25.0) -> tuple[float, float]:
    """(A in (mol/L)^-1/2, B in Å⁻¹ (mol/L)^-1/2) für lg γ."""
    if not 0 <= T_C <= 100:
        raise ActivityError("Temperatur 0–100 °C")
    rho = AB.water_density(T_C) / 1000
    eT = dielectric(T_C) * (T_C + 273.15)
    return 1.82483e6 * math.sqrt(rho) / eT ** 1.5, 50.2916 * math.sqrt(rho) / math.sqrt(eT)


def log_gamma(z: int, I: float, model: str = "davies", a_pm: float | None = None, T_C: float = 25.0) -> float:
    if model not in MODELS:
        raise ActivityError("Modell: davies oder edh")
    if z == 0 or I <= 0:
        return 0.0
    A, B = dh_constants(T_C)
    s = math.sqrt(I)
    if model == "davies":
        return -A * z * z * (s / (1 + s) - 0.3 * I)
    a = (a_pm if a_pm else SIZE_BY_CHARGE.get(min(abs(z), 4), 900.0)) / 100.0   # pm -> Å
    return -A * z * z * s / (1 + B * a * s)


def gamma(z: int, I: float, model: str = "davies", a_pm: float | None = None, T_C: float = 25.0) -> float:
    return 10 ** log_gamma(z, I, model, a_pm, T_C)


def _notes(model, I):
    out = []
    if I > LIMIT[model]:
        out.append(f"Ionenstärke {I:.3g} mol/L über dem Gültigkeitsbereich ({LIMIT[model]:g} mol/L) des Modells: "
                   .replace(".", ",") + "Werte nur grob.")
    if model == "edh":
        out.append("Ionengrössen: H⁺ 900 pm, OH⁻ 350 pm (Kielland 1937); übrige Ionen typische Werte je Ladung "
                   "(400/600/900 pm für |z| = 1/2/3).")
    return out


def ph_corrected(mixture, T_C: float = 25.0, model: str = "davies") -> dict:
    """pH = −lg a(H⁺) mit Aktivitätskoeffizienten; Ionenstärke iterativ. Ideal-Ergebnis daneben."""
    if model not in MODELS:
        raise ActivityError("Modell: davies oder edh")
    items = AB.parse_mixture(mixture) if isinstance(mixture, str) else mixture
    comps = [AB.component(t, float(c)) for t, c in items]
    T_C = 25.0 if T_C is None else float(T_C)
    kw = AB.pkw(T_C)
    ideal = AB.ph(items, T_C)
    I = ideal["I"]
    lg = lambda z, a=None: log_gamma(z, I, model, a, T_C)          # noqa: E731
    it, p = 0, ideal["pH"]
    for it in range(1, 60):
        gH, gOH = lg(1, SIZE_H), lg(-1, SIZE_OH)
        systems = []
        for c in comps:
            for y in c["systems"]:
                steps = {}
                for j, pk in y["steps"].items():
                    zj, zj1 = y["charge_h"] + j, y["charge_h"] + j - 1
                    steps[j] = pk + lg(zj1) - lg(zj)          # Konzentrationskonstante zum aktivitätsbasierten pH
                systems.append((y, steps))

        def bal(pH):
            H = 10 ** -pH / 10 ** gH
            OH = 10 ** (pH - kw) / 10 ** gOH
            s = H - OH
            for c in comps:
                s -= c["strong_acid"] - c["strong_base"]
            for y, st in systems:
                s -= y["c"] * (y["h"] - AB._nbar({"steps": st}, pH))
            return s
        lo, hi = -2.0, 16.5
        if bal(lo) < 0 or bal(hi) > 0:
            raise AB.AcidBaseError("pH ausserhalb −2 … 16,5")
        for _ in range(80):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if bal(mid) > 0 else (lo, mid)
        p = (lo + hi) / 2
        H, OH = 10 ** -p / 10 ** gH, 10 ** (p - kw) / 10 ** gOH
        I_new = 0.5 * (H + OH)
        for c in comps:
            I_new += sum(0.5 * cc * z * z for z, cc in c["ions"])
        for y, st in systems:
            for j, a in AB._forms({"steps": st}, p):
                z = y["charge_h"] + j
                I_new += 0.5 * y["c"] * a * z * z
        if abs(I_new - I) < 1e-12 * max(1.0, I):
            I = I_new
            break
        I = I_new
    return {"model": model, "pH": p, "pH_ideal": ideal["pH"], "dpH": p - ideal["pH"], "I": I, "iterations": it,
            "T_C": T_C, "A": dh_constants(T_C)[0], "gamma_H": gamma(1, I, model, SIZE_H, T_C),
            "gamma_1": gamma(1, I, model, None, T_C), "gamma_2": gamma(2, I, model, None, T_C),
            "notes": ["pH = −lg a(H⁺); ideal: pH aus Konzentrationen."] + _notes(model, I), "refs": REFS}


def buffer_corrected(b: dict, model: str = "davies") -> dict:
    """Pufferverhältnis mit Aktivitäten: [B]/[A] = 10^(pH − pKa) · γ(A)/γ(B); I aus den Pufferformen samt
    einwertigen Gegenionen (z. B. Na⁺ bzw. Cl⁻), iterativ."""
    T_C, pka, j = b["T_C"], b["pKa"], b["step"]
    h = AB.acid_system(b["key"])["n"]                 # Protonen der neutralen Form
    zA, zB = j - h, j - 1 - h                          # Ladung der Säureform HjL und der Basenform Hj-1L
    pH = math.log10(b["ratio_base_acid"]) + pka
    c_tot = b["acid_form_c"] + b["base_form_c"]
    I = 0.0
    for _ in range(60):
        r = 10 ** (pH - pka) * 10 ** (log_gamma(zA, I, model, None, T_C) - log_gamma(zB, I, model, None, T_C))
        ca, cb = c_tot / (1 + r), c_tot * r / (1 + r)
        I_new = 0.5 * (ca * (zA * zA + abs(zA)) + cb * (zB * zB + abs(zB)))
        if abs(I_new - I) < 1e-14:
            break
        I = I_new
    return {"model": model, "ratio_base_acid": r, "acid_form_c": ca, "base_form_c": cb, "I": I,
            "notes": ["Ionenstärke aus den Pufferformen und einwertigen Gegenionen."] + _notes(model, I), "refs": REFS}
