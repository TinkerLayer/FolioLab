"""Werkstoffauswahl nach Ashby: Eigenschaftsdiagramme, Leistungskennzahlen (Indizes), Rangliste mit Gründen.

Kennzahl M = Π P_k^(e_k) (z. B. E^½/ρ für einen leichten, steifen Balken). Im doppelt-logarithmischen Diagramm
Y gegen X ist M = Y^a X^b konstant auf Geraden lg Y = (−b/a) lg X + lg M / a; die Steigung ist −b/a (Ashby, Kap. 5).
Werte aus der gemeinsamen Werkstoffdatenbank (labcalc.materials) mit Spanne und Quelle; Einträge des Materials Project
nur auf Wunsch (berechnet, DFT).
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

_SDK = Path(__file__).resolve().parents[3] / "sdk" / "python"
if _SDK.is_dir() and str(_SDK) not in sys.path:
    sys.path.insert(0, str(_SDK))

from labcalc import materials as M  # noqa: E402
from labcalc import units as U  # noqa: E402

REFS = ["ashby"]

# id: (Bezeichnung DE, EN, {Eigenschaft: Exponent}, maximieren?)
INDICES = {
    "tie_E": ("Zugstab, steif und leicht: E/ρ", "Tie, stiff and light: E/ρ", {"E": 1, "rho": -1}),
    "beam_E": ("Balken, steif und leicht: E^½/ρ", "Beam, stiff and light: E^½/ρ", {"E": 0.5, "rho": -1}),
    "panel_E": ("Platte, steif und leicht: E^⅓/ρ", "Panel, stiff and light: E^⅓/ρ", {"E": 1 / 3, "rho": -1}),
    "tie_s": ("Zugstab, fest und leicht: Rp/ρ", "Tie, strong and light: σy/ρ", {"Rp": 1, "rho": -1}),
    "beam_s": ("Balken, fest und leicht: Rp^⅔/ρ", "Beam, strong and light: σy^⅔/ρ", {"Rp": 2 / 3, "rho": -1}),
    "panel_s": ("Platte, fest und leicht: Rp^½/ρ", "Panel, strong and light: σy^½/ρ", {"Rp": 0.5, "rho": -1}),
    "spring": ("Feder, Energie je Volumen: Rp²/E", "Spring, energy per volume: σy²/E", {"Rp": 2, "E": -1}),
    "hinge": ("Elastisches Gelenk: Rp/E", "Elastic hinge: σy/E", {"Rp": 1, "E": -1}),
    "lbb": ("Leck vor Bruch: K_Ic/Rp", "Leak before break: K_Ic/σy", {"KIc": 1, "Rp": -1}),
    "tough": ("Schadenstolerant: K_Ic", "Damage tolerant: K_Ic", {"KIc": 1}),
    "thermal": ("Wärmedämmung: 1/λ", "Thermal insulation: 1/λ", {"lambda": -1}),
    "shock": ("Thermoschock: Rp/(E α)", "Thermal shock: σy/(E α)", {"Rp": 1, "E": -1, "alpha": -1}),
}


# Anzeigenamen der Familien (Datenbankfeld „familie“) für die Familienumrisse im Diagramm: (DE, EN)
FAMILY_NAMES = {
    "Kunststoff": ("Thermoplaste", "Thermoplastics"), "Reinmetall": ("Reinmetalle", "Pure metals"),
    "Aluminium": ("Aluminiumlegierungen", "Aluminium alloys"), "Stahl": ("Stähle", "Steels"),
    "Kupfer": ("Kupferlegierungen", "Copper alloys"), "Elastomer": ("Elastomere", "Elastomers"),
    "Edelstahl": ("Nichtrostende Stähle", "Stainless steels"), "Titan": ("Titanlegierungen", "Titanium alloys"),
    "Folie": ("Folien", "Films"), "Nickel": ("Nickellegierungen", "Nickel alloys"), "Papier": ("Papier", "Paper"),
    "Holz": ("Holz", "Wood"), "Faserverbund": ("Faserverbunde", "Fibre composites"),
    "Halbleiter": ("Halbleiter", "Semiconductors"), "Oxidkeramik": ("Oxidkeramik", "Oxide ceramics"),
    "Glas": ("Gläser", "Glasses"), "Kohlenstofffaser": ("Kohlenstofffasern", "Carbon fibres"),
    "UD-Schicht": ("UD-Schichten", "UD plies"), "Gusseisen": ("Gusseisen", "Cast irons"),
    "Magnesium": ("Magnesiumlegierungen", "Magnesium alloys"),
    "Kunststoff verstärkt": ("Verstärkte Kunststoffe", "Reinforced plastics"), "Duroplast": ("Duroplaste", "Thermosets"),
    "Nichtoxidkeramik": ("Nichtoxidkeramik", "Non-oxide ceramics"), "Kohlenstoff": ("Kohlenstoff", "Carbon"),
    "Glaskeramik": ("Glaskeramik", "Glass ceramics"), "Baustoff": ("Baustoffe", "Building materials"),
    "Glasfaser": ("Glasfasern", "Glass fibres"), "Aramidfaser": ("Aramidfasern", "Aramid fibres"),
    "Polymerfaser": ("Polymerfasern", "Polymer fibres"),
}


def family_name(fam: str, lang: str = "de") -> str:
    n = FAMILY_NAMES.get(fam)
    return (n[0] if lang == "de" else n[1]) if n else fam


class SelError(ValueError):
    pass


def disp(si: float | None, prop: str) -> float | None:
    """SI -> Anzeigeeinheit der Eigenschaft (°C für Temperaturen)."""
    if si is None:
        return None
    kind, unit, _, _ = M.PROPS[prop]
    if unit == "°C":
        return si - 273.15
    if unit in ("", "1"):
        return si
    return float(U.from_si(si, unit))


def props(lang: str = "de") -> list[dict]:
    return [{"key": k, "label": (de if lang == "de" else en), "unit": u, "kind": kind}
            for k, (kind, u, de, en) in M.PROPS.items() if kind != "text"]


def _val(r: dict, prop: str):
    try:
        v = M.value(r, prop)
    except M.MatError:
        v = None
    if v and v.get("si") is not None:
        return v
    # kein Einzelwert, aber eine zitierte Spanne: Punkt in der (geometrischen) Mitte, als „nur Spanne“ markiert
    rg = M.range_of(r, prop) if hasattr(M, "range_of") else None
    if rg and rg["min_si"] > 0 and rg["max_si"] > 0:
        return {"si": (rg["min_si"] * rg["max_si"]) ** 0.5, "min_si": rg["min_si"], "max_si": rg["max_si"],
                "art": "spanne", "key": rg.get("range_key"), "range_only": True, "nicht_geprueft": True}
    return None


def point(r: dict, px: str, py: str, lang: str = "de") -> dict | None:
    vx, vy = _val(r, px), _val(r, py)
    if not vx or not vy:
        return None
    s = M.summary(r, lang)
    return {"id": r["id"], "name": s["name"], "klasse": r.get("klasse", ""), "familie": r.get("familie", ""),
            "x": disp(vx["si"], px), "xmin": disp(vx.get("min_si"), px), "xmax": disp(vx.get("max_si"), px),
            "y": disp(vy["si"], py), "ymin": disp(vy.get("min_si"), py), "ymax": disp(vy.get("max_si"), py),
            "art_x": vx.get("art", ""), "art_y": vy.get("art", ""),
            "unchecked": bool(vx.get("nicht_geprueft") or vy.get("nicht_geprueft")),
            "range_only": bool(vx.get("range_only") or vy.get("range_only")),
            "mp": s.get("teil") == "materials_mp", "q": [k for k in (vx.get("key"), vy.get("key")) if k]}


def chart(px: str, py: str, classes: list[str] | None = None, include_mp: bool = False, lang: str = "de") -> dict:
    """Punkte (Wert, Spanne) aller Werkstoffe mit beiden Eigenschaften."""
    for p in (px, py):
        if p not in M.PROPS or M.PROPS[p][0] == "text":
            raise SelError(f"Eigenschaft „{p}“ nicht darstellbar")
    pts = []
    for r in M.materials():
        if classes and r.get("klasse") not in classes:
            continue
        if r.get("_teil") == "materials_mp" and not include_mp:
            continue
        p = point(r, px, py, lang)
        if p:
            pts.append(p)
    kx, ux, dx, ex = M.PROPS[px]
    ky, uy, dy, ey = M.PROPS[py]
    return {"points": pts, "x": {"key": px, "label": dx if lang == "de" else ex, "unit": ux},
            "y": {"key": py, "label": dy if lang == "de" else ey, "unit": uy},
            "classes": {k: (v[0] if lang == "de" else v[1]) for k, v in M.CLASSES.items()},
            "families": {f: family_name(f, lang) for f in sorted({p["familie"] for p in pts if p["familie"]})}}


def index_value(r: dict, expo: dict) -> tuple[float | None, str | None]:
    """M in Anzeigeeinheiten; (None, Grund) wenn ein Wert fehlt oder nicht positiv ist."""
    m = 1.0
    for prop, e in expo.items():
        v = _val(r, prop)
        if v is None:
            return None, f"{prop} fehlt"
        x = disp(v["si"], prop)
        if x is None or x <= 0:
            return None, f"{prop} ≤ 0"
        m *= x ** e
    return m, None


def rank(expo: dict, limits: list[dict] | None = None, classes: list[str] | None = None, include_mp: bool = False,
         lang: str = "de", top: int = 400) -> dict:
    """Rangliste nach M (grösser = besser) mit Ausschlussgründen; limits: [{"prop", "min", "max"}] in Anzeigeeinheiten."""
    if not expo:
        raise SelError("Kennzahl ohne Eigenschaften")
    for p in expo:
        if p not in M.PROPS:
            raise SelError(f"Eigenschaft „{p}“ unbekannt")
    ok, out_ = [], []
    for r in M.materials():
        if r.get("_teil") == "materials_mp" and not include_mp:
            continue
        name = M.summary(r, lang)["name"]
        if classes and r.get("klasse") not in classes:
            continue
        why = []
        for lim in limits or []:
            v = _val(r, lim["prop"])
            if v is None:
                why.append(f"{lim['prop']} fehlt")
                continue
            x = disp(v["si"], lim["prop"])
            lo = lim.get("min")
            hi = lim.get("max")
            if lo not in (None, "") and x < float(lo):
                why.append(f"{lim['prop']} = {x:.4g} < {float(lo):g}")
            if hi not in (None, "") and x > float(hi):
                why.append(f"{lim['prop']} = {x:.4g} > {float(hi):g}")
        m, miss = index_value(r, expo)
        if miss:
            why.append(miss)
        row = {"id": r["id"], "name": name, "klasse": r.get("klasse", ""), "M": m, "why": why,
               "mp": r.get("_teil") == "materials_mp", "unchecked": bool(r.get("nicht_geprueft"))}
        (out_ if why else ok).append(row)
    ok.sort(key=lambda r: -r["M"])
    for i, r in enumerate(ok, 1):
        r["rank"] = i
    return {"ranked": ok[:top], "excluded": out_[:top], "n_ok": len(ok), "n_out": len(out_)}


def guide_slope(expo: dict, px: str, py: str) -> float | None:
    """Steigung der Linien gleicher Kennzahl im Diagramm (py über px), wenn M nur von px und py abhängt."""
    if set(expo) - {px, py} or py not in expo:
        return None
    a, b = expo.get(py, 0), expo.get(px, 0)
    return -b / a if a else None


def compare(names: list[str], lang: str = "de") -> dict:
    """Karten von 2–6 Werkstoffen und die Vereinigung ihrer Eigenschaften."""
    if not 1 <= len(names) <= 6:
        raise SelError("1 bis 6 Werkstoffe wählen")
    cards = [M.card(n, lang) for n in names]
    keys = []
    for c in cards:
        for w in c["werte"]:
            if w["prop"] not in keys:
                keys.append(w["prop"])
    order = [k for k in M.PROPS if k in keys] + [k for k in keys if k not in M.PROPS]
    rows = []
    for k in order:
        kind, unit, de, en = M.PROPS.get(k, ("", "", k, k))
        cells = []
        for c in cards:
            w = next((x for x in c["werte"] if x["prop"] == k), None)
            cells.append(w)
        rows.append({"prop": k, "label": de if lang == "de" else en, "unit": unit, "cells": cells})
    return {"cards": cards, "rows": rows}


def finite(x) -> bool:
    return x is not None and isinstance(x, (int, float)) and math.isfinite(x)
