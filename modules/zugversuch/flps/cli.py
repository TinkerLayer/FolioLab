"""Kommandozeilenaufruf fuer Stapelverarbeitung (Spezifikation 9.1).

Beispiel:
  python -m flps.cli "Messung UNgekocht.flps" --form "ISO 527-2 Typ 5B" --dicke 0.1 --v 1 --weg traverse
  python -m flps.cli *.flps --a0 0.2 --l0 10 --aus Ausgaben --ueberschreiben
  python -m flps.cli a.flps b.flps --form "DIN 50125 B 6×30" --werkstoff-ref S235JR --vergleich
  python -m flps.cli rohr.flps --manuell --rohr 10 1 --l0 50 --gruppe "alle Metalle"
  python -m flps.cli --liste-werkstoffe --liste-proben
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

from . import alloys as alloys_mod
from .analyse import MANUAL_SHAPE, SHAPES, Config, fmt, result_to_dict, run
from .export import comparison_path, write_all, write_comparison
from .parser import parse_file


def build_config(a) -> Config:
    manual = a.manuell or not a.form
    shape = {} if manual else SHAPES[a.form]
    if a.rohr:
        section = "rohr"
    elif a.d is not None or shape.get("section") == "rund":
        section = "rund"
    else:
        section = "rechteckig"
    cfg = Config(
        specimen_mode="manuell" if manual else "norm",
        shape=MANUAL_SHAPE if manual else a.form,
        section=section,
        width_mm=a.b if a.b is not None else shape.get("b"),
        thickness_mm=a.dicke,
        diameter_mm=a.d if a.d is not None else (shape.get("d") if section == "rund" else None),
        outer_d_mm=a.rohr[0] if a.rohr else None, wall_mm=a.rohr[1] if a.rohr else None,
        a0_mm2=a.a0,
        l0_mm=a.l0 if a.l0 is not None else shape.get("L0"),
        speed_mm_min=a.v, displacement_source=a.weg,
        material=a.werkstoff or "", material_ref=a.werkstoff_ref, compare_group=a.gruppe,
        batch=a.charge or "", operator=a.pruefer or "", remark=a.bemerkung or "",
        yield_threshold=a.schwelle / 100.0,
    )
    return cfg


def _print_catalogues(a, alloy_list) -> bool:
    if a.liste_werkstoffe:
        for cat in alloys_mod.categories(alloy_list):
            print(f"== {cat}")
            for x in alloy_list:
                if x.category == cat:
                    rp = fmt(x.rp, 0) if x.rp else "–"
                    print(f"   {x.name:<34} Rm {fmt(x.rm, 0):>5}  Rp {rp:>5}  A {fmt(x.a_pct, 0):>4} %  "
                          f"E {fmt(x.e_gpa, 1):>6} GPa")
        print("Vergleichsgruppen: " + ", ".join(alloys_mod.groups(alloy_list)))
    if a.liste_proben:
        groups: dict[str, list[str]] = {}
        for name, sh in SHAPES.items():
            groups.setdefault(sh.get("gruppe") or "weitere", []).append(name)
        for g, names in groups.items():
            print(f"== {g}")
            for name in names:
                sh = SHAPES[name]
                dims = ", ".join(f"{k} {fmt(sh[k], 2)}" for k in ("b", "d", "L0", "h") if sh.get(k) is not None)
                print(f"   {name:<34} {sh.get('section', ''):<10} {dims}")
    return bool(a.liste_werkstoffe or a.liste_proben)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="flps", description="Auswertung von IMADA .flps Zugversuchen")
    ap.add_argument("dateien", nargs="*", help=".flps Dateien (Platzhalter erlaubt)")
    ap.add_argument("--form", choices=list(SHAPES), metavar="NORMPROBE",
                    help="Normprobe (siehe --liste-proben), füllt b bzw. d und L0 vor")
    ap.add_argument("--manuell", action="store_true", help="freie Abmessungen ohne Normbezug")
    ap.add_argument("--b", type=float, help="Stegbreite b [mm]")
    ap.add_argument("--dicke", type=float, help="Dicke [mm]")
    ap.add_argument("--d", type=float, help="Durchmesser einer Rundprobe [mm]")
    ap.add_argument("--rohr", type=float, nargs=2, metavar=("D", "T"), help="Rohr: Aussendurchmesser und Wanddicke [mm]")
    ap.add_argument("--werkstoff-ref", metavar="NAME", help="Referenzwerkstoff aus der Datenbank (siehe --liste-werkstoffe)")
    ap.add_argument("--gruppe", metavar="GRUPPE", help="Vergleichsgruppe, z. B. Stahl, Kunststoff, 'alle Metalle'")
    ap.add_argument("--vergleich", action="store_true", help="zusätzlich einen Vergleichsbericht aller Dateien schreiben")
    ap.add_argument("--liste-werkstoffe", action="store_true", help="Werkstoffdatenbank anzeigen")
    ap.add_argument("--liste-proben", action="store_true", help="Normproben anzeigen")
    ap.add_argument("--a0", type=float, help="Querschnittsfläche A0 [mm²], überschreibt die Geometrie")
    ap.add_argument("--l0", type=float, help="Messlänge L0 [mm]")
    ap.add_argument("--v", type=float, help="Vorschubgeschwindigkeit [mm/min]")
    ap.add_argument("--weg", choices=["probe", "traverse"], help="Weg an der Probe gemessen oder Traversenweg")
    ap.add_argument("--werkstoff"), ap.add_argument("--charge"), ap.add_argument("--pruefer")
    ap.add_argument("--bemerkung")
    ap.add_argument("--schwelle", type=float, default=2.0, help="Schwelle Fliessbeginn in %% (Vorgabe 2)")
    ap.add_argument("--legierungen", help="Pfad zu alloys.json")
    ap.add_argument("--aus", default="Ausgaben", help="Wurzelordner der Ausgaben")
    ap.add_argument("--formate", default="csv,xlsx,png,pdf,bericht",
                    help="Auswahl aus csv, xlsx, png, pdf, bericht (grafischer Bericht)")
    ap.add_argument("--ueberschreiben", action="store_true", help="vorhandene Ausgaben ohne Rückfrage ersetzen")
    ap.add_argument("--json", action="store_true", help="Ergebnis als JSON ausgeben, nichts schreiben")
    a = ap.parse_args(argv)

    alloy_list = alloys_mod.load_alloys(a.legierungen)
    if _print_catalogues(a, alloy_list):
        return 0
    if not a.dateien:
        ap.error("keine .flps Datei angegeben")
    if a.werkstoff_ref and alloys_mod.find(alloy_list, a.werkstoff_ref) is None:
        ap.error(f"Referenzwerkstoff '{a.werkstoff_ref}' unbekannt (siehe --liste-werkstoffe)")
    if a.gruppe and a.gruppe not in alloys_mod.groups(alloy_list):
        ap.error(f"Vergleichsgruppe '{a.gruppe}' unbekannt. Möglich: {', '.join(alloys_mod.groups(alloy_list))}")
    files = []
    for pat in a.dateien:
        files += glob.glob(pat) or [pat]
    cfg = build_config(a)
    rc = 0
    results = []
    for fp in files:
        try:
            r = run(parse_file(fp), cfg, alloy_list)
        except Exception as e:  # noqa: BLE001
            print(f"{fp}: Fehler: {e}", file=sys.stderr)
            rc = 1
            continue
        results.append(r)
        if a.json:
            print(json.dumps(result_to_dict(r, include_series=False), ensure_ascii=False, indent=1))
            continue
        kv = r.kv
        print(f"== {r.name} ({r.device['model']}, SN {r.device['serial']})")
        print(f"   {kv['n_active']} aktiv, {kv['n_cut']} abgeschnitten, {fmt(kv['rate_hz'], 1, 'Hz')}, {kv['test_type']}versuch")
        print(f"   Fmax {fmt(kv['max']['F'], 1, 'N')} bei {fmt(kv['max']['t'], 1, 's')}"
              + (f", Rm {fmt(kv['Rm'], 0, 'MPa')}" if r.a0 else ""))
        for w in r.warnings:
            if w["level"] != "info":
                print(f"   ! [{w['code']}] {w['text']}")
        if a.formate:
            if not a.ueberschreiben and (Path(a.aus) / r.name).exists():
                ans = input(f"   Ausgabeordner {Path(a.aus) / r.name} existiert. Überschreiben? [j/N] ") \
                    if sys.stdin.isatty() else "n"
                if ans.strip().lower() not in ("j", "ja", "y", "yes"):
                    print("   übersprungen, nichts überschrieben")
                    continue
            out = write_all(r, Path(a.aus), overwrite=True, formats=a.formate.split(","))
            print(f"   {len(out)} Dateien in {Path(a.aus) / r.name}")
    if a.vergleich and not a.json:
        if len(results) < 2:
            print("Vergleichsbericht braucht mindestens zwei Messungen.", file=sys.stderr)
            return rc or 1
        path = comparison_path(results, Path(a.aus))
        if path.exists() and not a.ueberschreiben:
            ans = input(f"{path} existiert. Überschreiben? [j/N] ") if sys.stdin.isatty() else "n"
            if ans.strip().lower() not in ("j", "ja", "y", "yes"):
                print("Vergleichsbericht übersprungen, nichts überschrieben")
                return rc
        try:
            print(f"Vergleichsbericht: {write_comparison(results, Path(a.aus), overwrite=True)}")
        except ValueError as e:
            print(f"Vergleichsbericht: {e}", file=sys.stderr)
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
