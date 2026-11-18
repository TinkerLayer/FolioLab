"""Lösungen ansetzen: aus Feststoffen (auch Hydrate), aus flüssigen Reagenzien bzw. Stammlösungen, aus zertifizierten
Standards und als Mischungen mehrerer Stoffe (Tickets ER-L01 bis ER-L03).

Regeln (Feature-Spezifikation 01, „keine versteckten Annahmen“):
- Die Form des Stoffs ist explizit: eingewogen wird die angegebene Form (z. B. CuSO4·5H2O); die Zielkonzentration
  bezieht sich auf eine genannte Bezugsspezies (z. B. Cu²⁺ oder CuSO4). Ohne Angabe ist die Form selbst der Bezug.
- Fehlt ein Wert, der nötig ist (Dichte für Massenanteil oder Molalität), wird die Rechnung verweigert und der Wert
  benannt – es wird nichts angenommen.
- Eine Dichte braucht eine Quelle und eine Temperatur.
- Volumina werden nicht als additiv behandelt: es wird immer „auf das Endvolumen auffüllen“ gerechnet.
- Jeder Rechenschritt landet im Arbeitsblatt (``steps``) mit Formel, Wert, Einheit und Quelle.

Molare Massen: CIAAW-Standardatomgewichte über labcalc.chem.
"""
from __future__ import annotations

import math
import re

from . import chem as C

REFS = ["ciaaw2024", "harris"]
FLASKS_ML = (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 5000)   # Messkolben nach DIN EN ISO 1042

# Konzentrationsbasen: Einheit -> (Art, Faktor in SI-nahe Grösse)
#   molar: mol/L;  mass: g/L;  w: Massenanteil (1);  wv: g/mL;  b: mol/kg
BASES = {
    "mol/L": ("molar", 1.0), "M": ("molar", 1.0), "mmol/L": ("molar", 1e-3), "mM": ("molar", 1e-3),
    "µmol/L": ("molar", 1e-6), "µM": ("molar", 1e-6), "umol/L": ("molar", 1e-6),
    "g/L": ("mass", 1.0), "mg/L": ("mass", 1e-3), "mg/mL": ("mass", 1.0), "µg/mL": ("mass", 1e-3),
    "µg/L": ("mass", 1e-6), "ppm": ("mass", 1e-3),                 # ppm hier = mg/L (wässrig, so beschriftet)
    "%(w/v)": ("wv", 0.01), "g/100mL": ("wv", 0.01),
    "%(w/w)": ("w", 0.01), "%": ("w", 0.01), "w": ("w", 1.0),
    "mol/kg": ("b", 1.0), "mmol/kg": ("b", 1e-3),
}
VOL = {"L": 1.0, "mL": 1e-3, "µL": 1e-6, "uL": 1e-6, "dL": 0.1}
MASS = {"g": 1.0, "mg": 1e-3, "kg": 1e3, "µg": 1e-6}


class PrepError(C.ChemError):
    pass


# ----------------------------------------------------------------------------- Grundbausteine
def _num(v, what: str) -> float:
    if isinstance(v, str):
        v = v.strip().replace(",", ".")
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise PrepError(f"{what}: Zahl erwartet")
    if not math.isfinite(x):
        raise PrepError(f"{what}: Zahl erwartet")
    return x


def volume_L(v, unit: str = "mL") -> float:
    if unit not in VOL:
        raise PrepError(f"Volumeneinheit „{unit}“ unbekannt (L, mL, µL)")
    x = _num(v, "Volumen") * VOL[unit]
    if x <= 0:
        raise PrepError("Das Volumen muss grösser als 0 sein")
    return x


def _plain(counts) -> dict:
    out = {}
    for k, n in counts.items():
        b = re.sub(r"^\d+", "", k)
        out[b] = out.get(b, 0) + float(n)
    return out


def form(text: str) -> dict:
    """Chemische Form (was eingewogen bzw. abgemessen wird): Formel, Hydratwasser, molare Masse."""
    t = (text or "").strip()
    if not t:
        raise PrepError("Kein Stoff angegeben")
    name = ""
    try:
        sp = C.parse_species(t.replace("*", "·"))
    except C.ChemError as e:
        from . import substances as S                    # Name aus der Stoffsammlung (z. B. „Tris“, „HEPES“)
        k = S.resolve(t)
        m = S.get(k) if k else None
        if not m or not m.get("formula"):
            raise PrepError(f"Unbekannter Stoff bzw. Formel: {e}")
        sp = C.parse_species(m["formula"])
        name = m.get("de") or m.get("en") or t
    if sp.kind != "chem":
        raise PrepError(f"„{t}“ ist kein chemischer Stoff")
    mm = C.molar_mass(sp)
    water = sum(float(n or 1) for n in re.findall(r"[·*•.]\s*(\d*(?:[.,]\d+)?)\s*H2O\b", t.replace(",", ".")))
    return {"text": t, "formula": sp.unicode(), "counts": _plain(sp.counts), "charge": sp.charge, "M": mm["M"],
            "M_u": mm["u"], "water": water, "name": name or sp.name}


def per_unit(f: dict, basis: dict) -> float:
    """Anzahl Bezugsspezies je Formeleinheit der Form, z. B. Cu²⁺ in CuSO4·5H2O = 1, Cl⁻ in CaCl2·2H2O = 2.
    Bestimmt über das knappste Element der Bezugsspezies (ohne H und O, falls sie andere Elemente hat)."""
    if basis["formula"] == f["formula"]:
        return 1.0
    els = [e for e in basis["counts"] if e not in ("H", "O")] or list(basis["counts"])
    ratios = []
    for e in els:
        have = f["counts"].get(e, 0)
        if have <= 0:
            raise PrepError(f"{basis['formula']} ist in {f['formula']} nicht enthalten ({e} fehlt)")
        ratios.append(have / basis["counts"][e])
    k = min(ratios)
    if k < 1 - 1e-9:
        raise PrepError(f"{basis['formula']} ist in {f['formula']} nicht ganz enthalten")
    if abs(k - round(k)) > 1e-6:
        raise PrepError(f"{basis['formula']} je Formeleinheit {f['formula']} ist keine ganze Zahl ({k:g}); "
                        "Anzahl bitte angeben")
    return float(round(k))


def density(d) -> dict | None:
    """Dichte {value, unit (g/mL | g/L | kg/m3), T_C, source} -> g/mL. Ohne Quelle oder Temperatur verweigert."""
    if d in (None, "", {}):
        return None
    if not isinstance(d, dict):
        raise PrepError("Dichte bitte mit Wert, Temperatur und Quelle angeben")
    v = _num(d.get("value"), "Dichte")
    u = d.get("unit") or "g/mL"
    fac = {"g/mL": 1.0, "g/cm3": 1.0, "g/cm³": 1.0, "kg/L": 1.0, "g/L": 1e-3, "kg/m3": 1e-3, "kg/m³": 1e-3}.get(u)
    if fac is None:
        raise PrepError(f"Dichteeinheit „{u}“ unbekannt")
    if v <= 0:
        raise PrepError("Die Dichte muss grösser als 0 sein")
    src = d.get("source")
    if not src or (isinstance(src, dict) and not (src.get("title") or src.get("doi") or src.get("url") or src.get("key"))):
        raise PrepError("Die Dichte braucht eine Quelle (z. B. Datenblatt oder Tabellenwerk)")
    if d.get("T_C") in (None, ""):
        raise PrepError("Die Dichte braucht die Temperatur, bei der sie gilt")
    return {"g_mL": v * fac, "T_C": _num(d["T_C"], "Temperatur der Dichte"), "source": src, "value": v, "unit": u}


def _src_text(src) -> str:
    if isinstance(src, dict):
        return src.get("key") or ", ".join(str(x) for x in (src.get("authors"), src.get("title"), src.get("year"))
                                          if x) or src.get("doi") or src.get("url") or ""
    return str(src)


class Sheet:
    """Arbeitsblatt: Schritte mit Text, Formel, Ergebnis, Einheit und Quelle."""

    def __init__(self):
        self.steps = []

    def add(self, text, formula="", value=None, unit="", source=""):
        self.steps.append({"text": text, "formula": formula, "value": value, "unit": unit, "source": source})
        return value


def target(value, unit: str) -> dict:
    if unit not in BASES:
        raise PrepError(f"Konzentrationsangabe „{unit}“ unbekannt ({', '.join(BASES)})")
    x = _num(value, "Zielkonzentration")
    if x <= 0:
        raise PrepError("Die Zielkonzentration muss grösser als 0 sein")
    kind, fac = BASES[unit]
    if kind in ("w", "wv") and x * fac >= 1:
        raise PrepError("Massenanteil muss unter 100 % liegen")
    return {"kind": kind, "x": x * fac, "value": x, "unit": unit}


def basis_moles(tg: dict, V_L: float, M_basis: float, sheet: Sheet, rho_sol: dict | None = None,
                label: str = "B") -> float:
    """Stoffmenge der Bezugsspezies für das Endvolumen. Massenanteil und Molalität brauchen die Dichte der Lösung."""
    k, x = tg["kind"], tg["x"]
    if k == "molar":
        return sheet.add(f"Stoffmenge {label}", f"n = c·V = {x:g} mol/L · {V_L:g} L", x * V_L, "mol")
    if k == "mass":
        m = sheet.add(f"Masse {label} im Endvolumen", f"m = β·V = {x:g} g/L · {V_L:g} L", x * V_L, "g")
        return sheet.add(f"Stoffmenge {label}", f"n = m/M = {m:.6g} g / {M_basis:.6g} g/mol", m / M_basis, "mol")
    if k == "wv":
        m = sheet.add(f"Masse {label} im Endvolumen", f"m = {x * 100:g} g/100 mL · {V_L * 1000:g} mL",
                      x * V_L * 1000, "g")
        return sheet.add(f"Stoffmenge {label}", f"n = m/M = {m:.6g} g / {M_basis:.6g} g/mol", m / M_basis, "mol")
    if rho_sol is None:
        what = "Massenanteil" if k == "w" else "Molalität"
        raise PrepError(f"{what} → Einwaage für ein Volumen braucht die Dichte der fertigen Lösung (mit Quelle und "
                        "Temperatur); sie wird nicht angenommen")
    m_sol = sheet.add("Masse der Lösung", f"m(Lsg) = ρ·V = {rho_sol['g_mL']:g} g/mL · {V_L * 1000:g} mL",
                      rho_sol["g_mL"] * V_L * 1000, "g", _src_text(rho_sol["source"]))
    if k == "w":
        m = sheet.add(f"Masse {label}", f"m = w·m(Lsg) = {x:g} · {m_sol:.6g} g", x * m_sol, "g")
    else:
        m_solv = sheet.add("Masse Lösungsmittel", f"m(LM) = m(Lsg)/(1 + b·M) = {m_sol:.6g} g / (1 + {x:g}·"
                           f"{M_basis / 1000:.6g} kg/mol)", m_sol / (1 + x * M_basis / 1000), "g")
        return sheet.add(f"Stoffmenge {label}", f"n = b·m(LM) = {x:g} mol/kg · {m_solv / 1000:.6g} kg",
                         x * m_solv / 1000, "mol")
    return sheet.add(f"Stoffmenge {label}", f"n = m/M = {m:.6g} g / {M_basis:.6g} g/mol", m / M_basis, "mol")


def _purity(p) -> float:
    if p in (None, ""):
        return 1.0
    x = _num(p, "Reinheit")
    if x > 1:
        x /= 100                                          # in Prozent angegeben
    if not 0 < x <= 1:
        raise PrepError("Reinheit zwischen 0 und 100 %")
    return x


def _round_to(x: float, d: float) -> float:
    return round(x / d) * d


# ----------------------------------------------------------------------------- ER-L02 Feststoff
def from_solid(substance: str, value, unit: str, V, V_unit: str = "mL", basis: str | None = None,
               purity=None, balance_d: float | None = None, flask: bool = False, rho_solution=None) -> dict:
    """Einwaage eines Feststoffs (Form = substance, auch Hydrat) für eine Lösung mit Zielkonzentration der
    Bezugsspezies basis (Standard: die Form selbst). Reinheit als Anteil oder Prozent der Form."""
    sh = Sheet()
    f = form(substance)
    b = form(basis) if basis and basis.strip() else f
    k = per_unit(f, b)
    V_L = volume_L(V, V_unit)
    notes = []
    if flask:
        mL = V_L * 1000
        fl = next((x for x in FLASKS_ML if x >= mL - 1e-9), None)
        if fl is None:
            raise PrepError("Kein Messkolben in dieser Grösse")
        if abs(fl - mL) > 1e-9:
            notes.append(f"Messkolben {fl:g} mL statt {mL:g} mL gewählt (kleinster passender).")
        V_L = fl / 1000
    tg = target(value, unit)
    rho = density(rho_solution)
    sh.add(f"Molare Masse {f['formula']}", "M aus Standardatomgewichten", f["M"], "g/mol", "ciaaw2024")
    if b is not f:
        sh.add(f"Molare Masse {b['formula']}", "M aus Standardatomgewichten", b["M"], "g/mol", "ciaaw2024")
        sh.add(f"{b['formula']} je Formeleinheit {f['formula']}", "aus der Formel", k, "")
    n_b = basis_moles(tg, V_L, b["M"], sh, rho, b["formula"])
    n_f = sh.add(f"Stoffmenge {f['formula']}", f"n(Form) = n({b['formula']}) / {k:g}", n_b / k, "mol") \
        if b is not f else n_b
    m_pure = sh.add(f"Masse {f['formula']} (rein)", f"m = n·M = {n_f:.6g} mol · {f['M']:.6g} g/mol", n_f * f["M"], "g")
    pu = _purity(purity)
    m = m_pure
    if pu < 1:
        m = sh.add("Einwaage mit Reinheit", f"m = m(rein)/Reinheit = {m_pure:.6g} g / {pu:g}", m_pure / pu, "g")
    out = {"form": f, "basis": b, "per_unit": k, "V_L": V_L, "n_basis": n_b, "n_form": n_f, "m_pure_g": m_pure,
           "purity": pu, "mass_g": m, "target": tg, "notes": notes}
    if balance_d:
        d = _num(balance_d, "Ablesbarkeit der Waage")
        if d <= 0:
            raise PrepError("Ablesbarkeit muss grösser als 0 sein")
        mr = _round_to(m, d)
        if mr <= 0:
            raise PrepError("Einwaage liegt unter der Ablesbarkeit der Waage")
        out["mass_rounded_g"] = sh.add("Einwaage gerundet auf die Waage", f"Ablesbarkeit {d:g} g", mr, "g")
        out["actual_factor"] = mr / m
        if tg["kind"] in ("molar", "mass", "wv"):
            out["actual_value"] = sh.add("Tatsächliche Konzentration", "Ziel · m(gerundet)/m",
                                         tg["value"] * mr / m, tg["unit"])
        if d / m > 0.001:
            notes.append(f"Ablesbarkeit {d:g}".replace(".", ",") + " g ist mehr als 0,1 % der Einwaage; grössere Menge ansetzen oder "
                         "feinere Waage nehmen.")
    if f["water"]:
        notes.append(f"Eingewogen wird das Hydrat {f['formula']} ({f['water']:g} H₂O je Formeleinheit); die "
                     f"Konzentration bezieht sich auf {b['formula']}.")
    sh.add(f"Ansetzen: {out.get('mass_rounded_g', m):.4g} g {f['formula']} lösen und im Messkolben auf "
           f"{V_L * 1000:g} mL auffüllen", "", None, "")
    out["steps"] = sh.steps
    out["refs"] = REFS
    return out


def mixture(components: list[dict], V, V_unit: str = "mL", **kw) -> dict:
    """Eigene Mischung: mehrere Feststoffe in einer Lösung, jeder mit eigener Zielkonzentration."""
    if not components:
        raise PrepError("Keine Bestandteile")
    rows = [from_solid(c["substance"], c["value"], c["unit"], V, V_unit, basis=c.get("basis"),
                       purity=c.get("purity"), balance_d=kw.get("balance_d")) for c in components]
    return {"components": rows, "V_L": rows[0]["V_L"], "refs": REFS,
            "notes": ["Alle Bestandteile lösen, dann gemeinsam auf das Endvolumen auffüllen."]}


# ----------------------------------------------------------------------------- ER-L04 Verdünnungsreihe und Mischen
LINEAR = ("molar", "mass", "wv")                         # Konzentrationsbasen, für die c₁V₁ = c₂V₂ gilt


def series(c0, unit: str, factor, steps: int, V_final, V_unit: str = "mL", replicates: int = 1,
           min_pipette_uL: float | None = None) -> dict:
    """Verdünnungsreihe 1:factor über steps Stufen. Jede Stufe behält V_final·replicates; der Übertrag in die nächste
    Stufe wird mit angesetzt (rückwärts gerechnet). Gilt nur für Stoffmengen-/Massenkonzentrationen."""
    tg = target(c0, unit)
    if tg["kind"] not in LINEAR:
        raise PrepError("Verdünnungsreihe nur für mol/L, g/L oder % (w/v): für Massenanteile und Molalität gilt "
                        "c₁V₁ = c₂V₂ nicht")
    f = _num(factor, "Verdünnungsfaktor")
    if f <= 1:
        raise PrepError("Verdünnungsfaktor muss grösser als 1 sein (1:10 = 10)")
    n = int(_num(steps, "Stufen"))
    if not 1 <= n <= 30:
        raise PrepError("1 bis 30 Stufen")
    reps = int(_num(replicates, "Wiederholungen"))
    if reps < 1:
        raise PrepError("Mindestens eine Wiederholung")
    keep = volume_L(V_final, V_unit) * reps
    rows = [None] * n
    carry = 0.0                                          # Volumen, das die nächste Stufe aus dieser entnimmt
    for i in range(n - 1, -1, -1):
        total = keep + carry
        transfer = total / f
        rows[i] = {"step": i + 1, "c": tg["value"] / f ** (i + 1), "total_mL": total * 1000,
                   "transfer_mL": transfer * 1000, "fill_to_mL": total * 1000, "keep_mL": keep * 1000,
                   "diluent_approx_mL": (total - transfer) * 1000}
        carry = transfer
    notes = [f"Aus der Ausgangslösung werden {rows[0]['transfer_mL']:.4g}".replace(".", ",") + " mL gebraucht."]
    notes.append("Jede Stufe auf das angegebene Gesamtvolumen auffüllen; das Lösungsmittelvolumen ist nur ungefähr "
                 "(Volumina sind nicht streng additiv).")
    if min_pipette_uL:
        mp = _num(min_pipette_uL, "kleinstes Pipettiervolumen")
        small = [r["step"] for r in rows if r["transfer_mL"] * 1000 < mp]
        if small:
            notes.append(f"Übertrag unter {mp:g} µL in Stufe {', '.join(map(str, small))}: grösseres Volumen oder "
                         "kleineren Faktor wählen.")
    return {"c0": tg["value"], "unit": unit, "factor": f, "rows": rows, "replicates": reps, "notes": notes,
            "stock_needed_mL": rows[0]["transfer_mL"], "refs": ["harris"]}


def mix_solve(parts: list[dict], c_final=None, V_final=None) -> dict:
    """Stoffbilanz Σ cᵢ·Vᵢ = c·V für eine Spezies; genau ein Wert (ein cᵢ, ein Vᵢ, c oder V) darf fehlen (None) und
    wird berechnet. Volumen in mL, Konzentrationen in einer gemeinsamen linearen Einheit. V ist das aufgefüllte
    Endvolumen (nicht die Summe der Vᵢ)."""
    vals = [("c", i, p.get("c")) for i, p in enumerate(parts)] + [("V", i, p.get("V")) for i, p in enumerate(parts)]
    vals += [("cf", None, c_final), ("Vf", None, V_final)]
    missing = [v for v in vals if v[2] in (None, "")]
    if len(missing) != 1:
        raise PrepError("Genau ein Wert muss offen sein (leer lassen), alle anderen angeben")
    num = {(k, i): _num(v, "Wert") for k, i, v in vals if v not in (None, "")}
    for (k, i), x in num.items():
        if x < 0 or (k in ("V", "Vf") and x == 0):
            raise PrepError("Volumina > 0, Konzentrationen ≥ 0")
    k, i, _ = missing[0]
    n_parts = lambda skip=None: sum(num[("c", j)] * num[("V", j)] for j in range(len(parts)) if j != skip)  # noqa: E731
    if k == "cf":
        x = n_parts() / num[("Vf", None)]
    elif k == "Vf":
        if num[("cf", None)] <= 0:
            raise PrepError("Endkonzentration muss grösser als 0 sein")
        x = n_parts() / num[("cf", None)]
        if x < sum(num[("V", j)] for j in range(len(parts))) * (1 - 1e-12):
            raise PrepError("Das Endvolumen wäre kleiner als die Summe der Anteile")
    elif k == "c":
        if num[("V", i)] <= 0:
            raise PrepError("Volumen des gesuchten Anteils fehlt")
        x = (num[("cf", None)] * num[("Vf", None)] - n_parts(i)) / num[("V", i)]
    else:
        if num[("c", i)] <= 0:
            raise PrepError("Konzentration des gesuchten Anteils muss grösser als 0 sein")
        x = (num[("cf", None)] * num[("Vf", None)] - n_parts(i)) / num[("c", i)]
    if x < 0:
        raise PrepError("Keine Lösung: der gesuchte Wert wäre negativ")
    if k in ("V", "Vf") and x == 0:
        raise PrepError("Keine Lösung: das gesuchte Volumen wäre 0")
    out_parts = [{"c": num.get(("c", j)), "V": num.get(("V", j))} for j in range(len(parts))]
    res = {"parts": out_parts, "c_final": num.get(("cf", None)), "V_final": num.get(("Vf", None)),
           "solved": {"what": k, "index": i, "value": x}}
    if k in ("c", "V"):
        res["parts"][i][k] = x
    else:
        res["c_final" if k == "cf" else "V_final"] = x
    vf = res["V_final"]
    res["balance"] = {"n_parts": sum(p["c"] * p["V"] for p in res["parts"]), "n_final": res["c_final"] * vf}
    res["fill_mL"] = vf - sum(p["V"] for p in res["parts"])
    res["notes"] = ["Auf das Endvolumen auffüllen; die Differenz zur Summe der Anteile ist nur ungefähr das "
                    "Lösungsmittelvolumen."]
    res["refs"] = ["harris"]
    return res


def mix(parts: list[dict], V_final) -> dict:
    """Mehrere Stammlösungen mit je mehreren Spezies (parts = [{V, species: {name: c}}]) auf V_final (mL): Konzentration
    jeder Spezies in der Mischung."""
    vf = _num(V_final, "Endvolumen")
    if vf <= 0:
        raise PrepError("Endvolumen muss grösser als 0 sein")
    tot, Vsum = {}, 0.0
    for p in parts:
        V = _num(p.get("V"), "Volumen")
        if V <= 0:
            raise PrepError("Volumen jedes Anteils muss grösser als 0 sein")
        Vsum += V
        for sp, c in (p.get("species") or {}).items():
            tot[sp] = tot.get(sp, 0.0) + _num(c, f"Konzentration {sp}") * V
    if Vsum > vf * (1 + 1e-12):
        raise PrepError("Summe der Anteile ist grösser als das Endvolumen")
    return {"species": {sp: n / vf for sp, n in tot.items()}, "V_final": vf, "fill_mL": vf - Vsum, "refs": ["harris"],
            "notes": ["Auf das Endvolumen auffüllen (nicht die Volumina addieren)."]}


# ----------------------------------------------------------------------------- ER-L08 Pufferrezept
def _anhydrous(text: str) -> str:
    """Formel ohne Kristallwasser für die Säure-Base-Rechnung (das Hydratwasser ändert den pH nicht)."""
    return re.sub(r"\s*[·*•.]\s*\d*(?:[.,]\d+)?\s*H2O\b", "", text.strip())


def _bisect(fn, lo, hi, target, rising=True, it=60):
    for _ in range(it):
        mid = (lo + hi) / 2
        if (fn(mid) < target) == rising:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def register_calc_functions():
    """Laborrechnungen als Rechner-Funktionen (ER-L09, Q15 = a). Der Rechner übergibt Grössen in SI
    (c in mol/m³, V in m³, ρ in kg/m³, T in K, p in Pa); Ergebnisse ebenfalls in SI."""
    from . import expr as E
    from . import units as U
    from . import chem as C

    def _s(x, fn):
        return C._str_arg(x, fn)

    def m_prep(ctx, sub, c, V, basis=None):
        r = from_solid(_s(sub, "m_prep"), float(c) / 1000, "mol/L", float(V) * 1000, "L",
                       basis=_s(basis, "m_prep") if basis is not None else None)
        return r["mass_g"] / 1000

    def V_reag(ctx, sub, w, rho, c, V):
        w, rho = float(w), float(rho)
        if not 0 < w <= 1:
            raise PrepError("V_reag: Massenanteil w zwischen 0 und 1 (37 % = 0,37)")
        if rho <= 0:
            raise PrepError("V_reag: Dichte muss grösser als 0 sein")
        M = form(_s(sub, "V_reag"))["M"] / 1000                     # kg/mol
        return float(c) * float(V) * M / w / rho

    def m_buf(ctx, acid, base, pH, c, V, i=1):
        k = int(i)
        if k not in (1, 2):
            raise PrepError("m_buf: i = 1 (Säureform) oder 2 (Basenform)")
        r = buffer_recipe(float(pH), float(c) / 1000, float(V) * 1000, "L", acid=_s(acid, "m_buf"),
                          base=_s(base, "m_buf"))
        return r["parts"][k - 1]["mass_g"] / 1000

    def rho_gas(ctx, f, T, p):
        from . import gas as G
        return G.density(_s(f, "rho_gas"), float(T), float(p), "K", "Pa")["rho_g_L"]   # g/L = kg/m³

    def AE(ctx, eq, product):
        from . import reaction_setup as RS
        e, coefs = RS._balanced(_s(eq, "AE"))
        want = _s(product, "AE").strip()
        wf = C.parse_species(want).formula
        ms = [C.molar_mass(t.species)["M"] for t in e.terms]
        hit = [i for i, t in enumerate(e.terms) if t.side > 0 and t.species.formula == wf]
        if not hit:
            raise PrepError(f"AE: {want} ist kein Produkt der Gleichung")
        den = sum(coefs[i] * ms[i] for i, t in enumerate(e.terms) if t.side < 0)
        return coefs[hit[0]] * ms[hit[0]] / den

    E.register_string_function("m_prep", m_prep, 3, 4, U.kind_dims("mass"),
                               'm_prep("CuSO4·5H2O", 0,1 mol/L, 250 mL) – Einwaage für eine Lösung (Hydratwasser, '
                               'molare Massen CIAAW); 4. Argument Bezug, z. B. "Cu"')
    E.register_string_function("V_reag", V_reag, 5, 5, U.kind_dims("volume"),
                               'V_reag("HCl", 0,37, 1,18 g/mL, 1 mol/L, 1 L) – Volumen eines Reagenzes mit Massenanteil w '
                               'und Dichte ρ (Quelle der Dichte angeben); danach auffüllen')
    E.register_string_function("m_buf", m_buf, 5, 6, U.kind_dims("mass"),
                               'm_buf("NaH2PO4·H2O", "Na2HPO4·2H2O", 7,4, 0,1 mol/L, 1 L, i) – Einwaage der Säure- (i = 1) '
                               'bzw. Basenform (i = 2) eines Puffers, exakte Protonenbilanz bei 25 °C')
    E.register_string_function("rho_gas", rho_gas, 3, 3, U.kind_dims("density"),
                               'rho_gas("N2", 273,15 K, 101325 Pa) – Dichte eines idealen Gases pM/(RT)')
    E.register_string_function("AE", AE, 2, 2, U.D0,
                               'AE("CH4 + O2 -> CO2 + H2O", "CO2") – Atomökonomie (Trost 1991) der ausgeglichenen Gleichung')


def buffer_recipe(pH, c_total, V, V_unit: str = "mL", acid: str | None = None, base: str | None = None,
                  form_: str | None = None, titrant: str | None = None, titrant_stock=None, T_C: float = 25.0,
                  purity: dict | None = None) -> dict:
    """Pufferrezept aus vorhandenen Chemikalien, exakt über die Protonenbilanz (labcalc.acidbase):
    - zwei Formen: acid (protonierter, z. B. NaH2PO4·H2O) + base (z. B. Na2HPO4·2H2O), Summe c_total;
    - eine Form + Titrant: form_ (z. B. Tris) mit c_total, eingestellt mit titrant (z. B. HCl) aus titrant_stock
      ({value, unit, density}) – Volumen der Massslösung.
    Ergebnis mit Einwaagen, Volumen, Kontroll-pH und Ionenstärke."""
    from . import acidbase as AB
    target_pH = _num(pH, "Ziel-pH")
    c = _num(c_total, "Pufferkonzentration")
    if c <= 0:
        raise PrepError("Pufferkonzentration muss grösser als 0 sein")
    V_L = volume_L(V, V_unit)
    pur = purity or {}
    sh = Sheet()
    if acid and base:
        a, b = _anhydrous(acid), _anhydrous(base)

        def ph_at(f):
            return AB.ph([(a, c * (1 - f)), (b, c * f)], T_C)["pH"]
        lo, hi = ph_at(1e-9), ph_at(1 - 1e-9)
        if not lo <= target_pH <= hi:
            raise PrepError(f"Mit {acid} und {base} sind bei {c:g} mol/L nur pH {lo:.2f} bis {hi:.2f} erreichbar"
                            .replace(".", ","))
        f = _bisect(ph_at, 1e-9, 1 - 1e-9, target_pH)
        check = AB.ph([(a, c * (1 - f)), (b, c * f)], T_C)
        parts = []
        for txt, cc in ((acid, c * (1 - f)), (base, c * f)):
            fm = form(txt)
            pu = _purity(pur.get(txt))
            m = cc * V_L * fm["M"] / pu
            sh.add(f"{fm['formula']}", f"c = {cc:.5g} mol/L; m = c·V·M{'/Reinheit' if pu < 1 else ''} = {cc:.5g} · "
                   f"{V_L:g} · {fm['M']:.6g}", m, "g", "ciaaw2024")
            parts.append({"substance": fm["formula"], "c": cc, "mass_g": m, "M": fm["M"], "purity": pu})
        mode = "pair"
        titr = None
    elif form_ and titrant:
        a, t = _anhydrous(form_), _anhydrous(titrant)
        sys_cap = 3 * c

        def ph_at(ct):
            return AB.ph([(a, c), (t, ct)], T_C)["pH"]
        p0, p1 = ph_at(0.0), ph_at(sys_cap)
        rising = p1 > p0
        if not min(p0, p1) <= target_pH <= max(p0, p1):
            raise PrepError(f"Mit {titrant} ist pH {target_pH:g} nicht erreichbar (ohne Titrant pH {p0:.2f})"
                            .replace(".", ","))
        ct = _bisect(ph_at, 0.0, sys_cap, target_pH, rising)
        check = AB.ph([(a, c), (t, ct)], T_C)
        fm = form(form_)
        pu = _purity(pur.get(form_))
        m = c * V_L * fm["M"] / pu
        sh.add(fm["formula"], f"m = c·V·M = {c:g} · {V_L:g} · {fm['M']:.6g}", m, "g", "ciaaw2024")
        parts = [{"substance": fm["formula"], "c": c, "mass_g": m, "M": fm["M"], "purity": pu}]
        n_t = ct * V_L
        titr = {"substance": titrant, "c_in_buffer": ct, "n_mol": n_t}
        if titrant_stock:
            cs = stock_molarity(titrant_stock, form(titrant)["M"], sh, form(titrant)["formula"])
            titr["V_mL"] = sh.add(f"Volumen {titrant}-Lösung", f"V = n/c = {n_t:.5g} mol / {cs:.5g} mol/L",
                                  n_t / cs * 1000, "mL")
        mode = "titrant"
    else:
        raise PrepError("Entweder zwei Formen (Säure- und Basenform) oder eine Form mit Titrant angeben")
    notes = [f"Kontrolle mit der Protonenbilanz: pH {check['pH']:.3f}, Ionenstärke {check['I']:.3g} mol/L."
             .replace(f"{check['pH']:.3f}", f"{check['pH']:.3f}".replace(".", ","))
             .replace(f"{check['I']:.3g}", f"{check['I']:.3g}".replace(".", ",")),
             "Rechnung mit Konzentrationen statt Aktivitäten: bei dieser Ionenstärke weicht der gemessene pH ab; "
             "mit dem pH-Meter nachstellen."]
    notes += [n for n in check.get("notes") or [] if "Ionenstärke" not in n]
    sh.add(f"Ansetzen: lösen{', Titrant zugeben' if titr else ''}, pH mit pH-Meter prüfen, auf {V_L * 1000:g} mL auffüllen",
           "", None, "")
    return {"mode": mode, "pH": target_pH, "c_total": c, "V_L": V_L, "parts": parts, "titrant": titr,
            "check": {"pH": check["pH"], "I": check["I"], "species": check["species"]}, "T_C": T_C,
            "steps": sh.steps, "notes": notes, "refs": ["harris", "ciaaw2024"] + check["refs"][2:]}


# ----------------------------------------------------------------------------- ER-L03 Flüssigreagenz/Stammlösung
def stock_molarity(stock: dict, M_basis: float, sheet: Sheet, label: str) -> float:
    """Stoffmengenkonzentration der Bezugsspezies in der Stammlösung (mol/L).
    stock = {value, unit, density?}: unit wie BASES; Massenanteil braucht die Dichte des Reagenzes."""
    tg = target(stock.get("value"), stock.get("unit") or "mol/L")
    k, x = tg["kind"], tg["x"]
    if k == "molar":
        return sheet.add(f"c({label}) der Stammlösung", "angegeben", x, "mol/L", _src_text(stock.get("source") or ""))
    if k == "mass":
        return sheet.add(f"c({label}) der Stammlösung", f"c = β/M = {x:g} g/L / {M_basis:.6g} g/mol", x / M_basis,
                         "mol/L", _src_text(stock.get("source") or ""))
    if k == "wv":
        return sheet.add(f"c({label}) der Stammlösung", f"c = {x * 1000:g} g/L / {M_basis:.6g} g/mol",
                         x * 1000 / M_basis, "mol/L")
    if k == "w":
        rho = density(stock.get("density"))
        if rho is None:
            raise PrepError("Für ein Reagenz mit Massenanteil wird seine Dichte gebraucht (mit Quelle und "
                            "Temperatur), z. B. aus dem Datenblatt; sie wird nicht angenommen")
        return sheet.add(f"c({label}) der Stammlösung", f"c = w·ρ/M = {x:g} · {rho['g_mL'] * 1000:g} g/L / "
                         f"{M_basis:.6g} g/mol", x * rho["g_mL"] * 1000 / M_basis, "mol/L", _src_text(rho["source"]))
    raise PrepError("Molalität als Angabe der Stammlösung: bitte als Massenanteil oder mol/L mit Dichte angeben")


def from_stock(substance: str, stock: dict, value, unit: str, V, V_unit: str = "mL", basis: str | None = None,
               rho_solution=None) -> dict:
    """Aliquot einer Stammlösung bzw. eines flüssigen Reagenzes (auch zertifizierter Standard, z. B. 1000 mg/L Cu)
    für das Endvolumen. c₁V₁ = c₂V₂ gilt nur für Stoffmengen- bzw. Massenkonzentrationen; aufgefüllt wird immer."""
    sh = Sheet()
    f = form(substance)
    b = form(basis) if basis and basis.strip() else f
    k = per_unit(f, b) if b is not f else 1.0
    V_L = volume_L(V, V_unit)
    tg = target(value, unit)
    if b is not f:
        sh.add(f"{b['formula']} je Formeleinheit {f['formula']}", "aus der Formel", k, "")
    stock_basis = stock.get("basis") or "form"            # Konzentrationsangabe der Stammlösung: Form oder Bezug
    if stock_basis == "form":
        c_f = stock_molarity(stock, f["M"], sh, f["formula"])
        c_b = sh.add(f"c({b['formula']}) der Stammlösung", f"c = {k:g} · c({f['formula']})", c_f * k, "mol/L") \
            if b is not f else c_f
    else:
        c_b = stock_molarity(stock, b["M"], sh, b["formula"])
    n_b = basis_moles(tg, V_L, b["M"], sh, density(rho_solution), b["formula"])
    if c_b * V_L < n_b * (1 - 1e-12):
        raise PrepError("Die Stammlösung ist zu verdünnt für diese Zielkonzentration")
    V1 = sh.add("Volumen Stammlösung", f"V₁ = n/c = {n_b:.6g} mol / {c_b:.6g} mol/L", n_b / c_b, "L")
    out = {"form": f, "basis": b, "V_L": V_L, "n_basis": n_b, "c_stock": c_b, "V_stock_L": V1, "V_stock_mL": V1 * 1000,
           "target": tg, "dilution": c_b * V_L / n_b, "notes": []}
    rho = density(stock.get("density"))
    if rho:
        out["m_stock_g"] = sh.add("Masse Stammlösung (alternativ wägen)", f"m = ρ·V₁ = {rho['g_mL']:g} g/mL · "
                                  f"{V1 * 1000:.6g} mL", rho["g_mL"] * V1 * 1000, "g", _src_text(rho["source"]))
    if V1 * 1000 < 0.01:
        out["notes"].append("Aliquot unter 10 µL: lieber eine Zwischenverdünnung ansetzen.")
    sh.add(f"Ansetzen: {V1 * 1000:.4g} mL Stammlösung in einen Messkolben geben und auf {V_L * 1000:g} mL auffüllen",
           "", None, "")
    out["notes"].append("Volumina sind nicht additiv: nicht Stammlösung + Wasser addieren, sondern auffüllen.")
    if tg["kind"] in ("w", "b"):
        out["notes"].append("Ziel als Massenanteil bzw. Molalität: c₁V₁ = c₂V₂ gilt dafür nicht; gerechnet über die "
                            "Masse der fertigen Lösung (Dichte angegeben).")
    out["steps"] = sh.steps
    out["refs"] = REFS
    return out
