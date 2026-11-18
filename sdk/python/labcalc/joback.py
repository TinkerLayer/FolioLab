"""Gruppenbeitragsverfahren nach Joback & Reid (1987) für reine Stoffe aus der Struktur.

Joback, K. G.; Reid, R. C.: Estimation of pure-component properties from group-contributions.
Chem. Eng. Commun. 57 (1987) 233–243, doi:10.1080/00986448708960487. Gruppenwerte in der tabellarischen Wiedergabe
des Wikipedia-Artikels „Joback method“ (abgerufen 17.11.2026), geprüft am dort durchgerechneten Beispiel Aceton.

Alle Ergebnisse sind Schätzwerte und werden so gekennzeichnet. Gleichungen (T in K, Pc in bar, Vc in cm³/mol,
Energien in kJ/mol, Cp in J/(mol·K), η in Pa·s):
  Tb = 198,2 + ΣTb                    Tm = 122,5 + ΣTm
  Tc = Tb / (0,584 + 0,965 ΣTc − (ΣTc)²)
  Pc = (0,113 + 0,0032 Na − ΣPc)⁻²    (Na = Zahl aller Atome einschliesslich H)
  Vc = 17,5 + ΣVc
  ΔfH°(g, 298 K) = 68,29 + ΣH         ΔfG°(g, 298 K) = 53,88 + ΣG
  Cp°(g) = (Σa − 37,93) + (Σb + 0,210) T + (Σc − 3,91·10⁻⁴) T² + (Σd + 2,06·10⁻⁷) T³   (273–1000 K)
  ΔHvap(Tb) = 15,30 + ΣHvap           ΔHfus = −0,88 + ΣHfus
  η(l) = M · exp((Σηa − 597,82)/T + Σηb − 11,202)   (M in g/mol; Tm < T < 0,7 Tc)
Amide werden mangels eigener Gruppe als >C=O + −NH2/>NH/>N− zerlegt (vermerkt).
"""
from __future__ import annotations

import math

from .molgraph import HALOGENS, Mol, aromatic_atom, terminal_O

NA = None
# Gruppe: Tc, Pc, Vc, Tb, Tm, H, G, a, b, c, d, Hfus, Hvap, ηa, ηb   (None = „n. a.“ in der Tabelle)
TABLE = {
    "-CH3": (0.0141, -0.0012, 65, 23.58, -5.10, -76.45, -43.96, 1.95e1, -8.08e-3, 1.53e-4, -9.67e-8, 0.908, 2.373, 548.29, -1.719),
    "-CH2-": (0.0189, 0.0000, 56, 22.88, 11.27, -20.64, 8.42, -9.09e-1, 9.50e-2, -5.44e-5, 1.19e-8, 2.590, 2.226, 94.16, -0.199),
    ">CH-": (0.0164, 0.0020, 41, 21.74, 12.64, 29.89, 58.36, -2.30e1, 2.04e-1, -2.65e-4, 1.20e-7, 0.749, 1.691, -322.15, 1.187),
    ">C<": (0.0067, 0.0043, 27, 18.25, 46.43, 82.23, 116.02, -6.62e1, 4.27e-1, -6.41e-4, 3.01e-7, -1.460, 0.636, -573.56, 2.307),
    "=CH2": (0.0113, -0.0028, 56, 18.18, -4.32, -9.630, 3.77, 2.36e1, -3.81e-2, 1.72e-4, -1.03e-7, -0.473, 1.724, 495.01, -1.539),
    "=CH-": (0.0129, -0.0006, 46, 24.96, 8.73, 37.97, 48.53, -8.00, 1.05e-1, -9.63e-5, 3.56e-8, 2.691, 2.205, 82.28, -0.242),
    "=C<": (0.0117, 0.0011, 38, 24.14, 11.14, 83.99, 92.36, -2.81e1, 2.08e-1, -3.06e-4, 1.46e-7, 3.063, 2.138, NA, NA),
    "=C=": (0.0026, 0.0028, 36, 26.15, 17.78, 142.14, 136.70, 2.74e1, -5.57e-2, 1.01e-4, -5.02e-8, 4.720, 2.661, NA, NA),
    "≡CH": (0.0027, -0.0008, 46, 9.20, -11.18, 79.30, 77.71, 2.45e1, -2.71e-2, 1.11e-4, -6.78e-8, 2.322, 1.155, NA, NA),
    "≡C-": (0.0020, 0.0016, 37, 27.38, 64.32, 115.51, 109.82, 7.87, 2.01e-2, -8.33e-6, 1.39e-9, 4.151, 3.302, NA, NA),
    "ring -CH2-": (0.0100, 0.0025, 48, 27.15, 7.75, -26.80, -3.68, -6.03, 8.54e-2, -8.00e-6, -1.80e-8, 0.490, 2.398, 307.53, -0.798),
    "ring >CH-": (0.0122, 0.0004, 38, 21.78, 19.88, 8.67, 40.99, -2.05e1, 1.62e-1, -1.60e-4, 6.24e-8, 3.243, 1.942, -394.29, 1.251),
    "ring >C<": (0.0042, 0.0061, 27, 21.32, 60.15, 79.72, 87.88, -9.09e1, 5.57e-1, -9.00e-4, 4.69e-7, -1.373, 0.644, NA, NA),
    "ring =CH-": (0.0082, 0.0011, 41, 26.73, 8.13, 2.09, 11.30, -2.14, 5.74e-2, -1.64e-6, -1.59e-8, 1.101, 2.544, 259.65, -0.702),
    "ring =C<": (0.0143, 0.0008, 32, 31.01, 37.02, 46.43, 54.05, -8.25, 1.01e-1, -1.42e-4, 6.78e-8, 2.394, 3.059, -245.74, 0.912),
    "-F": (0.0111, -0.0057, 27, -0.03, -15.78, -251.92, -247.19, 2.65e1, -9.13e-2, 1.91e-4, -1.03e-7, 1.398, -0.670, NA, NA),
    "-Cl": (0.0105, -0.0049, 58, 38.13, 13.55, -71.55, -64.31, 3.33e1, -9.63e-2, 1.87e-4, -9.96e-8, 2.515, 4.532, 625.45, -1.814),
    "-Br": (0.0133, 0.0057, 71, 66.86, 43.43, -29.48, -38.06, 2.86e1, -6.49e-2, 1.36e-4, -7.45e-8, 3.603, 6.582, 738.91, -2.038),
    "-I": (0.0068, -0.0034, 97, 93.84, 41.69, 21.06, 5.74, 3.21e1, -6.41e-2, 1.26e-4, -6.87e-8, 2.724, 9.520, 809.55, -2.224),
    "-OH (Alkohol)": (0.0741, 0.0112, 28, 92.88, 44.45, -208.04, -189.20, 2.57e1, -6.91e-2, 1.77e-4, -9.88e-8, 2.406, 16.826, 2173.72, -5.057),
    "-OH (Phenol)": (0.0240, 0.0184, -25, 76.34, 82.83, -221.65, -197.37, -2.81, 1.11e-1, -1.16e-4, 4.94e-8, 4.490, 12.499, 3018.17, -7.314),
    "-O-": (0.0168, 0.0015, 18, 22.42, 22.23, -132.22, -105.00, 2.55e1, -6.32e-2, 1.11e-4, -5.48e-8, 1.188, 2.410, 122.09, -0.386),
    "ring -O-": (0.0098, 0.0048, 13, 31.22, 23.05, -138.16, -98.22, 1.22e1, -1.26e-2, 6.03e-5, -3.86e-8, 5.879, 4.682, 440.24, -0.953),
    ">C=O": (0.0380, 0.0031, 62, 76.75, 61.20, -133.22, -120.50, 6.45, 6.70e-2, -3.57e-5, 2.86e-9, 4.189, 8.972, 340.35, -0.350),
    "ring >C=O": (0.0284, 0.0028, 55, 94.97, 75.97, -164.50, -126.27, 3.04e1, -8.29e-2, 2.36e-4, -1.31e-7, 0.0, 6.645, NA, NA),
    "O=CH- (Aldehyd)": (0.0379, 0.0030, 82, 72.24, 36.90, -162.03, -143.48, 3.09e1, -3.36e-2, 1.60e-4, -9.88e-8, 3.197, 9.093, 740.92, -1.713),
    "-COOH": (0.0791, 0.0077, 89, 169.09, 155.50, -426.72, -387.87, 2.41e1, 4.27e-2, 8.04e-5, -6.87e-8, 11.051, 19.537, 1317.23, -2.578),
    "-COO- (Ester)": (0.0481, 0.0005, 82, 81.10, 53.60, -337.92, -301.95, 2.45e1, 4.02e-2, 4.02e-5, -4.52e-8, 6.959, 9.633, 483.88, -0.966),
    "=O (sonstige)": (0.0143, 0.0101, 36, -10.50, 2.08, -247.61, -250.83, 6.82, 1.96e-2, 1.27e-5, -1.78e-8, 3.624, 5.909, 675.24, -1.340),
    "-NH2": (0.0243, 0.0109, 38, 73.23, 66.89, -22.02, 14.07, 2.69e1, -4.12e-2, 1.64e-4, -9.76e-8, 3.515, 10.788, NA, NA),
    ">NH": (0.0295, 0.0077, 35, 50.17, 52.66, 53.47, 89.39, -1.21, 7.62e-2, -4.86e-5, 1.05e-8, 5.099, 6.436, NA, NA),
    "ring >NH": (0.0130, 0.0114, 29, 52.82, 101.51, 31.65, 75.61, 1.18e1, -2.30e-2, 1.07e-4, -6.28e-8, 7.490, 6.930, NA, NA),
    ">N-": (0.0169, 0.0074, 9, 11.74, 48.84, 123.34, 163.16, -3.11e1, 2.27e-1, -3.20e-4, 1.46e-7, 4.703, 1.896, NA, NA),
    "-N=": (0.0255, -0.0099, NA, 74.60, NA, 23.61, NA, NA, NA, NA, NA, NA, 3.335, NA, NA),
    "ring -N=": (0.0085, 0.0076, 34, 57.55, 68.40, 55.52, 79.93, 8.83, -3.84e-3, 4.35e-5, -2.60e-8, 3.649, 6.528, NA, NA),
    "=NH": (NA, NA, NA, 83.08, 68.91, 93.70, 119.66, 5.69, -4.12e-3, 1.28e-4, -8.88e-8, NA, 12.169, NA, NA),
    "-CN": (0.0496, -0.0101, 91, 125.66, 59.89, 88.43, 89.22, 3.65e1, -7.33e-2, 1.84e-4, -1.03e-7, 2.414, 12.851, NA, NA),
    "-NO2": (0.0437, 0.0064, 91, 152.54, 127.24, -66.57, -16.83, 2.59e1, -3.74e-3, 1.29e-4, -8.88e-8, 9.679, 16.738, NA, NA),
    "-SH": (0.0031, 0.0084, 63, 63.56, 20.09, -17.33, -22.99, 3.53e1, -7.58e-2, 1.85e-4, -1.03e-7, 2.360, 6.884, NA, NA),
    "-S-": (0.0119, 0.0049, 54, 68.78, 34.40, 41.87, 33.12, 1.96e1, -5.61e-3, 4.02e-5, -2.76e-8, 4.130, 6.817, NA, NA),
    "ring -S-": (0.0019, 0.0051, 38, 52.10, 79.93, 39.10, 27.76, 1.67e1, 4.81e-3, 2.77e-5, -2.11e-8, 1.557, 5.984, NA, NA),
}
COLS = ("Tc", "Pc", "Vc", "Tb", "Tm", "H", "G", "a", "b", "c", "d", "Hfus", "Hvap", "ea", "eb")
REFS = ["joback1987", "joback_wiki"]


class JobackError(ValueError):
    pass


def assign(m: Mol) -> tuple[dict, list[str]]:
    """Gruppenzählung {Gruppe: n} und Hinweise. JobackError, wenn ein Atom in keine Gruppe passt."""
    groups, notes, used = {}, [], set()

    def add(g, *atoms):
        groups[g] = groups.get(g, 0) + 1
        used.update(atoms)
    if any(m.q) and not _nitro_only_charges(m):
        raise JobackError("geladene Teilchen sind im Joback-Verfahren nicht vorgesehen")
    amide = False
    for c in range(m.n()):
        if m.el[c] != "C" or c in used:
            continue
        ring = m.ring_atom[c]
        dO = terminal_O(m, c, 2)
        if dO:
            o2 = dO[0]
            sO = [j for j, o in m.nbrs(c) if m.el[j] == "O" and o == 1]
            nN = [j for j, o in m.nbrs(c) if m.el[j] == "N" and o == 1]
            if sO and m.h[sO[0]] == 1 and m.deg(sO[0]) == 1 and len(sO) == 1 and not ring:
                add("-COOH", c, o2, sO[0])
            elif len(sO) == 1 and m.deg(sO[0]) == 2 and not ring and not m.ring_atom[sO[0]] and not nN:
                add("-COO- (Ester)", c, o2, sO[0])
            elif m.h[c] == 1 and not sO and not nN and not ring:
                add("O=CH- (Aldehyd)", c, o2)
            elif m.h[c] == 0 and not sO:
                add("ring >C=O" if ring else ">C=O", c, o2)
                if nN:
                    amide = True
            else:
                raise JobackError("Carbonylgruppe dieser Art (z. B. Formaldehyd, Carbonat, Lacton) ist nicht vorgesehen")
            continue
        nit = [j for j, o in m.nbrs(c) if m.el[j] == "N" and o == 3 and m.deg(j) == 1]
        if nit:
            add("-CN", c, nit[0])
            continue
        orders = [o for _, o in m.nbrs(c)]
        h = m.h[c]
        arom = aromatic_atom(m, c)
        n2 = sum(1 for o in orders if o == 2)
        if any(o == 3 for o in orders):
            g = "≡CH" if h == 1 else "≡C-"
        elif n2 >= 2:
            g = "=C="
        elif n2 == 1 or arom:
            if ring:
                g = {1: "ring =CH-", 0: "ring =C<"}.get(h)
            else:
                g = {2: "=CH2", 1: "=CH-", 0: "=C<"}.get(h)
        else:
            if ring:
                g = {2: "ring -CH2-", 1: "ring >CH-", 0: "ring >C<"}.get(h)
            else:
                g = {3: "-CH3", 2: "-CH2-", 1: ">CH-", 0: ">C<"}.get(h)
        if g is None:
            raise JobackError("Kohlenstoffatom ohne passende Gruppe (z. B. Methan, CH4)")
        add(g, c)
    for a in range(m.n()):
        if a in used:
            continue
        e, h, nb = m.el[a], m.h[a], m.nbrs(a)
        ring = m.ring_atom[a]
        if e in HALOGENS:
            if len(nb) != 1:
                raise JobackError("Halogen ohne genau eine Bindung")
            add("-" + e, a)
        elif e == "O":
            if len(nb) == 1 and h == 1:
                add("-OH (Phenol)" if aromatic_atom(m, nb[0][0]) else "-OH (Alkohol)", a)
            elif len(nb) == 2 and all(o == 1 for _, o in nb):
                add("ring -O-" if ring else "-O-", a)
            elif len(nb) == 1 and nb[0][1] == 2:
                add("=O (sonstige)", a)
            elif m.aro[a] and ring:
                add("ring -O-", a)
            else:
                raise JobackError("Sauerstoffatom ohne passende Gruppe")
        elif e == "N":
            oo = [j for j, _ in nb if m.el[j] == "O" and m.deg(j) == 1]
            if len(oo) == 2 and len(nb) == 3:
                add("-NO2", a, *oo)
            elif m.aro[a] and ring:
                add("ring >NH" if h == 1 else "ring -N=", a)
            elif any(o == 2 for _, o in nb):
                if h == 1:
                    add("=NH", a)
                else:
                    add("ring -N=" if ring else "-N=", a)
            elif h == 2 and len(nb) == 1:
                add("-NH2", a)
            elif h == 1 and len(nb) == 2:
                add("ring >NH" if ring else ">NH", a)
            elif h == 0 and len(nb) == 3 and not ring:
                add(">N-", a)
            else:
                raise JobackError("Stickstoffatom ohne passende Gruppe (z. B. Ring-N mit drei Bindungen, Ammoniak)")
        elif e == "S":
            if h == 1 and len(nb) == 1:
                add("-SH", a)
            elif len(nb) == 2 and all(o in (1, 1.5) for _, o in nb):
                add("ring -S-" if ring else "-S-", a)
            else:
                raise JobackError("Schwefel in dieser Bindungsform (z. B. Sulfon) ist nicht vorgesehen")
        else:
            raise JobackError(f"Element {e} ist im Joback-Verfahren nicht vorgesehen")
    if amide:
        notes.append("Amid als >C=O plus Stickstoffgruppe gezählt (keine eigene Amidgruppe im Verfahren)")
    return groups, notes


def _nitro_only_charges(m: Mol) -> bool:
    """Nitrogruppe als [N+](=O)[O-] ist neutral im Ganzen und erlaubt."""
    for a in range(m.n()):
        if not m.q[a]:
            continue
        if m.el[a] == "N" and m.q[a] == 1 and sum(1 for j, _ in m.nbrs(a) if m.el[j] == "O") == 2:
            continue
        if m.el[a] == "O" and m.q[a] == -1 and any(m.el[j] == "N" and m.q[j] == 1 for j, _ in m.nbrs(a)):
            continue
        return False
    return True


def _sum(groups: dict, col: str):
    i = COLS.index(col)
    s = 0.0
    for g, n in groups.items():
        v = TABLE[g][i]
        if v is None:
            return None
        s += n * v
    return s


def cp(groups: dict, T: float) -> float | None:
    a, b, c, d = (_sum(groups, k) for k in "abcd")
    if None in (a, b, c, d):
        return None
    return (a - 37.93) + (b + 0.210) * T + (c - 3.91e-4) * T ** 2 + (d + 2.06e-7) * T ** 3


def estimate(m: Mol, M: float | None = None) -> dict:
    """Alle Joback-Grössen mit Einheit; fehlende Gruppenwerte ergeben None mit Hinweis."""
    groups, notes = assign(m)
    na = sum(1 for _ in m.el) + sum(m.h)
    out = {"groups": [{"group": g, "n": n} for g, n in sorted(groups.items())], "notes": notes, "refs": REFS,
           "method": "Joback & Reid 1987 (Gruppenbeiträge)", "values": {}}
    v = out["values"]

    def put(k, val, unit, label, note=""):
        v[k] = {"v": val, "u": unit, "label": label, "note": note}
    sTb, sTm, sTc, sPc, sVc = (_sum(groups, k) for k in ("Tb", "Tm", "Tc", "Pc", "Vc"))
    Tb = 198.2 + sTb if sTb is not None else None
    put("Tb", Tb, "K", "Siedepunkt Tb (1 atm)")
    put("Tm", 122.5 + sTm if sTm is not None else None, "K", "Schmelzpunkt Tm", "Schmelzpunkte schätzt das Verfahren nur grob")
    Tc = None
    if Tb is not None and sTc is not None:
        den = 0.584 + 0.965 * sTc - sTc ** 2
        Tc = Tb / den if den > 0 else None
    put("Tc", Tc, "K", "kritische Temperatur Tc", "aus dem geschätzten Tb")
    put("Pc", (0.113 + 0.0032 * na - sPc) ** -2 if sPc is not None else None, "bar", "kritischer Druck Pc")
    put("Vc", 17.5 + sVc if sVc is not None else None, "cm³/mol", "kritisches Volumen Vc")
    sH, sG = _sum(groups, "H"), _sum(groups, "G")
    put("dfH_g", 68.29 + sH if sH is not None else None, "kJ/mol", "ΔfH°(g, 298 K)")
    put("dfG_g", 53.88 + sG if sG is not None else None, "kJ/mol", "ΔfG°(g, 298 K)")
    put("Cp_g", cp(groups, 298.15), "J/(mol·K)", "Cp°(g, 298 K)", "Polynom gültig 273–1000 K")
    sHv, sHf = _sum(groups, "Hvap"), _sum(groups, "Hfus")
    put("Hvap", 15.30 + sHv if sHv is not None else None, "kJ/mol", "Verdampfungsenthalpie bei Tb")
    put("Hfus", -0.88 + sHf if sHf is not None else None, "kJ/mol", "Schmelzenthalpie")
    sea, seb = _sum(groups, "ea"), _sum(groups, "eb")
    eta = None
    note = "nur für Tm < T < 0,7 Tc"
    if M and sea is not None and seb is not None:
        T = 298.15
        tm = v["Tm"]["v"]
        if (tm is None or tm < T) and (Tc is None or T < 0.7 * Tc):
            eta = M * math.exp((sea - 597.82) / T + seb - 11.202)
        else:
            note = "298 K liegt ausserhalb von Tm < T < 0,7 Tc"
    put("eta_l", eta, "Pa·s", "Viskosität der Flüssigkeit bei 298 K", note)
    a, b, c, d = (_sum(groups, k) for k in "abcd")
    if None not in (a, b, c, d):
        out["cp_poly"] = {"A": a - 37.93, "B": b + 0.210, "C": c - 3.91e-4, "D": d + 2.06e-7, "Tmin": 273, "Tmax": 1000}
    return out
