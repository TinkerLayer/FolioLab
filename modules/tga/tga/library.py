"""TGA-Referenzbibliotheken: mitgelieferte Modellbibliothek (schreibgeschützt) und eigene Bibliotheken.

Ein Eintrag beschreibt das Zersetzungsverhalten eines Stoffes: Stufen (Onset, DTG-Spitze, Ende, Massenverlust),
Rückstand, Atmosphäre und Heizrate, dazu eine strukturierte Quelle (labcite). Für die Suche wird daraus eine DTG-Kurve
(dm/dT in %/°C, positiv für Verlust) auf dem Raster 25–1000 °C (1 K) gebildet:

- Modelleinträge und eingetippte Stufentabellen: Summe von Fraser-Suzuki-Spitzen (Fraser & Suzuki 1969), Fläche =
  Massenverlust der Stufe, linke/rechte Halbwertsbreite aus Onset bzw. Ende (Tangentenkonstruktion an einer
  glockenförmigen DTG: Spitze − Onset ≈ 1,06 · halbe Halbwertsbreite). Ohne Onset/Ende: 50 K Halbwertsbreite,
  gekennzeichnet als geschätzt. **Diese Kurven sind aus Literaturwerten modelliert, nicht gemessen.**
- Gemessene Einträge (eigener Lauf als Referenz gespeichert): DTG aus der gespeicherten Massenkurve.

Eigene Bibliotheken liegen unter <ausgaben>/bibliotheken/<id>/meta.json (+ data.npz für gemessene Kurven), lesbar
und von Hand editierbar.
"""
from __future__ import annotations

import json
import math
import re
import shutil
import threading
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path

import numpy as np

GRID = np.arange(25.0, 1000.0 + 0.5, 1.0)
MODEL_ID = "modell"
DATA = Path(__file__).resolve().parent / "data"
LN2 = math.log(2.0)
ONSET_TO_HW = 1.1774 / 1.2533  # Gauss: Spitze − Onset = σ·√(π/2) ≈ 1,2533 σ; HWHM = 1,1774 σ  ->  HWHM ≈ 0,94·(Tp − Ton)


def fs_peak(x: np.ndarray, x0: float, area: float, hwl: float, hwr: float) -> np.ndarray:
    """Fraser-Suzuki-Spitze mit Fläche `area` und linker/rechter Halbwertsbreite (Halbwertsbreiten > 0)."""
    hwl, hwr = max(0.5, float(hwl)), max(0.5, float(hwr))
    a = math.log(hwr / hwl)
    if abs(a) < 1e-6:
        sig = hwl / math.sqrt(2 * LN2)
        y = np.exp(-0.5 * ((x - x0) / sig) ** 2)
        return area * y / (sig * math.sqrt(2 * math.pi))
    w = 2 * a * hwr / (math.exp(a) - 1)
    arg = 1 + 2 * a * (x - x0) / w
    y = np.zeros_like(x, dtype=float)
    ok = arg > 0
    y[ok] = np.exp(-LN2 * (np.log(arg[ok]) / a) ** 2)
    norm = w / 2 * math.sqrt(math.pi / LN2) * math.exp(a * a / (4 * LN2))
    return area * y / norm


def step_widths(st: dict) -> tuple[float, float, bool]:
    """Linke/rechte Halbwertsbreite aus Onset/Ende; dritter Wert: geschätzt."""
    tp = float(st["T_peak"])
    hwl = hwr = None
    if st.get("T_onset") not in (None, ""):
        hwl = max(2.0, (tp - float(st["T_onset"])) * ONSET_TO_HW)
    if st.get("T_end") not in (None, ""):
        hwr = max(2.0, (float(st["T_end"]) - tp) * ONSET_TO_HW)
    if st.get("hw") not in (None, ""):
        hwl = hwl or float(st["hw"])
        hwr = hwr or float(st["hw"])
    est = hwl is None and hwr is None
    if hwl is None and hwr is None:
        hwl = hwr = 25.0
    elif hwl is None:
        hwl = hwr * 1.4                  # thermische Zersetzung: DTG meist links flacher als rechts
    elif hwr is None:
        hwr = hwl / 1.4
    return hwl, hwr, est


def model_dtg(steps: list[dict], grid: np.ndarray = GRID) -> np.ndarray:
    y = np.zeros(len(grid))
    for st in steps or []:
        if st.get("T_peak") in (None, "") or st.get("loss") in (None, ""):
            continue
        hwl, hwr, _ = step_widths(st)
        p = fs_peak(grid, float(st["T_peak"]), float(st["loss"]), hwl, hwr)
        # stark schiefe Spitzen haben lange Ausläufer über den Rasterrand hinaus: auf dem Raster auf den
        # veröffentlichten Stufenverlust normieren, damit die Modell-TG genau diesen Verlust zeigt
        a = float(np.sum((p[1:] + p[:-1]) / 2 * np.diff(grid)))
        if a > 0:
            p *= float(st["loss"]) / a
        y += p
    return y


def model_tg(steps: list[dict], grid: np.ndarray = GRID) -> np.ndarray:
    d = model_dtg(steps, grid)
    return 100.0 - np.concatenate([[0.0], np.cumsum((d[1:] + d[:-1]) / 2 * np.diff(grid))])


def dtg_of_curve(T: np.ndarray, m_pct: np.ndarray, grid: np.ndarray = GRID) -> np.ndarray:
    """DTG (−dm/dT, %/°C) einer gemessenen Kurve auf dem Raster; nur Heizabschnitt, NaN ausserhalb."""
    T = np.asarray(T, float)
    m = np.asarray(m_pct, float)
    ok = np.isfinite(T) & np.isfinite(m)
    T, m = T[ok], m[ok]
    if len(T) < 10:
        return np.full(len(grid), np.nan)
    # erste Aufheizung: nur Punkte mit steigender Temperatur (laufendes Maximum)
    keep = T >= np.maximum.accumulate(T) - 1e-9
    T, m = T[keep], m[keep]
    T, idx = np.unique(T, return_index=True)
    m = m[idx]
    if len(T) < 10:
        return np.full(len(grid), np.nan)
    mg = np.interp(grid, T, m, left=np.nan, right=np.nan)
    v = np.isfinite(mg)
    out = np.full(len(grid), np.nan)
    if v.sum() < 10:
        return out
    from .process import savgol
    a, b = np.nonzero(v)[0][[0, -1]]
    seg = mg[a:b + 1]
    out[a:b + 1] = -savgol(seg, 9, 2, 1, 1.0)
    return out


def tg_of_curve(T, m_pct, grid: np.ndarray = GRID) -> np.ndarray:
    T = np.asarray(T, float)
    m = np.asarray(m_pct, float)
    keep = T >= np.maximum.accumulate(np.nan_to_num(T, nan=-1e9)) - 1e-9
    T, m = T[keep], m[keep]
    T, idx = np.unique(T, return_index=True)
    return np.interp(grid, T, m[idx], left=np.nan, right=np.nan)


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:40] or "bibliothek"


def _clean_steps(steps) -> list[dict]:
    out = []
    for st in steps or []:
        if not isinstance(st, dict):
            continue
        row = {}
        for k in ("T_onset", "T_peak", "T_end", "loss", "hw"):
            v = st.get(k)
            if v in (None, ""):
                continue
            try:
                f = float(str(v).replace(",", "."))
            except ValueError:
                raise ValueError(f"Stufe: „{v}“ ist keine Zahl")
            if not math.isfinite(f):
                continue
            row[k] = f
        if "T_peak" not in row or "loss" not in row:
            continue
        if not (0 < row["loss"] <= 100) or not (-50 < row["T_peak"] < 1500):
            raise ValueError("Stufe: Massenverlust 0–100 %, Temperatur −50–1500 °C")
        if st.get("label"):
            row["label"] = str(st["label"])[:80]
        out.append(row)
    return sorted(out, key=lambda r: r["T_peak"])


class Library:
    def __init__(self, lid: str, name: str, description: str = "", readonly: bool = False, path: Path | None = None):
        self.id, self.name, self.description, self.readonly, self.path = lid, name, description, readonly, path
        self.created = datetime.now().isoformat(timespec="seconds")
        self.entries: list[dict] = []
        self.raw: dict[str, tuple] = {}           # Eintrag -> (T, m%) gemessen
        self.source = {}                          # Quelle der Bibliothek (labcite)
        self.kind = "own"
        self.version = 0
        self._G = None

    @property
    def G(self) -> np.ndarray:
        """DTG-Suchvektoren (Zeilen = Einträge)."""
        if self._G is None or self._G[0] != self.version:
            rows = [self.dtg(e) for e in self.entries]
            self._G = (self.version, np.array(rows, dtype=np.float64) if rows else np.zeros((0, len(GRID))))
        return self._G[1]

    def dtg(self, e: dict) -> np.ndarray:
        if e["id"] in self.raw:
            T, m = self.raw[e["id"]]
            return dtg_of_curve(T, m)
        return model_dtg(e.get("steps"))

    def tg(self, e: dict) -> np.ndarray:
        if e["id"] in self.raw:
            T, m = self.raw[e["id"]]
            return tg_of_curve(T, m)
        return model_tg(e.get("steps"))

    def info(self) -> dict:
        cats = sorted({e.get("category") or "" for e in self.entries} - {""})
        return {"id": self.id, "name": self.name, "description": self.description, "readonly": self.readonly,
                "count": len(self.entries), "categories": cats, "created": self.created, "kind": self.kind,
                "source": self.source}

    def ref_of(self, e: dict) -> dict:
        out = {"lib": self.id, "lib_name": self.name, "id": e["id"], "name": e["name"], "kind": e.get("kind", "model"),
               "source": e.get("source") or {}, "atmosphere": e.get("atmosphere", ""), "rate": e.get("rate")}
        if self.kind == "model":
            out["modelled"] = True
        return out

    def index(self, eid: str) -> int:
        for i, e in enumerate(self.entries):
            if e["id"] == eid:
                return i
        raise LookupError("Eintrag nicht gefunden")

    def entry(self, eid: str) -> dict:
        return self.entries[self.index(eid)]

    # --------------------------------------------------------------- Ändern
    def _check_rw(self):
        if self.readonly:
            raise PermissionError(f"„{self.name}“ ist schreibgeschützt.")

    def _meta(self, meta: dict, e: dict | None = None) -> dict:
        import labcite
        e = dict(e or {})
        for k in ("name", "category", "atmosphere", "note", "group", "formula", "cas"):
            if k in meta and meta[k] is not None:
                e[k] = str(meta[k]).strip()[:300]
        for k in ("rate", "residue", "m0"):
            if meta.get(k) not in (None, ""):
                try:
                    e[k] = float(str(meta[k]).replace(",", "."))
                except ValueError:
                    raise ValueError(f"{k}: keine Zahl")
        if "source" in meta:
            s = meta["source"]
            e["source"] = labcite.clean(s) if isinstance(s, dict) else labcite.from_legacy(str(s or ""))
        if "steps" in meta:
            e["steps"] = _clean_steps(meta["steps"])
        if not e.get("name"):
            raise ValueError("Name fehlt")
        return e

    def add_steps(self, meta: dict) -> dict:
        """Referenz aus einer Stufentabelle (z. B. Werte aus einem Paper)."""
        self._check_rw()
        e = self._meta(meta, {"id": uuid.uuid4().hex[:10], "kind": "steps", "added": datetime.now().isoformat(timespec="seconds")})
        if not e.get("steps"):
            raise ValueError("Mindestens eine Stufe mit DTG-Spitze und Massenverlust angeben.")
        self.entries.append(e)
        self.version += 1
        return e

    def add_curve(self, T: np.ndarray, m_pct: np.ndarray, meta: dict) -> dict:
        """Gemessener Lauf als Referenz (Masse in % der Bezugsmasse)."""
        self._check_rw()
        e = self._meta(meta, {"id": uuid.uuid4().hex[:10], "kind": "measured", "added": datetime.now().isoformat(timespec="seconds")})
        T = np.asarray(T, np.float32)
        m = np.asarray(m_pct, np.float32)
        if len(T) < 20:
            raise ValueError("Zu wenige Messpunkte für eine Referenz")
        e["Tmin"], e["Tmax"] = float(np.nanmin(T)), float(np.nanmax(T))
        if "residue" not in e:
            e["residue"] = float(np.median(m[-3:]))
        self.entries.append(e)
        self.raw[e["id"]] = (T, m)
        self.version += 1
        return e

    def update(self, eid: str, meta: dict) -> dict:
        self._check_rw()
        i = self.index(eid)
        e = self._meta(meta, self.entries[i])
        if e.get("kind") == "steps" and not e.get("steps"):
            raise ValueError("Mindestens eine Stufe angeben.")
        self.entries[i] = e
        self.version += 1
        return e

    def remove(self, eid: str):
        self._check_rw()
        i = self.index(eid)
        self.entries.pop(i)
        self.raw.pop(eid, None)
        self.version += 1

    # --------------------------------------------------------------- Datei
    def save(self):
        if self.readonly or self.path is None:
            return
        self.path.mkdir(parents=True, exist_ok=True)
        meta = {"format": "folio-tga-bibliothek/1", "id": self.id, "name": self.name, "description": self.description,
                "created": self.created, "source": self.source, "entries": self.entries}
        if self.raw:
            arrays = {}
            for eid, (T, m) in self.raw.items():
                arrays[f"T_{eid}"] = T
                arrays[f"m_{eid}"] = m
            tmp = self.path / "data.tmp.npz"
            np.savez_compressed(tmp, **arrays)
            tmp.replace(self.path / "data.npz")
        elif (self.path / "data.npz").exists():
            (self.path / "data.npz").unlink()
        tmp = self.path / "meta.tmp.json"
        tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path / "meta.json")

    @classmethod
    def load(cls, path: Path) -> "Library":
        meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
        lib = cls(meta.get("id") or path.name, meta.get("name") or path.name, meta.get("description", ""), False, path)
        lib.created = meta.get("created", lib.created)
        lib.source = meta.get("source") or {}
        lib.entries = [e for e in meta.get("entries", []) if isinstance(e, dict) and e.get("id")]
        if (path / "data.npz").exists():
            with np.load(path / "data.npz") as z:
                for e in lib.entries:
                    if f"T_{e['id']}" in z:
                        lib.raw[e["id"]] = (z[f"T_{e['id']}"], z[f"m_{e['id']}"])
        for e in lib.entries:
            if e.get("kind") == "measured" and e["id"] not in lib.raw:
                e["kind"] = "steps"
        return lib

    def export(self) -> dict:
        """Ganze Bibliothek als JSON (Messkurven als Listen), z. B. zum Weitergeben."""
        ents = []
        for e in self.entries:
            x = dict(e)
            if e["id"] in self.raw:
                T, m = self.raw[e["id"]]
                x["curve"] = {"T": [round(float(v), 2) for v in T], "m": [round(float(v), 4) for v in m]}
            ents.append(x)
        return {"format": "folio-tga-bibliothek/1", "name": self.name, "description": self.description,
                "source": self.source, "entries": ents}

    def import_(self, data: dict) -> int:
        self._check_rw()
        n = 0
        for x in (data or {}).get("entries", []):
            if not isinstance(x, dict):
                continue
            curve = x.pop("curve", None)
            x.pop("id", None)
            if curve and curve.get("T"):
                self.add_curve(np.array(curve["T"], float), np.array(curve["m"], float), x)
            else:
                self.add_steps(x)
            n += 1
        return n


def model_library() -> Library:
    """Mitgelieferte Modellbibliothek aus tga/data/referenzen.json."""
    lib = Library(MODEL_ID, "Modellbibliothek TGA (aus Literaturwerten modelliert)",
                  "DTG-Kurven aus veröffentlichten Stufenwerten (Onset, DTG-Spitze, Massenverlust, Rückstand) berechnet; "
                  "keine gemessenen Kurven. Jede Referenz nennt ihre Quelle. Für belastbare Identifizierungen eigene "
                  "Referenzen messen und als eigene Bibliothek anlegen.", readonly=True)
    lib.kind = "model"
    p = DATA / "referenzen.json"
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        lib.source = d.get("source") or {}
        for e in d.get("entries", []):
            e = dict(e)
            e.setdefault("kind", "model")
            e["steps"] = _clean_steps(e.get("steps"))
            if e.get("steps"):
                lib.entries.append(e)
    return lib


class Libraries:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.lock = threading.RLock()
        self.errors: list[str] = []
        self.libs: dict[str, Library] = {}
        try:
            self.libs[MODEL_ID] = model_library()
        except Exception as e:  # noqa: BLE001
            self.errors.append(f"Modellbibliothek: {e}")
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

    def create(self, name: str, description: str = "", source: dict | None = None) -> Library:
        import labcite
        name = (name or "").strip()
        if not name:
            raise ValueError("Bitte einen Namen für die Bibliothek angeben.")
        with self.lock:
            base = slugify(name)
            lid, k = base, 2
            while lid in self.libs or (self.root / lid).exists():
                lid = f"{base}-{k}"
                k += 1
            lib = Library(lid, name[:120], (description or "").strip()[:500], False, self.root / lid)
            lib.source = labcite.clean(source) if isinstance(source, dict) else {}
            lib.save()
            self.libs[lid] = lib
            return lib

    def own(self, name: str = "Eigene Referenzen") -> Library:
        """Bibliothek „Eigene Referenzen“, bei Bedarf angelegt."""
        for lib in self.libs.values():
            if not lib.readonly and lib.name == name:
                return lib
        return self.create(name, "Eigene Referenzen aus Messungen und Literatur")

    def delete(self, lid: str):
        with self.lock:
            lib = self.get(lid)
            if lib.readonly:
                raise PermissionError(f"„{lib.name}“ ist mitgeliefert und lässt sich nicht löschen.")
            self.libs.pop(lid)
            if lib.path and lib.path.exists() and self.root.resolve() in lib.path.resolve().parents:
                shutil.rmtree(lib.path)
