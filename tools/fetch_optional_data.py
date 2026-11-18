"""Download and build the optional reference data that Folio Lab may not redistribute.

The repository contains only data whose licence allows redistribution (THIRD_PARTY_NOTICES.md). The parts below are
free to use, but their terms forbid redistribution or commercial copying, or are unclear. This script downloads them
from the original publisher onto your computer and builds the files Folio Lab reads. Nothing is uploaded anywhere.
The built files are listed in .gitignore, so they never end up in a commit.

    python tools/fetch_optional_data.py --list                 what exists, licences, what is installed
    python tools/fetch_optional_data.py all                    download and build every part
    python tools/fetch_optional_data.py pka asd                only some parts
    python tools/fetch_optional_data.py all --from <folder>    use originals you downloaded yourself
                                                               (<folder>/<part>/<file name>, names as in --list)
    python tools/fetch_optional_data.py --remove all           delete the built files again (keeps the downloads)

Downloads are kept in tools/fetch_cache/ and reused; --refresh downloads again. Each built file records the URL,
date and SHA-256 of every original it was built from ("_fetched"), so a report can state exactly which data it used.
By running this script you accept the terms of each source, printed before the download. Read them: several allow
non-commercial use only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "tools" / "fetch_cache"
SDK = ROOT / "sdk" / "python"
SDK_DATA = SDK / "labcalc" / "data"
FTIR_DATA = ROOT / "modules" / "ftir" / "ftir" / "data"
ER_TOOLS = ROOT / "modules" / "elementrechner" / "tools"
FTIR_TOOLS = ROOT / "modules" / "ftir" / "tools"
sys.path.insert(0, str(SDK))

import laboptional  # noqa: E402

UA = "FolioLab-fetch_optional_data/0.1 (+https://github.com/FolioLab-OP/FolioLab)"

# part -> description, terms, citation, originals (sub folder, file name, URL), outputs (relative to ROOT)
PARTS = {
    "pka": {
        "title": "IUPAC Digitized pKa Dataset v2.4 (aqueous dissociation constants)",
        "terms": "CC BY-NC 4.0: non-commercial use only, with attribution. https://zenodo.org/records/7236452",
        "cite": "Zheng J. W., Lafontant-Joseph O., IUPAC Digitized pKa Dataset, Zenodo, doi:10.5281/zenodo.7236452; "
                "Zheng, Lafontant-Joseph, Green (2026), RSC Adv. 16, 21397, doi:10.1039/D6RA02418A",
        "files": [("pka", "Dissociation-Constants-v2.4.zip",
                   "https://zenodo.org/records/22878440/files/IUPAC/Dissociation-Constants-v2.4.zip?download=1")],
        "out": ["sdk/python/labcalc/data/pka.json"],
    },
    "srd46": {
        "title": "NIST SRD 46 v8.0, Critically Selected Stability Constants of Metal Complexes",
        "terms": "NIST Standard Reference Data: copyright U.S. Secretary of Commerce (15 U.S.C. 290e); the dataset "
                 "README grants use and derivative works. Not redistributed here because the two statements "
                 "conflict. https://data.nist.gov/od/id/mds2-2154",
        "cite": "NIST SRD 46 v8.0 (D. R. Burgess, after Martell & Smith, Critical Stability Constants), "
                "doi:10.18434/M32154",
        "files": [("srd46", "SRD 46 SQL.zip",
                   "https://data.nist.gov/od/ds/ark:/88434/mds2-2154/SRD%2046%20SQL.zip")],
        "out": ["sdk/python/labcalc/data/stability.json"],
    },
    "asd": {
        "title": "NIST Atomic Spectra Database (SRD 78), ionisation energies H to Ds",
        "terms": "NIST Standard Reference Data: copyright U.S. Secretary of Commerce, all rights reserved. "
                 "https://www.nist.gov/pml/atomic-spectra-database",
        "cite": "Kramida A., Ralchenko Yu., Reader J., NIST ASD Team, NIST Atomic Spectra Database, "
                "doi:10.18434/T4W30F",
        "files": [("asd", "ie.csv",
                   "https://physics.nist.gov/cgi-bin/ASD/ie.pl?spectra=H-Ds&units=1&format=2&order=0&at_num_out=on"
                   "&sp_name_out=on&ion_charge_out=on&el_name_out=on&e_out=0&unc_out=on&biblio=on"
                   "&submit=Retrieve+Data")],
        "out": ["sdk/python/labcalc/data/ionization.json"],
    },
    "burcat": {
        "title": "Burcat/Goos/Ruscic, Extended Third Millennium Thermodynamic Database (NASA-7 polynomials, ATcT)",
        "terms": "Free of charge with proper citation; sale, and copying into any commercial publication, need the "
                 "author's written agreement. https://burcat.technion.ac.il/ (mirror: respecth.elte.hu/burcat)",
        "cite": "Goos E., Burcat A., Ruscic B., Extended Third Millennium Ideal Gas and Condensed Phase "
                "Thermochemical Database for Combustion with Updates from Active Thermochemical Tables",
        "files": [("burcat", "BURCAT.THR.txt", "https://respecth.elte.hu/burcat/BURCAT.THR.txt"),
                  # the two open sources are needed to link the Burcat species to the bundled collection
                  ("nbs", "NBS_Tables_with_ErratumValues.csv",
                   "https://data.nist.gov/od/ds/mds2-2124/NBS_Tables_with_ErratumValues.csv"),
                  ("codata", "key1.html", "https://www.codata.info/resources/databases/key1.html")],
        "out": ["sdk/python/labcalc/data/optional/thermo_burcat.json"],
    },
    "openspecy": {
        "title": "Open Specy reference library: spectra from sources with non-commercial or unstated licences "
                 "(RRUFF, SWGDRUG, Kimmel Center, FLOPP, AWI 2024, Kozloski, PSLC and others)",
        "terms": "Per source; several are CC BY-NC, 'personal educational purposes' (RRUFF) or 'all rights "
                 "reserved' (SWGDRUG); others state no licence. Each spectrum keeps its source and licence. "
                 "https://osf.io/x7dpz",
        "cite": "Cowger W. et al. (2025), Open Specy 1.0, Anal. Chem., doi:10.1021/acs.analchem.5c00962; "
                "data doi:10.17605/OSF.IO/X7DPZ; plus the source of each spectrum",
        "files": [("openspecy", "nobaseline.rds", "https://osf.io/download/jy7zk/")],
        "out": ["modules/ftir/ftir/data/openspecy-restricted/meta.json",
                "modules/ftir/ftir/data/openspecy-restricted/data.npz"],
    },
}


# ----------------------------------------------------------------------------- originals
def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _download(url: str, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    print(f"  downloading {url}")
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as fh:  # noqa: S310 (fixed https URLs)
        n = 0
        while True:
            block = r.read(1 << 20)
            if not block:
                break
            fh.write(block)
            n += len(block)
    tmp.replace(dst)
    print(f"  -> {dst.relative_to(ROOT)} ({n / 1e6:.1f} MB)")


def originals(part: str, src: Path | None, refresh: bool) -> list[dict]:
    """Get the originals of a part into tools/fetch_cache/<sub>/; returns their provenance records."""
    recs = []
    for sub, name, url in PARTS[part]["files"]:
        dst = CACHE / sub / name
        if src is not None:
            have = src / sub / name
            if not have.is_file():
                sys.exit(f"--from: {have} not found")
            if have.resolve() != dst.resolve():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(have, dst)
            origin = f"local copy ({name}); original at {url}"
        else:
            if refresh or not dst.is_file():
                _download(url, dst)
            origin = url
        recs.append({"file": name, "url": origin, "sha256": _sha256(dst), "bytes": dst.stat().st_size,
                     "date": date.today().isoformat()})
    return recs


def _unzip_flat(zp: Path, dst: Path, want: set[str] | None = None):
    """Extract members by base name only (no paths from the archive are used)."""
    dst.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zp) as z:
        for info in z.infolist():
            base = Path(info.filename).name
            if info.is_dir() or not base or (want and base not in want):
                continue
            with z.open(info) as fh, open(dst / base, "wb") as out:
                shutil.copyfileobj(fh, out)


def _stamp(path: Path, recs: list[dict], part: str):
    d = json.loads(path.read_text(encoding="utf-8"))
    d["_fetched"] = {"by": "tools/fetch_optional_data.py", "part": part, "terms": PARTS[part]["terms"],
                     "originals": recs}
    path.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def _builder(module: str):
    sys.path.insert(0, str(ER_TOOLS))
    return __import__(module)


# ----------------------------------------------------------------------------- builders
def build_pka(recs):
    raw = CACHE / "_raw"
    _unzip_flat(CACHE / "pka" / "Dissociation-Constants-v2.4.zip", raw / "pka",
                {"iupac_high-confidence_v2_4.csv", "method_translation.csv", "reference_code_translation.csv"})
    _builder("build_data").build_pka(raw)
    _stamp(SDK_DATA / "pka.json", recs, "pka")


def build_srd46(recs):
    raw = CACHE / "_raw"
    _unzip_flat(CACHE / "srd46" / "SRD 46 SQL.zip", raw / "srd46" / "x")
    _builder("build_data").build_srd46(raw)
    _stamp(SDK_DATA / "stability.json", recs, "srd46")


def build_asd(recs):
    sys.path.insert(0, str(ER_TOOLS))
    import build_ie
    build_ie.main(str(CACHE / "asd" / "ie.csv"), str(SDK_DATA / "ionization.json"))
    _stamp(SDK_DATA / "ionization.json", recs, "asd")


def build_burcat(recs):
    _builder("build_data")                                    # sets up the import paths of the builders
    from build_thermo import build_thermo
    data = build_thermo(CACHE, SDK_DATA, lambda p, o: None)     # reads molecules.json there, writes nothing
    out = {"_source": "Burcat/Ruscic-Datenbank (Goos, Burcat & Ruscic; ATcT-Werte), über "
                      "tools/fetch_optional_data.py",
           "_note": data.get("_note", ""),
           "species": [s for s in data["species"] if s.get("src") == "burcat"]}
    dst = SDK_DATA / "optional" / "thermo_burcat.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    _stamp(dst, recs, "burcat")
    print(f"  {dst.relative_to(ROOT)}: {len(out['species'])} species")


def build_openspecy(recs):
    import numpy as np
    sys.path.insert(0, str(FTIR_TOOLS))
    import build_openspecy as B
    with tempfile.TemporaryDirectory() as tmp:
        B.main(str(CACHE / "openspecy" / "nobaseline.rds"), tmp)
        meta = json.loads((Path(tmp) / "meta.json").read_text(encoding="utf-8"))
        with np.load(Path(tmp) / "data.npz") as z:
            arrays = {k: z[k] for k in z.files}
    keep = [i for i, e in enumerate(meta["entries"]) if e.get("origin") not in laboptional.OPENSPECY_OPEN]
    entries = []
    for i in keep:
        e = dict(meta["entries"][i])
        e["id"] = "r" + e["id"]                               # never collides with the public library's ids
        entries.append(e)
    cats: dict[str, int] = {}
    for e in entries:
        cats[e.get("category", "")] = cats.get(e.get("category", ""), 0) + 1
    out_meta = {**meta, "id": "openspecy-restricted", "readonly": True,
                "name": "Referenzen, gemessen (Open Specy, eingeschränkte Lizenzen)",
                "name_en": "Measured references (Open Specy, restricted licences)",
                "description": "Spectra of the Open Specy collection whose source licence does not allow "
                               "redistribution (non-commercial, educational use or unstated). Built on this "
                               "computer by tools/fetch_optional_data.py; each entry names its source and licence.",
                "entries": entries, "counts": cats,
                "_fetched": {"by": "tools/fetch_optional_data.py", "part": "openspecy",
                             "terms": PARTS["openspecy"]["terms"], "originals": recs}}
    if isinstance(meta.get("origins"), dict):
        out_meta["origins"] = {k: v for k, v in meta["origins"].items() if k not in laboptional.OPENSPECY_OPEN}
    dst = FTIR_DATA / "openspecy-restricted"
    dst.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(dst / "data.npz", G=arrays["G"][keep])
    (dst / "meta.json").write_text(json.dumps(out_meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  {dst.relative_to(ROOT)}: {len(entries)} spectra")


BUILD = {"pka": build_pka, "srd46": build_srd46, "asd": build_asd, "burcat": build_burcat,
         "openspecy": build_openspecy}


# ----------------------------------------------------------------------------- command line
def show_list():
    for k, p in PARTS.items():
        state = "installed" if laboptional.available(k) else "not installed"
        print(f"{k:10s} [{state}]  {p['title']}")
        print(f"{'':12s}terms: {p['terms']}")
        print(f"{'':12s}cite:  {p['cite']}")
        for sub, name, url in p["files"]:
            print(f"{'':12s}file:  {sub}/{name}  <- {url}")
        print()


def remove(parts):
    for k in parts:
        for rel in PARTS[k]["out"]:
            p = ROOT / rel
            if p.exists():
                p.unlink()
                print(f"  removed {rel}")
        d = FTIR_DATA / "openspecy-restricted"
        if k == "openspecy" and d.is_dir() and not any(d.iterdir()):
            d.rmdir()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("parts", nargs="*", help="all, or any of: " + ", ".join(PARTS))
    ap.add_argument("--list", action="store_true", help="show parts, terms and what is installed")
    ap.add_argument("--from", dest="src", type=Path, help="folder with originals you downloaded yourself")
    ap.add_argument("--refresh", action="store_true", help="download again even if a cached copy exists")
    ap.add_argument("--remove", action="store_true", help="delete the built files of the given parts")
    a = ap.parse_args(argv)
    if a.list or not a.parts:
        show_list()
        return 0
    parts = list(PARTS) if "all" in a.parts else a.parts
    bad = [p for p in parts if p not in PARTS]
    if bad:
        sys.exit(f"unknown part(s) {', '.join(bad)}; known: all, {', '.join(PARTS)}")
    if a.remove:
        remove(parts)
        return 0
    failed = []
    for k in parts:
        p = PARTS[k]
        print(f"\n== {k}: {p['title']}\n   terms: {p['terms']}")
        try:
            recs = originals(k, a.src, a.refresh)
            BUILD[k](recs)
        except Exception as e:  # noqa: BLE001 – one source being down must not stop the others
            failed.append(k)
            print(f"   FAILED: {type(e).__name__}: {e}")
    laboptional.available.cache_clear()
    print("\ninstalled: " + ", ".join(k for k in PARTS if laboptional.available(k)))
    if failed:
        print("failed:    " + ", ".join(failed) + "  (check the URL with --list, or use --from)")
        return 1
    print("Restart Folio Lab (or the module) so it reads the new data.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
