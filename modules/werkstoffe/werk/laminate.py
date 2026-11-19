"""Klassische Laminattheorie (CLT) für ebene Laminate aus unidirektionalen Schichten (Daniel & Ishai, Kap. 7–8;
Jones, Kap. 4).

Schicht: E1, E2, G12 [GPa], ν12, Festigkeiten Xt, Xc, Yt, Yc, S12 [MPa] (Druckfestigkeiten als positive Zahlen),
Dicke t [mm], Winkel θ [Grad] gegen die x-Achse. Lasten: N = (Nx, Ny, Nxy) [N/mm], M = (Mx, My, Mxy) [N·mm/mm].

    Q11 = E1/(1−ν12ν21), Q22 = E2/(1−ν12ν21), Q12 = ν12 E2/(1−ν12ν21), Q66 = G12;  Q̄ = T⁻¹ Q R T R⁻¹
    A = Σ Q̄ (z_k − z_{k−1}),  B = ½ Σ Q̄ (z_k² − z_{k−1}²),  D = ⅓ Σ Q̄ (z_k³ − z_{k−1}³)
    [ε⁰; κ] = [A B; B D]⁻¹ [N; M],  ε(z) = ε⁰ + z κ

Versagenskriterien je Schicht im Schichtsystem (1, 2), Reservefaktor R = Lastfaktor bis zum Versagen:
- Maximalspannung: R = min(X/σ1, Y/σ2, S/|τ12|) mit X, Y je nach Vorzeichen
- Tsai–Hill (Azzi & Tsai 1965): (σ1/X)² − σ1σ2/X² + (σ2/Y)² + (τ12/S)² = 1/R²
- Tsai–Wu (Tsai & Wu 1971): F1σ1 + F2σ2 + F11σ1² + F22σ2² + F66τ12² + 2F12σ1σ2 = 1, F12 = −½√(F11F22) (Vorgabe)
- Hashin (1980), ebener Fall: Faser Zug/Druck, Matrix Zug/Druck (S_T = Yc/2 als Vorgabe)
"""
from __future__ import annotations

import math
import re

import numpy as np

REFS = {"clt": ["daniel2006", "jones1999"], "maxstress": ["daniel2006"], "tsaihill": ["azzi1965"],
        "tsaiwu": ["tsai1971"], "hashin": ["hashin1980"]}
CRITERIA = ("maxstress", "tsaihill", "tsaiwu", "hashin")


class LamError(ValueError):
    pass


def q_matrix(E1, E2, G12, nu12) -> np.ndarray:
    """Reduzierte Steifigkeit [MPa] aus GPa-Werten."""
    E1, E2, G12 = E1 * 1e3, E2 * 1e3, G12 * 1e3
    nu21 = nu12 * E2 / E1
    d = 1 - nu12 * nu21
    if d <= 0:
        raise LamError("ν12·ν21 ≥ 1: Schichtwerte nicht möglich")
    return np.array([[E1 / d, nu12 * E2 / d, 0], [nu12 * E2 / d, E2 / d, 0], [0, 0, G12]])


def t_sigma(theta_deg: float) -> np.ndarray:
    """Transformation der Spannungen (σx, σy, τxy) -> (σ1, σ2, τ12)."""
    c, s = math.cos(math.radians(theta_deg)), math.sin(math.radians(theta_deg))
    return np.array([[c * c, s * s, 2 * c * s], [s * s, c * c, -2 * c * s], [-c * s, c * s, c * c - s * s]])


def t_eps(theta_deg: float) -> np.ndarray:
    """Transformation der Ingenieurdehnungen (εx, εy, γxy) -> (ε1, ε2, γ12)."""
    c, s = math.cos(math.radians(theta_deg)), math.sin(math.radians(theta_deg))
    return np.array([[c * c, s * s, c * s], [s * s, c * c, -c * s], [-2 * c * s, 2 * c * s, c * c - s * s]])


def qbar(Q, theta_deg) -> np.ndarray:
    Ts = t_sigma(theta_deg)
    Te = t_eps(theta_deg)
    return np.linalg.inv(Ts) @ Q @ Te


def parse_layup(text: str) -> list[float]:
    """'[0/45/-45/90]s', '0,90,90,0', '[0/±45/90]2s' -> Winkelliste von unten nach oben."""
    s = str(text or "").strip().replace(" ", "").replace("°", "")
    if not s:
        raise LamError("Lagenaufbau fehlt")
    m = re.fullmatch(r"\[?([^\]]*)\]?(\d*)(s?)", s, flags=re.I)
    if not m:
        raise LamError(f"Lagenaufbau „{text}“ nicht lesbar")
    body, rep, sym = m.group(1), m.group(2), m.group(3)
    seq: list[float] = []
    for tok in re.split(r"[/,;]", body):
        if not tok:
            continue
        k = 1
        if "_" in tok:
            tok, kk = tok.split("_", 1)
            try:
                k = int(kk)
            except ValueError:
                raise LamError(f"Wiederholung „_{kk}“ nicht lesbar") from None
        try:
            if tok.startswith(("±", "+-")):
                a = float(tok.lstrip("±+-"))
                seq += [a, -a] * k
            else:
                seq += [float(tok)] * k
        except ValueError:
            raise LamError(f"Winkel „{tok}“ nicht lesbar") from None
    if rep:
        seq = seq * int(rep)
    if sym:
        seq = seq + seq[::-1]
    if not seq or len(seq) > 400:
        raise LamError("Lagenaufbau leer oder zu gross")
    return seq


def analyse(ply: dict, angles: list[float], t: float | list[float], N=(0, 0, 0), M=(0, 0, 0),
            F12_star: float = -0.5, ST: float | None = None) -> dict:
    """Laminat auswerten. ply: E1, E2, G12 (GPa), nu12, Xt, Xc, Yt, Yc, S12 (MPa)."""
    for k in ("E1", "E2", "G12", "nu12"):
        if ply.get(k) in (None, ""):
            raise LamError(f"Schichtwert {k} fehlt")
    Q = q_matrix(float(ply["E1"]), float(ply["E2"]), float(ply["G12"]), float(ply["nu12"]))
    n = len(angles)
    ts = [float(t)] * n if not isinstance(t, (list, tuple)) else [float(x) for x in t]
    if len(ts) != n or min(ts) <= 0:
        raise LamError("Dicken passen nicht zum Lagenaufbau")
    h = sum(ts)
    z = np.r_[-h / 2, -h / 2 + np.cumsum(ts)]
    A = np.zeros((3, 3))
    B = np.zeros((3, 3))
    D = np.zeros((3, 3))
    Qb = []
    for k, th in enumerate(angles):
        qb = qbar(Q, th)
        Qb.append(qb)
        A += qb * (z[k + 1] - z[k])
        B += qb * (z[k + 1] ** 2 - z[k] ** 2) / 2
        D += qb * (z[k + 1] ** 3 - z[k] ** 3) / 3
    ABD = np.block([[A, B], [B, D]])
    abd = np.linalg.inv(ABD)
    load = np.r_[np.asarray(N, float), np.asarray(M, float)]
    ek = abd @ load
    e0, kap = ek[:3], ek[3:]
    a = np.linalg.inv(A)
    eng = {"Ex": 1 / (h * a[0, 0]) / 1e3, "Ey": 1 / (h * a[1, 1]) / 1e3, "Gxy": 1 / (h * a[2, 2]) / 1e3,
           "nuxy": -a[0, 1] / a[0, 0], "nuyx": -a[0, 1] / a[1, 1]}
    sym = bool(np.allclose(B, 0, atol=1e-6 * max(1.0, np.abs(A).max())))
    S = _strengths(ply, ST)
    plies = []
    for k, th in enumerate(angles):
        rows = []
        for pos, zz in (("unten", z[k]), ("oben", z[k + 1])):
            ex = e0 + zz * kap
            sx = Qb[k] @ ex
            s12 = t_sigma(th) @ sx
            e12 = t_eps(th) @ ex
            rows.append({"pos": pos, "z": float(zz), "eps_xy": ex.tolist(), "sig_xy": sx.tolist(),
                         "eps_12": e12.tolist(), "sig_12": s12.tolist(),
                         "R": _reserve(s12, S, F12_star) if S else None})
        plies.append({"k": k + 1, "angle": th, "t": ts[k], "z0": float(z[k]), "z1": float(z[k + 1]), "points": rows})
    fpf = None
    if S:
        fpf = {}
        for crit in CRITERIA:
            best = None
            for p in plies:
                for r in p["points"]:
                    v = r["R"][crit]["R"]
                    if v is not None and (best is None or v < best[0]):
                        best = (v, p["k"], p["angle"], r["pos"], r["R"][crit].get("mode"))
            if best:
                fpf[crit] = {"R": best[0], "ply": best[1], "angle": best[2], "pos": best[3], "mode": best[4],
                             "N": (load[:3] * best[0]).tolist() if np.any(load) else None}
    return {"A": A.tolist(), "B": B.tolist(), "D": D.tolist(), "abd": abd.tolist(), "h": h, "z": z.tolist(),
            "eps0": e0.tolist(), "kappa": kap.tolist(), "eng": eng, "symmetric": sym, "plies": plies, "fpf": fpf,
            "Q": Q.tolist(), "angles": list(angles), "strengths": S}


def _strengths(ply, ST):
    keys = ("Xt", "Xc", "Yt", "Yc", "S12")
    if any(ply.get(k) in (None, "") for k in keys):
        return None
    S = {k: abs(float(ply[k])) for k in keys}
    if min(S.values()) <= 0:
        raise LamError("Festigkeiten müssen > 0 sein")
    S["ST"] = float(ST) if ST else S["Yc"] / 2
    return S


def _quad_R(a: float, b: float) -> float | None:
    """Kleinster positiver Lastfaktor R mit a R² + b R = 1."""
    if abs(a) < 1e-30:
        return 1 / b if b > 0 else None
    disc = b * b + 4 * a
    if disc < 0:
        return None
    r = (-b + math.sqrt(disc)) / (2 * a)
    return r if r > 0 else None


def _reserve(s, S, F12_star) -> dict:
    s1, s2, t12 = (float(v) for v in s)
    out = {}
    X = S["Xt"] if s1 >= 0 else S["Xc"]
    Y = S["Yt"] if s2 >= 0 else S["Yc"]
    cands = []
    if abs(s1) > 1e-12:
        cands.append((X / abs(s1), "σ1"))
    if abs(s2) > 1e-12:
        cands.append((Y / abs(s2), "σ2"))
    if abs(t12) > 1e-12:
        cands.append((S["S12"] / abs(t12), "τ12"))
    r, mode = min(cands) if cands else (None, None)
    out["maxstress"] = {"R": r, "mode": mode}
    a = (s1 / X) ** 2 - s1 * s2 / X ** 2 + (s2 / Y) ** 2 + (t12 / S["S12"]) ** 2
    out["tsaihill"] = {"R": 1 / math.sqrt(a) if a > 0 else None, "mode": None}
    F1 = 1 / S["Xt"] - 1 / S["Xc"]
    F2 = 1 / S["Yt"] - 1 / S["Yc"]
    F11 = 1 / (S["Xt"] * S["Xc"])
    F22 = 1 / (S["Yt"] * S["Yc"])
    F66 = 1 / S["S12"] ** 2
    F12 = F12_star * math.sqrt(F11 * F22)
    qa = F11 * s1 ** 2 + F22 * s2 ** 2 + F66 * t12 ** 2 + 2 * F12 * s1 * s2
    qb = F1 * s1 + F2 * s2
    out["tsaiwu"] = {"R": _quad_R(qa, qb), "mode": None}
    modes = []
    if s1 >= 0:
        aa = (s1 / S["Xt"]) ** 2 + (t12 / S["S12"]) ** 2
        modes.append((1 / math.sqrt(aa) if aa > 0 else None, "Faser Zug"))
    else:
        modes.append((S["Xc"] / abs(s1), "Faser Druck"))
    if s2 >= 0:
        aa = (s2 / S["Yt"]) ** 2 + (t12 / S["S12"]) ** 2
        modes.append((1 / math.sqrt(aa) if aa > 0 else None, "Matrix Zug"))
    else:
        aa = (s2 / (2 * S["ST"])) ** 2 + (t12 / S["S12"]) ** 2
        bb = ((S["Yc"] / (2 * S["ST"])) ** 2 - 1) * s2 / S["Yc"]
        modes.append((_quad_R(aa, bb), "Matrix Druck"))
    modes = [m for m in modes if m[0] is not None]
    out["hashin"] = {"R": min(modes)[0] if modes else None, "mode": min(modes)[1] if modes else None}
    return out


def ply_from_material(name: str) -> dict:
    """Schichtwerte aus der Werkstoffdatenbank (UD-Verbunde mit E1 … S12)."""
    from labcalc import materials as M
    out = {"name": M.find(name)["name"], "src": {}}
    for k, unit in (("E1", 1e9), ("E2", 1e9), ("G12", 1e9), ("nu12", 1), ("Xt", 1e6), ("Xc", 1e6), ("Yt", 1e6),
                    ("Yc", 1e6), ("S12", 1e6)):
        try:
            v = M.value(name, k)
        except M.MatError:
            continue
        out[k] = v["si"] / unit
        out["src"][k] = {"key": v.get("key"), "unchecked": bool(v.get("nicht_geprueft"))}
    return out
