"""Formelsammlung: Gleichungen in SI-Einheiten, sortiert nach Gebiet und Thema.

Jede Variable hat eine Groessenart (units.KINDS). Gleichungen mit auto=True duerfen fuer die automatische Ableitung
verwendet werden (allgemeine Gesetze und Definitionen); Sonderfaelle (bestimmte Querschnitte, Lastfaelle, Wurf,
Pendel ...) stehen auf auto=False und werden nur auf Wunsch benutzt.
"""
from __future__ import annotations

import ast

from . import expr as E          # legt sdk/python in den Suchpfad
from . import render as R
from . import units as U

import labcite                   # noqa: E402
from labcalc import sources as SRC  # noqa: E402

# Vorgabe fuer haeufige Symbole: Symbol -> (Groessenart, Bezeichnung, label)
SYMBOLS = {
    "s": ("length", "Weg", "Distance"), "s0": ("length", "Anfangsposition", "Initial position"),
    "v": ("velocity", "Geschwindigkeit", "Velocity"), "v0": ("velocity", "Anfangsgeschwindigkeit", "Initial velocity"),
    "v1": ("velocity", "Geschwindigkeit 1", "Velocity 1"), "v2": ("velocity", "Geschwindigkeit 2", "Velocity 2"),
    "a": ("acceleration", "Beschleunigung", "Acceleration"), "t": ("time", "Zeit", "Time"),
    "h": ("length", "Höhe", "Height"), "m": ("mass", "Masse", "Mass"), "F": ("force", "Kraft", "Force"),
    "F_G": ("force", "Gewichtskraft", "Weight"), "F_N": ("force", "Normalkraft", "Normal force"),
    "F_R": ("force", "Reibungskraft", "Friction force"), "mu_R": ("number", "Reibungszahl", "Friction coefficient"),
    "r": ("length", "Radius", "Radius"), "d": ("length", "Durchmesser", "Diameter"), "l": ("length", "Länge", "Length"),
    "b": ("length", "Breite", "Width"), "L0": ("length", "Anfangslänge", "Initial length"),
    "dL": ("length", "Längenänderung", "Change in length"), "A": ("area", "Fläche", "Area"),
    "V": ("volume", "Volumen", "Volume"), "rho": ("density", "Dichte", "Density"),
    "sigma": ("stress", "Spannung", "Stress"), "tau": ("stress", "Schubspannung", "Shear stress"),
    "epsilon": ("strain", "Dehnung", "Strain"), "E": ("modulus", "Elastizitätsmodul", "Young's modulus"),
    "G": ("modulus", "Schubmodul", "Shear modulus"), "nu": ("number", "Querkontraktionszahl", "Poisson's ratio"),
    "omega": ("ang_velocity", "Winkelgeschwindigkeit", "Angular velocity"), "f": ("frequency", "Frequenz", "Frequency"),
    "alpha": ("angle", "Winkel", "Angle"), "P": ("power", "Leistung", "Power"), "W": ("energy", "Arbeit", "Work"),
    "T": ("temperature", "Temperatur", "Temperature"), "dT": ("temp_diff", "Temperaturdifferenz", "Temperature difference"),
    "Q": ("energy", "Wärmemenge", "Heat"), "c": ("spec_heat", "Spez. Wärmekapazität", "Specific heat capacity"),
    "n": ("amount", "Stoffmenge", "Amount of substance"), "M": ("molar_mass", "Molare Masse", "Molar mass"),
    "p": ("pressure", "Druck", "Pressure"), "U": ("voltage", "Spannung", "Voltage"), "I": ("current", "Stromstärke", "Current"),
    "R": ("resistance", "Widerstand", "Resistance"), "C": ("capacitance", "Kapazität", "Capacitance"),
    "lambda": ("length", "Wellenlänge", "Wavelength"), "k": ("spring", "Federsteifigkeit", "Spring rate"),
    "eta": ("dyn_visc", "Dynamische Viskosität", "Dynamic viscosity"), "M_b": ("torque", "Biegemoment", "Bending moment"),
    "M_t": ("torque", "Torsionsmoment", "Torque"), "I_y": ("area_moment", "Flächenträgheitsmoment", "Second moment of area"),
    "W_b": ("section_mod", "Widerstandsmoment", "Section modulus"), "J_m": ("mass_moment", "Massenträgheitsmoment", "Moment of inertia"),
    "K_I": ("stress_int", "Spannungsintensitätsfaktor", "Stress intensity factor"),
    "Y": ("number", "Geometriefaktor", "Geometry factor"), "q": ("spec_energy", "Spezifische Energie", "Specific energy"),
}


class Equation:
    def __init__(self, id, cat, sub, text, de, en, vars=None, auto=True, note="", note_en="", src=None, ref="", sample=None):
        self.id, self.cat, self.sub, self.text, self.de, self.en = id, cat, sub, text, de, en
        self.auto, self.note, self.note_en = auto, note, note_en
        self.src_key, self.ref = src, ref          # Quelle (labcalc.sources), sonst die des Abschnitts
        self.sample = sample or {}                 # typische SI-Werte für die Selbstprüfung (Exponent mit kB·T)
        self.source = None
        lhs, rhs = text.split("=", 1)
        self.lhs, self.rhs = E.parse(lhs), E.parse(rhs)
        over = vars or {}
        clash = set(over) & set(U.CONSTANTS)
        if clash:
            raise ValueError(f"{id}: Variable heisst wie eine Konstante: {', '.join(sorted(clash))}")
        self.vars = []
        for name in R.names_in(self.lhs) + R.names_in(self.rhs):
            if name in [v["sym"] for v in self.vars] or name in U.CONSTANTS:
                continue
            key = E.plain_name(name)
            spec = over.get(key)
            if spec is None:
                if key not in SYMBOLS:
                    raise ValueError(f"{id}: Variable {name} ohne Grössenart")
                kind, vde, ven = SYMBOLS[key]
            else:
                parts = spec.split("|")
                kind = parts[0]
                d = SYMBOLS.get(key, (kind, key, key))
                vde = parts[1] if len(parts) > 1 else d[1]
                ven = parts[2] if len(parts) > 2 else (d[2] if len(parts) == 1 else vde)
            if kind not in U.KINDS:
                raise ValueError(f"{id}: Grössenart {kind} unbekannt")
            self.vars.append({"sym": name, "kind": kind, "de": vde, "en": ven})
        self.consts = [n for n in R.names_in(self.lhs) + R.names_in(self.rhs) if n in U.CONSTANTS]
        self.target = self.vars[0]["sym"]
        self._iso = {}

    def var(self, sym):
        for v in self.vars:
            if v["sym"] == sym:
                return v
        return None

    def isolated(self, sym):
        """Umgestellte rechte Seite fuer sym (AST) oder None, wenn nur numerisch loesbar."""
        if sym not in self._iso:
            if isinstance(self.lhs, ast.Name) and self.lhs.id == sym and R.count(self.rhs, sym) == 0:
                self._iso[sym] = self.rhs
            else:
                import copy
                self._iso[sym] = R.isolate(copy.deepcopy(self.lhs), copy.deepcopy(self.rhs), sym)
        return self._iso[sym]

    def to_dict(self, lang="de"):
        tex, html = R.render(ast.Compare(left=self.lhs, ops=[ast.Eq()], comparators=[self.rhs]))
        return {"id": self.id, "cat": self.cat, "sub": self.sub, "de": self.de, "en": self.en, "text": self.text,
                "tex": tex, "html": html, "vars": [{**v, "html": R.sym_html(v["sym"]), "tex": R.sym_tex(v["sym"])} for v in self.vars],
                "consts": self.consts, "auto": self.auto, "note": self.note, "note_en": self.note_en,
                "source": self.source, "source_short": labcite.short(self.source), "source_text": labcite.text(self.source)}


_RAW = []


def EQ(*a, **k):
    _RAW.append((a, k))


# =============================================================================================== Mechanik
C, S = "Mechanik", "Kinematik"
EQ("kin_uniform", C, S, "s = v*t", "Gleichförmige Bewegung", "Uniform motion", auto=False)
EQ("kin_a_mean", C, S, "a = v/t", "Mittlere Beschleunigung (aus dem Stand)", "Mean acceleration (from rest)",
   {"v": "velocity|Erreichte Geschwindigkeit|Final velocity"}, note="a = Δv/Δt mit v₀ = 0")
EQ("kin_v_t", C, S, "v = v0 + a*t", "Geschwindigkeit bei konstanter Beschleunigung", "Velocity, constant acceleration")
EQ("kin_s_t", C, S, "s = v0*t + 0.5*a*t**2", "Weg bei konstanter Beschleunigung", "Distance, constant acceleration")
EQ("kin_v_s", C, S, "v**2 = v0**2 + 2*a*s", "Geschwindigkeit–Weg (zeitfrei)", "Velocity–distance (time-free)")
EQ("kin_s_mean", C, S, "s = (v0 + v)/2*t", "Weg aus mittlerer Geschwindigkeit", "Distance from mean velocity", auto=False)
EQ("kin_s_rest", C, S, "s = 0.5*a*t**2", "Weg aus dem Stand", "Distance from rest", auto=False)
S = "Freier Fall und Wurf"
EQ("fall_h", C, S, "h = 0.5*g0*t**2", "Freier Fall: Fallhöhe", "Free fall: height", {"h": "length|Fallhöhe|Drop height"}, auto=False)
EQ("fall_v", C, S, "v = g0*t", "Freier Fall: Geschwindigkeit", "Free fall: velocity", auto=False)
EQ("fall_v_h", C, S, "v = sqrt(2*g0*h)", "Freier Fall: Aufprallgeschwindigkeit", "Free fall: impact velocity",
   {"h": "length|Fallhöhe|Drop height"}, auto=False)
EQ("throw_range", C, S, "s = v0**2*sin(2*alpha)/g0", "Schräger Wurf: Wurfweite", "Projectile: range",
   {"s": "length|Wurfweite|Range", "alpha": "angle|Abwurfwinkel|Launch angle"}, auto=False, note="Abwurf- und Auftreffhöhe gleich")
EQ("throw_height", C, S, "h = v0**2*sin(alpha)**2/(2*g0)", "Schräger Wurf: Wurfhöhe", "Projectile: maximum height",
   {"h": "length|Wurfhöhe|Maximum height", "alpha": "angle|Abwurfwinkel|Launch angle"}, auto=False)
EQ("throw_time", C, S, "t = 2*v0*sin(alpha)/g0", "Schräger Wurf: Flugzeit", "Projectile: flight time",
   {"t": "time|Flugzeit|Flight time", "alpha": "angle|Abwurfwinkel|Launch angle"}, auto=False)
S = "Kreisbewegung"
EQ("rot_omega_f", C, S, "omega = 2*pi*f", "Winkelgeschwindigkeit aus Drehzahl", "Angular velocity from frequency",
   {"f": "frequency|Drehzahl, Frequenz|Rotational frequency"})
EQ("rot_v", C, S, "v = omega*r", "Bahngeschwindigkeit", "Circumferential speed")
EQ("rot_f_T", C, S, "f = 1/T", "Frequenz und Periodendauer", "Frequency and period", {"T": "time|Periodendauer|Period"})
EQ("rot_az", C, S, "a_z = v**2/r", "Zentripetalbeschleunigung", "Centripetal acceleration",
   {"a_z": "acceleration|Zentripetalbeschleunigung|Centripetal acceleration"})
EQ("rot_az_omega", C, S, "a_z = omega**2*r", "Zentripetalbeschleunigung (ω)", "Centripetal acceleration (ω)",
   {"a_z": "acceleration|Zentripetalbeschleunigung|Centripetal acceleration"})
EQ("rot_Fz", C, S, "F_z = m*v**2/r", "Zentripetalkraft", "Centripetal force", {"F_z": "force|Zentripetalkraft|Centripetal force"})
EQ("rot_phi", C, S, "phi = omega*t", "Drehwinkel", "Rotation angle", {"phi": "angle|Drehwinkel|Rotation angle"}, auto=False)
EQ("rot_alpha", C, S, "alpha_w = omega/t", "Winkelbeschleunigung (aus dem Stand)", "Angular acceleration (from rest)",
   {"alpha_w": "ang_accel|Winkelbeschleunigung|Angular acceleration"}, auto=False)
S = "Dynamik"
EQ("dyn_newton", C, S, "F = m*a", "Grundgesetz der Dynamik", "Newton's second law")
EQ("dyn_weight", C, S, "F_G = m*g0", "Gewichtskraft", "Weight")
EQ("dyn_friction", C, S, "F_R = mu_R*F_N", "Reibungskraft (Coulomb)", "Friction force (Coulomb)")
EQ("dyn_momentum", C, S, "p = m*v", "Impuls", "Momentum", {"p": "momentum|Impuls|Momentum"})
EQ("dyn_impulse", C, S, "F*t = p", "Kraftstoss", "Impulse", {"p": "momentum|Impulsänderung|Change in momentum"}, auto=False)
EQ("dyn_torque", C, S, "M = F*r_H", "Drehmoment", "Torque", {"M": "torque|Drehmoment|Torque", "r_H": "length|Hebelarm|Lever arm"})
EQ("dyn_rot_newton", C, S, "M = J_m*alpha_w", "Grundgesetz der Drehbewegung", "Rotational Newton's law",
   {"M": "torque|Drehmoment|Torque", "alpha_w": "ang_accel|Winkelbeschleunigung|Angular acceleration"})
EQ("dyn_incline_H", C, S, "F_H = m*g0*sin(alpha)", "Schiefe Ebene: Hangabtriebskraft", "Incline: downhill force",
   {"F_H": "force|Hangabtriebskraft|Downhill force", "alpha": "angle|Neigungswinkel|Incline angle"}, auto=False)
EQ("dyn_incline_N", C, S, "F_N = m*g0*cos(alpha)", "Schiefe Ebene: Normalkraft", "Incline: normal force",
   {"alpha": "angle|Neigungswinkel|Incline angle"}, auto=False)
EQ("dyn_gravity", C, S, "F = G_grav*m1*m2/r**2", "Gravitationsgesetz", "Law of gravitation",
   {"m1": "mass|Masse 1|Mass 1", "m2": "mass|Masse 2|Mass 2", "r": "length|Abstand|Distance"}, auto=False)
EQ("dyn_spring", C, S, "F_F = k*x_F", "Federgesetz (Hooke)", "Spring law (Hooke)",
   {"F_F": "force|Federkraft|Spring force", "x_F": "length|Federweg|Spring deflection"})
EQ("dyn_density", C, S, "rho = m/V", "Dichte", "Density")
S = "Energie und Leistung"
EQ("en_kin", C, S, "E_kin = 0.5*m*v**2", "Kinetische Energie", "Kinetic energy", {"E_kin": "energy|Kinetische Energie|Kinetic energy"})
EQ("en_pot", C, S, "E_pot = m*g0*h", "Potenzielle Energie", "Potential energy", {"E_pot": "energy|Potenzielle Energie|Potential energy"})
EQ("en_spring", C, S, "E_sp = 0.5*k*x_F**2", "Spannenergie einer Feder", "Spring energy",
   {"E_sp": "energy|Spannenergie|Spring energy", "x_F": "length|Federweg|Spring deflection"})
EQ("en_rot", C, S, "E_rot = 0.5*J_m*omega**2", "Rotationsenergie", "Rotational energy", {"E_rot": "energy|Rotationsenergie|Rotational energy"})
EQ("en_work", C, S, "W = F*s", "Mechanische Arbeit", "Mechanical work")
EQ("en_work_angle", C, S, "W = F*s*cos(alpha)", "Arbeit bei schräger Kraft", "Work, inclined force", auto=False)
EQ("en_power", C, S, "P = W/t", "Leistung", "Power")
EQ("en_power_v", C, S, "P = F*v", "Leistung aus Kraft und Geschwindigkeit", "Power from force and velocity")
EQ("en_power_rot", C, S, "P = M*omega", "Leistung bei Drehbewegung", "Rotational power", {"M": "torque|Drehmoment|Torque"})
EQ("en_eff", C, S, "eta_w = P_ab/P_zu", "Wirkungsgrad", "Efficiency",
   {"eta_w": "number|Wirkungsgrad|Efficiency", "P_ab": "power|Nutzleistung|Output power", "P_zu": "power|Zugeführte Leistung|Input power"})
S = "Schwingungen und Wellen"
EQ("osc_spring", C, S, "T = 2*pi*sqrt(m/k)", "Federpendel: Periodendauer", "Spring pendulum: period", {"T": "time|Periodendauer|Period"}, auto=False)
EQ("osc_pendulum", C, S, "T = 2*pi*sqrt(l/g0)", "Fadenpendel: Periodendauer", "Simple pendulum: period",
   {"T": "time|Periodendauer|Period", "l": "length|Pendellänge|Pendulum length"}, auto=False, note="kleine Auslenkung")
EQ("osc_omega0", C, S, "omega_0 = sqrt(k/m)", "Eigenkreisfrequenz", "Natural angular frequency",
   {"omega_0": "ang_velocity|Eigenkreisfrequenz|Natural angular frequency"})
EQ("osc_damped", C, S, "x_t = x_0*exp(-delta_d*t)*cos(omega*t)", "Gedämpfte Schwingung", "Damped oscillation",
   {"x_t": "length|Auslenkung|Displacement", "x_0": "length|Amplitude|Amplitude", "delta_d": "rate_const|Abklingkonstante|Decay constant",
    "omega": "ang_velocity|Kreisfrequenz|Angular frequency"}, auto=False)
EQ("wave_speed", C, S, "c_w = lambda*f", "Ausbreitungsgeschwindigkeit", "Wave speed", {"c_w": "velocity|Ausbreitungsgeschwindigkeit|Wave speed"})
EQ("wave_sound_solid", C, S, "c_w = sqrt(E/rho)", "Schallgeschwindigkeit im Stab", "Speed of sound in a rod",
   {"c_w": "velocity|Schallgeschwindigkeit|Speed of sound"}, auto=False)

# =============================================================================================== Festigkeit
C, S = "Festigkeitslehre", "Spannung und Dehnung"
EQ("str_normal", C, S, "sigma = F/A", "Normalspannung", "Normal stress", {"A": "area|Querschnittsfläche|Cross-section"})
EQ("str_shear", C, S, "tau = F/A", "Schubspannung (mittlere)", "Shear stress (mean)", {"A": "area|Scherfläche|Shear area"}, auto=False)
EQ("str_strain", C, S, "epsilon = dL/L0", "Dehnung", "Strain")
EQ("str_hooke", C, S, "sigma = E*epsilon", "Hookesches Gesetz", "Hooke's law")
EQ("str_shear_hooke", C, S, "tau = G*gamma", "Hookesches Gesetz für Schub", "Hooke's law in shear", {"gamma": "strain|Gleitung|Shear strain"})
EQ("str_poisson", C, S, "epsilon_q = -nu*epsilon", "Querdehnung", "Lateral strain", {"epsilon_q": "strain|Querdehnung|Lateral strain"})
EQ("str_G", C, S, "G = E/(2*(1 + nu))", "Schubmodul aus E und ν", "Shear modulus from E and ν")
EQ("str_K", C, S, "K_v = E/(3*(1 - 2*nu))", "Kompressionsmodul", "Bulk modulus", {"K_v": "modulus|Kompressionsmodul|Bulk modulus"})
EQ("str_true_stress", C, S, "sigma_w = sigma*(1 + epsilon)", "Wahre Spannung", "True stress",
   {"sigma_w": "stress|Wahre Spannung|True stress"}, note="gilt bis zur Einschnürung")
EQ("str_true_strain", C, S, "phi_w = ln(1 + epsilon)", "Wahre (logarithmische) Dehnung", "True (logarithmic) strain",
   {"phi_w": "strain|Wahre Dehnung|True strain"})
EQ("str_thermal", C, S, "sigma_th = E*alpha_T*dT", "Wärmespannung (vollständig behindert)", "Thermal stress (fully constrained)",
   {"sigma_th": "stress|Wärmespannung|Thermal stress", "alpha_T": "expansion|Ausdehnungskoeffizient|Expansion coefficient"})
EQ("str_safety", C, S, "S_F = R_e/sigma", "Sicherheit gegen Fliessen", "Safety factor against yield",
   {"S_F": "number|Sicherheitsfaktor|Safety factor", "R_e": "stress|Streckgrenze|Yield strength"})
EQ("str_notch", C, S, "sigma_max = K_t*sigma_n", "Kerbspannung", "Notch stress",
   {"sigma_max": "stress|Spannungsspitze|Peak stress", "K_t": "number|Formzahl|Stress concentration factor",
    "sigma_n": "stress|Nennspannung|Nominal stress"})
EQ("str_mixture", C, S, "E_c = V_f*E_f + (1 - V_f)*E_m", "Mischungsregel (Verbund, längs)", "Rule of mixtures (longitudinal)",
   {"E_c": "modulus|E-Modul Verbund|Composite modulus", "V_f": "number|Faservolumenanteil|Fibre volume fraction",
    "E_f": "modulus|E-Modul Faser|Fibre modulus", "E_m": "modulus|E-Modul Matrix|Matrix modulus"}, auto=False)
EQ("str_mixture_t", C, S, "1/E_c = V_f/E_f + (1 - V_f)/E_m", "Mischungsregel (Verbund, quer)", "Rule of mixtures (transverse)",
   {"E_c": "modulus|E-Modul Verbund quer|Composite modulus, transverse", "V_f": "number|Faservolumenanteil|Fibre volume fraction",
    "E_f": "modulus|E-Modul Faser|Fibre modulus", "E_m": "modulus|E-Modul Matrix|Matrix modulus"}, auto=False)
EQ("str_hallpetch", C, S, "sigma_y = sigma_0 + k_y/sqrt(d_k)", "Hall-Petch-Beziehung", "Hall–Petch relation",
   {"sigma_y": "stress|Streckgrenze|Yield strength", "sigma_0": "stress|Reibspannung|Friction stress",
    "k_y": "stress_int|Hall-Petch-Koeffizient|Hall–Petch coefficient", "d_k": "length|Korngrösse|Grain size"}, auto=False)
S = "Zugversuch"
EQ("tens_Rm", C, S, "R_m = F_m/S_0", "Zugfestigkeit", "Tensile strength",
   {"R_m": "stress|Zugfestigkeit|Tensile strength", "F_m": "force|Höchstkraft|Maximum force", "S_0": "area|Anfangsquerschnitt|Original cross-section"})
EQ("tens_Re", C, S, "R_e = F_e/S_0", "Streckgrenze", "Yield strength",
   {"R_e": "stress|Streckgrenze|Yield strength", "F_e": "force|Kraft an der Streckgrenze|Yield force", "S_0": "area|Anfangsquerschnitt|Original cross-section"})
EQ("tens_A", C, S, "A_b = (L_u - L_0)/L_0", "Bruchdehnung", "Elongation after fracture",
   {"A_b": "strain|Bruchdehnung|Elongation after fracture", "L_u": "length|Messlänge nach Bruch|Final gauge length",
    "L_0": "length|Anfangsmesslänge|Original gauge length"})
EQ("tens_Z", C, S, "Z = (S_0 - S_u)/S_0", "Brucheinschnürung", "Reduction of area",
   {"Z": "strain|Brucheinschnürung|Reduction of area", "S_0": "area|Anfangsquerschnitt|Original cross-section",
    "S_u": "area|Kleinster Querschnitt nach Bruch|Minimum cross-section after fracture"})
EQ("tens_S0_round", C, S, "S_0 = pi*d_0**2/4", "Anfangsquerschnitt Rundprobe", "Cross-section, round specimen",
   {"S_0": "area|Anfangsquerschnitt|Original cross-section", "d_0": "length|Probendurchmesser|Specimen diameter"}, auto=False)
EQ("tens_S0_flat", C, S, "S_0 = a_0*b_0", "Anfangsquerschnitt Flachprobe", "Cross-section, flat specimen",
   {"S_0": "area|Anfangsquerschnitt|Original cross-section", "a_0": "length|Probendicke|Specimen thickness",
    "b_0": "length|Probenbreite|Specimen width"}, auto=False)
EQ("tens_L0_prop", C, S, "L_0 = 5.65*sqrt(S_0)", "Proportionalprobe (k = 5,65)", "Proportional specimen (k = 5.65)",
   {"L_0": "length|Anfangsmesslänge|Original gauge length", "S_0": "area|Anfangsquerschnitt|Original cross-section"}, auto=False)
S = "Biegung"
EQ("bend_sigma", C, S, "sigma_b = M_b/W_b", "Biegespannung (Randfaser)", "Bending stress (outer fibre)",
   {"sigma_b": "stress|Biegespannung|Bending stress"})
EQ("bend_sigma_z", C, S, "sigma_b = M_b*z/I_y", "Biegespannung im Abstand z", "Bending stress at distance z",
   {"sigma_b": "stress|Biegespannung|Bending stress", "z": "length|Abstand zur neutralen Faser|Distance from neutral axis"}, auto=False)
EQ("bend_W", C, S, "W_b = I_y/e_r", "Widerstandsmoment aus I", "Section modulus from I",
   {"e_r": "length|Randabstand|Distance to outer fibre"})
EQ("bend_I_rect", C, S, "I_y = b*h**3/12", "Flächenträgheitsmoment Rechteck", "Second moment, rectangle", auto=False)
EQ("bend_W_rect", C, S, "W_b = b*h**2/6", "Widerstandsmoment Rechteck", "Section modulus, rectangle", auto=False)
EQ("bend_I_circ", C, S, "I_y = pi*d**4/64", "Flächenträgheitsmoment Kreis", "Second moment, circle", auto=False)
EQ("bend_W_circ", C, S, "W_b = pi*d**3/32", "Widerstandsmoment Kreis", "Section modulus, circle", auto=False)
EQ("bend_I_tube", C, S, "I_y = pi*(D_a**4 - d_i**4)/64", "Flächenträgheitsmoment Rohr", "Second moment, tube",
   {"D_a": "length|Aussendurchmesser|Outer diameter", "d_i": "length|Innendurchmesser|Inner diameter"}, auto=False)
EQ("bend_cant_M", C, S, "M_b = F*l", "Kragträger: Einspannmoment", "Cantilever: fixed-end moment", auto=False)
EQ("bend_cant_f", C, S, "w = F*l**3/(3*E*I_y)", "Kragträger: Durchbiegung (Einzellast)", "Cantilever: deflection (end load)",
   {"w": "length|Durchbiegung|Deflection"}, auto=False)
EQ("bend_ss_M", C, S, "M_b = F*l/4", "Träger auf zwei Stützen: Moment (Last in Mitte)", "Simply supported: moment (central load)", auto=False)
EQ("bend_ss_f", C, S, "w = F*l**3/(48*E*I_y)", "Träger auf zwei Stützen: Durchbiegung", "Simply supported: deflection (central load)",
   {"w": "length|Durchbiegung|Deflection"}, auto=False)
EQ("bend_3pt", C, S, "sigma_b = 3*F*l/(2*b*h**2)", "Dreipunktbiegung: Biegespannung", "Three-point bending: flexural stress",
   {"sigma_b": "stress|Biegespannung|Flexural stress", "l": "length|Stützweite|Support span", "h": "length|Probendicke|Specimen thickness"}, auto=False)
EQ("bend_3pt_E", C, S, "E = l**3*k_b/(4*b*h**3)", "Dreipunktbiegung: Biegemodul", "Three-point bending: flexural modulus",
   {"E": "modulus|Biegemodul|Flexural modulus", "l": "length|Stützweite|Support span", "h": "length|Probendicke|Specimen thickness",
    "k_b": "spring|Steigung Kraft–Durchbiegung|Slope force–deflection"}, auto=False)
S = "Torsion und Knickung"
EQ("tors_tau", C, S, "tau_t = M_t/W_t", "Torsionsspannung", "Torsional stress",
   {"tau_t": "stress|Torsionsspannung|Torsional stress", "W_t": "section_mod|Polares Widerstandsmoment|Polar section modulus"})
EQ("tors_Wt", C, S, "W_t = pi*d**3/16", "Polares Widerstandsmoment Kreis", "Polar section modulus, circle",
   {"W_t": "section_mod|Polares Widerstandsmoment|Polar section modulus"}, auto=False)
EQ("tors_Ip", C, S, "I_p = pi*d**4/32", "Polares Flächenträgheitsmoment Kreis", "Polar moment, circle",
   {"I_p": "area_moment|Polares Flächenträgheitsmoment|Polar moment of area"}, auto=False)
EQ("tors_phi", C, S, "phi = M_t*l/(G*I_p)", "Verdrehwinkel", "Angle of twist",
   {"phi": "angle|Verdrehwinkel|Angle of twist", "I_p": "area_moment|Polares Flächenträgheitsmoment|Polar moment of area"})
EQ("buck_euler", C, S, "F_k = pi**2*E*I_y/l_k**2", "Knickkraft nach Euler", "Euler buckling load",
   {"F_k": "force|Knickkraft|Buckling load", "l_k": "length|Knicklänge|Effective length"})
EQ("buck_i", C, S, "i_r = sqrt(I_y/A)", "Trägheitsradius", "Radius of gyration", {"i_r": "length|Trägheitsradius|Radius of gyration"})
EQ("buck_lambda", C, S, "lambda_s = l_k/i_r", "Schlankheitsgrad", "Slenderness ratio",
   {"lambda_s": "number|Schlankheitsgrad|Slenderness ratio", "l_k": "length|Knicklänge|Effective length", "i_r": "length|Trägheitsradius|Radius of gyration"})
S = "Behälter"
EQ("ves_hoop", C, S, "sigma_t = p*d/(2*s_w)", "Kesselformel: Umfangsspannung", "Thin-walled vessel: hoop stress",
   {"sigma_t": "stress|Umfangsspannung|Hoop stress", "d": "length|Innendurchmesser|Inner diameter", "s_w": "length|Wanddicke|Wall thickness"})
EQ("ves_axial", C, S, "sigma_a = p*d/(4*s_w)", "Kesselformel: Längsspannung", "Thin-walled vessel: axial stress",
   {"sigma_a": "stress|Längsspannung|Axial stress", "d": "length|Innendurchmesser|Inner diameter", "s_w": "length|Wanddicke|Wall thickness"})
EQ("ves_sphere", C, S, "sigma_k = p*d/(4*s_w)", "Kugelbehälter: Wandspannung", "Spherical vessel: wall stress",
   {"sigma_k": "stress|Wandspannung|Wall stress", "d": "length|Innendurchmesser|Inner diameter", "s_w": "length|Wanddicke|Wall thickness"}, auto=False)
S = "Bruchmechanik"
EQ("frac_KI", C, S, "K_I = Y*sigma*sqrt(pi*a)", "Spannungsintensitätsfaktor", "Stress intensity factor",
   {"a": "length|Risslänge|Crack length"})
EQ("frac_crit", C, S, "K_Ic = Y*sigma_c*sqrt(pi*a_c)", "Bruchzähigkeit: kritischer Zustand", "Fracture toughness: critical state",
   {"K_Ic": "stress_int|Bruchzähigkeit|Fracture toughness", "sigma_c": "stress|Bruchspannung|Fracture stress",
    "a_c": "length|Kritische Risslänge|Critical crack length"})
EQ("frac_griffith", C, S, "sigma_c = sqrt(2*E*gamma_s/(pi*a))", "Griffith-Kriterium", "Griffith criterion",
   {"sigma_c": "stress|Bruchspannung|Fracture stress", "gamma_s": "surface_energy|Oberflächenenergie|Surface energy",
    "a": "length|Halbe Risslänge|Half crack length"}, auto=False)
EQ("frac_G", C, S, "G_I = K_I**2/E", "Energiefreisetzungsrate (ESZ)", "Energy release rate (plane stress)",
   {"G_I": "surface_energy|Energiefreisetzungsrate|Energy release rate"}, auto=False)
EQ("frac_plastic", C, S, "r_p = (K_I/sigma_y)**2/(2*pi)", "Plastische Zone (Irwin, ESZ)", "Plastic zone (Irwin, plane stress)",
   {"r_p": "length|Radius plastische Zone|Plastic zone radius", "sigma_y": "stress|Streckgrenze|Yield strength"}, auto=False)
EQ("frac_paris", C, S, "da_dN = C_p*dK**n_P", "Paris-Gesetz (Risswachstum)", "Paris law (crack growth)",
   {"da_dN": "length|Risswachstum je Zyklus|Crack growth per cycle", "C_p": "length|Paris-Konstante C|Paris constant C",
    "dK": "number|ΔK in MPa√m (Zahlenwert)|ΔK in MPa√m (number)", "n_P": "number|Paris-Exponent|Paris exponent"}, auto=False,
   note="ΔK als Zahlenwert in MPa√m, C in m je Zyklus passend dazu")
S = "Härte"
EQ("hard_HV", C, S, "HV = 0.1891*F/(d_V**2*MPa1)", "Vickershärte", "Vickers hardness",
   {"HV": "number|Vickershärte|Vickers hardness", "F": "force|Prüfkraft|Test force", "d_V": "length|Mittlere Eindruckdiagonale|Mean diagonal"},
   note="F in N, d in mm (wie in der Norm)")
EQ("hard_HB", C, S, "HB = 0.102*2*F/(pi*D_k*(D_k - sqrt(D_k**2 - d_B**2))*MPa1)", "Brinellhärte", "Brinell hardness",
   {"HB": "number|Brinellhärte|Brinell hardness", "F": "force|Prüfkraft|Test force", "D_k": "length|Kugeldurchmesser|Ball diameter",
    "d_B": "length|Eindruckdurchmesser|Indentation diameter"}, auto=False)
EQ("hard_Rm", C, S, "R_m = 3.3*HV*MPa1", "Zugfestigkeit aus Vickershärte (Faustformel Stahl, ≈)", "Tensile strength from HV (steel rule of thumb, ≈)",
   {"R_m": "stress|Zugfestigkeit|Tensile strength", "HV": "number|Vickershärte|Vickers hardness"}, auto=False,
   note="Faustformel (Faktor 3,3 nicht gegen die Tabellen der ISO 18265 geprüft); nur Richtwert für unlegierte und niedriglegierte Stähle "
        "mittlerer Festigkeit; für verbindliche Werte die Umwertungstabellen der Norm verwenden",
   note_en="rule of thumb (factor 3.3 not checked against the ISO 18265 tables); indicative only for unalloyed and low-alloy steels "
           "of medium strength; use the conversion tables of the standard for binding values")

# =============================================================================================== Geometrie
C, S = "Geometrie", "Flächen"
EQ("geo_circle", C, S, "A = pi*d**2/4", "Kreisfläche (Durchmesser)", "Circle area (diameter)", auto=False)
EQ("geo_circle_r", C, S, "A = pi*r**2", "Kreisfläche (Radius)", "Circle area (radius)", auto=False)
EQ("geo_circumf", C, S, "U_k = pi*d", "Kreisumfang", "Circumference", {"U_k": "length|Umfang|Circumference"}, auto=False)
EQ("geo_rect", C, S, "A = b*h", "Rechteckfläche", "Rectangle area", auto=False)
EQ("geo_triangle", C, S, "A = 0.5*b*h", "Dreiecksfläche", "Triangle area", auto=False)
EQ("geo_ring", C, S, "A = pi*(D_a**2 - d_i**2)/4", "Kreisring (Rohrquerschnitt)", "Annulus (tube cross-section)",
   {"D_a": "length|Aussendurchmesser|Outer diameter", "d_i": "length|Innendurchmesser|Inner diameter"}, auto=False)
EQ("geo_pyth", C, S, "c_h = sqrt(a_k**2 + b_k**2)", "Satz des Pythagoras", "Pythagorean theorem",
   {"c_h": "length|Hypotenuse|Hypotenuse", "a_k": "length|Kathete a|Leg a", "b_k": "length|Kathete b|Leg b"}, auto=False)
EQ("geo_sector", C, S, "A = 0.5*r**2*phi", "Kreissektor", "Circular sector", {"phi": "angle|Mittelpunktswinkel|Central angle"}, auto=False)
S = "Körper"
EQ("geo_cyl", C, S, "V = pi*d**2/4*h", "Zylindervolumen", "Cylinder volume", auto=False)
EQ("geo_sphere", C, S, "V = 4/3*pi*r**3", "Kugelvolumen", "Sphere volume", auto=False)
EQ("geo_sphere_A", C, S, "A = 4*pi*r**2", "Kugeloberfläche", "Sphere surface", auto=False)
EQ("geo_cuboid", C, S, "V = l*b*h", "Quadervolumen", "Cuboid volume", auto=False)
EQ("geo_cone", C, S, "V = pi*r**2*h/3", "Kegelvolumen", "Cone volume", auto=False)
EQ("geo_prism", C, S, "V = A*l", "Prisma, Stab (Querschnitt × Länge)", "Prism, bar (cross-section × length)", auto=False)

# =============================================================================================== Waerme
C, S = "Wärmelehre", "Wärme und Temperatur"
EQ("th_heat", C, S, "Q = m*c*dT", "Wärmemenge", "Heat")
EQ("th_latent", C, S, "Q = m*q", "Umwandlungswärme (Schmelzen, Verdampfen)", "Latent heat", {"q": "spec_energy|Spez. Umwandlungswärme|Specific latent heat"})
EQ("th_expansion", C, S, "dL = alpha_T*L0*dT", "Längenausdehnung", "Linear thermal expansion",
   {"alpha_T": "expansion|Längenausdehnungskoeffizient|Linear expansion coefficient"})
EQ("th_vol_expansion", C, S, "dV = 3*alpha_T*V*dT", "Volumenausdehnung", "Volume expansion",
   {"dV": "volume|Volumenänderung|Change in volume", "alpha_T": "expansion|Längenausdehnungskoeffizient|Linear expansion coefficient"}, auto=False)
EQ("th_mix", C, S, "T_m = (m1*c1*T1 + m2*c2*T2)/(m1*c1 + m2*c2)", "Mischungstemperatur", "Mixing temperature",
   {"T_m": "temperature|Mischungstemperatur|Mixing temperature", "m1": "mass|Masse 1|Mass 1", "m2": "mass|Masse 2|Mass 2",
    "c1": "spec_heat|Wärmekapazität 1|Specific heat 1", "c2": "spec_heat|Wärmekapazität 2|Specific heat 2",
    "T1": "temperature|Temperatur 1|Temperature 1", "T2": "temperature|Temperatur 2|Temperature 2"}, auto=False)
S = "Wärmeübertragung"
EQ("th_cond", C, S, "Q_dot = lambda_w*A*dT/s_w", "Wärmeleitung (ebene Wand)", "Conduction (plane wall)",
   {"Q_dot": "power|Wärmestrom|Heat flow", "lambda_w": "conductivity_th|Wärmeleitfähigkeit|Thermal conductivity",
    "s_w": "length|Wanddicke|Wall thickness"})
EQ("th_conv", C, S, "Q_dot = alpha_h*A*dT", "Wärmeübergang (Konvektion)", "Convection",
   {"Q_dot": "power|Wärmestrom|Heat flow", "alpha_h": "htc|Wärmeübergangskoeffizient|Heat transfer coefficient"}, auto=False)
EQ("th_rad", C, S, "Q_dot = eps_e*sigma_SB*A*T**4", "Wärmestrahlung", "Thermal radiation",
   {"Q_dot": "power|Abgestrahlte Leistung|Radiated power", "eps_e": "number|Emissionsgrad|Emissivity"}, auto=False)
EQ("th_flux", C, S, "q_A = Q_dot/A", "Wärmestromdichte", "Heat flux",
   {"q_A": "heat_flux|Wärmestromdichte|Heat flux", "Q_dot": "power|Wärmestrom|Heat flow"})
EQ("th_diffusivity", C, S, "a_th = lambda_w/(rho*c)", "Temperaturleitfähigkeit", "Thermal diffusivity",
   {"a_th": "diffusivity|Temperaturleitfähigkeit|Thermal diffusivity", "lambda_w": "conductivity_th|Wärmeleitfähigkeit|Thermal conductivity"})
EQ("th_wien", C, S, "lambda_max = b_wien/T", "Wiensches Verschiebungsgesetz", "Wien's displacement law",
   {"lambda_max": "length|Wellenlänge des Maximums|Peak wavelength"}, auto=False)
S = "Gase"
EQ("gas_ideal", C, S, "p*V = n*Rgas*T", "Ideales Gasgesetz (Stoffmenge)", "Ideal gas law (amount)")
EQ("gas_ideal_m", C, S, "p*V = m*R_s*T", "Ideales Gasgesetz (Masse)", "Ideal gas law (mass)", {"R_s": "spec_gas|Spez. Gaskonstante|Specific gas constant"}, auto=False)
EQ("gas_Rs", C, S, "R_s = Rgas/M", "Spezifische Gaskonstante", "Specific gas constant", {"R_s": "spec_gas|Spez. Gaskonstante|Specific gas constant"})
EQ("gas_boyle", C, S, "p1*V1 = p2*V2", "Boyle-Mariotte (isotherm)", "Boyle's law (isothermal)",
   {"p1": "pressure|Druck 1|Pressure 1", "V1": "volume|Volumen 1|Volume 1", "p2": "pressure|Druck 2|Pressure 2", "V2": "volume|Volumen 2|Volume 2"}, auto=False)
EQ("gas_charles", C, S, "V1/T1 = V2/T2", "Gay-Lussac (isobar)", "Charles's law (isobaric)",
   {"V1": "volume|Volumen 1|Volume 1", "T1": "temperature|Temperatur 1|Temperature 1", "V2": "volume|Volumen 2|Volume 2",
    "T2": "temperature|Temperatur 2|Temperature 2"}, auto=False)
EQ("gas_amontons", C, S, "p1/T1 = p2/T2", "Amontons (isochor)", "Gay-Lussac's law (isochoric)",
   {"p1": "pressure|Druck 1|Pressure 1", "T1": "temperature|Temperatur 1|Temperature 1", "p2": "pressure|Druck 2|Pressure 2",
    "T2": "temperature|Temperatur 2|Temperature 2"}, auto=False)
EQ("gas_adiabatic", C, S, "p1/p2 = (V2/V1)**kappa", "Adiabate (isentrop)", "Adiabatic (isentropic)",
   {"p1": "pressure|Druck 1|Pressure 1", "V1": "volume|Volumen 1|Volume 1", "p2": "pressure|Druck 2|Pressure 2",
    "V2": "volume|Volumen 2|Volume 2", "kappa": "number|Isentropenexponent|Heat capacity ratio"}, auto=False)
EQ("gas_iso_work", C, S, "W = n*Rgas*T*ln(V2/V1)", "Isotherme Volumenarbeit", "Isothermal work",
   {"V1": "volume|Volumen 1|Volume 1", "V2": "volume|Volumen 2|Volume 2"}, auto=False)
EQ("gas_carnot", C, S, "eta_c = 1 - T_k/T_w", "Carnot-Wirkungsgrad", "Carnot efficiency",
   {"eta_c": "number|Carnot-Wirkungsgrad|Carnot efficiency", "T_k": "temperature|Kalte Temperatur|Cold temperature",
    "T_w": "temperature|Warme Temperatur|Hot temperature"}, auto=False)
EQ("gas_mol_kin", C, S, "v_rms = sqrt(3*Rgas*T/M)", "Mittlere Molekülgeschwindigkeit", "RMS molecular speed",
   {"v_rms": "velocity|Mittlere quadratische Geschwindigkeit|RMS speed"}, auto=False)
EQ("gas_molvol", C, S, "V_m = V/n", "Molares Volumen", "Molar volume", {"V_m": "molar_volume|Molares Volumen|Molar volume"}, src="greenbook")
EQ("gas_dalton", C, S, "p_i = x_i*p", "Partialdruck (Dalton)", "Partial pressure (Dalton)",
   {"p_i": "pressure|Partialdruck|Partial pressure", "x_i": "number|Stoffmengenanteil|Mole fraction", "p": "pressure|Gesamtdruck|Total pressure"},
   auto=False, src="atkins")
EQ("gas_vdw", C, S, "(p + a_vdw*n**2/V**2)*(V - n*b_vdw) = n*Rgas*T", "Van-der-Waals-Gleichung (reales Gas)", "Van der Waals equation (real gas)",
   {"a_vdw": "vdw_a|Van-der-Waals-Konstante a|Van der Waals constant a", "b_vdw": "molar_volume|Van-der-Waals-Konstante b|Van der Waals constant b"},
   auto=False, src="atkins")

# =============================================================================================== Fluide
C, S = "Fluidmechanik", "Hydrostatik"
EQ("fl_hydro", C, S, "p = rho*g0*h", "Hydrostatischer Druck", "Hydrostatic pressure", {"h": "length|Tiefe|Depth"}, auto=False)
EQ("fl_buoy", C, S, "F_A = rho*g0*V", "Auftriebskraft", "Buoyancy force", {"F_A": "force|Auftriebskraft|Buoyancy force", "V": "volume|Verdrängtes Volumen|Displaced volume"}, auto=False)
EQ("fl_pressure", C, S, "p = F/A", "Druck", "Pressure", auto=False)
S = "Strömung"
EQ("fl_flow", C, S, "Q_V = A*v", "Volumenstrom", "Volume flow rate",
   {"Q_V": "vol_flow|Volumenstrom|Volume flow rate", "A": "area|Strömungsquerschnitt|Flow cross-section",
    "v": "velocity|Mittlere Strömungsgeschwindigkeit|Mean flow velocity"}, auto=False)
EQ("fl_massflow", C, S, "m_dot = rho*Q_V", "Massenstrom", "Mass flow rate",
   {"m_dot": "mass_flow|Massenstrom|Mass flow rate", "Q_V": "vol_flow|Volumenstrom|Volume flow rate"})
EQ("fl_cont", C, S, "A1*v1 = A2*v2", "Kontinuitätsgleichung", "Continuity equation",
   {"A1": "area|Querschnitt 1|Cross-section 1", "A2": "area|Querschnitt 2|Cross-section 2"}, auto=False)
EQ("fl_bernoulli", C, S, "p1 + 0.5*rho*v1**2 + rho*g0*h1 = p2 + 0.5*rho*v2**2 + rho*g0*h2", "Bernoulli-Gleichung", "Bernoulli equation",
   {"p1": "pressure|Druck 1|Pressure 1", "p2": "pressure|Druck 2|Pressure 2", "h1": "length|Höhe 1|Height 1", "h2": "length|Höhe 2|Height 2"}, auto=False)
EQ("fl_dyn_pressure", C, S, "p_d = 0.5*rho*v**2", "Staudruck", "Dynamic pressure", {"p_d": "pressure|Staudruck|Dynamic pressure"}, auto=False)
EQ("fl_torricelli", C, S, "v = sqrt(2*g0*h)", "Ausflussgeschwindigkeit (Torricelli)", "Outflow velocity (Torricelli)",
   {"h": "length|Füllhöhe|Fluid height"}, auto=False)
EQ("fl_re", C, S, "Re = rho*v*d/eta", "Reynolds-Zahl", "Reynolds number", {"Re": "number|Reynolds-Zahl|Reynolds number", "d": "length|Charakteristische Länge|Characteristic length"})
EQ("fl_re_nu", C, S, "Re = v*d/nu_k", "Reynolds-Zahl (kinematisch)", "Reynolds number (kinematic)",
   {"Re": "number|Reynolds-Zahl|Reynolds number", "d": "length|Charakteristische Länge|Characteristic length",
    "nu_k": "kin_visc|Kinematische Viskosität|Kinematic viscosity"})
EQ("fl_nu", C, S, "nu_k = eta/rho", "Kinematische Viskosität", "Kinematic viscosity", {"nu_k": "kin_visc|Kinematische Viskosität|Kinematic viscosity"})
EQ("fl_hagen", C, S, "Q_V = pi*r**4*dp/(8*eta*l)", "Hagen-Poiseuille (laminar)", "Hagen–Poiseuille (laminar)",
   {"Q_V": "vol_flow|Volumenstrom|Volume flow rate", "dp": "pressure|Druckdifferenz|Pressure difference", "l": "length|Rohrlänge|Pipe length"}, auto=False)
EQ("fl_stokes", C, S, "F = 6*pi*eta*r*v", "Stokes-Reibung (Kugel)", "Stokes drag (sphere)", auto=False)
EQ("fl_drag", C, S, "F_W = c_W*A*0.5*rho*v**2", "Strömungswiderstand", "Drag force",
   {"F_W": "force|Widerstandskraft|Drag force", "c_W": "number|Widerstandsbeiwert|Drag coefficient", "A": "area|Stirnfläche|Frontal area"}, auto=False)
EQ("fl_darcy", C, S, "dp = lambda_R*l/d*0.5*rho*v**2", "Druckverlust im Rohr (Darcy)", "Pipe pressure loss (Darcy)",
   {"dp": "pressure|Druckverlust|Pressure loss", "lambda_R": "number|Rohrreibungszahl|Friction factor", "l": "length|Rohrlänge|Pipe length",
    "d": "length|Rohrdurchmesser|Pipe diameter"}, auto=False)

# =============================================================================================== Elektrotechnik
C, S = "Elektrotechnik", "Gleichstrom"
EQ("el_ohm", C, S, "U = R*I", "Ohmsches Gesetz", "Ohm's law")
EQ("el_power", C, S, "P = U*I", "Elektrische Leistung", "Electric power")
EQ("el_power_R", C, S, "P = I**2*R", "Leistung aus Strom und Widerstand", "Power from current and resistance")
EQ("el_power_U", C, S, "P = U**2/R", "Leistung aus Spannung und Widerstand", "Power from voltage and resistance")
EQ("el_resist", C, S, "R = rho_el*l/A", "Leiterwiderstand", "Conductor resistance",
   {"rho_el": "resistivity|Spez. Widerstand|Resistivity", "l": "length|Leiterlänge|Conductor length", "A": "area|Leiterquerschnitt|Conductor cross-section"})
EQ("el_resist_T", C, S, "R_T = R_20*(1 + alpha_R*dT)", "Temperaturabhängiger Widerstand", "Temperature-dependent resistance",
   {"R_T": "resistance|Widerstand bei T|Resistance at T", "R_20": "resistance|Widerstand bei 20 °C|Resistance at 20 °C",
    "alpha_R": "temp_coeff|Temperaturkoeffizient|Temperature coefficient", "dT": "temp_diff|Temperaturdifferenz zu 20 °C|Difference to 20 °C"})
EQ("el_charge", C, S, "Q = I*t", "Ladung", "Charge", {"Q": "charge|Ladung|Charge"})
EQ("el_energy", C, S, "W = U*I*t", "Elektrische Arbeit", "Electric energy", {"W": "energy|Elektrische Arbeit|Electric energy"}, auto=False)
EQ("el_series", C, S, "R_ges = R1 + R2", "Reihenschaltung", "Series connection",
   {"R_ges": "resistance|Gesamtwiderstand|Total resistance", "R1": "resistance|Widerstand 1|Resistor 1", "R2": "resistance|Widerstand 2|Resistor 2"}, auto=False)
EQ("el_parallel", C, S, "R_ges = R1*R2/(R1 + R2)", "Parallelschaltung", "Parallel connection",
   {"R_ges": "resistance|Gesamtwiderstand|Total resistance", "R1": "resistance|Widerstand 1|Resistor 1", "R2": "resistance|Widerstand 2|Resistor 2"}, auto=False)
EQ("el_divider", C, S, "U_2 = U*R2/(R1 + R2)", "Spannungsteiler", "Voltage divider",
   {"U_2": "voltage|Teilspannung an R2|Voltage across R2", "R1": "resistance|Widerstand 1|Resistor 1", "R2": "resistance|Widerstand 2|Resistor 2"}, auto=False)
S = "Felder, Kondensator, Spule"
EQ("el_cap", C, S, "C = Q/U", "Kapazität", "Capacitance", {"Q": "charge|Ladung|Charge"})
EQ("el_cap_plate", C, S, "C = eps0*eps_r*A/d", "Plattenkondensator", "Parallel-plate capacitor",
   {"eps_r": "number|Permittivitätszahl|Relative permittivity", "A": "area|Plattenfläche|Plate area", "d": "length|Plattenabstand|Plate distance"}, auto=False)
EQ("el_cap_energy", C, S, "E_C = 0.5*C*U**2", "Energie im Kondensator", "Capacitor energy", {"E_C": "energy|Feldenergie|Stored energy"})
EQ("el_rc", C, S, "tau_RC = R*C", "Zeitkonstante RC-Glied", "RC time constant", {"tau_RC": "time|Zeitkonstante|Time constant"})
EQ("el_ind_energy", C, S, "E_L = 0.5*L_i*I**2", "Energie in der Spule", "Inductor energy",
   {"E_L": "energy|Feldenergie|Stored energy", "L_i": "inductance|Induktivität|Inductance"})
EQ("el_coulomb", C, S, "F = q1*q2/(4*pi*eps0*r**2)", "Coulomb-Gesetz", "Coulomb's law",
   {"q1": "charge|Ladung 1|Charge 1", "q2": "charge|Ladung 2|Charge 2", "r": "length|Abstand|Distance"}, auto=False)
S = "Wechselstrom"
EQ("ac_XL", C, S, "X_L = 2*pi*f*L_i", "Induktiver Blindwiderstand", "Inductive reactance",
   {"X_L": "resistance|Induktiver Blindwiderstand|Inductive reactance", "L_i": "inductance|Induktivität|Inductance"})
EQ("ac_XC", C, S, "X_C = 1/(2*pi*f*C)", "Kapazitiver Blindwiderstand", "Capacitive reactance",
   {"X_C": "resistance|Kapazitiver Blindwiderstand|Capacitive reactance"})
EQ("ac_res", C, S, "f_0 = 1/(2*pi*sqrt(L_i*C))", "Resonanzfrequenz (Schwingkreis)", "Resonant frequency (LC)",
   {"f_0": "frequency|Resonanzfrequenz|Resonant frequency", "L_i": "inductance|Induktivität|Inductance"}, auto=False)
EQ("ac_rms", C, S, "U_eff = U_s/sqrt(2)", "Effektivwert (Sinus)", "RMS value (sine)",
   {"U_eff": "voltage|Effektivwert|RMS voltage", "U_s": "voltage|Scheitelwert|Peak voltage"}, auto=False)
EQ("ac_power", C, S, "P = U*I*cos(phi)", "Wirkleistung", "Real power", {"phi": "angle|Phasenverschiebung|Phase angle", "U": "voltage|Effektivspannung|RMS voltage", "I": "current|Effektivstrom|RMS current"}, auto=False)

# =============================================================================================== Optik
C, S = "Optik und Mikroskopie", "Licht"
EQ("opt_photon", C, S, "E_ph = hP*c0/lambda", "Photonenenergie", "Photon energy", {"E_ph": "energy|Photonenenergie|Photon energy"})
EQ("opt_photon_f", C, S, "E_ph = hP*f", "Photonenenergie aus Frequenz", "Photon energy from frequency", {"E_ph": "energy|Photonenenergie|Photon energy"}, auto=False)
EQ("opt_wavenumber", C, S, "nu_t = 1/lambda", "Wellenzahl", "Wavenumber", {"nu_t": "wavenumber|Wellenzahl|Wavenumber"})
EQ("opt_index", C, S, "n_r = c0/c_m", "Brechzahl", "Refractive index",
   {"n_r": "number|Brechzahl|Refractive index", "c_m": "velocity|Lichtgeschwindigkeit im Medium|Speed of light in medium"})
EQ("opt_snell", C, S, "n1*sin(alpha1) = n2*sin(alpha2)", "Brechungsgesetz (Snellius)", "Snell's law",
   {"n1": "number|Brechzahl 1|Refractive index 1", "alpha1": "angle|Einfallswinkel|Angle of incidence",
    "n2": "number|Brechzahl 2|Refractive index 2", "alpha2": "angle|Brechungswinkel|Angle of refraction"}, auto=False)
EQ("opt_brewster", C, S, "tan(theta_B) = n2/n1", "Brewster-Winkel", "Brewster angle",
   {"theta_B": "angle|Brewster-Winkel|Brewster angle", "n1": "number|Brechzahl 1|Refractive index 1", "n2": "number|Brechzahl 2|Refractive index 2"}, auto=False)
EQ("opt_total", C, S, "sin(theta_c) = n2/n1", "Grenzwinkel der Totalreflexion", "Critical angle",
   {"theta_c": "angle|Grenzwinkel|Critical angle", "n1": "number|Brechzahl dichteres Medium|Index, denser medium",
    "n2": "number|Brechzahl dünneres Medium|Index, less dense medium"}, auto=False)
EQ("opt_bragg", C, S, "n_b*lambda = 2*d_hkl*sin(theta)", "Bragg-Gleichung", "Bragg's law",
   {"n_b": "number|Beugungsordnung|Diffraction order", "d_hkl": "length|Netzebenenabstand|Lattice spacing",
    "theta": "angle|Bragg-Winkel|Bragg angle"}, auto=False)
EQ("opt_grating", C, S, "g_s*sin(theta) = n_b*lambda", "Beugungsgitter", "Diffraction grating",
   {"g_s": "length|Gitterkonstante|Grating period", "theta": "angle|Beugungswinkel|Diffraction angle",
    "n_b": "number|Beugungsordnung|Diffraction order"}, auto=False)
S = "Abbildung und Mikroskop"
EQ("opt_lens", C, S, "1/f_L = 1/g_o + 1/b_o", "Abbildungsgleichung (dünne Linse)", "Thin lens equation",
   {"f_L": "length|Brennweite|Focal length", "g_o": "length|Gegenstandsweite|Object distance", "b_o": "length|Bildweite|Image distance"}, auto=False)
EQ("opt_mag", C, S, "beta_m = b_o/g_o", "Abbildungsmassstab", "Magnification",
   {"beta_m": "number|Abbildungsmassstab|Magnification", "g_o": "length|Gegenstandsweite|Object distance", "b_o": "length|Bildweite|Image distance"}, auto=False)
EQ("opt_mag_total", C, S, "V_ges = V_obj*V_ok", "Gesamtvergrösserung Mikroskop", "Total magnification",
   {"V_ges": "number|Gesamtvergrösserung|Total magnification", "V_obj": "number|Objektivvergrösserung|Objective magnification",
    "V_ok": "number|Okularvergrösserung|Eyepiece magnification"})
EQ("opt_NA", C, S, "NA_o = n_r*sin(alpha_o)", "Numerische Apertur", "Numerical aperture",
   {"NA_o": "number|Numerische Apertur|Numerical aperture", "n_r": "number|Brechzahl Immersion|Immersion index",
    "alpha_o": "angle|Halber Öffnungswinkel|Half aperture angle"})
EQ("opt_abbe", C, S, "d_min = lambda/(2*NA_o)", "Auflösungsgrenze nach Abbe", "Abbe resolution limit",
   {"d_min": "length|Kleinster auflösbarer Abstand|Minimum resolvable distance", "NA_o": "number|Numerische Apertur|Numerical aperture"})
EQ("opt_rayleigh", C, S, "d_min = 0.61*lambda/NA_o", "Auflösung nach Rayleigh", "Rayleigh resolution",
   {"d_min": "length|Kleinster auflösbarer Abstand|Minimum resolvable distance", "NA_o": "number|Numerische Apertur|Numerical aperture"}, auto=False)
EQ("opt_dof", C, S, "d_tief = lambda*n_r/NA_o**2", "Schärfentiefe (wellenoptisch)", "Depth of field (wave optics)",
   {"d_tief": "length|Schärfentiefe|Depth of field", "n_r": "number|Brechzahl|Refractive index", "NA_o": "number|Numerische Apertur|Numerical aperture"}, auto=False)
EQ("opt_pixel", C, S, "s_px = p_cam/V_ges", "Pixelgrösse im Objekt", "Pixel size in the object",
   {"s_px": "length|Pixelgrösse im Objekt|Object pixel size", "p_cam": "length|Pixelgrösse der Kamera|Camera pixel pitch",
    "V_ges": "number|Vergrösserung bis zur Kamera|Magnification to camera"}, auto=False)
EQ("opt_nyquist", C, S, "s_px = d_min/2", "Nyquist-Abtastung", "Nyquist sampling",
   {"s_px": "length|Grösste zulässige Pixelgrösse|Largest pixel size", "d_min": "length|Auflösung|Resolution"}, auto=False)

# =============================================================================================== Chemie
C, S = "Chemie", "Stoffmenge und Konzentration"
EQ("ch_amount", C, S, "n = m/M", "Stoffmenge", "Amount of substance")
EQ("ch_conc", C, S, "c = n/V", "Stoffmengenkonzentration", "Molar concentration", {"c": "concentration|Konzentration|Concentration"})
EQ("ch_mass_conc", C, S, "beta = m/V", "Massenkonzentration", "Mass concentration", {"beta": "mass_conc|Massenkonzentration|Mass concentration"}, auto=False)
EQ("ch_dilution", C, S, "c1*V1 = c2*V2", "Verdünnung", "Dilution",
   {"c1": "concentration|Konzentration 1|Concentration 1", "V1": "volume|Volumen 1|Volume 1",
    "c2": "concentration|Konzentration 2|Concentration 2", "V2": "volume|Volumen 2|Volume 2"}, auto=False)
EQ("ch_particles", C, S, "N_T = n*NA", "Teilchenzahl", "Number of particles", {"N_T": "number|Teilchenzahl|Number of particles"})
EQ("ch_massfrac", C, S, "w_m = m_i/m", "Massenanteil", "Mass fraction",
   {"w_m": "number|Massenanteil|Mass fraction", "m_i": "mass|Masse der Komponente|Component mass", "m": "mass|Gesamtmasse|Total mass"}, auto=False)
S = "Säuren und Basen"
EQ("ch_pH", C, S, "pH = -log10(c_H/c_std)", "pH-Wert", "pH value", {"pH": "number|pH-Wert|pH", "c_H": "concentration|Oxoniumkonzentration|H₃O⁺ concentration"})
EQ("ch_pOH", C, S, "pH + pOH = 14", "pH und pOH (25 °C)", "pH and pOH (25 °C)", {"pH": "number|pH-Wert|pH", "pOH": "number|pOH-Wert|pOH"}, auto=False,
   note="setzt pKw = 14 voraus, also Wasser bei 25 °C; bei anderer Temperatur „pH und pOH (pKw)“ mit dem pKw dieser Temperatur verwenden",
   note_en="assumes pKw = 14, i.e. water at 25 °C; at other temperatures use “pH and pOH (pKw)” with the pKw of that temperature")
EQ("ch_pOH_pKw", C, S, "pH + pOH = pKw", "pH und pOH (pKw)", "pH and pOH (pKw)",
   {"pH": "number|pH-Wert|pH", "pOH": "number|pOH-Wert|pOH", "pKw": "number|pKw (14,00 bei 25 °C)|pKw (14.00 at 25 °C)"},
   auto=False, note="pKw nimmt mit steigender Temperatur ab; Wert für die Temperatur der Lösung aus einer Tabelle einsetzen",
   note_en="pKw decreases with rising temperature; insert the tabulated value for the solution temperature")
EQ("ch_hh", C, S, "pH = pKa + log10(c_A/c_HA)", "Henderson-Hasselbalch (Puffer)", "Henderson–Hasselbalch (buffer)",
   {"pH": "number|pH-Wert|pH", "pKa": "number|pKs-Wert|pKa", "c_A": "concentration|Konzentration Base|Base concentration",
    "c_HA": "concentration|Konzentration Säure|Acid concentration"}, auto=False)
_PH = "number|pH-Wert|pH"
_PKA = "number|pKs-Wert|pKa"
_PKB = "number|pKb-Wert|pKb"
_PKW = "number|pKw (14,00 bei 25 °C)|pKw (14.00 at 25 °C)"
_CA = "concentration|Anfangskonzentration Säure|Initial acid concentration"
_CB = "concentration|Anfangskonzentration Base|Initial base concentration"
EQ("ch_pKa", C, S, "pKa = -log10(K_a)", "pKs aus der Säurekonstante", "pKa from the acid constant",
   {"pKa": _PKA, "K_a": "number|Säurekonstante Ks (auf c° = 1 mol/L bezogen)|Acid constant Ka (relative to c° = 1 mol/L)"})
EQ("ch_pKw", C, S, "pKa + pKb = pKw", "Korrespondierendes Säure-Base-Paar", "Conjugate acid–base pair",
   {"pKa": _PKA, "pKb": _PKB, "pKw": _PKW}, auto=False, note="pKw = 14,00 bei 25 °C; temperaturabhängig")
EQ("ch_strong_acid", C, S, "pH = -log10(c_a/c_std)", "pH einer starken Säure", "pH of a strong acid",
   {"pH": _PH, "c_a": _CA}, auto=False, note="vollständige Protolyse; gilt für c ≫ 10⁻⁷ mol/L")
EQ("ch_strong_base", C, S, "pH = pKw + log10(c_b/c_std)", "pH einer starken Base", "pH of a strong base",
   {"pH": _PH, "pKw": _PKW, "c_b": _CB}, auto=False, note="vollständige Protolyse; gilt für c ≫ 10⁻⁷ mol/L")
EQ("ch_weak_acid", C, S, "pH = 0.5*(pKa - log10(c_a/c_std))", "pH einer schwachen Säure (Näherung)", "pH of a weak acid (approximation)",
   {"pH": _PH, "pKa": _PKA, "c_a": _CA}, auto=False,
   note="Näherung für geringe Protolyse (c/Ks > 100); sonst die exakte Formel verwenden")
EQ("ch_weak_acid_exact", C, S, "pH = -log10((sqrt(10**(-2*pKa) + 4*10**(-pKa)*c_a/c_std) - 10**(-pKa))/2)",
   "pH einer schwachen Säure (exakt, quadratisch)", "pH of a weak acid (exact, quadratic)",
   {"pH": _PH, "pKa": _PKA, "c_a": _CA}, auto=False,
   note="aus Ks = x²/(c − x); Autoprotolyse des Wassers vernachlässigt (gilt bis etwa pH 6)")
EQ("ch_weak_base", C, S, "pH = pKw - 0.5*(pKb - log10(c_b/c_std))", "pH einer schwachen Base (Näherung)", "pH of a weak base (approximation)",
   {"pH": _PH, "pKb": _PKB, "pKw": _PKW, "c_b": _CB}, auto=False, note="Näherung für geringe Protolyse (c/Kb > 100)")
EQ("ch_weak_base_exact", C, S, "pH = pKw + log10((sqrt(10**(-2*pKb) + 4*10**(-pKb)*c_b/c_std) - 10**(-pKb))/2)",
   "pH einer schwachen Base (exakt, quadratisch)", "pH of a weak base (exact, quadratic)",
   {"pH": _PH, "pKb": _PKB, "pKw": _PKW, "c_b": _CB}, auto=False, note="aus Kb = x²/(c − x); Autoprotolyse vernachlässigt")
EQ("ch_alpha", C, S, "alpha_d = 1/(1 + 10**(pKa - pH))", "Protolysegrad (Anteil A⁻)", "Degree of dissociation (fraction A⁻)",
   {"alpha_d": "number|Protolysegrad|Degree of dissociation", "pKa": _PKA, "pH": _PH}, auto=False)
EQ("ch_ostwald", C, S, "K_a = alpha_d**2*c_a/((1 - alpha_d)*c_std)", "Ostwaldsches Verdünnungsgesetz", "Ostwald's dilution law",
   {"K_a": "number|Säurekonstante Ks (auf c° bezogen)|Acid constant Ka (relative to c°)", "alpha_d": "number|Protolysegrad|Degree of dissociation",
    "c_a": _CA}, auto=False, src="atkins")
EQ("ch_buffer_cap", C, S, "beta_p = ln(10)*c_t*10**(-pKa)*10**(-pH)/(10**(-pKa) + 10**(-pH))**2", "Pufferkapazität", "Buffer capacity",
   {"beta_p": "concentration|Pufferkapazität (je pH-Einheit)|Buffer capacity (per pH unit)",
    "c_t": "concentration|Gesamtkonzentration des Puffers|Total buffer concentration", "pKa": _PKA, "pH": _PH}, auto=False,
   note="nur der Beitrag des Puffers; Beiträge von H₃O⁺ und OH⁻ vernachlässigt; grösste Kapazität bei pH = pKs")
EQ("ch_ampholyte", C, S, "pH = (pKa1 + pKa2)/2", "pH eines Ampholyten (z. B. HCO₃⁻)", "pH of an ampholyte (e.g. HCO₃⁻)",
   {"pH": _PH, "pKa1": "number|pKs1|pKa1", "pKa2": "number|pKs2|pKa2"}, auto=False, note="Näherung für nicht zu verdünnte Lösungen")
EQ("ch_diprotic", C, S, "alpha_1 = 1/(1 + 10**(pKa1 - pH) + 10**(pH - pKa2))", "Zweiprotonige Säure: Anteil HA⁻", "Diprotic acid: fraction HA⁻",
   {"alpha_1": "number|Anteil HA⁻|Fraction HA⁻", "pKa1": "number|pKs1|pKa1", "pKa2": "number|pKs2|pKa2", "pH": _PH}, auto=False)
EQ("ch_equiv_weak", C, S, "pH = 0.5*(pKw + pKa + log10(c_s/c_std))", "pH am Äquivalenzpunkt (schwache Säure, starke Base)",
   "pH at equivalence (weak acid, strong base)",
   {"pH": _PH, "pKw": _PKW, "pKa": _PKA, "c_s": "concentration|Salzkonzentration am Äquivalenzpunkt|Salt concentration at equivalence"},
   auto=False)
EQ("ch_titration", C, S, "c_a*V_a = c_b*V_b", "Titration: Äquivalenzpunkt (1:1)", "Titration: equivalence point (1:1)",
   {"c_a": "concentration|Konzentration Säure|Acid concentration", "V_a": "volume|Volumen Säure|Acid volume",
    "c_b": "concentration|Konzentration Base|Base concentration", "V_b": "volume|Volumen Base bis zum Äquivalenzpunkt|Base volume at equivalence"},
   auto=False)
S = "Löslichkeit und Gleichgewicht"
_KSP = "number|Löslichkeitsprodukt (auf c° bezogen)|Solubility product (relative to c°)"
EQ("ch_ksp_11", C, S, "s_l = c_std*sqrt(K_sp)", "Löslichkeit eines 1:1-Salzes (AB)", "Solubility of a 1:1 salt (AB)",
   {"s_l": "concentration|Löslichkeit|Solubility", "K_sp": _KSP}, auto=False, note="ohne Fremdionen und Komplexbildung")
EQ("ch_ksp_xy", C, S, "K_sp = nu_x**nu_x*nu_y**nu_y*(s_l/c_std)**(nu_x + nu_y)", "Löslichkeitsprodukt AₓBᵧ", "Solubility product AₓBᵧ",
   {"K_sp": _KSP, "nu_x": "number|Anzahl Kationen x|Number of cations x", "nu_y": "number|Anzahl Anionen y|Number of anions y",
    "s_l": "concentration|Löslichkeit|Solubility"}, auto=False, note="z. B. CaF₂: x = 1, y = 2")
EQ("ch_pKsp", C, S, "pKsp = -log10(K_sp)", "pKL aus dem Löslichkeitsprodukt", "pKsp from the solubility product",
   {"pKsp": "number|pKL-Wert|pKsp", "K_sp": _KSP}, auto=False)
EQ("ch_Kc_Kp", C, S, "K_p = K_c*(c_std*Rgas*T/p_std)**dnu", "Kp und Kc (ideale Gase)", "Kp and Kc (ideal gases)",
   {"K_p": "number|Kp (auf p° = 1 bar bezogen)|Kp (relative to p° = 1 bar)", "K_c": "number|Kc (auf c° bezogen)|Kc (relative to c°)",
    "dnu": "number|Δν (Gasmoleküle Produkte − Edukte)|Δν (gas molecules products − reactants)"}, auto=False, src="atkins")
S = "Thermodynamik"
_DG = "reaction_energy|Freie Reaktionsenthalpie ΔG|Reaction Gibbs energy ΔG"
_DH = "reaction_energy|Reaktionsenthalpie ΔH|Reaction enthalpy ΔH"
_DS = "molar_entropy|Reaktionsentropie ΔS|Reaction entropy ΔS"
_DG0 = "reaction_energy|Freie Standardreaktionsenthalpie ΔG°|Standard reaction Gibbs energy ΔG°"
_KEQ = "number|Gleichgewichtskonstante K|Equilibrium constant K"
EQ("ch_gibbs", C, S, "dG = dH - T*dS", "Freie Enthalpie (ΔG = ΔH − TΔS)", "Gibbs energy (ΔG = ΔH − TΔS)",
   {"dG": _DG, "dH": _DH, "dS": _DS}, note="ΔG < 0: Reaktion läuft freiwillig ab (konstanter Druck und Temperatur)")
EQ("ch_T_switch", C, S, "T_u = dH/dS", "Umschlagtemperatur (ΔG = 0)", "Crossover temperature (ΔG = 0)",
   {"T_u": "temperature|Temperatur mit ΔG = 0|Temperature where ΔG = 0", "dH": _DH, "dS": _DS}, auto=False,
   note="ΔH und ΔS als temperaturunabhängig angenommen")
EQ("ch_dG_K", C, S, "dG_0 = -Rgas*T*ln(K_eq)", "ΔG° und Gleichgewichtskonstante", "ΔG° and equilibrium constant",
   {"dG_0": _DG0, "K_eq": _KEQ})
EQ("ch_dG_Q", C, S, "dG = dG_0 + Rgas*T*ln(Q_r)", "ΔG bei beliebiger Zusammensetzung", "ΔG at any composition",
   {"dG": _DG, "dG_0": _DG0, "Q_r": "number|Reaktionsquotient|Reaction quotient"}, auto=False)
EQ("ch_vanthoff", C, S, "ln(K_2/K_1) = -dH/Rgas*(1/T2 - 1/T1)", "Van-'t-Hoff-Gleichung", "Van 't Hoff equation",
   {"K_1": "number|K bei T₁|K at T₁", "K_2": "number|K bei T₂|K at T₂", "dH": _DH,
    "T1": "temperature|Temperatur 1|Temperature 1", "T2": "temperature|Temperatur 2|Temperature 2"}, auto=False,
   note="ΔH im Bereich konstant")
EQ("ch_clausius", C, S, "ln(p2/p1) = -dH_v/Rgas*(1/T2 - 1/T1)", "Clausius-Clapeyron (Dampfdruck)", "Clausius–Clapeyron (vapour pressure)",
   {"p1": "pressure|Dampfdruck bei T₁|Vapour pressure at T₁", "p2": "pressure|Dampfdruck bei T₂|Vapour pressure at T₂",
    "dH_v": "molar_energy|Verdampfungsenthalpie|Enthalpy of vaporisation",
    "T1": "temperature|Temperatur 1|Temperature 1", "T2": "temperature|Temperatur 2|Temperature 2"}, auto=False)
EQ("ch_heat_rxn", C, S, "Q = -xi*dH", "Wärmeumsatz einer Reaktion", "Heat of a reaction",
   {"Q": "energy|Abgegebene Wärme (positiv = exotherm)|Heat released (positive = exothermic)",
    "xi": "amount|Reaktionslaufzahl ξ (Formelumsätze)|Extent of reaction ξ", "dH": _DH}, auto=False,
   note="ΔH < 0: exotherm, Wärme wird frei")
EQ("ch_kirchhoff", C, S, "dH_2 = dH_1 + dCp*(T2 - T1)", "Kirchhoffsches Gesetz (ΔH bei anderer Temperatur)", "Kirchhoff's law (ΔH at another temperature)",
   {"dH_2": "reaction_energy|ΔH bei T₂|ΔH at T₂", "dH_1": "reaction_energy|ΔH bei T₁|ΔH at T₁",
    "dCp": "molar_entropy|ΔCp der Reaktion|ΔCp of the reaction", "T1": "temperature|Temperatur 1|Temperature 1",
    "T2": "temperature|Temperatur 2|Temperature 2"}, auto=False, note="ΔCp im Bereich konstant")
S = "Elektrochemie"
EQ("ch_dG_E", C, S, "dG_0 = -z_e*F_c*U_0", "ΔG° aus der Standardzellspannung", "ΔG° from the standard cell potential",
   {"dG_0": _DG0, "z_e": "number|Zahl übertragener Elektronen|Electrons transferred", "U_0": "voltage|Standardzellspannung|Standard cell potential"})
EQ("ch_K_E", C, S, "U_0 = Rgas*T/(z_e*F_c)*ln(K_eq)", "Standardzellspannung und Gleichgewichtskonstante", "Standard potential and equilibrium constant",
   {"U_0": "voltage|Standardzellspannung|Standard cell potential", "z_e": "number|Zahl übertragener Elektronen|Electrons transferred",
    "K_eq": _KEQ}, auto=False)
EQ("ch_cell", C, S, "U_z = U_K - U_A", "Zellspannung (Kathode − Anode)", "Cell potential (cathode − anode)",
   {"U_z": "voltage|Zellspannung|Cell potential", "U_K": "voltage|Potential Kathode (Reduktion)|Cathode potential (reduction)",
    "U_A": "voltage|Potential Anode (Oxidation)|Anode potential (oxidation)"}, auto=False, note="U > 0: Zelle liefert Strom (freiwillig)")
S = "Kolligative Eigenschaften"
_BM = "molality|Molalität des Gelösten|Molality of solute"
_IVH = "number|Van-'t-Hoff-Faktor i (Teilchen je Formeleinheit)|van 't Hoff factor i"
EQ("ch_molality", C, S, "b_m = n/m_lm", "Molalität", "Molality",
   {"b_m": _BM, "n": "amount|Stoffmenge des Gelösten|Amount of solute", "m_lm": "mass|Masse des Lösungsmittels|Mass of solvent"}, src="greenbook")
EQ("ch_molfrac", C, S, "x_i = n_i/n_ges", "Stoffmengenanteil", "Mole fraction",
   {"x_i": "number|Stoffmengenanteil|Mole fraction", "n_i": "amount|Stoffmenge der Komponente|Amount of component",
    "n_ges": "amount|Gesamtstoffmenge|Total amount"}, auto=False, src="greenbook")
EQ("ch_raoult", C, S, "p_A = x_A*p_A0", "Raoultsches Gesetz", "Raoult's law",
   {"p_A": "pressure|Dampfdruck über der Lösung|Vapour pressure over solution", "x_A": "number|Stoffmengenanteil Lösungsmittel|Mole fraction of solvent",
    "p_A0": "pressure|Dampfdruck reines Lösungsmittel|Vapour pressure of pure solvent"}, auto=False)
EQ("ch_bp", C, S, "dT_b = i_vh*K_b*b_m", "Siedepunktserhöhung", "Boiling-point elevation",
   {"dT_b": "temp_diff|Siedepunktserhöhung|Boiling-point elevation", "i_vh": _IVH,
    "K_b": "cryo_const|Ebullioskopische Konstante|Ebullioscopic constant", "b_m": _BM}, auto=False,
   note="Wasser: K_b = 0,51 K·kg/mol; verdünnte Lösungen")
EQ("ch_fp", C, S, "dT_f = i_vh*K_f*b_m", "Gefrierpunktserniedrigung", "Freezing-point depression",
   {"dT_f": "temp_diff|Gefrierpunktserniedrigung|Freezing-point depression", "i_vh": _IVH,
    "K_f": "cryo_const|Kryoskopische Konstante|Cryoscopic constant", "b_m": _BM}, auto=False,
   note="Wasser: K_f = 1,86 K·kg/mol; verdünnte Lösungen")
EQ("ch_osmotic", C, S, "Pi_o = i_vh*c*Rgas*T", "Osmotischer Druck (van 't Hoff)", "Osmotic pressure (van 't Hoff)",
   {"Pi_o": "pressure|Osmotischer Druck|Osmotic pressure", "i_vh": _IVH, "c": "concentration|Konzentration des Gelösten|Solute concentration"},
   auto=False, note="verdünnte Lösungen")
S = "Radioaktivität"
_LD = "rate_const|Zerfallskonstante λ|Decay constant λ"
_TH = "time|Halbwertszeit|Half-life"
EQ("nuc_decay", C, S, "N_t = N_0*exp(-lambda_d*t)", "Zerfallsgesetz", "Radioactive decay law",
   {"N_t": "number|Anzahl Kerne zur Zeit t|Nuclei at time t", "N_0": "number|Anfangszahl der Kerne|Initial number of nuclei", "lambda_d": _LD})
EQ("nuc_halflife", C, S, "T_half = ln(2)/lambda_d", "Halbwertszeit und Zerfallskonstante", "Half-life and decay constant",
   {"T_half": _TH, "lambda_d": _LD})
EQ("nuc_mean_life", C, S, "tau_m = 1/lambda_d", "Mittlere Lebensdauer", "Mean lifetime",
   {"tau_m": "time|Mittlere Lebensdauer|Mean lifetime", "lambda_d": _LD}, auto=False)
EQ("nuc_activity", C, S, "A_act = lambda_d*N_t", "Aktivität", "Activity",
   {"A_act": "activity|Aktivität|Activity", "lambda_d": _LD, "N_t": "number|Anzahl Kerne|Number of nuclei"})
EQ("nuc_activity_t", C, S, "A_act = A_0*exp(-ln(2)*t/T_half)", "Aktivität nach der Zeit t", "Activity after time t",
   {"A_act": "activity|Aktivität zur Zeit t|Activity at time t", "A_0": "activity|Anfangsaktivität|Initial activity", "T_half": _TH}, auto=False)
EQ("nuc_remaining", C, S, "w_r = 0.5**(t/T_half)", "Verbleibender Anteil nach der Zeit t", "Fraction remaining after time t",
   {"w_r": "number|Verbleibender Anteil|Fraction remaining", "T_half": _TH}, auto=False)
EQ("nuc_mass_act", C, S, "A_act = ln(2)*m*NA/(M*T_half)", "Aktivität aus der Masse eines Nuklids", "Activity from the mass of a nuclide",
   {"A_act": "activity|Aktivität|Activity", "m": "mass|Masse des Nuklids|Mass of nuclide", "M": "molar_mass|Molare Masse des Nuklids|Molar mass of nuclide",
    "T_half": _TH}, auto=False)
EQ("nuc_spec_act", C, S, "a_s = ln(2)*NA/(M*T_half)", "Spezifische Aktivität eines reinen Nuklids", "Specific activity of a pure nuclide",
   {"a_s": "spec_activity|Spezifische Aktivität|Specific activity", "M": "molar_mass|Molare Masse des Nuklids|Molar mass of nuclide",
    "T_half": _TH}, auto=False)
EQ("nuc_mass_defect", C, S, "E_B = dm_B*c0**2", "Bindungsenergie aus dem Massendefekt", "Binding energy from the mass defect",
   {"E_B": "energy|Bindungsenergie|Binding energy", "dm_B": "mass|Massendefekt|Mass defect"}, auto=False,
   note="Massendefekt in u: 1 u·c² = 931,494 MeV")
S = "Kinetik und Spektroskopie"
EQ("ch_arrhenius", C, S, "k_r = A_r*exp(-E_a/(Rgas*T))", "Arrhenius-Gleichung", "Arrhenius equation",
   {"k_r": "rate_const|Geschwindigkeitskonstante|Rate constant", "A_r": "rate_const|Präexponentieller Faktor|Pre-exponential factor",
    "E_a": "molar_energy|Aktivierungsenergie|Activation energy"}, auto=False)
EQ("ch_first", C, S, "c = c_0*exp(-k_r*t)", "Reaktion 1. Ordnung", "First-order reaction",
   {"c": "concentration|Konzentration|Concentration", "c_0": "concentration|Anfangskonzentration|Initial concentration",
    "k_r": "rate_const|Geschwindigkeitskonstante|Rate constant"}, auto=False)
EQ("ch_halflife", C, S, "t_half = ln(2)/k_r", "Halbwertszeit (1. Ordnung)", "Half-life (first order)",
   {"t_half": "time|Halbwertszeit|Half-life", "k_r": "rate_const|Geschwindigkeitskonstante|Rate constant"})
EQ("ch_zero", C, S, "c = c_0 - k_0*t", "Reaktion 0. Ordnung", "Zero-order reaction",
   {"c": "concentration|Konzentration|Concentration", "c_0": "concentration|Anfangskonzentration|Initial concentration",
    "k_0": "rate_const0|Geschwindigkeitskonstante 0. Ordnung|Zero-order rate constant"}, auto=False)
EQ("ch_halflife0", C, S, "t_half = c_0/(2*k_0)", "Halbwertszeit (0. Ordnung)", "Half-life (zero order)",
   {"t_half": "time|Halbwertszeit|Half-life", "c_0": "concentration|Anfangskonzentration|Initial concentration",
    "k_0": "rate_const0|Geschwindigkeitskonstante 0. Ordnung|Zero-order rate constant"}, auto=False)
EQ("ch_second", C, S, "1/c = 1/c_0 + k_2*t", "Reaktion 2. Ordnung (A + A, gleiche Konzentrationen)", "Second-order reaction",
   {"c": "concentration|Konzentration|Concentration", "c_0": "concentration|Anfangskonzentration|Initial concentration",
    "k_2": "rate_const2|Geschwindigkeitskonstante 2. Ordnung|Second-order rate constant"}, auto=False)
EQ("ch_halflife2", C, S, "t_half = 1/(k_2*c_0)", "Halbwertszeit (2. Ordnung)", "Half-life (second order)",
   {"t_half": "time|Halbwertszeit|Half-life", "c_0": "concentration|Anfangskonzentration|Initial concentration",
    "k_2": "rate_const2|Geschwindigkeitskonstante 2. Ordnung|Second-order rate constant"}, auto=False)
EQ("ch_arrh2", C, S, "ln(k_T2/k_T1) = -E_a/Rgas*(1/T2 - 1/T1)", "Arrhenius aus zwei Temperaturen", "Arrhenius from two temperatures",
   {"k_T1": "rate_const|k bei T₁|k at T₁", "k_T2": "rate_const|k bei T₂|k at T₂", "E_a": "molar_energy|Aktivierungsenergie|Activation energy",
    "T1": "temperature|Temperatur 1|Temperature 1", "T2": "temperature|Temperatur 2|Temperature 2"}, auto=False,
   note="Aktivierungsenergie aus zwei gemessenen Geschwindigkeitskonstanten; folgt nicht aus der Reaktionsgleichung")
EQ("ch_eyring", C, S, "k_r = kB*T/hP*exp(-dG_a/(Rgas*T))", "Eyring-Gleichung (Theorie des Übergangszustands)", "Eyring equation (transition state theory)",
   {"k_r": "rate_const|Geschwindigkeitskonstante|Rate constant", "dG_a": "molar_energy|Freie Aktivierungsenthalpie ΔG‡|Gibbs energy of activation ΔG‡"},
   auto=False, note="Transmissionskoeffizient 1; k für eine Reaktion 1. Ordnung")
EQ("ch_beer", C, S, "A_abs = eps_m*c*l_s", "Lambert-Beer-Gesetz", "Beer–Lambert law",
   {"A_abs": "number|Extinktion|Absorbance", "eps_m": "molar_abs|Molarer Extinktionskoeffizient|Molar absorptivity",
    "c": "concentration|Konzentration|Concentration", "l_s": "length|Schichtdicke|Path length"})
EQ("ch_transm", C, S, "A_abs = -log10(T_r)", "Extinktion aus Transmission", "Absorbance from transmittance",
   {"A_abs": "number|Extinktion|Absorbance", "T_r": "number|Transmissionsgrad|Transmittance"})
EQ("ch_faraday", C, S, "m = M*I*t/(z_e*F_c)", "Faradaysches Gesetz (Elektrolyse)", "Faraday's law of electrolysis",
   {"z_e": "number|Ladungszahl|Charge number", "m": "mass|Abgeschiedene Masse|Deposited mass"}, auto=False)
EQ("ch_faraday_eta", C, S, "m = eta_I*M*I*t/(z_e*F_c)", "Faradaysches Gesetz mit Stromausbeute",
   "Faraday's law with current efficiency",
   {"eta_I": "number|Stromausbeute (0–1)|Current efficiency (0–1)", "z_e": "number|Ladungszahl|Charge number",
    "m": "mass|Abgeschiedene Masse|Deposited mass"}, auto=False)
EQ("ch_el_yield", C, S, "Y_el = m_exp/m_th", "Ausbeute der Elektrolyse", "Electrolysis yield",
   {"Y_el": "number|Ausbeute|Yield", "m_exp": "mass|Gemessene Masse|Measured mass",
    "m_th": "mass|Theoretische Masse (η = 1)|Theoretical mass (η = 1)"})
EQ("ch_nernst", C, S, "U = U_0 - Rgas*T/(z_e*F_c)*ln(Q_r)", "Nernst-Gleichung", "Nernst equation",
   {"U": "voltage|Elektrodenpotential|Electrode potential", "U_0": "voltage|Standardpotential|Standard potential",
    "z_e": "number|Ladungszahl|Charge number", "Q_r": "number|Reaktionsquotient|Reaction quotient"}, auto=False)
EQ("ch_diff_arrh", C, S, "D_c = D_0*exp(-Q_a/(Rgas*T))", "Diffusionskoeffizient (Arrhenius)", "Diffusion coefficient (Arrhenius)",
   {"D_c": "diffusivity|Diffusionskoeffizient|Diffusion coefficient", "D_0": "diffusivity|Frequenzfaktor|Pre-exponential factor",
    "Q_a": "molar_energy|Aktivierungsenergie|Activation energy"}, auto=False)
EQ("ch_diff_len", C, S, "x_d = sqrt(D_c*t)", "Diffusionslänge", "Diffusion length",
   {"x_d": "length|Diffusionslänge|Diffusion length", "D_c": "diffusivity|Diffusionskoeffizient|Diffusion coefficient"}, auto=False)

S = "Laborpraxis und grüne Kennzahlen"
EQ("lab_E_factor", C, S, "E_f = (m_in - m_P)/m_P", "E-Faktor", "E-factor",
   {"E_f": "number|E-Faktor|E-factor", "m_in": "mass|Eingesetzte Masse (Zählgrenze angeben)|Mass input (state the boundary)",
    "m_P": "mass|Produktmasse|Product mass"}, note="Abfall je Produktmasse; Zählgrenze (Lösungsmittel, Aufarbeitung) mit angeben")
EQ("lab_PMI", C, S, "PMI = m_in/m_P", "Prozessmassenintensität", "Process mass intensity",
   {"PMI": "number|PMI|PMI", "m_in": "mass|Eingesetzte Masse|Mass input", "m_P": "mass|Produktmasse|Product mass"},
   note="PMI = E-Faktor + 1 bei gleicher Zählgrenze")
EQ("lab_RME", C, S, "RME = m_P/m_reac", "Reaktionsmasseneffizienz", "Reaction mass efficiency",
   {"RME": "number|RME|RME", "m_P": "mass|Produktmasse|Product mass",
    "m_reac": "mass|Masse aller Edukte (inkl. Überschuss)|Mass of all reactants (incl. excess)"})
EQ("lab_yield", C, S, "Y_r = n_P/(nu_P*xi_lim)", "Ausbeute aus dem limitierenden Edukt", "Yield from the limiting reactant",
   {"Y_r": "number|Ausbeute|Yield", "n_P": "amount|Isolierte Stoffmenge Produkt|Isolated amount of product",
    "nu_P": "number|Stöchiometriezahl Produkt|Stoichiometric number of product",
    "xi_lim": "amount|Umsatzvariable des limitierenden Edukts n/ν|Extent from limiting reactant n/ν"})
EQ("lab_mix", C, S, "c_m*V_m = c_1*V_1 + c_2*V_2", "Mischungsrechnung (Stoffbilanz, aufgefüllt)", "Mixing (mass balance, made up)",
   {"c_m": "concentration|Endkonzentration|Final concentration", "V_m": "volume|Endvolumen (aufgefüllt)|Final volume (made up)",
    "c_1": "concentration|Konzentration 1|Concentration 1", "V_1": "volume|Volumen 1|Volume 1",
    "c_2": "concentration|Konzentration 2|Concentration 2", "V_2": "volume|Volumen 2|Volume 2"}, auto=False,
   note="V_m ist das aufgefüllte Endvolumen, nicht V_1 + V_2")

# =============================================================================================== Werkstoffkunde
# Werkstoffkennwerte dazu liefert die Werkstoffdatenbank: mat("Cu", "E"), E_mat("1.4301"), D_diff("C", "γ-Fe", T) …
C, S = "Werkstoffkunde", "Kristallographie"
_LG = "length|Gitterkonstante|Lattice parameter"
_RA = "length|Atomradius|Atomic radius"
_TH = "angle|Beugungswinkel θ (halber Streuwinkel)|Bragg angle θ (half the scattering angle)"
EQ("wk_a_fcc", C, S, "a_g = 2*sqrt(2)*r_at", "Gitterkonstante kfz aus dem Atomradius", "Lattice parameter FCC from atomic radius",
   {"a_g": _LG, "r_at": _RA}, auto=False)
EQ("wk_a_bcc", C, S, "a_g = 4*r_at/sqrt(3)", "Gitterkonstante krz aus dem Atomradius", "Lattice parameter BCC from atomic radius",
   {"a_g": _LG, "r_at": _RA}, auto=False)
EQ("wk_rho_th", C, S, "rho = n_at*M/(a_g**3*NA)", "Theoretische Dichte (kubische Zelle)", "Theoretical density (cubic cell)",
   {"n_at": "number|Atome je Elementarzelle|Atoms per unit cell", "a_g": _LG, "M": "molar_mass|Molare Masse|Molar mass"},
   auto=False, note="kfz: n = 4, krz: n = 2, kubisch primitiv: n = 1")
EQ("wk_apf", C, S, "APF = n_at*4/3*pi*r_at**3/a_g**3", "Packungsdichte (kubische Zelle)", "Atomic packing factor (cubic cell)",
   {"APF": "number|Packungsdichte|Atomic packing factor", "n_at": "number|Atome je Elementarzelle|Atoms per unit cell",
    "r_at": _RA, "a_g": _LG}, auto=False, note="kfz 0,74; krz 0,68")
EQ("wk_d_hkl", C, S, "d_hkl = a_g/sqrt(h_i**2 + k_i**2 + l_i**2)", "Netzebenenabstand (kubisch)", "Interplanar spacing (cubic)",
   {"d_hkl": "length|Netzebenenabstand|Interplanar spacing", "a_g": _LG, "h_i": "number|Miller-Index h|Miller index h",
    "k_i": "number|Miller-Index k|Miller index k", "l_i": "number|Miller-Index l|Miller index l"}, auto=False)
EQ("wk_bragg", C, S, "d_hkl = n_o*lambda/(2*sin(theta))", "Bragg-Gleichung", "Bragg's law",
   {"d_hkl": "length|Netzebenenabstand|Interplanar spacing", "n_o": "number|Beugungsordnung|Order of diffraction",
    "lambda": "length|Wellenlänge der Strahlung|Wavelength of the radiation", "theta": _TH}, note="n·λ = 2·d·sin θ")
EQ("wk_hex_V", C, S, "V_c = 3*sqrt(3)/2*a_g**2*c_g", "Volumen der hexagonalen Elementarzelle", "Volume of the hexagonal unit cell",
   {"V_c": "volume|Zellvolumen|Cell volume", "a_g": "length|Gitterkonstante a|Lattice parameter a",
    "c_g": "length|Gitterkonstante c|Lattice parameter c"}, auto=False)
EQ("wk_scherrer", C, S, "D_s = K_s*lambda/(beta_s*cos(theta))", "Scherrer-Gleichung (Kristallitgrösse)", "Scherrer equation (crystallite size)",
   {"D_s": "length|Kristallitgrösse|Crystallite size", "K_s": "number|Formfaktor (≈ 0,9)|Shape factor (≈ 0.9)",
    "lambda": "length|Wellenlänge der Strahlung|Wavelength of the radiation",
    "beta_s": "angle|Linienverbreiterung (Halbwertsbreite)|Line broadening (FWHM)", "theta": _TH}, auto=False, src="cullity",
   note="β nach Abzug der Geräteverbreiterung, im Bogenmass")

S = "Defekte und Diffusion"
_DC = "diffusivity|Diffusionskoeffizient|Diffusion coefficient"
EQ("wk_vacancy", C, S, "N_v = N_s*exp(-Q_v/(Rgas*T))", "Leerstellenkonzentration im Gleichgewicht", "Equilibrium vacancy concentration",
   {"N_v": "number_conc|Leerstellen je Volumen|Vacancies per volume", "N_s": "number_conc|Gitterplätze je Volumen|Lattice sites per volume",
    "Q_v": "molar_energy|Bildungsenergie der Leerstellen (je Mol)|Vacancy formation energy (per mole)"}, auto=False,
   note="Bildungsenergie je Leerstelle in eV: Q_v = E·N_A (1 eV je Leerstelle ≈ 96,5 kJ/mol)")
EQ("wk_sites", C, S, "N_s = NA*rho/M", "Gitterplätze (Atome) je Volumen", "Atomic sites per volume",
   {"N_s": "number_conc|Atome je Volumen|Atoms per volume"}, auto=False)
EQ("wk_fick1", C, S, "J_d = -D_c*(C_2 - C_1)/(x_2 - x_1)", "1. Ficksches Gesetz (stationär, lineares Profil)",
   "Fick's first law (steady state, linear profile)",
   {"J_d": "diff_flux|Diffusionsstromdichte|Diffusion flux", "D_c": _DC, "C_1": "mass_conc|Konzentration bei x₁|Concentration at x₁",
    "C_2": "mass_conc|Konzentration bei x₂|Concentration at x₂", "x_1": "length|Ort 1|Position 1", "x_2": "length|Ort 2|Position 2"},
   auto=False)
EQ("wk_fick2", C, S, "(C_x - C_0)/(C_s - C_0) = 1 - erf(x/(2*sqrt(D_c*t)))", "2. Ficksches Gesetz (halbunendlicher Körper)",
   "Fick's second law (semi-infinite solid)",
   {"C_x": "number|Konzentration in der Tiefe x|Concentration at depth x", "C_0": "number|Anfangskonzentration|Initial concentration",
    "C_s": "number|Oberflächenkonzentration|Surface concentration", "x": "length|Tiefe|Depth", "D_c": _DC},
   auto=False, note="Oberflächenkonzentration und D konstant; Konzentrationen in derselben Einheit (z. B. Massen-%)")
EQ("wk_Q_two_T", C, S, "Q_d = Rgas*ln(D_1/D_2)/(1/T_2 - 1/T_1)", "Aktivierungsenergie aus D bei zwei Temperaturen",
   "Activation energy from D at two temperatures",
   {"Q_d": "molar_energy|Aktivierungsenergie|Activation energy", "D_1": "diffusivity|D bei T₁|D at T₁",
    "D_2": "diffusivity|D bei T₂|D at T₂", "T_1": "temperature|Temperatur 1|Temperature 1",
    "T_2": "temperature|Temperatur 2|Temperature 2"}, auto=False)
EQ("wk_Dt", C, S, "D_1*t_1 = D_2*t_2", "Gleiche Eindringtiefe: D·t konstant", "Equal penetration depth: D·t constant",
   {"D_1": "diffusivity|D bei Bedingung 1|D at condition 1", "D_2": "diffusivity|D bei Bedingung 2|D at condition 2",
    "t_1": "time|Zeit bei Bedingung 1|Time at condition 1", "t_2": "time|Zeit bei Bedingung 2|Time at condition 2"}, auto=False,
   note="gleiche Konzentration in gleicher Tiefe (2. Ficksches Gesetz, gleiche Randbedingungen)")

S = "Phasen und Umwandlungen"
_W0 = "fraction|Legierungszusammensetzung|Alloy composition"
EQ("wk_lever", C, S, "W_L = (w_a - w_0)/(w_a - w_L)", "Hebelgesetz: Anteil Schmelze", "Lever rule: liquid fraction",
   {"W_L": "fraction|Massenanteil Schmelze|Mass fraction of liquid", "w_a": "fraction|Zusammensetzung der festen Phase α|Composition of solid α",
    "w_0": _W0, "w_L": "fraction|Zusammensetzung der Schmelze|Composition of liquid"}, src="callister",
   note="Zusammensetzungen aus der Konode bei der betrachteten Temperatur")
EQ("wk_gibbs", C, S, "F_f = C_k - P_p + 2", "Gibbssche Phasenregel", "Gibbs phase rule",
   {"F_f": "number|Freiheitsgrade|Degrees of freedom", "C_k": "number|Zahl der Komponenten|Number of components",
    "P_p": "number|Zahl der Phasen|Number of phases"}, auto=False, note="bei festem Druck (kondensierte Systeme) F = C − P + 1")
EQ("wk_avrami", C, S, "y_A = 1 - exp(-(t/tau_A)**n_A)", "Avrami-Gleichung (JMAK)", "Avrami equation (JMAK)",
   {"y_A": "fraction|Umgewandelter Anteil|Transformed fraction", "tau_A": "time|Zeitkonstante|Time constant",
    "n_A": "number|Avrami-Exponent|Avrami exponent"}, auto=False, src="avrami1939", note="mit k = τ⁻ⁿ: y = 1 − exp(−k·tⁿ)")
EQ("wk_rate", C, S, "r_U = 1/t_05", "Umwandlungsrate", "Transformation rate",
   {"r_U": "rate_const|Umwandlungsrate|Transformation rate", "t_05": "time|Zeit bis 50 % Umwandlung|Time to 50 % transformation"},
   auto=False, src="callister")
EQ("wk_dGv", C, S, "dG_v = L_v*(T_m - T)/T_m", "Treibende Kraft der Erstarrung bei Unterkühlung", "Driving force for solidification at undercooling",
   {"dG_v": "energy_density|Treibende Kraft je Volumen (Betrag)|Driving force per volume (magnitude)",
    "L_v": "energy_density|Schmelzwärme je Volumen|Latent heat of fusion per volume", "T_m": "temperature|Schmelztemperatur|Melting temperature"},
   auto=False, note="T unterhalb T_m; ΔG_v als positiver Betrag")
EQ("wk_r_crit", C, S, "r_c = 2*gamma_s/dG_v", "Kritischer Keimradius (homogene Keimbildung)", "Critical nucleus radius (homogeneous nucleation)",
   {"r_c": "length|Kritischer Keimradius|Critical radius", "gamma_s": "surface_energy|Grenzflächenenergie|Interfacial energy",
    "dG_v": "energy_density|Treibende Kraft je Volumen (Betrag)|Driving force per volume (magnitude)"}, auto=False)
EQ("wk_dG_crit", C, S, "dG_c = 16*pi*gamma_s**3/(3*dG_v**2)", "Keimbildungsarbeit (homogen)", "Nucleation barrier (homogeneous)",
   {"dG_c": "energy|Keimbildungsarbeit|Nucleation barrier", "gamma_s": "surface_energy|Grenzflächenenergie|Interfacial energy",
    "dG_v": "energy_density|Treibende Kraft je Volumen (Betrag)|Driving force per volume (magnitude)"}, auto=False)
EQ("wk_scheil", C, S, "w_s = k_0*w_0*(1 - f_s)**(k_0 - 1)", "Scheil-Gleichung", "Scheil equation",
   {"w_s": "fraction|Konzentration im Festkörper an der Erstarrungsfront|Solid composition at the interface",
    "k_0": "number|Verteilungskoeffizient|Partition coefficient", "w_0": _W0, "f_s": "fraction|Erstarrter Anteil|Solid fraction"},
   auto=False, note="keine Diffusion im Festkörper, vollständige Durchmischung der Schmelze")

S = "Verformung und Festigkeit"
_SW = "stress|Wahre Spannung|True stress"
_PHI = "strain|Wahre plastische Dehnung|True plastic strain"
_NH = "number|Verfestigungsexponent|Strain-hardening exponent"
EQ("wk_hollomon", C, S, "sigma_w = K_H*phi_w**n_H", "Fliesskurve nach Hollomon", "Flow curve (Hollomon)",
   {"sigma_w": _SW, "K_H": "stress|Festigkeitskoeffizient|Strength coefficient", "phi_w": _PHI, "n_H": _NH},
   auto=False, src="hollomon1945")
EQ("wk_ludwik", C, S, "sigma_w = sigma_0 + K_H*phi_w**n_H", "Fliesskurve nach Ludwik", "Flow curve (Ludwik)",
   {"sigma_w": _SW, "sigma_0": "stress|Anfangsfliessspannung|Initial yield stress", "K_H": "stress|Festigkeitskoeffizient|Strength coefficient",
    "phi_w": _PHI, "n_H": _NH}, auto=False, src="dowling")
EQ("wk_considere", C, S, "phi_u = n_H", "Gleichmassdehnung (Considère)", "Uniform strain (Considère)",
   {"phi_u": "strain|Wahre Gleichmassdehnung|True uniform strain", "n_H": _NH}, auto=False, note="gilt für die Fliesskurve nach Hollomon")
EQ("wk_resilience", C, S, "U_r = sigma_y**2/(2*E)", "Resilienz (elastische Energie je Volumen)", "Modulus of resilience",
   {"U_r": "energy_density|Resilienz|Modulus of resilience", "sigma_y": "stress|Streckgrenze|Yield strength"})
EQ("wk_mises", C, S, "sigma_v = sqrt(sigma_x**2 + sigma_y**2 - sigma_x*sigma_y + 3*tau_xy**2)",
   "Vergleichsspannung nach von Mises (ebener Spannungszustand)", "Von Mises equivalent stress (plane stress)",
   {"sigma_v": "stress|Vergleichsspannung|Equivalent stress", "sigma_x": "stress|Normalspannung x|Normal stress x",
    "sigma_y": "stress|Normalspannung y|Normal stress y", "tau_xy": "stress|Schubspannung|Shear stress"}, src="gross2")
EQ("wk_tresca", C, S, "sigma_v = sigma_1 - sigma_3", "Vergleichsspannung nach Tresca", "Tresca equivalent stress",
   {"sigma_v": "stress|Vergleichsspannung|Equivalent stress", "sigma_1": "stress|Grösste Hauptspannung|Maximum principal stress",
    "sigma_3": "stress|Kleinste Hauptspannung|Minimum principal stress"}, auto=False, src="gross2")
EQ("wk_schmid", C, S, "tau_r = sigma*cos(phi_s)*cos(lambda_s)", "Schmidsches Schubspannungsgesetz", "Schmid's law",
   {"tau_r": "stress|Aufgelöste Schubspannung|Resolved shear stress",
    "phi_s": "angle|Winkel Gleitebenennormale – Last|Angle slip-plane normal – load",
    "lambda_s": "angle|Winkel Gleitrichtung – Last|Angle slip direction – load"}, src="callister")

S = "Kriechen"
EQ("wk_norton", C, S, "eps_dot = A_N*(sigma/MPa1)**n_N*exp(-Q_c/(Rgas*T))", "Stationäres Kriechen (Norton, Potenzgesetz)",
   "Steady-state creep (Norton power law)",
   {"eps_dot": "rate_const|Kriechrate|Creep rate", "A_N": "rate_const|Werkstoffkonstante (σ in MPa)|Material constant (σ in MPa)",
    "n_N": "number|Spannungsexponent|Stress exponent", "Q_c": "molar_energy|Aktivierungsenergie des Kriechens|Activation energy for creep"},
   auto=False, note="σ wird in MPa eingesetzt; A_N gilt für diese Wahl")
EQ("wk_lmp", C, S, "P_LM = T*(C_LM + log10(t_h))", "Larson-Miller-Parameter", "Larson–Miller parameter",
   {"P_LM": "temperature|Larson-Miller-Parameter (in K)|Larson–Miller parameter (in K)", "C_LM": "number|Konstante (oft ≈ 20)|Constant (often ≈ 20)",
    "t_h": "number|Bruchzeit in Stunden|Rupture time in hours"}, auto=False, src="larsonmiller1952")

S = "Ermüdung"
_SA = "stress|Spannungsamplitude|Stress amplitude"
_SO = "stress|Oberspannung|Maximum stress"
_SU = "stress|Unterspannung|Minimum stress"
_SM = "stress|Mittelspannung|Mean stress"
_SWF = "stress|Wechselfestigkeit (σ_m = 0)|Fully reversed fatigue strength"
_NF = "number|Bruchlastspielzahl|Cycles to failure"
EQ("wk_basquin", C, S, "sigma_a = sigma_ff*(2*N_f)**b_B", "Basquin-Gleichung (Zeitfestigkeit)", "Basquin equation (finite life)",
   {"sigma_a": _SA, "sigma_ff": "stress|Schwingfestigkeitskoeffizient σ′f|Fatigue strength coefficient σ′f", "N_f": _NF,
    "b_B": "number|Basquin-Exponent (negativ)|Basquin exponent (negative)"}, auto=False, src="basquin1910")
EQ("wk_coffin", C, S, "eps_ap = eps_ff*(2*N_f)**c_CM", "Coffin-Manson-Gleichung", "Coffin–Manson equation",
   {"eps_ap": "strain|Plastische Dehnungsamplitude|Plastic strain amplitude",
    "eps_ff": "strain|Duktilitätskoeffizient ε′f|Fatigue ductility coefficient ε′f", "N_f": _NF,
    "c_CM": "number|Duktilitätsexponent (negativ)|Fatigue ductility exponent (negative)"}, auto=False)
EQ("wk_amp", C, S, "sigma_a = (sigma_o - sigma_u)/2", "Spannungsamplitude", "Stress amplitude", {"sigma_a": _SA, "sigma_o": _SO, "sigma_u": _SU})
EQ("wk_mean", C, S, "sigma_m = (sigma_o + sigma_u)/2", "Mittelspannung", "Mean stress", {"sigma_m": _SM, "sigma_o": _SO, "sigma_u": _SU})
EQ("wk_R", C, S, "R_s = sigma_u/sigma_o", "Spannungsverhältnis", "Stress ratio",
   {"R_s": "number|Spannungsverhältnis R|Stress ratio R", "sigma_u": _SU, "sigma_o": _SO})
EQ("wk_goodman", C, S, "sigma_a = sigma_W*(1 - sigma_m/R_m)", "Goodman-Gerade", "Goodman line",
   {"sigma_a": "stress|Ertragbare Spannungsamplitude|Allowable stress amplitude", "sigma_W": _SWF, "sigma_m": _SM,
    "R_m": "stress|Zugfestigkeit|Tensile strength"}, auto=False)
EQ("wk_gerber", C, S, "sigma_a = sigma_W*(1 - (sigma_m/R_m)**2)", "Gerber-Parabel", "Gerber parabola",
   {"sigma_a": "stress|Ertragbare Spannungsamplitude|Allowable stress amplitude", "sigma_W": _SWF, "sigma_m": _SM,
    "R_m": "stress|Zugfestigkeit|Tensile strength"}, auto=False)
EQ("wk_soderberg", C, S, "sigma_a = sigma_W*(1 - sigma_m/R_e)", "Soderberg-Gerade", "Soderberg line",
   {"sigma_a": "stress|Ertragbare Spannungsamplitude|Allowable stress amplitude", "sigma_W": _SWF, "sigma_m": _SM,
    "R_e": "stress|Streckgrenze|Yield strength"}, auto=False)
EQ("wk_miner", C, S, "D_M = n_1/N_1 + n_2/N_2 + n_3/N_3", "Palmgren-Miner-Regel (drei Laststufen)", "Palmgren–Miner rule (three load levels)",
   {"D_M": "number|Schadenssumme (Bruch bei 1)|Damage sum (failure at 1)", "n_1": "number|Lastspiele Stufe 1|Cycles at level 1",
    "N_1": "number|Bruchlastspiele Stufe 1|Cycles to failure at level 1", "n_2": "number|Lastspiele Stufe 2|Cycles at level 2",
    "N_2": "number|Bruchlastspiele Stufe 2|Cycles to failure at level 2", "n_3": "number|Lastspiele Stufe 3|Cycles at level 3",
    "N_3": "number|Bruchlastspiele Stufe 3|Cycles to failure at level 3"}, auto=False, src="miner1945",
   note="nicht benutzte Stufen mit n = 0 eintragen")
EQ("wk_endurance", C, S, "sigma_W = 0.5*R_m", "Wechselfestigkeit von Stahl (Faustwert)", "Fatigue limit of steel (rule of thumb)",
   {"sigma_W": _SWF, "R_m": "stress|Zugfestigkeit|Tensile strength"}, auto=False,
   note="polierte Probe, Stahl bis R_m ≈ 1400 MPa; nur zur Abschätzung")

S = "Bruch und Zuverlässigkeit"
_PF = "fraction|Versagenswahrscheinlichkeit|Probability of failure"
_S0W = "stress|Charakteristische Festigkeit σ₀|Characteristic strength σ₀"
_MW = "number|Weibull-Modul|Weibull modulus"
EQ("wk_weibull", C, S, "P_f = 1 - exp(-(sigma/sigma_0W)**m_W)", "Weibull-Verteilung", "Weibull distribution",
   {"P_f": _PF, "sigma_0W": _S0W, "m_W": _MW}, src="weibull1951")
EQ("wk_weibull_V", C, S, "P_f = 1 - exp(-(V/V_0)*(sigma/sigma_0W)**m_W)", "Weibull-Verteilung mit Volumeneinfluss",
   "Weibull distribution with volume effect",
   {"P_f": _PF, "V": "volume|Beanspruchtes Volumen|Stressed volume", "V_0": "volume|Bezugsvolumen|Reference volume",
    "sigma_0W": _S0W, "m_W": _MW}, auto=False, src="weibull1951")
EQ("wk_size", C, S, "sigma_2 = sigma_1*(V_1/V_2)**(1/m_W)", "Grösseneinfluss der Festigkeit (Weibull)", "Size effect on strength (Weibull)",
   {"sigma_2": "stress|Festigkeit bei V₂|Strength at V₂", "sigma_1": "stress|Festigkeit bei V₁|Strength at V₁",
    "V_1": "volume|Volumen 1|Volume 1", "V_2": "volume|Volumen 2|Volume 2", "m_W": _MW}, auto=False, src="weibull1951",
   note="gleiche Versagenswahrscheinlichkeit")
EQ("wk_B_min", C, S, "B_min = 2.5*(K_Ic/R_e)**2", "Mindestdicke für ein gültiges K_Ic", "Minimum thickness for a valid K_Ic",
   {"B_min": "length|Mindestdicke (und Risslänge)|Minimum thickness (and crack length)", "K_Ic": "stress_int|Bruchzähigkeit|Fracture toughness",
    "R_e": "stress|Dehngrenze Rp0,2|Yield strength"}, src="anderson", note="Gültigkeitskriterium nach ASTM E399 (ebener Dehnungszustand)")
EQ("wk_shock", C, S, "dT_c = sigma_f*(1 - nu)/(E*alpha_T)", "Thermoschock: kritischer Temperatursprung", "Thermal shock: critical temperature jump",
   {"dT_c": "temp_diff|Kritischer Temperatursprung|Critical temperature jump", "sigma_f": "stress|Bruchfestigkeit|Fracture strength",
    "alpha_T": "expansion|Ausdehnungskoeffizient|Expansion coefficient"}, auto=False, src="kingery1955",
   note="erster Thermoschockparameter R; schroffe Abkühlung der Oberfläche")

S = "Verbundwerkstoffe"
_VF = "number|Faservolumenanteil|Fibre volume fraction"
_E1 = "modulus|E-Modul längs E₁|Longitudinal modulus E₁"
_E2 = "modulus|E-Modul quer E₂|Transverse modulus E₂"
_G12 = "modulus|Schubmodul G₁₂|Shear modulus G₁₂"
_NU12 = "number|Querkontraktionszahl ν₁₂|Poisson's ratio ν₁₂"
EQ("wk_c_rho", C, S, "rho_c = V_f*rho_f + (1 - V_f)*rho_m", "Dichte des Verbunds", "Composite density",
   {"rho_c": "density|Dichte Verbund|Composite density", "V_f": _VF, "rho_f": "density|Dichte Faser|Fibre density",
    "rho_m": "density|Dichte Matrix|Matrix density"}, auto=False)
EQ("wk_c_vf", C, S, "V_f = (w_f/rho_f)/(w_f/rho_f + (1 - w_f)/rho_m)", "Faservolumenanteil aus dem Massenanteil",
   "Fibre volume fraction from mass fraction",
   {"V_f": _VF, "w_f": "number|Fasermassenanteil|Fibre mass fraction", "rho_f": "density|Dichte Faser|Fibre density",
    "rho_m": "density|Dichte Matrix|Matrix density"}, auto=False, note="porenfrei")
EQ("wk_c_nu12", C, S, "nu_12 = V_f*nu_f + (1 - V_f)*nu_m", "Querkontraktionszahl ν₁₂ (Mischungsregel)", "Poisson's ratio ν₁₂ (rule of mixtures)",
   {"nu_12": _NU12, "V_f": _VF, "nu_f": "number|Querkontraktionszahl Faser|Fibre Poisson's ratio",
    "nu_m": "number|Querkontraktionszahl Matrix|Matrix Poisson's ratio"}, auto=False)
EQ("wk_c_G12", C, S, "1/G_12 = V_f/G_f + (1 - V_f)/G_m", "Schubmodul G₁₂ (Mischungsregel, Reihe)", "Shear modulus G₁₂ (rule of mixtures, series)",
   {"G_12": _G12, "V_f": _VF, "G_f": "modulus|Schubmodul Faser|Fibre shear modulus", "G_m": "modulus|Schubmodul Matrix|Matrix shear modulus"},
   auto=False, note="untere Abschätzung")
EQ("wk_c_halpin_eta", C, S, "eta_H = (E_f/E_m - 1)/(E_f/E_m + xi_H)", "Halpin-Tsai: Hilfsgrösse η", "Halpin–Tsai: parameter η",
   {"eta_H": "number|Hilfsgrösse η|Parameter η", "E_f": "modulus|E-Modul Faser|Fibre modulus", "E_m": "modulus|E-Modul Matrix|Matrix modulus",
    "xi_H": "number|Verstärkungsfaktor ξ|Reinforcement factor ξ"}, auto=False, src="halpin1976")
EQ("wk_c_halpin", C, S, "E_2 = E_m*(1 + xi_H*eta_H*V_f)/(1 - eta_H*V_f)", "Halpin-Tsai: E-Modul quer", "Halpin–Tsai: transverse modulus",
   {"E_2": _E2, "E_m": "modulus|E-Modul Matrix|Matrix modulus", "xi_H": "number|Verstärkungsfaktor ξ|Reinforcement factor ξ",
    "eta_H": "number|Hilfsgrösse η|Parameter η", "V_f": _VF}, auto=False, src="halpin1976",
   note="ξ ≈ 2 für E₂ bei runden Fasern")
EQ("wk_c_strength", C, S, "sigma_cl = V_f*sigma_fu + (1 - V_f)*sigma_mf", "Längsfestigkeit (Mischungsregel)", "Longitudinal strength (rule of mixtures)",
   {"sigma_cl": "stress|Festigkeit Verbund längs|Composite longitudinal strength", "V_f": _VF,
    "sigma_fu": "stress|Faserfestigkeit|Fibre strength", "sigma_mf": "stress|Matrixspannung beim Faserbruch|Matrix stress at fibre failure"},
   auto=False, src="callister")
EQ("wk_c_lcrit", C, S, "l_c = sigma_fu*d_f/(2*tau_c)", "Kritische Faserlänge", "Critical fibre length",
   {"l_c": "length|Kritische Faserlänge|Critical fibre length", "sigma_fu": "stress|Faserfestigkeit|Fibre strength",
    "d_f": "length|Faserdurchmesser|Fibre diameter", "tau_c": "stress|Grenzflächenscherfestigkeit|Interfacial shear strength"},
   auto=False, src="callister")
EQ("wk_c_offaxis", C, S, "1/E_x = cos(theta)**4/E_1 + (1/G_12 - 2*nu_12/E_1)*sin(theta)**2*cos(theta)**2 + sin(theta)**4/E_2",
   "E-Modul einer UD-Schicht unter dem Winkel θ", "Off-axis modulus of a UD ply",
   {"E_x": "modulus|E-Modul in Lastrichtung|Modulus in load direction", "theta": "angle|Winkel Faser – Last|Fibre–load angle",
    "E_1": _E1, "G_12": _G12, "nu_12": _NU12, "E_2": _E2}, auto=False)
EQ("wk_c_tsaihill", C, S, "F_TH = (sigma_1/X_t)**2 - sigma_1*sigma_2/X_t**2 + (sigma_2/Y_t)**2 + (tau_12/S_12)**2",
   "Tsai-Hill-Kriterium (Versagen bei 1)", "Tsai–Hill criterion (failure at 1)",
   {"F_TH": "number|Versagensindex|Failure index", "sigma_1": "stress|Spannung längs|Longitudinal stress",
    "X_t": "stress|Festigkeit längs (Zug bzw. Druck)|Longitudinal strength (tension or compression)",
    "sigma_2": "stress|Spannung quer|Transverse stress", "Y_t": "stress|Festigkeit quer (Zug bzw. Druck)|Transverse strength (tension or compression)",
    "tau_12": "stress|Schubspannung|Shear stress", "S_12": "stress|Schubfestigkeit|Shear strength"}, auto=False,
   note="bei Druckspannung die Druckfestigkeit einsetzen; Werte der Schicht z. B. mat(\"AS4/3501-6\", \"Xt\")")

S = "Polymere"
EQ("wk_wlf", C, S, "log10(a_T) = -C_1*(T - T_r)/(C_2 + T - T_r)", "WLF-Gleichung (Zeit-Temperatur-Verschiebung)", "WLF equation (time–temperature shift)",
   {"a_T": "number|Verschiebungsfaktor|Shift factor", "C_1": "number|Konstante C₁ (17,44 bei T_r = T_g)|Constant C₁ (17.44 for T_r = T_g)",
    "T_r": "temperature|Bezugstemperatur|Reference temperature", "C_2": "temp_diff|Konstante C₂ (51,6 K bei T_r = T_g)|Constant C₂ (51.6 K for T_r = T_g)"},
   auto=False, src="wlf1955", note="etwa T_g bis T_g + 100 K")
EQ("wk_fox", C, S, "1/T_g = w_1/T_g1 + w_2/T_g2", "Fox-Gleichung (T_g von Mischungen und Copolymeren)", "Fox equation (T_g of blends and copolymers)",
   {"T_g": "temperature|Glasübergangstemperatur der Mischung|Glass transition of the blend", "w_1": "fraction|Massenanteil 1|Mass fraction 1",
    "T_g1": "temperature|T_g Komponente 1|T_g component 1", "w_2": "fraction|Massenanteil 2|Mass fraction 2",
    "T_g2": "temperature|T_g Komponente 2|T_g component 2"}, auto=False, src="fox1956")
EQ("wk_Mn", C, S, "M_n = DP*M_0", "Zahlenmittel der Molmasse", "Number-average molar mass",
   {"M_n": "molar_mass|Zahlenmittel M_n|Number average M_n", "DP": "number|Polymerisationsgrad|Degree of polymerisation",
    "M_0": "molar_mass|Molmasse der Wiederholeinheit|Repeat-unit molar mass"}, src="callister")
EQ("wk_PDI", C, S, "D_M = M_w/M_n", "Dispersität", "Dispersity",
   {"D_M": "number|Dispersität Đ|Dispersity Đ", "M_w": "molar_mass|Gewichtsmittel M_w|Weight average M_w",
    "M_n": "molar_mass|Zahlenmittel M_n|Number average M_n"}, src="callister")
EQ("wk_xc_rho", C, S, "x_c = rho_c*(rho_s - rho_a)/(rho_s*(rho_c - rho_a))", "Kristallinität aus der Dichte", "Crystallinity from density",
   {"x_c": "fraction|Kristallinität (Massenanteil)|Crystallinity (mass fraction)", "rho_c": "density|Dichte kristallin|Crystalline density",
    "rho_s": "density|Dichte der Probe|Sample density", "rho_a": "density|Dichte amorph|Amorphous density"}, src="callister")
EQ("wk_xc_dsc", C, S, "x_c = dH_m/dH_m0", "Kristallinität aus der Schmelzenthalpie (DSC)", "Crystallinity from enthalpy of fusion (DSC)",
   {"x_c": "fraction|Kristallinität (Massenanteil)|Crystallinity (mass fraction)", "dH_m": "spec_energy|Gemessene Schmelzenthalpie|Measured enthalpy of fusion",
    "dH_m0": "spec_energy|Schmelzenthalpie bei 100 % Kristallinität|Enthalpy of fusion at 100 % crystallinity"}, src="mark2007",
   note="bei gefüllten Proben ΔH_m auf den Polymeranteil beziehen")
EQ("wk_rubber", C, S, "E_r = 3*rho*Rgas*T/M_c", "Gummielastizität: E-Modul aus der Netzbogenmolmasse", "Rubber elasticity: modulus from molar mass between crosslinks",
   {"E_r": "modulus|E-Modul (kleine Dehnung)|Young's modulus (small strain)", "M_c": "molar_mass|Molmasse zwischen Vernetzungsstellen|Molar mass between crosslinks"},
   auto=False, src="treloar1975", note="ideales affines Netzwerk; G = E/3")
EQ("wk_relax", C, S, "sigma_t = sigma_i*exp(-t/tau_r)", "Spannungsrelaxation (Maxwell-Modell)", "Stress relaxation (Maxwell model)",
   {"sigma_t": "stress|Spannung zur Zeit t|Stress at time t", "sigma_i": "stress|Anfangsspannung|Initial stress",
    "tau_r": "time|Relaxationszeit|Relaxation time"}, auto=False, src="callister")

S = "Elektrische und thermische Eigenschaften"
_KAP = "el_conductivity|Elektrische Leitfähigkeit|Electrical conductivity"
EQ("wk_wf", C, S, "lambda_w = L_WF*kappa*T", "Wiedemann-Franz-Gesetz", "Wiedemann–Franz law",
   {"lambda_w": "conductivity_th|Wärmeleitfähigkeit|Thermal conductivity",
    "L_WF": "lorenz|Lorenz-Zahl (≈ 2,44·10⁻⁸ W·Ω/K²)|Lorenz number (≈ 2.44·10⁻⁸ W·Ω/K²)", "kappa": _KAP}, auto=False,
   note="Metalle: Elektronenanteil der Wärmeleitung")
EQ("wk_matthiessen", C, S, "rho_el = rho_t + rho_i + rho_d", "Matthiessen-Regel", "Matthiessen's rule",
   {"rho_el": "resistivity|Spez. Widerstand|Resistivity", "rho_t": "resistivity|Thermischer Anteil|Thermal contribution",
    "rho_i": "resistivity|Anteil der Fremdatome|Impurity contribution", "rho_d": "resistivity|Anteil der Verformung|Deformation contribution"},
   auto=False)
EQ("wk_carrier", C, S, "kappa = n_q*q_e*mu_q", "Leitfähigkeit aus Ladungsträgerdichte und Beweglichkeit", "Conductivity from carrier density and mobility",
   {"kappa": _KAP, "n_q": "number_conc|Ladungsträgerdichte|Carrier density", "mu_q": "mobility|Beweglichkeit|Mobility"})
EQ("wk_semi", C, S, "kappa = q_e*(n_q*mu_n + p_q*mu_p)", "Leitfähigkeit eines Halbleiters", "Conductivity of a semiconductor",
   {"kappa": _KAP, "n_q": "number_conc|Elektronendichte|Electron density", "mu_n": "mobility|Elektronenbeweglichkeit|Electron mobility",
    "p_q": "number_conc|Löcherdichte|Hole density", "mu_p": "mobility|Löcherbeweglichkeit|Hole mobility"}, auto=False)
EQ("wk_intrinsic", C, S, "n_i = sqrt(N_C*N_V)*exp(-E_g/(2*kB*T))", "Eigenleitungsdichte", "Intrinsic carrier density",
   {"n_i": "number_conc|Eigenleitungsdichte|Intrinsic carrier density",
    "N_C": "number_conc|Effektive Zustandsdichte Leitungsband|Effective density of states, conduction band",
    "N_V": "number_conc|Effektive Zustandsdichte Valenzband|Effective density of states, valence band", "E_g": "energy|Bandlücke|Band gap"},
   auto=False, src="sze2007", sample={"E_g": 1.8e-19, "T": 300.0})

S = "Korrosion"
_IC = "current_density|Korrosionsstromdichte|Corrosion current density"
EQ("wk_corr_rate", C, S, "v_corr = i_corr*M/(z_e*F_c*rho)", "Abtragsrate aus der Korrosionsstromdichte", "Penetration rate from corrosion current density",
   {"v_corr": "penetration_rate|Abtragsrate|Penetration rate", "i_corr": _IC, "M": "molar_mass|Molare Masse des Metalls|Molar mass of the metal",
    "z_e": "number|Ladungszahl|Charge number", "rho": "density|Dichte des Metalls|Density of the metal"},
   note="gleichmässiger Abtrag; bei Legierungen M/z durch das Äquivalentgewicht ersetzen")
EQ("wk_corr_mass", C, S, "m = i_corr*A*t*M/(z_e*F_c)", "Massenverlust durch Korrosion", "Mass loss by corrosion",
   {"m": "mass|Massenverlust|Mass loss", "i_corr": _IC, "A": "area|Angegriffene Fläche|Exposed area",
    "M": "molar_mass|Molare Masse des Metalls|Molar mass of the metal", "z_e": "number|Ladungszahl|Charge number"}, auto=False)
EQ("wk_pbr", C, S, "PBR = M_ox*rho_me/(n_me*M_me*rho_ox)", "Pilling-Bedworth-Verhältnis", "Pilling–Bedworth ratio",
   {"PBR": "number|Pilling-Bedworth-Verhältnis|Pilling–Bedworth ratio", "M_ox": "molar_mass|Molare Masse des Oxids|Oxide molar mass",
    "rho_me": "density|Dichte des Metalls|Metal density", "n_me": "number|Metallatome je Formeleinheit Oxid|Metal atoms per oxide formula unit",
    "M_me": "molar_mass|Molare Masse des Metalls|Metal molar mass", "rho_ox": "density|Dichte des Oxids|Oxide density"},
   src="pilling1923", note="Faustregel: < 1 porös, 1 bis 2 schützend, > 2 neigt zum Abplatzen")
EQ("wk_parabolic", C, S, "x_ox**2 = k_p*t", "Parabolisches Wachstum der Oxidschicht", "Parabolic oxide growth",
   {"x_ox": "length|Schichtdicke|Scale thickness", "k_p": "diffusivity|Parabolische Konstante|Parabolic rate constant"},
   auto=False, src="callister")
EQ("wk_tafel", C, S, "eta_T = b_T*log10(i_A/i_0)", "Tafel-Gleichung", "Tafel equation",
   {"eta_T": "voltage|Überspannung|Overpotential", "b_T": "voltage|Tafel-Steigung je Dekade|Tafel slope per decade",
    "i_A": "current_density|Stromdichte|Current density", "i_0": "current_density|Austauschstromdichte|Exchange current density"},
   auto=False, src="bard")

S = "Stahl und Wärmebehandlung"
_W = lambda el: f"number|{el} in Massen-%|{el} in mass-%"
EQ("wk_ce_iiw", C, S, "CE = w_C + w_Mn/6 + (w_Cr + w_Mo + w_V)/5 + (w_Ni + w_Cu)/15", "Kohlenstoffäquivalent (IIW)", "Carbon equivalent (IIW)",
   {"CE": "number|Kohlenstoffäquivalent in %|Carbon equivalent in %", **{f"w_{x}": _W(x) for x in ("C", "Mn", "Cr", "Mo", "V", "Ni", "Cu")}},
   note="Massenanteile in % als Zahl eingeben")
EQ("wk_ms", C, S, "theta_Ms = 539 - 423*w_C - 30.4*w_Mn - 17.7*w_Ni - 12.1*w_Cr - 7.5*w_Mo", "Martensitstarttemperatur (Andrews, linear)",
   "Martensite start temperature (Andrews, linear)",
   {"theta_Ms": "number|Ms in °C (als Zahl)|Ms in °C (as a number)", **{f"w_{x}": _W(x) for x in ("C", "Mn", "Ni", "Cr", "Mo")}},
   auto=False, src="andrews1965", note="Massenanteile in %; Ergebnis in °C als Zahl")
EQ("wk_ac3", C, S, "theta_Ac3 = 910 - 203*sqrt(w_C) - 15.2*w_Ni + 44.7*w_Si + 104*w_V + 31.5*w_Mo + 13.1*w_W",
   "Ac3-Temperatur (Andrews)", "Ac3 temperature (Andrews)",
   {"theta_Ac3": "number|Ac3 in °C (als Zahl)|Ac3 in °C (as a number)", **{f"w_{x}": _W(x) for x in ("C", "Ni", "Si", "V", "Mo", "W")}},
   auto=False, src="andrews1965", note="Massenanteile in %; Ergebnis in °C als Zahl")
EQ("wk_hj", C, S, "P_HJ = T*(C_HJ + log10(t_h))", "Anlassparameter (Hollomon-Jaffe)", "Tempering parameter (Hollomon–Jaffe)",
   {"P_HJ": "temperature|Anlassparameter (in K)|Tempering parameter (in K)", "C_HJ": "number|Konstante (werkstoffabhängig, oft ≈ 20)|Constant (material-dependent, often ≈ 20)",
    "t_h": "number|Anlassdauer in Stunden|Tempering time in hours"}, auto=False, src="hollomonjaffe1945")

S = "Werkstoffauswahl"
EQ("wk_spec_E", C, S, "E_sp = E/rho", "Spezifische Steifigkeit", "Specific stiffness",
   {"E_sp": "spec_energy|Spezifischer E-Modul|Specific modulus"})
EQ("wk_spec_R", C, S, "R_sp = sigma_f/rho", "Spezifische Festigkeit", "Specific strength",
   {"R_sp": "spec_energy|Spezifische Festigkeit|Specific strength", "sigma_f": "stress|Festigkeit|Strength"})
EQ("wk_tie_stiff", C, S, "m = S_t*l**2*rho/E", "Masse eines Zugstabs gegebener Steifigkeit", "Mass of a tie of given stiffness",
   {"S_t": "spring|Geforderte Steifigkeit|Required stiffness", "l": "length|Länge|Length"}, auto=False,
   note="Leistungsindex E/ρ: der leichteste Stab hat das grösste E/ρ")
EQ("wk_tie_strong", C, S, "m = F*l*rho/sigma_f", "Masse eines Zugstabs gegebener Tragkraft", "Mass of a tie of given strength",
   {"F": "force|Zu tragende Kraft|Load to carry", "l": "length|Länge|Length", "sigma_f": "stress|Festigkeit|Strength"}, auto=False,
   note="Leistungsindex σ_f/ρ")
EQ("wk_beam_stiff", C, S, "m = sqrt(12*S_t*l**3/(C_B*E))*l*rho", "Masse eines Balkens (quadratischer Querschnitt) gegebener Steifigkeit",
   "Mass of a beam (square section) of given stiffness",
   {"S_t": "spring|Geforderte Steifigkeit|Required stiffness", "l": "length|Länge|Length",
    "C_B": "number|Lagerungsfaktor (z. B. 48: zwei Stützen, Last in der Mitte)|Support factor (e.g. 48: simply supported, central load)"},
   auto=False, note="Leistungsindex E^(1/2)/ρ")

# =============================================================================================== Mathematik
C, S = "Mathematik", "Algebra und Trigonometrie"
EQ("m_quad", C, S, "x_1 = (-b_q + sqrt(b_q**2 - 4*a_q*c_q))/(2*a_q)", "Quadratische Gleichung (Lösung 1)", "Quadratic formula (root 1)",
   {"x_1": "number|Lösung|Root", "a_q": "number|Koeffizient a|Coefficient a", "b_q": "number|Koeffizient b|Coefficient b",
    "c_q": "number|Koeffizient c|Coefficient c"}, auto=False, note="a·x² + b·x + c = 0; zweite Lösung mit −√")
EQ("m_cos_law", C, S, "c_t**2 = a_t**2 + b_t**2 - 2*a_t*b_t*cos(gamma_t)", "Kosinussatz", "Law of cosines",
   {"c_t": "length|Seite c|Side c", "a_t": "length|Seite a|Side a", "b_t": "length|Seite b|Side b", "gamma_t": "angle|Winkel γ|Angle γ"}, auto=False)
EQ("m_sin_law", C, S, "a_t/sin(alpha_t) = b_t/sin(beta_t)", "Sinussatz", "Law of sines",
   {"a_t": "length|Seite a|Side a", "b_t": "length|Seite b|Side b", "alpha_t": "angle|Winkel α|Angle α", "beta_t": "angle|Winkel β|Angle β"}, auto=False)
EQ("m_slope", C, S, "alpha = atan(h/l)", "Steigungswinkel", "Slope angle", {"alpha": "angle|Steigungswinkel|Slope angle", "h": "length|Höhendifferenz|Rise",
   "l": "length|Horizontale Länge|Run"}, auto=False)
EQ("m_percent", C, S, "x_p = (x_neu - x_alt)/x_alt", "Relative Änderung", "Relative change",
   {"x_p": "number|Relative Änderung|Relative change", "x_neu": "number|Neuer Wert|New value", "x_alt": "number|Alter Wert|Old value"}, auto=False)
EQ("m_exp_growth", C, S, "N_t = N_0*exp(k_r*t)", "Exponentielles Wachstum", "Exponential growth",
   {"N_t": "number|Bestand|Amount", "N_0": "number|Anfangsbestand|Initial amount", "k_r": "rate_const|Wachstumsrate|Growth rate"}, auto=False)

# ----------------------------------------------------------------------------------------------- Quellen
# Quelle je Abschnitt (labcalc.sources); einzelne Formeln mit eigener Quelle stehen in SRC_OVERRIDE oder EQ(src=…).
SECTION_SRC = {
    ("Mechanik", "Kinematik"): "halliday", ("Mechanik", "Freier Fall und Wurf"): "halliday",
    ("Mechanik", "Kreisbewegung"): "halliday", ("Mechanik", "Dynamik"): "halliday",
    ("Mechanik", "Energie und Leistung"): "halliday", ("Mechanik", "Schwingungen und Wellen"): "halliday",
    ("Festigkeitslehre", "Spannung und Dehnung"): "gross2", ("Festigkeitslehre", "Zugversuch"): "iso6892",
    ("Festigkeitslehre", "Biegung"): "gross2", ("Festigkeitslehre", "Torsion und Knickung"): "gross2",
    ("Festigkeitslehre", "Behälter"): "gross2", ("Festigkeitslehre", "Bruchmechanik"): "anderson",
    ("Festigkeitslehre", "Härte"): "iso6507",
    ("Geometrie", "Flächen"): "bronstein", ("Geometrie", "Körper"): "bronstein",
    ("Wärmelehre", "Wärme und Temperatur"): "halliday", ("Wärmelehre", "Wärmeübertragung"): "bergman",
    ("Wärmelehre", "Gase"): "halliday",
    ("Fluidmechanik", "Hydrostatik"): "white", ("Fluidmechanik", "Strömung"): "white",
    ("Elektrotechnik", "Gleichstrom"): "halliday", ("Elektrotechnik", "Felder, Kondensator, Spule"): "halliday",
    ("Elektrotechnik", "Wechselstrom"): "halliday",
    ("Optik und Mikroskopie", "Licht"): "hecht", ("Optik und Mikroskopie", "Abbildung und Mikroskop"): "murphy",
    ("Chemie", "Stoffmenge und Konzentration"): "greenbook", ("Chemie", "Säuren und Basen"): "harris",
    ("Chemie", "Löslichkeit und Gleichgewicht"): "harris", ("Chemie", "Thermodynamik"): "atkins",
    ("Chemie", "Elektrochemie"): "bard", ("Chemie", "Kolligative Eigenschaften"): "atkins",
    ("Chemie", "Radioaktivität"): "krane", ("Chemie", "Kinetik und Spektroskopie"): "atkins",
    ("Chemie", "Laborpraxis und grüne Kennzahlen"): "harris",
    ("Werkstoffkunde", "Kristallographie"): "callister", ("Werkstoffkunde", "Defekte und Diffusion"): "callister",
    ("Werkstoffkunde", "Phasen und Umwandlungen"): "porter", ("Werkstoffkunde", "Verformung und Festigkeit"): "callister",
    ("Werkstoffkunde", "Kriechen"): "dowling", ("Werkstoffkunde", "Ermüdung"): "dowling",
    ("Werkstoffkunde", "Bruch und Zuverlässigkeit"): "callister", ("Werkstoffkunde", "Verbundwerkstoffe"): "daniel2006",
    ("Werkstoffkunde", "Polymere"): "callister", ("Werkstoffkunde", "Elektrische und thermische Eigenschaften"): "callister",
    ("Werkstoffkunde", "Korrosion"): "astmg102", ("Werkstoffkunde", "Stahl und Wärmebehandlung"): "en1011_2",
    ("Werkstoffkunde", "Werkstoffauswahl"): "ashby",
    ("Mathematik", "Algebra und Trigonometrie"): "bronstein",
}
SRC_OVERRIDE = {
    "str_true_stress": "callister", "str_true_strain": "callister", "str_notch": "callister",
    "str_mixture": "callister", "str_mixture_t": "callister", "str_hallpetch": "callister",
    "bend_3pt": "iso178", "bend_3pt_E": "iso178",
    "hard_HB": "iso6506", "hard_Rm": "iso18265",
    "opt_lens": "hecht", "opt_mag": "hecht",
    "ch_dilution": "harris", "ch_pH": "harris", "ch_beer": "harris", "ch_transm": "harris",
    "ch_faraday": "bard", "ch_faraday_eta": "bard", "ch_el_yield": "bard", "ch_nernst": "bard", "ch_diff_arrh": "porter", "ch_diff_len": "porter",
    "nuc_mass_defect": "krane",
    "lab_E_factor": "sheldon2007", "lab_PMI": "jimenez2011", "lab_RME": "constable2002",
}

# ----------------------------------------------------------------------------------------------- aufbauen
EQUATIONS: list[Equation] = [Equation(*a, **k) for a, k in _RAW]
for _e in EQUATIONS:
    _key = _e.src_key or SRC_OVERRIDE.get(_e.id) or SECTION_SRC.get((_e.cat, _e.sub))
    if _key is None:
        raise ValueError(f"{_e.id}: keine Quelle (Abschnitt {_e.cat} / {_e.sub})")
    _note = _e.ref or (f"Stichwort: {_e.en}" if SRC.REFS[_key]["type"] == "book" else "")
    _e.source = SRC.ref(_key, _note)
    _e.source_key = _key
BY_ID = {e.id: e for e in EQUATIONS}
CATEGORY_EN = {"Mechanik": "Mechanics", "Festigkeitslehre": "Strength of materials", "Geometrie": "Geometry",
               "Wärmelehre": "Heat", "Fluidmechanik": "Fluid mechanics", "Elektrotechnik": "Electrical engineering",
               "Optik und Mikroskopie": "Optics and microscopy", "Chemie": "Chemistry", "Werkstoffkunde": "Materials science",
               "Mathematik": "Mathematics"}


def symbols_list():
    """Alle in der Sammlung vorkommenden (Symbol, Groessenart) mit Bezeichnung, fuer Vorschlaege."""
    seen, out = set(), []
    for e in EQUATIONS:
        for v in e.vars:
            key = (v["sym"], v["kind"])
            if key in seen:
                continue
            seen.add(key)
            out.append({"sym": v["sym"], "kind": v["kind"], "de": v["de"], "en": v["en"], "html": R.sym_html(v["sym"])})
    return out


def library_dict(lang="de"):
    return [e.to_dict(lang) for e in EQUATIONS]
