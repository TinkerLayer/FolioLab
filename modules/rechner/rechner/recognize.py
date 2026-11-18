"""Variablen erkennen: aus einem frei gewählten Namen und/oder einer Einheit die passende Rolle in den Formeln.

"Geschwindigkeit" in m/s -> v (Geschwindigkeit); Tippfehler werden toleriert ("Geschweindigkeit"), Synonyme
erkannt ("Tempo", "Strecke", "Gewicht"), und die Einheit entscheidet zwischen Arten mit gleichem Wort
("Spannung" in MPa -> mechanische Spannung, in V -> elektrische Spannung). Passt keine vordefinierte Art zur Einheit,
wird eine Art "nach Einheit" angeboten (z. B. kg/m), damit jede Grösse als Variable taugt.
"""
from __future__ import annotations

import difflib
import re

from . import expr as E
from . import library as L
from . import render as R
from . import units as U

# Weitere Wörter, unter denen Benutzer eine Grösse anlegen: (Symbol, Art) -> Wörter
SYNONYMS = {
    ("v", "velocity"): ["Tempo", "Speed", "Fahrgeschwindigkeit", "Schnelligkeit", "Geschw"],
    ("s", "length"): ["Strecke", "Distanz", "Abstand", "Fahrstrecke", "Wegstrecke", "Verschiebung", "Distance"],
    ("l", "length"): ["Länge", "Laenge", "Length"],
    ("h", "length"): ["Höhe", "Hoehe", "Fallhöhe", "Height"],
    ("d", "length"): ["Durchmesser", "Diameter", "Dm"],
    ("r", "length"): ["Radius", "Halbmesser"],
    ("b", "length"): ["Breite", "Width"],
    ("m", "mass"): ["Gewicht", "Masse", "Weight", "Mass", "Last"],
    ("t", "time"): ["Dauer", "Zeitdauer", "Zeitspanne", "Fahrzeit", "Duration"],
    ("a", "acceleration"): ["Beschl", "Acceleration"],
    ("F", "force"): ["Belastung", "Zugkraft", "Druckkraft", "Load"],
    ("T", "temperature"): ["Temp", "Temperatur"],
    ("p", "pressure"): ["Luftdruck", "Innendruck", "Überdruck"],
    ("rho", "density"): ["Dichte", "Rohdichte", "Density"],
    ("f", "frequency"): ["Frequenz", "Drehzahl", "Frequency"],
    ("sigma", "stress"): ["Spannung", "Zugspannung", "Normalspannung", "Stress"],
    ("U", "voltage"): ["Spannung", "Voltage", "elektrische Spannung"],
    ("I", "current"): ["Strom", "Stromstärke", "Current"],
    ("R", "resistance"): ["Widerstand", "Resistance"],
    ("P", "power"): ["Leistung", "Power"],
    ("V", "volume"): ["Volumen", "Rauminhalt", "Volume"],
    ("A", "area"): ["Fläche", "Querschnitt", "Querschnittsfläche", "Area"],
}

_FOLD = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "é": "e", "è": "e"})


def fold(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(s).lower().translate(_FOLD))


def _tokens(s: str):
    return [t for t in (fold(x) for x in re.split(r"[\s_\-]+", str(s))) if t]


_ENTRIES = None


def _entries():
    """Alle (Symbol, Art) der Sammlung plus die Grundsymbole jeder Art, mit ihren Wörtern."""
    global _ENTRIES
    if _ENTRIES is None:
        ent = {}
        for s in L.symbols_list():
            ent.setdefault((s["sym"], s["kind"]), {"words": set(), "de": s["de"], "en": s["en"]})["words"].update([s["de"], s["en"]])
        for k in U.KINDS.values():
            if k.key.startswith("dim:"):
                continue
            e = ent.setdefault((k.sym, k.key), {"words": set(), "de": k.de, "en": k.en})
            e["words"].update([k.de, k.en])
        for key, words in SYNONYMS.items():
            if key in ent:
                ent[key]["words"].update(words)
        for key, e in ent.items():
            e["folded"] = {fold(w) for w in e["words"] if fold(w)}
            e["kind_words"] = {fold(U.KINDS[key[1]].de), fold(U.KINDS[key[1]].en)}
        _ENTRIES = ent
    return _ENTRIES


def _word_score(q: str, w: str) -> float:
    if not q or not w:
        return 0.0
    if q == w:
        return 1.0
    r = difflib.SequenceMatcher(None, q, w).ratio()
    if len(q) >= 3 and w.startswith(q):                       # Anfang getippt: "Geschw" -> Geschwindigkeit
        r = max(r, 0.72 + 0.26 * len(q) / len(w))
    elif len(q) >= 4 and (q in w or w in q):                  # "Anfangsgeschwindigkeit" enthält "geschwindigkeit"
        r = max(r, 0.62 + 0.25 * min(len(q), len(w)) / max(len(q), len(w)))
    return r


def _name_score(name: str, sym: str, e) -> tuple[float, str]:
    raw = str(name).strip()
    if not raw:
        return 0.0, ""
    try:
        n = E.norm_name(raw)
    except E.CalcError:
        n = raw
    if n == sym:
        return 1.0, "Symbol"
    if n.lower() == sym.lower() and len(sym) > 1:
        return 0.9, "Symbol"
    best, why = 0.0, ""
    full = fold(raw)
    toks = _tokens(raw) or [full]
    for w in e["folded"]:
        sc = _word_score(full, w)
        for t in toks:
            if t != full:
                sc = max(sc, 0.93 * _word_score(t, w))      # "Geschwindigkeit_Auto" -> "geschwindigkeit"
        if sc > best:
            best, why = sc, w
    return best, why


def recognize(name: str = "", unit: str = "", kind: str | None = None, lang: str = "de", limit: int = 8) -> dict:
    out = {"name": name, "unit": unit, "unit_ok": None, "unit_dims": None, "unit_error": None, "cands": [],
           "best": None, "confident": False, "unit_kinds": []}
    udims = None
    if str(unit or "").strip():
        try:
            _, udims, _ = U.parse_unit(unit)
            out["unit_ok"] = True
            out["unit_dims"] = U.dims_text(udims) or "1"
            out["unit_kinds"] = [k.key for k in U.kinds_for_unit(unit)]       # U-01: pH nur zu pH-Wert/Zahl
        except U.UnitError as e:
            out["unit_ok"] = False
            out["unit_error"] = str(e)
    try:
        nname = E.norm_name(name) if str(name).strip() else ""
    except E.CalcError:
        nname = ""
    cands = []
    for (sym, kd), e in _entries().items():
        k = U.KINDS[kd]
        sc, why = _name_score(name, sym, e)
        fits = udims is None or kd in out["unit_kinds"]
        if udims is not None:
            sc = sc + 0.06 if fits else sc * 0.35                    # Einheit entscheidet bei gleichen Wörtern
        if not str(name).strip() and fits and udims is not None and sym == k.sym:
            sc = 0.5                                               # nur Einheit: Grundsymbol jeder passenden Art
        if sc < 0.55:
            continue
        cands.append({"sym": sym, "kind": kd, "score": round(min(sc, 1.0), 3), "unit_fits": fits,
                      "label": e["de"] if lang == "de" else e["en"], "kind_label": k.de if lang == "de" else k.en,
                      "html": R.sym_html(sym), "units": k.units, "why": why})
    cands.sort(key=lambda c: (-c["score"], not c["unit_fits"], len(c["sym"])))
    # gleiche Art mehrfach (v, v0, v1 …) nur so weit zeigen, wie sie sich im Wert unterscheiden
    seen, short = {}, []
    for c in cands:
        n = seen.get(c["kind"], 0)
        if n >= 3:
            continue
        seen[c["kind"]] = n + 1
        short.append(c)
    cands = short[:limit]
    if udims is not None:                                          # Arten, die nur über die Einheit passen
        have = {c["kind"] for c in cands}
        for kd in out["unit_kinds"]:
            if kd not in have and len(cands) < limit + 3:
                k = U.KINDS[kd]
                cands.append({"sym": k.sym, "kind": kd, "score": 0.5, "unit_fits": True, "by_unit": True,
                              "label": k.de if lang == "de" else k.en, "kind_label": k.de if lang == "de" else k.en,
                              "html": R.sym_html(k.sym), "units": k.units, "why": ""})
    if udims is not None and not out["unit_kinds"]:
        key = U.unit_kind_key(unit)
        k = U.ensure_kind(key)
        cands.append({"sym": nname or "q", "kind": key, "score": 0.5, "unit_fits": True, "own": True,
                      "label": k.de if lang == "de" else k.en, "kind_label": k.de if lang == "de" else k.en,
                      "html": R.sym_html(nname or "q"), "units": [unit, *k.units], "why": ""})
    if kind:
        cands.sort(key=lambda c: c["kind"] != kind)
    out["cands"] = cands
    if cands:
        b = cands[0]
        second = next((c for c in cands[1:] if c["kind"] != b["kind"]), None)
        out["best"] = b
        out["confident"] = bool(b["unit_fits"] and b["score"] >= 0.8 and not b.get("own")
                                and (second is None or b["score"] - second["score"] >= 0.08))
    # Grössenart, wenn der Name nichts Sicheres ergibt: allein aus der Einheit
    if out["confident"]:
        out["kind_guess"] = out["best"]["kind"]
    elif udims is not None:
        uk = out["unit_kinds"]
        out["kind_guess"] = (kind if kind in uk else uk[0]) if uk else U.unit_kind_key(unit)
        U.ensure_kind(out["kind_guess"])
    else:
        out["kind_guess"] = None
    return out
