"""Gitterbetrachter: ein Ausschnitt des Kristallgitters eines Werkstoffs bei einer Temperatur, mit gelösten
Fremdatomen, Leerstellen, Gitterschwingung, Verzerrung, Ausscheidungen und schematischen Linien- und Flächenfehlern.

Was berechnet wird und wonach
- Phase bei T: Allotropie des Grundelements (data/gitter.json) oder das Gebiet im zitierten schematischen
  Zustandsdiagramm (phasediag), Anteile nach dem Hebelgesetz (Callister, Kap. 9).
- Gitterparameter a(T) = a(T₀)·[1 + α (T − T₀)] mit dem Ausdehnungskoeffizienten bei 25 °C (crc97) bzw. linear zwischen
  Stützpunkten (basinski1955); bei hohen Temperaturen unterschätzt der konstante Koeffizient die Ausdehnung.
- Platz der Fremdatome: H, B, C, N, O auf Zwischengitterplätzen (Oktaeder- bzw. Tetraederlücke je Gittertyp, porter,
  hirth1980), alle anderen Elemente auf Gitterplätzen (Substitution, Callister Kap. 4); Radien aus dem eigenen Gitter
  (krz r = a√3/4, kfz r = a√2/4, hdp r = a/2), Kovalenzradien nach cordero2008. Grössenunterschied > 15 % wird
  gemeldet (Hume-Rothery-Regel, callister).
- Löslichkeit: aus dem Zustandsdiagramm (Grenze des Einphasengebiets bei T), lückenlose Paare nach massalski1990,
  sonst eine eigene Grenze; der Überschuss bildet die zweite Phase (Hebelgesetz), dargestellt als Kugel oder Lamelle.
- Leerstellen im Gleichgewicht: c_v = exp(S_v/k)·exp(−H_v/kT) (ehrhart1991, porter).
- Gitterschwingung im Debye-Modell: ⟨u_x²⟩ = 3ħ²/(m k θ_D)·[Φ(x)/x + 1/4], x = θ_D/T (willis1975).
- Verzerrung um Fremdatome und Leerstellen: radiale Verschiebung u(r) = δ·(d₁/r)² bis 2·d₁ (eshelby1956), Grösse δ
  aus dem Radienunterschied; schematisch.
- Stufenversetzung: isotropes Verschiebungsfeld nach Volterra (hirth1982) mit dem kürzesten Burgers-Vektor in der
  Gleitebene (kfz a/2⟨110⟩ in {111}, krz a/2⟨111⟩ in {110}, hdp a in der Basisebene); Stapelfehler (kfz: Shockley-
  Teilversetzung a/6⟨112⟩, hdp: a/√3 in der Basisebene); symmetrische Kippkorngrenze. Lage und Grösse schematisch.
Alle Zufallsentscheidungen hängen am Startwert `seed`, das Bild ist damit reproduzierbar.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np

from . import cryst
from . import phasediag as PD

DATA = Path(__file__).resolve().parent / "data"
_SDK_DATA = Path(__file__).resolve().parents[3] / "sdk" / "python" / "labcalc" / "data"

K_EV = 8.617333262e-5          # Boltzmann-Konstante in eV/K (CODATA 2018)
K_J = 1.380649e-23             # J/K (exakt, SI)
HBAR = 1.054571817e-34         # J·s (CODATA 2018)
U_KG = 1.66053906660e-27       # atomare Masseneinheit in kg (CODATA 2018)
T0 = 273.15
MAX_ATOMS = 12000
INTERSTITIAL = ("H", "B", "C", "N", "O")
G_NAMES = {"krz": ("krz", "bcc"), "kfz": ("kfz", "fcc"), "hdp": ("hdp", "hcp")}


class LatticeError(ValueError):
    pass


# ============================================================================ Daten
@lru_cache(maxsize=None)
def _data() -> dict:
    return json.loads((DATA / "gitter.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def _weights() -> dict:
    return json.loads((_SDK_DATA / "atomic_weights.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def _pure() -> dict:
    """Reinmetalle der gemeinsamen Werkstoffdatenbank: Element → (alpha in 1e-6/K, nu, Quelle)."""
    d = json.loads((_SDK_DATA / "materials.json").read_text(encoding="utf-8"))
    out = {}
    for m in d["werkstoffe"]:
        if m.get("familie") == "Reinmetall" and m.get("element"):
            w = m.get("werte") or {}
            out[m["element"]] = {"alpha": (w.get("alpha") or {}).get("v"), "nu": (w.get("nu") or {}).get("v"),
                                 "q": m.get("q") or "crc97", "id": m["id"]}
    return out


def mass(el: str) -> float:
    try:
        return float(_weights()[el]["value"])
    except KeyError:
        raise LatticeError(f"Atommasse für {el} fehlt") from None


def hosts(lang: str = "de") -> list[dict]:
    out = []
    for el, e in _data()["elemente"].items():
        out.append({"el": el, "Tm": e["Tm"], "forms": [{"name": f["name"], "gitter": G_NAMES[f["gitter"]][lang == "en"],
                                                         "bis": f["bis"]} for f in e["formen"]]})
    return out


def solute_list() -> list[str]:
    d = _data()
    subs = list(d["elemente"]) + [k for k in d["radien_zusatz"] if not k.startswith("_")]
    return subs + [k for k in d["zwischengitter"] if not k.startswith("_")]


def examples(lang: str = "de") -> list[dict]:
    return [{**x, "name": x.get("name_en") if lang == "en" else x["name"]} for x in _data()["beispiele"]]


# ============================================================================ Phase und Gitterparameter
def form_at(el: str, T: float) -> dict | None:
    """Kristallform des reinen Elements bei T (°C); None oberhalb der Schmelztemperatur."""
    e = _data()["elemente"].get(el)
    if e is None:
        raise LatticeError(f"Für {el} sind keine Gitterdaten hinterlegt")
    if T > e["Tm"]:
        return None
    for f in e["formen"]:
        if T <= f["bis"]:
            return f
    return e["formen"][-1]


def form_named(el: str, name: str) -> dict:
    for f in _data()["elemente"][el]["formen"]:
        if f["name"] == name:
            return f
    raise LatticeError(f"Form {name} von {el} unbekannt")


def lattice_param(el: str, form: dict, T: float) -> dict:
    """a (und c) in Å bei T in °C mit Quellen und Angabe, wie gerechnet wurde."""
    pure = _pure().get(el) or {}
    alpha = form.get("alpha", pure.get("alpha"))
    refs = list(form.get("q") or [])
    if form.get("phase"):
        cell = cryst.phase(form["phase"])["cell"]
        refs.append("wyckoff1963")
        a0, c0 = float(cell["a"]), (float(cell["c"]) if cell.get("c") else None)
    else:
        a0, c0 = None, None
    pts = form.get("a_punkte") or ([[20.0, a0]] if a0 else None)
    if not pts:
        raise LatticeError(f"Kein Gitterparameter für {form['name']}")
    if alpha is None:
        raise LatticeError(f"Kein Ausdehnungskoeffizient für {el}")
    alpha = float(alpha) * 1e-6
    if pure.get("q") and "alpha" not in form:
        refs.append(pure["q"])
    pts = sorted(pts)
    if len(pts) >= 2 and pts[0][0] <= T <= pts[-1][0]:
        for (t1, v1), (t2, v2) in zip(pts, pts[1:]):
            if t1 <= T <= t2:
                a = v1 + (v2 - v1) * (T - t1) / (t2 - t1)
                how = "interp"
                break
    else:
        t_ref, a_ref = (pts[-1] if T > pts[-1][0] else pts[0])
        a = a_ref * (1 + alpha * (T - t_ref))
        how = "alpha"
    c = None
    if c0 is not None:
        c = c0 * a / a0 if a0 else None   # isotrope Ausdehnung angenommen
    return {"a": a, "c": c, "alpha": alpha, "how": how, "refs": list(dict.fromkeys(refs))}


def metal_radius(el: str) -> tuple[float, str]:
    """Metallradius in Å: aus dem eigenen Gitter bei 20 °C, sonst aus der Zusatztabelle (callister)."""
    d = _data()
    if el in d["elemente"]:
        f = d["elemente"][el]["formen"][0]
        lp = lattice_param(el, f, 20.0)
        g = f["gitter"]
        r = lp["a"] * math.sqrt(3) / 4 if g == "krz" else lp["a"] * math.sqrt(2) / 4 if g == "kfz" else lp["a"] / 2
        return r, "gitter"
    if el in d["radien_zusatz"]:
        return float(d["radien_zusatz"][el]), "callister"
    if el in d["zwischengitter"]:
        return float(d["zwischengitter"][el]), "cordero2008"
    raise LatticeError(f"Kein Radius für {el}")


def nn_distance(g: str, a: float, c: float | None) -> float:
    return a * math.sqrt(3) / 2 if g == "krz" else a / math.sqrt(2) if g == "kfz" else a


def at_fractions(host: str, sols: list[dict]) -> dict[str, float]:
    """Stoffmengenanteile aller Elemente aus Angaben in Gew.-% oder At.-% (Rest: Wirtselement)."""
    wt = [s for s in sols if s.get("einheit", "wt") == "wt"]
    at = [s for s in sols if s.get("einheit") == "at"]
    if wt and at:
        raise LatticeError("Bitte alle Gehalte in derselben Einheit angeben (Gew.-% oder At.-%)")
    tot = sum(float(s["c"]) for s in sols)
    if tot >= 100:
        raise LatticeError("Summe der gelösten Elemente muss unter 100 % liegen")
    if at:
        out = {s["el"]: float(s["c"]) / 100 for s in sols}
        out[host] = 1 - tot / 100
        return out
    n = {s["el"]: float(s["c"]) / mass(s["el"]) for s in sols}
    n[host] = (100 - tot) / mass(host)
    S = sum(n.values())
    return {k: v / S for k, v in n.items()}


def wt_of(host: str, el: str, x_at: float) -> float:
    """Gew.-% von el in einem Zweistoffgemisch mit dem Stoffmengenanteil x_at."""
    mA, mB = mass(host), mass(el)
    return 100 * x_at * mB / (x_at * mB + (1 - x_at) * mA)


def at_of(host: str, el: str, w: float) -> float:
    mA, mB = mass(host), mass(el)
    return (w / mB) / (w / mB + (100 - w) / mA) if w > 0 else 0.0


# ============================================================================ Löslichkeit und Phasenzustand
def _diagram_for(host: str, el: str):
    for s in PD._data()["systeme"]:
        if {s["A"], s["B"]} == {host, el}:
            return s
    return None


def _complete(host: str, el: str) -> bool:
    return any({host, el} == set(p) for p in _data()["vollstaendig"]["paare"])


def phase_state(host: str, sols: list[dict], T: float, own_limits: dict | None = None, lang: str = "de") -> dict:
    """Phasen bei T: [{name, frac (Massenanteil), x (Gew.-% des Diagramm-Elements), el/form oder fluessig}],
    das Diagramm, nach dem gerechnet wurde, und Hinweise."""
    de = lang != "en"
    notes, refs = [], []
    own_limits = own_limits or {}
    form = form_at(host, T)
    base = {"diagram": None, "notes": notes, "refs": refs, "clamped": None}
    # Zustandsdiagramm des ersten passenden Paares (Wechselwirkungen mehrerer Fremdelemente nicht berücksichtigt)
    for s in sols:
        dg = _diagram_for(host, s["el"])
        if dg is None:
            continue
        w = float(s["c"]) if s.get("einheit", "wt") == "wt" else wt_of(host, s["el"], float(s["c"]) / 100)
        x = w if dg["A"] == host else 100 - w
        lo, hi = dg["Tlim"]
        Tc = min(max(T, lo), hi)
        if Tc != T:
            base["clamped"] = Tc
            notes.append((f"{T:g} °C liegt ausserhalb des Diagramms ({lo}–{hi} °C); Phasen und Löslichkeit am Rand "
                          f"bei {Tc:g} °C bestimmt.") if de else
                         (f"{T:g} °C lies outside the diagram ({lo}–{hi} °C); phases and solubility taken at the edge, "
                          f"{Tc:g} °C."))
        x = min(max(x, dg["xlim"][0]), dg["xlim"][1])
        lv = PD.lever(dg, x, Tc + (1e-6 if any(abs(Tc - i["T"]) < 1e-9 for i in dg.get("invariants", [])) else 0), lang)
        mp = _data()["diagramme"].get(dg["id"], {}).get("phasen", {})
        phases = []
        for p in lv["phases"]:
            info = dict(mp.get(p["name"], {"name": p["name"]}))
            # x im Diagramm → Gew.-% des gelösten Elements in dieser Phase
            xs = p["x"] if dg["A"] == host else 100 - p["x"]
            phases.append({"name": info.get("name") or p["name"], "label": p["name"], "frac": p["frac"],
                           "x_wt": xs, "el": info.get("el"), "form": info.get("form"),
                           "fluessig": bool(info.get("fluessig"))})
        refs += list(dg["q"]) if isinstance(dg["q"], list) else [dg["q"]]
        return {**base, "diagram": {"id": dg["id"], "name": dg["name_en"] if not de else dg["name"], "solute": s["el"],
                                    "region": lv["region"], "T": Tc}, "phases": phases}
    # kein Diagramm: reines Element bzw. Mischkristall mit der Form des Wirts
    if form is None:
        return {**base, "phases": [{"name": "Schmelze" if de else "melt", "label": "L", "frac": 1.0, "x_wt": None,
                                    "fluessig": True}]}
    return {**base, "phases": [{"name": form["name"], "label": form["name"], "frac": 1.0, "x_wt": None, "el": host,
                                "form": form["name"], "fluessig": False}]}


def solubility(host: str, el: str, T: float, phase_label: str | None, state: dict, own: dict | None) -> dict:
    """Wie viel von el sich in der Matrix löst: {how, limit_wt (None = unbegrenzt), refs}."""
    own = own or {}
    d = state.get("diagram")
    if d and d["solute"] == el:
        return {"how": "diagramm", "limit_wt": None, "refs": []}     # bereits über das Hebelgesetz aufgeteilt
    if _complete(host, el):
        return {"how": "vollstaendig", "limit_wt": None, "refs": ["massalski1990"]}
    if el in own and own[el] not in (None, ""):
        return {"how": "eigen", "limit_wt": float(own[el]), "refs": []}
    return {"how": "unbekannt", "limit_wt": None, "refs": []}


# ============================================================================ Gittergeometrie
def _cell(g: str, a: float, c: float | None):
    """Gittervektoren (Zeilen) und Basis (Bruchkoordinaten) der konventionellen Zelle."""
    if g == "kfz":
        return a * np.eye(3), np.array([[0, 0, 0], [.5, .5, 0], [.5, 0, .5], [0, .5, .5]], float)
    if g == "krz":
        return a * np.eye(3), np.array([[0, 0, 0], [.5, .5, .5]], float)
    if g == "hdp":
        A = np.array([[a, 0, 0], [-a / 2, a * math.sqrt(3) / 2, 0], [0, 0, c]], float)
        return A, np.array([[0, 0, 0], [2 / 3, 1 / 3, .5]], float)     # Atome auf den Ecken (übliche Zeichnung)
    raise LatticeError(f"Gittertyp {g} nicht unterstützt")


def _holes(g: str, kind: str) -> np.ndarray:
    """Zwischengitterlücken je Zelle in Bruchkoordinaten."""
    q, h, t = .25, .5, .75
    if g == "kfz":
        if kind == "okt":
            return np.array([[h, 0, 0], [0, h, 0], [0, 0, h], [h, h, h]])
        return np.array([[x, y, z] for x in (q, t) for y in (q, t) for z in (q, t)])
    if g == "krz":
        if kind == "okt":
            return np.array([[h, h, 0], [h, 0, h], [0, h, h], [h, 0, 0], [0, h, 0], [0, 0, h]])
        return np.array([[h, q, 0], [h, t, 0], [q, h, 0], [t, h, 0], [h, 0, q], [h, 0, t], [q, 0, h], [t, 0, h],
                         [0, h, q], [0, h, t], [0, q, h], [0, t, h]])
    # hdp mit Atomen auf (0, 0, 0) und (2/3, 1/3, 1/2): Oktaederlücken über den freien C-Plätzen, Tetraederlücken
    # 3c/8 über und unter jedem Atom
    if kind == "okt":
        return np.array([[1 / 3, 2 / 3, q], [1 / 3, 2 / 3, t]])
    return np.array([[0, 0, .375], [0, 0, .625], [2 / 3, 1 / 3, .125], [2 / 3, 1 / 3, .875]])


def frame(g: str, rotated: bool) -> np.ndarray:
    """Zeilen = Achsen x, y, z des Bildes in kartesischen Kristallkoordinaten. Mit Linien-/Flächenfehlern liegt die
    Gleitebene waagrecht (Normale z) und der Burgers-Vektor entlang x."""
    if not rotated or g == "hdp":
        return np.eye(3)
    if g == "kfz":
        R = np.array([[1, -1, 0], [1, 1, -2], [1, 1, 1]], float)
    else:
        R = np.array([[1, 1, 1], [1, 1, -2], [-1, 1, 0]], float)
    return R / np.linalg.norm(R, axis=1)[:, None]


def _rot_y(phi: float) -> np.ndarray:
    c, s = math.cos(phi), math.sin(phi)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def _points(A: np.ndarray, frac: np.ndarray, R: np.ndarray, L: np.ndarray, center: np.ndarray, extra=None):
    """Alle Punkte frac + (i,j,k) der Zelle A, gedreht in das Bild R, die im Kasten [0, L) liegen.
    `extra` (3×3) dreht zusätzlich um die Kastenmitte (Korngrenze)."""
    M = R if extra is None else extra @ R
    corners = np.array([[x, y, z] for x in (0, 1) for y in (0, 1) for z in (0, 1)], float) * L - center
    cryst_c = corners @ M                      # Bild → kartesisch (M orthogonal)
    fracs = cryst_c @ np.linalg.inv(A)
    lo = np.floor(fracs.min(0)) - 1
    hi = np.ceil(fracs.max(0)) + 1
    ii = np.arange(lo[0], hi[0] + 1)
    jj = np.arange(lo[1], hi[1] + 1)
    kk = np.arange(lo[2], hi[2] + 1)
    grid = np.stack(np.meshgrid(ii, jj, kk, indexing="ij"), -1).reshape(-1, 3)
    pts = (grid[:, None, :] + frac[None, :, :]).reshape(-1, 3) @ A
    P = pts @ M.T + center
    eps = 1e-6
    keep = np.all((P >= -eps) & (P < L - eps), axis=1)
    return P[keep]


# ============================================================================ Physik
def debye_u2(m_u: float, theta: float, T_K: float) -> float:
    """⟨u_x²⟩ in Å² im Debye-Modell (willis1975)."""
    x = theta / max(T_K, 1e-6)
    if x < 1e-6:
        phi = 1.0
    else:
        t = np.linspace(1e-9, x, 2001)
        f = t / np.expm1(t)
        phi = float(np.sum((f[1:] + f[:-1]) * np.diff(t)) / 2) / x   # Trapezregel (np.trapz fehlt in numpy ≥ 2)
    u2 = 3 * HBAR ** 2 / (m_u * U_KG * K_J * theta) * (phi / max(x, 1e-12) + 0.25)
    return u2 * 1e20


def vacancy_fraction(Hv: float, Sv: float, T_K: float) -> float:
    return math.exp(Sv) * math.exp(-Hv / (K_EV * T_K)) if T_K > 0 else 0.0


def edge_field(dx: np.ndarray, dz: np.ndarray, b: float, nu: float) -> tuple[np.ndarray, np.ndarray]:
    """Verschiebung (u_x, u_z) der Stufenversetzung, Linie entlang y, Gleitebene z = 0 (hirth1982, Gl. 3-45)."""
    r2 = dx ** 2 + dz ** 2 + 1e-12
    ux = b / (2 * math.pi) * (np.arctan2(dz, dx) + dx * dz / (2 * (1 - nu) * r2))
    uz = -b / (2 * math.pi) * ((1 - 2 * nu) / (4 * (1 - nu)) * np.log(r2 / b ** 2) + (dx ** 2 - dz ** 2) / (4 * (1 - nu) * r2))
    return ux, uz


# ============================================================================ Aufbau
DEFAULT_FX = {"vac": True, "vib": True, "distort": True, "precip": True, "disl": False, "sf": False, "gb": False}


def build(req: dict, lang: str = "de") -> dict:
    de = lang != "en"
    d = _data()
    host = str(req.get("host") or "Fe")
    if host not in d["elemente"]:
        raise LatticeError(f"Grundelement {host} nicht hinterlegt")
    T = float(req.get("T", 20))
    if not (-273.15 < T < 4000):
        raise LatticeError("Temperatur zwischen −273 °C und 4000 °C angeben")
    T_K = T + T0
    n = int(req.get("n", 6))
    if not 2 <= n <= 14:
        raise LatticeError("Zellen je Kante zwischen 2 und 14")
    seed = int(req.get("seed", 1))
    fx = {**DEFAULT_FX, **{k: bool(v) for k, v in (req.get("fx") or {}).items() if k in DEFAULT_FX}}
    boost = float(req.get("boost", 1) or 1)
    vib_boost = float(req.get("vib_boost", 1) or 1)
    if not (1 <= boost <= 1e8 and 1 <= vib_boost <= 10):
        raise LatticeError("Überhöhung: Leerstellen 1 bis 10⁸, Schwingung 1 bis 10")
    Sv = float(req.get("Sv", d["Sv_k"]))
    gb_deg = float(req.get("gb_angle", 16))
    own = req.get("limits") or {}
    sols = []
    for s in (req.get("solutes") or [])[:4]:
        el = str(s.get("el") or "")
        if not el:
            continue
        if el == host:
            raise LatticeError("Ein gelöstes Element darf nicht das Grundelement sein")
        if el not in solute_list():
            raise LatticeError(f"Für {el} ist kein Radius hinterlegt")
        try:
            c = float(s.get("c"))
        except (TypeError, ValueError):
            raise LatticeError(f"Gehalt von {el} ist keine Zahl") from None
        if c < 0:
            raise LatticeError(f"Gehalt von {el} negativ")
        if c > 0:
            sols.append({"el": el, "c": c, "einheit": "at" if s.get("einheit") == "at" else "wt"})
    rng = np.random.default_rng(seed)
    notes: list[str] = []
    refs = ["callister"]

    # ---------------------------------------------------------------- Phasen
    st = phase_state(host, sols, T, own, lang)
    notes += st["notes"]
    refs += st["refs"]
    phases = st["phases"]
    # Matrix = Phase auf dem Gitter des Grundelements, sonst die mit dem grössten Anteil
    mi = next((i for i, p in enumerate(phases) if p.get("el") == host), None)
    if mi is None:
        mi = max(range(len(phases)), key=lambda i: phases[i]["frac"])
    matrix = phases[mi]
    second = [p for i, p in enumerate(phases) if i != mi]
    liquid = matrix.get("fluessig", False)
    x_all = at_fractions(host, sols) if sols else {host: 1.0}
    e_host = d["elemente"][host]

    if liquid:
        form = form_at(host, min(T, e_host["Tm"])) or e_host["formen"][-1]
        lp = lattice_param(host, form, e_host["Tm"])
        g = form["gitter"]
    else:
        form = form_named(matrix["el"], matrix["form"]) if matrix.get("form") else form_at(host, T)
        g = form["gitter"]
        lp = lattice_param(host, form, T)
    refs += lp["refs"]
    a, c = lp["a"], lp["c"]
    dnn = nn_distance(g, a, c)
    r_host = metal_radius(host)[0]

    rotated = (fx["disl"] or fx["sf"] or fx["gb"]) and not liquid
    R = frame(g, rotated)
    A, frac = _cell(g, a, c)
    if g == "hdp":
        L = np.array([n * a, n * a * math.sqrt(3) / 2, max(2, round(n * a / c)) * c])
    else:
        L = np.array([n * a] * 3)
    center = L / 2
    hole_kind = {}
    for s in sols:
        if s["el"] in INTERSTITIAL:
            hole_kind[s["el"]] = d["platz"][g][s["el"]]

    # ---------------------------------------------------------------- Gitter (ggf. zwei Körner)
    gb_rot = None
    if fx["gb"] and not liquid:
        phi = math.radians(gb_deg) / 2
        up = _points(A, frac, R, L, center, _rot_y(phi))
        lo_ = _points(A, frac, R, L, center, _rot_y(-phi))
        up = up[up[:, 2] >= center[2]]
        lo_ = lo_[lo_[:, 2] < center[2]]
        near_up = up[:, 2] < center[2] + dnn
        near_lo = lo_[:, 2] > center[2] - dnn
        drop = np.zeros(len(up), bool)
        if near_up.any() and near_lo.any():
            U, Lw = up[near_up], lo_[near_lo]
            dist = np.sqrt(((U[:, None, :] - Lw[None, :, :]) ** 2).sum(-1)).min(1)
            idx = np.where(near_up)[0]
            drop[idx[dist < 0.7 * dnn]] = True
        P = np.vstack([lo_, up[~drop]])
        grain = np.r_[np.zeros(len(lo_), int), np.ones(int((~drop).sum()), int)]
        gb_rot = gb_deg
        holes = {}
        for el, kind in hole_kind.items():
            hu = _points(A, _holes(g, kind), R, L, center, _rot_y(phi))
            hl = _points(A, _holes(g, kind), R, L, center, _rot_y(-phi))
            holes[el] = np.vstack([hl[hl[:, 2] < center[2] - 0.3 * dnn], hu[hu[:, 2] > center[2] + 0.3 * dnn]])
        refs.append("hirth1982")
    else:
        P = _points(A, frac, R, L, center)
        grain = np.zeros(len(P), int)
        holes = {el: _points(A, _holes(g, kind), R, L, center) for el, kind in hole_kind.items()}
    if len(P) > MAX_ATOMS:
        raise LatticeError(f"Zu viele Atome ({len(P)}); weniger Zellen je Kante wählen")
    # Elementarzelle (im unteren Korn, abseits von Versetzungskern und Korngrenze); folgt Stapelfehler und Versetzung
    M_cell = (_rot_y(-math.radians(gb_deg) / 2) @ R) if gb_rot else R
    cell_c = None if liquid else _unit_cell(A, M_cell, L, center, 0.22 * L)
    N = len(P)
    role = np.array(["host"] * N, dtype=object)
    elem = np.array([host] * N, dtype=object)

    # ---------------------------------------------------------------- Stapelfehler
    sf_info = None
    if fx["sf"] and not liquid:
        if g == "krz":
            notes.append("Stapelfehler im krz-Gitter nicht dargestellt (keine dichtgepackte Stapelfolge)." if de else
                         "No stacking fault in the bcc lattice (no close-packed stacking sequence).")
        elif fx["gb"]:
            notes.append("Stapelfehler nur ohne Korngrenze dargestellt." if de else
                         "Stacking fault shown only without a grain boundary.")
        else:
            zs = np.unique(np.round(P[:, 2], 3))
            z0 = float(zs[np.argmin(np.abs(zs - (0.68 * L[2] if fx["disl"] else center[2])))]) - 1e-3
            # erste Ebene über z0 auf einen Platz schieben, der nicht über der Ebene darunter liegt
            if g == "kfz":
                cands = [np.array([0, a / math.sqrt(6), 0]), np.array([0, -a / math.sqrt(6), 0])]
            else:
                cands = [np.array([a / 2, -a / (2 * math.sqrt(3)), 0]), np.array([-a / 2, a / (2 * math.sqrt(3)), 0])]
            above = P[:, 2] > z0
            zb = P[~above, 2].max() if (~above).any() else None
            za = P[above, 2].min() if above.any() else None
            best = cands[0]
            if zb is not None and za is not None:
                below_l = P[np.abs(P[:, 2] - zb) < 1e-3][:, :2]
                above_l = P[np.abs(P[:, 2] - za) < 1e-3][:, :2]
                scores = []
                for s in cands:
                    q = above_l + s[:2]
                    m = np.sqrt(((q[:, None, :] - below_l[None, :, :]) ** 2).sum(-1)).min()
                    scores.append(m)
                best = cands[int(np.argmax(scores))]
            P[above] += best
            if cell_c is not None:
                cell_c[cell_c[:, 2] > z0] += best
            # in den Kasten zurückfalten (x, y periodisch)
            P[:, :2] = np.mod(P[:, :2], L[:2])
            for el in holes:
                ha = holes[el][:, 2] > z0
                holes[el][ha] += best
                holes[el][:, :2] = np.mod(holes[el][:, :2], L[:2])
            sf_info = {"z": z0, "shift": float(np.linalg.norm(best)), "kind": "shockley" if g == "kfz" else "basal"}
            refs.append("hirth1982")

    # ---------------------------------------------------------------- Schmelze
    if liquid:
        P = _liquid(N, L, 0.86 * dnn, rng)
        N = len(P)
        role = np.array(["liq"] * N, dtype=object)
        elem = np.array([host] * N, dtype=object)
        grain = np.zeros(N, int)
        holes = {}
        notes.append(("Schmelze: Atome ohne Fernordnung zufällig verteilt (Mindestabstand 0,86·d₁, Dichte wie im "
                      "Festkörper); schematisch.") if de else
                     ("Melt: atoms without long-range order, placed at random (minimum spacing 0.86·d₁, solid "
                      "density); schematic."))

    # ---------------------------------------------------------------- zweite Phase
    stats_second = []
    region = np.zeros(N, bool)
    if second and fx["precip"]:
        # Massenanteile → Anteil der Atome (über die mittlere Molmasse der Phasen)
        def mean_m(p):
            sol = st["diagram"]["solute"] if st.get("diagram") else None
            if not sol or p.get("x_wt") is None:
                return mass(host)
            x = at_of(host, sol, p["x_wt"])
            return x * mass(sol) + (1 - x) * mass(host)
        tot = sum(p["frac"] / mean_m(p) for p in phases)
        geom_used = []
        for p in second:
            f_at = (p["frac"] / mean_m(p)) / tot
            if f_at <= 0:
                continue
            k = int(round(f_at * N))
            if k < 1:
                stats_second.append({**p, "f_at": f_at, "atoms": 0})
                continue
            sel, geom = _region(P, L, k, f_at, rng, ~region)
            region |= sel
            geom_used.append(geom)
            sol = st["diagram"]["solute"]
            x2 = at_of(host, sol, p["x_wt"]) if p.get("x_wt") is not None else 1.0
            idx = np.where(sel)[0]
            if p.get("fluessig"):
                role[idx] = "liq2"
                P[idx] = _jiggle_liquid(P[idx], 0.18 * dnn, rng)
            elif p.get("el") and p.get("form"):
                # zweite Kristallphase mit eigenem Gitter in ihrem Bereich neu aufbauen
                f2 = form_named(p["el"], p["form"])
                lp2 = lattice_param(p["el"], f2, T)
                A2, fr2 = _cell(f2["gitter"], lp2["a"], lp2["c"])
                P2 = _points(A2, fr2, frame(f2["gitter"], False), L, center)
                inside = _in_geom(P2, geom)
                P2 = P2[inside]
                keep = np.ones(N, bool)
                keep[idx] = False
                P, role, elem, grain, region = P[keep], role[keep], elem[keep], grain[keep], region[keep]
                P = np.vstack([P, P2])
                role = np.r_[role, np.array(["host2"] * len(P2), dtype=object)]
                elem = np.r_[elem, np.array([p["el"]] * len(P2), dtype=object)]
                grain = np.r_[grain, np.zeros(len(P2), int)]
                region = np.r_[region, np.ones(len(P2), bool)]
                N = len(P)
                if p["el"] != host:
                    pass
                # gelöster Anteil des Fremdelements in der zweiten Phase (substitutionell)
                if sol not in INTERSTITIAL and p["el"] != sol:
                    nsub = int(round(x2 * len(P2)))
                    cand = np.where(role == "host2")[0]
                    pick = rng.choice(cand, size=min(nsub, len(cand)), replace=False) if nsub else []
                    role[pick] = f"sub2:{sol}"
                    elem[pick] = sol
                refs += lp2["refs"]
                stats_second.append({**p, "f_at": f_at, "atoms": int(len(P2)), "geom": geom["kind"]})
                continue
            else:
                # Ausscheidung ohne eigene Struktur: Zusammensetzung auf den Plätzen des Wirtsgitters (schematisch)
                if sol in INTERSTITIAL:
                    role[idx] = "prec"
                    hs = holes.get(sol)
                    nint = int(round(x2 / max(1 - x2, 1e-9) * len(idx)))
                    if hs is not None and len(hs):
                        hin = np.where(_in_geom(hs, geom))[0]
                        pick = rng.choice(hin, size=min(nint, len(hin)), replace=False) if nint and len(hin) else []
                        if len(pick):
                            P = np.vstack([P, hs[pick]])
                            role = np.r_[role, np.array([f"precint:{sol}"] * len(pick), dtype=object)]
                            elem = np.r_[elem, np.array([sol] * len(pick), dtype=object)]
                            grain = np.r_[grain, np.zeros(len(pick), int)]
                            region = np.r_[region, np.ones(len(pick), bool)]
                            holes[sol] = np.delete(hs, pick, axis=0)
                            N = len(P)
                else:
                    pick = rng.choice(idx, size=int(round(x2 * len(idx))), replace=False)
                    role[idx] = "prec"
                    role[pick] = f"precsub:{sol}"
                    elem[pick] = sol
            stats_second.append({**p, "f_at": f_at, "atoms": int(sel.sum()), "geom": geom["kind"]})
        if geom_used:
            notes.append(("Zweite Phase nach dem Hebelgesetz als Kugel bzw. Lamelle im Ausschnitt; Form, Lage und Grösse "
                          "schematisch, nicht die wirkliche Gefügeausbildung.") if de else
                         ("Second phase by the lever rule as a sphere or lamella in the cell; shape, position and size "
                          "are schematic, not the real microstructure."))
    elif second and not fx["precip"]:
        notes.append("Zweite Phase ausgeblendet: der Überschuss ist als übersättigter Mischkristall gezeichnet." if de else
                     "Second phase hidden: the excess is drawn as a supersaturated solid solution.")

    matrix_idx = np.where((role == "host") | (role == "liq"))[0]
    n_sites = len(matrix_idx)

    # ---------------------------------------------------------------- gelöste Fremdatome in der Matrix
    sol_stats = []
    for s in sols:
        el = s["el"]
        sol_info = solubility(host, el, T, matrix.get("label"), st, own)
        refs += sol_info["refs"]
        x_tot = x_all.get(el, 0.0)
        w_tot = s["c"] if s["einheit"] == "wt" else wt_of(host, el, s["c"] / 100)
        if st.get("diagram") and st["diagram"]["solute"] == el and matrix.get("x_wt") is not None and fx["precip"]:
            w_m = min(matrix["x_wt"], w_tot) if len(phases) > 1 else w_tot
        elif sol_info["limit_wt"] is not None:
            w_m = min(w_tot, sol_info["limit_wt"])
        else:
            w_m = w_tot
        x_m = at_of(host, el, w_m) if s["einheit"] == "wt" or True else x_tot
        r_s, r_src = metal_radius(el)
        inter = el in INTERSTITIAL
        misfit = (r_s - r_host) / r_host
        info = {"el": el, "c": s["c"], "einheit": s["einheit"], "x_at": x_tot, "w_tot": w_tot, "w_matrix": w_m,
                "how": sol_info["how"], "r": r_s, "r_src": r_src, "site": hole_kind.get(el) if inter else "sub",
                "misfit": misfit, "ratio": r_s / r_host}
        if inter:
            hs = holes.get(el)
            if hs is None or not len(hs):
                info["placed"] = 0
                sol_stats.append(info)
                continue
            # Lücken in der Matrix (nicht in der zweiten Phase)
            ok = ~_near_region(hs, P[region], 0.6 * dnn) if region.any() else np.ones(len(hs), bool)
            cand = np.where(ok)[0]
            n_exp = x_m / max(1 - x_m, 1e-12) * n_sites
            k = _round_stoch(n_exp, rng)
            pick = rng.choice(cand, size=min(k, len(cand)), replace=False) if k and len(cand) else []
            if len(pick):
                P = np.vstack([P, hs[pick]])
                role = np.r_[role, np.array([f"int:{el}"] * len(pick), dtype=object)]
                elem = np.r_[elem, np.array([el] * len(pick), dtype=object)]
                grain = np.r_[grain, np.zeros(len(pick), int)]
                region = np.r_[region, np.zeros(len(pick), bool)]
                holes[el] = np.delete(hs, pick, axis=0)
            info.update({"expected": n_exp, "placed": int(len(pick)),
                         "hole_ratio": {"kfz": {"okt": 0.414, "tet": 0.225}, "krz": {"okt": 0.155, "tet": 0.291},
                                        "hdp": {"okt": 0.414, "tet": 0.225}}[g][hole_kind[el]]})
            refs += ["cordero2008", "porter"] + (["hirth1980"] if el == "H" and g == "krz" else [])
        else:
            matrix_idx = np.where((role == "host") | (role == "liq"))[0]
            n_exp = x_m * n_sites
            k = _round_stoch(n_exp, rng)
            pick = rng.choice(matrix_idx, size=min(k, len(matrix_idx)), replace=False) if k else []
            role[pick] = f"sub:{el}"
            elem[pick] = el
            info.update({"expected": n_exp, "placed": int(len(pick))})
            if abs(misfit) > 0.15:
                notes.append((f"{el}: Radius weicht um {misfit * 100:+.0f} % vom Wirt ab (> 15 %): nach Hume-Rothery nur "
                              f"geringe Löslichkeit zu erwarten.") if de else
                             (f"{el}: radius differs by {misfit * 100:+.0f} % from the host (> 15 %): by Hume-Rothery only "
                              f"limited solubility is expected."))
        if sol_info["how"] == "unbekannt" and not (st.get("diagram") and st["diagram"]["solute"] == el):
            notes.append((f"Löslichkeit von {el} in {host} nicht hinterlegt: vollständig gelöst gezeichnet. Eine eigene "
                          f"Grenze (Gew.-%) mit Quelle eintragen, um den Überschuss als Ausscheidung zu zeigen.") if de else
                         (f"Solubility of {el} in {host} not available: drawn fully dissolved. Enter a limit (wt%) with a "
                          f"source to show the excess as a precipitate."))
        if sol_info["how"] == "eigen" and w_tot > w_m and fx["precip"]:
            # Überschuss über der eigenen Grenze: Ausscheidung aus reinem Fremdelement (schematisch)
            x_ex = at_of(host, el, w_tot) - at_of(host, el, w_m)
            k_ex = int(round(x_ex * N))
            if k_ex > 0 and not inter:
                sel, geom = _region(P, L, k_ex, x_ex, rng, (role == "host"))
                idx = np.where(sel)[0]
                role[idx] = f"precsub:{el}"
                elem[idx] = el
                region |= sel
                info["excess_atoms"] = int(len(idx))
        sol_stats.append(info)

    # ---------------------------------------------------------------- Leerstellen
    vac = {"c": 0.0, "expected": 0.0, "placed": 0}
    vac_pos = np.zeros((0, 3))
    if fx["vac"] and not liquid:
        cv = vacancy_fraction(e_host["Hv"], Sv, T_K)
        cand = np.where((role == "host") | (role == "host2"))[0]
        n_exp = cv * len(cand)
        k = _round_stoch(n_exp * boost, rng)
        pick = rng.choice(cand, size=min(k, len(cand)), replace=False) if k else np.array([], int)
        vac_pos = P[pick].copy()
        keep = np.ones(len(P), bool)
        keep[pick] = False
        P, role, elem, grain, region = P[keep], role[keep], elem[keep], grain[keep], region[keep]
        vac = {"c": cv, "expected": n_exp, "shown_expected": n_exp * boost, "placed": int(len(pick)),
               "Hv": e_host["Hv"], "Sv": Sv, "sites": int(len(cand))}
        refs += ["ehrhart1991", "porter"]

    # ---------------------------------------------------------------- Verzerrung (schematisch)
    if fx["distort"] and not liquid:
        disp = np.zeros_like(P)
        cut = 2.0 * dnn
        src = []                                    # (Ort, δ in Å)
        for i in np.where([str(x).startswith("sub:") for x in role])[0]:
            src.append((P[i], metal_radius(elem[i])[0] - r_host, i))
        for i in np.where([str(x).startswith("int:") for x in role])[0]:
            others = np.where((role != role[i]) & ~np.array([str(x).startswith("int:") for x in role]))[0]
            dd = np.sqrt(((P[others] - P[i]) ** 2).sum(1))
            near = dd.min() if len(dd) else dnn
            src.append((P[i], 0.5 * max(metal_radius(elem[i])[0] + r_host - near, 0.0), i))
        for v in vac_pos:
            src.append((v, -0.02 * dnn, -1))
        for pos, delta, i in src:
            if abs(delta) < 1e-6:
                continue
            dv = P - pos
            r = np.sqrt((dv ** 2).sum(1))
            m = (r > 1e-6) & (r <= cut)
            if i >= 0:
                m[i] = False
            u = delta * (dnn / r[m]) ** 2
            disp[m] += dv[m] / r[m, None] * u[:, None]
        P = P + disp
        refs.append("eshelby1956")

    # ---------------------------------------------------------------- Stufenversetzung
    disl_info = None
    if fx["disl"] and not liquid:
        pure = _pure().get(host) or {}
        nu = float(pure.get("nu") or 0.3)
        b = {"kfz": a / math.sqrt(2), "krz": a * math.sqrt(3) / 2, "hdp": a}[g]
        zc = 0.3 * L[2] if fx["gb"] else center[2]
        zs = np.unique(np.round(P[:, 2], 2))
        if len(zs) > 1:
            j = np.argmin(np.abs(zs - zc))
            nb = zs[j + 1] if j + 1 < len(zs) else zs[j - 1]
            zc = 0.5 * (zs[j] + nb)
        xc = center[0] + 0.25 * b
        ux, uz = edge_field(P[:, 0] - xc, P[:, 2] - zc, b, nu)
        P[:, 0] += ux
        P[:, 2] += uz
        if len(vac_pos):
            vx, vz = edge_field(vac_pos[:, 0] - xc, vac_pos[:, 2] - zc, b, nu)
            vac_pos[:, 0] += vx
            vac_pos[:, 2] += vz
        if cell_c is not None:
            cx_, cz_ = edge_field(cell_c[:, 0] - xc, cell_c[:, 2] - zc, b, nu)
            cell_c[:, 0] += cx_
            cell_c[:, 2] += cz_
        disl_info = {"b": b, "nu": nu, "core": [float(xc), float(center[1]), float(zc)],
                     "burgers": {"kfz": "a/2⟨110⟩", "krz": "a/2⟨111⟩", "hdp": "a⟨112̄0⟩/3"}[g],
                     "plane": {"kfz": "{111}", "krz": "{110}", "hdp": "(0001)"}[g]}
        refs += ["hirth1982"] + ([pure["q"]] if pure.get("q") else [])

    # ---------------------------------------------------------------- Gitterschwingung
    u2 = debye_u2(mass(host), e_host["theta_D"], T_K) if not liquid else None
    if fx["vib"] and not liquid:
        sig = math.sqrt(u2) * vib_boost
        P = P + rng.normal(0, sig, P.shape)
        refs.append("willis1975")

    # ---------------------------------------------------------------- Ergebnis
    kinds, codes = _kinds(role, elem, host, de)
    code_of = {k["id"]: i for i, k in enumerate(kinds)}
    atoms = [[round(float(p[0]), 3), round(float(p[1]), 3), round(float(p[2]), 3), code_of[cd]] for p, cd in zip(P, codes)]
    cellbox = {"corners": cell_c.round(3).tolist(), "edges": CELL_EDGES} if cell_c is not None else None
    refs += ["kittel", "crc97"]
    out = {
        "host": host, "T": T, "lang": lang, "liquid": liquid,
        "phase": {"name": matrix["name"], "gitter": G_NAMES[g][not de], "gitter_id": g,
                  "region": st["diagram"]["region"] if st.get("diagram") else None,
                  "diagram": st["diagram"], "phases": [{k: p.get(k) for k in ("name", "label", "frac", "x_wt",
                                                                                 "fluessig")} for p in phases]},
        "lattice": {"a": a, "c": c, "how": lp["how"], "alpha": lp["alpha"], "dnn": dnn, "r_host": r_host},
        "box": [float(x) for x in L], "frame": R.round(6).tolist(), "rotated": bool(rotated),
        "atoms": atoms, "kinds": kinds, "vacancies": [[round(float(v[0]), 3), round(float(v[1]), 3),
                                                       round(float(v[2]), 3)] for v in vac_pos],
        "cell": cellbox, "solutes": sol_stats, "second": [{k: v for k, v in s.items() if k != "geom_obj"}
                                                           for s in stats_second],
        "vac": vac, "u2": u2, "sigma": math.sqrt(u2) if u2 else None, "vib_boost": vib_boost, "boost": boost,
        "theta_D": e_host["theta_D"], "Tm": e_host["Tm"],
        "disl": disl_info, "sf": sf_info, "gb": ({"angle": gb_rot} if gb_rot else None),
        "fx": fx, "seed": seed, "n": n, "notes": notes, "refs": list(dict.fromkeys(refs)),
        "count": len(atoms),
    }
    return out


def _round_stoch(x: float, rng) -> int:
    f = math.floor(x)
    return int(f + (1 if rng.random() < x - f else 0))


def _liquid(n_target: int, L: np.ndarray, dmin: float, rng) -> np.ndarray:
    """Zufällige dichte Anordnung (sequentielles Einfügen mit Mindestabstand) auf einem Hilfsgitter."""
    pts = []
    cell = dmin
    grid: dict = {}
    tries = 0
    while len(pts) < n_target and tries < n_target * 60:
        tries += 1
        p = rng.random(3) * L
        key = tuple((p // cell).astype(int))
        ok = True
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for q in grid.get((key[0] + dx, key[1] + dy, key[2] + dz), ()):
                        if ((p - q) ** 2).sum() < dmin * dmin:
                            ok = False
                            break
                    if not ok:
                        break
                if not ok:
                    break
            if not ok:
                break
        if ok:
            pts.append(p)
            grid.setdefault(key, []).append(p)
    return np.array(pts) if pts else np.zeros((0, 3))


def _jiggle_liquid(P: np.ndarray, s: float, rng) -> np.ndarray:
    return P + rng.normal(0, s, P.shape)


def _region(P: np.ndarray, L: np.ndarray, k: int, f: float, rng, allowed: np.ndarray):
    """k Atome als Kugel (Anteil ≤ 0,25) oder Lamelle (darüber) auswählen."""
    idx = np.where(allowed)[0]
    k = min(k, len(idx))
    if f <= 0.25:
        c0 = L * (0.5 + (rng.random(3) - 0.5) * 0.2)
        d = np.sqrt(((P[idx] - c0) ** 2).sum(1))
        order = idx[np.argsort(d)][:k]
        rad = float(np.sort(d)[k - 1]) if k else 0.0
        sel = np.zeros(len(P), bool)
        sel[order] = True
        return sel, {"kind": "kugel", "c": c0.tolist(), "r": rad}
    order = idx[np.argsort(P[idx, 0])][:k]
    xmax = float(P[order, 0].max()) if k else 0.0
    sel = np.zeros(len(P), bool)
    sel[order] = True
    return sel, {"kind": "lamelle", "x": xmax}


def _in_geom(Q: np.ndarray, geom: dict) -> np.ndarray:
    if geom["kind"] == "kugel":
        return np.sqrt(((Q - np.array(geom["c"])) ** 2).sum(1)) <= geom["r"] + 1e-6
    return Q[:, 0] <= geom["x"] + 1e-6


def _near_region(Q: np.ndarray, R_pts: np.ndarray, dmax: float) -> np.ndarray:
    if not len(R_pts) or not len(Q):
        return np.zeros(len(Q), bool)
    out = np.zeros(len(Q), bool)
    for i in range(0, len(Q), 512):
        q = Q[i:i + 512]
        out[i:i + 512] = np.sqrt(((q[:, None, :] - R_pts[None, :, :]) ** 2).sum(-1)).min(1) < dmax
    return out


PALETTE = {"host": "#9aa5b1", "host2": "#7c8fd6", "liq": "#b9a28a", "liq2": "#c9b08f", "prec": "#d18a5a"}
EL_COL = {"C": "#2b2b2b", "N": "#3f6fd8", "O": "#d8423f", "H": "#f2f2f2", "B": "#e8a33c",
          "Ni": "#3fa36b", "Cu": "#c8763a", "Zn": "#7d7dbd", "Si": "#e0b84a", "Sn": "#8a9a5b", "Cr": "#6f7fa8",
          "Mo": "#5b8f8f", "Mn": "#a35d8f", "Ag": "#c9cdd2", "Au": "#e3b437", "Al": "#b5c3d1", "Fe": "#8d6e63",
          "Pb": "#57606f", "V": "#8f6db0", "W": "#4b6584", "Ti": "#95a5a6", "Mg": "#9fd29f", "Co": "#3a7dc8",
          "Nb": "#73a5a5", "Pt": "#d0d0e0", "Ta": "#7b8fa1", "Cd": "#c7a0c0"}


def _kinds(role, elem, host, de):
    names = {"host": "{el} (Matrix)" if de else "{el} (matrix)", "host2": "{el} (zweite Phase)" if de else "{el} (second phase)",
             "liq": "{el} (Schmelze)" if de else "{el} (melt)", "liq2": "{el} (Schmelze)" if de else "{el} (melt)",
             "prec": "{el} in der Ausscheidung" if de else "{el} in the precipitate",
             "sub": "{el} substitutionell" if de else "{el} substitutional",
             "sub2": "{el} gelöst in der zweiten Phase" if de else "{el} dissolved in the second phase",
             "int": "{el} auf Zwischengitterplatz" if de else "{el} interstitial",
             "precsub": "{el} (Ausscheidung)" if de else "{el} (precipitate)",
             "precint": "{el} (Ausscheidung)" if de else "{el} (precipitate)"}
    kinds, codes, seen = [], [], {}
    for r, e in zip(role, elem):
        base = str(r).split(":")[0]
        cid = f"{base}:{e}"
        codes.append(cid)
        if cid in seen:
            continue
        seen[cid] = True
        col = PALETTE.get(base) if base in ("host", "host2", "liq", "liq2", "prec") and e == host else EL_COL.get(e, "#888")
        if base == "host2" and e != host:
            col = EL_COL.get(e, PALETTE["host2"])
        r_ = metal_radius(e)[0]
        kinds.append({"id": cid, "role": base, "el": e, "name": names[base].format(el=e), "color": col,
                      "r": round(r_, 3)})
    return kinds, codes


_CELL_FR = np.array([[x, y, z] for x in (0, 1) for y in (0, 1) for z in (0, 1)], float)
CELL_EDGES = [[i, j] for i in range(8) for j in range(i + 1, 8) if np.abs(_CELL_FR[i] - _CELL_FR[j]).sum() == 1]


def _unit_cell(A, M, L, center, at):
    """Ecken der konventionellen Zelle auf Gitterpunkten nahe dem Punkt `at` (Bild), mit der Drehung M wie in _points.
    Liegt abseits von Versetzungskern und Korngrenze und folgt deren Verschiebungen wie die Atome."""
    f0 = np.floor(((np.asarray(at) - center) @ M) @ np.linalg.inv(A))
    return ((_CELL_FR + f0) @ A) @ M.T + center
