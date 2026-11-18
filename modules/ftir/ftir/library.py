"""Spektrenbibliotheken: eingebaute Modellbibliothek (schreibgeschützt) und eigene Bibliotheken auf der Festplatte.

Jede Bibliothek liegt in <ausgaben>/bibliotheken/<id>/ als meta.json (Einträge mit Name, Kategorie, CAS, Quelle,
Bemerkung) und data.npz (für die Suche vorbereitete Spektren auf dem Raster 400–4000 cm⁻¹, Abstand 2 cm⁻¹, sowie
das eingelesene Spektrum selbst). Vorbereitung für die Suche: in Absorbanz umrechnen, auf das Raster mitteln,
Basislinie (Gummiband) abziehen, Maximum 1. Ausserhalb des gemessenen Bereichs bleibt der Wert leer (NaN).
"""
from __future__ import annotations

import json
import re
import shutil
import threading
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path

import numpy as np

from . import refdata
from .process import moving_mean, rubberband, savgol, to_absorbance
from .readers import Spectrum, to_jcamp

GRID = refdata.GRID
MODEL_ID = "modell"
DATA_DIR = Path(__file__).resolve().parent / "data"      # mitgelieferte, schreibgeschützte Bibliotheken


def prep(x: np.ndarray, y: np.ndarray, yunit: str = "A", baseline: bool = True, blank=None) -> np.ndarray:
    """Spektrum -> Suchvektor auf GRID (float32, NaN ausserhalb).

    blank: Bereiche [[hoch, tief], ...] (z. B. verrauschte), die leer bleiben. Sie zählen dann weder für die
    Basislinie und die Normierung noch für den Vergleich."""
    x = np.asarray(x, float)
    a = to_absorbance(np.asarray(y, float), yunit)
    step = float(np.median(np.diff(x))) if len(x) > 1 else 2.0
    if 0 < step < 2.0:
        a = moving_mean(a, int(round(2.0 / step)) | 1)
    g = np.interp(GRID, x, a, left=np.nan, right=np.nan)
    for r in blank or []:
        lo, hi = sorted((float(r[0]), float(r[1])))
        g[(GRID >= lo) & (GRID <= hi)] = np.nan
    v = np.isfinite(g)
    if v.sum() < 20:
        raise ValueError("Das Spektrum überdeckt zu wenig vom Bereich 400–4000 cm⁻¹.")
    if baseline:
        g[v] = g[v] - rubberband(GRID[v], g[v])
    mx = float(np.nanmax(g))
    if mx > 0:
        g = g / mx
    return g.astype(np.float32)


def deriv(g: np.ndarray) -> np.ndarray:
    """1. Ableitung (Savitzky-Golay, 9 Punkte) eines Suchvektors, nur im belegten Bereich."""
    out = np.full_like(g, np.nan, dtype=np.float32)
    v = np.where(np.isfinite(g))[0]
    if len(v) < 12:
        return out
    a, b = v[0], v[-1] + 1
    seg = g[a:b].astype(float)
    gap = ~np.isfinite(seg)
    if gap.any():
        # Lücken (ausgeblendete verrauschte Bereiche) linear überbrücken und danach samt Rand wieder leeren
        idx = np.arange(len(seg))
        seg[gap] = np.interp(idx[gap], idx[~gap], seg[~gap])
    d = savgol(seg, 9, 2, 1, 2.0)
    if gap.any():
        near = np.convolve(gap.astype(float), np.ones(9), mode="same") > 0
        d[near] = np.nan
    s = float(np.nanmax(np.abs(d))) or 1.0
    out[a:b] = d / s
    return out


def _labcite():
    try:
        import labcite
    except ImportError:  # ausserhalb des Hubs gestartet: SDK aus dem Suite-Ordner holen
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "sdk" / "python"))
        import labcite
    return labcite


def clean_cite(rec) -> dict | None:
    """Strukturierte Quelle (labcite) prüfen und vereinheitlichen; leer -> None, fehlerhaft -> ValueError."""
    if not isinstance(rec, dict):
        return None
    C = _labcite()
    if not C.is_record(rec):
        return None
    err = C.errors(rec)
    if err:
        raise ValueError("Quelle: " + "; ".join(err))
    return C.clean(rec)


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:40] or "bibliothek"


class Library:
    def __init__(self, lid: str, name: str, description: str = "", readonly: bool = False, path: Path | None = None):
        self.id, self.name, self.description, self.readonly, self.path = lid, name, description, readonly, path
        self.created = datetime.now().isoformat(timespec="seconds")
        self.entries: list[dict] = []
        self.G = np.zeros((0, len(GRID)), dtype=np.float32)
        self.raw: dict[str, tuple] = {}            # Eintrag -> (x, y, yunit)
        self.version = 0
        self.source = ""
        self.cite: dict | None = None      # Quelle der ganzen Sammlung (strukturiert), optional
        self._d = None
        self._pk = None
        self._mats = {}

    # --------------------------------------------------------------- abgeleitete Grössen (zwischengespeichert)
    @property
    def D(self) -> np.ndarray:
        if self._d is None or self._d[0] != self.version:
            self._d = (self.version, np.array([deriv(g) for g in self.G]) if len(self.G) else self.G.copy())
        return self._d[1]

    def mats(self, which: str = "G"):
        """Für die Suche vorbereitete Matrizen (float32): Werte mit 0 statt NaN, belegt (0/1), Quadrate."""
        c = self._mats.get(which)
        if c is None or c[0] != self.version:
            L = self.D if which == "D" else self.G
            W = np.isfinite(L)
            L0 = np.where(W, L, 0).astype(np.float32)
            c = (self.version, L0, W.astype(np.float32), L0 * L0)
            self._mats[which] = c
        return c[1:]

    def peaklists(self):
        if self._pk is None or self._pk[0] != self.version:
            from . import peaks as PK
            out = []
            for g in self.G:
                v = np.isfinite(g)
                if v.sum() < 12:
                    out.append(([], []))
                    continue
                p = PK.find(GRID[v], g[v].astype(float), "A", {"prominence": 1.5, "distance": 6, "max": 40, "snr": 0})
                out.append(([q["x"] for q in p], [q["rel"] for q in p]))
            self._pk = (self.version, out)
        return self._pk[1]

    def info(self) -> dict:
        cats = sorted({e.get("category") or "" for e in self.entries} - {""})
        return {"id": self.id, "name": self.name, "description": self.description, "readonly": self.readonly,
                "count": len(self.entries), "categories": cats, "created": self.created, "source": self.source,
                "substances": len({e.get("group") or e["id"] for e in self.entries}), "cite": self.cite}

    def cite_fields(self, e: dict) -> dict:
        """Strukturierte Quellen von Eintrag und Sammlung, so wie Treffer und Bericht sie weitertragen."""
        out = {}
        if e.get("cite"):
            out["cite"] = e["cite"]
        if self.cite:
            out["lib_cite"] = self.cite
        return out

    def ref_of(self, e: dict) -> dict:
        """Herkunft eines Eintrags, wie sie Treffer, geöffnete Referenzen und der Bericht verwenden."""
        out = {"lib": self.id, "lib_name": self.name, "id": e["id"], "name": e["name"], "source": e.get("source", "")}
        for k in ("mode", "license"):
            if e.get(k):
                out[k] = e[k]
        out.update(self.cite_fields(e))
        return out

    # --------------------------------------------------------------- Ändern
    def add(self, sp: Spectrum, meta: dict | None = None) -> dict:
        if self.readonly:
            raise PermissionError(f"„{self.name}“ ist schreibgeschützt.")
        m = meta or {}
        cite = clean_cite(m.get("cite"))
        g = prep(sp.x, sp.y, sp.yunit)
        eid = uuid.uuid4().hex[:10]
        src = (m.get("source") or "").strip() or (_labcite().text(cite) if cite else "") or \
            (sp.meta.get("origin") or sp.meta.get("format") or "").strip()
        e = {"id": eid, "name": (m.get("name") or sp.name).strip()[:200], "category": (m.get("category") or "").strip(),
             "cas": (m.get("cas") or sp.meta.get("cas") or "").strip(), "formula": (m.get("formula") or sp.meta.get("formula") or ""),
             "source": src[:500],
             "comment": (m.get("comment") or "").strip(), "added": datetime.now().isoformat(timespec="seconds"),
             "xmin": float(sp.x[0]), "xmax": float(sp.x[-1]), "yunit": sp.yunit}
        if cite:
            e["cite"] = cite
        self.entries.append(e)
        self.G = np.vstack([self.G, g[None, :]])
        self.raw[eid] = (sp.x.astype(np.float32), sp.y.astype(np.float32), sp.yunit)
        self.version += 1
        return e

    def remove(self, eid: str):
        if self.readonly:
            raise PermissionError(f"„{self.name}“ ist schreibgeschützt.")
        i = self.index(eid)
        self.entries.pop(i)
        self.G = np.delete(self.G, i, axis=0)
        self.raw.pop(eid, None)
        self.version += 1

    def update(self, eid: str, meta: dict):
        if self.readonly:
            raise PermissionError(f"„{self.name}“ ist schreibgeschützt.")
        e = self.entries[self.index(eid)]
        if "cite" in meta:                      # vor den übrigen Feldern prüfen: fehlerhafte Quelle ändert nichts
            cite = clean_cite(meta["cite"])
            if cite:
                e["cite"] = cite
                if not str(meta.get("source") or "").strip():
                    meta = dict(meta, source=_labcite().text(cite))
            else:
                e.pop("cite", None)
        for k in ("name", "category", "cas", "formula", "source", "comment"):
            if k in meta and meta[k] is not None:
                e[k] = str(meta[k]).strip()[:500]
        self.version += 1
        return e

    def index(self, eid: str) -> int:
        for i, e in enumerate(self.entries):
            if e["id"] == eid:
                return i
        raise LookupError("Eintrag nicht gefunden")

    def spectrum(self, eid: str) -> Spectrum:
        e = self.entries[self.index(eid)]
        if eid in self.raw:
            x, y, u = self.raw[eid]
            return Spectrum(e["name"], x, y, u, {"library": self.name})
        g = self.G[self.index(eid)]
        v = np.isfinite(g)
        return Spectrum(e["name"], GRID[v], g[v], "A", {"library": self.name})

    # --------------------------------------------------------------- Datei
    def save(self):
        if self.readonly or self.path is None:
            return
        self.path.mkdir(parents=True, exist_ok=True)
        meta = {"format": "folio-ftir-bibliothek/1", "id": self.id, "name": self.name, "description": self.description,
                "created": self.created, "entries": self.entries}
        if self.cite:
            meta["cite"] = self.cite
        arrays = {"G": self.G}
        for eid, (x, y, _u) in self.raw.items():
            arrays[f"x_{eid}"] = x
            arrays[f"y_{eid}"] = y
        tmp = self.path / "data.tmp.npz"
        np.savez_compressed(tmp, **arrays)
        tmp.replace(self.path / "data.npz")
        (self.path / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")

    @classmethod
    def load(cls, path: Path, lang: str = "de") -> "Library":
        meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
        ro = bool(meta.get("readonly"))
        name = (meta.get("name_en") if lang == "en" else None) or meta.get("name") or path.name
        lib = cls(meta.get("id") or path.name, name, meta.get("description", ""), ro, None if ro else path)
        lib.created = meta.get("created", lib.created)
        lib.source = meta.get("source", "")
        lib.cite = meta.get("cite") if isinstance(meta.get("cite"), dict) else None
        lib.entries = meta.get("entries", [])
        if lang == "en":
            for e in lib.entries:
                e["name"] = e.get("name_en") or e["name"]
        if (path / "data.npz").exists():
            with np.load(path / "data.npz") as z:
                lib.G = z["G"].astype(np.float32) if "G" in z else lib.G
                for e in lib.entries:
                    if f"x_{e['id']}" in z:
                        lib.raw[e["id"]] = (z[f"x_{e['id']}"], z[f"y_{e['id']}"], e.get("yunit", "A"))
        if len(lib.G) != len(lib.entries):
            raise ValueError(f"Bibliothek {path.name}: Daten und Einträge passen nicht zusammen")
        return lib

    def to_jcamp(self) -> str:
        blocks = [f"##TITLE={self.name}", "##JCAMP-DX=5.01", "##DATA TYPE=LINK", f"##BLOCKS={len(self.entries)}"]
        out = "\n".join(blocks) + "\n"
        for i, e in enumerate(self.entries, 1):
            sp = self.spectrum(e["id"])
            out += to_jcamp(sp, e["name"], {"BLOCK_ID": i, "CAS REGISTRY NO": e.get("cas"), "MOLFORM": e.get("formula"),
                                             "ORIGIN": e.get("source") or "Folio Lab", "$CATEGORY": e.get("category"),
                                             "$COMMENT": e.get("comment")})
        return out + "##END=\n"


def model_library(lang: str = "de") -> Library:
    lib = Library(MODEL_ID, "Modellbibliothek (Folio Lab)" if lang == "de" else "Model library (Folio Lab)",
                  "Aus Literatur-Bandenlagen berechnete Referenzen gängiger Kunststoffe, Elastomere, Füllstoffe, "
                  "Lösemittel und Naturstoffe. Keine gemessenen Spektren: zum Eingrenzen und Ausprobieren; für "
                  "belastbare Identifizierungen eigene Referenzen einlesen.", readonly=True)
    rows = []
    for e in refdata.entries(lang):
        y = refdata.band_model(e["bands"])
        rows.append(y.astype(np.float32))
        lib.entries.append({"id": e["id"], "name": e["name"], "category": e["category"], "cas": "", "formula": "",
                            "source": e["source"], "comment": "", "xmin": 400.0, "xmax": 4000.0, "yunit": "A"})
    lib.G = np.array(rows, dtype=np.float32)
    return lib


def bundled_libraries(lang: str = "de") -> list[Library]:
    """Mitgelieferte gemessene Referenzbibliotheken (ftir/data/<id>/), schreibgeschützt."""
    out = []
    if DATA_DIR.exists():
        for p in sorted(DATA_DIR.iterdir()):
            if (p / "meta.json").exists() and (p / "data.npz").exists():
                out.append(Library.load(p, lang))
    return out


def _warm(libs):
    for lib in libs:
        try:
            lib.mats("G")
            lib.mats("D")
            lib.peaklists()
        except Exception:  # noqa: BLE001 – nur Vorbereitung, die Suche rechnet sonst selbst
            pass


class Libraries:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.lock = threading.RLock()
        self.libs: dict[str, Library] = {MODEL_ID: model_library()}
        self.errors: list[str] = []
        try:
            bundled = bundled_libraries()
            for lib in bundled:
                self.libs[lib.id] = lib
            # Ableitungen, Suchmatrizen und Bandenlisten im Hintergrund vorbereiten (sonst dauert die erste Peaksuche
            # über die gemessenen Referenzen einige Sekunden)
            threading.Thread(target=_warm, args=(bundled,), daemon=True).start()
        except Exception as e:  # noqa: BLE001
            self.errors.append(f"mitgelieferte Bibliothek: {e}")
        if self.root.exists():
            for p in sorted(self.root.iterdir()):
                if (p / "meta.json").exists():
                    try:
                        lib = Library.load(p)
                        self.libs[lib.id] = lib
                    except Exception as e:  # noqa: BLE001
                        self.errors.append(f"{p.name}: {e}")

    def get(self, lid: str) -> Library:
        lib = self.libs.get(lid)
        if lib is None:
            raise LookupError(f"Bibliothek „{lid}“ nicht gefunden")
        return lib

    def list(self) -> list[dict]:
        return [lib.info() for lib in self.libs.values()]

    def create(self, name: str, description: str = "", cite: dict | None = None) -> Library:
        name = (name or "").strip()
        if not name:
            raise ValueError("Bitte einen Namen für die Bibliothek angeben.")
        cite = clean_cite(cite)
        with self.lock:
            base = slugify(name)
            lid, k = base, 2
            while lid in self.libs or (self.root / lid).exists():
                lid = f"{base}-{k}"
                k += 1
            lib = Library(lid, name, description.strip(), False, self.root / lid)
            lib.cite = cite
            lib.save()
            self.libs[lid] = lib
            return lib

    OWN_REFS = "eigene-referenzen"

    def own_refs(self) -> Library:
        """Bibliothek „Eigene Referenzen“ für schnell eingeblendete Referenzen aus Dateien; wird bei Bedarf angelegt."""
        with self.lock:
            lib = self.libs.get(self.OWN_REFS)
            if lib is not None and not lib.readonly:
                return lib
            lib = Library(self.OWN_REFS, "Eigene Referenzen", "Aus Dateien eingeblendete Referenzspektren mit Quelle",
                          False, self.root / self.OWN_REFS)
            lib.save()
            self.libs[lib.id] = lib
            return lib

    def delete(self, lid: str):
        with self.lock:
            lib = self.get(lid)
            if lib.readonly:
                raise PermissionError(f"„{lib.name}“ ist mitgeliefert und lässt sich nicht löschen.")
            self.libs.pop(lid)
            if lib.path and lib.path.exists() and self.root.resolve() in lib.path.resolve().parents:
                shutil.rmtree(lib.path)
