"""CSV-Ausgabe (Spezifikation 6.1): Semikolon, UTF-8 mit BOM, Dezimalkomma."""
from __future__ import annotations

from pathlib import Path

from ..analyse import PHASES, Result


def _n(v, nd=4) -> str:
    if v is None:
        return ""
    return f"{v:.{nd}f}".rstrip("0").rstrip(".").replace(".", ",") if nd else str(v)


def rows(r: Result):
    p = r.prep
    eps_unit = "Dehnung scheinbar [%]" if r.config.displacement_source != "probe" else "Dehnung [%]"
    head = ["Index", "Zeitstempel", "Zeit grob [s]", "Zeit fein [s]", "Kraft mit Vorzeichen [N]",
            "Kraft Betrag [N]", "Spannung [MPa]", eps_unit, f"Weg [{r.device['displacement_unit']}]",
            f"Phase (Schwelle {_n(r.config.yield_threshold * 100, 2)} %)", "Lastabfall-Marke"]
    yield head
    v, l0, a0 = r.v_mm_s, r.l0, r.a0
    t0 = r.t0 + p.t_fine[0]  # Dehnung ab Fusspunkt, in der Setzphase negativ
    for i in range(p.n_total):
        sigma = p.force_abs[i] / a0 if a0 else None
        eps = (p.t_fine[i] - t0) * v / l0 * 100 if (v and l0) else None
        yield [str(i), p.timestamps[i].strftime("%d.%m.%Y %H:%M:%S"), _n(p.t_coarse[i], 0),
               _n(p.t_fine[i], 4), _n(p.force_raw[i], 3), _n(p.force_abs[i], 3),
               _n(sigma, 3) if sigma is not None else "", _n(eps, 4) if eps is not None else "",
               _n(p.displacement[i], 3), PHASES[int(r.phases[i])],
               "1" if (r.drop_idx is not None and i == r.drop_idx) else "0"]


def write_csv(r: Result, folder: Path) -> Path:
    path = folder / f"{r.name}.csv"
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        for row in rows(r):
            fh.write(";".join(row) + "\r\n")
    return path


def write_notes(r: Result, folder: Path) -> Path:
    """Pflichtwarnungen (Abschnitt 7) als Begleittext zur CSV."""
    path = folder / f"{r.name}_Hinweise.txt"
    lines = [f"Hinweise zur Auswertung {r.name}", ""]
    for w in r.warnings:
        lines.append(f"[{w['code']}] {w['text']}")
    path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8-sig")
    return path
