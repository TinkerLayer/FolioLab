"""Arbeitsstand -> Ergebnisse (Oberfläche, Bericht und Neuaufbau rechnen gleich).

state = {
  "equation": "C3H8 + O2 -> CO2 + H2O",
  "amounts": {"0": {"mass_g": 10}},          Mengen je Stoff (Index in der Gleichung)
  "actual": {"2": {"mass_g": 25}},           tatsächlich erhaltene Produktmengen (Ausbeute)
  "species": ["H2SO4", ...],                 einzelne Stoffe (Molmasse, Zusammensetzung)
  "empirical": {"fractions": {...}, "M": 180},  Elementaranalyse
  "detail": "steps" | "results",
  "thermo": {"T": 700, "choices": {"2": "nbs|H2O|g||"}},   Temperatur (Näherung) und gewählte Datensätze je Stoff
  "redox": {"activities": {"1": 0.01}, "pH": 3, "T": 298.15, "faraday": {"I": 2, "t": 3600}},   Nernst und Faraday
  "ph": {"mixture": "0,1 M CH3COOH; 0,1 M CH3COONa"},     pH-Rechner (Bericht)
  "titration": {"analyte": "0,1 M CH3COOH", "V0": 25, "titrant": "NaOH", "c": 0.1, "Vmax": 50},
}
"""
from __future__ import annotations

import math
import re
import sys
from fractions import Fraction
from pathlib import Path

_SDK = Path(__file__).resolve().parents[3] / "sdk" / "python"
if _SDK.is_dir() and str(_SDK) not in sys.path:
    sys.path.insert(0, str(_SDK))

from labcalc import chem as C  # noqa: E402


def collection_match(sp) -> dict:
    """Stoff der Gleichung in der Sammlung: per Name (aufgelöst) oder Summenformel; Isomere werden alle genannt."""
    from labcalc import substances as S
    if sp.name:
        k = S.resolve(sp.name)
        if k:
            return {"matches": [S.summary(k)], "match_by": "name"}
    try:
        hill = C.hill_formula(sp)
    except C.ChemError:
        return {"matches": []}
    keys = S._index()[1].get(hill, [])
    exact = [k for k in keys if (S.molecules()[k].get("formula") or "") == sp.text.split("(")[0].strip()]
    keys = exact + [k for k in keys if k not in exact]
    single_ion = len([e for e in sp.counts]) == 1 and (sp.charge or len(sp.counts) == 1)
    return {"matches": [S.summary(k) for k in keys[:6]], "n_matches": len(keys), "match_by": "formula",
            "simple": bool(single_ion)}


def species_card(text: str) -> dict:
    sp = C.parse_species(text)
    d = sp.to_dict()
    if sp.kind == "chem":
        mm = C.molar_mass(sp)
        d["molar_mass"] = mm
        d["hill"] = C.hill_formula(sp)
        dbe = C.unsaturation(sp)
        if dbe is not None:
            d["dbe"] = dbe
    return d


def thermo_result(eq, coefs, stoich=None, opts=None, key_hints=None) -> dict:
    """Thermochemie bei 298,15 K; andere Temperatur nur genähert (ΔrH°, ΔrS° konstant)."""
    from labcalc import thermo as TH
    opts = opts or {}
    try:
        T = float(opts.get("T") or TH.T0)
    except (TypeError, ValueError):
        T = TH.T0
    if not 1 <= T <= 6000:
        T = TH.T0
    r = TH.reaction(eq, coefs, T, opts.get("choices") or {}, key_hints)
    if r.get("dH") is not None:
        r["heat"] = TH.heat(r, stoich, eq, coefs)
    if r.get("dH") is not None and r.get("dS") is not None:
        ts = r.get("T_star")
        hi = max(1000.0, min(3000.0, 1.6 * ts)) if ts and ts > 0 else 1500.0
        if T > hi - 50:
            hi = min(6000.0, T * 1.3)
        r["curve"] = [[round(t, 2), round(g, 4)] for t, g in TH.dG_curve(r["dH"], r["dS"], 200.0, hi, 61)]
        # ER-701: mit Cp(T) (NASA-7, Burcat), Konstant-Näherung bleibt daneben stehen
        from labcalc import thermo_t as TT
        try:
            pts = TT.dG_points(eq, coefs, [t for t, _ in r["curve"]], opts.get("choices") or {}, key_hints)
            if pts:
                r["curve_cp"] = [[round(t, 2), round(g, 4)] for t, g in pts["points"]]
                r["curve_cp_model"] = pts["model"]
            if abs(T - TH.T0) > 0.01:
                r["cpT"] = TT.reaction_T(eq, coefs, T, opts.get("choices") or {}, key_hints)
        except C.ChemError as e:
            r["cpT_error"] = str(e)
    try:                                                                   # ER-X01: Schätzung aus Bindungsenthalpien
        from labcalc import bonds as BD
        r["bond_estimate"] = BD.estimate(eq, coefs)
    except Exception as e:  # noqa: BLE001 – Strukturen fehlen oft; nur Hinweis
        r["bond_estimate_error"] = str(e)
    return r


def equilibrium_call(r: dict) -> dict:
    """ER-702: Gleichgewichtslage einer Gleichung bei T, p (Gase) bzw. V (Lösung) ab Anfangsstoffmengen."""
    from labcalc import equilibrium as EQ
    from labcalc import thermo_t as TT
    eq = C.parse_equation(str(r.get("equation") or ""))
    bal = C.balance(eq)
    if not bal.get("coefs"):
        raise C.ChemError("Gleichung lässt sich nicht eindeutig ausgleichen")
    coefs = bal["coefs"]
    T = float(r.get("T") or 298.15)
    th = TT.reaction_T(eq, coefs, T, r.get("choices") or {})
    if th.get("error"):
        raise C.ChemError(th["error"])
    n0 = r.get("n0") or {}
    from fractions import Fraction
    species = []
    for row in th["species"]:
        i = row["i"]
        nu = float(Fraction(str(coefs[i]))) * eq.terms[i].side
        ph = {"cr": "cr", "l": "l", "g": "g", "aq": "aq"}.get(row.get("ph") or "", "g")
        v = n0.get(str(i), n0.get(i))
        species.append({"name": row["species"], "nu": nu, "phase": ph,
                        "n0": float(str(v).replace(",", ".")) if v not in (None, "") else (abs(nu) if nu < 0 else 0.0)})
    p = float(r.get("p") or 1.0)
    V = float(r["V"]) if r.get("V") not in (None, "") else None
    out = {"T": T, "p_bar": p, "lnK": th["lnK_T"], "lgK": th["lgK_T"], "model": th["model"], "refs": th["refs"],
           "thermo_notes": th["notes"]}
    q = EQ.quotient([{**s, "n": s["n0"]} for s in species], p, V)
    out["Q"] = q
    if q.get("lnQ") is not None:
        out["direction"] = EQ.direction(q["lnQ"], th["lnK_T"])
    out.update(EQ.solve(species, th["lnK_T"], p, V))
    return out


def _smiles_for(c: dict) -> str | None:
    """Struktur eines Gleichungsstoffs für Oxidationszahlen je Atom: nur wenn die Zuordnung eindeutig ist."""
    m = (c.get("matches") or [None])[0]
    if not m or not m.get("smiles"):
        return None
    if c.get("match_by") == "name" or c.get("n_matches") == 1 or (m.get("formula") or "") == c["text"].split("(")[0]:
        return m["smiles"]
    return None


def redox_result(eq, coefs, cards, thermo=None, opts=None) -> dict:
    """Oxidationszahlen, Elektronenbilanz, Halbreaktionen, E°, Nernst und Faraday (labcalc.redox)."""
    from labcalc import redox as RX
    opts = opts or {}
    smiles = {i: _smiles_for(c) for i, c in enumerate(cards) if c.get("kind") == "chem"}
    r = RX.analyse(eq, coefs, {i: s for i, s in smiles.items() if s})
    if r.get("half"):
        terms = [(t.species, float(Fraction(str(c))) * t.side) for t, c in zip(eq.terms, coefs)]
        h = RX.E_of_half(terms)
        r["E_half"] = {k: h.get(k) for k in ("E0", "n", "dG_red", "rows", "refs", "error")}
        r["couple"] = RX.couple_label(terms)
        E0, n = h.get("E0"), h.get("n")
    elif r.get("redox"):
        r["halves"] = RX.half_reactions(eq, coefs, r)
        hv = r["halves"]
        failed = lambda h, k: bool(h.get(k)) and not h[k].get("text")       # noqa: E731
        if failed(hv, "oxidation") or failed(hv, "reduction"):
            # Salze, Gegenionen: Halbreaktionen aus der Ionengleichung (Zn + CuSO₄ -> Zn + Cu²⁺ -> Zn²⁺ + Cu)
            ion = RX.ionic_form(eq, coefs, {i: s for i, s in smiles.items() if s})
            if ion and ion.get("text"):
                try:
                    eq2 = C.parse_equation(ion["text"])
                    b2 = C.balance(eq2)
                    c2 = [Fraction(str(c)) for c in b2["coefs"]]
                    h2 = RX.half_reactions(eq2, c2, RX.analyse(eq2, c2))
                    if h2.get("oxidation") and h2.get("reduction") and not failed(h2, "oxidation") \
                            and not failed(h2, "reduction"):
                        h2["from_ionic"] = ion["unicode"]
                        r["halves"] = h2
                except (C.ChemError, KeyError):
                    pass
        T = (thermo or {}).get("T") or RX.T0
        r["potential"] = RX.potentials(r, thermo, T)
        E0, n = r["potential"].get("E0"), r.get("n")
        # in Lösung massgeblich: E°(Kathode) − E°(Anode) aus den Halbreaktionen (wässrige Ionen); ΔrG° der Gleichung
        # wie geschrieben nutzt die Phasen der Thermochemie (z. B. HCl(g), Salze kristallin) und weicht dann ab
        if r["halves"].get("E0_cell_halves") is not None:
            E0 = r["halves"]["E0_cell_halves"]
            r["potential"]["E0_cell"] = E0
            r["potential"]["E0_src"] = "halves"
            r["potential"].setdefault("refs", RX.REFS_E)
            r["potential"].setdefault("n", n)
    else:
        return r
    if E0 is not None and n:
        try:
            T = float(opts.get("T") or (thermo or {}).get("T") or RX.T0)
            pH = opts.get("pH")
            r["nernst"] = RX.nernst(eq, coefs, E0, n, opts.get("activities") or {}, T,
                                    float(pH) if pH not in (None, "") else None)
        except (C.ChemError, ValueError) as e:
            r["nernst"] = {"error": str(e)}
    fa = opts.get("faraday") or {}
    if n and (fa.get("Q") not in (None, "") or (fa.get("I") not in (None, "") and fa.get("t") not in (None, ""))):
        try:
            eta = fa.get("eta")                                  # Prozent
            actual = {int(k): float(v) for k, v in (fa.get("actual") or {}).items() if v not in (None, "")}
            r["faraday"] = RX.faraday(eq, coefs, n, *(float(fa[k]) if fa.get(k) not in (None, "") else None
                                                     for k in ("Q", "I", "t")),
                                      eta=float(eta) / 100 if eta not in (None, "") else None, actual=actual,
                                      analysis=r)
        except (C.ChemError, ValueError) as e:
            r["faraday"] = {"error": str(e)}
    return r


def equation_result(text: str, amounts=None, actual=None, thermo=None, redox=None) -> dict:
    eq = C.parse_equation(text)
    res = C.balance(eq)
    res["input"] = text
    cards = []
    hints = {}
    for i, t in enumerate(eq.terms):
        sp = t.species
        c = {"text": sp.text, "unicode": sp.unicode(), "kind": sp.kind, "side": t.side}
        if sp.kind == "chem":
            try:
                c["M"] = C.molar_mass(sp)["M"]
                from . import uncert as UC                   # Runde U: u(M) nach Possolo et al. 2018 (Wertekatalog)
                c["M_u"] = UC.possolo_u(sp)["u"]
            except C.ChemError as e:
                c["M_error"] = str(e)
            except ValueError:
                pass
            c.update(collection_match(sp))
            if c.get("match_by") == "name" and c.get("matches"):
                hints[str(i)] = c["matches"][0]["key"]
        cards.append(c)
    res["cards"] = cards
    ok = res.get("status") in ("ok", "given_ok")
    chem_only = not res.get("nuclear") and all(t.species.kind in ("chem", "electron") for t in eq.terms)
    has_e = any(t.species.kind == "electron" for t in eq.terms)
    if not ok and chem_only:                            # Redox in Lösung: Ausgleich mit H⁺/H₂O bzw. OH⁻/H₂O anbieten
        from labcalc import redox as RX
        opts = [o for o in (RX.balance_in_medium(eq, m) for m in ("acid", "base")) if o]
        if opts:
            res["medium_options"] = opts
    if ok and amounts:
        try:
            res["stoich"] = C.stoichiometry(eq, res["coefs"], amounts, actual or None)
        except C.ChemError as e:
            res["stoich_error"] = str(e)
    if ok and chem_only and not has_e:
        try:
            res["thermo"] = thermo_result(eq, res["coefs"], res.get("stoich"), thermo, hints)
        except C.ChemError as e:
            res["thermo"] = {"error": str(e)}
    if ok and chem_only:
        from labcalc import rxtype as RT
        try:
            res["redox"] = redox_result(eq, [Fraction(str(c)) for c in res["coefs"]], cards, res.get("thermo"), redox)
        except C.ChemError as e:
            res["redox"] = {"error": str(e)}
        try:
            res["rtype"] = RT.classify(eq, res["coefs"], res.get("redox"))
        except C.ChemError:
            res["rtype"] = []
        if not has_e:
            from labcalc import redox as RX
            try:
                smi = {i: s for i, s in ((i, _smiles_for(c)) for i, c in enumerate(cards) if c.get("kind") == "chem") if s}
                ion = RX.ionic_form(eq, [Fraction(str(c)) for c in res["coefs"]], smi)
                if ion:
                    res["ionic"] = ion
            except C.ChemError:
                pass
    return res


PREP_KINDS = ("solid", "stock", "series", "mixsolve", "reaction", "gas", "buffer")


def prep_call(kind: str, r: dict) -> dict:
    """Eine Rechnung des Tabs „Ansetzen“ – gleiche Eingabe wie /api/prep/<kind>; Server und Bericht nutzen sie beide,
    damit der Bericht genau das rechnet, was die Seite zeigt. Mit ``unc`` (±-Angaben und Verfahren) kommt die
    Messunsicherheit der Ergebnisse dazu (``out["unc"]``, elementrechner.uncert)."""
    out = _prep_call(kind, r)
    if isinstance(r.get("unc"), dict) and isinstance(out, dict) and not r.get("terms_only"):
        from . import uncert as UC
        out["unc"] = UC.prep(kind, r, out, r.get("lang") if r.get("lang") in ("de", "en") else "de")
    return out


def _prep_call(kind: str, r: dict) -> dict:
    from labcalc import prep as PR
    if kind == "solid":
        comps = r.get("components") or []
        if len(comps) > 1:
            return PR.mixture(comps, r.get("V"), r.get("V_unit") or "mL", balance_d=r.get("balance_d") or None)
        c = comps[0] if comps else {}
        return PR.from_solid(str(c.get("substance") or ""), c.get("value"), c.get("unit") or "mol/L",
                             r.get("V"), r.get("V_unit") or "mL", basis=c.get("basis"),
                             purity=c.get("purity"), balance_d=r.get("balance_d") or None,
                             flask=bool(r.get("flask")), rho_solution=r.get("rho_solution"))
    if kind == "stock":
        return PR.from_stock(str(r.get("substance") or ""), r.get("stock") or {}, r.get("value"),
                             r.get("unit") or "mol/L", r.get("V"), r.get("V_unit") or "mL",
                             basis=r.get("basis"), rho_solution=r.get("rho_solution"))
    if kind == "series":
        return PR.series(r.get("c0"), r.get("unit") or "mol/L", r.get("factor"), r.get("steps") or 1,
                         r.get("V"), r.get("V_unit") or "mL", r.get("replicates") or 1, r.get("min_uL") or None)
    if kind == "mixsolve":
        return PR.mix_solve(r.get("parts") or [], r.get("c_final"), r.get("V_final"))
    if kind == "buffer":
        return PR.buffer_recipe(r.get("pH"), r.get("c"), r.get("V"), r.get("V_unit") or "mL",
                                acid=r.get("acid") or None, base=r.get("base") or None,
                                form_=r.get("form") or None, titrant=r.get("titrant") or None,
                                titrant_stock=r.get("stock") or None, T_C=float(r.get("T") or 25))
    if kind == "gas":
        from labcalc import gas as GA
        u = {k: r.get(k) for k in ("p_unit", "V_unit", "T_unit") if r.get(k)}
        out = {"ideal": None}
        vals = [r.get(k) for k in ("p", "V", "n", "T")]
        if sum(v in (None, "") for v in vals) == 1:
            out["ideal"] = GA.ideal(*vals, **u)
        if (r.get("formula") or "").strip() and r.get("T") not in (None, "") and r.get("p") not in (None, ""):
            out["density"] = GA.density(r["formula"].strip(), r["T"], r["p"], r.get("T_unit") or "°C",
                                        r.get("p_unit") or "kPa")
        if r.get("mix"):
            out["mixture"] = GA.mixture(r["mix"], r.get("p") or 101.325, r.get("p_unit") or "kPa", basis="x")
        return out
    if kind == "reaction":
        from labcalc import reaction_setup as RS
        eq, coefs = RS._balanced(str(r.get("equation") or ""))
        terms = [{"i": i, "species": t.species.unicode(), "side": t.side, "nu": coefs[i]} for i, t in enumerate(eq.terms)]
        if r.get("terms_only"):
            return {"terms": terms}
        inp = {k: r.get(k) for k in ("reference", "reagents", "extras", "target", "conditions", "observed")}
        if r.get("scale"):
            inp = RS.scale(inp, r["scale"])
        plan = RS.plan(str(r["equation"]), **inp)
        out = {"terms": terms, "plan": plan, "inputs": inp}
        if r.get("metrics"):
            try:
                out["metrics"] = RS.metrics(plan, boundary=r.get("boundary"), workup=r.get("workup"))
            except C.ChemError as e:
                out["metrics_error"] = str(e)
        return out
    raise C.ChemError(f"Unbekannte Ansetz-Rechnung „{kind}“")


NUC_KINDS = ("q", "binding", "equation", "decay", "chain", "dating", "pattern", "enriched")
KIN_KINDS = ("arrhenius", "eyring", "order", "sim", "flame")


def _series(s) -> list[str]:
    """Zahlenreihe aus Text (Zeilen, Semikolon oder Leerzeichen getrennt; Dezimalkomma erlaubt)."""
    if isinstance(s, (list, tuple)):
        return [str(x) for x in s if str(x).strip()]
    return [x for x in re.split(r"[;\s]+", str(s or "").strip()) if x]


def speciation_call(r: dict) -> dict:
    """ER-S02: Speziesverteilung Metall–Ligand über dem pH."""
    from labcalc import speciation as SP
    num = lambda v, d=None: float(str(v).replace(",", ".")) if v not in (None, "") else d   # noqa: E731
    out = SP.distribution(str(r.get("metal")).strip(), str(r.get("ligand")).strip(), num(r.get("c_M"), 0.001),
                          num(r.get("c_L")), num(r.get("pH_from"), 0.0), num(r.get("pH_to"), 14.0), 141)
    if out["ligand"].lower() in SP.HYDROXIDE:
        out["refs"] = out["refs"] + ["baes1976"]
    return out


def saturation_call(r: dict) -> dict:
    """ER-S03: Sättigungsindex aus Ionenkonzentrationen und Ksp."""
    from labcalc import speciation as SP
    num = lambda v, d=None: float(str(v).replace(",", ".")) if v not in (None, "") else d   # noqa: E731
    model = r.get("model") if r.get("model") in ("davies", "edh") else None
    return SP.saturation(str(r.get("salt") or "").strip(), str(r.get("cation") or "").strip(), num(r.get("c_cat"), 0),
                         str(r.get("anion") or "").strip(), num(r.get("c_an"), 0), num(r.get("I_extra"), 0.0), model)


def vapor_call(r: dict) -> dict:
    """ER-X03: Dampfdruck (Antoine), Siedepunkt bei p und kolligative Verschiebungen für ein Lösungsmittel."""
    from labcalc import vapor as VP
    num = lambda v, d=None: float(str(v).replace(",", ".")) if v not in (None, "") else d   # noqa: E731
    name = str(r.get("solvent") or "").strip()
    if not name:
        raise ValueError("Lösungsmittel fehlt")
    out = {"solvent": name, "notes": [], "refs": []}
    T = num(r.get("T_C"))
    if name and T is not None:
        out["pvap"] = VP.vapour_pressure(name, T + 273.15)
    p = num(r.get("p_bar"))
    if p is not None:
        out["bp"] = VP.boiling_point(name, p)
    b = num(r.get("b"))
    if b is not None:
        out["collig"] = VP.colligative(name, b, num(r.get("i"), 1.0))
    if not any(k in out for k in ("pvap", "bp", "collig")):
        raise ValueError("Temperatur, Druck oder Molalität angeben")
    for k in ("pvap", "bp", "collig"):
        if k in out:
            out["notes"] += [n for n in out[k]["notes"] if n not in out["notes"]]
            out["refs"] += [x for x in out[k]["refs"] if x not in out["refs"]]
    return out


def kinetics_call(kind: str, r: dict) -> dict:
    """ER-703/704: Kinetik-Auswertungen; Server und Bericht nutzen dieselbe Funktion."""
    from labcalc import kinetics as K
    if kind in ("arrhenius", "eyring"):
        T, k = _series(r.get("T")), _series(r.get("k"))
        if r.get("T_unit") == "C":
            T = [str(float(x.replace(",", ".")) + 273.15) for x in T]
        out = (K.arrhenius if kind == "arrhenius" else K.eyring)(T, k)
    elif kind == "order":
        c0 = r.get("c0")
        out = K.order_fit(_series(r.get("t")), _series(r.get("c")), r.get("data") or "c",
                          float(str(c0).replace(",", ".")) if c0 not in (None, "") else None)
    elif kind == "sim":
        p = dict(r.get("params") or {})
        if r.get("Ea") not in (None, "") and r.get("T") not in (None, ""):   # k(T) aus Eₐ mit Quelle
            if not (r.get("source") or "").strip():
                raise K.KineticsError("Für k aus Eₐ die Quelle von Eₐ angeben")
            num = lambda v: float(str(v).replace(",", "."))                  # noqa: E731
            kk = K.k_at(num(r["T"]), num(r["Ea"]), A=num(r["A"]) if r.get("A") not in (None, "") else None,
                        k_ref=num(r["k_ref"]) if r.get("k_ref") not in (None, "") else None,
                        T_ref=num(r["T_ref"]) if r.get("T_ref") not in (None, "") else None)
            p["k" if "k" in K.MODELS.get(r.get("model") or "1", ("", []))[1] else "k1"] = kk
        out = K.simulate(str(r.get("model") or "1"), p, r.get("t_end"))
        if r.get("source"):
            out["source"] = str(r["source"])
    elif kind == "flame":                                                  # ER-705
        from labcalc import flame as FL
        num = lambda v, d: float(str(v).replace(",", ".")) if v not in (None, "") else d   # noqa: E731
        out = FL.adiabatic(str(r.get("fuel") or "").strip(), num(r.get("phi"), 1.0), r.get("oxidant") or "air",
                           num(r.get("T0"), 298.15))
    else:
        raise ValueError("unbekannte Kinetik-Rechnung")
    if r.get("unit_k"):
        out["unit_k"] = str(r["unit_k"])
    if r.get("label"):
        out["label_user"] = str(r["label"])[:120]
    if kind in ("arrhenius", "eyring", "order") and isinstance(r.get("dataset"), dict):   # DP-12: Herkunft der Messreihe
        from .datasets import clean_origin, order_unit
        o = clean_origin(r["dataset"])
        if o:
            out["dataset"] = o
            if kind == "order" and not out.get("unit_k"):    # t in s, c in mol/L: Einheit von k folgt aus der Ordnung
                u = order_unit(out["best"], r.get("data") or "c")
                if u:
                    out["unit_k"] = u
    return out


def nuclear_call(kind: str, r: dict) -> dict:
    """Rechnungen des Tabs „Kern“ (Phase 6); Server und Bericht nutzen dieselbe Funktion."""
    from labcalc import nuclear as N
    num = lambda k, d=None: float(str(r.get(k)).replace(",", ".")) if r.get(k) not in (None, "") else d  # noqa: E731
    if kind == "q":
        return N.q_value(str(r.get("nuclide") or ""), str(r.get("mode") or "A"))
    if kind == "binding":
        return N.binding(str(r.get("nuclide") or ""))
    if kind == "equation":
        return N.classify(str(r.get("equation") or ""))
    if kind == "decay":
        unit_t = {"s": 1, "min": 60, "h": 3600, "d": 86400, "a": N.YEAR_S}[r.get("t_unit") or "a"]
        nuc = (r.get("nuclide") or "").strip() or None
        T = num("T_half") * unit_t if num("T_half") else None
        A0 = N.activity_convert(num("A0"), r.get("A_unit") or "Bq", "Bq") if num("A0") is not None else None
        out = N.decay(nuc, T, N0=num("N0"), A0_Bq=A0, m0_g=num("m0"), t_s=(num("t") or 0) * unit_t)
        out["t_unit"] = r.get("t_unit") or "a"
        if nuc:
            out["specific"] = N.specific_activity(nuc)
        return out
    if kind == "chain":
        mem = N.chain(str(r.get("nuclide") or ""), int(num("members", 4)))
        unit_t = {"s": 1, "min": 60, "h": 3600, "d": 86400, "a": N.YEAR_S}[r.get("t_unit") or "d"]
        tmax = (num("tmax") or 10) * unit_t
        times = [tmax * i / 120 for i in range(121)]
        out = {"members": mem, "times_s": times, "t_unit": r.get("t_unit") or "d",
               "N": N.bateman(mem, num("N0", 1e6), times), "refs": ["nubase2020", "bateman1910", "krane"]}
        if len(mem) >= 2 and not mem[1]["stable"]:
            out["equilibrium"] = N.equilibrium(mem[0]["key"], mem[1]["key"])
        return out
    if kind == "dating":
        m = r.get("method") or "c14"
        if m == "c14":
            return {"method": m, **N.radiocarbon(num("F"))}
        if m == "kar":
            return {"method": m, **N.k_ar(num("R"))}
        if m == "arar":
            return {"method": m, **N.ar_ar(num("R"), num("J"))}
        if m == "upb":
            return {"method": m, **N.u_pb(num("r206"), num("r207"))}
        if m == "rbsr":
            pts = []
            for ln in str(r.get("points") or "").replace(";", "\n").splitlines():
                f = [x for x in re.split(r"[\s\t]+", ln.strip().replace(",", ".")) if x]
                if len(f) >= 2:
                    pts.append((float(f[0]), float(f[1])))
            out = {"method": m, **N.rb_sr(pts, r.get("constant") or "villa2015")}
            if isinstance(r.get("dataset"), dict):                      # DP-12: Herkunft der Isochronen-Punkte
                from .datasets import clean_origin
                o = clean_origin(r["dataset"])
                if o:
                    out["dataset"] = o
            return out
        raise C.ChemError(f"Datierungsverfahren „{m}“")
    if kind == "pattern":
        return N.isotope_pattern(str(r.get("formula") or ""))
    if kind == "enriched":
        comp = {}
        for part in re.split(r"[;\n]", str(r.get("composition") or "")):
            f = part.strip().split()
            if len(f) >= 2:
                comp[f[0]] = float(f[1].replace(",", ".").rstrip("%"))
        return N.enriched_mass(comp)
    raise C.ChemError(f"Unbekannte Kernrechnung „{kind}“")


def run(state: dict) -> dict:
    out = {"errors": []}
    eqs = (state.get("equation") or "").strip()
    if eqs:
        try:
            out["equation"] = equation_result(eqs, state.get("amounts"), state.get("actual"), state.get("thermo"),
                                              state.get("redox"))
        except C.ChemError as e:
            out["errors"].append({"where": "equation", "error": str(e)})
    cards = []
    for s in state.get("species") or []:
        s = str(s).strip()
        if not s:
            continue
        try:
            cards.append(species_card(s))
        except C.ChemError as e:
            cards.append({"text": s, "error": str(e)})
    out["species"] = cards
    phs = state.get("ph") or {}
    if (phs.get("mixture") or "").strip():
        from labcalc import acidbase as AB
        try:
            out["ph"] = AB.ph(phs["mixture"], float(phs.get("T") or 25))
            if phs.get("activity") in ("davies", "edh"):                    # ER-S01
                from labcalc import activity as ACT
                out["ph"]["activity"] = ACT.ph_corrected(phs["mixture"], float(phs.get("T") or 25), phs["activity"])
        except C.ChemError as e:
            out["errors"].append({"where": "ph", "error": str(e)})
    ti = state.get("titration") or {}
    if (ti.get("analyte") or "").strip() and (ti.get("titrant") or "").strip():
        from labcalc import acidbase as AB
        try:
            out["titration"] = AB.titration(ti["analyte"], float(ti.get("V0") or 25), ti["titrant"],
                                            float(ti.get("c") or 0.1), float(ti.get("Vmax") or 50),
                                            T_C=float(ti.get("T") or 25))
        except (C.ChemError, ValueError) as e:
            out["errors"].append({"where": "titration", "error": str(e)})
    prep = []
    for item in state.get("prep") or []:
        kind = (item or {}).get("kind")
        if kind not in PREP_KINDS:
            continue
        try:
            rq = dict(item.get("req") or {}, terms_only=False)
            if state.get("lang") in ("de", "en"):
                rq["lang"] = state["lang"]
            prep.append({"kind": kind, "label": item.get("label") or "", "req": item.get("req") or {},
                         "result": prep_call(kind, rq)})
        except (C.ChemError, ValueError, TypeError) as e:
            out["errors"].append({"where": f"prep:{kind}", "error": str(e)})
    if prep:
        out["prep"] = prep
    plans = []
    for item in state.get("plans") or []:          # gemerkte Reaktionspläne zum Vergleich
        try:
            plans.append({"label": item.get("label") or "", "result": prep_call("reaction", dict(item.get("req") or {},
                                                                                              terms_only=False))})
        except (C.ChemError, ValueError, TypeError) as e:
            out["errors"].append({"where": "plans", "error": str(e)})
    if plans:
        out["plans"] = plans
    nuc = []
    for item in state.get("nuclear") or []:
        kind = (item or {}).get("kind")
        if kind not in NUC_KINDS:
            continue
        try:
            nuc.append({"kind": kind, "req": item.get("req") or {}, "result": nuclear_call(kind, item.get("req") or {})})
        except (C.ChemError, ValueError, TypeError, KeyError) as e:
            out["errors"].append({"where": f"nuclear:{kind}", "error": str(e)})
    if nuc:
        out["nuclear"] = nuc
    kin = []
    for item in state.get("kinetics") or []:
        kind = (item or {}).get("kind")
        if kind not in KIN_KINDS:
            continue
        try:
            kin.append({"kind": kind, "req": item.get("req") or {}, "result": kinetics_call(kind, item.get("req") or {})})
        except (ValueError, TypeError, KeyError) as e:
            out["errors"].append({"where": f"kinetics:{kind}", "error": str(e)})
    if kin:
        out["kinetics"] = kin
    vp = state.get("vapor") or {}
    if (vp.get("solvent") or "").strip():
        try:
            out["vapor"] = vapor_call(vp)
        except (ValueError, TypeError) as e:
            out["errors"].append({"where": "vapor", "error": str(e)})
    sat = state.get("saturation") or {}
    if (sat.get("salt") or "").strip():
        try:
            out["saturation"] = saturation_call(sat)
        except (ValueError, TypeError) as e:
            out["errors"].append({"where": "saturation", "error": str(e)})
    sp = state.get("speciation") or {}
    if (sp.get("metal") or "").strip() and (sp.get("ligand") or "").strip():
        try:
            out["speciation"] = speciation_call(sp)
        except (ValueError, TypeError) as e:
            out["errors"].append({"where": "speciation", "error": str(e)})
    emp = state.get("empirical")
    if emp and emp.get("fractions"):
        try:
            fr = {k: float(v) for k, v in emp["fractions"].items() if str(v).strip() not in ("", "None")}
            out["empirical"] = C.empirical_formula(fr, float(emp["M"]) if emp.get("M") else None)
        except (C.ChemError, ValueError) as e:
            out["errors"].append({"where": "empirical", "error": str(e)})
    if isinstance(state.get("unc"), dict):                  # Runde U: Ausbeute, molare Massen, pH mit Unsicherheit
        from . import uncert as UC
        out["unc"] = UC.for_run(state, out, state.get("lang") if state.get("lang") in ("de", "en") else "de")
    return out


def fmt(v, digits=4):
    if v is None:
        return "–"
    if v == 0:
        return "0"
    a = abs(v)
    if 1e-3 <= a < 1e6:
        d = max(0, digits - int(math.floor(math.log10(a))) - 1)
        return f"{v:.{d}f}"
    return f"{v:.{digits - 1}e}"
