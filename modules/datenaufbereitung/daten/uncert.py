"""Measurement uncertainty in datasets.

* ± / uncertainty columns → standard uncertainty u per row (`factor`, `std_u`), stating the conversion used
  (JCGM 100:2008, 4.2.2, 4.2.3, 4.3.3, 4.3.4).
* Formula columns: u per row with the linear GUM law of propagation for independent inputs
  (`labcalc.uncertainty.gum_rows`), written into a new uncertainty column linked with "u" (`formula_u`).
* Derived-dataset step "unc": a type-B uncertainty column from an instrument spec (`op_unc`); the parts are the shared
  format of `labcalc.uncertainty` (instrument classes from the shared library, limits, resolution, % of value …).
* Repeated measurements: mean, s, u = s/√n, ν = n − 1 (`repeats`, type A, JCGM 100:2008, 4.2).
"""
from __future__ import annotations

import math
import re

import numpy as np

from labcalc import uncertainty as UN
from labcalc import units as U

REF = "jcgm100"                     # labcalc.sources.REFS key
CITE = "unc-jcgm100"                # bib key used in the report
MAX_UNIQUE = 100_000                # distinct values a type-B column is evaluated for

TX = {
    "de": {"u": "Standardunsicherheit u (unverändert)",
           "se": "Standardfehler des Mittelwerts = Standardunsicherheit des Mittelwerts (JCGM 100:2008, 4.2.3)",
           "U": "u = U/k mit k = {k} (JCGM 100:2008, 4.3.3)",
           "sd": "u = s: Standardabweichung als Standardunsicherheit eines Einzelwerts (JCGM 100:2008, 4.2.2; "
                 "für einen Mittelwert aus n Werten die Art „Standardfehler“ wählen)",
           "ci": "u = halbe Breite / {z} ({lvl} %, Normalverteilung angenommen, JCGM 100:2008, 4.3.4)",
           "none": "Art der Unsicherheit nicht angegeben – nicht als Standardunsicherheit verwendet",
           "unit": "Einheit {u} passt nicht zu {v}"},
    "en": {"u": "standard uncertainty u (as given)",
           "se": "standard error of the mean = standard uncertainty of the mean (JCGM 100:2008, 4.2.3)",
           "U": "u = U/k with k = {k} (JCGM 100:2008, 4.3.3)",
           "sd": "u = s: standard deviation as the standard uncertainty of a single value (JCGM 100:2008, 4.2.2; "
                 "for a mean of n values choose “standard error”)",
           "ci": "u = half-width / {z} ({lvl} %, normal distribution assumed, JCGM 100:2008, 4.3.4)",
           "none": "type of uncertainty not stated – not used as a standard uncertainty",
           "unit": "unit {u} does not fit {v}"},
}


class UncColError(ValueError):
    pass


def _g(x, lang="de", sig=4) -> str:
    s = f"{float(x):.{sig}g}"
    return s.replace(".", ",") if lang == "de" else s


def factor(ucol: dict, lang: str = "de") -> tuple[float | None, str]:
    """Factor that turns the numbers of an uncertainty column into standard uncertainties, and the text saying how.
    None when the type is not stated (or incomplete)."""
    L = TX.get(lang, TX["de"])
    t = ucol.get("u_type") or ""
    if t in ("u", "se"):
        return 1.0, L[t]
    if t == "U" and ucol.get("u_k"):
        k = float(ucol["u_k"])
        return UN.standard_u({"parts": [{"kind": "U", "U": 1.0, "k": k}]}, 0.0)["u"], L["U"].format(k=_g(k, lang))
    if t == "sd":
        return UN.standard_u({"parts": [{"kind": "sd", "sd": 1.0, "n": 1}]}, 0.0)["u"], L["sd"]
    if t == "ci" and ucol.get("u_level"):
        lvl = float(ucol["u_level"])
        f = UN.standard_u({"parts": [{"kind": "ci", "half": 1.0, "level": lvl}]}, 0.0)["u"]
        return f, L["ci"].format(z=_g(1 / f, lang, 3), lvl=_g(lvl, lang))
    return None, L["none"]


def _col(cols, key):
    return next((c for c in cols if c["key"] == key), None)


def _scale(unit: str) -> tuple[float, tuple]:
    f, d, _ = U.parse_unit(unit or "")
    return f, d


def std_u(cols, data, key: str, lang: str = "de") -> tuple[np.ndarray | None, str]:
    """Standard uncertainty of value column `key` per row, in the unit of that column (via its "u" link)."""
    c = _col(cols, key)
    if not c or not c.get("u"):
        return None, ""
    uc = _col(cols, c["u"])
    if not uc or uc.get("dtype") != "number":
        return None, ""
    f, text = factor(uc, lang)
    if f is None:
        return None, text
    try:
        fu, du = _scale(uc.get("unit"))
        fv, dv = _scale(c.get("unit"))
    except U.UnitError as e:
        return None, str(e)
    if (uc.get("unit") or "") and not U.deq(du, dv):
        return None, TX.get(lang, TX["de"])["unit"].format(u=uc.get("unit"), v=c.get("unit") or "1")
    scale = f * (fu / fv if (uc.get("unit") or "") else 1.0)
    return np.asarray(data[uc["key"]], float) * scale, text


def _u_kind(unit: str) -> str:
    try:
        return "temp_diff" if U.kind_for_unit(unit or "1") == "temperature" else ""
    except U.UnitError:
        return ""


def formula_u(model, names: dict, cols, data, src: str, n: int, const_u: dict | None = None) -> tuple[np.ndarray | None, list[str], list[str]]:
    """u (SI) of a formula column per row: GUM linear law, independent inputs (`UN.gum_rows`).

    model: f(dict of SI values) → SI value; names: all SI values of the formula (columns and constants);
    const_u: standard uncertainties (SI) of constants, e.g. values taken from the project index.
    Returns (u in SI or None, names of the inputs with u, texts of inputs skipped)."""
    used = [k for k in dict.fromkeys(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", src)) if k in names]
    u_si, have, skipped = {}, [], []
    for k in used:
        if const_u and k in const_u:
            u_si[k] = const_u[k]
            have.append(k)
            continue
        c = _col(cols, k)
        if not c or not c.get("u"):
            continue
        u, why = std_u(cols, data, k)
        if u is None:
            skipped.append(f"{c['name']}: {why}" if why else c["name"])
            continue
        u_si[k] = u * _scale(c.get("unit"))[0]
        have.append(k)
    if not u_si:
        return None, [], skipped
    vals = {k: names[k] for k in used}
    r = UN.gum_rows(lambda X: model({**names, **X}), vals, u_si)
    uo = np.asarray(r["u"], float).copy()
    y = np.broadcast_to(np.asarray(r["value"], float), (n,))
    uo[~np.isfinite(y)] = np.nan
    for k, u in u_si.items():                        # a row without a stated u of an input has no u of the result
        x = np.broadcast_to(np.asarray(vals[k], float), (n,))
        uo[np.isfinite(x) & ~np.isfinite(u)] = np.nan
    return uo, have, skipped


def add_u_col(t, at: int, value_col: dict, u_vals: np.ndarray, note: str, name: str | None = None) -> dict:
    """Insert a standard-uncertainty column after position `at` and link `value_col` to it."""
    from labdataset import safe_key
    key = safe_key(f"u_{value_col['key']}", [c["key"] for c in t.cols])
    uc = {"key": key, "name": (name or f"u({value_col['name']})")[:120], "unit": value_col.get("unit") or "",
          "dtype": "number", "role": "uncertainty", "u_type": "u", "note": note[:200]}
    k = _u_kind(uc["unit"])
    if k:
        uc["kind"] = k
    t.cols.insert(at + 1, uc)
    t.data[key] = np.asarray(u_vals, float)
    value_col["u"] = key
    return uc


def op_unc(t, op: dict, lang: str = "de") -> str:
    """Derived-dataset step "unc": type-B standard uncertainty per row from an instrument spec on column `col`."""
    key = str(op.get("col") or "")
    idx = next((i for i, c in enumerate(t.cols) if c["key"] == key), None)
    if idx is None:
        raise UncColError(f"Spalte „{key}“ nicht im Datensatz")
    c = t.cols[idx]
    if c["dtype"] != "number":
        raise UncColError(f"Spalte „{c['name']}“ ist Text")
    parts = op.get("parts")
    if not isinstance(parts, list) or not parts or len(parts) > 20:
        raise UncColError("Messunsicherheit: Angaben fehlen")
    unit = c.get("unit") or ""
    x = np.asarray(t.data[key], float)
    uniq = np.unique(x[np.isfinite(x)])
    if uniq.size > MAX_UNIQUE:
        raise UncColError(f"Messunsicherheit: zu viele verschiedene Werte ({uniq.size} > {MAX_UNIQUE})")
    try:
        UN.make_input({"name": key, "value": float(uniq[0]) if uniq.size else 0.0, "unit": unit, "parts": parts}, lang)
        tab = {float(v): UN.make_input({"name": key, "value": float(v), "unit": unit, "parts": parts}, lang)["u"]
               for v in uniq}
    except UN.UncError as e:
        raise UncColError(str(e)) from None
    uB = np.array([tab.get(float(v), math.nan) if math.isfinite(v) else math.nan for v in x])
    labels = list(dict.fromkeys(p.get("label") or "" for p in
                                UN.make_input({"name": key, "value": float(uniq[0]) if uniq.size else 0.0, "unit": unit,
                                               "parts": parts}, lang)["parts"]))
    what = ", ".join(lb for lb in labels if lb)[:120]
    u0, how = std_u(t.cols, t.data, key)
    old = c.get("u")
    ub = add_u_col(t, idx, c, uB, f"Typ B: {what}", f"u_B({c['name']})")
    text = f"Typ-B-Unsicherheit u_B({c['name']}) aus {what}"
    if u0 is not None:
        tot = np.sqrt(np.where(np.isfinite(u0), u0, 0.0) ** 2 + uB ** 2)
        pos = next(i for i, cc in enumerate(t.cols) if cc["key"] == ub["key"])
        add_u_col(t, pos, c, tot, f"u = √(u_±² + u_B²); u_± {how}", f"u({c['name']}) gesamt")
        text += f"; mit der Angabe ± ({how}) quadratisch zu u({c['name']}) gesamt addiert"
    elif old:
        text += f"; die bisherige Angabe ist nicht verwendet ({how})"
    return text


def op_sources(ops) -> list[tuple[str, dict]]:
    """Sources of the instruments named in "unc" steps: (key, labcite record)."""
    from labcalc.sources import REFS
    out = []
    for o in ops or []:
        if (o or {}).get("op") != "unc":
            continue
        for p in o.get("parts") or []:
            if not isinstance(p, dict) or p.get("kind") != "instrument":
                continue
            try:
                src = UN.instrument(str(p.get("id") or "")).get("source")
            except UN.UncError:
                continue
            if isinstance(src, str) and src in REFS:
                out.append((f"unc-{src}", REFS[src]))
            elif isinstance(src, dict) and (src.get("title") or src.get("doi") or src.get("url")):
                out.append((f"unc-{p.get('id')}", src))
    return list({k: (k, r) for k, r in out}.values())


def repeats(values) -> dict:
    """Repeated measurement: mean, s (n − 1), u = s/√n, ν = n − 1 (type A, JCGM 100:2008, 4.2.2–4.2.3)."""
    vals = [float(v) for v in values if v is not None and math.isfinite(float(v))][:10000]
    if len(vals) < 2:
        raise UncColError("Wiederholmessung: mindestens zwei Zahlen wählen")
    try:
        r = UN.standard_u({"parts": [{"kind": "repeats", "values": vals}]}, float(np.mean(vals)))
    except UN.UncError as e:
        raise UncColError(str(e)) from None
    p = r["parts"][0]
    return {"n": int(p["n"]), "mean": float(p["mean"]), "s": float(p["s"]), "u": float(r["u"]), "dof": int(p["n"]) - 1,
            "values": vals}
