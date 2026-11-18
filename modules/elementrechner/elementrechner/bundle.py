"""Ergebnisse des Elementrechners für den Bericht (Format folio-lab-bundle/1).

Inhalt: ausgeglichene Gleichung (mit Rechenweg über die Stoffmatrix), Bilanz je Element, Stöchiometrie
(limitierender Stoff, theoretische Mengen, Ausbeute, Atomökonomie), molare Massen mit Zusammensetzung und
Werte für \\labval. Formeln werden im Mathemodus mit \\mathrm gesetzt, damit kein Zusatzpaket (mhchem) nötig ist.
Die Quelle ist der Arbeitsstand selbst; "Aktualisieren" rechnet alles neu.
"""
from __future__ import annotations

import math
import re
import sys
from fractions import Fraction
from pathlib import Path

_SDK = Path(__file__).resolve().parents[3] / "sdk" / "python"
if _SDK.is_dir() and str(_SDK) not in sys.path:
    sys.path.insert(0, str(_SDK))

import labcite  # noqa: E402
from labbundle import Bundle, booktabs, slugify, tex_escape  # noqa: E402
from labcalc import chem as C  # noqa: E402

from . import analysis as AN  # noqa: E402
from .refs import REFS  # noqa: E402


def _amp(s: str) -> str:
    """& for LaTeX (kept out of f-string expressions: a backslash there needs Python 3.12)."""
    return s.replace("&", "\\&")

T = {
    "de": {
        "module": "Elementrechner", "title": "Reaktionsgleichung", "eq": "Reaktionsgleichung",
        "balanced": "Die Gleichung wurde über die Erhaltung der Atome jedes Elements{charge} ausgeglichen.",
        "charge": " und der Ladung", "nuclear": "Die Kerngleichung erfüllt die Erhaltung von Massenzahl $A$ und Ordnungszahl $Z$.",
        "given_ok": "Die angegebenen Koeffizienten sind ausgeglichen.",
        "matrix": "Rechenweg: Jede Zeile der Stoffmatrix $\\mathbf{{A}}$ ist eine Erhaltungsgrösse ({rows}), jede Spalte ein Stoff "
                  "(Edukte negativ, Produkte positiv). Gesucht sind die kleinsten positiven ganzen Koeffizienten "
                  "$\\nu$ mit $\\mathbf{{A}}\\,\\nu = \\mathbf{{0}}$ (Nullraum der Matrix).",
        "solution": "Lösung", "problem": "Die Gleichung lässt sich nicht ausgleichen", "status": "Hinweis",
        "bal_cap": "Bilanz der ausgeglichenen Gleichung je Erhaltungsgrösse.", "h_row": "Grösse", "h_l": "Edukte",
        "h_r": "Produkte", "stoich": "Stöchiometrie", "st_cap": "Stoffmengen und Massen; molare Massen aus den Standard-Atomgewichten.",
        "h_sp": "Stoff", "h_nu": "$\\nu$", "h_M": "$M$ in g/mol", "h_n0": "$n_0$ in mol", "h_m0": "$m_0$ in g",
        "h_n": "$n$ umgesetzt/gebildet in mol", "h_m": "$m$ in g", "h_rest": "Rest in g", "h_y": "Ausbeute",
        "lim": "Limitierend ist {sp}; der Umsatz beträgt $\\xi = {xi}$\\,mol.",
        "st_steps": "Rechenweg: Für jedes gegebene Edukt ist $n = m/M$ (bzw. $n = c\\,V$ oder für Gase $n = pV/(RT)$); "
                    "der mögliche Umsatz ist $\\xi_i = n_i/\\nu_i$. Das kleinste $\\xi$ bestimmt den limitierenden Stoff; "
                    "gebildet werden $n_j = \\nu_j\\,\\xi$ und $m_j = n_j\\,M_j$.",
        "gas": "Gasvolumen bei $T = {T}$\\,K und $p = {p}$\\,Pa mit $R$ aus CODATA 2022.",
        "ae": "Atomökonomie nach Trost: Anteil der Masse eines Produkts an der Masse aller Edukte "
              "($\\mathrm{AE} = \\nu_P M_P / \\sum \\nu_E M_E$)",
        "yield": "Ausbeute = erhalten / theoretisch.",
        "mm": "Molare Masse", "mm_cap": "Zusammensetzung von {f}; Atomgewichte gekürzt nach IUPAC/CIAAW.",
        "h_el": "Element", "h_cnt": "Anzahl", "h_Ar": "$A_\\mathrm{r}$", "h_part": "$N \\cdot A_\\mathrm{r}$", "h_w": "Massenanteil",
        "mm_text": "$M = \\sum_i N_i\\,A_{\\mathrm{r},i} \\cdot M_\\mathrm{u}$ mit $M_\\mathrm{u} \\approx 1$\\,g/mol "
                   "(relative Abweichung unter $10^{-8}$). Die Unsicherheit ist aus den Unsicherheiten der gekürzten "
                   "Atomgewichte kombiniert (gleiche Elemente voll korreliert, verschiedene unabhängig).",
        "emp": "Elementaranalyse", "emp_text": "Aus den Massenanteilen folgt die Verhältnisformel {e}",
        "emp_mol": " und mit der molaren Masse die Molekülformel {m}", "nothing": "Noch nichts berechnet: bitte eine Gleichung oder einen Stoff eingeben.",
        "v_M": "Molare Masse von {f}", "v_xi": "Umsatz $\\xi$", "v_m": "Theoretische Masse {f}", "v_n": "Theoretische Stoffmenge {f}",
        "v_y": "Ausbeute {f}", "v_ae": "Atomökonomie {f}", "v_lim": "Limitierender Stoff", "v_eq": "Ausgeglichene Gleichung",
        "summary": "{n} Stoffe",
        "th": "Thermochemie", "th_cap": "Standardbildungsgrössen bei 298,15 K und 1 bar; * $\\Delta_\\mathrm{f}G^\\circ$ berechnet aus "
              "$\\Delta_\\mathrm{f}H^\\circ$ und $S^\\circ$.",
        "h_ph": "Phase", "h_H": "$\\Delta_\\mathrm{f}H^\\circ$ in kJ/mol", "h_G": "$\\Delta_\\mathrm{f}G^\\circ$ in kJ/mol",
        "h_S": "$S^\\circ$ in J/(mol\\,K)", "h_Cp": "$C_p^\\circ$ in J/(mol\\,K)", "h_src": "Quelle",
        "th_intro": "Die Reaktionsgrössen folgen aus den Standardbildungsgrössen der Stoffe bei $T^\\circ = 298{,}15$\\,K und "
                    "$p^\\circ = 1$\\,bar (Satz von Hess; $\\nu$ negativ für Edukte).",
        "th_gcalc": "Wo die Tabelle kein $\\Delta_\\mathrm{f}G^\\circ$ angibt, ist es aus $\\Delta_\\mathrm{f}G^\\circ = "
                    "\\Delta_\\mathrm{f}H^\\circ - T\\,\\Delta_\\mathrm{f}S^\\circ$ mit $\\Delta_\\mathrm{f}S^\\circ = S^\\circ - "
                    "\\sum S^\\circ_\\mathrm{Elemente}$ (Elemente im Referenzzustand) berechnet.",
        "exo": "Die Reaktion ist exotherm", "endo": "Die Reaktion ist endotherm",
        "exg": "und unter Standardbedingungen exergonisch", "eng": "und unter Standardbedingungen endergonisch",
        "rate": "$\\Delta_\\mathrm{r}G^\\circ < 0$ bedeutet nur, dass die Reaktion ablaufen kann; über ihre Geschwindigkeit sagt "
                "es nichts aus. Die Aktivierungsenergie folgt nicht aus der Gleichung und den Bildungsdaten, sondern aus "
                "kinetischen Messungen (Arrhenius-Auftragung).",
        "tstar": "Bei $T^* = \\Delta_\\mathrm{r}H^\\circ/\\Delta_\\mathrm{r}S^\\circ = {T}$\\,K wird $\\Delta_\\mathrm{r}G = 0$ "
                 "(Näherung mit temperaturunabhängigem $\\Delta_\\mathrm{r}H^\\circ$ und $\\Delta_\\mathrm{r}S^\\circ$).",
        "approx": "Bei $T = {T}$\\,K gilt genähert $\\Delta_\\mathrm{r}G \\approx \\Delta_\\mathrm{r}H^\\circ - T\\,\\Delta_\\mathrm{r}S^\\circ "
                  "= {G}$\\,kJ/mol und $\\lg K \\approx {lgK}$ (ohne Temperaturabhängigkeit von $C_p$).",
        "cpt": "Bei $T = {T}$\\,K ist mit {model} $\\Delta_\\mathrm{r}H(T) = {H}$\\,kJ/mol, "
               "$\\Delta_\\mathrm{r}S(T) = {S}$\\,J/(mol\\,K), $\\Delta_\\mathrm{r}G(T) = {G}$\\,kJ/mol und $\\lg K(T) = {lgK}$. "
               "Zum Vergleich ergibt die Näherung mit konstantem $\\Delta_\\mathrm{r}H^\\circ$ und $\\Delta_\\mathrm{r}S^\\circ$ "
               "$\\lg K \\approx {lgKc}$.",
        "m_cp": "$C_p(T)$ aus NASA-7-Polynomen",
        "m_cp298": "konstantem $C_p$ (Werte bei 298,15\\,K)",
        "teq": "Im $C_p$-Modell wird $\\Delta_\\mathrm{r}G(T) = 0$ bei $T = {T}$\\,K.",
        "fig_cp": "Freie Reaktionsenthalpie in Abhängigkeit von der Temperatur: durchgezogen mit {model}, gestrichelt "
                  "Näherung mit konstantem $\\Delta_\\mathrm{r}H^\\circ$ und $\\Delta_\\mathrm{r}S^\\circ$; unter der Nulllinie "
                  "läuft die Reaktion freiwillig.",
        "lg_cp": "mit Cp(T)", "lg_c": "ΔrH°, ΔrS° konstant",
        "v_dGT": "Freie Reaktionsenthalpie bei $T$", "v_lgKT": "$\\lg K$ bei $T$",
        "kc": "Mit $\\Delta n_\\mathrm{Gas} = {dn}$ ist $K_c = K\\,(p^\\circ/(RT c^\\circ))^{\\Delta n} = {Kc}$ "
              "($c^\\circ = 1$\\,mol/L).",
        "heat": "Für den Umsatz $\\xi = {xi}$\\,mol beträgt die Reaktionswärme bei konstantem Druck "
                "$Q = \\xi\\,\\Delta_\\mathrm{r}H^\\circ = {Q}$\\,kJ.",
        "hs": "Brennwert $H_\\mathrm{s}$ (H$_2$O flüssig)", "hi": "Heizwert $H_\\mathrm{i}$ (H$_2$O gasförmig)",
        "hc": "Verbrennungsenthalpie", "hv": "{lab} von {f}: ${v}$\\,MJ/kg.",
        "fig": "Freie Reaktionsenthalpie in Abhängigkeit von der Temperatur, genähert mit konstantem $\\Delta_\\mathrm{r}H^\\circ$ "
               "und $\\Delta_\\mathrm{r}S^\\circ$; unterhalb der Nulllinie läuft die Reaktion freiwillig ab.",
        "ax_T": "$T$ in K", "ax_G": "$\\Delta_\\mathrm{r}G$ in kJ/mol",
        "v_dH": "Reaktionsenthalpie $\\Delta_\\mathrm{r}H^\\circ$", "v_dS": "Reaktionsentropie $\\Delta_\\mathrm{r}S^\\circ$",
        "v_dG": "Freie Reaktionsenthalpie $\\Delta_\\mathrm{r}G^\\circ$", "v_K": "Gleichgewichtskonstante $K$ (298,15 K)",
        "v_lgK": "$\\lg K$ (298,15 K)", "v_Ts": "Temperatur $T^*$ mit $\\Delta_\\mathrm{r}G = 0$", "v_Q": "Reaktionswärme $Q$",
        "v_hv": "Brennwert bzw. Heizwert", "missing": "Für die Thermochemie fehlen Bildungsdaten",
    },
    "en": {
        "module": "Element calculator", "title": "Reaction equation", "eq": "Reaction equation",
        "balanced": "The equation was balanced by conserving the atoms of every element{charge}.",
        "charge": " and the charge", "nuclear": "The nuclear equation conserves mass number $A$ and atomic number $Z$.",
        "given_ok": "The given coefficients are balanced.",
        "matrix": "Worked solution: every row of the species matrix $\\mathbf{{A}}$ is a conserved quantity ({rows}), every column a "
                  "species (reactants negative, products positive). The smallest positive integer coefficients "
                  "$\\nu$ with $\\mathbf{{A}}\\,\\nu = \\mathbf{{0}}$ are sought (null space of the matrix).",
        "solution": "Solution", "problem": "The equation cannot be balanced", "status": "Note",
        "bal_cap": "Balance of the balanced equation per conserved quantity.", "h_row": "Quantity", "h_l": "Reactants",
        "h_r": "Products", "stoich": "Stoichiometry", "st_cap": "Amounts and masses; molar masses from the standard atomic weights.",
        "h_sp": "Species", "h_nu": "$\\nu$", "h_M": "$M$ in g/mol", "h_n0": "$n_0$ in mol", "h_m0": "$m_0$ in g",
        "h_n": "$n$ reacted/formed in mol", "h_m": "$m$ in g", "h_rest": "Excess in g", "h_y": "Yield",
        "lim": "The limiting reagent is {sp}; the extent of reaction is $\\xi = {xi}$\\,mol.",
        "st_steps": "Worked solution: for every given reactant $n = m/M$ (or $n = c\\,V$, for gases $n = pV/(RT)$); "
                    "the possible extent is $\\xi_i = n_i/\\nu_i$. The smallest $\\xi$ identifies the limiting reagent; "
                    "formed are $n_j = \\nu_j\\,\\xi$ and $m_j = n_j\\,M_j$.",
        "gas": "Gas volume at $T = {T}$\\,K and $p = {p}$\\,Pa with $R$ from CODATA 2022.",
        "ae": "Atom economy after Trost: mass share of one product in the mass of all reactants "
              "($\\mathrm{AE} = \\nu_P M_P / \\sum \\nu_E M_E$)",
        "yield": "Yield = obtained / theoretical.",
        "mm": "Molar mass", "mm_cap": "Composition of {f}; abridged atomic weights after IUPAC/CIAAW.",
        "h_el": "Element", "h_cnt": "Count", "h_Ar": "$A_\\mathrm{r}$", "h_part": "$N \\cdot A_\\mathrm{r}$", "h_w": "Mass fraction",
        "mm_text": "$M = \\sum_i N_i\\,A_{\\mathrm{r},i} \\cdot M_\\mathrm{u}$ with $M_\\mathrm{u} \\approx 1$\\,g/mol "
                   "(relative deviation below $10^{-8}$). The uncertainty combines the uncertainties of the abridged atomic "
                   "weights (same element fully correlated, different elements independent).",
        "emp": "Elemental analysis", "emp_text": "The mass fractions give the empirical formula {e}",
        "emp_mol": " and, with the molar mass, the molecular formula {m}", "nothing": "Nothing calculated yet: enter an equation or a species.",
        "v_M": "Molar mass of {f}", "v_xi": "Extent $\\xi$", "v_m": "Theoretical mass {f}", "v_n": "Theoretical amount {f}",
        "v_y": "Yield {f}", "v_ae": "Atom economy {f}", "v_lim": "Limiting reagent", "v_eq": "Balanced equation",
        "summary": "{n} species",
        "th": "Thermochemistry", "th_cap": "Standard formation quantities at 298.15 K and 1 bar; * $\\Delta_\\mathrm{f}G^\\circ$ "
              "calculated from $\\Delta_\\mathrm{f}H^\\circ$ and $S^\\circ$.",
        "h_ph": "Phase", "h_H": "$\\Delta_\\mathrm{f}H^\\circ$ in kJ/mol", "h_G": "$\\Delta_\\mathrm{f}G^\\circ$ in kJ/mol",
        "h_S": "$S^\\circ$ in J/(mol\\,K)", "h_Cp": "$C_p^\\circ$ in J/(mol\\,K)", "h_src": "Source",
        "th_intro": "The reaction quantities follow from the standard formation quantities of the species at "
                    "$T^\\circ = 298.15$\\,K and $p^\\circ = 1$\\,bar (Hess's law; $\\nu$ negative for reactants).",
        "th_gcalc": "Where the table gives no $\\Delta_\\mathrm{f}G^\\circ$, it is calculated from $\\Delta_\\mathrm{f}G^\\circ = "
                    "\\Delta_\\mathrm{f}H^\\circ - T\\,\\Delta_\\mathrm{f}S^\\circ$ with $\\Delta_\\mathrm{f}S^\\circ = S^\\circ - "
                    "\\sum S^\\circ_\\mathrm{elements}$ (elements in their reference state).",
        "exo": "The reaction is exothermic", "endo": "The reaction is endothermic",
        "exg": "and exergonic under standard conditions", "eng": "and endergonic under standard conditions",
        "rate": "$\\Delta_\\mathrm{r}G^\\circ < 0$ only means that the reaction can proceed; it says nothing about its rate. "
                "The activation energy does not follow from the equation and the formation data but from kinetic "
                "measurements (Arrhenius plot).",
        "tstar": "At $T^* = \\Delta_\\mathrm{r}H^\\circ/\\Delta_\\mathrm{r}S^\\circ = {T}$\\,K, $\\Delta_\\mathrm{r}G = 0$ "
                 "(approximation with temperature-independent $\\Delta_\\mathrm{r}H^\\circ$ and $\\Delta_\\mathrm{r}S^\\circ$).",
        "approx": "At $T = {T}$\\,K, approximately $\\Delta_\\mathrm{r}G \\approx \\Delta_\\mathrm{r}H^\\circ - T\\,\\Delta_\\mathrm{r}S^\\circ "
                  "= {G}$\\,kJ/mol and $\\lg K \\approx {lgK}$ (neglecting the temperature dependence of $C_p$).",
        "cpt": "At $T = {T}$\\,K, with {model}, $\\Delta_\\mathrm{r}H(T) = {H}$\\,kJ/mol, "
               "$\\Delta_\\mathrm{r}S(T) = {S}$\\,J/(mol\\,K), $\\Delta_\\mathrm{r}G(T) = {G}$\\,kJ/mol and $\\lg K(T) = {lgK}$. "
               "For comparison, the approximation with constant $\\Delta_\\mathrm{r}H^\\circ$ and $\\Delta_\\mathrm{r}S^\\circ$ "
               "gives $\\lg K \\approx {lgKc}$.",
        "m_cp": "$C_p(T)$ from NASA-7 polynomials",
        "m_cp298": "constant $C_p$ (values at 298.15\\,K)",
        "teq": "In the $C_p$ model, $\\Delta_\\mathrm{r}G(T) = 0$ at $T = {T}$\\,K.",
        "fig_cp": "Gibbs energy of reaction versus temperature: solid with {model}, dashed the approximation with constant "
                  "$\\Delta_\\mathrm{r}H^\\circ$ and $\\Delta_\\mathrm{r}S^\\circ$; below the zero line the reaction is "
                  "spontaneous.",
        "lg_cp": "with Cp(T)", "lg_c": "ΔrH°, ΔrS° constant",
        "v_dGT": "Gibbs energy of reaction at $T$", "v_lgKT": "$\\lg K$ at $T$",
        "kc": "With $\\Delta n_\\mathrm{gas} = {dn}$, $K_c = K\\,(p^\\circ/(RT c^\\circ))^{\\Delta n} = {Kc}$ "
              "($c^\\circ = 1$\\,mol/L).",
        "heat": "For the extent $\\xi = {xi}$\\,mol the heat of reaction at constant pressure is "
                "$Q = \\xi\\,\\Delta_\\mathrm{r}H^\\circ = {Q}$\\,kJ.",
        "hs": "Higher heating value (H$_2$O liquid)", "hi": "Lower heating value (H$_2$O gaseous)",
        "hc": "Enthalpy of combustion", "hv": "{lab} of {f}: ${v}$\\,MJ/kg.",
        "fig": "Gibbs energy of reaction versus temperature, approximated with constant $\\Delta_\\mathrm{r}H^\\circ$ and "
               "$\\Delta_\\mathrm{r}S^\\circ$; below the zero line the reaction is spontaneous.",
        "ax_T": "$T$ in K", "ax_G": "$\\Delta_\\mathrm{r}G$ in kJ/mol",
        "v_dH": "Enthalpy of reaction $\\Delta_\\mathrm{r}H^\\circ$", "v_dS": "Entropy of reaction $\\Delta_\\mathrm{r}S^\\circ$",
        "v_dG": "Gibbs energy of reaction $\\Delta_\\mathrm{r}G^\\circ$", "v_K": "Equilibrium constant $K$ (298.15 K)",
        "v_lgK": "$\\lg K$ (298.15 K)", "v_Ts": "Temperature $T^*$ with $\\Delta_\\mathrm{r}G = 0$", "v_Q": "Heat of reaction $Q$",
        "v_hv": "Heating value", "missing": "Formation data are missing for the thermochemistry",
    },
}


# ----------------------------------------------------------------------------- Zahlen
def _sig(v: float, digits: int) -> str:
    if v == 0:
        return "0"
    d = max(0, digits - int(math.floor(math.log10(abs(v)))) - 1)
    return f"{v:.{min(d, 12)}f}"


def ntex(v, digits=4, lang="de") -> str:
    """Zahl für den Mathemodus (Dezimalkomma als {,})."""
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "-"
    if isinstance(v, int) and not isinstance(v, bool):
        return str(v)                                   # exakte Zählgrössen (Atome, Ladung, A, Z)
    v = float(v)
    a = abs(v)
    if a == 0 or 1e-3 <= a < 1e6:
        s = _sig(v, digits)
    else:
        e = int(math.floor(math.log10(a)))
        s = _sig(v / 10 ** e, digits) + f"\\cdot 10^{{{e}}}"
    return s.replace(".", "{,}") if lang == "de" else s


def _cite_end(s: str, key: str) -> str:
    """Zitat vor den Schlusspunkt setzen."""
    s = s.rstrip()
    if s.endswith("."):
        return s[:-1] + r"~\cite{%s}." % key
    return s + r"~\cite{%s}" % key


def nplain(v, digits=4, lang="de") -> str:
    if v is None:
        return "–"
    v = float(v)
    a = abs(v)
    if a == 0 or 1e-3 <= a < 1e6:
        s = _sig(v, digits)
    else:
        e = int(math.floor(math.log10(a)))
        s = _sig(v / 10 ** e, digits) + f"e{e}"
    return s.replace(".", ",") if lang == "de" else s


def _m(s: str) -> str:
    return f"${s}$"


def _with_u(M: float, u: float, lang: str) -> tuple[str, str]:
    """Wert mit Unsicherheit, gerundet auf zwei signifikante Stellen der Unsicherheit."""
    if not u:
        return ntex(M, 6, lang), nplain(M, 6, lang)
    e = int(math.floor(math.log10(u))) - 1
    nd = max(0, -e)
    mv = f"{M:.{nd}f}"
    uv = f"{u:.{nd}f}"
    if lang == "de":
        mv, uv = mv.replace(".", ","), uv.replace(".", ",")
    return f"{mv.replace(',', '{,}')} \\pm {uv.replace(',', '{,}')}", f"{mv} ± {uv}"


def _key(s: str, used: set) -> str:
    k = slugify(s, 30)
    base, i = k, 2
    while k in used:
        k = f"{base}-{i}"
        i += 1
    used.add(k)
    return k


def _frac_tex(c) -> str:
    c = Fraction(str(c))
    return str(c.numerator) if c.denominator == 1 else r"%d/%d" % (c.numerator, c.denominator)


# ----------------------------------------------------------------------------- Thermochemie
def _fill(s: str, **kw) -> str:
    """Platzhalter {name} ersetzen, ohne die geschweiften Klammern von LaTeX anzufassen."""
    for k, v in kw.items():
        s = s.replace("{" + k + "}", str(v))
    return s


def _fx(v: float, d: int, lang: str) -> str:
    """Feste Nachkommastellen, Minuszeichen und Dezimalkomma für den Mathemodus."""
    s = f"{v:.{d}f}"
    if s.lstrip("-").strip("0.") == "":
        s = s.lstrip("-")
    return s.replace(".", "{,}") if lang == "de" else s


def _fxp(v: float, d: int, lang: str) -> str:
    return _fx(v, d, lang).replace("{,}", ",")


def _ktex(lg: float, lang: str) -> tuple[str, str]:
    """K aus lg K (auch jenseits des Gleitkommabereichs): Mantisse·10^Exponent."""
    if abs(lg) < 4:
        v = 10 ** lg
        return ntex(v, 3, lang), nplain(v, 3, lang)
    e = math.floor(lg)
    m = 10 ** (lg - e)
    if m >= 9.995:
        m, e = 1.0, e + 1
    mt = f"{m:.2f}"
    if lang == "de":
        mt = mt.replace(".", ",")
    return mt.replace(",", "{,}") + r"\cdot 10^{%d}" % e, f"{mt}·10^{e}"


def _case_tex(dH: float, dS: float, lang: str) -> str:
    """Die vier Fälle nach den Vorzeichen von ΔrH° und ΔrS° als LaTeX-Satzteil."""
    h = r"$\Delta_\mathrm{r}H^\circ %s 0$" % ("<" if dH < 0 else ">")
    s = r"$\Delta_\mathrm{r}S^\circ %s 0$" % ("<" if dS < 0 else ">")
    de = lang != "en"
    if dH < 0 and dS >= 0:
        return f"{h}, {s}: " + ("freiwillig bei jeder Temperatur" if de else "spontaneous at every temperature")
    if dH < 0:
        return f"{h}, {s}: " + (r"enthalpiegetrieben, freiwillig unterhalb von $T^*$" if de else r"enthalpy-driven, spontaneous below $T^*$")
    if dS > 0:
        return f"{h}, {s}: " + (r"entropiegetrieben, freiwillig oberhalb von $T^*$" if de else r"entropy-driven, spontaneous above $T^*$")
    return f"{h}, {s}: " + ("bei keiner Temperatur freiwillig; die Rückreaktion läuft freiwillig ab" if de
                            else "not spontaneous at any temperature; the reverse reaction is")


def _thermo(b, L, lang, eqr, th, steps, tables, cite, vals):
    rows = [r for r in th["rows"] if "error" not in r]
    sp_tex = {r["i"]: C.parse_species(r["text"]).latex() for r in rows}
    coef = eqr["coefs"]

    def nu_tex(r, paren=False):
        s = _frac_tex(coef[r["i"]])
        if r["nu"] < 0:
            return f"(-{s})" if paren else f"-{s}"
        return s

    def cites_of(keys):
        return ",".join(cite(k) for k in keys if k in REFS)

    all_keys = list(dict.fromkeys(k for r in rows for k in r.get("refs") or []))
    parts = [_cite_end(L["th_intro"], cites_of(all_keys)) if all_keys else L["th_intro"]]
    if th.get("error"):
        miss = ", ".join(m["species"] for m in th.get("missing") or [])
        parts.append(tex_escape(f"{L['missing']}: {miss}."))
    if tables:
        trows = []
        for r in th["rows"]:
            if "error" in r:
                continue
            ph = r["ph"] + (f", {r['aqs']}" if r.get("aqs") else "")
            g = (_m(_fx(r["G"], 2, lang)) + (r"\,*" if r.get("Gcalc") else "")) if r.get("G") is not None else "--"
            trows.append([_m(sp_tex[r["i"]]), _m(nu_tex(r)), tex_escape(ph),
                          _m(_fx(r["H"], 2, lang)) if r.get("H") is not None else "--", g,
                          _m(_fx(r["S"], 2, lang)) if r.get("S") is not None else "--",
                          _m(_fx(r["Cp"], 2, lang)) if r.get("Cp") is not None else "--",
                          r"\cite{%s}" % cites_of(r.get("refs") or []) if r.get("refs") else tex_escape(r.get("src", ""))])
        b.add_table("thermochemie", booktabs([L["h_sp"], L["h_nu"], L["h_ph"], L["h_H"], L["h_G"], L["h_S"], L["h_Cp"], L["h_src"]],
                                             trows, "llcrrrrl", small=True, escape_header=False), L["th_cap"],
                    cites=[cites_of(all_keys)] if all_keys else None)
    if th.get("error"):
        b.add_text("thermochemie", "\n\n".join(parts) + "\n", L["th"])
        return
    dH, dS, dG = th.get("dH"), th.get("dS"), th.get("dG")
    if steps and dH is not None:
        terms = " + ".join(f"{nu_tex(r, True)} \\cdot ({_fx(r['H'], 2, lang)})" if r["H"] < 0 else
                           f"{nu_tex(r, True)} \\cdot {_fx(r['H'], 2, lang)}" for r in rows)
        parts.append(r"\[ \Delta_\mathrm{r}H^\circ = \sum_i \nu_i\,\Delta_\mathrm{f}H^\circ_i = %s = %s\ \mathrm{kJ\,mol^{-1}} \]"
                     % (terms, _fx(dH, 2, lang)))
    if steps and dS is not None:
        terms = " + ".join(f"{nu_tex(r, True)} \\cdot {_fx(r['S'], 2, lang)}" for r in rows)
        parts.append(r"\[ \Delta_\mathrm{r}S^\circ = \sum_i \nu_i\,S^\circ_i = %s = %s\ \mathrm{J\,mol^{-1}\,K^{-1}} \]"
                     % (terms, _fx(dS, 2, lang)))
    if dG is not None:
        if steps and th.get("dG_HS") is not None:
            parts.append(r"\[ \Delta_\mathrm{r}G^\circ = \Delta_\mathrm{r}H^\circ - T^\circ\,\Delta_\mathrm{r}S^\circ = %s - 298{,}15 \cdot (%s) = %s\ \mathrm{kJ\,mol^{-1}} \]"
                         .replace("{,}", "{,}" if lang == "de" else ".")
                         % (_fx(dH, 2, lang), _fx(dS / 1000, 5, lang), _fx(dG, 2, lang)))
        else:
            parts.append(r"\[ \Delta_\mathrm{r}G^\circ = %s\ \mathrm{kJ\,mol^{-1}} \]" % _fx(dG, 2, lang))
        kt, _ = _ktex(th["lgK"], lang)
        parts.append(r"\[ K = \exp\!\left(-\frac{\Delta_\mathrm{r}G^\circ}{R\,T^\circ}\right) = %s, \qquad \lg K = %s \]"
                     % (kt, _fx(th["lgK"], 2, lang)))
        sent = (L["exo"] if (dH or 0) < 0 else L["endo"]) + " " + (L["exg"] if dG < 0 else L["eng"]) + "; "
        sent += _case_tex(dH, dS, lang) + "."
        parts.append(_cite_end(sent, cite("atkins")))
    if th.get("T_star") is not None:
        parts.append(_fill(L["tstar"], T=_fx(th["T_star"], 1, lang)))
    if th.get("lgKc") is not None:
        dn = th["dn_gas"]
        parts.append(_fill(L["kc"], dn=_fx(dn, 0 if float(dn).is_integer() else 2, lang), Kc=_ktex(th["lgKc"], lang)[0]))
    be = th.get("bond_estimate")
    if be and dH is not None:                                             # ER-X01
        s = (r"Schätzung aus mittleren Bindungsenthalpien (alle Stoffe gasförmig): $\Delta_\mathrm{r}H \approx %s$\,kJ/mol "
             r"gegenüber dem Tabellenwert $%s$\,kJ/mol" if lang != "en" else
             r"Estimate from mean bond enthalpies (all species gaseous): $\Delta_\mathrm{r}H \approx %s$\,kJ/mol "
             r"compared with the tabulated $%s$\,kJ/mol") % (_fx(be["dH_est"], 0, lang), _fx(dH, 2, lang))
        parts.append(_cite_end(s + ".", cites_of(be.get("refs") or [])))
    ct = th.get("cpT") if th.get("cpT") and not th["cpT"].get("error") else None
    if ct and ct.get("model") in ("cp", "cp298"):
        mod = L["m_" + ct["model"]]
        ck = [k for k in ct.get("refs") or [] if k in ("burcat2018", "mcbride2002")]
        parts.append(_cite_end(_fill(L["cpt"], T=_fx(ct["T"], 2, lang), model=mod, H=_fx(ct["dH_T"], 2, lang),
                                     S=_fx(ct["dS_T"], 2, lang), G=_fx(ct["dG_T"], 2, lang),
                                     lgK=_fx(ct["lgK_T"], 2, lang), lgKc=_fx(ct["const"]["lgK_T"], 2, lang)),
                               cites_of(ck)))
        if ct.get("T_eq") is not None:
            parts.append(_fill(L["teq"], T=_fx(ct["T_eq"], 1, lang)))
        for n_ in ct.get("notes") or []:
            if n_ not in (th.get("notes") or []):
                parts.append(r"\textit{%s}" % tex_escape(n_))
        vals.append(("dG-T", L["v_dGT"], _m(_fx(ct["dG_T"], 2, lang) + r"\,\mathrm{kJ\,mol^{-1}}"),
                     _fxp(ct["dG_T"], 2, lang) + " kJ/mol"))
        vals.append(("lgK-T", L["v_lgKT"], _m(_fx(ct["lgK_T"], 2, lang)), _fxp(ct["lgK_T"], 2, lang)))
    elif th.get("approx_T") and th.get("dG_T") is not None:
        parts.append(_fill(L["approx"], T=_fx(th["T"], 2, lang), G=_fx(th["dG_T"], 2, lang), lgK=_fx(th["lgK_T"], 2, lang)))
    parts.append(L["rate"])
    if any(r.get("Gcalc") for r in rows):
        parts.append(L["th_gcalc"])
    notes = [f"{r['species']}: {r['phase_note']}" for r in rows if r.get("phase_note")] + list(th.get("notes") or [])
    notes += [f"{r['species']}: {r['fix']}" for r in rows if r.get("fix")]
    for n_ in dict.fromkeys(notes):
        parts.append(r"\textit{%s}" % tex_escape(n_))
    ht = th.get("heat") or {}
    if ht.get("Q_kJ") is not None and eqr.get("stoich"):
        parts.append(_fill(L["heat"], xi=ntex(eqr["stoich"]["extent"], 4, lang), Q=_fx(ht["Q_kJ"], 2, lang)))
        vals.append(("Q-r", L["v_Q"], _m(_fx(ht["Q_kJ"], 2, lang) + r"\,\mathrm{kJ}"), _fxp(ht["Q_kJ"], 2, lang) + " kJ"))
    if ht.get("combustion") and ht.get("per_reactant"):
        p = ht["per_reactant"][0]
        lab = L["hs"] if ht.get("water_phase") == "l" else L["hi"] if ht.get("water_phase") == "g" else L["hc"]
        parts.append(_fill(L["hv"], lab=lab, f=_m(sp_tex.get(p["i"], tex_escape(p["species"]))), v=_fx(-p["per_kg"] / 1000, 2, lang)))
        vals.append(("hv", L["v_hv"], _m(_fx(-p["per_kg"] / 1000, 2, lang) + r"\,\mathrm{MJ\,kg^{-1}}"),
                     _fxp(-p["per_kg"] / 1000, 2, lang) + " MJ/kg"))
    b.add_text("thermochemie", "\n\n".join(parts) + "\n", L["th"])
    # Werte für \labval
    if dH is not None:
        vals.append(("dH-r", L["v_dH"], _m(_fx(dH, 2, lang) + r"\,\mathrm{kJ\,mol^{-1}}"), _fxp(dH, 2, lang) + " kJ/mol"))
    if dS is not None:
        vals.append(("dS-r", L["v_dS"], _m(_fx(dS, 2, lang) + r"\,\mathrm{J\,mol^{-1}\,K^{-1}}"), _fxp(dS, 2, lang) + " J/(mol·K)"))
    if dG is not None:
        vals.append(("dG-r", L["v_dG"], _m(_fx(dG, 2, lang) + r"\,\mathrm{kJ\,mol^{-1}}"), _fxp(dG, 2, lang) + " kJ/mol"))
        kt, kp = _ktex(th["lgK"], lang)
        vals.append(("K-298", L["v_K"], _m(kt), kp))
        vals.append(("lgK-298", L["v_lgK"], _m(_fx(th["lgK"], 2, lang)), _fxp(th["lgK"], 2, lang)))
    if th.get("T_star") is not None:
        vals.append(("T-star", L["v_Ts"], _m(_fx(th["T_star"], 1, lang) + r"\,\mathrm{K}"), _fxp(th["T_star"], 1, lang) + " K"))
    # Abbildung ΔrG(T)
    if th.get("curve") and dH is not None and dS is not None:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        xs = [p[0] for p in th["curve"]]
        ys = [p[1] for p in th["curve"]]
        fig, ax = plt.subplots(figsize=(6.0, 3.2))
        cpc = th.get("curve_cp")
        cmod = th.get("curve_cp_model")
        if cpc:
            ax.plot(xs, ys, color="#6d28d9", lw=1.4, ls="--", label=L["lg_c"])
            ax.plot([p[0] for p in cpc], [p[1] for p in cpc], color="#0e7490", lw=1.8, label=L["lg_cp"])
            ax.legend(fontsize=8, frameon=False)
        else:
            ax.plot(xs, ys, color="#6d28d9", lw=1.8)
        ax.axhline(0, color="0.2", lw=0.8)
        ax.plot([298.15], [dH - 298.15 * dS / 1000], "o", color="#6d28d9", ms=4)
        ax.annotate("298 K", (298.15, dH - 298.15 * dS / 1000), textcoords="offset points", xytext=(5, 5), fontsize=8)
        ts = th.get("T_star")
        if ts and xs[0] <= ts <= xs[-1]:
            ax.axvline(ts, color="#0e7490", ls="--", lw=1)
            ax.annotate(f"T* = {_fxp(ts, 1, lang)} K", (ts, ax.get_ylim()[1]), textcoords="offset points",
                        xytext=(4, -12), fontsize=8, color="#0e7490")
        if th.get("approx_T") and xs[0] <= th["T"] <= xs[-1]:
            ax.plot([th["T"]], [ct["dG_T"] if ct else th["dG_T"]], "s", color="#0e7490", ms=4)
        ax.set_xlabel(L["ax_T"])
        ax.set_ylabel(L["ax_G"])
        ax.grid(alpha=0.3)
        if lang == "de":
            ax.ticklabel_format(useLocale=False)
            from matplotlib.ticker import FuncFormatter
            ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}".replace(".", ",").replace("-", "−")))
            ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}".replace(".", ",")))
        fig.tight_layout()
        fkeys = all_keys + (["burcat2018", "mcbride2002"] if cpc and cmod == "cp" else [])
        cap = _fill(L["fig_cp"], model=L["m_" + cmod]) if cpc and cmod in ("cp", "cp298") else L["fig"]
        b.add_figure(fig, "dg-t", cap, cites=[cites_of(list(dict.fromkeys(fkeys)))] if fkeys else None)


# ----------------------------------------------------------------------------- Redox, pH, Titration (Phase 5)
T["de"].update({
    "rx": "Redoxreaktion", "rx_ox": "Die Oxidationszahlen folgen der IUPAC-Definition (Bindungselektronen zum "
    "elektronegativeren Partner; Elektronegativität nach Pauling)",
    "rx_cap": "Oxidationszahlen der Stoffe; bei bekannter Struktur je Atom, sonst Mittelwert aus der Formel.",
    "h_ox": "Oxidationszahlen", "rx_chg": "Oxidiert wird {ox}, reduziert {red}; übertragen werden $n = {n}$ Elektronen je Formelumsatz.",
    "rx_none": "Die Oxidationszahlen ändern sich nicht: keine Redoxreaktion.",
    "ionic": "Ionengleichung (gelöste Salze, starke Säuren und Basen als Ionen, Zuschauerionen {sp} gekürzt):",
    "ionic0": "Ionengleichung (gelöste Salze, starke Säuren und Basen als Ionen):",
    "halves": "Halbreaktionen (Ausgleich mit Elektronen, H$^+$ bzw. OH$^-$ und Wasser):", "anode": "Oxidation (Anode)",
    "cathode": "Reduktion (Kathode)",
    "e0": "Die Standardpotenziale folgen aus den Freien Bildungsenthalpien, $E^\\circ = -\\Delta_\\mathrm{r}G^\\circ/(nF)$, "
          "gegen die Standardwasserstoffelektrode ($\\Delta_\\mathrm{f}G^\\circ(\\mathrm{H^+, aq}) = 0$, "
          "$\\Delta_\\mathrm{f}G^\\circ(\\mathrm{e^-}) = 0$)",
    "e0_dg": "Aus $\\Delta_\\mathrm{r}G^\\circ$ der Gleichung wie geschrieben (Phasen wie in der Thermochemie) folgt "
             "$E^\\circ = {E}$\\,V.",
    "spont": "Die Reaktion läuft unter Standardbedingungen freiwillig ab.", "nspont": "Die Reaktion läuft unter Standardbedingungen nicht freiwillig ab.",
    "nernst": "Nernst-Gleichung mit den eingegebenen Aktivitäten bei $T = {T}$\\,K:",
    "faraday": "Faraday-Gesetz (Stromausbeute $\\eta = {eta}$\\,\\%): $Q = {Q}$\\,C, $n(\\mathrm{e^-}) = Q/F = {ne}$\\,mol, "
               "$\\xi = \\eta\\, n(\\mathrm{e^-})/n = {xi}$\\,mol.",
    "fa_yield": "Ausbeute der Elektrolyse für {sp}: gemessen {m}\\,g, theoretisch (bei $\\eta = 100$\\,\\%) {m0}\\,g, "
                "also {y}\\,\\%.",
    "half_e": "Standardpotenzial des Redoxpaars {c} (als Reduktion):",
    "v_E0": "Standard-Zellspannung $E^\\circ$", "v_ne": "Übertragene Elektronen $n$", "v_E": "Zellspannung nach Nernst $E$",
    "v_Eh": "Standardpotenzial $E^\\circ$ {c}", "v_Yel": "Ausbeute der Elektrolyse",
    "ph": "pH-Wert", "ph_text": "Für die Lösung {mix} ergibt die Protonenbilanz (Ladungs- und Massenbilanz, Konzentrationen statt "
    "Aktivitäten) bei {tc}\\,\\textdegree C $\\mathrm{pH} = {val}$; $\\mathrm{p}K_\\mathrm{w} = {pkw}$, neutral wäre "
    "$\\mathrm{pH} = {neu}$",
    "ph_cap": "Speziesverteilung; A = vollständig deprotonierte Form; p$K_\\mathrm{a}$ bei 25\\,\\textdegree C.",
    "h_form": "Form", "h_alpha": "Anteil", "h_c": "$c$ in mol/L", "h_sys": "System", "v_pH": "pH der Lösung",
    "ti": "Titration", "ti_text": "Titration von {V0}\\,mL der Lösung {mix} mit {t} ($c = {c}$\\,mol/L); Verdünnung "
    "berücksichtigt, ideal verdünnt.", "ti_eq": "Äquivalenzpunkt{pl} (grösste Steigung): {pts}.",
    "rx_half": "{kind}: {chg}; $n = {n}$ Elektronen.",
    "ti_fig": "Berechnete Titrationskurve; gestrichelt die Äquivalenzpunkte.", "ax_V": "$V$({t}) in mL",
    "v_Veq": "Äquivalenzvolumen {k}",
    "ind_eq": "Geeigneter Indikator am Äquivalenzpunkt{k}: {items}.",
    "ind_item": "{ind} (Umschlag {lo}--{hi}, {ca} nach {cb}; Titrierfehler ${err}$\\,\\%)",
    "ind_note": "Titrierfehler = Volumen bei der Mitte des Umschlagbereichs minus Äquivalenzvolumen, bezogen auf das "
                "Äquivalenzvolumen",
})
T["en"].update({
    "rx": "Redox reaction", "rx_ox": "Oxidation numbers follow the IUPAC definition (bonding electrons to the more "
    "electronegative partner; Pauling electronegativity)",
    "rx_cap": "Oxidation numbers of the species; per atom where the structure is known, otherwise mean from the formula.",
    "h_ox": "Oxidation numbers", "rx_chg": "{ox} is oxidised, {red} reduced; $n = {n}$ electrons are transferred per formula conversion.",
    "rx_none": "No oxidation number changes: not a redox reaction.",
    "ionic": "Net ionic equation (dissolved salts, strong acids and bases as ions, spectator ions {sp} cancelled):",
    "ionic0": "Net ionic equation (dissolved salts, strong acids and bases as ions):",
    "halves": "Half-reactions (balanced with electrons, H$^+$ or OH$^-$ and water):", "anode": "Oxidation (anode)",
    "cathode": "Reduction (cathode)",
    "e0": "Standard potentials follow from the Gibbs energies of formation, $E^\\circ = -\\Delta_\\mathrm{r}G^\\circ/(nF)$, "
          "versus the standard hydrogen electrode ($\\Delta_\\mathrm{f}G^\\circ(\\mathrm{H^+, aq}) = 0$, "
          "$\\Delta_\\mathrm{f}G^\\circ(\\mathrm{e^-}) = 0$)",
    "e0_dg": "From $\\Delta_\\mathrm{r}G^\\circ$ of the equation as written (phases as in the thermochemistry), "
             "$E^\\circ = {E}$\\,V.",
    "spont": "The reaction is spontaneous under standard conditions.", "nspont": "The reaction is not spontaneous under standard conditions.",
    "nernst": "Nernst equation with the given activities at $T = {T}$\\,K:",
    "faraday": "Faraday's law (current efficiency $\\eta = {eta}$\\,\\%): $Q = {Q}$\\,C, $n(\\mathrm{e^-}) = Q/F = {ne}$\\,mol, "
               "$\\xi = \\eta\\, n(\\mathrm{e^-})/n = {xi}$\\,mol.",
    "fa_yield": "Electrolysis yield for {sp}: measured {m}\\,g, theoretical (at $\\eta = 100$\\,\\%) {m0}\\,g, "
                "i.e. {y}\\,\\%.",
    "half_e": "Standard potential of the couple {c} (as reduction):",
    "v_E0": "Standard cell potential $E^\\circ$", "v_ne": "Electrons transferred $n$", "v_E": "Cell potential (Nernst) $E$",
    "v_Eh": "Standard potential $E^\\circ$ {c}", "v_Yel": "Electrolysis yield",
    "ph": "pH", "ph_text": "For the solution {mix} the proton balance (charge and mass balance, concentrations instead of "
    "activities) at {tc}\\,\\textdegree C gives $\\mathrm{pH} = {val}$; $\\mathrm{p}K_\\mathrm{w} = {pkw}$, neutral "
    "would be $\\mathrm{pH} = {neu}$",
    "ph_cap": "Species distribution; A = fully deprotonated form; p$K_\\mathrm{a}$ at 25\\,\\textdegree C.",
    "h_form": "Form", "h_alpha": "Fraction", "h_c": "$c$ in mol/L", "h_sys": "System", "v_pH": "pH of the solution",
    "ti": "Titration", "ti_text": "Titration of {V0}\\,mL of the solution {mix} with {t} ($c = {c}$\\,mol/L); dilution "
    "included, ideal dilute solution.", "ti_eq": "Equivalence point{pl} (steepest slope): {pts}.",
    "rx_half": "{kind}: {chg}; $n = {n}$ electrons.",
    "ti_fig": "Calculated titration curve; dashed: equivalence points.", "ax_V": "$V$({t}) in mL",
    "v_Veq": "Equivalence volume {k}",
    "ind_eq": "Suitable indicator at equivalence point{k}: {items}.",
    "ind_item": "{ind} (transition {lo}--{hi}, {ca} to {cb}; titration error ${err}$\\,\\%)",
    "ind_note": "Titration error = volume at the middle of the transition range minus the equivalence volume, relative "
                "to the equivalence volume",
})


def _eq_latex(text: str) -> str:
    return C.balance(C.parse_equation(text))["latex"]


def _ox_tex(ox: str) -> str:
    return ox.replace("−", "-")


_SUBC = {c: str(i) for i, c in enumerate("₀₁₂₃₄₅₆₇₈₉")}
_SUPC = {**{c: str(i) for i, c in enumerate("⁰¹²³⁴⁵⁶⁷⁸⁹")}, "⁺": "+", "⁻": "-"}


def _uni_tex(s: str) -> str:
    """Formel in Unicode (Zn²⁺/Zn, SO₄²⁻) -> Mathemodus-Text ohne Unicode: \\mathrm{Zn^{2+}/Zn}."""
    out, i = [], 0
    while i < len(s):
        c = s[i]
        for tab, op in ((_SUBC, "_"), (_SUPC, "^")):
            if c in tab:
                j = i
                while j < len(s) and s[j] in tab:
                    j += 1
                out.append(op + "{" + "".join(tab[x] for x in s[i:j]) + "}")
                i = j
                break
        else:
            out.append("\\ " if c == " " else "{,}" if c == "," else c if c.isalnum() or c in "/()+-." else tex_escape(c))
            i += 1
    return r"\mathrm{%s}" % "".join(out)


def _redox(b, L, lang, eqr, rx, steps, tables, cite, vals):
    cards = eqr.get("cards") or []
    sp_tex = {}
    for s in rx.get("species") or []:
        try:
            sp_tex[s["i"]] = C.parse_species(cards[s["i"]]["text"]).latex()
        except (C.ChemError, IndexError, KeyError):
            sp_tex[s["i"]] = _uni_tex(s["species"])
    ox_cite = ",".join(cite(k) for k in ("karen2016", "redbook2005", "pubchem_pt"))
    parts = [_cite_end(L["rx_ox"] + ".", ox_cite)]
    chg_els = {c["el"] for c in rx.get("changes") or []}
    if tables and rx.get("species"):
        rows = []
        for s in rx["species"]:
            if s.get("error"):
                rows.append([_m(sp_tex[s["i"]]), tex_escape(s["error"])])
                continue
            by = {}
            for a in s.get("atoms") or []:
                by.setdefault(a["el"], [])
                if a["ox"] not in by[a["el"]]:
                    by[a["el"]].append(a["ox"])
            cell = ", ".join((r"\textbf{%s}" if e in chg_els else "%s") % (f"{e}~${', '.join(_ox_tex(v) for v in vs)}$")
                             for e, vs in by.items())
            rows.append([_m(sp_tex[s["i"]]), cell])
        b.add_table("oxidationszahlen", booktabs([L["h_sp"], L["h_ox"]], rows, "ll", escape_header=False), L["rx_cap"],
                    cites=[ox_cite])

    def chg(els):
        return ", ".join(f"{c['el']} (${_ox_tex(', '.join(c['from']))} \\rightarrow {_ox_tex(', '.join(c['to']))}$)"
                         for c in rx.get("changes") or [] if c["el"] in els)
    e_cite = ",".join(cite(k) for k in ("bard", "atkins"))
    if rx.get("redox") is False:
        parts.append(L["rx_none"])
    elif rx.get("half"):
        E = rx.get("E_half") or {}
        kind = rx.get("kind") or ""
        if lang == "en":
            kind = {"Oxidation": "Oxidation", "Reduktion": "Reduction"}.get(kind, kind)
        parts.append(_fill(L["rx_half"], kind=kind, chg=chg(chg_els), n=rx.get("n_frac")))
        if E.get("E0") is not None:
            parts.append(_cite_end(L["e0"] + ".", e_cite))
            parts.append(_fill(L["half_e"], c=_m(_uni_tex(rx.get("couple") or ""))))
            parts.append(r"\[ E^\circ = -\frac{\Delta_\mathrm{r}G^\circ}{nF} = -\frac{%s\ \mathrm{J\,mol^{-1}}}{%s \cdot 96\,485{,}33\ \mathrm{C\,mol^{-1}}} = %s\ \mathrm{V} \]"
                         .replace("{,}", "{,}" if lang == "de" else ".")
                         % (_fx(E["dG_red"] * 1000, 0, lang), _fx(E["n"], 0, lang), _fx(E["E0"], 3, lang)))
            vals.append(("E0-half", _fill(L["v_Eh"], c=_m(_uni_tex(rx.get("couple") or ""))),
                         _m(_fx(E["E0"], 3, lang) + r"\,\mathrm{V}"), _fxp(E["E0"], 3, lang) + " V"))
    elif rx.get("redox"):
        parts.append(_fill(L["rx_chg"], ox=chg(rx.get("oxidized") or []), red=chg(rx.get("reduced") or []),
                                        n=rx.get("n_frac")))
        ion = eqr.get("ionic") or {}
        if ion.get("text"):
            sp = ", ".join(ion.get("spectators") or [])
            sp = ", ".join(_m(_uni_tex(x)) for x in ion.get("spectators") or [])
            parts.append(_cite_end((_fill(L["ionic"], sp=sp) if sp else L["ionic0"]), cite("atkins")))
            parts.append(r"\[ %s \]" % _eq_latex(ion["text"]))
        hv = rx.get("halves") or {}
        hrows = [(L["anode"], hv.get("oxidation")), (L["cathode"], hv.get("reduction"))]
        if all(h and h.get("text") for _, h in hrows):
            parts.append(L["halves"])
            for lab, h in hrows:
                e = f",\\quad E^\\circ({_uni_tex(h['couple'])}) = {_fx(h['E0'], 3, lang)}\\ \\mathrm{{V}}" \
                    if h.get("E0") is not None else ""
                parts.append(r"%s: \[ %s%s \]" % (lab, _eq_latex(h["text"]), e))     # Vorlage ohne amsmath: kein \text
        pot = rx.get("potential") or {}
        E0 = pot.get("E0_cell", pot.get("E0"))
        if E0 is not None:
            parts.append(_cite_end(L["e0"] + ".", e_cite))
            if hv.get("E0_cell_halves") is not None:
                eo, er = hv["oxidation"]["E0"], hv["reduction"]["E0"]
                parts.append(r"\[ E^\circ = E^\circ_\mathrm{Kathode} - E^\circ_\mathrm{Anode} = %s - %s = %s\ \mathrm{V} \]"
                             .replace("Kathode", "Kathode" if lang == "de" else "cathode").replace("Anode", "Anode" if lang == "de" else "anode")
                             % (_fx(er, 3, lang), f"({_fx(eo, 3, lang)})" if eo < 0 else _fx(eo, 3, lang), _fx(E0, 3, lang)))
            dG = -float(rx["n"]) * 96485.33212 * E0 / 1000
            parts.append(r"\[ \Delta_\mathrm{r}G^\circ = -nFE^\circ = -%s \cdot %s\ \mathrm{C\,mol^{-1}} \cdot %s\ \mathrm{V} = %s\ \mathrm{kJ\,mol^{-1}} \]"
                         % (rx.get("n_frac"), "96\\,485{,}33" if lang == "de" else "96\\,485.33", _fx(E0, 3, lang), _fx(dG, 1, lang)))
            parts.append(_cite_end(L["spont"] if E0 > 0 else L["nspont"], cite("codata2022")))
            if pot.get("E0_src") == "halves" and pot.get("E0") is not None:
                parts.append(_fill(L["e0_dg"], E=_fx(pot["E0"], 3, lang)))
            vals.append(("E0-r", L["v_E0"], _m(_fx(E0, 3, lang) + r"\,\mathrm{V}"), _fxp(E0, 3, lang) + " V"))
        vals.append(("n-e", L["v_ne"], _m(str(rx.get("n_frac"))), str(rx.get("n_frac"))))
    ne = rx.get("nernst") or {}
    if ne.get("E") is not None and ne.get("lnQ"):
        E0n = ne["E"] + 8.314462618 * ne["T"] / (float(rx["n"]) * 96485.33212) * ne["lnQ"]
        parts.append(_fill(L["nernst"], T=_fx(ne["T"], 2, lang)))
        parts.append(r"\[ E = E^\circ - \frac{RT}{nF}\ln Q = %s - \frac{R \cdot %s\ \mathrm{K}}{%s F}\cdot %s = %s\ \mathrm{V} \]"
                     % (_fx(E0n, 3, lang), _fx(ne["T"], 2, lang), rx.get("n_frac"), _fx(ne["lnQ"], 3, lang), _fx(ne["E"], 3, lang)))
        vals.append(("E-r", L["v_E"], _m(_fx(ne["E"], 3, lang) + r"\,\mathrm{V}"), _fxp(ne["E"], 3, lang) + " V"))
    fa = rx.get("faraday") or {}
    if fa.get("Q") is not None and not fa.get("error"):
        parts.append(_cite_end(_fill(L["faraday"], Q=ntex(fa["Q"], 5, lang), ne=ntex(fa["n_e"], 4, lang),
                                     xi=ntex(fa["xi"], 4, lang), eta=_fx(100 * (fa.get("eta") or 1), 3, lang)),
                               cite("codata2022")))
        for w in fa.get("rows") or []:
            if w.get("yield") is not None:
                parts.append(_fill(L["fa_yield"], sp=_uni_tex(w["species"]), m=_fx(w["m_actual_g"], 4, lang),
                                   m0=_fx(w["m0_g"], 4, lang), y=_fx(100 * w["yield"], 3, lang)))
                vals.append((f"Y-el{w['i']}", L["v_Yel"], _m(_fx(100 * w["yield"], 3, lang) + r"\,\%"),
                             _fxp(100 * w["yield"], 3, lang) + " %"))
    b.add_text("redox", "\n\n".join(parts) + "\n", L["rx"])


def _ph_section(b, L, lang, state, ph, tables, cite, vals):
    mix = tex_escape((state.get("ph") or {}).get("mixture") or "")
    src_keys = [k for k in dict.fromkeys(x.get("source") for s in ph.get("species") or [] for x in (s.get("src") or {}).values())
                if k in REFS]
    keys = [cite(k) for k in ph.get("refs") or [] if k in REFS] + [cite(k) for k in src_keys]
    txt = _fill(L["ph_text"], mix=mix, val=_fx(ph["pH"], 2, lang), pkw=_fx(ph["pKw"], 3, lang),
                tc=f"{float(ph.get('T_C', 25)):g}".replace(".", "{,}" if lang == "de" else "."), neu=_fx(ph.get("pH_neutral", ph["pKw"] / 2), 2, lang))
    parts = [_cite_end(txt + ".", ",".join(keys))]
    act = ph.get("activity")
    if act:                                                               # ER-S01
        mod = {"de": {"davies": "Davies-Gleichung", "edh": "erweiterten Debye-Hückel-Gleichung"},
               "en": {"davies": "Davies equation", "edh": "extended Debye-Hückel equation"}}["en" if lang == "en" else "de"][act["model"]]
        s = (r"Mit Aktivitätskoeffizienten nach der {m} ($I = {I}$\,mol/L, $\gamma(\mathrm{{H^+}}) = {g}$) ist "
             r"$\mathrm{{pH}} = -\lg a(\mathrm{{H^+}}) = {p}$, also ${d}$ gegenüber dem idealen Wert") if lang != "en" else \
            (r"With activity coefficients from the {m} ($I = {I}$\,mol/L, $\gamma(\mathrm{{H^+}}) = {g}$), "
             r"$\mathrm{{pH}} = -\lg a(\mathrm{{H^+}}) = {p}$, i.e. ${d}$ relative to the ideal value")
        s = _fill(s.replace("{{", "{").replace("}}", "}"), m=mod, I=_fx(act["I"], 4, lang), g=_fx(act["gamma_H"], 3, lang),
                  p=_fx(act["pH"], 2, lang), d=("+" if act["dpH"] >= 0 else "") + _fx(act["dpH"], 2, lang))
        parts.append(_cite_end(s + ".", ",".join(cite(k) for k in act.get("refs") or [] if k in REFS)))
        vals.append(("pH-akt" if lang == "de" else "pH-act", "pH (Aktivität)" if lang == "de" else "pH (activity)",
                     _m(_fx(act["pH"], 2, lang)), _fxp(act["pH"], 2, lang)))
        for n_ in act.get("notes") or []:
            parts.append(r"\textit{%s}" % _ntx(n_))
    for n_ in ph.get("notes") or []:
        parts.append(r"\textit{%s}" % tex_escape(n_))
    b.add_text("ph", "\n\n".join(parts) + "\n", L["ph"])
    if tables and ph.get("species"):
        rows, seen = [], set()
        for s in ph["species"]:
            k = (str(s["pKa"]), tuple(f["charge"] for f in s["forms"]))
            if k in seen:
                continue
            seen.add(k)
            same = [x for x in ph["species"] if (str(x["pKa"]), tuple(f["charge"] for f in x["forms"])) == k]
            N = max(int(j) for j in s["pKa"])
            pk = ", ".join(f"p$K_{{\\mathrm{{a}}{N - int(j) + 1 if N > 1 else ''}}} = {_fx(v, 2, lang)}$"
                           for j, v in sorted(s["pKa"].items(), key=lambda kv: -int(kv[0])))
            name = tex_escape(" / ".join(dict.fromkeys(x["component"] for x in same)))
            for f in sorted(s["forms"], key=lambda f: -f["j"]):
                c = sum(x["forms"][s["forms"].index(f)]["c"] for x in same)
                q = f["charge"]
                lab = ("H" + (f"_{{{f['j']}}}" if f["j"] > 1 else "") if f["j"] else "") + "A" + \
                      (f"^{{{abs(q) if abs(q) > 1 else ''}{'+' if q > 0 else '-'}}}" if q else "")
                rows.append([f"{name} ({pk})" if f is sorted(s["forms"], key=lambda f: -f["j"])[0] else "",
                             _m(r"\mathrm{%s}" % lab), _m(ntex(100 * f["alpha"], 3, lang)) + r"\,\%", _m(ntex(c, 3, lang))])
        b.add_table("speziesverteilung", booktabs([L["h_sys"], L["h_form"], L["h_alpha"], L["h_c"]], rows, "llrr",
                                                  small=True, escape_header=False), L["ph_cap"],
                    cites=[",".join(cite(k) for k in src_keys)] if src_keys else None)
    vals.append(("ph", L["v_pH"], _m(_fx(ph["pH"], 2, lang)), _fxp(ph["pH"], 2, lang)))


def _indicator_text(L, lang, eqs) -> str:
    """Bester Indikator je Äquivalenzpunkt (Umschlagbereich nach Harris 2016, Titrierfehler aus der Kurve)."""
    from labcalc import acidbase as AB
    data = {i["key"]: i for i in AB.indicators()}
    out = []
    for k, e in enumerate(eqs, 1):
        good = [x for x in e.get("indicators") or [] if x["rating"] == "geeignet"][:2]
        if not good:
            continue
        items = []
        for x in good:
            r = next((r for r in data[x["key"]]["ranges"] if r["low"] == x["low"] and r["high"] == x["high"]), None)
            a, bcol = (r["acid"], r["base"]) if lang == "de" else (r["acid_en"], r["base_en"])
            name = x["name"] if lang == "de" else x["name_en"]
            err = _fx(x["error_pct"], 2, lang)
            items.append(_fill(L["ind_item"], ind=tex_escape(name), lo=_fx(x["low"], 1, lang), hi=_fx(x["high"], 1, lang),
                               ca=tex_escape(a), cb=tex_escape(bcol), err=err))
        out.append(_fill(L["ind_eq"], k=f" {k}" if len(eqs) > 1 else "", items="; ".join(items)))
    return " ".join(out) + (" " + L["ind_note"] + "." if out else "")


def _titration_section(b, L, lang, state, ti, cite, vals):
    st = state.get("titration") or {}
    eqs = ti.get("equivalence") or []
    pts = "; ".join(f"$V = {_fx(e['V'], 2, lang)}$\\,mL (pH ${_fx(e['pH'], 2, lang)}$)" for e in eqs) or "--"
    txt = _fill(L["ti_text"], V0=_fx(float(st.get("V0") or 25), 1, lang), mix=tex_escape(st.get("analyte") or ""),
                              t=tex_escape(ti.get("titrant") or ""), c=_fx(float(ti.get("c_t") or 0.1), 3, lang))
    parts = [_cite_end(txt, ",".join(cite(k) for k in ti.get("refs") or [] if k in REFS)),
             _fill(L["ti_eq"], pl="e" if len(eqs) > 1 and lang == "de" else "s" if len(eqs) > 1 else "", pts=pts)]
    ind_txt = _indicator_text(L, lang, eqs)
    if ind_txt:
        parts.append(_cite_end(ind_txt, cite("harris")))
    b.add_text("titration", "\n\n".join(parts) + "\n", L["ti"])
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(5.6, 3.4))
    ax.plot([p[0] for p in ti["points"]], [p[1] for p in ti["points"]], color="#6d28d9", lw=1.8)
    for e in eqs:
        ax.axvline(e["V"], color="#0e7490", ls="--", lw=1)
        ax.plot([e["V"]], [e["pH"]], "o", color="#0e7490", ms=4)
    ax.set_ylim(0, 14)
    ax.set_xlabel(_fill(L["ax_V"], t=tex_escape(ti.get("titrant") or "")))
    ax.set_ylabel("pH")
    ax.grid(alpha=0.3)
    if lang == "de":
        from matplotlib.ticker import FuncFormatter
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}".replace(".", ",")))
    fig.tight_layout()
    b.add_figure(fig, "titration", L["ti_fig"], cites=[",".join(cite(k) for k in ti.get("refs") or [] if k in REFS)])
    for k, e in enumerate(eqs, 1):
        vals.append((f"V-eq{k}", _fill(L["v_Veq"], k=k), _m(_fx(e["V"], 2, lang) + r"\,\mathrm{mL}"), _fxp(e["V"], 2, lang) + " mL"))


# ----------------------------------------------------------------------------- Ansetzen (ER-L09)
PT = {
    "de": {
        "sec": "Ansetzen", "ws": "Arbeitsblatt", "h_step": "Schritt", "h_calc": "Rechnung", "h_res": "Ergebnis",
        "ws_cap": "Arbeitsblatt: {what}.",
        "solid": "Für {tg} {basis} in {V}\\,mL werden {m}\\,g {form} eingewogen, gelöst und auf das Endvolumen aufgefüllt.",
        "solid_act": " Mit der Waagenauflösung gerundet ergibt das {act} {unit}.",
        "mix_head": "Mehrkomponentige Lösung ({V}\\,mL): ", "mix_item": "{m}\\,g {form} für {tg} {basis}",
        "mix_end": "; alle Bestandteile lösen und gemeinsam auf das Endvolumen auffüllen.",
        "stock": "Aus der Stammlösung von {form} ({cs}\\,mol/L {basis}) werden {Vs}\\,mL entnommen und auf {V}\\,mL "
                 "aufgefüllt (Verdünnung 1\\,:\\,{dil}).",
        "stock_m": " Alternativ werden {ms}\\,g Stammlösung gewogen.",
        "series": "Verdünnungsreihe 1\\,:\\,{f} über {n} Stufen ab {c0}\\,{unit}; je Stufe bleiben {keep}\\,mL. Aus der "
                  "Ausgangslösung werden {need}\\,mL gebraucht. Jede Stufe wird auf das Gesamtvolumen aufgefüllt.",
        "series_cap": "Verdünnungsreihe 1\\,:\\,{f}: Übertrag aus der vorherigen Stufe und Gesamtvolumen.",
        "h_lvl": "Stufe", "h_c": "$c$ in {unit}", "h_tr": "Übertrag in mL", "h_fill": "auffüllen auf mL",
        "mixs": "Mischungsrechnung mit der Stoffbilanz $\\sum_i c_i V_i = c\\,V$: {parts}; aufgefüllt auf {Vf}\\,mL mit "
                "$c = {cf}$. Gesucht war {what}.",
        "mixs_c": "die Konzentration von Anteil {i}", "mixs_V": "das Volumen von Anteil {i}",
        "mixs_cf": "die Endkonzentration", "mixs_Vf": "das Endvolumen",
        "buf": "Puffer pH {pH} ({c}\\,mol/L, {V}\\,mL): {items}{tit}. Kontrolle mit der Protonenbilanz bei {T}\\,\\textdegree{}C: "
               "pH {chk}, Ionenstärke {I}\\,mol/L. Gerechnet mit Konzentrationen statt Aktivitäten; der pH wird mit dem "
               "pH-Meter nachgestellt.",
        "buf_tit": " und {Vt} {t}",
        "gas_id": "Ideales Gasgesetz $pV = nRT$: {solved} aus den übrigen Grössen ({vals}).",
        "gas_rho": "Gasdichte $\\rho = pM/(RT)$ von {f} bei {T}\\,K und {p}\\,kPa: {rho}\\,g/L.",
        "gas_mix": "Partialdrücke nach Dalton bei {pt}\\,{pu}: {items}.",
        "gas_note": "Ideales Verhalten angenommen; bei hohem Druck oder tiefer Temperatur weichen reale Gase ab.",
        "rx": "Reaktionsansatz", "rx_text": "Ansatz für {eq}; Bezug {ref}. Limitierend ist {lim}.",
        "rx_cap": "Reaktionsansatz: Stoffmengen, Massen und Volumina; Lösungsmittel und Zusätze gehen nicht in die "
                  "Stöchiometrie ein.",
        "h_sp": "Stoff", "h_role": "Rolle", "h_nu": "$\\nu$", "h_eq": "Äq.", "h_n": "$n$ in mmol", "h_m": "$m$ in g",
        "h_V": "$V$ in mL",
        "role": {"reactant": "Edukt", "reagent": "Reagenz", "product": "Produkt (theor.)", "solvent": "Lösungsmittel",
                 "catalyst": "Katalysator", "additive": "Zusatz"},
        "cond": "Bedingungen: {c}.",
        "obs": "Isoliert: {items}.", "obs_item": "{m}\\,g {sp} (Ausbeute {y}\\,\\%)",
        "met": "Kennzahlen für {p} (Produktmasse {basis}, {mp}\\,g): E-Faktor {E}, PMI {PMI}, RME {RME}\\,\\%, "
               "Lösungsmittelanteil {S}\\,\\%{ae}. Zählgrenze: {bd}.",
        "met_ae": ", Atomökonomie {ae}\\,\\%",
        "met_note": "PMI = E-Faktor + 1 gilt bei gleicher Zählgrenze.",
        "cmp": "Vergleich der Ansätze", "cmp_text": "Die Ansätze werden mit ihrer jeweils angegebenen Zählgrenze "
                                                   "verglichen; Werte sind nur bei gleicher Zählgrenze direkt vergleichbar.",
        "cmp_cap": "Grüne Kennzahlen der gemerkten Ansätze.",
        "r_prod": "Produktmasse in g", "r_basis": "Grundlage", "r_in": "Einsatz in g", "r_E": "E-Faktor", "r_PMI": "PMI",
        "r_RME": "RME in \\%", "r_S": "Lösungsmittelanteil in \\%", "r_AE": "Atomökonomie in \\%", "r_bd": "Zählgrenze",
        "v_m": "Einwaage {f}", "v_Vs": "Volumen Stammlösung {f}", "v_E": "E-Faktor", "v_PMI": "Prozessmassenintensität PMI",
        "v_RME": "Reaktionsmasseneffizienz RME", "v_buf": "Einwaage {f} (Puffer)",
        "basis_iso": "isoliert", "basis_th": "theoretisch",
    },
    "en": {
        "sec": "Preparation", "ws": "Worksheet", "h_step": "Step", "h_calc": "Calculation", "h_res": "Result",
        "ws_cap": "Worksheet: {what}.",
        "solid": "For {tg} {basis} in {V}\\,mL, {m}\\,g {form} are weighed, dissolved and made up to volume.",
        "solid_act": " Rounded to the balance resolution this gives {act} {unit}.",
        "mix_head": "Multi-component solution ({V}\\,mL): ", "mix_item": "{m}\\,g {form} for {tg} {basis}",
        "mix_end": "; dissolve all components and make up to volume together.",
        "stock": "From the stock solution of {form} ({cs}\\,mol/L {basis}), {Vs}\\,mL are taken and made up to {V}\\,mL "
                 "(dilution 1\\,:\\,{dil}).",
        "stock_m": " Alternatively, {ms}\\,g of stock solution are weighed.",
        "series": "Dilution series 1\\,:\\,{f} over {n} steps from {c0}\\,{unit}; {keep}\\,mL remain at each step. "
                  "{need}\\,mL of the starting solution are needed. Each step is made up to its total volume.",
        "series_cap": "Dilution series 1\\,:\\,{f}: transfer from the previous step and total volume.",
        "h_lvl": "Step", "h_c": "$c$ in {unit}", "h_tr": "Transfer in mL", "h_fill": "Make up to mL",
        "mixs": "Mixing calculation from the mass balance $\\sum_i c_i V_i = c\\,V$: {parts}; made up to {Vf}\\,mL with "
                "$c = {cf}$. Solved for {what}.",
        "mixs_c": "the concentration of part {i}", "mixs_V": "the volume of part {i}",
        "mixs_cf": "the final concentration", "mixs_Vf": "the final volume",
        "buf": "Buffer pH {pH} ({c}\\,mol/L, {V}\\,mL): {items}{tit}. Check with the proton balance at {T}\\,\\textdegree{}C: "
               "pH {chk}, ionic strength {I}\\,mol/L. Calculated with concentrations instead of activities; the pH is "
               "adjusted with a pH meter.",
        "buf_tit": " and {Vt} {t}",
        "gas_id": "Ideal gas law $pV = nRT$: {solved} from the other quantities ({vals}).",
        "gas_rho": "Gas density $\\rho = pM/(RT)$ of {f} at {T}\\,K and {p}\\,kPa: {rho}\\,g/L.",
        "gas_mix": "Dalton partial pressures at {pt}\\,{pu}: {items}.",
        "gas_note": "Ideal behaviour assumed; real gases deviate at high pressure or low temperature.",
        "rx": "Reaction set-up", "rx_text": "Set-up for {eq}; reference {ref}. The limiting reactant is {lim}.",
        "rx_cap": "Reaction set-up: amounts, masses and volumes; solvents and additives are not part of the stoichiometry.",
        "h_sp": "Substance", "h_role": "Role", "h_nu": "$\\nu$", "h_eq": "Equiv.", "h_n": "$n$ in mmol", "h_m": "$m$ in g",
        "h_V": "$V$ in mL",
        "role": {"reactant": "reactant", "reagent": "reagent", "product": "product (theor.)", "solvent": "solvent",
                 "catalyst": "catalyst", "additive": "additive"},
        "cond": "Conditions: {c}.",
        "obs": "Isolated: {items}.", "obs_item": "{m}\\,g {sp} (yield {y}\\,\\%)",
        "met": "Metrics for {p} (product mass {basis}, {mp}\\,g): E-factor {E}, PMI {PMI}, RME {RME}\\,\\%, solvent share "
               "{S}\\,\\%{ae}. Counting boundary: {bd}.",
        "met_ae": ", atom economy {ae}\\,\\%",
        "met_note": "PMI = E-factor + 1 holds for the same counting boundary.",
        "cmp": "Comparison of set-ups", "cmp_text": "The set-ups are compared with their own stated counting boundary; "
                                                   "values are directly comparable only for the same boundary.",
        "cmp_cap": "Green metrics of the saved set-ups.",
        "r_prod": "Product mass in g", "r_basis": "Basis", "r_in": "Input in g", "r_E": "E-factor", "r_PMI": "PMI",
        "r_RME": "RME in \\%", "r_S": "Solvent share in \\%", "r_AE": "Atom economy in \\%", "r_bd": "Counting boundary",
        "v_m": "Mass {f}", "v_Vs": "Volume of stock {f}", "v_E": "E-factor", "v_PMI": "Process mass intensity PMI",
        "v_RME": "Reaction mass efficiency RME", "v_buf": "Mass {f} (buffer)",
        "basis_iso": "isolated", "basis_th": "theoretical",
    },
}
_BD_EN = {"reagents": "reactants and reagents", "solvents": "solvents", "catalyst": "catalyst", "additives": "additives",
          "workup": "work-up and purification"}
_PX = {"ξ": r"$\xi$", "η": r"$\eta$", "ω": r"$\omega$", "κ": r"$\kappa$", "χ": r"$\chi$", "Σ": r"$\Sigma$",
       "ᵢ": r"$_i$", "₊": r"$_+$", "₋": r"$_-$", " ": r"\,", " ": r"\,", " ": "~", "≙": r"$\widehat{=}$"}


def _ptx(s) -> str:
    """Text aus labcalc (Unicode: Indizes, griechische Buchstaben) -> LaTeX-Text, nur Latin-1."""
    s = "".join(_PX.get(ch, ch) if ch in _PX else ch for ch in str(s))
    parts = re.split(r"(\$[^$]*\$|\\,)", s)
    out = "".join(p if (p.startswith("$") and p.endswith("$") and len(p) > 1) or p == r"\," else tex_escape(p)
                  for p in parts)
    return "".join(ch if ord(ch) < 256 else "?" for ch in out).replace("$$", "")


def _fu(s: str) -> str:
    """Unicode-Formel mit Hydratpunkt (CuSO₄·5H₂O) -> Mathemodus ohne verschachteltes $."""
    return r"\cdot ".join(_uni_tex(p) for p in str(s).replace("*", "·").split("·"))


def _sp_tex(s: str) -> str:
    """Formel als Mathemodus-Text; Namen (z. B. Tris) als Text."""
    try:
        return _m(C.parse_species(str(s).strip()).latex())
    except Exception:  # noqa: BLE001
        return _ptx(s)


def _worksheet(b, P, lang, r, tid, what, cite):
    """Arbeitsblatt (Schritte aus labcalc.prep) als Tabelle; Quellen als \\cite."""
    rows = []
    for s in r.get("steps") or []:
        src = s.get("source") or ""
        if src in REFS:
            src_t = r"~\cite{%s}" % cite(src)
        elif src:
            src_t = " (" + _ptx(src) + ")"
        else:
            src_t = ""
        if s.get("value") is None:
            rows.append([r"\textit{%s}" % _ptx(s["text"]), "", ""])
            continue
        v = s["value"]
        val = _m(ntex(v, 5, lang)) if isinstance(v, (int, float)) else _ptx(v)
        frm = _ptx(s.get("formula") or "")
        if lang == "de":
            frm = re.sub(r"(\d)\.(\d)", r"\1,\2", frm)
        rows.append([_ptx(s["text"]), frm + src_t, val + (r"\," + _ptx(s.get("unit")) if s.get("unit") else "")])
    if rows:
        b.add_table(tid, booktabs([P["h_step"], P["h_calc"], P["h_res"]], rows, "p{4.2cm}p{6.2cm}r", small=True,
                                  escape_header=False), _fill(P["ws_cap"], what=what))


def _prep_section(b, lang, res, steps, tables, cite, vals, used):
    P = PT["en" if lang == "en" else "de"]
    paras: list[str] = []
    keys: list[str] = []

    def refs_of(r):
        return [k for k in r.get("refs") or [] if k in REFS]

    def unit_t(u):
        return _ptx(u)

    for k, it in enumerate(res.get("prep") or [], 1):
        kind, r = it["kind"], it["result"]
        txt = ""
        if kind == "solid":
            comps = r.get("components") or [r]
            items = []
            for c in comps:
                tg = _m(ntex(c["target"]["value"], 4, lang)) + r"\," + unit_t(c["target"]["unit"])
                m_ = c.get("mass_rounded_g") or c["mass_g"]
                items.append(_fill(P["mix_item"] if len(comps) > 1 else P["solid"], tg=tg, basis=_m(_fu(c["basis"]["formula"])),
                                   V=_m(ntex(c["V_L"] * 1000, 4, lang)), m=_m(ntex(m_, 4, lang)),
                                   form=_m(_fu(c["form"]["formula"]))))
                if len(comps) == 1 and c.get("actual_value") is not None:
                    items[-1] += _fill(P["solid_act"], act=_m(ntex(c["actual_value"], 4, lang)), unit=unit_t(c["target"]["unit"]))
                vals.append((_key("einwaage-" + c["form"]["formula"], used), _fill(P["v_m"], f=_m(_fu(c["form"]["formula"]))),
                             _m(ntex(m_, 4, lang) + r"\,\mathrm{g}"), nplain(m_, 4, lang) + " g"))
            txt = (P["mix_head"].replace("{V}", _m(ntex(r["V_L"] * 1000, 4, lang))) + "; ".join(items) + P["mix_end"]) \
                if len(comps) > 1 else items[0]
            if steps and lang == "de":
                for j, c in enumerate(comps, 1):
                    _worksheet(b, P, lang, c, f"arbeitsblatt-{k}-{j}", _m(_fu(c["form"]["formula"])), cite)
        elif kind == "stock":
            txt = _fill(P["stock"], form=_m(_fu(r["form"]["formula"])), cs=_m(ntex(r["c_stock"], 4, lang)),
                        basis=_m(_fu(r["basis"]["formula"])), Vs=_m(ntex(r["V_stock_mL"], 4, lang)),
                        V=_m(ntex(r["V_L"] * 1000, 4, lang)), dil=_m(ntex(r["dilution"], 4, lang)))
            if r.get("m_stock_g") is not None:
                txt += _fill(P["stock_m"], ms=_m(ntex(r["m_stock_g"], 4, lang)))
            vals.append((_key("stamm-" + r["form"]["formula"], used), _fill(P["v_Vs"], f=_m(_fu(r["form"]["formula"]))),
                         _m(ntex(r["V_stock_mL"], 4, lang) + r"\,\mathrm{mL}"), nplain(r["V_stock_mL"], 4, lang) + " mL"))
            if steps and lang == "de":
                _worksheet(b, P, lang, r, f"arbeitsblatt-{k}", _m(_fu(r["form"]["formula"])), cite)
        elif kind == "series":
            rows = r["rows"]
            txt = _fill(P["series"], f=_m(ntex(r["factor"], 4, lang)), n=len(rows), c0=_m(ntex(r["c0"], 4, lang)),
                        unit=unit_t(r["unit"]), keep=_m(ntex(rows[0]["keep_mL"], 4, lang)),
                        need=_m(ntex(r["stock_needed_mL"], 4, lang)))
            if tables:
                trs = [[str(x["step"]), _m(ntex(x["c"], 4, lang)), _m(ntex(x["transfer_mL"], 4, lang)),
                        _m(ntex(x["fill_to_mL"], 4, lang))] for x in rows]
                b.add_table(f"verduennungsreihe-{k}", booktabs([P["h_lvl"], _fill(P["h_c"], unit=unit_t(r["unit"])),
                                                               P["h_tr"], P["h_fill"]], trs, "rrrr", escape_header=False),
                            _fill(P["series_cap"], f=_m(ntex(r["factor"], 4, lang))))
        elif kind == "mixsolve":
            sv = r["solved"]
            what = {"c": P["mixs_c"], "V": P["mixs_V"], "cf": P["mixs_cf"], "Vf": P["mixs_Vf"]}[sv["what"]]
            what = what.replace("{i}", str((sv["index"] or 0) + 1))
            parts = ", ".join(f"$c_{{{j}}} = {ntex(p['c'], 4, lang)}$, $V_{{{j}}} = {ntex(p['V'], 4, lang)}$\\,mL"
                              for j, p in enumerate(r["parts"], 1))
            txt = _fill(P["mixs"], parts=parts, Vf=_m(ntex(r["V_final"], 4, lang)), cf=ntex(r["c_final"], 4, lang), what=what)
        elif kind == "buffer":
            items = ", ".join(f"{_m(ntex(p['mass_g'], 4, lang))}\\,g {_m(_fu(p['substance']))}" for p in r["parts"])
            tit = ""
            t = r.get("titrant")
            if t:
                amt = (_m(ntex(t["V_mL"], 4, lang)) + r"\,mL " + _fill(r"({c}\,mol/L)", c=_m(ntex(float((it["req"].get("stock") or {}).get("value") or 0), 3, lang)))
                       if t.get("V_mL") is not None else _m(ntex(t["n_mol"] * 1000, 4, lang)) + r"\,mmol")
                tit = _fill(P["buf_tit"], Vt=amt, t=_sp_tex(t["substance"]))
            txt = _fill(P["buf"], pH=_m(_fx(r["pH"], 2, lang)), c=_m(ntex(r["c_total"], 4, lang)),
                        V=_m(ntex(r["V_L"] * 1000, 4, lang)), items=items, tit=tit,
                        T=_m(f"{r['T_C']:g}".replace(".", "{,}" if lang == "de" else ".")),
                        chk=_m(_fx(r["check"]["pH"], 3, lang)), I=_m(ntex(r["check"]["I"], 3, lang)))
            for p in r["parts"]:
                vals.append((_key("puffer-" + p["substance"], used), _fill(P["v_buf"], f=_m(_fu(p["substance"]))),
                             _m(ntex(p["mass_g"], 4, lang) + r"\,\mathrm{g}"), nplain(p["mass_g"], 4, lang) + " g"))
            if steps and lang == "de":
                _worksheet(b, P, lang, r, f"arbeitsblatt-{k}", "Puffer pH " + _m(_fx(r["pH"], 2, lang)), cite)
        elif kind == "gas":
            gp = []
            gi = r.get("ideal")
            if gi:
                names = {"p": "$p$", "V": "$V$", "n": "$n$", "T": "$T$"}
                u = gi["units"]
                sv = gi["solved"]
                others = ", ".join(f"{names[q]} = {_m(ntex(gi['values'][q], 5, lang))}\\,{unit_t(u[q])}"
                                   for q in ("p", "V", "n", "T") if q != sv)
                gp.append(_fill(P["gas_id"], solved=f"{names[sv]} = {_m(ntex(gi['value'], 5, lang))}\\,{unit_t(u[sv])}",
                                vals=others))
            gd = r.get("density")
            if gd:
                gp.append(_fill(P["gas_rho"], f=_sp_tex(it["req"].get("formula") or ""),
                                T=_m(ntex(gd["T_K"], 5, lang)), p=_m(ntex(gd["p_Pa"] / 1000, 5, lang)),
                                rho=_m(ntex(gd["rho_g_L"], 4, lang))))
            gm = r.get("mixture")
            if gm:
                its = "; ".join(f"{_sp_tex(name)} {_m(ntex(c['p'], 4, lang))}\\,{unit_t(gm['p_unit'])}"
                                for name, c in gm["components"].items())
                gp.append(_fill(P["gas_mix"], pt=_m(ntex(gm["p_total"], 5, lang)), pu=unit_t(gm["p_unit"]), items=its))
            if gp:
                txt = " ".join(gp) + " " + P["gas_note"]
        elif kind == "reaction":
            _reaction_block(b, P, lang, it, r, k, tables, cite, vals, used, paras)
            keys += refs_of(r["plan"]) + (refs_of(r["metrics"]) if r.get("metrics") else [])
            continue
        if txt:
            ks = refs_of(r) if kind != "solid" else refs_of(r.get("components", [r])[0]) or refs_of(r)
            keys += ks
            paras.append(_cite_end(txt, ",".join(cite(x) for x in dict.fromkeys(ks))) if ks else txt)
    plans = [p for p in res.get("plans") or [] if p["result"].get("metrics")]
    if plans:
        paras.append(r"\paragraph{%s} %s" % (P["cmp"], P["cmp_text"]))
        cols = [_ptx(p["label"] or f"#{i}") for i, p in enumerate(plans, 1)]
        ms = [p["result"]["metrics"] for p in plans]
        bd_t = [_ptx(m["boundary_text"]) if lang == "de" else
                _ptx(", ".join(_BD_EN[k] for k, v in m["boundary"].items() if v)) for m in ms]
        rows = [[P["r_prod"]] + [_m(ntex(m["m_product_g"], 4, lang)) for m in ms],
                [P["r_basis"]] + [P["basis_iso"] if m["product_basis"] == "isoliert" else P["basis_th"] for m in ms],
                [P["r_in"]] + [_m(ntex(m["m_in_g"], 4, lang)) for m in ms],
                [P["r_E"]] + [_m(ntex(m["E_factor"], 3, lang)) for m in ms],
                [P["r_PMI"]] + [_m(ntex(m["PMI"], 3, lang)) for m in ms],
                [P["r_RME"]] + [_m(ntex(100 * m["RME"], 3, lang)) for m in ms],
                [P["r_S"]] + [_m(ntex(100 * m["solvent_share"], 3, lang)) for m in ms],
                [P["r_AE"]] + [_m(ntex(100 * m["atom_economy"], 3, lang)) if m.get("atom_economy") else "--" for m in ms],
                [P["r_bd"]] + bd_t]
        mk = [x for x in plans[0]["result"]["metrics"]["refs"] if x in REFS]
        b.add_table("ansatzvergleich", booktabs([""] + cols, rows, "l" + "p{3.2cm}" * len(cols), small=True,
                                                escape_header=False), P["cmp_cap"],
                    cites=[",".join(cite(x) for x in mk)] if mk else None)
    if paras:
        b.add_text("ansetzen", "\n\n".join(paras) + "\n", P["sec"])


def _reaction_block(b, P, lang, it, r, k, tables, cite, vals, used, paras):
    p = r["plan"]
    sp = {t["i"]: t["species"] for t in r["terms"]}
    eq = _eq_latex(p["equation"])
    ref = _m(_fu(sp[p["reference"]])) if p.get("reference") is not None else "--"
    txt = _fill(P["rx_text"], eq=_m(eq), ref=ref, lim=_m(_fu(sp[p["limiting"]])))
    cond = {kk: v for kk, v in (p.get("conditions") or {}).items() if str(v).strip()}
    if cond:
        txt += " " + _fill(P["cond"], c=", ".join(f"{_ptx(kk)} {_ptx(v)}" for kk, v in cond.items()))
    obs = p.get("observed") or {}
    oi = []
    for i, o in obs.items():
        if o.get("kind") == "product":
            oi.append(_fill(P["obs_item"], m=_m(ntex(o["m_g"], 4, lang)), sp=_m(_fu(sp[int(i)])),
                            y=_m(ntex(100 * o["yield"], 3, lang))))
    if oi:
        txt += " " + _fill(P["obs"], items="; ".join(oi))
    pk = [x for x in p.get("refs") or [] if x in REFS]
    paras.append(r"\paragraph{%s} " % P["rx"] + (_cite_end(txt, ",".join(cite(x) for x in pk)) if pk else txt))
    if tables:
        rows = []
        for x in p["reactants"]:
            rows.append([_m(_fu(x["species"])) + (r"\textsuperscript{*}" if x.get("limiting") else ""),
                         P["role"][x["role"]], _m(_frac_tex(x["nu"])), _m(ntex(x["equiv"], 3, lang)),
                         _m(ntex(x["n_mol"] * 1000, 4, lang)), _m(ntex(x["m_g"], 4, lang)) if x.get("m_g") is not None else "--",
                         _m(ntex(x["V_mL"], 4, lang)) if x.get("V_mL") is not None else ""])
        for e in p["extras"]:
            rows.append([_ptx(e["name"]), P["role"][e["role"]], "", (_m(ntex(e["value"], 3, lang)) + r"\,mol\,\%") if e["unit"] == "mol%" else "",
                         _m(ntex(e["n_mol"] * 1000, 4, lang)) if e.get("n_mol") is not None else "",
                         _m(ntex(e["m_g"], 4, lang)) if e.get("m_g") is not None else "",
                         _m(ntex(e["V_mL"], 4, lang)) if e.get("V_mL") is not None else ""])
        for x in p["products"]:
            rows.append([_m(_fu(x["species"])), P["role"]["product"], _m(_frac_tex(x["nu"])), "",
                         _m(ntex(x["n_theor_mol"] * 1000, 4, lang)),
                         _m(ntex(x["m_theor_g"], 4, lang)) if x.get("m_theor_g") is not None else "--", ""])
        lim_note = r"\textsuperscript{*}\," + ("limitierend" if lang == "de" else "limiting")
        b.add_table(f"reaktionsansatz-{k}", booktabs([P["h_sp"], P["h_role"], P["h_nu"], P["h_eq"], P["h_n"], P["h_m"], P["h_V"]],
                                                     rows, "llrrrrr", small=True, escape_header=False),
                    P["rx_cap"], notes=lim_note, cites=[",".join(cite(x) for x in ["ciaaw2024", "ciaaw2021"] if x in REFS)])
    m = r.get("metrics")
    if m:
        bd = m["boundary_text"] if lang == "de" else \
            "counted: " + ", ".join(_BD_EN[kk] for kk, v in m["boundary"].items() if v) + \
            ("; not counted: " + ", ".join(_BD_EN[kk] for kk, v in m["boundary"].items() if not v)
             if not all(m["boundary"].values()) else "")
        mt = _fill(P["met"], p=_m(_fu(m["product"])),
                   basis=P["basis_iso"] if m["product_basis"] == "isoliert" else P["basis_th"],
                   mp=_m(ntex(m["m_product_g"], 4, lang)), E=_m(ntex(m["E_factor"], 3, lang)), PMI=_m(ntex(m["PMI"], 3, lang)),
                   RME=_m(ntex(100 * m["RME"], 3, lang)), S=_m(ntex(100 * m["solvent_share"], 3, lang)),
                   ae=_fill(P["met_ae"], ae=_m(ntex(100 * m["atom_economy"], 3, lang))) if m.get("atom_economy") else "",
                   bd=_ptx(bd))
        mk = [x for x in m.get("refs") or [] if x in REFS]
        paras.append(_cite_end(mt, ",".join(cite(x) for x in mk)) + " " + P["met_note"] if mk else mt + " " + P["met_note"])
        for key, lab, v in (("e-faktor", P["v_E"], m["E_factor"]), ("pmi", P["v_PMI"], m["PMI"])):
            vals.append((_key(key, used), lab, _m(ntex(v, 3, lang)), nplain(v, 3, lang)))
        vals.append((_key("rme", used), P["v_RME"], _m(ntex(100 * m["RME"], 3, lang)) + r"\,\%", nplain(100 * m["RME"], 3, lang) + " %"))
    elif r.get("metrics_error"):
        paras.append(r"\textit{%s}" % _ptx(r["metrics_error"]))


# ----------------------------------------------------------------------------- Molekülkarte (ER-401/402)
DT = {
    "de": {"sec": "Molekül", "fig": "Struktur von {n} (gezeichnet im Moleküleditor).",
           "text": "{n} hat die Summenformel {f} und die molare Masse {M}\\,g/mol{cite_aw}. Herkunft des Namens: {src}.",
           "src_coll": "Sammlung des Elementrechners", "src_own": "eigener Stoff", "src_rule": "nach Regeln erzeugt",
           "src_pub": "PubChem, CID {cid}", "src_user": "selbst vergeben", "noname": "Die gezeichnete Struktur",
           "groups": "Erkannte funktionelle Gruppen: {g}.",
           "est": "Geschätzte Werte sind keine Messwerte; sie stammen aus Inkrement- und Gruppenbeitragsverfahren und "
                  "sind in der Tabelle als Schätzung gekennzeichnet.",
           "cap": "Kennwerte der Struktur. Art: exakt (aus der Struktur), abgeleitet (aus anderen Werten), Schätzung "
                  "(Verfahren in der letzten Spalte).",
           "h_q": "Grösse", "h_v": "Wert", "h_k": "Art", "h_s": "Methode / Quelle",
           "exact": "exakt", "calc": "abgeleitet", "est_k": "Schätzung",
           "r_f": "Summenformel (Hill)", "r_M": "Molare Masse", "r_mono": "Monoisotopische Masse", "r_dbe": "Doppelbindungsäquivalente",
           "r_q": "Ladung", "r_hb": "H-Brücken-Donoren / -Akzeptoren", "r_rot": "Drehbare Bindungen", "r_st": "Stereozentren",
           "r_logP": "$\\log P$ (Octanol/Wasser)", "r_logS": "$\\log S$ (Wasser, mol/L)", "r_tpsa": "Polare Oberfläche TPSA",
           "r_Tb": "Siedepunkt (1 atm)", "r_Tm": "Schmelzpunkt", "r_Tc": "Kritische Temperatur", "r_Pc": "Kritischer Druck",
           "r_Vc": "Kritisches Volumen", "r_dfH": "$\\Delta_\\mathrm{f}H^\\circ$(g, 298 K)",
           "r_dfG": "$\\Delta_\\mathrm{f}G^\\circ$(g, 298 K)", "r_S": "$S^\\circ$(g, 298 K)", "r_Cp": "$C_p^\\circ$(g, 298 K)",
           "r_Hvap": "Verdampfungsenthalpie bei $T_\\mathrm{b}$", "r_Hfus": "Schmelzenthalpie",
           "m_hill": "Hill-Schreibweise", "m_dbe": "C $-$ H/2 + N/2 + 1", "m_mono": "häufigstes Isotop je Element",
           "m_count": "Zählregel", "m_inc": "Inkrementverfahren", "m_job": "Gruppenbeiträge (Joback)",
           "m_ben": "Benson-Gruppenadditivität (Vorrang vor Joback)",
           "m_S": "aus $\\Delta_\\mathrm{f}H^\\circ$ und $\\Delta_\\mathrm{f}G^\\circ$ (Joback), $S^\\circ$ der Elemente",
           "ocl": "berechnet im Browser mit OpenChemLib", "v_M": "Molare Masse {f}"},
    "en": {"sec": "Molecule", "fig": "Structure of {n} (drawn in the molecule editor).",
           "text": "{n} has the molecular formula {f} and the molar mass {M}\\,g/mol{cite_aw}. Origin of the name: {src}.",
           "src_coll": "Elementrechner collection", "src_own": "own substance", "src_rule": "generated by rules",
           "src_pub": "PubChem, CID {cid}", "src_user": "chosen by the user", "noname": "The drawn structure",
           "groups": "Functional groups recognised: {g}.",
           "est": "Estimated values are not measurements; they come from increment and group-contribution methods and "
                  "are marked as estimates in the table.",
           "cap": "Properties of the structure. Kind: exact (from the structure), derived (from other values), estimate "
                  "(method in the last column).",
           "h_q": "Quantity", "h_v": "Value", "h_k": "Kind", "h_s": "Method / source",
           "exact": "exact", "calc": "derived", "est_k": "estimate",
           "r_f": "Molecular formula (Hill)", "r_M": "Molar mass", "r_mono": "Monoisotopic mass", "r_dbe": "Double-bond equivalents",
           "r_q": "Charge", "r_hb": "H-bond donors / acceptors", "r_rot": "Rotatable bonds", "r_st": "Stereocentres",
           "r_logP": "$\\log P$ (octanol/water)", "r_logS": "$\\log S$ (water, mol/L)", "r_tpsa": "Polar surface area TPSA",
           "r_Tb": "Boiling point (1 atm)", "r_Tm": "Melting point", "r_Tc": "Critical temperature", "r_Pc": "Critical pressure",
           "r_Vc": "Critical volume", "r_dfH": "$\\Delta_\\mathrm{f}H^\\circ$(g, 298 K)",
           "r_dfG": "$\\Delta_\\mathrm{f}G^\\circ$(g, 298 K)", "r_S": "$S^\\circ$(g, 298 K)", "r_Cp": "$C_p^\\circ$(g, 298 K)",
           "r_Hvap": "Enthalpy of vaporisation at $T_\\mathrm{b}$", "r_Hfus": "Enthalpy of fusion",
           "m_hill": "Hill notation", "m_dbe": "C $-$ H/2 + N/2 + 1", "m_mono": "most abundant isotope of each element",
           "m_count": "counting rule", "m_inc": "increment method", "m_job": "group contributions (Joback)",
           "m_ben": "Benson group additivity (preferred over Joback)",
           "m_S": "from $\\Delta_\\mathrm{f}H^\\circ$ and $\\Delta_\\mathrm{f}G^\\circ$ (Joback), $S^\\circ$ of the elements",
           "ocl": "calculated in the browser with OpenChemLib", "v_M": "Molar mass {f}"},
}


def _design_section(b, lang, d, tables, cite, cite_aw, vals, used):
    from . import design as DZ
    D = DT["en" if lang == "en" else "de"]
    r = DZ.analyze(str(d.get("smiles") or ""))
    names = d.get("names") or {}
    nm = (names.get("en") if lang == "en" else names.get("de")) or names.get("de") or names.get("en") or ""
    src_raw = names.get("src") or ""
    pub = d.get("pub") or {}
    keys_name = []
    if "PubChem" in src_raw and pub.get("cid"):
        src = _fill(D["src_pub"], cid=str(int(pub["cid"])))
        keys_name.append("pubchem2025")
    elif "Regeln" in src_raw or "rules" in src_raw:
        src = D["src_rule"]
        keys_name.append("favre2014")
    elif src_raw == "Sammlung":
        src = D["src_coll"]
    elif src_raw == "eigener Stoff":
        src = D["src_own"]
    else:
        src = D["src_user"] if nm else "--"
    if keys_name:
        src += r"~\cite{%s}" % ",".join(cite(k) for k in keys_name)
    try:
        ftex = _m(C.parse_species(r["hill"]).latex()) if r.get("hill") else "--"
    except C.ChemError:
        ftex = tex_escape(r.get("hill") or "--")
    name_t = tex_escape(nm) if nm else D["noname"]
    parts = [_fill(D["text"], n=name_t, f=ftex, M=_m(ntex(r["M"], 6, lang)) if r.get("M") else "--",
                   cite_aw=r"~\cite{%s}" % cite_aw(), src=src)]
    if r.get("groups"):
        parts.append(_fill(D["groups"], g=", ".join(tex_escape(g["de"] if lang == "de" else g.get("en") or g["de"])
                                                    + (f" ($\\times {g['n']}$)" if g.get("n", 1) > 1 else "")
                                                    for g in r["groups"])))
    o = d.get("ocl") or {}
    jb = r.get("joback") or {}
    J = jb.get("values") or {}
    if o.get("logP") is not None or J:
        parts.append(D["est"])
    b.add_text("molekuel", "\n\n".join(parts) + "\n", D["sec"] + (": " + nm if nm else ""))
    if d.get("molfile"):
        from . import structure as ST
        try:
            fig = ST.draw(d["molfile"])
            b.add_figure(fig, "struktur", _fill(D["fig"], n=name_t), width="0.45", cites=[cite("openchemlib")])
        except ST.MolfileError:
            pass
    if tables:
        rows = []

        def row(q, v, kind, srcs="", keys=()):
            s = srcs + (r"~\cite{%s}" % ",".join(cite(k) for k in keys) if keys else "")
            rows.append([q, v, {"x": D["exact"], "calc": D["calc"], "est": r"\textit{%s}" % D["est_k"]}[kind], s])
        row(D["r_f"], ftex, "x", D["m_hill"])
        if r.get("M"):
            row(D["r_M"], _m(ntex(r["M"], 6, lang)) + r"\,g/mol", "x", "", ("ciaaw2024",))
        if r.get("mono") is not None:
            row(D["r_mono"], _m(_fx(r["mono"], 5, lang)) + r"\,u", "x", D["m_mono"], ("ame2020",))
        if r.get("dbe") is not None:
            row(D["r_dbe"], _m(ntex(r["dbe"], 3, lang)), "x", D["m_dbe"])
        if r.get("charge"):
            row(D["r_q"], _m(str(r["charge"])), "x")
        if o.get("hbd") is not None:
            row(D["r_hb"], f"{int(o['hbd'])} / {int(o.get('hba') or 0)}", "x", D["m_count"] + ", " + D["ocl"], ("openchemlib",))
        if o.get("rot") is not None:
            row(D["r_rot"], str(int(o["rot"])), "x", D["ocl"], ("openchemlib",))
        if o.get("stereo"):
            row(D["r_st"], str(int(o["stereo"])), "x", D["ocl"], ("openchemlib",))
        if o.get("logP") is not None:
            row(D["r_logP"], _m(_fx(float(o["logP"]), 2, lang)), "est", D["m_inc"] + ", " + D["ocl"], ("sander2015", "openchemlib"))
        if o.get("logS") is not None:
            row(D["r_logS"], _m(_fx(float(o["logS"]), 2, lang)), "est", D["ocl"], ("sander2015", "openchemlib"))
        if o.get("tpsa") is not None:
            row(D["r_tpsa"], _m(_fx(float(o["tpsa"]), 1, lang)) + r"\,\AA$^2$", "est", D["ocl"], ("ertl2000", "openchemlib"))
        BV = (r.get("benson") or {}).get("values") or {}
        for k, lab in (("dfH_g", "r_dfH"), ("S_g", "r_S"), ("Cp_g", "r_Cp")):
            x = BV.get(k) or {}
            if x.get("v") is not None:
                row(D[lab], _m(_fx(x["v"], 1, lang)) + r"\," + tex_escape(x.get("u") or ""), "est", D["m_ben"],
                    ("domalski1993", "benson1969"))
        jk = ("joback1987", "joback_wiki")
        for k, lab in (("Tb", "r_Tb"), ("Tm", "r_Tm"), ("Tc", "r_Tc")):
            v = (J.get(k) or {}).get("v")
            if v is not None:
                row(D[lab], _m(_fx(v, 1, lang)) + r"\,K", "est", D["m_job"], jk)
        for k, lab in (("Pc", "r_Pc"), ("Vc", "r_Vc"), ("dfH_g", "r_dfH"), ("dfG_g", "r_dfG"), ("S_g", "r_S"),
                       ("Cp_g", "r_Cp"), ("Hvap", "r_Hvap"), ("Hfus", "r_Hfus")):
            x = J.get(k) or {}
            if x.get("v") is None:
                continue
            u = tex_escape(x.get("u") or "")
            if k == "S_g":
                row(D[lab], _m(_fx(x["v"], 1, lang)) + r"\," + u, "calc", D["m_S"], ("cox1989",))
            else:
                row(D[lab], _m(_fx(x["v"], 1, lang)) + r"\," + u, "est", D["m_job"], jk)
        b.add_table("molekuel-kennwerte", booktabs([D["h_q"], D["h_v"], D["h_k"], D["h_s"]], rows, "llll", small=True,
                                                  escape_header=False), D["cap"])
    if r.get("M"):
        vals.append((_key("molmasse-struktur", used), _fill(D["v_M"], f=ftex), _m(ntex(r["M"], 6, lang) + r"\ \mathrm{g\,mol^{-1}}"),
                     nplain(r["M"], 6, lang) + " g/mol"))


# ----------------------------------------------------------------------------- Kernchemie (ER-606)
NT = {
    "de": {"sec": "Kernchemie",
           "q": "Q-Wert des {mode}-Zerfalls von {P} zu {D} aus den Atommassen: $Q = [{f}]\\,c^2 = {Q}$\\,MeV ($\\pm {u}$\\,keV){imp}.",
           "imp": "; der Zerfall ist energetisch nicht möglich",
           "eqn": "Kerngleichung {e}: Art {mt}; Kernladungs- und Massenzahl sind erhalten ($Z = {Z}$, $A = {A}$).",
           "eqn_q": " Aus den Atommassen folgt $Q = {Q}$\\,MeV ($\\pm {u}$\\,keV).",
           "eqn_it": "Q entspricht der Anregungsenergie des Isomers und folgt nicht aus Grundzustandsmassen.",
           "rx": "Kernreaktion", "sf": "Spontanspaltung",
           "b": "Bindungsenergie von {N}: $B = {B}$\\,MeV, je Nukleon ${BA}$\\,MeV (Massendefekt ${dm}$\\,u).",
           "d": "Zerfallsgesetz {nuc}mit $T_{1/2} = {T}$: $\\lambda = {lam}\\,\\mathrm{s^{-1}}$, nach $t = {t}$ verbleiben "
                "${f}\\,\\%$; Aktivität ${A0}$\\,Bq $\\rightarrow$ ${A}$\\,Bq.",
           "spec": " Spezifische Aktivität $a = \\lambda N_\\mathrm{A}/M = {a}\\,\\mathrm{Bq/g}$.",
           "c": "Zerfallskette ab {P} (Bateman-Lösung, Hauptzweige): {m}.",
           "eq": " {txt} (Verhältnis der Halbwertszeiten ${r}$).",
           "c_fig": "Anzahl der Kerne der Kette ab {P} über der Zeit (Bateman-Lösung).", "ax_t": "t in {u}", "ax_N": "N",
           "c14": "Konventionelles $^{14}$C-Alter aus F$^{14}$C = ${F}$: ${t}$\\,a BP (Libby-Halbwertszeit 5568\\,a); mit "
                  "5730\\,a ${tc}$\\,a. Ein Kalenderalter erfordert eine Kalibrierung (IntCal20).",
           "kar": "K--Ar-Alter aus $^{40}$Ar$^*$/$^{40}$K = ${R}$: ${t}$\\,Mio.\\,a.",
           "arar": "Ar--Ar-Alter mit $J = {J}$ und $R = {R}$: ${t}$\\,Mio.\\,a.",
           "upb": "U--Pb-Alter: {items}.", "u206": "$^{206}$Pb/$^{238}$U ${t}$\\,Mio.\\,a",
           "u207": "$^{207}$Pb/$^{235}$U ${t}$\\,Mio.\\,a",
           "rbsr": "Rb--Sr-Isochrone ({n} Proben): Steigung ${m}$, ($^{87}$Sr/$^{86}$Sr)$_0 = {b}$, Alter ${t} \\pm {u}$\\,Mio.\\,a.",
           "pat": "Isotopenmuster von {f}.", "pat_cap": "Isotopenmuster von {f} (grösster Peak = 100).",
           "h_A": "Nominalmasse", "h_m": "exakte Masse in u", "h_rel": "rel. Intensität",
           "enr": "Mittlere Atommasse des Gemischs ({c}): ${M}$\\,u.",
           "v_Q": "Q-Wert {P} ({mode})", "v_BA": "Bindungsenergie je Nukleon {N}", "v_a": "Spezifische Aktivität {N}",
           "v_age": "Alter ({m})"},
    "en": {"sec": "Nuclear chemistry",
           "q": "Q-value of the {mode} decay of {P} to {D} from atomic masses: $Q = [{f}]\\,c^2 = {Q}$\\,MeV ($\\pm {u}$\\,keV){imp}.",
           "imp": "; the decay is energetically forbidden",
           "eqn": "Nuclear equation {e}: type {mt}; charge and mass numbers are conserved ($Z = {Z}$, $A = {A}$).",
           "eqn_q": " The atomic masses give $Q = {Q}$\\,MeV ($\\pm {u}$\\,keV).",
           "eqn_it": "Q equals the excitation energy of the isomer and does not follow from ground-state masses.",
           "rx": "nuclear reaction", "sf": "spontaneous fission",
           "b": "Binding energy of {N}: $B = {B}$\\,MeV, per nucleon ${BA}$\\,MeV (mass defect ${dm}$\\,u).",
           "d": "Decay law {nuc}with $T_{1/2} = {T}$: $\\lambda = {lam}\\,\\mathrm{s^{-1}}$; after $t = {t}$, ${f}\\,\\%$ remain; "
                "activity ${A0}$\\,Bq $\\rightarrow$ ${A}$\\,Bq.",
           "spec": " Specific activity $a = \\lambda N_\\mathrm{A}/M = {a}\\,\\mathrm{Bq/g}$.",
           "c": "Decay chain from {P} (Bateman solution, main branches): {m}.",
           "eq": " {txt} (ratio of half-lives ${r}$).",
           "c_fig": "Number of nuclei in the chain from {P} over time (Bateman solution).", "ax_t": "t in {u}", "ax_N": "N",
           "c14": "Conventional $^{14}$C age from F$^{14}$C = ${F}$: ${t}$\\,a BP (Libby half-life 5568\\,a); with 5730\\,a "
                  "${tc}$\\,a. A calendar age requires calibration (IntCal20).",
           "kar": "K--Ar age from $^{40}$Ar$^*$/$^{40}$K = ${R}$: ${t}$\\,Ma.",
           "arar": "Ar--Ar age with $J = {J}$ and $R = {R}$: ${t}$\\,Ma.",
           "upb": "U--Pb ages: {items}.", "u206": "$^{206}$Pb/$^{238}$U ${t}$\\,Ma", "u207": "$^{207}$Pb/$^{235}$U ${t}$\\,Ma",
           "rbsr": "Rb--Sr isochron ({n} samples): slope ${m}$, ($^{87}$Sr/$^{86}$Sr)$_0 = {b}$, age ${t} \\pm {u}$\\,Ma.",
           "pat": "Isotope pattern of {f}.", "pat_cap": "Isotope pattern of {f} (largest peak = 100).",
           "h_A": "Nominal mass", "h_m": "Exact mass in u", "h_rel": "Rel. intensity",
           "enr": "Mean atomic mass of the mixture ({c}): ${M}$\\,u.",
           "v_Q": "Q-value {P} ({mode})", "v_BA": "Binding energy per nucleon {N}", "v_a": "Specific activity {N}",
           "v_age": "Age ({m})"},
}
_EQ_EN = {"secular": "Secular equilibrium", "transient": "Transient equilibrium", "none": "No equilibrium"}
_EQ_DE = {"secular": "Säkulares Gleichgewicht", "transient": "Transientes Gleichgewicht", "none": "Kein Gleichgewicht"}
_SUP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
_NX = {"–": "--", "−": "-", "→": r"$\rightarrow$", "≈": r"$\approx$", "≤": r"$\le$", "λ": r"$\lambda$", "α": r"$\alpha$",
       "β": r"$\beta$", "⁻": r"$^-$", "⁺": r"$^+$"}


def _ntx(s) -> str:
    """Hinweistexte aus labcalc.nuclear (²⁰⁶Pb, ⁴⁰Ar, –, →) -> Latin-1-LaTeX."""
    s = re.sub(r"([⁰¹²³⁴⁵⁶⁷⁸⁹]+)", lambda m: "$^{%s}$" % m.group(1).translate(_SUP), str(s))
    return _ptx("".join(_NX.get(ch, ch) for ch in s))
_MODE_TEX = {"A": r"$\alpha$", "B-": r"$\beta^-$", "B+": r"$\beta^+$", "EC": "EC", "n": "n", "p": "p"}


def _nuc_tex(k: str) -> str:
    m = re.fullmatch(r"(\d+)([A-Za-z]+)", k)
    return r"$^{%s}\mathrm{%s}$" % (m.group(1), m.group(2)) if m else tex_escape(k)


_PT_TEX = {"α": r"$\alpha$", "alpha": r"$\alpha$", "β-": r"$\beta^-$", "β⁻": r"$\beta^-$", "beta-": r"$\beta^-$",
           "β": r"$\beta^-$", "e-": r"$e^-$", "e⁻": r"$e^-$", "e": r"$e^-$", "β+": r"$\beta^+$", "β⁺": r"$\beta^+$",
           "beta+": r"$\beta^+$", "e+": r"$e^+$", "e⁺": r"$e^+$", "ν": r"$\nu$", "nu": r"$\nu$", "v": r"$\nu$",
           "ν̄": r"$\bar{\nu}$", "antinu": r"$\bar{\nu}$", "anti-nu": r"$\bar{\nu}$", "γ": r"$\gamma$",
           "gamma": r"$\gamma$", "n": "n", "p": "p"}


def _nuc_eq_tex(eq: str) -> str:
    """Kerngleichung als LaTeX-Text: Nuklide mit Massenzahl hochgestellt, Teilchen griechisch."""
    from labcalc import nuclear as N

    def term(t):
        t = t.strip()
        m = re.fullmatch(r"(\d+)\s*(\S+)", t)
        pre = ""
        if m and (m.group(2) in _PT_TEX):
            pre, t = m.group(1) + r"\,", m.group(2)
        if t in _PT_TEX or t.lower() in _PT_TEX:
            return pre + (_PT_TEX.get(t) or _PT_TEX[t.lower()])
        k = N.key(t)
        iso = bool(re.fullmatch(r"[A-Za-z]{1,2}-?\d+m\d?", t))
        s = _nuc_tex(k)
        return pre + (s.replace("}", r"\mathrm{m}}", 1) if iso else s)
    sides = re.split(r"\s*(?:->|→|=>|=)\s*", eq.strip())
    return r" $\rightarrow$ ".join(" + ".join(term(x) for x in re.split(r"\s+\+\s+", s) if x.strip()) for s in sides)


def _nuclear_section(b, lang, res, tables, cite, vals, used):
    P = NT["en" if lang == "en" else "de"]
    paras, keys, extra, dsx = [], [], "", ""
    YR = 365.2422 * 86400
    for k, it in enumerate(res.get("nuclear") or [], 1):
        kind, r = it["kind"], it["result"]
        if kind == "q":
            f = r["formula"].replace("−", "-").replace("ₑ", "_e").replace("ₙ", "_n")
            f = re.sub(r"M\((\d+)([A-Za-z]+)\)", lambda m: r"M(^{%s}\mathrm{%s})" % (m.group(1), m.group(2)), f)
            f = f.replace("M(⁴He)", r"M(^{4}\mathrm{He})").replace("M(¹H)", r"M(^{1}\mathrm{H})").replace("2m_e", "2m_\\mathrm{e}")
            paras.append(_fill(P["q"], mode=_MODE_TEX.get(r["mode"], r["mode"]), P=_nuc_tex(r["parent"]),
                               D=_nuc_tex(r["daughter"]), f=f, Q=ntex(r["Q_MeV"], 6, lang), u=ntex(r["u_MeV"] * 1000, 2, lang),
                               imp="" if r["possible"] else P["imp"]))
            keys += ["ame2020", "codata2022", "krane"]
            vals.append((_key(f"q-{r['parent']}-{r['mode']}", used), _fill(P["v_Q"], P=_nuc_tex(r["parent"]), mode=_MODE_TEX.get(r["mode"], r["mode"])),
                         _m(ntex(r["Q_MeV"], 6, lang) + r"\,\mathrm{MeV}"), nplain(r["Q_MeV"], 6, lang) + " MeV"))
        elif kind == "equation":
            mt = {"reaction": P["rx"], "IT": "IT", "SF": P["sf"], "2B-": r"$2\beta^-$"}.get(r["mode"]) or \
                _MODE_TEX.get(r["mode"], r["mode"])
            txt = _fill(P["eqn"], e=_nuc_eq_tex(r["equation"]), mt=mt, Z=r["Z"], A=r["A"])
            if r.get("Q_MeV") is not None:
                txt += _fill(P["eqn_q"], Q=ntex(r["Q_MeV"], 6, lang), u=ntex(r["u_MeV"] * 1000, 2, lang))
            else:
                txt += " " + P["eqn_it"]
            paras.append(txt)
            keys += ["ame2020", "codata2022", "krane"]
        elif kind == "binding":
            paras.append(_fill(P["b"], N=_nuc_tex(r["key"]), B=ntex(r["B_MeV"], 6, lang), BA=ntex(r["B_per_A_MeV"], 5, lang),
                               dm=ntex(r["mass_defect_u"], 6, lang)))
            keys += ["ame2020", "codata2022"]
            vals.append((_key(f"ba-{r['key']}", used), _fill(P["v_BA"], N=_nuc_tex(r["key"])),
                         _m(ntex(r["B_per_A_MeV"], 5, lang) + r"\,\mathrm{MeV}"), nplain(r["B_per_A_MeV"], 5, lang) + " MeV"))
        elif kind == "decay":
            u = r.get("t_unit") or "a"
            fac = {"s": 1, "min": 60, "h": 3600, "d": 86400, "a": YR}[u]
            nuc = (it["req"].get("nuclide") or "").strip()
            sp = r.get("specific")
            txt = _fill(P["d"], nuc=(_nuc_tex(sp["key"]) + " ") if sp else "",
                        T=ntex(r["T_half_s"] / fac, 5, lang) + r"\,\mathrm{%s}" % u, lam=ntex(r["lambda_s"], 4, lang),
                        t=ntex(r["t_s"] / fac, 4, lang) + r"\,\mathrm{%s}" % u, f=ntex(100 * r["fraction"], 4, lang),
                        A0=ntex(r["A0_Bq"], 4, lang), A=ntex(r["A_Bq"], 4, lang))
            if sp:
                txt += _fill(P["spec"], a=ntex(sp["a_Bq_g"], 4, lang))
                vals.append((_key(f"a-{sp['key']}", used), _fill(P["v_a"], N=_nuc_tex(sp["key"])),
                             _m(ntex(sp["a_Bq_g"], 4, lang) + r"\,\mathrm{Bq/g}"), nplain(sp["a_Bq_g"], 4, lang) + " Bq/g"))
            paras.append(txt)
            keys += ["nubase2020", "krane"] + (["ame2020"] if nuc else [])
        elif kind == "chain":
            mem = r["members"]
            def _hl(s):          # NUBASE-Text "28.91 y (0.03)" -> "28,91 a"
                v, _, u = str(s).partition(" ")
                u = {"y": "a"}.get(u.split(" ")[0], u.split(" ")[0])
                return (v.replace(".", ",") if lang == "de" else v) + r"\," + tex_escape(u)
            ms = r" $\rightarrow$ ".join(_nuc_tex(m["key"]) + (" (%s)" % _hl(m["half_life"]) if m.get("half_life") and
                                                               not m.get("stable") else "") for m in mem)
            txt = _fill(P["c"], P=_nuc_tex(mem[0]["key"]), m=ms)
            e = r.get("equilibrium")
            if e:
                eqt = (_EQ_DE if lang == "de" else _EQ_EN)[e["kind"]]
                txt += _fill(P["eq"], txt=eqt, r=ntex(e["ratio"], 3, lang)) if e.get("ratio") else " " + eqt + "."
            paras.append(txt)
            keys += ["nubase2020", "bateman1910", "krane"]
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            u = r.get("t_unit") or "d"
            fac = {"s": 1, "min": 60, "h": 3600, "d": 86400, "a": YR}[u]
            fig, ax = plt.subplots(figsize=(5.6, 3.2))
            for j, m in enumerate(mem):
                ax.plot([t / fac for t in r["times_s"]], [row[j] for row in r["N"]], lw=1.6,
                        label="$^{%s}$%s" % (re.match(r"\d+", m["key"]).group(), re.sub(r"^\d+", "", m["key"])))
            ax.set_xlabel(_fill(P["ax_t"], u=u))
            ax.set_ylabel(P["ax_N"])
            ax.legend(fontsize=8)
            ax.grid(alpha=0.3)
            fig.tight_layout()
            b.add_figure(fig, f"kette-{k}", _fill(P["c_fig"], P=_nuc_tex(mem[0]["key"])),
                         cites=[",".join(cite(x) for x in ("nubase2020", "bateman1910"))])
        elif kind == "dating":
            m = r["method"]
            if m == "c14":
                paras.append(_fill(P["c14"], F=ntex(r["F14C"], 4, lang), t=ntex(round(r["age_BP"]), 6, lang),
                                   tc=ntex(round(r["age_cambridge_a"]), 6, lang)))
                age = r["age_BP"]
            elif m in ("kar", "arar"):
                paras.append(_fill(P[m], R=ntex(r["R"], 4, lang), J=ntex(r.get("J") or 0, 4, lang), t=ntex(r["age_a"] / 1e6, 4, lang)))
                age = r["age_a"]
            elif m == "upb":
                items = []
                if r.get("age_206_a") is not None:
                    items.append(_fill(P["u206"], t=ntex(r["age_206_a"] / 1e6, 4, lang)))
                if r.get("age_207_a") is not None:
                    items.append(_fill(P["u207"], t=ntex(r["age_207_a"] / 1e6, 4, lang)))
                paras.append(_fill(P["upb"], items="; ".join(items)))
                age = r.get("age_206_a") or r.get("age_207_a")
            else:
                paras.append(_fill(P["rbsr"], n=len(r["residuals"]), m=ntex(r["slope"], 5, lang), b=ntex(r["intercept"], 6, lang),
                                   t=ntex(r["age_a"] / 1e6, 4, lang), u=ntex(r["u_age_a"] / 1e6, 2, lang)))
                age = r["age_a"]
                dsx = _ds_note(r, lang)                     # DP-12: Isochronen-Punkte aus einem Datensatz
            if lang == "de":
                extra = " " + " ".join(r"\textit{%s}" % _ntx(n) for n in r.get("notes") or [])
            keys += [x for x in r.get("refs") or []]
            vals.append((_key(f"alter-{m}", used), _fill(P["v_age"], m=m.upper()), _m(ntex(age, 5, lang) + r"\,\mathrm{a}"),
                         nplain(age, 5, lang) + " a"))
        elif kind == "pattern":
            ftx = _sp_tex(str(r["formula"]).translate(str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")))
            paras.append(_fill(P["pat"], f=ftx))
            keys += ["nubase2020", "ame2020"]
            if tables:
                rows = [[str(p["A"]), _m(ntex(p["mass_u"], 7, lang)), _m(ntex(p["rel"], 4, lang))] for p in r["peaks"]]
                b.add_table(f"isotopenmuster-{k}", booktabs([P["h_A"], P["h_m"], P["h_rel"]], rows, "rrr", escape_header=False),
                            _fill(P["pat_cap"], f=ftx), cites=[",".join(cite(x) for x in ("nubase2020", "ame2020"))])
        elif kind == "enriched":
            c = ", ".join(f"{_nuc_tex(kk)} {nplain(100 * v, 4, lang)}\\,\\%" for kk, v in r["fractions"].items())
            paras.append(_fill(P["enr"], c=c, M=ntex(r["M"], 7, lang)))
            keys += ["ame2020"]
        ks = [x for x in dict.fromkeys(keys) if x in REFS]
        if paras and ks:
            paras[-1] = _cite_end(paras[-1], ",".join(cite(x) for x in ks))
        if paras and extra.strip():
            paras[-1] += extra
        if paras and dsx:
            paras[-1] += dsx
        keys, extra, dsx = [], "", ""
    if paras:
        b.add_text("kernchemie", "\n\n".join(paras) + "\n", P["sec"])


# ----------------------------------------------------------------------------- Kinetik (ER-703/704)
KT = {
    "de": {"sec": "Kinetik", "conv": "Die Geschwindigkeitskonstante ist über $-\\mathrm{d}[\\mathrm{A}]/\\mathrm{d}t = k\\,[\\mathrm{A}]^n$ definiert.",
           "arr": "Arrhenius-Auswertung von {n} Messpunkten ({T1}--{T2}\\,K): lineare Regression von $\\ln k$ gegen $1/T$ "
                  "ergibt $E_\\mathrm{a} = ({Ea} \\pm {uEa})$\\,kJ/mol und $\\ln A = {lnA} \\pm {ulnA}$ ($A = {A}${unit}), "
                  "$R^2 = {r2}$; Unsicherheiten als Standardfehler (1\\,$\\sigma$).",
           "ey": "Eyring-Auswertung von {n} Messpunkten ({T1}--{T2}\\,K, $\\kappa = 1$): $\\Delta H^\\ddagger = ({H} \\pm {uH})$\\,kJ/mol, "
                 "$\\Delta S^\\ddagger = ({S} \\pm {uS})$\\,J/(mol\\,K), $R^2 = {r2}$.",
           "ord": "Reaktionsordnung aus {n} Konzentrations-Zeit-Werten: am besten passt Ordnung {o} mit $k = {k} \\pm {uk}${unit} "
                  "und $c_0 = {c0}$; Auswahl nach der kleinsten Restabweichung in $c$ (Ordnung 0/1/2: {rms}).",
           "sim": "Simulation {lab} mit {par}; analytische Lösung, Kontrolle mit Runge-Kutta 4. Ordnung "
                  "(grösste Abweichung {dev}).",
           "th": " Halbwertszeit $t_{1/2} = {t}$.", "tb": " Maximum von B bei $t = {t}$.",
           "src": " Quelle von $E_\\mathrm{a}$: {s}.",
           "f_arr": "Arrhenius-Auftragung mit Regressionsgerade; unten Residuen von $\\ln k$.",
           "f_ord": "Konzentration gegen Zeit mit angepasstem Gesetz der Ordnung {o}; unten Residuen.",
           "f_sim": "Simulierter Konzentrationsverlauf: {lab}.",
           "t_cap": "Kinetische Kenngrössen mit Standardfehler (1\\,$\\sigma$).",
           "h_q": "Grösse", "h_v": "Wert", "h_u": "Standardfehler",
           "v_Ea": "Aktivierungsenergie $E_\\mathrm{a}$", "v_A": "Präexponentieller Faktor $A$",
           "v_H": "Aktivierungsenthalpie $\\Delta H^\\ddagger$", "v_S": "Aktivierungsentropie $\\Delta S^\\ddagger$",
           "v_k": "Geschwindigkeitskonstante $k$", "v_n": "Reaktionsordnung", "v_t": "Halbwertszeit",
           "ax_c": "$c$", "ax_t": "$t$", "ax_res": "Residuum"},
    "en": {"sec": "Kinetics", "conv": "The rate constant is defined by $-\\mathrm{d}[\\mathrm{A}]/\\mathrm{d}t = k\\,[\\mathrm{A}]^n$.",
           "arr": "Arrhenius analysis of {n} data points ({T1}--{T2}\\,K): linear regression of $\\ln k$ on $1/T$ gives "
                  "$E_\\mathrm{a} = ({Ea} \\pm {uEa})$\\,kJ/mol and $\\ln A = {lnA} \\pm {ulnA}$ ($A = {A}${unit}), "
                  "$R^2 = {r2}$; uncertainties are standard errors (1\\,$\\sigma$).",
           "ey": "Eyring analysis of {n} data points ({T1}--{T2}\\,K, $\\kappa = 1$): $\\Delta H^\\ddagger = ({H} \\pm {uH})$\\,kJ/mol, "
                 "$\\Delta S^\\ddagger = ({S} \\pm {uS})$\\,J/(mol\\,K), $R^2 = {r2}$.",
           "ord": "Reaction order from {n} concentration-time values: order {o} fits best with $k = {k} \\pm {uk}${unit} "
                  "and $c_0 = {c0}$; chosen by the smallest residual in $c$ (order 0/1/2: {rms}).",
           "sim": "Simulation {lab} with {par}; analytic solution, checked with fourth-order Runge-Kutta "
                  "(largest deviation {dev}).",
           "th": " Half-life $t_{1/2} = {t}$.", "tb": " B peaks at $t = {t}$.", "src": " Source of $E_\\mathrm{a}$: {s}.",
           "f_arr": "Arrhenius plot with regression line; below, residuals of $\\ln k$.",
           "f_ord": "Concentration versus time with the fitted order-{o} law; below, residuals.",
           "f_sim": "Simulated concentration course: {lab}.",
           "t_cap": "Kinetic parameters with standard errors (1\\,$\\sigma$).",
           "h_q": "Quantity", "h_v": "Value", "h_u": "Standard error",
           "v_Ea": "Activation energy $E_\\mathrm{a}$", "v_A": "Pre-exponential factor $A$",
           "v_H": "Enthalpy of activation $\\Delta H^\\ddagger$", "v_S": "Entropy of activation $\\Delta S^\\ddagger$",
           "v_k": "Rate constant $k$", "v_n": "Reaction order", "v_t": "Half-life",
           "ax_c": "$c$", "ax_t": "$t$", "ax_res": "Residual"},
}
_SIM_EN = {"0": "A → P, zeroth order", "1": "A → P, first order", "2": "A → P, second order",
           "2AB": "A + B → P, second order", "consec": "A → B → C, consecutive first order",
           "rev": "A ⇌ B, reversible first order"}


_SUPX = str.maketrans("⁻⁺⁰¹²³⁴⁵⁶⁷⁸⁹", "-+0123456789")


def _unit_tex(u: str) -> str:
    """Einheit wie 's⁻¹' oder 'L mol⁻¹ s⁻¹' -> Latin-1-LaTeX."""
    s = re.sub(r"([⁻⁺]?[⁰¹²³⁴⁵⁶⁷⁸⁹]+)", lambda m: "\x00%s\x01" % m.group(1).translate(_SUPX), str(u))
    s = tex_escape(s).replace("\x00", "$^{").replace("\x01", "}$")
    return s.replace("·", r"$\cdot$")


_DS_T = {"de": (" Messwerte aus dem Datensatz ,,{t}`` (Freigabe {id}, Version {v}, {m}): {cols}; umgerechnet in die "
                "Einheiten der Auswertung{drop}.", "live", "gepinnt", "; {n} Zeile(n) ausgelassen (ausgeschlossen oder leer)"),
         "en": (" Data from the dataset ``{t}'' (share {id}, version {v}, {m}): {cols}; converted to the units of the "
                "analysis{drop}.", "live", "pinned", "; {n} row(s) left out (excluded or empty)")}


def _ds_note(r: dict, lang: str) -> str:
    """DP-12: Satz zur Herkunft einer Messreihe aus einem Datensatz (Freigabe-ID, Version, live/gepinnt, Spalten)."""
    o = r.get("dataset")
    if not isinstance(o, dict) or not o.get("id"):
        return ""
    txt, live, pin, drop = _DS_T["en" if lang == "en" else "de"]
    names, units = o.get("names") or {}, o.get("units") or {}
    cols = ", ".join(f"{_ntx(names.get(k) or k)} ({_unit_tex(units[k]) if units.get(k) else '1'})" for k in (o.get("cols") or {}))
    return _fill(txt, t=_ntx(o.get("title") or ""), id=tex_escape(o["id"]), v=int(o.get("version") or 0),
                 m=pin if o.get("mode") == "pin" else live, cols=cols or "--",
                 drop=_fill(drop, n=int(o["dropped"])) if o.get("dropped") else "")


def _kin_fig(lang):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, (ax, ar) = plt.subplots(2, 1, figsize=(6.0, 3.8), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    if lang == "de":
        from matplotlib.ticker import FuncFormatter
        fm = FuncFormatter(lambda v, _: f"{v:g}".replace(".", ",").replace("-", "−"))
        for a in (ax, ar):
            a.yaxis.set_major_formatter(fm)
            a.xaxis.set_major_formatter(fm)
    return plt, fig, ax, ar


FL_T = {
    "de": {"sec": "Adiabate Flammentemperatur", "ox": {"air": "Luft (21\\,\\% O$_2$, 79\\,\\% N$_2$)", "O2": "reinem O$_2$"},
           "txt": "Für {f} mit {ox} bei $\\varphi = {phi}$ und $T_0 = {T0}$\\,K folgt aus der Energiebilanz bei konstantem Druck "
                  "$\\sum_\\mathrm{E} n_i\\,H_i(T_0) = \\sum_\\mathrm{P} n_i\\,H_i(T_\\mathrm{ad})$ mit $C_p(T)$ aus NASA-7-Polynomen "
                  "die adiabate Flammentemperatur $T_\\mathrm{ad} = {T}$\\,K. Angenommen ist vollständige Verbrennung zu "
                  "CO$_2$ und H$_2$O(g) ohne Dissoziation und ohne Wärmeverluste; oberhalb von etwa 2000\\,K liegt der Wert "
                  "deshalb zu hoch (bei Methan/Luft rund 100\\,K über dem Gleichgewichtswert).",
           "cap": "Produkte der vollständigen Verbrennung je mol Brennstoff.", "h_p": "Produkt", "h_n": "$n$ in mol",
           "h_x": "Stoffmengenanteil", "v": "Adiabate Flammentemperatur"},
    "en": {"sec": "Adiabatic flame temperature", "ox": {"air": "air (21\\,\\% O$_2$, 79\\,\\% N$_2$)", "O2": "pure O$_2$"},
           "txt": "For {f} with {ox} at $\\varphi = {phi}$ and $T_0 = {T0}$\\,K, the constant-pressure energy balance "
                  "$\\sum_\\mathrm{R} n_i\\,H_i(T_0) = \\sum_\\mathrm{P} n_i\\,H_i(T_\\mathrm{ad})$ with $C_p(T)$ from NASA-7 polynomials "
                  "gives the adiabatic flame temperature $T_\\mathrm{ad} = {T}$\\,K. Complete combustion to CO$_2$ and H$_2$O(g) is "
                  "assumed, without dissociation or heat loss; above about 2000\\,K the value is therefore too high (about "
                  "100\\,K above the equilibrium value for methane/air).",
           "cap": "Products of complete combustion per mol of fuel.", "h_p": "Product", "h_n": "$n$ in mol",
           "h_x": "Mole fraction", "v": "Adiabatic flame temperature"},
}


def _flame_text(b, lang, r, tables, cite, vals, used, j):
    P = FL_T["en" if lang == "en" else "de"]
    ks = [x for x in r.get("refs") or [] if x in REFS]
    cs = ",".join(cite(x) for x in ks)
    f = _m(C.parse_species(r["fuel"]).latex())
    txt = _fill(P["txt"], f=f, ox=P["ox"][r["oxidant"]], phi=_fx(r["phi"], 2, lang), T0=_fx(r["T0"], 2, lang),
                T=_fx(r["T_ad"], 0, lang))
    b.add_text(f"flammentemperatur-{j}", _cite_end(txt, cs) + "\n", P["sec"])
    if tables:
        rows = [[_m(C.parse_species(p["species"]).latex()), _m(ntex(p["n"], 4, lang)), _m(ntex(p["x"], 4, lang))]
                for p in r["products"]]
        b.add_table(f"flammentemperatur-{j}", booktabs([P["h_p"], P["h_n"], P["h_x"]], rows, "lrr", escape_header=False),
                    P["cap"], cites=[cs] if cs else None)
    vals.append((_key(f"Tad-{j}", used), P["v"], _m(_fx(r["T_ad"], 0, lang) + r"\,\mathrm{K}"), _fxp(r["T_ad"], 0, lang) + " K"))


def _ion_tex(s: str) -> str:
    """'Ca2+', 'CO3^2-', 'Fe³⁺' -> $\\mathrm{CO_{3}}^{2-}$."""
    from labcalc import speciation as SP
    t = s.strip().translate(str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻", "0123456789+-"))
    z = SP._charge(t)
    base = re.sub(r"\^?\d*[+-]\d*$", "", t) if z else t
    base = re.sub(r"(\d+)", r"_{\1}", base)
    sup = "" if not z else "^{%s%s}" % (abs(z) if abs(z) > 1 else "", "+" if z > 0 else "-")
    return r"$\mathrm{%s}%s$" % (base, sup)


def _speciation_section(b, lang, r, cite, vals, used):
    en = lang == "en"
    ks = [x for x in r.get("refs") or [] if x in REFS]
    cs = ",".join(cite(x) for x in ks)
    mt = _ion_tex(r["metal"])
    lt = _ion_tex(r["ligand"]) if re.search(r"[-+⁺⁻]$", r["ligand"].strip()) or re.fullmatch(r"[A-Z][A-Za-z0-9]*", r["ligand"].strip()) \
        else _ntx(r["ligand"])
    bet = ", ".join(r"$\lg\beta_{%s} = %s$" % (n, _fx(v, 2, lang)) for n, v in r["betas"].items())
    if en:
        txt = (f"Species distribution of {mt} with {lt} ($c_\\mathrm{{M}} = {ntex(r['c_M'], 3, lang)}$\\,mol/L"
               + (f", $c_\\mathrm{{L}} = {ntex(r['c_L'], 3, lang)}$\\,mol/L" if r.get("c_L") else "")
               + f") from the stability constants {bet} and the ligand protonation constants; the pH is set (buffered). "
               f"Largest relative mass-balance residual {_m(ntex(r['max_residual'], 2, lang))}; the charge balance is closed by "
               "buffer and counter-ions. Mononuclear complexes only; constants at their ionic strength.")
    else:
        txt = (f"Speziesverteilung von {mt} mit {lt} ($c_\\mathrm{{M}} = {ntex(r['c_M'], 3, lang)}$\\,mol/L"
               + (f", $c_\\mathrm{{L}} = {ntex(r['c_L'], 3, lang)}$\\,mol/L" if r.get("c_L") else "")
               + f") aus den Stabilitätskonstanten {bet} und den Protonierungskonstanten des Liganden; der pH ist "
               f"vorgegeben (gepuffert). Grösster relativer Rest der Massenbilanzen {_m(ntex(r['max_residual'], 2, lang))}; "
               "die Ladungsbilanz gleichen Puffer und Gegenionen aus. Nur einkernige Komplexe; Konstanten bei ihrer "
               "Ionenstärke.")
    b.add_text("speziation", _cite_end(txt, cs) + "\n", "Speciation" if en else "Speziation")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6.0, 3.2))
    xs = [p["pH"] for p in r["points"]]
    cols = ["#6d28d9", "#0e7490", "#b45309", "#15803d", "#be123c", "#1d4ed8", "#a16207", "#7c3aed"]
    for i, r0 in enumerate(r["points"][0]["rows"]):
        n = r0["n"]
        lab = "M" if n == 0 else ("MHL" if n == "MHL" else ("ML" if n == 1 else f"ML$_{n}$"))
        ax.plot(xs, [p["rows"][i]["frac"] for p in r["points"]], color=cols[i % len(cols)], lw=1.6, label=lab)
    ax.set_xlabel("pH")
    ax.set_ylabel("Anteil am Metall" if not en else "Fraction of metal")
    ax.set_ylim(-0.02, 1.02)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, frameon=False, ncol=3)
    fig.tight_layout()
    cap = (f"Species distribution of {mt} with {lt} versus pH." if en else f"Speziesverteilung von {mt} mit {lt} über dem pH.")
    b.add_figure(fig, "speziation", cap, cites=[cs] if cs else None)
    plt.close(fig)


def _kinetics_section(b, lang, res, tables, cite, vals, used):
    P = KT["en" if lang == "en" else "de"]
    paras, cites_all = [P["conv"]], []
    for j, item in enumerate(res["kinetics"], 1):
        kind, r = item["kind"], item["result"]
        if kind == "flame":
            _flame_text(b, lang, r, tables, cite, vals, used, j)
            continue
        unit = (r"\," + _unit_tex(r["unit_k"])) if r.get("unit_k") else ""
        ks = [x for x in r.get("refs") or [] if x in REFS]
        cites_all += ks
        cs = ",".join(cite(x) for x in ks)
        if kind in ("arrhenius", "eyring"):
            T1, T2 = r["T_range"]
            if kind == "arrhenius":
                txt = _fill(P["arr"], n=r["n"], T1=_fx(T1, 1, lang), T2=_fx(T2, 1, lang), Ea=ntex(r["Ea_kJ"], 4, lang),
                            uEa=ntex(r["u_Ea_kJ"], 2, lang), lnA=ntex(r["lnA"], 4, lang), ulnA=ntex(r["u_lnA"], 2, lang),
                            A=ntex(r["A"], 3, lang), unit=unit, r2=_fx(r["r2"], 4, lang))
                vals.append((_key(f"Ea-{j}", used), P["v_Ea"], _m(ntex(r["Ea_kJ"], 4, lang) + r"\,\mathrm{kJ\,mol^{-1}}"),
                             nplain(r["Ea_kJ"], 4, lang) + " kJ/mol"))
                vals.append((_key(f"A-{j}", used), P["v_A"], _m(ntex(r["A"], 3, lang)) + unit, nplain(r["A"], 3, lang)))
                trows = [[P["v_Ea"] + " (kJ/mol)", _m(ntex(r["Ea_kJ"], 4, lang)), _m(ntex(r["u_Ea_kJ"], 2, lang))],
                         [r"$\ln A$", _m(ntex(r["lnA"], 4, lang)), _m(ntex(r["u_lnA"], 2, lang))]]
            else:
                txt = _fill(P["ey"], n=r["n"], T1=_fx(T1, 1, lang), T2=_fx(T2, 1, lang), H=ntex(r["dH_kJ"], 4, lang),
                            uH=ntex(r["u_dH_kJ"], 2, lang), S=ntex(r["dS_J"], 3, lang), uS=ntex(r["u_dS_J"], 2, lang),
                            r2=_fx(r["r2"], 4, lang))
                vals.append((_key(f"dHact-{j}", used), P["v_H"], _m(ntex(r["dH_kJ"], 4, lang) + r"\,\mathrm{kJ\,mol^{-1}}"),
                             nplain(r["dH_kJ"], 4, lang) + " kJ/mol"))
                vals.append((_key(f"dSact-{j}", used), P["v_S"], _m(ntex(r["dS_J"], 3, lang) + r"\,\mathrm{J\,mol^{-1}\,K^{-1}}"),
                             nplain(r["dS_J"], 3, lang) + " J/(mol·K)"))
                trows = [[P["v_H"] + " (kJ/mol)", _m(ntex(r["dH_kJ"], 4, lang)), _m(ntex(r["u_dH_kJ"], 2, lang))],
                         [P["v_S"] + " (J/(mol\\,K))", _m(ntex(r["dS_J"], 3, lang)), _m(ntex(r["u_dS_J"], 2, lang))]]
            paras.append(_cite_end(txt, cs) + _ds_note(r, lang))
            if tables:
                b.add_table(f"kinetik-{j}", booktabs([P["h_q"], P["h_v"], P["h_u"]], trows, "lrr", escape_header=False),
                            P["t_cap"], cites=[cs] if cs else None)
            plt, fig, ax, ar = _kin_fig(lang)
            xs = [p["x"] * 1000 for p in r["points"]]
            ys = [p["y"] for p in r["points"]]
            ax.plot(xs, ys, "o", color="#6d28d9", ms=4)
            fy = [y - p["res"] for y, p in zip(ys, r["points"])]
            ax.plot(xs, fy, "-", color="#0e7490", lw=1.4)
            ar.axhline(0, color="0.3", lw=0.8)
            ar.plot(xs, [p["res"] for p in r["points"]], "o", color="#6d28d9", ms=3)
            ax.set_ylabel(r"$\ln k$" if kind == "arrhenius" else r"$\ln(k/T)$")
            ar.set_xlabel(r"$1000/T$ in K$^{-1}$")
            ar.set_ylabel(P["ax_res"])
            for a in (ax, ar):
                a.grid(alpha=0.3)
            fig.tight_layout()
            b.add_figure(fig, f"kinetik-{j}", P["f_arr"] if kind == "arrhenius" else P["f_arr"].replace("\\ln k", "\\ln(k/T)"),
                         cites=[cs] if cs else None)
            plt.close(fig)
        elif kind == "order":
            best = next(f for f in r["fits"] if f.get("valid") and f["order"] == r["best"])
            rms = "/".join(_m(ntex(f["rms_c"], 2, lang)) if f.get("valid") else "--" for f in r["fits"])
            paras.append(_cite_end(_fill(P["ord"], n=len(r["t"]), o=r["best"], k=ntex(best["k"], 4, lang),
                                         uk=ntex(best["u_k"], 2, lang), unit=unit, c0=ntex(best["c0"], 4, lang), rms=rms)
                                   + (_fill(P["th"], t=ntex(best["t_half"], 4, lang)) if best.get("t_half") else ""), cs)
                         + _ds_note(r, lang))
            vals.append((_key(f"ordnung-{j}" if lang == "de" else f"order-{j}", used), P["v_n"], _m(str(r["best"])), str(r["best"])))
            vals.append((_key(f"k-{j}", used), P["v_k"], _m(ntex(best["k"], 4, lang)) + unit, nplain(best["k"], 4, lang)))
            plt, fig, ax, ar = _kin_fig(lang)
            from labcalc import kinetics as KN
            ax.plot(r["t"], r["c"], "o", color="#6d28d9", ms=4)
            t1 = max(r["t"])
            tt = [t1 * i / 100 for i in range(101)]
            ax.plot(tt, [KN._c_pred(r["best"], best["k"], best["c0"], t) for t in tt], "-", color="#0e7490", lw=1.4)
            ar.axhline(0, color="0.3", lw=0.8)
            ar.plot(r["t"], best["residuals_c"], "o", color="#6d28d9", ms=3)
            ax.set_ylabel(P["ax_c"])
            ar.set_xlabel(P["ax_t"])
            ar.set_ylabel(P["ax_res"])
            for a in (ax, ar):
                a.grid(alpha=0.3)
            fig.tight_layout()
            b.add_figure(fig, f"kinetik-{j}", _fill(P["f_ord"], o=r["best"]), cites=[cs] if cs else None)
            plt.close(fig)
        elif kind == "sim":
            lab = _ntx((_SIM_EN[r["model"]] if lang == "en" else r["label"]).replace("⇌", "<=>"))
            lab = lab.replace("<=>", r"$\rightleftharpoons$")
            par =", ".join(f"{k_} = {_m(ntex(v, 4, lang))}" for k_, v in r["params"].items())
            txt = _fill(P["sim"], lab=lab, par=par, dev=_m(ntex(r["check"]["max_dev"], 2, lang)))
            if r.get("t_half"):
                txt += _fill(P["th"], t=ntex(r["t_half"], 4, lang))
            if r.get("t_Bmax"):
                txt += _fill(P["tb"], t=ntex(r["t_Bmax"], 4, lang))
            if r.get("source"):
                txt += _fill(P["src"], s=_ntx(r["source"]))
            paras.append(_cite_end(txt, cs))
            if r.get("t_half"):
                vals.append((_key(f"thalb-{j}" if lang == "de" else f"thalf-{j}", used), P["v_t"],
                             _m(ntex(r["t_half"], 4, lang)), nplain(r["t_half"], 4, lang)))
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=(6.0, 3.0))
            for s, col in zip([k_ for k_ in r["rows"][0] if k_ != "t"], ["#6d28d9", "#0e7490", "#b45309"]):
                ax.plot([x["t"] for x in r["rows"]], [x[s] for x in r["rows"]], color=col, lw=1.6, label=s)
            ax.legend(fontsize=8, frameon=False)
            ax.set_xlabel(P["ax_t"])
            ax.set_ylabel(P["ax_c"])
            ax.grid(alpha=0.3)
            fig.tight_layout()
            b.add_figure(fig, f"kinetik-{j}", _fill(P["f_sim"], lab=lab), cites=[cs] if cs else None)
            plt.close(fig)
    if len(paras) > 1:
        b.add_text("kinetik", "\n\n".join(paras) + "\n", P["sec"])


# ----------------------------------------------------------------------------- Aufbau
def _shared_section(b, lang, sh, tables, vals, used):
    """A3/A5: Vergleich geteilter TGA-Stufen mit der Theorie. Der Umschlag liegt im Request (gepinnte Version), damit
    „Aktualisieren“ dieselbe Version benutzt; genannt werden Freigabe-ID, Version und erzeugende Umgebung."""
    from . import shared as SH
    de = lang != "en"
    env = sh["envelope"]
    rows_in = sh.get("rows") or []
    res = SH.compare(env, rows_in)
    p = env.get("producer") or {}
    who = tex_escape(f"{env.get('id')} v{env.get('version')}, TGA-Lauf {p.get('item_name') or p.get('item') or '?'}"
                     f" ({p.get('env_name') or p.get('env') or '?'})" if de else
                     f"{env.get('id')} v{env.get('version')}, TGA run {p.get('item_name') or p.get('item') or '?'}"
                     f" ({p.get('env_name') or p.get('env') or '?'})")
    rows = []
    for r in res:
        if r.get("error"):
            rows.append([tex_escape(r["label"]), f"{r['measured']:.2f}".replace(".", "," if de else "."), tex_escape(r["error"]), "", ""])
            continue
        f = (lambda x: f"{x:.2f}".replace(".", "," if de else "."))
        rows.append([tex_escape(r["label"]), f(r["measured"]), "$%s$ (%s $%s$)" % (r["equation_tex"], "Basis" if de else "basis", r["basis_tex"]),
                     f(r["theory"]), ("$+$" if r["delta"] >= 0 else "$-$") + f(abs(r["delta"]))])
        k = "tga-" + r["key"]
        if k not in used:
            used.add(k)
            vals.append((k + "-theo", tex_escape(("Theoretischer Verlust " if de else "Theoretical loss ") + r["label"]),
                         "$" + f(r["theory"]) + r"\,\%$", f(r["theory"]) + " %"))
    if not rows or not tables:
        return
    head = ["Stufe", r"gemessen / \%", "Zersetzung", r"theoretisch / \%", r"$\Delta$ / \%"] if de else \
           ["Step", r"measured / \%", "Decomposition", r"theoretical / \%", r"$\Delta$ / \%"]
    cap = ((r"Gemessener und theoretischer Massenverlust; geteilte Eingabe " if de else
            r"Measured and theoretical mass loss; shared input ") + who + ". " +
           (r"Theoretisch: $\sum \nu_g M_g / (\nu_E M_{Basis})$, molare Massen aus den Standard-Atomgewichten (CIAAW)."
            if de else r"Theoretical: $\sum \nu_g M_g / (\nu_E M_{basis})$, molar masses from standard atomic weights (CIAAW)."))
    b.add_table("tga-vergleich", booktabs(head, rows, "lrp{6cm}rr", small=True, escape_header=False), cap)


def _ir_section(b, lang, ir, cite):
    """A6: Struktur gegen geteilte FTIR-Banden; nennt Freigabe und Version (gepinnt im Request)."""
    from . import shared as SH
    de = lang != "en"
    c = SH.compare_ir(ir["envelope"], ir["smiles"])
    st_en = {"bestätigt": "confirmed", "teilweise": "partial", "fehlt": "missing", "ohne IR-Bande": "no reliable band"}
    rows = []
    for x in c["rows"]:
        exp = ", ".join(f"{bd['range'][0]}--{bd['range'][1]}" for bd in x["bands"]) or "--"
        got = ", ".join(f"{bd['at']:.0f}" if bd["at"] is not None else "--" for bd in x["bands"]) or "--"
        rows.append([tex_escape(x["name"] + (f" (x{x['n']})" if x["n"] > 1 else "")), exp, got,
                     tex_escape(x["ftir_verdict"] or "--"), tex_escape(x["status"] if de else st_en.get(x["status"], x["status"]))])
    if not rows:
        return
    who = tex_escape(f"{c['share']} v{c['version']}, " + ("Spektrum " if de else "spectrum ") + f"{c['spectrum'] or '?'} ({c['env_name'] or '?'})")
    extra = ""
    if c["extra"]:
        extra = tex_escape((" Im Spektrum wahrscheinlich, nicht in der Struktur: " if de else " Likely in the spectrum but not in the structure: ")
                           + ", ".join(e["name"] for e in c["extra"]) + ".")
    head = (["Gruppe", r"erwartet / cm$^{-1}$", r"gefunden / cm$^{-1}$", "FTIR-Auswertung", "Ergebnis"] if de else
            ["Group", r"expected / cm$^{-1}$", r"found / cm$^{-1}$", "FTIR evaluation", "Result"])
    cap = (("Funktionelle Gruppen der Struktur gegen die geteilten FTIR-Banden " if de else
            "Functional groups of the structure against shared FTIR bands ") + who + ". " +
           ("Erwartete Bereiche nach Socrates; ein Hinweis, keine Identifizierung." if de else
            "Expected ranges after Socrates; an indication, not an identification.") + extra +
           r" \cite{%s}" % cite("socrates2001"))
    b.add_table("ftir-vergleich", booktabs(head, rows, "lllll", small=True, escape_header=False), cap)


def _chain_section(b, lang, ch, tables, cite, vals, used):
    """UI-12: Reaktionskette – Schritte, Gesamtgleichung, Hess, Mengen und grüne Kennzahlen (wie auf der Seite)."""
    from . import chain as CH
    de = lang != "en"
    r = CH.analyse(ch.get("steps") or [], ch.get("feeds") or {}, ch.get("target") or None)
    ok = [s for s in r["steps"] if s.get("ok")]
    if len(ok) < 2:
        return False
    f = (lambda v, d=4: ntex(v, d, lang))
    parts = [("Die Umgebung enthält eine Reaktionskette aus %d Schritten:" if de else "The environment contains a reaction chain of %d steps:") % len(ok)]
    for s in ok:
        src = [l for l in s.get("links") or [] if l.get("from_n")]
        link = ("; " + ", ".join(r"$%s$ aus Schritt %d" % (C.parse_species(l["species"]).latex(), l["from_n"]) if de else
                                 r"$%s$ from step %d" % (C.parse_species(l["species"]).latex(), l["from_n"]) for l in src)) if src else ""
        parts.append(r"\[ \mathrm{(%d)}\quad %s \]" % (s["n"], s["latex"]))
        parts.append(tex_escape(("Schritt %d: Ausbeute " if de else "Step %d: yield ") % s["n"]) + "$" + f(s["yield"], 3) + r"\,\%$" + link + ".")
    o = r.get("overall")
    if o:
        mult = ", ".join(o["multipliers"].get(s["id"], "0") for s in ok)
        parts.append(("Gesamtgleichung (Schrittfaktoren %s; Zwischenstoffe heben sich auf):" if de else
                      "Overall equation (step factors %s; intermediates cancel):") % tex_escape(mult))
        parts.append(r"\[ %s \]" % o["latex"])
        vals.append(("kette-gesamt", tex_escape("Gesamtgleichung der Kette" if de else "Overall equation of the chain"), _m(o["latex"]), o["text"]))
    h = r.get("hess")
    keys = []
    if h:
        for s in ok:
            keys += [k for k in ((s.get("thermo") or {}).get("refs") or []) if k in REFS]
        cites = ",".join(dict.fromkeys(cite(k) for k in keys))
        if h.get("dH") is not None:
            s = ((r"Nach dem Satz von Hess (Summe der Schrittwerte mal Schrittfaktor, 298{,}15~K): "
                  if de else r"By Hess's law (sum of step values times step factor, 298.15~K): ")
                 + r"$\Delta_\mathrm{r}H^\circ = %s\,\mathrm{kJ\,mol^{-1}}$" % f(h["dH"], 5))
            if h.get("dG") is not None:
                s += r", $\Delta_\mathrm{r}G^\circ = %s\,\mathrm{kJ\,mol^{-1}}$" % f(h["dG"], 5)
            if h.get("lgK") is not None:
                s += r", $\lg K = %s$" % _fx(h["lgK"], 2, lang)
            parts.append(_cite_end(s + ".", cites) if cites else s + ".")
            used.add("kette-dh")
            vals.append(("kette-dh", r"$\Delta_\mathrm{r}H^\circ$ " + tex_escape("der Kette" if de else "of the chain"),
                         r"$%s\,\mathrm{kJ\,mol^{-1}}$" % f(h["dH"], 5), nplain(h["dH"], 5, lang) + " kJ/mol"))
        elif h.get("missing"):
            parts.append(tex_escape(("Hess: Für Schritt %s fehlen Bildungsdaten." if de else "Hess: formation data missing for step %s.")
                                    % ", ".join(str(n) for n in h["missing"])))
    a = r.get("amounts") or {}
    p = a.get("product") or {}
    main = a.get("main")
    if main and p.get("n_actual") is not None:
        sp = C.parse_species(main["species"]).latex()
        if a.get("mode") == "target":
            s = (r"Zielmenge $%s\,\mathrm{mol}$ $%s$" if de else r"Target amount $%s\,\mathrm{mol}$ of $%s$") % (f(p["n_actual"]), sp)
        else:
            s = (r"Aus den Einsatzmengen entstehen $%s\,\mathrm{mol}$ $%s$" if de else r"The feeds give $%s\,\mathrm{mol}$ of $%s$") % (f(p["n_actual"]), sp)
        if p.get("m_actual") is not None:
            s += r" ($%s\,\mathrm{g}$)" % f(p["m_actual"])
        if a.get("yield_overall") is not None:
            s += (r"; Gesamtausbeute $%s\,\%%$" if de else r"; overall yield $%s\,\%%$") % f(a["yield_overall"], 3)
            vals.append(("kette-ausbeute", tex_escape("Gesamtausbeute der Kette" if de else "Overall yield of the chain"),
                         r"$%s\,\%%$" % f(a["yield_overall"], 3), nplain(a["yield_overall"], 3, lang) + " %"))
        parts.append(s + ".")
    g = r.get("green") or {}
    gs = []
    if g.get("AE") is not None:
        gs.append((r"Atomökonomie $%s\,\%%$" if de else r"atom economy $%s\,\%%$") % f(g["AE"], 3))
    if g.get("E") is not None:
        gs.append((r"E-Faktor $%s$, PMI $%s$" if de else r"E-factor $%s$, PMI $%s$") % (f(g["E"], 3), f(g["PMI"], 3)))
    if gs:
        parts.append((("Grüne Kennzahlen über die Kette: " if de else "Green metrics over the chain: ") + ", ".join(gs) + ". "
                      + tex_escape("Nur Reagenzien; Lösungsmittel und Aufarbeitung nicht enthalten." if de else
                                   "Reagents only; solvents and work-up not included.")))
    for n in r.get("notes") or []:
        parts.append(r"\textit{%s}" % tex_escape(n))
    b.add_text("reaktionskette", "\n\n".join(parts) + "\n", "Reaktionskette" if de else "Reaction chain")
    if tables and h:
        rows = []
        for s in ok:
            hr = next((x for x in h["rows"] if x["id"] == s["id"]), {})
            rows.append([str(s["n"]), _m(s["latex"]), _m(f(s["yield"], 3)), _m(_frac_tex(s["mult"] or 0)),
                         _m(f(hr.get("dH"), 5)) if hr.get("dH") is not None else "--",
                         _m(f(hr.get("dG"), 5)) if hr.get("dG") is not None else "--"])
        if h.get("dH") is not None:
            rows.append([r"$\Sigma$", "", "", "", _m(f(h["dH"], 5)), _m(f(h["dG"], 5)) if h.get("dG") is not None else "--"])
        head = (["Schritt", "Gleichung", r"Ausbeute / \%", "Faktor", r"$\Delta_\mathrm{r}H^\circ$ / kJ\,mol$^{-1}$", r"$\Delta_\mathrm{r}G^\circ$ / kJ\,mol$^{-1}$"]
                if de else ["Step", "Equation", r"Yield / \%", "Factor", r"$\Delta_\mathrm{r}H^\circ$ / kJ\,mol$^{-1}$", r"$\Delta_\mathrm{r}G^\circ$ / kJ\,mol$^{-1}$"])
        cap = ("Schritte der Reaktionskette; Summe nach dem Satz von Hess (298,15 K)." if de else
               "Steps of the reaction chain; sum by Hess's law (298.15 K).")
        b.add_table("kette-schritte", booktabs(head, rows, "llrrrr", small=True, escape_header=False), tex_escape(cap))
    if tables and a.get("feeds"):
        rows = [[_m(C.parse_species(x["species"]).latex()), str(x["n_step"]),
                 _m(f(x["n"])) if x.get("n") is not None else "--", _m(f(x["m"])) if x.get("m") is not None else "--"] for x in a["feeds"]]
        head = ["Einsatzstoff", "Schritt", r"$n$ / mol", r"$m$ / g"] if de else ["Feed", "Step", r"$n$ / mol", r"$m$ / g"]
        cap = (("Benötigte Einsatzstoffe für die Zielmenge." if a.get("mode") == "target" else "Eingesetzte Mengen der Einsatzstoffe.")
               if de else ("Feeds needed for the target amount." if a.get("mode") == "target" else "Amounts of the feeds charged."))
        b.add_table("kette-einsatz", booktabs(head, rows, "lrrr", small=True, escape_header=False), tex_escape(cap))
    return True


_GREEK = {"Δ": r"\Delta", "α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta", "ε": r"\varepsilon", "η": r"\eta",
          "θ": r"\theta", "κ": r"\kappa", "λ": r"\lambda", "ν": r"\nu", "π": r"\pi", "ρ": r"\rho", "σ": r"\sigma", "τ": r"\tau",
          "φ": r"\varphi", "χ": r"\chi", "ψ": r"\psi", "ω": r"\omega", "Ω": r"\Omega", "‡": r"\ddagger"}


def _latin_text(s: str) -> str:
    """Freitext (Bezeichnung, Quelle) für LaTeX: Latin-1 bleibt, Indizes und griechische Buchstaben werden Mathemodus."""
    out = []
    for c in str(s):
        if c in _SUBC:
            out.append("$_{%s}$" % _SUBC[c])
        elif c in _SUPC:
            out.append("$^{%s}$" % _SUPC[c])
        elif c in _GREEK:
            out.append("$%s$" % _GREEK[c])
        elif c in "−–—":
            out.append("-" if c == "−" else "--")
        elif c in "„“”":
            out.append('"')
        else:
            try:
                c.encode("latin-1")
                out.append(tex_escape(c))
            except UnicodeEncodeError:
                out.append("?")
    return "".join(out)


def _values_section(b, lang, values, tables):
    """UI-13: aus dem Nachschlagefenster übernommene Werte mit Quelle und Übernahmezeitpunkt (Herkunft)."""
    de = lang != "en"
    rows = []
    for v in values[:200]:
        if not isinstance(v, dict) or v.get("value") in (None, ""):
            continue
        src = v.get("source") or {}
        ref = src.get("text") or src.get("short") or ""
        used = []
        for u in (v.get("used") or [])[:50]:
            w = str((u or {}).get("where") or "").strip() if isinstance(u, dict) else ""
            if w and w not in used:
                used.append(w)
        used_txt = ", ".join(used[:3]) + (" …" if len(used) > 3 else "")
        rows.append([_latin_text(str(v.get("sym") or "")[:40]), _latin_text(str(v.get("label") or "")[:160]),
                     _latin_text(f"{v.get('value')} {v.get('unit') or ''}".strip()[:60]), _latin_text(ref[:300]),
                     _latin_text(str(v.get("copied") or "")[:16].replace("T", " ")), _latin_text(used_txt[:120]) or "--"])
    if not rows or not tables:
        return False
    head = (["Symbol", "Grösse", "Wert", "Quelle", "übernommen", "eingesetzt in"] if de else
            ["Symbol", "Quantity", "Value", "Source", "copied", "used in"])
    cap = ("Aus dem Nachschlagefenster übernommene Werte dieser Umgebung, mit Quelle, Zeitpunkt der Übernahme und den Feldern, "
           "in die sie eingesetzt wurden." if de else
           "Values copied from the research window into this environment, with source, time of copying and the fields they "
           "were inserted into.")
    b.add_table("uebernommene-werte", booktabs(head, rows, "llrp{4.5cm}lp{2.5cm}", small=True, escape_header=False), tex_escape(cap))
    return True


def build(request: dict, lang: str = "de", include=None, title=None) -> dict:
    L = T["en" if lang == "en" else "de"]
    state = dict(request.get("state") or {})
    inc = {"steps": True, "tables": True}
    inc.update(request.get("include") or include or {})
    steps = bool(inc.get("steps"))
    tables = bool(inc.get("tables"))
    title = title or request.get("title") or L["title"]
    res = AN.run(state)

    eqr = res.get("equation")
    n_species = len(eqr.get("species") or []) if eqr else 0
    n_species += len([c for c in res.get("species") or [] if not c.get("error")])
    b = Bundle(module="elementrechner", module_name=L["module"], title=title, lang=lang, slug=request.get("slug"),
               summary=(eqr or {}).get("text") or L["summary"].format(n=n_species))

    cited: dict[str, str] = {}

    def cite(key: str) -> str:
        if key not in cited:
            cited[key] = labcite.to_bib(b, "er-" + key, REFS[key])
        return cited[key]

    def cite_aw() -> str:
        """Atomgewichte: Tabelle CIAAW 2024 und die Methode/Werte des Berichts 2021."""
        return ",".join([cite("ciaaw2024"), cite("ciaaw2021")])

    vals, used = [], set()
    any_content = False

    # ---- Gleichung
    if eqr:
        ok = eqr.get("status") in ("ok", "given_ok")
        parts = []
        if ok:
            parts.append(r"\[ %s \]" % eqr["latex"])
            if eqr.get("nuclear"):
                parts.append(L["nuclear"])
            elif eqr.get("status") == "given_ok":
                parts.append(L["given_ok"])
            else:
                parts.append(L["balanced"].format(charge=L["charge"] if any(r == "Ladung" for r in eqr.get("rows") or []) else ""))
            if eqr.get("identified"):
                parts.append(tex_escape(eqr["identified"]) + ".")
            if steps and eqr.get("matrix") and not eqr.get("nuclear"):
                rows = eqr.get("rows") or []
                rn = [("Ladung" if lang == "de" else "charge") if r == "Ladung" else r for r in rows]
                parts.append(L["matrix"].format(rows=", ".join(tex_escape(r) for r in rn)))
                ncol = len(eqr["matrix"][0]) if eqr["matrix"] else 0
                cols = [C.parse_species(sp["text"], bool(eqr.get("nuclear"))).latex() if sp.get("kind") != "unknown" else "?"
                        for sp in eqr.get("species") or []]
                head = " & " + " & ".join(cols)
                body = [r"\mathrm{%s} & " % (r if r in C.Z_OF else ("Q" if r == "Ladung" else tex_escape(r)))
                        + " & ".join(_frac_tex(x) for x in row) for row, r in zip(eqr["matrix"], rows)]
                parts.append(r"\[ \mathbf{A} = \begin{array}{r|%s} %s \\ \hline %s \end{array} \]"
                             % ("r" * ncol, head, r" \\ ".join(body)))
                parts.append(r"\[ \nu = (%s) \]" % ",\\ ".join(_frac_tex(c) for c in eqr["coefs"]))
            vals.append(("gleichung" if lang == "de" else "equation", L["v_eq"], _m(eqr["latex"]), eqr["text"]))
        else:
            parts.append(r"\[ %s \]" % C.format_equation(C.parse_equation(eqr["input"]),
                                                        [Fraction(1)] * len(eqr.get("species") or []), "latex")
                         if eqr.get("species") else "")
            parts.append(r"\textbf{%s.} %s" % (L["problem"], tex_escape(eqr.get("reason") or "")))
            if eqr.get("suggestion_text"):
                parts.append(tex_escape(("Vorschlag: " if lang == "de" else "Suggestion: ") + eqr["suggestion_text"]))
        hints = [h for h in eqr.get("hints") or [] if h]
        if hints:
            parts.append(r"\textit{%s:} %s" % (L["status"], tex_escape(" ".join(dict.fromkeys(hints)))))
        b.add_text("gleichung", "\n\n".join(p for p in parts if p is not None) + "\n", L["eq"])
        any_content = True

        if ok and tables and eqr.get("balance"):
            brows = []
            for r in eqr["balance"]:
                name = r["row"]
                lab = (("Ladung" if lang == "de" else "Charge") if name == "Ladung" else name)
                brows.append([tex_escape(lab), _m(ntex(r["left"], 6, lang)), _m(ntex(r["right"], 6, lang))])
            b.add_table("bilanz", booktabs([L["h_row"], L["h_l"], L["h_r"]], brows, "lrr", escape_header=False), L["bal_cap"])

        # ---- Stöchiometrie
        st = eqr.get("stoich")
        if ok and st:
            sp_tex = [C.parse_species(s["text"], bool(eqr.get("nuclear"))).latex() for s in eqr["species"]]
            rows = []
            for r in st["rows"]:
                i = r["i"]
                y = r.get("yield_pct")
                if r["side"] < 0:
                    n_, m_ = r.get("n_used"), r.get("m_used")
                    rest = r.get("m_left")
                else:
                    n_, m_ = r.get("n_theor"), r.get("m_theor")
                    rest = None
                rows.append([_m(sp_tex[i]) + (r" \textsuperscript{*}" if r.get("limiting") else ""),
                             _m(_frac_tex(r["nu"])), _m(ntex(r.get("M"), 6, lang)) if r.get("M") else "--",
                             _m(ntex(r.get("n_start"), 4, lang)) if r.get("n_start") is not None else "",
                             _m(ntex(r.get("m_start"), 4, lang)) if r.get("m_start") is not None else "",
                             _m(ntex(n_, 4, lang)), _m(ntex(m_, 4, lang)) if m_ is not None else "--",
                             _m(ntex(rest, 4, lang)) if rest is not None else "",
                             (_m(ntex(y, 3, lang)) + r"\,\%") if y is not None else ""])
            keep = [c for c in range(9) if any(row[c] for row in rows)]
            heads = [L["h_sp"], L["h_nu"], L["h_M"], L["h_n0"], L["h_m0"], L["h_n"], L["h_m"], L["h_rest"], L["h_y"]]
            if tables:
                lim_note = r"\textsuperscript{*}\," + ("limitierend" if lang == "de" else "limiting")
                b.add_table("stoechiometrie", booktabs([heads[c] for c in keep], [[row[c] for c in keep] for row in rows],
                                                       "l" + "r" * (len(keep) - 1), small=len(keep) > 6, escape_header=False),
                            L["st_cap"], notes=lim_note, cites=[cite_aw()])
            lim = st["limiting"]
            txt = [L["lim"].format(sp=_m(sp_tex[lim]), xi=ntex(st["extent"], 4, lang))]
            gas = []
            for k, a in (state.get("amounts") or {}).items():
                if a.get("V_L") is not None and a.get("c_molL") is None:
                    gas.append(a)
            if steps:
                txt.append(L["st_steps"])
            if gas:
                g = gas[0]
                txt.append(_cite_end(L["gas"].format(T=ntex(float(g.get("T_K") or 273.15), 5, lang),
                                                     p=ntex(float(g.get("p_Pa") or 101325), 6, lang)), cite("codata2022")))
            if any(r.get("yield_pct") is not None for r in st["rows"]):
                txt.append(L["yield"])
            if st.get("atom_economy"):
                aes = ", ".join(f"{_m(sp_tex[a['i']])}: {_m(ntex(a['pct'], 3, lang))}\\,\\%" for a in st["atom_economy"])
                txt.append(L["ae"] + r"~\cite{%s}: " % cite("trost1991") + aes + ".")
            b.add_text("stoechiometrie", "\n\n".join(txt) + "\n", L["stoich"])
            vals.append(("umsatz" if lang == "de" else "extent", L["v_xi"], _m(ntex(st["extent"], 4, lang) + r"\,\mathrm{mol}"),
                         nplain(st["extent"], 4, lang) + " mol"))
            vals.append(("limitierend" if lang == "de" else "limiting", L["v_lim"], _m(sp_tex[lim]), eqr["species"][lim]["unicode"]))
            for r in st["rows"]:
                if r["side"] > 0:
                    u = eqr["species"][r["i"]]["unicode"]
                    f = eqr["species"][r["i"]]["formula"]
                    if r.get("m_theor") is not None:
                        vals.append((_key("masse-" + f, used), L["v_m"].format(f=_m(sp_tex[r["i"]])),
                                     _m(ntex(r["m_theor"], 4, lang) + r"\,\mathrm{g}"), nplain(r["m_theor"], 4, lang) + " g"))
                    vals.append((_key("stoffmenge-" + f, used), L["v_n"].format(f=_m(sp_tex[r["i"]])),
                                 _m(ntex(r["n_theor"], 4, lang) + r"\,\mathrm{mol}"), nplain(r["n_theor"], 4, lang) + " mol"))
                    if r.get("yield_pct") is not None:
                        vals.append((_key("ausbeute-" + f, used), L["v_y"].format(f=_m(sp_tex[r["i"]])),
                                     _m(ntex(r["yield_pct"], 3, lang)) + r"\,\%", nplain(r["yield_pct"], 3, lang) + " %"))
            for a in st.get("atom_economy") or []:
                f = eqr["species"][a["i"]]["formula"]
                vals.append((_key("ae-" + f, used), L["v_ae"].format(f=_m(sp_tex[a["i"]])),
                             _m(ntex(a["pct"], 3, lang)) + r"\,\%", nplain(a["pct"], 3, lang) + " %"))

        # ---- Thermochemie
        th = eqr.get("thermo")
        if ok and th and th.get("rows"):
            _thermo(b, L, lang, eqr, th, steps, tables, cite, vals)

        # ---- Redox (Oxidationszahlen, Halbreaktionen, E°, Nernst, Faraday)
        rx = eqr.get("redox")
        if ok and rx and not rx.get("skip") and (rx.get("redox") or rx.get("half")):
            _redox(b, L, lang, eqr, rx, steps, tables, cite, vals)

    # ---- pH und Titration
    if res.get("ph"):
        _ph_section(b, L, lang, state, res["ph"], tables, cite, vals)
        any_content = True
    if res.get("titration"):
        _titration_section(b, L, lang, state, res["titration"], cite, vals)
        any_content = True

    # ---- Einzelne Stoffe: molare Masse und Zusammensetzung
    for k, card in enumerate(res.get("species") or [], 1):
        mm = card.get("molar_mass")
        if card.get("error") or not mm:
            continue
        sp = C.parse_species(card["text"])
        ftex = sp.latex()
        mt, mp = _with_u(mm["M"], mm.get("u") or 0.0, lang)
        parts = [r"\[ M(%s) = %s\ \mathrm{g\,mol^{-1}} \]" % (ftex, mt)]
        if steps:
            terms = " + ".join(f"{_frac_tex(r['n'])} \\cdot {ntex(r['Ar'], 6, lang)}" for r in mm["rows"])
            parts.append(r"\[ M = %s = %s\ \mathrm{g\,mol^{-1}} \]" % (terms, ntex(mm["M"], 6, lang)))
            parts.append(L["mm_text"])
        for n_ in mm.get("notes") or []:
            parts.append(tex_escape(n_))
        keys = cite_aw() + ("," + cite("ame2020") if any(r.get("isotope") for r in mm["rows"]) else "")
        parts[-1] = _cite_end(parts[-1], keys)
        b.add_text(f"molmasse-{k}", "\n\n".join(parts) + "\n", f"{L['mm']} {sp.unicode()}")
        if tables:
            rows = [[tex_escape(r["el"]), _m(_frac_tex(r["n"])), _m(ntex(r["Ar"], 6, lang)), _m(ntex(r["mass"], 6, lang)),
                     _m(ntex(100 * r["frac"], 4, lang)) + r"\,\%"] for r in mm["rows"]]
            b.add_table(f"zusammensetzung-{k}", booktabs([L["h_el"], L["h_cnt"], L["h_Ar"], L["h_part"], L["h_w"]], rows,
                                                         "lrrrr", escape_header=False),
                        L["mm_cap"].format(f=_m(ftex)), cites=[cite_aw()])
        vals.append((_key("molmasse-" + sp.formula, used), L["v_M"].format(f=_m(ftex)),
                     _m(mt + r"\ \mathrm{g\,mol^{-1}}"), mp + " g/mol"))
        any_content = True

    # ---- Elementaranalyse
    emp = res.get("empirical")
    if emp:
        e = C.parse_species(emp["empirical"]).latex()
        s = L["emp_text"].format(e=_m(e))
        if emp.get("molecular"):
            s += L["emp_mol"].format(m=_m(C.parse_species(emp["molecular"]).latex()))
        s += r"~\cite{%s}." % cite_aw()
        for n_ in emp.get("notes") or []:
            s += "\n\n" + tex_escape(n_)
        b.add_text("elementaranalyse", s + "\n", L["emp"])
        any_content = True

    # ---- Kernchemie
    if res.get("nuclear"):
        _nuclear_section(b, lang, res, tables, cite, vals, used)
        any_content = True

    # ---- Sättigungsindex (ER-S03)
    if res.get("saturation"):
        r = res["saturation"]
        en = lang == "en"
        ks = [x for x in r.get("refs") or [] if x in REFS]
        st = {"übersättigt: Fällung möglich": ("supersaturated: precipitation possible", "übersättigt: Fällung möglich"),
              "untersättigt: keine Fällung": ("undersaturated: no precipitation", "untersättigt: keine Fällung"),
              "nahe Sättigung": ("close to saturation", "nahe Sättigung")}[r["state"]][0 if en else 1]
        ion = _ion_tex
        txt = ((f"Saturation index of {_m(C.parse_species(r['salt']).latex())}: with $c$({ion(r['cation'])}) = "
                f"{_m(ntex(r['c'][0], 3, lang))}\\,mol/L and $c$({ion(r['anion'])}) = {_m(ntex(r['c'][1], 3, lang))}\\,mol/L, "
                f"$\\lg \\mathrm{{IAP}} = {_fx(r['lg_IAP'], 2, lang)}$ and $\\lg K_\\mathrm{{sp}} = {_fx(r['lgKsp'], 2, lang)}$, so "
                f"$\\mathrm{{SI}} = {_fx(r['SI'], 2, lang)}$ ({st}). "
                + ("Activities from the " + ("Davies" if r["model"] == "davies" else "extended Debye-Hückel") + " equation. " if r["model"] else "")
                + "SI $>$ 0 only means that precipitation is possible; no amount is predicted.") if en else
               (f"Sättigungsindex von {_m(C.parse_species(r['salt']).latex())}: mit $c$({ion(r['cation'])}) = "
                f"{_m(ntex(r['c'][0], 3, lang))}\\,mol/L und $c$({ion(r['anion'])}) = {_m(ntex(r['c'][1], 3, lang))}\\,mol/L ist "
                f"$\\lg \\mathrm{{IAP}} = {_fx(r['lg_IAP'], 2, lang)}$ und $\\lg K_\\mathrm{{sp}} = {_fx(r['lgKsp'], 2, lang)}$, also "
                f"$\\mathrm{{SI}} = {_fx(r['SI'], 2, lang)}$ ({st}). "
                + ("Aktivitäten nach der " + ("Davies-Gleichung" if r["model"] == "davies" else "erweiterten Debye-Hückel-Gleichung") + ". " if r["model"] else "")
                + "SI $>$ 0 heisst nur, dass Fällung möglich ist; eine Menge wird nicht vorhergesagt."))
        b.add_text("saettigung", _cite_end(txt, ",".join(cite(x) for x in ks)) + "\n",
                   "Saturation index" if en else "Sättigungsindex")
        vals.append(("SI", "SI", _m(_fx(r["SI"], 2, lang)), _fxp(r["SI"], 2, lang)))
        any_content = True

    # ---- Dampfdruck und kolligative Eigenschaften (ER-X03)
    _SOLV_EN = {"Wasser": "water", "Benzol": "benzene", "Aceton": "acetone", "Toluol": "toluene", "n-Hexan": "n-hexane",
                "Essigsäure": "acetic acid", "Tetrachlormethan": "tetrachloromethane", "Schwefelkohlenstoff": "carbon disulfide",
                "Naphthalin": "naphthalene", "Campher": "camphor"}
    _solv = lambda n, en: _SOLV_EN.get(n, n.lower()) if en else n   # noqa: E731
    if res.get("vapor"):
        r = res["vapor"]
        en = lang == "en"
        parts = []
        if r.get("pvap"):
            v = r["pvap"]
            parts.append((f"The vapour pressure of {_solv(v['name'], en)} at $T = {_fx(v['T'], 2, lang)}$\\,K from the Antoine "
                          f"equation $\\lg(p/\\mathrm{{bar}}) = A - B/(T/\\mathrm{{K}} + C)$ with $A = {_fx(v['A'], 5, lang)}$, "
                          f"$B = {_fx(v['B'], 3, lang)}$, $C = {_fx(v['C'], 3, lang)}$ ({_amp(v['orig'])}, valid "
                          f"{_fx(v['range'][0], 1, lang)}--{_fx(v['range'][1], 1, lang)}\\,K) is "
                          f"$p = {ntex(v['p_kPa'], 4, lang)}$\\,kPa.") if en else
                         (f"Der Dampfdruck von {_solv(v['name'], en)} bei $T = {_fx(v['T'], 2, lang)}$\\,K nach der Antoine-Gleichung "
                          f"$\\lg(p/\\mathrm{{bar}}) = A - B/(T/\\mathrm{{K}} + C)$ mit $A = {_fx(v['A'], 5, lang)}$, "
                          f"$B = {_fx(v['B'], 3, lang)}$, $C = {_fx(v['C'], 3, lang)}$ ({_amp(v['orig'])}, gültig "
                          f"{_fx(v['range'][0], 1, lang)}--{_fx(v['range'][1], 1, lang)}\\,K) beträgt "
                          f"$p = {ntex(v['p_kPa'], 4, lang)}$\\,kPa."))
            if v["out_of_range"]:
                parts.append("The temperature is outside the validity range; the value is an extrapolation." if en else
                             "Die Temperatur liegt ausserhalb des Gültigkeitsbereichs; der Wert ist extrapoliert.")
            vals.append(("pdampf", "p (Antoine)", _m(ntex(v["p_kPa"], 4, lang)) + "\\,kPa", nplain(v["p_kPa"], 4, lang) + " kPa"))
        if r.get("bp"):
            v = r["bp"]
            parts.append((f"The boiling temperature at $p = {_fx(v['p_bar'], 4, lang)}$\\,bar is $T = {_fx(v['T'], 1, lang)}$\\,K."
                          if en else
                          f"Die Siedetemperatur bei $p = {_fx(v['p_bar'], 4, lang)}$\\,bar beträgt $T = {_fx(v['T'], 1, lang)}$\\,K.")
                         + ((" (outside the validity range)" if en else " (ausserhalb des Gültigkeitsbereichs)") if v["out_of_range"] else ""))
            vals.append(("tsiede", "T_b(p)", _m(_fx(v["T"], 1, lang)) + "\\,K", _fxp(v["T"], 1, lang) + " K"))
        if r.get("collig"):
            v = r["collig"]
            s = []
            if v.get("dTf") is not None:
                s.append(f"$\\Delta T_\\mathrm{{f}} = i K_\\mathrm{{f}} b = {_fx(v['dTf'], 3, lang)}$\\,K "
                         f"($K_\\mathrm{{f}} = {_fx(v['Kf'], 2, lang)}$\\,K\\,kg/mol)")
                vals.append(("dtf", "dT_f", _m(_fx(v["dTf"], 3, lang)) + "\\,K", _fxp(v["dTf"], 3, lang) + " K"))
            if v.get("dTb") is not None:
                s.append(f"$\\Delta T_\\mathrm{{b}} = i K_\\mathrm{{b}} b = {_fx(v['dTb'], 3, lang)}$\\,K "
                         f"($K_\\mathrm{{b}} = {_fx(v['Kb'], 2, lang)}$\\,K\\,kg/mol)")
                vals.append(("dtb", "dT_b", _m(_fx(v["dTb"], 3, lang)) + "\\,K", _fxp(v["dTb"], 3, lang) + " K"))
            parts.append((f"For $b = {_fx(v['b'], 4, lang)}$\\,mol/kg in {_solv(v['name'], en)} with $i = {_fx(v['i'], 2, lang)}$: "
                          + " and ".join(s) + " (ideal dilute solution).") if en else
                         (f"Für $b = {_fx(v['b'], 4, lang)}$\\,mol/kg in {_solv(v['name'], en)} mit $i = {_fx(v['i'], 2, lang)}$: "
                          + " und ".join(s) + " (ideal verdünnte Lösung)."))
        ks = [x for x in r.get("refs") or [] if x in REFS]
        b.add_text("dampfdruck", _cite_end(" ".join(parts), ",".join(cite(x) for x in ks)) + "\n",
                   "Vapour pressure and colligative properties" if en else "Dampfdruck und kolligative Eigenschaften")
        any_content = True

    # ---- Speziation (ER-S02)
    if res.get("speciation"):
        _speciation_section(b, lang, res["speciation"], cite, vals, used)
        any_content = True

    # ---- Kinetik
    if res.get("kinetics"):
        _kinetics_section(b, lang, res, tables, cite, vals, used)
        any_content = True

    # ---- Molekülkarte aus dem Designer
    if (state.get("design") or {}).get("smiles"):
        _design_section(b, lang, state["design"], tables, cite, cite_aw, vals, used)
        any_content = True

    # ---- Ansetzen (Lösungen, Reihen, Puffer, Gase, Reaktionsansatz, Vergleich)
    if res.get("prep") or res.get("plans"):
        _prep_section(b, lang, res, steps, tables, cite, vals, used)
        any_content = True

    sh = state.get("shared")
    if isinstance(sh, dict) and isinstance(sh.get("envelope"), dict):
        _shared_section(b, lang, sh, tables, vals, used)
        any_content = True
    ir = state.get("ir_shared")
    if isinstance(ir, dict) and isinstance(ir.get("envelope"), dict) and ir.get("smiles") and tables:
        _ir_section(b, lang, ir, cite)
        any_content = True
    ch = state.get("chain")                                   # UI-12
    if isinstance(ch, dict) and isinstance(ch.get("steps"), list) and len(ch["steps"]) > 1:
        try:
            if _chain_section(b, lang, ch, tables, cite, vals, used):
                any_content = True
        except C.ChemError:
            pass
    if isinstance(state.get("values"), list) and _values_section(b, lang, state["values"], tables):   # UI-13
        any_content = True

    if not any_content:
        errs = "; ".join(e["error"] for e in res.get("errors") or [])
        raise ValueError(L["nothing"] + (f" ({errs})" if errs else ""))
    if vals:
        b.add_values(vals)
    b.set_source({"state": state, "slug": b.slug, "lang": lang, "include": inc, "title": title}, {})
    return b.to_dict()
