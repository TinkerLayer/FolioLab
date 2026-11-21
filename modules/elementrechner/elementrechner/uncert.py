"""Messunsicherheit im Elementrechner (Runde U): Modelle für molare Masse, Ansetzen, Verdünnungsreihe, Gase, Ausbeute
und pH. Die Rechnungen der Verfahren (GUM linear, Monte Carlo nach GUM S1, Gauss, Grösstfehler) stehen in
``labcalc.uncertainty``; hier stehen nur die Modelle und ihre Eingangsgrössen.

Angaben der Seite (``unc``)::

    {"method": "gum" | "mc" | "gauss" | "worst" | "all", "p": 0.95, "k": None,
     "specs": {"s.V": {"parts": [...]}, "s.m.0": {...}, ...}}     # Schlüssel wie die ±-Knöpfe der Seite

Ein Eintrag in ``specs`` kann ``value`` und ``unit`` des Eingabefelds mitbringen (z. B. eine Masse in mg); dann
wird mit diesem Wert und dieser Einheit gerechnet und im Modell umgerechnet.

Standardatomgewichte: Intervalle [a, b] gelten als Rechteckverteilung über das Intervall (Mitte, Halbbreite
(b − a)/2) nach Possolo et al. 2018; ein Einzelwert mit Unsicherheit in Klammern wird hier ebenfalls als Rechteck
±U behandelt (Annahme des Moduls). Elemente sind unabhängig; ein Element, das n-mal vorkommt, geht als n·A_r ein
(voll mit sich selbst korreliert), auch über mehrere Stoffe einer Rechnung hinweg (dieselbe Eingangsgrösse).
"""
from __future__ import annotations

import math
import re

import numpy as np

from labcalc import chem as C
from labcalc import uncertainty as UN

from .refs import REFS as _REFS

POSSOLO = _REFS["possolo2018"]        # Quelle jeder Atomgewicht-Eingangsgrösse (im Bericht zitiert)
QUAM_A1 = _REFS["quam2012a1"]         # Prüfbeispiel (tests/test_uncert.py)
AME2020 = _REFS["ame2020"]

TX = {
    "de": {"aw": "Standardatomgewicht {el}", "aw_int": "Intervall [{a}; {b}], Rechteck (Possolo et al. 2018)",
           "aw_one": "Einzelwert ± {U}, als Rechteck angenommen", "aw_abr": "gekürzter Wert ± {U}, als Rechteck",
           "aw_iso": "Isotopenmasse (AME2020)", "aw_none": "{el}: kein Standardatomgewicht, Massenzahl exakt gesetzt",
           "M": "Molare Masse {f}", "mid": "Wert aus den Intervallmitten der Standardatomgewichte (Possolo et al. 2018); "
           "die übrigen Rechnungen nutzen die gekürzten Werte, Abweichung {d} g/mol",
           "mid_short": "Molare Massen aus den Intervallmitten der Standardatomgewichte (Possolo et al. 2018); die "
                        "Einwaage-Rechnung nutzt die gekürzten Werte, der Wert kann daher in der 5. Stelle abweichen",
           "m": "Masse eingewogen {f}", "P": "Reinheit {f}", "V": "Endvolumen", "rho": "Dichte der Lösung",
           "c": "Konzentration {f} (angesetzt)", "cs": "Stammlösung", "rhos": "Dichte des Reagenzes",
           "V1": "Volumen Stammlösung", "V2": "Endvolumen", "c0": "Ausgangskonzentration",
           "t": "Übertrag Stufe {i}", "f": "auffüllen Stufe {i}", "ci": "c Stufe {i}",
           "corr": "Korrelation der Stufen über die Ausgangslösung und die gemeinsamen Überträge (GUM linear)",
           "gas": "{q} (ideales Gas)", "q": {"p": "Druck p", "V": "Volumen V", "n": "Stoffmenge n", "T": "Temperatur T"},
           "amt": "Bezugsmenge {f}", "obs": "beobachtete Masse {f}", "Y": "Ausbeute {f}",
           "n": "Menge {f}", "act": "erhalten {f}",
           "pc": "c({f})", "pka": "pKa{j} ({f})", "pH": "pH",
           "pHnote": "u(pH) aus den Unsicherheiten von c und pKa fortgepflanzt; das Modell (Protonenbilanz, ideale Lösung, "
                     "ohne Aktivitäten) hat keine eigene Unsicherheit",
           "nob": "Molalität und Massenanteil als Ziel: keine Unsicherheit für die Stammlösungsrechnung",
           "series_c0": "Ausgangslösung",
           "lim": "begrenzender Stoff je Versuch neu bestimmt (Minimum)"},
    "en": {"aw": "Standard atomic weight {el}", "aw_int": "interval [{a}; {b}], rectangular (Possolo et al. 2018)",
           "aw_one": "single value ± {U}, taken as rectangular", "aw_abr": "abridged value ± {U}, rectangular",
           "aw_iso": "isotopic mass (AME2020)", "aw_none": "{el}: no standard atomic weight, mass number taken as exact",
           "M": "Molar mass {f}", "mid": "Value from the midpoints of the standard atomic weight intervals (Possolo et al. "
           "2018); the other calculations use the abridged values, difference {d} g/mol",
           "mid_short": "Molar masses from the midpoints of the standard atomic weight intervals (Possolo et al. 2018); "
                        "the weighing calculation uses the abridged values, so the value may differ in the 5th digit",
           "m": "mass weighed {f}", "P": "purity {f}", "V": "final volume", "rho": "density of the solution",
           "c": "concentration {f} (as prepared)", "cs": "stock solution", "rhos": "density of the reagent",
           "V1": "volume of stock", "V2": "final volume", "c0": "initial concentration",
           "t": "transfer step {i}", "f": "fill-up step {i}", "ci": "c step {i}",
           "corr": "Correlation of the steps through the stock and the shared transfers (GUM linear)",
           "gas": "{q} (ideal gas)", "q": {"p": "pressure p", "V": "volume V", "n": "amount n", "T": "temperature T"},
           "amt": "reference amount {f}", "obs": "observed mass {f}", "Y": "Yield {f}",
           "n": "amount {f}", "act": "obtained {f}",
           "pc": "c({f})", "pka": "pKa{j} ({f})", "pH": "pH",
           "pHnote": "u(pH) propagated from the uncertainties of c and pKa; the model (proton balance, ideal solution, "
                     "no activities) carries no uncertainty of its own",
           "nob": "Molality or mass fraction as target: no uncertainty for the stock calculation",
           "series_c0": "stock",
           "lim": "limiting reagent re-determined for every trial (minimum)"},
}

VOL = {"L": 1.0, "mL": 1e-3, "µL": 1e-6, "uL": 1e-6, "dL": 0.1}
MASS = {"g": 1.0, "mg": 1e-3, "kg": 1e3, "µg": 1e-6}
NMOL = {"mol": 1.0, "mmol": 1e-3, "µmol": 1e-6}


def _L(lang):
    return TX["en" if lang == "en" else "de"]


def _f(v, what="Wert") -> float:
    try:
        x = float(str(v).strip().replace(",", ".").replace("−", "-"))
    except (TypeError, ValueError):
        raise UN.UncError(f"{what}: Zahl erwartet") from None
    if not math.isfinite(x):
        raise UN.UncError(f"{what}: Zahl erwartet")
    return x


def method_of(unc: dict | None) -> dict:
    u = unc or {}
    m = u.get("method") if u.get("method") in UN.METHODS + ("all",) else "gum"
    try:
        p = float(u.get("p") or UN.P_DEFAULT)
    except (TypeError, ValueError):
        p = UN.P_DEFAULT
    try:
        k = float(u["k"]) if u.get("k") not in (None, "", 0) else None
    except (TypeError, ValueError):
        k = None
    return {"method": m, "p": p, "k": k}


def _specs(unc: dict | None) -> dict:
    s = (unc or {}).get("specs")
    return s if isinstance(s, dict) else {}


def _inp(name, value, unit, label, spec=None, source=None) -> dict:
    """Eingangsgrösse aus Wert und ±-Angabe der Seite (ohne Angabe: exakt)."""
    d = {"name": name, "value": float(value), "unit": unit or "", "label": label, "parts": []}
    if isinstance(spec, dict) and spec.get("parts"):
        d["parts"] = list(spec["parts"])[:20]
        if spec.get("dof") not in (None, ""):
            d["dof"] = spec["dof"]
        if spec.get("note"):
            d["note"] = str(spec["note"])[:300]
    if source:
        d["source"] = source
    return d


def _measured(spec, value, unit, table) -> tuple[float, str, float]:
    """Wert/Einheit aus dem Eingabefeld (spec.value/unit), sonst (value, unit); Faktor in die Basiseinheit der Tabelle."""
    if isinstance(spec, dict) and spec.get("value") not in (None, "") and spec.get("unit") in table:
        try:
            return _f(spec["value"]), spec["unit"], table[spec["unit"]]
        except UN.UncError:
            pass
    return float(value), unit, table.get(unit, 1.0)


# ============================================================================== Standardatomgewichte
def aw_input(el: str, lang: str = "de") -> dict:
    """Eingangsgrösse A_r(el) nach Possolo et al. 2018 (Intervall → Rechteck); Isotope mit AME2020."""
    L = _L(lang)
    name = "A_" + el
    m = re.match(r"^(\d+)([A-Z][a-z]?)$", el)
    if m:
        iso = C.isotope_masses().get(el)
        if not iso:
            raise UN.UncError(f"Isotopenmasse von {el} nicht vorhanden")
        u = float(iso.get("u_u") or 0.0)
        parts = [{"kind": "u", "u": u, "label": L["aw_iso"]}] if u > 0 else []
        return {"name": name, "value": float(iso["mass_u"]), "unit": "", "label": L["aw"].format(el=el), "parts": parts,
                "source": AME2020}
    w = C.atomic_weights().get(el)
    if not w:
        raise UN.UncError(f"Kein Atomgewicht für {el}")
    if w.get("value") is None:
        return {"name": name, "value": float(w.get("mass_number") or 0), "unit": "", "parts": [],
                "label": L["aw_none"].format(el=el)}
    loc = (lambda s: s.replace(".", ",")) if lang == "de" else (lambda s: s)
    if w.get("interval"):
        a, b = (float(x) for x in w["interval"])
        parts = [{"kind": "limits", "a": (b - a) / 2, "dist": "rect", "source": POSSOLO,
                  "label": L["aw_int"].format(a=loc(f"{a:g}"), b=loc(f"{b:g}"))}]
        val = (a + b) / 2
    elif w.get("standard") is not None:
        U = float(w.get("standard_u") or 0.0)
        parts = [{"kind": "limits", "a": U, "dist": "rect", "source": POSSOLO,
                  "label": L["aw_one"].format(U=loc(f"{U:g}"))}] if U > 0 else []
        val = float(w["standard"])
    else:
        U = float(w.get("u") or 0.0)
        parts = [{"kind": "limits", "a": U, "dist": "rect", "source": POSSOLO,
                  "label": L["aw_abr"].format(U=loc(f"{U:g}"))}] if U > 0 else []
        val = float(w["value"])
    return {"name": name, "value": val, "unit": "", "label": L["aw"].format(el=el), "parts": parts, "source": _REFS["ciaaw2024"]}


def counts_of(sp) -> dict[str, float]:
    if isinstance(sp, str):
        sp = C.parse_species(sp)
    if sp.kind != "chem":
        raise UN.UncError(f"„{sp.text}“ ist kein chemischer Stoff")
    return {k: float(n) for k, n in sp.counts.items()}


def m_of(counts: dict, vals: dict):
    """Σ nᵢ·A_r,i aus den Werten (Zahl oder numpy-Feld)."""
    s = 0.0
    for el, n in counts.items():
        s = s + n * vals["A_" + el]
    return s


def _aw_inputs(els, lang) -> list[dict]:
    return [aw_input(e, lang) for e in dict.fromkeys(els)]


def possolo_u(text) -> dict:
    """Molare Masse aus den Intervallmitten und ihre Standardunsicherheit (GUM linear, geschlossen; für Wertekataloge).
    text: Formel oder Species."""
    cnt = counts_of(text)
    v, var = 0.0, 0.0
    for el, n in cnt.items():
        x = aw_input(el)
        v += n * x["value"]
        for p in x["parts"]:
            u = p["a"] / math.sqrt(3) if p.get("kind") == "limits" else float(p.get("u") or 0)
            var += (n * u) ** 2
    return {"value": v, "u": math.sqrt(var)}


# ============================================================================== Auswertung
def job(name, label, unit, model, inputs, notes=None, corr=None) -> dict:
    return {"name": name, "label": label, "unit": unit, "model": model, "inputs": inputs, "notes": list(notes or []),
            "corr": corr}


def run_job(j: dict, meth: dict, lang: str = "de") -> dict:
    kw = dict(corr=j.get("corr"), p=meth["p"], k=meth["k"], lang=lang, unit=j["unit"], label=j["label"], name=j["name"])
    try:
        if meth["method"] == "all":
            return {"name": j["name"], "label": j["label"], "compare": UN.compare(j["model"], j["inputs"], **kw)}
        r = UN.evaluate(j["model"], j["inputs"], meth["method"], **kw)
    except (UN.UncError, C.ChemError, ValueError, ZeroDivisionError) as e:
        return {"name": j["name"], "label": j["label"], "error": str(e)}
    if j["notes"]:
        r["note_texts"] = list(j["notes"]) + list(r.get("note_texts") or [])
    r["specs"] = [{k: x.get(k) for k in ("name", "value", "unit", "label", "parts")} for x in j["inputs"]]
    return r


def _uncertain(j: dict) -> bool:
    return any(x.get("parts") for x in j["inputs"])


def run_jobs(jobs: list[dict], unc: dict | None, lang: str = "de", only: str | None = None) -> list[dict]:
    """Ergebnisse der Modelle; ein Modell ohne unsichere Eingangsgrösse liefert nur {"name", "label", "none": True}."""
    meth = method_of(unc)
    return [run_job(j, meth, lang) if _uncertain(j) else {"name": j["name"], "label": j["label"], "none": True}
            for j in jobs if not only or j["name"] == only]


# ============================================================================== Molare Masse
def molar_mass_job(text: str, lang: str = "de", name: str | None = None) -> dict:
    L = _L(lang)
    sp = C.parse_species(text)
    cnt = counts_of(sp)
    ins = _aw_inputs(cnt, lang)
    notes = []
    try:
        ab = C.molar_mass(sp)["M"]
        mid = sum(n * x["value"] for n, x in zip(cnt.values(), ins))
        if abs(mid - ab) > 0:
            notes.append(L["mid"].format(d=(f"{mid - ab:+.2g}".replace(".", ",") if lang == "de" else f"{mid - ab:+.2g}")))
    except C.ChemError:
        pass
    return job(name or ("M-" + sp.formula), L["M"].format(f=sp.unicode()), "g/mol", lambda v: m_of(cnt, v), ins, notes)


def molar_mass(text: str, unc: dict | None = None, lang: str = "de") -> dict:
    return run_jobs([molar_mass_job(text, lang)], unc, lang)[0]


# ============================================================================== Ansetzen: Feststoff
def _fac(unit: str) -> tuple[str, float]:
    from labcalc import prep as PR
    if unit not in PR.BASES:
        raise UN.UncError(f"Einheit „{unit}“ unbekannt")
    return PR.BASES[unit]


def _rho_gmL(unit: str) -> float:
    return {"g/mL": 1.0, "g/cm3": 1.0, "g/cm³": 1.0, "kg/L": 1.0, "g/L": 1e-3, "kg/m3": 1e-3, "kg/m³": 1e-3}.get(unit or "g/mL", 1.0)


def _conc_out(kind: str, n_b, Mb, VL, rho_gmL=None):
    """Konzentration in der Basis der Art (mol/L, g/L, g/mL, Anteil, mol/kg) aus der Stoffmenge des Bezugs."""
    if kind == "molar":
        return n_b / VL
    if kind == "mass":
        return n_b * Mb / VL
    if kind == "wv":
        return n_b * Mb / (VL * 1000)
    m_sol = rho_gmL * VL * 1000                                   # g
    if kind == "w":
        return n_b * Mb / m_sol
    return n_b / ((m_sol - n_b * Mb) / 1000)                      # b: mol/kg Lösungsmittel


def solid_jobs(req: dict, out: dict, lang: str = "de") -> list[dict]:
    L = _L(lang)
    specs = _specs(req.get("unc"))
    comps = req.get("components") or []
    rows = out.get("components") or [out]
    V_unit = req.get("V_unit") or "mL"
    if V_unit not in VOL:
        raise UN.UncError("Volumeneinheit")
    V_val = rows[0]["V_L"] / VOL[V_unit]
    V_in = _inp("V", V_val, V_unit, L["V"], specs.get("s.V"))
    jobs = []
    many = len(rows) > 1
    for i, r in enumerate(rows):
        c = comps[i] if i < len(comps) else {}
        f, b = r["form"], r["basis"]
        k = float(r.get("per_unit") or 1.0)
        tg = r["target"]
        kind, fac = _fac(tg["unit"])
        sfx = f"_{i + 1}" if many else ""
        sm = specs.get(f"s.m.{i}")
        mw = c.get("mw") if c.get("mw") not in (None, "") else None
        m_base = _f(mw, "Einwaage") if mw is not None else float(r.get("mass_rounded_g") or r["mass_g"])
        m_val, m_unit, m_fac = _measured(sm, m_base, "g", MASS)
        ins = [_inp("m" + sfx, m_val, m_unit, L["m"].format(f=f["formula"]), sm)]
        raw_p = c.get("purity")
        sp_ = specs.get(f"s.purity.{i}")
        if raw_p in (None, "") and not (sp_ and sp_.get("parts")):
            P_val, P_sc = 1.0, 1.0
        else:
            P_val = _f(raw_p, "Reinheit") if raw_p not in (None, "") else 100.0
            P_sc = 0.01 if P_val > 1 else 1.0
        ins.append(_inp("P" + sfx, P_val, "%" if P_sc != 1 else "", L["P"].format(f=f["formula"]), sp_))
        ins.append(V_in)
        cf, cb = f["counts"], b["counts"]
        ins += _aw_inputs(list(cf) + list(cb), lang)
        rho_unit = None
        if kind in ("w", "b"):
            rs = req.get("rho_solution") or {}
            rho_unit = rs.get("unit") or "g/mL"
            ins.append(_inp("rho", _f(rs.get("value"), "Dichte"), rho_unit, L["rho"], specs.get("s.rv")))
        vu, rg = VOL[V_unit], _rho_gmL(rho_unit)

        def model(v, cf=cf, cb=cb, k=k, kind=kind, fac=fac, sfx=sfx, m_fac=m_fac, P_sc=P_sc, vu=vu, rg=rg):
            Mf, Mb = m_of(cf, v), m_of(cb, v)
            n_b = v["m" + sfx] * m_fac * v["P" + sfx] * P_sc * k / Mf
            rho = v["rho"] * rg if "rho" in v else None
            return _conc_out(kind, n_b, Mb, v["V"] * vu, rho) / fac
        notes = [L["mid_short"]] if cf != cb or kind in ("molar", "w", "b") else []
        jobs.append(job(f"prep-c{sfx}-{b['formula']}" if many else f"prep-c-{b['formula']}",
                        L["c"].format(f=b["formula"]), tg["unit"], model, ins, notes))
    return jobs


# ============================================================================== Ansetzen: Stammlösung
def stock_jobs(req: dict, out: dict, lang: str = "de") -> list[dict]:
    from labcalc import prep as PR
    L = _L(lang)
    specs = _specs(req.get("unc"))
    f, b = out["form"], out["basis"]
    tg = out["target"]
    kind_t, fac_t = _fac(tg["unit"])
    if kind_t not in ("molar", "mass", "wv"):
        return [{"name": "prep-stock", "label": L["c"].format(f=b["formula"]), "skip": L["nob"]}]
    stock = req.get("stock") or {}
    s_unit = stock.get("unit") or "mol/L"
    kind_s, fac_s = _fac(s_unit)
    k = 1.0
    if req.get("basis") and str(req.get("basis")).strip():
        k = PR.per_unit(f, b)
    stock_basis = stock.get("basis") or "form"
    ins = [_inp("c_s", _f(stock.get("value"), "Stammlösung"), s_unit, L["cs"], specs.get("k.sv"))]
    rg = 1.0
    if kind_s == "w":
        d = stock.get("density") or {}
        rg = _rho_gmL(d.get("unit") or "g/mL")
        ins.append(_inp("rho", _f(d.get("value"), "Dichte"), d.get("unit") or "g/mL", L["rhos"], specs.get("k.dv")))
    sv1 = specs.get("k.V1")
    v1_base = _f(req["V1"], "Volumen") if req.get("V1") not in (None, "") else float(out["V_stock_mL"])
    v1, v1_unit, v1_fac = _measured(sv1, v1_base, "mL", {u: x * 1000 for u, x in VOL.items()})
    ins.append(_inp("V_1", v1, v1_unit, L["V1"], sv1))
    V_unit = req.get("V_unit") or "mL"
    ins.append(_inp("V_2", out["V_L"] / VOL[V_unit], V_unit, L["V2"], specs.get("k.V")))
    cf, cb = f["counts"], b["counts"]
    cs_counts = cf if stock_basis == "form" else cb
    ins += _aw_inputs(list(cf) + list(cb), lang)
    vu = VOL[V_unit]

    def model(v):
        x = v["c_s"] * fac_s
        Ms, Mb = m_of(cs_counts, v), m_of(cb, v)
        if kind_s == "molar":
            cmol = x
        elif kind_s == "mass":
            cmol = x / Ms
        elif kind_s == "wv":
            cmol = x * 1000 / Ms
        else:
            cmol = x * v["rho"] * rg * 1000 / Ms
        c_b = cmol * k if stock_basis == "form" else cmol
        c2 = c_b * v["V_1"] * v1_fac / 1000 / (v["V_2"] * vu)
        if kind_t == "molar":
            return c2 / fac_t
        if kind_t == "mass":
            return c2 * Mb / fac_t
        return c2 * Mb / 1000 / fac_t
    return [job("prep-stock-" + b["formula"], L["c"].format(f=b["formula"]), tg["unit"], model, ins)]


# ============================================================================== Verdünnungsreihe
def series_jobs(req: dict, out: dict, lang: str = "de") -> list[dict]:
    L = _L(lang)
    specs = _specs(req.get("unc"))
    unit = out["unit"]
    c0 = _inp("c_0", float(out["c0"]), unit, L["c0"], specs.get("v.c0"))
    ins = [c0]
    jobs = []
    for r in out["rows"]:
        i = r["step"]
        ins = ins + [_inp(f"t_{i}", r["transfer_mL"], "mL", L["t"].format(i=i), specs.get("v.pip")),
                     _inp(f"f_{i}", r["total_mL"], "mL", L["f"].format(i=i), specs.get("v.flask"))]

        def model(v, i=i):
            c = v["c_0"]
            for j in range(1, i + 1):
                c = c * v[f"t_{j}"] / v[f"f_{j}"]
            return c
        jobs.append(job(f"series-c{i}", L["ci"].format(i=i), unit, model, list(ins)))
    return jobs


def series_corr(jobs: list[dict], lang: str = "de") -> dict:
    """Korrelationsmatrix der Stufen (GUM linear): r_ik = Σ c_i,q c_k,q u_q² / (u_i u_k)."""
    if not jobs:
        return {}
    full = UN._prep(jobs[-1]["inputs"], lang)
    idx = {x["name"]: q for q, x in enumerate(full)}
    S = []
    for j in jobs:
        ins = UN._prep(j["inputs"], lang)
        _, cs, _ = UN.sensitivities(j["model"], ins)
        row = np.zeros(len(full))
        for x, c in zip(ins, cs):
            row[idx[x["name"]]] = c * x["u"]
        S.append(row)
    S = np.array(S)
    cov = S @ S.T
    d = np.sqrt(np.diag(cov))
    with np.errstate(all="ignore"):
        R = np.where(np.outer(d, d) > 0, cov / np.outer(d, d), 0.0)
    return {"r": [[float(x) for x in row] for row in R], "u": [float(x) for x in d], "note": _L(lang)["corr"]}


# ============================================================================== Gase
def gas_jobs(req: dict, out: dict, lang: str = "de") -> list[dict]:
    from labcalc import gas as GA
    L = _L(lang)
    ide = out.get("ideal")
    if not ide:
        return []
    specs = _specs(req.get("unc"))
    un = ide["units"]
    k = ide["solved"]
    ins = []
    for q in ("p", "V", "n", "T"):
        if q == k:
            continue
        ins.append(_inp(q, _f(req.get(q), q), un[q], L["q"][q], specs.get("g." + q)))
    pf, vf, nf = GA.P_UNITS[un["p"]], GA.V_UNITS[un["V"]], GA.N_UNITS[un["n"]]
    tc = un["T"] in ("°C", "C")
    R = GA.R

    def model(v):
        p = v["p"] * pf if "p" in v else None
        V = v["V"] * vf if "V" in v else None
        n = v["n"] * nf if "n" in v else None
        T = (v["T"] + 273.15 if tc else v["T"]) if "T" in v else None
        if k == "p":
            return n * R * T / V / pf
        if k == "V":
            return n * R * T / p / vf
        if k == "n":
            return p * V / (R * T) / nf
        TK = p * V / (n * R)
        return TK - 273.15 if tc else TK
    return [job("gas-" + k, L["gas"].format(q=L["q"][k]), un[k], model, ins)]


# ============================================================================== Ausbeute (Reaktionsansatz)
def plan_jobs(req: dict, out: dict, lang: str = "de") -> list[dict]:
    from labcalc import reaction_setup as RS
    L = _L(lang)
    plan = out.get("plan") or {}
    obs = plan.get("observed") or {}
    if not obs:
        return []
    specs = _specs(req.get("unc"))
    ref = req.get("reference") or {}
    ref_i = int(plan["reference"])
    coefs = plan["coefs"]
    terms = out["terms"]
    unit = ref.get("unit") or "mmol"
    kind, fac = RS.AMOUNT_UNITS.get(unit, ("n", 1e-3))
    ratio = plan["xi_limiting"] / plan["xi"] if plan.get("xi") else 1.0
    ref_sp = terms[ref_i]["species"]
    ref_counts = counts_of(C.parse_equation(plan["equation"]).terms[ref_i].species)
    eq_terms = C.parse_equation(plan["equation"]).terms
    jobs = []
    for key, o in obs.items():
        if o.get("kind") != "product":
            continue
        i = int(key)
        pc = counts_of(eq_terms[i].species)
        f = terms[i]["species"]
        so = specs.get(f"r.obs.{i}")
        ins = [_inp("n_ref" if kind == "n" else "m_ref", _f(ref.get("value"), "Bezugsmenge"), unit,
                    L["amt"].format(f=ref_sp), specs.get("r.amt")),
               _inp("m_P", float(o["m_g"]), "g", L["obs"].format(f=f), so)]
        ins += _aw_inputs(list(pc) + (list(ref_counts) if kind == "m" else []), lang)

        def model(v, pc=pc, i=i):
            n_ref = v["n_ref"] * fac if kind == "n" else v["m_ref"] * fac / m_of(ref_counts, v)
            m_th = coefs[i] * (n_ref / coefs[ref_i]) * ratio * m_of(pc, v)
            return 100 * v["m_P"] / m_th
        jobs.append(job(f"yield-plan-{i}", L["Y"].format(f=f), "%", model, ins))
    return jobs


# ============================================================================== Ausbeute (Gleichung, Stöchiometrie)
def stoich_jobs(state: dict, eqr: dict, lang: str = "de") -> list[dict]:
    L = _L(lang)
    st = eqr.get("stoich") if eqr else None
    if not st or not state.get("actual"):
        return []
    specs = _specs(state.get("unc"))
    eq = C.parse_equation(eqr["input"])
    coefs = [float(Fraction_(c)) for c in eqr["coefs"]]
    amounts = {int(k): v for k, v in (state.get("amounts") or {}).items()}
    actual = {int(k): v for k, v in (state.get("actual") or {}).items()}
    reac = [i for i, t in enumerate(eq.terms) if t.side < 0 and i in amounts]
    if not reac:
        return []
    ins, conv, els = [], {}, []

    def add(i, a, label):
        sp = eq.terms[i].species
        spec = specs.get(f"st.{i}")
        nm = f"x_{i + 1}"
        if a.get("n_mol") is not None:
            val, unit, fct = _measured(spec, float(a["n_mol"]), "mol", NMOL)
            conv[i] = ("n", fct, nm, None)
        elif a.get("mass_g") is not None:
            val, unit, fct = _measured(spec, float(a["mass_g"]), "g", MASS)
            cnt = counts_of(sp)
            els.extend(cnt)
            conv[i] = ("m", fct, nm, cnt)
        elif a.get("c_molL") is not None and a.get("V_L") is not None:
            val, unit = float(a["c_molL"]), "mol/L"
            conv[i] = ("c", float(a["V_L"]), nm, None)
        elif a.get("V_L") is not None:
            T = float(a.get("T_K") or 273.15)
            p = float(a.get("p_Pa") or 101325.0)
            val, unit = float(a["V_L"]), "L"
            conv[i] = ("g", p * 1e-3 / (C.R_GAS * T), nm, None)
        else:
            return
        ins.append(_inp(nm, val, unit, label.format(f=sp.unicode()), spec))
    for i in reac:
        add(i, amounts[i], L["n"])
    prods = [i for i in actual if 0 <= i < len(eq.terms) and eq.terms[i].side > 0]
    for i in prods:
        add(i, actual[i], L["act"])
    ins += _aw_inputs(els, lang)

    def n_of(i, v):
        kind, fct, nm, cnt = conv[i]
        if kind == "m":
            return v[nm] * fct / m_of(cnt, v)
        if kind in ("n",):
            return v[nm] * fct
        return v[nm] * fct                               # c·V bzw. pV/(RT)
    jobs = []
    for i in prods:
        if i not in conv:
            continue

        def model(v, i=i):
            xi = None
            for j in reac:
                x = n_of(j, v) / coefs[j]
                xi = x if xi is None else np.minimum(xi, x)
            return 100 * n_of(i, v) / (coefs[i] * xi)
        notes = [L["lim"]] if len(reac) > 1 else []
        jobs.append(job(f"yield-{eq.terms[i].species.formula}", L["Y"].format(f=eq.terms[i].species.unicode()), "%",
                        model, ins, notes))
    return jobs


def Fraction_(c):
    from fractions import Fraction
    return Fraction(str(c))


# ============================================================================== pH
def _forms_v(steps: dict, pH):
    js = sorted(steps)
    j0 = js[0] - 1
    logs = [np.zeros_like(pH)]
    acc = np.zeros_like(pH)
    for j in range(js[0], js[-1] + 1):
        pk = steps.get(j)
        if pk is None:
            break
        acc = acc + pk - pH
        logs.append(acc)
    mx = np.maximum.reduce(logs)
    w = [10.0 ** (x - mx) for x in logs]
    s = sum(w)
    return j0, w, s


def ph_vec(comps: list[dict], scale: list, pkas: dict, kw: float, n: int):
    """pH aus der Protonenbilanz (wie labcalc.acidbase.solve), vektorisiert über n Wertesätze.
    scale[k]: Faktor auf die Konzentration von Bestandteil k; pkas[(k, s, j)]: pKa-Werte (Zahl oder Feld)."""
    lo, hi = np.full(n, -2.0), np.full(n, 16.5)

    def bal(pH):
        s = 10.0 ** -pH - 10.0 ** (pH - kw)
        for k, c in enumerate(comps):
            f = scale[k]
            s = s - f * (c["strong_acid"] - c["strong_base"])
            for si, y in enumerate(c["systems"]):
                steps = {j: pkas.get((k, si, j), v) for j, v in y["steps"].items()}
                j0, w, tot = _forms_v(steps, pH)
                nbar = sum((j0 + q) * wq for q, wq in enumerate(w)) / tot
                s = s - f * y["c"] * (y["h"] - nbar)
        return s
    for _ in range(80):
        mid = (lo + hi) / 2
        pos = bal(mid) > 0
        lo = np.where(pos, mid, lo)
        hi = np.where(pos, hi, mid)
    return (lo + hi) / 2


def ph_job(mixture, T_C: float = 25.0, unc: dict | None = None, lang: str = "de") -> tuple[dict, list[dict]]:
    """Modell pH(c, pKa) und die Liste der Eingaben, an die die Seite ± hängen kann."""
    from labcalc import acidbase as AB
    L = _L(lang)
    specs = _specs(unc)
    items = AB.parse_mixture(mixture) if isinstance(mixture, str) else list(mixture)
    comps = [AB.component(t, float(c)) for t, c in items]
    kw = AB.pkw(25.0 if T_C is None else float(T_C))
    ins, listing, pk_names = [], [], {}
    for k, (t, c) in enumerate(items):
        key = f"ph.c.{k}"
        ins.append(_inp(f"c_{k + 1}", float(c), "mol/L", L["pc"].format(f=t), specs.get(key)))
        listing.append({"key": key, "name": f"c_{k + 1}", "label": L["pc"].format(f=t), "value": float(c), "unit": "mol/L"})
        for si, y in enumerate(comps[k]["systems"]):
            N = max(y["steps"])                       # Anzeige wie die Seite: pKa1 = sauerste Stufe (j = N)
            for j, v in sorted(y["steps"].items(), reverse=True):
                if (y.get("src") or {}).get(j, {}).get("strong"):
                    continue
                d = N - j + 1
                nm = f"pKa_{k + 1}{'abcdefgh'[si] if len(comps[k]['systems']) > 1 else ''}_{d}"
                key = f"ph.pka.{k}.{si}.{j}"
                lab = L["pka"].format(j=d, f=t)
                ins.append(_inp(nm, float(v), "", lab, specs.get(key)))
                listing.append({"key": key, "name": nm, "label": lab, "value": float(v), "unit": ""})
                pk_names[(k, si, j)] = nm
    c0 = [float(c) for _, c in items]

    def model(v):
        arrs = [np.atleast_1d(np.asarray(x, float)) for x in v.values()]
        n = max([a.size for a in arrs] + [1])
        scale = [np.broadcast_to(np.asarray(v[f"c_{k + 1}"], float) / c0[k], (n,)) if c0[k] else 0.0 for k in range(len(c0))]
        pk = {key: np.broadcast_to(np.asarray(v[nm], float), (n,)) for key, nm in pk_names.items()}
        r = ph_vec(comps, scale, pk, kw, n)
        return r if n > 1 or any(np.ndim(x) for x in v.values()) else float(r[0])
    return job("pH", L["pH"], "", model, ins, [L["pHnote"]]), listing


def ph(mixture, T_C=25.0, unc: dict | None = None, lang: str = "de") -> dict:
    j, listing = ph_job(mixture, T_C, unc, lang)
    res = run_jobs([j], unc, lang)[0]
    return {"inputs": listing, "result": res}


# ============================================================================== Einstieg aus Server und Bericht
PREP_JOBS = {"solid": solid_jobs, "stock": stock_jobs, "series": series_jobs, "gas": gas_jobs, "reaction": plan_jobs}


def prep(kind: str, req: dict, out: dict, lang: str = "de", only: str | None = None) -> dict:
    """Unsicherheit einer Ansetz-Rechnung: {"results": [...], "corr"?: {...}}; Fehler bleiben je Ergebnis stehen."""
    fn = PREP_JOBS.get(kind)
    if not fn:
        return {"results": []}
    try:
        jobs = fn(req, out, lang)
    except (UN.UncError, C.ChemError, KeyError, ValueError, TypeError) as e:
        return {"results": [], "error": str(e)}
    skipped = [{"name": j["name"], "label": j["label"], "error": j["skip"]} for j in jobs if j.get("skip")]
    jobs = [j for j in jobs if not j.get("skip")]
    res = {"results": skipped + run_jobs(jobs, req.get("unc"), lang, only)}
    if kind == "series" and not only and len(jobs) > 1:
        try:
            res["corr"] = series_corr(jobs, lang)
        except (UN.UncError, ValueError, np.linalg.LinAlgError):
            pass
    return res


def for_run(state: dict, out: dict, lang: str = "de", only: str | None = None) -> dict:
    """Unsicherheiten der Ergebnisse von analysis.run: Ausbeute der Gleichung, molare Massen der Stoffe, pH."""
    unc = state.get("unc") or {}
    jobs = []
    try:
        jobs += stoich_jobs(state, out.get("equation"), lang)
    except (UN.UncError, C.ChemError, KeyError, ValueError, TypeError):
        pass
    for card in out.get("species") or []:
        if card.get("error") or not card.get("molar_mass"):
            continue
        try:
            jobs.append(molar_mass_job(card["text"], lang))
        except (UN.UncError, C.ChemError):
            pass
    results = run_jobs(jobs, unc, lang, only)
    ph_ = (state.get("ph") or {}).get("mixture")
    listing = []
    if ph_ and out.get("ph") and (not only or only == "pH"):
        try:
            j, listing = ph_job(ph_, (state.get("ph") or {}).get("T") or 25, unc, lang)
            results += run_jobs([j], unc, lang, only)
        except (UN.UncError, C.ChemError, ValueError):
            pass
    return {"results": results, "ph_inputs": listing, "method": method_of(unc)}


def report_results(res: dict) -> list[dict]:
    """Alle Unsicherheitsergebnisse eines run()-Ergebnisses (für den Bericht)."""
    out = [r for r in ((res.get("unc") or {}).get("results") or [])]
    for it in res.get("prep") or []:
        out += ((it.get("result") or {}).get("unc") or {}).get("results") or []
    return [r for r in out if r and not r.get("error") and not r.get("none") and r.get("value") is not None
            and not (not r.get("u") and not r.get("U"))]                  # u = U = 0: nichts zu berichten


def compare(where: str, req: dict, name: str, lang: str = "de") -> dict:
    """Alle vier Verfahren für ein Ergebnis (Fold „Verfahren vergleichen“ der Seite).
    where: "prep:<kind>" (req wie /api/prep/<kind>), "run" (req = state), "species" (req = {formula}), "ph" ({mixture, T})."""
    from . import analysis as AN
    unc = dict((req or {}).get("unc") or {}, method="all")
    if where.startswith("prep:"):
        kind = where[5:]
        if kind not in PREP_JOBS:
            raise UN.UncError("unbekannte Rechnung")
        r = dict(req)
        r.pop("unc", None)
        out = AN._prep_call(kind, r)
        res = prep(kind, dict(r, unc=unc), out, lang, only=name)["results"]
    elif where == "run":
        st = dict(req)
        st.pop("unc", None)
        out = AN.run(st)
        res = for_run(dict(st, unc=unc), out, lang, only=name)["results"]
    elif where == "species":
        res = run_jobs([molar_mass_job(str(req.get("formula") or ""), lang)], unc, lang)
    elif where == "ph":
        j, _ = ph_job(str(req.get("mixture") or ""), req.get("T") or 25, unc, lang)
        res = run_jobs([j], unc, lang)
    else:
        raise UN.UncError("unbekannter Bereich")
    hit = next((r for r in res if r.get("name") == name), res[0] if res else None)
    if not hit or not hit.get("compare"):
        raise UN.UncError((hit or {}).get("error") or "kein Ergebnis")
    return hit["compare"]
