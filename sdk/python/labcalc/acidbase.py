"""Säure–Base-Gleichgewichte in Wasser: pH beliebiger Mischungen (starke und schwache, mehrprotonige Säuren und Basen,
Salze, Puffer), Speziesverteilung, Titrationskurven und Puffervorschläge.

Methode (systematische Behandlung mit Ladungs- und Massenbilanz, Harris 2016): Protonenbilanz bezogen auf die
eingesetzten Formen,
    [H⁺] − [OH⁻] = Σᵢ cᵢ·(hᵢ − n̄ᵢ) + c(starke Säure) − c(starke Base),
hᵢ = Protonen der eingesetzten Form, n̄ᵢ = mittlere gebundene Protonen beim gesuchten pH. Die Gleichung ist im pH
monoton und wird durch Bisektion gelöst. Ideal verdünnt: Konzentrationen statt Aktivitäten (die Ionenstärke wird
angegeben). pKa bei 25 °C aus labcalc.substances (NIST SRD 46, IUPAC-pKa-Datensatz, HSDB), pKw(T) nach Bandura &
Lvov 2006 (13,995 bei 25 °C; Dichte nach Kell 1975), wählbar 0–100 °C. pKa-Werte werden nicht auf andere Temperaturen
umgerechnet (Hinweis). Starke Säuren und Basen nach Harris 2016.
"""
from __future__ import annotations

import math
import re
from functools import lru_cache

from . import chem as C

REFS = ["harris", "atkins", "bandura2006"]
STRONG = -30.0                                     # Platzhalter-pKa einer vollständig dissoziierten Stufe
# starke Säuren (Harris 2016): (Hill ohne Ladung) -> Anzahl Protonen; H2SO4 nur die erste Stufe
STRONG_ACIDS = {"ClH": 1, "BrH": 1, "HI": 1, "HNO3": 1, "ClHO4": 1}
SPECTATOR_ANIONS = {("Cl", -1), ("Br", -1), ("I", -1), ("NO3", -1), ("ClO4", -1)}
SPECTATOR_CATIONS = {"Li", "Na", "K", "Rb", "Cs", "Mg", "Ca", "Sr", "Ba"}
SULFATE = {("H2O4S", 0): 2, ("HO4S", -1): 1, ("O4S", -2): 0}


class AcidBaseError(C.ChemError):
    pass


def _pkw() -> float:
    from .substances import PKW_25
    return PKW_25


def water_density(T_C: float) -> float:
    """Dichte von Wasser bei 0,101325 MPa in kg/m³, 0–100 °C (Kell 1975, Gl. für die Temperaturskala IPTS-68)."""
    t = float(T_C)
    num = (999.83952 + 16.945176 * t - 7.9870401e-3 * t ** 2 - 46.170461e-6 * t ** 3 + 105.56302e-9 * t ** 4
           - 280.54253e-12 * t ** 5)
    return num / (1 + 16.879850e-3 * t)


def pkw(T_C: float = 25.0) -> float:
    """pKw von Wasser bei 0,1 MPa nach Bandura & Lvov 2006 (Gl. 3 mit ihren Parametern), Dichte nach Kell 1975.
    Gültig hier 0–100 °C; ergibt 14,946 / 13,995 / 13,264 / 12,696 / 12,252 bei 0 / 25 / 50 / 75 / 100 °C (Tabelle der
    Quelle)."""
    t = float(T_C)
    if not 0 <= t <= 100:
        raise AcidBaseError("Temperatur für pKw: 0 bis 100 °C")
    if abs(t - 25) < 1e-9:
        return _pkw()
    T = t + 273.15
    rho = water_density(t) / 1000                       # g/cm³
    n = 6
    a0, a1, a2 = -0.864671, 8659.19, -22786.2
    b0, b1, b2 = 0.642044, -56.8534, -0.375754
    Q = rho * math.exp(a0 + a1 / T + a2 / T ** 2 * rho ** (2 / 3))
    pkw_g = 0.61415 + 48251.33 / T - 67707.93 / T ** 2 + 10102100 / T ** 3
    return (-2 * n * (math.log10(1 + Q) - Q / (Q + 1) * rho * (b0 + b1 / T + b2 * rho)) + pkw_g
            + 2 * math.log10(18.015268 / 1000))


PKW_REFS = ["bandura2006", "kell1975"]


def _plain_counts(counts) -> dict:
    out = {}
    for k, v in counts.items():
        b = re.sub(r"^\d+", "", k)
        b = "H" if b in ("D", "T") else b
        out[b] = out.get(b, 0) + int(v)
    return out


def _hill(counts) -> str:
    return C._hill(counts)


# ----------------------------------------------------------------------------- Säure-Base-Systeme aus den Daten
_ACID_J = re.compile(r"^H([₀-₉]*)L")


def _j_of(acid: str) -> int | None:
    m = _ACID_J.match(acid or "")
    if not m:
        return None
    d = m.group(1).translate(str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789"))
    return int(d) if d else 1


@lru_cache(maxsize=4096)
def acid_system(key: str) -> dict | None:
    """Protonierungsstufen eines Stoffs der Sammlung: {"n": Protonen der neutralen Form, "steps": {j: Wert}} mit
    j = Protonen der sauren Form HjL der Stufe HjL ⇌ Hj−1L + H⁺. None ohne pKa-Werte."""
    from . import substances as S
    vals = [v for v in S.pka_values(key)["values"] if v["kind"] == "pKa" and v.get("value") is not None]
    if not vals:
        return None
    m = S.get(key) or {}
    has_n = "N" in (m.get("formula") or "")
    srd = [v for v in vals if v["source"] == "srd46" and _j_of(v.get("acid"))]
    steps, n, how = {}, None, ""
    if srd:
        by_j = {}
        for v in srd:
            by_j.setdefault(_j_of(v["acid"]), []).append(v)
            if v.get("step"):
                n = v["step"] + _j_of(v["acid"]) - 1
        if n is None:
            n = min(by_j) - 1
        steps = {j: S.choose(l, 25.0) for j, l in by_j.items()}
        how = "NIST SRD 46 (Protonierungskonstanten)"
    else:
        iu = [v for v in vals if v["source"] == "iupac_pka" and re.match(r"pKa(H)?\d+$", v.get("type") or "")]
        if iu:
            acid = {}
            base = {}
            for v in iu:
                mm = re.match(r"pKa(H)?(\d+)$", v["type"])
                (base if mm.group(1) else acid).setdefault(int(mm.group(2)), []).append(v)
            n = max(acid) if acid else 0
            for k, l in acid.items():
                steps[n - k + 1] = S.choose(l, 25.0)
            bvals = sorted((S.choose(l, 25.0) for l in base.values()), key=lambda v: -v["value"])
            for k, v in enumerate(bvals, 1):
                steps[n + k] = v
            how = "IUPAC-pKa-Datensatz"
        else:
            hs = [v for v in vals if v.get("step") is None]
            if not hs:
                return None
            v = S.choose(hs, 25.0)
            base_like = False
            if m.get("smiles"):
                try:
                    from . import molgraph as G
                    keys = {g["key"] for g in G.functional_groups(G.parse(m["smiles"]))}
                    base_like = bool(keys & {"amine1", "amine2", "amine3", "arylamine", "heteroarene", "imine"}) and \
                        not keys & {"acid", "phenol", "sulfonic"}
                except Exception:  # noqa: BLE001
                    pass
            n = 0 if base_like else 1
            steps = {1: v}
            how = "HSDB (Stufe aus der Struktur zugeordnet)"
    # in Wasser bedeutungslose Stufen (pKa < −1,5) und Protonierung von Oxosäuren ohne N weglassen
    steps = {j: v for j, v in steps.items() if v and v["value"] >= -1.5 and (j <= n or has_n)}
    if not steps:
        return None
    return {"key": key, "n": n, "steps": steps, "how": how}


def _system_for_fragment(hill: str, q: int, key_hint: str | None = None) -> dict | None:
    """Säure-Base-System eines (Teil-)Ions: Stammverbindung mit q Protonen mehr bzw. weniger in der Sammlung suchen."""
    from . import substances as S
    if (hill, q) in SULFATE:
        k = S.resolve("sulfuric acid")
        st = {2: {"value": STRONG, "source": "harris", "strong": True}}
        sys_ = acid_system(k) if k else None
        if sys_ and 1 in sys_["steps"]:
            st[1] = sys_["steps"][1]
        return {"key": k, "n": 2, "steps": st, "how": "erste Stufe stark (Harris 2016), zweite aus den Daten",
                "h": SULFATE[(hill, q)]}
    if key_hint and q == 0:
        s = acid_system(key_hint)
        if s:
            return dict(s, h=s["n"])
    counts = _counts_of(hill)
    counts["H"] = counts.get("H", 0) - q                      # Anion: + |q| H; Kation: − q H
    if counts["H"] < 0:
        return None
    if counts["H"] == 0:
        del counts["H"]
    parent = _hill(counts)
    for k in S._index()[1].get(parent, []):
        s = acid_system(k)
        if s:
            h = s["n"] + q
            js = sorted(s["steps"])
            if min(js) - 1 <= h <= max(js):
                return dict(s, h=h)
    return None


def _counts_of(hill: str) -> dict:
    return {e: int(n or 1) for e, n in re.findall(r"([A-Z][a-z]?)(\d*)", hill)}


# ----------------------------------------------------------------------------- Komponenten
def component(text: str, c: float) -> dict:
    """Stoff mit Konzentration c (mol/L) -> Beiträge: Systeme, starke Säure/Base, Zuschauerionen."""
    from . import substances as S
    from . import molgraph as G
    text = text.strip()
    if c < 0:
        raise AcidBaseError("Konzentration muss ≥ 0 sein")
    key = S.resolve(text)
    frags = []                                          # [(hill, Ladung, Anzahl, key_hint)]
    sp = None
    try:
        sp = C.parse_species(text)
    except C.ChemError:
        pass
    m = S.get(key) if key else None
    if m and m.get("smiles") and (sp is None or sp.charge == 0):
        g = G.parse(m["smiles"])
        tmp = {}
        for fr in g.fragments():
            cnt = {}
            for i in fr:
                cnt[g.el[i]] = cnt.get(g.el[i], 0) + 1
                if g.h[i]:
                    cnt["H"] = cnt.get("H", 0) + g.h[i]
            qq = sum(g.q[i] for i in fr)
            k = (_hill(cnt), qq)
            tmp[k] = tmp.get(k, 0) + 1
        single = len(tmp) == 1 and list(tmp.values())[0] == 1
        frags = [(h, q, n, key if single else None) for (h, q), n in tmp.items()]
    elif sp is not None and sp.kind == "chem":
        frags = [(_hill(_plain_counts(sp.counts)), sp.charge, 1, key if sp.charge == 0 else None)]
    else:
        raise AcidBaseError(f"„{text}“ ist weder Formel noch Stoff der Sammlung")
    out = {"text": text, "c": c, "name": (m or {}).get("de") or (m or {}).get("en") or "", "key": key,
           "systems": [], "strong_acid": 0.0, "strong_base": 0.0, "ions": [], "notes": []}
    for hill, q, n, khint in frags:
        cc = c * n
        if (hill, q) == ("HO", -1):
            out["strong_base"] += cc
            out["ions"].append((q, cc))
            continue
        if (hill, q) in (("H", 1), ("H3O", 1)):
            out["strong_acid"] += cc
            out["ions"].append((q, cc))
            continue
        if q == 0 and hill in STRONG_ACIDS:
            out["strong_acid"] += cc * STRONG_ACIDS[hill]
            out["ions"].append((-1, cc))
            out["notes"].append(f"{text}: starke Säure, vollständig dissoziiert (Harris 2016)")
            continue
        if (hill, q) in SPECTATOR_ANIONS or (q > 0 and hill in SPECTATOR_CATIONS):
            out["ions"].append((q, cc))
            continue
        s = _system_for_fragment(hill, q, khint)
        if s:
            out["systems"].append({"c": cc, "h": s["h"], "steps": {j: v["value"] for j, v in s["steps"].items()},
                                   "src": {j: {k: v.get(k) for k in ("source", "T_C", "I", "label", "ref", "strong")}
                                           for j, v in s["steps"].items()},
                                   "key": s["key"], "how": s["how"], "label": f"{hill}{'' if not q else (str(abs(q)) if abs(q) > 1 else '') + ('+' if q > 0 else '-')}",
                                   "charge_h": q - s["h"]})        # Ladung der Form H0L = q − h
            continue
        if q > 0 and len(_counts_of(hill)) == 1:
            out["ions"].append((q, cc))
            out["notes"].append(f"{hill}{q}+: Hydrolyse des Metallions nicht berücksichtigt (keine Daten)")
            continue
        if q == 0:
            out["notes"].append(f"{text}: keine pKa-Werte – als neutral (ohne Säure-Base-Wirkung) behandelt")
            continue
        raise AcidBaseError(f"Für {hill} (Ladung {q:+d}) gibt es keine pKa-Werte in den mitgelieferten Quellen")
    return out


# ----------------------------------------------------------------------------- Löser
def _forms(sys_: dict, pH: float) -> list[tuple[int, float]]:
    """Anteile αⱼ der Formen HjL (j = jmin−1 … jmax) beim pH."""
    js = sorted(sys_["steps"])
    j0 = js[0] - 1
    logs = [0.0]
    acc = 0.0
    for j in range(js[0], js[-1] + 1):
        pk = sys_["steps"].get(j)
        if pk is None:                                   # Lücke: höhere Stufen ignorieren
            break
        acc += pk - pH
        logs.append(acc)
    mx = max(logs)
    w = [10 ** (x - mx) for x in logs]
    s = sum(w)
    return [(j0 + k, wk / s) for k, wk in enumerate(w)]


def _nbar(sys_, pH):
    return sum(j * a for j, a in _forms(sys_, pH))


def _balance(comps, pH, pkw_=None):
    H = 10 ** -pH
    OH = 10 ** (pH - (pkw_ if pkw_ is not None else _pkw()))
    s = H - OH
    for c in comps:
        s -= c["strong_acid"] - c["strong_base"]
        for y in c["systems"]:
            s -= y["c"] * (y["h"] - _nbar(y, pH))
    return s


def solve(comps: list[dict], pkw_: float | None = None) -> float:
    lo, hi = -2.0, 16.5
    flo, fhi = _balance(comps, lo, pkw_), _balance(comps, hi, pkw_)
    if flo < 0 or fhi > 0:
        raise AcidBaseError("pH ausserhalb −2 … 16,5 (Konzentrationen prüfen)")
    for _ in range(80):
        mid = (lo + hi) / 2
        if _balance(comps, mid, pkw_) > 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def parse_mixture(text: str) -> list[tuple[str, float]]:
    """„0,1 M CH3COOH; 0,05 M CH3COONa“ -> [(Stoff, mol/L)]. Einheiten M, mol/L, mM, mmol/L, µM."""
    units = {"m": 1.0, "mol/l": 1.0, "mm": 1e-3, "mmol/l": 1e-3, "µm": 1e-6, "um": 1e-6, "µmol/l": 1e-6}
    out = []
    for part in re.split(r"[;\n]|\s\+\s|,\s(?=\d)", text):
        part = part.strip()
        if not part:
            continue
        mm = re.match(r"^([\d.,]+(?:[eE][-+]?\d+)?)\s*(mol/L|mmol/L|µmol/L|M|mM|µM|uM)\s+(.+)$", part, re.I)
        if not mm:
            raise AcidBaseError(f"„{part}“: erwartet „Konzentration Einheit Stoff“, z. B. 0,1 M CH3COOH")
        c = float(mm.group(1).replace(",", ".")) * units[mm.group(2).lower()]
        out.append((mm.group(3).strip(), c))
    if not out:
        raise AcidBaseError("keine Stoffe angegeben")
    return out


def _temp_notes(comps, T_C: float) -> list[str]:
    """Hinweis, wenn verwendete pKa-Werte bei einer anderen Temperatur gemessen sind (keine Extrapolation)."""
    off = set()
    for c in comps:
        for y in c["systems"]:
            for j, s in (y.get("src") or {}).items():
                tc = (s or {}).get("T_C")
                if tc is not None and abs(float(tc) - T_C) > 2 and not (s or {}).get("strong"):
                    off.add(f"{c['text']} ({float(tc):g} °C)".replace(".", ","))
    if not off:
        return []
    return [f"pKa-Werte gelten bei ihrer Messtemperatur, nicht bei {T_C:g} °C: ".replace(".", ",") + ", ".join(sorted(off))
            + ". Nur pKw ist auf die gewählte Temperatur umgerechnet."]


def ph(mixture, T_C: float = 25.0) -> dict:
    """pH einer Mischung; mixture = Text oder [(Stoff, c)]. Mit Speziesverteilung, Ionenstärke und Quellen.
    T_C: Temperatur für pKw (Bandura & Lvov 2006); pKa-Werte bleiben bei ihrer Messtemperatur (Hinweis)."""
    items = parse_mixture(mixture) if isinstance(mixture, str) else mixture
    comps = [component(t, float(c)) for t, c in items]
    T_C = 25.0 if T_C is None else float(T_C)
    kw = pkw(T_C)
    p = solve(comps, kw)
    H = 10 ** -p
    OH = 10 ** (p - kw)
    species, I = [], 0.5 * (H + OH)
    for c in comps:
        for z, cc in c["ions"]:
            I += 0.5 * cc * z * z
        for y in c["systems"]:
            rows = []
            for j, a in _forms(y, p):
                z = y["charge_h"] + j
                I += 0.5 * y["c"] * a * z * z
                rows.append({"j": j, "charge": z, "alpha": a, "c": y["c"] * a})
            species.append({"component": c["text"], "label": y["label"], "c": y["c"], "forms": rows,
                            "pKa": {str(j): v for j, v in sorted(y["steps"].items())}, "src": y["src"],
                            "how": y["how"]})
    notes = [n for c in comps for n in c["notes"]] + _temp_notes(comps, T_C)
    if I > 0.01:
        notes.append(f"Ionenstärke {I:.3g}".replace(".", ",") + " mol/L: Aktivitätskoeffizienten sind nicht berücksichtigt; "
                     "der wahre pH kann um einige Zehntel abweichen.")
    return {"pH": p, "pOH": kw - p, "H": H, "OH": OH, "I": I, "T_C": T_C, "pH_neutral": kw / 2, "species": species,
            "components": [{"text": c["text"], "c": c["c"], "name": c["name"], "strong_acid": c["strong_acid"],
                            "strong_base": c["strong_base"]} for c in comps],
            "notes": notes, "pKw": kw, "refs": REFS + (["kell1975"] if T_C != 25 else [])}


def titration(analyte, V0: float, titrant: str, c_t: float, V_max: float, n: int = 161, T_C: float = 25.0) -> dict:
    """Titrationskurve: Analyt (Text oder Liste) im Volumen V0 (mL), Massslösung c_t (mol/L) bis V_max (mL);
    T_C wirkt nur auf pKw."""
    items = parse_mixture(analyte) if isinstance(analyte, str) else analyte
    base = [component(t, float(c)) for t, c in items]
    tit = component(titrant, 1.0)
    T_C = 25.0 if T_C is None else float(T_C)
    kw = pkw(T_C)

    def at(V):
        f0, ft = V0 / (V0 + V), V / (V0 + V)
        comps = []
        for c in base:
            comps.append({**c, "strong_acid": c["strong_acid"] * f0, "strong_base": c["strong_base"] * f0,
                          "systems": [dict(y, c=y["c"] * f0) for y in c["systems"]]})
        comps.append({**tit, "strong_acid": tit["strong_acid"] * c_t * ft, "strong_base": tit["strong_base"] * c_t * ft,
                      "systems": [dict(y, c=y["c"] * c_t * ft) for y in tit["systems"]]})
        return solve(comps, kw)
    Vs = [V_max * k / (n - 1) for k in range(n)]
    pts = [(V, at(V)) for V in Vs]
    # Äquivalenzpunkte: Maxima der Steigung, verfeinert
    slope = [(pts[k + 1][1] - pts[k][1]) / (pts[k + 1][0] - pts[k][0]) for k in range(n - 1)]
    eqp = []
    for k in range(1, n - 2):
        s = abs(slope[k])
        if s > abs(slope[k - 1]) and s >= abs(slope[k + 1]) and s > 0.5 * max(abs(x) for x in slope) * 0.1 and s > 0.05:
            a, b = pts[k][0], pts[k + 1][0]
            for _ in range(30):                          # goldener Schnitt auf die Steigung
                m1, m2 = a + (b - a) * 0.382, a + (b - a) * 0.618
                d = 1e-4 * max(V_max, 1)
                g1 = abs(at(m1 + d) - at(m1 - d))
                g2 = abs(at(m2 + d) - at(m2 - d))
                if g1 > g2:
                    b = m2
                else:
                    a = m1
            V = (a + b) / 2
            eqp.append({"V": V, "pH": at(V)})
    bounds = [0.0] + [e["V"] for e in eqp] + [V_max]
    for k, e in enumerate(eqp):
        e["indicators"] = _indicator_fit(at, e["V"], bounds[k], bounds[k + 2])
    return {"points": [[round(V, 5), round(p, 4)] for V, p in pts], "equivalence": eqp, "V0": V0, "c_t": c_t,
            "titrant": titrant, "T_C": T_C, "pKw": kw, "indicator_refs": ["harris"],
            "notes": [n for c in base + [tit] for n in c["notes"]] + _temp_notes(base + [tit], T_C),
            "refs": REFS + (["kell1975"] if T_C != 25 else [])}


# ----------------------------------------------------------------------------- Indikatoren
@lru_cache(maxsize=1)
def _indicator_data() -> dict:
    import json
    import os
    with open(os.path.join(os.path.dirname(__file__), "data", "indicators.json"), encoding="utf-8") as f:
        return json.load(f)


def indicators() -> list[dict]:
    """Säure-Base-Indikatoren (Harris 2016) mit Umschlagbereichen; ein Indikator kann zwei Bereiche haben."""
    return _indicator_data()["indicators"]


def indicator_colours(pH: float) -> list[dict]:
    """Farbe jedes Indikators beim pH: sauer, basisch oder im Umschlag."""
    out = []
    for ind in indicators():
        state, col, hexs = None, None, None
        for r in ind["ranges"]:
            if pH < r["low"]:
                state, col, hexs = "sauer", r["acid"], [r["acid_hex"]]
                break
            if pH <= r["high"]:
                state, col, hexs = "Umschlag", f"{r['acid']}–{r['base']}", [r["acid_hex"], r["base_hex"]]
                break
            state, col, hexs = "basisch", r["base"], [r["base_hex"]]
        out.append({"key": ind["key"], "name": ind["de"], "state": state, "colour": col, "hex": hexs})
    return out


def _indicator_fit(at, V_eq: float, V_lo: float, V_hi: float, grid: int = 121) -> list[dict]:
    """Indikatoren für einen Äquivalenzpunkt: Volumen, bei dem der pH die Mitte (bzw. die Grenzen) des
    Umschlagbereichs erreicht, und der relative Titrierfehler (V − V_eq)/V_eq. Geeignet: Mitte ≤ 0,2 % und beide
    Grenzen ≤ 1 %; bedingt: Mitte ≤ 1 %. Gesucht wird zwischen den benachbarten Äquivalenzpunkten (Kurve dort monoton)."""
    a = V_eq - 0.5 * (V_eq - V_lo)
    b = V_eq + 0.5 * (V_hi - V_eq)
    if b <= a or V_eq <= 0:
        return []
    Vs = [a + (b - a) * k / (grid - 1) for k in range(grid)]
    ps = [at(V) for V in Vs]
    rising = ps[-1] > ps[0]

    def v_at(target):
        for k in range(grid - 1):
            p0, p1 = ps[k], ps[k + 1]
            if (p0 - target) * (p1 - target) <= 0 and p0 != p1:
                lo, hi = Vs[k], Vs[k + 1]
                for _ in range(16):
                    m = (lo + hi) / 2
                    if (at(m) < target) == rising:
                        lo = m
                    else:
                        hi = m
                return (lo + hi) / 2
        return None

    out = []
    for ind in indicators():
        for r in ind["ranges"]:
            mid = (r["low"] + r["high"]) / 2
            Vm = v_at(mid)
            if Vm is None:
                continue
            err = 100 * (Vm - V_eq) / V_eq
            if abs(err) > 1:
                continue
            ends = [v_at(r["low"]), v_at(r["high"])]
            e_ends = [None if v is None else 100 * (v - V_eq) / V_eq for v in ends]
            ok = abs(err) <= 0.2 and all(x is not None and abs(x) <= 1 for x in e_ends)
            first, last = (r["acid"], r["base"]) if rising else (r["base"], r["acid"])
            out.append({"key": ind["key"], "name": ind["de"], "name_en": ind["en"], "low": r["low"], "high": r["high"],
                        "change": f"{first} → {last}", "error_pct": err, "error_ends_pct": e_ends,
                        "rating": "geeignet" if ok else "bedingt", "source": ind.get("source", "harris"),
                        "hex": [r["acid_hex"], r["base_hex"]] if rising else [r["base_hex"], r["acid_hex"]]})
    out.sort(key=lambda x: (x["rating"] != "geeignet", abs(x["error_pct"])))
    return out[:6]


def buffer(key_or_name: str, pH: float, c_total: float = 0.1, T_C: float = 25.0) -> dict:
    """Puffer aus einem Säure-Base-Paar: passende Stufe (pKa nahe pH), Verhältnis nach Henderson–Hasselbalch und
    exakte Zusammensetzung aus der Protonenbilanz (ohne Fremdionen), Pufferkapazität β."""
    from . import substances as S
    key = S.resolve(key_or_name)
    s = acid_system(key) if key else None
    if not s:
        raise AcidBaseError(f"keine pKa-Werte für „{key_or_name}“")
    j, v = min(s["steps"].items(), key=lambda kv: abs(kv[1]["value"] - pH))
    pka = v["value"]
    r = 10 ** (pH - pka)                                 # [Hj-1L]/[HjL]
    sysd = {"steps": {k: x["value"] for k, x in s["steps"].items()}}
    fr = _forms(sysd, pH)
    H = 10 ** -pH
    Ka_terms = sum(c_total * a * (jj - _nbar(sysd, pH)) ** 2 for jj, a in fr)
    T_C = 25.0 if T_C is None else float(T_C)
    kw = pkw(T_C)
    beta = math.log(10) * (H + 10 ** (pH - kw) + Ka_terms)
    m = S.get(key) or {}
    tnote = []
    if v.get("T_C") is not None and abs(float(v["T_C"]) - T_C) > 2:
        tnote = [f"pKa gilt bei {float(v['T_C']):g} °C, nicht bei {T_C:g} °C (nicht umgerechnet)".replace(".", ",")]
    return {"T_C": T_C, "pKw": kw, "notes": tnote,
            "key": key, "name": m.get("de") or m.get("en"), "formula": m.get("formula"), "step": j,
            "k": max(s["steps"]) - j + 1, "pKa": pka, "src": {k: v.get(k) for k in ("source", "T_C", "I", "label")},
            "ratio_base_acid": r, "acid_form_c": c_total / (1 + r), "base_form_c": c_total * r / (1 + r),
            "in_range": abs(pH - pka) <= 1, "beta": beta, "forms": [{"j": jj, "alpha": a} for jj, a in fr],
            "note": "Pufferbereich etwa pKa ± 1; β = ln 10·([H⁺] + [OH⁻] + Σ cᵢαᵢ(j − n̄)²) (Harris 2016)",
            "refs": REFS}


def register_calc_functions():
    from . import expr as E
    from . import units as U
    E.register_string_function("pH", lambda ctx, q, *t: ph(C._str_arg(q, "pH"), _temp_arg(t))["pH"], 1, 2, U.D0,
                               'pH("0,1 M CH3COOH; 0,05 M CH3COONa", T) – pH einer Mischung (Protonenbilanz); '
                               'T optional: 0–100 = °C, 273,15–373,15 = K; Standard 25 °C (wirkt auf pKw)')


def _temp_arg(t) -> float:
    """Optionales Temperatur-Argument einer Rechner-Funktion. Der Rechner rechnet in SI, eine Temperatur mit Einheit
    kommt also in K an; eine reine Zahl 0–100 gilt als °C. Die Bereiche überschneiden sich nicht."""
    if not t:
        return 25.0
    try:
        v = float(t[0])
    except (TypeError, ValueError):
        raise AcidBaseError("Temperatur muss eine Zahl sein (°C oder K)")
    if 273.15 <= v <= 373.15:
        return v - 273.15
    if 0 <= v <= 100:
        return v
    raise AcidBaseError("Temperatur für pH: 0–100 °C bzw. 273,15–373,15 K")


@lru_cache(maxsize=1)
def _all_systems() -> list:
    from . import substances as S
    out = []
    for k, m in S.molecules().items():
        if m.get("own") or not m.get("formula"):
            continue
        try:
            s = acid_system(k)
        except Exception:  # noqa: BLE001
            continue
        if s and s["how"].startswith("NIST"):
            out.append((k, s))
    return out


# übliche Laborpuffer (Harris 2016, Kap. Puffer; Good et al. 1966 für MES, PIPES, MOPS, HEPES, Tricin, Bicin, CHES)
COMMON_BUFFERS = ("acetic acid", "phosphoric acid", "citric acid", "Tris", "HEPES", "MES", "MOPS", "PIPES", "boric acid",
                  "carbonic acid", "ammonia", "glycine", "formic acid", "imidazole", "bicine", "tricine", "CHES", "CAPS",
                  "succinic acid", "triethanolamine", "diethanolamine")
BUFFER_REFS = ["harris", "good1966", "srd46"]


@lru_cache(maxsize=1)
def _common_keys() -> frozenset:
    from . import substances as S
    out = set()
    for n in COMMON_BUFFERS:
        try:
            k = S.resolve(n)
        except Exception:  # noqa: BLE001
            k = None
        if k:
            out.add(k)
    return frozenset(out)


def buffer_suggestions(pH: float, limit: int = 12) -> list[dict]:
    """Säure-Base-Paare der Sammlung mit pKa im Bereich pH ± 1 (nur kritisch ausgewählte Werte, NIST SRD 46);
    übliche Laborpuffer (COMMON_BUFFERS) zuerst, dann nach Abstand zum Ziel-pH."""
    from . import substances as S
    hits = []
    common = _common_keys()
    for k, s in _all_systems():
        for j, v in s["steps"].items():
            if abs(v["value"] - pH) <= 1:
                m = S.get(k) or {}
                hits.append({"key": k, "name": m.get("de") or m.get("en"), "formula": m.get("formula"), "step": j,
                             "k": max(s["steps"]) - j + 1, "pKa": v["value"], "common": k in common,
                             "T_C": v.get("T_C"), "I": v.get("I"), "d": abs(v["value"] - pH)})
    hits.sort(key=lambda h: (not h["common"], h["d"], h["I"] or 0))
    seen, out = set(), []
    for h in hits:
        if h["key"] in seen:
            continue
        seen.add(h["key"])
        out.append(h)
        if len(out) >= limit:
            break
    return out
