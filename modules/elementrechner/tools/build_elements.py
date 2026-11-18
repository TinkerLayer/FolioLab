"""PubChem-Periodensystem (CSV) -> sdk/python/labcalc/data/elements.json.

    python -I tools/build_elements.py <periodictable.csv>

Quelle: https://pubchem.ncbi.nlm.nih.gov/rest/pug/periodictable/CSV (Kim et al. 2021, Chem. Teach. Int. 3, 57-65),
abgerufen am 17.11.2026. PubChem stellt die Elementdaten aus den dort je Grösse genannten Primärquellen zusammen.
Atomgewichte kommen NICHT von hier (CIAAW 2024, atomic_weights.json).
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[3] / "sdk" / "python" / "labcalc" / "data" / "elements.json"


def num(s):
    s = (s or "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def ox_states(s):
    out = []
    for p in (s or "").replace(" ", "").split(","):
        if not p:
            continue
        try:
            out.append(int(p))
        except ValueError:
            pass
    return out


def main(src: str):
    els = {}
    with open(src, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            sym = r["Symbol"].strip()
            e = {"electron_configuration": r["ElectronConfiguration"].strip() or None,
                 "electronegativity": num(r["Electronegativity"]),
                 "oxidation_states": ox_states(r["OxidationStates"]),
                 "ionization_energy_eV": num(r["IonizationEnergy"]),
                 "electron_affinity_eV": num(r["ElectronAffinity"]),
                 "atomic_radius_pm": num(r["AtomicRadius"]),
                 "melting_point_K": num(r["MeltingPoint"]),
                 "boiling_point_K": num(r["BoilingPoint"]),
                 "density_g_cm3": num(r["Density"]),
                 "standard_state": r["StandardState"].strip() or None,
                 "group_block": r["GroupBlock"].strip() or None}
            els[sym] = {k: v for k, v in e.items() if v not in (None, [], "")}
    data = {"_source": "pubchem_pt", "_accessed": "2026-11-17",
            "_url": "https://pubchem.ncbi.nlm.nih.gov/rest/pug/periodictable/CSV",
            "_note": "Elektronegativität nach Pauling; Atomradius = Van-der-Waals-Radius; Ionisierungsenergie und "
                     "Elektronenaffinität in eV; Schmelz-/Siedepunkt in K; Dichte in g/cm³ (Gase bei 0 °C, 1 atm). "
                     "Oxidationsstufen: häufige Stufen laut PubChem.",
            "elements": els}
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=0, separators=(",", ":")), encoding="utf-8")
    print(len(els), "elements ->", OUT)


if __name__ == "__main__":
    main(sys.argv[1])
