"""UI-12: Reaktionsketten in einer Umgebung.

Netz (Q32): Schritte in Reihenfolge; jedes Edukt eines Schritts ist entweder ein Einsatzstoff (zugekauft, eingewogen)
oder stammt aus einem Produkt eines früheren Schritts. Ohne Angabe wird automatisch verknüpft, wenn die Formel einem
Produkt eines früheren Schritts entspricht (der späteste solche Schritt). Speist ein Produkt mehrere Schritte, wird es
zu gleichen Teilen aufgeteilt.

Zusammenfassung (Q33):
- Gesamtgleichung: Schrittfaktoren so, dass jeder Zwischenstoff vollständig verbraucht wird (Bedarf rückwärts,
  Ausbeute 100 %); bleibt ein Überschuss, erscheint er als Nebenprodukt.
- Hess: ΔrH°, ΔrG°, lg K der Gesamtgleichung = Summe der Schrittwerte mal Schrittfaktor (298,15 K).
- Mengen vorwärts (Einsatzstoffe → Produkt, mit Schrittausbeuten; Gesamtausbeute = tatsächlich / theoretisch) oder
  rückwärts (Zielmenge → nötige Einsatzstoffe).
- Grüne Kennzahlen über die Kette: Atomökonomie aus der Gesamtgleichung; E-Faktor und PMI aus den Massen der
  Einsatzstoffe und des Produkts (nur Reagenzien; Lösungsmittel und Aufarbeitung im Werkzeug „Lösung ansetzen“).

steps  = [{"id": "s1", "equation": "...", "yield": 85, "links": {"<Edukt>": "auto" | "feed" | "<Schritt-ID>"}}]
feeds  = {"s1|<Edukt>": {"value": 10, "unit": "g" | "mg" | "kg" | "mol" | "mmol"}}
target = {"step": "s3", "species": "<Produkt>", "value": 5, "unit": "g"}   (optional; dann rückwärts)
"""
from __future__ import annotations

import math
import re
from fractions import Fraction

from labcalc import chem as C

MAX_STEPS = 12
UNITS = {"g": ("m", 1.0), "mg": ("m", 1e-3), "kg": ("m", 1e3), "mol": ("n", 1.0), "mmol": ("n", 1e-3)}


def key_of(text: str) -> str:
    """Stoff ohne Phase und Leerzeichen: „CaCO3(s)“ und „CaCO3“ sind derselbe Stoff in der Kette."""
    return re.sub(r"\((?:s|l|g|aq|cr)\)$", "", str(text).replace(" ", ""))


def _num(v):
    if v is None or v == "":
        return None
    try:
        x = float(str(v).replace(",", "."))
    except ValueError:
        return None
    return x if math.isfinite(x) else None


def _to_mol(spec, M):
    if not isinstance(spec, dict):
        return None
    x = _num(spec.get("value"))
    u = UNITS.get(str(spec.get("unit") or "g"))
    if x is None or x < 0 or not u:
        return None
    if u[0] == "n":
        return x * u[1]
    return x * u[1] / M if M else None


def _parse(step: dict, i: int) -> dict:
    sid = str(step.get("id") or f"s{i + 1}")[:20]
    y = _num(step.get("yield"))
    out = {"id": sid, "n": i + 1, "input": str(step.get("equation") or "").strip(),
           "yield": 100.0 if y is None else max(0.0, min(100.0, y)), "terms": [], "ok": False}
    if not out["input"]:
        out["error"] = "leer"
        return out
    try:
        eq = C.parse_equation(out["input"])
        bal = C.balance(eq)
    except C.ChemError as e:
        out["error"] = str(e)
        return out
    if bal.get("status") not in ("ok", "given_ok") or not bal.get("coefs"):
        out["error"] = {"impossible": "nicht ausgleichbar", "ambiguous": "nicht eindeutig ausgleichbar"}.get(bal.get("status"), "nicht ausgeglichen")
        return out
    if bal.get("nuclear") or any(t.species.kind != "chem" for t in eq.terms):
        out["error"] = "nur chemische Reaktionen (keine Kern- oder Elektronengleichungen)"
        return out
    coefs = [Fraction(str(c)) for c in bal["coefs"]]
    for t, c in zip(eq.terms, coefs):
        try:
            M = C.molar_mass(t.species)["M"]
        except C.ChemError:
            M = None
        out["terms"].append({"key": key_of(t.species.text), "text": t.species.text, "unicode": t.species.unicode(),
                             "side": t.side, "nu": c, "M": M})
    out.update(ok=True, eq=eq, coefs=coefs, text=C.format_equation(eq, coefs), latex=C.format_equation(eq, coefs, "latex"))
    return out


def _thermo(st: dict) -> dict:
    from . import analysis as AN
    try:
        r = AN.thermo_result(st["eq"], st["coefs"])
    except C.ChemError as e:
        return {"error": str(e)}
    if r.get("error"):
        return {"error": r["error"]}
    return {k: r.get(k) for k in ("dH", "dS", "dG", "lgK", "refs", "estimated")}


def _frac_str(c: Fraction) -> str:
    return str(c.numerator) if c.denominator == 1 else f"{c.numerator}/{c.denominator}"


def analyse(steps: list, feeds: dict | None = None, target: dict | None = None, with_thermo: bool = True) -> dict:
    feeds = feeds or {}
    if not isinstance(steps, list) or not steps:
        raise C.ChemError("Keine Schritte")
    if len(steps) > MAX_STEPS:
        raise C.ChemError(f"Höchstens {MAX_STEPS} Schritte")
    S = [_parse(s if isinstance(s, dict) else {}, i) for i, s in enumerate(steps)]
    ids = [s["id"] for s in S]
    if len(set(ids)) != len(ids):
        raise C.ChemError("Schritt-IDs doppelt")
    notes = []

    # ---------------------------------------------------------------- Verknüpfungen
    producer = {}                                  # (k, key) -> j
    for k, st in enumerate(S):
        st["links"] = []
        if not st["ok"]:
            continue
        want = (steps[k].get("links") or {}) if isinstance(steps[k], dict) else {}
        for t in st["terms"]:
            if t["side"] > 0:
                continue
            mode = str(want.get(t["key"], "auto"))
            src = None
            if mode == "auto":
                for j in range(k - 1, -1, -1):
                    if S[j]["ok"] and any(p["side"] > 0 and p["key"] == t["key"] for p in S[j]["terms"]):
                        src = j
                        break
            elif mode != "feed":
                j = ids.index(mode) if mode in ids else -1
                if 0 <= j < k and S[j]["ok"] and any(p["side"] > 0 and p["key"] == t["key"] for p in S[j]["terms"]):
                    src = j
                else:
                    notes.append(f"Schritt {k + 1}: {t['unicode']} kommt nicht aus Schritt „{mode}“ (dort kein solches "
                                 f"Produkt oder kein früherer Schritt); als Einsatzstoff behandelt.")
            if src is not None:
                producer[(k, t["key"])] = src
            st["links"].append({"species": t["key"], "unicode": t["unicode"], "mode": mode,
                                "from": S[src]["id"] if src is not None else None, "from_n": src + 1 if src is not None else None})
    consumers = {}                                 # (j, key) -> [k]
    for (k, key), j in producer.items():
        consumers.setdefault((j, key), []).append(k)
    for (j, key), ks in consumers.items():
        if len(ks) > 1:
            notes.append(f"{key} aus Schritt {j + 1} speist die Schritte {', '.join(str(k + 1) for k in ks)}: "
                         f"zu gleichen Teilen aufgeteilt.")

    def nu(st, key, side):
        return next((t["nu"] for t in st["terms"] if t["key"] == key and t["side"] == side), None)

    # ---------------------------------------------------------------- Gesamtgleichung (Bedarf rückwärts, 100 %)
    mult = [Fraction(0)] * len(S)
    for j in range(len(S) - 1, -1, -1):
        st = S[j]
        if not st["ok"]:
            continue
        need = Fraction(0)
        fed = False
        for t in st["terms"]:
            if t["side"] < 0:
                continue
            ks = consumers.get((j, t["key"]), [])
            if ks:
                fed = True
                demand = sum((nu(S[k], t["key"], -1) * mult[k] for k in ks), Fraction(0))
                need = max(need, demand / t["nu"])
        mult[j] = need if fed else Fraction(1)
    net = {}
    first = {}
    for st, m in zip(S, mult):
        if not st["ok"] or m == 0:
            continue
        for t in st["terms"]:
            net[t["key"]] = net.get(t["key"], Fraction(0)) + t["side"] * t["nu"] * m
            first.setdefault(t["key"], t)
    overall = None
    if net:
        nz = {k: v for k, v in net.items() if v != 0}
        den = 1
        for v in list(nz.values()) + [m for m in mult if m]:
            den = den * v.denominator // math.gcd(den, v.denominator)
        ints = {k: v * den for k, v in nz.items()}
        g = 0
        for v in ints.values():
            g = math.gcd(g, int(abs(v)))
        g = g or 1
        scale = Fraction(den, g)
        L = [k for k, v in nz.items() if v < 0]
        R = [k for k, v in nz.items() if v > 0]
        if L and R:
            txt = " + ".join(first[k]["text"] for k in L) + " -> " + " + ".join(first[k]["text"] for k in R)
            eqo = C.parse_equation(txt)
            co = [abs(nz[k]) * scale for k in L + R]
            intermediates = [first[k]["unicode"] for k, v in net.items() if v == 0]
            byp = [first[k]["unicode"] for k in R if any((j, k) in consumers for j in range(len(S)))]
            overall = {"text": C.format_equation(eqo, co), "latex": C.format_equation(eqo, co, "latex"),
                       "coefs": [_frac_str(c) for c in co], "species": [{"key": k, "unicode": first[k]["unicode"], "side": -1 if k in L else 1,
                                                                        "coef": _frac_str(abs(nz[k]) * scale), "M": first[k]["M"]} for k in L + R],
                       "multipliers": {S[i]["id"]: _frac_str(mult[i] * scale) for i in range(len(S)) if S[i]["ok"] and mult[i]},
                       "intermediates": intermediates, "surplus": byp}
            for st, m in zip(S, mult):
                st["mult"] = m * scale if st["ok"] else None
        else:
            notes.append("Keine Gesamtgleichung: alle Stoffe heben sich auf.")

    # ---------------------------------------------------------------- Hess (298,15 K)
    hess = None
    if with_thermo and overall:
        rows, sums, missing = [], {"dH": 0.0, "dG": 0.0, "lgK": 0.0}, []
        complete = {"dH": True, "dG": True, "lgK": True}
        for st in S:
            if not st["ok"] or not st.get("mult"):
                continue
            th = _thermo(st)
            st["thermo"] = th
            m = float(st["mult"])
            row = {"n": st["n"], "id": st["id"], "mult": _frac_str(st["mult"])}
            for q in sums:
                v = th.get(q)
                row[q] = v
                if v is None:
                    complete[q] = False
                else:
                    sums[q] += m * v
            if th.get("error") or th.get("dH") is None:
                missing.append(st["n"])
            rows.append(row)
        hess = {"rows": rows, "missing": missing, "T": 298.15,
                **{q: (sums[q] if complete[q] else None) for q in sums}}
        if hess["lgK"] is not None:
            hess["K"] = 10 ** hess["lgK"] if hess["lgK"] < 300 else math.inf

    # ---------------------------------------------------------------- Mengen
    def forward(use_yield: bool):
        made = [dict() for _ in S]                  # erzeugte Mengen je Schritt
        res = []
        for k, st in enumerate(S):
            if not st["ok"]:
                res.append(None)
                continue
            avail = {}
            for t in st["terms"]:
                if t["side"] > 0:
                    continue
                j = producer.get((k, t["key"]))
                if j is not None:
                    got = made[j].get(t["key"])
                    avail[t["key"]] = None if got is None else got / len(consumers[(j, t["key"])])
                else:
                    avail[t["key"]] = _to_mol(feeds.get(f"{st['id']}|{t['key']}"), t["M"])
            given = {key: n for key, n in avail.items() if n is not None}
            if not given:
                res.append({"xi": None, "avail": avail})
                continue
            lim = min(given, key=lambda key: given[key] / float(nu(st, key, -1)))
            xi = given[lim] / float(nu(st, lim, -1))
            y = st["yield"] / 100.0 if use_yield else 1.0
            for t in st["terms"]:
                if t["side"] > 0:
                    made[k][t["key"]] = float(t["nu"]) * xi * y
            res.append({"xi": xi, "limiting": lim, "avail": avail, "made": dict(made[k])})
        return res

    def main_product():
        if target and target.get("step") in ids:
            k = ids.index(target["step"])
            key = key_of(target.get("species") or "")
            if S[k]["ok"] and any(t["side"] > 0 and t["key"] == key for t in S[k]["terms"]):
                return k, key
        for k in range(len(S) - 1, -1, -1):
            if S[k]["ok"]:
                p = next((t for t in S[k]["terms"] if t["side"] > 0), None)
                if p:
                    return k, p["key"]
        return None, None

    mk, mkey = main_product()
    amounts = {"mode": "target" if target and _num(target.get("value")) is not None else "forward"}
    mp = next((t for t in S[mk]["terms"] if t["side"] > 0 and t["key"] == mkey), None) if mk is not None else None
    if mp:
        amounts["main"] = {"step": S[mk]["id"], "n": mk + 1, "species": mkey, "unicode": mp["unicode"], "M": mp["M"]}
    feeds_out = []
    if amounts["mode"] == "forward":
        act, theo = forward(True), forward(False)
        for k, st in enumerate(S):
            if not st["ok"]:
                continue
            a, th_ = act[k], theo[k]
            st["xi"] = a and a.get("xi")
            st["limiting"] = a and a.get("limiting")
            st["rows"] = [{"species": t["key"], "unicode": t["unicode"], "side": t["side"], "nu": _frac_str(t["nu"]), "M": t["M"],
                           "linked": (k, t["key"]) in producer,
                           "n_in": (a or {}).get("avail", {}).get(t["key"]) if t["side"] < 0 else None,
                           "n_used": float(t["nu"]) * a["xi"] if a and a.get("xi") is not None and t["side"] < 0 else None,
                           "n_out": (a or {}).get("made", {}).get(t["key"]) if t["side"] > 0 else None}
                          for t in st["terms"]]
            for t in st["terms"]:
                if t["side"] < 0 and (k, t["key"]) not in producer:
                    n = (a or {}).get("avail", {}).get(t["key"])
                    feeds_out.append({"step": st["id"], "n_step": k + 1, "species": t["key"], "unicode": t["unicode"],
                                      "n": n, "m": n * t["M"] if n is not None and t["M"] else None,
                                      "used": float(t["nu"]) * a["xi"] if a and a.get("xi") is not None else None})
        if mp:
            na = (act[mk] or {}).get("made", {}).get(mkey)
            nt = (theo[mk] or {}).get("made", {}).get(mkey)
            amounts["product"] = {"n_actual": na, "n_theor": nt, "m_actual": na * mp["M"] if na is not None and mp["M"] else None,
                                  "m_theor": nt * mp["M"] if nt is not None and mp["M"] else None}
            if na is not None and nt:
                amounts["yield_overall"] = 100.0 * na / nt
    else:                                          # rückwärts: Zielmenge → Einsatzstoffe
        n_t = _to_mol(target, mp["M"] if mp else None)
        if mp is None or n_t is None:
            amounts["error"] = "Zielstoff oder Zielmenge ungültig"
        else:
            xi = [0.0] * len(S)
            demand = {}
            xi[mk] = n_t / (float(mp["nu"]) * S[mk]["yield"] / 100.0) if S[mk]["yield"] > 0 else math.inf
            for k in range(mk, -1, -1):
                st = S[k]
                if not st["ok"]:
                    continue
                if k != mk:
                    need = [demand.get((k, t["key"]), 0.0) / (float(t["nu"]) * st["yield"] / 100.0)
                            for t in st["terms"] if t["side"] > 0 and (k, t["key"]) in demand]
                    xi[k] = max(need) if need and st["yield"] > 0 else (math.inf if need else 0.0)
                for t in st["terms"]:
                    if t["side"] < 0 and (k, t["key"]) in producer:
                        j = producer[(k, t["key"])]
                        demand[(j, t["key"])] = demand.get((j, t["key"]), 0.0) + float(t["nu"]) * xi[k]
            for k, st in enumerate(S):
                if not st["ok"]:
                    continue
                st["xi"] = xi[k] or None
                for t in st["terms"]:
                    if t["side"] < 0 and (k, t["key"]) not in producer and xi[k]:
                        n = float(t["nu"]) * xi[k]
                        feeds_out.append({"step": st["id"], "n_step": k + 1, "species": t["key"], "unicode": t["unicode"],
                                          "n": n, "m": n * t["M"] if t["M"] else None, "used": n})
            amounts["product"] = {"n_actual": n_t, "m_actual": n_t * mp["M"] if mp["M"] else None}
            if any(math.isinf(x) for x in xi):
                amounts["error"] = "Ein Schritt hat 0 % Ausbeute: Zielmenge nicht erreichbar"
            y = 1.0
            for k in range(mk, -1, -1):        # Pfad-Ausbeute (für lineare Ketten die Gesamtausbeute)
                if S[k]["ok"] and xi[k]:
                    y *= S[k]["yield"] / 100.0
            amounts["yield_overall"] = 100.0 * y
            if len(consumers) > 0 and any(len(v) > 1 for v in consumers.values()):
                notes.append("Rückwärts: ein geteiltes Zwischenprodukt wird so hergestellt, dass jeder abnehmende Schritt "
                             "genau seinen Bedarf erhält (statt gleicher Teile).")
    amounts["feeds"] = feeds_out

    # ---------------------------------------------------------------- grüne Kennzahlen
    green = {"note": "Nur Reagenzien; Lösungsmittel, Katalysatoren und Aufarbeitung bleiben aussen vor."}
    if overall and mp:
        prod = next((s for s in overall["species"] if s["key"] == mkey and s["side"] > 0), None)
        ins = [s for s in overall["species"] if s["side"] < 0]
        if prod and prod["M"] and all(s["M"] for s in ins):
            m_in = sum(float(Fraction(s["coef"])) * s["M"] for s in ins)
            green["AE"] = 100.0 * float(Fraction(prod["coef"])) * prod["M"] / m_in if m_in else None
    m_feed = [f["m"] for f in feeds_out if f.get("m") is not None]
    mprod = (amounts.get("product") or {}).get("m_actual")
    if m_feed and len(m_feed) == len(feeds_out) and mprod:
        green["PMI"] = sum(m_feed) / mprod
        green["E"] = (sum(m_feed) - mprod) / mprod
    elif feeds_out and mprod:
        green["partial"] = "Nicht für alle Einsatzstoffe ist eine Menge angegeben; E-Faktor und PMI fehlen."

    out_steps = []
    for st in S:
        d = {k: st.get(k) for k in ("id", "n", "input", "yield", "ok", "error", "text", "latex", "links", "xi", "limiting", "rows", "thermo")}
        d["mult"] = _frac_str(st["mult"]) if st.get("mult") else None
        d["terms"] = [{"species": t["key"], "unicode": t["unicode"], "side": t["side"]} for t in st["terms"]]
        out_steps.append(d)
    return {"steps": out_steps, "overall": overall, "hess": hess, "amounts": amounts, "green": green, "notes": notes}
