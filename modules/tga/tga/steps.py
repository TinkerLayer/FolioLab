"""Stufen, Kennwerte, Rückstand.

- Stufen werden aus der DTG (Massenverlustrate über der Zeit) gefunden: jede deutliche Spitze ist eine Stufe, die
  Grenzen liegen im Minimum der Rate zwischen zwei Spitzen bzw. dort, wo die Rate am Rand unter einen Bruchteil der
  Spitze fällt. Grenzen lassen sich von Hand setzen (dann werden nur die Kennwerte berechnet).
- Extrapolierte Onset- und Endtemperatur nach ISO 11358-1 (Schnittpunkt der Tangente im Wendepunkt mit der
  verlängerten Basislinie vor bzw. nach der Stufe), Mittelpunkttemperatur (halber Massenverlust der Stufe),
  DTG-Spitzentemperatur und maximale Rate.
- T bei x % Massenverlust (T₁, T₂, T₅, T₁₀, T₅₀), Rückstand am Ende und bei gewählter Temperatur.
"""
from __future__ import annotations

import numpy as np

from . import process as PR
from .readers import Run

DEFAULT = {"width": 4.0, "rel": 0.03, "min_loss": 0.3, "edge": 0.05}
LOSS_LEVELS = (1, 2, 5, 10, 50)


def _peaks(y: np.ndarray) -> list[tuple[int, float]]:
    """Lokale Maxima mit Prominenz."""
    n = len(y)
    if n < 3:
        return []
    yy = np.nan_to_num(y, nan=-np.inf)
    d = np.diff(yy)
    cand = np.nonzero((np.concatenate([[1.0], d]) > 0) & (np.concatenate([d, [-1.0]]) <= 0))[0]
    out = []
    for i in cand:
        if not np.isfinite(yy[i]) or yy[i] <= 0:
            continue
        left = np.nonzero(yy[:i] > yy[i])[0]
        lo = left[-1] if len(left) else 0
        right = np.nonzero(yy[i + 1:] > yy[i])[0]
        hi = i + 1 + right[0] if len(right) else n - 1
        lmin = np.min(yy[lo:i + 1]) if i > lo else yy[i]
        rmin = np.min(yy[i:hi + 1]) if hi > i else yy[i]
        base = max(lmin, rmin, 0.0)
        out.append((int(i), float(yy[i] - base)))
    return out


def detect(run: Run, opts: dict | None = None, d: dict | None = None) -> list[tuple[int, int]]:
    """Stufen als Indexpaare (a, b)."""
    o = {**DEFAULT, **(opts or {})}
    d = d or PR.dtg(run, o["width"])
    m = run.pct()
    rate = -np.nan_to_num(d["dt"], nan=0.0)                # Verlustrate %/min, positiv
    n = len(rate)
    if n < 10:
        return []
    top = float(np.max(rate))
    if top <= 0:
        return []
    pk = [(i, p) for i, p in _peaks(rate) if p >= o["rel"] * top]
    pk.sort()
    if not pk:
        return []

    def bounds(peaks):
        res = []
        for k, (i, _) in enumerate(peaks):
            if k == 0:
                a = i
                thr = o["edge"] * rate[i]
                while a > 0 and rate[a] > thr:
                    a -= 1
            else:
                j = peaks[k - 1][0]
                a = j + int(np.argmin(rate[j:i + 1]))
            if k == len(peaks) - 1:
                b = i
                thr = o["edge"] * rate[i]
                while b < n - 1 and rate[b] > thr:
                    b += 1
            else:
                j = peaks[k + 1][0]
                b = i + int(np.argmin(rate[i:j + 1]))
            res.append((a, b))
        return res

    # kleine Stufen verwerfen (iterativ, damit die Grenzen der verbleibenden neu bestimmt werden)
    while True:
        bs = bounds(pk)
        losses = [m[a] - m[b] for a, b in bs]
        k_small = [k for k, L in enumerate(losses) if L < o["min_loss"]]
        if not k_small or len(pk) == 1:
            break
        k = min(k_small, key=lambda k: losses[k])
        pk.pop(k)
    bs = bounds(pk)
    return [(a, b) for (a, b) in bs if m[a] - m[b] >= o["min_loss"] and b > a + 2]


def _linfit(x, y):
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 3 or np.ptp(x[ok]) <= 0:
        return None
    return np.polyfit(x[ok], y[ok], 1)


def _cross(line1, line2):
    s1, c1 = line1
    s2, c2 = line2
    if abs(s1 - s2) < 1e-12:
        return None
    return (c2 - c1) / (s1 - s2)


def characterise(run: Run, a: int, b: int, d: dict | None = None, width: float = 4.0) -> dict:
    """Kennwerte einer Stufe zwischen den Indizes a und b."""
    d = d or PR.dtg(run, width)
    m = run.pct()
    mg = run.mg()
    t = run.time()
    n = len(m)
    a, b = max(0, int(a)), min(n - 1, int(b))
    if b <= a + 1:
        raise PR.OpError("Stufe zu schmal")
    rate = -np.nan_to_num(d["dt"], nan=0.0)
    p = a + int(np.argmax(rate[a:b + 1]))
    seg_rate = (run.T[min(b, n - 1)] - run.T[a]) / max(1e-9, t[b] - t[a]) if run.has_T else 0.0
    dynamic = run.has_T and seg_rate > 0.3
    x = run.T if dynamic else t
    xs = "T" if dynamic else "t"
    loss = float(m[a] - m[b])
    out = {"a": a, "b": b, "x": xs, "T_start": _f(run.T[a]), "T_end": _f(run.T[b]), "t_start": float(t[a]),
           "t_end": float(t[b]), "m_start": float(m[a]), "m_end": float(m[b]), "loss": loss,
           "loss_mg": float(mg[a] - mg[b]) if mg is not None else None,
           "T_peak": _f(run.T[p]), "t_peak": float(t[p]), "rate_peak": float(rate[p]),
           "rate_peak_T": _f(-d["dT"][p]) if dynamic else None}
    # Mittelpunkt: halber Verlust der Stufe
    half = m[a] - loss / 2
    seg = m[a:b + 1]
    k = np.nonzero(seg <= half)[0]
    if len(k):
        j = a + int(k[0])
        if j > a:
            f = (m[j - 1] - half) / ((m[j - 1] - m[j]) or 1e-12)
            out["T_mid"] = _f(run.T[j - 1] + f * (run.T[j] - run.T[j - 1]))
            out["t_mid"] = float(t[j - 1] + f * (t[j] - t[j - 1]))
    # Tangente im Wendepunkt der TG-Kurve über der aufgetragenen Achse (ISO 11358-1): bei Heizen der Punkt
    # grösster Steigung |dm/dT| und dessen örtliche Steigung dm/dT (Kettenregel mit der örtlichen Heizrate), nicht
    # die mittlere Heizrate der Stufe; isotherm über der Zeit mit dm/dt.
    q = p
    if dynamic:
        gT = -np.asarray(d["dT"], float)[a:b + 1]
        if np.isfinite(gT).any() and np.nanmax(gT) > 0:
            q = a + int(np.nanargmax(gT))
            slope = -float(gT[q - a])                       # dm/dT in %/°C
        else:
            slope = -rate[p] / seg_rate                     # Rückfall: mittlere Heizrate der Stufe
    else:
        slope = -rate[p]                                    # dm/dt in %/min
    tang = (slope, m[q] - slope * x[q])
    out["T_inflection"] = _f(run.T[q])
    w = max(5, int(0.25 * (b - a)))
    pre = _linfit(x[max(0, a - w):a + 1], m[max(0, a - w):a + 1]) if a > 2 else None
    post = _linfit(x[b:min(n, b + w + 1)], m[b:min(n, b + w + 1)]) if b < n - 3 else None
    # Basislinie nur übernehmen, wenn sie wirklich ein Plateau ist; sonst waagrecht durch die Stufengrenze
    if pre is None or abs(pre[0]) > 0.1 * abs(slope):
        pre = (0.0, m[a])
    if post is None or abs(post[0]) > 0.1 * abs(slope):
        post = (0.0, m[b])
    on = _cross(tang, tuple(pre))
    en = _cross(tang, tuple(post))
    key = "T" if dynamic else "t"
    if on is not None and x[a] - 0.5 * (x[b] - x[a]) <= on <= x[q]:
        out[f"{key}_onset"] = float(on)
    if en is not None and x[q] <= en <= x[b] + 0.5 * (x[b] - x[a]):
        out[f"{key}_endset"] = float(en)
    out["tangent"] = [float(tang[0]), float(tang[1])]
    out["base_pre"] = [float(pre[0]), float(pre[1])]
    out["base_post"] = [float(post[0]), float(post[1])]
    return out


def _f(v):
    v = float(v)
    return v if np.isfinite(v) else None


def loss_temperatures(run: Run, levels=LOSS_LEVELS) -> dict:
    """T (und t) beim ersten Erreichen von x % Massenverlust, bezogen auf 100 % am Start (bzw. Bezugsmasse)."""
    m = run.pct()
    t = run.time()
    start = float(np.median(m[:3]))
    out = {}
    for L in levels:
        target = start - L
        k = np.nonzero(m <= target)[0]
        if not len(k) or k[0] == 0:
            out[str(L)] = None
            continue
        j = int(k[0])
        f = (m[j - 1] - target) / ((m[j - 1] - m[j]) or 1e-12)
        out[str(L)] = {"T": _f(run.T[j - 1] + f * (run.T[j] - run.T[j - 1])) if run.has_T else None,
                       "t": float(t[j - 1] + f * (t[j] - t[j - 1]))}
    return out


def residue(run: Run, at_T: float | None = None) -> dict:
    m = run.pct()
    mg = run.mg()
    out = {"end": float(np.median(m[-3:])), "end_mg": float(np.median(mg[-3:])) if mg is not None else None,
           "T_end": _f(run.T[-1]) if run.has_T else None}
    if at_T is not None and run.has_T:
        k = np.nonzero(run.T >= at_T)[0]
        if len(k):
            out["at"] = {"T": float(at_T), "m": float(m[k[0]]), "mg": float(mg[k[0]]) if mg is not None else None}
    return out


def mass_at(run: Run, T: float | None = None, t: float | None = None) -> dict | None:
    m = run.pct()
    tt = run.time()
    if T is not None and run.has_T:
        k = np.nonzero(run.T >= T)[0]
        if not len(k):
            return None
        j = int(k[0])
        return {"T": float(run.T[j]), "t": float(tt[j]), "m": float(m[j])}
    if t is not None:
        return {"t": float(t), "T": _f(np.interp(t, tt, run.T)) if run.has_T else None, "m": float(np.interp(t, tt, m))}
    return None


def isothermal(run: Run, segs: list[dict], after: float | None = None) -> list[dict]:
    """Verlust je isothermem Abschnitt; optional nach einer Haltezeit."""
    m = run.pct()
    t = run.time()
    out = []
    for s in segs:
        if s["kind"] != "iso" or s["i1"] - s["i0"] < 5:
            continue
        i0, i1 = s["i0"], s["i1"] - 1
        row = {"no": s["no"], "T": s["T0"], "duration": float(t[i1] - t[i0]), "loss": float(m[i0] - m[i1])}
        if after is not None and t[i1] - t[i0] >= after:
            row["after"] = float(after)
            row["loss_after"] = float(m[i0] - np.interp(t[i0] + after, t[i0:i1 + 1], m[i0:i1 + 1]))
        out.append(row)
    return out


def analyse(run: Run, opts: dict | None = None, manual: list | None = None) -> dict:
    """Alles für die Stufenansicht: DTG, Stufen (automatisch oder von Hand gesetzt), T bei x %, Rückstand, Segmente."""
    o = {**DEFAULT, **(opts or {})}
    d = PR.dtg(run, o["width"])
    t = run.time()
    if manual:
        pairs = []
        for st in manual:
            if run.has_T and st.get("x", "T") == "T":
                a = _idx(run.T, st["lo"])
                b = _idx(run.T, st["hi"])
            else:
                a = int(np.searchsorted(t, st["lo"]))
                b = int(np.searchsorted(t, st["hi"]))
            if b > a + 2:
                pairs.append((a, min(b, len(t) - 1)))
    else:
        pairs = detect(run, o, d)
    steps = []
    for k, (a, b) in enumerate(pairs, 1):
        try:
            s = characterise(run, a, b, d, o["width"])
        except PR.OpError:
            continue
        s["no"] = k
        steps.append(s)
    segs = PR.segments(run)
    return {"steps": steps, "dtg": d, "loss_T": loss_temperatures(run), "residue": residue(run, o.get("residue_T")),
            "segments": segs, "iso": isothermal(run, segs, o.get("iso_after")), "manual": bool(manual)}


def _idx(T, v):
    """Erster Index mit T >= v (Heizen)."""
    k = np.nonzero(T >= float(v))[0]
    return int(k[0]) if len(k) else len(T) - 1
