"""Baut sdk/python/labcalc/data/ionization.json aus dem CSV-Export der NIST ASD (Ionisierungsenergien).

Aufruf (Daten aus dem Netz nur mit -I lesen):
    python -I tools/build_ie.py <ie.csv> <ziel.json>
Export: https://physics.nist.gov/cgi-bin/ASD/ie.pl, spectra=H-Ds, units=eV, format=CSV, mit Unsicherheit und
Literaturschlüssel. Kennzeichnung der ASD: Wert in ( ) theoretisch/abgeleitet, in [ ] halbempirisch/extrapoliert.
"""
import csv
import json
import sys
from datetime import date


def clean(s: str) -> str:
    s = (s or "").strip()
    if s.startswith('="') and s.endswith('"'):
        s = s[2:-1]
    return s.strip()


def main(src: str, dst: str) -> None:
    out = {}
    with open(src, encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    for r in rows[1:]:
        if len(r) < 9:
            continue
        z, sp, q, name, pre, val, suf, unc, ref = (clean(x) for x in r[:9])
        try:
            zi, qi, v = int(z), int(q.replace("+", "")), float(val)
        except ValueError:
            continue
        flag = "theo" if pre == "(" else ("semi" if pre == "[" else "")
        try:
            u = float(unc) if unc else None
        except ValueError:
            u = None
        out.setdefault(str(zi), {"name": name, "ie": []})["ie"].append([qi, v, u, flag, ref])
    for e in out.values():
        e["ie"].sort()
    meta = {"_source": "NIST Atomic Spectra Database, Ionization Energies (Kramida, Ralchenko, Reader & NIST ASD Team)",
            "_doi": "10.18434/T4W30F", "_accessed": date.today().isoformat(), "_units": "eV",
            "_licence": "NIST Standard Reference Data (SRD 78), copyright U.S. Secretary of Commerce, all rights reserved; "
                        "not redistributed with Folio Lab, built on the user's computer by tools/fetch_optional_data.py",
            "_flags": {"theo": "( ) theoretical or derived", "semi": "[ ] semi-empirical or extrapolated"}}
    with open(dst, "w", encoding="utf-8") as fh:
        json.dump({**meta, "elements": out}, fh, ensure_ascii=False, separators=(",", ":"))
    print(len(out), "elements,", sum(len(e["ie"]) for e in out.values()), "values")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
