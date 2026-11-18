"""Funktionelle Gruppen: Korrelationstabelle der Gruppenfrequenzen und Auswertung eines Spektrums.

Bereiche nach den gängigen Tabellenwerken (G. Socrates, Infrared and Raman Characteristic Group Frequencies, 3. Aufl.,
Wiley 2001; R. M. Silverstein, F. X. Webster, D. J. Kiemle, D. L. Bryce, Spectrometric Identification of Organic
Compounds, 8. Aufl., Wiley 2014; einzelne Einträge sind keiner Seite zugeordnet). Die Bewertung ist ein Hinweis, keine
Identifizierung: Sie prüft, ob die typischen Banden einer Gruppe mit passender Stärke vorhanden sind, und nennt
fehlende Schlüsselbanden.
"""
from __future__ import annotations

import numpy as np

from labcalc.irbands import TABLE  # noqa: E402  (A6: Tabelle liegt im SDK, gemeinsam mit dem Elementrechner)

_T = {t[0]: t for t in TABLE}

LEVEL = {"s": 0.15, "m": 0.06, "w": 0.03, "v": 0.03}

# Stoffklassen: (id, deutsch, englisch, nötig [(Tabellen-id | (von, bis), Stärke)], stützend [...], widersprechend [...])
# Mehrere ids in einem Tupel = eine davon genügt.
CLASSES = [
    ("alkyl", "Aliphatische C–H (Alkyl)", "Aliphatic C–H (alkyl)", [((2990, 2840), "m")], [("ch2_sciss", "w"), ("ch3_umb", "w")], []),
    ("longchain", "Lange CH₂-Ketten (Polyethylen, Wachs, Fettsäuren)", "Long CH₂ chains (PE, wax, fatty acids)",
     [("ch2_as", "s"), ("ch2_s", "m"), ("ch2_sciss", "w"), ("ch2_rock", "w")], [], []),
    ("aromatic", "Aromatischer Ring", "Aromatic ring", [(("arom_1600", "arom_1500"), "w"), ((900, 670), "m")],
     [("ch_arom", "w")], []),
    ("alkene", "Alken (C=C)", "Alkene (C=C)", [("cc_alkene", "w"), (("vinyl", "trans", "vinylidene"), "m")], [("ch_alkene", "w")], []),
    ("alcohol", "Alkohol / Phenol (O–H)", "Alcohol / phenol (O–H)", [("oh_hb", "m"), ("alc_co", "m")], [("oh_free", "w")],
     [((1850, 1680), "s")]),
    ("acid", "Carbonsäure", "Carboxylic acid", [("oh_acid", "m"), ("acid_co", "s"), ("acid_co_stretch", "m")], [("acid_oop", "w")], []),
    ("ester", "Ester", "Ester", [((1765, 1710), "s"), (("ester_co_as", "ester_co_s"), "s")], [], [("oh_acid", "m")]),
    ("ketone", "Keton", "Ketone", [("ketone", "s")], [((1380, 1350), "m")], [("ester_co_as", "s"), ("oh_acid", "m")]),
    ("aldehyde", "Aldehyd", "Aldehyde", [("aldehyde", "s"), ("cho", "w")], [], []),
    ("anhydride", "Anhydrid", "Anhydride", [("anh_1", "m"), ("anh_2", "m")], [], []),
    ("carbonate_org", "Organisches Carbonat (z. B. Polycarbonat)", "Organic carbonate (e.g. polycarbonate)",
     [("carbonate_org", "s"), ((1260, 1150), "s")], [("arom_1500", "m")], []),
    ("amide", "Amid (Polyamid, Protein)", "Amide (polyamide, protein)", [("amide1", "s"), ("amide2", "m"), ("nh_amide", "w")], [], []),
    ("urethane", "Urethan (Polyurethan)", "Urethane (polyurethane)", [("nh_amide", "w"), ("urethane_co", "s"), ((1545, 1510), "m"),
                                                                      ((1250, 1200), "m")], [], []),
    ("amine", "Amin", "Amine", [("nh_amine", "m"), ("nh_bend", "m"), ("cn_amine", "m")], [], [((1760, 1640), "s"), ("carbonate", "s")]),
    ("nitrile", "Nitril (C≡N)", "Nitrile (C≡N)", [("cn", "w")], [], []),
    ("isocyanate", "Isocyanat (N=C=O)", "Isocyanate (N=C=O)", [("nco", "s")], [], []),
    ("ether", "Ether (C–O–C)", "Ether (C–O–C)", [("ether", "s")], [], [((1800, 1680), "s"), ("oh_hb", "s")]),
    ("silicone", "Silikon (Polysiloxan)", "Silicone (polysiloxane)", [("sich3", "m"), ("siosi", "s"), ("sich3_rock", "s")], [], []),
    ("silicate", "Silikat / Silica / Quarz", "Silicate / silica / quartz", [("siosi", "s")], [((480, 440), "m")], [("sich3", "m")]),
    ("carbonate", "Anorganisches Carbonat (Kalk, Kreide)", "Inorganic carbonate (chalk, calcite)",
     [("carbonate", "s"), ("carbonate_oop", "w")], [("carbonate_ip", "w")], []),
    ("sulfate", "Sulfat (Gips, Baryt)", "Sulfate (gypsum, barite)", [("sulfate", "s"), ("sulfate_bend", "w")], [], []),
    ("phosphate", "Phosphat", "Phosphate", [("phosphate", "s"), ("phosphate_bend", "w")], [], []),
    ("carboxylate", "Carboxylat (Seife, Stearat)", "Carboxylate (soap, stearate)", [("coo_as", "s"), ("coo_s", "m")], [],
     [("acid_co", "s")]),
    ("nitro", "Nitroverbindung", "Nitro compound", [("no2_as", "s"), ("no2_s", "s")], [], []),
    ("fluoro", "Fluorpolymer (C–F)", "Fluoropolymer (C–F)", [((1250, 1100), "s")], [],
     [((3000, 2840), "w"), ((1800, 1680), "s"), ("arom_1500", "m")]),
    ("chloro", "Chlorverbindung (z. B. PVC)", "Chlorinated (e.g. PVC)", [("ccl", "s"), ((1440, 1410), "m")], [((1260, 1240), "m")],
     [("carbonate", "s")]),
    ("water", "Wasser / Feuchte / Hydrat", "Water / moisture / hydrate", [("oh_hb", "m"), ("water_bend", "w")], [], []),
    ("clay", "Tonmineral / Hydroxid (O–H im Gitter)", "Clay mineral / hydroxide", [("oh_clay", "w"), ("siosi", "s")], [], []),
    ("epoxy", "Epoxid (Bisphenol-A-Harz)", "Epoxy (bisphenol A resin)", [("arom_1500", "s"), ("aryl_ether", "s"), ("arom_para", "m")],
     [("epoxide_ring", "w")], []),
]

# Schlüsselbereiche, deren Fehlen eine Aussage erlaubt
ABSENCE = [
    ((1850, 1650), "Keine Carbonylbande (C=O): kein Ester, Keton, Säure, Amid, Urethan.",
     "No carbonyl band (C=O): no ester, ketone, acid, amide, urethane."),
    ((3600, 3150), "Keine O–H/N–H-Bande: kein Alkohol, Wasser, primäres/sekundäres Amin oder Amid.",
     "No O–H/N–H band: no alcohol, water, primary/secondary amine or amide."),
    ((3000, 2840), "Keine aliphatische C–H-Bande: kaum organische Alkylgruppen (anorganisch oder perfluoriert?).",
     "No aliphatic C–H band: hardly any alkyl groups (inorganic or perfluorinated?)."),
    ((2270, 2100), "Keine Dreifachbindung (C≡N, C≡C) und kein Isocyanat.", "No triple bond (C≡N, C≡C) and no isocyanate."),
]


def _resolve(spec):
    """Tabellen-id(s) oder Bereich -> Liste (von, bis, Name, breit?)."""
    if isinstance(spec, tuple) and len(spec) == 2 and all(isinstance(v, (int, float)) for v in spec):
        lo, hi = sorted(spec)
        return [(lo, hi, f"{hi:g}–{lo:g} cm⁻¹", "")]
    ids = spec if isinstance(spec, tuple) else (spec,)
    out = []
    for i in ids:
        t = _T[i]
        out.append((min(t[1], t[2]), max(t[1], t[2]), t[5], t[4]))
    return out


class Probe:
    """Schnelle Abfragen auf einem normierten Absorbanzspektrum (Maximum 1) mit Peakliste."""

    def __init__(self, x, a, peaks, noisy=None, sigma=0.0):
        self.x, self.a, self.peaks = x, a, peaks
        self.noisy = noisy if noisy is not None else np.zeros(len(x), bool)
        self.sigma = sigma            # Rauschen in Einheiten der stärksten Bande

    def band(self, lo, hi, level, broad):
        m = (self.x >= lo) & (self.x <= hi)
        if m.sum() < 3:
            return None, 0.0, "ausserhalb"
        if self.noisy[m].mean() > 0.5:
            return None, 0.0, "verrauscht"
        # bei schwachem Signal zählt nur, was deutlich über dem Rauschen liegt (Rauschspitzen erreichen 3–4 sigma)
        need = max(LEVEL[level], 6 * self.sigma)
        pk = [p for p in self.peaks if lo <= p["x"] <= hi]
        best = max(pk, key=lambda p: p["h"]) if pk else None
        if broad:
            # breite Bande: hebt den ganzen Bereich an (unteres Quartil), einzelne scharfe Peaks tun das nicht
            floor = float(np.percentile(self.a[m], 25))
            if floor >= need:
                return float(self.x[m][np.argmax(self.a[m])]), floor, "ok"
            if best and best["h"] >= need and best["w"] >= 40:
                return best["x"], best["h"], "ok"
            return None, floor, "schwach"
        if best and best["h"] >= need:
            return best["x"], best["h"], "ok"
        return None, (best["h"] if best else float(np.max(self.a[m]))), "schwach" if best else "fehlt"


def _probe(x, y, yunit):
    from . import peaks as PK
    from . import quality as Q
    from .process import rubberband, to_absorbance
    x = np.asarray(x, float)
    a = to_absorbance(np.asarray(y, float), yunit)
    q = Q.assess(x, a, "A")
    noisy = Q.mask_of(x, q["noisy"])
    calm = ~noisy if (~noisy).sum() >= 10 else np.ones(len(x), bool)
    # Basislinie und Normierung nur aus den ruhigen Bereichen, damit Rauschspitzen nichts verziehen
    o = np.argsort(x[calm])
    xc = x[calm][o]
    # Hülle auf einer leicht geglätteten Kopie, sonst hängt sie an den Rauschminima und alles liegt etwas zu hoch
    from .process import moving_mean
    step = float(abs(np.median(np.diff(x)))) if len(x) > 1 else 2.0
    a_sm = moving_mean(a, max(1, int(round(10 / max(step, 1e-6))) | 1))
    a = a - np.interp(x, xc, rubberband(xc, a_sm[calm][o]))
    mx = float(np.max(a[calm])) or 1.0
    a = a / mx
    pk = PK.find(x, a, "A", {"prominence": 1.5, "distance": 6, "max": 120, "snr": 6})
    return Probe(x, a, [{"x": p["x"], "h": p["prom"], "w": p["fwhm"]} for p in pk],   # Höhe über den Fusspunkten
                 noisy, q["sigma"] / mx if mx > 0 else 0.0), q


def analyse(x, y, yunit: str = "A", lang: str = "de") -> dict:
    """Bewertung aller Stoffklassen und Aussagen aus fehlenden Banden."""
    if yunit in ("D1", "D2"):
        return {"classes": [], "absent": [], "note": "Für abgeleitete Spektren nicht möglich."}
    pr, qa = _probe(x, y, yunit)
    de = lang == "de"
    out = []
    for cid, nde, nen, req, sup, exc in CLASSES:
        ev, n_ok, unchecked = [], 0, []
        for spec, lvl in req:
            hit = None
            for lo, hi, nm, shape in _resolve(spec):
                at, h, st = pr.band(lo, hi, lvl, shape == "br")
                if st in ("ausserhalb", "verrauscht"):
                    continue
                if hit is None or (st == "ok" and hit["status"] != "ok") or (st == hit["status"] and h > hit["h"]):
                    hit = {"band": nm if de else _en(nm, spec), "range": [hi, lo], "status": st, "at": at, "h": h, "need": lvl, "kind": "nötig"}
            if hit is None:
                # Bande liegt ausserhalb des Messbereichs oder im Rauschen: nicht prüfbar
                lo, hi, nm, _s = _resolve(spec)[0]
                unchecked.append({"band": nm if de else _en(nm, spec), "range": [hi, lo], "status": "nicht prüfbar",
                                  "at": None, "h": 0.0, "need": lvl,
                                  "kind": "nicht prüfbar" if de else "not checkable"})
                continue
            ev.append(hit)
            n_ok += hit["status"] == "ok"
        n_req = len(ev)
        if n_req == 0:
            continue
        n_sup = 0
        for spec, lvl in sup:
            for lo, hi, nm, shape in _resolve(spec):
                at, h, st = pr.band(lo, hi, lvl, shape == "br")
                if st == "ok":
                    n_sup += 1
                    ev.append({"band": nm if de else _en(nm, spec), "range": [hi, lo], "status": "ok", "at": at, "h": h,
                               "need": lvl, "kind": "stützend"})
                    break
        contra = []
        for spec, lvl in exc:
            for lo, hi, nm, shape in _resolve(spec):
                at, h, st = pr.band(lo, hi, lvl, shape == "br")
                if st == "ok":
                    contra.append({"band": nm if de else _en(nm, spec), "range": [hi, lo], "status": "widerspricht", "at": at,
                                   "h": h, "need": lvl, "kind": "widersprechend"})
        frac = n_ok / n_req
        missing = n_req - n_ok
        score = frac + 0.15 * n_sup - 0.35 * len(contra)
        # "möglich": Leitbande (die erste nötige) vorhanden, höchstens eine weitere fehlt, und mindestens zwei Belege,
        # wenn die Klasse mehr als eine Bande verlangt; Widersprüche nur, wenn sonst alles passt
        key_ok = ev[0]["status"] == "ok"
        if frac == 1 and not contra:
            verdict = "wahrscheinlich"
        elif key_ok and missing <= 1 and (n_req == 1 or n_ok >= 2) and len(contra) <= (0 if missing else 1):
            verdict = "möglich"
        else:
            verdict = "unwahrscheinlich"
        if unchecked and verdict == "wahrscheinlich":
            # eine nötige Bande liess sich nicht prüfen (z. B. unter 650 cm⁻¹ bei ATR): höchstens "möglich"
            verdict = "möglich"
            score -= 0.1
        out.append({"id": cid, "name": nde if de else nen, "verdict": verdict, "score": round(score, 3),
                    "found": n_ok, "needed": n_req, "evidence": ev + unchecked + contra})
    rank = {"wahrscheinlich": 0, "möglich": 1, "unwahrscheinlich": 2}
    out.sort(key=lambda c: (rank[c["verdict"]], -c["score"]))
    absent = []
    # leer heisst: kaum etwas über 2,5 % der stärksten Bande (leicht geglättet, 98. Perzentil, damit einzelne
    # Rauschspitzen nicht zählen, schwache echte Banden wie C–H in PET aber schon). Nur wenn das Rauschen klein genug
    # ist, um eine Bande dieser Höhe zu sehen, und der Bereich nicht verrauscht ist.
    from .process import moving_mean
    step = float(abs(np.median(np.diff(pr.x)))) if len(pr.x) > 1 else 2.0
    k = max(1, int(round(8 / max(step, 1e-6))) | 1)
    a_s = moving_mean(pr.a, k)
    detect = 3 * pr.sigma / np.sqrt(k) < 0.025
    for (hi, lo), tde, ten in ABSENCE:
        m = (pr.x >= lo) & (pr.x <= hi)
        if detect and m.sum() > 5 and pr.noisy[m].mean() < 0.3 and float(np.percentile(a_s[m], 98)) < 0.025:
            absent.append({"range": [hi, lo], "text": tde if de else ten})
    return {"classes": out, "absent": absent, "masked": qa["noisy"], "snr": qa["snr"],
            "absent_note": "" if detect else (
                "Rauschen zu hoch für Aussagen über fehlende Banden." if de else
                "Noise too high for statements about missing bands.")}


def _en(nm, spec):
    ids = spec if isinstance(spec, tuple) else (spec,)
    for i in ids:
        if isinstance(i, str) and i in _T:
            return _T[i][6]
    return nm


ASSIGN_TOL = 4.0          # cm⁻¹: Tabellenbereiche gelten um so viel erweitert (Messunsicherheit der Bandenlage)
BROAD_MIN = 30.0          # cm⁻¹: schmalere Banden passen nicht zu breiten Tabellenbanden (O–H, Carbonat, Sulfat …)
EXTRA_GROUPS = {"fluoro": ("Fluor",)}    # Stoffklassen, deren Banden nur als Bereich angegeben sind


def class_groups(cid: str) -> set:
    """Tabellengruppen (Spalte "Gruppe" der Korrelationstabelle) einer Stoffklasse: die Gruppen aller Tabellenbanden,
    die die Klasse als nötig oder stützend nennt."""
    for c in CLASSES:
        if c[0] != cid:
            continue
        out = set(EXTRA_GROUPS.get(cid, ()))
        for spec, _lvl in list(c[3]) + list(c[4]):
            ids = spec if isinstance(spec, tuple) else (spec,)
            out |= {_T[i][7] for i in ids if isinstance(i, str) and i in _T}
        return out
    return set()


def context_of(groups_result: dict | None) -> dict:
    """Gruppe -> Rang aus der Gruppenbewertung des ganzen Spektrums: 0 = Klasse „wahrscheinlich“, 1 = „möglich“."""
    ctx: dict = {}
    for c in (groups_result or {}).get("classes", []):
        r = {"wahrscheinlich": 0, "möglich": 1}.get(c.get("verdict"))
        if r is None:
            continue
        for g in class_groups(c["id"]):
            ctx[g] = min(ctx.get(g, 9), r)
    return ctx


def assign(x0: float, strength: str = "m", lang: str = "de", n: int = 3, fwhm: float | None = None,
           context: dict | None = None) -> list[str]:
    """Mögliche Zuordnungen einer Bande. Es passen alle Tabellenbereiche, die (um ASSIGN_TOL erweitert) die Lage
    enthalten. Reihenfolge: (1) Form passt (eine Bande schmaler als BROAD_MIN gehört nicht zu einer breiten
    Tabellenbande), (2) Gruppe einer Stoffklasse, die die Gruppenbewertung des Spektrums als „wahrscheinlich“ (vor
    „möglich“, vor allen anderen) einstuft (context, siehe context_of), (3) Lage im nicht erweiterten Bereich,
    (4) engerer Bereich, (5) Stärke passt zur Tabelle. Die Stärke kommt zuletzt, weil sie relativ zur stärksten Bande
    des Spektrums gilt und wenig über die Gruppe aussagt."""
    order = {"vs": 3, "s": 3, "m": 2, "w": 1}
    ctx = context or {}
    hits = []
    for t in TABLE:
        lo, hi = min(t[1], t[2]), max(t[1], t[2])
        if lo - ASSIGN_TOL <= x0 <= hi + ASSIGN_TOL:
            width = hi - lo
            mism = abs(order.get(strength, 2) - order.get(t[3], 2))
            inside = 0 if lo <= x0 <= hi else 1
            shape_bad = 1 if (fwhm is not None and t[4] == "br" and float(fwhm) < BROAD_MIN) else 0
            hits.append((shape_bad, ctx.get(t[7], 2), inside, width, mism, t[5] if lang == "de" else t[6]))
    hits.sort()
    return [h[5] for h in hits[:n]]


def table(lang: str = "de") -> list[dict]:
    return [{"id": t[0], "lo": min(t[1], t[2]), "hi": max(t[1], t[2]), "strength": t[3], "shape": t[4],
             "name": t[5] if lang == "de" else t[6], "group": t[7]} for t in TABLE]
