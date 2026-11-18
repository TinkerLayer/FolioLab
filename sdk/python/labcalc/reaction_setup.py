"""Reaktionsansatz und Skalierung (Ticket ER-L05).

Aus der ausgeglichenen Gleichung entsteht eine Reagenzientabelle: Rolle, Äquivalente, Form, Reinheit, Stammlösung
oder Dichte (reine Flüssigkeit) -> Stoffmenge, Masse, Volumen. Lösungsmittel, Katalysatoren und Zusätze stehen in
derselben Tabelle, gehen aber nicht in die Stöchiometrie ein. Beobachtete Massen und die isolierte Ausbeute stehen
neben dem Plan und ändern ihn nie. Skalieren multipliziert die Bezugsmenge und absolute Mengen, nie die Äquivalente.
"""
from __future__ import annotations

import copy

from . import chem as C
from . import prep as P

AMOUNT_UNITS = {"mol": ("n", 1.0), "mmol": ("n", 1e-3), "µmol": ("n", 1e-6), "g": ("m", 1.0), "mg": ("m", 1e-3),
                "kg": ("m", 1e3)}
ROLES = ("reactant", "reagent", "solvent", "catalyst", "additive")
REFS = ["ciaaw2024", "harris"]


class SetupError(C.ChemError):
    pass


def _amount_mol(a: dict, M: float | None, what: str) -> float:
    u = a.get("unit") or "mmol"
    if u not in AMOUNT_UNITS:
        raise SetupError(f"{what}: Einheit „{u}“ (mol, mmol, µmol, g, mg)")
    kind, f = AMOUNT_UNITS[u]
    x = P._num(a.get("value"), what) * f
    if x <= 0:
        raise SetupError(f"{what}: Menge muss grösser als 0 sein")
    if kind == "n":
        return x
    if not M:
        raise SetupError(f"{what}: keine molare Masse")
    return x / M


def _balanced(equation: str):
    eq = C.parse_equation(equation)
    b = C.balance(eq)
    if b.get("status") not in ("ok", "given_ok"):
        raise SetupError("Gleichung lässt sich nicht eindeutig ausgleichen")
    return eq, [float(c) for c in b["coefs"]]


def plan(equation: str, reference: dict, reagents: dict | None = None, extras: list | None = None,
         target: dict | None = None, conditions: dict | None = None, observed: dict | None = None) -> dict:
    """reference = {i, value, unit}: Bezugsstoff (Edukt, 1 Äquiv.) und seine Menge.
    target = {i, value, unit, yield_pct}: statt Bezugsmenge eine gewünschte Produktmenge (mit erwarteter Ausbeute).
    reagents = {i: {role, equiv, purity, stock:{value, unit, density, basis}, density:{…}}} für Gleichungsstoffe.
    extras = [{name, role, value, unit (mL, g, mol%, mol/L)}] – Lösungsmittel, Katalysator, Zusatz (ohne Stöchiometrie).
    observed = {"masses": {i: g}, "extras": {name: g}}: neben dem Plan, ändert ihn nicht."""
    eq, coefs = _balanced(equation)
    terms = eq.terms
    reagents = {int(k): v for k, v in (reagents or {}).items()}
    Ms = []
    for t in terms:
        try:
            Ms.append(C.molar_mass(t.species)["M"])
        except C.ChemError:
            Ms.append(None)
    reac = [i for i, t in enumerate(terms) if t.side < 0]
    prods = [i for i, t in enumerate(terms) if t.side > 0]
    sh = P.Sheet()
    if target:
        k = int(target["i"])
        if k not in prods:
            raise SetupError("Zielstoff muss ein Produkt sein")
        y = P._num(target.get("yield_pct") or 100, "erwartete Ausbeute") / 100
        if not 0 < y <= 1:
            raise SetupError("Erwartete Ausbeute zwischen 0 und 100 %")
        n_t = _amount_mol(target, Ms[k], "Zielmenge")
        ref_i = int((reference or {}).get("i", reac[0]))
        if ref_i not in reac:
            raise SetupError("Bezugsstoff muss ein Edukt sein")
        xi = sh.add("Umsatzvariable aus der Zielmenge", f"ξ = n(Ziel)/(ν·Ausbeute) = {n_t:.6g} mol / "
                    f"({coefs[k]:g}·{y:g})", n_t / (coefs[k] * y), "mol")
        n_ref = xi * coefs[ref_i]
    else:
        ref_i = int(reference["i"])
        if ref_i not in reac:
            raise SetupError("Bezugsstoff muss ein Edukt sein")
        n_ref = _amount_mol(reference, Ms[ref_i], "Bezugsmenge")
        xi = sh.add("Umsatzvariable", f"ξ = n(Bezug)/ν = {n_ref:.6g} mol / {coefs[ref_i]:g}", n_ref / coefs[ref_i],
                    "mol")
    rows = []
    for i in reac:
        r = reagents.get(i, {})
        role = r.get("role") or "reactant"
        if role not in ("reactant", "reagent"):
            raise SetupError("Stoffe der Gleichung sind Edukt oder Reagenz; Lösungsmittel usw. als Zusatz angeben")
        eqv = 1.0 if i == ref_i else P._num(r.get("equiv") or 1, "Äquivalente")
        if eqv <= 0:
            raise SetupError("Äquivalente müssen grösser als 0 sein")
        n = eqv * coefs[i] * xi
        pu = P._purity(r.get("purity"))
        row = {"i": i, "species": terms[i].species.unicode(), "role": role, "nu": coefs[i], "equiv": eqv, "M": Ms[i],
               "n_mol": n, "purity": pu, "ref": i == ref_i}
        if Ms[i]:
            row["m_g"] = n * Ms[i] / pu
        if r.get("stock"):
            c = P.stock_molarity(r["stock"], Ms[i] or 1, P.Sheet(), row["species"])
            row["V_mL"] = n / c * 1000
            row["how"] = "Stammlösung"
        elif r.get("density"):
            rho = P.density(r["density"])
            if "m_g" not in row:
                raise SetupError(f"{row['species']}: keine molare Masse für das Volumen")
            row["V_mL"] = row["m_g"] / rho["g_mL"]
            row["how"] = "rein, abgemessen"
            row["density_source"] = rho["source"]
        rows.append(row)
    lim = min(rows, key=lambda r: r["n_mol"] / r["nu"])
    xi_lim = lim["n_mol"] / lim["nu"]
    for r in rows:
        r["excess_mol"] = r["n_mol"] - r["nu"] * xi_lim
        r["limiting"] = r is lim
    prod_rows = []
    for i in prods:
        n = coefs[i] * xi_lim
        prod_rows.append({"i": i, "species": terms[i].species.unicode(), "role": "product", "nu": coefs[i], "M": Ms[i],
                          "n_theor_mol": n, "m_theor_g": n * Ms[i] if Ms[i] else None})
    ext_rows = []
    for e in extras or []:
        role = e.get("role") or "solvent"
        if role not in ("solvent", "catalyst", "additive"):
            raise SetupError("Zusätze: Lösungsmittel, Katalysator oder Zusatz")
        u = e.get("unit") or ("mL" if role == "solvent" else "mol%")
        x = P._num(e.get("value"), f"Menge {e.get('name') or role}")
        if x <= 0:
            raise SetupError(f"Menge {e.get('name') or role} muss grösser als 0 sein")
        row = {"name": e.get("name") or role, "role": role, "value": x, "unit": u, "in_stoichiometry": False}
        if u == "mol%":
            row["n_mol"] = x / 100 * n_ref
            if e.get("formula"):
                row["m_g"] = row["n_mol"] * P.form(e["formula"])["M"]
        elif u == "mol/L":                                # Lösungsmittelmenge über die Konzentration des Bezugs
            row["V_mL"] = n_ref / x * 1000
        elif u in P.VOL:
            row["V_mL"] = x * P.VOL[u] * 1000
            row["absolute"] = True
        elif u in P.MASS:
            row["m_g"] = x * P.MASS[u]
            row["absolute"] = True
        else:
            raise SetupError(f"Einheit „{u}“ für Zusätze (mL, L, g, mg, mol%, mol/L)")
        if e.get("density") and "V_mL" in row:
            row["m_g"] = row["V_mL"] * P.density(e["density"])["g_mL"]
        ext_rows.append(row)
    out = {"equation": equation, "coefs": coefs, "xi": xi, "xi_limiting": xi_lim, "reference": ref_i,
           "reactants": rows, "products": prod_rows, "extras": ext_rows, "limiting": lim["i"],
           "conditions": dict(conditions or {}), "steps": sh.steps, "refs": REFS,
           "notes": ["Lösungsmittel, Katalysatoren und Zusätze gehen nicht in die Stöchiometrie ein."]}
    if observed:
        obs = {}
        for k, m in (observed.get("masses") or {}).items():
            k = int(k)
            mg = P._num(m, "beobachtete Masse")
            pr = next((p for p in prod_rows if p["i"] == k), None)
            rr = next((r for r in rows if r["i"] == k), None)
            if pr and pr["m_theor_g"]:
                obs[k] = {"m_g": mg, "yield": mg / pr["m_theor_g"], "kind": "product"}
            elif rr:
                obs[k] = {"m_g": mg, "planned_g": rr.get("m_g"), "kind": "reactant"}
        out["observed"] = obs
    return out


# ----------------------------------------------------------------------------- ER-L06 Grüne Kennzahlen
METRIC_REFS = ["sheldon2007", "constable2002", "jimenez2011", "trost1991"]
BOUNDARY_DEFAULT = {"reagents": True, "solvents": True, "catalyst": True, "additives": True, "workup": True}
BOUNDARY_TEXT = {"reagents": "Edukte und Reagenzien", "solvents": "Lösungsmittel", "catalyst": "Katalysator",
                 "additives": "Zusätze", "workup": "Aufarbeitung und Reinigung"}


def metrics(p: dict, boundary: dict | None = None, workup: list | None = None, product_i: int | None = None,
            basis: str = "observed") -> dict:
    """E-Faktor (Sheldon 2007), Reaktionsmasseneffizienz RME (Constable et al. 2002), Prozessmassenintensität PMI
    (Jimenez-Gonzalez et al. 2011), Lösungsmittelanteil, Atomökonomie (Trost 1991). Die Zählgrenze wird gewählt und
    mit jedem Wert ausgegeben. Produktmasse: beobachtet (falls vorhanden und basis = observed) oder theoretisch."""
    bd = {**BOUNDARY_DEFAULT, **(boundary or {})}
    prods = p["products"]
    pr = next((x for x in prods if x["i"] == product_i), None) if product_i is not None else (prods[0] if prods else None)
    if pr is None:
        raise SetupError("Kein Produkt")
    obs = (p.get("observed") or {}).get(pr["i"])
    if basis == "observed" and obs:
        m_prod, prod_basis = obs["m_g"], "isoliert"
    else:
        if not pr.get("m_theor_g"):
            raise SetupError("Keine Produktmasse")
        m_prod, prod_basis = pr["m_theor_g"], "theoretisch (100 % Ausbeute)"
    parts = []
    for r in p["reactants"]:
        if "m_g" not in r:
            raise SetupError(f"{r['species']}: keine Masse")
        if r["role"] == "reagent" and not bd["reagents"]:
            continue
        parts.append(("reactant" if r["role"] == "reactant" else "reagent", r["species"], r["m_g"]))
    key = {"solvent": "solvents", "catalyst": "catalyst", "additive": "additives"}
    for e in p["extras"]:
        if not bd[key[e["role"]]]:
            continue
        if "m_g" not in e:
            raise SetupError(f"{e['name']}: Masse fehlt (für Volumen bitte die Dichte mit Quelle angeben); sonst "
                             f"„{BOUNDARY_TEXT[key[e['role']]]}“ aus der Zählgrenze nehmen")
        parts.append((e["role"], e["name"], e["m_g"]))
    if bd["workup"]:
        for w in workup or []:
            parts.append(("workup", w.get("name") or "Aufarbeitung", P._num(w.get("m_g"), "Masse Aufarbeitung")))
    m_in = sum(m for _, _, m in parts)
    m_stoich = sum(r["m_g"] for r in p["reactants"])          # RME: alle Gleichungsedukte (inkl. Überschuss)
    m_solv = sum(m for k, _, m in parts if k == "solvent")
    n_reac_M = sum(r["nu"] * r["M"] for r in p["reactants"] if r.get("M"))
    ae = pr["nu"] * pr["M"] / n_reac_M if pr.get("M") and n_reac_M else None
    E = (m_in - m_prod) / m_prod
    return {"product": pr["species"], "m_product_g": m_prod, "product_basis": prod_basis, "m_in_g": m_in,
            "E_factor": E, "PMI": m_in / m_prod, "RME": m_prod / m_stoich, "solvent_share": m_solv / m_in if m_in else 0,
            "atom_economy": ae, "parts": [{"kind": k, "name": n, "m_g": m} for k, n, m in parts],
            "boundary": bd, "boundary_text": "eingerechnet: " + ", ".join(BOUNDARY_TEXT[k] for k, v in bd.items() if v)
            + ("; nicht eingerechnet: " + ", ".join(BOUNDARY_TEXT[k] for k, v in bd.items() if not v)
               if not all(bd.values()) else ""),
            "notes": ["PMI = E-Faktor + 1 bei gleicher Zählgrenze; Wasser ist hier mitgezählt, wenn es als Zusatz oder "
                      "in der Aufarbeitung angegeben ist."], "refs": METRIC_REFS}


def compare(plans: list[dict], **kw) -> list[dict]:
    """Kennzahlen mehrerer Ansätze mit derselben Zählgrenze nebeneinander."""
    return [metrics(p, **kw) for p in plans]


def scale(inputs: dict, factor) -> dict:
    """Ansatz um factor vergrössern/verkleinern: Bezugs- bzw. Zielmenge und absolute Zusatzmengen (mL, g) werden
    multipliziert; Äquivalente, mol% und Konzentrationen bleiben."""
    f = P._num(factor, "Faktor")
    if f <= 0:
        raise SetupError("Faktor muss grösser als 0 sein")
    new = copy.deepcopy(inputs)
    for key in ("reference", "target"):
        if new.get(key) and new[key].get("value") not in (None, ""):
            new[key]["value"] = P._num(new[key]["value"], "Menge") * f
    for e in new.get("extras") or []:
        if (e.get("unit") or "") in list(P.VOL) + list(P.MASS):
            e["value"] = P._num(e["value"], "Menge") * f
    new.pop("observed", None)                               # Beobachtungen gehören zum alten Ansatz
    return new
