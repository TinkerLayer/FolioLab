"""Bibliothekssuche und Mischungsanalyse für TGA (Prinzip wie die rechnergestützte Datenbanksuche nach
Schindler u. a. 2017: Kurvenvergleich plus Vergleich der Kennwerte).

- Kurvenwert: Kosinus-Ähnlichkeit der DTG-Kurven (dm/dT) im gemeinsamen Temperaturbereich, wobei die Referenz um bis
  zu ±shift K verschoben werden darf (Heizrate, Probenmasse und Tiegel verschieben Stufen); multipliziert mit der
  Wurzel des Anteils des Referenzverlustes, der im gemessenen Bereich liegt.
- Stufenwert: jede Referenzstufe wird der nächstgelegenen gemessenen Stufe zugeordnet; Abweichungen in Spitzen-
  temperatur (σ = 15 K), Massenverlust (σ = 4 %-Punkte) und Rückstand (σ = 4 %-Punkte) gehen als
  exp(−½·mittleres χ²) ein.
- Treffer-Wert (0–100) = 0,6·Kurve + 0,4·Stufen (einstellbar). Abweichende Atmosphäre oder Heizrate wird angezeigt.
- Mischung: DTG der Probe als nichtnegative Summe von Referenz-DTGs; da jede Referenz in % ihrer eigenen Masse
  vorliegt, sind die Gewichte Massenanteile. Masse ohne Verlust im Messbereich (Füllstoffe) bleibt als „inert“ übrig.
"""
from __future__ import annotations

import math
from itertools import combinations

import numpy as np

from .library import GRID, Library

SIG_T, SIG_L, SIG_R = 15.0, 4.0, 4.0
INERT = {"N₂", "Ar", "He", "inert", "Stickstoff", "Argon", "Helium"}
OXID = {"Luft", "O₂", "oxidativ", "Air"}


def atm_class(g: str) -> str:
    g = (g or "").strip()
    if not g:
        return ""
    if g in INERT or g.lower() in {x.lower() for x in INERT}:
        return "inert"
    if g in OXID or g.lower() in {x.lower() for x in OXID}:
        return "oxidativ"
    return g


def steps_from_dtg(d: np.ndarray, grid: np.ndarray = GRID, rel: float = 0.05) -> list[dict]:
    """Grobe Stufen aus einer DTG auf dem Raster (für gemessene Referenzen): Spitze, Verlust zwischen Minima."""
    y = np.nan_to_num(d, nan=0.0)
    if y.max() <= 0:
        return []
    from .steps import _peaks
    pk = sorted(i for i, p in _peaks(y) if p >= rel * y.max())
    out = []
    for k, i in enumerate(pk):
        a = 0 if k == 0 else pk[k - 1] + int(np.argmin(y[pk[k - 1]:i + 1]))
        b = len(y) - 1 if k == len(pk) - 1 else i + int(np.argmin(y[i:pk[k + 1] + 1]))
        loss = float(np.trapezoid(y[a:b + 1], grid[a:b + 1]) if hasattr(np, "trapezoid") else np.trapz(y[a:b + 1], grid[a:b + 1]))
        if loss >= 0.5:
            out.append({"T_peak": float(grid[i]), "loss": loss})
    return out


def _shifted(G: np.ndarray, s: int) -> np.ndarray:
    if s == 0:
        return G
    out = np.zeros_like(G)
    if s > 0:
        out[:, s:] = G[:, :-s]
    else:
        out[:, :s] = G[:, -s:]
    return out


def _entry_steps(lib: Library, e: dict, row: np.ndarray) -> list[dict]:
    if e.get("steps"):
        return e["steps"]
    key = ("_auto_steps", lib.version)
    if e.get("_auto") != key:
        e["_auto_steps"] = steps_from_dtg(row)
        e["_auto"] = key
    return e["_auto_steps"]


def step_score(q_steps, r_steps, q_res=None, r_res=None, shift: float = 0.0) -> float:
    pens = []
    qs = [s for s in q_steps or [] if (s.get("loss") or 0) >= 0.5 and s.get("T_peak") is not None]
    rs = [s for s in r_steps or [] if (s.get("loss") or 0) >= 1.0]
    used = set()
    for r in rs:
        if not qs:
            pens.append(9.0)
            continue
        T = r["T_peak"] + shift
        j = min(range(len(qs)), key=lambda k: abs(qs[k]["T_peak"] - T))
        used.add(j)
        pens.append(min(9.0, ((qs[j]["T_peak"] - T) / SIG_T) ** 2 + ((qs[j]["loss"] - r["loss"]) / SIG_L) ** 2))
    for k, q in enumerate(qs):
        if k not in used and q["loss"] >= 3.0:
            pens.append(min(9.0, (q["loss"] / SIG_L) ** 2))
    if q_res is not None and r_res is not None:
        pens.append(min(9.0, ((q_res - r_res) / SIG_R) ** 2))
    if not pens:
        return 0.0
    return 100.0 * math.exp(-0.5 * float(np.mean(pens)))


def query(run, steps: list[dict], residue: float | None) -> dict:
    """Suchanfrage aus einem (bearbeiteten) Lauf."""
    from .library import dtg_of_curve
    q = dtg_of_curve(run.T, run.pct())
    return {"dtg": q, "steps": [{"T_peak": s["T_peak"], "loss": s["loss"]} for s in steps if s.get("T_peak") is not None],
            "residue": residue, "gas": run.meta.get("gas", ""), "rate": run.meta.get("rate")}


def search(Q: dict, libs: list[Library], mode: str = "both", shift: int = 20, n: int = 25, category: str | None = None,
           same_atm: bool = False, w_curve: float = 0.6, n_overlay: int = 8) -> dict:
    q = np.asarray(Q["dtg"], float)
    wq = np.isfinite(q)
    if wq.sum() < 30:
        raise ValueError("Der Lauf überdeckt zu wenig vom Bereich 25–1000 °C (Heizabschnitt) für eine Suche.")
    qv = np.where(wq, q, 0.0)
    qn = float(np.linalg.norm(qv)) or 1.0
    shift = int(max(0, min(60, shift)))
    qatm = atm_class(Q.get("gas", ""))
    hits = []
    for lib in libs:
        if not lib.entries:
            continue
        G = np.nan_to_num(lib.G, nan=0.0)
        tot = np.sum(np.clip(G, 0, None), axis=1) + 1e-12
        best = np.full(len(G), -1.0)
        best_s = np.zeros(len(G), dtype=int)
        best_cov = np.zeros(len(G))
        for s in range(-shift, shift + 1):
            Gs = _shifted(G, s)
            Gw = Gs[:, wq]
            num = Gw @ qv[wq]
            den = np.linalg.norm(Gw, axis=1) * qn + 1e-12
            cos = num / den
            cov = np.sum(np.clip(Gw, 0, None), axis=1) / tot
            sc = cos * np.sqrt(np.clip(cov, 0, 1))
            better = sc > best
            best[better], best_s[better], best_cov[better] = sc[better], s, cov[better]
        for i, e in enumerate(lib.entries):
            if category and e.get("category") != category:
                continue
            ratm = atm_class(e.get("atmosphere", ""))
            warn = []
            if qatm and ratm and qatm != ratm:
                if same_atm:
                    continue
                warn.append(f"Atmosphäre: Referenz {e.get('atmosphere')}, Messung {Q.get('gas')}")
            rr, qr = e.get("rate"), Q.get("rate")
            if rr and qr and max(rr, qr) / max(1e-9, min(rr, qr)) > 1.5:
                warn.append(f"Heizrate: Referenz {rr:g} K/min, Messung {qr:g} K/min")
            if best_cov[i] < 0.8:
                warn.append(f"nur {100 * best_cov[i]:.0f} % des Referenzverlustes im gemessenen Bereich")
            curve = 100.0 * max(0.0, float(best[i]))
            stp = step_score(Q.get("steps"), _entry_steps(lib, e, G[i]), Q.get("residue"), e.get("residue"), float(best_s[i]))
            if mode == "curve":
                hqi = curve
            elif mode == "steps":
                hqi = stp
            else:
                hqi = w_curve * curve + (1 - w_curve) * stp
            if qatm and ratm and qatm != ratm:
                hqi *= 0.85
            hits.append({"lib": lib.id, "lib_name": lib.name, "id": e["id"], "name": e["name"],
                         "category": e.get("category", ""), "hqi": round(hqi, 2), "curve": round(curve, 2),
                         "step": round(stp, 2), "shift": int(best_s[i]), "coverage": float(best_cov[i]),
                         "atmosphere": e.get("atmosphere", ""), "rate": e.get("rate"), "residue": e.get("residue"),
                         "warnings": warn, "source": e.get("source") or {}, "kind": e.get("kind", "model"),
                         "modelled": lib.kind == "model" or e.get("kind") in ("model", "steps"), "note": e.get("note", ""),
                         "_lib": lib, "_i": i})
    hits.sort(key=lambda h: -h["hqi"])
    hits = hits[:max(1, int(n))]
    for k, h in enumerate(hits):
        lib, i = h.pop("_lib"), h.pop("_i")
        h["rank"] = k + 1
        if k < n_overlay:
            row = _shifted(np.nan_to_num(lib.G[i:i + 1], nan=0.0), h["shift"])[0]
            h["y"] = row.astype(np.float32)
            tg = lib.tg(lib.entries[i])
            if h["shift"]:
                tg = np.interp(GRID - h["shift"], GRID, tg, left=np.nan, right=np.nan)
            h["tg"] = tg.astype(np.float32)
    return {"hits": hits, "query": q.astype(np.float32), "grid": {"x0": float(GRID[0]), "dx": 1.0, "n": len(GRID)},
            "mode": mode, "shift": shift, "w_curve": float(w_curve)}


# ----------------------------------------------------------------------------- Mischung
def _nnls_small(G: np.ndarray, b: np.ndarray):
    k = len(b)
    best_w, best_gain = np.zeros(k), 0.0
    for r in range(1, k + 1):
        for S in combinations(range(k), r):
            S = list(S)
            try:
                w = np.linalg.solve(G[np.ix_(S, S)], b[S])
            except np.linalg.LinAlgError:
                continue
            if np.any(w <= 0):
                continue
            gain = float(2 * w @ b[S] - w @ G[np.ix_(S, S)] @ w)
            if gain > best_gain:
                best_gain, best_w = gain, np.zeros(k)
                best_w[S] = w
    return best_w, best_gain


def mixture(Q: dict, libs: list[Library], max_components: int = 3, shift: int = 20, pool: int = 14, top: int = 6) -> dict:
    q = np.asarray(Q["dtg"], float)
    wq = np.isfinite(q)
    single = search(Q, libs, "curve", shift, n=pool, n_overlay=0)["hits"]
    if not single:
        return {"combos": [], "note": "Keine Referenz gefunden."}
    # Kandidaten: beste Einzeltreffer plus beste Treffer für den Rest nach Abzug des besten
    byid = {(lib.id, e["id"]): (lib, i) for lib in libs for i, e in enumerate(lib.entries)}
    cands = []
    for h in single:
        lib, i = byid[(h["lib"], h["id"])]
        cands.append((lib, i, h["shift"]))
    lib0, i0, s0 = cands[0]
    r0 = _shifted(np.nan_to_num(lib0.G[i0:i0 + 1], nan=0.0), s0)[0]
    a0 = float(np.dot(q[wq], r0[wq]) / (np.dot(r0[wq], r0[wq]) or 1.0))
    resid = np.where(wq, np.clip(q - a0 * r0, 0, None), np.nan)
    try:
        more = search({**Q, "dtg": resid, "steps": []}, libs, "curve", shift, n=pool // 2, n_overlay=0)["hits"]
    except ValueError:
        more = []
    have = {(lib.id, i) for lib, i, _ in cands}
    for h in more:
        lib, i = byid[(h["lib"], h["id"])]
        if (lib.id, i) not in have:
            cands.append((lib, i, h["shift"]))
            have.add((lib.id, i))
    X = np.array([_shifted(np.nan_to_num(lib.G[i:i + 1], nan=0.0), s)[0] for lib, i, s in cands])
    y = q[wq]
    Xm = X[:, wq]
    Gm = Xm @ Xm.T
    bm = Xm @ y
    sst = float(y @ y) or 1.0
    k_max = max(1, min(int(max_components), 4))
    P = min(len(cands), 16 if k_max == 4 else 24)
    res = []
    for k in range(1, k_max + 1):
        for S in combinations(range(P), k):
            S = list(S)
            w, gain = _nnls_small(Gm[np.ix_(S, S)], bm[S])
            if np.count_nonzero(w) != k:
                continue
            res.append((100.0 * gain / sst, S, w))
    # Sparsamkeit: jede weitere Komponente muss den unerklärten Rest deutlich verkleinern (k=2: um ein Drittel,
    # k=3: um ein Viertel). Ein fester Abzug in HQI-Punkten würde kleine, breite Füllstoffstufen (z. B. 10 % CaCO₃
    # neben 90 % Polymer) nie zulassen, weil sie nur wenig zur Kurvenvarianz beitragen.
    def score(hqi, k):
        return 100.0 - (100.0 - hqi) * (1.0 + 0.5 * (k - 1))

    res.sort(key=lambda t: -score(t[0], len(t[1])))
    combos, seen = [], set()
    for hqi, S, w in res:
        key = frozenset(S)
        if key in seen:
            continue
        seen.add(key)
        comps = []
        fit = np.zeros(len(GRID))
        tg = np.zeros(len(GRID))
        for j, wj in zip(S, w):
            lib, i, s = cands[j]
            e = lib.entries[i]
            yy = X[j] * wj
            fit += yy
            t = lib.tg(e)
            if s:
                t = np.interp(GRID - s, GRID, t, left=np.nan, right=np.nan)
            tg += wj * np.nan_to_num(t, nan=float(np.nanmin(t)) if np.isfinite(t).any() else 100.0)
            comps.append({"lib": lib.id, "lib_name": lib.name, "id": e["id"], "name": e["name"], "frac": float(wj),
                          "shift": int(s), "source": e.get("source") or {}, "residue": e.get("residue"),
                          "modelled": lib.kind == "model" or e.get("kind") in ("model", "steps"), "y": yy.astype(np.float32)})
        tot = float(sum(c["frac"] for c in comps))
        inert = max(0.0, 1.0 - tot)
        tg += inert * 100.0
        r = np.full(len(GRID), np.nan)
        r[wq] = q[wq] - fit[wq]
        pres = sum(c["frac"] * (c["residue"] or 0.0) for c in comps) + 100.0 * inert
        combos.append({"hqi": round(float(hqi), 2), "n": len(S), "score": round(score(float(hqi), len(S)), 2),
                       "components": comps, "sum": tot, "inert": inert, "residue_pred": pres,
                       "fit": fit.astype(np.float32), "tg": tg.astype(np.float32), "residual": r.astype(np.float32)})
        if len(combos) >= top:
            break
    note = ""
    if combos and combos[0]["sum"] > 1.15:
        note = "Summe der Anteile > 100 %: Referenzen passen in der Verlusthöhe nicht zur Probe (andere Rezeptur?)."
    return {"combos": combos, "query": q.astype(np.float32), "note": note}
