"""Kernchemie (Phase 6, ER-601…605).

Daten: Atommassen AME2020, Halbwertszeiten, Zerfallsarten mit Verzweigung und Häufigkeiten NUBASE2020
(`data/isotopes.json`). Konstanten CODATA 2022. Alle Massen sind Atommassen (mit Elektronen); die Q-Werte
berücksichtigen das je Zerfallsart (Krane 1988, Kap. 8–9).

- Q-Wert und Bindungsenergie (ER-601)
- Zerfallsgesetz, Aktivität, spezifische Aktivität, Bq/Ci (ER-602)
- Zerfallsketten nach Bateman, Gleichgewichtsarten (ER-603)
- Datierung: ¹⁴C, K–Ar, Ar–Ar, U–Pb, Rb–Sr-Isochrone (ER-604)
- Isotopenmuster einer Formel, mittlere Atommasse angereicherter Gemische (ER-605)
"""
from __future__ import annotations

import math
import re
from decimal import Decimal, getcontext
from functools import lru_cache

from . import chem as C

U_MEV = 931.49410372          # m_u·c² in MeV (CODATA 2022)
ME_U = 5.485799090441e-4      # Elektronenmasse in u (CODATA 2022)
N_A = 6.02214076e23           # exakt (SI 2019)
CI_BQ = 3.7e10                # 1 Ci = 3,7·10¹⁰ Bq (exakt, Definition)
YEAR_S = 365.2422 * 86400     # Jahr in NUBASE2020
REFS = ["ame2020", "nubase2020", "codata2022", "krane"]

MODES = {"A": "α", "B-": "β⁻", "B+": "β⁺", "EC": "EC", "IT": "IT", "SF": "SF", "n": "n", "p": "p", "2B-": "2β⁻",
         "B+EC": "β⁺/EC", "EC+B+": "β⁺/EC"}
_SUP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")


class NuclearError(C.ChemError):
    pass


@lru_cache(maxsize=1)
def _data() -> dict:
    return C.isotope_masses()


def key(text: str) -> str:
    """'U-238', '238U', '²³⁸U', 'U238', 'uran-238' (Symbol) -> '238U'."""
    t = str(text).strip().translate(_SUP).replace(" ", "")
    m = re.fullmatch(r"(\d+)([A-Za-z]{1,2})(m\d?)?", t) or re.fullmatch(r"([A-Za-z]{1,2})-?(\d+)(m\d?)?", t)
    if not m:
        raise NuclearError(f"„{text}“ ist kein Nuklid (z. B. U-238, 238U, ²³⁸U)")
    a, s = (m.group(1), m.group(2)) if m.group(1).isdigit() else (m.group(2), m.group(1))
    s = s[0].upper() + s[1:].lower()
    k = f"{int(a)}{s}"
    if k not in _data():
        raise NuclearError(f"{k} ist nicht in NUBASE2020/AME2020")
    return k


def nuclide(text: str) -> dict:
    k = key(text)
    d = dict(_data()[k])
    d["key"] = k
    d["symbol"] = re.sub(r"^\d+", "", k)
    return d


def _mass(k: str) -> float:
    m = _data()[k].get("mass_u")
    if m is None:
        raise NuclearError(f"Keine AME2020-Masse für {k}")
    return m


def _by_za(Z: int, A: int) -> str:
    for k, v in _data().items():
        if v.get("Z") == Z and v.get("A") == A:
            return k
    raise NuclearError(f"Kein Nuklid mit Z = {Z}, A = {A} in den Daten")


# ----------------------------------------------------------------------------- ER-601
def daughter(parent: str, mode: str) -> str:
    p = nuclide(parent)
    Z, A = p["Z"], p["A"]
    dz, da = {"A": (-2, -4), "B-": (1, 0), "B+": (-1, 0), "EC": (-1, 0), "IT": (0, 0), "n": (0, -1), "p": (-1, -1),
              "2B-": (2, 0)}.get(mode, (None, None))
    if dz is None:
        raise NuclearError(f"Zerfallsart {mode} ohne festes Tochternuklid (SF: Spaltprodukte verteilt)")
    return _by_za(Z + dz, A + da)


def q_value(parent: str, mode: str) -> dict:
    """Q in MeV aus Atommassen AME2020: α: M(P) − M(D) − M(⁴He); β⁻ und EC: M(P) − M(D); β⁺: M(P) − M(D) − 2mₑ."""
    mode = {"alpha": "A", "α": "A", "beta-": "B-", "β-": "B-", "β⁻": "B-", "beta+": "B+", "β+": "B+", "β⁺": "B+",
            "ec": "EC"}.get(str(mode).strip(), str(mode).strip())
    if mode == "IT":
        raise NuclearError("IT: Q ist die Anregungsenergie des Isomers (nicht aus Grundzustandsmassen)")
    if mode == "SF":
        raise NuclearError("SF: Q hängt von den Spaltprodukten ab")
    P = key(parent)
    D = daughter(P, mode)
    dm = _mass(P) - _mass(D)
    terms = [f"M({P}) − M({D})"]
    if mode == "A":
        dm -= _mass("4He")
        terms.append("− M(⁴He)")
    elif mode == "B+":
        dm -= 2 * ME_U
        terms.append("− 2mₑ")
    elif mode == "p":
        dm -= _mass("1H")
        terms.append("− M(¹H)")
    elif mode == "n":
        dm -= _mass("1n")
        terms.append("− mₙ")
    u = math.hypot(_data()[P].get("u_u") or 0, _data()[D].get("u_u") or 0)
    Q = dm * U_MEV
    out = {"parent": P, "daughter": D, "mode": mode, "mode_text": MODES.get(mode, mode), "dm_u": dm, "Q_MeV": Q,
           "u_MeV": u * U_MEV, "formula": " ".join(terms), "possible": Q > 0, "refs": REFS[:3] + ["krane"],
           "notes": []}
    if mode == "EC":
        out["notes"].append("EC: Bindungsenergie des eingefangenen Elektrons vernachlässigt (≤ 0,1 MeV).")
    if Q <= 0:
        out["notes"].append("Q ≤ 0: dieser Zerfall ist energetisch nicht möglich.")
    return out


_PART = {  # Teilchen in Kerngleichungen: (Z, A, Rolle)
    "α": (2, 4, "alpha"), "alpha": (2, 4, "alpha"),
    "β-": (-1, 0, "e-"), "β⁻": (-1, 0, "e-"), "beta-": (-1, 0, "e-"), "e-": (-1, 0, "e-"), "e⁻": (-1, 0, "e-"),
    "e": (-1, 0, "e-"), "β": (-1, 0, "e-"),
    "β+": (1, 0, "e+"), "β⁺": (1, 0, "e+"), "beta+": (1, 0, "e+"), "e+": (1, 0, "e+"), "e⁺": (1, 0, "e+"),
    "ν": (0, 0, "nu"), "nu": (0, 0, "nu"), "v": (0, 0, "nu"), "ν̄": (0, 0, "nu"), "anti-nu": (0, 0, "nu"),
    "antinu": (0, 0, "nu"), "γ": (0, 0, "gamma"), "gamma": (0, 0, "gamma"),
    "n": (0, 1, "n"), "p": (1, 1, "p"),
}


def _term(t: str):
    """'2 n', '3n', 'U-238', 'Tc-99m', 'β⁻' -> (Anzahl, Z, A, Art, Nuklid oder None, isomer)."""
    t = t.strip()
    m = re.fullmatch(r"(\d+)\s*(n|p|α|e-|e\+|β-|β\+|β⁻|β⁺)", t)
    cnt = 1
    if m:
        cnt, t = int(m.group(1)), m.group(2)
    if t in _PART or t.lower() in _PART:
        Z, A, kind = _PART.get(t) or _PART[t.lower()]
        return cnt, Z, A, kind, ({"alpha": "4He", "p": "1H", "n": "1n"}.get(kind)), False
    iso = bool(re.fullmatch(r"[A-Za-z]{1,2}-?\d+m\d?", t))          # Tc-99m (Symbol vorn; 238Am ist kein Isomer)
    k = key(t)
    d = _data()[k]
    if k == "4He":
        return cnt, 2, 4, "alpha", k, False
    if k == "1H":
        return cnt, 1, 1, "p", k, False
    return cnt, d["Z"], d["A"], "nuclide", k, iso


def classify(equation: str) -> dict:
    """Kerngleichung lesen ('U-238 -> Th-234 + α', 'Tc-99m -> Tc-99 + γ', 'K-40 + e- -> Ar-40 + ν'), Z und A
    prüfen, Zerfallsart erkennen (α, β⁻, β⁺, EC, IT, SF, n, p, Kernreaktion) und Q aus AME2020-Atommassen."""
    parts = re.split(r"\s*(?:->|→|=>|=)\s*", str(equation).strip())
    if len(parts) != 2 or not all(parts):
        raise NuclearError("Kerngleichung mit einem Pfeil schreiben, z. B. U-238 -> Th-234 + α")
    side = [[_term(x) for x in re.split(r"\s+\+\s+", s) if x.strip()] for s in parts]
    zl, al = sum(c * z for c, z, *_ in side[0]), sum(c * a for c, _, a, *_ in side[0])
    zr, ar = sum(c * z for c, z, *_ in side[1]), sum(c * a for c, _, a, *_ in side[1])
    if (zl, al) != (zr, ar):
        raise NuclearError(f"Nicht ausgeglichen: links Z = {zl}, A = {al}; rechts Z = {zr}, A = {ar}")
    nl = [x for x in side[0] if x[3] == "nuclide"]
    nr = [x for x in side[1] if x[3] in ("nuclide",)]
    kinds_l = {x[3] for x in side[0]}
    kinds_r = [x[3] for x in side[1] for _ in range(x[0])]
    out = {"equation": str(equation).strip(), "Z": zl, "A": al, "balanced": True, "refs": REFS[:3] + ["krane"],
           "notes": []}
    mode = None
    if len(nl) == 1 and nl[0][0] == 1 and kinds_l <= {"nuclide", "e-"}:
        P = nl[0][4]
        if "e-" in kinds_l:
            mode = "EC"
        elif nl[0][5] and len(nr) == 1 and nr[0][4] == P:
            mode = "IT"
        elif len(nr) >= 2 or (nr and sum(x[0] for x in nr) >= 2):
            mode = "SF"
        elif kinds_r.count("alpha") == 1:
            mode = "A"
        elif kinds_r.count("e-") == 2:
            mode = "2B-"
        elif kinds_r.count("e-") == 1:
            mode = "B-"
        elif kinds_r.count("e+") == 1:
            mode = "B+"
        elif kinds_r.count("n") == 1:
            mode = "n"
        elif kinds_r.count("p") == 1:
            mode = "p"
    out["mode"] = mode or "reaction"
    out["mode_text"] = MODES.get(mode, "Kernreaktion") if mode else "Kernreaktion"
    if mode in ("A", "B-", "B+", "EC", "n", "p", "2B-") and mode != "2B-":
        q = q_value(nl[0][4], mode)
        out.update({k: q[k] for k in ("parent", "daughter", "Q_MeV", "u_MeV", "formula", "possible")})
        out["notes"] += q["notes"]
        if mode == "EC" and "nu" not in kinds_r:
            out["notes"].append("Neutrino ergänzt (EC: e⁻ + p → n + ν).")
        if mode == "B-" and "nu" not in kinds_r:
            out["notes"].append("Antineutrino ergänzt (β⁻: n → p + e⁻ + ν̄).")
        if mode == "B+" and "nu" not in kinds_r:
            out["notes"].append("Neutrino ergänzt (β⁺: p → n + e⁺ + ν).")
    elif mode == "IT":
        out["parent"] = nl[0][4]
        out["notes"].append("IT: Q = Anregungsenergie des Isomers; AME2020-Grundzustandsmassen enthalten sie nicht.")
    else:
        # SF, Kernreaktion, 2β⁻: Q aus Atommassen; Elektronen heben sich auf, wenn Z links = Z rechts (neutrale Atome)
        def msum(side_):
            s, u2 = 0.0, 0.0
            for c, z, a, kind, k, _ in side_:
                if kind in ("nu", "gamma"):
                    continue
                if kind in ("e-", "e+"):
                    s += c * ME_U if kind == "e+" else 0.0   # e⁻ ist in der Atommasse enthalten (Z-Bilanz)
                    continue
                s += c * _mass(k)
                u2 += (c * (_data()[k].get("u_u") or 0)) ** 2
            return s, u2
        (ml, ul), (mr, ur) = msum(side[0]), msum(side[1])
        if any(x[3] == "e+" for x in side[1]):
            mr += sum(x[0] for x in side[1] if x[3] == "e+") * ME_U    # Atommassen: je e⁺ ein Hüllenelektron zu viel
        Q = (ml - mr) * U_MEV
        out.update({"Q_MeV": Q, "u_MeV": math.sqrt(ul + ur) * U_MEV, "possible": Q > 0,
                    "formula": "Σ M(links) − Σ M(rechts)"})
        if mode == "SF":
            out["parent"] = nl[0][4]
            out["notes"].append("SF: Q gilt für genau diese Spaltprodukte; reale Spaltung verteilt sich auf viele Paare.")
        if Q <= 0:
            out["notes"].append("Q ≤ 0: endotherm, läuft nur mit zugeführter Energie (Schwelle).")
    return out


def binding(nuc: str) -> dict:
    """Bindungsenergie B = [Z·M(¹H) + N·mₙ − M(A, Z)]·c² (Atommassen, Elektronen heben sich auf)."""
    k = key(nuc)
    d = _data()[k]
    Z, A = d["Z"], d["A"]
    N = A - Z
    dm = Z * _mass("1H") + N * _mass("1n") - _mass(k)
    B = dm * U_MEV
    return {"key": k, "Z": Z, "N": N, "A": A, "mass_defect_u": dm, "B_MeV": B, "B_per_A_MeV": B / A if A else None,
            "refs": REFS[:3]}


# ----------------------------------------------------------------------------- ER-602
def half_life_s(nuc: str) -> float:
    d = nuclide(nuc)
    if d.get("stable"):
        raise NuclearError(f"{d['key']} ist stabil")
    t = d.get("half_life_s")
    if not t:
        raise NuclearError(f"Keine Halbwertszeit für {d['key']} in NUBASE2020")
    return t


def decay(nuc: str | None = None, T_half_s: float | None = None, N0: float | None = None, A0_Bq: float | None = None,
          m0_g: float | None = None, t_s: float = 0.0) -> dict:
    """N(t), A(t), m(t) aus einer Anfangsgrösse; λ = ln 2 / T½; τ = 1/λ."""
    T = T_half_s or half_life_s(nuc)
    lam = math.log(2) / T
    M = _mass(key(nuc)) if nuc else None
    if N0 is None:
        if A0_Bq is not None:
            N0 = A0_Bq / lam
        elif m0_g is not None:
            if M is None:
                raise NuclearError("Masse nur mit Nuklid (molare Masse)")
            N0 = m0_g / M * N_A
        else:
            raise NuclearError("Anfangswert fehlt: N₀, A₀ oder m₀")
    f = math.exp(-lam * t_s)
    N = N0 * f
    out = {"T_half_s": T, "lambda_s": lam, "tau_s": 1 / lam, "N0": N0, "N": N, "A0_Bq": lam * N0, "A_Bq": lam * N,
           "fraction": f, "t_s": t_s, "refs": ["nubase2020", "krane"]}
    if M:
        out["m0_g"] = N0 * M / N_A
        out["m_g"] = N * M / N_A
        out["specific_activity_Bq_g"] = lam * N_A / M
    return out


def specific_activity(nuc: str) -> dict:
    k = key(nuc)
    lam = math.log(2) / half_life_s(k)
    M = _mass(k)
    a = lam * N_A / M
    return {"key": k, "a_Bq_g": a, "a_Ci_g": a / CI_BQ, "lambda_s": lam, "M_g_mol": M, "refs": ["nubase2020", "ame2020"]}


PREFIX = {"": 1.0, "k": 1e3, "M": 1e6, "G": 1e9, "T": 1e12, "P": 1e15, "m": 1e-3, "µ": 1e-6, "u": 1e-6, "n": 1e-9,
          "p": 1e-12}


def activity_convert(value: float, unit: str, to: str) -> float:
    """Bq ↔ Ci mit Vorsätzen (kBq, MBq, mCi, µCi …)."""
    def base(u):
        u = u.strip()
        for b, f in (("Bq", 1.0), ("Ci", CI_BQ)):
            if u.endswith(b) and u[: -len(b)] in PREFIX:
                return PREFIX[u[: -len(b)]] * f
        raise NuclearError(f"Einheit „{u}“ (Bq oder Ci mit Vorsatz)")
    return float(value) * base(unit) / base(to)


# ----------------------------------------------------------------------------- ER-603
def chain(parent: str, max_members: int = 8, min_branch_pct: float = 0.0, follow: str = "major") -> list[dict]:
    """Kette ab parent: je Glied die Zerfallsart mit dem grössten Anteil (follow="major"); endet bei stabil."""
    out = []
    k = key(parent)
    for _ in range(max_members):
        d = _data()[k]
        row = {"key": k, "T_half_s": d.get("half_life_s"), "stable": bool(d.get("stable")), "half_life": d.get("half_life")}
        out.append(row)
        if d.get("stable") or not d.get("decay"):
            break
        modes = [x for x in d["decay"] if x.get("pct") is not None and x["mode"] in ("A", "B-", "B+", "EC", "n", "p")]
        if not modes:
            break
        mm = max(modes, key=lambda x: x["pct"])
        if mm["pct"] < min_branch_pct:
            break
        row["mode"], row["branch"] = mm["mode"], mm["pct"] / 100
        try:
            k = daughter(k, mm["mode"])
        except NuclearError:
            break
    return out


def bateman(members: list[dict], N0: float, times_s: list[float]) -> list[list[float]]:
    """N_i(t) einer linearen Kette (Bateman 1910) mit Verzweigungsanteilen; Rechnung in Dezimalarithmetik
    (60 Stellen), damit sehr verschiedene λ (z. B. Gy und µs) nicht auslöschen. Stabiles Endglied: λ = 0."""
    getcontext().prec = 60
    lam = [Decimal(math.log(2)) / Decimal(m["T_half_s"]) if m.get("T_half_s") else Decimal(0) for m in members]
    br = [Decimal(str(m.get("branch", 1.0))) for m in members]
    n = len(members)
    if len(set(lam)) != n:
        raise NuclearError("Zwei Glieder mit gleicher Zerfallskonstante: Bateman-Lösung in dieser Form nicht anwendbar")
    out = []
    for t in times_s:
        T = Decimal(t)
        row = []
        for j in range(n):
            pre = Decimal(N0)
            for i in range(j):
                pre *= br[i] * lam[i]
            s = Decimal(0)
            for i in range(j + 1):
                den = Decimal(1)
                for k2 in range(j + 1):
                    if k2 != i:
                        den *= (lam[k2] - lam[i])
                s += (-lam[i] * T).exp() / den
            row.append(float(pre * s))
        out.append(row)
    return out


def equilibrium(parent: str, daughter_: str | None = None) -> dict:
    """Säkular (T½(P)/T½(T) > 1000), transient (1 < Verhältnis ≤ 1000), kein Gleichgewicht (≤ 1)."""
    P = key(parent)
    D = key(daughter_) if daughter_ else chain(P, 2)[-1]["key"]
    tp, td = half_life_s(P), (_data()[D].get("half_life_s") or math.inf)
    r = tp / td if td and math.isfinite(td) else 0.0
    if not math.isfinite(td) or _data()[D].get("stable"):
        kind, txt = "none", "Tochter stabil: kein radioaktives Gleichgewicht"
    elif r > 1000:
        kind, txt = "secular", "säkulares Gleichgewicht: A(Tochter) ≈ A(Mutter) nach einigen T½ der Tochter"
    elif r > 1:
        kind, txt = "transient", "transientes Gleichgewicht: A(T)/A(M) → λ_T/(λ_T − λ_M) > 1"
    else:
        kind, txt = "none", "kein Gleichgewicht: die Mutter zerfällt schneller als die Tochter"
    out = {"parent": P, "daughter": D, "ratio": r, "kind": kind, "text": txt, "refs": ["nubase2020", "krane"],
           "notes": ["Grenze säkular/transient bei T½-Verhältnis 1000 gewählt (Lehrbuchkonvention, fliessend)."]}
    if kind == "transient":
        lp, ld = math.log(2) / tp, math.log(2) / td
        out["A_ratio"] = ld / (ld - lp)
        out["t_max_s"] = math.log(ld / lp) / (ld - lp)
    return out


# ----------------------------------------------------------------------------- ER-604
DATING_REFS = {"c14": ["stuiver1977", "godwin1962", "nubase2020"], "kar": ["steiger1977"], "upb": ["jaffey1971"],
               "rbsr": ["villa2015", "steiger1977"]}
LAMBDA = {  # 1/a
    "K40_total": (5.543e-10, "steiger1977"), "K40_e": (0.581e-10, "steiger1977"),
    "U238": (1.55125e-10, "jaffey1971"), "U235": (9.8485e-10, "jaffey1971"),
    "Rb87": (1.3972e-11, "villa2015"), "Rb87_SJ": (1.42e-11, "steiger1977"),
}


def radiocarbon(F14C: float, delta13C: float | None = None) -> dict:
    """Konventionelles ¹⁴C-Alter t = −8033 · ln F¹⁴C (Libby-Halbwertszeit 5568 a, Stuiver & Polach 1977); dazu das
    Alter mit der Cambridge-Halbwertszeit 5730 a (Godwin 1962). F¹⁴C ist bereits auf δ¹³C = −25 ‰ normiert."""
    F = float(F14C)
    if not 0 < F <= 1.5:
        raise NuclearError("F¹⁴C zwischen 0 und 1,5 (Anteil des modernen Kohlenstoffs)")
    t_conv = -8033.0 * math.log(F)
    t_cam = -(5730.0 / math.log(2)) * math.log(F)
    t_nub = -(half_life_s("14C") / YEAR_S / math.log(2)) * math.log(F)
    return {"F14C": F, "age_BP": t_conv, "age_cambridge_a": t_cam, "age_nubase_a": t_nub,
            "notes": ["Konventionelles Alter in Jahren BP (vor 1950) mit der Libby-Halbwertszeit 5568 a – so wird "
                      "berichtet; das ist kein Kalenderalter.",
                      "Kalenderalter nur über eine Kalibrierkurve (IntCal20); ohne Kalibrierung keine Kalenderdaten "
                      "angeben."],
            "refs": DATING_REFS["c14"]}


def k_ar(ar40_k40: float) -> dict:
    """t = 1/λ · ln(1 + (λ/λₑ)·⁴⁰Ar*/⁴⁰K) mit den IUGS-Konstanten (Steiger & Jäger 1977)."""
    lam, le = LAMBDA["K40_total"][0], LAMBDA["K40_e"][0]
    R = float(ar40_k40)
    if R <= 0:
        raise NuclearError("⁴⁰Ar*/⁴⁰K muss grösser als 0 sein")
    t = math.log(1 + lam / le * R) / lam
    return {"R": R, "age_a": t, "lambda": lam, "lambda_e": le, "refs": DATING_REFS["kar"],
            "notes": ["Annahmen: kein Ar-Verlust, kein ererbtes ⁴⁰Ar (Überschussargon), K-System geschlossen."]}


def ar_ar(R: float, J: float) -> dict:
    lam = LAMBDA["K40_total"][0]
    t = math.log(1 + float(J) * float(R)) / lam
    return {"R": float(R), "J": float(J), "age_a": t, "refs": DATING_REFS["kar"],
            "notes": ["J aus einem mitbestrahlten Standard bekannten Alters; R = ⁴⁰Ar*/³⁹Ar_K."]}


def u_pb(pb206_u238: float | None = None, pb207_u235: float | None = None) -> dict:
    out = {"refs": DATING_REFS["upb"], "notes": ["Annahmen: radiogenes Pb korrigiert (kein Anfangs-Pb), System geschlossen."]}
    if pb206_u238 is not None:
        out["age_206_a"] = math.log(1 + float(pb206_u238)) / LAMBDA["U238"][0]
    if pb207_u235 is not None:
        out["age_207_a"] = math.log(1 + float(pb207_u235)) / LAMBDA["U235"][0]
    if "age_206_a" in out and "age_207_a" in out:
        a, b = out["age_206_a"], out["age_207_a"]
        out["concordant"] = abs(a - b) / max(a, b) < 0.01
        out["notes"].append("Konkordant: beide Alter innerhalb 1 %." if out["concordant"] else
                            "Diskordant: Pb-Verlust oder Mischung – Concordia-Auswertung nötig.")
    if len(out) == 2:
        raise NuclearError("²⁰⁶Pb*/²³⁸U oder ²⁰⁷Pb*/²³⁵U angeben")
    return out


def rb_sr(points: list[tuple[float, float]], constant: str = "villa2015") -> dict:
    """Isochrone ⁸⁷Sr/⁸⁶Sr gegen ⁸⁷Rb/⁸⁶Sr (kleinste Quadrate, ungewichtet): Steigung m = e^{λt} − 1."""
    if len(points) < 3:
        raise NuclearError("Isochrone: mindestens drei Proben")
    xs, ys = [float(p[0]) for p in points], [float(p[1]) for p in points]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        raise NuclearError("Isochrone: die Rb/Sr-Verhältnisse unterscheiden sich nicht")
    m = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    b = my - m * mx
    res = [y - (b + m * x) for x, y in zip(xs, ys)]
    s = math.sqrt(sum(r * r for r in res) / (n - 2)) if n > 2 else 0.0
    sm = s / math.sqrt(sxx)
    lam = LAMBDA["Rb87" if constant == "villa2015" else "Rb87_SJ"][0]
    if m <= -1:
        raise NuclearError("Isochrone: Steigung ≤ −1")
    t = math.log(1 + m) / lam
    return {"slope": m, "u_slope": sm, "intercept": b, "age_a": t, "u_age_a": sm / ((1 + m) * lam), "lambda": lam,
            "constant": constant, "residuals": res, "refs": DATING_REFS["rbsr"],
            "notes": ["Ungewichtete Ausgleichsgerade (keine York-Regression); Unsicherheit nur aus der Streuung.",
                      "Annahmen: gleiche Anfangs-⁸⁷Sr/⁸⁶Sr aller Proben, System seither geschlossen."]}


# ----------------------------------------------------------------------------- ER-606 Rechner
MEV_J = 1.602176634e-13       # 1 MeV in J (e exakt, SI 2019)


def register_calc_functions():
    """Qval("U-238", "A") in J, Bnuc("Fe-56") (je Nukleon) in J, Thalf("C-14") in s, Aspec("Ra-226") in Bq/kg,
    Ma("U-235") Atommasse in kg/mol – Daten AME2020/NUBASE2020."""
    from . import expr as E
    from . import units as U

    def _s(x, fn):
        return C._str_arg(x, fn)
    E.register_string_function("Qval", lambda ctx, n, m: q_value(_s(n, "Qval"), _s(m, "Qval"))["Q_MeV"] * MEV_J, 2, 2,
                               U.kind_dims("energy"), 'Qval("U-238", "A") – Q-Wert (A, B-, B+, EC) aus AME2020-Massen')
    E.register_string_function("Bnuc", lambda ctx, n: binding(_s(n, "Bnuc"))["B_per_A_MeV"] * MEV_J, 1, 1,
                               U.kind_dims("energy"), 'Bnuc("Fe-56") – Bindungsenergie je Nukleon (AME2020)')
    E.register_string_function("Thalf", lambda ctx, n: half_life_s(_s(n, "Thalf")), 1, 1, U.kind_dims("time"),
                               'Thalf("C-14") – Halbwertszeit (NUBASE2020)')
    E.register_string_function("Aspec", lambda ctx, n: specific_activity(_s(n, "Aspec"))["a_Bq_g"] * 1000, 1, 1,
                               U.parse_unit("Bq/kg")[1], 'Aspec("Ra-226") – spezifische Aktivität λ·N_A/M')
    E.register_string_function("Ma", lambda ctx, n: _mass(key(_s(n, "Ma"))) / 1000, 1, 1, U.kind_dims("molar_mass"),
                               'Ma("U-235") – Atommasse eines Nuklids (AME2020) als molare Masse')


# ----------------------------------------------------------------------------- ER-605
def _iso_comp(el: str) -> list[tuple[float, float, int]]:
    """(Masse, Anteil, A) der stabilen bzw. natürlichen Isotope (Häufigkeiten NUBASE2020 'IS')."""
    rows = []
    for k, v in _data().items():
        if re.sub(r"^\d+", "", k) == el and v.get("abundance_nubase_pct"):
            rows.append((v["mass_u"], v["abundance_nubase_pct"] / 100, v["A"]))
    if not rows:
        raise NuclearError(f"{el}: keine natürliche Isotopenzusammensetzung (radioaktiv ohne stabiles Isotop?)")
    s = sum(r[1] for r in rows)
    return [(m, f / s, a) for m, f, a in rows]


def isotope_pattern(formula: str, threshold: float = 0.001, limit: int = 40) -> dict:
    """Massenspektrum (Isotopenmuster) einer Formel: Peaks je Nominalmasse mit mittlerer exakter Masse und
    relativer Intensität (grösster Peak = 100)."""
    sp = C.parse_species(formula)
    counts = {e: int(n) for e, n in sp.counts.items() if e not in ("e", "+")}
    dist = {0: (1.0, 0.0)}                                    # A_sum -> (p, p·m)
    for el, n in counts.items():
        comp = _iso_comp(el)
        for _ in range(n):
            new = {}
            for A0, (p0, pm0) in dist.items():
                for m, f, a in comp:
                    p = p0 * f
                    if p < 1e-12:
                        continue
                    q = new.get(A0 + a, (0.0, 0.0))
                    new[A0 + a] = (q[0] + p, q[1] + pm0 * f + p * m)
            dist = new
    top = max(p for p, _ in dist.values())
    peaks = [{"A": A, "mass_u": pm / p, "rel": 100 * p / top, "frac": p} for A, (p, pm) in sorted(dist.items())
             if p / top >= threshold]
    e_corr = -sp.charge * ME_U if sp.charge else 0.0
    for pk in peaks:
        pk["mass_u"] += e_corr
    return {"formula": sp.unicode(), "peaks": peaks[:limit], "charge": sp.charge,
            "refs": ["nubase2020", "ame2020"],
            "notes": ["Häufigkeiten: repräsentative Isotopenzusammensetzung (NUBASE2020, nach IUPAC); natürliche "
                      "Schwankungen verschieben die Verhältnisse leicht."]}


def enriched_mass(composition: dict) -> dict:
    """Mittlere Atommasse eines Gemischs {'6Li': 95, '7Li': 5} (Anteile in % oder als Stoffmengenanteil)."""
    if not composition:
        raise NuclearError("Zusammensetzung fehlt")
    rows = [(key(k), float(v)) for k, v in composition.items()]
    els = {re.sub(r"^\d+", "", k) for k, _ in rows}
    if len(els) != 1:
        raise NuclearError("Nur Isotope eines Elements")
    s = sum(v for _, v in rows)
    if s <= 0:
        raise NuclearError("Summe der Anteile muss grösser als 0 sein")
    M = sum(_mass(k) * v / s for k, v in rows)
    notes = []
    if abs(s - 100) > 1e-6 and abs(s - 1) > 1e-6:
        notes.append(f"Anteile ergeben {s:g}, normiert.".replace(".", ","))
    return {"element": els.pop(), "M": M, "fractions": {k: v / s for k, v in rows}, "notes": notes, "refs": ["ame2020"]}
