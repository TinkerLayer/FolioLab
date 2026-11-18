"""Ausgaben (Spezifikation Abschnitt 6). Je Format ein Modul."""
from __future__ import annotations

import shutil
from pathlib import Path

from ..analyse import Result


def output_folder(r: Result, root: Path) -> Path:
    return Path(root) / r.name


def write_all(r: Result, root: Path, overwrite: bool = False, formats=None) -> list[Path]:
    """Schreibt alle Ausgaben in einen Ordner je Messung, benannt nach der Quelldatei.

    Existiert der Ordner bereits, wird ohne overwrite=True nichts ueberschrieben (FileExistsError).
    """
    from .charts import write_pngs
    from .csv_export import write_csv, write_notes
    from .pdf_export import write_datasheet, write_image_appendix
    from .report import write_report
    from .xlsx_export import write_xlsx

    formats = set(formats or ("csv", "xlsx", "png", "pdf", "bericht"))
    folder = output_folder(r, root)
    if folder.exists() and any(folder.iterdir()):
        if not overwrite:
            raise FileExistsError(str(folder))
    folder.mkdir(parents=True, exist_ok=True)

    # zuerst in einen Arbeitsordner schreiben, damit eine fehlerhafte Mappe nichts Bestehendes zerstoert
    work = folder.parent / (folder.name + ".~arbeit")
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    try:
        written: list[Path] = []
        if "csv" in formats:
            written += [write_csv(r, work), write_notes(r, work)]
        if "xlsx" in formats:
            written.append(write_xlsx(r, work))
        if "png" in formats:
            written += write_pngs(r, work)
        if "pdf" in formats:
            written += [write_datasheet(r, work), write_image_appendix(r, work)]
        if "bericht" in formats:
            written.append(write_report(r, work))
        final = []
        for p in written:
            dest = folder / p.name
            if dest.exists():
                dest.unlink()
            shutil.move(str(p), str(dest))
            final.append(dest)
        return final
    finally:
        shutil.rmtree(work, ignore_errors=True)


def comparison_path(results: list[Result], root: Path) -> Path:
    names = " + ".join(r.name for r in results)
    if len(names) > 80:
        names = names[:77] + "..."
    return Path(root) / "Vergleiche" / f"Vergleich {names}.pdf"


def write_comparison(results: list[Result], root: Path, overwrite: bool = False) -> Path:
    """Vergleichsbericht mehrerer Messungen unter <root>/Vergleiche. Ueberschreibt nur mit overwrite=True."""
    from .report import write_comparison_report
    if len({r.mode for r in results}) > 1:
        raise ValueError("Messungen in Kraft und in Spannung lassen sich nicht in einem Bericht vergleichen. "
                         "A₀ für alle Messungen eingeben oder bei allen leer lassen.")
    path = comparison_path(results, root)
    if path.exists() and not overwrite:
        raise FileExistsError(str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    return write_comparison_report(results, path)
