"""Reaktionstyp als Vorschlag aus Gleichung, Elektronenbilanz und Stoffdaten (Lehrbuch-Einteilung, Atkins 2018).

Regeln, in dieser Reihenfolge geprüft; mehrere Typen können zutreffen:
- Halbreaktion: Elektronen in der Gleichung.
- Redoxreaktion: Oxidationszahlen ändern sich (labcalc.redox); Unterfälle Verbrennung (O₂ als Edukt, CO₂/H₂O als
  Produkt), Disproportionierung, Komproportionierung, Verdrängung (Element + Verbindung → Element + Verbindung).
- Säure–Base: keine Redoxreaktion, ein Edukt gibt Protonen ab und ein anderes nimmt sie auf (pKa-Daten, starke Säuren
  und Basen nach Harris 2016); Neutralisation, wenn dabei Wasser entsteht.
- Fällung: keine Redoxreaktion, ein Produkt ist als Feststoff angegeben oder schwer löslich (molare Löslichkeit aus
  Ksp unter 0,01 mol/L), die Edukte enthalten Ionen bzw. lösliche Salze.
- Komplexbildung: Metallion als Edukt, Produkt enthält dasselbe Metall mit weiteren Liganden als Ion bzw. in [ ].
- Synthese (mehrere Edukte → ein Produkt), Zersetzung (ein Edukt → mehrere Produkte), doppelte Umsetzung.
"""
from __future__ import annotations

from . import chem as C


def _p(sp):
    from .redox import _plain
    return _plain(sp)


def _ab_role(sp: C.Species) -> tuple[bool, bool, str | None]:
    """(kann Protonen abgeben, kann Protonen aufnehmen, Systemschlüssel) eines Stoffs."""
    from . import acidbase as AB
    try:
        c = AB.component(sp.text if not sp.name else sp.name, 1.0)
    except C.ChemError:
        return False, False, None
    acid = c["strong_acid"] > 0
    base = c["strong_base"] > 0
    key = None
    for y in c["systems"]:
        js = sorted(y["steps"])
        acid = acid or y["h"] > js[0] - 1
        base = base or y["h"] < js[-1]
        key = y["key"]
    return acid, base, key


def classify(eq: C.Equation, coefs, redox: dict | None) -> list[dict]:
    out = []
    terms = [t for t in eq.terms if t.species.kind in ("chem", "electron")]
    if eq.nuclear:
        return [{"key": "nuclear", "de": "Kernreaktion", "en": "nuclear reaction"}]
    react = [t.species for t in terms if t.side < 0 and t.species.kind == "chem"]
    prod = [t.species for t in terms if t.side > 0 and t.species.kind == "chem"]
    if any(t.species.kind == "electron" for t in terms):
        kind = (redox or {}).get("kind") or "Halbreaktion"
        return [{"key": "half", "de": f"Halbreaktion ({kind})", "en": "half-reaction",
                 "why": "Elektronen stehen in der Gleichung"}]
    if redox and redox.get("redox"):
        why = f"{', '.join(redox.get('oxidized', []))} wird oxidiert, {', '.join(redox.get('reduced', []))} reduziert"
        out.append({"key": "redox", "de": "Redoxreaktion", "en": "redox reaction", "why": why})
        hp = {_p(s)[0] for s in prod}
        if any(_p(s) == ("O2", 0) for s in react) and ({"CO2", "H2O"} & hp):
            out.append({"key": "combustion", "de": "Verbrennung", "en": "combustion",
                        "why": "O₂ als Edukt, CO₂ bzw. H₂O als Produkt"})
        if redox.get("disproportionation"):
            out.append({"key": "disproportionation", "de": "Disproportionierung", "en": "disproportionation",
                        "why": f"{', '.join(redox['disproportionation'])} wird zugleich oxidiert und reduziert"})
        if redox.get("comproportionation"):
            out.append({"key": "comproportionation", "de": "Komproportionierung", "en": "comproportionation",
                        "why": f"{', '.join(redox['comproportionation'])} aus zwei Stufen zu einer"})
        el_r = [s for s in react if len(s.counts) == 1 and s.charge == 0]
        el_p = [s for s in prod if len(s.counts) == 1 and s.charge == 0]
        if len(react) == 2 and len(prod) == 2 and len(el_r) == 1 and len(el_p) == 1:
            out.append({"key": "displacement", "de": "Verdrängungsreaktion", "en": "single displacement",
                        "why": "Element + Verbindung → Element + Verbindung"})
    elif redox is not None and redox.get("redox") is False:
        roles = [(s, *_ab_role(s)) for s in react]
        acids = [r for r in roles if r[1]]
        bases = [r for r in roles if r[2]]
        if acids and bases and any(a[0] is not b[0] for a in acids for b in bases):
            water = any(_p(s) == ("H2O", 0) for s in prod)
            out.append({"key": "acidbase", "de": "Neutralisation (Säure–Base)" if water else "Säure–Base-Reaktion",
                        "en": "neutralisation" if water else "acid–base reaction",
                        "why": f"Protonendonator {acids[0][0].unicode()}, Protonenakzeptor "
                               f"{next(b[0] for b in bases if b[0] is not acids[0][0]).unicode()}"})
        from . import substances as S

        def has_ksp(s):
            """schwer löslich: molare Löslichkeit aus Ksp unter 0,01 mol/L"""
            if s.charge or len(s.counts) < 2:
                return False
            return S.sparingly_soluble(s.text)
        ionic_in = any(s.charge or s.phase == "aq" for s in react)
        solid = [s for s in prod if s.phase in ("s", "cr")] or [s for s in prod if has_ksp(s)]
        # Salzlösungen ohne Phasenangabe (AgNO₃ + NaCl): Edukte, die nicht schwer löslich sind, gelten als gelöst
        soluble_in = ionic_in or (len(react) >= 2 and not any(has_ksp(s) for s in react))
        if solid and soluble_in:
            out.append({"key": "precipitation", "de": "Fällung", "en": "precipitation",
                        "why": f"{solid[0].unicode()} fällt aus (schwer löslich)"})
        metal_ions = [s for s in react if s.charge > 0 and len(s.counts) == 1]
        for mi in metal_ions:
            el = next(iter(mi.counts))
            if any(el in s.counts and len(s.counts) > 1 and (s.charge or "[" in s.text) for s in prod):
                out.append({"key": "complex", "de": "Komplexbildung", "en": "complex formation",
                            "why": f"{mi.unicode()} bindet Liganden"})
                break
    if len(react) >= 2 and len(prod) == 1:
        out.append({"key": "synthesis", "de": "Synthese (Aufbau)", "en": "synthesis", "why": "mehrere Edukte → ein Produkt"})
    elif len(react) == 1 and len(prod) >= 2:
        out.append({"key": "decomposition", "de": "Zersetzung", "en": "decomposition", "why": "ein Edukt → mehrere Produkte"})
    elif len(react) == 2 and len(prod) == 2 and not (redox or {}).get("redox") and \
            not any(o["key"] in ("acidbase",) for o in out) and all(len(s.counts) >= 2 for s in react + prod):
        out.append({"key": "metathesis", "de": "Doppelte Umsetzung", "en": "double displacement",
                    "why": "Ionen tauschen die Partner"})
    return out
