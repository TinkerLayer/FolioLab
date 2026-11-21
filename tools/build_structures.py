"""Build `modules/werkstoffe/werk/data/structures.json` from the Crystallography Open Database (COD).

COD data are in the public domain (https://www.crystallography.net/cod/, "COD data are placed in the public
domain"). For every phase below the script searches COD by formula, keeps entries with coordinates and the expected
space group, prefers entries with a DOI that were measured near room temperature, downloads the CIF, reads it with
the Werkstoffe CIF reader and checks that the cell content matches the formula. The chosen COD number and the
publication are stored with the phase, so the structure can be cited.

Usage (needs network access; writes only the data file and a download folder you give):

    python tools/build_structures.py --download-dir <empty folder>

Phases that COD does not hold (martensite, ε-carbide, θ′, γ″ …) are written by hand in
`modules/werkstoffe/werk/data/structures_lit.json` with their literature source; this script does not touch them.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "sdk" / "python"), str(ROOT / "modules" / "werkstoffe")]
from werk import cryst  # noqa: E402

UA = "FolioLab-structure-builder"
OUT = ROOT / "modules" / "werkstoffe" / "werk" / "data" / "structures.json"

# id, German name, English name, COD formula (Hill order, as COD stores it), space-group numbers accepted (first
# preferred), optional filter on the cell (a, c ranges), optional preferred COD number.
PHASES = [
    ("fe3c", "Zementit Fe₃C", "Cementite Fe₃C", "C Fe3", [62], None, None),
    ("graphit", "Graphit", "Graphite", "C", [194], {"c": (6.5, 6.9)}, None),
    ("cr23c6", "Chromcarbid Cr₂₃C₆", "Chromium carbide Cr₂₃C₆", "C6 Cr23", [225], None, None),
    ("mo2c", "Molybdäncarbid Mo₂C", "Molybdenum carbide Mo₂C", "C Mo2", [60, 194], None, None),
    ("nbc", "Niobcarbid NbC", "Niobium carbide NbC", "C Nb", [225], None, None),
    ("al2cu-theta", "θ-Al₂Cu", "θ-Al₂Cu", "Al2 Cu", [140], None, None),
    ("al2cumg-s", "S-Phase Al₂CuMg", "S phase Al₂CuMg", "Al2 Cu Mg", [63], None, None),
    ("mg2si", "β-Mg₂Si", "β-Mg₂Si", "Mg2 Si", [225], None, None),
    ("mgzn2", "η-MgZn₂", "η-MgZn₂", "Mg Zn2", [194], None, None),
    ("cuzn-beta", "β′-CuZn (geordnet)", "β′-CuZn (ordered)", "Cu Zn", [221], None, None),
    ("cu3sn-eps", "ε-Cu₃Sn", "ε-Cu₃Sn", "Cu3 Sn", [63, 194], None, None),
    ("ni3nb-delta", "δ-Ni₃Nb", "δ-Ni₃Nb", "Nb Ni3", [59], None, None),
    ("ti3al", "α₂-Ti₃Al", "α₂-Ti₃Al", "Al Ti3", [194], None, None),
    ("mg17al12", "β-Mg₁₇Al₁₂", "β-Mg₁₇Al₁₂", "Al12 Mg17", [217], None, None),
    ("sn-beta", "β-Zinn", "β-tin", "Sn", [141], None, None),
    ("sn-alpha", "α-Zinn (grau)", "α-tin (grey)", "Sn", [227], None, None),
    ("sic-6h", "α-SiC (6H)", "α-SiC (6H)", "C Si", [186], {"c": (14.9, 15.3)}, None),
    ("sic-3c", "β-SiC (3C)", "β-SiC (3C)", "C Si", [216], None, None),
    ("si3n4-beta", "β-Si₃N₄", "β-Si₃N₄", "N4 Si3", [176, 173], None, None),
    ("zro2-t", "tetragonales ZrO₂", "tetragonal ZrO₂", "O2 Zr", [137], None, None),
    ("zro2-m", "monoklines ZrO₂ (Baddeleyit)", "monoclinic ZrO₂ (baddeleyite)", "O2 Zr", [14], None, None),
    ("portlandit", "Portlandit Ca(OH)₂", "Portlandite Ca(OH)₂", "Ca H2 O2", [164], None, None),
    ("calcit", "Calcit CaCO₃", "Calcite CaCO₃", "C Ca O3", [167], {"a": (4.95, 5.0), "c": (16.9, 17.1)}, None),
    ("quarz", "α-Quarz", "α-quartz", "O2 Si", [154, 152], None, None),
    ("spodumen-beta", "β-Spodumen (Keatit-Typ)", "β-spodumene (keatite type)", "Al Li O6 Si2", [96, 92], None, None),
]


def get(url: str, tries: int = 3) -> bytes:
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            if k == tries - 1:
                raise
            print("  retry", url, e)
            time.sleep(3)
    raise RuntimeError("unreachable")


def formula_counts(formula: str) -> Counter:
    c = Counter()
    for el, n in re.findall(r"([A-Z][a-z]?)([\d.]*)", formula):
        c[el] += float(n) if n else 1.0
    return c


def ratio_ok(atoms: list[dict], formula: str) -> bool:
    want = formula_counts(formula)
    have = Counter()
    for a in atoms:
        have[a["el"]] += a.get("occ", 1.0)
    want.pop("H", None)                                   # H positions are often missing
    have.pop("H", None)
    if set(want) != set(have):
        return False
    k = next(iter(want))
    s = have[k] / want[k]
    return all(abs(have[e] / s - want[e]) <= 0.08 * max(1.0, want[e]) for e in want)


def score(row: dict, sgs: list[int]) -> tuple:
    t = row.get("celltemp") or row.get("diffrtemp")
    try:
        dt = abs(float(t) - 295) if t else 0.0
    except ValueError:
        dt = 0.0
    return (sgs.index(int(row["sgNumber"])), 0 if row.get("doi") else 1, dt > 30, -int(row.get("year") or 0) * 0)


def candidates(formula: str, sgs: list[int], cell_filter: dict | None) -> list[dict]:
    url = "https://www.crystallography.net/cod/result?" + urllib.parse.urlencode({"formula": formula, "format": "json"})
    rows = json.loads(get(url).decode("utf-8"))
    out = []
    for r in rows:
        if "has coordinates" not in (r.get("flags") or "") or r.get("duplicateof"):
            continue
        try:
            if int(r.get("sgNumber") or 0) not in sgs:
                continue
        except ValueError:
            continue
        if cell_filter:
            ok = True
            for k, (lo, hi) in cell_filter.items():
                try:
                    ok = ok and lo <= float(r[k]) <= hi
                except (TypeError, ValueError, KeyError):
                    ok = False
            if not ok:
                continue
        out.append(r)
    return sorted(out, key=lambda r: score(r, sgs))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--download-dir", required=True)
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    dl = Path(a.download_dir)
    dl.mkdir(parents=True, exist_ok=True)
    old = json.loads(OUT.read_text("utf-8")) if OUT.exists() else {"phasen": []}
    keep = {p["id"]: p for p in old.get("phasen", [])}
    for pid, de, en, formula, sgs, cf, pref in PHASES:
        if a.only and pid not in a.only:
            continue
        print(pid, formula, sgs)
        rows = candidates(formula, sgs, cf)
        if pref:
            rows = [r for r in rows if r["file"] == str(pref)] + [r for r in rows if r["file"] != str(pref)]
        chosen = None
        for r in rows[:6]:
            path = dl / f"{r['file']}.cif"
            if not path.exists():
                path.write_bytes(get(f"https://www.crystallography.net/cod/{r['file']}.cif"))
                time.sleep(0.5)
            try:
                ph = cryst.parse_cif(path.read_text("utf-8", errors="replace"))
                atoms = cryst.expand(ph)
            except Exception as e:  # noqa: BLE001
                print("  skip", r["file"], e)
                continue
            if not ratio_ok(atoms, formula.replace(" ", "")):
                print("  skip", r["file"], "content does not match the formula")
                continue
            chosen = (r, ph, len(atoms))
            break
        if not chosen:
            print("  NOT FOUND")
            continue
        r, ph, n = chosen
        src = {"type": "article" if r.get("journal") else "misc", "authors": r.get("authors") or "",
               "title": (r.get("title") or "").strip() or f"{en}, COD {r['file']}",
               "container": r.get("journal") or "", "year": r.get("year") or "", "volume": r.get("volume") or "",
               "pages": "-".join(x for x in (r.get("firstpage"), r.get("lastpage")) if x),
               "doi": r.get("doi") or "", "url": f"https://www.crystallography.net/cod/{r['file']}.html",
               "note": f"Struktur aus der Crystallography Open Database, COD {r['file']} (gemeinfrei)"}
        keep[pid] = {"id": pid, "name": de, "name_en": en, "formula": formula.replace(" ", ""),
                     "system": ph["system"], "spacegroup": r.get("sg") or ph["spacegroup"],
                     "sg_number": int(r["sgNumber"]), "cell": ph["cell"], "centring": "P", "ops": ph["ops"],
                     "atoms": [{k: v for k, v in at.items() if k in ("el", "x", "y", "z", "occ", "label")}
                               for at in ph["atoms"]],
                     "cod": int(r["file"]), "T_messung": r.get("celltemp") or r.get("diffrtemp"),
                     "source": src, "q": "COD"}
        print(f"  COD {r['file']}: {r.get('sg')}, {n} atoms per cell, {(r.get('authors') or '')[:60]} {r.get('year')}")
    data = {"_format": "folio-structures/1",
            "_hinweis": "Kristallstrukturen aus der Crystallography Open Database (gemeinfrei), gebaut mit "
                        "tools/build_structures.py; Quelle und COD-Nummer je Phase.",
            "phasen": [keep[k] for k in sorted(keep)]}
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print("written", OUT, len(data["phasen"]), "phases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
