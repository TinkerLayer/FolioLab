"""Synthetische TGA-Läufe für Tests und zum Ausprobieren (in der Oberfläche als „synthetisch“ gekennzeichnet).

Jede Stufe ist eine Reaktion n-ter Ordnung mit Arrhenius-Geschwindigkeit, dα/dt = A·exp(−Eₐ/RT)·(1−α)ⁿ, numerisch
integriert über dem Temperaturprogramm. Dadurch verschieben sich die Stufen mit der Heizrate wie bei echten Proben
(Kinetik-Auswertungen finden die vorgegebene Aktivierungsenergie wieder). Der Vorfaktor A wird so gewählt, dass die
DTG-Spitze bei 10 K/min an der gewünschten Temperatur liegt (Kissinger-Bedingung für n = 1).

Stöchiometrische Massenverluste aus den Standard-Atomgewichten (siehe composition.py).
"""
from __future__ import annotations

import math

import numpy as np

R = 8.314462618   # J/(mol K), CODATA 2022 (exakt aus k_B·N_A)


def A_for_peak(Ea_kJ: float, Tp_C: float, beta: float = 10.0) -> float:
    """Vorfaktor (1/min), der bei Heizrate beta (K/min) die DTG-Spitze einer Reaktion 1. Ordnung bei Tp setzt."""
    Ea = Ea_kJ * 1000
    Tp = Tp_C + 273.15
    return Ea * beta / (R * Tp * Tp) * math.exp(Ea / (R * Tp))


def program(segments, dt: float = 0.05):
    """Temperaturprogramm aus Segmenten [("ramp", T_end, K/min) | ("iso", Minuten)] ab 25 °C; gibt t (min), T (°C)."""
    t, T = [0.0], [25.0]
    for s in segments:
        if s[0] == "ramp":
            T_end, rate = float(s[1]), float(s[2])
            n = max(2, int(abs(T_end - T[-1]) / abs(rate) / dt))
            tt = np.linspace(0, abs(T_end - T[-1]) / abs(rate), n + 1)[1:]
            t += list(t[-1] + tt)
            T += list(T[-1] + np.sign(T_end - T[-1]) * abs(rate) * tt)
        else:
            n = max(2, int(float(s[1]) / dt))
            tt = np.linspace(0, float(s[1]), n + 1)[1:]
            t += list(t[-1] + tt)
            T += [T[-1]] * len(tt)
    return np.array(t), np.array(T)


def simulate(steps, t, T, m0: float = 10.0, gas=None, noise: float = 0.0, seed: int = 0):
    """steps: Liste dict(frac=Massenanteil, Ea=kJ/mol, A=1/min, n=Ordnung, gas="Luft" -> nur unter diesem Gas).
    Gibt die Masse in mg zurück."""
    rng = np.random.default_rng(seed)
    loss = np.zeros(len(t))
    for st in steps:
        a = 0.0
        alpha = np.zeros(len(t))
        Ea = st["Ea"] * 1000
        A = st["A"]
        n = st.get("n", 1.0)
        only = st.get("gas")
        for i in range(1, len(t)):
            h = t[i] - t[i - 1]
            if only and gas is not None and gas[i] != only:
                alpha[i] = a
                continue
            Tk = T[i] + 273.15
            k = A * math.exp(-Ea / (R * Tk))
            # implizit für 1. Ordnung stabil, sonst kleine Unterschritte
            if n == 1:
                a = 1 - (1 - a) * math.exp(-k * h)
            else:
                sub = 20
                for _ in range(sub):
                    a = min(1.0, a + h / sub * k * max(0.0, 1 - a) ** n)
            alpha[i] = a
        loss += st["frac"] * alpha
    m = m0 * (1 - loss)
    if noise:
        m = m + rng.normal(0, noise, len(m))
    return m


def oxalate(beta: float = 10.0, m0: float = 10.0, noise: float = 0.0005, gas: str = "N₂"):
    """Calciumoxalat-Monohydrat: H₂O (12,33 %), CO (19,17 %), CO₂ (30,12 %), bezogen auf die Einwaage."""
    t, T = program([("ramp", 950, beta)])
    steps = [dict(frac=0.1233, Ea=90, A=A_for_peak(90, 190)),
             dict(frac=0.1917, Ea=190, A=A_for_peak(190, 500)),
             dict(frac=0.3012, Ea=200, A=A_for_peak(200, 740))]
    return t, T, simulate(steps, t, T, m0, noise=noise)


def filled_polymer(beta: float = 20.0, m0: float = 15.0, noise: float = 0.0008):
    """Gefülltes Elastomer nach ASTM E1131: Feuchte, Weichmacher, Polymer (N₂), Russ (nach Wechsel auf Luft), Asche."""
    t1, T1 = program([("ramp", 600, beta), ("iso", 5)])
    t2, T2 = program([("ramp", 850, beta)])
    # zweites Programm beginnt bei 600 °C weiter
    t2 = t2[T2 >= 600]
    T2 = T2[T2 >= 600]
    t = np.concatenate([t1, t1[-1] + (t2 - t2[0]) + 0.05])
    T = np.concatenate([T1, T2])
    gas = np.array(["N₂"] * len(t1) + ["Luft"] * len(t2), dtype=object)
    steps = [dict(frac=0.008, Ea=60, A=A_for_peak(60, 90, beta), n=1),
             dict(frac=0.12, Ea=110, A=A_for_peak(110, 300, beta)),
             dict(frac=0.48, Ea=220, A=A_for_peak(220, 455, beta)),
             dict(frac=0.30, Ea=150, A=A_for_peak(150, 640, beta), gas="Luft")]
    return t, T, simulate(steps, t, T, m0, gas=gas, noise=noise), gas


def kinetics_series(rates=(5, 10, 20, 40), Ea: float = 180.0, Tp10: float = 450.0, n: float = 1.0, m0: float = 8.0):
    """Ein Polymer mit einer Stufe bei mehreren Heizraten (für die Kinetik-Auswertung)."""
    A = A_for_peak(Ea, Tp10, 10.0)
    out = []
    for b in rates:
        t, T = program([("ramp", 700, b)], dt=min(0.05, 0.5 / b))
        out.append((b, t, T, simulate([dict(frac=0.97, Ea=Ea, A=A, n=n)], t, T, m0, noise=0.0003, seed=int(b))))
    return out


def csv_text(name, t, T, m, m0, rate=None, gas=None, extra_head=()):
    head = [f"# Probe: {name}", f"# Einwaage: {m0:.4f} mg", "# Herkunft: synthetisch (Folio Lab, tga/synth.py)"]
    if rate:
        head.append(f"# Heizrate: {rate} K/min")
    head += list(extra_head)
    cols = "Zeit/min;Temperatur/°C;Masse/mg" + (";Gas" if gas is not None else "")
    rows = [f"{a:.4f};{b:.3f};{c:.5f}" + (f";{g}" if gas is not None else "")
            for a, b, c, g in zip(t, T, m, gas if gas is not None else [None] * len(t))]
    return "\n".join(head + [cols] + rows) + "\n"


SAMPLES = {
    "oxalat": ("Calciumoxalat-Monohydrat (synthetisch, 10 K/min, N₂)", "Kalibrierprobe"),
    "elastomer": ("Gefülltes Elastomer, N₂ → Luft (synthetisch, 20 K/min)", "Zusammensetzung ASTM E1131"),
    "kinetik": ("Ein Polymer bei 5/10/20/40 K/min (synthetisch)", "Kinetik"),
}


def make(which: str):
    """Liefert [(Dateiinhalt, Dateiname)]."""
    if which == "oxalat":
        t, T, m = oxalate()
        return [(csv_text("Calciumoxalat-Monohydrat (synthetisch)", t, T, m, 10.0, 10, None,
                          ["# Gas: Stickstoff 50 ml/min", "# Tiegel: Al2O3"]).encode("utf-8"), "Calciumoxalat_synth.csv")]
    if which == "elastomer":
        t, T, m, gas = filled_polymer()
        return [(csv_text("Gefülltes Elastomer (synthetisch)", t, T, m, 15.0, 20, gas,
                          ["# Gas: Stickstoff, ab 600 °C Luft"]).encode("utf-8"), "Elastomer_synth.csv")]
    if which == "kinetik":
        return [(csv_text(f"Polymer {b} K/min (synthetisch)", t, T, m, 8.0, b).encode("utf-8"), f"Polymer_{b}Kmin_synth.csv")
                for b, t, T, m in kinetics_series()]
    raise KeyError(which)
