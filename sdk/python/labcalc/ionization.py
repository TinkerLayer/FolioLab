"""Ionisierungsenergien aus der NIST Atomic Spectra Database (ER-X02), gebündelt in data/ionization.json.

ie(symbol, n): n-te Ionisierungsenergie in eV (n = 1: neutrales Atom -> einfach geladenes Ion).
Werte in ( ) der ASD sind theoretisch/abgeleitet, in [ ] halbempirisch/extrapoliert – als flag mitgegeben.
"""
from __future__ import annotations

from functools import lru_cache

from . import chem as C

from .units import E_CHARGE, FARADAY

EV_J = E_CHARGE                # 1 eV in J, exakt (SI 2019: e·1 V)
EV_KJMOL = FARADAY / 1000      # 1 eV je Teilchen in kJ/mol = N_A·e·1 V/1000, exakt aus den definierenden Konstanten
REFS = ["nistasd"]


@lru_cache(maxsize=1)
def _data() -> dict:
    return C._json("ionization.json") or {}


def z_of(symbol: str) -> int:
    syms = C.SYMBOLS.split() if isinstance(C.SYMBOLS, str) else list(C.SYMBOLS)
    s = str(symbol).strip()
    if s not in syms:
        raise C.ChemError(f"unbekanntes Element {symbol}")
    return syms.index(s) + 1


def register_calc_functions():
    from . import expr as E
    from .units import D0, kind_dims
    # IE trägt die Dimension Energie (Wert intern in J); „IE("Na") -> eV“ zeigt eV.
    E.register_string_function("IE", lambda ctx, el, n=1: ie(z_of(str(el)), int(n))["eV"] * EV_J, 1, 2,
                               kind_dims("energy"),
                               'IE("Na", 1) – n-te Ionisierungsenergie als Energie (NIST ASD); „-> eV“ zeigt eV')
    # bisheriges Verhalten: reine Zahl in eV (dimensionslos)
    E.register_string_function("IE_eV", lambda ctx, el, n=1: ie(z_of(str(el)), int(n))["eV"], 1, 2, D0,
                               'IE_eV("Na", 1) – n-te Ionisierungsenergie als Zahl in eV (dimensionslos)')


def series(Z: int) -> list[dict]:
    e = (_data().get("elements") or {}).get(str(int(Z)))
    if not e:
        return []
    return [{"n": q + 1, "eV": v, "u": u, "flag": f, "ref": r, "kJmol": v * EV_KJMOL} for q, v, u, f, r in e["ie"]]


def ie(Z: int, n: int = 1) -> dict:
    s = [x for x in series(Z) if x["n"] == n]
    if not s:
        raise C.ChemError(f"keine {n}. Ionisierungsenergie für Z = {Z} in der NIST ASD")
    return s[0]
