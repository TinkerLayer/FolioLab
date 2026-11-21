"""Messunsicherheit in jedem Modulserver: gemeinsame Endpunkte ``/api/unc/<aktion>`` und eigene Messmittel der Suite.

Eigene Messmittel liegen für die ganze Suite in ``<suite>/messmittel.json`` (lesbar, von Hand editierbar, teilbar);
jedes Modul sieht dieselbe Liste. Die Rechnungen selbst stehen in ``labcalc.uncertainty``.

Aktionen:
    instruments                 → {"groups", "items"}  eingebaute Klassen (mit Quelle) und eigene
    own_save {item}             → gespeichertes Messmittel
    own_delete {id}             → {"ok"}
    own_export / own_import {data, replace}
    preview {value, unit, parts}→ Standardunsicherheit einer Eingabe (für das ±-Fenster)
    evaluate {expr, inputs, method | "all", corr, p, k, unit, label, name}
                                → Ergebnis eines Verfahrens oder aller vier (``compare``)
    methods                     → Verfahren mit Namen und Quellen
"""
from __future__ import annotations

from labcalc import uncertainty as UN
from labcalc.sources import REFS
from labproject import EnvError
from labuser import JsonStore

KIND = "folio-messmittel/1"


def store(envs) -> JsonStore:
    envs.ensure()
    return JsonStore(envs.suite.root / "messmittel.json", kind=KIND, max_items=500)


def load_own(envs) -> list[dict]:
    """Eigene Messmittel lesen und für ``labcalc.uncertainty`` bekannt machen (vor jeder Auswertung aufrufen)."""
    try:
        items = store(envs).items()
    except (OSError, ValueError, EnvError):
        items = []
    UN.set_own_instruments(items)
    return items


def methods(lang: str = "de") -> list[dict]:
    N = UN.NAMES.get(lang, UN.NAMES["de"])
    return [{"id": m, "name": N[m], "refs": [{"key": k, **REFS[k]} for k in UN.REF_KEYS[m] if k in REFS]}
            for m in UN.METHODS]


def route(envs, action: str, req: dict, lang: str | None = None):
    lang = lang or (req.get("lang") if req.get("lang") in ("de", "en") else "de")
    try:
        if action == "instruments":
            load_own(envs)
            d = UN._instr_data()
            items = UN.instruments(lang)
            for it in items:
                src = it.get("source")
                it["ref"] = {"key": src, **REFS[src]} if isinstance(src, str) and src in REFS else src
            return {"groups": [{"id": g, "name": n.get(lang, n["de"])} for g, n in d["groups"].items()],
                    "items": items, "methods": methods(lang)}
        if action == "methods":
            return {"methods": methods(lang)}
        if action == "own_save":
            it = UN.check_own_instrument(req.get("item") or {})
            st = store(envs)
            if not it.get("id"):
                it.pop("id", None)
            saved = st.put(it)
            load_own(envs)
            return saved
        if action == "own_delete":
            ok = store(envs).delete(str(req.get("id") or ""))
            load_own(envs)
            return {"ok": ok}
        if action == "own_export":
            return store(envs).export()
        if action == "own_import":
            data = req.get("data")
            items = data.get("items") if isinstance(data, dict) else data
            clean = []
            for x in items or []:
                try:
                    c = UN.check_own_instrument(x)
                    c["id"] = x.get("id")
                    clean.append(c)
                except UN.UncError:
                    continue
            n = store(envs).import_(clean, replace=bool(req.get("replace")))
            load_own(envs)
            return {"imported": n}
        if action == "preview":
            load_own(envs)
            return UN.standard_u({"parts": req.get("parts") or []}, req.get("value"), str(req.get("unit") or ""), lang)
        if action == "evaluate":
            load_own(envs)
            model = {"expr": str(req.get("expr") or "")}
            if not model["expr"]:
                raise UN.UncError("Modell (Ausdruck) fehlt")
            kw = dict(corr=req.get("corr"), p=req.get("p") or UN.P_DEFAULT, k=req.get("k") or None,
                      seed=int(req.get("seed") or 20261119), lang=lang, unit=str(req.get("unit") or ""),
                      label=str(req.get("label") or ""), name=str(req.get("name") or "y"))
            if (req.get("method") or "gum") == "all":
                return UN.compare(model, req.get("inputs") or [], **kw)
            return UN.evaluate(model, req.get("inputs") or [], req.get("method") or "gum", **kw)
    except UN.UncError as e:
        raise EnvError(str(e)) from None
    raise EnvError("unbekannte Aktion")
