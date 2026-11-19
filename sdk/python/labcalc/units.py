"""Einheiten, Groessenarten und Naturkonstanten.

Intern wird alles in SI-Basiseinheiten gerechnet. Eine Dimension ist ein Tupel der Exponenten von
(m, kg, s, A, K, mol, cd).
"""
from __future__ import annotations

import math
import re

BASE = ("m", "kg", "s", "A", "K", "mol", "cd")
D0 = (0.0,) * 7


class UnitError(ValueError):
    pass


def dmul(a, b):
    return tuple(x + y for x, y in zip(a, b))


def ddiv(a, b):
    return tuple(x - y for x, y in zip(a, b))


def dpow(a, n):
    return tuple(x * n for x in a)


def deq(a, b):
    return all(abs(x - y) < 1e-9 for x, y in zip(a, b))


def _d(**kw):
    return tuple(float(kw.get(k, 0)) for k in ("m", "kg", "s", "A", "K", "mol", "cd"))


# Symbol -> (Faktor nach SI, Dimension, Nullpunktverschiebung, Vorsaetze erlaubt)
_U = {}


def _add(sym, factor, dims, prefix=True, offset=0.0):
    _U[sym] = (factor, dims, offset, prefix)


L, M, T, I, K, N, J = _d(m=1), _d(kg=1), _d(s=1), _d(A=1), _d(K=1), _d(mol=1), _d(cd=1)
_add("m", 1, L)
_add("g", 1e-3, M)
_add("s", 1, T)
_add("A", 1, I)
_add("K", 1, K)
_add("mol", 1, N)
_add("cd", 1, J)
FORCE = _d(kg=1, m=1, s=-2)
PRESS = _d(kg=1, m=-1, s=-2)
ENERGY = _d(kg=1, m=2, s=-2)
POWER = _d(kg=1, m=2, s=-3)
VOLT = _d(kg=1, m=2, s=-3, A=-1)
_add("N", 1, FORCE)
_add("Pa", 1, PRESS)
_add("bar", 1e5, PRESS)
_add("atm", 101325, PRESS, False)
_add("psi", 6894.757293168, PRESS, False)
_add("mmHg", 133.322387415, PRESS, False)
_add("J", 1, ENERGY)
_add("Wh", 3600, ENERGY)
_add("cal", 4.184, ENERGY)
_add("eV", 1.602176634e-19, ENERGY)               # = e·1 V, exakt (SI 2019)
_add("W", 1, POWER)
_add("Hz", 1, _d(s=-1))
_add("C", 1, _d(A=1, s=1))
_add("Ah", 3600, _d(A=1, s=1))
_add("V", 1, VOLT)
_add("Ohm", 1, _d(kg=1, m=2, s=-3, A=-2))
_add("S", 1, _d(kg=-1, m=-2, s=3, A=2))
_add("F", 1, _d(kg=-1, m=-2, s=4, A=2))
_add("H", 1, _d(kg=1, m=2, s=-2, A=-2))
_add("T", 1, _d(kg=1, s=-2, A=-1))
_add("Wb", 1, _d(kg=1, m=2, s=-2, A=-1))
_add("L", 1e-3, _d(m=3))
_add("l", 1e-3, _d(m=3))
_add("t", 1000, M)
_add("M", 1000, _d(mol=1, m=-3))                 # molar, mol/L
_add("min", 60, T, False)
_add("h", 3600, T, False)
_add("d", 86400, T, False)
_add("a", 365.25 * 86400, T, False)
_add("rad", 1, D0, False)
_add("sr", 1, D0, False)
_add("deg", math.pi / 180, D0, False)
_add("°", math.pi / 180, D0, False)
_add("rpm", 1 / 60, _d(s=-1), False)
_add("%", 0.01, D0, False)
_add("‰", 0.001, D0, False)
_add("ppm", 1e-6, D0, False)
_add("Å", 1e-10, L, False)
_add("in", 0.0254, L, False)
_add("ft", 0.3048, L, False)
_add("lb", 0.45359237, M, False)
_add("lbf", 4.4482216152605, FORCE, False)
_add("°C", 1, K, False, 273.15)
_add("°F", 5 / 9, K, False, 459.67 * 5 / 9)
_add("Nm", 1, ENERGY)                             # Newtonmeter (Moment)
_add("u", 1.66053906892e-27, M, False)            # atomare Masseneinheit, CODATA 2022 (Vorsatz "u" ist µ)
_add("Da", 1.66053906892e-27, M)                  # Dalton = u
_add("Bq", 1, _d(s=-1))                           # Becquerel (Aktivität)
_add("Ci", 3.7e10, _d(s=-1))                      # Curie, festgelegt 3,7·10¹⁰ Bq
# U-01: Messgrössen aus Labor, Wasser- und Umweltanalytik
_add("pH", 1, D0, False)                          # pH-Wert; "pH" ist damit nicht mehr Pikohenry (dafür 1e-12 H)
_add("ppb", 1e-9, D0, False)                      # ("ppt" bewusst nicht: Tausendstel oder Billionstel?)
_add("Torr", 101325 / 760, PRESS)                 # auch mTorr
_add("lx", 1, _d(cd=1, m=-2))                     # Lux = lm/m² (sr dimensionslos)
_add("lm", 1, J)                                  # Lumen = cd·sr
_add("%RH", 0.01, D0, False)                      # relative Feuchte
_add("%rH", 0.01, D0, False)
_add("%rF", 0.01, D0, False)
_add("NTU", 1, D0, False)                         # Trübung (nephelometrisch)
_add("FNU", 1, D0, False)                         # Trübung nach ISO 7027 (Formazin, 90°)
_add("FAU", 1, D0, False)                         # Trübung, Formazin-Schwächung
_add("dB", 1, D0, False)                          # Pegel (logarithmisch)
_add("AU", 1, D0)                                 # Absorbanz (auch mAU)
_add("P", 0.1, _d(kg=1, m=-1, s=-1))              # Poise (cP = mPa·s)
_add("St", 1e-4, _d(m=2, s=-1))                   # Stokes (cSt = mm²/s)
_add("sccm", 1e-6 / 60, _d(m=3, s=-1), False)     # cm³/min im Normzustand (als Volumenstrom, ohne Zustandsumrechnung)
_add("slm", 1e-3 / 60, _d(m=3, s=-1), False)      # L/min im Normzustand
_add("Gy", 1, _d(m=2, s=-2))                      # Gray (Energiedosis, J/kg)
_add("Sv", 1, _d(m=2, s=-2))                      # Sievert (Äquivalentdosis, J/kg)
_add("kat", 1, _d(mol=1, s=-1))                   # Katal (katalytische Aktivität)
# Wasserhärte als Stoffmenge Erdalkali-Ionen; molare Massen aus den konventionellen Standard-Atomgewichten (IUPAC/CIAAW:
# Ca 40,078; C 12,011; O 15,999 g/mol).
M_CAO = 40.078 + 15.999                            # g/mol
M_CACO3 = 40.078 + 12.011 + 3 * 15.999             # g/mol
_add("°dH", 10.0 / M_CAO, _d(mol=1, m=-3), False)    # deutsche Härte: 1 °dH = 10 mg CaO/L = 0,178326 mmol/L
_add("°fH", 10.0 / M_CACO3, _d(mol=1, m=-3), False)  # französische Härte: 1 °fH = 10 mg CaCO₃/L = 0,099914 mmol/L
#                                                    (oft auf 0,1 mmol/L gerundet; Unterschied 0,09 %)
_add("CFU", 1, D0, False)                         # koloniebildende Einheiten (Anzahl), z. B. CFU/mL
_add("KBE", 1, D0, False)                         # dasselbe deutsch
# Skalen, die sich nicht in andere dimensionslose Einheiten umrechnen lassen (pH → % wäre Unsinn); siehe compatible()
_SCALE = {"pH", "dB", "NTU", "FNU", "FAU", "AU"}

PREFIX = {"Y": 1e24, "Z": 1e21, "E": 1e18, "P": 1e15, "T": 1e12, "G": 1e9, "M": 1e6, "k": 1e3, "h": 1e2,
          "da": 1e1, "d": 1e-1, "c": 1e-2, "m": 1e-3, "µ": 1e-6, "u": 1e-6, "n": 1e-9, "p": 1e-12, "f": 1e-15,
          "a": 1e-18}

_SUP = {"²": "^2", "³": "^3", "⁴": "^4", "⁻¹": "^-1", "⁻²": "^-2", "⁻³": "^-3", "⁻⁴": "^-4", "¹": "^1"}


def _normalize(s: str) -> str:
    s = str(s).strip()
    for a, b in (("μ", "µ"), ("Ω", "Ohm"), ("·", "*"), ("⋅", "*"), ("×", "*"), ("U/min", "rpm")):
        s = s.replace(a, b)
    for a, b in _SUP.items():
        s = s.replace(a, b)
    s = re.sub(r"(?<=[\w)])\s*√", "*√", s)
    s = re.sub(r"√\(([^)]*)\)", r"(\1)^0.5", s)
    s = re.sub(r"√([A-Za-zµ]+)", r"\1^0.5", s)
    s = re.sub(r"\s+", "*", s)
    return s


_TOK = re.compile(r"\s*(\(|\)|\*|/|\^|[-+]?\d+(?:\.\d+)?|[A-Za-zµ°%‰Å_]+)")
_CACHE: dict = {}


def _atom(sym: str):
    if sym in _U:
        f, d, off, _ = _U[sym]
        return f, d, off
    for pl in (2, 1):
        p, rest = sym[:pl], sym[pl:]
        if p in PREFIX and rest in _U and _U[rest][3]:
            f, d, off, _ = _U[rest]
            return f * PREFIX[p], d, 0.0
    raise UnitError(f"Unbekannte Einheit „{sym}“")


def parse_unit(s: str):
    """Einheitentext -> (Faktor, Dimension, Nullpunkt). Leerer Text oder "1" ist dimensionslos."""
    key = str(s)
    if key in _CACHE:
        return _CACHE[key]
    src = _normalize(key)
    if src in ("", "1", "-"):
        _CACHE[key] = (1.0, D0, 0.0)
        return _CACHE[key]
    toks, pos = [], 0
    while pos < len(src):
        m = _TOK.match(src, pos)
        if not m or m.end() == pos:
            raise UnitError(f"Einheit „{s}“ nicht lesbar")
        toks.append(m.group(1))
        pos = m.end()
    i = 0

    def peek():
        return toks[i] if i < len(toks) else None

    def expr():
        nonlocal i
        f, d, single = term()
        offset = single
        while peek() in ("*", "/"):
            op = toks[i]
            i += 1
            f2, d2, _ = term()
            f, d = (f * f2, dmul(d, d2)) if op == "*" else (f / f2, ddiv(d, d2))
            offset = None
        return f, d, offset

    def term():
        nonlocal i
        t = peek()
        if t is None:
            raise UnitError(f"Einheit „{s}“ unvollständig")
        single = None
        if t == "(":
            i += 1
            f, d, _ = expr()
            if peek() != ")":
                raise UnitError(f"Klammer in „{s}“ nicht geschlossen")
            i += 1
        elif re.fullmatch(r"[-+]?\d+(?:\.\d+)?", t):
            i += 1
            f, d = float(t), D0
        else:
            i += 1
            f, d, off = _atom(t)
            single = off
        if peek() == "^" or (peek() is not None and re.fullmatch(r"[-+]?\d+(?:\.\d+)?", peek()) and t not in ("(",)
                             and not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", t)):
            if peek() == "^":
                i += 1
            n = peek()
            if n is None or not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", n):
                raise UnitError(f"Exponent in „{s}“ fehlt")
            i += 1
            f, d = f ** float(n), dpow(d, float(n))
            single = None
        return f, d, single

    f, d, off = expr()
    if i != len(toks):
        raise UnitError(f"Einheit „{s}“ nicht lesbar")
    res = (f, d, off or 0.0)
    _CACHE[key] = res
    return res


def scale_of(unit) -> str | None:
    """U-01: Name der Skala (pH, dB, NTU, FNU, FAU, AU), wenn die Einheit eine solche ist (auch mAU), sonst None."""
    s = _normalize(str(unit or ""))
    if s in _SCALE:
        return s
    for pl in (2, 1):
        if s[:pl] in PREFIX and s[pl:] in _SCALE and _U[s[pl:]][3]:
            return s[pl:]
    return None


def compatible(a, b) -> bool:
    """Lässt sich ein Wert in Einheit a in Einheit b umrechnen? Gleiche Dimension und dieselbe Skala (pH nur in pH)."""
    try:
        da, db = parse_unit(a or "")[1], parse_unit(b or "")[1]
    except UnitError:
        return False
    return deq(da, db) and scale_of(a) == scale_of(b)


def to_si(v: float, unit: str, diff: bool = False) -> float:
    f, _, off = parse_unit(unit)
    return v * f + (0.0 if diff else off)


def from_si(v, unit: str, diff: bool = False):
    f, _, off = parse_unit(unit)
    return (v - (0.0 if diff else off)) / f


_DELTA = re.compile(r"^\s*(?:Δ|Delta|delta)\s*")


def split_delta(unit: str):
    """Zieleinheit mit Differenz-Kennung: "Δ°C", "Delta °C", "delta °F" -> ("°C", True); sonst (Einheit, False).
    Eine Differenz wird ohne Nullpunktverschiebung umgerechnet (10 K -> 10 °C)."""
    s = str(unit or "")
    m = _DELTA.match(s)
    if m and s[m.end():].strip():
        return s[m.end():].strip(), True
    return s.strip(), False


_NAMED = [("N", FORCE), ("Pa", PRESS), ("J", ENERGY), ("W", POWER), ("V", VOLT), ("C", _d(A=1, s=1)),
          ("Ω", _d(kg=1, m=2, s=-3, A=-2)), ("F", _d(kg=-1, m=-2, s=4, A=2)), ("H", _d(kg=1, m=2, s=-2, A=-2)),
          ("T", _d(kg=1, s=-2, A=-1)), ("Hz", _d(s=-1))]
_SUPCH = str.maketrans("0123456789-.", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻·")


def dims_text(d) -> str:
    """Dimension als SI-Einheit, z. B. (1,0,-1,...) -> m/s, Kraft -> N."""
    if d is None:
        return "?"
    if deq(d, D0):
        return ""
    for name, nd in _NAMED:
        if deq(d, nd):
            return name
    num, den = [], []
    for sym, e in zip(BASE, d):
        if abs(e) < 1e-9:
            continue
        ex = abs(e)
        es = "" if abs(ex - 1) < 1e-9 else (f"{ex:g}".translate(_SUPCH) if ex == int(ex) else f"^{ex:g}")
        (num if e > 0 else den).append(sym + es)
    s = "·".join(num) or "1"
    if den:
        s += "/" + ("·".join(den) if len(den) == 1 else "(" + "·".join(den) + ")")
    return s


# ----------------------------------------------------------------------------- Groessenarten
class Kind:
    __slots__ = ("key", "de", "en", "si", "dims", "units", "sym", "pos", "diff")

    def __init__(self, key, de, en, si, units, sym, pos=True, diff=False):
        self.key, self.de, self.en, self.si = key, de, en, si
        self.dims = parse_unit(si)[1]
        self.units = units
        self.sym, self.pos, self.diff = sym, pos, diff
        for u in units:
            if not deq(parse_unit(u)[1], self.dims):
                raise ValueError(f"{key}: Einheit {u} passt nicht")

    def to_dict(self):
        return {"key": self.key, "de": self.de, "en": self.en, "si": self.si, "units": self.units, "sym": self.sym,
                "pos": self.pos, "diff": self.diff, "dims": dims_text(self.dims)}


_K = [
    # Geometrie und Kinematik
    ("length", "Länge", "Length", "m", ["m", "mm", "cm", "km", "µm", "nm"], "L"),
    ("area", "Fläche", "Area", "m^2", ["m^2", "mm^2", "cm^2", "km^2"], "A"),
    ("volume", "Volumen", "Volume", "m^3", ["m^3", "L", "mL", "cm^3", "mm^3"], "V"),
    ("angle", "Winkel", "Angle", "rad", ["°", "rad"], "alpha", False),
    ("time", "Zeit", "Time", "s", ["s", "ms", "µs", "min", "h", "d"], "t"),
    ("frequency", "Frequenz", "Frequency", "Hz", ["Hz", "kHz", "MHz", "GHz", "rpm"], "f"),
    ("velocity", "Geschwindigkeit", "Velocity", "m/s", ["m/s", "km/h", "mm/s", "cm/s"], "v", False),
    ("acceleration", "Beschleunigung", "Acceleration", "m/s^2", ["m/s^2", "mm/s^2"], "a", False),
    ("ang_velocity", "Winkelgeschwindigkeit", "Angular velocity", "rad/s", ["rad/s", "°/s"], "omega", False),
    ("ang_accel", "Winkelbeschleunigung", "Angular acceleration", "rad/s^2", ["rad/s^2"], "alpha_w", False),
    # Mechanik
    ("mass", "Masse", "Mass", "kg", ["kg", "g", "mg", "t"], "m"),
    ("density", "Dichte", "Density", "kg/m^3", ["kg/m^3", "g/cm^3", "g/L"], "rho"),
    ("force", "Kraft", "Force", "N", ["N", "kN", "MN", "mN"], "F", False),
    ("pressure", "Druck", "Pressure", "Pa", ["Pa", "kPa", "MPa", "bar", "mbar", "hPa", "atm", "Torr", "mTorr"], "p", False),
    ("stress", "Spannung (mech.)", "Stress", "Pa", ["MPa", "N/mm^2", "Pa", "kPa", "GPa"], "sigma", False),
    ("modulus", "Elastizitätsmodul", "Elastic modulus", "Pa", ["GPa", "MPa", "N/mm^2", "Pa"], "E"),
    ("strain", "Dehnung", "Strain", "1", ["%", "1", "‰"], "epsilon", False),
    ("number", "Zahl (dimensionslos)", "Number (dimensionless)", "1", ["1", "%"], "x", False),
    ("energy", "Energie, Arbeit", "Energy, work", "J", ["J", "kJ", "MJ", "Wh", "kWh", "eV", "kcal"], "E", False),
    ("power", "Leistung", "Power", "W", ["W", "kW", "MW", "mW"], "P", False),
    ("momentum", "Impuls", "Momentum", "kg*m/s", ["kg*m/s", "N*s"], "p", False),
    ("torque", "Moment", "Moment, torque", "N*m", ["N*m", "kN*m", "N*mm"], "M", False),
    ("area_moment", "Flächenträgheitsmoment", "Second moment of area", "m^4", ["mm^4", "cm^4", "m^4"], "I"),
    ("section_mod", "Widerstandsmoment", "Section modulus", "m^3", ["mm^3", "cm^3", "m^3"], "W_b"),
    ("mass_moment", "Massenträgheitsmoment", "Moment of inertia", "kg*m^2", ["kg*m^2", "g*cm^2"], "J_m"),
    ("spring", "Federsteifigkeit", "Spring rate", "N/m", ["N/m", "N/mm", "kN/m"], "k"),
    ("stress_int", "Spannungsintensität", "Stress intensity", "Pa*m^0.5", ["MPa*m^0.5", "Pa*m^0.5"], "K_I"),
    ("surface_energy", "Oberflächenenergie", "Surface energy", "J/m^2", ["J/m^2", "N/m"], "gamma_s"),
    ("energy_density", "Energiedichte (Energie je Volumen)", "Energy density (energy per volume)", "J/m^3", ["J/m^3", "kJ/m^3", "MJ/m^3"], "u_V", False),
    # Waerme
    ("temperature", "Temperatur", "Temperature", "K", ["K", "°C", "°F"], "T"),
    ("temp_diff", "Temperaturdifferenz", "Temperature difference", "K", ["K"], "dT", False, True),
    ("spec_heat", "Spez. Wärmekapazität", "Specific heat capacity", "J/(kg*K)", ["J/(kg*K)", "kJ/(kg*K)"], "c"),
    ("spec_energy", "Spezifische Energie", "Specific energy", "J/kg", ["J/kg", "kJ/kg"], "q"),
    ("conductivity_th", "Wärmeleitfähigkeit", "Thermal conductivity", "W/(m*K)", ["W/(m*K)"], "lambda_w"),
    ("htc", "Wärmeübergangskoeffizient", "Heat transfer coefficient", "W/(m^2*K)", ["W/(m^2*K)"], "alpha_h"),
    ("expansion", "Ausdehnungskoeffizient", "Expansion coefficient", "1/K", ["1/K", "µm/(m*K)"], "alpha_T"),
    ("heat_flux", "Wärmestromdichte", "Heat flux", "W/m^2", ["W/m^2", "kW/m^2"], "q_A"),
    # Stoff und Chemie
    ("amount", "Stoffmenge", "Amount of substance", "mol", ["mol", "mmol", "µmol"], "n"),
    ("molar_mass", "Molare Masse", "Molar mass", "kg/mol", ["g/mol", "kg/mol"], "M"),
    ("concentration", "Stoffmengenkonzentration", "Molar concentration", "mol/m^3", ["mol/L", "mmol/L", "µmol/L", "mol/m^3"], "c"),
    ("mass_conc", "Massenkonzentration", "Mass concentration", "kg/m^3", ["g/L", "mg/L", "kg/m^3"], "beta"),
    ("molar_energy", "Molare Energie", "Molar energy", "J/mol", ["kJ/mol", "J/mol"], "E_a"),
    ("rate_const", "Geschwindigkeitskonstante", "Rate constant", "1/s", ["1/s", "1/min", "1/h", "1/d", "1/a"], "k_r"),
    ("rate_const0", "Geschwindigkeitskonstante 0. Ordnung", "Zero-order rate constant", "mol/(m^3*s)",
     ["mol/(L*s)", "mmol/(L*s)", "mol/(L*min)"], "k_0"),
    ("rate_const2", "Geschwindigkeitskonstante 2. Ordnung", "Second-order rate constant", "m^3/(mol*s)",
     ["L/(mol*s)", "L/(mol*min)", "m^3/(mol*s)"], "k_2"),
    ("molality", "Molalität", "Molality", "mol/kg", ["mol/kg", "mmol/kg"], "b_m"),
    ("reaction_energy", "Molare Reaktionsgrösse (ΔG, ΔH)", "Molar reaction quantity (ΔG, ΔH)", "J/mol", ["kJ/mol", "J/mol"], "dG", False),
    ("molar_entropy", "Molare Entropie, Wärmekapazität", "Molar entropy, heat capacity", "J/(mol*K)", ["J/(mol*K)", "kJ/(mol*K)"], "S_m", False),
    ("molar_volume", "Molares Volumen", "Molar volume", "m^3/mol", ["L/mol", "cm^3/mol", "m^3/mol"], "V_m"),
    ("vdw_a", "Van-der-Waals-Konstante a", "Van der Waals constant a", "Pa*m^6/mol^2", ["Pa*m^6/mol^2", "bar*L^2/mol^2"], "a_vdw"),
    ("cryo_const", "Kryo-/Ebullioskopische Konstante", "Cryoscopic/ebullioscopic constant", "K*kg/mol", ["K*kg/mol"], "K_f"),
    ("activity", "Aktivität (Zerfälle je Zeit)", "Activity", "1/s", ["Bq", "kBq", "MBq", "GBq", "Ci", "mCi"], "A_act"),
    ("spec_activity", "Spezifische Aktivität", "Specific activity", "1/(kg*s)", ["Bq/g", "Bq/kg", "GBq/g", "Ci/g"], "a_s"),
    ("molar_abs", "Molarer Absorptionskoeffizient", "Molar absorptivity", "m^2/mol", ["L/(mol*cm)", "m^2/mol"], "eps_m"),
    ("wavenumber", "Wellenzahl", "Wavenumber", "1/m", ["1/cm", "1/m"], "nu_t"),
    ("diffusivity", "Diffusionskoeffizient", "Diffusion coefficient", "m^2/s", ["m^2/s", "cm^2/s", "µm^2/s"], "D_c"),
    ("diff_flux", "Diffusionsstromdichte (Masse)", "Diffusion flux (mass)", "kg/(m^2*s)", ["kg/(m^2*s)", "g/(m^2*s)"], "J_d", False),
    ("penetration_rate", "Abtragsrate (Korrosion)", "Penetration rate (corrosion)", "m/s", ["mm/a", "µm/a", "m/s"], "v_corr"),
    ("spec_gas", "Spez. Gaskonstante", "Specific gas constant", "J/(kg*K)", ["J/(kg*K)"], "R_s"),
    # U-01: Messgrössen der Chemie, Wasser- und Umweltanalytik
    ("ph", "pH-Wert", "pH value", "1", ["pH"], "pH", False),
    ("fraction", "Anteil (Massen-, Volumen-, Stoffmengenanteil)", "Fraction (mass, volume, mole)", "1",
     ["%", "‰", "ppm", "ppb", "g/kg", "mg/kg", "1"], "w"),
    ("hardness", "Wasserhärte (Erdalkali-Ionen)", "Water hardness (alkaline earth ions)", "mol/m^3",
     ["mmol/L", "°dH", "°fH"], "c_H"),
    ("dissolved_o2", "Gelöster Sauerstoff", "Dissolved oxygen", "kg/m^3", ["mg/L", "µg/L"], "c_O2"),
    ("salinity", "Salinität", "Salinity", "1", ["‰", "g/kg"], "S_A"),
    ("turbidity", "Trübung", "Turbidity", "1", ["NTU", "FNU", "FAU"], "Tu"),
    ("absorbance", "Absorbanz (Extinktion)", "Absorbance", "1", ["AU", "mAU"], "A_bs", False),
    ("number_conc", "Anzahlkonzentration (z. B. Keimzahl)", "Number concentration (e.g. colony count)", "1/m^3",
     ["CFU/mL", "1/mL", "1/cm^3", "1/L"], "c_N"),
    ("cat_activity", "Katalytische Aktivität (Enzym)", "Catalytic activity (enzyme)", "kat", ["µkat", "nkat", "kat"], "z_cat"),
    ("activity_conc", "Aktivitätskonzentration", "Activity concentration", "Bq/m^3", ["Bq/L", "Bq/m^3", "kBq/m^3"], "c_A"),
    # Elektrik
    ("voltage", "Spannung (elektr.)", "Voltage", "V", ["V", "mV", "kV", "µV"], "U", False),
    ("current", "Stromstärke", "Current", "A", ["A", "mA", "µA", "kA"], "I", False),
    ("resistance", "Widerstand", "Resistance", "Ohm", ["Ohm", "kOhm", "MOhm", "mOhm"], "R"),
    ("resistivity", "Spez. Widerstand", "Resistivity", "Ohm*m", ["Ohm*mm^2/m", "Ohm*m", "µOhm*cm"], "rho_el"),
    ("charge", "Ladung", "Charge", "C", ["C", "mC", "µC", "Ah", "mAh"], "Q", False),
    ("capacitance", "Kapazität", "Capacitance", "F", ["F", "mF", "µF", "nF", "pF"], "C"),
    ("inductance", "Induktivität", "Inductance", "H", ["H", "mH", "µH"], "L_i"),
    ("temp_coeff", "Temperaturkoeffizient", "Temperature coefficient", "1/K", ["1/K"], "alpha_R", False),
    ("el_conductivity", "Elektrische Leitfähigkeit", "Electrical conductivity", "S/m", ["µS/cm", "mS/cm", "S/m", "mS/m"], "kappa"),
    ("mobility", "Beweglichkeit (Ladungsträger)", "Mobility (charge carriers)", "m^2/(V*s)", ["m^2/(V*s)", "cm^2/(V*s)"], "mu_q"),
    ("current_density", "Stromdichte", "Current density", "A/m^2", ["A/m^2", "mA/cm^2", "µA/cm^2"], "j_A", False),
    ("lorenz", "Lorenz-Zahl", "Lorenz number", "W*Ohm/K^2", ["W*Ohm/K^2"], "L_WF"),
    ("conductance", "Leitwert", "Conductance", "S", ["S", "mS", "µS"], "G_el"),
    ("redox", "Redoxpotential (ORP)", "Redox potential (ORP)", "V", ["mV", "V"], "E_h", False),
    # U-01: Umwelt, Licht, Schall, Strahlung
    ("rel_humidity", "Relative Feuchte", "Relative humidity", "1", ["%RH", "%", "1"], "phi_RH"),
    ("illuminance", "Beleuchtungsstärke", "Illuminance", "lx", ["lx", "klx"], "E_v"),
    ("luminous_flux", "Lichtstrom", "Luminous flux", "lm", ["lm", "klm"], "Phi_v"),
    ("sound_level", "Schallpegel", "Sound level", "1", ["dB"], "L_p", False),
    ("dose", "Energiedosis", "Absorbed dose", "Gy", ["Gy", "mGy", "µGy"], "D_dose"),
    ("equiv_dose", "Äquivalentdosis", "Equivalent dose", "Sv", ["Sv", "mSv", "µSv"], "H_dose"),
    ("dose_rate", "Dosisleistung", "Dose rate", "Gy/s", ["µSv/h", "mSv/h", "µGy/h", "Gy/h"], "H_dot"),
    # Fluide
    ("dyn_visc", "Dynamische Viskosität", "Dynamic viscosity", "Pa*s", ["Pa*s", "mPa*s", "cP"], "eta"),
    ("kin_visc", "Kinematische Viskosität", "Kinematic viscosity", "m^2/s", ["m^2/s", "mm^2/s", "cSt"], "nu_k"),
    ("vol_flow", "Volumenstrom", "Volume flow", "m^3/s", ["m^3/s", "L/s", "L/min", "mL/min", "m^3/h", "sccm", "slm"], "Q_V"),
    ("mass_flow", "Massenstrom", "Mass flow", "kg/s", ["kg/s", "kg/h", "g/s"], "m_dot"),
]
KINDS: dict[str, Kind] = {}
for row in _K:
    key, de, en, si, units, sym, *rest = row
    pos = rest[0] if rest else True
    diff = rest[1] if len(rest) > 1 else False
    KINDS[key] = Kind(key, de, en, si, units, sym, pos, diff)


def kind_dims(key):
    return ensure_kind(key).dims


def kinds_for_dims(d):
    """Vordefinierte Grössenarten mit dieser Dimension (z. B. Pa -> Druck, Spannung, E-Modul)."""
    return [k for k in KINDS.values() if not k.key.startswith("dim:") and deq(k.dims, d)]


def kinds_for_unit(unit: str):
    """U-01: Grössenarten, die zu einer Einheit passen, die naheliegendste zuerst: Arten, deren Einheitenliste die
    Einheit enthält (dimensionslose Zahl, dann Anteil vor den übrigen), danach die übrigen gleicher Dimension. Eine
    Skala (pH, dB, NTU …) passt nur zu Arten mit dieser Skala und zur Zahl, eine gewöhnliche Einheit nicht zu
    Skalen-Arten (pH-Wert, Trübung, Schallpegel, Absorbanz)."""
    _, d, _ = parse_unit(unit or "")
    sc = scale_of(unit)
    ks = [k for k in kinds_for_dims(d)
          if (any(scale_of(u) == sc for u in k.units) or k.key == "number" if sc
              else not any(scale_of(u) for u in k.units))]
    u = _normalize(unit or "") or "1"
    first = {"number": 0, "fraction": 1}
    exact = sorted((k for k in ks if u in {_normalize(x) for x in k.units}), key=lambda k: first.get(k.key, 2))
    return exact + sorted((k for k in ks if k not in exact), key=lambda k: first.get(k.key, 2))


def kind_for_unit(unit: str) -> str:
    """Naheliegendste Grössenart einer Einheit (z. B. pH -> ph, µS/cm -> el_conductivity), sonst "dim:<SI>"."""
    ks = kinds_for_unit(unit)
    return ks[0].key if ks else unit_kind_key(unit or "1")


def unit_kind_key(unit: str) -> str:
    """Grössenart "nach Einheit" für Einheiten ohne vordefinierte Art, z. B. kg/m -> dim:kg/m."""
    _, d, _ = parse_unit(unit)
    return "dim:" + (dims_text(d) or "1")


def ensure_kind(key: str) -> Kind:
    """Grössenart holen; "dim:<SI-Einheit>" wird bei Bedarf angelegt (beliebige Einheiten für eigene Variablen)."""
    k = KINDS.get(key)
    if k is not None:
        return k
    if not str(key).startswith("dim:"):
        raise UnitError(f"Grössenart {key} unbekannt")
    si = key[4:] or "1"
    parse_unit(si)
    k = Kind(key, f"Grösse in {si}", f"Quantity in {si}", si, [si], "q", False)
    KINDS[key] = k
    return k


def check_unit(kind: str, unit: str):
    """Fehlermeldung, wenn die Einheit nicht zur Groessenart passt, sonst None."""
    try:
        _, d, _ = parse_unit(unit)
    except UnitError as e:
        return str(e)
    k = ensure_kind(kind)
    if not deq(d, k.dims):
        return f"Einheit „{unit}“ passt nicht zu {k.de} ({k.si})"
    return None


def auto_unit(kind: str, si: float) -> str:
    """Gut lesbare Einheit fuer einen Wert: Zahl moeglichst zwischen 1 und 1000."""
    k = ensure_kind(kind)
    if si is None or not math.isfinite(si) or si == 0 or kind in ("angle", "ang_velocity", "strain", "number", "ph",
                                                                  "sound_level", "turbidity", "absorbance"):
        return k.units[0]
    best, score = k.units[0], None
    for i, u in enumerate(k.units):
        f, _, off = parse_unit(u)
        if off and not k.diff and kind == "temperature":
            continue
        v = abs(si / f)
        if v == 0:
            continue
        lg = math.log10(v)
        s = 0 if 0 <= lg < 3 else (-lg if lg < 0 else lg - 3 + 0.01)
        s += i * 0.001                                    # Reihenfolge der Liste bevorzugen
        if score is None or s < score:
            best, score = u, s
    if kind == "temperature":
        return "°C" if 200 < si < 2000 else "K"
    return best


# ----------------------------------------------------------------------------- Konstanten
# Definierende Konstanten des SI (9. Ausgabe der SI-Broschüre, 2019), exakt:
H_PLANCK = 6.62607015e-34          # J·s
C_LIGHT = 299792458.0              # m/s
K_BOLTZMANN = 1.380649e-23         # J/K
N_AVOGADRO = 6.02214076e23         # 1/mol
E_CHARGE = 1.602176634e-19         # C


def _wien_x() -> float:
    """Lösung von x = 5·(1 − e^(−x)) (Wiensches Verschiebungsgesetz in der Wellenlänge), Newton, Doppelgenauigkeit."""
    x = 5.0
    for _ in range(50):
        g = x - 5 * (1 - math.exp(-x))
        nx = x - g / (1 - 5 * math.exp(-x))
        if nx == x:
            break
        x = nx
    return x


# Daraus abgeleitete Konstanten, ebenfalls exakt (hier in voller Doppelgenauigkeit berechnet, nicht gerundet):
HBAR = H_PLANCK / (2 * math.pi)
R_GAS = N_AVOGADRO * K_BOLTZMANN                                                  # 8,314462618… J/(mol·K)
FARADAY = N_AVOGADRO * E_CHARGE                                                   # 96485,33212… C/mol
SIGMA_SB = 2 * math.pi ** 5 * K_BOLTZMANN ** 4 / (15 * H_PLANCK ** 3 * C_LIGHT ** 2)  # 5,670374419…·10⁻⁸
WIEN_B = H_PLANCK * C_LIGHT / (K_BOLTZMANN * _wien_x())                           # 2,897771955…·10⁻³ m·K

CONSTANTS = {
    "pi": (math.pi, "1", "Kreiszahl π", "pi"),
    "e": (math.e, "1", "Eulersche Zahl", "Euler's number"),
    "g0": (9.80665, "m/s^2", "Normfallbeschleunigung", "Standard gravity"),
    "c0": (C_LIGHT, "m/s", "Lichtgeschwindigkeit", "Speed of light"),
    "hP": (H_PLANCK, "J*s", "Planck-Konstante", "Planck constant"),
    "hbar": (HBAR, "J*s", "Reduzierte Planck-Konstante", "Reduced Planck constant"),
    "kB": (K_BOLTZMANN, "J/K", "Boltzmann-Konstante", "Boltzmann constant"),
    "NA": (N_AVOGADRO, "1/mol", "Avogadro-Konstante", "Avogadro constant"),
    "Rgas": (R_GAS, "J/(mol*K)", "Universelle Gaskonstante", "Gas constant"),
    "G_grav": (6.67430e-11, "m^3/(kg*s^2)", "Gravitationskonstante", "Gravitational constant"),
    "eps0": (8.8541878188e-12, "F/m", "Elektrische Feldkonstante", "Vacuum permittivity"),
    "mu0": (1.25663706127e-6, "H/m", "Magnetische Feldkonstante", "Vacuum permeability"),
    "q_e": (E_CHARGE, "C", "Elementarladung", "Elementary charge"),
    "m_e": (9.1093837139e-31, "kg", "Elektronenmasse", "Electron mass"),
    "m_p": (1.67262192595e-27, "kg", "Protonenmasse", "Proton mass"),
    "m_n": (1.67492750056e-27, "kg", "Neutronenmasse", "Neutron mass"),
    "m_u": (1.66053906892e-27, "kg", "Atomare Masseneinheit", "Atomic mass constant"),
    "sigma_SB": (SIGMA_SB, "W/(m^2*K^4)", "Stefan-Boltzmann-Konstante", "Stefan-Boltzmann constant"),
    "F_c": (FARADAY, "C/mol", "Faraday-Konstante", "Faraday constant"),
    "T0": (273.15, "K", "Nullpunkt der Celsius-Skala", "Zero of the Celsius scale"),
    "p_n": (101325.0, "Pa", "Normdruck (Standardatmosphäre)", "Standard atmosphere"),
    "p_std": (1e5, "Pa", "Standarddruck 1 bar", "Standard pressure 1 bar"),
    "c_std": (1000.0, "mol/m^3", "Standardkonzentration 1 mol/L", "Standard concentration 1 mol/L"),
    "b_std": (1.0, "mol/kg", "Standardmolalität 1 mol/kg", "Standard molality 1 mol/kg"),
    "MPa1": (1e6, "Pa", "Bezugsspannung 1 N/mm²", "Reference stress 1 N/mm²"),
    "b_wien": (WIEN_B, "m*K", "Wiensche Konstante", "Wien's displacement constant"),
}


def constant_dims(name):
    return parse_unit(CONSTANTS[name][1])[1]


def constant_source(name):
    """(Quellendatensatz, exakt?, Hinweis) einer Konstante; Herkunft siehe labcalc.sources."""
    from .sources import CONSTANT_SOURCES, ref
    key, exact, note = CONSTANT_SOURCES[name]
    return ref(key), exact, note


def constants_list():
    try:
        import labcite
        text, short = labcite.text, labcite.short
    except ImportError:                                    # labcite liegt daneben in sdk/python; ohne ihn nur der Titel
        def text(r):
            return r.get("title", "")
        short = text
    out = []
    for k, v in CONSTANTS.items():
        src, exact, note = constant_source(k)
        out.append({"name": k, "value": v[0], "unit": v[1], "de": v[2], "en": v[3], "source": src, "source_text": text(src), "source_short": short(src),
                    "exact": exact, "note": note})
    return out
